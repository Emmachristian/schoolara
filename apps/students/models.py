# students/models.py

from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models import Q
from django.utils import timezone
from schoolara.managers import SchoolManager
from django_countries.fields import CountryField
from utils.models import BaseModel
from django.contrib.auth import get_user_model

User = get_user_model()

import logging

logger = logging.getLogger(__name__)


# =============================================================================
# STUDENT MODEL
# =============================================================================

class Student(BaseModel):
    """Core model for student information"""
    
    # -------------------------------------------------------------------------
    # CHOICE FIELDS
    # -------------------------------------------------------------------------
    
    GENDER_CHOICES = (
        ('M', 'Male'),
        ('F', 'Female'),
    )
    
    ENROLLMENT_STATUS_CHOICES = (
        ('ACTIVE', 'Active'),
        ('SUSPENDED', 'Suspended'),
        ('DISMISSED', 'Dismissed'),
        ('GRADUATED', 'Graduated'),
        ('TRANSFERRED', 'Transferred'),
        ('WITHDRAWN', 'Withdrawn'),
        ('DECEASED', 'Deceased'),
        ('DEFERRED', 'Deferred'),
    )
    
    RELIGIOUS_AFFILIATION_CHOICES = (
        ('CATHOLIC', 'Catholic'),
        ('PROTESTANT', 'Protestant'),
        ('ANGLICAN', 'Anglican'),
        ('BAPTIST', 'Baptist'),
        ('PENTECOSTAL', 'Pentecostal'),
        ('EVANGELICAL', 'Evangelical'),
        ('ADVENTIST', 'Adventist'),
        ('ISLAM', 'Islam'),
        ('HINDU', 'Hindu'),
        ('BUDDHIST', 'Buddhist'),
        ('JEWISH', 'Jewish'),
        ('TRADITIONAL', 'Traditional'),
        ('NONE', 'No Religion'),
        ('OTHER', 'Other'),
    )
    
    HEALTH_CONDITION_CHOICES = (
        ('EXCELLENT', 'Excellent'),
        ('GOOD', 'Good'),
        ('FAIR', 'Fair'),
        ('POOR', 'Poor'),
        ('CHRONIC', 'Chronic Condition'),
        ('RECOVERING', 'Recovering'),
        ('SPECIAL_NEEDS', 'Special Needs'),
        ('OTHER', 'Other'),
    )
    
    BLOOD_TYPE_CHOICES = (
        ('A+', 'A+'), ('A-', 'A-'),
        ('B+', 'B+'), ('B-', 'B-'),
        ('AB+', 'AB+'), ('AB-', 'AB-'),
        ('O+', 'O+'), ('O-', 'O-'),
        ('UNKNOWN', 'Unknown'),
    )
    
    # -------------------------------------------------------------------------
    # IDENTIFICATION & BASIC INFORMATION
    # -------------------------------------------------------------------------
    
    admission_number = models.CharField(
        "Admission Number",
        max_length=20,
        unique=True,
        blank=True,
        db_index=True
    )
    admission_date = models.DateField("Admission Date")
    
    national_student_number = models.CharField(
        "National Student Number",
        max_length=30,
        unique=True,
        null=True,
        blank=True,
        help_text="Government-issued student identification number"
    )
    
    birth_certificate_number = models.CharField(
        "Birth Certificate Number",
        max_length=50,
        blank=True
    )
    
    # Personal information
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
        related_name='current_students',
        help_text="Current grade/class level"
    )
    
    admission_academic_level = models.ForeignKey(
        'academics.AcademicLevel',
        verbose_name="Admission Academic Level",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='admitted_students',
        help_text="Grade/class level at time of admission"
    )
    
    # -------------------------------------------------------------------------
    # DEMOGRAPHICS & CULTURAL INFORMATION
    # -------------------------------------------------------------------------
    
    nationality = CountryField("Nationality", blank=True, null=True)
    ethnicity = models.CharField("Ethnicity", max_length=50, blank=True)
    birth_place = models.CharField("Place of Birth", max_length=100, blank=True)
    birth_country = CountryField("Country of Birth", blank=True, null=True)
    religious_affiliation = models.CharField(
        "Religious Affiliation",
        max_length=20,
        choices=RELIGIOUS_AFFILIATION_CHOICES,
        blank=True
    )
    
    # -------------------------------------------------------------------------
    # CONTACT & ADDRESS INFORMATION
    # -------------------------------------------------------------------------
    
    personal_email = models.EmailField("Personal Email", blank=True)
    phone_number = models.CharField("Phone Number", max_length=20, blank=True)
    home_address = models.TextField("Home Address")
    mailing_address = models.TextField("Mailing Address", blank=True)
    district = models.CharField("District", max_length=50, blank=True)
    region = models.CharField("Region/Province", max_length=50, blank=True)
    country_of_residence = CountryField("Country of Residence", blank=True, null=True)
    
    # -------------------------------------------------------------------------
    # HEALTH & MEDICAL INFORMATION
    # -------------------------------------------------------------------------
    
    health_condition = models.CharField(
        "Health Condition",
        max_length=20,
        choices=HEALTH_CONDITION_CHOICES,
        default='GOOD'
    )
    blood_type = models.CharField(
        "Blood Type",
        max_length=10,
        choices=BLOOD_TYPE_CHOICES,
        default='UNKNOWN'
    )
    medical_conditions = models.TextField("Medical Conditions", blank=True)
    allergies = models.TextField("Allergies", blank=True)
    medications = models.TextField("Current Medications", blank=True)
    special_medical_needs = models.TextField("Special Medical Needs", blank=True)
    emergency_medical_contact = models.CharField(
        "Emergency Medical Contact",
        max_length=20,
        blank=True
    )
    preferred_hospital = models.CharField("Preferred Hospital", max_length=100, blank=True)
    medical_insurance = models.CharField("Medical Insurance", max_length=100, blank=True)
    insurance_policy_number = models.CharField(
        "Insurance Policy Number",
        max_length=50,
        blank=True
    )
    
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
    
    transportation_required = models.BooleanField(
        "Transportation Required",
        default=False
    )
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
    transfer_certificate_number = models.CharField(
        "Transfer Certificate Number",
        max_length=50,
        blank=True
    )
    previous_school_completion_date = models.DateField(
        "Previous School Completion Date",
        null=True,
        blank=True
    )
    
    # -------------------------------------------------------------------------
    # MEDIA & DOCUMENTS
    # -------------------------------------------------------------------------
    
    photo = models.ImageField(
        'Photo',
        upload_to='students/photos/%Y/%m/',
        blank=True,
        null=True
    )
    
    # -------------------------------------------------------------------------
    # RELATIONSHIPS
    # -------------------------------------------------------------------------
    
    guardians = models.ManyToManyField(
        'Guardian',
        through='StudentGuardian',
        related_name='students',
        blank=True
    )
    
    # -------------------------------------------------------------------------
    # STATUS & TRACKING
    # -------------------------------------------------------------------------
    
    enrollment_status = models.CharField(
        "Enrollment Status",
        max_length=20,
        choices=ENROLLMENT_STATUS_CHOICES,
        default='ACTIVE',
        db_index=True
    )
    graduation_date = models.DateField("Graduation Date", null=True, blank=True)
    withdrawal_date = models.DateField("Withdrawal Date", null=True, blank=True)
    
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
            models.Index(fields=['date_of_birth']),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.get_full_name()} ({self.admission_number})"
    
    # -------------------------------------------------------------------------
    # PROPERTIES
    # -------------------------------------------------------------------------
    
    @property
    def full_name(self):
        """Get student's full name as property"""
        return self.get_full_name()
    
    @property
    def age(self):
        """Calculate student's age"""
        return self.get_age()
    
    # -------------------------------------------------------------------------
    # HELPER METHODS
    # -------------------------------------------------------------------------
    
    def get_full_name(self):
        """Get student's full name"""
        if self.middle_name:
            return f"{self.first_name} {self.middle_name} {self.last_name}"
        return f"{self.first_name} {self.last_name}"
    
    def get_age(self):
        """Calculate student's age in years"""
        from datetime import date
        today = date.today()
        age = (
            today.year - self.date_of_birth.year
            - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))
        )
        return age
    
    def get_primary_guardian(self):
        """Get the primary guardian for this student"""
        try:
            relationship = self.guardian_relationships.filter(
                is_primary=True,
                is_active=True
            ).select_related('guardian').first()
            return relationship.guardian if relationship else None
        except Exception as e:
            logger.error(f"Error getting primary guardian: {e}")
            return None
    
    def get_emergency_contacts(self):
        """Get emergency contacts ordered by priority"""
        return self.guardian_relationships.filter(
            is_active=True,
            emergency_contact_priority__lte=5
        ).order_by('emergency_contact_priority').select_related('guardian')
    
    def get_financial_guardians(self):
        """Get guardians responsible for fees"""
        return Guardian.objects.filter(
            student_relationships__student=self,
            student_relationships__is_financial_responsible=True,
            student_relationships__is_active=True
        ).distinct()
    
    def is_active(self):
        """Check if student is currently active"""
        return self.enrollment_status == 'ACTIVE'
    
    def has_medical_alert(self):
        """Check if student has any medical alerts"""
        return bool(
            self.medical_conditions or
            self.allergies or
            self.medications or
            self.special_medical_needs or
            self.has_special_needs
        )
    
    # -------------------------------------------------------------------------
    # SAVE METHOD
    # -------------------------------------------------------------------------
    
    def save(self, *args, **kwargs):
        """Override save to auto-generate admission number"""
        if not self.admission_number:
            from students.utils import generate_admission_number
            self.admission_number = generate_admission_number(
                admission_date=self.admission_date
            )
        
        super().save(*args, **kwargs)
    
    # -------------------------------------------------------------------------
    # VALIDATION
    # -------------------------------------------------------------------------
    
    def clean(self):
        """Validate student data"""
        super().clean()
        errors = {}
        
        # Validate age (students should typically be between 3 and 25)
        age = self.get_age()
        if age < 3 or age > 25:
            errors['date_of_birth'] = f"Student age ({age}) seems unusual. Please verify."
        
        # Validate dates
        if self.graduation_date and self.admission_date:
            if self.graduation_date < self.admission_date:
                errors['graduation_date'] = "Graduation date cannot be before admission date"
        
        if self.withdrawal_date and self.admission_date:
            if self.withdrawal_date < self.admission_date:
                errors['withdrawal_date'] = "Withdrawal date cannot be before admission date"
        
        if errors:
            raise ValidationError(errors)

