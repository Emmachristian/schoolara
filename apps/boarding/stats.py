# boarding/stats.py

from django.db.models import Count, Avg, Q, Max, Min, Sum, F
from django.db.models.functions import TruncMonth
from django.utils import timezone
from datetime import date, timedelta

# =============================================================================
# BOARDING STATISTICS UTILITIES
# =============================================================================

def get_boarding_statistics():
    """
    Get comprehensive statistics for boarding system
    Returns a dictionary with various boarding statistics
    
    Returns:
        dict: Dictionary containing boarding statistics including:
            - total_boarders: Total count of active boarding students
            - boarding_type_counts: Dictionary with counts for each boarding type
            - dormitory_occupancy: Dictionary with dormitory occupancy statistics
            - gender_distribution: Distribution of boarders by gender
            - enrollment_status_counts: Counts for each enrollment status
            - avg_enrollment_duration: Average boarding enrollment duration in days
            - occupancy_rate: Overall occupancy rate percentage
            - pending_approvals: Number of enrollments pending approval
    """
    from .models import BoardingEnrollment, Dormitory
    
    enrollments = BoardingEnrollment.objects.all()
    active_enrollments = enrollments.filter(status='ACTIVE')
    
    # Total boarders
    total_boarders = active_enrollments.count()
    
    # Boarding type breakdown
    boarding_type_counts = {}
    for type_code, type_name in BoardingEnrollment.BOARDING_TYPE_CHOICES:
        boarding_type_counts[type_code] = active_enrollments.filter(
            boarding_type=type_code
        ).count()
    
    # Enrollment status breakdown
    enrollment_status_counts = {}
    for status_code, status_name in BoardingEnrollment.ENROLLMENT_STATUS_CHOICES:
        enrollment_status_counts[status_code] = enrollments.filter(
            status=status_code
        ).count()
    
    # Gender distribution
    gender_distribution = {
        'male': active_enrollments.filter(student__gender='M').count(),
        'female': active_enrollments.filter(student__gender='F').count(),
    }
    
    # Calculate average enrollment duration
    completed_enrollments = enrollments.filter(
        status='COMPLETED',
        effective_end_date__isnull=False
    )
    
    total_duration = 0
    duration_count = 0
    for enrollment in completed_enrollments:
        duration = (enrollment.effective_end_date - enrollment.effective_start_date).days
        total_duration += duration
        duration_count += 1
    
    avg_enrollment_duration = (total_duration / duration_count) if duration_count > 0 else 0
    
    # Dormitory occupancy statistics
    dormitories = Dormitory.objects.filter(is_active=True)
    total_capacity = dormitories.aggregate(Sum('total_capacity'))['total_capacity__sum'] or 0
    total_occupied = dormitories.aggregate(Sum('current_occupancy'))['current_occupancy__sum'] or 0
    
    occupancy_rate = (total_occupied / total_capacity * 100) if total_capacity > 0 else 0
    
    dormitory_occupancy = {
        'total_capacity': total_capacity,
        'total_occupied': total_occupied,
        'total_available': total_capacity - total_occupied,
        'occupancy_rate': round(occupancy_rate, 1),
        'dormitory_count': dormitories.count(),
    }
    
    # Pending approvals
    pending_approvals = enrollments.filter(status='PENDING').count()
    
    # Male/Female percentages
    male_percentage = (gender_distribution['male'] / total_boarders * 100) if total_boarders > 0 else 0
    female_percentage = (gender_distribution['female'] / total_boarders * 100) if total_boarders > 0 else 0
    
    return {
        'total_boarders': total_boarders,
        'boarding_type_counts': boarding_type_counts,
        'enrollment_status_counts': enrollment_status_counts,
        'gender_distribution': gender_distribution,
        'male_percentage': round(male_percentage, 1),
        'female_percentage': round(female_percentage, 1),
        'avg_enrollment_duration': round(avg_enrollment_duration, 1),
        'dormitory_occupancy': dormitory_occupancy,
        'pending_approvals': pending_approvals,
    }


