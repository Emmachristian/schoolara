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
from django.db.models import Q
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
    code = models.CharField("Department Code", max_length=20, unique=True, db_index=True)
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
        help_text="Period for basic_salary rate (e.g., 'per month', 'per hour')"
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

    is_active = models.BooleanField(
        "Active Status",
        default=True,
        help_text="Whether this teacher profile is currently active"
    )
    
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
    """
    Staff payroll processing with pay period tracking and reversal support.

    PAY PERIODS vs FISCAL PERIODS:
    - Pay Period: The time worked (e.g., Jan 1-31 for monthly salary)
    - Fiscal Period: Accounting period for reporting (e.g., Term 1 = Jan-Apr)
    - Multiple pay periods can exist within one fiscal period

    REVERSAL RULES:
    - Only draft or approved (not yet paid) payrolls can be reversed easily
    - Paid payrolls require special approval and statutory adjustments
    - Must be reversed in same fiscal period
    - Cannot reverse if period is closed
    - Reversal affects: allowances, deductions, bonuses, journal entries

    GROSS PAY BREAKDOWN:
        gross_pay = basic_salary + total_allowances + total_bonuses

    DEDUCTIONS BREAKDOWN:
        total_deductions = total_statutory_deductions + total_voluntary_deductions

    NET PAY:
        net_pay = gross_pay - total_deductions

    EMPLOYER COST:
        employer_total_cost = gross_pay + nssf_employer (+ any other employer contributions)
    """

    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('APPROVED', 'Approved'),
        ('PROCESSING', 'Processing Payment'),
        ('PAID', 'Paid'),
        ('REVERSED', 'Reversed'),
        ('CANCELLED', 'Cancelled'),
    ]

    PAY_FREQUENCY_CHOICES = [
        ('MONTHLY', 'Monthly'),
        ('WEEKLY', 'Weekly'),
        ('BIWEEKLY', 'Bi-Weekly'),
        ('SEMI_MONTHLY', 'Semi-Monthly'),
        ('QUARTERLY', 'Quarterly'),
    ]

    # =========================================================================
    # CORE RELATIONSHIPS
    # =========================================================================

    staff = models.ForeignKey(
        Staff,
        on_delete=models.CASCADE,
        related_name='payrolls',
        verbose_name="Staff Member"
    )

    fiscal_period = models.ForeignKey(
        'core.FiscalPeriod',
        on_delete=models.PROTECT,
        related_name='staff_payrolls',
        verbose_name="Fiscal Period",
        help_text="Fiscal period for accounting (may contain multiple monthly payrolls)"
    )

    payroll_number = models.CharField(
        "Payroll Number",
        max_length=30,
        unique=True,
        blank=True,
        db_index=True,
        help_text="Auto-generated payroll reference number (e.g. PAY/2025/12/0001)"
    )

    # =========================================================================
    # PAY PERIOD (What employee actually worked)
    # =========================================================================

    pay_period_start = models.DateField(
        "Pay Period Start",
        db_index=True,
        help_text="Start date of period being paid (e.g., Jan 1 for January salary)"
    )

    pay_period_end = models.DateField(
        "Pay Period End",
        db_index=True,
        help_text="End date of period being paid (e.g., Jan 31 for January salary)"
    )

    payment_date = models.DateField(
        "Payment Date",
        db_index=True,
        help_text="Date when salary is actually paid"
    )

    pay_frequency = models.CharField(
        "Pay Frequency",
        max_length=12,
        choices=PAY_FREQUENCY_CHOICES,
        default='MONTHLY',
        db_index=True,
        help_text=(
            "How often employee is paid (may differ from contract salary_frequency). "
            "E.g., monthly contract paid biweekly"
        )
    )

    pay_period_label = models.CharField(
        "Pay Period Label",
        max_length=50,
        blank=True,
        db_index=True,
        help_text="Display label (e.g., 'January 2024', 'Week 1 Feb 2024')"
    )

    # =========================================================================
    # SALARY COMPONENTS — EARNINGS
    # =========================================================================

    basic_salary = models.DecimalField(
        "Basic Salary",
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Basic salary for this pay period"
    )

    total_allowances = models.DecimalField(
        "Total Allowances",
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Sum of all PayrollAllowance entries for this pay period"
    )

    total_bonuses = models.DecimalField(
        "Total Bonuses",
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Sum of all PayrollBonus entries for this pay period"
    )

    gross_pay = models.DecimalField(
        "Gross Pay",
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="basic_salary + total_allowances + total_bonuses"
    )

    # =========================================================================
    # SALARY COMPONENTS — TAXABLE BASE
    # =========================================================================

    taxable_income = models.DecimalField(
        "Taxable Income",
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=(
            "Gross pay minus pre-tax deductions and non-taxable allowances. "
            "This is the base used to calculate PAYE."
        )
    )

    # =========================================================================
    # SALARY COMPONENTS — DEDUCTIONS
    # =========================================================================

    # --- Statutory ---

    paye_amount = models.DecimalField(
        "PAYE Amount",
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=(
            "Income tax (Pay As You Earn) withheld this period. "
            "Stored here for quick access on payslips and P9/P10 reports."
        )
    )

    nssf_employee = models.DecimalField(
        "NSSF Employee Contribution",
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Employee portion of NSSF contribution (deducted from gross pay)"
    )

    local_service_tax = models.DecimalField(
        "Local Service Tax",
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Local Service Tax (LST) deducted this period"
    )

    total_statutory_deductions = models.DecimalField(
        "Total Statutory Deductions",
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="PAYE + NSSF Employee + Local Service Tax (for compliance reporting)"
    )

    # --- Voluntary ---

    total_voluntary_deductions = models.DecimalField(
        "Total Voluntary Deductions",
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=(
            "All non-statutory deductions: loans, SACCO, insurance, "
            "pension contributions, union dues, etc."
        )
    )

    # --- Grand total ---

    total_deductions = models.DecimalField(
        "Total Deductions",
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="total_statutory_deductions + total_voluntary_deductions"
    )

    net_pay = models.DecimalField(
        "Net Pay",
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Amount actually paid to employee (gross_pay - total_deductions)"
    )

    # =========================================================================
    # EMPLOYER CONTRIBUTIONS (Cost to school, not deducted from employee)
    # =========================================================================

    nssf_employer = models.DecimalField(
        "NSSF Employer Contribution",
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=(
            "Employer's NSSF contribution. This is a cost to the school "
            "and does NOT appear in the employee's net pay calculation."
        )
    )

    employer_total_cost = models.DecimalField(
        "Total Employer Cost",
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=(
            "True cost of this employee to the school for this period: "
            "gross_pay + nssf_employer + any other employer contributions. "
            "Use this for budget and cost-of-employment reporting."
        )
    )

    # =========================================================================
    # CURRENCY
    # =========================================================================

    currency = models.CharField(
        "Currency",
        max_length=3,
        default='UGX',
        help_text="ISO 4217 currency code (e.g., UGX, USD, KES)"
    )

    exchange_rate = models.DecimalField(
        "Exchange Rate",
        max_digits=10,
        decimal_places=6,
        default=Decimal('1.000000'),
        help_text=(
            "Exchange rate to base currency (UGX) at time of payment. "
            "Use 1.000000 for UGX payrolls."
        )
    )

    # =========================================================================
    # WORKING DAYS TRACKING
    # =========================================================================

    total_working_days = models.PositiveIntegerField(
        "Total Working Days",
        null=True,
        blank=True,
        help_text="Total working days in pay period"
    )

    days_worked = models.PositiveIntegerField(
        "Days Worked",
        null=True,
        blank=True,
        help_text="Actual days worked (for prorated salary)"
    )

    is_prorated = models.BooleanField(
        "Is Prorated",
        default=False,
        help_text="Whether salary is prorated (partial month/period)"
    )

    # =========================================================================
    # PAYMENT DETAILS
    # =========================================================================

    payment_method = models.ForeignKey(
        'core.PaymentMethod',
        on_delete=models.PROTECT,
        related_name='staff_payrolls',
        verbose_name="Payment Method",
        help_text="How the staff will be paid"
    )

    bank_account = models.CharField(
        "Bank Account",
        max_length=100,
        blank=True,
        help_text="Bank account number for payment"
    )

    payment_reference = models.CharField(
        "Payment Reference",
        max_length=100,
        blank=True,
        help_text="Bank transfer reference or check number"
    )

    # =========================================================================
    # STATUS AND APPROVAL
    # =========================================================================

    status = models.CharField(
        "Status",
        max_length=12,
        choices=STATUS_CHOICES,
        default='DRAFT',
        db_index=True
    )

    approved_by_id = models.CharField(
        "Approved By ID",
        max_length=50,
        null=True,
        blank=True,
        help_text="HR Manager who approved payroll"
    )

    approved_at = models.DateTimeField(
        "Approved At",
        null=True,
        blank=True
    )

    paid_by_id = models.CharField(
        "Paid By ID",
        max_length=50,
        null=True,
        blank=True,
        help_text="User who processed payment"
    )

    paid_at = models.DateTimeField(
        "Paid At",
        null=True,
        blank=True
    )

    # =========================================================================
    # REVERSAL TRACKING
    # =========================================================================

    reversed = models.BooleanField(
        "Reversed",
        default=False,
        db_index=True,
        help_text=(
            "Payroll was reversed due to error in calculation, wrong employee, "
            "or incorrect amounts. Employee was NOT actually paid or payment was recovered."
        )
    )

    reversed_on = models.DateTimeField(
        "Reversed On",
        null=True,
        blank=True,
        help_text="When this payroll was reversed"
    )

    reversed_by_id = models.CharField(
        "Reversed By ID",
        max_length=50,
        null=True,
        blank=True,
        help_text="User who initiated reversal"
    )

    reversal_reason = models.TextField(
        "Reversal Reason",
        blank=True,
        help_text=(
            "Detailed reason for reversal. Examples: "
            "'Incorrect salary amount calculated', 'Wrong deductions applied', "
            "'Payroll generated for terminated employee', 'Duplicate payroll entry'"
        )
    )

    # Special approval for paid payrolls
    reversal_approved_by_id = models.CharField(
        "Reversal Approved By ID",
        max_length=50,
        null=True,
        blank=True,
        help_text="Finance Director/HR Director who approved reversal of PAID payroll"
    )

    reversal_approved_on = models.DateTimeField(
        "Reversal Approved On",
        null=True,
        blank=True
    )

    # Statutory implications
    statutory_reversals_required = models.BooleanField(
        "Statutory Reversals Required",
        default=False,
        help_text="Whether tax/NSSF filings need to be adjusted due to reversal"
    )

    statutory_adjustments_notes = models.TextField(
        "Statutory Adjustments Notes",
        blank=True,
        help_text="Details of tax/NSSF adjustments needed for this reversal"
    )

    # Journal entry for reversal
    reversal_journal_entry = models.ForeignKey(
        'finance.JournalEntry',
        verbose_name="Reversal Journal Entry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reversed_payrolls',
        help_text="Journal entry created when payroll was reversed"
    )

    # =========================================================================
    # JOURNAL ENTRY INTEGRATION
    # =========================================================================

    journal_entry = models.ForeignKey(
        'finance.JournalEntry',
        verbose_name="Journal Entry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payrolls',
        help_text="Journal entry for payroll expense (accrual)"
    )

    payment_journal_entry = models.ForeignKey(
        'finance.JournalEntry',
        verbose_name="Payment Journal Entry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payroll_payments',
        help_text="Journal entry when salary was actually paid"
    )

    auto_create_journal_entry = models.BooleanField(
        "Auto-Create Journal Entry",
        default=True,
        help_text="Automatically create journal entries for this payroll"
    )

    # =========================================================================
    # NOTES
    # =========================================================================

    notes = models.TextField(
        "Notes",
        blank=True,
        help_text="Additional notes about this payroll"
    )

    # =========================================================================
    # META CLASS
    # =========================================================================

    class Meta:
        verbose_name = "Payroll"
        verbose_name_plural = "Payrolls"
        ordering = ['-payment_date', 'staff']

        constraints = [
            # Prevent duplicate payrolls for same staff and pay period
            models.UniqueConstraint(
                fields=['staff', 'pay_period_start', 'pay_period_end'],
                name='unique_staff_pay_period',
                condition=models.Q(reversed=False)  # Exclude reversed payrolls
            ),
            # Ensure pay period is valid
            models.CheckConstraint(
                check=models.Q(pay_period_start__lt=models.F('pay_period_end')),
                name='payroll_pay_period_start_before_end'
            ),
            # Ensure amounts are non-negative
            models.CheckConstraint(
                check=models.Q(gross_pay__gte=0),
                name='payroll_gross_pay_non_negative'
            ),
            models.CheckConstraint(
                check=models.Q(net_pay__gte=0),
                name='payroll_net_pay_non_negative'
            ),
            models.CheckConstraint(
                check=models.Q(total_allowances__gte=0),
                name='payroll_total_allowances_non_negative'
            ),
            models.CheckConstraint(
                check=models.Q(total_bonuses__gte=0),
                name='payroll_total_bonuses_non_negative'
            ),
            models.CheckConstraint(
                check=models.Q(total_deductions__gte=0),
                name='payroll_total_deductions_non_negative'
            ),
            models.CheckConstraint(
                check=models.Q(total_statutory_deductions__gte=0),
                name='payroll_statutory_deductions_non_negative'
            ),
            models.CheckConstraint(
                check=models.Q(total_voluntary_deductions__gte=0),
                name='payroll_voluntary_deductions_non_negative'
            ),
            models.CheckConstraint(
                check=models.Q(nssf_employer__gte=0),
                name='payroll_nssf_employer_non_negative'
            ),
            models.CheckConstraint(
                check=models.Q(employer_total_cost__gte=0),
                name='payroll_employer_total_cost_non_negative'
            ),
        ]

        indexes = [
            models.Index(fields=['staff', 'fiscal_period']),
            models.Index(fields=['staff', 'pay_period_start', 'pay_period_end']),
            models.Index(fields=['fiscal_period', 'status']),
            models.Index(fields=['payment_date']),
            models.Index(fields=['status']),
            models.Index(fields=['reversed']),
            models.Index(fields=['reversed_on']),
            models.Index(fields=['statutory_reversals_required']),
            models.Index(fields=['pay_frequency']),
            models.Index(fields=['pay_period_label']),
            models.Index(fields=['currency']),
        ]

    # =========================================================================
    # STRING REPRESENTATION
    # =========================================================================

    def __str__(self):
        state_suffix = ""
        if self.reversed:
            state_suffix = " [REVERSED]"
        elif self.status == 'CANCELLED':
            state_suffix = " [CANCELLED]"

        label = self.pay_period_label or f"{self.pay_period_start} to {self.pay_period_end}"
        return f"{self.staff.full_name()} - {label}{state_suffix}"

    # =========================================================================
    # VALIDATION
    # =========================================================================

    def clean(self):
        """Validate payroll data"""
        super().clean()
        errors = {}

        # =====================================================================
        # PAY PERIOD VALIDATION
        # =====================================================================

        if self.pay_period_start and self.pay_period_end:
            if self.pay_period_end < self.pay_period_start:
                errors['pay_period_end'] = "Pay period end cannot be before start"

        # =====================================================================
        # FISCAL PERIOD VALIDATION
        # =====================================================================

        if self.fiscal_period:
            if self.pay_period_start and self.pay_period_start < self.fiscal_period.start_date:
                errors['pay_period_start'] = (
                    f"Pay period cannot start before fiscal period start date "
                    f"({self.fiscal_period.start_date})"
                )

            if self.pay_period_end and self.pay_period_end > self.fiscal_period.end_date:
                errors['pay_period_end'] = (
                    f"Pay period cannot end after fiscal period end date "
                    f"({self.fiscal_period.end_date})"
                )

            if self.payment_date:
                if self.payment_date < self.fiscal_period.start_date:
                    errors['payment_date'] = (
                        f"Payment date cannot be before fiscal period start "
                        f"({self.fiscal_period.start_date})"
                    )

                from datetime import timedelta
                max_allowed_date = self.fiscal_period.end_date

                if hasattr(self.fiscal_period, 'grace_period_days') and self.fiscal_period.grace_period_days > 0:
                    max_allowed_date = (
                        self.fiscal_period.end_date +
                        timedelta(days=self.fiscal_period.grace_period_days)
                    )

                if self.payment_date > max_allowed_date:
                    grace_note = ""
                    if hasattr(self.fiscal_period, 'grace_period_days') and self.fiscal_period.grace_period_days > 0:
                        grace_note = f" (including {self.fiscal_period.grace_period_days} days grace period)"

                    errors['payment_date'] = (
                        f"Payment date cannot be after fiscal period end date "
                        f"({self.fiscal_period.end_date}){grace_note}"
                    )

            if hasattr(self.fiscal_period, 'is_closed') and self.fiscal_period.is_closed:
                if not self.pk:
                    errors['fiscal_period'] = "Cannot create payroll in a closed fiscal period"
                elif not self.reversed and self.status != 'CANCELLED':
                    errors['fiscal_period'] = "Cannot modify active payroll in a closed fiscal period"

        # =====================================================================
        # PAYMENT DATE LOGIC
        # =====================================================================

        if self.payment_date and self.pay_period_start:
            if self.payment_date < self.pay_period_start:
                errors['payment_date'] = "Payment date should not be before pay period starts"

        # =====================================================================
        # REVERSAL VALIDATION
        # =====================================================================

        if self.reversed and not self.reversal_reason:
            errors['reversal_reason'] = "Reversal reason is required"

        if self.reversed and self.status == 'PAID':
            if not self.reversal_approved_by_id:
                errors['reversal_approved_by_id'] = (
                    "Finance/HR Director approval required to reverse paid payroll"
                )

        if self.reversed and self.status == 'CANCELLED':
            errors['reversed'] = "Cannot reverse a cancelled payroll"

        # =====================================================================
        # WORKING DAYS VALIDATION
        # =====================================================================

        if self.days_worked is not None and self.total_working_days is not None:
            if self.days_worked > self.total_working_days:
                errors['days_worked'] = "Days worked cannot exceed total working days"

        # =====================================================================
        # AMOUNT CONSISTENCY VALIDATION
        #
        # ⭐ ONLY validates on EXISTING payrolls with a calculated gross_pay.
        #    For NEW payrolls, amounts are 0.00 at clean() time — signals and
        #    recalculate_all() run AFTER the initial save, so there is nothing
        #    meaningful to check yet.
        #
        # ⭐ All errors here use '__all__' (NON_FIELD_ERRORS) rather than field
        #    names like 'gross_pay' or 'total_deductions'. These are calculated
        #    fields intentionally excluded from PayrollForm. If Django tries to
        #    attach a ValidationError to a field that doesn't exist on the form,
        #    it raises a hard ValueError crash — even if the model field exists.
        # =====================================================================

        if self.pk and self.gross_pay > Decimal('0.00'):

            # --- Net pay sanity check ---
            if self.net_pay > self.gross_pay:
                errors.setdefault('__all__', []).append(
                    f"Net pay ({self.net_pay}) cannot be greater than "
                    f"gross pay ({self.gross_pay})."
                )

            # --- Gross pay breakdown consistency ---
            # gross_pay must equal basic_salary + total_allowances + total_bonuses
            expected_gross = self.basic_salary + self.total_allowances + self.total_bonuses
            if abs(expected_gross - self.gross_pay) > Decimal('0.01'):
                errors.setdefault('__all__', []).append(
                    f"Gross pay ({self.gross_pay}) is inconsistent: "
                    f"basic salary ({self.basic_salary}) + allowances "
                    f"({self.total_allowances}) + bonuses ({self.total_bonuses}) "
                    f"= {expected_gross}. Please recalculate."
                )

            # --- Deductions breakdown consistency ---
            # total_deductions must equal statutory + voluntary
            expected_deductions = (
                self.total_statutory_deductions + self.total_voluntary_deductions
            )
            if abs(expected_deductions - self.total_deductions) > Decimal('0.01'):
                errors.setdefault('__all__', []).append(
                    f"Total deductions ({self.total_deductions}) is inconsistent: "
                    f"statutory ({self.total_statutory_deductions}) + voluntary "
                    f"({self.total_voluntary_deductions}) = {expected_deductions}. "
                    f"Please recalculate."
                )

        if errors:
            raise ValidationError(errors)

    # =========================================================================
    # SAVE METHOD
    # =========================================================================

    def save(self, *args, **kwargs):
        """Auto-populate fields before saving"""

        # Auto-assign fiscal period if not set
        if not self.fiscal_period_id and self.pay_period_start and self.pay_period_end:
            self.fiscal_period = self.get_applicable_fiscal_period()

        # Auto-generate pay period label if not set
        if not self.pay_period_label and self.pay_period_start:
            if self.pay_frequency == 'MONTHLY':
                self.pay_period_label = self.pay_period_start.strftime('%B %Y')
            elif self.pay_frequency == 'WEEKLY':
                self.pay_period_label = (
                    f"Week of {self.pay_period_start.strftime('%b %d, %Y')}"
                )
            else:
                self.pay_period_label = (
                    f"{self.pay_period_start.strftime('%b %d')} - "
                    f"{self.pay_period_end.strftime('%b %d, %Y')}"
                )

        # Auto-detect if statutory adjustments needed on reversal
        if self.reversed and not self.statutory_reversals_required:
            self.statutory_reversals_required = self.requires_statutory_adjustments()

        super().save(*args, **kwargs)

    # =========================================================================
    # HELPER METHODS — FISCAL PERIOD
    # =========================================================================

    def get_applicable_fiscal_period(self):
        """
        Find the correct fiscal period for this payroll based on pay period dates.

        Returns:
            FiscalPeriod: The fiscal period this payroll should belong to

        Raises:
            ValidationError: If no suitable fiscal period is found
        """
        from core.models import FiscalPeriod

        fiscal_period = FiscalPeriod.objects.filter(
            start_date__lte=self.pay_period_start,
            end_date__gte=self.pay_period_end,
            is_active=True
        ).first()

        if not fiscal_period:
            raise ValidationError(
                f"No active fiscal period found for pay period "
                f"{self.pay_period_start} to {self.pay_period_end}. "
                f"Please create or activate the appropriate fiscal period first."
            )

        return fiscal_period

    # =========================================================================
    # BACKWARD COMPATIBILITY PROPERTIES
    # =========================================================================

    @property
    def period_start(self):
        """Alias for backwards compatibility"""
        return self.pay_period_start

    @property
    def period_end(self):
        """Alias for backwards compatibility"""
        return self.pay_period_end

    # =========================================================================
    # STATUS PROPERTIES
    # =========================================================================

    @property
    def is_active(self):
        """Check if payroll is still active (not reversed/cancelled)"""
        return not self.reversed and self.status != 'CANCELLED'

    @property
    def effective_net_pay(self):
        """Get effective net pay (0 if reversed or cancelled)"""
        if not self.is_active:
            return Decimal('0.00')
        return self.net_pay

    @property
    def effective_gross_pay(self):
        """Get effective gross pay (0 if reversed or cancelled)"""
        if not self.is_active:
            return Decimal('0.00')
        return self.gross_pay

    @property
    def effective_employer_cost(self):
        """Get effective employer cost (0 if reversed or cancelled)"""
        if not self.is_active:
            return Decimal('0.00')
        return self.employer_total_cost

    @property
    def payroll_state(self):
        """Get human-readable payroll state"""
        if self.reversed:
            return "REVERSED"
        return self.status

    # =========================================================================
    # REVERSAL CHECK METHODS
    # =========================================================================

    def can_be_reversed(self):
        """
        Check if this payroll can be reversed.

        Returns:
            tuple: (can_reverse: bool, reason: str)
        """
        if self.reversed:
            return False, "Payroll already reversed"

        if self.status == 'CANCELLED':
            return False, "Cannot reverse a cancelled payroll"

        if self.fiscal_period and hasattr(self.fiscal_period, 'is_closed'):
            if self.fiscal_period.is_closed:
                return False, "Cannot reverse payroll from closed fiscal period"

        if self.status == 'PAID':
            if not self.reversal_approved_by_id:
                return False, "Reversal of paid payroll requires Finance/HR Director approval"

            if self.statutory_reversals_required and not self.statutory_adjustments_notes:
                return False, "Statutory adjustment plan required for paid payroll reversal"

        return True, "OK"

    def requires_statutory_adjustments(self):
        """
        Check if reversal requires statutory adjustments (tax, NSSF filings).

        Returns:
            bool: True if adjustments needed
        """
        if self.status == 'PAID':
            has_statutory = self.deductions.filter(
                deduction_type__in=['PAYE', 'SOCIAL_SECURITY', 'LOCAL_TAX']
            ).exists()
            return has_statutory

        return False

    # =========================================================================
    # USER RETRIEVAL HELPERS
    # =========================================================================

    def get_approved_by_user(self):
        """Get user who approved payroll"""
        if not self.approved_by_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            return User.objects.using('default').get(id=self.approved_by_id)
        except Exception as e:
            logger.error(f"Error fetching approved_by user: {e}")
            return None

    def get_paid_by_user(self):
        """Get user who processed payment"""
        if not self.paid_by_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            return User.objects.using('default').get(id=self.paid_by_id)
        except Exception as e:
            logger.error(f"Error fetching paid_by user: {e}")
            return None

    def get_reversed_by_user(self):
        """Get user who reversed payroll"""
        if not self.reversed_by_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            return User.objects.using('default').get(id=self.reversed_by_id)
        except Exception as e:
            logger.error(f"Error fetching reversed_by user: {e}")
            return None

    def get_reversal_approved_by_user(self):
        """Get user who approved reversal"""
        if not self.reversal_approved_by_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            return User.objects.using('default').get(id=self.reversal_approved_by_id)
        except Exception as e:
            logger.error(f"Error fetching reversal_approved_by user: {e}")
            return None

    # =========================================================================
    # CALCULATION METHODS
    # =========================================================================

    def calculate_gross_pay(self):
        """
        Calculate gross pay from basic salary, allowances, and bonuses.
        Also updates total_allowances and total_bonuses summary fields.

        Returns:
            Decimal: Updated gross pay amount
        """
        self.total_allowances = self.allowances.aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0.00')

        self.total_bonuses = self.bonuses.aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0.00')

        self.gross_pay = self.basic_salary + self.total_allowances + self.total_bonuses
        return self.gross_pay

    def calculate_taxable_income(self):
        """
        Calculate taxable income for PAYE purposes.

        Taxable income = Gross pay
            - pre-tax deductions (pension, provident fund, etc.)
            - non-taxable allowances

        Returns:
            Decimal: Updated taxable income
        """
        # Subtract pre-tax deductions
        pretax_deductions = self.deductions.filter(
            is_pretax=True
        ).aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0.00')

        # Subtract non-taxable allowances
        non_taxable_allowances = self.allowances.filter(
            is_taxable=False
        ).aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0.00')

        self.taxable_income = max(
            self.gross_pay - pretax_deductions - non_taxable_allowances,
            Decimal('0.00')
        )
        return self.taxable_income

    def calculate_total_deductions(self):
        """
        Calculate total deductions, broken down into statutory and voluntary.
        Also updates paye_amount, nssf_employee, and local_service_tax fields.

        Returns:
            Decimal: Updated total deductions amount
        """
        STATUTORY_TYPES = ['PAYE', 'SOCIAL_SECURITY', 'LOCAL_TAX']

        all_deductions = self.deductions.values('deduction_type', 'amount')

        statutory_total = Decimal('0.00')
        voluntary_total = Decimal('0.00')
        paye_total = Decimal('0.00')
        nssf_employee_total = Decimal('0.00')
        lst_total = Decimal('0.00')

        for deduction in all_deductions:
            amount = deduction['amount']
            dtype = deduction['deduction_type']

            if dtype in STATUTORY_TYPES:
                statutory_total += amount
                if dtype == 'PAYE':
                    paye_total += amount
                elif dtype == 'SOCIAL_SECURITY':
                    nssf_employee_total += amount
                elif dtype == 'LOCAL_TAX':
                    lst_total += amount
            else:
                voluntary_total += amount

        self.total_statutory_deductions = statutory_total
        self.total_voluntary_deductions = voluntary_total
        self.total_deductions = statutory_total + voluntary_total
        self.paye_amount = paye_total
        self.nssf_employee = nssf_employee_total
        self.local_service_tax = lst_total

        return self.total_deductions

    def calculate_net_pay(self):
        """
        Calculate net pay (gross pay - total deductions).

        Returns:
            Decimal: Updated net pay amount
        """
        self.net_pay = max(
            self.gross_pay - self.total_deductions,
            Decimal('0.00')
        )
        return self.net_pay

    def calculate_employer_cost(self):
        """
        Calculate total cost of this employee to the school.
        employer_total_cost = gross_pay + nssf_employer

        Returns:
            Decimal: Updated employer total cost
        """
        self.employer_total_cost = self.gross_pay + self.nssf_employer
        return self.employer_total_cost

    def recalculate_all(self):
        """
        Recalculate all amounts in the correct order:
            1. Gross pay (basic + allowances + bonuses)
            2. Taxable income (gross - pre-tax items)
            3. Deductions (statutory + voluntary breakdown)
            4. Net pay (gross - deductions)
            5. Employer cost (gross + employer contributions)

        Returns:
            dict: Dictionary with all updated amounts
        """
        self.calculate_gross_pay()
        self.calculate_taxable_income()
        self.calculate_total_deductions()
        self.calculate_net_pay()
        self.calculate_employer_cost()

        return {
            'basic_salary': self.basic_salary,
            'total_allowances': self.total_allowances,
            'total_bonuses': self.total_bonuses,
            'gross_pay': self.gross_pay,
            'taxable_income': self.taxable_income,
            'paye_amount': self.paye_amount,
            'nssf_employee': self.nssf_employee,
            'local_service_tax': self.local_service_tax,
            'total_statutory_deductions': self.total_statutory_deductions,
            'total_voluntary_deductions': self.total_voluntary_deductions,
            'total_deductions': self.total_deductions,
            'net_pay': self.net_pay,
            'nssf_employer': self.nssf_employer,
            'employer_total_cost': self.employer_total_cost,
        }

    # =========================================================================
    # PRORATION METHODS
    # =========================================================================

    def calculate_prorated_salary(self, days_worked=None, total_days=None):
        """
        Calculate prorated salary based on days worked.

        Args:
            days_worked: Days actually worked (uses self.days_worked if not provided)
            total_days: Total working days in period (uses self.total_working_days if not provided)

        Returns:
            Decimal: Prorated basic salary
        """
        days_worked = days_worked or self.days_worked
        total_days = total_days or self.total_working_days

        if not days_worked or not total_days or total_days == 0:
            return self.basic_salary

        contract = Contract.get_staff_active_contract(self.staff)
        if not contract:
            return Decimal('0.00')

        base_salary = contract.basic_salary
        proration_factor = Decimal(str(days_worked)) / Decimal(str(total_days))
        prorated_salary = base_salary * proration_factor

        return prorated_salary.quantize(Decimal('0.01'))

    def apply_proration(self, days_worked, total_days):
        """
        Apply proration to this payroll.

        Args:
            days_worked: Days actually worked
            total_days: Total working days in period
        """
        self.days_worked = days_worked
        self.total_working_days = total_days
        self.is_prorated = True
        self.basic_salary = self.calculate_prorated_salary(days_worked, total_days)
        self.save()

    # =========================================================================
    # ACCOUNT MAPPING HELPERS
    # =========================================================================

    def _get_payroll_mappings(self):
        """Internal helper to retrieve payroll account mappings."""
        from core.models import FinancialSettings
        settings = FinancialSettings.get_instance()
        if not settings:
            return None
        return getattr(settings, 'payroll_account_mappings', None)

    def get_salary_expense_account(self):
        """Get salary expense account from mappings"""
        mappings = self._get_payroll_mappings()
        return getattr(mappings, 'salaries_expense_account', None) if mappings else None

    def get_salary_payable_account(self):
        """Get wages payable account from mappings"""
        mappings = self._get_payroll_mappings()
        return getattr(mappings, 'wages_payable_account', None) if mappings else None

    def get_cash_account(self):
        """Get cash/bank account for salary payment"""
        from core.models import FinancialSettings
        settings = FinancialSettings.get_instance()
        if not settings:
            return None
        mappings = settings.get_account_mappings()
        return mappings.get_cash_or_bank_account(self.payment_method)

    def get_deduction_account(self, deduction_type):
        """Get payable account for a specific deduction type"""
        mappings = self._get_payroll_mappings()
        if not mappings:
            return None

        deduction_account_map = {
            'PAYE': getattr(mappings, 'payroll_tax_payable_account', None),
            'SOCIAL_SECURITY': getattr(mappings, 'social_security_payable_account', None),
            'PENSION': getattr(mappings, 'pension_payable_account', None),
        }
        return deduction_account_map.get(deduction_type)

    def get_allowance_expense_account(self, allowance_type):
        """Get expense account for a specific allowance type"""
        mappings = self._get_payroll_mappings()
        if not mappings:
            return None

        allowance_account_map = {
            'HOUSING': getattr(mappings, 'housing_allowance_expense_account', None),
            'TRANSPORT': getattr(mappings, 'transport_allowance_expense_account', None),
            'MEDICAL': getattr(mappings, 'medical_allowance_expense_account', None),
            'OVERTIME': getattr(mappings, 'overtime_expense_account', None),
        }

        account = allowance_account_map.get(allowance_type)
        if account:
            return account

        # Fallback to general allowance account
        return getattr(mappings, 'general_allowance_expense_account', None)

    # =========================================================================
    # CLASS METHODS
    # =========================================================================

    @classmethod
    def get_staff_payrolls_for_period(cls, staff, fiscal_period):
        """
        Get all active payrolls for a staff member in a fiscal period.

        Args:
            staff: Staff instance
            fiscal_period: FiscalPeriod instance

        Returns:
            QuerySet: Payroll queryset ordered by pay period start
        """
        return cls.objects.filter(
            staff=staff,
            fiscal_period=fiscal_period,
            reversed=False
        ).order_by('pay_period_start')

    @classmethod
    def get_staff_payroll_for_month(cls, staff, year, month):
        """
        Get payroll for a specific month.

        Args:
            staff: Staff instance
            year: Year (int)
            month: Month (int, 1-12)

        Returns:
            Payroll or None
        """
        from datetime import date
        start_of_month = date(year, month, 1)

        return cls.objects.filter(
            staff=staff,
            pay_period_start__lte=start_of_month,
            pay_period_end__gte=start_of_month,
            reversed=False
        ).first()

    @classmethod
    def get_pending_payrolls(cls):
        """Get all payrolls pending approval"""
        return cls.objects.filter(
            status='DRAFT',
            reversed=False
        ).order_by('payment_date')

    @classmethod
    def get_approved_unpaid_payrolls(cls):
        """Get all approved but unpaid payrolls"""
        return cls.objects.filter(
            status='APPROVED',
            reversed=False
        ).order_by('payment_date')


