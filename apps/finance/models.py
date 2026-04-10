# finance/models.py

"""
Financial Management Models for School System

Comprehensive double-entry accounting system with:
- Chart of Accounts (Assets, Liabilities, Equity, Revenue, Expenses)
- Expense Management with approval workflows
- Journal Entries and Transactions
- Budget Planning and Tracking
- Financial Period Management

All business logic properly separated with utils.py integration

User tracking handled automatically by BaseModel
"""

from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.db.models import Sum, Q, Count, F, Max
from decimal import Decimal
from datetime import datetime, timedelta
import logging

from utils.models import BaseModel
from core.models import UnitOfMeasure, PaymentMethod, TaxRate, FinancialSettings, FiscalYear, FiscalPeriod
from academics.models import AcademicSession

logger = logging.getLogger(__name__)


# =============================================================================
# CHART OF ACCOUNTS SYSTEM
# =============================================================================

class AccountType(BaseModel):
    """Account type model for flexible chart of accounts"""
    
    ACCOUNT_TYPE_CHOICES = [
        ('ASSET', 'Asset'),
        ('LIABILITY', 'Liability'),
        ('EQUITY', 'Equity'),
        ('REVENUE', 'Revenue'),
        ('EXPENSE', 'Expense'),
    ]
    
    # -------------------------------------------------------------------------
    # BASIC INFORMATION
    # -------------------------------------------------------------------------
    
    name = models.CharField("Account Type Name", max_length=100)
    code = models.CharField("Account Type Code", max_length=20, unique=True, db_index=True)
    account_type = models.CharField(
        "Account Category", 
        max_length=10, 
        choices=ACCOUNT_TYPE_CHOICES,
        db_index=True
    )
    description = models.TextField("Description", blank=True)
    
    # -------------------------------------------------------------------------
    # BEHAVIORAL SETTINGS
    # -------------------------------------------------------------------------
    
    is_active = models.BooleanField("Is Active", default=True, db_index=True)
    requires_approval = models.BooleanField("Requires Approval by Default", default=False)
    allows_manual_entries = models.BooleanField("Allows Manual Journal Entries", default=True)
    
    # -------------------------------------------------------------------------
    # ACCOUNT NUMBERING
    # -------------------------------------------------------------------------
    
    number_prefix = models.CharField(
        "Account Number Prefix", 
        max_length=5, 
        blank=True,
        help_text="Prefix for auto-generated account numbers (e.g., '1' for Assets)"
    )
    next_number = models.IntegerField(
        "Next Account Number", 
        default=1,
        help_text="Next number to use for auto-generation"
    )
    
    # -------------------------------------------------------------------------
    # DISPLAY SETTINGS
    # -------------------------------------------------------------------------
    
    display_order = models.IntegerField("Display Order", default=1, db_index=True)
    icon = models.CharField(
        "Icon", 
        max_length=50, 
        blank=True,
        default="fa-folder",
        help_text="FontAwesome icon class or emoji for display"
    )
    color = models.CharField(
        "Color", 
        max_length=7, 
        blank=True,
        default="#6f42c1",
        help_text="Hex color code for charts/displays"
    )
    
    # -------------------------------------------------------------------------
    # BUSINESS RULES
    # -------------------------------------------------------------------------
    
    max_balance_limit = models.DecimalField(
        "Maximum Balance Limit",
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum allowed balance for accounts of this type"
    )

    normal_balance = models.CharField(
        "Normal Balance",
        max_length=6,
        choices=[
            ('DEBIT', 'Debit'),
            ('CREDIT', 'Credit'),
        ],
        default='DEBIT',
        help_text="Normal balance side for this account type"
    )
    
    affects_balance_sheet = models.BooleanField(
        "Affects Balance Sheet",
        default=True,
        help_text="Whether accounts of this type appear on balance sheet"
    )
    
    affects_income_statement = models.BooleanField(
        "Affects Income Statement",
        default=False,
        help_text="Whether accounts of this type appear on P&L statement"
    )
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Account Type"
        verbose_name_plural = "Account Types"
        ordering = ['account_type', 'display_order', 'name']
        indexes = [
            models.Index(fields=['account_type']),
            models.Index(fields=['is_active']),
            models.Index(fields=['display_order']),
            models.Index(fields=['code']),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.name} ({self.get_account_type_display()})"


