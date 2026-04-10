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
from datetime import date as _date
import logging

from utils.models import BaseModel

logger = logging.getLogger(__name__)

# =============================================================================
# MODULE-LEVEL DEFAULT FUNCTIONS
# Must be defined at module level (not as lambdas or local functions) so that
# Django migrations can serialize them.
# =============================================================================
 
def _payroll_default_currency():
    """
    Callable default for Payroll.currency.
 
    Called at instance creation time, not at class definition time, so it
    reads the correct school currency from FinancialSettings for whichever
    school database is active on the current request.
 
    Falls back to 'UGX' if FinancialSettings has not yet been initialised
    (e.g. during the school init sequence before the singleton is created).
    """
    try:
        from core.models import FinancialSettings
        currency = FinancialSettings.get_school_currency()
        return currency if currency else 'UGX'
    except Exception:
        return 'UGX'
    
# =============================================================================
# ORGANIZATIONAL STRUCTURE MODELS
# =============================================================================

class Department(BaseModel):
    """
    School departments for organizational structure.
 
    STAFF COUNTING
    --------------
    get_staff_count() and get_all_staff() both traverse the StaffDesignation
    through model to count/list staff who have an active designation in this
    department. They will always return the same population.
 
    get_primary_staff_count() counts staff whose primary_department FK points
    here — a different (and smaller) number since a staff member can have
    designations in multiple departments but only one primary department.
 
    Use get_staff_count() for "how many staff work in this department."
    Use get_primary_staff_count() for "how many staff belong here as home base."
    """
 
    DEPARTMENT_TYPES = [
        ('ACADEMIC',          'Academic Department'),
        ('ADMINISTRATIVE',    'Administrative Department'),
        ('SUPPORT',           'Support Services'),
        ('TECHNICAL',         'Technical Department'),
        ('HEALTH',            'Health Services'),
        ('SECURITY',          'Security Department'),
        ('MAINTENANCE',       'Maintenance & Facilities'),
        ('FINANCE',           'Finance & Accounting'),
        ('HR',                'Human Resources'),
        ('IT',                'Information Technology'),
        ('LIBRARY',           'Library Services'),
        ('TRANSPORT',         'Transport Department'),
        ('CATERING',          'Catering Services'),
        ('SPORTS',            'Sports & Recreation'),
        ('RESEARCH',          'Research & Development'),
        ('PROCUREMENT',       'Procurement'),
        ('LEGAL',             'Legal Affairs'),
        ('MARKETING',         'Marketing & Communications'),
        ('STUDENT_AFFAIRS',   'Student Affairs'),
        ('QUALITY_ASSURANCE', 'Quality Assurance'),
        ('OTHER',             'Other'),
    ]
 
    ACADEMIC_SUBTYPES = [
        ('MATHEMATICS',        'Mathematics'),
        ('SCIENCE',            'Science'),
        ('ENGLISH',            'English Language'),
        ('SOCIAL_STUDIES',     'Social Studies'),
        ('LANGUAGES',          'Foreign Languages'),
        ('ARTS',               'Creative Arts'),
        ('PHYSICAL_EDUCATION', 'Physical Education'),
        ('RELIGIOUS_STUDIES',  'Religious Studies'),
        ('COMPUTER_SCIENCE',   'Computer Science'),
        ('BUSINESS_STUDIES',   'Business Studies'),
        ('VOCATIONAL',         'Vocational Education'),
        ('SPECIAL_NEEDS',      'Special Needs Education'),
    ]
 
    # -------------------------------------------------------------------------
    # FIELDS
    # -------------------------------------------------------------------------
 
    name            = models.CharField("Department Name", max_length=100)
    code            = models.CharField("Department Code", max_length=20, unique=True, db_index=True)
    description     = models.TextField("Description", blank=True)
    department_type = models.CharField(
        "Department Type", max_length=20,
        choices=DEPARTMENT_TYPES, default='ACADEMIC', db_index=True,
    )
    academic_subtype = models.CharField(
        "Academic Subject Area", max_length=20,
        choices=ACADEMIC_SUBTYPES, blank=True, null=True,
    )
    is_academic = models.BooleanField("Is Academic", default=True)
 
    parent_department = models.ForeignKey(
        'self', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='sub_departments',
    )
 
    annual_budget = models.DecimalField(
        "Annual Budget", max_digits=12, decimal_places=2,
        default=Decimal('0.00'), null=True, blank=True,
    )
 
    phone    = models.CharField("Department Phone", max_length=20, blank=True)
    email    = models.EmailField("Department Email", blank=True)
    head_id  = models.CharField(
        "Department Head ID", max_length=50, null=True, blank=True,
        help_text="Staff ID (Staff.staff_id) who heads this department",
    )
 
    is_active       = models.BooleanField("Is Active", default=True, db_index=True)
    capacity        = models.PositiveIntegerField("Staff Capacity", null=True, blank=True)
    location        = models.CharField("Location/Building", max_length=100, blank=True)
    operating_hours = models.JSONField("Operating Hours", default=dict, blank=True)
 
    # -------------------------------------------------------------------------
    # META
    # -------------------------------------------------------------------------
 
    class Meta:
        verbose_name        = "Department"
        verbose_name_plural = "Departments"
        ordering = ['department_type', 'name']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['department_type']),
            models.Index(fields=['is_active']),
        ]
 
    def __str__(self):
        return f"{self.name} ({self.get_department_type_display()})"
 
    # -------------------------------------------------------------------------
    # PROPERTIES
    # -------------------------------------------------------------------------
 
    @property
    def is_academic_department(self):
        return self.department_type in ('ACADEMIC', 'RESEARCH', 'LIBRARY') or self.is_academic
 
    # -------------------------------------------------------------------------
    # STAFF RETRIEVAL
    # -------------------------------------------------------------------------
 
    def get_department_head(self):
        """Return the Staff instance who heads this department, or None."""
        if not self.head_id:
            return None
        try:
            from hr.models import Staff
            return Staff.objects.get(staff_id=self.head_id)
        except Exception:
            logger.error(f"Department head with staff_id '{self.head_id}' not found")
            return None
 
    def get_all_staff(self):
        """
        Return all Staff who have at least one active StaffDesignation in
        this department.
 
        FIX: original query used two independent M2M traversals
        (designations__department and staffdesignation__is_active) which
        Django evaluates as two separate JOINs. A staff member with an active
        designation anywhere would match even if their designation in this
        department was inactive. Corrected to a single traversal through the
        through model.
        """
        from hr.models import Staff
        return Staff.objects.filter(
            staffdesignation__designation__department=self,
            staffdesignation__is_active=True,
        ).distinct()
 
    def get_staff_count(self):
        """
        Count of staff with at least one active designation in this department.
 
        FIX: original counted by primary_department FK, which is inconsistent
        with get_all_staff() and undercounts staff who work here via a secondary
        designation. Now uses the same StaffDesignation traversal as get_all_staff().
 
        For the primary_department-based count use get_primary_staff_count().
        """
        from hr.models import Staff
        return Staff.objects.filter(
            staffdesignation__designation__department=self,
            staffdesignation__is_active=True,
        ).distinct().count()
 
    def get_primary_staff_count(self):
        """
        Count of active staff whose primary_department is this department.
 
        This is the count that was previously returned by get_staff_count().
        Kept as a separate method because it answers a distinct question:
        "how many staff call this department their home base" vs
        "how many staff are working here in any capacity."
        """
        from hr.models import Staff
        return Staff.objects.filter(
            primary_department=self,
            is_active=True,
        ).count()
 
    def is_at_capacity(self):
        """
        Return True if the number of staff with active designations here
        meets or exceeds the configured capacity limit.
 
        Returns False if no capacity limit is set (capacity is null).
        """
        if not self.capacity:
            return False
        return self.get_staff_count() >= self.capacity


