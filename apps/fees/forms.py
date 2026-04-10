# fees/forms.py

"""
Fee management forms.
All date validations use school timezone for consistency.

Discount system: FeesDiscount replaced by DiscountPolicy / DiscountTier / StudentDiscount.
Refund model removed — refunds are handled directly on Payment.refunded.
"""

from django import forms
from django.forms import inlineformset_factory
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta
from django.db.models import Q
from decimal import Decimal
import logging

from utils.forms import (
    BootstrapFormMixin,
    DateRangeFormMixin,
    RequiredFieldsMixin,
    MoneyFieldsMixin,
    DatePickerInput,
    SearchInput,
    MoneyField,
    MoneyInput,
    PercentageInput,
    PhoneInput,
    validate_phone_number,
)

from core.utils import get_school_today

from .models import (
    DisplayGroup, FeesCategory, FeesStructure, FeesStructureItem,
    FeesStructureBillingSplit, FeeInvoice, FeeInvoiceItem,
    Payment, BadDebtWriteOff, StudentAccount, AccountTransaction,
    ScholarshipProgram, StudentScholarshipApplication, StudentScholarship,
    DiscountPolicy, DiscountTier, StudentDiscount,
)
from students.models import Student
from academics.models import AcademicLevel, Class, AcademicSession
from core.models import PaymentMethod, FiscalPeriod

logger = logging.getLogger(__name__)


# =============================================================================
# DISPLAY GROUP FORMS
# =============================================================================

class DisplayGroupForm(RequiredFieldsMixin, BootstrapFormMixin, forms.ModelForm):

    class Meta:
        model  = DisplayGroup
        fields = [
            'name', 'description', 'display_order', 'color_code',
            'show_as_group', 'show_group_subtotal', 'is_active',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g., Tuition Fees, Boarding Fees'}),
            'description': forms.Textarea(attrs={'rows': 3}),
            'display_order': forms.NumberInput(attrs={'min': '1'}),
            'color_code': forms.TextInput(attrs={'type': 'color'}),
        }


class DisplayGroupFilterForm(BootstrapFormMixin, forms.Form):

    q = forms.CharField(label='Search', required=False,
        widget=SearchInput(attrs={'placeholder': 'Search by name...'}))
    is_active = forms.NullBooleanField(label='Status', required=False,
        widget=forms.Select(choices=[('', 'All'), ('true', 'Active'), ('false', 'Inactive')],
            attrs={'class': 'form-select'}))
    show_as_group = forms.NullBooleanField(label='Show as Group', required=False,
        widget=forms.Select(choices=[('', 'All'), ('true', 'Grouped'), ('false', 'Individual')],
            attrs={'class': 'form-select'}))


# =============================================================================
# FEE CATEGORY FORMS
# =============================================================================

class FeesCategoryForm(RequiredFieldsMixin, BootstrapFormMixin, forms.ModelForm):
 
    class Meta:
        model  = FeesCategory
        fields = [
            'name', 'code', 'description', 'category_type',
            'is_recurring', 'frequency', 'applicability',
            'display_group', 'display_order',
            'is_mandatory', 'is_refundable', 'allows_partial_payment',
            # ── CURRENCY ─────────────────────────────────────────────────────
            'currency',
            # ─────────────────────────────────────────────────────────────────
            'is_taxable', 'default_tax_rate', 'is_active',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g., Tuition Fee'}),
            'code': forms.TextInput(attrs={
                'placeholder': 'e.g., TUI001',
                'style': 'text-transform:uppercase;',
            }),
            'description': forms.Textarea(attrs={'rows': 3}),
            'category_type': forms.Select(attrs={'class': 'form-select'}),
            'frequency': forms.Select(attrs={'class': 'form-select'}),
            'applicability': forms.Select(attrs={'class': 'form-select'}),
            'display_group': forms.Select(attrs={'class': 'form-select'}),
            'display_order': forms.NumberInput(attrs={'min': '1'}),
            # ── currency widget ───────────────────────────────────────────────
            'currency': forms.TextInput(attrs={
                'class': 'form-control text-uppercase',
                'placeholder': 'Leave blank for school currency (e.g. UGX)',
                'maxlength': '3',
            }),
            # ─────────────────────────────────────────────────────────────────
            'default_tax_rate': PercentageInput(),
        }
 
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['display_group'].queryset = DisplayGroup.objects.filter(
            is_active=True).order_by('display_order')
 
        self.fields['currency'].required  = False
        self.fields['currency'].help_text = (
            'ISO 4217 currency code this fee is always billed in. '
            'Leave blank to use the school\'s primary currency. '
            'Example: USD for international tuition; blank for UGX boarding.'
        )
 
    def clean_code(self):
        return self.cleaned_data.get('code', '').upper()
 
    def clean_currency(self):
        code = self.cleaned_data.get('currency', '').upper().strip()
        if code and len(code) != 3:
            raise ValidationError('Currency code must be exactly 3 characters (ISO 4217).')
        return code
 
    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('is_taxable') and not cleaned_data.get('default_tax_rate'):
            self.add_error('default_tax_rate', 'Tax rate required for taxable fees.')
        return cleaned_data


