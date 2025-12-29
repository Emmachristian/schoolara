# fees/models.py

"""
Student Fee Management Models

Comprehensive fee management system with:
- Student Account Tracking
- Fee Structures and Categories
- Invoice and Payment Management
- Scholarship Programs
- Discount System
- Refund Management

All user tracking handled automatically by BaseModel
"""

from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from decimal import Decimal
import logging

from utils.models import BaseModel
from core.models import PaymentMethod, TaxRate, FiscalYear, FiscalPeriod
from academics.models import AcademicLevel, Class, AcademicSession
from students.models import Student

logger = logging.getLogger(__name__)


# =============================================================================
# STUDENT ACCOUNT MODELS
# =============================================================================

class StudentAccount(BaseModel):
    """Student financial account for tracking balances and transactions"""
    
    ACCOUNT_STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('SUSPENDED', 'Suspended'),
        ('FROZEN', 'Frozen'),
        ('CLOSED', 'Closed'),
    ]
    
    # -------------------------------------------------------------------------
    # CORE RELATIONSHIP
    # -------------------------------------------------------------------------
    
    student = models.OneToOneField(
        Student,
        verbose_name="Student",
        on_delete=models.CASCADE,
        related_name='financial_account'
    )
    
    # -------------------------------------------------------------------------
    # ACCOUNT BALANCES
    # -------------------------------------------------------------------------
    
    current_balance = models.DecimalField(
        "Current Balance",
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Positive = Credit (overpayment), Negative = Debit (outstanding)"
    )
    total_fees_charged = models.DecimalField(
        "Total Fees Charged",
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )
    total_payments_received = models.DecimalField(
        "Total Payments Received",
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )
    total_discounts_applied = models.DecimalField(
        "Total Discounts Applied",
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )
    total_refunds_issued = models.DecimalField(
        "Total Refunds Issued",
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )
    
    # -------------------------------------------------------------------------
    # CREDIT LIMITS AND SETTINGS
    # -------------------------------------------------------------------------
    
    credit_limit = models.DecimalField(
        "Credit Limit",
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Maximum negative balance allowed"
    )
    
    # -------------------------------------------------------------------------
    # ACCOUNT STATUS
    # -------------------------------------------------------------------------
    
    status = models.CharField(
        "Account Status",
        max_length=10,
        choices=ACCOUNT_STATUS_CHOICES,
        default='ACTIVE',
        db_index=True
    )
    
    # -------------------------------------------------------------------------
    # LAST TRANSACTION TRACKING
    # -------------------------------------------------------------------------
    
    last_transaction_date = models.DateTimeField("Last Transaction Date", null=True, blank=True)
    last_payment_date = models.DateTimeField("Last Payment Date", null=True, blank=True)
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Student Account"
        verbose_name_plural = "Student Accounts"
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['student']),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.student.get_full_name()} - Balance: {self.current_balance}"


class AccountTransaction(BaseModel):
    """Individual transactions on student accounts"""
    
    TRANSACTION_TYPES = [
        ('CREDIT', 'Credit'),
        ('DEBIT', 'Debit'),
        ('PAYMENT', 'Payment'),
        ('INVOICE', 'Invoice'),
        ('DISCOUNT', 'Discount'),
        ('REFUND', 'Refund'),
        ('ADJUSTMENT', 'Adjustment'),
        ('TRANSFER', 'Transfer'),
    ]
    
    # -------------------------------------------------------------------------
    # CORE RELATIONSHIPS
    # -------------------------------------------------------------------------
    
    student_account = models.ForeignKey(
        StudentAccount,
        verbose_name="Student Account",
        on_delete=models.CASCADE,
        related_name='transactions'
    )
    transaction_type = models.CharField(
        "Transaction Type",
        max_length=15,
        choices=TRANSACTION_TYPES,
        db_index=True
    )
    amount = models.DecimalField(
        "Amount",
        max_digits=12,
        decimal_places=2
    )
    description = models.TextField("Description")
    balance_after = models.DecimalField(
        "Balance After Transaction",
        max_digits=12,
        decimal_places=2
    )
    
    # -------------------------------------------------------------------------
    # RELATED OBJECTS
    # -------------------------------------------------------------------------
    
    invoice = models.ForeignKey(
        'FeeInvoice',
        verbose_name="Related Invoice",
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    payment = models.ForeignKey(
        'Payment',
        verbose_name="Related Payment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    
    # -------------------------------------------------------------------------
    # PERIOD TRACKING
    # -------------------------------------------------------------------------
    
    academic_session = models.ForeignKey(
        AcademicSession,
        verbose_name="Academic Session",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='account_transactions',
        help_text="Academic session this transaction relates to"
    )
    
    fiscal_period = models.ForeignKey(
        FiscalPeriod,
        verbose_name="Fiscal Period",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='account_transactions',
        help_text="Fiscal period when this transaction was recorded"
    )
    
    # -------------------------------------------------------------------------
    # TRANSACTION METADATA
    # -------------------------------------------------------------------------
    
    reference_number = models.CharField("Reference Number", max_length=50, blank=True)
    processed_by_id = models.CharField(
        "Processed By ID",
        max_length=50,
        null=True,
        blank=True,
        help_text="User ID who processed this transaction"
    )
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Account Transaction"
        verbose_name_plural = "Account Transactions"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['student_account', '-created_at']),
            models.Index(fields=['transaction_type']),
            models.Index(fields=['reference_number']),
            models.Index(fields=['academic_session']),
            models.Index(fields=['fiscal_period']),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.get_transaction_type_display()} - {self.amount}"


# =============================================================================
# FEE STRUCTURE MODELS
# =============================================================================

class DisplayGroup(BaseModel):
    """Groups fee categories for display purposes on invoices and receipts"""
    
    # -------------------------------------------------------------------------
    # BASIC INFORMATION
    # -------------------------------------------------------------------------
    
    name = models.CharField("Display Group Name", max_length=100, unique=True)
    description = models.TextField("Description", blank=True)
    display_order = models.PositiveIntegerField(
        "Display Order", 
        default=1,
        help_text="Lower numbers appear first on invoices"
    )
    color_code = models.CharField(
        "Color Code",
        max_length=7,
        default="#6f42c1",
        help_text="Hex color code for display (e.g., #2E86AB)"
    )
    
    # -------------------------------------------------------------------------
    # GROUPING BEHAVIOR - NEW FLAG
    # -------------------------------------------------------------------------
    
    show_as_group = models.BooleanField(
        "Show as Group",
        default=True,
        help_text=(
            "If checked, items in this group are displayed together under the group header. "
            "If unchecked, items are shown individually without grouping."
        )
    )
    
    show_group_subtotal = models.BooleanField(
        "Show Group Subtotal",
        default=True,
        help_text="Show subtotal for this group (only applies when 'Show as Group' is checked)"
    )
    
    # -------------------------------------------------------------------------
    # STATUS
    # -------------------------------------------------------------------------
    
    is_active = models.BooleanField("Is Active", default=True, db_index=True)
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Display Group"
        verbose_name_plural = "Display Groups"
        ordering = ['display_order', 'name']
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return self.name


# fees/models.py

