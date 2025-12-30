# academics/modal_views.py

"""
Academic Management Modal Views (HTMX)

Handles HTMX modal operations including:
- Delete confirmations and operations
- Quick actions and forms
- Inline editing capabilities
- Bulk operations
- Status changes

All modals use HTMX for seamless UX
Uses core.utils for timezone awareness
Audit trail automatically handled by BaseModel
"""

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db import transaction
from django.db.models import Q, Count
from django.views.decorators.http import require_http_methods
import logging

# ⭐ Import timezone utilities from core (BaseModel handles audit trail automatically)
from core.utils import (
    get_school_today,
    get_school_current_time,
)

from .utils import get_current_academic_session

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

from .services import (
    ClassEnrollmentService,
    AcademicSessionService,
    ClassSubjectService,
)

logger = logging.getLogger(__name__)


# =============================================================================
# DELETE CONFIRMATION MODALS
# =============================================================================

@login_required
def academic_session_delete_modal(request, pk):
    """Show delete confirmation modal for academic session"""
    
    session = get_object_or_404(AcademicSession, pk=pk)
    
    # Check if session can be deleted
    can_delete = True
    warnings = []
    
    # Check for enrollments
    enrollment_count = session.student_class_enrollments.count()
    if enrollment_count > 0:
        can_delete = False
        warnings.append(f"Session has {enrollment_count} student enrollments")
    
    # Check for classes
    class_count = session.classes.count()
    if class_count > 0:
        can_delete = False
        warnings.append(f"Session has {class_count} classes")
    
    # Check if current or active
    if session.is_current or session.is_active:
        can_delete = False
        warnings.append("Cannot delete active or current sessions")
    
    context = {
        'object': session,
        'object_name': 'Academic Session',
        'object_title': session.name,
        'can_delete': can_delete,
        'warnings': warnings,
        'delete_url': 'academics:session_delete',
    }
    
    return render(request, 'academics/modals/delete_confirmation.html', context)


@login_required
@require_http_methods(["POST"])
def academic_session_delete(request, pk):
    """Delete academic session via HTMX"""
    
    session = get_object_or_404(AcademicSession, pk=pk)
    session_name = session.name
    
    # Final validation
    if session.is_current or session.is_active:
        return JsonResponse({
            'success': False,
            'message': 'Cannot delete active or current sessions'
        })
    
    if session.student_class_enrollments.exists() or session.classes.exists():
        return JsonResponse({
            'success': False,
            'message': 'Cannot delete session with enrollments or classes'
        })
    
    try:
        session.delete()
        
        messages.success(request, f'Academic session "{session_name}" deleted successfully.')
        
        return JsonResponse({
            'success': True,
            'message': f'Academic session "{session_name}" deleted successfully.',
            'redirect': '/academics/sessions/'
        })
        
    except Exception as e:
        logger.error(f"Error deleting session: {e}")
        return JsonResponse({
            'success': False,
            'message': f'Error deleting session: {str(e)}'
        })


@login_required
def subject_delete_modal(request, pk):
    """Show delete confirmation modal for subject"""
    
    subject = get_object_or_404(Subject, pk=pk)
    
    # Check if subject can be deleted
    can_delete = True
    warnings = []
    
    # Check for class assignments
    assignment_count = subject.classes.filter(is_active=True).count()
    if assignment_count > 0:
        can_delete = False
        warnings.append(f"Subject is assigned to {assignment_count} active classes")
    
    # Check for prerequisites
    prerequisite_count = Subject.objects.filter(prerequisites=subject).count()
    if prerequisite_count > 0:
        warnings.append(f"Subject is a prerequisite for {prerequisite_count} other subjects")
    
    context = {
        'object': subject,
        'object_name': 'Subject',
        'object_title': subject.name,
        'can_delete': can_delete,
        'warnings': warnings,
        'delete_url': 'academics:subject_delete',
    }
    
    return render(request, 'academics/modals/delete_confirmation.html', context)