class PayrollAllowance(BaseModel):
    """
    Payroll allowances linked to specific payroll records.
    
    Note: When parent payroll is reversed, these allowances remain for audit trail
    but are considered inactive (use payroll.is_active to check).
    """
    
    TYPE_CHOICES = [
        ('HOUSING', 'Housing Allowance'),
        ('TRANSPORT', 'Transport Allowance'),
        ('MEAL', 'Meal Allowance'),
        ('MEDICAL', 'Medical Allowance'),
        ('UTILITY', 'Utility Allowance'),
        ('PHONE', 'Phone Allowance'),
        ('INTERNET', 'Internet Allowance'),
        ('EDUCATION', 'Education Allowance'),
        ('BOOKS', 'Books Allowance'),
        ('RESPONSIBILITY', 'Responsibility Allowance'),
        ('OVERTIME', 'Overtime Allowance'),
        ('ACTING', 'Acting Allowance'),
        ('HARDSHIP', 'Hardship Allowance'),
        ('TRAVEL', 'Travel Allowance'),
        ('PER_DIEM', 'Per Diem Allowance'),
        ('UNIFORM', 'Uniform Allowance'),
        ('BONUS', 'Bonus'),
        ('OTHER', 'Other Allowance'),
    ]
    
    # -------------------------------------------------------------------------
    # CORE RELATIONSHIPS
    # -------------------------------------------------------------------------
    
    payroll = models.ForeignKey(
        Payroll, 
        on_delete=models.CASCADE, 
        related_name='allowances',
        verbose_name="Payroll"
    )
    
    allowance_type = models.CharField(
        "Allowance Type", 
        max_length=20,  # ⭐ CHANGED: Increased from 15 to 20
        choices=TYPE_CHOICES,
        db_index=True
    )
    
    description = models.CharField(
        "Description", 
        max_length=200,  # ⭐ CHANGED: Increased from 100 to 200
        help_text="Detailed description of this allowance"
    )
    
    amount = models.DecimalField(
        "Amount", 
        max_digits=15, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],  # ⭐ ADDED: Ensure non-negative
        help_text="Allowance amount for this pay period"
    )
    
    is_taxable = models.BooleanField(
        "Is Taxable", 
        default=True,
        help_text="Whether this allowance is subject to income tax"
    )
    
    # ⭐ OPTIONAL: Add for better tracking
    is_recurring = models.BooleanField(
        "Is Recurring",
        default=False,
        help_text="Whether this allowance recurs every pay period"
    )
    
    reference_number = models.CharField(
        "Reference Number",
        max_length=50,
        blank=True,
        help_text="External reference (e.g., approval number, policy reference)"
    )
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Payroll Allowance"
        verbose_name_plural = "Payroll Allowances"
        ordering = ['allowance_type', 'description']
        indexes = [
            models.Index(fields=['payroll', 'allowance_type']),
            models.Index(fields=['allowance_type']),
            models.Index(fields=['is_taxable']),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount__gte=0),
                name='payroll_allowance_amount_non_negative'
            ),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.get_allowance_type_display()} - {self.amount}"
    
    # -------------------------------------------------------------------------
    # PROPERTIES
    # -------------------------------------------------------------------------
    
    @property
    def is_active(self):
        """Check if this allowance is active (payroll not reversed)"""
        return self.payroll.is_active if self.payroll else False
    
    @property
    def effective_amount(self):
        """Get effective amount (0 if payroll reversed)"""
        if not self.is_active:
            return Decimal('0.00')
        return self.amount


