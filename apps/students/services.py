# students/services.py
"""
Business logic services for student management.
Handles complex operations that span multiple models and apps.
"""

from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import Q, Count, Sum
from decimal import Decimal
import logging

from .models import Student, Guardian, StudentGuardian, EnrollmentStatusHistory
from academics.models import StudentClassEnrollment, Class, AcademicSession

logger = logging.getLogger(__name__)


# =============================================================================
# STUDENT ENROLLMENT SERVICES
# =============================================================================

class StudentEnrollmentService:
    """Service for handling complex student enrollment operations."""
    
    @staticmethod
    @transaction.atomic
    def enroll_student_in_class(
        student, 
        class_instance, 
        academic_session=None,
        enrollment_type='NEW',
        auto_create_invoice=True,
        **kwargs
    ):
        """
        Comprehensive student enrollment with all related operations.
        
        Args:
            student (Student): Student to enroll
            class_instance (Class): Class to enroll in
            academic_session (AcademicSession): Session (defaults to class session)
            enrollment_type (str): Type of enrollment
            auto_create_invoice (bool): Whether to create fee invoice
            **kwargs: Additional enrollment data
            
        Returns:
            tuple: (enrollment, created, messages)
        """
        if not academic_session:
            academic_session = class_instance.academic_session
        
        messages = []
        
        # 1. Validation checks
        validation_errors = []
        
        # Check if student is active
        if student.enrollment_status != 'ACTIVE':
            validation_errors.append(f"Student {student.get_full_name()} is not active")
        
        # Check class capacity
        from academics.utils import get_class_capacity_summary
        capacity = get_class_capacity_summary(class_instance)
        if not capacity['has_capacity']:
            validation_errors.append(f"Class {class_instance} is at full capacity")
        
        # Check for existing enrollment
        existing = StudentClassEnrollment.objects.filter(
            student=student,
            academic_session=academic_session,
            is_active=True,
            completion_status='ONGOING'
        ).first()
        
        if existing:
            validation_errors.append(
                f"Student already enrolled in {existing.class_instance} for {academic_session}"
            )
        
        if validation_errors:
            raise ValidationError(validation_errors)
        
        # 2. Create the enrollment
        enrollment = StudentClassEnrollment.objects.create(
            student=student,
            class_instance=class_instance,
            academic_session=academic_session,
            enrollment_type=enrollment_type,
            auto_create_invoice=auto_create_invoice,
            enrollment_date=timezone.now().date(),
            **kwargs
        )
        
        messages.append(f"Successfully enrolled {student.get_full_name()} in {class_instance}")
        
        # 3. Update student's current academic level
        if enrollment.is_active:
            student.current_academic_level = class_instance.academic_level
            student.save(update_fields=['current_academic_level'])
            messages.append(f"Updated student's current level to {class_instance.academic_level}")
        
        # 4. Create fee invoice if requested
        invoice_created = False
        if auto_create_invoice:
            try:
                invoice = StudentEnrollmentService._create_enrollment_invoice(enrollment)
                if invoice:
                    enrollment.academic_invoice = invoice
                    enrollment.save(update_fields=['academic_invoice'])
                    invoice_created = True
                    messages.append(f"Created fee invoice: {invoice.invoice_number}")
            except Exception as e:
                logger.error(f"Failed to create invoice for enrollment {enrollment.id}: {e}")
                messages.append(f"Warning: Could not create fee invoice - {str(e)}")
        
        # 5. Log the enrollment
        logger.info(
            f"Student enrollment completed: {student.get_full_name()} -> "
            f"{class_instance} ({academic_session}) [Roll: {enrollment.roll_number}]"
        )
        
        return enrollment, True, messages
    
    @staticmethod
    @transaction.atomic
    def transfer_student_between_classes(
        student,
        from_class,
        to_class,
        reason="Class transfer",
        effective_date=None
    ):
        """
        Transfer a student from one class to another within the same session.
        
        Args:
            student (Student): Student to transfer
            from_class (Class): Current class
            to_class (Class): Target class
            reason (str): Reason for transfer
            effective_date (date): Transfer effective date
            
        Returns:
            tuple: (new_enrollment, messages)
        """
        if not effective_date:
            effective_date = timezone.now().date()
        
        messages = []
        
        # Validation
        if from_class.academic_session != to_class.academic_session:
            raise ValidationError("Cannot transfer between different academic sessions")
        
        # Check capacity in target class
        from academics.utils import get_class_capacity_summary
        capacity = get_class_capacity_summary(to_class)
        if not capacity['has_capacity']:
            raise ValidationError(f"Target class {to_class} is at full capacity")
        
        # Get current enrollment
        current_enrollment = StudentClassEnrollment.objects.get(
            student=student,
            class_instance=from_class,
            is_active=True,
            completion_status='ONGOING'
        )
        
        # Complete the current enrollment
        current_enrollment.completion_status = 'TRANSFERRED'
        current_enrollment.completion_date = effective_date
        current_enrollment.is_active = False
        current_enrollment.enrollment_notes += f"\nTransferred to {to_class} on {effective_date}. Reason: {reason}"
        current_enrollment.save()
        
        messages.append(f"Completed enrollment in {from_class}")
        
        # Create new enrollment
        new_enrollment = StudentClassEnrollment.objects.create(
            student=student,
            class_instance=to_class,
            academic_session=to_class.academic_session,
            enrollment_type='TRANSFERRED',
            previous_enrollment=current_enrollment,
            enrollment_date=effective_date,
            enrollment_notes=f"Transferred from {from_class}. Reason: {reason}",
            auto_create_invoice=False  # Don't create new invoice for transfer
        )
        
        messages.append(f"Created new enrollment in {to_class}")
        
        # Update student's current level if different
        if student.current_academic_level != to_class.academic_level:
            student.current_academic_level = to_class.academic_level
            student.save(update_fields=['current_academic_level'])
            messages.append(f"Updated student's level to {to_class.academic_level}")
        
        logger.info(
            f"Student transfer completed: {student.get_full_name()} from "
            f"{from_class} to {to_class} (Roll: {new_enrollment.roll_number})"
        )
        
        return new_enrollment, messages
    
    @staticmethod
    @transaction.atomic
    def withdraw_student(
        student,
        withdrawal_date=None,
        reason="Voluntary withdrawal",
        new_status='WITHDRAWN'
    ):
        """
        Withdraw a student from school.
        
        Args:
            student (Student): Student to withdraw
            withdrawal_date (date): Withdrawal date
            reason (str): Reason for withdrawal
            new_status (str): New enrollment status
            
        Returns:
            tuple: (success, messages)
        """
        if not withdrawal_date:
            withdrawal_date = timezone.now().date()
        
        messages = []
        
        # Update student status
        old_status = student.enrollment_status
        student.enrollment_status = new_status
        student.withdrawal_date = withdrawal_date
        student.save(update_fields=['enrollment_status', 'withdrawal_date'])
        
        # Create status history record
        StudentStatusChangeService.create_status_change(
            student=student,
            previous_status=old_status,
            new_status=new_status,
            effective_date=withdrawal_date,
            reason=reason
        )
        
        # Complete all active enrollments
        active_enrollments = StudentClassEnrollment.objects.filter(
            student=student,
            is_active=True,
            completion_status='ONGOING'
        )
        
        for enrollment in active_enrollments:
            enrollment.completion_status = 'WITHDRAWN'
            enrollment.completion_date = withdrawal_date
            enrollment.is_active = False
            enrollment.enrollment_notes += f"\nStudent withdrawn on {withdrawal_date}. Reason: {reason}"
            enrollment.save()
            messages.append(f"Completed enrollment in {enrollment.class_instance}")
        
        messages.append(f"Student withdrawal completed: {student.get_full_name()}")
        
        logger.warning(
            f"Student withdrawn: {student.get_full_name()} on {withdrawal_date}. "
            f"Reason: {reason}"
        )
        
        return True, messages
    
    @staticmethod
    def _create_enrollment_invoice(enrollment):
        """
        Create fee invoice for student enrollment.
        
        Args:
            enrollment (StudentClassEnrollment): The enrollment
            
        Returns:
            FeeInvoice or None: Created invoice
        """
        try:
            from fees.services import FeeInvoiceService
            from fees.models import FeeStructure
            
            # Get applicable fee structure
            fee_structure = FeeStructure.objects.filter(
                academic_level=enrollment.class_instance.academic_level,
                academic_session=enrollment.academic_session,
                is_active=True
            ).first()
            
            if not fee_structure:
                logger.warning(
                    f"No fee structure found for {enrollment.class_instance.academic_level} "
                    f"in {enrollment.academic_session}"
                )
                return None
            
            # Create invoice using fee service
            invoice = FeeInvoiceService.create_enrollment_invoice(
                student=enrollment.student,
                fee_structure=fee_structure,
                enrollment=enrollment
            )
            
            return invoice
            
        except ImportError:
            logger.debug("Fee management not available")
            return None
        except Exception as e:
            logger.error(f"Error creating enrollment invoice: {e}")
            raise


