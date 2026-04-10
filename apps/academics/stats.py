# academics/stats.py
"""
Aggregation and statistics functions for the academics app.

INTENDED CALLERS
────────────────
These functions are designed for dashboards, reports, and data-export
endpoints that need aggregated summaries across many records.

They are NOT intended for individual detail views (class_detail,
level_detail, etc.) — those build lightweight stats dicts from model
properties and cheap annotated querysets directly in views.py.

REMOVED vs original
────────────────────
  get_current_academic_session()
      Duplicate of the function in utils.py.  All callers should import
      from academics.utils (or call AcademicSession.get_current_session()
      directly).

  get_academic_dashboard_statistics() — simple / early version
      The file originally defined two functions with the same name.
      The first (simple) version was silently overwritten by the second
      (comprehensive) one at module load time.  The dead simple version
      has been removed; the comprehensive one is kept under the same name.

FIXED vs original
─────────────────
  get_holiday_statistics()
      Accessed holiday.duration on Holiday instances but the model defines
      the property as duration_days.  Fixed all references.

  get_class_statistics()
      by_session was built with an incorrect values_list call that
      produced 3-tuples of (year, term, id) rather than counts; iterated
      over those tuples as if they were (year, term, count).  Replaced
      with a proper values().annotate(count=Count()) query.

      by_level was built the same broken way.  Replaced with a clean
      values_list().annotate() query.

  get_enrollment_statistics()
      The gender breakdown filtered student__gender as a falsy guard
      (`if gender['student__gender']`) which silently dropped any gender
      value that is an empty string stored in the DB rather than NULL.
      Changed to an explicit `is not None` check.

      recent_enrollments used extra(select={'day': 'date(enrollment_date)'})
      which is a legacy, database-specific API.  Replaced with
      TruncDate() which is database-agnostic and consistent with the rest
      of the file.

  All functions
      Date/datetime keys in aggregation dicts (by_year, by_month) are
      now consistently converted to strings before being returned, so
      callers serialising to JSON never hit "Object of type date is not
      JSON serialisable".
"""

from django.utils import timezone
from django.db.models import (
    Count, Q, Avg, Sum, Max, Min, F,
    Case, When, IntegerField, FloatField, DecimalField,
)
from django.db.models.functions import TruncMonth, TruncYear, TruncDate
from datetime import timedelta, date
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)

from core.utils import get_school_today, get_school_current_time


# =============================================================================
# ACADEMIC SESSION STATISTICS
# =============================================================================

def get_academic_session_statistics(filters=None):
    """
    Comprehensive statistics for academic sessions.

    Args:
        filters (dict, optional):
            year_name   – filter by specific academic year string
            period_type – filter by period type
            is_active   – bool
            is_current  – bool
            date_range  – tuple (start_date, end_date)

    Returns:
        dict
    """
    from .models import AcademicSession

    sessions = AcademicSession.objects.all()

    if filters:
        if filters.get('year_name'):
            sessions = sessions.filter(year_name=filters['year_name'])
        if filters.get('period_type'):
            sessions = sessions.filter(period_type=filters['period_type'])
        if filters.get('is_active') is not None:
            sessions = sessions.filter(is_active=filters['is_active'])
        if filters.get('is_current') is not None:
            sessions = sessions.filter(is_current=filters['is_current'])
        if filters.get('date_range'):
            start_date, end_date = filters['date_range']
            sessions = sessions.filter(
                Q(start_date__gte=start_date, start_date__lte=end_date) |
                Q(end_date__gte=start_date, end_date__lte=end_date)
            )

    total_sessions = sessions.count()
    current_date   = timezone.now().date()

    stats = {
        'total_sessions':  total_sessions,
        'active_sessions': sessions.filter(is_active=True).count(),
        'inactive_sessions': sessions.filter(is_active=False).count(),
        'current_session': sessions.filter(is_current=True).first(),
        'closed_sessions': sessions.filter(is_academically_closed=True).count(),
        'open_sessions':   sessions.filter(is_academically_closed=False).count(),

        'status_breakdown': {
            'current':  sessions.filter(is_current=True).count(),
            'upcoming': sessions.filter(
                start_date__gt=current_date, is_active=True
            ).count(),
            'ongoing':  sessions.filter(
                start_date__lte=current_date,
                end_date__gte=current_date,
                is_active=True,
                is_current=False,
            ).count(),
            'completed': sessions.filter(
                end_date__lt=current_date,
                is_academically_closed=False,
            ).count(),
            'closed': sessions.filter(is_academically_closed=True).count(),
        },

        'by_period_type': dict(
            sessions.values('period_type')
            .annotate(count=Count('id'))
            .values_list('period_type', 'count')
        ),

        'special_session_stats': {
            'regular_sessions': sessions.filter(is_special_session=False).count(),
            'special_sessions': sessions.filter(is_special_session=True).count(),
        },

        'promotion_stats': {
            'allows_promotion':  sessions.filter(allows_promotion=True).count(),
            'promotion_done':    sessions.filter(promotion_done=True).count(),
            'promotion_pending': sessions.filter(
                allows_promotion=True, promotion_done=False
            ).count(),
        },

        # Values are plain strings so callers can JSON-serialise without issue
        'by_year': dict(
            sessions.values('year_name')
            .annotate(count=Count('id'))
            .order_by('-year_name')
            .values_list('year_name', 'count')
        ),

        'enrollment_stats': {
            'open_for_enrollment': sessions.filter(
                is_active=True,
                is_academically_closed=False,
            ).count(),
            'past_deadline': sessions.filter(
                enrollment_deadline__lt=current_date,
                late_enrollment_allowed=False,
            ).count(),
            'allows_late_enrollment': sessions.filter(
                late_enrollment_allowed=True
            ).count(),
        },
    }

    if total_sessions > 0:
        sessions_with_dates = sessions.exclude(
            Q(start_date__isnull=True) | Q(end_date__isnull=True)
        )

        if sessions_with_dates.exists():
            durations = [
                (s.end_date - s.start_date).days
                for s in sessions_with_dates
            ]
            stats['duration_analysis'] = {
                'average_duration_days': sum(durations) / len(durations),
                'shortest_duration_days': min(durations),
                'longest_duration_days':  max(durations),
                'total_academic_days':    sum(durations),
            }

        active_sessions = sessions.filter(
            is_active=True, is_academically_closed=False
        )
        if active_sessions.exists():
            stats['progress_analysis'] = [
                {
                    'session':              str(s),
                    'progress_percentage':  s.progress_percentage,
                    'days_elapsed':         s.days_elapsed,
                    'days_remaining':       s.days_remaining,
                }
                for s in active_sessions
                if s.total_days > 0
            ]

    stats['recent_activity'] = {
        'created_last_30_days': sessions.filter(
            created_at__gte=timezone.now() - timedelta(days=30)
        ).count(),
        'modified_last_7_days': sessions.filter(
            updated_at__gte=timezone.now() - timedelta(days=7)
        ).count(),
        'starting_next_30_days': sessions.filter(
            start_date__gte=current_date,
            start_date__lte=current_date + timedelta(days=30),
        ).count(),
        'ending_next_30_days': sessions.filter(
            end_date__gte=current_date,
            end_date__lte=current_date + timedelta(days=30),
        ).count(),
    }

    return stats


