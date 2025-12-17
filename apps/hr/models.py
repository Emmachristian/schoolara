from django.db import models
from django.core.validators import RegexValidator, MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta
from djmoney.models.fields import MoneyField
from djmoney.money import Money
from schoolara.managers import SchoolManager
from django_countries.fields import CountryField
from django.contrib.contenttypes.fields import GenericRelation
from decimal import Decimal
from django.db.models import Sum

from utils.models import BaseModel

# =============================================================================
# ORGANIZATIONAL STRUCTURE MODELS
# =============================================================================

class Department(BaseModel):
    """Model for school departments"""
    
    DEPARTMENT_TYPES = [
        ('ACADEMIC', 'Academic Department'),
        ('ADMINISTRATIVE', 'Administrative Department'),
        ('SUPPORT', 'Support Services'),
        ('TECHNICAL', 'Technical Department'),
        ('HEALTH', 'Health Services'),
        ('SECURITY', 'Security Department'),
        ('MAINTENANCE', 'Maintenance & Facilities'),
        ('FINANCE', 'Finance & Accounting'),
        ('HR', 'Human Resources'),
        ('IT', 'Information Technology'),
        ('LIBRARY', 'Library Services'),
        ('TRANSPORT', 'Transport Department'),
        ('CATERING', 'Catering Services'),
        ('SPORTS', 'Sports & Recreation'),
        ('RESEARCH', 'Research & Development'),
        ('PROCUREMENT', 'Procurement'),
        ('LEGAL', 'Legal Affairs'),
        ('MARKETING', 'Marketing & Communications'),
        ('STUDENT_AFFAIRS', 'Student Affairs'),
        ('QUALITY_ASSURANCE', 'Quality Assurance'),
        ('OTHER', 'Other')
    ]
    
    ACADEMIC_SUBTYPES = [
        ('MATHEMATICS', 'Mathematics'),
        ('SCIENCE', 'Science'),
        ('ENGLISH', 'English Language'),
        ('SOCIAL_STUDIES', 'Social Studies'),
        ('LANGUAGES', 'Foreign Languages'),
        ('ARTS', 'Creative Arts'),
        ('PHYSICAL_EDUCATION', 'Physical Education'),
        ('RELIGIOUS_STUDIES', 'Religious Studies'),
        ('COMPUTER_SCIENCE', 'Computer Science'),
        ('BUSINESS_STUDIES', 'Business Studies'),
        ('VOCATIONAL', 'Vocational Education'),
        ('SPECIAL_NEEDS', 'Special Needs Education'),
    ]
    
    name = models.CharField("Department Name", max_length=100)
    code = models.CharField("Department Code", max_length=10, unique=True)
    description = models.TextField("Description", blank=True)
    
    department_type = models.CharField(
        "Department Type",
        max_length=20,
        choices=DEPARTMENT_TYPES,
        default='ACADEMIC'
    )
    
    academic_subtype = models.CharField(
        "Academic Subject Area",
        max_length=20,
        choices=ACADEMIC_SUBTYPES,
        blank=True,
        null=True
    )
    
    is_academic = models.BooleanField("Is Academic", default=True)
    
    parent_department = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sub_departments'
    )
    
    annual_budget = MoneyField(
        "Annual Budget",
        max_digits=12,
        decimal_places=2,
        default=0,
        default_currency='UGX',
        null=True,
        blank=True
    )
    
    phone = models.CharField("Department Phone", max_length=20, blank=True)
    email = models.EmailField("Department Email", blank=True)
    
    head = models.ForeignKey(
        'Staff', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="headed_departments"
    )
    
    is_active = models.BooleanField("Is Active", default=True)
    capacity = models.PositiveIntegerField("Staff Capacity", null=True, blank=True)
    location = models.CharField("Location/Building", max_length=100, blank=True)
    operating_hours = models.JSONField("Operating Hours", default=dict, blank=True)

    # Add the custom manager
    objects = SchoolManager()

    def __str__(self):
        return f"{self.name} ({self.get_department_type_display()})"
    
    @property
    def is_academic_department(self):
        return self.department_type in ['ACADEMIC', 'RESEARCH', 'LIBRARY'] or self.is_academic
    
    def get_all_staff(self):
        """Get all staff in this department"""
        return Staff.objects.filter(
            designations__department=self,
            staffdesignation__is_active=True
        ).distinct()
    
    def get_staff_count(self):
        """Get count of active staff in this department"""
        return Staff.objects.filter(
            primary_department=self,
            is_active=True
        ).count()
    
    class Meta:
        ordering = ['department_type', 'name']
        verbose_name = "Department"
        verbose_name_plural = "Departments"


