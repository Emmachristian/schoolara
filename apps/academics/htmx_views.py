# academics/htmx_views.py

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
from utils.utils import parse_filters, paginate_queryset

logger = logging.getLogger(__name__)


# =============================================================================
# ACADEMIC SESSION SEARCH
# =============================================================================

def session_search(request):
    """HTMX-compatible academic session search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'year_name', 'period_type', 'is_current', 
        'is_active', 'is_academically_closed', 'is_special_session',
        'allows_promotion', 'term_number'
    ])
    
    query = filters['q']
    year_name = filters['year_name']
    period_type = filters['period_type']
    is_current = filters['is_current']
    is_active = filters['is_active']
    is_academically_closed = filters['is_academically_closed']
    is_special_session = filters['is_special_session']
    allows_promotion = filters['allows_promotion']
    term_number = filters['term_number']
    
    # Build queryset
    sessions = AcademicSession.objects.all().order_by('-start_date', 'term_number')
    
    # Apply text search
    if query:
        sessions = sessions.filter(
            Q(year_name__icontains=query) |
            Q(term_name__icontains=query) |
            Q(description__icontains=query)
        )
    
    # Apply filters
    if year_name:
        sessions = sessions.filter(year_name=year_name)
    
    if period_type:
        sessions = sessions.filter(period_type=period_type)
    
    if term_number:
        sessions = sessions.filter(term_number=term_number)
    
    if is_current is not None:
        sessions = sessions.filter(is_current=(is_current.lower() == 'true'))
    
    if is_active is not None:
        sessions = sessions.filter(is_active=(is_active.lower() == 'true'))
    
    if is_academically_closed is not None:
        sessions = sessions.filter(is_academically_closed=(is_academically_closed.lower() == 'true'))
    
    if is_special_session is not None:
        sessions = sessions.filter(is_special_session=(is_special_session.lower() == 'true'))
    
    if allows_promotion is not None:
        sessions = sessions.filter(allows_promotion=(allows_promotion.lower() == 'true'))
    
    # Paginate
    sessions_page, paginator = paginate_queryset(request, sessions, per_page=20)
    
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
# HOLIDAY SEARCH
# =============================================================================

def holiday_search(request):
    """HTMX-compatible holiday search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'holiday_type', 'is_school_closed', 'is_partial_closure',
        'is_recurring', 'academic_session', 'year', 'month'
    ])
    
    query = filters['q']
    holiday_type = filters['holiday_type']
    is_school_closed = filters['is_school_closed']
    is_partial_closure = filters['is_partial_closure']
    is_recurring = filters['is_recurring']
    academic_session = filters['academic_session']
    year = filters['year']
    month = filters['month']
    
    # Build queryset
    holidays = Holiday.objects.select_related('academic_session').order_by('-start_date')
    
    # Apply text search
    if query:
        holidays = holidays.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(notes__icontains=query)
        )
    
    # Apply filters
    if holiday_type:
        holidays = holidays.filter(holiday_type=holiday_type)
    
    if academic_session:
        holidays = holidays.filter(academic_session_id=academic_session)
    
    if is_school_closed is not None:
        holidays = holidays.filter(is_school_closed=(is_school_closed.lower() == 'true'))
    
    if is_partial_closure is not None:
        holidays = holidays.filter(is_partial_closure=(is_partial_closure.lower() == 'true'))
    
    if is_recurring is not None:
        holidays = holidays.filter(is_recurring=(is_recurring.lower() == 'true'))
    
    if year:
        holidays = holidays.filter(start_date__year=year)
    
    if month:
        holidays = holidays.filter(start_date__month=month)
    
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
# SUBJECT SEARCH
# =============================================================================

