# academics/modal_views.py

"""
Modal Views for Academic Management

This module contains modal views for the academics app.
These are lightweight views that return HTML partials for modals.

IMPORTANT: This module does NOT contain form modals for create/edit operations.
Create and Edit operations use full template pages in views.py instead.

Modal types included:
- Delete confirmation modals
- Toggle action modals (activate/deactivate)  
- Quick view modals (preview)
- Action confirmation modals (close, finalize, promote, etc.)
- Report option modals
- Bulk operation modals
- Utility modals
"""

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q

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

from core.utils import get_school_today


# =============================================================================
# ACADEMIC SESSION MODALS
# =============================================================================

@login_required
def academic_session_delete_modal(request, session_pk):
    """Return delete confirmation modal for academic session"""
    session = get_object_or_404(AcademicSession, pk=session_pk)
    
    # Check if can be deleted
    can_delete = True
    warnings = []
    
    # Check for active classes
    active_classes = session.classes.filter(is_active=True).count()
    if active_classes > 0:
        can_delete = False
        warnings.append(f"Has {active_classes} active class(es)")
    
    # Check for active enrollments
    active_enrollments = session.student_class_enrollments.filter(is_active=True).count()
    if active_enrollments > 0:
        can_delete = False
        warnings.append(f"Has {active_enrollments} active enrollment(s)")
    
    return render(request, 'academics/sessions/modals/delete_session.html', {
        'session': session,
        'can_delete': can_delete,
        'warnings': warnings,
    })


@login_required
def academic_session_close_modal(request, session_pk):
    """Return modal for closing academic session"""
    session = get_object_or_404(AcademicSession, pk=session_pk)
    
    # Get statistics
    total_enrollments = session.student_class_enrollments.count()
    ongoing_enrollments = session.student_class_enrollments.filter(
        completion_status='ONGOING'
    ).count()
    
    # Warnings
    warnings = []
    if ongoing_enrollments > 0:
        warnings.append(f"{ongoing_enrollments} student(s) still have ongoing enrollments")
    
    return render(request, 'academics/sessions/modals/close_session.html', {
        'session': session,
        'total_enrollments': total_enrollments,
        'ongoing_enrollments': ongoing_enrollments,
        'warnings': warnings,
    })


@login_required
def academic_session_reopen_modal(request, session_pk):
    """Return modal for reopening academic session"""
    session = get_object_or_404(AcademicSession, pk=session_pk)
    
    return render(request, 'academics/sessions/modals/reopen_session.html', {
        'session': session,
    })


@login_required
def academic_session_set_current_modal(request, session_pk):
    """Return modal for setting session as current"""
    session = get_object_or_404(AcademicSession, pk=session_pk)
    
    # Get current session if exists
    current_session = AcademicSession.objects.filter(is_current=True).first()
    
    return render(request, 'academics/sessions/modals/set_current.html', {
        'session': session,
        'current_session': current_session,
    })


# =============================================================================
# SUBJECT MODALS
# =============================================================================

@login_required
def subject_delete_modal(request, subject_pk):
    """Return delete confirmation modal for subject"""
    subject = get_object_or_404(Subject, pk=subject_pk)
    
    # Check if can be deleted
    can_delete = True
    warnings = []
    
    # Check for class assignments
    active_assignments = ClassSubject.objects.filter(
        subject=subject,
        is_active=True
    ).count()
    
    if active_assignments > 0:
        can_delete = False
        warnings.append(f"Assigned to {active_assignments} active class(es)")
    
    return render(request, 'academics/subjects/modals/delete_subject.html', {
        'subject': subject,
        'can_delete': can_delete,
        'warnings': warnings,
    })


# =============================================================================
# ACADEMIC LEVEL MODALS
# =============================================================================

