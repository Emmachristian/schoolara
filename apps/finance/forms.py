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
# EXPENSE FORMS
# =============================================================================

class ExpenseForm(RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """
    Form for creating/editing expenses.
    Uses school timezone for date validations. ⭐
    """
    
    class Meta:
        model = Expense
        fields = [
            'expense_date', 'description', 'category',
            'academic_session', 'fiscal_period',
            'total_amount', 'tax_amount',
            'vendor_name', 'vendor_contact', 'vendor_reference',
            'preferred_payment_method', 'expense_account',
            'budget_line', 'budget_override_reason',
            'receipt_image', 'notes', 'is_recurring', 'auto_create_journal_entry'
        ]
        widgets = {
            'expense_date': DatePickerInput(),
            'description': forms.TextInput(attrs={
                'placeholder': 'Brief description of expense...'
            }),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'academic_session': forms.Select(attrs={'class': 'form-select'}),
            'fiscal_period': forms.Select(attrs={'class': 'form-select'}),
            'total_amount': MoneyInput(),
            'tax_amount': MoneyInput(),
            'vendor_name': forms.TextInput(attrs={
                'placeholder': 'Vendor/Supplier name'
            }),
            'vendor_contact': forms.TextInput(attrs={
                'placeholder': 'Phone or email'
            }),
            'vendor_reference': forms.TextInput(attrs={
                'placeholder': 'Invoice or reference number'
            }),
            'preferred_payment_method': forms.Select(attrs={'class': 'form-select'}),
            'expense_account': forms.Select(attrs={'class': 'form-select'}),
            'budget_line': forms.Select(attrs={'class': 'form-select'}),
            'budget_override_reason': forms.Textarea(attrs={
                'rows': 2,
                'placeholder': 'Reason for exceeding budget (if applicable)...'
            }),
            'notes': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Additional notes...'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
            self.fields['category'].queryset = ExpenseCategory.objects.filter(
                is_active=True
            ).order_by('category_type', 'name')
            
            self.fields['academic_session'].queryset = AcademicSession.objects.filter(
                is_active=True
            ).order_by('-start_date')
            
            self.fields['fiscal_period'].queryset = FiscalPeriod.objects.filter(
                status__in=['OPEN', 'CURRENT']
            ).order_by('-start_date')
            
            self.fields['preferred_payment_method'].queryset = PaymentMethod.objects.filter(
                is_active=True
            ).order_by('name')
            
            self.fields['expense_account'].queryset = Account.objects.filter(
                is_active=True,
                is_expense_account=True
            ).order_by('account_number')
            
            self.fields['budget_line'].queryset = BudgetLine.objects.filter(
                budget__status='ACTIVE',
                line_type='EXPENSE'
            ).select_related('budget', 'account').order_by('budget__name', 'account__name')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")
        
        if not self.is_bound:
            self.fields['expense_date'].initial = get_school_today()  # ⭐ SCHOOL TIMEZONE
    
    def clean(self):
        """Validate expense data using school timezone ⭐"""
        cleaned_data = super().clean()
        
        expense_date = cleaned_data.get('expense_date')
        fiscal_period = cleaned_data.get('fiscal_period')
        
        today = get_school_today()  # ⭐ SCHOOL TIMEZONE
        
        if expense_date and expense_date > today:
            raise ValidationError({
                'expense_date': 'Expense date cannot be in the future.'
            })
        
        if expense_date and fiscal_period:
            if expense_date < fiscal_period.start_date or expense_date > fiscal_period.end_date:
                self.add_error('fiscal_period',
                    'Expense date must fall within the selected fiscal period.'
                )
        
        total_amount = cleaned_data.get('total_amount')
        tax_amount = cleaned_data.get('tax_amount')
        
        if total_amount and tax_amount:
            if tax_amount > total_amount:
                raise ValidationError({
                    'tax_amount': 'Tax amount cannot exceed total amount.'
                })
        
        return cleaned_data


class ExpenseLineForm(RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """Form for expense line items (inline formset use)"""
    
    class Meta:
        model = ExpenseLine
        fields = [
            'description', 'quantity', 'unit_of_measure', 'unit_price', 'amount',
            'expense_account', 'tax_rate', 'tax_amount', 'notes'
        ]
        widgets = {
            'description': forms.TextInput(attrs={
                'placeholder': 'Line item description...'
            }),
            'quantity': forms.NumberInput(attrs={'min': '0.01', 'step': '0.01'}),
            'unit_of_measure': forms.Select(attrs={'class': 'form-select'}),
            'unit_price': MoneyInput(),
            'amount': MoneyInput(),
            'expense_account': forms.Select(attrs={'class': 'form-select'}),
            'tax_rate': forms.Select(attrs={'class': 'form-select'}),
            'tax_amount': MoneyInput(),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
            self.fields['unit_of_measure'].queryset = UnitOfMeasure.objects.filter(
                is_active=True
            ).order_by('name')
            
            self.fields['expense_account'].queryset = Account.objects.filter(
                is_active=True,
                is_expense_account=True
            ).order_by('account_number')
            
            self.fields['tax_rate'].queryset = TaxRate.objects.filter(
                is_active=True
            ).order_by('name')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")


class ExpenseFilterForm(DateRangeFormMixin, BootstrapFormMixin, forms.Form):
    """
    Filter form for expense search.
    Uses school timezone for date filters. ⭐
    """
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by number, description, vendor...'
        })
    )
    
    category = forms.ModelChoiceField(
        label='Category',
        queryset=None,
        required=False,
        empty_label="All Categories",
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
        choices=[('', 'All Statuses')] + list(Expense.STATUS_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    expense_date_from = forms.DateField(
        label='Expense Date From',
        required=False,
        widget=DatePickerInput()
    )
    
    expense_date_to = forms.DateField(
        label='Expense Date To',
        required=False,
        widget=DatePickerInput()
    )
    
    min_amount = MoneyField(
        label='Min Amount',
        required=False
    )
    
    max_amount = MoneyField(
        label='Max Amount',
        required=False
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
            self.fields['category'].queryset = ExpenseCategory.objects.filter(
                is_active=True
            ).order_by('category_type', 'name')
            
            self.fields['academic_session'].queryset = AcademicSession.objects.filter(
                is_active=True
            ).order_by('-start_date')
            
            self.fields['fiscal_period'].queryset = FiscalPeriod.objects.all().order_by('-start_date')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")


class ExpenseApprovalForm(RequiredFieldsMixin, BootstrapFormMixin, forms.Form):
    """Form for approving/rejecting expenses"""
    
    DECISION_CHOICES = [
        ('', '-- Select Decision --'),
        ('APPROVE', 'Approve Expense'),
        ('REJECT', 'Reject Expense'),
    ]
    
    decision = forms.ChoiceField(
        label='Decision',
        choices=DECISION_CHOICES,
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    notes = forms.CharField(
        label='Approval/Rejection Notes',
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'Enter notes...'
        })
    )
    
    def clean_decision(self):
        """Ensure a decision is selected"""
        decision = self.cleaned_data.get('decision')
        if not decision:
            raise ValidationError('Please select a decision.')
        return decision
    
# =============================================================================
# EXPENSE PAYMENT FORMS
# =============================================================================

class ExpensePaymentForm(RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """
    Form for recording expense payments.
    
    Features:
    - Uses school timezone for date validations
    - Auto-calculates total disbursement (amount + fees)
    - Validates against approved expenses
    - Restricts editing of reversed payments
    """
    
    amount = MoneyField(label="Payment Amount")
    processing_fee = MoneyField(label="Processing Fee", required=False)
    bank_charges = MoneyField(label="Bank Charges", required=False)
    
    class Meta:
        model = ExpensePayment
        fields = [
            'expense', 'payment_date', 'amount', 'fiscal_period',
            'payment_method', 'account', 'processing_fee', 'bank_charges',
            'reference_number', 'transaction_id', 'batch_number', 'check_number',
            'payment_details', 'receipt_number', 'notes'
        ]
        widgets = {
            'expense': forms.Select(attrs={'class': 'form-select'}),
            'payment_date': DatePickerInput(),
            'fiscal_period': forms.Select(attrs={'class': 'form-select'}),
            'payment_method': forms.Select(attrs={'class': 'form-select'}),
            'account': forms.Select(attrs={'class': 'form-select'}),
            'reference_number': forms.TextInput(attrs={
                'placeholder': 'Payment reference number'
            }),
            'transaction_id': forms.TextInput(attrs={
                'placeholder': 'Bank/mobile money transaction ID'
            }),
            'batch_number': forms.TextInput(attrs={
                'placeholder': 'Batch number (for grouped payments)'
            }),
            'check_number': forms.TextInput(attrs={
                'placeholder': 'Cheque/Check number (if applicable)'
            }),
            'payment_details': forms.Textarea(attrs={
                'rows': 2,
                'placeholder': 'Additional payment details (JSON format)...'
            }),
            'receipt_number': forms.TextInput(attrs={
                'placeholder': 'Receipt number from vendor/supplier'
            }),
            'notes': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Payment notes...'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        expense = kwargs.pop('expense', None)
        super().__init__(*args, **kwargs)
        
        try:
            # Only show approved expenses (ready for payment)
            self.fields['expense'].queryset = Expense.objects.filter(
                status='APPROVED'
            ).order_by('-expense_date')
            
            # Only open fiscal periods
            self.fields['fiscal_period'].queryset = FiscalPeriod.objects.filter(
                is_closed=False
            ).order_by('-start_date')
            
            # Only active payment methods
            self.fields['payment_method'].queryset = PaymentMethod.objects.filter(
                is_active=True
            ).order_by('name')
            
            # Only cash/bank/mobile money accounts
            self.fields['account'].queryset = Account.objects.filter(
                Q(is_bank_account=True) | Q(is_cash_account=True) | Q(is_mobile_money_account=True),
                is_active=True
            ).order_by('account_number')
            
            # Add helpful labels
            self.fields['account'].label = "Payment From Account"
            self.fields['account'].help_text = "Bank/cash account to disburse funds from"
            
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")
        
        # Pre-populate if expense provided
        if expense:
            self.fields['expense'].initial = expense
            self.fields['amount'].initial = expense.total_amount
        
        # Set default payment date (school timezone) ⭐
        if not self.is_bound:
            from core.utils import get_school_today
            self.fields['payment_date'].initial = get_school_today()
        
        # Disable editing if payment is reversed
        if self.instance.pk:
            if self.instance.reversed:
                # Make all fields read-only for reversed payments
                for field in self.fields:
                    self.fields[field].disabled = True
                    self.fields[field].help_text = "Cannot edit reversed payment"
            
            elif self.instance.status in ['VERIFIED', 'PROCESSED']:
                # Restrict editing for verified/processed payments (only notes allowed)
                restricted_fields = [
                    'expense', 'amount', 'payment_date', 'payment_method',
                    'account', 'processing_fee', 'bank_charges'
                ]
                for field in restricted_fields:
                    if field in self.fields:
                        self.fields[field].disabled = True
                        self.fields[field].help_text = "Cannot modify verified/processed payment"
    
    def clean(self):
        """Validate payment data using school timezone ⭐"""
        cleaned_data = super().clean()
        
        payment_date = cleaned_data.get('payment_date')
        
        if payment_date:
            from core.utils import get_school_today
            today = get_school_today()  # ⭐ SCHOOL TIMEZONE
            
            # Payment date cannot be in the future
            if payment_date > today:
                raise ValidationError({
                    'payment_date': 'Payment date cannot be in the future.'
                })
            
            # Reasonable past date check
            if payment_date < (today - timedelta(days=365)):
                raise ValidationError({
                    'payment_date': 'Payment date seems too far in the past (over 1 year).'
                })
        
        # Validate amount against expense
        expense = cleaned_data.get('expense')
        amount = cleaned_data.get('amount')
        
        if expense and amount:
            if amount <= 0:
                raise ValidationError({
                    'amount': 'Payment amount must be greater than zero.'
                })
            
            # Check if exceeds expense total
            if amount > expense.total_amount:
                raise ValidationError({
                    'amount': f'Payment amount cannot exceed expense total of {expense.total_amount:,.2f}.'
                })
            
            # Check if expense already fully paid
            total_paid = sum(
                p.amount for p in expense.payments.all()
                if p.is_active  # Only count non-reversed payments
            )
            
            remaining = expense.total_amount - total_paid
            
            if amount > remaining:
                raise ValidationError({
                    'amount': (
                        f'Payment amount exceeds remaining balance of {remaining:,.2f}. '
                        f'Already paid: {total_paid:,.2f} out of {expense.total_amount:,.2f}.'
                    )
                })
        
        # Validate fees are non-negative
        processing_fee = cleaned_data.get('processing_fee', Decimal('0.00'))
        bank_charges = cleaned_data.get('bank_charges', Decimal('0.00'))
        
        if processing_fee < 0:
            raise ValidationError({
                'processing_fee': 'Processing fee cannot be negative.'
            })
        
        if bank_charges < 0:
            raise ValidationError({
                'bank_charges': 'Bank charges cannot be negative.'
            })
        
        # Validate fiscal period is not closed
        fiscal_period = cleaned_data.get('fiscal_period')
        if fiscal_period and hasattr(fiscal_period, 'is_closed'):
            if fiscal_period.is_closed:
                raise ValidationError({
                    'fiscal_period': (
                        f'Cannot create payment in closed period: {fiscal_period.name}. '
                        'Please select an open fiscal period.'
                    )
                })
        
        return cleaned_data


class ExpensePaymentReversalForm(BootstrapFormMixin, RequiredFieldsMixin, forms.Form):
    """
    Form for reversing an expense payment (internal correction).
    
    Use this when:
    - Payment was posted to wrong expense
    - Duplicate payment entry
    - Wrong amount entered
    - Wrong vendor paid
    - Other data entry errors
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
            )
        }),
        help_text="Detailed explanation required for audit trail"
    )
    
    requires_approval = forms.BooleanField(
        label="This reversal requires manager approval",
        required=False,
        initial=True,
        help_text="Large or verified payments require approval for reversal"
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
        )
    )
    
    def __init__(self, expense_payment, user, *args, **kwargs):
        self.expense_payment = expense_payment
        self.user = user
        super().__init__(*args, **kwargs)
        
        # Add payment details to help text
        self.fields['reversal_reason'].help_text = (
            f"Reversing payment {expense_payment.reference_number} - "
            f"Amount: {expense_payment.amount:,.2f} - "
            f"Date: {expense_payment.payment_date} - "
            f"Expense: {expense_payment.expense.expense_number}"
        )
        
        # Auto-set approval requirement based on payment status
        if expense_payment.is_verified or expense_payment.amount > Decimal('1000000.00'):
            self.fields['requires_approval'].initial = True
            self.fields['requires_approval'].disabled = True
            self.fields['requires_approval'].help_text = (
                "REQUIRED: This payment is verified or exceeds 1M UGX threshold"
            )
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Validate payment can be reversed
        can_reverse, reason = self.expense_payment.can_be_reversed()
        if not can_reverse:
            raise ValidationError(f"Cannot reverse this payment: {reason}")
        
        # Ensure reason is meaningful
        reversal_reason = cleaned_data.get('reversal_reason', '').strip()
        if len(reversal_reason) < 20:
            raise ValidationError({
                'reversal_reason': 'Please provide a detailed reason (at least 20 characters).'
            })
        
        return cleaned_data


class ExpensePaymentFilterForm(DateRangeFormMixin, BootstrapFormMixin, forms.Form):
    """
    Filter form for expense payment search.
    Uses school timezone for date filters. ⭐
    """
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by reference, transaction ID, expense number...'
        })
    )
    
    fiscal_period = forms.ModelChoiceField(
        label='Fiscal Period',
        queryset=None,
        required=False,
        empty_label="All Periods",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    payment_method = forms.ModelChoiceField(
        label='Payment Method',
        queryset=None,
        required=False,
        empty_label="All Methods",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    account = forms.ModelChoiceField(
        label='Payment Account',
        queryset=None,
        required=False,
        empty_label="All Accounts",
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Account from which payment was made"
    )
    
    status = forms.ChoiceField(
        label='Status',
        choices=[('', 'All Statuses')] + list(ExpensePayment.STATUS_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    # NEW: Filter by reversal state ⭐
    payment_state = forms.ChoiceField(
        label='Payment State',
        choices=[
            ('', 'All Payments'),
            ('active', 'Active Only'),
            ('reversed', 'Reversed Only'),
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Filter by reversal status"
    )
    
    is_verified = forms.NullBooleanField(
        label='Verification',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Verified'),
            ('false', 'Unverified')
        ], attrs={'class': 'form-select'})
    )
    
    payment_date_from = forms.DateField(
        label='Payment Date From',
        required=False,
        widget=DatePickerInput()
    )
    
    payment_date_to = forms.DateField(
        label='Payment Date To',
        required=False,
        widget=DatePickerInput()
    )
    
    min_amount = MoneyField(
        label='Min Amount',
        required=False
    )
    
    max_amount = MoneyField(
        label='Max Amount',
        required=False
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
            self.fields['fiscal_period'].queryset = FiscalPeriod.objects.all().order_by('-start_date')
            
            self.fields['payment_method'].queryset = PaymentMethod.objects.filter(
                is_active=True
            ).order_by('name')
            
            # Only show cash/bank accounts
            self.fields['account'].queryset = Account.objects.filter(
                Q(is_bank_account=True) | Q(is_cash_account=True) | Q(is_mobile_money_account=True),
                is_active=True
            ).order_by('account_number')
            
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")


class BulkExpensePaymentForm(BootstrapFormMixin, RequiredFieldsMixin, forms.Form):
    """
    Form for processing multiple expense payments at once.
    
    Used when paying multiple approved expenses in a single batch
    (e.g., monthly vendor payments).
    """
    
    expense_ids = forms.CharField(
        widget=forms.HiddenInput(),
        required=True
    )
    
    payment_date = forms.DateField(
        label="Payment Date",
        widget=DatePickerInput(),
        help_text="Date when payments were actually made"
    )
    
    payment_method = forms.ModelChoiceField(
        label="Payment Method",
        queryset=None,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="How all payments will be made"
    )
    
    account = forms.ModelChoiceField(
        label="Payment From Account",
        queryset=None,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Bank/cash account to disburse funds from"
    )
    
    batch_number = forms.CharField(
        label="Batch Number",
        max_length=50,
        widget=forms.TextInput(attrs={
            'placeholder': 'E.g., BATCH-2024-01 or upload reference'
        }),
        help_text="Reference number for this payment batch"
    )
    
    payment_notes = forms.CharField(
        label="Payment Notes",
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'Any notes about this payment batch...'
        }),
        required=False
    )
    
    confirm_payment = forms.BooleanField(
        label="I confirm all selected expenses will be paid",
        required=True,
        help_text="Money will be disbursed from the selected account"
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
            # Only active payment methods
            self.fields['payment_method'].queryset = PaymentMethod.objects.filter(
                is_active=True
            ).order_by('name')
            
            # Only cash/bank accounts
            self.fields['account'].queryset = Account.objects.filter(
                Q(is_bank_account=True) | Q(is_cash_account=True) | Q(is_mobile_money_account=True),
                is_active=True
            ).order_by('account_number')
            
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")
        
        # Set default payment date
        if not self.is_bound:
            from core.utils import get_school_today
            self.fields['payment_date'].initial = get_school_today()
    
    def clean_expense_ids(self):
        """Validate and parse expense IDs"""
        ids_string = self.cleaned_data.get('expense_ids', '')
        
        try:
            expense_ids = [int(id.strip()) for id in ids_string.split(',') if id.strip()]
        except ValueError:
            raise ValidationError("Invalid expense IDs")
        
        if not expense_ids:
            raise ValidationError("No expenses selected")
        
        # Validate all expenses exist and are APPROVED
        expenses = Expense.objects.filter(id__in=expense_ids)
        
        if expenses.count() != len(expense_ids):
            raise ValidationError("Some selected expenses do not exist")
        
        non_approved = expenses.exclude(status='APPROVED')
        if non_approved.exists():
            raise ValidationError(
                f"{non_approved.count()} expense(s) are not APPROVED and cannot be paid. "
                "Only approved expenses can be paid."
            )
        
        # Check for fully paid expenses
        for expense in expenses:
            total_paid = sum(
                p.amount for p in expense.payments.all()
                if p.is_active  # Only count non-reversed payments
            )
            
            if total_paid >= expense.total_amount:
                raise ValidationError(
                    f"Expense {expense.expense_number} is already fully paid. "
                    "Please deselect it from the batch."
                )
        
        return expense_ids
    
    def clean_payment_date(self):
        """Validate payment date"""
        payment_date = self.cleaned_data.get('payment_date')
        
        if payment_date:
            from core.utils import get_school_today
            today = get_school_today()
            
            if payment_date > today:
                raise ValidationError(
                    "Payment date cannot be in the future. "
                    "Use actual date when payment was/will be made."
                )
            
            if payment_date < (today - timedelta(days=90)):
                raise ValidationError(
                    "Payment date seems too far in the past. Please verify."
                )
        
        return payment_date


class BulkExpensePaymentVerificationForm(BootstrapFormMixin, forms.Form):
    """
    Form for verifying multiple expense payments at once.
    
    Used by finance manager to mark payments as verified after reconciliation.
    """
    
    payment_ids = forms.CharField(
        widget=forms.HiddenInput(),
        required=True
    )
    
    verification_notes = forms.CharField(
        label="Verification Notes",
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'Any notes for this verification batch...'
        }),
        required=False
    )
    
    confirm_verification = forms.BooleanField(
        label="I confirm all selected payments have been verified",
        required=True,
        help_text="All selected payments will be marked as verified"
    )
    
    def clean_payment_ids(self):
        """Validate and parse payment IDs"""
        ids_string = self.cleaned_data.get('payment_ids', '')
        
        try:
            payment_ids = [int(id.strip()) for id in ids_string.split(',') if id.strip()]
        except ValueError:
            raise ValidationError("Invalid payment IDs")
        
        if not payment_ids:
            raise ValidationError("No payments selected")
        
        # Validate all payments exist
        payments = ExpensePayment.objects.filter(id__in=payment_ids)
        
        if payments.count() != len(payment_ids):
            raise ValidationError("Some selected payments do not exist")
        
        # Check for already verified
        already_verified = payments.filter(is_verified=True)
        if already_verified.exists():
            raise ValidationError(
                f"{already_verified.count()} payment(s) are already verified"
            )
        
        # Check for reversed
        reversed_payments = payments.filter(reversed=True)
        if reversed_payments.exists():
            raise ValidationError(
                f"{reversed_payments.count()} payment(s) are reversed and cannot be verified"
            )
        
        # Check status
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