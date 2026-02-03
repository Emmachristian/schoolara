# hr/htmx_views.py

from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.db.models import Q, Count, Sum, Avg, F, DecimalField, Case, When
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from datetime import timedelta, date
from decimal import Decimal
from django.db.models import Prefetch
import logging

from .models import (
    Department,
    Designation,
    Contract,
    Staff,
    StaffDesignation,
    Teacher,
    SalaryHistory,
    ContractBenefit,
    Attendance,
    Payroll,
)
from utils.utils import parse_filters, paginate_queryset

logger = logging.getLogger(__name__)


# =============================================================================
# DEPARTMENT SEARCH
# =============================================================================

def department_search(request):
    """HTMX-compatible department search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'department_type', 'is_academic', 'is_active',
        'academic_subtype', 'parent_department'
    ])
    
    query = filters['q']
    department_type = filters['department_type']
    is_academic = filters['is_academic']
    is_active = filters['is_active']
    academic_subtype = filters['academic_subtype']
    parent_department = filters['parent_department']
    
    # Build queryset
    departments = Department.objects.select_related(
        'parent_department'
    ).annotate(
        staff_count=Count('primary_staff', filter=Q(primary_staff__is_active=True), distinct=True),
        designation_count=Count('designations', filter=Q(designations__is_active=True), distinct=True),
        sub_department_count=Count('sub_departments', distinct=True)
    ).order_by('department_type', 'name')
    
    # Apply text search with multi-word support
    if query:
        # Split query into words and search for each word across fields
        words = query.strip().split()
        
        if words:
            # Build combined query: each word must match at least one field
            combined_q = Q()
            
            for word in words:
                word_q = (
                    Q(name__icontains=word) |
                    Q(code__icontains=word) |
                    Q(description__icontains=word)
                )
                combined_q &= word_q  # AND logic between words
            
            departments = departments.filter(combined_q)
    
    # Apply filters
    if department_type:
        departments = departments.filter(department_type=department_type)
    
    if academic_subtype:
        departments = departments.filter(academic_subtype=academic_subtype)
    
    if is_academic is not None:
        departments = departments.filter(is_academic=(is_academic.lower() == 'true'))
    
    if is_active is not None:
        departments = departments.filter(is_active=(is_active.lower() == 'true'))
    
    if parent_department == 'null':
        departments = departments.filter(parent_department__isnull=True)
    elif parent_department == 'has_parent':
        departments = departments.filter(parent_department__isnull=False)
    elif parent_department:
        departments = departments.filter(parent_department_id=parent_department)
    
    # Paginate
    departments_page, paginator = paginate_queryset(request, departments, per_page=10)
    
    # Calculate stats
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
    
    return render(request, 'hr/departments/_department_results.html', {
        'departments_page': departments_page,
        'stats': stats,
    })


# =============================================================================
# DESIGNATION SEARCH
# =============================================================================

def designation_search(request):
    """HTMX-compatible designation search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'department', 'is_teaching', 'is_management',
        'is_active', 'min_salary', 'max_salary'
    ])
    
    query = filters['q']
    department = filters['department']
    is_teaching = filters['is_teaching']
    is_management = filters['is_management']
    is_active = filters['is_active']
    min_salary = filters['min_salary']
    max_salary = filters['max_salary']
    
    # Build queryset
    designations = Designation.objects.select_related(
        'department',
        'reports_to'
    ).annotate(
        staff_count=Count('staffdesignation', filter=Q(staffdesignation__is_active=True), distinct=True),
        subordinate_count=Count('subordinate_designations', distinct=True)
    ).order_by('rank_order', 'name')
    
    # Apply text search with multi-word support
    if query:
        # Split query into words and search for each word across fields
        words = query.strip().split()
        
        if words:
            # Build combined query: each word must match at least one field
            combined_q = Q()
            
            for word in words:
                word_q = (
                    Q(name__icontains=word) |
                    Q(code__icontains=word) |
                    Q(description__icontains=word)
                )
                combined_q &= word_q  # AND logic between words
            
            designations = designations.filter(combined_q)
    
    # Apply filters
    if department:
        designations = designations.filter(department_id=department)
    
    if is_teaching is not None:
        designations = designations.filter(is_teaching=(is_teaching.lower() == 'true'))
    
    if is_management is not None:
        designations = designations.filter(is_management=(is_management.lower() == 'true'))
    
    if is_active is not None:
        designations = designations.filter(is_active=(is_active.lower() == 'true'))
    
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
    
    # Paginate
    designations_page, paginator = paginate_queryset(request, designations, per_page=10)
    
    # Calculate stats
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
    
    return render(request, 'hr/designations/_designation_results.html', {
        'designations_page': designations_page,
        'stats': stats,
    })

