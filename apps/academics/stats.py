# academics/stats.py
"""
Comprehensive statistics utility functions for Academic models
Similar to students statistics pattern
"""

from django.utils import timezone
from django.db.models import Count, Q, Avg, Sum, Max, Min, F, Case, When, IntegerField, FloatField, DecimalField
from django.db.models.functions import TruncMonth, TruncYear, TruncWeek, TruncDate
from datetime import timedelta, date
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# ACADEMIC SESSION STATISTICS
# =============================================================================

def get_academic_session_statistics(filters=None):
    """
    Get comprehensive statistics for academic sessions
    
    Args:
        filters (dict): Optional filters to apply
            - year_name: Filter by specific academic year
            - period_type: Filter by period type
            - is_active: Filter by active status
            - is_current: Filter by current status
            - date_range: Tuple of (start_date, end_date)
    
    Returns:
        dict: Statistics including counts, durations, status breakdowns
    """
    from .models import AcademicSession
    
    sessions = AcademicSession.objects.all()
    
    # Apply filters
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
    
    # Basic counts
    total_sessions = sessions.count()
    current_date = timezone.now().date()
    
    stats = {
        'total_sessions': total_sessions,
        'active_sessions': sessions.filter(is_active=True).count(),
        'inactive_sessions': sessions.filter(is_active=False).count(),
        'current_session': sessions.filter(is_current=True).first(),
        'closed_sessions': sessions.filter(is_closed=True).count(),
        'open_sessions': sessions.filter(is_closed=False).count(),
        
        # Status breakdown
        'status_breakdown': {
            'current': sessions.filter(is_current=True).count(),
            'upcoming': sessions.filter(start_date__gt=current_date, is_active=True).count(),
            'ongoing': sessions.filter(
                start_date__lte=current_date,
                end_date__gte=current_date,
                is_active=True,
                is_current=False
            ).count(),
            'completed': sessions.filter(end_date__lt=current_date, is_closed=False).count(),
            'closed': sessions.filter(is_closed=True).count(),
        },
        
        # Period type distribution
        'by_period_type': dict(
            sessions.values('period_type')
            .annotate(count=Count('id'))
            .values_list('period_type', 'count')
        ),
        
        # Promotion statistics
        'promotion_stats': {
            'allows_promotion': sessions.filter(allows_promotion=True).count(),
            'promotion_done': sessions.filter(promotion_done=True).count(),
            'promotion_pending': sessions.filter(
                allows_promotion=True, 
                promotion_done=False
            ).count(),
        },
        
        # Academic year distribution
        'by_year': dict(
            sessions.values('year_name')
            .annotate(count=Count('id'))
            .order_by('-year_name')
            .values_list('year_name', 'count')
        ),
        
        # Enrollment statistics
        'enrollment_stats': {
            'open_for_enrollment': sessions.filter(
                is_active=True,
                is_closed=False
            ).count(),
            'past_deadline': sessions.filter(
                enrollment_deadline__lt=current_date,
                late_enrollment_allowed=False
            ).count(),
            'allows_late_enrollment': sessions.filter(late_enrollment_allowed=True).count(),
        },
    }
    
    # Duration analysis
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
                'average_duration_days': sum(durations) / len(durations) if durations else 0,
                'shortest_duration_days': min(durations) if durations else 0,
                'longest_duration_days': max(durations) if durations else 0,
                'total_academic_days': sum(durations),
            }
        
        # Progress analysis for active sessions
        active_sessions = sessions.filter(is_active=True, is_closed=False)
        if active_sessions.exists():
            progress_data = []
            for session in active_sessions:
                if session.total_days > 0:
                    progress_data.append({
                        'session': str(session),
                        'progress_percentage': session.progress_percentage,
                        'days_elapsed': session.days_elapsed,
                        'days_remaining': session.days_remaining,
                    })
            
            stats['progress_analysis'] = progress_data
    
    # Recent activity
    stats['recent_activity'] = {
        'created_last_30_days': sessions.filter(
            created_at__gte=current_date - timedelta(days=30)
        ).count(),
        'modified_last_7_days': sessions.filter(
            updated_at__gte=current_date - timedelta(days=7)
        ).count(),
        'starting_next_30_days': sessions.filter(
            start_date__gte=current_date,
            start_date__lte=current_date + timedelta(days=30)
        ).count(),
        'ending_next_30_days': sessions.filter(
            end_date__gte=current_date,
            end_date__lte=current_date + timedelta(days=30)
        ).count(),
    }
    
    return stats


