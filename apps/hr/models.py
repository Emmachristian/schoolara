# hr/models.py

"""
Human Resources Management Models

Comprehensive HR system with:
- Organizational Structure (Departments, Designations)
- Staff Management
- Contract Management
- Teacher Profiles

All user tracking handled automatically by BaseModel
"""

from django.db import models
from django.core.validators import RegexValidator, MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from django_countries.fields import CountryField
from decimal import Decimal
import logging

from utils.models import BaseModel

logger = logging.getLogger(__name__)


# =============================================================================
# ORGANIZATIONAL STRUCTURE MODELS
# =============================================================================

class Department(BaseModel):
    """School departments for organizational structure"""
    
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
    
    # -------------------------------------------------------------------------
    # BASIC INFORMATION
    # -------------------------------------------------------------------------
    
    name = models.CharField("Department Name", max_length=100)
    code = models.CharField("Department Code", max_length=10, unique=True, db_index=True)
    description = models.TextField("Description", blank=True)
    
    # -------------------------------------------------------------------------
    # DEPARTMENT CLASSIFICATION
    # -------------------------------------------------------------------------
    
    department_type = models.CharField(
        "Department Type",
        max_length=20,
        choices=DEPARTMENT_TYPES,
        default='ACADEMIC',
        db_index=True
    )
    
    academic_subtype = models.CharField(
        "Academic Subject Area",
        max_length=20,
        choices=ACADEMIC_SUBTYPES,
        blank=True,
        null=True
    )
    
    is_academic = models.BooleanField("Is Academic", default=True)
    
    # -------------------------------------------------------------------------
    # HIERARCHICAL STRUCTURE
    # -------------------------------------------------------------------------
    
    parent_department = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sub_departments'
    )
    
    # -------------------------------------------------------------------------
    # BUDGET AND RESOURCES
    # -------------------------------------------------------------------------
    
    annual_budget = models.DecimalField(
        "Annual Budget",
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        null=True,
        blank=True
    )
    
    # -------------------------------------------------------------------------
    # CONTACT INFORMATION
    # -------------------------------------------------------------------------
    
    phone = models.CharField("Department Phone", max_length=20, blank=True)
    email = models.EmailField("Department Email", blank=True)
    
    # -------------------------------------------------------------------------
    # DEPARTMENT LEADERSHIP
    # -------------------------------------------------------------------------
    
    head_id = models.CharField(
        "Department Head ID",
        max_length=50,
        null=True,
        blank=True,
        help_text="Staff ID who heads this department"
    )
    
    # -------------------------------------------------------------------------
    # STATUS AND CAPACITY
    # -------------------------------------------------------------------------
    
    is_active = models.BooleanField("Is Active", default=True, db_index=True)
    capacity = models.PositiveIntegerField("Staff Capacity", null=True, blank=True)
    location = models.CharField("Location/Building", max_length=100, blank=True)
    operating_hours = models.JSONField("Operating Hours", default=dict, blank=True)
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Department"
        verbose_name_plural = "Departments"
        ordering = ['department_type', 'name']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['department_type']),
            models.Index(fields=['is_active']),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.name} ({self.get_department_type_display()})"
    
    # -------------------------------------------------------------------------
    # PROPERTIES
    # -------------------------------------------------------------------------
    
    @property
    def is_academic_department(self):
        return self.department_type in ['ACADEMIC', 'RESEARCH', 'LIBRARY'] or self.is_academic
    
    # -------------------------------------------------------------------------
    # HELPER METHODS
    # -------------------------------------------------------------------------
    
    def get_department_head(self):
        """Get the staff member who heads this department"""
        if not self.head_id:
            return None
        try:
            return Staff.objects.get(staff_id=self.head_id)
        except Staff.DoesNotExist:
            logger.error(f"Department head with ID {self.head_id} not found")
            return None
    
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


class Designation(BaseModel):
    """Staff designations/roles with salary reference ranges"""
    
    # -------------------------------------------------------------------------
    # BASIC INFORMATION
    # -------------------------------------------------------------------------
    
    name = models.CharField("Designation Name", max_length=100)
    code = models.CharField("Designation Code", max_length=50, unique=True, db_index=True)
    description = models.TextField("Description", blank=True)
    department = models.ForeignKey(
        Department, 
        on_delete=models.CASCADE, 
        related_name="designations"
    )
    
    # -------------------------------------------------------------------------
    # DESIGNATION CHARACTERISTICS
    # -------------------------------------------------------------------------
    
    is_teaching = models.BooleanField("Is Teaching", default=False)
    is_management = models.BooleanField("Is Management Position", default=False)
    
    # -------------------------------------------------------------------------
    # HIERARCHICAL REPORTING
    # -------------------------------------------------------------------------
    
    reports_to = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subordinate_designations'
    )
    
    rank_order = models.PositiveIntegerField("Rank Order", default=0, db_index=True)
    
    # -------------------------------------------------------------------------
    # SALARY RANGES (FOR REFERENCE ONLY)
    # -------------------------------------------------------------------------
    
    min_salary = models.DecimalField(
        "Minimum Salary (Reference)",
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        null=True,
        blank=True,
        help_text="Reference minimum salary for this designation"
    )
    
    max_salary = models.DecimalField(
        "Maximum Salary (Reference)",
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        null=True,
        blank=True,
        help_text="Reference maximum salary for this designation"
    )
    
    # -------------------------------------------------------------------------
    # QUALIFICATIONS AND RESPONSIBILITIES
    # -------------------------------------------------------------------------
    
    required_qualifications = models.JSONField(
        "Required Qualifications",
        default=list,
        blank=True
    )
    
    key_responsibilities = models.TextField("Key Responsibilities", blank=True)
    is_active = models.BooleanField("Is Active", default=True, db_index=True)
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Designation"
        verbose_name_plural = "Designations"
        ordering = ['rank_order', 'name']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['department']),
            models.Index(fields=['is_active']),
            models.Index(fields=['rank_order']),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.name} ({self.department.name})"
    
    # -------------------------------------------------------------------------
    # HELPER METHODS
    # -------------------------------------------------------------------------
    
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


# =============================================================================
# CONTRACT MANAGEMENT MODEL 
# =============================================================================

