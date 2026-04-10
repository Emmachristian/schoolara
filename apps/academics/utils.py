# academics/utils.py
"""
Utility functions for academics app.
Helper functions for session management, period calculations, and academic operations.

REMOVED vs original:
  - get_next_level()      — trivial one-liner (return level.next_level); callers access
                            the attribute directly.
  - is_graduation_level() — trivial one-liner (return level.is_graduation_level); same reason.

FIXED vs original:
  - get_classes_with_low_enrollment() / get_classes_at_capacity() — replaced per-class
    DB query loop (N+1) with a single annotated queryset.
  - close_session()  — delegates the "can this be closed?" guard to the model's
                       can_be_closed() method instead of re-implementing it inline.
  - reset_class_roll_numbers() — added an explicit comment that this intentionally
    bypasses the pre_save signal; callers must be aware of the implication.

NOTE on validate_academic_year_format() / validate_term_number():
  AcademicSessionForm.clean_year_name() and clean_term_number() currently duplicate
  this logic inline.  Those methods should be refactored to call these utilities so
  the validation rules live in exactly one place.
"""

from django.utils import timezone
from django.db.models import Q, Count, Avg, Sum, Max, Min
from datetime import timedelta, date
from decimal import Decimal
from django.db import transaction
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# ACADEMIC SESSION UTILITIES
# =============================================================================

def get_current_academic_session():
    """
    Get the current academic session.

    Returns:
        AcademicSession or None: Currently active session.
    """
    from .models import AcademicSession

    try:
        return AcademicSession.objects.get(is_current=True)
    except AcademicSession.DoesNotExist:
        # Fallback: find by current date
        current_date = timezone.now().date()
        return AcademicSession.objects.filter(
            start_date__lte=current_date,
            end_date__gte=current_date,
            is_active=True
        ).first()
    except AcademicSession.MultipleObjectsReturned:
        logger.warning("Multiple sessions marked as current")
        return (
            AcademicSession.objects
            .filter(is_current=True)
            .order_by('-start_date')
            .first()
        )


def get_session_by_date(check_date):
    """
    Get the academic session that contains a specific date.

    Args:
        check_date (date): Date to check.

    Returns:
        AcademicSession or None
    """
    from .models import AcademicSession

    return AcademicSession.objects.filter(
        start_date__lte=check_date,
        end_date__gte=check_date
    ).first()


def get_sessions_for_year(year_name):
    """
    Get all sessions for a specific academic year.

    Args:
        year_name (str): e.g. '2024' or '2024-2025'.

    Returns:
        QuerySet
    """
    from .models import AcademicSession

    return AcademicSession.objects.filter(year_name=year_name).order_by('term_number')


def get_active_sessions():
    """
    Get all currently active, open sessions.

    Returns:
        QuerySet
    """
    from .models import AcademicSession

    return AcademicSession.objects.filter(
        is_active=True,
        is_academically_closed=False
    )


def get_upcoming_sessions(days=90):
    """
    Get upcoming sessions starting within the specified number of days.

    Args:
        days (int): Look-ahead window in days (default 90).

    Returns:
        QuerySet
    """
    from .models import AcademicSession

    current_date = timezone.now().date()
    future_date  = current_date + timedelta(days=days)

    return AcademicSession.objects.filter(
        start_date__gte=current_date,
        start_date__lte=future_date,
        is_active=True
    ).order_by('start_date')


def calculate_session_progress(session):
    """
    Calculate the progress of a session.

    Args:
        session (AcademicSession): The session.

    Returns:
        dict: Keys — status, progress_percentage, days_elapsed, days_remaining, total_days.
    """
    today = timezone.now().date()

    if today < session.start_date:
        status   = 'not_started'
        progress = 0
    elif today > session.end_date:
        status   = 'completed'
        progress = 100
    else:
        status     = 'ongoing'
        total_days = (session.end_date - session.start_date).days + 1
        elapsed    = (today - session.start_date).days + 1
        progress   = round((elapsed / total_days) * 100, 1)

    return {
        'status':              status,
        'progress_percentage': progress,
        'days_elapsed':        session.days_elapsed,
        'days_remaining':      session.days_remaining,
        'total_days':          session.total_days,
    }


