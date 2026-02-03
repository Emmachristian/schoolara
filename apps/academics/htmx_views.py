# academics/htmx_views.py - FIXED VERSION

from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.db.models import Q, Count, Avg, Sum, Prefetch, F
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from datetime import timedelta, date
import logging

from .models import (
    AcademicSession,
    Holiday,
    Subject,
    AcademicLevel,
    ClassRoom,
    Class,
    ClassSubject,
    StudentClassEnrollment,
    AcademicProgress
)

from .forms import ClassSubjectFilterForm
from core.utils import parse_filters, paginate_queryset
# Import stats functions
from . import stats as academic_stats

logger = logging.getLogger(__name__)


# =============================================================================
# HELPER FUNCTION - Apply Boolean Filters Correctly
# =============================================================================

def apply_boolean_filter(queryset, field_name, filter_value):
    """
    Helper to correctly apply boolean filters.
    
    Args:
        queryset: Django queryset
        field_name: Model field name (e.g., 'is_active')
        filter_value: Filter value from request (can be '', 'true', 'false', None)
    
    Returns:
        Filtered queryset (or unchanged if filter_value is empty)
    
    The problem:
        parse_filters() returns '' for empty dropdowns
        Checking `if filter_value is not None:` passes for ''
        Then ''.lower() == 'true' evaluates to False
        Filtering everything out!
    
    The fix:
        Only apply filter if value is truthy AND not empty string
    """
    # ✅ CRITICAL FIX: Check for empty string specifically
    if filter_value and filter_value != '':
        return queryset.filter(**{field_name: (filter_value.lower() == 'true')})
    return queryset


# =============================================================================
# ACADEMIC SESSION SEARCH - FIXED
# =============================================================================

def session_search(request):
    """HTMX-compatible academic session search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'year_name', 'period_type', 'is_current', 
        'is_active', 'is_academically_closed', 'is_special_session',
        'allows_promotion', 'term_number'
    ])
    
    # Build queryset
    sessions = AcademicSession.objects.all().order_by('-start_date', 'term_number')
    
    # Apply text search
    if filters['q']:
        sessions = sessions.filter(
            Q(year_name__icontains=filters['q']) |
            Q(term_name__icontains=filters['q']) |
            Q(description__icontains=filters['q'])
        )
    
    # Apply simple text filters
    if filters['year_name']:
        sessions = sessions.filter(year_name=filters['year_name'])
    
    if filters['period_type']:
        sessions = sessions.filter(period_type=filters['period_type'])
    
    if filters['term_number']:
        sessions = sessions.filter(term_number=filters['term_number'])
    
    # ✅ FIXED: Apply boolean filters correctly
    sessions = apply_boolean_filter(sessions, 'is_current', filters['is_current'])
    sessions = apply_boolean_filter(sessions, 'is_active', filters['is_active'])
    sessions = apply_boolean_filter(sessions, 'is_academically_closed', filters['is_academically_closed'])
    sessions = apply_boolean_filter(sessions, 'is_special_session', filters['is_special_session'])
    sessions = apply_boolean_filter(sessions, 'allows_promotion', filters['allows_promotion'])
    
    # Paginate
    sessions_page, paginator = paginate_queryset(request, sessions, per_page=10)
    
    # Calculate stats from filtered queryset
    total = sessions.count()
    current_date = timezone.now().date()
    
    stats = {
        'total': total,
        'current': sessions.filter(is_current=True).count(),
        'active': sessions.filter(is_active=True).count(),
        'closed': sessions.filter(is_academically_closed=True).count(),
        'special': sessions.filter(is_special_session=True).count(),
        'regular': sessions.filter(is_special_session=False).count(),
        'upcoming': sessions.filter(start_date__gt=current_date).count(),
        'ongoing': sessions.filter(
            start_date__lte=current_date,
            end_date__gte=current_date,
            is_active=True
        ).count(),
        'completed': sessions.filter(end_date__lt=current_date).count(),
        'allows_promotion': sessions.filter(allows_promotion=True).count(),
        'promotion_done': sessions.filter(promotion_done=True).count(),
    }
    
    return render(request, 'academics/sessions/_session_results.html', {
        'sessions_page': sessions_page,
        'stats': stats,
    })


# =============================================================================
# HOLIDAY SEARCH - FIXED
# =============================================================================

def holiday_search(request):
    """HTMX-compatible holiday search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'holiday_type', 'is_school_closed', 'is_partial_closure',
        'is_recurring', 'academic_session', 'year', 'month'
    ])
    
    # Build queryset
    holidays = Holiday.objects.select_related('academic_session').order_by('-start_date')
    
    # Apply text search
    if filters['q']:
        holidays = holidays.filter(
            Q(name__icontains=filters['q']) |
            Q(description__icontains=filters['q']) |
            Q(notes__icontains=filters['q'])
        )
    
    # Apply simple filters
    if filters['holiday_type']:
        holidays = holidays.filter(holiday_type=filters['holiday_type'])
    
    if filters['academic_session']:
        holidays = holidays.filter(academic_session_id=filters['academic_session'])
    
    if filters['year']:
        holidays = holidays.filter(start_date__year=filters['year'])
    
    if filters['month']:
        holidays = holidays.filter(start_date__month=filters['month'])
    
    # ✅ FIXED: Apply boolean filters correctly
    holidays = apply_boolean_filter(holidays, 'is_school_closed', filters['is_school_closed'])
    holidays = apply_boolean_filter(holidays, 'is_partial_closure', filters['is_partial_closure'])
    holidays = apply_boolean_filter(holidays, 'is_recurring', filters['is_recurring'])
    
    # Paginate
    holidays_page, paginator = paginate_queryset(request, holidays, per_page=20)
    
    # Calculate stats
    total = holidays.count()
    current_date = timezone.now().date()
    
    stats = {
        'total': total,
        'school_closed': holidays.filter(is_school_closed=True).count(),
        'partial_closure': holidays.filter(is_partial_closure=True).count(),
        'recurring': holidays.filter(is_recurring=True).count(),
        'current': holidays.filter(
            start_date__lte=current_date,
            end_date__gte=current_date
        ).count() + holidays.filter(
            start_date=current_date,
            end_date__isnull=True
        ).count(),
        'upcoming': holidays.filter(start_date__gt=current_date).count(),
        'past': holidays.filter(
            Q(end_date__lt=current_date) |
            Q(start_date__lt=current_date, end_date__isnull=True)
        ).count(),
        'public': holidays.filter(holiday_type='PUBLIC').count(),
        'school_break': holidays.filter(holiday_type='SCHOOL_BREAK').count(),
    }
    
    return render(request, 'academics/holidays/_holiday_results.html', {
        'holidays_page': holidays_page,
        'stats': stats,
    })


