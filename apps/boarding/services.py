# boarding/services.py
"""
Boarding enrolment services.

RESPONSIBILITY BOUNDARIES
--------------------------
BulkBoardingEnrollmentService
    Orchestrates bulk boarding enrolment: pre-flight validation, DB writes
    (atomic per student), invoice generation, and result reporting.

    Pre-flight vs model-level validation
        _pre_validate() performs BLOCKING pre-flight checks that catch problems
        before any DB write is attempted — session state, dormitory availability,
        capacity, gender compatibility, date range, and already-enrolled
        detection.  These checks intentionally overlap with model-level
        constraints (BoardingEnrollment.clean() / DB UniqueConstraints) because
        catching them early produces cleaner user-facing errors.  If a pre-flight
        check passes but a model constraint fires anyway (e.g. a race condition),
        only that student's savepoint is rolled back — successful enrolments are
        preserved.

    ATOMICITY MODEL:
        Each student is enrolled inside its own transaction.atomic() savepoint
        so a single failure (ValidationError, IntegrityError, or any other
        exception) does not roll back enrolments that already succeeded.
        This is consistent with the per-student failure handling in
        _create_invoices().

    INVOICE CREATION:
        Invoice creation is handled EXPLICITLY by _create_invoices() rather than
        relying on the post_save signal in boarding/signals.py.  The signal's
        auto_add_boarding_fees_to_student_invoice() is designed for single
        enrolments created from the UI.  For bulk enrolment, explicit control
        gives cleaner error reporting — invoice failures appear as warnings in
        the result dict rather than being silently swallowed by the signal.

        To prevent double-invoice creation, enrolments created by this service
        have auto_create_invoice=False.  The service calls _create_invoices()
        directly after the DB writes complete.

BoardingEnrollmentValidationService
    Stateless, read-only pre-flight helpers for the UI (single-student checks).
    Does NOT create or modify any records.  Intended to power real-time HTMX
    field validation before the user submits the enrolment form.
"""

from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError
from django.utils import timezone
from typing import List, Dict, Tuple, Optional

from students.models import Student
from academics.models import AcademicSession
from boarding.models import Dormitory, BoardingEnrollment
from core.utils import get_school_today

import logging

logger = logging.getLogger(__name__)


# =============================================================================
# BULK BOARDING ENROLMENT SERVICE
# =============================================================================

