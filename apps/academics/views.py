# academics/views.py

"""
Academic Management Views

Comprehensive view functions for:
- Academic Sessions Management (CRUD + Print)
- Subjects and Academic Levels (CRUD + Print)
- Classes and Classrooms (CRUD + Print)
- Student Class Enrollments (CRUD + Print)
- Academic Progress Tracking (CRUD + Print)
- Holidays Management (CRUD + Print)
- Class Subjects Management (CRUD + Print)
- Reports and Analytics

All views delegate business logic to services.py
Uses stats.py for comprehensive statistics and analytics
Uses SweetAlert2 for all notifications via Django messages
Uses core.utils for timezone-aware operations
Audit trail automatically handled by BaseModel
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count, Sum, Avg, Prefetch, F
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from django.db import transaction
from django.core.files.storage import FileSystemStorage
from datetime import timedelta, date, datetime
from decimal import Decimal
import os
import logging

# ⭐ Import timezone utilities from core (no need for log_user_action - BaseModel handles it)
from core.utils import (
    get_school_today,
    get_school_current_time,
    get_school_timezone,
    localize_datetime,
    get_academic_session_by_date,
    get_active_academic_session,
    format_money,
    calculate_percentage,
    validate_date_range,
    paginate_queryset,
    parse_filters,
)

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from io import BytesIO

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
    AcademicSessionForm,
    AcademicSessionFilterForm,
    SubjectForm,
    SubjectFilterForm,
    AcademicLevelForm,
    AcademicLevelFilterForm,
    ClassRoomForm,
    ClassRoomFilterForm,
    ClassForm,
    ClassFilterForm,
    StudentClassEnrollmentForm,
    StudentClassEnrollmentFilterForm,
    BulkEnrollmentForm,
    ClassSubjectForm,
    ClassSubjectFilterForm,
    AcademicProgressForm,
    AcademicProgressFilterForm,
    HolidayForm,
    HolidayFilterForm,
)

# Import stats functions
from . import stats as academic_stats

logger = logging.getLogger(__name__)


# =============================================================================
# DASHBOARD
# =============================================================================

@login_required
def academics_dashboard(request):
    """Main academics dashboard with overview statistics - USES stats.py"""
    
    try:
        # Use comprehensive overview from stats.py
        overview = academic_stats.get_academic_dashboard_statistics()
        
        # Get current session info
        current_session = academic_stats.get_current_academic_session()
        
        # Get additional statistics for charts and widgets
        today = timezone.now().date()
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
    
    # Get recent activities (limited queries for display)
    recent_sessions = AcademicSession.objects.order_by('-created_at')[:10]
    recent_enrollments = StudentClassEnrollment.objects.select_related(
        'student', 'class_instance', 'academic_session'
    ).order_by('-created_at')[:10]
    
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
# ACADEMIC SESSION VIEWS (CRUD + Print)
# =============================================================================

@login_required
def academic_session_list(request):
    """List all academic sessions - HTMX loads data on page load"""
    
    # Initialize filter form
    filter_form = AcademicSessionFilterForm()
    
    # Get initial stats from stats.py
    try:
        initial_stats = academic_stats.get_academic_session_statistics()
    except Exception as e:
        logger.error(f"Error getting session statistics: {e}")
        initial_stats = {}
    
    context = {
        'filter_form': filter_form,
        'stats': initial_stats,
        'AcademicSession': AcademicSession,
    }
    
    return render(request, 'academics/sessions/list.html', context)

@login_required
def academic_session_create(request):
    """Create new academic session"""
    
    if request.method == 'POST':
        form = AcademicSessionForm(request.POST)
        if form.is_valid():
            try:
                from .services import AcademicSessionService
                
                session_data = form.cleaned_data
                
                session = AcademicSessionService.create_academic_session(session_data)
                
                messages.success(
                    request, 
                    f'Academic session "{session.name}" created successfully!'
                )
                return redirect('academics:session_detail', pk=session.pk)
                
            except Exception as e:
                logger.error(f"Error creating session: {e}")
                messages.error(request, f'Error creating session: {str(e)}')
    else:
        form = AcademicSessionForm()
    
    context = {
        'form': form,
        'title': 'Create Academic Session',
        'submit_text': 'Create Session',
    }
    
    return render(request, 'academics/sessions/form.html', context)


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
        'academic_level', 'class_teacher'
    ).prefetch_related('enrollments')[:10]
    
    recent_enrollments = session.student_class_enrollments.select_related(
        'student', 'class_instance'
    ).order_by('-created_at')[:10]
    
    holidays = session.holidays.order_by('start_date')[:10]
    
    # ⭐ Calculate progress using school timezone
    today = get_school_today()
    progress_info = {
        'days_elapsed': max(0, (today - session.start_date).days) if today >= session.start_date else 0,
        'days_remaining': max(0, (session.end_date - today).days) if today <= session.end_date else 0,
        'total_days': (session.end_date - session.start_date).days + 1,
        'is_current': session.start_date <= today <= session.end_date,
        'is_future': today < session.start_date,
        'is_past': today > session.end_date,
    }
    
    if progress_info['total_days'] > 0:
        progress_info['progress_percentage'] = round(
            (progress_info['days_elapsed'] / progress_info['total_days']) * 100, 1
        )
    else:
        progress_info['progress_percentage'] = 0
    
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
def academic_session_edit(request, pk):
    """Edit academic session"""
    
    session = get_object_or_404(AcademicSession, pk=pk)
    
    # Check if session can be edited
    if session.is_academically_closed:
        messages.warning(request, 'Cannot edit a closed academic session.')
        return redirect('academics:session_detail', pk=pk)
    
    if request.method == 'POST':
        form = AcademicSessionForm(request.POST, instance=session)
        if form.is_valid():
            try:
                session = form.save()
                
                messages.success(
                    request, 
                    f'Academic session "{session.name}" updated successfully!'
                )
                return redirect('academics:session_detail', pk=session.pk)
                
            except Exception as e:
                logger.error(f"Error updating session: {e}")
                messages.error(request, f'Error updating session: {str(e)}')
    else:
        form = AcademicSessionForm(instance=session)
    
    context = {
        'form': form,
        'session': session,
        'title': f'Edit {session.name}',
        'submit_text': 'Update Session',
    }
    
    return render(request, 'academics/sessions/form.html', context)


@login_required
def academic_session_close(request, pk):
    """Close academic session"""
    
    session = get_object_or_404(AcademicSession, pk=pk)
    
    if request.method == 'POST':
        try:
            from .services import AcademicSessionService
            
            success, message = AcademicSessionService.close_academic_session(
                session, user=request.user
            )
            
            if success:
                messages.success(request, message)
            else:
                messages.error(request, message)
                
        except Exception as e:
            logger.error(f"Error closing session: {e}")
            messages.error(request, f'Error closing session: {str(e)}')
    
    return redirect('academics:session_detail', pk=pk)


@login_required
def academic_session_reopen(request, pk):
    """Reopen closed academic session"""
    
    session = get_object_or_404(AcademicSession, pk=pk)
    
    if request.method == 'POST':
        try:
            from .services import AcademicSessionService
            
            success, message = AcademicSessionService.reopen_academic_session(
                session, user=request.user
            )
            
            if success:
                messages.success(request, message)
            else:
                messages.warning(request, message)
                
        except Exception as e:
            logger.error(f"Error reopening session: {e}")
            messages.error(request, f'Error reopening session: {str(e)}')
    
    return redirect('academics:session_detail', pk=pk)


@login_required
def academic_session_print_view(request):
    """Generate printable academic session list with selected fields"""
    
    # Get selected fields from the modal
    selected_fields = request.GET.getlist('fields')
    if not selected_fields:
        # Default fields if none selected
        selected_fields = ['year_name', 'term_name', 'period_type', 'start_date', 'end_date', 'status_display', 'is_current']
    
    # Get additional options
    include_stats = request.GET.get('include_stats') == 'true'
    landscape_mode = request.GET.get('landscape') == 'true'
    
    # Get filter parameters from URL
    query = request.GET.get('q', '')
    is_current = request.GET.get('is_current', '')
    is_active = request.GET.get('is_active', '')
    is_academically_closed = request.GET.get('is_academically_closed', '')
    period_type = request.GET.get('period_type', '')
    year_name = request.GET.get('year_name', '')
    is_special_session = request.GET.get('is_special_session', '')
    
    # Build queryset
    sessions = AcademicSession.objects.order_by('-start_date', 'term_number')
    
    # Apply filters (same as session_search)
    if query:
        sessions = sessions.filter(
            Q(year_name__icontains=query) |
            Q(term_name__icontains=query) |
            Q(description__icontains=query)
        )
    
    if is_current:
        sessions = sessions.filter(is_current=(is_current == 'true'))
    
    if is_active:
        sessions = sessions.filter(is_active=(is_active == 'true'))
    
    if is_academically_closed:
        sessions = sessions.filter(is_academically_closed=(is_academically_closed == 'true'))
    
    if period_type:
        sessions = sessions.filter(period_type=period_type)
    
    if year_name:
        sessions = sessions.filter(year_name__icontains=year_name)
    
    if is_special_session:
        sessions = sessions.filter(is_special_session=(is_special_session == 'true'))
    
    # Calculate stats only if requested
    stats = None
    if include_stats:
        total = sessions.count()
        active_count = sessions.filter(is_active=True).count()
        current_count = sessions.filter(is_current=True).count()
        closed_count = sessions.filter(is_academically_closed=True).count()
        
        stats = {
            'total': total,
            'active': active_count,
            'current': current_count,
            'closed': closed_count,
            'active_percentage': round((active_count / total * 100), 1) if total > 0 else 0,
        }
    
    # Field display names mapping
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
        'is_special_session': 'Special Session',
        'allows_promotion': 'Allows Promotion',
        'minimum_attendance_percentage': 'Min Attendance %',
        'status_display': 'Status',
        'progress_percentage': 'Progress %',
        'days_remaining': 'Days Remaining',
        'description': 'Description',
    }
    
    # Create ordered list of field display names for template
    selected_field_names = [field_names.get(field, field.replace('_', ' ').title()) for field in selected_fields]
    
    context = {
        'sessions': sessions,
        'stats': stats,
        'now': timezone.now(),
        'selected_fields': selected_fields,
        'selected_field_names': selected_field_names,
        'field_names': field_names,
        'landscape': landscape_mode,
        'title': 'Academic Sessions Report',
    }
    
    return render(request, 'academics/sessions/print.html', context)


# =============================================================================
# SUBJECT VIEWS (CRUD + Print)
# =============================================================================

@login_required
def subject_list(request):
    """List all subjects - HTMX loads data on page load"""
    
    # Initialize filter form
    filter_form = SubjectFilterForm()
    
    # Get initial stats from stats.py
    try:
        initial_stats = academic_stats.get_subject_statistics()
    except Exception as e:
        logger.error(f"Error getting subject statistics: {e}")
        initial_stats = {}
    
    context = {
        'filter_form': filter_form,
        'stats': initial_stats,
        'Subject': Subject,
    }
    
    return render(request, 'academics/subjects/list.html', context)


@login_required
def subject_create(request):
    """Create new subject"""
    
    if request.method == 'POST':
        form = SubjectForm(request.POST)
        if form.is_valid():
            try:
                subject = form.save()
                
                messages.success(
                    request, 
                    f'Subject "{subject.name}" created successfully!'
                )
                return redirect('academics:subject_detail', pk=subject.pk)
                
            except Exception as e:
                logger.error(f"Error creating subject: {e}")
                messages.error(request, f'Error creating subject: {str(e)}')
    else:
        form = SubjectForm()
    
    context = {
        'form': form,
        'title': 'Create Subject',
        'submit_text': 'Create Subject',
    }
    
    return render(request, 'academics/subjects/form.html', context)


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
def subject_edit(request, pk):
    """Edit subject"""
    
    subject = get_object_or_404(Subject, pk=pk)
    
    if request.method == 'POST':
        form = SubjectForm(request.POST, instance=subject)
        if form.is_valid():
            try:
                subject = form.save()
                
                messages.success(
                    request, 
                    f'Subject "{subject.name}" updated successfully!'
                )
                return redirect('academics:subject_detail', pk=subject.pk)
                
            except Exception as e:
                logger.error(f"Error updating subject: {e}")
                messages.error(request, f'Error updating subject: {str(e)}')
    else:
        form = SubjectForm(instance=subject)
    
    context = {
        'form': form,
        'subject': subject,
        'title': f'Edit {subject.name}',
        'submit_text': 'Update Subject',
    }
    
    return render(request, 'academics/subjects/form.html', context)


@login_required
def subject_print_view(request):
    """Generate printable subject list with selected fields"""
    
    # Get selected fields from the modal
    selected_fields = request.GET.getlist('fields')
    if not selected_fields:
        # Default fields if none selected
        selected_fields = ['name', 'abbreviation', 'code', 'subject_type', 'credit_hours', 'is_compulsory', 'is_active']
    
    # Get additional options
    include_stats = request.GET.get('include_stats') == 'true'
    landscape_mode = request.GET.get('landscape') == 'true'
    
    # Get filter parameters from URL
    query = request.GET.get('q', '')
    subject_type = request.GET.get('subject_type', '')
    is_active = request.GET.get('is_active', '')
    is_compulsory = request.GET.get('is_compulsory', '')
    difficulty_level = request.GET.get('difficulty_level', '')
    department = request.GET.get('department', '')
    
    # Build queryset
    subjects = Subject.objects.select_related('department').order_by('subject_type', 'name')
    
    # Apply filters
    if query:
        subjects = subjects.filter(
            Q(name__icontains=query) |
            Q(abbreviation__icontains=query) |
            Q(code__icontains=query) |
            Q(description__icontains=query)
        )
    
    if subject_type:
        subjects = subjects.filter(subject_type=subject_type)
    
    if is_active:
        subjects = subjects.filter(is_active=(is_active == 'true'))
    
    if is_compulsory:
        subjects = subjects.filter(is_compulsory=(is_compulsory == 'true'))
    
    if difficulty_level:
        subjects = subjects.filter(difficulty_level=difficulty_level)
    
    if department:
        subjects = subjects.filter(department_id=department)
    
    # Calculate stats only if requested
    stats = None
    if include_stats:
        total = subjects.count()
        active_count = subjects.filter(is_active=True).count()
        compulsory_count = subjects.filter(is_compulsory=True).count()
        
        stats = {
            'total': total,
            'active': active_count,
            'compulsory': compulsory_count,
            'optional': total - compulsory_count,
            'active_percentage': round((active_count / total * 100), 1) if total > 0 else 0,
            'avg_credit_hours': round(subjects.aggregate(Avg('credit_hours'))['credit_hours__avg'] or 0, 1),
        }
    
    # Field display names mapping
    field_names = {
        'name': 'Subject Name',
        'abbreviation': 'Abbreviation',
        'code': 'Subject Code',
        'subject_type': 'Subject Type',
        'credit_hours': 'Credit Hours',
        'pass_mark': 'Pass Mark',
        'difficulty_level': 'Difficulty',
        'weight_factor': 'Weight Factor',
        'is_compulsory': 'Compulsory',
        'is_active': 'Active',
        'department': 'Department',
        'textbook_required': 'Textbook Required',
        'description': 'Description',
    }
    
    selected_field_names = [field_names.get(field, field.replace('_', ' ').title()) for field in selected_fields]
    
    context = {
        'subjects': subjects,
        'stats': stats,
        'now': timezone.now(),
        'selected_fields': selected_fields,
        'selected_field_names': selected_field_names,
        'field_names': field_names,
        'landscape': landscape_mode,
        'title': 'Subjects Report',
    }
    
    return render(request, 'academics/subjects/print.html', context)


# =============================================================================
# ACADEMIC LEVEL VIEWS (CRUD + Print)
# =============================================================================

@login_required
def academic_level_list(request):
    """List all academic levels - HTMX loads data on page load"""
    
    # Initialize filter form
    filter_form = AcademicLevelFilterForm()
    
    # Get initial stats from stats.py
    try:
        initial_stats = academic_stats.get_academic_level_statistics()
    except Exception as e:
        logger.error(f"Error getting level statistics: {e}")
        initial_stats = {}
    
    context = {
        'filter_form': filter_form,
        'stats': initial_stats,
        'AcademicLevel': AcademicLevel,
    }
    
    return render(request, 'academics/levels/list.html', context)


@login_required
def academic_level_create(request):
    """Create new academic level"""
    
    if request.method == 'POST':
        form = AcademicLevelForm(request.POST)
        if form.is_valid():
            try:
                level = form.save()
                
                # ✅ Audit trail automatically handled by BaseModel
                
                messages.success(
                    request, 
                    f'Academic level "{level.name}" created successfully!'
                )
                return redirect('academics:level_detail', pk=level.pk)
                
            except Exception as e:
                logger.error(f"Error creating academic level: {e}")
                messages.error(request, f'Error creating academic level: {str(e)}')
    else:
        form = AcademicLevelForm()
    
    context = {
        'form': form,
        'title': 'Create Academic Level',
        'submit_text': 'Create Level',
    }
    
    return render(request, 'academics/levels/form.html', context)


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
def academic_level_edit(request, pk):
    """Edit academic level"""
    
    level = get_object_or_404(AcademicLevel, pk=pk)
    
    if request.method == 'POST':
        form = AcademicLevelForm(request.POST, instance=level)
        if form.is_valid():
            try:
                level = form.save()
                
                # ✅ Audit trail automatically handled by BaseModel
                
                messages.success(
                    request, 
                    f'Academic level "{level.name}" updated successfully!'
                )
                return redirect('academics:level_detail', pk=level.pk)
                
            except Exception as e:
                logger.error(f"Error updating academic level: {e}")
                messages.error(request, f'Error updating academic level: {str(e)}')
    else:
        form = AcademicLevelForm(instance=level)
    
    context = {
        'form': form,
        'level': level,
        'title': f'Edit {level.name}',
        'submit_text': 'Update Level',
    }
    
    return render(request, 'academics/levels/form.html', context)


@login_required
def academic_level_print_view(request):
    """Generate printable academic level list with selected fields"""
    
    selected_fields = request.GET.getlist('fields')
    if not selected_fields:
        selected_fields = ['name', 'code', 'order', 'has_sections', 'is_graduation_level', 'is_active']
    
    include_stats = request.GET.get('include_stats') == 'true'
    landscape_mode = request.GET.get('landscape') == 'true'
    
    # Get filter parameters
    query = request.GET.get('q', '')
    is_active = request.GET.get('is_active', '')
    has_sections = request.GET.get('has_sections', '')
    is_graduation_level = request.GET.get('is_graduation_level', '')
    
    # Build queryset
    levels = AcademicLevel.objects.order_by('order')
    
    # Apply filters
    if query:
        levels = levels.filter(
            Q(name__icontains=query) |
            Q(code__icontains=query) |
            Q(description__icontains=query)
        )
    
    if is_active:
        levels = levels.filter(is_active=(is_active == 'true'))
    
    if has_sections:
        levels = levels.filter(has_sections=(has_sections == 'true'))
    
    if is_graduation_level:
        levels = levels.filter(is_graduation_level=(is_graduation_level == 'true'))
    
    # Calculate stats
    stats = None
    if include_stats:
        total = levels.count()
        active_count = levels.filter(is_active=True).count()
        
        stats = {
            'total': total,
            'active': active_count,
            'with_sections': levels.filter(has_sections=True).count(),
            'graduation_levels': levels.filter(is_graduation_level=True).count(),
        }
    
    # Field display names
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
    
    selected_field_names = [field_names.get(field, field.replace('_', ' ').title()) for field in selected_fields]
    
    context = {
        'levels': levels,
        'stats': stats,
        'now': timezone.now(),
        'selected_fields': selected_fields,
        'selected_field_names': selected_field_names,
        'field_names': field_names,
        'landscape': landscape_mode,
        'title': 'Academic Levels Report',
    }
    
    return render(request, 'academics/levels/print.html', context)


# =============================================================================
# CLASSROOM VIEWS (CRUD + Print)
# =============================================================================

@login_required
def classroom_list(request):
    """List all classrooms - HTMX loads data on page load"""
    
    filter_form = ClassRoomFilterForm()
    
    try:
        initial_stats = academic_stats.get_classroom_statistics()
    except Exception as e:
        logger.error(f"Error getting classroom statistics: {e}")
        initial_stats = {}
    
    context = {
        'filter_form': filter_form,
        'stats': initial_stats,
        'ClassRoom': ClassRoom,
    }
    
    return render(request, 'academics/classrooms/list.html', context)


@login_required
def classroom_create(request):
    """Create new classroom"""
    
    if request.method == 'POST':
        form = ClassRoomForm(request.POST)
        if form.is_valid():
            try:
                classroom = form.save()
                
                # ✅ Audit trail automatically handled by BaseModel
                
                messages.success(
                    request, 
                    f'Classroom "{classroom.name}" created successfully!'
                )
                return redirect('academics:classroom_detail', pk=classroom.pk)
                
            except Exception as e:
                logger.error(f"Error creating classroom: {e}")
                messages.error(request, f'Error creating classroom: {str(e)}')
    else:
        form = ClassRoomForm()
    
    context = {
        'form': form,
        'title': 'Create Classroom',
        'submit_text': 'Create Classroom',
    }
    
    return render(request, 'academics/classrooms/form.html', context)


@login_required
def classroom_detail(request, pk):
    """View classroom details"""
    
    classroom = get_object_or_404(ClassRoom, pk=pk)
    
    # Get classes currently using this classroom
    current_classes = classroom.classes.select_related(
        'academic_level', 'academic_session', 'class_teacher'
    ).filter(is_active=True)
    
    # Calculate utilization
    total_capacity = classroom.capacity
    current_students = sum(
        cls.enrollments.filter(is_active=True).count() 
        for cls in current_classes
    )
    
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
def classroom_edit(request, pk):
    """Edit classroom"""
    
    classroom = get_object_or_404(ClassRoom, pk=pk)
    
    if request.method == 'POST':
        form = ClassRoomForm(request.POST, instance=classroom)
        if form.is_valid():
            try:
                classroom = form.save()
                
                # ✅ Audit trail automatically handled by BaseModel
                
                messages.success(
                    request, 
                    f'Classroom "{classroom.name}" updated successfully!'
                )
                return redirect('academics:classroom_detail', pk=classroom.pk)
                
            except Exception as e:
                logger.error(f"Error updating classroom: {e}")
                messages.error(request, f'Error updating classroom: {str(e)}')
    else:
        form = ClassRoomForm(instance=classroom)
    
    context = {
        'form': form,
        'classroom': classroom,
        'title': f'Edit {classroom.name}',
        'submit_text': 'Update Classroom',
    }
    
    return render(request, 'academics/classrooms/form.html', context)


@login_required
def classroom_print_view(request):
    """Generate printable classroom list with selected fields"""
    
    selected_fields = request.GET.getlist('fields')
    if not selected_fields:
        selected_fields = ['name', 'room_number', 'building', 'room_type', 'capacity', 'is_active']
    
    include_stats = request.GET.get('include_stats') == 'true'
    landscape_mode = request.GET.get('landscape') == 'true'
    
    # Get filter parameters
    query = request.GET.get('q', '')
    room_type = request.GET.get('room_type', '')
    building = request.GET.get('building', '')
    is_active = request.GET.get('is_active', '')
    
    # Build queryset
    classrooms = ClassRoom.objects.order_by('building', 'room_number')
    
    # Apply filters
    if query:
        classrooms = classrooms.filter(
            Q(name__icontains=query) |
            Q(room_number__icontains=query) |
            Q(building__icontains=query)
        )
    
    if room_type:
        classrooms = classrooms.filter(room_type=room_type)
    
    if building:
        classrooms = classrooms.filter(building__icontains=building)
    
    if is_active:
        classrooms = classrooms.filter(is_active=(is_active == 'true'))
    
    # Calculate stats
    stats = None
    if include_stats:
        total = classrooms.count()
        active_count = classrooms.filter(is_active=True).count()
        total_capacity = classrooms.aggregate(Sum('capacity'))['capacity__sum'] or 0
        
        stats = {
            'total': total,
            'active': active_count,
            'total_capacity': total_capacity,
            'avg_capacity': round(classrooms.aggregate(Avg('capacity'))['capacity__avg'] or 0),
        }
    
    # Field display names
    field_names = {
        'name': 'Room Name',
        'room_number': 'Room Number',
        'building': 'Building',
        'floor': 'Floor',
        'wing': 'Wing',
        'room_type': 'Room Type',
        'capacity': 'Capacity',
        'is_active': 'Active',
        'has_projector': 'Projector',
        'has_computer': 'Computer',
        'has_smart_board': 'Smart Board',
        'has_air_conditioning': 'A/C',
        'is_accessible': 'Accessible',
    }
    
    selected_field_names = [field_names.get(field, field.replace('_', ' ').title()) for field in selected_fields]
    
    context = {
        'classrooms': classrooms,
        'stats': stats,
        'now': timezone.now(),
        'selected_fields': selected_fields,
        'selected_field_names': selected_field_names,
        'field_names': field_names,
        'landscape': landscape_mode,
        'title': 'Classrooms Report',
    }
    
    return render(request, 'academics/classrooms/print.html', context)


# =============================================================================
# CLASS VIEWS (CRUD + Print)
# =============================================================================

@login_required
def class_list(request):
    """List all classes - HTMX loads data on page load"""
    
    filter_form = ClassFilterForm()
    
    try:
        initial_stats = academic_stats.get_class_statistics()
    except Exception as e:
        logger.error(f"Error getting class statistics: {e}")
        initial_stats = {}
    
    context = {
        'filter_form': filter_form,
        'stats': initial_stats,
        'Class': Class,
    }
    
    return render(request, 'academics/classes/list.html', context)


@login_required
def class_create(request):
    """Create new class"""
    
    if request.method == 'POST':
        form = ClassForm(request.POST)
        if form.is_valid():
            try:
                class_instance = form.save()
                
                messages.success(
                    request, 
                    f'Class "{class_instance}" created successfully!'
                )
                return redirect('academics:class_detail', pk=class_instance.pk)
                
            except Exception as e:
                logger.error(f"Error creating class: {e}")
                messages.error(request, f'Error creating class: {str(e)}')
    else:
        # Get current session as default
        current_session = get_active_academic_session()
        form = ClassForm(initial={
            'academic_session': current_session
        } if current_session else {})
    
    context = {
        'form': form,
        'title': 'Create Class',
        'submit_text': 'Create Class',
    }
    
    return render(request, 'academics/classes/form.html', context)


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
    
    # Get class capacity summary
    from academics.utils import get_class_capacity_summary
    capacity_info = get_class_capacity_summary(class_instance)
    
    # Calculate additional stats
    male_students = enrollments.filter(student__gender='M').count()
    female_students = enrollments.filter(student__gender='F').count()
    
    context = {
        'class': class_instance,
        'enrollments': enrollments,
        'subjects': subjects,
        'capacity_info': capacity_info,
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
def class_edit(request, pk):
    """Edit class"""
    
    class_instance = get_object_or_404(Class, pk=pk)
    
    if request.method == 'POST':
        form = ClassForm(request.POST, instance=class_instance)
        if form.is_valid():
            try:
                class_instance = form.save()
                
                # ✅ Audit trail automatically handled by BaseModel
                
                messages.success(
                    request, 
                    f'Class "{class_instance}" updated successfully!'
                )
                return redirect('academics:class_detail', pk=class_instance.pk)
                
            except Exception as e:
                logger.error(f"Error updating class: {e}")
                messages.error(request, f'Error updating class: {str(e)}')
    else:
        form = ClassForm(instance=class_instance)
    
    context = {
        'form': form,
        'class': class_instance,
        'title': f'Edit {class_instance}',
        'submit_text': 'Update Class',
    }
    
    return render(request, 'academics/classes/form.html', context)


@login_required
def class_print_view(request):
    """Generate printable class list with selected fields"""
    
    selected_fields = request.GET.getlist('fields')
    if not selected_fields:
        selected_fields = ['academic_level', 'section', 'academic_session', 'class_teacher', 'max_students', 'is_active']
    
    include_stats = request.GET.get('include_stats') == 'true'
    landscape_mode = request.GET.get('landscape') == 'true'
    
    # Get filter parameters
    query = request.GET.get('q', '')
    academic_level = request.GET.get('academic_level', '')
    academic_session = request.GET.get('academic_session', '')
    class_teacher = request.GET.get('class_teacher', '')
    is_active = request.GET.get('is_active', '')
    
    # Build queryset
    classes = Class.objects.select_related(
        'academic_level', 'academic_session', 'class_teacher', 'classroom'
    ).order_by('academic_session__start_date', 'academic_level__order', 'section')
    
    # Apply filters
    if query:
        classes = classes.filter(
            Q(academic_level__name__icontains=query) |
            Q(section__icontains=query) |
            Q(class_teacher__user__first_name__icontains=query) |
            Q(class_teacher__user__last_name__icontains=query)
        )
    
    if academic_level:
        classes = classes.filter(academic_level_id=academic_level)
    
    if academic_session:
        classes = classes.filter(academic_session_id=academic_session)
    
    if class_teacher:
        classes = classes.filter(class_teacher_id=class_teacher)
    
    if is_active:
        classes = classes.filter(is_active=(is_active == 'true'))
    
    # Calculate stats
    stats = None
    if include_stats:
        total = classes.count()
        active_count = classes.filter(is_active=True).count()
        total_capacity = classes.aggregate(Sum('max_students'))['max_students__sum'] or 0
        
        stats = {
            'total': total,
            'active': active_count,
            'total_capacity': total_capacity,
            'with_teacher': classes.exclude(class_teacher__isnull=True).count(),
        }
    
    # Field display names
    field_names = {
        'academic_level': 'Academic Level',
        'section': 'Section',
        'academic_session': 'Academic Session',
        'class_teacher': 'Class Teacher',
        'assistant_teacher': 'Assistant Teacher',
        'classroom': 'Classroom',
        'max_students': 'Max Students',
        'is_active': 'Active',
        'class_motto': 'Class Motto',
        'start_time': 'Start Time',
        'end_time': 'End Time',
    }
    
    selected_field_names = [field_names.get(field, field.replace('_', ' ').title()) for field in selected_fields]
    
    context = {
        'classes': classes,
        'stats': stats,
        'now': timezone.now(),
        'selected_fields': selected_fields,
        'selected_field_names': selected_field_names,
        'field_names': field_names,
        'landscape': landscape_mode,
        'title': 'Classes Report',
    }
    
    return render(request, 'academics/classes/print.html', context)


# =============================================================================
# STUDENT CLASS ENROLLMENT VIEWS (CRUD + Print)
# =============================================================================

@login_required
def student_enrollment_list(request):
    """List all student class enrollments - HTMX loads data on page load"""
    
    filter_form = StudentClassEnrollmentFilterForm()
    
    try:
        initial_stats = academic_stats.get_enrollment_statistics()
    except Exception as e:
        logger.error(f"Error getting enrollment statistics: {e}")
        initial_stats = {}
    
    context = {
        'filter_form': filter_form,
        'stats': initial_stats,
        'StudentClassEnrollment': StudentClassEnrollment,
    }
    
    return render(request, 'academics/enrollments/list.html', context)


@login_required
def student_enrollment_create(request):
    """Create new student enrollment"""
    
    if request.method == 'POST':
        form = StudentClassEnrollmentForm(request.POST)
        if form.is_valid():
            try:
                from .services import ClassEnrollmentService
                
                # ⭐ Use service for enrollment with timezone awareness
                enrollment, invoice = ClassEnrollmentService.enroll_student_in_class(
                    student=form.cleaned_data['student'],
                    class_instance=form.cleaned_data['class_instance'],
                    session=form.cleaned_data['academic_session'],
                    enrollment_type=form.cleaned_data.get('enrollment_type', 'NEW'),
                    notes=form.cleaned_data.get('enrollment_notes', ''),
                    auto_create_invoice=form.cleaned_data.get('auto_create_invoice', True)
                )
                
                message = f'Student "{enrollment.student.get_full_name()}" enrolled in {enrollment.class_instance} successfully!'
                if invoice:
                    message += f' Invoice {invoice.invoice_number} created.'
                
                messages.success(request, message)
                return redirect('academics:enrollment_detail', pk=enrollment.pk)
                
            except Exception as e:
                logger.error(f"Error creating enrollment: {e}")
                messages.error(request, f'Error enrolling student: {str(e)}')
    else:
        # ⭐ Use school timezone for default date
        today = get_school_today()
        current_session = get_active_academic_session()
        
        form = StudentClassEnrollmentForm(initial={
            'enrollment_date': today,
            'academic_session': current_session,
        })
    
    context = {
        'form': form,
        'title': 'Enroll Student',
        'submit_text': 'Enroll Student',
    }
    
    return render(request, 'academics/enrollments/form.html', context)


@login_required
def student_enrollment_detail(request, pk):
    """View enrollment details"""
    
    enrollment = get_object_or_404(
        StudentClassEnrollment.objects.select_related(
            'student', 'class_instance', 'academic_session', 'academic_invoice'
        ),
        pk=pk
    )
    
    # Get related data
    try:
        progress_record = enrollment.progress_records.first()
    except:
        progress_record = None
    
    # ⭐ Calculate enrollment duration using school timezone
    today = get_school_today()
    enrollment_info = {
        'days_enrolled': max(0, (today - enrollment.enrollment_date).days + 1),
        'is_current': enrollment.is_active and enrollment.completion_status == 'ONGOING',
        'completion_percentage': 0,
    }
    
    if enrollment.academic_session:
        session_days = (enrollment.academic_session.end_date - enrollment.academic_session.start_date).days + 1
        if session_days > 0:
            enrollment_info['completion_percentage'] = round(
                (enrollment_info['days_enrolled'] / session_days) * 100, 1
            )
    
    context = {
        'enrollment': enrollment,
        'progress_record': progress_record,
        'enrollment_info': enrollment_info,
    }
    
    return render(request, 'academics/enrollments/detail.html', context)


@login_required
def student_enrollment_edit(request, pk):
    """Edit student enrollment"""
    
    enrollment = get_object_or_404(StudentClassEnrollment, pk=pk)
    
    # Check if enrollment can be edited
    if enrollment.completion_status != 'ONGOING':
        messages.warning(request, 'Cannot edit completed enrollments.')
        return redirect('academics:enrollment_detail', pk=pk)
    
    if request.method == 'POST':
        form = StudentClassEnrollmentForm(request.POST, instance=enrollment)
        if form.is_valid():
            try:
                enrollment = form.save()
                
                messages.success(
                    request, 
                    f'Enrollment for "{enrollment.student.get_full_name()}" updated successfully!'
                )
                return redirect('academics:enrollment_detail', pk=enrollment.pk)
                
            except Exception as e:
                logger.error(f"Error updating enrollment: {e}")
                messages.error(request, f'Error updating enrollment: {str(e)}')
    else:
        form = StudentClassEnrollmentForm(instance=enrollment)
    
    context = {
        'form': form,
        'enrollment': enrollment,
        'title': f'Edit Enrollment - {enrollment.student.get_full_name()}',
        'submit_text': 'Update Enrollment',
    }
    
    return render(request, 'academics/enrollments/form.html', context)


@login_required
def student_enrollment_transfer(request, pk):
    """Transfer student to different class"""
    
    enrollment = get_object_or_404(StudentClassEnrollment, pk=pk)
    
    if enrollment.completion_status != 'ONGOING':
        messages.warning(request, 'Can only transfer students with ongoing enrollments.')
        return redirect('academics:enrollment_detail', pk=pk)
    
    if request.method == 'POST':
        new_class_id = request.POST.get('new_class')
        reason = request.POST.get('reason', '')
        
        try:
            new_class = Class.objects.get(pk=new_class_id)
            
            from .services import ClassEnrollmentService
            
            new_enrollment = ClassEnrollmentService.transfer_student_to_class(
                enrollment=enrollment,
                new_class_instance=new_class,
                reason=reason,
                transfer_date=get_school_today()  # ⭐ Use school timezone
            )
            
            messages.success(
                request, 
                f'Student "{enrollment.student.get_full_name()}" transferred from {enrollment.class_instance} to {new_class}!'
            )
            return redirect('academics:enrollment_detail', pk=new_enrollment.pk)
            
        except Exception as e:
            logger.error(f"Error transferring student: {e}")
            messages.error(request, f'Error transferring student: {str(e)}')
    
    # Get available classes for transfer (same session, different class)
    available_classes = Class.objects.filter(
        academic_session=enrollment.academic_session,
        is_active=True
    ).exclude(pk=enrollment.class_instance.pk).select_related('academic_level')
    
    context = {
        'enrollment': enrollment,
        'available_classes': available_classes,
        'title': f'Transfer {enrollment.student.get_full_name()}',
    }
    
    return render(request, 'academics/enrollments/transfer.html', context)


@login_required
def student_enrollment_withdraw(request, pk):
    """Withdraw student from class"""
    
    enrollment = get_object_or_404(StudentClassEnrollment, pk=pk)
    
    if enrollment.completion_status != 'ONGOING':
        messages.warning(request, 'Student is already withdrawn or completed.')
        return redirect('academics:enrollment_detail', pk=pk)
    
    if request.method == 'POST':
        reason = request.POST.get('reason', '')
        
        try:
            from .services import ClassEnrollmentService
            
            ClassEnrollmentService.withdraw_student_from_class(
                enrollment=enrollment,
                reason=reason,
                withdrawal_date=get_school_today()  # ⭐ Use school timezone
            )
            
            messages.success(
                request, 
                f'Student "{enrollment.student.get_full_name()}" withdrawn from {enrollment.class_instance}!'
            )
            return redirect('academics:enrollment_detail', pk=enrollment.pk)
            
        except Exception as e:
            logger.error(f"Error withdrawing student: {e}")
            messages.error(request, f'Error withdrawing student: {str(e)}')
    
    context = {
        'enrollment': enrollment,
        'title': f'Withdraw {enrollment.student.get_full_name()}',
    }
    
    return render(request, 'academics/enrollments/withdraw.html', context)


@login_required
def student_enrollment_print_view(request):
    """Generate printable student enrollment list with selected fields"""
    
    selected_fields = request.GET.getlist('fields')
    if not selected_fields:
        selected_fields = ['student', 'class_instance', 'academic_session', 'roll_number', 'enrollment_type', 'completion_status']
    
    include_stats = request.GET.get('include_stats') == 'true'
    landscape_mode = request.GET.get('landscape') == 'true'
    
    # Get filter parameters
    query = request.GET.get('q', '')
    class_instance = request.GET.get('class_instance', '')
    academic_session = request.GET.get('academic_session', '')
    enrollment_type = request.GET.get('enrollment_type', '')
    completion_status = request.GET.get('completion_status', '')
    is_active = request.GET.get('is_active', '')
    
    # Build queryset
    enrollments = StudentClassEnrollment.objects.select_related(
        'student', 'class_instance', 'academic_session', 'class_instance__academic_level'
    ).order_by('-enrollment_date', 'student__last_name')
    
    # Apply filters
    if query:
        enrollments = enrollments.filter(
            Q(student__first_name__icontains=query) |
            Q(student__last_name__icontains=query) |
            Q(student__admission_number__icontains=query) |
            Q(roll_number__icontains=query)
        )
    
    if class_instance:
        enrollments = enrollments.filter(class_instance_id=class_instance)
    
    if academic_session:
        enrollments = enrollments.filter(academic_session_id=academic_session)
    
    if enrollment_type:
        enrollments = enrollments.filter(enrollment_type=enrollment_type)
    
    if completion_status:
        enrollments = enrollments.filter(completion_status=completion_status)
    
    if is_active:
        enrollments = enrollments.filter(is_active=(is_active == 'true'))
    
    # Calculate stats
    stats = None
    if include_stats:
        total = enrollments.count()
        active_count = enrollments.filter(is_active=True).count()
        ongoing_count = enrollments.filter(completion_status='ONGOING').count()
        
        stats = {
            'total': total,
            'active': active_count,
            'ongoing': ongoing_count,
            'completed': enrollments.filter(completion_status='COMPLETED').count(),
        }
    
    # Field display names
    field_names = {
        'student': 'Student',
        'class_instance': 'Class',
        'academic_session': 'Academic Session',
        'roll_number': 'Roll Number',
        'enrollment_date': 'Enrollment Date',
        'enrollment_type': 'Enrollment Type',
        'completion_status': 'Status',
        'completion_date': 'Completion Date',
        'is_active': 'Active',
        'progression_type': 'Progression Type',
    }
    
    selected_field_names = [field_names.get(field, field.replace('_', ' ').title()) for field in selected_fields]
    
    context = {
        'enrollments': enrollments,
        'stats': stats,
        'now': timezone.now(),
        'selected_fields': selected_fields,
        'selected_field_names': selected_field_names,
        'field_names': field_names,
        'landscape': landscape_mode,
        'title': 'Student Enrollments Report',
    }
    
    return render(request, 'academics/enrollments/print.html', context)

@login_required
def bulk_student_enrollment(request):
    """Bulk student enrollment interface"""
    try:
        if request.method == 'POST':
            form = BulkEnrollmentForm(request.POST, user=request.user)
            if form.is_valid():
                try:
                    # Use the bulk enrollment service
                    from .services import BulkEnrollmentService
                    
                    students = form.cleaned_data['students']
                    class_instance = form.cleaned_data['class_instance']
                    academic_session = form.cleaned_data['academic_session']
                    enrollment_type = form.cleaned_data.get('enrollment_type', 'BULK')
                    auto_create_invoices = form.cleaned_data.get('auto_create_invoices', True)
                    
                    result = BulkEnrollmentService.bulk_enroll_students(
                        students=students,
                        class_instance=class_instance,
                        session=academic_session,
                        enrollment_type=enrollment_type,
                        auto_create_invoices=auto_create_invoices
                    )
                    
                    # ✅ Audit trail automatically handled by BaseModel for each enrollment
                    
                    success_count = len(result['enrolled'])
                    failure_count = len(result['failed'])
                    
                    if success_count > 0:
                        success_msg = f"Bulk enrollment completed. Successfully enrolled: {success_count}"
                        if failure_count > 0:
                            success_msg += f", Failed: {failure_count}"
                        
                        # Show first few failures if any
                        if result['failed']:
                            failure_details = ", ".join([
                                f"{fail['student'].get_full_name()}" 
                                for fail in result['failed'][:3]
                            ])
                            if len(result['failed']) > 3:
                                failure_details += f" and {len(result['failed']) - 3} others"
                            success_msg += f". Failed students: {failure_details}"
                        
                        messages.success(request, success_msg)
                        return redirect('academics:enrollment_list')
                    else:
                        error_details = "; ".join([
                            f"{fail['student'].get_full_name()}: {fail['error']}" 
                            for fail in result['failed'][:3]
                        ])
                        messages.error(request, f"All enrollments failed. Examples: {error_details}")
                        
                except Exception as e:
                    logger.error(f"Bulk enrollment service error: {e}")
                    messages.error(request, f"Bulk enrollment error: {str(e)}")
            else:
                messages.error(request, "Please correct the errors below.")
        else:
            # Initialize form with current session if available
            current_session = get_active_academic_session()
            initial_data = {}
            if current_session:
                initial_data['academic_session'] = current_session
            
            form = BulkEnrollmentForm(user=request.user, initial=initial_data)
        
        # Get data for the template
        academic_levels = []
        active_sessions = []
        available_classes = []
        
        try:
            # Get academic levels
            academic_levels = list(AcademicLevel.objects.filter(
                is_active=True
            ).values('id', 'name', 'order').order_by('order'))
            
            # Get active academic sessions
            active_sessions = list(AcademicSession.objects.filter(
                is_active=True
            ).values('id', 'year_name', 'term_name', 'is_current').order_by('-start_date'))
            
            # Get available classes (limit to current/active sessions)
            available_classes = list(Class.objects.filter(
                academic_session__is_active=True,
                is_active=True
            ).select_related(
                'academic_level', 'academic_session'
            ).values(
                'id', 'academic_level__name', 'section', 
                'academic_session__year_name', 'academic_session__term_name',
                'max_students', 'academic_level__order'
            ).order_by('academic_level__order', 'section'))
            
        except Exception as e:
            logger.error(f"Error loading bulk enrollment data: {e}")
        
        # Get capacity information for classes
        class_capacity_info = {}
        try:
            from .utils import get_class_capacity_summary
            for class_data in available_classes:
                try:
                    class_obj = Class.objects.get(id=class_data['id'])
                    capacity_info = get_class_capacity_summary(class_obj)
                    class_capacity_info[class_data['id']] = capacity_info
                except Exception as e:
                    logger.debug(f"Error getting capacity for class {class_data['id']}: {e}")
        except Exception as e:
            logger.error(f"Error loading class capacity information: {e}")
        
        # Get students available for enrollment
        available_students = []
        try:
            from students.models import Student
            
            # Students who are active but not currently enrolled
            available_students = Student.objects.filter(
                enrollment_status='ACTIVE'
            ).exclude(
                class_enrollments__is_active=True,
                class_enrollments__completion_status='ONGOING'
            ).values(
                'id', 'admission_number', 'first_name', 'last_name', 
                'current_academic_level__name'
            ).order_by('last_name', 'first_name')[:100]  # Limit for performance
            
        except Exception as e:
            logger.error(f"Error loading available students: {e}")
        
        context = {
            'form': form,
            'academic_levels': academic_levels,
            'active_sessions': active_sessions,
            'available_classes': available_classes,
            'class_capacity_info': class_capacity_info,
            'available_students': list(available_students),
            'title': 'Bulk Student Enrollment',
        }
        
        return render(request, 'academics/enrollments/bulk_enrollment.html', context)
        
    except Exception as e:
        logger.error(f"Error in bulk student enrollment: {e}")
        messages.error(request, f"Error: {str(e)}")
        return redirect('academics:enrollment_list')


@login_required
def bulk_enrollment_preview(request):
    """HTMX endpoint to preview bulk enrollment before submission"""
    
    if request.method == 'POST':
        try:
            class_id = request.POST.get('class_instance')
            student_ids = request.POST.getlist('students')
            
            if not class_id or not student_ids:
                return JsonResponse({'error': 'Missing required data'})
            
            # Get class and students
            from students.models import Student
            class_instance = get_object_or_404(Class, id=class_id)
            students = Student.objects.filter(id__in=student_ids)
            
            # Get capacity information
            from .utils import get_class_capacity_summary
            capacity_info = get_class_capacity_summary(class_instance)
            
            # Validate capacity
            selected_count = students.count()
            available_capacity = capacity_info['available_capacity']
            
            preview_data = {
                'class': {
                    'name': str(class_instance),
                    'academic_level': class_instance.academic_level.name,
                    'academic_session': str(class_instance.academic_session),
                    'max_students': class_instance.max_students,
                    'current_enrollment': capacity_info['current_enrollment'],
                    'available_capacity': available_capacity,
                },
                'students': {
                    'selected_count': selected_count,
                    'can_enroll_all': selected_count <= available_capacity,
                    'overflow_count': max(0, selected_count - available_capacity),
                    'students_list': [
                        {
                            'name': student.get_full_name(),
                            'admission_number': student.admission_number,
                            'current_level': str(student.current_academic_level) if student.current_academic_level else 'None'
                        }
                        for student in students[:10]  # Show first 10
                    ],
                    'has_more': students.count() > 10,
                },
                'warnings': []
            }
            
            # Add warnings
            if selected_count > available_capacity:
                preview_data['warnings'].append(
                    f"Selected {selected_count} students but only {available_capacity} spots available. "
                    f"{preview_data['students']['overflow_count']} students will not be enrolled."
                )
            
            # Check for level mismatches
            level_mismatches = students.exclude(
                current_academic_level=class_instance.academic_level
            ).count()
            
            if level_mismatches > 0:
                preview_data['warnings'].append(
                    f"{level_mismatches} students are not at the {class_instance.academic_level} level."
                )
            
            return JsonResponse({'success': True, 'preview': preview_data})
            
        except Exception as e:
            logger.error(f"Error in bulk enrollment preview: {e}")
            return JsonResponse({'error': str(e)})
    
    return JsonResponse({'error': 'Invalid request method'})

# =============================================================================
# CLASS SUBJECT VIEWS (CRUD + Print)
# =============================================================================

@login_required
def class_subject_list(request):
    """List all class subjects - HTMX loads data on page load"""
    
    filter_form = ClassSubjectFilterForm()
    
    try:
        initial_stats = academic_stats.get_class_subject_statistics()
    except Exception as e:
        logger.error(f"Error getting class subject statistics: {e}")
        initial_stats = {}
    
    context = {
        'filter_form': filter_form,
        'stats': initial_stats,
        'ClassSubject': ClassSubject,
    }
    
    return render(request, 'academics/class_subjects/list.html', context)


@login_required
def class_subject_create(request):
    """Create new class subject assignment"""
    
    if request.method == 'POST':
        form = ClassSubjectForm(request.POST)
        if form.is_valid():
            try:
                class_subject = form.save()
                
                # ✅ Audit trail automatically handled by BaseModel
                
                messages.success(
                    request, 
                    f'Subject "{class_subject.subject.name}" assigned to {class_subject.class_instance} successfully!'
                )
                return redirect('academics:class_subject_detail', pk=class_subject.pk)
                
            except Exception as e:
                logger.error(f"Error creating class subject: {e}")
                messages.error(request, f'Error assigning subject: {str(e)}')
    else:
        form = ClassSubjectForm()
    
    context = {
        'form': form,
        'title': 'Assign Subject to Class',
        'submit_text': 'Assign Subject',
    }
    
    return render(request, 'academics/class_subjects/form.html', context)


@login_required
def class_subject_detail(request, pk):
    """View class subject details"""
    
    class_subject = get_object_or_404(
        ClassSubject.objects.select_related(
            'class_instance', 'subject', 'teacher', 
            'class_instance__academic_level', 'class_instance__academic_session'
        ),
        pk=pk
    )
    
    # Get students in this class
    students = class_subject.class_instance.enrollments.select_related('student').filter(
        is_active=True,
        completion_status='ONGOING'
    ).order_by('student__last_name')
    
    context = {
        'class_subject': class_subject,
        'students': students,
        'stats': {
            'total_students': students.count(),
            'weekly_hours': class_subject.hours_per_week or 0,
            'total_hours': class_subject.total_hours or 0,
        }
    }
    
    return render(request, 'academics/class_subjects/detail.html', context)


@login_required
def class_subject_edit(request, pk):
    """Edit class subject assignment"""
    
    class_subject = get_object_or_404(ClassSubject, pk=pk)
    
    if request.method == 'POST':
        form = ClassSubjectForm(request.POST, instance=class_subject)
        if form.is_valid():
            try:
                class_subject = form.save()
                
                # ✅ Audit trail automatically handled by BaseModel
                
                messages.success(
                    request, 
                    f'Subject assignment for "{class_subject.subject.name}" updated successfully!'
                )
                return redirect('academics:class_subject_detail', pk=class_subject.pk)
                
            except Exception as e:
                logger.error(f"Error updating class subject: {e}")
                messages.error(request, f'Error updating subject assignment: {str(e)}')
    else:
        form = ClassSubjectForm(instance=class_subject)
    
    context = {
        'form': form,
        'class_subject': class_subject,
        'title': f'Edit Subject Assignment - {class_subject.subject.name}',
        'submit_text': 'Update Assignment',
    }
    
    return render(request, 'academics/class_subjects/form.html', context)


# =============================================================================
# ACADEMIC PROGRESS VIEWS (CRUD + Print)
# =============================================================================

@login_required
def academic_progress_list(request):
    """List all academic progress records - HTMX loads data on page load"""
    
    filter_form = AcademicProgressFilterForm()
    
    try:
        initial_stats = academic_stats.get_progress_statistics()
    except Exception as e:
        logger.error(f"Error getting progress statistics: {e}")
        initial_stats = {}
    
    context = {
        'filter_form': filter_form,
        'stats': initial_stats,
        'AcademicProgress': AcademicProgress,
    }
    
    return render(request, 'academics/progress/list.html', context)


@login_required
def academic_progress_create(request):
    """Create new academic progress record"""
    
    if request.method == 'POST':
        form = AcademicProgressForm(request.POST)
        if form.is_valid():
            try:
                progress = form.save()
                
                # ✅ Audit trail automatically handled by BaseModel
                
                messages.success(
                    request, 
                    f'Academic progress record created for {progress.student.get_full_name()}!'
                )
                return redirect('academics:progress_detail', pk=progress.pk)
                
            except Exception as e:
                logger.error(f"Error creating progress record: {e}")
                messages.error(request, f'Error creating progress record: {str(e)}')
    else:
        form = AcademicProgressForm()
    
    context = {
        'form': form,
        'title': 'Create Academic Progress Record',
        'submit_text': 'Create Progress Record',
    }
    
    return render(request, 'academics/progress/form.html', context)


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
def academic_progress_edit(request, pk):
    """Edit academic progress record"""
    
    progress = get_object_or_404(AcademicProgress, pk=pk)
    
    # Check if progress is finalized
    if progress.is_final:
        messages.warning(request, 'Cannot edit finalized progress records.')
        return redirect('academics:progress_detail', pk=pk)
    
    if request.method == 'POST':
        form = AcademicProgressForm(request.POST, instance=progress)
        if form.is_valid():
            try:
                progress = form.save()
                
                # ✅ Audit trail automatically handled by BaseModel
                
                messages.success(
                    request, 
                    f'Academic progress updated for {progress.student.get_full_name()}!'
                )
                return redirect('academics:progress_detail', pk=progress.pk)
                
            except Exception as e:
                logger.error(f"Error updating progress: {e}")
                messages.error(request, f'Error updating progress: {str(e)}')
    else:
        form = AcademicProgressForm(instance=progress)
    
    context = {
        'form': form,
        'progress': progress,
        'title': f'Edit Progress - {progress.student.get_full_name()}',
        'submit_text': 'Update Progress',
    }
    
    return render(request, 'academics/progress/form.html', context)


# =============================================================================
# HOLIDAY VIEWS (CRUD + Print)
# =============================================================================

@login_required
def holiday_list(request):
    """List all holidays - HTMX loads data on page load"""
    
    filter_form = HolidayFilterForm()
    
    try:
        initial_stats = academic_stats.get_holiday_statistics()
    except Exception as e:
        logger.error(f"Error getting holiday statistics: {e}")
        initial_stats = {}
    
    context = {
        'filter_form': filter_form,
        'stats': initial_stats,
        'Holiday': Holiday,
    }
    
    return render(request, 'academics/holidays/list.html', context)


@login_required
def holiday_create(request):
    """Create new holiday"""
    
    if request.method == 'POST':
        form = HolidayForm(request.POST)
        if form.is_valid():
            try:
                holiday = form.save()
                
                # ✅ Audit trail automatically handled by BaseModel
                
                messages.success(
                    request, 
                    f'Holiday "{holiday.name}" created successfully!'
                )
                return redirect('academics:holiday_detail', pk=holiday.pk)
                
            except Exception as e:
                logger.error(f"Error creating holiday: {e}")
                messages.error(request, f'Error creating holiday: {str(e)}')
    else:
        form = HolidayForm()
    
    context = {
        'form': form,
        'title': 'Create Holiday',
        'submit_text': 'Create Holiday',
    }
    
    return render(request, 'academics/holidays/form.html', context)


@login_required
def holiday_detail(request, pk):
    """View holiday details"""
    
    holiday = get_object_or_404(Holiday, pk=pk)
    
    # Calculate duration
    if holiday.end_date:
        duration = (holiday.end_date - holiday.start_date).days + 1
    else:
        duration = 1  # Single day holiday
    
    context = {
        'holiday': holiday,
        'duration': duration,
    }
    
    return render(request, 'academics/holidays/detail.html', context)


@login_required
def holiday_edit(request, pk):
    """Edit holiday"""
    
    holiday = get_object_or_404(Holiday, pk=pk)
    
    if request.method == 'POST':
        form = HolidayForm(request.POST, instance=holiday)
        if form.is_valid():
            try:
                holiday = form.save()
                
                # ✅ Audit trail automatically handled by BaseModel
                
                messages.success(
                    request, 
                    f'Holiday "{holiday.name}" updated successfully!'
                )
                return redirect('academics:holiday_detail', pk=holiday.pk)
                
            except Exception as e:
                logger.error(f"Error updating holiday: {e}")
                messages.error(request, f'Error updating holiday: {str(e)}')
    else:
        form = HolidayForm(instance=holiday)
    
    context = {
        'form': form,
        'holiday': holiday,
        'title': f'Edit {holiday.name}',
        'submit_text': 'Update Holiday',
    }
    
    return render(request, 'academics/holidays/form.html', context)


@login_required
def class_subject_print_view(request):
    """Generate printable class subject list with selected fields"""
    
    selected_fields = request.GET.getlist('fields')
    if not selected_fields:
        selected_fields = ['class_instance', 'subject', 'teacher', 'hours_per_week', 'is_optional', 'is_active']
    
    include_stats = request.GET.get('include_stats') == 'true'
    landscape_mode = request.GET.get('landscape') == 'true'
    
    # Get filter parameters
    query = request.GET.get('q', '')
    class_instance = request.GET.get('class_instance', '')
    subject = request.GET.get('subject', '')
    teacher = request.GET.get('teacher', '')
    is_optional = request.GET.get('is_optional', '')
    is_active = request.GET.get('is_active', '')
    
    # Build queryset
    class_subjects = ClassSubject.objects.select_related(
        'class_instance', 'subject', 'teacher', 'class_instance__academic_level'
    ).order_by('class_instance__academic_level__order', 'class_instance__section', 'subject__name')
    
    # Apply filters
    if query:
        class_subjects = class_subjects.filter(
            Q(subject__name__icontains=query) |
            Q(subject__abbreviation__icontains=query) |
            Q(class_instance__academic_level__name__icontains=query)
        )
    
    if class_instance:
        class_subjects = class_subjects.filter(class_instance_id=class_instance)
    
    if subject:
        class_subjects = class_subjects.filter(subject_id=subject)
    
    if teacher:
        class_subjects = class_subjects.filter(teacher_id=teacher)
    
    if is_optional:
        class_subjects = class_subjects.filter(is_optional=(is_optional == 'true'))
    
    if is_active:
        class_subjects = class_subjects.filter(is_active=(is_active == 'true'))
    
    # Calculate stats
    stats = None
    if include_stats:
        total = class_subjects.count()
        active_count = class_subjects.filter(is_active=True).count()
        total_hours = class_subjects.aggregate(Sum('hours_per_week'))['hours_per_week__sum'] or 0
        
        stats = {
            'total': total,
            'active': active_count,
            'compulsory': class_subjects.filter(is_optional=False).count(),
            'optional': class_subjects.filter(is_optional=True).count(),
            'total_weekly_hours': total_hours,
        }
    
    # Field display names
    field_names = {
        'class_instance': 'Class',
        'subject': 'Subject',
        'teacher': 'Teacher',
        'hours_per_week': 'Hours/Week',
        'total_hours': 'Total Hours',
        'is_optional': 'Optional',
        'is_active': 'Active',
        'continuous_assessment_weight': 'CA Weight %',
        'final_exam_weight': 'Exam Weight %',
        'textbook': 'Textbook',
    }
    
    selected_field_names = [field_names.get(field, field.replace('_', ' ').title()) for field in selected_fields]
    
    context = {
        'class_subjects': class_subjects,
        'stats': stats,
        'now': timezone.now(),
        'selected_fields': selected_fields,
        'selected_field_names': selected_field_names,
        'field_names': field_names,
        'landscape': landscape_mode,
        'title': 'Class Subjects Report',
    }
    
    return render(request, 'academics/class_subjects/print.html', context)


# =============================================================================
# ACADEMIC PROGRESS VIEWS
# =============================================================================

@login_required
def academic_progress_list(request):
    """List all academic progress records - HTMX loads data on page load"""
    
    filter_form = AcademicProgressFilterForm()
    
    try:
        initial_stats = academic_stats.get_progress_statistics()
    except Exception as e:
        logger.error(f"Error getting progress statistics: {e}")
        initial_stats = {}
    
    context = {
        'filter_form': filter_form,
        'stats': initial_stats,
        'AcademicProgress': AcademicProgress,
    }
    
    return render(request, 'academics/progress/list.html', context)


@login_required
def academic_progress_print_view(request):
    """Generate printable academic progress list with selected fields"""
    
    selected_fields = request.GET.getlist('fields')
    if not selected_fields:
        selected_fields = ['student', 'academic_session', 'overall_grade', 'percentage', 'progress_status', 'promotion_decision']
    
    include_stats = request.GET.get('include_stats') == 'true'
    landscape_mode = request.GET.get('landscape') == 'true'
    
    # Get filter parameters
    query = request.GET.get('q', '')
    academic_session = request.GET.get('academic_session', '')
    progress_status = request.GET.get('progress_status', '')
    promotion_decision = request.GET.get('promotion_decision', '')
    is_eligible_for_promotion = request.GET.get('is_eligible_for_promotion', '')
    is_final = request.GET.get('is_final', '')
    
    # Build queryset
    progress_records = AcademicProgress.objects.select_related(
        'student', 'academic_session', 'class_enrollment'
    ).order_by('-academic_session__start_date', 'student__last_name')
    
    # Apply filters
    if query:
        progress_records = progress_records.filter(
            Q(student__first_name__icontains=query) |
            Q(student__last_name__icontains=query) |
            Q(student__admission_number__icontains=query)
        )
    
    if academic_session:
        progress_records = progress_records.filter(academic_session_id=academic_session)
    
    if progress_status:
        progress_records = progress_records.filter(progress_status=progress_status)
    
    if promotion_decision:
        progress_records = progress_records.filter(promotion_decision=promotion_decision)
    
    if is_eligible_for_promotion:
        progress_records = progress_records.filter(is_eligible_for_promotion=(is_eligible_for_promotion == 'true'))
    
    if is_final:
        progress_records = progress_records.filter(is_final=(is_final == 'true'))
    
    # Calculate stats
    stats = None
    if include_stats:
        total = progress_records.count()
        finalized_count = progress_records.filter(is_final=True).count()
        eligible_count = progress_records.filter(is_eligible_for_promotion=True).count()
        
        stats = {
            'total': total,
            'finalized': finalized_count,
            'eligible_for_promotion': eligible_count,
            'avg_percentage': round(progress_records.aggregate(Avg('percentage'))['percentage__avg'] or 0, 1),
        }
    
    # Field display names
    field_names = {
        'student': 'Student',
        'academic_session': 'Academic Session',
        'overall_grade': 'Overall Grade',
        'gpa': 'GPA',
        'percentage': 'Percentage',
        'progress_status': 'Progress Status',
        'promotion_decision': 'Promotion Decision',
        'is_eligible_for_promotion': 'Eligible for Promotion',
        'attendance_percentage': 'Attendance %',
        'subjects_passed': 'Subjects Passed',
        'subjects_failed': 'Subjects Failed',
        'is_final': 'Finalized',
    }
    
    selected_field_names = [field_names.get(field, field.replace('_', ' ').title()) for field in selected_fields]
    
    context = {
        'progress_records': progress_records,
        'stats': stats,
        'now': timezone.now(),
        'selected_fields': selected_fields,
        'selected_field_names': selected_field_names,
        'field_names': field_names,
        'landscape': landscape_mode,
        'title': 'Academic Progress Report',
    }
    
    return render(request, 'academics/progress/print.html', context)


# =============================================================================
# HOLIDAY VIEWS
# =============================================================================

@login_required
def holiday_list(request):
    """List all holidays - HTMX loads data on page load"""
    
    filter_form = HolidayFilterForm()
    
    try:
        initial_stats = academic_stats.get_holiday_statistics()
    except Exception as e:
        logger.error(f"Error getting holiday statistics: {e}")
        initial_stats = {}
    
    context = {
        'filter_form': filter_form,
        'stats': initial_stats,
        'Holiday': Holiday,
    }
    
    return render(request, 'academics/holidays/list.html', context)


@login_required
def holiday_print_view(request):
    """Generate printable holiday list with selected fields"""
    
    selected_fields = request.GET.getlist('fields')
    if not selected_fields:
        selected_fields = ['name', 'holiday_type', 'start_date', 'end_date', 'is_school_closed', 'academic_session']
    
    include_stats = request.GET.get('include_stats') == 'true'
    landscape_mode = request.GET.get('landscape') == 'true'
    
    # Get filter parameters
    query = request.GET.get('q', '')
    holiday_type = request.GET.get('holiday_type', '')
    is_school_closed = request.GET.get('is_school_closed', '')
    academic_session = request.GET.get('academic_session', '')
    
    # Build queryset
    holidays = Holiday.objects.select_related('academic_session').order_by('start_date')
    
    # Apply filters
    if query:
        holidays = holidays.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query)
        )
    
    if holiday_type:
        holidays = holidays.filter(holiday_type=holiday_type)
    
    if is_school_closed:
        holidays = holidays.filter(is_school_closed=(is_school_closed == 'true'))
    
    if academic_session:
        holidays = holidays.filter(academic_session_id=academic_session)
    
    # Calculate stats
    stats = None
    if include_stats:
        total = holidays.count()
        school_closed_count = holidays.filter(is_school_closed=True).count()
        total_days = sum(holiday.duration_days for holiday in holidays)
        
        stats = {
            'total': total,
            'school_closed': school_closed_count,
            'school_open': total - school_closed_count,
            'total_holiday_days': total_days,
        }
    
    # Field display names
    field_names = {
        'name': 'Holiday Name',
        'holiday_type': 'Holiday Type',
        'start_date': 'Start Date',
        'end_date': 'End Date',
        'duration_days': 'Duration (Days)',
        'is_school_closed': 'School Closed',
        'is_partial_closure': 'Partial Closure',
        'affects_attendance': 'Affects Attendance',
        'is_recurring': 'Recurring',
        'academic_session': 'Academic Session',
        'description': 'Description',
    }
    
    selected_field_names = [field_names.get(field, field.replace('_', ' ').title()) for field in selected_fields]
    
    context = {
        'holidays': holidays,
        'stats': stats,
        'now': timezone.now(),
        'selected_fields': selected_fields,
        'selected_field_names': selected_field_names,
        'field_names': field_names,
        'landscape': landscape_mode,
        'title': 'Holidays Report',
    }
    
    return render(request, 'academics/holidays/print.html', context)


# =============================================================================
# HTMX SEARCH VIEWS (AJAX)
# =============================================================================

@login_required
def academic_session_search(request):
    """HTMX search for academic sessions"""
    
    filter_form = AcademicSessionFilterForm(request.GET)
    sessions = AcademicSession.objects.order_by('-start_date', 'term_number')
    
    if filter_form.is_valid():
        data = filter_form.cleaned_data
        
        if data.get('q'):
            sessions = sessions.filter(
                Q(year_name__icontains=data['q']) |
                Q(term_name__icontains=data['q']) |
                Q(description__icontains=data['q'])
            )
        
        if data.get('is_current') is not None:
            sessions = sessions.filter(is_current=data['is_current'])
        
        if data.get('is_active') is not None:
            sessions = sessions.filter(is_active=data['is_active'])
        
        if data.get('is_academically_closed') is not None:
            sessions = sessions.filter(is_academically_closed=data['is_academically_closed'])
        
        if data.get('is_special_session') is not None:
            sessions = sessions.filter(is_special_session=data['is_special_session'])
        
        if data.get('period_type'):
            sessions = sessions.filter(period_type=data['period_type'])
        
        if data.get('year_name'):
            sessions = sessions.filter(year_name__icontains=data['year_name'])
        
        if data.get('start_date_from'):
            sessions = sessions.filter(start_date__gte=data['start_date_from'])
        
        if data.get('start_date_to'):
            sessions = sessions.filter(start_date__lte=data['start_date_to'])
    
    # Get stats for filtered results
    try:
        stats = academic_stats.get_academic_session_statistics()
        stats['filtered_count'] = sessions.count()
    except Exception as e:
        logger.error(f"Error getting filtered session stats: {e}")
        stats = {'filtered_count': sessions.count()}
    
    context = {
        'sessions': sessions[:50],  # Limit for performance
        'stats': stats,
        'has_more': sessions.count() > 50,
    }
    
    return render(request, 'academics/sessions/partials/session_list.html', context)

