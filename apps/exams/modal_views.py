"""
exams/modal_views.py

Modal views for the exams app.
Returns HTML partials consumed by HTMX modal containers.

Rule: this module only renders confirmation / preview / action-config modals.
      Full create/edit forms live in views.py as dedicated pages.

Results flow (2 pages + 1 modal):
  Page 1  /exams/results/               results_by_class
  Page 2  /exams/results/<class_pk>/    class_marks   (category tabs + read-only grid)
  Modal   student_marks_edit_modal      score entry per student, per category
"""

import logging
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Avg, Count, Max, Min, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render

from academics.models import AcademicSession, Class, Subject
from core.utils import get_active_academic_session, get_school_today
from students.models import Student

from .models import (
    ClassGradingSystem,
    ExamCategory,
    Examination,
    GradingRange,
    GradingSystem,
    StudentExamResult,
)

logger = logging.getLogger(__name__)


# =============================================================================
# EXAM CATEGORY MODALS
# =============================================================================

@login_required
def exam_category_delete_modal(request, pk):
    category   = get_object_or_404(ExamCategory, pk=pk)
    exam_count = category.examinations.count()
    warnings   = [f'Has {exam_count} examination(s)'] if exam_count else []
    return render(request, 'exams/categories/modals/delete_category.html', {
        'category':   category,
        'can_delete': exam_count == 0,
        'warnings':   warnings,
    })


@login_required
def exam_category_toggle_active_modal(request, pk):
    category = get_object_or_404(ExamCategory, pk=pk)
    return render(request, 'exams/categories/modals/toggle_active.html', {
        'category': category,
        'action':   'deactivate' if category.is_active else 'activate',
    })


@login_required
def exam_category_quick_view_modal(request, pk):
    category = get_object_or_404(ExamCategory, pk=pk)
    today    = get_school_today()
    return render(request, 'exams/categories/modals/quick_view.html', {
        'category':        category,
        'total_exams':     category.examinations.count(),
        'active_exams':    category.examinations.filter(status='ONGOING').count(),
        'completed_exams': category.examinations.filter(status='COMPLETED').count(),
        'upcoming_exams':  category.examinations.filter(
            exam_date__gte=today, status__in=['PLANNED', 'SCHEDULED']
        ).count(),
    })


# =============================================================================
# GRADING SYSTEM MODALS
# =============================================================================

@login_required
def grading_system_delete_modal(request, pk):
    system           = get_object_or_404(GradingSystem, pk=pk)
    assignment_count = system.class_assignments.count()
    exam_count       = system.examinations.count()

    warnings = []
    if system.is_default:
        warnings.append('This is the default grading system')
    if assignment_count:
        warnings.append(f'Has {assignment_count} class assignment(s)')
    if exam_count:
        warnings.append(f'Used in {exam_count} examination(s)')

    return render(request, 'exams/grading_systems/modals/delete_system.html', {
        'system':     system,
        'can_delete': not warnings,
        'warnings':   warnings,
    })


@login_required
def grading_system_toggle_active_modal(request, pk):
    system = get_object_or_404(GradingSystem, pk=pk)
    return render(request, 'exams/grading_systems/modals/toggle_active.html', {
        'system': system,
        'action': 'deactivate' if system.is_active else 'activate',
    })


@login_required
def grading_system_set_default_modal(request, pk):
    system = get_object_or_404(GradingSystem, pk=pk)
    return render(request, 'exams/grading_systems/modals/set_default.html', {
        'system':          system,
        'current_default': GradingSystem.objects.filter(is_default=True).first(),
    })


@login_required
def grading_system_quick_view_modal(request, pk):
    system = get_object_or_404(GradingSystem, pk=pk)
    return render(request, 'exams/grading_systems/modals/quick_view.html', {
        'system':       system,
        'ranges':       system.ranges.all().order_by('-min_score'),
        'assignments':  system.class_assignments.filter(is_active=True).count(),
        'examinations': system.examinations.count(),
    })


# =============================================================================
# GRADING RANGE MODALS
# =============================================================================