def get_session_timeline_data(year_name=None, include_breaks=True):
    """
    Get timeline data for session visualization
    
    Args:
        year_name (str): Optional year filter
        include_breaks (bool): Include break periods
    
    Returns:
        dict: Timeline data with sessions and optional breaks
    """
    from .models import AcademicSession, Holiday
    
    sessions = AcademicSession.objects.all().order_by('start_date')
    if year_name:
        sessions = sessions.filter(year_name=year_name)
    
    timeline = []
    
    for session in sessions:
        timeline.append({
            'type': 'session',
            'id': session.id,
            'name': session.name,
            'start_date': session.start_date,
            'end_date': session.end_date,
            'duration_days': session.total_days,
            'status': session.status_display,
            'is_current': session.is_current,
            'term_number': session.term_number,
            'year_name': session.year_name,
        })
    
    if include_breaks:
        breaks = Holiday.objects.filter(holiday_type='BREAK').order_by('start_date')
        if year_name:
            breaks = breaks.filter(
                Q(previous_session__year_name=year_name) |
                Q(next_session__year_name=year_name)
            )
        
        for holiday in breaks:
            timeline.append({
                'type': 'break',
                'id': holiday.id,
                'name': holiday.name,
                'start_date': holiday.start_date,
                'end_date': holiday.end_date,
                'duration_days': holiday.duration,
                'break_type': holiday.break_type,
            })
    
    # Sort by start date
    timeline.sort(key=lambda x: x['start_date'])
    
    return {
        'timeline': timeline,
        'total_items': len(timeline),
        'year_name': year_name,
    }


# =============================================================================
# HOLIDAY STATISTICS
# =============================================================================

def get_holiday_statistics(filters=None):
    """
    Get comprehensive statistics for holidays and breaks
    
    Args:
        filters (dict): Optional filters
            - holiday_type: Filter by type
            - break_type: Filter by break type
            - year: Filter by year
            - academic_session: Filter by session
    
    Returns:
        dict: Holiday statistics and analysis
    """
    from .models import Holiday
    
    holidays = Holiday.objects.all()
    
    # Apply filters
    if filters:
        if filters.get('holiday_type'):
            holidays = holidays.filter(holiday_type=filters['holiday_type'])
        if filters.get('break_type'):
            holidays = holidays.filter(break_type=filters['break_type'])
        if filters.get('year'):
            holidays = holidays.filter(start_date__year=filters['year'])
        if filters.get('academic_session'):
            holidays = holidays.filter(academic_session_id=filters['academic_session'])
    
    total_holidays = holidays.count()
    
    stats = {
        'total_holidays': total_holidays,
        
        # Type distribution
        'by_type': dict(
            holidays.values('holiday_type')
            .annotate(count=Count('id'))
            .values_list('holiday_type', 'count')
        ),
        
        # Break type distribution
        'by_break_type': dict(
            holidays.filter(holiday_type='BREAK')
            .values('break_type')
            .annotate(count=Count('id'))
            .values_list('break_type', 'count')
        ),
        
        # Year distribution
        'by_year': dict(
            holidays.annotate(year=TruncYear('start_date'))
            .values('year')
            .annotate(count=Count('id'))
            .order_by('-year')
            .values_list('year', 'count')
        ),
        
        # Monthly distribution
        'by_month': dict(
            holidays.annotate(month=TruncMonth('start_date'))
            .values('month')
            .annotate(count=Count('id'))
            .order_by('month')
            .values_list('month', 'count')
        ),
    }
    
    # Duration analysis
    if total_holidays > 0:
        holidays_with_end = holidays.exclude(end_date__isnull=True)
        
        if holidays_with_end.exists():
            durations = [h.duration for h in holidays_with_end]
            
            stats['duration_analysis'] = {
                'average_duration_days': sum(durations) / len(durations) if durations else 0,
                'shortest_duration_days': min(durations) if durations else 0,
                'longest_duration_days': max(durations) if durations else 0,
                'total_holiday_days': sum(durations),
            }
            
            # Break-specific analysis
            breaks = holidays_with_end.filter(holiday_type='BREAK')
            if breaks.exists():
                break_durations = [b.duration for b in breaks]
                stats['break_duration_analysis'] = {
                    'average_break_days': sum(break_durations) / len(break_durations),
                    'shortest_break_days': min(break_durations),
                    'longest_break_days': max(break_durations),
                    'total_break_days': sum(break_durations),
                }
    
    # Upcoming holidays
    current_date = timezone.now().date()
    stats['upcoming'] = {
        'next_7_days': holidays.filter(
            start_date__gte=current_date,
            start_date__lte=current_date + timedelta(days=7)
        ).count(),
        'next_30_days': holidays.filter(
            start_date__gte=current_date,
            start_date__lte=current_date + timedelta(days=30)
        ).count(),
        'next_90_days': holidays.filter(
            start_date__gte=current_date,
            start_date__lte=current_date + timedelta(days=90)
        ).count(),
    }
    
    return stats