class Designation(BaseModel):
    """Model for staff designations/roles with salary reference ranges"""
    name = models.CharField("Designation Name", max_length=100)
    code = models.CharField("Designation Code", max_length=50, unique=True)
    description = models.TextField("Description", blank=True)
    department = models.ForeignKey(
        Department, 
        on_delete=models.CASCADE, 
        related_name="designations"
    )
    
    is_teaching = models.BooleanField("Is Teaching", default=False)
    is_management = models.BooleanField("Is Management Position", default=False)
    
    reports_to = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subordinate_designations'
    )
    
    rank_order = models.PositiveIntegerField("Rank Order", default=0)
    
    # SALARY RANGES - FOR REFERENCE ONLY
    min_salary = MoneyField(
        "Minimum Salary (Reference)",
        max_digits=10,
        decimal_places=2,
        default=0,
        default_currency='UGX',
        null=True,
        blank=True,
        help_text="Reference minimum salary for this designation"
    )
    
    max_salary = MoneyField(
        "Maximum Salary (Reference)",
        max_digits=10,
        decimal_places=2,
        default=0,
        default_currency='UGX',
        null=True,
        blank=True,
        help_text="Reference maximum salary for this designation"
    )
    
    required_qualifications = models.JSONField(
        "Required Qualifications",
        default=list,
        blank=True
    )
    
    key_responsibilities = models.TextField("Key Responsibilities", blank=True)
    is_active = models.BooleanField("Is Active", default=True)

    # Add the custom manager
    objects = SchoolManager()

    def __str__(self):
        return f"{self.name} ({self.department.name})"
    
    def get_salary_reference_range(self):
        """Get salary reference range for contract creation"""
        if self.min_salary and self.max_salary:
            return {
                'min': self.min_salary,
                'max': self.max_salary,
                'midpoint': (self.min_salary + self.max_salary) / 2,
                'new_hire_suggested': self.min_salary + ((self.max_salary - self.min_salary) * Decimal('0.2'))
            }
        return None
    
    class Meta:
        ordering = ['rank_order', 'name']
        verbose_name = "Designation"
        verbose_name_plural = "Designations"


# =============================================================================
# CONTRACT MANAGEMENT MODELS
# =============================================================================

class ContractType(BaseModel):
    """Types of contracts"""
    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    default_duration_months = models.PositiveIntegerField(default=12)
    requires_renewal = models.BooleanField(default=True)
    auto_create_probation = models.BooleanField(default=False)
    default_probation_months = models.PositiveIntegerField(default=3)
    is_active = models.BooleanField(default=True)

    # Add the custom manager
    objects = SchoolManager()
    
    class Meta:
        ordering = ['name']
        verbose_name = "Contract Type"
        verbose_name_plural = "Contract Types"
    
    def __str__(self):
        return self.name