# =============================================================================
# SUBJECT SEARCH - FIXED
# =============================================================================

def subject_search(request):
    """HTMX-compatible subject search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'subject_type', 'is_active', 'is_compulsory',
        'department', 'difficulty_level', 'textbook_required'
    ])
    
    # Build queryset
    subjects = Subject.objects.select_related('department').prefetch_related(
        'applicable_levels',
        'prerequisites'
    ).order_by('subject_type', 'abbreviation')
    
    # Apply text search
    if filters['q']:
        subjects = subjects.filter(
            Q(name__icontains=filters['q']) |
            Q(abbreviation__icontains=filters['q']) |
            Q(code__icontains=filters['q']) |
            Q(description__icontains=filters['q'])
        )
    
    # Apply simple filters
    if filters['subject_type']:
        subjects = subjects.filter(subject_type=filters['subject_type'])
    
    if filters['department']:
        subjects = subjects.filter(department_id=filters['department'])
    
    if filters['difficulty_level']:
        subjects = subjects.filter(difficulty_level=filters['difficulty_level'])
    
    # ✅ FIXED: Apply boolean filters correctly
    subjects = apply_boolean_filter(subjects, 'is_active', filters['is_active'])
    subjects = apply_boolean_filter(subjects, 'is_compulsory', filters['is_compulsory'])
    subjects = apply_boolean_filter(subjects, 'textbook_required', filters['textbook_required'])
    
    # Paginate
    subjects_page, paginator = paginate_queryset(request, subjects, per_page=10)
    
    # Calculate stats
    total = subjects.count()
    
    stats = {
        'total': total,
        'active': subjects.filter(is_active=True).count(),
        'inactive': subjects.filter(is_active=False).count(),
        'compulsory': subjects.filter(is_compulsory=True).count(),
        'optional': subjects.filter(is_compulsory=False).count(),
        'with_prerequisites': subjects.filter(prerequisites__isnull=False).distinct().count(),
        'textbook_required': subjects.filter(textbook_required=True).count(),
        'beginner': subjects.filter(difficulty_level='BEGINNER').count(),
        'intermediate': subjects.filter(difficulty_level='INTERMEDIATE').count(),
        'advanced': subjects.filter(difficulty_level='ADVANCED').count(),
    }
    
    return render(request, 'academics/subjects/_subject_results.html', {
        'subjects_page': subjects_page,
        'stats': stats,
    })


# =============================================================================
# ACADEMIC LEVEL SEARCH - FIXED
# =============================================================================

def academic_level_search(request):
    """HTMX-compatible academic level search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'is_active', 'has_sections', 'is_graduation_level'
    ])
    
    # Build queryset
    levels = AcademicLevel.objects.select_related('next_level').annotate(
        class_count=Count('classes', distinct=True)
    ).order_by('order')
    
    # Apply text search
    if filters['q']:
        levels = levels.filter(
            Q(name__icontains=filters['q']) |
            Q(code__icontains=filters['q']) |
            Q(description__icontains=filters['q'])
        )
    
    # ✅ FIXED: Apply boolean filters correctly
    levels = apply_boolean_filter(levels, 'is_active', filters['is_active'])
    levels = apply_boolean_filter(levels, 'has_sections', filters['has_sections'])
    levels = apply_boolean_filter(levels, 'is_graduation_level', filters['is_graduation_level'])
    
    # Paginate
    levels_page, paginator = paginate_queryset(request, levels, per_page=20)
    
    # Calculate stats
    total = levels.count()
    
    stats = {
        'total': total,
        'active': levels.filter(is_active=True).count(),
        'with_sections': levels.filter(has_sections=True).count(),
        'graduation_levels': levels.filter(is_graduation_level=True).count(),
        'total_classes': sum(level.class_count for level in levels),
    }
    
    return render(request, 'academics/levels/_level_results.html', {
        'levels_page': levels_page,
        'stats': stats,
    })


