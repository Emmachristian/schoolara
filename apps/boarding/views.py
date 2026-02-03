# boarding/views.py

"""
Boarding Management Views

Comprehensive view functions for:
- Dormitories and Dormitory Management
- Boarding Enrollments and Account Management
- Bulk Enrollment Process
- Reports and Analytics

All views follow the same patterns as savings/views.py
Uses SweetAlert2 for all notifications via Django messages
HTMX support for dynamic content
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.contrib import messages
from django.db.models import Q, Count, Sum, Avg, F, Max, Min, Case, When, FloatField
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from django.db import transaction
from datetime import timedelta, date, datetime
from decimal import Decimal
import logging

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from core.utils import get_school_today, get_school_current_time, format_money

from .models import Dormitory, BoardingEnrollment
from students.models import Student
from academics.models import AcademicSession, AcademicLevel, Class

from .forms import (
    DormitoryFilterForm,
    BoardingEnrollmentFilterForm,
    DormitoryForm,
    DormitoryQuickAddForm,
    BoardingEnrollmentForm,
    BoardingApprovalForm,
    BoardingTerminationForm,
    BulkBoardingEnrollmentStudentSelectionForm,
    BulkBoardingEnrollmentConfirmationForm,
)

logger = logging.getLogger(__name__)


# =============================================================================
# DASHBOARD
# =============================================================================

@login_required
def boarding_dashboard(request):
    """Main boarding dashboard with overview statistics"""
    
    try:
        # Get comprehensive statistics
        dormitory_stats = Dormitory.objects.aggregate(
            total_dormitories=Count('id'),
            active_dormitories=Count('id', filter=Q(is_active=True)),
            boys_dormitories=Count('id', filter=Q(dormitory_type='BOYS')),
            girls_dormitories=Count('id', filter=Q(dormitory_type='GIRLS')),
            mixed_dormitories=Count('id', filter=Q(dormitory_type='MIXED')),
            total_capacity=Sum('total_capacity'),
            total_occupancy=Sum('current_occupancy'),
            available_beds=Sum(F('total_capacity') - F('current_occupancy')),
            full_dormitories=Count('id', filter=Q(current_occupancy__gte=F('total_capacity'))),
            needs_maintenance=Count(
                'id', 
                filter=Q(next_maintenance_due__lte=get_school_today())
            ),
        )
        
        enrollment_stats = BoardingEnrollment.objects.aggregate(
            total_enrollments=Count('id'),
            pending_approval=Count('id', filter=Q(status='PENDING')),
            active_enrollments=Count('id', filter=Q(status='ACTIVE')),
            suspended_enrollments=Count('id', filter=Q(status='SUSPENDED')),
            terminated_enrollments=Count('id', filter=Q(status='TERMINATED')),
            full_boarders=Count('id', filter=Q(boarding_type='FULL_BOARDER', status='ACTIVE')),
            weekly_boarders=Count('id', filter=Q(boarding_type='WEEKLY_BOARDER', status='ACTIVE')),
            flexi_boarders=Count('id', filter=Q(boarding_type='FLEXI_BOARDER', status='ACTIVE')),
            with_consent=Count('id', filter=Q(guardian_consent=True)),
            without_consent=Count('id', filter=Q(guardian_consent=False)),
            with_invoice=Count('id', filter=Q(boarding_invoice__isnull=False)),
        )
        
    except Exception as e:
        logger.error(f"Error getting dashboard statistics: {e}")
        dormitory_stats = {}
        enrollment_stats = {}
    
    # Calculate occupancy percentage
    total_capacity = dormitory_stats.get('total_capacity') or 0
    total_occupancy = dormitory_stats.get('total_occupancy') or 0
    occupancy_percentage = round(
        (total_occupancy / total_capacity * 100) if total_capacity > 0 else 0, 
        1
    )
    
    # Get recent activities
    recent_enrollments = BoardingEnrollment.objects.select_related(
        'student', 'dormitory', 'academic_session'
    ).order_by('-created_at')[:10]
    
    pending_approvals = BoardingEnrollment.objects.select_related(
        'student', 'dormitory', 'academic_session'
    ).filter(status='PENDING').order_by('created_at')[:10]
    
    # Dormitories needing attention
    today = get_school_today()
    
    full_dormitories = Dormitory.objects.filter(
        is_active=True,
        current_occupancy__gte=F('total_capacity')
    ).order_by('dormitory_type', 'name')[:10]
    
    maintenance_due = Dormitory.objects.filter(
        is_active=True,
        next_maintenance_due__lte=today
    ).order_by('next_maintenance_due')[:10]
    
    # Enrollments needing attention
    missing_consent = BoardingEnrollment.objects.select_related(
        'student', 'dormitory'
    ).filter(
        status__in=['PENDING', 'ACTIVE'],
        guardian_consent=False
    ).order_by('enrollment_date')[:10]
    
    context = {
        'dormitory_stats': dormitory_stats,
        'enrollment_stats': enrollment_stats,
        'occupancy_percentage': occupancy_percentage,
        'recent_enrollments': recent_enrollments,
        'pending_approvals': pending_approvals,
        'full_dormitories': full_dormitories,
        'maintenance_due': maintenance_due,
        'missing_consent': missing_consent,
    }
    
    return render(request, 'boarding/dashboard.html', context)


# =============================================================================
# HELPER FUNCTIONS FOR FILTERING
# =============================================================================

def get_filtered_dormitories(request):
    """Helper function to get filtered dormitories queryset"""
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
            output_field=FloatField(),  # ⭐ Specify output_field
        ),
    ).order_by('dormitory_type', 'code')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    dormitory_type = request.GET.get('dormitory_type', '')
    is_active = request.GET.get('is_active', '')
    is_available_for_new_admissions = request.GET.get('is_available_for_new_admissions', '')
    maintenance_status = request.GET.get('maintenance_status', '')
    occupancy_level = request.GET.get('occupancy_level', '')
    dormitory_master = request.GET.get('dormitory_master', '')
    
    # Apply text search
    if query:
        words = query.strip().split()
        if words:
            combined_q = Q()
            for word in words:
                word_q = (
                    Q(name__icontains=word) |
                    Q(code__icontains=word) |
                    Q(building__icontains=word) |
                    Q(wing__icontains=word) |
                    Q(description__icontains=word)
                )
                combined_q &= word_q
            dormitories = dormitories.filter(combined_q)
    
    # Apply filters
    if dormitory_type:
        dormitories = dormitories.filter(dormitory_type=dormitory_type)
    
    if is_active:
        dormitories = dormitories.filter(is_active=(is_active.lower() == 'true'))
    
    if is_available_for_new_admissions:
        dormitories = dormitories.filter(
            is_available_for_new_admissions=(is_available_for_new_admissions.lower() == 'true')
        )
    
    if maintenance_status:
        dormitories = dormitories.filter(maintenance_status=maintenance_status)
    
    if dormitory_master:
        try:
            dormitories = dormitories.filter(dormitory_master_id=int(dormitory_master))
        except (ValueError, TypeError):
            pass
    
    # Occupancy level filter
    if occupancy_level:
        if occupancy_level == 'empty':
            dormitories = dormitories.filter(current_occupancy=0)
        elif occupancy_level == 'low':
            dormitories = dormitories.filter(occupancy_ratio__lt=70)
        elif occupancy_level == 'medium':
            dormitories = dormitories.filter(occupancy_ratio__gte=70, occupancy_ratio__lt=90)
        elif occupancy_level == 'high':
            dormitories = dormitories.filter(occupancy_ratio__gte=90)
    
    return dormitories


def get_filtered_boarding_enrollments(request):
    """Helper function to get filtered boarding enrollments queryset"""
    enrollments = BoardingEnrollment.objects.select_related(
        'student__current_academic_level',
        'academic_session',
        'dormitory',
        'consenting_guardian',
        'approved_by',
        'boarding_invoice'
    ).order_by('-academic_session__start_date', 'dormitory', 'boarding_roll_number')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    boarding_type = request.GET.get('boarding_type', '')
    dormitory = request.GET.get('dormitory', '')
    academic_session = request.GET.get('academic_session', '')
    guardian_consent = request.GET.get('guardian_consent', '')
    enrollment_date_from = request.GET.get('enrollment_date_from', '')
    enrollment_date_to = request.GET.get('enrollment_date_to', '')
    student_gender = request.GET.get('student_gender', '')
    
    # Apply text search
    if query:
        words = query.strip().split()
        if words:
            combined_q = Q()
            for word in words:
                word_q = (
                    Q(student__first_name__icontains=word) |
                    Q(student__last_name__icontains=word) |
                    Q(student__admission_number__icontains=word) |
                    Q(boarding_roll_number__icontains=word) |
                    Q(room_number__icontains=word) |
                    Q(bed_number__icontains=word)
                )
                combined_q &= word_q
            enrollments = enrollments.filter(combined_q)
    
    # Apply filters
    if status:
        enrollments = enrollments.filter(status=status)
    
    if boarding_type:
        enrollments = enrollments.filter(boarding_type=boarding_type)
    
    if dormitory:
        try:
            enrollments = enrollments.filter(dormitory_id=int(dormitory))
        except (ValueError, TypeError):
            pass
    
    if academic_session:
        try:
            enrollments = enrollments.filter(academic_session_id=int(academic_session))
        except (ValueError, TypeError):
            pass
    
    if guardian_consent:
        enrollments = enrollments.filter(guardian_consent=(guardian_consent.lower() == 'true'))
    
    if enrollment_date_from:
        enrollments = enrollments.filter(enrollment_date__gte=enrollment_date_from)
    
    if enrollment_date_to:
        enrollments = enrollments.filter(enrollment_date__lte=enrollment_date_to)
    
    if student_gender:
        enrollments = enrollments.filter(student__gender=student_gender)
    
    return enrollments


# =============================================================================
# DORMITORY VIEWS
# =============================================================================

@login_required
def dormitory_list(request):
    """
    Handle BOTH full page loads AND HTMX search/filter requests.
    
    - Normal request: Returns full page with filter form
    - HTMX request: Returns only the results partial (table + stats)
    
    This single view handles all dormitory listing needs.
    """
    filter_form = DormitoryFilterForm(request.GET or None)
    dormitories = get_filtered_dormitories(request)
    
    # Calculate statistics - SEPARATE from the annotated queryset
    # Get a fresh queryset without annotations for aggregation
    stats_queryset = Dormitory.objects.all()
    
    # Apply the same filters as dormitories (excluding annotations)
    query = request.GET.get('q', '').strip()
    if query:
        words = query.strip().split()
        if words:
            combined_q = Q()
            for word in words:
                word_q = (
                    Q(name__icontains=word) |
                    Q(code__icontains=word) |
                    Q(building__icontains=word) |
                    Q(wing__icontains=word) |
                    Q(description__icontains=word)
                )
                combined_q &= word_q
            stats_queryset = stats_queryset.filter(combined_q)
    
    dormitory_type = request.GET.get('dormitory_type', '')
    if dormitory_type:
        stats_queryset = stats_queryset.filter(dormitory_type=dormitory_type)
    
    is_active = request.GET.get('is_active', '')
    if is_active:
        stats_queryset = stats_queryset.filter(is_active=(is_active.lower() == 'true'))
    
    is_available_for_new_admissions = request.GET.get('is_available_for_new_admissions', '')
    if is_available_for_new_admissions:
        stats_queryset = stats_queryset.filter(
            is_available_for_new_admissions=(is_available_for_new_admissions.lower() == 'true')
        )
    
    maintenance_status = request.GET.get('maintenance_status', '')
    if maintenance_status:
        stats_queryset = stats_queryset.filter(maintenance_status=maintenance_status)
    
    dormitory_master = request.GET.get('dormitory_master', '')
    if dormitory_master:
        try:
            stats_queryset = stats_queryset.filter(dormitory_master_id=int(dormitory_master))
        except (ValueError, TypeError):
            pass
    
    # Now calculate statistics on the clean queryset
    stats = stats_queryset.aggregate(
        total=Count('id'),
        active=Count('id', filter=Q(is_active=True)),
        boys=Count('id', filter=Q(dormitory_type='BOYS')),
        girls=Count('id', filter=Q(dormitory_type='GIRLS')),
        mixed=Count('id', filter=Q(dormitory_type='MIXED')),
        total_capacity=Sum('total_capacity'),
        total_occupancy=Sum('current_occupancy'),
    )
    
    # Calculate derived statistics
    total_capacity = stats.get('total_capacity') or 0
    total_occupancy = stats.get('total_occupancy') or 0
    stats['available_beds'] = total_capacity - total_occupancy
    
    # Calculate average occupancy percentage manually
    if total_capacity > 0:
        stats['avg_occupancy'] = round((total_occupancy / total_capacity) * 100, 1)
    else:
        stats['avg_occupancy'] = 0
    
    # Count full dormitories (need to do this separately)
    stats['full_dormitories'] = stats_queryset.filter(
        current_occupancy__gte=F('total_capacity')
    ).count()
    
    # Pagination
    paginator = Paginator(dormitories, 20)
    page_number = request.GET.get('page', 1)
    dormitories_page = paginator.get_page(page_number)
    
    # Detect HTMX request
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'dormitories_page': dormitories_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    # Return appropriate template
    if is_htmx:
        return render(request, 'boarding/dormitories/partials/_dormitory_results.html', context)
    else:
        return render(request, 'boarding/dormitories/list.html', context)


@login_required
def dormitory_create(request):
    """Create new dormitory"""
    if request.method == 'POST':
        form = DormitoryForm(request.POST)
        if form.is_valid():
            dormitory = form.save()
            messages.success(
                request,
                f"Dormitory '{dormitory.name}' created successfully",
                extra_tags='sweetalert'
            )
            return redirect('boarding:dormitory_detail', pk=dormitory.pk)
    else:
        form = DormitoryForm()
    
    context = {
        'form': form,
        'title': 'Create Dormitory',
    }
    
    return render(request, 'boarding/dormitories/form.html', context)


@login_required
def dormitory_edit(request, pk):
    """Edit existing dormitory"""
    dormitory = get_object_or_404(Dormitory, pk=pk)
    
    if request.method == 'POST':
        form = DormitoryForm(request.POST, instance=dormitory)
        if form.is_valid():
            dormitory = form.save()
            messages.success(
                request,
                f"Dormitory '{dormitory.name}' updated successfully",
                extra_tags='sweetalert'
            )
            return redirect('boarding:dormitory_detail', pk=dormitory.pk)
    else:
        form = DormitoryForm(instance=dormitory)
    
    context = {
        'form': form,
        'dormitory': dormitory,
        'title': f'Edit {dormitory.name}',
    }
    
    return render(request, 'boarding/dormitories/form.html', context)


@login_required
def dormitory_detail(request, pk):
    """View dormitory details"""
    dormitory = get_object_or_404(
        Dormitory.objects.prefetch_related('boarding_enrollments'),
        pk=pk
    )
    
    # Get enrollment statistics
    enrollment_stats = dormitory.boarding_enrollments.aggregate(
        total_enrollments=Count('id'),
        active_enrollments=Count('id', filter=Q(status='ACTIVE')),
        pending_enrollments=Count('id', filter=Q(status='PENDING')),
        male_students=Count('id', filter=Q(student__gender='M', status='ACTIVE')),
        female_students=Count('id', filter=Q(student__gender='F', status='ACTIVE')),
    )
    
    # Get current residents
    current_residents = dormitory.boarding_enrollments.filter(
        status='ACTIVE'
    ).select_related('student', 'academic_session').order_by('room_number', 'bed_number')
    
    # Get recent enrollments
    recent_enrollments = dormitory.boarding_enrollments.select_related(
        'student', 'academic_session'
    ).order_by('-created_at')[:10]
    
    context = {
        'dormitory': dormitory,
        'enrollment_stats': enrollment_stats,
        'current_residents': current_residents,
        'recent_enrollments': recent_enrollments,
    }
    
    return render(request, 'boarding/dormitories/detail.html', context)


@login_required
def dormitory_delete(request, pk):
    """Delete dormitory with HTMX support"""
    dormitory = get_object_or_404(Dormitory, pk=pk)
    
    if request.method == 'POST':
        # Check if dormitory has enrollments
        if dormitory.boarding_enrollments.exists():
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f"Cannot delete '{dormitory.name}' because it has boarding enrollments"
                response['HX-Alert-Type'] = 'error'
                response['HX-Alert-Title'] = 'Cannot Delete'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(
                    request,
                    f"Cannot delete '{dormitory.name}' because it has boarding enrollments",
                    extra_tags='sweetalert-error'
                )
                return redirect('boarding:dormitory_list')
        
        dormitory_name = dormitory.name
        dormitory.delete()
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Dormitory '{dormitory_name}' deleted successfully"
            response['HX-Alert-Type'] = 'success'
            response['HX-Alert-Title'] = 'Deleted!'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('boarding:dormitory_list')
            return response
        else:
            messages.success(
                request,
                f"Dormitory '{dormitory_name}' deleted successfully",
                extra_tags='sweetalert'
            )
            return redirect('boarding:dormitory_list')


@login_required
def dormitory_activate(request, pk):
    """Activate dormitory with HTMX support"""
    dormitory = get_object_or_404(Dormitory, pk=pk)
    
    if request.method == 'POST':
        if dormitory.is_active:
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f"{dormitory.name} is already active"
                response['HX-Alert-Type'] = 'warning'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.warning(request, f"{dormitory.name} is already active", extra_tags='sweetalert')
                return redirect('boarding:dormitory_detail', pk=pk)
        
        dormitory.is_active = True
        dormitory.save(update_fields=['is_active', 'updated_at'])
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"{dormitory.name} activated successfully"
            response['HX-Alert-Type'] = 'success'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('boarding:dormitory_detail', kwargs={'pk': pk})
            return response
        else:
            messages.success(request, f"{dormitory.name} activated successfully", extra_tags='sweetalert')
            return redirect('boarding:dormitory_detail', pk=pk)


@login_required
def dormitory_deactivate(request, pk):
    """Deactivate dormitory with HTMX support"""
    dormitory = get_object_or_404(Dormitory, pk=pk)
    
    if request.method == 'POST':
        if not dormitory.is_active:
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f"{dormitory.name} is already inactive"
                response['HX-Alert-Type'] = 'warning'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.warning(request, f"{dormitory.name} is already inactive", extra_tags='sweetalert')
                return redirect('boarding:dormitory_detail', pk=pk)
        
        dormitory.is_active = False
        dormitory.save(update_fields=['is_active', 'updated_at'])
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"{dormitory.name} deactivated successfully"
            response['HX-Alert-Type'] = 'warning'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('boarding:dormitory_detail', kwargs={'pk': pk})
            return response
        else:
            messages.warning(request, f"{dormitory.name} deactivated", extra_tags='sweetalert')
            return redirect('boarding:dormitory_detail', pk=pk)


@login_required
def dormitory_print_view(request):
    """Generate printable dormitory list"""
    
    selected_fields = request.GET.getlist('fields')
    if not selected_fields:
        selected_fields = [
            'code', 'name', 'dormitory_type', 'total_capacity', 
            'current_occupancy', 'is_active'
        ]
    
    include_stats = request.GET.get('include_stats') == 'true'
    landscape = request.GET.get('landscape') == 'true'
    
    dormitories = get_filtered_dormitories(request)
    
    stats = None
    if include_stats:
        stats = dormitories.aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(is_active=True)),
            total_capacity=Sum('total_capacity'),
            total_occupancy=Sum('current_occupancy'),
        )
    
    field_names = {
        'code': 'Dormitory Code',
        'name': 'Dormitory Name',
        'dormitory_type': 'Type',
        'total_capacity': 'Capacity',
        'current_occupancy': 'Occupancy',
        'is_active': 'Active',
    }
    
    selected_field_names = [
        field_names.get(field, field.replace('_', ' ').title())
        for field in selected_fields
    ]
    
    context = {
        'dormitories': dormitories,
        'stats': stats,
        'now': timezone.now(),
        'selected_fields': selected_fields,
        'selected_field_names': selected_field_names,
        'field_names': field_names,
        'landscape': landscape,
    }
    
    return render(request, 'boarding/dormitories/print.html', context)


@login_required
def export_dormitories_excel(request):
    """Export dormitories to Excel with filters applied"""
    
    dormitories = get_filtered_dormitories(request)
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Dormitories"
    
    # Define styles
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_alignment = Alignment(horizontal="center", vertical="center")
    
    # Headers
    headers = [
        '#', 'Code', 'Name', 'Type', 'Building', 'Capacity',
        'Occupancy', 'Available', 'Active', 'Dormitory Master'
    ]
    ws.append(headers)
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
    
    # Data rows
    for idx, dormitory in enumerate(dormitories, start=1):
        ws.append([
            idx,
            dormitory.code,
            dormitory.name,
            dormitory.get_dormitory_type_display(),
            dormitory.building or '',
            dormitory.total_capacity,
            dormitory.current_occupancy,
            dormitory.get_available_capacity(),
            'Yes' if dormitory.is_active else 'No',
            str(dormitory.dormitory_master) if dormitory.dormitory_master else '',
        ])
    
    # Auto-adjust column widths
    for column in ws.columns:
        max_length = 0
        column_letter = get_column_letter(column[0].column)
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(cell.value)
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        ws.column_dimensions[column_letter].width = adjusted_width
    
    # Create response
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"dormitories_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


# =============================================================================
# BOARDING ENROLLMENT VIEWS
# =============================================================================

@login_required
def boarding_enrollment_list(request):
    """
    Handle BOTH full page loads AND HTMX search/filter requests.
    
    - Normal request: Returns full page with filter form
    - HTMX request: Returns only the results partial (table + stats)
    
    This single view handles all enrollment listing needs.
    """
    filter_form = BoardingEnrollmentFilterForm(request.GET or None)
    enrollments = get_filtered_boarding_enrollments(request)
    
    # Calculate statistics
    stats = enrollments.aggregate(
        total=Count('id'),
        pending=Count('id', filter=Q(status='PENDING')),
        active=Count('id', filter=Q(status='ACTIVE')),
        suspended=Count('id', filter=Q(status='SUSPENDED')),
        terminated=Count('id', filter=Q(status='TERMINATED')),
        full_boarders=Count('id', filter=Q(boarding_type='FULL_BOARDER')),
        weekly_boarders=Count('id', filter=Q(boarding_type='WEEKLY_BOARDER')),
        flexi_boarders=Count('id', filter=Q(boarding_type='FLEXI_BOARDER')),
        with_consent=Count('id', filter=Q(guardian_consent=True)),
        without_consent=Count('id', filter=Q(guardian_consent=False)),
    )
    
    # Pagination
    paginator = Paginator(enrollments, 20)
    page_number = request.GET.get('page', 1)
    enrollments_page = paginator.get_page(page_number)
    
    # Detect HTMX request
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'enrollments_page': enrollments_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    # Return appropriate template
    if is_htmx:
        return render(request, 'boarding/enrollments/partials/_enrollment_results.html', context)
    else:
        return render(request, 'boarding/enrollments/list.html', context)


@login_required
def boarding_enrollment_create(request):
    """Create new boarding enrollment"""
    if request.method == 'POST':
        form = BoardingEnrollmentForm(request.POST)
        if form.is_valid():
            enrollment = form.save()
            messages.success(
                request,
                f"Boarding enrollment for {enrollment.student.get_full_name()} created successfully",
                extra_tags='sweetalert'
            )
            return redirect('boarding:enrollment_detail', pk=enrollment.pk)
    else:
        form = BoardingEnrollmentForm()
    
    context = {
        'form': form,
        'enrollment': None,
        'title': 'Create Boarding Enrollment',
    }
    
    return render(request, 'boarding/enrollments/form.html', context)


@login_required
def boarding_enrollment_edit(request, pk):
    """Edit existing boarding enrollment"""
    enrollment = get_object_or_404(BoardingEnrollment, pk=pk)
    
    if request.method == 'POST':
        form = BoardingEnrollmentForm(request.POST, instance=enrollment)
        if form.is_valid():
            enrollment = form.save()
            messages.success(
                request,
                f"Boarding enrollment updated successfully",
                extra_tags='sweetalert'
            )
            return redirect('boarding:enrollment_detail', pk=enrollment.pk)
    else:
        form = BoardingEnrollmentForm(instance=enrollment)
    
    context = {
        'form': form,
        'enrollment': enrollment,
        'title': f'Edit Boarding Enrollment',
    }
    
    return render(request, 'boarding/enrollments/form.html', context)


@login_required
def boarding_enrollment_detail(request, pk):
    """View boarding enrollment details"""
    enrollment = get_object_or_404(
        BoardingEnrollment.objects.select_related(
            'student',
            'academic_session',
            'dormitory',
            'consenting_guardian',
            'approved_by',
            'boarding_invoice'
        ),
        pk=pk
    )
    
    context = {
        'enrollment': enrollment,
    }
    
    return render(request, 'boarding/enrollments/detail.html', context)


@login_required
def boarding_enrollment_approve(request, pk):
    """Approve pending boarding enrollment"""
    enrollment = get_object_or_404(BoardingEnrollment, pk=pk)
    
    if request.method == 'POST':
        if enrollment.status != 'PENDING':
            messages.error(
                request,
                'Only pending enrollments can be approved',
                extra_tags='sweetalert-error'
            )
            return redirect('boarding:enrollment_detail', pk=pk)
        
        enrollment.approve(approved_by=request.user)
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = 'Boarding enrollment approved successfully'
            response['HX-Alert-Type'] = 'success'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('boarding:enrollment_detail', kwargs={'pk': pk})
            return response
        else:
            messages.success(request, 'Boarding enrollment approved successfully', extra_tags='sweetalert')
            return redirect('boarding:enrollment_detail', pk=pk)


@login_required
def boarding_enrollment_terminate(request, pk):
    """Terminate boarding enrollment"""
    enrollment = get_object_or_404(BoardingEnrollment, pk=pk)
    
    if request.method == 'POST':
        form = BoardingTerminationForm(request.POST)
        if form.is_valid():
            enrollment.terminate(reason=form.cleaned_data['termination_reason'])
            enrollment.effective_end_date = form.cleaned_data['effective_termination_date']
            enrollment.save(update_fields=['effective_end_date', 'updated_at'])
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = 'Boarding enrollment terminated successfully'
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('boarding:enrollment_detail', kwargs={'pk': pk})
                return response
            else:
                messages.success(request, 'Boarding enrollment terminated successfully', extra_tags='sweetalert')
                return redirect('boarding:enrollment_detail', pk=pk)
        else:
            # Form has errors - return modal with errors
            return render(request, 'boarding/enrollments/modals/terminate_enrollment.html', {
                'form': form,
                'enrollment': enrollment,
            })


@login_required
def boarding_enrollment_suspend(request, pk):
    """Suspend boarding enrollment"""
    enrollment = get_object_or_404(BoardingEnrollment, pk=pk)
    
    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        
        if not reason:
            return render(request, 'boarding/enrollments/modals/suspend_enrollment.html', {
                'enrollment': enrollment,
                'error_message': 'Suspension reason is required',
            })
        
        enrollment.suspend(reason=reason)
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = 'Boarding enrollment suspended successfully'
            response['HX-Alert-Type'] = 'success'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('boarding:enrollment_detail', kwargs={'pk': pk})
            return response
        else:
            messages.success(request, 'Boarding enrollment suspended successfully', extra_tags='sweetalert')
            return redirect('boarding:enrollment_detail', pk=pk)


@login_required
def boarding_enrollment_delete(request, pk):
    """Delete boarding enrollment with HTMX support"""
    enrollment = get_object_or_404(BoardingEnrollment, pk=pk)
    
    if request.method == 'POST':
        student_name = enrollment.student.get_full_name()
        enrollment.delete()
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Boarding enrollment for {student_name} deleted successfully"
            response['HX-Alert-Type'] = 'success'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('boarding:enrollment_list')
            return response
        else:
            messages.success(
                request,
                f"Boarding enrollment for {student_name} deleted successfully",
                extra_tags='sweetalert'
            )
            return redirect('boarding:enrollment_list')


@login_required
def boarding_enrollment_print_view(request):
    """Generate printable enrollment list"""
    
    selected_fields = request.GET.getlist('fields')
    if not selected_fields:
        selected_fields = [
            'student_name', 'dormitory', 'boarding_type', 'status',
            'enrollment_date', 'boarding_roll_number'
        ]
    
    include_stats = request.GET.get('include_stats') == 'true'
    landscape = request.GET.get('landscape') == 'true'
    
    enrollments = get_filtered_boarding_enrollments(request)
    
    stats = None
    if include_stats:
        stats = enrollments.aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(status='ACTIVE')),
        )
    
    field_names = {
        'student_name': 'Student Name',
        'dormitory': 'Dormitory',
        'boarding_type': 'Boarding Type',
        'status': 'Status',
        'enrollment_date': 'Enrollment Date',
        'boarding_roll_number': 'Roll Number',
    }
    
    selected_field_names = [
        field_names.get(field, field.replace('_', ' ').title())
        for field in selected_fields
    ]
    
    context = {
        'enrollments': enrollments,
        'stats': stats,
        'now': timezone.now(),
        'selected_fields': selected_fields,
        'selected_field_names': selected_field_names,
        'field_names': field_names,
        'landscape': landscape,
    }
    
    return render(request, 'boarding/enrollments/print.html', context)


@login_required
def export_boarding_enrollments_excel(request):
    """Export boarding enrollments to Excel with filters applied"""
    
    enrollments = get_filtered_boarding_enrollments(request)
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Boarding Enrollments"
    
    # Define styles
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_alignment = Alignment(horizontal="center", vertical="center")
    
    # Headers
    headers = [
        '#', 'Student Name', 'Admission No.', 'Dormitory', 'Boarding Type',
        'Status', 'Enrollment Date', 'Room/Bed', 'Session'
    ]
    ws.append(headers)
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
    
    # Data rows
    for idx, enrollment in enumerate(enrollments, start=1):
        room_bed = f"{enrollment.room_number}/{enrollment.bed_number}" if enrollment.room_number else ''
        
        ws.append([
            idx,
            enrollment.student.get_full_name(),
            enrollment.student.admission_number,
            enrollment.dormitory.name,
            enrollment.get_boarding_type_display(),
            enrollment.get_status_display(),
            enrollment.enrollment_date.strftime('%Y-%m-%d'),
            room_bed,
            str(enrollment.academic_session),
        ])
    
    # Auto-adjust column widths
    for column in ws.columns:
        max_length = 0
        column_letter = get_column_letter(column[0].column)
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(cell.value)
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        ws.column_dimensions[column_letter].width = adjusted_width
    
    # Create response
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"boarding_enrollments_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


# =============================================================================
# BULK ENROLLMENT - STEP 1: STUDENT SELECTION
# =============================================================================

@login_required
def bulk_enrollment_step1(request):
    """
    Bulk Enrollment - Step 1: Select students.
    
    Features:
    - HTMX-powered student filtering
    - Multi-select with checkboxes
    - Shows eligible students
    
    Handles both full page loads and HTMX filter requests.
    """
    # Get target dormitory and session from query params
    dormitory_id = request.GET.get('dormitory_id')
    session_id = request.GET.get('session_id')
    
    target_dormitory = None
    target_session = None
    
    if dormitory_id:
        target_dormitory = get_object_or_404(Dormitory, pk=dormitory_id)
    
    if session_id:
        target_session = get_object_or_404(AcademicSession, pk=session_id)
    
    # Initialize filter form
    form = BulkBoardingEnrollmentStudentSelectionForm(
        request.GET,
        academic_session=target_session,
        target_dormitory=target_dormitory
    )
    
    # Get base queryset
    students = Student.objects.filter(
        enrollment_status='ACTIVE'
    ).select_related(
        'current_academic_level',
    ).order_by('first_name', 'last_name')
    
    # Apply filters if form is valid
    if form.is_valid():
        search = form.cleaned_data.get('search')
        current_level = form.cleaned_data.get('current_level')
        current_class = form.cleaned_data.get('current_class')
        enrollment_status = form.cleaned_data.get('enrollment_status')
        gender = form.cleaned_data.get('gender')
        exclude_already_enrolled = form.cleaned_data.get('exclude_already_enrolled')
        dormitory_type = form.cleaned_data.get('dormitory_type')
        sort_by = form.cleaned_data.get('sort_by')
        
        # Apply filters
        if search:
            students = students.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(middle_name__icontains=search) |
                Q(admission_number__icontains=search)
            )
        
        if current_level:
            students = students.filter(current_academic_level=current_level)
        
        if current_class:
            students = students.filter(current_class=current_class)
        
        if enrollment_status:
            students = students.filter(enrollment_status=enrollment_status)
        
        if gender:
            students = students.filter(gender=gender)
        
        if dormitory_type:
            if dormitory_type == 'BOYS':
                students = students.filter(gender='M')
            elif dormitory_type == 'GIRLS':
                students = students.filter(gender='F')
        
        if exclude_already_enrolled and target_session:
            students = students.exclude(
                boarding_enrollments__academic_session=target_session,
                boarding_enrollments__status__in=['PENDING', 'ACTIVE']
            )
        
        # Apply sorting
        sort_mapping = {
            'name': 'first_name',
            '-name': '-first_name',
            'admission_number': 'admission_number',
            '-admission_date': '-admission_date',
            'admission_date': 'admission_date',
        }
        students = students.order_by(sort_mapping.get(sort_by, 'first_name'))
    
    # Pagination
    paginator = Paginator(students, 50)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    # Detect HTMX request
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'form': form,
        'students': page_obj,
        'page_obj': page_obj,
        'target_dormitory': target_dormitory,
        'target_session': target_session,
        'total_count': students.count(),
        'is_htmx': is_htmx,
        'title': 'Bulk Boarding Enrollment - Select Students',
    }
    
    # Return appropriate template
    if is_htmx:
        return render(request, 'boarding/bulk_enrollment/partials/_student_results.html', context)
    else:
        return render(request, 'boarding/bulk_enrollment/step1.html', context)


# =============================================================================
# BULK ENROLLMENT - STEP 2: CONFIRMATION & EXECUTION
# =============================================================================

@login_required
def bulk_enrollment_step2(request):
    """
    Bulk Enrollment - Step 2: Review and confirm enrollment.
    """
    if request.method == 'POST':
        form = BulkBoardingEnrollmentConfirmationForm(request.POST)
        
        if form.is_valid():
            try:
                result = execute_bulk_boarding_enrollment(form.cleaned_data, request.user)
                
                # Success message
                messages.success(
                    request,
                    f'Successfully enrolled {result["enrolled_count"]} student(s) in boarding. '
                    f'{result["invoice_count"]} invoice(s) created.',
                    extra_tags='sweetalert'
                )
                
                # Redirect to enrollment list with filter
                return redirect(
                    reverse('boarding:enrollment_list') + 
                    f'?dormitory={form.cleaned_data["dormitory"].pk}'
                )
                
            except Exception as e:
                logger.error(f"Bulk boarding enrollment failed: {e}")
                messages.error(
                    request,
                    f'Bulk boarding enrollment failed: {str(e)}',
                    extra_tags='sweetalert-error'
                )
        else:
            messages.error(
                request,
                'Please correct the errors below.',
                extra_tags='sweetalert-error'
            )
    else:
        # Get student IDs from query params
        student_ids = request.GET.get('student_ids', '')
        
        if not student_ids:
            messages.error(
                request,
                'No students selected. Please go back and select students.',
                extra_tags='sweetalert-error'
            )
            return redirect('boarding:bulk_enrollment_step1')
        
        # Keep as strings (UUIDs)
        ids = [id.strip() for id in student_ids.split(',') if id.strip()]
        
        # Count students
        student_count = Student.objects.filter(id__in=ids).count()
        
        # Initialize form with student IDs
        initial = {
            'selected_student_ids': student_ids,
        }
        
        # Pre-fill dormitory and session if provided
        dormitory_id = request.GET.get('dormitory_id')
        session_id = request.GET.get('session_id')
        
        if dormitory_id:
            target_dormitory = get_object_or_404(Dormitory, pk=dormitory_id)
            initial['dormitory'] = target_dormitory
        
        if session_id:
            initial['academic_session'] = get_object_or_404(AcademicSession, pk=session_id)
        
        form = BulkBoardingEnrollmentConfirmationForm(
            initial=initial,
            student_count=student_count
        )
    
    # Get selected students for display
    student_ids_str = form.data.get('selected_student_ids') or form.initial.get('selected_student_ids', '')
    ids = [id.strip() for id in student_ids_str.split(',') if id.strip()]
    selected_students = Student.objects.filter(id__in=ids).select_related(
        'current_academic_level'
    )
    
    context = {
        'form': form,
        'selected_students': selected_students,
        'student_count': len(ids),
        'title': 'Bulk Boarding Enrollment - Confirm',
    }
    
    return render(request, 'boarding/bulk_enrollment/step2.html', context)


def execute_bulk_boarding_enrollment(data, user):
    """
    Execute bulk boarding enrollment with transaction safety.
    Invoice creation is handled automatically by signals.
    
    Args:
        data: Cleaned form data
        user: Current user (for audit trail)
    
    Returns:
        dict: Result summary
    """
    enrolled_count = 0
    errors = []
    
    student_ids = data['selected_student_ids']
    students = Student.objects.filter(id__in=student_ids)
    
    # ⭐ Each enrollment in its own transaction for partial success support
    for student in students:
        try:
            with transaction.atomic():
                # Create boarding enrollment
                enrollment = BoardingEnrollment.objects.create(
                    student=student,
                    academic_session=data['academic_session'],
                    dormitory=data['dormitory'],
                    boarding_type=data['boarding_type'],
                    enrollment_date=data['enrollment_date'],
                    effective_start_date=data['effective_start_date'],
                    effective_end_date=data.get('effective_end_date'),
                    boarding_days=data.get('boarding_days'),
                    auto_create_invoice=data['auto_create_invoice'],  # ✅ Signal checks this
                    reason_for_boarding=data.get('reason_for_boarding', ''),
                    guardian_consent=data.get('require_guardian_consent', False),
                    status='PENDING',  # Will be approved later
                )
                
                enrolled_count += 1
                logger.info(f"✅ Enrolled {student.get_full_name()} in boarding")
                
                # ✅ Invoice creation handled by signal when enrollment is approved
                # Signal: auto_add_boarding_fees_to_invoice will:
                #   - Check if auto_create_invoice is True
                #   - Find student's DRAFT invoice and add boarding items
                #   - OR create supplementary invoice if main invoice is finalized
                
        except Exception as e:
            logger.error(f"Failed to enroll {student} in boarding: {e}")
            errors.append(f"{student.get_full_name()}: {str(e)}")
    
    # Return results with partial success support
    result = {
        'enrolled_count': enrolled_count,
        'errors': errors,
    }
    
    return result


# =============================================================================
# OPTIONAL AJAX/JSON UTILITY VIEWS
# These are optional but useful for dynamic features
# =============================================================================

@login_required
def check_dormitory_capacity_ajax(request, pk):
    """
    AJAX endpoint to check dormitory capacity.
    Returns JSON with capacity information.
    
    Usage: Real-time capacity checking when selecting students for bulk enrollment.
    """
    try:
        dormitory = get_object_or_404(Dormitory, pk=pk)
        student_count = int(request.GET.get('student_count', 0))
        
        available_capacity = dormitory.get_available_capacity()
        can_accommodate = available_capacity >= student_count
        
        data = {
            'success': True,
            'can_accommodate': can_accommodate,
            'dormitory_name': dormitory.name,
            'total_capacity': dormitory.total_capacity,
            'current_occupancy': dormitory.current_occupancy,
            'available_capacity': available_capacity,
            'requested_count': student_count,
            'occupancy_percentage': dormitory.get_occupancy_percentage(),
            'message': (
                f'Dormitory can accommodate {student_count} student(s).'
                if can_accommodate
                else f'Insufficient capacity. Only {available_capacity} bed(s) available.'
            )
        }
        
    except (ValueError, TypeError):
        data = {
            'success': False,
            'error': 'Invalid student count provided.'
        }
    except Exception as e:
        logger.error(f"Error checking dormitory capacity: {e}")
        data = {
            'success': False,
            'error': 'An error occurred while checking capacity.'
        }
    
    return JsonResponse(data)


@login_required
def check_student_boarding_eligibility_ajax(request, student_id):
    """
    AJAX endpoint to check if student is eligible for boarding.
    Returns JSON with eligibility information.
    
    Usage: Pre-validation before creating boarding enrollment.
    """
    try:
        student = get_object_or_404(Student, pk=student_id)
        dormitory_id = request.GET.get('dormitory_id')
        
        if dormitory_id:
            dormitory = get_object_or_404(Dormitory, pk=dormitory_id)
            can_accommodate, message = dormitory.can_accommodate(student)
            
            data = {
                'success': True,
                'eligible': can_accommodate,
                'student_name': student.get_full_name(),
                'dormitory_name': dormitory.name,
                'message': message,
            }
        else:
            # Check which dormitories can accommodate
            compatible_dormitories = []
            for dorm in Dormitory.objects.filter(is_active=True, is_available_for_new_admissions=True):
                can_accommodate, _ = dorm.can_accommodate(student)
                if can_accommodate:
                    compatible_dormitories.append({
                        'id': dorm.id,
                        'name': dorm.name,
                        'type': dorm.get_dormitory_type_display(),
                        'available_capacity': dorm.get_available_capacity(),
                    })
            
            data = {
                'success': True,
                'student_name': student.get_full_name(),
                'compatible_dormitories': compatible_dormitories,
            }
        
    except Exception as e:
        logger.error(f"Error checking student eligibility: {e}")
        data = {
            'success': False,
            'error': 'An error occurred while checking eligibility.'
        }
    
    return JsonResponse(data)


@login_required
def boarding_quick_stats_ajax(request):
    """
    AJAX endpoint for quick boarding statistics.
    Returns JSON with key metrics.
    
    Usage: Dashboard widgets, real-time stats updates.
    """
    try:
        today = get_school_today()
        
        dormitory_stats = Dormitory.objects.filter(is_active=True).aggregate(
            total_capacity=Sum('total_capacity'),
            total_occupancy=Sum('current_occupancy')
        )
        
        total_capacity = dormitory_stats['total_capacity'] or 0
        total_occupancy = dormitory_stats['total_occupancy'] or 0
        
        stats = {
            'success': True,
            'dormitories': {
                'total': Dormitory.objects.filter(is_active=True).count(),
                'boys': Dormitory.objects.filter(is_active=True, dormitory_type='BOYS').count(),
                'girls': Dormitory.objects.filter(is_active=True, dormitory_type='GIRLS').count(),
                'full': Dormitory.objects.filter(is_active=True, current_occupancy__gte=F('total_capacity')).count(),
            },
            'capacity': {
                'total': total_capacity,
                'occupied': total_occupancy,
                'available': total_capacity - total_occupancy,
                'occupancy_percentage': round((total_occupancy / total_capacity * 100) if total_capacity > 0 else 0, 1),
            },
            'enrollments': {
                'total': BoardingEnrollment.objects.count(),
                'active': BoardingEnrollment.objects.filter(status='ACTIVE').count(),
                'pending': BoardingEnrollment.objects.filter(status='PENDING').count(),
            },
        }
        
    except Exception as e:
        logger.error(f"Error getting boarding stats: {e}")
        stats = {
            'success': False,
            'error': 'An error occurred while fetching statistics.'
        }
    
    return JsonResponse(stats)

@login_required
def get_student_guardians_api(request, student_id):
    """
    API endpoint to get guardians for a specific student.
    Used for dynamically populating guardian dropdown in boarding enrollment form.
    """
    try:
        from students.models import Student, StudentGuardian
        
        student = get_object_or_404(Student, pk=student_id)
        
        # Get active guardians for this student
        guardians_data = []
        
        # ✅ FIXED: Use 'is_primary' instead of 'is_primary_contact'
        student_guardians = StudentGuardian.objects.filter(
            student=student,
            is_active=True
        ).select_related('guardian').order_by(
            '-is_primary',  # ✅ FIXED: Changed from is_primary_contact
            'guardian__first_name', 
            'guardian__last_name'
        )
        
        for sg in student_guardians:
            guardian = sg.guardian
            guardians_data.append({
                'id': str(guardian.id),
                'full_name': guardian.get_full_name(),
                'first_name': guardian.first_name,
                'last_name': guardian.last_name,
                'relationship': sg.relationship or 'Guardian',
                'is_primary': sg.is_primary,  # ✅ FIXED: Changed from is_primary_contact
            })
        
        logger.info(
            f"API: Returned {len(guardians_data)} guardian(s) for student "
            f"{student.get_full_name()}"
        )
        
        return JsonResponse({
            'success': True,
            'student_id': str(student.id),
            'student_name': student.get_full_name(),
            'guardians': guardians_data,
            'count': len(guardians_data)
        })
        
    except Student.DoesNotExist:
        logger.warning(f"API: Student not found (ID: {student_id})")
        return JsonResponse({
            'success': False,
            'error': 'Student not found'
        }, status=404)
        
    except Exception as e:
        logger.error(f"API: Error fetching guardians for student {student_id}: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'An error occurred while fetching guardians'
        }, status=500)