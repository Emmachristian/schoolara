# hr/ajax_views.py

from django.http import JsonResponse
from django.db.models import Q, Count
import json
import base64
import os
from django.views.decorators.csrf import csrf_exempt
from django.core.files.base import ContentFile
from django.urls import reverse
import logging

from .models import Staff, Teacher, Contract, Department, Designation, ContractType
from .utils import parse_filters, paginate_queryset
from .stats import (
    get_staff_statistics,
    get_department_statistics,
    get_designation_statistics,
    get_contract_statistics,
    get_teacher_statistics,
    get_contract_type_statistics
)

logger = logging.getLogger(__name__)


# =============================================================================
# STAFF PROFILE PICTURE UPDATE
# =============================================================================

@csrf_exempt
def update_staff_profile_picture(request):
    """
    AJAX endpoint to update staff profile picture via base64 image data
    """
    try:
        # Parse the JSON body
        data = json.loads(request.body)

        staff_id = data.get("staff_id")
        image_data = data.get("image")

        if not staff_id or not image_data:
            return JsonResponse(
                {"success": False, "message": "Invalid data."},
                status=400
            )
        
        # Find the staff by ID (UUID)
        try:
            staff = Staff.objects.get(id=staff_id)
        except Staff.DoesNotExist:
            return JsonResponse(
                {"success": False, "message": "Staff member not found."},
                status=404  
            )
        
        extension = None

        # Handle base64 prefix and determine extension
        if image_data.startswith("data:image/jpeg;base64,"):
            image_data = image_data[len("data:image/jpeg;base64,"):]
            extension = ".jpg"
        elif image_data.startswith("data:image/png;base64,"):
            image_data = image_data[len("data:image/png;base64,"):]
            extension = ".png"
        else:
            return JsonResponse(
                {"success": False, "message": "Unsupported image format. Only JPG and PNG are allowed"},
                status=400  
            )
        
        # Decode base64 string
        try:
            image_data_decoded = base64.b64decode(image_data)
        except Exception:
            return JsonResponse(
                {"success": False, "message": "Invalid image data."},
                status=400  
            )   

        # Generate the file name
        file_name = f"{staff.id}{extension}" 

        # Delete old photo file if exists 
        if staff.photo:
            old_file_path = staff.photo.path
            if os.path.exists(old_file_path):
                try:
                    os.remove(old_file_path)
                except Exception as e:
                    logger.warning(f"Could not delete old file: {e}")

        # Wrap decoded bytes in ContentFile and save to ImageField
        profile_picture = ContentFile(image_data_decoded)
        staff.photo.save(file_name, profile_picture, save=True)

        # Redirect back to staff profile
        redirect_url = reverse("hr:staff_profile", args=[staff.id])

        return JsonResponse(
            {"success": True, "message": "Profile picture updated successfully", "redirect_url": redirect_url}
        )
    
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "message": "Invalid JSON data."},
            status=400 
        )
    
    except Exception as e:
        logger.error(f"Error updating staff profile picture: {e}")
        return JsonResponse(
            {"success": False, "message": f"Server error: {str(e)}"},
            status=500  
        )


# =============================================================================
# STAFF SEARCH
# =============================================================================