def get_session_timeline_data(year_name=None, include_breaks=True):
    """
    Timeline data for session visualisation.

    Args:
        year_name (str, optional): Filter to a single academic year.
        include_breaks (bool): Append school-break holidays to the timeline.

    Returns:
        dict: timeline (list), total_items (int), year_name (str or None).
    """
    from .models import AcademicSession, Holiday

    sessions = AcademicSession.objects.all().order_by('start_date')
    if year_name:
        sessions = sessions.filter(year_name=year_name)

    timeline = [
        {
            'type':        'session',
            'id':          s.id,
            'name':        s.name,
            'start_date':  s.start_date,
            'end_date':    s.end_date,
            'duration_days': s.total_days,
            'status':      s.status_display,
            'is_current':  s.is_current,
            'is_closed':   s.is_academically_closed,
            'term_number': s.term_number,
            'year_name':   s.year_name,
        }
        for s in sessions
    ]

    if include_breaks:
        try:
            breaks = Holiday.objects.filter(
                holiday_type='SCHOOL_BREAK'
            ).order_by('start_date')
            if year_name:
                breaks = breaks.filter(
                    academic_session__year_name=year_name
                )
            for h in breaks:
                end   = h.end_date or h.start_date
                timeline.append({
                    'type':        'break',
                    'id':          h.id,
                    'name':        h.name,
                    'start_date':  h.start_date,
                    'end_date':    end,
                    'duration_days': (end - h.start_date).days + 1,
                })
        except Exception as e:
            logger.warning(f"Could not fetch holiday break data: {e}")

    timeline.sort(key=lambda x: x['start_date'])

    return {
        'timeline':    timeline,
        'total_items': len(timeline),
        'year_name':   year_name,
    }


# =============================================================================
# HOLIDAY STATISTICS
# =============================================================================

def get_holiday_statistics(filters=None):
    """
    Comprehensive statistics for holidays and school breaks.

    Args:
        filters (dict, optional):
            holiday_type     – filter by type string
            year             – filter by calendar year (int)
            academic_session – filter by session FK

    Returns:
        dict
    """
    from .models import Holiday

    holidays = Holiday.objects.all()

    if filters:
        if filters.get('holiday_type'):
            holidays = holidays.filter(holiday_type=filters['holiday_type'])
        if filters.get('year'):
            holidays = holidays.filter(start_date__year=filters['year'])
        if filters.get('academic_session'):
            holidays = holidays.filter(
                academic_session_id=filters['academic_session']
            )

    total_holidays = holidays.count()

    stats = {
        'total_holidays': total_holidays,

        'by_type': dict(
            holidays.values('holiday_type')
            .annotate(count=Count('id'))
            .values_list('holiday_type', 'count')
        ),

        # Keyed by string "YYYY" to stay JSON-serialisable
        'by_year':  {},
        'by_month': {},
    }

    # Year distribution — convert date → string
    for item in (
        holidays
        .annotate(year=TruncYear('start_date'))
        .values('year')
        .annotate(count=Count('id'))
        .order_by('-year')
    ):
        if item['year']:
            stats['by_year'][item['year'].strftime('%Y')] = item['count']

    # Monthly distribution — convert date → string "YYYY-MM"
    for item in (
        holidays
        .annotate(month=TruncMonth('start_date'))
        .values('month')
        .annotate(count=Count('id'))
        .order_by('month')
    ):
        if item['month']:
            stats['by_month'][item['month'].strftime('%Y-%m')] = item['count']

    if total_holidays > 0:
        # duration_days is the correct property name on the Holiday model
        holidays_with_end = holidays.exclude(end_date__isnull=True)

        if holidays_with_end.exists():
            durations = [h.duration_days for h in holidays_with_end]
            stats['duration_analysis'] = {
                'average_duration_days': sum(durations) / len(durations),
                'shortest_duration_days': min(durations),
                'longest_duration_days':  max(durations),
                'total_holiday_days':     sum(durations),
            }

            breaks = holidays_with_end.filter(holiday_type='SCHOOL_BREAK')
            if breaks.exists():
                break_durations = [b.duration_days for b in breaks]
                stats['break_duration_analysis'] = {
                    'average_break_days': sum(break_durations) / len(break_durations),
                    'shortest_break_days': min(break_durations),
                    'longest_break_days':  max(break_durations),
                    'total_break_days':    sum(break_durations),
                }

    current_date = timezone.now().date()
    stats['upcoming'] = {
        'next_7_days': holidays.filter(
            start_date__gte=current_date,
            start_date__lte=current_date + timedelta(days=7),
        ).count(),
        'next_30_days': holidays.filter(
            start_date__gte=current_date,
            start_date__lte=current_date + timedelta(days=30),
        ).count(),
        'next_90_days': holidays.filter(
            start_date__gte=current_date,
            start_date__lte=current_date + timedelta(days=90),
        ).count(),
    }

    # Convenience keys used by some frontend templates
    stats['upcoming_holidays'] = stats['upcoming']['next_30_days']
    stats['total_breaks']      = holidays.filter(holiday_type='SCHOOL_BREAK').count()
    stats['total_days']        = (
        stats.get('duration_analysis', {}).get('total_holiday_days', 0)
    )

    return stats


# =============================================================================
# SUBJECT STATISTICS
# =============================================================================

