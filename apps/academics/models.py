# academics/models.py

from django.db import models
from django.db.models import Q
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from schoolara.managers import SchoolManager
from utils.models import BaseModel, SchoolConfiguration
import re
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# ACADEMIC SESSION MODEL
# =============================================================================

class AcademicSession(BaseModel):
    """
    Enhanced Academic sessions with comprehensive functionality
    """
    # Academic year part
    year_name = models.CharField(
        "Academic Year", 
        max_length=20, 
        help_text="E.g., '2024-2025' or '2024'"
    )
    
    # Term/Period part - adapts to school configuration
    term_number = models.PositiveSmallIntegerField(
        "Period Number", 
        help_text="Position of this period within the year (1, 2, 3, etc.)"
    )
    term_name = models.CharField(
        "Period Name", 
        max_length=50,
        help_text="E.g., 'Fall Semester', 'Term 1', 'Quarter 3', etc."
    )
    
    # Period type tracking (automatically set from school config)
    period_type = models.CharField(
        "Period Type",
        max_length=15,
        choices=[
            ('term', 'Term'),
            ('semester', 'Semester'),
            ('quarter', 'Quarter'),
            ('trimester', 'Trimester'),
            ('module', 'Module'),
            ('block', 'Block'),
            ('yearlong', 'Year-long'),
            ('intensive', 'Intensive'),
            ('custom', 'Custom'),
        ],
        default='term',
        help_text="Type of academic period (automatically set from school configuration)"
    )
    
    # Date range
    start_date = models.DateField("Start Date")
    end_date = models.DateField("End Date")
    
    # Status flags
    is_current = models.BooleanField("Is Current Session", default=False)
    is_active = models.BooleanField("Is Active", default=False)
    allows_promotion = models.BooleanField(
        "Allows Promotion", 
        default=False,
        help_text="Whether students can be promoted at the end of this period"
    )
    promotion_done = models.BooleanField("Promotion Completed", default=False)
    
    # Financial settings for this session
    registration_fee_required = models.BooleanField("Registration Fee Required", default=True)
    late_payment_penalty_rate = models.DecimalField(
        "Late Payment Penalty Rate", 
        max_digits=5, 
        decimal_places=2, 
        default=0.00,
        help_text="Percentage penalty for late payments (e.g., 5.00 for 5%)"
    )
    
    # Enrollment and capacity
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
    
    # Session closure
    is_closed = models.BooleanField("Session Closed", default=False)
    closure_date = models.DateTimeField("Closure Date", null=True, blank=True)
    closed_by_id = models.CharField(
        "Closed By User ID",
        max_length=100,
        null=True,
        blank=True,
        help_text="ID of user who closed this session"
    )

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
        return f"{self.year_name} Academic Year - {self.term_name} ({self.get_period_type_display()})"

    @property
    def status_display(self):
        """Get human-readable status"""
        if self.is_closed:
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
        
        return (self.end_date - self.start_date).days

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
        if not self.enrollment_deadline:
            return True  # No deadline set
        
        current_date = timezone.now().date()
        if current_date <= self.enrollment_deadline:
            return True
        
        return self.late_enrollment_allowed
    
    # Add the custom manager
    objects = SchoolManager()

    def __str__(self):
        return self.name

    # -------------------------------------------------------------------------
    # VALIDATION AND SAVE METHODS
    # -------------------------------------------------------------------------

    def clean(self):
        """Enhanced validation"""
        super().clean()
        errors = {}
        
        # Date validation
        if self.start_date and self.end_date and self.start_date > self.end_date:
            errors['end_date'] = 'End date cannot be before start date'
        
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
        
        # Validate period number against school configuration
        try:
            config = SchoolConfiguration.get_instance()
            if config and not config.validate_period_number(self.term_number):
                errors['term_number'] = f'Period number {self.term_number} is invalid for {config.get_term_system_display()} system (max: {config.get_period_count()})'
        except Exception:
            if self.term_number > 8:
                errors['term_number'] = 'Period number cannot exceed 8'
        
        # Percentage field validation
        if not (0 <= self.late_payment_penalty_rate <= 100):
            errors['late_payment_penalty_rate'] = 'Late payment penalty rate must be between 0 and 100'
        
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """Enhanced save with auto-generation and validation"""
        # Auto-generate period name and type from school configuration
        if not self.term_name or self.period_type == 'term':
            try:
                config = SchoolConfiguration.get_instance()
                if config:
                    self.period_type = config.term_system
                    
                    if not self.term_name:
                        self.term_name = config.get_period_name(self.term_number)
            except Exception:
                if not self.term_name:
                    period_types = {
                        'semester': 'Semester',
                        'quarter': 'Quarter',
                        'trimester': 'Trimester',
                        'module': 'Module',
                        'block': 'Block'
                    }
                    period_name = period_types.get(self.period_type, 'Term')
                    self.term_name = f"{period_name} {self.term_number}"
        
        # Validate before saving
        self.full_clean()
        
        # Ensure only one current session
        if self.is_current:
            AcademicSession.objects.filter(is_current=True).exclude(pk=self.pk).update(is_current=False)
        
        # Track changes for break synchronization
        is_new = self.pk is None
        old_dates = None
        
        if not is_new:
            try:
                old_instance = AcademicSession.objects.get(pk=self.pk)
                old_dates = (old_instance.start_date, old_instance.end_date)
            except AcademicSession.DoesNotExist:
                old_dates = None
        
        super().save(*args, **kwargs)
        
        # Auto-create/update breaks if dates changed
        if is_new or (old_dates and (old_dates[0] != self.start_date or old_dates[1] != self.end_date)):
            from django.db import transaction
            transaction.on_commit(lambda: self._trigger_break_sync())

    def _trigger_break_sync(self):
        """Trigger break synchronization for this session"""
        try:
            config = SchoolConfiguration.get_instance()
            if config and config.auto_create_breaks:
                self.__class__.update_breaks_for_session(self)
        except Exception as e:
            logger.error(f"Error triggering break sync for session {self}: {e}")

    # -------------------------------------------------------------------------
    # INSTANCE HELPER METHODS
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

    def can_enroll_students(self):
        """Check if students can be enrolled in this session"""
        return self.is_enrollment_open and self.is_active and not self.is_closed

    def can_be_closed(self):
        """Check if session can be closed"""
        return not self.is_closed and not self.is_current

    def can_be_made_current(self):
        """Check if this session can be made current"""
        if self.is_closed:
            return False
        
        current_date = timezone.now().date()
        return self.start_date <= current_date <= self.end_date

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

    # -------------------------------------------------------------------------
    # CLASS METHODS FOR SESSION MANAGEMENT
    # -------------------------------------------------------------------------
    
    @classmethod
    def get_current(cls):
        """Returns the current academic session"""
        try:
            return cls.objects.get(is_current=True)
        except cls.DoesNotExist:
            # Fallback: find by current date
            current_date = timezone.now().date()
            return cls.objects.filter(
                start_date__lte=current_date,
                end_date__gte=current_date
            ).first()
        except cls.MultipleObjectsReturned:
            # If multiple marked as current, return most recent
            return cls.objects.filter(is_current=True).order_by('-start_date').first()
    
    @classmethod
    def _generate_break_name_enhanced(cls, previous_session, next_session, break_type='TERM_BREAK'):
        """Generate enhanced break name"""
        if previous_session and next_session:
            return f"Break between {previous_session.term_name} and {next_session.term_name}"
        elif previous_session:
            return f"Break after {previous_session.term_name}"
        elif next_session:
            return f"Break before {next_session.term_name}"
        else:
            return "Academic Break"

    @classmethod
    def get_upcoming_sessions(cls):
        """Get sessions that haven't started yet"""
        current_date = timezone.now().date()
        return cls.objects.filter(start_date__gt=current_date, is_active=True)

    @classmethod
    def get_completed_sessions(cls):
        """Get sessions that have ended"""
        current_date = timezone.now().date()
        return cls.objects.filter(end_date__lt=current_date)

    @classmethod
    def update_breaks_for_session(cls, session):
        """Update breaks for a specific session"""
        # This would be implemented based on your break management system
        pass

    @classmethod
    def _determine_break_type_enhanced(cls, previous_session, next_session, config=None):
        """Determine what type of break this represents between sessions"""
        # If sessions are in different academic years
        if (previous_session and next_session and 
                previous_session.year_name != next_session.year_name):
            return 'YEAR_BREAK'  # Break between academic years
            
        # If previous session is the last of the year
        if previous_session and config:
            try:
                if config.is_last_period(previous_session.term_number):
                    return 'YEAR_END'  # End of academic year break
            except:
                pass
            
        # Regular term break within the same year
        return 'TERM_BREAK'

    @classmethod
    def _generate_break_description(cls, previous_session, next_session, break_type):
        """Generate description for break between sessions"""
        if break_type == 'YEAR_BREAK':
            return f"Break between academic years {previous_session.year_name} and {next_session.year_name}"
        elif break_type == 'YEAR_END':
            return f"End of academic year break after {previous_session.year_name}"
        else:
            return f"Break between {previous_session.term_name} and {next_session.term_name}"

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
            models.Index(fields=['start_date', 'end_date']),
            models.Index(fields=['year_name', 'term_number']),
            models.Index(fields=['allows_promotion', 'promotion_done']),
            models.Index(fields=['period_type']),
            models.Index(fields=['is_closed']),
            models.Index(fields=['enrollment_deadline']),
        ]
        
        constraints = [
            models.CheckConstraint(
                check=Q(start_date__lte=models.F('end_date')),
                name='session_start_before_end'
            ),
            models.CheckConstraint(
                check=Q(late_payment_penalty_rate__gte=0, late_payment_penalty_rate__lte=100),
                name='valid_penalty_rate'
            ),
        ]