def validate_session_overlap(start_date, end_date, year_name, exclude_session_id=None):
    """
    Check whether a proposed session date range overlaps with existing sessions
    in the same academic year.

    NOTE: AcademicSessionForm.clean() separately enforces unique (year_name, term_number)
    combinations but does NOT check date overlaps — that is this function's job.
    Views that create or update sessions should call both checks.

    Args:
        start_date (date): Proposed start date.
        end_date (date): Proposed end date.
        year_name (str): Academic year name.
        exclude_session_id: Session PK to exclude (used when editing an existing session).

    Returns:
        tuple: (is_valid: bool, overlapping_sessions: list)
    """
    from .models import AcademicSession

    overlapping = AcademicSession.objects.filter(
        year_name=year_name,
        start_date__lt=end_date,
        end_date__gt=start_date
    )

    if exclude_session_id:
        overlapping = overlapping.exclude(pk=exclude_session_id)

    return (not overlapping.exists(), list(overlapping))


def close_session(session, user=None):
    """
    Close an academic session with proper pre-flight checks.

    Delegates the "can this be closed?" decision to the model's
    can_be_closed() method (which checks is_academically_closed and is_current)
    rather than duplicating that logic here.

    Args:
        session (AcademicSession): Session to close.
        user: User performing the closure.

    Returns:
        tuple: (success: bool, message: str)
    """
    if not session.can_be_closed():
        if session.is_academically_closed:
            return False, "Session is already closed"
        if session.is_current:
            return False, "Cannot close the current session"
        return False, "Session cannot be closed in its current state"

    try:
        session.close_academically(user)
        return True, f"Session {session.name} closed successfully"
    except Exception as e:
        logger.error(f"Error closing session {session}: {e}")
        return False, f"Error closing session: {str(e)}"


def reopen_session(session, user=None):
    """
    Reopen a closed academic session.

    Args:
        session (AcademicSession): Session to reopen.
        user: User performing the reopen.

    Returns:
        tuple: (success: bool, message: str)
    """
    if not session.is_academically_closed:
        return False, "Session is not closed"

    try:
        session.reopen_academically(user)
        return True, f"Session {session.name} reopened successfully"
    except Exception as e:
        logger.error(f"Error reopening session {session}: {e}")
        return False, f"Error reopening session: {str(e)}"


# =============================================================================
# HOLIDAY UTILITIES
# =============================================================================

def get_holidays_in_range(start_date, end_date):
    """
    Get all holidays within a date range (inclusive).

    Args:
        start_date (date): Range start.
        end_date (date): Range end.

    Returns:
        QuerySet
    """
    from .models import Holiday

    return Holiday.objects.filter(
        Q(start_date__range=[start_date, end_date]) |
        Q(end_date__range=[start_date, end_date]) |
        Q(start_date__lte=start_date, end_date__gte=end_date)
    ).order_by('start_date')


def is_holiday(check_date):
    """
    Check whether a specific date falls on a holiday.

    Args:
        check_date (date): Date to check.

    Returns:
        bool
    """
    from .models import Holiday

    return Holiday.objects.filter(
        Q(start_date__lte=check_date, end_date__gte=check_date) |
        Q(start_date=check_date, end_date__isnull=True)
    ).exists()


def get_working_days(start_date, end_date, exclude_weekends=True):
    """
    Calculate working days between two dates, excluding holidays (and optionally weekends).

    Args:
        start_date (date): Start date (inclusive).
        end_date (date): End date (inclusive).
        exclude_weekends (bool): Exclude Saturdays and Sundays (default True).

    Returns:
        int: Number of working days.
    """
    current_date = start_date
    working_days = 0

    while current_date <= end_date:
        if exclude_weekends and current_date.weekday() >= 5:   # 5=Sat, 6=Sun
            current_date += timedelta(days=1)
            continue
        if not is_holiday(current_date):
            working_days += 1
        current_date += timedelta(days=1)

    return working_days


def get_upcoming_holidays(days=30):
    """
    Get upcoming holidays starting within the specified number of days.

    Args:
        days (int): Look-ahead window (default 30).

    Returns:
        QuerySet
    """
    from .models import Holiday

    today       = timezone.now().date()
    future_date = today + timedelta(days=days)

    return Holiday.objects.filter(
        start_date__gte=today,
        start_date__lte=future_date
    ).order_by('start_date')