@login_required
def academic_level_delete_modal(request, level_pk):
    """Return delete confirmation modal for academic level"""
    level = get_object_or_404(AcademicLevel, pk=level_pk)
    
    # Check if can be deleted
    can_delete = True
    warnings = []
    
    # Check for active classes
    active_classes = level.classes.filter(is_active=True).count()
    if active_classes > 0:
        can_delete = False
        warnings.append(f"Has {active_classes} active class(es)")
    
    # Check for students
    from students.models import Student
    students_at_level = Student.objects.filter(
        current_academic_level=level
    ).count()
    if students_at_level > 0:
        can_delete = False
        warnings.append(f"{students_at_level} student(s) currently at this level")
    
    return render(request, 'academics/levels/modals/delete_level.html', {
        'level': level,
        'can_delete': can_delete,
        'warnings': warnings,
    })


# =============================================================================
# CLASSROOM MODALS
# =============================================================================

@login_required
def classroom_delete_modal(request, classroom_pk):
    """Return delete confirmation modal for classroom"""
    classroom = get_object_or_404(ClassRoom, pk=classroom_pk)
    
    # Check if can be deleted
    can_delete = True
    warnings = []
    
    # Check for assigned classes
    assigned_classes = classroom.assigned_classes.filter(is_active=True).count()
    if assigned_classes > 0:
        can_delete = False
        warnings.append(f"Assigned to {assigned_classes} active class(es)")
    
    return render(request, 'academics/classrooms/modals/delete_classroom.html', {
        'classroom': classroom,
        'can_delete': can_delete,
        'warnings': warnings,
    })


# =============================================================================
# CLASS MODALS
# =============================================================================

@login_required
def class_delete_modal(request, class_pk):
    """Return delete confirmation modal for class"""
    class_instance = get_object_or_404(Class, pk=class_pk)
    
    # Check if can be deleted
    can_delete = True
    warnings = []
    
    # Check for active enrollments
    active_enrollments = class_instance.enrollments.filter(is_active=True).count()
    if active_enrollments > 0:
        can_delete = False
        warnings.append(f"Has {active_enrollments} active enrollment(s)")
    
    # Check for assigned subjects
    active_subjects = class_instance.subjects.filter(is_active=True).count()
    if active_subjects > 0:
        warnings.append(f"Has {active_subjects} assigned subject(s)")
    
    return render(request, 'academics/classes/modals/delete_class.html', {
        'class': class_instance,
        'can_delete': can_delete,
        'warnings': warnings,
    })


# =============================================================================
# ENROLLMENT MODALS
# =============================================================================

@login_required
def enrollment_delete_modal(request, enrollment_pk):
    """Return delete confirmation modal for enrollment"""
    from core.utils import format_money

    enrollment = get_object_or_404(StudentClassEnrollment, pk=enrollment_pk)

    can_delete = True
    warnings = []

    if enrollment.academic_invoice:
        invoice = enrollment.academic_invoice

        # PRIMARY CHECK: Journal Entry Status (highest priority)
        if invoice.journal_entry:
            je_status = invoice.journal_entry.status
            
            if je_status == 'POSTED':
                can_delete = False
                warnings.append(
                    f"Invoice has posted journal entry ({invoice.journal_entry.entry_number})"
                )
            elif je_status == 'REVERSED':
                can_delete = False
                warnings.append(
                    f"Invoice has reversed journal entry ({invoice.journal_entry.entry_number})"
                )
            # DRAFT journal entries are OK - will be deleted with invoice

        # SECONDARY CHECK: Invoice Status
        # Allow deletion for DRAFT and VOID invoices only
        if invoice.status not in ['DRAFT', 'VOID'] and can_delete:
            can_delete = False
            warnings.append(
                f"Invoice status is {invoice.get_status_display()}"
            )

        # TERTIARY CHECK: Payments (but VOID invoices should have zero payments)
        if invoice.paid_amount > 0 and can_delete:
            can_delete = False
            warnings.append(
                f"Invoice has payments of {format_money(invoice.paid_amount)}"
            )

    return render(
        request,
        'academics/enrollments/modals/delete_enrollment.html',
        {
            'enrollment': enrollment,
            'can_delete': can_delete,
            'warnings': warnings,
        }
    )

