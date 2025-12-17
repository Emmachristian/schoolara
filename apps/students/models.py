# students/models.py

from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models import Q
from django.utils import timezone
from schoolara.managers import SchoolManager
from django_countries.fields import CountryField
from utils.models import BaseModel
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# STUDENT MODEL
# =============================================================================

class Student(BaseModel):
    """Enhanced model for comprehensive student information"""
    
    # -------------------------------------------------------------------------
    # CHOICE FIELDS
    # -------------------------------------------------------------------------
    
    GENDER_CHOICES = (
        ('M', 'Male'),
        ('F', 'Female'),
    )
    
    ENROLLMENT_STATUS_CHOICES = (
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('dismissed', 'Dismissed'),
        ('graduated', 'Graduated'),
        ('transferred', 'Transferred'),
        ('withdrawn', 'Withdrawn'),
        ('deceased', 'Deceased'),
        ('deferred', 'Deferred'),
    )
    
    RELIGIOUS_AFFILIATION_CHOICES = (
        ('catholic', 'Catholic'),
        ('protestant', 'Protestant'),
        ('anglican', 'Anglican'),
        ('baptist', 'Baptist'),
        ('pentecostal', 'Pentecostal'),
        ('evangelical', 'Evangelical'),
        ('adventist', 'Adventist'),
        ('islam', 'Islam'),
        ('hindu', 'Hindu'),
        ('buddhist', 'Buddhist'),
        ('jewish', 'Jewish'),
        ('traditional', 'Traditional'),
        ('none', 'No Religion'),
        ('other', 'Other'),
    )
    
    HEALTH_CONDITION_CHOICES = (
        ('excellent', 'Excellent'),
        ('good', 'Good'),
        ('fair', 'Fair'),
        ('poor', 'Poor'),
        ('chronic', 'Chronic Condition'),
        ('recovering', 'Recovering'),
        ('special_Needs', 'Special Needs'),
        ('other', 'Other'),
    )
    
    BLOOD_TYPE_CHOICES = (
        ('A+', 'A+'), ('A-', 'A-'),
        ('B+', 'B+'), ('B-', 'B-'),
        ('AB+', 'AB+'), ('AB-', 'AB-'),
        ('O+', 'O+'), ('O-', 'O-'),
        ('Unknown', 'Unknown'),
    )
    
    # -------------------------------------------------------------------------
    # IDENTIFICATION & BASIC INFORMATION
    # -------------------------------------------------------------------------
    
    admission_number = models.CharField("Admission Number", max_length=20, unique=True, blank=True)
    admission_date = models.DateField("Admission Date")
    national_student_number = models.CharField("National Student Number", max_length=30, unique=True, null=True, blank=True)
    birth_certificate_number = models.CharField("Birth Certificate Number", max_length=50, blank=True)
    first_name = models.CharField("First Name", max_length=50)
    middle_name = models.CharField("Middle Name", max_length=50, blank=True)
    last_name = models.CharField("Last Name", max_length=50)
    date_of_birth = models.DateField("Date of Birth")
    gender = models.CharField("Gender", max_length=1, choices=GENDER_CHOICES)
    
    # -------------------------------------------------------------------------
    # ACADEMIC INFORMATION
    # -------------------------------------------------------------------------
    
    current_academic_level = models.ForeignKey(
        'academics.AcademicLevel', 
        verbose_name="Current Academic Level", 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='current_students'
    )
    admission_academic_level = models.ForeignKey(
        'academics.AcademicLevel', 
        verbose_name="Admission Academic Level", 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='admitted_students'
    )
    
    # -------------------------------------------------------------------------
    # DEMOGRAPHICS & CULTURAL INFORMATION
    # -------------------------------------------------------------------------
    
    nationality = CountryField("Nationality", blank=True, null=True)
    ethnicity = models.CharField("Ethnicity", max_length=50, blank=True)
    birth_place = models.CharField("Place of Birth", max_length=100, blank=True)
    birth_country = CountryField(verbose_name="Country of Birth", blank=True, null=True)
    religious_affiliation = models.CharField("Religious Affiliation", max_length=20, choices=RELIGIOUS_AFFILIATION_CHOICES, blank=True)
    
    # -------------------------------------------------------------------------
    # CONTACT & ADDRESS INFORMATION
    # -------------------------------------------------------------------------
    
    personal_email = models.EmailField("Personal Email", blank=True)
    phone_number = models.CharField("Phone Number", max_length=20, blank=True)
    home_address = models.TextField("Home Address")
    mailing_address = models.TextField("Mailing Address", blank=True)
    district = models.CharField("District", max_length=50, blank=True)
    region = models.CharField("Region/Province", max_length=50, blank=True)
    country_of_residence = CountryField(verbose_name="Country of Residence", blank=True, null=True)
    
    # -------------------------------------------------------------------------
    # HEALTH & MEDICAL INFORMATION
    # -------------------------------------------------------------------------
    
    health_condition = models.CharField("Health Condition", max_length=20, choices=HEALTH_CONDITION_CHOICES, default='Good')
    blood_type = models.CharField("Blood Type", max_length=10, choices=BLOOD_TYPE_CHOICES, default='Unknown')
    medical_conditions = models.TextField("Medical Conditions", blank=True)
    allergies = models.TextField("Allergies", blank=True)
    medications = models.TextField("Current Medications", blank=True)
    special_medical_needs = models.TextField("Special Medical Needs", blank=True)
    emergency_medical_contact = models.CharField("Emergency Medical Contact", max_length=20, blank=True)
    preferred_hospital = models.CharField("Preferred Hospital", max_length=100, blank=True)
    medical_insurance = models.CharField("Medical Insurance", max_length=100, blank=True)
    insurance_policy_number = models.CharField("Insurance Policy Number", max_length=50, blank=True)
    
    # -------------------------------------------------------------------------
    # SPECIAL NEEDS & ACCOMMODATIONS
    # -------------------------------------------------------------------------
    
    has_special_needs = models.BooleanField("Has Special Needs", default=False)
    special_needs_description = models.TextField("Special Needs Description", blank=True)
    requires_special_diet = models.BooleanField("Requires Special Diet", default=False)
    special_diet_details = models.TextField("Special Diet Details", blank=True)
    learning_disabilities = models.TextField("Learning Disabilities", blank=True)
    learning_accommodations = models.TextField("Learning Accommodations", blank=True)
    
    # -------------------------------------------------------------------------
    # TRANSPORT INFORMATION
    # -------------------------------------------------------------------------
    
    transportation_required = models.BooleanField("Transportation Required", default=False)
    transport_route = models.CharField("Transport Route", max_length=50, blank=True)
    pickup_point = models.CharField("Pickup Point", max_length=50, blank=True)
    pickup_time = models.TimeField("Pickup Time", null=True, blank=True)
    
    # -------------------------------------------------------------------------
    # PREVIOUS EDUCATION
    # -------------------------------------------------------------------------
    
    previous_school = models.CharField("Previous School", max_length=100, blank=True)
    previous_school_address = models.TextField("Previous School Address", blank=True)
    previous_academic_level = models.ForeignKey(
        'academics.AcademicLevel', 
        verbose_name="Previous Academic Level", 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='previous_students'
    )
    transfer_reason = models.TextField("Reason for Transfer", blank=True)
    transfer_certificate_number = models.CharField("Transfer Certificate Number", max_length=50, blank=True)
    previous_school_completion_date = models.DateField("Previous School Completion Date", null=True, blank=True)
    
    # -------------------------------------------------------------------------
    # MEDIA & DOCUMENTS
    # -------------------------------------------------------------------------
    
    photo = models.ImageField('Photo', upload_to='students/photos', blank=True, null=True)
    
    # -------------------------------------------------------------------------
    # RELATIONSHIPS
    # -------------------------------------------------------------------------
    
    # Guardian Relationships
    guardians = models.ManyToManyField(
        'Guardian',
        through='StudentGuardian',
        through_fields=('student', 'guardian'),
        related_name='students',
        blank=True
    )
    
    # -------------------------------------------------------------------------
    # STATUS & TRACKING
    # -------------------------------------------------------------------------
    
    enrollment_status = models.CharField("Enrollment Status", max_length=20, choices=ENROLLMENT_STATUS_CHOICES, default='active')
    graduation_date = models.DateField("Graduation Date", null=True, blank=True)
    withdrawal_date = models.DateField("Withdrawal Date", null=True, blank=True)

    # Add the custom manager
    objects = SchoolManager()
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.get_full_name()} ({self.admission_number})"
    
    # -------------------------------------------------------------------------
    # HELPER METHODS
    # -------------------------------------------------------------------------
    
    def get_full_name(self):
        """Get student's full name"""
        if self.middle_name:
            return f"{self.first_name} {self.middle_name} {self.last_name}"
        return f"{self.first_name} {self.last_name}"
    
    def get_age(self):
        """Calculate student's age"""
        from datetime import date
        today = date.today()
        age = today.year - self.date_of_birth.year - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))
        return age
    
    # -------------------------------------------------------------------------
    # SAVE METHOD
    # -------------------------------------------------------------------------
    
    def save(self, *args, **kwargs):
        """
        Automatically generate a century-safe admission number on first save.
        Gets school from current database context.
        """
        if not self.admission_number:
            from .utils import generate_student_admission_number
            from accounts.models import School
            from schoolara.managers import get_current_db
            
            # Get the current database alias
            current_db = get_current_db()
            
            # Find the school that matches this database
            try:
                school = School.objects.get(database_alias=current_db)
            except School.DoesNotExist:
                # Fallback: try to get from default database
                school = School.objects.using('default').filter(database_alias=current_db).first()
            
            # Generate admission number with school context
            self.admission_number = generate_student_admission_number(
                school=school,
                admission_year=self.admission_date.year if self.admission_date else None
            )
        
        super().save(*args, **kwargs)

    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------

    class Meta:
        ordering = ['admission_number']
        verbose_name = "Student"
        verbose_name_plural = "Students"
        indexes = [
            models.Index(fields=['admission_number']),
            models.Index(fields=['first_name', 'last_name']),
            models.Index(fields=['enrollment_status']),
            models.Index(fields=['current_academic_level']),
            models.Index(fields=['admission_date']),
        ]