# =============================================================================
# SUBJECT STATISTICS
# =============================================================================

def get_subject_statistics(filters=None):
    """
    Get comprehensive statistics for subjects
    
    Args:
        filters (dict): Optional filters
            - subject_type: Filter by type
            - is_active: Filter by active status
            - is_compulsory: Filter by compulsory status
            - department: Filter by department
            - difficulty_level: Filter by difficulty
    
    Returns:
        dict: Subject statistics and analysis
    """
    from .models import Subject, ClassSubject
    
    subjects = Subject.objects.all()
    
    # Apply filters
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
    
    # Annotate with usage counts
    subjects = subjects.annotate(
        class_count=Count('classes', distinct=True),
        active_class_count=Count(
            'classes',
            filter=Q(classes__is_active=True),
            distinct=True
        )
    )
    
    total_subjects = subjects.count()
    
    stats = {
        'total_subjects': total_subjects,
        'active_subjects': subjects.filter(is_active=True).count(),
        'inactive_subjects': subjects.filter(is_active=False).count(),
        'compulsory_subjects': subjects.filter(is_compulsory=True).count(),
        'optional_subjects': subjects.filter(is_compulsory=False).count(),
        
        # Type distribution
        'by_type': dict(
            subjects.values('subject_type')
            .annotate(count=Count('id'))
            .order_by('-count')
            .values_list('subject_type', 'count')
        ),
        
        # Difficulty distribution
        'by_difficulty': dict(
            subjects.values('difficulty_level')
            .annotate(count=Count('id'))
            .values_list('difficulty_level', 'count')
        ),
        
        # Department distribution
        'by_department': dict(
            subjects.exclude(department__isnull=True)
            .values('department__name')
            .annotate(count=Count('id'))
            .order_by('-count')
            .values_list('department__name', 'count')
        ),
        
        # Usage analysis
        'usage_stats': {
            'used_in_classes': subjects.filter(class_count__gt=0).count(),
            'not_used': subjects.filter(class_count=0).count(),
            'total_class_assignments': ClassSubject.objects.count(),
            'average_classes_per_subject': subjects.aggregate(
                avg=Avg('class_count')
            )['avg'] or 0,
        },
    }
    
    # Credit hours analysis
    if total_subjects > 0:
        credit_data = subjects.aggregate(
            avg_credit=Avg('credit_hours'),
            min_credit=Min('credit_hours'),
            max_credit=Max('credit_hours'),
            total_credit=Sum('credit_hours')
        )
        
        stats['credit_analysis'] = {
            'average_credit_hours': float(credit_data['avg_credit'] or 0),
            'minimum_credit_hours': float(credit_data['min_credit'] or 0),
            'maximum_credit_hours': float(credit_data['max_credit'] or 0),
            'total_credit_hours': float(credit_data['total_credit'] or 0),
        }
    
    # Pass mark analysis
    if total_subjects > 0:
        pass_mark_data = subjects.aggregate(
            avg_pass=Avg('pass_mark'),
            min_pass=Min('pass_mark'),
            max_pass=Max('pass_mark')
        )
        
        stats['pass_mark_analysis'] = {
            'average_pass_mark': float(pass_mark_data['avg_pass'] or 0),
            'minimum_pass_mark': float(pass_mark_data['min_pass'] or 0),
            'maximum_pass_mark': float(pass_mark_data['max_pass'] or 0),
        }
    
    # Most used subjects
    most_used = subjects.order_by('-class_count')[:10]
    stats['most_used_subjects'] = [
        {
            'id': s.id,
            'name': s.name,
            'abbreviation': s.abbreviation,
            'class_count': s.class_count,
            'active_class_count': s.active_class_count,
        }
        for s in most_used
    ]
    
    # Unused subjects
    unused = subjects.filter(class_count=0, is_active=True)
    stats['unused_active_subjects'] = unused.count()
    
    # Textbook requirements
    stats['textbook_stats'] = {
        'requires_textbook': subjects.filter(textbook_required=True).count(),
        'no_textbook': subjects.filter(textbook_required=False).count(),
    }
    
    return stats


# =============================================================================
# ACADEMIC LEVEL STATISTICS
# =============================================================================

