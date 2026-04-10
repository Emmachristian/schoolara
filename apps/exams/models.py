# exams/models.py

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import Sum, Count, Avg, Q, Max, Min
from decimal import Decimal
import logging

# Import related models from other apps
from utils.models import BaseModel
from academics.models import Class, Subject, AcademicLevel, ClassSubject, AcademicSession, ClassRoom
from students.models import Student
from django.contrib.auth.models import User

logger = logging.getLogger(__name__)


# =============================================================================
# SHARED CONSTANTS
# =============================================================================

CURRICULUM_TYPES = [
    ('ALL', 'All Curricula'),
    ('NATIONAL', 'National Curriculum'),
    ('INTERNATIONAL', 'International Curriculum'),
    ('CAMBRIDGE', 'Cambridge Curriculum'),
    ('IB', 'International Baccalaureate'),
    ('MONTESSORI', 'Montessori'),
    ('WALDORF', 'Waldorf/Steiner'),
    ('CUSTOM', 'Custom Curriculum'),
]


# =============================================================================
# EXAMINATION CATEGORY MODELS
# =============================================================================

class ExamCategory(BaseModel):
    """Model for different types of examinations"""
    
    CATEGORY_TYPES = [
        ('FORMATIVE', 'Formative Assessment'),
        ('SUMMATIVE', 'Summative Assessment'),
        ('DIAGNOSTIC', 'Diagnostic Assessment'),
        ('BENCHMARK', 'Benchmark Assessment'),
        ('STANDARDIZED', 'Standardized Test'),
        ('INTERNAL', 'Internal Examination'),
        ('EXTERNAL', 'External Examination'),
        ('MOCK', 'Mock Examination'),
        ('CONTINUOUS', 'Continuous Assessment'),
        ('FINAL', 'Final Examination'),
    ]
    
    FREQUENCY_CHOICES = [
        ('DAILY', 'Daily'),
        ('WEEKLY', 'Weekly'),
        ('MONTHLY', 'Monthly'),
        ('TERMLY', 'Per Term'),
        ('YEARLY', 'Yearly'),
        ('AS_NEEDED', 'As Needed'),
    ]
    
    # Basic Information
    name = models.CharField("Category Name", max_length=100)
    abbreviation = models.CharField("Abbreviation", max_length=20, unique=True)
    code = models.CharField("Category Code", max_length=20, unique=True)
    description = models.TextField("Description", blank=True)
    
    category_type = models.CharField(
        "Category Type",
        max_length=20,
        choices=CATEGORY_TYPES,
        default='INTERNAL'
    )
    
    # Academic Configuration
    applicable_levels = models.ManyToManyField(
        AcademicLevel,
        verbose_name="Applicable Academic Levels",
        blank=True,
        related_name='exam_categories'
    )
    
    # Subject Type Specific Settings
    applicable_subject_types = models.JSONField(
        "Applicable Subject Types",
        default=list,
        blank=True,
        help_text="Subject types this category applies to (empty = all types)"
    )
    
    # Curriculum Compatibility
    curriculum_compatibility = models.CharField(
        "Curriculum Compatibility",
        max_length=20,
        choices=CURRICULUM_TYPES,
        default='ALL'
    )
    
    frequency = models.CharField(
        "Frequency",
        max_length=15,
        choices=FREQUENCY_CHOICES,
        default='TERMLY'
    )
    
    weight_percentage = models.DecimalField(
        "Weight Percentage",
        max_digits=5,
        decimal_places=2,
        default=Decimal('100.00'),
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))],
        help_text="Percentage contribution to overall grade"
    )
    
    # Financial Requirements
    required_payment_percentage = models.PositiveIntegerField(
        "Required Payment Percentage",
        default=50,
        validators=[MaxValueValidator(100)],
        help_text="Minimum percentage of fees that must be paid to participate"
    )
    
    consider_all_outstanding_balances = models.BooleanField(
        "Consider All Outstanding Balances",
        default=False,
        help_text="If True, all outstanding balances are considered. If False, only current term balance."
    )
    
    # Examination Settings
    allows_retakes = models.BooleanField("Allows Retakes", default=True)
    max_retakes = models.PositiveIntegerField(
        "Maximum Retakes",
        default=2,
        validators=[MinValueValidator(0), MaxValueValidator(10)]
    )
    
    # Reporting Settings
    includes_in_report_cards = models.BooleanField("Include in Report Cards", default=True)
    public_results = models.BooleanField("Public Results", default=False)
    results_publication_days = models.PositiveIntegerField(
        "Results Publication (Days After Exam)",
        default=14,
        help_text="Days after exam completion when results are published"
    )
    
    # Status and Validity
    is_active = models.BooleanField("Is Active", default=True)
    effective_date = models.DateField("Effective Date", default=timezone.now)
    
    valid_sessions = models.ManyToManyField(
        AcademicSession,
        verbose_name="Valid Academic Sessions",
        blank=True,
        help_text="Sessions in which this category is available"
    )

    class Meta:
        verbose_name = "Exam Category"
        verbose_name_plural = "Exam Categories"
        ordering = ['name']
        indexes = [
            models.Index(fields=['category_type']),
            models.Index(fields=['is_active']),
            models.Index(fields=['frequency']),
            models.Index(fields=['curriculum_compatibility']),
        ]

    def __str__(self):
        return f"{self.name} ({self.abbreviation})"

    def save(self, *args, **kwargs):
        """Enhanced save with auto-generation of code"""
        if not self.code:
            self.code = self.abbreviation.upper()
        super().save(*args, **kwargs)

    def is_applicable_to_level(self, academic_level):
        """Check if this category applies to a specific academic level"""
        if not self.applicable_levels.exists():
            return True  # If no levels specified, applies to all
        return self.applicable_levels.filter(pk=academic_level.pk).exists()

    def is_applicable_to_subject_type(self, subject_type):
        """Check if this category applies to a specific subject type"""
        if not self.applicable_subject_types:
            return True  # If no types specified, applies to all
        return subject_type in self.applicable_subject_types

    def is_compatible_with_curriculum(self, curriculum_type):
        """Check if category is compatible with curriculum type"""
        return (self.curriculum_compatibility == 'ALL' or 
                self.curriculum_compatibility == curriculum_type)

    def get_payment_requirement_for_student(self, student):
        """Get payment requirement details for a specific student."""
        try:
            from fees.models import StudentAccount, FeeInvoice
            from academics.models import AcademicSession

            account = StudentAccount.objects.filter(student=student).first()

            if self.consider_all_outstanding_balances:
                total_fees = account.get_total_charges()   if account else Decimal('0.00')
                total_paid = account.get_total_payments()  if account else Decimal('0.00')
            else:
                current_session = AcademicSession.get_current_session()
                invoices = FeeInvoice.objects.filter(
                    student=student, academic_session=current_session
                )
                total_fees = invoices.aggregate(t=Sum('total_amount'))['t'] or Decimal('0.00')
                total_paid = invoices.aggregate(p=Sum('paid_amount'))['p']  or Decimal('0.00')

            if total_fees > 0:
                payment_percentage = (total_paid / total_fees) * 100
                meets_requirement  = payment_percentage >= self.required_payment_percentage
            else:
                payment_percentage = 100
                meets_requirement  = True

            return {
                'total_fees':           total_fees,
                'total_paid':           total_paid,
                'payment_percentage':   payment_percentage,
                'required_percentage':  self.required_payment_percentage,
                'meets_requirement':    meets_requirement,
                'outstanding_amount':   total_fees - total_paid,
            }

        except Exception as e:
            logger.error(f"Error calculating payment requirement: {e}")
            return {'meets_requirement': True, 'error': str(e)}