# =============================================================================
# GUARDIAN MODEL
# =============================================================================

class Guardian(BaseModel):
    """Model for student guardians/parents"""

    # -------------------------------------------------------------------------
    # CHOICE FIELDS
    # -------------------------------------------------------------------------

    RELATION_CHOICES = [
        ('Father', 'Father'),
        ('Mother', 'Mother'),
        ('Uncle', 'Uncle'),
        ('Aunt', 'Aunt'),
        ('Brother', 'Brother'),
        ('Sister', 'Sister'),
        ('Guardian', 'Guardian'),
        ('Sponsor', 'Sponsor'),
        ('Grandparent', 'Grandparent'),
        ('Step_Father', 'Step Father'),
        ('Step_Mother', 'Step Mother'),
        ('Foster_Parent', 'Foster Parent'),
        ('Other', 'Other'),
    ]

    GUARDIAN_TYPE_CHOICES = [
        ('Primary', 'Primary Guardian'),
        ('Secondary', 'Secondary Guardian'),
        ('Emergency', 'Emergency Contact'),
        ('Financial', 'Financial Sponsor'),
    ]

    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
    ]

    # -------------------------------------------------------------------------
    # BASIC INFORMATION
    # -------------------------------------------------------------------------

    first_name = models.CharField("First Name", max_length=50)
    middle_name = models.CharField("Middle Name", max_length=50, blank=True, null=True)
    last_name = models.CharField("Last Name", max_length=50)

    # -------------------------------------------------------------------------
    # CONTACT INFORMATION
    # -------------------------------------------------------------------------

    primary_phone = models.CharField("Primary Phone", max_length=20)
    secondary_phone = models.CharField("Secondary Phone", max_length=20, blank=True)
    email = models.EmailField("Email", max_length=80, blank=True, null=True)

    # -------------------------------------------------------------------------
    # PERSONAL DETAILS
    # -------------------------------------------------------------------------

    date_of_birth = models.DateField("Date of Birth", null=True, blank=True)
    gender = models.CharField("Gender", max_length=1, choices=GENDER_CHOICES, blank=True)

    # -------------------------------------------------------------------------
    # PROFESSIONAL INFORMATION
    # -------------------------------------------------------------------------

    occupation = models.CharField("Occupation", max_length=50, blank=True)
    employer = models.CharField("Employer", max_length=50, blank=True)
    work_phone = models.CharField("Work Phone", max_length=20, blank=True)
    monthly_income = models.DecimalField(
        "Monthly Income",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )

    # -------------------------------------------------------------------------
    # ADDRESS INFORMATION
    # -------------------------------------------------------------------------

    home_address = models.TextField("Home Address")
    work_address = models.TextField("Work Address", blank=True)

    # -------------------------------------------------------------------------
    # IDENTIFICATION
    # -------------------------------------------------------------------------

    national_id = models.CharField("National ID", max_length=50, blank=True)
    passport_number = models.CharField("Passport Number", max_length=50, blank=True)

    # -------------------------------------------------------------------------
    # GUARDIAN CLASSIFICATION
    # -------------------------------------------------------------------------

    guardian_type = models.CharField(
        "Guardian Type",
        max_length=20,
        choices=GUARDIAN_TYPE_CHOICES,
        default='Primary'
    )

    # -------------------------------------------------------------------------
    # STATUS & MEDIA
    # -------------------------------------------------------------------------

    is_active = models.BooleanField("Is Active", default=True)
    photo = models.ImageField("Photo", upload_to='guardian_photos/', blank=True, null=True)

    # Add the custom manager
    objects = SchoolManager()

    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    # -------------------------------------------------------------------------
    # HELPER METHODS
    # -------------------------------------------------------------------------

    def get_full_name(self):
        """Return the guardian's full name"""
        if self.middle_name:
            return f"{self.first_name} {self.middle_name} {self.last_name}"
        return f"{self.first_name} {self.last_name}"

    def get_age(self):
        """Calculate age from date of birth"""
        if not self.date_of_birth:
            return None

        from datetime import date
        today = date.today()
        return (
            today.year
            - self.date_of_birth.year
            - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))
        )
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------

    class Meta:
        ordering = ['last_name', 'first_name']
        verbose_name = "Guardian"
        verbose_name_plural = "Guardians"
        indexes = [
            models.Index(fields=['guardian_type']),
            models.Index(fields=['is_active']),
            models.Index(fields=['first_name', 'last_name']),
        ]