# =============================================================================
# STUDENT STATUS CHANGE SERVICES
# =============================================================================

class StudentStatusChangeService:
    """Service for managing student status changes."""
    
    @staticmethod
    @transaction.atomic
    def create_status_change(
        student,
        previous_status,
        new_status,
        effective_date,
        reason="",
        academic_session=None,
        approval_required=False
    ):
        """
        Create a student status change record.
        
        Args:
            student (Student): The student
            previous_status (str): Previous status
            new_status (str): New status
            effective_date (date): When change takes effect
            reason (str): Reason for change
            academic_session (AcademicSession): Related session
            approval_required (bool): Whether approval is needed
            
        Returns:
            EnrollmentStatusHistory: Created history record
        """
        history = EnrollmentStatusHistory.objects.create(
            student=student,
            previous_status=previous_status,
            new_status=new_status,
            effective_date=effective_date,
            reason=reason,
            academic_session=academic_session,
            approval_required=approval_required,
            is_approved=not approval_required  # Auto-approve if no approval needed
        )
        
        if not approval_required:
            history.approval_date = timezone.now()
            history.save(update_fields=['approval_date'])
        
        logger.info(
            f"Status change recorded: {student.get_full_name()} "
            f"{previous_status} → {new_status} (Effective: {effective_date})"
        )
        
        return history
    
    @staticmethod
    @transaction.atomic
    def bulk_status_change(
        students_queryset,
        new_status,
        effective_date,
        reason="Bulk status change"
    ):
        """
        Change status for multiple students.
        
        Args:
            students_queryset (QuerySet): Students to update
            new_status (str): New status for all
            effective_date (date): Effective date
            reason (str): Reason for change
            
        Returns:
            tuple: (success_count, error_count, messages)
        """
        success_count = 0
        error_count = 0
        messages = []
        
        for student in students_queryset:
            try:
                old_status = student.enrollment_status
                
                # Update student
                student.enrollment_status = new_status
                student.save(update_fields=['enrollment_status'])
                
                # Create history
                StudentStatusChangeService.create_status_change(
                    student=student,
                    previous_status=old_status,
                    new_status=new_status,
                    effective_date=effective_date,
                    reason=reason
                )
                
                success_count += 1
                
            except Exception as e:
                error_count += 1
                messages.append(f"Failed to update {student.get_full_name()}: {str(e)}")
                logger.error(f"Bulk status change error for {student}: {e}")
        
        messages.insert(0, f"Successfully updated {success_count} students")
        if error_count > 0:
            messages.insert(1, f"Failed to update {error_count} students")
        
        return success_count, error_count, messages