# =============================================================================
# GUARDIAN MODEL
# =============================================================================

class Guardian(BaseModel):
    """Model for student guardians/parents"""
    
    # -------------------------------------------------------------------------
    # CHOICE FIELDS
    # -------------------------------------------------------------------------
    
    GUARDIAN_TYPE_CHOICES = [
        ('PRIMARY', 'Primary Guardian'),
        ('SECONDARY', 'Secondary Guardian'),
        ('EMERGENCY', 'Emergency Contact'),
        ('FINANCIAL', 'Financial Sponsor'),
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
    gender = models.CharField(
        "Gender",
        max_length=1,
        choices=GENDER_CHOICES,
        blank=True
    )
    
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
        blank=True,
        validators=[MinValueValidator(0)]
    )
    
    # -------------------------------------------------------------------------
    # ADDRESS INFORMATION
    # -------------------------------------------------------------------------
    
    home_address = models.TextField("Home Address")
    work_address = models.TextField("Work Address", blank=True)
    district = models.CharField("District", max_length=50, blank=True)
    city = models.CharField("City", max_length=50, blank=True)
    country = CountryField("Country", blank_label='(Select Country)', default='UG')
    
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
        default='PRIMARY'
    )
    
    # -------------------------------------------------------------------------
    # STATUS & MEDIA
    # -------------------------------------------------------------------------
    
    is_active = models.BooleanField("Is Active", default=True, db_index=True)
    photo = models.ImageField(
        "Photo",
        upload_to='guardians/photos/%Y/%m/',
        blank=True,
        null=True
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
            models.Index(fields=['primary_phone']),
            models.Index(fields=['email']),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return self.get_full_name()
    
    # -------------------------------------------------------------------------
    # PROPERTIES
    # -------------------------------------------------------------------------
    
    @property
    def full_name(self):
        """Get guardian's full name as property"""
        return self.get_full_name()
    
    @property
    def age(self):
        """Calculate guardian's age"""
        return self.get_age()
    
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
            today.year - self.date_of_birth.year
            - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))
        )
    
    def get_students(self):
        """Get all students for this guardian"""
        return Student.objects.filter(
            guardian_relationships__guardian=self,
            guardian_relationships__is_active=True
        ).distinct()
    
    def get_primary_students(self):
        """Get students where this guardian is primary"""
        return Student.objects.filter(
            guardian_relationships__guardian=self,
            guardian_relationships__is_primary=True,
            guardian_relationships__is_active=True
        ).distinct()
    
    def get_financial_responsibility_students(self):
        """Get students where this guardian is financially responsible"""
        return Student.objects.filter(
            guardian_relationships__guardian=self,
            guardian_relationships__is_financial_responsible=True,
            guardian_relationships__is_active=True
        ).distinct()
    
