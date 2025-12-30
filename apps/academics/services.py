# academics/services.py

"""
Academic Services Module

Comprehensive business logic services for academic operations:
- Class Enrollment Management
- Student Transfers and Promotions
- Bulk Operations
- Academic Session Management
- Progress Tracking Integration

All services use @transaction.atomic for data consistency
Integrates with fee system for invoice generation
Uses utilities for validation and calculations
"""

from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import Q, Count, Sum, Avg, F
from decimal import Decimal
import logging

# Import models
from .models import (
    Class, 
    AcademicSession, 
    StudentClassEnrollment,
    AcademicProgress,
    Subject,
    ClassSubject,
    Holiday,
)
from students.models import Student

# Import utilities
from .utils import (
    get_current_academic_session,
    get_class_capacity_summary,
    validate_term_number,
    get_session_by_date,
    validate_session_overlap,
    get_working_days,
    close_session,
    reopen_session,
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
        
        Args:
            student (Student): Student to enroll
            class_instance (Class): Class to enroll in
            session (AcademicSession): Academic session
            **kwargs: Additional options
                - enrollment_type: Type of enrollment
                - notes: Enrollment notes
                - send_notifications: Whether to send notifications
                - include_optional_fees: Include optional fees in invoice
                - discount_amount: Discount to apply
                - due_date: Custom due date for invoice
        
        Returns:
            tuple: (enrollment, invoice) - invoice may be None
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
            completion_status='ONGOING',
            is_active=True,
            enrollment_notes=kwargs.get('notes', ''),
            auto_create_invoice=kwargs.get('auto_create_invoice', True)
        )
        
        logger.info(
            f"Created class enrollment for {student.get_full_name()} "
            f"in {class_instance.get_display_name()} ({session.name}) "
            f"with roll number {enrollment.roll_number}"
        )
        
        # =================================================================
        # STEP 3: GENERATE INVOICE (if auto_create_invoice)
        # =================================================================
        
        invoice = None
        if enrollment.auto_create_invoice:
            try:
                # Try to import fee invoice generator
                from fees.invoice_generators import ClassEnrollmentInvoiceGenerator
                
                invoice = ClassEnrollmentInvoiceGenerator.generate(
                    enrollment,
                    include_optional=kwargs.get('include_optional_fees', False),
                    discount_amount=kwargs.get('discount_amount'),
                    custom_due_date=kwargs.get('due_date')
                )
                
                # Link invoice to enrollment
                enrollment.academic_invoice = invoice
                enrollment.save(update_fields=['academic_invoice'])
                
                logger.info(
                    f"Generated academic invoice {invoice.invoice_number} "
                    f"for enrollment {enrollment.pk}"
                )
                
            except ImportError:
                logger.debug("Fee invoice generator not available")
            except Exception as e:
                logger.error(f"Error generating invoice: {e}")
                # Don't fail entire enrollment if invoice generation fails
        
        # =================================================================
        # STEP 4: SEND NOTIFICATIONS (optional)
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
        
        Args:
            enrollment (StudentClassEnrollment): Current enrollment
            new_class_instance (Class): Target class
            reason (str): Reason for transfer
            **kwargs: Additional options
        
        Returns:
            StudentClassEnrollment: New enrollment record
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
            send_notifications=kwargs.get('send_notifications', False),
            auto_create_invoice=False  # Don't create new invoice for transfer
        )
        
        # Link to previous enrollment
        new_enrollment.previous_enrollment = enrollment
        new_enrollment.save(update_fields=['previous_enrollment'])
        
        # Update existing invoice if requested
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
        
        Args:
            enrollment (StudentClassEnrollment): Current enrollment
            next_class_instance (Class): Target class for promotion
            next_session (AcademicSession): Target session
            **kwargs: Additional options
        
        Returns:
            tuple: (new_enrollment, invoice)
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
        
        Args:
            enrollment (StudentClassEnrollment): Enrollment to withdraw
            reason (str): Reason for withdrawal
            withdrawal_date (date): Date of withdrawal
        
        Returns:
            StudentClassEnrollment: Updated enrollment record
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
            try:
                from fees.services import InvoiceService
                
                InvoiceService.cancel_invoice(
                    enrollment.academic_invoice,
                    reason=f"Student withdrawn: {reason}"
                )
            except ImportError:
                logger.debug("Fee service not available for invoice cancellation")
        
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
        logger.debug(f"Would send enrollment notification for {enrollment.student}")
        pass
    
    @staticmethod
    def _send_teacher_notification(enrollment):
        """Send notification to class teacher"""
        # TODO: Implement notification logic
        logger.debug(f"Would send teacher notification for {enrollment.class_instance.class_teacher}")
        pass
    
    # =========================================================================
    # QUERY HELPERS (delegate to utils where appropriate)
    # =========================================================================
    
    @staticmethod
    def get_active_enrollment_for_student(student, session=None):
        """
        Get active class enrollment for student in session.
        
        Args:
            student (Student): Student instance
            session (AcademicSession): Session (optional, uses current if not provided)
            
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
            student (Student): Student instance
            
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
        
        Args:
            students (list): List of Student instances
            class_instance (Class): Class to enroll in
            session (AcademicSession): Academic session
            **kwargs: Additional options
        
        Returns:
            dict: Results with enrolled, failed, invoices lists
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
        
        Args:
            class_instance (Class): Current class
            next_class_instance (Class): Target class for promotion
            next_session (AcademicSession): Target session
            **kwargs: Additional options
        
        Returns:
            dict: Results with promoted, failed, invoices lists
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


# =============================================================================
# ACADEMIC SESSION MANAGEMENT SERVICE
# =============================================================================

class AcademicSessionService:
    """Academic session management operations"""
    
    @staticmethod
    @transaction.atomic
    def create_academic_session(session_data):
        """
        Create new academic session with validation.
        
        Args:
            session_data (dict): Session data
            
        Returns:
            AcademicSession: Created session
        """
        # Validate term number
        term_number = session_data.get('term_number')
        year_name = session_data.get('year_name')
        
        # ✅ Use utility for validation
        is_valid, error_msg, max_periods = validate_term_number(term_number)
        if not is_valid:
            raise ValidationError(error_msg)
        
        # Check for overlapping sessions
        start_date = session_data.get('start_date')
        end_date = session_data.get('end_date')
        
        is_valid_overlap, overlapping = validate_session_overlap(
            start_date, end_date, year_name
        )
        if not is_valid_overlap:
            raise ValidationError(
                f"Session dates overlap with existing sessions: "
                f"{[str(s) for s in overlapping]}"
            )
        
        # Create session
        session = AcademicSession.objects.create(**session_data)
        
        logger.info(f"Created academic session: {session.name}")
        return session
    
    @staticmethod
    @transaction.atomic
    def close_academic_session(session, user=None):
        """
        Close academic session with proper validation.
        
        Args:
            session (AcademicSession): Session to close
            user: User performing closure
            
        Returns:
            tuple: (success, message)
        """
        # ✅ Use utility for closure
        return close_session(session, user)
    
    @staticmethod
    @transaction.atomic
    def reopen_academic_session(session, user=None):
        """
        Reopen closed academic session.
        
        Args:
            session (AcademicSession): Session to reopen
            user: User performing reopen
            
        Returns:
            tuple: (success, message)
        """
        # ✅ Use utility for reopening
        return reopen_session(session, user)
    
    @staticmethod
    def calculate_working_days_in_session(session, exclude_weekends=True):
        """
        Calculate working days in academic session.
        
        Args:
            session (AcademicSession): Session to calculate
            exclude_weekends (bool): Whether to exclude weekends
            
        Returns:
            int: Number of working days
        """
        # ✅ Use utility for calculation
        return get_working_days(
            session.start_date, 
            session.end_date, 
            exclude_weekends
        )


# =============================================================================
# CLASS SUBJECT MANAGEMENT SERVICE
# =============================================================================

class ClassSubjectService:
    """Class subject assignment and management"""
    
    @staticmethod
    @transaction.atomic
    def assign_subject_to_class(class_instance, subject, teacher=None, **kwargs):
        """
        Assign subject to a class with teacher.
        
        Args:
            class_instance (Class): Class to assign to
            subject (Subject): Subject to assign
            teacher: Teacher for the subject (optional)
            **kwargs: Additional assignment data
            
        Returns:
            ClassSubject: Created assignment
        """
        # Check if assignment already exists
        existing = ClassSubject.objects.filter(
            class_instance=class_instance,
            subject=subject
        ).first()
        
        if existing and existing.is_active:
            raise ValidationError(
                f"Subject {subject.name} is already assigned to {class_instance}"
            )
        
        # Create or reactivate assignment
        if existing:
            existing.is_active = True
            existing.teacher = teacher
            for key, value in kwargs.items():
                setattr(existing, key, value)
            existing.save()
            assignment = existing
        else:
            assignment = ClassSubject.objects.create(
                class_instance=class_instance,
                subject=subject,
                teacher=teacher,
                **kwargs
            )
        
        logger.info(
            f"Assigned subject {subject.name} to {class_instance} "
            f"with teacher {teacher.get_full_name() if teacher else 'TBA'}"
        )
        
        return assignment
    
    @staticmethod
    @transaction.atomic
    def bulk_assign_compulsory_subjects(class_instance):
        """
        Auto-assign all compulsory subjects for class academic level.
        
        Args:
            class_instance (Class): Class to assign subjects to
            
        Returns:
            list: List of created assignments
        """
        # Get compulsory subjects for this academic level
        compulsory_subjects = Subject.objects.filter(
            Q(applicable_levels__isnull=True) |
            Q(applicable_levels=class_instance.academic_level),
            is_compulsory=True,
            is_active=True
        ).distinct()
        
        assignments = []
        
        for subject in compulsory_subjects:
            try:
                assignment = ClassSubjectService.assign_subject_to_class(
                    class_instance=class_instance,
                    subject=subject,
                    is_optional=False,
                    hours_per_week=3  # Default hours
                )
                assignments.append(assignment)
            except ValidationError as e:
                logger.warning(f"Could not assign {subject.name}: {e}")
        
        logger.info(
            f"Auto-assigned {len(assignments)} compulsory subjects to {class_instance}"
        )
        
        return assignments


# =============================================================================
# ACADEMIC PROGRESS SERVICE
# =============================================================================

class AcademicProgressService:
    """Academic progress tracking and management"""
    
    @staticmethod
    @transaction.atomic
    def create_or_update_progress(student, academic_session, **progress_data):
        """
        Create or update academic progress record.
        
        Args:
            student (Student): Student
            academic_session (AcademicSession): Academic session
            **progress_data: Progress data fields
            
        Returns:
            AcademicProgress: Progress record
        """
        # Get or create progress record
        progress, created = AcademicProgress.objects.get_or_create(
            student=student,
            academic_session=academic_session,
            defaults=progress_data
        )
        
        if not created:
            # Update existing record
            for key, value in progress_data.items():
                setattr(progress, key, value)
            progress.save()
        
        # Auto-calculate fields
        progress.calculate_attendance_percentage()
        progress.determine_promotion_eligibility()
        
        action = "Created" if created else "Updated"
        logger.info(f"{action} progress record for {student} - {academic_session}")
        
        return progress
    
    @staticmethod
    @transaction.atomic
    def finalize_session_progress(academic_session, user=None):
        """
        Finalize all progress records for an academic session.
        
        Args:
            academic_session (AcademicSession): Session to finalize
            user: User performing finalization
            
        Returns:
            dict: Finalization results
        """
        progress_records = AcademicProgress.objects.filter(
            academic_session=academic_session,
            is_final=False
        )
        
        results = {
            'total': progress_records.count(),
            'finalized': 0,
            'failed': 0,
            'errors': []
        }
        
        for progress in progress_records:
            try:
                success = progress.finalize_record(user=user)
                if success:
                    results['finalized'] += 1
            except Exception as e:
                results['failed'] += 1
                results['errors'].append(f"{progress.student}: {str(e)}")
                logger.error(f"Error finalizing progress for {progress.student}: {e}")
        
        logger.info(
            f"Finalized {results['finalized']}/{results['total']} progress records "
            f"for {academic_session}"
        )
        
        return results


# =============================================================================
# HOLIDAY MANAGEMENT SERVICE
# =============================================================================

class HolidayService:
    """Holiday and calendar management"""
    
    @staticmethod
    @transaction.atomic
    def create_holiday(holiday_data):
        """
        Create holiday with validation.
        
        Args:
            holiday_data (dict): Holiday data
            
        Returns:
            Holiday: Created holiday
        """
        holiday = Holiday.objects.create(**holiday_data)
        
        logger.info(f"Created holiday: {holiday.name} ({holiday.start_date})")
        return holiday
    
    @staticmethod
    def get_holidays_in_session(academic_session):
        """
        Get all holidays within an academic session.
        
        Args:
            academic_session (AcademicSession): Session to check
            
        Returns:
            QuerySet: Holidays in the session period
        """
        from .utils import get_holidays_in_range
        
        return get_holidays_in_range(
            academic_session.start_date,
            academic_session.end_date
        )
    
    @staticmethod
    def calculate_teaching_days(academic_session, exclude_weekends=True):
        """
        Calculate actual teaching days excluding holidays.
        
        Args:
            academic_session (AcademicSession): Session to calculate
            exclude_weekends (bool): Whether to exclude weekends
            
        Returns:
            dict: Teaching days calculation
        """
        total_days = AcademicSessionService.calculate_working_days_in_session(
            academic_session, exclude_weekends
        )
        
        # Get holidays that affect school days
        holidays = HolidayService.get_holidays_in_session(academic_session)
        holiday_days = 0
        
        for holiday in holidays.filter(is_school_closed=True):
            if holiday.end_date:
                holiday_days += get_working_days(
                    holiday.start_date, holiday.end_date, exclude_weekends
                )
            else:
                # Single day holiday
                holiday_days += 1
        
        teaching_days = max(0, total_days - holiday_days)
        
        return {
            'total_calendar_days': total_days,
            'holiday_days': holiday_days,
            'teaching_days': teaching_days,
            'utilization_percentage': round((teaching_days / total_days * 100), 1) if total_days > 0 else 0
        }


# =============================================================================
# VALIDATION AND CONSISTENCY SERVICE
# =============================================================================

class AcademicDataValidationService:
    """Academic data validation and consistency checking"""
    
    @staticmethod
    def validate_enrollment_consistency(academic_session):
        """
        Validate enrollment data consistency for a session.
        
        Args:
            academic_session (AcademicSession): Session to validate
            
        Returns:
            dict: Validation results
        """
        issues = []
        
        # Check for duplicate active enrollments
        duplicates = Student.objects.annotate(
            active_enrollment_count=Count(
                'class_enrollments',
                filter=Q(
                    class_enrollments__academic_session=academic_session,
                    class_enrollments__is_active=True,
                    class_enrollments__completion_status='ONGOING'
                )
            )
        ).filter(active_enrollment_count__gt=1)
        
        if duplicates.exists():
            issues.append(f"{duplicates.count()} students have multiple active enrollments")
        
        # Check for enrollments without roll numbers
        missing_roll_numbers = StudentClassEnrollment.objects.filter(
            academic_session=academic_session,
            is_active=True,
            roll_number__in=['', None]
        ).count()
        
        if missing_roll_numbers > 0:
            issues.append(f"{missing_roll_numbers} enrollments missing roll numbers")
        
        # Check for over-capacity classes
        over_capacity = Class.objects.annotate(
            current_enrollment=Count(
                'enrollments',
                filter=Q(
                    enrollments__academic_session=academic_session,
                    enrollments__is_active=True
                )
            )
        ).filter(current_enrollment__gt=F('max_students')).count()
        
        if over_capacity > 0:
            issues.append(f"{over_capacity} classes are over capacity")
        
        return {
            'has_issues': len(issues) > 0,
            'issues': issues,
            'session': academic_session
        }
    
    @staticmethod
    def fix_roll_number_gaps(class_instance, academic_session):
        """
        Fix gaps in roll number sequence for a class.
        
        Args:
            class_instance (Class): Class to fix
            academic_session (AcademicSession): Session to fix
            
        Returns:
            int: Number of roll numbers updated
        """
        from .utils import reset_class_roll_numbers
        
        return reset_class_roll_numbers(class_instance, academic_session)