class Account(BaseModel):
    """Individual accounts in the chart of accounts for school operations"""
    
    # -------------------------------------------------------------------------
    # CHOICE FIELDS - CATEGORIZATION
    # -------------------------------------------------------------------------
    
    BANK_ACCOUNT_TYPE_CHOICES = [
        ('SAVINGS', 'Savings Account'),
        ('CURRENT', 'Current Account'),
        ('FIXED_DEPOSIT', 'Fixed Deposit'),
        ('MONEY_MARKET', 'Money Market Account'),
        ('OTHER', 'Other'),
    ]
    
    MOBILE_MONEY_PROVIDER_CHOICES = [
        ('MTN', 'MTN Mobile Money'),
        ('AIRTEL', 'Airtel Money'),
        ('SAFARICOM', 'M-Pesa'),
        ('ORANGE', 'Orange Money'),
        ('OTHER', 'Other Provider'),
    ]
    
    RECEIVABLE_TYPE_CHOICES = [
        ('STUDENT', 'Student Fees'),
        ('STAFF', 'Staff Advances/Loans'),
        ('GOVERNMENT', 'Government Grants'),
        ('DONOR', 'Donor Funds'),
        ('OTHER', 'Other Receivables'),
    ]
    
    PAYABLE_TYPE_CHOICES = [
        ('SUPPLIERS', 'Suppliers'),
        ('STAFF_COMPENSATION', 'Staff Salaries and Benefits'),
        ('TAXES', 'Taxes and Government Dues'),
        ('UTILITIES', 'Utilities'),
        ('OTHER', 'Other Payables'),
    ]
    
    INVENTORY_TYPE_CHOICES = [
        ('UNIFORMS', 'School Uniforms'),
        ('BOOKS_STATIONERY', 'Books and Stationery'),
        ('FOOD_PROVISIONS', 'Food and Provisions'),
        ('MEDICAL', 'Medical Supplies'),
        ('EQUIPMENT', 'Equipment and Supplies'),
        ('SPORTS', 'Sports Equipment'),
        ('OTHER', 'Other Inventory'),
    ]
    
    ASSET_TYPE_CHOICES = [
        ('REAL_ESTATE', 'Land and Buildings'),
        ('FURNITURE_EQUIPMENT', 'Furniture and Equipment'),
        ('VEHICLES', 'Vehicles and Transport'),
        ('COMPUTER_EQUIPMENT', 'Computers and IT Equipment'),
        ('LIBRARY', 'Library Resources'),
        ('SPORTS_FACILITIES', 'Sports Facilities'),
        ('OTHER', 'Other Fixed Assets'),
    ]
    
    LIABILITY_TYPE_CHOICES = [
        ('STUDENT_DEPOSITS', 'Student Deposits and Prepayments'),
        ('STAFF_PAYABLE', 'Staff Payables'),
        ('SUPPLIER_PAYABLE', 'Supplier Payables'),
        ('TAX_PAYABLE', 'Tax Payables'),
        ('OTHER', 'Other Liabilities'),
    ]
    
    LOAN_TYPE_CHOICES = [
        ('BANK_LOAN', 'Bank Loan'),
        ('EQUIPMENT_FINANCING', 'Equipment Financing'),
        ('CONSTRUCTION_LOAN', 'Construction/Development Loan'),
        ('MORTGAGE', 'Mortgage'),
        ('OTHER', 'Other Loan'),
    ]
    
    EQUITY_TYPE_CHOICES = [
        ('RETAINED_EARNINGS', 'Retained Earnings'),
        ('CAPITAL', 'Capital/Initial Investment'),
        ('DEVELOPMENT_FUND', 'Development Fund'),
        ('RESERVE_FUND', 'Reserve Fund'),
        ('SCHOLARSHIP_FUND', 'Scholarship Fund'),
        ('OTHER', 'Other Equity'),
    ]
    
    REVENUE_TYPE_CHOICES = [
        ('TUITION', 'Tuition Fees'),
        ('BOARDING', 'Boarding Fees'),
        ('TRANSPORT', 'Transport Fees'),
        ('ACTIVITIES_SPORTS', 'Activities and Sports'),
        ('BOOKS_STATIONERY_SALES', 'Books and Stationery Sales'),
        ('UNIFORM_SALES', 'Uniform Sales'),
        ('GOVERNMENT_GRANTS', 'Government Grants'),
        ('DONATIONS', 'Donations'),
        ('INTEREST_INCOME', 'Interest Income'),
        ('OTHER_FEES', 'Other Fees'),
        ('OTHER', 'Other Revenue'),
    ]
    
    EXPENSE_TYPE_CHOICES = [
        ('TEACHING_SALARIES', 'Teaching Staff Salaries'),
        ('ADMIN_SALARIES', 'Administrative Staff Salaries'),
        ('STAFF_BENEFITS', 'Staff Benefits and Allowances'),
        ('UTILITIES', 'Utilities (Water, Electricity, etc.)'),
        ('MAINTENANCE_REPAIRS', 'Maintenance and Repairs'),
        ('SECURITY', 'Security Services'),
        ('CLEANING_SANITATION', 'Cleaning and Sanitation'),
        ('TEACHING_MATERIALS', 'Teaching Materials'),
        ('LIBRARY_MATERIALS', 'Library Materials'),
        ('IT_EXPENSES', 'IT Expenses'),
        ('FOOD_CATERING', 'Food and Catering'),
        ('BOARDING_SUPPLIES', 'Boarding Supplies'),
        ('VEHICLE_EXPENSES', 'Vehicle Expenses'),
        ('TRANSPORT_SERVICES', 'Transport Services'),
        ('OFFICE_SUPPLIES', 'Office Supplies'),
        ('COMMUNICATION', 'Communication'),
        ('PROFESSIONAL_FEES', 'Professional Fees'),
        ('INSURANCE', 'Insurance'),
        ('BANK_CHARGES', 'Bank Charges'),
        ('INTEREST_EXPENSE', 'Interest Expense'),
        ('BAD_DEBT', 'Bad Debt'),
        ('DEPRECIATION', 'Depreciation'),
        ('TAXES', 'Taxes and Levies'),
        ('SCHOLARSHIP', 'Scholarships and Financial Aid'),
        ('BURSARY', 'Bursaries and Grants'),
        ('FEE_DISCOUNT', 'Fee Discounts and Allowances'),
        ('MISCELLANEOUS', 'Miscellaneous Expenses'),
    ]
    
    # -------------------------------------------------------------------------
    # ACCOUNT IDENTIFICATION
    # -------------------------------------------------------------------------
    
    account_number = models.CharField("Account Number", max_length=20, unique=True, db_index=True)
    name = models.CharField("Account Name", max_length=100)
    description = models.TextField("Description", blank=True)
    account_type = models.ForeignKey(
        AccountType,
        verbose_name="Account Type",
        on_delete=models.PROTECT,
        related_name='accounts'
    )
    
    # -------------------------------------------------------------------------
    # ACCOUNT HIERARCHY
    # -------------------------------------------------------------------------
    
    parent_account = models.ForeignKey(
        'self',
        verbose_name="Parent Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='child_accounts',
        help_text="Parent account for hierarchical organization"
    )
    
    # -------------------------------------------------------------------------
    # BALANCE TRACKING
    # -------------------------------------------------------------------------
    
    current_balance = models.DecimalField(
        "Current Balance",
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Current account balance"
    )
    
    opening_balance = models.DecimalField(
        "Opening Balance",
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Opening balance when account was created"
    )
    
    # -------------------------------------------------------------------------
    # BANK ACCOUNT DETAILS
    # -------------------------------------------------------------------------
    
    is_bank_account = models.BooleanField("Is Bank Account", default=False, db_index=True)
    bank_name = models.CharField("Bank Name", max_length=100, blank=True)
    bank_branch = models.CharField("Bank Branch", max_length=100, blank=True)
    account_holder_name = models.CharField("Account Holder Name", max_length=100, blank=True)
    bank_account_number = models.CharField("Bank Account Number", max_length=50, blank=True)
    bank_account_type = models.CharField(
        "Bank Account Type",
        max_length=20,
        choices=BANK_ACCOUNT_TYPE_CHOICES,
        blank=True
    )
    bank_routing_number = models.CharField("Bank Routing Number", max_length=20, blank=True)
    bank_swift_code = models.CharField("SWIFT Code", max_length=11, blank=True)
    
    # -------------------------------------------------------------------------
    # CASH ACCOUNT DETAILS
    # -------------------------------------------------------------------------
    
    is_cash_account = models.BooleanField("Is Cash Account", default=False, db_index=True)
    cash_location = models.CharField("Cash Location", max_length=100, blank=True)
    responsible_person_id = models.CharField(
        "Responsible Person ID",
        max_length=50,
        blank=True,
        help_text="User ID of person responsible for this cash account"
    )
    
    # -------------------------------------------------------------------------
    # MOBILE MONEY DETAILS
    # -------------------------------------------------------------------------
    
    is_mobile_money_account = models.BooleanField("Is Mobile Money Account", default=False, db_index=True)
    mobile_money_provider = models.CharField(
        "Mobile Money Provider",
        max_length=20,
        choices=MOBILE_MONEY_PROVIDER_CHOICES,
        blank=True
    )
    mobile_number = models.CharField("Mobile Number", max_length=20, blank=True)
    mobile_account_name = models.CharField("Mobile Account Name", max_length=100, blank=True)
    
    # -------------------------------------------------------------------------
    # RECEIVABLE ACCOUNT DETAILS
    # -------------------------------------------------------------------------
    
    is_receivable_account = models.BooleanField(
        "Is Receivable Account", 
        default=False,
        db_index=True,
        help_text="Indicates if this account tracks money owed to the school"
    )
    receivable_type = models.CharField(
        "Receivable Type",
        max_length=20,
        choices=RECEIVABLE_TYPE_CHOICES,
        blank=True,
        help_text="Type of receivable (student fees, staff loans, etc.)"
    )
    
    # -------------------------------------------------------------------------
    # PAYABLE ACCOUNT DETAILS
    # -------------------------------------------------------------------------
    
    is_payable_account = models.BooleanField(
        "Is Payable Account", 
        default=False,
        db_index=True,
        help_text="Indicates if this account tracks money owed by the school"
    )
    payable_type = models.CharField(
        "Payable Type",
        max_length=30,
        choices=PAYABLE_TYPE_CHOICES,
        blank=True,
        help_text="Type of payable (suppliers, staff, taxes, etc.)"
    )
    
    # -------------------------------------------------------------------------
    # INVENTORY ACCOUNT DETAILS
    # -------------------------------------------------------------------------
    
    is_inventory_account = models.BooleanField(
        "Is Inventory Account", 
        default=False,
        db_index=True,
        help_text="Indicates if this account tracks physical inventory/stock"
    )
    inventory_type = models.CharField(
        "Inventory Type",
        max_length=20,
        choices=INVENTORY_TYPE_CHOICES,
        blank=True,
        help_text="Type of inventory tracked by this account"
    )
    
    # -------------------------------------------------------------------------
    # FIXED ASSET DETAILS
    # -------------------------------------------------------------------------
    
    is_fixed_asset = models.BooleanField(
        "Is Fixed Asset", 
        default=False,
        db_index=True,
        help_text="Indicates if this account tracks long-term physical assets"
    )
    asset_type = models.CharField(
        "Asset Type",
        max_length=30,
        choices=ASSET_TYPE_CHOICES,
        blank=True,
        help_text="Type of fixed asset (buildings, equipment, vehicles, etc.)"
    )
    
    # -------------------------------------------------------------------------
    # LIABILITY ACCOUNT DETAILS
    # -------------------------------------------------------------------------
    
    is_liability_account = models.BooleanField(
        "Is Liability Account", 
        default=False,
        db_index=True,
        help_text="Indicates if this account tracks general liabilities"
    )
    liability_type = models.CharField(
        "Liability Type",
        max_length=30,
        choices=LIABILITY_TYPE_CHOICES,
        blank=True,
        help_text="Type of liability"
    )
    
    # -------------------------------------------------------------------------
    # LOAN ACCOUNT DETAILS
    # -------------------------------------------------------------------------
    
    is_loan_account = models.BooleanField(
        "Is Loan Account", 
        default=False,
        db_index=True,
        help_text="Indicates if this account tracks loans and financing"
    )
    loan_type = models.CharField(
        "Loan Type",
        max_length=30,
        choices=LOAN_TYPE_CHOICES,
        blank=True,
        help_text="Type of loan or financing"
    )
    
    # -------------------------------------------------------------------------
    # EQUITY ACCOUNT DETAILS
    # -------------------------------------------------------------------------
    
    is_equity_account = models.BooleanField(
        "Is Equity Account", 
        default=False,
        db_index=True,
        help_text="Indicates if this account tracks equity/net assets"
    )
    equity_type = models.CharField(
        "Equity Type",
        max_length=30,
        choices=EQUITY_TYPE_CHOICES,
        blank=True,
        help_text="Type of equity account"
    )
    
    # -------------------------------------------------------------------------
    # REVENUE ACCOUNT DETAILS
    # -------------------------------------------------------------------------
    
    is_revenue_account = models.BooleanField(
        "Is Revenue Account", 
        default=False,
        db_index=True,
        help_text="Indicates if this account tracks income/revenue"
    )
    revenue_type = models.CharField(
        "Revenue Type",
        max_length=30,
        choices=REVENUE_TYPE_CHOICES,
        blank=True,
        help_text="Type of revenue stream"
    )
    
    # -------------------------------------------------------------------------
    # EXPENSE ACCOUNT DETAILS
    # -------------------------------------------------------------------------
    
    is_expense_account = models.BooleanField(
        "Is Expense Account", 
        default=False,
        db_index=True,
        help_text="Indicates if this account tracks operational expenses"
    )
    expense_type = models.CharField(
        "Expense Type",
        max_length=30,
        choices=EXPENSE_TYPE_CHOICES,
        blank=True,
        help_text="Category of expense tracked by this account"
    )
    
    # -------------------------------------------------------------------------
    # ACCOUNT SETTINGS
    # -------------------------------------------------------------------------
    
    is_active = models.BooleanField("Is Active", default=True, db_index=True)

    # ✅ ADD THIS FIELD
    is_header = models.BooleanField(
        "Is Header Account",
        default=False,
        db_index=True,
        help_text="Header accounts are used for grouping only and cannot have transactions posted to them"
    )
    requires_approval = models.BooleanField(
        "Requires Approval",
        null=True,
        blank=True,
        help_text="Leave blank to use account type default"
    )
    daily_limit = models.DecimalField(
        "Daily Transaction Limit",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum daily transaction amount (leave blank for no limit)"
    )
    
    # -------------------------------------------------------------------------
    # RECONCILIATION
    # -------------------------------------------------------------------------
    
    is_reconcilable = models.BooleanField("Is Reconcilable", default=True)
    last_reconciled_date = models.DateField("Last Reconciled Date", null=True, blank=True)
    reconciliation_balance = models.DecimalField(
        "Reconciliation Balance",
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Balance as per last reconciliation"
    )
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Account"
        verbose_name_plural = "Accounts"
        ordering = ['account_type__account_type', 'account_number']
        indexes = [
            models.Index(fields=['account_number']),
            models.Index(fields=['account_type']),
            models.Index(fields=['is_active']),
            models.Index(fields=['is_header']),
            models.Index(fields=['is_bank_account']),
            models.Index(fields=['is_cash_account']),
            models.Index(fields=['is_mobile_money_account']),
            models.Index(fields=['is_receivable_account']),
            models.Index(fields=['is_payable_account']),
            models.Index(fields=['is_inventory_account']),
            models.Index(fields=['is_fixed_asset']),
            models.Index(fields=['is_liability_account']),
            models.Index(fields=['is_loan_account']),
            models.Index(fields=['is_equity_account']),
            models.Index(fields=['is_revenue_account']),
            models.Index(fields=['is_expense_account']),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.account_number} - {self.name}"
    
    # -------------------------------------------------------------------------
    # HELPER METHODS
    # -------------------------------------------------------------------------
    
    def get_responsible_person(self):
        """Get the user responsible for this cash account"""
        if not self.responsible_person_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            return User.objects.using('default').get(id=self.responsible_person_id)
        except Exception as e:
            logger.error(f"Error fetching responsible person: {e}")
            return None
    
    def get_account_category(self):
        """Get the specific category of this account"""
        if self.is_cash_account:
            return 'cash'
        elif self.is_bank_account:
            return 'bank'
        elif self.is_mobile_money_account:
            return 'mobile_money'
        elif self.is_receivable_account:
            return 'receivable'
        elif self.is_payable_account:
            return 'payable'
        elif self.is_inventory_account:
            return 'inventory'
        elif self.is_fixed_asset:
            return 'fixed_asset'
        elif self.is_liability_account:
            return 'liability'
        elif self.is_loan_account:
            return 'loan'
        elif self.is_equity_account:
            return 'equity'
        elif self.is_revenue_account:
            return 'revenue'
        elif self.is_expense_account:
            return 'expense'
        else:
            return 'general'
    
    def get_category_display(self):
        """Get human-readable category display"""
        category_map = {
            'cash': 'Cash Account',
            'bank': 'Bank Account',
            'mobile_money': 'Mobile Money',
            'receivable': 'Receivable',
            'payable': 'Payable',
            'inventory': 'Inventory',
            'fixed_asset': 'Fixed Asset',
            'liability': 'Liability',
            'loan': 'Loan',
            'equity': 'Equity',
            'revenue': 'Revenue',
            'expense': 'Expense',
            'general': 'General Account',
        }
        return category_map.get(self.get_account_category(), 'General Account')
    
    @property
    def icon(self):
        """Get appropriate icon based on account type"""
        if self.is_cash_account:
            return 'fa-money-bill-wave'
        elif self.is_bank_account:
            return 'fa-university'
        elif self.is_mobile_money_account:
            return 'fa-mobile-alt'
        elif self.is_receivable_account:
            return 'fa-receipt'
        elif self.is_payable_account:
            return 'fa-file-invoice'
        elif self.is_inventory_account:
            return 'fa-boxes'
        elif self.is_fixed_asset:
            return 'fa-building'
        elif self.is_liability_account:
            return 'fa-balance-scale'
        elif self.is_loan_account:
            return 'fa-hand-holding-usd'
        elif self.is_equity_account:
            return 'fa-landmark'
        elif self.is_revenue_account:
            return 'fa-dollar-sign'
        elif self.is_expense_account:
            return 'fa-file-invoice-dollar'
        else:
            return 'fa-folder'


