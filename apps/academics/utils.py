# academics/utils.py
"""
Utility functions for academics app
Helper functions for session management, period calculations, and academic operations
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
        AcademicSession or None: Currently active session
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
        # If multiple marked as current, return most recent
        logger.warning("Multiple sessions marked as current")
        return AcademicSession.objects.filter(is_current=True).order_by('-start_date').first()


def get_session_by_date(check_date):
    """
    Get academic session that contains a specific date.
    
    Args:
        check_date (date): Date to check
        
    Returns:
        AcademicSession or None: Session containing the date
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
        year_name (str): Academic year name (e.g., '2024', '2024-2025')
        
    Returns:
        QuerySet: Sessions for that year
    """
    from .models import AcademicSession
    
    return AcademicSession.objects.filter(
        year_name=year_name
    ).order_by('term_number')


def get_active_sessions():
    """
    Get all currently active sessions.
    
    Returns:
        QuerySet: Active sessions
    """
    from .models import AcademicSession
    
    return AcademicSession.objects.filter(
        is_active=True,
        is_academically_closed=False
    )


def get_upcoming_sessions(days=90):
    """
    Get upcoming sessions within specified days.
    
    Args:
        days (int): Number of days to look ahead
        
    Returns:
        QuerySet: Upcoming sessions
    """
    from .models import AcademicSession
    
    current_date = timezone.now().date()
    future_date = current_date + timedelta(days=days)
    
    return AcademicSession.objects.filter(
        start_date__gte=current_date,
        start_date__lte=future_date,
        is_active=True
    ).order_by('start_date')


def calculate_session_progress(session):
    """
    Calculate the progress of a session.
    
    Args:
        session (AcademicSession): The session
        
    Returns:
        dict: Progress information
    """
    today = timezone.now().date()
    
    if today < session.start_date:
        status = 'not_started'
        progress = 0
    elif today > session.end_date:
        status = 'completed'
        progress = 100
    else:
        status = 'ongoing'
        total_days = (session.end_date - session.start_date).days + 1
        elapsed_days = (today - session.start_date).days + 1
        progress = round((elapsed_days / total_days) * 100, 1)
    
    return {
        'status': status,
        'progress_percentage': progress,
        'days_elapsed': session.days_elapsed,
        'days_remaining': session.days_remaining,
        'total_days': session.total_days,
    }


def validate_session_overlap(start_date, end_date, year_name, exclude_session_id=None):
    """
    Check if a session overlaps with existing sessions in the same year.
    
    Args:
        start_date (date): Session start date
        end_date (date): Session end date
        year_name (str): Academic year name
        exclude_session_id: Session ID to exclude from check (for updates)
        
    Returns:
        tuple: (is_valid, overlapping_sessions)
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
    Close an academic session with proper checks.
    
    Args:
        session (AcademicSession): Session to close
        user: User performing the closure
        
    Returns:
        tuple: (success, message)
    """
    if session.is_academically_closed:
        return (False, "Session is already closed")
    
    if session.is_current:
        return (False, "Cannot close the current session")
    
    try:
        session.close_academically(user)
        return (True, f"Session {session.name} closed successfully")
    except Exception as e:
        logger.error(f"Error closing session {session}: {e}")
        return (False, f"Error closing session: {str(e)}")


def reopen_session(session, user=None):
    """
    Reopen a closed academic session.
    
    Args:
        session (AcademicSession): Session to reopen
        user: User performing the reopen
        
    Returns:
        tuple: (success, message)
    """
    if not session.is_academically_closed:
        return (False, "Session is not closed")
    
    try:
        session.reopen_academically(user)
        return (True, f"Session {session.name} reopened successfully")
    except Exception as e:
        logger.error(f"Error reopening session {session}: {e}")
        return (False, f"Error reopening session: {str(e)}")


# =============================================================================
# HOLIDAY UTILITIES
# =============================================================================

def get_holidays_in_range(start_date, end_date):
    """
    Get all holidays within a date range.
    
    Args:
        start_date (date): Range start
        end_date (date): Range end
        
    Returns:
        QuerySet: Holidays in range
    """
    from .models import Holiday
    
    return Holiday.objects.filter(
        Q(start_date__range=[start_date, end_date]) |
        Q(end_date__range=[start_date, end_date]) |
        Q(start_date__lte=start_date, end_date__gte=end_date)
    ).order_by('start_date')


def is_holiday(check_date):
    """
    Check if a specific date is a holiday.
    
    Args:
        check_date (date): Date to check
        
    Returns:
        bool: True if date is a holiday
    """
    from .models import Holiday
    
    return Holiday.objects.filter(
        Q(start_date__lte=check_date, end_date__gte=check_date) |
        Q(start_date=check_date, end_date__isnull=True)
    ).exists()


def get_working_days(start_date, end_date, exclude_weekends=True):
    """
    Calculate working days between two dates (excluding holidays).
    
    Args:
        start_date (date): Start date
        end_date (date): End date
        exclude_weekends (bool): Whether to exclude Saturdays and Sundays
        
    Returns:
        int: Number of working days
    """
    from .models import Holiday
    
    current_date = start_date
    working_days = 0
    
    while current_date <= end_date:
        # Check weekends if needed
        if exclude_weekends and current_date.weekday() >= 5:  # Saturday=5, Sunday=6
            current_date += timedelta(days=1)
            continue
        
        # Check if it's a holiday
        if not is_holiday(current_date):
            working_days += 1
        
        current_date += timedelta(days=1)
    
    return working_days


def get_upcoming_holidays(days=30):
    """
    Get upcoming holidays within specified days.
    
    Args:
        days (int): Number of days to look ahead
        
    Returns:
        QuerySet: Upcoming holidays
    """
    from .models import Holiday
    
    today = timezone.now().date()
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
        session (AcademicSession): The academic session
        active_only (bool): Whether to return only active classes
        
    Returns:
        QuerySet: Classes for the session
    """
    from .models import Class
    
    classes = Class.objects.filter(academic_session=session)
    
    if active_only:
        classes = classes.filter(is_active=True)
    
    return classes