@login_required
@require_http_methods(["POST"])
def subject_delete(request, pk):
    """Delete subject via HTMX"""
    
    subject = get_object_or_404(Subject, pk=pk)
    subject_name = subject.name
    
    # Final validation
    if subject.classes.filter(is_active=True).exists():
        return JsonResponse({
            'success': False,
            'message': 'Cannot delete subject assigned to active classes'
        })
    
    try:
        subject.delete()
        
        messages.success(request, f'Subject "{subject_name}" deleted successfully.')
        
        return JsonResponse({
            'success': True,
            'message': f'Subject "{subject_name}" deleted successfully.',
            'redirect': '/academics/subjects/'
        })
        
    except Exception as e:
        logger.error(f"Error deleting subject: {e}")
        return JsonResponse({
            'success': False,
            'message': f'Error deleting subject: {str(e)}'
        })


@login_required
def enrollment_delete_modal(request, pk):
    """Show delete confirmation modal for student enrollment"""
    
    enrollment = get_object_or_404(
        StudentClassEnrollment.objects.select_related('student', 'class_instance'),
        pk=pk
    )
    
    # Check if enrollment can be deleted
    can_delete = True
    warnings = []
    
    # Check completion status
    if enrollment.completion_status != 'ONGOING':
        warnings.append(f"Enrollment is {enrollment.get_completion_status_display()}")
    
    # Check for invoice
    if enrollment.academic_invoice:
        if enrollment.academic_invoice.status == 'PAID':
            can_delete = False
            warnings.append("Enrollment has paid invoice - use withdrawal instead")
        else:
            warnings.append("Enrollment has unpaid invoice that will be cancelled")
    
    # Check for progress records
    progress_count = enrollment.progress_records.count()
    if progress_count > 0:
        warnings.append(f"Enrollment has {progress_count} academic progress records")
    
    context = {
        'object': enrollment,
        'object_name': 'Student Enrollment',
        'object_title': f'{enrollment.student.get_full_name()} - {enrollment.class_instance}',
        'can_delete': can_delete,
        'warnings': warnings,
        'delete_url': 'academics:enrollment_delete',
        'alternative_action': 'Consider using withdrawal instead of deletion',
    }
    
    return render(request, 'academics/modals/delete_confirmation.html', context)


@login_required
@require_http_methods(["POST"])
def enrollment_delete(request, pk):
    """Delete student enrollment via HTMX"""
    
    enrollment = get_object_or_404(StudentClassEnrollment, pk=pk)
    student_name = enrollment.student.get_full_name()
    class_name = str(enrollment.class_instance)
    
    # Final validation
    if enrollment.academic_invoice and enrollment.academic_invoice.status == 'PAID':
        return JsonResponse({
            'success': False,
            'message': 'Cannot delete enrollment with paid invoice'
        })
    
    try:
        # Cancel unpaid invoice if exists
        if enrollment.academic_invoice and enrollment.academic_invoice.status in ['PENDING', 'OVERDUE']:
            enrollment.academic_invoice.status = 'CANCELLED'
            enrollment.academic_invoice.save()
        
        enrollment.delete()
        
        messages.success(request, f'Enrollment for "{student_name}" in {class_name} deleted successfully.')
        
        return JsonResponse({
            'success': True,
            'message': f'Enrollment deleted successfully.',
            'redirect': '/academics/enrollments/'
        })
        
    except Exception as e:
        logger.error(f"Error deleting enrollment: {e}")
        return JsonResponse({
            'success': False,
            'message': f'Error deleting enrollment: {str(e)}'
        })


# =============================================================================
# QUICK ACTION MODALS
# =============================================================================

@login_required
def session_set_current_modal(request, pk):
    """Modal to set session as current"""
    
    session = get_object_or_404(AcademicSession, pk=pk)
    
    # Check if session can be made current
    can_set_current = True
    warnings = []
    
    # ⭐ Check against school timezone
    today = get_school_today()
    
    if today < session.start_date:
        warnings.append("Session hasn't started yet")
    elif today > session.end_date:
        warnings.append("Session has already ended")
    
    if session.is_academically_closed:
        can_set_current = False
        warnings.append("Cannot make closed session current")
    
    if not session.is_active:
        warnings.append("Session is not active")
    
    context = {
        'session': session,
        'can_set_current': can_set_current,
        'warnings': warnings,
        'today': today,
    }
    
    return render(request, 'academics/modals/set_current_session.html', context)


