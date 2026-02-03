# students/services.py

"""
Student enrollment services.

This module contains business logic for student enrollments,
including bulk enrollment operations, validation, and notifications.
"""

from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError
from django.utils import timezone
from typing import List, Dict, Tuple, Optional
from decimal import Decimal

from students.models import Student
from academics.models import AcademicSession, Class, StudentClassEnrollment
from core.utils import get_school_today

import logging

logger = logging.getLogger(__name__)


# =============================================================================
# BULK ENROLLMENT SERVICE
# =============================================================================

class BulkEnrollmentService:
    """
    Service for handling bulk student enrollments.
    
    This service encapsulates all business logic for enrolling
    multiple students at once, including:
    - Validation
    - Invoice generation
    - Error handling
    - Rollback on failure
    
    Usage:
        service = BulkEnrollmentService()
        result = service.enroll_students(
            student_ids=[1, 2, 3, 4, 5],
            academic_session=session,
            class_instance=class_obj,
            enrollment_date=date.today(),
            enrollment_type='PROMOTED',
            auto_create_invoice=True,
            send_notification=False,  # Not implemented yet
            created_by=request.user
        )
        
        if result['success']:
            print(f"Enrolled {result['enrolled_count']} students")
        else:
            print(f"Errors: {result['errors']}")
    """
    
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.enrolled_students = []
        self.failed_students = []
    
    def enroll_students(
        self,
        student_ids: List[int],
        academic_session: AcademicSession,
        class_instance: Class,
        enrollment_date: Optional[str] = None,
        enrollment_type: str = 'NEW',
        auto_create_invoice: bool = True,
        send_notification: bool = False,
        enrollment_notes: str = '',
        created_by=None,
        dry_run: bool = False
    ) -> Dict:
        """
        Enroll multiple students into a class.
        
        Args:
            student_ids: List of student IDs to enroll
            academic_session: Academic session to enroll into
            class_instance: Class to enroll into
            enrollment_date: Date of enrollment (defaults to today)
            enrollment_type: Type of enrollment
            auto_create_invoice: Whether to create fee invoices
            send_notification: Whether to send notifications (NOT IMPLEMENTED YET)
            enrollment_notes: Notes to add to enrollment records
            created_by: User performing the enrollment
            dry_run: If True, validate only without saving
        
        Returns:
            Dict containing:
                - success: bool
                - enrolled_count: int
                - failed_count: int
                - enrollments: List of created enrollment objects
                - errors: List of error messages
                - warnings: List of warning messages
        """
        self.errors = []
        self.warnings = []
        self.enrolled_students = []
        self.failed_students = []
        
        # Set default enrollment date
        if not enrollment_date:
            enrollment_date = get_school_today()
        
        # Step 1: Pre-validation
        logger.info(
            f"Starting bulk enrollment: {len(student_ids)} students -> "
            f"{class_instance} ({academic_session})"
        )
        
        validation_result = self._pre_validate(
            student_ids=student_ids,
            academic_session=academic_session,
            class_instance=class_instance,
            enrollment_date=enrollment_date
        )
        
        if not validation_result['valid']:
            return {
                'success': False,
                'enrolled_count': 0,
                'failed_count': len(student_ids),
                'enrollments': [],
                'errors': validation_result['errors'],
                'warnings': self.warnings
            }
        
        # Step 2: Get valid students
        students = validation_result['students']
        
        if dry_run:
            return {
                'success': True,
                'enrolled_count': 0,
                'failed_count': 0,
                'enrollments': [],
                'errors': [],
                'warnings': self.warnings,
                'dry_run': True,
                'would_enroll': len(students)
            }
        
        # Step 3: Perform bulk enrollment
        enrollments = self._perform_bulk_enrollment(
            students=students,
            academic_session=academic_session,
            class_instance=class_instance,
            enrollment_date=enrollment_date,
            enrollment_type=enrollment_type,
            enrollment_notes=enrollment_notes,
            created_by=created_by
        )
        
        # Step 4: Post-enrollment actions
        if enrollments and auto_create_invoice:
            self._create_invoices(enrollments)
        
        # Note: Notifications not implemented yet
        if send_notification:
            self.warnings.append(
                "Notification feature is not yet implemented. "
                "Please notify parents/guardians manually."
            )
        
        # Step 5: Compile results
        success = len(enrollments) > 0
        
        result = {
            'success': success,
            'enrolled_count': len(enrollments),
            'failed_count': len(self.failed_students),
            'enrollments': enrollments,
            'errors': self.errors,
            'warnings': self.warnings
        }
        
        logger.info(
            f"Bulk enrollment completed: {result['enrolled_count']} succeeded, "
            f"{result['failed_count']} failed"
        )
        
        return result
    
    def _pre_validate(
        self,
        student_ids: List[int],
        academic_session: AcademicSession,
        class_instance: Class,
        enrollment_date
    ) -> Dict:
        """
        Pre-validate enrollment parameters.
        
        Returns:
            Dict with 'valid' (bool), 'students' (queryset), and 'errors' (list)
        """
        errors = []
        
        # Validate session is not academically closed
        if academic_session.is_academically_closed:
            errors.append(
                f"{academic_session.name} is academically closed"
            )
        
        # Validate session is active
        if not academic_session.is_active:
            errors.append(
                f"{academic_session.name} is not active"
            )
        
        # Validate class belongs to session
        if class_instance.academic_session != academic_session:
            errors.append(
                f"Class {class_instance} does not belong to {academic_session.name}"
            )
        
        # Validate enrollment date is within session
        if (enrollment_date < academic_session.start_date or 
            enrollment_date > academic_session.end_date):
            errors.append(
                f"Enrollment date must be between {academic_session.start_date} "
                f"and {academic_session.end_date}"
            )
        
        # Get and validate students
        students = Student.objects.filter(
            id__in=student_ids
        ).select_related('current_academic_level')
        
        if students.count() != len(student_ids):
            found_ids = set(students.values_list('id', flat=True))
            missing_ids = set(student_ids) - found_ids
            errors.append(
                f"Some students not found: IDs {missing_ids}"
            )
        
        # Check class capacity
        available_capacity = class_instance.get_available_capacity()
        if len(student_ids) > available_capacity:
            errors.append(
                f"Class has only {available_capacity} available spots, "
                f"but attempting to enroll {len(student_ids)} students"
            )
        
        # Check for existing enrollments
        existing_enrollments = StudentClassEnrollment.objects.filter(
            academic_session=academic_session,
            student_id__in=student_ids,
            is_active=True,
            completion_status='ONGOING'
        ).select_related('student', 'class_instance')
        
        if existing_enrollments.exists():
            for enrollment in existing_enrollments:
                self.warnings.append(
                    f"{enrollment.student.get_full_name()} is already enrolled in "
                    f"{enrollment.class_instance}"
                )
                # Remove from student_ids
                students = students.exclude(id=enrollment.student_id)
        
        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'students': students
        }
    
    @transaction.atomic
    def _perform_bulk_enrollment(
        self,
        students,
        academic_session: AcademicSession,
        class_instance: Class,
        enrollment_date,
        enrollment_type: str,
        enrollment_notes: str,
        created_by=None
    ) -> List[StudentClassEnrollment]:
        """
        Perform the actual bulk enrollment in a transaction.
        
        If any enrollment fails, all enrollments are rolled back.
        
        Returns:
            List of created StudentClassEnrollment objects
        """
        enrollments = []
        
        for student in students:
            try:
                # Create enrollment
                enrollment = StudentClassEnrollment(
                    student=student,
                    academic_session=academic_session,
                    class_instance=class_instance,
                    enrollment_date=enrollment_date,
                    enrollment_type=enrollment_type,
                    enrollment_notes=enrollment_notes,
                    is_active=True,
                    completion_status='ONGOING',
                    auto_create_invoice=True  # Will trigger in post_save signal if exists
                )
                
                # Validate
                enrollment.full_clean()
                
                # Save
                enrollment.save()
                
                enrollments.append(enrollment)
                self.enrolled_students.append(student)
                
                logger.debug(
                    f"Enrolled {student.get_full_name()} "
                    f"(ID: {student.id}) into {class_instance}"
                )
                
            except ValidationError as e:
                error_msg = f"{student.get_full_name()}: {str(e)}"
                self.errors.append(error_msg)
                self.failed_students.append(student)
                logger.error(f"Validation error during enrollment: {error_msg}")
                
                # Rollback transaction
                raise
                
            except IntegrityError as e:
                error_msg = f"{student.get_full_name()}: Database integrity error"
                self.errors.append(error_msg)
                self.failed_students.append(student)
                logger.error(f"Integrity error during enrollment: {error_msg} - {str(e)}")
                
                # Rollback transaction
                raise
                
            except Exception as e:
                error_msg = f"{student.get_full_name()}: {str(e)}"
                self.errors.append(error_msg)
                self.failed_students.append(student)
                logger.exception(f"Unexpected error during enrollment: {error_msg}")
                
                # Rollback transaction
                raise
        
        return enrollments
    
    def _create_invoices(self, enrollments: List[StudentClassEnrollment]):
        """
        Create fee invoices for enrolled students.
        
        Uses the invoice generator from fees.invoice_generators
        """
        logger.info(f"Creating invoices for {len(enrollments)} enrollments")
        
        try:
            # Import here to avoid circular imports
            from fees.invoice_generators import generate_enrollment_invoice
            from fees.invoice_generators import FeeStructureNotFoundError
            
            invoices_created = 0
            
            for enrollment in enrollments:
                try:
                    # Generate invoice for class enrollment
                    invoice = generate_enrollment_invoice(
                        enrollment=enrollment,
                        enrollment_type='CLASS',
                        include_optional=False  # Only mandatory fees
                    )
                    
                    # Link invoice to enrollment
                    enrollment.academic_invoice = invoice
                    enrollment.save(update_fields=['academic_invoice'])
                    
                    logger.debug(
                        f"Created invoice {invoice.invoice_number} for "
                        f"{enrollment.student.get_full_name()}"
                    )
                    invoices_created += 1
                    
                except FeeStructureNotFoundError as e:
                    # This is a critical error - no fee structure exists
                    warning_msg = (
                        f"Cannot create invoice for {enrollment.student.get_full_name()}: "
                        f"{str(e)}"
                    )
                    self.warnings.append(warning_msg)
                    logger.error(warning_msg)
                    
                except Exception as e:
                    warning_msg = (
                        f"Failed to create invoice for "
                        f"{enrollment.student.get_full_name()}: {str(e)}"
                    )
                    self.warnings.append(warning_msg)
                    logger.warning(warning_msg)
            
            logger.info(f"Successfully created {invoices_created} invoices")
            
        except ImportError as e:
            logger.error(f"Invoice generator not available: {e}")
            self.warnings.append(
                "Invoice auto-creation is not available. "
                "Please create invoices manually."
            )