class FeesCategory(BaseModel):
    """Categories of fees with detailed configuration"""
    
    FREQUENCY_CHOICES = [
        ('MONTHLY', 'Monthly'),
        ('TERMLY', 'Per Term'),
        ('YEARLY', 'Yearly'),
        ('ONE_TIME', 'One Time'),
        ('DAILY', 'Daily'),
        ('WEEKLY', 'Weekly'),
    ]
    
    APPLICABILITY_CHOICES = [
        ('ALL', 'All Students'),
        ('DAY_SCHOLARS', 'Day Scholars Only'),
        ('BOARDERS', 'Boarders Only'),
        ('WEEKLY_BOARDERS', 'Weekly Boarders Only'),
        ('FULL_BOARDERS', 'Full Boarders Only'),
        ('FLEXI_BOARDERS', 'Flexible Boarders Only'),
        ('NEW_STUDENTS', 'New Students Only'),
        ('CONTINUING_STUDENTS', 'Continuing Students Only'),
        ('SCHOLARSHIP_STUDENTS', 'Scholarship Students'),
        ('OPTIONAL', 'Optional/Elective'),
    ]
    
    CATEGORY_TYPE_CHOICES = [
        ('TUITION', 'Tuition Fee'),
        ('BOARDING', 'Boarding Fee'),
        ('MEALS', 'Meals Fee'),
        ('LAUNDRY', 'Laundry Fee'),
        ('TRANSPORT', 'Transport Fee'),
        ('UNIFORM', 'Uniform Fee'),
        ('BOOKS', 'Books & Materials'),
        ('EXAM', 'Examination Fee'),
        ('SPORT', 'Sports Fee'),
        ('CLUB', 'Club/Activity Fee'),
        ('REGISTRATION', 'Registration Fee'),
        ('ADMISSION', 'Admission Fee'),
        ('DEVELOPMENT', 'Development Levy'),
        ('MEDICAL', 'Medical Fee'),
        ('INSURANCE', 'Insurance Fee'),
        ('LIBRARY', 'Library Fee'),
        ('TECHNOLOGY', 'Technology Fee'),
        ('LABORATORY', 'Laboratory Fee'),
        ('FIELD_TRIP', 'Field Trip'),
        ('GRADUATION', 'Graduation Fee'),
        ('LATE_PAYMENT', 'Late Payment Fee'),
        ('MISCELLANEOUS', 'Miscellaneous'),
        ('OTHER', 'Other'),
    ]
    
    # -------------------------------------------------------------------------
    # BASIC INFORMATION
    # -------------------------------------------------------------------------
    
    name = models.CharField("Fee Name", max_length=100, unique=True)
    code = models.CharField(
        "Fee Code", 
        max_length=20, 
        unique=True, 
        db_index=True,
        help_text="Unique code for this fee category (e.g., TUI001, BRD001)"
    )
    description = models.TextField("Description", blank=True)
    
    category_type = models.CharField(
        "Category Type",
        max_length=20,
        choices=CATEGORY_TYPE_CHOICES,
        default='OTHER',
        db_index=True,
        help_text="Type of fee - used by system to identify specific fees"
    )
    
    # -------------------------------------------------------------------------
    # FEE CONFIGURATION
    # -------------------------------------------------------------------------
    
    is_recurring = models.BooleanField("Recurring", default=True)
    frequency = models.CharField(
        "Frequency",
        max_length=20, 
        choices=FREQUENCY_CHOICES, 
        default='TERMLY'
    )
    
    # -------------------------------------------------------------------------
    # APPLICABILITY RULES
    # -------------------------------------------------------------------------
    
    applicability = models.CharField(
        "Applicable To",
        max_length=25,
        choices=APPLICABILITY_CHOICES,
        default='ALL'
    )
    
    applicable_levels = models.ManyToManyField(
        AcademicLevel,
        verbose_name="Applicable Academic Levels",
        blank=True,
        help_text="If empty, applies to all levels"
    )
    
    # -------------------------------------------------------------------------
    # DISPLAY AND ORGANIZATION
    # -------------------------------------------------------------------------
    
    display_group = models.ForeignKey(
        DisplayGroup,
        verbose_name="Display Group",
        null=True,
        blank=True,
        on_delete=models.SET_NULL
    )
    display_order = models.PositiveIntegerField("Display Order", default=1)
    
    # -------------------------------------------------------------------------
    # FINANCIAL SETTINGS
    # -------------------------------------------------------------------------
    
    is_mandatory = models.BooleanField("Mandatory", default=True)
    is_refundable = models.BooleanField("Refundable", default=True)
    allows_partial_payment = models.BooleanField("Allows Partial Payment", default=True)
    
    # -------------------------------------------------------------------------
    # TAX SETTINGS
    # -------------------------------------------------------------------------
    
    is_taxable = models.BooleanField("Taxable", default=False)
    default_tax_rate = models.DecimalField(
        "Default Tax Rate (%)",
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))]
    )
    
    # -------------------------------------------------------------------------
    # STATUS
    # -------------------------------------------------------------------------
    
    is_active = models.BooleanField("Active", default=True, db_index=True)
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Fee Category"
        verbose_name_plural = "Fee Categories"
        ordering = ['display_order', 'name']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['category_type']),  
            models.Index(fields=['is_active']),
            models.Index(fields=['applicability']),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.name} ({self.get_category_type_display()})"
    
    # ✅ NEW: Helper methods
    def is_boarding_related(self):
        """Check if this is a boarding-related fee"""
        return self.category_type in ['BOARDING', 'MEALS', 'LAUNDRY']
    
    def is_academic_related(self):
        """Check if this is an academic fee"""
        return self.category_type in ['TUITION', 'EXAM', 'BOOKS', 'LIBRARY', 'LABORATORY']


class FeesStructure(BaseModel):
    """Fee structure supporting multiple academic levels and sessions"""
    
    STRUCTURE_TYPE_CHOICES = [
        ('STANDARD', 'Standard Structure'),
        ('DAY_SCHOLAR', 'Day Scholar Structure'),
        ('BOARDER', 'Boarder Structure'),
        ('WEEKLY_BOARDER', 'Weekly Boarder Structure'),
        ('FULL_BOARDER', 'Full Boarder Structure'),
        ('FLEXI_BOARDER', 'Flexible Boarder Structure'),
        ('SCHOLARSHIP', 'Scholarship Structure'),
        ('CUSTOM', 'Custom Structure'),
        ('STAFF_CHILD', 'Staff Child Structure'),
        ('SIBLING_DISCOUNT', 'Sibling Discount Structure'),
        ('NEED_BASED', 'Need-Based Structure'),
        ('MERIT_BASED', 'Merit-Based Structure'),
    ]
    
    # -------------------------------------------------------------------------
    # MULTI-SESSION SUPPORT
    # -------------------------------------------------------------------------
    
    applicable_sessions = models.ManyToManyField(
        AcademicSession,
        verbose_name="Applicable Academic Sessions",
        help_text="Academic sessions where this fee structure applies"
    )
    
    # -------------------------------------------------------------------------
    # ACADEMIC LEVELS AND CLASSES
    # -------------------------------------------------------------------------
    
    academic_levels = models.ManyToManyField(
        AcademicLevel,
        verbose_name="Academic Levels",
        related_name='fee_structures',
        help_text="Academic levels this structure applies to (e.g., Form 1, Form 2, Form 3)"
    )
    
    applicable_classes = models.ManyToManyField(
        Class,
        verbose_name="Applicable Classes",
        blank=True,
        help_text="Leave empty to apply to ALL classes in the selected academic levels"
    )
    
    # -------------------------------------------------------------------------
    # BASIC INFORMATION
    # -------------------------------------------------------------------------
    
    name = models.CharField(
        "Structure Name", 
        max_length=100, 
        help_text="Name of this fee structure (e.g., 'Secondary Day Scholar Fees')"
    )
    description = models.TextField("Description", blank=True)
    
    # -------------------------------------------------------------------------
    # STRUCTURE TYPE AND APPLICABILITY
    # -------------------------------------------------------------------------
    
    structure_type = models.CharField(
        "Structure Type",
        max_length=20,
        choices=STRUCTURE_TYPE_CHOICES,
        default='STANDARD',
        db_index=True
    )
    
    boarding_type_filter = models.CharField(
        "Boarding Type Filter",
        max_length=20,
        choices=[
            ('ALL', 'All Students'),
            ('DAY_ONLY', 'Day Scholars Only'),
            ('BOARDER_ONLY', 'Boarders Only'),
            ('FULL_BOARDER', 'Full Boarders Only'),
            ('WEEKLY_BOARDER', 'Weekly Boarders Only'),
            ('FLEXI_BOARDER', 'Flexible Boarders Only'),
        ],
        default='ALL',
        help_text="Filter by student boarding status"
    )
    
    student_type_filter = models.CharField(
        "Student Type Filter",
        max_length=20,
        choices=[
            ('ALL', 'All Students'),
            ('NEW_ONLY', 'New Students Only'),
            ('CONTINUING_ONLY', 'Continuing Students Only'),
            ('SCHOLARSHIP_ONLY', 'Scholarship Students Only'),
        ],
        default='ALL',
        help_text="Filter by student enrollment type"
    )
    
    # -------------------------------------------------------------------------
    # AUTO-APPLICATION CRITERIA
    # -------------------------------------------------------------------------
    
    auto_apply_criteria = models.JSONField(
        "Auto-Apply Criteria",
        default=dict,
        blank=True,
        help_text="JSON criteria for automatic application of this structure"
    )
    
    # -------------------------------------------------------------------------
    # PAYMENT TERMS
    # -------------------------------------------------------------------------
    
    payment_terms_days = models.PositiveIntegerField(
        "Payment Terms (Days)",
        default=30,
        help_text="Number of days from invoice date for payment"
    )
    
    # -------------------------------------------------------------------------
    # LATE FEE CONFIGURATION
    # -------------------------------------------------------------------------
    
    charges_late_fee = models.BooleanField("Charges Late Fee", default=False)
    late_fee_amount = models.DecimalField(
        "Late Fee Amount",
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00')
    )
    late_fee_percentage = models.DecimalField(
        "Late Fee Percentage",
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00')
    )
    grace_period_days = models.PositiveIntegerField(
        "Grace Period (Days)",
        default=7,
        help_text="Days after due date before late fees apply"
    )
    
    # -------------------------------------------------------------------------
    # PRIORITY FOR STRUCTURE SELECTION
    # -------------------------------------------------------------------------
    
    priority = models.PositiveIntegerField(
        "Priority",
        default=100,
        help_text="Lower number = higher priority when multiple structures match a student"
    )
    
    # -------------------------------------------------------------------------
    # STATUS AND VALIDITY
    # -------------------------------------------------------------------------
    
    is_active = models.BooleanField("Active", default=True, db_index=True)
    effective_date = models.DateField("Effective Date", default=timezone.now, db_index=True)
    expiry_date = models.DateField("Expiry Date", null=True, blank=True, db_index=True)
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Fee Structure"
        verbose_name_plural = "Fee Structures"
        unique_together = ('name', 'structure_type', 'boarding_type_filter')
        ordering = ['structure_type', 'priority', 'name']
        indexes = [
            models.Index(fields=['structure_type', 'is_active']),
            models.Index(fields=['boarding_type_filter']),
            models.Index(fields=['student_type_filter']),
            models.Index(fields=['priority']),
            models.Index(fields=['effective_date', 'expiry_date']),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.name} ({self.get_structure_type_display()})"


