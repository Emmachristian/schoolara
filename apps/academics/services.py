# academics/services.py
"""
Student enrolment services.

RESPONSIBILITY BOUNDARIES
--------------------------
BulkEnrollmentService
    Orchestrates bulk enrolment: pre-flight validation, DB writes (atomic
    per student), invoice generation, and result reporting.

    Pre-flight vs model-level validation
        _pre_validate() performs BLOCKING pre-flight checks that catch problems
        before any DB write is attempted -- session state, class/session mismatch,
        date range, capacity, and already-enrolled detection.  These checks
        intentionally overlap with model-level constraints (StudentClassEnrollment
        clean() / DB UniqueConstraints) because catching them early produces
        cleaner user-facing errors.  If a pre-flight check passes but a model
        constraint fires anyway (e.g. a race condition between two concurrent
        requests), only that student's savepoint is rolled back -- successful
        enrolments are preserved.

    ATOMICITY MODEL:
        Each student is enrolled inside its own transaction.atomic() savepoint
        so a single failure (ValidationError, IntegrityError, or any other
        exception) does not roll back enrolments that already succeeded.
        This matches the per-student failure handling in _create_invoices().

StudentPromotionService
    Thin wrapper around BulkEnrollmentService for the promotion flow.
    Marks prior enrolments COMPLETED before delegating to bulk enrolment.

EnrollmentValidationService
    Stateless, read-only pre-flight helpers for the UI (single-student checks).
    Does NOT create or modify any records.
"""

from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError
from django.utils import timezone
from typing import List, Dict, Tuple, Optional

from students.models import Student
from academics.models import AcademicSession, Class, StudentClassEnrollment
from core.utils import get_school_today

import logging

logger = logging.getLogger(__name__)


# =============================================================================
# BULK ENROLMENT SERVICE
# =============================================================================