class Designation(BaseModel):
    """
    Staff designations/roles with salary reference ranges.
 
    QUALIFICATIONS
    --------------
    required_qualifications is a JSONField that stores a list of qualification
    strings. When not manually populated, get_qualifications() falls back to
    get_default_qualifications() which returns sensible defaults based on
    is_teaching and the parent department type.
 
    Always call get_qualifications() rather than reading required_qualifications
    directly to guarantee a non-empty result.
    """
 
    # -------------------------------------------------------------------------
    # FIELDS
    # -------------------------------------------------------------------------
 
    name        = models.CharField("Designation Name", max_length=100)
    code        = models.CharField("Designation Code", max_length=50, unique=True, db_index=True)
    description = models.TextField("Description", blank=True)
    department  = models.ForeignKey(
        Department, on_delete=models.CASCADE, related_name="designations",
    )
 
    is_teaching   = models.BooleanField("Is Teaching",             default=False)
    is_management = models.BooleanField("Is Management Position",  default=False)
 
    reports_to = models.ForeignKey(
        'self', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='subordinate_designations',
    )
    rank_order = models.PositiveIntegerField("Rank Order", default=0, db_index=True)
 
    min_salary = models.DecimalField(
        "Minimum Salary (Reference)", max_digits=10, decimal_places=2,
        default=Decimal('0.00'), null=True, blank=True,
        help_text="Reference minimum salary for this designation",
    )
    max_salary = models.DecimalField(
        "Maximum Salary (Reference)", max_digits=10, decimal_places=2,
        default=Decimal('0.00'), null=True, blank=True,
        help_text="Reference maximum salary for this designation",
    )
 
    required_qualifications = models.JSONField(
        "Required Qualifications",
        default=list,
        blank=True,
        help_text=(
            "List of qualification strings for this designation. "
            "If left empty, get_qualifications() returns sensible defaults "
            "based on is_teaching and department type."
        ),
    )
    key_responsibilities = models.TextField("Key Responsibilities", blank=True)
    is_active            = models.BooleanField("Is Active", default=True, db_index=True)
 
    # -------------------------------------------------------------------------
    # META
    # -------------------------------------------------------------------------
 
    class Meta:
        verbose_name        = "Designation"
        verbose_name_plural = "Designations"
        ordering = ['rank_order', 'name']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['department']),
            models.Index(fields=['is_active']),
            models.Index(fields=['rank_order']),
        ]
 
    def __str__(self):
        return f"{self.name} ({self.department.name})"
 
    # -------------------------------------------------------------------------
    # QUALIFICATION HELPERS
    # -------------------------------------------------------------------------
 
    def get_default_qualifications(self):
        """
        Return a list of sensible qualification defaults based on the
        designation's teaching status and parent department type.
 
        These are returned when required_qualifications has not been
        manually populated. They serve as starting-point guidance for
        HR staff and are not binding constraints.
        """
        dept_type = self.department.department_type if self.department_id else ''
 
        if self.is_teaching:
            base = ["Bachelor's Degree in Education or relevant subject area"]
            if dept_type == 'ACADEMIC':
                if self.is_management:
                    return base + [
                        "Postgraduate qualification in Education Management",
                        "Minimum 5 years teaching experience",
                        "Valid teaching licence / registration",
                    ]
                return base + [
                    "Valid teaching licence / registration",
                    "Minimum 2 years classroom experience",
                ]
            return base + ["Valid teaching licence / registration"]
 
        # Non-teaching, management
        if self.is_management:
            dept_defaults = {
                'FINANCE':    ["Bachelor's Degree in Accounting, Finance, or CPA/ACCA"],
                'HR':         ["Bachelor's Degree in Human Resource Management or equivalent"],
                'HEALTH':     ["Clinical Officer Diploma or Nursing Degree", "Valid health practice licence"],
                'IT':         ["Bachelor's Degree in Computer Science or Information Technology"],
                'PROCUREMENT':["Bachelor's Degree in Procurement, Supply Chain, or Business Administration"],
                'CATERING':   ["Diploma in Catering or Hospitality Management", "Food handler's certificate"],
                'SECURITY':   ["Certificate in Security Management or equivalent"],
                'TRANSPORT':  ["Valid driver's licence (class applicable to vehicles operated)"],
                'LIBRARY':    ["Bachelor's Degree in Library and Information Science"],
            }
            return dept_defaults.get(dept_type, ["Bachelor's Degree or equivalent", "Minimum 3 years experience in relevant field"])
 
        # Non-teaching, non-management — operational / support roles
        operational_defaults = {
            'HEALTH':     ["Certificate in Nursing or equivalent", "Valid health practice licence"],
            'CATERING':   ["Certificate in Food Production or equivalent", "Food handler's certificate"],
            'SECURITY':   ["Certificate in Security Services or equivalent"],
            'TRANSPORT':  ["Valid driver's licence (class applicable)", "Certificate of Good Conduct"],
            'MAINTENANCE':["Trade certificate or equivalent practical qualification"],
            'IT':         ["Diploma or Certificate in ICT"],
        }
        return operational_defaults.get(dept_type, ["Certificate or Diploma in relevant field"])
 
    def get_qualifications(self):
        """
        Return required qualifications for this designation.
 
        Returns the stored required_qualifications list if it has been
        manually populated, otherwise delegates to get_default_qualifications()
        so callers always receive a non-empty, meaningful list.
 
        Always call this method rather than reading required_qualifications
        directly.
        """
        if self.required_qualifications:
            return self.required_qualifications
        return self.get_default_qualifications()
 
    # -------------------------------------------------------------------------
    # SALARY HELPERS
    # -------------------------------------------------------------------------
 
    def get_salary_reference_range(self):
        """Return salary reference range dict for contract creation."""
        if self.min_salary and self.max_salary:
            return {
                'min':              self.min_salary,
                'max':              self.max_salary,
                'midpoint':         (self.min_salary + self.max_salary) / 2,
                'new_hire_suggested': (
                    self.min_salary
                    + ((self.max_salary - self.min_salary) * Decimal('0.2'))
                ),
            }
        return None

# =============================================================================
# CONTRACT MANAGEMENT MODEL 
# =============================================================================