def get_subject_statistics(filters=None):
    """
    Comprehensive statistics for subjects.

    Args:
        filters (dict, optional):
            subject_type    – filter by type string
            is_active       – bool
            is_compulsory   – bool
            department      – department PK
            difficulty_level – string

    Returns:
        dict
    """
    from .models import Subject, ClassSubject

    subjects = Subject.objects.all()

    if filters:
        if filters.get('subject_type'):
            subjects = subjects.filter(subject_type=filters['subject_type'])
        if filters.get('is_active') is not None:
            subjects = subjects.filter(is_active=filters['is_active'])
        if filters.get('is_compulsory') is not None:
            subjects = subjects.filter(is_compulsory=filters['is_compulsory'])
        if filters.get('department'):
            subjects = subjects.filter(department_id=filters['department'])
        if filters.get('difficulty_level'):
            subjects = subjects.filter(difficulty_level=filters['difficulty_level'])

    subjects = subjects.annotate(
        class_count=Count('classes', distinct=True),
        active_class_count=Count(
            'classes',
            filter=Q(classes__is_active=True),
            distinct=True,
        ),
    )

    total_subjects = subjects.count()

    stats = {
        'total_subjects':    total_subjects,
        'active_subjects':   subjects.filter(is_active=True).count(),
        'inactive_subjects': subjects.filter(is_active=False).count(),
        'compulsory_subjects': subjects.filter(is_compulsory=True).count(),
        'optional_subjects':   subjects.filter(is_compulsory=False).count(),

        'by_type': dict(
            subjects.values('subject_type')
            .annotate(count=Count('id'))
            .order_by('-count')
            .values_list('subject_type', 'count')
        ),

        'by_difficulty': dict(
            subjects.values('difficulty_level')
            .annotate(count=Count('id'))
            .values_list('difficulty_level', 'count')
        ),

        'by_department': dict(
            subjects.exclude(department__isnull=True)
            .values('department__name')
            .annotate(count=Count('id'))
            .order_by('-count')
            .values_list('department__name', 'count')
        ),

        'usage_stats': {
            'used_in_classes':          subjects.filter(class_count__gt=0).count(),
            'not_used':                 subjects.filter(class_count=0).count(),
            'total_class_assignments':  ClassSubject.objects.count(),
            'average_classes_per_subject': (
                subjects.aggregate(avg=Avg('class_count'))['avg'] or 0
            ),
        },
    }

    if total_subjects > 0:
        credit_data = subjects.aggregate(
            avg_credit=Avg('credit_hours'),
            min_credit=Min('credit_hours'),
            max_credit=Max('credit_hours'),
            total_credit=Sum('credit_hours'),
        )
        stats['credit_analysis'] = {
            'average_credit_hours': float(credit_data['avg_credit'] or 0),
            'minimum_credit_hours': float(credit_data['min_credit'] or 0),
            'maximum_credit_hours': float(credit_data['max_credit'] or 0),
            'total_credit_hours':   float(credit_data['total_credit'] or 0),
        }

        pass_mark_data = subjects.aggregate(
            avg_pass=Avg('pass_mark'),
            min_pass=Min('pass_mark'),
            max_pass=Max('pass_mark'),
        )
        stats['pass_mark_analysis'] = {
            'average_pass_mark': float(pass_mark_data['avg_pass'] or 0),
            'minimum_pass_mark': float(pass_mark_data['min_pass'] or 0),
            'maximum_pass_mark': float(pass_mark_data['max_pass'] or 0),
        }

    most_used = subjects.order_by('-class_count')[:10]
    stats['most_used_subjects'] = [
        {
            'id':                s.id,
            'name':              s.name,
            'abbreviation':      s.abbreviation,
            'class_count':       s.class_count,
            'active_class_count': s.active_class_count,
        }
        for s in most_used
    ]

    stats['unused_active_subjects'] = subjects.filter(
        class_count=0, is_active=True
    ).count()

    stats['textbook_stats'] = {
        'requires_textbook': subjects.filter(textbook_required=True).count(),
        'no_textbook':       subjects.filter(textbook_required=False).count(),
    }

    return stats


# =============================================================================
# ACADEMIC LEVEL STATISTICS
# =============================================================================

def get_academic_level_statistics(filters=None):
    """
    Comprehensive statistics for academic levels.

    Args:
        filters (dict, optional):
            is_active           – bool
            has_sections        – bool
            is_graduation_level – bool

    Returns:
        dict
    """
    from .models import AcademicLevel, Class

    levels = AcademicLevel.objects.all()

    if filters:
        if filters.get('is_active') is not None:
            levels = levels.filter(is_active=filters['is_active'])
        if filters.get('has_sections') is not None:
            levels = levels.filter(has_sections=filters['has_sections'])
        if filters.get('is_graduation_level') is not None:
            levels = levels.filter(
                is_graduation_level=filters['is_graduation_level']
            )

    levels = levels.annotate(
        class_count=Count('classes', distinct=True),
        active_class_count=Count(
            'classes',
            filter=Q(classes__is_active=True),
            distinct=True,
        ),
    )

    total_levels = levels.count()

    stats = {
        'total_levels':              total_levels,
        'active_levels':             levels.filter(is_active=True).count(),
        'inactive_levels':           levels.filter(is_active=False).count(),
        'levels_with_sections':      levels.filter(has_sections=True).count(),
        'levels_without_sections':   levels.filter(has_sections=False).count(),
        'graduation_levels':         levels.filter(is_graduation_level=True).count(),

        'class_stats': {
            'levels_with_classes':    levels.filter(class_count__gt=0).count(),
            'levels_without_classes': levels.filter(class_count=0).count(),
            'total_classes':          Class.objects.count(),
            'average_classes_per_level': (
                levels.aggregate(avg=Avg('class_count'))['avg'] or 0
            ),
        },
    }

    try:
        from students.models import Student
        level_enrollment = []
        for level in levels:
            count = Student.objects.filter(
                current_academic_level=level,
                enrollment_status='ACTIVE',
            ).count()
            level_enrollment.append({
                'level_id':        level.id,
                'level_name':      level.name,
                'enrollment_count': count,
                'class_count':     level.class_count,
                'has_sections':    level.has_sections,
            })

        stats['enrollment_by_level'] = sorted(
            level_enrollment,
            key=lambda x: x['enrollment_count'],
            reverse=True,
        )
        stats['total_enrollment'] = sum(
            l['enrollment_count'] for l in level_enrollment
        )
    except ImportError:
        pass

    stats['progression_stats'] = {
        'levels_with_next_level': levels.exclude(next_level__isnull=True).count(),
        'terminal_levels':        levels.filter(next_level__isnull=True).count(),
    }

    if total_levels > 0:
        order_data = levels.aggregate(
            min_order=Min('order'), max_order=Max('order')
        )
        if order_data['min_order'] is not None:
            stats['order_range'] = {
                'first_level_order':       order_data['min_order'],
                'last_level_order':        order_data['max_order'],
                'total_progression_steps': (
                    order_data['max_order'] - order_data['min_order'] + 1
                ),
            }

    most_populated = levels.order_by('-class_count', 'order')[:5]
    stats['most_populated_levels'] = [
        {
            'id':                l.id,
            'name':              l.name,
            'order':             l.order,
            'class_count':       l.class_count,
            'active_class_count': l.active_class_count,
            'has_sections':      l.has_sections,
        }
        for l in most_populated
    ]

    return stats


