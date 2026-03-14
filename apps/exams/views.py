"""
exams/views.py

Examination Management Views.

Contains:
- Dashboard
- Exam Category CRUD + actions + print/export
- Grading System CRUD + actions + print/export
- Class Grading System Assignment CRUD + bulk assign + print/export
- Examination CRUD + status + publish/unpublish + print/export
- Exam Registration CRUD + bulk + print/export
- Student Exam Results CRUD + bulk entry + grade locking + print/export
- class_category_results_entry  ← main result-entry grid
- Analytics
- Reports
- Timetable
- Import/Export templates
- AJAX utility endpoints

All views use school-timezone utilities from core.utils.
SweetAlert2 notifications via Django messages + HTMX HX-Trigger headers.
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
    ExamRegistrationFilterForm,
    StudentExamResultForm,
    StudentExamResultFilterForm,
    GradeLockForm,
    GradeUnlockForm,
    ResultPublishForm,
    BulkResultEntryForm,
    apply_result_filters,
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
    """Main exams dashboard with overview statistics."""
    try:
        today = get_school_today()
        current_session = get_active_academic_session()

        total_categories     = ExamCategory.objects.filter(is_active=True).count()
        total_grading_systems = GradingSystem.objects.filter(is_active=True).count()
        total_examinations   = Examination.objects.count()
        upcoming_exams       = Examination.objects.filter(
            exam_date__gte=today, status__in=['PLANNED', 'SCHEDULED']
        ).count()
        ongoing_exams        = Examination.objects.filter(status='ONGOING').count()
        completed_exams      = Examination.objects.filter(status='COMPLETED').count()

        total_results      = StudentExamResult.objects.count()
        published_results  = StudentExamResult.objects.filter(is_published=True).count()
        locked_grades      = StudentExamResult.objects.filter(is_grade_locked=True).count()
        pending_results    = StudentExamResult.objects.filter(
            status='SUBMITTED', is_published=False
        ).count()

        session_stats = {}
        if current_session:
            session_exams = Examination.objects.filter(academic_session=current_session)
            session_stats = {
                'total_exams': session_exams.count(),
                'completed':   session_exams.filter(status='COMPLETED').count(),
                'ongoing':     session_exams.filter(status='ONGOING').count(),
                'upcoming':    session_exams.filter(
                    exam_date__gte=today, status__in=['PLANNED', 'SCHEDULED']
                ).count(),
            }

        overview = {
            'total_categories':     total_categories,
            'total_grading_systems': total_grading_systems,
            'total_examinations':   total_examinations,
            'upcoming_exams':       upcoming_exams,
            'ongoing_exams':        ongoing_exams,
            'completed_exams':      completed_exams,
            'total_results':        total_results,
            'published_results':    published_results,
            'locked_grades':        locked_grades,
            'pending_results':      pending_results,
        }
    except Exception as e:
        logger.error(f"Error getting dashboard statistics: {e}")
        overview, current_session, session_stats = {}, None, {}

    today = get_school_today()

    recent_examinations = Examination.objects.select_related(
        'subject', 'academic_session', 'exam_category'
    ).order_by('-created_at')[:10]

    recent_results = StudentExamResult.objects.select_related(
        'student', 'examination__subject'
    ).order_by('-created_at')[:10]

    upcoming_examinations = Examination.objects.filter(
        exam_date__gte=today, status__in=['PLANNED', 'SCHEDULED']
    ).select_related('subject', 'exam_category').order_by('exam_date', 'start_time')[:10]

    unpublished_results = Examination.objects.filter(
        status='COMPLETED', results_published=False
    ).annotate(results_count=Count('student_results')).filter(
        results_count__gt=0
    ).order_by('exam_date')[:10]

    unlocked_published_results = StudentExamResult.objects.filter(
        is_published=True, is_grade_locked=False
    ).select_related('student', 'examination').order_by('-publication_date')[:10]

    context = {
        'overview':                   overview,
        'current_session':            current_session,
        'session_stats':              session_stats,
        'recent_examinations':        recent_examinations,
        'recent_results':             recent_results,
        'upcoming_examinations':      upcoming_examinations,
        'unpublished_results':        unpublished_results,
        'unlocked_published_results': unlocked_published_results,
    }
    return render(request, 'exams/dashboard.html', context)


# =============================================================================
# SHARED FILTER HELPERS
# =============================================================================

def _get_filtered_exam_categories(request):
    qs = ExamCategory.objects.prefetch_related(
        'applicable_levels', 'valid_sessions'
    ).order_by('category_type', 'name')

    q                    = request.GET.get('q', '').strip()
    category_type        = request.GET.get('category_type', '')
    frequency            = request.GET.get('frequency', '')
    is_active            = request.GET.get('is_active', '')
    curriculum           = request.GET.get('curriculum_compatibility', '')
    requires_reg         = request.GET.get('requires_registration', '')

    if q:
        qs = qs.filter(
            Q(name__icontains=q) | Q(abbreviation__icontains=q) |
            Q(code__icontains=q) | Q(description__icontains=q)
        )
    if category_type:  qs = qs.filter(category_type=category_type)
    if frequency:      qs = qs.filter(frequency=frequency)
    if is_active:      qs = qs.filter(is_active=(is_active.lower() == 'true'))
    if curriculum:     qs = qs.filter(curriculum_compatibility=curriculum)
    if requires_reg:   qs = qs.filter(requires_registration=(requires_reg.lower() == 'true'))
    return qs


def _get_filtered_grading_systems(request):
    qs = GradingSystem.objects.prefetch_related(
        'applicable_levels', 'applicable_subjects', 'ranges'
    ).annotate(ranges_count=Count('ranges')).order_by('grading_type', 'name')

    q            = request.GET.get('q', '').strip()
    grading_type = request.GET.get('grading_type', '')
    scale_type   = request.GET.get('scale_type', '')
    is_active    = request.GET.get('is_active', '')
    is_default   = request.GET.get('is_default', '')
    uses_gpa     = request.GET.get('uses_gpa', '')
    curriculum   = request.GET.get('curriculum_compatibility', '')

    if q:
        qs = qs.filter(
            Q(name__icontains=q) | Q(code__icontains=q) | Q(description__icontains=q)
        )
    if grading_type: qs = qs.filter(grading_type=grading_type)
    if scale_type:   qs = qs.filter(scale_type=scale_type)
    if is_active:    qs = qs.filter(is_active=(is_active.lower() == 'true'))
    if is_default:   qs = qs.filter(is_default=(is_default.lower() == 'true'))
    if uses_gpa:     qs = qs.filter(uses_gpa=(uses_gpa.lower() == 'true'))
    if curriculum:   qs = qs.filter(curriculum_compatibility=curriculum)
    return qs


def _get_filtered_class_grading_systems(request):
    qs = ClassGradingSystem.objects.select_related(
        'class_instance__academic_level', 'grading_system', 'academic_session', 'subject'
    ).order_by('-academic_session__start_date', 'class_instance__academic_level__order', 'priority')

    q               = request.GET.get('q', '').strip()
    class_id        = request.GET.get('class_id', '')
    academic_session = request.GET.get('academic_session', '')
    grading_system  = request.GET.get('grading_system', '')
    subject         = request.GET.get('subject', '')
    is_active       = request.GET.get('is_active', '')

    if q:
        qs = qs.filter(
            Q(class_instance__academic_level__name__icontains=q) |
            Q(grading_system__name__icontains=q) |
            Q(subject__name__icontains=q)
        )
    if class_id:          qs = qs.filter(class_instance_id=class_id)
    if academic_session:  qs = qs.filter(academic_session_id=academic_session)
    if grading_system:    qs = qs.filter(grading_system_id=grading_system)
    if subject:           qs = qs.filter(subject_id=subject)
    if is_active:         qs = qs.filter(is_active=(is_active.lower() == 'true'))
    return qs


def _get_filtered_examinations(request):
    qs = Examination.objects.select_related(
        'subject', 'academic_session', 'exam_category', 'grading_system', 'classroom'
    ).prefetch_related('target_classes', 'invigilators').order_by('-exam_date', 'start_time')

    q               = request.GET.get('q', '').strip()
    academic_session = request.GET.get('academic_session', '')
    exam_category   = request.GET.get('exam_category', '')
    subject         = request.GET.get('subject', '')
    status          = request.GET.get('status', '')
    exam_mode       = request.GET.get('exam_mode', '')
    date_from       = request.GET.get('exam_date_from', '')
    date_to         = request.GET.get('exam_date_to', '')

    if q:
        qs = qs.filter(
            Q(name__icontains=q) | Q(code__icontains=q) |
            Q(description__icontains=q) | Q(subject__name__icontains=q)
        )
    if academic_session: qs = qs.filter(academic_session_id=academic_session)
    if exam_category:    qs = qs.filter(exam_category_id=exam_category)
    if subject:          qs = qs.filter(subject_id=subject)
    if status:           qs = qs.filter(status=status)
    if exam_mode:        qs = qs.filter(exam_mode=exam_mode)
    if date_from:
        try:
            qs = qs.filter(exam_date__gte=datetime.strptime(date_from, '%Y-%m-%d').date())
        except (ValueError, TypeError):
            pass
    if date_to:
        try:
            qs = qs.filter(exam_date__lte=datetime.strptime(date_to, '%Y-%m-%d').date())
        except (ValueError, TypeError):
            pass
    return qs


def _get_filtered_exam_registrations(request):
    qs = ExamRegistration.objects.select_related(
        'student', 'examination__subject', 'examination__academic_session', 'registered_by'
    ).order_by('-registration_date')

    q               = request.GET.get('q', '').strip()
    examination     = request.GET.get('examination', '')
    status          = request.GET.get('registration_status', '')
    requires_assist = request.GET.get('requires_assistance', '')
    payment_verif   = request.GET.get('payment_verified', '')

    if q:
        words = q.split()
        combined = Q()
        for word in words:
            combined &= (
                Q(student__first_name__icontains=word) |
                Q(student__last_name__icontains=word) |
                Q(student__admission_number__icontains=word)
            )
        qs = qs.filter(combined)
    if examination:     qs = qs.filter(examination_id=examination)
    if status:          qs = qs.filter(status=status)
    if requires_assist: qs = qs.filter(requires_assistance=(requires_assist.lower() == 'true'))
    if payment_verif:   qs = qs.filter(payment_verified=(payment_verif.lower() == 'true'))
    return qs


def _get_filtered_student_results(request):
    qs = StudentExamResult.objects.select_related(
        'student', 'examination__subject', 'examination__academic_session'
    ).order_by('-examination__exam_date', 'student__first_name', 'student__last_name')

    q               = request.GET.get('q', '').strip()
    examination     = request.GET.get('examination', '')
    status          = request.GET.get('status', '')
    is_published    = request.GET.get('is_published', '')
    is_grade_locked = request.GET.get('is_grade_locked', '')
    is_pass         = request.GET.get('is_pass', '')
    min_score       = request.GET.get('min_score', '')
    max_score       = request.GET.get('max_score', '')
    class_instance  = request.GET.get('class_instance', '')

    if q:
        words = q.split()
        combined = Q()
        for word in words:
            combined &= (
                Q(student__first_name__icontains=word) |
                Q(student__last_name__icontains=word) |
                Q(student__middle_name__icontains=word) |
                Q(student__admission_number__icontains=word)
            )
        qs = qs.filter(combined)
    if examination:     qs = qs.filter(examination_id=examination)
    if status:          qs = qs.filter(status=status)
    if is_published:    qs = qs.filter(is_published=(is_published.lower() == 'true'))
    if is_grade_locked: qs = qs.filter(is_grade_locked=(is_grade_locked.lower() == 'true'))
    if is_pass:         qs = qs.filter(is_pass=(is_pass.lower() == 'true'))
    if min_score:
        try:
            qs = qs.filter(score__gte=Decimal(min_score))
        except (ValueError, InvalidOperation):
            pass
    if max_score:
        try:
            qs = qs.filter(score__lte=Decimal(max_score))
        except (ValueError, InvalidOperation):
            pass
    if class_instance:
        qs = qs.filter(
            student__class_enrollments__class_instance_id=class_instance,
            student__class_enrollments__is_active=True
        )
    return qs


# =============================================================================
# EXAM CATEGORY VIEWS
# =============================================================================

@login_required
def exam_category_list(request):
    filter_form = ExamCategoryFilterForm(request.GET or None)
    categories  = _get_filtered_exam_categories(request)

    stats = {
        'total':     categories.count(),
        'active':    categories.filter(is_active=True).count(),
        'inactive':  categories.filter(is_active=False).count(),
        'formative': categories.filter(category_type='FORMATIVE').count(),
        'summative': categories.filter(category_type='SUMMATIVE').count(),
        'internal':  categories.filter(category_type='INTERNAL').count(),
        'external':  categories.filter(category_type='EXTERNAL').count(),
    }

    paginator      = Paginator(categories, 20)
    categories_page = paginator.get_page(request.GET.get('page', 1))
    is_htmx        = request.headers.get('HX-Request') == 'true'

    context = {
        'categories_page': categories_page,
        'paginator':        paginator,
        'stats':            stats,
        'filter_form':      filter_form,
        'is_htmx':          is_htmx,
    }
    template = (
        'exams/categories/partials/_category_results.html' if is_htmx
        else 'exams/categories/list.html'
    )
    return render(request, template, context)


@login_required
def exam_category_detail(request, pk):
    category     = get_object_or_404(ExamCategory, pk=pk)
    examinations = category.examinations.select_related(
        'subject', 'academic_session'
    ).order_by('-exam_date')[:20]

    today = get_school_today()
    stats = {
        'total_exams':     category.examinations.count(),
        'active_exams':    category.examinations.filter(status='ONGOING').count(),
        'completed_exams': category.examinations.filter(status='COMPLETED').count(),
        'upcoming_exams':  category.examinations.filter(
            exam_date__gte=today, status__in=['PLANNED', 'SCHEDULED']
        ).count(),
    }
    return render(request, 'exams/categories/detail.html', {
        'category': category, 'examinations': examinations, 'stats': stats,
    })


@login_required
def exam_category_create(request):
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

    return render(request, 'exams/categories/form.html', {
        'form': form, 'title': 'Create Exam Category', 'submit_text': 'Create Category',
    })


@login_required
def exam_category_edit(request, pk):
    category = get_object_or_404(ExamCategory, pk=pk)
    today    = get_school_today()
    stats    = {
        'total_exams':     category.examinations.count(),
        'active_exams':    category.examinations.filter(status='ONGOING').count(),
        'completed_exams': category.examinations.filter(status='COMPLETED').count(),
        'upcoming_exams':  category.examinations.filter(
            exam_date__gte=today, status__in=['PLANNED', 'SCHEDULED']
        ).count(),
        'planned_exams':   category.examinations.filter(status='PLANNED').count(),
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

    return render(request, 'exams/categories/form.html', {
        'form': form, 'category': category,
        'title': 'Edit Exam Category', 'submit_text': 'Update Category', 'stats': stats,
    })


@login_required
def exam_category_delete(request, pk):
    category = get_object_or_404(ExamCategory, pk=pk)
    is_htmx  = request.headers.get('HX-Request') == 'true'

    if request.method == 'POST':
        if category.examinations.exists():
            msg = 'Cannot delete category with existing examinations'
            if is_htmx:
                r = HttpResponse()
                r['HX-Trigger']      = 'showAlert'
                r['HX-Trigger-Data'] = f'{{"type":"error","message":"{msg}"}}'
                return r
            messages.error(request, msg)
            return redirect('exams:category_detail', pk=pk)

        try:
            name = category.name
            category.delete()
            if is_htmx:
                r = HttpResponse()
                r['HX-Redirect']     = reverse('exams:category_list')
                r['HX-Trigger']      = 'showAlert'
                r['HX-Trigger-Data'] = f'{{"type":"success","message":"Category \\"{name}\\" deleted"}}'
                return r
            messages.success(request, f'Exam category "{name}" deleted successfully')
            return redirect('exams:category_list')
        except Exception as e:
            logger.error(f"Error deleting exam category: {e}")
            if is_htmx:
                r = HttpResponse()
                r['HX-Trigger']      = 'showAlert'
                r['HX-Trigger-Data'] = f'{{"type":"error","message":"{str(e)}"}}'
                return r
            messages.error(request, str(e))
            return redirect('exams:category_detail', pk=pk)


@login_required
def exam_category_toggle_active(request, pk):
    category = get_object_or_404(ExamCategory, pk=pk)
    if request.method == 'POST':
        try:
            category.is_active = not category.is_active
            category.save()
            status = 'activated' if category.is_active else 'deactivated'
            messages.success(request, f'Category "{category.name}" {status} successfully')
        except Exception as e:
            logger.error(f"Error toggling category: {e}")
            messages.error(request, str(e))
    return redirect('exams:category_detail', pk=pk)


@login_required
def exam_category_print_detail(request, pk):
    return render(request, 'exams/categories/print_detail.html', {
        'category':   get_object_or_404(ExamCategory, pk=pk),
        'print_date': get_school_current_time(),
    })


@login_required
def exam_category_print_view(request):
    return render(request, 'exams/categories/print_list.html', {
        'categories': _get_filtered_exam_categories(request),
        'print_date': get_school_current_time(),
    })


@login_required
def export_exam_categories_excel(request):
    categories = _get_filtered_exam_categories(request)
    wb = Workbook()
    ws = wb.active
    ws.title = 'Exam Categories'

    header_fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
    header_font = Font(bold=True, color='FFFFFF', size=12)

    headers = ['#', 'Name', 'Code', 'Type', 'Frequency', 'Weight %',
               'Requires Registration', 'Active', 'Curriculum']
    ws.append(headers)
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')

    for idx, cat in enumerate(categories, 1):
        ws.append([
            idx, cat.name, cat.code, cat.get_category_type_display(),
            cat.get_frequency_display(), float(cat.weight_percentage),
            'Yes' if cat.requires_registration else 'No',
            'Yes' if cat.is_active else 'No',
            cat.get_curriculum_compatibility_display(),
        ])

    for col in ws.columns:
        letter = get_column_letter(col[0].column)
        ws.column_dimensions[letter].width = min(
            max(len(str(c.value or '')) for c in col) + 2, 50
        )

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = (
        f'attachment; filename="exam_categories_{datetime.now():%Y%m%d_%H%M%S}.xlsx"'
    )
    wb.save(response)
    return response


# =============================================================================
# GRADING SYSTEM VIEWS
# =============================================================================

@login_required
def grading_system_list(request):
    filter_form = GradingSystemFilterForm(request.GET or None)
    systems     = _get_filtered_grading_systems(request)

    stats = {
        'total':       systems.count(),
        'active':      systems.filter(is_active=True).count(),
        'default':     systems.filter(is_default=True).count(),
        'with_gpa':    systems.filter(uses_gpa=True).count(),
        'letter_grade': systems.filter(grading_type='LETTER').count(),
        'numerical':   systems.filter(grading_type='NUMERICAL').count(),
    }

    paginator    = Paginator(systems, 20)
    systems_page = paginator.get_page(request.GET.get('page', 1))
    is_htmx      = request.headers.get('HX-Request') == 'true'

    context = {
        'systems_page': systems_page,
        'paginator':    paginator,
        'stats':        stats,
        'filter_form':  filter_form,
        'is_htmx':      is_htmx,
    }
    template = (
        'exams/grading_systems/partials/_system_results.html' if is_htmx
        else 'exams/grading_systems/list.html'
    )
    return render(request, template, context)


@login_required
def grading_system_detail(request, pk):
    system           = get_object_or_404(GradingSystem, pk=pk)
    ranges           = system.ranges.all().order_by('-min_score')
    class_assignments = system.class_assignments.select_related(
        'class_instance__academic_level', 'academic_session'
    ).filter(is_active=True).order_by('-academic_session__start_date')[:20]
    examinations     = system.examinations.select_related(
        'subject', 'academic_session'
    ).order_by('-exam_date')[:20]

    stats = {
        'total_ranges':     ranges.count(),
        'class_assignments': system.class_assignments.filter(is_active=True).count(),
        'examinations':     system.examinations.count(),
        'passing_ranges':   ranges.filter(is_passing_grade=True).count(),
        'failing_ranges':   ranges.filter(is_passing_grade=False).count(),
    }
    coverage_status = _check_grading_system_coverage(system, ranges)

    return render(request, 'exams/grading_systems/detail.html', {
        'system': system, 'ranges': ranges,
        'class_assignments': class_assignments, 'examinations': examinations,
        'stats': stats, 'coverage_status': coverage_status,
    })


@login_required
def grading_system_create(request):
    if request.method == 'POST':
        form    = GradingSystemForm(request.POST)
        formset = GradingRangeFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    system          = form.save()
                    formset.instance = system
                    formset.save()
                messages.success(request, f'Grading system "{system.name}" created successfully')
                return redirect('exams:grading_system_detail', pk=system.pk)
            except Exception as e:
                logger.error(f"Error creating grading system: {e}", exc_info=True)
                messages.error(request, f'Error creating grading system: {str(e)}')
        else:
            if form.errors:
                messages.error(request, 'Please correct the errors in the grading system details')
            if formset.errors or formset.non_form_errors():
                messages.error(request, 'Please correct the errors in the grade ranges')
    else:
        form    = GradingSystemForm()
        formset = GradingRangeFormSet()

    return render(request, 'exams/grading_systems/form.html', {
        'form': form, 'formset': formset,
        'title': 'Create Grading System', 'submit_text': 'Create Grading System',
        'is_edit': False,
    })


@login_required
def grading_system_edit(request, pk):
    system  = get_object_or_404(GradingSystem, pk=pk)
    today   = get_school_today()

    locked_count = StudentExamResult.objects.filter(
        examination__grading_system=system, is_grade_locked=True
    ).count()

    stats = {
        'total_ranges':      system.ranges.count(),
        'class_assignments': system.class_assignments.filter(is_active=True).count(),
        'examinations':      system.examinations.count(),
        'active_assignments': system.class_assignments.filter(
            is_active=True, effective_date__lte=today
        ).filter(Q(end_date__isnull=True) | Q(end_date__gte=today)).count(),
        'locked_grades_count': locked_count,
    }

    if request.method == 'POST':
        form    = GradingSystemForm(request.POST, instance=system)
        formset = GradingRangeFormSet(request.POST, instance=system)
        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    system = form.save()
                    formset.save()
                if locked_count:
                    messages.warning(
                        request,
                        f'Note: {locked_count} locked grade(s) were not recalculated.'
                    )
                messages.success(request, f'Grading system "{system.name}" updated successfully')
                return redirect('exams:grading_system_detail', pk=system.pk)
            except Exception as e:
                logger.error(f"Error updating grading system: {e}", exc_info=True)
                messages.error(request, f'Error updating grading system: {str(e)}')
        else:
            if form.errors:
                messages.error(request, 'Please correct the errors in the grading system details')
            if formset.errors or formset.non_form_errors():
                messages.error(request, 'Please correct the errors in the grade ranges')
    else:
        form    = GradingSystemForm(instance=system)
        formset = GradingRangeFormSet(instance=system)

    return render(request, 'exams/grading_systems/form.html', {
        'form': form, 'formset': formset, 'system': system,
        'title': f'Edit {system.name}', 'submit_text': 'Update Grading System',
        'is_edit': True, 'stats': stats,
        'has_locked_grades': locked_count > 0,
        'has_examinations':  stats['examinations'] > 0,
    })


@login_required
def grading_system_delete(request, pk):
    system  = get_object_or_404(GradingSystem, pk=pk)
    is_htmx = request.headers.get('HX-Request') == 'true'

    if request.method == 'POST':
        if system.is_default:
            msg = 'Cannot delete the default grading system'
            if is_htmx:
                r = HttpResponse()
                r['HX-Trigger']      = 'showAlert'
                r['HX-Trigger-Data'] = f'{{"type":"error","message":"{msg}"}}'
                return r
            messages.error(request, msg)
            return redirect('exams:grading_system_detail', pk=pk)

        if system.class_assignments.exists() or system.examinations.exists():
            msg = 'Cannot delete a grading system that has class assignments or examinations'
            if is_htmx:
                r = HttpResponse()
                r['HX-Trigger']      = 'showAlert'
                r['HX-Trigger-Data'] = f'{{"type":"error","message":"{msg}"}}'
                return r
            messages.error(request, msg)
            return redirect('exams:grading_system_detail', pk=pk)

        try:
            name = system.name
            system.delete()
            if is_htmx:
                r = HttpResponse()
                r['HX-Redirect']     = reverse('exams:grading_system_list')
                r['HX-Trigger']      = 'showAlert'
                r['HX-Trigger-Data'] = f'{{"type":"success","message":"System \\"{name}\\" deleted"}}'
                return r
            messages.success(request, f'Grading system "{name}" deleted successfully')
            return redirect('exams:grading_system_list')
        except Exception as e:
            logger.error(f"Error deleting grading system: {e}", exc_info=True)
            if is_htmx:
                r = HttpResponse()
                r['HX-Trigger']      = 'showAlert'
                r['HX-Trigger-Data'] = f'{{"type":"error","message":"{str(e)}"}}'
                return r
            messages.error(request, str(e))
            return redirect('exams:grading_system_detail', pk=pk)


@login_required
def grading_system_toggle_active(request, pk):
    system = get_object_or_404(GradingSystem, pk=pk)
    if request.method == 'POST':
        try:
            system.is_active = not system.is_active
            system.save()
            status = 'activated' if system.is_active else 'deactivated'
            messages.success(request, f'Grading system "{system.name}" {status} successfully')
        except Exception as e:
            logger.error(f"Error toggling grading system: {e}", exc_info=True)
            messages.error(request, str(e))
    return redirect('exams:grading_system_detail', pk=pk)


@login_required
def grading_system_set_default(request, pk):
    system = get_object_or_404(GradingSystem, pk=pk)
    if request.method == 'POST':
        try:
            with transaction.atomic():
                GradingSystem.objects.filter(is_default=True).update(is_default=False)
                system.is_default = True
                system.is_active  = True
                system.save()
            messages.success(request, f'"{system.name}" set as default grading system')
        except Exception as e:
            logger.error(f"Error setting default: {e}", exc_info=True)
            messages.error(request, str(e))
    return redirect('exams:grading_system_detail', pk=pk)


@login_required
def grading_system_print_detail(request, pk):
    system = get_object_or_404(GradingSystem, pk=pk)
    return render(request, 'exams/grading_systems/print_detail.html', {
        'system': system, 'ranges': system.ranges.all().order_by('-min_score'),
        'print_date': get_school_current_time(),
    })


@login_required
def grading_system_print_view(request):
    return render(request, 'exams/grading_systems/print_list.html', {
        'systems':    _get_filtered_grading_systems(request),
        'print_date': get_school_current_time(),
    })


@login_required
def export_grading_systems_excel(request):
    systems = _get_filtered_grading_systems(request)
    wb = Workbook()

    ws1 = wb.active
    ws1.title = 'Grading Systems'
    ws1.append(['#', 'Name', 'Code', 'Type', 'Scale', 'Min Score', 'Max Score',
                'Pass Mark', 'Uses GPA', 'Active', 'Default', 'Grade Ranges'])
    for idx, sys in enumerate(systems, 1):
        ws1.append([
            idx, sys.name, sys.code, sys.get_grading_type_display(),
            sys.get_scale_type_display(), float(sys.minimum_score),
            float(sys.maximum_score), float(sys.pass_mark),
            'Yes' if sys.uses_gpa else 'No',
            'Yes' if sys.is_active else 'No',
            'Yes' if sys.is_default else 'No',
            sys.ranges.count(),
        ])

    ws2 = wb.create_sheet('Grade Ranges')
    ws2.append(['#', 'Grading System', 'Grade', 'Grade Name', 'Min Score', 'Max Score',
                'Aggregate', 'GPA Points', 'Passing Grade'])
    row_num = 1
    for sys in systems:
        for gr in sys.ranges.all().order_by('-min_score'):
            ws2.append([
                row_num, sys.name, gr.grade, gr.grade_name or '',
                float(gr.min_score), float(gr.max_score),
                gr.aggregate or '',
                float(gr.gpa_points) if gr.gpa_points else '',
                'Yes' if gr.is_passing_grade else 'No',
            ])
            row_num += 1

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = (
        f'attachment; filename="grading_systems_{datetime.now():%Y%m%d_%H%M%S}.xlsx"'
    )
    wb.save(response)
    return response


# =============================================================================
# CLASS GRADING SYSTEM ASSIGNMENT VIEWS
# =============================================================================

@login_required
def class_grading_system_list(request):
    filter_form  = ClassGradingSystemFilterForm(request.GET or None)
    assignments  = _get_filtered_class_grading_systems(request)
    current_sess = get_active_academic_session()

    stats = {
        'total':           assignments.count(),
        'active':          assignments.filter(is_active=True).count(),
        'inactive':        assignments.filter(is_active=False).count(),
        'current_session': assignments.filter(
            academic_session=current_sess, is_active=True
        ).count() if current_sess else 0,
    }

    paginator        = Paginator(assignments, 20)
    assignments_page = paginator.get_page(request.GET.get('page', 1))
    is_htmx          = request.headers.get('HX-Request') == 'true'

    context = {
        'assignments_page': assignments_page,
        'paginator':         paginator,
        'stats':             stats,
        'filter_form':       filter_form,
        'is_htmx':           is_htmx,
    }
    template = (
        'exams/class_grading_systems/partials/_assignment_results.html' if is_htmx
        else 'exams/class_grading_systems/list.html'
    )
    return render(request, template, context)


@login_required
def class_grading_system_detail(request, pk):
    assignment = get_object_or_404(
        ClassGradingSystem.objects.select_related(
            'class_instance__academic_level', 'grading_system',
            'academic_session', 'subject', 'assigned_by'
        ), pk=pk
    )
    return render(request, 'exams/class_grading_systems/detail.html', {
        'assignment':         assignment,
        'grading_ranges':     assignment.grading_system.ranges.all().order_by('-min_score'),
        'is_currently_active': assignment.is_currently_active(),
    })


@login_required
def class_grading_system_create(request, class_pk=None):
    initial = {}
    if class_pk:
        cls = get_object_or_404(Class, pk=class_pk)
        initial = {'class_instance': cls, 'academic_session': cls.academic_session}

    if request.method == 'POST':
        form = ClassGradingSystemForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    assignment             = form.save(commit=False)
                    assignment.assigned_by = request.user
                    assignment.save()
                    form.save_m2m()
                messages.success(request, 'Grading system assignment created successfully')
                return redirect('exams:class_grading_system_detail', pk=assignment.pk)
            except Exception as e:
                logger.error(f"Error creating class grading system assignment: {e}", exc_info=True)
                messages.error(request, f'Error creating assignment: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below')
    else:
        form = ClassGradingSystemForm(initial=initial)

    return render(request, 'exams/class_grading_systems/form.html', {
        'form': form, 'title': 'Assign Grading System to Class',
    })


@login_required
def class_grading_system_edit(request, pk):
    assignment = get_object_or_404(ClassGradingSystem, pk=pk)

    if request.method == 'POST':
        form = ClassGradingSystemForm(request.POST, instance=assignment)
        if form.is_valid():
            try:
                with transaction.atomic():
                    assignment = form.save()
                messages.success(request, 'Grading system assignment updated successfully')
                return redirect('exams:class_grading_system_detail', pk=assignment.pk)
            except Exception as e:
                logger.error(f"Error updating class grading system assignment: {e}", exc_info=True)
                messages.error(request, f'Error updating assignment: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below')
    else:
        form = ClassGradingSystemForm(instance=assignment)

    return render(request, 'exams/class_grading_systems/form.html', {
        'form': form, 'assignment': assignment, 'title': 'Edit Grading System Assignment',
    })


@login_required
def class_grading_system_delete(request, pk):
    assignment = get_object_or_404(ClassGradingSystem, pk=pk)
    is_htmx    = request.headers.get('HX-Request') == 'true'

    if request.method == 'POST':
        try:
            assignment.delete()
            if is_htmx:
                r = HttpResponse()
                r['HX-Redirect']     = reverse('exams:class_grading_system_list')
                r['HX-Trigger']      = 'showAlert'
                r['HX-Trigger-Data'] = '{"type":"success","message":"Assignment deleted successfully"}'
                return r
            messages.success(request, 'Grading system assignment deleted successfully')
            return redirect('exams:class_grading_system_list')
        except Exception as e:
            logger.error(f"Error deleting class grading system assignment: {e}", exc_info=True)
            if is_htmx:
                r = HttpResponse()
                r['HX-Trigger']      = 'showAlert'
                r['HX-Trigger-Data'] = f'{{"type":"error","message":"{str(e)}"}}'
                return r
            messages.error(request, str(e))
            return redirect('exams:class_grading_system_detail', pk=pk)


@login_required
def class_grading_system_toggle_active(request, pk):
    assignment = get_object_or_404(ClassGradingSystem, pk=pk)
    if request.method == 'POST':
        try:
            assignment.is_active = not assignment.is_active
            assignment.save()
            status = 'activated' if assignment.is_active else 'deactivated'
            messages.success(request, f'Assignment {status} successfully')
        except Exception as e:
            logger.error(f"Error toggling assignment: {e}", exc_info=True)
            messages.error(request, str(e))
    return redirect('exams:class_grading_system_detail', pk=pk)


@login_required
def bulk_class_grading_system_assign(request):
    if request.method == 'POST':
        try:
            grading_system   = get_object_or_404(GradingSystem, pk=request.POST.get('grading_system'))
            academic_session = get_object_or_404(AcademicSession, pk=request.POST.get('academic_session'))
            class_ids        = request.POST.getlist('classes')
            subject_id       = request.POST.get('subject')
            subject          = get_object_or_404(Subject, pk=subject_id) if subject_id else None

            created  = 0
            skipped  = 0
            with transaction.atomic():
                for class_id in class_ids:
                    cls = get_object_or_404(Class, pk=class_id)
                    _, was_created = ClassGradingSystem.objects.get_or_create(
                        class_instance=cls,
                        grading_system=grading_system,
                        academic_session=academic_session,
                        subject=subject,
                        defaults={
                            'assigned_by':  request.user,
                            'effective_date': get_school_today(),
                        }
                    )
                    if was_created:
                        created += 1
                    else:
                        skipped += 1

            if created: messages.success(request, f'Assigned grading system to {created} class(es)')
            if skipped: messages.info(request,    f'Skipped {skipped} class(es) — assignment already exists')
            return redirect('exams:class_grading_system_list')
        except Exception as e:
            logger.error(f"Error in bulk grading system assignment: {e}", exc_info=True)
            messages.error(request, str(e))
            return redirect('exams:class_grading_system_list')

    return render(request, 'exams/class_grading_systems/bulk_assign.html', {
        'grading_systems': GradingSystem.objects.filter(is_active=True).order_by('name'),
        'sessions':        AcademicSession.objects.filter(is_active=True).order_by('-start_date'),
        'classes':         Class.objects.filter(is_active=True).select_related('academic_level')
                               .order_by('academic_level__order', 'section'),
        'subjects':        Subject.objects.filter(is_active=True).order_by('name'),
        'title':           'Bulk Assign Grading System',
    })


@login_required
def class_grading_system_print_view(request):
    return render(request, 'exams/class_grading_systems/print_list.html', {
        'assignments': _get_filtered_class_grading_systems(request),
        'print_date':  get_school_current_time(),
    })


@login_required
def export_class_grading_systems_excel(request):
    assignments = _get_filtered_class_grading_systems(request)
    wb = Workbook()
    ws = wb.active
    ws.title = 'Class Grading Systems'
    ws.append(['#', 'Class', 'Grading System', 'Session', 'Subject',
               'Effective Date', 'End Date', 'Priority', 'Active', 'Default'])
    for idx, a in enumerate(assignments, 1):
        ws.append([
            idx, str(a.class_instance), a.grading_system.name, a.academic_session.name,
            a.subject.name if a.subject else 'All Subjects',
            a.effective_date.strftime('%Y-%m-%d'),
            a.end_date.strftime('%Y-%m-%d') if a.end_date else 'N/A',
            a.priority,
            'Yes' if a.is_active else 'No',
            'Yes' if a.is_default_for_class else 'No',
        ])
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = (
        f'attachment; filename="class_grading_systems_{datetime.now():%Y%m%d_%H%M%S}.xlsx"'
    )
    wb.save(response)
    return response


# =============================================================================
# GRADING SYSTEM HELPERS
# =============================================================================

def _check_grading_system_coverage(system, ranges):
    """Return coverage status dict for a grading system's ranges."""
    if not ranges.exists():
        return {'has_coverage': False, 'has_gaps': True, 'gaps': [],
                'message': 'No grade ranges defined'}

    sorted_ranges = list(ranges.order_by('min_score'))
    gaps = []

    if sorted_ranges[0].min_score > system.minimum_score:
        gaps.append({'start': system.minimum_score, 'end': sorted_ranges[0].min_score,
                     'message': f'Gap from {system.minimum_score} to {sorted_ranges[0].min_score}'})

    for i in range(len(sorted_ranges) - 1):
        cur  = sorted_ranges[i]
        nxt  = sorted_ranges[i + 1]
        gap  = nxt.min_score - cur.max_score
        if gap > Decimal('0.01'):
            gaps.append({'start': cur.max_score, 'end': nxt.min_score,
                         'message': f'Gap from {cur.max_score} to {nxt.min_score}'})

    if sorted_ranges[-1].max_score < system.maximum_score:
        gaps.append({'start': sorted_ranges[-1].max_score, 'end': system.maximum_score,
                     'message': f'Gap from {sorted_ranges[-1].max_score} to {system.maximum_score}'})

    return {
        'has_coverage': len(gaps) == 0,
        'has_gaps':     len(gaps) > 0,
        'gaps':         gaps,
        'message':      'Complete coverage' if not gaps else f'{len(gaps)} gap(s) found',
    }