class PayrollDeduction(BaseModel):
    """
    Payroll deductions linked to specific payroll records.
    
    Note: When parent payroll is reversed, these deductions remain for audit trail
    but are considered inactive (use payroll.is_active to check).
    """
    
    TYPE_CHOICES = [
        # Statutory
        ('PAYE', 'PAYE / Income Tax'),
        ('SOCIAL_SECURITY', 'Social Security (NSSF)'),
        ('LOCAL_TAX', 'Local Service Tax'),

        # Retirement
        ('PENSION', 'Pension Contribution'),
        ('PROVIDENT_FUND', 'Provident Fund'),

        # Healthcare & Insurance
        ('HEALTHCARE', 'Healthcare Contribution'),
        ('INSURANCE', 'Insurance Premium'),

        # Loans & SACCO
        ('LOAN', 'Loan Repayment'),
        ('ADVANCE', 'Salary Advance'),
        ('SACCO_LOAN', 'SACCO Loan Repayment'),
        ('SAVINGS', 'SACCO Savings'),

        # Union & Welfare
        ('UNION', 'Union Dues'),
        ('WELFARE', 'Staff Welfare Contribution'),
        ('FUNERAL', 'Funeral Fund'),

        # Recoveries & Discipline
        ('RECOVERY', 'Expense Recovery'),
        ('FINE', 'Disciplinary Fine'),

        # Time-based
        ('ABSENCE', 'Absence Deduction'),
        ('LATE', 'Late Coming Deduction'),

        ('OTHER', 'Other Deduction'),
    ]
    
    # Statutory deduction types (for easy filtering)
    STATUTORY_TYPES = ['PAYE', 'SOCIAL_SECURITY', 'LOCAL_TAX']
    
    # -------------------------------------------------------------------------
    # CORE RELATIONSHIPS
    # -------------------------------------------------------------------------
    
    payroll = models.ForeignKey(
        Payroll, 
        on_delete=models.CASCADE, 
        related_name='deductions',
        verbose_name="Payroll"
    )
    
    deduction_type = models.CharField(
        "Deduction Type", 
        max_length=20,  # ⭐ CHANGED: Increased from 15 to 20
        choices=TYPE_CHOICES,
        db_index=True
    )
    
    description = models.CharField(
        "Description", 
        max_length=200,  # ⭐ CHANGED: Increased from 100 to 200
        help_text="Detailed description of this deduction"
    )
    
    amount = models.DecimalField(
        "Amount", 
        max_digits=15, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],  # ⭐ ADDED: Ensure non-negative
        help_text="Deduction amount for this pay period"
    )
    
    is_pretax = models.BooleanField(
        "Is Pre-Tax", 
        default=False,
        help_text="Whether this deduction is calculated before tax"
    )
    
    reference_number = models.CharField(
        "Reference Number", 
        max_length=50, 
        blank=True,
        help_text="External reference (e.g., NSSF number, loan ID)"
    )
    
    # ⭐ OPTIONAL: Add for better tracking
    is_recurring = models.BooleanField(
        "Is Recurring",
        default=False,
        help_text="Whether this deduction recurs every pay period"
    )
    
    # For loan deductions
    loan_balance_remaining = models.DecimalField(
        "Loan Balance Remaining",
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Remaining loan balance after this deduction"
    )
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Payroll Deduction"
        verbose_name_plural = "Payroll Deductions"
        ordering = ['deduction_type', 'description']
        indexes = [
            models.Index(fields=['payroll', 'deduction_type']),
            models.Index(fields=['deduction_type']),
            models.Index(fields=['is_pretax']),
            models.Index(fields=['reference_number']),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount__gte=0),
                name='payroll_deduction_amount_non_negative'
            ),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.get_deduction_type_display()} - {self.amount}"
    
    # -------------------------------------------------------------------------
    # PROPERTIES
    # -------------------------------------------------------------------------
    
    @property
    def is_active(self):
        """Check if this deduction is active (payroll not reversed)"""
        return self.payroll.is_active if self.payroll else False
    
    @property
    def effective_amount(self):
        """Get effective amount (0 if payroll reversed)"""
        if not self.is_active:
            return Decimal('0.00')
        return self.amount
    
    @property
    def is_statutory(self):
        """Check if this is a statutory deduction"""
        return self.deduction_type in self.STATUTORY_TYPES