# =============================================================================
# CLASSROOM STATISTICS
# =============================================================================

def get_classroom_statistics(filters=None):
    """
    Comprehensive statistics for classrooms.

    Args:
        filters (dict, optional):
            room_type  – room type string
            building   – building name string
            is_active  – bool
            is_bookable – bool

    Returns:
        dict
    """
    from .models import ClassRoom, Class

    classrooms = ClassRoom.objects.all()

    if filters:
        if filters.get('room_type'):
            classrooms = classrooms.filter(room_type=filters['room_type'])
        if filters.get('building'):
            classrooms = classrooms.filter(building=filters['building'])
        if filters.get('is_active') is not None:
            classrooms = classrooms.filter(is_active=filters['is_active'])
        if filters.get('is_bookable') is not None:
            classrooms = classrooms.filter(is_bookable=filters['is_bookable'])

    classrooms = classrooms.annotate(
        assigned_class_count=Count('assigned_classes', distinct=True),
        active_assigned_count=Count(
            'assigned_classes',
            filter=Q(assigned_classes__is_active=True),
            distinct=True,
        ),
    )

    total_classrooms = classrooms.count()

    stats = {
        'total_classrooms':    total_classrooms,
        'active_classrooms':   classrooms.filter(is_active=True).count(),
        'inactive_classrooms': classrooms.filter(is_active=False).count(),
        'bookable_classrooms':     classrooms.filter(is_bookable=True).count(),
        'non_bookable_classrooms': classrooms.filter(is_bookable=False).count(),

        'by_type': dict(
            classrooms.values('room_type')
            .annotate(count=Count('id'))
            .order_by('-count')
            .values_list('room_type', 'count')
        ),

        'by_building': dict(
            classrooms.exclude(building='')
            .values('building')
            .annotate(count=Count('id'))
            .order_by('-count')
            .values_list('building', 'count')
        ),

        'by_floor': dict(
            classrooms.exclude(floor='')
            .values('floor')
            .annotate(count=Count('id'))
            .order_by('floor')
            .values_list('floor', 'count')
        ),

        'assignment_stats': {
            'assigned_classrooms':   classrooms.filter(
                assigned_class_count__gt=0
            ).count(),
            'unassigned_classrooms': classrooms.filter(
                assigned_class_count=0
            ).count(),
            'total_assignments': Class.objects.exclude(
                classroom__isnull=True
            ).count(),
        },
    }

    if total_classrooms > 0:
        cap = classrooms.aggregate(
            total_capacity=Sum('capacity'),
            avg_capacity=Avg('capacity'),
            min_capacity=Min('capacity'),
            max_capacity=Max('capacity'),
        )
        stats['capacity_analysis'] = {
            'total_capacity':   cap['total_capacity'] or 0,
            'average_capacity': float(cap['avg_capacity'] or 0),
            'smallest_capacity': cap['min_capacity'] or 0,
            'largest_capacity':  cap['max_capacity'] or 0,
        }
        stats['capacity_distribution'] = {
            'small_rooms':     classrooms.filter(capacity__lte=20).count(),
            'medium_rooms':    classrooms.filter(capacity__gt=20, capacity__lte=40).count(),
            'large_rooms':     classrooms.filter(capacity__gt=40, capacity__lte=100).count(),
            'very_large_rooms': classrooms.filter(capacity__gt=100).count(),
        }

    stats['facilities'] = {
        'with_projector':    classrooms.filter(has_projector=True).count(),
        'with_computer':     classrooms.filter(has_computer=True).count(),
        'with_ac':           classrooms.filter(has_air_conditioning=True).count(),
        'with_whiteboard':   classrooms.filter(has_whiteboard=True).count(),
        'with_smart_board':  classrooms.filter(has_smart_board=True).count(),
        'with_internet':     classrooms.filter(has_internet=True).count(),
        'with_sound_system': classrooms.filter(has_sound_system=True).count(),
        'accessible':        classrooms.filter(is_accessible=True).count(),
    }

    most_used = classrooms.order_by('-assigned_class_count')[:10]
    stats['most_used_classrooms'] = [
        {
            'id':                  c.id,
            'name':                c.name,
            'room_number':         c.room_number,
            'building':            c.building,
            'capacity':            c.capacity,
            'assigned_count':      c.assigned_class_count,
            'active_assigned_count': c.active_assigned_count,
        }
        for c in most_used
    ]

    stats['underutilized_classrooms'] = classrooms.filter(
        is_active=True, assigned_class_count=0
    ).count()

    return stats


# =============================================================================
# CLASS STATISTICS
# =============================================================================