# =============================================================================
# STUDENT-GUARDIAN RELATIONSHIP MODEL
# =============================================================================

class StudentGuardian(BaseModel):
    """Through model for student-guardian relationships"""
    
    # -------------------------------------------------------------------------
    # CHOICE FIELDS
    # -------------------------------------------------------------------------
    
    RELATIONSHIP_CHOICES = (
        ('FATHER', 'Father'),
        ('MOTHER', 'Mother'),
        ('STEP_FATHER', 'Step Father'),
        ('STEP_MOTHER', 'Step Mother'),
        ('FOSTER_FATHER', 'Foster Father'),
        ('FOSTER_MOTHER', 'Foster Mother'),
        ('GRANDFATHER', 'Grandfather'),
        ('GRANDMOTHER', 'Grandmother'),
        ('UNCLE', 'Uncle'),
        ('AUNT', 'Aunt'),
        ('BROTHER', 'Brother'),
        ('SISTER', 'Sister'),
        ('COUSIN', 'Cousin'),
        ('GUARDIAN', 'Legal Guardian'),
        ('SPONSOR', 'Sponsor'),
        ('FRIEND', 'Family Friend'),
        ('OTHER', 'Other'),
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
    
    is_primary = models.BooleanField("Primary Guardian", default=False, db_index=True)
    is_financial_responsible = models.BooleanField(
        "Financial Responsibility",
        default=False,
        db_index=True
    )
    can_pickup = models.BooleanField("Can Pickup Student", default=True)
    can_authorize_medical = models.BooleanField(
        "Can Authorize Medical Treatment",
        default=False
    )
    
    # -------------------------------------------------------------------------
    # CONTACT PRIORITIES
    # -------------------------------------------------------------------------
    
    emergency_contact_priority = models.PositiveSmallIntegerField(
        "Emergency Contact Priority",
        default=999,
        validators=[MinValueValidator(1), MaxValueValidator(999)],
        help_text="Lower number = higher priority (1 is highest)"
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
    
    receives_academic_reports = models.BooleanField(
        "Receives Academic Reports",
        default=True
    )
    receives_financial_statements = models.BooleanField(
        "Receives Financial Statements",
        default=True
    )
    receives_emergency_notifications = models.BooleanField(
        "Receives Emergency Notifications",
        default=True
    )
    
    # -------------------------------------------------------------------------
    # STATUS & DATES
    # -------------------------------------------------------------------------
    
    is_active = models.BooleanField("Is Active", default=True, db_index=True)
    relationship_start_date = models.DateField(
        "Relationship Start Date",
        default=timezone.now
    )
    relationship_end_date = models.DateField(
        "Relationship End Date",
        null=True,
        blank=True
    )
    
    notes = models.TextField("Notes", blank=True)
    
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
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.student.get_full_name()} - {self.get_relationship_display()}: {self.guardian.get_full_name()}"
    
    # -------------------------------------------------------------------------
    # SAVE METHOD
    # -------------------------------------------------------------------------
    
    def save(self, *args, **kwargs):
        """Ensure only one primary guardian per student"""
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
        
# =============================================================================
# SIBLING RELATIONSHIP MODEL
# =============================================================================

class SiblingRelationship(BaseModel):
    """Model for tracking sibling relationships between students"""
    
    RELATIONSHIP_TYPES = (
        ('FULL', 'Full Sibling'),
        ('HALF', 'Half Sibling'),
        ('STEP', 'Step Sibling'),
        ('ADOPTED', 'Adopted Sibling'),
        ('FOSTER', 'Foster Sibling'),
        ('COUSIN', 'Cousin'),
    )
    
    from_student = models.ForeignKey(
        Student,
        verbose_name="Student",
        on_delete=models.CASCADE,
        related_name='sibling_relationships'
    )
    
    to_student = models.ForeignKey(
        Student,
        verbose_name="Sibling",
        on_delete=models.CASCADE,
        related_name='reverse_sibling_relationships'
    )
    
    relationship_type = models.CharField(
        "Relationship Type",
        max_length=10,
        choices=RELATIONSHIP_TYPES,
        default='FULL'
    )
    
    # Verification
    is_verified = models.BooleanField("Is Verified", default=False)
    verification_date = models.DateTimeField("Verification Date", null=True, blank=True)
    
    notes = models.TextField("Notes", blank=True)
    
    class Meta:
        verbose_name = "Sibling Relationship"
        verbose_name_plural = "Sibling Relationships"
        unique_together = ('from_student', 'to_student')
        indexes = [
            models.Index(fields=['from_student', 'is_verified']),
            models.Index(fields=['to_student', 'is_verified']),
        ]
    
    def __str__(self):
        return f"{self.from_student.get_full_name()} - {self.get_relationship_type_display()} - {self.to_student.get_full_name()}"
    
    def clean(self):
        """Validate sibling relationship"""
        if self.from_student == self.to_student:
            raise ValidationError("A student cannot be their own sibling")
    
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        
# =============================================================================
# ENROLLMENT STATUS HISTORY MODEL
# =============================================================================

class EnrollmentStatusHistory(BaseModel):
    """Track student enrollment status changes"""
    
    student = models.ForeignKey(
        Student,
        verbose_name="Student",
        on_delete=models.CASCADE,
        related_name='status_history'
    )
    
    previous_status = models.CharField(
        "Previous Status",
        max_length=20,
        choices=Student.ENROLLMENT_STATUS_CHOICES
    )
    
    new_status = models.CharField(
        "New Status",
        max_length=20,
        choices=Student.ENROLLMENT_STATUS_CHOICES
    )
    
    effective_date = models.DateField("Effective Date")
    
    reason = models.TextField("Reason for Change", blank=True)
    
    # Link to the academic session when change occurred
    academic_session = models.ForeignKey(
        'academics.AcademicSession',
        verbose_name="Academic Session",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Academic session when the status change occurred"
    )
    
    # Approval workflow
    approval_required = models.BooleanField("Approval Required", default=False)
    is_approved = models.BooleanField("Is Approved", default=False)
    approval_date = models.DateTimeField("Approval Date", null=True, blank=True)
    
    class Meta:
        verbose_name = "Enrollment Status History"
        verbose_name_plural = "Enrollment Status Histories"
        ordering = ['-effective_date']
        indexes = [
            models.Index(fields=['student', 'effective_date']),
            models.Index(fields=['new_status', 'effective_date']),
            models.Index(fields=['academic_session']),
        ]
    
    def __str__(self):
        return f"{self.student.get_full_name()}: {self.previous_status} → {self.new_status}"
    
    def get_changed_by_user(self):
        """Get the user who made this change"""
        return self.get_created_by()