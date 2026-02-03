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
from decimal import Decimal, InvalidOperation
from django.db.models import F
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
    """
    Student financial account for tracking balances and transactions.
    
    Architecture:
    - This is the SUBSIDIARY LEDGER for individual student tracking
    - All balances are calculated dynamically from AccountTransaction records
    - No redundant summary fields (single source of truth)
    - Links to General Ledger via invoice/payment journal entries
    
    Balance Calculation (Simplified):
    - Transaction amounts are SIGNED:
      * INVOICE/DEBIT: Negative (student owes more)
      * PAYMENT/DISCOUNT: Positive (reduces what student owes)
      * REFUND: Negative (student owes more after refund)
    
    Balance = Sum of all signed transaction amounts
    
    Interpretation:
    - Negative balance = Student owes money (debit balance in accounting)
    - Positive balance = Student has credit (overpayment)
    - Zero balance = Account is settled
    """
    
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
    # CREDIT LIMITS AND SETTINGS
    # -------------------------------------------------------------------------
    
    credit_limit = models.DecimalField(
        "Credit Limit",
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Maximum negative balance allowed (how much student can owe)"
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
    
    last_transaction_date = models.DateTimeField(
        "Last Transaction Date", 
        null=True, 
        blank=True,
        help_text="When the last transaction was recorded on this account"
    )
    
    last_payment_date = models.DateTimeField(
        "Last Payment Date", 
        null=True, 
        blank=True,
        help_text="When the last payment was received"
    )
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Student Account"
        verbose_name_plural = "Student Accounts"
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['student']),
            models.Index(fields=['last_transaction_date']),
            models.Index(fields=['last_payment_date']),
        ]
    
    # -------------------------------------------------------------------------
    # BALANCE CALCULATION METHODS
    # -------------------------------------------------------------------------
    
    def get_current_balance(self):
        """
        Calculate current balance from all transactions.
        
        This method simply sums all transaction amounts with their signs.
        Transaction amounts are signed when created:
        - INVOICE/DEBIT: Negative (increases what student owes)
        - PAYMENT: Positive (decreases what student owes)
        - DISCOUNT: Positive (decreases what student owes)
        - REFUND: Negative (increases what student owes after refund issued)
        
        Returns:
            Decimal: Current balance
                Negative = Student owes money (debit balance)
                Positive = Student has credit (overpayment)
                Zero = Account is settled
        
        Examples:
            >>> account = StudentAccount.objects.get(student=student)
            >>> balance = account.get_current_balance()
            >>> if balance < 0:
            >>>     print(f"Student owes: {abs(balance)}")
            >>> elif balance > 0:
            >>>     print(f"Student has credit: {balance}")
            >>> else:
            >>>     print("Account is settled")
        
        Transaction Examples:
            Invoice 100,000:  amount = -100,000
            Payment  50,000:  amount = +50,000
            Balance:          -50,000 (student owes 50,000)
            
            Invoice  100,000: amount = -100,000
            Payment  120,000: amount = +120,000
            Balance:          +20,000 (student has 20,000 credit)
            Refund    20,000: amount = -20,000
            Balance:           0 (settled)
        """
        from django.db.models import Sum
        
        total = self.transactions.aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')
        
        return total
    
    def get_total_charges(self):
        """
        Calculate total charges (invoices + debits) ever made to this account.
        
        Note: Returns absolute value (positive number) for display purposes.
        
        Returns:
            Decimal: Total amount charged to student (always positive)
        
        Example:
            >>> total = account.get_total_charges()
            >>> print(f"Total fees charged: UGX {total:,.2f}")
        """
        from django.db.models import Sum
        
        # Charges are stored as negative, so we take absolute value
        charges = self.transactions.filter(
            transaction_type__in=['INVOICE', 'DEBIT']
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        return abs(charges)
    
    def get_total_payments(self):
        """
        Calculate total payments received from this student.
        
        Returns:
            Decimal: Total amount paid by student (always positive)
        
        Example:
            >>> total = account.get_total_payments()
            >>> print(f"Total payments received: UGX {total:,.2f}")
        """
        from django.db.models import Sum
        
        # Payments are stored as positive
        payments = self.transactions.filter(
            transaction_type='PAYMENT'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        return payments
    
    def get_total_discounts(self):
        """
        Calculate total discounts applied to this account.
        
        Returns:
            Decimal: Total discount amount (always positive)
        
        Example:
            >>> total = account.get_total_discounts()
            >>> print(f"Total discounts: UGX {total:,.2f}")
        """
        from django.db.models import Sum
        
        # Discounts are stored as positive
        discounts = self.transactions.filter(
            transaction_type='DISCOUNT'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        return discounts
    
    def get_total_refunds(self):
        """
        Calculate total refunds issued to this student.
        
        Note: Returns absolute value (positive number) for display purposes.
        
        Returns:
            Decimal: Total refund amount (always positive)
        
        Example:
            >>> total = account.get_total_refunds()
            >>> print(f"Total refunds issued: UGX {total:,.2f}")
        """
        from django.db.models import Sum
        
        # Refunds are stored as negative, so we take absolute value
        refunds = self.transactions.filter(
            transaction_type='REFUND'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        return abs(refunds)
    
    # -------------------------------------------------------------------------
    # BALANCE ANALYSIS METHODS
    # -------------------------------------------------------------------------
    
    def has_outstanding_balance(self):
        """
        Check if student has an outstanding balance (owes money).
        
        Returns:
            bool: True if student owes money, False otherwise
        
        Example:
            >>> if account.has_outstanding_balance():
            >>>     print("Send reminder to parent")
        """
        return self.get_current_balance() < 0
    
    def has_credit_balance(self):
        """
        Check if student has a credit balance (overpaid).
        
        Returns:
            bool: True if student has overpaid, False otherwise
        
        Example:
            >>> if account.has_credit_balance():
            >>>     print("Offer refund or apply to next term")
        """
        return self.get_current_balance() > 0
    
    def is_account_settled(self):
        """
        Check if account is fully settled (balance is zero).
        
        Returns:
            bool: True if balance is zero, False otherwise
        
        Example:
            >>> if account.is_account_settled():
            >>>     print("Account is up to date")
        """
        balance = self.get_current_balance()
        return abs(balance) < Decimal('0.01')  # Allow for rounding
    
    def get_outstanding_amount(self):
        """
        Get the amount student owes (always returns positive number or zero).
        
        This is a convenience method that converts negative balance to positive.
        
        Returns:
            Decimal: Amount owed (0 if no outstanding balance)
        
        Example:
            >>> amount = account.get_outstanding_amount()
            >>> print(f"Student owes: UGX {amount:,.2f}")
        """
        balance = self.get_current_balance()
        return abs(balance) if balance < 0 else Decimal('0.00')
    
    def get_credit_amount(self):
        """
        Get the credit amount available to student (always positive or zero).
        
        Returns:
            Decimal: Credit amount (0 if no credit balance)
        
        Example:
            >>> credit = account.get_credit_amount()
            >>> if credit > 0:
            >>>     print(f"Available credit: UGX {credit:,.2f}")
        """
        balance = self.get_current_balance()
        return balance if balance > 0 else Decimal('0.00')
    
    def is_over_credit_limit(self):
        """
        Check if current outstanding balance exceeds credit limit.
        
        Returns:
            bool: True if over limit, False otherwise
        
        Example:
            >>> if account.is_over_credit_limit():
            >>>     print("Student has exceeded credit limit")
            >>>     # Block new charges or send alert
        """
        if self.credit_limit <= 0:
            return False  # No limit set
        
        outstanding = self.get_outstanding_amount()
        return outstanding > self.credit_limit
    
    # -------------------------------------------------------------------------
    # TRANSACTION BREAKDOWN METHODS
    # -------------------------------------------------------------------------
    
    def get_balance_by_fee_type(self):
        """
        Get breakdown of outstanding balance by fee type.
        
        Returns:
            QuerySet: Annotated with fee_type and balance_owed
        
        Example:
            >>> breakdown = account.get_balance_by_fee_type()
            >>> for item in breakdown:
            >>>     print(f"{item['fee_type']}: {item['balance_owed']}")
        """
        from django.db.models import Sum, F, Q, Case, When, DecimalField
        
        # Get all invoices with their balances
        invoices_breakdown = self.transactions.filter(
            transaction_type='INVOICE',
            invoice__isnull=False
        ).values('invoice').annotate(
            charged=Sum('amount'),  # This will be negative
            paid=Sum(
                Case(
                    When(
                        invoice__payments__status='COMPLETED',
                        then=F('invoice__payments__amount')
                    ),
                    default=Decimal('0.00'),
                    output_field=DecimalField()
                )
            )
        ).annotate(
            # Balance = charged (negative) + paid (positive)
            balance=F('charged') + F('paid')
        )
        
        return invoices_breakdown
    
    def get_balance_by_academic_session(self):
        """
        Get breakdown of balance by academic session.
        
        Returns:
            QuerySet: Balance per academic session
        
        Example:
            >>> sessions = account.get_balance_by_academic_session()
            >>> for session in sessions:
            >>>     print(f"{session['academic_session__name']}: {session['balance']}")
        """
        from django.db.models import Sum, Q
        
        return self.transactions.values(
            'academic_session__name'
        ).annotate(
            # Simply sum all transaction amounts per session
            balance=Sum('amount')
        ).order_by('academic_session__name')
    
    def get_detailed_balance_by_session(self):
        """
        Get detailed breakdown by academic session showing charges, payments, etc.
        
        Returns:
            QuerySet: Detailed breakdown per academic session
        
        Example:
            >>> sessions = account.get_detailed_balance_by_session()
            >>> for session in sessions:
            >>>     print(f"{session['academic_session__name']}:")
            >>>     print(f"  Charged: {session['total_charges']}")
            >>>     print(f"  Paid: {session['total_payments']}")
            >>>     print(f"  Balance: {session['balance']}")
        """
        from django.db.models import Sum, Q, Case, When
        
        return self.transactions.values(
            'academic_session__name'
        ).annotate(
            total_charges=Sum(
                Case(
                    When(transaction_type__in=['INVOICE', 'DEBIT'], then='amount'),
                    default=Decimal('0.00')
                )
            ),
            total_payments=Sum(
                Case(
                    When(transaction_type='PAYMENT', then='amount'),
                    default=Decimal('0.00')
                )
            ),
            total_discounts=Sum(
                Case(
                    When(transaction_type='DISCOUNT', then='amount'),
                    default=Decimal('0.00')
                )
            ),
            total_refunds=Sum(
                Case(
                    When(transaction_type='REFUND', then='amount'),
                    default=Decimal('0.00')
                )
            ),
            # Balance is just the sum of all amounts
            balance=Sum('amount')
        ).order_by('academic_session__name')
    
    # -------------------------------------------------------------------------
    # ACCOUNT HEALTH CHECKS
    # -------------------------------------------------------------------------
    
    def get_account_summary(self):
        """
        Get comprehensive account summary.
        
        Returns:
            dict: Complete account summary with all key metrics
        
        Example:
            >>> summary = account.get_account_summary()
            >>> print(f"Status: {summary['status']}")
            >>> print(f"Balance: {summary['current_balance']}")
            >>> print(f"Total Charged: {summary['total_charges']}")
        """
        balance = self.get_current_balance()
        
        return {
            'student': self.student,
            'status': self.status,
            'current_balance': balance,
            'outstanding_amount': self.get_outstanding_amount(),
            'credit_amount': self.get_credit_amount(),
            'total_charges': self.get_total_charges(),
            'total_payments': self.get_total_payments(),
            'total_discounts': self.get_total_discounts(),
            'total_refunds': self.get_total_refunds(),
            'is_settled': self.is_account_settled(),
            'has_outstanding': self.has_outstanding_balance(),
            'has_credit': self.has_credit_balance(),
            'credit_limit': self.credit_limit,
            'over_limit': self.is_over_credit_limit(),
            'last_transaction': self.last_transaction_date,
            'last_payment': self.last_payment_date,
        }
    
    def get_payment_history_summary(self, limit=10):
        """
        Get recent payment history.
        
        Args:
            limit: Number of recent transactions to return
        
        Returns:
            QuerySet: Recent payment transactions
        
        Example:
            >>> history = account.get_payment_history_summary(5)
            >>> for transaction in history:
            >>>     print(f"{transaction.created_at}: {transaction.amount}")
        """
        return self.transactions.filter(
            transaction_type='PAYMENT'
        ).order_by('-created_at')[:limit]
    
    def get_transaction_history(self, limit=None):
        """
        Get complete transaction history.
        
        Args:
            limit: Optional limit on number of transactions to return
        
        Returns:
            QuerySet: All transactions ordered by date (newest first)
        
        Example:
            >>> history = account.get_transaction_history(20)
            >>> for transaction in history:
            >>>     print(f"{transaction.created_at}: {transaction.get_transaction_type_display()} - {transaction.amount}")
        """
        qs = self.transactions.order_by('-created_at')
        if limit:
            qs = qs[:limit]
        return qs
    
    # -------------------------------------------------------------------------
    # VALIDATION METHODS
    # -------------------------------------------------------------------------
    
    def can_charge_amount(self, amount):
        """
        Check if an amount can be charged without exceeding credit limit.
        
        Args:
            amount: Amount to be charged (positive number)
        
        Returns:
            tuple: (can_charge: bool, reason: str)
        
        Example:
            >>> can_charge, reason = account.can_charge_amount(50000)
            >>> if not can_charge:
            >>>     print(f"Cannot charge: {reason}")
        """
        if self.status == 'FROZEN':
            return False, "Account is frozen"
        
        if self.status == 'CLOSED':
            return False, "Account is closed"
        
        if self.status == 'SUSPENDED':
            return False, "Account is suspended"
        
        # Check credit limit
        if self.credit_limit > 0:
            current_outstanding = self.get_outstanding_amount()
            new_outstanding = current_outstanding + Decimal(str(amount))
            
            if new_outstanding > self.credit_limit:
                excess = new_outstanding - self.credit_limit
                return False, f"Would exceed credit limit by {excess:,.2f}"
        
        return True, "OK"
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        balance = self.get_current_balance()
        if balance < 0:
            return f"{self.student.get_full_name()} - Owes: {abs(balance):,.2f}"
        elif balance > 0:
            return f"{self.student.get_full_name()} - Credit: {balance:,.2f}"
        else:
            return f"{self.student.get_full_name()} - Settled"
    
    # -------------------------------------------------------------------------
    # PROPERTY SHORTCUTS (for template/admin convenience)
    # -------------------------------------------------------------------------
    
    @property
    def current_balance(self):
        """Property shortcut for get_current_balance() - use in templates"""
        return self.get_current_balance()
    
    @property
    def outstanding_amount(self):
        """Property shortcut for get_outstanding_amount() - use in templates"""
        return self.get_outstanding_amount()
    
    @property
    def credit_balance(self):
        """Property shortcut for get_credit_amount() - use in templates"""
        return self.get_credit_amount()


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
    """
    Fee structure supporting multiple academic levels and sessions.
    
    ARCHITECTURE:
    - applicable_sessions: Which academic sessions this covers (WHAT)
    - billing_periods: When to generate invoices (WHEN)
    - This separation allows flexibility in billing schedules
    
    Examples:
    1. Term fees billed once at start: 
       - applicable_sessions=[Term1]
       - billing_periods=[FiscalPeriod_Term1]
    
    2. Term fees split into 2 payments:
       - applicable_sessions=[Term1]
       - billing_periods=[FiscalPeriod_Jan, FiscalPeriod_Feb]
    
    3. Annual fees billed once but applicable to all terms:
       - applicable_sessions=[Term1, Term2, Term3]
       - billing_periods=[FiscalPeriod_Jan]
    """
    
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
    
    BILLING_FREQUENCY_CHOICES = [
        ('ONCE', 'Bill Once (Full Amount)'),
        ('PER_PERIOD', 'Bill Per Fiscal Period'),
        ('SPLIT_CUSTOM', 'Custom Split Across Periods'),
        ('ON_ENROLLMENT', 'Bill on Student Enrollment'),
    ]
    
    # -------------------------------------------------------------------------
    # ACADEMIC CONTEXT (WHAT fees apply to which students)
    # -------------------------------------------------------------------------
    
    academic_year = models.ForeignKey(
        FiscalYear,
        on_delete=models.PROTECT,
        related_name='fee_structures',
        null=True,  # ✅ ADD THIS
        blank=True,  # ✅ ADD THIS
        help_text="Academic/Fiscal year this structure belongs to"
    )
    
    applicable_sessions = models.ManyToManyField(
        AcademicSession,
        verbose_name="Applicable Academic Sessions",
        related_name='fee_structures',
        help_text="Which academic sessions this fee structure covers (e.g., Term 1, Term 2)"
    )
    
    academic_levels = models.ManyToManyField(
        AcademicLevel,
        verbose_name="Academic Levels",
        related_name='fee_structures',
        help_text="Academic levels this structure applies to (e.g., Form 1, Form 2)"
    )
    
    applicable_classes = models.ManyToManyField(
        Class,
        verbose_name="Applicable Classes",
        blank=True,
        help_text="Leave empty to apply to ALL classes in selected academic levels"
    )
    
    # -------------------------------------------------------------------------
    # BILLING SCHEDULE (WHEN to generate invoices)
    # -------------------------------------------------------------------------
    
    billing_periods = models.ManyToManyField(
        FiscalPeriod,
        verbose_name="Billing Periods",
        through='FeesStructureBillingSplit',
        related_name='fee_structures',
        help_text="When to generate invoices for this structure"
    )
    
    billing_frequency = models.CharField(
        "Billing Frequency",
        max_length=20,
        choices=BILLING_FREQUENCY_CHOICES,
        default='ONCE',
        help_text="How to split billing across fiscal periods"
    )
    
    # -------------------------------------------------------------------------
    # BASIC INFORMATION
    # -------------------------------------------------------------------------
    
    name = models.CharField(
        "Structure Name", 
        max_length=100, 
        help_text="Name of this fee structure (e.g., 'Secondary Day Scholar - Term 1 2024')"
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
        help_text="Lower number = higher priority when multiple structures match"
    )
    
    # -------------------------------------------------------------------------
    # STATUS AND VALIDITY
    # -------------------------------------------------------------------------
    
    is_active = models.BooleanField("Active", default=True, db_index=True)
    effective_date = models.DateField("Effective Date", default=timezone.now, db_index=True)
    expiry_date = models.DateField("Expiry Date", null=True, blank=True, db_index=True)
    
    # -------------------------------------------------------------------------
    # HELPER METHODS
    # -------------------------------------------------------------------------
    
    def get_total_amount(self):
        """Calculate total amount for this fee structure"""
        from django.db.models import Sum
        total = self.items.aggregate(total=Sum('amount'))['total']
        return total or Decimal('0.00')
    
    def get_billing_schedule(self):
        """
        Get billing schedule with amounts per period.
        
        Returns:
            list: [{period: FiscalPeriod, amount: Decimal, percentage: Decimal}]
        """
        splits = self.billing_splits.select_related('fiscal_period').order_by('fiscal_period__period_number')
        
        if not splits.exists():
            # No custom splits - bill full amount in first period
            first_period = self.billing_periods.order_by('period_number').first()
            if first_period:
                return [{
                    'period': first_period,
                    'amount': self.get_total_amount(),
                    'percentage': Decimal('100.00')
                }]
            return []
        
        total = self.get_total_amount()
        schedule = []
        
        for split in splits:
            amount = (total * split.percentage) / Decimal('100.00')
            schedule.append({
                'period': split.fiscal_period,
                'amount': amount,
                'percentage': split.percentage
            })
        
        return schedule
    
    def is_applicable_to_student(self, student, academic_session=None):
        """
        Check if this fee structure applies to a given student.
        
        Args:
            student: Student instance
            academic_session: AcademicSession instance (optional). If None, uses current session.
        
        Returns:
            bool: True if applicable, False otherwise
        """
        # -------------------------------------------------------------------------
        # CHECK ACADEMIC SESSION
        # -------------------------------------------------------------------------
        if academic_session:
            if not self.applicable_sessions.filter(pk=academic_session.pk).exists():
                return False
        else:
            current_enrollment = student.get_current_enrollment()
            if current_enrollment:
                student_session = current_enrollment.class_instance.academic_session
                if not self.applicable_sessions.filter(pk=student_session.pk).exists():
                    return False
        
        # -------------------------------------------------------------------------
        # CHECK BOARDING TYPE
        # -------------------------------------------------------------------------
        if self.boarding_type_filter != 'ALL':
            # Get student's active boarding enrollment for the session
            boarding_enrollment = student.boarding_enrollments.filter(
                academic_session=academic_session if academic_session else current_enrollment.academic_session,
                status='ACTIVE'
            ).first()
            
            if self.boarding_type_filter == 'DAY_ONLY':
                # Student must NOT have an active boarding enrollment
                if boarding_enrollment:
                    return False
            elif self.boarding_type_filter == 'BOARDER_ONLY':
                # Student must have any active boarding enrollment
                if not boarding_enrollment:
                    return False
            else:
                # Specific boarding type filters
                if not boarding_enrollment:
                    return False
                
                filter_map = {
                    'FULL_BOARDER': 'FULL_BOARDER',
                    'WEEKLY_BOARDER': 'WEEKLY_BOARDER',
                    'FLEXI_BOARDER': 'FLEXI_BOARDER',
                }
                
                required_type = filter_map.get(self.boarding_type_filter)
                if boarding_enrollment.boarding_type != required_type:
                    return False
        
        # -------------------------------------------------------------------------
        # CHECK STUDENT TYPE (NEW vs CONTINUING)
        # -------------------------------------------------------------------------
        if self.student_type_filter != 'ALL':
            # Get student's class enrollment for the session
            class_enrollment = student.get_current_enrollment(academic_session)
            if not class_enrollment:
                return False
            
            if self.student_type_filter == 'NEW_ONLY':
                if class_enrollment.enrollment_type not in ['NEW', 'TRANSFER_IN', 'READMISSION']:
                    return False
            elif self.student_type_filter == 'CONTINUING_ONLY':
                if class_enrollment.enrollment_type not in ['CONTINUING', 'PROMOTED']:
                    return False
            elif self.student_type_filter == 'SCHOLARSHIP_ONLY':
                # Check if student has active scholarship
                # Assuming you have a scholarships relationship
                has_scholarship = hasattr(student, 'scholarships') and student.scholarships.filter(
                    is_active=True,
                    academic_session=academic_session if academic_session else class_enrollment.academic_session
                ).exists()
                
                if not has_scholarship:
                    return False
        
        # -------------------------------------------------------------------------
        # CHECK ACADEMIC LEVEL
        # -------------------------------------------------------------------------
        if self.academic_levels.exists():
            current_enrollment = student.get_current_enrollment(academic_session)
            if not current_enrollment:
                return False
            
            student_level = current_enrollment.class_instance.academic_level
            if not self.academic_levels.filter(pk=student_level.pk).exists():
                return False
        
        # -------------------------------------------------------------------------
        # CHECK SPECIFIC CLASSES
        # -------------------------------------------------------------------------
        if self.applicable_classes.exists():
            current_enrollment = student.get_current_enrollment(academic_session)
            if not current_enrollment:
                return False
            
            if not self.applicable_classes.filter(pk=current_enrollment.class_instance.pk).exists():
                return False
        
        return True
    
    def get_next_billing_period(self):
        """Get the next fiscal period for billing"""
        from core.utils import get_school_today
        
        today = get_school_today()
        return self.billing_periods.filter(
            start_date__gte=today,
            is_closed=False
        ).order_by('start_date').first()
    
    def should_generate_invoice_now(self):
        """Check if invoice should be generated in current fiscal period"""
        current_period = FiscalPeriod.get_current_fiscal_period()
        if not current_period:
            return False
        
        return self.billing_periods.filter(pk=current_period.pk).exists()
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
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
    """
    Through model for splitting fee structure billing across multiple fiscal periods.
    
    Example:
    - Term 1 fees: 50,000 UGX
    - Split 1: January period - 30,000 UGX (60%)
    - Split 2: February period - 20,000 UGX (40%)
    """
    
    fee_structure = models.ForeignKey(
        FeesStructure,
        verbose_name="Fee Structure",
        on_delete=models.CASCADE,
        related_name='billing_splits'
    )
    
    fiscal_period = models.ForeignKey(
        FiscalPeriod,
        verbose_name="Fiscal Period",
        on_delete=models.CASCADE,
        related_name='fee_structure_splits'
    )
    
    percentage = models.DecimalField(
        "Percentage of Total",
        max_digits=5,
        decimal_places=2,
        validators=[
            MinValueValidator(Decimal('0.01')),
            MaxValueValidator(Decimal('100.00'))
        ],
        help_text="Percentage of total fee structure to bill in this period"
    )
    
    sequence = models.PositiveIntegerField(
        "Sequence",
        default=1,
        help_text="Order of billing (1 = first installment, 2 = second, etc.)"
    )
    
    description = models.CharField(
        "Description",
        max_length=200,
        blank=True,
        help_text="E.g., 'First Installment', 'Second Installment'"
    )
    
    class Meta:
        verbose_name = "Fee Structure Billing Split"
        verbose_name_plural = "Fee Structure Billing Splits"
        ordering = ['fee_structure', 'sequence', 'fiscal_period__period_number']
        unique_together = ('fee_structure', 'fiscal_period')
        constraints = [
            models.CheckConstraint(
                check=models.Q(percentage__gt=0, percentage__lte=100),
                name='valid_percentage_range'
            ),
        ]
    
    def __str__(self):
        return f"{self.fee_structure.name} - {self.fiscal_period.name} ({self.percentage}%)"
    
    def clean(self):
        """Validate that total percentages for a fee structure don't exceed 100%"""
        super().clean()
        
        if self.fee_structure_id:
            total = FeesStructureBillingSplit.objects.filter(
                fee_structure=self.fee_structure
            ).exclude(pk=self.pk).aggregate(
                total=models.Sum('percentage')
            )['total'] or Decimal('0.00')
            
            total += self.percentage
            
            if total > Decimal('100.00'):
                raise ValidationError({
                    'percentage': f'Total billing percentages cannot exceed 100%. Current total: {total}%'
                })

class FeesStructureItem(BaseModel):
    """
    Individual fee line items within a fee structure.
    
    Architecture:
    - FeesStructure defines WHAT/WHEN (academic context + billing schedule)
    - FeesStructureItem defines DETAILS (specific fees + amounts + rules)
    
    Example:
    Structure: "Form 1 Day Scholar - Term 1 2024"
        Item 1: Tuition - 500,000 UGX
        Item 2: Computer Fee - 50,000 UGX
        Item 3: Library Fee - 25,000 UGX
    
    When invoices are generated based on billing_periods,
    these items are included with their configured amounts/rules.
    """
    
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
        on_delete=models.CASCADE,
        related_name='structure_items'
    )
    
    # -------------------------------------------------------------------------
    # AMOUNT CONFIGURATION
    # -------------------------------------------------------------------------
    
    amount = models.DecimalField(
        "Amount",
        max_digits=10, 
        decimal_places=2, 
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Base amount for this fee item"
    )
    
    # ✅ NEW: Support for variable amounts based on student attributes
    use_variable_amount = models.BooleanField(
        "Use Variable Amount",
        default=False,
        help_text="Amount varies based on student criteria (e.g., boarding type)"
    )
    
    variable_amount_rules = models.JSONField(
        "Variable Amount Rules",
        default=dict,
        blank=True,
        help_text="""
        JSON rules for variable amounts. Example:
        {
            "FULL_BOARDER": "300000.00",
            "WEEKLY_BOARDER": "150000.00",
            "DAY_SCHOLAR": "0.00"
        }
        """
    )
    
    # -------------------------------------------------------------------------
    # TAX CONFIGURATION
    # -------------------------------------------------------------------------
    
    is_taxable = models.BooleanField(
        "Is Taxable",
        default=False,
        help_text="Override from fee category if needed"
    )
    
    tax_percentage = models.DecimalField(
        "Tax Percentage",
        max_digits=5, 
        decimal_places=2, 
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text="Tax rate for this specific item (overrides category default)"
    )
    
    tax_inclusive = models.BooleanField(
        "Tax Inclusive",
        default=False,
        help_text="If True, amount includes tax. If False, tax is added on top"
    )
    
    # -------------------------------------------------------------------------
    # DISCOUNT CONFIGURATION
    # -------------------------------------------------------------------------
    
    default_discount_percentage = models.DecimalField(
        "Default Discount Percentage",
        max_digits=5, 
        decimal_places=2, 
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text="Default discount applied to this item"
    )
    
    max_discount_percentage = models.DecimalField(
        "Maximum Discount Percentage",
        max_digits=5, 
        decimal_places=2, 
        default=Decimal('100.00'),
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text="Maximum discount allowed for this item"
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
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text="Maximum scholarship discount percentage for this item (null = no limit)"
    )
    
    scholarship_priority = models.PositiveIntegerField(
        "Scholarship Priority",
        default=100,
        help_text="Order in which scholarships are applied (lower = higher priority)"
    )
    
    # -------------------------------------------------------------------------
    # CONDITIONAL INCLUSION
    # -------------------------------------------------------------------------
    
    is_mandatory = models.BooleanField(
        "Mandatory",
        default=True,
        help_text="Must be included on invoice (cannot be opted out)"
    )
    
    is_conditional = models.BooleanField(
        "Conditional",
        default=False,
        help_text="Only include if certain conditions are met"
    )
    
    condition_description = models.TextField(
        "Condition Description",
        blank=True,
        help_text="Human-readable description of when this item applies"
    )
    
    condition_criteria = models.JSONField(
        "Condition Criteria",
        default=dict,
        blank=True,
        help_text="""
        JSON criteria for when this item should be included. Examples:
        
        1. Boarding students only:
        {"boarding_status__in": ["FULL_BOARDER", "WEEKLY_BOARDER"]}
        
        2. New students only:
        {"enrollment_status": "NEW"}
        
        3. Specific classes:
        {"class_id__in": [1, 2, 3]}
        
        4. Subject-based (e.g., science students):
        {"has_subject": "SCIENCE"}
        """
    )
    
    # -------------------------------------------------------------------------
    # BILLING PERIOD OVERRIDE (Advanced Feature)
    # -------------------------------------------------------------------------
    
    override_billing_periods = models.BooleanField(
        "Override Billing Periods",
        default=False,
        help_text="Use different billing periods than parent structure"
    )
    
    custom_billing_periods = models.ManyToManyField(
        FiscalPeriod,
        verbose_name="Custom Billing Periods",
        blank=True,
        related_name='custom_fee_items',
        help_text="Specific periods to bill this item (if override enabled)"
    )
    
    # -------------------------------------------------------------------------
    # PAYMENT SCHEDULING
    # -------------------------------------------------------------------------
    
    is_payable_in_installments = models.BooleanField(
        "Payable in Installments",
        default=False,
        help_text="Can this specific item be paid in installments"
    )
    
    number_of_installments = models.PositiveIntegerField(
        "Number of Installments",
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(12)]
    )
    
    minimum_installment_amount = models.DecimalField(
        "Minimum Installment Amount",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Minimum amount per installment (null = no minimum)"
    )
    
    # -------------------------------------------------------------------------
    # DISPLAY CONFIGURATION
    # -------------------------------------------------------------------------
    
    display_order = models.PositiveIntegerField(
        "Display Order",
        default=1,
        help_text="Order on invoice (within display group)"
    )
    
    print_on_invoice = models.BooleanField(
        "Print on Invoice",
        default=True,
        help_text="Include this item on printed invoices"
    )
    
    custom_description = models.TextField(
        "Custom Description",
        blank=True,
        help_text="Override fee category description for this structure"
    )
    
    # -------------------------------------------------------------------------
    # NOTES AND METADATA
    # -------------------------------------------------------------------------
    
    internal_notes = models.TextField(
        "Internal Notes",
        blank=True,
        help_text="Notes for accounting staff (not shown to parents)"
    )
    
    # -------------------------------------------------------------------------
    # VALIDATION
    # -------------------------------------------------------------------------
    
    def clean(self):
        """Enhanced validation"""
        super().clean()
        errors = {}
        
        # Validate discount limits
        if self.default_discount_percentage > self.max_discount_percentage:
            errors['default_discount_percentage'] = (
                f"Default discount ({self.default_discount_percentage}%) cannot exceed "
                f"maximum discount ({self.max_discount_percentage}%)"
            )
        
        # Validate scholarship discount
        if self.max_scholarship_discount is not None:
            if self.max_scholarship_discount > Decimal('100.00'):
                errors['max_scholarship_discount'] = "Cannot exceed 100%"
        
        # Validate installments
        if self.is_payable_in_installments and self.number_of_installments < 2:
            errors['number_of_installments'] = (
                "Must be at least 2 if payable in installments"
            )
        
        # Validate variable amount rules
        if self.use_variable_amount and not self.variable_amount_rules:
            errors['variable_amount_rules'] = (
                "Variable amount rules required when 'Use Variable Amount' is enabled"
            )
        
        # Validate custom billing periods
        if self.override_billing_periods and self.pk:
            if not self.custom_billing_periods.exists():
                errors['custom_billing_periods'] = (
                    "Custom billing periods required when override is enabled"
                )
        
        if errors:
            raise ValidationError(errors)
    
    # -------------------------------------------------------------------------
    # AMOUNT CALCULATION METHODS
    # -------------------------------------------------------------------------
    
    def get_amount_for_student(self, student):
        """
        Get the applicable amount for a specific student.
        
        Args:
            student: Student instance
        
        Returns:
            Decimal: Amount applicable to this student
        """
        if not self.use_variable_amount:
            return self.amount
        
        # Get student's relevant attribute
        if hasattr(student, 'boarding_status'):
            boarding_status = student.boarding_status
            if boarding_status in self.variable_amount_rules:
                return Decimal(str(self.variable_amount_rules[boarding_status]))
        
        # Fallback to base amount
        return self.amount
    
    def calculate_tax_amount(self, base_amount=None):
        """
        Calculate tax amount for this item.
        
        Args:
            base_amount: Amount to calculate tax on (defaults to item amount)
        
        Returns:
            Decimal: Tax amount
        """
        if not self.is_taxable or self.tax_percentage == 0:
            return Decimal('0.00')
        
        amount = base_amount or self.amount
        
        if self.tax_inclusive:
            # Tax is already included in amount
            # Tax = Amount * (Tax% / (100 + Tax%))
            tax = amount * (self.tax_percentage / (Decimal('100.00') + self.tax_percentage))
        else:
            # Tax is added on top
            tax = amount * (self.tax_percentage / Decimal('100.00'))
        
        return tax.quantize(Decimal('0.01'))
    
    def calculate_net_amount(self, base_amount=None):
        """
        Calculate net amount (before tax).
        
        Args:
            base_amount: Base amount (defaults to item amount)
        
        Returns:
            Decimal: Net amount
        """
        amount = base_amount or self.amount
        
        if self.is_taxable and self.tax_inclusive:
            # Remove tax from inclusive amount
            net = amount / (Decimal('1.00') + (self.tax_percentage / Decimal('100.00')))
            return net.quantize(Decimal('0.01'))
        
        return amount
    
    def calculate_gross_amount(self, base_amount=None):
        """
        Calculate gross amount (including tax).
        
        Args:
            base_amount: Base amount (defaults to item amount)
        
        Returns:
            Decimal: Gross amount
        """
        amount = base_amount or self.amount
        
        if self.is_taxable and not self.tax_inclusive:
            # Add tax to amount
            gross = amount * (Decimal('1.00') + (self.tax_percentage / Decimal('100.00')))
            return gross.quantize(Decimal('0.01'))
        
        return amount
    
    # -------------------------------------------------------------------------
    # APPLICABILITY CHECKS
    # -------------------------------------------------------------------------
    
    def is_applicable_to_student(self, student):
        """
        Check if this fee item applies to a given student.
        
        Args:
            student: Student instance
        
        Returns:
            bool: True if applicable, False otherwise
        """
        if not self.is_conditional:
            return True
        
        if not self.condition_criteria:
            return True
        
        # Evaluate condition criteria
        try:
            # Simple key-value matching
            for key, value in self.condition_criteria.items():
                if '__' in key:
                    # Django-style lookup (e.g., 'boarding_status__in')
                    field_name, lookup = key.split('__', 1)
                    
                    if not hasattr(student, field_name):
                        return False
                    
                    student_value = getattr(student, field_name)
                    
                    if lookup == 'in':
                        if student_value not in value:
                            return False
                    elif lookup == 'exact':
                        if student_value != value:
                            return False
                else:
                    # Direct comparison
                    if not hasattr(student, key):
                        return False
                    
                    if getattr(student, key) != value:
                        return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error evaluating condition criteria for {self}: {e}")
            return True  # Fail open (include item on error)
    
    def get_applicable_billing_periods(self):
        """
        Get billing periods for this item.
        
        Returns:
            QuerySet: FiscalPeriod objects
        """
        if self.override_billing_periods:
            return self.custom_billing_periods.all()
        
        return self.fee_structure.billing_periods.all()
    
    # -------------------------------------------------------------------------
    # DISPLAY HELPERS
    # -------------------------------------------------------------------------
    
    def get_description(self):
        """Get display description (custom or from category)"""
        return self.custom_description or self.fee_category.description
    
    def get_display_name(self):
        """Get display name for invoices"""
        return self.fee_category.name
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
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
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        amount_display = f"{self.amount:,.2f}"
        if self.use_variable_amount:
            amount_display = "Variable"
        return f"{self.fee_structure.name} - {self.fee_category.name} ({amount_display})"


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
    # HELPER METHODS TO GET ACCOUNTS FROM MAPPINGS
    # -------------------------------------------------------------------------
    
    def get_receivable_account(self):
        """
        Get accounts receivable account for this invoice.
        
        Returns:
            Account: Student receivables account to debit (always 1100)
        """
        from core.models import FinancialSettings
        
        settings = FinancialSettings.get_instance()
        if not settings:
            return None
        
        mappings = settings.get_account_mappings()
        return mappings.student_receivables_account
    
    # -------------------------------------------------------------------------
    # REVENUE BREAKDOWN HELPER (for reporting)
    # -------------------------------------------------------------------------
    
    def get_revenue_breakdown(self):
        """
        Get revenue breakdown by category type for this invoice.
        
        This is useful for reporting and analytics, showing how much
        revenue came from each fee category type.
        
        Returns:
            dict: Revenue amounts grouped by category type
            
        Example:
            {
                'TUITION': Decimal('300000.00'),
                'MEALS': Decimal('50000.00'),
                'BOARDING': Decimal('200000.00'),
                'UNIFORM': Decimal('50000.00')
            }
        """
        from django.db.models import Sum
        
        breakdown = self.items.values(
            'fee_category__category_type',
            'fee_category__code'
        ).annotate(
            total=Sum('final_amount')
        ).order_by('fee_category__category_type')
        
        result = {}
        for item in breakdown:
            category_type = item['fee_category__category_type'] or item['fee_category__code'] or 'OTHER'
            result[category_type] = item['total']
        
        return result
    
    def get_revenue_account_allocation(self):
        """
        Get breakdown showing which GL accounts this invoice's revenue goes to.
        
        This matches the logic used in journal entry creation, showing
        how the invoice total is split across revenue accounts.
        
        Returns:
            dict: Account allocations
            
        Example:
            {
                'account_4000': {
                    'account_number': '4000',
                    'account_name': 'Tuition Fees',
                    'amount': Decimal('350000.00'),
                    'categories': ['TUITION', 'MEALS', 'EXAM']
                },
                'account_4100': {
                    'account_number': '4100',
                    'account_name': 'Boarding Revenue',
                    'amount': Decimal('200000.00'),
                    'categories': ['BOARDING', 'LAUNDRY']
                }
            }
        """
        from core.models import FinancialSettings
        from decimal import Decimal
        
        settings = FinancialSettings.get_instance()
        if not settings:
            return {}
        
        mappings = settings.get_account_mappings()
        
        # Group items by which account they'll hit
        account_allocation = {}
        
        for item in self.items.all():
            category_type = item.fee_category.category_type or ''
            category_code = item.fee_category.code or ''
            amount = item.final_amount
            
            # Use same logic as _create_journal_entry
            if category_type in [
                'TUITION', 'EXAM', 'DEVELOPMENT', 'MEDICAL', 'SPORT',
                'MEALS', 'TECHNOLOGY', 'LABORATORY', 'LIBRARY', 'TRANSPORT',
                'ADMISSION', 'REGISTRATION', 'CLUB', 'LATE_PAYMENT',
                'FIELD_TRIP', 'GRADUATION', 'INSURANCE', 'BOOKS', 'OTHER'
            ]:
                account = mappings.default_revenue_account
            elif category_type in ['BOARDING', 'LAUNDRY']:
                account = mappings.boarding_revenue_account or mappings.default_revenue_account
            elif category_type == 'UNIFORM':
                account = mappings.uniform_and_book_sales_account or mappings.default_revenue_account
            elif not category_type:
                # Empty category_type - check code
                if category_code in ['TUITION', 'EXAM', 'MEALS']:
                    account = mappings.default_revenue_account
                elif category_code == 'BOARD':
                    account = mappings.boarding_revenue_account or mappings.default_revenue_account
                else:
                    account = mappings.default_revenue_account
            else:
                account = mappings.default_revenue_account
            
            # Build allocation dict
            account_key = f"account_{account.account_number}"
            
            if account_key not in account_allocation:
                account_allocation[account_key] = {
                    'account_number': account.account_number,
                    'account_name': account.name,
                    'amount': Decimal('0.00'),
                    'categories': []
                }
            
            account_allocation[account_key]['amount'] += amount
            
            # Track which categories contributed
            category_label = category_type or category_code or 'OTHER'
            if category_label not in account_allocation[account_key]['categories']:
                account_allocation[account_key]['categories'].append(category_label)
        
        return account_allocation

    def can_be_safely_modified(self):
        """
        Check if invoice can be safely deleted/modified.
        
        Safe to delete if:
        1. Invoice is DRAFT, VOID, or CANCELLED
        2. No payments have been made (paid_amount = 0)
        3. Journal entry is DRAFT or doesn't exist
        4. No completed payment records exist
        
        Returns:
            tuple: (can_modify: bool, reason: str)
        """
        # Check 1: Must be DRAFT, VOID, or CANCELLED
        if self.status not in ['DRAFT', 'VOID', 'CANCELLED']:
            return False, f"Invoice status is {self.status} (must be DRAFT, VOID, or CANCELLED)"
        
        # Check 2: No payments (VOID/CANCELLED should never have payments anyway)
        if self.paid_amount > 0:
            return False, f"Invoice has payments totaling {self.paid_amount}"
        
        # Check 3: Journal entry must be DRAFT or not exist
        if self.journal_entry_id:
            from finance.models import JournalEntry
            try:
                journal_entry = JournalEntry.objects.get(pk=self.journal_entry_id)
                if journal_entry.status not in ['DRAFT', 'REVERSED']:
                    return False, f"Journal entry {journal_entry.entry_number} is {journal_entry.status}"
            except JournalEntry.DoesNotExist:
                # Journal entry was deleted - this is OK
                pass
        
        # Check 4: No completed payments
        if self.payments.exists():
            completed_payments = self.payments.filter(status='COMPLETED')
            if completed_payments.exists():
                return False, "Invoice has completed payment records"
        
        return True, "OK"

    def recalculate_totals(self, auto_reapply_discounts=False):
        """
        Recalculate invoice totals from line items.
        
        Args:
            auto_reapply_discounts: If True, re-apply auto scholarships/discounts.
                                Set to False during manual editing (default).
        """
        from decimal import Decimal
        import logging
        
        logger = logging.getLogger(__name__)
        
        # Get all items
        items = self.items.all()
        
        if not items.exists():
            # No items - reset to zero
            self.subtotal_amount = Decimal('0.00')
            self.tax_amount = Decimal('0.00')
            self.discount_amount = Decimal('0.00')
            self.scholarship_discount_amount = Decimal('0.00')
            self.total_amount = Decimal('0.00')
            self.balance = Decimal('0.00')
            self.has_scholarships_applied = False
            self.has_discounts_applied = False
            self.save()
            logger.info(f"Invoice {self.invoice_number} now has no items - totals reset to 0")
            return
        
        # Calculate subtotal (sum of all item amounts before discounts/tax)
        self.subtotal_amount = sum(item.amount for item in items)
        
        # Calculate tax
        self.tax_amount = sum(item.tax_amount for item in items)
        
        # Calculate regular discounts (sum from all items)
        self.discount_amount = sum(item.discount_amount for item in items)
        
        # Calculate scholarship discounts (sum from all items)
        self.scholarship_discount_amount = sum(item.scholarship_discount_amount for item in items)
        
        # Calculate total (sum of all final amounts)
        self.total_amount = sum(item.final_amount for item in items)
        
        # Update balance
        self.balance = self.total_amount - self.paid_amount
        
        # Update flags based on actual amounts
        self.has_scholarships_applied = self.scholarship_discount_amount > Decimal('0.00')
        self.has_discounts_applied = self.discount_amount > Decimal('0.00')
        
        # =====================================================================
        # OPTIONAL: Re-apply scholarships/discounts (only if explicitly requested)
        # =====================================================================
        if auto_reapply_discounts:
            if self.auto_scholarships_applied or self.auto_discounts_applied:
                logger.info("Re-applying auto scholarships/discounts after recalculation")
                
                # Reset discount amounts
                self.scholarship_discount_amount = Decimal('0.00')
                self.discount_amount = Decimal('0.00')
                
                # Reset item-level discounts
                for item in items:
                    item.discount_amount = Decimal('0.00')
                    item.scholarship_discount_amount = Decimal('0.00')
                    item.total_discount_amount = Decimal('0.00')
                    item.recalculate_totals()
                    item.save()
                
                # Re-apply scholarships
                if self.auto_scholarships_applied:
                    from fees.invoice_generators import UnifiedStudentInvoiceGenerator
                    UnifiedStudentInvoiceGenerator._auto_apply_scholarships(self)
                
                # Re-apply discounts
                if self.auto_discounts_applied:
                    from fees.invoice_generators import UnifiedStudentInvoiceGenerator
                    UnifiedStudentInvoiceGenerator._auto_apply_discounts(self)
        
        # Save (without recursive reapplication)
        self.save()
        
        logger.info(
            f"Recalculated invoice {self.invoice_number}: "
            f"Subtotal={self.subtotal_amount}, Tax={self.tax_amount}, "
            f"Regular Discounts={self.discount_amount}, "
            f"Scholarship Discounts={self.scholarship_discount_amount}, "
            f"Total={self.total_amount}, Balance={self.balance}"
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

    def recalculate_totals(self):
        """
        Recalculate item totals based on unit_amount, quantity, tax, and discounts.
        
        This method updates:
        - amount (unit_amount × quantity)
        - tax_amount (based on tax_percentage)
        - total_discount_amount (discount_amount + scholarship_discount_amount)
        - final_amount (amount - discounts + tax)
        """
        from decimal import Decimal
        
        # Calculate base amount
        self.amount = self.unit_amount * self.quantity
        
        # Calculate total discount
        self.total_discount_amount = self.discount_amount + self.scholarship_discount_amount
        
        # Calculate taxable amount (after discounts)
        taxable_amount = self.amount - self.total_discount_amount
        
        # Calculate tax
        self.tax_amount = (taxable_amount * self.tax_percentage / Decimal('100.00')).quantize(Decimal('0.01'))
        
        # Calculate final amount
        self.final_amount = taxable_amount + self.tax_amount
        
        # Update flags
        self.has_regular_discount = self.discount_amount > Decimal('0.00')
        self.has_scholarship_discount = self.scholarship_discount_amount > Decimal('0.00')


    def get_subtotal(self):
        """Get line subtotal (before discounts and tax)."""
        return self.amount  # This is already unit_amount × quantity


    def get_taxable_amount(self):
        """Get amount subject to tax (after discounts)."""
        return self.amount - self.total_discount_amount


    def get_net_amount(self):
        """Get net amount (after discounts, before tax)."""
        return self.amount - self.total_discount_amount



class Payment(BaseModel):
    """
    Payment model with comprehensive tracking, reversal, and refund support.
    
    KEY CONCEPTS:
    - REVERSAL: Internal correction, no actual money movement (wrong invoice, duplicate entry)
    - REFUND: Actual money returned to payer (overpayment, cancellation)
    - A payment can be EITHER reversed OR refunded, never both
    - Reversed/refunded payments don't affect balances (tracked but inactive)
    """
    
    PAYMENT_STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
        ('CANCELLED', 'Cancelled'),
        ('REVERSED', 'Reversed'),  # NEW: For internal corrections
        ('REFUNDED', 'Refunded'),  # Actual money returned
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
    
    # =========================================================================
    # IDENTIFICATION
    # =========================================================================
    
    payment_number = models.CharField(
        "Payment Number", 
        max_length=50, 
        unique=True, 
        db_index=True
    )
    
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
    
    # =========================================================================
    # PAYMENT DETAILS
    # =========================================================================
    
    amount = models.DecimalField(
        "Amount",
        max_digits=12, 
        decimal_places=2, 
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Total amount paid (including any overpayment)"
    )
    
    amount_applied_to_invoice = models.DecimalField(
        "Amount Applied to Invoice",
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Amount that reduced the invoice balance"
    )
    
    overpayment_amount = models.DecimalField(
        "Overpayment Amount",
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Amount exceeding invoice balance (becomes student credit)"
    )
    
    # =========================================================================
    # PAYMENT METHOD DETAILS
    # =========================================================================
    
    payment_date = models.DateField("Payment Date", db_index=True)
    
    payment_method = models.ForeignKey(
        PaymentMethod,
        verbose_name="Payment Method",
        on_delete=models.PROTECT,
        related_name='student_payments'
    )
    
    reference_number = models.CharField(
        "Reference Number", 
        max_length=100, 
        blank=True, 
        db_index=True,
        help_text="External reference (e.g., bank transaction reference)"
    )
    
    transaction_id = models.CharField(
        "Transaction ID", 
        max_length=100, 
        blank=True, 
        db_index=True,
        help_text="Payment gateway or mobile money transaction ID"
    )
    
    # =========================================================================
    # BANK/CARD DETAILS
    # =========================================================================
    
    bank_name = models.CharField("Bank Name", max_length=100, blank=True)
    account_number = models.CharField("Account Number", max_length=50, blank=True)
    cheque_number = models.CharField("Cheque Number", max_length=50, blank=True)
    cheque_date = models.DateField("Cheque Date", null=True, blank=True)
    
    # =========================================================================
    # MOBILE MONEY DETAILS
    # =========================================================================
    
    mobile_money_provider = models.CharField(
        "Mobile Money Provider", 
        max_length=50, 
        blank=True
    )
    
    mobile_number = models.CharField(
        "Mobile Money Number", 
        max_length=20, 
        blank=True,
        help_text="Mobile money account number used for the transaction"
    )
    
    # =========================================================================
    # PAYER INFORMATION
    # =========================================================================
    
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
    
    # =========================================================================
    # PROCESSING FEES
    # =========================================================================
    
    processing_fee_amount = models.DecimalField(
        "Processing Fee Amount",
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Fee charged by payment method (e.g., mobile money charges)"
    )
    
    processing_fee_account = models.ForeignKey(
        'finance.Account',
        verbose_name="Processing Fee Account",
        on_delete=models.PROTECT,
        related_name='processing_fee_payments',
        null=True,
        blank=True,
        help_text="Expense account for payment processing fees (auto-assigned from settings)"
    )
    
    # =========================================================================
    # STATUS AND VERIFICATION
    # =========================================================================
    
    status = models.CharField(
        "Payment Status",
        max_length=12,
        choices=PAYMENT_STATUS_CHOICES,
        default='COMPLETED',
        db_index=True
    )
    
    is_verified = models.BooleanField(
        "Verified", 
        default=False, 
        db_index=True,
        help_text="Whether payment has been verified by finance team"
    )
    
    verified_by_id = models.CharField(
        "Verified By ID",
        max_length=50,
        null=True,
        blank=True,
        help_text="User ID who verified this payment"
    )
    
    verification_date = models.DateTimeField(
        "Verification Date", 
        null=True, 
        blank=True
    )
    
    # =========================================================================
    # RECEIPT DETAILS
    # =========================================================================
    
    receipt_number = models.CharField(
        "Receipt Number", 
        max_length=50, 
        unique=True, 
        db_index=True
    )
    
    receipt_issued = models.BooleanField(
        "Receipt Issued", 
        default=False,
        help_text="Whether receipt has been issued to payer"
    )
    
    receipt_issued_date = models.DateTimeField(
        "Receipt Issued Date", 
        null=True, 
        blank=True
    )
    
    # =========================================================================
    # PROCESSING DETAILS
    # =========================================================================
    
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
    
    # =========================================================================
    # REVERSAL TRACKING (Internal Correction - No Money Movement) ⭐ NEW
    # =========================================================================
    
    reversed = models.BooleanField(
        "Reversed",
        default=False,
        db_index=True,
        help_text=(
            "Payment was reversed due to internal error (wrong invoice, duplicate entry). "
            "No actual money was returned - this is an accounting correction only."
        )
    )
    
    reversed_on = models.DateTimeField(
        "Reversed On",
        null=True,
        blank=True,
        help_text="When this payment was reversed"
    )
    
    reversed_by_id = models.CharField(
        "Reversed By ID",
        max_length=50,
        null=True,
        blank=True,
        help_text="User ID who reversed this payment"
    )
    
    reversal_reason = models.TextField(
        "Reversal Reason",
        blank=True,
        help_text="Detailed reason for payment reversal (e.g., 'Duplicate payment entry', 'Posted to wrong invoice')"
    )
    
    reversal_journal_entry = models.ForeignKey(
        'finance.JournalEntry',
        verbose_name="Reversal Journal Entry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reversed_fee_payments',
        help_text="Journal entry created when payment was reversed"
    )
    
    # =========================================================================
    # REFUND TRACKING (Actual Money Returned to Payer) ⭐ NEW
    # =========================================================================
    
    refunded = models.BooleanField(
        "Refunded",
        default=False,
        db_index=True,
        help_text=(
            "Actual money was returned to the payer (overpayment, cancellation, withdrawal). "
            "This represents real cash outflow from school accounts."
        )
    )
    
    refunded_on = models.DateTimeField(
        "Refunded On",
        null=True,
        blank=True,
        help_text="When refund was processed and money returned"
    )
    
    refunded_by_id = models.CharField(
        "Refunded By ID",
        max_length=50,
        null=True,
        blank=True,
        help_text="User ID who processed the refund"
    )
    
    refund_method = models.CharField(
        "Refund Method",
        max_length=50,
        blank=True,
        choices=[
            ('CASH', 'Cash'),
            ('BANK_TRANSFER', 'Bank Transfer'),
            ('MOBILE_MONEY', 'Mobile Money'),
            ('CHEQUE', 'Cheque'),
            ('ORIGINAL_METHOD', 'Refund to Original Payment Method'),
        ],
        help_text="How the refund was issued to the payer"
    )
    
    refund_reference = models.CharField(
        "Refund Reference",
        max_length=100,
        blank=True,
        db_index=True,
        help_text="Reference number for refund transaction (bank ref, mobile money ref, etc.)"
    )
    
    refund_journal_entry = models.ForeignKey(
        'finance.JournalEntry',
        verbose_name="Refund Journal Entry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='refunded_fee_payments',
        help_text="Journal entry created when refund was issued"
    )
    
    refund_notes = models.TextField(
        "Refund Notes",
        blank=True,
        help_text="Additional notes about the refund (recipient details, reason, approval, etc.)"
    )
    
    # =========================================================================
    # ADDITIONAL DETAILS
    # =========================================================================
    
    remarks = models.TextField(
        "Remarks", 
        blank=True,
        help_text="Public remarks visible on receipts"
    )
    
    internal_notes = models.TextField(
        "Internal Notes", 
        blank=True,
        help_text="Internal notes for finance team only (not visible to parents/students)"
    )
    
    # =========================================================================
    # ACADEMIC CONTEXT (Which session was this payment for?)
    # =========================================================================
    
    academic_session = models.ForeignKey(
        AcademicSession,
        verbose_name="Academic Session",
        on_delete=models.SET_NULL,
        null=True,
        related_name='payments',
        help_text="Academic session this payment is for (from invoice)"
    )
    
    # =========================================================================
    # FISCAL CONTEXT (When was this payment received?)
    # =========================================================================
    
    fiscal_period = models.ForeignKey(
        FiscalPeriod,
        verbose_name="Fiscal Period",
        on_delete=models.PROTECT,
        related_name='payments',
        help_text="Fiscal period when payment was received (for cash flow tracking)"
    )
    
    # =========================================================================
    # BREAK PERIOD TRACKING
    # =========================================================================
    
    is_break_payment = models.BooleanField(
        "Break Period Payment", 
        default=False,
        help_text="Payment made during break period (for reporting)"
    )
    
    # =========================================================================
    # FEE BREAKDOWN
    # =========================================================================
    
    fee_breakdown = models.JSONField(
        "Fee Breakdown", 
        default=dict, 
        blank=True,
        help_text="Breakdown of payment allocation across fee categories (JSON)"
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
        related_name='fee_payments',
        help_text="Journal entry created for this payment (DR: Cash/Bank, CR: Receivables)"
    )
    
    auto_create_journal_entry = models.BooleanField(
        "Auto-Create Journal Entry",
        default=True,
        help_text="Automatically create journal entry when payment is verified"
    )
    
    # =========================================================================
    # ACCOUNT MAPPING HELPERS (Get accounts from CoreAccountMappings)
    # =========================================================================
    
    def get_deposit_account(self):
        """
        Get appropriate deposit account based on payment method.
        
        Uses CoreAccountMappings to determine correct account:
        - Cash payments → default_cash_account
        - Bank transfers → default_bank_account
        - Mobile money → mobile_money_account (if configured)
        - Petty cash → petty_cash_account (if configured)
        
        Returns:
            Account: Cash/Bank account where payment was deposited
        """
        from core.models import FinancialSettings
        
        settings = FinancialSettings.get_instance()
        if not settings:
            logger.error("FinancialSettings not configured")
            return None
        
        mappings = settings.get_account_mappings()
        return mappings.get_cash_or_bank_account(self.payment_method)
    
    def get_receivable_account(self):
        """
        Get accounts receivable account to credit.
        
        Returns:
            Account: Student receivables account (always the same)
        """
        from core.models import FinancialSettings
        
        settings = FinancialSettings.get_instance()
        if not settings:
            logger.error("FinancialSettings not configured")
            return None
        
        mappings = settings.get_account_mappings()
        return mappings.student_receivables_account
    
    def get_processing_fee_account(self):
        """
        Get processing fee expense account.
        
        Returns:
            Account: Processing fee expense account from mappings
        """
        # If specific account set on payment, use it
        if self.processing_fee_account:
            return self.processing_fee_account
        
        # Otherwise get from special account mappings
        from core.models import FinancialSettings
        
        settings = FinancialSettings.get_instance()
        if not settings:
            return None
        
        # Try to get from special account mappings
        special_mappings = getattr(settings, 'special_account_mappings', None)
        if special_mappings and hasattr(special_mappings, 'payment_processing_fee_account'):
            return special_mappings.payment_processing_fee_account
        
        # Fallback: use default expense account
        mappings = settings.get_account_mappings()
        return mappings.default_expense_account
    
    # =========================================================================
    # VALIDATION
    # =========================================================================
    
    def clean(self):
        """Validate payment data"""
        super().clean()
        errors = {}
        
        # Cannot be both reversed AND refunded
        if self.reversed and self.refunded:
            errors['reversed'] = "Payment cannot be both reversed and refunded. Choose one."
            errors['refunded'] = "Payment cannot be both reversed and refunded. Choose one."
        
        # If reversed, must have reason
        if self.reversed and not self.reversal_reason:
            errors['reversal_reason'] = "Reversal reason is required for reversed payments"
        
        # If refunded, must have refund method
        if self.refunded and not self.refund_method:
            errors['refund_method'] = "Refund method is required for refunded payments"
        
        # If refunded, should have reference
        if self.refunded and not self.refund_reference:
            # This is a warning, not an error
            logger.warning(
                f"Payment {self.payment_number} refunded without refund reference"
            )
        
        # Amount validations
        if self.amount < 0:
            errors['amount'] = "Payment amount cannot be negative"
        
        if self.amount_applied_to_invoice > self.amount:
            errors['amount_applied_to_invoice'] = (
                "Amount applied to invoice cannot exceed total payment amount"
            )
        
        if self.overpayment_amount < 0:
            errors['overpayment_amount'] = "Overpayment amount cannot be negative"
        
        # Processing fee validation
        if self.processing_fee_amount < 0:
            errors['processing_fee_amount'] = "Processing fee cannot be negative"
        
        if errors:
            raise ValidationError(errors)
    
    # =========================================================================
    # STATUS PROPERTIES AND HELPERS ⭐ NEW
    # =========================================================================
    
    @property
    def is_active(self):
        """
        Check if payment is still active (not reversed or refunded).
        
        Active payments count toward balances and reports.
        Inactive payments are kept for audit trail only.
        
        Returns:
            bool: True if payment is active and affects balances
        """
        return not self.reversed and not self.refunded
    
    @property
    def effective_amount(self):
        """
        Get effective amount that counts toward balances.
        
        Returns:
            Decimal: Amount (0 if reversed/refunded, full amount if active)
        """
        if not self.is_active:
            return Decimal('0.00')
        return self.amount
    
    @property
    def payment_state(self):
        """
        Get human-readable payment state.
        
        Returns:
            str: Current state of payment
        """
        if self.reversed:
            return "REVERSED"
        elif self.refunded:
            return "REFUNDED"
        elif self.status == 'COMPLETED' and self.is_verified:
            return "ACTIVE"
        else:
            return self.status
    
    def can_be_reversed(self):
        """
        Check if this payment can be reversed.
        
        Returns:
            tuple: (can_reverse: bool, reason: str)
        """
        if self.reversed:
            return False, "Payment already reversed"
        
        if self.refunded:
            return False, "Cannot reverse a refunded payment"
        
        if self.status == 'FAILED' or self.status == 'CANCELLED':
            return False, f"Cannot reverse {self.status.lower()} payment"
        
        # Check if fiscal period is closed
        if self.fiscal_period and hasattr(self.fiscal_period, 'is_closed'):
            if self.fiscal_period.is_closed:
                return False, "Cannot reverse payment from closed fiscal period"
        
        return True, "OK"

    def reverse(self, reason, reversed_by):
        """
        Reverse this payment (internal correction - no money movement).
        
        This is used for correcting mistakes like:
        - Payment posted to wrong invoice
        - Duplicate payment entry
        - Data entry errors
        
        The actual reversal logic (journal entries, invoice updates, etc.)
        is handled by the signal handler in fees/signals.py
        
        Args:
            reason: Detailed reason for reversal
            reversed_by: User object performing the reversal
            
        Raises:
            ValidationError: If payment cannot be reversed
        """
        from django.core.exceptions import ValidationError
        from django.utils import timezone
        from django.db import transaction
        
        # Check if can be reversed
        can_reverse, error_reason = self.can_be_reversed()
        if not can_reverse:
            raise ValidationError(error_reason)
        
        with transaction.atomic():
            # Mark as reversed
            self.reversed = True
            self.reversed_on = timezone.now()
            self.reversed_by_id = str(reversed_by.id)
            self.reversal_reason = reason
            self.status = 'REVERSED'
            
            # Save - the signal will handle the rest
            # (journal entry, invoice update, student account update)
            self.save()
            
            logger.info(
                f"✅ Payment {self.payment_number} marked as REVERSED. "
                f"Signal handler will process journal entries and balance updates."
            )
    
    def can_be_refunded(self):
        """
        Check if this payment can be refunded.
        
        Returns:
            tuple: (can_refund: bool, reason: str)
        """
        if self.refunded:
            return False, "Payment already refunded"
        
        if self.reversed:
            return False, "Cannot refund a reversed payment (reversal is internal correction only)"
        
        if self.status != 'COMPLETED':
            return False, f"Can only refund completed payments (current status: {self.status})"
        
        return True, "OK"
    
    # =========================================================================
    # USER RETRIEVAL HELPERS
    # =========================================================================
    
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
    
    def get_reversed_by_user(self):
        """Get the user who reversed this payment"""
        if not self.reversed_by_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            return User.objects.using('default').get(id=self.reversed_by_id)
        except Exception as e:
            logger.error(f"Error fetching reversed_by user: {e}")
            return None
    
    def get_refunded_by_user(self):
        """Get the user who refunded this payment"""
        if not self.refunded_by_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            return User.objects.using('default').get(id=self.refunded_by_id)
        except Exception as e:
            logger.error(f"Error fetching refunded_by user: {e}")
            return None
    
    # =========================================================================
    # AUDIT TRAIL HELPERS
    # =========================================================================
    
    def get_audit_trail(self):
        """
        Get complete audit trail for this payment.
        
        Returns:
            dict: Chronological audit trail
        """
        trail = []
        
        # Creation
        trail.append({
            'action': 'CREATED',
            'timestamp': self.created_at,
            'user': self.get_created_by_user(),
            'details': f"Payment {self.payment_number} created for {self.amount}"
        })
        
        # Receipt issued
        if self.receipt_issued and self.receipt_issued_date:
            trail.append({
                'action': 'RECEIPT_ISSUED',
                'timestamp': self.receipt_issued_date,
                'details': f"Receipt {self.receipt_number} issued"
            })
        
        # Verification
        if self.is_verified and self.verification_date:
            trail.append({
                'action': 'VERIFIED',
                'timestamp': self.verification_date,
                'user': self.get_verified_by_user(),
                'details': "Payment verified by finance team"
            })
        
        # Journal entry
        if self.journal_entry:
            trail.append({
                'action': 'JOURNAL_ENTRY_CREATED',
                'timestamp': self.journal_entry.created_at,
                'details': f"Journal Entry {self.journal_entry.entry_number} created"
            })
        
        # Reversal
        if self.reversed and self.reversed_on:
            trail.append({
                'action': 'REVERSED',
                'timestamp': self.reversed_on,
                'user': self.get_reversed_by_user(),
                'details': f"Payment reversed: {self.reversal_reason}"
            })
            
            if self.reversal_journal_entry:
                trail.append({
                    'action': 'REVERSAL_JOURNAL_ENTRY',
                    'timestamp': self.reversal_journal_entry.created_at,
                    'details': f"Reversal Journal Entry {self.reversal_journal_entry.entry_number} created"
                })
        
        # Refund
        if self.refunded and self.refunded_on:
            trail.append({
                'action': 'REFUNDED',
                'timestamp': self.refunded_on,
                'user': self.get_refunded_by_user(),
                'details': f"Refund issued via {self.refund_method} - Ref: {self.refund_reference}"
            })
            
            if self.refund_journal_entry:
                trail.append({
                    'action': 'REFUND_JOURNAL_ENTRY',
                    'timestamp': self.refund_journal_entry.created_at,
                    'details': f"Refund Journal Entry {self.refund_journal_entry.entry_number} created"
                })
        
        # Sort by timestamp
        trail.sort(key=lambda x: x['timestamp'])
        
        return trail
    
    # =========================================================================
    # META CLASS
    # =========================================================================
    
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
            # NEW indexes for reversal/refund tracking
            models.Index(fields=['reversed']),
            models.Index(fields=['refunded']),
            models.Index(fields=['reversed_on']),
            models.Index(fields=['refunded_on']),
            models.Index(fields=['refund_reference']),
        ]
        constraints = [
            # Ensure amount is positive
            models.CheckConstraint(
                check=models.Q(amount__gt=0),
                name='payment_amount_positive'
            ),
            # Ensure overpayment is non-negative
            models.CheckConstraint(
                check=models.Q(overpayment_amount__gte=0),
                name='payment_overpayment_non_negative'
            ),
            # Ensure processing fee is non-negative
            models.CheckConstraint(
                check=models.Q(processing_fee_amount__gte=0),
                name='payment_processing_fee_non_negative'
            ),
        ]
    
    # =========================================================================
    # STRING REPRESENTATION
    # =========================================================================
    
    def __str__(self):
        state_suffix = ""
        if self.reversed:
            state_suffix = " [REVERSED]"
        elif self.refunded:
            state_suffix = " [REFUNDED]"
        
        return f"{self.payment_number} - {self.student.get_full_name()} - {self.amount:,.2f}{state_suffix}"
    
class BadDebtWriteOff(BaseModel):
    """Track bad debt write-offs for uncollectible invoices"""
    
    invoice = models.ForeignKey(
        FeeInvoice,
        on_delete=models.PROTECT,
        related_name='bad_debt_write_offs'
    )
    
    write_off_amount = models.DecimalField(
        "Write-Off Amount",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    
    write_off_date = models.DateField("Write-Off Date")
    
    fiscal_period = models.ForeignKey(
        'core.FiscalPeriod',
        on_delete=models.PROTECT,
        related_name='bad_debt_write_offs'
    )
    
    use_allowance_method = models.BooleanField(
        "Use Allowance Method",
        default=False,
        help_text="If true, debit Allowance account; if false, debit Bad Debt Expense"
    )
    
    reason = models.TextField("Reason for Write-Off")
    
    approved_by = models.ForeignKey(
        'hr.Staff',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_write_offs'
    )
    
    approval_date = models.DateTimeField("Approval Date", null=True, blank=True)
    
    journal_entry = models.ForeignKey(
        'finance.JournalEntry',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bad_debt_write_offs'
    )
    
    class Meta:
        verbose_name = "Bad Debt Write-Off"
        verbose_name_plural = "Bad Debt Write-Offs"
        ordering = ['-write_off_date']
    
    def __str__(self):
        return f"Write-off: {self.invoice.invoice_number} - {self.write_off_amount}"

# =============================================================================
# SCHOLARSHIP PROGRAM MODELS
# =============================================================================

# fees/models.py - COMPLETE REWRITTEN ScholarshipProgram Model

class ScholarshipProgram(BaseModel):
    """
    Scholarship programs with detailed configuration and category-specific discount templates.
    
    DISCOUNT MODES:
    
    1. GLOBAL DISCOUNT (Traditional):
       - discount_type = 'PERCENTAGE' or 'FIXED_AMOUNT' or 'FULL_WAIVER'
       - Same discount applies to ALL fee categories
       - Simple and straightforward
    
    2. CATEGORY-SPECIFIC DISCOUNT (Advanced):
       - discount_type = 'CATEGORY_SPECIFIC'
       - default_category_discounts defines template per category
       - Example: 100% tuition, 0% boarding, 50% meals
       - When awarding scholarships, officers can customize per student
    
    PROGRAM TYPES:
    - BUDGETED: Fixed budget pool, tracked spending
    - POLICY_BASED: No budget limits, automatic eligibility
    - DISCRETIONARY: Case-by-case approval
    - SPONSORED: Donor-funded with specific budget
    """
    
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
        ('PERCENTAGE', 'Percentage Discount (Global)'),
        ('FIXED_AMOUNT', 'Fixed Amount Discount (Global)'),
        ('FULL_WAIVER', 'Full Fee Waiver (Global)'),
        ('CATEGORY_SPECIFIC', 'Category-Specific Discounts'),  # ⭐ ENHANCED
    ]
    
    ELIGIBILITY_RENEWAL_CHOICES = [
        ('AUTOMATIC', 'Automatic Renewal'),
        ('PERFORMANCE_BASED', 'Performance-Based Review'),
        ('ANNUAL_APPLICATION', 'Annual Re-application Required'),
        ('ONE_TIME_ONLY', 'One-Time Award'),
    ]

    PROGRAM_TYPE_CHOICES = [
        ('BUDGETED', 'Budgeted Program'),           # Has fixed budget
        ('POLICY_BASED', 'Policy-Based Program'),   # No budget - automatic eligibility
        ('DISCRETIONARY', 'Discretionary'),         # Case-by-case, no budget
        ('SPONSORED', 'Externally Sponsored'),      # Donor-funded with budget
    ]
    
    # =========================================================================
    # BASIC PROGRAM INFORMATION
    # =========================================================================
    
    name = models.CharField("Program Name", max_length=200)
    code = models.CharField("Program Code", max_length=50, unique=True, db_index=True)
    scholarship_type = models.CharField(
        "Scholarship Type", 
        max_length=30, 
        choices=SCHOLARSHIP_TYPES,
        db_index=True
    )
    description = models.TextField("Description")
    
    # =========================================================================
    # FINANCIAL CONFIGURATION
    # =========================================================================

    program_type = models.CharField(
        "Program Type",
        max_length=20,
        choices=PROGRAM_TYPE_CHOICES,
        default='POLICY_BASED',
        help_text="How this program is funded and managed"
    )
    
    discount_type = models.CharField(
        "Discount Type", 
        max_length=20, 
        choices=DISCOUNT_TYPE_CHOICES,
        help_text=(
            "PERCENTAGE/FIXED_AMOUNT/FULL_WAIVER: Same discount for all categories. "
            "CATEGORY_SPECIFIC: Define different discounts per category."
        )
    )
    
    # -------------------------------------------------------------------------
    # GLOBAL DISCOUNT SETTINGS (When discount_type != CATEGORY_SPECIFIC)
    # -------------------------------------------------------------------------
    
    discount_percentage = models.DecimalField(
        "Global Discount Percentage",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text="For PERCENTAGE discount type: applies to all categories"
    )
    
    fixed_discount_amount = models.DecimalField(
        "Global Fixed Discount Amount",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="For FIXED_AMOUNT discount type: applies to all categories"
    )
    
    maximum_award_amount = models.DecimalField(
        "Maximum Award Amount Per Student",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Overall cap on total discount per student (across all categories)"
    )
    
    # =========================================================================
    # CATEGORY-SPECIFIC DISCOUNT CONFIGURATION ⭐ NEW
    # =========================================================================
    
    default_category_discounts = models.JSONField(
        "Default Category Discount Template",
        default=dict,
        blank=True,
        help_text="""
        Default discount rules per fee category (used when discount_type = CATEGORY_SPECIFIC).
        When awarding scholarships, these defaults are pre-filled but can be customized per student.
        
        Structure:
        {
            "TUITION": {
                "type": "percentage" | "fixed_amount" | "full_waiver" | "none",
                "value": 100.00,
                "description": "Optional explanation"
            },
            "BOARDING": {
                "type": "none",
                "value": 0.00,
                "description": "Not covered by this scholarship"
            },
            "MEALS": {
                "type": "percentage",
                "value": 50.00
            }
        }
        
        Common Templates:
        
        1. FULL TUITION ONLY:
        {
            "TUITION": {"type": "full_waiver", "value": 100.00},
            "BOARDING": {"type": "none", "value": 0.00},
            "MEALS": {"type": "none", "value": 0.00},
            "TRANSPORT": {"type": "none", "value": 0.00}
        }
        
        2. 50% EVERYTHING:
        {
            "TUITION": {"type": "percentage", "value": 50.00},
            "BOARDING": {"type": "percentage", "value": 50.00},
            "MEALS": {"type": "percentage", "value": 50.00}
        }
        
        3. TUITION + PARTIAL BOARDING:
        {
            "TUITION": {"type": "full_waiver", "value": 100.00},
            "BOARDING": {"type": "percentage", "value": 50.00},
            "MEALS": {"type": "percentage", "value": 50.00}
        }
        
        4. FIXED AMOUNTS:
        {
            "TUITION": {"type": "fixed_amount", "value": 500000.00},
            "EXAM": {"type": "fixed_amount", "value": 50000.00},
            "BOARDING": {"type": "none", "value": 0.00}
        }
        
        Notes:
        - Only used when discount_type = 'CATEGORY_SPECIFIC'
        - Category codes must match FeesCategory.category_type or FeesCategory.code
        - If a category is not listed, no discount is applied by default
        - Scholarship officers can customize these when awarding scholarships
        """
    )
    
    allows_category_customization = models.BooleanField(
        "Allow Category Customization Per Student",
        default=True,
        help_text=(
            "If True, scholarship officers can customize category discounts when awarding scholarships. "
            "If False, default_category_discounts template is enforced for all students."
        )
    )
    
    category_discount_description = models.TextField(
        "Category Discount Explanation",
        blank=True,
        help_text=(
            "Human-readable explanation of how category discounts work for this program. "
            "Example: 'This scholarship covers 100% of tuition fees but does not cover boarding or meal costs.'"
        )
    )
    
    # =========================================================================
    # APPLICABLE FEE CATEGORIES (Legacy - for filtering)
    # =========================================================================
    
    applicable_fee_categories = models.ManyToManyField(
        FeesCategory,
        verbose_name="Applicable Fee Categories (Legacy Filter)",
        blank=True,
        help_text=(
            "Legacy field: Leave empty to apply to all fee categories. "
            "For CATEGORY_SPECIFIC mode, use default_category_discounts instead."
        )
    )
    
    # =========================================================================
    # ELIGIBILITY CRITERIA
    # =========================================================================
    
    minimum_gpa = models.DecimalField(
        "Minimum GPA Requirement",
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Student must maintain this GPA to qualify/renew"
    )
    
    minimum_attendance_percentage = models.DecimalField(
        "Minimum Attendance Percentage",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Student must maintain this attendance to qualify/renew"
    )
    
    family_income_threshold = models.DecimalField(
        "Family Income Threshold",
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum family income for need-based scholarships"
    )
    
    # =========================================================================
    # ACADEMIC LEVEL RESTRICTIONS
    # =========================================================================
    
    applicable_levels = models.ManyToManyField(
        AcademicLevel,
        verbose_name="Applicable Academic Levels",
        blank=True,
        help_text="Leave empty to apply to all levels"
    )
    
    # =========================================================================
    # PROGRAM LIMITS AND BUDGET
    # =========================================================================
    
    total_budget_amount = models.DecimalField(
        "Total Program Budget",
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Required for BUDGETED and SPONSORED programs, not applicable for POLICY_BASED"
    )
    
    requires_budget_tracking = models.BooleanField(
        "Requires Budget Tracking",
        default=False,
        help_text="Track spending against budget? False for unlimited programs"
    )
    
    maximum_recipients = models.PositiveIntegerField(
        "Maximum Number of Recipients",
        null=True,
        blank=True,
        help_text="Maximum number of students who can receive this scholarship"
    )
    
    current_budget_used = models.DecimalField(
        "Current Budget Used",
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Total amount awarded to date (tracked automatically)"
    )
    
    current_recipient_count = models.PositiveIntegerField(
        "Current Recipients",
        default=0,
        help_text="Number of students currently receiving this scholarship"
    )
    
    # =========================================================================
    # TIME AND RENEWAL SETTINGS
    # =========================================================================
    
    renewal_policy = models.CharField(
        "Renewal Policy",
        max_length=20,
        choices=ELIGIBILITY_RENEWAL_CHOICES,
        default='ANNUAL_APPLICATION',
        help_text="How scholarships are renewed for subsequent years/terms"
    )
    
    maximum_duration_years = models.PositiveIntegerField(
        "Maximum Duration (Years)",
        default=1,
        help_text="Maximum years a student can receive this scholarship"
    )
    
    # =========================================================================
    # APPLICATION AND AWARD PERIODS
    # =========================================================================
    
    application_start_date = models.DateField(
        "Application Start Date", 
        null=True, 
        blank=True,
        help_text="When students can start applying"
    )
    
    application_end_date = models.DateField(
        "Application End Date", 
        null=True, 
        blank=True,
        help_text="Deadline for scholarship applications"
    )
    
    award_announcement_date = models.DateField(
        "Award Announcement Date", 
        null=True, 
        blank=True,
        help_text="When scholarship awards will be announced"
    )
    
    # =========================================================================
    # SPONSOR INFORMATION
    # =========================================================================
    
    sponsor_name = models.CharField(
        "Sponsor Name", 
        max_length=200, 
        blank=True,
        help_text="Name of sponsor/donor (for SPONSORED programs)"
    )
    
    sponsor_contact = models.TextField(
        "Sponsor Contact Information", 
        blank=True,
        help_text="Contact details for sponsor/donor"
    )
    
    external_funding_source = models.CharField(
        "External Funding Source", 
        max_length=200, 
        blank=True,
        help_text="Source of external funding (e.g., foundation, corporation)"
    )
    
    # =========================================================================
    # PROGRAM STATUS
    # =========================================================================
    
    is_active = models.BooleanField(
        "Is Active", 
        default=True, 
        db_index=True,
        help_text="Only active programs can award scholarships"
    )
    
    is_accepting_applications = models.BooleanField(
        "Accepting Applications", 
        default=True,
        help_text="Whether this program is currently accepting applications"
    )
    
    # =========================================================================
    # ACADEMIC SESSION VALIDITY
    # =========================================================================
    
    valid_sessions = models.ManyToManyField(
        AcademicSession,
        verbose_name="Valid Academic Sessions",
        blank=True,
        help_text="Sessions in which this program is available (leave empty for all sessions)"
    )
    
    # =========================================================================
    # VALIDATION
    # =========================================================================
    
    def clean(self):
        """Validate scholarship program configuration"""
        super().clean()
        errors = {}
        
        # =====================================================================
        # VALIDATE BUDGET REQUIREMENTS
        # =====================================================================
        
        # Budgeted/Sponsored programs MUST have a budget
        if self.program_type in ['BUDGETED', 'SPONSORED']:
            if not self.total_budget_amount:
                errors['total_budget_amount'] = (
                    'Budget amount is required for budgeted/sponsored programs'
                )
        
        # Policy-based shouldn't have budget limits
        if self.program_type == 'POLICY_BASED':
            if self.total_budget_amount:
                errors['total_budget_amount'] = (
                    'Policy-based programs should not have budget limits'
                )
        
        # =====================================================================
        # VALIDATE DISCOUNT CONFIGURATION ⭐ FIXED
        # =====================================================================
        
        discount_type = self.discount_type
        
        if discount_type == 'PERCENTAGE':
            if not self.discount_percentage:
                errors['discount_percentage'] = (
                    'Discount percentage is required when discount type is PERCENTAGE'
                )
            elif self.discount_percentage < 0 or self.discount_percentage > 100:
                errors['discount_percentage'] = (
                    'Discount percentage must be between 0 and 100'
                )
        
        elif discount_type == 'FIXED_AMOUNT':
            if not self.fixed_discount_amount:
                errors['fixed_discount_amount'] = (
                    'Fixed discount amount is required when discount type is FIXED_AMOUNT'
                )
            elif self.fixed_discount_amount < 0:
                errors['fixed_discount_amount'] = (
                    'Fixed discount amount cannot be negative'
                )
        
        elif discount_type == 'CATEGORY_SPECIFIC':
            # ⭐ FIX: Only validate structure if default_category_discounts already exists
            # Don't require it to exist during form save (form's save() will populate it)
            if self.default_category_discounts:
                # Validate structure of category discounts
                for category_code, config in self.default_category_discounts.items():
                    if not isinstance(config, dict):
                        # Use 'discount_type' instead of 'default_category_discounts'
                        errors['discount_type'] = (
                            f"Invalid configuration for category '{category_code}': must be a dictionary"
                        )
                        continue
                    
                    config_type = config.get('type')
                    config_value = config.get('value', 0)
                    
                    # Validate discount type
                    if config_type not in ['percentage', 'fixed_amount', 'full_waiver', 'none']:
                        errors['discount_type'] = (
                            f"Invalid discount type '{config_type}' for category '{category_code}'. "
                            f"Must be one of: percentage, fixed_amount, full_waiver, none"
                        )
                    
                    # Validate percentage range
                    if config_type == 'percentage':
                        try:
                            value = Decimal(str(config_value))
                            if value < 0 or value > 100:
                                errors['discount_type'] = (
                                    f"Percentage for category '{category_code}' must be between 0 and 100. "
                                    f"Got: {value}"
                                )
                        except (ValueError, TypeError, InvalidOperation):
                            errors['discount_type'] = (
                                f"Invalid percentage value for category '{category_code}': {config_value}"
                            )
                    
                    # Validate fixed amount is positive
                    elif config_type == 'fixed_amount':
                        try:
                            value = Decimal(str(config_value))
                            if value < 0:
                                errors['discount_type'] = (
                                    f"Fixed amount for category '{category_code}' cannot be negative. "
                                    f"Got: {value}"
                                )
                        except (ValueError, TypeError, InvalidOperation):
                            errors['discount_type'] = (
                                f"Invalid fixed amount value for category '{category_code}': {config_value}"
                            )
            # Note: We don't validate if it's empty - the form will populate it before save
        
        # =====================================================================
        # VALIDATE DATES
        # =====================================================================
        
        if self.application_start_date and self.application_end_date:
            if self.application_end_date < self.application_start_date:
                errors['application_end_date'] = (
                    'Application end date cannot be before start date'
                )
        
        if errors:
            raise ValidationError(errors)
    
    # =========================================================================
    # DISCOUNT MODE HELPERS ⭐ NEW
    # =========================================================================
    
    def is_global_discount(self):
        """
        Check if using global discount mode (same discount for all categories).
        
        Returns:
            bool: True if PERCENTAGE, FIXED_AMOUNT, or FULL_WAIVER
        """
        return self.discount_type in ['PERCENTAGE', 'FIXED_AMOUNT', 'FULL_WAIVER']
    
    def is_category_specific_discount(self):
        """
        Check if using category-specific discount mode.
        
        Returns:
            bool: True if CATEGORY_SPECIFIC
        """
        return self.discount_type == 'CATEGORY_SPECIFIC'
    
    def get_discount_summary(self):
        """
        Get human-readable summary of discount configuration.
        
        Returns:
            str: Description of how discounts work for this program
        """
        if self.discount_type == 'PERCENTAGE':
            return f"{self.discount_percentage}% discount on all eligible fees"
        
        elif self.discount_type == 'FIXED_AMOUNT':
            return f"Fixed discount of {self.fixed_discount_amount:,.0f} UGX per invoice"
        
        elif self.discount_type == 'FULL_WAIVER':
            return "100% fee waiver (full scholarship)"
        
        elif self.discount_type == 'CATEGORY_SPECIFIC':
            if not self.default_category_discounts:
                return "Category-specific discounts (not yet configured)"
            
            # Summarize category discounts
            summary_parts = []
            for code, config in self.default_category_discounts.items():
                discount_type = config.get('type')
                discount_value = config.get('value', 0)
                
                if discount_type == 'percentage':
                    summary_parts.append(f"{code}: {discount_value}%")
                elif discount_type == 'fixed_amount':
                    summary_parts.append(f"{code}: {discount_value:,.0f} UGX")
                elif discount_type == 'full_waiver':
                    summary_parts.append(f"{code}: 100%")
                elif discount_type == 'none':
                    summary_parts.append(f"{code}: Not covered")
            
            if summary_parts:
                return "Category-specific: " + ", ".join(summary_parts[:3]) + \
                       (f" (+{len(summary_parts) - 3} more)" if len(summary_parts) > 3 else "")
            else:
                return "Category-specific discounts configured"
        
        return "Discount type not configured"
    
    def get_category_discount_template(self):
        """
        Get the default category discount template for this program.
        
        Returns:
            dict: Category discount template (empty dict if not category-specific)
        """
        if not self.is_category_specific_discount():
            return {}
        
        return self.default_category_discounts.copy()
    
    def get_covered_categories(self):
        """
        Get list of fee categories covered by this scholarship.
        
        Returns:
            list: Category codes with non-zero discounts, or None for global mode
        """
        if self.is_global_discount():
            # All categories covered
            return None
        
        # Category-specific: only non-'none' categories
        covered = []
        for code, config in self.default_category_discounts.items():
            if config.get('type') != 'none':
                covered.append(code)
        
        return covered
    
    # =========================================================================
    # BUDGET TRACKING HELPERS
    # =========================================================================
    
    def get_remaining_budget(self):
        """
        Calculate remaining program budget.
        
        Returns:
            Decimal: Remaining budget, or None if no budget tracking
        """
        if not self.total_budget_amount:
            return None
        
        return self.total_budget_amount - self.current_budget_used
    
    def has_budget_available(self, amount):
        """
        Check if program has sufficient budget for given amount.
        
        Args:
            amount: Decimal amount to check
        
        Returns:
            bool: True if sufficient budget (or no budget tracking)
        """
        if not self.requires_budget_tracking or not self.total_budget_amount:
            return True
        
        remaining = self.get_remaining_budget()
        return remaining is not None and remaining >= amount
    
    def can_accept_new_recipient(self):
        """
        Check if program can accept a new scholarship recipient.
        
        Returns:
            tuple: (can_accept: bool, reason: str)
        """
        if not self.is_active:
            return False, "Program is not active"
        
        if self.maximum_recipients:
            if self.current_recipient_count >= self.maximum_recipients:
                return False, f"Maximum recipients reached ({self.maximum_recipients})"
        
        if self.requires_budget_tracking and self.total_budget_amount:
            remaining = self.get_remaining_budget()
            if remaining is not None and remaining <= 0:
                return False, "Program budget exhausted"
        
        return True, "OK"
    
    # =========================================================================
    # META CLASS
    # =========================================================================
    
    class Meta:
        verbose_name = "Scholarship Program"
        verbose_name_plural = "Scholarship Programs"
        ordering = ['name']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['scholarship_type']),
            models.Index(fields=['is_active']),
            models.Index(fields=['program_type']),
            models.Index(fields=['discount_type']),  # ⭐ NEW
        ]
    
    # =========================================================================
    # STRING REPRESENTATION
    # =========================================================================
    
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
    """
    Active scholarships awarded to students with category-specific discount support.
    
    Three Types of Scholarships:
    1. Policy-Based (amount_awarded = 0): Discount comes from program.discount_percentage
       - Can apply same percentage to all categories OR
       - Use category_discounts for different percentages per category
    
    2. Budget-Based (amount_awarded > 0): Discount tracked against fixed budget
       - Single budget pool applied across all categories OR
       - Use category_discounts for targeted spending
    
    3. Category-Specific: Granular control per fee category
       - Example: 100% tuition waiver, 0% boarding, 50% meals
       - Overrides program-level discount settings when enabled
    
    Architecture:
    - use_category_specific_discounts=False: Use program's global discount
    - use_category_specific_discounts=True: Use category_discounts JSON field
    """
    
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
    
    # =========================================================================
    # CORE RELATIONSHIPS
    # =========================================================================
    
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
    
    # =========================================================================
    # AWARD AMOUNTS
    # =========================================================================
    
    amount_awarded = models.DecimalField(
        "Total Amount Awarded",
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text=(
            "For budget-based scholarships: Total amount available across all sessions. "
            "For policy-based scholarships: Set to 0.00 (discount comes from program percentage)."
        )
    )
    
    total_amount_used = models.DecimalField(
        "Total Amount Used to Date",
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Cumulative amount applied to invoices (only tracked for budget-based scholarships)"
    )
    
    # =========================================================================
    # CATEGORY-SPECIFIC DISCOUNT CONFIGURATION ⭐ NEW
    # =========================================================================
    
    use_category_specific_discounts = models.BooleanField(
        "Use Category-Specific Discounts",
        default=False,
        db_index=True,
        help_text=(
            "Enable granular control per fee category. "
            "If True, uses category_discounts field. "
            "If False, uses program's global discount for all categories."
        )
    )
    
    category_discounts = models.JSONField(
        "Category-Specific Discount Rules",
        default=dict,
        blank=True,
        help_text="""
        JSON mapping fee category codes to discount configurations.
        
        Structure:
        {
            "TUITION": {
                "type": "percentage" | "fixed_amount" | "full_waiver" | "none",
                "value": 100.00,
                "notes": "Optional notes"
            },
            "BOARDING": {
                "type": "none",
                "value": 0.00
            },
            "MEALS": {
                "type": "percentage",
                "value": 50.00
            }
        }
        
        Discount Types:
        - "percentage": value is percentage (0-100)
        - "fixed_amount": value is specific amount per invoice
        - "full_waiver": 100% discount (value ignored)
        - "none": no discount for this category
        
        Examples:
        
        1. Full tuition waiver, no boarding discount:
        {
            "TUITION": {"type": "full_waiver", "value": 100.00},
            "BOARDING": {"type": "none", "value": 0.00}
        }
        
        2. 50% discount on everything:
        {
            "TUITION": {"type": "percentage", "value": 50.00},
            "BOARDING": {"type": "percentage", "value": 50.00},
            "MEALS": {"type": "percentage", "value": 50.00}
        }
        
        3. Fixed amount tuition, percentage boarding:
        {
            "TUITION": {"type": "fixed_amount", "value": 500000.00},
            "BOARDING": {"type": "percentage", "value": 25.00}
        }
        
        4. Complex scenario:
        {
            "TUITION": {"type": "full_waiver", "value": 100.00},
            "EXAM": {"type": "percentage", "value": 75.00},
            "BOARDING": {"type": "none", "value": 0.00},
            "MEALS": {"type": "fixed_amount", "value": 50000.00},
            "TRANSPORT": {"type": "percentage", "value": 50.00}
        }
        
        Notes:
        - If a category is not listed, it defaults to program's global discount
        - Category codes match FeesCategory.category_type or FeesCategory.code
        - For budget-based scholarships, total spending across all categories
          is tracked against amount_awarded
        """
    )
    
    category_discount_notes = models.TextField(
        "Category Discount Notes",
        blank=True,
        help_text="Administrative notes explaining why specific category discounts were configured"
    )
    
    # =========================================================================
    # DATE RANGE
    # =========================================================================
    
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
    
    # =========================================================================
    # DISTRIBUTION SETTINGS
    # =========================================================================
    
    distribution_method = models.CharField(
        "Distribution Method",
        max_length=20,
        choices=DISTRIBUTION_METHOD_CHOICES,
        default='PROPORTIONAL',
        help_text=(
            "How to distribute the scholarship. "
            "For policy-based (percentage) scholarships, use PROPORTIONAL. "
            "For budget-based scholarships, choose based on how to allocate the fixed amount."
        )
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
    
    # =========================================================================
    # STATUS
    # =========================================================================
    
    status = models.CharField(
        "Scholarship Status",
        max_length=15,
        choices=SCHOLARSHIP_STATUS_CHOICES,
        default='ACTIVE',
        db_index=True
    )
    
    # =========================================================================
    # RENEWAL SETTINGS
    # =========================================================================
    
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
    
    # =========================================================================
    # PERFORMANCE TRACKING
    # =========================================================================
    
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
    
    # =========================================================================
    # ADMINISTRATIVE FIELDS
    # =========================================================================
    
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
    
# =========================================================================
    # VALIDATION
    # =========================================================================
    
    def clean(self):
        """Validate scholarship configuration based on program type"""
        super().clean()
        
        if not self.scholarship_program_id:
            return  # Can't validate without program
        
        program = self.scholarship_program
        errors = {}
        
        # =====================================================================
        # VALIDATE AMOUNT AWARDED BASED ON PROGRAM TYPE
        # =====================================================================
        
        if program.program_type in ['BUDGETED', 'SPONSORED']:
            # Budget-based programs MUST have amount_awarded > 0
            if program.discount_type == 'FIXED_AMOUNT':
                if not self.amount_awarded or self.amount_awarded <= 0:
                    errors['amount_awarded'] = (
                        f"'{program.name}' is a budget-based program and requires "
                        f"a specific amount to be awarded (e.g., 500000.00). "
                        f"Cannot be zero or empty."
                    )
        
        elif program.program_type in ['POLICY_BASED', 'DISCRETIONARY']:
            # Policy-based / Discretionary with percentage discount: auto-correct amount to zero
            if program.discount_type == 'PERCENTAGE':
                if self.amount_awarded and self.amount_awarded > 0:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(
                        f"Scholarship {self.id}: Policy-based program '{program.name}' "
                        f"uses percentage discount. Setting amount_awarded to 0.00"
                    )
                    self.amount_awarded = Decimal('0.00')
            
            # For CATEGORY_SPECIFIC or FULL_WAIVER: amount can legitimately be 0.00
            # so we do NOT raise an error here — the discount comes from the program config
        
        # Validate amount_used doesn't exceed amount_awarded (for budget-based only)
        if self.amount_awarded > 0:
            if self.total_amount_used > self.amount_awarded:
                errors['total_amount_used'] = (
                    f"Amount used ({self.total_amount_used}) cannot exceed "
                    f"amount awarded ({self.amount_awarded})"
                )
        
        # =====================================================================
        # VALIDATE CATEGORY-SPECIFIC DISCOUNTS
        # =====================================================================
        # NOTE: errors keyed to None here because 'category_discounts' is a
        # JSONField populated by the form's sub-forms — it is NOT a field on
        # StudentScholarshipForm. Keying to a non-existent form field causes
        # Django's add_error() to raise a ValueError.
        # =====================================================================
        
        if self.use_category_specific_discounts:
            if not self.category_discounts:
                errors[None] = (
                    "Category-specific discounts are enabled but no discount rules are configured. "
                    "Either configure category discounts or disable category-specific discounts."
                )
            else:
                # Validate each category discount configuration
                for category_code, config in self.category_discounts.items():
                    if not isinstance(config, dict):
                        errors[None] = (
                            f"Invalid configuration for category '{category_code}': must be a dictionary"
                        )
                        continue
                    
                    discount_type = config.get('type')
                    discount_value = config.get('value', 0)
                    
                    # Validate discount type
                    if discount_type not in ['percentage', 'fixed_amount', 'full_waiver', 'none']:
                        errors[None] = (
                            f"Invalid discount type '{discount_type}' for category '{category_code}'. "
                            f"Must be one of: percentage, fixed_amount, full_waiver, none"
                        )
                    
                    # Validate discount value
                    if discount_type == 'percentage':
                        try:
                            value = Decimal(str(discount_value))
                            if value < 0 or value > 100:
                                errors[None] = (
                                    f"Percentage for category '{category_code}' must be between 0 and 100. "
                                    f"Got: {value}"
                                )
                        except (ValueError, TypeError, InvalidOperation):
                            errors[None] = (
                                f"Invalid percentage value for category '{category_code}': {discount_value}"
                            )
                    
                    elif discount_type == 'fixed_amount':
                        try:
                            value = Decimal(str(discount_value))
                            if value < 0:
                                errors[None] = (
                                    f"Fixed amount for category '{category_code}' cannot be negative. "
                                    f"Got: {value}"
                                )
                        except (ValueError, TypeError, InvalidOperation):
                            errors[None] = (
                                f"Invalid fixed amount value for category '{category_code}': {discount_value}"
                            )
        
        # =====================================================================
        # VALIDATE DISTRIBUTION METHOD SETTINGS
        # =====================================================================
        
        if self.distribution_method == 'EQUAL_PER_SESSION':
            if not self.amount_per_session or self.amount_per_session <= 0:
                errors['amount_per_session'] = (
                    "Amount per session is required when using EQUAL_PER_SESSION distribution"
                )
        
        elif self.distribution_method == 'EQUAL_PER_INVOICE':
            if not self.amount_per_invoice or self.amount_per_invoice <= 0:
                errors['amount_per_invoice'] = (
                    "Amount per invoice is required when using EQUAL_PER_INVOICE distribution"
                )
        
        # =====================================================================
        # VALIDATE DATES
        # =====================================================================
        
        if self.end_date and self.start_date:
            if self.end_date < self.start_date:
                errors['end_date'] = "End date cannot be before start date"
        
        if errors:
            raise ValidationError(errors)
    
    # =========================================================================
    # SCHOLARSHIP TYPE HELPERS
    # =========================================================================
    
    def is_policy_based(self):
        """
        Check if this is a policy-based scholarship.
        
        Returns:
            bool: True if policy-based (uses program percentage)
        """
        program = self.scholarship_program
        return (
            program.program_type == 'POLICY_BASED' and
            program.discount_type in ['PERCENTAGE', 'FULL_WAIVER']
        )
    
    def is_budget_based(self):
        """
        Check if this is a budget-based scholarship.
        
        Returns:
            bool: True if budget-based (tracks amount_awarded)
        """
        program = self.scholarship_program
        return (
            program.program_type in ['BUDGETED', 'SPONSORED'] and
            program.discount_type == 'FIXED_AMOUNT' and
            self.amount_awarded > 0
        )
    
    def requires_budget_tracking(self):
        """
        Check if this scholarship requires budget tracking.
        
        Returns:
            bool: True if should track total_amount_used
        """
        return self.is_budget_based()
    
    def is_category_specific(self):
        """
        Check if using category-specific discounts.
        
        Returns:
            bool: True if category-specific mode is enabled
        """
        return self.use_category_specific_discounts and bool(self.category_discounts)
    
    # =========================================================================
    # BALANCE CALCULATION
    # =========================================================================
    
    def get_remaining_balance(self):
        """
        Calculate remaining scholarship balance.
        
        Returns:
            Decimal: Remaining balance for budget-based scholarships
            None: For policy-based scholarships (not applicable)
        """
        if not self.is_budget_based():
            # Policy-based scholarships don't have a balance
            return None
        
        return self.amount_awarded - self.total_amount_used
    
    @property
    def remaining_balance(self):
        """Property shortcut for get_remaining_balance()"""
        return self.get_remaining_balance()
    
    def is_exhausted(self):
        """
        Check if scholarship budget is exhausted.
        
        Returns:
            bool: True if budget-based and no balance remaining
            bool: False for policy-based scholarships (never exhausted)
        """
        if not self.is_budget_based():
            return False  # Policy-based scholarships are never exhausted
        
        remaining = self.get_remaining_balance()
        return remaining is not None and remaining <= Decimal('0.00')
    
    def has_sufficient_balance(self, amount):
        """
        Check if scholarship has sufficient balance for given amount.
        
        Args:
            amount: Decimal amount to check
            
        Returns:
            bool: True if sufficient balance (or policy-based)
        """
        if not self.is_budget_based():
            return True  # Policy-based scholarships are unlimited
        
        remaining = self.get_remaining_balance()
        return remaining is not None and remaining >= amount
    
    # =========================================================================
    # CATEGORY DISCOUNT HELPERS ⭐ NEW
    # =========================================================================
    
    def get_category_discount_config(self, category_code):
        """
        Get discount configuration for a specific fee category.
        
        Args:
            category_code: Fee category code (e.g., 'TUITION', 'BOARDING')
        
        Returns:
            dict: Discount configuration or None if not found
        """
        if not self.use_category_specific_discounts:
            return None
        
        return self.category_discounts.get(category_code)
    
    def get_all_covered_categories(self):
        """
        Get list of all fee categories covered by this scholarship.
        
        Returns:
            list: Category codes that have discounts configured
        """
        if not self.use_category_specific_discounts:
            # All categories covered by program discount
            return None
        
        # Only categories with non-'none' discounts
        return [
            code for code, config in self.category_discounts.items()
            if config.get('type') != 'none'
        ]
    
    def get_category_discount_summary(self):
        """
        Get human-readable summary of category discounts.
        
        Returns:
            dict: Summary of discounts by category
        """
        if not self.use_category_specific_discounts:
            program = self.scholarship_program
            if program.discount_type == 'PERCENTAGE':
                return {
                    'mode': 'global',
                    'description': f"{program.discount_percentage}% discount on all categories"
                }
            elif program.discount_type == 'FULL_WAIVER':
                return {
                    'mode': 'global',
                    'description': "100% waiver on all categories"
                }
            else:
                return {
                    'mode': 'global',
                    'description': f"Fixed amount: {program.fixed_discount_amount}"
                }
        
        # Category-specific mode
        summary = {
            'mode': 'category_specific',
            'categories': {}
        }
        
        for code, config in self.category_discounts.items():
            discount_type = config.get('type')
            discount_value = config.get('value', 0)
            
            if discount_type == 'percentage':
                summary['categories'][code] = f"{discount_value}% discount"
            elif discount_type == 'fixed_amount':
                summary['categories'][code] = f"{discount_value:,.0f} UGX per invoice"
            elif discount_type == 'full_waiver':
                summary['categories'][code] = "100% waiver"
            elif discount_type == 'none':
                summary['categories'][code] = "No discount"
        
        return summary
    
    # =========================================================================
    # DISCOUNT CALCULATION ⭐ ENHANCED
    # =========================================================================
    
    def calculate_discount_for_amount(self, eligible_amount, category_code=None):
        """
        Calculate scholarship discount for a given eligible amount.
        
        Args:
            eligible_amount: Decimal - Amount eligible for scholarship discount
            category_code: str - Fee category code (required if using category-specific discounts)
            
        Returns:
            Decimal: Discount amount to apply
        """
        program = self.scholarship_program
        
        # =====================================================================
        # CATEGORY-SPECIFIC MODE ⭐ NEW
        # =====================================================================
        
        if self.use_category_specific_discounts:
            if not category_code:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(
                    f"Scholarship {self.id}: Category-specific mode enabled but no category_code provided. "
                    f"Falling back to program discount."
                )
                # Fall through to program discount
            else:
                # Get category-specific config
                config = self.get_category_discount_config(category_code)
                
                if config:
                    discount = self._calculate_category_discount(eligible_amount, config)
                    
                    # For budget-based scholarships, check remaining balance
                    if self.is_budget_based():
                        remaining = self.get_remaining_balance()
                        if remaining is not None and remaining > 0:
                            discount = min(discount, remaining)
                        else:
                            discount = Decimal('0.00')
                    
                    return discount
                else:
                    # Category not in config - use program default or no discount
                    # Depending on your business logic, you might want to:
                    # Option A: Fall through to program discount
                    # Option B: Return zero (no discount for unlisted categories)
                    # Using Option A for backward compatibility
                    pass
        
        # =====================================================================
        # POLICY-BASED MODE (Program-level discount)
        # =====================================================================
        
        if self.is_policy_based():
            if program.discount_type == 'PERCENTAGE' and program.discount_percentage:
                discount = (eligible_amount * program.discount_percentage / Decimal('100.00'))
                discount = discount.quantize(Decimal('0.01'))
                
                # Apply program maximum if set
                if program.maximum_award_amount and discount > program.maximum_award_amount:
                    discount = program.maximum_award_amount
                
                return discount
            
            elif program.discount_type == 'FULL_WAIVER':
                return eligible_amount
        
        # =====================================================================
        # BUDGET-BASED MODE
        # =====================================================================
        
        elif self.is_budget_based():
            remaining = self.get_remaining_balance()
            
            if remaining is None or remaining <= 0:
                return Decimal('0.00')
            
            # Discount is min of remaining balance and eligible amount
            return min(remaining, eligible_amount)
        
        return Decimal('0.00')
    
    def _calculate_category_discount(self, amount, config):
        """
        Calculate discount based on category-specific configuration.
        
        Args:
            amount: Decimal - Amount to calculate discount for
            config: dict - Category discount configuration
        
        Returns:
            Decimal: Discount amount
        """
        discount_type = config.get('type')
        discount_value = Decimal(str(config.get('value', 0)))
        
        if discount_type == 'percentage':
            discount = (amount * discount_value / Decimal('100.00'))
            return discount.quantize(Decimal('0.01'))
        
        elif discount_type == 'fixed_amount':
            # Fixed amount per invoice (capped at item amount)
            return min(discount_value, amount)
        
        elif discount_type == 'full_waiver':
            return amount
        
        elif discount_type == 'none':
            return Decimal('0.00')
        
        return Decimal('0.00')
    
    def apply_discount_to_invoice(self, invoice_amount, category_code=None):
        """
        Apply scholarship discount to an invoice and update usage tracking.
        
        Args:
            invoice_amount: Decimal - Invoice amount eligible for discount
            category_code: str - Fee category code (for category-specific discounts)
            
        Returns:
            Decimal: Actual discount amount applied
        """
        discount = self.calculate_discount_for_amount(invoice_amount, category_code)
        
        # Update usage tracking for budget-based scholarships
        if self.is_budget_based() and discount > 0:
            self.total_amount_used += discount
            self.save(update_fields=['total_amount_used'])
        
        return discount
    
    # =========================================================================
    # ELIGIBILITY CHECKS
    # =========================================================================
    
    def is_active_for_date(self, check_date=None):
        """
        Check if scholarship is active for a given date.
        
        Args:
            check_date: Date to check (default: today)
            
        Returns:
            bool: True if active
        """
        from django.utils import timezone
        
        if check_date is None:
            check_date = timezone.now().date()
        
        if self.status != 'ACTIVE':
            return False
        
        if check_date < self.start_date:
            return False
        
        if self.end_date and check_date > self.end_date:
            return False
        
        return True
    
    def check_renewal_eligibility(self):
        """
        Check if student meets renewal criteria.
        
        Returns:
            tuple: (eligible: bool, reasons: list)
        """
        if not self.requires_renewal_verification:
            return True, []
        
        reasons = []
        program = self.scholarship_program
        
        # Check GPA requirement
        if program.minimum_gpa:
            if not self.current_gpa or self.current_gpa < program.minimum_gpa:
                reasons.append(
                    f"GPA below minimum ({self.current_gpa} < {program.minimum_gpa})"
                )
        
        # Check attendance requirement
        if program.minimum_attendance_percentage:
            if not self.current_attendance or self.current_attendance < program.minimum_attendance_percentage:
                reasons.append(
                    f"Attendance below minimum "
                    f"({self.current_attendance}% < {program.minimum_attendance_percentage}%)"
                )
        
        # Check custom renewal criteria
        if self.renewal_criteria:
            # Add custom criteria checks here
            pass
        
        return len(reasons) == 0, reasons
    
    # =========================================================================
    # STATUS HELPERS
    # =========================================================================
    
    def can_be_applied(self):
        """
        Check if scholarship can be applied to invoices.
        
        Returns:
            tuple: (can_apply: bool, reason: str)
        """
        if self.status != 'ACTIVE':
            return False, f"Scholarship is {self.status.lower()}"
        
        if not self.is_active_for_date():
            return False, "Scholarship is not active for current date"
        
        if self.is_budget_based() and self.is_exhausted():
            return False, "Scholarship budget is exhausted"
        
        return True, "OK"
    
    def get_status_display_with_balance(self):
        """
        Get status display with balance information.
        
        Returns:
            str: Status with balance info
        """
        status = self.get_status_display()
        
        if self.is_budget_based():
            remaining = self.get_remaining_balance()
            if remaining is not None:
                return f"{status} (Balance: {remaining:,.0f})"
        
        return status
    
    # =========================================================================
    # META CLASS
    # =========================================================================
    
    class Meta:
        verbose_name = "Student Scholarship"
        verbose_name_plural = "Student Scholarships"
        ordering = ['-awarded_date']
        indexes = [
            models.Index(fields=['student', 'status']),
            models.Index(fields=['scholarship_program']),
            models.Index(fields=['status']),
            models.Index(fields=['start_date', 'end_date']),
            models.Index(fields=['use_category_specific_discounts']),  # ⭐ NEW
        ]
    
    # =========================================================================
    # STRING REPRESENTATION
    # =========================================================================
    
    def __str__(self):
        program_name = self.scholarship_program.name
        student_name = self.student.get_full_name()
        
        if self.is_category_specific():
            return f"{student_name} - {program_name} (Category-Specific)"
        elif self.is_policy_based():
            return f"{student_name} - {program_name} (Policy-Based)"
        elif self.is_budget_based():
            remaining = self.get_remaining_balance()
            return f"{student_name} - {program_name} (Balance: {remaining:,.0f})"
        else:
            return f"{student_name} - {program_name}"


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
    # HELPER METHODS TO GET ACCOUNTS FROM MAPPINGS
    # -------------------------------------------------------------------------
    
    def get_refund_account(self):
        """
        Get cash/bank account from which refund is paid.
        
        Returns:
            Account: Cash or bank account for refund payment
        """
        from core.models import FinancialSettings
        
        settings = FinancialSettings.get_instance()
        if not settings:
            return None
        
        mappings = settings.get_account_mappings()
        return mappings.get_cash_or_bank_account(self.payment_method)
    
    def get_receivable_account(self):
        """
        Get accounts receivable account to debit (for overpayment refunds).
        
        Returns:
            Account: Student receivables account
        """
        from core.models import FinancialSettings
        
        settings = FinancialSettings.get_instance()
        if not settings:
            return None
        
        mappings = settings.get_account_mappings()
        return mappings.student_receivables_account
    
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
    

