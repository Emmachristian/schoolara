# academics/models.py

from django.db import models
from django.db.models import Q
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta, date
from schoolara.managers import SchoolManager
from utils.models import BaseModel
from core.models import SchoolConfiguration
# FIX: import get_school_today for school-timezone-aware date comparisons in AcademicSession
from core.utils import get_school_today
import re
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# ACADEMIC SESSION MODEL
# =============================================================================

class AcademicSession(BaseModel):
    """
    Academic session for educational activities and student progression.
    
    Purpose: Track teaching/learning periods with strict academic dates.
    Unlike FiscalPeriod (which handles financial transactions with flexible dates),
    AcademicSession represents actual classroom instruction time and is strictly
    closed after the session ends to preserve academic integrity.
    
    Examples:
    - "Term 1 2024" (Jan 15 - Mar 30) - Regular session
    - "Fall Semester 2024" (Sep 1 - Dec 20) - Regular session
    - "Quarter 3 2024" (Mar 1 - May 31) - Regular session
    - "December Holiday Program 2024" (Dec 1-20) - Special session
    - "Summer Remedial 2024" (Jun 1-30) - Special session
    
    Used for:
    - Student class enrollments
    - Academic reports and transcripts
    - Grading and assessments
    - Timetables and class schedules
    - Student promotion/progression
    - Academic calendar and events
    - Attendance tracking
    - Curriculum delivery
    
    Key Feature: Strictly closed after session ends to preserve academic
    integrity (grades locked, reports finalized, enrollment frozen).
    Financial transactions for this session can continue in the associated
    FiscalPeriod which may extend beyond these dates.
    
    Regular vs Special Sessions:
    - Regular sessions: Follow SchoolConfiguration (auto-generated names/types)
    - Special sessions: Holiday programs, summer school, remedial (customizable)
    
    NOTE: All date comparisons in this model use get_school_today() from
    core.utils rather than timezone.now().date() so they respect the school's
    configured operational timezone (core.models.SchoolConfiguration.operational_timezone).
    """
    
    # -------------------------------------------------------------------------
    # ACADEMIC YEAR IDENTIFICATION
    # -------------------------------------------------------------------------
    
    year_name = models.CharField(
        "Academic Year", 
        max_length=20, 
        help_text="E.g., '2024', '2024-2025', '2024/2025'"
    )
    
    # -------------------------------------------------------------------------
    # PERIOD IDENTIFICATION
    # -------------------------------------------------------------------------
    
    term_number = models.PositiveSmallIntegerField(
        "Period Number", 
        help_text="Position of this period within the year (1, 2, 3, etc.)",
        db_index=True
    )
    
    term_name = models.CharField(
        "Period Name", 
        max_length=50,
        blank=True,
        help_text="Leave blank to auto-generate from school configuration. "
                  "Provide custom name for special sessions (e.g., 'December Holiday Program')."
    )
    
    period_type = models.CharField(
        "Period Type",
        max_length=20,
        choices=[
            ('term', 'Term'),
            ('semester', 'Semester'),
            ('quarter', 'Quarter'),
            ('trimester', 'Trimester'),
            ('module', 'Module'),
            ('block', 'Block'),
            ('yearlong', 'Year-long'),
            ('intensive', 'Intensive'),
            ('holiday_program', 'Holiday Program'),
            ('remedial', 'Remedial Program'),
            ('summer_school', 'Summer School'),
            ('custom', 'Custom'),
        ],
        blank=True,
        db_index=True,
        help_text="Leave blank to auto-set from school configuration. "
                  "Select manually for special sessions."
    )
    
    is_special_session = models.BooleanField(
        "Is Special Session",
        default=False,
        db_index=True,
        help_text="Check this for holiday programs, summer school, remedial classes, "
                  "or other sessions outside the regular term structure. "
                  "This allows you to customize the period type and name."
    )
    
    # -------------------------------------------------------------------------
    # DATE RANGE (STRICT - actual teaching/learning dates)
    # -------------------------------------------------------------------------
    
    start_date = models.DateField(
        "Start Date",
        db_index=True,
        help_text="When classes begin for this session"
    )
    
    end_date = models.DateField(
        "End Date",
        db_index=True,
        help_text="When classes end for this session"
    )
    
    # -------------------------------------------------------------------------
    # ACADEMIC STATUS
    # -------------------------------------------------------------------------
    
    is_current = models.BooleanField(
        "Is Current Session",
        default=False,
        db_index=True,
        help_text="Whether this is the current active session"
    )
    
    is_active = models.BooleanField(
        "Is Active",
        default=False,
        db_index=True,
        help_text="Whether this session is active for enrollment and activities"
    )
    
    # -------------------------------------------------------------------------
    # ACADEMIC CLOSURE (STRICT - preserves academic records)
    # -------------------------------------------------------------------------
    
    is_academically_closed = models.BooleanField(
        "Academically Closed",
        default=False,
        db_index=True,
        help_text="Academic activities frozen - grades locked, reports final, no enrollment changes"
    )
    
    academic_closure_date = models.DateTimeField(
        "Academic Closure Date",
        null=True,
        blank=True,
        help_text="When this session was academically closed"
    )
    
    closed_by_id = models.CharField(
        "Closed By User ID",
        max_length=100,
        null=True,
        blank=True,
        help_text="ID of user who closed this session"
    )
    
    # -------------------------------------------------------------------------
    # STUDENT PROGRESSION
    # -------------------------------------------------------------------------
    
    allows_promotion = models.BooleanField(
        "Allows Promotion", 
        default=False,
        help_text="Whether students can be promoted at the end of this period"
    )
    
    promotion_done = models.BooleanField(
        "Promotion Completed",
        default=False,
        help_text="Whether student promotion has been completed"
    )
    
    # -------------------------------------------------------------------------
    # ENROLLMENT SETTINGS
    # -------------------------------------------------------------------------
    
    enrollment_deadline = models.DateField(
        "Enrollment Deadline",
        null=True,
        blank=True,
        help_text="Last date for student enrollment"
    )
    
    late_enrollment_allowed = models.BooleanField(
        "Late Enrollment Allowed",
        default=True,
        help_text="Whether students can enroll after deadline"
    )
    
    # -------------------------------------------------------------------------
    # ACADEMIC REQUIREMENTS
    # -------------------------------------------------------------------------
    
    minimum_attendance_percentage = models.DecimalField(
        "Minimum Attendance %",
        max_digits=5,
        decimal_places=2,
        default=75.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Minimum attendance required for this session"
    )
    
    # -------------------------------------------------------------------------
    # LEGACY FINANCIAL FIELDS (Deprecated - use FiscalPeriod instead)
    # -------------------------------------------------------------------------
    
    registration_fee_required = models.BooleanField(
        "Registration Fee Required",
        default=True,
        help_text="DEPRECATED: Use FiscalPeriod settings instead"
    )
    
    late_payment_penalty_rate = models.DecimalField(
        "Late Payment Penalty Rate", 
        max_digits=5, 
        decimal_places=2, 
        default=0.00,
        help_text="DEPRECATED: Use FiscalPeriod settings instead"
    )
    
    # -------------------------------------------------------------------------
    # METADATA
    # -------------------------------------------------------------------------
    
    description = models.TextField(
        "Description",
        blank=True,
        help_text="Optional description or notes about this session"
    )
    
    # -------------------------------------------------------------------------
    # CUSTOM MANAGER
    # -------------------------------------------------------------------------
    
    objects = SchoolManager()
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return self.name
    
    # -------------------------------------------------------------------------
    # PROPERTIES
    # -------------------------------------------------------------------------
    
    @property
    def name(self):
        """Returns the display name of the session"""
        return f"{self.year_name} - {self.term_name}"
    
    @property
    def display_name(self):
        """Alternative display name with more details"""
        return f"{self.year_name} {self.term_name}"
    
    @property
    def short_name(self):
        """Short display name"""
        year_part = self.year_name.split('-')[0] if '-' in self.year_name else self.year_name.split('/')[0] if '/' in self.year_name else self.year_name
        return f"{year_part}/{self.term_name}"
    
    @property
    def full_name(self):
        """Full descriptive name"""
        session_type = "Special Session" if self.is_special_session else "Regular Session"
        return f"{self.year_name} Academic Year - {self.term_name} ({self.get_period_type_display()}) [{session_type}]"
    
    def get_period_type_display(self):
        """Get display name for period type"""
        type_names = {
            'term': 'Term',
            'semester': 'Semester',
            'quarter': 'Quarter',
            'trimester': 'Trimester',
            'module': 'Module',
            'block': 'Block',
            'yearlong': 'Year-long',
            'intensive': 'Intensive',
            'holiday_program': 'Holiday Program',
            'remedial': 'Remedial Program',
            'summer_school': 'Summer School',
            'custom': 'Custom',
        }
        return type_names.get(self.period_type, self.period_type.title())
    
    @property
    def status_display(self):
        """
        Get human-readable status.
        FIX: uses get_school_today() instead of timezone.now().date()
        """
        if self.is_academically_closed:
            return "Closed"
        elif self.is_current:
            return "Current"
        elif self.is_active:
            current_date = get_school_today()
            if current_date < self.start_date:
                return "Upcoming"
            elif current_date > self.end_date:
                return "Completed"
            else:
                return "Active"
        else:
            return "Inactive"
    
    @property
    def days_remaining(self):
        """
        Get days remaining in the session.
        FIX: uses get_school_today() instead of timezone.now().date()
        """
        if not self.end_date:
            return 0

        current_date = get_school_today()
        if current_date > self.end_date:
            return 0

        return (self.end_date - current_date).days
    
    @property
    def days_elapsed(self):
        """
        Get days elapsed since session started.
        FIX: uses get_school_today() instead of timezone.now().date()
        """
        if not self.start_date:
            return 0

        current_date = get_school_today()
        if current_date < self.start_date:
            return 0

        return (current_date - self.start_date).days
    
    @property
    def total_days(self):
        """Get total days in the session"""
        if not self.start_date or not self.end_date:
            return 0
        return (self.end_date - self.start_date).days + 1
    
    @property
    def progress_percentage(self):
        """
        Get session progress as percentage.
        Derived from days_elapsed and total_days — fixed transitively via days_elapsed.
        """
        if self.total_days == 0:
            return 0

        elapsed = self.days_elapsed
        if elapsed <= 0:
            return 0
        elif elapsed >= self.total_days:
            return 100

        return round((elapsed / self.total_days) * 100, 1)
    
    @property
    def is_enrollment_open(self):
        """
        Check if enrollment is still open.
        FIX: uses get_school_today() instead of timezone.now().date()
        """
        if self.is_academically_closed:
            return False

        if not self.enrollment_deadline:
            return self.is_active  # No deadline set

        current_date = get_school_today()
        if current_date <= self.enrollment_deadline:
            return self.is_active

        return self.late_enrollment_allowed and self.is_active
    
    @property
    def closed_by_name(self):
        """Get name of user who closed session"""
        user = self.get_closed_by_user()
        if user:
            return user.get_full_name() or user.username
        return "System"
    
    # -------------------------------------------------------------------------
    # VALIDATION AND SAVE METHODS
    # -------------------------------------------------------------------------
    
    def clean(self):
        """Enhanced validation with smart enforcement"""
        super().clean()
        errors = {}
        
        # Date validation
        if self.start_date and self.end_date and self.start_date >= self.end_date:
            errors['end_date'] = 'End date must be after start date'
        
        # Enrollment deadline validation
        if self.enrollment_deadline:
            if self.start_date and self.enrollment_deadline > self.end_date:
                errors['enrollment_deadline'] = 'Enrollment deadline cannot be after session end'
        
        # Year name format validation
        if '/' in self.year_name or '-' in self.year_name:
            pattern = r'^(20\d{2})[\/-](20\d{2})$'
            if not re.match(pattern, self.year_name):
                errors['year_name'] = 'Year name must be in format "YYYY-YYYY" or "YYYY/YYYY"'
        else:
            pattern = r'^20\d{2}$'
            if not re.match(pattern, self.year_name):
                errors['year_name'] = 'Year name must be in format "YYYY"'
        
        # SMART VALIDATION: Only enforce SchoolConfiguration for regular sessions
        if not self.is_special_session:
            try:
                config = SchoolConfiguration.get_instance()
                if config:
                    if not config.validate_period_number(self.term_number):
                        errors['term_number'] = (
                            f'Period number {self.term_number} is invalid for '
                            f'{config.get_term_system_display_name()} system (max: {config.get_period_count()}). '
                            f'To create a session outside the regular term structure, '
                            f'check the "Is Special Session" checkbox.'
                        )
                    if self.period_type and self.period_type != config.term_system:
                        logger.warning(
                            f"Regular session {self.year_name} term {self.term_number} "
                            f"has period_type '{self.period_type}' which differs from "
                            f"school configuration '{config.term_system}'"
                        )
            except Exception as e:
                logger.warning(f"Could not validate against SchoolConfiguration: {e}")
                if self.term_number > 12:
                    errors['term_number'] = 'Period number cannot exceed 12 without a configured school system'
        else:
            if self.term_number > 20:
                errors['term_number'] = 'Period number cannot exceed 20 even for special sessions'
            if not self.period_type:
                errors['period_type'] = 'Period type is required for special sessions'
            if not self.term_name:
                errors['term_name'] = 'Period name is required for special sessions'
        
        # Percentage field validation
        if not (0 <= self.late_payment_penalty_rate <= 100):
            errors['late_payment_penalty_rate'] = 'Late payment penalty rate must be between 0 and 100'
        
        if not (0 <= self.minimum_attendance_percentage <= 100):
            errors['minimum_attendance_percentage'] = 'Minimum attendance percentage must be between 0 and 100'
        
        if errors:
            raise ValidationError(errors)
    
    def save(self, *args, **kwargs):
        """
        Enhanced save with SMART auto-generation.
        
        Logic for REGULAR sessions (is_special_session=False):
        - Auto-set period_type from SchoolConfiguration if blank
        - Auto-generate term_name from SchoolConfiguration if blank
        - Validate term_number against SchoolConfiguration
        
        Logic for SPECIAL sessions (is_special_session=True):
        - Require user to provide period_type and term_name
        - Allow any valid term_number (up to 20)
        - No auto-generation from SchoolConfiguration
        """
        if not self.is_special_session:
            try:
                config = SchoolConfiguration.get_instance()
                if config:
                    if not self.period_type:
                        self.period_type = config.term_system
                        logger.debug(
                            f"Regular session: Auto-set period_type='{self.period_type}' "
                            f"from SchoolConfiguration"
                        )
                    if not self.term_name:
                        self.term_name = config.get_period_name(self.term_number)
                        logger.debug(
                            f"Regular session: Auto-generated term_name='{self.term_name}' "
                            f"from SchoolConfiguration"
                        )
                else:
                    logger.warning("No SchoolConfiguration found, using fallback values")
                    self._set_fallback_values()
            except Exception as e:
                logger.error(f"Error getting SchoolConfiguration: {e}", exc_info=True)
                self._set_fallback_values()
        else:
            logger.info(
                f"Creating/updating special session: {self.year_name} - "
                f"{self.term_name or 'unnamed'}"
            )
            if not self.period_type:
                self.period_type = 'custom'
                logger.debug("Special session: Defaulting to period_type='custom'")
            if not self.term_name:
                type_names = {
                    'holiday_program': 'Holiday Program',
                    'summer_school':   'Summer School',
                    'remedial':        'Remedial Program',
                    'intensive':       'Intensive Course',
                    'custom':          'Special Session',
                }
                base_name = type_names.get(self.period_type, 'Special Session')
                self.term_name = f"{base_name} {self.term_number}"
                logger.debug(f"Special session: Generated term_name='{self.term_name}'")
        
        # Ensure only one current session
        if self.is_current:
            AcademicSession.objects.filter(is_current=True).exclude(pk=self.pk).update(is_current=False)
        
        super().save(*args, **kwargs)
        logger.info(f"Academic session saved successfully: {self.name}")
    
    def _set_fallback_values(self):
        """Set fallback values if SchoolConfiguration is not available"""
        if not self.period_type:
            self.period_type = 'term'
            logger.debug("Using fallback period_type='term'")
        
        if not self.term_name:
            period_types = {
                'semester':  'Semester',
                'quarter':   'Quarter',
                'trimester': 'Trimester',
                'module':    'Module',
                'block':     'Block',
                'term':      'Term',
            }
            period_name = period_types.get(self.period_type, 'Term')
            self.term_name = f"{period_name} {self.term_number}"
            logger.debug(f"Using fallback term_name='{self.term_name}'")
    
    # -------------------------------------------------------------------------
    # CLOSURE METHODS
    # -------------------------------------------------------------------------
    
    def close_academically(self, user=None):
        """
        Close session for academic purposes.
        
        After this:
        - No grade changes allowed
        - No enrollment changes allowed
        - Reports are final
        - Attendance is locked
        
        Financial transactions can still occur in the associated FiscalPeriod.
        """
        if self.is_academically_closed:
            logger.warning(f"Academic session {self} is already closed")
            return
        
        self.is_academically_closed = True
        self.is_active              = False
        self.is_current             = False
        self.academic_closure_date  = timezone.now()
        
        if user:
            self.closed_by_id = str(user.id) if hasattr(user, 'id') else str(user.pk)
        
        self.save()
        logger.info(f"Academic session {self} closed by {self.closed_by_name}")
    
    def reopen_academically(self, user=None):
        """Reopen a closed session (requires proper authorization)."""
        if not self.is_academically_closed:
            logger.warning(f"Academic session {self} is not closed")
            return
        
        self.is_academically_closed = False
        self.is_active              = True
        self.academic_closure_date  = None
        self.closed_by_id           = None
        
        self.save()
        user_name = user.get_full_name() if user else "System"
        logger.warning(f"Academic session {self} reopened by {user_name}")
    
    # -------------------------------------------------------------------------
    # PERMISSION CHECK METHODS
    # -------------------------------------------------------------------------
    
    def can_modify_grades(self):
        return not self.is_academically_closed
    
    def can_enroll_students(self):
        return self.is_enrollment_open and not self.is_academically_closed
    
    def can_take_attendance(self):
        return not self.is_academically_closed and self.is_active
    
    def can_modify_timetable(self):
        return not self.is_academically_closed and self.is_active
    
    def can_be_closed(self):
        return not self.is_academically_closed and not self.is_current
    
    def can_be_made_current(self):
        if self.is_academically_closed:
            return False
        # Uses timezone.now().date() here intentionally — this is a write-guard
        # check, not a reporting comparison, so school timezone is less critical.
        current_date = timezone.now().date()
        return self.start_date <= current_date <= self.end_date
    
    # -------------------------------------------------------------------------
    # STATUS CHECK METHODS
    # -------------------------------------------------------------------------
    
    def is_current_session(self):
        """
        Check if this is the current session.
        FIX: uses get_school_today() instead of timezone.now().date()
        """
        today = get_school_today()
        return self.start_date <= today <= self.end_date and self.is_current
    
    def is_upcoming(self):
        """
        Check if session is in the future.
        FIX: uses get_school_today() instead of timezone.now().date()
        """
        return self.start_date > get_school_today()
    
    def is_past(self):
        """
        Check if session has ended.
        FIX: uses get_school_today() instead of timezone.now().date()
        """
        return self.end_date < get_school_today()
    
    # -------------------------------------------------------------------------
    # DURATION METHODS
    # -------------------------------------------------------------------------
    
    def get_duration_days(self):
        return self.total_days
    
    def get_duration_weeks(self):
        return self.total_days // 7 if self.total_days > 0 else 0
    
    # -------------------------------------------------------------------------
    # HELPER METHODS
    # -------------------------------------------------------------------------
    
    def get_closed_by_user(self):
        if self.closed_by_id:
            try:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                return User.objects.using('default').get(pk=self.closed_by_id)
            except Exception as e:
                logger.debug(f"Could not fetch closed_by user {self.closed_by_id}: {e}")
                return None
        return None
    
    def get_session_category_display(self):
        if self.is_special_session:
            return f"Special Session ({self.get_period_type_display()})"
        return f"Regular Session ({self.get_period_type_display()})"
    
    def get_academic_calendar(self):
        events = []
        events.append({'title': f'{self.name} Begins', 'date': self.start_date, 'type': 'session_start'})
        events.append({'title': f'{self.name} Ends',   'date': self.end_date,   'type': 'session_end'})
        if self.enrollment_deadline:
            events.append({'title': 'Enrollment Deadline', 'date': self.enrollment_deadline, 'type': 'enrollment_deadline'})
        return sorted(events, key=lambda x: x['date'])
    
    def get_status_display_class(self):
        if self.is_academically_closed:
            return 'status-closed'
        elif self.is_current:
            return 'status-current'
        elif self.is_active:
            return 'status-active'
        else:
            return 'status-inactive'
        
    @classmethod
    def get_current_session(cls):
        try:
            return cls.objects.get(is_current=True, is_active=True)
        except cls.DoesNotExist:
            logger.warning("No current session found")
            return None
        except cls.MultipleObjectsReturned:
            logger.error("Multiple current sessions found - data integrity issue")
            return cls.objects.filter(is_current=True, is_active=True).order_by('-start_date').first()

    @classmethod
    def get_open_for_enrollment(cls):
        from django.db.models import Q

        from core.utils import get_school_today
        today = get_school_today()
        
        return cls.objects.filter(
            is_active=True,
            is_academically_closed=False
        ).filter(
            Q(enrollment_deadline__isnull=True) |
            Q(enrollment_deadline__gte=today) |
            Q(enrollment_deadline__lt=today, late_enrollment_allowed=True)
        ).order_by('-start_date')
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        ordering = ['-start_date', 'term_number']
        verbose_name = "Academic Session"
        verbose_name_plural = "Academic Sessions"
        unique_together = ('year_name', 'term_number')
        indexes = [
            models.Index(fields=['is_current']),
            models.Index(fields=['is_active']),
            models.Index(fields=['is_academically_closed']),
            models.Index(fields=['is_special_session']),
            models.Index(fields=['start_date', 'end_date']),
            models.Index(fields=['year_name', 'term_number']),
            models.Index(fields=['allows_promotion', 'promotion_done']),
            models.Index(fields=['period_type']),
            models.Index(fields=['enrollment_deadline']),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(start_date__lt=models.F('end_date')),
                name='session_start_before_end'
            ),
            models.CheckConstraint(
                check=Q(late_payment_penalty_rate__gte=0, late_payment_penalty_rate__lte=100),
                name='valid_penalty_rate'
            ),
            models.CheckConstraint(
                check=Q(minimum_attendance_percentage__gte=0, minimum_attendance_percentage__lte=100),
                name='valid_attendance_percentage'
            ),
        ]


