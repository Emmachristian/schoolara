# boarding/models.py

from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models import Q
from django.utils import timezone
from utils.models import BaseModel
# FIX: use get_school_today() for all date comparisons so they respect the
# school's configured operational timezone, matching the pattern established
# in academics/models.py.
from core.utils import get_school_today
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# DORMITORY MODEL
# =============================================================================

class Dormitory(BaseModel):
    """
    Physical dormitory / residential facility.

    Tracks capacity, gender compatibility, management staff, facilities,
    and maintenance state.  Does not directly track per-session occupancy —
    that belongs on BoardingEnrollment.

    CHANGE: current_occupancy is now a live @property that counts ACTIVE
    BoardingEnrollment records directly.  The old cached PositiveIntegerField
    was removed because it drifted whenever enrollments changed outside the
    normal save cycle (bulk operations, shell scripts, management commands).
    With at most a handful of dormitories per school the extra query is
    negligible and the value is now always accurate with zero maintenance.

    NOTE: All date comparisons use get_school_today() so they respect the
    school's configured operational timezone.
    """

    # -------------------------------------------------------------------------
    # CHOICES
    # -------------------------------------------------------------------------

    DORMITORY_TYPE_CHOICES = [
        ('BOYS',  'Boys Dormitory'),
        ('GIRLS', 'Girls Dormitory'),
        ('MIXED', 'Mixed Dormitory'),
        ('STAFF', 'Staff Quarters'),
    ]

    MAINTENANCE_STATUS_CHOICES = [
        ('EXCELLENT',         'Excellent Condition'),
        ('GOOD',              'Good Condition'),
        ('FAIR',              'Fair Condition'),
        ('NEEDS_REPAIR',      'Needs Repair'),
        ('UNDER_MAINTENANCE', 'Under Maintenance'),
        ('CONDEMNED',         'Condemned'),
    ]

    # -------------------------------------------------------------------------
    # BASIC INFORMATION
    # -------------------------------------------------------------------------

    name = models.CharField("Dormitory Name", max_length=100)

    code = models.CharField(
        "Dormitory Code",
        max_length=20,
        unique=True,
        db_index=True,
        help_text="Unique short identifier for this dormitory (e.g., DORM-B-001)"
    )

    dormitory_type = models.CharField(
        "Dormitory Type",
        max_length=10,
        choices=DORMITORY_TYPE_CHOICES,
        db_index=True,
    )

    description = models.TextField("Description", blank=True)

    # -------------------------------------------------------------------------
    # LOCATION
    # -------------------------------------------------------------------------

    building = models.CharField("Building", max_length=100, blank=True)
    floor    = models.CharField("Floor",    max_length=10,  blank=True)
    wing     = models.CharField("Wing/Section", max_length=50, blank=True)

    # -------------------------------------------------------------------------
    # CAPACITY
    # current_occupancy is a live @property — see CAPACITY PROPERTIES below.
    # -------------------------------------------------------------------------

    total_capacity = models.PositiveIntegerField(
        "Total Capacity",
        validators=[MinValueValidator(1)],
        help_text="Maximum number of students this dormitory can hold",
    )

    room_count    = models.PositiveIntegerField("Number of Rooms", default=0)
    beds_per_room = models.PositiveIntegerField(
        "Beds per Room",
        default=1,
        validators=[MinValueValidator(1)],
    )

    # -------------------------------------------------------------------------
    # FACILITIES
    # -------------------------------------------------------------------------

    has_bathroom    = models.BooleanField("Has Bathroom",           default=True)
    has_study_area  = models.BooleanField("Has Study Area",         default=False)
    has_common_room = models.BooleanField("Has Common Room",        default=False)
    has_laundry     = models.BooleanField("Has Laundry Facilities", default=False)
    has_kitchen     = models.BooleanField("Has Kitchen",            default=False)
    has_wifi        = models.BooleanField("Has WiFi",               default=False)
    has_security    = models.BooleanField("Has Security",           default=True)

    facilities_description = models.TextField("Facilities Description", blank=True)

    # -------------------------------------------------------------------------
    # MANAGEMENT STAFF
    # -------------------------------------------------------------------------

    dormitory_master = models.ForeignKey(
        'hr.Staff',
        verbose_name="Dormitory Master",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='managed_dormitories',
    )

    assistant_dormitory_master = models.ForeignKey(
        'hr.Staff',
        verbose_name="Assistant Dormitory Master",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='assisted_dormitories',
    )

    # -------------------------------------------------------------------------
    # STATUS AND CONDITION
    # -------------------------------------------------------------------------

    is_active = models.BooleanField(
        "Is Active",
        default=True,
        db_index=True,
    )

    is_available_for_new_admissions = models.BooleanField(
        "Available for New Admissions",
        default=True,
        help_text="Un-check to stop new students being assigned here",
    )

    maintenance_status = models.CharField(
        "Maintenance Status",
        max_length=20,
        choices=MAINTENANCE_STATUS_CHOICES,
        default='GOOD',
        db_index=True,
    )

    last_maintenance_date = models.DateField(
        "Last Maintenance Date",
        null=True, blank=True,
    )

    next_maintenance_due = models.DateField(
        "Next Maintenance Due",
        null=True, blank=True,
    )

    # -------------------------------------------------------------------------
    # RULES, SAFETY AND CONTACT
    # -------------------------------------------------------------------------

    rules_and_regulations = models.TextField("Rules and Regulations", blank=True)
    emergency_procedures  = models.TextField("Emergency Procedures",  blank=True)
    dormitory_phone       = models.CharField("Dormitory Phone", max_length=20,  blank=True)
    dormitory_email       = models.EmailField("Dormitory Email",                blank=True)
    notes                 = models.TextField("Administrative Notes",            blank=True)

    # -------------------------------------------------------------------------
    # META
    # -------------------------------------------------------------------------

    class Meta:
        ordering = ['dormitory_type', 'name']
        verbose_name = "Dormitory"
        verbose_name_plural = "Dormitories"
        indexes = [
            models.Index(fields=['dormitory_type', 'is_active']),
            models.Index(fields=['maintenance_status']),
            models.Index(fields=['is_available_for_new_admissions']),
        ]
        # NOTE: the old CheckConstraint(occupancy_not_exceed_capacity) has been
        # removed — it referenced current_occupancy which is no longer a column.

    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------

    def __str__(self):
        return f"{self.name} ({self.get_dormitory_type_display()})"

    # -------------------------------------------------------------------------
    # CAPACITY PROPERTIES
    # -------------------------------------------------------------------------

    @property
    def current_occupancy(self):
        """
        Live count of ACTIVE boarding enrollments, filtered by gender for
        single-gender dormitories so the number always matches what the
        residents view shows.
        """
        qs = self.boarding_enrollments.filter(status='ACTIVE')
        if self.dormitory_type == 'BOYS':
            qs = qs.filter(student__gender='M')
        elif self.dormitory_type == 'GIRLS':
            qs = qs.filter(student__gender='F')
        return qs.count()

    @property
    def available_capacity(self):
        """Available beds (total minus current occupancy)."""
        return self.get_available_capacity()

    @property
    def occupancy_percentage(self):
        """Current occupancy as a percentage of total capacity."""
        return self.get_occupancy_percentage()

    @property
    def is_full(self):
        """True when current occupancy has reached total capacity."""
        return self.current_occupancy >= self.total_capacity

    @property
    def is_nearly_full(self):
        """True when occupancy is at or above 90 % of total capacity."""
        if self.total_capacity == 0:
            return False
        return (self.current_occupancy / self.total_capacity) >= 0.9

    # -------------------------------------------------------------------------
    # CAPACITY METHODS
    # -------------------------------------------------------------------------

    def get_available_capacity(self):
        """Return the number of free beds."""
        return max(0, self.total_capacity - self.current_occupancy)

    def has_capacity(self):
        """Return True if at least one bed is available."""
        return self.current_occupancy < self.total_capacity

    def get_occupancy_percentage(self):
        """Return occupancy as a rounded percentage float."""
        if self.total_capacity == 0:
            return 0.0
        return round((self.current_occupancy / self.total_capacity) * 100, 1)

    def get_occupancy_level(self):
        """
        Return a string label for the current occupancy level.
        Thresholds: empty → low (<70 %) → medium (<90 %) → high (≥90 %).
        """
        if self.total_capacity == 0 or self.current_occupancy == 0:
            return 'empty'
        ratio = self.current_occupancy / self.total_capacity
        if ratio < 0.70:
            return 'low'
        elif ratio < 0.90:
            return 'medium'
        return 'high'

    def get_occupancy_color(self):
        """Return a Bootstrap colour class matching the current occupancy level."""
        return {
            'empty':  'secondary',
            'low':    'success',
            'medium': 'warning',
            'high':   'danger',
        }.get(self.get_occupancy_level(), 'secondary')

    # -------------------------------------------------------------------------
    # COMPATIBILITY CHECKS
    # -------------------------------------------------------------------------

    def can_accommodate_gender(self, gender):
        """
        Return True if this dormitory can house a student of the given gender.
        Mixed dormitories accept all genders.
        """
        if self.dormitory_type == 'MIXED':
            return True
        if self.dormitory_type == 'BOYS'  and gender == 'M':
            return True
        if self.dormitory_type == 'GIRLS' and gender == 'F':
            return True
        return False

    def can_accommodate(self, student):
        """
        Comprehensive check for whether a student can be assigned here.

        Returns:
            tuple(bool, str): (can_accommodate, reason_message)
        """
        if not self.is_active:
            return False, "Dormitory is not active"

        if not self.is_available_for_new_admissions:
            return False, "Dormitory is not accepting new admissions"

        if self.maintenance_status in ('CONDEMNED', 'UNDER_MAINTENANCE'):
            return False, f"Dormitory is {self.get_maintenance_status_display()}"

        if self.is_full:
            return False, "Dormitory is at full capacity"

        if not self.can_accommodate_gender(student.gender):
            return (
                False,
                f"Dormitory cannot accommodate "
                f"{student.get_gender_display()} students",
            )

        return True, "Can accommodate"

    # -------------------------------------------------------------------------
    # MAINTENANCE
    # -------------------------------------------------------------------------

    def needs_maintenance(self):
        """
        True when next_maintenance_due is today or in the past.
        Uses get_school_today() so the check respects the school's timezone.
        """
        if not self.next_maintenance_due:
            return False
        return get_school_today() >= self.next_maintenance_due

    # -------------------------------------------------------------------------
    # RESIDENT QUERIES
    # -------------------------------------------------------------------------

    def get_current_residents(self):
        """Return a queryset of active boarding students in this dormitory."""
        from students.models import Student
        return Student.objects.filter(
            boarding_enrollments__dormitory=self,
            boarding_enrollments__status='ACTIVE',
            enrollment_status='ACTIVE',
        ).distinct()

    def get_resident_count(self):
        """
        Return the number of active residents.
        Identical to current_occupancy — provided for semantic clarity when
        called from non-capacity contexts.
        """
        return self.boarding_enrollments.filter(status='ACTIVE').count()

    def get_residents_by_class(self):
        """
        Return a dict mapping academic-level name → list of active students.
        """
        grouped = {}
        for student in self.get_current_residents().select_related(
            'current_academic_level'
        ):
            level_name = (
                str(student.current_academic_level)
                if student.current_academic_level
                else 'Unassigned'
            )
            grouped.setdefault(level_name, []).append(student)
        return grouped

    # -------------------------------------------------------------------------
    # UTILITY
    # -------------------------------------------------------------------------

    def get_full_location(self):
        """Return a human-readable location string."""
        parts = [self.name]
        if self.building:
            parts.append(self.building)
        if self.floor:
            parts.append(f"Floor {self.floor}")
        if self.wing:
            parts.append(self.wing)
        return ", ".join(parts)

    def get_facilities_list(self):
        """Return a list of facility names that are marked True."""
        facility_map = {
            'has_bathroom':    'Bathroom',
            'has_study_area':  'Study Area',
            'has_common_room': 'Common Room',
            'has_laundry':     'Laundry',
            'has_kitchen':     'Kitchen',
            'has_wifi':        'WiFi',
            'has_security':    'Security',
        }
        return [name for field, name in facility_map.items() if getattr(self, field)]

    # -------------------------------------------------------------------------
    # VALIDATION
    # -------------------------------------------------------------------------

    def clean(self):
        super().clean()
        errors = {}

        # current_occupancy is now a live property — we cannot validate it in
        # clean() because it issues a DB query on an unsaved instance and the
        # count reflects the real DB state, not pending changes.  The
        # can_accommodate() method enforces the capacity limit at enrolment time.

        if self.dormitory_master and self.assistant_dormitory_master:
            if self.dormitory_master == self.assistant_dormitory_master:
                errors['assistant_dormitory_master'] = (
                    "Assistant dormitory master cannot be the same person as "
                    "the dormitory master"
                )

        if self.last_maintenance_date and self.next_maintenance_due:
            if self.next_maintenance_due < self.last_maintenance_date:
                errors['next_maintenance_due'] = (
                    "Next maintenance date cannot be before last maintenance date"
                )

        if errors:
            raise ValidationError(errors)