@login_required
@require_http_methods(["POST"])
def session_set_current(request, pk):
    """Set session as current via HTMX"""
    
    session = get_object_or_404(AcademicSession, pk=pk)
    
    try:
        # Remove current flag from all sessions
        AcademicSession.objects.filter(is_current=True).update(is_current=False)
        
        # Set this session as current
        session.is_current = True
        session.save()
        
        messages.success(request, f'"{session.name}" is now the current academic session.')
        
        return JsonResponse({
            'success': True,
            'message': f'Current session updated to "{session.name}"',
        })
        
    except Exception as e:
        logger.error(f"Error setting current session: {e}")
        return JsonResponse({
            'success': False,
            'message': f'Error setting current session: {str(e)}'
        })


@login_required
def bulk_enrollment_modal(request):
    """Modal for bulk student enrollment"""
    
    # Get available classes and sessions
    current_session = get_current_academic_session
    active_sessions = AcademicSession.objects.filter(is_active=True).order_by('-start_date')
    
    available_classes = Class.objects.filter(
        academic_session__in=active_sessions,
        is_active=True
    ).select_related('academic_level', 'academic_session')
    
    # Get students available for enrollment
    from students.models import Student
    available_students = Student.objects.filter(
        enrollment_status='ACTIVE'
    ).exclude(
        class_enrollments__is_active=True,
        class_enrollments__completion_status='ONGOING'
    ).order_by('last_name', 'first_name')[:50]  # Limit for performance
    
    context = {
        'current_session': current_session,
        'active_sessions': active_sessions,
        'available_classes': available_classes,
        'available_students': available_students,
    }
    
    return render(request, 'academics/modals/bulk_enrollment.html', context)


@login_required
@require_http_methods(["POST"])
def bulk_enrollment_process(request):
    """Process bulk enrollment via HTMX"""
    
    try:
        student_ids = request.POST.getlist('students')
        class_id = request.POST.get('class_instance')
        session_id = request.POST.get('academic_session')
        enrollment_type = request.POST.get('enrollment_type', 'BULK')
        
        if not student_ids or not class_id or not session_id:
            return JsonResponse({
                'success': False,
                'message': 'Missing required fields'
            })
        
        # Get objects
        from students.models import Student
        students = Student.objects.filter(id__in=student_ids)
        class_instance = Class.objects.get(pk=class_id)
        session = AcademicSession.objects.get(pk=session_id)
        
        # Use bulk enrollment service
        from .services import BulkEnrollmentService
        
        results = BulkEnrollmentService.bulk_enroll_students(
            students=students,
            class_instance=class_instance,
            session=session,
            enrollment_type=enrollment_type
        )
        
        message = f"Bulk enrollment completed: {len(results['enrolled'])} enrolled, {len(results['failed'])} failed"
        
        if results['failed']:
            message += f". Failures: {', '.join([f['student'].get_full_name() for f in results['failed'][:3]])}"
            if len(results['failed']) > 3:
                message += f" and {len(results['failed']) - 3} others"
        
        messages.success(request, message)
        
        return JsonResponse({
            'success': True,
            'message': message,
            'results': {
                'enrolled_count': len(results['enrolled']),
                'failed_count': len(results['failed']),
                'total_count': results['total']
            }
        })
        
    except Exception as e:
        logger.error(f"Error in bulk enrollment: {e}")
        return JsonResponse({
            'success': False,
            'message': f'Bulk enrollment failed: {str(e)}'
        })


# =============================================================================
# STATUS CHANGE MODALS
# =============================================================================