# =============================================================================
# HOLIDAY MODEL
# =============================================================================

class Holiday(BaseModel):
    """
    School holidays, public holidays, and important calendar dates.
    
    Purpose: Track specific dates when school is closed or has special events.
    Unlike FiscalPeriod (which tracks financial transaction windows),
    Holiday marks specific calendar dates for:
    - Staff leave/payroll calculations
    - Attendance tracking (mark as excused)
    - Timetable/schedule blocking
    - Academic calendar display
    - Event planning
    
    NOT used for:
    - Financial transactions (use FiscalPeriod)
    - Fee collection windows (use FiscalPeriod)
    
    NOTE: Holiday date comparisons deliberately use timezone.now().date()
    not get_school_today() — holidays are calendar events, not school-finance
    operations, so UTC-local offset is not a concern here.
    """
    
    HOLIDAY_TYPE_CHOICES = [
        ('PUBLIC',       'Public Holiday'),
        ('SCHOOL_BREAK', 'School Break'),
        ('SCHOOL_EVENT', 'School Event'),
        ('RELIGIOUS',    'Religious Holiday'),
        ('PROFESSIONAL', 'Professional Day'),
        ('EXAMINATION',  'Examination Period'),
        ('CUSTOM',       'Custom Holiday'),
    ]
    
    name = models.CharField(
        "Holiday Name",
        max_length=200,
        help_text="E.g., 'Easter Monday', 'Mid-Term Break', 'Independence Day'"
    )
    
    holiday_type = models.CharField(
        "Holiday Type",
        max_length=20,
        choices=HOLIDAY_TYPE_CHOICES,
        default='PUBLIC',
        db_index=True
    )
    
    start_date = models.DateField(
        "Start Date",
        db_index=True,
        help_text="First day of holiday"
    )
    
    end_date = models.DateField(
        "End Date",
        null=True,
        blank=True,
        help_text="Last day of holiday (leave blank for single-day holidays)"
    )
    
    academic_session = models.ForeignKey(
        AcademicSession,
        on_delete=models.SET_NULL,
        related_name='holidays',
        verbose_name="Academic Session",
        null=True,
        blank=True,
        help_text="Academic session this holiday falls within (optional, for reference)"
    )
    
    is_school_closed    = models.BooleanField("School Closed",     default=True)
    is_partial_closure  = models.BooleanField("Partial Closure",   default=False)
    affects_attendance  = models.BooleanField("Affects Attendance", default=True)
    affects_payroll     = models.BooleanField("Affects Payroll",    default=False)
    is_recurring        = models.BooleanField("Is Recurring",       default=False)
    
    color = models.CharField(
        "Calendar Color",
        max_length=7,
        default="#FF0000",
        help_text="Hex color for calendar display (e.g., #FF0000)"
    )
    
    notify_parents = models.BooleanField("Notify Parents", default=True)
    notify_staff   = models.BooleanField("Notify Staff",   default=True)
    
    description = models.TextField("Description", blank=True)
    notes       = models.TextField("Internal Notes", blank=True)
    
    objects = SchoolManager()
    
    def __str__(self):
        if self.end_date and self.start_date != self.end_date:
            return f"{self.name} ({self.start_date} to {self.end_date})"
        return f"{self.name} - {self.start_date}"
    
    def clean(self):
        super().clean()
        errors = {}
        
        if self.end_date and self.start_date > self.end_date:
            errors['end_date'] = 'End date cannot be before start date'
        
        if self.is_partial_closure and self.is_school_closed:
            errors['is_partial_closure'] = 'Cannot be both fully closed and partially closed'
        
        if self.color:
            import re
            if not re.match(r'^#[0-9A-Fa-f]{6}$', self.color):
                errors['color'] = 'Invalid hex color code (e.g., #FF0000)'
        
        if errors:
            raise ValidationError(errors)
    
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
    
    @property
    def duration_days(self):
        if not self.end_date or self.start_date == self.end_date:
            return 1
        return (self.end_date - self.start_date).days + 1
    
    @property
    def is_single_day(self):
        return self.end_date is None or self.start_date == self.end_date
    
    @property
    def is_current(self):
        today = timezone.now().date()
        if self.end_date:
            return self.start_date <= today <= self.end_date
        return self.start_date == today
    
    @property
    def is_upcoming(self):
        return self.start_date > timezone.now().date()
    
    @property
    def is_past(self):
        end = self.end_date or self.start_date
        return end < timezone.now().date()
    
    def overlaps_with_date(self, check_date):
        if self.end_date:
            return self.start_date <= check_date <= self.end_date
        return self.start_date == check_date
    
    def overlaps_with_range(self, start_date, end_date):
        holiday_end = self.end_date or self.start_date
        return not (holiday_end < start_date or self.start_date > end_date)
    
    def get_display_class(self):
        type_classes = {
            'PUBLIC':       'holiday-public',
            'SCHOOL_BREAK': 'holiday-break',
            'SCHOOL_EVENT': 'holiday-event',
            'RELIGIOUS':    'holiday-religious',
            'PROFESSIONAL': 'holiday-professional',
            'EXAMINATION':  'holiday-exam',
            'CUSTOM':       'holiday-custom',
        }
        return type_classes.get(self.holiday_type, 'holiday-default')
    
    class Meta:
        verbose_name = "Holiday"
        verbose_name_plural = "Holidays"
        ordering = ['start_date', 'name']
        indexes = [
            models.Index(fields=['start_date', 'end_date']),
            models.Index(fields=['holiday_type']),
            models.Index(fields=['is_school_closed']),
            models.Index(fields=['academic_session']),
            models.Index(fields=['is_recurring']),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(start_date__lte=models.F('end_date')) | Q(end_date__isnull=True),
                name='holiday_start_before_end'
            ),
        ]