# =============================================================================
# EXAMINATION VIEWS
# =============================================================================

@login_required
def examination_list(request):
    filter_form  = ExaminationFilterForm(request.GET or None)
    examinations = _get_filtered_examinations(request)
    today        = get_school_today()

    stats = {
        'total':            examinations.count(),
        'planned':          examinations.filter(status='PLANNED').count(),
        'scheduled':        examinations.filter(status='SCHEDULED').count(),
        'ongoing':          examinations.filter(status='ONGOING').count(),
        'completed':        examinations.filter(status='COMPLETED').count(),
        'upcoming':         examinations.filter(
            exam_date__gte=today, status__in=['PLANNED', 'SCHEDULED']
        ).count(),
        'results_published': examinations.filter(results_published=True).count(),
    }

    paginator        = Paginator(examinations, 20)
    examinations_page = paginator.get_page(request.GET.get('page', 1))
    is_htmx          = request.headers.get('HX-Request') == 'true'

    context = {
        'examinations_page': examinations_page,
        'paginator':          paginator,
        'stats':              stats,
        'filter_form':        filter_form,
        'is_htmx':            is_htmx,
    }
    template = (
        'exams/examinations/partials/_examination_results.html' if is_htmx
        else 'exams/examinations/list.html'
    )
    return render(request, template, context)