# =============================================================================
# GRADING SYSTEM MODELS
# =============================================================================

class GradingSystem(BaseModel):
    """Model for grading systems with comprehensive configuration"""
    
    GRADING_TYPES = [
        ('LETTER', 'Letter Grades (A, B, C, D, F)'),
        ('NUMERICAL', 'Numerical Scores (0-100)'),
        ('PERCENTAGE', 'Percentage (0-100%)'),
        ('POINTS', 'Points System (GPA)'),
        ('PASS_FAIL', 'Pass/Fail'),
        ('RUBRIC', 'Rubric-Based'),
        ('STANDARDS', 'Standards-Based'),
        ('MIXED', 'Mixed System'),
    ]
    
    SCALE_TYPES = [
        ('4_POINT', '4-Point Scale'),
        ('5_POINT', '5-Point Scale'),
        ('10_POINT', '10-Point Scale'),
        ('20_POINT', '20-Point Scale'),
        ('100_POINT', '100-Point Scale'),
        ('CUSTOM', 'Custom Scale'),
    ]
    
    # Basic Information
    name = models.CharField("Grading System Name", max_length=100, unique=True)
    code = models.CharField("System Code", max_length=20, unique=True)
    description = models.TextField("Description", blank=True)
    
    grading_type = models.CharField(
        "Grading Type",
        max_length=15,
        choices=GRADING_TYPES,
        default='LETTER'
    )
    
    scale_type = models.CharField(
        "Scale Type",
        max_length=15,
        choices=SCALE_TYPES,
        default='100_POINT'
    )
    
    # Score Configuration
    minimum_score = models.DecimalField(
        "Minimum Score",
        max_digits=6,
        decimal_places=2,
        default=Decimal('0.00')
    )
    maximum_score = models.DecimalField(
        "Maximum Score",
        max_digits=6,
        decimal_places=2,
        default=Decimal('100.00')
    )
    pass_mark = models.DecimalField(
        "Pass Mark",
        max_digits=6,
        decimal_places=2,
        default=Decimal('50.00')
    )
    
    # Grading Features
    uses_letter_grades = models.BooleanField("Uses Letter Grades", default=True)
    uses_numerical_scores = models.BooleanField("Uses Numerical Scores", default=True)
    uses_aggregates = models.BooleanField("Uses Aggregates", default=False)
    uses_color_codes = models.BooleanField("Uses Color Codes", default=True)
    uses_gpa = models.BooleanField("Uses GPA Calculation", default=False)
    
    # Subject Requirements
    minimum_subjects_required = models.PositiveIntegerField(
        "Minimum Subjects Required",
        default=1,
        help_text="Minimum number of subjects needed for this grading system"
    )
    
    maximum_subjects_considered = models.PositiveIntegerField(
        "Maximum Subjects Considered",
        null=True,
        blank=True,
        help_text="Maximum number of subjects to consider in calculations (leave blank for no limit)"
    )
    
    # Subject Selection Rules
    SUBJECT_SELECTION_METHODS = [
        ('ALL', 'Use All Subjects'),
        ('BEST', 'Use Best Performing Subjects'),
        ('WORST', 'Use Worst Performing Subjects'),
        ('REQUIRED_PLUS_BEST', 'Required Subjects + Best Optional'),
        ('CORE_PLUS_ELECTIVES', 'Core Subjects + Best Electives'),
        ('CUSTOM', 'Custom Selection Rules'),
    ]
    
    subject_selection_method = models.CharField(
        "Subject Selection Method",
        max_length=20,
        choices=SUBJECT_SELECTION_METHODS,
        default='ALL'
    )
    
    # Mandatory Subjects
    mandatory_subjects = models.ManyToManyField(
        Subject,
        verbose_name="Mandatory Subjects",
        blank=True,
        related_name='mandatory_for_grading_systems',
        help_text="Subjects that must be included in calculations"
    )
    
    # Optional Subjects Pool
    optional_subjects = models.ManyToManyField(
        Subject,
        verbose_name="Optional Subjects Pool",
        blank=True,
        related_name='optional_for_grading_systems',
        help_text="Pool of subjects to choose from for optional slots"
    )
    
    # Weighting Rules
    uses_subject_weighting = models.BooleanField(
        "Uses Subject Weighting",
        default=False,
        help_text="Whether different subjects have different weights"
    )
    
    # Aggregate Calculation Rules
    aggregate_calculation_method = models.CharField(
        "Aggregate Calculation Method",
        max_length=20,
        choices=[
            ('SUM', 'Sum of Grades'),
            ('AVERAGE', 'Average of Grades'),
            ('WEIGHTED_AVERAGE', 'Weighted Average'),
            ('BEST_N', 'Best N Subjects'),
            ('POINTS_TOTAL', 'Total Points'),
        ],
        default='AVERAGE'
    )
    
    # Failure Conditions
    maximum_failures_allowed = models.PositiveIntegerField(
        "Maximum Failures Allowed",
        null=True,
        blank=True,
        help_text="Maximum number of failed subjects allowed for overall pass"
    )
    
    # Special Requirements
    requires_mathematics = models.BooleanField("Requires Mathematics", default=False)
    requires_english = models.BooleanField("Requires English", default=False)
    requires_science = models.BooleanField("Requires at least one Science", default=False)
    
    # Calculation Settings
    include_positions = models.BooleanField("Include Class Positions", default=True)
    calculate_average = models.BooleanField("Calculate Class Average", default=True)
    calculate_totals = models.BooleanField("Calculate Subject Totals", default=True)
    
    # Rounding and Precision
    round_to_nearest = models.DecimalField(
        "Round to Nearest",
        max_digits=3,
        decimal_places=2,
        default=Decimal('0.01'),
        help_text="Round scores to nearest value (e.g., 0.5 for half points)"
    )
    
    # Display Settings
    display_format = models.CharField(
        "Display Format",
        max_length=50,
        default="{grade} ({score})",
        help_text="Format for displaying grades. Use {grade}, {score}, {percentage}"
    )
    
    # Academic Applicability
    applicable_levels = models.ManyToManyField(
        AcademicLevel,
        verbose_name="Applicable Academic Levels",
        blank=True,
        help_text="Levels this grading system applies to"
    )
    
    applicable_subjects = models.ManyToManyField(
        Subject,
        verbose_name="Applicable Subjects",
        blank=True,
        help_text="Subjects this grading system applies to"
    )
    
    # Curriculum Compatibility
    curriculum_compatibility = models.CharField(
        "Curriculum Compatibility",
        max_length=20,
        choices=CURRICULUM_TYPES,
        default='ALL',
        help_text="Which curriculum types this grading system supports"
    )
    
    # Subject Type Specific Grading
    subject_type_specific = models.BooleanField(
        "Subject Type Specific",
        default=False,
        help_text="Whether this grading system is specific to certain subject types"
    )
    
    applicable_subject_types = models.JSONField(
        "Applicable Subject Types",
        default=list,
        blank=True,
        help_text="Subject types this grading system applies to (if subject_type_specific is True)"
    )
    
    # Status and Dates
    is_active = models.BooleanField("Is Active", default=True)
    is_default = models.BooleanField("Is Default System", default=False)
    effective_date = models.DateField("Effective Date", default=timezone.now)
    expiry_date = models.DateField("Expiry Date", null=True, blank=True)

    class Meta:
        verbose_name = "Grading System"
        verbose_name_plural = "Grading Systems"
        ordering = ['name']
        indexes = [
            models.Index(fields=['grading_type']),
            models.Index(fields=['is_active']),
            models.Index(fields=['is_default']),
            models.Index(fields=['curriculum_compatibility']),
            models.Index(fields=['subject_type_specific']),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_grading_type_display()})"

    def save(self, *args, **kwargs):
        """Enhanced save with validation"""
        if not self.code:
            self.code = self.name.upper().replace(' ', '_')[:20]
        
        # Ensure only one default system
        if self.is_default:
            GradingSystem.objects.filter(is_default=True).exclude(pk=self.pk).update(is_default=False)
        
        super().save(*args, **kwargs)

    def clean(self):
        """Validate grading system configuration"""
        super().clean()
        
        if self.minimum_score >= self.maximum_score:
            raise ValidationError("Maximum score must be greater than minimum score")
        
        if self.pass_mark < self.minimum_score or self.pass_mark > self.maximum_score:
            raise ValidationError("Pass mark must be between minimum and maximum scores")
        
        if self.expiry_date and self.effective_date:
            if self.expiry_date <= self.effective_date:
                raise ValidationError("Expiry date must be after effective date")

    def is_compatible_with_curriculum(self, curriculum_type):
        """Check if grading system is compatible with curriculum type"""
        return (self.curriculum_compatibility == 'ALL' or 
                self.curriculum_compatibility == curriculum_type)
    
    def is_applicable_to_subject_type(self, subject_type):
        """Check if grading system applies to a specific subject type"""
        if not self.subject_type_specific:
            return True
        return subject_type in self.applicable_subject_types

    def get_grade_for_score(self, score):
        """Get grade information for a given score"""
        try:
            grade_range = self.ranges.filter(
                min_score__lte=score,
                max_score__gte=score
            ).first()
            
            if grade_range:
                return {
                    'grade': grade_range.grade,
                    'aggregate': grade_range.aggregate,
                    'comments': grade_range.comments,
                    'color_code': grade_range.color_code,
                    'gpa_points': grade_range.gpa_points,
                    'is_passing': score >= self.pass_mark
                }
            else:
                # No matching range found
                return {
                    'grade': 'F',
                    'aggregate': '',
                    'comments': 'Score out of range',
                    'color_code': '#FF0000',
                    'gpa_points': 0.0,
                    'is_passing': False
                }
        except Exception as e:
            logger.error(f"Error getting grade for score {score}: {e}")
            return None

    def calculate_gpa(self, scores):
        """Calculate GPA for a list of scores"""
        if not self.uses_gpa or not scores:
            return None
        
        try:
            total_points = 0
            total_subjects = 0
            
            for score in scores:
                grade_info = self.get_grade_for_score(score)
                if grade_info and grade_info['gpa_points'] is not None:
                    total_points += grade_info['gpa_points']
                    total_subjects += 1
            
            return round(total_points / total_subjects, 2) if total_subjects > 0 else 0.0
        except Exception as e:
            logger.error(f"Error calculating GPA: {e}")
            return None

    def is_applicable_to_level(self, academic_level):
        """Check if this system applies to a specific academic level"""
        if not self.applicable_levels.exists():
            return True
        return self.applicable_levels.filter(pk=academic_level.pk).exists()

    def is_applicable_to_subject(self, subject):
        """Check if this system applies to a specific subject"""
        if not self.applicable_subjects.exists():
            return True
        return self.applicable_subjects.filter(pk=subject.pk).exists()