def get_dormitory_statistics():
    """
    Get detailed statistics for all dormitories
    
    Returns:
        dict: Dictionary containing dormitory statistics including:
            - total_dormitories: Total count of dormitories
            - active_dormitories: Count of active dormitories
            - dormitory_breakdown: List of dormitories with individual stats
            - occupancy_levels: Count of dormitories by occupancy level
            - maintenance_status_counts: Count of dormitories by maintenance status
            - avg_occupancy_rate: Average occupancy rate across all dormitories
    """
    from .models import Dormitory
    
    dormitories = Dormitory.objects.all()
    active_dormitories = dormitories.filter(is_active=True)
    
    # Basic counts
    total_dormitories = dormitories.count()
    active_count = active_dormitories.count()
    
    # Dormitory type breakdown
    type_breakdown = {}
    for type_code, type_name in Dormitory.DORMITORY_TYPE_CHOICES:
        type_breakdown[type_code] = dormitories.filter(
            dormitory_type=type_code
        ).count()
    
    # Maintenance status breakdown
    maintenance_status_counts = {}
    for status_code, status_name in Dormitory.MAINTENANCE_STATUS_CHOICES:
        maintenance_status_counts[status_code] = dormitories.filter(
            maintenance_status=status_code
        ).count()
    
    # Occupancy levels
    occupancy_levels = {
        'empty': 0,
        'low': 0,
        'medium': 0,
        'high': 0,
    }
    
    total_occupancy_rate = 0
    dormitory_count_with_capacity = 0
    
    # Individual dormitory stats
    dormitory_breakdown = []
    for dorm in active_dormitories:
        occupancy_percentage = dorm.get_occupancy_percentage()
        occupancy_level = dorm.get_occupancy_level()
        
        occupancy_levels[occupancy_level] += 1
        
        if dorm.total_capacity > 0:
            total_occupancy_rate += occupancy_percentage
            dormitory_count_with_capacity += 1
        
        dormitory_breakdown.append({
            'id': dorm.id,
            'name': dorm.name,
            'type': dorm.get_dormitory_type_display(),
            'capacity': dorm.total_capacity,
            'occupancy': dorm.current_occupancy,
            'available': dorm.get_available_capacity(),
            'occupancy_percentage': occupancy_percentage,
            'occupancy_level': occupancy_level,
            'is_full': dorm.is_full,
            'maintenance_status': dorm.get_maintenance_status_display(),
        })
    
    avg_occupancy_rate = (
        total_occupancy_rate / dormitory_count_with_capacity
    ) if dormitory_count_with_capacity > 0 else 0
    
    return {
        'total_dormitories': total_dormitories,
        'active_dormitories': active_count,
        'type_breakdown': type_breakdown,
        'maintenance_status_counts': maintenance_status_counts,
        'occupancy_levels': occupancy_levels,
        'avg_occupancy_rate': round(avg_occupancy_rate, 1),
        'dormitory_breakdown': dormitory_breakdown,
    }


def get_active_boarders_count():
    """
    Get count of active boarding students
    
    Returns:
        int: Number of active boarding students
    """
    from .models import BoardingEnrollment
    return BoardingEnrollment.objects.filter(status='ACTIVE').count()


def get_boarding_type_count(boarding_type):
    """
    Get count of students by boarding type
    
    Args:
        boarding_type (str): Boarding type code ('FULL_BOARDER', 'WEEKLY_BOARDER', 'FLEXI_BOARDER')
        
    Returns:
        int: Number of active boarding students with specified type
    """
    from .models import BoardingEnrollment
    return BoardingEnrollment.objects.filter(
        status='ACTIVE',
        boarding_type=boarding_type
    ).count()


def get_dormitory_occupancy_rate(dormitory_id):
    """
    Get occupancy rate for a specific dormitory
    
    Args:
        dormitory_id (int): ID of the dormitory
        
    Returns:
        float: Occupancy rate as percentage, or 0 if dormitory not found
    """
    from .models import Dormitory
    
    try:
        dormitory = Dormitory.objects.get(id=dormitory_id)
        return dormitory.get_occupancy_percentage()
    except Dormitory.DoesNotExist:
        return 0


def get_boarding_enrollment_trends(months=6):
    """
    Get boarding enrollment trends over specified months
    
    Args:
        months (int): Number of months to analyze (default: 6)
        
    Returns:
        list: List of dictionaries with month and enrollment count
    """
    from .models import BoardingEnrollment
    
    start_date = timezone.now() - timedelta(days=months * 30)
    
    trends = BoardingEnrollment.objects.filter(
        enrollment_date__gte=start_date
    ).annotate(
        month=TruncMonth('enrollment_date')
    ).values('month').annotate(
        count=Count('id')
    ).order_by('month')
    
    return list(trends)


def get_pending_approvals_count():
    """
    Get count of boarding enrollments pending approval
    
    Returns:
        int: Number of pending enrollments
    """
    from .models import BoardingEnrollment
    return BoardingEnrollment.objects.filter(status='PENDING').count()


def get_dormitory_gender_distribution(dormitory_id):
    """
    Get gender distribution for a specific dormitory
    
    Args:
        dormitory_id (int): ID of the dormitory
        
    Returns:
        dict: Dictionary with male and female counts
    """
    from .models import BoardingEnrollment
    
    active_enrollments = BoardingEnrollment.objects.filter(
        dormitory_id=dormitory_id,
        status='ACTIVE'
    )
    
    return {
        'male': active_enrollments.filter(student__gender='M').count(),
        'female': active_enrollments.filter(student__gender='F').count(),
    }