# =============================================================================
# PROMOTION SERVICE
# =============================================================================

class StudentPromotionService:
    """
    Service for promoting students to the next academic level.
    
    This is a specialized bulk enrollment service for promotions.
    
    Usage:
        service = StudentPromotionService()
        result = service.promote_students(
            from_session=current_session,
            to_session=next_session,
            from_class=current_class,
            to_class=next_class,
            student_ids=[1, 2, 3]  # optional, promotes all if not provided
        )
    """
    
    def __init__(self):
        self.bulk_enrollment_service = BulkEnrollmentService()
    
    def promote_students(
        self,
        from_session: AcademicSession,
        to_session: AcademicSession,
        from_class: Class,
        to_class: Class,
        student_ids: Optional[List[int]] = None,
        auto_create_invoice: bool = True,
        send_notification: bool = False,
        created_by=None
    ) -> Dict:
        """
        Promote students from one class to another.
        
        Args:
            from_session: Current academic session
            to_session: Next academic session
            from_class: Current class
            to_class: Target class for promotion
            student_ids: Specific students to promote (None = all eligible)
            auto_create_invoice: Create invoices for promoted students
            send_notification: Send promotion notifications (NOT IMPLEMENTED)
            created_by: User performing the promotion
        
        Returns:
            Dict with promotion results
        """
        logger.info(
            f"Starting promotion: {from_class} ({from_session}) -> "
            f"{to_class} ({to_session})"
        )
        
        # Get students to promote
        if student_ids:
            # Promote specific students
            students_query = StudentClassEnrollment.objects.filter(
                id__in=student_ids,
                academic_session=from_session,
                class_instance=from_class,
                is_active=True,
                completion_status='ONGOING'
            )
        else:
            # Promote all eligible students
            students_query = StudentClassEnrollment.objects.filter(
                academic_session=from_session,
                class_instance=from_class,
                is_active=True,
                completion_status='ONGOING'
            )
        
        # Filter for eligible students only
        # (you might want to check academic progress, attendance, etc.)
        students_query = students_query.select_related('student')
        
        student_ids_to_promote = list(
            students_query.values_list('student_id', flat=True)
        )
        
        if not student_ids_to_promote:
            return {
                'success': False,
                'enrolled_count': 0,
                'failed_count': 0,
                'enrollments': [],
                'errors': ['No eligible students found for promotion'],
                'warnings': []
            }
        
        # Mark previous enrollments as completed
        students_query.update(
            completion_status='COMPLETED',
            completion_date=from_session.end_date
        )
        
        # Enroll in new class
        result = self.bulk_enrollment_service.enroll_students(
            student_ids=student_ids_to_promote,
            academic_session=to_session,
            class_instance=to_class,
            enrollment_date=to_session.start_date,
            enrollment_type='PROMOTED',
            auto_create_invoice=auto_create_invoice,
            send_notification=send_notification,
            enrollment_notes=f'Promoted from {from_class}',
            created_by=created_by
        )
        
        # Link to previous enrollments
        if result['success']:
            for enrollment in result['enrollments']:
                # Find previous enrollment
                previous = StudentClassEnrollment.objects.filter(
                    student=enrollment.student,
                    academic_session=from_session,
                    class_instance=from_class
                ).first()
                
                if previous:
                    enrollment.previous_enrollment = previous
                    enrollment.save(update_fields=['previous_enrollment'])
        
        logger.info(
            f"Promotion completed: {result['enrolled_count']} promoted, "
            f"{result['failed_count']} failed"
        )
        
        return result


