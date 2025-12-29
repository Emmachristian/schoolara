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
        """Get human-readable status"""
        if self.is_academically_closed:
            return "Closed"
        elif self.is_current:
            return "Current"
        elif self.is_active:
            current_date = timezone.now().date()
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
        """Get days remaining in the session"""
        if not self.end_date:
            return 0
        
        current_date = timezone.now().date()
        if current_date > self.end_date:
            return 0
        
        return (self.end_date - current_date).days
    
    @property
    def days_elapsed(self):
        """Get days elapsed since session started"""
        if not self.start_date:
            return 0
        
        current_date = timezone.now().date()
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
        """Get session progress as percentage"""
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
        """Check if enrollment is still open"""
        if self.is_academically_closed:
            return False
        
        if not self.enrollment_deadline:
            return self.is_active  # No deadline set
        
        current_date = timezone.now().date()
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
        
        # ✅ SMART VALIDATION: Only enforce SchoolConfiguration for regular sessions
        if not self.is_special_session:
            try:
                config = SchoolConfiguration.get_instance()
                if config:
                    # Validate term_number against config for regular sessions
                    if not config.validate_period_number(self.term_number):
                        errors['term_number'] = (
                            f'Period number {self.term_number} is invalid for '
                            f'{config.get_term_system_display()} system (max: {config.get_period_count()}). '
                            f'To create a session outside the regular term structure, '
                            f'check the "Is Special Session" checkbox.'
                        )
                    
                    # Warn if period_type differs from config (but don't block)
                    if self.period_type and self.period_type != config.term_system:
                        logger.warning(
                            f"Regular session {self.year_name} term {self.term_number} "
                            f"has period_type '{self.period_type}' which differs from "
                            f"school configuration '{config.term_system}'"
                        )
            except Exception as e:
                logger.warning(f"Could not validate against SchoolConfiguration: {e}")
                if self.term_number > 12:
                    errors['term_number'] = 'Period number cannot exceed 12'
        else:
            # ✅ For special sessions, be more lenient with term_number
            if self.term_number > 20:
                errors['term_number'] = 'Period number cannot exceed 20 even for special sessions'
            
            # Require period_type and term_name for special sessions
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
            # ✅ REGULAR SESSION - strict auto-generation from config
            try:
                config = SchoolConfiguration.get_instance()
                if config:
                    # Auto-set period_type if blank
                    if not self.period_type:
                        self.period_type = config.term_system
                        logger.debug(
                            f"Regular session: Auto-set period_type='{self.period_type}' "
                            f"from SchoolConfiguration"
                        )
                    
                    # Auto-generate term_name if blank
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
                logger.error(f"Error getting SchoolConfiguration: {e}")
                self._set_fallback_values()
        
        else:
            # ✅ SPECIAL SESSION - user provides values, with smart defaults
            logger.info(
                f"Creating/updating special session: {self.year_name} - "
                f"{self.term_name or 'unnamed'}"
            )
            
            # Set default period_type if not provided
            if not self.period_type:
                self.period_type = 'custom'
                logger.debug("Special session: Defaulting to period_type='custom'")
            
            # Generate descriptive name if not provided
            if not self.term_name:
                type_names = {
                    'holiday_program': 'Holiday Program',
                    'summer_school': 'Summer School',
                    'remedial': 'Remedial Program',
                    'intensive': 'Intensive Course',
                    'custom': 'Special Session',
                }
                base_name = type_names.get(self.period_type, 'Special Session')
                self.term_name = f"{base_name} {self.term_number}"
                logger.debug(f"Special session: Generated term_name='{self.term_name}'")
        
        # Validate before saving
        self.full_clean()
        
        # Ensure only one current session
        if self.is_current:
            AcademicSession.objects.filter(is_current=True).exclude(pk=self.pk).update(is_current=False)
        
        super().save(*args, **kwargs)
    
    def _set_fallback_values(self):
        """Set fallback values if SchoolConfiguration is not available"""
        if not self.period_type:
            self.period_type = 'term'
        
        if not self.term_name:
            period_types = {
                'semester': 'Semester',
                'quarter': 'Quarter',
                'trimester': 'Trimester',
                'module': 'Module',
                'block': 'Block',
                'term': 'Term',
            }
            period_name = period_types.get(self.period_type, 'Term')
            self.term_name = f"{period_name} {self.term_number}"
    
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
        
        Args:
            user: User performing the closure
        """
        if self.is_academically_closed:
            logger.warning(f"Academic session {self} is already closed")
            return
        
        self.is_academically_closed = True
        self.is_active = False
        self.is_current = False
        self.academic_closure_date = timezone.now()
        
        if user:
            self.closed_by_id = str(user.id) if hasattr(user, 'id') else str(user.pk)
        
        self.save()
        
        logger.info(f"Academic session {self} closed by {self.closed_by_name}")
    
    def reopen_academically(self, user=None):
        """
        Reopen a closed session (requires proper authorization).
        
        Args:
            user: User performing the reopen
        """
        if not self.is_academically_closed:
            logger.warning(f"Academic session {self} is not closed")
            return
        
        self.is_academically_closed = False
        self.is_active = True
        self.academic_closure_date = None
        self.closed_by_id = None
        
        self.save()
        
        user_name = user.get_full_name() if user else "System"
        logger.warning(f"Academic session {self} reopened by {user_name}")
    
    # -------------------------------------------------------------------------
    # PERMISSION CHECK METHODS
    # -------------------------------------------------------------------------
    
    def can_modify_grades(self):
        """Check if grades can still be modified"""
        return not self.is_academically_closed
    
    def can_enroll_students(self):
        """Check if students can be enrolled in this session"""
        return self.is_enrollment_open and not self.is_academically_closed
    
    def can_take_attendance(self):
        """Check if attendance can be recorded"""
        return not self.is_academically_closed and self.is_active
    
    def can_modify_timetable(self):
        """Check if timetable can be modified"""
        return not self.is_academically_closed and self.is_active
    
    def can_be_closed(self):
        """Check if session can be closed"""
        return not self.is_academically_closed and not self.is_current
    
    def can_be_made_current(self):
        """Check if this session can be made current"""
        if self.is_academically_closed:
            return False
        
        current_date = timezone.now().date()
        return self.start_date <= current_date <= self.end_date
    
    # -------------------------------------------------------------------------
    # STATUS CHECK METHODS
    # -------------------------------------------------------------------------
    
    def is_current_session(self):
        """Check if this is the current session"""
        today = timezone.now().date()
        return self.start_date <= today <= self.end_date and self.is_current
    
    def is_upcoming(self):
        """Check if session is in the future"""
        return self.start_date > timezone.now().date()
    
    def is_past(self):
        """Check if session has ended"""
        return self.end_date < timezone.now().date()
    
    # -------------------------------------------------------------------------
    # DURATION METHODS
    # -------------------------------------------------------------------------
    
    def get_duration_days(self):
        """Get the duration of this session in days"""
        return self.total_days
    
    def get_duration_weeks(self):
        """Get the duration of this session in weeks"""
        return self.total_days // 7 if self.total_days > 0 else 0
    
    # -------------------------------------------------------------------------
    # HELPER METHODS
    # -------------------------------------------------------------------------
    
    def get_closed_by_user(self):
        """Get the user who closed this session"""
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
        """Get human-readable session category"""
        if self.is_special_session:
            return f"Special Session ({self.get_period_type_display()})"
        return f"Regular Session ({self.get_period_type_display()})"
    
    def get_academic_calendar(self):
        """Get academic calendar events for this session"""
        events = []
        
        # Session start and end
        events.append({
            'title': f'{self.name} Begins',
            'date': self.start_date,
            'type': 'session_start'
        })
        events.append({
            'title': f'{self.name} Ends',
            'date': self.end_date,
            'type': 'session_end'
        })
        
        # Enrollment deadline
        if self.enrollment_deadline:
            events.append({
                'title': 'Enrollment Deadline',
                'date': self.enrollment_deadline,
                'type': 'enrollment_deadline'
            })
        
        return sorted(events, key=lambda x: x['date'])
    
    def get_status_display_class(self):
        """Get CSS class for status display"""
        if self.is_academically_closed:
            return 'status-closed'
        elif self.is_current:
            return 'status-current'
        elif self.is_active:
            return 'status-active'
        else:
            return 'status-inactive'
    
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
    
    Examples:
    - "Easter Monday" (single day)
    - "Mid-Term Break" (Feb 19-23)
    - "Independence Day" (single day, recurring)
    - "End of Year Break" (multi-week)
    """
    
    # -------------------------------------------------------------------------
    # HOLIDAY TYPE CHOICES
    # -------------------------------------------------------------------------
    
    HOLIDAY_TYPE_CHOICES = [
        ('PUBLIC', 'Public Holiday'),           # National/public holidays
        ('SCHOOL_BREAK', 'School Break'),       # Term breaks, summer break
        ('SCHOOL_EVENT', 'School Event'),       # Sports day, open house
        ('RELIGIOUS', 'Religious Holiday'),     # Easter, Eid, Diwali, etc.
        ('PROFESSIONAL', 'Professional Day'),   # Staff training, PD days
        ('EXAMINATION', 'Examination Period'),  # Exam days (partial closure)
        ('CUSTOM', 'Custom Holiday'),           # School-specific
    ]
    
    # -------------------------------------------------------------------------
    # CORE FIELDS
    # -------------------------------------------------------------------------
    
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
    
    # -------------------------------------------------------------------------
    # DATE RANGE
    # -------------------------------------------------------------------------
    
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
    
    # -------------------------------------------------------------------------
    # ACADEMIC SESSION ASSOCIATION (Optional - for context only)
    # -------------------------------------------------------------------------
    
    academic_session = models.ForeignKey(
        AcademicSession,
        on_delete=models.SET_NULL,
        related_name='holidays',
        verbose_name="Academic Session",
        null=True,
        blank=True,
        help_text="Academic session this holiday falls within (optional, for reference)"
    )
    
    # -------------------------------------------------------------------------
    # OPERATIONAL FLAGS
    # -------------------------------------------------------------------------
    
    is_school_closed = models.BooleanField(
        "School Closed",
        default=True,
        help_text="Whether school is completely closed"
    )
    
    is_partial_closure = models.BooleanField(
        "Partial Closure",
        default=False,
        help_text="School open but limited activities (e.g., exams only)"
    )
    
    affects_attendance = models.BooleanField(
        "Affects Attendance",
        default=True,
        help_text="Whether absence on this day affects attendance records"
    )
    
    affects_payroll = models.BooleanField(
        "Affects Payroll",
        default=False,
        help_text="Whether this is a paid holiday for staff"
    )
    
    is_recurring = models.BooleanField(
        "Is Recurring",
        default=False,
        help_text="Whether this holiday repeats annually"
    )
    
    # -------------------------------------------------------------------------
    # DISPLAY SETTINGS
    # -------------------------------------------------------------------------
    
    color = models.CharField(
        "Calendar Color",
        max_length=7,
        default="#FF0000",
        help_text="Hex color for calendar display (e.g., #FF0000)"
    )
    
    # -------------------------------------------------------------------------
    # NOTIFICATIONS
    # -------------------------------------------------------------------------
    
    notify_parents = models.BooleanField(
        "Notify Parents",
        default=True,
        help_text="Send notification to parents about this holiday"
    )
    
    notify_staff = models.BooleanField(
        "Notify Staff",
        default=True,
        help_text="Send notification to staff about this holiday"
    )
    
    # -------------------------------------------------------------------------
    # METADATA
    # -------------------------------------------------------------------------
    
    description = models.TextField(
        "Description",
        blank=True,
        help_text="Additional details about this holiday"
    )
    
    notes = models.TextField(
        "Internal Notes",
        blank=True,
        help_text="Internal notes (not visible to parents/students)"
    )
    
    # -------------------------------------------------------------------------
    # CUSTOM MANAGER
    # -------------------------------------------------------------------------
    
    objects = SchoolManager()
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        if self.end_date and self.start_date != self.end_date:
            return f"{self.name} ({self.start_date} to {self.end_date})"
        return f"{self.name} - {self.start_date}"
    
    # -------------------------------------------------------------------------
    # VALIDATION
    # -------------------------------------------------------------------------
    
    def clean(self):
        """Enhanced validation"""
        super().clean()
        errors = {}
        
        # Date validation
        if self.end_date and self.start_date > self.end_date:
            errors['end_date'] = 'End date cannot be before start date'
        
        # Closure validation
        if self.is_partial_closure and self.is_school_closed:
            errors['is_partial_closure'] = 'Cannot be both fully closed and partially closed'
        
        # Color validation
        if self.color:
            import re
            if not re.match(r'^#[0-9A-Fa-f]{6}$', self.color):
                errors['color'] = 'Invalid hex color code (e.g., #FF0000)'
        
        if errors:
            raise ValidationError(errors)
    
    def save(self, *args, **kwargs):
        """Save with validation"""
        self.full_clean()
        super().save(*args, **kwargs)
    
    # -------------------------------------------------------------------------
    # PROPERTIES
    # -------------------------------------------------------------------------
    
    @property
    def duration_days(self):
        """Get duration in days"""
        if not self.end_date or self.start_date == self.end_date:
            return 1
        return (self.end_date - self.start_date).days + 1
    
    @property
    def is_single_day(self):
        """Check if this is a single-day holiday"""
        return self.end_date is None or self.start_date == self.end_date
    
    @property
    def is_current(self):
        """Check if holiday is currently active"""
        today = timezone.now().date()
        if self.end_date:
            return self.start_date <= today <= self.end_date
        return self.start_date == today
    
    @property
    def is_upcoming(self):
        """Check if holiday is in the future"""
        return self.start_date > timezone.now().date()
    
    @property
    def is_past(self):
        """Check if holiday has passed"""
        end = self.end_date or self.start_date
        return end < timezone.now().date()
    
    # -------------------------------------------------------------------------
    # INSTANCE METHODS
    # -------------------------------------------------------------------------
    
    def overlaps_with_date(self, check_date):
        """
        Check if a date falls within this holiday.
        
        Args:
            check_date: Date to check
            
        Returns:
            bool: True if date overlaps, False otherwise
        """
        if self.end_date:
            return self.start_date <= check_date <= self.end_date
        return self.start_date == check_date
    
    def overlaps_with_range(self, start_date, end_date):
        """
        Check if this holiday overlaps with a date range.
        
        Args:
            start_date: Range start date
            end_date: Range end date
            
        Returns:
            bool: True if overlaps, False otherwise
        """
        holiday_end = self.end_date or self.start_date
        return not (holiday_end < start_date or self.start_date > end_date)
    
    def get_display_class(self):
        """Get CSS class for holiday type display"""
        type_classes = {
            'PUBLIC': 'holiday-public',
            'SCHOOL_BREAK': 'holiday-break',
            'SCHOOL_EVENT': 'holiday-event',
            'RELIGIOUS': 'holiday-religious',
            'PROFESSIONAL': 'holiday-professional',
            'EXAMINATION': 'holiday-exam',
            'CUSTOM': 'holiday-custom',
        }
        return type_classes.get(self.holiday_type, 'holiday-default')
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
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
        # Core academic subjects
        ('MATH', 'Mathematics'),
        ('LANG_ARTS', 'Language Arts'),
        ('SCIENCES', 'Sciences'),
        ('SOCIAL', 'Social Studies'),

        # Learning Area (Lower Primary specific)
        ('LITERACY', 'Literacy'),
        ('NUMERACY', 'Numeracy'),
        ('SCIENCE_ENV', 'Environmental Education'),
        ('RELIGION', 'Religious & Moral Education'),
        ('CREATIVE', 'Creative Arts & Life Skills'),

        # Language subjects
        ('MOTHER_TONGUE', 'Mother Tongue'),
        ('FOREIGN_LANG', 'Foreign Language'),

        # Specialized or skill-based
        ('ARTS_CRAFTS', 'Arts and Crafts'),
        ('MUSIC', 'Music'),
        ('PE', 'Physical Education'),
        ('RELIGIOUS', 'Religious Studies'),
        ('COMPUTER', 'Computer Studies'),
        ('LIFE_SKILLS', 'Life Skills'),

        # Vocational/Technical (secondary level)
        ('TECHNICAL', 'Technical Subjects'),
        ('BUSINESS', 'Business Studies'),
        ('AGRICULTURE', 'Agriculture'),
        ('HOME_ECON', 'Home Economics'),

        # Other / Elective
        ('EXTRA', 'Extracurricular Activities'),
        ('CLUBS', 'Clubs and Societies'),
        ('GUIDANCE', 'Guidance & Counselling'),

        # Custom
        ('OTHER', 'Other / Miscellaneous'),
    ]
    subject_type = models.CharField(
        "Subject Type", 
        max_length=20, 
        choices=SUBJECT_TYPE_CHOICES,
        default='SCIENCES'
    )
    
    # Academic details
    credit_hours = models.DecimalField(
        "Credit Hours", 
        max_digits=4, 
        decimal_places=1, 
        validators=[MinValueValidator(0.5), MaxValueValidator(20.0)],
        default=1.0
    )
    
    # Prerequisites relationship
    prerequisites = models.ManyToManyField(
        'self',
        blank=True,
        symmetrical=False,
        related_name='prerequisite_for',
        verbose_name="Prerequisites",
        help_text="Subjects that must be completed before taking this subject"
    )
    
    # Department/Faculty association
    department = models.ForeignKey(
        'hr.Department',
        on_delete=models.SET_NULL,  
        null=True,
        blank=True,
        related_name='subjects',
        verbose_name="Department"
    )
    
    # Status and settings
    is_active = models.BooleanField("Is Active", default=True)
    is_compulsory = models.BooleanField("Is Compulsory", default=True)
    
    # Grading settings
    pass_mark = models.DecimalField(
        "Pass Mark", 
        max_digits=5, 
        decimal_places=2, 
        default=50.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    
    # Academic level applicability
    applicable_levels = models.ManyToManyField(
        'AcademicLevel',
        verbose_name="Applicable Academic Levels",
        blank=True,
        help_text="Academic levels where this subject is offered"
    )
    
    # Subject difficulty and weighting
    difficulty_level = models.CharField(
        "Difficulty Level",
        max_length=20,
        choices=[
            ('BEGINNER', 'Beginner'),
            ('INTERMEDIATE', 'Intermediate'),
            ('ADVANCED', 'Advanced'),
            ('EXPERT', 'Expert'),
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
    
    # Resources and materials
    textbook_required = models.BooleanField("Textbook Required", default=True)
    recommended_textbooks = models.TextField("Recommended Textbooks", blank=True)
    required_materials = models.TextField("Required Materials", blank=True)
    
    # -------------------------------------------------------------------------
    # METHODS
    # -------------------------------------------------------------------------

    # Add the custom manager
    objects = SchoolManager()

    def __str__(self):
        return f"{self.abbreviation} - {self.name}"
    
    def get_full_display(self):
        """Return full subject identification"""
        return f"{self.code} - {self.name} ({self.abbreviation})"
    
    def can_be_taken_by_level(self, academic_level):
        """Check if subject can be taken by students at a specific academic level"""
        if not self.applicable_levels.exists():
            return True  # If no levels specified, assume applicable to all
        return self.applicable_levels.filter(pk=academic_level.pk).exists()

    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------

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

    name = models.CharField("Level Name", max_length=50)
    code = models.CharField("Level Code", max_length=10, unique=True)
    description = models.TextField("Description", blank=True)
    
    # Ordering and progression
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
    
    # Section/Stream configuration
    has_sections = models.BooleanField(
        "Has Sections/Streams", 
        default=False,
        help_text="Whether this level has multiple sections/streams (A, B, C, etc.)"
    )
    
    # Status
    is_active = models.BooleanField("Is Active", default=True)
    is_graduation_level = models.BooleanField(
        "Is Graduation Level", 
        default=False,
        help_text="Whether completing this level constitutes graduation"
    )

    # Add the custom manager
    objects = SchoolManager()

    def __str__(self):
        return self.name
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------

    class Meta:
        ordering = ['order']
        verbose_name = "Academic Level"
        verbose_name_plural = "Academic Levels"


# =============================================================================
# CLASSROOM MODEL
# =============================================================================

class ClassRoom(BaseModel):
    """Model for physical classrooms"""
    name = models.CharField("Room Name", max_length=50)
    room_number = models.CharField("Room Number", max_length=20, unique=True)
    building = models.CharField("Building", max_length=100, blank=True)
    floor = models.CharField("Floor", max_length=10, blank=True)
    wing = models.CharField("Wing/Section", max_length=50, blank=True)
    
    # Capacity and features
    capacity = models.PositiveIntegerField("Capacity", default=0)
    
    ROOM_TYPE_CHOICES = [
        ('REGULAR', 'Regular Classroom'),
        ('LABORATORY', 'Laboratory'),
        ('COMPUTER_LAB', 'Computer Laboratory'),
        ('LIBRARY', 'Library'),
        ('AUDITORIUM', 'Auditorium'),
        ('GYMNASIUM', 'Gymnasium'),
        ('WORKSHOP', 'Workshop'),
        ('CONFERENCE', 'Conference Room'),
        ('MUSIC_ROOM', 'Music Room'),
        ('ART_ROOM', 'Art Room'),
        ('SCIENCE_LAB', 'Science Laboratory'),
        ('LANGUAGE_LAB', 'Language Laboratory'),
        ('EXAMINATION_HALL', 'Examination Hall'),
    ]
    room_type = models.CharField(
        "Room Type", 
        max_length=20, 
        choices=ROOM_TYPE_CHOICES,
        default='REGULAR'
    )
    
    # Equipment and features
    has_projector = models.BooleanField("Has Projector", default=False)
    has_computer = models.BooleanField("Has Computer", default=False)
    has_air_conditioning = models.BooleanField("Has Air Conditioning", default=False)
    has_whiteboard = models.BooleanField("Has Whiteboard", default=True)
    has_blackboard = models.BooleanField("Has Blackboard", default=True)
    has_smart_board = models.BooleanField("Has Smart Board", default=False)
    has_internet = models.BooleanField("Has Internet Access", default=False)
    has_sound_system = models.BooleanField("Has Sound System", default=False)
    
    # Specialized equipment
    specialized_equipment = models.TextField(
        "Specialized Equipment",
        blank=True,
        help_text="List of specialized equipment available in this room"
    )
    
    # Accessibility
    is_accessible = models.BooleanField("Is Accessible", default=True)
    accessibility_features = models.TextField(
        "Accessibility Features",
        blank=True,
        help_text="Specific accessibility features available"
    )
    
    # Booking and availability
    is_bookable = models.BooleanField("Is Bookable", default=True)
    requires_approval = models.BooleanField("Requires Approval", default=False)
    
    # Safety and maintenance
    last_maintenance_date = models.DateField("Last Maintenance Date", null=True, blank=True)
    safety_inspection_date = models.DateField("Safety Inspection Date", null=True, blank=True)
    
    # Status
    is_active = models.BooleanField("Is Active", default=True)

    # Add the custom manager
    objects = SchoolManager()
    
    # -------------------------------------------------------------------------
    # METHODS
    # -------------------------------------------------------------------------

    def __str__(self):
        return f"{self.room_number} - {self.name}"
    
    def get_full_location(self):
        """Get full location description"""
        location_parts = [self.room_number]
        if self.building:
            location_parts.append(self.building)
        if self.floor:
            location_parts.append(f"Floor {self.floor}")
        if self.wing:
            location_parts.append(self.wing)
        return ", ".join(location_parts)

    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------

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
    
    # Class leadership
    class_teacher = models.ForeignKey(
        'hr.Teacher', 
        verbose_name="Class Teacher",
        on_delete=models.SET_NULL,
        related_name="classes_led",
        null=True,
        blank=True
    )
    assistant_teacher = models.ForeignKey(
        'hr.Teacher',
        verbose_name="Assistant Teacher",
        on_delete=models.SET_NULL,
        related_name="classes_assisted",
        null=True,
        blank=True
    )
    
    # Physical assignment
    classroom = models.ForeignKey(
        ClassRoom,
        verbose_name="Primary Classroom",
        on_delete=models.SET_NULL,
        related_name="assigned_classes",
        null=True,
        blank=True
    )
    
    # Class settings
    max_students = models.PositiveIntegerField("Maximum Students", default=30)
    
    # Schedule and timing
    class_schedule = models.TextField("Class Schedule", blank=True)
    start_time = models.TimeField("Start Time", null=True, blank=True)
    end_time = models.TimeField("End Time", null=True, blank=True)
    
    # Academic configuration
    class_motto = models.CharField("Class Motto", max_length=200, blank=True)
    class_colors = models.CharField("Class Colors", max_length=100, blank=True)
    
    # Performance tracking
    class_average_score = models.DecimalField(
        "Class Average Score",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Current class average performance score"
    )
    
    attendance_rate = models.DecimalField(
        "Attendance Rate",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Class attendance rate percentage"
    )
    
    # Status
    is_active = models.BooleanField("Is Active", default=True)

    # -------------------------------------------------------------------------
    # VALIDATION AND SAVE METHODS
    # -------------------------------------------------------------------------

    def clean(self):
        """Custom validation"""
        super().clean()
        
        # If academic level has sections, section field is required
        if self.academic_level and self.academic_level.has_sections and not self.section:
            raise ValidationError({
                'section': 'Section is required for this academic level.'
            })
        
        # If academic level doesn't have sections, section should be empty
        if self.academic_level and not self.academic_level.has_sections and self.section:
            raise ValidationError({
                'section': 'This academic level does not use sections.'
            })
        
        # Validate time schedule
        if self.start_time and self.end_time:
            if self.start_time >= self.end_time:
                raise ValidationError({
                    'end_time': 'End time must be after start time.'
                })

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    # -------------------------------------------------------------------------
    # DISPLAY METHODS
    # -------------------------------------------------------------------------

    # Add the custom manager
    objects = SchoolManager()

    def __str__(self):
        if self.section:
            return f"{self.academic_level.name} {self.section} ({self.academic_session})"
        else:
            return f"{self.academic_level.name} ({self.academic_session})"
    
    def get_display_name(self):
        """Get a clean display name for the class"""
        if self.section:
            return f"{self.academic_level.name} {self.section}"
        else:
            return self.academic_level.name
        
    @property
    def name(self):
        """Backward compatibility property"""
        return self.get_display_name()
    
    # -------------------------------------------------------------------------
    # CAPACITY METHODS
    # -------------------------------------------------------------------------

    def has_capacity(self):
        """Check if class has space for more students"""
        return self.get_current_enrollment_count() < self.max_students
    
    def get_available_capacity(self):
        """Get number of available spots"""
        return max(0, self.max_students - self.get_current_enrollment_count())
    
    def get_occupancy_percentage(self):
        """Get class occupancy as percentage"""
        if self.max_students == 0:
            return 0
        return round((self.get_current_enrollment_count() / self.max_students) * 100, 1)
    
    def get_timetable_url(self):
        """Get URL for class timetable"""
        return reverse('academic:class_timetable', kwargs={'pk': self.pk})

    def get_current_enrollment_count(self):
        """Get current number of enrolled students for this class"""
        try:
            from students.models import StudentClassEnrollment
            return StudentClassEnrollment.objects.filter(
                class_instance=self,
                is_active=True,
                completion_status='ONGOING'
            ).count()
        except ImportError:
            return 0
        except Exception:
            return 0

    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------

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

    # -------------------------------------------------------------------------
    # CHOICE FIELDS
    # -------------------------------------------------------------------------

    ENROLLMENT_TYPE_CHOICES = [
        ('NEW', 'New Admission'),
        ('CONTINUING', 'Continuing Student'),
        ('TRANSFER_IN', 'Transfer from Another School'),
        ('REPEATER', 'Repeating Class'),
        ('READMISSION', 'Readmitted Student'),
        ('PROMOTED', 'Promoted from Previous Level'),
        ('TRANSFERRED', 'Transferred Between Classes'),
        ('REPEATED', 'Repeated Current Level'),
        ('INTERNAL_TRANSFER', 'Internal Class Transfer'),
    ]
    
    COMPLETION_STATUS_CHOICES = [
        ('ONGOING', 'Ongoing'),
        ('COMPLETED', 'Completed'),
        ('DROPPED', 'Dropped Out'),
        ('TRANSFERRED', 'Transferred'),
        ('SUSPENDED', 'Suspended'),
        ('WITHDRAWN', 'Withdrawn'),
    ]
    
    PROGRESSION_TYPE_CHOICES = [
        ('NORMAL', 'Normal Progression'),
        ('SKIP', 'Level Skipped'),
        ('REPEAT', 'Level Repeated'),
        ('LATERAL', 'Lateral Transfer'),
        ('READMISSION', 'Readmission'),
    ]

    # -------------------------------------------------------------------------
    # FOREIGN KEY RELATIONSHIPS
    # -------------------------------------------------------------------------

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

    # =========================================================================
    # FINANCIAL INTEGRATION - LINK TO INVOICE
    # =========================================================================
    
    academic_invoice = models.OneToOneField(
        'fees.FeeInvoice',
        verbose_name="Academic Fees Invoice",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='class_enrollment',
        help_text="Invoice generated for this class enrollment"
    )
    
    auto_create_invoice = models.BooleanField(
        "Auto-Create Invoice",
        default=True,
        help_text="Automatically create invoice when enrollment is finalized"
    )
    
    # -------------------------------------------------------------------------
    # ENROLLMENT DETAILS
    # -------------------------------------------------------------------------

    enrollment_date = models.DateField("Enrollment Date")
    roll_number = models.CharField("Roll Number", max_length=20, blank=True)
    
    # -------------------------------------------------------------------------
    # STATUS TRACKING
    # -------------------------------------------------------------------------

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
        null=True,
        blank=True,
        help_text="Previous class enrollment before promotion/transfer"
    )
    
    # -------------------------------------------------------------------------
    # COMPLETION TRACKING
    # -------------------------------------------------------------------------

    completion_date = models.DateField("Completion Date", null=True, blank=True)
    completion_status = models.CharField(
        "Completion Status",
        max_length=20,
        choices=COMPLETION_STATUS_CHOICES,
        default='ONGOING'
    )
    
    enrollment_notes = models.TextField(
        "Enrollment Notes", 
        blank=True,
        help_text="Additional notes about this enrollment"
    )
    
    progression_type = models.CharField(
        "Progression Type",
        max_length=20,
        choices=PROGRESSION_TYPE_CHOICES,
        default='NORMAL',
        help_text="Type of academic progression this enrollment represents"
    )
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------

    # Add the custom manager
    objects = SchoolManager()

    def __str__(self):
        return f"{self.student} - {self.class_instance} ({self.academic_session})"
    
    # -------------------------------------------------------------------------
    # SAVE METHOD
    # -------------------------------------------------------------------------

    def save(self, *args, **kwargs):
        """Save with default values"""
        
        # Set default enrollment date
        if not self.enrollment_date:
            self.enrollment_date = timezone.now().date()
        
        super().save(*args, **kwargs)
    
    # -------------------------------------------------------------------------
    # VALIDATION METHODS
    # -------------------------------------------------------------------------

    def clean(self):
        """Enhanced validation with comprehensive duplicate prevention"""
        super().clean()
        
        # Validate enrollment date vs completion date
        if self.enrollment_date and self.completion_date:
            if self.enrollment_date > self.completion_date:
                raise ValidationError("Enrollment date cannot be after completion date")
        
        # Validate academic session dates
        if self.enrollment_date and self.academic_session:
            if (self.enrollment_date < self.academic_session.start_date or 
                self.enrollment_date > self.academic_session.end_date):
                raise ValidationError(
                    "Enrollment date must be within the academic session period"
                )
        
        # Validate roll number uniqueness if provided
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
        
        # Prevent duplicate enrollments
        self._validate_no_duplicate_enrollment()

    def _validate_no_duplicate_enrollment(self):
        """Comprehensive validation to prevent duplicate enrollments"""
        if not self.student or not self.class_instance or not self.academic_session:
            return
        
        # Check for exact duplicate
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
        
        # Check for active enrollment in ANY class for the same session
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

    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------

    class Meta:
        ordering = ['class_instance', 'roll_number', 'student__last_name']
        verbose_name = "Student Class Enrollment"
        verbose_name_plural = "Student Class Enrollments"
        
        constraints = [
            # Ensure only one active enrollment per student per session
            models.UniqueConstraint(
                fields=['student', 'academic_session'],
                condition=Q(is_active=True, completion_status='ONGOING'),
                name='unique_active_enrollment_per_session'
            ),
            # Prevent exact duplicates
            models.UniqueConstraint(
                fields=['student', 'class_instance', 'academic_session'],
                name='unique_student_class_session'
            ),
            # Ensure unique roll numbers within class/session
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
        null=True,
        blank=True
    )
    
    # Teaching details
    is_optional = models.BooleanField("Is Optional", default=False)
    hours_per_week = models.PositiveIntegerField("Hours Per Week", default=3)
    total_hours = models.PositiveIntegerField("Total Hours", default=0)
    
    # Schedule information
    schedule_days = models.JSONField(
        "Schedule Days",
        blank=True,
        null=True,
        help_text="Days of the week when this subject is taught"
    )
    
    preferred_periods = models.JSONField(
        "Preferred Periods",
        blank=True,
        null=True,
        help_text="Preferred time periods for this subject"
    )
    
    # Academic content
    syllabus = models.TextField("Syllabus", blank=True)
    learning_objectives = models.TextField("Learning Objectives", blank=True)
    assessment_criteria = models.TextField("Assessment Criteria", blank=True)
    
    # Grading configuration
    continuous_assessment_weight = models.DecimalField(
        "Continuous Assessment Weight",
        max_digits=5,
        decimal_places=2,
        default=40.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Percentage weight of continuous assessment"
    )
    
    final_exam_weight = models.DecimalField(
        "Final Exam Weight",
        max_digits=5,
        decimal_places=2,
        default=60.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Percentage weight of final examination"
    )
    
    # Resources
    textbook = models.CharField("Textbook", max_length=200, blank=True)
    reference_materials = models.TextField("Reference Materials", blank=True)
    required_equipment = models.TextField("Required Equipment", blank=True)
    
    # Performance tracking
    class_average = models.DecimalField(
        "Class Average",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Current class average for this subject"
    )
    
    pass_rate = models.DecimalField(
        "Pass Rate",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Percentage of students passing this subject"
    )
    
    # Status
    is_active = models.BooleanField("Is Active", default=True)

    # -------------------------------------------------------------------------
    # VALIDATION METHODS
    # -------------------------------------------------------------------------

    # Add the custom manager
    objects = SchoolManager()

    def __str__(self):
        return f"{self.subject.name} for {self.class_instance}"
    
    def clean(self):
        """Validate class subject configuration"""
        super().clean()
        
        # Validate assessment weights
        if (self.continuous_assessment_weight + self.final_exam_weight) != 100:
            raise ValidationError(
                "Continuous assessment and final exam weights must total 100%"
            )
        
        # Check if subject is applicable to the academic level
        if not self.subject.can_be_taken_by_level(self.class_instance.academic_level):
            raise ValidationError(
                "This subject is not applicable to the selected academic level"
            )
    
    # -------------------------------------------------------------------------
    # HELPER METHODS
    # -------------------------------------------------------------------------

    def get_assessment_breakdown(self):
        """Get assessment weight breakdown"""
        return {
            'continuous_assessment': self.continuous_assessment_weight,
            'final_exam': self.final_exam_weight,
            'total': self.continuous_assessment_weight + self.final_exam_weight
        }
    
    def get_schedule_display(self):
        """Get formatted schedule display"""
        if self.schedule_days:
            days = ", ".join(self.schedule_days)
            return f"{days} ({self.hours_per_week}h/week)"
        return f"{self.hours_per_week} hours per week"
    
    def is_compulsory_for_level(self):
        """Check if subject is compulsory for this academic level"""
        return self.subject.is_compulsory and not self.is_optional

    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------

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
    
    # -------------------------------------------------------------------------
    # CHOICE FIELDS
    # -------------------------------------------------------------------------
    
    PROGRESS_STATUS_CHOICES = [
        ('EXCELLENT', 'Excellent'),
        ('GOOD', 'Good'),
        ('SATISFACTORY', 'Satisfactory'),
        ('NEEDS_IMPROVEMENT', 'Needs Improvement'),
        ('POOR', 'Poor'),
    ]
    
    PROMOTION_DECISION_CHOICES = [
        ('PROMOTED', 'Promoted'),
        ('REPEAT', 'Repeat Class'),
        ('CONDITIONAL', 'Conditional Promotion'),
        ('PENDING', 'Decision Pending'),
        ('TRANSFERRED', 'Transferred Out'),
        ('WITHDRAWN', 'Withdrawn'),
    ]
    
    # -------------------------------------------------------------------------
    # CORE RELATIONSHIPS
    # -------------------------------------------------------------------------
    
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
    
    # -------------------------------------------------------------------------
    # OVERALL PERFORMANCE METRICS
    # -------------------------------------------------------------------------
    
    overall_grade = models.CharField(
        "Overall Grade",
        max_length=5,
        blank=True,
        help_text="Letter grade (A, B+, C, etc.)"
    )
    
    gpa = models.DecimalField(
        "GPA",
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(4)],
        help_text="Grade Point Average (0.00 - 4.00)"
    )
    
    percentage = models.DecimalField(
        "Overall Percentage",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Overall percentage score"
    )
    
    # -------------------------------------------------------------------------
    # ATTENDANCE TRACKING
    # -------------------------------------------------------------------------
    
    total_school_days = models.PositiveIntegerField(
        "Total School Days",
        default=0,
        help_text="Total number of school days in the session"
    )
    
    days_attended = models.PositiveIntegerField(
        "Days Attended",
        default=0,
        help_text="Number of days student was present"
    )
    
    attendance_percentage = models.DecimalField(
        "Attendance Percentage",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    
    # -------------------------------------------------------------------------
    # PROGRESS STATUS
    # -------------------------------------------------------------------------
    
    progress_status = models.CharField(
        "Progress Status",
        max_length=20,
        choices=PROGRESS_STATUS_CHOICES,
        blank=True,
        db_index=True
    )
    
    # -------------------------------------------------------------------------
    # PROMOTION TRACKING
    # -------------------------------------------------------------------------
    
    is_eligible_for_promotion = models.BooleanField(
        "Eligible for Promotion",
        default=False,
        db_index=True
    )
    
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
        null=True,
        blank=True,
        related_name='promoted_students',
        verbose_name="Promoted to Academic Level",
        help_text="Academic level student was promoted to"
    )
    
    promotion_date = models.DateField(
        "Promotion Date",
        null=True,
        blank=True,
        help_text="Date when promotion decision was made"
    )
    
    # -------------------------------------------------------------------------
    # SUBJECT PERFORMANCE SUMMARY
    # -------------------------------------------------------------------------
    
    total_subjects = models.PositiveIntegerField(
        "Total Subjects",
        default=0,
        help_text="Total number of subjects taken"
    )
    
    subjects_passed = models.PositiveIntegerField(
        "Subjects Passed",
        default=0,
        help_text="Number of subjects passed"
    )
    
    subjects_failed = models.PositiveIntegerField(
        "Subjects Failed",
        default=0,
        help_text="Number of subjects failed"
    )
    
    # -------------------------------------------------------------------------
    # FINALIZATION TRACKING
    # -------------------------------------------------------------------------
    
    is_final = models.BooleanField(
        "Is Final Record",
        default=False,
        db_index=True,
        help_text="Mark this as the final academic record for the session"
    )
    
    final_date = models.DateField(
        "Final Record Date",
        null=True,
        blank=True,
        help_text="Date when this record was finalized"
    )
    
    finalized_by = models.CharField(
        "Finalized By",
        max_length=100,
        blank=True,
        help_text="User who finalized this record"
    )
    
    # -------------------------------------------------------------------------
    # COMMENTS AND FEEDBACK
    # -------------------------------------------------------------------------
    
    teacher_comments = models.TextField(
        "Teacher Comments",
        blank=True,
        help_text="Class teacher's comments on student progress"
    )
    
    head_teacher_comments = models.TextField(
        "Head Teacher Comments",
        blank=True,
        help_text="Head teacher or principal's comments"
    )
    
    parent_comments = models.TextField(
        "Parent Comments",
        blank=True,
        help_text="Parent/guardian feedback (if applicable)"
    )
    
    recommendations = models.TextField(
        "Recommendations",
        blank=True,
        help_text="Recommendations for improvement or next steps"
    )
    
    # -------------------------------------------------------------------------
    # CUSTOM MANAGER
    # -------------------------------------------------------------------------
    
    objects = SchoolManager()
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.student.get_full_name()} - {self.academic_session.name} Progress"
    
    # -------------------------------------------------------------------------
    # PROPERTIES
    # -------------------------------------------------------------------------
    
    @property
    def pass_percentage(self):
        """Get percentage of subjects passed"""
        return self.calculate_pass_percentage()
    
    @property
    def is_passing(self):
        """Check if student is passing overall"""
        return self.subjects_failed == 0 and self.total_subjects > 0
    
    @property
    def performance_level(self):
        """Get performance level based on percentage"""
        if not self.percentage:
            return "Not Graded"
        
        if self.percentage >= 90:
            return "Distinction"
        elif self.percentage >= 80:
            return "Excellence"
        elif self.percentage >= 70:
            return "Very Good"
        elif self.percentage >= 60:
            return "Good"
        elif self.percentage >= 50:
            return "Satisfactory"
        else:
            return "Needs Improvement"
    
    # -------------------------------------------------------------------------
    # CALCULATION METHODS
    # -------------------------------------------------------------------------
    
    def calculate_attendance_percentage(self):
        """Calculate and update attendance percentage"""
        if self.total_school_days > 0:
            percentage = (self.days_attended / self.total_school_days) * 100
            self.attendance_percentage = round(percentage, 2)
            return self.attendance_percentage
        return 0
    
    def calculate_pass_percentage(self):
        """Calculate percentage of subjects passed"""
        if self.total_subjects > 0:
            return round((self.subjects_passed / self.total_subjects) * 100, 2)
        return 0
    
    def update_subject_counts(self):
        """
        Update subject pass/fail counts from individual assessments.
        This should be called after grades are entered.
        """
        # This would typically aggregate from Assessment/Grade models
        # Implementation depends on your grading system
        pass
    
    def determine_promotion_eligibility(self):
        """
        Determine if student is eligible for promotion based on:
        - Minimum attendance requirement
        - Subjects passed
        - Overall performance
        """
        # Get minimum requirements from session or configuration
        min_attendance = self.academic_session.minimum_attendance_percentage
        
        # Check attendance
        meets_attendance = (
            self.attendance_percentage and
            self.attendance_percentage >= min_attendance
        )
        
        # Check if passed all required subjects
        passed_all_subjects = self.subjects_failed == 0
        
        # Determine eligibility
        self.is_eligible_for_promotion = meets_attendance and passed_all_subjects
        
        return self.is_eligible_for_promotion
    
    def finalize_record(self, user=None):
        """
        Finalize this academic progress record.
        After finalization, no changes should be made.
        """
        if self.is_final:
            logger.warning(f"Progress record {self.pk} is already finalized")
            return False
        
        self.is_final = True
        self.final_date = timezone.now().date()
        
        if user:
            self.finalized_by = str(user.get_full_name() if hasattr(user, 'get_full_name') else user)
        
        # Determine promotion eligibility
        self.determine_promotion_eligibility()
        
        self.save()
        
        logger.info(f"Finalized progress record for {self.student} - {self.academic_session}")
        return True
    
    # -------------------------------------------------------------------------
    # VALIDATION
    # -------------------------------------------------------------------------
    
    def clean(self):
        """Validate academic progress data"""
        super().clean()
        errors = {}
        
        # Validate attendance
        if self.days_attended > self.total_school_days:
            errors['days_attended'] = "Days attended cannot exceed total school days"
        
        # Validate subject counts
        if self.subjects_passed + self.subjects_failed > self.total_subjects:
            errors['total_subjects'] = "Sum of passed and failed subjects cannot exceed total subjects"
        
        # Validate GPA range
        if self.gpa and not (0 <= self.gpa <= 4):
            errors['gpa'] = "GPA must be between 0.00 and 4.00"
        
        # Validate percentage
        if self.percentage and not (0 <= self.percentage <= 100):
            errors['percentage'] = "Percentage must be between 0 and 100"
        
        # Ensure session and enrollment match
        if self.class_enrollment and self.academic_session:
            if self.class_enrollment.academic_session != self.academic_session:
                errors['class_enrollment'] = "Class enrollment must be for the same academic session"
        
        if self.class_enrollment and self.student:
            if self.class_enrollment.student != self.student:
                errors['class_enrollment'] = "Class enrollment must be for the same student"
        
        if errors:
            raise ValidationError(errors)
    
    def save(self, *args, **kwargs):
        """Auto-calculate fields before saving"""
        # Calculate attendance percentage
        if self.total_school_days > 0:
            self.calculate_attendance_percentage()
        
        # Validate
        self.full_clean()
        
        super().save(*args, **kwargs)
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
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