# =============================================================================
# CLASS UTILITIES
# =============================================================================

def get_classes_for_session(session, active_only=True):
    """
    Get all classes for a specific academic session.

    Args:
        session (AcademicSession): The academic session.
        active_only (bool): Return only active classes (default True).

    Returns:
        QuerySet
    """
    from .models import Class

    qs = Class.objects.filter(academic_session=session)
    if active_only:
        qs = qs.filter(is_active=True)
    return qs


def get_class_capacity_summary(class_instance):
    """
    Return a capacity summary dict for a single class.

    Wraps the model's existing capacity methods into one dict so callers
    that need multiple metrics in one go don't have to call each property
    individually.  For bulk capacity reporting across many classes prefer
    get_classes_with_low_enrollment() / get_classes_at_capacity() which
    use a single annotated query.

    Args:
        class_instance (Class): The class.

    Returns:
        dict: current_enrollment, max_students, available_capacity,
              occupancy_percentage, is_full, has_capacity.
    """
    current_enrollment = class_instance.get_current_enrollment_count()
    max_students       = class_instance.max_students
    available          = max(0, max_students - current_enrollment)
    occupancy          = round((current_enrollment / max_students) * 100, 1) if max_students else 0

    return {
        'current_enrollment':  current_enrollment,
        'max_students':        max_students,
        'available_capacity':  available,
        'occupancy_percentage': occupancy,
        'is_full':             current_enrollment >= max_students,
        'has_capacity':        current_enrollment < max_students,
    }


def get_classes_with_low_enrollment(session, threshold=50):
    """
    Get classes whose current occupancy is below threshold %.

    Uses a single annotated query to avoid the N+1 problem that would arise
    from calling get_class_capacity_summary() in a loop.

    Args:
        session (AcademicSession): The academic session.
        threshold (int): Minimum occupancy percentage (default 50).

    Returns:
        list[dict]: Sorted ascending by occupancy.
                    Each dict: class, occupancy, current_enrollment, max_students.
    """
    from .models import Class
    from students.models import StudentClassEnrollment

    classes = (
        Class.objects
        .filter(academic_session=session, is_active=True)
        .annotate(
            current_enrollment=Count(
                'enrollments',
                filter=Q(
                    enrollments__is_active=True,
                    enrollments__completion_status='ONGOING',
                )
            )
        )
    )

    result = []
    for cls in classes:
        if cls.max_students == 0:
            continue
        occupancy = round((cls.current_enrollment / cls.max_students) * 100, 1)
        if occupancy < threshold:
            result.append({
                'class':              cls,
                'occupancy':          occupancy,
                'current_enrollment': cls.current_enrollment,
                'max_students':       cls.max_students,
            })

    return sorted(result, key=lambda x: x['occupancy'])


def get_classes_at_capacity(session):
    """
    Get classes that are at or over their maximum capacity.

    Uses a single annotated query to avoid the N+1 problem that would arise
    from calling get_class_capacity_summary() in a loop.

    Args:
        session (AcademicSession): The academic session.

    Returns:
        list[dict]: Each dict: class, current_enrollment, max_students, over_capacity.
    """
    from .models import Class

    classes = (
        Class.objects
        .filter(academic_session=session, is_active=True)
        .annotate(
            current_enrollment=Count(
                'enrollments',
                filter=Q(
                    enrollments__is_active=True,
                    enrollments__completion_status='ONGOING',
                )
            )
        )
    )

    return [
        {
            'class':              cls,
            'current_enrollment': cls.current_enrollment,
            'max_students':       cls.max_students,
            'over_capacity':      cls.current_enrollment > cls.max_students,
        }
        for cls in classes
        if cls.max_students > 0 and cls.current_enrollment >= cls.max_students
    ]


# =============================================================================
# SUBJECT UTILITIES
# =============================================================================

def get_subjects_for_level(academic_level):
    """
    Get all subjects applicable to an academic level.

    Returns subjects with no level restriction OR those explicitly including
    this level.

    Args:
        academic_level (AcademicLevel): The academic level.

    Returns:
        QuerySet
    """
    from .models import Subject

    return Subject.objects.filter(
        Q(applicable_levels__isnull=True) |
        Q(applicable_levels=academic_level)
    ).distinct()


