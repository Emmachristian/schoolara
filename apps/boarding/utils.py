# boarding/utils.py

"""
Utility functions for boarding app
Helper functions for dormitory management, capacity calculations, and boarding operations
"""

from django.utils import timezone
from django.db.models import Q, Count, Avg, Sum, Max, Min, F
from django.db import transaction
from datetime import timedelta, date
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# DORMITORY UTILITIES
# =============================================================================

def get_dormitory_capacity_summary(dormitory):
    """
    Get capacity summary for a dormitory.
    
    Args:
        dormitory (Dormitory): The dormitory
        
    Returns:
        dict: Capacity information
    """
    current_occupancy = dormitory.current_occupancy
    total_capacity = dormitory.total_capacity
    available = max(0, total_capacity - current_occupancy)
    occupancy_percentage = round((current_occupancy / total_capacity) * 100, 1) if total_capacity > 0 else 0
    
    return {
        'current_occupancy': current_occupancy,
        'total_capacity': total_capacity,
        'available_capacity': available,
        'occupancy_percentage': occupancy_percentage,
        'is_full': current_occupancy >= total_capacity,
        'has_capacity': current_occupancy < total_capacity,
        'is_nearly_full': occupancy_percentage >= 90,
        'occupancy_level': get_occupancy_level(occupancy_percentage),
        'occupancy_color': get_occupancy_color(occupancy_percentage),
    }


def get_occupancy_level(occupancy_percentage):
    """
    Get occupancy level as string.
    
    Args:
        occupancy_percentage (float): Occupancy percentage
        
    Returns:
        str: 'low', 'medium', 'high', or 'full'
    """
    if occupancy_percentage == 0:
        return 'empty'
    elif occupancy_percentage < 50:
        return 'low'
    elif occupancy_percentage < 80:
        return 'medium'
    elif occupancy_percentage < 100:
        return 'high'
    else:
        return 'full'


def get_occupancy_color(occupancy_percentage):
    """
    Get color class for occupancy display.
    
    Args:
        occupancy_percentage (float): Occupancy percentage
        
    Returns:
        str: Bootstrap color class
    """
    level = get_occupancy_level(occupancy_percentage)
    colors = {
        'empty': 'secondary',
        'low': 'success',
        'medium': 'info',
        'high': 'warning',
        'full': 'danger',
    }
    return colors.get(level, 'secondary')


def get_available_dormitories(gender, session, boarding_type=None):
    """
    Get available dormitories for a gender and session.
    
    Args:
        gender (str): 'M' or 'F'
        session (AcademicSession): The academic session
        boarding_type (str): Optional - filter by boarding type
        
    Returns:
        QuerySet: Available dormitories
    """
    from boarding.models import Dormitory
    
    # Base query - active and available
    dormitories = Dormitory.objects.filter(
        is_active=True,
        is_available_for_new_admissions=True
    )
    
    # Filter by gender compatibility
    if gender == 'M':
        dormitories = dormitories.filter(
            Q(dormitory_type='BOYS') | Q(dormitory_type='MIXED')
        )
    elif gender == 'F':
        dormitories = dormitories.filter(
            Q(dormitory_type='GIRLS') | Q(dormitory_type='MIXED')
        )
    
    # Filter by capacity (has space)
    dormitories = dormitories.filter(
        current_occupancy__lt=F('total_capacity')
    )
    
    # Exclude dormitories under maintenance
    dormitories = dormitories.exclude(
        maintenance_status__in=['CONDEMNED', 'UNDER_MAINTENANCE']
    )
    
    return dormitories


def get_dormitories_by_gender(gender):
    """
    Get all dormitories that can accommodate a specific gender.
    
    Args:
        gender (str): 'M' or 'F'
        
    Returns:
        QuerySet: Compatible dormitories
    """
    from boarding.models import Dormitory
    
    if gender == 'M':
        return Dormitory.objects.filter(
            Q(dormitory_type='BOYS') | Q(dormitory_type='MIXED'),
            is_active=True
        )
    elif gender == 'F':
        return Dormitory.objects.filter(
            Q(dormitory_type='GIRLS') | Q(dormitory_type='MIXED'),
            is_active=True
        )
    
    return Dormitory.objects.none()