class Contract(BaseModel):
    """Staff employment contracts with full lifecycle management"""
    
    CONTRACT_TYPE_CHOICES = (
        ('PERMANENT', 'Permanent Contract'),
        ('FIXED_TERM', 'Fixed Term Contract'),
        ('PROBATION', 'Probationary Contract'),
        ('TEMPORARY', 'Temporary Contract'),
        ('PART_TIME', 'Part-Time Contract'),
        ('CASUAL', 'Casual Contract'),
        ('INTERNSHIP', 'Internship Contract'),
        ('VOLUNTEER', 'Volunteer Agreement'),
        ('CONSULTANT', 'Consultancy Contract'),
        ('SEASONAL', 'Seasonal Contract'),
        ('PROJECT_BASED', 'Project-Based Contract'),
        ('APPRENTICESHIP', 'Apprenticeship Contract'),
    )
    
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
    
    # -------------------------------------------------------------------------
    # CORE RELATIONSHIPS
    # -------------------------------------------------------------------------
    
    staff = models.ForeignKey(
        'Staff', 
        on_delete=models.CASCADE, 
        related_name='contracts'
    )
    
    # -------------------------------------------------------------------------
    # CONTRACT IDENTIFICATION
    # -------------------------------------------------------------------------
    
    contract_number = models.CharField(
        "Contract Number",
        max_length=50, 
        unique=True, 
        db_index=True
    )
    
    contract_type = models.CharField(
        "Contract Type",
        max_length=20,
        choices=CONTRACT_TYPE_CHOICES,
        default='FIXED_TERM',
        db_index=True
    )
    
    # -------------------------------------------------------------------------
    # CONTRACT STATUS
    # -------------------------------------------------------------------------
    
    status = models.CharField(
        "Status",
        max_length=12,
        choices=CONTRACT_STATUS_CHOICES,
        default='DRAFT',
        db_index=True
    )
    
    # -------------------------------------------------------------------------
    # IMPORTANT DATES
    # -------------------------------------------------------------------------
    
    start_date = models.DateField("Contract Start Date", db_index=True)
    end_date = models.DateField("Contract End Date", null=True, blank=True, db_index=True)
    signed_date = models.DateField("Date Signed", null=True, blank=True)
    renewal_due_date = models.DateField("Renewal Due Date", null=True, blank=True)
    
    # -------------------------------------------------------------------------
    # TERMINATION INFORMATION
    # -------------------------------------------------------------------------
    
    termination_date = models.DateField("Termination Date", null=True, blank=True)
    termination_reason = models.CharField(
        "Termination Reason",
        max_length=15,
        choices=TERMINATION_REASON_CHOICES,
        blank=True
    )
    termination_notice_period_days = models.PositiveIntegerField(
        "Notice Period (Days)", 
        default=30
    )
    termination_notes = models.TextField("Termination Notes", blank=True)
    
    # -------------------------------------------------------------------------
    # FINANCIAL TERMS
    # -------------------------------------------------------------------------
    
    basic_salary = models.DecimalField(
        "Basic Salary",
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Basic salary amount - interpreted based on salary_frequency"
    )
    salary_frequency = models.CharField(
        "Salary Frequency",
        max_length=10,
        choices=SALARY_FREQUENCY_CHOICES,
        default='MONTHLY',
        help_text="How often this salary amount is paid"
    )
    
    # -------------------------------------------------------------------------
    # CONTRACT TERMS
    # -------------------------------------------------------------------------
    
    working_hours_per_week = models.PositiveIntegerField(
        "Working Hours Per Week",
        default=40,
        validators=[MinValueValidator(1), MaxValueValidator(168)]
    )
    probation_period_months = models.PositiveIntegerField(
        "Probation Period (Months)", 
        default=0,
        help_text="Number of months for probation period (0 if no probation)"
    )
    annual_leave_days = models.PositiveIntegerField(
        "Annual Leave Days", 
        default=21
    )
    
    # -------------------------------------------------------------------------
    # JOB DETAILS
    # -------------------------------------------------------------------------
    
    job_title = models.CharField("Job Title", max_length=100)
    job_description = models.TextField("Job Description", blank=True)
    reporting_to_id = models.CharField(
        "Reports To Staff ID",
        max_length=50,
        null=True,
        blank=True,
        help_text="Staff ID of direct supervisor"
    )
    
    # -------------------------------------------------------------------------
    # CONTRACT DOCUMENTS
    # -------------------------------------------------------------------------
    
    contract_document = models.FileField(
        "Contract Document",
        upload_to='contracts/documents/',
        blank=True,
        null=True
    )
    
    # -------------------------------------------------------------------------
    # RENEWAL SETTINGS
    # -------------------------------------------------------------------------
    
    auto_renew = models.BooleanField(
        "Auto Renew", 
        default=False,
        help_text="Automatically renew contract when it expires"
    )
    renewal_period_months = models.PositiveIntegerField(
        "Renewal Period (Months)", 
        default=12,
        help_text="Duration of each renewal period"
    )
    requires_renewal_approval = models.BooleanField(
        "Requires Renewal Approval",
        default=True,
        help_text="Whether renewal requires approval"
    )
    
    # -------------------------------------------------------------------------
    # USER TRACKING FOR CONTRACT ACTIONS
    # -------------------------------------------------------------------------
    
    approved_by_id = models.CharField(
        "Approved By ID",
        max_length=100, 
        null=True, 
        blank=True,
        help_text="User ID who approved this contract"
    )
    approved_at = models.DateTimeField("Approval Date", null=True, blank=True)
    
    signed_by_id = models.CharField(
        "Signed By ID",
        max_length=100, 
        null=True, 
        blank=True,
        help_text="User ID who signed this contract"
    )
    signed_at = models.DateTimeField("Signed At", null=True, blank=True)
    
    terminated_by_id = models.CharField(
        "Terminated By ID",
        max_length=100, 
        null=True, 
        blank=True,
        help_text="User ID who terminated this contract"
    )
    terminated_at = models.DateTimeField("Terminated At", null=True, blank=True)
    
    # -------------------------------------------------------------------------
    # ADDITIONAL FIELDS
    # -------------------------------------------------------------------------
    
    benefits_package = models.JSONField(
        "Benefits Package",
        default=dict,
        blank=True,
        help_text="JSON structure for contract benefits (health insurance, housing, etc.)"
    )
    
    special_terms = models.TextField(
        "Special Terms & Conditions",
        blank=True,
        help_text="Any special terms or conditions for this contract"
    )
    
    notes = models.TextField("Contract Notes", blank=True)
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Contract"
        verbose_name_plural = "Contracts"
        ordering = ['-start_date', 'staff']
        indexes = [
            models.Index(fields=['contract_number']),
            models.Index(fields=['staff', 'status']),
            models.Index(fields=['contract_type']),
            models.Index(fields=['status']),
            models.Index(fields=['start_date', 'end_date']),
            models.Index(fields=['staff', 'contract_type']),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.contract_number} - {self.staff.full_name()} ({self.get_contract_type_display()})"
    
    # -------------------------------------------------------------------------
    # VALIDATION METHODS
    # -------------------------------------------------------------------------
    
    def clean(self):
        """Validate contract data"""
        super().clean()
        errors = {}
        
        # Validate dates
        if self.end_date and self.end_date < self.start_date:
            errors['end_date'] = "End date cannot be before start date"
        
        # Validate termination date
        if self.termination_date:
            if self.termination_date < self.start_date:
                errors['termination_date'] = "Termination date cannot be before start date"
            if self.end_date and self.termination_date > self.end_date:
                errors['termination_date'] = "Termination date cannot be after contract end date"
        
        # Permanent contracts should not have end dates
        if self.contract_type == 'PERMANENT' and self.end_date:
            errors['end_date'] = "Permanent contracts should not have an end date"
        
        # Fixed term contracts must have end dates
        if self.contract_type in ['FIXED_TERM', 'PROBATION', 'TEMPORARY', 'SEASONAL', 'PROJECT_BASED'] and not self.end_date:
            errors['end_date'] = f"{self.get_contract_type_display()} must have an end date"
        
        if errors:
            raise ValidationError(errors)
    
    # -------------------------------------------------------------------------
    # PROPERTIES
    # -------------------------------------------------------------------------
    
    @property
    def is_active(self):
        """Check if contract is currently active"""
        return self.status == 'ACTIVE'
    
    @property
    def is_expired(self):
        """Check if contract has expired"""
        if not self.end_date:
            return False
        return self.end_date < timezone.now().date()
    
    @property
    def days_until_expiry(self):
        """Calculate days until contract expires"""
        if not self.end_date:
            return None
        return (self.end_date - timezone.now().date()).days
    
    @property
    def expires_soon(self, days_threshold=30):
        """Check if contract expires within threshold days"""
        days = self.days_until_expiry
        return days is not None and 0 <= days <= days_threshold
    
    @property
    def is_permanent(self):
        """Check if this is a permanent contract"""
        return self.contract_type == 'PERMANENT'
    
    @property
    def is_probationary(self):
        """Check if contract is probationary or has active probation period"""
        if self.contract_type == 'PROBATION':
            return True
        
        if self.probation_period_months > 0:
            from datetime import timedelta
            probation_end = self.start_date + timedelta(days=self.probation_period_months * 30)
            return timezone.now().date() <= probation_end
        
        return False
    
    @property
    def duration_in_months(self):
        """Calculate contract duration in months"""
        if not self.end_date:
            return None
        
        return ((self.end_date.year - self.start_date.year) * 12 + 
                (self.end_date.month - self.start_date.month))
    
    # -------------------------------------------------------------------------
    # HELPER METHODS - USER RETRIEVAL
    # -------------------------------------------------------------------------
    
    def get_reporting_to_staff(self):
        """Get the staff member this person reports to"""
        if not self.reporting_to_id:
            return None
        try:
            return Staff.objects.get(staff_id=self.reporting_to_id)
        except Staff.DoesNotExist:
            logger.error(f"Reporting staff with ID {self.reporting_to_id} not found")
            return None
    
    def get_approved_by_user(self):
        """Get the user who approved this contract"""
        if not self.approved_by_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            return User.objects.using('default').get(id=self.approved_by_id)
        except Exception as e:
            logger.error(f"Error fetching approved_by user: {e}")
            return None
    
    def get_signed_by_user(self):
        """Get the user who signed this contract"""
        if not self.signed_by_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            return User.objects.using('default').get(id=self.signed_by_id)
        except Exception as e:
            logger.error(f"Error fetching signed_by user: {e}")
            return None
    
    def get_terminated_by_user(self):
        """Get the user who terminated this contract"""
        if not self.terminated_by_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            return User.objects.using('default').get(id=self.terminated_by_id)
        except Exception as e:
            logger.error(f"Error fetching terminated_by user: {e}")
            return None
    
    # -------------------------------------------------------------------------
    # ACTION METHODS
    # -------------------------------------------------------------------------
    
    def activate(self, user=None):
        """Activate the contract"""
        self.status = 'ACTIVE'
        if user:
            self.approved_by_id = str(user.id) if hasattr(user, 'id') else str(user.pk)
            self.approved_at = timezone.now()
        self.save()
    
    def terminate(self, reason, user=None, termination_date=None, notes=''):
        """Terminate the contract"""
        self.status = 'TERMINATED'
        self.termination_reason = reason
        self.termination_date = termination_date or timezone.now().date()
        self.termination_notes = notes
        
        if user:
            self.terminated_by_id = str(user.id) if hasattr(user, 'id') else str(user.pk)
            self.terminated_at = timezone.now()
        
        self.save()
    
    def renew(self, new_end_date=None, user=None):
        """Renew the contract"""
        from datetime import timedelta
        
        if not new_end_date:
            # Calculate new end date based on renewal period
            if self.end_date:
                new_end_date = self.end_date + timedelta(days=self.renewal_period_months * 30)
            else:
                new_end_date = timezone.now().date() + timedelta(days=self.renewal_period_months * 30)
        
        self.end_date = new_end_date
        self.status = 'ACTIVE'
        self.renewal_due_date = None  # Clear renewal due date
        
        if user:
            self.approved_by_id = str(user.id) if hasattr(user, 'id') else str(user.pk)
            self.approved_at = timezone.now()
        
        self.save()
    
    # -------------------------------------------------------------------------
    # CLASS METHODS
    # -------------------------------------------------------------------------
    
    @classmethod
    def get_active_contracts(cls):
        """Get all active contracts"""
        return cls.objects.filter(status='ACTIVE')
    
    @classmethod
    def get_expiring_soon(cls, days=30):
        """Get contracts expiring within specified days"""
        from datetime import timedelta
        threshold_date = timezone.now().date() + timedelta(days=days)
        return cls.objects.filter(
            status='ACTIVE',
            end_date__lte=threshold_date,
            end_date__gte=timezone.now().date()
        ).order_by('end_date')
    
    @classmethod
    def get_expired_contracts(cls):
        """Get all expired contracts that are still marked as active"""
        return cls.objects.filter(
            status='ACTIVE',
            end_date__lt=timezone.now().date()
        )
    
    @classmethod
    def get_staff_active_contract(cls, staff):
        """Get the active contract for a staff member"""
        return cls.objects.filter(
            staff=staff,
            status='ACTIVE'
        ).first()
    
    @classmethod
    def get_contracts_by_type(cls, contract_type):
        """Get all contracts of a specific type"""
        return cls.objects.filter(contract_type=contract_type)