@login_required
def enrollment_status_change_modal(request, pk):
    """Modal to change enrollment status"""
    
    enrollment = get_object_or_404(
        StudentClassEnrollment.objects.select_related('student', 'class_instance'),
        pk=pk
    )
    
    # Available status transitions
    current_status = enrollment.completion_status
    available_statuses = []
    
    if current_status == 'ONGOING':
        available_statuses = [
            ('COMPLETED', 'Mark as Completed'),
            ('TRANSFERRED', 'Mark as Transferred'),
            ('WITHDRAWN', 'Mark as Withdrawn'),
            ('DROPPED', 'Mark as Dropped'),
            ('SUSPENDED', 'Mark as Suspended'),
        ]
    elif current_status in ['SUSPENDED', 'TRANSFERRED']:
        available_statuses = [
            ('ONGOING', 'Reactivate Enrollment'),
        ]
    
    context = {
        'enrollment': enrollment,
        'current_status': current_status,
        'available_statuses': available_statuses,
    }
    
    return render(request, 'academics/modals/enrollment_status_change.html', context)


@login_required
@require_http_methods(["POST"])
def enrollment_status_change(request, pk):
    """Change enrollment status via HTMX"""
    
    enrollment = get_object_or_404(StudentClassEnrollment, pk=pk)
    
    try:
        new_status = request.POST.get('new_status')
        reason = request.POST.get('reason', '')
        
        old_status = enrollment.completion_status
        enrollment.completion_status = new_status
        
        # ⭐ Set completion date if completing
        if new_status in ['COMPLETED', 'WITHDRAWN', 'DROPPED'] and not enrollment.completion_date:
            enrollment.completion_date = get_school_today()
        
        # Update active status
        enrollment.is_active = (new_status == 'ONGOING')
        
        # Add note
        if reason:
            note = f"\nStatus changed from {old_status} to {new_status}: {reason}"
            enrollment.enrollment_notes = (enrollment.enrollment_notes or '') + note
        
        enrollment.save() 
        
        messages.success(
            request, 
            f'Enrollment status changed from {old_status} to {new_status} for {enrollment.student.get_full_name()}'
        )
        
        return JsonResponse({
            'success': True,
            'message': f'Status updated to {new_status}',
        })
        
    except Exception as e:
        logger.error(f"Error changing enrollment status: {e}")
        return JsonResponse({
            'success': False,
            'message': f'Error changing status: {str(e)}'
        })


# =============================================================================
# QUICK EDIT MODALS
# =============================================================================

@login_required
def enrollment_roll_number_modal(request, pk):
    """Modal to edit enrollment roll number"""
    
    enrollment = get_object_or_404(
        StudentClassEnrollment.objects.select_related('student', 'class_instance'),
        pk=pk
    )
    
    # Get existing roll numbers in the class to avoid duplicates
    existing_roll_numbers = StudentClassEnrollment.objects.filter(
        class_instance=enrollment.class_instance,
        academic_session=enrollment.academic_session,
        is_active=True
    ).exclude(pk=pk).values_list('roll_number', flat=True)
    
    context = {
        'enrollment': enrollment,
        'existing_roll_numbers': list(existing_roll_numbers),
    }
    
    return render(request, 'academics/modals/edit_roll_number.html', context)


@login_required
@require_http_methods(["POST"])
def enrollment_roll_number_update(request, pk):
    """Update enrollment roll number via HTMX"""
    
    enrollment = get_object_or_404(StudentClassEnrollment, pk=pk)
    
    try:
        new_roll_number = request.POST.get('roll_number', '').strip()
        
        # Validate uniqueness
        if new_roll_number:
            existing = StudentClassEnrollment.objects.filter(
                class_instance=enrollment.class_instance,
                academic_session=enrollment.academic_session,
                roll_number=new_roll_number,
                is_active=True
            ).exclude(pk=pk).exists()
            
            if existing:
                return JsonResponse({
                    'success': False,
                    'message': f'Roll number {new_roll_number} is already assigned to another student'
                })
        
        old_roll_number = enrollment.roll_number
        enrollment.roll_number = new_roll_number
        enrollment.save()
        
        messages.success(
            request, 
            f'Roll number updated for {enrollment.student.get_full_name()}: {old_roll_number} → {new_roll_number}'
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Roll number updated successfully',
            'new_roll_number': new_roll_number
        })
        
    except Exception as e:
        logger.error(f"Error updating roll number: {e}")
        return JsonResponse({
            'success': False,
            'message': f'Error updating roll number: {str(e)}'
        })


