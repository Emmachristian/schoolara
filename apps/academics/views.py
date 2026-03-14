# academics/views.py

"""
Academic Management Views

Comprehensive view functions for:
- Academic Sessions Management (CRUD + Print)
- Subjects and Academic Levels (CRUD + Print)
- Classes and Classrooms (CRUD + Print)
- Student Class Enrollments (CRUD + Print + Bulk)
- Academic Progress Tracking (CRUD + Print)
- Holidays Management (CRUD + Print)
- Class Subjects Management (CRUD + Print + Bulk)
- Reports and Analytics

All views delegate business logic to services.py
Uses SweetAlert2 for all notifications via Django messages
Uses core.utils for timezone-aware operations
Audit trail automatically handled by BaseModel

Pattern follows loans/views.py:
- Helper functions for filtering
- HTMX response headers
- Clean separation of concerns
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.contrib import messages
from django.db.models import Q, Count, Sum, Avg, Prefetch, F
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from django.db import transaction
from django.core.exceptions import ValidationError
from datetime import timedelta, date, datetime
from decimal import Decimal
import logging
import json
from django.http import HttpResponse
from django.db import transaction

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# ⭐ Import timezone utilities from core
from core.utils import (
    get_school_today,
    get_school_current_time,
    get_school_timezone,
    localize_datetime,
    get_active_academic_session,
    format_money,
    calculate_percentage,
    validate_date_range,
)

from .models import (
    AcademicSession,
    Subject,
    AcademicLevel,
    ClassRoom,
    Class,
    StudentClassEnrollment,
    ClassSubject,
    AcademicProgress,
    Holiday,
)

from .forms import (
    AcademicSessionFilterForm,
    SubjectFilterForm,
    AcademicLevelFilterForm,
    ClassRoomFilterForm,
    ClassFilterForm,
    StudentClassEnrollmentFilterForm,
    ClassSubjectFilterForm,
    AcademicProgressFilterForm,
    HolidayFilterForm,
    AcademicSessionForm,
    SubjectForm,
    AcademicLevelForm,
    ClassRoomForm,
    ClassForm,
    StudentEnrollmentForm,
    BulkEnrollmentStudentSelectionForm,
    BulkEnrollmentConfirmationForm,
    ClassSubjectForm,
    BulkClassSubjectForm,
    AcademicProgressForm,
    HolidayForm,
)

from .services import BulkEnrollmentService, EnrollmentValidationService
from students.models import Student
from . import stats as academic_stats

logger = logging.getLogger(__name__)


# =============================================================================
# DASHBOARD
# =============================================================================

@login_required
def academics_dashboard(request):
    """Main academics dashboard with overview statistics"""
    
    try:
        # Use comprehensive overview from stats.py
        overview = academic_stats.get_academic_dashboard_statistics()
        current_session = academic_stats.get_current_academic_session()
        
        # Get additional statistics
        today = get_school_today()
        current_year = today.year
        
        session_stats = academic_stats.get_academic_session_statistics({
            'year_name': str(current_year)
        })
        class_stats = academic_stats.get_class_statistics()
        enrollment_stats = academic_stats.get_student_enrollment_statistics()
        subject_stats = academic_stats.get_subject_statistics()
        
    except Exception as e:
        logger.error(f"Error getting dashboard statistics: {e}")
        overview = {}
        current_session = None
        session_stats = {}
        class_stats = {}
        enrollment_stats = {}
        subject_stats = {}
    
    # Get recent activities
    recent_sessions = AcademicSession.objects.order_by('-created_at')[:10]
    recent_enrollments = StudentClassEnrollment.objects.select_related(
        'student', 'class_instance', 'academic_session'
    ).order_by('-created_at')[:10]
    
    today = get_school_today()
    upcoming_holidays = Holiday.objects.filter(
        start_date__gte=today
    ).order_by('start_date')[:10]
    
    # Get items needing attention
    classes_at_capacity = Class.objects.annotate(
        enrollment_count=Count('enrollments', filter=Q(enrollments__is_active=True))
    ).filter(enrollment_count__gte=F('max_students')).order_by('-enrollment_count')[:10]
    
    sessions_ending_soon = AcademicSession.objects.filter(
        end_date__gte=today,
        end_date__lte=today + timedelta(days=30),
        is_active=True
    ).order_by('end_date')[:10]
    
    pending_progress_records = AcademicProgress.objects.filter(
        is_final=False
    ).select_related('student', 'academic_session').order_by('-updated_at')[:10]
    
    context = {
        'overview': overview,
        'current_session': current_session,
        'session_stats': session_stats,
        'class_stats': class_stats,
        'enrollment_stats': enrollment_stats,
        'subject_stats': subject_stats,
        'recent_sessions': recent_sessions,
        'recent_enrollments': recent_enrollments,
        'upcoming_holidays': upcoming_holidays,
        'classes_at_capacity': classes_at_capacity,
        'sessions_ending_soon': sessions_ending_soon,
        'pending_progress_records': pending_progress_records,
    }
    
    return render(request, 'academics/dashboard.html', context)


# =============================================================================
# HELPER FUNCTIONS FOR FILTERING
# =============================================================================

def get_filtered_academic_sessions(request):
    """Helper function to get filtered academic sessions queryset"""
    sessions = AcademicSession.objects.order_by('-start_date', 'term_number')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    year_name = request.GET.get('year_name', '')
    period_type = request.GET.get('period_type', '')
    is_current = request.GET.get('is_current', '')
    is_active = request.GET.get('is_active', '')
    is_academically_closed = request.GET.get('is_academically_closed', '')
    is_special_session = request.GET.get('is_special_session', '')
    allows_promotion = request.GET.get('allows_promotion', '')
    term_number = request.GET.get('term_number', '')
    
    # Apply text search
    if query:
        sessions = sessions.filter(
            Q(year_name__icontains=query) |
            Q(term_name__icontains=query) |
            Q(description__icontains=query)
        )
    
    # Apply filters
    if year_name:
        sessions = sessions.filter(year_name__icontains=year_name)
    if period_type:
        sessions = sessions.filter(period_type=period_type)
    if is_current:
        sessions = sessions.filter(is_current=(is_current.lower() == 'true'))
    if is_active:
        sessions = sessions.filter(is_active=(is_active.lower() == 'true'))
    if is_academically_closed:
        sessions = sessions.filter(is_academically_closed=(is_academically_closed.lower() == 'true'))
    if is_special_session:
        sessions = sessions.filter(is_special_session=(is_special_session.lower() == 'true'))
    if allows_promotion:
        sessions = sessions.filter(allows_promotion=(allows_promotion.lower() == 'true'))
    if term_number:
        try:
            sessions = sessions.filter(term_number=int(term_number))
        except (ValueError, TypeError):
            pass
    
    return sessions


def get_filtered_subjects(request):
    """Helper function to get filtered subjects queryset"""
    subjects = Subject.objects.select_related('department').prefetch_related(
        'applicable_levels', 'prerequisites'
    ).order_by('subject_type', 'abbreviation')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    subject_type = request.GET.get('subject_type', '')
    is_active = request.GET.get('is_active', '')
    is_compulsory = request.GET.get('is_compulsory', '')
    department = request.GET.get('department', '')
    difficulty_level = request.GET.get('difficulty_level', '')
    textbook_required = request.GET.get('textbook_required', '')
    
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
    if is_active:
        subjects = subjects.filter(is_active=(is_active.lower() == 'true'))
    if is_compulsory:
        subjects = subjects.filter(is_compulsory=(is_compulsory.lower() == 'true'))
    if department:
        subjects = subjects.filter(department_id=department)
    if difficulty_level:
        subjects = subjects.filter(difficulty_level=difficulty_level)
    if textbook_required:
        subjects = subjects.filter(textbook_required=(textbook_required.lower() == 'true'))
    
    return subjects


def get_filtered_academic_levels(request):
    """Helper function to get filtered academic levels queryset"""
    levels = AcademicLevel.objects.select_related('next_level').annotate(
        class_count=Count('classes', distinct=True)
    ).order_by('order')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    is_active = request.GET.get('is_active', '')
    has_sections = request.GET.get('has_sections', '')
    is_graduation_level = request.GET.get('is_graduation_level', '')
    
    # Apply text search
    if query:
        levels = levels.filter(
            Q(name__icontains=query) |
            Q(code__icontains=query) |
            Q(description__icontains=query)
        )
    
    # Apply filters
    if is_active:
        levels = levels.filter(is_active=(is_active.lower() == 'true'))
    if has_sections:
        levels = levels.filter(has_sections=(has_sections.lower() == 'true'))
    if is_graduation_level:
        levels = levels.filter(is_graduation_level=(is_graduation_level.lower() == 'true'))
    
    return levels


def get_filtered_classrooms(request):
    """Helper function to get filtered classrooms queryset"""
    classrooms = ClassRoom.objects.annotate(
        assigned_class_count=Count('assigned_classes', distinct=True)
    ).order_by('building', 'floor', 'room_number')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    room_type = request.GET.get('room_type', '')
    building = request.GET.get('building', '')
    floor = request.GET.get('floor', '')
    is_active = request.GET.get('is_active', '')
    is_bookable = request.GET.get('is_bookable', '')
    has_projector = request.GET.get('has_projector', '')
    has_computer = request.GET.get('has_computer', '')
    min_capacity = request.GET.get('min_capacity', '')
    
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
    if is_active:
        classrooms = classrooms.filter(is_active=(is_active.lower() == 'true'))
    if is_bookable:
        classrooms = classrooms.filter(is_bookable=(is_bookable.lower() == 'true'))
    if has_projector:
        classrooms = classrooms.filter(has_projector=(has_projector.lower() == 'true'))
    if has_computer:
        classrooms = classrooms.filter(has_computer=(has_computer.lower() == 'true'))
    if min_capacity:
        try:
            classrooms = classrooms.filter(capacity__gte=int(min_capacity))
        except (ValueError, TypeError):
            pass
    
    return classrooms


def get_filtered_classes(request):
    """Helper function to get filtered classes queryset"""
    classes = Class.objects.select_related(
        'academic_level', 'academic_session', 'class_teacher', 'classroom'
    ).annotate(
        enrollment_count=Count('enrollments', filter=Q(enrollments__is_active=True))
    ).order_by('-academic_session__start_date', 'academic_level__order', 'section')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    academic_level = request.GET.get('academic_level', '')
    academic_session = request.GET.get('academic_session', '')
    section = request.GET.get('section', '')
    class_teacher = request.GET.get('class_teacher', '')
    is_active = request.GET.get('is_active', '')
    has_capacity = request.GET.get('has_capacity', '')
    
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
    if is_active:
        classes = classes.filter(is_active=(is_active.lower() == 'true'))
    if has_capacity and has_capacity.lower() == 'true':
        classes = classes.filter(enrollment_count__lt=F('max_students'))
    
    return classes


def get_filtered_enrollments(request=None, filter_params=None):
    """
    Helper function to get filtered student enrollments queryset.
    
    Args:
        request: HttpRequest object (optional, for GET requests)
        filter_params: dict of filter parameters (optional, for POST requests)
    
    Returns:
        QuerySet: Filtered enrollments
    """
    enrollments = StudentClassEnrollment.objects.select_related(
        'student', 
        'class_instance', 
        'class_instance__academic_level',
        'class_instance__academic_session',
        'academic_session',
        'academic_invoice',
        'academic_invoice__journal_entry'
    ).order_by('-enrollment_date')
    
    # Get filter parameters from request (GET) or filter_params dict (POST)
    if request:
        query = request.GET.get('q', '').strip()
        class_instance = request.GET.get('class_instance', '')
        academic_session = request.GET.get('academic_session', '')
        enrollment_type = request.GET.get('enrollment_type', '')
        completion_status = request.GET.get('completion_status', '')
        progression_type = request.GET.get('progression_type', '')
        is_active = request.GET.get('is_active', '')
        has_invoice = request.GET.get('has_invoice', '')
        enrollment_date_from = request.GET.get('enrollment_date_from', '')
        enrollment_date_to = request.GET.get('enrollment_date_to', '')
    elif filter_params:
        query = filter_params.get('q', '').strip()
        class_instance = filter_params.get('class_instance', '')
        academic_session = filter_params.get('academic_session', '')
        enrollment_type = filter_params.get('enrollment_type', '')
        completion_status = filter_params.get('completion_status', '')
        progression_type = filter_params.get('progression_type', '')
        is_active = filter_params.get('is_active', '')
        has_invoice = filter_params.get('has_invoice', '')
        enrollment_date_from = filter_params.get('enrollment_date_from', '')
        enrollment_date_to = filter_params.get('enrollment_date_to', '')
    else:
        # No filters - return all
        return enrollments
    
    # Apply text search
    if query:
        words = query.strip().split()
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
    
    # Apply filters
    if class_instance:
        enrollments = enrollments.filter(class_instance_id=class_instance)
    if academic_session:
        enrollments = enrollments.filter(academic_session_id=academic_session)
    if enrollment_type:
        enrollments = enrollments.filter(enrollment_type=enrollment_type)
    if completion_status:
        enrollments = enrollments.filter(completion_status=completion_status)
    if progression_type:
        enrollments = enrollments.filter(progression_type=progression_type)
    if is_active:
        enrollments = enrollments.filter(is_active=(is_active.lower() == 'true'))
    if has_invoice:
        if has_invoice.lower() == 'true':
            enrollments = enrollments.filter(academic_invoice__isnull=False)
        else:
            enrollments = enrollments.filter(academic_invoice__isnull=True)
    
    # Apply date range filters
    if enrollment_date_from:
        try:
            from datetime import datetime
            date_from = datetime.strptime(enrollment_date_from, '%Y-%m-%d').date()
            enrollments = enrollments.filter(enrollment_date__gte=date_from)
        except (ValueError, TypeError):
            pass
    
    if enrollment_date_to:
        try:
            from datetime import datetime
            date_to = datetime.strptime(enrollment_date_to, '%Y-%m-%d').date()
            enrollments = enrollments.filter(enrollment_date__lte=date_to)
        except (ValueError, TypeError):
            pass
    
    return enrollments


def get_filtered_class_subjects(request):
    """Helper function to get filtered class subjects queryset"""
    class_subjects = ClassSubject.objects.select_related(
        'class_instance__academic_level', 'class_instance__academic_session',
        'subject', 'teacher__staff'
    ).filter(is_active=True)
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    class_instance = request.GET.get('class_instance', '')
    subject = request.GET.get('subject', '')
    teacher = request.GET.get('teacher', '')
    is_optional = request.GET.get('is_optional', '')
    
    # Apply text search
    if query:
        class_subjects = class_subjects.filter(
            Q(subject__name__icontains=query) |
            Q(subject__code__icontains=query) |
            Q(class_instance__academic_level__name__icontains=query) |
            Q(class_instance__section__icontains=query)
        )
    
    # Apply filters
    if class_instance:
        class_subjects = class_subjects.filter(class_instance_id=class_instance)
    if subject:
        class_subjects = class_subjects.filter(subject_id=subject)
    if teacher:
        class_subjects = class_subjects.filter(teacher_id=teacher)
    if is_optional:
        class_subjects = class_subjects.filter(is_optional=(is_optional.lower() == 'true'))
    
    # Order by class and subject
    class_subjects = class_subjects.order_by(
        '-class_instance__academic_session__start_date',
        'class_instance__academic_level__order',
        'subject__name'
    )
    
    return class_subjects


def get_filtered_holidays(request):
    """Helper function to get filtered holidays queryset"""
    holidays = Holiday.objects.select_related('academic_session').order_by('-start_date')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    holiday_type = request.GET.get('holiday_type', '')
    is_school_closed = request.GET.get('is_school_closed', '')
    academic_session = request.GET.get('academic_session', '')
    
    # Apply text search
    if query:
        holidays = holidays.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query)
        )
    
    # Apply filters
    if holiday_type:
        holidays = holidays.filter(holiday_type=holiday_type)
    if is_school_closed:
        holidays = holidays.filter(is_school_closed=(is_school_closed.lower() == 'true'))
    if academic_session:
        holidays = holidays.filter(academic_session_id=academic_session)
    
    return holidays


# =============================================================================
# ACADEMIC SESSION VIEWS
# =============================================================================

@login_required
def academic_session_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""
    filter_form = AcademicSessionFilterForm(request.GET or None)
    sessions = get_filtered_academic_sessions(request)
    
    # Calculate statistics
    today = get_school_today()
    stats = {
        'total': sessions.count(),
        'current': sessions.filter(is_current=True).count(),
        'active': sessions.filter(is_active=True).count(),
        'closed': sessions.filter(is_academically_closed=True).count(),
        'special': sessions.filter(is_special_session=True).count(),
        'regular': sessions.filter(is_special_session=False).count(),
        'upcoming': sessions.filter(start_date__gt=today).count(),
        'ongoing': sessions.filter(start_date__lte=today, end_date__gte=today, is_active=True).count(),
    }
    
    # Pagination
    paginator = Paginator(sessions, 10)
    page_number = request.GET.get('page', 1)
    sessions_page = paginator.get_page(page_number)
    
    # Detect HTMX request
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'sessions_page': sessions_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    # Return appropriate template
    if is_htmx:
        return render(request, 'academics/sessions/partials/_session_results.html', context)
    else:
        return render(request, 'academics/sessions/list.html', context)


@login_required
def academic_session_detail(request, pk):
    """View academic session details"""
    session = get_object_or_404(AcademicSession, pk=pk)
    
    # Get session statistics
    try:
        session_stats = academic_stats.get_academic_session_statistics({
            'year_name': session.year_name
        })
    except Exception as e:
        logger.error(f"Error getting session stats: {e}")
        session_stats = {}
    
    # Get related data
    classes = session.classes.select_related(
        'academic_level', 'class_teacher__staff'
    ).prefetch_related('enrollments')[:10]
    
    recent_enrollments = session.student_class_enrollments.select_related(
        'student__current_academic_level', 'class_instance__academic_level'
    ).order_by('-created_at')[:10]
    
    holidays = session.holidays.order_by('start_date')[:10]
    
    # Calculate progress
    today = get_school_today()
    total_days = (session.end_date - session.start_date).days + 1
    
    if today < session.start_date:
        progress_info = {
            'days_until_start': (session.start_date - today).days,
            'days_elapsed': 0,
            'days_remaining': total_days,
            'total_days': total_days,
            'is_current': False,
            'is_future': True,
            'is_past': False,
            'progress_percentage': 0,
        }
    elif today > session.end_date:
        progress_info = {
            'days_since_end': (today - session.end_date).days,
            'days_elapsed': total_days,
            'days_remaining': 0,
            'total_days': total_days,
            'is_current': False,
            'is_future': False,
            'is_past': True,
            'progress_percentage': 100,
        }
    else:
        days_elapsed = (today - session.start_date).days
        days_remaining = (session.end_date - today).days
        progress_info = {
            'days_elapsed': days_elapsed,
            'days_remaining': days_remaining,
            'total_days': total_days,
            'is_current': True,
            'is_future': False,
            'is_past': False,
            'progress_percentage': round((days_elapsed / total_days) * 100, 1) if total_days > 0 else 0,
        }
    
    context = {
        'session': session,
        'session_stats': session_stats,
        'classes': classes,
        'recent_enrollments': recent_enrollments,
        'holidays': holidays,
        'progress_info': progress_info,
    }
    
    return render(request, 'academics/sessions/detail.html', context)


@login_required
def academic_session_close(request, pk):
    """Close academic session with HTMX support"""
    session = get_object_or_404(AcademicSession, pk=pk)
    
    if request.method == 'POST':
        # Validate
        if session.is_academically_closed:
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Session "{session.name}" is already closed'
                response['HX-Alert-Type'] = 'warning'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.warning(request, f'Session "{session.name}" is already closed')
                return redirect('academics:session_detail', pk=pk)
        
        if session.is_current:
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = 'Cannot close current session. Set another session as current first.'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, 'Cannot close current session')
                return redirect('academics:session_detail', pk=pk)
        
        # Close session
        try:
            session.close_academically(user=request.user)
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Session "{session.name}" closed successfully'
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('academics:session_detail', kwargs={'pk': pk})
                return response
            else:
                messages.success(request, f'Session "{session.name}" closed successfully')
                return redirect('academics:session_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error closing session: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error closing session: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error closing session: {str(e)}')
                return redirect('academics:session_detail', pk=pk)


@login_required
def academic_session_reopen(request, pk):
    """Reopen academic session with HTMX support"""
    session = get_object_or_404(AcademicSession, pk=pk)
    
    if request.method == 'POST':
        if not session.is_academically_closed:
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Session "{session.name}" is not closed'
                response['HX-Alert-Type'] = 'warning'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.warning(request, f'Session "{session.name}" is not closed')
                return redirect('academics:session_detail', pk=pk)
        
        try:
            session.reopen_academically(user=request.user)
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Session "{session.name}" reopened successfully'
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('academics:session_detail', kwargs={'pk': pk})
                return response
            else:
                messages.success(request, f'Session "{session.name}" reopened')
                return redirect('academics:session_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error reopening session: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error reopening session: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error reopening session: {str(e)}')
                return redirect('academics:session_detail', pk=pk)


@login_required
def academic_session_delete(request, pk):
    """Delete academic session with HTMX support"""
    session = get_object_or_404(AcademicSession, pk=pk)
    
    if request.method == 'POST':
        # Validate
        if session.is_current or session.is_active:
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = 'Cannot delete active or current sessions'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, 'Cannot delete active or current sessions')
                return redirect('academics:session_detail', pk=pk)
        
        if session.student_class_enrollments.exists() or session.classes.exists():
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = 'Cannot delete session with enrollments or classes'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, 'Cannot delete session with enrollments or classes')
                return redirect('academics:session_detail', pk=pk)
        
        # Delete
        try:
            session_name = session.name
            session.delete()
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Session "{session_name}" deleted successfully'
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('academics:session_list')
                return response
            else:
                messages.success(request, f'Session "{session_name}" deleted successfully')
                return redirect('academics:session_list')
                
        except Exception as e:
            logger.error(f"Error deleting session: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error deleting session: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error deleting session: {str(e)}')
                return redirect('academics:session_detail', pk=pk)


@login_required
def academic_session_set_current(request, pk):
    """Set session as current with HTMX support"""
    session = get_object_or_404(AcademicSession, pk=pk)
    
    if request.method == 'POST':
        try:
            # Remove current flag from all sessions
            AcademicSession.objects.filter(is_current=True).update(is_current=False)
            
            # Set this session as current
            session.is_current = True
            session.save()
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'"{session.name}" is now the current session'
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('academics:session_detail', kwargs={'pk': pk})
                return response
            else:
                messages.success(request, f'Current session updated to "{session.name}"')
                return redirect('academics:session_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error setting current session: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error setting current session: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error setting current session: {str(e)}')
                return redirect('academics:session_detail', pk=pk)


@login_required
def academic_session_print_view(request):
    """Generate printable academic session list"""
    selected_fields = request.GET.getlist('fields')
    if not selected_fields:
        selected_fields = [
            'year_name', 'term_name', 'period_type', 'start_date',
            'end_date', 'status_display', 'is_current'
        ]
    
    include_stats = request.GET.get('include_stats') == 'true'
    landscape = request.GET.get('landscape') == 'true'
    
    sessions = get_filtered_academic_sessions(request)
    
    stats = None
    if include_stats:
        stats = sessions.aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(is_active=True)),
            current=Count('id', filter=Q(is_current=True)),
            closed=Count('id', filter=Q(is_academically_closed=True)),
        )
    
    field_names = {
        'year_name': 'Academic Year',
        'term_name': 'Period Name',
        'term_number': 'Period Number',
        'period_type': 'Period Type',
        'start_date': 'Start Date',
        'end_date': 'End Date',
        'enrollment_deadline': 'Enrollment Deadline',
        'is_current': 'Current',
        'is_active': 'Active',
        'is_academically_closed': 'Closed',
        'status_display': 'Status',
    }
    
    selected_field_names = [
        field_names.get(field, field.replace('_', ' ').title())
        for field in selected_fields
    ]
    
    context = {
        'sessions': sessions,
        'stats': stats,
        'now': timezone.now(),
        'selected_fields': selected_fields,
        'selected_field_names': selected_field_names,
        'field_names': field_names,
        'landscape': landscape,
        'title': 'Academic Sessions Report',
    }
    
    return render(request, 'academics/sessions/print.html', context)


@login_required
def export_academic_sessions_excel(request):
    """Export academic sessions to Excel with filters applied"""
    sessions = get_filtered_academic_sessions(request)
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Academic Sessions"
    
    # Define styles
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_alignment = Alignment(horizontal="center", vertical="center")
    
    # Headers
    headers = [
        '#', 'Year', 'Term', 'Period Type', 'Start Date', 'End Date',
        'Current', 'Active', 'Closed', 'Status'
    ]
    ws.append(headers)
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
    
    # Data rows
    for idx, session in enumerate(sessions, start=1):
        ws.append([
            idx,
            session.year_name,
            session.term_name,
            session.get_period_type_display(),
            session.start_date.strftime('%Y-%m-%d'),
            session.end_date.strftime('%Y-%m-%d'),
            'Yes' if session.is_current else 'No',
            'Yes' if session.is_active else 'No',
            'Yes' if session.is_academically_closed else 'No',
            session.status_display,
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
    filename = f"academic_sessions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


# =============================================================================
# SUBJECT VIEWS
# =============================================================================

@login_required
def subject_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""
    filter_form = SubjectFilterForm(request.GET or None)
    subjects = get_filtered_subjects(request)
    
    # Calculate statistics
    stats = {
        'total': subjects.count(),
        'active': subjects.filter(is_active=True).count(),
        'compulsory': subjects.filter(is_compulsory=True).count(),
        'optional': subjects.filter(is_compulsory=False).count(),
    }
    
    # Pagination
    paginator = Paginator(subjects, 10)
    page_number = request.GET.get('page', 1)
    subjects_page = paginator.get_page(page_number)
    
    # Detect HTMX
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'subjects_page': subjects_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    if is_htmx:
        return render(request, 'academics/subjects/partials/_subject_results.html', context)
    else:
        return render(request, 'academics/subjects/list.html', context)


@login_required
def subject_detail(request, pk):
    """View subject details"""
    subject = get_object_or_404(Subject, pk=pk)
    
    # Get related data
    class_assignments = subject.classes.select_related(
        'class_instance', 'teacher'
    ).filter(is_active=True)[:10]
    
    applicable_levels = subject.applicable_levels.all()
    prerequisites = subject.prerequisites.all()
    
    context = {
        'subject': subject,
        'class_assignments': class_assignments,
        'applicable_levels': applicable_levels,
        'prerequisites': prerequisites,
    }
    
    return render(request, 'academics/subjects/detail.html', context)


@login_required
def subject_delete(request, pk):
    """Delete subject with HTMX support"""
    subject = get_object_or_404(Subject, pk=pk)
    
    if request.method == 'POST':
        if subject.classes.filter(is_active=True).exists():
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = 'Cannot delete subject assigned to active classes'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, 'Cannot delete subject assigned to active classes')
                return redirect('academics:subject_detail', pk=pk)
        
        try:
            subject_name = subject.name
            subject.delete()
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Subject "{subject_name}" deleted successfully'
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('academics:subject_list')
                return response
            else:
                messages.success(request, f'Subject "{subject_name}" deleted successfully')
                return redirect('academics:subject_list')
                
        except Exception as e:
            logger.error(f"Error deleting subject: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error deleting subject: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error deleting subject: {str(e)}')
                return redirect('academics:subject_detail', pk=pk)


# =============================================================================
# ACADEMIC LEVEL VIEWS
# =============================================================================

@login_required
def academic_level_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""
    filter_form = AcademicLevelFilterForm(request.GET or None)
    levels = get_filtered_academic_levels(request)
    
    # Calculate statistics
    stats = {
        'total': levels.count(),
        'active': levels.filter(is_active=True).count(),
        'with_sections': levels.filter(has_sections=True).count(),
        'graduation_levels': levels.filter(is_graduation_level=True).count(),
    }
    
    # Pagination
    paginator = Paginator(levels, 20)
    page_number = request.GET.get('page', 1)
    levels_page = paginator.get_page(page_number)
    
    # Detect HTMX
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'levels_page': levels_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    if is_htmx:
        return render(request, 'academics/levels/partials/_level_results.html', context)
    else:
        return render(request, 'academics/levels/list.html', context)


@login_required
def academic_level_detail(request, pk):
    """View academic level details"""
    level = get_object_or_404(AcademicLevel, pk=pk)
    
    # Get related data
    classes = level.classes.select_related(
        'academic_session', 'class_teacher'
    ).filter(is_active=True)[:10]
    
    from students.models import Student
    current_students = Student.objects.filter(
        current_academic_level=level,
        enrollment_status='ACTIVE'
    )[:10]
    
    # Calculate statistics
    total_classes = level.classes.filter(is_active=True).count()
    total_students = Student.objects.filter(current_academic_level=level).count()
    active_students = Student.objects.filter(
        current_academic_level=level,
        enrollment_status='ACTIVE'
    ).count()
    
    context = {
        'level': level,
        'classes': classes,
        'current_students': current_students,
        'stats': {
            'total_classes': total_classes,
            'total_students': total_students,
            'active_students': active_students,
        }
    }
    
    return render(request, 'academics/levels/detail.html', context)


@login_required
def academic_level_delete(request, pk):
    """Delete academic level with HTMX support"""
    level = get_object_or_404(AcademicLevel, pk=pk)
    
    if request.method == 'POST':
        if level.classes.filter(is_active=True).exists():
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = 'Cannot delete academic level with active classes'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, 'Cannot delete academic level with active classes')
                return redirect('academics:level_detail', pk=pk)
        
        from students.models import Student
        if Student.objects.filter(current_academic_level=level).exists():
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = 'Cannot delete academic level with assigned students'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, 'Cannot delete academic level with assigned students')
                return redirect('academics:level_detail', pk=pk)
        
        try:
            level_name = level.name
            level.delete()
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Academic level "{level_name}" deleted successfully'
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('academics:level_list')
                return response
            else:
                messages.success(request, f'Academic level "{level_name}" deleted successfully')
                return redirect('academics:level_list')
                
        except Exception as e:
            logger.error(f"Error deleting academic level: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error deleting academic level: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error deleting academic level: {str(e)}')
                return redirect('academics:level_detail', pk=pk)


@login_required
def academic_level_print_view(request):
    """Generate printable academic level list"""
    selected_fields = request.GET.getlist('fields')
    if not selected_fields:
        selected_fields = ['name', 'code', 'order', 'has_sections', 'is_graduation_level', 'is_active']
    
    include_stats = request.GET.get('include_stats') == 'true'
    landscape = request.GET.get('landscape') == 'true'
    
    levels = get_filtered_academic_levels(request)
    
    stats = None
    if include_stats:
        stats = levels.aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(is_active=True)),
            with_sections=Count('id', filter=Q(has_sections=True)),
            graduation_levels=Count('id', filter=Q(is_graduation_level=True)),
        )
    
    field_names = {
        'name': 'Level Name',
        'code': 'Level Code',
        'order': 'Order',
        'has_sections': 'Has Sections',
        'is_graduation_level': 'Graduation Level',
        'is_active': 'Active',
        'next_level': 'Next Level',
        'description': 'Description',
    }
    
    selected_field_names = [
        field_names.get(field, field.replace('_', ' ').title())
        for field in selected_fields
    ]
    
    context = {
        'levels': levels,
        'stats': stats,
        'now': timezone.now(),
        'selected_fields': selected_fields,
        'selected_field_names': selected_field_names,
        'field_names': field_names,
        'landscape': landscape,
        'title': 'Academic Levels Report',
    }
    
    return render(request, 'academics/levels/print.html', context)


@login_required
def export_academic_levels_excel(request):
    """Export academic levels to Excel with filters applied"""
    levels = get_filtered_academic_levels(request)
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Academic Levels"
    
    # Define styles
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_alignment = Alignment(horizontal="center", vertical="center")
    
    # Headers
    headers = [
        '#', 'Level Name', 'Code', 'Order', 'Has Sections',
        'Graduation Level', 'Active', 'Total Classes'
    ]
    ws.append(headers)
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
    
    # Data rows
    for idx, level in enumerate(levels, start=1):
        ws.append([
            idx,
            level.name,
            level.code,
            level.order,
            'Yes' if level.has_sections else 'No',
            'Yes' if level.is_graduation_level else 'No',
            'Yes' if level.is_active else 'No',
            level.class_count or 0,
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
    filename = f"academic_levels_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


# =============================================================================
# CLASSROOM VIEWS
# =============================================================================

@login_required
def classroom_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""
    filter_form = ClassRoomFilterForm(request.GET or None)
    classrooms = get_filtered_classrooms(request)
    
    # Calculate statistics
    stats = {
        'total': classrooms.count(),
        'active': classrooms.filter(is_active=True).count(),
        'regular': classrooms.filter(room_type='REGULAR').count(),
        'labs': classrooms.filter(room_type__in=['LABORATORY', 'COMPUTER_LAB', 'SCIENCE_LAB']).count(),
        'total_capacity': classrooms.aggregate(Sum('capacity'))['capacity__sum'] or 0,
    }
    
    # Pagination
    paginator = Paginator(classrooms, 10)
    page_number = request.GET.get('page', 1)
    classrooms_page = paginator.get_page(page_number)
    
    # Detect HTMX
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'classrooms_page': classrooms_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    if is_htmx:
        return render(request, 'academics/classrooms/partials/_classroom_results.html', context)
    else:
        return render(request, 'academics/classrooms/list.html', context)


@login_required
def classroom_detail(request, pk):
    """View classroom details"""
    classroom = get_object_or_404(ClassRoom, pk=pk)
    
    # Get classes currently using this classroom
    current_classes = classroom.assigned_classes.select_related(
        'academic_level', 'academic_session', 'class_teacher'
    ).filter(is_active=True)
    
    # Calculate utilization
    total_capacity = classroom.capacity
    current_students = 0
    
    for cls in current_classes:
        current_students += cls.get_current_enrollment_count()
    
    utilization_percentage = 0
    if total_capacity > 0 and current_students > 0:
        utilization_percentage = round((current_students / total_capacity) * 100, 1)
    
    context = {
        'classroom': classroom,
        'current_classes': current_classes,
        'stats': {
            'current_classes_count': current_classes.count(),
            'current_students': current_students,
            'utilization_percentage': utilization_percentage,
            'available_capacity': max(0, total_capacity - current_students),
        }
    }
    
    return render(request, 'academics/classrooms/detail.html', context)


@login_required
def classroom_delete(request, pk):
    """Delete classroom with HTMX support"""
    classroom = get_object_or_404(ClassRoom, pk=pk)
    
    if request.method == 'POST':
        if classroom.assigned_classes.filter(is_active=True).exists():
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = 'Cannot delete classroom assigned to active classes'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, 'Cannot delete classroom assigned to active classes')
                return redirect('academics:classroom_detail', pk=pk)
        
        try:
            classroom_name = classroom.name
            classroom.delete()
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Classroom "{classroom_name}" deleted successfully'
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('academics:classroom_list')
                return response
            else:
                messages.success(request, f'Classroom "{classroom_name}" deleted successfully')
                return redirect('academics:classroom_list')
                
        except Exception as e:
            logger.error(f"Error deleting classroom: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error deleting classroom: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error deleting classroom: {str(e)}')
                return redirect('academics:classroom_detail', pk=pk)


@login_required
def classroom_print_view(request):
    """Generate printable classroom list"""
    selected_fields = request.GET.getlist('fields')
    if not selected_fields:
        selected_fields = ['name', 'room_number', 'building', 'room_type', 'capacity', 'is_active']
    
    include_stats = request.GET.get('include_stats') == 'true'
    landscape = request.GET.get('landscape') == 'true'
    
    classrooms = get_filtered_classrooms(request)
    
    stats = None
    if include_stats:
        stats = classrooms.aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(is_active=True)),
            total_capacity=Sum('capacity'),
            avg_capacity=Avg('capacity'),
        )
    
    field_names = {
        'name': 'Room Name',
        'room_number': 'Room Number',
        'building': 'Building',
        'floor': 'Floor',
        'room_type': 'Room Type',
        'capacity': 'Capacity',
        'is_active': 'Active',
        'has_projector': 'Projector',
        'has_computer': 'Computer',
    }
    
    selected_field_names = [
        field_names.get(field, field.replace('_', ' ').title())
        for field in selected_fields
    ]
    
    context = {
        'classrooms': classrooms,
        'stats': stats,
        'now': timezone.now(),
        'selected_fields': selected_fields,
        'selected_field_names': selected_field_names,
        'field_names': field_names,
        'landscape': landscape,
        'title': 'Classrooms Report',
    }
    
    return render(request, 'academics/classrooms/print.html', context)


@login_required
def export_classrooms_excel(request):
    """Export classrooms to Excel with filters applied"""
    classrooms = get_filtered_classrooms(request)
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Classrooms"
    
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_alignment = Alignment(horizontal="center", vertical="center")
    
    headers = [
        '#', 'Room Name', 'Room Number', 'Building', 'Floor',
        'Room Type', 'Capacity', 'Active'
    ]
    ws.append(headers)
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
    
    for idx, classroom in enumerate(classrooms, start=1):
        ws.append([
            idx,
            classroom.name,
            classroom.room_number,
            classroom.building or '',
            classroom.floor or '',
            classroom.get_room_type_display(),
            classroom.capacity,
            'Yes' if classroom.is_active else 'No',
        ])
    
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
    
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"classrooms_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


# =============================================================================
# CLASS VIEWS
# =============================================================================

@login_required
def class_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""
    filter_form = ClassFilterForm(request.GET or None)
    classes = get_filtered_classes(request)
    
    # Calculate statistics
    stats = {
        'total': classes.count(),
        'active': classes.filter(is_active=True).count(),
        'with_teacher': classes.filter(class_teacher__isnull=False).count(),
        'total_capacity': classes.aggregate(Sum('max_students'))['max_students__sum'] or 0,
    }
    
    # Pagination
    paginator = Paginator(classes, 10)
    page_number = request.GET.get('page', 1)
    classes_page = paginator.get_page(page_number)
    
    # Detect HTMX
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'classes_page': classes_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    if is_htmx:
        return render(request, 'academics/classes/partials/_class_results.html', context)
    else:
        return render(request, 'academics/classes/list.html', context)


@login_required
def class_detail(request, pk):
    """View class details"""
    class_instance = get_object_or_404(
        Class.objects.select_related(
            'academic_level', 'academic_session', 'class_teacher', 'classroom'
        ),
        pk=pk
    )
    
    # Get current enrollments
    enrollments = class_instance.enrollments.select_related('student').filter(
        is_active=True,
        completion_status='ONGOING'
    ).order_by('roll_number', 'student__last_name')
    
    # Get subjects assigned to this class
    subjects = class_instance.subjects.select_related('subject', 'teacher').filter(
        is_active=True
    )
    
    # Calculate stats
    male_students = enrollments.filter(student__gender='M').count()
    female_students = enrollments.filter(student__gender='F').count()
    
    context = {
        'class': class_instance,
        'enrollments': enrollments,
        'subjects': subjects,
        'stats': {
            'total_students': enrollments.count(),
            'male_students': male_students,
            'female_students': female_students,
            'total_subjects': subjects.count(),
            'compulsory_subjects': subjects.filter(is_optional=False).count(),
            'optional_subjects': subjects.filter(is_optional=True).count(),
        }
    }
    
    return render(request, 'academics/classes/detail.html', context)


@login_required
def class_delete(request, pk):
    """Delete class with HTMX support"""
    class_instance = get_object_or_404(Class, pk=pk)
    
    if request.method == 'POST':
        if class_instance.enrollments.filter(is_active=True).exists():
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = 'Cannot delete class with active enrollments'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, 'Cannot delete class with active enrollments')
                return redirect('academics:class_detail', pk=pk)
        
        if class_instance.subjects.filter(is_active=True).exists():
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = 'Cannot delete class with active subject assignments'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, 'Cannot delete class with active subject assignments')
                return redirect('academics:class_detail', pk=pk)
        
        try:
            class_name = str(class_instance)
            class_instance.delete()
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Class "{class_name}" deleted successfully'
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('academics:class_list')
                return response
            else:
                messages.success(request, f'Class "{class_name}" deleted successfully')
                return redirect('academics:class_list')
                
        except Exception as e:
            logger.error(f"Error deleting class: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error deleting class: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error deleting class: {str(e)}')
                return redirect('academics:class_detail', pk=pk)


@login_required
def class_print_view(request):
    """Generate printable class list"""
    selected_fields = request.GET.getlist('fields')
    if not selected_fields:
        selected_fields = [
            'academic_level', 'section', 'academic_session',
            'class_teacher', 'max_students', 'is_active'
        ]
    
    include_stats = request.GET.get('include_stats') == 'true'
    landscape = request.GET.get('landscape') == 'true'
    
    classes = get_filtered_classes(request)
    
    stats = None
    if include_stats:
        stats = classes.aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(is_active=True)),
            total_capacity=Sum('max_students'),
            with_teacher=Count('id', filter=Q(class_teacher__isnull=False)),
        )
    
    field_names = {
        'academic_level': 'Academic Level',
        'section': 'Section',
        'academic_session': 'Academic Session',
        'class_teacher': 'Class Teacher',
        'max_students': 'Max Students',
        'is_active': 'Active',
    }
    
    selected_field_names = [
        field_names.get(field, field.replace('_', ' ').title())
        for field in selected_fields
    ]
    
    context = {
        'classes': classes,
        'stats': stats,
        'now': timezone.now(),
        'selected_fields': selected_fields,
        'selected_field_names': selected_field_names,
        'field_names': field_names,
        'landscape': landscape,
        'title': 'Classes Report',
    }
    
    return render(request, 'academics/classes/print.html', context)


@login_required
def export_classes_excel(request):
    """Export classes to Excel with filters applied"""
    classes = get_filtered_classes(request)
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Classes"
    
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_alignment = Alignment(horizontal="center", vertical="center")
    
    headers = [
        '#', 'Level', 'Section', 'Session', 'Class Teacher',
        'Max Students', 'Current Enrollment', 'Active'
    ]
    ws.append(headers)
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
    
    for idx, cls in enumerate(classes, start=1):
        ws.append([
            idx,
            cls.academic_level.name,
            cls.section or '',
            str(cls.academic_session),
            cls.class_teacher.staff.full_name() if cls.class_teacher else '',
            cls.max_students,
            cls.enrollment_count,
            'Yes' if cls.is_active else 'No',
        ])
    
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
    
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"classes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


# =============================================================================
# STUDENT ENROLLMENT VIEWS
# =============================================================================

@login_required
def enrollment_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""
    filter_form = StudentClassEnrollmentFilterForm(request.GET or None)
    enrollments = get_filtered_enrollments(request)
    
    # Calculate statistics
    stats = {
        'total': enrollments.count(),
        'active': enrollments.filter(is_active=True, completion_status='ONGOING').count(),
        'completed': enrollments.filter(completion_status='COMPLETED').count(),
        'with_invoice': enrollments.filter(academic_invoice__isnull=False).count(),
    }
    
    # Pagination
    paginator = Paginator(enrollments, 25)
    page_number = request.GET.get('page', 1)
    enrollments_page = paginator.get_page(page_number)
    
    # Detect HTMX
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'enrollments_page': enrollments_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    if is_htmx:
        return render(request, 'academics/enrollments/partials/_enrollment_results.html', context)
    else:
        return render(request, 'academics/enrollments/list.html', context)


@login_required
def enrollment_detail(request, pk):
    """View enrollment details"""
    enrollment = get_object_or_404(
        StudentClassEnrollment.objects.select_related(
            'student', 'class_instance', 'class_instance__academic_level',
            'academic_session', 'academic_invoice', 'previous_enrollment'
        ),
        pk=pk
    )
    
    # Get enrollment history
    enrollment_history = StudentClassEnrollment.objects.filter(
        student=enrollment.student
    ).select_related(
        'class_instance', 'academic_session'
    ).order_by('-enrollment_date')
    
    # Get next enrollment if exists
    next_enrollment = StudentClassEnrollment.objects.filter(
        previous_enrollment=enrollment
    ).select_related('class_instance', 'academic_session').first()
    
    context = {
        'enrollment': enrollment,
        'enrollment_history': enrollment_history,
        'next_enrollment': next_enrollment,
    }
    
    return render(request, 'academics/enrollments/detail.html', context)

@login_required
def enrollment_delete(request, pk):
    """Delete enrollment with HTMX support and filter preservation"""
    enrollment = get_object_or_404(StudentClassEnrollment, pk=pk)
    
    if request.method == 'POST':
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        # =====================================================================
        # CAPTURE CURRENT FILTERS FROM REQUEST (from hx-include="#searchForm")
        # =====================================================================
        filter_params = {
            'q': request.POST.get('q', ''),
            'class_instance': request.POST.get('class_instance', ''),
            'academic_session': request.POST.get('academic_session', ''),
            'enrollment_type': request.POST.get('enrollment_type', ''),
            'completion_status': request.POST.get('completion_status', ''),
            'progression_type': request.POST.get('progression_type', ''),
            'is_active': request.POST.get('is_active', ''),
            'has_invoice': request.POST.get('has_invoice', ''),
            'enrollment_date_from': request.POST.get('enrollment_date_from', ''),
            'enrollment_date_to': request.POST.get('enrollment_date_to', ''),
            'page': request.POST.get('page', '1'),
        }
        
        # DEBUG: Log what we captured
        logger.info(f"Filter params captured from POST: {filter_params}")
        logger.info(f"All POST data keys: {list(request.POST.keys())}")
        
        # =====================================================================
        # VALIDATION: Check if deletion is safe
        # =====================================================================
        
        can_delete = True
        error_message = None
        
        if enrollment.academic_invoice:
            invoice = enrollment.academic_invoice
            
            # ALLOW deletion of VOID and CANCELLED invoices
            if invoice.status in ['VOID', 'CANCELLED']:
                can_delete = True
                logger.info(
                    f"Allowing deletion of enrollment with {invoice.status} invoice "
                    f"({invoice.invoice_number})"
                )
            else:
                # For other statuses, use the invoice's built-in safety check
                can_delete, error_message = invoice.can_be_safely_modified()
                
                if not can_delete:
                    # Format error message - SINGLE LINE for header (no newlines)
                    error_message = (
                        f"Cannot delete enrollment: {error_message}. "
                        f"This enrollment has a finalized invoice ({invoice.invoice_number}). "
                        f"Before deleting, you must: (1) Cancel or void the invoice, "
                        f"(2) Process any necessary refunds, (3) Update student financial records. "
                        f"Contact the finance team for assistance."
                    )
        
        # If deletion is blocked, return error
        if not can_delete:
            logger.warning(
                f"Blocked enrollment deletion for {enrollment.student.get_full_name()}: "
                f"{error_message}"
            )
            
            if is_htmx:
                response = HttpResponse(status=200)
                response['HX-Trigger'] = json.dumps({
                    'showAlert': {
                        'message': error_message,
                        'type': 'error',
                        'title': 'Cannot Delete'
                    },
                    'closeModal': True
                })
                return response
            else:
                messages.error(request, error_message)
                return redirect('academics:enrollment_detail', pk=pk)
        
        # =====================================================================
        # DELETION: Safe to proceed - let signals handle cleanup
        # =====================================================================
        
        try:
            with transaction.atomic():
                student_name = enrollment.student.get_full_name()
                class_name = str(enrollment.class_instance)
                session_name = enrollment.academic_session.name
                enrollment_id = str(enrollment.id)
                
                # Store invoice info for logging (if it exists)
                had_invoice = bool(enrollment.academic_invoice)
                invoice_number = enrollment.academic_invoice.invoice_number if had_invoice else None
                invoice_status = enrollment.academic_invoice.status if had_invoice else None
                
                # Delete the enrollment
                # Signals will handle:
                # 1. Invoice deletion (academics.signals.class_enrollment_pre_delete)
                # 2. Journal entry deletion (fees.signals.fee_invoice_pre_delete)
                # 3. AccountTransaction cleanup (fees.signals.fee_invoice_pre_delete)
                enrollment.delete()
                
                # Build success message
                if had_invoice:
                    if invoice_status in ['VOID', 'CANCELLED']:
                        success_message = (
                            f'Successfully deleted enrollment for "{student_name}" from '
                            f'{class_name} ({session_name}). '
                            f'{invoice_status} invoice {invoice_number} was also deleted.'
                        )
                    else:
                        success_message = (
                            f'Successfully deleted enrollment for "{student_name}" from '
                            f'{class_name} ({session_name}). '
                            f'Draft invoice {invoice_number} was also deleted.'
                        )
                    logger.info(
                        f"Deleted enrollment for {student_name} "
                        f"and {invoice_status} invoice {invoice_number}"
                    )
                else:
                    success_message = (
                        f'Successfully deleted enrollment for "{student_name}" from '
                        f'{class_name} ({session_name}).'
                    )
                    logger.info(f"Deleted enrollment for {student_name}")
                
                # =====================================================================
                # SUCCESS RESPONSE - RETURN UPDATED LIST WITH FILTERS PRESERVED
                # =====================================================================
                
                if is_htmx:
                    # Get fresh filtered data using filter_params
                    logger.info(f"Applying filters: {filter_params}")
                    enrollments = get_filtered_enrollments(filter_params=filter_params)
                    logger.info(f"Filtered enrollments count: {enrollments.count()}")
                    
                    # Calculate statistics
                    stats = {
                        'total': enrollments.count(),
                        'active': enrollments.filter(is_active=True, completion_status='ONGOING').count(),
                        'completed': enrollments.filter(completion_status='COMPLETED').count(),
                        'with_invoice': enrollments.filter(academic_invoice__isnull=False).count(),
                    }
                    
                    # Pagination
                    paginator = Paginator(enrollments, 25)
                    page_number = filter_params.get('page', 1)
                    enrollments_page = paginator.get_page(page_number)
                    
                    logger.info(f"Returning page {page_number} with {len(enrollments_page)} results")
                    
                    # Prepare context (DON'T include success_message in template)
                    context = {
                        'enrollments_page': enrollments_page,
                        'paginator': paginator,
                        'stats': stats,
                        'is_htmx': True,
                    }
                    
                    # Return the updated table HTML
                    response = render(
                        request,
                        'academics/enrollments/partials/_enrollment_results.html',
                        context
                    )
                    
                    # Send BOTH triggers: close modal AND show SweetAlert
                    response['HX-Trigger'] = json.dumps({
                        'closeModal': True,
                        'showAlert': {
                            'message': success_message,
                            'type': 'success',
                            'title': 'Deleted Successfully'
                        }
                    })
                    
                    logger.info("Response prepared with closeModal and showAlert triggers")
                    
                    return response
                else:
                    # Non-HTMX request (traditional POST)
                    messages.success(request, success_message)
                    return redirect('academics:enrollment_list')
                    
        except ValidationError as e:
            # This catches ValidationErrors raised by signals
            if hasattr(e, 'message_dict'):
                error_msg = '; '.join([f"{k}: {', '.join(v)}" for k, v in e.message_dict.items()])
            elif hasattr(e, 'messages'):
                error_msg = '; '.join(e.messages)
            else:
                error_msg = str(e)
            
            # Remove newlines from error message
            error_msg = error_msg.replace('\n', ' ').replace('\r', ' ')
            
            logger.error(f"Validation error deleting enrollment: {error_msg}")
            
            if is_htmx:
                response = HttpResponse(status=200)
                response['HX-Trigger'] = json.dumps({
                    'showAlert': {
                        'message': error_msg,
                        'type': 'error',
                        'title': 'Cannot Delete'
                    },
                    'closeModal': True
                })
                return response
            else:
                messages.error(request, error_msg)
                return redirect('academics:enrollment_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error deleting enrollment: {e}", exc_info=True)
            
            error_msg = str(e).replace('\n', ' ').replace('\r', ' ')
            
            if is_htmx:
                response = HttpResponse(status=200)
                response['HX-Trigger'] = json.dumps({
                    'showAlert': {
                        'message': f'Error deleting enrollment: {error_msg}',
                        'type': 'error',
                        'title': 'Error'
                    },
                    'closeModal': True
                })
                return response
            else:
                messages.error(request, f'Error deleting enrollment: {str(e)}')
                return redirect('academics:enrollment_detail', pk=pk)
    
    # GET request - redirect to list (modal is loaded separately)
    return redirect('academics:enrollment_list')

@login_required
def enrollment_toggle_active(request, pk):
    """Toggle enrollment active status with HTMX support"""
    enrollment = get_object_or_404(StudentClassEnrollment, pk=pk)
    
    if request.method == 'POST':
        try:
            enrollment.is_active = not enrollment.is_active
            enrollment.save(update_fields=['is_active'])
            
            status_text = 'activated' if enrollment.is_active else 'deactivated'
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Enrollment {status_text} successfully'
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('academics:enrollment_detail', kwargs={'pk': pk})
                return response
            else:
                messages.success(request, f'Enrollment {status_text}')
                return redirect('academics:enrollment_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error toggling enrollment status: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error updating status: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error updating status: {str(e)}')
                return redirect('academics:enrollment_detail', pk=pk)


@login_required
def enrollment_update_status(request, pk):
    """Update enrollment completion status with HTMX support"""
    enrollment = get_object_or_404(StudentClassEnrollment, pk=pk)
    
    if request.method == 'POST':
        new_status = request.POST.get('completion_status')
        completion_date = request.POST.get('completion_date')
        notes = request.POST.get('notes', '')
        
        if not new_status:
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = 'Please select a completion status'
                response['HX-Alert-Type'] = 'error'
                return response
            else:
                messages.error(request, 'Please select a completion status')
                return redirect('academics:enrollment_detail', pk=pk)
        
        try:
            with transaction.atomic():
                enrollment.completion_status = new_status
                
                if completion_date:
                    from django.utils.dateparse import parse_date
                    enrollment.completion_date = parse_date(completion_date)
                
                if notes:
                    enrollment.enrollment_notes = notes
                
                # If status is completed or dropped, deactivate enrollment
                if new_status in ['COMPLETED', 'DROPPED', 'WITHDRAWN', 'SUSPENDED']:
                    enrollment.is_active = False
                
                enrollment.save()
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Status updated successfully'
                    response['HX-Alert-Type'] = 'success'
                    response['HX-Close-Modal'] = 'true'
                    response['HX-Redirect'] = reverse('academics:enrollment_detail', kwargs={'pk': pk})
                    return response
                else:
                    messages.success(request, 'Status updated successfully')
                    return redirect('academics:enrollment_detail', pk=pk)
                    
        except Exception as e:
            logger.error(f"Error updating status: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error updating status: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error updating status: {str(e)}')
                return redirect('academics:enrollment_detail', pk=pk)


@login_required
def enrollment_create_invoice(request, pk):
    """Create invoice for enrollment with HTMX support"""
    enrollment = get_object_or_404(StudentClassEnrollment, pk=pk)
    
    if request.method == 'POST':
        if enrollment.academic_invoice:
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = 'Invoice already exists for this enrollment'
                response['HX-Alert-Type'] = 'warning'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.warning(request, 'Invoice already exists')
                return redirect('academics:enrollment_detail', pk=pk)
        
        try:
            from fees.utils import create_enrollment_invoice
            
            with transaction.atomic():
                invoice = create_enrollment_invoice(enrollment)
                enrollment.academic_invoice = invoice
                enrollment.save(update_fields=['academic_invoice'])
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Invoice #{invoice.invoice_number} created successfully'
                    response['HX-Alert-Type'] = 'success'
                    response['HX-Close-Modal'] = 'true'
                    response['HX-Redirect'] = reverse('academics:enrollment_detail', kwargs={'pk': pk})
                    return response
                else:
                    messages.success(request, f'Invoice created successfully')
                    return redirect('academics:enrollment_detail', pk=pk)
                    
        except Exception as e:
            logger.error(f"Error creating invoice: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error creating invoice: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error creating invoice: {str(e)}')
                return redirect('academics:enrollment_detail', pk=pk)


@login_required
def enrollment_assign_roll_number(request, pk):
    """Assign roll number to enrollment with HTMX support"""
    enrollment = get_object_or_404(StudentClassEnrollment, pk=pk)
    
    if request.method == 'POST':
        roll_number = request.POST.get('roll_number', '').strip()
        
        if not roll_number:
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = 'Please enter a roll number'
                response['HX-Alert-Type'] = 'error'
                return response
            else:
                messages.error(request, 'Please enter a roll number')
                return redirect('academics:enrollment_detail', pk=pk)
        
        # Check for duplicate
        duplicate = StudentClassEnrollment.objects.filter(
            class_instance=enrollment.class_instance,
            academic_session=enrollment.academic_session,
            roll_number=roll_number,
            is_active=True
        ).exclude(pk=enrollment.pk).exists()
        
        if duplicate:
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Roll number {roll_number} is already assigned'
                response['HX-Alert-Type'] = 'error'
                return response
            else:
                messages.error(request, f'Roll number {roll_number} is already assigned')
                return redirect('academics:enrollment_detail', pk=pk)
        
        try:
            enrollment.roll_number = roll_number
            enrollment.save(update_fields=['roll_number'])
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Roll number {roll_number} assigned successfully'
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('academics:enrollment_detail', kwargs={'pk': pk})
                return response
            else:
                messages.success(request, f'Roll number assigned successfully')
                return redirect('academics:enrollment_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error assigning roll number: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error assigning roll number: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error assigning roll number: {str(e)}')
                return redirect('academics:enrollment_detail', pk=pk)


@login_required
def enrollment_print_view(request):
    """Generate printable enrollment report"""
    selected_fields = request.GET.getlist('fields')
    if not selected_fields:
        selected_fields = [
            'student', 'class_instance', 'academic_session',
            'enrollment_date', 'enrollment_type', 'completion_status'
        ]
    
    include_stats = request.GET.get('include_stats') == 'true'
    landscape = request.GET.get('landscape') == 'true'
    
    enrollments = get_filtered_enrollments(request)
    
    stats = None
    if include_stats:
        stats = enrollments.aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(is_active=True, completion_status='ONGOING')),
            completed=Count('id', filter=Q(completion_status='COMPLETED')),
        )
    
    field_names = {
        'student': 'Student',
        'class_instance': 'Class',
        'academic_session': 'Session',
        'enrollment_date': 'Enrollment Date',
        'enrollment_type': 'Type',
        'completion_status': 'Status',
        'roll_number': 'Roll Number',
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
        'title': 'Student Enrollments Report',
    }
    
    return render(request, 'academics/enrollments/print.html', context)


@login_required
def export_enrollments_excel(request):
    """Export enrollments to Excel with filters applied"""
    enrollments = get_filtered_enrollments(request)
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Student Enrollments"
    
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_alignment = Alignment(horizontal="center", vertical="center")
    
    headers = [
        '#', 'Student', 'Class', 'Session', 'Enrollment Date',
        'Type', 'Status', 'Roll Number', 'Active'
    ]
    ws.append(headers)
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
    
    for idx, enrollment in enumerate(enrollments, start=1):
        ws.append([
            idx,
            enrollment.student.get_full_name(),
            str(enrollment.class_instance),
            str(enrollment.academic_session),
            enrollment.enrollment_date.strftime('%Y-%m-%d'),
            enrollment.get_enrollment_type_display(),
            enrollment.get_completion_status_display(),
            enrollment.roll_number or '',
            'Yes' if enrollment.is_active else 'No',
        ])
    
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
    
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"student_enrollments_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


# =============================================================================
# CLASS SUBJECT VIEWS
# =============================================================================

@login_required
def class_subject_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""
    filter_form = ClassSubjectFilterForm(request.GET or None)
    class_subjects = get_filtered_class_subjects(request)
    
    # Calculate statistics
    stats = {
        'total': class_subjects.count(),
        'with_teacher': class_subjects.filter(teacher__isnull=False).count(),
        'without_teacher': class_subjects.filter(teacher__isnull=True).count(),
    }
    
    # Pagination
    paginator = Paginator(class_subjects, 20)
    page_number = request.GET.get('page', 1)
    class_subjects_page = paginator.get_page(page_number)
    
    # Detect HTMX
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'class_subjects_page': class_subjects_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    if is_htmx:
        return render(request, 'academics/class_subjects/partials/_class_subject_results.html', context)
    else:
        return render(request, 'academics/class_subjects/list.html', context)


@login_required
def class_subject_detail(request, pk):
    """View class subject details"""
    class_subject = get_object_or_404(
        ClassSubject.objects.select_related(
            'class_instance__academic_level', 'class_instance__academic_session',
            'subject', 'teacher__staff'
        ),
        pk=pk
    )
    
    # Get enrolled students count
    enrolled_students_count = class_subject.class_instance.enrollments.filter(
        is_active=True,
        completion_status='ONGOING'
    ).count()
    
    context = {
        'class_subject': class_subject,
        'enrolled_students_count': enrolled_students_count,
    }
    
    return render(request, 'academics/class_subjects/detail.html', context)


@login_required
def class_subject_delete(request, pk):
    """Delete class subject with HTMX support"""
    class_subject = get_object_or_404(ClassSubject, pk=pk)
    
    if request.method == 'POST':
        # Check for grades
        try:
            if hasattr(class_subject, 'grades') and class_subject.grades.exists():
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = 'Cannot delete assignment with existing grades'
                    response['HX-Alert-Type'] = 'error'
                    response['HX-Close-Modal'] = 'true'
                    return response
                else:
                    messages.error(request, 'Cannot delete assignment with existing grades')
                    return redirect('academics:class_subject_detail', pk=pk)
        except:
            pass
        
        try:
            subject_name = class_subject.subject.name
            class_name = str(class_subject.class_instance)
            
            class_subject.delete()
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Subject "{subject_name}" removed from {class_name}'
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('academics:class_subject_list')
                return response
            else:
                messages.success(request, 'Subject assignment deleted successfully')
                return redirect('academics:class_subject_list')
                
        except Exception as e:
            logger.error(f"Error deleting class subject: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error deleting assignment: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error deleting assignment: {str(e)}')
                return redirect('academics:class_subject_detail', pk=pk)


@login_required
def class_subject_assign_teacher(request, pk):
    """Assign teacher to class subject with HTMX support"""
    class_subject = get_object_or_404(ClassSubject, pk=pk)
    
    if request.method == 'POST':
        teacher_id = request.POST.get('teacher_id')
        
        try:
            from hr.models import Teacher
            
            old_teacher = class_subject.teacher
            
            if teacher_id:
                teacher = get_object_or_404(Teacher, pk=teacher_id)
                class_subject.teacher = teacher
                message = f'Teacher {teacher.staff.full_name()} assigned to {class_subject.subject.name}'
                if old_teacher:
                    message += f' (replaced {old_teacher.staff.full_name()})'
            else:
                class_subject.teacher = None
                message = f'Teacher removed from {class_subject.subject.name}'
            
            class_subject.save()
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = message
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('academics:class_subject_detail', kwargs={'pk': pk})
                return response
            else:
                messages.success(request, message)
                return redirect('academics:class_subject_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error assigning teacher: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error assigning teacher: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error assigning teacher: {str(e)}')
                return redirect('academics:class_subject_detail', pk=pk)


@login_required
def class_subject_toggle_active(request, pk):
    """Toggle class subject active status with HTMX support"""
    class_subject = get_object_or_404(ClassSubject, pk=pk)
    
    if request.method == 'POST':
        try:
            old_status = class_subject.is_active
            class_subject.is_active = not old_status
            class_subject.save()
            
            status_text = 'activated' if class_subject.is_active else 'deactivated'
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Assignment {status_text} successfully'
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('academics:class_subject_detail', kwargs={'pk': pk})
                return response
            else:
                messages.success(request, f'Assignment {status_text}')
                return redirect('academics:class_subject_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error toggling status: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error changing status: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error changing status: {str(e)}')
                return redirect('academics:class_subject_detail', pk=pk)


@login_required
def class_subject_print_view(request):
    """Generate printable class subject list"""
    selected_fields = request.GET.getlist('fields')
    if not selected_fields:
        selected_fields = [
            'class_instance', 'subject', 'teacher',
            'hours_per_week', 'is_optional', 'is_active'
        ]
    
    include_stats = request.GET.get('include_stats') == 'true'
    landscape = request.GET.get('landscape') == 'true'
    
    class_subjects = get_filtered_class_subjects(request)
    
    stats = None
    if include_stats:
        stats = class_subjects.aggregate(
            total=Count('id'),
            with_teacher=Count('id', filter=Q(teacher__isnull=False)),
            without_teacher=Count('id', filter=Q(teacher__isnull=True)),
        )
    
    field_names = {
        'class_instance': 'Class',
        'subject': 'Subject',
        'teacher': 'Teacher',
        'hours_per_week': 'Hours/Week',
        'is_optional': 'Optional',
        'is_active': 'Active',
    }
    
    selected_field_names = [
        field_names.get(field, field.replace('_', ' ').title())
        for field in selected_fields
    ]
    
    context = {
        'class_subjects': class_subjects,
        'stats': stats,
        'now': timezone.now(),
        'selected_fields': selected_fields,
        'selected_field_names': selected_field_names,
        'field_names': field_names,
        'landscape': landscape,
        'title': 'Class Subjects Report',
    }
    
    return render(request, 'academics/class_subjects/print.html', context)


@login_required
def export_class_subjects_excel(request):
    """Export class subjects to Excel with filters applied"""
    class_subjects = get_filtered_class_subjects(request)
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Class Subjects"
    
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_alignment = Alignment(horizontal="center", vertical="center")
    
    headers = [
        '#', 'Class', 'Subject', 'Teacher', 'Hours/Week',
        'Optional', 'Active'
    ]
    ws.append(headers)
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
    
    for idx, cs in enumerate(class_subjects, start=1):
        ws.append([
            idx,
            str(cs.class_instance),
            cs.subject.name,
            cs.teacher.staff.full_name() if cs.teacher else '',
            cs.hours_per_week,
            'Yes' if cs.is_optional else 'No',
            'Yes' if cs.is_active else 'No',
        ])
    
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
    
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"class_subjects_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


# =============================================================================
# ACADEMIC PROGRESS VIEWS
# =============================================================================

@login_required
def academic_progress_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""
    filter_form = AcademicProgressFilterForm(request.GET or None)
    
    # Build queryset
    progress_records = AcademicProgress.objects.select_related(
        'student', 'academic_session', 'class_enrollment'
    ).order_by('-academic_session__start_date', 'student__last_name')
    
    # Apply filters (simplified for brevity - use helper function in production)
    query = request.GET.get('q', '').strip()
    if query:
        progress_records = progress_records.filter(
            Q(student__first_name__icontains=query) |
            Q(student__last_name__icontains=query)
        )
    
    # Calculate statistics
    stats = {
        'total': progress_records.count(),
        'finalized': progress_records.filter(is_final=True).count(),
        'eligible_for_promotion': progress_records.filter(is_eligible_for_promotion=True).count(),
    }
    
    # Pagination
    paginator = Paginator(progress_records, 20)
    page_number = request.GET.get('page', 1)
    progress_page = paginator.get_page(page_number)
    
    # Detect HTMX
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'progress_page': progress_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    if is_htmx:
        return render(request, 'academics/progress/partials/_progress_results.html', context)
    else:
        return render(request, 'academics/progress/list.html', context)


@login_required
def academic_progress_detail(request, pk):
    """View academic progress details"""
    progress = get_object_or_404(
        AcademicProgress.objects.select_related(
            'student', 'academic_session', 'class_enrollment'
        ),
        pk=pk
    )
    
    context = {
        'progress': progress,
    }
    
    return render(request, 'academics/progress/detail.html', context)


@login_required
def academic_progress_delete(request, pk):
    """Delete academic progress with HTMX support"""
    progress = get_object_or_404(AcademicProgress, pk=pk)
    
    if request.method == 'POST':
        if progress.is_final:
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = 'Cannot delete finalized progress records'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, 'Cannot delete finalized progress records')
                return redirect('academics:progress_detail', pk=pk)
        
        try:
            student_name = progress.student.get_full_name()
            session_name = str(progress.academic_session)
            
            progress.delete()
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = 'Progress record deleted successfully'
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('academics:progress_list')
                return response
            else:
                messages.success(request, 'Progress record deleted successfully')
                return redirect('academics:progress_list')
                
        except Exception as e:
            logger.error(f"Error deleting academic progress: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error deleting progress record: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error deleting progress record: {str(e)}')
                return redirect('academics:progress_detail', pk=pk)


@login_required
def academic_progress_finalize(request, pk):
    """Finalize academic progress with HTMX support"""
    progress = get_object_or_404(AcademicProgress, pk=pk)
    
    if request.method == 'POST':
        try:
            finalized = progress.finalize_record(user=request.user)
            
            if finalized:
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = 'Progress record finalized successfully'
                    response['HX-Alert-Type'] = 'success'
                    response['HX-Close-Modal'] = 'true'
                    response['HX-Redirect'] = reverse('academics:progress_detail', kwargs={'pk': pk})
                    return response
                else:
                    messages.success(request, 'Progress record finalized successfully')
                    return redirect('academics:progress_detail', pk=pk)
            else:
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = 'Progress record is already finalized'
                    response['HX-Alert-Type'] = 'warning'
                    response['HX-Close-Modal'] = 'true'
                    return response
                else:
                    messages.warning(request, 'Progress record is already finalized')
                    return redirect('academics:progress_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error finalizing progress: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error finalizing progress: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error finalizing progress: {str(e)}')
                return redirect('academics:progress_detail', pk=pk)


# =============================================================================
# HOLIDAY VIEWS
# =============================================================================

@login_required
def holiday_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""
    filter_form = HolidayFilterForm(request.GET or None)
    holidays = get_filtered_holidays(request)
    
    # Calculate statistics
    today = get_school_today()
    stats = {
        'total': holidays.count(),
        'school_closed': holidays.filter(is_school_closed=True).count(),
        'upcoming': holidays.filter(start_date__gte=today).count(),
    }
    
    # Pagination
    paginator = Paginator(holidays, 20)
    page_number = request.GET.get('page', 1)
    holidays_page = paginator.get_page(page_number)
    
    # Detect HTMX
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'holidays_page': holidays_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    if is_htmx:
        return render(request, 'academics/holidays/_holiday_results.html', context)
    else:
        return render(request, 'academics/holidays/list.html', context)


@login_required
def holiday_detail(request, pk):
    """View holiday details"""
    holiday = get_object_or_404(Holiday, pk=pk)
    
    # Calculate duration
    if holiday.end_date:
        duration = (holiday.end_date - holiday.start_date).days + 1
    else:
        duration = 1
    
    context = {
        'holiday': holiday,
        'duration': duration,
    }
    
    return render(request, 'academics/holidays/detail.html', context)


@login_required
def holiday_delete(request, pk):
    """Delete holiday with HTMX support"""
    holiday = get_object_or_404(Holiday, pk=pk)
    
    if request.method == 'POST':
        try:
            holiday_name = holiday.name
            holiday.delete()
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Holiday "{holiday_name}" deleted successfully'
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('academics:holiday_list')
                return response
            else:
                messages.success(request, f'Holiday "{holiday_name}" deleted successfully')
                return redirect('academics:holiday_list')
                
        except Exception as e:
            logger.error(f"Error deleting holiday: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error deleting holiday: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error deleting holiday: {str(e)}')
                return redirect('academics:holiday_detail', pk=pk)


@login_required
def holiday_print_view(request):
    """Generate printable holiday list"""
    selected_fields = request.GET.getlist('fields')
    if not selected_fields:
        selected_fields = ['name', 'holiday_type', 'start_date', 'end_date', 'is_school_closed']
    
    include_stats = request.GET.get('include_stats') == 'true'
    landscape = request.GET.get('landscape') == 'true'
    
    holidays = get_filtered_holidays(request)
    
    stats = None
    if include_stats:
        stats = {
            'total': holidays.count(),
            'school_closed': holidays.filter(is_school_closed=True).count(),
        }
    
    field_names = {
        'name': 'Holiday Name',
        'holiday_type': 'Type',
        'start_date': 'Start Date',
        'end_date': 'End Date',
        'is_school_closed': 'School Closed',
    }
    
    selected_field_names = [
        field_names.get(field, field.replace('_', ' ').title())
        for field in selected_fields
    ]
    
    context = {
        'holidays': holidays,
        'stats': stats,
        'now': timezone.now(),
        'selected_fields': selected_fields,
        'selected_field_names': selected_field_names,
        'field_names': field_names,
        'landscape': landscape,
        'title': 'Holidays Report',
    }
    
    return render(request, 'academics/holidays/print.html', context)


@login_required
def export_holidays_excel(request):
    """Export holidays to Excel with filters applied"""
    holidays = get_filtered_holidays(request)
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Holidays"
    
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_alignment = Alignment(horizontal="center", vertical="center")
    
    headers = [
        '#', 'Holiday Name', 'Type', 'Start Date', 'End Date',
        'Duration (Days)', 'School Closed', 'Recurring'
    ]
    ws.append(headers)
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
    
    for idx, holiday in enumerate(holidays, start=1):
        ws.append([
            idx,
            holiday.name,
            holiday.get_holiday_type_display(),
            holiday.start_date.strftime('%Y-%m-%d'),
            holiday.end_date.strftime('%Y-%m-%d') if holiday.end_date else holiday.start_date.strftime('%Y-%m-%d'),
            holiday.duration_days,
            'Yes' if holiday.is_school_closed else 'No',
            'Yes' if holiday.is_recurring else 'No',
        ])
    
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
    
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"holidays_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


# =============================================================================
# MISSING CRUD OPERATIONS (CREATE/EDIT)
# =============================================================================

@login_required
def academic_session_create(request):
    """Create new academic session with HTMX support"""
    if request.method == 'POST':
        form = AcademicSessionForm(request.POST)
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    session = form.save(commit=False)
                    session.save()
                    
                    is_htmx = request.headers.get('HX-Request') == 'true'
                    if is_htmx:
                        response = HttpResponse()
                        response['HX-Alert-Message'] = f'Session "{session.name}" created successfully'
                        response['HX-Alert-Type'] = 'success'
                        response['HX-Close-Modal'] = 'true'
                        response['HX-Redirect'] = reverse('academics:session_detail', kwargs={'pk': session.pk})
                        return response
                    else:
                        messages.success(request, f'Session "{session.name}" created successfully')
                        return redirect('academics:session_detail', pk=session.pk)
                        
            except Exception as e:
                logger.error(f"Error creating session: {e}")
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Error creating session: {str(e)}'
                    response['HX-Alert-Type'] = 'error'
                    return response
                else:
                    messages.error(request, f'Error creating session: {str(e)}')
        else:
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = 'Please correct the errors in the form'
                response['HX-Alert-Type'] = 'error'
                return response
            else:
                messages.error(request, 'Please correct the errors in the form')
    else:
        form = AcademicSessionForm()
    
    return render(request, 'academics/sessions/form.html', {
        'form': form,
        'title': 'Create Academic Session',
    })


@login_required
def academic_session_edit(request, pk):
    """Edit academic session with HTMX support"""
    session = get_object_or_404(AcademicSession, pk=pk)
    
    if request.method == 'POST':
        form = AcademicSessionForm(request.POST, instance=session)
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    session = form.save()
                    
                    is_htmx = request.headers.get('HX-Request') == 'true'
                    if is_htmx:
                        response = HttpResponse()
                        response['HX-Alert-Message'] = f'Session "{session.name}" updated successfully'
                        response['HX-Alert-Type'] = 'success'
                        response['HX-Close-Modal'] = 'true'
                        response['HX-Redirect'] = reverse('academics:session_detail', kwargs={'pk': session.pk})
                        return response
                    else:
                        messages.success(request, f'Session updated successfully')
                        return redirect('academics:session_detail', pk=session.pk)
                        
            except Exception as e:
                logger.error(f"Error updating session: {e}")
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Error updating session: {str(e)}'
                    response['HX-Alert-Type'] = 'error'
                    return response
                else:
                    messages.error(request, f'Error updating session: {str(e)}')
        else:
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = 'Please correct the errors in the form'
                response['HX-Alert-Type'] = 'error'
                return response
            else:
                messages.error(request, 'Please correct the errors in the form')
    else:
        form = AcademicSessionForm(instance=session)
    
    return render(request, 'academics/sessions/form.html', {
        'form': form,
        'session': session,
        'title': f'Edit {session.name}',
    })


@login_required
def academic_session_toggle_active(request, pk):
    """Toggle session active status with HTMX support"""
    session = get_object_or_404(AcademicSession, pk=pk)
    
    if request.method == 'POST':
        try:
            session.is_active = not session.is_active
            session.save(update_fields=['is_active'])
            
            status_text = 'activated' if session.is_active else 'deactivated'
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Session {status_text} successfully'
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('academics:session_detail', kwargs={'pk': pk})
                return response
            else:
                messages.success(request, f'Session {status_text}')
                return redirect('academics:session_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error toggling session status: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error updating status: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error updating status: {str(e)}')
                return redirect('academics:session_detail', pk=pk)


# Subject CRUD operations
@login_required
def subject_create(request):
    """Create new subject with HTMX support"""
    if request.method == 'POST':
        form = SubjectForm(request.POST)
        
        if form.is_valid():
            try:
                subject = form.save()
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Subject "{subject.name}" created successfully'
                    response['HX-Alert-Type'] = 'success'
                    response['HX-Close-Modal'] = 'true'
                    response['HX-Redirect'] = reverse('academics:subject_detail', kwargs={'pk': subject.pk})
                    return response
                else:
                    messages.success(request, f'Subject created successfully')
                    return redirect('academics:subject_detail', pk=subject.pk)
                    
            except Exception as e:
                logger.error(f"Error creating subject: {e}")
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Error creating subject: {str(e)}'
                    response['HX-Alert-Type'] = 'error'
                    return response
                else:
                    messages.error(request, f'Error: {str(e)}')
        else:
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = 'Please correct the errors in the form'
                response['HX-Alert-Type'] = 'error'
                return response
    else:
        form = SubjectForm()
    
    return render(request, 'academics/subjects/form.html', {
        'form': form,
        'title': 'Create Subject',
    })


@login_required
def subject_edit(request, pk):
    """Edit subject with HTMX support"""
    subject = get_object_or_404(Subject, pk=pk)
    
    if request.method == 'POST':
        form = SubjectForm(request.POST, instance=subject)
        
        if form.is_valid():
            try:
                subject = form.save()
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = 'Subject updated successfully'
                    response['HX-Alert-Type'] = 'success'
                    response['HX-Close-Modal'] = 'true'
                    response['HX-Redirect'] = reverse('academics:subject_detail', kwargs={'pk': subject.pk})
                    return response
                else:
                    messages.success(request, 'Subject updated successfully')
                    return redirect('academics:subject_detail', pk=subject.pk)
                    
            except Exception as e:
                logger.error(f"Error updating subject: {e}")
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Error: {str(e)}'
                    response['HX-Alert-Type'] = 'error'
                    return response
                else:
                    messages.error(request, f'Error: {str(e)}')
    else:
        form = SubjectForm(instance=subject)
    
    return render(request, 'academics/subjects/form.html', {
        'form': form,
        'subject': subject,
        'title': f'Edit {subject.name}',
    })


@login_required
def subject_toggle_active(request, pk):
    """Toggle subject active status"""
    subject = get_object_or_404(Subject, pk=pk)
    
    if request.method == 'POST':
        try:
            subject.is_active = not subject.is_active
            subject.save(update_fields=['is_active'])
            
            status_text = 'activated' if subject.is_active else 'deactivated'
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Subject {status_text} successfully'
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('academics:subject_detail', kwargs={'pk': pk})
                return response
            else:
                messages.success(request, f'Subject {status_text}')
                return redirect('academics:subject_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error toggling subject status: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error: {str(e)}')
                return redirect('academics:subject_detail', pk=pk)


@login_required
def subject_print_view(request):
    """Generate printable subject list"""
    selected_fields = request.GET.getlist('fields')
    if not selected_fields:
        selected_fields = ['name', 'code', 'subject_type', 'credit_hours', 'is_active']
    
    include_stats = request.GET.get('include_stats') == 'true'
    landscape = request.GET.get('landscape') == 'true'
    
    subjects = get_filtered_subjects(request)
    
    stats = None
    if include_stats:
        stats = {
            'total': subjects.count(),
            'active': subjects.filter(is_active=True).count(),
        }
    
    field_names = {
        'name': 'Subject Name',
        'code': 'Code',
        'subject_type': 'Type',
        'credit_hours': 'Credit Hours',
        'is_active': 'Active',
    }
    
    selected_field_names = [
        field_names.get(field, field.replace('_', ' ').title())
        for field in selected_fields
    ]
    
    context = {
        'subjects': subjects,
        'stats': stats,
        'now': timezone.now(),
        'selected_fields': selected_fields,
        'selected_field_names': selected_field_names,
        'field_names': field_names,
        'landscape': landscape,
        'title': 'Subjects Report',
    }
    
    return render(request, 'academics/subjects/print.html', context)


@login_required
def export_subjects_excel(request):
    """Export subjects to Excel with filters applied"""
    subjects = get_filtered_subjects(request)
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Subjects"
    
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_alignment = Alignment(horizontal="center", vertical="center")
    
    headers = ['#', 'Name', 'Code', 'Type', 'Credit Hours', 'Active']
    ws.append(headers)
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
    
    for idx, subject in enumerate(subjects, start=1):
        ws.append([
            idx,
            subject.name,
            subject.code,
            subject.get_subject_type_display(),
            subject.credit_hours,
            'Yes' if subject.is_active else 'No',
        ])
    
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
    
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"subjects_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


# Academic Level CRUD operations
@login_required
def academic_level_create(request):
    """Create new academic level"""
    if request.method == 'POST':
        form = AcademicLevelForm(request.POST)
        
        if form.is_valid():
            try:
                level = form.save()
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Level "{level.name}" created successfully'
                    response['HX-Alert-Type'] = 'success'
                    response['HX-Close-Modal'] = 'true'
                    response['HX-Redirect'] = reverse('academics:level_detail', kwargs={'pk': level.pk})
                    return response
                else:
                    messages.success(request, 'Level created successfully')
                    return redirect('academics:level_detail', pk=level.pk)
                    
            except Exception as e:
                logger.error(f"Error creating level: {e}")
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Error: {str(e)}'
                    response['HX-Alert-Type'] = 'error'
                    return response
                else:
                    messages.error(request, f'Error: {str(e)}')
    else:
        form = AcademicLevelForm()
    
    return render(request, 'academics/levels/form.html', {
        'form': form,
        'title': 'Create Academic Level',
    })


@login_required
def academic_level_edit(request, pk):
    """Edit academic level"""
    level = get_object_or_404(AcademicLevel, pk=pk)
    
    if request.method == 'POST':
        form = AcademicLevelForm(request.POST, instance=level)
        
        if form.is_valid():
            try:
                level = form.save()
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = 'Level updated successfully'
                    response['HX-Alert-Type'] = 'success'
                    response['HX-Close-Modal'] = 'true'
                    response['HX-Redirect'] = reverse('academics:level_detail', kwargs={'pk': level.pk})
                    return response
                else:
                    messages.success(request, 'Level updated successfully')
                    return redirect('academics:level_detail', pk=level.pk)
                    
            except Exception as e:
                logger.error(f"Error updating level: {e}")
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Error: {str(e)}'
                    response['HX-Alert-Type'] = 'error'
                    return response
                else:
                    messages.error(request, f'Error: {str(e)}')
    else:
        form = AcademicLevelForm(instance=level)
    
    return render(request, 'academics/levels/form.html', {
        'form': form,
        'level': level,
        'title': f'Edit {level.name}',
    })


@login_required
def academic_level_toggle_active(request, pk):
    """Toggle academic level active status"""
    level = get_object_or_404(AcademicLevel, pk=pk)
    
    if request.method == 'POST':
        try:
            level.is_active = not level.is_active
            level.save(update_fields=['is_active'])
            
            status_text = 'activated' if level.is_active else 'deactivated'
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Level {status_text} successfully'
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('academics:level_detail', kwargs={'pk': pk})
                return response
            else:
                messages.success(request, f'Level {status_text}')
                return redirect('academics:level_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error toggling level status: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error: {str(e)}')
                return redirect('academics:level_detail', pk=pk)


# Continue with remaining CRUD operations for other models...
# (Classroom, Class, Enrollment, ClassSubject, Progress, Holiday)
# Following the same pattern as above

# =============================================================================
# PLACEHOLDER STUBS FOR MISSING FUNCTIONS
# These need to be implemented following the patterns above
# =============================================================================

@login_required
def classroom_create(request):
    """Create new classroom with HTMX support"""
    if request.method == 'POST':
        form = ClassRoomForm(request.POST)
        
        if form.is_valid():
            try:
                classroom = form.save()
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Classroom "{classroom.name}" created successfully'
                    response['HX-Alert-Type'] = 'success'
                    response['HX-Close-Modal'] = 'true'
                    response['HX-Redirect'] = reverse('academics:classroom_detail', kwargs={'pk': classroom.pk})
                    return response
                else:
                    messages.success(request, f'Classroom "{classroom.name}" created successfully')
                    return redirect('academics:classroom_detail', pk=classroom.pk)
                    
            except Exception as e:
                logger.error(f"Error creating classroom: {e}")
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Error creating classroom: {str(e)}'
                    response['HX-Alert-Type'] = 'error'
                    return response
                else:
                    messages.error(request, f'Error creating classroom: {str(e)}')
        else:
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = 'Please correct the errors in the form'
                response['HX-Alert-Type'] = 'error'
                return response
    else:
        form = ClassRoomForm()
    
    return render(request, 'academics/classrooms/form.html', {
        'form': form,
        'title': 'Create Classroom',
    })


@login_required
def classroom_edit(request, pk):
    """Edit classroom with HTMX support"""
    classroom = get_object_or_404(ClassRoom, pk=pk)
    
    if request.method == 'POST':
        form = ClassRoomForm(request.POST, instance=classroom)
        
        if form.is_valid():
            try:
                classroom = form.save()
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Classroom "{classroom.name}" updated successfully'
                    response['HX-Alert-Type'] = 'success'
                    response['HX-Close-Modal'] = 'true'
                    response['HX-Redirect'] = reverse('academics:classroom_detail', kwargs={'pk': classroom.pk})
                    return response
                else:
                    messages.success(request, 'Classroom updated successfully')
                    return redirect('academics:classroom_detail', pk=classroom.pk)
                    
            except Exception as e:
                logger.error(f"Error updating classroom: {e}")
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Error updating classroom: {str(e)}'
                    response['HX-Alert-Type'] = 'error'
                    return response
                else:
                    messages.error(request, f'Error updating classroom: {str(e)}')
    else:
        form = ClassRoomForm(instance=classroom)
    
    return render(request, 'academics/classrooms/form.html', {
        'form': form,
        'classroom': classroom,
        'title': f'Edit {classroom.name}',
    })


@login_required
def classroom_toggle_active(request, pk):
    """Toggle classroom active status with HTMX support"""
    classroom = get_object_or_404(ClassRoom, pk=pk)
    
    if request.method == 'POST':
        try:
            classroom.is_active = not classroom.is_active
            classroom.save(update_fields=['is_active'])
            
            status_text = 'activated' if classroom.is_active else 'deactivated'
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Classroom {status_text} successfully'
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('academics:classroom_detail', kwargs={'pk': pk})
                return response
            else:
                messages.success(request, f'Classroom {status_text}')
                return redirect('academics:classroom_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error toggling classroom status: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error updating status: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error updating status: {str(e)}')
                return redirect('academics:classroom_detail', pk=pk)


@login_required
def classroom_toggle_bookable(request, pk):
    """Toggle classroom bookable status with HTMX support"""
    classroom = get_object_or_404(ClassRoom, pk=pk)
    
    if request.method == 'POST':
        try:
            classroom.is_bookable = not classroom.is_bookable
            classroom.save(update_fields=['is_bookable'])
            
            status_text = 'bookable' if classroom.is_bookable else 'not bookable'
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Classroom is now {status_text}'
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('academics:classroom_detail', kwargs={'pk': pk})
                return response
            else:
                messages.success(request, f'Classroom is now {status_text}')
                return redirect('academics:classroom_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error toggling classroom bookable status: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error updating status: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error updating status: {str(e)}')
                return redirect('academics:classroom_detail', pk=pk)


@login_required
def class_create(request):
    """Create new class with HTMX support"""
    if request.method == 'POST':
        form = ClassForm(request.POST)
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    class_instance = form.save()
                    
                    is_htmx = request.headers.get('HX-Request') == 'true'
                    if is_htmx:
                        response = HttpResponse()
                        response['HX-Alert-Message'] = f'Class "{class_instance}" created successfully'
                        response['HX-Alert-Type'] = 'success'
                        response['HX-Close-Modal'] = 'true'
                        response['HX-Redirect'] = reverse('academics:class_detail', kwargs={'pk': class_instance.pk})
                        return response
                    else:
                        messages.success(request, 'Class created successfully')
                        return redirect('academics:class_detail', pk=class_instance.pk)
                        
            except Exception as e:
                logger.error(f"Error creating class: {e}")
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Error creating class: {str(e)}'
                    response['HX-Alert-Type'] = 'error'
                    return response
                else:
                    messages.error(request, f'Error creating class: {str(e)}')
        else:
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = 'Please correct the errors in the form'
                response['HX-Alert-Type'] = 'error'
                return response
    else:
        form = ClassForm()
    
    return render(request, 'academics/classes/form.html', {
        'form': form,
        'title': 'Create Class',
    })


@login_required
def class_edit(request, pk):
    """Edit class with HTMX support"""
    class_instance = get_object_or_404(Class, pk=pk)
    
    if request.method == 'POST':
        form = ClassForm(request.POST, instance=class_instance)
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    class_instance = form.save()
                    
                    is_htmx = request.headers.get('HX-Request') == 'true'
                    if is_htmx:
                        response = HttpResponse()
                        response['HX-Alert-Message'] = 'Class updated successfully'
                        response['HX-Alert-Type'] = 'success'
                        response['HX-Close-Modal'] = 'true'
                        response['HX-Redirect'] = reverse('academics:class_detail', kwargs={'pk': class_instance.pk})
                        return response
                    else:
                        messages.success(request, 'Class updated successfully')
                        return redirect('academics:class_detail', pk=class_instance.pk)
                        
            except Exception as e:
                logger.error(f"Error updating class: {e}")
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Error updating class: {str(e)}'
                    response['HX-Alert-Type'] = 'error'
                    return response
                else:
                    messages.error(request, f'Error updating class: {str(e)}')
    else:
        form = ClassForm(instance=class_instance)
    
    return render(request, 'academics/classes/form.html', {
        'form': form,
        'class': class_instance,
        'title': f'Edit {class_instance}',
    })


@login_required
def class_toggle_active(request, pk):
    """Toggle class active status with HTMX support"""
    class_instance = get_object_or_404(Class, pk=pk)
    
    if request.method == 'POST':
        try:
            class_instance.is_active = not class_instance.is_active
            class_instance.save(update_fields=['is_active'])
            
            status_text = 'activated' if class_instance.is_active else 'deactivated'
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Class {status_text} successfully'
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('academics:class_detail', kwargs={'pk': pk})
                return response
            else:
                messages.success(request, f'Class {status_text}')
                return redirect('academics:class_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error toggling class status: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error updating status: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error updating status: {str(e)}')
                return redirect('academics:class_detail', pk=pk)


@login_required
def class_assign_teacher(request, pk):
    """Assign teacher to class with HTMX support"""
    class_instance = get_object_or_404(Class, pk=pk)
    
    if request.method == 'POST':
        try:
            teacher_id = request.POST.get('teacher_id')
            
            if teacher_id:
                from hr.models import Teacher
                teacher = get_object_or_404(Teacher, pk=teacher_id)
                
                old_teacher = class_instance.class_teacher
                class_instance.class_teacher = teacher
                class_instance.save(update_fields=['class_teacher'])
                
                message = f'Teacher {teacher.staff.full_name()} assigned to class'
                if old_teacher:
                    message += f' (replaced {old_teacher.staff.full_name()})'
            else:
                class_instance.class_teacher = None
                class_instance.save(update_fields=['class_teacher'])
                message = 'Teacher removed from class'
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = message
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('academics:class_detail', kwargs={'pk': pk})
                return response
            else:
                messages.success(request, message)
                return redirect('academics:class_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error assigning teacher: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error assigning teacher: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error assigning teacher: {str(e)}')
                return redirect('academics:class_detail', pk=pk)


@login_required
def class_assign_classroom(request, pk):
    """Assign classroom to class with HTMX support"""
    class_instance = get_object_or_404(Class, pk=pk)
    
    if request.method == 'POST':
        try:
            classroom_id = request.POST.get('classroom_id')
            
            if classroom_id:
                classroom = get_object_or_404(ClassRoom, pk=classroom_id)
                
                old_classroom = class_instance.classroom
                class_instance.classroom = classroom
                class_instance.save(update_fields=['classroom'])
                
                message = f'Classroom {classroom.name} assigned to class'
                if old_classroom:
                    message += f' (replaced {old_classroom.name})'
            else:
                class_instance.classroom = None
                class_instance.save(update_fields=['classroom'])
                message = 'Classroom removed from class'
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = message
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('academics:class_detail', kwargs={'pk': pk})
                return response
            else:
                messages.success(request, message)
                return redirect('academics:class_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error assigning classroom: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error assigning classroom: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error assigning classroom: {str(e)}')
                return redirect('academics:class_detail', pk=pk)


@login_required
def enrollment_create(request, student_pk=None, class_pk=None):
    """Create new enrollment with HTMX support"""
    # Pre-populate form if coming from student or class context
    initial = {}
    if student_pk:
        from students.models import Student
        student = get_object_or_404(Student, pk=student_pk)
        initial['student'] = student
    if class_pk:
        class_instance = get_object_or_404(Class, pk=class_pk)
        initial['class_instance'] = class_instance
    
    if request.method == 'POST':
        form = StudentEnrollmentForm(request.POST)
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    enrollment = form.save(commit=False)
                    
                    # Set enrollment date if not provided
                    if not enrollment.enrollment_date:
                        enrollment.enrollment_date = get_school_today()
                    
                    enrollment.save()
                    
                    # Log the auto-generated roll number
                    logger.info(
                        f"Created enrollment for {enrollment.student.get_full_name()} "
                        f"with roll number: {enrollment.roll_number}"
                    )
                    
                    is_htmx = request.headers.get('HX-Request') == 'true'
                    if is_htmx:
                        response = HttpResponse()
                        response['HX-Alert-Message'] = (
                            f'Enrollment created for {enrollment.student.get_full_name()} '
                            f'(Roll #: {enrollment.roll_number})'
                        )
                        response['HX-Alert-Type'] = 'success'
                        response['HX-Close-Modal'] = 'true'
                        response['HX-Redirect'] = reverse('academics:enrollment_detail', kwargs={'pk': enrollment.pk})
                        return response
                    else:
                        messages.success(
                            request, 
                            f'Enrollment created successfully (Roll Number: {enrollment.roll_number})',
                            extra_tags='sweetalert'
                        )
                        return redirect('academics:enrollment_detail', pk=enrollment.pk)
                        
            except ValidationError as e:
                # Handle validation errors (like duplicate enrollment)
                logger.error(f"Validation error creating enrollment: {e}")
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = str(e)
                    response['HX-Alert-Type'] = 'error'
                    return response
                else:
                    # Add errors to form for display
                    if hasattr(e, 'error_dict'):
                        for field, errors in e.error_dict.items():
                            form.add_error(field, errors)
                    else:
                        form.add_error(None, e)
                        
            except Exception as e:
                logger.error(f"Error creating enrollment: {e}", exc_info=True)
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Error creating enrollment: {str(e)}'
                    response['HX-Alert-Type'] = 'error'
                    return response
                else:
                    messages.error(request, f'Error creating enrollment: {str(e)}')
        else:
            # Form validation failed
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                # Collect all form errors
                error_messages = []
                for field, errors in form.errors.items():
                    for error in errors:
                        if field == '__all__':
                            error_messages.append(str(error))
                        else:
                            error_messages.append(f"{field}: {error}")
                
                response['HX-Alert-Message'] = ' | '.join(error_messages)
                response['HX-Alert-Type'] = 'error'
                return response
    else:
        form = StudentEnrollmentForm(initial=initial)
    
    context = {
        'form': form,
        'title': 'Create Enrollment',
        'submit_text': 'Enroll Student',
        'enrollment': None,
    }
    
    return render(request, 'academics/enrollments/form.html', context)


@login_required
def enrollment_edit(request, pk):
    """Edit enrollment with HTMX support"""
    enrollment = get_object_or_404(StudentClassEnrollment, pk=pk)
    
    if request.method == 'POST':
        form = StudentEnrollmentForm(request.POST, instance=enrollment)
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    enrollment = form.save()
                    
                    logger.info(
                        f"Updated enrollment for {enrollment.student.get_full_name()} "
                        f"(Roll #: {enrollment.roll_number})"
                    )
                    
                    is_htmx = request.headers.get('HX-Request') == 'true'
                    if is_htmx:
                        response = HttpResponse()
                        response['HX-Alert-Message'] = 'Enrollment updated successfully'
                        response['HX-Alert-Type'] = 'success'
                        response['HX-Close-Modal'] = 'true'
                        response['HX-Redirect'] = reverse('academics:enrollment_detail', kwargs={'pk': enrollment.pk})
                        return response
                    else:
                        messages.success(request, 'Enrollment updated successfully', extra_tags='sweetalert')
                        return redirect('academics:enrollment_detail', pk=enrollment.pk)
                        
            except ValidationError as e:
                logger.error(f"Validation error updating enrollment: {e}")
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = str(e)
                    response['HX-Alert-Type'] = 'error'
                    return response
                else:
                    if hasattr(e, 'error_dict'):
                        for field, errors in e.error_dict.items():
                            form.add_error(field, errors)
                    else:
                        form.add_error(None, e)
                        
            except Exception as e:
                logger.error(f"Error updating enrollment: {e}", exc_info=True)
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Error updating enrollment: {str(e)}'
                    response['HX-Alert-Type'] = 'error'
                    return response
                else:
                    messages.error(request, f'Error updating enrollment: {str(e)}')
        else:
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                error_messages = []
                for field, errors in form.errors.items():
                    for error in errors:
                        if field == '__all__':
                            error_messages.append(str(error))
                        else:
                            error_messages.append(f"{field}: {error}")
                
                response = HttpResponse()
                response['HX-Alert-Message'] = ' | '.join(error_messages)
                response['HX-Alert-Type'] = 'error'
                return response
    else:
        form = StudentEnrollmentForm(instance=enrollment)
    
    context = {
        'form': form,
        'enrollment': enrollment,
        'title': f'Edit Enrollment - {enrollment.student.get_full_name()}',
        'submit_text': 'Update Enrollment',
    }
    
    return render(request, 'academics/enrollments/form.html', context)


@login_required
def bulk_enrollment_create(request):
    """
    Bulk Enrollment - Step 1: Select students.
    
    Features:
    - HTMX-powered student filtering
    - Multi-select with checkboxes
    - Shows eligible students
    """
    # Get target class and session from query params
    class_id = request.GET.get('class_id')
    session_id = request.GET.get('session_id')
    
    target_class = None
    target_session = None
    
    if class_id:
        target_class = get_object_or_404(Class, pk=class_id)
        target_session = target_class.academic_session
    elif session_id:
        target_session = get_object_or_404(AcademicSession, pk=session_id)
    
    # Initialize filter form
    from students.models import Student
    form = BulkEnrollmentStudentSelectionForm(
        request.GET,
        academic_session=target_session,
        target_class=target_class
    ) if hasattr(globals(), 'BulkEnrollmentStudentSelectionForm') else None
    
    # Get filtered students
    if form and form.is_valid():
        students = form.get_filtered_queryset()
    else:
        # Default: Get active students not already enrolled in this class
        students = Student.objects.filter(enrollment_status='ACTIVE')
        
        if target_class:
            # Exclude already enrolled students
            enrolled_student_ids = StudentClassEnrollment.objects.filter(
                class_instance=target_class,
                academic_session=target_session
            ).values_list('student_id', flat=True)
            students = students.exclude(id__in=enrolled_student_ids)
        
        students = students.select_related(
            'current_academic_level', 'admission_academic_level'
        ).order_by('first_name', 'last_name')
    
    # Pagination
    paginator = Paginator(students, 50)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    context = {
        'form': form,
        'students': page_obj,
        'page_obj': page_obj,
        'target_class': target_class,
        'target_session': target_session,
        'title': 'Bulk Enrollment - Select Students',
    }
    
    return render(request, 'academics/enrollments/bulk_step1.html', context)


@login_required
def bulk_enrollment_student_search(request):
    """
    HTMX endpoint for live student search in the bulk enrollment wizard.
    Returns only the _student_selection_results.html partial.

    Parameter names match the BulkEnrollmentStudentSelectionForm field names:
        search                  — text search (name / admission number)
        current_level           — AcademicLevel PK
        enrollment_status       — Student.ENROLLMENT_STATUS_CHOICES value
        gender                  — Student.GENDER_CHOICES value
        exclude_already_enrolled — 'on' / absent
        show_only_eligible      — 'on' / absent
        sort_by                 — one of the sort_map keys below
        class_id                — hidden context field (passed via hx-include)
        session_id              — hidden context field (passed via hx-include)
        page                    — pagination page number
    """
    from students.models import Student

    # -------------------------------------------------------------------------
    # Base queryset
    # -------------------------------------------------------------------------
    students = Student.objects.select_related(
        'current_academic_level', 'admission_academic_level'
    )

    # -------------------------------------------------------------------------
    # Enrollment status  (default: ACTIVE)
    # -------------------------------------------------------------------------
    status = request.GET.get('enrollment_status', '').strip()
    if status:
        students = students.filter(enrollment_status=status)
    else:
        students = students.filter(enrollment_status='ACTIVE')

    # -------------------------------------------------------------------------
    # Text search — name or admission number
    # -------------------------------------------------------------------------
    query = request.GET.get('search', '').strip()
    if query:
        students = students.filter(
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(admission_number__icontains=query)
        )

    # -------------------------------------------------------------------------
    # Academic level filter
    # -------------------------------------------------------------------------
    level_id = request.GET.get('current_level', '').strip()
    if level_id:
        students = students.filter(current_academic_level_id=level_id)

    # -------------------------------------------------------------------------
    # Gender filter
    # -------------------------------------------------------------------------
    gender = request.GET.get('gender', '').strip()
    if gender:
        students = students.filter(gender=gender)

    # -------------------------------------------------------------------------
    # Exclude already-enrolled students
    # Checkbox sends 'on' when ticked; absent when unticked.
    # -------------------------------------------------------------------------
    exclude_enrolled = request.GET.get('exclude_already_enrolled')
    session_id = request.GET.get('session_id', '').strip()
    class_id   = request.GET.get('class_id', '').strip()

    if exclude_enrolled:
        # Exclude students with ANY active enrollment in the target session.
        # If a specific class is provided, scope to that class instead.
        enrollment_filter = {'completion_status': 'ONGOING'}

        if session_id:
            enrollment_filter['academic_session_id'] = session_id
        if class_id:
            enrollment_filter['class_instance_id'] = class_id

        if session_id or class_id:
            enrolled_ids = StudentClassEnrollment.objects.filter(
                **enrollment_filter
            ).values_list('student_id', flat=True)
            students = students.exclude(id__in=enrolled_ids)

    # -------------------------------------------------------------------------
    # Show only promotion-eligible students
    # -------------------------------------------------------------------------
    show_only_eligible = request.GET.get('show_only_eligible')
    if show_only_eligible:
        from academics.models import AcademicProgress
        eligible_ids = AcademicProgress.objects.filter(
            is_eligible_for_promotion=True
        ).values_list('student_id', flat=True)
        students = students.filter(id__in=eligible_ids)

    # -------------------------------------------------------------------------
    # Sorting
    # -------------------------------------------------------------------------
    sort_map = {
        'name'           : ('first_name', 'last_name'),
        '-name'          : ('-first_name', '-last_name'),
        'admission_number': ('admission_number',),
        '-admission_date': ('-admission_date',),
        'admission_date' : ('admission_date',),
    }
    sort_by = request.GET.get('sort_by', 'name').strip()
    students = students.order_by(*sort_map.get(sort_by, ('first_name', 'last_name')))

    # -------------------------------------------------------------------------
    # Pagination
    # -------------------------------------------------------------------------
    # Count before paginating so the footer shows the total correctly.
    total_count = students.count()

    paginator   = Paginator(students, 50)
    page_number = request.GET.get('page', 1)
    page_obj    = paginator.get_page(page_number)

    context = {
        'page_obj'   : page_obj,
        'total_count': total_count,
    }

    return render(
        request,
        'academics/enrollments/_student_selection_results.html',
        context,
    )


@login_required
def bulk_enrollment_step2(request):
    """
    Bulk Enrollment - Step 2: Review and confirm enrollment.

    Handles three distinct request scenarios:
    1. POST with 'student_ids' only → Step 1 handoff (render the form)
    2. POST with 'confirm_enrollment' → actual form submission
    3. GET → fallback/back-navigation (redirects if no student_ids)
    """
    from students.models import Student

    is_htmx = request.headers.get('HX-Request') == 'true'

    # =========================================================================
    # SCENARIO 1: Step 1 → Step 2 handoff (POST with student_ids, no confirm)
    # =========================================================================
    if request.method == 'POST' and 'student_ids' in request.POST and 'confirm_enrollment' not in request.POST:
        student_ids_str = request.POST.get('student_ids', '')
        class_id = request.POST.get('class_id')
        session_id = request.POST.get('session_id')

        if not student_ids_str:
            messages.error(request, 'No students selected. Please go back and select students.')
            return redirect('academics:bulk_enrollment_step1')

        ids = [id.strip() for id in student_ids_str.split(',') if id.strip()]
        student_count = Student.objects.filter(id__in=ids).count()

        initial = {'selected_student_ids': student_ids_str}

        if class_id:
            target_class = get_object_or_404(Class, pk=class_id)
            initial['class_instance'] = target_class
            initial['academic_session'] = target_class.academic_session
        elif session_id:
            initial['academic_session'] = get_object_or_404(AcademicSession, pk=session_id)

        form = BulkEnrollmentConfirmationForm(initial=initial, student_count=student_count)

        selected_students = Student.objects.filter(id__in=ids).select_related('current_academic_level')

        return render(request, 'academics/enrollments/bulk_step2.html', {
            'form': form,
            'selected_students': selected_students,
            'student_count': student_count,
            'title': 'Bulk Enrollment - Confirm',
        })

    # =========================================================================
    # SCENARIO 2: Actual form submission (POST with confirm_enrollment present)
    # =========================================================================
    if request.method == 'POST':
        form = BulkEnrollmentConfirmationForm(request.POST)

        if form.is_valid():
            try:
                result = execute_bulk_enrollment(form.cleaned_data, request.user)

                # Build success message from result breakdown
                parts = [f"Enrolled: {result['enrolled_count']}"]
                if result['skipped_count']:
                    parts.append(f"Skipped (already enrolled): {result['skipped_count']}")
                if result['invoice_count']:
                    parts.append(f"Invoices created: {result['invoice_count']}")
                success_message = ' | '.join(parts)

                # Build warning message if some failed
                warning_message = None
                if result['failed']:
                    failed_names = ', '.join(
                        f"{name} ({reason})" for name, reason in result['failed'][:5]
                    )
                    extra = f" and {len(result['failed']) - 5} more" if len(result['failed']) > 5 else ""
                    warning_message = f"Failed for {len(result['failed'])} student(s): {failed_names}{extra}"

                redirect_url = (
                    reverse('academics:enrollment_list') +
                    f'?class_instance={form.cleaned_data["class_instance"].pk}'
                )

                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = success_message
                    response['HX-Alert-Type'] = 'success' if result['enrolled_count'] > 0 else 'warning'
                    if warning_message:
                        response['HX-Alert-Warning'] = warning_message
                    response['HX-Close-Modal'] = 'true'
                    response['HX-Redirect'] = redirect_url
                    return response
                else:
                    messages.success(request, success_message, extra_tags='sweetalert')
                    if warning_message:
                        messages.warning(request, warning_message, extra_tags='sweetalert')
                    return redirect(redirect_url)

            except Exception as e:
                logger.error(f"Bulk enrollment failed: {e}", exc_info=True)

                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Bulk enrollment failed: {str(e)}'
                    response['HX-Alert-Type'] = 'error'
                    return response
                else:
                    messages.error(request, f'Bulk enrollment failed: {str(e)}')

        else:
            # Form validation failed - collect all errors for display
            if is_htmx:
                error_messages = []
                for field, errors in form.errors.items():
                    for error in errors:
                        if field == '__all__':
                            error_messages.append(str(error))
                        else:
                            error_messages.append(f"{field}: {error}")

                response = HttpResponse()
                response['HX-Alert-Message'] = ' | '.join(error_messages) or 'Please correct the errors in the form'
                response['HX-Alert-Type'] = 'error'
                return response
            else:
                messages.error(request, 'Please correct the errors below.')

        # Re-render form with errors (non-HTMX invalid submission)
        student_ids_str = form.data.get('selected_student_ids', '')
        ids = [id.strip() for id in student_ids_str.split(',') if id.strip()]
        selected_students = Student.objects.filter(id__in=ids).select_related('current_academic_level')

        return render(request, 'academics/enrollments/bulk_step2.html', {
            'form': form,
            'selected_students': selected_students,
            'student_count': len(ids),
            'title': 'Bulk Enrollment - Confirm',
        })

    # =========================================================================
    # SCENARIO 3: GET request — back navigation or direct URL access
    # =========================================================================
    student_ids_str = request.GET.get('student_ids', '')

    if not student_ids_str:
        messages.error(request, 'No students selected. Please go back and select students.')
        return redirect('academics:bulk_enrollment_step1')

    ids = [id.strip() for id in student_ids_str.split(',') if id.strip()]
    student_count = Student.objects.filter(id__in=ids).count()

    initial = {'selected_student_ids': student_ids_str}

    class_id = request.GET.get('class_id')
    session_id = request.GET.get('session_id')

    if class_id:
        target_class = get_object_or_404(Class, pk=class_id)
        initial['class_instance'] = target_class
        initial['academic_session'] = target_class.academic_session
    elif session_id:
        initial['academic_session'] = get_object_or_404(AcademicSession, pk=session_id)

    form = BulkEnrollmentConfirmationForm(initial=initial, student_count=student_count)
    selected_students = Student.objects.filter(id__in=ids).select_related('current_academic_level')

    return render(request, 'academics/enrollments/bulk_step2.html', {
        'form': form,
        'selected_students': selected_students,
        'student_count': student_count,
        'title': 'Bulk Enrollment - Confirm',
    })

def execute_bulk_enrollment(data, user):
    from students.models import Student

    enrolled_count = 0
    invoice_count = 0
    skipped_count = 0
    failed = []  # List of (student_name, error_message)

    student_ids_str = data.get('selected_student_ids', '')
    if isinstance(student_ids_str, str):
        student_ids = [id.strip() for id in student_ids_str.split(',') if id.strip()]
    else:
        student_ids = student_ids_str

    students = Student.objects.filter(id__in=student_ids).select_related('current_academic_level')

    academic_session = data['academic_session']
    class_instance = data['class_instance']
    enrollment_date = data.get('enrollment_date') or get_school_today()
    enrollment_type = data.get('enrollment_type', 'CONTINUING')
    auto_create_invoice = data.get('auto_create_invoice', True)

    for student in students:
        # Each student gets its own transaction so one failure doesn't affect others
        try:
            with transaction.atomic():
                existing = StudentClassEnrollment.objects.filter(
                    student=student,
                    academic_session=academic_session,
                    class_instance=class_instance
                ).exists()

                if existing:
                    skipped_count += 1
                    continue

                enrollment = StudentClassEnrollment.objects.create(
                    student=student,
                    academic_session=academic_session,
                    class_instance=class_instance,
                    enrollment_date=enrollment_date,
                    enrollment_type=enrollment_type,
                    auto_create_invoice=auto_create_invoice,
                    is_active=True,
                    completion_status='ONGOING',
                    enrollment_notes=data.get('enrollment_notes', '')
                )

                enrolled_count += 1

                if enrollment.academic_invoice:
                    invoice_count += 1

        except ValidationError as e:
            failed.append((student.get_full_name(), str(e)))
            logger.error(f"Validation error enrolling {student.get_full_name()}: {e}")
        except Exception as e:
            failed.append((student.get_full_name(), str(e)))
            logger.error(f"Failed to enroll {student.get_full_name()}: {e}", exc_info=True)

    logger.info(
        f"Bulk enrollment: {enrolled_count} enrolled, {invoice_count} invoices, "
        f"{skipped_count} skipped, {len(failed)} failed"
    )

    return {
        'enrolled_count': enrolled_count,
        'invoice_count': invoice_count,
        'skipped_count': skipped_count,
        'failed': failed,  # List of (name, reason) tuples
    }

@login_required
def bulk_enrollment_update_status(request):
    """Bulk update enrollment status with HTMX support"""
    if request.method == 'POST':
        try:
            enrollment_ids = request.POST.getlist('enrollment_ids')
            new_status = request.POST.get('new_status')
            
            if not enrollment_ids or not new_status:
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = 'Missing required fields'
                    response['HX-Alert-Type'] = 'error'
                    return response
                else:
                    messages.error(request, 'Missing required fields')
                    return redirect('academics:enrollment_list')
            
            updated_count = StudentClassEnrollment.objects.filter(
                pk__in=enrollment_ids
            ).update(completion_status=new_status)
            
            message = f'Updated status for {updated_count} enrollment(s)'
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = message
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('academics:enrollment_list')
                return response
            else:
                messages.success(request, message)
                return redirect('academics:enrollment_list')
                
        except Exception as e:
            logger.error(f"Error in bulk status update: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error: {str(e)}')
                return redirect('academics:enrollment_list')
    
    return redirect('academics:enrollment_list')


@login_required
def bulk_assign_roll_numbers(request):
    """Bulk assign roll numbers with HTMX support"""
    if request.method == 'POST':
        try:
            class_id = request.POST.get('class_id')
            session_id = request.POST.get('session_id')
            starting_number = int(request.POST.get('starting_number', 1))
            
            if not class_id or not session_id:
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = 'Missing required fields'
                    response['HX-Alert-Type'] = 'error'
                    return response
                else:
                    messages.error(request, 'Missing required fields')
                    return redirect('academics:enrollment_list')
            
            enrollments = StudentClassEnrollment.objects.filter(
                class_instance_id=class_id,
                academic_session_id=session_id,
                is_active=True,
                roll_number__isnull=True
            ).order_by('student__last_name', 'student__first_name')
            
            with transaction.atomic():
                current_number = starting_number
                for enrollment in enrollments:
                    enrollment.roll_number = str(current_number).zfill(3)
                    enrollment.save(update_fields=['roll_number'])
                    current_number += 1
            
            count = enrollments.count()
            message = f'Assigned roll numbers to {count} student(s)'
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = message
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('academics:enrollment_list')
                return response
            else:
                messages.success(request, message)
                return redirect('academics:enrollment_list')
                
        except Exception as e:
            logger.error(f"Error in bulk roll number assignment: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error: {str(e)}')
                return redirect('academics:enrollment_list')
    
    return redirect('academics:enrollment_list')


@login_required
def class_subject_create(request, class_pk=None):
    """Create class subject assignment with HTMX support"""
    initial = {}
    if class_pk:
        class_instance = get_object_or_404(Class, pk=class_pk)
        initial['class_instance'] = class_instance
    
    if request.method == 'POST':
        form = ClassSubjectForm(request.POST)
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    class_subject = form.save()
                    
                    is_htmx = request.headers.get('HX-Request') == 'true'
                    if is_htmx:
                        response = HttpResponse()
                        response['HX-Alert-Message'] = f'Subject "{class_subject.subject.name}" assigned to class'
                        response['HX-Alert-Type'] = 'success'
                        response['HX-Close-Modal'] = 'true'
                        response['HX-Redirect'] = reverse('academics:class_subject_detail', kwargs={'pk': class_subject.pk})
                        return response
                    else:
                        messages.success(request, 'Subject assigned successfully')
                        return redirect('academics:class_subject_detail', pk=class_subject.pk)
                        
            except Exception as e:
                logger.error(f"Error creating class subject: {e}")
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Error: {str(e)}'
                    response['HX-Alert-Type'] = 'error'
                    return response
                else:
                    messages.error(request, f'Error: {str(e)}')
        else:
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = 'Please correct the errors in the form'
                response['HX-Alert-Type'] = 'error'
                return response
    else:
        form = ClassSubjectForm(initial=initial)
    
    return render(request, 'academics/class_subjects/form.html', {
        'form': form,
        'title': 'Assign Subject to Class',
    })


@login_required
def class_subject_edit(request, pk):
    """Edit class subject with HTMX support"""
    class_subject = get_object_or_404(ClassSubject, pk=pk)
    
    if request.method == 'POST':
        form = ClassSubjectForm(request.POST, instance=class_subject)
        
        if form.is_valid():
            try:
                class_subject = form.save()
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = 'Subject assignment updated successfully'
                    response['HX-Alert-Type'] = 'success'
                    response['HX-Close-Modal'] = 'true'
                    response['HX-Redirect'] = reverse('academics:class_subject_detail', kwargs={'pk': class_subject.pk})
                    return response
                else:
                    messages.success(request, 'Subject assignment updated successfully')
                    return redirect('academics:class_subject_detail', pk=class_subject.pk)
                    
            except Exception as e:
                logger.error(f"Error updating class subject: {e}")
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Error: {str(e)}'
                    response['HX-Alert-Type'] = 'error'
                    return response
                else:
                    messages.error(request, f'Error: {str(e)}')
    else:
        form = ClassSubjectForm(instance=class_subject)
    
    return render(request, 'academics/class_subjects/form.html', {
        'form': form,
        'class_subject': class_subject,
        'title': 'Edit Subject Assignment',
    })


@login_required
def bulk_class_subject_assign(request):
    """
    Bulk assign multiple subjects to a single class.
    This is the recommended way to set up a new class.
    
    Features:
    - Assign multiple subjects at once
    - Set default hours per week
    - Set assessment weights
    - Mark subjects as optional
    - Skip existing assignments
    """
    
    if request.method == 'POST':
        form = BulkClassSubjectForm(request.POST)
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    cleaned_data = form.cleaned_data
                    
                    class_instance = cleaned_data['class_instance']
                    subjects = cleaned_data['subjects']
                    skip_existing = cleaned_data.get('skip_existing', True)
                    
                    created_count = 0
                    skipped_count = 0
                    
                    for subject in subjects:
                        # Check if already exists
                        if skip_existing:
                            existing = ClassSubject.objects.filter(
                                class_instance=class_instance,
                                subject=subject
                            ).exists()
                            
                            if existing:
                                skipped_count += 1
                                continue
                        
                        # Create new assignment
                        ClassSubject.objects.create(
                            class_instance=class_instance,
                            subject=subject,
                            is_optional=cleaned_data.get('mark_all_optional', False),
                            hours_per_week=cleaned_data.get('default_hours_per_week', 0),
                            total_hours=cleaned_data.get('default_total_hours', 0),
                            continuous_assessment_weight=cleaned_data.get('continuous_assessment_weight', 40),
                            final_exam_weight=cleaned_data.get('final_exam_weight', 60),
                            is_active=True
                        )
                        created_count += 1
                    
                    # Success message
                    message = f'Successfully assigned {created_count} subject(s) to {class_instance}.'
                    if skipped_count > 0:
                        message += f' Skipped {skipped_count} existing assignment(s).'
                    
                    # Check if HTMX request
                    is_htmx = request.headers.get('HX-Request') == 'true'
                    if is_htmx:
                        response = HttpResponse()
                        response['HX-Alert-Message'] = message
                        response['HX-Alert-Type'] = 'success'
                        response['HX-Close-Modal'] = 'true'
                        response['HX-Redirect'] = reverse('academics:class_detail', kwargs={'pk': class_instance.pk})
                        return response
                    else:
                        messages.success(request, message)
                        return redirect('academics:class_detail', pk=class_instance.pk)
                    
            except Exception as e:
                logger.error(f"Error in bulk subject assignment: {e}")
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Error assigning subjects: {str(e)}'
                    response['HX-Alert-Type'] = 'error'
                    return response
                else:
                    messages.error(request, f'Error assigning subjects: {str(e)}')
        else:
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = 'Please correct the errors in the form'
                response['HX-Alert-Type'] = 'error'
                return response
            else:
                messages.error(request, 'Please correct the errors in the form')
    else:
        # Pre-populate class if provided in URL
        class_id = request.GET.get('class_id')
        initial = {}
        
        if class_id:
            try:
                initial_class = Class.objects.get(pk=class_id)
                initial['class_instance'] = initial_class
                
                # Get academic level to suggest subjects
                if initial_class.academic_level:
                    # Could pre-populate subjects based on level curriculum
                    pass
                    
            except Class.DoesNotExist:
                pass
        
        form = BulkClassSubjectForm(initial=initial)
    
    context = {
        'form': form,
        'title': 'Bulk Assign Subjects to Class',
        'submit_text': 'Assign Subjects',
    }
    
    return render(request, 'academics/class_subjects/bulk_assign_form.html', context)


@login_required
def bulk_class_subject_assign_to_multiple(request):
    """
    Bulk assign subject(s) to multiple classes.
    Useful for assigning common subjects across classes.
    """
    if request.method == 'POST':
        try:
            class_ids = request.POST.getlist('class_ids')
            subject_ids = request.POST.getlist('subject_ids')
            skip_existing = request.POST.get('skip_existing', 'true') == 'true'
            hours_per_week = request.POST.get('hours_per_week', 0)
            
            if not class_ids or not subject_ids:
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = 'Please select classes and subjects'
                    response['HX-Alert-Type'] = 'error'
                    return response
                else:
                    messages.error(request, 'Please select classes and subjects')
                    return redirect('academics:class_subject_list')
            
            created_count = 0
            skipped_count = 0
            
            with transaction.atomic():
                for class_id in class_ids:
                    class_instance = get_object_or_404(Class, pk=class_id)
                    
                    for subject_id in subject_ids:
                        subject = get_object_or_404(Subject, pk=subject_id)
                        
                        # Check if already exists
                        existing = ClassSubject.objects.filter(
                            class_instance=class_instance,
                            subject=subject
                        ).exists()
                        
                        if existing:
                            if skip_existing:
                                skipped_count += 1
                                continue
                            else:
                                # Update existing
                                ClassSubject.objects.filter(
                                    class_instance=class_instance,
                                    subject=subject
                                ).update(
                                    hours_per_week=hours_per_week,
                                    is_active=True
                                )
                                continue
                        
                        # Create assignment
                        ClassSubject.objects.create(
                            class_instance=class_instance,
                            subject=subject,
                            hours_per_week=hours_per_week,
                            is_active=True
                        )
                        created_count += 1
            
            message = f'Created {created_count} assignment(s)'
            if skipped_count > 0:
                message += f', skipped {skipped_count} duplicate(s)'
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = message
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('academics:class_subject_list')
                return response
            else:
                messages.success(request, message)
                return redirect('academics:class_subject_list')
                
        except Exception as e:
            logger.error(f"Error in bulk assignment: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error: {str(e)}')
                return redirect('academics:class_subject_list')
    
    return redirect('academics:class_subject_list')


@login_required
def bulk_assign_subject_teachers(request):
    """Bulk assign teachers to subject assignments"""
    if request.method == 'POST':
        try:
            class_subject_ids = request.POST.getlist('class_subject_ids')
            teacher_id = request.POST.get('teacher_id')
            
            if not class_subject_ids or not teacher_id:
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = 'Please select assignments and a teacher'
                    response['HX-Alert-Type'] = 'error'
                    return response
                else:
                    messages.error(request, 'Please select assignments and a teacher')
                    return redirect('academics:class_subject_list')
            
            from hr.models import Teacher
            teacher = get_object_or_404(Teacher, pk=teacher_id)
            
            updated_count = ClassSubject.objects.filter(
                pk__in=class_subject_ids
            ).update(teacher=teacher)
            
            message = f'Assigned teacher to {updated_count} subject(s)'
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = message
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('academics:class_subject_list')
                return response
            else:
                messages.success(request, message)
                return redirect('academics:class_subject_list')
                
        except Exception as e:
            logger.error(f"Error in bulk teacher assignment: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error: {str(e)}')
                return redirect('academics:class_subject_list')
    
    return redirect('academics:class_subject_list')


# Academic Progress operations
@login_required
def academic_progress_create(request, student_pk=None):
    """Create academic progress record"""
    initial = {}
    if student_pk:
        from students.models import Student
        student = get_object_or_404(Student, pk=student_pk)
        initial['student'] = student
    
    if request.method == 'POST':
        form = AcademicProgressForm(request.POST)
        
        if form.is_valid():
            try:
                progress = form.save()
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = 'Progress record created successfully'
                    response['HX-Alert-Type'] = 'success'
                    response['HX-Close-Modal'] = 'true'
                    response['HX-Redirect'] = reverse('academics:progress_detail', kwargs={'pk': progress.pk})
                    return response
                else:
                    messages.success(request, 'Progress record created successfully')
                    return redirect('academics:progress_detail', pk=progress.pk)
                    
            except Exception as e:
                logger.error(f"Error creating progress: {e}")
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Error: {str(e)}'
                    response['HX-Alert-Type'] = 'error'
                    return response
                else:
                    messages.error(request, f'Error: {str(e)}')
    else:
        form = AcademicProgressForm(initial=initial)
    
    return render(request, 'academics/progress/form.html', {
        'form': form,
        'title': 'Create Progress Record',
    })


@login_required
def academic_progress_edit(request, pk):
    """Edit academic progress"""
    progress = get_object_or_404(AcademicProgress, pk=pk)
    
    if progress.is_final:
        messages.error(request, 'Cannot edit finalized progress records')
        return redirect('academics:progress_detail', pk=pk)
    
    if request.method == 'POST':
        form = AcademicProgressForm(request.POST, instance=progress)
        
        if form.is_valid():
            try:
                progress = form.save()
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = 'Progress record updated successfully'
                    response['HX-Alert-Type'] = 'success'
                    response['HX-Close-Modal'] = 'true'
                    response['HX-Redirect'] = reverse('academics:progress_detail', kwargs={'pk': progress.pk})
                    return response
                else:
                    messages.success(request, 'Progress record updated successfully')
                    return redirect('academics:progress_detail', pk=progress.pk)
                    
            except Exception as e:
                logger.error(f"Error updating progress: {e}")
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Error: {str(e)}'
                    response['HX-Alert-Type'] = 'error'
                    return response
                else:
                    messages.error(request, f'Error: {str(e)}')
    else:
        form = AcademicProgressForm(instance=progress)
    
    return render(request, 'academics/progress/form.html', {
        'form': form,
        'progress': progress,
        'title': 'Edit Progress Record',
    })


@login_required
def academic_progress_update_promotion(request, pk):
    """Update promotion decision"""
    progress = get_object_or_404(AcademicProgress, pk=pk)
    
    if request.method == 'POST':
        try:
            promotion_decision = request.POST.get('promotion_decision')
            
            if not promotion_decision:
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = 'Please select a promotion decision'
                    response['HX-Alert-Type'] = 'error'
                    return response
                else:
                    messages.error(request, 'Please select a promotion decision')
                    return redirect('academics:progress_detail', pk=pk)
            
            progress.promotion_decision = promotion_decision
            
            # Update eligibility based on decision
            if promotion_decision in ['PROMOTED', 'PROMOTED_WITH_CONDITIONS']:
                progress.is_eligible_for_promotion = True
            elif promotion_decision in ['RETAINED', 'FAILED']:
                progress.is_eligible_for_promotion = False
            
            progress.save()
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = 'Promotion decision updated successfully'
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('academics:progress_detail', kwargs={'pk': pk})
                return response
            else:
                messages.success(request, 'Promotion decision updated successfully')
                return redirect('academics:progress_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error updating promotion: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error: {str(e)}')
                return redirect('academics:progress_detail', pk=pk)
    
    return redirect('academics:progress_detail', pk=pk)


@login_required
def promote_student(request):
    """
    Single student promotion page with search.
    
    GET: Show form with student search
    POST: Execute promotion for selected student
    """
    from students.models import Student
    
    if request.method == 'POST':
        student_id = request.POST.get('student_id')
        next_level_id = request.POST.get('next_level')
        complete_current_enrollment = request.POST.get('complete_current_enrollment') == 'true'
        completion_date = request.POST.get('completion_date') or get_school_today()
        
        if not student_id or not next_level_id:
            messages.error(request, 'Please select a student and target academic level')
            return redirect('academics:promote_student')
        
        try:
            student = get_object_or_404(Student, pk=student_id)
            next_level = get_object_or_404(AcademicLevel, pk=next_level_id)
            
            with transaction.atomic():
                # Complete current enrollment if requested
                if complete_current_enrollment:
                    current_enrollments = StudentClassEnrollment.objects.filter(
                        student=student,
                        is_active=True,
                        completion_status='ONGOING'
                    )
                    
                    for enrollment in current_enrollments:
                        enrollment.completion_status = 'COMPLETED'
                        enrollment.completion_date = completion_date
                        enrollment.is_active = False
                        enrollment.save()
                
                # Update student's academic level
                old_level = student.current_academic_level
                student.current_academic_level = next_level
                student.save(update_fields=['current_academic_level'])
                
                message = (
                    f'{student.get_full_name()} promoted from '
                    f'{old_level.name if old_level else "N/A"} to {next_level.name}'
                )
                messages.success(request, message)
                return redirect('academics:promote_student')
                
        except Exception as e:
            logger.error(f"Error promoting student: {e}")
            messages.error(request, f'Promotion failed: {str(e)}')
            return redirect('academics:promote_student')
    
    # GET request - show form with search
    
    # Handle student search
    search_query = request.GET.get('search', '')
    level_filter = request.GET.get('level', '')
    status_filter = request.GET.get('status', 'ACTIVE')
    
    students = Student.objects.all()
    
    # Apply filters
    if search_query:
        students = students.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(admission_number__icontains=search_query)
        )
    
    if level_filter:
        students = students.filter(current_academic_level_id=level_filter)
    
    if status_filter:
        students = students.filter(enrollment_status=status_filter)
    
    # Order by name
    students = students.select_related('current_academic_level').order_by('first_name', 'last_name')
    
    # Get selected student details if student_id in GET params
    selected_student = None
    student_id = request.GET.get('student_id')
    if student_id:
        try:
            selected_student = Student.objects.select_related('current_academic_level').get(pk=student_id)
            # Get current enrollment
            current_enrollment = StudentClassEnrollment.objects.filter(
                student=selected_student,
                is_active=True,
                completion_status='ONGOING'
            ).select_related('class_instance', 'academic_session').first()
            
            # Get suggested next level
            current_level = selected_student.current_academic_level
            next_level = None
            if current_level and hasattr(current_level, 'order_number'):
                next_level = AcademicLevel.objects.filter(
                    order_number=current_level.order_number + 1,
                    is_active=True
                ).first()
        except Student.DoesNotExist:
            messages.error(request, 'Student not found')
    
    # Get all levels for selection
    available_levels = AcademicLevel.objects.filter(is_active=True).order_by('name')
    
    # Get levels for filter dropdown
    all_levels = AcademicLevel.objects.filter(is_active=True).order_by('name')
    
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(students, 25)
    page_number = request.GET.get('page')
    students_page = paginator.get_page(page_number)
    
    context = {
        'students': students_page,
        'selected_student': selected_student,
        'current_enrollment': current_enrollment if selected_student else None,
        'next_level': next_level if selected_student else None,
        'available_levels': available_levels,
        'all_levels': all_levels,
        'search_query': search_query,
        'level_filter': level_filter,
        'status_filter': status_filter,
        'title': 'Promote Student',
    }
    
    return render(request, 'academics/promotions/promote_student.html', context)


@login_required
def bulk_promote_students(request):
    """
    Bulk student promotion page with advanced search and filtering.
    
    GET: Show form with student search/filter
    POST: Execute bulk promotion for selected students
    """
    if request.method == 'POST':
        try:
            student_ids = request.POST.getlist('student_ids')
            next_level_id = request.POST.get('next_level')
            complete_enrollments = request.POST.get('complete_enrollments') == 'true'
            completion_date = request.POST.get('completion_date') or get_school_today()
            
            if not student_ids:
                messages.error(request, 'Please select at least one student')
                return redirect('academics:bulk_promote_students')
            
            if not next_level_id:
                messages.error(request, 'Please select target academic level')
                return redirect('academics:bulk_promote_students')
            
            next_level = get_object_or_404(AcademicLevel, pk=next_level_id)
            
            from students.models import Student
            students = Student.objects.filter(id__in=student_ids)
            
            promoted_count = 0
            errors = []
            
            with transaction.atomic():
                for student in students:
                    try:
                        # Complete current enrollments if requested
                        if complete_enrollments:
                            current_enrollments = StudentClassEnrollment.objects.filter(
                                student=student,
                                is_active=True,
                                completion_status='ONGOING'
                            )
                            
                            for enrollment in current_enrollments:
                                enrollment.completion_status = 'COMPLETED'
                                enrollment.completion_date = completion_date
                                enrollment.is_active = False
                                enrollment.save()
                        
                        # Update academic level
                        student.current_academic_level = next_level
                        student.save(update_fields=['current_academic_level'])
                        
                        promoted_count += 1
                        
                    except Exception as e:
                        logger.error(f"Error promoting {student}: {e}")
                        errors.append(f"{student.get_full_name()}: {str(e)}")
            
            message = f'Successfully promoted {promoted_count} student(s) to {next_level.name}'
            if errors:
                message += f'. {len(errors)} error(s) occurred'
                messages.warning(request, message)
            else:
                messages.success(request, message)
                
            return redirect('academics:bulk_promote_students')
                
        except Exception as e:
            logger.error(f"Bulk promotion error: {e}")
            messages.error(request, f'Bulk promotion failed: {str(e)}')
            return redirect('academics:bulk_promote_students')
    
    # GET request - show form with advanced filters
    
    # Get filter parameters
    search_query = request.GET.get('search', '')
    level_filter = request.GET.get('level', '')
    class_filter = request.GET.get('class', '')
    status_filter = request.GET.get('status', 'ACTIVE')
    session_filter = request.GET.get('session', '')
    eligible_only = request.GET.get('eligible_only') == 'true'
    
    from students.models import Student
    students = Student.objects.all()
    
    # Apply filters
    if search_query:
        students = students.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(admission_number__icontains=search_query)
        )
    
    if level_filter:
        students = students.filter(current_academic_level_id=level_filter)
    
    if status_filter:
        students = students.filter(enrollment_status=status_filter)
    
    if class_filter:
        # Filter by current class enrollment
        students = students.filter(
            enrollments__class_instance_id=class_filter,
            enrollments__is_active=True,
            enrollments__completion_status='ONGOING'
        ).distinct()
    
    if session_filter:
        # Filter by session
        students = students.filter(
            enrollments__academic_session_id=session_filter,
            enrollments__is_active=True,
            enrollments__completion_status='ONGOING'
        ).distinct()
    
    if eligible_only:
        # Filter by promotion eligibility
        current_session = AcademicSession.objects.filter(is_current=True).first()
        if current_session:
            eligible_student_ids = AcademicProgress.objects.filter(
                academic_session=current_session,
                is_eligible_for_promotion=True
            ).values_list('student_id', flat=True)
            students = students.filter(id__in=eligible_student_ids)
    
    # Select related for efficiency
    students = students.select_related('current_academic_level').order_by(
        'current_academic_level__name', 'first_name', 'last_name'
    )
    
    # Get filter options
    all_levels = AcademicLevel.objects.filter(is_active=True).order_by('name')
    all_classes = Class.objects.filter(is_active=True).select_related(
        'academic_level', 'academic_session'
    ).order_by('academic_level__name', 'academic_session__start_date')
    all_sessions = AcademicSession.objects.filter(is_active=True).order_by('-start_date')
    
    # Get target levels for promotion
    target_levels = AcademicLevel.objects.filter(is_active=True).order_by('name')
    
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(students, 50)
    page_number = request.GET.get('page')
    students_page = paginator.get_page(page_number)
    
    # Group students by current level for better display
    from collections import defaultdict
    students_by_level = defaultdict(list)
    for student in students_page:
        level_name = student.current_academic_level.name if student.current_academic_level else 'No Level'
        students_by_level[level_name].append(student)
    
    context = {
        'students': students_page,
        'students_by_level': dict(students_by_level),
        'all_levels': all_levels,
        'all_classes': all_classes,
        'all_sessions': all_sessions,
        'target_levels': target_levels,
        'search_query': search_query,
        'level_filter': level_filter,
        'class_filter': class_filter,
        'status_filter': status_filter,
        'session_filter': session_filter,
        'eligible_only': eligible_only,
        'total_count': students.count(),
        'title': 'Bulk Promote Students',
    }
    
    return render(request, 'academics/promotions/bulk_promote.html', context)


@login_required
def promotion_dashboard(request):
    """
    Dashboard for managing student promotions.
    
    Shows:
    - Students eligible for promotion
    - Promotion statistics by level
    - Quick actions
    """
    # Get current session
    current_session = AcademicSession.objects.filter(
        is_current=True
    ).first()
    
    # Get eligible students (those marked as eligible in progress)
    eligible_students = []
    if current_session:
        eligible_progress = AcademicProgress.objects.filter(
            academic_session=current_session,
            is_eligible_for_promotion=True,
            promotion_decision__in=['PROMOTED', 'PROMOTED_WITH_CONDITIONS']
        ).select_related('student', 'class_enrollment__class_instance__academic_level')
        
        eligible_students = [
            {
                'student': p.student,
                'current_level': p.class_enrollment.class_instance.academic_level if p.class_enrollment else None,
                'progress': p,
            }
            for p in eligible_progress
        ]
    
    # Get statistics by level
    from django.db.models import Count, Q
    from students.models import Student
    
    level_stats = []
    for level in AcademicLevel.objects.filter(is_active=True).order_by('name'):
        students_at_level = Student.objects.filter(
            current_academic_level=level,
            enrollment_status='ACTIVE'
        ).count()
        
        eligible_at_level = 0
        if current_session:
            eligible_at_level = AcademicProgress.objects.filter(
                student__current_academic_level=level,
                academic_session=current_session,
                is_eligible_for_promotion=True
            ).count()
        
        level_stats.append({
            'level': level,
            'total_students': students_at_level,
            'eligible_for_promotion': eligible_at_level,
        })
    
    context = {
        'current_session': current_session,
        'eligible_students': eligible_students,
        'level_stats': level_stats,
        'title': 'Student Promotions',
    }
    
    return render(request, 'academics/promotions/dashboard.html', context)


@login_required
def bulk_progress_finalize(request):
    """Bulk finalize progress records"""
    if request.method == 'POST':
        try:
            progress_ids = request.POST.getlist('progress_ids')
            
            if not progress_ids:
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = 'Please select progress records'
                    response['HX-Alert-Type'] = 'error'
                    return response
                else:
                    messages.error(request, 'Please select progress records')
                    return redirect('academics:progress_list')
            
            finalized_count = 0
            
            with transaction.atomic():
                for progress_id in progress_ids:
                    progress = get_object_or_404(AcademicProgress, pk=progress_id)
                    
                    if not progress.is_final:
                        if progress.finalize_record(user=request.user):
                            finalized_count += 1
            
            message = f'Finalized {finalized_count} progress record(s)'
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = message
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('academics:progress_list')
                return response
            else:
                messages.success(request, message)
                return redirect('academics:progress_list')
                
        except Exception as e:
            logger.error(f"Error in bulk finalization: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error: {str(e)}')
                return redirect('academics:progress_list')
    
    return redirect('academics:progress_list')


@login_required
def bulk_progress_calculate(request):
    """Bulk calculate progress metrics"""
    if request.method == 'POST':
        try:
            progress_ids = request.POST.getlist('progress_ids')
            
            if not progress_ids:
                messages.error(request, 'Please select progress records')
                return redirect('academics:progress_list')
            
            calculated_count = 0
            
            with transaction.atomic():
                for progress_id in progress_ids:
                    progress = get_object_or_404(AcademicProgress, pk=progress_id)
                    
                    if hasattr(progress, 'calculate_metrics'):
                        progress.calculate_metrics()
                        calculated_count += 1
            
            messages.success(request, f'Calculated metrics for {calculated_count} record(s)')
            return redirect('academics:progress_list')
                
        except Exception as e:
            logger.error(f"Error in bulk calculation: {e}")
            messages.error(request, f'Error: {str(e)}')
            return redirect('academics:progress_list')
    
    return redirect('academics:progress_list')


@login_required
def academic_progress_report_card(request, pk):
    """Generate student report card"""
    progress = get_object_or_404(AcademicProgress, pk=pk)
    
    context = {
        'progress': progress,
        'student': progress.student,
        'session': progress.academic_session,
        'enrollment': progress.class_enrollment,
    }
    
    return render(request, 'academics/progress/report_card.html', context)


@login_required
def academic_progress_list_print_view(request):
    """Print progress list - alias for academic_progress_list with print param"""
    return render(request, 'academics/progress/print_list.html', {
        'progress_records': AcademicProgress.objects.all()[:100],
        'title': 'Academic Progress Report',
    })


@login_required
def export_academic_progress_excel(request):
    """Export academic progress to Excel"""
    progress_records = AcademicProgress.objects.select_related(
        'student', 'academic_session'
    ).order_by('-academic_session__start_date', 'student__last_name')[:1000]
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Academic Progress"
    
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    
    headers = ['#', 'Student', 'Session', 'GPA', 'Attendance %', 'Promotion Decision', 'Final']
    ws.append(headers)
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
    
    for idx, progress in enumerate(progress_records, start=1):
        ws.append([
            idx,
            progress.student.get_full_name(),
            str(progress.academic_session),
            progress.gpa if progress.gpa else '',
            progress.attendance_percentage if progress.attendance_percentage else '',
            progress.get_promotion_decision_display() if progress.promotion_decision else '',
            'Yes' if progress.is_final else 'No',
        ])
    
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
    
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"academic_progress_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


# Holiday CRUD operations
@login_required
def holiday_create(request):
    """Create new holiday"""
    if request.method == 'POST':
        form = HolidayForm(request.POST)
        
        if form.is_valid():
            try:
                holiday = form.save()
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Holiday "{holiday.name}" created successfully'
                    response['HX-Alert-Type'] = 'success'
                    response['HX-Close-Modal'] = 'true'
                    response['HX-Redirect'] = reverse('academics:holiday_detail', kwargs={'pk': holiday.pk})
                    return response
                else:
                    messages.success(request, 'Holiday created successfully')
                    return redirect('academics:holiday_detail', pk=holiday.pk)
                    
            except Exception as e:
                logger.error(f"Error creating holiday: {e}")
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Error: {str(e)}'
                    response['HX-Alert-Type'] = 'error'
                    return response
                else:
                    messages.error(request, f'Error: {str(e)}')
    else:
        form = HolidayForm()
    
    return render(request, 'academics/holidays/form.html', {
        'form': form,
        'title': 'Create Holiday',
    })


@login_required
def holiday_edit(request, pk):
    """Edit holiday"""
    holiday = get_object_or_404(Holiday, pk=pk)
    
    if request.method == 'POST':
        form = HolidayForm(request.POST, instance=holiday)
        
        if form.is_valid():
            try:
                holiday = form.save()
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = 'Holiday updated successfully'
                    response['HX-Alert-Type'] = 'success'
                    response['HX-Close-Modal'] = 'true'
                    response['HX-Redirect'] = reverse('academics:holiday_detail', kwargs={'pk': holiday.pk})
                    return response
                else:
                    messages.success(request, 'Holiday updated successfully')
                    return redirect('academics:holiday_detail', pk=holiday.pk)
                    
            except Exception as e:
                logger.error(f"Error updating holiday: {e}")
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Error: {str(e)}'
                    response['HX-Alert-Type'] = 'error'
                    return response
                else:
                    messages.error(request, f'Error: {str(e)}')
    else:
        form = HolidayForm(instance=holiday)
    
    return render(request, 'academics/holidays/form.html', {
        'form': form,
        'holiday': holiday,
        'title': f'Edit {holiday.name}',
    })


@login_required
def export_holidays_calendar(request):
    """Export holidays calendar (iCal format)"""
    try:
        from icalendar import Calendar, Event
    except ImportError:
        # Fallback if icalendar not installed
        messages.error(request, 'Calendar export requires icalendar package')
        return redirect('academics:holiday_list')
    
    holidays = Holiday.objects.filter(is_active=True).order_by('start_date')
    
    cal = Calendar()
    cal.add('prodid', '-//Academic Calendar//EN')
    cal.add('version', '2.0')
    
    for holiday in holidays:
        event = Event()
        event.add('summary', holiday.name)
        event.add('dtstart', holiday.start_date)
        
        if holiday.end_date:
            event.add('dtend', holiday.end_date)
        else:
            event.add('dtend', holiday.start_date)
        
        if holiday.description:
            event.add('description', holiday.description)
        
        cal.add_component(event)
    
    response = HttpResponse(cal.to_ical(), content_type='text/calendar')
    response['Content-Disposition'] = f'attachment; filename="holidays_{datetime.now().strftime("%Y%m%d")}.ics"'
    
    return response


# =============================================================================
# INDIVIDUAL ITEM PRINT VIEWS
# =============================================================================

@login_required
def academic_session_print_detail(request, pk):
    """Print detailed view of single academic session"""
    session = get_object_or_404(AcademicSession, pk=pk)
    
    # Get related statistics
    classes = session.classes.select_related('academic_level').filter(is_active=True)
    enrollments = session.student_class_enrollments.select_related('student', 'class_instance')
    
    # Group enrollments by class
    from collections import defaultdict
    enrollments_by_class = defaultdict(list)
    for enrollment in enrollments:
        enrollments_by_class[enrollment.class_instance].append(enrollment)
    
    stats = {
        'total_classes': classes.count(),
        'total_enrollments': enrollments.count(),
        'active_enrollments': enrollments.filter(is_active=True, completion_status='ONGOING').count(),
        'completed_enrollments': enrollments.filter(completion_status='COMPLETED').count(),
        'male_students': enrollments.filter(student__gender='M').count(),
        'female_students': enrollments.filter(student__gender='F').count(),
    }
    
    # Get subjects being taught
    subjects_taught = ClassSubject.objects.filter(
        class_instance__academic_session=session,
        is_active=True
    ).select_related('subject').values_list('subject__name', flat=True).distinct()
    
    context = {
        'session': session,
        'classes': classes,
        'enrollments_by_class': dict(enrollments_by_class),
        'stats': stats,
        'subjects_taught': list(subjects_taught),
        'now': timezone.now(),
        'title': f'Academic Session: {session.name}',
    }
    
    return render(request, 'academics/sessions/print_detail.html', context)


@login_required
def subject_print_detail(request, pk):
    """Print detailed view of single subject"""
    subject = get_object_or_404(Subject, pk=pk)
    
    # Get classes teaching this subject
    class_assignments = ClassSubject.objects.filter(
        subject=subject,
        is_active=True
    ).select_related('class_instance', 'teacher__staff')
    
    # Get statistics
    stats = {
        'total_classes': class_assignments.count(),
        'with_teacher': class_assignments.filter(teacher__isnull=False).count(),
        'without_teacher': class_assignments.filter(teacher__isnull=True).count(),
        'total_students': sum(
            cs.class_instance.get_current_enrollment_count() 
            for cs in class_assignments
        ),
    }
    
    context = {
        'subject': subject,
        'class_assignments': class_assignments,
        'stats': stats,
        'now': timezone.now(),
        'title': f'Subject: {subject.name}',
    }
    
    return render(request, 'academics/subjects/print_detail.html', context)


@login_required
def academic_level_print_detail(request, pk):
    """Print detailed view of single academic level"""
    level = get_object_or_404(AcademicLevel, pk=pk)
    
    # Get classes at this level
    classes = level.classes.select_related('academic_session').filter(is_active=True)
    
    # Get students at this level
    from students.models import Student
    students = Student.objects.filter(
        current_academic_level=level,
        enrollment_status='ACTIVE'
    )
    
    stats = {
        'total_classes': classes.count(),
        'total_students': students.count(),
        'male_students': students.filter(gender='M').count(),
        'female_students': students.filter(gender='F').count(),
    }
    
    context = {
        'level': level,
        'classes': classes,
        'students': students[:50],  # Limit for print
        'stats': stats,
        'now': timezone.now(),
        'title': f'Academic Level: {level.name}',
    }
    
    return render(request, 'academics/levels/print_detail.html', context)


@login_required
def classroom_print_detail(request, pk):
    """Print detailed view of single classroom"""
    classroom = get_object_or_404(ClassRoom, pk=pk)
    
    # Get classes using this classroom
    classes = classroom.assigned_classes.select_related(
        'academic_level', 'academic_session'
    ).filter(is_active=True)
    
    # Calculate utilization
    total_capacity = classroom.capacity
    current_students = sum(cls.get_current_enrollment_count() for cls in classes)
    utilization = round((current_students / total_capacity * 100), 1) if total_capacity > 0 else 0
    
    stats = {
        'total_capacity': total_capacity,
        'current_students': current_students,
        'available_capacity': max(0, total_capacity - current_students),
        'utilization_percentage': utilization,
        'assigned_classes': classes.count(),
    }
    
    context = {
        'classroom': classroom,
        'classes': classes,
        'stats': stats,
        'now': timezone.now(),
        'title': f'Classroom: {classroom.name}',
    }
    
    return render(request, 'academics/classrooms/print_detail.html', context)


@login_required
def class_print_detail(request, pk):
    """Print detailed view of single class"""
    class_instance = get_object_or_404(
        Class.objects.select_related(
            'academic_level', 'academic_session', 'class_teacher', 'classroom'
        ),
        pk=pk
    )
    
    # Get enrollments
    enrollments = class_instance.enrollments.select_related('student').filter(
        is_active=True,
        completion_status='ONGOING'
    ).order_by('roll_number', 'student__last_name')
    
    # Get subjects
    subjects = class_instance.subjects.select_related('subject', 'teacher__staff').filter(
        is_active=True
    )
    
    # Calculate statistics
    male_students = enrollments.filter(student__gender='M').count()
    female_students = enrollments.filter(student__gender='F').count()
    
    stats = {
        'total_students': enrollments.count(),
        'male_students': male_students,
        'female_students': female_students,
        'total_subjects': subjects.count(),
        'compulsory_subjects': subjects.filter(is_optional=False).count(),
        'optional_subjects': subjects.filter(is_optional=True).count(),
        'capacity_used': round((enrollments.count() / class_instance.max_students * 100), 1) if class_instance.max_students > 0 else 0,
    }
    
    context = {
        'class': class_instance,
        'enrollments': enrollments,
        'subjects': subjects,
        'stats': stats,
        'now': timezone.now(),
        'title': f'Class: {class_instance}',
    }
    
    return render(request, 'academics/classes/print_detail.html', context)


@login_required
def enrollment_print_detail(request, pk):
    """Print detailed view of single enrollment"""
    enrollment = get_object_or_404(
        StudentClassEnrollment.objects.select_related(
            'student', 'class_instance', 'academic_session', 'academic_invoice'
        ),
        pk=pk
    )
    
    # Get enrollment history
    enrollment_history = StudentClassEnrollment.objects.filter(
        student=enrollment.student
    ).select_related('class_instance', 'academic_session').order_by('-enrollment_date')
    
    # Get progress if exists
    progress = None
    try:
        progress = AcademicProgress.objects.filter(
            student=enrollment.student,
            academic_session=enrollment.academic_session
        ).first()
    except:
        pass
    
    context = {
        'enrollment': enrollment,
        'enrollment_history': enrollment_history,
        'progress': progress,
        'now': timezone.now(),
        'title': f'Enrollment: {enrollment.student.get_full_name()}',
    }
    
    return render(request, 'academics/enrollments/print_detail.html', context)


@login_required
def class_subject_print_detail(request, pk):
    """Print detailed view of single class subject assignment"""
    class_subject = get_object_or_404(
        ClassSubject.objects.select_related(
            'class_instance__academic_level', 'subject', 'teacher__staff'
        ),
        pk=pk
    )
    
    # Get enrolled students
    enrolled_students = class_subject.class_instance.enrollments.select_related('student').filter(
        is_active=True,
        completion_status='ONGOING'
    )
    
    stats = {
        'enrolled_students': enrolled_students.count(),
        'total_hours': class_subject.total_hours or (class_subject.hours_per_week * 40 if class_subject.hours_per_week else 0),
        'hours_per_week': class_subject.hours_per_week,
    }
    
    context = {
        'class_subject': class_subject,
        'enrolled_students': enrolled_students,
        'stats': stats,
        'now': timezone.now(),
        'title': f'{class_subject.subject.name} - {class_subject.class_instance}',
    }
    
    return render(request, 'academics/class_subjects/print_detail.html', context)


@login_required
def academic_progress_print_detail(request, pk):
    """Print detailed view of single academic progress record"""
    progress = get_object_or_404(
        AcademicProgress.objects.select_related(
            'student', 'academic_session', 'class_enrollment'
        ),
        pk=pk
    )
    
    # Get enrollment details
    enrollment = progress.class_enrollment
    
    # Get subject grades if they exist
    subject_grades = []
    try:
        # This would connect to a grades model if it exists
        pass
    except:
        pass
    
    context = {
        'progress': progress,
        'enrollment': enrollment,
        'subject_grades': subject_grades,
        'now': timezone.now(),
        'title': f'Progress Report: {progress.student.get_full_name()}',
    }
    
    return render(request, 'academics/progress/print_detail.html', context)


@login_required
def holiday_print_detail(request, pk):
    """Print detailed view of single holiday"""
    holiday = get_object_or_404(Holiday, pk=pk)
    
    # Calculate duration
    duration = holiday.duration_days
    
    # Check if it affects any sessions
    affected_sessions = AcademicSession.objects.filter(
        start_date__lte=holiday.end_date or holiday.start_date,
        end_date__gte=holiday.start_date,
        is_active=True
    )
    
    context = {
        'holiday': holiday,
        'duration': duration,
        'affected_sessions': affected_sessions,
        'now': timezone.now(),
        'title': f'Holiday: {holiday.name}',
    }
    
    return render(request, 'academics/holidays/print_detail.html', context)


# Report generation views
@login_required
def session_summary_report(request):
    """Session summary report"""
    session_id = request.GET.get('session_id')
    
    if not session_id:
        messages.error(request, 'Please select a session')
        return redirect('academics:dashboard')
    
    session = get_object_or_404(AcademicSession, pk=session_id)
    
    # Get statistics
    classes = Class.objects.filter(academic_session=session)
    enrollments = StudentClassEnrollment.objects.filter(academic_session=session)
    
    stats = {
        'total_classes': classes.count(),
        'total_enrollments': enrollments.count(),
        'active_enrollments': enrollments.filter(is_active=True).count(),
        'completed_enrollments': enrollments.filter(completion_status='COMPLETED').count(),
    }
    
    context = {
        'session': session,
        'classes': classes,
        'stats': stats,
    }
    
    return render(request, 'academics/reports/session_summary.html', context)


@login_required
def enrollment_report(request):
    """Enrollment report"""
    session_id = request.GET.get('session_id')
    level_id = request.GET.get('level_id')
    
    enrollments = StudentClassEnrollment.objects.select_related(
        'student', 'class_instance', 'academic_session'
    )
    
    if session_id:
        enrollments = enrollments.filter(academic_session_id=session_id)
    if level_id:
        enrollments = enrollments.filter(class_instance__academic_level_id=level_id)
    
    # Group by level
    from django.db.models import Count
    by_level = enrollments.values(
        'class_instance__academic_level__name'
    ).annotate(
        total=Count('id')
    )
    
    context = {
        'enrollments': enrollments[:100],
        'by_level': by_level,
    }
    
    return render(request, 'academics/reports/enrollment.html', context)


@login_required
def class_roster_report(request, class_pk):
    """Class roster report"""
    class_instance = get_object_or_404(Class, pk=class_pk)
    
    enrollments = class_instance.enrollments.select_related('student').filter(
        is_active=True,
        completion_status='ONGOING'
    ).order_by('roll_number', 'student__last_name')
    
    context = {
        'class': class_instance,
        'enrollments': enrollments,
    }
    
    return render(request, 'academics/reports/class_roster.html', context)


@login_required
def teacher_assignment_report(request):
    """Teacher assignment report"""
    session_id = request.GET.get('session_id')
    
    class_subjects = ClassSubject.objects.select_related(
        'class_instance', 'subject', 'teacher__staff'
    ).filter(is_active=True)
    
    if session_id:
        class_subjects = class_subjects.filter(class_instance__academic_session_id=session_id)
    
    # Group by teacher
    from django.db.models import Count
    by_teacher = class_subjects.values(
        'teacher__staff__first_name',
        'teacher__staff__last_name'
    ).annotate(
        total_assignments=Count('id')
    )
    
    context = {
        'class_subjects': class_subjects[:100],
        'by_teacher': by_teacher,
    }
    
    return render(request, 'academics/reports/teacher_assignment.html', context)


# Calendar and utility views
@login_required
def academic_calendar(request, year=None, month=None):
    """Academic calendar view"""
    from calendar import monthcalendar, month_name
    
    if not year or not month:
        today = get_school_today()
        year = today.year
        month = today.month
    
    # Get holidays for this month
    holidays = Holiday.objects.filter(
        start_date__year=year,
        start_date__month=month
    )
    
    # Get calendar data
    cal = monthcalendar(year, month)
    
    context = {
        'year': year,
        'month': month,
        'month_name': month_name[month],
        'calendar': cal,
        'holidays': holidays,
    }
    
    return render(request, 'academics/calendar/view.html', context)


# AJAX endpoints
@login_required
def ajax_get_subjects_for_level(request, level_pk):
    """Get subjects for a level"""
    from django.http import JsonResponse
    
    try:
        level = get_object_or_404(AcademicLevel, pk=level_pk)
        
        # Get subjects typically taught at this level
        subjects = Subject.objects.filter(is_active=True).values('id', 'name', 'code')
        
        return JsonResponse({
            'success': True,
            'subjects': list(subjects)
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
def ajax_get_classes_for_session(request, session_pk):
    """Get classes for a session"""
    from django.http import JsonResponse
    
    try:
        session = get_object_or_404(AcademicSession, pk=session_pk)
        
        classes = Class.objects.filter(
            academic_session=session,
            is_active=True
        ).select_related('academic_level').values(
            'id', 'academic_level__name', 'section'
        )
        
        # Format class names
        class_list = []
        for cls in classes:
            name = cls['academic_level__name']
            if cls['section']:
                name += f" - {cls['section']}"
            class_list.append({
                'id': cls['id'],
                'name': name
            })
        
        return JsonResponse({
            'success': True,
            'classes': class_list
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
def ajax_get_next_roll_number(request, class_pk):
    """Get next roll number for class"""
    from django.http import JsonResponse
    
    try:
        class_instance = get_object_or_404(Class, pk=class_pk)
        
        # Get the highest roll number
        last_enrollment = StudentClassEnrollment.objects.filter(
            class_instance=class_instance
        ).exclude(roll_number__isnull=True).order_by('-roll_number').first()
        
        if last_enrollment and last_enrollment.roll_number:
            try:
                next_number = int(last_enrollment.roll_number) + 1
            except ValueError:
                next_number = 1
        else:
            next_number = 1
        
        return JsonResponse({
            'success': True,
            'next_roll_number': str(next_number).zfill(3)
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
def ajax_check_enrollment_duplicate(request):
    """Check for duplicate enrollment"""
    from django.http import JsonResponse
    
    try:
        student_id = request.GET.get('student_id')
        class_id = request.GET.get('class_id')
        session_id = request.GET.get('session_id')
        
        if not all([student_id, class_id, session_id]):
            return JsonResponse({
                'success': False,
                'error': 'Missing required parameters'
            }, status=400)
        
        exists = StudentClassEnrollment.objects.filter(
            student_id=student_id,
            class_instance_id=class_id,
            academic_session_id=session_id
        ).exists()
        
        return JsonResponse({
            'success': True,
            'is_duplicate': exists
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
def ajax_get_class_subjects(request, class_pk):
    """Get subjects for a class"""
    from django.http import JsonResponse
    
    try:
        class_instance = get_object_or_404(Class, pk=class_pk)
        
        subjects = ClassSubject.objects.filter(
            class_instance=class_instance,
            is_active=True
        ).select_related('subject', 'teacher__staff').values(
            'id', 'subject__name', 'subject__code',
            'teacher__staff__first_name', 'teacher__staff__last_name',
            'is_optional'
        )
        
        subject_list = []
        for subj in subjects:
            teacher_name = ''
            if subj['teacher__staff__first_name']:
                teacher_name = f"{subj['teacher__staff__first_name']} {subj['teacher__staff__last_name']}"
            
            subject_list.append({
                'id': subj['id'],
                'name': subj['subject__name'],
                'code': subj['subject__code'],
                'teacher': teacher_name,
                'is_optional': subj['is_optional']
            })
        
        return JsonResponse({
            'success': True,
            'subjects': subject_list
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)