@login_required
def enrollment_toggle_active_modal(request, enrollment_pk):
    """Return modal for toggling enrollment active status"""
    enrollment = get_object_or_404(StudentClassEnrollment, pk=enrollment_pk)
    
    action = 'deactivate' if enrollment.is_active else 'activate'
    
    return render(request, 'academics/enrollments/modals/toggle_active.html', {
        'enrollment': enrollment,
        'action': action,
    })


@login_required
def enrollment_update_status_modal(request, enrollment_pk):
    """Return modal for updating enrollment completion status"""
    enrollment = get_object_or_404(StudentClassEnrollment, pk=enrollment_pk)
    
    return render(request, 'academics/enrollments/modals/update_status.html', {
        'enrollment': enrollment,
    })


@login_required
def enrollment_assign_roll_number_modal(request, enrollment_pk):
    """Return modal for assigning roll number"""
    enrollment = get_object_or_404(StudentClassEnrollment, pk=enrollment_pk)
    
    # Get next available roll number
    last_enrollment = StudentClassEnrollment.objects.filter(
        class_instance=enrollment.class_instance
    ).exclude(
        roll_number__isnull=True
    ).order_by('-roll_number').first()
    
    suggested_roll_number = '001'
    if last_enrollment and last_enrollment.roll_number:
        try:
            next_num = int(last_enrollment.roll_number) + 1
            suggested_roll_number = str(next_num).zfill(3)
        except ValueError:
            pass
    
    return render(request, 'academics/enrollments/modals/assign_roll_number.html', {
        'enrollment': enrollment,
        'suggested_roll_number': suggested_roll_number,
    })


@login_required
def enrollment_create_invoice_modal(request, enrollment_pk):
    """Return modal for creating invoice for enrollment"""
    enrollment = get_object_or_404(StudentClassEnrollment, pk=enrollment_pk)
    
    # Check if already has invoice
    has_invoice = enrollment.academic_invoice is not None
    
    return render(request, 'academics/enrollments/modals/create_invoice.html', {
        'enrollment': enrollment,
        'has_invoice': has_invoice,
    })


@login_required
def bulk_enrollment_modal(request):
    """Return modal for bulk enrollment"""
    # Get active sessions and classes
    sessions = AcademicSession.objects.filter(is_active=True)
    classes = Class.objects.filter(is_active=True).select_related('academic_level', 'academic_session')
    
    return render(request, 'academics/enrollments/modals/bulk_enrollment.html', {
        'sessions': sessions,
        'classes': classes,
    })


# =============================================================================
# CLASS SUBJECT MODALS
# =============================================================================

@login_required
def class_subject_delete_modal(request, class_subject_pk):
    """Return delete confirmation modal for class subject"""
    class_subject = get_object_or_404(ClassSubject, pk=class_subject_pk)
    
    # Check if can be deleted
    can_delete = True
    warnings = []
    
    # Check for existing grades (if grades model exists)
    # This would need to be implemented based on your grades model
    
    return render(request, 'academics/class_subjects/modals/delete_class_subject.html', {
        'class_subject': class_subject,
        'can_delete': can_delete,
        'warnings': warnings,
    })


@login_required
def class_subject_assign_teacher_modal(request, class_subject_pk):
    """Return modal for assigning teacher to class subject"""
    class_subject = get_object_or_404(ClassSubject, pk=class_subject_pk)
    
    # Get available teachers
    from hr.models import Teacher
    teachers = Teacher.objects.filter(is_active=True).select_related('staff')
    
    return render(request, 'academics/class_subjects/modals/assign_teacher.html', {
        'class_subject': class_subject,
        'teachers': teachers,
    })


@login_required
def class_subject_toggle_active_modal(request, class_subject_pk):
    """Return modal for toggling class subject active status"""
    class_subject = get_object_or_404(ClassSubject, pk=class_subject_pk)
    
    action = 'deactivate' if class_subject.is_active else 'activate'
    
    return render(request, 'academics/class_subjects/modals/toggle_active.html', {
        'class_subject': class_subject,
        'action': action,
    })