class Contract(BaseModel):
    """Staff contracts with full lifecycle management and salary frequency support"""
    
    CONTRACT_STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('REVIEW', 'Under Review'),
        ('APPROVED', 'Approved'),
        ('SIGNED', 'Signed'),
        ('ACTIVE', 'Active'),
        ('EXPIRED', 'Expired'),
        ('TERMINATED', 'Terminated'),
        ('CANCELLED', 'Cancelled'),
        ('RENEWED', 'Renewed'),
    )
    
    TERMINATION_REASON_CHOICES = (
        ('COMPLETION', 'Contract Completion'),
        ('RESIGNATION', 'Staff Resignation'),
        ('TERMINATION', 'Employer Termination'),
        ('MUTUAL', 'Mutual Agreement'),
        ('BREACH', 'Contract Breach'),
        ('REDUNDANCY', 'Redundancy'),
        ('RETIREMENT', 'Retirement'),
        ('OTHER', 'Other'),
    )
    
    SALARY_FREQUENCY_CHOICES = (
        ('MONTHLY', 'Monthly'),
        ('WEEKLY', 'Weekly'),
        ('DAILY', 'Daily'),
        ('HOURLY', 'Hourly'),
        ('ANNUAL', 'Annual'),
    )
    
    staff = models.ForeignKey(
        'Staff', 
        on_delete=models.CASCADE, 
        related_name='contracts'
    )

    contract_type = models.ForeignKey(ContractType, on_delete=models.PROTECT, related_name='contracts')
    contract_number = models.CharField(max_length=50, unique=True, db_index=True)
    
    status = models.CharField(
        max_length=12,
        choices=CONTRACT_STATUS_CHOICES,
        default='DRAFT',
        db_index=True
    )
    
    # Important dates
    start_date = models.DateField("Contract Start Date")
    end_date = models.DateField("Contract End Date")
    signed_date = models.DateField("Date Signed", null=True, blank=True)
    renewal_due_date = models.DateField("Renewal Due Date", null=True, blank=True)
    
    # Termination information
    termination_date = models.DateField("Termination Date", null=True, blank=True)
    termination_reason = models.CharField(
        max_length=15,
        choices=TERMINATION_REASON_CHOICES,
        blank=True
    )
    termination_notice_period_days = models.PositiveIntegerField(
        "Notice Period (Days)", default=30
    )
    
    # Financial terms
    basic_salary = MoneyField(
        "Basic Salary",
        max_digits=10,
        decimal_places=2,
        default_currency='UGX',
        help_text="Basic salary amount - interpreted based on salary_frequency"
    )
    salary_frequency = models.CharField(
        "Salary Frequency",
        max_length=10,
        choices=SALARY_FREQUENCY_CHOICES,
        default='MONTHLY',
        help_text="How often this salary amount is paid"
    )
    
    # Contract terms
    working_hours_per_week = models.PositiveIntegerField(
        default=40,
        validators=[MinValueValidator(1), MaxValueValidator(168)]
    )
    probation_period_months = models.PositiveIntegerField(
        "Probation Period (Months)", default=0
    )
    annual_leave_days = models.PositiveIntegerField("Annual Leave Days", default=21)
    
    # Contract details
    job_title = models.CharField("Job Title", max_length=100)
    job_description = models.TextField("Job Description", blank=True)
    reporting_to = models.ForeignKey(
        'Staff',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='direct_reports_contracts'
    )
    
    # Contract documents
    contract_document = models.FileField(
        "Contract Document",
        upload_to='contracts/documents/',
        blank=True,
        null=True
    )
    
    # Auto-renewal settings
    auto_renew = models.BooleanField("Auto Renew", default=False)
    renewal_period_months = models.PositiveIntegerField(
        "Renewal Period (Months)", default=12
    )
    
    # User tracking for contract actions
    approved_by_id = models.CharField(max_length=100, null=True, blank=True)
    approved_at = models.DateTimeField("Approval Date", null=True, blank=True)
    signed_by_id = models.CharField(max_length=100, null=True, blank=True)
    signed_at = models.DateTimeField("Signed At", null=True, blank=True)
    terminated_by_id = models.CharField(max_length=100, null=True, blank=True)
    terminated_at = models.DateTimeField("Terminated At", null=True, blank=True)
    
    notes = models.TextField("Contract Notes", blank=True)

    # Add the custom manager
    objects = SchoolManager()
    
    def __str__(self):
        return f"{self.contract_number} - {self.staff.full_name()} ({self.contract_type})"
    
    @property
    def is_active(self):
        return self.status == 'ACTIVE'
    
    @property
    def is_expired(self):
        return self.end_date < timezone.now().date()
    
    @property
    def days_until_expiry(self):
        if self.end_date:
            return (self.end_date - timezone.now().date()).days
        return None
    
    @property
    def expires_soon(self):
        days = self.days_until_expiry
        return days is not None and 0 <= days <= 30