@login_required
def grading_range_delete_modal(request, pk):
    range_obj = get_object_or_404(GradingRange, pk=pk)
    is_last   = range_obj.grading_system.ranges.count() <= 1
    warnings  = ['Cannot delete the last grading range'] if is_last else []
    return render(request, 'exams/grading_ranges/modals/delete_range.html', {
        'range':      range_obj,
        'can_delete': not is_last,
        'warnings':   warnings,
    })


@login_required
def grading_range_quick_view_modal(request, pk):
    return render(request, 'exams/grading_ranges/modals/quick_view.html', {
        'range': get_object_or_404(GradingRange, pk=pk),
    })


# =============================================================================
# CLASS GRADING SYSTEM MODALS
# =============================================================================

@login_required
def class_grading_system_delete_modal(request, pk):
    return render(request, 'exams/class_grading_systems/modals/delete_assignment.html', {
        'assignment': get_object_or_404(ClassGradingSystem, pk=pk),
    })


@login_required
def class_grading_system_toggle_active_modal(request, pk):
    assignment = get_object_or_404(ClassGradingSystem, pk=pk)
    return render(request, 'exams/class_grading_systems/modals/toggle_active.html', {
        'assignment': assignment,
        'action':     'deactivate' if assignment.is_active else 'activate',
    })


@login_required
def class_grading_system_quick_view_modal(request, pk):
    assignment = get_object_or_404(
        ClassGradingSystem.objects.select_related(
            'class_instance', 'grading_system', 'academic_session', 'subject'
        ),
        pk=pk,
    )
    return render(request, 'exams/class_grading_systems/modals/quick_view.html', {
        'assignment': assignment,
        'ranges':     assignment.grading_system.ranges.all().order_by('-min_score'),
    })


@login_required
def bulk_class_grading_system_assign_modal(request):
    return render(request, 'exams/class_grading_systems/modals/bulk_assign.html', {
        'grading_systems': GradingSystem.objects.filter(is_active=True).order_by('name'),
        'sessions':        AcademicSession.objects.filter(is_active=True).order_by('-start_date'),
        'classes':         Class.objects.filter(is_active=True)
                               .select_related('academic_level')
                               .order_by('academic_level__order', 'section'),
        'subjects':        Subject.objects.filter(is_active=True).order_by('name'),
    })


# =============================================================================
# EXAMINATION MODALS
# =============================================================================

@login_required
def examination_delete_modal(request, pk):
    examination  = get_object_or_404(Examination, pk=pk)
    result_count = examination.student_results.count()
    blocked      = examination.status in ('ONGOING', 'COMPLETED')

    warnings = []
    if blocked:
        warnings.append(f'Examination is {examination.get_status_display()}')
    if result_count:
        warnings.append(f'Has {result_count} result(s) — these will also be deleted')

    return render(request, 'exams/examinations/modals/delete_examination.html', {
        'examination': examination,
        'can_delete':  not blocked and result_count == 0,
        'warnings':    warnings,
    })


@login_required
def examination_update_status_modal(request, pk):
    examination = get_object_or_404(Examination, pk=pk)

    # Valid forward transitions per status
    _TRANSITIONS = {
        'PLANNED':   ['SCHEDULED', 'CANCELLED'],
        'SCHEDULED': ['ONGOING', 'POSTPONED', 'CANCELLED'],
        'ONGOING':   ['COMPLETED', 'SUSPENDED'],
        'COMPLETED': ['ONGOING'],
    }
    available = _TRANSITIONS.get(examination.status, ['PLANNED', 'SCHEDULED'])

    return render(request, 'exams/examinations/modals/update_status.html', {
        'examination':        examination,
        'available_statuses': available,
        'status_choices':     Examination.EXAM_STATUS_CHOICES,
    })


