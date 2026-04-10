# fees/models.py

"""
Student Fee Management Models

Structure:
  Student Accounts        (StudentAccount, AccountTransaction)
  Display Groups          (DisplayGroup)
  Fee Categories          (FeesCategory)
  Fee Structures          (FeesStructure, FeesStructureBillingSplit, FeesStructureItem)
  Invoices & Payments     (FeeInvoice, FeeInvoiceItem, Payment, BadDebtWriteOff)
  Scholarship Programs    (ScholarshipProgram, StudentScholarshipApplication,
                           StudentScholarship, ScholarshipApplicationLog)
  Discounts               (DiscountPolicy, DiscountTier, StudentDiscount,
                           DiscountApplication, DiscountEngine)

Refunds: no separate Refund model — handled via Payment.refunded / refund_method etc.
Discount tracking: DiscountApplication replaces the old FeeInvoiceItem.applied_discount FK.
Reporting stats: see fees/stats.py — do not duplicate aggregate queries here.
Calculation helpers: see fees/utils.py — do not duplicate line-item math here.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.db.models import F, Q, Sum
from django.utils import timezone
from decimal import Decimal, InvalidOperation
import logging

from utils.models import BaseModel
from core.models import PaymentMethod, TaxRate, FiscalYear, FiscalPeriod
from core.utils import get_school_today
from academics.models import AcademicLevel, Class, AcademicSession
from students.models import Student, SiblingRelationship

logger = logging.getLogger(__name__)


# =============================================================================
# STUDENT ACCOUNTS
# =============================================================================

class StudentAccount(BaseModel):
    """
    Student financial account — subsidiary ledger for individual tracking.

    Balance sign convention (stored on AccountTransaction.amount):
      INVOICE / DEBIT    → Negative  (student owes more)
      PAYMENT / DISCOUNT → Positive  (reduces what student owes)
      REFUND             → Negative  (student owes more after refund)

    Balance interpretation:
      Negative = Student owes money
      Positive = Student has credit (overpayment)
      Zero     = Account is settled

    Use the property shortcuts for templates:
      outstanding_amount  — replaces has_outstanding_balance()  (outstanding_amount > 0)
      credit_balance      — replaces has_credit_balance()        (credit_balance > 0)
      outstanding_amount  — replaces is_account_settled()        (outstanding_amount == 0)

    NOTE: Aggregate reporting (totals by session, top debtors, etc.)
    lives in fees/stats.py — do not duplicate here.
    """

    ACCOUNT_STATUS_CHOICES = [
        ('ACTIVE',    'Active'),
        ('SUSPENDED', 'Suspended'),
        ('FROZEN',    'Frozen'),
        ('CLOSED',    'Closed'),
    ]

    student = models.OneToOneField(
        Student,
        verbose_name="Student",
        on_delete=models.CASCADE,
        related_name='financial_account',
    )
    credit_limit = models.DecimalField(
        "Credit Limit",
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Maximum negative balance allowed",
    )
    status = models.CharField(
        "Account Status",
        max_length=10,
        choices=ACCOUNT_STATUS_CHOICES,
        default='ACTIVE',
        db_index=True,
    )
    last_transaction_date = models.DateTimeField(
        "Last Transaction Date", null=True, blank=True,
    )
    last_payment_date = models.DateTimeField(
        "Last Payment Date", null=True, blank=True,
    )

    # -------------------------------------------------------------------------
    # BALANCE CALCULATION
    # -------------------------------------------------------------------------

    def get_current_balance(self):
        """Sum all signed transaction amounts. Negative = owes money."""
        total = self.transactions.aggregate(total=Sum('amount'))['total']
        return total or Decimal('0.00')

    def get_total_charges(self):
        charges = (
            self.transactions
            .filter(transaction_type__in=['INVOICE', 'DEBIT'])
            .aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        )
        return abs(charges)

    def get_total_payments(self):
        return (
            self.transactions
            .filter(transaction_type='PAYMENT')
            .aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        )

    def get_total_discounts(self):
        return (
            self.transactions
            .filter(transaction_type='DISCOUNT')
            .aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        )

    def get_total_refunds(self):
        refunds = (
            self.transactions
            .filter(transaction_type='REFUND')
            .aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        )
        return abs(refunds)

    # -------------------------------------------------------------------------
    # DERIVED STATES
    # FIX: removed has_outstanding_balance(), has_credit_balance(),
    #      is_account_settled() — use property shortcuts below instead.
    # -------------------------------------------------------------------------

    def get_outstanding_amount(self):
        """Amount owed — always returns positive or zero."""
        balance = self.get_current_balance()
        return abs(balance) if balance < 0 else Decimal('0.00')

    def get_credit_amount(self):
        """Credit available — always returns positive or zero."""
        balance = self.get_current_balance()
        return balance if balance > 0 else Decimal('0.00')

    def is_over_credit_limit(self):
        if self.credit_limit <= 0:
            return False
        return self.get_outstanding_amount() > self.credit_limit

    def can_charge_amount(self, amount):
        """Return (bool, reason). True if charge can proceed."""
        if self.status == 'FROZEN':
            return False, "Account is frozen"
        if self.status == 'CLOSED':
            return False, "Account is closed"
        if self.status == 'SUSPENDED':
            return False, "Account is suspended"
        if self.credit_limit > 0:
            new_outstanding = self.get_outstanding_amount() + Decimal(str(amount))
            if new_outstanding > self.credit_limit:
                excess = new_outstanding - self.credit_limit
                return False, f"Would exceed credit limit by {excess:,.2f}"
        return True, "OK"

    # -------------------------------------------------------------------------
    # PROPERTY SHORTCUTS  (for templates)
    # -------------------------------------------------------------------------

    @property
    def current_balance(self):
        return self.get_current_balance()

    @property
    def outstanding_amount(self):
        """Use outstanding_amount > 0 instead of has_outstanding_balance()."""
        return self.get_outstanding_amount()

    @property
    def credit_balance(self):
        """Use credit_balance > 0 instead of has_credit_balance()."""
        return self.get_credit_amount()

    class Meta:
        verbose_name = "Student Account"
        verbose_name_plural = "Student Accounts"
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['student']),
            models.Index(fields=['last_transaction_date']),
            models.Index(fields=['last_payment_date']),
        ]

    def __str__(self):
        balance = self.get_current_balance()
        if balance < 0:
            return f"{self.student.get_full_name()} — Owes: {abs(balance):,.2f}"
        if balance > 0:
            return f"{self.student.get_full_name()} — Credit: {balance:,.2f}"
        return f"{self.student.get_full_name()} — Settled"


class AccountTransaction(BaseModel):
    """Individual ledger entries on student accounts."""

    TRANSACTION_TYPES = [
        ('CREDIT',     'Credit'),
        ('DEBIT',      'Debit'),
        ('PAYMENT',    'Payment'),
        ('INVOICE',    'Invoice'),
        ('DISCOUNT',   'Discount'),
        ('REFUND',     'Refund'),
        ('ADJUSTMENT', 'Adjustment'),
        ('TRANSFER',   'Transfer'),
    ]

    student_account  = models.ForeignKey(
        StudentAccount,
        verbose_name="Student Account",
        on_delete=models.CASCADE,
        related_name='transactions',
    )
    transaction_type = models.CharField(
        "Transaction Type", max_length=15, choices=TRANSACTION_TYPES, db_index=True,
    )
    amount        = models.DecimalField("Amount",      max_digits=12, decimal_places=2)
    description   = models.TextField("Description")
    balance_after = models.DecimalField("Balance After", max_digits=12, decimal_places=2)

    invoice = models.ForeignKey(
        'FeeInvoice',
        verbose_name="Related Invoice",
        on_delete=models.SET_NULL,
        null=True, blank=True,
    )
    payment = models.ForeignKey(
        'Payment',
        verbose_name="Related Payment",
        on_delete=models.SET_NULL,
        null=True, blank=True,
    )

    academic_session = models.ForeignKey(
        AcademicSession,
        verbose_name="Academic Session",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='account_transactions',
    )
    fiscal_period = models.ForeignKey(
        FiscalPeriod,
        verbose_name="Fiscal Period",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='account_transactions',
    )

    reference_number = models.CharField("Reference Number", max_length=50, blank=True)
    processed_by_id  = models.CharField("Processed By ID",  max_length=50, null=True, blank=True)

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

    def __str__(self):
        return f"{self.get_transaction_type_display()} — {self.amount}"


# =============================================================================
# DISPLAY GROUPS
# =============================================================================

class DisplayGroup(BaseModel):
    """Groups fee categories for display on invoices and receipts."""

    name          = models.CharField("Display Group Name", max_length=100, unique=True)
    description   = models.TextField("Description", blank=True)
    display_order = models.PositiveIntegerField("Display Order", default=1)
    color_code    = models.CharField("Color Code", max_length=7, default="#6f42c1")

    show_as_group = models.BooleanField(
        "Show as Group", default=True,
        help_text="Items shown together under a header; if False, shown individually",
    )
    show_group_subtotal = models.BooleanField(
        "Show Group Subtotal", default=True,
        help_text="Only relevant when show_as_group is True",
    )
    is_active = models.BooleanField("Is Active", default=True, db_index=True)

    class Meta:
        verbose_name = "Display Group"
        verbose_name_plural = "Display Groups"
        ordering = ['display_order', 'name']

    def __str__(self):
        return self.name


# =============================================================================
# FEE CATEGORIES
# =============================================================================

class FeesCategory(BaseModel):
    """
    Fee categories with billing, tax, display, and GL routing configuration.

    CATEGORY TYPE → GL ROUTING
    --------------------------
    DEPOSIT                 → SpecialAccountMappings.default_student_deposit_account
                              (LIABILITY — never a revenue account)
    BOARDING / MEALS /
    LAUNDRY                 → CoreAccountMappings.boarding_revenue_account
    UNIFORM                 → CoreAccountMappings.uniform_and_book_sales_account
    LATE_PAYMENT            → RevenueAccountMappings.late_fee_revenue_account
    PENALTY                 → RevenueAccountMappings.penalty_revenue_account
    TRANSPORT               → RevenueAccountMappings.transport_revenue_account
    Everything else         → CoreAccountMappings.default_revenue_account

    Use is_liability_type() before routing to any account — DEPOSIT categories
    must credit a liability, never income. Bypassing this check will incorrectly
    recognise a held deposit as earned revenue.

    FREQUENCY SEMANTICS
    -------------------
    ONE_TIME     — charged exactly once per student's entire enrollment
                   (registration, caution money deposit, admission)
    PER_INCIDENT — charged each time a triggering event occurs; a student can
                   be charged 0–N times per term
                   (replacement fee, retake fee, breakages charge)
    All others   — periodic billing driven by the academic/fiscal calendar

    Both ONE_TIME and PER_INCIDENT automatically set is_recurring = False on
    save(). You do not need to set this manually.

    APPLICABILITY
    -------------
    Drives FeesStructure.is_applicable_to_student() filtering and invoice
    generation logic. Values must match APPLICABILITY_CHOICES — the init
    config previously used strings outside these choices (TRANSPORT_USERS,
    ICT_STUDENTS, SCIENCE_STUDENTS, PARTICIPANTS, DEFAULTERS) which have
    now been added to this list.

    MIGRATION NOTE
    --------------
    Adding new choices to CharField does not require a schema migration in
    Django since choices are not enforced at the database level.
    The two new indexes (frequency, is_recurring) do require a migration.
    """

    # -------------------------------------------------------------------------
    # FREQUENCY CHOICES
    # -------------------------------------------------------------------------

    FREQUENCY_CHOICES = [
        ('TERMLY',       'Per Term'),
        ('YEARLY',       'Yearly'),
        ('MONTHLY',      'Monthly'),
        ('WEEKLY',       'Weekly'),
        ('DAILY',        'Daily'),
        ('ONE_TIME',     'One Time'),
        ('PER_INCIDENT', 'Per Incident'),
    ]

    # -------------------------------------------------------------------------
    # APPLICABILITY CHOICES
    # -------------------------------------------------------------------------

    APPLICABILITY_CHOICES = [
        # Boarding status
        ('ALL',                  'All Students'),
        ('DAY_SCHOLARS',         'Day Scholars Only'),
        ('BOARDERS',             'Boarders Only'),
        ('WEEKLY_BOARDERS',      'Weekly Boarders Only'),
        ('FULL_BOARDERS',        'Full Boarders Only'),
        ('FLEXI_BOARDERS',       'Flexible Boarders Only'),
        # Enrollment stage
        ('NEW_STUDENTS',         'New Students Only'),
        ('CONTINUING_STUDENTS',  'Continuing Students Only'),
        # Funding status
        ('SCHOLARSHIP_STUDENTS', 'Scholarship Students'),
        # Service / program enrollment
        ('TRANSPORT_USERS',      'Transport Users Only'),
        ('SCIENCE_STUDENTS',     'Science Stream Students'),
        ('ICT_STUDENTS',         'ICT / Computer Students'),
        ('PARTICIPANTS',         'Activity Participants Only'),
        # Fee status — for penalty-type categories only
        ('DEFAULTERS',           'Students with Outstanding Balances'),
        # Catch-all
        ('OPTIONAL',             'Optional / Elective'),
    ]

    # -------------------------------------------------------------------------
    # CATEGORY TYPE CHOICES
    # -------------------------------------------------------------------------

    CATEGORY_TYPE_CHOICES = [
        # ── Core academic ──────────────────────────────────────────────────────
        ('TUITION',       'Tuition Fee'),
        ('EXAM',          'Examination Fee'),
        ('LABORATORY',    'Laboratory Fee'),
        ('LIBRARY',       'Library Fee'),
        ('BOOKS',         'Books & Materials'),
        ('TECHNOLOGY',    'Technology Fee'),
        # ── Boarding & residential ─────────────────────────────────────────────
        ('BOARDING',      'Boarding Fee'),
        ('MEALS',         'Meals Fee'),
        ('LAUNDRY',       'Laundry Fee'),
        # ── Student services ───────────────────────────────────────────────────
        ('TRANSPORT',     'Transport Fee'),
        ('MEDICAL',       'Medical Fee'),
        ('INSURANCE',     'Insurance Fee'),
        ('SPORT',         'Sports Fee'),
        ('CLUB',          'Club / Activity Fee'),
        ('FIELD_TRIP',    'Field Trip'),
        # ── Uniform & supplies ─────────────────────────────────────────────────
        ('UNIFORM',       'Uniform Fee'),
        # ── Enrollment & administration ────────────────────────────────────────
        ('REGISTRATION',  'Registration Fee'),
        ('ADMISSION',     'Admission Fee'),
        ('DEVELOPMENT',   'Development Levy'),
        ('GRADUATION',    'Graduation Fee'),
        ('PTA',           'PTA Levy'),
        # ── Financial instruments ──────────────────────────────────────────────
        # DEPOSIT routes to a LIABILITY account — never revenue.
        # is_liability_type() returns True for this type.
        ('DEPOSIT',       'Refundable Deposit'),
        # ── Penalties & charges ────────────────────────────────────────────────
        ('LATE_PAYMENT',  'Late Payment Fee'),
        ('PENALTY',       'Penalty / Fine'),
        # ── Publications & media ───────────────────────────────────────────────
        ('PHOTO',         'Photography Fee'),
        ('PUBLICATION',   'Publication Fee'),      # magazine, yearbook, diary
        # ── Catch-alls ─────────────────────────────────────────────────────────
        ('MISCELLANEOUS', 'Miscellaneous'),
        ('OTHER',         'Other'),
    ]

    # -------------------------------------------------------------------------
    # CLASS-LEVEL TYPE SETS
    # Used by helper methods and importable by other modules without
    # instantiating the model.
    #
    # Example external use:
    #   from fees.models import FeesCategory
    #   if category.category_type in FeesCategory._LIABILITY_TYPES:
    #       account = deposit_account
    # -------------------------------------------------------------------------

    _BOARDING_TYPES  = frozenset({'BOARDING', 'MEALS', 'LAUNDRY'})
    _ACADEMIC_TYPES  = frozenset({'TUITION', 'EXAM', 'BOOKS', 'LIBRARY', 'LABORATORY', 'TECHNOLOGY'})
    _LIABILITY_TYPES = frozenset({'DEPOSIT'})
    _PENALTY_TYPES   = frozenset({'LATE_PAYMENT', 'PENALTY'})
    _UNIFORM_TYPES   = frozenset({'UNIFORM'})
    _OPTIONAL_TYPES  = frozenset({'CLUB', 'FIELD_TRIP', 'PHOTO', 'PUBLICATION', 'SPORT'})

    # -------------------------------------------------------------------------
    # FIELDS
    # -------------------------------------------------------------------------

    name = models.CharField("Fee Name", max_length=100, unique=True)
    code = models.CharField("Fee Code", max_length=20, unique=True, db_index=True)
    description   = models.TextField("Description", blank=True)
    category_type = models.CharField(
        "Category Type",
        max_length=20,
        choices=CATEGORY_TYPE_CHOICES,
        default='OTHER',
        db_index=True,
    )

    is_recurring = models.BooleanField(
        "Recurring",
        default=True,
        help_text=(
            "True for periodic fees (TERMLY, MONTHLY, YEARLY). "
            "Automatically set to False for ONE_TIME and PER_INCIDENT "
            "frequencies — do not set manually."
        ),
    )
    frequency = models.CharField(
        "Frequency",
        max_length=20,
        choices=FREQUENCY_CHOICES,
        default='TERMLY',
    )
    applicability = models.CharField(
        "Applicable To",
        max_length=25,
        choices=APPLICABILITY_CHOICES,
        default='ALL',
    )

    display_group = models.ForeignKey(
        DisplayGroup,
        verbose_name="Display Group",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text=(
            "Display groups are seeded before fee categories during school "
            "initialization. The init config passes group names as strings — "
            "the init command must resolve these to DisplayGroup instances "
            "before saving."
        ),
    )
    display_order = models.PositiveIntegerField("Display Order", default=1)

    is_mandatory           = models.BooleanField("Mandatory",              default=True)
    is_refundable          = models.BooleanField("Refundable",             default=True)
    allows_partial_payment = models.BooleanField("Allows Partial Payment", default=True)

    currency = models.CharField(
        "Billing Currency",
        max_length=3,
        blank=True,
        help_text=(
            "Currency this fee is always billed in. "
            "Leave blank to use the school's primary currency. "
            "Example: set to 'USD' for international tuition categories."
        ),
    )

    is_taxable = models.BooleanField("Taxable", default=False)
    default_tax_rate = models.DecimalField(
        "Default Tax Rate (%)",
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
    )

    is_active = models.BooleanField("Active", default=True, db_index=True)

    # -------------------------------------------------------------------------
    # VALIDATION
    # -------------------------------------------------------------------------

    def clean(self):
        super().clean()
        errors = {}

        # ONE_TIME and PER_INCIDENT fees are by definition non-periodic
        if self.frequency in ('ONE_TIME', 'PER_INCIDENT') and self.is_recurring:
            errors['is_recurring'] = (
                f"A fee with frequency '{self.get_frequency_display()}' "
                "cannot be marked as recurring. Set is_recurring to False, "
                "or change the frequency."
            )

        # DEPOSIT: must always be refundable
        if self.category_type == 'DEPOSIT' and not self.is_refundable:
            errors['is_refundable'] = (
                "Deposit-type fees must be refundable — they are held as a "
                "liability and returned to the student on departure. "
                "If the charge is non-refundable, use category type 'OTHER'."
            )

        # DEPOSIT: must not allow partial payment
        # A deposit is only meaningful when paid in full — a partial deposit
        # cannot be held as a clean liability entry.
        if self.category_type == 'DEPOSIT' and self.allows_partial_payment:
            errors['allows_partial_payment'] = (
                "Deposit-type fees must be paid in full. "
                "A partial deposit cannot be recorded as a clean liability. "
                "Disable partial payment or change the category type."
            )

        # Penalty types are non-refundable by nature
        if self.category_type in self._PENALTY_TYPES and self.is_refundable:
            errors['is_refundable'] = (
                f"'{self.get_category_type_display()}' fees should not be "
                "refundable. Penalties are income earned — if a reversal is "
                "genuinely needed, use a manual journal entry or payment reversal."
            )

        # PTA levies are mandatory and non-refundable by convention
        if self.category_type == 'PTA' and self.is_refundable:
            errors['is_refundable'] = (
                "PTA levies are remitted to the Parents-Teacher Association "
                "and are not refundable by the school."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # Auto-correct is_recurring for non-periodic frequencies so that
        # callers do not need to remember to set this manually.
        if self.frequency in ('ONE_TIME', 'PER_INCIDENT'):
            self.is_recurring = False
        self.full_clean()
        super().save(*args, **kwargs)

    # -------------------------------------------------------------------------
    # CATEGORY CLASSIFICATION HELPERS
    # -------------------------------------------------------------------------

    def is_boarding_related(self):
        """
        True for BOARDING, MEALS, LAUNDRY.
        These route to CoreAccountMappings.boarding_revenue_account.
        Also used by StudentAccount and invoice generators to filter
        boarding-specific fee lines.
        """
        return self.category_type in self._BOARDING_TYPES

    def is_academic_related(self):
        """
        True for TUITION, EXAM, BOOKS, LIBRARY, LABORATORY, TECHNOLOGY.
        These aggregate under academic/tuition revenue in financial reports.
        """
        return self.category_type in self._ACADEMIC_TYPES

    def is_liability_type(self):
        """
        True for DEPOSIT.

        CRITICAL — invoice generators and GL routing code MUST call this
        before routing to any account. DEPOSIT categories credit a liability
        account (SpecialAccountMappings.default_student_deposit_account),
        never a revenue account. Failing to check this will book a held
        deposit as earned income, which is an accounting error.
        """
        return self.category_type in self._LIABILITY_TYPES

    def is_penalty_type(self):
        """
        True for LATE_PAYMENT and PENALTY.
        These are non-refundable and route to dedicated penalty/fine revenue
        accounts in RevenueAccountMappings.
        """
        return self.category_type in self._PENALTY_TYPES

    def is_uniform_related(self):
        """
        True for UNIFORM.
        Routes to CoreAccountMappings.uniform_and_book_sales_account,
        or RevenueAccountMappings.uniform_sales_revenue_account if set.
        See FinancialSettings.get_uniform_revenue_account() for resolution order.
        """
        return self.category_type in self._UNIFORM_TYPES

    def is_optional_charge(self):
        """
        True for CLUB, FIELD_TRIP, PHOTO, PUBLICATION, SPORT.
        These are typically elective. Note: is_mandatory on the instance
        takes precedence — this is a category-level signal used for UI
        filtering, not an absolute billing rule.
        """
        return self.category_type in self._OPTIONAL_TYPES

    def get_suggested_gl_account(self):
        """
        Return a human-readable string describing where this category should
        post in the general ledger.

        This is for admin help text and validation warnings only.
        For actual GL routing use:
          - FinancialSettings.get_revenue_account(invoice_type)
          - CoreAccountMappings.get_revenue_account(fee_category)
        Never derive accounts from this string programmatically.
        """
        if self.is_liability_type():
            return 'SpecialAccountMappings.default_student_deposit_account (LIABILITY)'
        if self.is_boarding_related():
            return 'CoreAccountMappings.boarding_revenue_account'
        if self.is_uniform_related():
            return (
                'RevenueAccountMappings.uniform_sales_revenue_account → '
                'CoreAccountMappings.uniform_and_book_sales_account → '
                'CoreAccountMappings.default_revenue_account'
            )
        if self.category_type == 'LATE_PAYMENT':
            return 'RevenueAccountMappings.late_fee_revenue_account'
        if self.category_type == 'PENALTY':
            return 'RevenueAccountMappings.penalty_revenue_account'
        if self.category_type == 'TRANSPORT':
            return 'RevenueAccountMappings.transport_revenue_account'
        return 'CoreAccountMappings.default_revenue_account'

    # -------------------------------------------------------------------------
    # META
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
            models.Index(fields=['frequency']),           # new
            models.Index(fields=['is_recurring']),        # new
        ]

    def __str__(self):
        return f"{self.name} ({self.get_category_type_display()})"


# =============================================================================
# FEE STRUCTURES
# =============================================================================

class FeesStructure(BaseModel):
    """
    Fee structure covering one or more academic sessions.

    ARCHITECTURE
    ------------
    applicable_sessions — Which sessions this fee applies to   (WHAT)
    billing_periods     — When invoices are generated           (WHEN)

    This separation allows billing a full-year fee in one payment
    (applicable_sessions = [T1, T2, T3], billing_periods = [Jan])
    or splitting one term's fees across two months.
    """

    STRUCTURE_TYPE_CHOICES = [
        ('STANDARD',         'Standard Structure'),
        ('DAY_SCHOLAR',      'Day Scholar Structure'),
        ('BOARDER',          'Boarder Structure'),
        ('WEEKLY_BOARDER',   'Weekly Boarder Structure'),
        ('FULL_BOARDER',     'Full Boarder Structure'),
        ('FLEXI_BOARDER',    'Flexible Boarder Structure'),
        ('SCHOLARSHIP',      'Scholarship Structure'),
        ('CUSTOM',           'Custom Structure'),
        ('STAFF_CHILD',      'Staff Child Structure'),
        ('SIBLING_DISCOUNT', 'Sibling Discount Structure'),
        ('NEED_BASED',       'Need-Based Structure'),
        ('MERIT_BASED',      'Merit-Based Structure'),
    ]

    BILLING_FREQUENCY_CHOICES = [
        ('ONCE',          'Bill Once (Full Amount)'),
        ('PER_PERIOD',    'Bill Per Fiscal Period'),
        ('SPLIT_CUSTOM',  'Custom Split Across Periods'),
        ('ON_ENROLLMENT', 'Bill on Student Enrollment'),
    ]

    BOARDING_FILTER_CHOICES = [
        ('ALL',           'All Students'),
        ('DAY_ONLY',      'Day Scholars Only'),
        ('BOARDER_ONLY',  'Boarders Only'),
        ('FULL_BOARDER',  'Full Boarders Only'),
        ('WEEKLY_BOARDER','Weekly Boarders Only'),
        ('FLEXI_BOARDER', 'Flexible Boarders Only'),
    ]

    STUDENT_TYPE_FILTER_CHOICES = [
        ('ALL',               'All Students'),
        ('NEW_ONLY',          'New Students Only'),
        ('CONTINUING_ONLY',   'Continuing Students Only'),
        ('SCHOLARSHIP_ONLY',  'Scholarship Students Only'),
    ]

    academic_year = models.ForeignKey(
        FiscalYear,
        on_delete=models.PROTECT,
        related_name='fee_structures',
        null=True, blank=True,
    )
    applicable_sessions = models.ManyToManyField(
        AcademicSession,
        verbose_name="Applicable Academic Sessions",
        related_name='fee_structures',
    )
    academic_levels = models.ManyToManyField(
        AcademicLevel,
        verbose_name="Academic Levels",
        related_name='fee_structures',
    )
    applicable_classes = models.ManyToManyField(
        Class,
        verbose_name="Applicable Classes",
        blank=True,
        help_text="Leave empty to apply to all classes in selected academic levels",
    )

    billing_periods = models.ManyToManyField(
        FiscalPeriod,
        verbose_name="Billing Periods",
        through='FeesStructureBillingSplit',
        related_name='fee_structures',
    )
    billing_frequency = models.CharField(
        "Billing Frequency", max_length=20,
        choices=BILLING_FREQUENCY_CHOICES, default='ONCE',
    )

    name          = models.CharField("Structure Name", max_length=100)
    description   = models.TextField("Description", blank=True)
    structure_type = models.CharField(
        "Structure Type", max_length=20, choices=STRUCTURE_TYPE_CHOICES,
        default='STANDARD', db_index=True,
    )

    boarding_type_filter = models.CharField(
        "Boarding Type Filter", max_length=20,
        choices=BOARDING_FILTER_CHOICES, default='ALL',
    )
    student_type_filter = models.CharField(
        "Student Type Filter", max_length=20,
        choices=STUDENT_TYPE_FILTER_CHOICES, default='ALL',
    )

    payment_terms_days = models.PositiveIntegerField(
        "Payment Terms (Days)", default=30,
    )

    charges_late_fee   = models.BooleanField("Charges Late Fee", default=False)
    late_fee_amount    = models.DecimalField(
        "Late Fee Amount", max_digits=10, decimal_places=2, default=Decimal('0.00'),
    )
    late_fee_percentage = models.DecimalField(
        "Late Fee Percentage", max_digits=5, decimal_places=2, default=Decimal('0.00'),
    )
    grace_period_days  = models.PositiveIntegerField("Grace Period (Days)", default=7)

    priority       = models.PositiveIntegerField(
        "Priority", default=100,
        help_text="Lower = higher priority when multiple structures match",
    )
    is_active      = models.BooleanField("Active", default=True, db_index=True)
    effective_date = models.DateField("Effective Date", default=timezone.now, db_index=True)
    expiry_date    = models.DateField("Expiry Date", null=True, blank=True, db_index=True)

    def get_total_amount(self):
        total = self.items.aggregate(total=Sum('amount'))['total']
        return total or Decimal('0.00')

    def get_billing_schedule(self):
        """Return list of {period, amount, percentage} dicts."""
        splits = self.billing_splits.select_related('fiscal_period').order_by(
            'fiscal_period__period_number'
        )
        if not splits.exists():
            first_period = self.billing_periods.order_by('period_number').first()
            if first_period:
                return [{'period': first_period, 'amount': self.get_total_amount(), 'percentage': Decimal('100.00')}]
            return []
        total = self.get_total_amount()
        return [
            {'period': s.fiscal_period, 'amount': (total * s.percentage / 100), 'percentage': s.percentage}
            for s in splits
        ]

    def is_applicable_to_student(self, student, academic_session=None):
        """Return True if this structure should apply to the given student."""
        if academic_session:
            if not self.applicable_sessions.filter(pk=academic_session.pk).exists():
                return False
        else:
            enrollment = student.get_current_enrollment()
            if enrollment:
                session = enrollment.class_instance.academic_session
                if not self.applicable_sessions.filter(pk=session.pk).exists():
                    return False

        if self.boarding_type_filter != 'ALL':
            boarding = student.boarding_enrollments.filter(
                academic_session=academic_session, status='ACTIVE'
            ).first()
            if self.boarding_type_filter == 'DAY_ONLY':
                if boarding:
                    return False
            elif self.boarding_type_filter == 'BOARDER_ONLY':
                if not boarding:
                    return False
            else:
                if not boarding:
                    return False
                filter_map = {
                    'FULL_BOARDER':   'FULL_BOARDER',
                    'WEEKLY_BOARDER': 'WEEKLY_BOARDER',
                    'FLEXI_BOARDER':  'FLEXI_BOARDER',
                }
                if boarding.boarding_type != filter_map.get(self.boarding_type_filter):
                    return False

        if self.student_type_filter != 'ALL':
            enrollment = student.get_current_enrollment(academic_session)
            if not enrollment:
                return False
            if self.student_type_filter == 'NEW_ONLY':
                if enrollment.enrollment_type not in ['NEW', 'TRANSFER_IN', 'READMISSION']:
                    return False
            elif self.student_type_filter == 'CONTINUING_ONLY':
                if enrollment.enrollment_type not in ['CONTINUING', 'PROMOTED']:
                    return False
            elif self.student_type_filter == 'SCHOLARSHIP_ONLY':
                if not student.scholarships.filter(status='ACTIVE').exists():
                    return False

        if self.academic_levels.exists():
            enrollment = student.get_current_enrollment(academic_session)
            if not enrollment:
                return False
            if not self.academic_levels.filter(pk=enrollment.class_instance.academic_level.pk).exists():
                return False

        if self.applicable_classes.exists():
            enrollment = student.get_current_enrollment(academic_session)
            if not enrollment:
                return False
            if not self.applicable_classes.filter(pk=enrollment.class_instance.pk).exists():
                return False

        return True

    def get_next_billing_period(self):
        # FIX: removed redundant local import — get_school_today already imported at module level
        today = get_school_today()
        return self.billing_periods.filter(
            start_date__gte=today, is_closed=False
        ).order_by('start_date').first()

    def should_generate_invoice_now(self):
        current_period = FiscalPeriod.get_current_fiscal_period()
        if not current_period:
            return False
        return self.billing_periods.filter(pk=current_period.pk).exists()

    class Meta:
        verbose_name = "Fee Structure"
        verbose_name_plural = "Fee Structures"
        ordering = ['academic_year', 'structure_type', 'priority', 'name']
        indexes = [
            models.Index(fields=['academic_year', 'is_active']),
            models.Index(fields=['structure_type', 'is_active']),
            models.Index(fields=['boarding_type_filter']),
            models.Index(fields=['student_type_filter']),
            models.Index(fields=['priority']),
            models.Index(fields=['effective_date', 'expiry_date']),
        ]

    def __str__(self):
        return f"{self.name} ({self.academic_year})"


class FeesStructureBillingSplit(BaseModel):
    """Through model — splits a fee structure's billing across fiscal periods."""

    fee_structure = models.ForeignKey(
        FeesStructure, on_delete=models.CASCADE, related_name='billing_splits',
    )
    fiscal_period = models.ForeignKey(
        FiscalPeriod, on_delete=models.CASCADE, related_name='fee_structure_splits',
    )
    percentage = models.DecimalField(
        "Percentage of Total", max_digits=5, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01')), MaxValueValidator(Decimal('100.00'))],
    )
    sequence    = models.PositiveIntegerField("Sequence", default=1)
    description = models.CharField("Description", max_length=200, blank=True)

    def clean(self):
        super().clean()
        if self.fee_structure_id:
            total = (
                FeesStructureBillingSplit.objects
                .filter(fee_structure=self.fee_structure)
                .exclude(pk=self.pk)
                .aggregate(total=models.Sum('percentage'))['total'] or Decimal('0.00')
            )
            if total + self.percentage > Decimal('100.00'):
                raise ValidationError({
                    'percentage': f'Total billing percentages cannot exceed 100%. Current total: {total + self.percentage}%'
                })

    class Meta:
        verbose_name = "Fee Structure Billing Split"
        verbose_name_plural = "Fee Structure Billing Splits"
        ordering = ['fee_structure', 'sequence', 'fiscal_period__period_number']
        unique_together = ('fee_structure', 'fiscal_period')
        constraints = [
            models.CheckConstraint(
                check=models.Q(percentage__gt=0, percentage__lte=100),
                name='valid_percentage_range',
            ),
        ]

    def __str__(self):
        return f"{self.fee_structure.name} — {self.fiscal_period.name} ({self.percentage}%)"