class FeesStructureItem(BaseModel):
    """Individual items within a fee structure"""
    
    # -------------------------------------------------------------------------
    # CORE RELATIONSHIPS
    # -------------------------------------------------------------------------
    
    fee_structure = models.ForeignKey(
        FeesStructure, 
        verbose_name="Fee Structure",
        on_delete=models.CASCADE, 
        related_name='items'
    )
    fee_category = models.ForeignKey(
        FeesCategory, 
        verbose_name="Fee Category",
        on_delete=models.CASCADE
    )
    amount = models.DecimalField(
        "Amount",
        max_digits=10, 
        decimal_places=2, 
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    
    # -------------------------------------------------------------------------
    # TAX AND DISCOUNT DEFAULTS
    # -------------------------------------------------------------------------
    
    tax_percentage = models.DecimalField(
        "Tax Percentage",
        max_digits=5, 
        decimal_places=2, 
        default=Decimal('0.00')
    )
    discount_percentage = models.DecimalField(
        "Discount Percentage",
        max_digits=5, 
        decimal_places=2, 
        default=Decimal('0.00')
    )
    
    # -------------------------------------------------------------------------
    # SCHOLARSHIP ELIGIBILITY
    # -------------------------------------------------------------------------
    
    scholarship_eligible = models.BooleanField(
        "Scholarship Eligible",
        default=True,
        help_text="Whether this fee item is eligible for scholarship discounts"
    )
    
    max_scholarship_discount = models.DecimalField(
        "Maximum Scholarship Discount",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum scholarship discount percentage for this item"
    )
    
    # -------------------------------------------------------------------------
    # CONDITIONAL LOGIC
    # -------------------------------------------------------------------------
    
    is_conditional = models.BooleanField("Conditional", default=False)
    condition_description = models.TextField("Condition Description", blank=True)
    condition_criteria = models.JSONField(
        "Condition Criteria",
        default=dict,
        blank=True,
        help_text="JSON criteria for when this item should be included"
    )
    
    # -------------------------------------------------------------------------
    # PAYMENT SCHEDULING
    # -------------------------------------------------------------------------
    
    is_payable_in_installments = models.BooleanField("Payable in Installments", default=False)
    number_of_installments = models.PositiveIntegerField("Number of Installments", default=1)
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Fee Structure Item"
        verbose_name_plural = "Fee Structure Items"
        ordering = ['fee_structure', 'fee_category']
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.fee_structure.name} - {self.fee_category.name}"


# =============================================================================
# INVOICE AND PAYMENT MODELS
# =============================================================================