def get_dormitories_at_capacity(session):
    """
    Get dormitories that are at or over capacity.
    
    Args:
        session (AcademicSession): The academic session
        
    Returns:
        list: Dormitories at capacity
    """
    from boarding.models import Dormitory
    
    dormitories = Dormitory.objects.filter(is_active=True)
    at_capacity = []
    
    for dormitory in dormitories:
        summary = get_dormitory_capacity_summary(dormitory)
        if summary['is_full']:
            at_capacity.append({
                'dormitory': dormitory,
                'current_occupancy': summary['current_occupancy'],
                'total_capacity': summary['total_capacity'],
                'over_capacity': summary['current_occupancy'] > summary['total_capacity'],
            })
    
    return at_capacity


def get_dormitories_with_low_occupancy(threshold=50):
    """
    Get dormitories with occupancy below threshold percentage.
    
    Args:
        threshold (int): Minimum occupancy percentage
        
    Returns:
        list: Dormitories with low occupancy
    """
    from boarding.models import Dormitory
    
    dormitories = Dormitory.objects.filter(is_active=True)
    low_occupancy = []
    
    for dormitory in dormitories:
        summary = get_dormitory_capacity_summary(dormitory)
        if summary['occupancy_percentage'] < threshold:
            low_occupancy.append({
                'dormitory': dormitory,
                'occupancy': summary['occupancy_percentage'],
                'current_occupancy': summary['current_occupancy'],
                'total_capacity': summary['total_capacity'],
            })
    
    return sorted(low_occupancy, key=lambda x: x['occupancy'])


def validate_dormitory_compatibility(dormitory, student):
    """
    Check if a dormitory can accommodate a student.
    
    Args:
        dormitory (Dormitory): The dormitory
        student (Student): The student
        
    Returns:
        tuple: (is_compatible, message)
    """
    # Check if active
    if not dormitory.is_active:
        return (False, "Dormitory is not active")
    
    # Check if available for admissions
    if not dormitory.is_available_for_new_admissions:
        return (False, "Dormitory is not accepting new admissions")
    
    # Check maintenance status
    if dormitory.maintenance_status in ['CONDEMNED', 'UNDER_MAINTENANCE']:
        return (False, f"Dormitory is {dormitory.get_maintenance_status_display()}")
    
    # Check capacity
    if dormitory.is_full:
        return (False, "Dormitory is at full capacity")
    
    # Check gender compatibility
    if not dormitory.can_accommodate_gender(student.gender):
        return (False, f"Dormitory cannot accommodate {student.get_gender_display()} students")
    
    return (True, "Compatible")


# =============================================================================
# BOARDING ENROLLMENT UTILITIES
# =============================================================================

def get_active_boarders(session, dormitory=None):
    """
    Get all active boarders for a session.
    
    Args:
        session (AcademicSession): The academic session
        dormitory (Dormitory): Optional - filter by dormitory
        
    Returns:
        QuerySet: Active boarding enrollments
    """
    from boarding.models import BoardingEnrollment
    
    enrollments = BoardingEnrollment.objects.filter(
        academic_session=session,
        status='ACTIVE'
    ).select_related('student', 'dormitory')
    
    if dormitory:
        enrollments = enrollments.filter(dormitory=dormitory)
    
    return enrollments


def get_boarding_enrollments_by_type(session, boarding_type):
    """
    Get boarding enrollments by type.
    
    Args:
        session (AcademicSession): The academic session
        boarding_type (str): 'FULL_BOARDER', 'WEEKLY_BOARDER', 'FLEXI_BOARDER'
        
    Returns:
        QuerySet: Enrollments of specified type
    """
    from boarding.models import BoardingEnrollment
    
    return BoardingEnrollment.objects.filter(
        academic_session=session,
        boarding_type=boarding_type,
        status='ACTIVE'
    ).select_related('student', 'dormitory')