# =============================================================================
# STAFF MODELS
# =============================================================================

class Staff(BaseModel):
    """Comprehensive staff management model"""
    
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
    
    # -------------------------------------------------------------------------
    # BASIC INFORMATION
    # -------------------------------------------------------------------------
    
    salutation = models.CharField(
        "Salutation", 
        max_length=10, 
        choices=SALUTATION_CHOICES, 
        blank=True
    )
    first_name = models.CharField("First Name", max_length=50, db_index=True)
    middle_name = models.CharField("Middle Name", max_length=50, blank=True, db_index=True)
    last_name = models.CharField("Last Name", max_length=50, db_index=True)
    
    # -------------------------------------------------------------------------
    # STAFF ID
    # -------------------------------------------------------------------------
    
    staff_id = models.CharField(
        "Staff ID", 
        max_length=30, 
        unique=True, 
        db_index=True,
        help_text="Format: YY/SCHOOL/[DEPT/]TYPE-NNN"
    )
    
    # -------------------------------------------------------------------------
    # PERSONAL INFORMATION
    # -------------------------------------------------------------------------
    
    date_of_birth = models.DateField("Date of Birth", null=True, blank=True)
    gender = models.CharField(
        "Gender", 
        max_length=1, 
        choices=GENDER_CHOICES, 
        blank=True, 
        db_index=True
    )
    
    ethnicity = models.CharField("Ethnicity", max_length=50, blank=True)
    religious_affiliation = models.CharField(
        "Religious Affiliation",
        max_length=20,
        choices=RELIGIOUS_AFFILIATION_CHOICES,
        blank=True
    )
    marital_status = models.CharField(
        "Marital Status", 
        max_length=1, 
        choices=MARITAL_STATUS_CHOICES, 
        blank=True
    )
    nationality = CountryField("Nationality", default='UG')
    national_id = models.CharField("National ID", max_length=50, blank=True)
    passport_number = models.CharField("Passport Number", max_length=50, blank=True)
    
    # -------------------------------------------------------------------------
    # PROFILE PICTURE
    # -------------------------------------------------------------------------
    
    photo = models.ImageField(
        "Profile Picture", 
        upload_to='staff/photos',  
        blank=True, 
        null=True
    )
    
    # -------------------------------------------------------------------------
    # CONTACT INFORMATION
    # -------------------------------------------------------------------------
    
    phone_regex = RegexValidator(
        regex=r'^\+?1?\d{9,15}$',
        message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed."
    )
    phone_number = models.CharField(
        "Phone Number", 
        validators=[phone_regex], 
        max_length=17, 
        blank=True
    )
    alternative_phone = models.CharField(
        "Alternative Phone", 
        validators=[phone_regex], 
        max_length=17, 
        blank=True
    )
    personal_email = models.EmailField("Personal Email", max_length=100, blank=True)
    
    # -------------------------------------------------------------------------
    # EMERGENCY CONTACT INFORMATION
    # -------------------------------------------------------------------------
    
    emergency_contact_name = models.CharField("Emergency Contact Name", max_length=100, blank=True)
    emergency_contact_relationship = models.CharField("Emergency Contact Relationship", max_length=20, blank=True)
    emergency_contact_phone = models.CharField(
        "Emergency Contact Phone", 
        validators=[phone_regex], 
        max_length=17, 
        blank=True
    )
    emergency_contact_address = models.TextField("Emergency Contact Address", blank=True)
    
    # -------------------------------------------------------------------------
    # MULTIPLE DESIGNATIONS SUPPORT
    # -------------------------------------------------------------------------
    
    designations = models.ManyToManyField(
        Designation,
        through='StaffDesignation',
        through_fields=('staff', 'designation'), 
        related_name='staff_members',
        verbose_name="Designations"
    )
    
    # -------------------------------------------------------------------------
    # PRIMARY DEPARTMENT
    # -------------------------------------------------------------------------
    
    primary_department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL, 
        null=True,
        blank=True,
        related_name="primary_staff"
    )
    
    # -------------------------------------------------------------------------
    # EMPLOYMENT INFORMATION
    # -------------------------------------------------------------------------
    
    employment_status = models.CharField(
        "Employment Status", 
        max_length=2, 
        choices=EMPLOYMENT_STATUS_CHOICES, 
        default='FT', 
        db_index=True
    )
    date_of_joining = models.DateField("Date of Joining", db_index=True)
    date_of_leaving = models.DateField("Date of Leaving", null=True, blank=True)
    
    # -------------------------------------------------------------------------
    # QUALIFICATION AND EXPERIENCE
    # -------------------------------------------------------------------------
    
    qualification = models.TextField("Educational Qualifications", blank=True)
    experience = models.TextField("Work Experience", blank=True)
    skills = models.TextField("Skills", blank=True)
    languages_spoken = models.TextField("Languages Spoken", blank=True)
    professional_memberships = models.TextField("Professional Memberships", blank=True)
    certifications = models.TextField("Certifications", blank=True)
    
    # -------------------------------------------------------------------------
    # BANKING INFORMATION
    # -------------------------------------------------------------------------
    
    bank_account_name = models.CharField("Bank Account Name", max_length=100, blank=True)
    bank_account_number = models.CharField("Bank Account Number", max_length=50, blank=True)
    bank_name = models.CharField("Bank Name", max_length=100, blank=True)
    bank_branch = models.CharField("Bank Branch", max_length=100, blank=True)
    
    # -------------------------------------------------------------------------
    # TAX AND STATUTORY INFORMATION
    # -------------------------------------------------------------------------
    
    tax_identification_number = models.CharField("Tax ID Number", max_length=50, blank=True)
    social_security_number = models.CharField("Social Security Number", max_length=50, blank=True)
    
    # -------------------------------------------------------------------------
    # STATUS
    # -------------------------------------------------------------------------
    
    is_active = models.BooleanField("Is Active", default=True, db_index=True)
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Staff"
        verbose_name_plural = "Staff"
        ordering = ['first_name', 'last_name']
        indexes = [
            models.Index(fields=['staff_id']),
            models.Index(fields=['first_name', 'last_name']),
            models.Index(fields=['is_active']),
            models.Index(fields=['employment_status']),
            models.Index(fields=['date_of_joining']),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        if self.middle_name:
            return f"{self.first_name} {self.middle_name} {self.last_name} ({self.staff_id})"
        return f"{self.first_name} {self.last_name} ({self.staff_id})"
    
    # -------------------------------------------------------------------------
    # HELPER METHODS
    # -------------------------------------------------------------------------
    
    def full_name(self):
        """Get full name safely"""
        try:
            if self.middle_name:
                return f"{self.first_name} {self.middle_name} {self.last_name}"
            return f"{self.first_name} {self.last_name}"
        except Exception:
            return f"Staff {self.staff_id}"
    
    # -------------------------------------------------------------------------
    # VALIDATION METHODS
    # -------------------------------------------------------------------------
    
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
        Automatically generate staff ID on first save only.
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
            self.staff_id = generate_staff_id(
                school=school,
                joining_year=self.date_of_joining.year if self.date_of_joining else None,
                department=self.primary_department,
                employment_status=self.employment_status,
                is_teaching=False  # Default to False; Teacher profile is separate
            )
        
        super().save(*args, **kwargs)


class StaffDesignation(BaseModel):
    """Through model for staff-designation relationship with detailed assignment tracking"""
    
    ASSIGNMENT_TYPE_CHOICES = [
        ('PERMANENT', 'Permanent Assignment'),
        ('ACTING', 'Acting Role'),
        ('TEMPORARY', 'Temporary Assignment'),
        ('SECONDMENT', 'Secondment'),
        ('ADDITIONAL', 'Additional Responsibility'),
    ]
    
    # -------------------------------------------------------------------------
    # CORE RELATIONSHIPS
    # -------------------------------------------------------------------------
    
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE)
    designation = models.ForeignKey(Designation, on_delete=models.CASCADE)
    
    # -------------------------------------------------------------------------
    # DESIGNATION FLAGS
    # -------------------------------------------------------------------------
    
    is_primary = models.BooleanField("Is Primary Designation", default=False)
    
    # -------------------------------------------------------------------------
    # DATE RANGE
    # -------------------------------------------------------------------------
    
    start_date = models.DateField("Start Date", default=timezone.now)
    end_date = models.DateField("End Date", null=True, blank=True)
    is_active = models.BooleanField("Is Active", default=True, db_index=True)
    
    # -------------------------------------------------------------------------
    # ROLE ALLOWANCE
    # -------------------------------------------------------------------------
    
    role_allowance = models.DecimalField(
        "Role-Specific Allowance",
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00')
    )
    
    # -------------------------------------------------------------------------
    # ASSIGNMENT TYPE
    # -------------------------------------------------------------------------
    
    assignment_type = models.CharField(
        "Assignment Type", 
        max_length=20, 
        choices=ASSIGNMENT_TYPE_CHOICES, 
        default='PERMANENT'
    )
    
    # -------------------------------------------------------------------------
    # ASSIGNMENT DETAILS
    # -------------------------------------------------------------------------
    
    assignment_order_number = models.CharField("Assignment Order Number", max_length=50, blank=True)
    notes = models.TextField("Notes", blank=True)
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Staff Designation"
        verbose_name_plural = "Staff Designations"
        ordering = ['staff', '-is_primary', 'designation']
        indexes = [
            models.Index(fields=['staff', 'is_primary']),
            models.Index(fields=['designation', 'is_active']),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        primary_indicator = " (Primary)" if self.is_primary else ""
        return f"{self.staff.full_name()} - {self.designation.name}{primary_indicator}"
    
    # -------------------------------------------------------------------------
    # VALIDATION METHODS
    # -------------------------------------------------------------------------
    
    def clean(self):
        if self.start_date and self.end_date:
            if self.end_date < self.start_date:
                raise ValidationError("End date cannot be before start date")


# =============================================================================
# TEACHER MODEL
# =============================================================================

class Teacher(BaseModel):
    """Enhanced teacher profile linked to staff"""
    
    # -------------------------------------------------------------------------
    # CORE RELATIONSHIP
    # -------------------------------------------------------------------------
    
    staff = models.OneToOneField(
        Staff, 
        on_delete=models.CASCADE, 
        related_name="teacher"
    )
    
    # -------------------------------------------------------------------------
    # TEACHING SPECIALIZATION
    # -------------------------------------------------------------------------
    
    specialization = models.CharField("Specialization", max_length=200, blank=True)
    teaching_philosophy = models.TextField("Teaching Philosophy", blank=True)
    
    # -------------------------------------------------------------------------
    # TEACHING LOAD
    # -------------------------------------------------------------------------
    
    max_hours_per_week = models.PositiveIntegerField(
        "Maximum Teaching Hours Per Week", 
        default=40,
        validators=[MinValueValidator(1), MaxValueValidator(60)]
    )
    current_teaching_load = models.PositiveIntegerField(
        "Current Teaching Load (Hours)", 
        default=0,
        validators=[MinValueValidator(0)]
    )
    
    # -------------------------------------------------------------------------
    # ACADEMIC PREFERENCES
    # -------------------------------------------------------------------------
    
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
    
    # -------------------------------------------------------------------------
    # AVAILABILITY
    # -------------------------------------------------------------------------
    
    available_days = models.JSONField("Available Days", default=list, blank=True)
    preferred_time_slots = models.JSONField("Preferred Time Slots", default=list, blank=True)
    
    # -------------------------------------------------------------------------
    # CLASS TEACHER ASSIGNMENT
    # -------------------------------------------------------------------------
    
    is_class_teacher = models.BooleanField("Is Class Teacher", default=False)
    assigned_classes = models.ManyToManyField(
        'academics.Class',
        blank=True,
        related_name='class_teachers'
    )
    
    # -------------------------------------------------------------------------
    # DIGITAL LITERACY
    # -------------------------------------------------------------------------
    
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
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Teacher"
        verbose_name_plural = "Teachers"
        ordering = ['staff__first_name', 'staff__last_name']
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.staff.full_name()} - Teacher"