@login_required
def examination_detail(request, pk):
    examination = get_object_or_404(
        Examination.objects.select_related(
            'subject', 'academic_session', 'exam_category', 'grading_system', 'classroom'
        ).prefetch_related('target_classes', 'invigilators'),
        pk=pk
    )

    registrations = examination.registrations.select_related('student').order_by('registration_date')[:50]
    results       = examination.student_results.select_related('student').order_by('-score')[:50]

    total_results = results.count()
    agg           = results.aggregate(
        highest=Max('score'), lowest=Min('score'), average=Avg('score'),
        pass_count=Count('id', filter=Q(is_pass=True)),
    )

    stats = {
        'total_registered': registrations.count(),
        'total_results':    total_results,
        'highest_score':    agg['highest'],
        'lowest_score':     agg['lowest'],
        'average_score':    round(agg['average'], 2) if agg['average'] else 0,
        'pass_count':       agg['pass_count'],
        'pass_rate':        round(agg['pass_count'] / total_results * 100, 2) if total_results else 0,
        'published_count':  results.filter(is_published=True).count(),
        'locked_count':     results.filter(is_grade_locked=True).count(),
    }

    return render(request, 'exams/examinations/detail.html', {
        'examination': examination, 'registrations': registrations,
        'results': results, 'stats': stats,
    })