# =============================================================================
# GUARDIAN MANAGEMENT SERVICES
# =============================================================================

class GuardianManagementService:
    """Service for managing guardian relationships."""
    
    @staticmethod
    @transaction.atomic
    def add_guardian_to_student(
        student,
        guardian,
        relationship,
        is_primary=False,
        is_financial_responsible=False,
        emergency_contact_priority=999,
        **relationship_data
    ):
        """
        Add a guardian to a student with full relationship setup.
        
        Args:
            student (Student): The student
            guardian (Guardian): The guardian
            relationship (str): Type of relationship
            is_primary (bool): Whether this is primary guardian
            is_financial_responsible (bool): Financial responsibility
            emergency_contact_priority (int): Emergency contact priority
            **relationship_data: Additional relationship data
            
        Returns:
            StudentGuardian: Created relationship
        """
        # Check if relationship already exists
        existing = StudentGuardian.objects.filter(
            student=student,
            guardian=guardian
        ).first()
        
        if existing:
            if existing.is_active:
                raise ValidationError(
                    f"Guardian {guardian.get_full_name()} is already linked to "
                    f"{student.get_full_name()}"
                )
            else:
                # Reactivate existing relationship
                existing.is_active = True
                existing.relationship = relationship
                existing.is_primary = is_primary
                existing.is_financial_responsible = is_financial_responsible
                existing.emergency_contact_priority = emergency_contact_priority
                existing.save()
                
                logger.info(f"Reactivated guardian relationship: {existing}")
                return existing
        
        # Create new relationship
        relationship_obj = StudentGuardian.objects.create(
            student=student,
            guardian=guardian,
            relationship=relationship,
            is_primary=is_primary,
            is_financial_responsible=is_financial_responsible,
            emergency_contact_priority=emergency_contact_priority,
            **relationship_data
        )
        
        logger.info(f"Created guardian relationship: {relationship_obj}")
        return relationship_obj
    
    @staticmethod
    @transaction.atomic
    def transfer_primary_guardian(student, new_primary_guardian):
        """
        Transfer primary guardian status to another guardian.
        
        Args:
            student (Student): The student
            new_primary_guardian (Guardian): New primary guardian
            
        Returns:
            StudentGuardian: Updated primary relationship
        """
        # Remove primary status from all current guardians
        StudentGuardian.objects.filter(
            student=student,
            is_primary=True
        ).update(is_primary=False)
        
        # Set new primary
        relationship = StudentGuardian.objects.get(
            student=student,
            guardian=new_primary_guardian,
            is_active=True
        )
        relationship.is_primary = True
        relationship.save()
        
        logger.info(
            f"Primary guardian changed for {student.get_full_name()}: "
            f"{new_primary_guardian.get_full_name()}"
        )
        
        return relationship


