# finance/forms.py

"""
Financial Management Forms with timezone support.
All date validations use school timezone for consistency.

HTMX configuration removed - to be handled in views and templates.
"""

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta
from django.db.models import Q
from decimal import Decimal
import logging

# Import base form utilities with timezone support ⭐
from utils.forms import (
    BootstrapFormMixin,
    DateRangeFormMixin,
    RequiredFieldsMixin,
    MoneyFieldsMixin,
    DatePickerInput,
    DateTimePickerInput,
    SearchInput,
    MoneyField,
    MoneyInput,
    PercentageField,
    PercentageInput,
    validate_future_date,  # ⭐ Uses school timezone
    validate_past_date,  # ⭐ Uses school timezone
    validate_date_not_before,  # ⭐ Uses school timezone
    validate_date_not_after,  # ⭐ Uses school timezone
    validate_positive_amount,
)

# Import school timezone utilities ⭐
from core.utils import get_school_today, get_school_current_time

from .models import (
    AccountType, Account, ExpenseCategory, Expense, ExpenseLine, ExpensePayment,
    Journal, JournalEntry, JournalTransaction, Budget, BudgetLine
)
from core.models import PaymentMethod, TaxRate, FiscalYear, FiscalPeriod, UnitOfMeasure
from academics.models import AcademicSession

logger = logging.getLogger(__name__)


# =============================================================================
# ACCOUNT TYPE FORMS
# =============================================================================

class AccountTypeForm(RequiredFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """Form for creating/editing account types"""
    
    class Meta:
        model = AccountType
        fields = [
            'name', 'code', 'account_type', 'description',
            'is_active', 'requires_approval', 'allows_manual_entries',
            'number_prefix', 'next_number', 'display_order',
            'icon', 'color', 'max_balance_limit'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'e.g., Current Assets, Operating Expenses'
            }),
            'code': forms.TextInput(attrs={
                'placeholder': 'e.g., CA, OE',
                'style': 'text-transform: uppercase;'
            }),
            'account_type': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Description of this account type...'
            }),
            'number_prefix': forms.TextInput(attrs={
                'placeholder': 'e.g., 1 for Assets, 4 for Revenue',
                'maxlength': '5'
            }),
            'next_number': forms.NumberInput(attrs={'min': '1'}),
            'display_order': forms.NumberInput(attrs={'min': '1'}),
            'icon': forms.TextInput(attrs={
                'placeholder': 'e.g., fa-folder, fa-dollar-sign'
            }),
            'color': forms.TextInput(attrs={
                'type': 'color',
                'placeholder': '#6f42c1'
            }),
            'max_balance_limit': MoneyInput(),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.fields['code'].help_text = "Unique code for this account type"
        self.fields['number_prefix'].help_text = "Prefix for auto-generated account numbers"
        self.fields['icon'].help_text = "FontAwesome icon class (e.g., fa-folder)"
    
    def clean_code(self):
        """Ensure code is uppercase"""
        code = self.cleaned_data.get('code', '')
        return code.upper()


class AccountTypeFilterForm(BootstrapFormMixin, forms.Form):
    """Filter form for account type search"""
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by name, code...'
        })
    )
    
    account_type = forms.ChoiceField(
        label='Account Type',
        choices=[('', 'All Types')] + list(AccountType.ACCOUNT_TYPE_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    is_active = forms.NullBooleanField(
        label='Status',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Active'),
            ('false', 'Inactive')
        ], attrs={'class': 'form-select'})
    )


# =============================================================================
# ACCOUNT FORMS
# =============================================================================