def get_class_capacity_summary(class_instance):
    """
    Get capacity summary for a class.
    
    Args:
        class_instance (Class): The class
        
    Returns:
        dict: Capacity information
    """
    current_enrollment = class_instance.get_current_enrollment_count()
    max_students = class_instance.max_students
    available = max(0, max_students - current_enrollment)
    occupancy = round((current_enrollment / max_students) * 100, 1) if max_students > 0 else 0
    
    return {
        'current_enrollment': current_enrollment,
        'max_students': max_students,
        'available_capacity': available,
        'occupancy_percentage': occupancy,
        'is_full': current_enrollment >= max_students,
        'has_capacity': current_enrollment < max_students,
    }


def get_classes_with_low_enrollment(session, threshold=50):
    """
    Get classes with enrollment below threshold percentage.
    
    Args:
        session (AcademicSession): The academic session
        threshold (int): Minimum enrollment percentage
        
    Returns:
        list: Classes with low enrollment
    """
    from .models import Class
    
    classes = get_classes_for_session(session)
    low_enrollment = []
    
    for class_instance in classes:
        summary = get_class_capacity_summary(class_instance)
        if summary['occupancy_percentage'] < threshold:
            low_enrollment.append({
                'class': class_instance,
                'occupancy': summary['occupancy_percentage'],
                'current_enrollment': summary['current_enrollment'],
                'max_students': summary['max_students'],
            })
    
    return sorted(low_enrollment, key=lambda x: x['occupancy'])


def get_classes_at_capacity(session):
    """
    Get classes that are at or over capacity.
    
    Args:
        session (AcademicSession): The academic session
        
    Returns:
        list: Classes at capacity
    """
    from .models import Class
    
    classes = get_classes_for_session(session)
    at_capacity = []
    
    for class_instance in classes:
        summary = get_class_capacity_summary(class_instance)
        if summary['is_full']:
            at_capacity.append({
                'class': class_instance,
                'current_enrollment': summary['current_enrollment'],
                'max_students': summary['max_students'],
                'over_capacity': summary['current_enrollment'] > summary['max_students'],
            })
    
    return at_capacity


# =============================================================================
# SUBJECT UTILITIES
# =============================================================================