# =============================================================================
# SALARY HISTORY
# =============================================================================

class SalaryHistory(BaseModel):
    """Track salary changes over time with period tracking"""
    
    CHANGE_TYPE_CHOICES = [
        ('INITIAL', 'Initial Salary'),
        ('INCREMENT', 'Salary Increment'),
        ('PROMOTION', 'Promotion'),
        ('ADJUSTMENT', 'Adjustment'),
        ('DEMOTION', 'Demotion'),
        ('CORRECTION', 'Correction'),
    ]
    
    # -------------------------------------------------------------------------
    # CORE RELATIONSHIPS
    # -------------------------------------------------------------------------
    
    staff = models.ForeignKey(
        Staff, 
        on_delete=models.CASCADE, 
        related_name='salary_history'
    )
    contract = models.ForeignKey(
        Contract, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='salary_changes'
    )
    
    # -------------------------------------------------------------------------
    # PERIOD TRACKING
    # -------------------------------------------------------------------------
    
    effective_period = models.ForeignKey(
        'core.FiscalPeriod',
        on_delete=models.PROTECT,
        related_name='salary_changes',
        help_text="Period when change becomes effective"
    )
    
    effective_date = models.DateField("Effective Date", db_index=True)
    
    # -------------------------------------------------------------------------
    # SALARY DETAILS
    # -------------------------------------------------------------------------
    
    previous_salary = models.DecimalField(
        "Previous Salary",
        max_digits=15, 
        decimal_places=2, 
        null=True, 
        blank=True
    )
    new_salary = models.DecimalField(
        "New Salary",
        max_digits=15, 
        decimal_places=2
    )
    
    # -------------------------------------------------------------------------
    # CHANGE DETAILS
    # -------------------------------------------------------------------------
    
    change_type = models.CharField(
        "Change Type",
        max_length=15, 
        choices=CHANGE_TYPE_CHOICES,
        db_index=True
    )
    change_percentage = models.DecimalField(
        "Change Percentage",
        max_digits=5, 
        decimal_places=2, 
        null=True, 
        blank=True
    )
    
    # -------------------------------------------------------------------------
    # APPROVAL
    # -------------------------------------------------------------------------
    
    reason = models.TextField("Reason")
    approved_by_id = models.CharField(
        "Approved By ID",
        max_length=50, 
        null=True, 
        blank=True
    )
    approved_at = models.DateTimeField("Approved At", null=True, blank=True)
    
    # -------------------------------------------------------------------------
    # REFERENCE DOCUMENT
    # -------------------------------------------------------------------------
    
    reference_document = models.FileField(
        "Reference Document",
        upload_to='hr/salary_changes/', 
        blank=True
    )
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Salary History"
        verbose_name_plural = "Salary Histories"
        ordering = ['-effective_date']
        indexes = [
            models.Index(fields=['staff', 'effective_period']),
            models.Index(fields=['effective_date']),
            models.Index(fields=['change_type']),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.staff.full_name()} - {self.get_change_type_display()} - {self.effective_date}"
    
    # -------------------------------------------------------------------------
    # PROPERTIES
    # -------------------------------------------------------------------------
    
    @property
    def fiscal_year(self):
        """Get fiscal year from effective period"""
        return self.effective_period.fiscal_year if self.effective_period else None
    
    @property
    def salary_increase(self):
        """Calculate salary increase amount"""
        if self.previous_salary:
            return self.new_salary - self.previous_salary
        return Decimal('0.00')