class FeeInvoice(BaseModel):
    """Invoice model with integrated scholarship and discount support"""
    
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('PENDING', 'Pending Payment'),
        ('PARTIALLY_PAID', 'Partially Paid'),
        ('PAID', 'Paid in Full'),
        ('OVERDUE', 'Overdue'),
        ('CANCELLED', 'Cancelled'),
        ('VOID', 'Void'),
        ('BAD_DEBT', 'Bad Debt'),
        ('WRITTEN_OFF', 'Written Off'),
        ('UNCOLLECTIBLE', 'Uncollectible'),
    ]
    
    # -------------------------------------------------------------------------
    # IDENTIFICATION
    # -------------------------------------------------------------------------
    
    invoice_number = models.CharField("Invoice Number", max_length=50, unique=True, db_index=True)
    student = models.ForeignKey(
        Student, 
        verbose_name="Student",
        on_delete=models.CASCADE, 
        related_name='fee_invoices'
    )
    
    # -------------------------------------------------------------------------
    # ACADEMIC CONTEXT (What session is this invoice FOR?)
    # -------------------------------------------------------------------------
    
    academic_session = models.ForeignKey(
        AcademicSession,
        verbose_name="Academic Session",
        on_delete=models.PROTECT,
        related_name='fee_invoices',
        help_text="Academic session this invoice covers (e.g., Term 1 2024)"
    )
    
    # -------------------------------------------------------------------------
    # FISCAL CONTEXT (When/where was this invoice processed?)
    # -------------------------------------------------------------------------
    
    fiscal_period = models.ForeignKey(
        FiscalPeriod,
        verbose_name="Fiscal Period",
        on_delete=models.PROTECT,
        related_name='invoices',
        help_text="Fiscal period when this invoice was issued (for financial reporting)"
    )
    
    # -------------------------------------------------------------------------
    # FEE STRUCTURE
    # -------------------------------------------------------------------------
    
    fee_structure = models.ForeignKey(
        FeesStructure, 
        verbose_name="Fee Structure",
        on_delete=models.CASCADE,
        related_name='invoices'
    )
    
    # -------------------------------------------------------------------------
    # DATES
    # -------------------------------------------------------------------------
    
    issue_date = models.DateField("Issue Date", db_index=True)
    due_date = models.DateField("Due Date", db_index=True)
    
    # -------------------------------------------------------------------------
    # AMOUNTS
    # -------------------------------------------------------------------------
    
    subtotal_amount = models.DecimalField("Subtotal Amount", max_digits=12, decimal_places=2)
    discount_amount = models.DecimalField("Discount Amount", max_digits=12, decimal_places=2, default=Decimal('0.00'))
    scholarship_discount_amount = models.DecimalField(
        "Scholarship Discount Amount", 
        max_digits=12, 
        decimal_places=2, 
        default=Decimal('0.00')
    )
    tax_amount = models.DecimalField("Tax Amount", max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField("Total Amount", max_digits=12, decimal_places=2)
    paid_amount = models.DecimalField("Paid Amount", max_digits=12, decimal_places=2, default=Decimal('0.00'))
    balance = models.DecimalField("Balance", max_digits=12, decimal_places=2)
    
    # -------------------------------------------------------------------------
    # LATE FEES
    # -------------------------------------------------------------------------
    
    late_fee_amount = models.DecimalField("Late Fee Amount", max_digits=10, decimal_places=2, default=Decimal('0.00'))
    
    # -------------------------------------------------------------------------
    # STATUS AND FLAGS
    # -------------------------------------------------------------------------
    
    status = models.CharField("Status", max_length=15, choices=STATUS_CHOICES, default='PENDING', db_index=True)
    is_break_payment = models.BooleanField(
        "Break Period Invoice", 
        default=False,
        help_text="Invoice generated during break period"
    )

    # -------------------------------------------------------------------------
    # ACCOUNTING INTEGRATION
    # -------------------------------------------------------------------------
    
    revenue_account = models.ForeignKey(
        'finance.Account',
        verbose_name="Revenue Account",
        on_delete=models.PROTECT,
        related_name='fee_invoices',
        null=True,
        blank=True,
        help_text="Account to credit for this invoice (typically Student Fees Receivable)"
    )
    
    receivable_account = models.ForeignKey(
        'finance.Account',
        verbose_name="Accounts Receivable Account",
        on_delete=models.PROTECT,
        related_name='receivable_invoices',
        null=True,
        blank=True,
        help_text="Receivable account to debit (typically Accounts Receivable - Students)"
    )
    
    # -------------------------------------------------------------------------
    # SCHOLARSHIP AND DISCOUNT TRACKING
    # -------------------------------------------------------------------------
    
    has_scholarships_applied = models.BooleanField(
        "Has Scholarships Applied", 
        default=False
    )
    has_discounts_applied = models.BooleanField(
        "Has Discounts Applied", 
        default=False
    )
    
    auto_scholarships_applied = models.BooleanField(
        "Auto Scholarships Applied", 
        default=False
    )
    auto_discounts_applied = models.BooleanField(
        "Auto Discounts Applied", 
        default=False
    )
    
    # -------------------------------------------------------------------------
    # PAYMENT TERMS
    # -------------------------------------------------------------------------
    
    payment_terms = models.CharField("Payment Terms", max_length=200, blank=True)
    
    # -------------------------------------------------------------------------
    # NOTES AND REFERENCES
    # -------------------------------------------------------------------------
    
    notes = models.TextField("Notes", blank=True)
    internal_notes = models.TextField("Internal Notes", blank=True)
    
    # -------------------------------------------------------------------------
    # JOURNAL ENTRY INTEGRATION
    # -------------------------------------------------------------------------
    
    journal_entry = models.ForeignKey(
        'finance.JournalEntry',
        verbose_name="Journal Entry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='fee_invoices', 
        help_text="Journal entry created for this invoice"
    )
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Fee Invoice"
        verbose_name_plural = "Fee Invoices"
        ordering = ['-issue_date', '-created_at']
        indexes = [
            models.Index(fields=['invoice_number']),
            models.Index(fields=['student', 'academic_session']),
            models.Index(fields=['status']),
            models.Index(fields=['issue_date']),
            models.Index(fields=['due_date']),
            models.Index(fields=['fiscal_period']),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.invoice_number} - {self.student.get_full_name()}"


class FeeInvoiceItem(BaseModel):
    """Individual items within a fee invoice"""
    
    # -------------------------------------------------------------------------
    # CORE RELATIONSHIPS
    # -------------------------------------------------------------------------
    
    invoice = models.ForeignKey(
        FeeInvoice, 
        verbose_name="Invoice",
        on_delete=models.CASCADE, 
        related_name='items'
    )
    fee_category = models.ForeignKey(
        FeesCategory, 
        verbose_name="Fee Category",
        on_delete=models.CASCADE
    )
    description = models.CharField("Description", max_length=255, blank=True)
    quantity = models.DecimalField("Quantity", max_digits=8, decimal_places=2, default=Decimal('1.00'))
    unit_amount = models.DecimalField("Unit Amount", max_digits=10, decimal_places=2)
    amount = models.DecimalField("Amount", max_digits=10, decimal_places=2)
    
    # -------------------------------------------------------------------------
    # TAX DETAILS
    # -------------------------------------------------------------------------
    
    tax_percentage = models.DecimalField("Tax Percentage", max_digits=5, decimal_places=2, default=Decimal('0.00'))
    tax_amount = models.DecimalField("Tax Amount", max_digits=10, decimal_places=2, default=Decimal('0.00'))
    
    # -------------------------------------------------------------------------
    # REGULAR DISCOUNT DETAILS
    # -------------------------------------------------------------------------
    
    discount_percentage = models.DecimalField("Discount Percentage", max_digits=5, decimal_places=2, default=Decimal('0.00'))
    discount_amount = models.DecimalField("Regular Discount Amount", max_digits=10, decimal_places=2, default=Decimal('0.00'))
    
    # -------------------------------------------------------------------------
    # SCHOLARSHIP DISCOUNT DETAILS
    # -------------------------------------------------------------------------
    
    scholarship_discount_amount = models.DecimalField(
        "Scholarship Discount Amount", 
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0.00')
    )
    
    # -------------------------------------------------------------------------
    # TOTAL DISCOUNT AMOUNT
    # -------------------------------------------------------------------------
    
    total_discount_amount = models.DecimalField(
        "Total Discount Amount", 
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0.00')
    )
    
    final_amount = models.DecimalField("Final Amount", max_digits=10, decimal_places=2)
    
    # -------------------------------------------------------------------------
    # DISCOUNT TRACKING
    # -------------------------------------------------------------------------
    
    applied_discount = models.ForeignKey(
        'FeesDiscount',
        verbose_name="Applied Regular Discount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='applied_invoice_items'
    )
    
    # -------------------------------------------------------------------------
    # FLAGS FOR TRACKING
    # -------------------------------------------------------------------------
    
    has_scholarship_discount = models.BooleanField("Has Scholarship Discount", default=False)
    has_regular_discount = models.BooleanField("Has Regular Discount", default=False)
    
    # -------------------------------------------------------------------------
    # ORIGINAL AMOUNT
    # -------------------------------------------------------------------------
    
    original_amount = models.DecimalField(
        "Original Amount", 
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True
    )
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Fee Invoice Item"
        verbose_name_plural = "Fee Invoice Items"
        indexes = [
            models.Index(fields=['invoice', 'fee_category']),
            models.Index(fields=['has_scholarship_discount']),
            models.Index(fields=['has_regular_discount']),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.invoice.invoice_number} - {self.fee_category.name}"


class Payment(BaseModel):
    """Payment model with comprehensive tracking"""
    
    PAYMENT_STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
        ('CANCELLED', 'Cancelled'),
        ('REFUNDED', 'Refunded'),
    ]
    
    PAYER_RELATIONSHIP_CHOICES = [
        ('STUDENT', 'Student (Self)'),
        ('FATHER', 'Father'),
        ('MOTHER', 'Mother'),
        ('UNCLE', 'Uncle'),
        ('AUNT', 'Aunt'),
        ('BROTHER', 'Brother'),
        ('SISTER', 'Sister'),
        ('GUARDIAN', 'Guardian'),
        ('SPONSOR', 'Sponsor'),
        ('GRANDPARENT', 'Grandparent'),
        ('STEP_FATHER', 'Step Father'),
        ('STEP_MOTHER', 'Step Mother'),
        ('FOSTER_PARENT', 'Foster Parent'),
        ('OTHER', 'Other'),
    ]
    
    # -------------------------------------------------------------------------
    # IDENTIFICATION
    # -------------------------------------------------------------------------
    
    payment_number = models.CharField("Payment Number", max_length=50, unique=True, db_index=True)
    invoice = models.ForeignKey(
        FeeInvoice, 
        verbose_name="Invoice",
        on_delete=models.CASCADE, 
        related_name='payments'
    )
    student = models.ForeignKey(
        Student,
        verbose_name="Student",
        on_delete=models.CASCADE,
        related_name='payments'
    )
    
    # -------------------------------------------------------------------------
    # PAYMENT DETAILS
    # -------------------------------------------------------------------------
    
    amount = models.DecimalField(
        "Amount",
        max_digits=12, 
        decimal_places=2, 
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    amount_applied_to_invoice = models.DecimalField(
        "Amount Applied to Invoice",
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )
    overpayment_amount = models.DecimalField(
        "Overpayment Amount",
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )
    
    # -------------------------------------------------------------------------
    # PAYMENT METHOD DETAILS
    # -------------------------------------------------------------------------
    
    payment_date = models.DateField("Payment Date", db_index=True)
    payment_method = models.ForeignKey(
        PaymentMethod,
        verbose_name="Payment Method",
        on_delete=models.PROTECT,
        related_name='student_payments'
    )
    reference_number = models.CharField("Reference Number", max_length=100, blank=True, db_index=True)
    transaction_id = models.CharField("Transaction ID", max_length=100, blank=True, db_index=True)
    
    # -------------------------------------------------------------------------
    # BANK/CARD DETAILS
    # -------------------------------------------------------------------------
    
    bank_name = models.CharField("Bank Name", max_length=100, blank=True)
    account_number = models.CharField("Account Number", max_length=50, blank=True)
    cheque_number = models.CharField("Cheque Number", max_length=50, blank=True)
    cheque_date = models.DateField("Cheque Date", null=True, blank=True)
    
    # -------------------------------------------------------------------------
    # MOBILE MONEY DETAILS
    # -------------------------------------------------------------------------
    
    mobile_money_provider = models.CharField("Mobile Money Provider", max_length=50, blank=True)
    mobile_number = models.CharField(
        "Mobile Money Number", 
        max_length=20, 
        blank=True,
        help_text="Mobile money account number used for the transaction"
    )
    
    # -------------------------------------------------------------------------
    # PAYER INFORMATION
    # -------------------------------------------------------------------------
    
    paid_by_name = models.CharField(
        "Paid By (Name)", 
        max_length=200, 
        blank=True,
        null=True,
        help_text="Name of the person who made the payment"
    )
    paid_by_phone = models.CharField(
        "Paid By (Phone)", 
        max_length=20, 
        blank=True,
        null=True,
        help_text="Contact phone number of the person who made the payment"
    )
    paid_by_email = models.EmailField(
        "Paid By (Email)", 
        blank=True,
        null=True,
        help_text="Email address of the person who made the payment"
    )
    paid_by_relationship = models.CharField(
        "Relationship to Student",
        max_length=50,
        blank=True,
        null=True,
        choices=PAYER_RELATIONSHIP_CHOICES,
        help_text="Relationship of payer to the student"
    )

    # -------------------------------------------------------------------------
    # ACCOUNTING INTEGRATION
    # -------------------------------------------------------------------------
    
    deposit_account = models.ForeignKey(
        'finance.Account',
        verbose_name="Deposit Account",
        on_delete=models.PROTECT,
        related_name='fee_payments',
        help_text="Bank/Cash account where payment was deposited"
    )
    
    receivable_account = models.ForeignKey(
        'finance.Account',
        verbose_name="Receivable Account",
        on_delete=models.PROTECT,
        related_name='cleared_payments',
        null=True,
        blank=True,
        help_text="Accounts Receivable account to credit (clears the receivable)"
    )

    # -------------------------------------------------------------------------
    # FEES AND CHARGES ACCOUNTS
    # -------------------------------------------------------------------------
    
    processing_fee_account = models.ForeignKey(
        'finance.Account',
        verbose_name="Processing Fee Account",
        on_delete=models.PROTECT,
        related_name='processing_fee_payments',
        null=True,
        blank=True,
        help_text="Expense account for payment processing fees"
    )
    
    # -------------------------------------------------------------------------
    # STATUS AND VERIFICATION
    # -------------------------------------------------------------------------
    
    status = models.CharField(
        "Payment Status",
        max_length=12,
        choices=PAYMENT_STATUS_CHOICES,
        default='COMPLETED',
        db_index=True
    )
    is_verified = models.BooleanField("Verified", default=False, db_index=True)
    verified_by_id = models.CharField(
        "Verified By ID",
        max_length=50,
        null=True,
        blank=True,
        help_text="User ID who verified this payment"
    )
    verification_date = models.DateTimeField("Verification Date", null=True, blank=True)
    
    # -------------------------------------------------------------------------
    # RECEIPT DETAILS
    # -------------------------------------------------------------------------
    
    receipt_number = models.CharField("Receipt Number", max_length=50, unique=True, db_index=True)
    receipt_issued = models.BooleanField("Receipt Issued", default=False)
    receipt_issued_date = models.DateTimeField("Receipt Issued Date", null=True, blank=True)
    
    # -------------------------------------------------------------------------
    # PROCESSING DETAILS
    # -------------------------------------------------------------------------
    
    received_by_id = models.CharField(
        "Received By ID",
        max_length=50,
        null=True,
        blank=True,
        help_text="User ID who received this payment"
    )
    processed_by_id = models.CharField(
        "Processed By ID",
        max_length=50,
        null=True,
        blank=True,
        help_text="User ID who processed this payment"
    )
    
    # -------------------------------------------------------------------------
    # ADDITIONAL DETAILS
    # -------------------------------------------------------------------------
    
    remarks = models.TextField("Remarks", blank=True)
    internal_notes = models.TextField("Internal Notes", blank=True)
    
    # -------------------------------------------------------------------------
    # ACADEMIC CONTEXT (Which session was this payment for?)
    # -------------------------------------------------------------------------
    
    academic_session = models.ForeignKey(
        AcademicSession,
        verbose_name="Academic Session",
        on_delete=models.SET_NULL,
        null=True,
        related_name='payments',
        help_text="Academic session this payment is for (from invoice)"
    )
    
    # -------------------------------------------------------------------------
    # FISCAL CONTEXT (When was this payment received?)
    # -------------------------------------------------------------------------
    
    fiscal_period = models.ForeignKey(
        FiscalPeriod,
        verbose_name="Fiscal Period",
        on_delete=models.PROTECT,
        related_name='payments',
        help_text="Fiscal period when payment was received (for cash flow tracking)"
    )
    
    # -------------------------------------------------------------------------
    # BREAK PERIOD TRACKING
    # -------------------------------------------------------------------------
    
    is_break_payment = models.BooleanField(
        "Break Period Payment", 
        default=False,
        help_text="Payment made during break period"
    )
    
    # -------------------------------------------------------------------------
    # FEE BREAKDOWN
    # -------------------------------------------------------------------------
    
    fee_breakdown = models.JSONField("Fee Breakdown", default=dict, blank=True)
    
    # -------------------------------------------------------------------------
    # JOURNAL ENTRY INTEGRATION
    # -------------------------------------------------------------------------
    
    journal_entry = models.ForeignKey(
        'finance.JournalEntry',
        verbose_name="Journal Entry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='fee_payments',
        help_text="Journal entry created for this payment"
    )
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Payment"
        verbose_name_plural = "Payments"
        ordering = ['-payment_date', '-created_at']
        indexes = [
            models.Index(fields=['payment_number']),
            models.Index(fields=['student', 'payment_date']),
            models.Index(fields=['invoice']),
            models.Index(fields=['status']),
            models.Index(fields=['payment_date']),
            models.Index(fields=['reference_number']),
            models.Index(fields=['transaction_id']),
            models.Index(fields=['receipt_number']),
            models.Index(fields=['academic_session']),
            models.Index(fields=['fiscal_period']),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.payment_number} - {self.student.get_full_name()}"
    
    # -------------------------------------------------------------------------
    # HELPER METHODS
    # -------------------------------------------------------------------------
    
    def get_verified_by_user(self):
        """Get the user who verified this payment"""
        if not self.verified_by_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            return User.objects.using('default').get(id=self.verified_by_id)
        except Exception as e:
            logger.error(f"Error fetching verified_by user: {e}")
            return None
    
    def get_received_by_user(self):
        """Get the user who received this payment"""
        if not self.received_by_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            return User.objects.using('default').get(id=self.received_by_id)
        except Exception as e:
            logger.error(f"Error fetching received_by user: {e}")
            return None
    
    def get_processed_by_user(self):
        """Get the user who processed this payment"""
        if not self.processed_by_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            return User.objects.using('default').get(id=self.processed_by_id)
        except Exception as e:
            logger.error(f"Error fetching processed_by user: {e}")
            return None


# =============================================================================
# SCHOLARSHIP PROGRAM MODELS
# =============================================================================

class ScholarshipProgram(BaseModel):
    """Scholarship programs with detailed configuration"""
    
    SCHOLARSHIP_TYPES = [
        ('ACADEMIC_MERIT', 'Academic Merit'),
        ('SPORTS_EXCELLENCE', 'Sports Excellence'),
        ('ARTS_TALENT', 'Arts & Talent'),
        ('NEED_BASED', 'Need-Based'),
        ('STAFF_CHILD', 'Staff Child'),
        ('SIBLING_DISCOUNT', 'Sibling Discount'),
        ('MULTIPLE_SIBLING', 'Multiple Sibling Discount'),
        ('COMMUNITY_SERVICE', 'Community Service'),
        ('LEADERSHIP', 'Leadership Excellence'),
        ('SPECIAL_CIRCUMSTANCES', 'Special Circumstances'),
        ('ALUMNI_SPONSORED', 'Alumni Sponsored'),
        ('CORPORATE_SPONSORED', 'Corporate Sponsored'),
        ('GOVERNMENT_BURSARY', 'Government Bursary'),
        ('FULL_SCHOLARSHIP', 'Full Scholarship'),
        ('PARTIAL_SCHOLARSHIP', 'Partial Scholarship'),
        ('EMERGENCY_AID', 'Emergency Financial Aid'),
    ]
    
    DISCOUNT_TYPE_CHOICES = [
        ('PERCENTAGE', 'Percentage Discount'),
        ('FIXED_AMOUNT', 'Fixed Amount Discount'),
        ('FULL_WAIVER', 'Full Fee Waiver'),
        ('CATEGORY_SPECIFIC', 'Specific Fee Categories Only'),
    ]
    
    ELIGIBILITY_RENEWAL_CHOICES = [
        ('AUTOMATIC', 'Automatic Renewal'),
        ('PERFORMANCE_BASED', 'Performance-Based Review'),
        ('ANNUAL_APPLICATION', 'Annual Re-application Required'),
        ('ONE_TIME_ONLY', 'One-Time Award'),
    ]
    
    # -------------------------------------------------------------------------
    # BASIC PROGRAM INFORMATION
    # -------------------------------------------------------------------------
    
    name = models.CharField("Program Name", max_length=200)
    code = models.CharField("Program Code", max_length=50, unique=True, db_index=True)
    scholarship_type = models.CharField(
        "Scholarship Type", 
        max_length=30, 
        choices=SCHOLARSHIP_TYPES,
        db_index=True
    )
    description = models.TextField("Description")
    
    # -------------------------------------------------------------------------
    # FINANCIAL CONFIGURATION
    # -------------------------------------------------------------------------
    
    discount_type = models.CharField(
        "Discount Type", 
        max_length=20, 
        choices=DISCOUNT_TYPE_CHOICES
    )
    discount_percentage = models.DecimalField(
        "Discount Percentage",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))]
    )
    fixed_discount_amount = models.DecimalField(
        "Fixed Discount Amount",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )
    maximum_award_amount = models.DecimalField(
        "Maximum Award Amount Per Student",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )
    
    # -------------------------------------------------------------------------
    # APPLICABLE FEE CATEGORIES
    # -------------------------------------------------------------------------
    
    applicable_fee_categories = models.ManyToManyField(
        FeesCategory,
        verbose_name="Applicable Fee Categories",
        blank=True,
        help_text="Leave empty to apply to all fee categories"
    )
    
    # -------------------------------------------------------------------------
    # ELIGIBILITY CRITERIA
    # -------------------------------------------------------------------------
    
    minimum_gpa = models.DecimalField(
        "Minimum GPA Requirement",
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True
    )
    minimum_attendance_percentage = models.DecimalField(
        "Minimum Attendance Percentage",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True
    )
    family_income_threshold = models.DecimalField(
        "Family Income Threshold",
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum family income for need-based scholarships"
    )
    
    # -------------------------------------------------------------------------
    # ACADEMIC LEVEL RESTRICTIONS
    # -------------------------------------------------------------------------
    
    applicable_levels = models.ManyToManyField(
        AcademicLevel,
        verbose_name="Applicable Academic Levels",
        blank=True,
        help_text="Leave empty to apply to all levels"
    )
    
    # -------------------------------------------------------------------------
    # PROGRAM LIMITS AND BUDGET
    # -------------------------------------------------------------------------
    
    total_budget_amount = models.DecimalField(
        "Total Program Budget",
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True
    )
    maximum_recipients = models.PositiveIntegerField(
        "Maximum Number of Recipients",
        null=True,
        blank=True
    )
    current_budget_used = models.DecimalField(
        "Current Budget Used",
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00')
    )
    current_recipient_count = models.PositiveIntegerField(
        "Current Recipients",
        default=0
    )
    
    # -------------------------------------------------------------------------
    # TIME AND RENEWAL SETTINGS
    # -------------------------------------------------------------------------
    
    renewal_policy = models.CharField(
        "Renewal Policy",
        max_length=20,
        choices=ELIGIBILITY_RENEWAL_CHOICES,
        default='ANNUAL_APPLICATION'
    )
    maximum_duration_years = models.PositiveIntegerField(
        "Maximum Duration (Years)",
        default=1,
        help_text="Maximum years a student can receive this scholarship"
    )
    
    # -------------------------------------------------------------------------
    # APPLICATION AND AWARD PERIODS
    # -------------------------------------------------------------------------
    
    application_start_date = models.DateField("Application Start Date", null=True, blank=True)
    application_end_date = models.DateField("Application End Date", null=True, blank=True)
    award_announcement_date = models.DateField("Award Announcement Date", null=True, blank=True)
    
    # -------------------------------------------------------------------------
    # SPONSOR INFORMATION
    # -------------------------------------------------------------------------
    
    sponsor_name = models.CharField("Sponsor Name", max_length=200, blank=True)
    sponsor_contact = models.TextField("Sponsor Contact Information", blank=True)
    external_funding_source = models.CharField("External Funding Source", max_length=200, blank=True)
    
    # -------------------------------------------------------------------------
    # PROGRAM STATUS
    # -------------------------------------------------------------------------
    
    is_active = models.BooleanField("Is Active", default=True, db_index=True)
    is_accepting_applications = models.BooleanField("Accepting Applications", default=True)
    
    # -------------------------------------------------------------------------
    # ACADEMIC SESSION VALIDITY
    # -------------------------------------------------------------------------
    
    valid_sessions = models.ManyToManyField(
        AcademicSession,
        verbose_name="Valid Academic Sessions",
        blank=True,
        help_text="Sessions in which this program is available"
    )
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Scholarship Program"
        verbose_name_plural = "Scholarship Programs"
        ordering = ['name']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['scholarship_type']),
            models.Index(fields=['is_active']),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.name} ({self.code})"


