# academics/services.py 

from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from decimal import Decimal
import logging

from .models import Class, AcademicSession, StudentClassEnrollment
from students.models import Student
from fees.invoice_generators import ClassEnrollmentInvoiceGenerator

# ✅ Import utilities
from .utils import (
    get_current_academic_session,
    get_class_capacity_summary,
    generate_class_roll_number,
    validate_term_number,
    get_session_by_date,
)

logger = logging.getLogger(__name__)


# =============================================================================
# CLASS ENROLLMENT SERVICE (ENHANCED)
# =============================================================================

class ClassEnrollmentService:
    """Academic class enrollment workflow"""
    
    @staticmethod
    @transaction.atomic
    def enroll_student_in_class(student, class_instance, session, **kwargs):
        """
        Complete class enrollment with invoice generation.
        
        ENHANCED: Now uses utilities for validation and calculations
        """
        # =================================================================
        # STEP 1: VALIDATE (using utilities)
        # =================================================================
        
        # ✅ Use utility for capacity check
        capacity_summary = get_class_capacity_summary(class_instance)
        if not capacity_summary['has_capacity']:
            raise ValueError(
                f"{class_instance.get_display_name()} is at full capacity "
                f"({capacity_summary['current_enrollment']}/{capacity_summary['max_students']})"
            )
        
        # Check if academic session is active for enrollment
        if not session.is_enrollment_open:
            raise ValueError(
                f"Enrollment is closed for {session.name}. "
                f"Deadline was {session.enrollment_deadline or 'not set'}"
            )
        
        # Check for existing active enrollment in this session
        existing = StudentClassEnrollment.objects.filter(
            student=student,
            academic_session=session,
            is_active=True,
            completion_status='ONGOING'
        ).exists()
        
        if existing:
            raise ValueError(
                f"{student.get_full_name()} already has an active class enrollment "
                f"for {session.name}"
            )
        
        # =================================================================
        # STEP 2: CREATE ENROLLMENT
        # =================================================================
        
        enrollment = StudentClassEnrollment.objects.create(
            student=student,
            class_instance=class_instance,
            academic_session=session,
            enrollment_date=timezone.now().date(),
            enrollment_type=kwargs.get('enrollment_type', 'NEW'),
            roll_number=kwargs.get('roll_number', ''),
            completion_status='ONGOING',
            is_active=True,
            enrollment_notes=kwargs.get('notes', '')
        )
        
        logger.info(
            f"Created class enrollment for {student.get_full_name()} "
            f"in {class_instance.get_display_name()} ({session.name})"
        )
        
        # =================================================================
        # STEP 3: GENERATE INVOICE (if auto_create_invoice)
        # =================================================================
        
        invoice = None
        if enrollment.auto_create_invoice:
            try:
                invoice = ClassEnrollmentInvoiceGenerator.generate(
                    enrollment,
                    include_optional=kwargs.get('include_optional_fees', False),
                    discount_amount=kwargs.get('discount_amount'),
                    custom_due_date=kwargs.get('due_date')
                )
                
                logger.info(
                    f"Generated academic invoice {invoice.invoice_number} "
                    f"for enrollment {enrollment.pk}"
                )
                
            except Exception as e:
                logger.error(f"Error generating invoice: {e}")
                # Don't fail entire enrollment if invoice generation fails
        
        # =================================================================
        # STEP 4: LINK INVOICE TO ENROLLMENT
        # =================================================================
        
        if invoice:
            enrollment.academic_invoice = invoice
            enrollment.save(update_fields=['academic_invoice'])
        
        # =================================================================
        # STEP 5: AUTO-ASSIGN ROLL NUMBER (using utility)
        # =================================================================
        
        if not enrollment.roll_number:
            # ✅ Use utility for roll number generation
            roll_number = generate_class_roll_number(
                class_instance=class_instance,
                academic_session=session
            )
            enrollment.roll_number = roll_number
            enrollment.save(update_fields=['roll_number'])
            
            logger.debug(f"Auto-assigned roll number {roll_number} to enrollment {enrollment.pk}")
        
        # =================================================================
        # STEP 6: SEND NOTIFICATIONS (optional)
        # =================================================================
        
        if kwargs.get('send_notifications', True):
            try:
                # Send to parents
                ClassEnrollmentService._send_enrollment_notification(enrollment)
                
                # Notify class teacher
                if class_instance.class_teacher:
                    ClassEnrollmentService._send_teacher_notification(enrollment)
                    
            except Exception as e:
                logger.error(f"Error sending notifications: {e}")
        
        return enrollment, invoice
    
    @staticmethod
    @transaction.atomic
    def transfer_student_to_class(enrollment, new_class_instance, reason="", **kwargs):
        """
        Transfer student from one class to another within same session.
        
        ENHANCED: Uses capacity utility
        """
        # Validate
        if enrollment.completion_status != 'ONGOING':
            raise ValueError("Can only transfer students with ONGOING enrollment")
        
        if new_class_instance.academic_session != enrollment.academic_session:
            raise ValueError("Cannot transfer to class in different academic session")
        
        # ✅ Use utility for capacity check
        capacity_summary = get_class_capacity_summary(new_class_instance)
        if not capacity_summary['has_capacity']:
            raise ValueError(
                f"{new_class_instance.get_display_name()} is at full capacity "
                f"({capacity_summary['current_enrollment']}/{capacity_summary['max_students']})"
            )
        
        # Complete current enrollment
        enrollment.completion_status = 'TRANSFERRED'
        enrollment.completion_date = kwargs.get('transfer_date', timezone.now().date())
        enrollment.is_active = False
        enrollment.enrollment_notes = (
            f"{enrollment.enrollment_notes}\n\nTRANSFERRED: {reason}" 
            if enrollment.enrollment_notes 
            else f"TRANSFERRED: {reason}"
        )
        enrollment.save()
        
        logger.info(
            f"Marked enrollment {enrollment.pk} as TRANSFERRED from "
            f"{enrollment.class_instance.get_display_name()}"
        )
        
        # Create new enrollment (reuse enroll_student_in_class)
        new_enrollment, _ = ClassEnrollmentService.enroll_student_in_class(
            student=enrollment.student,
            class_instance=new_class_instance,
            session=enrollment.academic_session,
            enrollment_type='INTERNAL_TRANSFER',
            notes=kwargs.get('notes', f"Transferred from {enrollment.class_instance.get_display_name()}: {reason}"),
            send_notifications=kwargs.get('send_notifications', False)
        )
        
        # Link to previous enrollment
        new_enrollment.previous_enrollment = enrollment
        new_enrollment.save(update_fields=['previous_enrollment'])
        
        # Copy invoice if requested
        if kwargs.get('update_invoice', False) and enrollment.academic_invoice:
            invoice = enrollment.academic_invoice
            invoice.notes = (
                f"{invoice.notes}\n\nStudent transferred to {new_class_instance.get_display_name()}"
            )
            invoice.save()
            
            new_enrollment.academic_invoice = invoice
            new_enrollment.save(update_fields=['academic_invoice'])
        
        logger.info(
            f"Transferred {enrollment.student.get_full_name()} to "
            f"{new_class_instance.get_display_name()}"
        )
        
        return new_enrollment
    
    @staticmethod
    @transaction.atomic
    def promote_student_to_next_level(enrollment, next_class_instance, next_session, **kwargs):
        """
        Promote student to next academic level/session.
        """
        # Validate
        if enrollment.completion_status != 'ONGOING':
            raise ValueError("Can only promote students with ONGOING enrollment")
        
        # Complete current enrollment
        enrollment.completion_status = 'COMPLETED'
        enrollment.completion_date = kwargs.get('promotion_date', timezone.now().date())
        enrollment.is_active = False
        enrollment.save()
        
        logger.info(
            f"Completed enrollment {enrollment.pk} for promotion to "
            f"{next_class_instance.get_display_name()}"
        )
        
        # Create new enrollment for next session (reuse enroll_student_in_class)
        new_enrollment, invoice = ClassEnrollmentService.enroll_student_in_class(
            student=enrollment.student,
            class_instance=next_class_instance,
            session=next_session,
            enrollment_type='PROMOTED',
            include_optional_fees=kwargs.get('include_optional_fees', False),
            notes=kwargs.get('notes', f"Promoted from {enrollment.class_instance.get_display_name()}"),
            send_notifications=kwargs.get('send_notifications', True)
        )
        
        # Link to previous enrollment
        new_enrollment.previous_enrollment = enrollment
        new_enrollment.save(update_fields=['previous_enrollment'])
        
        logger.info(
            f"Promoted {enrollment.student.get_full_name()} from "
            f"{enrollment.class_instance.get_display_name()} to "
            f"{next_class_instance.get_display_name()}"
        )
        
        return new_enrollment, invoice
    
    @staticmethod
    @transaction.atomic
    def withdraw_student_from_class(enrollment, reason, withdrawal_date=None):
        """
        Withdraw student from class.
        """
        if enrollment.completion_status not in ['ONGOING']:
            raise ValueError(
                f"Can only withdraw ONGOING enrollments, current status: {enrollment.completion_status}"
            )
        
        # Update enrollment
        enrollment.completion_status = 'WITHDRAWN'
        enrollment.completion_date = withdrawal_date or timezone.now().date()
        enrollment.is_active = False
        enrollment.enrollment_notes = (
            f"{enrollment.enrollment_notes}\n\nWITHDRAWN: {reason}" 
            if enrollment.enrollment_notes 
            else f"WITHDRAWN: {reason}"
        )
        enrollment.save()
        
        # Cancel unpaid invoice if exists
        if enrollment.academic_invoice and enrollment.academic_invoice.status in ['PENDING', 'OVERDUE']:
            from fees.services import InvoiceService
            
            InvoiceService.cancel_invoice(
                enrollment.academic_invoice,
                reason=f"Student withdrawn: {reason}"
            )
        
        logger.info(
            f"Withdrew {enrollment.student.get_full_name()} from "
            f"{enrollment.class_instance.get_display_name()}: {reason}"
        )
        
        return enrollment
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    @staticmethod
    def _send_enrollment_notification(enrollment):
        """Send enrollment notification to parents/guardians"""
        # TODO: Implement notification logic
        pass
    
    @staticmethod
    def _send_teacher_notification(enrollment):
        """Send notification to class teacher"""
        # TODO: Implement notification logic
        pass
    
    # =========================================================================
    # QUERY HELPERS (delegate to utils where appropriate)
    # =========================================================================
    
    @staticmethod
    def get_active_enrollment_for_student(student, session=None):
        """
        Get active class enrollment for student in session.
        
        Args:
            student: Student instance
            session: AcademicSession instance (optional, uses current if not provided)
            
        Returns:
            StudentClassEnrollment or None
        """
        # ✅ Use utility to get current session if not provided
        if session is None:
            session = get_current_academic_session()
            if not session:
                return None
        
        try:
            return StudentClassEnrollment.objects.get(
                student=student,
                academic_session=session,
                is_active=True,
                completion_status='ONGOING'
            )
        except StudentClassEnrollment.DoesNotExist:
            return None
        except StudentClassEnrollment.MultipleObjectsReturned:
            logger.error(
                f"Multiple active enrollments found for {student.get_full_name()} "
                f"in {session.name}"
            )
            return StudentClassEnrollment.objects.filter(
                student=student,
                academic_session=session,
                is_active=True,
                completion_status='ONGOING'
            ).first()
    
    @staticmethod
    def get_enrollment_history(student):
        """
        Get complete enrollment history for student.
        
        Args:
            student: Student instance
            
        Returns:
            QuerySet of StudentClassEnrollment
        """
        return StudentClassEnrollment.objects.filter(
            student=student
        ).select_related(
            'class_instance',
            'class_instance__academic_level',
            'academic_session',
            'academic_invoice'
        ).order_by('-academic_session__start_date', '-enrollment_date')