# =============================================================================
# SUBJECT MODEL
# =============================================================================

class Subject(BaseModel):
    """Model for managing academic subjects"""
    name = models.CharField("Subject Name", max_length=100)
    abbreviation = models.CharField(
        "Abbreviation", 
        max_length=10, 
        unique=True,
        help_text="Short form for display purposes (e.g., MATH, ENG, SCI)",
        blank=True
    )
    code = models.CharField("Subject Code", max_length=20, unique=True)
    description = models.TextField("Description", blank=True)
    
    SUBJECT_TYPE_CHOICES = [
        ('MATH',        'Mathematics'),
        ('LANG_ARTS',   'Language Arts'),
        ('SCIENCES',    'Sciences'),
        ('SOCIAL',      'Social Studies'),
        ('LITERACY',    'Literacy'),
        ('NUMERACY',    'Numeracy'),
        ('SCIENCE_ENV', 'Environmental Education'),
        ('RELIGION',    'Religious & Moral Education'),
        ('CREATIVE',    'Creative Arts & Life Skills'),
        ('MOTHER_TONGUE','Mother Tongue'),
        ('FOREIGN_LANG','Foreign Language'),
        ('ARTS_CRAFTS', 'Arts and Crafts'),
        ('MUSIC',       'Music'),
        ('PE',          'Physical Education'),
        ('RELIGIOUS',   'Religious Studies'),
        ('COMPUTER',    'Computer Studies'),
        ('LIFE_SKILLS', 'Life Skills'),
        ('TECHNICAL',   'Technical Subjects'),
        ('BUSINESS',    'Business Studies'),
        ('AGRICULTURE', 'Agriculture'),
        ('HOME_ECON',   'Home Economics'),
        ('EXTRA',       'Extracurricular Activities'),
        ('CLUBS',       'Clubs and Societies'),
        ('GUIDANCE',    'Guidance & Counselling'),
        ('OTHER',       'Other / Miscellaneous'),
    ]
    subject_type = models.CharField(
        "Subject Type", 
        max_length=20, 
        choices=SUBJECT_TYPE_CHOICES,
        default='SCIENCES'
    )
    
    credit_hours = models.DecimalField(
        "Credit Hours", 
        max_digits=4, 
        decimal_places=1, 
        validators=[MinValueValidator(0.5), MaxValueValidator(20.0)],
        default=1.0
    )
    
    prerequisites = models.ManyToManyField(
        'self',
        blank=True,
        symmetrical=False,
        related_name='prerequisite_for',
        verbose_name="Prerequisites",
        help_text="Subjects that must be completed before taking this subject"
    )
    
    department = models.ForeignKey(
        'hr.Department',
        on_delete=models.SET_NULL,  
        null=True,
        blank=True,
        related_name='subjects',
        verbose_name="Department"
    )
    
    is_active     = models.BooleanField("Is Active",     default=True)
    is_compulsory = models.BooleanField("Is Compulsory", default=True)
    
    pass_mark = models.DecimalField(
        "Pass Mark", 
        max_digits=5, 
        decimal_places=2, 
        default=50.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    
    applicable_levels = models.ManyToManyField(
        'AcademicLevel',
        verbose_name="Applicable Academic Levels",
        blank=True,
        help_text="Academic levels where this subject is offered"
    )
    
    difficulty_level = models.CharField(
        "Difficulty Level",
        max_length=20,
        choices=[
            ('BEGINNER',     'Beginner'),
            ('INTERMEDIATE', 'Intermediate'),
            ('ADVANCED',     'Advanced'),
            ('EXPERT',       'Expert'),
        ],
        default='INTERMEDIATE'
    )
    
    weight_factor = models.DecimalField(
        "Weight Factor",
        max_digits=3,
        decimal_places=2,
        default=1.00,
        validators=[MinValueValidator(0.5), MaxValueValidator(3.0)],
        help_text="Multiplier for GPA calculation (1.0 = normal weight)"
    )
    
    textbook_required     = models.BooleanField("Textbook Required", default=True)
    recommended_textbooks = models.TextField("Recommended Textbooks", blank=True)
    required_materials    = models.TextField("Required Materials",    blank=True)
    
    objects = SchoolManager()

    def __str__(self):
        return f"{self.abbreviation} - {self.name}"
    
    def get_full_display(self):
        return f"{self.code} - {self.name} ({self.abbreviation})"
    
    def can_be_taken_by_level(self, academic_level):
        if not self.applicable_levels.exists():
            return True
        return self.applicable_levels.filter(pk=academic_level.pk).exists()

    class Meta:
        ordering = ['subject_type', 'abbreviation']
        verbose_name = "Subject"
        verbose_name_plural = "Subjects"
        indexes = [
            models.Index(fields=['subject_type']),
            models.Index(fields=['is_active']),
            models.Index(fields=['is_compulsory']),
            models.Index(fields=['department']),
        ]


# =============================================================================
# ACADEMIC LEVEL MODEL
# =============================================================================

class AcademicLevel(BaseModel):
    """Model for different academic levels/classes (e.g., Grade 1, Grade 2, Form 1, etc.)"""

    name        = models.CharField("Level Name",  max_length=50)
    code        = models.CharField("Level Code",  max_length=10, unique=True)
    description = models.TextField("Description", blank=True)
    
    order = models.PositiveIntegerField("Order", help_text="For ordering levels")
    next_level = models.ForeignKey(
        'self',
        verbose_name="Next Level",
        on_delete=models.SET_NULL,
        related_name="previous_levels",
        null=True,
        blank=True,
        help_text="The level students progress to after completing this one"
    )
    
    has_sections = models.BooleanField(
        "Has Sections/Streams", 
        default=False,
        help_text="Whether this level has multiple sections/streams (A, B, C, etc.)"
    )
    
    is_active             = models.BooleanField("Is Active",         default=True)
    is_graduation_level   = models.BooleanField(
        "Is Graduation Level", 
        default=False,
        help_text="Whether completing this level constitutes graduation"
    )

    objects = SchoolManager()

    def __str__(self):
        return self.name
    
    class Meta:
        ordering = ['order']
        verbose_name = "Academic Level"
        verbose_name_plural = "Academic Levels"


# =============================================================================
# CLASSROOM MODEL
# =============================================================================

class ClassRoom(BaseModel):
    """Model for physical classrooms"""
    name        = models.CharField("Room Name",   max_length=50)
    room_number = models.CharField("Room Number", max_length=20, unique=True)
    building    = models.CharField("Building",    max_length=100, blank=True)
    floor       = models.CharField("Floor",       max_length=10,  blank=True)
    wing        = models.CharField("Wing/Section",max_length=50,  blank=True)
    
    capacity = models.PositiveIntegerField("Capacity", default=0)
    
    ROOM_TYPE_CHOICES = [
        ('REGULAR',          'Regular Classroom'),
        ('LABORATORY',       'Laboratory'),
        ('COMPUTER_LAB',     'Computer Laboratory'),
        ('LIBRARY',          'Library'),
        ('AUDITORIUM',       'Auditorium'),
        ('GYMNASIUM',        'Gymnasium'),
        ('WORKSHOP',         'Workshop'),
        ('CONFERENCE',       'Conference Room'),
        ('MUSIC_ROOM',       'Music Room'),
        ('ART_ROOM',         'Art Room'),
        ('SCIENCE_LAB',      'Science Laboratory'),
        ('LANGUAGE_LAB',     'Language Laboratory'),
        ('EXAMINATION_HALL', 'Examination Hall'),
    ]
    room_type = models.CharField(
        "Room Type", 
        max_length=20, 
        choices=ROOM_TYPE_CHOICES,
        default='REGULAR'
    )
    
    has_projector        = models.BooleanField("Has Projector",        default=False)
    has_computer         = models.BooleanField("Has Computer",         default=False)
    has_air_conditioning = models.BooleanField("Has Air Conditioning", default=False)
    has_whiteboard       = models.BooleanField("Has Whiteboard",       default=True)
    has_blackboard       = models.BooleanField("Has Blackboard",       default=True)
    has_smart_board      = models.BooleanField("Has Smart Board",      default=False)
    has_internet         = models.BooleanField("Has Internet Access",  default=False)
    has_sound_system     = models.BooleanField("Has Sound System",     default=False)
    
    specialized_equipment = models.TextField("Specialized Equipment", blank=True)
    
    is_accessible         = models.BooleanField("Is Accessible",    default=True)
    accessibility_features = models.TextField("Accessibility Features", blank=True)
    
    is_bookable        = models.BooleanField("Is Bookable",        default=True)
    requires_approval  = models.BooleanField("Requires Approval",  default=False)
    
    last_maintenance_date   = models.DateField("Last Maintenance Date",   null=True, blank=True)
    safety_inspection_date  = models.DateField("Safety Inspection Date",  null=True, blank=True)
    
    is_active = models.BooleanField("Is Active", default=True)

    objects = SchoolManager()
    
    def __str__(self):
        return f"{self.room_number} - {self.name}"
    
    def get_full_location(self):
        location_parts = [self.room_number]
        if self.building: location_parts.append(self.building)
        if self.floor:    location_parts.append(f"Floor {self.floor}")
        if self.wing:     location_parts.append(self.wing)
        return ", ".join(location_parts)

    class Meta:
        ordering = ['building', 'floor', 'room_number']
        verbose_name = "Classroom"
        verbose_name_plural = "Classrooms"
        indexes = [
            models.Index(fields=['room_type']),
            models.Index(fields=['building', 'floor']),
            models.Index(fields=['is_active']),
            models.Index(fields=['capacity']),
        ]


# =============================================================================
# CLASS MODEL
# =============================================================================

class Class(BaseModel):
    """Model for a class (combination of academic level and optional section)"""
    academic_level = models.ForeignKey(
        AcademicLevel, 
        verbose_name="Academic Level",
        on_delete=models.CASCADE,
        related_name="classes"
    )
    section = models.CharField(
        "Section", 
        max_length=10, 
        blank=True,
        null=True,
        help_text="E.g., A, B, C (leave blank if no sections)"
    )
    academic_session = models.ForeignKey(
        AcademicSession, 
        verbose_name="Academic Session",
        on_delete=models.CASCADE,
        related_name="classes"
    )
    
    class_teacher = models.ForeignKey(
        'hr.Teacher', 
        verbose_name="Class Teacher",
        on_delete=models.SET_NULL,
        related_name="classes_led",
        null=True, blank=True
    )
    assistant_teacher = models.ForeignKey(
        'hr.Teacher',
        verbose_name="Assistant Teacher",
        on_delete=models.SET_NULL,
        related_name="classes_assisted",
        null=True, blank=True
    )
    
    classroom = models.ForeignKey(
        ClassRoom,
        verbose_name="Primary Classroom",
        on_delete=models.SET_NULL,
        related_name="assigned_classes",
        null=True, blank=True
    )
    
    max_students = models.PositiveIntegerField("Maximum Students", default=30)
    
    class_schedule = models.TextField("Class Schedule", blank=True)
    start_time     = models.TimeField("Start Time", null=True, blank=True)
    end_time       = models.TimeField("End Time",   null=True, blank=True)
    
    class_motto  = models.CharField("Class Motto",  max_length=200, blank=True)
    class_colors = models.CharField("Class Colors", max_length=100, blank=True)
    
    class_average_score = models.DecimalField(
        "Class Average Score",
        max_digits=5, decimal_places=2,
        null=True, blank=True,
    )
    
    attendance_rate = models.DecimalField(
        "Attendance Rate",
        max_digits=5, decimal_places=2,
        null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    
    is_active = models.BooleanField("Is Active", default=True)

    def clean(self):
        super().clean()
        if self.academic_level and self.academic_level.has_sections and not self.section:
            raise ValidationError({'section': 'Section is required for this academic level.'})
        if self.academic_level and not self.academic_level.has_sections and self.section:
            raise ValidationError({'section': 'This academic level does not use sections.'})
        if self.start_time and self.end_time:
            if self.start_time >= self.end_time:
                raise ValidationError({'end_time': 'End time must be after start time.'})

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    objects = SchoolManager()

    def __str__(self):
        if self.section:
            return f"{self.academic_level.name} {self.section} ({self.academic_session})"
        return f"{self.academic_level.name} ({self.academic_session})"
    
    def get_display_name(self):
        if self.section:
            return f"{self.academic_level.name} {self.section}"
        return self.academic_level.name
        
    @property
    def name(self):
        return self.get_display_name()
    
    def has_capacity(self):
        return self.get_current_enrollment_count() < self.max_students
    
    def get_available_capacity(self):
        return max(0, self.max_students - self.get_current_enrollment_count())
    
    def get_occupancy_percentage(self):
        if self.max_students == 0:
            return 0
        return round((self.get_current_enrollment_count() / self.max_students) * 100, 1)
    
    def get_timetable_url(self):
        return reverse('academic:class_timetable', kwargs={'pk': self.pk})

    def get_current_enrollment_count(self):
        try:
            from students.models import StudentClassEnrollment
            return StudentClassEnrollment.objects.filter(
                class_instance=self,
                is_active=True,
                completion_status='ONGOING'
            ).count()
        except Exception:
            return 0
        
    @property
    def active_enrollment_count(self):
        return self.enrollments.filter(is_active=True, completion_status='ONGOING').count()
    
    @property
    def active_subject_count(self):
        return self.subjects.filter(is_active=True).count()
    
    @property
    def subjects_without_teacher_count(self):
        return self.subjects.filter(is_active=True, teacher__isnull=True).count()
    
    def has_all_teachers_assigned(self):
        return not self.subjects.filter(is_active=True, teacher__isnull=True).exists()
    
    @property
    def completion_percentage(self):
        score = 0
        if self.subjects.filter(is_active=True).exists():           score += 1
        if self.has_all_teachers_assigned():                         score += 1
        if self.active_enrollment_count > 0:                         score += 1
        return round((score / 3) * 100)

    class Meta:
        ordering = ['academic_level__order', 'section']
        verbose_name = "Class"
        verbose_name_plural = "Classes"
        constraints = [
            models.UniqueConstraint(
                fields=['academic_level', 'section', 'academic_session'],
                condition=Q(section__isnull=False),
                name='unique_class_with_section'
            ),
            models.UniqueConstraint(
                fields=['academic_level', 'academic_session'],
                condition=Q(section__isnull=True),
                name='unique_class_without_section'
            ),
        ]
        indexes = [
            models.Index(fields=['academic_level', 'academic_session']),
            models.Index(fields=['class_teacher']),
            models.Index(fields=['is_active']),
        ]

# =============================================================================
# STUDENT CLASS ENROLLMENT MODEL
# =============================================================================

class StudentClassEnrollment(BaseModel):
    """Enhanced model for tracking student enrollment in classes"""

    ENROLLMENT_TYPE_CHOICES = [
        ('NEW',               'New Admission'),
        ('CONTINUING',        'Continuing Student'),
        ('TRANSFER_IN',       'Transfer from Another School'),
        ('REPEATER',          'Repeating Class'),
        ('READMISSION',       'Readmitted Student'),
        ('PROMOTED',          'Promoted from Previous Level'),
        ('TRANSFERRED',       'Transferred Between Classes'),
        ('REPEATED',          'Repeated Current Level'),
        ('INTERNAL_TRANSFER', 'Internal Class Transfer'),
    ]
    
    COMPLETION_STATUS_CHOICES = [
        ('ONGOING',    'Ongoing'),
        ('COMPLETED',  'Completed'),
        ('DROPPED',    'Dropped Out'),
        ('TRANSFERRED','Transferred'),
        ('SUSPENDED',  'Suspended'),
        ('WITHDRAWN',  'Withdrawn'),
    ]
    
    PROGRESSION_TYPE_CHOICES = [
        ('NORMAL',      'Normal Progression'),
        ('SKIP',        'Level Skipped'),
        ('REPEAT',      'Level Repeated'),
        ('LATERAL',     'Lateral Transfer'),
        ('READMISSION', 'Readmission'),
    ]

    academic_session = models.ForeignKey(
        'academics.AcademicSession',
        verbose_name="Academic Session",
        on_delete=models.CASCADE,
        related_name="student_class_enrollments"
    )

    student = models.ForeignKey(
        'students.Student',
        verbose_name="Student",
        on_delete=models.CASCADE,
        related_name="class_enrollments"
    )
    
    class_instance = models.ForeignKey(
        'academics.Class',
        verbose_name="Class",
        on_delete=models.CASCADE,
        related_name="enrollments"
    )

    academic_invoice = models.OneToOneField(
        'fees.FeeInvoice',
        verbose_name="Academic Fees Invoice",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='class_enrollment',
        help_text="Invoice generated for this class enrollment"
    )
    
    auto_create_invoice = models.BooleanField(
        "Auto-Create Invoice",
        default=True,
        help_text="Automatically create invoice when enrollment is finalized"
    )
    
    enrollment_date = models.DateField("Enrollment Date")
    roll_number     = models.CharField("Roll Number", max_length=20, blank=True)
    
    is_active = models.BooleanField("Is Active", default=True)
    
    enrollment_type = models.CharField(
        "Enrollment Type",
        max_length=20,
        choices=ENROLLMENT_TYPE_CHOICES,
        default='NEW'
    )
    
    previous_enrollment = models.ForeignKey(
        'self',
        verbose_name="Previous Enrollment",
        on_delete=models.SET_NULL,
        related_name="next_enrollment",
        null=True, blank=True,
    )
    
    completion_date = models.DateField("Completion Date", null=True, blank=True)
    completion_status = models.CharField(
        "Completion Status",
        max_length=20,
        choices=COMPLETION_STATUS_CHOICES,
        default='ONGOING'
    )
    
    enrollment_notes = models.TextField("Enrollment Notes", blank=True)
    
    progression_type = models.CharField(
        "Progression Type",
        max_length=20,
        choices=PROGRESSION_TYPE_CHOICES,
        default='NORMAL',
    )
    
    objects = SchoolManager()

    def __str__(self):
        return f"{self.student} - {self.class_instance} ({self.academic_session})"

    def save(self, *args, **kwargs):
        if not self.enrollment_date:
            self.enrollment_date = timezone.now().date()
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        
        if self.enrollment_date and self.completion_date:
            if self.enrollment_date > self.completion_date:
                raise ValidationError("Enrollment date cannot be after completion date")
        
        if self.enrollment_date and self.academic_session:
            if (self.enrollment_date < self.academic_session.start_date or 
                self.enrollment_date > self.academic_session.end_date):
                raise ValidationError(
                    "Enrollment date must be within the academic session period"
                )
        
        if self.roll_number and self.class_instance and self.academic_session:
            duplicate_roll = StudentClassEnrollment.objects.filter(
                class_instance=self.class_instance,
                academic_session=self.academic_session,
                roll_number=self.roll_number,
                is_active=True
            ).exclude(pk=self.pk if self.pk else None)
            
            if duplicate_roll.exists():
                raise ValidationError({
                    'roll_number': f"Roll number {self.roll_number} is already assigned to another student in this class"
                })
        
        self._validate_no_duplicate_enrollment()

    def _validate_no_duplicate_enrollment(self):
        if not self.student or not self.class_instance or not self.academic_session:
            return
        
        exact_duplicate = StudentClassEnrollment.objects.filter(
            student=self.student,
            class_instance=self.class_instance,
            academic_session=self.academic_session
        )
        if self.pk:
            exact_duplicate = exact_duplicate.exclude(pk=self.pk)
        if exact_duplicate.exists():
            raise ValidationError({
                'student': f"Student {self.student.get_full_name()} is already enrolled in {self.class_instance} for {self.academic_session}"
            })
        
        active_enrollment = StudentClassEnrollment.objects.filter(
            student=self.student,
            academic_session=self.academic_session,
            is_active=True,
            completion_status='ONGOING'
        )
        if self.pk:
            active_enrollment = active_enrollment.exclude(pk=self.pk)
        if active_enrollment.exists():
            existing = active_enrollment.first()
            raise ValidationError({
                'student': f"Student {self.student.get_full_name()} already has an active enrollment in {existing.class_instance} for {self.academic_session}. A student can only be enrolled in one class per session."
            })

    class Meta:
        ordering = ['class_instance', 'roll_number', 'student__last_name']
        verbose_name = "Student Class Enrollment"
        verbose_name_plural = "Student Class Enrollments"
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'academic_session'],
                condition=Q(is_active=True, completion_status='ONGOING'),
                name='unique_active_enrollment_per_session'
            ),
            models.UniqueConstraint(
                fields=['student', 'class_instance', 'academic_session'],
                name='unique_student_class_session'
            ),
            models.UniqueConstraint(
                fields=['class_instance', 'academic_session', 'roll_number'],
                condition=Q(roll_number__isnull=False) & ~Q(roll_number=''),
                name='unique_roll_number_per_class_session'
            ),
        ]
        indexes = [
            models.Index(fields=['student', 'academic_session']),
            models.Index(fields=['class_instance', 'is_active']),
            models.Index(fields=['enrollment_type']),
            models.Index(fields=['completion_status']),
            models.Index(fields=['enrollment_date']),
            models.Index(fields=['student', 'is_active', 'completion_status']),
            models.Index(fields=['progression_type']),
            models.Index(fields=['academic_session', 'is_active', 'completion_status']),
            models.Index(fields=['roll_number']),
            models.Index(fields=['class_instance', 'academic_session', 'roll_number']),
        ]