# =============================================================================
# STAFF MODELS
# =============================================================================

class Staff(BaseModel):
    """Enhanced staff model with comprehensive validation"""
    
    GENDER_CHOICES = (
        ('M', 'Male'),
        ('F', 'Female'),
    )
    
    EMPLOYMENT_STATUS_CHOICES = (
        ('FT', 'Full-Time'),
        ('PT', 'Part-Time'),
        ('CT', 'Contract'),
        ('PR', 'Probation'),
        ('IN', 'Intern'),
        ('VO', 'Volunteer'),
        ('RT', 'Retired'),
        ('TR', 'Terminated'),
        ('RS', 'Resigned'),
    )
    
    MARITAL_STATUS_CHOICES = (
        ('S', 'Single'),
        ('M', 'Married'),
        ('D', 'Divorced'),
        ('W', 'Widowed'),
        ('O', 'Other'),
    )

    SALUTATION_CHOICES = (
        ('MR', 'Mr.'),
        ('MS', 'Ms.'),
        ('MRS', 'Mrs.'),
        ('DR', 'Dr.'),
        ('PROF', 'Prof.'),
        ('REV', 'Rev.'),
        ('HON', 'Hon.'),
        ('SIR', 'Sir'),
        ('MADAM', 'Madam'),
        ('MISS', 'Miss'),
        ('MASTER', 'Master'),
    )

    RELIGIOUS_AFFILIATION_CHOICES = (
        ('Catholic', 'Catholic'),
        ('Protestant', 'Protestant'),
        ('Anglican', 'Anglican'),
        ('Baptist', 'Baptist'),
        ('Pentecostal', 'Pentecostal'),
        ('Evangelical', 'Evangelical'),
        ('Adventist', 'Adventist'),
        ('Islam', 'Islam'),
        ('Hindu', 'Hindu'),
        ('Buddhist', 'Buddhist'),
        ('Jewish', 'Jewish'),
        ('Traditional', 'Traditional'),
        ('None', 'No Religion'),
        ('Other', 'Other'),
    )

    # Basic information
    salutation = models.CharField(
        "Salutation", max_length=10, choices=SALUTATION_CHOICES, blank=True
    )
    first_name = models.CharField("First Name", max_length=50, db_index=True)
    middle_name = models.CharField("Middle Name", max_length=50, blank=True, db_index=True)
    last_name = models.CharField("Last Name", max_length=50, db_index=True)
    
    # Staff ID
    staff_id = models.CharField(
        "Staff ID", 
        max_length=30, 
        unique=True, 
        db_index=True,
        help_text="Format: YY/SCHOOL/[DEPT/]TYPE-NNN"
    )
    
    date_of_birth = models.DateField("Date of Birth", null=True, blank=True)
    gender = models.CharField("Gender", max_length=1, choices=GENDER_CHOICES, blank=True, db_index=True)

    ethnicity = models.CharField("Ethnicity", max_length=50, blank=True)
    religious_affiliation = models.CharField(
        "Religious Affiliation",
        max_length=20,
        choices=RELIGIOUS_AFFILIATION_CHOICES,
        blank=True
    )
    marital_status = models.CharField("Marital Status", max_length=1, choices=MARITAL_STATUS_CHOICES, blank=True)
    nationality = CountryField("Nationality", default='UG')
    national_id = models.CharField("National ID", max_length=50, blank=True)
    passport_number = models.CharField("Passport Number", max_length=50, blank=True)
    
    photo = models.ImageField(
        "Profile Picture", 
        upload_to='students/photos',  
        blank=True, 
        null=True
    )
    
    # Contact Information
    phone_regex = RegexValidator(
        regex=r'^\+?1?\d{9,15}$',
        message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed."
    )
    phone_number = models.CharField(
        "Phone Number", validators=[phone_regex], max_length=17, blank=True
    )
    alternative_phone = models.CharField(
        "Alternative Phone", validators=[phone_regex], max_length=17, blank=True
    )
    personal_email = models.EmailField("Personal Email", max_length=100, blank=True)  
    
    # Emergency Contact Information
    emergency_contact_name = models.CharField("Emergency Contact Name", max_length=100, blank=True)
    emergency_contact_relationship = models.CharField("Emergency Contact Relationship", max_length=20, blank=True)
    emergency_contact_phone = models.CharField(
        "Emergency Contact Phone", validators=[phone_regex], max_length=17, blank=True
    )
    emergency_contact_address = models.TextField("Emergency Contact Address", blank=True)
    
    # Multiple Designations Support
    designations = models.ManyToManyField(
        Designation,
        through='StaffDesignation',
        through_fields=('staff', 'designation'), 
        related_name='staff_members',
        verbose_name="Designations"
    )
    
    # Primary Department
    primary_department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL, 
        null=True,
        blank=True,
        related_name="primary_staff"
    )
    
    # Employment information
    employment_status = models.CharField(
        "Employment Status", max_length=2, choices=EMPLOYMENT_STATUS_CHOICES, 
        default='FT', db_index=True
    )
    date_of_joining = models.DateField("Date of Joining", db_index=True)
    date_of_leaving = models.DateField("Date of Leaving", null=True, blank=True)
    
    # Qualification and Experience
    qualification = models.TextField("Educational Qualifications", blank=True)
    experience = models.TextField("Work Experience", blank=True)
    skills = models.TextField("Skills", blank=True)
    languages_spoken = models.TextField("Languages Spoken", blank=True)
    professional_memberships = models.TextField("Professional Memberships", blank=True)
    certifications = models.TextField("Certifications", blank=True)
    
    # Banking Information
    bank_account_name = models.CharField("Bank Account Name", max_length=100, blank=True)
    bank_account_number = models.CharField("Bank Account Number", max_length=50, blank=True)
    bank_name = models.CharField("Bank Name", max_length=100, blank=True)
    bank_branch = models.CharField("Bank Branch", max_length=100, blank=True)
    
    # Tax and statutory information
    tax_identification_number = models.CharField("Tax ID Number", max_length=50, blank=True)
    social_security_number = models.CharField("Social Security Number", max_length=50, blank=True)
    
    # Status
    is_active = models.BooleanField("Is Active", default=True, db_index=True)

    # Add the custom manager
    objects = SchoolManager()
    
    def __str__(self):
        if self.middle_name:
            return f"{self.first_name} {self.middle_name} {self.last_name} ({self.staff_id})"
        return f"{self.first_name} {self.last_name} ({self.staff_id})"
    
    def full_name(self):
        """Get full name safely"""
        try:
            if self.middle_name:
                return f"{self.first_name} {self.middle_name} {self.last_name}"
            return f"{self.first_name} {self.last_name}"
        except Exception:
            return f"Staff {self.staff_id}"
    
    def clean(self):
        """Enhanced validation"""
        super().clean()
        errors = {}
        
        if self.date_of_leaving and self.date_of_leaving < self.date_of_joining:
            errors['date_of_leaving'] = "Date of leaving cannot be before date of joining"
        
        if self.date_of_birth and self.date_of_birth > timezone.now().date():
            errors['date_of_birth'] = "Birth date cannot be in the future"
        
        if self.date_of_birth and self.date_of_birth >= self.date_of_joining:
            errors['date_of_birth'] = "Birth date must be before joining date"
        
        if errors:
            raise ValidationError(errors)
        
    def save(self, *args, **kwargs):
        """
        Automatically generate a century-safe staff ID on first save only.
        Gets school from current database context.
        Staff ID is permanent and never changes.
        """
        if not self.staff_id:  # Only generate if staff_id doesn't exist
            from .utils import generate_staff_id
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
            
            # Generate staff ID with school context - ONLY ONCE
            # Use current values at time of creation
            self.staff_id = generate_staff_id(
                school=school,
                joining_year=self.date_of_joining.year if self.date_of_joining else None,
                department=self.primary_department,
                employment_status=self.employment_status,
                is_teaching=False  # Default to False; Teacher profile is separate
            )
        
        super().save(*args, **kwargs)