def subject_search(request):
    """HTMX-compatible subject search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'subject_type', 'is_active', 'is_compulsory',
        'department', 'difficulty_level', 'textbook_required'
    ])
    
    query = filters['q']
    subject_type = filters['subject_type']
    is_active = filters['is_active']
    is_compulsory = filters['is_compulsory']
    department = filters['department']
    difficulty_level = filters['difficulty_level']
    textbook_required = filters['textbook_required']
    
    # Build queryset
    subjects = Subject.objects.select_related('department').prefetch_related(
        'applicable_levels',
        'prerequisites'
    ).order_by('subject_type', 'abbreviation')
    
    # Apply text search
    if query:
        subjects = subjects.filter(
            Q(name__icontains=query) |
            Q(abbreviation__icontains=query) |
            Q(code__icontains=query) |
            Q(description__icontains=query)
        )
    
    # Apply filters
    if subject_type:
        subjects = subjects.filter(subject_type=subject_type)
    
    if department:
        subjects = subjects.filter(department_id=department)
    
    if difficulty_level:
        subjects = subjects.filter(difficulty_level=difficulty_level)
    
    if is_active is not None:
        subjects = subjects.filter(is_active=(is_active.lower() == 'true'))
    
    if is_compulsory is not None:
        subjects = subjects.filter(is_compulsory=(is_compulsory.lower() == 'true'))
    
    if textbook_required is not None:
        subjects = subjects.filter(textbook_required=(textbook_required.lower() == 'true'))
    
    # Paginate
    subjects_page, paginator = paginate_queryset(request, subjects, per_page=20)
    
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
# ACADEMIC LEVEL SEARCH
# =============================================================================

def academic_level_search(request):
    """HTMX-compatible academic level search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'is_active', 'has_sections', 'is_graduation_level'
    ])
    
    query = filters['q']
    is_active = filters['is_active']
    has_sections = filters['has_sections']
    is_graduation_level = filters['is_graduation_level']
    
    # Build queryset
    levels = AcademicLevel.objects.select_related('next_level').annotate(
        class_count=Count('classes', distinct=True)
    ).order_by('order')
    
    # Apply text search
    if query:
        levels = levels.filter(
            Q(name__icontains=query) |
            Q(code__icontains=query) |
            Q(description__icontains=query)
        )
    
    # Apply filters
    if is_active is not None:
        levels = levels.filter(is_active=(is_active.lower() == 'true'))
    
    if has_sections is not None:
        levels = levels.filter(has_sections=(has_sections.lower() == 'true'))
    
    if is_graduation_level is not None:
        levels = levels.filter(is_graduation_level=(is_graduation_level.lower() == 'true'))
    
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
# CLASSROOM SEARCH
# =============================================================================