# =============================================================================
# EXPENSE MANAGEMENT MODELS
# =============================================================================

class ExpenseCategory(BaseModel):
    """Categories for organizing expenses"""
    
    CATEGORY_TYPE_CHOICES = [
        ('ADMINISTRATIVE', 'Administrative'),
        ('ACADEMIC', 'Academic Resources'),
        ('SCHOLASTIC', 'Scholastic Materials'),
        ('EXAMINATION', 'Examination Materials'),
        ('FACILITIES', 'Facilities & Maintenance'),
        ('UTILITIES', 'Utilities'),
        ('TRANSPORT', 'Transport'),
        ('MEALS', 'Meals & Catering'),
        ('STAFF', 'Staff Salaries & Benefits'),
        ('MEDICAL', 'Medical & Health Services'),
        ('SPORTS', 'Sports & Physical Education'),
        ('STUDENT_SERVICES', 'Student Welfare & Services'),
        ('PTA', 'Parent-Teacher Association'),
        ('MARKETING', 'Marketing & Promotion'),
        ('TECHNOLOGY', 'Technology & IT'),
        ('LEGAL', 'Legal & Professional Services'),
        ('CAPITAL', 'Capital Expenditure'),
        ('FINANCIAL', 'Financial Expenses'),
        ('INSURANCE', 'Insurance & Risk Management'),
        ('TAX', 'Taxes & Compliance'),
        ('DRAWINGS', 'Owner Drawings & Distributions'),
        ('DEPRECIATION', 'Depreciation & Amortization'),
        ('CHARITY', 'Charity & Social Support'),
        ('MISCELLANEOUS', 'Miscellaneous & Emergency'),
        ('OTHER', 'Other Expenses'),
    ]
    
    # -------------------------------------------------------------------------
    # BASIC INFORMATION
    # -------------------------------------------------------------------------
    
    name = models.CharField("Category Name", max_length=100)
    category_type = models.CharField("Category Type", max_length=20, choices=CATEGORY_TYPE_CHOICES, db_index=True)
    description = models.TextField("Description", blank=True)
    
    # -------------------------------------------------------------------------
    # DEFAULT ACCOUNT
    # -------------------------------------------------------------------------
    
    default_expense_account = models.ForeignKey(
        Account,
        verbose_name="Default Expense Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='expense_categories'
    )
    
    # -------------------------------------------------------------------------
    # APPROVAL REQUIREMENTS
    # -------------------------------------------------------------------------
    
    requires_approval = models.BooleanField("Requires Approval", default=True)
    approval_limit = models.DecimalField(
        "Approval Limit",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Amount above which approval is required"
    )
    
    is_active = models.BooleanField("Is Active", default=True, db_index=True)
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Expense Category"
        verbose_name_plural = "Expense Categories"
        ordering = ['category_type', 'name']
        indexes = [
            models.Index(fields=['category_type']),
            models.Index(fields=['is_active']),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.name} ({self.get_category_type_display()})"


