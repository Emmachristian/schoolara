# hr/views.py

"""
Human Resources Management Views

Comprehensive view functions for:
- Staff Registration and Profile Management (using Wizard)
- Department Management
- Designation Management
- Contract Management
- Teacher Management
- Attendance Tracking
- Payroll Management
- Reports and Analytics

All views delegate business logic to services.py where appropriate
Uses SweetAlert2 for all notifications via Django messages
Follows the same patterns as loans/views.py
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.contrib import messages
from django.db.models import Q, Count, Sum, Avg, Prefetch, F, IntegerField, Case, When
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from django.db import transaction
from django.core.files.storage import FileSystemStorage
from formtools.wizard.views import SessionWizardView
from datetime import timedelta, date, datetime
from decimal import Decimal
import os
import logging

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from .models import (
    Department,
    Designation,
    Contract,
    Staff,
    StaffDesignation,
    Teacher,
    Attendance,
    Payroll,
    SalaryHistory,
    ContractBenefit,
)

from .forms import (
    # Wizard forms
    STAFF_WIZARD_FORMS,
    STAFF_WIZARD_STEP_NAMES,
    
    # Regular forms
    StaffForm,
    DepartmentForm,
    DesignationForm,
    ContractForm,
    TeacherForm,
    AttendanceForm,
    PayrollForm,
    PayrollAllowanceFormSet,
    PayrollBonusFormSet,
    PayrollDeductionFormSet,
    StaffDesignationForm,
    
    # Filter forms
    DepartmentFilterForm,
    DesignationFilterForm,
    StaffFilterForm,
    ContractFilterForm,
    TeacherFilterForm,
    AttendanceFilterForm,
    PayrollFilterForm,
    StaffDesignationFilterForm,
)

# Import stats functions
from . import stats as hr_stats

from core.utils import format_money, get_school_today

logger = logging.getLogger(__name__)


# =============================================================================
# DASHBOARD
# =============================================================================

@login_required
def hr_dashboard(request):
    """Main HR dashboard with overview statistics"""
    
    try:
        # Get comprehensive statistics
        staff_statistics = hr_stats.get_staff_statistics()
        department_statistics = hr_stats.get_department_statistics()
        designation_statistics = hr_stats.get_designation_statistics()
        contract_statistics = hr_stats.get_contract_statistics()
        teacher_statistics = hr_stats.get_teacher_statistics()
        
    except Exception as e:
        logger.error(f"Error getting dashboard statistics: {e}")
        staff_statistics = {}
        department_statistics = {}
        designation_statistics = {}
        contract_statistics = {}
        teacher_statistics = {}
    
    # Get recent activities (limited queries for display)
    recent_staff = Staff.objects.select_related(
        'primary_department'
    ).order_by('-created_at')[:10]
    
    recent_contracts = Contract.objects.select_related(
        'staff'
    ).order_by('-created_at')[:10]
    
    # Get contracts expiring soon
    today = get_school_today()
    expiring_contracts = Contract.objects.filter(
        status='ACTIVE',
        end_date__gte=today,
        end_date__lte=today + timedelta(days=30)
    ).select_related('staff').order_by('end_date')[:10]
    
    # Get staff needing attention
    staff_without_contracts = Staff.objects.filter(
        is_active=True
    ).annotate(
        contract_count=Count('contracts', filter=Q(contracts__status='ACTIVE'))
    ).filter(contract_count=0).order_by('date_of_joining')[:10]
    
    # Get birthdays this week
    week_from_now = today + timedelta(days=7)
    
    upcoming_birthdays = Staff.objects.filter(
        is_active=True,
        date_of_birth__month=today.month,
        date_of_birth__day__gte=today.day,
        date_of_birth__day__lte=week_from_now.day
    ).order_by('date_of_birth__day')[:10]
    
    # Probation ending soon
    probation_ending = []
    for staff in Staff.objects.filter(employment_status='PR', is_active=True):
        contract = Contract.objects.filter(
            staff=staff,
            status='ACTIVE',
            probation_period_months__gt=0
        ).first()
        
        if contract:
            probation_end = contract.start_date + timedelta(days=contract.probation_period_months * 30)
            if today <= probation_end <= today + timedelta(days=30):
                probation_ending.append({
                    'staff': staff,
                    'contract': contract,
                    'probation_end': probation_end,
                    'days_remaining': (probation_end - today).days
                })
    
    # Recent salary changes
    recent_salary_changes = SalaryHistory.objects.select_related(
        'staff', 'contract', 'effective_period'
    ).order_by('-effective_date')[:10]
    
    context = {
        'staff_statistics': staff_statistics,
        'department_statistics': department_statistics,
        'designation_statistics': designation_statistics,
        'contract_statistics': contract_statistics,
        'teacher_statistics': teacher_statistics,
        'recent_staff': recent_staff,
        'recent_contracts': recent_contracts,
        'expiring_contracts': expiring_contracts,
        'staff_without_contracts': staff_without_contracts,
        'upcoming_birthdays': upcoming_birthdays,
        'probation_ending': probation_ending,
        'recent_salary_changes': recent_salary_changes,
    }
    
    return render(request, 'hr/dashboard.html', context)


# =============================================================================
# HELPER FUNCTIONS FOR FILTERING
# =============================================================================

def get_filtered_staff(request):
    """Helper function to get filtered staff queryset"""
    staff = Staff.objects.select_related(
        'primary_department'
    ).prefetch_related(
        Prefetch(
            'staffdesignation_set',
            queryset=StaffDesignation.objects.filter(
                is_primary=True,
                is_active=True
            ).select_related('designation'),
            to_attr='primary_staff_designation'
        ),
        'contracts'
    ).annotate(
        active_contract_count=Count('contracts', filter=Q(contracts__status='ACTIVE'), distinct=True),
        designation_count=Count('staffdesignation', filter=Q(staffdesignation__is_active=True), distinct=True)
    ).order_by('-is_active', 'first_name', 'last_name')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    employment_status = request.GET.get('employment_status', '')
    gender = request.GET.get('gender', '')
    primary_department = request.GET.get('primary_department', '')
    is_active = request.GET.get('is_active', '')
    marital_status = request.GET.get('marital_status', '')
    nationality = request.GET.get('nationality', '')
    
    # Apply text search with multi-word support
    if query:
        words = query.strip().split()
        if words:
            combined_q = Q()
            for word in words:
                word_q = (
                    Q(first_name__icontains=word) |
                    Q(middle_name__icontains=word) |
                    Q(last_name__icontains=word) |
                    Q(staff_id__icontains=word) |
                    Q(phone_number__icontains=word) |
                    Q(personal_email__icontains=word) |
                    Q(national_id__icontains=word)
                )
                combined_q &= word_q
            staff = staff.filter(combined_q)
    
    # Apply filters
    if employment_status:
        staff = staff.filter(employment_status=employment_status)
    if gender:
        staff = staff.filter(gender=gender)
    if primary_department:
        staff = staff.filter(primary_department_id=primary_department)
    if marital_status:
        staff = staff.filter(marital_status=marital_status)
    if nationality:
        staff = staff.filter(nationality=nationality)
    if is_active:
        staff = staff.filter(is_active=(is_active.lower() == 'true'))
    
    return staff


def get_filtered_departments(request):
    """Helper function to get filtered departments queryset"""
    departments = Department.objects.select_related(
        'parent_department'
    ).annotate(
        staff_count=Count('primary_staff', filter=Q(primary_staff__is_active=True), distinct=True),
        designation_count=Count('designations', filter=Q(designations__is_active=True), distinct=True),
        sub_department_count=Count('sub_departments', distinct=True)
    ).order_by('department_type', 'name')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    department_type = request.GET.get('department_type', '')
    is_academic = request.GET.get('is_academic', '')
    is_active = request.GET.get('is_active', '')
    academic_subtype = request.GET.get('academic_subtype', '')
    parent_department = request.GET.get('parent_department', '')
    
    # Apply text search
    if query:
        words = query.strip().split()
        if words:
            combined_q = Q()
            for word in words:
                word_q = (
                    Q(name__icontains=word) |
                    Q(code__icontains=word) |
                    Q(description__icontains=word)
                )
                combined_q &= word_q
            departments = departments.filter(combined_q)
    
    # Apply filters
    if department_type:
        departments = departments.filter(department_type=department_type)
    if academic_subtype:
        departments = departments.filter(academic_subtype=academic_subtype)
    if is_academic is not None and is_academic:
        departments = departments.filter(is_academic=(is_academic.lower() == 'true'))
    if is_active is not None and is_active:
        departments = departments.filter(is_active=(is_active.lower() == 'true'))
    if parent_department == 'null':
        departments = departments.filter(parent_department__isnull=True)
    elif parent_department == 'has_parent':
        departments = departments.filter(parent_department__isnull=False)
    elif parent_department:
        departments = departments.filter(parent_department_id=parent_department)
    
    return departments


def get_filtered_designations(request):
    """Helper function to get filtered designations queryset"""
    designations = Designation.objects.select_related(
        'department',
        'reports_to'
    ).annotate(
        staff_count=Count('staffdesignation', filter=Q(staffdesignation__is_active=True), distinct=True),
        subordinate_count=Count('subordinate_designations', distinct=True)
    ).order_by('rank_order', 'name')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    department = request.GET.get('department', '')
    is_teaching = request.GET.get('is_teaching', '')
    is_management = request.GET.get('is_management', '')
    is_active = request.GET.get('is_active', '')
    min_salary = request.GET.get('min_salary', '')
    max_salary = request.GET.get('max_salary', '')
    
    # Apply text search
    if query:
        words = query.strip().split()
        if words:
            combined_q = Q()
            for word in words:
                word_q = (
                    Q(name__icontains=word) |
                    Q(code__icontains=word) |
                    Q(description__icontains=word)
                )
                combined_q &= word_q
            designations = designations.filter(combined_q)
    
    # Apply filters
    if department:
        designations = designations.filter(department_id=department)
    if is_teaching is not None and is_teaching:
        designations = designations.filter(is_teaching=(is_teaching.lower() == 'true'))
    if is_management is not None and is_management:
        designations = designations.filter(is_management=(is_management.lower() == 'true'))
    if is_active is not None and is_active:
        designations = designations.filter(is_active=(is_active.lower() == 'true'))
    
    # Apply salary filters
    if min_salary:
        try:
            designations = designations.filter(min_salary__gte=Decimal(min_salary))
        except (ValueError, TypeError):
            pass
    if max_salary:
        try:
            designations = designations.filter(max_salary__lte=Decimal(max_salary))
        except (ValueError, TypeError):
            pass
    
    return designations


def get_filtered_contracts(request):
    """Helper function to get filtered contracts queryset.
    
    Ordering: ACTIVE contracts always first, then by most recent start date,
    then alphabetically by staff name for stable tie-breaking.
    """
    contracts = Contract.objects.select_related(
        'staff'
    ).annotate(
        status_order=Case(
            When(status='ACTIVE', then=0),
            default=1,
            output_field=IntegerField()
        )
    ).order_by('status_order', '-start_date', 'staff__first_name')

    # -------------------------------------------------------------------------
    # FILTER PARAMETERS
    # -------------------------------------------------------------------------

    query            = request.GET.get('q', '').strip()
    contract_type    = request.GET.get('contract_type', '')
    status           = request.GET.get('status', '')
    staff            = request.GET.get('staff', '')
    start_date       = request.GET.get('start_date', '')
    end_date         = request.GET.get('end_date', '')
    expiring_soon    = request.GET.get('expiring_soon', '')
    is_permanent     = request.GET.get('is_permanent', '')
    salary_frequency = request.GET.get('salary_frequency', '')

    # -------------------------------------------------------------------------
    # TEXT SEARCH — multi-word AND logic
    # -------------------------------------------------------------------------

    if query:
        words = query.split()
        if words:
            combined_q = Q()
            for word in words:
                combined_q &= (
                    Q(contract_number__icontains=word) |
                    Q(staff__first_name__icontains=word) |
                    Q(staff__last_name__icontains=word) |
                    Q(staff__staff_id__icontains=word) |
                    Q(job_title__icontains=word)
                )
            contracts = contracts.filter(combined_q)

    # -------------------------------------------------------------------------
    # FILTERS
    # -------------------------------------------------------------------------

    if contract_type:
        contracts = contracts.filter(contract_type=contract_type)
    if status:
        contracts = contracts.filter(status=status)
    if staff:
        contracts = contracts.filter(staff_id=staff)
    if salary_frequency:
        contracts = contracts.filter(salary_frequency=salary_frequency)
    if start_date:
        contracts = contracts.filter(start_date__gte=start_date)
    if end_date:
        contracts = contracts.filter(end_date__lte=end_date)
    if is_permanent and is_permanent.lower() == 'true':
        contracts = contracts.filter(contract_type='PERMANENT')
    if expiring_soon and expiring_soon.lower() == 'true':
        threshold = timezone.now().date() + timedelta(days=30)
        contracts = contracts.filter(
            status='ACTIVE',
            end_date__lte=threshold,
            end_date__gte=timezone.now().date()
        )

    return contracts


def get_filtered_teachers(request):
    """Helper function to get filtered teachers queryset"""
    teachers = Teacher.objects.select_related(
        'staff',
        'staff__primary_department'
    ).prefetch_related(
        'assigned_classes',
        'assigned_classes__academic_level',
        'qualified_subjects',
        'preferred_academic_levels',
        Prefetch(
            'staff__staffdesignation_set',
            queryset=StaffDesignation.objects.filter(
                is_primary=True,
                is_active=True
            ).select_related('designation'),
            to_attr='primary_staff_designation'
        )
    ).annotate(
        assigned_classes_count=Count('assigned_classes', distinct=True),
        qualified_subjects_count=Count('qualified_subjects', distinct=True)
    )
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    department = request.GET.get('department', '')
    specialization = request.GET.get('specialization', '')
    is_class_teacher = request.GET.get('is_class_teacher', '')
    digital_literacy_level = request.GET.get('digital_literacy_level', '')
    can_teach_online = request.GET.get('can_teach_online', '')
    is_active = request.GET.get('is_active', '')
    
    # Filter by active status (default to active only)
    if is_active is not None and is_active:
        if is_active.lower() == 'true':
            teachers = teachers.filter(is_active=True)
        elif is_active.lower() == 'false':
            teachers = teachers.filter(is_active=False)
    else:
        teachers = teachers.filter(is_active=True)
    
    # Apply text search
    if query:
        words = query.strip().split()
        if words:
            combined_q = Q()
            for word in words:
                word_q = (
                    Q(staff__first_name__icontains=word) |
                    Q(staff__middle_name__icontains=word) |
                    Q(staff__last_name__icontains=word) |
                    Q(staff__staff_id__icontains=word) |
                    Q(specialization__icontains=word) |
                    Q(teaching_philosophy__icontains=word) |
                    Q(staff__phone_number__icontains=word) |
                    Q(staff__personal_email__icontains=word)
                )
                combined_q &= word_q
            teachers = teachers.filter(combined_q)
    
    # Apply filters
    if department:
        teachers = teachers.filter(staff__primary_department_id=department)
    if specialization:
        teachers = teachers.filter(specialization__icontains=specialization)
    if is_class_teacher is not None and is_class_teacher:
        teachers = teachers.filter(is_class_teacher=(is_class_teacher.lower() == 'true'))
    if can_teach_online is not None and can_teach_online:
        teachers = teachers.filter(can_teach_online=(can_teach_online.lower() == 'true'))
    if digital_literacy_level:
        teachers = teachers.filter(digital_literacy_level=digital_literacy_level)
    
    teachers = teachers.order_by('-is_active', 'staff__first_name', 'staff__last_name')
    
    return teachers

# =============================================================================
# STAFF VIEWS
# =============================================================================

@login_required
def staff_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""
    filter_form = StaffFilterForm(request.GET or None)
    staff = get_filtered_staff(request)
    
    # Calculate statistics
    total = staff.count()
    
    stats = {
        'total': total,
        'active': staff.filter(is_active=True).count(),
        'full_time': staff.filter(employment_status='FT').count(),
        'part_time': staff.filter(employment_status='PT').count(),
        'contract': staff.filter(employment_status='CT').count(),
        'male': staff.filter(gender='M').count(),
        'female': staff.filter(gender='F').count(),
        'with_active_contract': staff.filter(active_contract_count__gt=0).count(),
        'teachers': staff.filter(teacher__isnull=False).count(),
    }
    
    # Pagination
    paginator = Paginator(staff, 10)
    page_number = request.GET.get('page', 1)
    staff_page = paginator.get_page(page_number)
    
    # Detect HTMX request
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'staff_page': staff_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    # Return appropriate template
    if is_htmx:
        return render(request, 'hr/staff/partials/_staff_results.html', context)
    else:
        return render(request, 'hr/staff/list.html', context)


@login_required
def staff_profile(request, pk):
    """View staff profile with all related information"""
    staff = get_object_or_404(
        Staff.objects.prefetch_related(
            Prefetch(
                'staffdesignation_set',
                queryset=StaffDesignation.objects.filter(is_active=True).select_related('designation')
            ),
            Prefetch(
                'contracts',
                queryset=Contract.objects.order_by('-start_date')
            ),
        ),
        pk=pk
    )

    # Get staff summary using utils
    from .utils import (
        get_staff_age,
        get_years_of_service,
        get_days_until_birthday,
        is_birthday_today,
        is_staff_due_for_retirement,
    )
    
    try:
        summary = {
            'staff_id': staff.staff_id,
            'full_name': staff.full_name(),
            'employment_status': staff.get_employment_status_display(),
            'age': get_staff_age(staff),
            'years_of_service': get_years_of_service(staff),
            'days_until_birthday': get_days_until_birthday(staff),
            'is_birthday_today': is_birthday_today(staff),
            'retirement_info': is_staff_due_for_retirement(staff),
            'designation_count': staff.designations.count(),
            'contract_count': staff.contracts.count(),
        }
    except Exception as e:
        logger.error(f"Error getting staff summary: {e}")
        summary = {}

    # Get related data
    designations = staff.staffdesignation_set.filter(is_active=True)
    primary_designation = designations.filter(is_primary=True).first()
    
    contracts = staff.contracts.order_by('-start_date')
    active_contract = contracts.filter(status='ACTIVE').first()
    
    teacher_profile = None
    if hasattr(staff, 'teacher'):
        teacher_profile = staff.teacher
    
    salary_history = staff.salary_history.select_related(
        'contract', 'effective_period'
    ).order_by('-effective_date')[:5]

    context = {
        'staff': staff,
        'summary': summary,
        'designations': designations,
        'primary_designation': primary_designation,
        'contracts': contracts,
        'active_contract': active_contract,
        'teacher_profile': teacher_profile,
        'salary_history': salary_history,
    }
    
    return render(request, "hr/staff/profile.html", context)


@login_required
def staff_print_view(request):
    """Generate printable staff list"""
    
    selected_fields = request.GET.getlist('fields')
    if not selected_fields:
        selected_fields = [
            'staff_id', 'full_name', 'date_of_birth', 'gender',
            'primary_department', 'employment_status', 'phone_number'
        ]
    
    include_stats = request.GET.get('include_stats') == 'true'
    landscape_mode = request.GET.get('landscape') == 'true'
    
    staff = get_filtered_staff(request)
    
    stats = None
    if include_stats:
        total = staff.count()
        active_count = staff.filter(is_active=True).count()
        
        stats = {
            'total': total,
            'active': active_count,
            'active_percentage': round((active_count / total * 100), 1) if total > 0 else 0,
            'male': staff.filter(gender='M').count(),
            'female': staff.filter(gender='F').count(),
            'full_time': staff.filter(employment_status='FT').count(),
        }
    
    field_names = {
        'staff_id': 'Staff ID',
        'full_name': 'Full Name',
        'first_name': 'First Name',
        'last_name': 'Last Name',
        'date_of_birth': 'Date of Birth',
        'age': 'Age',
        'gender': 'Gender',
        'nationality': 'Nationality',
        'phone_number': 'Phone',
        'personal_email': 'Email',
        'primary_department': 'Department',
        'employment_status': 'Employment Status',
        'date_of_joining': 'Date of Joining',
        'marital_status': 'Marital Status',
        'religious_affiliation': 'Religion',
        'national_id': 'National ID',
    }
    
    selected_field_names = [
        field_names.get(field, field.replace('_', ' ').title()) 
        for field in selected_fields
    ]
    
    context = {
        'staff': staff,
        'stats': stats,
        'now': timezone.now(),
        'selected_fields': selected_fields,
        'selected_field_names': selected_field_names,
        'field_names': field_names,
        'landscape': landscape_mode,
        'title': 'Staff Report',
    }
    
    return render(request, 'hr/staff/print.html', context)


@login_required
def export_staff_excel(request):
    """Export staff to Excel with filters applied"""
    
    staff = get_filtered_staff(request)
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Staff"
    
    # Define styles
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_alignment = Alignment(horizontal="center", vertical="center")
    
    # Headers
    headers = [
        '#', 'Staff ID', 'Full Name', 'Gender', 'Department',
        'Employment Status', 'Date of Joining', 'Phone', 'Email', 'Active'
    ]
    ws.append(headers)
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
    
    # Data rows
    for idx, s in enumerate(staff, start=1):
        ws.append([
            idx,
            s.staff_id,
            s.full_name(),
            s.get_gender_display(),
            s.primary_department.name if s.primary_department else '',
            s.get_employment_status_display(),
            s.date_of_joining.strftime('%Y-%m-%d') if s.date_of_joining else '',
            s.phone_number,
            s.personal_email,
            'Yes' if s.is_active else 'No',
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
    filename = f"staff_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


@login_required
def staff_activate(request, pk):
    """Activate a staff member with HTMX support"""
    staff = get_object_or_404(Staff, pk=pk)
    
    if request.method == 'POST':
        if staff.is_active:
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f"{staff.full_name()} is already active"
                response['HX-Alert-Type'] = 'warning'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.warning(request, f"{staff.full_name()} is already active", extra_tags='sweetalert')
                return redirect('hr:staff_profile', pk=pk)
        
        staff.is_active = True
        staff.save(update_fields=['is_active', 'updated_at'])
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Staff member {staff.full_name()} has been activated successfully"
            response['HX-Alert-Type'] = 'success'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('hr:staff_profile', kwargs={'pk': pk})
            return response
        else:
            messages.success(
                request,
                f"Staff member {staff.full_name()} has been activated successfully",
                extra_tags='sweetalert'
            )
            return redirect('hr:staff_profile', pk=staff.pk)


@login_required
def staff_deactivate(request, pk):
    """Deactivate a staff member with HTMX support"""
    staff = get_object_or_404(Staff, pk=pk)
    
    if request.method == 'POST':
        if not staff.is_active:
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f"{staff.full_name()} is already inactive"
                response['HX-Alert-Type'] = 'warning'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.warning(request, f"{staff.full_name()} is already inactive", extra_tags='sweetalert')
                return redirect('hr:staff_profile', pk=pk)
        
        reason = request.POST.get('reason', 'No reason provided')
        
        staff.is_active = False
        staff.save(update_fields=['is_active', 'updated_at'])
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Staff member {staff.full_name()} has been deactivated"
            response['HX-Alert-Type'] = 'warning'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('hr:staff_profile', kwargs={'pk': pk})
            return response
        else:
            messages.warning(
                request,
                f"Staff member {staff.full_name()} has been deactivated",
                extra_tags='sweetalert'
            )
            return redirect('hr:staff_profile', pk=staff.pk)


# =============================================================================
# STAFF WIZARD FOR CREATION
# =============================================================================

class StaffWizardFileStorage(FileSystemStorage):
    """Custom storage for handling file uploads in wizard"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.location = os.path.join(self.location, 'wizard_temp')