def get_subjects_for_level(academic_level):
    """
    Get all subjects applicable to an academic level.
    
    Args:
        academic_level (AcademicLevel): The academic level
        
    Returns:
        QuerySet: Applicable subjects
    """
    from .models import Subject
    
    # Subjects with no level restrictions OR explicitly including this level
    return Subject.objects.filter(
        Q(applicable_levels__isnull=True) |
        Q(applicable_levels=academic_level)
    ).distinct()


def get_compulsory_subjects_for_level(academic_level):
    """
    Get compulsory subjects for an academic level.
    
    Args:
        academic_level (AcademicLevel): The academic level
        
    Returns:
        QuerySet: Compulsory subjects
    """
    from .models import Subject
    
    return get_subjects_for_level(academic_level).filter(is_compulsory=True)


def get_optional_subjects_for_level(academic_level):
    """
    Get optional subjects for an academic level.
    
    Args:
        academic_level (AcademicLevel): The academic level
        
    Returns:
        QuerySet: Optional subjects
    """
    from .models import Subject
    
    return get_subjects_for_level(academic_level).filter(is_compulsory=False)


def validate_subject_prerequisites(subject, student_completed_subjects):
    """
    Check if a student has completed prerequisites for a subject.
    
    Args:
        subject (Subject): The subject
        student_completed_subjects (QuerySet): Subjects the student has completed
        
    Returns:
        tuple: (is_valid, missing_prerequisites)
    """
    prerequisites = subject.prerequisites.all()
    
    if not prerequisites.exists():
        return (True, [])
    
    completed_ids = set(student_completed_subjects.values_list('id', flat=True))
    required_ids = set(prerequisites.values_list('id', flat=True))
    
    missing_ids = required_ids - completed_ids
    
    if missing_ids:
        missing = subject.prerequisites.filter(id__in=missing_ids)
        return (False, list(missing))
    
    return (True, [])


# =============================================================================
# ACADEMIC LEVEL UTILITIES
# =============================================================================

def get_next_level(current_level):
    """
    Get the next academic level.
    
    Args:
        current_level (AcademicLevel): Current level
        
    Returns:
        AcademicLevel or None: Next level
    """
    return current_level.next_level


def get_level_progression_path(start_level):
    """
    Get the full progression path from a starting level.
    
    Args:
        start_level (AcademicLevel): Starting level
        
    Returns:
        list: Ordered list of levels in progression
    """
    path = [start_level]
    current = start_level
    
    # Prevent infinite loops
    max_iterations = 20
    iterations = 0
    
    while current.next_level and iterations < max_iterations:
        current = current.next_level
        if current in path:  # Circular reference
            logger.warning(f"Circular reference detected in level progression at {current}")
            break
        path.append(current)
        iterations += 1
    
    return path


def is_graduation_level(level):
    """
    Check if a level is a graduation level.
    
    Args:
        level (AcademicLevel): The level
        
    Returns:
        bool: True if graduation level
    """
    return level.is_graduation_level


# =============================================================================
# CLASSROOM UTILITIES
# =============================================================================

def get_available_classrooms(start_time=None, end_time=None, exclude_class=None):
    """
    Get available classrooms for a time period.
    
    Args:
        start_time (time): Start time
        end_time (time): End time
        exclude_class: Class to exclude from check
        
    Returns:
        QuerySet: Available classrooms
    """
    from .models import ClassRoom, Class
    
    available = ClassRoom.objects.filter(is_active=True, is_bookable=True)
    
    if start_time and end_time:
        # Get classrooms already assigned to classes in this time range
        occupied_query = Q(
            start_time__lt=end_time,
            end_time__gt=start_time,
            is_active=True
        )
        
        if exclude_class:
            occupied_query &= ~Q(pk=exclude_class.pk)
        
        occupied_rooms = Class.objects.filter(occupied_query).values_list('classroom_id', flat=True)
        
        available = available.exclude(id__in=occupied_rooms)
    
    return available