class StudentScholarshipApplication(BaseModel):
    """Student applications for scholarships"""
    
    APPLICATION_STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('SUBMITTED', 'Submitted'),
        ('UNDER_REVIEW', 'Under Review'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('WAITLISTED', 'Waitlisted'),
        ('WITHDRAWN', 'Withdrawn'),
    ]
    
    # -------------------------------------------------------------------------
    # BASIC INFORMATION
    # -------------------------------------------------------------------------
    
    application_number = models.CharField("Application Number", max_length=50, unique=True, db_index=True)
    student = models.ForeignKey(
        Student,
        verbose_name="Student",
        on_delete=models.CASCADE,
        related_name='scholarship_applications'
    )
    scholarship_program = models.ForeignKey(
        ScholarshipProgram,
        verbose_name="Scholarship Program",
        on_delete=models.CASCADE,
        related_name='applications'
    )
    academic_session = models.ForeignKey(
        AcademicSession,
        verbose_name="Academic Session",
        on_delete=models.CASCADE, 
        related_name='scholarship_application_records'
    )
    
    # -------------------------------------------------------------------------
    # APPLICATION DETAILS
    # -------------------------------------------------------------------------
    
    application_date = models.DateField("Application Date", auto_now_add=True)
    requested_amount = models.DecimalField(
        "Requested Amount",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )
    
    # -------------------------------------------------------------------------
    # SUPPORTING INFORMATION
    # -------------------------------------------------------------------------
    
    essay = models.TextField("Personal Essay", blank=True)
    family_income = models.DecimalField(
        "Family Monthly Income",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )
    number_of_dependents = models.PositiveIntegerField("Number of Dependents", null=True, blank=True)
    special_circumstances = models.TextField("Special Circumstances", blank=True)
    
    # -------------------------------------------------------------------------
    # ACADEMIC INFORMATION
    # -------------------------------------------------------------------------
    
    current_gpa = models.DecimalField(
        "Current GPA",
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True
    )
    attendance_percentage = models.DecimalField(
        "Attendance Percentage",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True
    )
    
    # -------------------------------------------------------------------------
    # DOCUMENTS
    # -------------------------------------------------------------------------
    
    supporting_documents = models.JSONField(
        "Supporting Documents",
        default=list,
        blank=True,
        help_text="List of uploaded document references"
    )
    
    # -------------------------------------------------------------------------
    # STATUS AND REVIEW
    # -------------------------------------------------------------------------
    
    status = models.CharField(
        "Application Status",
        max_length=15,
        choices=APPLICATION_STATUS_CHOICES,
        default='SUBMITTED',
        db_index=True
    )
    
    reviewed_by_id = models.CharField(
        "Reviewed By ID",
        max_length=50,
        null=True,
        blank=True,
        help_text="User ID who reviewed this application"
    )
    review_date = models.DateTimeField("Review Date", null=True, blank=True)
    review_notes = models.TextField("Review Notes", blank=True)
    
    # -------------------------------------------------------------------------
    # DECISION
    # -------------------------------------------------------------------------
    
    approved_amount = models.DecimalField(
        "Approved Amount",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )
    decision_reason = models.TextField("Decision Reason", blank=True)
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Scholarship Application"
        verbose_name_plural = "Scholarship Applications"
        ordering = ['-application_date']
        indexes = [
            models.Index(fields=['application_number']),
            models.Index(fields=['student', 'status']),
            models.Index(fields=['scholarship_program']),
            models.Index(fields=['status']),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.application_number} - {self.student.get_full_name()} - {self.scholarship_program.name}"