@login_required
def bulk_class_subject_assign_modal(request):
    """Return modal for bulk subject assignment"""
    classes = Class.objects.filter(is_active=True).select_related('academic_level')
    subjects = Subject.objects.filter(is_active=True)
    
    return render(request, 'academics/class_subjects/modals/bulk_assign.html', {
        'classes': classes,
        'subjects': subjects,
    })


# =============================================================================
# ACADEMIC PROGRESS MODALS
# =============================================================================

@login_required
def academic_progress_delete_modal(request, progress_pk):
    """Return delete confirmation modal for academic progress"""
    progress = get_object_or_404(AcademicProgress, pk=progress_pk)
    
    # Check if can be deleted
    can_delete = not progress.is_final
    warnings = []
    
    if progress.is_final:
        warnings.append("Progress record is finalized - cannot delete")
    
    return render(request, 'academics/progress/modals/delete_progress.html', {
        'progress': progress,
        'can_delete': can_delete,
        'warnings': warnings,
    })


@login_required
def academic_progress_finalize_modal(request, progress_pk):
    """Return modal for finalizing academic progress"""
    progress = get_object_or_404(AcademicProgress, pk=progress_pk)
    
    warnings = []
    if progress.is_final:
        warnings.append("Progress is already finalized")
    
    return render(request, 'academics/progress/modals/finalize_progress.html', {
        'progress': progress,
        'warnings': warnings,
    })


# =============================================================================
# HOLIDAY MODALS
# =============================================================================

@login_required
def holiday_delete_modal(request, holiday_pk):
    """Return delete confirmation modal for holiday"""
    holiday = get_object_or_404(Holiday, pk=holiday_pk)
    
    # Check if can be deleted
    can_delete = True
    warnings = []
    
    today = get_school_today()
    if holiday.start_date < today:
        warnings.append("Holiday has already started/passed")
    
    if holiday.is_recurring:
        warnings.append("This is a recurring holiday")
    
    return render(request, 'academics/holidays/modals/delete_holiday.html', {
        'holiday': holiday,
        'can_delete': can_delete,
        'warnings': warnings,
    })


# =============================================================================
# QUICK VIEW MODALS
# =============================================================================

@login_required
def academic_session_quick_view_modal(request, session_pk):
    """Quick view modal for academic session"""
    session = get_object_or_404(AcademicSession, pk=session_pk)
    
    stats = {
        'total_classes': session.classes.filter(is_active=True).count(),
        'total_enrollments': session.student_class_enrollments.filter(is_active=True).count(),
    }
    
    return render(request, 'academics/sessions/modals/quick_view.html', {
        'session': session,
        'stats': stats,
    })


@login_required
def subject_quick_view_modal(request, subject_pk):
    """Quick view modal for subject"""
    subject = get_object_or_404(Subject, pk=subject_pk)
    
    assignment_count = ClassSubject.objects.filter(subject=subject, is_active=True).count()
    
    return render(request, 'academics/subjects/modals/quick_view.html', {
        'subject': subject,
        'assignment_count': assignment_count,
    })


@login_required
def academic_level_quick_view_modal(request, level_pk):
    """Quick view modal for academic level"""
    level = get_object_or_404(AcademicLevel, pk=level_pk)
    
    stats = {
        'total_classes': level.classes.filter(is_active=True).count(),
    }
    
    return render(request, 'academics/levels/modals/quick_view.html', {
        'level': level,
        'stats': stats,
    })


@login_required
def classroom_quick_view_modal(request, classroom_pk):
    """Quick view modal for classroom"""
    classroom = get_object_or_404(ClassRoom, pk=classroom_pk)
    
    assigned_classes = classroom.assigned_classes.filter(is_active=True)
    
    return render(request, 'academics/classrooms/modals/quick_view.html', {
        'classroom': classroom,
        'assigned_classes': assigned_classes,
    })