# =============================================================================
# BOARDING ENROLLMENT MODEL
# =============================================================================

class BoardingEnrollment(BaseModel):
    """
    A student's boarding arrangement for one academic session.

    Parallel to StudentClassEnrollment in the academics app — students enroll
    into a Dormitory the same way they enroll into a Class.

    STATUS LIFECYCLE:
        PENDING → (approve) → ACTIVE → (suspend) → SUSPENDED → (re-activate) → ACTIVE
                                      → (terminate) → TERMINATED
        PENDING → (cancel) → CANCELLED

    INVOICE HANDLING:
        auto_create_invoice controls whether the post_save signal fires invoice
        creation.  BulkBoardingEnrollmentService sets this to False and calls
        _create_invoices() explicitly so that invoice failures surface as
        warnings in the result dict rather than being silently swallowed.

    DATE DEFAULTING:
        Defaults for enrollment_date, effective_start_date, and
        effective_end_date are applied in save() — not in clean() or
        full_clean().  This keeps a single code path for defaults and avoids
        the need to override full_clean().

    NOTE: Date comparisons use get_school_today() to respect the school's
    configured operational timezone.
    """

    # -------------------------------------------------------------------------
    # CHOICES
    # -------------------------------------------------------------------------

    BOARDING_TYPE_CHOICES = [
        ('FULL_BOARDER',   'Full Boarder'),
        ('WEEKLY_BOARDER', 'Weekly Boarder'),
        ('FLEXI_BOARDER',  'Flexible Boarder'),
    ]

    ENROLLMENT_STATUS_CHOICES = [
        ('PENDING',    'Pending Approval'),
        ('ACTIVE',     'Active'),
        ('SUSPENDED',  'Suspended'),
        ('TERMINATED', 'Terminated'),
        ('COMPLETED',  'Completed'),
        ('CANCELLED',  'Cancelled'),
    ]

    # -------------------------------------------------------------------------
    # CORE RELATIONSHIPS
    # -------------------------------------------------------------------------

    student = models.ForeignKey(
        'students.Student',
        verbose_name="Student",
        on_delete=models.CASCADE,
        related_name='boarding_enrollments',
    )

    academic_session = models.ForeignKey(
        'academics.AcademicSession',
        verbose_name="Academic Session",
        on_delete=models.CASCADE,
        related_name='boarding_enrollments',
    )

    dormitory = models.ForeignKey(
        Dormitory,
        verbose_name="Dormitory",
        on_delete=models.PROTECT,
        related_name='boarding_enrollments',
    )

    # -------------------------------------------------------------------------
    # BOARDING CONFIGURATION
    # -------------------------------------------------------------------------

    boarding_type = models.CharField(
        "Boarding Type",
        max_length=20,
        choices=BOARDING_TYPE_CHOICES,
        db_index=True,
    )

    boarding_days = models.JSONField(
        "Boarding Days",
        null=True,
        blank=True,
        help_text="Required for Flexible Boarders — JSON list of day names, "
                  "e.g. ['Monday', 'Tuesday', 'Wednesday']",
    )

    # -------------------------------------------------------------------------
    # ROOM / BED ASSIGNMENT
    # -------------------------------------------------------------------------

    room_number = models.CharField("Room Number", max_length=20, blank=True)
    bed_number  = models.CharField("Bed Number",  max_length=20, blank=True)

    boarding_roll_number = models.CharField(
        "Boarding Roll Number",
        max_length=20,
        blank=True,
        help_text="Auto-generated sequential number per dormitory and session",
    )

    # -------------------------------------------------------------------------
    # INVOICE INTEGRATION
    # -------------------------------------------------------------------------

    boarding_invoice = models.OneToOneField(
        'fees.FeeInvoice',
        verbose_name="Boarding Invoice",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='boarding_enrollment',
        help_text="Invoice generated for this boarding enrollment",
    )

    auto_create_invoice = models.BooleanField(
        "Auto-Create Invoice",
        default=True,
        help_text="When True, the post_save signal attempts invoice creation. "
                  "Set to False when BulkBoardingEnrollmentService handles "
                  "invoices explicitly.",
    )

    # -------------------------------------------------------------------------
    # DATES AND STATUS
    # -------------------------------------------------------------------------

    enrollment_date = models.DateField(
        "Boarding Enrollment Date",
        help_text="Administrative date the enrollment was recorded",
    )

    effective_start_date = models.DateField(
        "Effective Start Date",
        help_text="Date when boarding actually begins",
    )

    effective_end_date = models.DateField(
        "Effective End Date",
        null=True, blank=True,
        help_text="Date when boarding ends — defaults to session end date",
    )

    status = models.CharField(
        "Status",
        max_length=20,
        choices=ENROLLMENT_STATUS_CHOICES,
        default='PENDING',
        db_index=True,
    )

    # -------------------------------------------------------------------------
    # GUARDIAN CONSENT
    # -------------------------------------------------------------------------

    guardian_consent = models.BooleanField(
        "Guardian Consent",
        default=False,
        help_text="Whether the consenting guardian has provided written consent",
    )

    consent_date = models.DateField("Consent Date", null=True, blank=True)

    consenting_guardian = models.ForeignKey(
        'students.Guardian',
        verbose_name="Consenting Guardian",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='boarding_consents',
    )

    consent_document = models.FileField(
        "Consent Document",
        upload_to='boarding/consents/%Y/%m/',
        null=True, blank=True,
    )

    # -------------------------------------------------------------------------
    # FLEXIBLE BOARDING SCHEDULE (FLEXI_BOARDER only)
    # Stored in boarding_days JSONField above.
    # -------------------------------------------------------------------------

    # -------------------------------------------------------------------------
    # MEDICAL AND DIETARY REQUIREMENTS
    # -------------------------------------------------------------------------

    dietary_requirements    = models.TextField("Dietary Requirements",    blank=True)
    medical_requirements    = models.TextField("Medical Requirements",    blank=True)
    special_accommodations  = models.TextField("Special Accommodations",  blank=True)

    # -------------------------------------------------------------------------
    # EMERGENCY CONTACT
    # -------------------------------------------------------------------------

    emergency_contact_during_boarding    = models.CharField("Emergency Contact Phone",        max_length=20,  blank=True)
    emergency_contact_name               = models.CharField("Emergency Contact Name",         max_length=100, blank=True)
    emergency_contact_relationship       = models.CharField("Emergency Contact Relationship", max_length=50,  blank=True)

    # -------------------------------------------------------------------------
    # REASONS AND NOTES
    # -------------------------------------------------------------------------

    reason_for_boarding = models.TextField("Reason for Boarding", blank=True)
    termination_reason  = models.TextField("Termination Reason",  blank=True)
    admin_notes         = models.TextField("Administrative Notes", blank=True)

    # -------------------------------------------------------------------------
    # APPROVAL WORKFLOW
    # -------------------------------------------------------------------------

    approved_by = models.ForeignKey(
        'hr.Staff',
        verbose_name="Approved By",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='approved_boarding_enrollments',
    )

    approval_date = models.DateTimeField("Approval Date", null=True, blank=True)

    # -------------------------------------------------------------------------
    # META
    # -------------------------------------------------------------------------

    class Meta:
        ordering = ['-academic_session__start_date', 'dormitory', 'boarding_roll_number']
        verbose_name = "Boarding Enrollment"
        verbose_name_plural = "Boarding Enrollments"
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'academic_session'],
                condition=Q(status__in=['ACTIVE', 'PENDING']),
                name='unique_active_boarding_per_student_session',
            ),
            models.UniqueConstraint(
                fields=['dormitory', 'academic_session', 'boarding_roll_number'],
                condition=(
                    Q(boarding_roll_number__isnull=False) &
                    ~Q(boarding_roll_number='') &
                    Q(status='ACTIVE')
                ),
                name='unique_boarding_roll_per_dormitory_session',
            ),
        ]
        indexes = [
            models.Index(fields=['student', 'academic_session']),
            models.Index(fields=['dormitory', 'status']),
            models.Index(fields=['boarding_type']),
            models.Index(fields=['status']),
            models.Index(fields=['enrollment_date']),
            models.Index(fields=['effective_start_date']),
            models.Index(fields=['boarding_roll_number']),
        ]

    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------

    def __str__(self):
        display = (
            f"{self.student.get_full_name()} — "
            f"{self.get_boarding_type_display()} "
            f"({self.academic_session})"
        )
        if self.boarding_roll_number:
            display += f" [Roll: {self.boarding_roll_number}]"
        return display

    # -------------------------------------------------------------------------
    # PROPERTIES
    # -------------------------------------------------------------------------

    @property
    def is_current(self):
        """True when this enrollment is currently active by date."""
        return self.is_currently_active()

    @property
    def duration_days(self):
        """Elapsed or total duration in days."""
        return self.get_duration_days()

    # -------------------------------------------------------------------------
    # STATUS CHECKS
    # -------------------------------------------------------------------------

    def is_currently_active(self):
        """
        True when status is ACTIVE and today falls within the boarding dates.
        FIX: uses get_school_today() instead of timezone.now().date()
        """
        if self.status != 'ACTIVE':
            return False

        today = get_school_today()

        if today < self.effective_start_date:
            return False

        if self.effective_end_date and today > self.effective_end_date:
            return False

        return True

    # -------------------------------------------------------------------------
    # DURATION
    # -------------------------------------------------------------------------

    def get_duration_days(self):
        """
        Days between effective_start_date and effective_end_date (or today
        for still-active enrollments).
        FIX: uses get_school_today() instead of timezone.now().date()
        """
        end = self.effective_end_date or get_school_today()
        return (end - self.effective_start_date).days

    # -------------------------------------------------------------------------
    # DISPLAY HELPERS
    # -------------------------------------------------------------------------

    def get_boarding_schedule_display(self):
        """Human-readable boarding schedule."""
        if self.boarding_type == 'FULL_BOARDER':
            return "Monday – Sunday (Full Week)"
        if self.boarding_type == 'WEEKLY_BOARDER':
            return "Monday – Friday (Weekdays)"
        if self.boarding_type == 'FLEXI_BOARDER' and self.boarding_days:
            return f"Flexible: {', '.join(self.boarding_days)}"
        return "Not specified"

    def get_status_color(self):
        """Bootstrap colour class for the current status."""
        return {
            'PENDING':    'warning',
            'ACTIVE':     'success',
            'SUSPENDED':  'danger',
            'TERMINATED': 'dark',
            'COMPLETED':  'info',
            'CANCELLED':  'secondary',
        }.get(self.status, 'secondary')

    # -------------------------------------------------------------------------
    # STATUS TRANSITION METHODS
    # -------------------------------------------------------------------------

    def approve(self, approved_by):
        """
        Move the enrollment from PENDING to ACTIVE.
        Records the approving staff member and timestamp.
        """
        if self.status != 'PENDING':
            logger.warning(
                "approve() called on enrollment %s with status %s",
                self.pk, self.status,
            )
            return

        self.status        = 'ACTIVE'
        self.approved_by   = approved_by
        self.approval_date = timezone.now()
        self.save()
        logger.info(
            "Boarding enrollment %s approved by %s", self.pk, approved_by
        )

    def suspend(self, reason=None):
        """
        Suspend an ACTIVE enrollment.  Appends the reason to admin_notes.
        """
        if self.status != 'ACTIVE':
            logger.warning(
                "suspend() called on enrollment %s with status %s",
                self.pk, self.status,
            )
            return

        self.status = 'SUSPENDED'
        if reason:
            separator = "\n\n" if self.admin_notes else ""
            self.admin_notes += f"{separator}Suspended: {reason}"
        self.save()
        logger.info("Boarding enrollment %s suspended", self.pk)

    def terminate(self, reason=None, effective_date=None):
        """
        Terminate an ACTIVE or SUSPENDED enrollment.

        Args:
            reason:         Optional termination reason recorded on the record.
            effective_date: Date termination takes effect.  Defaults to today
                            (school timezone).

        FIX: uses get_school_today() instead of timezone.now().date()
        """
        if self.status not in ('ACTIVE', 'SUSPENDED'):
            logger.warning(
                "terminate() called on enrollment %s with status %s",
                self.pk, self.status,
            )
            return

        self.status             = 'TERMINATED'
        self.effective_end_date = effective_date or get_school_today()
        if reason:
            self.termination_reason = reason
        self.save()
        logger.info("Boarding enrollment %s terminated", self.pk)

    def reactivate(self):
        """Re-activate a SUSPENDED enrollment."""
        if self.status != 'SUSPENDED':
            logger.warning(
                "reactivate() called on enrollment %s with status %s",
                self.pk, self.status,
            )
            return

        self.status = 'ACTIVE'
        self.save()
        logger.info("Boarding enrollment %s reactivated", self.pk)

    # -------------------------------------------------------------------------
    # VALIDATION
    # -------------------------------------------------------------------------

    def clean(self):
        """
        Business-rule validation.

        Date defaults are NOT applied here — they are applied in save() so
        there is a single code path.  Validation guards against None to handle
        the case where clean() is called before save() has run (e.g. from a
        form that excludes those fields).
        """
        super().clean()
        errors = {}

        # Date ordering
        if self.effective_start_date and self.effective_end_date:
            if self.effective_end_date < self.effective_start_date:
                errors['effective_end_date'] = (
                    "Effective end date cannot be before effective start date"
                )

        # Start date within session bounds
        if self.effective_start_date and self.academic_session_id:
            try:
                session = self.academic_session
                if self.effective_start_date < session.start_date:
                    errors['effective_start_date'] = (
                        f"Effective start date cannot be before session start "
                        f"date ({session.start_date})"
                    )
                if self.effective_start_date > session.end_date:
                    errors['effective_start_date'] = (
                        f"Effective start date cannot be after session end "
                        f"date ({session.end_date})"
                    )
            except Exception:
                pass

        # Boarding days required for flexible boarders
        if self.boarding_type == 'FLEXI_BOARDER':
            if not self.boarding_days or not isinstance(self.boarding_days, list):
                errors['boarding_days'] = (
                    "Boarding days must be specified for flexible boarders"
                )
            elif len(self.boarding_days) == 0:
                errors['boarding_days'] = (
                    "At least one boarding day must be selected"
                )

        # Dormitory gender compatibility
        if self.dormitory_id and self.student_id:
            try:
                if not self.dormitory.can_accommodate_gender(self.student.gender):
                    errors['dormitory'] = (
                        f"Selected dormitory cannot accommodate "
                        f"{self.student.get_gender_display()} students"
                    )
            except Exception:
                pass

        # Consent consistency: if guardian_consent is True, require a date
        if self.guardian_consent and not self.consent_date:
            errors['consent_date'] = (
                "Consent date is required when guardian consent is recorded"
            )

        if self.guardian_consent and not self.consenting_guardian_id:
            errors['consenting_guardian'] = (
                "Please select which guardian provided consent"
            )

        if errors:
            raise ValidationError(errors)

    # -------------------------------------------------------------------------
    # SAVE
    # -------------------------------------------------------------------------

    def save(self, *args, **kwargs):
        """
        Apply date defaults then save.

        Defaults are applied here — not in clean() or full_clean() — so that
        there is a single authoritative code path regardless of whether the
        record is created via a form, the service, or the shell.

        Dormitory occupancy is resynced after every status change.
        """
        # -- Apply date defaults ----------------------------------------------
        if not self.enrollment_date:
            self.enrollment_date = (
                self.academic_session.start_date
                if self.academic_session_id
                else get_school_today()
            )

        if not self.effective_start_date:
            self.effective_start_date = self.enrollment_date

        if not self.effective_end_date and self.academic_session_id:
            try:
                self.effective_end_date = self.academic_session.end_date
            except Exception:
                pass

        # -- Track status change for occupancy sync ---------------------------
        old_status = None
        if not self._state.adding:
            try:
                old_status = BoardingEnrollment.objects.values_list(
                    'status', flat=True
                ).get(pk=self.pk)
            except BoardingEnrollment.DoesNotExist:
                pass

        super().save(*args, **kwargs)

        # -- Sync dormitory occupancy if status changed -----------------------
        if old_status != self.status:
            try:
                self.dormitory.update_occupancy_count()
            except Exception as e:
                logger.error(
                    "Error updating dormitory occupancy after status change: %s", e
                )

    def delete(self, *args, **kwargs):
        """Resync dormitory occupancy after deletion."""
        dormitory = self.dormitory
        super().delete(*args, **kwargs)
        try:
            dormitory.update_occupancy_count()
        except Exception as e:
            logger.error(
                "Error updating dormitory occupancy after deletion: %s", e
            )