@login_required
def examination_create(request):
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

    return render(request, 'exams/examinations/form.html', {
        'form': form, 'title': 'Create Examination',
    })


@login_required
def examination_edit(request, pk):
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

    return render(request, 'exams/examinations/form.html', {
        'form': form, 'examination': examination, 'title': 'Edit Examination',
    })


@login_required
def examination_delete(request, pk):
    examination = get_object_or_404(Examination, pk=pk)
    is_htmx     = request.headers.get('HX-Request') == 'true'

    if request.method == 'POST':
        if examination.student_results.exists():
            msg = 'Cannot delete an examination that already has results'
            if is_htmx:
                r = HttpResponse()
                r['HX-Trigger']      = 'showAlert'
                r['HX-Trigger-Data'] = f'{{"type":"error","message":"{msg}"}}'
                return r
            messages.error(request, msg)
            return redirect('exams:examination_detail', pk=pk)

        if examination.status in ['ONGOING', 'COMPLETED']:
            msg = 'Cannot delete an ongoing or completed examination'
            if is_htmx:
                r = HttpResponse()
                r['HX-Trigger']      = 'showAlert'
                r['HX-Trigger-Data'] = f'{{"type":"error","message":"{msg}"}}'
                return r
            messages.error(request, msg)
            return redirect('exams:examination_detail', pk=pk)

        try:
            name = examination.name
            examination.delete()
            if is_htmx:
                r = HttpResponse()
                r['HX-Redirect']     = reverse('exams:examination_list')
                r['HX-Trigger']      = 'showAlert'
                r['HX-Trigger-Data'] = f'{{"type":"success","message":"Examination \\"{name}\\" deleted"}}'
                return r
            messages.success(request, f'Examination "{name}" deleted successfully')
            return redirect('exams:examination_list')
        except Exception as e:
            logger.error(f"Error deleting examination: {e}")
            if is_htmx:
                r = HttpResponse()
                r['HX-Trigger']      = 'showAlert'
                r['HX-Trigger-Data'] = f'{{"type":"error","message":"{str(e)}"}}'
                return r
            messages.error(request, str(e))
            return redirect('exams:examination_detail', pk=pk)


@login_required
def examination_update_status(request, pk):
    examination = get_object_or_404(Examination, pk=pk)
    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status not in dict(Examination.EXAM_STATUS_CHOICES):
            messages.error(request, 'Invalid status')
        else:
            try:
                examination.status = new_status
                examination.save()
                messages.success(request, f'Status updated to {examination.get_status_display()}')
            except Exception as e:
                logger.error(f"Error updating examination status: {e}")
                messages.error(request, str(e))
    return redirect('exams:examination_detail', pk=pk)


@login_required
def publish_results(request, pk):
    examination = get_object_or_404(Examination, pk=pk)
    is_htmx     = request.headers.get('HX-Request') == 'true'

    if request.method == 'POST':
        form = ResultPublishForm(request.POST)
        if form.is_valid():
            try:
                auto_lock = form.cleaned_data['auto_lock_grades']
                with transaction.atomic():
                    examination.results_published        = True
                    examination.results_publication_date = get_school_current_time()
                    examination.save()

                    results = examination.student_results.filter(
                        status__in=['COMPLETED', 'SUBMITTED']
                    )
                    for result in results:
                        result.is_published      = True
                        result.publication_date  = get_school_current_time()
                        result.save()
                        if auto_lock and not result.is_grade_locked:
                            result.lock_grade(
                                locked_by=request.user,
                                reason='Auto-locked during result publication'
                            )
                    count  = results.count()
                    locked = results.filter(is_grade_locked=True).count() if auto_lock else 0

                msg = f'Published {count} result(s)'
                if auto_lock:
                    msg += f' and locked {locked} grade(s)'
                if is_htmx:
                    r = HttpResponse()
                    r['HX-Redirect']     = reverse('exams:examination_detail', kwargs={'pk': pk})
                    r['HX-Trigger']      = 'showAlert'
                    r['HX-Trigger-Data'] = f'{{"type":"success","message":"{msg}"}}'
                    return r
                messages.success(request, msg)
                return redirect('exams:examination_detail', pk=pk)
            except Exception as e:
                logger.error(f"Error publishing results: {e}")
                if is_htmx:
                    r = HttpResponse()
                    r['HX-Trigger']      = 'showAlert'
                    r['HX-Trigger-Data'] = f'{{"type":"error","message":"{str(e)}"}}'
                    return r
                messages.error(request, str(e))
                return redirect('exams:examination_detail', pk=pk)

    return render(request, 'exams/examinations/publish_form.html', {
        'examination': examination,
        'form':        ResultPublishForm(),
    })


@login_required
def unpublish_results(request, pk):
    examination = get_object_or_404(Examination, pk=pk)
    if request.method == 'POST':
        try:
            with transaction.atomic():
                examination.results_published        = False
                examination.results_publication_date = None
                examination.save()
                for result in examination.student_results.all():
                    result.is_published     = False
                    result.publication_date = None
                    result.save()
            messages.success(request, 'Results unpublished successfully')
        except Exception as e:
            logger.error(f"Error unpublishing results: {e}")
            messages.error(request, str(e))
    return redirect('exams:examination_detail', pk=pk)


@login_required
def examination_print_detail(request, pk):
    return render(request, 'exams/examinations/print_detail.html', {
        'examination': get_object_or_404(Examination, pk=pk),
        'print_date':  get_school_current_time(),
    })


@login_required
def examination_print_timetable(request, pk):
    return render(request, 'exams/examinations/print_timetable.html', {
        'examination': get_object_or_404(Examination, pk=pk),
        'print_date':  get_school_current_time(),
    })


@login_required
def examination_print_answer_sheet(request, pk):
    return render(request, 'exams/examinations/print_answer_sheet.html', {
        'examination': get_object_or_404(Examination, pk=pk),
        'print_date':  get_school_current_time(),
    })


@login_required
def examination_print_view(request):
    return render(request, 'exams/examinations/print_list.html', {
        'examinations': _get_filtered_examinations(request),
        'print_date':   get_school_current_time(),
    })


@login_required
def export_examinations_excel(request):
    examinations = _get_filtered_examinations(request)
    wb = Workbook()
    ws = wb.active
    ws.title = 'Examinations'

    hf = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
    ws.append(['#', 'Name', 'Code', 'Subject', 'Session', 'Category',
               'Date', 'Time', 'Total Marks', 'Pass Marks', 'Status'])
    for cell in ws[1]:
        cell.fill      = hf
        cell.font      = Font(bold=True, color='FFFFFF', size=12)
        cell.alignment = Alignment(horizontal='center', vertical='center')

    for idx, exam in enumerate(examinations, 1):
        ws.append([
            idx, exam.name, exam.code, exam.subject.name, exam.academic_session.name,
            exam.exam_category.name, exam.exam_date.strftime('%Y-%m-%d'),
            f"{exam.start_time.strftime('%H:%M')} - {exam.end_time.strftime('%H:%M')}",
            float(exam.total_marks), float(exam.pass_marks), exam.get_status_display(),
        ])

    for col in ws.columns:
        letter = get_column_letter(col[0].column)
        ws.column_dimensions[letter].width = min(
            max(len(str(c.value or '')) for c in col) + 2, 50
        )

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = (
        f'attachment; filename="examinations_{datetime.now():%Y%m%d_%H%M%S}.xlsx"'
    )
    wb.save(response)
    return response


# =============================================================================
# EXAM REGISTRATION VIEWS
# =============================================================================

@login_required
def exam_registration_list(request):
    filter_form   = ExamRegistrationFilterForm(request.GET or None)
    registrations = _get_filtered_exam_registrations(request)

    stats = {
        'total':            registrations.count(),
        'confirmed':        registrations.filter(status='CONFIRMED').count(),
        'pending':          registrations.filter(status='PENDING').count(),
        'cancelled':        registrations.filter(status='CANCELLED').count(),
        'payment_verified': registrations.filter(payment_verified=True).count(),
    }

    paginator         = Paginator(registrations, 50)
    registrations_page = paginator.get_page(request.GET.get('page', 1))
    is_htmx           = request.headers.get('HX-Request') == 'true'

    context = {
        'registrations_page': registrations_page,
        'paginator':           paginator,
        'stats':               stats,
        'filter_form':         filter_form,
        'is_htmx':             is_htmx,
    }
    template = (
        'exams/registrations/_registration_results.html' if is_htmx
        else 'exams/registrations/list.html'
    )
    return render(request, template, context)


@login_required
def exam_registration_detail(request, pk):
    registration = get_object_or_404(
        ExamRegistration.objects.select_related(
            'student', 'examination__subject', 'examination__academic_session', 'registered_by'
        ), pk=pk
    )
    return render(request, 'exams/registrations/detail.html', {'registration': registration})


@login_required
def exam_registration_create(request, examination_pk=None, student_pk=None):
    initial = {}
    if examination_pk:
        initial['examination'] = get_object_or_404(Examination, pk=examination_pk)
    if student_pk:
        initial['student'] = get_object_or_404(Student, pk=student_pk)

    if request.method == 'POST':
        form = ExamRegistrationForm(request.POST)
        if form.is_valid():
            try:
                registration = form.save(commit=False)
                registration.registered_by = request.user
                registration.save()
                messages.success(
                    request,
                    f'Exam registration for {registration.student.get_full_name()} created successfully'
                )
                return redirect('exams:registration_detail', pk=registration.pk)
            except Exception as e:
                logger.error(f"Error creating exam registration: {e}")
                messages.error(request, f'Error creating registration: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below')
    else:
        form = ExamRegistrationForm(initial=initial)

    return render(request, 'exams/registrations/form.html', {
        'form': form, 'title': 'Register for Examination',
    })