class BulkEnrollmentService:
    """
    Orchestrate bulk student enrolments.

    Usage::

        service = BulkEnrollmentService()
        result  = service.enroll_students(
            student_ids=[1, 2, 3],
            academic_session=session,
            class_instance=class_obj,
            enrollment_type='PROMOTED',
            auto_create_invoice=True,
            created_by=request.user,
        )
        if result['success']:
            print(f"Enrolled {result['enrolled_count']} students")
        else:
            print(result['errors'])
    """

    def __init__(self):
        self.errors            = []
        self.warnings          = []
        self.enrolled_students = []
        self.failed_students   = []

    # -------------------------------------------------------------------------
    # PUBLIC API
    # -------------------------------------------------------------------------

    def enroll_students(
        self,
        student_ids: List,
        academic_session: AcademicSession,
        class_instance: Class,
        enrollment_date=None,
        enrollment_type: str = 'NEW',
        auto_create_invoice: bool = True,
        send_notification: bool = False,
        enrollment_notes: str = '',
        created_by=None,
        dry_run: bool = False,
    ) -> Dict:
        """
        Enrol multiple students into a class.

        Args:
            student_ids:          List of student PKs to enrol.
            academic_session:     Target academic session.
            class_instance:       Target class.
            enrollment_date:      Date of enrolment (defaults to school today).
            enrollment_type:      One of StudentClassEnrollment.ENROLLMENT_TYPE_CHOICES.
            auto_create_invoice:  Create fee invoices after enrolment.
            send_notification:    Reserved -- not yet implemented.
            enrollment_notes:     Free-text note written to every enrolment record.
            created_by:           User performing the operation (for audit).
            dry_run:              Validate only; make no DB changes.

        Returns:
            Dict with keys:

            ==================  ================================================
            success             bool
            enrolled_count      int
            failed_count        int
            enrollments         list[StudentClassEnrollment]
            errors              list[str]
            warnings            list[str]
            dry_run             bool  (only present when dry_run=True)
            would_enroll        int   (only present when dry_run=True)
            ==================  ================================================
        """
        # Reset state so the service instance can be reused.
        self.errors            = []
        self.warnings          = []
        self.enrolled_students = []
        self.failed_students   = []

        if not enrollment_date:
            enrollment_date = get_school_today()

        logger.info(
            "Starting bulk enrolment: %d students -> %s (%s)",
            len(student_ids),
            class_instance,
            academic_session,
        )

        # -- Step 1: pre-flight validation ------------------------------------
        validation = self._pre_validate(
            student_ids=student_ids,
            academic_session=academic_session,
            class_instance=class_instance,
            enrollment_date=enrollment_date,
        )

        if not validation['valid']:
            return self._result(
                success=False,
                enrolled=[],
                failed_count=len(student_ids),
                errors=validation['errors'],
            )

        students = validation['students']

        # -- Step 2: dry-run short-circuit ------------------------------------
        if dry_run:
            return {
                'success':        True,
                'enrolled_count': 0,
                'failed_count':   0,
                'enrollments':    [],
                'errors':         [],
                'warnings':       self.warnings,
                'dry_run':        True,
                'would_enroll':   students.count(),
            }

        # -- Step 3: DB writes (per-student savepoints) -----------------------
        enrollments = self._perform_bulk_enrollment(
            students=students,
            academic_session=academic_session,
            class_instance=class_instance,
            enrollment_date=enrollment_date,
            enrollment_type=enrollment_type,
            enrollment_notes=enrollment_notes,
            auto_create_invoice=auto_create_invoice,
            created_by=created_by,
        )

        # -- Step 4: post-enrolment invoice generation ------------------------
        if enrollments and auto_create_invoice:
            self._create_invoices(enrollments)
        else:
            logger.info(
                "Invoice auto-creation skipped (auto_create_invoice=%s)",
                auto_create_invoice,
            )

        # -- Step 5: notification stub ----------------------------------------
        if send_notification:
            self.warnings.append(
                "Notification feature is not yet implemented. "
                "Please notify parents/guardians manually."
            )

        result = self._result(
            success=len(enrollments) > 0,
            enrolled=enrollments,
            failed_count=len(self.failed_students),
        )

        logger.info(
            "Bulk enrolment completed: %d succeeded, %d failed",
            result['enrolled_count'],
            result['failed_count'],
        )
        return result

    # -------------------------------------------------------------------------
    # PRIVATE HELPERS
    # -------------------------------------------------------------------------

    def _result(self, *, success, enrolled, failed_count, errors=None) -> Dict:
        """Build the standard result dict."""
        return {
            'success':        success,
            'enrolled_count': len(enrolled),
            'failed_count':   failed_count,
            'enrollments':    enrolled,
            'errors':         errors if errors is not None else self.errors,
            'warnings':       self.warnings,
        }

    def _pre_validate(
        self,
        student_ids: List,
        academic_session: AcademicSession,
        class_instance: Class,
        enrollment_date,
    ) -> Dict:
        """
        Blocking pre-flight checks before any DB write is attempted.

        These are UX-level guards that produce clean error messages.  They
        intentionally overlap with model constraints -- see module docstring.

        Returns:
            Dict with keys:

            =========  =========================================================
            valid      bool
            errors     list[str]
            students   QuerySet  (filtered to those not already enrolled)
            =========  =========================================================
        """
        errors = []

        # -- Session state checks ---------------------------------------------
        if academic_session.is_academically_closed:
            errors.append(f"{academic_session.name} is academically closed.")

        if not academic_session.is_active:
            errors.append(f"{academic_session.name} is not active.")

        # -- Class / session coherence ----------------------------------------
        if class_instance.academic_session != academic_session:
            errors.append(
                f"Class '{class_instance}' does not belong to "
                f"session '{academic_session.name}'."
            )

        # -- Enrolment date within session bounds -----------------------------
        if (
            enrollment_date < academic_session.start_date
            or enrollment_date > academic_session.end_date
        ):
            errors.append(
                f"Enrolment date {enrollment_date} must be between "
                f"{academic_session.start_date} and {academic_session.end_date}."
            )

        # -- Fetch students and detect missing IDs ----------------------------
        students = Student.objects.filter(
            id__in=student_ids
        ).select_related('current_academic_level')

        found_ids   = set(str(pk) for pk in students.values_list('id', flat=True))
        missing_ids = set(str(pk) for pk in student_ids) - found_ids
        if missing_ids:
            errors.append(f"Some students were not found (IDs: {sorted(missing_ids)}).")

        # -- Capacity check ---------------------------------------------------
        available_capacity = class_instance.get_available_capacity()
        if len(student_ids) > available_capacity:
            errors.append(
                f"Class has only {available_capacity} available spot(s), "
                f"but attempting to enrol {len(student_ids)} student(s)."
            )

        # Early return -- no point querying existing enrolments if the
        # checks above already failed.
        if errors:
            return {'valid': False, 'errors': errors, 'students': students}

        # -- Warn about already-enrolled students and exclude them ------------
        already_enrolled = StudentClassEnrollment.objects.filter(
            academic_session=academic_session,
            student_id__in=student_ids,
            is_active=True,
            completion_status='ONGOING',
        ).select_related('student', 'class_instance')

        for enrolment in already_enrolled:
            self.warnings.append(
                f"{enrolment.student.get_full_name()} is already enrolled in "
                f"'{enrolment.class_instance}' -- skipping."
            )
            students = students.exclude(id=enrolment.student_id)

        return {'valid': True, 'errors': [], 'students': students}

    def _perform_bulk_enrollment(
        self,
        students,
        academic_session: AcademicSession,
        class_instance: Class,
        enrollment_date,
        enrollment_type: str,
        enrollment_notes: str,
        auto_create_invoice: bool,
        created_by=None,
    ) -> List[StudentClassEnrollment]:
        """
        Write enrolment records, one atomic savepoint per student.

        Each student is wrapped in its own transaction.atomic() so a
        ValidationError or IntegrityError for one student only rolls back
        that student's savepoint — all previously succeeded saves are kept.
        This is consistent with the per-student failure handling in
        _create_invoices().

        Failures are collected in self.errors / self.failed_students and
        are surfaced to the caller via the result dict.  The exception is
        NOT re-raised so the loop continues to the next student.

        ``auto_create_invoice`` is written onto every enrolment record so
        that any post-save signal wired to that field fires (or does not
        fire) in line with the user's explicit choice.
        """
        enrollments = []

        for student in students:
            try:
                with transaction.atomic():
                    enrolment = StudentClassEnrollment(
                        student=student,
                        academic_session=academic_session,
                        class_instance=class_instance,
                        enrollment_date=enrollment_date,
                        enrollment_type=enrollment_type,
                        enrollment_notes=enrollment_notes,
                        is_active=True,
                        completion_status='ONGOING',
                        auto_create_invoice=auto_create_invoice,
                    )
                    enrolment.full_clean()
                    enrolment.save()

                enrollments.append(enrolment)
                self.enrolled_students.append(student)

                logger.debug(
                    "Enrolled %s (ID: %s) into %s",
                    student.get_full_name(),
                    student.id,
                    class_instance,
                )

            except (ValidationError, IntegrityError) as exc:
                error_msg = f"{student.get_full_name()}: {exc}"
                self.errors.append(error_msg)
                self.failed_students.append(student)
                logger.error("Enrolment constraint error: %s", error_msg)

            except Exception as exc:
                error_msg = f"{student.get_full_name()}: {exc}"
                self.errors.append(error_msg)
                self.failed_students.append(student)
                logger.exception("Unexpected error during enrolment: %s", error_msg)

        return enrollments

    def _create_invoices(self, enrollments: List[StudentClassEnrollment]) -> None:
        """
        Generate fee invoices for a list of enrolment records.

        Uses ``generate_student_enrollment_invoice()`` from
        ``fees.invoice_generators`` (the current public API).  Failures are
        collected as warnings rather than exceptions so a missing fee structure
        for one student does not prevent invoices being created for others.
        """
        logger.info("Creating invoices for %d enrolment(s)", len(enrollments))

        try:
            from fees.invoice_generators import (
                generate_student_enrollment_invoice,
                FeeStructureNotFoundError,
            )
        except ImportError as exc:
            logger.error("Invoice generator not available: %s", exc)
            self.warnings.append(
                "Invoice auto-creation is not available. "
                "Please create invoices manually."
            )
            return

        invoices_created = 0

        for enrolment in enrollments:
            try:
                invoice = generate_student_enrollment_invoice(enrolment)

                # Confirm the link in case the generator skipped the update step.
                if not enrolment.academic_invoice:
                    enrolment.academic_invoice = invoice
                    enrolment.save(update_fields=['academic_invoice'])

                logger.debug(
                    "Created invoice %s for %s",
                    invoice.invoice_number,
                    enrolment.student.get_full_name(),
                )
                invoices_created += 1

            except FeeStructureNotFoundError as exc:
                msg = (
                    f"Cannot create invoice for "
                    f"{enrolment.student.get_full_name()}: {exc}"
                )
                self.warnings.append(msg)
                logger.error(msg)

            except Exception as exc:
                msg = (
                    f"Failed to create invoice for "
                    f"{enrolment.student.get_full_name()}: {exc}"
                )
                self.warnings.append(msg)
                logger.warning(msg)

        logger.info("Successfully created %d invoice(s)", invoices_created)