def classroom_search(request):
    """HTMX-compatible classroom search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'room_type', 'building', 'floor', 'is_active',
        'has_projector', 'has_computer', 'has_air_conditioning',
        'is_bookable', 'min_capacity'
    ])
    
    query = filters['q']
    room_type = filters['room_type']
    building = filters['building']
    floor = filters['floor']
    is_active = filters['is_active']
    has_projector = filters['has_projector']
    has_computer = filters['has_computer']
    has_air_conditioning = filters['has_air_conditioning']
    is_bookable = filters['is_bookable']
    min_capacity = filters['min_capacity']
    
    # Build queryset
    classrooms = ClassRoom.objects.annotate(
        assigned_class_count=Count('assigned_classes', distinct=True)
    ).order_by('building', 'floor', 'room_number')
    
    # Apply text search
    if query:
        classrooms = classrooms.filter(
            Q(name__icontains=query) |
            Q(room_number__icontains=query) |
            Q(building__icontains=query) |
            Q(specialized_equipment__icontains=query)
        )
    
    # Apply filters
    if room_type:
        classrooms = classrooms.filter(room_type=room_type)
    
    if building:
        classrooms = classrooms.filter(building__icontains=building)
    
    if floor:
        classrooms = classrooms.filter(floor=floor)
    
    if is_active is not None:
        classrooms = classrooms.filter(is_active=(is_active.lower() == 'true'))
    
    if has_projector is not None:
        classrooms = classrooms.filter(has_projector=(has_projector.lower() == 'true'))
    
    if has_computer is not None:
        classrooms = classrooms.filter(has_computer=(has_computer.lower() == 'true'))
    
    if has_air_conditioning is not None:
        classrooms = classrooms.filter(has_air_conditioning=(has_air_conditioning.lower() == 'true'))
    
    if is_bookable is not None:
        classrooms = classrooms.filter(is_bookable=(is_bookable.lower() == 'true'))
    
    if min_capacity:
        try:
            classrooms = classrooms.filter(capacity__gte=int(min_capacity))
        except ValueError:
            pass
    
    # Paginate
    classrooms_page, paginator = paginate_queryset(request, classrooms, per_page=20)
    
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
# CLASS SEARCH
# =============================================================================

def class_search(request):
    """HTMX-compatible class search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'academic_level', 'academic_session', 'section',
        'class_teacher', 'is_active', 'has_capacity'
    ])
    
    query = filters['q']
    academic_level = filters['academic_level']
    academic_session = filters['academic_session']
    section = filters['section']
    class_teacher = filters['class_teacher']
    is_active = filters['is_active']
    has_capacity = filters['has_capacity']
    
    # Build queryset
    classes = Class.objects.select_related(
        'academic_level',
        'academic_session',
        'class_teacher',
        'classroom'
    ).annotate(
        enrollment_count=Count('enrollments', filter=Q(enrollments__is_active=True))
    ).order_by('academic_session__start_date', 'academic_level__order', 'section')
    
    # Apply text search
    if query:
        classes = classes.filter(
            Q(academic_level__name__icontains=query) |
            Q(section__icontains=query) |
            Q(class_motto__icontains=query)
        )
    
    # Apply filters
    if academic_level:
        classes = classes.filter(academic_level_id=academic_level)
    
    if academic_session:
        classes = classes.filter(academic_session_id=academic_session)
    
    if section:
        classes = classes.filter(section__iexact=section)
    
    if class_teacher:
        classes = classes.filter(class_teacher_id=class_teacher)
    
    if is_active is not None:
        classes = classes.filter(is_active=(is_active.lower() == 'true'))
    
    if has_capacity and has_capacity.lower() == 'true':
        classes = classes.filter(enrollment_count__lt=F('max_students'))
    
    # Paginate
    classes_page, paginator = paginate_queryset(request, classes, per_page=20)
    
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
# CLASS SUBJECT SEARCH
# =============================================================================

def class_subject_search(request):
    """HTMX-compatible class subject search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'class_instance', 'subject', 'teacher', 
        'is_active', 'is_optional'
    ])
    
    query = filters['q']
    class_instance = filters['class_instance']
    subject = filters['subject']
    teacher = filters['teacher']
    is_active = filters['is_active']
    is_optional = filters['is_optional']
    
    # Build queryset
    class_subjects = ClassSubject.objects.select_related(
        'class_instance__academic_level',
        'class_instance__academic_session',
        'subject',
        'teacher'
    ).order_by('class_instance', 'subject__name')
    
    # Apply text search
    if query:
        class_subjects = class_subjects.filter(
            Q(subject__name__icontains=query) |
            Q(subject__code__icontains=query) |
            Q(class_instance__academic_level__name__icontains=query)
        )
    
    # Apply filters
    if class_instance:
        class_subjects = class_subjects.filter(class_instance_id=class_instance)
    
    if subject:
        class_subjects = class_subjects.filter(subject_id=subject)
    
    if teacher:
        class_subjects = class_subjects.filter(teacher_id=teacher)
    
    if is_active is not None:
        class_subjects = class_subjects.filter(is_active=(is_active.lower() == 'true'))
    
    if is_optional is not None:
        class_subjects = class_subjects.filter(is_optional=(is_optional.lower() == 'true'))
    
    # Paginate
    class_subjects_page, paginator = paginate_queryset(request, class_subjects, per_page=20)
    
    # Calculate stats
    total = class_subjects.count()
    
    stats = {
        'total': total,
        'active': class_subjects.filter(is_active=True).count(),
        'compulsory': class_subjects.filter(is_optional=False).count(),
        'optional': class_subjects.filter(is_optional=True).count(),
        'with_teacher': class_subjects.filter(teacher__isnull=False).count(),
        'avg_hours_per_week': round(
            class_subjects.aggregate(Avg('hours_per_week'))['hours_per_week__avg'] or 0,
            1
        ),
        'total_hours': class_subjects.aggregate(Sum('total_hours'))['total_hours__sum'] or 0,
    }
    
    return render(request, 'academics/class_subjects/_class_subject_results.html', {
        'class_subjects_page': class_subjects_page,
        'stats': stats,
    })


# =============================================================================
# STUDENT CLASS ENROLLMENT SEARCH
# =============================================================================

def enrollment_search(request):
    """HTMX-compatible student enrollment search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'academic_session', 'class_instance', 'student',
        'enrollment_type', 'completion_status', 'is_active',
        'progression_type'
    ])
    
    query = filters['q']
    academic_session = filters['academic_session']
    class_instance = filters['class_instance']
    student = filters['student']
    enrollment_type = filters['enrollment_type']
    completion_status = filters['completion_status']
    is_active = filters['is_active']
    progression_type = filters['progression_type']
    
    # Build queryset
    enrollments = StudentClassEnrollment.objects.select_related(
        'student',
        'class_instance__academic_level',
        'class_instance__academic_session',
        'academic_session'
    ).order_by('-enrollment_date')
    
    # Apply text search
    if query:
        enrollments = enrollments.filter(
            Q(student__first_name__icontains=query) |
            Q(student__last_name__icontains=query) |
            Q(student__admission_number__icontains=query) |
            Q(roll_number__icontains=query)
        )
    
    # Apply filters
    if academic_session:
        enrollments = enrollments.filter(academic_session_id=academic_session)
    
    if class_instance:
        enrollments = enrollments.filter(class_instance_id=class_instance)
    
    if student:
        enrollments = enrollments.filter(student_id=student)
    
    if enrollment_type:
        enrollments = enrollments.filter(enrollment_type=enrollment_type)
    
    if completion_status:
        enrollments = enrollments.filter(completion_status=completion_status)
    
    if progression_type:
        enrollments = enrollments.filter(progression_type=progression_type)
    
    if is_active is not None:
        enrollments = enrollments.filter(is_active=(is_active.lower() == 'true'))
    
    # Paginate
    enrollments_page, paginator = paginate_queryset(request, enrollments, per_page=20)
    
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
# ACADEMIC PROGRESS SEARCH
# =============================================================================