def get_boarding_statistics(session):
    """
    Get comprehensive boarding statistics for a session.
    
    Args:
        session (AcademicSession): The academic session
        
    Returns:
        dict: Boarding statistics
    """
    from boarding.models import BoardingEnrollment, Dormitory
    
    enrollments = BoardingEnrollment.objects.filter(academic_session=session)
    
    # Count by status
    status_counts = enrollments.values('status').annotate(count=Count('id'))
    status_dict = {item['status']: item['count'] for item in status_counts}
    
    # Count by boarding type
    type_counts = enrollments.filter(status='ACTIVE').values('boarding_type').annotate(count=Count('id'))
    type_dict = {item['boarding_type']: item['count'] for item in type_counts}
    
    # Dormitory occupancy
    dormitories = Dormitory.objects.filter(is_active=True)
    total_capacity = dormitories.aggregate(total=Sum('total_capacity'))['total'] or 0
    total_occupied = dormitories.aggregate(total=Sum('current_occupancy'))['total'] or 0
    
    return {
        'total_enrollments': enrollments.count(),
        'active_boarders': enrollments.filter(status='ACTIVE').count(),
        'pending_enrollments': enrollments.filter(status='PENDING').count(),
        'suspended_enrollments': enrollments.filter(status='SUSPENDED').count(),
        'by_type': {
            'full_boarders': type_dict.get('FULL_BOARDER', 0),
            'weekly_boarders': type_dict.get('WEEKLY_BOARDER', 0),
            'flexi_boarders': type_dict.get('FLEXI_BOARDER', 0),
        },
        'dormitory_stats': {
            'total_capacity': total_capacity,
            'total_occupied': total_occupied,
            'total_available': max(0, total_capacity - total_occupied),
            'occupancy_percentage': round((total_occupied / total_capacity) * 100, 1) if total_capacity > 0 else 0,
        },
    }


def validate_boarding_enrollment(student, dormitory, boarding_type, session):
    """
    Validate if a boarding enrollment can be created.
    
    Args:
        student (Student): The student
        dormitory (Dormitory): The dormitory
        boarding_type (str): Boarding type
        session (AcademicSession): The academic session
        
    Returns:
        tuple: (is_valid, errors_list)
    """
    from boarding.models import BoardingEnrollment
    
    errors = []
    
    # Check dormitory compatibility
    is_compatible, message = validate_dormitory_compatibility(dormitory, student)
    if not is_compatible:
        errors.append(message)
    
    # Check for existing enrollment
    existing = BoardingEnrollment.objects.filter(
        student=student,
        academic_session=session,
        status__in=['PENDING', 'ACTIVE']
    ).exists()
    
    if existing:
        errors.append(
            f"{student.get_full_name()} already has an active boarding enrollment for {session.name}"
        )
    
    # Check guardian consent for minors
    if student.get_age() < 18:
        # This would need guardian parameter - just a warning
        errors.append("Guardian consent is required for students under 18")
    
    # Validate boarding days for flexible boarders
    if boarding_type == 'FLEXI_BOARDER':
        # This would need boarding_days parameter
        pass
    
    return (len(errors) == 0, errors)


# =============================================================================
# ROLL NUMBER GENERATION
# =============================================================================

def generate_boarding_roll_number(*, dormitory, academic_session):
    """
    Generate sequential boarding roll numbers per dormitory & session.
    
    Format: 001, 002, 003, ...
    
    Args:
        dormitory (Dormitory): The dormitory
        academic_session (AcademicSession): The academic session
        
    Returns:
        str: Zero-padded 3-digit roll number
        
    Note:
        This function uses select_for_update() to prevent race conditions
        when multiple enrollments are created simultaneously.
    """
    from boarding.models import BoardingEnrollment

    with transaction.atomic():
        # Lock the table to prevent race conditions
        last = (
            BoardingEnrollment.objects
            .select_for_update()
            .filter(
                dormitory=dormitory,
                academic_session=academic_session
            )
            .exclude(boarding_roll_number__isnull=True)
            .exclude(boarding_roll_number='')
            .order_by('-boarding_roll_number')
            .first()
        )

        if last and last.boarding_roll_number.isdigit():
            next_number = int(last.boarding_roll_number) + 1
        else:
            # First enrollment in this dormitory/session
            next_number = 1

        # Format as zero-padded 3-digit number
        return f"{next_number:03d}"


def reset_dormitory_roll_numbers(dormitory, academic_session):
    """
    Reset and regenerate roll numbers for an entire dormitory.
    Useful when students are reordered or roll numbers need to be sequential.
    
    Args:
        dormitory (Dormitory): The dormitory
        academic_session (AcademicSession): The academic session
        
    Returns:
        int: Number of roll numbers regenerated
    """
    from boarding.models import BoardingEnrollment
    
    with transaction.atomic():
        # Get all enrollments for this dormitory/session, ordered by student name
        enrollments = BoardingEnrollment.objects.filter(
            dormitory=dormitory,
            academic_session=academic_session,
            status='ACTIVE'
        ).select_for_update().order_by('student__last_name', 'student__first_name')
        
        count = 0
        for index, enrollment in enumerate(enrollments, start=1):
            enrollment.boarding_roll_number = f"{index:03d}"
            enrollment.save(update_fields=['boarding_roll_number'])
            count += 1
        
        logger.info(
            f"Reset {count} boarding roll numbers for {dormitory.name} - {academic_session.name}"
        )
        
        return count