class StaffDesignation(BaseModel):
    """Through model for staff-designation relationship"""
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE)
    designation = models.ForeignKey(Designation, on_delete=models.CASCADE)
    
    is_primary = models.BooleanField("Is Primary Designation", default=False)
    
    start_date = models.DateField("Start Date", default=timezone.now)
    end_date = models.DateField("End Date", null=True, blank=True)
    is_active = models.BooleanField("Is Active", default=True)
    
    role_allowance = MoneyField(
        "Role-Specific Allowance",
        max_digits=10,
        decimal_places=2,
        default=0,
        default_currency='UGX'
    )
    
    ASSIGNMENT_TYPE_CHOICES = [
        ('PERMANENT', 'Permanent Assignment'),
        ('ACTING', 'Acting Role'),
        ('TEMPORARY', 'Temporary Assignment'),
        ('SECONDMENT', 'Secondment'),
        ('ADDITIONAL', 'Additional Responsibility'),
    ]
    assignment_type = models.CharField(
        "Assignment Type", max_length=20, choices=ASSIGNMENT_TYPE_CHOICES, default='PERMANENT'
    )
    
    assignment_order_number = models.CharField("Assignment Order Number", max_length=50, blank=True)
    notes = models.TextField("Notes", blank=True)

    # Add the custom manager
    objects = SchoolManager()
    
    def __str__(self):
        primary_indicator = " (Primary)" if self.is_primary else ""
        return f"{self.staff.full_name()} - {self.designation.name}{primary_indicator}"
    
    def clean(self):
        if self.start_date and self.end_date:
            if self.end_date < self.start_date:
                raise ValidationError("End date cannot be before start date")