class StudentGuardian(BaseModel):
    """Enhanced through model for student-guardian relationships"""
    
    # -------------------------------------------------------------------------
    # CHOICE FIELDS
    # -------------------------------------------------------------------------
    
    RELATIONSHIP_CHOICES = (
        ('Father', 'Father'),
        ('Mother', 'Mother'),
        ('Step_Father', 'Step Father'),
        ('Step_Mother', 'Step Mother'),
        ('Foster_Father', 'Foster Father'),
        ('Foster_Mother', 'Foster Mother'),
        ('Grandfather', 'Grandfather'),
        ('Grandmother', 'Grandmother'),
        ('Uncle', 'Uncle'),
        ('Aunt', 'Aunt'),
        ('Brother', 'Brother'),
        ('Sister', 'Sister'),
        ('Cousin', 'Cousin'),
        ('Guardian', 'Legal Guardian'),
        ('Sponsor', 'Sponsor'),
        ('Friend', 'Family Friend'),
        ('Other', 'Other'),
    )
    
    # -------------------------------------------------------------------------
    # CORE RELATIONSHIPS
    # -------------------------------------------------------------------------
    
    student = models.ForeignKey(
        Student,
        verbose_name="Student",
        on_delete=models.CASCADE,
        related_name='guardian_relationships'
    )
    guardian = models.ForeignKey(
        Guardian,
        verbose_name="Guardian",
        on_delete=models.CASCADE,
        related_name='student_relationships'
    )
    relationship = models.CharField(
        "Relationship", 
        max_length=20,
        choices=RELATIONSHIP_CHOICES
    )
    
    # -------------------------------------------------------------------------
    # RELATIONSHIP DETAILS
    # -------------------------------------------------------------------------
    
    is_primary = models.BooleanField("Primary Guardian", default=False)
    is_financial_responsible = models.BooleanField("Financial Responsibility", default=False)
    can_pickup = models.BooleanField("Can Pickup Student", default=True)
    can_authorize_medical = models.BooleanField("Can Authorize Medical Treatment", default=False)
    
    # -------------------------------------------------------------------------
    # CONTACT PRIORITIES
    # -------------------------------------------------------------------------
    
    emergency_contact_priority = models.PositiveSmallIntegerField(
        "Emergency Contact Priority",
        default=999,
        help_text="Lower number = higher priority"
    )
    
    # -------------------------------------------------------------------------
    # LEGAL INFORMATION
    # -------------------------------------------------------------------------
    
    has_custody = models.BooleanField("Has Legal Custody", default=False)
    custody_percentage = models.DecimalField(
        "Custody Percentage", 
        max_digits=5, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    
    # -------------------------------------------------------------------------
    # COMMUNICATION PREFERENCES
    # -------------------------------------------------------------------------
    
    receives_academic_reports = models.BooleanField("Receives Academic Reports", default=True)
    receives_financial_statements = models.BooleanField("Receives Financial Statements", default=True)
    receives_emergency_notifications = models.BooleanField("Receives Emergency Notifications", default=True)
    
    # -------------------------------------------------------------------------
    # STATUS & DATES
    # -------------------------------------------------------------------------
    
    is_active = models.BooleanField("Is Active", default=True)
    relationship_start_date = models.DateField("Relationship Start Date", default=timezone.now)
    relationship_end_date = models.DateField("Relationship End Date", null=True, blank=True)
    
    # Add the custom manager
    objects = SchoolManager()
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.student} - {self.get_relationship_display()}: {self.guardian}"
    
    # -------------------------------------------------------------------------
    # SAVE METHOD
    # -------------------------------------------------------------------------
    
    def save(self, *args, **kwargs):
        # Ensure only one primary guardian per student
        if self.is_primary:
            StudentGuardian.objects.filter(
                student=self.student, 
                is_primary=True
            ).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)
    
    # -------------------------------------------------------------------------
    # HELPER METHODS
    # -------------------------------------------------------------------------
    
    def get_emergency_priority_display(self):
        """Get emergency priority as string"""
        if self.emergency_contact_priority == 1:
            return "Primary Emergency Contact"
        elif self.emergency_contact_priority == 2:
            return "Secondary Emergency Contact"
        elif self.emergency_contact_priority <= 5:
            return f"Emergency Contact #{self.emergency_contact_priority}"
        return "Not Priority Emergency Contact"
    
    def is_emergency_contact(self):
        """Check if this guardian is an emergency contact"""
        return self.emergency_contact_priority <= 5
    
    # -------------------------------------------------------------------------
    # VALIDATION METHODS
    # -------------------------------------------------------------------------
    
    def clean(self):
        """Validate student-guardian relationship"""
        super().clean()
        errors = {}
        
        # Validate dates
        if self.relationship_end_date and self.relationship_start_date:
            if self.relationship_end_date < self.relationship_start_date:
                errors['relationship_end_date'] = "End date cannot be before start date"
        
        # Validate custody percentage
        if self.custody_percentage is not None:
            if not (0 <= self.custody_percentage <= 100):
                errors['custody_percentage'] = "Custody percentage must be between 0 and 100"
        
        if errors:
            raise ValidationError(errors)
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        ordering = ['emergency_contact_priority', 'relationship']
        verbose_name = "Student Guardian Relationship"
        verbose_name_plural = "Student Guardian Relationships"
        unique_together = ['student', 'guardian']
        indexes = [
            models.Index(fields=['student', 'is_active']),
            models.Index(fields=['guardian', 'is_active']),
            models.Index(fields=['is_primary']),
            models.Index(fields=['emergency_contact_priority']),
            models.Index(fields=['is_financial_responsible']),
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
        Student,
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

        if not self.enrollment_date:
            self.enrollment_date = timezone.now().date()

        if not self.roll_number:
            from .utils import generate_class_roll_number
            self.roll_number = generate_class_roll_number(
                class_instance=self.class_instance,
                academic_session=self.academic_session
            )

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
# DORMITORY MODEL
# =============================================================================

class Dormitory(BaseModel):
    """Model for managing dormitories and residential facilities"""
    
    # -------------------------------------------------------------------------
    # CHOICE FIELDS
    # -------------------------------------------------------------------------
    
    DORMITORY_TYPE_CHOICES = [
        ('BOYS', 'Boys Dormitory'),
        ('GIRLS', 'Girls Dormitory'),
        ('MIXED', 'Mixed Dormitory'),
        ('STAFF', 'Staff Quarters'),
    ]
    
    MAINTENANCE_STATUS_CHOICES = [
        ('EXCELLENT', 'Excellent Condition'),
        ('GOOD', 'Good Condition'),
        ('FAIR', 'Fair Condition'),
        ('NEEDS_REPAIR', 'Needs Repair'),
        ('UNDER_MAINTENANCE', 'Under Maintenance'),
        ('CONDEMNED', 'Condemned'),
    ]
    
    # -------------------------------------------------------------------------
    # BASIC INFORMATION
    # -------------------------------------------------------------------------
    
    name = models.CharField("Dormitory Name", max_length=100)
    code = models.CharField("Dormitory Code", max_length=20, unique=True)
    dormitory_type = models.CharField(
        "Dormitory Type",
        max_length=10,
        choices=DORMITORY_TYPE_CHOICES
    )
    
    # -------------------------------------------------------------------------
    # LOCATION DETAILS
    # -------------------------------------------------------------------------
    
    building = models.CharField("Building", max_length=100, blank=True)
    floor = models.CharField("Floor", max_length=10, blank=True)
    wing = models.CharField("Wing/Section", max_length=50, blank=True)
    
    # -------------------------------------------------------------------------
    # CAPACITY MANAGEMENT
    # -------------------------------------------------------------------------
    
    total_capacity = models.PositiveIntegerField("Total Capacity")
    current_occupancy = models.PositiveIntegerField("Current Occupancy", default=0)
    room_count = models.PositiveIntegerField("Number of Rooms", default=0)
    beds_per_room = models.PositiveIntegerField("Beds per Room", default=1)
    
    # -------------------------------------------------------------------------
    # FACILITIES
    # -------------------------------------------------------------------------
    
    has_bathroom = models.BooleanField("Has Bathroom", default=True)
    has_study_area = models.BooleanField("Has Study Area", default=False)
    has_common_room = models.BooleanField("Has Common Room", default=False)
    has_laundry = models.BooleanField("Has Laundry Facilities", default=False)
    has_kitchen = models.BooleanField("Has Kitchen", default=False)
    has_wifi = models.BooleanField("Has WiFi", default=False)
    has_security = models.BooleanField("Has Security", default=True)
    
    # -------------------------------------------------------------------------
    # MANAGEMENT STAFF
    # -------------------------------------------------------------------------
    
    dormitory_master = models.ForeignKey(
        'hr.Staff',
        verbose_name="Dormitory Master",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='managed_dormitories'
    )
    
    assistant_dormitory_master = models.ForeignKey(
        'hr.Staff',
        verbose_name="Assistant Dormitory Master",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assisted_dormitories'
    )
    
    # -------------------------------------------------------------------------
    # STATUS AND CONDITION
    # -------------------------------------------------------------------------
    
    is_active = models.BooleanField("Is Active", default=True)
    is_available_for_new_admissions = models.BooleanField(
        "Available for New Admissions", 
        default=True
    )
    
    maintenance_status = models.CharField(
        "Maintenance Status",
        max_length=20,
        choices=MAINTENANCE_STATUS_CHOICES,
        default='GOOD'
    )
    
    last_maintenance_date = models.DateField("Last Maintenance Date", null=True, blank=True)
    next_maintenance_due = models.DateField("Next Maintenance Due", null=True, blank=True)
    
    # -------------------------------------------------------------------------
    # DESCRIPTIONS AND RULES
    # -------------------------------------------------------------------------
    
    description = models.TextField("Description", blank=True)
    facilities_description = models.TextField("Facilities Description", blank=True)
    rules_and_regulations = models.TextField("Rules and Regulations", blank=True)
    emergency_procedures = models.TextField("Emergency Procedures", blank=True)
    
    # -------------------------------------------------------------------------
    # CONTACT INFORMATION
    # -------------------------------------------------------------------------
    
    dormitory_phone = models.CharField("Dormitory Phone", max_length=20, blank=True)
    dormitory_email = models.EmailField("Dormitory Email", blank=True)

    # Add the custom manager
    objects = SchoolManager()
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.name} ({self.get_dormitory_type_display()})"
    
    # -------------------------------------------------------------------------
    # CAPACITY METHODS
    # -------------------------------------------------------------------------
    
    def get_available_capacity(self):
        """Get available capacity"""
        return max(0, self.total_capacity - self.current_occupancy)
    
    def is_full(self):
        """Check if dormitory is at capacity"""
        return self.current_occupancy >= self.total_capacity
    
    def get_occupancy_percentage(self):
        """Get occupancy as percentage"""
        if self.total_capacity == 0:
            return 0
        return round((self.current_occupancy / self.total_capacity) * 100, 1)
    
    def get_occupancy_level(self):
        """Get occupancy level as string"""
        if self.total_capacity == 0:
            return 'low'
        
        ratio = self.current_occupancy / self.total_capacity
        if ratio < 0.7:
            return 'low'
        elif ratio < 0.9:
            return 'medium'
        else:
            return 'high'
    
    # -------------------------------------------------------------------------
    # VALIDATION METHODS
    # -------------------------------------------------------------------------
    
    def can_accommodate_gender(self, gender):
        """Check if dormitory can accommodate specific gender"""
        if self.dormitory_type == 'MIXED':
            return True
        elif self.dormitory_type == 'BOYS' and gender == 'M':
            return True
        elif self.dormitory_type == 'GIRLS' and gender == 'F':
            return True
        return False
    
    # -------------------------------------------------------------------------
    # HELPER METHODS
    # -------------------------------------------------------------------------
    
    def get_full_location(self):
        """Get full location description"""
        location_parts = [self.name]
        if self.building:
            location_parts.append(self.building)
        if self.floor:
            location_parts.append(f"Floor {self.floor}")
        if self.wing:
            location_parts.append(self.wing)
        return ", ".join(location_parts)
    
    def get_current_residents(self):
        """Get current residents of this dormitory"""
        return Student.objects.filter(
            boarding_enrollments__dormitory=self,
            boarding_enrollments__status='ACTIVE',
            enrollment_status='active'
        ).distinct()
    
    def get_resident_count(self):
        """Get count of current residents"""
        return self.get_current_residents().count()
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        ordering = ['dormitory_type', 'name']
        verbose_name = "Dormitory"
        verbose_name_plural = "Dormitories"
        indexes = [
            models.Index(fields=['dormitory_type']),
            models.Index(fields=['is_active']),
            models.Index(fields=['code']),
            models.Index(fields=['maintenance_status']),
        ]