@login_required
def exam_registration_edit(request, pk):
    registration = get_object_or_404(ExamRegistration, pk=pk)

    if request.method == 'POST':
        form = ExamRegistrationForm(request.POST, instance=registration)
        if form.is_valid():
            try:
                registration = form.save()
                messages.success(
                    request,
                    f'Registration for {registration.student.get_full_name()} updated successfully'
                )
                return redirect('exams:registration_detail', pk=registration.pk)
            except Exception as e:
                logger.error(f"Error updating exam registration: {e}")
                messages.error(request, f'Error updating registration: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below')
    else:
        form = ExamRegistrationForm(instance=registration)

    return render(request, 'exams/registrations/form.html', {
        'form': form, 'registration': registration, 'title': 'Edit Exam Registration',
    })


@login_required
def exam_registration_delete(request, pk):
    registration = get_object_or_404(ExamRegistration, pk=pk)
    is_htmx      = request.headers.get('HX-Request') == 'true'

    if request.method == 'POST':
        try:
            name = registration.student.get_full_name()
            registration.delete()
            if is_htmx:
                r = HttpResponse()
                r['HX-Redirect']     = reverse('exams:registration_list')
                r['HX-Trigger']      = 'showAlert'
                r['HX-Trigger-Data'] = f'{{"type":"success","message":"Registration for {name} deleted"}}'
                return r
            messages.success(request, f'Registration for {name} deleted successfully')
            return redirect('exams:registration_list')
        except Exception as e:
            logger.error(f"Error deleting exam registration: {e}")
            if is_htmx:
                r = HttpResponse()
                r['HX-Trigger']      = 'showAlert'
                r['HX-Trigger-Data'] = f'{{"type":"error","message":"{str(e)}"}}'
                return r
            messages.error(request, str(e))
            return redirect('exams:registration_detail', pk=pk)


@login_required
def exam_registration_update_status(request, pk):
    registration = get_object_or_404(ExamRegistration, pk=pk)
    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status not in dict(ExamRegistration.REGISTRATION_STATUS_CHOICES):
            messages.error(request, 'Invalid status')
        else:
            try:
                registration.status = new_status
                registration.save()
                messages.success(request, f'Status updated to {registration.get_status_display()}')
            except Exception as e:
                logger.error(f"Error updating registration status: {e}")
                messages.error(request, str(e))
    return redirect('exams:registration_detail', pk=pk)


@login_required
def exam_registration_verify_payment(request, pk):
    registration = get_object_or_404(ExamRegistration, pk=pk)
    if request.method == 'POST':
        try:
            registration.payment_verified          = True
            registration.payment_verification_date = get_school_current_time()
            registration.save()
            messages.success(request, f'Payment verified for {registration.student.get_full_name()}')
        except Exception as e:
            logger.error(f"Error verifying payment: {e}")
            messages.error(request, str(e))
    return redirect('exams:registration_detail', pk=pk)


@login_required
def bulk_exam_registration_create(request):
    if request.method == 'POST':
        try:
            examination = get_object_or_404(Examination, pk=request.POST.get('examination'))
            student_ids = request.POST.getlist('students')
            created     = 0
            with transaction.atomic():
                for student_id in student_ids:
                    student = get_object_or_404(Student, pk=student_id)
                    _, was_created = ExamRegistration.objects.get_or_create(
                        student=student, examination=examination,
                        defaults={'registered_by': request.user, 'status': 'PENDING'}
                    )
                    if was_created:
                        created += 1
            messages.success(request, f'Registered {created} student(s)')
            return redirect('exams:registration_list')
        except Exception as e:
            logger.error(f"Error in bulk exam registration: {e}")
            messages.error(request, str(e))
            return redirect('exams:registration_list')

    return render(request, 'exams/registrations/bulk_create.html', {
        'examinations': Examination.objects.filter(
            status__in=['PLANNED', 'SCHEDULED']
        ).select_related('subject', 'academic_session').order_by('-exam_date'),
        'students': Student.objects.filter(enrollment_status='ACTIVE').order_by('first_name', 'last_name'),
        'title': 'Bulk Exam Registration',
    })


@login_required
def bulk_exam_registration_update_status(request):
    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status not in dict(ExamRegistration.REGISTRATION_STATUS_CHOICES):
            messages.error(request, 'Invalid status')
            return redirect('exams:registration_list')
        try:
            count = ExamRegistration.objects.filter(
                id__in=request.POST.getlist('registrations')
            ).update(status=new_status)
            messages.success(request, f'Updated {count} registration(s)')
        except Exception as e:
            logger.error(f"Error in bulk status update: {e}")
            messages.error(request, str(e))
    return redirect('exams:registration_list')


@login_required
def exam_registration_print_detail(request, pk):
    return render(request, 'exams/registrations/print_detail.html', {
        'registration': get_object_or_404(ExamRegistration, pk=pk),
        'print_date':   get_school_current_time(),
    })


@login_required
def exam_registration_print_view(request):
    return render(request, 'exams/registrations/print_list.html', {
        'registrations': _get_filtered_exam_registrations(request),
        'print_date':    get_school_current_time(),
    })


@login_required
def export_exam_registrations_excel(request):
    registrations = _get_filtered_exam_registrations(request)
    wb = Workbook()
    ws = wb.active
    ws.title = 'Exam Registrations'
    ws.append(['#', 'Student', 'Admission No', 'Examination', 'Subject',
               'Registration Date', 'Status', 'Payment Verified'])
    for idx, reg in enumerate(registrations, 1):
        ws.append([
            idx, reg.student.get_full_name(), reg.student.admission_number,
            reg.examination.name, reg.examination.subject.name,
            reg.registration_date.strftime('%Y-%m-%d %H:%M'),
            reg.get_status_display(),
            'Yes' if reg.payment_verified else 'No',
        ])
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = (
        f'attachment; filename="exam_registrations_{datetime.now():%Y%m%d_%H%M%S}.xlsx"'
    )
    wb.save(response)
    return response


# =============================================================================
# RESULTS — CLASS SELECTOR
# =============================================================================

@login_required
def class_results_selector(request):
    """
    Step 1: pick an academic session, see all classes with completion stats.
    Then click a class to go to class_results_dashboard.
    """
    session_id = request.GET.get('session')
    if session_id:
        session = get_object_or_404(AcademicSession, pk=session_id)
    else:
        session = AcademicSession.get_current_session()
        if not session:
            session = AcademicSession.objects.filter(is_active=True).order_by('-start_date').first()

    if not session:
        messages.warning(request, 'No academic session found. Please create one first.')
        return redirect('academics:session_create')

    if not session.is_current:
        messages.info(
            request,
            f'Using {session.name} — no current session is marked active. '
            'Select a different session from the dropdown if needed.'
        )

    classes = Class.objects.filter(
        is_active=True, academic_session=session
    ).select_related('academic_level').annotate(
        student_count=Count(
            'enrollments',
            filter=Q(enrollments__is_active=True, enrollments__completion_status='ONGOING')
        )
    ).order_by('academic_level__order', 'section')

    all_sessions = AcademicSession.objects.filter(is_active=True).order_by('-start_date')

    total_students          = 0
    total_results_entered   = 0
    total_pending_results   = 0
    class_stats             = []

    for cls in classes:
        results_count = StudentExamResult.objects.filter(
            examination__target_classes=cls,
            examination__academic_session=session,
            score__isnull=False
        ).count()
        total_exams    = Examination.objects.filter(
            target_classes=cls, academic_session=session
        ).count()
        total_possible = cls.student_count * total_exams
        completion_pct = round(results_count / total_possible * 100, 1) if total_possible else 0

        class_stats.append({
            'class':              cls,
            'results_entered':    results_count,
            'total_possible':     total_possible,
            'completion_percentage': completion_pct,
            'student_count':      cls.student_count,
        })

        total_students        += cls.student_count
        total_results_entered += results_count
        total_pending_results += (total_possible - results_count)

    return render(request, 'exams/results/class_selector.html', {
        'class_stats':           class_stats,
        'session':               session,
        'all_sessions':          all_sessions,
        'total_students':        total_students,
        'total_results_entered': total_results_entered,
        'total_pending_results': total_pending_results,
    })


# =============================================================================
# RESULTS — CLASS DASHBOARD  (read-only overview + list mode)
# =============================================================================

@login_required
def class_results_dashboard(request, class_pk):
    """
    Two modes:
      mode=dashboard  — category tabs with subject columns, read-only.
                        Each tab has an "Enter Results" button that goes to
                        class_category_results_entry.
      mode=list       — paginated table of individual results with filters.
    """
    class_instance = get_object_or_404(Class, pk=class_pk)

    session_id = request.GET.get('session')
    session    = (
        get_object_or_404(AcademicSession, pk=session_id) if session_id
        else class_instance.academic_session or AcademicSession.get_current_session()
    )
    if not session:
        messages.warning(request, 'No current academic session found.')
        return redirect('academics:session_list')

    all_sessions = AcademicSession.objects.filter(is_active=True).order_by('-start_date')
    view_mode    = request.GET.get('mode', 'dashboard')
    is_htmx      = request.headers.get('HX-Request') == 'true'

    # ------------------------------------------------------------------
    # STUDENT QUERYSET
    # For current/future sessions only show actively enrolled students.
    # For past sessions include completed enrollments so historical data
    # is visible (enrollment is_active=False, completion_status='COMPLETED').
    # ------------------------------------------------------------------
    today = get_school_today()

    enrollment_filter = dict(
        class_enrollments__class_instance=class_instance,
        class_enrollments__academic_session=session,
    )
    if session.end_date >= today:
        enrollment_filter['class_enrollments__is_active']        = True
        enrollment_filter['class_enrollments__completion_status'] = 'ONGOING'

    students = Student.objects.filter(
        **enrollment_filter
    ).distinct().order_by('first_name', 'last_name')

    # ------------------------------------------------------------------
    # DASHBOARD MODE
    # ------------------------------------------------------------------
    if view_mode == 'dashboard':
        selected_abbr   = request.GET.get('tab')
        exam_categories = ExamCategory.objects.filter(is_active=True).order_by('name')
        examinations    = Examination.objects.filter(
            target_classes=class_instance, academic_session=session
        ).select_related('exam_category', 'subject').order_by('subject__name')

        exams_by_category = {}
        for exam in examinations:
            abbr = exam.exam_category.abbreviation
            if abbr not in exams_by_category:
                exams_by_category[abbr] = {'category': exam.exam_category, 'exams': []}
            exams_by_category[abbr]['exams'].append(exam)

        # Default to first category if none selected
        if not selected_abbr and exams_by_category:
            selected_abbr = next(iter(exams_by_category.keys()))

        results_data      = []
        category_subjects = []
        selected_category = None

        if selected_abbr and selected_abbr in exams_by_category:
            cat_data          = exams_by_category[selected_abbr]
            category_exams    = cat_data['exams']
            selected_category = cat_data['category']
            category_subjects = [e.subject.name for e in category_exams]

            # Pre-fetch all relevant results in one query
            result_map = {}
            for result in StudentExamResult.objects.filter(
                examination__in=category_exams, student__in=students
            ).select_related('examination'):
                result_map[(result.student_id, result.examination_id)] = result

            for student in students:
                subject_results = {}
                scores = []
                for exam in category_exams:
                    result = result_map.get((student.pk, exam.pk))
                    subject_results[exam.subject.name] = {
                        'result':       result,
                        'exam':         exam,
                        'score':        result.score if result else None,
                        'grade':        result.grade if result else None,
                        'is_locked':    result.is_grade_locked if result else False,
                        'is_published': result.is_published if result else False,
                    }
                    if result and result.score is not None:
                        scores.append(result.score)

                results_data.append({
                    'student':         student,
                    'subject_results': subject_results,
                    'total':           sum(scores),
                    'average':         round(sum(scores) / len(scores), 2) if scores else 0,
                    'subjects_taken':  len(scores),
                })

            results_data.sort(key=lambda x: x['total'], reverse=True)
            for i, row in enumerate(results_data, 1):
                row['position'] = i

        stats = {
            'total_students': students.count(),
            'total_exams':    examinations.count(),
            'categories':     exam_categories.count(),
            'results_entered': StudentExamResult.objects.filter(
                examination__target_classes=class_instance,
                examination__academic_session=session,
                score__isnull=False
            ).count(),
            'published_results': StudentExamResult.objects.filter(
                examination__target_classes=class_instance,
                examination__academic_session=session,
                is_published=True
            ).count(),
            'locked_results': StudentExamResult.objects.filter(
                examination__target_classes=class_instance,
                examination__academic_session=session,
                is_grade_locked=True
            ).count(),
        }

        context = {
            'view_mode':         'dashboard',
            'class_instance':    class_instance,
            'session':           session,
            'all_sessions':      all_sessions,
            'exam_categories':   exam_categories,
            'selected_abbr':     selected_abbr,
            'selected_category': selected_category,
            'exams_by_category': exams_by_category,
            'results_data':      results_data,
            'category_subjects': category_subjects,
            'students':          students,
            'stats':             stats,
            'is_htmx':           is_htmx,
        }
        template = (
            'exams/results/partials/_dashboard_results.html' if is_htmx
            else 'exams/results/class_dashboard.html'
        )
        return render(request, template, context)

    # ------------------------------------------------------------------
    # LIST MODE
    # ------------------------------------------------------------------
    filter_form = StudentExamResultFilterForm(request.GET or None)

    # Mirror the same past-session logic for the results queryset —
    # past sessions must not filter by is_active/completion_status
    # or the join eliminates all rows.
    list_enrollment_filter = dict(
        student__class_enrollments__class_instance=class_instance,
        student__class_enrollments__academic_session=session,
        examination__academic_session=session,
    )
    if session.end_date >= today:
        list_enrollment_filter['student__class_enrollments__is_active'] = True

    results = StudentExamResult.objects.filter(
        **list_enrollment_filter
    ).select_related(
        'student', 'examination__subject', 'examination__exam_category',
        'verified_by', 'moderator', 'grade_locked_by'
    ).distinct().order_by('-examination__exam_date', 'student__first_name')

    if filter_form.is_valid():
        results = apply_result_filters(results, filter_form)

    total_graded = results.filter(score__isnull=False).count()
    pass_count   = results.filter(is_pass=True, score__isnull=False).count()

    stats = {
        'total':     results.count(),
        'published': results.filter(is_published=True).count(),
        'locked':    results.filter(is_grade_locked=True).count(),
        'pass':      pass_count,
        'fail':      total_graded - pass_count,
        'completed': results.filter(status='COMPLETED').count(),
        'pending':   results.filter(status__in=['NOT_STARTED', 'IN_PROGRESS']).count(),
        'pass_rate': round(pass_count / total_graded * 100, 1) if total_graded else 0,
    }

    paginator    = Paginator(results, 50)
    results_page = paginator.get_page(request.GET.get('page', 1))

    context = {
        'view_mode':      'list',
        'class_instance': class_instance,
        'session':        session,
        'all_sessions':   all_sessions,
        'results_page':   results_page,
        'paginator':      paginator,
        'stats':          stats,
        'filter_form':    filter_form,
        'is_htmx':        is_htmx,
    }
    template = (
        'exams/results/partials/_list_results.html' if is_htmx
        else 'exams/results/class_dashboard.html'
    )
    return render(request, template, context)