def get_classroom_utilization(classroom, session):
    """
    Calculate classroom utilization for a session.
    
    Args:
        classroom (ClassRoom): The classroom
        session (AcademicSession): The academic session
        
    Returns:
        dict: Utilization information
    """
    from .models import Class
    
    assigned_classes = Class.objects.filter(
        classroom=classroom,
        academic_session=session,
        is_active=True
    )
    
    total_classes = assigned_classes.count()
    total_hours = assigned_classes.aggregate(
        total=Sum('hours_per_week')
    )['total'] or 0
    
    # Assuming 40 hours per week maximum utilization
    max_hours_per_week = 40
    utilization_percentage = round((total_hours / max_hours_per_week) * 100, 1) if max_hours_per_week > 0 else 0
    
    return {
        'classroom': classroom,
        'total_classes_assigned': total_classes,
        'total_hours_per_week': total_hours,
        'max_hours_per_week': max_hours_per_week,
        'utilization_percentage': utilization_percentage,
        'is_overutilized': total_hours > max_hours_per_week,
    }


# =============================================================================
# VALIDATION UTILITIES
# =============================================================================

def validate_academic_year_format(year_name):
    """
    Validate academic year name format.
    
    Args:
        year_name (str): Year name to validate
        
    Returns:
        tuple: (is_valid, error_message)
    """
    import re
    
    if '/' in year_name or '-' in year_name:
        pattern = r'^(20\d{2})[\/-](20\d{2})$'
        if not re.match(pattern, year_name):
            return (False, 'Year name must be in format "YYYY-YYYY" or "YYYY/YYYY"')
    else:
        pattern = r'^20\d{2}$'
        if not re.match(pattern, year_name):
            return (False, 'Year name must be in format "YYYY"')
    
    return (True, None)


def validate_term_number(term_number):
    """
    Validate term number against school configuration.
    
    Args:
        term_number (int): Term number to validate
        
    Returns:
        tuple: (is_valid, error_message, max_periods)
    """
    from core.models import SchoolConfiguration
    
    try:
        config = SchoolConfiguration.get_instance()
        if config:
            max_periods = config.get_period_count()
            if not config.validate_period_number(term_number):
                return (
                    False,
                    f'Period number {term_number} is invalid for {config.get_term_system_display()} system (max: {max_periods})',
                    max_periods
                )
            return (True, None, max_periods)
    except Exception as e:
        logger.warning(f"Could not validate against SchoolConfiguration: {e}")
        if term_number > 12:
            return (False, 'Period number cannot exceed 12', 12)
    
    return (True, None, None)

# =============================================================================
# GENERATE ENROLLMENT ROLL NUMBERS
# =============================================================================

def generate_class_roll_number(*, class_instance, academic_session):
    """
    Generate a sequential roll number per class & academic session.
    
    Format: 001, 002, 003, ...
    
    Args:
        class_instance (Class): The class instance
        academic_session (AcademicSession): The academic session
        
    Returns:
        str: Zero-padded 3-digit roll number
        
    Note:
        This function uses select_for_update() to prevent race conditions
        when multiple enrollments are created simultaneously.
    """
    from django.db import transaction
    from academics.models import StudentClassEnrollment

    with transaction.atomic():
        # Lock the table to prevent race conditions
        last = (
            StudentClassEnrollment.objects
            .select_for_update()
            .filter(
                class_instance=class_instance,
                academic_session=academic_session
            )
            .exclude(roll_number__isnull=True)
            .exclude(roll_number='')
            .order_by('-roll_number')
            .first()
        )

        if last and last.roll_number.isdigit():
            next_number = int(last.roll_number) + 1
        else:
            # First enrollment in this class/session
            next_number = 1

        # Format as zero-padded 3-digit number
        return f"{next_number:03d}"


def reset_class_roll_numbers(class_instance, academic_session):
    """
    Reset and regenerate roll numbers for an entire class.
    Useful when students are reordered or roll numbers need to be sequential.
    
    Args:
        class_instance (Class): The class instance
        academic_session (AcademicSession): The academic session
        
    Returns:
        int: Number of roll numbers regenerated
    """
    from django.db import transaction
    from academics.models import StudentClassEnrollment
    
    with transaction.atomic():
        # Get all enrollments for this class/session, ordered by student name
        enrollments = StudentClassEnrollment.objects.filter(
            class_instance=class_instance,
            academic_session=academic_session
        ).select_for_update().order_by('student__last_name', 'student__first_name')
        
        count = 0
        for index, enrollment in enumerate(enrollments, start=1):
            enrollment.roll_number = f"{index:03d}"
            enrollment.save(update_fields=['roll_number'])
            count += 1
        
        logger.info(
            f"Reset {count} roll numbers for {class_instance} - {academic_session}"
        )
        
        return count