# =============================================================================
# PROMOTION SERVICE
# =============================================================================

class StudentPromotionService:
    """
    Promote students from one class / session to another.

    Thin wrapper around :class:`BulkEnrollmentService` that additionally marks
    prior enrolments as COMPLETED before delegating to the bulk flow.

    Usage::

        service = StudentPromotionService()
        result  = service.promote_students(
            from_session=current_session,
            to_session=next_session,
            from_class=current_class,
            to_class=next_class,
        )
    """

    def __init__(self):
        self._bulk_service = BulkEnrollmentService()

    def promote_students(
        self,
        from_session: AcademicSession,
        to_session: AcademicSession,
        from_class: Class,
        to_class: Class,
        student_ids: Optional[List[int]] = None,
        auto_create_invoice: bool = True,
        send_notification: bool = False,
        created_by=None,
    ) -> Dict:
        """
        Promote students from ``from_class`` (``from_session``) to
        ``to_class`` (``to_session``).

        Args:
            from_session:         Session the students are currently in.
            to_session:           Session to promote into.
            from_class:           Class the students are currently in.
            to_class:             Destination class.
            student_ids:          Specific enrolment PKs to promote.
                                  ``None`` promotes all ONGOING enrolments in
                                  ``from_class``.
            auto_create_invoice:  Create invoices for promoted students.
            send_notification:    Reserved -- not yet implemented.
            created_by:           User performing the operation.

        Returns:
            Standard :class:`BulkEnrollmentService` result dict.
        """
        logger.info(
            "Starting promotion: %s (%s) -> %s (%s)",
            from_class,
            from_session,
            to_class,
            to_session,
        )

        # -- Identify enrolments to promote -----------------------------------
        source_qs = StudentClassEnrollment.objects.filter(
            academic_session=from_session,
            class_instance=from_class,
            is_active=True,
            completion_status='ONGOING',
        )
        if student_ids:
            source_qs = source_qs.filter(id__in=student_ids)

        source_qs = source_qs.select_related('student')

        student_ids_to_promote = list(
            source_qs.values_list('student_id', flat=True)
        )

        if not student_ids_to_promote:
            return {
                'success':        False,
                'enrolled_count': 0,
                'failed_count':   0,
                'enrollments':    [],
                'errors':         ['No eligible students found for promotion.'],
                'warnings':       [],
            }

        # -- Mark prior enrolments COMPLETED ----------------------------------
        source_qs.update(
            completion_status='COMPLETED',
            completion_date=from_session.end_date,
        )

        # -- Enrol in the new class -------------------------------------------
        result = self._bulk_service.enroll_students(
            student_ids=student_ids_to_promote,
            academic_session=to_session,
            class_instance=to_class,
            enrollment_date=to_session.start_date,
            enrollment_type='PROMOTED',
            auto_create_invoice=auto_create_invoice,
            send_notification=send_notification,
            enrollment_notes=f"Promoted from {from_class}",
            created_by=created_by,
        )

        # -- Back-link new enrolments to their predecessors -------------------
        if result['success']:
            for enrolment in result['enrollments']:
                previous = StudentClassEnrollment.objects.filter(
                    student=enrolment.student,
                    academic_session=from_session,
                    class_instance=from_class,
                ).first()

                if previous:
                    enrolment.previous_enrollment = previous
                    enrolment.save(update_fields=['previous_enrollment'])

        logger.info(
            "Promotion completed: %d promoted, %d failed",
            result['enrolled_count'],
            result['failed_count'],
        )
        return result


