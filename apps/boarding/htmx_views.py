# boarding/htmx_views.py

from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.db.models import Q, Count, Sum, Avg, F, DecimalField, Case, When
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from datetime import timedelta
from decimal import Decimal
import logging

from .models import (
    Dormitory,
    BoardingEnrollment
)
from utils.utils import parse_filters, paginate_queryset

logger = logging.getLogger(__name__)


# =============================================================================
# DORMITORY SEARCH
# =============================================================================

def dormitory_search(request):
    """HTMX-compatible dormitory search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'dormitory_type', 'is_active', 'is_available_for_new_admissions',
        'maintenance_status', 'has_wifi', 'has_bathroom', 'has_study_area',
        'has_common_room', 'has_laundry', 'has_kitchen', 'has_security',
        'min_capacity', 'max_capacity', 'occupancy_level', 'needs_maintenance'
    ])
    
    query = filters['q']
    dormitory_type = filters['dormitory_type']
    is_active = filters['is_active']
    is_available_for_new_admissions = filters['is_available_for_new_admissions']
    maintenance_status = filters['maintenance_status']
    has_wifi = filters['has_wifi']
    has_bathroom = filters['has_bathroom']
    has_study_area = filters['has_study_area']
    has_common_room = filters['has_common_room']
    has_laundry = filters['has_laundry']
    has_kitchen = filters['has_kitchen']
    has_security = filters['has_security']
    min_capacity = filters['min_capacity']
    max_capacity = filters['max_capacity']
    occupancy_level = filters['occupancy_level']
    needs_maintenance = filters['needs_maintenance']
    
    # Build queryset
    dormitories = Dormitory.objects.select_related(
        'dormitory_master',
        'assistant_dormitory_master'
    ).annotate(
        active_enrollment_count=Count(
            'boarding_enrollments',
            filter=Q(boarding_enrollments__status='ACTIVE'),
            distinct=True
        ),
        available_beds=F('total_capacity') - F('current_occupancy'),
        occupancy_ratio=Case(
            When(total_capacity=0, then=0),
            default=F('current_occupancy') * 100.0 / F('total_capacity'),
            output_field=DecimalField(max_digits=5, decimal_places=2)
        )
    ).order_by('dormitory_type', 'name')
    
    # Apply text search
    if query:
        dormitories = dormitories.filter(
            Q(name__icontains=query) |
            Q(code__icontains=query) |
            Q(building__icontains=query) |
            Q(wing__icontains=query) |
            Q(description__icontains=query)
        )
    
    # Apply filters
    if dormitory_type:
        dormitories = dormitories.filter(dormitory_type=dormitory_type)
    
    if maintenance_status:
        dormitories = dormitories.filter(maintenance_status=maintenance_status)
    
    if is_active is not None:
        dormitories = dormitories.filter(is_active=(is_active.lower() == 'true'))
    
    if is_available_for_new_admissions is not None:
        dormitories = dormitories.filter(
            is_available_for_new_admissions=(is_available_for_new_admissions.lower() == 'true')
        )
    
    # Facility filters
    if has_wifi and has_wifi.lower() == 'true':
        dormitories = dormitories.filter(has_wifi=True)
    
    if has_bathroom and has_bathroom.lower() == 'true':
        dormitories = dormitories.filter(has_bathroom=True)
    
    if has_study_area and has_study_area.lower() == 'true':
        dormitories = dormitories.filter(has_study_area=True)
    
    if has_common_room and has_common_room.lower() == 'true':
        dormitories = dormitories.filter(has_common_room=True)
    
    if has_laundry and has_laundry.lower() == 'true':
        dormitories = dormitories.filter(has_laundry=True)
    
    if has_kitchen and has_kitchen.lower() == 'true':
        dormitories = dormitories.filter(has_kitchen=True)
    
    if has_security and has_security.lower() == 'true':
        dormitories = dormitories.filter(has_security=True)
    
    # Capacity filters
    if min_capacity:
        try:
            dormitories = dormitories.filter(total_capacity__gte=int(min_capacity))
        except:
            pass
    
    if max_capacity:
        try:
            dormitories = dormitories.filter(total_capacity__lte=int(max_capacity))
        except:
            pass
    
    # Occupancy level filter
    if occupancy_level:
        if occupancy_level == 'low':
            dormitories = dormitories.filter(occupancy_ratio__lt=70)
        elif occupancy_level == 'medium':
            dormitories = dormitories.filter(occupancy_ratio__gte=70, occupancy_ratio__lt=90)
        elif occupancy_level == 'high':
            dormitories = dormitories.filter(occupancy_ratio__gte=90)
        elif occupancy_level == 'full':
            dormitories = dormitories.filter(current_occupancy__gte=F('total_capacity'))
    
    # Needs maintenance filter
    if needs_maintenance and needs_maintenance.lower() == 'true':
        today = timezone.now().date()
        dormitories = dormitories.filter(
            next_maintenance_due__lte=today
        )
    
    # Paginate
    dormitories_page, paginator = paginate_queryset(request, dormitories, per_page=20)
    
    # Calculate stats
    total = dormitories.count()
    
    stats = {
        'total': total,
        'active': dormitories.filter(is_active=True).count(),
        'boys': dormitories.filter(dormitory_type='BOYS').count(),
        'girls': dormitories.filter(dormitory_type='GIRLS').count(),
        'mixed': dormitories.filter(dormitory_type='MIXED').count(),
        'total_capacity': dormitories.aggregate(Sum('total_capacity'))['total_capacity__sum'] or 0,
        'total_occupancy': dormitories.aggregate(Sum('current_occupancy'))['current_occupancy__sum'] or 0,
        'available_beds': dormitories.aggregate(Sum('available_beds'))['available_beds__sum'] or 0,
        'full_dormitories': dormitories.filter(
            current_occupancy__gte=F('total_capacity')
        ).count(),
        'needs_maintenance': dormitories.filter(
            next_maintenance_due__lte=timezone.now().date()
        ).count(),
        'avg_occupancy': dormitories.aggregate(Avg('occupancy_ratio'))['occupancy_ratio__avg'] or 0,
    }
    
    return render(request, 'boarding/dormitories/_dormitory_results.html', {
        'dormitories_page': dormitories_page,
        'stats': stats,
    })


# =============================================================================
# BOARDING ENROLLMENT SEARCH
# =============================================================================

def boarding_enrollment_search(request):
    """HTMX-compatible boarding enrollment search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'status', 'boarding_type', 'student', 'dormitory',
        'academic_session', 'guardian_consent', 'has_invoice',
        'start_date', 'end_date', 'room_number', 'bed_number'
    ])
    
    query = filters['q']
    status = filters['status']
    boarding_type = filters['boarding_type']
    student = filters['student']
    dormitory = filters['dormitory']
    academic_session = filters['academic_session']
    guardian_consent = filters['guardian_consent']
    has_invoice = filters['has_invoice']
    start_date = filters['start_date']
    end_date = filters['end_date']
    room_number = filters['room_number']
    bed_number = filters['bed_number']
    
    # Build queryset
    enrollments = BoardingEnrollment.objects.select_related(
        'student__current_academic_level',
        'academic_session',
        'dormitory',
        'consenting_guardian',
        'approved_by',
        'boarding_invoice'
    ).order_by('-academic_session__start_date', 'dormitory', 'boarding_roll_number')
    
    # Apply text search
    if query:
        enrollments = enrollments.filter(
            Q(student__first_name__icontains=query) |
            Q(student__last_name__icontains=query) |
            Q(student__admission_number__icontains=query) |
            Q(boarding_roll_number__icontains=query) |
            Q(room_number__icontains=query) |
            Q(bed_number__icontains=query)
        )
    
    # Apply filters
    if status:
        enrollments = enrollments.filter(status=status)
    
    if boarding_type:
        enrollments = enrollments.filter(boarding_type=boarding_type)
    
    if student:
        enrollments = enrollments.filter(student_id=student)
    
    if dormitory:
        enrollments = enrollments.filter(dormitory_id=dormitory)
    
    if academic_session:
        enrollments = enrollments.filter(academic_session_id=academic_session)
    
    if room_number:
        enrollments = enrollments.filter(room_number__icontains=room_number)
    
    if bed_number:
        enrollments = enrollments.filter(bed_number__icontains=bed_number)
    
    if guardian_consent is not None:
        enrollments = enrollments.filter(guardian_consent=(guardian_consent.lower() == 'true'))
    
    if has_invoice and has_invoice.lower() == 'true':
        enrollments = enrollments.exclude(Q(boarding_invoice__isnull=True))
    elif has_invoice and has_invoice.lower() == 'false':
        enrollments = enrollments.filter(boarding_invoice__isnull=True)
    
    if start_date:
        enrollments = enrollments.filter(effective_start_date__gte=start_date)
    
    if end_date:
        enrollments = enrollments.filter(
            Q(effective_end_date__lte=end_date) | Q(effective_end_date__isnull=True)
        )
    
    # Paginate
    enrollments_page, paginator = paginate_queryset(request, enrollments, per_page=20)
    
    # Calculate stats
    total = enrollments.count()
    
    stats = {
        'total': total,
        'pending': enrollments.filter(status='PENDING').count(),
        'active': enrollments.filter(status='ACTIVE').count(),
        'suspended': enrollments.filter(status='SUSPENDED').count(),
        'terminated': enrollments.filter(status='TERMINATED').count(),
        'completed': enrollments.filter(status='COMPLETED').count(),
        'full_boarders': enrollments.filter(boarding_type='FULL_BOARDER').count(),
        'weekly_boarders': enrollments.filter(boarding_type='WEEKLY_BOARDER').count(),
        'flexi_boarders': enrollments.filter(boarding_type='FLEXI_BOARDER').count(),
        'with_consent': enrollments.filter(guardian_consent=True).count(),
        'without_consent': enrollments.filter(guardian_consent=False).count(),
        'with_invoice': enrollments.exclude(boarding_invoice__isnull=True).count(),
        'without_invoice': enrollments.filter(boarding_invoice__isnull=True).count(),
        'unique_students': enrollments.values('student').distinct().count(),
        'unique_dormitories': enrollments.values('dormitory').distinct().count(),
    }
    
    return render(request, 'boarding/enrollments/_enrollment_results.html', {
        'enrollments_page': enrollments_page,
        'stats': stats,
    })