class BulkBoardingEnrollmentService:
    """
    Orchestrate bulk student boarding enrolments.

    Usage::

        service = BulkBoardingEnrollmentService()
        result  = service.enroll_students(
            student_ids=[1, 2, 3],
            academic_session=session,
            dormitory=dormitory,
            boarding_type='FULL_BOARDER',
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
        dormitory: Dormitory,
        boarding_type: str,
        enrollment_date=None,
        effective_start_date=None,
        effective_end_date=None,
        boarding_days: Optional[List[str]] = None,
        auto_create_invoice: bool = True,
        require_guardian_consent: bool = False,
        reason_for_boarding: str = '',
        enrollment_notes: str = '',
        created_by=None,
        dry_run: bool = False,
    ) -> Dict:
        """
        Enrol multiple students into a dormitory for an academic session.

        Args:
            student_ids:             List of student PKs to enrol.
            academic_session:        Target academic session.
            dormitory:               Target dormitory.
            boarding_type:           One of BoardingEnrollment.BOARDING_TYPE_CHOICES.
            enrollment_date:         Date of enrolment (defaults to school today).
            effective_start_date:    Date boarding actually starts (defaults to
                                     enrollment_date).
            effective_end_date:      Date boarding ends (defaults to session
                                     end_date).
            boarding_days:           Required for FLEXI_BOARDER; ignored otherwise.
            auto_create_invoice:     Create boarding invoices after enrolment.
            require_guardian_consent: Mark enrolments as requiring consent.
            reason_for_boarding:     Free-text reason written to every record.
            enrollment_notes:        Additional notes written to every record.
            created_by:              User performing the operation (for audit).
            dry_run:                 Validate only; make no DB changes.

        Returns:
            Dict with keys:

            ==================  ================================================
            success             bool
            enrolled_count      int
            failed_count        int
            enrollments         list[BoardingEnrollment]
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

        today = get_school_today()

        if not enrollment_date:
            enrollment_date = today
        if not effective_start_date:
            effective_start_date = enrollment_date
        if not effective_end_date and academic_session.end_date:
            effective_end_date = academic_session.end_date

        logger.info(
            "Starting bulk boarding enrolment: %d students -> %s (%s)",
            len(student_ids),
            dormitory,
            academic_session,
        )

        # -- Step 1: pre-flight validation ------------------------------------
        validation = self._pre_validate(
            student_ids=student_ids,
            academic_session=academic_session,
            dormitory=dormitory,
            boarding_type=boarding_type,
            enrollment_date=enrollment_date,
            effective_start_date=effective_start_date,
            boarding_days=boarding_days,
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
            dormitory=dormitory,
            boarding_type=boarding_type,
            enrollment_date=enrollment_date,
            effective_start_date=effective_start_date,
            effective_end_date=effective_end_date,
            boarding_days=boarding_days,
            require_guardian_consent=require_guardian_consent,
            reason_for_boarding=reason_for_boarding,
            enrollment_notes=enrollment_notes,
        )

        # -- Step 4: post-enrolment invoice generation ------------------------
        if enrollments and auto_create_invoice:
            self._create_invoices(enrollments)
        else:
            logger.info(
                "Invoice auto-creation skipped (auto_create_invoice=%s)",
                auto_create_invoice,
            )

        result = self._result(
            success=len(enrollments) > 0,
            enrolled=enrollments,
            failed_count=len(self.failed_students),
        )

        logger.info(
            "Bulk boarding enrolment completed: %d succeeded, %d failed",
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
        dormitory: Dormitory,
        boarding_type: str,
        enrollment_date,
        effective_start_date,
        boarding_days: Optional[List[str]],
    ) -> Dict:
        """
        Blocking pre-flight checks before any DB write is attempted.

        These are UX-level guards that produce clean error messages.  They
        intentionally overlap with model constraints — see module docstring.

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
            errors.append(
                f"Academic session '{academic_session.name}' is academically closed."
            )

        if not academic_session.is_active:
            errors.append(
                f"Academic session '{academic_session.name}' is not active."
            )

        # -- Dormitory state checks -------------------------------------------
        if not dormitory.is_active:
            errors.append(f"Dormitory '{dormitory.name}' is not active.")

        if not dormitory.is_available_for_new_admissions:
            errors.append(
                f"Dormitory '{dormitory.name}' is not available for new admissions."
            )

        if dormitory.maintenance_status in ('CONDEMNED', 'UNDER_MAINTENANCE'):
            errors.append(
                f"Dormitory '{dormitory.name}' is currently "
                f"{dormitory.get_maintenance_status_display().lower()}."
            )

        # -- Enrollment date within session bounds ----------------------------
        if (
            enrollment_date < academic_session.start_date
            or enrollment_date > academic_session.end_date
        ):
            errors.append(
                f"Enrolment date {enrollment_date} must be between "
                f"{academic_session.start_date} and {academic_session.end_date}."
            )

        # -- Effective start date within session bounds -----------------------
        if effective_start_date < academic_session.start_date:
            errors.append(
                f"Effective start date {effective_start_date} cannot be before "
                f"session start date {academic_session.start_date}."
            )

        # -- Boarding days required for flexible boarders ---------------------
        if boarding_type == 'FLEXI_BOARDER':
            if not boarding_days or len(boarding_days) == 0:
                errors.append(
                    "Boarding days must be specified for flexible boarders."
                )

        # -- Fetch students and detect missing IDs ----------------------------
        students = Student.objects.filter(
            id__in=student_ids
        ).select_related('current_academic_level')

        found_ids   = set(str(pk) for pk in students.values_list('id', flat=True))
        missing_ids = set(str(pk) for pk in student_ids) - found_ids
        if missing_ids:
            errors.append(
                f"Some students were not found (IDs: {sorted(missing_ids)})."
            )

        # -- Gender compatibility check (per student) -------------------------
        if dormitory.dormitory_type != 'MIXED':
            incompatible = []
            for student in students:
                if not dormitory.can_accommodate_gender(student.gender):
                    incompatible.append(student.get_full_name())
            if incompatible:
                errors.append(
                    f"The following students are not compatible with "
                    f"'{dormitory.name}' ({dormitory.get_dormitory_type_display()}): "
                    f"{', '.join(incompatible)}."
                )

        # -- Capacity check ---------------------------------------------------
        available_capacity = dormitory.get_available_capacity()
        if len(student_ids) > available_capacity:
            errors.append(
                f"Dormitory '{dormitory.name}' has only {available_capacity} "
                f"available bed(s), but attempting to enrol {len(student_ids)} "
                f"student(s)."
            )

        # Early return — no point querying existing enrolments if the
        # checks above already failed.
        if errors:
            return {'valid': False, 'errors': errors, 'students': students}

        # -- Warn about already-enrolled students and exclude them ------------
        #
        # Split into two buckets so the caller can distinguish:
        #   - enrolled in THIS dormitory (skip silently with a note)
        #   - enrolled in a DIFFERENT dormitory this session (warn more loudly)

        already_this_dormitory = BoardingEnrollment.objects.filter(
            academic_session=academic_session,
            dormitory=dormitory,
            student_id__in=student_ids,
            status__in=('PENDING', 'ACTIVE'),
        ).select_related('student')

        for enrolment in already_this_dormitory:
            self.warnings.append(
                f"{enrolment.student.get_full_name()} is already enrolled in "
                f"'{dormitory.name}' — skipping."
            )
            students = students.exclude(id=enrolment.student_id)

        already_other_dormitory = BoardingEnrollment.objects.filter(
            academic_session=academic_session,
            status__in=('PENDING', 'ACTIVE'),
            student_id__in=[str(s.id) for s in students],
        ).exclude(
            dormitory=dormitory,
        ).select_related('student', 'dormitory')

        for enrolment in already_other_dormitory:
            self.warnings.append(
                f"{enrolment.student.get_full_name()} is already enrolled in "
                f"'{enrolment.dormitory.name}' (different dormitory) — skipping."
            )
            students = students.exclude(id=enrolment.student_id)

        return {'valid': True, 'errors': [], 'students': students}

    def _perform_bulk_enrollment(
        self,
        students,
        academic_session: AcademicSession,
        dormitory: Dormitory,
        boarding_type: str,
        enrollment_date,
        effective_start_date,
        effective_end_date,
        boarding_days: Optional[List[str]],
        require_guardian_consent: bool,
        reason_for_boarding: str,
        enrollment_notes: str,
    ) -> List[BoardingEnrollment]:
        """
        Write enrolment records, one atomic savepoint per student.

        Each student is wrapped in its own transaction.atomic() so a
        ValidationError or IntegrityError for one student only rolls back
        that student's savepoint — all previously succeeded saves are kept.

        auto_create_invoice is set to False on every record because this
        service calls _create_invoices() explicitly after the loop.  This
        prevents the post_save signal from also attempting invoice creation
        and potentially doubling up.

        Failures are collected in self.errors / self.failed_students and
        surfaced to the caller via the result dict.  The exception is NOT
        re-raised so the loop continues to the next student.
        """
        enrollments = []

        for student in students:
            try:
                with transaction.atomic():
                    enrolment = BoardingEnrollment(
                        student=student,
                        academic_session=academic_session,
                        dormitory=dormitory,
                        boarding_type=boarding_type,
                        enrollment_date=enrollment_date,
                        effective_start_date=effective_start_date,
                        effective_end_date=effective_end_date,
                        boarding_days=boarding_days if boarding_type == 'FLEXI_BOARDER' else None,
                        guardian_consent=False,
                        reason_for_boarding=reason_for_boarding,
                        admin_notes=enrollment_notes,
                        status='PENDING',
                        # Disable signal-based invoice creation — this service
                        # calls _create_invoices() explicitly after the loop.
                        auto_create_invoice=False,
                    )
                    enrolment.full_clean()
                    enrolment.save()

                enrollments.append(enrolment)
                self.enrolled_students.append(student)

                logger.debug(
                    "Enrolled %s (ID: %s) into %s",
                    student.get_full_name(),
                    student.id,
                    dormitory,
                )

            except (ValidationError, IntegrityError) as exc:
                error_msg = f"{student.get_full_name()}: {exc}"
                self.errors.append(error_msg)
                self.failed_students.append(student)
                logger.error("Boarding enrolment constraint error: %s", error_msg)

            except Exception as exc:
                error_msg = f"{student.get_full_name()}: {exc}"
                self.errors.append(error_msg)
                self.failed_students.append(student)
                logger.exception(
                    "Unexpected error during boarding enrolment: %s", error_msg
                )

        return enrollments

    def _create_invoices(
        self, enrollments: List[BoardingEnrollment]
    ) -> None:
        """
        Generate boarding fee invoices for a list of enrolment records.

        Attempts to find and use the appropriate fee structure for each
        student based on their boarding type and academic session.  Failures
        are collected as warnings rather than exceptions so a missing fee
        structure for one student does not prevent invoices being created
        for others.

        On success, links the created invoice to the enrolment record via
        boarding_invoice so the pre_delete signal can find it later.
        """
        logger.info(
            "Creating boarding invoices for %d enrolment(s)", len(enrollments)
        )

        try:
            from fees.invoice_generators import (
                generate_boarding_enrollment_invoice,
                FeeStructureNotFoundError,
            )
        except ImportError as exc:
            logger.error("Boarding invoice generator not available: %s", exc)
            self.warnings.append(
                "Boarding invoice auto-creation is not available. "
                "Please create invoices manually."
            )
            return

        invoices_created = 0

        for enrolment in enrollments:
            try:
                invoice = generate_boarding_enrollment_invoice(enrolment)

                # Confirm the link in case the generator skipped the update step.
                if not enrolment.boarding_invoice:
                    enrolment.boarding_invoice = invoice
                    enrolment.save(update_fields=['boarding_invoice'])

                logger.debug(
                    "Created boarding invoice %s for %s",
                    invoice.invoice_number,
                    enrolment.student.get_full_name(),
                )
                invoices_created += 1

            except FeeStructureNotFoundError as exc:
                msg = (
                    f"Cannot create boarding invoice for "
                    f"{enrolment.student.get_full_name()}: {exc}"
                )
                self.warnings.append(msg)
                logger.error(msg)

            except Exception as exc:
                msg = (
                    f"Failed to create boarding invoice for "
                    f"{enrolment.student.get_full_name()}: {exc}"
                )
                self.warnings.append(msg)
                logger.warning(msg)

        logger.info(
            "Successfully created %d boarding invoice(s)", invoices_created
        )


# =============================================================================
# BOARDING ENROLMENT VALIDATION SERVICE  (read-only, UI pre-flight)
# =============================================================================

class BoardingEnrollmentValidationService:
    """
    Stateless read-only helpers for single-student pre-flight checks in the UI.

    These methods make **no** database writes.  They are intended to power
    real-time HTMX field validation before the user submits the boarding
    enrolment form.

    .. note::
        These checks overlap with ``BoardingEnrollment.clean()`` by design.
        The model constraint is the authoritative guard; these methods exist
        purely to surface friendly messages in the UI before the form is
        submitted.
    """

    @staticmethod
    def validate_student_boarding(
        student: Student,
        academic_session: AcademicSession,
        dormitory: Dormitory,
    ) -> Tuple[bool, List[str]]:
        """
        Check whether a student can be enrolled in boarding.

        Args:
            student:          Student to check.
            academic_session: Target session.
            dormitory:        Target dormitory.

        Returns:
            Tuple of ``(is_valid: bool, error_messages: list[str])``.
        """
        errors = []

        # Student must be actively enrolled in the school
        if student.enrollment_status != 'ACTIVE':
            errors.append(
                f"Student status is '{student.get_enrollment_status_display()}', "
                f"not 'ACTIVE'."
            )

        # Session checks
        if not academic_session.is_active:
            errors.append("Academic session is not active.")

        if academic_session.is_academically_closed:
            errors.append("Academic session is academically closed.")

        # Dormitory checks
        if not dormitory.is_active:
            errors.append(f"Dormitory '{dormitory.name}' is not active.")

        if not dormitory.is_available_for_new_admissions:
            errors.append(
                f"Dormitory '{dormitory.name}' is not accepting new admissions."
            )

        if not dormitory.has_capacity():
            errors.append(
                f"Dormitory '{dormitory.name}' has reached maximum capacity."
            )

        # Gender compatibility
        if not dormitory.can_accommodate_gender(student.gender):
            errors.append(
                f"Dormitory '{dormitory.name}' "
                f"({dormitory.get_dormitory_type_display()}) cannot accommodate "
                f"{student.get_gender_display()} students."
            )

        # Already enrolled this session (any dormitory)
        existing = BoardingEnrollment.objects.filter(
            student=student,
            academic_session=academic_session,
            status__in=('PENDING', 'ACTIVE'),
        ).select_related('dormitory').first()

        if existing:
            errors.append(
                f"Already enrolled in '{existing.dormitory.name}' "
                f"for this session."
            )

        return len(errors) == 0, errors

    @staticmethod
    def get_boarding_warnings(
        student: Student,
        dormitory: Dormitory,
        academic_session: AcademicSession,
    ) -> List[str]:
        """
        Return non-blocking warnings about a boarding enrolment.

        Examples of checks to add as requirements grow:
          - Student has outstanding fee balance
          - Dormitory is nearly full (> 90 % capacity)
          - Guardian consent not yet on file
          - Student age is below minimum boarding age
          - Medical requirements that the dormitory cannot accommodate

        Args:
            student:          Student being enrolled.
            dormitory:        Target dormitory.
            academic_session: Target session.

        Returns:
            List of warning strings (may be empty).
        """
        warnings = []

        # Capacity warning — not full, but getting close
        occupancy_pct = dormitory.get_occupancy_percentage()
        if occupancy_pct >= 90:
            available = dormitory.get_available_capacity()
            warnings.append(
                f"Dormitory '{dormitory.name}' is {occupancy_pct}% full "
                f"({available} bed(s) remaining)."
            )

        # Maintenance warning
        if dormitory.needs_maintenance():
            warnings.append(
                f"Dormitory '{dormitory.name}' has maintenance overdue since "
                f"{dormitory.next_maintenance_due}."
            )

        return warnings