class FeesStructureItem(BaseModel):
    """
    Individual fee line items within a fee structure.

    NOTE: Line-item calculations (tax, discount, gross amounts)
    live in fees/utils.py::calculate_line_item_totals() — use that instead of
    duplicating calculations here.
    """

    # FIX: class-level sentinel for day scholar boarding type key
    DAY_SCHOLAR_KEY = 'DAY_SCHOLAR'

    fee_structure = models.ForeignKey(
        FeesStructure, on_delete=models.CASCADE, related_name='items',
        verbose_name="Fee Structure",
    )
    fee_category = models.ForeignKey(
        FeesCategory, on_delete=models.CASCADE, related_name='structure_items',
        verbose_name="Fee Category",
    )

    amount = models.DecimalField(
        "Amount", max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    use_variable_amount = models.BooleanField("Use Variable Amount", default=False)
    variable_amount_rules = models.JSONField(
        "Variable Amount Rules", default=dict, blank=True,
        help_text='Maps boarding type to amount. e.g. {"FULL_BOARDER": "300000.00"}',
    )

    is_taxable      = models.BooleanField("Is Taxable", default=False)
    tax_percentage  = models.DecimalField(
        "Tax Percentage", max_digits=5, decimal_places=2, default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
    )
    tax_inclusive   = models.BooleanField("Tax Inclusive", default=False)

    default_discount_percentage = models.DecimalField(
        "Default Discount %", max_digits=5, decimal_places=2, default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
    )
    max_discount_percentage = models.DecimalField(
        "Maximum Discount %", max_digits=5, decimal_places=2, default=Decimal('100.00'),
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
    )

    scholarship_eligible     = models.BooleanField("Scholarship Eligible", default=True)
    max_scholarship_discount = models.DecimalField(
        "Max Scholarship Discount %", max_digits=5, decimal_places=2,
        null=True, blank=True,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
    )
    scholarship_priority = models.PositiveIntegerField(
        "Scholarship Priority", default=100,
    )

    currency = models.CharField(
        "Currency Override",
        max_length=3,
        blank=True,
        help_text=(
            "Override the fee category currency for this structure only. "
            "Leave blank to inherit from the fee category, "
            "which itself falls back to the school currency."
        ),
    )

    is_mandatory          = models.BooleanField("Mandatory", default=True)
    is_conditional        = models.BooleanField("Conditional", default=False)
    condition_description = models.TextField("Condition Description", blank=True)
    condition_criteria    = models.JSONField("Condition Criteria", default=dict, blank=True)

    override_billing_periods = models.BooleanField("Override Billing Periods", default=False)
    custom_billing_periods   = models.ManyToManyField(
        FiscalPeriod, blank=True, related_name='custom_fee_items',
    )

    is_payable_in_installments = models.BooleanField("Payable in Installments", default=False)
    number_of_installments     = models.PositiveIntegerField(
        "Number of Installments", default=1,
        validators=[MinValueValidator(1), MaxValueValidator(12)],
    )
    minimum_installment_amount = models.DecimalField(
        "Minimum Installment Amount", max_digits=10, decimal_places=2,
        null=True, blank=True,
    )

    display_order      = models.PositiveIntegerField("Display Order", default=1)
    print_on_invoice   = models.BooleanField("Print on Invoice", default=True)
    custom_description = models.TextField("Custom Description", blank=True)
    internal_notes     = models.TextField("Internal Notes", blank=True)

    def clean(self):
        super().clean()
        errors = {}
        if self.default_discount_percentage > self.max_discount_percentage:
            errors['default_discount_percentage'] = (
                f"Default discount ({self.default_discount_percentage}%) cannot exceed "
                f"maximum ({self.max_discount_percentage}%)"
            )
        if self.is_payable_in_installments and self.number_of_installments < 2:
            errors['number_of_installments'] = "Must be at least 2 if payable in installments"
        if self.use_variable_amount and not self.variable_amount_rules:
            errors['variable_amount_rules'] = "Variable rules required when use_variable_amount is enabled"
        if errors:
            raise ValidationError(errors)

    def get_amount_for_student(self, student, academic_session=None):
        if not self.use_variable_amount:
            return self.amount
        filter_kwargs = {'status': 'ACTIVE'}
        if academic_session:
            filter_kwargs['academic_session'] = academic_session
        boarding = student.boarding_enrollments.filter(**filter_kwargs).first()
        # FIX: use class-level DAY_SCHOLAR_KEY constant instead of hard-coded string
        boarding_type = boarding.boarding_type if boarding else self.DAY_SCHOLAR_KEY
        if boarding_type in self.variable_amount_rules:
            return Decimal(str(self.variable_amount_rules[boarding_type]))
        return self.amount

    # FIX: renamed from is_applicable_to_student() to is_condition_met_for_student()
    # to distinguish it from the identically-named but semantically different
    # FeesStructure.is_applicable_to_student()
    def is_condition_met_for_student(self, student):
        """
        Return True if this item's conditional criteria are met for the given student.

        Distinct from FeesStructure.is_applicable_to_student() which checks
        whether the whole structure applies. This checks per-item conditions.
        """
        if not self.is_conditional or not self.condition_criteria:
            return True
        try:
            for key, value in self.condition_criteria.items():
                if '__' in key:
                    field_name, lookup = key.split('__', 1)
                    if not hasattr(student, field_name):
                        return False
                    student_value = getattr(student, field_name)
                    if lookup == 'in' and student_value not in value:
                        return False
                    elif lookup == 'exact' and student_value != value:
                        return False
                else:
                    if not hasattr(student, key) or getattr(student, key) != value:
                        return False
            return True
        except Exception as e:
            logger.error(f"Error evaluating condition criteria for {self}: {e}")
            return True

    def get_applicable_billing_periods(self):
        if self.override_billing_periods:
            return self.custom_billing_periods.all()
        return self.fee_structure.billing_periods.all()

    def get_effective_currency(self, school_currency='UGX'):
        """
        Resolve the billing currency for this line item.

        Resolution chain (first non-blank wins):
          1. FeesStructureItem.currency  (structure-level override)
          2. FeesCategory.currency       (category-level default)
          3. school_currency             (school's primary currency)
        """
        return (
            self.currency
            or self.fee_category.currency
            or school_currency
        )

    def get_description(self):
        return self.custom_description or self.fee_category.description

    def get_display_name(self):
        return self.fee_category.name

    class Meta:
        verbose_name = "Fee Structure Item"
        verbose_name_plural = "Fee Structure Items"
        ordering = ['fee_structure', 'display_order', 'fee_category__display_order']
        unique_together = ('fee_structure', 'fee_category')
        indexes = [
            models.Index(fields=['fee_structure', 'display_order']),
            models.Index(fields=['is_mandatory']),
            models.Index(fields=['is_conditional']),
            models.Index(fields=['scholarship_eligible']),
            models.Index(fields=['print_on_invoice']),
        ]

    def __str__(self):
        amount_display = "Variable" if self.use_variable_amount else f"{self.amount:,.2f}"
        return f"{self.fee_structure.name} — {self.fee_category.name} ({amount_display})"


# =============================================================================
# INVOICES
# =============================================================================

class FeeInvoice(BaseModel):
    """
    Student fee invoice.

    Lifecycle:
      DRAFT → PENDING → PARTIALLY_PAID → PAID
                      → OVERDUE
      DRAFT / PENDING → VOID (zero-amount / data error)
      DRAFT / PENDING → CANCELLED (administrative cancel)

    Scholarship and discount tracking:
      has_scholarships_applied  — at least one scholarship reduced this invoice
      has_discounts_applied     — at least one discount reduced this invoice
      auto_scholarships_applied — auto-apply already ran (prevents double-apply)
      auto_discounts_applied    — DiscountEngine already ran (prevents double-apply)

    Refunds: handled directly on Payment.refunded — no separate Refund model.
    """

    STATUS_CHOICES = [
        ('DRAFT',          'Draft'),
        ('PENDING',        'Pending Payment'),
        ('PARTIALLY_PAID', 'Partially Paid'),
        ('PAID',           'Paid in Full'),
        ('OVERDUE',        'Overdue'),
        ('CANCELLED',      'Cancelled'),
        ('VOID',           'Void'),
        ('BAD_DEBT',       'Bad Debt'),
        ('WRITTEN_OFF',    'Written Off'),
        ('UNCOLLECTIBLE',  'Uncollectible'),
    ]

    invoice_number = models.CharField(
        "Invoice Number", max_length=50, unique=True, db_index=True,
    )
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name='fee_invoices',
    )

    academic_session = models.ForeignKey(
        AcademicSession, on_delete=models.PROTECT, related_name='fee_invoices',
    )
    fiscal_period = models.ForeignKey(
        FiscalPeriod, on_delete=models.PROTECT, related_name='invoices',
    )
    fee_structure = models.ForeignKey(
        FeesStructure, on_delete=models.CASCADE, related_name='invoices',
        null=True, blank=True,
    )

    issue_date = models.DateField("Issue Date", db_index=True)
    due_date   = models.DateField("Due Date",   db_index=True)

    subtotal_amount             = models.DecimalField("Subtotal",             max_digits=12, decimal_places=2)
    discount_amount             = models.DecimalField("Discount Amount",       max_digits=12, decimal_places=2, default=Decimal('0.00'))
    scholarship_discount_amount = models.DecimalField("Scholarship Discount",  max_digits=12, decimal_places=2, default=Decimal('0.00'))
    tax_amount                  = models.DecimalField("Tax Amount",            max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_amount                = models.DecimalField("Total Amount",          max_digits=12, decimal_places=2)
    paid_amount                 = models.DecimalField("Paid Amount",           max_digits=12, decimal_places=2, default=Decimal('0.00'))
    balance                     = models.DecimalField("Balance",               max_digits=12, decimal_places=2)
    late_fee_amount             = models.DecimalField("Late Fee Amount",       max_digits=10, decimal_places=2, default=Decimal('0.00'))

    currency = models.CharField(
        "Invoice Currency",
        max_length=3,
        default='',
        blank=True,
        help_text=(
            "Currency this invoice is denominated in. "
            "Blank = school's primary currency (UGX, SSD, etc.). "
            "Set to 'USD' if this invoice was raised in USD."
        ),
    )
    exchange_rate = models.DecimalField(
        "Exchange Rate",
        max_digits=12,
        decimal_places=6,
        default=Decimal('1.000000'),
        help_text=(
            "Rate between invoice currency and school currency at time of issue. "
            "1.0 when invoice currency = school currency."
        ),
    )

    status           = models.CharField("Status", max_length=15, choices=STATUS_CHOICES, default='PENDING', db_index=True)
    is_break_payment = models.BooleanField("Break Period Invoice", default=False)

    has_scholarships_applied  = models.BooleanField("Has Scholarships Applied",  default=False)
    has_discounts_applied     = models.BooleanField("Has Discounts Applied",     default=False)
    auto_scholarships_applied = models.BooleanField("Auto Scholarships Applied", default=False)
    auto_discounts_applied    = models.BooleanField("Auto Discounts Applied",    default=False)

    payment_terms  = models.CharField("Payment Terms", max_length=200, blank=True)
    notes          = models.TextField("Notes",          blank=True)
    internal_notes = models.TextField("Internal Notes", blank=True)

    journal_entry = models.ForeignKey(
        'finance.JournalEntry',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='fee_invoices',
    )

    def get_student_class(self):
        """Return the student's Class for this invoice's academic session."""
        if hasattr(self.student, 'prefetched_class_enrollments'):
            for enrollment in self.student.prefetched_class_enrollments:
                if enrollment.academic_session_id == self.academic_session_id:
                    return enrollment.class_instance
            return None
        from academics.models import StudentClassEnrollment
        enrollment = (
            StudentClassEnrollment.objects
            .filter(student=self.student, academic_session=self.academic_session)
            .select_related('class_instance__academic_level')
            .first()
        )
        return enrollment.class_instance if enrollment else None

    def get_receivable_account(self):
        from core.models import FinancialSettings
        settings = FinancialSettings.get_instance()
        if not settings:
            return None
        return settings.get_account_mappings().student_receivables_account

    def get_revenue_breakdown(self):
        """Return total final_amount grouped by fee category type."""
        rows = self.items.values(
            'fee_category__category_type',
            'fee_category__code',
        ).annotate(total=Sum('final_amount')).order_by('fee_category__category_type')
        return {
            (row['fee_category__category_type'] or row['fee_category__code'] or 'OTHER'): row['total']
            for row in rows
        }

    @property
    def total_in_school_currency(self):
        """
        Sum of all line item amount_in_school_currency values.
        Use this for cross-currency dashboard totals instead of total_amount,
        which is denominated in self.currency (may not be school currency).
        """
        return (
            self.items.aggregate(
                total=models.Sum('amount_in_school_currency')
            )['total'] or Decimal('0.00')
        )

    def can_be_safely_modified(self):
        """Return (True, 'OK') if the invoice can be deleted or edited."""
        if self.status not in ['DRAFT', 'VOID', 'CANCELLED']:
            return False, f"Status is {self.status} (must be DRAFT, VOID, or CANCELLED)"
        if self.paid_amount > 0:
            return False, f"Invoice has payments totalling {self.paid_amount}"
        if self.journal_entry_id:
            from finance.models import JournalEntry
            try:
                je = JournalEntry.objects.get(pk=self.journal_entry_id)
                if je.status not in ['DRAFT', 'REVERSED']:
                    return False, f"Journal entry {je.entry_number} is {je.status}"
            except JournalEntry.DoesNotExist:
                pass
        if self.payments.filter(status='COMPLETED').exists():
            return False, "Invoice has completed payment records"
        return True, "OK"

    def recalculate_totals(self):
        """
        Recompute invoice totals from current line item values.

        All totals are stored in invoice currency (self.currency).
        For ledger/dashboard aggregations across currencies use
        FeeInvoiceItem.amount_in_school_currency on the line items.

        FIX: removed auto_reapply_discounts parameter — discount reapplication
        logic has been extracted to
        fees.invoice_generators.UnifiedStudentInvoiceGenerator.recalculate_with_discounts(invoice).
        Call that instead when you need to wipe and re-run discounts.
        """
        items = self.items.all()
        if not items.exists():
            self.subtotal_amount             = Decimal('0.00')
            self.tax_amount                  = Decimal('0.00')
            self.discount_amount             = Decimal('0.00')
            self.scholarship_discount_amount = Decimal('0.00')
            self.total_amount                = Decimal('0.00')
            self.balance                     = Decimal('0.00')
            self.has_scholarships_applied    = False
            self.has_discounts_applied       = False
            self.save()
            return

        self.subtotal_amount             = sum(i.amount                      for i in items)
        self.tax_amount                  = sum(i.tax_amount                  for i in items)
        self.discount_amount             = sum(i.discount_amount              for i in items)
        self.scholarship_discount_amount = sum(i.scholarship_discount_amount  for i in items)
        self.total_amount                = sum(i.final_amount                 for i in items)
        self.balance                     = self.total_amount - self.paid_amount
        self.has_scholarships_applied    = self.scholarship_discount_amount > Decimal('0.00')
        self.has_discounts_applied       = self.discount_amount > Decimal('0.00')
        self.save()

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

    def __str__(self):
        return f"{self.invoice_number} — {self.student.get_full_name()}"


class FeeInvoiceItem(BaseModel):
    """
    Individual line items within a fee invoice.

    NOTE: Line-item arithmetic (tax, discount, gross) lives in
    fees/utils.py::calculate_line_item_totals() — use that instead of
    duplicating calculations here.
    DiscountApplication.invoice_item FK tracks which discount reduced this item.
    """

    invoice      = models.ForeignKey(
        FeeInvoice, on_delete=models.CASCADE, related_name='items',
    )
    fee_category = models.ForeignKey(
        FeesCategory, on_delete=models.CASCADE,
        related_name='feeinvoiceitem_set',
    )
    description  = models.CharField("Description", max_length=255, blank=True)

    quantity    = models.DecimalField("Quantity",    max_digits=8,  decimal_places=2, default=Decimal('1.00'))
    unit_amount = models.DecimalField("Unit Amount", max_digits=10, decimal_places=2)
    amount      = models.DecimalField("Amount",      max_digits=10, decimal_places=2)

    tax_percentage = models.DecimalField("Tax %",      max_digits=5,  decimal_places=2, default=Decimal('0.00'))
    tax_amount     = models.DecimalField("Tax Amount", max_digits=10, decimal_places=2, default=Decimal('0.00'))

    discount_percentage         = models.DecimalField("Discount %",              max_digits=5,  decimal_places=2, default=Decimal('0.00'))
    discount_amount             = models.DecimalField("Regular Discount Amount",  max_digits=10, decimal_places=2, default=Decimal('0.00'))
    scholarship_discount_amount = models.DecimalField("Scholarship Discount",     max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total_discount_amount       = models.DecimalField("Total Discount Amount",    max_digits=10, decimal_places=2, default=Decimal('0.00'))

    final_amount    = models.DecimalField("Final Amount",    max_digits=10, decimal_places=2)
    original_amount = models.DecimalField("Original Amount", max_digits=10, decimal_places=2, null=True, blank=True)

    currency = models.CharField(
        "Line Item Currency",
        max_length=3,
        blank=True,
        help_text=(
            "Currency for this line item. Resolved from: "
            "FeesStructureItem → FeesCategory → school currency."
        ),
    )
    exchange_rate = models.DecimalField(
        "Exchange Rate",
        max_digits=12,
        decimal_places=6,
        default=Decimal('1.000000'),
        help_text="Rate to school currency at time of invoice generation.",
    )
    amount_in_school_currency = models.DecimalField(
        "Amount in School Currency",
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="amount × exchange_rate. What posts to the ledger.",
    )

    has_scholarship_discount = models.BooleanField("Has Scholarship Discount", default=False)
    has_regular_discount     = models.BooleanField("Has Regular Discount",     default=False)

    def recalculate_totals(self):
        """Update amount, tax, discount, final_amount, and amount_in_school_currency."""
        self.amount                = self.unit_amount * self.quantity
        self.total_discount_amount = self.discount_amount + self.scholarship_discount_amount
        taxable_amount             = self.amount - self.total_discount_amount
        self.tax_amount            = (taxable_amount * self.tax_percentage / Decimal('100.00')).quantize(Decimal('0.01'))
        self.final_amount          = taxable_amount + self.tax_amount
        self.has_regular_discount     = self.discount_amount > Decimal('0.00')
        self.has_scholarship_discount = self.scholarship_discount_amount > Decimal('0.00')
        self.amount_in_school_currency = (
            self.final_amount * self.exchange_rate
        ).quantize(Decimal('0.01'))

    class Meta:
        verbose_name = "Fee Invoice Item"
        verbose_name_plural = "Fee Invoice Items"
        indexes = [
            models.Index(fields=['invoice', 'fee_category']),
            models.Index(fields=['has_scholarship_discount']),
            models.Index(fields=['has_regular_discount']),
        ]

    def __str__(self):
        return f"{self.invoice.invoice_number} — {self.fee_category.name}"


# =============================================================================
# PAYMENTS
# =============================================================================

class Payment(BaseModel):
    """
    Payment model with reversal and refund support.

    REVERSAL — internal accounting correction, no money movement.
    REFUND   — actual money returned to the payer.

    A payment can be EITHER reversed OR refunded, never both.
    """

    PAYMENT_STATUS_CHOICES = [
        ('PENDING',    'Pending'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED',  'Completed'),
        ('FAILED',     'Failed'),
        ('CANCELLED',  'Cancelled'),
        ('REVERSED',   'Reversed'),
        ('REFUNDED',   'Refunded'),
    ]

    PAYER_RELATIONSHIP_CHOICES = [
        ('STUDENT',       'Student (Self)'),
        ('FATHER',        'Father'),
        ('MOTHER',        'Mother'),
        ('UNCLE',         'Uncle'),
        ('AUNT',          'Aunt'),
        ('BROTHER',       'Brother'),
        ('SISTER',        'Sister'),
        ('GUARDIAN',      'Guardian'),
        ('SPONSOR',       'Sponsor'),
        ('GRANDPARENT',   'Grandparent'),
        ('STEP_FATHER',   'Step Father'),
        ('STEP_MOTHER',   'Step Mother'),
        ('FOSTER_PARENT', 'Foster Parent'),
        ('OTHER',         'Other'),
    ]

    REFUND_METHOD_CHOICES = [
        ('CASH',            'Cash'),
        ('BANK_TRANSFER',   'Bank Transfer'),
        ('MOBILE_MONEY',    'Mobile Money'),
        ('CHEQUE',          'Cheque'),
        ('ORIGINAL_METHOD', 'Refund to Original Payment Method'),
    ]

    payment_number = models.CharField("Payment Number", max_length=50, unique=True, db_index=True)
    invoice = models.ForeignKey(
        FeeInvoice, on_delete=models.CASCADE, related_name='payments',
    )
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name='payments',
    )

    amount = models.DecimalField(
        "Amount", max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    amount_applied_to_invoice = models.DecimalField(
        "Amount Applied to Invoice", max_digits=12, decimal_places=2, default=Decimal('0.00'),
    )
    overpayment_amount = models.DecimalField(
        "Overpayment Amount", max_digits=12, decimal_places=2, default=Decimal('0.00'),
    )

    payment_date   = models.DateField("Payment Date", db_index=True)
    payment_method = models.ForeignKey(
        PaymentMethod, on_delete=models.PROTECT, related_name='student_payments',
    )
    reference_number = models.CharField("Reference Number", max_length=100, blank=True, db_index=True)
    transaction_id   = models.CharField("Transaction ID",   max_length=100, blank=True, db_index=True)

    bank_name      = models.CharField("Bank Name",      max_length=100, blank=True)
    account_number = models.CharField("Account Number", max_length=50,  blank=True)
    cheque_number  = models.CharField("Cheque Number",  max_length=50,  blank=True)
    cheque_date    = models.DateField("Cheque Date", null=True, blank=True)

    currency = models.CharField(
        "Payment Currency",
        max_length=3,
        blank=True,
        help_text=(
            "Currency the parent paid in. Blank = school currency. "
            "Example: 'USD' if parent paid in dollars."
        ),
    )
    exchange_rate = models.DecimalField(
        "Exchange Rate Used",
        max_digits=12,
        decimal_places=6,
        default=Decimal('1.000000'),
        help_text=(
            "Rate entered by cashier at time of payment. "
            "Stored permanently — never recalculated."
        ),
    )
    amount_in_school_currency = models.DecimalField(
        "Amount in School Currency",
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=(
            "amount × exchange_rate. "
            "This is what credits the student account and hits the journal."
        ),
    )

    mobile_money_provider = models.CharField("Mobile Money Provider", max_length=50, blank=True)
    mobile_number         = models.CharField("Mobile Number",         max_length=20, blank=True)

    paid_by_name         = models.CharField("Paid By (Name)",    max_length=200, blank=True, null=True)
    paid_by_phone        = models.CharField("Paid By (Phone)",   max_length=20,  blank=True, null=True)
    paid_by_email        = models.EmailField("Paid By (Email)",                  blank=True, null=True)
    paid_by_relationship = models.CharField(
        "Relationship to Student", max_length=50, blank=True, null=True,
        choices=PAYER_RELATIONSHIP_CHOICES,
    )

    processing_fee_amount = models.DecimalField(
        "Processing Fee Amount", max_digits=10, decimal_places=2, default=Decimal('0.00'),
    )
    processing_fee_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='processing_fee_payments',
        null=True, blank=True,
    )

    status            = models.CharField("Payment Status", max_length=12, choices=PAYMENT_STATUS_CHOICES, default='COMPLETED', db_index=True)
    is_verified       = models.BooleanField("Verified", default=False, db_index=True)
    verified_by_id    = models.CharField("Verified By ID",    max_length=50, null=True, blank=True)
    verification_date = models.DateTimeField("Verification Date", null=True, blank=True)

    receipt_number      = models.CharField("Receipt Number", max_length=50, unique=True, db_index=True)
    receipt_issued      = models.BooleanField("Receipt Issued", default=False)
    receipt_issued_date = models.DateTimeField("Receipt Issued Date", null=True, blank=True)

    received_by_id  = models.CharField("Received By ID",  max_length=50, null=True, blank=True)
    processed_by_id = models.CharField("Processed By ID", max_length=50, null=True, blank=True)

    reversed        = models.BooleanField("Reversed", default=False, db_index=True)
    reversed_on     = models.DateTimeField("Reversed On", null=True, blank=True)
    reversed_by_id  = models.CharField("Reversed By ID", max_length=50, null=True, blank=True)
    reversal_reason = models.TextField("Reversal Reason", blank=True)
    reversal_journal_entry = models.ForeignKey(
        'finance.JournalEntry',
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reversed_fee_payments',
    )

    refunded         = models.BooleanField("Refunded", default=False, db_index=True)
    refunded_on      = models.DateTimeField("Refunded On", null=True, blank=True)
    refunded_by_id   = models.CharField("Refunded By ID", max_length=50, null=True, blank=True)
    refund_method    = models.CharField("Refund Method",  max_length=50, blank=True, choices=REFUND_METHOD_CHOICES)
    refund_reference = models.CharField("Refund Reference", max_length=100, blank=True, db_index=True)
    refund_notes     = models.TextField("Refund Notes", blank=True)
    refund_journal_entry = models.ForeignKey(
        'finance.JournalEntry',
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='refunded_fee_payments',
    )

    remarks        = models.TextField("Remarks",        blank=True)
    internal_notes = models.TextField("Internal Notes", blank=True)

    academic_session = models.ForeignKey(
        AcademicSession, on_delete=models.SET_NULL,
        null=True, related_name='payments',
    )
    fiscal_period = models.ForeignKey(
        FiscalPeriod, on_delete=models.PROTECT, related_name='payments',
    )
    is_break_payment = models.BooleanField("Break Period Payment", default=False)
    fee_breakdown    = models.JSONField("Fee Breakdown", default=dict, blank=True)

    journal_entry = models.ForeignKey(
        'finance.JournalEntry',
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='fee_payments',
    )
    auto_create_journal_entry = models.BooleanField("Auto-Create Journal Entry", default=True)

    # -------------------------------------------------------------------------
    # ACCOUNT HELPERS
    # -------------------------------------------------------------------------

    def get_deposit_account(self):
        from core.models import FinancialSettings
        settings = FinancialSettings.get_instance()
        if not settings:
            return None
        return settings.get_account_mappings().get_cash_or_bank_account(self.payment_method)

    def get_receivable_account(self):
        from core.models import FinancialSettings
        settings = FinancialSettings.get_instance()
        if not settings:
            return None
        return settings.get_account_mappings().student_receivables_account

    # -------------------------------------------------------------------------
    # VALIDATION
    # -------------------------------------------------------------------------

    def clean(self):
        super().clean()
        errors = {}
        if self.reversed and self.refunded:
            errors['reversed'] = "A payment cannot be both reversed and refunded."
            errors['refunded'] = "A payment cannot be both reversed and refunded."
        if self.reversed and not self.reversal_reason:
            errors['reversal_reason'] = "A reversal reason is required."
        if self.refunded and not self.refund_method:
            errors['refund_method'] = "A refund method is required."
        if self.amount < 0:
            errors['amount'] = "Payment amount cannot be negative."
        if self.amount_applied_to_invoice > self.amount:
            errors['amount_applied_to_invoice'] = "Cannot exceed total payment amount."
        if self.overpayment_amount < 0:
            errors['overpayment_amount'] = "Overpayment amount cannot be negative."
        if self.exchange_rate is not None and self.exchange_rate <= 0:
            errors['exchange_rate'] = "Exchange rate must be greater than zero."
        if errors:
            raise ValidationError(errors)

    # -------------------------------------------------------------------------
    # STATE PROPERTIES
    # -------------------------------------------------------------------------

    @property
    def is_active(self):
        return not self.reversed and not self.refunded

    @property
    def effective_amount(self):
        """Effective amount in school currency. Zero if reversed or refunded."""
        if not self.is_active:
            return Decimal('0.00')
        return self.amount_in_school_currency

    @property
    def effective_amount_original(self):
        """Effective amount in original payment currency. Zero if reversed or refunded."""
        return self.amount if self.is_active else Decimal('0.00')

    @property
    def payment_state(self):
        if self.reversed:
            return "REVERSED"
        if self.refunded:
            return "REFUNDED"
        if self.status == 'COMPLETED' and self.is_verified:
            return "ACTIVE"
        return self.status

    # -------------------------------------------------------------------------
    # REVERSAL
    # -------------------------------------------------------------------------

    def can_be_reversed(self):
        if self.reversed:
            return False, "Payment already reversed."
        if self.refunded:
            return False, "Cannot reverse a refunded payment."
        if self.status in ['FAILED', 'CANCELLED']:
            return False, f"Cannot reverse a {self.status.lower()} payment."
        if self.fiscal_period and getattr(self.fiscal_period, 'is_closed', False):
            return False, "Cannot reverse a payment from a closed fiscal period."
        return True, "OK"

    def reverse(self, reason, reversed_by):
        from django.db import transaction as db_transaction
        can_reverse, error_reason = self.can_be_reversed()
        if not can_reverse:
            raise ValidationError(error_reason)
        with db_transaction.atomic():
            self.reversed        = True
            self.reversed_on     = timezone.now()
            self.reversed_by_id  = str(reversed_by.id)
            self.reversal_reason = reason
            self.status          = 'REVERSED'
            self.save()

    # -------------------------------------------------------------------------
    # REFUND
    # -------------------------------------------------------------------------

    def can_be_refunded(self):
        if self.refunded:
            return False, "Payment already refunded."
        if self.reversed:
            return False, "Cannot refund a reversed payment."
        if self.status != 'COMPLETED':
            return False, f"Can only refund completed payments (current: {self.status})."
        return True, "OK"

    # -------------------------------------------------------------------------
    # USER LOOKUPS
    # -------------------------------------------------------------------------

    def _get_user(self, user_id):
        if not user_id:
            return None
        try:
            return get_user_model().objects.using('default').get(id=user_id)
        except Exception:
            return None

    def get_verified_by_user(self):  return self._get_user(self.verified_by_id)
    def get_received_by_user(self):  return self._get_user(self.received_by_id)
    def get_processed_by_user(self): return self._get_user(self.processed_by_id)
    def get_reversed_by_user(self):  return self._get_user(self.reversed_by_id)
    def get_refunded_by_user(self):  return self._get_user(self.refunded_by_id)

    # -------------------------------------------------------------------------
    # AUDIT TRAIL
    # -------------------------------------------------------------------------

    def get_audit_trail(self):
        # FIX: was self.get_created_by_user() which does not exist on BaseModel.
        # Corrected to self.get_created_by() which is the method defined on BaseModel.
        trail = [
            {
                'action':    'CREATED',
                'timestamp': self.created_at,
                'user':      self.get_created_by(),
                'details':   (
                    f"Payment {self.payment_number} created — "
                    f"{self.amount:,.2f} {self.currency or 'school currency'} "
                    f"(school currency: {self.amount_in_school_currency:,.2f})"
                ),
            }
        ]
        if self.receipt_issued and self.receipt_issued_date:
            trail.append({
                'action':    'RECEIPT_ISSUED',
                'timestamp': self.receipt_issued_date,
                'details':   f"Receipt {self.receipt_number} issued",
            })
        if self.is_verified and self.verification_date:
            trail.append({
                'action':    'VERIFIED',
                'timestamp': self.verification_date,
                'user':      self.get_verified_by_user(),
                'details':   "Payment verified by finance team",
            })
        if self.journal_entry:
            trail.append({
                'action':    'JOURNAL_ENTRY_CREATED',
                'timestamp': self.journal_entry.created_at,
                'details':   f"Journal entry {self.journal_entry.entry_number} created",
            })
        if self.reversed and self.reversed_on:
            trail.append({
                'action':    'REVERSED',
                'timestamp': self.reversed_on,
                'user':      self.get_reversed_by_user(),
                'details':   f"Reversed — {self.reversal_reason}",
            })
            if self.reversal_journal_entry:
                trail.append({
                    'action':    'REVERSAL_JE',
                    'timestamp': self.reversal_journal_entry.created_at,
                    'details':   f"Reversal JE {self.reversal_journal_entry.entry_number}",
                })
        if self.refunded and self.refunded_on:
            trail.append({
                'action':    'REFUNDED',
                'timestamp': self.refunded_on,
                'user':      self.get_refunded_by_user(),
                'details':   f"Refund via {self.refund_method} — ref: {self.refund_reference}",
            })
            if self.refund_journal_entry:
                trail.append({
                    'action':    'REFUND_JE',
                    'timestamp': self.refund_journal_entry.created_at,
                    'details':   f"Refund JE {self.refund_journal_entry.entry_number}",
                })
        trail.sort(key=lambda e: e['timestamp'])
        return trail

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
            models.Index(fields=['reversed']),
            models.Index(fields=['refunded']),
            models.Index(fields=['refunded_on']),
            models.Index(fields=['refund_reference']),
        ]
        constraints = [
            models.CheckConstraint(check=models.Q(amount__gt=0),              name='payment_amount_positive'),
            models.CheckConstraint(check=models.Q(overpayment_amount__gte=0), name='payment_overpayment_non_negative'),
            models.CheckConstraint(check=models.Q(processing_fee_amount__gte=0), name='payment_processing_fee_non_negative'),
        ]

    def __str__(self):
        suffix = " [REVERSED]" if self.reversed else (" [REFUNDED]" if self.refunded else "")
        return f"{self.payment_number} — {self.student.get_full_name()} — {self.amount:,.2f}{suffix}"


class BadDebtWriteOff(BaseModel):
    """Tracks bad debt write-offs for uncollectible invoices."""

    invoice          = models.ForeignKey(FeeInvoice, on_delete=models.PROTECT, related_name='bad_debt_write_offs')
    write_off_amount = models.DecimalField("Write-Off Amount", max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    write_off_date   = models.DateField("Write-Off Date")
    fiscal_period    = models.ForeignKey('core.FiscalPeriod', on_delete=models.PROTECT, related_name='bad_debt_write_offs')
    use_allowance_method = models.BooleanField("Use Allowance Method", default=False)
    reason           = models.TextField("Reason for Write-Off")
    approved_by_id   = models.CharField("Approved By ID", max_length=50, null=True, blank=True)
    approval_date    = models.DateTimeField("Approval Date", null=True, blank=True)
    journal_entry    = models.ForeignKey('finance.JournalEntry', on_delete=models.SET_NULL, null=True, blank=True, related_name='bad_debt_write_offs')

    class Meta:
        verbose_name = "Bad Debt Write-Off"
        verbose_name_plural = "Bad Debt Write-Offs"
        ordering = ['-write_off_date']

    def __str__(self):
        return f"Write-off: {self.invoice.invoice_number} — {self.write_off_amount}"


# =============================================================================
# SCHOLARSHIP PROGRAMS
# =============================================================================

class ScholarshipProgram(BaseModel):
    """
    Scholarship programs with global or category-specific discount templates.

    DISCOUNT MODES
    --------------
    GLOBAL:            discount_type = PERCENTAGE | FIXED_AMOUNT | FULL_WAIVER
    CATEGORY-SPECIFIC: discount_type = CATEGORY_SPECIFIC
                       default_category_discounts defines template per category.

    COMBINATION MODES
    -----------------
    STANDALONE: replaces all other scholarships.
    ADDITIVE:   stacks on top.
    BEST_OF:    system keeps only the highest-value single award.

    AUTO-AWARD
    ----------
    Safe only for: NEED_BASED, SPECIAL_CIRCUMSTANCES, EMERGENCY_AID.
    Must be False for merit types — clean() enforces this.
    """

    SCHOLARSHIP_TYPES = [
        ('ACADEMIC_MERIT',        'Academic Merit'),
        ('SPORTS_EXCELLENCE',     'Sports Excellence'),
        ('ARTS_TALENT',           'Arts & Talent'),
        ('LEADERSHIP',            'Leadership Excellence'),
        ('COMMUNITY_SERVICE',     'Community Service'),
        ('NEED_BASED',            'Need-Based'),
        ('SPECIAL_CIRCUMSTANCES', 'Special Circumstances'),
        ('EMERGENCY_AID',         'Emergency Financial Aid'),
        ('ALUMNI_SPONSORED',      'Alumni Sponsored'),
        ('CORPORATE_SPONSORED',   'Corporate Sponsored'),
        ('GOVERNMENT_BURSARY',    'Government Bursary'),
        ('FULL_SCHOLARSHIP',      'Full Scholarship'),
        ('PARTIAL_SCHOLARSHIP',   'Partial Scholarship'),
    ]

    DISCOUNT_TYPE_CHOICES = [
        ('PERCENTAGE',        'Percentage Discount (Global)'),
        ('FIXED_AMOUNT',      'Fixed Amount Discount (Global)'),
        ('FULL_WAIVER',       'Full Fee Waiver (Global)'),
        ('CATEGORY_SPECIFIC', 'Category-Specific Discounts'),
    ]

    PROGRAM_TYPE_CHOICES = [
        ('BUDGETED',      'Budgeted Program'),
        ('POLICY_BASED',  'Policy-Based Program'),
        ('DISCRETIONARY', 'Discretionary'),
        ('SPONSORED',     'Externally Sponsored'),
    ]

    RENEWAL_CHOICES = [
        ('AUTOMATIC',          'Automatic Renewal'),
        ('PERFORMANCE_BASED',  'Performance-Based Review'),
        ('ANNUAL_APPLICATION', 'Annual Re-application Required'),
        ('ONE_TIME_ONLY',      'One-Time Award'),
    ]

    COMBINATION_MODE_CHOICES = [
        ('STANDALONE', 'Replaces all other scholarships'),
        ('ADDITIVE',   'Stacks on top of other scholarships'),
        ('BEST_OF',    'System picks the highest single award'),
    ]

    _MERIT_TYPES = {
        'ACADEMIC_MERIT', 'SPORTS_EXCELLENCE', 'ARTS_TALENT',
        'LEADERSHIP', 'COMMUNITY_SERVICE',
        'ALUMNI_SPONSORED', 'CORPORATE_SPONSORED',
    }

    name             = models.CharField("Program Name", max_length=200)
    code             = models.CharField("Program Code", max_length=50, unique=True, db_index=True)
    scholarship_type = models.CharField("Scholarship Type", max_length=30, choices=SCHOLARSHIP_TYPES, db_index=True)
    description      = models.TextField("Description")

    program_type  = models.CharField("Program Type",  max_length=20, choices=PROGRAM_TYPE_CHOICES, default='POLICY_BASED')
    discount_type = models.CharField("Discount Type", max_length=20, choices=DISCOUNT_TYPE_CHOICES)

    discount_percentage   = models.DecimalField("Global Discount %",          max_digits=5,  decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))])
    fixed_discount_amount = models.DecimalField("Global Fixed Discount Amount", max_digits=12, decimal_places=2, null=True, blank=True)
    maximum_award_amount  = models.DecimalField("Max Award Per Student",       max_digits=12, decimal_places=2, null=True, blank=True)

    default_category_discounts = models.JSONField(
        "Default Category Discount Template", default=dict, blank=True,
        help_text='{"TUITION": {"type": "percentage", "value": 100}, "BOARDING": {"type": "none", "value": 0}}',
    )
    allows_category_customization = models.BooleanField("Allow Category Customization", default=True)
    category_discount_description = models.TextField("Category Discount Explanation", blank=True)

    applicable_fee_categories = models.ManyToManyField(FeesCategory, blank=True)

    combination_mode = models.CharField("Combination Mode", max_length=12, choices=COMBINATION_MODE_CHOICES, default='BEST_OF')
    auto_award       = models.BooleanField("Auto-Award Eligible Students", default=False)

    minimum_gpa                   = models.DecimalField("Minimum GPA",          max_digits=4,  decimal_places=2, null=True, blank=True)
    minimum_attendance_percentage = models.DecimalField("Min Attendance %",     max_digits=5,  decimal_places=2, null=True, blank=True)
    family_income_threshold       = models.DecimalField("Family Income Threshold", max_digits=15, decimal_places=2, null=True, blank=True)
    applicable_levels             = models.ManyToManyField(AcademicLevel, blank=True)

    total_budget_amount      = models.DecimalField("Total Program Budget",    max_digits=15, decimal_places=2, null=True, blank=True)
    requires_budget_tracking = models.BooleanField("Requires Budget Tracking", default=False)
    maximum_recipients       = models.PositiveIntegerField("Max Recipients",   null=True, blank=True)
    current_budget_used      = models.DecimalField("Current Budget Used",     max_digits=15, decimal_places=2, default=Decimal('0.00'))
    current_recipient_count  = models.PositiveIntegerField("Current Recipients", default=0)

    renewal_policy         = models.CharField("Renewal Policy",     max_length=20, choices=RENEWAL_CHOICES, default='ANNUAL_APPLICATION')
    maximum_duration_years = models.PositiveIntegerField("Max Duration (Years)", default=1)

    application_start_date  = models.DateField("Application Opens",    null=True, blank=True)
    application_end_date    = models.DateField("Application Deadline", null=True, blank=True)
    award_announcement_date = models.DateField("Award Announcement",   null=True, blank=True)

    sponsor_name            = models.CharField("Sponsor Name",           max_length=200, blank=True)
    sponsor_contact         = models.TextField("Sponsor Contact",         blank=True)
    external_funding_source = models.CharField("External Funding Source", max_length=200, blank=True)

    is_active                 = models.BooleanField("Is Active",             default=True, db_index=True)
    is_accepting_applications = models.BooleanField("Accepting Applications", default=True)
    valid_sessions            = models.ManyToManyField(AcademicSession, blank=True)

    def clean(self):
        super().clean()
        errors = {}
        if self.program_type in ['BUDGETED', 'SPONSORED'] and not self.total_budget_amount:
            errors['total_budget_amount'] = 'Required for BUDGETED and SPONSORED programs.'
        if self.discount_type == 'PERCENTAGE':
            if not self.discount_percentage:
                errors['discount_percentage'] = 'Required when discount_type is PERCENTAGE.'
        elif self.discount_type == 'FIXED_AMOUNT':
            if not self.fixed_discount_amount:
                errors['fixed_discount_amount'] = 'Required when discount_type is FIXED_AMOUNT.'
        if self.auto_award and self.scholarship_type in self._MERIT_TYPES:
            errors['auto_award'] = f'{self.get_scholarship_type_display()} scholarships require human approval.'
        if self.application_start_date and self.application_end_date:
            if self.application_end_date < self.application_start_date:
                errors['application_end_date'] = 'Cannot be before start date.'
        if errors:
            raise ValidationError(errors)

    def is_global_discount(self):
        return self.discount_type in ['PERCENTAGE', 'FIXED_AMOUNT', 'FULL_WAIVER']

    def is_category_specific_discount(self):
        return self.discount_type == 'CATEGORY_SPECIFIC'

    def get_discount_summary(self):
        # FIX: was hard-coded 'UGX' — now resolved from FinancialSettings
        from core.models import FinancialSettings
        currency = FinancialSettings.get_school_currency()

        if self.discount_type == 'PERCENTAGE':
            return f"{self.discount_percentage}% off all eligible fees"
        if self.discount_type == 'FIXED_AMOUNT':
            return f"Fixed {self.fixed_discount_amount:,.0f} {currency} off per invoice"
        if self.discount_type == 'FULL_WAIVER':
            return "100% fee waiver"
        if self.discount_type == 'CATEGORY_SPECIFIC':
            if not self.default_category_discounts:
                return "Category-specific (not yet configured)"
            parts = []
            for code, config in self.default_category_discounts.items():
                t, v = config.get('type'), config.get('value', 0)
                if t == 'percentage':     parts.append(f"{code}: {v}%")
                elif t == 'fixed_amount': parts.append(f"{code}: {v:,.0f} {currency}")
                elif t == 'full_waiver':  parts.append(f"{code}: 100%")
                elif t == 'none':         parts.append(f"{code}: not covered")
            summary = ", ".join(parts[:3])
            if len(parts) > 3:
                summary += f" (+{len(parts) - 3} more)"
            return f"Category-specific: {summary}"
        return "Not configured"

    def get_category_discount_template(self):
        return self.default_category_discounts.copy() if self.is_category_specific_discount() else {}

    def get_remaining_budget(self):
        if not self.total_budget_amount:
            return None
        return self.total_budget_amount - self.current_budget_used

    def has_budget_available(self, amount=Decimal('0.00')):
        if not self.requires_budget_tracking or not self.total_budget_amount:
            return True
        remaining = self.get_remaining_budget()
        return remaining is not None and remaining >= amount

    def can_accept_new_recipient(self):
        if not self.is_active:
            return False, "Program is not active"
        if self.maximum_recipients and self.current_recipient_count >= self.maximum_recipients:
            return False, f"Maximum recipients reached ({self.maximum_recipients})"
        if self.requires_budget_tracking and self.total_budget_amount:
            remaining = self.get_remaining_budget()
            if remaining is not None and remaining <= 0:
                return False, "Program budget exhausted"
        return True, "OK"

    class Meta:
        verbose_name = "Scholarship Program"
        verbose_name_plural = "Scholarship Programs"
        ordering = ['name']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['scholarship_type']),
            models.Index(fields=['is_active']),
            models.Index(fields=['program_type']),
            models.Index(fields=['discount_type']),
            models.Index(fields=['combination_mode']),
            models.Index(fields=['auto_award']),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"