# =============================================================================
# STAFF DESIGNATION SEARCH
# =============================================================================

def staff_designation_search(request):
    """HTMX-compatible staff designation search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'staff', 'designation', 'department', 'is_primary',
        'assignment_type', 'is_active', 'start_date', 'end_date'
    ])
    
    query = filters['q']
    staff = filters['staff']
    designation = filters['designation']
    department = filters['department']
    is_primary = filters['is_primary']
    assignment_type = filters['assignment_type']
    is_active = filters['is_active']
    start_date = filters['start_date']
    end_date = filters['end_date']
    
    # Build queryset
    staff_designations = StaffDesignation.objects.select_related(
        'staff__primary_department',
        'designation__department'
    ).annotate(
        days_in_role=Case(
            When(end_date__isnull=True, then=F('start_date')),
            default=F('end_date') - F('start_date'),
            output_field=DecimalField()
        )
    ).order_by('-is_primary', '-is_active', '-start_date', 'staff__first_name')
    
    # Apply text search with multi-word support
    if query:
        # Split query into words and search for each word across fields
        words = query.strip().split()
        
        if words:
            # Build combined query: each word must match at least one field
            combined_q = Q()
            
            for word in words:
                word_q = (
                    Q(staff__first_name__icontains=word) |
                    Q(staff__last_name__icontains=word) |
                    Q(staff__staff_id__icontains=word) |
                    Q(designation__name__icontains=word) |
                    Q(designation__code__icontains=word) |
                    Q(notes__icontains=word) |
                    Q(assignment_order_number__icontains=word)
                )
                combined_q &= word_q  # AND logic between words
            
            staff_designations = staff_designations.filter(combined_q)
    
    # Apply filters
    if staff:
        staff_designations = staff_designations.filter(staff_id=staff)
    
    if designation:
        staff_designations = staff_designations.filter(designation_id=designation)
    
    if department:
        staff_designations = staff_designations.filter(designation__department_id=department)
    
    if is_primary is not None:
        staff_designations = staff_designations.filter(is_primary=(is_primary.lower() == 'true'))
    
    if assignment_type:
        staff_designations = staff_designations.filter(assignment_type=assignment_type)
    
    if is_active is not None:
        staff_designations = staff_designations.filter(is_active=(is_active.lower() == 'true'))
    
    if start_date:
        staff_designations = staff_designations.filter(start_date__gte=start_date)
    
    if end_date:
        staff_designations = staff_designations.filter(
            Q(end_date__lte=end_date) | Q(end_date__isnull=True)
        )
    
    # Paginate
    staff_designations_page, paginator = paginate_queryset(request, staff_designations, per_page=20)
    
    # Calculate stats
    total = staff_designations.count()
    
    stats = {
        'total': total,
        'active': staff_designations.filter(is_active=True).count(),
        'primary': staff_designations.filter(is_primary=True, is_active=True).count(),
        'additional': staff_designations.filter(is_primary=False, is_active=True).count(),
        'permanent': staff_designations.filter(assignment_type='PERMANENT').count(),
        'acting': staff_designations.filter(assignment_type='ACTING').count(),
        'temporary': staff_designations.filter(assignment_type='TEMPORARY').count(),
        'secondment': staff_designations.filter(assignment_type='SECONDMENT').count(),
        'total_allowances': staff_designations.filter(
            is_active=True
        ).aggregate(Sum('role_allowance'))['role_allowance__sum'] or 0,
        'avg_allowance': staff_designations.filter(
            is_active=True,
            role_allowance__gt=0
        ).aggregate(Avg('role_allowance'))['role_allowance__avg'] or 0,
    }
    
    return render(request, 'hr/staff_designations/_staff_designation_results.html', {
        'staff_designations_page': staff_designations_page,
        'stats': stats,
    })

# =============================================================================
# CONTRACT SEARCH
# =============================================================================

def contract_search(request):
    """HTMX-compatible contract search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'contract_type', 'status', 'staff', 'start_date',
        'end_date', 'expiring_soon', 'is_permanent', 'salary_frequency'
    ])
    
    query = filters['q']
    contract_type = filters['contract_type']
    status = filters['status']
    staff = filters['staff']
    start_date = filters['start_date']
    end_date = filters['end_date']
    expiring_soon = filters['expiring_soon']
    is_permanent = filters['is_permanent']
    salary_frequency = filters['salary_frequency']
    
    # Build queryset
    contracts = Contract.objects.select_related(
        'staff'
    ).order_by('-start_date', 'staff__first_name')
    
    # Apply text search with multi-word support
    if query:
        # Split query into words and search for each word across fields
        words = query.strip().split()
        
        if words:
            # Build combined query: each word must match at least one field
            combined_q = Q()
            
            for word in words:
                word_q = (
                    Q(contract_number__icontains=word) |
                    Q(staff__first_name__icontains=word) |
                    Q(staff__last_name__icontains=word) |
                    Q(staff__staff_id__icontains=word) |
                    Q(job_title__icontains=word)
                )
                combined_q &= word_q  # AND logic between words
            
            contracts = contracts.filter(combined_q)
    
    # Apply filters
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
    
    # Paginate
    contracts_page, paginator = paginate_queryset(request, contracts, per_page=20)
    
    # Calculate stats
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
    
    return render(request, 'hr/contracts/_contract_results.html', {
        'contracts_page': contracts_page,
        'stats': stats,
    })