class StaffCreateWizard(SessionWizardView):
    """
    Multi-step wizard for creating a staff member.
    
    Steps:
    1. Basic Information - personal details
    2. Contact Information - address and contact details
    3. Employment Information - department and employment details
    4. Qualifications - education and experience
    5. Banking Information - bank and statutory details
    6. Designation & Contract - optional designation and contract setup
    7. Confirmation - review and confirm
    
    Note: Staff ID is automatically generated by pre_save signal in signals.py
    """

    form_list = STAFF_WIZARD_FORMS
    template_name = 'hr/staff/wizard.html'
    file_storage = StaffWizardFileStorage()

    def get_template_names(self):
        """Return the template for all steps"""
        return [self.template_name]

    def get_context_data(self, form, **kwargs):
        """Add step names and progress tracking"""
        context = super().get_context_data(form=form, **kwargs)

        total_steps = len(self.form_list)
        current_step_index = list(self.form_list).index(self.steps.current)

        context.update({
            'step_names': STAFF_WIZARD_STEP_NAMES,
            'current_step_name': STAFF_WIZARD_STEP_NAMES.get(
                self.steps.current, 'Step'
            ),
            'progress_percentage': ((current_step_index) / (total_steps - 1)) * 100 if total_steps > 1 else 100,
        })

        # Add review data for confirmation step
        if self.steps.current == 'confirmation':
            context['basic_data'] = self.get_cleaned_data_for_step('basic_info')
            context['contact_data'] = self.get_cleaned_data_for_step('contact_info')
            context['employment_data'] = self.get_cleaned_data_for_step('employment_info')
            context['qualifications_data'] = self.get_cleaned_data_for_step('qualifications')
            context['banking_data'] = self.get_cleaned_data_for_step('banking_info')
            context['designation_contract_data'] = self.get_cleaned_data_for_step('designation_contract')

        return context

    def get_form_kwargs(self, step=None):
        """Pass additional kwargs to forms if needed"""
        kwargs = super().get_form_kwargs(step)
        return kwargs

    @transaction.atomic
    def done(self, form_list, **kwargs):
        """
        Persist all wizard data and create staff.
        Staff ID generation is handled automatically by the pre_save signal
        in signals.py (generate_staff_id function).
        """
        
        logger.info("=" * 80)
        logger.info("WIZARD DONE - Creating Staff")
        logger.info("=" * 80)

        try:
            # Merge cleaned data from all steps
            form_data = {}
            
            for step, form in zip(self.form_list.keys(), form_list):
                form_data.update(form.cleaned_data)

            # Create Staff
            staff = Staff(
                # Basic info
                salutation=form_data.get('salutation', ''),
                first_name=form_data.get('first_name'),
                middle_name=form_data.get('middle_name', ''),
                last_name=form_data.get('last_name'),
                date_of_birth=form_data.get('date_of_birth'),
                gender=form_data.get('gender'),
                marital_status=form_data.get('marital_status', ''),
                nationality=form_data.get('nationality', ''),
                ethnicity=form_data.get('ethnicity', ''),
                religious_affiliation=form_data.get('religious_affiliation', ''),
                national_id=form_data.get('national_id', ''),
                passport_number=form_data.get('passport_number', ''),
                
                # Contact info
                phone_number=form_data.get('phone_number'),
                alternative_phone=form_data.get('alternative_phone', ''),
                personal_email=form_data.get('personal_email', ''),
                emergency_contact_name=form_data.get('emergency_contact_name'),
                emergency_contact_relationship=form_data.get('emergency_contact_relationship'),
                emergency_contact_phone=form_data.get('emergency_contact_phone'),
                emergency_contact_address=form_data.get('emergency_contact_address', ''),
                
                # Employment info
                primary_department=form_data.get('primary_department'),
                employment_status=form_data.get('employment_status', 'FT'),
                date_of_joining=form_data.get('date_of_joining'),
                date_of_leaving=form_data.get('date_of_leaving'),
                
                # Qualifications
                qualification=form_data.get('qualification', ''),
                experience=form_data.get('experience', ''),
                skills=form_data.get('skills', ''),
                languages_spoken=form_data.get('languages_spoken', ''),
                professional_memberships=form_data.get('professional_memberships', ''),
                certifications=form_data.get('certifications', ''),
                
                # Banking info
                bank_account_name=form_data.get('bank_account_name', ''),
                bank_account_number=form_data.get('bank_account_number', ''),
                bank_name=form_data.get('bank_name', ''),
                bank_branch=form_data.get('bank_branch', ''),
                tax_identification_number=form_data.get('tax_identification_number', ''),
                social_security_number=form_data.get('social_security_number', ''),
                
                is_active=True,
            )
            
            staff.save()

            # Handle Designation
            create_designation = form_data.get('create_designation', False)
            
            if create_designation:
                designation = form_data.get('designation')
                if designation:
                    is_primary = form_data.get('is_primary_designation', True)
                    role_allowance = form_data.get('role_allowance', Decimal('0.00'))
                    
                    StaffDesignation.objects.create(
                        staff=staff,
                        designation=designation,
                        is_primary=is_primary,
                        start_date=get_school_today(),
                        is_active=True,
                        role_allowance=role_allowance,
                        assignment_type='PERMANENT'
                    )
                    
                    logger.info(f"Assigned designation: {designation.name}")

            # Handle Contract (Optional)
            create_contract = form_data.get('create_contract', False)
            
            if create_contract:
                contract_type = form_data.get('contract_type')
                contract_start_date = form_data.get('contract_start_date')
                contract_duration_months = form_data.get('contract_duration_months', 12)
                basic_salary = form_data.get('basic_salary')
                job_title = form_data.get('job_title')
                
                if contract_type and contract_start_date and basic_salary and job_title:
                    end_date = contract_start_date + timedelta(days=contract_duration_months * 30)
                    
                    contract = Contract.objects.create(
                        staff=staff,
                        contract_type=contract_type,
                        start_date=contract_start_date,
                        end_date=end_date,
                        basic_salary=basic_salary,
                        job_title=job_title,
                        status='DRAFT',
                        salary_frequency='MONTHLY',
                        working_hours_per_week=40,
                        annual_leave_days=21,
                    )
                    
                    logger.info(f"Created contract: {contract.contract_number}")

            messages.success(
                self.request,
                f"Staff member {staff.full_name()} "
                f"({staff.staff_id}) was created successfully!",
                extra_tags='sweetalert'
            )

            return redirect('hr:staff_profile', pk=staff.pk)

        except Exception as exc:
            logger.exception("Error in wizard done method:")
            logger.exception(exc)
            
            messages.error(
                self.request,
                f"Error creating staff: {exc}",
                extra_tags='sweetalert-error'
            )
            return redirect('hr:staff_list')