def get_academic_level_statistics(filters=None):
    """
    Get comprehensive statistics for academic levels
    
    Args:
        filters (dict): Optional filters
            - is_active: Filter by active status
            - has_sections: Filter by section status
            - is_graduation_level: Filter by graduation status
    
    Returns:
        dict: Academic level statistics
    """
    from .models import AcademicLevel, Class
    try:
        from students.models import Student
        has_students_model = True
    except ImportError:
        has_students_model = False
    
    levels = AcademicLevel.objects.all()
    
    # Apply filters
    if filters:
        if filters.get('is_active') is not None:
            levels = levels.filter(is_active=filters['is_active'])
        if filters.get('has_sections') is not None:
            levels = levels.filter(has_sections=filters['has_sections'])
        if filters.get('is_graduation_level') is not None:
            levels = levels.filter(is_graduation_level=filters['is_graduation_level'])
    
    # Annotate with class counts
    levels = levels.annotate(
        class_count=Count('classes', distinct=True),
        active_class_count=Count(
            'classes',
            filter=Q(classes__is_active=True),
            distinct=True
        )
    )
    
    total_levels = levels.count()
    
    stats = {
        'total_levels': total_levels,
        'active_levels': levels.filter(is_active=True).count(),
        'inactive_levels': levels.filter(is_active=False).count(),
        'levels_with_sections': levels.filter(has_sections=True).count(),
        'levels_without_sections': levels.filter(has_sections=False).count(),
        'graduation_levels': levels.filter(is_graduation_level=True).count(),
        
        # Class distribution
        'class_stats': {
            'levels_with_classes': levels.filter(class_count__gt=0).count(),
            'levels_without_classes': levels.filter(class_count=0).count(),
            'total_classes': Class.objects.count(),
            'average_classes_per_level': levels.aggregate(
                avg=Avg('class_count')
            )['avg'] or 0,
        },
    }
    
    # Enrollment statistics (if Student model is available)
    if has_students_model:
        level_enrollment = []
        for level in levels:
            enrollment = Student.objects.filter(
                current_academic_level=level,
                enrollment_status='active'
            ).count()
            
            level_enrollment.append({
                'level_id': level.id,
                'level_name': level.name,
                'enrollment_count': enrollment,
                'class_count': level.class_count,
                'has_sections': level.has_sections,
            })
        
        stats['enrollment_by_level'] = sorted(
            level_enrollment,
            key=lambda x: x['enrollment_count'],
            reverse=True
        )
        
        stats['total_enrollment'] = sum(l['enrollment_count'] for l in level_enrollment)
    
    # Progression analysis
    levels_with_progression = levels.exclude(next_level__isnull=True)
    stats['progression_stats'] = {
        'levels_with_next_level': levels_with_progression.count(),
        'terminal_levels': levels.filter(next_level__isnull=True).count(),
    }
    
    # Order distribution
    if total_levels > 0:
        order_data = levels.aggregate(
            min_order=Min('order'),
            max_order=Max('order')
        )
        
        stats['order_range'] = {
            'first_level_order': order_data['min_order'],
            'last_level_order': order_data['max_order'],
            'total_progression_steps': order_data['max_order'] - order_data['min_order'] + 1,
        }
    
    # Most populated levels
    most_populated = levels.order_by('-class_count', 'order')[:5]
    stats['most_populated_levels'] = [
        {
            'id': l.id,
            'name': l.name,
            'order': l.order,
            'class_count': l.class_count,
            'active_class_count': l.active_class_count,
            'has_sections': l.has_sections,
        }
        for l in most_populated
    ]
    
    return stats


# =============================================================================
# CLASSROOM STATISTICS
# =============================================================================