def staff_search(request):
    """
    AJAX view to return filtered staff as JSON with statistics
    """
    # Extract filters using parse_filters
    filter_keys = [
        'q', 'gender', 'department', 'employment_status', 
        'is_teaching', 'min_age', 'max_age', 'page'
    ]
    filters = parse_filters(request, filter_keys)

    # Start with all staff
    staff = Staff.objects.all().select_related('primary_department').order_by('-created_at')

    # Apply text search filter
    if filters['q']:
        terms = filters['q'].split()
        q_objects = Q()
        for term in terms:
            q_objects &= (
                Q(first_name__icontains=term) |
                Q(middle_name__icontains=term) |
                Q(last_name__icontains=term) |
                Q(staff_id__icontains=term) |
                Q(personal_email__icontains=term) |
                Q(phone_number__icontains=term) |
                Q(primary_department__name__icontains=term)
            )
        staff = staff.filter(q_objects)

    # Apply filters
    if filters['gender']:
        staff = staff.filter(gender=filters['gender'])
    if filters['department']:
        staff = staff.filter(primary_department_id=filters['department'])
    if filters['employment_status']:
        staff = staff.filter(employment_status=filters['employment_status'])
    
    # Filter for teaching staff
    if filters['is_teaching']:
        if filters['is_teaching'].lower() == 'true':
            teacher_staff_ids = Teacher.objects.values_list('staff_id', flat=True)
            staff = staff.filter(id__in=teacher_staff_ids)
        elif filters['is_teaching'].lower() == 'false':
            teacher_staff_ids = Teacher.objects.values_list('staff_id', flat=True)
            staff = staff.exclude(id__in=teacher_staff_ids)

    # Age filtering
    from datetime import date, timedelta
    today = date.today()
    
    if filters['min_age']:
        try:
            min_age_int = int(filters['min_age'])
            max_birth_date = today - timedelta(days=min_age_int * 365.25)
            staff = staff.filter(date_of_birth__lte=max_birth_date)
        except ValueError:
            pass

    if filters['max_age']:
        try:
            max_age_int = int(filters['max_age'])
            min_birth_date = today - timedelta(days=(max_age_int + 1) * 365.25)
            staff = staff.filter(date_of_birth__gte=min_birth_date)
        except ValueError:
            pass

    # Get comprehensive statistics using statistics module
    stats_filters = {}
    if filters['employment_status']:
        stats_filters['employment_status'] = filters['employment_status']
    if filters['gender']:
        stats_filters['gender'] = filters['gender']
    if filters['department']:
        stats_filters['department'] = filters['department']
    if filters['is_teaching']:
        # Note: This would need to be handled in stats.py
        pass
    
    stats = get_staff_statistics(filters=stats_filters if stats_filters else None)

    # Check if requesting all results (for print/export)
    if filters['page'] == 'all':
        staff_list = []
        for s in staff:
            # Check if teaching
            is_teacher = Teacher.objects.filter(staff=s).exists()
            
            staff_list.append({
                'id': str(s.id),
                'full_name': s.full_name(),
                'staff_id': s.staff_id,
                'gender': s.get_gender_display(),
                'department': s.primary_department.name if s.primary_department else '',
                'employment_status': s.get_employment_status_display(),
                'is_teaching': is_teacher,
                'age': s.get_age() if hasattr(s, 'get_age') else (
                    today.year - s.date_of_birth.year - (
                        (today.month, today.day) < (s.date_of_birth.month, s.date_of_birth.day)
                    ) if s.date_of_birth else None
                ),
                'photo': s.photo.url if s.photo else '',
                'phone': s.phone_number or '',
                'email': s.personal_email or '',
                'date_of_birth': s.date_of_birth.isoformat() if s.date_of_birth else None,
                'date_of_joining': s.date_of_joining.isoformat() if s.date_of_joining else None,
                'is_active': s.is_active,
            })

        return JsonResponse({
            'staff': staff_list,
            'total_count': staff.count(),
            'stats': stats,
        })

    # Regular pagination
    staff_page, paginator = paginate_queryset(request, staff, per_page=10)

    staff_list = []
    for s in staff_page:
        # Check if teaching
        is_teacher = Teacher.objects.filter(staff=s).exists()
        
        staff_list.append({
            'id': str(s.id),
            'full_name': s.full_name(),
            'staff_id': s.staff_id,
            'gender': s.get_gender_display(),
            'department': s.primary_department.name if s.primary_department else '',
            'employment_status': s.get_employment_status_display(),
            'is_teaching': is_teacher,
            'age': s.get_age() if hasattr(s, 'get_age') else (
                today.year - s.date_of_birth.year - (
                    (today.month, today.day) < (s.date_of_birth.month, s.date_of_birth.day)
                ) if s.date_of_birth else None
            ),
            'photo': s.photo.url if s.photo else '',
            'phone': s.phone_number or '',
            'email': s.personal_email or '',
            'date_of_birth': s.date_of_birth.isoformat() if s.date_of_birth else None,
            'date_of_joining': s.date_of_joining.isoformat() if s.date_of_joining else None,
            'is_active': s.is_active,
        })

    return JsonResponse({
        'staff': staff_list,
        'has_previous': staff_page.has_previous(),
        'has_next': staff_page.has_next(),
        'current_page': staff_page.number,
        'total_pages': paginator.num_pages,
        'total_count': paginator.count,
        'start_index': staff_page.start_index(),
        'end_index': staff_page.end_index(),
        'stats': stats,
    })