@login_required
def class_quick_view_modal(request, class_pk):
    """Quick view modal for class"""
    class_instance = get_object_or_404(
        Class.objects.select_related('academic_level', 'class_teacher', 'classroom'),
        pk=class_pk
    )
    
    enrollment_count = class_instance.enrollments.filter(is_active=True).count()
    
    return render(request, 'academics/classes/modals/quick_view.html', {
        'class': class_instance,
        'enrollment_count': enrollment_count,
    })


@login_required
def enrollment_quick_view_modal(request, enrollment_pk):
    """Quick view modal for enrollment"""
    enrollment = get_object_or_404(
        StudentClassEnrollment.objects.select_related('student', 'class_instance'),
        pk=enrollment_pk
    )
    
    return render(request, 'academics/enrollments/modals/quick_view.html', {
        'enrollment': enrollment,
    })


@login_required
def class_subject_quick_view_modal(request, class_subject_pk):
    """Quick view modal for class subject"""
    class_subject = get_object_or_404(
        ClassSubject.objects.select_related('class_instance', 'subject', 'teacher'),
        pk=class_subject_pk
    )
    
    return render(request, 'academics/class_subjects/modals/quick_view.html', {
        'class_subject': class_subject,
    })


@login_required
def academic_progress_quick_view_modal(request, progress_pk):
    """Quick view modal for academic progress"""
    progress = get_object_or_404(
        AcademicProgress.objects.select_related('student', 'academic_session'),
        pk=progress_pk
    )
    
    return render(request, 'academics/progress/modals/quick_view.html', {
        'progress': progress,
    })


@login_required
def holiday_quick_view_modal(request, holiday_pk):
    """Quick view modal for holiday"""
    holiday = get_object_or_404(Holiday, pk=holiday_pk)
    
    return render(request, 'academics/holidays/modals/quick_view.html', {
        'holiday': holiday,
    })


# =============================================================================
# TOGGLE ACTIVE MODALS
# =============================================================================

@login_required
def academic_session_toggle_active_modal(request, session_pk):
    """Toggle active modal for academic session"""
    session = get_object_or_404(AcademicSession, pk=session_pk)
    
    action = 'deactivate' if session.is_active else 'activate'
    
    return render(request, 'academics/sessions/modals/toggle_active.html', {
        'session': session,
        'action': action,
    })


@login_required
def subject_toggle_active_modal(request, subject_pk):
    """Toggle active modal for subject"""
    subject = get_object_or_404(Subject, pk=subject_pk)
    
    action = 'deactivate' if subject.is_active else 'activate'
    
    return render(request, 'academics/subjects/modals/toggle_active.html', {
        'subject': subject,
        'action': action,
    })


@login_required
def academic_level_toggle_active_modal(request, level_pk):
    """Toggle active modal for academic level"""
    level = get_object_or_404(AcademicLevel, pk=level_pk)
    
    action = 'deactivate' if level.is_active else 'activate'
    
    return render(request, 'academics/levels/modals/toggle_active.html', {
        'level': level,
        'action': action,
    })


@login_required
def classroom_toggle_active_modal(request, classroom_pk):
    """Toggle active modal for classroom"""
    classroom = get_object_or_404(ClassRoom, pk=classroom_pk)
    
    action = 'deactivate' if classroom.is_active else 'activate'
    
    return render(request, 'academics/classrooms/modals/toggle_active.html', {
        'classroom': classroom,
        'action': action,
    })


@login_required
def classroom_toggle_bookable_modal(request, classroom_pk):
    """Toggle bookable modal for classroom"""
    classroom = get_object_or_404(ClassRoom, pk=classroom_pk)
    
    action = 'make non-bookable' if classroom.is_bookable else 'make bookable'
    
    return render(request, 'academics/classrooms/modals/toggle_bookable.html', {
        'classroom': classroom,
        'action': action,
    })


@login_required
def class_toggle_active_modal(request, class_pk):
    """Toggle active modal for class"""
    class_instance = get_object_or_404(Class, pk=class_pk)
    
    action = 'deactivate' if class_instance.is_active else 'activate'
    
    return render(request, 'academics/classes/modals/toggle_active.html', {
        'class': class_instance,
        'action': action,
    })


