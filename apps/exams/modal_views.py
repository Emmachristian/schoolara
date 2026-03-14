"""
exams/modal_views.py

Modal views for the exams app.
Returns HTML partials consumed by HTMX modal containers.

Rule: this module only renders confirmation/preview/action-config modals.
      Full create/edit forms live in views.py as dedicated pages.
"""

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count, Avg, Max, Min
from django.core.exceptions import PermissionDenied
from decimal import Decimal

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
from students.models import Student
from academics.models import Class, Subject, AcademicSession
from core.utils import get_school_today, get_school_current_time, get_active_academic_session

import logging
logger = logging.getLogger(__name__)


# =============================================================================
# EXAM CATEGORY MODALS
# =============================================================================

@login_required
def exam_category_delete_modal(request, pk):
    category  = get_object_or_404(ExamCategory, pk=pk)
    exam_count = category.examinations.count()
    warnings  = [f'Has {exam_count} examination(s)'] if exam_count else []
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
    range_obj  = get_object_or_404(GradingRange, pk=pk)
    is_last    = range_obj.grading_system.ranges.count() <= 1
    warnings   = ['Cannot delete the last grading range'] if is_last else []
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
        ), pk=pk
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
        'classes':         Class.objects.filter(is_active=True).select_related('academic_level')
                               .order_by('academic_level__order', 'section'),
        'subjects':        Subject.objects.filter(is_active=True).order_by('name'),
    })


# =============================================================================
# EXAMINATION MODALS
# =============================================================================

@login_required
def examination_delete_modal(request, pk):
    examination      = get_object_or_404(Examination, pk=pk)
    result_count     = examination.student_results.count()
    reg_count        = examination.registrations.count()
    blocked_by_status = examination.status in ['ONGOING', 'COMPLETED']

    warnings = []
    if blocked_by_status:
        warnings.append(f'Examination is {examination.get_status_display()}')
    if result_count:
        warnings.append(f'Has {result_count} result(s)')
    if reg_count:
        warnings.append(f'Has {reg_count} registration(s) — these will also be deleted')

    return render(request, 'exams/examinations/modals/delete_examination.html', {
        'examination': examination,
        'can_delete':  not blocked_by_status and result_count == 0,
        'warnings':    warnings,
    })


@login_required
def examination_toggle_active_modal(request, pk):
    examination = get_object_or_404(Examination, pk=pk)
    if examination.status == 'CANCELLED':
        action, new_status = 'reactivate', 'PLANNED'
    else:
        action, new_status = 'cancel', 'CANCELLED'
    return render(request, 'exams/examinations/modals/toggle_active.html', {
        'examination': examination,
        'action':      action,
        'new_status':  new_status,
    })


@login_required
def examination_update_status_modal(request, pk):
    examination    = get_object_or_404(Examination, pk=pk)
    current_status = examination.status

    transitions = {
        'PLANNED':    ['SCHEDULED', 'CANCELLED'],
        'SCHEDULED':  ['ONGOING', 'POSTPONED', 'CANCELLED'],
        'ONGOING':    ['COMPLETED', 'SUSPENDED'],
        'COMPLETED':  ['ONGOING'],
    }
    available = transitions.get(current_status, ['PLANNED', 'SCHEDULED'])

    return render(request, 'exams/examinations/modals/update_status.html', {
        'examination':        examination,
        'available_statuses': available,
        'status_choices':     Examination.EXAM_STATUS_CHOICES,
    })


@login_required
def examination_publish_results_modal(request, pk):
    examination      = get_object_or_404(Examination, pk=pk)
    total_results    = examination.student_results.count()
    completed        = examination.student_results.filter(status__in=['COMPLETED', 'SUBMITTED']).count()
    published        = examination.student_results.filter(is_published=True).count()
    locked           = examination.student_results.filter(is_grade_locked=True).count()

    warnings   = []
    can_publish = True
    if examination.results_published:
        warnings.append('Results are already published')
    if total_results == 0:
        can_publish = False
        warnings.append('No results to publish')
    if completed < total_results:
        warnings.append(f'Only {completed} of {total_results} results are completed')

    return render(request, 'exams/examinations/modals/publish_results.html', {
        'examination':      examination,
        'total_results':    total_results,
        'completed_results': completed,
        'published_results': published,
        'locked_results':   locked,
        'unlocked_results': total_results - locked,
        'warnings':         warnings,
        'can_publish':      can_publish,
    })