class AccountForm(RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """
    Form for creating/editing accounts.
    Uses school timezone for date validations. ⭐
    """
    
    class Meta:
        model = Account
        fields = [
            'account_number', 'name', 'description', 'account_type', 'parent_account',
            'opening_balance', 'is_active', 'requires_approval', 'daily_limit',
            # Bank account fields
            'is_bank_account', 'bank_name', 'bank_branch', 'account_holder_name',
            'bank_account_number', 'bank_account_type', 'bank_routing_number', 'bank_swift_code',
            # Cash account fields
            'is_cash_account', 'cash_location',
            # Mobile money fields
            'is_mobile_money_account', 'mobile_money_provider', 'mobile_number', 'mobile_account_name',
            # Receivable fields
            'is_receivable_account', 'receivable_type',
            # Payable fields
            'is_payable_account', 'payable_type',
            # Inventory fields
            'is_inventory_account', 'inventory_type',
            # Fixed asset fields
            'is_fixed_asset', 'asset_type',
            # Liability fields
            'is_liability_account', 'liability_type',
            # Loan fields
            'is_loan_account', 'loan_type',
            # Equity fields
            'is_equity_account', 'equity_type',
            # Revenue fields
            'is_revenue_account', 'revenue_type',
            # Expense fields
            'is_expense_account', 'expense_type',
            # Reconciliation
            'is_reconcilable',
        ]
        widgets = {
            'account_number': forms.TextInput(attrs={
                'placeholder': 'e.g., 1001, 4001',
                'style': 'text-transform: uppercase;'
            }),
            'name': forms.TextInput(attrs={
                'placeholder': 'e.g., Cash in Hand, Tuition Revenue'
            }),
            'description': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Description of this account...'
            }),
            'account_type': forms.Select(attrs={'class': 'form-select'}),
            'parent_account': forms.Select(attrs={'class': 'form-select'}),
            'opening_balance': MoneyInput(),
            'daily_limit': MoneyInput(),
            # Bank fields
            'bank_name': forms.TextInput(attrs={'placeholder': 'Bank name'}),
            'bank_branch': forms.TextInput(attrs={'placeholder': 'Branch name'}),
            'account_holder_name': forms.TextInput(attrs={'placeholder': 'Account holder'}),
            'bank_account_number': forms.TextInput(attrs={'placeholder': 'Account number'}),
            'bank_account_type': forms.Select(attrs={'class': 'form-select'}),
            'bank_routing_number': forms.TextInput(attrs={'placeholder': 'Routing number'}),
            'bank_swift_code': forms.TextInput(attrs={'placeholder': 'SWIFT code'}),
            # Cash fields
            'cash_location': forms.TextInput(attrs={'placeholder': 'e.g., Main Office Safe'}),
            # Mobile money fields
            'mobile_money_provider': forms.Select(attrs={'class': 'form-select'}),
            'mobile_number': forms.TextInput(attrs={'placeholder': '+256700000000'}),
            'mobile_account_name': forms.TextInput(attrs={'placeholder': 'Account name'}),
            # Type fields
            'receivable_type': forms.Select(attrs={'class': 'form-select'}),
            'payable_type': forms.Select(attrs={'class': 'form-select'}),
            'inventory_type': forms.Select(attrs={'class': 'form-select'}),
            'asset_type': forms.Select(attrs={'class': 'form-select'}),
            'liability_type': forms.Select(attrs={'class': 'form-select'}),
            'loan_type': forms.Select(attrs={'class': 'form-select'}),
            'equity_type': forms.Select(attrs={'class': 'form-select'}),
            'revenue_type': forms.Select(attrs={'class': 'form-select'}),
            'expense_type': forms.Select(attrs={'class': 'form-select'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
            self.fields['account_type'].queryset = AccountType.objects.filter(
                is_active=True
            ).order_by('account_type', 'display_order')
            
            self.fields['parent_account'].queryset = Account.objects.filter(
                is_active=True
            ).order_by('account_type__account_type', 'account_number')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")
        
        self.fields['account_number'].help_text = "Unique account number"
        self.fields['parent_account'].help_text = "Leave empty for top-level account"
    
    def clean_account_number(self):
        """Ensure account number is uppercase"""
        number = self.cleaned_data.get('account_number', '')
        return number.upper()
    
    def clean(self):
        """Validate account data"""
        cleaned_data = super().clean()
        
        category_flags = [
            'is_bank_account', 'is_cash_account', 'is_mobile_money_account',
            'is_receivable_account', 'is_payable_account', 'is_inventory_account',
            'is_fixed_asset', 'is_liability_account', 'is_loan_account',
            'is_equity_account', 'is_revenue_account', 'is_expense_account'
        ]
        
        if not any(cleaned_data.get(flag) for flag in category_flags):
            raise ValidationError(
                'Please select at least one account category (Bank, Cash, Revenue, etc.)'
            )
        
        if cleaned_data.get('is_bank_account'):
            if not cleaned_data.get('bank_name'):
                self.add_error('bank_name', 'Bank name is required for bank accounts.')
            if not cleaned_data.get('bank_account_number'):
                self.add_error('bank_account_number', 'Account number is required for bank accounts.')
        
        if cleaned_data.get('is_cash_account'):
            if not cleaned_data.get('cash_location'):
                self.add_error('cash_location', 'Cash location is required for cash accounts.')
        
        if cleaned_data.get('is_mobile_money_account'):
            if not cleaned_data.get('mobile_money_provider'):
                self.add_error('mobile_money_provider', 'Provider is required for mobile money accounts.')
            if not cleaned_data.get('mobile_number'):
                self.add_error('mobile_number', 'Mobile number is required for mobile money accounts.')
        
        return cleaned_data


class AccountQuickAddForm(BootstrapFormMixin, forms.ModelForm):
    """Simplified form for quick account creation"""
    
    class Meta:
        model = Account
        fields = [
            'account_number', 'name', 'account_type',
            'is_bank_account', 'is_cash_account', 'is_expense_account', 'is_revenue_account'
        ]
        widgets = {
            'account_number': forms.TextInput(attrs={'placeholder': 'Account number'}),
            'name': forms.TextInput(attrs={'placeholder': 'Account name'}),
            'account_type': forms.Select(attrs={'class': 'form-select'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
            self.fields['account_type'].queryset = AccountType.objects.filter(
                is_active=True
            ).order_by('account_type', 'display_order')
        except Exception as e:
            logger.error(f"Error setting account type queryset: {e}")


class AccountFilterForm(BootstrapFormMixin, forms.Form):
    """Filter form for account search"""
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by number, name...'
        })
    )
    
    account_type = forms.ModelChoiceField(
        label='Account Type',
        queryset=None,
        required=False,
        empty_label="All Types",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    account_category = forms.ChoiceField(
        label='Category',
        choices=[
            ('', 'All Categories'),
            ('bank', 'Bank Accounts'),
            ('cash', 'Cash Accounts'),
            ('mobile_money', 'Mobile Money'),
            ('receivable', 'Receivables'),
            ('payable', 'Payables'),
            ('inventory', 'Inventory'),
            ('fixed_asset', 'Fixed Assets'),
            ('revenue', 'Revenue'),
            ('expense', 'Expense'),
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    is_active = forms.NullBooleanField(
        label='Status',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Active'),
            ('false', 'Inactive')
        ], attrs={'class': 'form-select'})
    )
    
    is_reconcilable = forms.NullBooleanField(
        label='Reconcilable',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Reconcilable'),
            ('false', 'Non-Reconcilable')
        ], attrs={'class': 'form-select'})
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
            self.fields['account_type'].queryset = AccountType.objects.filter(
                is_active=True
            ).order_by('account_type', 'display_order')
        except Exception as e:
            logger.error(f"Error setting account type queryset: {e}")


# =============================================================================
# EXPENSE CATEGORY FORMS
# =============================================================================

class ExpenseCategoryForm(RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """Form for creating/editing expense categories"""
    
    class Meta:
        model = ExpenseCategory
        fields = [
            'name', 'category_type', 'description',
            'default_expense_account', 'requires_approval', 'approval_limit', 'is_active'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'e.g., Office Supplies, Teacher Salaries'
            }),
            'category_type': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Description of this category...'
            }),
            'default_expense_account': forms.Select(attrs={'class': 'form-select'}),
            'approval_limit': MoneyInput(),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
            self.fields['default_expense_account'].queryset = Account.objects.filter(
                is_active=True,
                is_expense_account=True
            ).order_by('account_number')
        except Exception as e:
            logger.error(f"Error setting expense account queryset: {e}")
        
        self.fields['approval_limit'].help_text = "Amount above which approval is required"


class ExpenseCategoryFilterForm(BootstrapFormMixin, forms.Form):
    """Filter form for expense category search"""
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by name...'
        })
    )
    
    category_type = forms.ChoiceField(
        label='Category Type',
        choices=[('', 'All Types')] + list(ExpenseCategory.CATEGORY_TYPE_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    is_active = forms.NullBooleanField(
        label='Status',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Active'),
            ('false', 'Inactive')
        ], attrs={'class': 'form-select'})
    )
    
    requires_approval = forms.NullBooleanField(
        label='Requires Approval',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Requires Approval'),
            ('false', 'No Approval Required')
        ], attrs={'class': 'form-select'})
    )

# =============================================================================
# EXPENSE FORM
# =============================================================================