# =============================================================================
# BULK OPERATIONS SERVICE
# =============================================================================

class BulkStudentOperationsService:
    """Service for bulk operations on students."""
    
    @staticmethod
    @transaction.atomic
    def bulk_enroll_students(
        students_queryset,
        class_instance,
        enrollment_type='BULK',
        auto_create_invoices=True
    ):
        """
        Enroll multiple students in a class.
        
        Args:
            students_queryset (QuerySet): Students to enroll
            class_instance (Class): Target class
            enrollment_type (str): Type of enrollment
            auto_create_invoices (bool): Create fee invoices
            
        Returns:
            tuple: (success_count, error_count, messages)
        """
        success_count = 0
        error_count = 0
        messages = []
        
        # Check class capacity
        from academics.utils import get_class_capacity_summary
        capacity = get_class_capacity_summary(class_instance)
        available_spots = capacity['available_capacity']
        
        students_count = students_queryset.count()
        if students_count > available_spots:
            messages.append(
                f"Warning: {students_count} students selected but only "
                f"{available_spots} spots available in {class_instance}"
            )
        
        for student in students_queryset[:available_spots]:
            try:
                enrollment, created, enroll_messages = StudentEnrollmentService.enroll_student_in_class(
                    student=student,
                    class_instance=class_instance,
                    enrollment_type=enrollment_type,
                    auto_create_invoice=auto_create_invoices
                )
                
                if created:
                    success_count += 1
                    messages.extend(enroll_messages)
                
            except ValidationError as e:
                error_count += 1
                messages.append(f"{student.get_full_name()}: {str(e)}")
            except Exception as e:
                error_count += 1
                messages.append(f"{student.get_full_name()}: Unexpected error - {str(e)}")
                logger.error(f"Bulk enrollment error for {student}: {e}")
        
        summary_msg = f"Bulk enrollment completed: {success_count} successful, {error_count} failed"
        messages.insert(0, summary_msg)
        
        logger.info(
            f"Bulk enrollment to {class_instance}: "
            f"{success_count}/{students_count} successful"
        )
        
        return success_count, error_count, messages
    
    @staticmethod
    @transaction.atomic
    def promote_students_to_next_level(
        students_queryset,
        target_session,
        only_eligible=True
    ):
        """
        Promote students to their next academic level.
        
        Args:
            students_queryset (QuerySet): Students to promote
            target_session (AcademicSession): Target session for promotion
            only_eligible (bool): Only promote eligible students
            
        Returns:
            tuple: (success_count, error_count, messages)
        """
        success_count = 0
        error_count = 0
        messages = []
        
        for student in students_queryset:
            try:
                # Check eligibility if required
                if only_eligible:
                    from academics.models import AcademicProgress
                    progress = AcademicProgress.objects.filter(
                        student=student
                    ).order_by('-academic_session__start_date').first()
                    
                    if not progress or not progress.is_eligible_for_promotion:
                        error_count += 1
                        messages.append(f"{student.get_full_name()}: Not eligible for promotion")
                        continue
                
                # Get next level
                if not student.current_academic_level:
                    error_count += 1
                    messages.append(f"{student.get_full_name()}: No current academic level set")
                    continue
                
                next_level = student.current_academic_level.next_level
                if not next_level:
                    error_count += 1
                    messages.append(f"{student.get_full_name()}: No next level defined")
                    continue
                
                # Find appropriate class in next level
                target_class = Class.objects.filter(
                    academic_level=next_level,
                    academic_session=target_session,
                    is_active=True
                ).first()
                
                if not target_class:
                    error_count += 1
                    messages.append(
                        f"{student.get_full_name()}: No class available in {next_level} "
                        f"for {target_session}"
                    )
                    continue
                
                # Enroll in new class
                enrollment, created, enroll_messages = StudentEnrollmentService.enroll_student_in_class(
                    student=student,
                    class_instance=target_class,
                    enrollment_type='PROMOTED'
                )
                
                if created:
                    success_count += 1
                    messages.append(f"{student.get_full_name()}: Promoted to {next_level}")
                
            except Exception as e:
                error_count += 1
                messages.append(f"{student.get_full_name()}: Promotion failed - {str(e)}")
                logger.error(f"Promotion error for {student}: {e}")
        
        summary = f"Student promotion completed: {success_count} promoted, {error_count} failed"
        messages.insert(0, summary)
        
        logger.info(f"Bulk promotion to {target_session}: {success_count}/{students_queryset.count()}")
        
        return success_count, error_count, messages