# =============================================================================
# STAFF SEARCH
# =============================================================================

def staff_search(request):
    """HTMX-compatible staff search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'employment_status', 'gender', 'primary_department',
        'is_active', 'marital_status', 'nationality'
    ])
    
    query = filters['q']
    employment_status = filters['employment_status']
    gender = filters['gender']
    primary_department = filters['primary_department']
    is_active = filters['is_active']
    marital_status = filters['marital_status']
    nationality = filters['nationality']
    
    # Build queryset with primary designation prefetch
    from django.db.models import Prefetch
    
    staff = Staff.objects.select_related(
        'primary_department'
    ).prefetch_related(
        # ⭐ Prefetch primary designation
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
    ).order_by('first_name', 'last_name')
    
    # Apply text search with multi-word support
    if query:
        # Split query into words and search for each word across fields
        words = query.strip().split()
        
        if words:
            # Build combined query: each word must match at least one field
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
                combined_q &= word_q  # AND logic between words
            
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
    
    if is_active is not None:
        staff = staff.filter(is_active=(is_active.lower() == 'true'))
    
    # Paginate
    staff_page, paginator = paginate_queryset(request, staff, per_page=10)
    
    # Calculate stats
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
    
    return render(request, 'hr/staff/_staff_results.html', {
        'staff_page': staff_page,
        'stats': stats,
    })

# =============================================================================
# TEACHER SEARCH
# =============================================================================

def teacher_search(request):
    """HTMX-compatible teacher search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'department', 'specialization', 'is_class_teacher',
        'digital_literacy_level', 'can_teach_online', 'is_active',
        'max_hours', 'min_hours'  # ⭐ Added these for completeness
    ])
    
    query = filters['q']
    department = filters['department']
    specialization = filters['specialization']
    is_class_teacher = filters['is_class_teacher']
    digital_literacy_level = filters['digital_literacy_level']
    can_teach_online = filters['can_teach_online']
    is_active = filters.get('is_active')  # ⭐ Soft delete filter
    max_hours = filters.get('max_hours')
    min_hours = filters.get('min_hours')
    
    # Build queryset with optimized relations
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
    
    # ⭐ Filter by active status (default to active only)
    if is_active is not None:
        if is_active.lower() == 'true':
            teachers = teachers.filter(is_active=True)
        elif is_active.lower() == 'false':
            teachers = teachers.filter(is_active=False)
        elif is_active.lower() == 'all':
            # Show all teachers (active and inactive)
            pass
    else:
        # Default: show only active teachers
        teachers = teachers.filter(is_active=True)
    
    # Apply text search with multi-word support
    if query:
        # Split query into words and search for each word across fields
        words = query.strip().split()
        
        if words:
            # Build combined query: each word must match at least one field
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
                combined_q &= word_q  # AND logic between words
            
            teachers = teachers.filter(combined_q)
    
    # Apply department filter
    if department:
        teachers = teachers.filter(staff__primary_department_id=department)
    
    # Apply specialization filter (partial match)
    if specialization:
        teachers = teachers.filter(specialization__icontains=specialization)
    
    # Apply boolean filters
    if is_class_teacher is not None:
        teachers = teachers.filter(is_class_teacher=(is_class_teacher.lower() == 'true'))
    
    if can_teach_online is not None:
        teachers = teachers.filter(can_teach_online=(can_teach_online.lower() == 'true'))
    
    # Apply digital literacy level filter
    if digital_literacy_level:
        teachers = teachers.filter(digital_literacy_level=digital_literacy_level)
    
    # Apply teaching hours filters
    if max_hours:
        try:
            teachers = teachers.filter(max_hours_per_week__lte=int(max_hours))
        except (ValueError, TypeError):
            logger.warning(f"Invalid max_hours value: {max_hours}")
    
    if min_hours:
        try:
            teachers = teachers.filter(current_teaching_load__gte=int(min_hours))
        except (ValueError, TypeError):
            logger.warning(f"Invalid min_hours value: {min_hours}")
    
    # Order by active status first, then by name
    teachers = teachers.order_by('-is_active', 'staff__first_name', 'staff__last_name')
    
    # Paginate
    teachers_page, paginator = paginate_queryset(request, teachers, per_page=20)
    
    # Calculate comprehensive stats
    total = teachers.count()
    
    # ⭐ Get all teachers for overall stats (before pagination)
    all_teachers = teachers
    
    stats = {
        # ⭐ Core stats with active/inactive breakdown
        'total': total,
        'active': all_teachers.filter(is_active=True).count(),
        'inactive': all_teachers.filter(is_active=False).count(),
        
        # ⭐ Active staff status (different from teacher active status)
        'active_staff': all_teachers.filter(staff__is_active=True).count(),
        
        # Role-based stats
        'class_teachers': all_teachers.filter(is_class_teacher=True, is_active=True).count(),
        'non_class_teachers': all_teachers.filter(is_class_teacher=False, is_active=True).count(),
        
        # Online teaching capability
        'can_teach_online': all_teachers.filter(can_teach_online=True, is_active=True).count(),
        'cannot_teach_online': all_teachers.filter(can_teach_online=False, is_active=True).count(),
        
        # Digital literacy breakdown
        'basic_literacy': all_teachers.filter(
            digital_literacy_level='BASIC',
            is_active=True
        ).count(),
        'intermediate_literacy': all_teachers.filter(
            digital_literacy_level='INTERMEDIATE',
            is_active=True
        ).count(),
        'advanced_literacy': all_teachers.filter(
            digital_literacy_level='ADVANCED',
            is_active=True
        ).count(),
        'expert_literacy': all_teachers.filter(
            digital_literacy_level='EXPERT',
            is_active=True
        ).count(),
        
        # Teaching load statistics (active teachers only)
        'avg_teaching_load': all_teachers.filter(
            is_active=True
        ).aggregate(
            Avg('current_teaching_load')
        )['current_teaching_load__avg'] or 0,
        
        'avg_max_hours': all_teachers.filter(
            is_active=True
        ).aggregate(
            Avg('max_hours_per_week')
        )['max_hours_per_week__avg'] or 0,
        
        # ⭐ Total classes assigned (active teachers only)
        'total_classes': all_teachers.filter(
            is_active=True
        ).aggregate(
            total=Sum('assigned_classes_count')
        )['total'] or 0,
        
        # ⭐ Overloaded teachers (current load > max hours)
        'overloaded': all_teachers.filter(
            is_active=True,
            current_teaching_load__gt=F('max_hours_per_week')
        ).count(),
        
        # ⭐ Underutilized teachers (current load < 50% of max hours)
        'underutilized': all_teachers.filter(
            is_active=True,
            current_teaching_load__lt=F('max_hours_per_week') * 0.5
        ).count(),
        
        # ⭐ Teachers with no teaching designation (inconsistency)
        'no_designation': all_teachers.filter(
            is_active=True,
            staff__staffdesignation__designation__is_teaching=False
        ).distinct().count() if all_teachers.filter(is_active=True).exists() else 0,
    }
    
    # ⭐ Round decimal values for display
    stats['avg_teaching_load'] = round(stats['avg_teaching_load'], 2)
    stats['avg_max_hours'] = round(stats['avg_max_hours'], 2)
    
    return render(request, 'hr/teachers/_teacher_results.html', {
        'teachers_page': teachers_page,
        'stats': stats,
    })