# =============================================================================
# CLASSROOM SEARCH - FIXED
# =============================================================================

def classroom_search(request):
    """HTMX-compatible classroom search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'room_type', 'building', 'floor', 'is_active',
        'has_projector', 'has_computer', 'has_air_conditioning',
        'is_bookable', 'min_capacity'
    ])
    
    # Build queryset
    classrooms = ClassRoom.objects.annotate(
        assigned_class_count=Count('assigned_classes', distinct=True)
    ).order_by('building', 'floor', 'room_number')
    
    # Apply text search
    if filters['q']:
        classrooms = classrooms.filter(
            Q(name__icontains=filters['q']) |
            Q(room_number__icontains=filters['q']) |
            Q(building__icontains=filters['q']) |
            Q(specialized_equipment__icontains=filters['q'])
        )
    
    # Apply simple filters
    if filters['room_type']:
        classrooms = classrooms.filter(room_type=filters['room_type'])
    
    if filters['building']:
        classrooms = classrooms.filter(building__icontains=filters['building'])
    
    if filters['floor']:
        classrooms = classrooms.filter(floor=filters['floor'])
    
    if filters['min_capacity']:
        try:
            classrooms = classrooms.filter(capacity__gte=int(filters['min_capacity']))
        except ValueError:
            pass
    
    # ✅ FIXED: Apply boolean filters correctly
    classrooms = apply_boolean_filter(classrooms, 'is_active', filters['is_active'])
    classrooms = apply_boolean_filter(classrooms, 'has_projector', filters['has_projector'])
    classrooms = apply_boolean_filter(classrooms, 'has_computer', filters['has_computer'])
    classrooms = apply_boolean_filter(classrooms, 'has_air_conditioning', filters['has_air_conditioning'])
    classrooms = apply_boolean_filter(classrooms, 'is_bookable', filters['is_bookable'])
    
    # Paginate
    classrooms_page, paginator = paginate_queryset(request, classrooms, per_page=10)
    
    # Calculate stats
    total = classrooms.count()
    
    stats = {
        'total': total,
        'active': classrooms.filter(is_active=True).count(),
        'regular': classrooms.filter(room_type='REGULAR').count(),
        'labs': classrooms.filter(room_type__in=['LABORATORY', 'COMPUTER_LAB', 'SCIENCE_LAB']).count(),
        'with_projector': classrooms.filter(has_projector=True).count(),
        'with_computer': classrooms.filter(has_computer=True).count(),
        'with_ac': classrooms.filter(has_air_conditioning=True).count(),
        'bookable': classrooms.filter(is_bookable=True).count(),
        'total_capacity': classrooms.aggregate(Sum('capacity'))['capacity__sum'] or 0,
        'avg_capacity': round(classrooms.aggregate(Avg('capacity'))['capacity__avg'] or 0, 1),
    }
    
    return render(request, 'academics/classrooms/_classroom_results.html', {
        'classrooms_page': classrooms_page,
        'stats': stats,
    })


# =============================================================================
# CLASS SEARCH - FIXED
# =============================================================================

def class_search(request):
    """HTMX-compatible class search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'academic_level', 'academic_session', 'section',
        'class_teacher', 'is_active', 'has_capacity'
    ])
    
    # Build queryset
    classes = Class.objects.select_related(
        'academic_level',
        'academic_session',
        'class_teacher',
        'classroom'
    ).annotate(
        enrollment_count=Count('enrollments', filter=Q(enrollments__is_active=True))
    ).order_by('-academic_session__start_date', 'academic_level__order', 'section')
    
    # Apply text search
    if filters['q']:
        classes = classes.filter(
            Q(academic_level__name__icontains=filters['q']) |
            Q(section__icontains=filters['q']) |
            Q(class_motto__icontains=filters['q'])
        )
    
    # Apply simple filters
    if filters['academic_level']:
        classes = classes.filter(academic_level_id=filters['academic_level'])
    
    if filters['academic_session']:
        classes = classes.filter(academic_session_id=filters['academic_session'])
    
    if filters['section']:
        classes = classes.filter(section__iexact=filters['section'])
    
    if filters['class_teacher']:
        classes = classes.filter(class_teacher_id=filters['class_teacher'])
    
    # ✅ FIXED: Apply boolean filters correctly
    classes = apply_boolean_filter(classes, 'is_active', filters['is_active'])
    
    # Special filter for capacity
    if filters['has_capacity'] and filters['has_capacity'] == 'true':
        classes = classes.filter(enrollment_count__lt=F('max_students'))
    
    # Paginate
    classes_page, paginator = paginate_queryset(request, classes, per_page=10)
    
    # Calculate stats
    total = classes.count()
    
    stats = {
        'total': total,
        'active': classes.filter(is_active=True).count(),
        'with_teacher': classes.filter(class_teacher__isnull=False).count(),
        'with_classroom': classes.filter(classroom__isnull=False).count(),
        'total_capacity': classes.aggregate(Sum('max_students'))['max_students__sum'] or 0,
        'total_enrolled': sum(c.enrollment_count for c in classes),
        'avg_class_size': round(
            sum(c.enrollment_count for c in classes) / total if total > 0 else 0,
            1
        ),
        'full_classes': sum(1 for c in classes if c.enrollment_count >= c.max_students),
    }
    
    return render(request, 'academics/classes/_class_results.html', {
        'classes_page': classes_page,
        'stats': stats,
    })