class ContractBenefit(BaseModel):
    """Benefits tied to employment contracts"""
    
    BENEFIT_TYPE_CHOICES = [
        ('HEALTH_INSURANCE', 'Health Insurance'),
        ('LIFE_INSURANCE', 'Life Insurance'),
        ('PENSION', 'Pension/Retirement'),
        ('VEHICLE', 'Company Vehicle'),
        ('HOUSING', 'Housing'),
        ('EDUCATION', 'Education Assistance'),
        ('GYM', 'Gym Membership'),
        ('MEAL', 'Meal Allowance'),
        ('TRANSPORT', 'Transport Allowance'),
        ('PHONE', 'Phone/Communication'),
        ('OTHER', 'Other Benefit'),
    ]
    
    # -------------------------------------------------------------------------
    # CORE RELATIONSHIPS
    # -------------------------------------------------------------------------
    
    contract = models.ForeignKey(
        Contract, 
        on_delete=models.CASCADE, 
        related_name='benefits'
    )
    benefit_type = models.CharField(
        "Benefit Type",
        max_length=20, 
        choices=BENEFIT_TYPE_CHOICES,
        db_index=True
    )
    description = models.CharField("Description", max_length=200)
    
    # -------------------------------------------------------------------------
    # VALUE
    # -------------------------------------------------------------------------
    
    monetary_value = models.DecimalField(
        "Monetary Value",
        max_digits=15, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Estimated monetary value of benefit"
    )
    
    # -------------------------------------------------------------------------
    # COVERAGE DETAILS
    # -------------------------------------------------------------------------
    
    coverage_details = models.TextField("Coverage Details", blank=True)
    provider = models.CharField("Provider", max_length=100, blank=True)
    policy_number = models.CharField("Policy Number", max_length=50, blank=True)
    
    # -------------------------------------------------------------------------
    # PERIOD
    # -------------------------------------------------------------------------
    
    start_date = models.DateField("Start Date")
    end_date = models.DateField("End Date", null=True, blank=True)
    
    is_active = models.BooleanField("Is Active", default=True, db_index=True)
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Contract Benefit"
        verbose_name_plural = "Contract Benefits"
        ordering = ['contract', 'benefit_type']
        indexes = [
            models.Index(fields=['contract', 'is_active']),
            models.Index(fields=['benefit_type']),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.contract.staff.full_name()} - {self.get_benefit_type_display()}"