# =============================================================================
# TEACHER SEARCH
# =============================================================================

def teacher_search(request):
    """
    AJAX view to return filtered teachers as JSON with statistics
    """
    filter_keys = [
        'q', 'subject', 'academic_level', 'is_class_teacher', 
        'digital_literacy', 'page'
    ]
    filters = parse_filters(request, filter_keys)

    teachers = Teacher.objects.select_related(
        'staff', 'staff__primary_department'
    ).filter(
        staff__is_active=True
    ).order_by('staff__first_name')

    # Apply text search
    if filters['q']:
        terms = filters['q'].split()
        q_objects = Q()
        for term in terms:
            q_objects &= (
                Q(staff__first_name__icontains=term) |
                Q(staff__middle_name__icontains=term) |
                Q(staff__last_name__icontains=term) |
                Q(staff__staff_id__icontains=term) |
                Q(specialization__icontains=term)
            )
        teachers = teachers.filter(q_objects)

    # Apply filters
    if filters['subject']:
        teachers = teachers.filter(qualified_subjects__id=filters['subject'])
    if filters['academic_level']:
        teachers = teachers.filter(preferred_academic_levels__id=filters['academic_level'])
    if filters['is_class_teacher']:
        if filters['is_class_teacher'].lower() == 'true':
            teachers = teachers.filter(is_class_teacher=True)
        elif filters['is_class_teacher'].lower() == 'false':
            teachers = teachers.filter(is_class_teacher=False)
    if filters['digital_literacy']:
        teachers = teachers.filter(digital_literacy_level=filters['digital_literacy'])

    # Get comprehensive statistics using statistics module
    stats_filters = {}
    if filters['is_class_teacher']:
        stats_filters['is_class_teacher'] = (filters['is_class_teacher'].lower() == 'true')
    if filters['digital_literacy']:
        stats_filters['digital_literacy_level'] = filters['digital_literacy']
    
    stats = get_teacher_statistics(filters=stats_filters if stats_filters else None)

    # Check if requesting all results
    if filters['page'] == 'all':
        teacher_list = []
        for t in teachers:
            teacher_list.append({
                'id': str(t.id),
                'staff_id': str(t.staff.id),
                'full_name': t.staff.full_name(),
                'staff_number': t.staff.staff_id,
                'specialization': t.specialization,
                'department': t.staff.primary_department.name if t.staff.primary_department else '',
                'is_class_teacher': t.is_class_teacher,
                'max_hours': t.max_hours_per_week,
                'current_load': t.current_teaching_load,
                'workload_percentage': round((t.current_teaching_load / t.max_hours_per_week * 100), 1) if t.max_hours_per_week > 0 else 0,
                'digital_literacy': t.get_digital_literacy_level_display(),
                'can_teach_online': t.can_teach_online,
                'photo': t.staff.photo.url if t.staff.photo else '',
                'phone': t.staff.phone_number or '',
                'email': t.staff.personal_email or '',
            })

        return JsonResponse({
            'teachers': teacher_list,
            'total_count': teachers.count(),
            'stats': stats,
        })

    # Regular pagination
    teachers_page, paginator = paginate_queryset(request, teachers, per_page=10)

    teacher_list = []
    for t in teachers_page:
        teacher_list.append({
            'id': str(t.id),
            'staff_id': str(t.staff.id),
            'full_name': t.staff.full_name(),
            'staff_number': t.staff.staff_id,
            'specialization': t.specialization,
            'department': t.staff.primary_department.name if t.staff.primary_department else '',
            'is_class_teacher': t.is_class_teacher,
            'max_hours': t.max_hours_per_week,
            'current_load': t.current_teaching_load,
            'workload_percentage': round((t.current_teaching_load / t.max_hours_per_week * 100), 1) if t.max_hours_per_week > 0 else 0,
            'digital_literacy': t.get_digital_literacy_level_display(),
            'can_teach_online': t.can_teach_online,
            'photo': t.staff.photo.url if t.staff.photo else '',
            'phone': t.staff.phone_number or '',
            'email': t.staff.personal_email or '',
        })

    return JsonResponse({
        'teachers': teacher_list,
        'has_previous': teachers_page.has_previous(),
        'has_next': teachers_page.has_next(),
        'current_page': teachers_page.number,
        'total_pages': paginator.num_pages,
        'total_count': paginator.count,
        'start_index': teachers_page.start_index(),
        'end_index': teachers_page.end_index(),
        'stats': stats,
    })