def progress_search(request):
    """HTMX-compatible academic progress search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'academic_session', 'student', 'progress_status',
        'promotion_decision', 'is_eligible_for_promotion',
        'is_final', 'min_gpa', 'max_gpa'
    ])
    
    query = filters['q']
    academic_session = filters['academic_session']
    student = filters['student']
    progress_status = filters['progress_status']
    promotion_decision = filters['promotion_decision']
    is_eligible_for_promotion = filters['is_eligible_for_promotion']
    is_final = filters['is_final']
    min_gpa = filters['min_gpa']
    max_gpa = filters['max_gpa']
    
    # Build queryset
    progress_records = AcademicProgress.objects.select_related(
        'student',
        'academic_session',
        'class_enrollment__class_instance',
        'promoted_to_level'
    ).order_by('-academic_session__start_date', 'student__last_name')
    
    # Apply text search
    if query:
        progress_records = progress_records.filter(
            Q(student__first_name__icontains=query) |
            Q(student__last_name__icontains=query) |
            Q(student__admission_number__icontains=query)
        )
    
    # Apply filters
    if academic_session:
        progress_records = progress_records.filter(academic_session_id=academic_session)
    
    if student:
        progress_records = progress_records.filter(student_id=student)
    
    if progress_status:
        progress_records = progress_records.filter(progress_status=progress_status)
    
    if promotion_decision:
        progress_records = progress_records.filter(promotion_decision=promotion_decision)
    
    if is_eligible_for_promotion is not None:
        progress_records = progress_records.filter(
            is_eligible_for_promotion=(is_eligible_for_promotion.lower() == 'true')
        )
    
    if is_final is not None:
        progress_records = progress_records.filter(is_final=(is_final.lower() == 'true'))
    
    if min_gpa:
        try:
            progress_records = progress_records.filter(gpa__gte=float(min_gpa))
        except ValueError:
            pass
    
    if max_gpa:
        try:
            progress_records = progress_records.filter(gpa__lte=float(max_gpa))
        except ValueError:
            pass
    
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
# QUICK STATS ENDPOINTS (for dashboard widgets)
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