# =============================================================================
# ATTENDANCE
# =============================================================================

class Attendance(BaseModel):
    """Staff attendance tracking"""
    
    STATUS_CHOICES = [
        ('PRESENT', 'Present'),
        ('ABSENT', 'Absent'),
        ('LATE', 'Late'),
        ('HALF_DAY', 'Half Day'),
        ('LEAVE', 'On Leave'),
        ('HOLIDAY', 'Holiday'),
        ('WEEKEND', 'Weekend'),
    ]
    
    WORK_MODE_CHOICES = [
        ('OFFICE', 'Office'),
        ('REMOTE', 'Remote'),
        ('HYBRID', 'Hybrid'),
        ('FIELD', 'Field Work'),
    ]
    
    # -------------------------------------------------------------------------
    # CORE RELATIONSHIPS
    # -------------------------------------------------------------------------
    
    staff = models.ForeignKey(
        Staff,
        on_delete=models.CASCADE,
        related_name='attendance_records'
    )
    
    # -------------------------------------------------------------------------
    # DATE AND TIME
    # -------------------------------------------------------------------------
    
    date = models.DateField("Date", db_index=True)
    
    check_in = models.DateTimeField("Check In", null=True, blank=True)
    check_out = models.DateTimeField("Check Out", null=True, blank=True)
    
    # -------------------------------------------------------------------------
    # STATUS
    # -------------------------------------------------------------------------
    
    status = models.CharField(
        "Status", 
        max_length=10, 
        choices=STATUS_CHOICES,
        db_index=True
    )
    
    # -------------------------------------------------------------------------
    # WORK HOURS
    # -------------------------------------------------------------------------
    
    work_hours = models.DecimalField(
        "Work Hours",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('24'))]
    )
    
    overtime_hours = models.DecimalField(
        "Overtime Hours",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0'))]
    )
    
    # -------------------------------------------------------------------------
    # WORK LOCATION
    # -------------------------------------------------------------------------
    
    work_location = models.CharField("Work Location", max_length=100, blank=True)
    work_mode = models.CharField(
        "Work Mode", 
        max_length=10, 
        choices=WORK_MODE_CHOICES, 
        blank=True
    )
    
    # -------------------------------------------------------------------------
    # NOTES
    # -------------------------------------------------------------------------
    
    notes = models.TextField("Notes", blank=True)
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Attendance"
        verbose_name_plural = "Attendance"
        unique_together = ['staff', 'date']
        ordering = ['-date', 'staff']
        indexes = [
            models.Index(fields=['staff', 'date']),
            models.Index(fields=['status']),
            models.Index(fields=['date']),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.staff.full_name()} - {self.date} - {self.get_status_display()}"
    
    # -------------------------------------------------------------------------
    # HELPER METHODS
    # -------------------------------------------------------------------------
    
    def calculate_work_hours(self):
        """Calculate work hours from check-in and check-out"""
        if self.check_in and self.check_out:
            duration = self.check_out - self.check_in
            hours = Decimal(str(duration.total_seconds() / 3600))
            self.work_hours = hours.quantize(Decimal('0.01'))
            self.save(update_fields=['work_hours', 'updated_at'])
            return self.work_hours
        return None