# =============================================================================
# CONTRACT TYPE SEARCH
# =============================================================================

def contract_type_search(request):
    """
    AJAX endpoint for searching and filtering contract types
    Returns JSON with contract types and statistics
    """
    
    # Parse filters from request
    filters = parse_filters(request, [
        'q',              # Search query
        'is_active',      # Active status filter
        'is_renewable',   # Renewable filter
        'sort_by',        # Sort field
        'page'            # Page number
    ])
    
    # Start with all contract types
    queryset = ContractType.objects.all()
    
    # Apply search query
    if filters.get('q'):
        search_query = filters['q']
        queryset = queryset.filter(
            Q(name__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    
    # Filter by active status
    if filters.get('is_active') is not None:
        if filters['is_active'] == 'true':
            queryset = queryset.filter(is_active=True)
        elif filters['is_active'] == 'false':
            queryset = queryset.filter(is_active=False)
    
    # Filter by renewable status
    if filters.get('is_renewable') is not None:
        if filters['is_renewable'] == 'true':
            queryset = queryset.filter(is_renewable=True)
        elif filters['is_renewable'] == 'false':
            queryset = queryset.filter(is_renewable=False)
    
    # Annotate with contract counts
    queryset = queryset.annotate(
        contract_count=Count('contracts', distinct=True),
        active_contract_count=Count(
            'contracts',
            filter=Q(contracts__status='ACTIVE'),
            distinct=True
        )
    )
    
    # Apply sorting
    sort_by = filters.get('sort_by', 'name')
    valid_sort_fields = [
        'name', '-name',
        'created_at', '-created_at',
        'contract_count', '-contract_count',
        'default_duration_months', '-default_duration_months'
    ]
    
    if sort_by in valid_sort_fields:
        queryset = queryset.order_by(sort_by)
    else:
        queryset = queryset.order_by('name')
    
    # Paginate results
    page_number = filters.get('page', 1)
    paginated_data = paginate_queryset(request, queryset, per_page=12)
    
    # Build contract types list
    contract_types_list = []
    for contract_type in paginated_data['items']:
        contract_types_list.append({
            'id': str(contract_type.id),
            'name': contract_type.name,
            'description': contract_type.description or '',
            'is_active': contract_type.is_active,
            'is_renewable': contract_type.is_renewable,
            'default_duration_months': contract_type.default_duration_months,
            'default_probation_period_months': contract_type.default_probation_period_months,
            'notice_period_days': contract_type.notice_period_days,
            'contract_count': contract_type.contract_count,
            'active_contracts': contract_type.active_contract_count,
            'created_at': contract_type.created_at.strftime('%b %d, %Y'),
        })
    
    # Get statistics
    stats = get_contract_type_statistics()
    
    # Build response
    response_data = {
        'contract_types': contract_types_list,
        'stats': stats,
        'current_page': paginated_data['current_page'],
        'total_pages': paginated_data['total_pages'],
        'total_count': paginated_data['total_count'],
        'has_previous': paginated_data['has_previous'],
        'has_next': paginated_data['has_next'],
        'start_index': paginated_data['start_index'],
        'end_index': paginated_data['end_index'],
    }
    
    return JsonResponse(response_data)

# =============================================================================
# CONTRACT SEARCH
# =============================================================================

def contract_search(request):
    """
    AJAX view to return filtered contracts as JSON with statistics
    """
    filter_keys = ['q', 'status', 'contract_type', 'expiring_soon', 'page']
    filters = parse_filters(request, filter_keys)

    contracts = Contract.objects.select_related(
        'staff', 'contract_type'
    ).order_by('-start_date')

    # Apply text search
    if filters['q']:
        contracts = contracts.filter(
            Q(contract_number__icontains=filters['q']) |
            Q(staff__first_name__icontains=filters['q']) |
            Q(staff__last_name__icontains=filters['q']) |
            Q(staff__staff_id__icontains=filters['q']) |
            Q(job_title__icontains=filters['q'])
        )

    # Apply filters
    if filters['status']:
        contracts = contracts.filter(status=filters['status'])
    if filters['contract_type']:
        contracts = contracts.filter(contract_type_id=filters['contract_type'])
    
    if filters['expiring_soon'] and filters['expiring_soon'].lower() == 'true':
        from datetime import date, timedelta
        today = date.today()
        end_date = today + timedelta(days=30)
        contracts = contracts.filter(
            status='ACTIVE',
            end_date__gte=today,
            end_date__lte=end_date
        )

    # Get comprehensive statistics using statistics module
    stats_filters = {}
    if filters['status']:
        stats_filters['status'] = filters['status']
    if filters['contract_type']:
        stats_filters['contract_type'] = filters['contract_type']
    
    stats = get_contract_statistics(filters=stats_filters if stats_filters else None)

    # Check if requesting all results
    if filters['page'] == 'all':
        contract_list = []
        for c in contracts:
            contract_list.append({
                'id': str(c.id),
                'contract_number': c.contract_number,
                'staff_name': c.staff.full_name(),
                'staff_id': c.staff.staff_id,
                'contract_type': c.contract_type.name,
                'job_title': c.job_title,
                'status': c.get_status_display(),
                'start_date': c.start_date.isoformat(),
                'end_date': c.end_date.isoformat(),
                'days_until_expiry': c.days_until_expiry,
                'expires_soon': c.expires_soon,
                'basic_salary': str(c.basic_salary),
                'salary_frequency': c.get_salary_frequency_display(),
            })

        return JsonResponse({
            'contracts': contract_list,
            'total_count': contracts.count(),
            'stats': stats,
        })

    # Regular pagination
    contracts_page, paginator = paginate_queryset(request, contracts, per_page=10)

    contract_list = []
    for c in contracts_page:
        contract_list.append({
            'id': str(c.id),
            'contract_number': c.contract_number,
            'staff_name': c.staff.full_name(),
            'staff_id': c.staff.staff_id,
            'contract_type': c.contract_type.name,
            'job_title': c.job_title,
            'status': c.get_status_display(),
            'start_date': c.start_date.isoformat(),
            'end_date': c.end_date.isoformat(),
            'days_until_expiry': c.days_until_expiry,
            'expires_soon': c.expires_soon,
            'basic_salary': str(c.basic_salary),
            'salary_frequency': c.get_salary_frequency_display(),
        })

    return JsonResponse({
        'contracts': contract_list,
        'has_previous': contracts_page.has_previous(),
        'has_next': contracts_page.has_next(),
        'current_page': contracts_page.number,
        'total_pages': paginator.num_pages,
        'total_count': paginator.count,
        'start_index': contracts_page.start_index(),
        'end_index': contracts_page.end_index(),
        'stats': stats,
    })


# =============================================================================
# DEPARTMENT SEARCH
# =============================================================================

def department_search(request):
    """
    AJAX view to return filtered departments as JSON with statistics
    """
    filter_keys = ['q', 'department_type', 'is_active', 'is_academic', 'page']
    filters = parse_filters(request, filter_keys)

    from django.db.models import Count
    
    departments = Department.objects.annotate(
        staff_count=Count('primary_staff', filter=Q(primary_staff__is_active=True))
    ).order_by('name')

    # Apply text search
    if filters['q']:
        departments = departments.filter(
            Q(name__icontains=filters['q']) |
            Q(code__icontains=filters['q']) |
            Q(description__icontains=filters['q'])
        )

    # Apply filters
    if filters['department_type']:
        departments = departments.filter(department_type=filters['department_type'])
    if filters['is_active'] is not None:
        departments = departments.filter(is_active=(filters['is_active'].lower() == 'true'))
    if filters['is_academic'] is not None:
        departments = departments.filter(is_academic=(filters['is_academic'].lower() == 'true'))

    # Get comprehensive statistics using statistics module
    stats_filters = {}
    if filters['department_type']:
        stats_filters['department_type'] = filters['department_type']
    if filters['is_active'] is not None:
        stats_filters['is_active'] = (filters['is_active'].lower() == 'true')
    if filters['is_academic'] is not None:
        stats_filters['is_academic'] = (filters['is_academic'].lower() == 'true')
    
    stats = get_department_statistics(filters=stats_filters if stats_filters else None)

    # Check if requesting all results
    if filters['page'] == 'all':
        department_list = []
        for dept in departments:
            department_list.append({
                'id': str(dept.id),
                'name': dept.name,
                'code': dept.code,
                'type': dept.get_department_type_display(),
                'staff_count': dept.staff_count,
                'is_academic': dept.is_academic,
                'is_active': dept.is_active,
                'head': dept.head.full_name() if dept.head else None,
                'capacity': dept.capacity,
            })

        return JsonResponse({
            'departments': department_list,
            'total_count': departments.count(),
            'stats': stats,
        })

    # Regular pagination
    departments_page, paginator = paginate_queryset(request, departments, per_page=10)

    department_list = []
    for dept in departments_page:
        department_list.append({
            'id': str(dept.id),
            'name': dept.name,
            'code': dept.code,
            'type': dept.get_department_type_display(),
            'staff_count': dept.staff_count,
            'is_academic': dept.is_academic,
            'is_active': dept.is_active,
            'head': dept.head.full_name() if dept.head else None,
            'capacity': dept.capacity,
        })

    return JsonResponse({
        'departments': department_list,
        'has_previous': departments_page.has_previous(),
        'has_next': departments_page.has_next(),
        'current_page': departments_page.number,
        'total_pages': paginator.num_pages,
        'total_count': paginator.count,
        'start_index': departments_page.start_index(),
        'end_index': departments_page.end_index(),
        'stats': stats,
    })


# =============================================================================
# DESIGNATION SEARCH
# =============================================================================

def designation_search(request):
    """
    AJAX view to return filtered designations as JSON with statistics
    """
    filter_keys = ['q', 'department', 'is_teaching', 'is_management', 'is_active', 'page']
    filters = parse_filters(request, filter_keys)

    from django.db.models import Count
    
    designations = Designation.objects.select_related('department').annotate(
        staff_count=Count(
            'staff_members',
            filter=Q(staffdesignation__is_active=True),
            distinct=True
        )
    ).order_by('rank_order')

    # Apply text search
    if filters['q']:
        designations = designations.filter(
            Q(name__icontains=filters['q']) |
            Q(description__icontains=filters['q']) |
            Q(department__name__icontains=filters['q'])
        )

    # Apply filters
    if filters['department']:
        designations = designations.filter(department_id=filters['department'])
    if filters['is_teaching'] is not None:
        designations = designations.filter(is_teaching=(filters['is_teaching'].lower() == 'true'))
    if filters['is_management'] is not None:
        designations = designations.filter(is_management=(filters['is_management'].lower() == 'true'))
    if filters['is_active'] is not None:
        designations = designations.filter(is_active=(filters['is_active'].lower() == 'true'))

    # Get comprehensive statistics using statistics module
    stats_filters = {}
    if filters['department']:
        stats_filters['department'] = filters['department']
    if filters['is_teaching'] is not None:
        stats_filters['is_teaching'] = (filters['is_teaching'].lower() == 'true')
    if filters['is_management'] is not None:
        stats_filters['is_management'] = (filters['is_management'].lower() == 'true')
    if filters['is_active'] is not None:
        stats_filters['is_active'] = (filters['is_active'].lower() == 'true')
    
    stats = get_designation_statistics(filters=stats_filters if stats_filters else None)

    # Check if requesting all results
    if filters['page'] == 'all':
        designation_list = []
        for d in designations:
            designation_list.append({
                'id': str(d.id),
                'name': d.name,
                'department': d.department.name,
                'rank_order': d.rank_order,
                'is_teaching': d.is_teaching,
                'is_management': d.is_management,
                'is_active': d.is_active,
                'staff_count': d.staff_count,
                'min_salary': str(d.min_salary) if d.min_salary else None,
                'max_salary': str(d.max_salary) if d.max_salary else None,
            })

        return JsonResponse({
            'designations': designation_list,
            'total_count': designations.count(),
            'stats': stats,
        })

    # Regular pagination
    designations_page, paginator = paginate_queryset(request, designations, per_page=10)

    designation_list = []
    for d in designations_page:
        designation_list.append({
            'id': str(d.id),
            'name': d.name,
            'department': d.department.name,
            'rank_order': d.rank_order,
            'is_teaching': d.is_teaching,
            'is_management': d.is_management,
            'is_active': d.is_active,
            'staff_count': d.staff_count,
            'min_salary': str(d.min_salary) if d.min_salary else None,
            'max_salary': str(d.max_salary) if d.max_salary else None,
        })

    return JsonResponse({
        'designations': designation_list,
        'has_previous': designations_page.has_previous(),
        'has_next': designations_page.has_next(),
        'current_page': designations_page.number,
        'total_pages': paginator.num_pages,
        'total_count': paginator.count,
        'start_index': designations_page.start_index(),
        'end_index': designations_page.end_index(),
        'stats': stats,
    })


# =============================================================================
# QUICK STAFF INFO
# =============================================================================

def get_staff_quick_info(request, staff_id):
    """
    Get quick information about a staff member for tooltips/modals
    """
    try:
        staff = Staff.objects.select_related('primary_department').get(id=staff_id)
        
        # Check if teacher
        is_teacher = Teacher.objects.filter(staff=staff).exists()
        teacher_info = None
        
        if is_teacher:
            teacher = Teacher.objects.get(staff=staff)
            teacher_info = {
                'specialization': teacher.specialization,
                'is_class_teacher': teacher.is_class_teacher,
                'current_load': teacher.current_teaching_load,
                'max_hours': teacher.max_hours_per_week,
            }
        
        # Get current contract
        current_contract = Contract.objects.filter(
            staff=staff,
            status='ACTIVE'
        ).first()
        
        contract_info = None
        if current_contract:
            contract_info = {
                'contract_number': current_contract.contract_number,
                'job_title': current_contract.job_title,
                'end_date': current_contract.end_date.isoformat(),
                'days_until_expiry': current_contract.days_until_expiry,
            }
        
        return JsonResponse({
            'success': True,
            'staff': {
                'id': str(staff.id),
                'full_name': staff.full_name(),
                'staff_id': staff.staff_id,
                'gender': staff.get_gender_display(),
                'department': staff.primary_department.name if staff.primary_department else '',
                'employment_status': staff.get_employment_status_display(),
                'phone': staff.phone_number or '',
                'email': staff.personal_email or '',
                'photo': staff.photo.url if staff.photo else '',
                'is_active': staff.is_active,
                'date_of_joining': staff.date_of_joining.isoformat() if staff.date_of_joining else None,
            },
            'is_teacher': is_teacher,
            'teacher_info': teacher_info,
            'contract_info': contract_info,
        })
        
    except Staff.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'Staff member not found'
        }, status=404)
    except Exception as e:
        logger.error(f"Error getting staff quick info: {e}")
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=500)