def get_boarding_statistics_by_session(academic_session_id):
    """
    Get boarding statistics for a specific academic session
    
    Args:
        academic_session_id (int): ID of the academic session
        
    Returns:
        dict: Dictionary containing session-specific boarding statistics
    """
    from .models import BoardingEnrollment
    
    enrollments = BoardingEnrollment.objects.filter(
        academic_session_id=academic_session_id
    )
    
    active_enrollments = enrollments.filter(status='ACTIVE')
    
    # Boarding type breakdown
    boarding_type_counts = {}
    for type_code, type_name in BoardingEnrollment.BOARDING_TYPE_CHOICES:
        boarding_type_counts[type_code] = active_enrollments.filter(
            boarding_type=type_code
        ).count()
    
    # Status breakdown
    status_counts = {}
    for status_code, status_name in BoardingEnrollment.ENROLLMENT_STATUS_CHOICES:
        status_counts[status_code] = enrollments.filter(
            status=status_code
        ).count()
    
    return {
        'total_enrollments': enrollments.count(),
        'active_enrollments': active_enrollments.count(),
        'boarding_type_counts': boarding_type_counts,
        'status_counts': status_counts,
        'pending_approvals': enrollments.filter(status='PENDING').count(),
    }


def get_dormitories_needing_maintenance():
    """
    Get list of dormitories that need maintenance
    
    Returns:
        QuerySet: Dormitories with maintenance due or in poor condition
    """
    from .models import Dormitory
    
    today = timezone.now().date()
    
    return Dormitory.objects.filter(
        Q(next_maintenance_due__lte=today) |
        Q(maintenance_status__in=['NEEDS_REPAIR', 'FAIR'])
    ).filter(is_active=True)


def get_dormitory_capacity_report():
    """
    Get comprehensive capacity report for all dormitories
    
    Returns:
        dict: Dictionary with capacity analysis by dormitory type
    """
    from .models import Dormitory
    
    dormitories = Dormitory.objects.filter(is_active=True)
    
    report = {
        'overall': {
            'total_capacity': 0,
            'current_occupancy': 0,
            'available_capacity': 0,
            'occupancy_rate': 0,
        }
    }
    
    # Get overall stats
    overall_capacity = dormitories.aggregate(
        total_cap=Sum('total_capacity'),
        total_occ=Sum('current_occupancy')
    )
    
    total_cap = overall_capacity['total_cap'] or 0
    total_occ = overall_capacity['total_occ'] or 0
    
    report['overall']['total_capacity'] = total_cap
    report['overall']['current_occupancy'] = total_occ
    report['overall']['available_capacity'] = total_cap - total_occ
    report['overall']['occupancy_rate'] = (
        round(total_occ / total_cap * 100, 1) if total_cap > 0 else 0
    )
    
    # Break down by dormitory type
    for type_code, type_name in Dormitory.DORMITORY_TYPE_CHOICES:
        type_dorms = dormitories.filter(dormitory_type=type_code)
        type_stats = type_dorms.aggregate(
            total_cap=Sum('total_capacity'),
            total_occ=Sum('current_occupancy')
        )
        
        type_cap = type_stats['total_cap'] or 0
        type_occ = type_stats['total_occ'] or 0
        
        report[type_code] = {
            'type_name': type_name,
            'dormitory_count': type_dorms.count(),
            'total_capacity': type_cap,
            'current_occupancy': type_occ,
            'available_capacity': type_cap - type_occ,
            'occupancy_rate': (
                round(type_occ / type_cap * 100, 1) if type_cap > 0 else 0
            ),
        }
    
    return report


def get_students_without_boarding():
    """
    Get count of active students without boarding enrollment
    
    Returns:
        int: Number of active students not enrolled in boarding
    """
    from students.models import Student
    from .models import BoardingEnrollment
    
    # Get all active students
    active_students = Student.objects.filter(enrollment_status='ACTIVE')
    
    # Get students with active boarding enrollment
    students_with_boarding = BoardingEnrollment.objects.filter(
        status='ACTIVE'
    ).values_list('student_id', flat=True)
    
    # Count students without boarding
    return active_students.exclude(id__in=students_with_boarding).count()


def get_boarding_consent_status():
    """
    Get statistics on guardian consent for boarding
    
    Returns:
        dict: Dictionary with consent statistics
    """
    from .models import BoardingEnrollment
    
    active_enrollments = BoardingEnrollment.objects.filter(status='ACTIVE')
    
    with_consent = active_enrollments.filter(guardian_consent=True).count()
    without_consent = active_enrollments.filter(guardian_consent=False).count()
    
    total = active_enrollments.count()
    consent_rate = (with_consent / total * 100) if total > 0 else 0
    
    return {
        'with_consent': with_consent,
        'without_consent': without_consent,
        'total_active': total,
        'consent_rate': round(consent_rate, 1),
    }