class Contract(BaseModel):
    """
    Staff employment contracts with full lifecycle management.
 
    TIMEZONE
    --------
    All date comparisons (is_expired, days_until_expiry, is_probationary) and
    queryset filters (get_expiring_soon, get_expired_contracts) use
    get_school_today() from core.utils so that contract status reflects the
    school's operational timezone rather than the server clock.
 
    EXPIRY CHECKING
    ---------------
    expires_soon — @property, checks within 30 days (no configurable threshold)
    will_expire_within(days) — regular method, configurable threshold
    """
 
    CONTRACT_TYPE_CHOICES = (
        ('PERMANENT',     'Permanent Contract'),
        ('FIXED_TERM',    'Fixed Term Contract'),
        ('PROBATION',     'Probationary Contract'),
        ('TEMPORARY',     'Temporary Contract'),
        ('PART_TIME',     'Part-Time Contract'),
        ('CASUAL',        'Casual Contract'),
        ('INTERNSHIP',    'Internship Contract'),
        ('VOLUNTEER',     'Volunteer Agreement'),
        ('CONSULTANT',    'Consultancy Contract'),
        ('SEASONAL',      'Seasonal Contract'),
        ('PROJECT_BASED', 'Project-Based Contract'),
        ('APPRENTICESHIP','Apprenticeship Contract'),
    )
 
    CONTRACT_STATUS_CHOICES = (
        ('DRAFT',      'Draft'),
        ('REVIEW',     'Under Review'),
        ('APPROVED',   'Approved'),
        ('SIGNED',     'Signed'),
        ('ACTIVE',     'Active'),
        ('EXPIRED',    'Expired'),
        ('TERMINATED', 'Terminated'),
        ('CANCELLED',  'Cancelled'),
        ('RENEWED',    'Renewed'),
    )
 
    TERMINATION_REASON_CHOICES = (
        ('COMPLETION', 'Contract Completion'),
        ('RESIGNATION','Staff Resignation'),
        ('TERMINATION','Employer Termination'),
        ('MUTUAL',     'Mutual Agreement'),
        ('BREACH',     'Contract Breach'),
        ('REDUNDANCY', 'Redundancy'),
        ('RETIREMENT', 'Retirement'),
        ('OTHER',      'Other'),
    )
 
    SALARY_FREQUENCY_CHOICES = (
        ('MONTHLY', 'Monthly'),
        ('WEEKLY',  'Weekly'),
        ('DAILY',   'Daily'),
        ('HOURLY',  'Hourly'),
        ('ANNUAL',  'Annual'),
    )
 
    # -------------------------------------------------------------------------
    # FIELDS
    # -------------------------------------------------------------------------
 
    staff = models.ForeignKey(
        'Staff', on_delete=models.CASCADE, related_name='contracts',
    )
 
    contract_number = models.CharField(
        "Contract Number", max_length=50, unique=True, db_index=True,
    )
    contract_type = models.CharField(
        "Contract Type", max_length=20,
        choices=CONTRACT_TYPE_CHOICES, default='FIXED_TERM', db_index=True,
    )
    status = models.CharField(
        "Status", max_length=12,
        choices=CONTRACT_STATUS_CHOICES, default='DRAFT', db_index=True,
    )
 
    start_date         = models.DateField("Contract Start Date", db_index=True)
    end_date           = models.DateField("Contract End Date",   null=True, blank=True, db_index=True)
    signed_date        = models.DateField("Date Signed",         null=True, blank=True)
    renewal_due_date   = models.DateField("Renewal Due Date",    null=True, blank=True)
 
    termination_date               = models.DateField("Termination Date", null=True, blank=True)
    termination_reason             = models.CharField("Termination Reason", max_length=15, choices=TERMINATION_REASON_CHOICES, blank=True)
    termination_notice_period_days = models.PositiveIntegerField("Notice Period (Days)", default=30)
    termination_notes              = models.TextField("Termination Notes", blank=True)
 
    basic_salary = models.DecimalField(
        "Basic Salary", max_digits=10, decimal_places=2, default=Decimal('0.00'),
        help_text="Basic salary amount — interpreted based on salary_frequency",
    )
    salary_frequency = models.CharField(
        "Salary Frequency", max_length=10,
        choices=SALARY_FREQUENCY_CHOICES, default='MONTHLY',
        help_text="Period for basic_salary rate (e.g., 'per month', 'per hour')",
    )
 
    working_hours_per_week  = models.PositiveIntegerField("Working Hours Per Week", default=40, validators=[MinValueValidator(1), MaxValueValidator(168)])
    probation_period_months = models.PositiveIntegerField("Probation Period (Months)", default=0, help_text="0 if no probation")
    annual_leave_days       = models.PositiveIntegerField("Annual Leave Days", default=21)
 
    job_title        = models.CharField("Job Title", max_length=100)
    job_description  = models.TextField("Job Description", blank=True)
    reporting_to_id  = models.CharField("Reports To Staff ID", max_length=50, null=True, blank=True, help_text="Staff ID of direct supervisor")
 
    contract_document = models.FileField("Contract Document", upload_to='contracts/documents/', blank=True, null=True)
 
    auto_renew                = models.BooleanField("Auto Renew", default=False)
    renewal_period_months     = models.PositiveIntegerField("Renewal Period (Months)", default=12)
    requires_renewal_approval = models.BooleanField("Requires Renewal Approval", default=True)
 
    approved_by_id    = models.CharField("Approved By ID",    max_length=100, null=True, blank=True)
    approved_at       = models.DateTimeField("Approval Date",  null=True, blank=True)
    signed_by_id      = models.CharField("Signed By ID",      max_length=100, null=True, blank=True)
    signed_at         = models.DateTimeField("Signed At",      null=True, blank=True)
    terminated_by_id  = models.CharField("Terminated By ID",  max_length=100, null=True, blank=True)
    terminated_at     = models.DateTimeField("Terminated At",  null=True, blank=True)
 
    benefits_package  = models.JSONField("Benefits Package",          default=dict, blank=True)
    special_terms     = models.TextField("Special Terms & Conditions", blank=True)
    notes             = models.TextField("Contract Notes",             blank=True)
 
    # -------------------------------------------------------------------------
    # META
    # -------------------------------------------------------------------------
 
    class Meta:
        verbose_name        = "Contract"
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
 
    def __str__(self):
        return (
            f"{self.contract_number} — "
            f"{self.staff.full_name()} ({self.get_contract_type_display()})"
        )
 
    # -------------------------------------------------------------------------
    # VALIDATION
    # -------------------------------------------------------------------------
 
    def clean(self):
        super().clean()
        errors = {}
 
        if self.end_date and self.end_date < self.start_date:
            errors['end_date'] = "End date cannot be before start date"
 
        if self.termination_date:
            if self.termination_date < self.start_date:
                errors['termination_date'] = "Termination date cannot be before start date"
            if self.end_date and self.termination_date > self.end_date:
                errors['termination_date'] = "Termination date cannot be after contract end date"
 
        if self.contract_type == 'PERMANENT' and self.end_date:
            errors['end_date'] = "Permanent contracts should not have an end date"
 
        if (self.contract_type in ('FIXED_TERM', 'PROBATION', 'TEMPORARY', 'SEASONAL', 'PROJECT_BASED')
                and not self.end_date):
            errors['end_date'] = f"{self.get_contract_type_display()} must have an end date"
 
        if errors:
            raise ValidationError(errors)
 
    # -------------------------------------------------------------------------
    # STATUS PROPERTIES
    # -------------------------------------------------------------------------
 
    @property
    def is_active(self):
        return self.status == 'ACTIVE'
 
    @property
    def is_expired(self):
        """
        True if the contract end date has passed.
 
        FIX: was timezone.now().date() — now uses get_school_today() so
        expiry is evaluated in the school's operational timezone.
        """
        if not self.end_date:
            return False
        from core.utils import get_school_today
        return self.end_date < get_school_today()
 
    @property
    def days_until_expiry(self):
        """
        Days until contract expires. Negative if already expired.
        Returns None for permanent (no end date) contracts.
 
        FIX: was timezone.now().date() — now uses get_school_today().
        """
        if not self.end_date:
            return None
        from core.utils import get_school_today
        return (self.end_date - get_school_today()).days
 
    @property
    def expires_soon(self):
        """
        True if contract expires within 30 days.
 
        FIX: was decorated @property with a days_threshold=30 parameter.
        Properties cannot accept arguments — the parameter was silently ignored
        and the threshold was always 30 regardless. Removed the parameter.
 
        For a configurable threshold use will_expire_within(days).
        """
        days = self.days_until_expiry
        return days is not None and 0 <= days <= 30
 
    def will_expire_within(self, days):
        """
        True if contract expires within the given number of days.
        Use this when you need a threshold other than 30.
 
        Example:
            contract.will_expire_within(60)   # expiring within 2 months
            contract.will_expire_within(7)    # expiring this week
        """
        days_left = self.days_until_expiry
        return days_left is not None and 0 <= days_left <= days
 
    @property
    def is_permanent(self):
        return self.contract_type == 'PERMANENT'
 
    @property
    def is_probationary(self):
        """
        True if this is a PROBATION contract or if the probation period
        has not yet elapsed on a contract with probation_period_months set.
 
        FIX: was timezone.now().date() — now uses get_school_today().
        """
        if self.contract_type == 'PROBATION':
            return True
        if self.probation_period_months > 0:
            from datetime import timedelta
            from core.utils import get_school_today
            probation_end = self.start_date + timedelta(days=self.probation_period_months * 30)
            return get_school_today() <= probation_end
        return False
 
    @property
    def duration_in_months(self):
        if not self.end_date:
            return None
        return (
            (self.end_date.year  - self.start_date.year)  * 12
            + (self.end_date.month - self.start_date.month)
        )
 
    # -------------------------------------------------------------------------
    # ACTION METHODS
    # -------------------------------------------------------------------------
 
    def activate(self, user=None):
        self.status = 'ACTIVE'
        if user:
            self.approved_by_id = str(user.id) if hasattr(user, 'id') else str(user.pk)
            self.approved_at    = timezone.now()
        self.save()
 
    def terminate(self, reason, user=None, termination_date=None, notes=''):
        """
        Terminate the contract.
 
        FIX: default termination_date was timezone.now().date() — now uses
        get_school_today() to respect the school's operational timezone.
        """
        from core.utils import get_school_today
        self.status             = 'TERMINATED'
        self.termination_reason = reason
        self.termination_date   = termination_date or get_school_today()
        self.termination_notes  = notes
        if user:
            self.terminated_by_id = str(user.id) if hasattr(user, 'id') else str(user.pk)
            self.terminated_at    = timezone.now()
        self.save()
 
    def renew(self, new_end_date=None, user=None):
        """
        Renew the contract for another renewal_period_months period.
 
        FIX: fallback new_end_date calculation used timezone.now().date() —
        now uses get_school_today() to respect the school's operational timezone.
        """
        from datetime import timedelta
        from core.utils import get_school_today
 
        if not new_end_date:
            base_date    = self.end_date or get_school_today()
            new_end_date = base_date + timedelta(days=self.renewal_period_months * 30)
 
        self.end_date        = new_end_date
        self.status          = 'ACTIVE'
        self.renewal_due_date = None
 
        if user:
            self.approved_by_id = str(user.id) if hasattr(user, 'id') else str(user.pk)
            self.approved_at    = timezone.now()
 
        self.save()
 
    # -------------------------------------------------------------------------
    # USER RETRIEVAL
    # -------------------------------------------------------------------------
 
    def get_reporting_to_staff(self):
        if not self.reporting_to_id:
            return None
        try:
            from hr.models import Staff
            return Staff.objects.get(staff_id=self.reporting_to_id)
        except Exception:
            logger.error(f"Reporting staff with ID {self.reporting_to_id} not found")
            return None
 
    def _get_user(self, user_id):
        if not user_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            return get_user_model().objects.using('default').get(id=user_id)
        except Exception as e:
            logger.error(f"Error fetching user {user_id}: {e}")
            return None
 
    def get_approved_by_user(self):   return self._get_user(self.approved_by_id)
    def get_signed_by_user(self):     return self._get_user(self.signed_by_id)
    def get_terminated_by_user(self): return self._get_user(self.terminated_by_id)
 
    # -------------------------------------------------------------------------
    # CLASS METHODS
    # -------------------------------------------------------------------------
 
    @classmethod
    def get_active_contracts(cls):
        return cls.objects.filter(status='ACTIVE')
 
    @classmethod
    def get_expiring_soon(cls, days=30):
        """
        Return active contracts expiring within `days` days.
 
        FIX: was timezone.now().date() — now uses get_school_today() so
        the threshold window is calculated in the school's operational timezone.
        """
        from datetime import timedelta
        from core.utils import get_school_today
        today          = get_school_today()
        threshold_date = today + timedelta(days=days)
        return cls.objects.filter(
            status='ACTIVE',
            end_date__lte=threshold_date,
            end_date__gte=today,
        ).order_by('end_date')
 
    @classmethod
    def get_expired_contracts(cls):
        """
        Return contracts still marked ACTIVE but whose end_date has passed.
 
        FIX: was timezone.now().date() — now uses get_school_today().
        """
        from core.utils import get_school_today
        return cls.objects.filter(
            status='ACTIVE',
            end_date__lt=get_school_today(),
        )
 
    @classmethod
    def get_staff_active_contract(cls, staff):
        return cls.objects.filter(staff=staff, status='ACTIVE').first()
 
    @classmethod
    def get_contracts_by_type(cls, contract_type):
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
    """
    Through model for the Staff ↔ Designation many-to-many relationship.
 
    DATE DEFAULT
    ------------
    start_date defaults to datetime.date.today (the current date in the
    process's local timezone). The original default was timezone.now which
    returns a timezone-aware datetime object — Django coerces it to a date
    using the server timezone, which can differ from the school's operational
    timezone and produce off-by-one dates for schools in different regions.
    """
 
    ASSIGNMENT_TYPE_CHOICES = [
        ('PERMANENT',   'Permanent Assignment'),
        ('ACTING',      'Acting Role'),
        ('TEMPORARY',   'Temporary Assignment'),
        ('SECONDMENT',  'Secondment'),
        ('ADDITIONAL',  'Additional Responsibility'),
    ]
 
    # -------------------------------------------------------------------------
    # FIELDS
    # -------------------------------------------------------------------------
 
    staff       = models.ForeignKey('Staff',       on_delete=models.CASCADE)
    designation = models.ForeignKey('Designation', on_delete=models.CASCADE)
 
    is_primary = models.BooleanField("Is Primary Designation", default=False)
 
    start_date = models.DateField(
        "Start Date",
        default=_date.today,     # _date is datetime.date, .today is callable
    )
    end_date   = models.DateField("End Date", null=True, blank=True)
    is_active  = models.BooleanField("Is Active", default=True, db_index=True)
 
    role_allowance = models.DecimalField(
        "Role-Specific Allowance", max_digits=10, decimal_places=2,
        default=Decimal('0.00'),
    )
 
    assignment_type         = models.CharField("Assignment Type", max_length=20, choices=ASSIGNMENT_TYPE_CHOICES, default='PERMANENT')
    assignment_order_number = models.CharField("Assignment Order Number", max_length=50, blank=True)
    notes                   = models.TextField("Notes", blank=True)
 
    # -------------------------------------------------------------------------
    # META
    # -------------------------------------------------------------------------
 
    class Meta:
        verbose_name        = "Staff Designation"
        verbose_name_plural = "Staff Designations"
        ordering = ['staff', '-is_primary', 'designation']
        indexes = [
            models.Index(fields=['staff', 'is_primary']),
            models.Index(fields=['designation', 'is_active']),
        ]
 
    def __str__(self):
        primary = " (Primary)" if self.is_primary else ""
        return f"{self.staff.full_name()} — {self.designation.name}{primary}"
 
    # -------------------------------------------------------------------------
    # VALIDATION
    # -------------------------------------------------------------------------
 
    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({
                'end_date': (
                    f"End date ({self.end_date}) cannot be before "
                    f"start date ({self.start_date})."
                )
            })