# =============================================================================
# CLASS SUBJECT SEARCH VIEW
# =============================================================================

from django.db.models import Q, Count, Prefetch
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.shortcuts import render


def class_subject_search(request):
    """
    HTMX view for searching and filtering class subjects.
    Focuses on class-subject assignments. Teacher assignment is handled separately.
    
    Supports two view modes:
    - 'class': Group by class (default) - shows classes with their assigned subjects
    - 'subject': Group by subject - shows subjects with their assigned classes
    """
    
    # =========================================================================
    # GET PARAMETERS
    # =========================================================================
    
    view_mode = request.GET.get('view_mode', 'class')
    query = request.GET.get('q', '').strip()
    academic_session_id = request.GET.get('academic_session')
    academic_level_id = request.GET.get('academic_level')
    is_active = request.GET.get('is_active')
    subject_count_filter = request.GET.get('subject_count_filter')
    
    # =========================================================================
    # BUILD QUERYSET BASED ON VIEW MODE
    # =========================================================================
    
    if view_mode == 'class':
        # ---------------------------------------------------------------------
        # CLASS VIEW: Show classes with their assigned subjects
        # ---------------------------------------------------------------------
        
        queryset = Class.objects.select_related(
            'academic_level',
            'academic_session',
            'class_teacher__staff'  # For displaying class teacher
        ).prefetch_related(
            Prefetch(
                'subjects',
                queryset=ClassSubject.objects.filter(
                    is_active=True
                ).select_related(
                    'subject',
                    'teacher__staff'  # For displaying subject teacher if assigned
                ).order_by('subject__name')
            )
        ).annotate(
            subject_count=Count('subjects', filter=Q(subjects__is_active=True)),
            assigned_teacher_count=Count(
                'subjects',
                filter=Q(subjects__is_active=True, subjects__teacher__isnull=False)
            )
        )
        
        # -----------------------------------------------------------------
        # APPLY FILTERS
        # -----------------------------------------------------------------
        
        # Filter by active status
        if is_active == 'true':
            queryset = queryset.filter(is_active=True)
        elif is_active == 'false':
            queryset = queryset.filter(is_active=False)
        # If not specified, show all
        
        # Search filter
        if query:
            queryset = queryset.filter(
                Q(academic_level__name__icontains=query) |
                Q(section__icontains=query) |
                Q(academic_session__year_name__icontains=query) |
                Q(subjects__subject__name__icontains=query) |
                Q(subjects__subject__code__icontains=query)
            ).distinct()
        
        # Academic session filter
        if academic_session_id:
            queryset = queryset.filter(academic_session_id=academic_session_id)
        
        # Academic level filter
        if academic_level_id:
            queryset = queryset.filter(academic_level_id=academic_level_id)
        
        # Subject count filter
        if subject_count_filter == 'empty':
            # Classes with no subjects assigned
            queryset = queryset.filter(subject_count=0)
        elif subject_count_filter == 'partial':
            # Classes with 1-5 subjects
            queryset = queryset.filter(subject_count__gte=1, subject_count__lte=5)
        elif subject_count_filter == 'full':
            # Classes with 6+ subjects
            queryset = queryset.filter(subject_count__gte=6)
        
        # Order results
        queryset = queryset.order_by(
            '-academic_session__start_date',  # Most recent first
            'academic_level__order',           # Then by level
            'section'                          # Then by section
        )
        
    else:
        # ---------------------------------------------------------------------
        # SUBJECT VIEW: Show subjects with their assigned classes
        # ---------------------------------------------------------------------
        
        queryset = ClassSubject.objects.filter(
            is_active=True
        ).select_related(
            'subject',
            'class_instance__academic_level',
            'class_instance__academic_session',
            'teacher__staff'
        ).order_by(
            'subject__name',
            'class_instance__academic_level__order',
            'class_instance__section'
        )
        
        # Apply filters for subject view
        if query:
            queryset = queryset.filter(
                Q(subject__name__icontains=query) |
                Q(subject__code__icontains=query) |
                Q(class_instance__academic_level__name__icontains=query)
            )
        
        if academic_session_id:
            queryset = queryset.filter(
                class_instance__academic_session_id=academic_session_id
            )
        
        if academic_level_id:
            queryset = queryset.filter(
                class_instance__academic_level_id=academic_level_id
            )
    
    # =========================================================================
    # PAGINATION
    # =========================================================================
    
    page = request.GET.get('page', 1)
    items_per_page = 20
    paginator = Paginator(queryset, items_per_page)
    
    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)
    
    # =========================================================================
    # CALCULATE STATISTICS
    # =========================================================================
    
    if view_mode == 'class':
        # Statistics for class view
        filtered_classes = queryset
        
        total_classes = filtered_classes.count()
        classes_with_subjects = filtered_classes.filter(subject_count__gt=0).count()
        classes_without_subjects = filtered_classes.filter(subject_count=0).count()
        
        # Total assignments in filtered classes
        total_assignments = ClassSubject.objects.filter(
            class_instance__in=filtered_classes,
            is_active=True
        ).count()
        
        # Average subjects per class (only for classes with subjects)
        if classes_with_subjects > 0:
            avg_subjects = total_assignments / classes_with_subjects
            avg_subjects_per_class = f"{avg_subjects:.1f}"
        else:
            avg_subjects_per_class = "0.0"
        
        # Teacher assignment stats (for information only)
        assignments_with_teacher = ClassSubject.objects.filter(
            class_instance__in=filtered_classes,
            is_active=True,
            teacher__isnull=False
        ).count()
        
        assignments_without_teacher = ClassSubject.objects.filter(
            class_instance__in=filtered_classes,
            is_active=True,
            teacher__isnull=True
        ).count()
        
        stats = {
            'total_classes': total_classes,
            'classes_with_subjects': classes_with_subjects,
            'classes_without_subjects': classes_without_subjects,
            'total_assignments': total_assignments,
            'avg_subjects_per_class': avg_subjects_per_class,
            'assignments_with_teacher': assignments_with_teacher,
            'assignments_without_teacher': assignments_without_teacher,
        }
        
    else:
        # Statistics for subject view
        unique_subjects = queryset.values('subject').distinct().count()
        total_assignments = queryset.count()
        
        # Calculate average classes per subject
        if unique_subjects > 0:
            avg_classes = total_assignments / unique_subjects
            avg_classes_per_subject = f"{avg_classes:.1f}"
        else:
            avg_classes_per_subject = "0.0"
        
        assignments_with_teacher = queryset.filter(teacher__isnull=False).count()
        assignments_without_teacher = queryset.filter(teacher__isnull=True).count()
        
        stats = {
            'unique_subjects': unique_subjects,
            'total_assignments': total_assignments,
            'avg_classes_per_subject': avg_classes_per_subject,
            'assignments_with_teacher': assignments_with_teacher,
            'assignments_without_teacher': assignments_without_teacher,
        }
    
    # =========================================================================
    # PREPARE CONTEXT
    # =========================================================================
    
    context = {
        'page_obj': page_obj,
        'stats': stats,
        'view_mode': view_mode,
        'query': query,
        'academic_session_id': academic_session_id,
        'academic_level_id': academic_level_id,
        'is_active': is_active,
        'subject_count_filter': subject_count_filter,
    }
    
    # =========================================================================
    # RENDER APPROPRIATE TEMPLATE
    # =========================================================================
    
    if view_mode == 'class':
        template = 'academics/class_subjects/_class_subject_results.html'
    else:
        template = 'academics/class_subjects/_subject_view_results.html'
    
    return render(request, template, context)