# =============================================================================
# ENROLMENT VALIDATION SERVICE  (read-only, UI pre-flight)
# =============================================================================

class EnrollmentValidationService:
    """
    Stateless read-only helpers for single-student pre-flight checks in the UI.

    These methods make **no** database writes.  They are intended to power
    real-time feedback (e.g. HTMX field validation) before the user submits
    the enrolment form.

    .. note::
        These checks overlap with ``StudentClassEnrollment.clean()`` by design.
        The model constraint is the authoritative guard; these methods exist
        purely to surface friendly messages in the UI before the form is
        submitted.
    """

    @staticmethod
    def validate_student_enrollment(
        student: Student,
        academic_session: AcademicSession,
        class_instance: Class,
    ) -> Tuple[bool, List[str]]:
        """
        Check whether a student can be enrolled.

        Args:
            student:          Student to check.
            academic_session: Target session.
            class_instance:   Target class.

        Returns:
            Tuple of ``(is_valid: bool, error_messages: list[str])``.
        """
        errors = []

        if student.enrollment_status != 'ACTIVE':
            errors.append(
                f"Student status is '{student.get_enrollment_status_display()}', "
                f"not 'ACTIVE'."
            )

        if not academic_session.is_active:
            errors.append("Academic session is not active.")

        if academic_session.is_academically_closed:
            errors.append("Academic session is closed.")

        if not class_instance.has_capacity():
            errors.append("Class has reached maximum capacity.")

        existing = StudentClassEnrollment.objects.filter(
            student=student,
            academic_session=academic_session,
            is_active=True,
            completion_status='ONGOING',
        ).first()

        if existing:
            errors.append(
                f"Already enrolled in '{existing.class_instance}' for this session."
            )

        return len(errors) == 0, errors

    @staticmethod
    def get_enrollment_warnings(
        student: Student,
        class_instance: Class,
    ) -> List[str]:
        """
        Return non-blocking warnings about an enrolment (e.g. unpaid fees,
        age-appropriateness, incomplete academic progress).

        Extend this method as school-specific checks are added.

        Args:
            student:        Student being enrolled.
            class_instance: Target class.

        Returns:
            List of warning strings (may be empty).
        """
        # Placeholder -- add checks here as requirements grow:
        #   - student has outstanding fee balance
        #   - student age is outside the normal range for this level
        #   - student's previous academic progress record is incomplete
        return []