class StudentScholarshipApplication(BaseModel):
    """Student applications for scholarships."""

    APPLICATION_STATUS_CHOICES = [
        ('DRAFT',        'Draft'),
        ('SUBMITTED',    'Submitted'),
        ('UNDER_REVIEW', 'Under Review'),
        ('APPROVED',     'Approved'),
        ('REJECTED',     'Rejected'),
        ('WAITLISTED',   'Waitlisted'),
        ('WITHDRAWN',    'Withdrawn'),
    ]

    application_number  = models.CharField("Application Number", max_length=50, unique=True, db_index=True)
    student             = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='scholarship_applications')
    scholarship_program = models.ForeignKey(ScholarshipProgram, on_delete=models.CASCADE, related_name='applications')
    academic_session    = models.ForeignKey(AcademicSession, on_delete=models.CASCADE, related_name='scholarship_application_records')

    application_date      = models.DateField("Application Date", auto_now_add=True)
    requested_amount      = models.DecimalField("Requested Amount", max_digits=12, decimal_places=2, null=True, blank=True)
    essay                 = models.TextField("Personal Essay", blank=True)
    family_income         = models.DecimalField("Family Monthly Income", max_digits=12, decimal_places=2, null=True, blank=True)
    number_of_dependents  = models.PositiveIntegerField("Number of Dependents", null=True, blank=True)
    special_circumstances = models.TextField("Special Circumstances", blank=True)
    current_gpa           = models.DecimalField("Current GPA", max_digits=4, decimal_places=2, null=True, blank=True)
    attendance_percentage = models.DecimalField("Attendance %", max_digits=5, decimal_places=2, null=True, blank=True)
    supporting_documents  = models.JSONField("Supporting Documents", default=list, blank=True)

    status = models.CharField(
        "Status",
        max_length=15,
        choices=APPLICATION_STATUS_CHOICES,
        default='SUBMITTED',
        db_index=True,
    )

    reviewed_by_id = models.CharField(
        "Reviewed By ID",
        max_length=50,
        null=True,
        blank=True,
        help_text="User ID who reviewed this application",
    )
    reviewed_at    = models.DateTimeField("Review Date", null=True, blank=True)
    reviewer_notes = models.TextField("Review Notes", blank=True)

    approved_amount = models.DecimalField("Approved Amount", max_digits=12, decimal_places=2, null=True, blank=True)
    effective_date  = models.DateField("Effective Date", null=True, blank=True)
    decision_reason = models.TextField("Decision Reason", blank=True)

    class Meta:
        verbose_name = "Scholarship Application"
        verbose_name_plural = "Scholarship Applications"
        ordering = ['-application_date']
        indexes = [
            models.Index(fields=['application_number']),
            models.Index(fields=['student', 'status']),
            models.Index(fields=['scholarship_program']),
            models.Index(fields=['status']),
            models.Index(fields=['reviewed_by_id']),
        ]

    def __str__(self):
        return f"{self.application_number} — {self.student.get_full_name()} — {self.scholarship_program.name}"

    def get_reviewed_by_user(self):
        if not self.reviewed_by_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            return get_user_model().objects.using('default').get(id=self.reviewed_by_id)
        except Exception as e:
            logger.error(f"Error fetching reviewed_by user: {e}")
            return None