def get_class_statistics(filters=None):
    """
    Comprehensive statistics for classes.

    Args:
        filters (dict, optional):
            academic_level   – level PK
            academic_session – session PK
            class_teacher    – teacher PK
            is_active        – bool

    Returns:
        dict
    """
    from .models import Class, ClassSubject

    try:
        from students.models import StudentClassEnrollment
        has_enrollment_model = True
    except ImportError:
        has_enrollment_model = False

    classes = Class.objects.all()

    if filters:
        if filters.get('academic_level'):
            classes = classes.filter(academic_level_id=filters['academic_level'])
        if filters.get('academic_session'):
            classes = classes.filter(academic_session_id=filters['academic_session'])
        if filters.get('class_teacher'):
            classes = classes.filter(class_teacher_id=filters['class_teacher'])
        if filters.get('is_active') is not None:
            classes = classes.filter(is_active=filters['is_active'])

    classes = classes.annotate(
        subject_count=Count('subjects', distinct=True),
        active_subject_count=Count(
            'subjects',
            filter=Q(subjects__is_active=True),
            distinct=True,
        ),
    )

    total_classes = classes.count()

    # by_session — correct aggregation (was broken in original)
    by_session_raw = (
        classes
        .values('academic_session__year_name', 'academic_session__term_name')
        .annotate(count=Count('id'))
        .order_by('academic_session__year_name', 'academic_session__term_name')
    )
    by_session = {}
    for row in by_session_raw:
        year = row['academic_session__year_name']
        term = row['academic_session__term_name']
        by_session.setdefault(year, {})[term] = row['count']

    # by_level — correct aggregation (was broken in original)
    by_level = dict(
        classes
        .values('academic_level__name')
        .annotate(count=Count('id'))
        .order_by('academic_level__name')
        .values_list('academic_level__name', 'count')
    )

    stats = {
        'total_classes':   total_classes,
        'active_classes':  classes.filter(is_active=True).count(),
        'inactive_classes': classes.filter(is_active=False).count(),
        'by_session':      by_session,
        'by_level':        by_level,

        'section_stats': {
            'classes_with_sections':    classes.exclude(section__isnull=True).exclude(section='').count(),
            'classes_without_sections': classes.filter(Q(section__isnull=True) | Q(section='')).count(),
        },

        'subject_stats': {
            'classes_with_subjects':    classes.filter(subject_count__gt=0).count(),
            'classes_without_subjects': classes.filter(subject_count=0).count(),
            'total_subject_assignments': ClassSubject.objects.count(),
            'average_subjects_per_class': (
                classes.aggregate(avg=Avg('subject_count'))['avg'] or 0
            ),
        },

        'teacher_stats': {
            'classes_with_teacher':    classes.exclude(class_teacher__isnull=True).count(),
            'classes_without_teacher': classes.filter(class_teacher__isnull=True).count(),
            'classes_with_assistant':  classes.exclude(assistant_teacher__isnull=True).count(),
        },

        'classroom_stats': {
            'classes_with_classroom':    classes.exclude(classroom__isnull=True).count(),
            'classes_without_classroom': classes.filter(classroom__isnull=True).count(),
        },
    }

    if total_classes > 0:
        cap = classes.aggregate(
            total_max_students=Sum('max_students'),
            avg_max_students=Avg('max_students'),
            min_max_students=Min('max_students'),
            max_max_students=Max('max_students'),
        )
        stats['capacity_analysis'] = {
            'total_capacity':   cap['total_max_students'] or 0,
            'average_capacity': float(cap['avg_max_students'] or 0),
            'smallest_capacity': cap['min_max_students'] or 0,
            'largest_capacity':  cap['max_max_students'] or 0,
        }

    if has_enrollment_model and total_classes > 0:
        enrollment_data = []
        total_enrolled  = 0
        for cls in classes:
            enrolled  = cls.get_current_enrollment_count()
            total_enrolled += enrolled
            occupancy = (enrolled / cls.max_students * 100) if cls.max_students else 0
            enrollment_data.append({
                'class_id':            cls.id,
                'class_name':          cls.name,
                'enrolled':            enrolled,
                'capacity':            cls.max_students,
                'occupancy_percentage': occupancy,
            })

        n = len(enrollment_data)
        stats['enrollment_analysis'] = {
            'total_enrolled_students':  total_enrolled,
            'average_enrollment_per_class': total_enrolled / total_classes,
            'classes_at_capacity':   sum(1 for e in enrollment_data if e['occupancy_percentage'] >= 100),
            'classes_over_capacity': sum(1 for e in enrollment_data if e['occupancy_percentage'] > 100),
            'classes_underutilized': sum(1 for e in enrollment_data if e['occupancy_percentage'] < 50),
            'average_occupancy_percentage': (
                sum(e['occupancy_percentage'] for e in enrollment_data) / n if n else 0
            ),
            'most_populated_classes': sorted(
                enrollment_data, key=lambda x: x['enrolled'], reverse=True
            )[:10],
        }

    classes_with_perf = classes.exclude(class_average_score__isnull=True)
    if classes_with_perf.exists():
        perf = classes_with_perf.aggregate(
            avg_score=Avg('class_average_score'),
            min_score=Min('class_average_score'),
            max_score=Max('class_average_score'),
        )
        stats['performance_analysis'] = {
            'classes_with_data': classes_with_perf.count(),
            'average_class_score': float(perf['avg_score'] or 0),
            'lowest_average':      float(perf['min_score'] or 0),
            'highest_average':     float(perf['max_score'] or 0),
        }

    classes_with_att = classes.exclude(attendance_rate__isnull=True)
    if classes_with_att.exists():
        att = classes_with_att.aggregate(
            avg_rate=Avg('attendance_rate'),
            min_rate=Min('attendance_rate'),
            max_rate=Max('attendance_rate'),
        )
        stats['attendance_analysis'] = {
            'classes_with_data': classes_with_att.count(),
            'average_attendance_rate': float(att['avg_rate'] or 0),
            'lowest_rate':             float(att['min_rate'] or 0),
            'highest_rate':            float(att['max_rate'] or 0),
        }

    return stats


# =============================================================================
# CLASS SUBJECT STATISTICS
# =============================================================================