# =============================================================================
# ENROLLMENT VALIDATION SERVICE
# =============================================================================

class EnrollmentValidationService:
    """
    Service for validating enrollment operations without actually creating records.
    
    Useful for pre-flight checks in the UI.
    """
    
    @staticmethod
    def validate_student_enrollment(
        student: Student,
        academic_session: AcademicSession,
        class_instance: Class
    ) -> Tuple[bool, List[str]]:
        """
        Validate if a student can be enrolled.
        
        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []
        
        # Check student status
        if student.enrollment_status != 'ACTIVE':
            errors.append(
                f"Student status is {student.get_enrollment_status_display()}, "
                f"not ACTIVE"
            )
        
        # Check session is active
        if not academic_session.is_active:
            errors.append("Academic session is not active")
        
        # Check session is not closed
        if academic_session.is_academically_closed:
            errors.append("Academic session is closed")
        
        # Check class capacity
        if not class_instance.has_capacity():
            errors.append("Class has reached maximum capacity")
        
        # Check for duplicate enrollment
        existing = StudentClassEnrollment.objects.filter(
            student=student,
            academic_session=academic_session,
            is_active=True,
            completion_status='ONGOING'
        ).first()
        
        if existing:
            errors.append(
                f"Already enrolled in {existing.class_instance} for this session"
            )
        
        return (len(errors) == 0, errors)
    
    @staticmethod
    def get_enrollment_warnings(
        student: Student,
        class_instance: Class
    ) -> List[str]:
        """
        Get non-blocking warnings about enrollment.
        
        Returns:
            List of warning messages
        """
        warnings = []
        
        # Check age appropriateness
        # student_age = student.get_age()
        # Add logic based on your academic level age ranges
        
        # Check if student has unpaid fees
        # (assumes you have a fee system)
        
        # Check academic progress
        # (assumes you have progress tracking)
        
        return warnings