class Expense(BaseModel):
    """
    Main expense tracking model with approval workflow.

    FIELD DESIGN NOTES
    ──────────────────
    expense_date    → auto-set by expense_pre_save signal via get_school_today()
                      if not supplied. Not shown in the create form.

    fiscal_period   → auto-set by expense_pre_save signal via
                      FiscalPeriod.get_current_fiscal_period() if not supplied.
                      Not shown in the create form.

    academic_session→ intentionally omitted. Accessible via:
                          expense.fiscal_period.related_academic_session
                      Storing it again would be redundant denormalisation.

    expense_account → auto-assigned from category.default_expense_account.
                      Shown in the form at header level but hidden by JS when
                      line items exist (QuickBooks pattern).

    subtotal_amount → sum of all ExpenseLine.amount values.
                      Set automatically by the ExpenseLine post_save signal.
                      Never user-entered.

    tax_amount      → entered manually by the accountant at header level.
                      Optional. Not derived from lines.

    total_amount    → subtotal_amount + tax_amount.
                      Set automatically by the ExpenseLine post_save signal.
                      Never user-entered.

    auto_create_journal_entry → removed. Journal entry creation is
                      unconditional — every approved expense posts to the
                      ledger. No legitimate reason to skip this.

    is_recurring    → removed. No automation exists to act on it yet.
                      Re-add when recurring expense generation is built.

    processing_fee  → intentionally omitted. Belongs on ExpensePayment,
                      not on the Expense record itself.

    PAYEE
    ─────
    Replaces the old vendor_name / vendor_contact / vendor_reference fields.
    Not every expense has a vendor — a worker receiving transport allowance,
    petty cash for a boda boda, or lunch for staff during an event have no
    identifiable supplier. payee_type captures who received the money;
    payee_name captures their name; vendor_reference remains for invoice/
    receipt numbers when applicable.

    LINE ITEM POLICY
    ────────────────
    At least one ExpenseLine is always required. Staff pick a category,
    then itemise every purchase under that category — even if it is a
    single item. This ensures a full audit trail and accurate GL posting.
    The formset enforces this via ExpenseLineFormSet.clean().
    """

    STATUS_CHOICES = [
        ('DRAFT',            'Draft'),
        ('PENDING_APPROVAL', 'Pending Approval'),
        ('APPROVED',         'Approved'),
        ('PAID',             'Paid'),
        ('REJECTED',         'Rejected'),
        ('CANCELLED',        'Cancelled'),
    ]

    PAYEE_TYPE_CHOICES = [
        ('SUPPLIER', 'Supplier / Vendor'),
        ('STAFF',    'Staff Member'),
        ('PETTY',    'Petty Cash'),
        ('OTHER',    'Other'),
    ]

    # ── Identification ────────────────────────────────────────────────────────

    expense_number = models.CharField(
        "Expense Number",
        max_length=50,
        unique=True,
        db_index=True,
        help_text="Auto-generated by signal on save",
    )

    # ── Basic Details ─────────────────────────────────────────────────────────

    expense_date = models.DateField(
        "Expense Date",
        db_index=True,
        help_text="Auto-set to school today by signal if not supplied",
    )

    description = models.CharField(
        "Description",
        max_length=255,
        help_text="One-line title e.g. 'Electricity bill — January'",
    )

    category = models.ForeignKey(
        ExpenseCategory,
        verbose_name="Category",
        on_delete=models.PROTECT,
        related_name='expenses',
        help_text="All line items belong to this category",
    )

    # ── Fiscal Context ────────────────────────────────────────────────────────
    # Academic session → expense.fiscal_period.related_academic_session

    fiscal_period = models.ForeignKey(
        FiscalPeriod,
        verbose_name="Fiscal Period",
        on_delete=models.PROTECT,
        related_name='expenses',
        help_text="Auto-set to current open period by signal if not supplied",
    )

    # ── Financial Totals (all signal-maintained) ──────────────────────────────

    subtotal_amount = models.DecimalField(
        "Subtotal Amount",
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Sum of all line amounts — updated by ExpenseLine signal",
    )

    tax_amount = models.DecimalField(
        "Tax Amount",
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Optional header-level tax — entered manually by accountant",
    )

    total_amount = models.DecimalField(
        "Total Amount",
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="subtotal_amount + tax_amount — updated by ExpenseLine signal",
    )

    # ── GL Account ────────────────────────────────────────────────────────────

    expense_account = models.ForeignKey(
        Account,
        verbose_name="Expense Account",
        on_delete=models.PROTECT,
        related_name='charged_expenses',
        null=True,
        blank=True,
        help_text=(
            "Header-level GL account — auto-assigned from category. "
            "Ignored when line items exist (per-line accounts take over)."
        ),
    )

    # ── Payment Details ───────────────────────────────────────────────────────

    preferred_payment_method = models.ForeignKey(
        PaymentMethod,
        verbose_name="Preferred Payment Method",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='preferred_expenses',
    )

    # ── Payee ─────────────────────────────────────────────────────────────────
    # Replaces vendor_name / vendor_contact. Not every expense has a vendor —
    # transport allowances, petty cash, and staff reimbursements go to people,
    # not suppliers.

    payee_type = models.CharField(
        "Payee Type",
        max_length=10,
        choices=PAYEE_TYPE_CHOICES,
        default='SUPPLIER',
        blank=True,
        db_index=True,
    )

    payee_name = models.CharField(
        "Payee Name",
        max_length=200,
        blank=True,
        help_text="Supplier name, staff member name, or leave blank for petty cash",
    )

    payee_contact = models.CharField(
        "Payee Contact",
        max_length=100,
        blank=True,
        help_text="Phone or email — optional",
    )

    vendor_reference = models.CharField(
        "Vendor Invoice / Reference",
        max_length=100,
        blank=True,
        help_text="Supplier invoice number or receipt reference — optional",
    )

    # ── Budget Tracking ───────────────────────────────────────────────────────

    budget_line = models.ForeignKey(
        'BudgetLine',
        verbose_name="Budget Line",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='expenses',
        help_text="Budget line this expense is charged against",
    )

    budget_override_reason = models.TextField(
        "Budget Override Reason",
        blank=True,
        help_text="Required if expense exceeds budget limit",
    )

    # ── Status & Approval ─────────────────────────────────────────────────────

    status = models.CharField(
        "Status",
        max_length=20,
        choices=STATUS_CHOICES,
        default='DRAFT',
        db_index=True,
    )

    # User IDs stored as CharField — users live in the default DB,
    # not the per-school DB, so FK references are not possible.
    requested_by_id = models.CharField("Requested By ID", max_length=50, null=True, blank=True)
    approved_by_id  = models.CharField("Approved By ID",  max_length=50, null=True, blank=True)
    approval_date   = models.DateTimeField("Approval Date",  null=True, blank=True)
    approval_notes  = models.TextField("Approval Notes", blank=True)

    # ── Rejection ─────────────────────────────────────────────────────────────

    rejection_reason = models.TextField("Rejection Reason", blank=True)
    rejected_by_id   = models.CharField("Rejected By ID", max_length=50, null=True, blank=True)
    rejection_date   = models.DateTimeField("Rejection Date", null=True, blank=True)

    # ── Supporting Documentation ──────────────────────────────────────────────

    receipt_image = models.ImageField(
        "Receipt Image",
        upload_to='expense_receipts/',
        blank=True,
        null=True,
    )

    notes = models.TextField(
        "Notes",
        blank=True,
        help_text=(
            "Free-text context for the whole expense — verbal approvals, "
            "delivery notes, references, etc."
        ),
    )

    # ── Journal Entry Integration ─────────────────────────────────────────────

    journal_entry = models.ForeignKey(
        'JournalEntry',
        verbose_name="Journal Entry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='expenses',
        help_text="Journal entry created automatically when expense is approved",
    )

    # ── Meta ──────────────────────────────────────────────────────────────────

    class Meta:
        verbose_name        = "Expense"
        verbose_name_plural = "Expenses"
        ordering            = ['-expense_date', '-created_at']
        indexes = [
            models.Index(fields=['expense_number']),
            models.Index(fields=['expense_date']),
            models.Index(fields=['status']),
            models.Index(fields=['category']),
            models.Index(fields=['fiscal_period']),
            models.Index(fields=['payee_type']),
        ]

    def __str__(self):
        return f"{self.expense_number} - {self.description}"

    # ── Account resolution ────────────────────────────────────────────────────

    def get_expense_account(self):
        """
        Resolve the GL expense account for this expense.

        Resolution order:
        1. Explicitly set header-level account (expense_account field)
        2. Category's default_expense_account (wired at school initialisation)
        3. CoreAccountMappings fallback
        """
        if self.expense_account_id:
            return self.expense_account

        if self.category_id and self.category.default_expense_account_id:
            return self.category.default_expense_account

        try:
            from core.models import FinancialSettings
            settings = FinancialSettings.get_instance()
            if settings:
                return settings.get_account_mappings().get_expense_account(self.category)
        except Exception as e:
            logger.error(f"Expense.get_expense_account: {e}")

        return None

    def get_payable_account(self):
        """Return the accounts-payable account from CoreAccountMappings."""
        try:
            from core.models import FinancialSettings
            settings = FinancialSettings.get_instance()
            if settings:
                return settings.get_account_mappings().default_payable_account
        except Exception as e:
            logger.error(f"Expense.get_payable_account: {e}")
        return None

    # ── User helpers ──────────────────────────────────────────────────────────

    def _get_user(self, user_id, label):
        if not user_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            return get_user_model().objects.using('default').get(id=user_id)
        except Exception as e:
            logger.error(f"Expense.{label}: {e}")
            return None

    def get_requested_by_user(self):
        return self._get_user(self.requested_by_id, 'get_requested_by_user')

    def get_approved_by_user(self):
        return self._get_user(self.approved_by_id, 'get_approved_by_user')

    def get_rejected_by_user(self):
        return self._get_user(self.rejected_by_id, 'get_rejected_by_user')