class StudentScholarship(BaseModel):
    """Active scholarships awarded to students"""
    
    SCHOLARSHIP_STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('SUSPENDED', 'Suspended'),
        ('TERMINATED', 'Terminated'),
        ('COMPLETED', 'Completed'),
        ('PENDING', 'Pending Activation'),
    ]
    
    DISTRIBUTION_METHOD_CHOICES = [
        ('UNTIL_EXHAUSTED', 'Apply Until Exhausted'),
        ('EQUAL_PER_SESSION', 'Equal Amount Per Academic Session'),
        ('EQUAL_PER_INVOICE', 'Equal Amount Per Invoice'),
        ('PROPORTIONAL', 'Proportional to Invoice Amount'),
        ('MANUAL', 'Manual Allocation Per Session'),
    ]
    
    # -------------------------------------------------------------------------
    # CORE RELATIONSHIPS
    # -------------------------------------------------------------------------
    
    student = models.ForeignKey(
        Student,
        verbose_name="Student",
        on_delete=models.CASCADE,
        related_name='scholarships',
        help_text="Student receiving this scholarship"
    )
    
    scholarship_program = models.ForeignKey(
        ScholarshipProgram,
        verbose_name="Scholarship Program",
        on_delete=models.CASCADE,
        related_name='student_scholarships',
        help_text="Program under which this scholarship is awarded"
    )
    
    application = models.OneToOneField(
        StudentScholarshipApplication,
        verbose_name="Related Application",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='awarded_scholarship',
        help_text="Original application that led to this award"
    )
    
    # -------------------------------------------------------------------------
    # AWARD AMOUNTS
    # -------------------------------------------------------------------------
    
    amount_awarded = models.DecimalField(
        "Total Amount Awarded",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Total scholarship amount available across all sessions"
    )
    
    total_amount_used = models.DecimalField(
        "Total Amount Used to Date",
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Cumulative amount applied to invoices"
    )
    
    # -------------------------------------------------------------------------
    # DATE RANGE
    # -------------------------------------------------------------------------
    
    start_date = models.DateField(
        "Start Date",
        help_text="Scholarship becomes active from this date"
    )
    
    end_date = models.DateField(
        "End Date",
        null=True,
        blank=True,
        help_text="Scholarship ends on this date (leave blank for no end date)"
    )
    
    # -------------------------------------------------------------------------
    # DISTRIBUTION SETTINGS
    # -------------------------------------------------------------------------
    
    distribution_method = models.CharField(
        "Distribution Method",
        max_length=20,
        choices=DISTRIBUTION_METHOD_CHOICES,
        default='EQUAL_PER_SESSION',
        help_text="How to distribute the scholarship across multiple sessions/invoices"
    )
    
    amount_per_session = models.DecimalField(
        "Amount Per Session",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="For EQUAL_PER_SESSION: fixed amount to apply per academic session"
    )
    
    amount_per_invoice = models.DecimalField(
        "Amount Per Invoice",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="For EQUAL_PER_INVOICE: fixed amount to apply per invoice"
    )
    
    max_amount_per_session = models.DecimalField(
        "Maximum Amount Per Session",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Cap on total amount that can be applied to a single session"
    )
    
    # -------------------------------------------------------------------------
    # STATUS
    # -------------------------------------------------------------------------
    
    status = models.CharField(
        "Scholarship Status",
        max_length=15,
        choices=SCHOLARSHIP_STATUS_CHOICES,
        default='ACTIVE',
        db_index=True
    )
    
    # -------------------------------------------------------------------------
    # RENEWAL SETTINGS
    # -------------------------------------------------------------------------
    
    is_renewable = models.BooleanField(
        "Is Renewable",
        default=True,
        help_text="Can this scholarship be renewed for multiple years/sessions?"
    )
    
    requires_renewal_verification = models.BooleanField(
        "Requires Renewal Verification",
        default=True,
        help_text="Check eligibility criteria before each disbursement?"
    )
    
    renewal_criteria = models.JSONField(
        "Renewal Criteria",
        default=dict,
        blank=True,
        help_text="Criteria student must meet for renewal"
    )
    
    next_renewal_check_date = models.DateField(
        "Next Renewal Check Date",
        null=True,
        blank=True,
        help_text="Date when next renewal verification is due"
    )
    
    times_renewed = models.PositiveIntegerField(
        "Times Renewed",
        default=0,
        help_text="Number of times this scholarship has been renewed"
    )
    
    last_renewal_date = models.DateField(
        "Last Renewal Date",
        null=True,
        blank=True,
        help_text="Date of most recent renewal"
    )
    
    # -------------------------------------------------------------------------
    # PERFORMANCE TRACKING
    # -------------------------------------------------------------------------
    
    current_gpa = models.DecimalField(
        "Current GPA",
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[
            MinValueValidator(Decimal('0.00')),
            MaxValueValidator(Decimal('4.00'))
        ],
        help_text="Student's current GPA (for renewal verification)"
    )
    
    current_attendance = models.DecimalField(
        "Current Attendance %",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[
            MinValueValidator(Decimal('0.00')),
            MaxValueValidator(Decimal('100.00'))
        ],
        help_text="Student's current attendance percentage"
    )
    
    performance_notes = models.TextField(
        "Performance Notes",
        blank=True,
        help_text="Notes on student's academic performance"
    )
    
    # -------------------------------------------------------------------------
    # ADMINISTRATIVE FIELDS
    # -------------------------------------------------------------------------
    
    awarded_by_id = models.CharField(
        "Awarded By ID",
        max_length=50,
        null=True,
        blank=True,
        help_text="User ID who approved this scholarship"
    )
    
    awarded_date = models.DateField(
        "Date Awarded",
        default=timezone.now,
        help_text="Date when scholarship was officially awarded"
    )
    
    notes = models.TextField(
        "Administrative Notes",
        blank=True,
        help_text="Internal notes about this scholarship"
    )
    
    suspension_reason = models.TextField(
        "Suspension Reason",
        blank=True,
        help_text="Reason for suspension (if status is SUSPENDED)"
    )
    
    termination_reason = models.TextField(
        "Termination Reason",
        blank=True,
        help_text="Reason for termination (if status is TERMINATED)"
    )
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Student Scholarship"
        verbose_name_plural = "Student Scholarships"
        ordering = ['-awarded_date']
        indexes = [
            models.Index(fields=['student', 'status']),
            models.Index(fields=['scholarship_program']),
            models.Index(fields=['status']),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.student.get_full_name()} - {self.scholarship_program.name}"