# =============================================================================
# BOARDING ENROLLMENT MODEL
# =============================================================================

class BoardingEnrollment(BaseModel):
    """Model for tracking student boarding enrollment"""
    
    # -------------------------------------------------------------------------
    # CHOICE FIELDS
    # -------------------------------------------------------------------------
    
    BOARDING_TYPE_CHOICES = [
        ('FULL_BOARDER', 'Full Boarder'),
        ('WEEKLY_BOARDER', 'Weekly Boarder'),
        ('FLEXI_BOARDER', 'Flexible Boarder'),
    ]
    
    ENROLLMENT_STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('SUSPENDED', 'Suspended'),
        ('TERMINATED', 'Terminated'),
        ('COMPLETED', 'Completed'),
        ('PENDING', 'Pending Approval'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    # -------------------------------------------------------------------------
    # CORE RELATIONSHIPS
    # -------------------------------------------------------------------------
    
    student = models.ForeignKey(
        Student,
        verbose_name="Student",
        on_delete=models.CASCADE,
        related_name='boarding_enrollments'
    )
    
    academic_session = models.ForeignKey(
        'academics.AcademicSession',
        verbose_name="Academic Session",
        on_delete=models.CASCADE,
        related_name='boarding_enrollments'
    )
    
    # -------------------------------------------------------------------------
    # BOARDING CONFIGURATION
    # -------------------------------------------------------------------------
    
    boarding_type = models.CharField(
        "Boarding Type",
        max_length=20,
        choices=BOARDING_TYPE_CHOICES,
        help_text="Type of boarding arrangement for this student"
    )
    
    # -------------------------------------------------------------------------
    # ACCOMMODATION ASSIGNMENT
    # -------------------------------------------------------------------------
    
    dormitory = models.ForeignKey(
        Dormitory,
        verbose_name="Dormitory",
        on_delete=models.PROTECT,
        related_name='boarding_enrollments',
        help_text="Dormitory assignment is required for all boarding students"
    )
    
    room_number = models.CharField("Room Number", max_length=20, blank=True)
    bed_number = models.CharField("Bed Number", max_length=20, blank=True)
    
    # -------------------------------------------------------------------------
    # ROLL NUMBER FOR BOARDING/DORMITORY
    # -------------------------------------------------------------------------
    
    boarding_roll_number = models.CharField(
        "Boarding Roll Number", 
        max_length=20, 
        blank=True,
        help_text="Roll number for dormitory attendance and management"
    )
    
    # -------------------------------------------------------------------------
    # DATES AND STATUS
    # -------------------------------------------------------------------------
    
    enrollment_date = models.DateField("Boarding Enrollment Date")
    effective_start_date = models.DateField(
        "Effective Start Date",
        help_text="Date when boarding actually starts"
    )
    effective_end_date = models.DateField(
        "Effective End Date",
        null=True,
        blank=True,
        help_text="Date when boarding ends"
    )
    
    status = models.CharField(
        "Status",
        max_length=20,
        choices=ENROLLMENT_STATUS_CHOICES,
        default='PENDING'
    )
    
    # -------------------------------------------------------------------------
    # GUARDIAN CONSENT AND AUTHORIZATION
    # -------------------------------------------------------------------------
    
    guardian_consent = models.BooleanField(
        "Guardian Consent",
        default=False,
        help_text="Whether guardian has provided written consent for boarding"
    )
    
    consent_date = models.DateField("Consent Date", null=True, blank=True)
    consenting_guardian = models.ForeignKey(
        Guardian,
        verbose_name="Consenting Guardian",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='boarding_consents'
    )
    
    consent_document = models.FileField(
        "Consent Document",
        upload_to='boarding_consents/',
        null=True,
        blank=True
    )
    
    # -------------------------------------------------------------------------
    # FLEXIBLE BOARDING SCHEDULE
    # -------------------------------------------------------------------------
    
    boarding_days = models.JSONField(
        "Boarding Days",
        null=True,
        blank=True,
        help_text="JSON array of days when student boards (required for FLEXI_BOARDER)"
    )
    
    # -------------------------------------------------------------------------
    # MEDICAL AND DIETARY REQUIREMENTS
    # -------------------------------------------------------------------------
    
    dietary_requirements = models.TextField("Dietary Requirements", blank=True)
    medical_requirements = models.TextField("Medical Requirements", blank=True)
    special_accommodations = models.TextField("Special Accommodations", blank=True)
    
    # -------------------------------------------------------------------------
    # EMERGENCY CONTACTS FOR BOARDING
    # -------------------------------------------------------------------------
    
    emergency_contact_during_boarding = models.CharField(
        "Emergency Contact During Boarding",
        max_length=20,
        blank=True
    )
    
    emergency_contact_name = models.CharField(
        "Emergency Contact Name",
        max_length=100,
        blank=True
    )
    
    emergency_contact_relationship = models.CharField(
        "Emergency Contact Relationship",
        max_length=50,
        blank=True
    )
    
    # -------------------------------------------------------------------------
    # REASONS AND NOTES
    # -------------------------------------------------------------------------
    
    reason_for_boarding = models.TextField("Reason for Boarding", blank=True)
    termination_reason = models.TextField("Termination Reason", blank=True)
    admin_notes = models.TextField("Administrative Notes", blank=True)
    
    # -------------------------------------------------------------------------
    # APPROVAL WORKFLOW
    # -------------------------------------------------------------------------
    
    approved_by = models.ForeignKey(
        'hr.Staff',
        verbose_name="Approved By",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_boarding_enrollments'
    )
    
    approval_date = models.DateTimeField("Approval Date", null=True, blank=True)

    # Add the custom manager
    objects = SchoolManager()
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        display = f"{self.student.get_full_name()} - {self.get_boarding_type_display()} ({self.academic_session})"
        if self.boarding_roll_number:
            display += f" [Roll: {self.boarding_roll_number}]"
        return display
    
    # -------------------------------------------------------------------------
    # SAVE METHOD
    # -------------------------------------------------------------------------
    

    def save(self, *args, **kwargs):

        if not self.effective_start_date:
            self.effective_start_date = self.enrollment_date

        if self.status == 'ACTIVE' and not self.boarding_roll_number:
            from .utils import generate_boarding_roll_number
            self.boarding_roll_number = generate_boarding_roll_number(
                dormitory=self.dormitory,
                academic_session=self.academic_session
            )

        super().save(*args, **kwargs)
    
    # -------------------------------------------------------------------------
    # VALIDATION METHODS
    # -------------------------------------------------------------------------
    
    def clean(self):
        """Validate boarding enrollment"""
        super().clean()
        errors = {}
        
        # Validate dates
        if self.effective_end_date and self.effective_start_date:
            if self.effective_end_date < self.effective_start_date:
                errors['effective_end_date'] = "End date cannot be before start date"
        
        # Validate academic session dates
        if self.effective_start_date and self.academic_session:
            if (self.effective_start_date < self.academic_session.start_date or 
                self.effective_start_date > self.academic_session.end_date):
                errors['effective_start_date'] = "Start date must be within the academic session period"
        
        # Validate boarding days for flexible boarders
        if self.boarding_type == 'FLEXI_BOARDER':
            if not self.boarding_days:
                errors['boarding_days'] = "Boarding days must be specified for flexible boarders"
            elif not isinstance(self.boarding_days, list) or len(self.boarding_days) == 0:
                errors['boarding_days'] = "Boarding days must be a non-empty list"
        
        # Validate dormitory assignment for all boarding types
        if self.status == 'ACTIVE' and not self.dormitory:
            errors['dormitory'] = "Dormitory assignment is required for all boarding students"
        
        # Validate gender compatibility with dormitory
        if self.dormitory and hasattr(self.student, 'gender'):
            if not self.dormitory.can_accommodate_gender(self.student.gender):
                errors['dormitory'] = f"Selected dormitory cannot accommodate {self.student.get_gender_display()} students"
        
        # Validate guardian consent for minors
        if not self.guardian_consent and self.status in ['ACTIVE', 'PENDING']:
            student_age = self.student.get_age() if hasattr(self.student, 'get_age') else None
            if student_age and student_age < 18:
                errors['guardian_consent'] = "Guardian consent is required for boarding students under 18"
        
        if errors:
            raise ValidationError(errors)
    
    # -------------------------------------------------------------------------
    # HELPER METHODS
    # -------------------------------------------------------------------------
    
    def get_duration_days(self):
        """Get duration of boarding enrollment in days"""
        if not self.effective_end_date:
            end_date = timezone.now().date()
        else:
            end_date = self.effective_end_date
        
        return (end_date - self.effective_start_date).days
    
    def is_current(self):
        """Check if boarding enrollment is currently active"""
        if self.status != 'ACTIVE':
            return False
        
        today = timezone.now().date()
        if today < self.effective_start_date:
            return False
        
        if self.effective_end_date and today > self.effective_end_date:
            return False
        
        return True
    
    def get_boarding_schedule_display(self):
        """Get formatted boarding schedule"""
        if self.boarding_type == 'FULL_BOARDER':
            return "Monday - Sunday (Full Week)"
        elif self.boarding_type == 'WEEKLY_BOARDER':
            return "Monday - Friday (Weekdays)"
        elif self.boarding_type == 'FLEXI_BOARDER' and self.boarding_days:
            days = ", ".join(self.boarding_days)
            return f"Flexible: {days}"
        return "Not specified"

    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------

    class Meta:
        ordering = ['-academic_session__start_date', 'dormitory', 'boarding_roll_number', 'student__last_name']
        verbose_name = "Boarding Enrollment"
        verbose_name_plural = "Boarding Enrollments"
        
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'academic_session'],
                condition=Q(status__in=['ACTIVE', 'PENDING']),
                name='unique_active_boarding_per_student_session'
            ),
            models.UniqueConstraint(
                fields=['dormitory', 'academic_session', 'boarding_roll_number'],
                condition=Q(boarding_roll_number__isnull=False) & ~Q(boarding_roll_number='') & Q(status='ACTIVE'),
                name='unique_boarding_roll_number_per_dormitory_session'
            ),
        ]
        
        indexes = [
            models.Index(fields=['student', 'academic_session']),
            models.Index(fields=['boarding_type']),
            models.Index(fields=['status']),
            models.Index(fields=['dormitory']),
            models.Index(fields=['enrollment_date']),
            models.Index(fields=['effective_start_date']),
            models.Index(fields=['boarding_roll_number']),
            models.Index(fields=['dormitory', 'academic_session', 'boarding_roll_number']),
            models.Index(fields=['student', 'status']),
            models.Index(fields=['dormitory', 'status']),
        ]