class GradingRange(BaseModel):
    """Model for grading ranges with comprehensive grade definitions"""
    
    grading_system = models.ForeignKey(
        GradingSystem,
        on_delete=models.CASCADE,
        related_name='ranges'
    )
    
    # Grade Identification
    grade = models.CharField("Grade", max_length=10)  # A, B, C, D, F, etc.
    grade_name = models.CharField("Grade Name", max_length=50, blank=True)  # Excellent, Good, etc.
    
    # Score Range
    min_score = models.DecimalField(
        "Minimum Score",
        max_digits=6,
        decimal_places=2
    )
    max_score = models.DecimalField(
        "Maximum Score",
        max_digits=6,
        decimal_places=2
    )
    
    # Additional Information
    aggregate = models.CharField(
        "Aggregate",
        max_length=10,
        blank=True,
        help_text="Aggregate classification (e.g., D1, D2, C6)"
    )
    
    # GPA and Points
    gpa_points = models.DecimalField(
        "GPA Points",
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Grade points for GPA calculation"
    )
    
    quality_points = models.DecimalField(
        "Quality Points",
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True
    )
    
    # Display Configuration
    color_code = models.CharField(
        "Color Code",
        max_length=7,
        blank=True,
        help_text="Hex color code for display (e.g., #FF0000)"
    )
    
    text_color = models.CharField(
        "Text Color",
        max_length=7,
        default='#FFFFFF',
        help_text="Text color for display on colored background"
    )
    
    # Comments and Descriptions
    comments = models.TextField("Grade Comments", blank=True)
    description = models.TextField("Grade Description", blank=True)
    
    # Performance Level
    PERFORMANCE_LEVELS = [
        ('EXCEPTIONAL', 'Exceptional'),
        ('PROFICIENT', 'Proficient'),
        ('DEVELOPING', 'Developing'),
        ('EMERGING', 'Emerging'),
        ('INADEQUATE', 'Inadequate'),
    ]
    
    performance_level = models.CharField(
        "Performance Level",
        max_length=15,
        choices=PERFORMANCE_LEVELS,
        blank=True
    )
    
    # Status
    is_passing_grade = models.BooleanField("Is Passing Grade", default=True)
    display_order = models.PositiveIntegerField("Display Order", default=0)

    class Meta:
        verbose_name = "Grading Range"
        verbose_name_plural = "Grading Ranges"
        unique_together = [
            ('grading_system', 'grade'),
            ('grading_system', 'min_score', 'max_score')
        ]
        ordering = ['-min_score']  # Order by descending min_score for efficient lookups
        indexes = [
            models.Index(fields=['grading_system', 'min_score', 'max_score']),
            models.Index(fields=['is_passing_grade']),
        ]

    def __str__(self):
        return f"{self.grade} ({self.min_score}-{self.max_score})"

    def clean(self):
        """Validate grading range"""
        super().clean()
        
        if self.min_score >= self.max_score:
            raise ValidationError("Maximum score must be greater than minimum score")
        
        # Check for overlapping ranges within the same grading system
        overlapping = GradingRange.objects.filter(
            grading_system=self.grading_system
        ).exclude(pk=self.pk if self.pk else None)
        
        for range_obj in overlapping:
            if (self.min_score <= range_obj.max_score and 
                self.max_score >= range_obj.min_score):
                raise ValidationError(
                    f"Score range overlaps with existing range: {range_obj.grade} "
                    f"({range_obj.min_score}-{range_obj.max_score})"
                )

    def contains_score(self, score):
        """Check if this range contains the given score"""
        return self.min_score <= score <= self.max_score

    def get_formatted_display(self):
        """Get formatted display string for this grade"""
        if self.grade_name:
            return f"{self.grade} - {self.grade_name}"
        return self.grade