# =============================================================================
# TEACHER MODEL
# =============================================================================

class Teacher(BaseModel):
    """Enhanced teacher model"""
    
    staff = models.OneToOneField(Staff, on_delete=models.CASCADE, related_name="teacher")
    
    specialization = models.CharField("Specialization", max_length=200, blank=True)
    teaching_philosophy = models.TextField("Teaching Philosophy", blank=True)
    
    max_hours_per_week = models.PositiveIntegerField(
        "Maximum Teaching Hours Per Week", default=40,
        validators=[MinValueValidator(1), MaxValueValidator(60)]
    )
    current_teaching_load = models.PositiveIntegerField(
        "Current Teaching Load (Hours)", default=0,
        validators=[MinValueValidator(0)]
    )
    
    # Use string references to avoid import issues
    preferred_academic_levels = models.ManyToManyField(
        'academics.AcademicLevel',
        blank=True,
        related_name='preferred_teachers'
    )
    
    qualified_subjects = models.ManyToManyField(
        'academics.Subject',
        blank=True,
        related_name='qualified_teachers'
    )
    
    available_days = models.JSONField("Available Days", default=list, blank=True)
    preferred_time_slots = models.JSONField("Preferred Time Slots", default=list, blank=True)
    
    is_class_teacher = models.BooleanField("Is Class Teacher", default=False)
    assigned_classes = models.ManyToManyField(
        'academics.Class',
        blank=True,
        related_name='class_teachers'
    )
    
    digital_literacy_level = models.CharField(
        "Digital Literacy Level",
        max_length=20,
        choices=[
            ('BASIC', 'Basic'),
            ('INTERMEDIATE', 'Intermediate'),
            ('ADVANCED', 'Advanced'),
            ('EXPERT', 'Expert'),
        ],
        default='BASIC'
    )
    
    can_teach_online = models.BooleanField("Can Teach Online", default=False)

    # Add the custom manager
    objects = SchoolManager()
    
    def __str__(self):
        return f"{self.staff.full_name()} - Teacher"