@login_required
def examination_unpublish_results_modal(request, pk):
    examination   = get_object_or_404(Examination, pk=pk)
    total_results = examination.student_results.count()
    published     = examination.student_results.filter(is_published=True).count()
    locked        = examination.student_results.filter(is_grade_locked=True).count()

    warnings = []
    if locked:
        warnings.append(f'{locked} grade(s) are locked — these will remain locked after unpublishing')

    return render(request, 'exams/examinations/modals/unpublish_results.html', {
        'examination':      examination,
        'total_results':    total_results,
        'published_results': published,
        'locked_results':   locked,
        'warnings':         warnings,
    })


@login_required
def examination_quick_view_modal(request, pk):
    examination = get_object_or_404(
        Examination.objects.select_related(
            'subject', 'exam_category', 'academic_session', 'grading_system'
        ), pk=pk
    )
    agg = examination.student_results.filter(status='COMPLETED').aggregate(
        highest=Max('score'), lowest=Min('score'), average=Avg('score'),
    )
    return render(request, 'exams/examinations/modals/quick_view.html', {
        'examination':       examination,
        'registration_count': examination.registrations.count(),
        'result_count':      examination.student_results.count(),
        'published_count':   examination.student_results.filter(is_published=True).count(),
        'highest_score':     agg['highest'],
        'lowest_score':      agg['lowest'],
        'average_score':     agg['average'],
    })


@login_required
def examination_statistics_modal(request, examination_pk):
    examination = get_object_or_404(Examination, pk=examination_pk)
    results     = examination.student_results.filter(status='COMPLETED')

    stats = results.aggregate(
        total=Count('id'), highest=Max('score'), lowest=Min('score'),
        average=Avg('score'), pass_count=Count('id', filter=Q(is_pass=True)),
    )

    grade_distribution = {}
    for result in results:
        if result.grade:
            grade_distribution[result.grade] = grade_distribution.get(result.grade, 0) + 1

    return render(request, 'exams/examinations/modals/statistics.html', {
        'examination':       examination,
        'stats':             stats,
        'grade_distribution': grade_distribution,
    })


# =============================================================================
# EXAM REGISTRATION MODALS
# =============================================================================

@login_required
def exam_registration_delete_modal(request, pk):
    registration = get_object_or_404(ExamRegistration, pk=pk)
    warnings     = []
    if registration.status == 'CONFIRMED':
        warnings.append('Registration is confirmed')
    if registration.payment_verified:
        warnings.append('Payment has been verified')
    return render(request, 'exams/registrations/modals/delete_registration.html', {
        'registration': registration,
        'can_delete':   True,
        'warnings':     warnings,
    })


@login_required
def exam_registration_update_status_modal(request, pk):
    return render(request, 'exams/registrations/modals/update_status.html', {
        'registration':   get_object_or_404(ExamRegistration, pk=pk),
        'status_choices': ExamRegistration.REGISTRATION_STATUS_CHOICES,
    })


@login_required
def exam_registration_verify_payment_modal(request, pk):
    registration = get_object_or_404(ExamRegistration, pk=pk)
    warnings     = ['Payment is already verified'] if registration.payment_verified else []
    return render(request, 'exams/registrations/modals/verify_payment.html', {
        'registration': registration,
        'warnings':     warnings,
    })


@login_required
def exam_registration_quick_view_modal(request, pk):
    return render(request, 'exams/registrations/modals/quick_view.html', {
        'registration': get_object_or_404(
            ExamRegistration.objects.select_related(
                'student', 'examination__subject', 'examination__academic_session'
            ), pk=pk
        ),
    })