def get_classroom_statistics(filters=None):
    """
    Get comprehensive statistics for classrooms
    
    Args:
        filters (dict): Optional filters
            - room_type: Filter by type
            - building: Filter by building
            - is_active: Filter by active status
            - is_bookable: Filter by bookable status
    
    Returns:
        dict: Classroom statistics and analysis
    """
    from .models import ClassRoom, Class
    
    classrooms = ClassRoom.objects.all()
    
    # Apply filters
    if filters:
        if filters.get('room_type'):
            classrooms = classrooms.filter(room_type=filters['room_type'])
        if filters.get('building'):
            classrooms = classrooms.filter(building=filters['building'])
        if filters.get('is_active') is not None:
            classrooms = classrooms.filter(is_active=filters['is_active'])
        if filters.get('is_bookable') is not None:
            classrooms = classrooms.filter(is_bookable=filters['is_bookable'])
    
    # Annotate with assignment counts
    classrooms = classrooms.annotate(
        assigned_class_count=Count('assigned_classes', distinct=True),
        active_assigned_count=Count(
            'assigned_classes',
            filter=Q(assigned_classes__is_active=True),
            distinct=True
        )
    )
    
    total_classrooms = classrooms.count()
    
    stats = {
        'total_classrooms': total_classrooms,
        'active_classrooms': classrooms.filter(is_active=True).count(),
        'inactive_classrooms': classrooms.filter(is_active=False).count(),
        'bookable_classrooms': classrooms.filter(is_bookable=True).count(),
        'non_bookable_classrooms': classrooms.filter(is_bookable=False).count(),
        
        # Type distribution
        'by_type': dict(
            classrooms.values('room_type')
            .annotate(count=Count('id'))
            .order_by('-count')
            .values_list('room_type', 'count')
        ),
        
        # Building distribution
        'by_building': dict(
            classrooms.exclude(building='')
            .values('building')
            .annotate(count=Count('id'))
            .order_by('-count')
            .values_list('building', 'count')
        ),
        
        # Floor distribution
        'by_floor': dict(
            classrooms.exclude(floor='')
            .values('floor')
            .annotate(count=Count('id'))
            .order_by('floor')
            .values_list('floor', 'count')
        ),
        
        # Assignment statistics
        'assignment_stats': {
            'assigned_classrooms': classrooms.filter(assigned_class_count__gt=0).count(),
            'unassigned_classrooms': classrooms.filter(assigned_class_count=0).count(),
            'total_assignments': Class.objects.exclude(classroom__isnull=True).count(),
        },
    }
    
    # Capacity analysis
    if total_classrooms > 0:
        capacity_data = classrooms.aggregate(
            total_capacity=Sum('capacity'),
            avg_capacity=Avg('capacity'),
            min_capacity=Min('capacity'),
            max_capacity=Max('capacity')
        )
        
        stats['capacity_analysis'] = {
            'total_capacity': capacity_data['total_capacity'] or 0,
            'average_capacity': float(capacity_data['avg_capacity'] or 0),
            'smallest_capacity': capacity_data['min_capacity'] or 0,
            'largest_capacity': capacity_data['max_capacity'] or 0,
        }
        
        # Capacity distribution
        stats['capacity_distribution'] = {
            'small_rooms': classrooms.filter(capacity__lte=20).count(),
            'medium_rooms': classrooms.filter(capacity__gt=20, capacity__lte=40).count(),
            'large_rooms': classrooms.filter(capacity__gt=40, capacity__lte=100).count(),
            'very_large_rooms': classrooms.filter(capacity__gt=100).count(),
        }
    
    # Facilities analysis
    stats['facilities'] = {
        'with_projector': classrooms.filter(has_projector=True).count(),
        'with_computer': classrooms.filter(has_computer=True).count(),
        'with_ac': classrooms.filter(has_air_conditioning=True).count(),
        'with_whiteboard': classrooms.filter(has_whiteboard=True).count(),
        'with_smart_board': classrooms.filter(has_smart_board=True).count(),
        'with_internet': classrooms.filter(has_internet=True).count(),
        'with_sound_system': classrooms.filter(has_sound_system=True).count(),
        'accessible': classrooms.filter(is_accessible=True).count(),
    }
    
    # Utilization analysis
    most_used = classrooms.order_by('-assigned_class_count')[:10]
    stats['most_used_classrooms'] = [
        {
            'id': c.id,
            'name': c.name,
            'room_number': c.room_number,
            'building': c.building,
            'capacity': c.capacity,
            'assigned_count': c.assigned_class_count,
            'active_assigned_count': c.active_assigned_count,
        }
        for c in most_used
    ]
    
    # Underutilized classrooms
    underutilized = classrooms.filter(
        is_active=True,
        assigned_class_count=0
    )
    stats['underutilized_classrooms'] = underutilized.count()
    
    return stats


# =============================================================================
# CLASS STATISTICS
# =============================================================================

# =============================================================================
# CLASS STATISTICS
# =============================================================================