# =============================================================================
# CLASS GRADING SYSTEM ASSIGNMENT
# =============================================================================

class ClassGradingSystem(BaseModel):
    """Model for assigning grading systems to classes for specific sessions"""

    class_instance = models.ForeignKey(
        Class,
        on_delete=models.CASCADE,
        related_name='grading_systems'
    )
    grading_system = models.ForeignKey(
        GradingSystem,
        on_delete=models.CASCADE,
        related_name='class_assignments'
    )
    academic_session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name='class_grading_systems'
    )

    # Subject-specific assignments
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='class_grading_assignments',
        help_text="Leave blank for class-wide assignment"
    )

    # Assignment Details
    effective_date = models.DateField("Effective Date", default=timezone.now)
    end_date = models.DateField("End Date", null=True, blank=True)

    # Priority and Status
    priority = models.PositiveIntegerField(
        "Priority",
        default=100,
        help_text="Lower number = higher priority"
    )

    is_active = models.BooleanField("Is Active", default=True)
    is_default_for_class = models.BooleanField("Is Default for Class", default=False)

    # Assignment Context
    assigned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='grading_system_assignments'
    )
    assignment_reason = models.TextField("Assignment Reason", blank=True)

    # Override Settings
    custom_pass_mark = models.DecimalField(
        "Custom Pass Mark",
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Override system pass mark for this class"
    )

    custom_maximum_score = models.DecimalField(
        "Custom Maximum Score",
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Override system maximum score for this class"
    )

    # Curriculum Specific Overrides
    curriculum_override = models.CharField(
        "Curriculum Override",
        max_length=20,
        blank=True,
        help_text="Override curriculum type for this assignment"
    )

    # Subject Type Specific Settings
    subject_type_overrides = models.JSONField(
        "Subject Type Overrides",
        default=dict,
        blank=True,
        help_text="Specific settings for different subject types"
    )

    # Reporting Preferences
    include_in_report_cards = models.BooleanField("Include in Report Cards", default=True)
    show_grade_breakdown = models.BooleanField("Show Grade Breakdown", default=True)

    class Meta:
        verbose_name = "Class Grading System"
        verbose_name_plural = "Class Grading Systems"
        unique_together = [
            ('class_instance', 'academic_session', 'subject', 'grading_system', 'effective_date')
        ]
        ordering = ['class_instance', 'academic_session', 'subject', 'priority']
        indexes = [
            models.Index(fields=['class_instance', 'academic_session', 'is_active']),
            models.Index(fields=['grading_system', 'is_active']),
            models.Index(fields=['effective_date', 'end_date']),
            models.Index(fields=['priority']),
        ]

    def __str__(self):
        subject_part = f" - {self.subject.name}" if self.subject else ""
        return f"{self.class_instance}{subject_part} -> {self.grading_system.name} ({self.academic_session})"

    def clean(self):
        """Validate class grading system assignment"""
        super().clean()

        # Validate date range
        if self.end_date and self.end_date <= self.effective_date:
            raise ValidationError("End date must be after effective date")

        # Validate session overlap
        if self.academic_session:
            session_start = self.academic_session.start_date
            session_end = self.academic_session.end_date

            if self.effective_date < session_start:
                raise ValidationError("Effective date cannot be before session start")

            if self.end_date and self.end_date > session_end:
                raise ValidationError("End date cannot be after session end")

    def get_effective_pass_mark(self):
        """Get the effective pass mark (custom or system default)"""
        return self.custom_pass_mark or self.grading_system.pass_mark

    def get_effective_maximum_score(self):
        """Get the effective maximum score (custom or system default)"""
        return self.custom_maximum_score or self.grading_system.maximum_score

    def is_currently_active(self):
        """Check if this assignment is currently active"""
        if not self.is_active:
            return False

        today = timezone.now().date()

        if self.effective_date > today:
            return False

        if self.end_date and self.end_date < today:
            return False

        return True

    @classmethod
    def get_active_grading_system(cls, class_instance, academic_session, subject=None):
        """Get the active grading system for a class, session, and optional subject"""
        try:
            assignment = cls.objects.filter(
                class_instance=class_instance,
                academic_session=academic_session,
                subject=subject,
                is_active=True,
                effective_date__lte=timezone.now().date()
            ).filter(
                Q(end_date__isnull=True) | Q(end_date__gte=timezone.now().date())
            ).order_by('priority', '-effective_date').first()

            if assignment:
                return assignment.grading_system

            # Fallback to class-wide assignment
            if subject:
                return cls.get_active_grading_system(class_instance, academic_session, None)

            # Fallback to default grading system
            return GradingSystem.objects.filter(is_default=True, is_active=True).first()

        except Exception as e:
            logger.error(f"Error getting active grading system: {e}")
            return None