# =============================================================================
# ACADEMIC PROGRESS SERVICES
# =============================================================================

class AcademicProgressService:
    """Service for academic progress operations."""
    
    @staticmethod
    def calculate_student_progression_eligibility(student, current_session):
        """
        Calculate if student is eligible for progression.
        
        Args:
            student (Student): The student
            current_session (AcademicSession): Current academic session
            
        Returns:
            dict: Eligibility details
        """
        from academics.models import AcademicProgress
        
        try:
            progress = AcademicProgress.objects.get(
                student=student,
                academic_session=current_session
            )
            
            # Check minimum attendance
            min_attendance = current_session.minimum_attendance_percentage
            meets_attendance = (
                progress.attendance_percentage and 
                progress.attendance_percentage >= min_attendance
            )
            
            # Check subject performance
            passed_all = progress.subjects_failed == 0 and progress.total_subjects > 0
            
            # Overall eligibility
            is_eligible = meets_attendance and passed_all
            
            return {
                'is_eligible': is_eligible,
                'meets_attendance_requirement': meets_attendance,
                'attendance_percentage': progress.attendance_percentage,
                'minimum_required_attendance': min_attendance,
                'passed_all_subjects': passed_all,
                'subjects_passed': progress.subjects_passed,
                'subjects_failed': progress.subjects_failed,
                'total_subjects': progress.total_subjects,
                'overall_percentage': progress.percentage,
                'promotion_decision': progress.promotion_decision,
            }
            
        except AcademicProgress.DoesNotExist:
            return {
                'is_eligible': False,
                'error': 'No academic progress record found',
                'meets_attendance_requirement': False,
                'passed_all_subjects': False,
            }
    
    @staticmethod
    @transaction.atomic
    def finalize_academic_progress(student, academic_session, user=None):
        """
        Finalize academic progress for a student.
        
        Args:
            student (Student): The student
            academic_session (AcademicSession): Academic session
            user: User finalizing the progress
            
        Returns:
            tuple: (success, message)
        """
        from academics.models import AcademicProgress
        
        try:
            progress = AcademicProgress.objects.get(
                student=student,
                academic_session=academic_session
            )
            
            success = progress.finalize_record(user=user)
            
            if success:
                return True, f"Academic progress finalized for {student.get_full_name()}"
            else:
                return False, "Progress record was already finalized"
                
        except AcademicProgress.DoesNotExist:
            return False, "No academic progress record found"
        except Exception as e:
            logger.error(f"Error finalizing progress for {student}: {e}")
            return False, f"Error finalizing progress: {str(e)}"