@login_required
def bulk_exam_registration_modal(request):
    return render(request, 'exams/registrations/modals/bulk_create.html', {
        'examinations': Examination.objects.filter(
            status__in=['PLANNED', 'SCHEDULED']
        ).select_related('subject', 'academic_session', 'exam_category').order_by('-exam_date'),
        'students': Student.objects.filter(enrollment_status='ACTIVE')
                        .order_by('first_name', 'last_name'),
        'classes':  Class.objects.filter(is_active=True).select_related('academic_level')
                        .order_by('academic_level__order', 'section'),
    })


# =============================================================================
# STUDENT RESULT MODALS
# =============================================================================

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
def student_result_verify_modal(request, pk):
    result   = get_object_or_404(StudentExamResult, pk=pk)
    warnings = []
    if result.is_verified:
        warnings.append('Result is already verified')
    if not result.score:
        warnings.append('No score entered yet')
    return render(request, 'exams/results/modals/verify_result.html', {
        'result': result, 'warnings': warnings,
    })


@login_required
def student_result_moderate_modal(request, pk):
    result   = get_object_or_404(StudentExamResult, pk=pk)
    warnings = []
    if result.is_moderated:
        warnings.append(f'Result already moderated (Score: {result.moderated_score})')
    return render(request, 'exams/results/modals/moderate_result.html', {
        'result': result, 'warnings': warnings,
    })


@login_required
def lock_grade_modal(request, pk):
    result   = get_object_or_404(StudentExamResult, pk=pk)
    # Permission name matches model Meta: 'lock_grades' (no 'can_' prefix)
    can_lock = request.user.has_perm('exams.lock_grades')
    warnings = []
    if result.is_grade_locked:
        warnings.append('Grade is already locked')
        can_lock = False
    if not result.grade:
        warnings.append('No grade assigned yet')
        can_lock = False
    if result.score is None:
        warnings.append('No score entered yet')
        can_lock = False
    return render(request, 'exams/results/modals/lock_grade.html', {
        'result': result, 'warnings': warnings, 'can_lock': can_lock,
    })


@login_required
def unlock_grade_modal(request, pk):
    result     = get_object_or_404(StudentExamResult, pk=pk)
    can_unlock = result.can_unlock_grade(request.user)
    warnings   = []
    if not result.is_grade_locked:
        warnings.append('Grade is not locked')
        can_unlock = False
    if not can_unlock:
        warnings.append("You don't have permission to unlock this grade")

    lock_info = None
    if result.is_grade_locked:
        lock_info = {
            'locked_by': result.grade_locked_by.get_full_name() if result.grade_locked_by else 'Unknown',
            'locked_at': result.grade_locked_at,
            'reason':    result.lock_reason,
        }
    return render(request, 'exams/results/modals/unlock_grade.html', {
        'result': result, 'warnings': warnings,
        'can_unlock': can_unlock, 'lock_info': lock_info,
    })


@login_required
def student_result_quick_view_modal(request, pk):
    result = get_object_or_404(
        StudentExamResult.objects.select_related(
            'student', 'examination__subject', 'examination__academic_session'
        ), pk=pk
    )
    return render(request, 'exams/results/modals/quick_view.html', {
        'result':      result,
        'performance': result.get_performance_summary(),
    })


@login_required
def grade_history_modal(request, pk):
    result = get_object_or_404(StudentExamResult, pk=pk)
    return render(request, 'exams/results/modals/grade_history.html', {
        'result':        result,
        'grade_history': result.get_grade_history() if result.is_grade_locked else None,
    })


# =============================================================================
# BULK RESULT OPERATION MODALS
# =============================================================================

@login_required
def bulk_result_entry_modal(request):
    return render(request, 'exams/results/modals/bulk_entry.html', {
        'examinations': Examination.objects.filter(
            status__in=['ONGOING', 'COMPLETED']
        ).select_related('subject', 'academic_session').order_by('-exam_date'),
        'classes': Class.objects.filter(is_active=True).select_related('academic_level')
                       .order_by('academic_level__order', 'section'),
    })