class StudentScholarship(BaseModel):
    """
    Active scholarship awarded to a student.

    Operating modes:
      Policy-based  (amount_awarded = 0):  Discount % from program.
      Budget-based  (amount_awarded > 0):  Fixed pot tracked against amount_awarded.
      Category-specific: per-category control via category_discounts JSON.
    """

    SCHOLARSHIP_STATUS_CHOICES = [
        ('ACTIVE',    'Active'),
        ('SUSPENDED', 'Suspended'),
        ('TERMINATED','Terminated'),
        ('COMPLETED', 'Completed'),
        ('PENDING',   'Pending Activation'),
    ]

    DISTRIBUTION_METHOD_CHOICES = [
        ('UNTIL_EXHAUSTED',   'Apply Until Exhausted'),
        ('EQUAL_PER_SESSION', 'Equal Amount Per Academic Session'),
        ('EQUAL_PER_INVOICE', 'Equal Amount Per Invoice'),
        ('PROPORTIONAL',      'Proportional to Invoice Amount'),
        ('MANUAL',            'Manual Allocation Per Session'),
    ]

    student             = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='scholarships')
    scholarship_program = models.ForeignKey(ScholarshipProgram, on_delete=models.CASCADE, related_name='student_scholarships')
    application         = models.OneToOneField(StudentScholarshipApplication, on_delete=models.SET_NULL, null=True, blank=True, related_name='awarded_scholarship')

    amount_awarded    = models.DecimalField("Total Amount Awarded",    max_digits=12, decimal_places=2, default=Decimal('0.00'), validators=[MinValueValidator(Decimal('0.00'))])
    total_amount_used = models.DecimalField("Total Amount Used to Date", max_digits=12, decimal_places=2, default=Decimal('0.00'), validators=[MinValueValidator(Decimal('0.00'))])

    use_category_specific_discounts = models.BooleanField("Use Category-Specific Discounts", default=False, db_index=True)
    category_discounts = models.JSONField(
        "Category-Specific Discount Rules", default=dict, blank=True,
        help_text='{"TUITION": {"type": "percentage", "value": 100}, "BOARDING": {"type": "none", "value": 0}}',
    )
    category_discount_notes = models.TextField("Category Discount Notes", blank=True)

    start_date = models.DateField("Start Date")
    end_date   = models.DateField("End Date", null=True, blank=True)

    distribution_method    = models.CharField("Distribution Method", max_length=20, choices=DISTRIBUTION_METHOD_CHOICES, default='PROPORTIONAL')
    amount_per_session     = models.DecimalField("Amount Per Session",  max_digits=12, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal('0.01'))])
    amount_per_invoice     = models.DecimalField("Amount Per Invoice",  max_digits=12, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal('0.01'))])
    max_amount_per_session = models.DecimalField("Max Per Session",     max_digits=12, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal('0.01'))])

    status = models.CharField("Status", max_length=15, choices=SCHOLARSHIP_STATUS_CHOICES, default='ACTIVE', db_index=True)

    is_renewable                  = models.BooleanField("Is Renewable", default=True)
    requires_renewal_verification = models.BooleanField("Requires Renewal Verification", default=True)
    renewal_criteria              = models.JSONField("Renewal Criteria", default=dict, blank=True)
    next_renewal_check_date       = models.DateField("Next Renewal Check Date", null=True, blank=True)
    times_renewed                 = models.PositiveIntegerField("Times Renewed", default=0)
    last_renewal_date             = models.DateField("Last Renewal Date", null=True, blank=True)

    current_gpa        = models.DecimalField("Current GPA",         max_digits=4, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('4.00'))])
    current_attendance = models.DecimalField("Current Attendance %", max_digits=5, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))])
    performance_notes  = models.TextField("Performance Notes", blank=True)

    awarded_by_id      = models.CharField("Awarded By ID", max_length=50, null=True, blank=True)
    awarded_date       = models.DateField("Date Awarded", null=True, blank=True)
    notes              = models.TextField("Administrative Notes", blank=True)
    suspension_reason  = models.TextField("Suspension Reason", blank=True)
    termination_reason = models.TextField("Termination Reason", blank=True)

    def clean(self):
        super().clean()
        if not self.scholarship_program_id:
            return
        program = self.scholarship_program
        errors  = {}

        if program.program_type in ['BUDGETED', 'SPONSORED'] and program.discount_type == 'FIXED_AMOUNT':
            if not self.amount_awarded or self.amount_awarded <= 0:
                errors['amount_awarded'] = f"'{program.name}' is budget-based and requires a specific amount."

        if self.amount_awarded and self.amount_awarded > 0:
            if self.total_amount_used > self.amount_awarded:
                errors['total_amount_used'] = f"Used ({self.total_amount_used}) cannot exceed awarded ({self.amount_awarded})"

        if self.use_category_specific_discounts and not self.category_discounts:
            errors[None] = "Category-specific discounts enabled but no rules configured."

        if self.distribution_method == 'EQUAL_PER_SESSION' and not self.amount_per_session:
            errors['amount_per_session'] = "Required when distribution_method is EQUAL_PER_SESSION."
        if self.distribution_method == 'EQUAL_PER_INVOICE' and not self.amount_per_invoice:
            errors['amount_per_invoice'] = "Required when distribution_method is EQUAL_PER_INVOICE."

        if self.end_date and self.start_date and self.end_date < self.start_date:
            errors['end_date'] = "End date cannot be before start date."

        if errors:
            raise ValidationError(errors)

    def is_policy_based(self):
        p = self.scholarship_program
        return p.program_type == 'POLICY_BASED' and p.discount_type in ['PERCENTAGE', 'FULL_WAIVER']

    def is_budget_based(self):
        p = self.scholarship_program
        return p.program_type in ['BUDGETED', 'SPONSORED'] and p.discount_type == 'FIXED_AMOUNT' and self.amount_awarded > 0

    def is_category_specific(self):
        return self.use_category_specific_discounts and bool(self.category_discounts)

    def get_remaining_balance(self):
        if not self.is_budget_based():
            return None
        return self.amount_awarded - self.total_amount_used

    @property
    def remaining_balance(self):
        return self.get_remaining_balance()

    def is_exhausted(self):
        if not self.is_budget_based():
            return False
        remaining = self.get_remaining_balance()
        return remaining is not None and remaining <= Decimal('0.00')

    def has_sufficient_balance(self, amount):
        if not self.is_budget_based():
            return True
        remaining = self.get_remaining_balance()
        return remaining is not None and remaining >= amount

    def get_category_discount_config(self, category_code):
        if not self.use_category_specific_discounts:
            return None
        return self.category_discounts.get(category_code)

    def get_all_covered_categories(self):
        if not self.use_category_specific_discounts:
            return None
        return [code for code, config in self.category_discounts.items() if config.get('type') != 'none']

    def get_discount_display_summary(self):
        if not self.use_category_specific_discounts:
            p = self.scholarship_program
            if p.discount_type == 'PERCENTAGE':
                return {'mode': 'global', 'description': f"{p.discount_percentage}% on all categories"}
            if p.discount_type == 'FULL_WAIVER':
                return {'mode': 'global', 'description': "100% waiver on all categories"}
            return {'mode': 'global', 'description': f"Fixed amount: {p.fixed_discount_amount}"}
        summary = {'mode': 'category_specific', 'categories': {}}
        for code, config in self.category_discounts.items():
            t, v = config.get('type'), config.get('value', 0)
            if t == 'percentage':    summary['categories'][code] = f"{v}% discount"
            elif t == 'fixed_amount': summary['categories'][code] = f"{v:,.0f} per invoice"
            elif t == 'full_waiver':  summary['categories'][code] = "100% waiver"
            elif t == 'none':         summary['categories'][code] = "No discount"
        return summary

    def calculate_discount_for_amount(self, eligible_amount, category_code=None):
        program = self.scholarship_program

        if self.use_category_specific_discounts:
            if category_code:
                config = self.get_category_discount_config(category_code)
                if config:
                    discount = self._calculate_category_discount(eligible_amount, config)
                    if self.is_budget_based():
                        remaining = self.get_remaining_balance()
                        discount = min(discount, remaining) if remaining and remaining > 0 else Decimal('0.00')
                    return discount

        if self.is_policy_based():
            if program.discount_type == 'PERCENTAGE' and program.discount_percentage:
                discount = (eligible_amount * program.discount_percentage / Decimal('100.00')).quantize(Decimal('0.01'))
                if program.maximum_award_amount and discount > program.maximum_award_amount:
                    discount = program.maximum_award_amount
                return discount
            if program.discount_type == 'FULL_WAIVER':
                return eligible_amount

        if self.is_budget_based():
            remaining = self.get_remaining_balance()
            if remaining is None or remaining <= 0:
                return Decimal('0.00')
            return min(remaining, eligible_amount)

        return Decimal('0.00')

    def _calculate_category_discount(self, amount, config):
        t = config.get('type')
        v = Decimal(str(config.get('value', 0)))
        if t == 'percentage':   return (amount * v / Decimal('100.00')).quantize(Decimal('0.01'))
        if t == 'fixed_amount': return min(v, amount)
        if t == 'full_waiver':  return amount
        return Decimal('0.00')

    def apply_discount_to_invoice(self, invoice_amount, category_code=None):
        """
        Calculate and record a discount applied to one invoice.

        IMPORTANT: Callers MUST wrap this in django.db.transaction.atomic()
        since it mutates total_amount_used and saves immediately with no
        transaction protection.
        """
        discount = self.calculate_discount_for_amount(invoice_amount, category_code)
        if self.is_budget_based() and discount > 0:
            self.total_amount_used += discount
            self.save(update_fields=['total_amount_used'])
        return discount

    def is_active_for_date(self, check_date=None):
        d = check_date or get_school_today()
        if self.status != 'ACTIVE':
            return False
        if d < self.start_date:
            return False
        if self.end_date and d > self.end_date:
            return False
        return True

    def check_renewal_eligibility(self):
        if not self.requires_renewal_verification:
            return True, []
        reasons = []
        program = self.scholarship_program
        if program.minimum_gpa and (not self.current_gpa or self.current_gpa < program.minimum_gpa):
            reasons.append(f"GPA below minimum ({self.current_gpa} < {program.minimum_gpa})")
        if program.minimum_attendance_percentage and (not self.current_attendance or self.current_attendance < program.minimum_attendance_percentage):
            reasons.append(f"Attendance below minimum ({self.current_attendance}% < {program.minimum_attendance_percentage}%)")
        return len(reasons) == 0, reasons

    def can_be_applied(self):
        if self.status != 'ACTIVE':
            return False, f"Scholarship is {self.status.lower()}"
        if not self.is_active_for_date():
            return False, "Scholarship is not active for current date"
        if self.is_budget_based() and self.is_exhausted():
            return False, "Scholarship budget is exhausted"
        return True, "OK"

    class Meta:
        verbose_name = "Student Scholarship"
        verbose_name_plural = "Student Scholarships"
        ordering = ['-awarded_date']
        indexes = [
            models.Index(fields=['student', 'status']),
            models.Index(fields=['scholarship_program']),
            models.Index(fields=['status']),
            models.Index(fields=['start_date', 'end_date']),
            models.Index(fields=['use_category_specific_discounts']),
        ]

    def __str__(self):
        if self.is_category_specific():
            return f"{self.student.get_full_name()} — {self.scholarship_program.name} (Category-Specific)"
        if self.is_policy_based():
            return f"{self.student.get_full_name()} — {self.scholarship_program.name} (Policy-Based)"
        if self.is_budget_based():
            remaining = self.get_remaining_balance()
            return f"{self.student.get_full_name()} — {self.scholarship_program.name} (Balance: {remaining:,.0f})"
        return f"{self.student.get_full_name()} — {self.scholarship_program.name}"