class ScholarshipApplicationLog(BaseModel):
    """Log of scholarship applications to invoices"""
    
    # -------------------------------------------------------------------------
    # CORE RELATIONSHIPS
    # -------------------------------------------------------------------------
    
    scholarship = models.ForeignKey(
        StudentScholarship,
        verbose_name="Scholarship",
        on_delete=models.CASCADE,
        related_name='application_logs',
        help_text="Scholarship that was applied"
    )
    
    invoice = models.ForeignKey(
        FeeInvoice,
        verbose_name="Invoice",
        on_delete=models.CASCADE,
        related_name='scholarship_application_logs',
        help_text="Invoice to which scholarship was applied"
    )
    
    student = models.ForeignKey(
        Student,
        verbose_name="Student",
        on_delete=models.CASCADE,
        related_name='scholarship_application_logs',
        help_text="Student who received the scholarship"
    )
    
    academic_session = models.ForeignKey(
        AcademicSession,
        verbose_name="Academic Session",
        on_delete=models.CASCADE,
        related_name='scholarship_application_logs',
        null=True,
        blank=True,
        help_text="Academic session for this application"
    )
    
    # -------------------------------------------------------------------------
    # AMOUNTS
    # -------------------------------------------------------------------------
    
    amount_applied = models.DecimalField(
        "Amount Applied",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Amount of scholarship applied to this invoice"
    )
    
    remaining_balance_after = models.DecimalField(
        "Remaining Balance After Application",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Scholarship balance remaining after this application"
    )
    
    # -------------------------------------------------------------------------
    # TRACKING
    # -------------------------------------------------------------------------
    
    application_date = models.DateField(
        "Application Date",
        help_text="Date when scholarship was applied to invoice"
    )
    
    distribution_method_used = models.CharField(
        "Distribution Method Used",
        max_length=20,
        blank=True,
        help_text="Which distribution method was used for this application"
    )
    
    applied_by_id = models.CharField(
        "Applied By ID",
        max_length=50,
        null=True,
        blank=True,
        help_text="User ID who applied the scholarship (if manual)"
    )
    
    notes = models.TextField(
        "Notes",
        blank=True,
        help_text="Additional notes about this application"
    )
    
    # -------------------------------------------------------------------------
    # REVERSAL TRACKING
    # -------------------------------------------------------------------------
    
    is_reversed = models.BooleanField(
        "Is Reversed",
        default=False,
        help_text="Has this application been reversed/undone?"
    )
    
    reversed_date = models.DateField(
        "Reversed Date",
        null=True,
        blank=True,
        help_text="Date when this application was reversed"
    )
    
    reversed_by_id = models.CharField(
        "Reversed By ID",
        max_length=50,
        null=True,
        blank=True,
        help_text="User ID who reversed this application"
    )
    
    reversal_reason = models.TextField(
        "Reversal Reason",
        blank=True,
        help_text="Reason for reversing this application"
    )
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Scholarship Application Log"
        verbose_name_plural = "Scholarship Application Logs"
        ordering = ['-application_date', '-created_at']
        indexes = [
            models.Index(fields=['scholarship', 'invoice']),
            models.Index(fields=['student', 'application_date']),
            models.Index(fields=['is_reversed']),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.scholarship} applied to {self.invoice.invoice_number}"


# =============================================================================
# DISCOUNT MODELS
# =============================================================================

class FeesDiscount(BaseModel):
    """Discount system with scholarship integration"""
    
    DISCOUNT_TYPES = (
        ('PERCENTAGE', 'Percentage'),
        ('FIXED', 'Fixed Amount'),
        ('WAIVER', 'Complete Waiver'),
    )
    
    ELIGIBILITY_CRITERIA = [
        ('MERIT', 'Merit Based'),
        ('NEED', 'Need Based'),
        ('STAFF_CHILD', 'Staff Child'),
        ('SIBLING', 'Sibling Discount'),
        ('EARLY_PAYMENT', 'Early Payment'),
        ('BULK_PAYMENT', 'Bulk Payment'),
        ('SCHOLARSHIP', 'Scholarship'),
        ('SPECIAL_CASE', 'Special Case'),
        ('ACADEMIC_EXCELLENCE', 'Academic Excellence'),
        ('SPORTS_ACHIEVEMENT', 'Sports Achievement'),
        ('FINANCIAL_HARDSHIP', 'Financial Hardship'),
        ('LOYALTY_DISCOUNT', 'Loyalty Discount'),
    ]
    
    # -------------------------------------------------------------------------
    # BASIC INFORMATION
    # -------------------------------------------------------------------------
    
    name = models.CharField("Discount Name", max_length=50)
    code = models.CharField("Discount Code", max_length=20, unique=True, db_index=True)
    discount_type = models.CharField("Discount Type", max_length=10, choices=DISCOUNT_TYPES)
    discount_value = models.DecimalField(
        "Discount Value",
        max_digits=10, 
        decimal_places=2, 
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    description = models.TextField("Description", blank=True)
    
    # -------------------------------------------------------------------------
    # ELIGIBILITY AND CRITERIA
    # -------------------------------------------------------------------------
    
    eligibility_criteria = models.CharField(
        "Eligibility Criteria",
        max_length=25,
        choices=ELIGIBILITY_CRITERIA,
        default='SPECIAL_CASE'
    )
    
    eligibility_rules = models.JSONField(
        "Eligibility Rules",
        default=dict,
        blank=True,
        help_text="JSON rules for complex eligibility checking"
    )
    
    # -------------------------------------------------------------------------
    # APPLICABLE CATEGORIES AND STRUCTURES
    # -------------------------------------------------------------------------
    
    applicable_categories = models.ManyToManyField(
        FeesCategory, 
        verbose_name="Applicable Fee Categories",
        blank=True,
        related_name='applicable_discounts'
    )
    applicable_structures = models.ManyToManyField(
        FeesStructure,
        verbose_name="Applicable Fee Structures",
        blank=True,
        related_name='applicable_discounts'
    )
    
    # -------------------------------------------------------------------------
    # SESSION AND DATE VALIDITY
    # -------------------------------------------------------------------------
    
    academic_session = models.ForeignKey(
        AcademicSession,
        verbose_name="Academic Session",
        on_delete=models.CASCADE,
        related_name='fee_discounts'
    )
    start_date = models.DateField("Start Date")
    end_date = models.DateField("End Date")
    
    # -------------------------------------------------------------------------
    # USAGE LIMITS
    # -------------------------------------------------------------------------
    
    max_usage_count = models.PositiveIntegerField(
        "Maximum Usage Count",
        null=True,
        blank=True,
        help_text="Leave empty for unlimited usage"
    )
    current_usage_count = models.PositiveIntegerField("Current Usage Count", default=0)
    
    # -------------------------------------------------------------------------
    # BUDGET LIMITS
    # -------------------------------------------------------------------------
    
    budget_limit = models.DecimalField(
        "Budget Limit",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum total amount that can be discounted"
    )
    
    current_budget_used = models.DecimalField(
        "Current Budget Used",
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )
    
    # -------------------------------------------------------------------------
    # AUTO-APPLICATION RULES
    # -------------------------------------------------------------------------
    
    auto_apply = models.BooleanField("Auto Apply", default=False)
    requires_approval = models.BooleanField("Requires Approval", default=True)
    
    # -------------------------------------------------------------------------
    # PRIORITY FOR MULTIPLE DISCOUNTS
    # -------------------------------------------------------------------------
    
    priority = models.PositiveIntegerField(
        "Priority",
        default=100,
        help_text="Lower number = higher priority when multiple discounts apply"
    )
    
    # -------------------------------------------------------------------------
    # COMBINATION RULES
    # -------------------------------------------------------------------------
    
    can_combine_with_other_discounts = models.BooleanField(
        "Can Combine with Other Discounts",
        default=False
    )
    
    mutually_exclusive_discounts = models.ManyToManyField(
        'self',
        verbose_name="Mutually Exclusive Discounts",
        blank=True,
        symmetrical=True,
        help_text="Discounts that cannot be applied together with this one"
    )
    
    # -------------------------------------------------------------------------
    # STATUS
    # -------------------------------------------------------------------------
    
    is_active = models.BooleanField("Active", default=True, db_index=True)
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Fee Discount"
        verbose_name_plural = "Fee Discounts"
        ordering = ['priority', 'name']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['is_active']),
            models.Index(fields=['priority']),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.name} ({self.code})"