# =============================================================================
# EXAMINATION MODELS
# =============================================================================

class Examination(BaseModel):
    """Model for individual examinations"""
    
    EXAM_STATUS_CHOICES = [
        ('PLANNED', 'Planned'),
        ('SCHEDULED', 'Scheduled'),
        ('ONGOING', 'Ongoing'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
        ('POSTPONED', 'Postponed'),
        ('SUSPENDED', 'Suspended'),
    ]
    
    EXAM_MODES = [
        ('WRITTEN', 'Written Examination'),
        ('ORAL', 'Oral Examination'),
        ('PRACTICAL', 'Practical Examination'),
        ('PROJECT', 'Project Assessment'),
        ('PRESENTATION', 'Presentation'),
        ('PORTFOLIO', 'Portfolio Assessment'),
        ('ONLINE', 'Online Examination'),
        ('MIXED', 'Mixed Mode'),
    ]
    
    # Basic Information
    name = models.CharField("Examination Name", max_length=200)
    code = models.CharField("Examination Code", max_length=50, unique=True)
    description = models.TextField("Description", blank=True)
    
    # Category and Type
    exam_category = models.ForeignKey(
        ExamCategory,
        on_delete=models.PROTECT,
        related_name='examinations'
    )
    
    exam_mode = models.CharField(
        "Examination Mode",
        max_length=15,
        choices=EXAM_MODES,
        default='WRITTEN'
    )
    
    # Academic Context
    academic_session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name='examinations'
    )
    
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='examinations'
    )
    
    # Class and Level Targeting
    target_classes = models.ManyToManyField(
        Class,
        verbose_name="Target Classes",
        related_name='examinations'
    )
    
    # Curriculum Context
    curriculum_type = models.CharField(
        "Curriculum Type",
        max_length=20,
        choices=CURRICULUM_TYPES,
        blank=True,
        help_text="Curriculum context for this examination"
    )
    
    # Subject Type Specific Settings
    subject_type_weight = models.DecimalField(
        "Subject Type Weight",
        max_digits=4,
        decimal_places=2,
        default=Decimal('1.00'),
        help_text="Weight multiplier based on subject type"
    )
    
    # Grading Configuration
    grading_system = models.ForeignKey(
        GradingSystem,
        on_delete=models.PROTECT,
        related_name='examinations',
        null=True,
        blank=True,
        help_text="Leave blank to use class default"
    )
    
    # Examination Timing
    exam_date = models.DateField("Examination Date")
    start_time = models.TimeField("Start Time")
    end_time = models.TimeField("End Time")
    duration_minutes = models.PositiveIntegerField("Duration (Minutes)")
    
    # Scoring and Assessment
    total_marks = models.DecimalField(
        "Total Marks",
        max_digits=6,
        decimal_places=2,
        default=Decimal('100.00')
    )
    
    pass_marks = models.DecimalField(
        "Pass Marks",
        max_digits=6,
        decimal_places=2,
        default=Decimal('50.00')
    )
    
    # Examination Rules
    instructions = models.TextField("Examination Instructions", blank=True)
    materials_allowed = models.TextField("Materials Allowed", blank=True)
    special_requirements = models.TextField("Special Requirements", blank=True)
    
    # Venue and Room Assignment
    examination_venue = models.CharField("Examination Venue", max_length=200, blank=True)
    
    classroom = models.ForeignKey(
        ClassRoom,
        verbose_name="Assigned Classroom",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='examinations'
    )
    
    # Online Exam Settings
    auto_submit = models.BooleanField("Auto Submit", default=False)
    show_results_immediately = models.BooleanField("Show Results Immediately", default=False)
    allow_review = models.BooleanField("Allow Review", default=True)
    
    # Invigilation and Supervision
    invigilators = models.ManyToManyField(
        'hr.Staff',
        verbose_name="Invigilators",
        blank=True,
        related_name='invigilated_exams'
    )
    
    # Status and Processing
    status = models.CharField(
        "Examination Status",
        max_length=15,
        choices=EXAM_STATUS_CHOICES,
        default='PLANNED'
    )
    
    results_published = models.BooleanField("Results Published", default=False)
    results_publication_date = models.DateTimeField("Results Publication Date", null=True, blank=True)
    
    notes = models.TextField("Administrative Notes", blank=True)

    class Meta:
        verbose_name = "Examination"
        verbose_name_plural = "Examinations"
        ordering = ['-exam_date', 'start_time']
        indexes = [
            models.Index(fields=['exam_category', 'academic_session']),
            models.Index(fields=['subject', 'exam_date']),
            models.Index(fields=['status']),
            models.Index(fields=['exam_date', 'start_time']),
            models.Index(fields=['curriculum_type']),
        ]

    def __str__(self):
        return f"{self.name} - {self.subject.name} ({self.exam_date})"

    def clean(self):
        """Validate examination data"""
        super().clean()
        
        # Validate time range
        if self.start_time and self.end_time:
            if self.start_time >= self.end_time:
                raise ValidationError("End time must be after start time")
            
            # Calculate duration from times if not provided
            if not self.duration_minutes:
                from datetime import datetime, timedelta
                start_dt = datetime.combine(self.exam_date, self.start_time)
                end_dt = datetime.combine(self.exam_date, self.end_time)
                duration = end_dt - start_dt
                self.duration_minutes = int(duration.total_seconds() / 60)
        
        # Validate pass marks
        if self.pass_marks > self.total_marks:
            raise ValidationError("Pass marks cannot exceed total marks")
        
        # Validate exam date is not in the past (for new exams)
        if not self.pk and self.exam_date and self.exam_date < timezone.now().date():
            raise ValidationError("Examination date cannot be in the past")

    def get_effective_grading_system(self):
        """Get the effective grading system for this examination"""
        if self.grading_system:
            return self.grading_system
        
        # Try to get from class assignments
        for class_instance in self.target_classes.all():
            grading_system = ClassGradingSystem.get_active_grading_system(
                class_instance, self.academic_session, self.subject
            )
            if grading_system:
                return grading_system
        
        # Fallback to system default
        return GradingSystem.objects.filter(is_default=True, is_active=True).first()

    def get_registered_students(self):
        """Get all students registered for this examination"""
        return Student.objects.filter(
            exam_registrations__examination=self,
            exam_registrations__is_active=True
        ).distinct()