class ScholarshipApplicationLog(BaseModel):
    """Immutable audit record of a scholarship being applied to an invoice."""

    scholarship      = models.ForeignKey(StudentScholarship, on_delete=models.CASCADE, related_name='application_logs')
    invoice          = models.ForeignKey(FeeInvoice, on_delete=models.CASCADE, related_name='scholarship_application_logs')
    student          = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='scholarship_application_logs')
    academic_session = models.ForeignKey(AcademicSession, on_delete=models.CASCADE, related_name='scholarship_application_logs', null=True, blank=True)

    amount_applied           = models.DecimalField("Amount Applied",          max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    remaining_balance_after  = models.DecimalField("Remaining Balance After", max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))])
    application_date         = models.DateField("Application Date")
    distribution_method_used = models.CharField("Distribution Method Used",  max_length=20, blank=True)
    applied_by_id            = models.CharField("Applied By ID",              max_length=50, null=True, blank=True)
    notes                    = models.TextField("Notes", blank=True)

    is_reversed     = models.BooleanField("Is Reversed", default=False)
    reversed_date   = models.DateField("Reversed Date", null=True, blank=True)
    reversed_by_id  = models.CharField("Reversed By ID", max_length=50, null=True, blank=True)
    reversal_reason = models.TextField("Reversal Reason", blank=True)

    class Meta:
        verbose_name = "Scholarship Application Log"
        verbose_name_plural = "Scholarship Application Logs"
        ordering = ['-application_date', '-created_at']
        indexes = [
            models.Index(fields=['scholarship', 'invoice']),
            models.Index(fields=['student', 'application_date']),
            models.Index(fields=['is_reversed']),
        ]

    def __str__(self):
        return f"{self.scholarship} applied to {self.invoice.invoice_number}"