# =============================================================================
# CLASS SUBJECT MODEL
# =============================================================================

class ClassSubject(BaseModel):
    """Model for subjects assigned to a class"""
    class_instance = models.ForeignKey(
        Class,
        verbose_name="Class",
        on_delete=models.CASCADE,
        related_name="subjects"
    )
    subject = models.ForeignKey(
        Subject,
        verbose_name="Subject",
        on_delete=models.CASCADE,
        related_name="classes"
    )
    teacher = models.ForeignKey(
        'hr.Teacher',
        verbose_name="Subject Teacher",
        on_delete=models.SET_NULL,
        related_name="teaching_subjects",
        null=True, blank=True
    )
    
    is_optional    = models.BooleanField("Is Optional",   default=False)
    hours_per_week = models.PositiveIntegerField("Hours Per Week", default=3)
    total_hours    = models.PositiveIntegerField("Total Hours",    default=0)
    
    schedule_days     = models.JSONField("Schedule Days",     blank=True, null=True)
    preferred_periods = models.JSONField("Preferred Periods", blank=True, null=True)
    
    syllabus             = models.TextField("Syllabus",              blank=True)
    learning_objectives  = models.TextField("Learning Objectives",   blank=True)
    assessment_criteria  = models.TextField("Assessment Criteria",   blank=True)
    
    continuous_assessment_weight = models.DecimalField(
        "Continuous Assessment Weight",
        max_digits=5, decimal_places=2, default=40.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    
    final_exam_weight = models.DecimalField(
        "Final Exam Weight",
        max_digits=5, decimal_places=2, default=60.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    
    textbook           = models.CharField("Textbook",           max_length=200, blank=True)
    reference_materials = models.TextField("Reference Materials", blank=True)
    required_equipment  = models.TextField("Required Equipment",  blank=True)
    
    class_average = models.DecimalField(
        "Class Average", max_digits=5, decimal_places=2, null=True, blank=True,
    )
    
    pass_rate = models.DecimalField(
        "Pass Rate", max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    
    is_active = models.BooleanField("Is Active", default=True)

    objects = SchoolManager()

    def __str__(self):
        return f"{self.subject.name} for {self.class_instance}"
    
    def clean(self):
        super().clean()
        if (self.continuous_assessment_weight + self.final_exam_weight) != 100:
            raise ValidationError(
                "Continuous assessment and final exam weights must total 100%"
            )
        if self.class_instance_id and self.subject_id:
            try:
                if not self.subject.can_be_taken_by_level(self.class_instance.academic_level):
                    raise ValidationError(
                        "This subject is not applicable to the selected academic level"
                    )
            except (ClassSubject.class_instance.RelatedObjectDoesNotExist,
                    ClassSubject.subject.RelatedObjectDoesNotExist):
                pass

    def get_assessment_breakdown(self):
        return {
            'continuous_assessment': self.continuous_assessment_weight,
            'final_exam':            self.final_exam_weight,
            'total':                 self.continuous_assessment_weight + self.final_exam_weight,
        }
    
    def get_schedule_display(self):
        if self.schedule_days:
            days = ", ".join(self.schedule_days)
            return f"{days} ({self.hours_per_week}h/week)"
        return f"{self.hours_per_week} hours per week"
    
    def is_compulsory_for_level(self):
        return self.subject.is_compulsory and not self.is_optional

    class Meta:
        ordering = ['class_instance', 'subject__name']
        verbose_name = "Class Subject"
        verbose_name_plural = "Class Subjects"
        unique_together = ['class_instance', 'subject']
        indexes = [
            models.Index(fields=['class_instance', 'is_active']),
            models.Index(fields=['teacher']),
            models.Index(fields=['subject']),
            models.Index(fields=['is_optional']),
        ]

# =============================================================================
# ACADEMIC PROGRESS MODEL
# =============================================================================

class AcademicProgress(BaseModel):
    """
    Track overall academic progress and performance for students in each session.
    
    Purpose: Consolidated record of student's academic performance including:
    - Overall grades and GPA
    - Attendance tracking
    - Subject performance summary
    - Promotion eligibility and decisions
    - Teacher and parent feedback
    
    This is the master record used for:
    - Report cards
    - Promotion decisions
    - Academic standing
    - Historical performance tracking
    """
    
    PROGRESS_STATUS_CHOICES = [
        ('EXCELLENT',         'Excellent'),
        ('GOOD',              'Good'),
        ('SATISFACTORY',      'Satisfactory'),
        ('NEEDS_IMPROVEMENT', 'Needs Improvement'),
        ('POOR',              'Poor'),
    ]
    
    PROMOTION_DECISION_CHOICES = [
        ('PROMOTED',    'Promoted'),
        ('REPEAT',      'Repeat Class'),
        ('CONDITIONAL', 'Conditional Promotion'),
        ('PENDING',     'Decision Pending'),
        ('TRANSFERRED', 'Transferred Out'),
        ('WITHDRAWN',   'Withdrawn'),
    ]
    
    student = models.ForeignKey(
        'students.Student',
        verbose_name="Student",
        on_delete=models.CASCADE,
        related_name="academic_progress"
    )
    
    academic_session = models.ForeignKey(
        AcademicSession,
        verbose_name="Academic Session",
        on_delete=models.CASCADE,
        related_name="student_progress"
    )
    
    class_enrollment = models.ForeignKey(
        StudentClassEnrollment,
        verbose_name="Class Enrollment",
        on_delete=models.CASCADE,
        related_name="progress_records"
    )
    
    overall_grade = models.CharField("Overall Grade", max_length=5, blank=True)
    
    gpa = models.DecimalField(
        "GPA", max_digits=4, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(4)],
    )
    
    percentage = models.DecimalField(
        "Overall Percentage", max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    
    total_school_days = models.PositiveIntegerField("Total School Days", default=0)
    days_attended     = models.PositiveIntegerField("Days Attended",     default=0)
    
    attendance_percentage = models.DecimalField(
        "Attendance Percentage", max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    
    progress_status = models.CharField(
        "Progress Status",
        max_length=20,
        choices=PROGRESS_STATUS_CHOICES,
        blank=True,
        db_index=True
    )
    
    is_eligible_for_promotion = models.BooleanField("Eligible for Promotion", default=False, db_index=True)
    
    promotion_decision = models.CharField(
        "Promotion Decision",
        max_length=20,
        choices=PROMOTION_DECISION_CHOICES,
        default='PENDING',
        db_index=True
    )
    
    promoted_to_level = models.ForeignKey(
        AcademicLevel,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='promoted_students',
        verbose_name="Promoted to Academic Level",
    )
    
    promotion_date = models.DateField("Promotion Date", null=True, blank=True)
    
    total_subjects   = models.PositiveIntegerField("Total Subjects",   default=0)
    subjects_passed  = models.PositiveIntegerField("Subjects Passed",  default=0)
    subjects_failed  = models.PositiveIntegerField("Subjects Failed",  default=0)
    
    is_final    = models.BooleanField("Is Final Record", default=False, db_index=True)
    final_date  = models.DateField("Final Record Date", null=True, blank=True)
    finalized_by = models.CharField("Finalized By", max_length=100, blank=True)
    
    teacher_comments      = models.TextField("Teacher Comments",       blank=True)
    head_teacher_comments = models.TextField("Head Teacher Comments",  blank=True)
    parent_comments       = models.TextField("Parent Comments",        blank=True)
    recommendations       = models.TextField("Recommendations",        blank=True)
    
    objects = SchoolManager()
    
    def __str__(self):
        return f"{self.student.get_full_name()} - {self.academic_session.name} Progress"
    
    @property
    def pass_percentage(self):
        return self.calculate_pass_percentage()
    
    @property
    def is_passing(self):
        return self.subjects_failed == 0 and self.total_subjects > 0
    
    @property
    def performance_level(self):
        if not self.percentage:
            return "Not Graded"
        if self.percentage >= 90: return "Distinction"
        if self.percentage >= 80: return "Excellence"
        if self.percentage >= 70: return "Very Good"
        if self.percentage >= 60: return "Good"
        if self.percentage >= 50: return "Satisfactory"
        return "Needs Improvement"
    
    def calculate_attendance_percentage(self):
        if self.total_school_days > 0:
            percentage = (self.days_attended / self.total_school_days) * 100
            self.attendance_percentage = round(percentage, 2)
            return self.attendance_percentage
        return 0
    
    def calculate_pass_percentage(self):
        if self.total_subjects > 0:
            return round((self.subjects_passed / self.total_subjects) * 100, 2)
        return 0
    
    def update_subject_counts(self):
        pass
    
    def determine_promotion_eligibility(self):
        min_attendance = self.academic_session.minimum_attendance_percentage
        meets_attendance = (
            self.attendance_percentage and
            self.attendance_percentage >= min_attendance
        )
        passed_all_subjects = self.subjects_failed == 0
        self.is_eligible_for_promotion = meets_attendance and passed_all_subjects
        return self.is_eligible_for_promotion
    
    def finalize_record(self, user=None):
        if self.is_final:
            logger.warning(f"Progress record {self.pk} is already finalized")
            return False
        
        self.is_final   = True
        self.final_date = timezone.now().date()
        
        if user:
            self.finalized_by = str(user.get_full_name() if hasattr(user, 'get_full_name') else user)
        
        self.determine_promotion_eligibility()
        self.save()
        logger.info(f"Finalized progress record for {self.student} - {self.academic_session}")
        return True
    
    def clean(self):
        super().clean()
        errors = {}
        
        if self.days_attended > self.total_school_days:
            errors['days_attended'] = "Days attended cannot exceed total school days"
        
        if self.subjects_passed + self.subjects_failed > self.total_subjects:
            errors['total_subjects'] = "Sum of passed and failed subjects cannot exceed total subjects"
        
        if self.gpa and not (0 <= self.gpa <= 4):
            errors['gpa'] = "GPA must be between 0.00 and 4.00"
        
        if self.percentage and not (0 <= self.percentage <= 100):
            errors['percentage'] = "Percentage must be between 0 and 100"
        
        if self.class_enrollment and self.academic_session:
            if self.class_enrollment.academic_session != self.academic_session:
                errors['class_enrollment'] = "Class enrollment must be for the same academic session"
        
        if self.class_enrollment and self.student:
            if self.class_enrollment.student != self.student:
                errors['class_enrollment'] = "Class enrollment must be for the same student"
        
        if errors:
            raise ValidationError(errors)
    
    def save(self, *args, **kwargs):
        if self.total_school_days > 0:
            self.calculate_attendance_percentage()
        self.full_clean()
        super().save(*args, **kwargs)
    
    class Meta:
        ordering = ['-academic_session__start_date', 'student__last_name']
        verbose_name = "Academic Progress"
        verbose_name_plural = "Academic Progress Records"
        unique_together = ['student', 'academic_session']
        indexes = [
            models.Index(fields=['student', 'academic_session']),
            models.Index(fields=['is_eligible_for_promotion']),
            models.Index(fields=['promotion_decision']),
            models.Index(fields=['is_final']),
            models.Index(fields=['progress_status']),
            models.Index(fields=['class_enrollment']),
            models.Index(fields=['promoted_to_level']),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(days_attended__lte=models.F('total_school_days')),
                name='attendance_valid'
            ),
            models.CheckConstraint(
                check=Q(gpa__gte=0, gpa__lte=4) | Q(gpa__isnull=True),
                name='gpa_valid_range'
            ),
            models.CheckConstraint(
                check=Q(percentage__gte=0, percentage__lte=100) | Q(percentage__isnull=True),
                name='percentage_valid_range'
            ),
        ]