class StudentExamResult(BaseModel):
    """Model for individual student examination results with grade locking"""
    
    RESULT_STATUS_CHOICES = [
        ('NOT_STARTED', 'Not Started'),
        ('IN_PROGRESS', 'In Progress'),
        ('SUBMITTED', 'Submitted'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
        ('DISQUALIFIED', 'Disqualified'),
        ('ABSENT', 'Absent'),
    ]
    
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='exam_results'
    )
    examination = models.ForeignKey(
        Examination,
        on_delete=models.CASCADE,
        related_name='student_results'
    )
    
    # Score and Grading
    score = models.DecimalField(
        "Score",
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True
    )
    
    percentage = models.DecimalField(
        "Percentage",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True
    )
    
    grade = models.CharField("Grade", max_length=10, blank=True)
    grade_points = models.DecimalField(
        "Grade Points",
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True
    )
    
    # Result Status and Timing
    status = models.CharField(
        "Result Status",
        max_length=15,
        choices=RESULT_STATUS_CHOICES,
        default='NOT_STARTED'
    )
    
    start_time = models.DateTimeField("Start Time", null=True, blank=True)
    end_time = models.DateTimeField("End Time", null=True, blank=True)
    submission_time = models.DateTimeField("Submission Time", null=True, blank=True)
    
    # Performance Indicators
    is_pass = models.BooleanField("Is Pass", default=False)
    rank_in_class = models.PositiveIntegerField("Rank in Class", null=True, blank=True)
    rank_in_subject = models.PositiveIntegerField("Rank in Subject", null=True, blank=True)
    
    # Additional Assessment Data
    attempt_number = models.PositiveIntegerField("Attempt Number", default=1)
    time_taken_minutes = models.PositiveIntegerField("Time Taken (Minutes)", null=True, blank=True)
    
    # Detailed Scoring (for objective exams)
    correct_answers = models.PositiveIntegerField("Correct Answers", null=True, blank=True)
    incorrect_answers = models.PositiveIntegerField("Incorrect Answers", null=True, blank=True)
    unanswered = models.PositiveIntegerField("Unanswered", null=True, blank=True)
    
    # Teacher Assessment and Comments
    teacher_comments = models.TextField("Teacher Comments", blank=True)
    examiner_comments = models.TextField("Examiner Comments", blank=True)
    
    # Verification and Moderation
    is_verified = models.BooleanField("Is Verified", default=False)
    verified_by = models.ForeignKey(
        'hr.Staff',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_exam_results'
    )
    verification_date = models.DateTimeField("Verification Date", null=True, blank=True)
    
    # Moderation (for quality assurance)
    is_moderated = models.BooleanField("Is Moderated", default=False)
    moderated_score = models.DecimalField(
        "Moderated Score",
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True
    )
    moderator = models.ForeignKey(
        'hr.Staff',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='moderated_exam_results'
    )
    moderation_notes = models.TextField("Moderation Notes", blank=True)
    
    # Result Publication
    is_published = models.BooleanField("Is Published", default=False)
    publication_date = models.DateTimeField("Publication Date", null=True, blank=True)
    
    # =========================================================================
    # GRADE LOCKING FIELDS
    # =========================================================================
    
    is_grade_locked = models.BooleanField(
        "Grade Locked", 
        default=False,
        help_text="When locked, grade will not change even if grading system is modified"
    )
    
    grade_locked_at = models.DateTimeField(
        "Grade Locked At", 
        null=True, 
        blank=True
    )
    
    grade_locked_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='locked_exam_grades',
        verbose_name="Grade Locked By"
    )
    
    # Historical Grade Data (preserved when locked)
    locked_grade_data = models.JSONField(
        "Locked Grade Data",
        default=dict,
        blank=True,
        help_text="Preserves grade calculation details when locked"
    )
    
    # Auto-lock after publication
    auto_lock_after_publication = models.BooleanField(
        "Auto-lock After Publication",
        default=True,
        help_text="Automatically lock grades when results are published"
    )
    
    # Lock reason for audit trail
    lock_reason = models.CharField(
        "Lock Reason",
        max_length=200,
        blank=True,
        help_text="Reason for locking the grade"
    )

    class Meta:
        verbose_name = "Student Exam Result"
        verbose_name_plural = "Student Exam Results"
        unique_together = ['student', 'examination', 'attempt_number']
        ordering = ['-examination__exam_date', 'examination', '-score']
        indexes = [
            models.Index(fields=['student', 'examination']),
            models.Index(fields=['examination', 'score']),
            models.Index(fields=['status']),
            models.Index(fields=['is_published']),
            models.Index(fields=['rank_in_class']),
            models.Index(fields=['is_grade_locked']),
            models.Index(fields=['grade_locked_at']),
        ]
        permissions = [
            ('lock_grades', 'Can lock exam grades'),
            ('unlock_grades', 'Can unlock exam grades'),
            ('view_locked_grade_history', 'Can view locked grade history'),
        ]

    def __str__(self):
        score_display = f"{self.score}/{self.examination.total_marks}" if self.score is not None else "No Score"
        lock_indicator = " 🔒" if self.is_grade_locked else ""
        return f"{self.student.get_full_name()} - {self.examination.name}: {score_display}{lock_indicator}"

    def save(self, *args, **kwargs):
        """Enhanced save with automatic calculations and grade locking logic"""
        from core.utils import get_school_current_time
        
        # Only recalculate grade if not locked
        if not self.is_grade_locked and self.score is not None and self.examination:
            # Calculate percentage
            if self.examination.total_marks > 0:
                self.percentage = round((self.score / self.examination.total_marks) * 100, 2)
            
            # Determine pass/fail
            self.is_pass = self.score >= self.examination.pass_marks
            
            # Get grade information
            grading_system = self.examination.get_effective_grading_system()
            if grading_system:
                grade_info = grading_system.get_grade_for_score(float(self.score))
                if grade_info:
                    self.grade = grade_info['grade']
                    self.grade_points = grade_info.get('gpa_points')
        
        # Calculate time taken
        if self.start_time and self.end_time:
            duration = self.end_time - self.start_time
            self.time_taken_minutes = int(duration.total_seconds() / 60)
        
        # Set publication date if being published for the first time
        if self.is_published and not self.publication_date:
            self.publication_date = get_school_current_time()
        
        # Check for auto-lock condition BEFORE save (to avoid recursion)
        should_auto_lock = (
            self.is_published and 
            not self.is_grade_locked and 
            self.auto_lock_after_publication and 
            self.grade
        )
        
        # If should auto-lock, set fields directly (no recursion)
        if should_auto_lock:
            grading_system = self.examination.get_effective_grading_system()
            
            self.locked_grade_data = {
                'grade': self.grade,
                'grade_points': float(self.grade_points) if self.grade_points else None,
                'percentage': float(self.percentage) if self.percentage else None,
                'is_pass': self.is_pass,
                'grading_system_id': grading_system.id if grading_system else None,
                'grading_system_name': grading_system.name if grading_system else None,
                'grading_system_code': grading_system.code if grading_system else None,
                'locked_date': get_school_current_time().isoformat(),
                'score_at_lock': float(self.score) if self.score else None,
                'total_marks_at_lock': float(self.examination.total_marks),
                'pass_marks_at_lock': float(self.examination.pass_marks),
                'lock_reason': 'Auto-locked after publication'
            }
            
            self.is_grade_locked = True
            self.grade_locked_at = get_school_current_time()
            self.lock_reason = 'Auto-locked after publication'
            self.set_change_reason('Grade auto-locked after publication')
        
        super().save(*args, **kwargs)

    def lock_grade(self, locked_by=None, reason=None):
        """Lock the current grade to prevent future changes"""
        from core.utils import get_school_current_time
        
        if not self.is_grade_locked and self.grade:
            try:
                # Store current grade data
                grading_system = self.examination.get_effective_grading_system()
                
                self.locked_grade_data = {
                    'grade': self.grade,
                    'grade_points': float(self.grade_points) if self.grade_points else None,
                    'percentage': float(self.percentage) if self.percentage else None,
                    'is_pass': self.is_pass,
                    'grading_system_id': grading_system.id if grading_system else None,
                    'grading_system_name': grading_system.name if grading_system else None,
                    'grading_system_code': grading_system.code if grading_system else None,
                    'locked_date': get_school_current_time().isoformat(),
                    'score_at_lock': float(self.score) if self.score else None,
                    'total_marks_at_lock': float(self.examination.total_marks),
                    'pass_marks_at_lock': float(self.examination.pass_marks),
                    'lock_reason': reason or 'Manual lock'
                }
                
                self.is_grade_locked = True
                self.grade_locked_at = get_school_current_time()
                self.grade_locked_by = locked_by
                self.lock_reason = reason or 'Manual lock'
                
                # Set explicit change reason for audit trail
                self.set_change_reason(f"Grade locked: {reason or 'Manual lock'}")
                
                # Use save with update_fields to trigger BaseModel's audit trail
                self.save(update_fields=[
                    'is_grade_locked', 
                    'grade_locked_at', 
                    'grade_locked_by', 
                    'locked_grade_data', 
                    'lock_reason',
                    'updated_at',
                    'updated_by_id',
                    'updated_from_ip'
                ])
                
                logger.info(f"Grade locked for {self.student} - {self.examination} by {locked_by}")
                return True
                
            except Exception as e:
                logger.error(f"Error locking grade for {self.student} - {self.examination}: {e}")
                return False
        
        return False

    def unlock_grade(self, unlocked_by=None, reason=None):
        """Unlock grade to allow recalculation (with permission check)"""
        from core.utils import get_school_current_time
        
        if self.is_grade_locked:
            try:
                # Store unlock information in the locked_grade_data for audit
                if self.locked_grade_data:
                    self.locked_grade_data['unlock_info'] = {
                        'unlocked_by': unlocked_by.get_full_name() if unlocked_by else 'System',
                        'unlocked_at': get_school_current_time().isoformat(),
                        'unlock_reason': reason or 'Manual unlock',
                        'previous_lock_reason': self.lock_reason
                    }
                
                self.is_grade_locked = False
                self.grade_locked_at = None
                self.grade_locked_by = None
                self.lock_reason = ''
                
                # Set explicit change reason for audit trail
                self.set_change_reason(f"Grade unlocked: {reason or 'Manual unlock'}")
                
                # Log the unlock action
                logger.info(f"Grade unlocked for {self.student} - {self.examination} by {unlocked_by}")
                
                # Save to trigger recalculation of grade with current grading system
                self.save()
                return True
                
            except Exception as e:
                logger.error(f"Error unlocking grade for {self.student} - {self.examination}: {e}")
                return False
        
        return False

    def get_grade_history(self):
        """Get comprehensive grade change history"""
        history = {
            'current_status': {
                'grade': self.grade,
                'grade_points': self.grade_points,
                'percentage': self.percentage,
                'is_locked': self.is_grade_locked,
                'last_updated': self.updated_at
            }
        }
        
        if self.locked_grade_data:
            history['locked_data'] = {
                'grade_at_lock': self.locked_grade_data.get('grade'),
                'percentage_at_lock': self.locked_grade_data.get('percentage'),
                'locked_at': self.grade_locked_at,
                'locked_by': self.grade_locked_by.get_full_name() if self.grade_locked_by else None,
                'lock_reason': self.locked_grade_data.get('lock_reason'),
                'grading_system_at_lock': self.locked_grade_data.get('grading_system_name'),
                'score_at_lock': self.locked_grade_data.get('score_at_lock')
            }
            
            # Include unlock information if available
            unlock_info = self.locked_grade_data.get('unlock_info')
            if unlock_info:
                history['unlock_history'] = unlock_info
        
        return history

    def can_unlock_grade(self, user):
        """Check if a user can unlock this grade"""
        if not self.is_grade_locked:
            return False
        
        # Check permissions
        if not user.has_perm('exams.unlock_grades'):
            return False
        
        # Additional business logic checks
        # Example: Don't allow unlocking if result is published for more than 30 days
        if self.publication_date:
            from datetime import timedelta
            from core.utils import get_school_current_time
            if get_school_current_time() - self.publication_date > timedelta(days=30):
                return False
        
        return True

    def get_lock_status_display(self):
        """Get human-readable lock status"""
        if not self.is_grade_locked:
            return "Unlocked"
        
        lock_info = f"Locked on {self.grade_locked_at.strftime('%Y-%m-%d %H:%M')}"
        if self.grade_locked_by:
            lock_info += f" by {self.grade_locked_by.get_full_name()}"
        if self.lock_reason:
            lock_info += f" ({self.lock_reason})"
        
        return lock_info

    def get_formatted_score(self):
        """Get formatted score display with lock indicator"""
        if self.score is not None:
            score_text = f"{self.score}/{self.examination.total_marks}"
            if self.is_grade_locked:
                score_text += " 🔒"
            return score_text
        return "No Score"

    def get_performance_summary(self):
        """Get comprehensive performance summary including lock status"""
        summary = {
            'score': self.score,
            'percentage': self.percentage,
            'grade': self.grade,
            'is_pass': self.is_pass,
            'rank_in_class': self.rank_in_class,
            'time_taken': self.time_taken_minutes,
            'is_grade_locked': self.is_grade_locked,
            'lock_status': self.get_lock_status_display(),
        }
        
        if self.correct_answers is not None:
            total_questions = (self.correct_answers or 0) + (self.incorrect_answers or 0) + (self.unanswered or 0)
            summary.update({
                'correct_answers': self.correct_answers,
                'incorrect_answers': self.incorrect_answers,
                'unanswered': self.unanswered,
                'total_questions': total_questions,
                'accuracy_rate': round((self.correct_answers / total_questions * 100), 2) if total_questions > 0 else 0
            })
        
        return summary

    def clean(self):
        """Validate the model data"""
        super().clean()
        
        # Validation: Cannot lock grade without a grade
        if self.is_grade_locked and not self.grade:
            raise ValidationError("Cannot lock grade when no grade is assigned")
        
        # Validation: Cannot lock grade without a score
        if self.is_grade_locked and self.score is None:
            raise ValidationError("Cannot lock grade when no score is assigned")

    @classmethod
    def get_lockable_results(cls, examination=None, academic_session=None):
        """Get results that can be locked"""
        queryset = cls.objects.filter(
            is_grade_locked=False,
            score__isnull=False,
            grade__isnull=False,
            status__in=['COMPLETED', 'SUBMITTED']
        )
        
        if examination:
            queryset = queryset.filter(examination=examination)
        
        if academic_session:
            queryset = queryset.filter(examination__academic_session=academic_session)
        
        return queryset



    