# =============================================================================
# DISCOUNTS
# =============================================================================

class DiscountPolicy(BaseModel):
    """
    One record per discount type in the school.

    Single-value decisions (category, value_mode, etc.) live here.
    Multi-row tiers live in DiscountTier.
    Per-student awards live in StudentDiscount.
    """

    CATEGORY_CHOICES = [
        ('SIBLING',        'Sibling / family discount'),
        ('STAFF_CHILD',    'Staff child benefit'),
        ('ALUMNI_FAMILY',  'Alumni family discount'),
        ('ACADEMIC_MERIT', 'Academic merit'),
        ('SPORTS_MERIT',   'Sports merit'),
        ('ARTS_MERIT',     'Arts & talent'),
        ('LEADERSHIP',     'Leadership excellence'),
        ('FINANCIAL_NEED', 'Financial need / bursary'),
        ('EMERGENCY_AID',  'Emergency aid'),
        ('EARLY_PAYMENT',  'Early payment incentive'),
        ('BULK_PAYMENT',   'Full-year / bulk payment'),
        ('NEW_STUDENT',    'New student incentive'),
        ('LOYALTY',        'Long enrollment loyalty'),
        ('RETURNING',      'Re-admitted student'),
        ('ORPHAN',         'Orphan / double-orphan'),
        ('SPECIAL_NEEDS',  'Special educational needs'),
        ('REFUGEE',        'Refugee / displaced'),
        ('COMMUNITY',      'Community / church partner'),
        ('CORPORATE',      'Corporate partner child'),
        ('REFERRAL',       'Referral discount'),
        ('PROMOTIONAL',    'Promotional / campaign'),
        ('CUSTOM',         'Custom / other'),
    ]

    VALUE_MODE_CHOICES = [
        ('FLAT_PERCENTAGE', 'Same % for everyone who qualifies'),
        ('FLAT_FIXED',      'Same fixed amount for everyone'),
        ('FLAT_WAIVER',     '100% waiver on applicable fees'),
        ('TIERED',          'Amount varies by a dimension'),
        ('CATEGORY_MATRIX', 'Different % per fee category'),
    ]

    TIER_DIMENSION_CHOICES = [
        ('SIBLING_RANK',   'Sibling rank'),
        ('YEARS_ENROLLED', 'Years enrolled'),
        ('GPA',            'Academic GPA'),
        ('FAMILY_INCOME',  'Declared family income'),
        ('PAYMENT_DAYS',   'Days before due date'),
        ('INVOICE_AMOUNT', 'Invoice amount band'),
        ('STAFF_GRADE',    'Staff employment grade'),
    ]

    APPLICATION_METHOD_CHOICES = [
        ('AUTO',            'Auto-apply on invoice generation'),
        ('AUTO_NOTIFY',     'Auto-apply and notify bursar'),
        ('MANUAL',          'Bursar applies manually per student'),
        ('NEEDS_APPROVAL',  'Bursar applies, head teacher approves'),
        ('STUDENT_APPLIES', 'Parent applies, then reviewed'),
    ]

    COMBINATION_MODE_CHOICES = [
        ('STANDALONE',             'Cannot combine — replaces all other discounts'),
        ('ADDITIVE',               'Adds on top of other discounts'),
        ('BEST_OF',                'System picks the single highest discount only'),
        ('SEQUENTIAL',             'Applied after others, on net amount'),
        ('SCHOLARSHIP_COMPATIBLE', 'Can stack with scholarship, not other discounts'),
    ]

    name        = models.CharField('Policy name', max_length=200)
    code        = models.CharField('Unique code', max_length=50, unique=True, db_index=True)
    description = models.TextField('Description', blank=True)

    category           = models.CharField(max_length=25, choices=CATEGORY_CHOICES, db_index=True)
    value_mode         = models.CharField(max_length=20, choices=VALUE_MODE_CHOICES)
    tier_dimension     = models.CharField(max_length=20, choices=TIER_DIMENSION_CHOICES, blank=True)
    application_method = models.CharField(max_length=20, choices=APPLICATION_METHOD_CHOICES, default='AUTO')
    combination_mode   = models.CharField(max_length=30, choices=COMBINATION_MODE_CHOICES, default='ADDITIVE')

    auto_apply = models.BooleanField('Auto-apply at invoice generation', default=False)

    flat_percentage   = models.DecimalField('Flat discount %',   max_digits=5,  decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))])
    flat_fixed_amount = models.DecimalField('Flat fixed amount', max_digits=12, decimal_places=2, null=True, blank=True)
    category_matrix   = models.JSONField('Category discount matrix', default=dict, blank=True, help_text='Maps FeesCategory.category_type → discount %. {"TUITION": 50, "BOARDING": 0}')

    applicable_categories = models.ManyToManyField(FeesCategory, blank=True, related_name='discount_policies')

    max_discount_per_student = models.DecimalField('Max discount per student', max_digits=12, decimal_places=2, null=True, blank=True)
    max_beneficiaries        = models.PositiveIntegerField('Max beneficiaries', null=True, blank=True)
    total_budget             = models.DecimalField('Total budget', max_digits=15, decimal_places=2, null=True, blank=True)
    budget_used              = models.DecimalField('Budget used so far', max_digits=15, decimal_places=2, default=Decimal('0.00'))

    valid_from     = models.DateField(null=True, blank=True)
    valid_until    = models.DateField(null=True, blank=True)
    valid_sessions = models.ManyToManyField(AcademicSession, blank=True)

    is_active              = models.BooleanField(default=True, db_index=True)
    requires_annual_review = models.BooleanField(default=False)
    priority               = models.PositiveIntegerField(default=100)

    def clean(self):
        super().clean()
        errors = {}
        if self.value_mode == 'FLAT_PERCENTAGE' and not self.flat_percentage:
            errors['flat_percentage'] = 'Required when value_mode is FLAT_PERCENTAGE.'
        if self.value_mode == 'FLAT_FIXED' and not self.flat_fixed_amount:
            errors['flat_fixed_amount'] = 'Required when value_mode is FLAT_FIXED.'
        if self.value_mode == 'TIERED' and not self.tier_dimension:
            errors['tier_dimension'] = 'Required when value_mode is TIERED.'
        if self.value_mode == 'CATEGORY_MATRIX' and not self.category_matrix:
            errors['category_matrix'] = 'Required when value_mode is CATEGORY_MATRIX.'
        if errors:
            raise ValidationError(errors)

    def is_tiered(self):
        return self.value_mode == 'TIERED'

    def get_flat_discount_for_amount(self, amount):
        if self.value_mode == 'FLAT_PERCENTAGE':
            return (amount * self.flat_percentage / Decimal('100')).quantize(Decimal('0.01'))
        if self.value_mode == 'FLAT_FIXED':
            return min(self.flat_fixed_amount, amount)
        if self.value_mode == 'FLAT_WAIVER':
            return amount
        return Decimal('0.00')

    def get_category_matrix_discount(self, category_type, amount):
        pct = Decimal(str(self.category_matrix.get(category_type, 0)))
        return (amount * pct / Decimal('100')).quantize(Decimal('0.01'))

    def has_budget_available(self, needed=Decimal('0.00')):
        if not self.total_budget:
            return True
        return (self.total_budget - self.budget_used) >= needed

    class Meta:
        verbose_name = 'Discount policy'
        verbose_name_plural = 'Discount policies'
        ordering = ['priority', 'name']
        indexes = [
            models.Index(fields=['category']),
            models.Index(fields=['is_active']),
            models.Index(fields=['auto_apply']),
            models.Index(fields=['priority']),
        ]

    def __str__(self):
        return f'{self.name} ({self.code})'