# =============================================================================
# TEACHER MODEL
# =============================================================================

class Teacher(BaseModel):
    """Enhanced teacher profile linked to staff."""

    # -------------------------------------------------------------------------
    # CHOICES
    # -------------------------------------------------------------------------

    AVAILABLE_DAYS_CHOICES = [
        ('Monday',    'Monday'),
        ('Tuesday',   'Tuesday'),
        ('Wednesday', 'Wednesday'),
        ('Thursday',  'Thursday'),
        ('Friday',    'Friday'),
        ('Saturday',  'Saturday'),
        ('Sunday',    'Sunday'),
    ]

    PREFERRED_SLOT_CHOICES = [
        ('07:00-09:00', '07:00 – 09:00'),
        ('08:00-10:00', '08:00 – 10:00'),
        ('09:00-11:00', '09:00 – 11:00'),
        ('10:00-12:00', '10:00 – 12:00'),
        ('11:00-13:00', '11:00 – 13:00'),
        ('12:00-14:00', '12:00 – 14:00'),
        ('13:00-15:00', '13:00 – 15:00'),
        ('14:00-16:00', '14:00 – 16:00'),
        ('15:00-17:00', '15:00 – 17:00'),
        ('16:00-18:00', '16:00 – 18:00'),
    ]

    DIGITAL_LITERACY_CHOICES = [
        ('BASIC',        'Basic'),
        ('INTERMEDIATE', 'Intermediate'),
        ('ADVANCED',     'Advanced'),
        ('EXPERT',       'Expert'),
    ]

    # -------------------------------------------------------------------------
    # CORE RELATIONSHIP
    # -------------------------------------------------------------------------

    staff = models.OneToOneField(
        Staff,
        on_delete=models.CASCADE,
        related_name='teacher',
    )

    # -------------------------------------------------------------------------
    # TEACHING SPECIALIZATION
    # -------------------------------------------------------------------------

    specialization      = models.CharField('Specialization', max_length=200, blank=True)
    teaching_philosophy = models.TextField('Teaching Philosophy', blank=True)

    # -------------------------------------------------------------------------
    # TEACHING LOAD
    # -------------------------------------------------------------------------

    max_hours_per_week = models.PositiveIntegerField(
        'Maximum Teaching Hours Per Week',
        default=40,
        validators=[MinValueValidator(1), MaxValueValidator(60)],
    )
    current_teaching_load = models.PositiveIntegerField(
        'Current Teaching Load (Hours)',
        default=0,
        validators=[MinValueValidator(0)],
    )

    # -------------------------------------------------------------------------
    # ACADEMIC PREFERENCES
    # -------------------------------------------------------------------------

    preferred_academic_levels = models.ManyToManyField(
        'academics.AcademicLevel',
        blank=True,
        related_name='preferred_teachers',
    )
    qualified_subjects = models.ManyToManyField(
        'academics.Subject',
        blank=True,
        related_name='qualified_teachers',
    )

    # -------------------------------------------------------------------------
    # AVAILABILITY
    # Stored as plain Python lists; valid values come from the class constants
    # above so any code path (signals, admin, API) has a single source of truth.
    # -------------------------------------------------------------------------

    available_days = models.JSONField(
        'Available Days',
        default=list,
        blank=True,
        help_text='List of days from AVAILABLE_DAYS_CHOICES',
    )
    preferred_time_slots = models.JSONField(
        'Preferred Time Slots',
        default=list,
        blank=True,
        help_text='List of time slots from PREFERRED_SLOT_CHOICES',
    )

    # -------------------------------------------------------------------------
    # CLASS TEACHER ASSIGNMENT
    # -------------------------------------------------------------------------

    is_class_teacher = models.BooleanField('Is Class Teacher', default=False)
    assigned_classes = models.ManyToManyField(
        'academics.Class',
        blank=True,
        related_name='class_teachers',
    )

    # -------------------------------------------------------------------------
    # DIGITAL LITERACY
    # -------------------------------------------------------------------------

    digital_literacy_level = models.CharField(
        'Digital Literacy Level',
        max_length=20,
        choices=DIGITAL_LITERACY_CHOICES,
        default='BASIC',
    )
    can_teach_online = models.BooleanField('Can Teach Online', default=False)

    # -------------------------------------------------------------------------
    # STATUS
    # -------------------------------------------------------------------------

    is_active = models.BooleanField(
        'Active Status',
        default=True,
        help_text='Whether this teacher profile is currently active.',
    )

    # -------------------------------------------------------------------------
    # META
    # -------------------------------------------------------------------------

    class Meta:
        verbose_name        = 'Teacher'
        verbose_name_plural = 'Teachers'
        ordering            = ['staff__first_name', 'staff__last_name']

    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------

    def __str__(self):
        return f'{self.staff.full_name()} - Teacher'


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
 
    CURRENCY DEFAULT
    ----------------
    The currency field uses _payroll_default_currency() as a callable default
    rather than the string literal 'UGX'. The callable is evaluated at instance
    creation time and reads FinancialSettings.get_school_currency() for the
    current school database. Schools whose currency is not UGX will get the
    correct currency on every new payroll record automatically.
 
    PAY PERIODS vs FISCAL PERIODS
    ------------------------------
    Pay Period: The time worked (e.g., Jan 1–31 for monthly salary)
    Fiscal Period: Accounting period for reporting (e.g., Term 1 = Jan–Apr)
    Multiple pay periods can exist within one fiscal period.
 
    REVERSAL RULES
    --------------
    Only draft or approved (not yet paid) payrolls can be reversed easily.
    Paid payrolls require special approval and statutory adjustments.
    Must be reversed in same fiscal period. Cannot reverse if period is closed.
 
    GROSS PAY:         gross_pay = basic_salary + total_allowances + total_bonuses
    DEDUCTIONS:        total_deductions = total_statutory + total_voluntary
    NET PAY:           net_pay = gross_pay - total_deductions
    EMPLOYER COST:     employer_total_cost = gross_pay + nssf_employer
    """
 
    STATUS_CHOICES = [
        ('DRAFT',     'Draft'),
        ('APPROVED',  'Approved'),
        ('PARTIAL',   'Partially Paid'),
        ('PAID',      'Paid'),
        ('CANCELLED', 'Cancelled'),
    ]
 
    PAY_FREQUENCY_CHOICES = [
        ('MONTHLY',      'Monthly'),
        ('WEEKLY',       'Weekly'),
        ('BIWEEKLY',     'Bi-Weekly'),
        ('SEMI_MONTHLY', 'Semi-Monthly'),
        ('QUARTERLY',    'Quarterly'),
    ]
 
    # =========================================================================
    # CORE RELATIONSHIPS
    # =========================================================================
 
    staff = models.ForeignKey(
        'Staff', on_delete=models.CASCADE, related_name='payrolls',
        verbose_name="Staff Member",
    )
    fiscal_period = models.ForeignKey(
        'core.FiscalPeriod', on_delete=models.PROTECT,
        related_name='staff_payrolls', verbose_name="Fiscal Period",
        help_text="Fiscal period for accounting (may contain multiple monthly payrolls)",
    )
    payroll_number = models.CharField(
        "Payroll Number", max_length=30, unique=True, blank=True, db_index=True,
        help_text="Auto-generated reference (e.g. PAY/2025/12/0001)",
    )
 
    # =========================================================================
    # PAY PERIOD
    # =========================================================================
 
    pay_period_start = models.DateField("Pay Period Start", db_index=True)
    pay_period_end   = models.DateField("Pay Period End",   db_index=True)
    payment_date     = models.DateField("Payment Date",     db_index=True)
 
    pay_frequency = models.CharField(
        "Pay Frequency", max_length=12,
        choices=PAY_FREQUENCY_CHOICES, default='MONTHLY', db_index=True,
    )
    pay_period_label = models.CharField(
        "Pay Period Label", max_length=50, blank=True, db_index=True,
        help_text="Display label (e.g., 'January 2024', 'Week 1 Feb 2024')",
    )
 
    # =========================================================================
    # EARNINGS
    # =========================================================================
 
    basic_salary     = models.DecimalField("Basic Salary",     max_digits=15, decimal_places=2, default=Decimal('0.00'))
    total_allowances = models.DecimalField("Total Allowances", max_digits=15, decimal_places=2, default=Decimal('0.00'))
    total_bonuses    = models.DecimalField("Total Bonuses",    max_digits=15, decimal_places=2, default=Decimal('0.00'))
    gross_pay        = models.DecimalField("Gross Pay",        max_digits=15, decimal_places=2, default=Decimal('0.00'), help_text="basic_salary + total_allowances + total_bonuses")
 
    # =========================================================================
    # TAXABLE BASE
    # =========================================================================
 
    taxable_income = models.DecimalField(
        "Taxable Income", max_digits=15, decimal_places=2, default=Decimal('0.00'),
        help_text="Gross pay minus pre-tax deductions and non-taxable allowances",
    )
 
    # =========================================================================
    # DEDUCTIONS
    # =========================================================================
 
    paye_amount                  = models.DecimalField("PAYE Amount",                    max_digits=15, decimal_places=2, default=Decimal('0.00'))
    nssf_employee                = models.DecimalField("NSSF Employee Contribution",     max_digits=15, decimal_places=2, default=Decimal('0.00'))
    local_service_tax            = models.DecimalField("Local Service Tax",              max_digits=15, decimal_places=2, default=Decimal('0.00'))
    total_statutory_deductions   = models.DecimalField("Total Statutory Deductions",    max_digits=15, decimal_places=2, default=Decimal('0.00'))
    total_voluntary_deductions   = models.DecimalField("Total Voluntary Deductions",    max_digits=15, decimal_places=2, default=Decimal('0.00'))
    total_deductions             = models.DecimalField("Total Deductions",              max_digits=15, decimal_places=2, default=Decimal('0.00'))
    net_pay                      = models.DecimalField("Net Pay",                       max_digits=15, decimal_places=2, default=Decimal('0.00'))
 
    # =========================================================================
    # EMPLOYER CONTRIBUTIONS
    # =========================================================================
 
    nssf_employer        = models.DecimalField("NSSF Employer Contribution", max_digits=15, decimal_places=2, default=Decimal('0.00'))
    employer_total_cost  = models.DecimalField("Total Employer Cost",        max_digits=15, decimal_places=2, default=Decimal('0.00'))
 
    # =========================================================================
    # CURRENCY
    # =========================================================================
 
    currency = models.CharField(
        "Currency",
        max_length=3,
        default=_payroll_default_currency,  # FIX: was default='UGX' (string literal)
        help_text=(
            "ISO 4217 currency code this payroll is denominated in. "
            "Defaults to the school's primary currency from FinancialSettings — "
            "non-UGX schools no longer need to manually correct this field."
        ),
    )
    exchange_rate = models.DecimalField(
        "Exchange Rate", max_digits=12, decimal_places=6, default=Decimal('1.000000'),
        help_text="Rate between payroll currency and school currency at time of payment. Stored permanently.",
    )
    net_pay_in_school_currency = models.DecimalField(
        "Net Pay in School Currency", max_digits=15, decimal_places=2, default=Decimal('0.00'),
        help_text="net_pay × exchange_rate",
    )
    employer_cost_in_school_currency = models.DecimalField(
        "Employer Cost in School Currency", max_digits=15, decimal_places=2, default=Decimal('0.00'),
        help_text="employer_total_cost × exchange_rate",
    )
 
    # =========================================================================
    # WORKING DAYS
    # =========================================================================
 
    total_working_days = models.PositiveIntegerField("Total Working Days", null=True, blank=True)
    days_worked        = models.PositiveIntegerField("Days Worked",        null=True, blank=True)
    is_prorated        = models.BooleanField("Is Prorated", default=False)
 
    # =========================================================================
    # PAYMENT DETAILS
    # =========================================================================
 
    payment_method    = models.ForeignKey('core.PaymentMethod', on_delete=models.PROTECT, related_name='staff_payrolls')
    bank_account      = models.CharField("Bank Account",      max_length=100, blank=True)
    payment_reference = models.CharField("Payment Reference", max_length=100, blank=True)
 
    # =========================================================================
    # STATUS AND APPROVAL
    # =========================================================================
 
    status         = models.CharField("Status", max_length=12, choices=STATUS_CHOICES, default='DRAFT', db_index=True)
    approved_by_id = models.CharField("Approved By ID", max_length=50, null=True, blank=True)
    approved_at    = models.DateTimeField("Approved At",  null=True, blank=True)
    paid_by_id     = models.CharField("Paid By ID",      max_length=50, null=True, blank=True)
    paid_at        = models.DateTimeField("Paid At",      null=True, blank=True)
 
    # =========================================================================
    # REVERSAL TRACKING
    # =========================================================================
 
    reversed                      = models.BooleanField("Reversed",                       default=False, db_index=True)
    reversed_on                   = models.DateTimeField("Reversed On",                    null=True, blank=True)
    reversed_by_id                = models.CharField("Reversed By ID",                    max_length=50, null=True, blank=True)
    reversal_reason               = models.TextField("Reversal Reason",                    blank=True)
    reversal_approved_by_id       = models.CharField("Reversal Approved By ID",           max_length=50, null=True, blank=True)
    reversal_approved_on          = models.DateTimeField("Reversal Approved On",           null=True, blank=True)
    statutory_reversals_required  = models.BooleanField("Statutory Reversals Required",   default=False)
    statutory_adjustments_notes   = models.TextField("Statutory Adjustments Notes",        blank=True)
    reversal_journal_entry        = models.ForeignKey(
        'finance.JournalEntry', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reversed_payrolls', verbose_name="Reversal Journal Entry",
    )
 
    # =========================================================================
    # JOURNAL ENTRY INTEGRATION
    # =========================================================================
 
    journal_entry             = models.ForeignKey('finance.JournalEntry', on_delete=models.SET_NULL, null=True, blank=True, related_name='payrolls')
    payment_journal_entry     = models.ForeignKey('finance.JournalEntry', on_delete=models.SET_NULL, null=True, blank=True, related_name='payroll_payments')
    auto_create_journal_entry = models.BooleanField("Auto-Create Journal Entry", default=True)
 
    notes = models.TextField("Notes", blank=True)
 
    # =========================================================================
    # META
    # =========================================================================
 
    class Meta:
        verbose_name        = "Payroll"
        verbose_name_plural = "Payrolls"
        ordering = ['-payment_date', 'staff']
 
        constraints = [
            models.UniqueConstraint(
                fields=['staff', 'pay_period_start', 'pay_period_end'],
                name='unique_staff_pay_period',
                condition=models.Q(reversed=False),
            ),
            models.CheckConstraint(check=models.Q(pay_period_start__lt=models.F('pay_period_end')), name='payroll_pay_period_start_before_end'),
            models.CheckConstraint(check=models.Q(gross_pay__gte=0),                                name='payroll_gross_pay_non_negative'),
            models.CheckConstraint(check=models.Q(net_pay__gte=0),                                  name='payroll_net_pay_non_negative'),
            models.CheckConstraint(check=models.Q(total_allowances__gte=0),                         name='payroll_total_allowances_non_negative'),
            models.CheckConstraint(check=models.Q(total_bonuses__gte=0),                            name='payroll_total_bonuses_non_negative'),
            models.CheckConstraint(check=models.Q(total_deductions__gte=0),                         name='payroll_total_deductions_non_negative'),
            models.CheckConstraint(check=models.Q(total_statutory_deductions__gte=0),               name='payroll_statutory_deductions_non_negative'),
            models.CheckConstraint(check=models.Q(total_voluntary_deductions__gte=0),               name='payroll_voluntary_deductions_non_negative'),
            models.CheckConstraint(check=models.Q(nssf_employer__gte=0),                            name='payroll_nssf_employer_non_negative'),
            models.CheckConstraint(check=models.Q(employer_total_cost__gte=0),                      name='payroll_employer_total_cost_non_negative'),
            models.CheckConstraint(check=models.Q(exchange_rate__gt=0),                             name='payroll_exchange_rate_positive'),
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
        suffix = " [REVERSED]" if self.reversed else (
            " [CANCELLED]" if self.status == 'CANCELLED' else ""
        )
        label = self.pay_period_label or f"{self.pay_period_start} to {self.pay_period_end}"
        return f"{self.staff.full_name()} — {label}{suffix}"
 
    # =========================================================================
    # VALIDATION
    # =========================================================================
 
    def clean(self):
        super().clean()
        errors = {}
 
        if self.pay_period_start and self.pay_period_end:
            if self.pay_period_end < self.pay_period_start:
                errors['pay_period_end'] = "Pay period end cannot be before start"
 
        if self.fiscal_period_id:
            fp = self.fiscal_period
 
            if self.pay_period_start and self.pay_period_start < fp.start_date:
                errors['pay_period_start'] = (
                    f"Pay period cannot start before fiscal period start date ({fp.start_date})"
                )
 
            if self.pay_period_end and self.pay_period_end > fp.end_date:
                errors['pay_period_end'] = (
                    f"Pay period cannot end after fiscal period end date ({fp.end_date})"
                )
 
            if self.payment_date:
                if self.payment_date < fp.start_date:
                    errors['payment_date'] = (
                        f"Payment date cannot be before fiscal period start ({fp.start_date})"
                    )
                from datetime import timedelta
                max_allowed = fp.end_date
                if hasattr(fp, 'grace_period_days') and fp.grace_period_days > 0:
                    max_allowed = fp.end_date + timedelta(days=fp.grace_period_days)
                if self.payment_date > max_allowed:
                    grace_note = (
                        f" (including {fp.grace_period_days} days grace period)"
                        if hasattr(fp, 'grace_period_days') and fp.grace_period_days > 0
                        else ""
                    )
                    errors['payment_date'] = (
                        f"Payment date cannot be after fiscal period end date "
                        f"({fp.end_date}){grace_note}"
                    )
 
            if hasattr(fp, 'is_closed') and fp.is_closed:
                if not self.pk:
                    errors['fiscal_period'] = "Cannot create payroll in a closed fiscal period"
                elif not self.reversed and self.status != 'CANCELLED':
                    errors['fiscal_period'] = "Cannot modify active payroll in a closed fiscal period"
 
        if self.payment_date and self.pay_period_start:
            if self.payment_date < self.pay_period_start:
                errors['payment_date'] = "Payment date should not be before pay period starts"
 
        if self.reversed and not self.reversal_reason:
            errors['reversal_reason'] = "Reversal reason is required"
 
        if self.reversed and self.status == 'PAID' and not self.reversal_approved_by_id:
            errors['reversal_approved_by_id'] = (
                "Finance/HR Director approval required to reverse paid payroll"
            )
 
        if self.reversed and self.status == 'CANCELLED':
            errors['reversed'] = "Cannot reverse a cancelled payroll"
 
        if (self.days_worked is not None and self.total_working_days is not None
                and self.days_worked > self.total_working_days):
            errors['days_worked'] = "Days worked cannot exceed total working days"
 
        if self.exchange_rate is not None and self.exchange_rate <= 0:
            errors['exchange_rate'] = "Exchange rate must be greater than zero"
 
        if self.pk and self.gross_pay > Decimal('0.00'):
            if self.net_pay > self.gross_pay:
                errors.setdefault('__all__', []).append(
                    f"Net pay ({self.net_pay}) cannot exceed gross pay ({self.gross_pay})."
                )
            expected_gross = self.basic_salary + self.total_allowances + self.total_bonuses
            if abs(expected_gross - self.gross_pay) > Decimal('0.01'):
                errors.setdefault('__all__', []).append(
                    f"Gross pay ({self.gross_pay}) is inconsistent: "
                    f"basic ({self.basic_salary}) + allowances ({self.total_allowances}) "
                    f"+ bonuses ({self.total_bonuses}) = {expected_gross}. Recalculate."
                )
            expected_deductions = self.total_statutory_deductions + self.total_voluntary_deductions
            if abs(expected_deductions - self.total_deductions) > Decimal('0.01'):
                errors.setdefault('__all__', []).append(
                    f"Total deductions ({self.total_deductions}) is inconsistent: "
                    f"statutory ({self.total_statutory_deductions}) + voluntary "
                    f"({self.total_voluntary_deductions}) = {expected_deductions}. Recalculate."
                )
 
        if errors:
            raise ValidationError(errors)
 
    # =========================================================================
    # SAVE
    # =========================================================================
 
    def save(self, *args, **kwargs):
        if not self.payment_date and self.pay_period_end:
            self.payment_date = self.pay_period_end
 
        if not self.fiscal_period_id and self.pay_period_start and self.pay_period_end:
            self.fiscal_period = self.get_applicable_fiscal_period()
 
        if not self.pay_period_label and self.pay_period_start:
            if self.pay_frequency == 'MONTHLY':
                self.pay_period_label = self.pay_period_start.strftime('%B %Y')
            elif self.pay_frequency == 'WEEKLY':
                self.pay_period_label = f"Week of {self.pay_period_start.strftime('%b %d, %Y')}"
            else:
                self.pay_period_label = (
                    f"{self.pay_period_start.strftime('%b %d')} – "
                    f"{self.pay_period_end.strftime('%b %d, %Y')}"
                )
 
        if self.reversed and not self.statutory_reversals_required:
            self.statutory_reversals_required = self.requires_statutory_adjustments()
 
        super().save(*args, **kwargs)
 
    # =========================================================================
    # FISCAL PERIOD HELPER
    # =========================================================================
 
    def get_applicable_fiscal_period(self):
        from core.models import FiscalPeriod
        fiscal_period = FiscalPeriod.objects.filter(
            start_date__lte=self.pay_period_start,
            end_date__gte=self.pay_period_end,
            is_active=True,
        ).first()
        if not fiscal_period:
            raise ValidationError(
                f"No active fiscal period found for pay period "
                f"{self.pay_period_start} to {self.pay_period_end}. "
                "Create or activate the appropriate fiscal period first."
            )
        return fiscal_period
 
    # =========================================================================
    # BACKWARD COMPATIBILITY PROPERTIES
    # =========================================================================
 
    @property
    def period_start(self):
        return self.pay_period_start
 
    @property
    def period_end(self):
        return self.pay_period_end
 
    # =========================================================================
    # STATUS PROPERTIES
    # =========================================================================
 
    @property
    def is_active(self):
        return not self.reversed and self.status != 'CANCELLED'
 
    @property
    def effective_net_pay(self):
        return self.net_pay if self.is_active else Decimal('0.00')
 
    @property
    def effective_net_pay_in_school_currency(self):
        return self.net_pay_in_school_currency if self.is_active else Decimal('0.00')
 
    @property
    def effective_gross_pay(self):
        return self.gross_pay if self.is_active else Decimal('0.00')
 
    @property
    def effective_employer_cost(self):
        return self.employer_total_cost if self.is_active else Decimal('0.00')
 
    @property
    def effective_employer_cost_in_school_currency(self):
        return self.employer_cost_in_school_currency if self.is_active else Decimal('0.00')
 
    @property
    def payroll_state(self):
        if self.reversed:
            return "REVERSED"
        return self.status
 
    # =========================================================================
    # PAYMENT TRACKING
    # =========================================================================
 
    @property
    def total_paid(self):
        return (
            self.salary_payments.aggregate(total=models.Sum('amount'))['total']
            or Decimal('0.00')
        )
 
    @property
    def balance_due(self):
        return max(self.net_pay - self.total_paid, Decimal('0.00'))
 
    @property
    def is_fully_paid(self):
        return self.total_paid >= self.net_pay
 
    @property
    def payment_completion_status(self):
        paid = self.total_paid
        if paid <= Decimal('0.00'):
            return 'UNPAID'
        if paid < self.net_pay:
            return 'PARTIAL'
        return 'FULLY_PAID'
 
    @property
    def payment_completion_display(self):
        return {
            'UNPAID':     'Unpaid',
            'PARTIAL':    'Partially Paid',
            'FULLY_PAID': 'Fully Paid',
        }.get(self.payment_completion_status, 'Unknown')
 
    # =========================================================================
    # REVERSAL CHECKS
    # =========================================================================
 
    def can_be_reversed(self):
        if self.reversed:
            return False, "Payroll already reversed"
        if self.status == 'CANCELLED':
            return False, "Cannot reverse a cancelled payroll"
        if self.fiscal_period_id and getattr(self.fiscal_period, 'is_closed', False):
            return False, "Cannot reverse payroll from closed fiscal period"
        if self.status == 'PAID':
            if not self.reversal_approved_by_id:
                return False, "Reversal of paid payroll requires Finance/HR Director approval"
            if self.statutory_reversals_required and not self.statutory_adjustments_notes:
                return False, "Statutory adjustment plan required for paid payroll reversal"
        return True, "OK"
 
    def requires_statutory_adjustments(self):
        if self.status == 'PAID':
            return self.deductions.filter(
                deduction_type__in=['PAYE', 'SOCIAL_SECURITY', 'LOCAL_TAX']
            ).exists()
        return False
 
    # =========================================================================
    # USER RETRIEVAL
    # =========================================================================
 
    def _get_user(self, user_id):
        if not user_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            return get_user_model().objects.using('default').get(id=user_id)
        except Exception as e:
            logger.error(f"Error fetching user {user_id}: {e}")
            return None
 
    def get_approved_by_user(self):          return self._get_user(self.approved_by_id)
    def get_paid_by_user(self):              return self._get_user(self.paid_by_id)
    def get_reversed_by_user(self):          return self._get_user(self.reversed_by_id)
    def get_reversal_approved_by_user(self): return self._get_user(self.reversal_approved_by_id)
 
    # =========================================================================
    # CALCULATION METHODS
    # =========================================================================
 
    def calculate_gross_pay(self):
        self.total_allowances = (
            self.allowances.aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
        )
        self.total_bonuses = (
            self.bonuses.aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
        )
        self.gross_pay = self.basic_salary + self.total_allowances + self.total_bonuses
        return self.gross_pay
 
    def calculate_taxable_income(self):
        pretax_deductions = (
            self.deductions.filter(is_pretax=True)
            .aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
        )
        non_taxable_allowances = (
            self.allowances.filter(is_taxable=False)
            .aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
        )
        self.taxable_income = max(
            self.gross_pay - pretax_deductions - non_taxable_allowances,
            Decimal('0.00'),
        )
        return self.taxable_income
 
    def calculate_total_deductions(self):
        STATUTORY_TYPES = {'PAYE', 'SOCIAL_SECURITY', 'LOCAL_TAX'}
 
        statutory_total = voluntary_total = Decimal('0.00')
        paye_total = nssf_employee_total = lst_total = Decimal('0.00')
 
        for d in self.deductions.values('deduction_type', 'amount'):
            amount = d['amount']
            dtype  = d['deduction_type']
            if dtype in STATUTORY_TYPES:
                statutory_total += amount
                if dtype == 'PAYE':              paye_total          += amount
                elif dtype == 'SOCIAL_SECURITY': nssf_employee_total += amount
                elif dtype == 'LOCAL_TAX':       lst_total           += amount
            else:
                voluntary_total += amount
 
        self.total_statutory_deductions = statutory_total
        self.total_voluntary_deductions = voluntary_total
        self.total_deductions           = statutory_total + voluntary_total
        self.paye_amount                = paye_total
        self.nssf_employee              = nssf_employee_total
        self.local_service_tax          = lst_total
        return self.total_deductions
 
    def calculate_net_pay(self):
        self.net_pay = max(self.gross_pay - self.total_deductions, Decimal('0.00'))
        return self.net_pay
 
    def calculate_employer_cost(self):
        self.employer_total_cost = self.gross_pay + self.nssf_employer
        return self.employer_total_cost
 
    def recalculate_all(self):
        """
        Recalculate all amounts in the correct order:
        1. Gross pay
        2. Taxable income
        3. Deductions
        4. Net pay
        5. Employer cost
        6. School-currency equivalents
        """
        self.calculate_gross_pay()
        self.calculate_taxable_income()
        self.calculate_total_deductions()
        self.calculate_net_pay()
        self.calculate_employer_cost()
 
        rate = self.exchange_rate or Decimal('1.000000')
        self.net_pay_in_school_currency          = (self.net_pay          * rate).quantize(Decimal('0.01'))
        self.employer_cost_in_school_currency    = (self.employer_total_cost * rate).quantize(Decimal('0.01'))
 
        return {
            'basic_salary':                     self.basic_salary,
            'total_allowances':                 self.total_allowances,
            'total_bonuses':                    self.total_bonuses,
            'gross_pay':                        self.gross_pay,
            'taxable_income':                   self.taxable_income,
            'paye_amount':                      self.paye_amount,
            'nssf_employee':                    self.nssf_employee,
            'local_service_tax':                self.local_service_tax,
            'total_statutory_deductions':       self.total_statutory_deductions,
            'total_voluntary_deductions':       self.total_voluntary_deductions,
            'total_deductions':                 self.total_deductions,
            'net_pay':                          self.net_pay,
            'nssf_employer':                    self.nssf_employer,
            'employer_total_cost':              self.employer_total_cost,
            'net_pay_in_school_currency':       self.net_pay_in_school_currency,
            'employer_cost_in_school_currency': self.employer_cost_in_school_currency,
        }
 
    # =========================================================================
    # PRORATION
    # =========================================================================
 
    def calculate_prorated_salary(self, days_worked=None, total_days=None):
        days_worked = days_worked or self.days_worked
        total_days  = total_days  or self.total_working_days
        if not days_worked or not total_days or total_days == 0:
            return self.basic_salary
        from hr.models import Contract
        contract = Contract.get_staff_active_contract(self.staff)
        if not contract:
            return Decimal('0.00')
        proration_factor = Decimal(str(days_worked)) / Decimal(str(total_days))
        return (contract.basic_salary * proration_factor).quantize(Decimal('0.01'))
 
    def apply_proration(self, days_worked, total_days):
        self.days_worked        = days_worked
        self.total_working_days = total_days
        self.is_prorated        = True
        self.basic_salary       = self.calculate_prorated_salary(days_worked, total_days)
        self.save()
 
    # =========================================================================
    # ACCOUNT MAPPING HELPERS
    # =========================================================================
 
    def _get_payroll_mappings(self):
        from core.models import FinancialSettings
        settings = FinancialSettings.get_cached_instance()
        if not settings:
            return None
        return getattr(settings, 'payroll_account_mappings', None)
 
    def get_salary_expense_account(self):
        mappings = self._get_payroll_mappings()
        return getattr(mappings, 'salaries_expense_account', None) if mappings else None
 
    def get_salary_payable_account(self):
        mappings = self._get_payroll_mappings()
        return getattr(mappings, 'wages_payable_account', None) if mappings else None
 
    def get_cash_account(self):
        from core.models import FinancialSettings
        settings = FinancialSettings.get_cached_instance()
        if not settings:
            return None
        return settings.get_account_mappings().get_cash_or_bank_account(self.payment_method)
 
    def get_deduction_account(self, deduction_type):
        mappings = self._get_payroll_mappings()
        if not mappings:
            return None
        return {
            'PAYE':            getattr(mappings, 'payroll_tax_payable_account',     None),
            'SOCIAL_SECURITY': getattr(mappings, 'social_security_payable_account', None),
            'PENSION':         getattr(mappings, 'pension_payable_account',          None),
        }.get(deduction_type)
 
    def get_allowance_expense_account(self, allowance_type):
        mappings = self._get_payroll_mappings()
        if not mappings:
            return None
        account = {
            'HOUSING':   getattr(mappings, 'housing_allowance_expense_account',   None),
            'TRANSPORT': getattr(mappings, 'transport_allowance_expense_account', None),
            'MEDICAL':   getattr(mappings, 'medical_allowance_expense_account',   None),
            'OVERTIME':  getattr(mappings, 'overtime_expense_account',            None),
        }.get(allowance_type)
        return account or getattr(mappings, 'general_allowance_expense_account', None)
 
    # =========================================================================
    # CLASS METHODS
    # =========================================================================
 
    @classmethod
    def get_staff_payrolls_for_period(cls, staff, fiscal_period):
        return cls.objects.filter(
            staff=staff, fiscal_period=fiscal_period, reversed=False,
        ).order_by('pay_period_start')
 
    @classmethod
    def get_staff_payroll_for_month(cls, staff, year, month):
        import datetime as dt
        start_of_month = dt.date(year, month, 1)
        return cls.objects.filter(
            staff=staff,
            pay_period_start__lte=start_of_month,
            pay_period_end__gte=start_of_month,
            reversed=False,
        ).first()
 
    @classmethod
    def get_pending_payrolls(cls):
        return cls.objects.filter(status='DRAFT', reversed=False).order_by('payment_date')
 
    @classmethod
    def get_approved_unpaid_payrolls(cls):
        return cls.objects.filter(status='APPROVED', reversed=False).order_by('payment_date')
 
   

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

# =============================================================================
# PAYROLL PAYMENT
# =============================================================================

class PayrollPayment(BaseModel):
    """
    Tracks individual payment instalments against a payroll record.

    A payroll may be settled in one lump sum or across multiple instalments —
    e.g. 50% now, 50% at end of month. Each instalment is one PayrollPayment row.

    PAYMENT COMPLETION:
        payroll.total_paid              = SUM(PayrollPayment.amount)
        payroll.balance_due             = payroll.net_pay - payroll.total_paid
        payroll.payment_completion_status = UNPAID | PARTIAL | FULLY_PAID

    RULES:
    - Cannot record a payment against a reversed or cancelled payroll
    - Cannot record a payment that would push total_paid above net_pay
    - Each payment can use a different payment method and reference
    """

    # =========================================================================
    # CORE RELATIONSHIP
    # =========================================================================

    payroll = models.ForeignKey(
        Payroll,
        on_delete=models.CASCADE,
        related_name='salary_payments',
        verbose_name="Payroll",
        help_text="The payroll record this payment is against",
    )

    # =========================================================================
    # PAYMENT DETAILS
    # =========================================================================

    amount = models.DecimalField(
        "Amount Paid",
        max_digits=15, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Amount paid in this instalment (in payroll currency)",
    )

    payment_date = models.DateField(
        "Payment Date", db_index=True,
        help_text="Date this instalment was paid",
    )

    payment_method = models.ForeignKey(
        'core.PaymentMethod',
        on_delete=models.PROTECT,
        related_name='payroll_payment_instalments',
        verbose_name="Payment Method",
        help_text="How this instalment was paid (may differ from payroll default)",
    )

    payment_reference = models.CharField(
        "Payment Reference", max_length=100, blank=True,
        help_text="Bank transfer reference, cheque number, or mobile money reference",
    )

    # =========================================================================
    # JOURNAL ENTRY
    # =========================================================================

    journal_entry = models.ForeignKey(
        'finance.JournalEntry',
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='payroll_instalment_payments',
        verbose_name="Journal Entry",
        help_text="Journal entry recording this payment (Dr Wages Payable / Cr Cash)",
    )

    # =========================================================================
    # RECORDED BY
    # =========================================================================

    recorded_by_id = models.CharField(
        "Recorded By ID", max_length=50, blank=True,
        help_text="User who recorded this payment",
    )

    notes = models.TextField(
        "Notes", blank=True,
        help_text="Any notes about this payment instalment",
    )

    # =========================================================================
    # META CLASS
    # =========================================================================

    class Meta:
        verbose_name = "Payroll Payment"
        verbose_name_plural = "Payroll Payments"
        ordering = ['payment_date', 'created_at']
        indexes = [
            models.Index(fields=['payroll', 'payment_date']),
            models.Index(fields=['payment_date']),
            models.Index(fields=['payment_method']),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount__gt=0),
                name='payroll_payment_amount_positive',
            ),
        ]

    # =========================================================================
    # STRING REPRESENTATION
    # =========================================================================

    def __str__(self):
        return (
            f"{self.payroll.payroll_number} — "
            f"{self.payment_date} — "
            f"{self.amount}"
        )

    # =========================================================================
    # SAVE
    # =========================================================================

    def save(self, *args, **kwargs):
        """Auto-generate payment reference if not provided."""
        if not self.payment_reference and self.payment_date:
            from hr.utils import generate_payment_reference
            self.payment_reference = generate_payment_reference(self.payment_date)
        super().save(*args, **kwargs)

    # =========================================================================
    # VALIDATION
    # =========================================================================

    def clean(self):
        super().clean()
        errors = {}

        if self.payroll_id:
            if self.payroll.reversed:
                errors['payroll'] = "Cannot record a payment against a reversed payroll."

            if self.payroll.status == 'CANCELLED':
                errors['payroll'] = "Cannot record a payment against a cancelled payroll."

            existing_total = (
                self.payroll.salary_payments
                .exclude(pk=self.pk)
                .aggregate(total=models.Sum('amount'))['total']
                or Decimal('0.00')
            )
            if existing_total + (self.amount or Decimal('0.00')) > self.payroll.net_pay:
                overpayment = existing_total + self.amount - self.payroll.net_pay
                errors['amount'] = (
                    f"This payment would overpay the payroll by {overpayment}. "
                    f"Net pay is {self.payroll.net_pay}, already paid {existing_total}. "
                    f"Maximum instalment allowed: {self.payroll.net_pay - existing_total}."
                )

        if errors:
            raise ValidationError(errors)

    # =========================================================================
    # PROPERTIES
    # =========================================================================

    @property
    def is_full_payment(self):
        """True if this single instalment covers the entire net pay."""
        return self.amount >= self.payroll.net_pay

    @property
    def running_total_after(self):
        """Total paid including this instalment."""
        prior = (
            self.payroll.salary_payments
            .filter(payment_date__lte=self.payment_date)
            .exclude(pk=self.pk)
            .aggregate(total=models.Sum('amount'))['total']
            or Decimal('0.00')
        )
        return prior + self.amount

    # =========================================================================
    # USER RETRIEVAL
    # =========================================================================

    def get_recorded_by_user(self):
        if not self.recorded_by_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            return get_user_model().objects.using('default').get(id=self.recorded_by_id)
        except Exception as e:
            logger.error(f"Error fetching recorded_by user: {e}")
            return None