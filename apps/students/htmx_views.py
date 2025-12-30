# students/htmx_views.py

from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.db.models import Q, Count, Sum, Avg, F, DecimalField, Case, When, Max, Min
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from datetime import timedelta, date
from decimal import Decimal
import logging

from .models import (
    Student,
    Guardian,
    StudentGuardian,
    SiblingRelationship,
    EnrollmentStatusHistory
)
from utils.utils import parse_filters, paginate_queryset

logger = logging.getLogger(__name__)


# =============================================================================
# STUDENT SEARCH
# =============================================================================

def student_search(request):
    """HTMX-compatible student search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'enrollment_status', 'gender', 'current_academic_level',
        'admission_academic_level', 'nationality', 'has_special_needs',
        'transportation_required', 'religious_affiliation', 'health_condition',
        'min_age', 'max_age', 'admission_year', 'blood_type'
    ])
    
    query = filters['q']
    enrollment_status = filters['enrollment_status']
    gender = filters['gender']
    current_academic_level = filters['current_academic_level']
    admission_academic_level = filters['admission_academic_level']
    nationality = filters['nationality']
    has_special_needs = filters['has_special_needs']
    transportation_required = filters['transportation_required']
    religious_affiliation = filters['religious_affiliation']
    health_condition = filters['health_condition']
    min_age = filters['min_age']
    max_age = filters['max_age']
    admission_year = filters['admission_year']
    blood_type = filters['blood_type']
    
    # Build queryset
    students = Student.objects.select_related(
        'current_academic_level',
        'admission_academic_level',
        'previous_academic_level'
    ).prefetch_related(
        'guardians',
        'guardian_relationships'
    ).annotate(
        guardian_count=Count('guardians', distinct=True),
        sibling_count=Count('sibling_relationships', distinct=True)
    ).order_by('admission_number')
    
    # Apply text search
    if query:
        students = students.filter(
            Q(admission_number__icontains=query) |
            Q(national_student_number__icontains=query) |
            Q(first_name__icontains=query) |
            Q(middle_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(phone_number__icontains=query) |
            Q(personal_email__icontains=query) |
            Q(birth_certificate_number__icontains=query)
        )
    
    # Apply filters
    if enrollment_status:
        students = students.filter(enrollment_status=enrollment_status)
    
    if gender:
        students = students.filter(gender=gender)
    
    if current_academic_level:
        students = students.filter(current_academic_level_id=current_academic_level)
    
    if admission_academic_level:
        students = students.filter(admission_academic_level_id=admission_academic_level)
    
    if nationality:
        students = students.filter(nationality=nationality)
    
    if religious_affiliation:
        students = students.filter(religious_affiliation=religious_affiliation)
    
    if health_condition:
        students = students.filter(health_condition=health_condition)
    
    if blood_type:
        students = students.filter(blood_type=blood_type)
    
    if has_special_needs is not None:
        students = students.filter(has_special_needs=(has_special_needs.lower() == 'true'))
    
    if transportation_required is not None:
        students = students.filter(transportation_required=(transportation_required.lower() == 'true'))
    
    # Age filters
    if min_age:
        try:
            max_birth_date = date.today().replace(year=date.today().year - int(min_age))
            students = students.filter(date_of_birth__lte=max_birth_date)
        except:
            pass
    
    if max_age:
        try:
            min_birth_date = date.today().replace(year=date.today().year - int(max_age) - 1)
            students = students.filter(date_of_birth__gte=min_birth_date)
        except:
            pass
    
    # Admission year filter
    if admission_year:
        try:
            students = students.filter(admission_date__year=int(admission_year))
        except:
            pass
    
    # Paginate
    students_page, paginator = paginate_queryset(request, students, per_page=10)
    
    # Calculate stats
    total = students.count()
    
    stats = {
        'total': total,
        'active': students.filter(enrollment_status='ACTIVE').count(),
        'suspended': students.filter(enrollment_status='SUSPENDED').count(),
        'graduated': students.filter(enrollment_status='GRADUATED').count(),
        'transferred': students.filter(enrollment_status='TRANSFERRED').count(),
        'withdrawn': students.filter(enrollment_status='WITHDRAWN').count(),
        'male': students.filter(gender='M').count(),
        'female': students.filter(gender='F').count(),
        'special_needs': students.filter(has_special_needs=True).count(),
        'transportation': students.filter(transportation_required=True).count(),
        'medical_alerts': students.filter(
            Q(medical_conditions__isnull=False) & ~Q(medical_conditions='') |
            Q(allergies__isnull=False) & ~Q(allergies='') |
            Q(medications__isnull=False) & ~Q(medications='')
        ).count(),
    }
    
    return render(request, 'students/_student_results.html', {
        'students_page': students_page,
        'stats': stats,
    })


# =============================================================================
# GUARDIAN SEARCH
# =============================================================================

def guardian_search(request):
    """HTMX-compatible guardian search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'guardian_type', 'gender', 'is_active',
        'occupation', 'country', 'has_email'
    ])
    
    query = filters['q']
    guardian_type = filters['guardian_type']
    gender = filters['gender']
    is_active = filters['is_active']
    occupation = filters['occupation']
    country = filters['country']
    has_email = filters['has_email']
    
    # Build queryset
    guardians = Guardian.objects.prefetch_related(
        'students',
        'student_relationships'
    ).annotate(
        student_count=Count('students', distinct=True),
        primary_student_count=Count(
            'student_relationships',
            filter=Q(student_relationships__is_primary=True),
            distinct=True
        ),
        financial_responsibility_count=Count(
            'student_relationships',
            filter=Q(student_relationships__is_financial_responsible=True),
            distinct=True
        )
    ).order_by('last_name', 'first_name')
    
    # Apply text search
    if query:
        guardians = guardians.filter(
            Q(first_name__icontains=query) |
            Q(middle_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(primary_phone__icontains=query) |
            Q(secondary_phone__icontains=query) |
            Q(email__icontains=query) |
            Q(national_id__icontains=query) |
            Q(employer__icontains=query)
        )
    
    # Apply filters
    if guardian_type:
        guardians = guardians.filter(guardian_type=guardian_type)
    
    if gender:
        guardians = guardians.filter(gender=gender)
    
    if occupation:
        guardians = guardians.filter(occupation__icontains=occupation)
    
    if country:
        guardians = guardians.filter(country=country)
    
    if is_active is not None:
        guardians = guardians.filter(is_active=(is_active.lower() == 'true'))
    
    if has_email and has_email.lower() == 'true':
        guardians = guardians.exclude(Q(email='') | Q(email__isnull=True))
    
    # Paginate
    guardians_page, paginator = paginate_queryset(request, guardians, per_page=20)
    
    # Calculate stats
    total = guardians.count()
    
    stats = {
        'total': total,
        'active': guardians.filter(is_active=True).count(),
        'primary': guardians.filter(guardian_type='PRIMARY').count(),
        'secondary': guardians.filter(guardian_type='SECONDARY').count(),
        'emergency': guardians.filter(guardian_type='EMERGENCY').count(),
        'financial': guardians.filter(guardian_type='FINANCIAL').count(),
        'male': guardians.filter(gender='M').count(),
        'female': guardians.filter(gender='F').count(),
        'with_email': guardians.exclude(Q(email='') | Q(email__isnull=True)).count(),
        'total_students': sum(g.student_count for g in guardians),
        'avg_income': guardians.filter(monthly_income__isnull=False).aggregate(
            Avg('monthly_income'))['monthly_income__avg'] or 0,
    }
    
    return render(request, 'students/guardians/_guardian_results.html', {
        'guardians_page': guardians_page,
        'stats': stats,
    })


# =============================================================================
# STUDENT-GUARDIAN RELATIONSHIP SEARCH
# =============================================================================

def student_guardian_search(request):
    """HTMX-compatible student-guardian relationship search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'student', 'guardian', 'relationship', 'is_primary',
        'is_financial_responsible', 'is_active', 'can_pickup',
        'can_authorize_medical', 'has_custody'
    ])
    
    query = filters['q']
    student = filters['student']
    guardian = filters['guardian']
    relationship = filters['relationship']
    is_primary = filters['is_primary']
    is_financial_responsible = filters['is_financial_responsible']
    is_active = filters['is_active']
    can_pickup = filters['can_pickup']
    can_authorize_medical = filters['can_authorize_medical']
    has_custody = filters['has_custody']
    
    # Build queryset
    relationships = StudentGuardian.objects.select_related(
        'student__current_academic_level',
        'guardian'
    ).order_by('student__admission_number', 'emergency_contact_priority')
    
    # Apply text search
    if query:
        relationships = relationships.filter(
            Q(student__first_name__icontains=query) |
            Q(student__last_name__icontains=query) |
            Q(student__admission_number__icontains=query) |
            Q(guardian__first_name__icontains=query) |
            Q(guardian__last_name__icontains=query) |
            Q(guardian__primary_phone__icontains=query)
        )
    
    # Apply filters
    if student:
        relationships = relationships.filter(student_id=student)
    
    if guardian:
        relationships = relationships.filter(guardian_id=guardian)
    
    if relationship:
        relationships = relationships.filter(relationship=relationship)
    
    if is_primary is not None:
        relationships = relationships.filter(is_primary=(is_primary.lower() == 'true'))
    
    if is_financial_responsible is not None:
        relationships = relationships.filter(
            is_financial_responsible=(is_financial_responsible.lower() == 'true')
        )
    
    if is_active is not None:
        relationships = relationships.filter(is_active=(is_active.lower() == 'true'))
    
    if can_pickup is not None:
        relationships = relationships.filter(can_pickup=(can_pickup.lower() == 'true'))
    
    if can_authorize_medical is not None:
        relationships = relationships.filter(
            can_authorize_medical=(can_authorize_medical.lower() == 'true')
        )
    
    if has_custody is not None:
        relationships = relationships.filter(has_custody=(has_custody.lower() == 'true'))
    
    # Paginate
    relationships_page, paginator = paginate_queryset(request, relationships, per_page=20)
    
    # Calculate stats
    total = relationships.count()
    
    stats = {
        'total': total,
        'active': relationships.filter(is_active=True).count(),
        'primary': relationships.filter(is_primary=True).count(),
        'financial_responsible': relationships.filter(is_financial_responsible=True).count(),
        'emergency_contacts': relationships.filter(emergency_contact_priority__lte=5).count(),
        'can_pickup': relationships.filter(can_pickup=True).count(),
        'can_authorize_medical': relationships.filter(can_authorize_medical=True).count(),
        'has_custody': relationships.filter(has_custody=True).count(),
        'fathers': relationships.filter(relationship='FATHER').count(),
        'mothers': relationships.filter(relationship='MOTHER').count(),
        'guardians': relationships.filter(relationship='GUARDIAN').count(),
    }
    
    return render(request, 'students/relationships/_relationship_results.html', {
        'relationships_page': relationships_page,
        'stats': stats,
    })


# =============================================================================
# SIBLING RELATIONSHIP SEARCH
# =============================================================================

def sibling_search(request):
    """HTMX-compatible sibling relationship search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'from_student', 'to_student', 'relationship_type', 'is_verified'
    ])
    
    query = filters['q']
    from_student = filters['from_student']
    to_student = filters['to_student']
    relationship_type = filters['relationship_type']
    is_verified = filters['is_verified']
    
    # Build queryset
    siblings = SiblingRelationship.objects.select_related(
        'from_student__current_academic_level',
        'to_student__current_academic_level'
    ).order_by('from_student__admission_number')
    
    # Apply text search
    if query:
        siblings = siblings.filter(
            Q(from_student__first_name__icontains=query) |
            Q(from_student__last_name__icontains=query) |
            Q(from_student__admission_number__icontains=query) |
            Q(to_student__first_name__icontains=query) |
            Q(to_student__last_name__icontains=query) |
            Q(to_student__admission_number__icontains=query)
        )
    
    # Apply filters
    if from_student:
        siblings = siblings.filter(from_student_id=from_student)
    
    if to_student:
        siblings = siblings.filter(to_student_id=to_student)
    
    if relationship_type:
        siblings = siblings.filter(relationship_type=relationship_type)
    
    if is_verified is not None:
        siblings = siblings.filter(is_verified=(is_verified.lower() == 'true'))
    
    # Paginate
    siblings_page, paginator = paginate_queryset(request, siblings, per_page=20)
    
    # Calculate stats
    total = siblings.count()
    
    stats = {
        'total': total,
        'verified': siblings.filter(is_verified=True).count(),
        'unverified': siblings.filter(is_verified=False).count(),
        'full': siblings.filter(relationship_type='FULL').count(),
        'half': siblings.filter(relationship_type='HALF').count(),
        'step': siblings.filter(relationship_type='STEP').count(),
        'adopted': siblings.filter(relationship_type='ADOPTED').count(),
        'foster': siblings.filter(relationship_type='FOSTER').count(),
        'cousin': siblings.filter(relationship_type='COUSIN').count(),
    }
    
    return render(request, 'students/siblings/_sibling_results.html', {
        'siblings_page': siblings_page,
        'stats': stats,
    })