class DiscountTier(BaseModel):
    """One band within a tiered DiscountPolicy."""

    DISCOUNT_TYPE_CHOICES = [
        ('PERCENTAGE', 'Percentage of applicable fee amount'),
        ('FIXED',      'Fixed amount per invoice'),
        ('WAIVER',     'Full waiver (100%)'),
    ]

    policy         = models.ForeignKey(DiscountPolicy, on_delete=models.CASCADE, related_name='tiers')
    min_value      = models.DecimalField(max_digits=12, decimal_places=2)
    max_value      = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    discount_type  = models.CharField(max_length=10, choices=DISCOUNT_TYPE_CHOICES, default='PERCENTAGE')
    discount_value = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal('0'))])
    label          = models.CharField(max_length=100, blank=True)

    def calculate(self, amount):
        if self.discount_type == 'PERCENTAGE':
            return (amount * self.discount_value / Decimal('100')).quantize(Decimal('0.01'))
        if self.discount_type == 'FIXED':
            return min(self.discount_value, amount)
        if self.discount_type == 'WAIVER':
            return amount
        return Decimal('0.00')

    def matches(self, dimension_value):
        val = Decimal(str(dimension_value))
        if val < self.min_value:
            return False
        if self.max_value is not None and val > self.max_value:
            return False
        return True

    class Meta:
        verbose_name = 'Discount tier'
        ordering = ['policy', 'min_value']
        unique_together = ('policy', 'min_value')

    def __str__(self):
        upper = f'–{self.max_value}' if self.max_value else '+'
        return f'{self.policy.code} | {self.min_value}{upper} → {self.discount_value}'