def get_class_statistics(filters=None):
    """
    Get comprehensive statistics for classes.
    
    Args:
        filters (dict): Optional filters
            - academic_level: Filter by level
            - academic_session: Filter by session
            - class_teacher: Filter by teacher
            - is_active: Filter by active status
    
    Returns:
        dict: Class statistics and analysis
    """
    from .models import Class, ClassSubject
    try:
        from students.models import StudentClassEnrollment
        has_enrollment_model = True
    except ImportError:
        has_enrollment_model = False
    
    classes = Class.objects.all()
    
    # Apply filters
    if filters:
        if filters.get('academic_level'):
            classes = classes.filter(academic_level_id=filters['academic_level'])
        if filters.get('academic_session'):
            classes = classes.filter(academic_session_id=filters['academic_session'])
        if filters.get('class_teacher'):
            classes = classes.filter(class_teacher_id=filters['class_teacher'])
        if filters.get('is_active') is not None:
            classes = classes.filter(is_active=filters['is_active'])
    
    # Annotate with subject counts
    classes = classes.annotate(
        subject_count=Count('subjects', distinct=True),
        active_subject_count=Count(
            'subjects',
            filter=Q(subjects__is_active=True),
            distinct=True
        )
    )
    
    total_classes = classes.count()
    
    # --- by_session (fixed) ---
    by_session = {}
    for year, term, count in classes.values_list(
        'academic_session__year_name',
        'academic_session__term_name',
        'id'
    ):
        by_session.setdefault(year, {})
        by_session[year][term] = by_session[year].get(term, 0) + 1
    
    # --- by_level (safe dictionary) ---
    by_level = {}
    for level, count in classes.values_list('academic_level__name').annotate(count=Count('id')):
        by_level[level] = count
    
    # Section analysis
    section_stats = {
        'classes_with_sections': classes.exclude(section__isnull=True).exclude(section='').count(),
        'classes_without_sections': classes.filter(Q(section__isnull=True) | Q(section='')).count(),
    }
    
    # Subject statistics
    subject_stats = {
        'classes_with_subjects': classes.filter(subject_count__gt=0).count(),
        'classes_without_subjects': classes.filter(subject_count=0).count(),
        'total_subject_assignments': ClassSubject.objects.count(),
        'average_subjects_per_class': classes.aggregate(avg=Avg('subject_count'))['avg'] or 0,
    }
    
    # Teacher statistics
    teacher_stats = {
        'classes_with_teacher': classes.exclude(class_teacher__isnull=True).count(),
        'classes_without_teacher': classes.filter(class_teacher__isnull=True).count(),
        'classes_with_assistant': classes.exclude(assistant_teacher__isnull=True).count(),
    }
    
    # Classroom statistics
    classroom_stats = {
        'classes_with_classroom': classes.exclude(classroom__isnull=True).count(),
        'classes_without_classroom': classes.filter(classroom__isnull=True).count(),
    }
    
    # Capacity analysis
    capacity_analysis = {}
    if total_classes > 0:
        cap_data = classes.aggregate(
            total_max_students=Sum('max_students'),
            avg_max_students=Avg('max_students'),
            min_max_students=Min('max_students'),
            max_max_students=Max('max_students')
        )
        capacity_analysis = {
            'total_capacity': cap_data['total_max_students'] or 0,
            'average_capacity': float(cap_data['avg_max_students'] or 0),
            'smallest_capacity': cap_data['min_max_students'] or 0,
            'largest_capacity': cap_data['max_max_students'] or 0,
        }
    
    # Enrollment analysis
    enrollment_analysis = {}
    if has_enrollment_model and total_classes > 0:
        enrollment_data = []
        total_enrolled = 0
        for cls in classes:
            enrolled = cls.get_current_enrollment_count()
            total_enrolled += enrolled
            occupancy = (enrolled / cls.max_students * 100) if cls.max_students else 0
            enrollment_data.append({
                'class_id': cls.id,
                'class_name': cls.name,
                'enrolled': enrolled,
                'capacity': cls.max_students,
                'occupancy_percentage': occupancy,
            })
        
        enrollment_analysis = {
            'total_enrolled_students': total_enrolled,
            'average_enrollment_per_class': total_enrolled / total_classes,
            'classes_at_capacity': len([e for e in enrollment_data if e['occupancy_percentage'] >= 100]),
            'classes_over_capacity': len([e for e in enrollment_data if e['occupancy_percentage'] > 100]),
            'classes_underutilized': len([e for e in enrollment_data if e['occupancy_percentage'] < 50]),
            'average_occupancy_percentage': sum(e['occupancy_percentage'] for e in enrollment_data) / len(enrollment_data),
            'most_populated_classes': sorted(enrollment_data, key=lambda x: x['enrolled'], reverse=True)[:10]
        }
    
    # Performance analysis
    performance_analysis = {}
    classes_with_perf = classes.exclude(class_average_score__isnull=True)
    if classes_with_perf.exists():
        perf_data = classes_with_perf.aggregate(
            avg_score=Avg('class_average_score'),
            min_score=Min('class_average_score'),
            max_score=Max('class_average_score')
        )
        performance_analysis = {
            'classes_with_data': classes_with_perf.count(),
            'average_class_score': float(perf_data['avg_score'] or 0),
            'lowest_average': float(perf_data['min_score'] or 0),
            'highest_average': float(perf_data['max_score'] or 0),
        }
    
    # Attendance analysis
    attendance_analysis = {}
    classes_with_att = classes.exclude(attendance_rate__isnull=True)
    if classes_with_att.exists():
        att_data = classes_with_att.aggregate(
            avg_rate=Avg('attendance_rate'),
            min_rate=Min('attendance_rate'),
            max_rate=Max('attendance_rate')
        )
        attendance_analysis = {
            'classes_with_data': classes_with_att.count(),
            'average_attendance_rate': float(att_data['avg_rate'] or 0),
            'lowest_rate': float(att_data['min_rate'] or 0),
            'highest_rate': float(att_data['max_rate'] or 0),
        }
    
    # Combine everything into stats dictionary
    stats = {
        'total_classes': total_classes,
        'active_classes': classes.filter(is_active=True).count(),
        'inactive_classes': classes.filter(is_active=False).count(),
        'by_session': by_session,
        'by_level': by_level,
        'section_stats': section_stats,
        'subject_stats': subject_stats,
        'teacher_stats': teacher_stats,
        'classroom_stats': classroom_stats,
        'capacity_analysis': capacity_analysis,
        'enrollment_analysis': enrollment_analysis,
        'performance_analysis': performance_analysis,
        'attendance_analysis': attendance_analysis,
    }
    
    return stats