# =============================================================================
# ACADEMIC LEVEL DELETE MODALS
# =============================================================================

@login_required
def academic_level_delete_modal(request, pk):
    """Show delete confirmation modal for academic level"""
    
    level = get_object_or_404(AcademicLevel, pk=pk)
    
    # Check if level can be deleted
    can_delete = True
    warnings = []
    
    # Check for classes
    class_count = level.classes.filter(is_active=True).count()
    if class_count > 0:
        can_delete = False
        warnings.append(f"Academic level has {class_count} active classes")
    
    # Check for students
    from students.models import Student
    student_count = Student.objects.filter(current_academic_level=level).count()
    if student_count > 0:
        can_delete = False
        warnings.append(f"Academic level has {student_count} students")
    
    # Check for subjects
    subject_count = level.applicable_subjects.count()
    if subject_count > 0:
        warnings.append(f"Academic level has {subject_count} applicable subjects")
    
    context = {
        'object': level,
        'object_name': 'Academic Level',
        'object_title': level.name,
        'can_delete': can_delete,
        'warnings': warnings,
        'delete_url': 'academics:level_delete',
    }
    
    return render(request, 'academics/modals/delete_confirmation.html', context)


@login_required
@require_http_methods(["POST"])
def academic_level_delete(request, pk):
    """Delete academic level via HTMX"""
    
    level = get_object_or_404(AcademicLevel, pk=pk)
    level_name = level.name
    
    # Final validation
    if level.classes.filter(is_active=True).exists():
        return JsonResponse({
            'success': False,
            'message': 'Cannot delete academic level with active classes'
        })
    
    from students.models import Student
    if Student.objects.filter(current_academic_level=level).exists():
        return JsonResponse({
            'success': False,
            'message': 'Cannot delete academic level with assigned students'
        })
    
    try:
        level.delete()
        
        messages.success(request, f'Academic level "{level_name}" deleted successfully.')
        
        return JsonResponse({
            'success': True,
            'message': f'Academic level "{level_name}" deleted successfully.',
            'redirect': '/academics/levels/'
        })
        
    except Exception as e:
        logger.error(f"Error deleting academic level: {e}")
        return JsonResponse({
            'success': False,
            'message': f'Error deleting academic level: {str(e)}'
        })


# =============================================================================
# CLASSROOM DELETE MODALS
# =============================================================================

@login_required
def classroom_delete_modal(request, pk):
    """Show delete confirmation modal for classroom"""
    
    classroom = get_object_or_404(ClassRoom, pk=pk)
    
    # Check if classroom can be deleted
    can_delete = True
    warnings = []
    
    # Check for assigned classes
    class_count = classroom.assigned_classes.filter(is_active=True).count()
    if class_count > 0:
        can_delete = False
        warnings.append(f"Classroom is assigned to {class_count} active classes")
    
    # Check for bookings (if booking system exists)
    try:
        booking_count = classroom.bookings.filter(
            status='CONFIRMED',
            start_time__gte=get_school_today()
        ).count()
        if booking_count > 0:
            warnings.append(f"Classroom has {booking_count} future bookings")
    except:
        pass  # Booking system might not exist
    
    context = {
        'object': classroom,
        'object_name': 'Classroom',
        'object_title': classroom.name,
        'can_delete': can_delete,
        'warnings': warnings,
        'delete_url': 'academics:classroom_delete',
    }
    
    return render(request, 'academics/modals/delete_confirmation.html', context)