def get_class_subject_statistics(filters=None):
    """
    Comprehensive statistics for class-subject assignments.

    Args:
        filters (dict, optional):
            class_instance – class PK
            subject        – subject PK
            teacher        – teacher PK
            is_active      – bool
            is_optional    – bool

    Returns:
        dict
    """
    from .models import ClassSubject

    class_subjects = ClassSubject.objects.all()

    if filters:
        if filters.get('class_instance'):
            class_subjects = class_subjects.filter(
                class_instance_id=filters['class_instance']
            )
        if filters.get('subject'):
            class_subjects = class_subjects.filter(subject_id=filters['subject'])
        if filters.get('teacher'):
            class_subjects = class_subjects.filter(teacher_id=filters['teacher'])
        if filters.get('is_active') is not None:
            class_subjects = class_subjects.filter(is_active=filters['is_active'])
        if filters.get('is_optional') is not None:
            class_subjects = class_subjects.filter(is_optional=filters['is_optional'])

    total_assignments = class_subjects.count()

    stats = {
        'total_assignments':    total_assignments,
        'active_assignments':   class_subjects.filter(is_active=True).count(),
        'inactive_assignments': class_subjects.filter(is_active=False).count(),
        'compulsory_assignments': class_subjects.filter(is_optional=False).count(),
        'optional_assignments':   class_subjects.filter(is_optional=True).count(),

        'teacher_stats': {
            'assignments_with_teacher':    class_subjects.exclude(teacher__isnull=True).count(),
            'assignments_without_teacher': class_subjects.filter(teacher__isnull=True).count(),
        },

        'by_subject': dict(
            class_subjects.values('subject__name')
            .annotate(count=Count('id'))
            .order_by('-count')
            .values_list('subject__name', 'count')[:20]
        ),

        'by_level': dict(
            class_subjects.values('class_instance__academic_level__name')
            .annotate(count=Count('id'))
            .order_by('-count')
            .values_list('class_instance__academic_level__name', 'count')[:20]
        ),
    }

    if total_assignments > 0:
        hours = class_subjects.aggregate(
            total_hours_per_week=Sum('hours_per_week'),
            avg_hours_per_week=Avg('hours_per_week'),
            min_hours=Min('hours_per_week'),
            max_hours=Max('hours_per_week'),
            total_course_hours=Sum('total_hours'),
        )
        stats['hours_analysis'] = {
            'total_weekly_hours':   hours['total_hours_per_week'] or 0,
            'average_weekly_hours': float(hours['avg_hours_per_week'] or 0),
            'minimum_weekly_hours': hours['min_hours'] or 0,
            'maximum_weekly_hours': hours['max_hours'] or 0,
            'total_course_hours':   hours['total_course_hours'] or 0,
        }

        assessment = class_subjects.aggregate(
            avg_ca_weight=Avg('continuous_assessment_weight'),
            avg_exam_weight=Avg('final_exam_weight'),
        )
        stats['assessment_analysis'] = {
            'average_ca_weight':   float(assessment['avg_ca_weight'] or 0),
            'average_exam_weight': float(assessment['avg_exam_weight'] or 0),
        }
        stats['ca_weight_distribution'] = {
            'ca_dominant':   class_subjects.filter(continuous_assessment_weight__gt=50).count(),
            'exam_dominant': class_subjects.filter(final_exam_weight__gt=50).count(),
            'balanced':      class_subjects.filter(
                continuous_assessment_weight=50, final_exam_weight=50
            ).count(),
        }

    assignments_with_avg = class_subjects.exclude(class_average__isnull=True)
    if assignments_with_avg.exists():
        perf = assignments_with_avg.aggregate(
            avg_class_average=Avg('class_average'),
            min_average=Min('class_average'),
            max_average=Max('class_average'),
        )
        stats['performance_analysis'] = {
            'assignments_with_data': assignments_with_avg.count(),
            'overall_average': float(perf['avg_class_average'] or 0),
            'lowest_average':  float(perf['min_average'] or 0),
            'highest_average': float(perf['max_average'] or 0),
        }

    assignments_with_pr = class_subjects.exclude(pass_rate__isnull=True)
    if assignments_with_pr.exists():
        pr = assignments_with_pr.aggregate(
            avg_pass_rate=Avg('pass_rate'),
            min_pass_rate=Min('pass_rate'),
            max_pass_rate=Max('pass_rate'),
        )
        stats['pass_rate_analysis'] = {
            'assignments_with_data': assignments_with_pr.count(),
            'average_pass_rate': float(pr['avg_pass_rate'] or 0),
            'lowest_pass_rate':  float(pr['min_pass_rate'] or 0),
            'highest_pass_rate': float(pr['max_pass_rate'] or 0),
        }

    teacher_workload = (
        class_subjects.exclude(teacher__isnull=True)
        .values('teacher__staff__first_name', 'teacher__staff__last_name')
        .annotate(
            assignment_count=Count('id'),
            total_weekly_hours=Sum('hours_per_week'),
        )
        .order_by('-total_weekly_hours')[:10]
    )
    stats['teacher_workload'] = [
        {
            'teacher_name': (
                f"{t['teacher__staff__first_name']} {t['teacher__staff__last_name']}"
            ),
            'assignment_count':    t['assignment_count'],
            'total_weekly_hours':  t['total_weekly_hours'],
        }
        for t in teacher_workload
    ]

    return stats


# =============================================================================
# COMPREHENSIVE DASHBOARD STATISTICS
# =============================================================================

def get_academic_dashboard_statistics(filters=None):
    """
    Aggregate statistics across all academic models for the dashboard.

    NOTE: Do not call this from individual detail views — it runs 7 separate
    aggregation functions.  Detail views should build their own lightweight
    stats dicts using model properties.

    Args:
        filters (dict, optional): Passed through to each sub-function.

    Returns:
        dict
    """
    dashboard = {
        'generated_at':  timezone.now(),
        'sessions':      get_academic_session_statistics(filters),
        'subjects':      get_subject_statistics(filters),
        'levels':        get_academic_level_statistics(filters),
        'classes':       get_class_statistics(filters),
        'classrooms':    get_classroom_statistics(filters),
        'holidays':      get_holiday_statistics(filters),
        'class_subjects': get_class_subject_statistics(filters),
    }

    dashboard['summary'] = {
        'total_active_sessions': dashboard['sessions']['active_sessions'],
        'current_session_name':  (
            str(dashboard['sessions']['current_session'])
            if dashboard['sessions']['current_session'] else None
        ),
        'total_subjects':    dashboard['subjects']['total_subjects'],
        'total_levels':      dashboard['levels']['total_levels'],
        'total_classes':     dashboard['classes']['total_classes'],
        'total_classrooms':  dashboard['classrooms']['total_classrooms'],
        'total_holidays':    dashboard['holidays']['total_holidays'],
    }

    return dashboard


# =============================================================================
# ENROLMENT STATISTICS
# =============================================================================