# =============================================================================
# QUICK STATS ENDPOINTS
# =============================================================================

@require_http_methods(["GET"])
def dormitory_quick_stats(request):
    """Get quick statistics for dormitories"""
    
    today = timezone.now().date()
    
    dormitories = Dormitory.objects.filter(is_active=True).aggregate(
        total_capacity=Sum('total_capacity'),
        total_occupancy=Sum('current_occupancy')
    )
    
    total_capacity = dormitories['total_capacity'] or 0
    total_occupancy = dormitories['total_occupancy'] or 0
    
    stats = {
        'total_dormitories': Dormitory.objects.filter(is_active=True).count(),
        'boys_dormitories': Dormitory.objects.filter(is_active=True, dormitory_type='BOYS').count(),
        'girls_dormitories': Dormitory.objects.filter(is_active=True, dormitory_type='GIRLS').count(),
        'total_capacity': total_capacity,
        'total_occupancy': total_occupancy,
        'available_beds': total_capacity - total_occupancy,
        'occupancy_percentage': round((total_occupancy / total_capacity * 100) if total_capacity > 0 else 0, 1),
        'full_dormitories': Dormitory.objects.filter(is_active=True, current_occupancy__gte=F('total_capacity')).count(),
        'needs_maintenance': Dormitory.objects.filter(is_active=True, next_maintenance_due__lte=today).count(),
    }
    
    return JsonResponse(stats)


@require_http_methods(["GET"])
def boarding_enrollment_quick_stats(request):
    """Get quick statistics for boarding enrollments"""
    
    stats = {
        'total_enrollments': BoardingEnrollment.objects.count(),
        'active': BoardingEnrollment.objects.filter(status='ACTIVE').count(),
        'pending': BoardingEnrollment.objects.filter(status='PENDING').count(),
        'full_boarders': BoardingEnrollment.objects.filter(status='ACTIVE', boarding_type='FULL_BOARDER').count(),
        'pending_consent': BoardingEnrollment.objects.filter(status__in=['PENDING', 'ACTIVE'], guardian_consent=False).count(),
    }
    
    return JsonResponse(stats)