# =============================================================================
# SALARY HISTORY SEARCH
# =============================================================================

def salary_history_search(request):
    """HTMX-compatible salary history search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'staff', 'change_type', 'contract',
        'effective_period', 'start_date', 'end_date'
    ])
    
    query = filters['q']
    staff = filters['staff']
    change_type = filters['change_type']
    contract = filters['contract']
    effective_period = filters['effective_period']
    start_date = filters['start_date']
    end_date = filters['end_date']
    
    # Build queryset
    salary_changes = SalaryHistory.objects.select_related(
        'staff',
        'contract',
        'effective_period'
    ).order_by('-effective_date', 'staff__first_name')
    
    # Apply text search with multi-word support
    if query:
        # Split query into words and search for each word across fields
        words = query.strip().split()
        
        if words:
            # Build combined query: each word must match at least one field
            combined_q = Q()
            
            for word in words:
                word_q = (
                    Q(staff__first_name__icontains=word) |
                    Q(staff__last_name__icontains=word) |
                    Q(staff__staff_id__icontains=word) |
                    Q(reason__icontains=word)
                )
                combined_q &= word_q  # AND logic between words
            
            salary_changes = salary_changes.filter(combined_q)
    
    # Apply filters
    if staff:
        salary_changes = salary_changes.filter(staff_id=staff)
    
    if change_type:
        salary_changes = salary_changes.filter(change_type=change_type)
    
    if contract:
        salary_changes = salary_changes.filter(contract_id=contract)
    
    if effective_period:
        salary_changes = salary_changes.filter(effective_period_id=effective_period)
    
    if start_date:
        salary_changes = salary_changes.filter(effective_date__gte=start_date)
    
    if end_date:
        salary_changes = salary_changes.filter(effective_date__lte=end_date)
    
    # Paginate
    salary_changes_page, paginator = paginate_queryset(request, salary_changes, per_page=20)
    
    # Calculate stats
    total = salary_changes.count()
    
    stats = {
        'total': total,
        'initial': salary_changes.filter(change_type='INITIAL').count(),
        'increment': salary_changes.filter(change_type='INCREMENT').count(),
        'promotion': salary_changes.filter(change_type='PROMOTION').count(),
        'avg_new_salary': salary_changes.aggregate(Avg('new_salary'))['new_salary__avg'] or 0,
        'avg_increase': salary_changes.filter(previous_salary__isnull=False).aggregate(
            avg_increase=Avg(F('new_salary') - F('previous_salary'))
        )['avg_increase'] or 0,
        'total_salary_increase': salary_changes.filter(previous_salary__isnull=False).aggregate(
            total=Sum(F('new_salary') - F('previous_salary'))
        )['total'] or 0,
    }
    
    return render(request, 'hr/salary_history/_history_results.html', {
        'salary_changes_page': salary_changes_page,
        'stats': stats,
    })


# =============================================================================
# ATTENDANCE SEARCH
# =============================================================================

def attendance_search(request):
    """HTMX-compatible attendance search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'staff', 'status', 'work_mode', 'start_date', 'end_date'
    ])
    
    query = filters['q']
    staff = filters['staff']
    status = filters['status']
    work_mode = filters['work_mode']
    start_date = filters['start_date']
    end_date = filters['end_date']
    
    # Build queryset
    attendance_records = Attendance.objects.select_related(
        'staff__primary_department'
    ).order_by('-date', 'staff__first_name')
    
    # Apply text search with multi-word support
    if query:
        # Split query into words and search for each word across fields
        words = query.strip().split()
        
        if words:
            # Build combined query: each word must match at least one field
            combined_q = Q()
            
            for word in words:
                word_q = (
                    Q(staff__first_name__icontains=word) |
                    Q(staff__last_name__icontains=word) |
                    Q(staff__staff_id__icontains=word)
                )
                combined_q &= word_q  # AND logic between words
            
            attendance_records = attendance_records.filter(combined_q)
    
    # Apply filters
    if staff:
        attendance_records = attendance_records.filter(staff_id=staff)
    
    if status:
        attendance_records = attendance_records.filter(status=status)
    
    if work_mode:
        attendance_records = attendance_records.filter(work_mode=work_mode)
    
    if start_date:
        attendance_records = attendance_records.filter(date__gte=start_date)
    
    if end_date:
        attendance_records = attendance_records.filter(date__lte=end_date)
    
    # Paginate
    attendance_page, paginator = paginate_queryset(request, attendance_records, per_page=20)
    
    # Calculate stats
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
    
    return render(request, 'hr/attendance/_attendance_results.html', {
        'attendance_page': attendance_page,
        'stats': stats,
    })