# =============================================================================
# RESULTS — MAIN ENTRY GRID  (class + category)
# =============================================================================

@login_required
def class_category_results_entry(request, class_pk, category_pk):
    """
    The primary result-entry surface.

    URL:  /exams/results/<class_pk>/entry/<category_pk>/
    GET:  renders a grid — students (rows) × subjects in this category (columns)
          with any existing scores pre-filled and locked cells shown as read-only.
    POST: validates and saves all submitted scores in a single transaction,
          then redirects back to the dashboard for that class/category.

    Field naming convention: score_<student_pk>_<examination_pk>
    """
    class_instance = get_object_or_404(Class, pk=class_pk)
    category       = get_object_or_404(ExamCategory, pk=category_pk)

    # Resolve session
    session_id = request.GET.get('session') or request.POST.get('session')
    session    = (
        get_object_or_404(AcademicSession, pk=session_id) if session_id
        else class_instance.academic_session
    )

    # All examinations for this class / category / session
    examinations = Examination.objects.filter(
        target_classes=class_instance,
        exam_category=category,
        academic_session=session
    ).select_related('subject').order_by('subject__name')

    if not examinations.exists():
        messages.warning(
            request,
            f'No examinations found for {category.name} in {class_instance}. '
            'Create examinations first.'
        )
        return redirect(
            reverse('exams:class_results_dashboard', kwargs={'class_pk': class_pk})
            + f'?session={session.pk}&mode=dashboard&tab={category.abbreviation}'
        )

    # Students enrolled in this class
    students = Student.objects.filter(
        class_enrollments__class_instance=class_instance,
        class_enrollments__academic_session=session,
        class_enrollments__is_active=True,
        class_enrollments__completion_status='ONGOING'
    ).distinct().order_by('first_name', 'last_name')

    # Pre-load existing results (avoids N+1 queries in the template)
    existing = {}
    for result in StudentExamResult.objects.filter(
        examination__in=examinations, student__in=students
    ).select_related('examination'):
        existing[(result.student_id, result.examination_id)] = result

    # ------------------------------------------------------------------
    # POST — save scores
    # ------------------------------------------------------------------
    if request.method == 'POST':
        form_errors       = []
        saved_count       = 0
        skipped_locked    = 0

        try:
            with transaction.atomic():
                for student in students:
                    for exam in examinations:
                        field = f'score_{student.pk}_{exam.pk}'
                        raw   = request.POST.get(field, '').strip()

                        if not raw:
                            continue  # blank = leave unchanged

                        try:
                            score = Decimal(raw)
                        except InvalidOperation:
                            form_errors.append(
                                f'Invalid value "{raw}" for '
                                f'{student.get_full_name()} / {exam.subject.name}'
                            )
                            continue

                        if score < 0 or score > exam.total_marks:
                            form_errors.append(
                                f'Score {score} is out of range '
                                f'(0 – {exam.total_marks}) for '
                                f'{student.get_full_name()} / {exam.subject.name}'
                            )
                            continue

                        result = existing.get((student.pk, exam.pk))

                        if result:
                            if result.is_grade_locked:
                                skipped_locked += 1
                                continue
                            result.score  = score
                            result.status = 'COMPLETED'
                            result.save()
                        else:
                            result = StudentExamResult.objects.create(
                                student     = student,
                                examination = exam,
                                score       = score,
                                status      = 'COMPLETED',
                            )
                            existing[(student.pk, exam.pk)] = result

                        saved_count += 1

                if form_errors:
                    # Re-raise to trigger rollback
                    raise ValidationError(form_errors)

        except ValidationError as ve:
            for err in ve.messages:
                messages.error(request, err)
            # Re-render the form with the errors visible
            # (rebuild grid data below and fall through to GET render)
        except Exception as e:
            logger.error(f"Error saving results for {class_instance} / {category}: {e}", exc_info=True)
            messages.error(request, f'Unexpected error saving results: {str(e)}')
        else:
            # No exceptions — success
            if skipped_locked:
                messages.warning(
                    request,
                    f'{skipped_locked} result(s) were skipped because their grades are locked.'
                )
            messages.success(request, f'Saved {saved_count} result(s) successfully.')
            return redirect(
                reverse('exams:class_results_dashboard', kwargs={'class_pk': class_pk})
                + f'?session={session.pk}&mode=dashboard&tab={category.abbreviation}'
            )

    # ------------------------------------------------------------------
    # GET (or POST with errors) — build grid
    # ------------------------------------------------------------------
    grid = []
    for student in students:
        row = {'student': student, 'cells': []}
        for exam in examinations:
            result = existing.get((student.pk, exam.pk))
            row['cells'].append({
                'exam':         exam,
                'result':       result,
                'score':        result.score if result else None,
                'grade':        result.grade if result else '',
                'is_locked':    result.is_grade_locked if result else False,
                'is_published': result.is_published if result else False,
                'field_name':   f'score_{student.pk}_{exam.pk}',
            })
        grid.append(row)

    # Summary counts for the info bar
    total_cells    = students.count() * examinations.count()
    filled_cells   = sum(
        1 for (sid, eid), r in existing.items() if r.score is not None
    )
    locked_cells   = sum(1 for r in existing.values() if r.is_grade_locked)

    return render(request, 'exams/results/entry_grid.html', {
        'class_instance': class_instance,
        'category':       category,
        'session':        session,
        'examinations':   examinations,
        'grid':           grid,
        'total_cells':    total_cells,
        'filled_cells':   filled_cells,
        'locked_cells':   locked_cells,
        'back_url': (
            reverse('exams:class_results_dashboard', kwargs={'class_pk': class_pk})
            + f'?session={session.pk}&mode=dashboard&tab={category.abbreviation}'
        ),
    })


# =============================================================================
# RESULTS — INDIVIDUAL RESULT VIEWS
# =============================================================================

@login_required
def result_list(request):
    """Global list of all results with filtering."""
    filter_form = StudentExamResultFilterForm(request.GET or None)
    results     = _get_filtered_student_results(request)

    total_graded = results.filter(score__isnull=False).count()
    pass_count   = results.filter(is_pass=True, score__isnull=False).count()

    stats = {
        'total':     results.count(),
        'published': results.filter(is_published=True).count(),
        'locked':    results.filter(is_grade_locked=True).count(),
        'pass':      pass_count,
        'fail':      total_graded - pass_count,
        'pass_rate': round(pass_count / total_graded * 100, 1) if total_graded else 0,
    }

    # Resolve optional class/session context so the template
    # can render back-links when filtering by class
    class_instance = None
    session        = None
    class_id       = request.GET.get('class_instance')
    session_id     = request.GET.get('session')
    if class_id:
        class_instance = Class.objects.filter(pk=class_id).first()
    if session_id:
        session = AcademicSession.objects.filter(pk=session_id).first()
    if class_instance and not session:
        session = class_instance.academic_session

    paginator    = Paginator(results, 50)
    results_page = paginator.get_page(request.GET.get('page', 1))
    is_htmx      = request.headers.get('HX-Request') == 'true'

    context = {
        'results_page':  results_page,
        'paginator':     paginator,
        'stats':         stats,
        'filter_form':   filter_form,
        'class_instance': class_instance,
        'session':        session,
        'is_htmx':        is_htmx,
    }
    template = (
        'exams/results/partials/_result_rows.html' if is_htmx
        else 'exams/results/list.html'
    )
    return render(request, template, context)


@login_required
def student_result_detail(request, pk):
    result = get_object_or_404(
        StudentExamResult.objects.select_related(
            'student', 'examination__subject', 'examination__academic_session',
            'examination__exam_category', 'verified_by', 'moderator', 'grade_locked_by'
        ), pk=pk
    )
    return render(request, 'exams/results/detail.html', {
        'result':              result,
        'grade_history':       result.get_grade_history() if result.is_grade_locked else None,
        'performance_summary': result.get_performance_summary(),
        'grading_system':      result.examination.get_effective_grading_system(),
    })


@login_required
def student_result_create(request, examination_pk=None, student_pk=None):
    initial = {}
    if examination_pk:
        initial['examination'] = get_object_or_404(Examination, pk=examination_pk)
    if student_pk:
        initial['student'] = get_object_or_404(Student, pk=student_pk)

    if request.method == 'POST':
        form = StudentExamResultForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    result = form.save()
                messages.success(request, f'Result for {result.student.get_full_name()} created successfully')
                return redirect('exams:result_detail', pk=result.pk)
            except Exception as e:
                logger.error(f"Error creating result: {e}", exc_info=True)
                messages.error(request, f'Error creating result: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below')
    else:
        form = StudentExamResultForm(initial=initial)

    return render(request, 'exams/results/form.html', {'form': form, 'title': 'Enter Exam Result'})


@login_required
def student_result_edit(request, pk):
    result = get_object_or_404(StudentExamResult, pk=pk)
    if result.is_grade_locked:
        messages.error(request, 'Cannot edit a locked grade. Please unlock it first.')
        return redirect('exams:result_detail', pk=pk)

    if request.method == 'POST':
        form = StudentExamResultForm(request.POST, instance=result)
        if form.is_valid():
            try:
                with transaction.atomic():
                    result = form.save()
                messages.success(request, f'Result for {result.student.get_full_name()} updated successfully')
                return redirect('exams:result_detail', pk=result.pk)
            except Exception as e:
                logger.error(f"Error updating result: {e}", exc_info=True)
                messages.error(request, f'Error updating result: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below')
    else:
        form = StudentExamResultForm(instance=result)

    return render(request, 'exams/results/form.html', {
        'form': form, 'result': result,
        'title': f'Edit Result: {result.student.get_full_name()}',
    })