# =============================================================================
# HOLIDAY MODEL
# =============================================================================

class Holiday(BaseModel):
    """School holidays and important dates for this school with enhanced break detection"""
    HOLIDAY_TYPES = (
        ('PUBLIC', 'Public Holiday'),
        ('SCHOOL', 'School Event'),
        ('BREAK', 'Term Break'),
    )
    
    BREAK_TYPES = (
        ('TERM_BREAK', 'Break Between Terms'),
        ('YEAR_END', 'End of Academic Year'),
        ('YEAR_BREAK', 'Break Between Years'),
    )
    
    name = models.CharField("Holiday Name", max_length=200)
    holiday_type = models.CharField(
        "Holiday Type", 
        max_length=10, 
        choices=HOLIDAY_TYPES, 
        default='PUBLIC'
    )
    break_type = models.CharField(
        "Break Type", 
        max_length=12,
        choices=BREAK_TYPES, 
        null=True, 
        blank=True,
        help_text="Only applicable for term breaks"
    )
    start_date = models.DateField("Start Date") 
    end_date = models.DateField("End Date", null=True, blank=True)
    description = models.TextField("Description", blank=True, null=True)
    
    # Session associations
    academic_session = models.ForeignKey(
        AcademicSession, 
        on_delete=models.CASCADE, 
        related_name='holidays', 
        verbose_name="Academic Session",
        null=True, blank=True
    )
    
    # For term breaks, reference the sessions before and after
    previous_session = models.ForeignKey(
        AcademicSession,
        on_delete=models.SET_NULL,
        related_name='following_breaks',
        verbose_name="Session Before Break",
        null=True, blank=True,
        help_text="Only applicable for term breaks"
    )
    next_session = models.ForeignKey(
        AcademicSession,
        on_delete=models.SET_NULL,
        related_name='preceding_breaks',
        verbose_name="Session After Break",
        null=True, blank=True,
        help_text="Only applicable for term breaks"
    )

    # -------------------------------------------------------------------------
    # VALIDATION AND SAVE METHODS
    # -------------------------------------------------------------------------

    def clean(self):
        """Enhanced validation"""
        super().clean()
        errors = {}
        
        if self.end_date and self.start_date > self.end_date:
            errors['end_date'] = 'End date cannot be before start date'
            
        # Term break validation
        if self.holiday_type == 'BREAK':
            # Require end date for breaks
            if not self.end_date:
                errors['end_date'] = "Term breaks must have an end date"
                
            # Require at least one session reference
            if not self.previous_session and not self.next_session:
                errors['previous_session'] = "Term breaks must be associated with at least one academic session"
                
            # Validate dates relative to sessions
            if self.previous_session and self.start_date < self.previous_session.end_date:
                errors['start_date'] = "Break cannot start before the previous session ends"
                
            if self.next_session and self.end_date > self.next_session.start_date:
                errors['end_date'] = "Break cannot end after the next session starts"
                
            # Auto-determine break type if not specified
            if not self.break_type:
                self.break_type = self.determine_break_type()
        else:
            # Clear break-specific fields for non-breaks
            self.break_type = None
            self.previous_session = None
            self.next_session = None
        
        if errors:
            raise ValidationError(errors)
    
    def save(self, *args, **kwargs):
        # Auto-determine break type before saving
        if self.holiday_type == 'BREAK' and not self.break_type:
            self.break_type = self.determine_break_type()
            
        super().save(*args, **kwargs)
    
    # -------------------------------------------------------------------------
    # HELPER METHODS
    # -------------------------------------------------------------------------

    def determine_break_type(self):
        """Determine what type of break this represents"""
        # If sessions are in different academic years
        if (self.previous_session and self.next_session and 
                self.previous_session.year_name != self.next_session.year_name):
            return 'YEAR_BREAK'  # Break between academic years
            
        # If previous session is the last of the year
        if self.previous_session:
            try:
                config = SchoolConfiguration.get_instance()
                if config and config.is_last_period(self.previous_session.term_number):
                    return 'YEAR_END'  # End of academic year break
            except:
                pass
            
        # Regular term break within the same year
        return 'TERM_BREAK'
    
    @property
    def duration(self):
        """Get the duration of the holiday in days"""
        if not self.end_date:
            return 1
        delta = self.end_date - self.start_date
        return delta.days + 1  # Include both start and end dates
    
    # Add the custom manager
    objects = SchoolManager()
    
    def __str__(self):
        if self.end_date:
            return f"{self.name} ({self.start_date} to {self.end_date})"
        return f"{self.name} - {self.start_date}"
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------

    class Meta:
        verbose_name = "Holiday"
        verbose_name_plural = "Holidays"
        ordering = ['start_date']
        indexes = [
            models.Index(fields=['start_date', 'end_date']),
            models.Index(fields=['holiday_type']),
            models.Index(fields=['break_type']),
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