# =============================================================================
# BOARDING FEE CALCULATIONS
# =============================================================================

def calculate_boarding_fees(boarding_type, include_meals=True, include_laundry=False):
    """
    Calculate boarding fees based on type and additional services.
    
    Args:
        boarding_type (str): 'FULL_BOARDER', 'WEEKLY_BOARDER', 'FLEXI_BOARDER'
        include_meals (bool): Include meal fees
        include_laundry (bool): Include laundry fees
        
    Returns:
        dict: Fee breakdown
    """
    # Base boarding rates (could be from settings/database)
    BASE_RATES = {
        'FULL_BOARDER': Decimal('800000.00'),
        'WEEKLY_BOARDER': Decimal('500000.00'),
        'FLEXI_BOARDER': Decimal('300000.00'),
    }
    
    # Additional service rates
    MEALS_FEE = Decimal('200000.00')
    LAUNDRY_FEE = Decimal('50000.00')
    
    boarding_fee = BASE_RATES.get(boarding_type, Decimal('800000.00'))
    meals_fee = MEALS_FEE if include_meals else Decimal('0.00')
    laundry_fee = LAUNDRY_FEE if include_laundry else Decimal('0.00')
    
    total = boarding_fee + meals_fee + laundry_fee
    
    return {
        'boarding_fee': boarding_fee,
        'meals_fee': meals_fee,
        'laundry_fee': laundry_fee,
        'total': total,
        'breakdown': {
            'base': boarding_fee,
            'meals': meals_fee,
            'laundry': laundry_fee,
        }
    }


def get_boarding_fee_summary(enrollment):
    """
    Get fee summary for a boarding enrollment.
    
    Args:
        enrollment (BoardingEnrollment): The enrollment
        
    Returns:
        dict: Fee summary
    """
    invoice = enrollment.boarding_invoice
    
    if not invoice:
        return {
            'has_invoice': False,
            'total_amount': Decimal('0.00'),
            'paid_amount': Decimal('0.00'),
            'balance': Decimal('0.00'),
        }
    
    return {
        'has_invoice': True,
        'invoice_number': invoice.invoice_number,
        'total_amount': invoice.total_amount,
        'paid_amount': invoice.paid_amount,
        'balance': invoice.balance,
        'status': invoice.status,
        'is_paid': invoice.status == 'PAID',
        'is_overdue': invoice.is_overdue,
    }


# =============================================================================
# DORMITORY REPORTING UTILITIES
# =============================================================================

def get_dormitory_resident_list(dormitory, session):
    """
    Get list of residents in a dormitory for a session.
    
    Args:
        dormitory (Dormitory): The dormitory
        session (AcademicSession): The academic session
        
    Returns:
        QuerySet: Residents with details
    """
    from boarding.models import BoardingEnrollment
    
    return BoardingEnrollment.objects.filter(
        dormitory=dormitory,
        academic_session=session,
        status='ACTIVE'
    ).select_related(
        'student',
        'student__current_academic_level',
        'boarding_invoice'
    ).order_by('boarding_roll_number', 'student__last_name')


def get_dormitory_residents_by_class(dormitory, session):
    """
    Get dormitory residents grouped by class.
    
    Args:
        dormitory (Dormitory): The dormitory
        session (AcademicSession): The academic session
        
    Returns:
        dict: Residents grouped by class
    """
    residents = get_dormitory_resident_list(dormitory, session)
    
    grouped = {}
    for enrollment in residents:
        student = enrollment.student
        level = student.current_academic_level
        
        if level:
            level_name = str(level)
            if level_name not in grouped:
                grouped[level_name] = []
            grouped[level_name].append(enrollment)
    
    return grouped