class FeesCategoryFilterForm(BootstrapFormMixin, forms.Form):

    q = forms.CharField(label='Search', required=False,
        widget=SearchInput(attrs={'placeholder': 'Search by name, code...'}))
    category_type = forms.ChoiceField(label='Category Type', required=False,
        choices=[('', 'All Types')] + list(FeesCategory.CATEGORY_TYPE_CHOICES),
        widget=forms.Select(attrs={'class': 'form-select'}))
    applicability = forms.ChoiceField(label='Applicable To', required=False,
        choices=[('', 'All')] + list(FeesCategory.APPLICABILITY_CHOICES),
        widget=forms.Select(attrs={'class': 'form-select'}))
    display_group = forms.ModelChoiceField(label='Display Group', queryset=None,
        required=False, empty_label='All Groups',
        widget=forms.Select(attrs={'class': 'form-select'}))
    is_active = forms.NullBooleanField(label='Status', required=False,
        widget=forms.Select(choices=[('', 'All'), ('true', 'Active'), ('false', 'Inactive')],
            attrs={'class': 'form-select'}))
    is_mandatory = forms.NullBooleanField(label='Mandatory', required=False,
        widget=forms.Select(choices=[('', 'All'), ('true', 'Mandatory'), ('false', 'Optional')],
            attrs={'class': 'form-select'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['display_group'].queryset = DisplayGroup.objects.filter(
            is_active=True).order_by('display_order')


# =============================================================================
# FEE STRUCTURE FORMS
# =============================================================================

class FeesStructureForm(RequiredFieldsMixin, BootstrapFormMixin, forms.ModelForm):

    class Meta:
        model  = FeesStructure
        fields = [
            'name', 'description', 'structure_type', 'academic_year', 'billing_frequency',
            'applicable_sessions', 'academic_levels', 'applicable_classes',
            'boarding_type_filter', 'student_type_filter',
            'payment_terms_days', 'charges_late_fee', 'late_fee_amount',
            'late_fee_percentage', 'grace_period_days',
            'priority', 'is_active', 'effective_date', 'expiry_date',
        ]
        widgets = {
            'name':                forms.TextInput(attrs={'placeholder': 'e.g., Form 1 Day Scholar Fees 2024'}),
            'description':         forms.Textarea(attrs={'rows': 3}),
            'structure_type':      forms.Select(attrs={'class': 'form-select'}),
            'academic_year':       forms.Select(attrs={'class': 'form-select'}),
            'billing_frequency':   forms.Select(attrs={'class': 'form-select'}),
            'applicable_sessions': forms.SelectMultiple(attrs={'class': 'form-select', 'size': '5'}),
            'academic_levels':     forms.SelectMultiple(attrs={'class': 'form-select', 'size': '5'}),
            'applicable_classes':  forms.SelectMultiple(attrs={'class': 'form-select', 'size': '5'}),
            'boarding_type_filter': forms.Select(attrs={'class': 'form-select'}),
            'student_type_filter': forms.Select(attrs={'class': 'form-select'}),
            'payment_terms_days':  forms.NumberInput(attrs={'min': '1'}),
            'late_fee_amount':     MoneyInput(),
            'late_fee_percentage': PercentageInput(),
            'grace_period_days':   forms.NumberInput(attrs={'min': '0'}),
            'priority':            forms.NumberInput(attrs={'min': '1'}),
            'effective_date':      DatePickerInput(),
            'expiry_date':         DatePickerInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from core.models import FiscalYear

        self.fields['academic_year'].queryset = FiscalYear.objects.all().order_by('-start_date')
        self.fields['applicable_sessions'].queryset = AcademicSession.objects.filter(
            is_active=True).order_by('-start_date')
        self.fields['academic_levels'].queryset = AcademicLevel.objects.filter(
            is_active=True).order_by('order')
        self.fields['applicable_classes'].queryset = Class.objects.filter(
            is_active=True).select_related('academic_level', 'academic_session').order_by(
            'academic_level__order', 'section')

        if not self.is_bound and not self.instance.pk:
            self.fields['effective_date'].initial = get_school_today()
            current_year = FiscalYear.get_active_fiscal_year()
            if current_year:
                self.fields['academic_year'].initial = current_year

    def clean(self):
        cleaned_data = super().clean()

        effective_date = cleaned_data.get('effective_date')
        expiry_date    = cleaned_data.get('expiry_date')
        if effective_date and expiry_date and expiry_date < effective_date:
            self.add_error('expiry_date', 'Expiry date cannot be before effective date.')

        applicable_sessions = cleaned_data.get('applicable_sessions')
        applicable_classes  = cleaned_data.get('applicable_classes')

        if applicable_classes and applicable_sessions:
            class_sessions    = {cls.academic_session_id for cls in applicable_classes}
            selected_sessions = {s.id for s in applicable_sessions}
            mismatched = class_sessions - selected_sessions
            if mismatched:
                bad = AcademicSession.objects.filter(id__in=mismatched)
                self.add_error('applicable_classes',
                    f"Some classes belong to sessions not in 'Applicable Sessions': "
                    f"{', '.join(str(s) for s in bad)}.")

        if not applicable_sessions:
            self.add_error('applicable_sessions', 'At least one session must be selected.')
        if not cleaned_data.get('academic_levels'):
            self.add_error('academic_levels', 'At least one academic level must be selected.')

        if cleaned_data.get('charges_late_fee'):
            if not cleaned_data.get('late_fee_amount') and not cleaned_data.get('late_fee_percentage'):
                self.add_error(None, 'A late fee amount or percentage is required when charging late fees.')

        return cleaned_data


class FeesStructureItemForm(RequiredFieldsMixin, BootstrapFormMixin, forms.ModelForm):

    class Meta:
        model  = FeesStructureItem
        fields = [
            'fee_category', 'amount', 'use_variable_amount',
            'currency',
            'is_taxable', 'tax_percentage',
            'default_discount_percentage',
            'scholarship_eligible', 'max_scholarship_discount',
            'is_mandatory', 'is_conditional',
            'print_on_invoice', 'display_order',
            'is_payable_in_installments', 'number_of_installments',
        ]
        widgets = {
            'fee_category': forms.Select(attrs={'class': 'form-select'}),
            'amount':       MoneyInput(),
            'currency':     forms.TextInput(attrs={
                'class':       'form-control text-uppercase',
                'placeholder': 'Blank = inherit from fee category',
                'maxlength':   '3',
            }),
            'tax_percentage':               PercentageInput(),
            'default_discount_percentage':  PercentageInput(),
            'max_scholarship_discount':     PercentageInput(),
            'number_of_installments':       forms.NumberInput(attrs={'min': '1'}),
            'display_order':                forms.NumberInput(attrs={'min': '1'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['fee_category'].queryset = FeesCategory.objects.filter(
            is_active=True).select_related('display_group').order_by(
            'display_group__display_order', 'display_order')

        # Guard every field that may be absent when this form runs inside the
        # inline formset (which uses a restricted fields list).
        optional_fields = (
            'tax_percentage',
            'default_discount_percentage',
            'max_scholarship_discount',
            'number_of_installments',
            'currency',
        )
        for field_name in optional_fields:
            if field_name in self.fields:
                self.fields[field_name].required = False

        if 'currency' in self.fields:
            self.fields['currency'].help_text = (
                "Override the fee category's currency for this structure only. "
                "Resolution chain: item → category → school currency. "
                "Leave blank in most cases."
            )

    def clean_currency(self):
        # Only runs when the field is present on the form.
        code = self.cleaned_data.get('currency', '').upper().strip()
        if code and len(code) != 3:
            raise ValidationError('Currency code must be exactly 3 characters (ISO 4217).')
        return code

    def clean(self):
        cleaned_data = super().clean()

        # Use .get() with safe defaults throughout — these fields may not be
        # present when the form is used inside the inline formset.
        tax_percentage              = cleaned_data.get('tax_percentage') or Decimal('0.00')
        default_discount_percentage = cleaned_data.get('default_discount_percentage') or Decimal('0.00')
        number_of_installments      = cleaned_data.get('number_of_installments') or 1

        cleaned_data['tax_percentage']              = tax_percentage
        cleaned_data['default_discount_percentage'] = default_discount_percentage
        cleaned_data['number_of_installments']      = number_of_installments

        is_taxable = cleaned_data.get('is_taxable', False)
        if is_taxable and tax_percentage == 0:
            self.add_error('tax_percentage',
                'Tax percentage must be > 0 when the item is marked taxable.')
        if not is_taxable and tax_percentage > 0:
            # Auto-correct: non-zero tax implies taxable.
            cleaned_data['is_taxable'] = True

        scholarship_eligible     = cleaned_data.get('scholarship_eligible')
        max_scholarship_discount = cleaned_data.get('max_scholarship_discount')
        if not scholarship_eligible and max_scholarship_discount:
            self.add_error('max_scholarship_discount',
                'Cannot set max scholarship discount when the item is not scholarship eligible.')

        is_payable = cleaned_data.get('is_payable_in_installments')
        if is_payable and number_of_installments < 2:
            self.add_error('number_of_installments',
                'Must be at least 2 when installment payment is enabled.')
        if not is_payable and number_of_installments > 1:
            cleaned_data['number_of_installments'] = 1

        return cleaned_data


class FeesStructureFilterForm(DateRangeFormMixin, BootstrapFormMixin, forms.Form):

    q               = forms.CharField(label='Search', required=False,
        widget=SearchInput(attrs={'placeholder': 'Search by name...'}))
    structure_type  = forms.ChoiceField(label='Structure Type', required=False,
        choices=[('', 'All Types')] + list(FeesStructure.STRUCTURE_TYPE_CHOICES),
        widget=forms.Select(attrs={'class': 'form-select'}))
    academic_year   = forms.ModelChoiceField(label='Academic Year', queryset=None,
        required=False, empty_label='All Years',
        widget=forms.Select(attrs={'class': 'form-select'}))
    billing_frequency = forms.ChoiceField(label='Billing Frequency', required=False,
        choices=[('', 'All')] + list(FeesStructure.BILLING_FREQUENCY_CHOICES),
        widget=forms.Select(attrs={'class': 'form-select'}))
    academic_session = forms.ModelChoiceField(label='Academic Session', queryset=None,
        required=False, empty_label='All Sessions',
        widget=forms.Select(attrs={'class': 'form-select'}))
    academic_level  = forms.ModelChoiceField(label='Academic Level', queryset=None,
        required=False, empty_label='All Levels',
        widget=forms.Select(attrs={'class': 'form-select'}))
    is_active       = forms.NullBooleanField(label='Status', required=False,
        widget=forms.Select(choices=[('', 'All'), ('true', 'Active'), ('false', 'Inactive')],
            attrs={'class': 'form-select'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from core.models import FiscalYear
        self.fields['academic_year'].queryset    = FiscalYear.objects.all().order_by('-start_date')
        self.fields['academic_session'].queryset = AcademicSession.objects.filter(
            is_active=True).order_by('-start_date')
        self.fields['academic_level'].queryset   = AcademicLevel.objects.filter(
            is_active=True).order_by('order')


class FeesStructureBillingSplitForm(BootstrapFormMixin, forms.ModelForm):

    class Meta:
        model  = FeesStructureBillingSplit
        fields = ['fiscal_period', 'percentage', 'sequence', 'description']
        widgets = {
            'fiscal_period': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'percentage':    forms.NumberInput(attrs={
                'step': '0.01', 'min': '0.01', 'max': '100',
                'class': 'form-control form-control-sm', 'placeholder': '0.00',
            }),
            'sequence':    forms.NumberInput(attrs={
                'class': 'form-control form-control-sm', 'min': '1',
            }),
            'description': forms.TextInput(attrs={
                'class': 'form-control form-control-sm',
                'placeholder': 'e.g. Term 1 instalment',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['fiscal_period'].queryset = FiscalPeriod.objects.filter(
            is_active=True, is_closed=False,
        ).order_by('period_number')
        # sequence and description are optional — auto-ordered and auto-labelled
        # by the view if left blank.
        self.fields['sequence'].required    = False
        self.fields['description'].required = False


# ---------------------------------------------------------------------------
# Inline formsets
#
# FeesStructureItemInlineFormSet
#   - fields must be a subset of FeesStructureItemForm.Meta.fields
#   - max_discount_percentage is NOT in Meta.fields so it is excluded here
#   - currency, is_payable_in_installments and number_of_installments ARE
#     included so that FeesStructureItemForm.__init__ and clean() can run
#     without KeyError when the form is used in the formset context
# ---------------------------------------------------------------------------

FeesStructureItemInlineFormSet = inlineformset_factory(
    FeesStructure, FeesStructureItem,
    form=FeesStructureItemForm,
    extra=0,
    can_delete=True,
    fields=[
        'fee_category',
        'amount',
        'use_variable_amount',
        'currency',                     # present in Meta.fields; guarded in __init__
        'is_taxable',
        'tax_percentage',
        'default_discount_percentage',
        'scholarship_eligible',
        'max_scholarship_discount',
        'is_mandatory',
        'is_conditional',
        'is_payable_in_installments',   # paired with number_of_installments in clean()
        'number_of_installments',
        'display_order',
    ],
)

FeesStructureBillingSplitInlineFormSet = inlineformset_factory(
    FeesStructure, FeesStructureBillingSplit,
    form=FeesStructureBillingSplitForm,
    extra=0,
    can_delete=True,
    fields=['fiscal_period', 'percentage', 'sequence', 'description'],
)


# =============================================================================
# INVOICE FORMS
# =============================================================================

class FeeInvoiceFilterForm(DateRangeFormMixin, BootstrapFormMixin, forms.Form):

    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={'placeholder': 'Search by invoice number, student...'}),
    )
    academic_session = forms.ModelChoiceField(
        label='Academic Session',
        queryset=None,
        required=False,
        empty_label='All Sessions',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    fiscal_period = forms.ModelChoiceField(
        label='Fiscal Period',
        queryset=None,
        required=False,
        empty_label='All Periods',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    status = forms.ChoiceField(
        label='Status',
        required=False,
        choices=[('', 'All Statuses')] + list(FeeInvoice.STATUS_CHOICES),
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    issue_date_from = forms.DateField(
        label='Issue Date From',
        required=False,
        widget=DatePickerInput(),
    )
    issue_date_to = forms.DateField(
        label='Issue Date To',
        required=False,
        widget=DatePickerInput(),
    )
    due_date_from = forms.DateField(
        label='Due Date From',
        required=False,
        widget=DatePickerInput(),
    )
    due_date_to = forms.DateField(
        label='Due Date To',
        required=False,
        widget=DatePickerInput(),
    )
    min_amount = MoneyField(
        label='Min Amount',
        required=False,
    )
    max_amount = MoneyField(
        label='Max Amount',
        required=False,
    )
    has_scholarships = forms.NullBooleanField(
        label='Has Scholarships',
        required=False,
        widget=forms.Select(
            choices=[
                ('', 'All'),
                ('true', 'With Scholarships'),
                ('false', 'Without Scholarships'),
            ],
            attrs={'class': 'form-select'},
        ),
    )
    has_discounts = forms.NullBooleanField(
        label='Has Discounts',
        required=False,
        widget=forms.Select(
            choices=[
                ('', 'All'),
                ('true', 'With Discounts'),
                ('false', 'Without Discounts'),
            ],
            attrs={'class': 'form-select'},
        ),
    )
    has_any_reduction = forms.NullBooleanField(
        label='Has Any Reduction',
        required=False,
        widget=forms.Select(
            choices=[
                ('', 'All'),
                ('true', 'With Scholarships or Discounts'),
                ('false', 'No Reductions Applied'),
            ],
            attrs={'class': 'form-select'},
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['academic_session'].queryset = AcademicSession.objects.filter(
            is_active=True,
        ).order_by('-start_date')
        self.fields['fiscal_period'].queryset = FiscalPeriod.objects.all().order_by('-start_date')


# =============================================================================
# PAYMENT FORMS
# =============================================================================

class PaymentForm(RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.ModelForm):

    amount = MoneyField(label='Amount Paid')

    class Meta:
        model  = Payment
        fields = [
            'invoice', 'student', 'amount',
            # ── CURRENCY ─────────────────────────────────────────────────────
            'currency', 'exchange_rate',
            # ─────────────────────────────────────────────────────────────────
            # payment_date and fiscal_period are intentionally omitted —
            # both are set automatically by payment_pre_save signal.
            # ─────────────────────────────────────────────────────────────────
            'payment_method',
            'reference_number', 'transaction_id',
            'bank_name', 'account_number', 'cheque_number', 'cheque_date',
            'mobile_money_provider', 'mobile_number',
            'paid_by_name', 'paid_by_phone', 'paid_by_email', 'paid_by_relationship',
            'remarks',
        ]
        widgets = {
            'invoice': forms.Select(attrs={'class': 'form-select'}),
            'student': forms.Select(attrs={'class': 'form-select'}),
            # ── currency widgets ──────────────────────────────────────────────
            'currency': forms.TextInput(attrs={
                'class':       'form-control text-uppercase',
                'placeholder': 'Leave blank for school currency',
                'maxlength':   '3',
                'id':          'id_payment_currency',
            }),
            'exchange_rate': forms.NumberInput(attrs={
                'class':       'form-control',
                'step':        '0.000001',
                'placeholder': '1.000000',
                'id':          'id_payment_exchange_rate',
            }),
            # ─────────────────────────────────────────────────────────────────
            'payment_method':        forms.Select(attrs={'class': 'form-select', 'id': 'id_payment_method'}),
            'reference_number':      forms.TextInput(attrs={'placeholder': 'Payment reference'}),
            'transaction_id':        forms.TextInput(attrs={'placeholder': 'Bank/mobile money transaction ID'}),
            'bank_name':             forms.TextInput(attrs={'placeholder': 'Bank name'}),
            'account_number':        forms.TextInput(attrs={'placeholder': 'Account number'}),
            'cheque_number':         forms.TextInput(attrs={'placeholder': 'Cheque number'}),
            'cheque_date':           DatePickerInput(),
            'mobile_money_provider': forms.TextInput(attrs={'placeholder': 'e.g., MTN, Airtel'}),
            'mobile_number':         PhoneInput(),
            'paid_by_name':          forms.TextInput(attrs={'placeholder': 'Name of payer'}),
            'paid_by_phone':         PhoneInput(),
            'paid_by_email':         forms.EmailInput(attrs={'placeholder': 'Email of payer'}),
            'paid_by_relationship':  forms.Select(attrs={'class': 'form-select'}),
            'remarks':               forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        invoice = kwargs.pop('invoice', None)

        if invoice and not kwargs.get('instance'):
            kwargs.setdefault('initial', {})
            kwargs['initial']['invoice'] = invoice.id
            kwargs['initial']['student'] = invoice.student.id
            kwargs['initial']['amount']  = invoice.balance

        super().__init__(*args, **kwargs)

        is_new = self.instance._state.adding

        # ── Resolve school currency for help text and validation ──────────────
        try:
            from core.models import FinancialSettings
            school_currency = FinancialSettings.get_school_currency() or 'UGX'
        except Exception:
            school_currency = 'UGX'
        self._school_currency = school_currency

        # ── Currency field setup ──────────────────────────────────────────────
        self.fields['currency'].required  = False
        self.fields['currency'].help_text = (
            f'Currency the parent is paying in. '
            f'Leave blank for {school_currency} (school currency). '
            f'Change only if paying in a foreign currency (e.g. USD).'
        )

        self.fields['exchange_rate'].required  = False
        self.fields['exchange_rate'].help_text = (
            f'Rate to {school_currency} at time of payment. '
            f'Pre-fill from today\'s exchange rates or enter manually. '
            f'Stored permanently — never changes after saving.'
        )

        # Pre-fill exchange_rate from ExchangeRate table if new payment
        # and a currency is already set in initial data
        if is_new:
            selected_currency = self.initial.get('currency', '')
            if selected_currency and selected_currency.upper() != school_currency:
                try:
                    from core.models import ExchangeRate
                    rate = ExchangeRate.get_rate(selected_currency.upper(), school_currency)
                    if rate:
                        self.fields['exchange_rate'].initial = rate
                except Exception:
                    pass

        if not self.fields['exchange_rate'].initial:
            self.fields['exchange_rate'].initial = Decimal('1.000000')

        # ── Payment method queryset ───────────────────────────────────────────
        self.fields['payment_method'].queryset = PaymentMethod.objects.filter(
            is_active=True
        ).order_by('display_order', 'name')

        # ── Invoice / student querysets ───────────────────────────────────────
        if is_new and invoice:
            self.fields['invoice'].widget   = forms.HiddenInput()
            self.fields['student'].widget   = forms.HiddenInput()
            self.fields['invoice'].queryset = FeeInvoice.objects.filter(id=invoice.id)
            self.fields['student'].queryset = Student.objects.filter(id=invoice.student.id)
        elif is_new:
            self.fields['invoice'].queryset = FeeInvoice.objects.exclude(
                status__in=['CANCELLED', 'VOID', 'WRITTEN_OFF', 'UNCOLLECTIBLE', 'BAD_DEBT']
            ).select_related('student').order_by('-issue_date')[:100]
            self.fields['student'].queryset = Student.objects.filter(
                enrollment_status='ACTIVE'
            ).order_by('first_name', 'last_name')
        else:
            self.fields['invoice'].queryset = FeeInvoice.objects.filter(
                id=self.instance.invoice_id
            ).select_related('student')
            self.fields['student'].queryset = Student.objects.filter(
                id=self.instance.student_id
            )

        # ── Edit mode restrictions ────────────────────────────────────────────
        if not is_new:
            if self.instance.reversed or self.instance.refunded:
                for f in self.fields:
                    self.fields[f].disabled = True
            elif self.instance.status == 'COMPLETED' and self.instance.is_verified:
                for f in ['invoice', 'student', 'amount',
                          'payment_method', 'transaction_id',
                          'currency', 'exchange_rate']:
                    if f in self.fields:
                        self.fields[f].disabled = True

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

        # ── Currency / rate cross-check ───────────────────────────────────────
        if currency != self._school_currency and exchange_rate == Decimal('1.000000'):
            self.add_error(
                'exchange_rate',
                f'Currency is set to {currency} but rate is 1.000000. '
                f'Please enter the actual rate to {self._school_currency}.',
            )

        # ── Calculate amount_in_school_currency ───────────────────────────────
        if amount and exchange_rate and exchange_rate > 0:
            cleaned_data['amount_in_school_currency'] = (
                Decimal(str(amount)) * Decimal(str(exchange_rate))
            ).quantize(Decimal('0.01'))

        # ── Validations ──────────────────────────────────────────────────────
        if not self.instance.pk or (not self.instance.reversed and not self.instance.refunded):

            if amount and amount <= 0:
                self.add_error('amount', 'Payment amount must be greater than zero.')

            cheque_date = cleaned_data.get('cheque_date')
            if cheque_date:
                today = get_school_today()
                if cheque_date > today:
                    self.add_error('cheque_date', 'Cheque date cannot be in the future.')

            payment_method = cleaned_data.get('payment_method')
            if payment_method:
                mt = payment_method.method_type.upper()
                if mt in ['BANK_TRANSFER', 'CHEQUE'] and not cleaned_data.get('bank_name'):
                    self.add_error('bank_name', 'Required for bank/cheque payments.')
                if mt == 'CHEQUE':
                    if not cleaned_data.get('cheque_number'):
                        self.add_error('cheque_number', 'Cheque number is required.')
                    if not cleaned_data.get('cheque_date'):
                        self.add_error('cheque_date', 'Cheque date is required.')
                if mt == 'MOBILE_MONEY':
                    if not cleaned_data.get('mobile_money_provider'):
                        self.add_error('mobile_money_provider',
                            'Provider required (e.g., MTN, Airtel).')
                    if not cleaned_data.get('mobile_number'):
                        self.add_error('mobile_number', 'Mobile number is required.')

            for phone_field in ['paid_by_phone', 'mobile_number']:
                val = cleaned_data.get(phone_field)
                if val:
                    try:
                        validate_phone_number(val)
                    except ValidationError as e:
                        self.add_error(phone_field, e)

        return cleaned_data

    def save(self, commit=True):
        """Set amount_in_school_currency before saving."""
        instance = super().save(commit=False)

        amount_sc = self.cleaned_data.get('amount_in_school_currency')
        if amount_sc is not None:
            instance.amount_in_school_currency = amount_sc

        if not instance.currency:
            instance.currency = self._school_currency

        if commit:
            instance.save()
        return instance


class PaymentReversalForm(BootstrapFormMixin, RequiredFieldsMixin, forms.Form):

    reversal_reason = forms.CharField(label='Reversal Reason',
        widget=forms.Textarea(attrs={'rows': 4,
            'placeholder': 'Detailed reason — wrong invoice, duplicate entry, etc.'}),
        help_text='Detailed explanation required for audit trail')
    confirm_reversal = forms.BooleanField(
        label='I confirm this is an internal correction (no money returned)',
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text='For data-entry corrections only. Use Refund if money must be returned.')

    def __init__(self, payment, user, *args, **kwargs):
        self.payment = payment
        self.user    = user
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        can_reverse, reason = self.payment.can_be_reversed()
        if not can_reverse:
            raise ValidationError(f'Cannot reverse this payment: {reason}')
        if len((cleaned_data.get('reversal_reason') or '').strip()) < 20:
            self.add_error('reversal_reason', 'Please provide at least 20 characters.')
        return cleaned_data


class PaymentRefundForm(BootstrapFormMixin, RequiredFieldsMixin, MoneyFieldsMixin, forms.Form):

    refund_amount    = MoneyField(label='Refund Amount')
    refund_method    = forms.ChoiceField(label='Refund Method',
        choices=Payment.REFUND_METHOD_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}))
    refund_reference = forms.CharField(label='Refund Reference', max_length=100,
        widget=forms.TextInput(attrs={'placeholder': 'Bank ref, mobile money ID, etc.'}))
    refund_reason    = forms.CharField(label='Refund Reason',
        widget=forms.Textarea(attrs={'rows': 4,
            'placeholder': 'Why is this refund being issued?'}))
    refund_notes     = forms.CharField(label='Refund Notes', required=False,
        widget=forms.Textarea(attrs={'rows': 3,
            'placeholder': 'Recipient details, approval notes...'}))
    confirm_refund   = forms.BooleanField(
        label='I confirm money will be / has been returned to the payer',
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))

    def __init__(self, payment, user, *args, **kwargs):
        self.payment = payment
        self.user    = user
        super().__init__(*args, **kwargs)
        self.fields['refund_amount'].initial = payment.amount

    def clean_refund_amount(self):
        amount = self.cleaned_data.get('refund_amount')
        if amount and amount <= 0:
            raise ValidationError('Refund amount must be greater than zero.')
        if amount and amount > self.payment.amount:
            raise ValidationError(
                f'Cannot exceed original payment amount of {self.payment.amount:,.2f}.')
        return amount

    def clean(self):
        cleaned_data = super().clean()
        can_refund, reason = self.payment.can_be_refunded()
        if not can_refund:
            raise ValidationError(f'Cannot refund this payment: {reason}')
        if len((cleaned_data.get('refund_reason') or '').strip()) < 20:
            self.add_error('refund_reason', 'Please provide at least 20 characters.')
        if len((cleaned_data.get('refund_reference') or '').strip()) < 5:
            self.add_error('refund_reference', 'Please provide a valid reference number.')
        return cleaned_data


class PaymentFilterForm(DateRangeFormMixin, BootstrapFormMixin, forms.Form):
 
    q                = forms.CharField(label='Search', required=False,
        widget=SearchInput(attrs={'placeholder': 'Payment number, student, reference...'}))
    academic_session = forms.ModelChoiceField(label='Academic Session', queryset=None,
        required=False, empty_label='All Sessions',
        widget=forms.Select(attrs={'class': 'form-select'}))
    fiscal_period    = forms.ModelChoiceField(label='Fiscal Period', queryset=None,
        required=False, empty_label='All Periods',
        widget=forms.Select(attrs={'class': 'form-select'}))
    payment_method   = forms.ModelChoiceField(label='Payment Method', queryset=None,
        required=False, empty_label='All Methods',
        widget=forms.Select(attrs={'class': 'form-select'}))
    status           = forms.ChoiceField(label='Status', required=False,
        choices=[('', 'All Statuses')] + list(Payment.PAYMENT_STATUS_CHOICES),
        widget=forms.Select(attrs={'class': 'form-select'}))
    payment_state    = forms.ChoiceField(label='Payment State', required=False,
        choices=[
            ('', 'All Payments'), ('active', 'Active Only'),
            ('reversed', 'Reversed Only'), ('refunded', 'Refunded Only'),
            ('inactive', 'Reversed or Refunded'),
        ],
        widget=forms.Select(attrs={'class': 'form-select'}))
    # ── CURRENCY ──────────────────────────────────────────────────────────────
    currency         = forms.ChoiceField(label='Currency', required=False,
        choices=[],   # populated in __init__ from live Payment data
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Filter by currency the payment was made in.')
    # ─────────────────────────────────────────────────────────────────────────
    is_verified      = forms.NullBooleanField(label='Verification', required=False,
        widget=forms.Select(
            choices=[('', 'All'), ('true', 'Verified'), ('false', 'Unverified')],
            attrs={'class': 'form-select'}))
    payment_date_from = forms.DateField(label='Payment Date From', required=False,
        widget=DatePickerInput())
    payment_date_to   = forms.DateField(label='Payment Date To', required=False,
        widget=DatePickerInput())
    min_amount        = MoneyField(label='Min Amount', required=False)
    max_amount        = MoneyField(label='Max Amount', required=False)
 
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['academic_session'].queryset = AcademicSession.objects.filter(
            is_active=True).order_by('-start_date')
        self.fields['fiscal_period'].queryset    = FiscalPeriod.objects.all().order_by('-start_date')
        self.fields['payment_method'].queryset   = PaymentMethod.objects.filter(
            is_active=True).order_by('name')
 
        # ── Currency choices from live Payment data ───────────────────────────
        self.fields['currency'].choices = self._build_currency_choices()
 
    @staticmethod
    def _build_currency_choices():
        """
        Build currency choices from currencies actually present in Payment records.
        School currency is always first; other used currencies follow.
        """
        choices = [('', 'All Currencies')]
 
        try:
            from core.models import FinancialSettings
            school_currency = FinancialSettings.get_school_currency() or 'UGX'
        except Exception:
            school_currency = 'UGX'
 
        choices.append((school_currency, f'{school_currency} (School Currency)'))
 
        try:
            others = (
                Payment.objects
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



class BulkPaymentVerificationForm(BootstrapFormMixin, forms.Form):

    payment_ids           = forms.CharField(widget=forms.HiddenInput(), required=True)
    verification_notes    = forms.CharField(label='Verification Notes', required=False,
        widget=forms.Textarea(attrs={'rows': 3}))
    confirm_verification  = forms.BooleanField(
        label='I confirm all selected payments have been verified',
        required=True, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))

    def clean_payment_ids(self):
        ids_string = self.cleaned_data.get('payment_ids', '')
        try:
            payment_ids = [int(i.strip()) for i in ids_string.split(',') if i.strip()]
        except ValueError:
            raise ValidationError('Invalid payment IDs.')
        if not payment_ids:
            raise ValidationError('No payments selected.')

        payments = Payment.objects.filter(id__in=payment_ids)
        if payments.count() != len(payment_ids):
            raise ValidationError('Some selected payments do not exist.')
        if payments.filter(is_verified=True).exists():
            raise ValidationError('Some payments are already verified.')
        if payments.filter(Q(reversed=True) | Q(refunded=True)).exists():
            raise ValidationError('Some payments are reversed or refunded.')
        if payments.exclude(status='COMPLETED').exists():
            raise ValidationError('All payments must be COMPLETED before verifying.')
        return payment_ids


# =============================================================================
# SCHOLARSHIP FORMS
# =============================================================================

class CategoryDiscountTemplateForm(forms.Form):
    """Sub-form for one fee category inside ScholarshipProgramForm."""

    category_code = forms.CharField(widget=forms.HiddenInput())
    category_name = forms.CharField(disabled=True, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control-plaintext fw-bold', 'readonly': True}))
    apply_discount = forms.BooleanField(required=False, label='Cover this category',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input category-apply-check'}))
    discount_type  = forms.ChoiceField(required=False,
        choices=[('percentage','Percentage'),('fixed_amount','Fixed Amount'),
                 ('full_waiver','Full Waiver (100%)'),('none','Not Covered')],
        initial='none',
        widget=forms.Select(attrs={'class': 'form-select form-select-sm category-discount-type'}))
    discount_value = forms.DecimalField(max_digits=10, decimal_places=2, required=False,
        initial=Decimal('0.00'),
        widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm',
            'placeholder': '0.00', 'step': '0.01', 'min': '0'}))
    description    = forms.CharField(required=False,
        widget=forms.TextInput(attrs={'class': 'form-control form-control-sm',
            'placeholder': 'Optional notes...'}))


class CategoryDiscountForm(forms.Form):
    """Sub-form for one fee category inside StudentScholarshipForm."""

    category_code  = forms.CharField(widget=forms.HiddenInput())
    category_name  = forms.CharField(disabled=True, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control-plaintext fw-bold', 'readonly': True}))
    apply_discount = forms.BooleanField(required=False, initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input category-apply-discount'}))
    discount_type  = forms.ChoiceField(
        choices=[('percentage','Percentage'),('fixed_amount','Fixed Amount'),
                 ('full_waiver','Full Waiver (100%)'),('none','Not Covered')],
        initial='percentage',
        widget=forms.Select(attrs={'class': 'form-select category-discount-type'}))
    discount_value = forms.DecimalField(max_digits=10, decimal_places=2, required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control category-discount-value',
            'placeholder': '0.00', 'step': '0.01'}))


class ScholarshipProgramForm(RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.ModelForm):

    class Meta:
        model  = ScholarshipProgram
        fields = [
            'name', 'code', 'scholarship_type', 'description',
            'program_type', 'discount_type',
            'discount_percentage', 'fixed_discount_amount', 'maximum_award_amount',
            'combination_mode', 'auto_award',
            'allows_category_customization', 'category_discount_description',
            'applicable_fee_categories',
            'minimum_gpa', 'minimum_attendance_percentage', 'family_income_threshold',
            'applicable_levels',
            'total_budget_amount', 'requires_budget_tracking', 'maximum_recipients',
            'renewal_policy', 'maximum_duration_years',
            'application_start_date', 'application_end_date', 'award_announcement_date',
            'sponsor_name', 'sponsor_contact', 'external_funding_source',
            'is_active', 'is_accepting_applications', 'valid_sessions',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g., Academic Merit Scholarship 2025/26'}),
            'code': forms.TextInput(attrs={'placeholder': 'e.g., MERIT_2526',
                'style': 'text-transform:uppercase;'}),
            'scholarship_type': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'rows': 4}),
            'program_type': forms.Select(attrs={'class': 'form-select'}),
            'discount_type': forms.Select(attrs={'class': 'form-select'}),
            'combination_mode': forms.Select(attrs={'class': 'form-select'}),
            'discount_percentage': PercentageInput(),
            'fixed_discount_amount': MoneyInput(),
            'maximum_award_amount': MoneyInput(),
            'allows_category_customization': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'auto_award': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'category_discount_description': forms.Textarea(attrs={'rows': 3}),
            'applicable_fee_categories': forms.SelectMultiple(attrs={'class': 'form-select', 'size': '5'}),
            'minimum_gpa': forms.NumberInput(attrs={'min': '0', 'max': '4', 'step': '0.01'}),
            'minimum_attendance_percentage': PercentageInput(),
            'family_income_threshold': MoneyInput(),
            'applicable_levels': forms.SelectMultiple(attrs={'class': 'form-select', 'size': '5'}),
            'total_budget_amount': MoneyInput(),
            'requires_budget_tracking': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'maximum_recipients': forms.NumberInput(attrs={'min': '1'}),
            'renewal_policy': forms.Select(attrs={'class': 'form-select'}),
            'maximum_duration_years': forms.NumberInput(attrs={'min': '1'}),
            'application_start_date': DatePickerInput(),
            'application_end_date': DatePickerInput(),
            'award_announcement_date': DatePickerInput(),
            'sponsor_name': forms.TextInput(attrs={'placeholder': 'Name of sponsor/donor'}),
            'sponsor_contact': forms.Textarea(attrs={'rows': 2}),
            'external_funding_source': forms.TextInput(attrs={'placeholder': 'Foundation, corporation...'}),
            'valid_sessions': forms.SelectMultiple(attrs={'class': 'form-select', 'size': '5'}),
        }

    @staticmethod
    def _category_key(category):
        """Use category.code as JSON key — enforced unique at DB level."""
        return category.code

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['applicable_fee_categories'].queryset = FeesCategory.objects.filter(
            is_active=True).order_by('display_group__display_order', 'display_order')
        self.fields['applicable_levels'].queryset = AcademicLevel.objects.filter(
            is_active=True).order_by('order')
        self.fields['valid_sessions'].queryset = AcademicSession.objects.filter(
            is_active=True).order_by('-start_date')

        existing_template = (
            self.instance.default_category_discounts
            if self.instance.pk and self.instance.default_category_discounts else {}
        )

        self.category_forms = []
        for category in FeesCategory.objects.filter(is_active=True).order_by(
                'display_group__display_order', 'display_order'):
            cat_key        = self._category_key(category)
            config         = existing_template.get(cat_key, {})
            discount_type  = config.get('type', 'none')
            self.category_forms.append({
                'form': CategoryDiscountTemplateForm(
                    data=self.data if self.is_bound else None,
                    prefix=f'cat_{cat_key}',
                    initial={
                        'category_code': cat_key,
                        'category_name': category.name,
                        'apply_discount': discount_type != 'none',
                        'discount_type':  discount_type,
                        'discount_value': config.get('value', 0.00),
                        'description':    config.get('description', ''),
                    },
                ),
                'category': category,
                'code':     cat_key,
            })

    def clean_code(self):
        return self.cleaned_data.get('code', '').upper()

    def is_valid(self):
        main_valid    = super().is_valid()
        discount_type = self.cleaned_data.get('discount_type') if hasattr(self, 'cleaned_data') else None
        if discount_type == 'CATEGORY_SPECIFIC':
            return main_valid and all(item['form'].is_valid() for item in self.category_forms)
        return main_valid

    def clean(self):
        cleaned_data  = super().clean()
        program_type  = cleaned_data.get('program_type')
        discount_type = cleaned_data.get('discount_type')
        total_budget  = cleaned_data.get('total_budget_amount')

        combination_mode = cleaned_data.get('combination_mode')
        if not combination_mode:
            self.add_error('combination_mode', 'Combination mode is required.')

        if program_type in ['BUDGETED', 'SPONSORED'] and not total_budget:
            self.add_error('total_budget_amount', 'Required for budgeted/sponsored programs.')
        if program_type == 'POLICY_BASED' and total_budget:
            self.add_error('total_budget_amount', 'Policy-based programs should not have a budget limit.')

        if discount_type == 'PERCENTAGE' and not cleaned_data.get('discount_percentage'):
            self.add_error('discount_percentage', 'Required for percentage discount type.')
        elif discount_type == 'FIXED_AMOUNT' and not cleaned_data.get('fixed_discount_amount'):
            self.add_error('fixed_discount_amount', 'Required for fixed amount discount type.')
        elif discount_type == 'CATEGORY_SPECIFIC':
            has_any = any(
                item['form'].is_valid()
                and item['form'].cleaned_data.get('apply_discount')
                and item['form'].cleaned_data.get('discount_type') != 'none'
                for item in self.category_forms
            )
            if not has_any:
                self.add_error('discount_type',
                    'Configure a discount for at least one category.')

        start = cleaned_data.get('application_start_date')
        end   = cleaned_data.get('application_end_date')
        if start and end and end < start:
            self.add_error('application_end_date', 'Cannot be before start date.')

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.cleaned_data.get('discount_type') == 'CATEGORY_SPECIFIC':
            template = {}
            for item in self.category_forms:
                if not item['form'].is_valid():
                    continue
                data    = item['form'].cleaned_data
                cat_key = item['code']
                config  = {'type': data.get('discount_type', 'none'),
                           'value': float(data.get('discount_value') or 0)}
                if data.get('description'):
                    config['description'] = data['description']
                template[cat_key] = config if data.get('apply_discount') else {'type': 'none', 'value': 0.0}
            instance.default_category_discounts = template
        else:
            instance.default_category_discounts = {}
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class ScholarshipProgramFilterForm(DateRangeFormMixin, BootstrapFormMixin, forms.Form):

    q                        = forms.CharField(label='Search', required=False,
        widget=SearchInput(attrs={'placeholder': 'Search by name, code...'}))
    scholarship_type         = forms.ChoiceField(label='Scholarship Type', required=False,
        choices=[('', 'All Types')] + list(ScholarshipProgram.SCHOLARSHIP_TYPES),
        widget=forms.Select(attrs={'class': 'form-select'}))
    program_type             = forms.ChoiceField(label='Program Type', required=False,
        choices=[('', 'All Program Types')] + list(ScholarshipProgram.PROGRAM_TYPE_CHOICES),
        widget=forms.Select(attrs={'class': 'form-select'}))
    discount_type            = forms.ChoiceField(label='Discount Type', required=False,
        choices=[('', 'All Discount Types')] + list(ScholarshipProgram.DISCOUNT_TYPE_CHOICES),
        widget=forms.Select(attrs={'class': 'form-select'}))
    combination_mode         = forms.ChoiceField(label='Combination Mode', required=False,
        choices=[('', 'All')] + list(ScholarshipProgram.COMBINATION_MODE_CHOICES),
        widget=forms.Select(attrs={'class': 'form-select'}))
    auto_award               = forms.NullBooleanField(label='Auto-Award', required=False,
        widget=forms.Select(choices=[('', 'All'), ('true', 'Enabled'), ('false', 'Disabled')],
            attrs={'class': 'form-select'}))
    is_active                = forms.NullBooleanField(label='Status', required=False,
        widget=forms.Select(choices=[('', 'All'), ('true', 'Active'), ('false', 'Inactive')],
            attrs={'class': 'form-select'}))
    is_accepting_applications = forms.NullBooleanField(label='Accepting Applications', required=False,
        widget=forms.Select(choices=[('', 'All'), ('true', 'Accepting'), ('false', 'Not Accepting')],
            attrs={'class': 'form-select'}))


class StudentScholarshipApplicationForm(RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.ModelForm):

    class Meta:
        model  = StudentScholarshipApplication
        fields = [
            'student', 'scholarship_program', 'academic_session',
            'requested_amount', 'essay', 'family_income', 'number_of_dependents',
            'special_circumstances', 'current_gpa', 'attendance_percentage',
        ]
        widgets = {
            'student': forms.Select(attrs={'class': 'form-select'}),
            'scholarship_program': forms.Select(attrs={'class': 'form-select'}),
            'academic_session': forms.Select(attrs={'class': 'form-select'}),
            'requested_amount': MoneyInput(),
            'essay': forms.Textarea(attrs={'rows': 8}),
            'family_income': MoneyInput(),
            'number_of_dependents': forms.NumberInput(attrs={'min': '0'}),
            'special_circumstances': forms.Textarea(attrs={'rows': 4}),
            'current_gpa': forms.NumberInput(attrs={'min': '0', 'max': '4', 'step': '0.01'}),
            'attendance_percentage': PercentageInput(),
        }

    def __init__(self, *args, **kwargs):
        student = kwargs.pop('student', None)
        super().__init__(*args, **kwargs)
        if student:
            self.fields['student'].initial = student
        else:
            self.fields['student'].queryset = Student.objects.filter(
                enrollment_status='ACTIVE').order_by('first_name', 'last_name')
        self.fields['scholarship_program'].queryset = ScholarshipProgram.objects.filter(
            is_active=True, is_accepting_applications=True).order_by('name')
        self.fields['academic_session'].queryset = AcademicSession.objects.filter(
            is_active=True).order_by('-start_date')


class ScholarshipApplicationFilterForm(DateRangeFormMixin, BootstrapFormMixin, forms.Form):

    q                   = forms.CharField(label='Search', required=False,
        widget=SearchInput(attrs={'placeholder': 'Search by student, application number...'}))
    scholarship_program = forms.ModelChoiceField(label='Program', queryset=None,
        required=False, empty_label='All Programs',
        widget=forms.Select(attrs={'class': 'form-select'}))
    status              = forms.ChoiceField(label='Status', required=False,
        choices=[('', 'All Statuses')] + list(StudentScholarshipApplication.APPLICATION_STATUS_CHOICES),
        widget=forms.Select(attrs={'class': 'form-select'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['scholarship_program'].queryset = ScholarshipProgram.objects.filter(
            is_active=True).order_by('name')


class StudentScholarshipForm(RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.ModelForm):

    class Meta:
        model  = StudentScholarship
        fields = [
            'student', 'scholarship_program', 'application',
            'amount_awarded', 'start_date', 'end_date',
            'use_category_specific_discounts', 'category_discount_notes',
            'distribution_method', 'amount_per_session', 'amount_per_invoice',
            'max_amount_per_session', 'is_renewable', 'requires_renewal_verification',
            'notes',
        ]
        widgets = {
            'student': forms.Select(attrs={'class': 'form-select'}),
            'scholarship_program': forms.Select(attrs={'class': 'form-select'}),
            'application': forms.Select(attrs={'class': 'form-select'}),
            'amount_awarded': MoneyInput(attrs={'placeholder': '0.00'}),
            'start_date': DatePickerInput(),
            'end_date': DatePickerInput(),
            'distribution_method': forms.Select(attrs={'class': 'form-select'}),
            'amount_per_session': MoneyInput(),
            'amount_per_invoice': MoneyInput(),
            'max_amount_per_session': MoneyInput(),
            'category_discount_notes': forms.Textarea(attrs={'rows': 3}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    @staticmethod
    def _category_key(category):
        return category.code

    def __init__(self, *args, **kwargs):
        application = kwargs.pop('application', None)
        super().__init__(*args, **kwargs)

        self.scholarship_program_instance = None

        if application:
            self.fields['student'].initial             = application.student
            self.fields['scholarship_program'].initial = application.scholarship_program
            self.fields['application'].initial         = application
            self.fields['amount_awarded'].initial      = (
                application.approved_amount or application.requested_amount)
            self.scholarship_program_instance = application.scholarship_program
        elif self.instance.pk and self.instance.scholarship_program_id:
            self.scholarship_program_instance = self.instance.scholarship_program

        if not self.is_bound and not self.instance.pk:
            self.fields['start_date'].initial = get_school_today()

        self.fields['student'].queryset = Student.objects.filter(
            enrollment_status='ACTIVE').order_by('first_name', 'last_name')
        self.fields['scholarship_program'].queryset = ScholarshipProgram.objects.filter(
            is_active=True).order_by('name')
        self.fields['application'].queryset = StudentScholarshipApplication.objects.filter(
            status='APPROVED').order_by('-application_date')

        existing_discounts = {}
        if self.instance.pk and self.instance.category_discounts:
            existing_discounts = self.instance.category_discounts
        elif self.scholarship_program_instance and \
                self.scholarship_program_instance.is_category_specific_discount():
            existing_discounts = self.scholarship_program_instance.get_category_discount_template()

        self.category_forms = []
        for category in FeesCategory.objects.filter(is_active=True).order_by(
                'display_group__display_order', 'display_order'):
            cat_key       = self._category_key(category)
            config        = existing_discounts.get(cat_key, {})
            discount_type = config.get('type', 'none')
            self.category_forms.append({
                'form': CategoryDiscountForm(
                    data=self.data if self.is_bound else None,
                    prefix=f'cat_{cat_key}',
                    initial={
                        'category_code': cat_key,
                        'category_name': category.name,
                        'apply_discount': discount_type != 'none',
                        'discount_type':  discount_type,
                        'discount_value': config.get('value', 0.00),
                    },
                ),
                'category': category,
                'code':     cat_key,
            })

    def is_valid(self):
        main_valid = super().is_valid()
        if self.cleaned_data.get('use_category_specific_discounts'):
            return main_valid and all(item['form'].is_valid() for item in self.category_forms)
        return main_valid

    def clean(self):
        cleaned_data = super().clean()
        use_category = cleaned_data.get('use_category_specific_discounts')

        if use_category:
            category_discounts = {}
            has_any = False
            for item in self.category_forms:
                if not item['form'].is_valid():
                    continue
                data    = item['form'].cleaned_data
                cat_key = item['code']
                if data.get('apply_discount'):
                    t = data.get('discount_type', 'none')
                    if t != 'none':
                        has_any = True
                    category_discounts[cat_key] = {
                        'type': t, 'value': float(data.get('discount_value') or 0)}
                else:
                    category_discounts[cat_key] = {'type': 'none', 'value': 0.0}

            if not has_any:
                raise ValidationError({'use_category_specific_discounts':
                    'Configure a discount for at least one category, or disable category-specific mode.'})

            self.instance.category_discounts = category_discounts
        else:
            self.instance.category_discounts = {}

        start = cleaned_data.get('start_date')
        end   = cleaned_data.get('end_date')
        if start and end and end < start:
            self.add_error('end_date', 'End date cannot be before start date.')

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.cleaned_data.get('use_category_specific_discounts'):
            discounts = {}
            for item in self.category_forms:
                if not item['form'].is_valid():
                    continue
                data    = item['form'].cleaned_data
                cat_key = item['code']
                discounts[cat_key] = (
                    {'type': data.get('discount_type', 'none'),
                     'value': float(data.get('discount_value') or 0)}
                    if data.get('apply_discount')
                    else {'type': 'none', 'value': 0.0}
                )
            instance.category_discounts = discounts
        else:
            instance.category_discounts = {}
        if commit:
            instance.save()
        return instance


class StudentScholarshipFilterForm(BootstrapFormMixin, forms.Form):

    q                   = forms.CharField(label='Search', required=False,
        widget=SearchInput(attrs={'placeholder': 'Student name, program...'}))
    scholarship_program = forms.ModelChoiceField(label='Program', queryset=None,
        required=False, empty_label='All Programs',
        widget=forms.Select(attrs={'class': 'form-select'}))
    status              = forms.ChoiceField(label='Status', required=False,
        choices=[('', 'All Statuses')] + list(StudentScholarship.SCHOLARSHIP_STATUS_CHOICES),
        widget=forms.Select(attrs={'class': 'form-select'}))
    program_type        = forms.ChoiceField(label='Program Type', required=False,
        choices=[('', 'All Program Types')] + list(ScholarshipProgram.PROGRAM_TYPE_CHOICES),
        widget=forms.Select(attrs={'class': 'form-select'}))
    discount_mode       = forms.ChoiceField(label='Discount Mode', required=False,
        choices=[('', 'All Modes'), ('global', 'Global Discount'),
                 ('category_specific', 'Category-Specific')],
        widget=forms.Select(attrs={'class': 'form-select'}))
    active_on_date      = forms.DateField(label='Active On', required=False,
        widget=DatePickerInput(), help_text='Show scholarships active on this date')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['scholarship_program'].queryset = ScholarshipProgram.objects.filter(
            is_active=True).order_by('name')


class ScholarshipApplicationApprovalForm(RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.Form):

    DECISION_CHOICES = [
        ('', '-- Select Decision --'),
        ('APPROVE', 'Approve Application'),
        ('REJECT',  'Reject Application'),
        ('WAITLIST','Add to Waitlist'),
    ]

    decision        = forms.ChoiceField(label='Decision', choices=DECISION_CHOICES,
        required=True, widget=forms.Select(attrs={'class': 'form-select'}))
    approved_amount = MoneyField(label='Approved Amount', required=False,
        help_text='Required if approving')
    decision_reason = forms.CharField(label='Decision Notes', required=False,
        widget=forms.Textarea(attrs={'rows': 4}))

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('decision') == 'APPROVE' and not cleaned_data.get('approved_amount'):
            self.add_error('approved_amount', 'Required when approving an application.')
        return cleaned_data


# =============================================================================
# DISCOUNT POLICY FORMS  (replaces FeesDiscount forms)
# =============================================================================

class DiscountPolicyForm(RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """
    Create / edit a DiscountPolicy.
    Tier rows are managed separately via DiscountTierFormSet.
    """

    class Meta:
        model  = DiscountPolicy
        fields = [
            'name', 'code', 'description', 'category', 'value_mode',
            'tier_dimension', 'application_method', 'combination_mode',
            'auto_apply',
            'flat_percentage', 'flat_fixed_amount', 'category_matrix',
            'applicable_categories',
            'max_discount_per_student', 'max_beneficiaries',
            'total_budget', 'valid_from', 'valid_until', 'valid_sessions',
            'requires_annual_review', 'priority', 'is_active',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g., Sibling Discount'}),
            'code': forms.TextInput(attrs={'placeholder': 'e.g., SIBLING_DISC',
                'style': 'text-transform:uppercase;'}),
            'description': forms.Textarea(attrs={'rows': 3}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'value_mode': forms.Select(attrs={'class': 'form-select'}),
            'tier_dimension': forms.Select(attrs={'class': 'form-select'}),
            'application_method': forms.Select(attrs={'class': 'form-select'}),
            'combination_mode': forms.Select(attrs={'class': 'form-select'}),
            'auto_apply': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'flat_percentage': PercentageInput(),
            'flat_fixed_amount': MoneyInput(),
            'category_matrix': forms.Textarea(attrs={'rows': 4,
                'placeholder': '{"TUITION": 50, "BOARDING": 0, "MEALS": 25}'}),
            'applicable_categories': forms.SelectMultiple(attrs={'class': 'form-select', 'size': '5'}),
            'max_discount_per_student': MoneyInput(),
            'total_budget': MoneyInput(),
            'valid_from': DatePickerInput(),
            'valid_until': DatePickerInput(),
            'valid_sessions': forms.SelectMultiple(attrs={'class': 'form-select', 'size': '4'}),
            'priority': forms.NumberInput(attrs={'min': '1'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['applicable_categories'].queryset = FeesCategory.objects.filter(
            is_active=True).order_by('display_group__display_order', 'display_order')
        self.fields['valid_sessions'].queryset = AcademicSession.objects.filter(
            is_active=True).order_by('-start_date')

        self.fields['category_matrix'].help_text = (
            'JSON: maps FeesCategory.category_type → discount %. '
            'Example: {"TUITION": 50, "BOARDING": 0}. '
            'Only used when value_mode = CATEGORY_MATRIX.'
        )
        self.fields['tier_dimension'].help_text = 'Required when value_mode = TIERED.'
        self.fields['auto_apply'].help_text = (
            'If enabled, DiscountEngine applies this automatically at invoice generation. '
            'Ignored when application_method = MANUAL or NEEDS_APPROVAL.'
        )

    def clean_code(self):
        return self.cleaned_data.get('code', '').upper()

    def clean(self):
        cleaned_data = super().clean()
        value_mode   = cleaned_data.get('value_mode')

        if value_mode == 'FLAT_PERCENTAGE' and not cleaned_data.get('flat_percentage'):
            self.add_error('flat_percentage', 'Required when value_mode is FLAT_PERCENTAGE.')
        elif value_mode == 'FLAT_FIXED' and not cleaned_data.get('flat_fixed_amount'):
            self.add_error('flat_fixed_amount', 'Required when value_mode is FLAT_FIXED.')
        elif value_mode == 'TIERED' and not cleaned_data.get('tier_dimension'):
            self.add_error('tier_dimension', 'Required when value_mode is TIERED.')
        elif value_mode == 'CATEGORY_MATRIX' and not cleaned_data.get('category_matrix'):
            self.add_error('category_matrix', 'Required when value_mode is CATEGORY_MATRIX.')

        valid_from  = cleaned_data.get('valid_from')
        valid_until = cleaned_data.get('valid_until')
        if valid_from and valid_until and valid_until < valid_from:
            self.add_error('valid_until', 'Valid until cannot be before valid from.')

        return cleaned_data


class DiscountPolicyFilterForm(DateRangeFormMixin, BootstrapFormMixin, forms.Form):

    q                  = forms.CharField(label='Search', required=False,
        widget=SearchInput(attrs={'placeholder': 'Search by name, code...'}))
    category           = forms.ChoiceField(label='Category', required=False,
        choices=[('', 'All Categories')] + list(DiscountPolicy.CATEGORY_CHOICES),
        widget=forms.Select(attrs={'class': 'form-select'}))
    value_mode         = forms.ChoiceField(label='Value Mode', required=False,
        choices=[('', 'All')] + list(DiscountPolicy.VALUE_MODE_CHOICES),
        widget=forms.Select(attrs={'class': 'form-select'}))
    application_method = forms.ChoiceField(label='Application', required=False,
        choices=[('', 'All')] + list(DiscountPolicy.APPLICATION_METHOD_CHOICES),
        widget=forms.Select(attrs={'class': 'form-select'}))
    auto_apply         = forms.NullBooleanField(label='Auto-Apply', required=False,
        widget=forms.Select(choices=[('', 'All'), ('true', 'Auto'), ('false', 'Manual')],
            attrs={'class': 'form-select'}))
    is_active          = forms.NullBooleanField(label='Status', required=False,
        widget=forms.Select(choices=[('', 'All'), ('true', 'Active'), ('false', 'Inactive')],
            attrs={'class': 'form-select'}))


class DiscountTierForm(RequiredFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """Inline form for a single DiscountTier row."""

    class Meta:
        model  = DiscountTier
        fields = ['min_value', 'max_value', 'discount_type', 'discount_value', 'label']
        widgets = {
            'min_value':      forms.NumberInput(attrs={'step': '0.01', 'min': '0',
                'placeholder': 'e.g., 3'}),
            'max_value':      forms.NumberInput(attrs={'step': '0.01', 'min': '0',
                'placeholder': 'Leave blank for "and above"'}),
            'discount_type':  forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'discount_value': forms.NumberInput(attrs={'step': '0.01', 'min': '0',
                'placeholder': '% or UGX amount'}),
            'label':          forms.TextInput(attrs={'placeholder': 'e.g., 3rd–4th child: 10% off'}),
        }


DiscountTierFormSet = inlineformset_factory(
    DiscountPolicy, DiscountTier,
    form=DiscountTierForm,
    extra=1, can_delete=True,
    fields=['min_value', 'max_value', 'discount_type', 'discount_value', 'label'],
)


class StudentDiscountForm(RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """Award a DiscountPolicy to a specific student."""

    class Meta:
        model  = StudentDiscount
        fields = [
            'student', 'policy', 'status', 'start_date', 'end_date',
            'override_percentage', 'override_fixed_amount',
            'override_category_matrix', 'override_tier_cap',  # new
            'awarded_by_id', 'awarded_date', 'approved_by_id',
            'notes', 'dimension_context',
        ]
        widgets = {
            'student': forms.Select(attrs={'class': 'form-select'}),
            'policy':  forms.Select(attrs={'class': 'form-select'}),
            'status':  forms.Select(attrs={'class': 'form-select'}),
            'start_date': DatePickerInput(),
            'end_date':   DatePickerInput(),
            'override_percentage':    PercentageInput(),
            'override_fixed_amount':  MoneyInput(),
            'override_tier_cap':      MoneyInput(),          # new
            'override_category_matrix': forms.Textarea(attrs={  # new
                'rows': 3,
                'placeholder': '{"TUITION": 40, "BOARDING": 0}',
            }),
            'awarded_date': DatePickerInput(),
            'notes': forms.Textarea(attrs={'rows': 3}),
            'dimension_context': forms.Textarea(attrs={
                'rows': 2,
                'placeholder': '{"sibling_rank": 3, "staff_grade": 2}',
            }),
        }

    def __init__(self, *args, **kwargs):
        student = kwargs.pop('student', None)
        super().__init__(*args, **kwargs)

        if student:
            self.fields['student'].initial  = student
            self.fields['student'].queryset = Student.objects.filter(id=student.id)
        else:
            self.fields['student'].queryset = Student.objects.filter(
                enrollment_status='ACTIVE').order_by('first_name', 'last_name')

        self.fields['policy'].queryset = DiscountPolicy.objects.filter(
            is_active=True).order_by('priority', 'name')

        if not self.is_bound and not self.instance.pk:
            self.fields['start_date'].initial  = get_school_today()
            self.fields['awarded_date'].initial = get_school_today()

        self.fields['override_percentage'].help_text = (
            'Overrides the policy percentage for this student only. '
            'Leave blank unless you need a different rate than the policy defines.'
        )
        self.fields['override_fixed_amount'].help_text = (
            'Overrides the policy fixed amount for this student only. '
            'Leave blank unless you need a hard cap for this student.'
        )
        self.fields['override_category_matrix'].help_text = (
            'CATEGORY_MATRIX policies only. '
            'JSON map of category type → discount %. '
            'Categories not listed here fall through to the policy matrix. '
            'Example: {"TUITION": 40, "BOARDING": 0}'
        )
        self.fields['override_tier_cap'].help_text = (
            'TIERED policies only. '
            'Tier logic still runs normally but the result is capped at this '
            'amount for this student. Leave blank to apply no cap.'
        )
        self.fields['dimension_context'].help_text = (
            'JSON: values used for tier lookup at award time. '
            'e.g. {"sibling_rank": 3}'
        )

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get('start_date')
        end   = cleaned_data.get('end_date')
        policy = cleaned_data.get('policy')

        if start and end and end < start:
            self.add_error('end_date', 'End date cannot be before start date.')

        # Validate that only one override field is set
        override_fields_set = [
            f for f in [
                'override_percentage',
                'override_fixed_amount',
                'override_category_matrix',
            ]
            if cleaned_data.get(f) not in (None, '', {})
        ]
        if len(override_fields_set) > 1:
            msg = (
                'Only one override field may be set at a time. '
                f'You have set: {", ".join(override_fields_set)}.'
            )
            for f in override_fields_set:
                self.add_error(f, msg)

        # Warn if override_category_matrix is used on the wrong policy type
        if cleaned_data.get('override_category_matrix') and policy:
            if policy.value_mode != 'CATEGORY_MATRIX':
                self.add_error(
                    'override_category_matrix',
                    'This override is only valid for policies with '
                    'value_mode = CATEGORY_MATRIX. '
                    f'The selected policy uses {policy.value_mode}.'
                )

        # Warn if override_tier_cap is used on the wrong policy type
        if cleaned_data.get('override_tier_cap') is not None and policy:
            if policy.value_mode != 'TIERED':
                self.add_error(
                    'override_tier_cap',
                    'This override is only valid for policies with '
                    'value_mode = TIERED. '
                    f'The selected policy uses {policy.value_mode}.'
                )

        return cleaned_data
    
    def clean_override_category_matrix(self):
        return self.cleaned_data.get("override_category_matrix") or {}


class StudentDiscountFilterForm(BootstrapFormMixin, forms.Form):

    q       = forms.CharField(label='Search', required=False,
        widget=SearchInput(attrs={'placeholder': 'Student name, policy...'}))
    policy  = forms.ModelChoiceField(label='Policy', queryset=None,
        required=False, empty_label='All Policies',
        widget=forms.Select(attrs={'class': 'form-select'}))
    status  = forms.ChoiceField(label='Status', required=False,
        choices=[('', 'All Statuses')] + list(StudentDiscount.STATUS_CHOICES),
        widget=forms.Select(attrs={'class': 'form-select'}))
    active_on_date = forms.DateField(label='Active On', required=False,
        widget=DatePickerInput(), help_text='Show discounts active on this date')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['policy'].queryset = DiscountPolicy.objects.filter(
            is_active=True).order_by('priority', 'name')


# =============================================================================
# STUDENT ACCOUNT FORMS
# =============================================================================

class StudentAccountForm(RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.ModelForm):

    class Meta:
        model  = StudentAccount
        fields = ['student', 'credit_limit', 'status']
        widgets = {
            'student':      forms.Select(attrs={'class': 'form-select'}),
            'credit_limit': MoneyInput(),
            'status':       forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['student'].queryset = Student.objects.filter(
            enrollment_status='ACTIVE').order_by('first_name', 'last_name')
        self.fields['credit_limit'].help_text = 'Maximum negative balance allowed'


class StudentAccountAdjustmentForm(RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.Form):

    ADJUSTMENT_TYPE_CHOICES = [
        ('CREDIT', 'Credit (Add to Account)'),
        ('DEBIT',  'Debit (Subtract from Account)'),
    ]

    adjustment_type  = forms.ChoiceField(label='Adjustment Type',
        choices=ADJUSTMENT_TYPE_CHOICES, required=True,
        widget=forms.Select(attrs={'class': 'form-select'}))
    amount           = MoneyField(label='Amount', required=True,
        help_text='Always positive')
    reason           = forms.CharField(label='Reason', required=True,
        widget=forms.Textarea(attrs={'rows': 4,
            'placeholder': 'Detailed reason for this adjustment...'}))
    reference_number = forms.CharField(label='Reference Number', required=False,
        max_length=50, widget=forms.TextInput(attrs={'placeholder': 'Optional reference'}))

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount and amount <= 0:
            raise ValidationError('Amount must be greater than zero.')
        return amount


class StudentAccountFilterForm(BootstrapFormMixin, forms.Form):

    q              = forms.CharField(label='Search', required=False,
        widget=SearchInput(attrs={'placeholder': 'Search by student name...'}))
    status         = forms.ChoiceField(label='Status', required=False,
        choices=[('', 'All Statuses')] + list(StudentAccount.ACCOUNT_STATUS_CHOICES),
        widget=forms.Select(attrs={'class': 'form-select'}))
    balance_status = forms.ChoiceField(label='Balance', required=False,
        choices=[
            ('', 'All'), ('positive', 'Credit (Overpaid)'),
            ('zero', 'Zero Balance'), ('negative', 'Debit (Outstanding)'),
        ],
        widget=forms.Select(attrs={'class': 'form-select'}))
    min_balance    = MoneyField(label='Min Balance', required=False)
    max_balance    = MoneyField(label='Max Balance', required=False)


# =============================================================================
# ACCOUNT TRANSACTION FORMS
# =============================================================================

class AccountTransactionFilterForm(DateRangeFormMixin, BootstrapFormMixin, forms.Form):

    q                = forms.CharField(label='Search', required=False,
        widget=SearchInput(attrs={'placeholder': 'Student name, reference...'}))
    student          = forms.ModelChoiceField(label='Student', queryset=None,
        required=False, empty_label='All Students',
        widget=forms.Select(attrs={'class': 'form-select'}))
    transaction_type = forms.ChoiceField(label='Transaction Type', required=False,
        choices=[('', 'All Types')] + list(AccountTransaction.TRANSACTION_TYPES),
        widget=forms.Select(attrs={'class': 'form-select'}))
    date_from        = forms.DateField(label='From Date', required=False,
        widget=DatePickerInput())
    date_to          = forms.DateField(label='To Date', required=False,
        widget=DatePickerInput())
    min_amount       = MoneyField(label='Min Amount', required=False)
    max_amount       = MoneyField(label='Max Amount', required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['student'].queryset = Student.objects.filter(
            enrollment_status='ACTIVE').order_by('first_name', 'last_name')


# =============================================================================
# MULTIPLE INVOICE PAYMENT FORM
# =============================================================================

class MultipleInvoicePaymentForm(RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.Form):
    """
    Form for recording a payment against multiple outstanding invoices.

    EXCLUDED FIELDS (set automatically):
    - payment_date   → set by payment_pre_save signal to today
    - fiscal_period  → set by payment_pre_save signal to current period

    EXCLUDED FIELDS (handled by HTMX student filter in the template):
    - selection_method  → replaced by student Select2 + session multi-select
    - students          → replaced by HTMX outstanding_invoices_for_student endpoint
    - invoice_numbers   → replaced by the dynamic invoice table rows

    EXCLUDED FIELDS (redundant — computed from per-row amounts in the view):
    - total_amount  → the view sums amount_N POST values directly; no separate
                      total field is needed since the table rows are the source
                      of truth and the sidebar/footer show the running total live.
    """

    allocation_method = forms.ChoiceField(
        label='Allocation Method',
        choices=[
            ('oldest_first',   'Oldest First (Recommended)'),
            ('newest_first',   'Newest First'),
            ('largest_first',  'Largest Balance First'),
            ('smallest_first', 'Smallest Balance First'),
            ('equal',          'Equal Distribution'),
        ],
        initial='oldest_first',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    payment_method = forms.ModelChoiceField(
        label='Payment Method',
        queryset=None,
        widget=forms.Select(attrs={
            'class': 'form-select',
            'id':    'id_payment_method',
        }),
    )

    reference_number = forms.CharField(
        label='Reference Number',
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Payment reference'}),
    )

    transaction_id = forms.CharField(
        label='Transaction ID',
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Bank/mobile transaction ID'}),
    )

    bank_name = forms.CharField(
        label='Bank Name',
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'e.g. Stanbic, Centenary'}),
    )

    account_number = forms.CharField(
        label='Account Number',
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Account number'}),
    )

    cheque_number = forms.CharField(
        label='Cheque Number',
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Cheque number'}),
    )

    cheque_date = forms.DateField(
        label='Cheque Date',
        required=False,
        widget=DatePickerInput(),
    )

    mobile_money_provider = forms.CharField(
        label='Mobile Money Provider',
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'e.g., MTN, Airtel'}),
    )

    mobile_number = forms.CharField(
        label='Mobile Number',
        max_length=20,
        required=False,
        widget=PhoneInput(),
    )

    # ── Currency ──────────────────────────────────────────────────────────────
    currency = forms.CharField(
        label='Payment Currency',
        max_length=3,
        required=False,
        widget=forms.TextInput(attrs={
            'class':       'form-control text-uppercase',
            'placeholder': 'Leave blank for school currency',
            'maxlength':   '3',
            'id':          'id_payment_currency',
        }),
    )

    exchange_rate = forms.DecimalField(
        label='Exchange Rate Used',
        required=False,
        initial=Decimal('1.000000'),
        max_digits=12,
        decimal_places=6,
        widget=forms.NumberInput(attrs={
            'class':       'form-control',
            'step':        '0.000001',
            'placeholder': '1.000000',
            'id':          'id_payment_exchange_rate',
        }),
    )
    # ─────────────────────────────────────────────────────────────────────────

    paid_by_name = forms.CharField(
        label='Paid By (Name)',
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Name of payer'}),
    )

    paid_by_phone = forms.CharField(
        label='Paid By (Phone)',
        max_length=20,
        required=False,
        widget=PhoneInput(),
    )

    paid_by_relationship = forms.ChoiceField(
        label='Relationship to Student',
        required=False,
        choices=[('', '— Select —')] + list(Payment.PAYER_RELATIONSHIP_CHOICES),
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    remarks = forms.CharField(
        label='Remarks',
        required=False,
        widget=forms.Textarea(attrs={'rows': 3}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['payment_method'].queryset = PaymentMethod.objects.filter(
            is_active=True
        ).order_by('display_order', 'name')

        # ── Resolve school currency for help text and validation ──────────────
        try:
            from core.models import FinancialSettings
            school_currency = FinancialSettings.get_school_currency() or 'UGX'
        except Exception:
            school_currency = 'UGX'
        self._school_currency = school_currency

        self.fields['currency'].help_text = (
            f'Currency the parent is paying in. '
            f'Leave blank for {school_currency} (school currency). '
            f'Change only if paying in a foreign currency (e.g. USD).'
        )
        self.fields['exchange_rate'].help_text = (
            f'Rate to {school_currency} at time of payment. '
            f'Pre-fill from today\'s exchange rates or enter manually. '
            f'Stored permanently — never changes after saving.'
        )

        if not self.is_bound:
            self.fields['exchange_rate'].initial = Decimal('1.000000')

    def clean(self):
        cleaned_data   = super().clean()
        payment_method = cleaned_data.get('payment_method')

        # ── Currency normalisation ────────────────────────────────────────────
        school_currency = getattr(self, '_school_currency', 'UGX')
        currency        = (cleaned_data.get('currency') or '').upper().strip()
        exchange_rate   = cleaned_data.get('exchange_rate') or Decimal('1.000000')

        if currency and len(currency) != 3:
            self.add_error(
                'currency',
                'Currency code must be exactly 3 characters (ISO 4217).',
            )
        else:
            # Normalise: blank → school currency
            cleaned_data['currency'] = currency or school_currency

        if exchange_rate <= 0:
            self.add_error('exchange_rate', 'Exchange rate must be greater than zero.')
        else:
            cleaned_data['exchange_rate'] = exchange_rate

        # ── Currency / rate cross-check ───────────────────────────────────────
        effective_currency = cleaned_data.get('currency', school_currency)
        if (
            effective_currency != school_currency and
            exchange_rate == Decimal('1.000000')
        ):
            self.add_error(
                'exchange_rate',
                f'Currency is set to {effective_currency} but rate is 1.000000. '
                f'Please enter the actual rate to {school_currency}.',
            )

        # ── Cheque date validation ────────────────────────────────────────────
        cheque_date = cleaned_data.get('cheque_date')
        if cheque_date:
            today = get_school_today()
            if cheque_date > today:
                self.add_error('cheque_date', 'Cheque date cannot be in the future.')

        # ── Method-specific required fields ───────────────────────────────────
        if payment_method:
            mt = payment_method.method_type.upper()
            if mt in ['BANK_TRANSFER', 'CHEQUE'] and not cleaned_data.get('bank_name'):
                self.add_error('bank_name', 'Required for bank/cheque payments.')
            if mt == 'CHEQUE':
                if not cleaned_data.get('cheque_number'):
                    self.add_error('cheque_number', 'Cheque number is required.')
                if not cleaned_data.get('cheque_date'):
                    self.add_error('cheque_date', 'Cheque date is required.')
            if mt == 'MOBILE_MONEY':
                if not cleaned_data.get('mobile_money_provider'):
                    self.add_error('mobile_money_provider',
                        'Provider required (e.g., MTN, Airtel).')
                if not cleaned_data.get('mobile_number'):
                    self.add_error('mobile_number', 'Mobile number is required.')

        # ── Phone validation ──────────────────────────────────────────────────
        for phone_field in ['paid_by_phone', 'mobile_number']:
            val = cleaned_data.get(phone_field)
            if val:
                try:
                    validate_phone_number(val)
                except ValidationError as e:
                    self.add_error(phone_field, e)

        return cleaned_data