# =============================================================================
# STUDENT ADMISSION SERVICES
# =============================================================================

class StudentAdmissionService:
    """Service for handling new student admissions."""
    
    @staticmethod
    @transaction.atomic
    def admit_new_student(
        student_data,
        guardian_data_list,
        initial_class=None,
        auto_enroll=True
    ):
        """
        Complete new student admission process.
        
        Args:
            student_data (dict): Student information
            guardian_data_list (list): List of guardian data dictionaries
            initial_class (Class): Class to initially enroll in
            auto_enroll (bool): Whether to auto-enroll in class
            
        Returns:
            tuple: (student, guardians, enrollment, messages)
        """
        messages = []
        
        # 1. Create student
        student = Student.objects.create(**student_data)
        messages.append(f"Created student record: {student.get_full_name()}")
        
        # 2. Create guardians and relationships
        guardians = []
        for i, guardian_data in enumerate(guardian_data_list):
            # Separate relationship data from guardian data
            relationship_data = guardian_data.pop('relationship_data', {})
            
            # Check if guardian already exists (by phone or email)
            existing_guardian = Guardian.objects.filter(
                Q(primary_phone=guardian_data.get('primary_phone')) |
                Q(email=guardian_data.get('email'))
            ).first()
            
            if existing_guardian:
                guardian = existing_guardian
                messages.append(f"Using existing guardian: {guardian.get_full_name()}")
            else:
                guardian = Guardian.objects.create(**guardian_data)
                messages.append(f"Created new guardian: {guardian.get_full_name()}")
            
            guardians.append(guardian)
            
            # Create relationship
            relationship_defaults = {
                'is_primary': i == 0,  # First guardian is primary
                'is_financial_responsible': i == 0,
                'emergency_contact_priority': i + 1,
                **relationship_data
            }
            
            GuardianManagementService.add_guardian_to_student(
                student=student,
                guardian=guardian,
                **relationship_defaults
            )
            messages.append(f"Created guardian relationship: {guardian.get_full_name()}")
        
        # 3. Auto-enroll if requested and class provided
        enrollment = None
        if auto_enroll and initial_class:
            try:
                enrollment, created, enroll_messages = StudentEnrollmentService.enroll_student_in_class(
                    student=student,
                    class_instance=initial_class,
                    enrollment_type='NEW'
                )
                messages.extend(enroll_messages)
            except ValidationError as e:
                messages.append(f"Could not auto-enroll: {str(e)}")
        
        logger.info(f"Student admission completed: {student.get_full_name()}")
        return student, guardians, enrollment, messages
    
    @staticmethod
    @transaction.atomic
    def transfer_student_from_external_school(
        student_data,
        transfer_details,
        guardian_data_list=None,
        target_class=None
    ):
        """
        Handle student transfer from external school.
        
        Args:
            student_data (dict): Student information
            transfer_details (dict): Transfer-specific information
            guardian_data_list (list): Guardian data (optional)
            target_class (Class): Class to enroll in
            
        Returns:
            tuple: (student, enrollment, messages)
        """
        messages = []
        
        # Update student data with transfer information
        student_data.update({
            'enrollment_type': 'TRANSFER_IN',
            'previous_school': transfer_details.get('previous_school'),
            'previous_school_address': transfer_details.get('previous_school_address'),
            'transfer_reason': transfer_details.get('reason'),
            'transfer_certificate_number': transfer_details.get('certificate_number'),
            'previous_school_completion_date': transfer_details.get('completion_date'),
        })
        
        # Handle guardians if provided
        guardians = []
        if guardian_data_list:
            student, guardians, _, guardian_messages = StudentAdmissionService.admit_new_student(
                student_data=student_data,
                guardian_data_list=guardian_data_list,
                initial_class=target_class,
                auto_enroll=bool(target_class)
            )
            messages.extend(guardian_messages)
        else:
            # Create student without guardians
            student = Student.objects.create(**student_data)
            messages.append(f"Created transfer student: {student.get_full_name()}")
        
        # Enroll in class if provided
        enrollment = None
        if target_class:
            try:
                enrollment, created, enroll_messages = StudentEnrollmentService.enroll_student_in_class(
                    student=student,
                    class_instance=target_class,
                    enrollment_type='TRANSFER_IN'
                )
                messages.extend(enroll_messages)
            except ValidationError as e:
                messages.append(f"Could not enroll transfer student: {str(e)}")
        
        logger.info(f"External transfer completed: {student.get_full_name()}")
        return student, enrollment, messages