class StudentDiscount(BaseModel):
    """A specific award of a DiscountPolicy to a specific student.

    OVERRIDE FIELDS
    ---------------
    At most ONE override field may be set at a time — clean() enforces this.

    override_percentage
        Replaces the policy calculation entirely with a flat % for this student.
        Use when you want a different rate than the policy defines globally.

    override_fixed_amount
        Replaces the policy calculation entirely with a fixed amount cap.
        Use when you want a hard ceiling regardless of the policy value_mode.

    override_category_matrix
        Only meaningful when policy.value_mode == 'CATEGORY_MATRIX'.
        Lets you override specific category percentages for this student without
        flattening the whole matrix to a single rate.
        Example: {"TUITION": 40, "BOARDING": 0}
        Categories not listed here fall through to the policy's own matrix.

    override_tier_cap
        Only meaningful when policy.value_mode == 'TIERED'.
        The tier logic still runs normally (sibling rank, years enrolled, etc.)
        but the resulting discount is capped at this value for this student.
        Use instead of override_fixed_amount when you want tier logic to still
        run but be limited for a specific student.
    """

    STATUS_CHOICES = [
        ('ACTIVE',    'Active'),
        ('SUSPENDED', 'Suspended'),
        ('EXPIRED',   'Expired'),
        ('REVOKED',   'Revoked'),
        ('PENDING',   'Pending approval'),
    ]

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='awarded_discounts')
    policy  = models.ForeignKey(DiscountPolicy, on_delete=models.PROTECT, related_name='student_awards')

    status     = models.CharField(max_length=10, choices=STATUS_CHOICES, default='ACTIVE', db_index=True)
    start_date = models.DateField()
    end_date   = models.DateField(null=True, blank=True)

    # ------------------------------------------------------------------
    # OVERRIDE FIELDS — at most one may be set (clean() enforces this)
    # ------------------------------------------------------------------
    override_percentage = models.DecimalField(
        'Override %',
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=(
            'Replaces the policy calculation entirely with this flat % for '
            'this student. Do not set alongside other override fields.'
        ),
    )
    override_fixed_amount = models.DecimalField(
        'Override fixed amount',
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=(
            'Replaces the policy calculation entirely with this fixed amount '
            'cap for this student. Do not set alongside other override fields.'
        ),
    )
    override_category_matrix = models.JSONField(
        'Override category matrix',
        default=dict,
        blank=True,
        null=False,
        help_text=(
            'Per-category discount overrides for this student. '
            'Maps FeesCategory.category_type → discount %. '
            'Example: {"TUITION": 40, "BOARDING": 0}. '
            'Only used when policy.value_mode is CATEGORY_MATRIX. '
            'Categories not listed fall through to the policy matrix. '
            'Do not set alongside other override fields.'
        ),
    )
    override_tier_cap = models.DecimalField(
        'Override tier cap',
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=(
            'Caps the tier-calculated discount at this value for this student. '
            'Tier logic still runs normally — only the result is capped. '
            'Only meaningful when policy.value_mode is TIERED. '
            'Do not set alongside other override fields.'
        ),
    )

    awarded_by_id     = models.CharField(max_length=50, null=True, blank=True)
    awarded_date      = models.DateField(null=True, blank=True)
    approved_by_id    = models.CharField(max_length=50, null=True, blank=True)
    notes             = models.TextField(blank=True)
    suspension_reason = models.TextField(blank=True)
    revocation_reason = models.TextField(blank=True)

    dimension_context = models.JSONField(
        default=dict,
        blank=True,
        help_text='Values used for tier dimension lookup. e.g. {"sibling_rank": 3}',
    )

    # ------------------------------------------------------------------
    # VALIDATION
    # ------------------------------------------------------------------

    def clean(self):
        super().clean()
        errors = {}

        # ------------------------------------------------------------
        # Normalize category matrix (treat empty dict as "not set")
        # ------------------------------------------------------------
        category_matrix_set = bool(self.override_category_matrix)

        # ------------------------------------------------------------
        # Only one override field may be set at a time
        # ------------------------------------------------------------
        override_fields = {
            "override_percentage": self.override_percentage,
            "override_fixed_amount": self.override_fixed_amount,
            "override_category_matrix": self.override_category_matrix if category_matrix_set else None,
            "override_tier_cap": self.override_tier_cap,
        }

        override_fields_set = [
            name for name, value in override_fields.items()
            if value not in (None, "", {}, Decimal("0"))
        ]

        if len(override_fields_set) > 1:
            msg = (
                "Only one override field may be set at a time. "
                f"You have set: {', '.join(override_fields_set)}."
            )
            for name in override_fields_set:
                errors[name] = msg

        # ------------------------------------------------------------
        # CATEGORY MATRIX validation
        # ------------------------------------------------------------
        if category_matrix_set and self.policy_id:
            if self.policy.value_mode != "CATEGORY_MATRIX":
                errors["override_category_matrix"] = (
                    "override_category_matrix can only be used when "
                    "policy.value_mode is CATEGORY_MATRIX."
                )

        # ------------------------------------------------------------
        # TIER CAP validation
        # ------------------------------------------------------------
        if self.override_tier_cap is not None and self.policy_id:
            if self.policy.value_mode != "TIERED":
                errors["override_tier_cap"] = (
                    "override_tier_cap can only be used when "
                    "policy.value_mode is TIERED."
                )
            elif self.override_tier_cap <= Decimal("0.00"):
                errors["override_tier_cap"] = (
                    "override_tier_cap must be greater than zero."
                )

        # ------------------------------------------------------------
        # Date validation
        # ------------------------------------------------------------
        if self.start_date and self.end_date:
            if self.end_date < self.start_date:
                errors["end_date"] = "End date cannot be before start date."

        # ------------------------------------------------------------
        # Raise errors
        # ------------------------------------------------------------
        
        if errors:
            raise ValidationError(errors)

    # ------------------------------------------------------------------
    # STATE
    # ------------------------------------------------------------------

    def is_active_for_date(self, check_date=None):
        d = check_date or get_school_today()
        if self.status != 'ACTIVE':
            return False
        if d < self.start_date:
            return False
        if self.end_date and d > self.end_date:
            return False
        return True

    # ------------------------------------------------------------------
    # DISCOUNT RESOLUTION
    # ------------------------------------------------------------------

    def resolve_discount(self, fee_amount, category_type=None, dimension_value=None):
        """Return the discount amount to apply to one fee line item.

        Override precedence (clean() ensures at most one override is set):

          1. override_category_matrix  — per-category % for CATEGORY_MATRIX
                                         policies; falls through to policy matrix
                                         for categories not listed in the override.
          2. override_percentage       — flat % replaces policy calculation entirely.
          3. override_fixed_amount     — fixed cap replaces policy calculation entirely.
          4. Policy logic              — TIERED → CATEGORY_MATRIX → flat.
             override_tier_cap         — applied after tier logic as a ceiling.
        """
        policy = self.policy

        # 1. Category matrix override — only for CATEGORY_MATRIX policies
        if self.override_category_matrix and policy.value_mode == 'CATEGORY_MATRIX':
            if category_type and category_type in self.override_category_matrix:
                pct = Decimal(str(self.override_category_matrix[category_type]))
                return (fee_amount * pct / Decimal('100')).quantize(Decimal('0.01'))
            # category not in override — fall through to policy matrix below

        # 2. Flat percentage override
        if self.override_percentage is not None:
            return (
                fee_amount * self.override_percentage / Decimal('100')
            ).quantize(Decimal('0.01'))

        # 3. Fixed amount override
        if self.override_fixed_amount is not None:
            return min(self.override_fixed_amount, fee_amount)

        # 4. Policy logic
        if policy.value_mode == 'TIERED':
            dim_val = dimension_value or self.dimension_context.get(
                policy.tier_dimension.lower()
            )
            if dim_val is None:
                return Decimal('0.00')
            tier = (
                policy.tiers
                .filter(min_value__lte=dim_val)
                .filter(
                    models.Q(max_value__gte=dim_val) |
                    models.Q(max_value__isnull=True)
                )
                .order_by('-min_value')
                .first()
            )
            discount = tier.calculate(fee_amount) if tier else Decimal('0.00')

            # Cap tier result for this student if override_tier_cap is set
            if self.override_tier_cap is not None:
                discount = min(discount, self.override_tier_cap)

            return discount

        if policy.value_mode == 'CATEGORY_MATRIX' and category_type:
            return policy.get_category_matrix_discount(category_type, fee_amount)

        return policy.get_flat_discount_for_amount(fee_amount)

    # ------------------------------------------------------------------
    # META
    # ------------------------------------------------------------------

    class Meta:
        verbose_name = 'Student discount'
        ordering = ['-start_date']
        indexes = [
            models.Index(fields=['student', 'status']),
            models.Index(fields=['policy', 'status']),
        ]

    def __str__(self):
        return f'{self.student} — {self.policy.name} ({self.status})'


class DiscountApplication(BaseModel):
    """
    Immutable audit record: which discount reduced which invoice (line),
    by how much. Reversed by setting is_reversed = True.
    """

    student_discount = models.ForeignKey(StudentDiscount, on_delete=models.PROTECT, related_name='applications')
    invoice          = models.ForeignKey(FeeInvoice,      on_delete=models.CASCADE,  related_name='discount_applications')
    invoice_item     = models.ForeignKey(
        FeeInvoiceItem, on_delete=models.CASCADE,
        null=True, blank=True, related_name='discount_applications',
        help_text='Specific line item discounted (null = applied at invoice level)',
    )
    amount_discounted = models.DecimalField(
        "Amount Discounted",
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
    )
    applied_by_id  = models.CharField(max_length=50, null=True, blank=True)
    notes          = models.TextField(blank=True)

    is_reversed    = models.BooleanField(default=False, db_index=True)
    reversed_date  = models.DateField(null=True, blank=True)
    reversed_by_id = models.CharField(max_length=50, null=True, blank=True)
    reversal_reason = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Discount application'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['invoice', 'is_reversed']),
            models.Index(fields=['student_discount']),
        ]

    def __str__(self):
        return f'{self.student_discount.policy.code} → {self.invoice.invoice_number} ({self.amount_discounted})'


# =============================================================================
# DISCOUNT ENGINE
# =============================================================================

class DiscountEngine:
    """
    Resolves and applies all eligible auto-apply discounts for a student's invoice.

    Usage:
        engine = DiscountEngine(student, invoice, academic_session)
        engine.apply_all()

    STACKING ORDER:
        Scholarships are applied first (by UnifiedStudentInvoiceGenerator).
        DiscountEngine runs second, calculating discount amounts against
        item.final_amount — the post-scholarship net — so that the discount
        percentage is taken off what the student actually still owes rather
        than the original billed amount.

        Example: 1,000,000 item with 50% scholarship → final_amount = 500,000.
        A 10% sibling discount then gives 50,000 (10% of 500,000), not 100,000
        (10% of the original 1,000,000).

    DOUBLE-APPLICATION GUARD:
        apply_all() checks invoice.auto_discounts_applied at entry and returns
        immediately if True.  The flag is set to True inside apply_all() itself
        before returning.  Callers must NOT pre-set this flag — doing so causes
        apply_all() to exit with no discounts applied.
    """

    def __init__(self, student, invoice, academic_session):
        self.student          = student
        self.invoice          = invoice
        self.academic_session = academic_session

    def get_active_discounts(self):
        today = get_school_today()
        qs = StudentDiscount.objects.filter(
            student=self.student, status='ACTIVE', start_date__lte=today,
        ).filter(
            models.Q(end_date__isnull=True) | models.Q(end_date__gte=today)
        ).select_related('policy').prefetch_related('policy__tiers', 'policy__applicable_categories')

        valid = []
        for sd in qs:
            if not sd.policy.auto_apply:
                continue
            sessions = sd.policy.valid_sessions.all()
            if sessions.exists() and not sessions.filter(pk=self.academic_session.pk).exists():
                continue
            if not sd.policy.has_budget_available():
                continue
            valid.append(sd)
        return valid

    def apply_all(self):
        if self.invoice.auto_discounts_applied:
            return
        active_discounts = self.get_active_discounts()
        if not active_discounts:
            return
        active_discounts.sort(key=lambda sd: sd.policy.priority)
        from django.db import transaction as db_transaction
        with db_transaction.atomic():
            for item in self.invoice.items.all():
                self._apply_to_item(item, active_discounts)
            self.invoice.auto_discounts_applied = True
            self.invoice.recalculate_totals()

    def _apply_to_item(self, item, active_discounts):
        category_type = item.fee_category.category_type

        # FIX: use item.final_amount (post-scholarship net) rather than
        # item.amount (original billed amount) so that discount percentages
        # are applied to what the student still owes after scholarships,
        # not the pre-scholarship gross.
        running_amount = item.final_amount
        candidates     = []

        for sd in active_discounts:
            policy = sd.policy
            scoped_cats = policy.applicable_categories.all()
            if scoped_cats.exists() and not scoped_cats.filter(pk=item.fee_category.pk).exists():
                continue
            discount_amount = sd.resolve_discount(
                fee_amount=running_amount,
                category_type=category_type,
                dimension_value=self._get_dimension_value(sd),
            )
            if discount_amount > Decimal('0.00'):
                candidates.append((sd, discount_amount))

        if not candidates:
            return

        to_apply = self._resolve_combination(candidates)

        for sd, discount_amount in to_apply:
            if sd.policy.max_discount_per_student:
                already_given = DiscountApplication.objects.filter(
                    student_discount__student=self.student,
                    student_discount__policy=sd.policy,
                    is_reversed=False,
                ).aggregate(total=models.Sum('amount_discounted'))['total'] or Decimal('0.00')
                remaining_cap = sd.policy.max_discount_per_student - already_given
                discount_amount = min(discount_amount, remaining_cap)

            if discount_amount <= Decimal('0.00'):
                continue

            item.discount_amount          += discount_amount
            item.total_discount_amount    += discount_amount
            item.final_amount             -= discount_amount
            item.has_regular_discount      = True
            item.amount_in_school_currency = (
                item.final_amount * item.exchange_rate
            ).quantize(Decimal('0.01'))
            item.save(update_fields=[
                'discount_amount', 'total_discount_amount', 'final_amount',
                'has_regular_discount', 'amount_in_school_currency',
            ])

            DiscountApplication.objects.create(
                student_discount=sd, invoice=self.invoice, invoice_item=item,
                amount_discounted=discount_amount,
            )

            if sd.policy.total_budget:
                DiscountPolicy.objects.filter(pk=sd.policy.pk).update(
                    budget_used=models.F('budget_used') + discount_amount
                )

    def _resolve_combination(self, candidates):
        if not candidates:
            return []
        modes = {sd.policy.combination_mode for sd, _ in candidates}
        if 'STANDALONE' in modes:
            return [max(candidates, key=lambda x: x[1])]
        if all(sd.policy.combination_mode == 'BEST_OF' for sd, _ in candidates):
            return [max(candidates, key=lambda x: x[1])]
        return candidates

    def _get_dimension_value(self, student_discount):
        policy = student_discount.policy
        if not policy.tier_dimension:
            return None
        ctx = student_discount.dimension_context
        dim = policy.tier_dimension
        if dim == 'SIBLING_RANK':    return ctx.get('sibling_rank')    or self._get_sibling_rank()
        if dim == 'YEARS_ENROLLED':  return ctx.get('years_enrolled')  or self._get_years_enrolled()
        if dim == 'GPA':             return ctx.get('gpa')
        if dim == 'FAMILY_INCOME':   return ctx.get('family_income')
        if dim == 'PAYMENT_DAYS':    return ctx.get('payment_days')
        if dim == 'STAFF_GRADE':     return ctx.get('staff_grade')
        if dim == 'INVOICE_AMOUNT':  return self.invoice.total_amount
        return None

    def _get_sibling_rank(self):
        """
        Delegates to Student.get_sibling_rank() — logic lives on the model.
        FIX: logic extracted to students/models.py::Student.get_sibling_rank()
        """
        return self.student.get_sibling_rank()

    def _get_years_enrolled(self):
        """
        Delegates to Student.get_years_enrolled() — logic lives on the model.
        FIX: logic extracted to students/models.py::Student.get_years_enrolled()
        """
        return self.student.get_years_enrolled()
        
    def get_preview_discounts(self, base_amount, preview_items=None):
        active_discounts = self.get_active_discounts()
        if not active_discounts:
            return []

        active_discounts.sort(key=lambda sd: sd.policy.priority)
        by_policy = {}

        if preview_items:
            # ✅ FULLY mirror _apply_to_item (BUT in-memory only)
            for item in preview_items:
                running_amount = item.final_amount
                candidates     = []

                for sd in active_discounts:
                    policy = sd.policy

                    scoped_cats = policy.applicable_categories.all()
                    if (
                        scoped_cats.exists() and
                        not scoped_cats.filter(pk=item.fee_category.pk).exists()
                    ):
                        continue

                    disc = sd.resolve_discount(
                        fee_amount      = running_amount,
                        category_type   = item.fee_category.category_type,
                        dimension_value = self._get_dimension_value_preview(sd, base_amount),
                    )

                    if disc > Decimal('0.00'):
                        candidates.append((sd, disc))

                if not candidates:
                    continue

                to_apply = self._resolve_combination(candidates)

                for sd, disc in to_apply:
                    # ✅ Apply per-student cap (same as real engine)
                    if sd.policy.max_discount_per_student:
                        already_given = DiscountApplication.objects.filter(
                            student_discount__student=self.student,
                            student_discount__policy=sd.policy,
                            is_reversed=False,
                        ).aggregate(total=models.Sum('amount_discounted'))['total'] or Decimal('0.00')

                        remaining_cap = sd.policy.max_discount_per_student - already_given
                        disc = min(disc, remaining_cap)

                    if disc <= Decimal('0.00'):
                        continue

                    # ✅ APPLY TO ITEM (THIS WAS MISSING)
                    item.discount_amount += disc
                    item.final_amount    -= disc

                    # ✅ Track per policy
                    pk = sd.policy.pk
                    if pk not in by_policy:
                        by_policy[pk] = {
                            'name':  sd.policy.name,
                            'code':  sd.policy.code,
                            'total': Decimal('0.00'),
                        }

                    by_policy[pk]['total'] += disc

        else:
            # fallback (unchanged)
            candidates = []

            for sd in active_discounts:
                disc = sd.resolve_discount(
                    fee_amount      = base_amount,
                    category_type   = None,
                    dimension_value = self._get_dimension_value_preview(sd, base_amount),
                )
                if disc > Decimal('0.00'):
                    candidates.append((sd, disc))

            for sd, disc in self._resolve_combination(candidates):
                pk = sd.policy.pk
                by_policy[pk] = {
                    'name':  sd.policy.name,
                    'code':  sd.policy.code,
                    'total': disc,
                }

        return sorted(by_policy.values(), key=lambda x: x['name'])
 
    def _get_dimension_value_preview(self, student_discount, base_amount):
        """
        Like _get_dimension_value() but works without a real invoice object.
 
        Substitutes base_amount for the INVOICE_AMOUNT dimension since
        there is no FeeInvoice instance during preview.  All other dimensions
        are resolved identically to the live path.
        """
        policy = student_discount.policy
        if not policy.tier_dimension:
            return None
        ctx = student_discount.dimension_context
        dim = policy.tier_dimension
        if dim == 'SIBLING_RANK':   return ctx.get('sibling_rank')   or self._get_sibling_rank()
        if dim == 'YEARS_ENROLLED': return ctx.get('years_enrolled') or self._get_years_enrolled()
        if dim == 'GPA':            return ctx.get('gpa')
        if dim == 'FAMILY_INCOME':  return ctx.get('family_income')
        if dim == 'PAYMENT_DAYS':   return ctx.get('payment_days')
        if dim == 'STAFF_GRADE':    return ctx.get('staff_grade')
        if dim == 'INVOICE_AMOUNT': return base_amount   # substitute for self.invoice.total_amount
        return None