@login_required
def examination_publish_results_modal(request, pk):
    examination = get_object_or_404(Examination, pk=pk)
    results     = examination.student_results
    total       = results.count()
    completed   = results.filter(status__in=['COMPLETED', 'SUBMITTED']).count()
    published   = results.filter(is_published=True).count()
    locked      = results.filter(is_grade_locked=True).count()

    warnings    = []
    can_publish = True

    if examination.results_published:
        warnings.append('Results are already published')
        can_publish = False
    if total == 0:
        warnings.append('No results to publish')
        can_publish = False
    elif completed < total:
        warnings.append(f'Only {completed} of {total} results are completed')

    return render(request, 'exams/examinations/modals/publish_results.html', {
        'examination':       examination,
        'total_results':     total,
        'completed_results': completed,
        'published_results': published,
        'locked_results':    locked,
        'unlocked_results':  total - locked,
        'warnings':          warnings,
        'can_publish':       can_publish,
    })


@login_required
def examination_unpublish_results_modal(request, pk):
    examination = get_object_or_404(Examination, pk=pk)
    results     = examination.student_results
    total       = results.count()
    published   = results.filter(is_published=True).count()
    locked      = results.filter(is_grade_locked=True).count()

    warnings = []
    if locked:
        warnings.append(
            f'{locked} grade(s) are locked — these will remain locked after unpublishing'
        )

    return render(request, 'exams/examinations/modals/unpublish_results.html', {
        'examination':       examination,
        'total_results':     total,
        'published_results': published,
        'locked_results':    locked,
        'warnings':          warnings,
    })


@login_required
def examination_quick_view_modal(request, pk):
    examination = get_object_or_404(
        Examination.objects.select_related(
            'subject', 'academic_session', 'exam_category', 'grading_system', 'classroom'
        ).prefetch_related('target_classes', 'invigilators'),
        pk=pk,
    )

    results       = examination.student_results.select_related('student').order_by('-score')
    total_results = results.count()
    agg           = results.aggregate(
        highest    = Max('score'),
        lowest     = Min('score'),
        average    = Avg('score'),
        pass_count = Count('id', filter=Q(is_pass=True)),
    )
    pass_count = agg['pass_count'] or 0

    return render(request, 'exams/examinations/modals/overview.html', {
        'examination': examination,
        'stats': {
            'total_results':   total_results,
            'highest_score':   agg['highest'],
            'lowest_score':    agg['lowest'],
            'average_score':   round(float(agg['average']), 2) if agg['average'] else 0,
            'pass_count':      pass_count,
            'pass_rate':       round(pass_count / total_results * 100, 2) if total_results else 0,
            'published_count': results.filter(is_published=True).count(),
            'locked_count':    results.filter(is_grade_locked=True).count(),
        },
    })


@login_required
def examination_statistics_modal(request, pk):
    examination = get_object_or_404(Examination, pk=pk)
    results     = examination.student_results.filter(status='COMPLETED')

    stats = results.aggregate(
        total      = Count('id'),
        highest    = Max('score'),
        lowest     = Min('score'),
        average    = Avg('score'),
        pass_count = Count('id', filter=Q(is_pass=True)),
    )

    grade_distribution = dict(
        results.exclude(grade='')
               .values('grade')
               .annotate(count=Count('id'))
               .values_list('grade', 'count')
    )

    return render(request, 'exams/examinations/modals/statistics.html', {
        'examination':        examination,
        'stats':              stats,
        'grade_distribution': grade_distribution,
    })


# =============================================================================
# RESULT MODALS
# (accessed from result_detail or the class_marks grid)
# =============================================================================

