# boarding/services.py 

"""
Boarding Enrollment Services

Handles complete boarding enrollment workflows including:
- Dormitory assignment and validation
- Invoice generation
- Capacity management
- Guardian consent tracking
- Status management
"""

from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from decimal import Decimal
import logging

from .models import BoardingEnrollment, Dormitory
from students.models import Student
from academics.models import AcademicSession
from fees.invoice_generators import BoardingEnrollmentInvoiceGenerator

# ✅ Import utilities
from .utils import (
    get_dormitory_capacity_summary,
    validate_dormitory_compatibility,
    generate_boarding_roll_number,
    validate_boarding_days,
    validate_boarding_enrollment,
    get_boarding_statistics,
)

logger = logging.getLogger(__name__)


# =============================================================================
# BOARDING SERVICE (ENHANCED)
# =============================================================================

class BoardingService:
    """Complete boarding enrollment workflow"""
    
    @staticmethod
    @transaction.atomic
    def enroll_student_in_boarding(student, dormitory, boarding_type, session, **kwargs):
        """
        Complete boarding enrollment with invoice generation.
        
        ENHANCED: Now uses utilities for validation and calculations
        """
        # =================================================================
        # STEP 1: VALIDATE (using utilities)
        # =================================================================
        
        # ✅ Use utility for dormitory compatibility check
        is_compatible, message = validate_dormitory_compatibility(dormitory, student)
        if not is_compatible:
            raise ValueError(f"Cannot accommodate student: {message}")
        
        # ✅ Use utility for capacity check
        capacity_summary = get_dormitory_capacity_summary(dormitory)
        if not capacity_summary['has_capacity']:
            raise ValueError(
                f"{dormitory.name} is at full capacity "
                f"({capacity_summary['current_occupancy']}/{capacity_summary['total_capacity']})"
            )
        
        # Check for existing active enrollment
        existing = BoardingEnrollment.objects.filter(
            student=student,
            academic_session=session,
            status__in=['PENDING', 'ACTIVE']
        ).exists()
        
        if existing:
            raise ValueError(
                f"{student.get_full_name()} already has an active boarding enrollment "
                f"for {session.name}"
            )
        
        # Validate guardian consent if required
        if student.get_age() < 18 and not kwargs.get('consenting_guardian'):
            raise ValueError("Guardian consent is required for students under 18")
        
        # ✅ Validate boarding days for flexible boarders (using utility)
        if boarding_type == 'FLEXI_BOARDER':
            boarding_days = kwargs.get('boarding_days')
            is_valid, error = validate_boarding_days(boarding_days)
            if not is_valid:
                raise ValueError(f"Invalid boarding days: {error}")
        
        # =================================================================
        # STEP 2: CREATE ENROLLMENT
        # =================================================================
        
        enrollment = BoardingEnrollment.objects.create(
            student=student,
            academic_session=session,
            dormitory=dormitory,
            boarding_type=boarding_type,
            enrollment_date=timezone.now().date(),
            effective_start_date=kwargs.get('start_date', timezone.now().date()),
            effective_end_date=kwargs.get('end_date'),
            status='PENDING',
            consenting_guardian=kwargs.get('consenting_guardian'),
            guardian_consent=bool(kwargs.get('consenting_guardian')),
            consent_date=timezone.now().date() if kwargs.get('consenting_guardian') else None,
            room_number=kwargs.get('room_number', ''),
            bed_number=kwargs.get('bed_number', ''),
            boarding_days=kwargs.get('boarding_days') if boarding_type == 'FLEXI_BOARDER' else None,
            reason_for_boarding=kwargs.get('notes', ''),
            admin_notes=kwargs.get('notes', '')
        )
        
        logger.info(
            f"Created boarding enrollment for {student.get_full_name()} "
            f"in {dormitory.name} ({boarding_type})"
        )
        
        # =================================================================
        # STEP 3: GENERATE INVOICE (if auto_create_invoice)
        # =================================================================
        
        invoice = None
        if enrollment.auto_create_invoice:
            try:
                invoice = BoardingEnrollmentInvoiceGenerator.generate(
                    enrollment,
                    include_meals=kwargs.get('include_meals', True),
                    include_laundry=kwargs.get('include_laundry', False),
                    custom_due_date=kwargs.get('custom_due_date')
                )
                
                logger.info(
                    f"Generated boarding invoice {invoice.invoice_number} "
                    f"for enrollment {enrollment.pk}"
                )
                
            except Exception as e:
                logger.error(f"Error generating invoice: {e}")
        
        # =================================================================
        # STEP 4: LINK INVOICE TO ENROLLMENT
        # =================================================================
        
        if invoice:
            enrollment.boarding_invoice = invoice
            enrollment.save(update_fields=['boarding_invoice'])
        
        # =================================================================
        # STEP 5: AUTO-ASSIGN BOARDING ROLL NUMBER (using utility)
        # =================================================================
        
        if not enrollment.boarding_roll_number:
            # ✅ Use utility for roll number generation
            roll_number = generate_boarding_roll_number(
                dormitory=dormitory,
                academic_session=session
            )
            enrollment.boarding_roll_number = roll_number
            enrollment.save(update_fields=['boarding_roll_number'])
            
            logger.debug(f"Auto-assigned boarding roll number {roll_number} to enrollment {enrollment.pk}")
        
        # =================================================================
        # STEP 6: UPDATE DORMITORY OCCUPANCY
        # =================================================================
        
        dormitory.update_occupancy_count()
        
        # =================================================================
        # STEP 7: SEND NOTIFICATIONS (optional)
        # =================================================================
        
        if kwargs.get('send_notifications', True):
            try:
                BoardingService._send_boarding_enrollment_notification(enrollment)
                
                if dormitory.dormitory_master:
                    BoardingService._send_dormitory_master_notification(enrollment)
                    
            except Exception as e:
                logger.error(f"Error sending notifications: {e}")
        
        return enrollment, invoice
    
    @staticmethod
    @transaction.atomic
    def approve_boarding_enrollment(enrollment, approved_by):
        """
        Approve pending boarding enrollment.
        
        Args:
            enrollment: BoardingEnrollment instance
            approved_by: User/Staff who approved
            
        Returns:
            BoardingEnrollment: Updated enrollment
        """
        if enrollment.status != 'PENDING':
            raise ValueError(
                f"Can only approve PENDING enrollments, current status: {enrollment.status}"
            )
        
        # Approve enrollment
        enrollment.approve(approved_by)
        
        # Generate invoice if not already created
        if not enrollment.boarding_invoice and enrollment.auto_create_invoice:
            try:
                invoice = BoardingEnrollmentInvoiceGenerator.generate(enrollment)
                enrollment.boarding_invoice = invoice
                enrollment.save(update_fields=['boarding_invoice'])
                
                logger.info(f"Generated invoice {invoice.invoice_number} after approval")
                
            except Exception as e:
                logger.error(f"Error generating invoice after approval: {e}")
        
        # Auto-assign roll number if not assigned
        if not enrollment.boarding_roll_number:
            roll_number = generate_boarding_roll_number(
                dormitory=enrollment.dormitory,
                academic_session=enrollment.academic_session
            )
            enrollment.boarding_roll_number = roll_number
            enrollment.save(update_fields=['boarding_roll_number'])
        
        logger.info(
            f"Approved boarding enrollment {enrollment.pk} by {approved_by} for "
            f"{enrollment.student.get_full_name()}"
        )
        
        return enrollment
    
    @staticmethod
    @transaction.atomic
    def suspend_boarding_enrollment(enrollment, reason, suspended_by=None):
        """
        Suspend boarding enrollment.
        """
        if enrollment.status not in ['ACTIVE', 'PENDING']:
            raise ValueError(
                f"Can only suspend ACTIVE or PENDING enrollments, current status: {enrollment.status}"
            )
        
        enrollment.suspend(reason)
        enrollment.dormitory.update_occupancy_count()
        
        logger.info(
            f"Suspended boarding enrollment {enrollment.pk} for "
            f"{enrollment.student.get_full_name()}: {reason}"
        )
        
        return enrollment
    
    @staticmethod
    @transaction.atomic
    def terminate_boarding_enrollment(enrollment, reason, termination_date=None):
        """
        Terminate boarding enrollment.
        """
        if enrollment.status not in ['ACTIVE', 'SUSPENDED']:
            raise ValueError(
                f"Can only terminate ACTIVE or SUSPENDED enrollments, current status: {enrollment.status}"
            )
        
        enrollment.terminate(reason)
        
        if termination_date:
            enrollment.effective_end_date = termination_date
            enrollment.save(update_fields=['effective_end_date'])
        
        enrollment.dormitory.update_occupancy_count()
        
        # Cancel unpaid invoice if exists
        if enrollment.boarding_invoice and enrollment.boarding_invoice.status in ['PENDING', 'PARTIALLY_PAID']:
            from fees.services import InvoiceService
            
            InvoiceService.cancel_invoice(
                enrollment.boarding_invoice,
                reason=f"Boarding enrollment terminated: {reason}"
            )
        
        logger.info(
            f"Terminated boarding enrollment {enrollment.pk} for "
            f"{enrollment.student.get_full_name()}: {reason}"
        )
        
        return enrollment
    
    @staticmethod
    @transaction.atomic
    def transfer_to_dormitory(enrollment, new_dormitory, reason="", **kwargs):
        """
        Transfer student to different dormitory.
        
        ENHANCED: Uses capacity utility for validation
        """
        # Validate
        if enrollment.status != 'ACTIVE':
            raise ValueError(f"Can only transfer ACTIVE enrollments, current status: {enrollment.status}")
        
        # ✅ Use utility for validation
        is_compatible, message = validate_dormitory_compatibility(new_dormitory, enrollment.student)
        if not is_compatible:
            raise ValueError(f"Cannot transfer to {new_dormitory.name}: {message}")
        
        # ✅ Use utility for capacity check
        capacity_summary = get_dormitory_capacity_summary(new_dormitory)
        if not capacity_summary['has_capacity']:
            raise ValueError(
                f"{new_dormitory.name} is at full capacity "
                f"({capacity_summary['current_occupancy']}/{capacity_summary['total_capacity']})"
            )
        
        # Store old dormitory for occupancy update
        old_dormitory = enrollment.dormitory
        
        # Update enrollment
        enrollment.dormitory = new_dormitory
        enrollment.room_number = kwargs.get('room_number', '')
        enrollment.bed_number = kwargs.get('bed_number', '')
        
        # Add to notes
        transfer_note = (
            f"\n\nTransferred from {old_dormitory.name} to {new_dormitory.name} "
            f"on {kwargs.get('transfer_date', timezone.now().date())}: {reason}"
        )
        enrollment.admin_notes = (
            f"{enrollment.admin_notes}{transfer_note}" 
            if enrollment.admin_notes 
            else transfer_note
        )
        
        enrollment.save()
        
        # Update occupancy for both dormitories
        old_dormitory.update_occupancy_count()
        new_dormitory.update_occupancy_count()
        
        logger.info(
            f"Transferred {enrollment.student.get_full_name()} from "
            f"{old_dormitory.name} to {new_dormitory.name}: {reason}"
        )
        
        return enrollment
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    @staticmethod
    def _send_boarding_enrollment_notification(enrollment):
        """Send enrollment notification to parents/guardians"""
        # TODO: Implement notification logic
        pass
    
    @staticmethod
    def _send_dormitory_master_notification(enrollment):
        """Send notification to dormitory master"""
        # TODO: Implement notification logic
        pass
    
    # =========================================================================
    # QUERY HELPERS (delegate to utils)
    # =========================================================================
    
    @staticmethod
    def get_active_boarding_for_student(student, session):
        """Get active boarding enrollment for student in session."""
        try:
            return BoardingEnrollment.objects.get(
                student=student,
                academic_session=session,
                status='ACTIVE'
            )
        except BoardingEnrollment.DoesNotExist:
            return None
        except BoardingEnrollment.MultipleObjectsReturned:
            logger.error(
                f"Multiple active boarding enrollments found for {student.get_full_name()} "
                f"in {session.name}"
            )
            return BoardingEnrollment.objects.filter(
                student=student,
                academic_session=session,
                status='ACTIVE'
            ).first()
    
    @staticmethod
    def get_boarding_history(student):
        """Get complete boarding history for student."""
        return BoardingEnrollment.objects.filter(
            student=student
        ).select_related(
            'dormitory',
            'academic_session',
            'boarding_invoice',
            'consenting_guardian'
        ).order_by('-academic_session__start_date', '-enrollment_date')