@login_required
def student_result_delete(request, pk):
    result  = get_object_or_404(StudentExamResult, pk=pk)
    is_htmx = request.headers.get('HX-Request') == 'true'

    if request.method == 'POST':
        if result.is_published or result.is_grade_locked:
            msg = 'Cannot delete a published or locked result'
            if is_htmx:
                r = HttpResponse()
                r['HX-Trigger']      = 'showAlert'
                r['HX-Trigger-Data'] = f'{{"type":"error","message":"{msg}"}}'
                return r
            messages.error(request, msg)
            return redirect('exams:result_detail', pk=pk)

        try:
            name = result.student.get_full_name()
            result.delete()
            if is_htmx:
                r = HttpResponse()
                r['HX-Redirect']     = reverse('exams:result_list')
                r['HX-Trigger']      = 'showAlert'
                r['HX-Trigger-Data'] = f'{{"type":"success","message":"Result for {name} deleted"}}'
                return r
            messages.success(request, f'Result for {name} deleted successfully')
            return redirect('exams:result_list')
        except Exception as e:
            logger.error(f"Error deleting result: {e}", exc_info=True)
            if is_htmx:
                r = HttpResponse()
                r['HX-Trigger']      = 'showAlert'
                r['HX-Trigger-Data'] = f'{{"type":"error","message":"{str(e)}"}}'
                return r
            messages.error(request, str(e))
            return redirect('exams:result_detail', pk=pk)


@login_required
def student_result_verify(request, pk):
    result = get_object_or_404(StudentExamResult, pk=pk)
    if request.method == 'POST':
        try:
            with transaction.atomic():
                result.is_verified       = True
                result.verified_by       = getattr(request.user, 'staff', None)
                result.verification_date = get_school_current_time()
                result.save()
            messages.success(request, f'Result verified for {result.student.get_full_name()}')
        except Exception as e:
            logger.error(f"Error verifying result: {e}", exc_info=True)
            messages.error(request, str(e))
    return redirect('exams:result_detail', pk=pk)


@login_required
def student_result_moderate(request, pk):
    result = get_object_or_404(StudentExamResult, pk=pk)
    if request.method == 'POST':
        raw_score       = request.POST.get('moderated_score', '').strip()
        moderation_notes = request.POST.get('moderation_notes', '')
        if not raw_score:
            messages.error(request, 'Moderated score is required')
            return redirect('exams:result_detail', pk=pk)
        try:
            with transaction.atomic():
                result.is_moderated      = True
                result.moderated_score   = Decimal(raw_score)
                result.moderator         = getattr(request.user, 'staff', None)
                result.moderation_notes  = moderation_notes
                result.save()
            messages.success(request, f'Result moderated for {result.student.get_full_name()}')
        except (ValueError, InvalidOperation):
            messages.error(request, 'Invalid moderated score value')
        except Exception as e:
            logger.error(f"Error moderating result: {e}", exc_info=True)
            messages.error(request, str(e))
    return redirect('exams:result_detail', pk=pk)


# =============================================================================
# GRADE LOCKING VIEWS
# =============================================================================

@login_required
def lock_grade(request, pk):
    result  = get_object_or_404(StudentExamResult, pk=pk)
    is_htmx = request.headers.get('HX-Request') == 'true'

    if not request.user.has_perm('exams.lock_grades'):
        raise PermissionDenied("You don't have permission to lock grades")

    if request.method == 'POST':
        form = GradeLockForm(request.POST)
        if form.is_valid():
            try:
                success = result.lock_grade(
                    locked_by=request.user,
                    reason=form.cleaned_data['lock_reason']
                )
                if success:
                    if is_htmx:
                        r = HttpResponse()
                        r['HX-Redirect']     = reverse('exams:result_detail', kwargs={'pk': pk})
                        r['HX-Trigger']      = 'showAlert'
                        r['HX-Trigger-Data'] = '{"type":"success","message":"Grade locked successfully"}'
                        return r
                    messages.success(request, 'Grade locked successfully')
                    return redirect('exams:result_detail', pk=pk)
                raise Exception('lock_grade returned False')
            except Exception as e:
                logger.error(f"Error locking grade: {e}")
                if is_htmx:
                    r = HttpResponse()
                    r['HX-Trigger']      = 'showAlert'
                    r['HX-Trigger-Data'] = f'{{"type":"error","message":"{str(e)}"}}'
                    return r
                messages.error(request, str(e))

    return render(request, 'exams/results/lock_grade_form.html', {
        'result': result, 'form': GradeLockForm(),
    })


@login_required
def unlock_grade(request, pk):
    result  = get_object_or_404(StudentExamResult, pk=pk)
    is_htmx = request.headers.get('HX-Request') == 'true'

    if not result.can_unlock_grade(request.user):
        raise PermissionDenied("You don't have permission to unlock this grade")

    if request.method == 'POST':
        form = GradeUnlockForm(request.POST)
        if form.is_valid():
            try:
                success = result.unlock_grade(
                    unlocked_by=request.user,
                    reason=form.cleaned_data['unlock_reason']
                )
                if success:
                    if is_htmx:
                        r = HttpResponse()
                        r['HX-Redirect']     = reverse('exams:result_detail', kwargs={'pk': pk})
                        r['HX-Trigger']      = 'showAlert'
                        r['HX-Trigger-Data'] = '{"type":"success","message":"Grade unlocked successfully"}'
                        return r
                    messages.success(request, 'Grade unlocked successfully')
                    return redirect('exams:result_detail', pk=pk)
                raise Exception('unlock_grade returned False')
            except Exception as e:
                logger.error(f"Error unlocking grade: {e}")
                if is_htmx:
                    r = HttpResponse()
                    r['HX-Trigger']      = 'showAlert'
                    r['HX-Trigger-Data'] = f'{{"type":"error","message":"{str(e)}"}}'
                    return r
                messages.error(request, str(e))

    return render(request, 'exams/results/unlock_grade_form.html', {
        'result': result, 'form': GradeUnlockForm(),
    })


# =============================================================================
# BULK RESULT OPERATIONS
# =============================================================================

@login_required
def bulk_result_entry(request, examination_pk):
    """
    Bulk-entry form for a single examination — all enrolled students on one page.
    Typically reached from the examination detail page.
    For the class-category grid (multiple subjects at once) use
    class_category_results_entry instead.
    """
    examination = get_object_or_404(
        Examination.objects.select_related('subject', 'academic_session', 'exam_category'),
        pk=examination_pk
    )

    students = Student.objects.filter(
        class_enrollments__class_instance__in=examination.target_classes.all(),
        class_enrollments__academic_session=examination.academic_session,
        class_enrollments__is_active=True,
        class_enrollments__completion_status='ONGOING'
    ).distinct().order_by('first_name', 'last_name')

    existing = {
        r.student_id: r for r in StudentExamResult.objects.filter(
            examination=examination, student__in=students
        )
    }

    if request.method == 'POST':
        errors  = []
        created = 0
        updated = 0
        try:
            with transaction.atomic():
                for student in students:
                    raw = request.POST.get(f'score_{student.pk}', '').strip()
                    if not raw:
                        continue
                    try:
                        score = Decimal(raw)
                    except InvalidOperation:
                        errors.append(f'Invalid score for {student.get_full_name()}')
                        continue
                    if score < 0 or score > examination.total_marks:
                        errors.append(
                            f'Score {score} out of range for {student.get_full_name()}'
                        )
                        continue

                    if student.pk in existing:
                        result = existing[student.pk]
                        if result.is_grade_locked:
                            continue
                        result.score  = score
                        result.status = 'COMPLETED'
                        result.save()
                        updated += 1
                    else:
                        StudentExamResult.objects.create(
                            student=student, examination=examination,
                            score=score, status='COMPLETED'
                        )
                        created += 1

                if errors:
                    raise ValidationError(errors)

        except ValidationError as ve:
            for err in ve.messages:
                messages.error(request, err)
        except Exception as e:
            logger.error(f"Error in bulk result entry: {e}", exc_info=True)
            messages.error(request, f'Error: {str(e)}')
        else:
            messages.success(
                request,
                f'Bulk entry complete: {created} created, {updated} updated.'
            )
            return redirect('exams:examination_detail', pk=examination.pk)

    student_data = [{
        'student':   student,
        'result':    existing.get(student.pk),
        'score':     existing[student.pk].score if student.pk in existing else None,
        'is_locked': existing[student.pk].is_grade_locked if student.pk in existing else False,
    } for student in students]

    return render(request, 'exams/results/bulk_entry.html', {
        'examination':  examination,
        'student_data': student_data,
        'title':        f'Bulk Entry: {examination.name}',
    })


@login_required
def bulk_lock_grades(request):
    if request.method == 'POST':
        try:
            reason  = request.POST.get('reason', 'Bulk grade lock')
            results = StudentExamResult.objects.filter(id__in=request.POST.getlist('results'))
            count   = sum(1 for r in results if r.lock_grade(locked_by=request.user, reason=reason))
            messages.success(request, f'Locked {count} grade(s) successfully')
        except Exception as e:
            logger.error(f"Error in bulk grade lock: {e}")
            messages.error(request, str(e))
    return redirect('exams:result_list')


@login_required
def bulk_unlock_grades(request):
    if request.method == 'POST':
        try:
            reason  = request.POST.get('reason', 'Bulk grade unlock')
            results = StudentExamResult.objects.filter(id__in=request.POST.getlist('results'))
            count   = sum(
                1 for r in results
                if r.can_unlock_grade(request.user) and r.unlock_grade(unlocked_by=request.user, reason=reason)
            )
            messages.success(request, f'Unlocked {count} grade(s) successfully')
        except Exception as e:
            logger.error(f"Error in bulk grade unlock: {e}")
            messages.error(request, str(e))
    return redirect('exams:result_list')


@login_required
def bulk_verify_results(request):
    if request.method == 'POST':
        try:
            count = StudentExamResult.objects.filter(
                id__in=request.POST.getlist('results')
            ).update(
                is_verified=True,
                verified_by=request.user,
                verification_date=get_school_current_time()
            )
            messages.success(request, f'Verified {count} result(s) successfully')
        except Exception as e:
            logger.error(f"Error in bulk verify: {e}")
            messages.error(request, str(e))
    return redirect('exams:result_list')


@login_required
def bulk_publish_results(request):
    if request.method == 'POST':
        try:
            auto_lock = request.POST.get('auto_lock', 'false') == 'true'
            results   = StudentExamResult.objects.filter(id__in=request.POST.getlist('results'))
            with transaction.atomic():
                for result in results:
                    result.is_published     = True
                    result.publication_date = get_school_current_time()
                    result.save()
                    if auto_lock and not result.is_grade_locked:
                        result.lock_grade(
                            locked_by=request.user,
                            reason='Auto-locked during bulk publication'
                        )
            messages.success(request, f'Published {results.count()} result(s) successfully')
        except Exception as e:
            logger.error(f"Error in bulk publish: {e}")
            messages.error(request, str(e))
    return redirect('exams:result_list')


# =============================================================================
# RESULT PRINT / EXPORT VIEWS
# =============================================================================

@login_required
def student_result_print_detail(request, pk):
    return render(request, 'exams/results/print_detail.html', {
        'result': get_object_or_404(StudentExamResult, pk=pk),
        'print_date': get_school_current_time(),
    })


@login_required
def student_result_print_certificate(request, pk):
    return render(request, 'exams/results/print_certificate.html', {
        'result': get_object_or_404(StudentExamResult, pk=pk),
        'print_date': get_school_current_time(),
    })


@login_required
def student_result_report_card(request, pk):
    result = get_object_or_404(StudentExamResult, pk=pk)
    return render(request, 'exams/results/report_card.html', {
        'result': result,
        'session_results': StudentExamResult.objects.filter(
            student=result.student,
            examination__academic_session=result.examination.academic_session
        ).select_related('examination__subject'),
        'print_date': get_school_current_time(),
    })


@login_required
def student_result_print_view(request):
    return render(request, 'exams/results/print_list.html', {
        'results':    _get_filtered_student_results(request),
        'print_date': get_school_current_time(),
    })