# =============================================================================
# PAYROLL SEARCH
# =============================================================================

def payroll_search(request):
    """HTMX-compatible payroll search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'staff', 'period', 'fiscal_year', 'status',
        'payment_method', 'start_date', 'end_date'
    ])
    
    query = filters['q']
    staff = filters['staff']
    period = filters['period']
    fiscal_year = filters['fiscal_year']
    status = filters['status']
    payment_method = filters['payment_method']
    start_date = filters['start_date']
    end_date = filters['end_date']
    
    # Build queryset
    payrolls = Payroll.objects.select_related(
        'staff__primary_department',
        'period',
        'fiscal_year',
        'payment_method'
    ).prefetch_related(
        'allowances',
        'deductions',
        'bonuses'
    ).annotate(
        allowance_count=Count('allowances', distinct=True),
        deduction_count=Count('deductions', distinct=True),
        bonus_count=Count('bonuses', distinct=True)
    ).order_by('-payment_date', 'staff__first_name')
    
    # Apply text search with multi-word support
    if query:
        # Split query into words and search for each word across fields
        words = query.strip().split()
        
        if words:
            # Build combined query: each word must match at least one field
            combined_q = Q()
            
            for word in words:
                word_q = (
                    Q(staff__first_name__icontains=word) |
                    Q(staff__last_name__icontains=word) |
                    Q(staff__staff_id__icontains=word) |
                    Q(payment_reference__icontains=word)
                )
                combined_q &= word_q  # AND logic between words
            
            payrolls = payrolls.filter(combined_q)
    
    # Apply filters
    if staff:
        payrolls = payrolls.filter(staff_id=staff)
    
    if period:
        payrolls = payrolls.filter(period_id=period)
    
    if fiscal_year:
        payrolls = payrolls.filter(fiscal_year_id=fiscal_year)
    
    if status:
        payrolls = payrolls.filter(status=status)
    
    if payment_method:
        payrolls = payrolls.filter(payment_method_id=payment_method)
    
    if start_date:
        payrolls = payrolls.filter(payment_date__gte=start_date)
    
    if end_date:
        payrolls = payrolls.filter(payment_date__lte=end_date)
    
    # Paginate
    payrolls_page, paginator = paginate_queryset(request, payrolls, per_page=20)
    
    # Calculate stats
    total = payrolls.count()
    
    stats = {
        'total': total,
        'draft': payrolls.filter(status='DRAFT').count(),
        'approved': payrolls.filter(status='APPROVED').count(),
        'paid': payrolls.filter(status='PAID').count(),
        'total_gross_pay': payrolls.filter(status='PAID').aggregate(
            Sum('gross_pay'))['gross_pay__sum'] or 0,
        'total_net_pay': payrolls.filter(status='PAID').aggregate(
            Sum('net_pay'))['net_pay__sum'] or 0,
        'total_deductions': payrolls.filter(status='PAID').aggregate(
            Sum('total_deductions'))['total_deductions__sum'] or 0,
        'avg_net_pay': payrolls.filter(status='PAID').aggregate(
            Avg('net_pay'))['net_pay__avg'] or 0,
    }
    
    return render(request, 'hr/payroll/_payroll_results.html', {
        'payrolls_page': payrolls_page,
        'stats': stats,
    })


# =============================================================================
# CONTRACT BENEFIT SEARCH
# =============================================================================

def contract_benefit_search(request):
    """HTMX-compatible contract benefit search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'contract', 'benefit_type', 'is_active', 'provider'
    ])
    
    query = filters['q']
    contract = filters['contract']
    benefit_type = filters['benefit_type']
    is_active = filters['is_active']
    provider = filters['provider']
    
    # Build queryset
    benefits = ContractBenefit.objects.select_related(
        'contract__staff'
    ).order_by('contract', 'benefit_type')
    
    # Apply text search with multi-word support
    if query:
        # Split query into words and search for each word across fields
        words = query.strip().split()
        
        if words:
            # Build combined query: each word must match at least one field
            combined_q = Q()
            
            for word in words:
                word_q = (
                    Q(description__icontains=word) |
                    Q(provider__icontains=word) |
                    Q(policy_number__icontains=word) |
                    Q(contract__staff__first_name__icontains=word) |
                    Q(contract__staff__last_name__icontains=word)
                )
                combined_q &= word_q  # AND logic between words
            
            benefits = benefits.filter(combined_q)
    
    # Apply filters
    if contract:
        benefits = benefits.filter(contract_id=contract)
    
    if benefit_type:
        benefits = benefits.filter(benefit_type=benefit_type)
    
    if provider:
        benefits = benefits.filter(provider__icontains=provider)
    
    if is_active is not None:
        benefits = benefits.filter(is_active=(is_active.lower() == 'true'))
    
    # Paginate
    benefits_page, paginator = paginate_queryset(request, benefits, per_page=20)
    
    # Calculate stats
    total = benefits.count()
    
    stats = {
        'total': total,
        'active': benefits.filter(is_active=True).count(),
        'health_insurance': benefits.filter(benefit_type='HEALTH_INSURANCE').count(),
        'housing': benefits.filter(benefit_type='HOUSING').count(),
        'transport': benefits.filter(benefit_type='TRANSPORT').count(),
        'total_value': benefits.filter(monetary_value__isnull=False).aggregate(
            Sum('monetary_value'))['monetary_value__sum'] or 0,
        'avg_value': benefits.filter(monetary_value__isnull=False).aggregate(
            Avg('monetary_value'))['monetary_value__avg'] or 0,
    }
    
    return render(request, 'hr/benefits/_benefit_results.html', {
        'benefits_page': benefits_page,
        'stats': stats,
    })