class ExpenseForm(RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """
    Form for creating and editing expenses.
 
    FIELD AUTO-SET POLICY
    ─────────────────────
    expense_date     → not shown. expense_pre_save sets it via get_school_today().
    fiscal_period    → not shown. expense_pre_save sets it via
                       FiscalPeriod.get_current_fiscal_period().
    academic_session → removed from model. Access via:
                       expense.fiscal_period.related_academic_session
 
    TOTALS POLICY
    ─────────────
    total_amount / subtotal_amount → not shown. Maintained by the ExpenseLine
    post_save signal as sum(lines) + tax_amount. Never user-entered.
 
    tax_amount → the only financial field the user touches. Optional.
 
    PAYEE
    ─────
    payee_type drives what the payee section means:
    - SUPPLIER → name is a vendor/shop, reference is an invoice number
    - STAFF    → name is a staff member, reference is an approval/trip ref
    - PETTY    → small cash purchase, name usually left blank
    - OTHER    → bank charges, government fees, etc.
 
    ⭐ All date comparisons use get_school_today() (school timezone).
    """
 
    class Meta:
        model  = Expense
        fields = [
            # Basic
            'description', 'category',
            # Financial — tax only; totals are signal-driven
            'tax_amount',
            # Payment
            'preferred_payment_method',
            # Payee
            'payee_type', 'payee_name', 'payee_contact', 'vendor_reference',
            # Budget
            'budget_line', 'budget_override_reason',
            # Supporting docs
            'receipt_image', 'notes',
        ]
        widgets = {
            'description': forms.TextInput(attrs={
                'placeholder': 'Brief description of expense…',
            }),
            'category': forms.Select(attrs={
                'class': 'form-select',
            }),
            'tax_amount': MoneyInput(),
            'preferred_payment_method': forms.Select(attrs={
                'class': 'form-select',
            }),
            'payee_type': forms.Select(attrs={
                'class': 'form-select',
                'id':    'id_payee_type',
            }),
            'payee_name': forms.TextInput(attrs={
                'placeholder': 'Name of supplier, staff member, etc.',
                'id':          'id_payee_name',
            }),
            'payee_contact': forms.TextInput(attrs={
                'placeholder': 'Phone or email — optional',
            }),
            'vendor_reference': forms.TextInput(attrs={
                'placeholder': 'Invoice no., receipt ref., trip approval ref…',
            }),
            'budget_line': forms.Select(attrs={
                'class': 'form-select',
            }),
            'budget_override_reason': forms.Textarea(attrs={
                'rows': 2,
                'placeholder': 'Required if expense exceeds budget limit…',
            }),
            'notes': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Verbal approvals, delivery notes, references…',
            }),
        }
 
    # ── __init__ ──────────────────────────────────────────────────────────────

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # payee_name is optional — depends on payee_type
        self.fields['payee_name'].required    = False
        self.fields['payee_contact'].required = False

        # FIX: replace Django's default "----------" empty option.
        # empty_label is a ModelChoiceField attribute — it cannot be set
        # via widget attrs, only here in __init__.
        # preferred_payment_method is a plain <select> with no Select2,
        # so this is the only place its placeholder can be set.
        # category and budget_line also get proper labels as a fallback
        # for when Select2 isn't loaded.
        self.fields['preferred_payment_method'].empty_label = '— Select payment method —'
        self.fields['category'].empty_label                 = '— Select a category —'
        self.fields['budget_line'].empty_label              = '— No budget line —'

        try:
            from core.models import FinancialSettings
            settings = FinancialSettings.get_instance()

            # Only show tax_amount if school has tax enabled in Financial Settings
            if not settings or not settings.include_tax_in_prices:
                self.fields.pop('tax_amount', None)

            self.fields['category'].queryset = ExpenseCategory.objects.filter(
                is_active=True,
            ).order_by('category_type', 'name')

            self.fields['preferred_payment_method'].queryset = PaymentMethod.objects.filter(
                is_active=True,
            ).order_by('name')

            self.fields['budget_line'].queryset = BudgetLine.objects.filter(
                budget__status='ACTIVE',
                line_type='EXPENSE',
            ).select_related('budget', 'account').order_by(
                'budget__name', 'account__name',
            )

        except Exception as e:
            logger.error(f"ExpenseForm: error in __init__: {e}")
            self.fields.pop('tax_amount', None)  # safe default if settings unavailable
 
    # ── clean ─────────────────────────────────────────────────────────────────
 
    def clean(self):
        cleaned_data = super().clean()
 
        tax_amount  = cleaned_data.get('tax_amount')
        payee_type  = cleaned_data.get('payee_type')
        payee_name  = cleaned_data.get('payee_name', '').strip()
 
        # Tax cannot be negative
        if tax_amount is not None and tax_amount < 0:
            self.add_error('tax_amount', 'Tax amount cannot be negative.')
 
        # Supplier and Staff expenses should have a payee name
        # Petty cash and Other can leave it blank
        if payee_type in ('SUPPLIER', 'STAFF') and not payee_name:
            self.add_error(
                'payee_name',
                'Please enter a name for the '
                + ('supplier.' if payee_type == 'SUPPLIER' else 'staff member.'),
            )
 
        return cleaned_data


# =============================================================================
# EXPENSE LINE FORM
# =============================================================================