# =============================================================================
# ASSIGNMENT MODALS
# =============================================================================

@login_required
def class_assign_teacher_modal(request, class_pk):
    """Assign teacher to class modal"""
    class_instance = get_object_or_404(Class, pk=class_pk)
    
    from hr.models import Teacher
    teachers = Teacher.objects.filter(is_active=True).select_related('staff')
    
    return render(request, 'academics/classes/modals/assign_teacher.html', {
        'class': class_instance,
        'teachers': teachers,
    })


@login_required
def class_assign_classroom_modal(request, class_pk):
    """Assign classroom to class modal"""
    class_instance = get_object_or_404(Class, pk=class_pk)
    
    classrooms = ClassRoom.objects.filter(is_active=True)
    
    return render(request, 'academics/classes/modals/assign_classroom.html', {
        'class': class_instance,
        'classrooms': classrooms,
    })


# =============================================================================
# PROMOTION DECISION MODAL (for academic progress)
# =============================================================================

@login_required
def academic_progress_promotion_modal(request, progress_pk):
    """Promotion decision modal for academic progress record"""
    progress = get_object_or_404(AcademicProgress, pk=progress_pk)
    
    return render(request, 'academics/progress/modals/promotion.html', {
        'progress': progress,
    })


# =============================================================================
# BULK OPERATION MODALS
# =============================================================================

@login_required
def bulk_enrollment_status_update_modal(request):
    """Bulk enrollment status update modal"""
    return render(request, 'academics/enrollments/modals/bulk_status_update.html')


@login_required
def bulk_progress_finalize_modal(request):
    """Bulk progress finalization modal"""
    return render(request, 'academics/progress/modals/bulk_finalize.html')


# =============================================================================
# UTILITY AND HELPER MODALS
# =============================================================================

@login_required
def confirm_action_modal(request):
    """Generic confirmation modal"""
    action = request.GET.get('action', 'this action')
    message = request.GET.get('message', f'Are you sure you want to {action}?')
    
    return render(request, 'academics/modals/confirm_action.html', {
        'action': action,
        'message': message,
    })


@login_required
def history_modal(request):
    """History view modal"""
    model_name = request.GET.get('model')
    object_id = request.GET.get('id')
    
    return render(request, 'academics/modals/history.html', {
        'model_name': model_name,
        'object_id': object_id,
    })


@login_required
def student_enrollment_history_modal(request, student_pk):
    """Student enrollment history modal"""
    from students.models import Student
    student = get_object_or_404(Student, pk=student_pk)
    
    enrollments = StudentClassEnrollment.objects.filter(
        student=student
    ).select_related('class_instance', 'academic_session').order_by('-enrollment_date')
    
    return render(request, 'academics/enrollments/modals/student_history.html', {
        'student': student,
        'enrollments': enrollments,
    })


@login_required
def class_students_modal(request, class_pk):
    """Class students list modal"""
    class_instance = get_object_or_404(Class, pk=class_pk)
    
    enrollments = class_instance.enrollments.select_related('student').filter(
        is_active=True
    ).order_by('roll_number', 'student__last_name')
    
    return render(request, 'academics/classes/modals/students.html', {
        'class': class_instance,
        'enrollments': enrollments,
    })


@login_required
def teacher_classes_modal(request, teacher_pk):
    """Teacher classes list modal"""
    from hr.models import Teacher
    teacher = get_object_or_404(Teacher, pk=teacher_pk)
    
    class_teacher_for = Class.objects.filter(class_teacher=teacher, is_active=True)
    
    teaches_subjects = ClassSubject.objects.filter(
        teacher=teacher, is_active=True
    ).select_related('class_instance', 'subject')
    
    return render(request, 'academics/teachers/modals/classes.html', {
        'teacher': teacher,
        'class_teacher_for': class_teacher_for,
        'teaches_subjects': teaches_subjects,
    })