# View entry point
staff_create = StaffCreateWizard.as_view()


@login_required
def staff_edit(request, pk):
    """Edit existing staff member"""
    staff = get_object_or_404(Staff, pk=pk)

    if request.method == "POST":
        form = StaffForm(request.POST, request.FILES, instance=staff)
        if form.is_valid():
            staff = form.save()
            
            messages.success(
                request,
                f"Staff member {staff.full_name()} was updated successfully",
                extra_tags='sweetalert'
            )
            return redirect("hr:staff_profile", pk=staff.pk)
        else:
            messages.error(
                request,
                "Please correct the errors in the form",
                extra_tags='sweetalert-error'
            )
    else:
        form = StaffForm(instance=staff)

    context = {
        'form': form,
        'staff': staff,
        'title': 'Update Staff',
    }

    return render(request, 'hr/staff/form.html', context)


# =============================================================================
# DEPARTMENT VIEWS
# =============================================================================

@login_required
def department_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""
    filter_form = DepartmentFilterForm(request.GET or None)
    departments = get_filtered_departments(request)
    
    # Calculate statistics
    total = departments.count()
    
    stats = {
        'total': total,
        'active': departments.filter(is_active=True).count(),
        'academic': departments.filter(is_academic=True).count(),
        'administrative': departments.filter(department_type='ADMINISTRATIVE').count(),
        'support': departments.filter(department_type='SUPPORT').count(),
        'parent_departments': departments.filter(parent_department__isnull=True).count(),
        'sub_departments': departments.filter(parent_department__isnull=False).count(),
        'total_staff': sum(d.staff_count for d in departments),
        'total_budget': departments.aggregate(Sum('annual_budget'))['annual_budget__sum'] or 0,
    }
    
    # Pagination
    paginator = Paginator(departments, 10)
    page_number = request.GET.get('page', 1)
    departments_page = paginator.get_page(page_number)
    
    # Detect HTMX request
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'departments_page': departments_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    # Return appropriate template
    if is_htmx:
        return render(request, 'hr/departments/partials/_department_results.html', context)
    else:
        return render(request, 'hr/departments/list.html', context)


@login_required
def department_create(request):
    """Create new department"""
    if request.method == 'POST':
        form = DepartmentForm(request.POST)
        if form.is_valid():
            department = form.save()
            
            messages.success(
                request,
                f"Department {department.name} was created successfully",
                extra_tags='sweetalert'
            )
            return redirect('hr:department_list')
        else:
            messages.error(
                request,
                "Please correct the errors in the form",
                extra_tags='sweetalert-error'
            )
    else:
        form = DepartmentForm()
    
    context = {
        'form': form,
        'title': 'Create Department',
    }
    
    return render(request, 'hr/departments/form.html', context)


@login_required
def department_edit(request, pk):
    """Edit existing department"""
    department = get_object_or_404(Department, pk=pk)
    
    if request.method == 'POST':
        form = DepartmentForm(request.POST, instance=department)
        if form.is_valid():
            department = form.save()
            
            messages.success(
                request,
                f"Department {department.name} was updated successfully",
                extra_tags='sweetalert'
            )
            return redirect('hr:department_list')
        else:
            messages.error(
                request,
                "Please correct the errors in the form",
                extra_tags='sweetalert-error'
            )
    else:
        form = DepartmentForm(instance=department)
    
    context = {
        'form': form,
        'department': department,
        'title': 'Update Department',
    }
    
    return render(request, 'hr/departments/form.html', context)


@login_required
def department_delete(request, pk):
    """Delete department with HTMX support"""
    department = get_object_or_404(Department, pk=pk)
    
    if request.method == 'POST':
        # Validation
        if department.primary_staff.exists():
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f"Cannot delete '{department.name}' because it has staff members"
                response['HX-Alert-Type'] = 'error'
                response['HX-Alert-Title'] = 'Cannot Delete'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(
                    request,
                    f"Cannot delete '{department.name}' because it has staff members",
                    extra_tags='sweetalert-error'
                )
                return redirect('hr:department_list')
        
        if department.sub_departments.exists():
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f"Cannot delete '{department.name}' because it has sub-departments"
                response['HX-Alert-Type'] = 'error'
                response['HX-Alert-Title'] = 'Cannot Delete'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(
                    request,
                    f"Cannot delete '{department.name}' because it has sub-departments",
                    extra_tags='sweetalert-error'
                )
                return redirect('hr:department_list')
        
        department_name = department.name
        department.delete()
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Department '{department_name}' deleted successfully"
            response['HX-Alert-Type'] = 'success'
            response['HX-Alert-Title'] = 'Deleted!'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('hr:department_list')
            return response
        else:
            messages.success(
                request,
                f"Department '{department_name}' deleted successfully",
                extra_tags='sweetalert'
            )
            return redirect('hr:department_list')


# =============================================================================
# DESIGNATION VIEWS
# =============================================================================

@login_required
def designation_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""
    filter_form = DesignationFilterForm(request.GET or None)
    designations = get_filtered_designations(request)
    
    # Calculate statistics
    total = designations.count()
    
    stats = {
        'total': total,
        'active': designations.filter(is_active=True).count(),
        'teaching': designations.filter(is_teaching=True).count(),
        'management': designations.filter(is_management=True).count(),
        'with_reports_to': designations.filter(reports_to__isnull=False).count(),
        'total_staff': sum(d.staff_count for d in designations),
        'avg_min_salary': designations.filter(min_salary__isnull=False).aggregate(
            Avg('min_salary'))['min_salary__avg'] or 0,
        'avg_max_salary': designations.filter(max_salary__isnull=False).aggregate(
            Avg('max_salary'))['max_salary__avg'] or 0,
    }
    
    # Pagination
    paginator = Paginator(designations, 10)
    page_number = request.GET.get('page', 1)
    designations_page = paginator.get_page(page_number)
    
    # Detect HTMX request
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'designations_page': designations_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    # Return appropriate template
    if is_htmx:
        return render(request, 'hr/designations/partials/_designation_results.html', context)
    else:
        return render(request, 'hr/designations/list.html', context)


@login_required
def designation_create(request):
    """Create new designation"""
    if request.method == 'POST':
        form = DesignationForm(request.POST)
        if form.is_valid():
            designation = form.save()
            
            messages.success(
                request,
                f"Designation {designation.name} was created successfully",
                extra_tags='sweetalert'
            )
            return redirect('hr:designation_list')
        else:
            messages.error(
                request,
                "Please correct the errors in the form",
                extra_tags='sweetalert-error'
            )
    else:
        form = DesignationForm()
    
    context = {
        'form': form,
        'title': 'Create Designation',
    }
    
    return render(request, 'hr/designations/form.html', context)


@login_required
def designation_edit(request, pk):
    """Edit existing designation"""
    designation = get_object_or_404(Designation, pk=pk)
    
    if request.method == 'POST':
        form = DesignationForm(request.POST, instance=designation)
        if form.is_valid():
            designation = form.save()
            
            messages.success(
                request,
                f"Designation {designation.name} was updated successfully",
                extra_tags='sweetalert'
            )
            return redirect('hr:designation_list')
        else:
            messages.error(
                request,
                "Please correct the errors in the form",
                extra_tags='sweetalert-error'
            )
    else:
        form = DesignationForm(instance=designation)
    
    context = {
        'form': form,
        'designation': designation,
        'title': 'Update Designation',
    }
    
    return render(request, 'hr/designations/form.html', context)


@login_required
def designation_detail(request, pk):
    """View designation details"""
    designation = get_object_or_404(
        Designation.objects.select_related('department', 'reports_to'),
        pk=pk
    )
    
    # Get staff with this designation
    staff_assignments = StaffDesignation.objects.filter(
        designation=designation,
        is_active=True
    ).select_related('staff__primary_department').order_by('-is_primary', 'staff__first_name')
    
    # Get subordinate designations
    subordinates = designation.subordinate_designations.filter(is_active=True)
    
    context = {
        'designation': designation,
        'staff_assignments': staff_assignments,
        'subordinates': subordinates,
        'staff_count': staff_assignments.count(),
    }
    
    return render(request, 'hr/designations/detail.html', context)


@login_required
def designation_delete(request, pk):
    """Delete designation with HTMX support"""
    designation = get_object_or_404(Designation, pk=pk)
    
    if request.method == 'POST':
        # Validation
        if designation.staff_members.exists():
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f"Cannot delete '{designation.name}' because it has staff assignments"
                response['HX-Alert-Type'] = 'error'
                response['HX-Alert-Title'] = 'Cannot Delete'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(
                    request,
                    f"Cannot delete '{designation.name}' because it has staff assignments",
                    extra_tags='sweetalert-error'
                )
                return redirect('hr:designation_list')
        
        designation_name = designation.name
        designation.delete()
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Designation '{designation_name}' deleted successfully"
            response['HX-Alert-Type'] = 'success'
            response['HX-Alert-Title'] = 'Deleted!'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('hr:designation_list')
            return response
        else:
            messages.success(
                request,
                f"Designation '{designation_name}' deleted successfully",
                extra_tags='sweetalert'
            )
            return redirect('hr:designation_list')


# =============================================================================
# CONTRACT VIEWS  
# =============================================================================

@login_required
def contract_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""
    filter_form = ContractFilterForm(request.GET or None)
    contracts = get_filtered_contracts(request)
    
    # Calculate statistics
    total = contracts.count()
    today = timezone.now().date()
    
    stats = {
        'total': total,
        'active': contracts.filter(status='ACTIVE').count(),
        'draft': contracts.filter(status='DRAFT').count(),
        'expired': contracts.filter(status='EXPIRED').count(),
        'terminated': contracts.filter(status='TERMINATED').count(),
        'permanent': contracts.filter(contract_type='PERMANENT').count(),
        'fixed_term': contracts.filter(contract_type='FIXED_TERM').count(),
        'expiring_soon': contracts.filter(
            status='ACTIVE',
            end_date__lte=today + timedelta(days=30),
            end_date__gte=today
        ).count(),
        'avg_salary': contracts.filter(status='ACTIVE').aggregate(
            Avg('basic_salary'))['basic_salary__avg'] or 0,
        'total_salary_obligation': contracts.filter(status='ACTIVE').aggregate(
            Sum('basic_salary'))['basic_salary__sum'] or 0,
    }
    
    # Pagination
    paginator = Paginator(contracts, 20)
    page_number = request.GET.get('page', 1)
    contracts_page = paginator.get_page(page_number)
    
    # Detect HTMX request
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'contracts_page': contracts_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    # Return appropriate template
    if is_htmx:
        return render(request, 'hr/contracts/partials/_contract_results.html', context)
    else:
        return render(request, 'hr/contracts/list.html', context)