# =============================================================================
# DATA VALIDATION SERVICES
# =============================================================================

class StudentDataValidationService:
    """Service for validating student data integrity."""
    
    @staticmethod
    def validate_student_enrollment_consistency(student):
        """
        Validate consistency of student enrollment data.
        
        Args:
            student (Student): Student to validate
            
        Returns:
            dict: Validation results with issues found
        """
        issues = []
        
        # Check active enrollments
        active_enrollments = StudentClassEnrollment.objects.filter(
            student=student,
            is_active=True,
            completion_status='ONGOING'
        )
        
        if active_enrollments.count() > 1:
            issues.append(f"Multiple active enrollments found: {active_enrollments.count()}")
        elif active_enrollments.count() == 0 and student.enrollment_status == 'ACTIVE':
            issues.append("Student marked as active but has no active class enrollment")
        
        # Check current level consistency
        if active_enrollments.exists():
            enrollment = active_enrollments.first()
            if student.current_academic_level != enrollment.class_instance.academic_level:
                issues.append(
                    f"Current level mismatch: Student level is {student.current_academic_level}, "
                    f"but enrolled in {enrollment.class_instance.academic_level}"
                )
        
        # Check guardian relationships
        primary_guardians = student.guardian_relationships.filter(
            is_primary=True,
            is_active=True
        ).count()
        
        if primary_guardians == 0:
            issues.append("No primary guardian assigned")
        elif primary_guardians > 1:
            issues.append(f"Multiple primary guardians found: {primary_guardians}")
        
        # Check emergency contacts
        emergency_contacts = student.guardian_relationships.filter(
            emergency_contact_priority__lte=5,
            is_active=True
        ).count()
        
        if emergency_contacts == 0:
            issues.append("No emergency contacts assigned")
        
        return {
            'has_issues': len(issues) > 0,
            'issues': issues,
            'student': student
        }
    
    @staticmethod
    def bulk_validate_student_data(students_queryset):
        """
        Validate multiple students' data integrity.
        
        Args:
            students_queryset (QuerySet): Students to validate
            
        Returns:
            dict: Validation results summary
        """
        total_students = students_queryset.count()
        students_with_issues = []
        
        for student in students_queryset:
            validation = StudentDataValidationService.validate_student_enrollment_consistency(student)
            if validation['has_issues']:
                students_with_issues.append(validation)
        
        return {
            'total_students': total_students,
            'students_with_issues': len(students_with_issues),
            'issues_percentage': round((len(students_with_issues) / total_students) * 100, 1) if total_students > 0 else 0,
            'detailed_issues': students_with_issues
        }