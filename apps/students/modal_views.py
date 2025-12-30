# students/modal_views.py

"""
Student Management Modal Views (HTMX)

Handles HTMX modal operations including:
- Delete confirmations and operations
- Quick actions and forms
- Inline editing capabilities
- Bulk operations
- Status changes
- Guardian assignment modals

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

from core.utils import get_school_today

from .models import (
    Student,
    Guardian,
    StudentGuardian,
    SiblingRelationship,
    EnrollmentStatusHistory,
)

logger = logging.getLogger(__name__)


# =============================================================================
# STUDENT DELETE MODALS
# =============================================================================

@login_required
def student_delete_modal(request, pk):
    """Show delete confirmation modal for student"""
    
    student = get_object_or_404(Student, pk=pk)
    
    # Check if student can be deleted
    can_delete = True
    warnings = []
    
    # Check enrollment status
    if student.enrollment_status == 'ACTIVE':
        can_delete = False
        warnings.append("Cannot delete active students. Please change status first.")
    
    # Check for guardians
    guardian_count = student.guardians.count()
    if guardian_count > 0:
        warnings.append(f"Student has {guardian_count} guardian(s) that will be unlinked")
    
    # Check for siblings
    sibling_count = student.sibling_relationships.count() + student.reverse_sibling_relationships.count()
    if sibling_count > 0:
        warnings.append(f"Student has {sibling_count} sibling relationship(s) that will be removed")
    
    # Check for class enrollments
    if hasattr(student, 'class_enrollments'):
        enrollment_count = student.class_enrollments.count()
        if enrollment_count > 0:
            can_delete = False
            warnings.append(f"Student has {enrollment_count} class enrollment(s). Cannot delete.")
    
    # Check for invoices/payments
    if hasattr(student, 'invoices'):
        invoice_count = student.invoices.count()
        if invoice_count > 0:
            can_delete = False
            warnings.append(f"Student has {invoice_count} financial record(s). Cannot delete.")
    
    context = {
        'object': student,
        'object_name': 'Student',
        'object_title': student.get_full_name(),
        'can_delete': can_delete,
        'warnings': warnings,
        'delete_url': 'students:student_delete',
    }
    
    return render(request, 'students/modals/delete_confirmation.html', context)


@login_required
@require_http_methods(["POST"])
def student_delete(request, pk):
    """Delete student via HTMX"""
    
    student = get_object_or_404(Student, pk=pk)
    student_name = student.get_full_name()
    
    # Final validation
    if student.enrollment_status == 'ACTIVE':
        return JsonResponse({
            'success': False,
            'message': 'Cannot delete active students'
        })
    
    # Check for class enrollments
    if hasattr(student, 'class_enrollments') and student.class_enrollments.exists():
        return JsonResponse({
            'success': False,
            'message': 'Cannot delete student with class enrollments'
        })
    
    try:
        student.delete()
        
        messages.success(request, f'Student "{student_name}" deleted successfully.')
        
        return JsonResponse({
            'success': True,
            'message': f'Student "{student_name}" deleted successfully.',
            'redirect': '/students/'
        })
        
    except Exception as e:
        logger.error(f"Error deleting student: {e}")
        return JsonResponse({
            'success': False,
            'message': f'Error deleting student: {str(e)}'
        })


# =============================================================================
# GUARDIAN DELETE MODALS
# =============================================================================

@login_required
def guardian_delete_modal(request, pk):
    """Show delete confirmation modal for guardian"""
    
    guardian = get_object_or_404(Guardian, pk=pk)
    
    # Check if guardian can be deleted
    can_delete = True
    warnings = []
    
    # Check for students
    student_count = guardian.students.count()
    if student_count > 0:
        can_delete = False
        warnings.append(f"Guardian has {student_count} student(s). Remove relationships first.")
    
    # Check if primary guardian
    primary_count = guardian.student_relationships.filter(is_primary=True).count()
    if primary_count > 0:
        can_delete = False
        warnings.append(f"Guardian is primary guardian for {primary_count} student(s)")
    
    context = {
        'object': guardian,
        'object_name': 'Guardian',
        'object_title': guardian.get_full_name(),
        'can_delete': can_delete,
        'warnings': warnings,
        'delete_url': 'students:guardian_delete',
    }
    
    return render(request, 'students/modals/delete_confirmation.html', context)


@login_required
@require_http_methods(["POST"])
def guardian_delete(request, pk):
    """Delete guardian via HTMX"""
    
    guardian = get_object_or_404(Guardian, pk=pk)
    guardian_name = guardian.get_full_name()
    
    # Final validation
    if guardian.students.exists():
        return JsonResponse({
            'success': False,
            'message': 'Cannot delete guardian with active student relationships'
        })
    
    try:
        guardian.delete()
        
        messages.success(request, f'Guardian "{guardian_name}" deleted successfully.')
        
        return JsonResponse({
            'success': True,
            'message': f'Guardian "{guardian_name}" deleted successfully.',
            'redirect': '/students/guardians/'
        })
        
    except Exception as e:
        logger.error(f"Error deleting guardian: {e}")
        return JsonResponse({
            'success': False,
            'message': f'Error deleting guardian: {str(e)}'
        })


# =============================================================================
# STUDENT-GUARDIAN RELATIONSHIP MODALS
# =============================================================================

@login_required
def guardian_relationship_delete_modal(request, pk):
    """Show delete confirmation modal for guardian relationship"""
    
    relationship = get_object_or_404(
        StudentGuardian.objects.select_related('student', 'guardian'),
        pk=pk
    )
    
    # Check if relationship can be deleted
    can_delete = True
    warnings = []
    
    # Check if primary guardian
    if relationship.is_primary:
        warnings.append("This is the primary guardian relationship")
    
    # Check if last guardian
    guardian_count = relationship.student.guardians.count()
    if guardian_count == 1:
        warnings.append("This is the student's only guardian")
    
    # Check if emergency contact
    if relationship.emergency_contact_priority <= 5:
        warnings.append("This guardian is an emergency contact")
    
    context = {
        'object': relationship,
        'object_name': 'Guardian Relationship',
        'object_title': f'{relationship.guardian.get_full_name()} - {relationship.student.get_full_name()}',
        'can_delete': can_delete,
        'warnings': warnings,
        'delete_url': 'students:guardian_relationship_delete',
    }
    
    return render(request, 'students/modals/delete_confirmation.html', context)


@login_required
@require_http_methods(["POST"])
def guardian_relationship_delete(request, pk):
    """Delete guardian relationship via HTMX"""
    
    relationship = get_object_or_404(StudentGuardian, pk=pk)
    student = relationship.student
    guardian = relationship.guardian
    
    try:
        relationship.delete()
        
        messages.success(
            request,
            f'Guardian relationship removed: {guardian.get_full_name()} - {student.get_full_name()}'
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Guardian relationship removed successfully.',
            'redirect': f'/students/{student.pk}/'
        })
        
    except Exception as e:
        logger.error(f"Error deleting relationship: {e}")
        return JsonResponse({
            'success': False,
            'message': f'Error deleting relationship: {str(e)}'
        })


# =============================================================================
# SIBLING RELATIONSHIP MODALS
# =============================================================================

@login_required
def sibling_relationship_delete_modal(request, pk):
    """Show delete confirmation modal for sibling relationship"""
    
    relationship = get_object_or_404(
        SiblingRelationship.objects.select_related('from_student', 'to_student'),
        pk=pk
    )
    
    can_delete = True
    warnings = []
    
    # Check if reciprocal relationship exists
    reciprocal = SiblingRelationship.objects.filter(
        from_student=relationship.to_student,
        to_student=relationship.from_student
    ).first()
    
    if reciprocal:
        warnings.append("Reciprocal relationship will also be deleted")
    
    context = {
        'object': relationship,
        'object_name': 'Sibling Relationship',
        'object_title': f'{relationship.from_student.get_full_name()} - {relationship.to_student.get_full_name()}',
        'can_delete': can_delete,
        'warnings': warnings,
        'delete_url': 'students:sibling_relationship_delete',
    }
    
    return render(request, 'students/modals/delete_confirmation.html', context)


@login_required
@require_http_methods(["POST"])
def sibling_relationship_delete(request, pk):
    """Delete sibling relationship via HTMX"""
    
    relationship = get_object_or_404(SiblingRelationship, pk=pk)
    from_student = relationship.from_student
    
    try:
        # Signal will handle reciprocal deletion
        relationship.delete()
        
        messages.success(request, 'Sibling relationship removed successfully.')
        
        return JsonResponse({
            'success': True,
            'message': 'Sibling relationship removed successfully.',
            'redirect': f'/students/{from_student.pk}/'
        })
        
    except Exception as e:
        logger.error(f"Error deleting sibling relationship: {e}")
        return JsonResponse({
            'success': False,
            'message': f'Error deleting relationship: {str(e)}'
        })


# =============================================================================
# QUICK ACTION MODALS
# =============================================================================

@login_required
def student_status_change_modal(request, pk):
    """Modal for changing student enrollment status"""
    
    student = get_object_or_404(Student, pk=pk)
    
    context = {
        'student': student,
        'status_choices': Student.ENROLLMENT_STATUS_CHOICES,
    }
    
    return render(request, 'students/modals/status_change.html', context)


@login_required
@require_http_methods(["POST"])
def student_status_change(request, pk):
    """Change student enrollment status via HTMX"""
    
    student = get_object_or_404(Student, pk=pk)
    new_status = request.POST.get('new_status')
    reason = request.POST.get('reason', '')
    
    if not new_status:
        return JsonResponse({
            'success': False,
            'message': 'Please select a status'
        })
    
    try:
        old_status = student.enrollment_status
        student.enrollment_status = new_status
        student.save()
        
        # Create history record (if not already created by signal)
        if not EnrollmentStatusHistory.objects.filter(
            student=student,
            previous_status=old_status,
            new_status=new_status,
            effective_date=get_school_today()
        ).exists():
            EnrollmentStatusHistory.objects.create(
                student=student,
                previous_status=old_status,
                new_status=new_status,
                effective_date=get_school_today(),
                reason=reason or f"Status changed via quick action"
            )
        
        messages.success(
            request,
            f"Status changed from {dict(Student.ENROLLMENT_STATUS_CHOICES)[old_status]} "
            f"to {dict(Student.ENROLLMENT_STATUS_CHOICES)[new_status]}"
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Status changed successfully',
            'redirect': f'/students/{student.pk}/'
        })
        
    except Exception as e:
        logger.error(f"Error changing status: {e}")
        return JsonResponse({
            'success': False,
            'message': f'Error changing status: {str(e)}'
        })


@login_required
def add_guardian_modal(request, student_pk):
    """Modal for adding guardian to student"""
    
    student = get_object_or_404(Student, pk=student_pk)
    
    # Get available guardians (not already linked to this student)
    existing_guardian_ids = student.guardians.values_list('id', flat=True)
    available_guardians = Guardian.objects.filter(
        is_active=True
    ).exclude(id__in=existing_guardian_ids).order_by('last_name', 'first_name')
    
    context = {
        'student': student,
        'available_guardians': available_guardians,
        'relationship_choices': StudentGuardian.RELATIONSHIP_CHOICES,
    }
    
    return render(request, 'students/modals/add_guardian.html', context)


@login_required
@require_http_methods(["POST"])
def add_guardian(request, student_pk):
    """Add guardian to student via HTMX"""
    
    student = get_object_or_404(Student, pk=student_pk)
    guardian_id = request.POST.get('guardian_id')
    relationship = request.POST.get('relationship')
    is_primary = request.POST.get('is_primary') == 'on'
    is_financial = request.POST.get('is_financial_responsible') == 'on'
    emergency_priority = request.POST.get('emergency_contact_priority', 999)
    
    if not guardian_id or not relationship:
        return JsonResponse({
            'success': False,
            'message': 'Please select a guardian and relationship type'
        })
    
    try:
        guardian = Guardian.objects.get(pk=guardian_id)
        
        # Check if relationship already exists
        if StudentGuardian.objects.filter(student=student, guardian=guardian).exists():
            return JsonResponse({
                'success': False,
                'message': 'This guardian is already linked to this student'
            })
        
        # Create relationship
        StudentGuardian.objects.create(
            student=student,
            guardian=guardian,
            relationship=relationship,
            is_primary=is_primary,
            is_financial_responsible=is_financial,
            emergency_contact_priority=int(emergency_priority),
        )
        
        messages.success(
            request,
            f"Guardian {guardian.get_full_name()} added to {student.get_full_name()}"
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Guardian added successfully',
            'redirect': f'/students/{student.pk}/'
        })
        
    except Guardian.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'Guardian not found'
        })
    except Exception as e:
        logger.error(f"Error adding guardian: {e}")
        return JsonResponse({
            'success': False,
            'message': f'Error adding guardian: {str(e)}'
        })


@login_required
def add_sibling_modal(request, student_pk):
    """Modal for adding sibling relationship"""
    
    student = get_object_or_404(Student, pk=student_pk)
    
    # Get available students (not already siblings and not self)
    existing_sibling_ids = list(student.sibling_relationships.values_list('to_student_id', flat=True))
    existing_sibling_ids += list(student.reverse_sibling_relationships.values_list('from_student_id', flat=True))
    
    available_students = Student.objects.filter(
        enrollment_status='ACTIVE'
    ).exclude(
        Q(id=student.pk) | Q(id__in=existing_sibling_ids)
    ).order_by('admission_number')
    
    context = {
        'student': student,
        'available_students': available_students,
        'relationship_types': SiblingRelationship.RELATIONSHIP_TYPES,
    }
    
    return render(request, 'students/modals/add_sibling.html', context)


@login_required
@require_http_methods(["POST"])
def add_sibling(request, student_pk):
    """Add sibling relationship via HTMX"""
    
    student = get_object_or_404(Student, pk=student_pk)
    sibling_id = request.POST.get('sibling_id')
    relationship_type = request.POST.get('relationship_type', 'FULL')
    
    if not sibling_id:
        return JsonResponse({
            'success': False,
            'message': 'Please select a sibling'
        })
    
    try:
        sibling = Student.objects.get(pk=sibling_id)
        
        # Check if relationship already exists
        if SiblingRelationship.objects.filter(
            Q(from_student=student, to_student=sibling) |
            Q(from_student=sibling, to_student=student)
        ).exists():
            return JsonResponse({
                'success': False,
                'message': 'Sibling relationship already exists'
            })
        
        # Create relationship (signal will create reciprocal)
        SiblingRelationship.objects.create(
            from_student=student,
            to_student=sibling,
            relationship_type=relationship_type,
        )
        
        messages.success(
            request,
            f"Sibling relationship created: {student.get_full_name()} - {sibling.get_full_name()}"
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Sibling relationship created successfully',
            'redirect': f'/students/{student.pk}/'
        })
        
    except Student.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'Student not found'
        })
    except Exception as e:
        logger.error(f"Error creating sibling relationship: {e}")
        return JsonResponse({
            'success': False,
            'message': f'Error creating relationship: {str(e)}'
        })


# =============================================================================
# BULK ACTION MODALS
# =============================================================================

@login_required
def bulk_status_change_modal(request):
    """Modal for bulk student status changes"""
    
    student_ids = request.GET.getlist('student_ids')
    students = Student.objects.filter(pk__in=student_ids)
    
    context = {
        'students': students,
        'student_count': students.count(),
        'status_choices': Student.ENROLLMENT_STATUS_CHOICES,
    }
    
    return render(request, 'students/modals/bulk_status_change.html', context)


@login_required
@require_http_methods(["POST"])
def bulk_status_change(request):
    """Bulk change student enrollment status"""
    
    student_ids = request.POST.getlist('student_ids')
    new_status = request.POST.get('new_status')
    reason = request.POST.get('reason', 'Bulk status change')
    
    if not student_ids or not new_status:
        return JsonResponse({
            'success': False,
            'message': 'Invalid request'
        })
    
    try:
        with transaction.atomic():
            students = Student.objects.filter(pk__in=student_ids)
            count = 0
            
            for student in students:
                old_status = student.enrollment_status
                student.enrollment_status = new_status
                student.save()
                count += 1
        
        messages.success(
            request,
            f"Successfully changed status for {count} student(s)"
        )
        
        return JsonResponse({
            'success': True,
            'message': f'Status changed for {count} student(s)',
            'redirect': '/students/'
        })
        
    except Exception as e:
        logger.error(f"Error in bulk status change: {e}")
        return JsonResponse({
            'success': False,
            'message': f'Error: {str(e)}'
        })