# =============================================================================

def get_default_uom():
    from core.models import UnitOfMeasure
    return UnitOfMeasure.objects.get(name="Each").id

class ExpenseLine(BaseModel):
    """
    Individual line item within an expense.
 
    FIELD DESIGN NOTES
    ──────────────────
    description  → required. Staff must describe what was purchased
                   on every line — e.g. "Box of chalk", "Ream of paper".
 
    unit_of_measure → required. Every quantity must have a unit.
                   The UoM list covers all school scenarios including
                   service units (hour, day, trip) for non-goods expenses.
 
    amount       → calculated as quantity × unit_price.
                   Set server-side in ExpenseLineForm.clean() and drives the
                   Expense.subtotal_amount + Expense.total_amount via
                   post_save signal. The form field is readonly in the UI.
 
    tax_rate /
    tax_amount   → intentionally omitted. Per-line tax is an AP/VAT-recovery
                   feature not applicable in a Ugandan school context.
                   Use Expense.tax_amount for any header-level tax notation.
 
    expense_account → REMOVED. All lines within an expense belong to the
                   same category, so the GL account is resolved once at
                   the Expense level via Expense.get_expense_account():
                     1. expense.expense_account  (if explicitly set)
                     2. category.default_expense_account
                     3. FinancialSettings fallback
                   That single account is what posts to the journal debit side.
                   Showing it per-line was redundant and misleading.
    """
 
    # ── Relationships ─────────────────────────────────────────────────────────
 
    expense = models.ForeignKey(
        Expense,
        verbose_name="Expense",
        on_delete=models.CASCADE,
        related_name='lines',
    )
 
    # ── Line Item Details ─────────────────────────────────────────────────────
 
    description = models.CharField(
        "Line Description",
        max_length=255,
        help_text="What was purchased — e.g. 'Box of chalk', 'Boda fare to market'",
    )
 
    quantity = models.DecimalField(
        "Quantity",
        max_digits=10,
        decimal_places=2,
        default=Decimal('1.00'),
    )
 
    unit_of_measure = models.ForeignKey(
        UnitOfMeasure,
        verbose_name="Unit of Measure",
        on_delete=models.PROTECT,
        default=get_default_uom,
        help_text="Unit for the quantity — e.g. box, ream, hour, day, trip",
    )
 
    unit_price = models.DecimalField(
        "Unit Price",
        max_digits=12,
        decimal_places=2,
    )
 
    amount = models.DecimalField(
        "Line Amount",
        max_digits=12,
        decimal_places=2,
        help_text="quantity × unit_price — set by form clean() and signal, not user-entered",
    )
 
    # ── Meta ──────────────────────────────────────────────────────────────────
 
    class Meta:
        verbose_name        = "Expense Line"
        verbose_name_plural = "Expense Lines"
        ordering            = ['expense', 'id']
 
    def __str__(self):
        return f"{self.expense.expense_number} — {self.description}"