@login_required
def contract_create(request):
    """Create new contract"""
    if request.method == 'POST':
        form = ContractForm(request.POST, request.FILES)
        if form.is_valid():
            contract = form.save()
            
            messages.success(
                request,
                f"Contract {contract.contract_number} was created successfully",
                extra_tags='sweetalert'
            )
            return redirect('hr:contract_detail', pk=contract.pk)
        else:
            messages.error(
                request,
                "Please correct the errors in the form",
                extra_tags='sweetalert-error'
            )
    else:
        form = ContractForm()
    
    context = {
        'form': form,
        'title': 'Create Contract',
    }
    
    return render(request, 'hr/contracts/form.html', context)


@login_required
def contract_edit(request, pk):
    """Edit existing contract"""
    contract = get_object_or_404(Contract, pk=pk)
    
    if request.method == 'POST':
        form = ContractForm(request.POST, request.FILES, instance=contract)
        if form.is_valid():
            contract = form.save()
            
            messages.success(
                request,
                f"Contract {contract.contract_number} was updated successfully",
                extra_tags='sweetalert'
            )
            return redirect('hr:contract_detail', pk=contract.pk)
        else:
            messages.error(
                request,
                "Please correct the errors in the form",
                extra_tags='sweetalert-error'
            )
    else:
        form = ContractForm(instance=contract)
    
    context = {
        'form': form,
        'contract': contract,
        'title': 'Update Contract',
    }
    
    return render(request, 'hr/contracts/form.html', context)


@login_required
def contract_detail(request, pk):
    """View contract details"""
    contract = get_object_or_404(
        Contract.objects.select_related('staff', 'staff__primary_department'),
        pk=pk
    )
    
    # Calculate contract metrics
    from .utils import (
        calculate_monthly_salary,
        calculate_annual_salary,
        calculate_daily_rate,
        calculate_hourly_rate,
    )
    
    metrics = {
        'monthly_salary': calculate_monthly_salary(contract),
        'annual_salary': calculate_annual_salary(contract),
        'daily_rate': calculate_daily_rate(contract),
        'hourly_rate': calculate_hourly_rate(contract),
        'days_until_expiry': contract.days_until_expiry,
        'duration_in_months': contract.duration_in_months,
        'is_permanent': contract.is_permanent,
        'is_probationary': contract.is_probationary,
    }
    
    # Get benefits
    benefits = contract.benefits.filter(is_active=True)
    
    context = {
        'contract': contract,
        'metrics': metrics,
        'benefits': benefits,
    }
    
    return render(request, 'hr/contracts/detail.html', context)


@login_required
def contract_activate(request, pk):
    """Activate a contract with HTMX support"""
    contract = get_object_or_404(Contract, pk=pk)
    
    if request.method == 'POST':
        contract.activate(user=request.user)
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Contract {contract.contract_number} has been activated"
            response['HX-Alert-Type'] = 'success'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('hr:contract_detail', kwargs={'pk': pk})
            return response
        else:
            messages.success(
                request,
                f"Contract {contract.contract_number} has been activated",
                extra_tags='sweetalert'
            )
            return redirect('hr:contract_detail', pk=contract.pk)


@login_required
def contract_terminate(request, pk):
    """Terminate a contract with HTMX support"""
    contract = get_object_or_404(Contract, pk=pk)
    
    if request.method == 'POST':
        reason = request.POST.get('termination_reason', 'OTHER')
        notes = request.POST.get('termination_notes', '')
        termination_date = request.POST.get('termination_date')
        
        if termination_date:
            from datetime import datetime
            termination_date = datetime.strptime(termination_date, '%Y-%m-%d').date()
        else:
            termination_date = get_school_today()
        
        contract.terminate(
            reason=reason,
            user=request.user,
            termination_date=termination_date,
            notes=notes
        )
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Contract {contract.contract_number} has been terminated"
            response['HX-Alert-Type'] = 'warning'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('hr:contract_detail', kwargs={'pk': pk})
            return response
        else:
            messages.warning(
                request,
                f"Contract {contract.contract_number} has been terminated",
                extra_tags='sweetalert'
            )
            return redirect('hr:contract_detail', pk=contract.pk)


@login_required
def contract_delete(request, pk):
    """Delete contract with HTMX support"""
    contract = get_object_or_404(Contract, pk=pk)
    
    if request.method == 'POST':
        # Validation
        if contract.status == 'ACTIVE':
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = "Cannot delete active contracts"
                response['HX-Alert-Type'] = 'error'
                response['HX-Alert-Title'] = 'Cannot Delete'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(
                    request,
                    "Cannot delete active contracts",
                    extra_tags='sweetalert-error'
                )
                return redirect('hr:contract_list')
        
        contract_number = contract.contract_number
        contract.delete()
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Contract '{contract_number}' deleted successfully"
            response['HX-Alert-Type'] = 'success'
            response['HX-Alert-Title'] = 'Deleted!'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('hr:contract_list')
            return response
        else:
            messages.success(
                request,
                f"Contract '{contract_number}' deleted successfully",
                extra_tags='sweetalert'
            )
            return redirect('hr:contract_list')


# =============================================================================
# TEACHER VIEWS
# =============================================================================

@login_required
def teacher_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""
    filter_form = TeacherFilterForm(request.GET or None)
    teachers = get_filtered_teachers(request)
    
    # Calculate comprehensive stats
    total = teachers.count()
    all_teachers = teachers
    
    stats = {
        'total': total,
        'active': all_teachers.filter(is_active=True).count(),
        'inactive': all_teachers.filter(is_active=False).count(),
        'active_staff': all_teachers.filter(staff__is_active=True).count(),
        'class_teachers': all_teachers.filter(is_class_teacher=True, is_active=True).count(),
        'non_class_teachers': all_teachers.filter(is_class_teacher=False, is_active=True).count(),
        'can_teach_online': all_teachers.filter(can_teach_online=True, is_active=True).count(),
        'cannot_teach_online': all_teachers.filter(can_teach_online=False, is_active=True).count(),
        'avg_teaching_load': round(all_teachers.filter(
            is_active=True
        ).aggregate(
            Avg('current_teaching_load')
        )['current_teaching_load__avg'] or 0, 2),
        'avg_max_hours': round(all_teachers.filter(
            is_active=True
        ).aggregate(
            Avg('max_hours_per_week')
        )['max_hours_per_week__avg'] or 0, 2),
        'overloaded': all_teachers.filter(
            is_active=True,
            current_teaching_load__gt=F('max_hours_per_week')
        ).count(),
    }
    
    # Pagination
    paginator = Paginator(teachers, 20)
    page_number = request.GET.get('page', 1)
    teachers_page = paginator.get_page(page_number)
    
    # Detect HTMX request
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'teachers_page': teachers_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    # Return appropriate template
    if is_htmx:
        return render(request, 'hr/teachers/partials/_teacher_results.html', context)
    else:
        return render(request, 'hr/teachers/list.html', context)


@login_required
def teacher_create(request):
    """Create new teacher profile"""
    if request.method == 'POST':
        form = TeacherForm(request.POST)
        if form.is_valid():
            teacher = form.save()
            
            messages.success(
                request,
                f"Teacher profile for {teacher.staff.full_name()} was created successfully",
                extra_tags='sweetalert'
            )
            return redirect('hr:teacher_profile', pk=teacher.pk)
        else:
            messages.error(
                request,
                "Please correct the errors in the form",
                extra_tags='sweetalert-error'
            )
    else:
        form = TeacherForm()
    
    context = {
        'form': form,
        'title': 'Create Teacher Profile',
    }
    
    return render(request, 'hr/teachers/form.html', context)


@login_required
def teacher_edit(request, pk):
    """Edit existing teacher profile"""
    teacher = get_object_or_404(Teacher, pk=pk)
    
    if request.method == 'POST':
        form = TeacherForm(request.POST, instance=teacher)
        if form.is_valid():
            teacher = form.save()
            
            messages.success(
                request,
                f"Teacher profile for {teacher.staff.full_name()} was updated successfully",
                extra_tags='sweetalert'
            )
            return redirect('hr:teacher_profile', pk=teacher.pk)
        else:
            messages.error(
                request,
                "Please correct the errors in the form",
                extra_tags='sweetalert-error'
            )
    else:
        form = TeacherForm(instance=teacher)
    
    context = {
        'form': form,
        'teacher': teacher,
        'title': 'Update Teacher Profile',
    }
    
    return render(request, 'hr/teachers/form.html', context)


@login_required
def teacher_profile(request, pk):
    """View teacher profile"""
    teacher = get_object_or_404(
        Teacher.objects.select_related('staff__primary_department')
        .prefetch_related('qualified_subjects', 'preferred_academic_levels', 'assigned_classes'),
        pk=pk
    )
    
    # Calculate workload metrics
    from .utils import get_teacher_workload, is_teacher_overloaded, calculate_available_teaching_hours
    
    metrics = {
        'workload_percentage': get_teacher_workload(teacher),
        'is_overloaded': is_teacher_overloaded(teacher),
        'available_hours': calculate_available_teaching_hours(teacher),
        'qualified_subject_count': teacher.qualified_subjects.count(),
        'assigned_class_count': teacher.assigned_classes.count(),
    }
    
    context = {
        'teacher': teacher,
        'metrics': metrics,
    }
    
    return render(request, 'hr/teachers/profile.html', context)


@login_required
def teacher_reactivate(request, pk):
    """Reactivate an inactive teacher profile with HTMX support"""
    teacher = get_object_or_404(Teacher, pk=pk)
    
    if request.method == 'POST':
        teacher.is_active = True
        teacher.save(update_fields=['is_active', 'updated_at'])
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Teacher profile for {teacher.staff.full_name()} has been reactivated"
            response['HX-Alert-Type'] = 'success'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('hr:teacher_profile', kwargs={'pk': pk})
            return response
        else:
            messages.success(
                request,
                f"Teacher profile for {teacher.staff.full_name()} has been reactivated.",
                extra_tags='sweetalert'
            )
            logger.info(f"Teacher profile reactivated: {teacher.staff.full_name()}")
            return redirect('hr:teacher_profile', pk=teacher.pk)


@login_required
def teacher_deactivate(request, pk):
    """Deactivate an active teacher profile with HTMX support"""
    teacher = get_object_or_404(Teacher, pk=pk)
    
    # Check if they have active teaching designations
    has_teaching_designation = StaffDesignation.objects.filter(
        staff=teacher.staff,
        designation__is_teaching=True,
        is_active=True
    ).exists()
    
    if has_teaching_designation:
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = (
                f"Cannot deactivate teacher profile for {teacher.staff.full_name()} "
                f"because they have active teaching designations. Remove teaching designations first."
            )
            response['HX-Alert-Type'] = 'warning'
            response['HX-Close-Modal'] = 'true'
            return response
        else:
            messages.warning(
                request,
                f"Cannot deactivate teacher profile for {teacher.staff.full_name()} "
                f"because they have active teaching designations. "
                f"Remove teaching designations first.",
                extra_tags='sweetalert'
            )
            return redirect('hr:teacher_profile', pk=teacher.pk)
    
    if request.method == 'POST':
        teacher.is_active = False
        teacher.save(update_fields=['is_active', 'updated_at'])
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Teacher profile for {teacher.staff.full_name()} has been deactivated"
            response['HX-Alert-Type'] = 'warning'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('hr:teacher_list')
            return response
        else:
            messages.success(
                request,
                f"Teacher profile for {teacher.staff.full_name()} has been deactivated.",
                extra_tags='sweetalert'
            )
            logger.info(f"Teacher profile deactivated: {teacher.staff.full_name()}")
            return redirect('hr:teacher_list')


@login_required
def teacher_delete(request, pk):
    """Delete teacher profile with HTMX support"""
    teacher = get_object_or_404(Teacher, pk=pk)
    
    if request.method == 'POST':
        # Validation
        if teacher.assigned_classes.exists():
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = "Cannot delete teacher with assigned classes"
                response['HX-Alert-Type'] = 'error'
                response['HX-Alert-Title'] = 'Cannot Delete'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(
                    request,
                    "Cannot delete teacher with assigned classes",
                    extra_tags='sweetalert-error'
                )
                return redirect('hr:teacher_list')
        
        teacher_name = teacher.staff.full_name()
        staff_pk = teacher.staff.pk
        teacher.delete()
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Teacher profile for '{teacher_name}' deleted successfully"
            response['HX-Alert-Type'] = 'success'
            response['HX-Alert-Title'] = 'Deleted!'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('hr:staff_profile', kwargs={'pk': staff_pk})
            return response
        else:
            messages.success(
                request,
                f"Teacher profile for '{teacher_name}' deleted successfully",
                extra_tags='sweetalert'
            )
            return redirect('hr:staff_profile', pk=staff_pk)


