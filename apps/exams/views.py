# exams/views.py 

"""
Examination Management Views - Part 1

This part contains:
- Dashboard
- Exam Category Views (List, Detail, Create, Edit, Delete, Actions, Print/Export)
- Grading System Views (List, Detail, Create, Edit, Delete, Actions, Print/Export)
- Grading Range Views (Create, Edit, Delete)

All views use SweetAlert2 for notifications via Django messages
Uses core.utils for timezone-aware operations
Audit trail automatically handled by BaseModel

Pattern follows academics/views.py:
- Helper functions for filtering
- HTMX response headers
- Clean separation of concerns
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.contrib import messages
from django.db.models import Q, Count, Sum, Avg, Prefetch, F, Max, Min
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from django.db import transaction
from django.core.exceptions import ValidationError, PermissionDenied
from datetime import timedelta, date, datetime
from decimal import Decimal, InvalidOperation
import logging

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# Import timezone utilities from core
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
    ExamCategory,
    GradingSystem,
    GradingRange,
    ClassGradingSystem,
    Examination,
    ExamRegistration,
    StudentExamResult,
    ExamAnalytics,
)

from .forms import (
    ExamCategoryForm,
    ExamCategoryFilterForm,
    GradingSystemForm,
    GradingSystemFilterForm,
    GradingRangeForm,
    GradingRangeFormSet,
    ClassGradingSystemForm,
    ClassGradingSystemFilterForm,
    ExaminationForm,
    ExaminationFilterForm,
    ExamRegistrationForm,
    StudentExamResultForm,
    StudentExamResultFilterForm,
    GradeLockForm,
    GradeUnlockForm,
    ResultPublishForm,
    BulkResultEntryForm,
    ExaminationFilterForm,
    ExamRegistrationFilterForm,
    StudentExamResultFilterForm,
)

from students.models import Student
from academics.models import Class, Subject, AcademicSession, AcademicLevel
from hr.models import Staff

logger = logging.getLogger(__name__)


# =============================================================================
# DASHBOARD
# =============================================================================

@login_required
def exams_dashboard(request):
    """Main exams dashboard with overview statistics"""
    
    try:
        today = get_school_today()
        current_session = get_active_academic_session()
        
        # Get statistics
        total_categories = ExamCategory.objects.filter(is_active=True).count()
        total_grading_systems = GradingSystem.objects.filter(is_active=True).count()
        total_examinations = Examination.objects.count()
        upcoming_exams = Examination.objects.filter(
            exam_date__gte=today,
            status__in=['PLANNED', 'SCHEDULED']
        ).count()
        ongoing_exams = Examination.objects.filter(status='ONGOING').count()
        completed_exams = Examination.objects.filter(status='COMPLETED').count()
        
        # Results statistics
        total_results = StudentExamResult.objects.count()
        published_results = StudentExamResult.objects.filter(is_published=True).count()
        locked_grades = StudentExamResult.objects.filter(is_grade_locked=True).count()
        pending_results = StudentExamResult.objects.filter(
            status='SUBMITTED',
            is_published=False
        ).count()
        
        # Current session statistics
        session_stats = {}
        if current_session:
            session_exams = Examination.objects.filter(academic_session=current_session)
            session_stats = {
                'total_exams': session_exams.count(),
                'completed': session_exams.filter(status='COMPLETED').count(),
                'ongoing': session_exams.filter(status='ONGOING').count(),
                'upcoming': session_exams.filter(
                    exam_date__gte=today,
                    status__in=['PLANNED', 'SCHEDULED']
                ).count(),
            }
        
        overview = {
            'total_categories': total_categories,
            'total_grading_systems': total_grading_systems,
            'total_examinations': total_examinations,
            'upcoming_exams': upcoming_exams,
            'ongoing_exams': ongoing_exams,
            'completed_exams': completed_exams,
            'total_results': total_results,
            'published_results': published_results,
            'locked_grades': locked_grades,
            'pending_results': pending_results,
        }
        
    except Exception as e:
        logger.error(f"Error getting dashboard statistics: {e}")
        overview = {}
        current_session = None
        session_stats = {}
    
    # Get recent activities
    recent_examinations = Examination.objects.select_related(
        'subject', 'academic_session', 'exam_category'
    ).order_by('-created_at')[:10]
    
    recent_results = StudentExamResult.objects.select_related(
        'student', 'examination__subject'
    ).order_by('-created_at')[:10]
    
    # Get upcoming examinations
    upcoming_examinations = Examination.objects.filter(
        exam_date__gte=today,
        status__in=['PLANNED', 'SCHEDULED']
    ).select_related('subject', 'exam_category').order_by('exam_date', 'start_time')[:10]
    
    # Items needing attention
    unpublished_results = Examination.objects.filter(
        status='COMPLETED',
        results_published=False
    ).annotate(
        results_count=Count('student_results')
    ).filter(results_count__gt=0).order_by('exam_date')[:10]
    
    unlocked_published_results = StudentExamResult.objects.filter(
        is_published=True,
        is_grade_locked=False
    ).select_related('student', 'examination').order_by('-publication_date')[:10]
    
    context = {
        'overview': overview,
        'current_session': current_session,
        'session_stats': session_stats,
        'recent_examinations': recent_examinations,
        'recent_results': recent_results,
        'upcoming_examinations': upcoming_examinations,
        'unpublished_results': unpublished_results,
        'unlocked_published_results': unlocked_published_results,
    }
    
    return render(request, 'exams/dashboard.html', context)


# =============================================================================
# HELPER FUNCTIONS FOR FILTERING
# =============================================================================

def get_filtered_exam_categories(request):
    """Helper function to get filtered exam categories queryset"""
    categories = ExamCategory.objects.prefetch_related(
        'applicable_levels', 'valid_sessions'
    ).order_by('category_type', 'name')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    category_type = request.GET.get('category_type', '')
    frequency = request.GET.get('frequency', '')
    is_active = request.GET.get('is_active', '')
    curriculum_compatibility = request.GET.get('curriculum_compatibility', '')
    requires_registration = request.GET.get('requires_registration', '')
    
    # Apply text search
    if query:
        categories = categories.filter(
            Q(name__icontains=query) |
            Q(abbreviation__icontains=query) |
            Q(code__icontains=query) |
            Q(description__icontains=query)
        )
    
    # Apply filters
    if category_type:
        categories = categories.filter(category_type=category_type)
    if frequency:
        categories = categories.filter(frequency=frequency)
    if is_active:
        categories = categories.filter(is_active=(is_active.lower() == 'true'))
    if curriculum_compatibility:
        categories = categories.filter(curriculum_compatibility=curriculum_compatibility)
    if requires_registration:
        categories = categories.filter(requires_registration=(requires_registration.lower() == 'true'))
    
    return categories


def get_filtered_grading_systems(request):
    """Helper function to get filtered grading systems queryset"""
    systems = GradingSystem.objects.prefetch_related(
        'applicable_levels', 'applicable_subjects', 'ranges'
    ).annotate(
        ranges_count=Count('ranges')
    ).order_by('grading_type', 'name')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    grading_type = request.GET.get('grading_type', '')
    scale_type = request.GET.get('scale_type', '')  # ✅ ADDED
    is_active = request.GET.get('is_active', '')
    is_default = request.GET.get('is_default', '')
    uses_gpa = request.GET.get('uses_gpa', '')
    curriculum_compatibility = request.GET.get('curriculum_compatibility', '')
    
    # Apply text search
    if query:
        systems = systems.filter(
            Q(name__icontains=query) |
            Q(code__icontains=query) |
            Q(description__icontains=query)
        )
    
    # Apply filters
    if grading_type:
        systems = systems.filter(grading_type=grading_type)
    if scale_type:  # ✅ ADDED
        systems = systems.filter(scale_type=scale_type)
    if is_active:
        systems = systems.filter(is_active=(is_active.lower() == 'true'))
    if is_default:
        systems = systems.filter(is_default=(is_default.lower() == 'true'))
    if uses_gpa:
        systems = systems.filter(uses_gpa=(uses_gpa.lower() == 'true'))
    if curriculum_compatibility:
        systems = systems.filter(curriculum_compatibility=curriculum_compatibility)
    
    return systems

def get_filtered_class_grading_systems(request):
    """Helper function to get filtered class grading system assignments"""
    assignments = ClassGradingSystem.objects.select_related(
        'class_instance__academic_level', 'grading_system', 'academic_session', 'subject'
    ).order_by('-academic_session__start_date', 'class_instance__academic_level__order', 'priority')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    class_id = request.GET.get('class_id', '')
    academic_session = request.GET.get('academic_session', '')
    grading_system = request.GET.get('grading_system', '')
    subject = request.GET.get('subject', '')
    is_active = request.GET.get('is_active', '')
    
    # Apply text search
    if query:
        assignments = assignments.filter(
            Q(class_instance__academic_level__name__icontains=query) |
            Q(grading_system__name__icontains=query) |
            Q(subject__name__icontains=query)
        )
    
    # Apply filters
    if class_id:
        assignments = assignments.filter(class_instance_id=class_id)
    if academic_session:
        assignments = assignments.filter(academic_session_id=academic_session)
    if grading_system:
        assignments = assignments.filter(grading_system_id=grading_system)
    if subject:
        assignments = assignments.filter(subject_id=subject)
    if is_active:
        assignments = assignments.filter(is_active=(is_active.lower() == 'true'))
    
    return assignments

def get_filtered_examinations(request):
    """Helper function to get filtered examinations queryset"""
    examinations = Examination.objects.select_related(
        'subject', 'academic_session', 'exam_category', 'grading_system', 'classroom'
    ).prefetch_related('target_classes', 'invigilators').order_by('-exam_date', 'start_time')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    academic_session = request.GET.get('academic_session', '')
    exam_category = request.GET.get('exam_category', '')
    subject = request.GET.get('subject', '')
    status = request.GET.get('status', '')
    exam_mode = request.GET.get('exam_mode', '')  # ✅ ADDED
    exam_date_from = request.GET.get('exam_date_from', '')
    exam_date_to = request.GET.get('exam_date_to', '')
    
    # Apply text search
    if query:
        examinations = examinations.filter(
            Q(name__icontains=query) |
            Q(code__icontains=query) |
            Q(description__icontains=query) |
            Q(subject__name__icontains=query)
        )
    
    # Apply filters
    if academic_session:
        examinations = examinations.filter(academic_session_id=academic_session)
    if exam_category:
        examinations = examinations.filter(exam_category_id=exam_category)
    if subject:
        examinations = examinations.filter(subject_id=subject)
    if status:
        examinations = examinations.filter(status=status)
    if exam_mode:  # ✅ ADDED
        examinations = examinations.filter(exam_mode=exam_mode)
    if exam_date_from:
        try:
            from_date = datetime.strptime(exam_date_from, '%Y-%m-%d').date()
            examinations = examinations.filter(exam_date__gte=from_date)
        except (ValueError, TypeError):
            pass
    if exam_date_to:
        try:
            to_date = datetime.strptime(exam_date_to, '%Y-%m-%d').date()
            examinations = examinations.filter(exam_date__lte=to_date)
        except (ValueError, TypeError):
            pass
    
    return examinations


def get_filtered_student_results(request):
    """Helper function to get filtered student exam results queryset"""
    results = StudentExamResult.objects.select_related(
        'student', 'examination__subject', 'examination__academic_session'
    ).order_by('-examination__exam_date', 'student__first_name', 'student__last_name')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    examination = request.GET.get('examination', '')
    status = request.GET.get('status', '')
    is_published = request.GET.get('is_published', '')
    is_grade_locked = request.GET.get('is_grade_locked', '')
    is_pass = request.GET.get('is_pass', '')
    min_score = request.GET.get('min_score', '')  # ✅ ADDED
    max_score = request.GET.get('max_score', '')  # ✅ ADDED
    class_instance = request.GET.get('class_instance', '')  # ✅ ADDED
    
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
                    Q(student__admission_number__icontains=word)
                )
                combined_q &= word_q
            results = results.filter(combined_q)
    
    # Apply filters
    if examination:
        results = results.filter(examination_id=examination)
    if status:
        results = results.filter(status=status)
    if is_published:
        results = results.filter(is_published=(is_published.lower() == 'true'))
    if is_grade_locked:
        results = results.filter(is_grade_locked=(is_grade_locked.lower() == 'true'))
    if is_pass:
        results = results.filter(is_pass=(is_pass.lower() == 'true'))
    
    # ✅ ADDED: Score range filters
    if min_score:
        try:
            min_val = Decimal(min_score)
            results = results.filter(score__gte=min_val)
        except (ValueError, TypeError, InvalidOperation):
            pass
    
    if max_score:
        try:
            max_val = Decimal(max_score)
            results = results.filter(score__lte=max_val)
        except (ValueError, TypeError, InvalidOperation):
            pass
    
    # ✅ ADDED: Class filter
    if class_instance:
        results = results.filter(
            student__class_enrollments__class_instance_id=class_instance,
            student__class_enrollments__is_active=True
        )
    
    return results


# ✅ ADDED: Missing helper for exam registrations
def get_filtered_exam_registrations(request):
    """Helper function to get filtered exam registrations queryset"""
    registrations = ExamRegistration.objects.select_related(
        'student', 'examination__subject', 'examination__academic_session', 'registered_by'
    ).order_by('-registration_date', 'student__first_name', 'student__last_name')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    examination = request.GET.get('examination', '')
    status = request.GET.get('registration_status', '')  # Note: changed from 'status' to 'registration_status'
    requires_assistance = request.GET.get('requires_assistance', '')
    payment_verified = request.GET.get('payment_verified', '')
    
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
                    Q(student__admission_number__icontains=word)
                )
                combined_q &= word_q
            registrations = registrations.filter(combined_q)
    
    # Apply filters
    if examination:
        registrations = registrations.filter(examination_id=examination)
    if status:
        registrations = registrations.filter(status=status)
    if requires_assistance:
        registrations = registrations.filter(requires_assistance=(requires_assistance.lower() == 'true'))
    if payment_verified:
        registrations = registrations.filter(payment_verified=(payment_verified.lower() == 'true'))
    
    return registrations


# =============================================================================
# EXAM CATEGORY VIEWS
# =============================================================================

@login_required
def exam_category_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""

    filter_form = ExamCategoryFilterForm(request.GET or None)

    categories = get_filtered_exam_categories(request)
    
    # Calculate statistics
    stats = {
        'total': categories.count(),
        'active': categories.filter(is_active=True).count(),
        'inactive': categories.filter(is_active=False).count(),
        'formative': categories.filter(category_type='FORMATIVE').count(),
        'summative': categories.filter(category_type='SUMMATIVE').count(),
        'internal': categories.filter(category_type='INTERNAL').count(),
        'external': categories.filter(category_type='EXTERNAL').count(),
    }
    
    # Pagination
    paginator = Paginator(categories, 20)
    page_number = request.GET.get('page', 1)
    categories_page = paginator.get_page(page_number)
    
    # Detect HTMX request
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'categories_page': categories_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    # Return appropriate template
    if is_htmx:
        return render(request, 'exams/categories/partials/_category_results.html', context)
    else:
        return render(request, 'exams/categories/list.html', context)


@login_required
def exam_category_detail(request, pk):
    """View exam category details"""
    category = get_object_or_404(ExamCategory, pk=pk)
    
    # Get related examinations
    examinations = category.examinations.select_related(
        'subject', 'academic_session'
    ).order_by('-exam_date')[:20]
    
    # Statistics
    stats = {
        'total_exams': category.examinations.count(),
        'active_exams': category.examinations.filter(status='ONGOING').count(),
        'completed_exams': category.examinations.filter(status='COMPLETED').count(),
        'upcoming_exams': category.examinations.filter(
            exam_date__gte=get_school_today(),
            status__in=['PLANNED', 'SCHEDULED']
        ).count(),
    }
    
    context = {
        'category': category,
        'examinations': examinations,
        'stats': stats,
    }
    
    return render(request, 'exams/categories/detail.html', context)


@login_required
def exam_category_create(request):
    """Create new exam category"""
    if request.method == 'POST':
        form = ExamCategoryForm(request.POST)
        if form.is_valid():
            try:
                category = form.save()
                messages.success(request, f'Exam category "{category.name}" created successfully')
                return redirect('exams:category_detail', pk=category.pk)
            except Exception as e:
                logger.error(f"Error creating exam category: {e}")
                messages.error(request, f'Error creating exam category: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below')
    else:
        form = ExamCategoryForm()
    
    context = {
        'form': form,
        'title': 'Create Exam Category',
        'submit_text': 'Create Category',
    }
    
    return render(request, 'exams/categories/form.html', context)


@login_required
def exam_category_edit(request, pk):
    """Edit exam category"""
    category = get_object_or_404(ExamCategory, pk=pk)
    
    # Calculate statistics for the category
    stats = {
        'total_exams': category.examinations.count(),
        'active_exams': category.examinations.filter(status='ONGOING').count(),
        'completed_exams': category.examinations.filter(status='COMPLETED').count(),
        'upcoming_exams': category.examinations.filter(
            exam_date__gte=get_school_today(),
            status__in=['PLANNED', 'SCHEDULED']
        ).count(),
        'planned_exams': category.examinations.filter(status='PLANNED').count(),
        'scheduled_exams': category.examinations.filter(status='SCHEDULED').count(),
    }
    
    if request.method == 'POST':
        form = ExamCategoryForm(request.POST, instance=category)
        if form.is_valid():
            try:
                category = form.save()
                messages.success(request, f'Exam category "{category.name}" updated successfully')
                return redirect('exams:category_detail', pk=category.pk)
            except Exception as e:
                logger.error(f"Error updating exam category: {e}")
                messages.error(request, f'Error updating exam category: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below')
    else:
        form = ExamCategoryForm(instance=category)
    
    context = {
        'form': form,
        'category': category,
        'title': 'Edit Exam Category',
        'submit_text': 'Update Category',
        'stats': stats,
    }
    
    return render(request, 'exams/categories/form.html', context)


@login_required
def exam_category_delete(request, pk):
    """Delete exam category with HTMX support"""
    category = get_object_or_404(ExamCategory, pk=pk)
    
    if request.method == 'POST':
        # Check if category has examinations
        if category.examinations.exists():
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Trigger'] = 'showAlert'
                response['HX-Trigger-Data'] = '{"type": "error", "message": "Cannot delete category with existing examinations"}'
                return response
            else:
                messages.error(request, 'Cannot delete category with existing examinations')
                return redirect('exams:category_detail', pk=pk)
        
        try:
            category_name = category.name
            category.delete()
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Redirect'] = reverse('exams:category_list')
                response['HX-Trigger'] = 'showAlert'
                response['HX-Trigger-Data'] = f'{{"type": "success", "message": "Exam category \\"{category_name}\\" deleted successfully"}}'
                return response
            else:
                messages.success(request, f'Exam category "{category_name}" deleted successfully')
                return redirect('exams:category_list')
                
        except Exception as e:
            logger.error(f"Error deleting exam category: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Trigger'] = 'showAlert'
                response['HX-Trigger-Data'] = f'{{"type": "error", "message": "Error deleting exam category: {str(e)}"}}'
                return response
            else:
                messages.error(request, f'Error deleting exam category: {str(e)}')
                return redirect('exams:category_detail', pk=pk)


@login_required
def exam_category_toggle_active(request, pk):
    """Toggle exam category active status with HTMX support"""
    category = get_object_or_404(ExamCategory, pk=pk)
    
    if request.method == 'POST':
        try:
            category.is_active = not category.is_active
            category.save()
            
            status = "activated" if category.is_active else "deactivated"
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Redirect'] = reverse('exams:category_detail', kwargs={'pk': pk})
                response['HX-Trigger'] = 'showAlert'
                response['HX-Trigger-Data'] = f'{{"type": "success", "message": "Category \\"{category.name}\\" {status} successfully"}}'
                return response
            else:
                messages.success(request, f'Category "{category.name}" {status} successfully')
                return redirect('exams:category_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error toggling category: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Trigger'] = 'showAlert'
                response['HX-Trigger-Data'] = f'{{"type": "error", "message": "Error: {str(e)}"}}'
                return response
            else:
                messages.error(request, f'Error: {str(e)}')
                return redirect('exams:category_detail', pk=pk)


@login_required
def exam_category_print_detail(request, pk):
    """Print single exam category details"""
    category = get_object_or_404(ExamCategory, pk=pk)
    
    context = {
        'category': category,
        'print_date': get_school_current_time(),
    }
    
    return render(request, 'exams/categories/print_detail.html', context)


@login_required
def exam_category_print_view(request):
    """Print filtered exam categories"""
    categories = get_filtered_exam_categories(request)
    
    context = {
        'categories': categories,
        'print_date': get_school_current_time(),
    }
    
    return render(request, 'exams/categories/print_list.html', context)


@login_required
def export_exam_categories_excel(request):
    """Export exam categories to Excel"""
    categories = get_filtered_exam_categories(request)
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Exam Categories"
    
    # Define styles
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_alignment = Alignment(horizontal="center", vertical="center")
    
    # Headers
    headers = [
        '#', 'Name', 'Code', 'Type', 'Frequency', 'Weight %',
        'Requires Registration', 'Active', 'Curriculum'
    ]
    ws.append(headers)
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
    
    # Data rows
    for idx, category in enumerate(categories, start=1):
        ws.append([
            idx,
            category.name,
            category.code,
            category.get_category_type_display(),
            category.get_frequency_display(),
            float(category.weight_percentage),
            'Yes' if category.requires_registration else 'No',
            'Yes' if category.is_active else 'No',
            category.get_curriculum_compatibility_display(),
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
    filename = f"exam_categories_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


# =============================================================================
# GRADING SYSTEM VIEWS
# =============================================================================

@login_required
def grading_system_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""

    filter_form = GradingSystemFilterForm(request.GET or None)

    systems = get_filtered_grading_systems(request)
    
    # Calculate statistics
    stats = {
        'total': systems.count(),
        'active': systems.filter(is_active=True).count(),
        'default': systems.filter(is_default=True).count(),
        'with_gpa': systems.filter(uses_gpa=True).count(),
        'letter_grade': systems.filter(grading_type='LETTER').count(),
        'numerical': systems.filter(grading_type='NUMERICAL').count(),
    }
    
    # Pagination
    paginator = Paginator(systems, 20)
    page_number = request.GET.get('page', 1)
    systems_page = paginator.get_page(page_number)
    
    # Detect HTMX request
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'systems_page': systems_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    # Return appropriate template
    if is_htmx:
        return render(request, 'exams/grading_systems/partials/_system_results.html', context)
    else:
        return render(request, 'exams/grading_systems/list.html', context)


@login_required
def grading_system_detail(request, pk):
    """View grading system details"""
    system = get_object_or_404(GradingSystem, pk=pk)
    
    # Get grading ranges ordered by score (descending)
    ranges = system.ranges.all().order_by('-min_score')
    
    # Get class assignments
    class_assignments = system.class_assignments.select_related(
        'class_instance__academic_level', 'academic_session'
    ).filter(is_active=True).order_by('-academic_session__start_date')[:20]
    
    # Get examinations using this system
    examinations = system.examinations.select_related(
        'subject', 'academic_session'
    ).order_by('-exam_date')[:20]
    
    # Statistics
    stats = {
        'total_ranges': ranges.count(),
        'class_assignments': system.class_assignments.filter(is_active=True).count(),
        'examinations': system.examinations.count(),
        'passing_ranges': ranges.filter(is_passing_grade=True).count(),
        'failing_ranges': ranges.filter(is_passing_grade=False).count(),
    }
    
    # Check for coverage gaps
    coverage_status = _check_grading_system_coverage(system, ranges)
    
    context = {
        'system': system,
        'ranges': ranges,
        'class_assignments': class_assignments,
        'examinations': examinations,
        'stats': stats,
        'coverage_status': coverage_status,
    }
    
    return render(request, 'exams/grading_systems/detail.html', context)


@login_required
def grading_system_create(request):
    """Create new grading system with inline grading ranges"""
    if request.method == 'POST':
        form = GradingSystemForm(request.POST)
        formset = GradingRangeFormSet(request.POST)
        
        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    # Save grading system
                    system = form.save()
                    
                    # Save grading ranges
                    formset.instance = system
                    formset.save()
                    
                    messages.success(
                        request, 
                        f'Grading system "{system.name}" created successfully with {formset.total_form_count() - formset.initial_form_count()} grade ranges'
                    )
                    return redirect('exams:grading_system_detail', pk=system.pk)
            except Exception as e:
                logger.error(f"Error creating grading system: {e}", exc_info=True)
                messages.error(request, f'Error creating grading system: {str(e)}')
        else:
            # Consolidate form and formset errors
            if form.errors:
                messages.error(request, 'Please correct the errors in the grading system details')
            if formset.errors or formset.non_form_errors():
                messages.error(request, 'Please correct the errors in the grade ranges')
    else:
        form = GradingSystemForm()
        formset = GradingRangeFormSet()
    
    context = {
        'form': form,
        'formset': formset,
        'title': 'Create Grading System',
        'submit_text': 'Create Grading System',
        'is_edit': False,
    }
    
    return render(request, 'exams/grading_systems/form.html', context)


@login_required
def grading_system_edit(request, pk):
    """Edit grading system with inline grading ranges"""
    system = get_object_or_404(GradingSystem, pk=pk)
    
    # Calculate statistics for the system
    stats = {
        'total_ranges': system.ranges.count(),
        'class_assignments': system.class_assignments.filter(is_active=True).count(),
        'examinations': system.examinations.count(),
        'active_assignments': system.class_assignments.filter(
            is_active=True,
            effective_date__lte=get_school_today()
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=get_school_today())
        ).count(),
        'locked_grades_count': StudentExamResult.objects.filter(
            examination__grading_system=system,
            is_grade_locked=True
        ).count() if hasattr(StudentExamResult, 'objects') else 0,
    }
    
    # Warning if system is in use
    has_locked_grades = stats['locked_grades_count'] > 0
    has_examinations = stats['examinations'] > 0
    
    if request.method == 'POST':
        form = GradingSystemForm(request.POST, instance=system)
        formset = GradingRangeFormSet(request.POST, instance=system)
        
        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    # Save grading system
                    system = form.save()
                    
                    # Save grading ranges
                    formset.save()
                    
                    # Show warning if grades are locked
                    if has_locked_grades:
                        messages.warning(
                            request,
                            f'Note: This system has {stats["locked_grades_count"]} locked grades. '
                            'Changes to grade ranges will NOT affect locked grades.'
                        )
                    
                    messages.success(
                        request, 
                        f'Grading system "{system.name}" updated successfully'
                    )
                    return redirect('exams:grading_system_detail', pk=system.pk)
            except Exception as e:
                logger.error(f"Error updating grading system: {e}", exc_info=True)
                messages.error(request, f'Error updating grading system: {str(e)}')
        else:
            # Consolidate form and formset errors
            if form.errors:
                messages.error(request, 'Please correct the errors in the grading system details')
            if formset.errors or formset.non_form_errors():
                messages.error(request, 'Please correct the errors in the grade ranges')
    else:
        form = GradingSystemForm(instance=system)
        formset = GradingRangeFormSet(instance=system)
    
    context = {
        'form': form,
        'formset': formset,
        'system': system,
        'title': f'Edit {system.name}',
        'submit_text': 'Update Grading System',
        'is_edit': True,
        'stats': stats,
        'has_locked_grades': has_locked_grades,
        'has_examinations': has_examinations,
    }
    
    return render(request, 'exams/grading_systems/form.html', context)


@login_required
def grading_system_delete(request, pk):
    """Delete grading system with HTMX support"""
    system = get_object_or_404(GradingSystem, pk=pk)
    
    if request.method == 'POST':
        # Check if system is default
        if system.is_default:
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Trigger'] = 'showAlert'
                response['HX-Trigger-Data'] = '{"type": "error", "message": "Cannot delete default grading system"}'
                return response
            else:
                messages.error(request, 'Cannot delete default grading system')
                return redirect('exams:grading_system_detail', pk=pk)
        
        # Check if system has assignments or examinations
        if system.class_assignments.exists() or system.examinations.exists():
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Trigger'] = 'showAlert'
                response['HX-Trigger-Data'] = '{"type": "error", "message": "Cannot delete grading system with class assignments or examinations"}'
                return response
            else:
                messages.error(request, 'Cannot delete grading system with assignments or examinations')
                return redirect('exams:grading_system_detail', pk=pk)
        
        try:
            system_name = system.name
            # Grading ranges will be deleted automatically via CASCADE
            system.delete()
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Redirect'] = reverse('exams:grading_system_list')
                response['HX-Trigger'] = 'showAlert'
                response['HX-Trigger-Data'] = f'{{"type": "success", "message": "Grading system \\"{system_name}\\" deleted successfully"}}'
                return response
            else:
                messages.success(request, f'Grading system "{system_name}" deleted successfully')
                return redirect('exams:grading_system_list')
                
        except Exception as e:
            logger.error(f"Error deleting grading system: {e}", exc_info=True)
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Trigger'] = 'showAlert'
                response['HX-Trigger-Data'] = f'{{"type": "error", "message": "Error deleting grading system: {str(e)}"}}'
                return response
            else:
                messages.error(request, f'Error deleting grading system: {str(e)}')
                return redirect('exams:grading_system_detail', pk=pk)


@login_required
def grading_system_toggle_active(request, pk):
    """Toggle grading system active status"""
    system = get_object_or_404(GradingSystem, pk=pk)
    
    if request.method == 'POST':
        try:
            system.is_active = not system.is_active
            system.save()
            
            status = "activated" if system.is_active else "deactivated"
            messages.success(request, f'Grading system "{system.name}" {status} successfully')
            return redirect('exams:grading_system_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error toggling grading system: {e}", exc_info=True)
            messages.error(request, f'Error: {str(e)}')
            return redirect('exams:grading_system_detail', pk=pk)


@login_required
def grading_system_set_default(request, pk):
    """Set grading system as default"""
    system = get_object_or_404(GradingSystem, pk=pk)
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Remove default from all systems
                GradingSystem.objects.filter(is_default=True).update(is_default=False)
                
                # Set this as default
                system.is_default = True
                system.is_active = True  # Ensure default system is active
                system.save()
            
            messages.success(request, f'"{system.name}" set as default grading system')
            return redirect('exams:grading_system_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error setting default: {e}", exc_info=True)
            messages.error(request, f'Error: {str(e)}')
            return redirect('exams:grading_system_detail', pk=pk)


@login_required
def grading_system_print_detail(request, pk):
    """Print single grading system details"""
    system = get_object_or_404(GradingSystem, pk=pk)
    ranges = system.ranges.all().order_by('-min_score')
    
    context = {
        'system': system,
        'ranges': ranges,
        'print_date': get_school_current_time(),
    }
    
    return render(request, 'exams/grading_systems/print_detail.html', context)


@login_required
def grading_system_print_view(request):
    """Print filtered grading systems"""
    systems = get_filtered_grading_systems(request)
    
    context = {
        'systems': systems,
        'print_date': get_school_current_time(),
    }
    
    return render(request, 'exams/grading_systems/print_list.html', context)


@login_required
def export_grading_systems_excel(request):
    """Export grading systems to Excel"""
    systems = get_filtered_grading_systems(request)
    
    # Create workbook
    wb = Workbook()
    
    # Sheet 1: Grading Systems
    ws1 = wb.active
    ws1.title = "Grading Systems"
    
    # Headers
    headers = [
        '#', 'Name', 'Code', 'Type', 'Scale', 'Min Score', 'Max Score',
        'Pass Mark', 'Uses GPA', 'Active', 'Default', 'Grade Ranges'
    ]
    ws1.append(headers)
    
    # Data rows
    for idx, system in enumerate(systems, start=1):
        ws1.append([
            idx,
            system.name,
            system.code,
            system.get_grading_type_display(),
            system.get_scale_type_display(),
            float(system.minimum_score),
            float(system.maximum_score),
            float(system.pass_mark),
            'Yes' if system.uses_gpa else 'No',
            'Yes' if system.is_active else 'No',
            'Yes' if system.is_default else 'No',
            system.ranges.count(),
        ])
    
    # Sheet 2: Grade Ranges (if needed)
    ws2 = wb.create_sheet("Grade Ranges")
    range_headers = [
        '#', 'Grading System', 'Grade', 'Grade Name', 'Min Score', 'Max Score',
        'Aggregate', 'GPA Points', 'Passing Grade'
    ]
    ws2.append(range_headers)
    
    row_num = 1
    for system in systems:
        for grade_range in system.ranges.all().order_by('-min_score'):
            ws2.append([
                row_num,
                system.name,
                grade_range.grade,
                grade_range.grade_name or '',
                float(grade_range.min_score),
                float(grade_range.max_score),
                grade_range.aggregate or '',
                float(grade_range.gpa_points) if grade_range.gpa_points else '',
                'Yes' if grade_range.is_passing_grade else 'No',
            ])
            row_num += 1
    
    # Create response
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"grading_systems_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response

# =============================================================================
# CLASS GRADING SYSTEM ASSIGNMENT VIEWS
# =============================================================================

@login_required
def class_grading_system_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""

    filter_form = ClassGradingSystemFilterForm(request.GET or None)

    assignments = get_filtered_class_grading_systems(request)
    
    # Calculate statistics
    stats = {
        'total': assignments.count(),
        'active': assignments.filter(is_active=True).count(),
        'inactive': assignments.filter(is_active=False).count(),
        'current_session': assignments.filter(
            academic_session=get_active_academic_session(),
            is_active=True
        ).count() if get_active_academic_session() else 0,
    }
    
    # Pagination
    paginator = Paginator(assignments, 20)
    page_number = request.GET.get('page', 1)
    assignments_page = paginator.get_page(page_number)
    
    # Detect HTMX request
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'assignments_page': assignments_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    # Return appropriate template
    if is_htmx:
        return render(request, 'exams/class_grading_systems/partials/_assignment_results.html', context)
    else:
        return render(request, 'exams/class_grading_systems/list.html', context)


@login_required
def class_grading_system_detail(request, pk):
    """View class grading system assignment details"""
    assignment = get_object_or_404(
        ClassGradingSystem.objects.select_related(
            'class_instance__academic_level', 'grading_system', 'academic_session',
            'subject', 'assigned_by'
        ),
        pk=pk
    )
    
    # Get related information
    grading_ranges = assignment.grading_system.ranges.all().order_by('-min_score')
    
    # Check if assignment is currently active
    is_currently_active = assignment.is_currently_active()
    
    context = {
        'assignment': assignment,
        'grading_ranges': grading_ranges,
        'is_currently_active': is_currently_active,
    }
    
    return render(request, 'exams/class_grading_systems/detail.html', context)


@login_required
def class_grading_system_create(request, class_pk=None):
    """Create new class grading system assignment"""
    initial = {}
    if class_pk:
        class_instance = get_object_or_404(Class, pk=class_pk)
        initial['class_instance'] = class_instance
        initial['academic_session'] = class_instance.academic_session
    
    if request.method == 'POST':
        form = ClassGradingSystemForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    assignment = form.save(commit=False)
                    assignment.assigned_by = request.user
                    assignment.save()
                    form.save_m2m()
                    
                messages.success(request, 'Class grading system assignment created successfully')
                return redirect('exams:class_grading_system_detail', pk=assignment.pk)
            except Exception as e:
                logger.error(f"Error creating class grading system assignment: {e}", exc_info=True)
                messages.error(request, f'Error creating assignment: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below')
    else:
        form = ClassGradingSystemForm(initial=initial)
    
    context = {
        'form': form,
        'title': 'Assign Grading System to Class',
    }
    
    return render(request, 'exams/class_grading_systems/form.html', context)


@login_required
def class_grading_system_edit(request, pk):
    """Edit class grading system assignment"""
    assignment = get_object_or_404(ClassGradingSystem, pk=pk)
    
    if request.method == 'POST':
        form = ClassGradingSystemForm(request.POST, instance=assignment)
        if form.is_valid():
            try:
                with transaction.atomic():
                    assignment = form.save()
                    
                messages.success(request, 'Class grading system assignment updated successfully')
                return redirect('exams:class_grading_system_detail', pk=assignment.pk)
            except Exception as e:
                logger.error(f"Error updating class grading system assignment: {e}", exc_info=True)
                messages.error(request, f'Error updating assignment: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below')
    else:
        form = ClassGradingSystemForm(instance=assignment)
    
    context = {
        'form': form,
        'assignment': assignment,
        'title': 'Edit Grading System Assignment',
    }
    
    return render(request, 'exams/class_grading_systems/form.html', context)


@login_required
def class_grading_system_delete(request, pk):
    """Delete class grading system assignment with HTMX support"""
    assignment = get_object_or_404(ClassGradingSystem, pk=pk)
    
    if request.method == 'POST':
        try:
            assignment.delete()
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Redirect'] = reverse('exams:class_grading_system_list')
                response['HX-Trigger'] = 'showAlert'
                response['HX-Trigger-Data'] = '{"type": "success", "message": "Grading system assignment deleted successfully"}'
                return response
            else:
                messages.success(request, 'Grading system assignment deleted successfully')
                return redirect('exams:class_grading_system_list')
                
        except Exception as e:
            logger.error(f"Error deleting class grading system assignment: {e}", exc_info=True)
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Trigger'] = 'showAlert'
                response['HX-Trigger-Data'] = f'{{"type": "error", "message": "Error deleting assignment: {str(e)}"}}'
                return response
            else:
                messages.error(request, f'Error deleting assignment: {str(e)}')
                return redirect('exams:class_grading_system_detail', pk=pk)


@login_required
def class_grading_system_toggle_active(request, pk):
    """Toggle class grading system assignment active status"""
    assignment = get_object_or_404(ClassGradingSystem, pk=pk)
    
    if request.method == 'POST':
        try:
            assignment.is_active = not assignment.is_active
            assignment.save()
            
            status = "activated" if assignment.is_active else "deactivated"
            messages.success(request, f'Assignment {status} successfully')
            return redirect('exams:class_grading_system_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error toggling assignment: {e}", exc_info=True)
            messages.error(request, f'Error: {str(e)}')
            return redirect('exams:class_grading_system_detail', pk=pk)


@login_required
def bulk_class_grading_system_assign(request):
    """Bulk assign grading system to multiple classes"""
    if request.method == 'POST':
        try:
            grading_system_id = request.POST.get('grading_system')
            academic_session_id = request.POST.get('academic_session')
            class_ids = request.POST.getlist('classes')
            subject_id = request.POST.get('subject')
            
            grading_system = get_object_or_404(GradingSystem, pk=grading_system_id)
            academic_session = get_object_or_404(AcademicSession, pk=academic_session_id)
            subject = get_object_or_404(Subject, pk=subject_id) if subject_id else None
            
            created_count = 0
            skipped_count = 0
            
            with transaction.atomic():
                for class_id in class_ids:
                    class_instance = get_object_or_404(Class, pk=class_id)
                    
                    # Check if assignment already exists
                    existing = ClassGradingSystem.objects.filter(
                        class_instance=class_instance,
                        grading_system=grading_system,
                        academic_session=academic_session,
                        subject=subject
                    ).first()
                    
                    if not existing:
                        ClassGradingSystem.objects.create(
                            class_instance=class_instance,
                            grading_system=grading_system,
                            academic_session=academic_session,
                            subject=subject,
                            assigned_by=request.user,
                            effective_date=get_school_today()
                        )
                        created_count += 1
                    else:
                        skipped_count += 1
            
            if created_count > 0:
                messages.success(
                    request, 
                    f'Successfully assigned grading system to {created_count} class(es)'
                )
            if skipped_count > 0:
                messages.info(
                    request,
                    f'Skipped {skipped_count} class(es) - assignment already exists'
                )
            
            return redirect('exams:class_grading_system_list')
            
        except Exception as e:
            logger.error(f"Error in bulk grading system assignment: {e}", exc_info=True)
            messages.error(request, f'Error: {str(e)}')
            return redirect('exams:class_grading_system_list')
    
    # GET request - show form
    grading_systems = GradingSystem.objects.filter(is_active=True).order_by('name')
    sessions = AcademicSession.objects.filter(is_active=True).order_by('-start_date')
    classes = Class.objects.filter(is_active=True).select_related('academic_level').order_by('academic_level__order', 'section')
    subjects = Subject.objects.filter(is_active=True).order_by('name')
    
    context = {
        'grading_systems': grading_systems,
        'sessions': sessions,
        'classes': classes,
        'subjects': subjects,
        'title': 'Bulk Assign Grading System',
    }
    
    return render(request, 'exams/class_grading_systems/bulk_assign.html', context)


@login_required
def class_grading_system_print_view(request):
    """Print filtered class grading system assignments"""
    assignments = get_filtered_class_grading_systems(request)
    
    context = {
        'assignments': assignments,
        'print_date': get_school_current_time(),
    }
    
    return render(request, 'exams/class_grading_systems/print_list.html', context)


@login_required
def export_class_grading_systems_excel(request):
    """Export class grading system assignments to Excel"""
    assignments = get_filtered_class_grading_systems(request)
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Class Grading Systems"
    
    # Headers
    headers = [
        '#', 'Class', 'Grading System', 'Session', 'Subject',
        'Effective Date', 'End Date', 'Priority', 'Active', 'Default'
    ]
    ws.append(headers)
    
    # Data rows
    for idx, assignment in enumerate(assignments, start=1):
        ws.append([
            idx,
            str(assignment.class_instance),
            assignment.grading_system.name,
            assignment.academic_session.name,
            assignment.subject.name if assignment.subject else 'All Subjects',
            assignment.effective_date.strftime('%Y-%m-%d'),
            assignment.end_date.strftime('%Y-%m-%d') if assignment.end_date else 'N/A',
            assignment.priority,
            'Yes' if assignment.is_active else 'No',
            'Yes' if assignment.is_default_for_class else 'No',
        ])
    
    # Create response
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"class_grading_systems_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _check_grading_system_coverage(system, ranges):
    """
    Check if grading ranges provide complete coverage of the grading system's score range.
    
    Returns:
        dict: Coverage status information
    """
    if not ranges.exists():
        return {
            'has_coverage': False,
            'has_gaps': True,
            'gaps': [],
            'message': 'No grade ranges defined'
        }
    
    sorted_ranges = list(ranges.order_by('min_score'))
    gaps = []
    
    # Check if ranges start at system minimum
    if sorted_ranges[0].min_score > system.minimum_score:
        gaps.append({
            'start': system.minimum_score,
            'end': sorted_ranges[0].min_score,
            'message': f'Gap from {system.minimum_score} to {sorted_ranges[0].min_score}'
        })
    
    # Check for gaps between consecutive ranges
    for i in range(len(sorted_ranges) - 1):
        current = sorted_ranges[i]
        next_range = sorted_ranges[i + 1]
        
        gap = next_range.min_score - current.max_score
        if gap > Decimal('0.01'):  # Allow for small floating point differences
            gaps.append({
                'start': current.max_score,
                'end': next_range.min_score,
                'message': f'Gap from {current.max_score} to {next_range.min_score}'
            })
    
    # Check if ranges reach system maximum
    if sorted_ranges[-1].max_score < system.maximum_score:
        gaps.append({
            'start': sorted_ranges[-1].max_score,
            'end': system.maximum_score,
            'message': f'Gap from {sorted_ranges[-1].max_score} to {system.maximum_score}'
        })
    
    return {
        'has_coverage': len(gaps) == 0,
        'has_gaps': len(gaps) > 0,
        'gaps': gaps,
        'message': 'Complete coverage' if len(gaps) == 0 else f'{len(gaps)} gap(s) found'
    }


def _validate_range_against_system(range_obj, system):
    """
    Validate a grading range against the grading system's bounds and other ranges.
    
    Args:
        range_obj: GradingRange instance
        system: GradingSystem instance
        
    Raises:
        ValidationError: If validation fails
    """
    from django.core.exceptions import ValidationError
    
    # Check system bounds
    if range_obj.min_score < system.minimum_score:
        raise ValidationError(
            f'Minimum score ({range_obj.min_score}) cannot be less than '
            f'grading system minimum ({system.minimum_score})'
        )
    
    if range_obj.max_score > system.maximum_score:
        raise ValidationError(
            f'Maximum score ({range_obj.max_score}) cannot exceed '
            f'grading system maximum ({system.maximum_score})'
        )
    
    # Check for overlaps with other ranges
    overlapping = system.ranges.exclude(pk=range_obj.pk if range_obj.pk else None).filter(
        Q(min_score__lte=range_obj.max_score) & Q(max_score__gte=range_obj.min_score)
    )
    
    if overlapping.exists():
        overlap = overlapping.first()
        raise ValidationError(
            f'Range overlaps with existing range "{overlap.grade}" '
            f'({overlap.min_score}-{overlap.max_score})'
        )

# =============================================================================
# EXAMINATION VIEWS (Additional ones not in original)
# =============================================================================

@login_required
def examination_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""
    filter_form = ExaminationFilterForm(request.GET or None)
    examinations = get_filtered_examinations(request)
    
    # Calculate statistics
    today = get_school_today()
    stats = {
        'total': examinations.count(),
        'planned': examinations.filter(status='PLANNED').count(),
        'scheduled': examinations.filter(status='SCHEDULED').count(),
        'ongoing': examinations.filter(status='ONGOING').count(),
        'completed': examinations.filter(status='COMPLETED').count(),
        'upcoming': examinations.filter(
            exam_date__gte=today,
            status__in=['PLANNED', 'SCHEDULED']
        ).count(),
        'results_published': examinations.filter(results_published=True).count(),
    }
    
    # Pagination
    paginator = Paginator(examinations, 20)
    page_number = request.GET.get('page', 1)
    examinations_page = paginator.get_page(page_number)
    
    # Detect HTMX request
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'examinations_page': examinations_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    # Return appropriate template
    if is_htmx:
        return render(request, 'exams/examinations/partials/_examination_results.html', context)
    else:
        return render(request, 'exams/examinations/list.html', context)


@login_required
def examination_detail(request, pk):
    """View examination details"""
    examination = get_object_or_404(
        Examination.objects.select_related(
            'subject', 'academic_session', 'exam_category', 'grading_system', 'classroom'
        ).prefetch_related('target_classes', 'invigilators'),
        pk=pk
    )
    
    # Get registrations
    registrations = examination.registrations.select_related('student').order_by('registration_date')[:50]
    
    # Get results
    results = examination.student_results.select_related('student').order_by('-score')[:50]
    
    # Calculate statistics
    total_registered = registrations.count()
    total_results = results.count()
    
    result_stats = results.aggregate(
        highest=Max('score'),
        lowest=Min('score'),
        average=Avg('score'),
        pass_count=Count('id', filter=Q(is_pass=True)),
    )
    
    stats = {
        'total_registered': total_registered,
        'total_results': total_results,
        'highest_score': result_stats['highest'],
        'lowest_score': result_stats['lowest'],
        'average_score': round(result_stats['average'], 2) if result_stats['average'] else 0,
        'pass_count': result_stats['pass_count'],
        'pass_rate': round((result_stats['pass_count'] / total_results * 100), 2) if total_results > 0 else 0,
        'published_count': results.filter(is_published=True).count(),
        'locked_count': results.filter(is_grade_locked=True).count(),
    }
    
    context = {
        'examination': examination,
        'registrations': registrations,
        'results': results,
        'stats': stats,
    }
    
    return render(request, 'exams/examinations/detail.html', context)


@login_required
def examination_create(request):
    """Create new examination"""
    if request.method == 'POST':
        form = ExaminationForm(request.POST)
        if form.is_valid():
            try:
                examination = form.save(commit=False)
                examination.created_by = request.user
                examination.save()
                form.save_m2m()
                messages.success(request, f'Examination "{examination.name}" created successfully')
                return redirect('exams:examination_detail', pk=examination.pk)
            except Exception as e:
                logger.error(f"Error creating examination: {e}")
                messages.error(request, f'Error creating examination: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below')
    else:
        form = ExaminationForm()
    
    context = {
        'form': form,
        'title': 'Create Examination',
    }
    
    return render(request, 'exams/examinations/form.html', context)


@login_required
def examination_edit(request, pk):
    """Edit examination"""
    examination = get_object_or_404(Examination, pk=pk)
    
    if request.method == 'POST':
        form = ExaminationForm(request.POST, instance=examination)
        if form.is_valid():
            try:
                examination = form.save()
                messages.success(request, f'Examination "{examination.name}" updated successfully')
                return redirect('exams:examination_detail', pk=examination.pk)
            except Exception as e:
                logger.error(f"Error updating examination: {e}")
                messages.error(request, f'Error updating examination: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below')
    else:
        form = ExaminationForm(instance=examination)
    
    context = {
        'form': form,
        'examination': examination,
        'title': 'Edit Examination',
    }
    
    return render(request, 'exams/examinations/form.html', context)


@login_required
def examination_delete(request, pk):
    """Delete examination with HTMX support"""
    examination = get_object_or_404(Examination, pk=pk)
    
    if request.method == 'POST':
        # Check if examination has results
        if examination.student_results.exists():
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Trigger'] = 'showAlert'
                response['HX-Trigger-Data'] = '{"type": "error", "message": "Cannot delete examination with existing results"}'
                return response
            else:
                messages.error(request, 'Cannot delete examination with existing results')
                return redirect('exams:examination_detail', pk=pk)
        
        # Check status
        if examination.status in ['ONGOING', 'COMPLETED']:
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Trigger'] = 'showAlert'
                response['HX-Trigger-Data'] = '{"type": "error", "message": "Cannot delete ongoing or completed examinations"}'
                return response
            else:
                messages.error(request, 'Cannot delete ongoing or completed examinations')
                return redirect('exams:examination_detail', pk=pk)
        
        try:
            exam_name = examination.name
            examination.delete()
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Redirect'] = reverse('exams:examination_list')
                response['HX-Trigger'] = 'showAlert'
                response['HX-Trigger-Data'] = f'{{"type": "success", "message": "Examination \\"{exam_name}\\" deleted successfully"}}'
                return response
            else:
                messages.success(request, f'Examination "{exam_name}" deleted successfully')
                return redirect('exams:examination_list')
                
        except Exception as e:
            logger.error(f"Error deleting examination: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Trigger'] = 'showAlert'
                response['HX-Trigger-Data'] = f'{{"type": "error", "message": "Error deleting examination: {str(e)}"}}'
                return response
            else:
                messages.error(request, f'Error deleting examination: {str(e)}')
                return redirect('exams:examination_detail', pk=pk)


@login_required
def examination_toggle_active(request, pk):
    """Toggle examination active status"""
    examination = get_object_or_404(Examination, pk=pk)
    
    if request.method == 'POST':
        try:
            # Toggle status between PLANNED and CANCELLED
            if examination.status == 'CANCELLED':
                examination.status = 'PLANNED'
            else:
                examination.status = 'CANCELLED'
            examination.save()
            
            messages.success(request, f'Examination status updated to {examination.get_status_display()}')
            return redirect('exams:examination_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error toggling examination: {e}")
            messages.error(request, f'Error: {str(e)}')
            return redirect('exams:examination_detail', pk=pk)


@login_required
def examination_update_status(request, pk):
    """Update examination status"""
    examination = get_object_or_404(Examination, pk=pk)
    
    if request.method == 'POST':
        new_status = request.POST.get('status')
        
        if new_status not in dict(Examination.EXAM_STATUS_CHOICES):
            messages.error(request, 'Invalid status')
            return redirect('exams:examination_detail', pk=pk)
        
        try:
            examination.status = new_status
            examination.save()
            
            messages.success(request, f'Examination status updated to {examination.get_status_display()}')
            return redirect('exams:examination_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error updating examination status: {e}")
            messages.error(request, f'Error: {str(e)}')
            return redirect('exams:examination_detail', pk=pk)


@login_required
def publish_results(request, pk):
    """Publish examination results with HTMX support"""
    examination = get_object_or_404(Examination, pk=pk)
    
    if request.method == 'POST':
        form = ResultPublishForm(request.POST)
        if form.is_valid():
            try:
                auto_lock = form.cleaned_data['auto_lock_grades']
                notes = form.cleaned_data.get('notes', '')
                
                with transaction.atomic():
                    # Update examination
                    examination.results_published = True
                    examination.results_publication_date = get_school_current_time()
                    examination.save()
                    
                    # Update all results
                    results = examination.student_results.filter(
                        status__in=['COMPLETED', 'SUBMITTED']
                    )
                    
                    for result in results:
                        result.is_published = True
                        result.publication_date = get_school_current_time()
                        result.save()
                        
                        # Auto-lock if requested
                        if auto_lock and not result.is_grade_locked:
                            result.lock_grade(
                                locked_by=request.user,
                                reason="Auto-locked during result publication"
                            )
                    
                    results_count = results.count()
                    locked_count = results.filter(is_grade_locked=True).count() if auto_lock else 0
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    message = f'Published {results_count} result(s)'
                    if auto_lock:
                        message += f' and locked {locked_count} grade(s)'
                    response['HX-Redirect'] = reverse('exams:examination_detail', kwargs={'pk': pk})
                    response['HX-Trigger'] = 'showAlert'
                    response['HX-Trigger-Data'] = f'{{"type": "success", "message": "{message}"}}'
                    return response
                else:
                    messages.success(request, f'Published {results_count} result(s)')
                    return redirect('exams:examination_detail', pk=pk)
                    
            except Exception as e:
                logger.error(f"Error publishing results: {e}")
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Trigger'] = 'showAlert'
                    response['HX-Trigger-Data'] = f'{{"type": "error", "message": "Error publishing results: {str(e)}"}}'
                    return response
                else:
                    messages.error(request, f'Error publishing results: {str(e)}')
                    return redirect('exams:examination_detail', pk=pk)


@login_required
def unpublish_results(request, pk):
    """Unpublish examination results"""
    examination = get_object_or_404(Examination, pk=pk)
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Update examination
                examination.results_published = False
                examination.results_publication_date = None
                examination.save()
                
                # Update all results
                results = examination.student_results.all()
                for result in results:
                    result.is_published = False
                    result.publication_date = None
                    result.save()
                
                results_count = results.count()
            
            messages.success(request, f'Unpublished {results_count} result(s)')
            return redirect('exams:examination_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error unpublishing results: {e}")
            messages.error(request, f'Error unpublishing results: {str(e)}')
            return redirect('exams:examination_detail', pk=pk)


@login_required
def examination_print_detail(request, pk):
    """Print examination details"""
    examination = get_object_or_404(Examination, pk=pk)
    
    context = {
        'examination': examination,
        'print_date': get_school_current_time(),
    }
    
    return render(request, 'exams/examinations/print_detail.html', context)


@login_required
def examination_print_timetable(request, pk):
    """Print examination timetable"""
    examination = get_object_or_404(Examination, pk=pk)
    
    context = {
        'examination': examination,
        'print_date': get_school_current_time(),
    }
    
    return render(request, 'exams/examinations/print_timetable.html', context)


@login_required
def examination_print_answer_sheet(request, pk):
    """Print examination answer sheet template"""
    examination = get_object_or_404(Examination, pk=pk)
    
    context = {
        'examination': examination,
        'print_date': get_school_current_time(),
    }
    
    return render(request, 'exams/examinations/print_answer_sheet.html', context)


@login_required
def examination_print_view(request):
    """Print filtered examinations"""
    examinations = get_filtered_examinations(request)
    
    context = {
        'examinations': examinations,
        'print_date': get_school_current_time(),
    }
    
    return render(request, 'exams/examinations/print_list.html', context)


@login_required
def export_examinations_excel(request):
    """Export examinations to Excel with filters applied"""
    examinations = get_filtered_examinations(request)
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Examinations"
    
    # Define styles
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_alignment = Alignment(horizontal="center", vertical="center")
    
    # Headers
    headers = [
        '#', 'Name', 'Code', 'Subject', 'Session', 'Category',
        'Date', 'Time', 'Total Marks', 'Pass Marks', 'Status'
    ]
    ws.append(headers)
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
    
    # Data rows
    for idx, exam in enumerate(examinations, start=1):
        ws.append([
            idx,
            exam.name,
            exam.code,
            exam.subject.name,
            exam.academic_session.name,
            exam.exam_category.name,
            exam.exam_date.strftime('%Y-%m-%d'),
            f"{exam.start_time.strftime('%H:%M')} - {exam.end_time.strftime('%H:%M')}",
            float(exam.total_marks),
            float(exam.pass_marks),
            exam.get_status_display(),
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
    filename = f"examinations_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


# =============================================================================
# EXAM REGISTRATION VIEWS
# =============================================================================

def get_filtered_exam_registrations(request):
    """Helper function to get filtered exam registrations"""
    registrations = ExamRegistration.objects.select_related(
        'student', 'examination__subject', 'examination__academic_session', 'registered_by'
    ).order_by('-registration_date')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    examination = request.GET.get('examination', '')
    status = request.GET.get('status', '')
    payment_verified = request.GET.get('payment_verified', '')
    
    # Apply text search
    if query:
        words = query.strip().split()
        if words:
            combined_q = Q()
            for word in words:
                word_q = (
                    Q(student__first_name__icontains=word) |
                    Q(student__last_name__icontains=word) |
                    Q(student__admission_number__icontains=word)
                )
                combined_q &= word_q
            registrations = registrations.filter(combined_q)
    
    # Apply filters
    if examination:
        registrations = registrations.filter(examination_id=examination)
    if status:
        registrations = registrations.filter(status=status)
    if payment_verified:
        registrations = registrations.filter(payment_verified=(payment_verified.lower() == 'true'))
    
    return registrations


@login_required
def exam_registration_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""

    filter_form = ExamRegistrationFilterForm(request.GET or None)

    registrations = get_filtered_exam_registrations(request)
    
    # Calculate statistics
    stats = {
        'total': registrations.count(),
        'confirmed': registrations.filter(status='CONFIRMED').count(),
        'pending': registrations.filter(status='PENDING').count(),
        'cancelled': registrations.filter(status='CANCELLED').count(),
        'payment_verified': registrations.filter(payment_verified=True).count(),
    }
    
    # Pagination
    paginator = Paginator(registrations, 50)
    page_number = request.GET.get('page', 1)
    registrations_page = paginator.get_page(page_number)
    
    # Detect HTMX request
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'registrations_page': registrations_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    # Return appropriate template
    if is_htmx:
        return render(request, 'exams/registrations/_registration_results.html', context)
    else:
        return render(request, 'exams/registrations/list.html', context)


@login_required
def exam_registration_detail(request, pk):
    """View exam registration details"""
    registration = get_object_or_404(
        ExamRegistration.objects.select_related(
            'student', 'examination__subject', 'examination__academic_session', 'registered_by'
        ),
        pk=pk
    )
    
    context = {
        'registration': registration,
    }
    
    return render(request, 'exams/registrations/detail.html', context)


@login_required
def exam_registration_create(request, examination_pk=None, student_pk=None):
    """Create new exam registration"""
    initial = {}
    if examination_pk:
        examination = get_object_or_404(Examination, pk=examination_pk)
        initial['examination'] = examination
    if student_pk:
        student = get_object_or_404(Student, pk=student_pk)
        initial['student'] = student
    
    if request.method == 'POST':
        form = ExamRegistrationForm(request.POST)
        if form.is_valid():
            try:
                registration = form.save(commit=False)
                registration.registered_by = request.user
                registration.save()
                messages.success(request, f'Exam registration for {registration.student.get_full_name()} created successfully')
                return redirect('exams:registration_detail', pk=registration.pk)
            except Exception as e:
                logger.error(f"Error creating exam registration: {e}")
                messages.error(request, f'Error creating registration: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below')
    else:
        form = ExamRegistrationForm(initial=initial)
    
    context = {
        'form': form,
        'title': 'Register for Examination',
    }
    
    return render(request, 'exams/registrations/form.html', context)


@login_required
def exam_registration_edit(request, pk):
    """Edit exam registration"""
    registration = get_object_or_404(ExamRegistration, pk=pk)
    
    if request.method == 'POST':
        form = ExamRegistrationForm(request.POST, instance=registration)
        if form.is_valid():
            try:
                registration = form.save()
                messages.success(request, f'Exam registration for {registration.student.get_full_name()} updated successfully')
                return redirect('exams:registration_detail', pk=registration.pk)
            except Exception as e:
                logger.error(f"Error updating exam registration: {e}")
                messages.error(request, f'Error updating registration: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below')
    else:
        form = ExamRegistrationForm(instance=registration)
    
    context = {
        'form': form,
        'registration': registration,
        'title': 'Edit Exam Registration',
    }
    
    return render(request, 'exams/registrations/form.html', context)


@login_required
def exam_registration_delete(request, pk):
    """Delete exam registration with HTMX support"""
    registration = get_object_or_404(ExamRegistration, pk=pk)
    
    if request.method == 'POST':
        try:
            student_name = registration.student.get_full_name()
            registration.delete()
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Redirect'] = reverse('exams:registration_list')
                response['HX-Trigger'] = 'showAlert'
                response['HX-Trigger-Data'] = f'{{"type": "success", "message": "Registration for {student_name} deleted successfully"}}'
                return response
            else:
                messages.success(request, f'Registration for {student_name} deleted successfully')
                return redirect('exams:registration_list')
                
        except Exception as e:
            logger.error(f"Error deleting exam registration: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Trigger'] = 'showAlert'
                response['HX-Trigger-Data'] = f'{{"type": "error", "message": "Error deleting registration: {str(e)}"}}'
                return response
            else:
                messages.error(request, f'Error deleting registration: {str(e)}')
                return redirect('exams:registration_detail', pk=pk)


@login_required
def exam_registration_update_status(request, pk):
    """Update exam registration status"""
    registration = get_object_or_404(ExamRegistration, pk=pk)
    
    if request.method == 'POST':
        new_status = request.POST.get('status')
        
        if new_status not in dict(ExamRegistration.REGISTRATION_STATUS_CHOICES):
            messages.error(request, 'Invalid status')
            return redirect('exams:registration_detail', pk=pk)
        
        try:
            registration.status = new_status
            registration.save()
            
            messages.success(request, f'Registration status updated to {registration.get_status_display()}')
            return redirect('exams:registration_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error updating registration status: {e}")
            messages.error(request, f'Error: {str(e)}')
            return redirect('exams:registration_detail', pk=pk)


@login_required
def exam_registration_verify_payment(request, pk):
    """Verify payment for exam registration"""
    registration = get_object_or_404(ExamRegistration, pk=pk)
    
    if request.method == 'POST':
        try:
            registration.payment_verified = True
            registration.payment_verification_date = get_school_current_time()
            registration.save()
            
            messages.success(request, f'Payment verified for {registration.student.get_full_name()}')
            return redirect('exams:registration_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error verifying payment: {e}")
            messages.error(request, f'Error: {str(e)}')
            return redirect('exams:registration_detail', pk=pk)


@login_required
def bulk_exam_registration_create(request):
    """Bulk create exam registrations for multiple students"""
    if request.method == 'POST':
        try:
            examination_id = request.POST.get('examination')
            student_ids = request.POST.getlist('students')
            
            examination = get_object_or_404(Examination, pk=examination_id)
            
            created_count = 0
            with transaction.atomic():
                for student_id in student_ids:
                    student = get_object_or_404(Student, pk=student_id)
                    
                    # Check if registration already exists
                    existing = ExamRegistration.objects.filter(
                        student=student,
                        examination=examination
                    ).first()
                    
                    if not existing:
                        ExamRegistration.objects.create(
                            student=student,
                            examination=examination,
                            registered_by=request.user,
                            status='PENDING'
                        )
                        created_count += 1
            
            messages.success(request, f'Successfully registered {created_count} student(s)')
            return redirect('exams:registration_list')
            
        except Exception as e:
            logger.error(f"Error in bulk exam registration: {e}")
            messages.error(request, f'Error: {str(e)}')
            return redirect('exams:registration_list')
    
    # GET request - show form
    examinations = Examination.objects.filter(
        status__in=['PLANNED', 'SCHEDULED']
    ).select_related('subject', 'academic_session').order_by('-exam_date')
    
    students = Student.objects.filter(enrollment_status='ACTIVE').order_by('first_name', 'last_name')
    
    context = {
        'examinations': examinations,
        'students': students,
        'title': 'Bulk Exam Registration',
    }
    
    return render(request, 'exams/registrations/bulk_create.html', context)


@login_required
def bulk_exam_registration_update_status(request):
    """Bulk update status for exam registrations"""
    if request.method == 'POST':
        try:
            registration_ids = request.POST.getlist('registrations')
            new_status = request.POST.get('status')
            
            if new_status not in dict(ExamRegistration.REGISTRATION_STATUS_CHOICES):
                messages.error(request, 'Invalid status')
                return redirect('exams:registration_list')
            
            updated_count = ExamRegistration.objects.filter(
                id__in=registration_ids
            ).update(status=new_status)
            
            messages.success(request, f'Successfully updated {updated_count} registration(s)')
            return redirect('exams:registration_list')
            
        except Exception as e:
            logger.error(f"Error in bulk status update: {e}")
            messages.error(request, f'Error: {str(e)}')
            return redirect('exams:registration_list')


@login_required
def exam_registration_print_detail(request, pk):
    """Print exam registration details"""
    registration = get_object_or_404(ExamRegistration, pk=pk)
    
    context = {
        'registration': registration,
        'print_date': get_school_current_time(),
    }
    
    return render(request, 'exams/registrations/print_detail.html', context)


@login_required
def exam_registration_print_view(request):
    """Print filtered exam registrations"""
    registrations = get_filtered_exam_registrations(request)
    
    context = {
        'registrations': registrations,
        'print_date': get_school_current_time(),
    }
    
    return render(request, 'exams/registrations/print_list.html', context)


@login_required
def export_exam_registrations_excel(request):
    """Export exam registrations to Excel"""
    registrations = get_filtered_exam_registrations(request)
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Exam Registrations"
    
    # Headers
    headers = [
        '#', 'Student', 'Admission No', 'Examination', 'Subject',
        'Registration Date', 'Status', 'Payment Verified'
    ]
    ws.append(headers)
    
    # Data rows
    for idx, registration in enumerate(registrations, start=1):
        ws.append([
            idx,
            registration.student.get_full_name(),
            registration.student.admission_number,
            registration.examination.name,
            registration.examination.subject.name,
            registration.registration_date.strftime('%Y-%m-%d %H:%M'),
            registration.get_status_display(),
            'Yes' if registration.payment_verified else 'No',
        ])
    
    # Create response
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"exam_registrations_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response

# =============================================================================
# STUDENT EXAM RESULT VIEWS
# =============================================================================

@login_required
def class_results_dashboard(request, class_pk):
    """
    Unified class results view that handles BOTH:
    1. Dashboard mode (exam category tabs with subject columns)
    2. List mode (individual results in table format)
    
    Supports HTMX for filtering and pagination.
    """
    class_instance = get_object_or_404(Class, pk=class_pk)
    
    # Get selected session
    session_id = request.GET.get('session')
    if session_id:
        session = get_object_or_404(AcademicSession, pk=session_id)
    else:
        session = class_instance.academic_session or AcademicSession.get_current_session()
    
    # Handle case where no current session exists
    if not session:
        messages.warning(request, 'No current academic session found. Please select a session.')
        return redirect('academics:session_list')
    
    # Determine display mode (dashboard or list)
    view_mode = request.GET.get('mode', 'dashboard')  # 'dashboard' or 'list'
    
    # Get all sessions for dropdown
    all_sessions = AcademicSession.objects.filter(is_active=True).order_by('-start_date')
    
    # Get students enrolled in this class
    students = Student.objects.filter(
        class_enrollments__class_instance=class_instance,
        class_enrollments__academic_session=session,
        class_enrollments__is_active=True,
        class_enrollments__completion_status='ONGOING'
    ).distinct().order_by('first_name', 'last_name')  # ✅ ADDED ordering
    
    # Detect HTMX request
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    # =========================================================================
    # DASHBOARD MODE - Category Tabs with Subject Results
    # =========================================================================
    if view_mode == 'dashboard':
        # Get selected tab (exam category)
        selected_category_abbr = request.GET.get('tab')
        
        # Get all active exam categories
        exam_categories = ExamCategory.objects.filter(is_active=True).order_by('name')
        
        # Get examinations for this class and session
        examinations = Examination.objects.filter(
            target_classes=class_instance,
            academic_session=session
        ).select_related('exam_category', 'subject').order_by('subject__name')
        
        # Organize by category
        exams_by_category = {}
        for exam in examinations:
            category_abbr = exam.exam_category.abbreviation
            if category_abbr not in exams_by_category:
                exams_by_category[category_abbr] = {
                    'category': exam.exam_category,  # ✅ ADDED category object
                    'exams': []
                }
            exams_by_category[category_abbr]['exams'].append(exam)
        
        # Get results for selected category
        results_data = []
        category_subjects = []
        selected_category = None  # ✅ ADDED
        
        if selected_category_abbr and selected_category_abbr in exams_by_category:
            category_data = exams_by_category[selected_category_abbr]
            category_exams = category_data['exams']
            selected_category = category_data['category']  # ✅ ADDED
            category_subjects = [exam.subject.name for exam in category_exams]
            
            for student in students:
                student_data = {
                    'student': student,
                    'subject_results': {}
                }
                
                # Get results for each subject in this category
                for exam in category_exams:
                    result = StudentExamResult.objects.filter(
                        student=student,
                        examination=exam
                    ).first()
                    
                    student_data['subject_results'][exam.subject.name] = {
                        'result': result,
                        'exam': exam,
                        'score': result.score if result else None,
                        'grade': result.grade if result else None,
                        'is_locked': result.is_grade_locked if result else False,
                        'is_published': result.is_published if result else False,  # ✅ ADDED
                    }
                
                # Calculate totals
                scores = [
                    r['score'] for r in student_data['subject_results'].values() 
                    if r['score'] is not None
                ]
                student_data['total'] = sum(scores) if scores else 0
                student_data['average'] = round(sum(scores) / len(scores), 2) if scores else 0
                student_data['subjects_taken'] = len(scores)
                
                results_data.append(student_data)
            
            # Sort by total (for ranking)
            results_data.sort(key=lambda x: x['total'], reverse=True)
            
            # Add positions
            for i, data in enumerate(results_data, 1):
                data['position'] = i
        
        # Determine active tab - select first category if none selected
        if not selected_category_abbr and exams_by_category:
            selected_category_abbr = next(iter(exams_by_category.keys()))
            selected_category = exams_by_category[selected_category_abbr]['category']
        
        # Dashboard statistics
        stats = {
            'total_students': students.count(),
            'total_exams': examinations.count(),
            'categories': exam_categories.count(),
            'results_entered': StudentExamResult.objects.filter(
                examination__target_classes=class_instance,
                examination__academic_session=session,
                score__isnull=False
            ).count(),
            'published_results': StudentExamResult.objects.filter(  # ✅ ADDED
                examination__target_classes=class_instance,
                examination__academic_session=session,
                is_published=True
            ).count(),
            'locked_results': StudentExamResult.objects.filter(  # ✅ ADDED
                examination__target_classes=class_instance,
                examination__academic_session=session,
                is_grade_locked=True
            ).count(),
        }
        
        context = {
            'view_mode': 'dashboard',
            'class_instance': class_instance,
            'session': session,
            'all_sessions': all_sessions,
            'exam_categories': exam_categories,
            'selected_category_abbr': selected_category_abbr,  # ✅ RENAMED for clarity
            'selected_category': selected_category,  # ✅ ADDED
            'exams_by_category': exams_by_category,
            'results_data': results_data,
            'category_subjects': category_subjects,
            'students': students,
            'stats': stats,
            'is_htmx': is_htmx,
        }
        
        # Return appropriate template
        if is_htmx:
            return render(request, 'exams/results/partials/_dashboard_results.html', context)
        else:
            return render(request, 'exams/results/class_dashboard.html', context)
    
    # =========================================================================
    # LIST MODE - Individual Results Table
    # =========================================================================
    else:  # view_mode == 'list'
        # Initialize filter form
        filter_form = StudentExamResultFilterForm(request.GET or None)
        
        # Get base queryset for this class and session
        results = StudentExamResult.objects.filter(
            student__class_enrollments__class_instance=class_instance,
            student__class_enrollments__academic_session=session,
            student__class_enrollments__is_active=True,
            examination__academic_session=session
        ).select_related(
            'student', 'examination__subject', 'examination__exam_category',
            'verified_by', 'moderator', 'grade_locked_by'
        ).distinct().order_by('-examination__exam_date', 'student__first_name')  # ✅ ADDED distinct()
        
        # Apply filters from form
        if filter_form.is_valid():  # ✅ ADDED validation check
            from .forms import apply_result_filters
            results = apply_result_filters(results, filter_form)
        
        # Calculate statistics
        stats = {
            'total': results.count(),
            'published': results.filter(is_published=True).count(),
            'locked': results.filter(is_grade_locked=True).count(),
            'pass': results.filter(is_pass=True, score__isnull=False).count(),  # ✅ ADDED score check
            'fail': results.filter(is_pass=False, score__isnull=False).count(),  # ✅ ADDED score check
            'completed': results.filter(status='COMPLETED').count(),
            'pending': results.filter(status__in=['NOT_STARTED', 'IN_PROGRESS']).count(),
        }
        
        # Calculate pass rate
        total_graded = stats['pass'] + stats['fail']  # ✅ CHANGED
        if total_graded > 0:
            stats['pass_rate'] = round((stats['pass'] / total_graded) * 100, 1)
        else:
            stats['pass_rate'] = 0
        
        # Pagination
        paginator = Paginator(results, 50)
        page_number = request.GET.get('page', 1)
        results_page = paginator.get_page(page_number)
        
        context = {
            'view_mode': 'list',
            'class_instance': class_instance,
            'session': session,
            'all_sessions': all_sessions,
            'results_page': results_page,
            'paginator': paginator,
            'stats': stats,
            'filter_form': filter_form,
            'is_htmx': is_htmx,
        }
        
        # Return appropriate template
        if is_htmx:
            return render(request, 'exams/results/partials/_list_results.html', context)
        else:
            return render(request, 'exams/results/class_dashboard.html', context)


@login_required
def class_results_selector(request):
    """
    Landing page for selecting a class to manage results.
    Shows all classes with student counts and quick stats.
    """
    # Get current session or allow selection
    session_id = request.GET.get('session')
    if session_id:
        try:
            session = AcademicSession.objects.get(id=session_id)
        except AcademicSession.DoesNotExist:
            session = None
    else:
        # Try to get current session
        session = AcademicSession.get_current_session()
        
        # If no current session, try to get any active session
        if not session:
            session = AcademicSession.objects.filter(is_active=True).order_by('-start_date').first()
    
    # Handle case where no sessions exist at all
    if not session:
        messages.warning(request, 'No academic session found. Please create an academic session first.')
        return redirect('academics:session_create')
    
    # If we found a session but it's not marked as current, show info message
    if not session.is_current:
        messages.info(
            request, 
            f'Using {session.name} as no current session is set. '
            f'You can select a different session from the dropdown.'
        )
    
    # Get all active classes for the current session
    classes = Class.objects.filter(
        is_active=True,
        academic_session=session
    ).select_related('academic_level').annotate(
        student_count=Count(
            'enrollments',
            filter=Q(
                enrollments__is_active=True,
                enrollments__completion_status='ONGOING'
            )
        )
    ).order_by('academic_level__order', 'section')
    
    # Get all sessions for dropdown
    all_sessions = AcademicSession.objects.filter(
        is_active=True
    ).order_by('-start_date')
    
    # Initialize totals
    total_students = 0
    total_results_entered = 0
    total_pending_results = 0
    
    # Get statistics for each class
    class_stats = []
    for class_instance in classes:
        # Count results entered for this class
        results_count = StudentExamResult.objects.filter(
            examination__target_classes=class_instance,
            examination__academic_session=session,
            score__isnull=False
        ).count()
        
        # Count total possible results (students × exams)
        total_exams = Examination.objects.filter(
            target_classes=class_instance,
            academic_session=session
        ).count()
        
        total_possible = class_instance.student_count * total_exams
        
        completion_percentage = 0
        if total_possible > 0:
            completion_percentage = (results_count / total_possible) * 100
        
        class_stats.append({
            'class': class_instance,
            'results_entered': results_count,
            'total_possible': total_possible,
            'completion_percentage': round(completion_percentage, 1),
            'student_count': class_instance.student_count
        })
        
        # Accumulate totals
        total_students += class_instance.student_count
        total_results_entered += results_count
        total_pending_results += (total_possible - results_count)
    
    context = {
        'class_stats': class_stats,
        'session': session,
        'all_sessions': all_sessions,
        'total_students': total_students,
        'total_results_entered': total_results_entered,
        'total_pending_results': total_pending_results,
    }
    
    return render(request, 'exams/results/class_selector.html', context)


@login_required
def student_result_detail(request, pk):
    """View student exam result details"""
    result = get_object_or_404(
        StudentExamResult.objects.select_related(
            'student', 'examination__subject', 'examination__academic_session',
            'examination__exam_category',  # ✅ ADDED
            'verified_by', 'moderator', 'grade_locked_by'
        ),
        pk=pk
    )
    
    # Get grade history if locked
    grade_history = None
    if result.is_grade_locked:
        grade_history = result.get_grade_history()
    
    # Get performance summary
    performance_summary = result.get_performance_summary()
    
    # ✅ ADDED: Get grading system being used
    grading_system = result.examination.get_effective_grading_system()
    
    context = {
        'result': result,
        'grade_history': grade_history,
        'performance_summary': performance_summary,
        'grading_system': grading_system,  # ✅ ADDED
    }
    
    return render(request, 'exams/results/detail.html', context)


@login_required
def student_result_create(request, examination_pk=None, student_pk=None):
    """Create new student exam result"""
    initial = {}
    if examination_pk:
        examination = get_object_or_404(Examination, pk=examination_pk)
        initial['examination'] = examination
    if student_pk:
        student = get_object_or_404(Student, pk=student_pk)
        initial['student'] = student
    
    if request.method == 'POST':
        form = StudentExamResultForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():  # ✅ ADDED transaction
                    result = form.save()
                    
                messages.success(request, f'Result for {result.student.get_full_name()} created successfully')
                return redirect('exams:result_detail', pk=result.pk)
            except Exception as e:
                logger.error(f"Error creating result: {e}", exc_info=True)  # ✅ ADDED exc_info
                messages.error(request, f'Error creating result: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below')
    else:
        form = StudentExamResultForm(initial=initial)
    
    context = {
        'form': form,
        'title': 'Enter Exam Result',
    }
    
    return render(request, 'exams/results/form.html', context)


@login_required
def student_result_edit(request, pk):
    """Edit student exam result"""
    result = get_object_or_404(StudentExamResult, pk=pk)
    
    # Check if grade is locked
    if result.is_grade_locked:
        messages.error(request, 'Cannot edit locked grades. Please unlock first.')
        return redirect('exams:result_detail', pk=pk)
    
    if request.method == 'POST':
        form = StudentExamResultForm(request.POST, instance=result)
        if form.is_valid():
            try:
                with transaction.atomic():  # ✅ ADDED transaction
                    result = form.save()
                    
                messages.success(request, f'Result for {result.student.get_full_name()} updated successfully')
                return redirect('exams:result_detail', pk=result.pk)
            except Exception as e:
                logger.error(f"Error updating result: {e}", exc_info=True)  # ✅ ADDED exc_info
                messages.error(request, f'Error updating result: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below')
    else:
        form = StudentExamResultForm(instance=result)
    
    context = {
        'form': form,
        'result': result,
        'title': f'Edit Result: {result.student.get_full_name()}',
    }
    
    return render(request, 'exams/results/form.html', context)


@login_required
def student_result_delete(request, pk):
    """Delete student exam result with HTMX support"""
    result = get_object_or_404(StudentExamResult, pk=pk)
    
    if request.method == 'POST':
        # Check if result is published or locked
        if result.is_published or result.is_grade_locked:
            error_msg = 'Cannot delete published or locked results'
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Trigger'] = 'showAlert'
                response['HX-Trigger-Data'] = f'{{"type": "error", "message": "{error_msg}"}}'
                return response
            else:
                messages.error(request, error_msg)
                return redirect('exams:result_detail', pk=pk)
        
        try:
            student_name = result.student.get_full_name()
            result.delete()
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Redirect'] = reverse('exams:result_list')
                response['HX-Trigger'] = 'showAlert'
                response['HX-Trigger-Data'] = f'{{"type": "success", "message": "Result for {student_name} deleted successfully"}}'
                return response
            else:
                messages.success(request, f'Result for {student_name} deleted successfully')
                return redirect('exams:result_list')
                
        except Exception as e:
            logger.error(f"Error deleting result: {e}", exc_info=True)  # ✅ ADDED exc_info
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Trigger'] = 'showAlert'
                response['HX-Trigger-Data'] = f'{{"type": "error", "message": "Error deleting result: {str(e)}"}}'
                return response
            else:
                messages.error(request, f'Error deleting result: {str(e)}')
                return redirect('exams:result_detail', pk=pk)


@login_required
def student_result_verify(request, pk):
    """Verify student exam result"""
    result = get_object_or_404(StudentExamResult, pk=pk)
    
    if request.method == 'POST':
        try:
            with transaction.atomic():  # ✅ ADDED transaction
                result.is_verified = True
                result.verified_by = request.user.staff if hasattr(request.user, 'staff') else None  # ✅ FIXED
                result.verification_date = get_school_current_time()
                result.save()
            
            messages.success(request, f'Result verified for {result.student.get_full_name()}')
            return redirect('exams:result_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error verifying result: {e}", exc_info=True)  # ✅ ADDED exc_info
            messages.error(request, f'Error: {str(e)}')
            return redirect('exams:result_detail', pk=pk)


@login_required
def student_result_moderate(request, pk):
    """Moderate student exam result"""
    result = get_object_or_404(StudentExamResult, pk=pk)
    
    if request.method == 'POST':
        try:
            moderated_score = request.POST.get('moderated_score')
            moderation_notes = request.POST.get('moderation_notes', '')
            
            # ✅ ADDED: Validate moderated score
            if not moderated_score:
                messages.error(request, 'Moderated score is required')
                return redirect('exams:result_detail', pk=pk)
            
            with transaction.atomic():  # ✅ ADDED transaction
                result.is_moderated = True
                result.moderated_score = Decimal(moderated_score)
                result.moderator = request.user.staff if hasattr(request.user, 'staff') else None  # ✅ FIXED
                result.moderation_notes = moderation_notes
                result.save()
            
            messages.success(request, f'Result moderated for {result.student.get_full_name()}')
            return redirect('exams:result_detail', pk=pk)
                
        except (ValueError, InvalidOperation) as e:  # ✅ ADDED specific exception
            logger.error(f"Invalid moderated score: {e}", exc_info=True)
            messages.error(request, 'Invalid moderated score value')
            return redirect('exams:result_detail', pk=pk)
        except Exception as e:
            logger.error(f"Error moderating result: {e}", exc_info=True)
            messages.error(request, f'Error: {str(e)}')
            return redirect('exams:result_detail', pk=pk)


# ✅ ADDED: Missing bulk operations view
@login_required
def bulk_result_entry(request, examination_pk):
    """Bulk entry of results for an examination"""
    examination = get_object_or_404(
        Examination.objects.select_related('subject', 'academic_session', 'exam_category'),
        pk=examination_pk
    )
    
    # Get students from target classes
    students = Student.objects.filter(
        class_enrollments__class_instance__in=examination.target_classes.all(),
        class_enrollments__academic_session=examination.academic_session,
        class_enrollments__is_active=True,
        class_enrollments__completion_status='ONGOING'
    ).distinct().order_by('first_name', 'last_name')
    
    if request.method == 'POST':
        try:
            results_created = 0
            results_updated = 0
            
            with transaction.atomic():
                for student in students:
                    score_key = f'score_{student.pk}'
                    score_value = request.POST.get(score_key, '').strip()
                    
                    if score_value:  # Only process if score is provided
                        score = Decimal(score_value)
                        
                        # Get or create result
                        result, created = StudentExamResult.objects.get_or_create(
                            student=student,
                            examination=examination,
                            defaults={'score': score, 'status': 'COMPLETED'}
                        )
                        
                        if created:
                            results_created += 1
                        else:
                            # Update existing result if not locked
                            if not result.is_grade_locked:
                                result.score = score
                                result.status = 'COMPLETED'
                                result.save()
                                results_updated += 1
            
            messages.success(
                request,
                f'Bulk entry complete: {results_created} results created, {results_updated} updated'
            )
            return redirect('exams:examination_detail', pk=examination.pk)
            
        except (ValueError, InvalidOperation) as e:
            logger.error(f"Invalid score in bulk entry: {e}", exc_info=True)
            messages.error(request, 'Invalid score value detected. Please check your entries.')
        except Exception as e:
            logger.error(f"Error in bulk result entry: {e}", exc_info=True)
            messages.error(request, f'Error: {str(e)}')
    
    # Get existing results
    existing_results = {
        r.student_id: r for r in StudentExamResult.objects.filter(
            examination=examination,
            student__in=students
        )
    }
    
    # Prepare student data
    student_data = []
    for student in students:
        existing_result = existing_results.get(student.pk)
        student_data.append({
            'student': student,
            'result': existing_result,
            'score': existing_result.score if existing_result else None,
            'is_locked': existing_result.is_grade_locked if existing_result else False,
        })
    
    context = {
        'examination': examination,
        'student_data': student_data,
        'title': f'Bulk Entry: {examination.name}',
    }
    
    return render(request, 'exams/results/bulk_entry.html', context)


# =============================================================================
# GRADE LOCKING VIEWS
# =============================================================================

@login_required
def lock_grade(request, pk):
    """Lock individual grade with HTMX support"""
    result = get_object_or_404(StudentExamResult, pk=pk)
    
    # Check permission
    if not request.user.has_perm('exams.lock_grades'):
        raise PermissionDenied("You don't have permission to lock grades")
    
    if request.method == 'POST':
        form = GradeLockForm(request.POST)
        if form.is_valid():
            try:
                reason = form.cleaned_data['lock_reason']
                success = result.lock_grade(locked_by=request.user, reason=reason)
                
                if success:
                    is_htmx = request.headers.get('HX-Request') == 'true'
                    if is_htmx:
                        response = HttpResponse()
                        response['HX-Redirect'] = reverse('exams:result_detail', kwargs={'pk': pk})
                        response['HX-Trigger'] = 'showAlert'
                        response['HX-Trigger-Data'] = '{"type": "success", "message": "Grade locked successfully"}'
                        return response
                    else:
                        messages.success(request, 'Grade locked successfully')
                        return redirect('exams:result_detail', pk=pk)
                else:
                    raise Exception("Failed to lock grade")
                    
            except Exception as e:
                logger.error(f"Error locking grade: {e}")
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Trigger'] = 'showAlert'
                    response['HX-Trigger-Data'] = f'{{"type": "error", "message": "Error locking grade: {str(e)}"}}'
                    return response
                else:
                    messages.error(request, f'Error locking grade: {str(e)}')
                    return redirect('exams:result_detail', pk=pk)


@login_required
def unlock_grade(request, pk):
    """Unlock individual grade with HTMX support"""
    result = get_object_or_404(StudentExamResult, pk=pk)
    
    # Check permission
    if not result.can_unlock_grade(request.user):
        raise PermissionDenied("You don't have permission to unlock this grade")
    
    if request.method == 'POST':
        form = GradeUnlockForm(request.POST)
        if form.is_valid():
            try:
                reason = form.cleaned_data['unlock_reason']
                success = result.unlock_grade(unlocked_by=request.user, reason=reason)
                
                if success:
                    is_htmx = request.headers.get('HX-Request') == 'true'
                    if is_htmx:
                        response = HttpResponse()
                        response['HX-Redirect'] = reverse('exams:result_detail', kwargs={'pk': pk})
                        response['HX-Trigger'] = 'showAlert'
                        response['HX-Trigger-Data'] = '{"type": "success", "message": "Grade unlocked successfully"}'
                        return response
                    else:
                        messages.success(request, 'Grade unlocked successfully')
                        return redirect('exams:result_detail', pk=pk)
                else:
                    raise Exception("Failed to unlock grade")
                    
            except Exception as e:
                logger.error(f"Error unlocking grade: {e}")
                is_htmx = request.headers.get('HX-Request') == 'true'
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Trigger'] = 'showAlert'
                    response['HX-Trigger-Data'] = f'{{"type": "error", "message": "Error unlocking grade: {str(e)}"}}'
                    return response
                else:
                    messages.error(request, f'Error unlocking grade: {str(e)}')
                    return redirect('exams:result_detail', pk=pk)


# =============================================================================
# BULK RESULT OPERATIONS
# =============================================================================

@login_required
def bulk_result_entry(request):
    """Step 1: Select examination for bulk result entry"""
    if request.method == 'POST':
        form = BulkResultEntryForm(request.POST)
        if form.is_valid():
            examination = form.cleaned_data['examination']
            target_class = form.cleaned_data.get('target_class')
            
            # Redirect to step 2 with parameters
            url = reverse('exams:bulk_result_entry_step2')
            params = f"?examination={examination.pk}"
            if target_class:
                params += f"&class={target_class.pk}"
            return redirect(url + params)
    else:
        form = BulkResultEntryForm()
    
    context = {
        'form': form,
        'title': 'Bulk Result Entry - Select Examination',
    }
    
    return render(request, 'exams/results/bulk_entry_step1.html', context)


@login_required
def bulk_result_entry_step2(request):
    """Step 2: Enter results for selected students"""
    examination_id = request.GET.get('examination')
    class_id = request.GET.get('class')
    
    examination = get_object_or_404(Examination, pk=examination_id)
    
    # Get students
    students = Student.objects.filter(enrollment_status='ACTIVE')
    if class_id:
        students = students.filter(current_class_id=class_id)
    
    # Get existing results
    existing_results = {
        r.student_id: r for r in StudentExamResult.objects.filter(
            examination=examination
        ).select_related('student')
    }
    
    if request.method == 'POST':
        try:
            created_count = 0
            updated_count = 0
            
            with transaction.atomic():
                for student in students:
                    score_key = f'score_{student.id}'
                    score = request.POST.get(score_key)
                    
                    if score:
                        score = Decimal(score)
                        
                        if student.id in existing_results:
                            # Update existing
                            result = existing_results[student.id]
                            result.score = score
                            result.status = 'COMPLETED'
                            result.save()
                            updated_count += 1
                        else:
                            # Create new
                            StudentExamResult.objects.create(
                                student=student,
                                examination=examination,
                                score=score,
                                status='COMPLETED'
                            )
                            created_count += 1
            
            messages.success(request, f'Successfully created {created_count} and updated {updated_count} result(s)')
            return redirect('exams:examination_detail', pk=examination.pk)
            
        except Exception as e:
            logger.error(f"Error in bulk result entry: {e}")
            messages.error(request, f'Error: {str(e)}')
    
    context = {
        'examination': examination,
        'students': students,
        'existing_results': existing_results,
        'title': f'Bulk Result Entry - {examination.name}',
    }
    
    return render(request, 'exams/results/bulk_entry_step2.html', context)


@login_required
def bulk_lock_grades(request):
    """Bulk lock grades for selected results"""
    if request.method == 'POST':
        try:
            result_ids = request.POST.getlist('results')
            reason = request.POST.get('reason', 'Bulk grade lock')
            
            results = StudentExamResult.objects.filter(id__in=result_ids)
            locked_count = 0
            
            for result in results:
                if result.lock_grade(locked_by=request.user, reason=reason):
                    locked_count += 1
            
            messages.success(request, f'Successfully locked {locked_count} grade(s)')
            return redirect('exams:result_list')
            
        except Exception as e:
            logger.error(f"Error in bulk grade lock: {e}")
            messages.error(request, f'Error: {str(e)}')
            return redirect('exams:result_list')


@login_required
def bulk_unlock_grades(request):
    """Bulk unlock grades for selected results"""
    if request.method == 'POST':
        try:
            result_ids = request.POST.getlist('results')
            reason = request.POST.get('reason', 'Bulk grade unlock')
            
            results = StudentExamResult.objects.filter(id__in=result_ids)
            unlocked_count = 0
            
            for result in results:
                if result.can_unlock_grade(request.user):
                    if result.unlock_grade(unlocked_by=request.user, reason=reason):
                        unlocked_count += 1
            
            messages.success(request, f'Successfully unlocked {unlocked_count} grade(s)')
            return redirect('exams:result_list')
            
        except Exception as e:
            logger.error(f"Error in bulk grade unlock: {e}")
            messages.error(request, f'Error: {str(e)}')
            return redirect('exams:result_list')


@login_required
def bulk_verify_results(request):
    """Bulk verify results"""
    if request.method == 'POST':
        try:
            result_ids = request.POST.getlist('results')
            
            updated_count = StudentExamResult.objects.filter(
                id__in=result_ids
            ).update(
                is_verified=True,
                verified_by=request.user,
                verification_date=get_school_current_time()
            )
            
            messages.success(request, f'Successfully verified {updated_count} result(s)')
            return redirect('exams:result_list')
            
        except Exception as e:
            logger.error(f"Error in bulk verify: {e}")
            messages.error(request, f'Error: {str(e)}')
            return redirect('exams:result_list')


@login_required
def bulk_publish_results(request):
    """Bulk publish results"""
    if request.method == 'POST':
        try:
            result_ids = request.POST.getlist('results')
            auto_lock = request.POST.get('auto_lock', 'false') == 'true'
            
            results = StudentExamResult.objects.filter(id__in=result_ids)
            
            with transaction.atomic():
                for result in results:
                    result.is_published = True
                    result.publication_date = get_school_current_time()
                    result.save()
                    
                    if auto_lock and not result.is_grade_locked:
                        result.lock_grade(
                            locked_by=request.user,
                            reason="Auto-locked during bulk publication"
                        )
            
            messages.success(request, f'Successfully published {results.count()} result(s)')
            return redirect('exams:result_list')
            
        except Exception as e:
            logger.error(f"Error in bulk publish: {e}")
            messages.error(request, f'Error: {str(e)}')
            return redirect('exams:result_list')


# =============================================================================
# RESULT PRINT VIEWS
# =============================================================================

@login_required
def student_result_print_detail(request, pk):
    """Print student result details"""
    result = get_object_or_404(StudentExamResult, pk=pk)
    
    context = {
        'result': result,
        'print_date': get_school_current_time(),
    }
    
    return render(request, 'exams/results/print_detail.html', context)


@login_required
def student_result_print_certificate(request, pk):
    """Print result certificate"""
    result = get_object_or_404(StudentExamResult, pk=pk)
    
    context = {
        'result': result,
        'print_date': get_school_current_time(),
    }
    
    return render(request, 'exams/results/print_certificate.html', context)


@login_required
def student_result_report_card(request, pk):
    """Generate student report card"""
    result = get_object_or_404(StudentExamResult, pk=pk)
    
    # Get all results for this student in the same session
    session_results = StudentExamResult.objects.filter(
        student=result.student,
        examination__academic_session=result.examination.academic_session
    ).select_related('examination__subject')
    
    context = {
        'result': result,
        'session_results': session_results,
        'print_date': get_school_current_time(),
    }
    
    return render(request, 'exams/results/report_card.html', context)


@login_required
def student_result_print_view(request):
    """Print filtered student results"""
    results = get_filtered_student_results(request)
    
    context = {
        'results': results,
        'print_date': get_school_current_time(),
    }
    
    return render(request, 'exams/results/print_list.html', context)


@login_required
def export_results_excel(request):
    """Export student results to Excel with filters applied"""
    results = get_filtered_student_results(request)
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Exam Results"
    
    # Define styles
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_alignment = Alignment(horizontal="center", vertical="center")
    
    # Headers
    headers = [
        '#', 'Student', 'Admission No', 'Examination', 'Subject',
        'Score', 'Grade', 'Percentage', 'Status', 'Pass/Fail', 'Published', 'Locked'
    ]
    ws.append(headers)
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
    
    # Data rows
    for idx, result in enumerate(results, start=1):
        ws.append([
            idx,
            result.student.get_full_name(),
            result.student.admission_number,
            result.examination.name,
            result.examination.subject.name,
            float(result.score) if result.score else '',
            result.grade,
            float(result.percentage) if result.percentage else '',
            result.get_status_display(),
            'Pass' if result.is_pass else 'Fail',
            'Yes' if result.is_published else 'No',
            'Yes' if result.is_grade_locked else 'No',
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
    filename = f"exam_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


# =============================================================================
# ANALYTICS VIEWS
# =============================================================================

@login_required
def exam_analytics_dashboard(request):
    """Main analytics dashboard"""
    current_session = get_active_academic_session()
    
    context = {
        'current_session': current_session,
    }
    
    return render(request, 'exams/analytics/dashboard.html', context)


@login_required
def examination_analytics(request, examination_pk):
    """View analytics for specific examination"""
    examination = get_object_or_404(Examination, pk=examination_pk)
    
    try:
        analytics = examination.analytics
    except ExamAnalytics.DoesNotExist:
        analytics = None
    
    context = {
        'examination': examination,
        'analytics': analytics,
    }
    
    return render(request, 'exams/analytics/examination.html', context)


@login_required
def generate_exam_analytics(request, examination_pk):
    """Generate analytics for examination"""
    examination = get_object_or_404(Examination, pk=examination_pk)
    
    try:
        results = examination.student_results.filter(status='COMPLETED')
        
        if not results.exists():
            messages.warning(request, 'No completed results to analyze')
            return redirect('exams:examination_detail', pk=examination_pk)
        
        # Calculate statistics
        stats = results.aggregate(
            highest=Max('score'),
            lowest=Min('score'),
            average=Avg('score'),
            total_students=Count('id'),
            pass_count=Count('id', filter=Q(is_pass=True)),
        )
        
        # Calculate grade distribution
        grade_distribution = {}
        for result in results:
            grade = result.grade
            if grade:
                grade_distribution[grade] = grade_distribution.get(grade, 0) + 1
        
        # Create or update analytics
        analytics, created = ExamAnalytics.objects.update_or_create(
            examination=examination,
            defaults={
                'total_students': results.count(),
                'students_appeared': results.count(),
                'students_passed': stats['pass_count'],
                'students_failed': results.count() - stats['pass_count'],
                'highest_score': stats['highest'],
                'lowest_score': stats['lowest'],
                'average_score': stats['average'],
                'pass_rate': (stats['pass_count'] / results.count() * 100) if results.count() > 0 else 0,
                'attendance_rate': 100.0,  # Assuming all registered students appeared
                'grade_distribution': grade_distribution,
            }
        )
        
        messages.success(request, 'Analytics generated successfully')
        return redirect('exams:examination_analytics', examination_pk=examination_pk)
        
    except Exception as e:
        logger.error(f"Error generating analytics: {e}")
        messages.error(request, f'Error generating analytics: {str(e)}')
        return redirect('exams:examination_detail', pk=examination_pk)


@login_required
def grade_distribution_analysis(request):
    """View grade distribution analysis"""
    context = {}
    return render(request, 'exams/analytics/grade_distribution.html', context)


@login_required
def performance_trends_analysis(request):
    """View performance trends analysis"""
    context = {}
    return render(request, 'exams/analytics/performance_trends.html', context)


@login_required
def subject_performance_analysis(request):
    """View subject performance analysis"""
    context = {}
    return render(request, 'exams/analytics/subject_performance.html', context)


# =============================================================================
# REPORT VIEWS
# =============================================================================

@login_required
def exam_performance_report(request):
    """Generate exam performance report"""
    context = {}
    return render(request, 'exams/reports/exam_performance.html', context)


@login_required
def student_comparison_report(request):
    """Generate student comparison report"""
    context = {}
    return render(request, 'exams/reports/student_comparison.html', context)


@login_required
def class_comparison_report(request):
    """Generate class comparison report"""
    context = {}
    return render(request, 'exams/reports/class_comparison.html', context)


@login_required
def exam_summary_report(request):
    """Generate exam summary report"""
    context = {}
    return render(request, 'exams/reports/exam_summary.html', context)


@login_required
def result_summary_report(request):
    """Generate result summary report"""
    context = {}
    return render(request, 'exams/reports/result_summary.html', context)


@login_required
def grade_sheet_report(request, examination_pk):
    """Generate grade sheet for examination"""
    examination = get_object_or_404(Examination, pk=examination_pk)
    results = examination.student_results.select_related('student').order_by('student__first_name', 'student__last_name')
    
    context = {
        'examination': examination,
        'results': results,
    }
    
    return render(request, 'exams/reports/grade_sheet.html', context)


@login_required
def mark_sheet_report(request, examination_pk):
    """Generate mark sheet for examination"""
    examination = get_object_or_404(Examination, pk=examination_pk)
    results = examination.student_results.select_related('student').order_by('student__first_name', 'student__last_name')
    
    context = {
        'examination': examination,
        'results': results,
    }
    
    return render(request, 'exams/reports/mark_sheet.html', context)


@login_required
def rank_list_report(request, examination_pk):
    """Generate rank list for examination"""
    examination = get_object_or_404(Examination, pk=examination_pk)
    results = examination.student_results.select_related('student').order_by('-score', 'student__first_name')
    
    context = {
        'examination': examination,
        'results': results,
    }
    
    return render(request, 'exams/reports/rank_list.html', context)


@login_required
def merit_list_report(request, examination_pk):
    """Generate merit list for examination"""
    examination = get_object_or_404(Examination, pk=examination_pk)
    results = examination.student_results.filter(is_pass=True).select_related('student').order_by('-score')[:50]
    
    context = {
        'examination': examination,
        'results': results,
    }
    
    return render(request, 'exams/reports/merit_list.html', context)


# =============================================================================
# EXAM TIMETABLE VIEWS
# =============================================================================

@login_required
def exam_timetable(request):
    """View exam timetable"""
    sessions = AcademicSession.objects.filter(is_active=True).order_by('-start_date')
    
    context = {
        'sessions': sessions,
    }
    
    return render(request, 'exams/timetable/index.html', context)


@login_required
def exam_timetable_session(request, session_pk):
    """View exam timetable for specific session"""
    session = get_object_or_404(AcademicSession, pk=session_pk)
    examinations = Examination.objects.filter(
        academic_session=session
    ).select_related('subject', 'exam_category').order_by('exam_date', 'start_time')
    
    context = {
        'session': session,
        'examinations': examinations,
    }
    
    return render(request, 'exams/timetable/session.html', context)


@login_required
def exam_timetable_print(request, session_pk):
    """Print exam timetable"""
    session = get_object_or_404(AcademicSession, pk=session_pk)
    examinations = Examination.objects.filter(
        academic_session=session
    ).select_related('subject', 'exam_category').order_by('exam_date', 'start_time')
    
    context = {
        'session': session,
        'examinations': examinations,
        'print_date': get_school_current_time(),
    }
    
    return render(request, 'exams/timetable/print.html', context)


@login_required
def exam_timetable_export_pdf(request, session_pk):
    """Export exam timetable as PDF"""
    # This would require a PDF library like ReportLab or WeasyPrint
    # For now, return a simple message
    messages.info(request, 'PDF export functionality coming soon')
    return redirect('exams:exam_timetable_session', session_pk=session_pk)


# =============================================================================
# IMPORT/EXPORT VIEWS
# =============================================================================

@login_required
def import_results(request):
    """Import results from Excel file"""
    if request.method == 'POST':
        try:
            # Handle file upload and import
            messages.info(request, 'Import functionality coming soon')
            return redirect('exams:result_list')
        except Exception as e:
            logger.error(f"Error importing results: {e}")
            messages.error(request, f'Error importing results: {str(e)}')
    
    context = {
        'title': 'Import Results',
    }
    
    return render(request, 'exams/import/results.html', context)


@login_required
def import_examinations(request):
    """Import examinations from Excel file"""
    if request.method == 'POST':
        try:
            # Handle file upload and import
            messages.info(request, 'Import functionality coming soon')
            return redirect('exams:examination_list')
        except Exception as e:
            logger.error(f"Error importing examinations: {e}")
            messages.error(request, f'Error importing examinations: {str(e)}')
    
    context = {
        'title': 'Import Examinations',
    }
    
    return render(request, 'exams/import/examinations.html', context)


@login_required
def download_results_template(request):
    """Download Excel template for results import"""
    wb = Workbook()
    ws = wb.active
    ws.title = "Results Template"
    
    # Headers
    headers = [
        'Admission Number', 'Examination Code', 'Score', 'Comments'
    ]
    ws.append(headers)
    
    # Create response
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="results_template.xlsx"'
    
    wb.save(response)
    return response


@login_required
def download_examinations_template(request):
    """Download Excel template for examinations import"""
    wb = Workbook()
    ws = wb.active
    ws.title = "Examinations Template"
    
    # Headers
    headers = [
        'Name', 'Code', 'Subject Code', 'Exam Date', 'Start Time', 'End Time', 'Total Marks'
    ]
    ws.append(headers)
    
    # Create response
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="examinations_template.xlsx"'
    
    wb.save(response)
    return response


# =============================================================================
# SETTINGS VIEWS
# =============================================================================

@login_required
def exam_settings(request):
    """Exam module settings"""
    context = {}
    return render(request, 'exams/settings/exam_settings.html', context)


@login_required
def grading_scale_settings(request):
    """Grading scale settings"""
    context = {}
    return render(request, 'exams/settings/grading_scale.html', context)


@login_required
def grade_locking_settings(request):
    """Grade locking settings"""
    context = {}
    return render(request, 'exams/settings/grade_locking.html', context)


# =============================================================================
# AJAX UTILITY ENDPOINTS
# =============================================================================

@login_required
def ajax_get_grading_system_ranges(request, system_pk):
    """AJAX endpoint to get grading ranges for a system"""
    try:
        system = get_object_or_404(GradingSystem, pk=system_pk)
        ranges = system.ranges.all().order_by('-min_score')
        
        data = {
            'ranges': [
                {
                    'id': r.id,
                    'grade': r.grade,
                    'min_score': float(r.min_score),
                    'max_score': float(r.max_score),
                    'gpa_points': float(r.gpa_points) if r.gpa_points else None,
                }
                for r in ranges
            ]
        }
        
        return JsonResponse(data)
    except Exception as e:
        logger.error(f"Error getting grading ranges: {e}")
        return JsonResponse({'error': str(e)}, status=400)


@login_required
def ajax_get_examinations_for_session(request, session_pk):
    """AJAX endpoint to get examinations for a session"""
    try:
        session = get_object_or_404(AcademicSession, pk=session_pk)
        examinations = Examination.objects.filter(academic_session=session).select_related('subject')
        
        data = {
            'examinations': [
                {
                    'id': e.id,
                    'name': e.name,
                    'code': e.code,
                    'subject': e.subject.name,
                    'exam_date': e.exam_date.strftime('%Y-%m-%d'),
                }
                for e in examinations
            ]
        }
        
        return JsonResponse(data)
    except Exception as e:
        logger.error(f"Error getting examinations: {e}")
        return JsonResponse({'error': str(e)}, status=400)


@login_required
def ajax_get_students_for_examination(request, examination_pk):
    """AJAX endpoint to get registered students for examination"""
    try:
        examination = get_object_or_404(Examination, pk=examination_pk)
        registrations = examination.registrations.select_related('student')
        
        data = {
            'students': [
                {
                    'id': r.student.id,
                    'name': r.student.get_full_name(),
                    'admission_number': r.student.admission_number,
                }
                for r in registrations
            ]
        }
        
        return JsonResponse(data)
    except Exception as e:
        logger.error(f"Error getting students: {e}")
        return JsonResponse({'error': str(e)}, status=400)


@login_required
def ajax_calculate_grade(request):
    """AJAX endpoint to calculate grade for a score"""
    try:
        score = Decimal(request.GET.get('score', 0))
        grading_system_id = request.GET.get('grading_system')
        
        grading_system = get_object_or_404(GradingSystem, pk=grading_system_id)
        grade_info = grading_system.get_grade_for_score(float(score))
        
        if grade_info:
            data = {
                'grade': grade_info['grade'],
                'gpa_points': grade_info['gpa_points'],
                'is_passing': grade_info['is_passing'],
                'comments': grade_info['comments'],
            }
        else:
            data = {'error': 'No grade found for score'}
        
        return JsonResponse(data)
    except Exception as e:
        logger.error(f"Error calculating grade: {e}")
        return JsonResponse({'error': str(e)}, status=400)


@login_required
def ajax_check_result_duplicate(request):
    """AJAX endpoint to check for duplicate result"""
    try:
        student_id = request.GET.get('student')
        examination_id = request.GET.get('examination')
        
        exists = StudentExamResult.objects.filter(
            student_id=student_id,
            examination_id=examination_id
        ).exists()
        
        return JsonResponse({'exists': exists})
    except Exception as e:
        logger.error(f"Error checking duplicate: {e}")
        return JsonResponse({'error': str(e)}, status=400)


@login_required
def ajax_get_exam_statistics(request, examination_pk):
    """AJAX endpoint to get examination statistics"""
    try:
        examination = get_object_or_404(Examination, pk=examination_pk)
        results = examination.student_results.filter(status='COMPLETED')
        
        stats = results.aggregate(
            total=Count('id'),
            highest=Max('score'),
            lowest=Min('score'),
            average=Avg('score'),
            pass_count=Count('id', filter=Q(is_pass=True)),
        )
        
        data = {
            'total_results': stats['total'],
            'highest_score': float(stats['highest']) if stats['highest'] else 0,
            'lowest_score': float(stats['lowest']) if stats['lowest'] else 0,
            'average_score': round(float(stats['average']), 2) if stats['average'] else 0,
            'pass_count': stats['pass_count'],
            'pass_rate': round((stats['pass_count'] / stats['total'] * 100), 2) if stats['total'] > 0 else 0,
        }
        
        return JsonResponse(data)
    except Exception as e:
        logger.error(f"Error getting exam statistics: {e}")
        return JsonResponse({'error': str(e)}, status=400)


@login_required
def ajax_validate_grade_unlock(request, result_pk):
    """AJAX endpoint to validate if grade can be unlocked"""
    try:
        result = get_object_or_404(StudentExamResult, pk=result_pk)
        can_unlock = result.can_unlock_grade(request.user)
        
        data = {
            'can_unlock': can_unlock,
            'is_locked': result.is_grade_locked,
            'locked_by': result.grade_locked_by.get_full_name() if result.grade_locked_by else None,
            'locked_at': result.grade_locked_at.strftime('%Y-%m-%d %H:%M') if result.grade_locked_at else None,
        }
        
        return JsonResponse(data)
    except Exception as e:
        logger.error(f"Error validating unlock: {e}")
        return JsonResponse({'error': str(e)}, status=400)