# =============================================================================
# PAYROLL
# =============================================================================

class Payroll(BaseModel):
    """Staff payroll processing"""
    
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('APPROVED', 'Approved'),
        ('PAID', 'Paid'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    # -------------------------------------------------------------------------
    # CORE RELATIONSHIPS
    # -------------------------------------------------------------------------
    
    staff = models.ForeignKey(
        Staff,
        on_delete=models.CASCADE,
        related_name='payrolls'
    )
    
    period = models.ForeignKey(
        'core.FiscalPeriod',
        on_delete=models.PROTECT,
        related_name='staff_payrolls',
        help_text="Payroll period"
    )
    
    # -------------------------------------------------------------------------
    # PERIOD DATES
    # -------------------------------------------------------------------------
    
    payment_date = models.DateField("Payment Date", db_index=True)
    
    fiscal_year = models.ForeignKey(
        'core.FiscalYear',
        on_delete=models.PROTECT,
        related_name='staff_payrolls',
        null=True,
        blank=True,
        help_text="Fiscal year (auto-populated from period)"
    )
    
    # -------------------------------------------------------------------------
    # SALARY COMPONENTS
    # -------------------------------------------------------------------------
    
    basic_salary = models.DecimalField(
        "Basic Salary",
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00')
    )
    
    gross_pay = models.DecimalField(
        "Gross Pay",
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00')
    )
    
    total_deductions = models.DecimalField(
        "Total Deductions",
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00')
    )
    
    net_pay = models.DecimalField(
        "Net Pay",
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00')
    )
    
    # -------------------------------------------------------------------------
    # PAYMENT DETAILS
    # -------------------------------------------------------------------------
    
    payment_method = models.ForeignKey(
        'core.PaymentMethod',
        on_delete=models.PROTECT,
        related_name='staff_payrolls',
        help_text="How the staff will be paid"
    )
    
    bank_account = models.CharField("Bank Account", max_length=100, blank=True)
    payment_reference = models.CharField("Payment Reference", max_length=100, blank=True)
    
    # -------------------------------------------------------------------------
    # STATUS
    # -------------------------------------------------------------------------
    
    status = models.CharField(
        "Status",
        max_length=10,
        choices=STATUS_CHOICES,
        default='DRAFT',
        db_index=True
    )
    
    approved_by_id = models.CharField(
        "Approved By ID",
        max_length=50, 
        null=True, 
        blank=True
    )
    approved_at = models.DateTimeField("Approved At", null=True, blank=True)
    
    # -------------------------------------------------------------------------
    # NOTES
    # -------------------------------------------------------------------------
    
    notes = models.TextField("Notes", blank=True)
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Payroll"
        verbose_name_plural = "Payrolls"
        unique_together = ['staff', 'period']
        ordering = ['-payment_date', 'staff']
        indexes = [
            models.Index(fields=['staff', 'period']),
            models.Index(fields=['payment_date']),
            models.Index(fields=['status']),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.staff.full_name()} - {self.period.name}"
    
    # -------------------------------------------------------------------------
    # SAVE METHOD
    # -------------------------------------------------------------------------
    
    def save(self, *args, **kwargs):
        """Auto-populate fiscal year from period"""
        if self.period and hasattr(self.period, 'fiscal_year'):
            self.fiscal_year = self.period.fiscal_year
        
        super().save(*args, **kwargs)
    
    # -------------------------------------------------------------------------
    # PROPERTIES
    # -------------------------------------------------------------------------
    
    @property
    def period_start(self):
        return self.period.start_date if self.period else None
    
    @property
    def period_end(self):
        return self.period.end_date if self.period else None
    
    # -------------------------------------------------------------------------
    # CALCULATION METHODS
    # -------------------------------------------------------------------------
    
    def calculate_gross_pay(self):
        """Calculate gross pay from basic salary and allowances"""
        total = self.basic_salary
        total += self.allowances.aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0.00')
        total += self.bonuses.aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0.00')
        
        self.gross_pay = total
        return self.gross_pay
    
    def calculate_total_deductions(self):
        """Calculate total deductions"""
        total = self.deductions.aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0.00')
        
        self.total_deductions = total
        return self.total_deductions
    
    def calculate_net_pay(self):
        """Calculate net pay"""
        self.net_pay = self.gross_pay - self.total_deductions
        return self.net_pay


class PayrollAllowance(BaseModel):
    """Payroll allowances"""
    
    TYPE_CHOICES = [
        ('HOUSING', 'Housing Allowance'),
        ('TRANSPORT', 'Transport Allowance'),
        ('MEAL', 'Meal Allowance'),
        ('MEDICAL', 'Medical Allowance'),
        ('EDUCATION', 'Education Allowance'),
        ('PHONE', 'Phone/Internet Allowance'),
        ('UNIFORM', 'Uniform Allowance'),
        ('OTHER', 'Other Allowance'),
    ]
    
    # -------------------------------------------------------------------------
    # CORE RELATIONSHIPS
    # -------------------------------------------------------------------------
    
    payroll = models.ForeignKey(
        Payroll, 
        on_delete=models.CASCADE, 
        related_name='allowances'
    )
    allowance_type = models.CharField(
        "Allowance Type", 
        max_length=15, 
        choices=TYPE_CHOICES,
        db_index=True
    )
    description = models.CharField("Description", max_length=100)
    amount = models.DecimalField(
        "Amount", 
        max_digits=15, 
        decimal_places=2
    )
    is_taxable = models.BooleanField("Is Taxable", default=True)
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Payroll Allowance"
        verbose_name_plural = "Payroll Allowances"
        ordering = ['allowance_type']
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.get_allowance_type_display()} - {self.amount}"