# =============================================================================
# STAFF DESIGNATION ASSIGNMENT VIEWS
# =============================================================================

@login_required
def staff_assign_designation(request, staff_pk):
    """Assign a new designation to existing staff member"""
    staff = get_object_or_404(Staff, pk=staff_pk)
    
    if request.method == 'POST':
        form = StaffDesignationForm(request.POST)
        if form.is_valid():
            staff_designation = form.save(commit=False)
            staff_designation.staff = staff
            
            # If marking as primary, unset other primary designations
            if staff_designation.is_primary:
                StaffDesignation.objects.filter(
                    staff=staff,
                    is_primary=True
                ).update(is_primary=False)
            
            staff_designation.save()
            
            messages.success(
                request,
                f"Designation {staff_designation.designation.name} assigned to {staff.full_name()}",
                extra_tags='sweetalert'
            )
            return redirect('hr:staff_profile', pk=staff.pk)
        else:
            messages.error(
                request,
                "Please correct the errors in the form",
                extra_tags='sweetalert-error'
            )
    else:
        # Pre-fill staff field
        form = StaffDesignationForm(initial={
            'staff': staff,
            'start_date': get_school_today(),
            'is_active': True,
            'assignment_type': 'PERMANENT'
        })
    
    context = {
        'form': form,
        'staff': staff,
        'title': f'Assign Designation to {staff.full_name()}'
    }
    
    return render(request, 'hr/staff/assign_designation.html', context)


@login_required
def staff_designation_edit(request, pk):
    """Edit an existing staff designation assignment"""
    staff_designation = get_object_or_404(
        StaffDesignation.objects.select_related('staff', 'designation'),
        pk=pk
    )
    
    if request.method == 'POST':
        form = StaffDesignationForm(request.POST, instance=staff_designation)
        if form.is_valid():
            staff_designation = form.save(commit=False)
            
            # If marking as primary, unset other primary designations
            if staff_designation.is_primary:
                StaffDesignation.objects.filter(
                    staff=staff_designation.staff,
                    is_primary=True
                ).exclude(pk=staff_designation.pk).update(is_primary=False)
            
            staff_designation.save()
            
            messages.success(
                request,
                f"Designation assignment updated successfully",
                extra_tags='sweetalert'
            )
            return redirect('hr:staff_profile', pk=staff_designation.staff.pk)
        else:
            messages.error(
                request,
                "Please correct the errors in the form",
                extra_tags='sweetalert-error'
            )
    else:
        form = StaffDesignationForm(instance=staff_designation)
    
    context = {
        'form': form,
        'staff_designation': staff_designation,
        'staff': staff_designation.staff,
        'title': 'Update Designation Assignment'
    }
    
    return render(request, 'hr/staff/designation_form.html', context)


@login_required
def staff_designation_deactivate(request, pk):
    """Deactivate a staff designation assignment with HTMX support"""
    staff_designation = get_object_or_404(StaffDesignation, pk=pk)
    
    if request.method == 'POST':
        # Don't allow deactivating the only primary designation
        if staff_designation.is_primary:
            other_active = StaffDesignation.objects.filter(
                staff=staff_designation.staff,
                is_active=True
            ).exclude(pk=staff_designation.pk).exists()
            
            if not other_active:
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = "Cannot deactivate the only active designation. Assign another designation first."
                    response['HX-Alert-Type'] = 'error'
                    response['HX-Close-Modal'] = 'true'
                    return response
                else:
                    messages.error(
                        request,
                        "Cannot deactivate the only active designation. Assign another designation first.",
                        extra_tags='sweetalert-error'
                    )
                    return redirect('hr:staff_profile', pk=staff_designation.staff.pk)
        
        # Set end date and deactivate
        staff_designation.end_date = get_school_today()
        staff_designation.is_active = False
        staff_designation.save()
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Designation {staff_designation.designation.name} has been deactivated"
            response['HX-Alert-Type'] = 'warning'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('hr:staff_profile', kwargs={'pk': staff_designation.staff.pk})
            return response
        else:
            messages.warning(
                request,
                f"Designation {staff_designation.designation.name} has been deactivated",
                extra_tags='sweetalert'
            )
            return redirect('hr:staff_profile', pk=staff_designation.staff.pk)


@login_required
def staff_designation_activate(request, pk):
    """Reactivate a staff designation assignment with HTMX support"""
    staff_designation = get_object_or_404(StaffDesignation, pk=pk)
    
    if request.method == 'POST':
        staff_designation.end_date = None
        staff_designation.is_active = True
        staff_designation.save()
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Designation {staff_designation.designation.name} has been reactivated"
            response['HX-Alert-Type'] = 'success'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('hr:staff_profile', kwargs={'pk': staff_designation.staff.pk})
            return response
        else:
            messages.success(
                request,
                f"Designation {staff_designation.designation.name} has been reactivated",
                extra_tags='sweetalert'
            )
            return redirect('hr:staff_profile', pk=staff_designation.staff.pk)


@login_required
def staff_designation_set_primary(request, pk):
    """Set a designation as primary for a staff member with HTMX support"""
    staff_designation = get_object_or_404(StaffDesignation, pk=pk)
    
    if request.method == 'POST':
        if not staff_designation.is_active:
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = "Cannot set inactive designation as primary. Activate it first."
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(
                    request,
                    "Cannot set inactive designation as primary. Activate it first.",
                    extra_tags='sweetalert-error'
                )
                return redirect('hr:staff_profile', pk=staff_designation.staff.pk)
        
        # Unset other primary designations
        StaffDesignation.objects.filter(
            staff=staff_designation.staff,
            is_primary=True
        ).update(is_primary=False)
        
        # Set this as primary
        staff_designation.is_primary = True
        staff_designation.save()
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Designation {staff_designation.designation.name} set as primary"
            response['HX-Alert-Type'] = 'success'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('hr:staff_profile', kwargs={'pk': staff_designation.staff.pk})
            return response
        else:
            messages.success(
                request,
                f"Designation {staff_designation.designation.name} set as primary",
                extra_tags='sweetalert'
            )
            return redirect('hr:staff_profile', pk=staff_designation.staff.pk)


@login_required
def staff_designation_delete(request, pk):
    """Delete staff designation with HTMX support"""
    assignment = get_object_or_404(StaffDesignation, pk=pk)
    staff = assignment.staff
    designation = assignment.designation
    
    if request.method == 'POST':
        assignment.delete()
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Designation assignment removed: {staff.full_name()} - {designation.name}"
            response['HX-Alert-Type'] = 'success'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('hr:staff_profile', kwargs={'pk': staff.pk})
            return response
        else:
            messages.success(
                request,
                f'Designation assignment removed: {staff.full_name()} - {designation.name}',
                extra_tags='sweetalert'
            )
            return redirect('hr:staff_profile', pk=staff.pk)


# =============================================================================
# ADDITIONAL STAFF ACTIONS
# =============================================================================

@login_required
def staff_delete(request, pk):
    """Delete staff with HTMX support"""
    staff = get_object_or_404(Staff, pk=pk)
    
    if request.method == 'POST':
        # Validation - Check if active
        if staff.is_active:
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = "Cannot delete active staff. Please deactivate first."
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(
                    request,
                    "Cannot delete active staff. Please deactivate first.",
                    extra_tags='sweetalert-error'
                )
                return redirect('hr:staff_list')
        
        # Check for active contracts
        if staff.contracts.filter(status='ACTIVE').exists():
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = "Cannot delete staff with active contracts"
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(
                    request,
                    "Cannot delete staff with active contracts",
                    extra_tags='sweetalert-error'
                )
                return redirect('hr:staff_list')
        
        # Check for payroll records
        if hasattr(staff, 'payrolls') and staff.payrolls.exists():
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = "Cannot delete staff with payroll records"
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(
                    request,
                    "Cannot delete staff with payroll records",
                    extra_tags='sweetalert-error'
                )
                return redirect('hr:staff_list')
        
        staff_name = staff.full_name()
        staff.delete()
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Staff member '{staff_name}' deleted successfully"
            response['HX-Alert-Type'] = 'success'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('hr:staff_list')
            return response
        else:
            messages.success(
                request,
                f"Staff member '{staff_name}' deleted successfully",
                extra_tags='sweetalert'
            )
            return redirect('hr:staff_list')


# =============================================================================
# ADDITIONAL CONTRACT ACTIONS
# =============================================================================

@login_required
def contract_renew(request, pk):
    """Renew contract with HTMX support"""
    contract = get_object_or_404(Contract, pk=pk)
    
    if request.method == 'POST':
        # Check if can be renewed
        if contract.status not in ['ACTIVE', 'EXPIRED']:
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f"Cannot renew contract with status: {contract.get_status_display()}"
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(
                    request,
                    f"Cannot renew contract with status: {contract.get_status_display()}",
                    extra_tags='sweetalert-error'
                )
                return redirect('hr:contract_detail', pk=pk)
        
        new_end_date = request.POST.get('new_end_date')
        
        try:
            if new_end_date:
                from datetime import datetime
                new_end_date = datetime.strptime(new_end_date, '%Y-%m-%d').date()
            
            contract.renew(new_end_date=new_end_date, user=request.user)
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f"Contract {contract.contract_number} renewed successfully"
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('hr:contract_detail', kwargs={'pk': pk})
                return response
            else:
                messages.success(
                    request,
                    f"Contract {contract.contract_number} renewed successfully",
                    extra_tags='sweetalert'
                )
                return redirect('hr:contract_detail', pk=pk)
            
        except Exception as e:
            logger.error(f"Error renewing contract: {e}")
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f"Error renewing contract: {str(e)}"
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(
                    request,
                    f"Error renewing contract: {str(e)}",
                    extra_tags='sweetalert-error'
                )
                return redirect('hr:contract_detail', pk=pk)


# =============================================================================
# ATTENDANCE ACTIONS
# =============================================================================