class ExpensePayment(BaseModel):
    """
    Expense payment tracking with automatic journal entries and reversal support.

    KEY CONCEPTS
    ─────────────
    REVERSAL: Internal correction when payment was entered incorrectly.
    Reversed payments are kept for audit trail but don't affect balances.
    Cannot delete expense payments — only reverse them.
    Journal entries are never deleted — reversing entries are created instead.

    CURRENCY
    ─────────
    currency                  — ISO 4217 code the payment was made in.
                                Blank = school's primary currency.
    exchange_rate             — Rate to school currency at time of payment.
                                Stored permanently — never recalculated.
    amount_in_school_currency — amount × exchange_rate.
                                This is what posts to the journal and ledger.
                                Use this for all aggregations across payments.

    Example (South Sudan school paying Ugandan supplier):
        amount                    = 1,500,000  (UGX — what was actually paid)
        currency                  = 'UGX'
        exchange_rate             = 850.000000  (UGX per SSD on that day)
        amount_in_school_currency = 1,764.71    (SSD — what hits the books)
    """

    STATUS_CHOICES = [
        ('PENDING',    'Pending'),
        ('PROCESSING', 'Processing'),
        ('PROCESSED',  'Processed'),
        ('VERIFIED',   'Verified'),
        ('FAILED',     'Failed'),
        ('CANCELLED',  'Cancelled'),
        ('REVERSED',   'Reversed'),
    ]

    # =========================================================================
    # BASIC PAYMENT INFORMATION
    # =========================================================================

    expense = models.ForeignKey(
        Expense,
        verbose_name="Expense",
        on_delete=models.CASCADE,
        related_name='payments',
    )

    payment_date = models.DateField(
        "Payment Date",
        default=timezone.now,
        db_index=True,
        help_text="Date when payment was made",
    )

    amount = models.DecimalField(
        "Payment Amount",
        max_digits=15,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Amount paid in payment currency",
    )

    # =========================================================================
    # CURRENCY
    # =========================================================================

    currency = models.CharField(
        "Currency",
        max_length=3,
        blank=True,
        help_text=(
            "Currency this payment was made in. "
            "Blank = school's primary currency. "
            "Example: 'UGX' for a South Sudan school paying a Ugandan supplier."
        ),
    )

    exchange_rate = models.DecimalField(
        "Exchange Rate",
        max_digits=12,
        decimal_places=6,
        default=Decimal('1.000000'),
        help_text=(
            "Rate between payment currency and school currency at time of payment. "
            "Stored permanently — never recalculated after saving."
        ),
    )

    amount_in_school_currency = models.DecimalField(
        "Amount in School Currency",
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=(
            "amount × exchange_rate. "
            "This is what posts to the journal and ledger. "
            "Use this field for all aggregations across payments."
        ),
    )

    # =========================================================================
    # FISCAL CONTEXT
    # =========================================================================

    fiscal_period = models.ForeignKey(
        FiscalPeriod,
        verbose_name="Fiscal Period",
        on_delete=models.PROTECT,
        related_name='expense_payments',
        help_text="Fiscal period when payment was made",
    )

    # =========================================================================
    # PAYMENT METHOD AND ACCOUNT DETAILS
    # =========================================================================

    payment_method = models.ForeignKey(
        PaymentMethod,
        verbose_name="Payment Method",
        on_delete=models.PROTECT,
        related_name='expense_payments',
        help_text="Method used for this payment",
    )

    account = models.ForeignKey(
        Account,
        verbose_name="Payment Account",
        on_delete=models.PROTECT,
        related_name='expense_payments',
        help_text="Account from which payment was made",
    )

    # =========================================================================
    # FEES AND CHARGES
    # =========================================================================

    processing_fee = models.DecimalField(
        "Processing Fee",
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Fee charged by payment method",
    )

    processing_fee_account = models.ForeignKey(
        Account,
        verbose_name="Processing Fee Account",
        on_delete=models.PROTECT,
        related_name='expense_processing_fees',
        null=True, blank=True,
        help_text="Expense account for payment processing fees",
    )

    bank_charges = models.DecimalField(
        "Bank Charges",
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Additional bank charges not included in processing fee",
    )

    # =========================================================================
    # PAYMENT REFERENCES AND TRACKING
    # =========================================================================

    reference_number = models.CharField(
        "Reference Number", max_length=100, blank=True, db_index=True,
        help_text="Bank reference, mobile money ref, etc.",
    )

    transaction_id = models.CharField(
        "Transaction ID", max_length=100, blank=True, db_index=True,
        help_text="External transaction identifier",
    )

    batch_number = models.CharField(
        "Batch Number", max_length=50, blank=True, db_index=True,
        help_text="Batch number for grouped vendor payments",
    )

    check_number = models.CharField(
        "Check/Cheque Number", max_length=20, blank=True,
    )

    payment_details = models.JSONField(
        "Payment Details", default=dict, blank=True,
        help_text="Additional payment method specific details (JSON)",
    )

    receipt_number = models.CharField(
        "Receipt Number", max_length=50, blank=True,
        help_text="Receipt number from vendor/supplier",
    )

    # =========================================================================
    # STATUS AND WORKFLOW
    # =========================================================================

    status = models.CharField(
        "Status", max_length=10, choices=STATUS_CHOICES, default='PENDING', db_index=True,
    )

    performed_by = models.CharField(
        "Performed By", max_length=100, default='System',
    )

    performed_by_user_id = models.CharField(
        "Performed By User ID", max_length=50, null=True, blank=True,
    )

    processed_date = models.DateTimeField("Processed Date", null=True, blank=True)

    # =========================================================================
    # VERIFICATION
    # =========================================================================

    is_verified = models.BooleanField("Verified", default=False, db_index=True)

    verified_by_id = models.CharField(
        "Verified By ID", max_length=50, null=True, blank=True,
    )

    verification_date    = models.DateTimeField("Verification Date",  null=True, blank=True)
    verification_notes   = models.TextField("Verification Notes",     blank=True)

    # =========================================================================
    # REVERSAL TRACKING
    # =========================================================================

    reversed = models.BooleanField(
        "Reversed", default=False, db_index=True,
        help_text=(
            "Payment was reversed due to internal error — wrong vendor, duplicate "
            "entry, wrong amount. Accounting correction only, no actual money movement."
        ),
    )

    reversed_on    = models.DateTimeField("Reversed On",    null=True, blank=True)
    reversed_by_id = models.CharField("Reversed By ID",    max_length=50, null=True, blank=True)

    reversal_reason = models.TextField(
        "Reversal Reason", blank=True,
        help_text=(
            "Detailed reason: 'Duplicate payment entry', 'Posted to wrong expense', "
            "'Incorrect vendor', 'Wrong amount entered'"
        ),
    )

    reversal_journal_entry = models.ForeignKey(
        'JournalEntry',
        verbose_name="Reversal Journal Entry",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='reversed_expense_payments',
        help_text="Journal entry created when payment was reversed",
    )

    reversal_approval_required  = models.BooleanField("Reversal Approval Required", default=True)
    reversal_approved_by_id     = models.CharField("Reversal Approved By ID", max_length=50, null=True, blank=True)
    reversal_approved_on        = models.DateTimeField("Reversal Approved On", null=True, blank=True)

    # =========================================================================
    # JOURNAL ENTRY INTEGRATION
    # =========================================================================

    journal_entry = models.ForeignKey(
        'JournalEntry',
        verbose_name="Journal Entry",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='expense_payments',
        help_text="Journal entry created for this payment (DR: Payables, CR: Cash/Bank)",
    )

    notes          = models.TextField("Notes",          blank=True)
    internal_notes = models.TextField("Internal Notes", blank=True)

    # =========================================================================
    # ACCOUNT MAPPING HELPERS
    # =========================================================================

    def get_payment_account(self):
        return self.account

    def get_payable_account(self):
        if hasattr(self.expense, 'get_payable_account'):
            return self.expense.get_payable_account()
        from core.models import FinancialSettings
        settings = FinancialSettings.get_instance()
        if not settings:
            return None
        return settings.get_account_mappings().default_payable_account

    def get_processing_fee_account(self):
        # FIX: replaced fragile getattr chain on OneToOne reverse with
        # explicit try/except — if special_account_mappings is not configured
        # the getattr previously swallowed the DoesNotExist silently.
        if self.processing_fee_account:
            return self.processing_fee_account
        from core.models import FinancialSettings
        settings = FinancialSettings.get_instance()
        if not settings:
            return None
        try:
            return settings.special_account_mappings.payment_processing_fee_account
        except Exception:
            return settings.get_account_mappings().default_expense_account

    # =========================================================================
    # VALIDATION
    # =========================================================================

    def clean(self):
        super().clean()
        errors = {}

        if self.reversed and not self.reversal_reason:
            errors['reversal_reason'] = "Reversal reason is required for reversed payments."

        if self.amount < 0:
            errors['amount'] = "Payment amount cannot be negative."

        if self.processing_fee < 0:
            errors['processing_fee'] = "Processing fee cannot be negative."

        if self.bank_charges < 0:
            errors['bank_charges'] = "Bank charges cannot be negative."

        if self.exchange_rate is not None and self.exchange_rate <= 0:
            errors['exchange_rate'] = "Exchange rate must be greater than zero."

        if self.reversed and self.status in ['FAILED', 'CANCELLED']:
            errors['reversed'] = f"Cannot reverse a {self.status.lower()} payment."

        if errors:
            raise ValidationError(errors)

    # =========================================================================
    # STATUS PROPERTIES
    # =========================================================================

    @property
    def is_active(self):
        """True if payment is not reversed — counts toward expense payment totals."""
        return not self.reversed

    @property
    def effective_amount(self):
        """
        Effective amount in school currency. Zero if reversed.
        Use this for all aggregations — not amount, which may be in foreign currency.
        """
        return Decimal('0.00') if self.reversed else self.amount_in_school_currency

    @property
    def effective_amount_original(self):
        """Effective amount in payment currency. Zero if reversed."""
        return Decimal('0.00') if self.reversed else self.amount

    @property
    def total_amount_including_fees(self):
        """Total disbursement including processing fee and bank charges."""
        return self.amount + self.processing_fee + self.bank_charges

    @property
    def payment_state(self):
        if self.reversed:
            return "REVERSED"
        if self.status == 'VERIFIED' and self.is_verified:
            return "ACTIVE"
        return self.status

    def can_be_reversed(self):
        if self.reversed:
            return False, "Payment already reversed"
        if self.status in ['FAILED', 'CANCELLED']:
            return False, f"Cannot reverse {self.status.lower()} payment"
        if self.fiscal_period and getattr(self.fiscal_period, 'is_closed', False):
            return False, "Cannot reverse payment from closed fiscal period"
        if self.reversal_approval_required and not self.reversal_approved_by_id:
            return False, "Reversal requires manager approval"
        return True, "OK"

    def requires_reversal_approval(self):
        APPROVAL_THRESHOLD = Decimal('1000000.00')
        return self.is_verified or self.amount >= APPROVAL_THRESHOLD

    # =========================================================================
    # USER RETRIEVAL HELPERS
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

    def get_performed_by_user(self):        return self._get_user(self.performed_by_user_id)
    def get_verified_by_user(self):         return self._get_user(self.verified_by_id)
    def get_reversed_by_user(self):         return self._get_user(self.reversed_by_id)
    def get_reversal_approved_by_user(self):return self._get_user(self.reversal_approved_by_id)

    # =========================================================================
    # AUDIT TRAIL
    # =========================================================================

    def get_audit_trail(self):
        trail = []

        trail.append({
            'action':    'CREATED',
            'timestamp': self.created_at,
            # FIX: was self.get_created_by_user() — method does not exist on
            # BaseModel. Corrected to self.get_created_by().
            'user':      self.get_created_by(),
            'details':   (
                f"Payment {self.reference_number} created — "
                f"{self.amount:,.2f} {self.currency or 'school currency'}"
                + (
                    f" ({self.amount_in_school_currency:,.2f} school currency "
                    f"at rate {self.exchange_rate})"
                    if self.currency and self.currency != ''
                    else ''
                )
            ),
        })

        if self.processed_date:
            trail.append({
                'action':    'PROCESSED',
                'timestamp': self.processed_date,
                'user':      self.get_performed_by_user(),
                'details':   f"Payment processed by {self.performed_by}",
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
                'details':   f"Journal Entry {self.journal_entry.entry_number} created",
            })

        if self.reversal_approved_by_id and self.reversal_approved_on:
            trail.append({
                'action':    'REVERSAL_APPROVED',
                'timestamp': self.reversal_approved_on,
                'user':      self.get_reversal_approved_by_user(),
                'details':   "Reversal approved by manager",
            })

        if self.reversed and self.reversed_on:
            trail.append({
                'action':    'REVERSED',
                'timestamp': self.reversed_on,
                'user':      self.get_reversed_by_user(),
                'details':   f"Payment reversed: {self.reversal_reason}",
            })
            if self.reversal_journal_entry:
                trail.append({
                    'action':    'REVERSAL_JOURNAL_ENTRY',
                    'timestamp': self.reversal_journal_entry.created_at,
                    'details':   f"Reversal Journal Entry {self.reversal_journal_entry.entry_number} created",
                })

        trail.sort(key=lambda x: x['timestamp'])
        return trail

    # =========================================================================
    # EXPENSE STATUS HELPER
    # =========================================================================

    def update_expense_status(self):
        """Update parent expense status based on active payments."""
        try:
            total_paid = sum(
                p.amount_in_school_currency
                for p in self.expense.payments.all()
                if p.is_active
            )
            self.expense.status = 'PAID' if total_paid >= self.expense.total_amount else 'APPROVED'
            self.expense.save(update_fields=['status'])
        except Exception as e:
            logger.error(f"Error updating expense status: {e}", exc_info=True)

    # =========================================================================
    # META
    # =========================================================================

    class Meta:
        verbose_name = "Expense Payment"
        verbose_name_plural = "Expense Payments"
        ordering = ['-payment_date', '-created_at']

        indexes = [
            models.Index(fields=['payment_date', 'status']),
            models.Index(fields=['reference_number']),
            models.Index(fields=['transaction_id']),
            models.Index(fields=['batch_number']),
            models.Index(fields=['is_verified']),
            models.Index(fields=['expense', 'payment_date']),
            models.Index(fields=['fiscal_period']),
            models.Index(fields=['reversed']),
            models.Index(fields=['reversed_on']),
            models.Index(fields=['reversal_approved_by_id']),
            models.Index(fields=['currency']),
        ]

        constraints = [
            models.CheckConstraint(
                check=Q(amount__gt=0),
                name='expense_payment_amount_positive',
            ),
            models.CheckConstraint(
                check=Q(processing_fee__gte=0),
                name='expense_payment_fee_non_negative',
            ),
            models.CheckConstraint(
                check=Q(bank_charges__gte=0),
                name='expense_payment_bank_charges_non_negative',
            ),
            models.CheckConstraint(
                check=Q(exchange_rate__gt=0),
                name='expense_payment_exchange_rate_positive',
            ),
        ]

    # =========================================================================
    # STRING REPRESENTATION
    # =========================================================================

    def __str__(self):
        suffix = " [REVERSED]" if self.reversed else ""
        currency_note = f" {self.currency}" if self.currency else ""
        return (
            f"Payment {self.reference_number} - "
            f"{self.expense.expense_number} - "
            f"{self.amount:,.2f}{currency_note}{suffix}"
        )