@login_required
@require_http_methods(["POST"])
def classroom_delete(request, pk):
    """Delete classroom via HTMX"""
    
    classroom = get_object_or_404(ClassRoom, pk=pk)
    classroom_name = classroom.name
    
    # Final validation
    if classroom.assigned_classes.filter(is_active=True).exists():
        return JsonResponse({
            'success': False,
            'message': 'Cannot delete classroom assigned to active classes'
        })
    
    try:
        classroom.delete()
        
        messages.success(request, f'Classroom "{classroom_name}" deleted successfully.')
        
        return JsonResponse({
            'success': True,
            'message': f'Classroom "{classroom_name}" deleted successfully.',
            'redirect': '/academics/classrooms/'
        })
        
    except Exception as e:
        logger.error(f"Error deleting classroom: {e}")
        return JsonResponse({
            'success': False,
            'message': f'Error deleting classroom: {str(e)}'
        })


# =============================================================================
# CLASS DELETE MODALS
# =============================================================================

@login_required
def class_delete_modal(request, pk):
    """Show delete confirmation modal for class"""
    
    class_instance = get_object_or_404(Class, pk=pk)
    
    # Check if class can be deleted
    can_delete = True
    warnings = []
    
    # Check for enrollments
    enrollment_count = class_instance.enrollments.filter(is_active=True).count()
    if enrollment_count > 0:
        can_delete = False
        warnings.append(f"Class has {enrollment_count} active student enrollments")
    
    # Check for subject assignments
    subject_count = class_instance.subjects.filter(is_active=True).count()
    if subject_count > 0:
        can_delete = False
        warnings.append(f"Class has {subject_count} subject assignments")
    
    # Check for progress records
    progress_count = class_instance.progress_records.count()
    if progress_count > 0:
        warnings.append(f"Class has {progress_count} academic progress records")
    
    context = {
        'object': class_instance,
        'object_name': 'Class',
        'object_title': str(class_instance),
        'can_delete': can_delete,
        'warnings': warnings,
        'delete_url': 'academics:class_delete',
    }
    
    return render(request, 'academics/modals/delete_confirmation.html', context)


@login_required
@require_http_methods(["POST"])
def class_delete(request, pk):
    """Delete class via HTMX"""
    
    class_instance = get_object_or_404(Class, pk=pk)
    class_name = str(class_instance)
    
    # Final validation
    if class_instance.enrollments.filter(is_active=True).exists():
        return JsonResponse({
            'success': False,
            'message': 'Cannot delete class with active enrollments'
        })
    
    if class_instance.subjects.filter(is_active=True).exists():
        return JsonResponse({
            'success': False,
            'message': 'Cannot delete class with active subject assignments'
        })
    
    try:
        class_instance.delete()
        
        messages.success(request, f'Class "{class_name}" deleted successfully.')
        
        return JsonResponse({
            'success': True,
            'message': f'Class "{class_name}" deleted successfully.',
            'redirect': '/academics/classes/'
        })
        
    except Exception as e:
        logger.error(f"Error deleting class: {e}")
        return JsonResponse({
            'success': False,
            'message': f'Error deleting class: {str(e)}'
        })


# =============================================================================
# CLASS SUBJECT DELETE MODALS
# =============================================================================

@login_required
def class_subject_delete_modal(request, pk):
    """Show delete confirmation modal for class subject"""
    
    class_subject = get_object_or_404(
        ClassSubject.objects.select_related('class_instance', 'subject', 'teacher'),
        pk=pk
    )
    
    # Check if class subject can be deleted
    can_delete = True
    warnings = []
    
    # Check for grades/assessments (if grading system exists)
    try:
        grade_count = class_subject.grades.count()
        if grade_count > 0:
            warnings.append(f"Subject assignment has {grade_count} student grades")
    except:
        pass  # Grading system might not exist
    
    # Check for timetable entries (if timetable system exists)
    try:
        timetable_count = class_subject.timetable_entries.count()
        if timetable_count > 0:
            warnings.append(f"Subject has {timetable_count} timetable entries")
    except:
        pass  # Timetable system might not exist
    
    context = {
        'object': class_subject,
        'object_name': 'Class Subject Assignment',
        'object_title': f'{class_subject.subject.name} - {class_subject.class_instance}',
        'can_delete': can_delete,
        'warnings': warnings,
        'delete_url': 'academics:class_subject_delete',
    }
    
    return render(request, 'academics/modals/delete_confirmation.html', context)