# =============================================================================
# CLASS SUBJECT STATISTICS
# =============================================================================

def get_class_subject_statistics(filters=None):
    """
    Get comprehensive statistics for class-subject assignments
    
    Args:
        filters (dict): Optional filters
            - class_instance: Filter by class
            - subject: Filter by subject
            - teacher: Filter by teacher
            - is_active: Filter by active status
            - is_optional: Filter by optional status
    
    Returns:
        dict: Class subject assignment statistics
    """
    from .models import ClassSubject
    
    class_subjects = ClassSubject.objects.all()
    
    # Apply filters
    if filters:
        if filters.get('class_instance'):
            class_subjects = class_subjects.filter(class_instance_id=filters['class_instance'])
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
        'total_assignments': total_assignments,
        'active_assignments': class_subjects.filter(is_active=True).count(),
        'inactive_assignments': class_subjects.filter(is_active=False).count(),
        'compulsory_assignments': class_subjects.filter(is_optional=False).count(),
        'optional_assignments': class_subjects.filter(is_optional=True).count(),
        
        # Teacher assignment
        'teacher_stats': {
            'assignments_with_teacher': class_subjects.exclude(teacher__isnull=True).count(),
            'assignments_without_teacher': class_subjects.filter(teacher__isnull=True).count(),
        },
        
        # Subject distribution
        'by_subject': dict(
            class_subjects.values('subject__name')
            .annotate(count=Count('id'))
            .order_by('-count')
            .values_list('subject__name', 'count')[:20]
        ),
        
        # Class distribution
        'by_class': dict(
            class_subjects.values('class_instance__academic_level__name', 'class_instance__section')
            .annotate(count=Count('id'))
            .order_by('-count')
            .values_list('class_instance__academic_level__name', 'count')[:20]
        ),
    }
    
    # Hours analysis
    if total_assignments > 0:
        hours_data = class_subjects.aggregate(
            total_hours_per_week=Sum('hours_per_week'),
            avg_hours_per_week=Avg('hours_per_week'),
            min_hours=Min('hours_per_week'),
            max_hours=Max('hours_per_week'),
            total_course_hours=Sum('total_hours'),
        )
        
        stats['hours_analysis'] = {
            'total_weekly_hours': hours_data['total_hours_per_week'] or 0,
            'average_weekly_hours': float(hours_data['avg_hours_per_week'] or 0),
            'minimum_weekly_hours': hours_data['min_hours'] or 0,
            'maximum_weekly_hours': hours_data['max_hours'] or 0,
            'total_course_hours': hours_data['total_course_hours'] or 0,
        }
    
    # Assessment weight analysis
    if total_assignments > 0:
        assessment_data = class_subjects.aggregate(
            avg_ca_weight=Avg('continuous_assessment_weight'),
            avg_exam_weight=Avg('final_exam_weight'),
        )
        
        stats['assessment_analysis'] = {
            'average_ca_weight': float(assessment_data['avg_ca_weight'] or 0),
            'average_exam_weight': float(assessment_data['avg_exam_weight'] or 0),
        }
        
        # Distribution of CA weights
        stats['ca_weight_distribution'] = {
            'ca_dominant': class_subjects.filter(continuous_assessment_weight__gt=50).count(),
            'exam_dominant': class_subjects.filter(final_exam_weight__gt=50).count(),
            'balanced': class_subjects.filter(
                continuous_assessment_weight=50,
                final_exam_weight=50
            ).count(),
        }
    
    # Performance analysis
    assignments_with_average = class_subjects.exclude(class_average__isnull=True)
    if assignments_with_average.exists():
        performance_data = assignments_with_average.aggregate(
            avg_class_average=Avg('class_average'),
            min_average=Min('class_average'),
            max_average=Max('class_average')
        )
        
        stats['performance_analysis'] = {
            'assignments_with_data': assignments_with_average.count(),
            'overall_average': float(performance_data['avg_class_average'] or 0),
            'lowest_average': float(performance_data['min_average'] or 0),
            'highest_average': float(performance_data['max_average'] or 0),
        }
    
    # Pass rate analysis
    assignments_with_pass_rate = class_subjects.exclude(pass_rate__isnull=True)
    if assignments_with_pass_rate.exists():
        pass_rate_data = assignments_with_pass_rate.aggregate(
            avg_pass_rate=Avg('pass_rate'),
            min_pass_rate=Min('pass_rate'),
            max_pass_rate=Max('pass_rate')
        )
        
        stats['pass_rate_analysis'] = {
            'assignments_with_data': assignments_with_pass_rate.count(),
            'average_pass_rate': float(pass_rate_data['avg_pass_rate'] or 0),
            'lowest_pass_rate': float(pass_rate_data['min_pass_rate'] or 0),
            'highest_pass_rate': float(pass_rate_data['max_pass_rate'] or 0),
        }
    
    # Teacher workload analysis
    teacher_workload = class_subjects.exclude(teacher__isnull=True).values(
        'teacher__staff__first_name',
        'teacher__staff__last_name'
    ).annotate(
        assignment_count=Count('id'),
        total_weekly_hours=Sum('hours_per_week')
    ).order_by('-total_weekly_hours')[:10]
    
    stats['teacher_workload'] = [
        {
            'teacher_name': f"{t['teacher__staff__first_name']} {t['teacher__staff__last_name']}",
            'assignment_count': t['assignment_count'],
            'total_weekly_hours': t['total_weekly_hours'],
        }
        for t in teacher_workload
    ]
    
    return stats