def get_enrollment_statistics(filters=None):
    """
    Comprehensive enrolment statistics with optional filtering.

    Args:
        filters (dict, optional):
            academic_session  – AcademicSession instance
            academic_level    – AcademicLevel instance
            class_instance    – Class instance
            enrollment_type   – string
            completion_status – string
            is_active         – bool
            date_range        – tuple (start_date, end_date)

    Returns:
        dict  (returns minimal error dict on unexpected failure)
    """
    try:
        from .models import StudentClassEnrollment, Class, AcademicSession, AcademicLevel
        from students.models import Student

        enrollments = StudentClassEnrollment.objects.select_related(
            'student',
            'class_instance',
            'academic_session',
            'class_instance__academic_level',
        )

        if filters:
            if filters.get('academic_session'):
                enrollments = enrollments.filter(
                    academic_session=filters['academic_session']
                )
            if filters.get('academic_level'):
                enrollments = enrollments.filter(
                    class_instance__academic_level=filters['academic_level']
                )
            if filters.get('class_instance'):
                enrollments = enrollments.filter(
                    class_instance=filters['class_instance']
                )
            if filters.get('enrollment_type'):
                enrollments = enrollments.filter(
                    enrollment_type=filters['enrollment_type']
                )
            if filters.get('completion_status'):
                enrollments = enrollments.filter(
                    completion_status=filters['completion_status']
                )
            if filters.get('is_active') is not None:
                enrollments = enrollments.filter(is_active=filters['is_active'])
            if filters.get('date_range'):
                start_date, end_date = filters['date_range']
                enrollments = enrollments.filter(
                    enrollment_date__gte=start_date,
                    enrollment_date__lte=end_date,
                )

        # ── Overview ──────────────────────────────────────────────────────
        total_enrollments    = enrollments.count()
        active_enrollments   = enrollments.filter(is_active=True).count()
        ongoing_enrollments  = enrollments.filter(completion_status='ONGOING').count()
        completed_enrollments = enrollments.filter(completion_status='COMPLETED').count()

        overview = {
            'total_enrollments':    total_enrollments,
            'active_enrollments':   active_enrollments,
            'ongoing_enrollments':  ongoing_enrollments,
            'completed_enrollments': completed_enrollments,
            'inactive_enrollments': total_enrollments - active_enrollments,
            'active_percentage': round(
                active_enrollments / total_enrollments * 100, 1
            ) if total_enrollments else 0,
            'completion_rate': round(
                completed_enrollments / total_enrollments * 100, 1
            ) if total_enrollments else 0,
        }

        # ── Status breakdown ──────────────────────────────────────────────
        status_stats = {}
        for row in enrollments.values('completion_status').annotate(count=Count('id')):
            pct = round(row['count'] / total_enrollments * 100, 1) if total_enrollments else 0
            status_stats[row['completion_status']] = {
                'count':      row['count'],
                'percentage': pct,
            }

        # ── Enrollment type breakdown ─────────────────────────────────────
        type_stats = {}
        for row in enrollments.values('enrollment_type').annotate(count=Count('id')):
            pct = round(row['count'] / total_enrollments * 100, 1) if total_enrollments else 0
            type_stats[row['enrollment_type']] = {
                'count':      row['count'],
                'percentage': pct,
            }

        # ── Session breakdown ─────────────────────────────────────────────
        session_breakdown = list(
            enrollments.values(
                'academic_session__year_name',
                'academic_session__term_name',
                session_id=F('academic_session__id'),
            )
            .annotate(
                count=Count('id'),
                active_count=Count('id', filter=Q(is_active=True)),
                ongoing_count=Count('id', filter=Q(completion_status='ONGOING')),
            )
            .order_by('-count')[:10]
        )

        # ── Level breakdown ───────────────────────────────────────────────
        level_breakdown = list(
            enrollments.values(
                'class_instance__academic_level__name',
                'class_instance__academic_level__order',
                level_id=F('class_instance__academic_level__id'),
            )
            .annotate(
                count=Count('id'),
                active_count=Count('id', filter=Q(is_active=True)),
                ongoing_count=Count('id', filter=Q(completion_status='ONGOING')),
            )
            .order_by('class_instance__academic_level__order')
        )

        # ── Capacity analysis ─────────────────────────────────────────────
        class_analysis = Class.objects.annotate(
            total_enrollments=Count('enrollments'),
            active_enrollments=Count(
                'enrollments', filter=Q(enrollments__is_active=True)
            ),
            ongoing_enrollments=Count(
                'enrollments',
                filter=Q(enrollments__completion_status='ONGOING'),
            ),
        ).filter(total_enrollments__gt=0)

        totals = class_analysis.aggregate(
            total_capacity=Sum('max_students'),
            total_enrolled=Sum('active_enrollments'),
            avg_utilization=Avg(
                Case(
                    When(max_students=0, then=0),
                    default=F('active_enrollments') * 100.0 / F('max_students'),
                    output_field=FloatField(),
                )
            ),
        )

        total_cap     = totals['total_capacity'] or 0
        total_enr     = totals['total_enrolled'] or 0
        capacity_stats = {
            'total_class_capacity':    total_cap,
            'total_students_enrolled': total_enr,
            'available_capacity':      total_cap - total_enr,
            'average_utilization':     round(totals['avg_utilization'] or 0, 1),
            'utilization_percentage':  round(
                total_enr / total_cap * 100, 1
            ) if total_cap else 0,
        }

        # Capacity distribution buckets
        util_annotation = Case(
            When(max_students=0, then=0),
            default=F('active_enrollments') * 100.0 / F('max_students'),
            output_field=FloatField(),
        )
        capacity_distribution = {
            'at_capacity':      class_analysis.annotate(u=util_annotation).filter(u__gte=100).count(),
            'high_utilization': class_analysis.annotate(u=util_annotation).filter(u__gte=80, u__lt=100).count(),
            'medium_utilization': class_analysis.annotate(u=util_annotation).filter(u__gte=50, u__lt=80).count(),
            'low_utilization':  class_analysis.annotate(u=util_annotation).filter(u__lt=50).count(),
        }

        # ── Enrolment trends (last 30 days) ────────────────────────────────
        today            = get_school_today()
        thirty_days_ago  = today - timedelta(days=30)
        recent           = enrollments.filter(enrollment_date__gte=thirty_days_ago)

        # Use TruncDate (database-agnostic) instead of legacy .extra()
        daily_trend = list(
            recent
            .annotate(day=TruncDate('enrollment_date'))
            .values('day')
            .annotate(count=Count('id'))
            .order_by('day')
        )
        # Convert date objects to strings for JSON safety
        for row in daily_trend:
            if row['day']:
                row['day'] = row['day'].strftime('%Y-%m-%d')

        trends = {
            'recent_enrollments_count': recent.count(),
            'daily_average':            round(recent.count() / 30, 1),
            'daily_trend':              daily_trend,
        }

        # ── Student progression ───────────────────────────────────────────
        student_progression = Student.objects.annotate(
            total_enr=Count('class_enrollments'),
            active_enr=Count(
                'class_enrollments',
                filter=Q(class_enrollments__is_active=True),
            ),
            completed_enr=Count(
                'class_enrollments',
                filter=Q(class_enrollments__completion_status='COMPLETED'),
            ),
        ).aggregate(
            students_never_enrolled=Count('id', filter=Q(total_enr=0)),
            students_currently_enrolled=Count('id', filter=Q(active_enr__gt=0)),
            students_with_completions=Count('id', filter=Q(completed_enr__gt=0)),
            avg_enrollments_per_student=Avg('total_enr'),
        )

        # ── Gender breakdown ──────────────────────────────────────────────
        gender_stats = {}
        for row in enrollments.values('student__gender').annotate(
            count=Count('id'),
            active_count=Count('id', filter=Q(is_active=True)),
        ):
            # Explicit None check — empty string is a valid stored gender value
            if row['student__gender'] is not None:
                gender_stats[row['student__gender']] = {
                    'total':  row['count'],
                    'active': row['active_count'],
                }

        # ── Recent activity ────────────────────────────────────────────────
        recent_activity = {
            'recent_enrollments': list(
                enrollments.order_by('-created_at')[:5]
            ),
            'recent_completions': list(
                enrollments.filter(
                    completion_status__in=['COMPLETED', 'GRADUATED']
                ).order_by('-completion_date')[:5]
            ),
            'recent_withdrawals': list(
                enrollments.filter(
                    completion_status__in=['WITHDRAWN', 'TRANSFERRED']
                ).order_by('-completion_date')[:5]
            ),
        }

        return {
            'overview':                   overview,
            'status_breakdown':           status_stats,
            'enrollment_type_breakdown':  type_stats,
            'academic_session_breakdown': session_breakdown,
            'academic_level_breakdown':   level_breakdown,
            'capacity_analysis':          capacity_stats,
            'capacity_distribution':      capacity_distribution,
            'enrollment_trends':          trends,
            'student_progression':        student_progression,
            'gender_breakdown':           gender_stats,
            'recent_activity':            recent_activity,
            'metadata': {
                'last_updated':          get_school_current_time(),
                'total_records_analyzed': total_enrollments,
                'filters_applied':        filters or {},
                'calculation_date':       today,
            },
        }

    except Exception as e:
        logger.error(f"Error calculating enrolment statistics: {e}", exc_info=True)
        return {
            'overview': {
                'total_enrollments':    0,
                'active_enrollments':   0,
                'ongoing_enrollments':  0,
                'completed_enrollments': 0,
                'active_percentage':    0,
                'completion_rate':      0,
            },
            'error': str(e),
            'metadata': {
                'last_updated': get_school_current_time(),
                'has_error':    True,
            },
        }