@login_required
@require_http_methods(["POST"])
def class_subject_delete(request, pk):
    """Delete class subject via HTMX"""
    
    class_subject = get_object_or_404(ClassSubject, pk=pk)
    subject_name = class_subject.subject.name
    class_name = str(class_subject.class_instance)
    
    try:
        class_subject.delete()
        
        messages.success(request, f'Subject "{subject_name}" removed from {class_name} successfully.')
        
        return JsonResponse({
            'success': True,
            'message': f'Subject assignment deleted successfully.',
            'redirect': '/academics/class-subjects/'
        })
        
    except Exception as e:
        logger.error(f"Error deleting class subject: {e}")
        return JsonResponse({
            'success': False,
            'message': f'Error deleting subject assignment: {str(e)}'
        })


# =============================================================================
# ACADEMIC PROGRESS DELETE MODALS
# =============================================================================

@login_required
def academic_progress_delete_modal(request, pk):
    """Show delete confirmation modal for academic progress"""
    
    progress = get_object_or_404(
        AcademicProgress.objects.select_related('student', 'academic_session'),
        pk=pk
    )
    
    # Check if progress can be deleted
    can_delete = True
    warnings = []
    
    # Check if finalized
    if progress.is_final:
        can_delete = False
        warnings.append("Cannot delete finalized progress records")
    
    # Check if used for promotion
    if progress.promotion_decision and progress.promotion_decision != 'PENDING':
        warnings.append(f"Progress record has promotion decision: {progress.get_promotion_decision_display()}")
    
    context = {
        'object': progress,
        'object_name': 'Academic Progress',
        'object_title': f'{progress.student.get_full_name()} - {progress.academic_session}',
        'can_delete': can_delete,
        'warnings': warnings,
        'delete_url': 'academics:progress_delete',
    }
    
    return render(request, 'academics/modals/delete_confirmation.html', context)


@login_required
@require_http_methods(["POST"])
def academic_progress_delete(request, pk):
    """Delete academic progress via HTMX"""
    
    progress = get_object_or_404(AcademicProgress, pk=pk)
    student_name = progress.student.get_full_name()
    session_name = str(progress.academic_session)
    
    # Final validation
    if progress.is_final:
        return JsonResponse({
            'success': False,
            'message': 'Cannot delete finalized progress records'
        })
    
    try:
        progress.delete()
        
        messages.success(request, f'Academic progress for "{student_name}" in {session_name} deleted successfully.')
        
        return JsonResponse({
            'success': True,
            'message': f'Progress record deleted successfully.',
            'redirect': '/academics/progress/'
        })
        
    except Exception as e:
        logger.error(f"Error deleting academic progress: {e}")
        return JsonResponse({
            'success': False,
            'message': f'Error deleting progress record: {str(e)}'
        })


@login_required
def academic_progress_finalize_modal(request, pk):
    """Modal to finalize academic progress"""
    
    progress = get_object_or_404(
        AcademicProgress.objects.select_related('student', 'academic_session'),
        pk=pk
    )
    
    # Check if progress can be finalized
    can_finalize = True
    warnings = []
    
    if progress.is_final:
        can_finalize = False
        warnings.append("Progress record is already finalized")
    
    if not progress.gpa:
        warnings.append("GPA is not calculated")
    
    if not progress.attendance_percentage:
        warnings.append("Attendance percentage is not recorded")
    
    context = {
        'progress': progress,
        'can_finalize': can_finalize,
        'warnings': warnings,
    }
    
    return render(request, 'academics/modals/finalize_progress.html', context)