class PayrollDeduction(BaseModel):
    """Payroll deductions"""
    
    TYPE_CHOICES = [
        ('TAX', 'Tax Deduction'),
        ('PENSION', 'Pension Contribution'),
        ('INSURANCE', 'Insurance Premium'),
        ('LOAN', 'Loan Repayment'),
        ('ADVANCE', 'Salary Advance'),
        ('SOCIAL_SECURITY', 'Social Security'),
        ('HEALTHCARE', 'Healthcare Contribution'),
        ('OTHER', 'Other Deduction'),
    ]
    
    # -------------------------------------------------------------------------
    # CORE RELATIONSHIPS
    # -------------------------------------------------------------------------
    
    payroll = models.ForeignKey(
        Payroll, 
        on_delete=models.CASCADE, 
        related_name='deductions'
    )
    deduction_type = models.CharField(
        "Deduction Type", 
        max_length=15, 
        choices=TYPE_CHOICES,
        db_index=True
    )
    description = models.CharField("Description", max_length=100)
    amount = models.DecimalField(
        "Amount", 
        max_digits=15, 
        decimal_places=2
    )
    is_pretax = models.BooleanField("Is Pre-Tax", default=False)
    reference_number = models.CharField("Reference Number", max_length=50, blank=True)
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Payroll Deduction"
        verbose_name_plural = "Payroll Deductions"
        ordering = ['deduction_type']
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.get_deduction_type_display()} - {self.amount}"


class PayrollBonus(BaseModel):
    """Payroll bonuses and additional earnings"""
    
    TYPE_CHOICES = [
        ('OVERTIME', 'Overtime Pay'),
        ('PERFORMANCE', 'Performance Bonus'),
        ('COMMISSION', 'Sales Commission'),
        ('ANNUAL', 'Annual Bonus'),
        ('HOLIDAY', 'Holiday Bonus'),
        ('INCENTIVE', 'Incentive Pay'),
        ('OTHER', 'Other Bonus'),
    ]
    
    # -------------------------------------------------------------------------
    # CORE RELATIONSHIPS
    # -------------------------------------------------------------------------
    
    payroll = models.ForeignKey(
        Payroll, 
        on_delete=models.CASCADE, 
        related_name='bonuses'
    )
    bonus_type = models.CharField(
        "Bonus Type", 
        max_length=15, 
        choices=TYPE_CHOICES,
        db_index=True
    )
    description = models.CharField("Description", max_length=100)
    amount = models.DecimalField(
        "Amount", 
        max_digits=15, 
        decimal_places=2
    )
    is_taxable = models.BooleanField("Is Taxable", default=True)
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Payroll Bonus"
        verbose_name_plural = "Payroll Bonuses"
        ordering = ['bonus_type']
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.get_bonus_type_display()} - {self.amount}"