@login_required
def bulk_lock_grades_modal(request):
    # Permission name matches model Meta: 'lock_grades'
    if not request.user.has_perm('exams.lock_grades'):
        raise PermissionDenied("You don't have permission to lock grades")

    exam_data = []
    for exam in Examination.objects.filter(
        status='COMPLETED', results_published=True
    ).select_related('subject', 'academic_session').order_by('-exam_date'):
        lockable = exam.student_results.filter(
            is_grade_locked=False, is_published=True,
            score__isnull=False, grade__isnull=False
        ).exclude(grade='').count()
        if lockable:
            exam_data.append({'examination': exam, 'lockable_count': lockable})

    return render(request, 'exams/results/modals/bulk_lock_grades.html', {
        'exam_data': exam_data,
    })


@login_required
def bulk_unlock_grades_modal(request):
    # Permission name matches model Meta: 'unlock_grades'
    if not request.user.has_perm('exams.unlock_grades'):
        raise PermissionDenied("You don't have permission to unlock grades")

    exam_data = []
    for exam in Examination.objects.filter(
        status='COMPLETED'
    ).select_related('subject', 'academic_session').order_by('-exam_date'):
        locked = exam.student_results.filter(is_grade_locked=True).count()
        if locked:
            exam_data.append({'examination': exam, 'locked_count': locked})

    return render(request, 'exams/results/modals/bulk_unlock_grades.html', {
        'exam_data': exam_data,
    })


@login_required
def bulk_publish_results_modal(request):
    exam_data = []
    for exam in Examination.objects.filter(
        status='COMPLETED', results_published=False
    ).select_related('subject', 'academic_session').order_by('-exam_date'):
        total     = exam.student_results.count()
        completed = exam.student_results.filter(status__in=['COMPLETED', 'SUBMITTED']).count()
        if completed:
            exam_data.append({
                'examination':      exam,
                'total_results':    total,
                'completed_results': completed,
            })

    return render(request, 'exams/results/modals/bulk_publish_results.html', {
        'exam_data': exam_data,
    })


# =============================================================================
# ANALYTICS MODALS
# =============================================================================

@login_required
def examination_analytics_modal(request, examination_pk):
    examination = get_object_or_404(Examination, pk=examination_pk)
    try:
        analytics = examination.analytics
    except ExamAnalytics.DoesNotExist:
        analytics = None
    return render(request, 'exams/analytics/modals/examination_analytics.html', {
        'examination': examination,
        'analytics':   analytics,
    })


@login_required
def grade_distribution_modal(request):
    examination_id = request.GET.get('examination')
    context        = {}
    if examination_id:
        examination = get_object_or_404(Examination, pk=examination_id)
        grade_dist  = {}
        for result in examination.student_results.filter(status='COMPLETED'):
            if result.grade:
                grade_dist[result.grade] = grade_dist.get(result.grade, 0) + 1
        context = {'examination': examination, 'grade_distribution': grade_dist}
    return render(request, 'exams/analytics/modals/grade_distribution.html', context)


@login_required
def performance_trends_modal(request):
    student_id = request.GET.get('student')
    context    = {}
    if student_id:
        student = get_object_or_404(Student, pk=student_id)
        context = {
            'student': student,
            'results': StudentExamResult.objects.filter(
                student=student, status='COMPLETED'
            ).select_related('examination__subject')
             .order_by('examination__exam_date'),
        }
    return render(request, 'exams/analytics/modals/performance_trends.html', context)


# =============================================================================
# REPORT MODALS
# =============================================================================

@login_required
def exam_summary_report_modal(request):
    return render(request, 'exams/reports/modals/exam_summary.html', {
        'sessions':    AcademicSession.objects.filter(is_active=True).order_by('-start_date'),
        'categories':  ExamCategory.objects.filter(is_active=True).order_by('name'),
        'subjects':    Subject.objects.filter(is_active=True).order_by('name'),
    })


@login_required
def result_summary_report_modal(request):
    return render(request, 'exams/reports/modals/result_summary.html', {
        'sessions':  AcademicSession.objects.filter(is_active=True).order_by('-start_date'),
        'classes':   Class.objects.filter(is_active=True).select_related('academic_level')
                         .order_by('academic_level__order', 'section'),
        'subjects':  Subject.objects.filter(is_active=True).order_by('name'),
    })