# =============================================================================
# JOURNAL AND ACCOUNTING SYSTEM
# =============================================================================

class Journal(BaseModel):
    """Journals to categorize different types of transactions"""
    
    JOURNAL_TYPE_CHOICES = [
        ('GENERAL', 'General Journal'),
        ('FEES', 'Fee Collection Journal'),
        ('EXPENSES', 'Expense Journal'),
        ('CASH', 'Cash Journal'),
        ('BANK', 'Bank Journal'),
        ('PAYROLL', 'Payroll Journal'),
        ('ADJUSTMENTS', 'Adjustments Journal'),
    ]
    
    # -------------------------------------------------------------------------
    # BASIC INFORMATION
    # -------------------------------------------------------------------------
    
    name = models.CharField("Journal Name", max_length=100)
    journal_type = models.CharField("Journal Type", max_length=15, choices=JOURNAL_TYPE_CHOICES, db_index=True)
    description = models.TextField("Description", blank=True)
    is_active = models.BooleanField("Is Active", default=True, db_index=True)
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Journal"
        verbose_name_plural = "Journals"
        ordering = ['journal_type', 'name']
        indexes = [
            models.Index(fields=['journal_type']),
            models.Index(fields=['is_active']),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.name} ({self.get_journal_type_display()})"


class JournalEntry(BaseModel):
    """Journal entries for double-entry bookkeeping"""
    
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('POSTED', 'Posted'),
        ('REVERSED', 'Reversed'),
    ]
    
    # -------------------------------------------------------------------------
    # IDENTIFICATION
    # -------------------------------------------------------------------------
    
    entry_number = models.CharField("Entry Number", max_length=50, unique=True, db_index=True)
    journal = models.ForeignKey(
        Journal, 
        verbose_name="Journal",
        on_delete=models.PROTECT, 
        related_name='entries'
    )
    entry_date = models.DateField("Entry Date", db_index=True)
    
    # -------------------------------------------------------------------------
    # ACADEMIC CONTEXT (What session does this entry relate to?)
    # -------------------------------------------------------------------------
    
    academic_session = models.ForeignKey(
        AcademicSession,
        verbose_name="Academic Session",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='journal_entries',
        help_text="Academic session this entry relates to (if applicable)"
    )
    
    # -------------------------------------------------------------------------
    # FISCAL CONTEXT (When was this entry made?)
    # -------------------------------------------------------------------------
    
    fiscal_period = models.ForeignKey(
        FiscalPeriod,
        verbose_name="Fiscal Period",
        on_delete=models.PROTECT,
        related_name='journal_entries',
        help_text="Fiscal period when this entry was recorded"
    )
    
    # Access fiscal year via: entry.fiscal_period.fiscal_year
    
    # -------------------------------------------------------------------------
    # REFERENCES
    # -------------------------------------------------------------------------
    
    reference_number = models.CharField("Reference Number", max_length=50, blank=True)
    description = models.TextField("Description")
    notes = models.TextField("Notes", blank=True)
    
    # -------------------------------------------------------------------------
    # STATUS
    # -------------------------------------------------------------------------
    
    status = models.CharField("Status", max_length=10, choices=STATUS_CHOICES, default='DRAFT', db_index=True)
    
    # -------------------------------------------------------------------------
    # APPROVAL AND POSTING
    # -------------------------------------------------------------------------
    
    approved_by_id = models.CharField(
        "Approved By ID",
        max_length=50,
        null=True,
        blank=True,
        help_text="User ID who approved this entry"
    )
    
    posted_by_id = models.CharField(
        "Posted By ID",
        max_length=50,
        null=True,
        blank=True,
        help_text="User ID who posted this entry"
    )
    
    posted_at = models.DateTimeField("Posted At", null=True, blank=True)
    
    # -------------------------------------------------------------------------
    # REVERSAL
    # -------------------------------------------------------------------------
    
    reversed_by_id = models.CharField(
        "Reversed By ID",
        max_length=50,
        null=True,
        blank=True,
        help_text="User ID who reversed this entry"
    )
    
    reversed_at = models.DateTimeField("Reversed At", null=True, blank=True)
    reversal_reason = models.TextField(
        "Reversal Reason", 
        blank=True,
        help_text="Reason for reversing this journal entry"
    )
    
    original_entry = models.ForeignKey(
        'self',
        verbose_name="Original Entry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reversed_entries',
        help_text="Original entry if this is a reversal"
    )
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Journal Entry"
        verbose_name_plural = "Journal Entries"
        ordering = ['-entry_date', '-created_at']
        indexes = [
            models.Index(fields=['entry_number']),
            models.Index(fields=['entry_date']),
            models.Index(fields=['status']),
            models.Index(fields=['journal', 'entry_date']),
            models.Index(fields=['fiscal_period']),
            models.Index(fields=['academic_session']),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.entry_number} - {self.description}"
    
    # -------------------------------------------------------------------------
    # HELPER METHODS
    # -------------------------------------------------------------------------
    
    def get_approved_by_user(self):
        """Get the user who approved this entry"""
        if not self.approved_by_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            return User.objects.using('default').get(id=self.approved_by_id)
        except Exception as e:
            logger.error(f"Error fetching approved_by user: {e}")
            return None
    
    def get_posted_by_user(self):
        """Get the user who posted this entry"""
        if not self.posted_by_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            return User.objects.using('default').get(id=self.posted_by_id)
        except Exception as e:
            logger.error(f"Error fetching posted_by user: {e}")
            return None
    
    def get_reversed_by_user(self):
        """Get the user who reversed this entry"""
        if not self.reversed_by_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            return User.objects.using('default').get(id=self.reversed_by_id)
        except Exception as e:
            logger.error(f"Error fetching reversed_by user: {e}")
            return None