def get_compulsory_subjects_for_level(academic_level):
    """
    Get compulsory subjects for an academic level.

    Args:
        academic_level (AcademicLevel): The academic level.

    Returns:
        QuerySet
    """
    return get_subjects_for_level(academic_level).filter(is_compulsory=True)


def get_optional_subjects_for_level(academic_level):
    """
    Get optional subjects for an academic level.

    Args:
        academic_level (AcademicLevel): The academic level.

    Returns:
        QuerySet
    """
    return get_subjects_for_level(academic_level).filter(is_compulsory=False)


def validate_subject_prerequisites(subject, student_completed_subjects):
    """
    Check whether a student has completed all prerequisites for a subject.

    Args:
        subject (Subject): The subject.
        student_completed_subjects (QuerySet): Subjects the student has passed.

    Returns:
        tuple: (is_valid: bool, missing_prerequisites: list)
    """
    prerequisites = subject.prerequisites.all()

    if not prerequisites.exists():
        return True, []

    completed_ids = set(student_completed_subjects.values_list('id', flat=True))
    required_ids  = set(prerequisites.values_list('id', flat=True))
    missing_ids   = required_ids - completed_ids

    if missing_ids:
        missing = subject.prerequisites.filter(id__in=missing_ids)
        return False, list(missing)

    return True, []


# =============================================================================
# ACADEMIC LEVEL UTILITIES
# =============================================================================

def get_level_progression_path(start_level):
    """
    Return the full ordered progression path starting from start_level.

    Follows the next_level chain until it terminates or a circular reference
    is detected.

    Args:
        start_level (AcademicLevel): Starting level.

    Returns:
        list[AcademicLevel]: Ordered path including start_level.
    """
    path    = [start_level]
    current = start_level
    max_iterations = 20
    iterations     = 0

    while current.next_level and iterations < max_iterations:
        current = current.next_level
        if current in path:
            logger.warning(
                f"Circular reference detected in level progression at {current}"
            )
            break
        path.append(current)
        iterations += 1

    return path


# =============================================================================
# CLASSROOM UTILITIES
# =============================================================================

def get_available_classrooms(start_time=None, end_time=None, exclude_class=None):
    """
    Get bookable, active classrooms — optionally filtered to those not already
    assigned to a class within the given time window.

    Args:
        start_time (time, optional): Window start time.
        end_time (time, optional): Window end time.
        exclude_class (Class, optional): Class to exclude from the occupancy check.

    Returns:
        QuerySet
    """
    from .models import ClassRoom, Class

    available = ClassRoom.objects.filter(is_active=True, is_bookable=True)

    if start_time and end_time:
        occupied_query = Q(
            start_time__lt=end_time,
            end_time__gt=start_time,
            is_active=True,
        )
        if exclude_class:
            occupied_query &= ~Q(pk=exclude_class.pk)

        occupied_rooms = (
            Class.objects
            .filter(occupied_query)
            .values_list('classroom_id', flat=True)
        )
        available = available.exclude(id__in=occupied_rooms)

    return available


def get_classroom_utilization(classroom, session):
    """
    Calculate classroom utilization for a session.

    Args:
        classroom (ClassRoom): The classroom.
        session (AcademicSession): The academic session.

    Returns:
        dict: classroom, total_classes_assigned, total_hours_per_week,
              max_hours_per_week, utilization_percentage, is_overutilized.
    """
    from .models import Class

    assigned_classes = Class.objects.filter(
        classroom=classroom,
        academic_session=session,
        is_active=True,
    )

    total_classes = assigned_classes.count()
    total_hours   = (
        assigned_classes.aggregate(total=Sum('hours_per_week'))['total'] or 0
    )

    max_hours_per_week    = 40   # assumed weekly maximum
    utilization_percentage = round(
        (total_hours / max_hours_per_week) * 100, 1
    ) if max_hours_per_week else 0

    return {
        'classroom':              classroom,
        'total_classes_assigned': total_classes,
        'total_hours_per_week':   total_hours,
        'max_hours_per_week':     max_hours_per_week,
        'utilization_percentage': utilization_percentage,
        'is_overutilized':        total_hours > max_hours_per_week,
    }