# =============================================================================
# QUICK STATS ENDPOINTS (for dashboard widgets)
# =============================================================================

@require_http_methods(["GET"])
def staff_quick_stats(request):
    """Get quick statistics for staff"""
    
    stats = {
        'total': Staff.objects.filter(is_active=True).count(),
        'full_time': Staff.objects.filter(employment_status='FT', is_active=True).count(),
        'part_time': Staff.objects.filter(employment_status='PT', is_active=True).count(),
        'contract': Staff.objects.filter(employment_status='CT', is_active=True).count(),
        'teachers': Teacher.objects.filter(staff__is_active=True).count(),
        'male': Staff.objects.filter(gender='M', is_active=True).count(),
        'female': Staff.objects.filter(gender='F', is_active=True).count(),
    }
    
    return JsonResponse(stats)


@require_http_methods(["GET"])
def contract_quick_stats(request):
    """Get quick statistics for contracts"""
    
    today = timezone.now().date()
    
    stats = {
        'total': Contract.objects.count(),
        'active': Contract.objects.filter(status='ACTIVE').count(),
        'expiring_soon': Contract.objects.filter(
            status='ACTIVE',
            end_date__lte=today + timedelta(days=30),
            end_date__gte=today
        ).count(),
        'expired': Contract.objects.filter(
            status='ACTIVE',
            end_date__lt=today
        ).count(),
        'permanent': Contract.objects.filter(contract_type='PERMANENT', status='ACTIVE').count(),
        'total_salary_obligation': Contract.objects.filter(status='ACTIVE').aggregate(
            Sum('basic_salary'))['basic_salary__sum'] or 0,
    }
    
    return JsonResponse(stats)