def get_dormitory_financial_summary(dormitory, session):
    """
    Get financial summary for a dormitory.
    
    Args:
        dormitory (Dormitory): The dormitory
        session (AcademicSession): The academic session
        
    Returns:
        dict: Financial summary
    """
    from boarding.models import BoardingEnrollment
    from django.db.models import Sum, Count, Q
    
    enrollments = BoardingEnrollment.objects.filter(
        dormitory=dormitory,
        academic_session=session,
        status='ACTIVE'
    )
    
    # Get invoice totals
    invoice_stats = enrollments.filter(
        boarding_invoice__isnull=False
    ).aggregate(
        total_invoiced=Sum('boarding_invoice__total_amount'),
        total_paid=Sum('boarding_invoice__paid_amount'),
        total_balance=Sum('boarding_invoice__balance')
    )
    
    # Count payment statuses
    paid_count = enrollments.filter(
        boarding_invoice__status='PAID'
    ).count()
    
    pending_count = enrollments.filter(
        Q(boarding_invoice__status='PENDING') | 
        Q(boarding_invoice__status='PARTIALLY_PAID')
    ).count()
    
    return {
        'total_enrollments': enrollments.count(),
        'total_invoiced': invoice_stats['total_invoiced'] or Decimal('0.00'),
        'total_paid': invoice_stats['total_paid'] or Decimal('0.00'),
        'total_balance': invoice_stats['total_balance'] or Decimal('0.00'),
        'paid_count': paid_count,
        'pending_count': pending_count,
        'collection_rate': round((invoice_stats['total_paid'] or 0) / (invoice_stats['total_invoiced'] or 1) * 100, 1) if invoice_stats['total_invoiced'] else 0,
    }


# =============================================================================
# VALIDATION UTILITIES
# =============================================================================

def validate_boarding_days(boarding_days):
    """
    Validate boarding days for flexible boarders.
    
    Args:
        boarding_days (list): List of day names
        
    Returns:
        tuple: (is_valid, error_message)
    """
    valid_days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    
    if not isinstance(boarding_days, list):
        return (False, "Boarding days must be a list")
    
    if len(boarding_days) == 0:
        return (False, "At least one boarding day must be specified")
    
    for day in boarding_days:
        if day not in valid_days:
            return (False, f"Invalid day: {day}. Must be one of {', '.join(valid_days)}")
    
    return (True, None)


def validate_room_assignment(dormitory, room_number, bed_number):
    """
    Validate room and bed assignment.
    
    Args:
        dormitory (Dormitory): The dormitory
        room_number (str): Room number
        bed_number (str): Bed number
        
    Returns:
        tuple: (is_valid, error_message)
    """
    # Basic validation - could be enhanced with actual room/bed tracking
    if not room_number:
        return (False, "Room number is required")
    
    # Check if room/bed already occupied (would need separate Room model)
    # This is a placeholder for more complex validation
    
    return (True, None)


# =============================================================================
# QUERY HELPERS
# =============================================================================

def get_students_without_boarding(session):
    """
    Get students who are not enrolled in boarding for a session.
    
    Args:
        session (AcademicSession): The academic session
        
    Returns:
        QuerySet: Students without boarding enrollment
    """
    from students.models import Student
    from boarding.models import BoardingEnrollment
    
    # Get students with active boarding
    students_with_boarding = BoardingEnrollment.objects.filter(
        academic_session=session,
        status__in=['PENDING', 'ACTIVE']
    ).values_list('student_id', flat=True)
    
    # Return students without boarding
    return Student.objects.filter(
        enrollment_status='ACTIVE'
    ).exclude(
        id__in=students_with_boarding
    )


def get_pending_boarding_approvals(session=None):
    """
    Get boarding enrollments pending approval.
    
    Args:
        session (AcademicSession): Optional - filter by session
        
    Returns:
        QuerySet: Pending enrollments
    """
    from boarding.models import BoardingEnrollment
    
    enrollments = BoardingEnrollment.objects.filter(
        status='PENDING'
    ).select_related('student', 'dormitory', 'academic_session')
    
    if session:
        enrollments = enrollments.filter(academic_session=session)
    
    return enrollments.order_by('-created_at')


def get_expiring_boarding_enrollments(days=30):
    """
    Get boarding enrollments expiring within specified days.
    
    Args:
        days (int): Number of days to look ahead
        
    Returns:
        QuerySet: Expiring enrollments
    """
    from boarding.models import BoardingEnrollment
    
    today = timezone.now().date()
    future_date = today + timedelta(days=days)
    
    return BoardingEnrollment.objects.filter(
        status='ACTIVE',
        effective_end_date__isnull=False,
        effective_end_date__gte=today,
        effective_end_date__lte=future_date
    ).select_related('student', 'dormitory').order_by('effective_end_date')