# =============================================================================
# BULK BOARDING OPERATIONS (ENHANCED)
# =============================================================================

class BulkBoardingService:
    """Bulk boarding operations"""
    
    @staticmethod
    @transaction.atomic
    def bulk_enroll_in_boarding(students, dormitory, boarding_type, session, **kwargs):
        """
        Enroll multiple students in boarding at once.
        
        ENHANCED: Pre-validates capacity before starting
        """
        # ✅ Use utility for pre-validation
        capacity_summary = get_dormitory_capacity_summary(dormitory)
        
        if capacity_summary['available_capacity'] < len(students):
            raise ValueError(
                f"Insufficient capacity: {capacity_summary['available_capacity']} available, "
                f"but {len(students)} students requested. "
                f"Current: {capacity_summary['current_occupancy']}/{capacity_summary['total_capacity']}"
            )
        
        results = {
            'enrolled': [],
            'failed': [],
            'invoices': [],
            'total': len(students)
        }
        
        for student in students:
            try:
                enrollment, invoice = BoardingService.enroll_student_in_boarding(
                    student=student,
                    dormitory=dormitory,
                    boarding_type=boarding_type,
                    session=session,
                    **kwargs
                )
                
                results['enrolled'].append(enrollment)
                if invoice:
                    results['invoices'].append(invoice)
                    
            except Exception as e:
                logger.error(f"Error enrolling {student.get_full_name()} in boarding: {e}")
                results['failed'].append({
                    'student': student,
                    'error': str(e)
                })
        
        logger.info(
            f"Bulk boarding enrollment completed: {len(results['enrolled'])} enrolled, "
            f"{len(results['failed'])} failed out of {results['total']} total"
        )
        
        return results