# =============================================================================
# COMPREHENSIVE DASHBOARD STATISTICS
# =============================================================================

def get_academic_dashboard_statistics(filters=None):
    """
    Get comprehensive dashboard statistics across all academic models
    
    Args:
        filters (dict): Optional filters to apply across models
    
    Returns:
        dict: Comprehensive dashboard statistics
    """
    dashboard = {
        'generated_at': timezone.now(),
        'sessions': get_academic_session_statistics(filters),
        'subjects': get_subject_statistics(filters),
        'levels': get_academic_level_statistics(filters),
        'classes': get_class_statistics(filters),
        'classrooms': get_classroom_statistics(filters),
        'holidays': get_holiday_statistics(filters),
        'class_subjects': get_class_subject_statistics(filters),
    }
    
    # Overall summary
    dashboard['summary'] = {
        'total_active_sessions': dashboard['sessions']['active_sessions'],
        'current_session_name': str(dashboard['sessions']['current_session']) if dashboard['sessions']['current_session'] else None,
        'total_subjects': dashboard['subjects']['total_subjects'],
        'total_levels': dashboard['levels']['total_levels'],
        'total_classes': dashboard['classes']['total_classes'],
        'total_classrooms': dashboard['classrooms']['total_classrooms'],
        'total_holidays': dashboard['holidays']['total_holidays'],
    }
    
    return dashboard


# =============================================================================
# EXPORT HELPER FUNCTIONS
# =============================================================================

def format_statistics_for_export(stats, format_type='dict'):
    """
    Format statistics for export (Excel, PDF, JSON)
    
    Args:
        stats (dict): Statistics dictionary
        format_type (str): Output format ('dict', 'flat', 'hierarchical')
    
    Returns:
        dict or list: Formatted statistics
    """
    if format_type == 'flat':
        # Flatten nested dictionaries
        flat_stats = {}
        
        def flatten(d, parent_key=''):
            for k, v in d.items():
                new_key = f"{parent_key}.{k}" if parent_key else k
                if isinstance(v, dict):
                    flatten(v, new_key)
                else:
                    flat_stats[new_key] = v
        
        flatten(stats)
        return flat_stats
    
    elif format_type == 'hierarchical':
        # Keep hierarchical structure but ensure all values are serializable
        def clean_values(d):
            cleaned = {}
            for k, v in d.items():
                if isinstance(v, dict):
                    cleaned[k] = clean_values(v)
                elif isinstance(v, (list, tuple)):
                    cleaned[k] = [clean_values(item) if isinstance(item, dict) else item for item in v]
                else:
                    # Convert to JSON-serializable types
                    if hasattr(v, 'isoformat'):
                        cleaned[k] = v.isoformat()
                    else:
                        cleaned[k] = v
            return cleaned
        
        return clean_values(stats)
    
    return stats