@login_required
def student_marks_edit_modal(request, class_pk, category_pk, student_pk):
    """
    Score-entry modal for a single student in one exam category.

    GET  → render the form with existing scores pre-filled.
    POST → validate and save scores; on success return an HTMX trigger that
           closes the modal and refreshes the student's row in the grid.

    Scores are saved individually via StudentExamResult.  If any score fails
    validation the entire batch is rolled back and the form is re-rendered
    with all errors listed.
    """
    class_instance = get_object_or_404(Class, pk=class_pk)
    category       = get_object_or_404(ExamCategory, pk=category_pk)
    student        = get_object_or_404(Student, pk=student_pk)

    session_id = request.GET.get('session') or request.POST.get('session')
    session    = (
        get_object_or_404(AcademicSession, pk=session_id)
        if session_id
        else class_instance.academic_session
    )

    examinations = Examination.objects.filter(
        target_classes   = class_instance,
        exam_category    = category,
        academic_session = session,
    ).select_related('subject').order_by('subject__name')

    # Pre-load existing results to avoid per-exam queries
    existing = {
        r.examination_id: r
        for r in StudentExamResult.objects.filter(
            examination__in=examinations,
            student=student,
        )
    }

    if request.method == 'POST':
        errors = []

        try:
            with transaction.atomic():
                for exam in examinations:
                    raw = request.POST.get(f'score_{exam.pk}', '').strip()
                    if not raw:
                        continue

                    try:
                        score = Decimal(raw)
                    except InvalidOperation:
                        errors.append(f'Invalid score for {exam.subject.name}: "{raw}"')
                        continue

                    if not (0 <= score <= exam.total_marks):
                        errors.append(
                            f'{exam.subject.name}: score must be between 0 and {exam.total_marks}'
                        )
                        continue

                    result = existing.get(exam.pk)
                    if result:
                        if result.is_grade_locked:
                            errors.append(f'{exam.subject.name}: grade is locked')
                            continue
                        result.score  = score
                        result.status = 'COMPLETED'
                        result.save()
                    else:
                        StudentExamResult.objects.create(
                            student     = student,
                            examination = exam,
                            score       = score,
                            status      = 'COMPLETED',
                        )

                # Raise inside the atomic block to roll back any partial saves
                if errors:
                    raise ValidationError(errors)

        except ValidationError as ve:
            return render(request, 'exams/results/modals/student_marks_edit.html', {
                'class_instance': class_instance,
                'category':       category,
                'session':        session,
                'student':        student,
                'examinations':   examinations,
                'existing':       existing,
                'errors':         ve.messages,
            })
        except Exception as e:
            logger.error(
                'Error saving marks in student_marks_edit_modal '
                '(class=%s category=%s student=%s): %s',
                class_pk, category_pk, student_pk, e, exc_info=True,
            )
            return render(request, 'exams/results/modals/student_marks_edit.html', {
                'class_instance': class_instance,
                'category':       category,
                'session':        session,
                'student':        student,
                'examinations':   examinations,
                'existing':       existing,
                'errors':         [str(e)],
            })

        # Success — close modal and trigger a grid refresh
        response = HttpResponse()
        response['HX-Trigger'] = 'closeModal, refreshGrid'
        return response

    return render(request, 'exams/results/modals/student_marks_edit.html', {
        'class_instance': class_instance,
        'category':       category,
        'session':        session,
        'student':        student,
        'examinations':   examinations,
        'existing':       existing,
        'errors':         [],
    })


@login_required
def student_result_delete_modal(request, pk):
    result   = get_object_or_404(StudentExamResult, pk=pk)
    warnings = []
    if result.is_grade_locked:
        warnings.append('Grade is locked')
    if result.is_published:
        warnings.append('Result is published')
    if result.is_verified:
        warnings.append('Result has been verified')
    return render(request, 'exams/results/modals/delete_result.html', {
        'result':     result,
        'can_delete': not result.is_grade_locked and not result.is_published,
        'warnings':   warnings,
    })


@login_required
def lock_grade_modal(request, pk):
    """
    Confirmation modal before locking a grade.
    The actual lock action is handled by ``exams:lock_grade`` (POST).
    """
    result   = get_object_or_404(StudentExamResult, pk=pk)
    can_lock = request.user.has_perm('exams.lock_grades')

    warnings = []
    if result.is_grade_locked:
        warnings.append('Grade is already locked')
        can_lock = False
    elif not result.grade:
        warnings.append('No grade assigned yet — enter a score first')
        can_lock = False
    elif result.score is None:
        warnings.append('No score entered yet')
        can_lock = False

    return render(request, 'exams/results/modals/lock_grade.html', {
        'result':   result,
        'warnings': warnings,
        'can_lock': can_lock,
    })