# =============================================================================
# REPORT MODALS
# =============================================================================

@login_required
def session_summary_report_modal(request):
    """Session summary report options modal"""
    sessions = AcademicSession.objects.filter(is_active=True)
    
    return render(request, 'academics/reports/modals/session_summary.html', {
        'sessions': sessions,
    })


@login_required
def enrollment_report_modal(request):
    """Enrollment report options modal"""
    sessions = AcademicSession.objects.filter(is_active=True)
    levels = AcademicLevel.objects.filter(is_active=True)
    
    return render(request, 'academics/reports/modals/enrollment.html', {
        'sessions': sessions,
        'levels': levels,
    })


@login_required
def attendance_report_modal(request):
    """Attendance report options modal"""
    sessions = AcademicSession.objects.filter(is_active=True)
    classes = Class.objects.filter(is_active=True)
    
    return render(request, 'academics/reports/modals/attendance.html', {
        'sessions': sessions,
        'classes': classes,
    })


@login_required
def grade_distribution_report_modal(request):
    """Grade distribution report options modal"""
    sessions = AcademicSession.objects.filter(is_active=True)
    subjects = Subject.objects.filter(is_active=True)
    
    return render(request, 'academics/reports/modals/grade_distribution.html', {
        'sessions': sessions,
        'subjects': subjects,
    })


@login_required
def class_roster_report_modal(request, class_pk):
    """Class roster report options modal"""
    class_instance = get_object_or_404(Class, pk=class_pk)
    
    return render(request, 'academics/reports/modals/class_roster.html', {
        'class': class_instance,
    })


@login_required
def teacher_assignment_report_modal(request):
    """Teacher assignment report options modal"""
    sessions = AcademicSession.objects.filter(is_active=True)
    
    return render(request, 'academics/reports/modals/teacher_assignment.html', {
        'sessions': sessions,
    })


@login_required
def promotion_analysis_report_modal(request):
    """Promotion analysis report options modal"""
    sessions = AcademicSession.objects.filter(is_active=True)
    levels = AcademicLevel.objects.filter(is_active=True)
    
    return render(request, 'academics/reports/modals/promotion_analysis.html', {
        'sessions': sessions,
        'levels': levels,
    })


# =============================================================================
# IMPORT/EXPORT MODALS
# =============================================================================

@login_required
def import_students_modal(request):
    """Import students modal"""
    return render(request, 'academics/import/modals/students.html')


@login_required
def import_subjects_modal(request):
    """Import subjects modal"""
    return render(request, 'academics/import/modals/subjects.html')


@login_required
def import_enrollments_modal(request):
    """Import enrollments modal"""
    classes = Class.objects.filter(is_active=True)
    
    return render(request, 'academics/import/modals/enrollments.html', {
        'classes': classes,
    })


@login_required
def export_options_modal(request):
    """Export options modal"""
    export_type = request.GET.get('type', 'general')
    
    return render(request, 'academics/export/modals/options.html', {
        'export_type': export_type,
    })


# =============================================================================
# SETTINGS MODALS
# =============================================================================

@login_required
def academic_settings_modal(request):
    """Academic settings modal"""
    return render(request, 'academics/settings/modals/settings.html')


@login_required
def grading_scale_modal(request):
    """Grading scale configuration modal"""
    return render(request, 'academics/settings/modals/grading_scale.html')


@login_required
def promotion_rules_modal(request):
    """Promotion rules configuration modal"""
    return render(request, 'academics/settings/modals/promotion_rules.html')


# =============================================================================
# CALENDAR MODALS
# =============================================================================

@login_required
def calendar_events_modal(request):
    """Calendar events modal"""
    year = request.GET.get('year')
    month = request.GET.get('month')
    
    holidays = Holiday.objects.filter(is_active=True)
    if year and month:
        holidays = holidays.filter(
            start_date__year=year,
            start_date__month=month
        )
    
    return render(request, 'academics/calendar/modals/events.html', {
        'holidays': holidays,
        'year': year,
        'month': month,
    })