# =============================================================================
# VALIDATION UTILITIES
# =============================================================================

def validate_academic_year_format(year_name):
    """
    Validate academic year name format.

    Accepted formats: "YYYY", "YYYY-YYYY", "YYYY/YYYY".

    NOTE: AcademicSessionForm.clean_year_name() currently duplicates this logic
    inline.  That method should be refactored to call this function so the rule
    lives in one place.

    Args:
        year_name (str): Year name to validate.

    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    import re

    if '/' in year_name or '-' in year_name:
        pattern = r'^(20\d{2})[\/-](20\d{2})$'
        if not re.match(pattern, year_name):
            return False, 'Year name must be in format "YYYY-YYYY" or "YYYY/YYYY"'
    else:
        if not re.match(r'^20\d{2}$', year_name):
            return False, 'Year name must be in format "YYYY"'

    return True, None


def validate_term_number(term_number):
    """
    Validate term number against the school's SchoolConfiguration.

    NOTE: AcademicSessionForm.clean_term_number() currently duplicates this logic
    inline.  That method should be refactored to call this function.

    Args:
        term_number (int): Term number to validate.

    Returns:
        tuple: (is_valid: bool, error_message: str or None, max_periods: int or None)
    """
    from core.models import SchoolConfiguration

    try:
        config = SchoolConfiguration.get_instance()
        if config:
            max_periods = config.get_period_count()
            if not config.validate_period_number(term_number):
                return (
                    False,
                    f'Period number {term_number} is invalid for '
                    f'{config.get_term_system_display()} system (max: {max_periods})',
                    max_periods,
                )
            return True, None, max_periods
    except Exception as e:
        logger.warning(f"Could not validate against SchoolConfiguration: {e}")
        if term_number > 12:
            return False, 'Period number cannot exceed 12', 12

    return True, None, None


# =============================================================================
# ROLL NUMBER UTILITIES
# =============================================================================

def generate_class_roll_number(*, class_instance, academic_session):
    """
    Generate a sequential roll number for a new enrolment in the given
    class / session combination.

    Format: zero-padded 3-digit integer — 001, 002, 003, …

    Uses select_for_update() inside an atomic block to prevent race conditions
    when multiple enrolments are created concurrently.

    Called by the pre_save signal in signals.py (auto_generate_roll_number).

    Args:
        class_instance (Class): The class.
        academic_session (AcademicSession): The academic session.

    Returns:
        str: e.g. "007"
    """
    from academics.models import StudentClassEnrollment

    with transaction.atomic():
        last = (
            StudentClassEnrollment.objects
            .select_for_update()
            .filter(
                class_instance=class_instance,
                academic_session=academic_session,
            )
            .exclude(roll_number__isnull=True)
            .exclude(roll_number='')
            .order_by('-roll_number')
            .first()
        )

        next_number = (int(last.roll_number) + 1) if (last and last.roll_number.isdigit()) else 1
        return f"{next_number:03d}"


def reset_class_roll_numbers(class_instance, academic_session):
    """
    Regenerate sequential roll numbers for all enrolments in a class,
    ordered alphabetically by student surname then first name.

    IMPORTANT — signal bypass:
        This function calls enrollment.save(update_fields=['roll_number'])
        directly.  The pre_save signal (auto_generate_roll_number in signals.py)
        only fires for new records (_state.adding == True), so existing records
        updated here are unaffected by it.  If the signal ever gains logic that
        should also run on updates, this function must be revised.

    Args:
        class_instance (Class): The class.
        academic_session (AcademicSession): The academic session.

    Returns:
        int: Number of roll numbers regenerated.
    """
    from academics.models import StudentClassEnrollment

    with transaction.atomic():
        enrollments = (
            StudentClassEnrollment.objects
            .filter(
                class_instance=class_instance,
                academic_session=academic_session,
            )
            .select_for_update()
            .order_by('student__last_name', 'student__first_name')
        )

        count = 0
        for index, enrollment in enumerate(enrollments, start=1):
            enrollment.roll_number = f"{index:03d}"
            enrollment.save(update_fields=['roll_number'])
            count += 1

        logger.info(
            f"Reset {count} roll numbers for {class_instance} - {academic_session}"
        )
        return count