@login_required
def unlock_grade_modal(request, pk):
    """
    Confirmation modal before unlocking a grade.
    The actual unlock action is handled by ``exams:unlock_grade`` (POST).
    """
    result     = get_object_or_404(StudentExamResult, pk=pk)
    can_unlock = result.can_unlock_grade(request.user)

    warnings = []
    if not result.is_grade_locked:
        warnings.append('Grade is not locked')
        can_unlock = False
    elif not can_unlock:
        warnings.append("You don't have permission to unlock this grade, "
                        "or the 30-day unlock window has expired")

    lock_info = None
    if result.is_grade_locked:
        lock_info = {
            'locked_by': (
                result.grade_locked_by.get_full_name()
                if result.grade_locked_by else 'Unknown'
            ),
            'locked_at': result.grade_locked_at,
            'reason':    result.lock_reason,
        }

    return render(request, 'exams/results/modals/unlock_grade.html', {
        'result':     result,
        'warnings':   warnings,
        'can_unlock': can_unlock,
        'lock_info':  lock_info,
    })


@login_required
def grade_history_modal(request, pk):
    """Full grade lock / unlock audit trail for a single result."""
    result = get_object_or_404(StudentExamResult, pk=pk)
    return render(request, 'exams/results/modals/grade_history.html', {
        'result':        result,
        'grade_history': result.get_grade_history() if result.is_grade_locked else None,
    })


@login_required
def student_result_quick_view_modal(request, pk):
    """Quick summary card for a result — used in the class_marks grid."""
    result = get_object_or_404(
        StudentExamResult.objects.select_related(
            'student',
            'examination__subject',
            'examination__academic_session',
            'examination__exam_category',
        ),
        pk=pk,
    )
    return render(request, 'exams/results/modals/quick_view.html', {
        'result':      result,
        'performance': result.get_performance_summary(),
    })


# =============================================================================
# STUDENT RESULT HISTORY MODALS
# (accessed from student profile or result_detail)
# =============================================================================

@login_required
def student_exam_history_modal(request, student_pk):
    """All results for a student across all sessions."""
    student = get_object_or_404(Student, pk=student_pk)
    return render(request, 'exams/students/modals/exam_history.html', {
        'student': student,
        'results': StudentExamResult.objects.filter(student=student)
                       .select_related(
                           'examination__subject',
                           'examination__academic_session',
                           'examination__exam_category',
                       )
                       .order_by('-examination__exam_date'),
    })


@login_required
def student_results_summary_modal(request, student_pk):
    """Current-session result summary for a student."""
    student         = get_object_or_404(Student, pk=student_pk)
    current_session = get_active_academic_session()

    if current_session:
        results = StudentExamResult.objects.filter(
            student=student,
            examination__academic_session=current_session,
            status='COMPLETED',
        ).select_related('examination__subject', 'examination__exam_category')

        stats = results.aggregate(
            total      = Count('id'),
            average    = Avg('score'),
            pass_count = Count('id', filter=Q(is_pass=True)),
        )
    else:
        results = StudentExamResult.objects.none()
        stats   = {'total': 0, 'average': None, 'pass_count': 0}

    return render(request, 'exams/students/modals/results_summary.html', {
        'student':         student,
        'current_session': current_session,
        'results':         results,
        'stats':           stats,
    })


# =============================================================================
# REPORT MODALS
# (scoped to examination or class — there is no global result list)
# =============================================================================

@login_required
def grade_sheet_report_modal(request):
    return render(request, 'exams/reports/modals/grade_sheet.html', {
        'examinations': Examination.objects.filter(status='COMPLETED')
                            .select_related('subject', 'academic_session', 'exam_category')
                            .order_by('-exam_date'),
    })


@login_required
def mark_sheet_report_modal(request):
    return render(request, 'exams/reports/modals/mark_sheet.html', {
        'examinations': Examination.objects.filter(status='COMPLETED')
                            .select_related('subject', 'academic_session', 'exam_category')
                            .order_by('-exam_date'),
        'classes':      Class.objects.filter(is_active=True)
                            .select_related('academic_level')
                            .order_by('academic_level__order', 'section'),
    })