class DiscountApplication(BaseModel):
    """Track applications of discounts to invoices"""
    
    # -------------------------------------------------------------------------
    # CORE RELATIONSHIPS
    # -------------------------------------------------------------------------
    
    discount = models.ForeignKey(
        FeesDiscount,
        verbose_name="Discount",
        on_delete=models.CASCADE,
        related_name='applications'
    )
    invoice = models.ForeignKey(
        FeeInvoice,
        verbose_name="Invoice",
        on_delete=models.CASCADE,
        related_name='discount_applications'
    )
    student = models.ForeignKey(
        Student,
        verbose_name="Student",
        on_delete=models.CASCADE,
        related_name='discount_applications'
    )
    
    # -------------------------------------------------------------------------
    # APPLICATION DETAILS
    # -------------------------------------------------------------------------
    
    discount_amount = models.DecimalField(
        "Discount Amount",
        max_digits=12,
        decimal_places=2
    )
    applied_by_id = models.CharField(
        "Applied By ID",
        max_length=50,
        null=True,
        blank=True,
        help_text="User ID who applied this discount"
    )
    application_date = models.DateTimeField("Application Date", auto_now_add=True)
    
    # -------------------------------------------------------------------------
    # ADDITIONAL CONTEXT
    # -------------------------------------------------------------------------
    
    notes = models.TextField("Application Notes", blank=True)
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Discount Application"
        verbose_name_plural = "Discount Applications"
        ordering = ['-application_date']
        indexes = [
            models.Index(fields=['discount', 'invoice']),
            models.Index(fields=['student', 'application_date']),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.discount.name} applied to {self.invoice.invoice_number}"


# =============================================================================
# REFUND MODELS
# =============================================================================

class Refund(BaseModel):
    """Refund model with comprehensive tracking"""
    
    STATUS_CHOICES = (
        ('REQUESTED', 'Requested'),
        ('UNDER_REVIEW', 'Under Review'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    )
    
    REFUND_TYPES = [
        ('OVERPAYMENT', 'Overpayment Refund'),
        ('WITHDRAWAL', 'Withdrawal Refund'),
        ('ERROR_CORRECTION', 'Error Correction'),
        ('POLICY_REFUND', 'Policy Refund'),
        ('GOODWILL', 'Goodwill Refund'),
    ]
    
    # -------------------------------------------------------------------------
    # IDENTIFICATION
    # -------------------------------------------------------------------------
    
    refund_number = models.CharField("Refund Number", max_length=50, unique=True, db_index=True)
    student = models.ForeignKey(
        Student, 
        verbose_name="Student",
        on_delete=models.CASCADE, 
        related_name='refunds'
    )
    
    # -------------------------------------------------------------------------
    # REFUND DETAILS
    # -------------------------------------------------------------------------
    
    refund_type = models.CharField(
        "Refund Type",
        max_length=20,
        choices=REFUND_TYPES,
        default='OVERPAYMENT'
    )
    amount = models.DecimalField(
        "Amount",
        max_digits=12, 
        decimal_places=2, 
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    reason = models.TextField("Reason")
    
    # -------------------------------------------------------------------------
    # RELATED RECORDS
    # -------------------------------------------------------------------------
    
    invoice = models.ForeignKey(
        FeeInvoice, 
        verbose_name="Related Invoice",
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='refunds'
    )
    payment = models.ForeignKey(
        Payment,
        verbose_name="Related Payment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='refunds'
    )
    academic_session = models.ForeignKey(
        AcademicSession,
        verbose_name="Academic Session",
        on_delete=models.SET_NULL,
        null=True,
        related_name='refunds'
    )
    
    fiscal_period = models.ForeignKey(
        FiscalPeriod,
        verbose_name="Fiscal Period",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='refunds',
        help_text="Fiscal period when refund was processed"
    )
    
    # -------------------------------------------------------------------------
    # STATUS AND APPROVAL WORKFLOW
    # -------------------------------------------------------------------------
    
    status = models.CharField("Status", max_length=15, choices=STATUS_CHOICES, default='REQUESTED', db_index=True)
    
    requested_by_id = models.CharField(
        "Requested By ID",
        max_length=50,
        null=True,
        blank=True,
        help_text="User ID who requested this refund"
    )
    requested_date = models.DateField("Requested Date", auto_now_add=True)
    
    reviewed_by_id = models.CharField(
        "Reviewed By ID",
        max_length=50,
        null=True,
        blank=True,
        help_text="User ID who reviewed this refund"
    )
    review_date = models.DateTimeField("Review Date", null=True, blank=True)
    review_notes = models.TextField("Review Notes", blank=True)
    
    approved_by_id = models.CharField(
        "Approved By ID",
        max_length=50,
        null=True,
        blank=True,
        help_text="User ID who approved this refund"
    )
    approval_date = models.DateTimeField("Approval Date", null=True, blank=True)
    approved_amount = models.DecimalField(
        "Approved Amount",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )
    
    # -------------------------------------------------------------------------
    # PAYMENT DETAILS
    # -------------------------------------------------------------------------
    
    payment_method = models.ForeignKey(
        PaymentMethod,
        verbose_name="Payment Method",
        on_delete=models.PROTECT,
        related_name='student_refunds'
    )
    payment_date = models.DateField("Payment Date", null=True, blank=True)
    transaction_id = models.CharField("Transaction ID", max_length=100, blank=True)
    bank_details = models.JSONField("Bank Details", default=dict, blank=True)

    # -------------------------------------------------------------------------
    # ACCOUNTING INTEGRATION
    # -------------------------------------------------------------------------
    
    refund_account = models.ForeignKey(
        'finance.Account',
        verbose_name="Refund Account",
        on_delete=models.PROTECT,
        related_name='fee_refunds',
        help_text="Cash/Bank account from which refund is paid"
    )
    
    receivable_account = models.ForeignKey(
        'finance.Account',
        verbose_name="Receivable Account",
        on_delete=models.PROTECT,
        related_name='refunded_receivables',
        null=True,
        blank=True,
        help_text="Accounts Receivable account to debit (if refunding an overpayment)"
    )
    
    revenue_reversal_account = models.ForeignKey(
        'finance.Account',
        verbose_name="Revenue Reversal Account",
        on_delete=models.PROTECT,
        related_name='reversed_revenue',
        null=True,
        blank=True,
        help_text="Revenue account to debit (if reversing revenue)"
    )
    
    # -------------------------------------------------------------------------
    # ADDITIONAL INFORMATION
    # -------------------------------------------------------------------------
    
    supporting_documents = models.TextField("Supporting Documents", blank=True)
    internal_notes = models.TextField("Internal Notes", blank=True)
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Refund"
        verbose_name_plural = "Refunds"
        ordering = ['-requested_date']
        indexes = [
            models.Index(fields=['refund_number']),
            models.Index(fields=['student', 'status']),
            models.Index(fields=['status']),
            models.Index(fields=['fiscal_period']),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.refund_number} - {self.student.get_full_name()}"