@login_required
def attendance_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""
    filter_form = AttendanceFilterForm(request.GET or None)
    
    # Build queryset
    attendance_records = Attendance.objects.select_related(
        'staff__primary_department'
    ).order_by('-date', 'staff__first_name')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    staff = request.GET.get('staff', '')
    status = request.GET.get('status', '')
    work_mode = request.GET.get('work_mode', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    
    # Apply text search
    if query:
        words = query.strip().split()
        if words:
            combined_q = Q()
            for word in words:
                word_q = (
                    Q(staff__first_name__icontains=word) |
                    Q(staff__last_name__icontains=word) |
                    Q(staff__staff_id__icontains=word)
                )
                combined_q &= word_q
            attendance_records = attendance_records.filter(combined_q)
    
    # Apply filters
    if staff:
        attendance_records = attendance_records.filter(staff_id=staff)
    if status:
        attendance_records = attendance_records.filter(status=status)
    if work_mode:
        attendance_records = attendance_records.filter(work_mode=work_mode)
    if date_from:
        attendance_records = attendance_records.filter(date__gte=date_from)
    if date_to:
        attendance_records = attendance_records.filter(date__lte=date_to)
    
    # Calculate statistics
    total = attendance_records.count()
    
    stats = {
        'total': total,
        'present': attendance_records.filter(status='PRESENT').count(),
        'absent': attendance_records.filter(status='ABSENT').count(),
        'late': attendance_records.filter(status='LATE').count(),
        'on_leave': attendance_records.filter(status='LEAVE').count(),
        'office': attendance_records.filter(work_mode='OFFICE').count(),
        'remote': attendance_records.filter(work_mode='REMOTE').count(),
        'avg_work_hours': attendance_records.filter(work_hours__isnull=False).aggregate(
            Avg('work_hours'))['work_hours__avg'] or 0,
        'total_overtime': attendance_records.aggregate(
            Sum('overtime_hours'))['overtime_hours__sum'] or 0,
    }
    
    # Pagination
    paginator = Paginator(attendance_records, 20)
    page_number = request.GET.get('page', 1)
    attendance_page = paginator.get_page(page_number)
    
    # Detect HTMX request
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'attendance_page': attendance_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    # Return appropriate template
    if is_htmx:
        return render(request, 'hr/attendance/partials/_attendance_results.html', context)
    else:
        return render(request, 'hr/attendance/list.html', context)


@login_required
def attendance_create(request):
    """Create attendance record"""
    if request.method == 'POST':
        form = AttendanceForm(request.POST)
        if form.is_valid():
            attendance = form.save()
            
            messages.success(
                request,
                f"Attendance recorded for {attendance.staff.full_name()}",
                extra_tags='sweetalert'
            )
            return redirect('hr:attendance_list')
        else:
            messages.error(
                request,
                "Please correct the errors in the form",
                extra_tags='sweetalert-error'
            )
    else:
        form = AttendanceForm()
    
    context = {
        'form': form,
        'title': 'Record Attendance',
    }
    
    return render(request, 'hr/attendance/form.html', context)


@login_required
def attendance_detail(request, pk):
    """View attendance details"""
    attendance = get_object_or_404(Attendance, pk=pk)
    return render(request, 'hr/attendance/detail.html', {'attendance': attendance})


@login_required
def attendance_edit(request, pk):
    """Edit attendance record"""
    attendance = get_object_or_404(Attendance, pk=pk)
    
    if request.method == 'POST':
        form = AttendanceForm(request.POST, instance=attendance)
        if form.is_valid():
            attendance = form.save()
            
            messages.success(
                request,
                f"Attendance updated for {attendance.staff.full_name()}",
                extra_tags='sweetalert'
            )
            return redirect('hr:attendance_list')
        else:
            messages.error(
                request,
                "Please correct the errors in the form",
                extra_tags='sweetalert-error'
            )
    else:
        form = AttendanceForm(instance=attendance)
    
    context = {
        'form': form,
        'attendance': attendance,
        'title': 'Update Attendance',
    }
    
    return render(request, 'hr/attendance/form.html', context)


@login_required
def attendance_delete(request, pk):
    """Delete attendance record with HTMX support"""
    attendance = get_object_or_404(Attendance, pk=pk)
    
    if request.method == 'POST':
        staff_name = attendance.staff.full_name()
        attendance_date = attendance.date
        
        attendance.delete()
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Attendance record for {staff_name} on {attendance_date} deleted successfully"
            response['HX-Alert-Type'] = 'success'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('hr:attendance_list')
            return response
        else:
            messages.success(
                request,
                f"Attendance record for {staff_name} on {attendance_date} deleted successfully",
                extra_tags='sweetalert'
            )
            return redirect('hr:attendance_list')


# =============================================================================
# PAYROLL ACTIONS
# =============================================================================

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Sum, Avg, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from decimal import Decimal


# =============================================================================
# HELPER FUNCTION
# =============================================================================

def get_filtered_payrolls(request):
    """
    Filter payrolls based on request parameters.

    Returns an optimised QuerySet with select_related and prefetch_related
    to minimise database queries. All new fields (nssf_employer,
    employer_total_cost, currency, etc.) are included automatically since
    they live on the Payroll model itself.
    """
    payrolls = Payroll.objects.select_related(
        'staff',
        'staff__primary_department',
        'fiscal_period',
        'fiscal_period__fiscal_year',
        'payment_method',
    ).prefetch_related(
        'allowances',
        'deductions',
        'bonuses',
    ).order_by('-payment_date', 'staff__first_name')

    # -------------------------------------------------------------------------
    # FILTER PARAMETERS
    # -------------------------------------------------------------------------

    query             = request.GET.get('q', '').strip()
    staff             = request.GET.get('staff', '')
    fiscal_period     = request.GET.get('fiscal_period', '')
    fiscal_year       = request.GET.get('fiscal_year', '')
    pay_frequency     = request.GET.get('pay_frequency', '')
    status            = request.GET.get('status', '')
    payment_method    = request.GET.get('payment_method', '')
    currency          = request.GET.get('currency', '')

    # Date range filters
    payment_date_from = request.GET.get('payment_date_from', '')
    payment_date_to   = request.GET.get('payment_date_to', '')
    pay_period_from   = request.GET.get('pay_period_from', '')
    pay_period_to     = request.GET.get('pay_period_to', '')

    # Quick filter
    quick_filter = request.GET.get('quick_filter', '')

    # Checkbox filters
    only_reversed_checked = request.GET.get('only_reversed') == 'on'
    only_prorated_checked = request.GET.get('only_prorated') == 'on'

    # -------------------------------------------------------------------------
    # TEXT SEARCH
    # -------------------------------------------------------------------------

    if query:
        words = query.strip().split()
        if words:
            combined_q = Q()
            for word in words:
                word_q = (
                    Q(staff__first_name__icontains=word) |
                    Q(staff__last_name__icontains=word) |
                    Q(staff__staff_id__icontains=word) |
                    Q(payment_reference__icontains=word) |
                    Q(pay_period_label__icontains=word)
                )
                combined_q &= word_q
            payrolls = payrolls.filter(combined_q)

    # -------------------------------------------------------------------------
    # DROPDOWN FILTERS
    # -------------------------------------------------------------------------

    if staff:
        payrolls = payrolls.filter(staff_id=staff)
    if fiscal_period:
        payrolls = payrolls.filter(fiscal_period_id=fiscal_period)
    if fiscal_year:
        payrolls = payrolls.filter(fiscal_period__fiscal_year_id=fiscal_year)
    if pay_frequency:
        payrolls = payrolls.filter(pay_frequency=pay_frequency)
    if status:
        payrolls = payrolls.filter(status=status)
    if payment_method:
        payrolls = payrolls.filter(payment_method_id=payment_method)
    if currency:
        payrolls = payrolls.filter(currency=currency.upper())

    # -------------------------------------------------------------------------
    # QUICK FILTERS
    # -------------------------------------------------------------------------

    if quick_filter:
        from datetime import date
        from calendar import monthrange

        today = date.today()

        if quick_filter == 'current_month':
            first_day = today.replace(day=1)
            last_day = today.replace(day=monthrange(today.year, today.month)[1])
            payrolls = payrolls.filter(
                pay_period_start__gte=first_day,
                pay_period_end__lte=last_day,
            )

        elif quick_filter == 'last_month':
            from datetime import timedelta
            first_of_current  = today.replace(day=1)
            last_of_previous  = first_of_current - timedelta(days=1)
            first_of_previous = last_of_previous.replace(day=1)
            payrolls = payrolls.filter(
                pay_period_start__gte=first_of_previous,
                pay_period_end__lte=last_of_previous,
            )

        elif quick_filter == 'current_quarter':
            quarter     = (today.month - 1) // 3 + 1
            first_month = (quarter - 1) * 3 + 1
            first_day   = today.replace(month=first_month, day=1)
            last_month  = first_month + 2
            last_year   = today.year
            if last_month > 12:
                last_month -= 12
                last_year  += 1
            last_day = date(last_year, last_month, monthrange(last_year, last_month)[1])
            payrolls = payrolls.filter(
                pay_period_start__gte=first_day,
                pay_period_end__lte=last_day,
            )

        elif quick_filter == 'last_quarter':
            current_quarter = (today.month - 1) // 3 + 1
            if current_quarter == 1:
                first_month = 10
                year = today.year - 1
            else:
                first_month = ((current_quarter - 2) * 3) + 1
                year = today.year
            first_day  = date(year, first_month, 1)
            last_month = first_month + 2
            last_day   = date(year, last_month, monthrange(year, last_month)[1])
            payrolls = payrolls.filter(
                pay_period_start__gte=first_day,
                pay_period_end__lte=last_day,
            )

        elif quick_filter == 'current_year':
            payrolls = payrolls.filter(
                pay_period_start__gte=today.replace(month=1, day=1),
                pay_period_end__lte=today.replace(month=12, day=31),
            )

        elif quick_filter == 'last_year':
            last_year = today.year - 1
            payrolls = payrolls.filter(
                pay_period_start__gte=date(last_year, 1, 1),
                pay_period_end__lte=date(last_year, 12, 31),
            )

    # -------------------------------------------------------------------------
    # CHECKBOX FILTERS
    # -------------------------------------------------------------------------

    if only_reversed_checked:
        payrolls = payrolls.filter(reversed=True)

    if only_prorated_checked:
        payrolls = payrolls.filter(is_prorated=True)

    # -------------------------------------------------------------------------
    # DATE RANGE FILTERS
    # -------------------------------------------------------------------------

    if payment_date_from:
        payrolls = payrolls.filter(payment_date__gte=payment_date_from)
    if payment_date_to:
        payrolls = payrolls.filter(payment_date__lte=payment_date_to)

    # Overlapping pay-period filter
    if pay_period_from:
        payrolls = payrolls.filter(pay_period_end__gte=pay_period_from)
    if pay_period_to:
        payrolls = payrolls.filter(pay_period_start__lte=pay_period_to)

    return payrolls

@login_required
def payroll_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests - UPDATED"""
    filter_form = PayrollFilterForm(request.GET or None)
    
    # Use updated helper function
    payrolls = get_filtered_payrolls(request)
    
    # Calculate statistics - UPDATED to exclude reversed by default
    total = payrolls.count()
    active_payrolls = payrolls.filter(reversed=False)  # ⭐ NEW
    
    stats = {
        'total': total,
        'active': active_payrolls.count(),  # ⭐ NEW
        'reversed': payrolls.filter(reversed=True).count(),  # ⭐ NEW
        'draft': active_payrolls.filter(status='DRAFT').count(),
        'approved': active_payrolls.filter(status='APPROVED').count(),
        'processing': active_payrolls.filter(status='PROCESSING').count(),  # ⭐ NEW
        'paid': active_payrolls.filter(status='PAID').count(),
        'cancelled': active_payrolls.filter(status='CANCELLED').count(),  # ⭐ NEW
        
        # Financial stats (active only)
        'total_gross_pay': active_payrolls.filter(status='PAID').aggregate(
            Sum('gross_pay'))['gross_pay__sum'] or 0,
        'total_net_pay': active_payrolls.filter(status='PAID').aggregate(
            Sum('net_pay'))['net_pay__sum'] or 0,
        'total_deductions': active_payrolls.filter(status='PAID').aggregate(
            Sum('total_deductions'))['total_deductions__sum'] or 0,
        'avg_net_pay': active_payrolls.filter(status='PAID').aggregate(
            Avg('net_pay'))['net_pay__avg'] or 0,
        
        # ⭐ NEW: Proration stats
        'prorated_count': active_payrolls.filter(is_prorated=True).count(),
        
        # ⭐ NEW: Pay frequency breakdown
        'monthly_count': active_payrolls.filter(pay_frequency='MONTHLY').count(),
        'weekly_count': active_payrolls.filter(pay_frequency='WEEKLY').count(),
    }
    
    # Pagination
    paginator = Paginator(payrolls, 20)
    page_number = request.GET.get('page', 1)
    payrolls_page = paginator.get_page(page_number)
    
    # Detect HTMX request
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'payrolls_page': payrolls_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    # Return appropriate template
    if is_htmx:
        return render(request, 'hr/payroll/partials/_payroll_results.html', context)
    else:
        return render(request, 'hr/payroll/list.html', context)

@login_required
@transaction.atomic
def payroll_create(request):
    """
    Create a payroll record together with its allowances, deductions,
    and bonuses in a single page submission.

    ⭐ SIMPLIFIED WORKFLOW (Signals Handle Recalculation):
        1. Save the Payroll header (commit=False first to get a PK)
        2. Save all three formsets (they FK back to the payroll)
        3. Signals automatically recalculate all summary fields
        4. Refresh from DB to get latest calculated values
        
    No manual recalculate_all() needed - signals handle everything!
    """
    if request.method == 'POST':
        form               = PayrollForm(request.POST)
        allowance_formset  = PayrollAllowanceFormSet(request.POST, prefix='allowances')
        deduction_formset  = PayrollDeductionFormSet(request.POST, prefix='deductions')
        bonus_formset      = PayrollBonusFormSet(request.POST, prefix='bonuses')

        all_valid = (
            form.is_valid() and
            allowance_formset.is_valid() and
            deduction_formset.is_valid() and
            bonus_formset.is_valid()
        )

        if all_valid:
            # ================================================================
            # STEP 1: Save payroll header to get PK
            # ================================================================
            payroll = form.save(commit=False)
            payroll.save()
            # ⭐ Payroll number auto-generated by signal if not set

            # ================================================================
            # STEP 2: Save formsets - signals will auto-recalculate
            # ================================================================
            allowance_formset.instance = payroll
            deduction_formset.instance = payroll
            bonus_formset.instance     = payroll
            
            # Each save() triggers signals that recalculate payroll totals
            allowance_formset.save()  # ⭐ Signal: recalculate_payroll_on_allowance_change
            deduction_formset.save()  # ⭐ Signal: recalculate_payroll_on_deduction_change
            bonus_formset.save()      # ⭐ Signal: recalculate_payroll_on_bonus_change

            # ================================================================
            # STEP 3: Refresh to get latest calculated values from signals
            # ================================================================
            payroll.refresh_from_db()
            
            # ⭐ Optional: Explicit recalculation for extra safety
            # (Signals already did this, but doesn't hurt to ensure consistency)
            # Uncomment if you want double-checking:
            # payroll.recalculate_all()
            # payroll.save(update_fields=[
            #     'total_allowances', 'total_bonuses', 'gross_pay',
            #     'taxable_income', 'paye_amount', 'nssf_employee', 'local_service_tax',
            #     'total_statutory_deductions', 'total_voluntary_deductions',
            #     'total_deductions', 'net_pay', 'employer_total_cost', 'updated_at',
            # ])

            messages.success(
                request,
                f"Payroll created for {payroll.staff.full_name()} "
                f"({payroll.pay_period_label}) - "
                f"Gross: {payroll.gross_pay:,.0f}, Net: {payroll.net_pay:,.0f}",
                extra_tags='sweetalert',
            )
            return redirect('hr:payroll_detail', pk=payroll.pk)

        else:
            messages.error(
                request,
                "Please correct the errors below.",
                extra_tags='sweetalert-error',
            )

    else:
        form              = PayrollForm()
        allowance_formset = PayrollAllowanceFormSet(prefix='allowances')
        deduction_formset = PayrollDeductionFormSet(prefix='deductions')
        bonus_formset     = PayrollBonusFormSet(prefix='bonuses')

    context = {
        'form':               form,
        'allowance_formset':  allowance_formset,
        'deduction_formset':  deduction_formset,
        'bonus_formset':      bonus_formset,
        'title':              'Create Payroll',
        'is_create':          True,
    }
    return render(request, 'hr/payroll/form.html', context)


@login_required
@transaction.atomic
def payroll_edit(request, pk):
    """
    Edit a payroll record and its allowances, deductions, and bonuses.

    ⭐ SIMPLIFIED WORKFLOW (Signals Handle Recalculation):
        1. Validate payroll is editable (not reversed, not in closed period)
        2. Save payroll header and formsets
        3. Signals automatically recalculate all summary fields
        4. Refresh from DB to get latest calculated values

    Guards:
    - Reversed payrolls: redirect immediately (form disables fields, but we
      also block at the view level)
    - Closed fiscal period: redirect immediately
    - Paid payrolls: allowed through (PayrollForm disables most fields;
      only notes/payment_reference remain editable)

    After saving, signals recalculate_all() automatically so summary fields stay
    consistent with any line-item changes.
    """
    payroll = get_object_or_404(Payroll, pk=pk)

    # =========================================================================
    # GUARD 1: REVERSED PAYROLLS
    # =========================================================================
    if payroll.reversed:
        messages.error(
            request,
            f"Cannot edit reversed payroll for {payroll.staff.full_name()} "
            f"({payroll.pay_period_label}). "
            f"Reversal reason: {payroll.reversal_reason}",
            extra_tags='sweetalert-error',
        )
        return redirect('hr:payroll_detail', pk=payroll.pk)

    # =========================================================================
    # GUARD 2: CLOSED FISCAL PERIOD
    # =========================================================================
    if payroll.fiscal_period and getattr(payroll.fiscal_period, 'is_closed', False):
        messages.error(
            request,
            f"Cannot edit payroll from closed fiscal period "
            f"({payroll.fiscal_period.name}). "
            "Please contact the finance department if changes are needed.",
            extra_tags='sweetalert-error',
        )
        return redirect('hr:payroll_detail', pk=payroll.pk)

    # =========================================================================
    # GUARD 3: PAID PAYROLLS (Warning, not blocking)
    # =========================================================================
    if payroll.status == 'PAID':
        messages.warning(
            request,
            f"Payroll is {payroll.get_status_display()}. "
            "Only notes and payment reference can be updated. "
            "Salary amounts are locked.",
            extra_tags='sweetalert',
        )
    elif payroll.status == 'PROCESSING':
        messages.info(
            request,
            f"Payroll is {payroll.get_status_display()}. "
            "Be cautious when making changes.",
            extra_tags='sweetalert',
        )

    # =========================================================================
    # FORM PROCESSING
    # =========================================================================
    if request.method == 'POST':
        form              = PayrollForm(request.POST, instance=payroll)
        allowance_formset = PayrollAllowanceFormSet(
            request.POST, instance=payroll, prefix='allowances'
        )
        deduction_formset = PayrollDeductionFormSet(
            request.POST, instance=payroll, prefix='deductions'
        )
        bonus_formset     = PayrollBonusFormSet(
            request.POST, instance=payroll, prefix='bonuses'
        )

        all_valid = (
            form.is_valid() and
            allowance_formset.is_valid() and
            deduction_formset.is_valid() and
            bonus_formset.is_valid()
        )

        if all_valid:
            # =================================================================
            # STEP 1: Save payroll header
            # =================================================================
            payroll = form.save(commit=False)
            payroll.save()
            # ⭐ If basic_salary changed, signal recalculates automatically

            # =================================================================
            # STEP 2: Save formsets - signals auto-recalculate
            # =================================================================
            allowance_formset.save()  # ⭐ Signal: recalculate_payroll_on_allowance_change
            deduction_formset.save()  # ⭐ Signal: recalculate_payroll_on_deduction_change
            bonus_formset.save()      # ⭐ Signal: recalculate_payroll_on_bonus_change

            # =================================================================
            # STEP 3: Refresh to get latest calculated values from signals
            # =================================================================
            payroll.refresh_from_db()
            
            # ⭐ Optional: Explicit recalculation for extra safety
            # (Signals already did this, but doesn't hurt for critical data)
            # Uncomment if you want double-checking:
            # payroll.recalculate_all()
            # payroll.save(update_fields=[
            #     'total_allowances', 'total_bonuses', 'gross_pay',
            #     'taxable_income', 'paye_amount', 'nssf_employee', 'local_service_tax',
            #     'total_statutory_deductions', 'total_voluntary_deductions',
            #     'total_deductions', 'net_pay', 'employer_total_cost', 'updated_at',
            # ])

            messages.success(
                request,
                f"Payroll updated for {payroll.staff.full_name()} "
                f"({payroll.pay_period_label}) - "
                f"Gross: {payroll.gross_pay:,.0f}, Net: {payroll.net_pay:,.0f}",
                extra_tags='sweetalert',
            )
            return redirect('hr:payroll_detail', pk=payroll.pk)

        else:
            messages.error(
                request,
                "Please correct the errors below.",
                extra_tags='sweetalert-error',
            )

    else:
        form              = PayrollForm(instance=payroll)
        allowance_formset = PayrollAllowanceFormSet(instance=payroll, prefix='allowances')
        deduction_formset = PayrollDeductionFormSet(instance=payroll, prefix='deductions')
        bonus_formset     = PayrollBonusFormSet(instance=payroll, prefix='bonuses')

    context = {
        'form':               form,
        'allowance_formset':  allowance_formset,
        'deduction_formset':  deduction_formset,
        'bonus_formset':      bonus_formset,
        'payroll':            payroll,
        'title':              f'Edit Payroll — {payroll.pay_period_label}',
        'is_create':          False,
        'is_editable':        payroll.status in ('DRAFT', 'APPROVED'),
        'is_paid':            payroll.status == 'PAID',
        'is_reversed':        payroll.reversed,
    }
    return render(request, 'hr/payroll/form.html', context)

@login_required
def payroll_detail(request, pk):
    """
    Display payroll details.

    Uses denormalised summary fields from the model directly — no manual
    aggregation needed. The prefetch_related for allowances/deductions/bonuses
    is kept so the template can still iterate individual line items.
    """
    payroll = get_object_or_404(
        Payroll.objects.select_related(
            'staff__primary_department',
            'fiscal_period',
            'payment_method',
            'journal_entry',
            'payment_journal_entry',
            'reversal_journal_entry',
        ).prefetch_related('allowances', 'deductions', 'bonuses'),
        pk=pk,
    )

    can_reverse, reversal_message = payroll.can_be_reversed()

    context = {
        'payroll': payroll,

        # Summary fields — read directly from denormalised model fields
        'total_allowances':           payroll.total_allowances,
        'total_bonuses':              payroll.total_bonuses,
        'gross_pay':                  payroll.gross_pay,
        'taxable_income':             payroll.taxable_income,
        'paye_amount':                payroll.paye_amount,
        'nssf_employee':              payroll.nssf_employee,
        'local_service_tax':          payroll.local_service_tax,
        'total_statutory_deductions': payroll.total_statutory_deductions,
        'total_voluntary_deductions': payroll.total_voluntary_deductions,
        'total_deductions':           payroll.total_deductions,
        'net_pay':                    payroll.net_pay,
        'nssf_employer':              payroll.nssf_employer,
        'employer_total_cost':        payroll.employer_total_cost,

        # Effective amounts (0 if reversed / cancelled)
        'effective_net_pay':   payroll.effective_net_pay,
        'effective_gross_pay': payroll.effective_gross_pay,
        'effective_employer_cost': payroll.effective_employer_cost,

        # Reversal info
        'can_reverse':          can_reverse,
        'reversal_message':     reversal_message,
        'requires_statutory':   payroll.requires_statutory_adjustments(),

        # Audit trail users
        'approved_by':          payroll.get_approved_by_user(),
        'paid_by':              payroll.get_paid_by_user(),
        'reversed_by':          payroll.get_reversed_by_user(),
        'reversal_approved_by': payroll.get_reversal_approved_by_user(),
    }
    return render(request, 'hr/payroll/detail.html', context)

@login_required
def payroll_approve(request, pk):
    """Approve a DRAFT payroll"""
    payroll = get_object_or_404(Payroll, pk=pk)

    if request.method == 'POST':
        if payroll.reversed:
            messages.error(
                request,
                "Cannot approve a reversed payroll.",
                extra_tags='sweetalert-error',
            )
        elif payroll.status == 'DRAFT':
            payroll.status      = 'APPROVED'
            payroll.approved_at = timezone.now()
            payroll.approved_by_id = str(request.user.id)
            payroll.save(update_fields=['status', 'approved_at', 'approved_by_id', 'updated_at'])

            messages.success(
                request,
                f"Payroll for {payroll.staff.full_name()} "
                f"({payroll.pay_period_label}) approved.",
                extra_tags='sweetalert',
            )
        else:
            messages.warning(
                request,
                f"Payroll is already {payroll.get_status_display()}.",
                extra_tags='sweetalert',
            )

    return redirect('hr:payroll_detail', pk=payroll.pk)

@login_required
def payroll_process_payment(request, pk):
    """Mark an APPROVED payroll as PAID"""
    payroll = get_object_or_404(Payroll, pk=pk)

    if request.method == 'POST':
        if payroll.reversed:
            messages.error(
                request,
                "Cannot process payment for a reversed payroll.",
                extra_tags='sweetalert-error',
            )
        elif payroll.status == 'APPROVED':
            payroll.status    = 'PAID'
            payroll.paid_at   = timezone.now()
            payroll.paid_by_id = str(request.user.id)
            payroll.save(update_fields=['status', 'paid_at', 'paid_by_id', 'updated_at'])

            messages.success(
                request,
                f"Payment processed for {payroll.staff.full_name()} "
                f"({payroll.pay_period_label}).",
                extra_tags='sweetalert',
            )
        else:
            messages.warning(
                request,
                f"Payroll must be approved before payment. "
                f"Current status: {payroll.get_status_display()}.",
                extra_tags='sweetalert',
            )

    return redirect('hr:payroll_detail', pk=payroll.pk)


# ⭐ NEW: Payroll reversal view
@login_required
def payroll_reverse(request, pk):
    """Reverse a payroll with HTMX support"""
    from .forms import PayrollReversalForm
    
    payroll = get_object_or_404(Payroll, pk=pk)
    
    # Check if can be reversed
    can_reverse, reason = payroll.can_be_reversed()
    
    if not can_reverse:
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Cannot reverse payroll: {reason}"
            response['HX-Alert-Type'] = 'error'
            response['HX-Close-Modal'] = 'true'
            return response
        else:
            messages.error(
                request,
                f"Cannot reverse payroll: {reason}",
                extra_tags='sweetalert-error'
            )
            return redirect('hr:payroll_detail', pk=pk)
    
    if request.method == 'POST':
        form = PayrollReversalForm(payroll, request.user, request.POST)
        
        if form.is_valid():
            # Perform reversal
            payroll.reversed = True
            payroll.reversed_on = timezone.now()
            payroll.reversed_by_id = str(request.user.id)
            payroll.reversal_reason = form.cleaned_data['reversal_reason']
            payroll.status = 'REVERSED'
            
            # Handle statutory adjustments if required
            if 'statutory_adjustments_notes' in form.cleaned_data:
                payroll.statutory_adjustments_notes = form.cleaned_data['statutory_adjustments_notes']
            
            # If paid payroll, need approval
            if payroll.status == 'PAID':
                payroll.reversal_approved_by_id = str(request.user.id)
                payroll.reversal_approved_on = timezone.now()
            
            payroll.save()
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f"Payroll for {payroll.staff.full_name()} ({payroll.pay_period_label}) has been reversed"
                response['HX-Alert-Type'] = 'warning'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('hr:payroll_detail', kwargs={'pk': pk})
                return response
            else:
                messages.warning(
                    request,
                    f"Payroll for {payroll.staff.full_name()} ({payroll.pay_period_label}) has been reversed",
                    extra_tags='sweetalert'
                )
                return redirect('hr:payroll_detail', pk=pk)
        else:
            messages.error(
                request,
                "Please correct the errors in the form",
                extra_tags='sweetalert-error'
            )
    else:
        form = PayrollReversalForm(payroll, request.user)
    
    context = {
        'form': form,
        'payroll': payroll,
        'can_reverse': can_reverse,
        'title': f'Reverse Payroll for {payroll.staff.full_name()}',
    }
    
    return render(request, 'hr/payroll/reverse_form.html', context)


@login_required
def payroll_delete(request, pk):
    """Delete payroll record with HTMX support - UPDATED"""
    payroll = get_object_or_404(Payroll, pk=pk)
    
    if request.method == 'POST':
        # Can only delete draft or cancelled payrolls
        if payroll.status not in ['DRAFT', 'CANCELLED']:  # ⭐ UPDATED
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f"Cannot delete payroll with status: {payroll.get_status_display()}. Only DRAFT or CANCELLED payrolls can be deleted."
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(
                    request,
                    f"Cannot delete payroll with status: {payroll.get_status_display()}. Only DRAFT or CANCELLED payrolls can be deleted.",
                    extra_tags='sweetalert-error'
                )
                return redirect('hr:payroll_list')
        
        # ⭐ NEW: Don't allow deleting reversed payrolls (keep for audit)
        if payroll.reversed:
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = "Cannot delete reversed payrolls. They must be kept for audit trail."
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(
                    request,
                    "Cannot delete reversed payrolls. They must be kept for audit trail.",
                    extra_tags='sweetalert-error'
                )
                return redirect('hr:payroll_list')
        
        staff_name = payroll.staff.full_name()
        pay_period_label = payroll.pay_period_label  # ⭐ NEW
        payroll.delete()
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Payroll for {staff_name} ({pay_period_label}) deleted successfully"  # ⭐ UPDATED
            response['HX-Alert-Type'] = 'success'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('hr:payroll_list')
            return response
        else:
            messages.success(
                request,
                f"Payroll for {staff_name} ({pay_period_label}) deleted successfully",  # ⭐ UPDATED
                extra_tags='sweetalert'
            )
            return redirect('hr:payroll_list')


# =============================================================================
# BULK OPERATIONS - UPDATED
# =============================================================================
            
@login_required
@transaction.atomic
def payroll_bulk_create(request):
    """
    ⭐ ADVANCED: Bulk create payrolls for multiple staff members.
    
    When creating many payrolls at once, you can disable signals
    for performance and then recalculate at the end.
    """
    from .signals import disable_payroll_calculation_signals
    from .models import Staff
    from core.models import FiscalPeriod
    from datetime import date
    
    if request.method == 'POST':
        # Get form data
        fiscal_period_id = request.POST.get('fiscal_period')
        staff_ids = request.POST.getlist('staff_ids')
        pay_period_start = request.POST.get('pay_period_start')
        pay_period_end = request.POST.get('pay_period_end')
        payment_date = request.POST.get('payment_date')
        
        fiscal_period = get_object_or_404(FiscalPeriod, pk=fiscal_period_id)
        staff_members = Staff.objects.filter(pk__in=staff_ids, is_active=True)
        
        if not staff_members.exists():
            messages.error(
                request,
                "No valid staff members selected.",
                extra_tags='sweetalert-error',
            )
            return redirect('hr:payroll_bulk_create')
        
        created_count = 0
        errors = []
        
        # ⭐ Disable signals for bulk operation (performance optimization)
        with disable_payroll_calculation_signals():
            for staff in staff_members:
                try:
                    # Get active contract
                    contract = staff.get_active_contract()
                    if not contract:
                        errors.append(f"{staff.full_name()} has no active contract")
                        continue
                    
                    # Create payroll
                    payroll = Payroll.objects.create(
                        staff=staff,
                        fiscal_period=fiscal_period,
                        pay_period_start=pay_period_start,
                        pay_period_end=pay_period_end,
                        payment_date=payment_date,
                        pay_frequency='MONTHLY',
                        basic_salary=contract.basic_salary,
                        currency='UGX',
                        exchange_rate=1.000000,
                        payment_method=staff.preferred_payment_method or fiscal_period.default_payment_method,
                        status='DRAFT',
                    )
                    
                    # ⭐ Manually recalculate (signals are disabled)
                    payroll.recalculate_all()
                    payroll.save()
                    
                    created_count += 1
                    
                except Exception as e:
                    errors.append(f"{staff.full_name()}: {str(e)}")
        
        # Show results
        if created_count > 0:
            messages.success(
                request,
                f"Successfully created {created_count} payroll(s).",
                extra_tags='sweetalert',
            )
        
        if errors:
            messages.warning(
                request,
                f"Errors: {'; '.join(errors[:5])}{'...' if len(errors) > 5 else ''}",
                extra_tags='sweetalert',
            )
        
        return redirect('hr:payroll_list')
    
    # GET request - show form
    from core.models import FiscalPeriod
    from .models import Staff
    
    context = {
        'title': 'Bulk Create Payrolls',
        'fiscal_periods': FiscalPeriod.objects.filter(is_closed=False),
        'staff_members': Staff.objects.filter(is_active=True).order_by('first_name', 'last_name'),
    }
    return render(request, 'hr/payroll/bulk_create.html', context)

@login_required
def payroll_recalculate(request, pk):
    """
    ⭐ MANUAL RECALCULATION ENDPOINT
    
    Force recalculation of a payroll's summary fields.
    Useful for fixing data inconsistencies or after manual DB edits.
    """
    payroll = get_object_or_404(Payroll, pk=pk)
    
    # Check permissions
    if payroll.reversed:
        messages.error(
            request,
            "Cannot recalculate a reversed payroll.",
            extra_tags='sweetalert-error',
        )
        return redirect('hr:payroll_detail', pk=payroll.pk)
    
    if payroll.status == 'PAID':
        messages.warning(
            request,
            "This payroll is already paid. Recalculation may cause inconsistencies.",
            extra_tags='sweetalert',
        )
    
    try:
        # Get values before recalculation
        old_gross = payroll.gross_pay
        old_net = payroll.net_pay
        
        # Recalculate
        payroll.recalculate_all()
        payroll.save(update_fields=[
            'total_allowances', 'total_bonuses', 'gross_pay',
            'taxable_income', 'paye_amount', 'nssf_employee', 'local_service_tax',
            'total_statutory_deductions', 'total_voluntary_deductions',
            'total_deductions', 'net_pay', 'employer_total_cost', 'updated_at',
        ])
        
        # Show what changed
        if old_gross != payroll.gross_pay or old_net != payroll.net_pay:
            messages.success(
                request,
                f"Payroll recalculated. "
                f"Gross: {old_gross:,.0f} → {payroll.gross_pay:,.0f}, "
                f"Net: {old_net:,.0f} → {payroll.net_pay:,.0f}",
                extra_tags='sweetalert',
            )
        else:
            messages.info(
                request,
                "Payroll recalculated. No changes detected.",
                extra_tags='sweetalert',
            )
        
    except Exception as e:
        messages.error(
            request,
            f"Error recalculating payroll: {str(e)}",
            extra_tags='sweetalert-error',
        )
    
    return redirect('hr:payroll_detail', pk=payroll.pk)

# =============================================================================
# SALARY HISTORY VIEWS
# =============================================================================

@login_required
def salary_history_list(request):
    """List all salary changes - HTMX loads data on page load"""
    
    context = {
        'SalaryHistory': SalaryHistory,
    }
    
    return render(request, 'hr/salary_history/list.html', context)


@login_required
def salary_history_create(request):
    """Create new salary history record"""
    from .forms import SalaryHistoryForm
    
    if request.method == 'POST':
        form = SalaryHistoryForm(request.POST)
        if form.is_valid():
            salary_history = form.save()
            
            messages.success(
                request,
                f"Salary change recorded for {salary_history.staff.full_name()}",
                extra_tags='sweetalert'
            )
            return redirect('hr:salary_history_list')
        else:
            messages.error(
                request,
                "Please correct the errors in the form",
                extra_tags='sweetalert-error'
            )
    else:
        form = SalaryHistoryForm()
    
    context = {
        'form': form,
        'title': 'Record Salary Change',
    }
    
    return render(request, 'hr/salary_history/form.html', context)


# =============================================================================
# BULK OPERATIONS
# =============================================================================

@login_required
@transaction.atomic
def bulk_staff_action(request):
    """Process bulk action for staff with HTMX support"""
    
    if request.method == 'POST':
        action = request.POST.get('action')
        selected_ids = request.POST.get('selected_ids', '').split(',')
        
        if not action or not selected_ids:
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = "No action or IDs provided"
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, "No action or IDs provided", extra_tags='sweetalert-error')
                return redirect('hr:staff_list')
        
        try:
            staff_members = Staff.objects.filter(id__in=selected_ids)
            count = staff_members.count()
            
            if action == 'activate':
                staff_members.update(is_active=True)
                message = f'{count} staff member(s) activated successfully'
                
            elif action == 'deactivate':
                # Don't deactivate staff with active contracts
                active_contracts = staff_members.filter(contracts__status='ACTIVE').distinct()
                if active_contracts.exists():
                    is_htmx = request.headers.get('HX-Request') == 'true'
                    
                    if is_htmx:
                        response = HttpResponse()
                        response['HX-Alert-Message'] = f"{active_contracts.count()} staff member(s) have active contracts and cannot be deactivated"
                        response['HX-Alert-Type'] = 'error'
                        response['HX-Close-Modal'] = 'true'
                        return response
                    else:
                        messages.error(
                            request,
                            f"{active_contracts.count()} staff member(s) have active contracts and cannot be deactivated",
                            extra_tags='sweetalert-error'
                        )
                        return redirect('hr:staff_list')
                
                staff_members.update(is_active=False)
                message = f'{count} staff member(s) deactivated successfully'
                
            elif action == 'export':
                # Handle export (would redirect to export view)
                message = f'{count} staff member(s) exported successfully'
                
            else:
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f"Unknown action: {action}"
                    response['HX-Alert-Type'] = 'error'
                    response['HX-Close-Modal'] = 'true'
                    return response
                else:
                    messages.error(request, f"Unknown action: {action}", extra_tags='sweetalert-error')
                    return redirect('hr:staff_list')
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = message
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('hr:staff_list')
                return response
            else:
                messages.success(request, message, extra_tags='sweetalert')
                return redirect('hr:staff_list')
            
        except Exception as e:
            logger.error(f"Error in bulk action: {e}")
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f"Error: {str(e)}"
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f"Error: {str(e)}", extra_tags='sweetalert-error')
                return redirect('hr:staff_list')


@login_required
@transaction.atomic
def bulk_attendance_record(request):
    """Bulk record attendance with HTMX support"""
    
    if request.method == 'POST':
        from core.utils import get_school_today
        
        attendance_date = request.POST.get('date')
        status = request.POST.get('status', 'PRESENT')
        work_mode = request.POST.get('work_mode', 'OFFICE')
        
        if not attendance_date:
            attendance_date = get_school_today()
        else:
            from datetime import datetime
            attendance_date = datetime.strptime(attendance_date, '%Y-%m-%d').date()
        
        try:
            # Get all active staff
            active_staff = Staff.objects.filter(is_active=True)
            
            # Check for existing records
            existing = Attendance.objects.filter(
                staff__in=active_staff,
                date=attendance_date
            )
            
            if existing.exists():
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f"Attendance already recorded for {existing.count()} staff on {attendance_date}"
                    response['HX-Alert-Type'] = 'warning'
                    response['HX-Close-Modal'] = 'true'
                    return response
                else:
                    messages.warning(
                        request,
                        f"Attendance already recorded for {existing.count()} staff on {attendance_date}",
                        extra_tags='sweetalert'
                    )
                    return redirect('hr:attendance_list')
            
            # Create attendance records
            attendance_records = []
            for staff in active_staff:
                attendance_records.append(
                    Attendance(
                        staff=staff,
                        date=attendance_date,
                        status=status,
                        work_mode=work_mode,
                    )
                )
            
            Attendance.objects.bulk_create(attendance_records)
            count = len(attendance_records)
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f"Attendance recorded for {count} staff members on {attendance_date}"
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('hr:attendance_list')
                return response
            else:
                messages.success(
                    request,
                    f"Attendance recorded for {count} staff members on {attendance_date}",
                    extra_tags='sweetalert'
                )
                return redirect('hr:attendance_list')
            
        except Exception as e:
            logger.error(f"Error in bulk attendance: {e}")
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f"Error: {str(e)}"
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f"Error: {str(e)}", extra_tags='sweetalert-error')
                return redirect('hr:attendance_list')

# =============================================================================
# REPORTS AND ANALYTICS
# =============================================================================

@login_required
def hr_reports(request):
    """HR reports and analytics page"""
    
    try:
        dashboard_stats = hr_stats.get_hr_dashboard_statistics()
    except Exception as e:
        logger.error(f"Error getting HR dashboard statistics: {e}")
        dashboard_stats = {}
    
    context = {
        'dashboard_stats': dashboard_stats,
    }
    
    return render(request, 'hr/reports/index.html', context)


@login_required
def staff_report(request):
    """Detailed staff report"""
    
    # Get filter parameters
    department = request.GET.get('department')
    employment_status = request.GET.get('employment_status')
    gender = request.GET.get('gender')
    
    # Build filters dict
    filters = {}
    if department:
        filters['department'] = department
    if employment_status:
        filters['employment_status'] = employment_status
    if gender:
        filters['gender'] = gender
    
    try:
        staff_stats = hr_stats.get_staff_statistics(filters)
    except Exception as e:
        logger.error(f"Error getting staff statistics: {e}")
        staff_stats = {}
    
    context = {
        'stats': staff_stats,
        'filters': filters,
    }
    
    return render(request, 'hr/reports/staff_report.html', context)


@login_required
def contract_report(request):
    """Detailed contract report"""
    
    # Get filter parameters
    status = request.GET.get('status')
    contract_type = request.GET.get('contract_type')
    expiring_within_days = request.GET.get('expiring_within_days')
    
    # Build filters dict
    filters = {}
    if status:
        filters['status'] = status
    if contract_type:
        filters['contract_type'] = contract_type
    if expiring_within_days:
        try:
            filters['expiring_within_days'] = int(expiring_within_days)
        except ValueError:
            pass
    
    try:
        contract_stats = hr_stats.get_contract_statistics(filters)
    except Exception as e:
        logger.error(f"Error getting contract statistics: {e}")
        contract_stats = {}
    
    context = {
        'stats': contract_stats,
        'filters': filters,
    }
    
    return render(request, 'hr/reports/contract_report.html', context)


@login_required
def teacher_report(request):
    """Detailed teacher report"""
    
    # Get filter parameters
    is_class_teacher = request.GET.get('is_class_teacher')
    can_teach_online = request.GET.get('can_teach_online')
    digital_literacy_level = request.GET.get('digital_literacy_level')
    
    # Build filters dict
    filters = {}
    if is_class_teacher:
        filters['is_class_teacher'] = is_class_teacher.lower() == 'true'
    if can_teach_online:
        filters['can_teach_online'] = can_teach_online.lower() == 'true'
    if digital_literacy_level:
        filters['digital_literacy_level'] = digital_literacy_level
    
    try:
        teacher_stats = hr_stats.get_teacher_statistics(filters)
    except Exception as e:
        logger.error(f"Error getting teacher statistics: {e}")
        teacher_stats = {}
    
    context = {
        'stats': teacher_stats,
        'filters': filters,
    }
    
    return render(request, 'hr/reports/teacher_report.html', context)