class ExpenseLineForm(RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """
    Form for individual expense line items — used inside ExpenseLineFormSet.

    FIELD NOTES
    ───────────
    description  → required. Staff must describe what was purchased on every
                   line — e.g. "Box of chalk", "Ream of paper".

    amount       → readonly in the template. Calculated server-side in clean()
                   as quantity × unit_price. Never trusted from the browser.

    expense_account → REMOVED. All lines belong to the same category and post
                   to the same GL account resolved at the Expense level.

    tax_rate /
    tax_amount   → removed from model and form. Not applicable in a Ugandan
                   school context. Use Expense.tax_amount for header-level tax.

    notes        → removed from model and form.
    """

    class Meta:
        model  = ExpenseLine
        fields = [
            'description', 'quantity', 'unit_of_measure',
            'unit_price', 'amount',
        ]
        widgets = {
            'description': forms.TextInput(attrs={
                'placeholder': 'e.g. Box of chalk, Ream of paper…',
            }),
            'quantity': forms.NumberInput(attrs={
                'min':  '0.01',
                'step': '0.01',
            }),
            # FIX: added 'uom-select' class so the template JS can target
            # this field specifically for Select2 initialization in formset rows.
            # The 'form-select' class is still applied by the template's
            # |add_class filter so it does not need to be duplicated here.
            'unit_of_measure': forms.Select(attrs={
                'class': 'uom-select',
            }),
            'unit_price': MoneyInput(),
            'amount':     MoneyInput(attrs={'readonly': True}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['amount'].required = False

        # FIX: replace the default "----------" empty label with something
        # meaningful. empty_label is a ModelChoiceField attribute — it cannot
        # be set via the widget attrs dict, only here in __init__.
        self.fields['unit_of_measure'].empty_label = '— Select unit —'

        try:
            self.fields['unit_of_measure'].queryset = UnitOfMeasure.objects.filter(
                is_active=True,
            ).order_by('name')

        except Exception as e:
            logger.error(f"ExpenseLineForm: error setting querysets: {e}")

    def clean(self):
        """Recalculate amount server-side — never trust the readonly browser value."""
        cleaned_data = super().clean()

        quantity   = cleaned_data.get('quantity')
        unit_price = cleaned_data.get('unit_price')

        if quantity is not None and unit_price is not None:
            if quantity <= 0:
                self.add_error('quantity', 'Quantity must be greater than zero.')
            if unit_price <= 0:
                self.add_error('unit_price', 'Unit price must be greater than zero.')
            if quantity > 0 and unit_price > 0:
                cleaned_data['amount'] = quantity * unit_price

        return cleaned_data


# =============================================================================
# EXPENSE FILTER FORM
# =============================================================================

class ExpenseFilterForm(DateRangeFormMixin, BootstrapFormMixin, forms.Form):
    """
    Filter form for the expense list view.
 
    academic_session → removed. Not on Expense model. Filter by fiscal_period
                       which carries the session via related_academic_session.
    """
 
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by number, description, payee…',
        }),
    )
 
    category = forms.ModelChoiceField(
        label='Category',
        queryset=None,
        required=False,
        empty_label="All Categories",
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
 
    payee_type = forms.ChoiceField(
        label='Payee Type',
        choices=[('', 'All Payee Types')] + list(Expense.PAYEE_TYPE_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
 
    fiscal_period = forms.ModelChoiceField(
        label='Fiscal Period',
        queryset=None,
        required=False,
        empty_label="All Periods",
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
 
    status = forms.ChoiceField(
        label='Status',
        choices=[('', 'All Statuses')] + list(Expense.STATUS_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
 
    expense_date_from = forms.DateField(
        label='Date From',
        required=False,
        widget=DatePickerInput(),
    )
 
    expense_date_to = forms.DateField(
        label='Date To',
        required=False,
        widget=DatePickerInput(),
    )
 
    min_amount = MoneyField(label='Min Amount', required=False)
    max_amount = MoneyField(label='Max Amount', required=False)
 
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
 
        try:
            self.fields['category'].queryset = ExpenseCategory.objects.filter(
                is_active=True,
            ).order_by('category_type', 'name')
 
            # All periods including closed — needed for historical filtering
            self.fields['fiscal_period'].queryset = FiscalPeriod.objects.all().order_by(
                '-start_date',
            )
 
        except Exception as e:
            logger.error(f"ExpenseFilterForm: error setting querysets: {e}")


# =============================================================================
# EXPENSE APPROVAL FORM
# =============================================================================

class ExpenseApprovalForm(RequiredFieldsMixin, BootstrapFormMixin, forms.Form):
    """Form for approving or rejecting an expense."""

    DECISION_CHOICES = [
        ('',        '— Select Decision —'),
        ('APPROVE', 'Approve Expense'),
        ('REJECT',  'Reject Expense'),
    ]

    decision = forms.ChoiceField(
        label='Decision',
        choices=DECISION_CHOICES,
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    notes = forms.CharField(
        label='Notes',
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'Approval or rejection notes…',
        }),
    )

    def clean(self):
        cleaned_data = super().clean()
        decision = cleaned_data.get('decision')
        notes    = cleaned_data.get('notes', '').strip()

        if not decision:
            self.add_error('decision', 'Please select a decision.')

        # Rejection without a reason is useless — enforce it here
        if decision == 'REJECT' and not notes:
            self.add_error(
                'notes',
                'Please provide a reason for rejecting this expense.',
            )

        return cleaned_data

# =============================================================================
# EXPENSE PAYMENT FORM
# =============================================================================

class ExpensePaymentForm(RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """
    Form for recording expense payments.

    FIELD AUTO-SET POLICY
    ─────────────────────
    payment_date  → removed from form. payment_pre_save signal sets it via
                    get_school_today() (school timezone). Never user-entered.

    fiscal_period → removed from form. payment_pre_save signal sets it via
                    FiscalPeriod.get_period_for_date(payment_date) after
                    payment_date is resolved. Never user-entered.

    DYNAMIC FIELD VISIBILITY (template JS)
    ───────────────────────────────────────
    reference_number / transaction_id / processing_fee / bank_charges are
    shown/hidden based on the selected payment method type (cash, mobile_money,
    bank, cheque, other). The template JS reads payment_methods_json passed by
    the modal view to determine which type each method is.

    OVERPAYMENT VALIDATION
    ──────────────────────
    clean() validates that the payment amount does not exceed the outstanding
    balance on the expense (accounting for any prior active payments).
    The service layer enforces the same rule server-side as a second guard.
    """

    amount         = MoneyField(label="Payment Amount")
    processing_fee = MoneyField(label="Processing Fee", required=False)
    bank_charges   = MoneyField(label="Bank Charges",   required=False)

    class Meta:
        model  = ExpensePayment
        fields = [
            # Core
            'expense', 'amount',
            # Method + account
            'payment_method', 'account',
            # Reference fields (shown conditionally by JS)
            'reference_number', 'transaction_id', 'check_number', 'batch_number',
            # Fees (shown conditionally by JS)
            'processing_fee', 'bank_charges',
            # Currency (foreign-currency payments)
            'currency', 'exchange_rate',
            # Supporting info
            'receipt_number', 'payment_details', 'notes',
        ]
        widgets = {
            'expense': forms.Select(attrs={
                'class': 'form-select',
            }),
            'payment_method': forms.Select(attrs={
                'class': 'form-select',
            }),
            'account': forms.Select(attrs={
                'class': 'form-select',
            }),
            # Currency widgets
            'currency': forms.TextInput(attrs={
                'class':       'form-control text-uppercase',
                'placeholder': 'Leave blank for school currency',
                'maxlength':   '3',
                'id':          'id_expense_payment_currency',
            }),
            'exchange_rate': forms.NumberInput(attrs={
                'class':       'form-control',
                'step':        '0.000001',
                'placeholder': '1.000000',
                'id':          'id_expense_payment_exchange_rate',
            }),
            # Reference fields
            'reference_number': forms.TextInput(attrs={
                'placeholder': 'Payment reference number',
            }),
            'transaction_id': forms.TextInput(attrs={
                'placeholder': 'Bank / mobile money transaction ID',
            }),
            'batch_number': forms.TextInput(attrs={
                'placeholder': 'Batch number (for grouped payments)',
            }),
            'check_number': forms.TextInput(attrs={
                'placeholder': 'Cheque number (if applicable)',
            }),
            'receipt_number': forms.TextInput(attrs={
                'placeholder': 'Receipt number from vendor / supplier',
            }),
            'payment_details': forms.Textarea(attrs={
                'rows': 2, 'placeholder': 'Additional payment details…',
            }),
            'notes': forms.Textarea(attrs={
                'rows': 3, 'placeholder': 'Payment notes…',
            }),
        }

    # ── __init__ ──────────────────────────────────────────────────────────────

    def __init__(self, *args, **kwargs):
        expense = kwargs.pop('expense', None)
        super().__init__(*args, **kwargs)

        # ── Resolve school currency once ──────────────────────────────────────
        try:
            from core.models import FinancialSettings
            school_currency = FinancialSettings.get_school_currency() or 'UGX'
        except Exception:
            school_currency = 'UGX'
        self._school_currency = school_currency

        try:
            # FIX: empty_label replaces the default "----------" on all FK selects
            self.fields['expense'].queryset = Expense.objects.filter(
                status='APPROVED'
            ).order_by('-expense_date')
            self.fields['expense'].empty_label = '— Select expense —'

            self.fields['payment_method'].queryset = PaymentMethod.objects.filter(
                is_active=True
            ).order_by('name')
            self.fields['payment_method'].empty_label = '— Select payment method —'

            self.fields['account'].queryset = Account.objects.filter(
                Q(is_bank_account=True) | Q(is_cash_account=True) | Q(is_mobile_money_account=True),
                is_active=True,
            ).order_by('account_number')
            self.fields['account'].empty_label = '— Select account —'
            self.fields['account'].label       = 'Payment From Account'
            self.fields['account'].help_text   = 'Bank / cash account to disburse funds from'

        except Exception as e:
            logger.error(f"ExpensePaymentForm: error setting querysets: {e}")

        # ── Currency field setup ──────────────────────────────────────────────
        self.fields['currency'].required  = False
        self.fields['currency'].help_text = (
            f'Currency the payment was made in. '
            f'Leave blank for {school_currency} (school currency). '
            f'Example: USD for a school paying a foreign supplier.'
        )

        self.fields['exchange_rate'].required  = False
        self.fields['exchange_rate'].help_text = (
            f'Rate to {school_currency} at time of payment. '
            f'Pre-filled from today\'s rates — confirm or override. '
            f'Stored permanently once saved.'
        )
        if not self.fields['exchange_rate'].initial:
            self.fields['exchange_rate'].initial = Decimal('1.000000')

        # Pre-fill exchange rate for new foreign-currency payments
        if not self.instance.pk:
            selected_currency = self.initial.get('currency', '')
            if selected_currency and selected_currency.upper() != school_currency:
                try:
                    from core.models import ExchangeRate
                    rate = ExchangeRate.get_rate(selected_currency.upper(), school_currency)
                    if rate:
                        self.fields['exchange_rate'].initial = rate
                except Exception:
                    pass

        # ── Pre-populate from expense ─────────────────────────────────────────
        if expense:
            self.fields['expense'].initial = expense
            self.fields['amount'].initial  = expense.total_amount

        # ── Lock fields for reversed / verified payments ──────────────────────
        if self.instance.pk:
            if self.instance.reversed:
                for field in self.fields:
                    self.fields[field].disabled  = True
                    self.fields[field].help_text = 'Cannot edit reversed payment'

            elif self.instance.status in ['VERIFIED', 'PROCESSED']:
                for field in [
                    'expense', 'amount', 'payment_method', 'account',
                    'processing_fee', 'bank_charges', 'currency', 'exchange_rate',
                ]:
                    if field in self.fields:
                        self.fields[field].disabled  = True
                        self.fields[field].help_text = 'Cannot modify verified / processed payment'

    # ── Field-level validation ────────────────────────────────────────────────

    def clean_currency(self):
        code = self.cleaned_data.get('currency', '').upper().strip()
        if code and len(code) != 3:
            raise ValidationError('Currency code must be exactly 3 characters (ISO 4217).')
        return code or self._school_currency

    def clean_exchange_rate(self):
        rate = self.cleaned_data.get('exchange_rate')
        if rate is not None and rate <= 0:
            raise ValidationError('Exchange rate must be greater than zero.')
        return rate or Decimal('1.000000')

    # ── Cross-field validation ────────────────────────────────────────────────

    def clean(self):
        cleaned_data  = super().clean()

        currency      = cleaned_data.get('currency') or self._school_currency
        exchange_rate = cleaned_data.get('exchange_rate') or Decimal('1.000000')
        amount        = cleaned_data.get('amount')

        # FIX: processing_fee and bank_charges arrive as None when the JS hides
        # and clears those fields (empty string → MoneyField(required=False) → None).
        # The model's clean() does `if self.processing_fee < 0` which crashes on None.
        # Coerce to Decimal('0.00') so the model always sees a valid value.
        for fee_field in ('processing_fee', 'bank_charges'):
            if not cleaned_data.get(fee_field):
                cleaned_data[fee_field] = Decimal('0.00')

        # Foreign currency requires a real exchange rate
        if currency != self._school_currency and exchange_rate == Decimal('1.000000'):
            self.add_error(
                'exchange_rate',
                f'Currency is {currency} but rate is 1.000000. '
                f'Enter the actual rate to {self._school_currency}.',
            )

        # Compute amount_in_school_currency for overpayment check and save()
        if amount and exchange_rate and exchange_rate > 0:
            cleaned_data['amount_in_school_currency'] = (
                Decimal(str(amount)) * Decimal(str(exchange_rate))
            ).quantize(Decimal('0.01'))

        # ── Amount must be positive (checked independently — 0 is falsy) ──────
        if amount is not None and amount <= 0:
            self.add_error('amount', 'Payment amount must be greater than zero.')

        # ── Overpayment validation ────────────────────────────────────────────
        expense = cleaned_data.get('expense')
        if expense and amount and amount > 0:
            # Sum all active (non-reversed) payments already on this expense
            total_paid = sum(
                p.amount_in_school_currency
                for p in expense.payments.all()
                if p.is_active and (not self.instance.pk or p.pk != self.instance.pk)
            )
            new_amount_sc = cleaned_data.get(
                'amount_in_school_currency',
                Decimal(str(amount)) * Decimal(str(exchange_rate)),
            )
            remaining = expense.total_amount - total_paid

            if new_amount_sc > remaining:
                self.add_error(
                    'amount',
                    f'Payment of {new_amount_sc:,.2f} {self._school_currency} exceeds the '
                    f'outstanding balance of {remaining:,.2f} {self._school_currency}. '
                    f'Already paid: {total_paid:,.2f} of {expense.total_amount:,.2f}.',
                )

        # Fees must be non-negative (None already coerced to 0 above)
        for fee_field, label in [
            ('processing_fee', 'Processing fee'),
            ('bank_charges',   'Bank charges'),
        ]:
            val = cleaned_data.get(fee_field, Decimal('0.00'))
            if val < 0:
                self.add_error(fee_field, f'{label} cannot be negative.')

        return cleaned_data

    # ── save ─────────────────────────────────────────────────────────────────

    def save(self, commit=True):
        """Set amount_in_school_currency and default currency before saving."""
        instance = super().save(commit=False)

        amount_sc = self.cleaned_data.get('amount_in_school_currency')
        if amount_sc is not None:
            instance.amount_in_school_currency = amount_sc

        if not instance.currency:
            instance.currency = self._school_currency

        # payment_date and fiscal_period are set by payment_pre_save signal —
        # do not set them here so the signal always uses the school timezone.

        if commit:
            instance.save()
        return instance


# =============================================================================
# EXPENSE PAYMENT REVERSAL FORM
# =============================================================================

class ExpensePaymentReversalForm(BootstrapFormMixin, RequiredFieldsMixin, forms.Form):
    """
    Form for reversing an expense payment (internal correction).

    Use when:
    - Payment was posted to wrong expense
    - Duplicate payment entry
    - Wrong amount entered
    - Wrong vendor paid
    """

    reversal_reason = forms.CharField(
        label="Reversal Reason",
        widget=forms.Textarea(attrs={
            'rows': 4,
            'placeholder': (
                'Provide detailed reason for reversal:\n'
                '- Was payment posted to wrong expense?\n'
                '- Was it a duplicate entry?\n'
                '- Was wrong amount paid?\n'
                '- Was wrong vendor paid?\n'
                '- Other specific details...'
            ),
        }),
        help_text="Detailed explanation required for audit trail",
    )

    requires_approval = forms.BooleanField(
        label="This reversal requires manager approval",
        required=False,
        initial=True,
        help_text="Large or verified payments require approval for reversal",
    )

    confirm_reversal = forms.BooleanField(
        label="I confirm this is an internal correction (payment was entered incorrectly)",
        required=True,
        help_text=(
            "Check this box to confirm you understand:\n"
            "• This is for correcting data entry errors only\n"
            "• The expense will be updated to reflect unpaid/partially paid status\n"
            "• Account balances will be adjusted\n"
            "• This action will be logged in the audit trail"
        ),
    )

    def __init__(self, expense_payment, user, *args, **kwargs):
        self.expense_payment = expense_payment
        self.user = user
        super().__init__(*args, **kwargs)

        self.fields['reversal_reason'].help_text = (
            f"Reversing payment {expense_payment.reference_number} — "
            f"Amount: {expense_payment.amount:,.2f} {expense_payment.currency or ''} "
            f"({expense_payment.amount_in_school_currency:,.2f} school currency) — "
            f"Date: {expense_payment.payment_date} — "
            f"Expense: {expense_payment.expense.expense_number}"
        )

        if expense_payment.is_verified or expense_payment.amount > Decimal('1000000.00'):
            self.fields['requires_approval'].initial  = True
            self.fields['requires_approval'].disabled = True
            self.fields['requires_approval'].help_text = (
                "REQUIRED: This payment is verified or exceeds 1M threshold"
            )

    def clean(self):
        cleaned_data = super().clean()
        can_reverse, reason = self.expense_payment.can_be_reversed()
        if not can_reverse:
            raise ValidationError(f"Cannot reverse this payment: {reason}")
        if len((cleaned_data.get('reversal_reason') or '').strip()) < 20:
            raise ValidationError({
                'reversal_reason': 'Please provide a detailed reason (at least 20 characters).',
            })
        return cleaned_data


# =============================================================================
# EXPENSE PAYMENT FILTER FORM
# =============================================================================

class ExpensePaymentFilterForm(DateRangeFormMixin, BootstrapFormMixin, forms.Form):
    """Filter form for expense payment search. Uses school timezone for date filters."""

    q = forms.CharField(
        label='Search', required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by reference, transaction ID, expense number...',
        }),
    )

    fiscal_period = forms.ModelChoiceField(
        label='Fiscal Period', queryset=None, required=False,
        empty_label="All Periods",
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    payment_method = forms.ModelChoiceField(
        label='Payment Method', queryset=None, required=False,
        empty_label="All Methods",
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    account = forms.ModelChoiceField(
        label='Payment Account', queryset=None, required=False,
        empty_label="All Accounts",
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Account from which payment was made",
    )

    status = forms.ChoiceField(
        label='Status', required=False,
        choices=[('', 'All Statuses')] + list(ExpensePayment.STATUS_CHOICES),
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    payment_state = forms.ChoiceField(
        label='Payment State', required=False,
        choices=[
            ('', 'All Payments'),
            ('active',   'Active Only'),
            ('reversed', 'Reversed Only'),
        ],
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Filter by reversal status",
    )

    # ── CURRENCY ──────────────────────────────────────────────────────────────
    currency = forms.ChoiceField(
        label='Currency', required=False,
        choices=[],   # populated in __init__ from live data
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Filter by currency the payment was made in.',
    )
    # ─────────────────────────────────────────────────────────────────────────

    is_verified = forms.NullBooleanField(
        label='Verification', required=False,
        widget=forms.Select(
            choices=[('', 'All'), ('true', 'Verified'), ('false', 'Unverified')],
            attrs={'class': 'form-select'},
        ),
    )

    payment_date_from = forms.DateField(
        label='Payment Date From', required=False, widget=DatePickerInput(),
    )

    payment_date_to = forms.DateField(
        label='Payment Date To', required=False, widget=DatePickerInput(),
    )

    min_amount = MoneyField(label='Min Amount', required=False)
    max_amount = MoneyField(label='Max Amount', required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        try:
            self.fields['fiscal_period'].queryset = FiscalPeriod.objects.all().order_by('-start_date')

            self.fields['payment_method'].queryset = PaymentMethod.objects.filter(
                is_active=True
            ).order_by('name')

            self.fields['account'].queryset = Account.objects.filter(
                Q(is_bank_account=True) | Q(is_cash_account=True) | Q(is_mobile_money_account=True),
                is_active=True
            ).order_by('account_number')

        except Exception as e:
            logger.error(f"ExpensePaymentFilterForm: error setting querysets: {e}")

        # ── Currency choices from live ExpensePayment data ────────────────────
        self.fields['currency'].choices = self._build_currency_choices()

    @staticmethod
    def _build_currency_choices():
        choices = [('', 'All Currencies')]
        try:
            from core.models import FinancialSettings
            school_currency = FinancialSettings.get_school_currency() or 'UGX'
        except Exception:
            school_currency = 'UGX'

        choices.append((school_currency, f'{school_currency} (School Currency)'))

        try:
            others = (
                ExpensePayment.objects
                .exclude(currency=school_currency)
                .exclude(currency='')
                .values_list('currency', flat=True)
                .distinct()
                .order_by('currency')
            )
            for code in others:
                if code:
                    choices.append((code, code))
        except Exception:
            pass

        return choices


# =============================================================================
# BULK EXPENSE PAYMENT FORM
# =============================================================================

class BulkExpensePaymentForm(BootstrapFormMixin, RequiredFieldsMixin, forms.Form):
    """
    Form for processing multiple expense payments at once.

    Used when paying multiple approved expenses in a single batch
    (e.g., monthly vendor payments).
    """

    expense_ids = forms.CharField(widget=forms.HiddenInput(), required=True)

    payment_date = forms.DateField(
        label="Payment Date", widget=DatePickerInput(),
        help_text="Date when payments were actually made",
    )

    payment_method = forms.ModelChoiceField(
        label="Payment Method", queryset=None,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="How all payments will be made",
    )

    account = forms.ModelChoiceField(
        label="Payment From Account", queryset=None,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Bank/cash account to disburse funds from",
    )

    batch_number = forms.CharField(
        label="Batch Number", max_length=50,
        widget=forms.TextInput(attrs={'placeholder': 'E.g., BATCH-2024-01 or upload reference'}),
        help_text="Reference number for this payment batch",
    )

    payment_notes = forms.CharField(
        label="Payment Notes",
        widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Any notes about this payment batch...'}),
        required=False,
    )

    confirm_payment = forms.BooleanField(
        label="I confirm all selected expenses will be paid",
        required=True,
        help_text="Money will be disbursed from the selected account",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        try:
            self.fields['payment_method'].queryset = PaymentMethod.objects.filter(
                is_active=True
            ).order_by('name')

            self.fields['account'].queryset = Account.objects.filter(
                Q(is_bank_account=True) | Q(is_cash_account=True) | Q(is_mobile_money_account=True),
                is_active=True
            ).order_by('account_number')

        except Exception as e:
            logger.error(f"BulkExpensePaymentForm: error setting querysets: {e}")

        if not self.is_bound:
            from core.utils import get_school_today
            self.fields['payment_date'].initial = get_school_today()

    def clean_expense_ids(self):
        ids_string = self.cleaned_data.get('expense_ids', '')
        try:
            expense_ids = [int(i.strip()) for i in ids_string.split(',') if i.strip()]
        except ValueError:
            raise ValidationError("Invalid expense IDs")

        if not expense_ids:
            raise ValidationError("No expenses selected")

        expenses = Expense.objects.filter(id__in=expense_ids)

        if expenses.count() != len(expense_ids):
            raise ValidationError("Some selected expenses do not exist")

        non_approved = expenses.exclude(status='APPROVED')
        if non_approved.exists():
            raise ValidationError(
                f"{non_approved.count()} expense(s) are not APPROVED and cannot be paid."
            )

        # Use amount_in_school_currency for consistent comparison
        for expense in expenses:
            total_paid = sum(
                p.amount_in_school_currency
                for p in expense.payments.all()
                if p.is_active
            )
            if total_paid >= expense.total_amount:
                raise ValidationError(
                    f"Expense {expense.expense_number} is already fully paid. "
                    "Please deselect it from the batch."
                )

        return expense_ids

    def clean_payment_date(self):
        payment_date = self.cleaned_data.get('payment_date')
        if payment_date:
            from core.utils import get_school_today
            today = get_school_today()
            if payment_date > today:
                raise ValidationError(
                    "Payment date cannot be in the future."
                )
            if payment_date < (today - timedelta(days=90)):
                raise ValidationError("Payment date seems too far in the past. Please verify.")
        return payment_date


# =============================================================================
# BULK EXPENSE PAYMENT VERIFICATION FORM
# =============================================================================

class BulkExpensePaymentVerificationForm(BootstrapFormMixin, forms.Form):
    """Form for verifying multiple expense payments at once."""

    payment_ids = forms.CharField(widget=forms.HiddenInput(), required=True)

    verification_notes = forms.CharField(
        label="Verification Notes",
        widget=forms.Textarea(attrs={
            'rows': 3, 'placeholder': 'Any notes for this verification batch...',
        }),
        required=False,
    )

    confirm_verification = forms.BooleanField(
        label="I confirm all selected payments have been verified",
        required=True,
        help_text="All selected payments will be marked as verified",
    )

    def clean_payment_ids(self):
        ids_string = self.cleaned_data.get('payment_ids', '')
        try:
            payment_ids = [int(i.strip()) for i in ids_string.split(',') if i.strip()]
        except ValueError:
            raise ValidationError("Invalid payment IDs")

        if not payment_ids:
            raise ValidationError("No payments selected")

        payments = ExpensePayment.objects.filter(id__in=payment_ids)

        if payments.count() != len(payment_ids):
            raise ValidationError("Some selected payments do not exist")

        already_verified = payments.filter(is_verified=True)
        if already_verified.exists():
            raise ValidationError(
                f"{already_verified.count()} payment(s) are already verified"
            )

        reversed_payments = payments.filter(reversed=True)
        if reversed_payments.exists():
            raise ValidationError(
                f"{reversed_payments.count()} payment(s) are reversed and cannot be verified"
            )

        non_processed = payments.exclude(status__in=['PROCESSED', 'VERIFIED'])
        if non_processed.exists():
            raise ValidationError(
                f"{non_processed.count()} payment(s) are not processed and cannot be verified"
            )

        return payment_ids

# =============================================================================
# JOURNAL FORMS
# =============================================================================

class JournalForm(RequiredFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """Form for creating/editing journals"""
    
    class Meta:
        model = Journal
        fields = ['name', 'journal_type', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'e.g., General Journal, Fee Collection Journal'
            }),
            'journal_type': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Description of this journal...'
            }),
        }


class JournalFilterForm(BootstrapFormMixin, forms.Form):
    """Filter form for journal search"""
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by name...'
        })
    )
    
    journal_type = forms.ChoiceField(
        label='Journal Type',
        choices=[('', 'All Types')] + list(Journal.JOURNAL_TYPE_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    is_active = forms.NullBooleanField(
        label='Status',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Active'),
            ('false', 'Inactive')
        ], attrs={'class': 'form-select'})
    )


# =============================================================================
# JOURNAL ENTRY FORMS
# =============================================================================

class JournalEntryForm(RequiredFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """
    Form for creating/editing journal entries.
    Uses school timezone for date validations. ⭐
    """
    
    class Meta:
        model = JournalEntry
        fields = [
            'journal', 'entry_date', 'academic_session', 'fiscal_period',
            'reference_number', 'description', 'notes'
        ]
        widgets = {
            'journal': forms.Select(attrs={'class': 'form-select'}),
            'entry_date': DatePickerInput(),
            'academic_session': forms.Select(attrs={'class': 'form-select'}),
            'fiscal_period': forms.Select(attrs={'class': 'form-select'}),
            'reference_number': forms.TextInput(attrs={
                'placeholder': 'Reference number (optional)'
            }),
            'description': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Entry description...'
            }),
            'notes': forms.Textarea(attrs={
                'rows': 2,
                'placeholder': 'Additional notes...'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
            self.fields['journal'].queryset = Journal.objects.filter(
                is_active=True
            ).order_by('journal_type', 'name')
            
            self.fields['academic_session'].queryset = AcademicSession.objects.filter(
                is_active=True
            ).order_by('-start_date')
            
            self.fields['fiscal_period'].queryset = FiscalPeriod.objects.filter(
                status__in=['OPEN', 'CURRENT']
            ).order_by('-start_date')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")
        
        if not self.is_bound:
            self.fields['entry_date'].initial = get_school_today()  # ⭐ SCHOOL TIMEZONE
    
    def clean(self):
        """Validate journal entry data using school timezone ⭐"""
        cleaned_data = super().clean()
        
        entry_date = cleaned_data.get('entry_date')
        fiscal_period = cleaned_data.get('fiscal_period')
        
        today = get_school_today()  # ⭐ SCHOOL TIMEZONE
        
        if entry_date and entry_date > today:
            raise ValidationError({
                'entry_date': 'Entry date cannot be in the future.'
            })
        
        if entry_date and fiscal_period:
            if entry_date < fiscal_period.start_date or entry_date > fiscal_period.end_date:
                self.add_error('fiscal_period',
                    'Entry date must fall within the selected fiscal period.'
                )
        
        return cleaned_data


class JournalTransactionForm(RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """Form for journal transactions (inline formset use)"""
    
    class Meta:
        model = JournalTransaction
        fields = ['account', 'description', 'amount', 'is_debit']
        widgets = {
            'account': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.TextInput(attrs={
                'placeholder': 'Transaction description...'
            }),
            'amount': MoneyInput(),
            'is_debit': forms.Select(
                choices=[(True, 'Debit'), (False, 'Credit')],
                attrs={'class': 'form-select'}
            ),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
            self.fields['account'].queryset = Account.objects.filter(
                is_active=True
            ).order_by('account_type__account_type', 'account_number')
        except Exception as e:
            logger.error(f"Error setting account queryset: {e}")


class JournalEntryFilterForm(DateRangeFormMixin, BootstrapFormMixin, forms.Form):
    """
    Filter form for journal entry search.
    Uses school timezone for date filters. ⭐
    """
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by entry number, description...'
        })
    )
    
    journal = forms.ModelChoiceField(
        label='Journal',
        queryset=None,
        required=False,
        empty_label="All Journals",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    academic_session = forms.ModelChoiceField(
        label='Academic Session',
        queryset=None,
        required=False,
        empty_label="All Sessions",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    fiscal_period = forms.ModelChoiceField(
        label='Fiscal Period',
        queryset=None,
        required=False,
        empty_label="All Periods",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    status = forms.ChoiceField(
        label='Status',
        choices=[('', 'All Statuses')] + list(JournalEntry.STATUS_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    entry_date_from = forms.DateField(
        label='Entry Date From',
        required=False,
        widget=DatePickerInput()
    )
    
    entry_date_to = forms.DateField(
        label='Entry Date To',
        required=False,
        widget=DatePickerInput()
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
            self.fields['journal'].queryset = Journal.objects.filter(
                is_active=True
            ).order_by('journal_type', 'name')
            
            self.fields['academic_session'].queryset = AcademicSession.objects.filter(
                is_active=True
            ).order_by('-start_date')
            
            self.fields['fiscal_period'].queryset = FiscalPeriod.objects.all().order_by('-start_date')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")


# =============================================================================
# BUDGET FORMS
# =============================================================================

class BudgetForm(RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """
    Form for creating/editing budgets.
    Uses school timezone for date validations. ⭐
    """
    
    class Meta:
        model = Budget
        fields = [
            'name', 'budget_type', 'academic_session', 'start_date', 'end_date',
            'fiscal_year', 'parent_budget', 'description', 'notes',
            'auto_sync_actuals'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'e.g., 2024 Annual Budget, Q1 2024 Budget'
            }),
            'budget_type': forms.Select(attrs={'class': 'form-select'}),
            'academic_session': forms.Select(attrs={'class': 'form-select'}),
            'start_date': DatePickerInput(),
            'end_date': DatePickerInput(),
            'fiscal_year': forms.Select(attrs={'class': 'form-select'}),
            'parent_budget': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Budget description...'
            }),
            'notes': forms.Textarea(attrs={
                'rows': 2,
                'placeholder': 'Additional notes...'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
            self.fields['academic_session'].queryset = AcademicSession.objects.filter(
                is_active=True
            ).order_by('-start_date')
            
            self.fields['fiscal_year'].queryset = FiscalYear.objects.filter(
                status__in=['OPEN', 'CURRENT']
            ).order_by('-start_date')
            
            self.fields['parent_budget'].queryset = Budget.objects.filter(
                status__in=['APPROVED', 'ACTIVE']
            ).order_by('-start_date')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")
    
    def clean(self):
        """Validate budget data using school timezone ⭐"""
        cleaned_data = super().clean()
        
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        
        if start_date and end_date:
            if end_date < start_date:
                raise ValidationError({
                    'end_date': 'End date cannot be before start date.'
                })
        
        return cleaned_data


class BudgetLineForm(RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """Form for budget lines (inline formset use)"""
    
    class Meta:
        model = BudgetLine
        fields = [
            'line_type', 'account', 'description', 'budgeted_amount',
            'primary_payment_methods', 'notes'
        ]
        widgets = {
            'line_type': forms.Select(attrs={'class': 'form-select'}),
            'account': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.TextInput(attrs={
                'placeholder': 'Line description...'
            }),
            'budgeted_amount': MoneyInput(),
            'primary_payment_methods': forms.SelectMultiple(attrs={
                'class': 'form-select',
                'size': '3'
            }),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
            self.fields['account'].queryset = Account.objects.filter(
                is_active=True
            ).order_by('account_type__account_type', 'account_number')
            
            self.fields['primary_payment_methods'].queryset = PaymentMethod.objects.filter(
                is_active=True
            ).order_by('name')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")


class BudgetFilterForm(DateRangeFormMixin, BootstrapFormMixin, forms.Form):
    """
    Filter form for budget search.
    Uses school timezone for date filters. ⭐
    """
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by name...'
        })
    )
    
    budget_type = forms.ChoiceField(
        label='Budget Type',
        choices=[('', 'All Types')] + list(Budget.BUDGET_TYPE_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    academic_session = forms.ModelChoiceField(
        label='Academic Session',
        queryset=None,
        required=False,
        empty_label="All Sessions",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    fiscal_year = forms.ModelChoiceField(
        label='Fiscal Year',
        queryset=None,
        required=False,
        empty_label="All Years",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    status = forms.ChoiceField(
        label='Status',
        choices=[('', 'All Statuses')] + list(Budget.STATUS_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
            self.fields['academic_session'].queryset = AcademicSession.objects.filter(
                is_active=True
            ).order_by('-start_date')
            
            self.fields['fiscal_year'].queryset = FiscalYear.objects.all().order_by('-start_date')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")


class BudgetApprovalForm(RequiredFieldsMixin, BootstrapFormMixin, forms.Form):
    """Form for approving/rejecting budgets"""
    
    DECISION_CHOICES = [
        ('', '-- Select Decision --'),
        ('APPROVE', 'Approve Budget'),
        ('REJECT', 'Reject Budget'),
        ('REQUEST_REVISION', 'Request Revision'),
    ]
    
    decision = forms.ChoiceField(
        label='Decision',
        choices=DECISION_CHOICES,
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    notes = forms.CharField(
        label='Approval Notes',
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'Enter approval or feedback notes...'
        })
    )
    
    def clean_decision(self):
        """Ensure a decision is selected"""
        decision = self.cleaned_data.get('decision')
        if not decision:
            raise ValidationError('Please select a decision.')
        return decision


# =============================================================================
# ACCOUNT RECONCILIATION FORM
# =============================================================================

class AccountReconciliationForm(RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.Form):
    """
    Form for reconciling accounts.
    Uses school timezone for date validations. ⭐
    """
    
    account = forms.ModelChoiceField(
        label='Account to Reconcile',
        queryset=None,
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    reconciliation_date = forms.DateField(
        label='Reconciliation Date',
        required=True,
        widget=DatePickerInput(),
        help_text='Date of the bank/account statement'
    )
    
    statement_balance = MoneyField(
        label='Statement Balance',
        required=True,
        help_text='Balance as shown on the bank/account statement'
    )
    
    notes = forms.CharField(
        label='Reconciliation Notes',
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'Notes about this reconciliation...'
        })
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
            self.fields['account'].queryset = Account.objects.filter(
                is_active=True,
                is_reconcilable=True
            ).order_by('account_number')
        except Exception as e:
            logger.error(f"Error setting account queryset: {e}")
        
        if not self.is_bound:
            self.fields['reconciliation_date'].initial = get_school_today()  # ⭐ SCHOOL TIMEZONE
    
    def clean_reconciliation_date(self):
        """Validate reconciliation date using school timezone ⭐"""
        date = self.cleaned_data.get('reconciliation_date')
        
        today = get_school_today()  # ⭐ SCHOOL TIMEZONE
        
        if date and date > today:
            raise ValidationError('Reconciliation date cannot be in the future.')
        
        return date


# =============================================================================
# JOURNAL ENTRY REVERSAL FORM
# =============================================================================

class JournalEntryReversalForm(RequiredFieldsMixin, BootstrapFormMixin, forms.Form):
    """
    Form for reversing journal entries.
    Uses school timezone for date validations. ⭐
    """
    
    reversal_reason = forms.CharField(
        label='Reason for Reversal',
        required=True,
        widget=forms.Textarea(attrs={
            'rows': 4,
            'placeholder': 'Please provide a detailed reason for reversing this entry...'
        })
    )
    
    reversal_date = forms.DateField(
        label='Reversal Date',
        required=True,
        widget=DatePickerInput(),
        help_text='Date for the reversal entry'
    )
    
    confirm = forms.BooleanField(
        label='I confirm this reversal',
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if not self.is_bound:
            self.fields['reversal_date'].initial = get_school_today()  # ⭐ SCHOOL TIMEZONE
    
    def clean_reversal_date(self):
        """Validate reversal date using school timezone ⭐"""
        date = self.cleaned_data.get('reversal_date')
        
        today = get_school_today()  # ⭐ SCHOOL TIMEZONE
        
        if date and date > today:
            raise ValidationError('Reversal date cannot be in the future.')
        
        return date