@login_required
@require_http_methods(["POST"])
def academic_progress_finalize(request, pk):
    """Finalize academic progress via HTMX"""
    
    progress = get_object_or_404(AcademicProgress, pk=pk)
    
    try:
        from .services import AcademicProgressService
        
        finalized_progress = AcademicProgressService.finalize_session_progress(
            progress, 
            finalized_by=request.user
        )
        
        messages.success(
            request, 
            f'Academic progress for {progress.student.get_full_name()} finalized successfully!'
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Progress record finalized successfully',
        })
        
    except Exception as e:
        logger.error(f"Error finalizing progress: {e}")
        return JsonResponse({
            'success': False,
            'message': f'Error finalizing progress: {str(e)}'
        })


# =============================================================================
# HOLIDAY DELETE MODALS
# =============================================================================

@login_required
def holiday_delete_modal(request, pk):
    """Show delete confirmation modal for holiday"""
    
    holiday = get_object_or_404(Holiday, pk=pk)
    
    # Check if holiday can be deleted
    can_delete = True
    warnings = []
    
    # Check if holiday is in the past
    today = get_school_today()
    if holiday.start_date < today:
        warnings.append("Holiday has already started/passed")
    
    # Check if recurring
    if holiday.is_recurring:
        warnings.append("This is a recurring holiday")
    
    context = {
        'object': holiday,
        'object_name': 'Holiday',
        'object_title': holiday.name,
        'can_delete': can_delete,
        'warnings': warnings,
        'delete_url': 'academics:holiday_delete',
    }
    
    return render(request, 'academics/modals/delete_confirmation.html', context)


@login_required
@require_http_methods(["POST"])
def holiday_delete(request, pk):
    """Delete holiday via HTMX"""
    
    holiday = get_object_or_404(Holiday, pk=pk)
    holiday_name = holiday.name
    
    try:
        holiday.delete()
        
        messages.success(request, f'Holiday "{holiday_name}" deleted successfully.')
        
        return JsonResponse({
            'success': True,
            'message': f'Holiday "{holiday_name}" deleted successfully.',
            'redirect': '/academics/holidays/'
        })
        
    except Exception as e:
        logger.error(f"Error deleting holiday: {e}")
        return JsonResponse({
            'success': False,
            'message': f'Error deleting holiday: {str(e)}'
        })


# =============================================================================
# ADDITIONAL UTILITY MODALS
# =============================================================================

@login_required
def class_capacity_modal(request, pk):
    """Modal to view class capacity details"""
    
    class_instance = get_object_or_404(
        Class.objects.select_related('academic_level', 'academic_session'),
        pk=pk
    )
    
    # Get capacity information
    from .utils import get_class_capacity_summary
    capacity_info = get_class_capacity_summary(class_instance)
    
    # Get enrolled students
    enrollments = class_instance.enrollments.filter(
        is_active=True,
        completion_status='ONGOING'
    ).select_related('student').order_by('roll_number', 'student__last_name')
    
    context = {
        'class': class_instance,
        'capacity_info': capacity_info,
        'enrollments': enrollments,
    }
    
    return render(request, 'academics/modals/class_capacity.html', context)


@login_required
def student_enrollment_history_modal(request, student_id):
    """Modal to view student's enrollment history"""
    
    from students.models import Student
    student = get_object_or_404(Student, pk=student_id)
    
    # Get enrollment history
    enrollments = StudentClassEnrollment.objects.filter(
        student=student
    ).select_related(
        'class_instance__academic_level',
        'academic_session'
    ).order_by('-enrollment_date')
    
    context = {
        'student': student,
        'enrollments': enrollments,
    }
    
    return render(request, 'academics/modals/enrollment_history.html', context)


@login_required
def session_statistics_modal(request, pk):
    """Modal to view detailed session statistics"""
    
    session = get_object_or_404(AcademicSession, pk=pk)
    
    # Get session statistics
    try:
        from .stats import get_enrollment_summary_by_session
        session_stats = get_enrollment_summary_by_session(session)
    except Exception as e:
        logger.error(f"Error getting session stats: {e}")
        session_stats = {}
    
    context = {
        'session': session,
        'stats': session_stats,
    }
    
    return render(request, 'academics/modals/session_statistics.html', context)