# =============================================================================
# STUDENT CLASS ENROLLMENT SEARCH - FIXED
# =============================================================================

def enrollment_search(request):
    """HTMX-compatible student enrollment search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'academic_session', 'class_instance', 'student',
        'enrollment_type', 'completion_status', 'is_active',
        'progression_type'
    ])
    
    # Build queryset
    enrollments = StudentClassEnrollment.objects.select_related(
        'student',
        'class_instance__academic_level',
        'class_instance__academic_session',
        'academic_session'
    ).order_by('-enrollment_date')
    
    # Apply text search with multi-word support
    if filters['q']:
        words = filters['q'].strip().split()
        if words:
            combined_q = Q()
            for word in words:
                word_q = (
                    Q(student__first_name__icontains=word) |
                    Q(student__last_name__icontains=word) |
                    Q(student__middle_name__icontains=word) |
                    Q(student__admission_number__icontains=word) |
                    Q(roll_number__icontains=word)
                )
                combined_q &= word_q
            enrollments = enrollments.filter(combined_q)
    
    # Apply simple filters
    if filters['academic_session']:
        enrollments = enrollments.filter(academic_session_id=filters['academic_session'])
    
    if filters['class_instance']:
        enrollments = enrollments.filter(class_instance_id=filters['class_instance'])
    
    if filters['student']:
        enrollments = enrollments.filter(student_id=filters['student'])
    
    if filters['enrollment_type']:
        enrollments = enrollments.filter(enrollment_type=filters['enrollment_type'])
    
    if filters['completion_status']:
        enrollments = enrollments.filter(completion_status=filters['completion_status'])
    
    if filters['progression_type']:
        enrollments = enrollments.filter(progression_type=filters['progression_type'])
    
    # ✅ FIXED: Apply boolean filter correctly
    enrollments = apply_boolean_filter(enrollments, 'is_active', filters['is_active'])
    
    # Paginate
    enrollments_page, paginator = paginate_queryset(request, enrollments, per_page=10)
    
    # Calculate stats
    total = enrollments.count()
    
    stats = {
        'total': total,
        'active': enrollments.filter(is_active=True).count(),
        'ongoing': enrollments.filter(completion_status='ONGOING').count(),
        'completed': enrollments.filter(completion_status='COMPLETED').count(),
        'new_admissions': enrollments.filter(enrollment_type='NEW').count(),
        'continuing': enrollments.filter(enrollment_type='CONTINUING').count(),
        'transfers': enrollments.filter(enrollment_type='TRANSFER_IN').count(),
        'repeaters': enrollments.filter(enrollment_type='REPEATER').count(),
        'with_invoice': enrollments.filter(academic_invoice__isnull=False).count(),
    }
    
    return render(request, 'academics/enrollments/_enrollment_results.html', {
        'enrollments_page': enrollments_page,
        'stats': stats,
    })


# =============================================================================
# BULK ENROLLMENT STUDENT SEARCH - FIXED
# =============================================================================

@require_http_methods(["GET"])
def bulk_enrollment_student_search(request):
    """HTMX endpoint for student search in bulk enrollment wizard"""
    
    # Get context from query params
    session_id = request.GET.get('session_id')
    class_id = request.GET.get('class_id')
    
    if not session_id or not class_id:
        return HttpResponse("Missing required parameters", status=400)
    
    try:
        academic_session = AcademicSession.objects.get(pk=session_id)
        class_instance = Class.objects.get(pk=class_id)
    except (AcademicSession.DoesNotExist, Class.DoesNotExist):
        return HttpResponse("Invalid session or class", status=400)
    
    # Parse filters
    filters = parse_filters(request, [
        'search', 'current_level', 'gender', 'enrollment_status', 
        'exclude_enrolled', 'show_eligible_only'
    ])
    
    # Build queryset
    from students.models import Student
    students = Student.objects.select_related('current_academic_level')
    
    # Filter by enrollment status
    if filters['enrollment_status']:
        students = students.filter(enrollment_status=filters['enrollment_status'])
    else:
        students = students.filter(enrollment_status='ACTIVE')
    
    # Apply search filter
    if filters['search']:
        words = filters['search'].split()
        combined_q = Q()
        for word in words:
            word_q = (
                Q(first_name__icontains=word) |
                Q(last_name__icontains=word) |
                Q(middle_name__icontains=word) |
                Q(admission_number__icontains=word)
            )
            combined_q &= word_q
        students = students.filter(combined_q)
    
    # Simple filters
    if filters['current_level']:
        students = students.filter(current_academic_level_id=filters['current_level'])
    
    if filters['gender']:
        students = students.filter(gender=filters['gender'])
    
    # ✅ FIXED: Exclude enrolled filter
    if not filters['exclude_enrolled'] or filters['exclude_enrolled'] == 'true':
        already_enrolled_ids = StudentClassEnrollment.objects.filter(
            academic_session=academic_session,
            is_active=True,
            completion_status='ONGOING'
        ).values_list('student_id', flat=True)
        students = students.exclude(id__in=already_enrolled_ids)
    
    # ✅ FIXED: Show only eligible filter
    if filters['show_eligible_only'] and filters['show_eligible_only'] == 'true':
        students = students.filter(current_academic_level=class_instance.academic_level)
    
    # Order by name
    students = students.order_by('first_name', 'last_name')
    
    # Paginate
    students_page, paginator = paginate_queryset(request, students, per_page=20)
    
    # Get academic levels for filter
    academic_levels = AcademicLevel.objects.filter(is_active=True).order_by('order')
    
    context = {
        'students_page': students_page,
        'academic_session': academic_session,
        'class_instance': class_instance,
        'academic_levels': academic_levels,
        'filters': filters,
    }
    
    return render(
        request,
        'academics/enrollments/wizard/_student_search_results.html',
        context
    )


# =============================================================================
# ACADEMIC PROGRESS SEARCH - FIXED
# =============================================================================

def progress_search(request):
    """HTMX-compatible academic progress search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'academic_session', 'student', 'progress_status',
        'promotion_decision', 'is_eligible_for_promotion',
        'is_final', 'min_gpa', 'max_gpa'
    ])
    
    # Build queryset
    progress_records = AcademicProgress.objects.select_related(
        'student',
        'academic_session',
        'class_enrollment__class_instance',
        'promoted_to_level'
    ).order_by('-academic_session__start_date', 'student__last_name')
    
    # Apply text search
    if filters['q']:
        progress_records = progress_records.filter(
            Q(student__first_name__icontains=filters['q']) |
            Q(student__last_name__icontains=filters['q']) |
            Q(student__admission_number__icontains=filters['q'])
        )
    
    # Apply simple filters
    if filters['academic_session']:
        progress_records = progress_records.filter(academic_session_id=filters['academic_session'])
    
    if filters['student']:
        progress_records = progress_records.filter(student_id=filters['student'])
    
    if filters['progress_status']:
        progress_records = progress_records.filter(progress_status=filters['progress_status'])
    
    if filters['promotion_decision']:
        progress_records = progress_records.filter(promotion_decision=filters['promotion_decision'])
    
    # Numeric filters
    if filters['min_gpa']:
        try:
            progress_records = progress_records.filter(gpa__gte=float(filters['min_gpa']))
        except ValueError:
            pass
    
    if filters['max_gpa']:
        try:
            progress_records = progress_records.filter(gpa__lte=float(filters['max_gpa']))
        except ValueError:
            pass
    
    # ✅ FIXED: Apply boolean filters correctly
    progress_records = apply_boolean_filter(progress_records, 'is_eligible_for_promotion', filters['is_eligible_for_promotion'])
    progress_records = apply_boolean_filter(progress_records, 'is_final', filters['is_final'])
    
    # Paginate
    progress_page, paginator = paginate_queryset(request, progress_records, per_page=20)
    
    # Calculate stats
    total = progress_records.count()
    
    stats = {
        'total': total,
        'finalized': progress_records.filter(is_final=True).count(),
        'eligible_for_promotion': progress_records.filter(is_eligible_for_promotion=True).count(),
        'promoted': progress_records.filter(promotion_decision='PROMOTED').count(),
        'repeat': progress_records.filter(promotion_decision='REPEAT').count(),
        'pending': progress_records.filter(promotion_decision='PENDING').count(),
        'excellent': progress_records.filter(progress_status='EXCELLENT').count(),
        'good': progress_records.filter(progress_status='GOOD').count(),
        'needs_improvement': progress_records.filter(progress_status='NEEDS_IMPROVEMENT').count(),
        'avg_gpa': round(
            progress_records.filter(gpa__isnull=False).aggregate(Avg('gpa'))['gpa__avg'] or 0,
            2
        ),
        'avg_attendance': round(
            progress_records.filter(attendance_percentage__isnull=False).aggregate(
                Avg('attendance_percentage')
            )['attendance_percentage__avg'] or 0,
            1
        ),
    }
    
    return render(request, 'academics/progress/_progress_results.html', {
        'progress_page': progress_page,
        'stats': stats,
    })