@require_http_methods(["GET"])
def payroll_quick_stats(request):
    """Get quick statistics for payroll"""
    
    current_month = timezone.now().date().replace(day=1)
    
    stats = {
        'total_this_month': Payroll.objects.filter(
            payment_date__gte=current_month
        ).count(),
        'draft': Payroll.objects.filter(status='DRAFT').count(),
        'pending_approval': Payroll.objects.filter(status='APPROVED').count(),
        'paid_this_month': Payroll.objects.filter(
            status='PAID',
            payment_date__gte=current_month
        ).count(),
        'total_payout_this_month': Payroll.objects.filter(
            status='PAID',
            payment_date__gte=current_month
        ).aggregate(Sum('net_pay'))['net_pay__sum'] or 0,
    }
    
    return JsonResponse(stats)


@require_http_methods(["GET"])
def attendance_quick_stats(request):
    """Get quick statistics for attendance"""
    
    today = timezone.now().date()
    
    stats = {
        'today_total': Attendance.objects.filter(date=today).count(),
        'today_present': Attendance.objects.filter(date=today, status='PRESENT').count(),
        'today_absent': Attendance.objects.filter(date=today, status='ABSENT').count(),
        'today_late': Attendance.objects.filter(date=today, status='LATE').count(),
        'today_on_leave': Attendance.objects.filter(date=today, status='LEAVE').count(),
    }
    
    if stats['today_total'] > 0:
        stats['today_attendance_rate'] = round(
            (stats['today_present'] / stats['today_total']) * 100, 1
        )
    else:
        stats['today_attendance_rate'] = 0
    
    return JsonResponse(stats)