class JournalTransaction(BaseModel):
    """Individual debit/credit transactions within journal entries"""
    
    # -------------------------------------------------------------------------
    # CORE RELATIONSHIPS
    # -------------------------------------------------------------------------
    
    journal_entry = models.ForeignKey(
        JournalEntry, 
        verbose_name="Journal Entry",
        on_delete=models.CASCADE, 
        related_name='transactions'
    )
    account = models.ForeignKey(
        Account, 
        verbose_name="Account",
        on_delete=models.PROTECT, 
        related_name='journal_transactions'
    )
    
    # -------------------------------------------------------------------------
    # TRANSACTION DETAILS
    # -------------------------------------------------------------------------
    
    description = models.CharField("Description", max_length=255, blank=True)
    amount = models.DecimalField(
        "Amount",
        max_digits=15, 
        decimal_places=2, 
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    is_debit = models.BooleanField("Is Debit", help_text="True for debit, False for credit")
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Journal Transaction"
        verbose_name_plural = "Journal Transactions"
        ordering = ['journal_entry', 'id']
        indexes = [
            models.Index(fields=['journal_entry']),
            models.Index(fields=['account']),
            models.Index(fields=['is_debit']),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        trans_type = "Debit" if self.is_debit else "Credit"
        return f"{self.journal_entry.entry_number} - {self.account.account_number} ({trans_type})"


# =============================================================================
# BUDGET MANAGEMENT
# =============================================================================

class Budget(BaseModel):
    """School budget planning and tracking"""
    
    BUDGET_TYPE_CHOICES = [
        ('ANNUAL', 'Annual Budget'),
        ('QUARTERLY', 'Quarterly Budget'),
        ('MONTHLY', 'Monthly Budget'),
        ('PROJECT', 'Project Budget'),
        ('DEPARTMENT', 'Department Budget'),
    ]
    
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('SUBMITTED', 'Submitted'),
        ('APPROVED', 'Approved'),
        ('ACTIVE', 'Active'),
        ('CLOSED', 'Closed'),
        ('REVISED', 'Revised'),
    ]
    
    # -------------------------------------------------------------------------
    # BUDGET IDENTIFICATION
    # -------------------------------------------------------------------------
    
    name = models.CharField("Budget Name", max_length=200)
    budget_type = models.CharField("Budget Type", max_length=15, choices=BUDGET_TYPE_CHOICES, db_index=True)
    
    # -------------------------------------------------------------------------
    # PERIOD
    # -------------------------------------------------------------------------
    
    academic_session = models.ForeignKey(
        AcademicSession,
        verbose_name="Academic Session",
        on_delete=models.CASCADE,
        related_name='budgets',
        help_text="Academic session this budget is for"
    )
    
    start_date = models.DateField("Start Date", db_index=True)
    end_date = models.DateField("End Date", db_index=True)
    
    # ✅ Keep fiscal_year for budgets (budgets are planned per year, not per period)
    fiscal_year = models.ForeignKey(
        FiscalYear,
        verbose_name="Fiscal Year",
        on_delete=models.CASCADE,
        related_name='budgets',
        help_text="Fiscal year this budget is for"
    )
    
    # -------------------------------------------------------------------------
    # BUDGET HIERARCHY
    # -------------------------------------------------------------------------
    
    parent_budget = models.ForeignKey(
        'self',
        verbose_name="Parent Budget",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='child_budgets',
        help_text="Parent budget for hierarchical organization"
    )
    
    # -------------------------------------------------------------------------
    # BUDGET TOTALS
    # -------------------------------------------------------------------------
    
    total_revenue_budget = models.DecimalField(
        "Total Revenue Budget",
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00')
    )
    total_expense_budget = models.DecimalField(
        "Total Expense Budget",
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00')
    )
    net_budget = models.DecimalField(
        "Net Budget (Revenue - Expenses)",
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00')
    )
    
    # -------------------------------------------------------------------------
    # STATUS AND WORKFLOW
    # -------------------------------------------------------------------------
    
    status = models.CharField("Status", max_length=10, choices=STATUS_CHOICES, default='DRAFT', db_index=True)
    
    prepared_by_id = models.CharField(
        "Prepared By ID",
        max_length=50,
        null=True,
        blank=True,
        help_text="User ID who prepared this budget"
    )
    
    approved_by_id = models.CharField(
        "Approved By ID",
        max_length=50,
        null=True,
        blank=True,
        help_text="User ID who approved this budget"
    )
    
    approval_date = models.DateTimeField("Approval Date", null=True, blank=True)
    
    # -------------------------------------------------------------------------
    # AUTO-SYNC WITH ACTUALS
    # -------------------------------------------------------------------------
    
    auto_sync_actuals = models.BooleanField(
        "Auto-Sync Actual Amounts",
        default=True,
        help_text="Automatically update actual amounts from transactions"
    )
    
    last_actuals_sync = models.DateTimeField(
        "Last Actuals Sync",
        null=True,
        blank=True,
        help_text="When actual amounts were last synchronized"
    )
    
    actual_revenue_total = models.DecimalField(
        "Actual Revenue Total",
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Total actual revenue (auto-calculated)"
    )
    
    actual_expense_total = models.DecimalField(
        "Actual Expense Total",
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Total actual expenses (auto-calculated)"
    )
    
    # -------------------------------------------------------------------------
    # DESCRIPTION AND NOTES
    # -------------------------------------------------------------------------
    
    description = models.TextField("Description", blank=True)
    notes = models.TextField("Notes", blank=True)
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Budget"
        verbose_name_plural = "Budgets"
        ordering = ['-start_date', 'name']
        indexes = [
            models.Index(fields=['budget_type']),
            models.Index(fields=['status']),
            models.Index(fields=['start_date', 'end_date']),
            models.Index(fields=['fiscal_year']),
            models.Index(fields=['academic_session']),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.name} ({self.get_budget_type_display()})"
    
    # -------------------------------------------------------------------------
    # HELPER METHODS
    # -------------------------------------------------------------------------
    
    def get_prepared_by_user(self):
        """Get the user who prepared this budget"""
        if not self.prepared_by_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            return User.objects.using('default').get(id=self.prepared_by_id)
        except Exception as e:
            logger.error(f"Error fetching prepared_by user: {e}")
            return None
    
    def get_approved_by_user(self):
        """Get the user who approved this budget"""
        if not self.approved_by_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            return User.objects.using('default').get(id=self.approved_by_id)
        except Exception as e:
            logger.error(f"Error fetching approved_by user: {e}")
            return None


class BudgetLine(BaseModel):
    """Individual line items in budgets"""
    
    LINE_TYPE_CHOICES = [
        ('REVENUE', 'Revenue'),
        ('EXPENSE', 'Expense'),
    ]
    
    # -------------------------------------------------------------------------
    # CORE RELATIONSHIPS
    # -------------------------------------------------------------------------
    
    budget = models.ForeignKey(
        Budget,
        verbose_name="Budget",
        on_delete=models.CASCADE,
        related_name='lines'
    )
    line_type = models.CharField("Line Type", max_length=10, choices=LINE_TYPE_CHOICES, db_index=True)
    
    # -------------------------------------------------------------------------
    # ACCOUNT AND DESCRIPTION
    # -------------------------------------------------------------------------
    
    account = models.ForeignKey(
        Account,
        verbose_name="Account",
        on_delete=models.CASCADE,
        related_name='budget_lines'
    )
    description = models.CharField("Description", max_length=255, blank=True)
    
    # -------------------------------------------------------------------------
    # BUDGET AMOUNTS
    # -------------------------------------------------------------------------
    
    budgeted_amount = models.DecimalField(
        "Budgeted Amount",
        max_digits=15,
        decimal_places=2
    )
    actual_amount = models.DecimalField(
        "Actual Amount",
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00')
    )
    
    # -------------------------------------------------------------------------
    # PAYMENT METHOD INTEGRATION
    # -------------------------------------------------------------------------
    
    primary_payment_methods = models.ManyToManyField(
        PaymentMethod,
        verbose_name="Primary Payment Methods",
        blank=True,
        related_name='budget_lines',
        help_text="Payment methods expected for this revenue line"
    )
    
    # -------------------------------------------------------------------------
    # MONTHLY/QUARTERLY BREAKDOWN
    # -------------------------------------------------------------------------
    
    monthly_breakdown = models.JSONField(
        "Monthly Breakdown",
        default=dict,
        blank=True,
        help_text="Month-by-month budget allocation"
    )
    
    # -------------------------------------------------------------------------
    # NOTES
    # -------------------------------------------------------------------------
    
    notes = models.TextField("Notes", blank=True)
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Budget Line"
        verbose_name_plural = "Budget Lines"
        ordering = ['budget', 'line_type', 'account']
        indexes = [
            models.Index(fields=['budget', 'line_type']),
            models.Index(fields=['account']),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.budget.name} - {self.account.name}"