@login_required
def grade_sheet_report_modal(request):
    return render(request, 'exams/reports/modals/grade_sheet.html', {
        'examinations': Examination.objects.filter(status='COMPLETED')
                            .select_related('subject', 'academic_session').order_by('-exam_date'),
    })


@login_required
def mark_sheet_report_modal(request):
    return render(request, 'exams/reports/modals/mark_sheet.html', {
        'examinations': Examination.objects.filter(status='COMPLETED')
                            .select_related('subject', 'academic_session').order_by('-exam_date'),
        'classes':      Class.objects.filter(is_active=True).select_related('academic_level')
                            .order_by('academic_level__order', 'section'),
    })


@login_required
def pass_fail_report_modal(request):
    return render(request, 'exams/reports/modals/pass_fail.html', {
        'examinations': Examination.objects.filter(status='COMPLETED')
                            .select_related('subject', 'academic_session').order_by('-exam_date'),
    })


@login_required
def rank_list_report_modal(request):
    return render(request, 'exams/reports/modals/rank_list.html', {
        'examinations': Examination.objects.filter(status='COMPLETED')
                            .select_related('subject', 'academic_session').order_by('-exam_date'),
        'classes':      Class.objects.filter(is_active=True).select_related('academic_level')
                            .order_by('academic_level__order', 'section'),
    })


@login_required
def merit_list_report_modal(request):
    return render(request, 'exams/reports/modals/merit_list.html', {
        'examinations': Examination.objects.filter(status='COMPLETED')
                            .select_related('subject', 'academic_session').order_by('-exam_date'),
    })


# =============================================================================
# TIMETABLE MODALS
# =============================================================================

@login_required
def generate_timetable_modal(request):
    return render(request, 'exams/timetable/modals/generate.html', {
        'sessions':    AcademicSession.objects.filter(is_active=True).order_by('-start_date'),
        'categories':  ExamCategory.objects.filter(is_active=True).order_by('name'),
    })


@login_required
def exam_timetable_modal(request, session_pk):
    session = get_object_or_404(AcademicSession, pk=session_pk)
    return render(request, 'exams/timetable/modals/view.html', {
        'session': session,
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
        'sessions':    AcademicSession.objects.filter(is_active=True).order_by('-start_date'),
        'categories':  ExamCategory.objects.filter(is_active=True).order_by('name'),
    })


@login_required
def import_grading_systems_modal(request):
    return render(request, 'exams/import/modals/import_grading_systems.html', {})


@login_required
def export_options_modal(request, resource_type):
    valid_types = ['categories', 'grading_systems', 'examinations', 'registrations', 'results']
    if resource_type not in valid_types:
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

@login_required
def history_modal(request, content_type, object_id):
    return render(request, 'exams/modals/history.html', {
        'content_type': content_type,
        'object_id':    object_id,
    })


@login_required
def confirm_action_modal(request):
    return render(request, 'exams/modals/confirm_action.html', {
        'action':  request.GET.get('action', 'perform this action'),
        'message': request.GET.get('message', 'Are you sure you want to proceed?'),
    })


@login_required
def student_exam_history_modal(request, student_pk):
    student = get_object_or_404(Student, pk=student_pk)
    return render(request, 'exams/students/modals/exam_history.html', {
        'student': student,
        'results': StudentExamResult.objects.filter(student=student)
                       .select_related('examination__subject', 'examination__academic_session')
                       .order_by('-examination__exam_date'),
    })


@login_required
def student_results_summary_modal(request, student_pk):
    student         = get_object_or_404(Student, pk=student_pk)
    current_session = get_active_academic_session()

    if current_session:
        results = StudentExamResult.objects.filter(
            student=student,
            examination__academic_session=current_session,
            status='COMPLETED'
        ).select_related('examination__subject')
        stats = results.aggregate(
            total=Count('id'),
            average=Avg('score'),
            pass_count=Count('id', filter=Q(is_pass=True)),
        )
    else:
        results = StudentExamResult.objects.none()
        stats   = {'total': 0, 'average': 0, 'pass_count': 0}

    return render(request, 'exams/students/modals/results_summary.html', {
        'student':         student,
        'current_session': current_session,
        'results':         results,
        'stats':           stats,
    })