@login_required
def rank_list_report_modal(request):
    return render(request, 'exams/reports/modals/rank_list.html', {
        'examinations': Examination.objects.filter(status='COMPLETED')
                            .select_related('subject', 'academic_session', 'exam_category')
                            .order_by('-exam_date'),
        'classes':      Class.objects.filter(is_active=True)
                            .select_related('academic_level')
                            .order_by('academic_level__order', 'section'),
    })


@login_required
def merit_list_report_modal(request):
    return render(request, 'exams/reports/modals/merit_list.html', {
        'examinations': Examination.objects.filter(status='COMPLETED')
                            .select_related('subject', 'academic_session', 'exam_category')
                            .order_by('-exam_date'),
    })


# =============================================================================
# TIMETABLE MODALS
# =============================================================================

@login_required
def generate_timetable_modal(request):
    return render(request, 'exams/timetable/modals/generate.html', {
        'sessions':   AcademicSession.objects.filter(is_active=True).order_by('-start_date'),
        'categories': ExamCategory.objects.filter(is_active=True).order_by('name'),
    })


@login_required
def exam_timetable_modal(request, session_pk):
    session = get_object_or_404(AcademicSession, pk=session_pk)
    return render(request, 'exams/timetable/modals/view.html', {
        'session':      session,
        'examinations': Examination.objects.filter(academic_session=session)
                            .select_related('subject', 'exam_category')
                            .order_by('exam_date', 'start_time'),
    })


# =============================================================================
# IMPORT / EXPORT MODALS
# =============================================================================

@login_required
def import_results_modal(request):
    return render(request, 'exams/import/modals/import_results.html', {
        'examinations': Examination.objects.filter(
            status__in=['ONGOING', 'COMPLETED']
        ).select_related('subject', 'academic_session').order_by('-exam_date'),
    })


@login_required
def import_examinations_modal(request):
    return render(request, 'exams/import/modals/import_examinations.html', {
        'sessions':   AcademicSession.objects.filter(is_active=True).order_by('-start_date'),
        'categories': ExamCategory.objects.filter(is_active=True).order_by('name'),
    })


@login_required
def export_options_modal(request, resource_type):
    _VALID_TYPES = frozenset({
        'categories',
        'grading_systems',
        'class_grading_systems',
        'examinations',
        'results',
    })
    if resource_type not in _VALID_TYPES:
        logger.warning(
            'export_options_modal: invalid resource_type %r requested', resource_type
        )
        resource_type = 'results'
    return render(request, 'exams/export/modals/export_options.html', {
        'resource_type': resource_type,
    })


# =============================================================================
# SETTINGS MODALS
# =============================================================================

@login_required
def exam_settings_modal(request):
    return render(request, 'exams/settings/modals/exam_settings.html', {})


@login_required
def grading_scale_settings_modal(request):
    return render(request, 'exams/settings/modals/grading_scale.html', {
        'grading_systems': GradingSystem.objects.filter(is_active=True).order_by('name'),
    })


@login_required
def grade_locking_settings_modal(request):
    return render(request, 'exams/settings/modals/grade_locking.html', {})


# =============================================================================
# UTILITY MODALS
# =============================================================================

_ALLOWED_HISTORY_CONTENT_TYPES = frozenset({
    'examination',
    'examcategory',
    'gradingsystem',
    'gradingrange',
    'classgradingsystem',
    'studentexamresult',
})


@login_required
def history_modal(request, content_type, object_id):
    """
    Generic audit-history modal.
    ``content_type`` is validated against an allowlist to prevent
    arbitrary model enumeration.
    """
    if content_type not in _ALLOWED_HISTORY_CONTENT_TYPES:
        raise PermissionDenied(f"History not available for '{content_type}'")
    return render(request, 'exams/modals/history.html', {
        'content_type': content_type,
        'object_id':    object_id,
    })


@login_required
def confirm_action_modal(request):
    """
    Generic low-stakes confirmation modal.
    Accepts ``?action=`` and ``?message=`` query params.
    Prefer purpose-specific modals for anything that needs business-logic
    warnings (can_delete, locked grades, etc.).
    """
    return render(request, 'exams/modals/confirm_action.html', {
        'action':  request.GET.get('action', 'perform this action'),
        'message': request.GET.get('message', 'Are you sure you want to proceed?'),
    })