class PayrollBonus(BaseModel):
    """
    Payroll bonuses and additional earnings linked to specific payroll records.
    
    Note: When parent payroll is reversed, these bonuses remain for audit trail
    but are considered inactive (use payroll.is_active to check).
    """
    
    TYPE_CHOICES = [
        ('OVERTIME', 'Overtime Pay'),
        ('PERFORMANCE', 'Performance Bonus'),
        ('COMMISSION', 'Sales Commission'),
        ('ANNUAL', 'Annual Bonus'),
        ('HOLIDAY', 'Holiday Bonus'),
        ('INCENTIVE', 'Incentive Pay'),

        ('ATTENDANCE', 'Attendance Bonus'),
        ('PUNCTUALITY', 'Punctuality Bonus'),

        ('EXAM', 'Examination Bonus'),
        ('COACHING', 'Coaching Bonus'),
        ('RESULTS', 'Results-Based Bonus'),

        ('PROJECT', 'Project Completion Bonus'),
        ('RETENTION', 'Retention Bonus'),

        ('SIGN_ON', 'Sign-On Bonus'),
        ('GRATUITY', 'Gratuity'),

        ('OTHER', 'Other Bonus'),
    ]
    
    # -------------------------------------------------------------------------
    # CORE RELATIONSHIPS
    # -------------------------------------------------------------------------
    
    payroll = models.ForeignKey(
        Payroll, 
        on_delete=models.CASCADE, 
        related_name='bonuses',
        verbose_name="Payroll"
    )
    
    bonus_type = models.CharField(
        "Bonus Type", 
        max_length=20,  # ⭐ CHANGED: Increased from 15 to 20
        choices=TYPE_CHOICES,
        db_index=True
    )
    
    description = models.CharField(
        "Description", 
        max_length=200,  # ⭐ CHANGED: Increased from 100 to 200
        help_text="Detailed description of this bonus"
    )
    
    amount = models.DecimalField(
        "Amount", 
        max_digits=15, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],  # ⭐ ADDED: Ensure non-negative
        help_text="Bonus amount for this pay period"
    )
    
    is_taxable = models.BooleanField(
        "Is Taxable", 
        default=True,
        help_text="Whether this bonus is subject to income tax"
    )
    
    # ⭐ OPTIONAL: Add for better tracking
    is_recurring = models.BooleanField(
        "Is Recurring",
        default=False,
        help_text="Whether this bonus recurs every pay period"
    )
    
    reference_number = models.CharField(
        "Reference Number",
        max_length=50,
        blank=True,
        help_text="External reference (e.g., approval number, performance review ID)"
    )
    
    # For overtime tracking
    overtime_hours = models.DecimalField(
        "Overtime Hours",
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Hours of overtime worked (if applicable)"
    )
    
    overtime_rate = models.DecimalField(
        "Overtime Rate",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Hourly rate for overtime (if applicable)"
    )
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Payroll Bonus"
        verbose_name_plural = "Payroll Bonuses"
        ordering = ['bonus_type', 'description']
        indexes = [
            models.Index(fields=['payroll', 'bonus_type']),
            models.Index(fields=['bonus_type']),
            models.Index(fields=['is_taxable']),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount__gte=0),
                name='payroll_bonus_amount_non_negative'
            ),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.get_bonus_type_display()} - {self.amount}"
    
    # -------------------------------------------------------------------------
    # PROPERTIES
    # -------------------------------------------------------------------------
    
    @property
    def is_active(self):
        """Check if this bonus is active (payroll not reversed)"""
        return self.payroll.is_active if self.payroll else False
    
    @property
    def effective_amount(self):
        """Get effective amount (0 if payroll reversed)"""
        if not self.is_active:
            return Decimal('0.00')
        return self.amount
    
    # -------------------------------------------------------------------------
    # VALIDATION
    # -------------------------------------------------------------------------
    
    def clean(self):
        """Validate bonus data"""
        super().clean()
        errors = {}
        
        # If overtime bonus, should have hours and rate
        if self.bonus_type == 'OVERTIME':
            if self.overtime_hours and self.overtime_rate:
                calculated_amount = self.overtime_hours * self.overtime_rate
                if abs(calculated_amount - self.amount) > Decimal('0.01'):
                    errors['amount'] = (
                        f"Amount ({self.amount}) doesn't match calculated overtime "
                        f"({calculated_amount} = {self.overtime_hours}h × {self.overtime_rate})"
                    )
        
        if errors:
            raise ValidationError(errors)