# =============================================================================
# BULK ENROLLMENT OPERATIONS
# =============================================================================

class BulkEnrollmentService:
    """Bulk enrollment operations for efficiency"""
    
    @staticmethod
    @transaction.atomic
    def bulk_enroll_students(students, class_instance, session, **kwargs):
        """
        Enroll multiple students in a class at once.
        
        ENHANCED: Pre-validates capacity before starting
        """
        # ✅ Use utility for pre-validation
        capacity_summary = get_class_capacity_summary(class_instance)
        
        if capacity_summary['available_capacity'] < len(students):
            raise ValueError(
                f"Insufficient capacity: {capacity_summary['available_capacity']} available, "
                f"but {len(students)} students requested. "
                f"Current: {capacity_summary['current_enrollment']}/{capacity_summary['max_students']}"
            )
        
        results = {
            'enrolled': [],
            'failed': [],
            'invoices': [],
            'total': len(students)
        }
        
        for student in students:
            try:
                enrollment, invoice = ClassEnrollmentService.enroll_student_in_class(
                    student=student,
                    class_instance=class_instance,
                    session=session,
                    **kwargs
                )
                
                results['enrolled'].append(enrollment)
                if invoice:
                    results['invoices'].append(invoice)
                    
            except Exception as e:
                logger.error(f"Error enrolling {student.get_full_name()}: {e}")
                results['failed'].append({
                    'student': student,
                    'error': str(e)
                })
        
        logger.info(
            f"Bulk enrollment completed: {len(results['enrolled'])} enrolled, "
            f"{len(results['failed'])} failed out of {results['total']} total"
        )
        
        return results
    
    @staticmethod
    @transaction.atomic
    def bulk_promote_class(class_instance, next_class_instance, next_session, **kwargs):
        """
        Promote entire class to next level.
        
        ENHANCED: Validates target class capacity before starting
        """
        # Get all active enrollments
        enrollments = StudentClassEnrollment.objects.filter(
            class_instance=class_instance,
            is_active=True,
            completion_status='ONGOING'
        ).select_related('student')
        
        student_count = enrollments.count()
        
        # ✅ Use utility for capacity validation
        capacity_summary = get_class_capacity_summary(next_class_instance)
        
        if capacity_summary['available_capacity'] < student_count:
            raise ValueError(
                f"Insufficient capacity in target class: {capacity_summary['available_capacity']} available, "
                f"but {student_count} students to promote. "
                f"Current: {capacity_summary['current_enrollment']}/{capacity_summary['max_students']}"
            )
        
        results = {
            'promoted': [],
            'failed': [],
            'invoices': [],
            'total': student_count
        }
        
        for enrollment in enrollments:
            try:
                new_enrollment, invoice = ClassEnrollmentService.promote_student_to_next_level(
                    enrollment=enrollment,
                    next_class_instance=next_class_instance,
                    next_session=next_session,
                    **kwargs
                )
                
                results['promoted'].append(new_enrollment)
                if invoice:
                    results['invoices'].append(invoice)
                    
            except Exception as e:
                logger.error(
                    f"Error promoting {enrollment.student.get_full_name()}: {e}"
                )
                results['failed'].append({
                    'enrollment': enrollment,
                    'student': enrollment.student,
                    'error': str(e)
                })
        
        logger.info(
            f"Bulk promotion completed: {len(results['promoted'])} promoted, "
            f"{len(results['failed'])} failed out of {results['total']} total"
        )
        
        return results