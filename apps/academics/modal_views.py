"""
academics/modal_views.py

GET-only modal trigger functions.
──────────────────────────────────
CONTRACT: every function in this file MUST:
  • accept only GET requests  (no POST handling, no form.save())
  • load a form (blank or pre-filled from an existing instance)
    OR load an object for confirmation / quick-view templates
  • return render(request, '<template>', context)

All create / update / delete logic lives in views.py.
Modal templates point their hx-post attributes at the views.py URLs.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404

from .models import (
    AcademicSession, Subject, AcademicLevel, ClassRoom, Class,
    StudentClassEnrollment, ClassSubject, AcademicProgress, Holiday,
)
from .forms import (
    ClassForm, ClassSubjectForm, StudentEnrollmentForm,
)


# =============================================================================
# ACADEMIC SESSIONS
# =============================================================================

@login_required
def academic_session_delete_modal(request, session_pk):
    session = get_object_or_404(AcademicSession, pk=session_pk)
    return render(request, 'academics/sessions/modals/session_delete.html', {
        'session': session,
    })


@login_required
def academic_session_close_modal(request, session_pk):
    session = get_object_or_404(AcademicSession, pk=session_pk)
    return render(request, 'academics/sessions/modals/session_close.html', {
        'session': session,
    })


@login_required
def academic_session_reopen_modal(request, session_pk):
    session = get_object_or_404(AcademicSession, pk=session_pk)
    return render(request, 'academics/sessions/modals/session_reopen.html', {
        'session': session,
    })


@login_required
def academic_session_set_current_modal(request, session_pk):
    session = get_object_or_404(AcademicSession, pk=session_pk)
    return render(request, 'academics/sessions/modals/session_set_current.html', {
        'session': session,
    })


@login_required
def academic_session_toggle_active_modal(request, session_pk):
    session = get_object_or_404(AcademicSession, pk=session_pk)
    return render(request, 'academics/sessions/modals/session_toggle_active.html', {
        'session': session,
    })


@login_required
def academic_session_quick_view_modal(request, session_pk):
    session = get_object_or_404(AcademicSession, pk=session_pk)
    return render(request, 'academics/sessions/modals/session_quick_view.html', {
        'session': session,
    })


# =============================================================================
# SUBJECTS
# =============================================================================

@login_required
def subject_delete_modal(request, subject_pk):
    subject = get_object_or_404(Subject, pk=subject_pk)
    return render(request, 'academics/subjects/modals/subject_delete.html', {
        'subject': subject,
    })


@login_required
def subject_toggle_active_modal(request, subject_pk):
    subject = get_object_or_404(Subject, pk=subject_pk)
    return render(request, 'academics/subjects/modals/subject_toggle_active.html', {
        'subject': subject,
    })


@login_required
def subject_quick_view_modal(request, subject_pk):
    subject = get_object_or_404(Subject, pk=subject_pk)
    return render(request, 'academics/subjects/modals/subject_quick_view.html', {
        'subject': subject,
    })


# =============================================================================
# ACADEMIC LEVELS
# =============================================================================

@login_required
def academic_level_delete_modal(request, level_pk):
    level = get_object_or_404(AcademicLevel, pk=level_pk)
    return render(request, 'academics/levels/modals/level_delete.html', {
        'level': level,
    })


@login_required
def academic_level_toggle_active_modal(request, level_pk):
    level = get_object_or_404(AcademicLevel, pk=level_pk)
    return render(request, 'academics/levels/modals/level_toggle_active.html', {
        'level': level,
    })


@login_required
def academic_level_quick_view_modal(request, level_pk):
    level = get_object_or_404(AcademicLevel, pk=level_pk)
    return render(request, 'academics/levels/modals/level_quick_view.html', {
        'level': level,
    })


# =============================================================================
# CLASSROOMS
# =============================================================================

@login_required
def classroom_delete_modal(request, classroom_pk):
    classroom = get_object_or_404(ClassRoom, pk=classroom_pk)
    return render(request, 'academics/classrooms/modals/classroom_delete.html', {
        'classroom': classroom,
    })


@login_required
def classroom_toggle_active_modal(request, classroom_pk):
    classroom = get_object_or_404(ClassRoom, pk=classroom_pk)
    return render(request, 'academics/classrooms/modals/classroom_toggle_active.html', {
        'classroom': classroom,
    })


@login_required
def classroom_toggle_bookable_modal(request, classroom_pk):
    classroom = get_object_or_404(ClassRoom, pk=classroom_pk)
    return render(request, 'academics/classrooms/modals/classroom_toggle_bookable.html', {
        'classroom': classroom,
    })


@login_required
def classroom_quick_view_modal(request, classroom_pk):
    classroom = get_object_or_404(ClassRoom, pk=classroom_pk)
    return render(request, 'academics/classrooms/modals/classroom_quick_view.html', {
        'classroom': classroom,
    })


# =============================================================================
# CLASSES
# =============================================================================

@login_required
def class_create_modal(request):
    level_pk = request.GET.get('level')
    initial  = {'academic_level': level_pk} if level_pk else {}
    form     = ClassForm(initial=initial)
    return render(request, 'academics/classes/modals/class_form.html', {
        'form': form, 'level_pk': level_pk,
    })


@login_required
def class_edit_modal(request, class_pk):
    class_instance = get_object_or_404(Class, pk=class_pk)
    form = ClassForm(instance=class_instance)
    return render(request, 'academics/classes/modals/class_form.html', {
        'form': form, 'class_instance': class_instance,
    })


@login_required
def class_delete_modal(request, class_pk):
    class_instance     = get_object_or_404(Class, pk=class_pk)
    active_enrollments = class_instance.enrollments.count()
    active_subjects    = class_instance.subjects.filter(is_active=True).count()
    return render(request, 'academics/classes/modals/class_delete.html', {
        'class_instance':     class_instance,
        'active_enrollments': active_enrollments,
        'active_subjects':    active_subjects,
        'can_delete':         active_enrollments == 0 and active_subjects == 0,
    })


@login_required
def class_toggle_active_modal(request, class_pk):
    class_instance = get_object_or_404(Class, pk=class_pk)
    return render(request, 'academics/classes/modals/class_toggle_active.html', {
        'class_instance': class_instance,
    })


@login_required
def class_assign_teacher_modal(request, class_pk):
    class_instance = get_object_or_404(Class, pk=class_pk)
    return render(request, 'academics/classes/modals/class_assign_teacher.html', {
        'class_instance': class_instance,
    })


@login_required
def class_assign_classroom_modal(request, class_pk):
    class_instance = get_object_or_404(Class, pk=class_pk)
    return render(request, 'academics/classes/modals/class_assign_classroom.html', {
        'class_instance': class_instance,
    })


@login_required
def class_quick_view_modal(request, class_pk):
    class_instance = get_object_or_404(
        Class.objects.select_related(
            'academic_level', 'academic_session', 'class_teacher__staff', 'classroom'
        ),
        pk=class_pk,
    )
    return render(request, 'academics/classes/modals/class_quick_view.html', {
        'class_instance': class_instance,
    })


@login_required
def class_fee_structure_modal(request, class_pk):
    """
    Show all applicable fee structures for a class so staff can see
    the base invoice amounts before generating invoices.

    Uses FeesStructureItem.is_mandatory (not fee_category.is_mandatory) to
    determine mandatory vs optional totals, consistent with how
    invoice_generators._add_items() bills students.
    """
    from fees.models import FeesStructure
    class_instance = get_object_or_404(
        Class.objects.select_related('academic_level', 'academic_session'),
        pk=class_pk,
    )

    base_qs = FeesStructure.objects.filter(
        is_active=True,
        applicable_sessions=class_instance.academic_session,
        academic_levels=class_instance.academic_level,
    )

    standard_structure = base_qs.filter(
        boarding_type_filter__in=['ALL', 'DAY_ONLY']
    ).order_by('priority').first()

    boarding_structure = base_qs.filter(
        boarding_type_filter__in=['BOARDER_ONLY', 'FULL_BOARDER', 'WEEKLY_BOARDER', 'FLEXI_BOARDER']
    ).exclude(
        pk=standard_structure.pk if standard_structure else None
    ).order_by('priority').first()

    def _summarise(structure):
        if not structure:
            return [], 0, 0
        items = list(structure.items.select_related(
            'fee_category__display_group'
        ).order_by(
            'fee_category__display_group__display_order',
            'fee_category__display_order',
            'display_order',
        ))
        # FIX: use item.is_mandatory (FeesStructureItem field) not
        # item.fee_category.is_mandatory — this matches what the invoice
        # generator checks in _add_items() via si.is_mandatory.
        mandatory = sum(i.amount for i in items if i.is_mandatory)
        optional  = sum(i.amount for i in items if not i.is_mandatory)
        return items, mandatory, optional

    std_items,   std_mandatory,   std_optional   = _summarise(standard_structure)
    board_items, board_mandatory, board_optional = _summarise(boarding_structure)

    return render(request, 'academics/classes/modals/fee_structure_preview.html', {
        'class_instance':  class_instance,
        'std_structure':   standard_structure,
        'std_items':       std_items,
        'std_mandatory':   std_mandatory,
        'std_optional':    std_optional,
        'board_structure': boarding_structure,
        'board_items':     board_items,
        'board_mandatory': board_mandatory,
        'board_optional':  board_optional,
        'boarder_total':   std_mandatory + board_mandatory,
    })


@login_required
def class_students_modal(request, class_pk):
    class_instance = get_object_or_404(Class, pk=class_pk)
    enrollments    = class_instance.enrollments.select_related('student').filter(
        is_active=True, completion_status='ONGOING'
    ).order_by('roll_number', 'student__last_name')
    return render(request, 'academics/classes/modals/class_students.html', {
        'class_instance': class_instance,
        'enrollments':    enrollments,
    })


# =============================================================================
# CLASS SUBJECTS
# =============================================================================

@login_required
def class_subject_create_modal(request):
    class_pk       = request.GET.get('class_pk')
    class_instance = get_object_or_404(Class, pk=class_pk) if class_pk else None
    form = ClassSubjectForm(initial={
        'class_instance':               class_instance,
        'continuous_assessment_weight': 40,
        'final_exam_weight':            60,
        'is_active':                    True,
    })
    return render(request, 'academics/classes/modals/class_subject_form.html', {
        'form': form, 'class_instance': class_instance,
    })


@login_required
def class_subject_edit_modal(request, class_subject_pk):
    class_subject = get_object_or_404(
        ClassSubject.objects.select_related('class_instance', 'subject', 'teacher'),
        pk=class_subject_pk,
    )
    form = ClassSubjectForm(instance=class_subject)
    return render(request, 'academics/classes/modals/class_subject_form.html', {
        'form': form, 'class_subject': class_subject,
        'class_instance': class_subject.class_instance,
    })


@login_required
def class_subject_delete_modal(request, class_subject_pk):
    class_subject = get_object_or_404(
        ClassSubject.objects.select_related('class_instance', 'subject'),
        pk=class_subject_pk,
    )
    return render(request, 'academics/classes/modals/class_subject_delete.html', {
        'class_subject':  class_subject,
        'class_instance': class_subject.class_instance,
    })


@login_required
def class_subject_toggle_active_modal(request, class_subject_pk):
    class_subject = get_object_or_404(
        ClassSubject.objects.select_related('class_instance', 'subject'),
        pk=class_subject_pk,
    )
    return render(request, 'academics/classes/modals/class_subject_toggle_active.html', {
        'class_subject':  class_subject,
        'class_instance': class_subject.class_instance,
    })


@login_required
def class_subject_assign_teacher_modal(request, class_subject_pk):
    class_subject = get_object_or_404(
        ClassSubject.objects.select_related('class_instance', 'subject', 'teacher__staff'),
        pk=class_subject_pk,
    )
    return render(request, 'academics/classes/modals/class_subject_assign_teacher.html', {
        'class_subject':  class_subject,
        'class_instance': class_subject.class_instance,
    })


@login_required
def class_subject_quick_view_modal(request, class_subject_pk):
    class_subject = get_object_or_404(
        ClassSubject.objects.select_related('class_instance', 'subject', 'teacher__staff'),
        pk=class_subject_pk,
    )
    return render(request, 'academics/classes/modals/class_subject_quick_view.html', {
        'class_subject':  class_subject,
        'class_instance': class_subject.class_instance,
    })


# =============================================================================
# STUDENT ENROLLMENTS
# =============================================================================

@login_required
def enrollment_create_modal(request):
    class_pk       = request.GET.get('class_pk')
    class_instance = get_object_or_404(Class, pk=class_pk) if class_pk else None
    from students.models import Student
    students = Student.objects.filter(
        enrollment_status='ACTIVE'
    ).select_related('current_academic_level').order_by('first_name', 'last_name')
    form = StudentEnrollmentForm(initial={
        'class_instance': class_instance,
        'is_active':      True,
    })
    form.fields['student'].queryset = students
    return render(request, 'academics/enrollments/modals/enrollment_form.html', {
        'form': form, 'class_instance': class_instance, 'students': students,
    })


@login_required
def enrollment_delete_modal(request, enrollment_pk):
    enrollment = get_object_or_404(
        StudentClassEnrollment.objects.select_related(
            'student', 'class_instance', 'academic_invoice'
        ),
        pk=enrollment_pk,
    )
    return render(request, 'academics/enrollments/modals/enrollment_delete.html', {
        'enrollment': enrollment,
    })


@login_required
def enrollment_toggle_active_modal(request, enrollment_pk):
    enrollment = get_object_or_404(
        StudentClassEnrollment.objects.select_related('student'),
        pk=enrollment_pk,
    )
    return render(request, 'academics/enrollments/modals/enrollment_toggle_active.html', {
        'enrollment': enrollment,
    })


@login_required
def enrollment_create_invoice_modal(request, enrollment_pk):
    """
    Invoice preview modal.

    Delegates entirely to generate_invoice_preview() in fees/invoice_generators.py
    which runs the full generator inside a rolled-back savepoint.  This view
    does no transaction management — it just calls the function and renders.
    """
    import logging
    logger = logging.getLogger(__name__)

    enrollment = get_object_or_404(
        StudentClassEnrollment.objects.select_related(
            'student', 'class_instance__academic_level',
            'class_instance__academic_session', 'academic_session',
            'academic_invoice',
        ),
        pk=enrollment_pk,
    )

    already_exists = bool(enrollment.academic_invoice_id)
    preview        = None

    if not already_exists:
        try:
            from fees.invoice_generators import (
                generate_invoice_preview,
                FeeStructureNotFoundError,
            )
            preview = generate_invoice_preview(enrollment)

        except FeeStructureNotFoundError:
            preview = {'error': 'no_structure'}

        except Exception as exc:
            logger.exception(
                "Invoice preview failed for enrollment %s: %s",
                enrollment_pk, exc,
            )
            preview = None

    return render(request, 'academics/enrollments/modals/create_invoice.html', {
        'enrollment':     enrollment,
        'already_exists': already_exists,
        'preview':        preview,
    })

@login_required
def enrollment_edit_modal(request, enrollment_pk):
    enrollment = get_object_or_404(
        StudentClassEnrollment.objects.select_related(
            'student', 'class_instance__academic_level',
            'class_instance__academic_session', 'academic_invoice'
        ),
        pk=enrollment_pk,
    )
    form = StudentEnrollmentForm(instance=enrollment)
    return render(request, 'academics/enrollments/modals/enrollment_edit.html', {
        'form': form, 'enrollment': enrollment,
    })


@login_required
def enrollment_quick_view_modal(request, enrollment_pk):
    enrollment = get_object_or_404(
        StudentClassEnrollment.objects.select_related(
            'student', 'class_instance__academic_level',
            'academic_session', 'academic_invoice',
        ),
        pk=enrollment_pk,
    )
    return render(request, 'academics/enrollments/modals/enrollment_quick_view.html', {
        'enrollment': enrollment,
    })


# =============================================================================
# ACADEMIC PROGRESS
# =============================================================================

@login_required
def academic_progress_delete_modal(request, progress_pk):
    progress = get_object_or_404(
        AcademicProgress.objects.select_related('student', 'academic_session'),
        pk=progress_pk,
    )
    return render(request, 'academics/progress/modals/progress_delete.html', {
        'progress': progress,
    })


@login_required
def academic_progress_finalize_modal(request, progress_pk):
    progress = get_object_or_404(
        AcademicProgress.objects.select_related('student', 'academic_session'),
        pk=progress_pk,
    )
    return render(request, 'academics/progress/modals/progress_finalize.html', {
        'progress': progress,
    })


@login_required
def academic_progress_promotion_modal(request, progress_pk):
    progress = get_object_or_404(
        AcademicProgress.objects.select_related('student', 'academic_session'),
        pk=progress_pk,
    )
    return render(request, 'academics/progress/modals/progress_promotion.html', {
        'progress': progress,
    })


@login_required
def academic_progress_quick_view_modal(request, progress_pk):
    progress = get_object_or_404(
        AcademicProgress.objects.select_related(
            'student', 'academic_session', 'class_enrollment'
        ),
        pk=progress_pk,
    )
    return render(request, 'academics/progress/modals/progress_quick_view.html', {
        'progress': progress,
    })


@login_required
def bulk_progress_finalize_modal(request):
    return render(request, 'academics/progress/modals/bulk_progress_finalize.html', {})


# =============================================================================
# HOLIDAYS
# =============================================================================

@login_required
def holiday_delete_modal(request, holiday_pk):
    holiday = get_object_or_404(Holiday, pk=holiday_pk)
    return render(request, 'academics/holidays/modals/holiday_delete.html', {
        'holiday': holiday,
    })


@login_required
def holiday_quick_view_modal(request, holiday_pk):
    holiday = get_object_or_404(Holiday, pk=holiday_pk)
    return render(request, 'academics/holidays/modals/holiday_quick_view.html', {
        'holiday': holiday,
    })


# =============================================================================
# REPORT MODALS
# =============================================================================

@login_required
def session_summary_report_modal(request):
    sessions = AcademicSession.objects.filter(is_active=True).order_by('-start_date')
    return render(request, 'academics/reports/modals/session_summary_report.html', {
        'sessions': sessions,
    })


@login_required
def attendance_report_modal(request):
    sessions = AcademicSession.objects.filter(is_active=True).order_by('-start_date')
    return render(request, 'academics/reports/modals/attendance_report.html', {
        'sessions': sessions,
    })


@login_required
def grade_distribution_report_modal(request):
    sessions = AcademicSession.objects.filter(is_active=True).order_by('-start_date')
    levels   = AcademicLevel.objects.filter(is_active=True).order_by('order')
    return render(request, 'academics/reports/modals/grade_distribution_report.html', {
        'sessions': sessions, 'levels': levels,
    })


@login_required
def class_roster_report_modal(request):
    sessions = AcademicSession.objects.filter(is_active=True).order_by('-start_date')
    classes  = Class.objects.filter(is_active=True).select_related(
        'academic_level', 'academic_session'
    ).order_by('academic_level__order', 'section')
    return render(request, 'academics/reports/modals/class_roster_report.html', {
        'sessions': sessions, 'classes': classes,
    })


@login_required
def teacher_assignment_report_modal(request):
    sessions = AcademicSession.objects.filter(is_active=True).order_by('-start_date')
    return render(request, 'academics/reports/modals/teacher_assignment_report.html', {
        'sessions': sessions,
    })


@login_required
def promotion_analysis_report_modal(request):
    sessions = AcademicSession.objects.filter(is_active=True).order_by('-start_date')
    levels   = AcademicLevel.objects.filter(is_active=True).order_by('order')
    return render(request, 'academics/reports/modals/promotion_analysis_report.html', {
        'sessions': sessions, 'levels': levels,
    })


# =============================================================================
# ACADEMIC CALENDAR MODAL
# =============================================================================

@login_required
def calendar_events_modal(request):
    from core.utils import get_school_today
    today    = get_school_today()
    holidays = Holiday.objects.filter(start_date__gte=today).order_by('start_date')[:10]
    sessions = AcademicSession.objects.filter(is_active=True).order_by('-start_date')[:5]
    return render(request, 'academics/calendar/modals/calendar_events.html', {
        'holidays': holidays, 'sessions': sessions,
    })


# =============================================================================
# IMPORT / EXPORT MODALS
# =============================================================================

@login_required
def import_students_modal(request):
    return render(request, 'academics/import/modals/import_students.html', {})


@login_required
def import_subjects_modal(request):
    return render(request, 'academics/import/modals/import_subjects.html', {})


@login_required
def import_enrollments_modal(request):
    sessions = AcademicSession.objects.filter(is_active=True).order_by('-start_date')
    classes  = Class.objects.filter(is_active=True).select_related('academic_level').order_by(
        'academic_level__order'
    )
    return render(request, 'academics/import/modals/import_enrollments.html', {
        'sessions': sessions, 'classes': classes,
    })


@login_required
def export_options_modal(request, resource_type):
    return render(request, 'academics/export/modals/export_options.html', {
        'resource_type': resource_type,
    })


# =============================================================================
# SETTINGS MODALS
# =============================================================================

@login_required
def academic_settings_modal(request):
    return render(request, 'academics/settings/modals/academic_settings.html', {})


@login_required
def grading_scale_modal(request):
    return render(request, 'academics/settings/modals/grading_scale.html', {})


@login_required
def promotion_rules_modal(request):
    return render(request, 'academics/settings/modals/promotion_rules.html', {})


# =============================================================================
# UTILITY MODALS
# =============================================================================

@login_required
def confirm_action_modal(request):
    return render(request, 'academics/modals/confirm_action.html', {
        'action_url':  request.GET.get('action_url', ''),
        'action_name': request.GET.get('action_name', 'Confirm'),
        'message':     request.GET.get('message', 'Are you sure?'),
        'method':      request.GET.get('method', 'POST'),
    })


@login_required
def history_modal(request):
    return render(request, 'academics/modals/history.html', {
        'model_name': request.GET.get('model', ''),
        'object_pk':  request.GET.get('pk', ''),
    })


@login_required
def student_enrollment_history_modal(request, student_pk):
    from students.models import Student
    student = get_object_or_404(Student, pk=student_pk)
    history = StudentClassEnrollment.objects.filter(student=student).select_related(
        'class_instance__academic_level', 'academic_session'
    ).order_by('-enrollment_date')
    return render(request, 'academics/enrollments/modals/student_enrollment_history.html', {
        'student': student, 'history': history,
    })


@login_required
def teacher_classes_modal(request, teacher_pk):
    from hr.models import Teacher
    teacher          = get_object_or_404(Teacher, pk=teacher_pk)
    class_subjects   = ClassSubject.objects.filter(
        teacher=teacher, is_active=True
    ).select_related('class_instance__academic_level', 'class_instance__academic_session', 'subject')
    teaching_classes = Class.objects.filter(
        class_teacher=teacher, is_active=True
    ).select_related('academic_level', 'academic_session')
    return render(request, 'academics/classes/modals/teacher_classes.html', {
        'teacher':          teacher,
        'class_subjects':   class_subjects,
        'teaching_classes': teaching_classes,
    })