# =============================================================================
# CONVENIENCE WRAPPERS
# =============================================================================

def get_enrollment_summary_by_session(academic_session):
    """Active enrolment summary for a specific academic session."""
    return get_enrollment_statistics({
        'academic_session': academic_session,
        'is_active':        True,
    })


def get_enrollment_summary_by_level(academic_level):
    """Enrolment summary for a specific academic level."""
    return get_enrollment_statistics({'academic_level': academic_level})


def get_current_enrollment_statistics():
    """Enrolment statistics for currently active, ONGOING enrolments only."""
    return get_enrollment_statistics({
        'is_active':        True,
        'completion_status': 'ONGOING',
    })


def get_enrollment_trends(days=30):
    """
    Enrolment statistics filtered to the most recent N days.

    Args:
        days (int): Look-back window (default 30).
    """
    today = get_school_today()
    return get_enrollment_statistics({
        'date_range': (today - timedelta(days=days), today)
    })


def get_class_enrollment_analysis(class_instance):
    """
    Detailed enrolment analysis for a single class.

    Unlike get_enrollment_statistics(), this function focuses entirely on
    one class and does not run the full aggregation pipeline — it is
    appropriate for use in detail views.

    Args:
        class_instance (Class): The class to analyse.

    Returns:
        dict
    """
    from .models import StudentClassEnrollment

    try:
        enrollments = StudentClassEnrollment.objects.filter(
            class_instance=class_instance
        ).select_related('student')

        total  = enrollments.count()
        active = enrollments.filter(is_active=True).count()

        status_breakdown = {
            row['completion_status']: row['count']
            for row in enrollments.values('completion_status').annotate(count=Count('id'))
        }
        gender_breakdown = {
            row['student__gender']: row['count']
            for row in enrollments.values('student__gender').annotate(count=Count('id'))
            if row['student__gender'] is not None
        }

        return {
            'class':                str(class_instance),
            'total_enrollments':    total,
            'active_enrollments':   active,
            'capacity':             class_instance.max_students,
            'available_spots':      max(0, class_instance.max_students - active),
            'utilization_percentage': round(
                active / class_instance.max_students * 100, 1
            ) if class_instance.max_students else 0,
            'status_breakdown':     status_breakdown,
            'gender_breakdown':     gender_breakdown,
            'has_capacity':         active < class_instance.max_students,
            'is_at_capacity':       active >= class_instance.max_students,
        }

    except Exception as e:
        logger.error(f"Error analysing class enrolment: {e}")
        return {
            'class':             str(class_instance),
            'error':             str(e),
            'total_enrollments': 0,
            'active_enrollments': 0,
        }


# =============================================================================
# EXPORT HELPER
# =============================================================================

def format_statistics_for_export(stats, format_type='dict'):
    """
    Format a statistics dict for export (JSON, flat CSV, etc.).

    Args:
        stats (dict):       Statistics dictionary to format.
        format_type (str):  'dict' | 'flat' | 'hierarchical'

    Returns:
        dict or list
    """
    if format_type == 'flat':
        flat = {}

        def _flatten(d, prefix=''):
            for k, v in d.items():
                key = f"{prefix}.{k}" if prefix else k
                if isinstance(v, dict):
                    _flatten(v, key)
                else:
                    flat[key] = v

        _flatten(stats)
        return flat

    if format_type == 'hierarchical':
        def _clean(d):
            out = {}
            for k, v in d.items():
                if isinstance(v, dict):
                    out[k] = _clean(v)
                elif isinstance(v, (list, tuple)):
                    out[k] = [_clean(i) if isinstance(i, dict) else i for i in v]
                elif hasattr(v, 'isoformat'):
                    out[k] = v.isoformat()
                else:
                    out[k] = v
            return out

        return _clean(stats)

    return stats