# =============================================================================
# ENROLLMENT STATUS HISTORY SEARCH
# =============================================================================

def enrollment_status_history_search(request):
    """HTMX-compatible enrollment status history search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'student', 'previous_status', 'new_status',
        'academic_session', 'start_date', 'end_date',
        'is_approved', 'approval_required'
    ])
    
    query = filters['q']
    student = filters['student']
    previous_status = filters['previous_status']
    new_status = filters['new_status']
    academic_session = filters['academic_session']
    start_date = filters['start_date']
    end_date = filters['end_date']
    is_approved = filters['is_approved']
    approval_required = filters['approval_required']
    
    # Build queryset
    history = EnrollmentStatusHistory.objects.select_related(
        'student__current_academic_level',
        'academic_session'
    ).order_by('-effective_date', 'student__admission_number')
    
    # Apply text search
    if query:
        history = history.filter(
            Q(student__first_name__icontains=query) |
            Q(student__last_name__icontains=query) |
            Q(student__admission_number__icontains=query) |
            Q(reason__icontains=query)
        )
    
    # Apply filters
    if student:
        history = history.filter(student_id=student)
    
    if previous_status:
        history = history.filter(previous_status=previous_status)
    
    if new_status:
        history = history.filter(new_status=new_status)
    
    if academic_session:
        history = history.filter(academic_session_id=academic_session)
    
    if start_date:
        history = history.filter(effective_date__gte=start_date)
    
    if end_date:
        history = history.filter(effective_date__lte=end_date)
    
    if is_approved is not None:
        history = history.filter(is_approved=(is_approved.lower() == 'true'))
    
    if approval_required is not None:
        history = history.filter(approval_required=(approval_required.lower() == 'true'))
    
    # Paginate
    history_page, paginator = paginate_queryset(request, history, per_page=20)
    
    # Calculate stats
    total = history.count()
    
    # Count status changes by type
    status_changes = {}
    for status_choice in Student.ENROLLMENT_STATUS_CHOICES:
        status_code = status_choice[0]
        status_changes[f'{status_code.lower()}_to'] = history.filter(
            new_status=status_code
        ).count()
        status_changes[f'{status_code.lower()}_from'] = history.filter(
            previous_status=status_code
        ).count()
    
    stats = {
        'total': total,
        'approved': history.filter(is_approved=True).count(),
        'pending_approval': history.filter(
            approval_required=True,
            is_approved=False
        ).count(),
        'to_suspended': history.filter(new_status='SUSPENDED').count(),
        'to_withdrawn': history.filter(new_status='WITHDRAWN').count(),
        'to_graduated': history.filter(new_status='GRADUATED').count(),
        'to_transferred': history.filter(new_status='TRANSFERRED').count(),
        'to_active': history.filter(new_status='ACTIVE').count(),
        'this_year': history.filter(
            effective_date__year=timezone.now().year
        ).count(),
    }
    
    return render(request, 'students/enrollment_history/_history_results.html', {
        'history_page': history_page,
        'stats': stats,
    })


# =============================================================================
# QUICK STATS ENDPOINTS (for dashboard widgets)
# =============================================================================

@require_http_methods(["GET"])
def student_quick_stats(request):
    """Get quick statistics for students"""
    
    today = timezone.now().date()
    
    # Age calculations
    age_ranges = {
        'under_5': Student.objects.filter(
            enrollment_status='ACTIVE',
            date_of_birth__gte=today.replace(year=today.year - 5)
        ).count(),
        'age_5_10': Student.objects.filter(
            enrollment_status='ACTIVE',
            date_of_birth__lt=today.replace(year=today.year - 5),
            date_of_birth__gte=today.replace(year=today.year - 11)
        ).count(),
        'age_11_15': Student.objects.filter(
            enrollment_status='ACTIVE',
            date_of_birth__lt=today.replace(year=today.year - 11),
            date_of_birth__gte=today.replace(year=today.year - 16)
        ).count(),
        'age_16_plus': Student.objects.filter(
            enrollment_status='ACTIVE',
            date_of_birth__lt=today.replace(year=today.year - 16)
        ).count(),
    }
    
    stats = {
        'total': Student.objects.count(),
        'active': Student.objects.filter(enrollment_status='ACTIVE').count(),
        'suspended': Student.objects.filter(enrollment_status='SUSPENDED').count(),
        'graduated': Student.objects.filter(enrollment_status='GRADUATED').count(),
        'male': Student.objects.filter(enrollment_status='ACTIVE', gender='M').count(),
        'female': Student.objects.filter(enrollment_status='ACTIVE', gender='F').count(),
        'special_needs': Student.objects.filter(
            enrollment_status='ACTIVE',
            has_special_needs=True
        ).count(),
        'transportation': Student.objects.filter(
            enrollment_status='ACTIVE',
            transportation_required=True
        ).count(),
        **age_ranges
    }
    
    return JsonResponse(stats)


@require_http_methods(["GET"])
def guardian_quick_stats(request):
    """Get quick statistics for guardians"""
    
    stats = {
        'total': Guardian.objects.filter(is_active=True).count(),
        'primary': Guardian.objects.filter(
            guardian_type='PRIMARY',
            is_active=True
        ).count(),
        'secondary': Guardian.objects.filter(
            guardian_type='SECONDARY',
            is_active=True
        ).count(),
        'financial': Guardian.objects.filter(
            guardian_type='FINANCIAL',
            is_active=True
        ).count(),
        'with_email': Guardian.objects.filter(
            is_active=True
        ).exclude(Q(email='') | Q(email__isnull=True)).count(),
        'total_students': StudentGuardian.objects.filter(is_active=True).count(),
    }
    
    return JsonResponse(stats)


@require_http_methods(["GET"])
def enrollment_status_quick_stats(request):
    """Get quick statistics for enrollment status changes"""
    
    today = timezone.now().date()
    this_month = today.replace(day=1)
    this_year = today.replace(month=1, day=1)
    
    stats = {
        'total_changes': EnrollmentStatusHistory.objects.count(),
        'this_month': EnrollmentStatusHistory.objects.filter(
            effective_date__gte=this_month
        ).count(),
        'this_year': EnrollmentStatusHistory.objects.filter(
            effective_date__gte=this_year
        ).count(),
        'pending_approval': EnrollmentStatusHistory.objects.filter(
            approval_required=True,
            is_approved=False
        ).count(),
        'recent_suspensions': EnrollmentStatusHistory.objects.filter(
            new_status='SUSPENDED',
            effective_date__gte=this_month
        ).count(),
        'recent_graduations': EnrollmentStatusHistory.objects.filter(
            new_status='GRADUATED',
            effective_date__gte=this_year
        ).count(),
    }
    
    return JsonResponse(stats)


@require_http_methods(["GET"])
def medical_alerts_quick_stats(request):
    """Get quick statistics for students with medical alerts"""
    
    stats = {
        'total_medical_alerts': Student.objects.filter(
            enrollment_status='ACTIVE'
        ).filter(
            Q(medical_conditions__isnull=False) & ~Q(medical_conditions='') |
            Q(allergies__isnull=False) & ~Q(allergies='') |
            Q(medications__isnull=False) & ~Q(medications='')
        ).count(),
        'with_conditions': Student.objects.filter(
            enrollment_status='ACTIVE'
        ).exclude(Q(medical_conditions='') | Q(medical_conditions__isnull=True)).count(),
        'with_allergies': Student.objects.filter(
            enrollment_status='ACTIVE'
        ).exclude(Q(allergies='') | Q(allergies__isnull=True)).count(),
        'on_medications': Student.objects.filter(
            enrollment_status='ACTIVE'
        ).exclude(Q(medications='') | Q(medications__isnull=True)).count(),
        'special_needs': Student.objects.filter(
            enrollment_status='ACTIVE',
            has_special_needs=True
        ).count(),
        'special_diet': Student.objects.filter(
            enrollment_status='ACTIVE',
            requires_special_diet=True
        ).count(),
    }
    
    return JsonResponse(stats)