@login_required
def export_results_excel(request):
    results = _get_filtered_student_results(request)
    wb = Workbook()
    ws = wb.active
    ws.title = 'Exam Results'

    hf = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
    ws.append(['#', 'Student', 'Admission No', 'Examination', 'Subject',
               'Score', 'Grade', 'Percentage', 'Status', 'Pass/Fail', 'Published', 'Locked'])
    for cell in ws[1]:
        cell.fill      = hf
        cell.font      = Font(bold=True, color='FFFFFF', size=12)
        cell.alignment = Alignment(horizontal='center', vertical='center')

    for idx, result in enumerate(results, 1):
        ws.append([
            idx, result.student.get_full_name(), result.student.admission_number,
            result.examination.name, result.examination.subject.name,
            float(result.score) if result.score is not None else '',
            result.grade,
            float(result.percentage) if result.percentage is not None else '',
            result.get_status_display(),
            'Pass' if result.is_pass else 'Fail',
            'Yes' if result.is_published else 'No',
            'Yes' if result.is_grade_locked else 'No',
        ])

    for col in ws.columns:
        letter = get_column_letter(col[0].column)
        ws.column_dimensions[letter].width = min(
            max(len(str(c.value or '')) for c in col) + 2, 50
        )

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = (
        f'attachment; filename="exam_results_{datetime.now():%Y%m%d_%H%M%S}.xlsx"'
    )
    wb.save(response)
    return response


# =============================================================================
# ANALYTICS
# =============================================================================

@login_required
def exam_analytics_dashboard(request):
    return render(request, 'exams/analytics/dashboard.html', {
        'current_session': get_active_academic_session(),
    })


@login_required
def examination_analytics(request, examination_pk):
    examination = get_object_or_404(Examination, pk=examination_pk)
    try:
        analytics = examination.analytics
    except ExamAnalytics.DoesNotExist:
        analytics = None
    return render(request, 'exams/analytics/examination.html', {
        'examination': examination, 'analytics': analytics,
    })


@login_required
def generate_exam_analytics(request, examination_pk):
    examination = get_object_or_404(Examination, pk=examination_pk)
    try:
        results = examination.student_results.filter(status='COMPLETED')
        if not results.exists():
            messages.warning(request, 'No completed results to analyse')
            return redirect('exams:examination_detail', pk=examination_pk)

        agg = results.aggregate(
            highest=Max('score'), lowest=Min('score'), average=Avg('score'),
            total=Count('id'), pass_count=Count('id', filter=Q(is_pass=True)),
        )

        grade_dist = {}
        for result in results:
            if result.grade:
                grade_dist[result.grade] = grade_dist.get(result.grade, 0) + 1

        ExamAnalytics.objects.update_or_create(
            examination=examination,
            defaults={
                'total_students':    agg['total'],
                'students_appeared': agg['total'],
                'students_passed':   agg['pass_count'],
                'students_failed':   agg['total'] - agg['pass_count'],
                'highest_score':     agg['highest'],
                'lowest_score':      agg['lowest'],
                'average_score':     agg['average'],
                'pass_rate':         round(agg['pass_count'] / agg['total'] * 100, 2) if agg['total'] else 0,
                'attendance_rate':   100.0,
                'grade_distribution': grade_dist,
            }
        )
        messages.success(request, 'Analytics generated successfully')
    except Exception as e:
        logger.error(f"Error generating analytics: {e}")
        messages.error(request, f'Error generating analytics: {str(e)}')
    return redirect('exams:examination_analytics', examination_pk=examination_pk)


@login_required
def grade_distribution_analysis(request):
    return render(request, 'exams/analytics/grade_distribution.html', {})


@login_required
def performance_trends_analysis(request):
    return render(request, 'exams/analytics/performance_trends.html', {})


@login_required
def subject_performance_analysis(request):
    return render(request, 'exams/analytics/subject_performance.html', {})


# =============================================================================
# REPORTS
# =============================================================================

@login_required
def exam_performance_report(request):
    return render(request, 'exams/reports/exam_performance.html', {})


@login_required
def student_comparison_report(request):
    return render(request, 'exams/reports/student_comparison.html', {})


@login_required
def class_comparison_report(request):
    return render(request, 'exams/reports/class_comparison.html', {})


@login_required
def exam_summary_report(request):
    return render(request, 'exams/reports/exam_summary.html', {})


@login_required
def result_summary_report(request):
    return render(request, 'exams/reports/result_summary.html', {})


@login_required
def grade_sheet_report(request, examination_pk):
    examination = get_object_or_404(Examination, pk=examination_pk)
    return render(request, 'exams/reports/grade_sheet.html', {
        'examination': examination,
        'results': examination.student_results.select_related('student')
                       .order_by('student__first_name', 'student__last_name'),
    })


@login_required
def mark_sheet_report(request, examination_pk):
    examination = get_object_or_404(Examination, pk=examination_pk)
    return render(request, 'exams/reports/mark_sheet.html', {
        'examination': examination,
        'results': examination.student_results.select_related('student')
                       .order_by('student__first_name', 'student__last_name'),
    })


@login_required
def rank_list_report(request, examination_pk):
    examination = get_object_or_404(Examination, pk=examination_pk)
    return render(request, 'exams/reports/rank_list.html', {
        'examination': examination,
        'results': examination.student_results.select_related('student').order_by('-score'),
    })


@login_required
def merit_list_report(request, examination_pk):
    examination = get_object_or_404(Examination, pk=examination_pk)
    return render(request, 'exams/reports/merit_list.html', {
        'examination': examination,
        'results': examination.student_results.filter(is_pass=True)
                       .select_related('student').order_by('-score')[:50],
    })


# =============================================================================
# TIMETABLE
# =============================================================================

@login_required
def exam_timetable(request):
    return render(request, 'exams/timetable/index.html', {
        'sessions': AcademicSession.objects.filter(is_active=True).order_by('-start_date'),
    })


@login_required
def exam_timetable_session(request, session_pk):
    session = get_object_or_404(AcademicSession, pk=session_pk)
    return render(request, 'exams/timetable/session.html', {
        'session': session,
        'examinations': Examination.objects.filter(academic_session=session)
                            .select_related('subject', 'exam_category')
                            .order_by('exam_date', 'start_time'),
    })


@login_required
def exam_timetable_print(request, session_pk):
    session = get_object_or_404(AcademicSession, pk=session_pk)
    return render(request, 'exams/timetable/print.html', {
        'session': session,
        'examinations': Examination.objects.filter(academic_session=session)
                            .select_related('subject', 'exam_category')
                            .order_by('exam_date', 'start_time'),
        'print_date': get_school_current_time(),
    })


@login_required
def exam_timetable_export_pdf(request, session_pk):
    messages.info(request, 'PDF export coming soon')
    return redirect('exams:exam_timetable_session', session_pk=session_pk)


# =============================================================================
# IMPORT / EXPORT TEMPLATES
# =============================================================================

@login_required
def import_results(request):
    if request.method == 'POST':
        messages.info(request, 'Import functionality coming soon')
        return redirect('exams:result_list')
    return render(request, 'exams/import/results.html', {'title': 'Import Results'})


@login_required
def import_examinations(request):
    if request.method == 'POST':
        messages.info(request, 'Import functionality coming soon')
        return redirect('exams:examination_list')
    return render(request, 'exams/import/examinations.html', {'title': 'Import Examinations'})


@login_required
def download_results_template(request):
    wb = Workbook()
    ws = wb.active
    ws.title = 'Results Template'
    ws.append(['Admission Number', 'Examination Code', 'Score', 'Comments'])
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="results_template.xlsx"'
    wb.save(response)
    return response


@login_required
def download_examinations_template(request):
    wb = Workbook()
    ws = wb.active
    ws.title = 'Examinations Template'
    ws.append(['Name', 'Code', 'Subject Code', 'Exam Date', 'Start Time', 'End Time', 'Total Marks'])
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="examinations_template.xlsx"'
    wb.save(response)
    return response


# =============================================================================
# SETTINGS
# =============================================================================

@login_required
def exam_settings(request):
    return render(request, 'exams/settings/exam_settings.html', {})


@login_required
def grading_scale_settings(request):
    return render(request, 'exams/settings/grading_scale.html', {})


@login_required
def grade_locking_settings(request):
    return render(request, 'exams/settings/grade_locking.html', {})


# =============================================================================
# AJAX UTILITY ENDPOINTS
# =============================================================================

@login_required
def ajax_get_grading_system_ranges(request, system_pk):
    try:
        system = get_object_or_404(GradingSystem, pk=system_pk)
        return JsonResponse({'ranges': [
            {
                'id':         r.id,
                'grade':      r.grade,
                'min_score':  float(r.min_score),
                'max_score':  float(r.max_score),
                'gpa_points': float(r.gpa_points) if r.gpa_points else None,
            }
            for r in system.ranges.all().order_by('-min_score')
        ]})
    except Exception as e:
        logger.error(f"Error getting grading ranges: {e}")
        return JsonResponse({'error': str(e)}, status=400)


@login_required
def ajax_get_examinations_for_session(request, session_pk):
    try:
        session = get_object_or_404(AcademicSession, pk=session_pk)
        return JsonResponse({'examinations': [
            {
                'id':        e.id,
                'name':      e.name,
                'code':      e.code,
                'subject':   e.subject.name,
                'exam_date': e.exam_date.strftime('%Y-%m-%d'),
            }
            for e in Examination.objects.filter(academic_session=session).select_related('subject')
        ]})
    except Exception as e:
        logger.error(f"Error getting examinations: {e}")
        return JsonResponse({'error': str(e)}, status=400)


@login_required
def ajax_get_students_for_examination(request, examination_pk):
    try:
        examination = get_object_or_404(Examination, pk=examination_pk)
        return JsonResponse({'students': [
            {
                'id':               r.student.id,
                'name':             r.student.get_full_name(),
                'admission_number': r.student.admission_number,
            }
            for r in examination.registrations.select_related('student')
        ]})
    except Exception as e:
        logger.error(f"Error getting students: {e}")
        return JsonResponse({'error': str(e)}, status=400)


@login_required
def ajax_calculate_grade(request):
    try:
        score          = Decimal(request.GET.get('score', 0))
        grading_system = get_object_or_404(GradingSystem, pk=request.GET.get('grading_system'))
        grade_info     = grading_system.get_grade_for_score(float(score))
        if grade_info:
            return JsonResponse({
                'grade':      grade_info['grade'],
                'gpa_points': grade_info['gpa_points'],
                'is_passing': grade_info['is_passing'],
                'comments':   grade_info['comments'],
            })
        return JsonResponse({'error': 'No grade found for this score'})
    except Exception as e:
        logger.error(f"Error calculating grade: {e}")
        return JsonResponse({'error': str(e)}, status=400)


@login_required
def ajax_check_result_duplicate(request):
    try:
        exists = StudentExamResult.objects.filter(
            student_id=request.GET.get('student'),
            examination_id=request.GET.get('examination')
        ).exists()
        return JsonResponse({'exists': exists})
    except Exception as e:
        logger.error(f"Error checking duplicate: {e}")
        return JsonResponse({'error': str(e)}, status=400)


@login_required
def ajax_get_exam_statistics(request, examination_pk):
    try:
        examination = get_object_or_404(Examination, pk=examination_pk)
        results = examination.student_results.filter(status='COMPLETED')
        agg = results.aggregate(
            total=Count('id'), highest=Max('score'), lowest=Min('score'),
            average=Avg('score'), pass_count=Count('id', filter=Q(is_pass=True)),
        )
        total = agg['total'] or 0
        return JsonResponse({
            'total_results':  total,
            'highest_score':  float(agg['highest']) if agg['highest'] else 0,
            'lowest_score':   float(agg['lowest'])  if agg['lowest']  else 0,
            'average_score':  round(float(agg['average']), 2) if agg['average'] else 0,
            'pass_count':     agg['pass_count'],
            'pass_rate':      round(agg['pass_count'] / total * 100, 2) if total else 0,
        })
    except Exception as e:
        logger.error(f"Error getting exam statistics: {e}")
        return JsonResponse({'error': str(e)}, status=400)


@login_required
def ajax_validate_grade_unlock(request, result_pk):
    try:
        result = get_object_or_404(StudentExamResult, pk=result_pk)
        return JsonResponse({
            'can_unlock': result.can_unlock_grade(request.user),
            'is_locked':  result.is_grade_locked,
            'locked_by':  result.grade_locked_by.get_full_name() if result.grade_locked_by else None,
            'locked_at':  result.grade_locked_at.strftime('%Y-%m-%d %H:%M') if result.grade_locked_at else None,
        })
    except Exception as e:
        logger.error(f"Error validating unlock: {e}")
        return JsonResponse({'error': str(e)}, status=400)