# =============================================================================
# QUICK STATS ENDPOINTS
# =============================================================================

@require_http_methods(["GET"])
def session_quick_stats(request):
    """Get quick statistics for academic sessions"""
    current_date = timezone.now().date()
    
    stats = {
        'total': AcademicSession.objects.count(),
        'current': AcademicSession.objects.filter(is_current=True).count(),
        'active': AcademicSession.objects.filter(is_active=True).count(),
        'upcoming': AcademicSession.objects.filter(start_date__gt=current_date).count(),
        'closed': AcademicSession.objects.filter(is_academically_closed=True).count(),
    }
    
    return JsonResponse(stats)


@require_http_methods(["GET"])
def class_quick_stats(request):
    """Get quick statistics for classes"""
    classes = Class.objects.annotate(
        enrollment_count=Count('enrollments', filter=Q(enrollments__is_active=True))
    )
    
    stats = {
        'total': classes.count(),
        'active': classes.filter(is_active=True).count(),
        'with_teacher': classes.filter(class_teacher__isnull=False).count(),
        'total_capacity': classes.aggregate(Sum('max_students'))['max_students__sum'] or 0,
        'total_enrolled': sum(c.enrollment_count for c in classes),
    }
    
    return JsonResponse(stats)


@require_http_methods(["GET"])
def enrollment_quick_stats(request):
    """Get quick statistics for student enrollments"""
    stats = {
        'total': StudentClassEnrollment.objects.count(),
        'active': StudentClassEnrollment.objects.filter(is_active=True).count(),
        'ongoing': StudentClassEnrollment.objects.filter(completion_status='ONGOING').count(),
        'completed': StudentClassEnrollment.objects.filter(completion_status='COMPLETED').count(),
        'new_admissions': StudentClassEnrollment.objects.filter(enrollment_type='NEW').count(),
    }
    
    return JsonResponse(stats)