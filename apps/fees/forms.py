# fees/forms.py

"""
Fee management forms with timezone support.
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
    PhoneNumberField,
    PhoneInput,
    validate_future_date,  # ⭐ Uses school timezone
    validate_past_date,  # ⭐ Uses school timezone
    validate_date_not_before,  # ⭐ Uses school timezone
    validate_date_not_after,  # ⭐ Uses school timezone
    validate_phone_number,
    validate_positive_amount,
    validate_percentage,
)

# Import school timezone utilities ⭐
from core.utils import get_school_today, get_school_current_time

from .models import (
    DisplayGroup, FeesCategory, FeesStructure, FeesStructureItem, FeesStructureBillingSplit,
    FeeInvoice, FeeInvoiceItem, Payment, BadDebtWriteOff, StudentAccount,
    ScholarshipProgram, StudentScholarshipApplication, StudentScholarship,
    FeesDiscount, Refund, AccountTransaction
)
from students.models import Student
from academics.models import AcademicLevel, Class, AcademicSession
from core.models import PaymentMethod, FiscalPeriod

logger = logging.getLogger(__name__)


# =============================================================================
# DISPLAY GROUP FORMS
# =============================================================================

class DisplayGroupForm(RequiredFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """Form for creating/editing display groups"""
    
    class Meta:
        model = DisplayGroup
        fields = [
            'name', 'description', 'display_order', 'color_code',
            'show_as_group', 'show_group_subtotal', 'is_active'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'e.g., Tuition Fees, Boarding Fees'
            }),
            'description': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Description of this fee group...'
            }),
            'display_order': forms.NumberInput(attrs={
                'min': '1',
                'placeholder': '1'
            }),
            'color_code': forms.TextInput(attrs={
                'type': 'color',
                'placeholder': '#6f42c1'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['display_order'].help_text = "Lower numbers appear first on invoices"
        self.fields['show_as_group'].help_text = (
            "If checked, items are grouped together. If unchecked, items show individually."
        )


class DisplayGroupFilterForm(BootstrapFormMixin, forms.Form):
    """Filter form for display group search"""
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by name...'
        })
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
    
    show_as_group = forms.NullBooleanField(
        label='Show as Group',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Grouped'),
            ('false', 'Individual Items')
        ], attrs={'class': 'form-select'})
    )


# =============================================================================
# FEE CATEGORY FORMS
# =============================================================================

class FeesCategoryForm(RequiredFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """Form for creating/editing fee categories"""
    
    class Meta:
        model = FeesCategory
        fields = [
            'name', 'code', 'description', 'category_type',
            'is_recurring', 'frequency', 'applicability',
            'display_group', 'display_order',
            'is_mandatory', 'is_refundable', 'allows_partial_payment',
            'is_taxable', 'default_tax_rate', 'is_active'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'e.g., Tuition Fee, Boarding Fee'
            }),
            'code': forms.TextInput(attrs={
                'placeholder': 'e.g., TUI001, BRD001',
                'style': 'text-transform: uppercase;'
            }),
            'description': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Description of this fee...'
            }),
            'category_type': forms.Select(attrs={'class': 'form-select'}),
            'frequency': forms.Select(attrs={'class': 'form-select'}),
            'applicability': forms.Select(attrs={'class': 'form-select'}),
            'display_group': forms.Select(attrs={'class': 'form-select'}),
            'display_order': forms.NumberInput(attrs={'min': '1'}),
            'default_tax_rate': PercentageInput(),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
            self.fields['display_group'].queryset = DisplayGroup.objects.filter(
                is_active=True
            ).order_by('display_order')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")
        
        self.fields['code'].help_text = "Unique code (e.g., TUI001)"
    
    def clean_code(self):
        """Ensure code is uppercase"""
        code = self.cleaned_data.get('code', '')
        return code.upper()
    
    def clean(self):
        """Validate fee category data"""
        cleaned_data = super().clean()
        
        is_taxable = cleaned_data.get('is_taxable')
        tax_rate = cleaned_data.get('default_tax_rate')
        
        if is_taxable and (tax_rate is None or tax_rate == Decimal('0.00')):
            self.add_error('default_tax_rate', 
                'Tax rate must be specified for taxable fees.'
            )
        
        return cleaned_data


class FeesCategoryFilterForm(BootstrapFormMixin, forms.Form):
    """Filter form for fee category search"""
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by name, code...'
        })
    )
    
    category_type = forms.ChoiceField(
        label='Category Type',
        choices=[('', 'All Types')] + list(FeesCategory.CATEGORY_TYPE_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    applicability = forms.ChoiceField(
        label='Applicable To',
        choices=[('', 'All')] + list(FeesCategory.APPLICABILITY_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    display_group = forms.ModelChoiceField(
        label='Display Group',
        queryset=None,
        required=False,
        empty_label="All Groups",
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
    
    is_mandatory = forms.NullBooleanField(
        label='Mandatory',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Mandatory'),
            ('false', 'Optional')
        ], attrs={'class': 'form-select'})
    )
    
    is_taxable = forms.NullBooleanField(
        label='Taxable',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Taxable'),
            ('false', 'Non-Taxable')
        ], attrs={'class': 'form-select'})
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
            self.fields['display_group'].queryset = DisplayGroup.objects.filter(
                is_active=True
            ).order_by('display_order')
        except Exception as e:
            logger.error(f"Error setting display group queryset: {e}")


# =============================================================================
# FEE STRUCTURE FORMS
# =============================================================================

class FeesStructureForm(RequiredFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """
    Form for creating/editing fee structures.
    Uses school timezone for date validations. ⭐
    """
    
    class Meta:
        model = FeesStructure
        fields = [
            'name', 'description', 'structure_type', 'academic_year', 'billing_frequency',
            'applicable_sessions', 'academic_levels', 'applicable_classes',
            'boarding_type_filter', 'student_type_filter',
            'payment_terms_days', 'charges_late_fee', 'late_fee_amount',
            'late_fee_percentage', 'grace_period_days',
            'priority', 'is_active', 'effective_date', 'expiry_date'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'e.g., Form 1 Day Scholar Fees 2024'
            }),
            'description': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Description of this fee structure...'
            }),
            'structure_type': forms.Select(attrs={'class': 'form-select'}),
            'academic_year': forms.Select(attrs={'class': 'form-select'}),
            'billing_frequency': forms.Select(attrs={'class': 'form-select'}),
            'applicable_sessions': forms.SelectMultiple(attrs={
                'class': 'form-select',
                'size': '5'
            }),
            'academic_levels': forms.SelectMultiple(attrs={
                'class': 'form-select',
                'size': '5'
            }),
            'applicable_classes': forms.SelectMultiple(attrs={
                'class': 'form-select',
                'size': '5'
            }),
            'boarding_type_filter': forms.Select(attrs={'class': 'form-select'}),
            'student_type_filter': forms.Select(attrs={'class': 'form-select'}),
            'payment_terms_days': forms.NumberInput(attrs={'min': '1'}),
            'late_fee_amount': MoneyInput(),
            'late_fee_percentage': PercentageInput(),
            'grace_period_days': forms.NumberInput(attrs={'min': '0'}),
            'priority': forms.NumberInput(attrs={'min': '1'}),
            'effective_date': DatePickerInput(),
            'expiry_date': DatePickerInput(),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        from core.models import FiscalYear
        self.fields['academic_year'].queryset = FiscalYear.objects.all().order_by('-start_date')
        
        self.fields['applicable_sessions'].queryset = AcademicSession.objects.filter(
            is_active=True
        ).order_by('-start_date')
        
        self.fields['academic_levels'].queryset = AcademicLevel.objects.filter(
            is_active=True
        ).order_by('order')
        
        self.fields['applicable_classes'].queryset = Class.objects.filter(
            is_active=True
        ).select_related('academic_level', 'academic_session').order_by(
            'academic_level__order', 'section'
        )
        
        if not self.is_bound and not self.instance.pk:
            self.fields['effective_date'].initial = get_school_today()  # ⭐ SCHOOL TIMEZONE
            
            current_year = FiscalYear.get_active_fiscal_year()
            if current_year:
                self.fields['academic_year'].initial = current_year
        
        self.fields['academic_year'].help_text = "Academic/Fiscal year this structure belongs to"
        self.fields['billing_frequency'].help_text = (
            "How fees will be billed: ONCE (one-time), PER_PERIOD (equal splits), "
            "SPLIT_CUSTOM (custom percentages), ON_ENROLLMENT (when student enrolls)"
        )
        self.fields['applicable_sessions'].help_text = (
            "Sessions where this fee structure applies. "
            "Only classes from these sessions can be selected."
        )
        self.fields['academic_levels'].help_text = "Academic levels this structure applies to"
        self.fields['applicable_classes'].help_text = (
            "Leave empty to apply to ALL classes in selected levels/sessions. "
            "If specified, must belong to the selected sessions."
        )
        self.fields['priority'].help_text = "Lower number = higher priority when multiple structures match"
    
    def clean(self):
        """Validate fee structure data using school timezone ⭐"""
        cleaned_data = super().clean()
        
        academic_year = cleaned_data.get('academic_year')
        applicable_sessions = cleaned_data.get('applicable_sessions')
        
        if academic_year and applicable_sessions:
            session_years = set()
            for session in applicable_sessions:
                session_years.add(session.year_name)
            
            if len(session_years) > 1:
                self.add_error('applicable_sessions',
                    f'Selected sessions span multiple years: {", ".join(session_years)}. '
                    f'Please select sessions from {academic_year.name} only.'
                )
        
        effective_date = cleaned_data.get('effective_date')
        expiry_date = cleaned_data.get('expiry_date')
        
        if effective_date and expiry_date:
            try:
                validate_date_not_before(expiry_date, effective_date, "Expiry date")
            except ValidationError as e:
                self.add_error('expiry_date', e)
        
        applicable_classes = cleaned_data.get('applicable_classes')
        
        if applicable_classes and applicable_sessions:
            class_sessions = set(
                cls.academic_session.id for cls in applicable_classes
            )
            selected_sessions = set(
                session.id for session in applicable_sessions
            )
            
            mismatched = class_sessions - selected_sessions
            if mismatched:
                mismatched_sessions = AcademicSession.objects.filter(
                    id__in=mismatched
                )
                self.add_error('applicable_classes',
                    f"Some selected classes belong to sessions not in 'Applicable Sessions': "
                    f"{', '.join(str(s) for s in mismatched_sessions)}. "
                    f"Please select only classes from the chosen sessions."
                )
        
        charges_late_fee = cleaned_data.get('charges_late_fee')
        late_fee_amount = cleaned_data.get('late_fee_amount')
        late_fee_percentage = cleaned_data.get('late_fee_percentage')
        
        if charges_late_fee:
            if not late_fee_amount and not late_fee_percentage:
                self.add_error(None,
                    'Either late fee amount or percentage must be specified when charging late fees.'
                )
        
        if not applicable_sessions:
            self.add_error('applicable_sessions',
                'At least one academic session must be selected.'
            )
        
        academic_levels = cleaned_data.get('academic_levels')
        if not academic_levels:
            self.add_error('academic_levels',
                'At least one academic level must be selected.'
            )
        
        return cleaned_data


class FeesStructureItemForm(RequiredFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """Form for fee structure items (inline formset use)"""
    
    class Meta:
        model = FeesStructureItem
        fields = [
            'fee_category', 'amount', 'use_variable_amount',
            'is_taxable', 'tax_percentage',
            'default_discount_percentage',
            'scholarship_eligible', 'max_scholarship_discount',
            'is_mandatory', 'is_conditional',
            'print_on_invoice', 'display_order',
            'is_payable_in_installments', 'number_of_installments',
        ]
        widgets = {
            'fee_category': forms.Select(attrs={'class': 'form-select'}),
            'amount': MoneyInput(),
            'tax_percentage': PercentageInput(),
            'default_discount_percentage': PercentageInput(),
            'max_scholarship_discount': PercentageInput(),
            'number_of_installments': forms.NumberInput(attrs={'min': '1'}),
            'display_order': forms.NumberInput(attrs={'min': '1'}),
            'use_variable_amount': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_taxable': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'scholarship_eligible': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_mandatory': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_conditional': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'print_on_invoice': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_payable_in_installments': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.fields['fee_category'].queryset = FeesCategory.objects.filter(
            is_active=True
        ).select_related('display_group').order_by(
            'display_group__display_order', 'display_order'
        )
    
    def clean(self):
        """Validate structure item data"""
        cleaned_data = super().clean()
        
        scholarship_eligible = cleaned_data.get('scholarship_eligible')
        max_scholarship_discount = cleaned_data.get('max_scholarship_discount')
        
        if not scholarship_eligible and max_scholarship_discount:
            self.add_error('max_scholarship_discount',
                'Cannot set max scholarship discount if item is not scholarship eligible.'
            )
        
        is_taxable = cleaned_data.get('is_taxable', False)
        tax_percentage = cleaned_data.get('tax_percentage') or Decimal('0.00')
        
        if is_taxable and tax_percentage == 0:
            self.add_error('tax_percentage',
                'Tax percentage must be greater than 0 if item is taxable.'
            )
        
        if not is_taxable and tax_percentage > 0:
            cleaned_data['is_taxable'] = True
        
        is_payable_in_installments = cleaned_data.get('is_payable_in_installments')
        number_of_installments = cleaned_data.get('number_of_installments')
        
        if is_payable_in_installments and number_of_installments < 2:
            self.add_error('number_of_installments',
                'Number of installments must be at least 2 when installments are enabled.'
            )
        
        if not is_payable_in_installments and number_of_installments > 1:
            cleaned_data['number_of_installments'] = 1
        
        return cleaned_data


class FeesStructureFilterForm(DateRangeFormMixin, BootstrapFormMixin, forms.Form):
    """
    Filter form for fee structure search.
    Uses school timezone for date filters. ⭐
    """
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by name...'
        })
    )
    
    structure_type = forms.ChoiceField(
        label='Structure Type',
        choices=[('', 'All Types')] + list(FeesStructure.STRUCTURE_TYPE_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    academic_year = forms.ModelChoiceField(
        label='Academic Year',
        queryset=None,
        required=False,
        empty_label="All Years",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    billing_frequency = forms.ChoiceField(
        label='Billing Frequency',
        choices=[('', 'All')] + list(FeesStructure.BILLING_FREQUENCY_CHOICES),
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
    
    academic_level = forms.ModelChoiceField(
        label='Academic Level',
        queryset=None,
        required=False,
        empty_label="All Levels",
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
    
    effective_from = forms.DateField(
        label='Effective From',
        required=False,
        widget=DatePickerInput()
    )
    
    effective_to = forms.DateField(
        label='Effective To',
        required=False,
        widget=DatePickerInput()
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        from core.models import FiscalYear
        self.fields['academic_year'].queryset = FiscalYear.objects.all().order_by('-start_date')
        
        self.fields['academic_session'].queryset = AcademicSession.objects.filter(
            is_active=True
        ).order_by('-start_date')
        
        self.fields['academic_level'].queryset = AcademicLevel.objects.filter(
            is_active=True
        ).order_by('order')


# =============================================================================
# INVOICE FORMS
# =============================================================================

class FeeInvoiceForm(RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """
    Form for creating/editing fee invoices.
    Uses school timezone for date validations. ⭐
    """
    
    class Meta:
        model = FeeInvoice
        fields = [
            'student', 'academic_session', 'fiscal_period', 'fee_structure',
            'issue_date', 'due_date', 'payment_terms',
            'notes', 'internal_notes'
        ]
        widgets = {
            'student': forms.Select(attrs={
                'class': 'form-select',
                'data-placeholder': 'Select student...'
            }),
            'academic_session': forms.Select(attrs={'class': 'form-select'}),
            'fiscal_period': forms.Select(attrs={'class': 'form-select'}),
            'fee_structure': forms.Select(attrs={'class': 'form-select'}),
            'issue_date': DatePickerInput(),
            'due_date': DatePickerInput(),
            'payment_terms': forms.TextInput(attrs={
                'placeholder': 'e.g., Payment due within 30 days'
            }),
            'notes': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Notes visible to student/parent...'
            }),
            'internal_notes': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Internal notes (not visible to student)...'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
            self.fields['student'].queryset = Student.objects.filter(
                enrollment_status='ACTIVE'
            ).order_by('first_name', 'last_name')
            
            self.fields['academic_session'].queryset = AcademicSession.objects.filter(
                is_active=True
            ).order_by('-start_date')
            
            self.fields['fiscal_period'].queryset = FiscalPeriod.objects.filter(
                status__in=['OPEN', 'CURRENT']
            ).order_by('-start_date')
            
            self.fields['fee_structure'].queryset = FeesStructure.objects.filter(
                is_active=True
            ).order_by('structure_type', 'name')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")
        
        if not self.is_bound:
            today = get_school_today()  # ⭐ SCHOOL TIMEZONE
            
            self.fields['issue_date'].initial = today
            self.fields['due_date'].initial = today + timezone.timedelta(days=30)
    
    def clean(self):
        """Validate invoice data using school timezone ⭐"""
        cleaned_data = super().clean()
        
        issue_date = cleaned_data.get('issue_date')
        due_date = cleaned_data.get('due_date')
        
        if issue_date and due_date:
            if due_date < issue_date:
                raise ValidationError({
                    'due_date': 'Due date cannot be before issue date.'
                })
        
        academic_session = cleaned_data.get('academic_session')
        fiscal_period = cleaned_data.get('fiscal_period')
        
        if academic_session and fiscal_period and issue_date:
            if issue_date < academic_session.start_date:
                self.add_error('issue_date',
                    f'Issue date cannot be before academic session start ({academic_session.start_date}).'
                )
            
            if issue_date < fiscal_period.start_date or issue_date > fiscal_period.end_date:
                self.add_error('fiscal_period',
                    f'Issue date must fall within the selected fiscal period.'
                )
        
        return cleaned_data


from django import forms
from django.forms import inlineformset_factory
from django.core.exceptions import ValidationError
from decimal import Decimal

from .models import FeeInvoice, FeeInvoiceItem


class FeeInvoiceItemForm(forms.ModelForm):
    """
    Form for editing individual invoice line items.
    
    Allows modifying:
    - Unit Amount (price per unit)
    - Quantity
    - Tax percentage
    - Discount amount
    
    Note: Scholarship amounts are auto-calculated and read-only
    Note: Description comes from fee_category and is not editable
    """
    
    class Meta:
        model = FeeInvoiceItem
        fields = [
            # 'description',  # REMOVED - comes from fee_category
            'unit_amount',
            'quantity',
            'tax_percentage',
            'discount_amount',
            'scholarship_discount_amount',
        ]
        widgets = {
            'unit_amount': forms.NumberInput(attrs={
                'class': 'form-control item-unit-amount',
                'placeholder': '0.00',
                'step': '0.01',
                'min': '0'
            }),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control item-quantity',
                'placeholder': '1',
                'step': '1',
                'min': '1',
                'value': '1'
            }),
            'tax_percentage': forms.NumberInput(attrs={
                'class': 'form-control item-tax-percentage',
                'placeholder': '0.00',
                'step': '0.01',
                'min': '0',
                'max': '100'
            }),
            'discount_amount': forms.NumberInput(attrs={
                'class': 'form-control item-discount',
                'placeholder': '0.00',
                'step': '0.01',
                'min': '0'
            }),
            'scholarship_discount_amount': forms.NumberInput(attrs={
                'class': 'form-control item-scholarship calculated-field',
                'placeholder': '0.00',
                'step': '0.01',
                'min': '0',
                'readonly': True
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set default quantity if not set
        if not self.instance.pk and not self.initial.get('quantity'):
            self.fields['quantity'].initial = Decimal('1.00')
        
        # Make scholarship amount read-only (calculated automatically)
        self.fields['scholarship_discount_amount'].disabled = True
        self.fields['scholarship_discount_amount'].help_text = (
            "Scholarship amount is calculated automatically and cannot be edited directly"
        )
    
    def clean_unit_amount(self):
        """Validate unit amount is positive."""
        amount = self.cleaned_data.get('unit_amount')
        if amount is not None and amount < 0:
            raise ValidationError("Unit amount cannot be negative.")
        return amount
    
    def clean_quantity(self):
        """Validate quantity is at least 1."""
        quantity = self.cleaned_data.get('quantity')
        if quantity is not None and quantity < 1:
            raise ValidationError("Quantity must be at least 1.")
        return quantity
    
    def clean_tax_percentage(self):
        """Validate tax percentage is between 0 and 100."""
        tax_percentage = self.cleaned_data.get('tax_percentage')
        if tax_percentage is not None:
            if tax_percentage < 0:
                raise ValidationError("Tax percentage cannot be negative.")
            if tax_percentage > 100:
                raise ValidationError("Tax percentage cannot exceed 100%.")
        return tax_percentage
    
    def clean_discount_amount(self):
        """Validate discount doesn't exceed line subtotal."""
        discount = self.cleaned_data.get('discount_amount', Decimal('0.00'))
        unit_amount = self.cleaned_data.get('unit_amount', Decimal('0.00'))
        quantity = self.cleaned_data.get('quantity', Decimal('1.00'))
        
        # Calculate item amount (before tax/discounts)
        item_amount = unit_amount * quantity
        
        if discount > item_amount:
            raise ValidationError(
                f"Discount amount ({discount}) cannot exceed line total ({item_amount})."
            )
        
        return discount
    
    def clean(self):
        """Cross-field validation and calculations."""
        cleaned_data = super().clean()
        
        unit_amount = cleaned_data.get('unit_amount', Decimal('0.00'))
        quantity = cleaned_data.get('quantity', Decimal('1.00'))
        tax_percentage = cleaned_data.get('tax_percentage', Decimal('0.00'))
        discount_amount = cleaned_data.get('discount_amount', Decimal('0.00'))
        scholarship_discount_amount = cleaned_data.get('scholarship_discount_amount', Decimal('0.00'))
        
        # Calculate totals (will be saved in view/save method)
        amount = unit_amount * quantity
        total_discount = discount_amount + scholarship_discount_amount
        taxable_amount = amount - total_discount
        tax_amount = (taxable_amount * tax_percentage / 100).quantize(Decimal('0.01'))
        final_amount = taxable_amount + tax_amount
        
        # Store calculated values for use in view
        self.calculated_amount = amount
        self.calculated_tax_amount = tax_amount
        self.calculated_final_amount = final_amount
        self.calculated_total_discount = total_discount
        
        return cleaned_data


class FeeInvoiceEditForm(forms.ModelForm):
    """
    Form for editing invoice header information.
    
    Allows modifying:
    - Issue date
    - Due date
    - Internal notes
    - Payment terms
    """
    
    class Meta:
        model = FeeInvoice
        fields = [
            'issue_date',
            'due_date',
            'internal_notes',
            'payment_terms'
        ]
        widgets = {
            'issue_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'due_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'internal_notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Internal notes about this invoice (not visible to student/parent)'
            }),
            'payment_terms': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Payment terms and conditions'
            })
        }
        help_texts = {
            'issue_date': 'Date when the invoice was issued',
            'due_date': 'Payment due date',
            'internal_notes': 'Internal notes (not visible to student/parent)',
            'payment_terms': 'Terms and conditions for payment'
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Only allow editing if invoice is DRAFT
        if self.instance.pk and self.instance.status != 'DRAFT':
            for field in self.fields:
                self.fields[field].disabled = True
                self.fields[field].help_text = "Invoice must be in DRAFT status to edit"
    
    def clean_due_date(self):
        """Validate due date is after issue date."""
        due_date = self.cleaned_data.get('due_date')
        issue_date = self.cleaned_data.get('issue_date')
        
        if due_date and issue_date and due_date < issue_date:
            raise ValidationError("Due date cannot be before issue date.")
        
        return due_date
    
    def clean(self):
        """Validate invoice can be edited."""
        cleaned_data = super().clean()
        
        if self.instance.pk and self.instance.status != 'DRAFT':
            raise ValidationError(
                "Only DRAFT invoices can be edited. "
                "Please revert to DRAFT status first."
            )
        
        return cleaned_data


# Formset for managing multiple invoice items
FeeInvoiceItemFormSet = inlineformset_factory(
    FeeInvoice,
    FeeInvoiceItem,
    form=FeeInvoiceItemForm,
    extra=1,  # Show one empty form for adding new items
    can_delete=True,  # Allow deleting items
    min_num=1,  # At least one item required
    validate_min=True,
    can_order=False
)


class InvoiceItemQuickEditForm(forms.Form):
    """
    Quick edit form for adjusting a single item's amount.
    
    Useful for simple adjustments without full formset.
    """
    
    item_id = forms.UUIDField(
        widget=forms.HiddenInput()
    )
    
    new_unit_amount = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal('0.00'),
        label="New Unit Amount",
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': '0.00',
            'step': '0.01'
        })
    )
    
    reason = forms.CharField(
        required=False,
        label="Reason for Adjustment",
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Optional: Why is this amount being adjusted?'
        })
    )
    
    def __init__(self, *args, invoice=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.invoice = invoice
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Validate invoice is DRAFT
        if self.invoice and self.invoice.status != 'DRAFT':
            raise ValidationError("Can only edit DRAFT invoices.")
        
        return cleaned_data


class InvoiceAddItemForm(forms.Form):
    """
    Form for adding a new item to an existing DRAFT invoice.
    """
    
    fee_category = forms.ChoiceField(
        label="Fee Category",
        widget=forms.Select(attrs={
            'class': 'form-control'
        })
    )
    
    description = forms.CharField(
        max_length=255,
        label="Description",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Fee description'
        })
    )
    
    unit_amount = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal('0.00'),
        label="Unit Amount",
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': '0.00',
            'step': '0.01'
        })
    )
    
    quantity = forms.DecimalField(
        max_digits=8,
        decimal_places=2,
        min_value=Decimal('1.00'),
        initial=Decimal('1.00'),
        label="Quantity",
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'value': '1.00',
            'step': '0.01'
        })
    )
    
    tax_percentage = forms.DecimalField(
        max_digits=5,
        decimal_places=2,
        min_value=Decimal('0.00'),
        max_value=Decimal('100.00'),
        initial=Decimal('0.00'),
        label="Tax Percentage (%)",
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': '0.00',
            'step': '0.01'
        })
    )
    
    def __init__(self, *args, invoice=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.invoice = invoice
        
        # Populate fee category choices
        if invoice:
            from .models import FeesCategory
            categories = FeesCategory.objects.filter(
                school=invoice.student.school,
                is_active=True
            ).order_by('name')
            
            self.fields['fee_category'].choices = [
                ('', '-- Select Fee Category --')
            ] + [
                (cat.id, cat.name) for cat in categories
            ]
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Validate invoice is DRAFT
        if self.invoice and self.invoice.status != 'DRAFT':
            raise ValidationError("Can only add items to DRAFT invoices.")
        
        return cleaned_data


class SingleInvoiceGenerationForm(forms.Form):
    """
    Form for generating a single invoice for a student enrollment.
    
    This form is used when creating invoices one at a time, typically from:
    - Student detail page
    - Enrollment detail page
    - Quick invoice generation workflow
    
    The form is simpler than BulkInvoiceGenerationForm since it only needs
    to specify invoice parameters, not target student selection criteria.
    """
    
    # Core Invoice Fields
    academic_session = forms.ModelChoiceField(
        queryset=AcademicSession.objects.filter(is_active=True).order_by('-start_date'),
        required=True,
        label="Academic Session",
        help_text="The academic session this invoice is for",
        widget=forms.Select(attrs={
            'class': 'form-control',
            'data-placeholder': 'Select Academic Session'
        })
    )
    
    fiscal_period = forms.ModelChoiceField(
        queryset=FiscalPeriod.objects.filter(is_closed=False).order_by('-start_date'),
        required=True,
        label="Fiscal Period",
        help_text="The fiscal period when this invoice is processed",
        widget=forms.Select(attrs={
            'class': 'form-control',
            'data-placeholder': 'Select Fiscal Period'
        })
    )
    
    # Invoice Dates
    issue_date = forms.DateField(
        required=False,
        label="Issue Date",
        help_text="Invoice issue date (defaults to today if not specified)",
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    
    due_date = forms.DateField(
        required=False,
        label="Due Date",
        help_text="Payment due date (defaults to 30 days from issue date if not specified)",
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    
    # Invoice Options
    auto_apply_scholarships = forms.BooleanField(
        required=False,
        initial=True,
        label="Auto-apply Scholarships",
        help_text="Automatically apply active scholarships to this invoice",
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        })
    )
    
    auto_apply_discounts = forms.BooleanField(
        required=False,
        initial=True,
        label="Auto-apply Discounts",
        help_text="Automatically apply eligible discounts to this invoice",
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        })
    )
    
    create_as_pending = forms.BooleanField(
        required=False,
        initial=False,
        label="Create as PENDING (Skip Draft)",
        help_text="Directly create invoice as PENDING (bypasses DRAFT status). Use with caution.",
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        })
    )
    
    # Validation Options
    skip_if_has_invoice = forms.BooleanField(
        required=False,
        initial=False,
        label="Skip if Invoice Exists",
        help_text="Don't create invoice if student already has an invoice for this session/period",
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        })
    )
    
    skip_if_has_pending = forms.BooleanField(
        required=False,
        initial=False,
        label="Skip if Pending Balance",
        help_text="Don't create invoice if student has unpaid invoices",
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        })
    )
    
    # Notes
    internal_notes = forms.CharField(
        required=False,
        label="Internal Notes",
        help_text="Optional notes about this invoice (not visible to student/parent)",
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Add any internal notes about this invoice...'
        })
    )
    
    def __init__(self, *args, school=None, enrollment=None, **kwargs):
        """
        Initialize form with optional school and enrollment context.
        
        Args:
            school: School instance to filter sessions/periods
            enrollment: StudentClassEnrollment instance (for pre-validation)
        """
        super().__init__(*args, **kwargs)
        
        self.school = school
        self.enrollment = enrollment
        
        # Filter querysets by school if provided
        if school:
            self.fields['academic_session'].queryset = AcademicSession.objects.filter(
                school=school,
                is_active=True
            ).order_by('-start_date')
            
            self.fields['fiscal_period'].queryset = FiscalPeriod.objects.filter(
                school=school,
                is_closed=False
            ).order_by('-start_date')
        
        # Pre-select current session if enrollment provided
        if enrollment:
            self.fields['academic_session'].initial = enrollment.academic_session
            
            # Try to find matching fiscal period
            if enrollment.academic_session:
                try:
                    # Find fiscal period that overlaps with session
                    fiscal_period = FiscalPeriod.objects.filter(
                        school=enrollment.academic_session.school,
                        start_date__lte=enrollment.academic_session.end_date,
                        end_date__gte=enrollment.academic_session.start_date,
                        is_closed=False
                    ).first()
                    
                    if fiscal_period:
                        self.fields['fiscal_period'].initial = fiscal_period
                except Exception:
                    pass
        
        # Set default dates using school timezone if available
        if school:
            from core.utils import get_school_today
            today = get_school_today(school)
        else:
            today = timezone.now().date()
        
        if not self.data.get('issue_date'):
            self.fields['issue_date'].initial = today
        
        if not self.data.get('due_date'):
            self.fields['due_date'].initial = today + timedelta(days=30)
    
    def clean_issue_date(self):
        """Validate issue date is not in the future."""
        issue_date = self.cleaned_data.get('issue_date')
        
        if not issue_date:
            # Use today if not provided
            if self.school:
                from core.utils import get_school_today
                issue_date = get_school_today(self.school)
            else:
                issue_date = timezone.now().date()
        
        # Check if date is in future
        if self.school:
            from core.utils import get_school_today
            today = get_school_today(self.school)
        else:
            today = timezone.now().date()
        
        if issue_date > today:
            raise ValidationError("Issue date cannot be in the future.")
        
        return issue_date
    
    def clean_due_date(self):
        """Validate due date is after issue date."""
        due_date = self.cleaned_data.get('due_date')
        issue_date = self.cleaned_data.get('issue_date')
        
        if not due_date and issue_date:
            # Default to 30 days from issue date
            due_date = issue_date + timedelta(days=30)
        
        if due_date and issue_date and due_date < issue_date:
            raise ValidationError("Due date cannot be before issue date.")
        
        return due_date
    
    def clean(self):
        """Cross-field validation."""
        cleaned_data = super().clean()
        
        academic_session = cleaned_data.get('academic_session')
        fiscal_period = cleaned_data.get('fiscal_period')
        issue_date = cleaned_data.get('issue_date')
        
        # Validate session and period exist
        if not academic_session:
            raise ValidationError("Academic session is required.")
        
        if not fiscal_period:
            raise ValidationError("Fiscal period is required.")
        
        # Validate fiscal period is not closed
        if fiscal_period and fiscal_period.is_closed:
            raise ValidationError(
                f"Cannot create invoice in closed fiscal period: {fiscal_period.name}"
            )
        
        # Check if enrollment already has invoice (if skip_if_has_invoice is True)
        if cleaned_data.get('skip_if_has_invoice') and self.enrollment:
            existing_invoice = FeeInvoice.objects.filter(
                student=self.enrollment.student,
                academic_session=academic_session,
                fiscal_period=fiscal_period
            ).exclude(status__in=['VOID', 'CANCELLED']).first()
            
            if existing_invoice:
                raise ValidationError(
                    f"Student already has an invoice ({existing_invoice.invoice_number}) "
                    f"for {academic_session.name} in {fiscal_period.name}. "
                    f"Uncheck 'Skip if Invoice Exists' to create another invoice."
                )
        
        # Check if student has pending balance (if skip_if_has_pending is True)
        if cleaned_data.get('skip_if_has_pending') and self.enrollment:
            pending_invoices = FeeInvoice.objects.filter(
                student=self.enrollment.student,
                status__in=['PENDING', 'PARTIALLY_PAID', 'OVERDUE']
            ).exclude(balance=0)
            
            if pending_invoices.exists():
                total_pending = sum(inv.balance for inv in pending_invoices)
                raise ValidationError(
                    f"Student has {pending_invoices.count()} unpaid invoice(s) "
                    f"with total balance of {total_pending}. "
                    f"Uncheck 'Skip if Pending Balance' to create invoice anyway."
                )
        
        return cleaned_data
    
    def get_generation_kwargs(self):
        """
        Get kwargs for passing to generate_student_enrollment_invoice().
        
        Returns:
            dict: Keyword arguments for invoice generation
        """
        return {
            'academic_session': self.cleaned_data.get('academic_session'),
            'fiscal_period': self.cleaned_data.get('fiscal_period'),
            'issue_date': self.cleaned_data.get('issue_date'),
            'due_date': self.cleaned_data.get('due_date'),
            'auto_apply_scholarships': self.cleaned_data.get('auto_apply_scholarships', True),
            'auto_apply_discounts': self.cleaned_data.get('auto_apply_discounts', True),
            'internal_notes': self.cleaned_data.get('internal_notes', ''),
            'create_as_pending': self.cleaned_data.get('create_as_pending', False),
        }

class FeeInvoiceFilterForm(DateRangeFormMixin, BootstrapFormMixin, forms.Form):
    """
    Filter form for invoice search.
    Uses school timezone for date filters. ⭐
    """
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by invoice number, student name...'
        })
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
        choices=[('', 'All Statuses')] + list(FeeInvoice.STATUS_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    issue_date_from = forms.DateField(
        label='Issue Date From',
        required=False,
        widget=DatePickerInput()
    )
    
    issue_date_to = forms.DateField(
        label='Issue Date To',
        required=False,
        widget=DatePickerInput()
    )
    
    due_date_from = forms.DateField(
        label='Due Date From',
        required=False,
        widget=DatePickerInput()
    )
    
    due_date_to = forms.DateField(
        label='Due Date To',
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
    
    balance_status = forms.ChoiceField(
        label='Balance Status',
        choices=[
            ('', 'All'),
            ('zero', 'Zero Balance'),
            ('positive', 'Has Balance'),
            ('overpaid', 'Overpaid'),
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    has_scholarships = forms.NullBooleanField(
        label='Has Scholarships',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'With Scholarships'),
            ('false', 'Without Scholarships')
        ], attrs={'class': 'form-select'})
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
            self.fields['academic_session'].queryset = AcademicSession.objects.filter(
                is_active=True
            ).order_by('-start_date')
            
            self.fields['fiscal_period'].queryset = FiscalPeriod.objects.all().order_by('-start_date')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")

# =============================================================================
# FINAL WORKING PaymentForm.__init__() 
# This accounts for the BootstrapFormMixin, RequiredFieldsMixin, MoneyFieldsMixin
# =============================================================================

class PaymentForm(RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """
    Form for recording payments against a single invoice.
    """
    
    amount = MoneyField(label="Amount Paid")
    
    class Meta:
        model = Payment
        fields = [
            'invoice', 'student', 'amount', 'payment_date', 'payment_method',
            'reference_number', 'transaction_id',
            'bank_name', 'account_number', 'cheque_number', 'cheque_date',
            'mobile_money_provider', 'mobile_number',
            'paid_by_name', 'paid_by_phone', 'paid_by_email', 'paid_by_relationship',
            'remarks'
        ]
        widgets = {
            'invoice': forms.Select(attrs={
                'class': 'form-select',
                'data-placeholder': 'Select an invoice...'
            }),
            'student': forms.Select(attrs={
                'class': 'form-select',
                'data-placeholder': 'Select a student...'
            }),
            'payment_date': DatePickerInput(),
            'payment_method': forms.Select(attrs={
                'class': 'form-select',
                'data-placeholder': 'Select payment method...'
            }),
            'reference_number': forms.TextInput(attrs={
                'placeholder': 'Payment reference number',
                'class': 'form-control'
            }),
            'transaction_id': forms.TextInput(attrs={
                'placeholder': 'Transaction ID from bank/mobile money',
                'class': 'form-control'
            }),
            'bank_name': forms.TextInput(attrs={
                'placeholder': 'Bank name',
                'class': 'form-control'
            }),
            'account_number': forms.TextInput(attrs={
                'placeholder': 'Account number',
                'class': 'form-control'
            }),
            'cheque_number': forms.TextInput(attrs={
                'placeholder': 'Cheque number',
                'class': 'form-control'
            }),
            'cheque_date': DatePickerInput(),
            'mobile_money_provider': forms.TextInput(attrs={
                'placeholder': 'e.g., MTN, Airtel',
                'class': 'form-control'
            }),
            'mobile_number': PhoneInput(),
            'paid_by_name': forms.TextInput(attrs={
                'placeholder': 'Name of person who paid',
                'class': 'form-control'
            }),
            'paid_by_phone': PhoneInput(),
            'paid_by_email': forms.EmailInput(attrs={
                'placeholder': 'Email of payer',
                'class': 'form-control'
            }),
            'paid_by_relationship': forms.Select(attrs={'class': 'form-select'}),
            'remarks': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Payment remarks...',
                'class': 'form-control'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        """
        Initialize payment form with proper handling of pre-selected invoice.
        """
        import logging
        logger = logging.getLogger(__name__)
        
        # ✅ STEP 1: Extract invoice from kwargs
        invoice = kwargs.pop('invoice', None)
        
        # ✅ STEP 2: Set initial values in kwargs BEFORE calling super().__init__()
        if invoice and not kwargs.get('instance'):
            logger.info(f"Pre-populating form with invoice: {invoice.id}")
            
            # Create initial dict if it doesn't exist
            if 'initial' not in kwargs:
                kwargs['initial'] = {}
            
            # Set the initial values - these will be used by ModelForm.__init__()
            kwargs['initial']['invoice'] = invoice.id
            kwargs['initial']['student'] = invoice.student.id
            kwargs['initial']['amount'] = invoice.balance
            
            logger.info(f"Set initial: invoice={invoice.id}, student={invoice.student.id}, amount={invoice.balance}")
        
        # ✅ STEP 3: Call super().__init__()
        super().__init__(*args, **kwargs)
        
        # ✅ STEP 4: Check if this is a new payment (use _state.adding for reliability)
        is_new_payment = self.instance._state.adding
        
        logger.info("=" * 80)
        logger.info("INSTANCE STATE AFTER super().__init__()")
        logger.info(f"self.instance.pk: {self.instance.pk}")
        logger.info(f"self.instance._state.adding: {self.instance._state.adding}")
        logger.info(f"is_new_payment: {is_new_payment}")
        logger.info("=" * 80)
        
        # ✅ STEP 5: Configure fields based on whether it's new
        
        if is_new_payment and invoice:
            logger.info(f"✅ NEW PAYMENT with pre-selected invoice: {invoice.id}")
            
            # Change widgets to HiddenInput
            self.fields['invoice'].widget = forms.HiddenInput()
            self.fields['student'].widget = forms.HiddenInput()
            
            # Set querysets - MUST include the selected value for validation
            self.fields['invoice'].queryset = FeeInvoice.objects.filter(id=invoice.id)
            self.fields['student'].queryset = Student.objects.filter(id=invoice.student.id)
            
            # Ensure fields are required
            self.fields['invoice'].required = True
            self.fields['student'].required = True
            
            # Verify configuration
            logger.info("Field configuration:")
            logger.info(f"  Invoice widget: {type(self.fields['invoice'].widget).__name__}")
            logger.info(f"  Invoice initial: {self.initial.get('invoice')}")
            logger.info(f"  Invoice queryset count: {self.fields['invoice'].queryset.count()}")
            logger.info(f"  Student widget: {type(self.fields['student'].widget).__name__}")
            logger.info(f"  Student initial: {self.initial.get('student')}")
            logger.info(f"  Student queryset count: {self.fields['student'].queryset.count()}")
            
        elif is_new_payment:
            # No invoice pre-selected - show full dropdowns
            logger.info("✅ NEW PAYMENT without pre-selected invoice")
            
            self.fields['invoice'].queryset = FeeInvoice.objects.exclude(
                status__in=['CANCELLED', 'VOID', 'WRITTEN_OFF', 
                        'UNCOLLECTIBLE', 'BAD_DEBT']
            ).select_related('student').order_by('-issue_date')[:100]
            
            self.fields['student'].queryset = Student.objects.filter(
                enrollment_status='ACTIVE'
            ).order_by('first_name', 'last_name')
            
        else:
            # Editing existing payment
            # ✅ SAFE LOGGING: Don't try to access related objects that might not exist
            payment_number = getattr(self.instance, 'payment_number', 'N/A')
            logger.info(f"✅ EDITING existing payment: {payment_number}")
            
            self.fields['invoice'].queryset = FeeInvoice.objects.filter(
                id=self.instance.invoice_id
            ).select_related('student')
            
            self.fields['student'].queryset = Student.objects.filter(
                id=self.instance.student_id
            )
        
        # =====================================================================
        # Payment Methods
        # =====================================================================
        
        self.fields['payment_method'].queryset = PaymentMethod.objects.filter(
            is_active=True
        ).order_by('display_order', 'name')
        
        # =====================================================================
        # Set default payment date
        # =====================================================================
        
        if not self.is_bound and is_new_payment:
            if 'payment_date' not in self.initial:
                from core.utils import get_school_today
                self.initial['payment_date'] = get_school_today()
                logger.info(f"Set default payment_date: {self.initial['payment_date']}")
        
        # =====================================================================
        # Add help text
        # =====================================================================
        
        self.fields['amount'].help_text = (
            "Total amount paid. Payment number, receipt number, and fiscal period "
            "will be auto-generated when you save."
        )
        
        # =====================================================================
        # Handle editing restrictions for EXISTING payments
        # =====================================================================
        
        if not is_new_payment:
            if self.instance.reversed:
                for field in self.fields:
                    self.fields[field].disabled = True
                    self.fields[field].help_text = "⚠️ Cannot edit reversed payment"
            
            elif self.instance.refunded:
                for field in self.fields:
                    self.fields[field].disabled = True
                    self.fields[field].help_text = "⚠️ Cannot edit refunded payment"
            
            elif self.instance.status == 'COMPLETED' and self.instance.is_verified:
                restricted_fields = [
                    'invoice', 'student', 'amount', 'payment_date',
                    'payment_method', 'transaction_id'
                ]
                for field in restricted_fields:
                    if field in self.fields:
                        self.fields[field].disabled = True
                        self.fields[field].help_text = "Cannot modify verified payment"
        
        logger.info("PaymentForm.__init__() completed successfully")
    
    def clean(self):
        """Validate payment data using school timezone"""
        cleaned_data = super().clean()
        
        # Don't validate reversed/refunded payments
        if not self.instance.pk or (not self.instance.reversed and not self.instance.refunded):
            
            payment_date = cleaned_data.get('payment_date')
            
            if payment_date:
                from core.utils import get_school_today
                from datetime import timedelta
                
                today = get_school_today()
                
                # Payment date cannot be in the future
                if payment_date > today:
                    raise ValidationError({
                        'payment_date': 'Payment date cannot be in the future.'
                    })
                
                # Reasonable past date check (1 year)
                if payment_date < (today - timedelta(days=365)):
                    raise ValidationError({
                        'payment_date': 'Payment date seems too far in the past (over 1 year).'
                    })
            
            # Validate amount against invoice
            invoice = cleaned_data.get('invoice')
            amount = cleaned_data.get('amount')
            
            if invoice and amount:
                if amount <= 0:
                    raise ValidationError({
                        'amount': 'Payment amount must be greater than zero.'
                    })
            
            # Validate cheque date
            cheque_date = cleaned_data.get('cheque_date')
            if cheque_date:
                from core.utils import get_school_today
                today = get_school_today()
                
                if cheque_date > today:
                    raise ValidationError({
                        'cheque_date': 'Cheque date cannot be in the future.'
                    })
            
            # Validate payment method specific fields
            payment_method = cleaned_data.get('payment_method')
            if payment_method:
                method_type = payment_method.method_type.upper()
                
                # Bank/Cheque payments require bank details
                if method_type in ['BANK_TRANSFER', 'CHEQUE']:
                    if not cleaned_data.get('bank_name'):
                        self.add_error('bank_name', 'Bank name is required for bank/cheque payments.')
                
                # Cheque payments require cheque number and date
                if method_type == 'CHEQUE':
                    if not cleaned_data.get('cheque_number'):
                        self.add_error('cheque_number', 'Cheque number is required.')
                    if not cleaned_data.get('cheque_date'):
                        self.add_error('cheque_date', 'Cheque date is required.')
                
                # Mobile money requires provider and number
                if method_type == 'MOBILE_MONEY':
                    if not cleaned_data.get('mobile_money_provider'):
                        self.add_error('mobile_money_provider', 
                            'Mobile money provider is required (e.g., MTN, Airtel).')
                    if not cleaned_data.get('mobile_number'):
                        self.add_error('mobile_number', 
                            'Mobile number is required for mobile money payments.')
            
            # Validate phone numbers
            paid_by_phone = cleaned_data.get('paid_by_phone')
            mobile_number = cleaned_data.get('mobile_number')
            
            if paid_by_phone:
                try:
                    validate_phone_number(paid_by_phone)
                except ValidationError as e:
                    raise ValidationError({'paid_by_phone': e.message})
            
            if mobile_number:
                try:
                    validate_phone_number(mobile_number)
                except ValidationError as e:
                    raise ValidationError({'mobile_number': e.message})
        
        return cleaned_data


# =============================================================================
# 2. MULTIPLE INVOICE PAYMENT FORM ⭐ NEW
# =============================================================================

class MultipleInvoicePaymentForm(RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.Form):
    """
    Form for making a SINGLE payment that covers MULTIPLE invoices.
    
    Use cases:
    - Parent paying for multiple children at once
    - Parent paying multiple terms for same student
    - Parent clearing all outstanding invoices
    
    How it works:
    1. User selects student(s) or enters invoice numbers
    2. System shows all outstanding invoices
    3. User enters total payment amount
    4. System allocates payment across invoices (oldest first, or custom)
    5. Creates individual Payment records for each invoice
    """
    
    # -------------------------------------------------------------------------
    # INVOICE SELECTION METHOD
    # -------------------------------------------------------------------------
    
    selection_method = forms.ChoiceField(
        label="How do you want to select invoices?",
        choices=[
            ('student', 'By Student (all outstanding invoices)'),
            ('invoices', 'By Invoice Numbers (specific invoices)'),
        ],
        initial='student',
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        help_text="Choose how to select which invoices to pay"
    )
    
    # -------------------------------------------------------------------------
    # STUDENT SELECTION (if selection_method = 'student')
    # -------------------------------------------------------------------------
    
    students = forms.ModelMultipleChoiceField(
        label="Select Student(s)",
        queryset=None,  # Set in __init__
        required=False,
        widget=forms.SelectMultiple(attrs={
            'class': 'form-select',
            'size': '8',
            'data-placeholder': 'Select one or more students...'
        }),
        help_text="All outstanding invoices for selected students will be included"
    )
    
    # -------------------------------------------------------------------------
    # INVOICE SELECTION (if selection_method = 'invoices')
    # -------------------------------------------------------------------------
    
    invoice_numbers = forms.CharField(
        label="Invoice Numbers",
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 4,
            'class': 'form-control',
            'placeholder': 'Enter invoice numbers (one per line or comma-separated)\nExample:\nINV-2024-001\nINV-2024-002\nINV-2024-003'
        }),
        help_text="Enter invoice numbers to pay (one per line or comma-separated)"
    )
    
    # -------------------------------------------------------------------------
    # PAYMENT DETAILS
    # -------------------------------------------------------------------------
    
    total_amount = MoneyField(
        label="Total Payment Amount",
        help_text="Total amount being paid (will be allocated across selected invoices)"
    )
    
    payment_date = forms.DateField(
        label="Payment Date",
        widget=DatePickerInput(),
        help_text="Date payment was received"
    )
    
    payment_method = forms.ModelChoiceField(
        label="Payment Method",
        queryset=None,  # Set in __init__
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="How payment was made"
    )
    
    # -------------------------------------------------------------------------
    # ALLOCATION METHOD
    # -------------------------------------------------------------------------
    
    allocation_method = forms.ChoiceField(
        label="Payment Allocation Method",
        choices=[
            ('oldest_first', 'Oldest Invoices First (Recommended)'),
            ('newest_first', 'Newest Invoices First'),
            ('largest_first', 'Largest Balances First'),
            ('smallest_first', 'Smallest Balances First (Clear small debts)'),
            ('equal', 'Equal Distribution'),
            ('custom', 'Custom Allocation (specify amounts)'),
        ],
        initial='oldest_first',
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="How to distribute payment across multiple invoices"
    )
    
    # -------------------------------------------------------------------------
    # CUSTOM ALLOCATION (if allocation_method = 'custom')
    # -------------------------------------------------------------------------
    
    custom_allocation = forms.JSONField(
        label="Custom Allocation",
        required=False,
        widget=forms.HiddenInput(),
        help_text="JSON object mapping invoice IDs to payment amounts"
    )
    
    # -------------------------------------------------------------------------
    # PAYMENT METHOD DETAILS
    # -------------------------------------------------------------------------
    
    reference_number = forms.CharField(
        label="Reference Number",
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Payment reference number'
        })
    )
    
    transaction_id = forms.CharField(
        label="Transaction ID",
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Bank/Mobile money transaction ID'
        })
    )
    
    # Bank details
    bank_name = forms.CharField(
        label="Bank Name",
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    
    account_number = forms.CharField(
        label="Account Number",
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    
    cheque_number = forms.CharField(
        label="Cheque Number",
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    
    cheque_date = forms.DateField(
        label="Cheque Date",
        required=False,
        widget=DatePickerInput()
    )
    
    # Mobile money details
    mobile_money_provider = forms.CharField(
        label="Mobile Money Provider",
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g., MTN, Airtel'
        })
    )
    
    mobile_number = forms.CharField(
        label="Mobile Number",
        max_length=20,
        required=False,
        widget=PhoneInput()
    )
    
    # -------------------------------------------------------------------------
    # PAYER INFORMATION
    # -------------------------------------------------------------------------
    
    paid_by_name = forms.CharField(
        label="Paid By (Name)",
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Name of person making payment'
        })
    )
    
    paid_by_phone = forms.CharField(
        label="Paid By (Phone)",
        max_length=20,
        required=False,
        widget=PhoneInput()
    )
    
    paid_by_email = forms.EmailField(
        label="Paid By (Email)",
        required=False,
        widget=forms.EmailInput(attrs={'class': 'form-control'})
    )
    
    paid_by_relationship = forms.ChoiceField(
        label="Relationship to Student",
        choices=[('', '-- Select --')] + list(Payment.PAYER_RELATIONSHIP_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    # -------------------------------------------------------------------------
    # REMARKS
    # -------------------------------------------------------------------------
    
    remarks = forms.CharField(
        label="Remarks",
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'class': 'form-control',
            'placeholder': 'Any additional notes about this payment...'
        })
    )
    
    # -------------------------------------------------------------------------
    # INITIALIZATION
    # -------------------------------------------------------------------------
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set querysets
        self.fields['students'].queryset = Student.objects.filter(
            enrollment_status='ACTIVE'
        ).order_by('first_name', 'last_name')
        
        self.fields['payment_method'].queryset = PaymentMethod.objects.filter(
            is_active=True
        ).order_by('display_order', 'name')
        
        # Set default payment date
        if not self.is_bound:
            self.fields['payment_date'].initial = get_school_today()
    
    # -------------------------------------------------------------------------
    # VALIDATION
    # -------------------------------------------------------------------------
    
    def clean(self):
        """Validate form data and get selected invoices"""
        cleaned_data = super().clean()
        
        selection_method = cleaned_data.get('selection_method')
        students = cleaned_data.get('students')
        invoice_numbers = cleaned_data.get('invoice_numbers', '').strip()
        total_amount = cleaned_data.get('total_amount')
        allocation_method = cleaned_data.get('allocation_method')
        custom_allocation = cleaned_data.get('custom_allocation')
        
        # =====================================================================
        # VALIDATE INVOICE SELECTION
        # =====================================================================
        
        if selection_method == 'student':
            if not students:
                raise ValidationError({
                    'students': 'Please select at least one student.'
                })
            
            # Get outstanding invoices for selected students
            invoices = FeeInvoice.objects.filter(
                student__in=students,
                status__in=['PENDING', 'PARTIALLY_PAID', 'OVERDUE']
            ).order_by('issue_date')
            
            if not invoices.exists():
                raise ValidationError({
                    'students': 'Selected student(s) have no outstanding invoices.'
                })
        
        elif selection_method == 'invoices':
            if not invoice_numbers:
                raise ValidationError({
                    'invoice_numbers': 'Please enter at least one invoice number.'
                })
            
            # Parse invoice numbers (handle both newline and comma separation)
            invoice_list = []
            for line in invoice_numbers.replace(',', '\n').split('\n'):
                number = line.strip()
                if number:
                    invoice_list.append(number)
            
            if not invoice_list:
                raise ValidationError({
                    'invoice_numbers': 'Please enter valid invoice numbers.'
                })
            
            # Get invoices by number
            invoices = FeeInvoice.objects.filter(
                invoice_number__in=invoice_list,
                status__in=['PENDING', 'PARTIALLY_PAID', 'OVERDUE']
            )
            
            if not invoices.exists():
                raise ValidationError({
                    'invoice_numbers': 'No outstanding invoices found with those numbers.'
                })
            
            # Check for missing invoices
            found_numbers = set(invoices.values_list('invoice_number', flat=True))
            missing = set(invoice_list) - found_numbers
            if missing:
                raise ValidationError({
                    'invoice_numbers': f'Invoice(s) not found or already paid: {", ".join(missing)}'
                })
        
        # Store invoices in cleaned_data for later use
        cleaned_data['selected_invoices'] = invoices
        
        # =====================================================================
        # VALIDATE PAYMENT AMOUNT
        # =====================================================================
        
        if total_amount:
            if total_amount <= 0:
                raise ValidationError({
                    'total_amount': 'Payment amount must be greater than zero.'
                })
            
            # Calculate total outstanding
            total_outstanding = sum(invoice.balance for invoice in invoices)
            
            # Warn if overpayment
            if total_amount > total_outstanding:
                overpayment = total_amount - total_outstanding
                import warnings
                warnings.warn(
                    f'Payment exceeds total outstanding balance by {overpayment:,.2f}. '
                    f'Excess will be credited to student account(s).'
                )
            
            cleaned_data['total_outstanding'] = total_outstanding
        
        # =====================================================================
        # VALIDATE CUSTOM ALLOCATION
        # =====================================================================
        
        if allocation_method == 'custom':
            if not custom_allocation:
                raise ValidationError({
                    'allocation_method': 'Custom allocation data required when using custom allocation method.'
                })
            
            # Validate custom allocation totals match payment amount
            try:
                custom_total = sum(Decimal(str(v)) for v in custom_allocation.values())
                if abs(custom_total - total_amount) > Decimal('0.01'):
                    raise ValidationError({
                        'custom_allocation': f'Custom allocation total ({custom_total:,.2f}) does not match payment amount ({total_amount:,.2f})'
                    })
            except (ValueError, TypeError):
                raise ValidationError({
                    'custom_allocation': 'Invalid custom allocation data.'
                })
        
        # =====================================================================
        # VALIDATE PAYMENT METHOD SPECIFIC FIELDS
        # =====================================================================
        
        payment_method = cleaned_data.get('payment_method')
        if payment_method:
            method_type = payment_method.method_type.upper()
            
            if method_type in ['BANK_TRANSFER', 'CHEQUE']:
                if not cleaned_data.get('bank_name'):
                    self.add_error('bank_name', 'Bank name is required for bank/cheque payments.')
            
            if method_type == 'CHEQUE':
                if not cleaned_data.get('cheque_number'):
                    self.add_error('cheque_number', 'Cheque number is required.')
                if not cleaned_data.get('cheque_date'):
                    self.add_error('cheque_date', 'Cheque date is required.')
            
            if method_type == 'MOBILE_MONEY':
                if not cleaned_data.get('mobile_money_provider'):
                    self.add_error('mobile_money_provider', 'Mobile money provider is required.')
                if not cleaned_data.get('mobile_number'):
                    self.add_error('mobile_number', 'Mobile number is required.')
        
        # =====================================================================
        # VALIDATE DATES
        # =====================================================================
        
        payment_date = cleaned_data.get('payment_date')
        if payment_date:
            today = get_school_today()
            
            if payment_date > today:
                raise ValidationError({
                    'payment_date': 'Payment date cannot be in the future.'
                })
            
            if payment_date < (today - timedelta(days=365)):
                raise ValidationError({
                    'payment_date': 'Payment date seems too far in the past.'
                })
        
        cheque_date = cleaned_data.get('cheque_date')
        if cheque_date:
            today = get_school_today()
            if cheque_date > today:
                raise ValidationError({
                    'cheque_date': 'Cheque date cannot be in the future.'
                })
        
        # =====================================================================
        # VALIDATE PHONE NUMBERS
        # =====================================================================
        
        paid_by_phone = cleaned_data.get('paid_by_phone')
        mobile_number = cleaned_data.get('mobile_number')
        
        if paid_by_phone:
            try:
                validate_phone_number(paid_by_phone)
            except ValidationError as e:
                raise ValidationError({'paid_by_phone': e.message})
        
        if mobile_number:
            try:
                validate_phone_number(mobile_number)
            except ValidationError as e:
                raise ValidationError({'mobile_number': e.message})
        
        return cleaned_data
    
    # -------------------------------------------------------------------------
    # HELPER METHODS
    # -------------------------------------------------------------------------
    
    def get_payment_allocation(self):
        """
        Calculate how payment should be allocated across invoices.
        
        Returns:
            list: [{invoice: FeeInvoice, amount: Decimal}, ...]
        """
        if not self.is_valid():
            return []
        
        invoices = self.cleaned_data['selected_invoices']
        total_amount = self.cleaned_data['total_amount']
        allocation_method = self.cleaned_data['allocation_method']
        custom_allocation = self.cleaned_data.get('custom_allocation')
        
        # Custom allocation - use provided amounts
        if allocation_method == 'custom' and custom_allocation:
            allocation = []
            for invoice in invoices:
                amount = Decimal(str(custom_allocation.get(str(invoice.id), '0.00')))
                if amount > 0:
                    allocation.append({
                        'invoice': invoice,
                        'amount': amount
                    })
            return allocation
        
        # Auto allocation methods
        invoice_list = list(invoices)
        
        # Sort based on method
        if allocation_method == 'oldest_first':
            invoice_list.sort(key=lambda x: x.issue_date)
        elif allocation_method == 'newest_first':
            invoice_list.sort(key=lambda x: x.issue_date, reverse=True)
        elif allocation_method == 'largest_first':
            invoice_list.sort(key=lambda x: x.balance, reverse=True)
        elif allocation_method == 'smallest_first':
            invoice_list.sort(key=lambda x: x.balance)
        # equal - no sorting needed
        
        allocation = []
        remaining = total_amount
        
        if allocation_method == 'equal':
            # Distribute equally
            per_invoice = total_amount / len(invoice_list)
            for invoice in invoice_list:
                amount = min(per_invoice, invoice.balance, remaining)
                allocation.append({
                    'invoice': invoice,
                    'amount': amount.quantize(Decimal('0.01'))
                })
                remaining -= amount
        else:
            # Waterfall allocation (pay invoices in full before moving to next)
            for invoice in invoice_list:
                if remaining <= 0:
                    break
                
                amount = min(invoice.balance, remaining)
                allocation.append({
                    'invoice': invoice,
                    'amount': amount
                })
                remaining -= amount
        
        # If any amount remaining (overpayment), add to last invoice
        if remaining > Decimal('0.01') and allocation:
            allocation[-1]['amount'] += remaining
        
        return allocation


# =============================================================================
# 3. PAYMENT REVERSAL FORM (Keep as is)
# =============================================================================

class PaymentReversalForm(BootstrapFormMixin, RequiredFieldsMixin, forms.Form):
    """Form for reversing a payment (internal correction, no money returned)"""
    
    reversal_reason = forms.CharField(
        label="Reversal Reason",
        widget=forms.Textarea(attrs={
            'rows': 4,
            'placeholder': (
                'Provide detailed reason for reversal:\n'
                '- Was payment posted to wrong invoice?\n'
                '- Was it a duplicate entry?\n'
                '- Was wrong amount entered?\n'
                '- Other specific details...'
            ),
            'class': 'form-control'
        }),
        help_text="Detailed explanation required for audit trail"
    )
    
    confirm_reversal = forms.BooleanField(
        label="I confirm this is an internal correction (no money was actually returned)",
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text=(
            "This is for correcting data entry errors only. "
            "No actual money is being returned to the payer. "
            "If money needs to be returned, use the REFUND function instead."
        )
    )
    
    def __init__(self, payment, user, *args, **kwargs):
        self.payment = payment
        self.user = user
        super().__init__(*args, **kwargs)
        
        # Add payment details to help text
        self.fields['reversal_reason'].help_text = (
            f"Reversing payment {payment.payment_number} - "
            f"Amount: {payment.amount:,.2f} - "
            f"Date: {payment.payment_date} - "
            f"Student: {payment.student.get_full_name()}"
        )
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Validate payment can be reversed
        can_reverse, reason = self.payment.can_be_reversed()
        if not can_reverse:
            raise ValidationError(f"Cannot reverse this payment: {reason}")
        
        # Ensure reason is meaningful
        reversal_reason = cleaned_data.get('reversal_reason', '').strip()
        if len(reversal_reason) < 20:
            raise ValidationError({
                'reversal_reason': 'Please provide a detailed reason (at least 20 characters).'
            })
        
        return cleaned_data


# =============================================================================
# 4. PAYMENT REFUND FORM (Keep as is)
# =============================================================================

class PaymentRefundForm(BootstrapFormMixin, RequiredFieldsMixin, MoneyFieldsMixin, forms.Form):
    """Form for processing payment refund (actual money returned to payer)"""
    
    refund_amount = MoneyField(
        label="Refund Amount",
        help_text="Amount to be refunded (cannot exceed payment amount)"
    )
    
    refund_method = forms.ChoiceField(
        label="Refund Method",
        choices=Payment._meta.get_field('refund_method').choices,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="How the refund will be issued to the payer"
    )
    
    refund_reference = forms.CharField(
        label="Refund Reference",
        max_length=100,
        widget=forms.TextInput(attrs={
            'placeholder': 'Bank reference, mobile money transaction ID, etc.',
            'class': 'form-control'
        }),
        help_text="Reference number for refund transaction"
    )
    
    refund_reason = forms.CharField(
        label="Refund Reason",
        widget=forms.Textarea(attrs={
            'rows': 4,
            'placeholder': (
                'Why is this refund being issued?\n'
                '- Student overpaid?\n'
                '- Student withdrew?\n'
                '- Service cancelled?\n'
                '- Other specific reason...'
            ),
            'class': 'form-control'
        }),
        help_text="Detailed explanation for audit trail"
    )
    
    refund_notes = forms.CharField(
        label="Refund Notes",
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'Additional notes about recipient, approval, etc.',
            'class': 'form-control'
        }),
        required=False,
        help_text="Optional notes (e.g., recipient details, approval notes)"
    )
    
    confirm_refund = forms.BooleanField(
        label="I confirm money will be/has been returned to the payer",
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text=(
            "Actual money is being returned to the payer. "
            "This action will affect cash/bank balances."
        )
    )
    
    def __init__(self, payment, user, *args, **kwargs):
        self.payment = payment
        self.user = user
        super().__init__(*args, **kwargs)
        
        # Set max refund amount
        self.fields['refund_amount'].initial = payment.amount
        self.fields['refund_amount'].help_text = (
            f"Maximum refundable: {payment.amount:,.2f} (original payment amount)"
        )
        
        # Pre-select refund method based on original payment method
        if payment.payment_method:
            method_name = payment.payment_method.name.upper()
            if 'BANK' in method_name:
                self.fields['refund_method'].initial = 'BANK_TRANSFER'
            elif 'MOBILE' in method_name:
                self.fields['refund_method'].initial = 'MOBILE_MONEY'
            elif 'CASH' in method_name:
                self.fields['refund_method'].initial = 'CASH'
        
        # Add payment details
        self.fields['refund_reason'].help_text = (
            f"Refunding payment {payment.payment_number} - "
            f"Original Amount: {payment.amount:,.2f} - "
            f"Date: {payment.payment_date} - "
            f"Student: {payment.student.get_full_name()}"
        )
    
    def clean_refund_amount(self):
        """Validate refund amount"""
        refund_amount = self.cleaned_data.get('refund_amount')
        
        if refund_amount:
            if refund_amount <= 0:
                raise ValidationError("Refund amount must be greater than zero.")
            
            if refund_amount > self.payment.amount:
                raise ValidationError(
                    f"Refund amount cannot exceed original payment amount of {self.payment.amount:,.2f}"
                )
        
        return refund_amount
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Validate payment can be refunded
        can_refund, reason = self.payment.can_be_refunded()
        if not can_refund:
            raise ValidationError(f"Cannot refund this payment: {reason}")
        
        # Ensure reason is meaningful
        refund_reason = cleaned_data.get('refund_reason', '').strip()
        if len(refund_reason) < 20:
            raise ValidationError({
                'refund_reason': 'Please provide a detailed reason (at least 20 characters).'
            })
        
        # Ensure reference is provided
        refund_reference = cleaned_data.get('refund_reference', '').strip()
        if len(refund_reference) < 5:
            raise ValidationError({
                'refund_reference': 'Please provide a valid reference number.'
            })
        
        return cleaned_data


# =============================================================================
# 5. PAYMENT FILTER FORM (Updated with payment_state)
# =============================================================================

class PaymentFilterForm(DateRangeFormMixin, BootstrapFormMixin, forms.Form):
    """Filter form for payment search"""
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by payment number, student, reference...'
        })
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
    
    payment_method = forms.ModelChoiceField(
        label='Payment Method',
        queryset=None,
        required=False,
        empty_label="All Methods",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    status = forms.ChoiceField(
        label='Status',
        choices=[('', 'All Statuses')] + list(Payment.PAYMENT_STATUS_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    payment_state = forms.ChoiceField(
        label='Payment State',
        choices=[
            ('', 'All Payments'),
            ('active', 'Active Only'),
            ('reversed', 'Reversed Only'),
            ('refunded', 'Refunded Only'),
            ('inactive', 'Reversed or Refunded'),
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Filter by reversal/refund status"
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
        
        self.fields['academic_session'].queryset = AcademicSession.objects.filter(
            is_active=True
        ).order_by('-start_date')
        
        self.fields['fiscal_period'].queryset = FiscalPeriod.objects.all().order_by('-start_date')
        
        self.fields['payment_method'].queryset = PaymentMethod.objects.filter(
            is_active=True
        ).order_by('name')


# =============================================================================
# 6. BULK PAYMENT VERIFICATION FORM (Keep as is)
# =============================================================================

class BulkPaymentVerificationForm(BootstrapFormMixin, forms.Form):
    """Form for verifying multiple payments at once"""
    
    payment_ids = forms.CharField(
        widget=forms.HiddenInput(),
        required=True
    )
    
    verification_notes = forms.CharField(
        label="Verification Notes",
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'Any notes for this verification batch...',
            'class': 'form-control'
        }),
        required=False
    )
    
    confirm_verification = forms.BooleanField(
        label="I confirm all selected payments have been verified",
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
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
        
        # Validate all payments exist and are completed
        payments = Payment.objects.filter(id__in=payment_ids)
        
        if payments.count() != len(payment_ids):
            raise ValidationError("Some selected payments do not exist")
        
        # Check for already verified
        already_verified = payments.filter(is_verified=True)
        if already_verified.exists():
            raise ValidationError(
                f"{already_verified.count()} payment(s) are already verified"
            )
        
        # Check for reversed/refunded
        inactive = payments.filter(Q(reversed=True) | Q(refunded=True))
        if inactive.exists():
            raise ValidationError(
                f"{inactive.count()} payment(s) are reversed or refunded and cannot be verified"
            )
        
        # Check status
        non_completed = payments.exclude(status='COMPLETED')
        if non_completed.exists():
            raise ValidationError(
                f"{non_completed.count()} payment(s) are not completed and cannot be verified"
            )
        
        return payment_ids
    
# =============================================================================
# SCHOLARSHIP FORMS
# =============================================================================

class CategoryDiscountTemplateForm(forms.Form):
    """
    Sub-form for configuring default discount template for a single fee category.
    Used within ScholarshipProgramForm when discount_type = CATEGORY_SPECIFIC.
    """
    
    category_code = forms.CharField(
        widget=forms.HiddenInput()
    )
    
    category_name = forms.CharField(
        disabled=True,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control-plaintext fw-bold',
            'readonly': True
        })
    )
    
    apply_discount = forms.BooleanField(
        required=False,
        initial=False,
        label="Cover this category",
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input category-apply-check'
        })
    )
    
    discount_type = forms.ChoiceField(
        choices=[
            ('percentage', 'Percentage Discount'),
            ('fixed_amount', 'Fixed Amount'),
            ('full_waiver', 'Full Waiver (100%)'),
            ('none', 'Not Covered'),
        ],
        initial='none',
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-select form-select-sm category-discount-type'
        })
    )
    
    discount_value = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        initial=Decimal('0.00'),
        widget=forms.NumberInput(attrs={
            'class': 'form-control form-control-sm category-discount-value',
            'placeholder': '0.00',
            'step': '0.01',
            'min': '0'
        })
    )
    
    description = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-sm',
            'placeholder': 'Optional notes...'
        })
    )

class CategoryDiscountForm(forms.Form):
    """
    Sub-form for configuring discount for a single fee category when awarding scholarship.
    """
    
    category_code = forms.CharField(widget=forms.HiddenInput())
    
    category_name = forms.CharField(
        disabled=True,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control-plaintext fw-bold',
            'readonly': True
        })
    )
    
    apply_discount = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input category-apply-discount'
        })
    )
    
    discount_type = forms.ChoiceField(
        choices=[
            ('percentage', 'Percentage Discount'),
            ('fixed_amount', 'Fixed Amount'),
            ('full_waiver', 'Full Waiver (100%)'),
            ('none', 'Not Covered'),
        ],
        initial='percentage',
        widget=forms.Select(attrs={
            'class': 'form-select category-discount-type'
        })
    )
    
    discount_value = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control category-discount-value',
            'placeholder': '0.00',
            'step': '0.01'
        })
    )

class ScholarshipProgramForm(RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """
    Enhanced form for creating/editing scholarship programs with category-specific discount support.
    Uses school timezone for date validations.
    """
    
    class Meta:
        model = ScholarshipProgram
        fields = [
            'name', 'code', 'scholarship_type', 'description',
            'program_type', 'discount_type', 
            'discount_percentage', 'fixed_discount_amount', 'maximum_award_amount',
            'allows_category_customization', 'category_discount_description',  # ⭐ NEW
            'applicable_fee_categories',
            'minimum_gpa', 'minimum_attendance_percentage', 'family_income_threshold',
            'applicable_levels', 
            'total_budget_amount', 'requires_budget_tracking', 'maximum_recipients',
            'renewal_policy', 'maximum_duration_years',
            'application_start_date', 'application_end_date', 'award_announcement_date',
            'sponsor_name', 'sponsor_contact', 'external_funding_source',
            'is_active', 'is_accepting_applications', 'valid_sessions'
        ]
        
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'e.g., Academic Merit Scholarship 2024'
            }),
            'code': forms.TextInput(attrs={
                'placeholder': 'e.g., SCHOL-MERIT-001',
                'style': 'text-transform: uppercase;'
            }),
            'scholarship_type': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': 'Detailed description of the scholarship program...'
            }),
            'program_type': forms.Select(attrs={'class': 'form-select'}),
            'discount_type': forms.Select(attrs={'class': 'form-select'}),
            'discount_percentage': PercentageInput(),
            'fixed_discount_amount': MoneyInput(),
            'maximum_award_amount': MoneyInput(),
            'allows_category_customization': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'category_discount_description': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Explain how category discounts work for this program...'
            }),
            'applicable_fee_categories': forms.SelectMultiple(attrs={
                'class': 'form-select',
                'size': '5'
            }),
            'minimum_gpa': forms.NumberInput(attrs={
                'min': '0',
                'max': '4',
                'step': '0.01',
                'placeholder': 'e.g., 3.5'
            }),
            'minimum_attendance_percentage': PercentageInput(),
            'family_income_threshold': MoneyInput(),
            'applicable_levels': forms.SelectMultiple(attrs={
                'class': 'form-select',
                'size': '5'
            }),
            'total_budget_amount': MoneyInput(),
            'requires_budget_tracking': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'maximum_recipients': forms.NumberInput(attrs={
                'min': '1',
                'placeholder': 'Maximum number of recipients'
            }),
            'renewal_policy': forms.Select(attrs={'class': 'form-select'}),
            'maximum_duration_years': forms.NumberInput(attrs={
                'min': '1',
                'placeholder': 'Years'
            }),
            'application_start_date': DatePickerInput(),
            'application_end_date': DatePickerInput(),
            'award_announcement_date': DatePickerInput(),
            'sponsor_name': forms.TextInput(attrs={
                'placeholder': 'Name of sponsor/donor'
            }),
            'sponsor_contact': forms.Textarea(attrs={
                'rows': 2,
                'placeholder': 'Contact information for sponsor...'
            }),
            'external_funding_source': forms.TextInput(attrs={
                'placeholder': 'External funding source if applicable'
            }),
            'valid_sessions': forms.SelectMultiple(attrs={
                'class': 'form-select',
                'size': '5'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set querysets
        try:
            self.fields['applicable_fee_categories'].queryset = FeesCategory.objects.filter(
                is_active=True
            ).order_by('display_group__display_order', 'display_order')
            
            self.fields['applicable_levels'].queryset = AcademicLevel.objects.filter(
                is_active=True
            ).order_by('order')
            
            self.fields['valid_sessions'].queryset = AcademicSession.objects.filter(
                is_active=True
            ).order_by('-start_date')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")
        
        # =====================================================================
        # ⭐ NEW: Initialize Category Discount Template Sub-Forms
        # =====================================================================
        
        self.category_forms = []
        
        # Get all active fee categories
        try:
            categories = FeesCategory.objects.filter(is_active=True).order_by(
                'display_group__display_order', 'display_order'
            )
        except Exception as e:
            logger.error(f"Error loading categories: {e}")
            categories = []
        
        # Get existing template if editing
        existing_template = {}
        if self.instance.pk and self.instance.default_category_discounts:
            existing_template = self.instance.default_category_discounts
        
        # Create a sub-form for each category
        for category in categories:
            cat_code = category.category_type or category.code
            discount_config = existing_template.get(cat_code, {})
            
            # Determine initial values
            discount_type = discount_config.get('type', 'none')
            discount_value = discount_config.get('value', 0.00)
            has_discount = discount_type != 'none'
            
            initial_data = {
                'category_code': cat_code,
                'category_name': category.name,
                'apply_discount': has_discount,
                'discount_type': discount_type,
                'discount_value': discount_value,
                'description': discount_config.get('description', ''),
            }
            
            form = CategoryDiscountTemplateForm(
                data=self.data if self.is_bound else None,
                prefix=f'cat_{cat_code}',
                initial=initial_data
            )
            
            self.category_forms.append({
                'form': form,
                'category': category,
                'code': cat_code
            })
        
        # Help texts
        self.fields['code'].help_text = "Unique scholarship code (automatically uppercased)"
        self.fields['program_type'].help_text = "How this program is funded and managed"
        self.fields['discount_type'].help_text = (
            "PERCENTAGE/FIXED_AMOUNT/FULL_WAIVER: Same discount for all categories. "
            "CATEGORY_SPECIFIC: Define different discounts per category."
        )
        self.fields['applicable_fee_categories'].help_text = (
            "Leave empty to apply to all fee categories (Legacy - use category discounts for granular control)"
        )
        self.fields['applicable_levels'].help_text = "Leave empty to apply to all levels"
        self.fields['total_budget_amount'].help_text = "Required for BUDGETED and SPONSORED programs"
        self.fields['requires_budget_tracking'].help_text = "Track spending against budget? False for unlimited programs"
        self.fields['allows_category_customization'].help_text = (
            "Allow scholarship officers to customize category discounts per student?"
        )
    
    def clean_code(self):
        """Ensure code is uppercase"""
        code = self.cleaned_data.get('code', '')
        return code.upper()
    
    def is_valid(self):
        """Validate main form + category sub-forms (if applicable)"""
        main_valid = super().is_valid()
        
        # Only validate category forms if discount_type is CATEGORY_SPECIFIC
        discount_type = self.cleaned_data.get('discount_type') if hasattr(self, 'cleaned_data') else None
        
        if discount_type == 'CATEGORY_SPECIFIC':
            category_valid = all(item['form'].is_valid() for item in self.category_forms)
            return main_valid and category_valid
        
        return main_valid
    
    def clean(self):
        """Enhanced validation with category discount support using school timezone"""
        cleaned_data = super().clean()
        
        program_type = cleaned_data.get('program_type')
        total_budget = cleaned_data.get('total_budget_amount')
        discount_type = cleaned_data.get('discount_type')
        
        # =====================================================================
        # VALIDATE BUDGET REQUIREMENTS
        # =====================================================================
        
        if program_type in ['BUDGETED', 'SPONSORED']:
            if not total_budget:
                raise ValidationError({
                    'total_budget_amount': 'Budget amount is required for budgeted/sponsored programs.'
                })
        
        if program_type == 'POLICY_BASED':
            if total_budget:
                raise ValidationError({
                    'total_budget_amount': 'Policy-based programs should not have budget limits.'
                })
        
        # =====================================================================
        # VALIDATE DISCOUNT CONFIGURATION ⭐ NEW
        # =====================================================================
        
        if discount_type == 'PERCENTAGE':
            discount_percentage = cleaned_data.get('discount_percentage')
            if not discount_percentage:
                raise ValidationError({
                    'discount_percentage': 'Percentage is required for percentage discount type.'
                })
        
        elif discount_type == 'FIXED_AMOUNT':
            fixed_discount_amount = cleaned_data.get('fixed_discount_amount')
            if not fixed_discount_amount:
                raise ValidationError({
                    'fixed_discount_amount': 'Fixed amount is required for fixed amount discount type.'
                })
        
        elif discount_type == 'CATEGORY_SPECIFIC':
            # Validate at least one category has a discount
            has_any_discount = False
            
            for item in self.category_forms:
                form = item['form']
                if form.is_valid():
                    data = form.cleaned_data
                    if data.get('apply_discount') and data.get('discount_type') != 'none':
                        has_any_discount = True
                        break
            
            if not has_any_discount:
                raise ValidationError({
                    'discount_type': (
                        'Category-specific discount requires at least one category to have a discount configured.'
                    )
                })
        
        # =====================================================================
        # VALIDATE DATES
        # =====================================================================
        
        start_date = cleaned_data.get('application_start_date')
        end_date = cleaned_data.get('application_end_date')
        
        if start_date and end_date:
            if end_date < start_date:
                raise ValidationError({
                    'application_end_date': 'Application end date cannot be before start date.'
                })
        
        return cleaned_data
    
    def save(self, commit=True):
        """Save program with category discount template"""
        instance = super().save(commit=False)
        
        # =====================================================================
        # ⭐ BUILD default_category_discounts JSON
        # =====================================================================
        
        if self.cleaned_data.get('discount_type') == 'CATEGORY_SPECIFIC':
            category_template = {}
            
            for item in self.category_forms:
                form = item['form']
                code = item['code']
                
                if form.is_valid():
                    data = form.cleaned_data
                    
                    if data.get('apply_discount'):
                        discount_type = data.get('discount_type', 'none')
                        discount_value = data.get('discount_value', 0.00)
                        description = data.get('description', '')
                        
                        category_template[code] = {
                            'type': discount_type,
                            'value': float(discount_value),
                        }
                        
                        if description:
                            category_template[code]['description'] = description
                    else:
                        # Not covered
                        category_template[code] = {
                            'type': 'none',
                            'value': 0.00
                        }
            
            instance.default_category_discounts = category_template
        else:
            # Clear category template for non-category-specific modes
            instance.default_category_discounts = {}
        
        if commit:
            instance.save()
            self.save_m2m()
        
        return instance


class ScholarshipProgramFilterForm(DateRangeFormMixin, BootstrapFormMixin, forms.Form):
    """Filter form for scholarship program search"""
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by name, code, sponsor...'
        })
    )
    
    scholarship_type = forms.ChoiceField(
        label='Scholarship Type',
        choices=[('', 'All Types')] + list(ScholarshipProgram.SCHOLARSHIP_TYPES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    program_type = forms.ChoiceField(
        label='Program Type',
        choices=[('', 'All Program Types')] + list(ScholarshipProgram.PROGRAM_TYPE_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    discount_type = forms.ChoiceField(  # ⭐ NEW
        label='Discount Type',
        choices=[('', 'All Discount Types')] + list(ScholarshipProgram.DISCOUNT_TYPE_CHOICES),
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
    
    is_accepting_applications = forms.NullBooleanField(
        label='Accepting Applications',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Accepting'),
            ('false', 'Not Accepting')
        ], attrs={'class': 'form-select'})
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class StudentScholarshipApplicationForm(RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """Form for scholarship applications"""
    
    class Meta:
        model = StudentScholarshipApplication
        fields = [
            'student', 'scholarship_program', 'academic_session',
            'requested_amount', 'essay', 'family_income', 'number_of_dependents',
            'special_circumstances', 'current_gpa', 'attendance_percentage'
        ]
        widgets = {
            'student': forms.Select(attrs={'class': 'form-select'}),
            'scholarship_program': forms.Select(attrs={'class': 'form-select'}),
            'academic_session': forms.Select(attrs={'class': 'form-select'}),
            'requested_amount': MoneyInput(),
            'essay': forms.Textarea(attrs={
                'rows': 8,
                'placeholder': 'Write your personal essay...'
            }),
            'family_income': MoneyInput(),
            'number_of_dependents': forms.NumberInput(attrs={'min': '0'}),
            'special_circumstances': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': 'Describe any special circumstances...'
            }),
            'current_gpa': forms.NumberInput(attrs={
                'min': '0',
                'max': '4',
                'step': '0.01'
            }),
            'attendance_percentage': PercentageInput(),
        }
    
    def __init__(self, *args, **kwargs):
        student = kwargs.pop('student', None)
        super().__init__(*args, **kwargs)
        
        try:
            if student:
                self.fields['student'].initial = student
            else:
                self.fields['student'].queryset = Student.objects.filter(
                    enrollment_status='ACTIVE'
                ).order_by('first_name', 'last_name')
            
            self.fields['scholarship_program'].queryset = ScholarshipProgram.objects.filter(
                is_active=True,
                is_accepting_applications=True
            ).order_by('name')
            
            self.fields['academic_session'].queryset = AcademicSession.objects.filter(
                is_active=True
            ).order_by('-start_date')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")


class ScholarshipApplicationFilterForm(DateRangeFormMixin, BootstrapFormMixin, forms.Form):
    """Filter form for scholarship application search"""
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by student, application number...'
        })
    )
    
    scholarship_program = forms.ModelChoiceField(
        label='Program',
        queryset=None,
        required=False,
        empty_label="All Programs",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    status = forms.ChoiceField(
        label='Status',
        choices=[('', 'All Statuses')] + list(StudentScholarshipApplication.APPLICATION_STATUS_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    application_date_from = forms.DateField(
        label='Applied From',
        required=False,
        widget=DatePickerInput()
    )
    
    application_date_to = forms.DateField(
        label='Applied To',
        required=False,
        widget=DatePickerInput()
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
            self.fields['scholarship_program'].queryset = ScholarshipProgram.objects.filter(
                is_active=True
            ).order_by('name')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")


class StudentScholarshipForm(RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """
    Enhanced form with category-specific discount configuration.
    """
    
    class Meta:
        model = StudentScholarship
        fields = [
            'student', 'scholarship_program', 'application',
            'amount_awarded', 'start_date', 'end_date',
            'use_category_specific_discounts',  # ⭐ NEW
            'category_discount_notes',  # ⭐ NEW
            'distribution_method', 'amount_per_session', 'amount_per_invoice',
            'max_amount_per_session',
            'is_renewable', 'requires_renewal_verification',
            'notes'
        ]
        widgets = {
            'student': forms.Select(attrs={
                'class': 'form-select',
                'data-placeholder': 'Select student...'
            }),
            'scholarship_program': forms.Select(attrs={
                'class': 'form-select',
                'data-placeholder': 'Select scholarship program...'
            }),
            'application': forms.Select(attrs={
                'class': 'form-select',
                'data-placeholder': 'Select application (optional)...'
            }),
            'amount_awarded': MoneyInput(attrs={
                'placeholder': '0.00'
            }),
            'start_date': DatePickerInput(),
            'end_date': DatePickerInput(),
            'distribution_method': forms.Select(attrs={'class': 'form-select'}),
            'amount_per_session': MoneyInput(),
            'amount_per_invoice': MoneyInput(),
            'max_amount_per_session': MoneyInput(),
            'category_discount_notes': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Optional notes explaining why specific category discounts were configured...'
            }),
            'notes': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Administrative notes...'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        application = kwargs.pop('application', None)
        super().__init__(*args, **kwargs)
        
        # ⭐ NEW: Store scholarship_program_instance for template access
        self.scholarship_program_instance = None
        
        # Pre-populate from application if provided
        if application:
            self.fields['student'].initial = application.student
            self.fields['scholarship_program'].initial = application.scholarship_program
            self.fields['application'].initial = application
            self.fields['amount_awarded'].initial = application.approved_amount or application.requested_amount
            # ⭐ NEW: Store program instance
            self.scholarship_program_instance = application.scholarship_program
        
        # ⭐ NEW: If editing existing scholarship, store program instance
        elif self.instance.pk and self.instance.scholarship_program_id:
            self.scholarship_program_instance = self.instance.scholarship_program
        
        # Set default dates
        if not self.is_bound and not self.instance.pk:
            self.fields['start_date'].initial = get_school_today()
        
        # Set querysets
        try:
            self.fields['student'].queryset = Student.objects.filter(
                enrollment_status='ACTIVE'
            ).order_by('first_name', 'last_name')
            
            self.fields['scholarship_program'].queryset = ScholarshipProgram.objects.filter(
                is_active=True
            ).order_by('name')
            
            self.fields['application'].queryset = StudentScholarshipApplication.objects.filter(
                status='APPROVED'
            ).order_by('-application_date')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")
        
        # =====================================================================
        # ⭐ NEW: Initialize Category Discount Sub-Forms
        # =====================================================================
        
        self.category_forms = []
        
        # Get all active fee categories
        categories = FeesCategory.objects.filter(is_active=True).order_by(
            'display_group__display_order', 'display_order'
        )
        
        # Determine initial category discounts
        existing_discounts = {}
        
        if self.instance.pk and self.instance.category_discounts:
            # ⭐ EDIT MODE: Use existing scholarship's category discounts
            existing_discounts = self.instance.category_discounts
            logger.info(f"Edit mode: Loading {len(existing_discounts)} category discounts from scholarship")
        elif self.scholarship_program_instance:
            # New scholarship - use program template
            if self.scholarship_program_instance.is_category_specific_discount():
                existing_discounts = self.scholarship_program_instance.get_category_discount_template()
                logger.info(f"New scholarship: Loading {len(existing_discounts)} category discounts from program template")
        
        # Create a sub-form for each category
        for category in categories:
            cat_code = category.category_type or category.code
            discount_config = existing_discounts.get(cat_code, {})
            
            discount_type = discount_config.get('type', 'none')
            discount_value = discount_config.get('value', 0.00)
            has_discount = discount_type != 'none'
            
            initial_data = {
                'category_code': cat_code,
                'category_name': category.name,
                'apply_discount': has_discount,
                'discount_type': discount_type,
                'discount_value': discount_value,
            }
            
            form = CategoryDiscountForm(
                data=self.data if self.is_bound else None,
                prefix=f'cat_{cat_code}',
                initial=initial_data
            )
            
            self.category_forms.append({
                'form': form,
                'category': category,
                'code': cat_code
            })
        
        logger.info(f"Initialized {len(self.category_forms)} category discount forms")
        
        # Help texts
        self.fields['use_category_specific_discounts'].help_text = (
            "Enable to configure different discounts for each fee category. "
            "When disabled, the program's global discount applies to all categories."
        )
        self.fields['amount_awarded'].help_text = (
            "For budget-based scholarships: Total amount available. "
            "For policy-based: Set to 0.00 (discount comes from program percentage)."
        )
    
    def is_valid(self):
        """Validate main form + all category sub-forms (if applicable)"""
        main_valid = super().is_valid()
        
        # Only validate category forms if use_category_specific_discounts is True
        if self.cleaned_data.get('use_category_specific_discounts'):
            category_valid = all(item['form'].is_valid() for item in self.category_forms)
            return main_valid and category_valid
        
        return main_valid
    
    def clean(self):
        """Enhanced validation with improved category discount handling"""
        cleaned_data = super().clean()
        
        # =================================================================
        # ⭐ POPULATE category_discounts on the instance EARLY.
        # Django's _post_clean() calls instance.full_clean() AFTER form
        # clean() but BEFORE save(). If we wait until save() to build
        # category_discounts, the model's clean() sees an empty dict and
        # raises a ValidationError. Building it here fixes that.
        # =================================================================
        
        if cleaned_data.get('use_category_specific_discounts'):
            category_discounts = {}
            has_any_discount = False  # ✅ Track if at least one category has a non-'none' discount
            
            for item in self.category_forms:
                form = item['form']
                code = item['code']
                
                if form.is_valid():
                    data = form.cleaned_data
                    
                    if data.get('apply_discount'):
                        discount_type = data.get('discount_type', 'none')
                        discount_value = data.get('discount_value', 0.00)
                        
                        # ✅ Only mark as having discount if type is not 'none'
                        if discount_type != 'none':
                            has_any_discount = True
                        
                        category_discounts[code] = {
                            'type': discount_type,
                            'value': float(discount_value)
                        }
                    else:
                        # Explicitly set to 'none' if not applying discount
                        category_discounts[code] = {
                            'type': 'none',
                            'value': 0.00
                        }
            
            # ✅ EARLY VALIDATION: Must have at least one non-'none' discount
            if not has_any_discount:
                raise ValidationError({
                    'use_category_specific_discounts': (
                        'At least one category must have a discount configured when using category-specific mode. '
                        'Please either: (1) Configure discounts for at least one category below, OR '
                        '(2) Disable category-specific discounts to use the program\'s global discount.'
                    )
                })
            
            # ✅ Set on instance for model validation
            self.instance.category_discounts = category_discounts
            
            logger.info(
                f"Built category_discounts for scholarship: {len(category_discounts)} categories, "
                f"{sum(1 for c in category_discounts.values() if c.get('type') != 'none')} with discounts"
            )
        else:
            # Clear category discounts if not using category-specific mode
            self.instance.category_discounts = {}
        
        # =================================================================
        # EXISTING VALIDATION (unchanged)
        # =================================================================
        
        student = cleaned_data.get('student')
        scholarship_program = cleaned_data.get('scholarship_program')
        amount_awarded = cleaned_data.get('amount_awarded') or Decimal('0.00')
        use_category_specific = cleaned_data.get('use_category_specific_discounts')
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        
        # =================================================================
        # VALIDATE AMOUNT BASED ON PROGRAM TYPE
        # =================================================================
        
        if scholarship_program:
            # For BUDGETED and SPONSORED programs: amount must be > 0
            if scholarship_program.program_type in ['BUDGETED', 'SPONSORED']:
                if not amount_awarded or amount_awarded <= 0:
                    raise ValidationError({
                        'amount_awarded': (
                            f"'{scholarship_program.name}' is a budget-based program. "
                            f"Please specify the amount being awarded to this student."
                        )
                    })
            
            # For POLICY_BASED and DISCRETIONARY: amount can be 0 if using discounts
            elif scholarship_program.program_type in ['POLICY_BASED', 'DISCRETIONARY']:
                if not amount_awarded or amount_awarded <= 0:
                    has_discount = False
                    
                    # Check global discount
                    if scholarship_program.is_global_discount():
                        if scholarship_program.discount_type == 'PERCENTAGE' and scholarship_program.discount_percentage:
                            has_discount = True
                        elif scholarship_program.discount_type == 'FIXED_AMOUNT' and scholarship_program.fixed_discount_amount:
                            has_discount = True
                        elif scholarship_program.discount_type == 'FULL_WAIVER':
                            has_discount = True
                    
                    # Check category-specific discount
                    elif scholarship_program.is_category_specific_discount():
                        if use_category_specific:
                            # ✅ Check the category_discounts we already built above
                            # Already validated that has_any_discount is True if we get here
                            has_discount = any(
                                config.get('type') != 'none'
                                for config in self.instance.category_discounts.values()
                            )
                        else:
                            # Using program's default category template
                            if scholarship_program.default_category_discounts:
                                has_discount = any(
                                    config.get('type') != 'none'
                                    for code, config in scholarship_program.default_category_discounts.items()
                                )
                    
                    if not has_discount:
                        raise ValidationError({
                            'amount_awarded': (
                                'For policy-based scholarships, you must either: '
                                '(1) Specify an amount awarded, OR '
                                '(2) Configure discount percentages/amounts. '
                                'Please provide at least one.'
                            )
                        })
        
        # =================================================================
        # VALIDATE DATES
        # =================================================================
        
        if start_date and end_date:
            if end_date < start_date:
                raise ValidationError({
                    'end_date': 'End date cannot be before start date.'
                })
        
        # =================================================================
        # ✅ REMOVED: Category-specific validation (already done above)
        # This was redundant since we already validate has_any_discount
        # when building category_discounts
        # =================================================================
        
        return cleaned_data
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # =====================================================================
        # ⭐ BUILD category_discounts JSON from sub-forms
        # =====================================================================
        
        if self.cleaned_data.get('use_category_specific_discounts'):
            category_discounts = {}
            
            for item in self.category_forms:
                form = item['form']
                code = item['code']
                
                if form.is_valid():
                    data = form.cleaned_data
                    
                    if data.get('apply_discount'):
                        discount_type = data.get('discount_type', 'none')
                        discount_value = data.get('discount_value', 0.00)
                        
                        category_discounts[code] = {
                            'type': discount_type,
                            'value': float(discount_value)
                        }
                    else:
                        category_discounts[code] = {
                            'type': 'none',
                            'value': 0.00
                        }
            
            instance.category_discounts = category_discounts
        else:
            instance.category_discounts = {}
        
        if commit:
            instance.save()
        
        return instance
    
class QuickScholarshipAwardForm(RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.Form):
    """
    Simplified form for quickly awarding scholarships without category customization.
    Uses program's default configuration.
    """
    
    student = forms.ModelChoiceField(
        queryset=Student.objects.none(),
        label="Student",
        widget=forms.Select(attrs={
            'class': 'form-select',
            'data-placeholder': 'Select student...'
        })
    )
    
    scholarship_program = forms.ModelChoiceField(
        queryset=ScholarshipProgram.objects.none(),
        label="Scholarship Program",
        widget=forms.Select(attrs={
            'class': 'form-select',
            'data-placeholder': 'Select program...'
        })
    )
    
    amount_awarded = forms.DecimalField(
        label="Amount Awarded",
        max_digits=12,
        decimal_places=2,
        required=False,
        widget=MoneyInput(attrs={
            'placeholder': '0.00 (leave empty for policy-based)'
        }),
        help_text="For budget-based scholarships only. Leave empty for policy-based."
    )
    
    start_date = forms.DateField(
        label="Start Date",
        widget=DatePickerInput()
    )
    
    end_date = forms.DateField(
        label="End Date",
        required=False,
        widget=DatePickerInput(),
        help_text="Leave empty for no end date"
    )
    
    use_program_defaults = forms.BooleanField(
        label="Use Program's Default Category Discounts",
        initial=True,
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        }),
        help_text="Apply program's default category discount template without customization"
    )
    
    notes = forms.CharField(
        label="Notes",
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'Optional administrative notes...'
        })
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.fields['student'].queryset = Student.objects.filter(
            enrollment_status='ACTIVE'
        ).order_by('first_name', 'last_name')
        
        self.fields['scholarship_program'].queryset = ScholarshipProgram.objects.filter(
            is_active=True
        ).order_by('name')
        
        if not self.is_bound:
            self.fields['start_date'].initial = get_school_today()
    
    def clean(self):
        cleaned_data = super().clean()
        
        program = cleaned_data.get('scholarship_program')
        amount_awarded = cleaned_data.get('amount_awarded')
        
        if program:
            # Validate amount_awarded based on program type
            if program.program_type in ['BUDGETED', 'SPONSORED']:
                if not amount_awarded or amount_awarded <= 0:
                    raise ValidationError({
                        'amount_awarded': (
                            f"'{program.name}' is a budget-based program and requires "
                            f"a specific amount to be awarded."
                        )
                    })
        
        return cleaned_data


# fees/forms.py - Enhanced StudentScholarshipFilterForm

class StudentScholarshipFilterForm(BootstrapFormMixin, forms.Form):
    """Enhanced filter form for student scholarship search with category-specific support"""
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by student name, program...'
        })
    )
    
    scholarship_program = forms.ModelChoiceField(
        label='Program',
        queryset=None,
        required=False,
        empty_label="All Programs",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    status = forms.ChoiceField(
        label='Status',
        choices=[('', 'All Statuses')] + list(StudentScholarship.SCHOLARSHIP_STATUS_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    # ⭐ NEW: Filter by scholarship type (program type)
    program_type = forms.ChoiceField(
        label='Program Type',
        choices=[('', 'All Program Types')] + list(ScholarshipProgram.PROGRAM_TYPE_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    # ⭐ NEW: Filter by category-specific mode
    discount_mode = forms.ChoiceField(
        label='Discount Mode',
        choices=[
            ('', 'All Modes'),
            ('global', 'Global Discount'),
            ('category_specific', 'Category-Specific'),
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    # ⭐ NEW: Filter by scholarship type (budget vs policy)
    scholarship_type = forms.ChoiceField(
        label='Scholarship Type',
        choices=[
            ('', 'All Types'),
            ('policy_based', 'Policy-Based'),
            ('budget_based', 'Budget-Based'),
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    # ⭐ NEW: Filter by budget status
    budget_status = forms.ChoiceField(
        label='Budget Status',
        choices=[
            ('', 'All'),
            ('active', 'Has Balance'),
            ('exhausted', 'Exhausted'),
            ('not_applicable', 'No Budget (Policy-Based)'),
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    # Existing date filters (optional enhancement)
    active_on_date = forms.DateField(
        label='Active On',
        required=False,
        widget=DatePickerInput(),
        help_text="Show scholarships active on this date"
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
            self.fields['scholarship_program'].queryset = ScholarshipProgram.objects.filter(
                is_active=True
            ).order_by('name')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")


# =============================================================================
# DISCOUNT FORMS
# =============================================================================

class FeesDiscountForm(RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """
    Form for creating/editing fee discounts.
    Uses school timezone for date validations. ⭐
    """
    
    class Meta:
        model = FeesDiscount
        fields = [
            'name', 'code', 'discount_type', 'discount_value', 'description',
            'eligibility_criteria', 'applicable_categories', 'applicable_structures',
            'academic_session', 'start_date', 'end_date',
            'max_usage_count', 'budget_limit', 'auto_apply', 'requires_approval',
            'priority', 'can_combine_with_other_discounts', 'is_active'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'e.g., Early Bird Discount'
            }),
            'code': forms.TextInput(attrs={
                'placeholder': 'e.g., EARLY2024',
                'style': 'text-transform: uppercase;'
            }),
            'discount_type': forms.Select(attrs={'class': 'form-select'}),
            'discount_value': MoneyInput(),
            'description': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Description of discount...'
            }),
            'eligibility_criteria': forms.Select(attrs={'class': 'form-select'}),
            'applicable_categories': forms.SelectMultiple(attrs={
                'class': 'form-select',
                'size': '5'
            }),
            'applicable_structures': forms.SelectMultiple(attrs={
                'class': 'form-select',
                'size': '5'
            }),
            'academic_session': forms.Select(attrs={'class': 'form-select'}),
            'start_date': DatePickerInput(),
            'end_date': DatePickerInput(),
            'max_usage_count': forms.NumberInput(attrs={'min': '1'}),
            'budget_limit': MoneyInput(),
            'priority': forms.NumberInput(attrs={'min': '1'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
            self.fields['applicable_categories'].queryset = FeesCategory.objects.filter(
                is_active=True
            ).order_by('display_group__display_order', 'display_order')
            
            self.fields['applicable_structures'].queryset = FeesStructure.objects.filter(
                is_active=True
            ).order_by('structure_type', 'name')
            
            self.fields['academic_session'].queryset = AcademicSession.objects.filter(
                is_active=True
            ).order_by('-start_date')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")
        
        if not self.is_bound:
            today = get_school_today()  # ⭐ SCHOOL TIMEZONE
            self.fields['start_date'].initial = today
            self.fields['end_date'].initial = today + timezone.timedelta(days=90)
        
        self.fields['code'].help_text = "Unique discount code"
        self.fields['priority'].help_text = "Lower number = higher priority"
    
    def clean_code(self):
        """Ensure code is uppercase"""
        code = self.cleaned_data.get('code', '')
        return code.upper()
    
    def clean(self):
        """Validate discount data using school timezone ⭐"""
        cleaned_data = super().clean()
        
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        
        if start_date and end_date:
            if end_date < start_date:
                raise ValidationError({
                    'end_date': 'End date cannot be before start date.'
                })
        
        return cleaned_data


class FeesDiscountFilterForm(DateRangeFormMixin, BootstrapFormMixin, forms.Form):
    """Filter form for discount search"""
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by name, code...'
        })
    )
    
    discount_type = forms.ChoiceField(
        label='Discount Type',
        choices=[('', 'All Types')] + list(FeesDiscount.DISCOUNT_TYPES),
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
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


# =============================================================================
# REFUND FORMS
# =============================================================================

class RefundForm(RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """
    Form for processing refunds.
    Uses school timezone for date validations. ⭐
    """
    
    class Meta:
        model = Refund
        fields = [
            'student', 'refund_type', 'amount', 'reason',
            'invoice', 'payment', 'academic_session', 'fiscal_period',
            'payment_method', 'bank_details', 'supporting_documents'
        ]
        widgets = {
            'student': forms.Select(attrs={'class': 'form-select'}),
            'refund_type': forms.Select(attrs={'class': 'form-select'}),
            'amount': MoneyInput(),
            'reason': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': 'Detailed reason for refund...'
            }),
            'invoice': forms.Select(attrs={'class': 'form-select'}),
            'payment': forms.Select(attrs={'class': 'form-select'}),
            'academic_session': forms.Select(attrs={'class': 'form-select'}),
            'fiscal_period': forms.Select(attrs={'class': 'form-select'}),
            'payment_method': forms.Select(attrs={'class': 'form-select'}),
            'bank_details': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Bank account details for refund payment...'
            }),
            'supporting_documents': forms.Textarea(attrs={
                'rows': 2,
                'placeholder': 'List of supporting documents...'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        student = kwargs.pop('student', None)
        super().__init__(*args, **kwargs)
        
        try:
            if student:
                self.fields['student'].initial = student
                self.fields['invoice'].queryset = FeeInvoice.objects.filter(
                    student=student
                ).order_by('-issue_date')
                self.fields['payment'].queryset = Payment.objects.filter(
                    student=student
                ).order_by('-payment_date')
            else:
                self.fields['student'].queryset = Student.objects.filter(
                    enrollment_status='ACTIVE'
                ).order_by('first_name', 'last_name')
                self.fields['invoice'].queryset = FeeInvoice.objects.all().order_by('-issue_date')
                self.fields['payment'].queryset = Payment.objects.all().order_by('-payment_date')
            
            self.fields['academic_session'].queryset = AcademicSession.objects.filter(
                is_active=True
            ).order_by('-start_date')
            
            self.fields['fiscal_period'].queryset = FiscalPeriod.objects.filter(
                status__in=['OPEN', 'CURRENT']
            ).order_by('-start_date')
            
            self.fields['payment_method'].queryset = PaymentMethod.objects.filter(
                is_active=True
            ).order_by('name')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")


class RefundFilterForm(DateRangeFormMixin, BootstrapFormMixin, forms.Form):
    """Filter form for refund search"""
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by refund number, student...'
        })
    )
    
    refund_type = forms.ChoiceField(
        label='Refund Type',
        choices=[('', 'All Types')] + list(Refund.REFUND_TYPES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    status = forms.ChoiceField(
        label='Status',
        choices=[('', 'All Statuses')] + list(Refund.STATUS_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


# =============================================================================
# STUDENT ACCOUNT FORMS
# =============================================================================

class StudentAccountForm(RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """Form for creating/editing student accounts"""
    
    class Meta:
        model = StudentAccount
        fields = [
            'student', 'credit_limit', 'status'
        ]
        widgets = {
            'student': forms.Select(attrs={
                'class': 'form-select',
                'data-placeholder': 'Select student...'
            }),
            'credit_limit': MoneyInput(),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
            self.fields['student'].queryset = Student.objects.filter(
                enrollment_status='ACTIVE'
            ).order_by('first_name', 'last_name')
        except Exception as e:
            logger.error(f"Error setting student queryset: {e}")
        
        self.fields['credit_limit'].help_text = "Maximum negative balance allowed"


class StudentAccountAdjustmentForm(RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.Form):
    """Form for making manual adjustments to student accounts"""
    
    ADJUSTMENT_TYPE_CHOICES = [
        ('CREDIT', 'Credit (Add to Account)'),
        ('DEBIT', 'Debit (Subtract from Account)'),
    ]
    
    adjustment_type = forms.ChoiceField(
        label='Adjustment Type',
        choices=ADJUSTMENT_TYPE_CHOICES,
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    amount = MoneyField(
        label='Amount',
        required=True,
        help_text='Amount to adjust (always positive)'
    )
    
    reason = forms.CharField(
        label='Reason',
        required=True,
        widget=forms.Textarea(attrs={
            'rows': 4,
            'placeholder': 'Detailed reason for this adjustment...'
        })
    )
    
    reference_number = forms.CharField(
        label='Reference Number',
        required=False,
        max_length=50,
        widget=forms.TextInput(attrs={
            'placeholder': 'Optional reference number'
        })
    )
    
    def clean_amount(self):
        """Ensure amount is positive"""
        amount = self.cleaned_data.get('amount')
        if amount and amount <= 0:
            raise ValidationError('Amount must be greater than zero.')
        return amount


class StudentAccountFilterForm(BootstrapFormMixin, forms.Form):
    """Filter form for student account search"""
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by student name...'
        })
    )
    
    status = forms.ChoiceField(
        label='Status',
        choices=[('', 'All Statuses')] + list(StudentAccount.ACCOUNT_STATUS_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    balance_status = forms.ChoiceField(
        label='Balance',
        choices=[
            ('', 'All'),
            ('positive', 'Credit (Overpaid)'),
            ('zero', 'Zero Balance'),
            ('negative', 'Debit (Outstanding)'),
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    min_balance = MoneyField(
        label='Min Balance',
        required=False
    )
    
    max_balance = MoneyField(
        label='Max Balance',
        required=False
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


# =============================================================================
# BULK OPERATIONS FORMS
# =============================================================================

# fees/forms.py - ENHANCED VERSION

class BulkInvoiceGenerationForm(RequiredFieldsMixin, BootstrapFormMixin, forms.Form):
    """
    Form for generating invoices in bulk based on class enrollments.
    Uses school timezone for date validations. ⭐
    """
    
    # =========================================================================
    # REQUIRED FIELDS
    # =========================================================================
    
    academic_session = forms.ModelChoiceField(
        label='Academic Session',
        queryset=None,
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Session for which to generate invoices'
    )
    
    fiscal_period = forms.ModelChoiceField(
        label='Fiscal Period',
        queryset=None,
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Fiscal period for invoice issuance (for financial reporting)'
    )
    
    # =========================================================================
    # STUDENT FILTERING
    # =========================================================================
    
    target_students = forms.ChoiceField(
        label='Target Students',
        choices=[
            ('all_enrolled', 'All Enrolled Students in Session'),
            ('by_level', 'By Academic Level'),
            ('by_class', 'By Specific Class'),
            ('by_enrollment_type', 'By Enrollment Type'),
            ('by_boarding', 'By Boarding Status'),
            ('without_invoice', 'Only Students Without Invoice'),
        ],
        required=True,
        initial='without_invoice',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    academic_levels = forms.ModelMultipleChoiceField(
        queryset=AcademicLevel.objects.none(),  # ✅ Start with empty queryset
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Select Academic Levels",
        help_text="Select one or more levels (only if filtering by level)"
    )
    
    classes = forms.ModelMultipleChoiceField(
        queryset=Class.objects.none(),  # ✅ Start with empty queryset
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Select Classes",
        help_text="Select one or more classes (only if filtering by class)"
    )
    
    enrollment_types = forms.MultipleChoiceField(
        label='Enrollment Types',
        choices=[
            ('NEW', 'New Students'),
            ('CONTINUING', 'Continuing Students'),
            ('TRANSFER_IN', 'Transfer Students'),
        ],
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text='Select enrollment types (if targeting by enrollment type)'
    )
    
    boarding_types = forms.MultipleChoiceField(
        label='Boarding Types',
        choices=[
            ('DAY_SCHOLAR', 'Day Scholars'),
            ('FULL_BOARDER', 'Full Boarders'),
            ('WEEKLY_BOARDER', 'Weekly Boarders'),
            ('FLEXI_BOARDER', 'Flexible Boarders'),
        ],
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text='Select boarding types (if targeting by boarding status)'
    )
    
    # =========================================================================
    # INVOICE PARAMETERS
    # =========================================================================
    
    issue_date = forms.DateField(
        label='Issue Date',
        required=True,
        widget=DatePickerInput(),
        help_text='Invoice issue date'
    )
    
    due_date = forms.DateField(
        label='Due Date',
        required=True,
        widget=DatePickerInput(),
        help_text='Payment due date'
    )
    
    payment_terms = forms.CharField(
        label='Payment Terms',
        max_length=200,
        required=False,
        widget=forms.Textarea(attrs={'rows': 2}),
        help_text='Payment terms to display on invoices'
    )
    
    # =========================================================================
    # AUTO-APPLICATION OPTIONS
    # =========================================================================
    
    auto_apply_scholarships = forms.BooleanField(
        label='Auto-apply Active Scholarships',
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text='Automatically apply active scholarships to generated invoices'
    )
    
    auto_apply_discounts = forms.BooleanField(
        label='Auto-apply Eligible Discounts',
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text='Automatically apply eligible discounts to generated invoices'
    )
    
    # =========================================================================
    # EXCLUSION OPTIONS
    # =========================================================================
    
    skip_with_pending = forms.BooleanField(
        label='Skip Students with Pending Invoices',
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text='Skip students who have unpaid invoices for this session'
    )
    
    skip_with_enrollment_invoice = forms.BooleanField(
        label='Skip Students with Enrollment Invoice',
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text='Skip students whose enrollment already has an invoice linked'
    )
    
    # =========================================================================
    # PREVIEW/CONFIRMATION
    # =========================================================================
    
    preview_only = forms.BooleanField(
        label='Preview Only (Don\'t Create Yet)',
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text='Show what will be created without actually creating invoices'
    )
    
    confirm = forms.BooleanField(
        label='I confirm bulk invoice generation',
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text='Required when preview_only is unchecked'
    )
    
    # =========================================================================
    # INITIALIZATION
    # =========================================================================
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
            # ✅ FIX 1: Use correct field name 'order' instead of 'level_order'
            self.fields['academic_levels'].queryset = AcademicLevel.objects.filter(
                is_active=True
            ).order_by('order')  # ✅ Changed from 'level_order' to 'order'
            
            # ✅ FIX 2: Use correct field names for Class ordering
            self.fields['classes'].queryset = Class.objects.filter(
                is_active=True
            ).select_related('academic_level').order_by(
                'academic_level__order',  # ✅ Changed from 'academic_level__level_order'
                'section'
            )
            
            self.fields['academic_session'].queryset = AcademicSession.objects.filter(
                is_active=True
            ).order_by('-start_date')
            
            self.fields['fiscal_period'].queryset = FiscalPeriod.objects.filter(
                is_closed=False
            ).order_by('-start_date')
            
        except Exception as e:
            logger.error(f"Error setting querysets in BulkInvoiceGenerationForm: {e}")
        
        # Set default dates
        if not self.is_bound:
            from core.utils import get_school_today  # ✅ Import here
            from datetime import timedelta
            
            today = get_school_today()
            self.fields['issue_date'].initial = today
            self.fields['due_date'].initial = today + timedelta(days=30)
    
    # =========================================================================
    # VALIDATION
    # =========================================================================
    
    def clean(self):
        """Validate bulk generation parameters"""
        cleaned_data = super().clean()
        
        # Date validation
        issue_date = cleaned_data.get('issue_date')
        due_date = cleaned_data.get('due_date')
        
        if issue_date and due_date:
            if due_date < issue_date:
                raise ValidationError({
                    'due_date': 'Due date cannot be before issue date.'
                })
        
        # Target validation
        target_students = cleaned_data.get('target_students')
        
        if target_students == 'by_level' and not cleaned_data.get('academic_levels'):
            raise ValidationError({
                'academic_levels': 'Select at least one academic level.'
            })
        
        if target_students == 'by_class' and not cleaned_data.get('classes'):
            raise ValidationError({
                'classes': 'Select at least one class.'
            })
        
        if target_students == 'by_enrollment_type' and not cleaned_data.get('enrollment_types'):
            raise ValidationError({
                'enrollment_types': 'Select at least one enrollment type.'
            })
        
        if target_students == 'by_boarding' and not cleaned_data.get('boarding_types'):
            raise ValidationError({
                'boarding_types': 'Select at least one boarding type.'
            })
        
        # Confirmation validation
        preview_only = cleaned_data.get('preview_only', True)
        confirm = cleaned_data.get('confirm', False)
        
        if not preview_only and not confirm:
            raise ValidationError({
                'confirm': 'You must confirm before generating invoices.'
            })
        
        return cleaned_data
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def get_target_enrollments(self):
            """
            Get enrollments that match the filter criteria.
            
            Returns:
                QuerySet: Filtered StudentClassEnrollment objects
            """
            cleaned_data = self.cleaned_data
            academic_session = cleaned_data.get('academic_session')
            target_students = cleaned_data.get('target_students')
            
            if not academic_session:
                logger.error("No academic session provided")
                from academics.models import StudentClassEnrollment
                return StudentClassEnrollment.objects.none()
            
            # Base queryset: active enrollments for the session
            from academics.models import StudentClassEnrollment
            enrollments = StudentClassEnrollment.objects.filter(
                academic_session=academic_session,
                is_active=True,
                completion_status='ONGOING'
            ).select_related(
                'student',
                'class_instance',
                'class_instance__academic_level',
                'academic_invoice'
            )
            
            logger.info(f"Base enrollments for session {academic_session}: {enrollments.count()}")
            
            # Apply filters based on target
            if target_students == 'by_level':
                academic_levels = cleaned_data.get('academic_levels')
                if academic_levels:
                    enrollments = enrollments.filter(
                        class_instance__academic_level__in=academic_levels
                    )
                    logger.info(f"Filtered by levels {[str(l) for l in academic_levels]}: {enrollments.count()}")
                else:
                    logger.warning("by_level selected but no levels provided")
                    return StudentClassEnrollment.objects.none()
            
            elif target_students == 'by_class':
                classes = cleaned_data.get('classes')
                if classes:
                    enrollments = enrollments.filter(
                        class_instance__in=classes
                    )
                    logger.info(f"Filtered by classes {[str(c) for c in classes]}: {enrollments.count()}")
                else:
                    logger.warning("by_class selected but no classes provided")
                    return StudentClassEnrollment.objects.none()
            
            elif target_students == 'by_enrollment_type':
                enrollment_types = cleaned_data.get('enrollment_types')
                if enrollment_types:
                    enrollments = enrollments.filter(
                        enrollment_type__in=enrollment_types
                    )
                    logger.info(f"Filtered by enrollment types {enrollment_types}: {enrollments.count()}")
                else:
                    logger.warning("by_enrollment_type selected but no types provided")
                    return StudentClassEnrollment.objects.none()
            
            elif target_students == 'by_boarding':
                boarding_types = cleaned_data.get('boarding_types')
                if boarding_types:
                    # Check if student has active boarding enrollment with matching type
                    enrollments = enrollments.filter(
                        student__boarding_enrollments__academic_session=academic_session,
                        student__boarding_enrollments__status='ACTIVE',
                        student__boarding_enrollments__boarding_type__in=boarding_types
                    ).distinct()
                    logger.info(f"Filtered by boarding types {boarding_types}: {enrollments.count()}")
                else:
                    logger.warning("by_boarding selected but no boarding types provided")
                    return StudentClassEnrollment.objects.none()
            
            elif target_students == 'without_invoice':
                enrollments = enrollments.filter(academic_invoice__isnull=True)
                logger.info(f"Filtered without invoice: {enrollments.count()}")
            
            elif target_students == 'all_enrolled':
                logger.info(f"All enrolled students: {enrollments.count()}")
            
            # Apply exclusions (these apply to ALL target types)
            if cleaned_data.get('skip_with_enrollment_invoice'):
                before_count = enrollments.count()
                enrollments = enrollments.filter(academic_invoice__isnull=True)
                logger.info(f"Excluded with enrollment invoice: {before_count} -> {enrollments.count()}")
            
            if cleaned_data.get('skip_with_pending'):
                # Get students with pending invoices
                from fees.models import FeeInvoice
                students_with_pending = FeeInvoice.objects.filter(
                    academic_session=academic_session,
                    status__in=['PENDING', 'PARTIALLY_PAID', 'OVERDUE']
                ).values_list('student_id', flat=True)
                
                before_count = enrollments.count()
                enrollments = enrollments.exclude(student_id__in=students_with_pending)
                logger.info(f"Excluded with pending invoices: {before_count} -> {enrollments.count()}")
            
            logger.info(f"Final enrollment count: {enrollments.count()}")
            return enrollments
        
    def get_preview_data(self):
            """
            Generate preview data showing what will be created.
            
            Returns:
                dict: Preview information with proper dictionaries
            """
            enrollments = self.get_target_enrollments()
            
            from collections import defaultdict
            
            # Initialize counters as defaultdicts
            by_class_counter = defaultdict(int)
            by_level_counter = defaultdict(int)
            by_enrollment_type_counter = defaultdict(int)
            by_boarding_counter = defaultdict(int)
            
            logger.info(f"Generating preview data for {enrollments.count()} enrollments")
            
            # Count enrollments - ✅ FIXED: Iterate over queryset properly
            for enrollment in enrollments.iterator():
                # Group by class
                class_name = str(enrollment.class_instance)
                by_class_counter[class_name] += 1
                
                # Group by level
                level_name = str(enrollment.class_instance.academic_level)
                by_level_counter[level_name] += 1
                
                # Group by enrollment type
                type_display = enrollment.get_enrollment_type_display()
                by_enrollment_type_counter[type_display] += 1
                
                # Group by boarding (if available)
                try:
                    # Check if student has boarding enrollment for this session
                    boarding_enrollment = enrollment.student.boarding_enrollments.filter(
                        academic_session=enrollment.academic_session,
                        status='ACTIVE'
                    ).first()
                    
                    if boarding_enrollment:
                        boarding_type = boarding_enrollment.get_boarding_type_display()
                        by_boarding_counter[boarding_type] += 1
                    else:
                        by_boarding_counter['Day Scholar'] += 1
                except Exception as e:
                    logger.warning(f"Could not get boarding status for student {enrollment.student}: {e}")
                    by_boarding_counter['Unknown'] += 1
            
            # ✅ CRITICAL FIX: Convert defaultdicts to regular dicts and sort them
            # The template cannot iterate properly over defaultdict
            preview = {
                'total_enrollments': enrollments.count(),
                'by_class': dict(sorted(by_class_counter.items())),
                'by_level': dict(sorted(by_level_counter.items())),
                'by_enrollment_type': dict(sorted(by_enrollment_type_counter.items())),
                'by_boarding': dict(sorted(by_boarding_counter.items())),
                'enrollments': list(enrollments[:100]),  # ✅ Convert to list for template
            }
            
            logger.info(f"Preview data generated:")
            logger.info(f"  - Total: {preview['total_enrollments']}")
            logger.info(f"  - By class: {len(preview['by_class'])} classes")
            logger.info(f"  - By level: {len(preview['by_level'])} levels")
            logger.info(f"  - Classes: {list(preview['by_class'].keys())}")
            logger.info(f"  - Levels: {list(preview['by_level'].keys())}")
            
            return preview


# =============================================================================
# ADDITIONAL UTILITY FORMS
# =============================================================================

class PaymentVerificationForm(BootstrapFormMixin, forms.Form):
    """Form for verifying payments"""
    
    VERIFICATION_DECISION_CHOICES = [
        ('', '-- Select Decision --'),
        ('VERIFY', 'Verify Payment'),
        ('REJECT', 'Reject Payment'),
    ]
    
    decision = forms.ChoiceField(
        label='Verification Decision',
        choices=VERIFICATION_DECISION_CHOICES,
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    notes = forms.CharField(
        label='Verification Notes',
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'Enter verification notes...'
        })
    )
    
    def clean_decision(self):
        """Ensure a decision is selected"""
        decision = self.cleaned_data.get('decision')
        if not decision:
            raise ValidationError('Please select a verification decision.')
        return decision


class ScholarshipApplicationApprovalForm(RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.Form):
    """Form for approving/rejecting scholarship applications"""
    
    DECISION_CHOICES = [
        ('', '-- Select Decision --'),
        ('APPROVE', 'Approve Application'),
        ('REJECT', 'Reject Application'),
        ('WAITLIST', 'Add to Waitlist'),
    ]
    
    decision = forms.ChoiceField(
        label='Decision',
        choices=DECISION_CHOICES,
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    approved_amount = MoneyField(
        label='Approved Amount',
        required=False,
        help_text='Required if approving (can be different from requested amount)'
    )
    
    decision_reason = forms.CharField(
        label='Decision Notes',
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 4,
            'placeholder': 'Reason for this decision...'
        })
    )
    
    def clean(self):
        """Validate approval data"""
        cleaned_data = super().clean()
        
        decision = cleaned_data.get('decision')
        approved_amount = cleaned_data.get('approved_amount')
        
        if decision == 'APPROVE' and not approved_amount:
            raise ValidationError({
                'approved_amount': 'Approved amount is required when approving an application.'
            })
        
        return cleaned_data


class InvoiceVoidForm(RequiredFieldsMixin, BootstrapFormMixin, forms.Form):
    """Form for voiding/cancelling invoices"""
    
    ACTION_CHOICES = [
        ('', '-- Select Action --'),
        ('VOID', 'Void Invoice'),
        ('CANCEL', 'Cancel Invoice'),
    ]
    
    action = forms.ChoiceField(
        label='Action',
        choices=ACTION_CHOICES,
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Void = never valid, Cancel = was valid but now cancelled'
    )
    
    reason = forms.CharField(
        label='Reason',
        required=True,
        widget=forms.Textarea(attrs={
            'rows': 4,
            'placeholder': 'Detailed reason for voiding/cancelling this invoice...'
        })
    )
    
    confirm = forms.BooleanField(
        label='I confirm this action',
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text='This action cannot be easily undone'
    )
    
    def clean_action(self):
        """Ensure an action is selected"""
        action = self.cleaned_data.get('action')
        if not action:
            raise ValidationError('Please select an action.')
        return action


class AccountTransactionFilterForm(DateRangeFormMixin, BootstrapFormMixin, forms.Form):
    """Filter form for account transaction search"""
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by student name, reference...'
        })
    )
    
    student = forms.ModelChoiceField(
        label='Student',
        queryset=None,
        required=False,
        empty_label="All Students",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    transaction_type = forms.ChoiceField(
        label='Transaction Type',
        choices=[('', 'All Types')] + list(AccountTransaction.TRANSACTION_TYPES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    date_from = forms.DateField(
        label='From Date',
        required=False,
        widget=DatePickerInput()
    )
    
    date_to = forms.DateField(
        label='To Date',
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
            self.fields['student'].queryset = Student.objects.filter(
                enrollment_status='ACTIVE'
            ).order_by('first_name', 'last_name')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")


class ScholarshipApplicationLogFilterForm(DateRangeFormMixin, BootstrapFormMixin, forms.Form):
    """Filter form for scholarship application log search"""
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by student name...'
        })
    )
    
    scholarship = forms.ModelChoiceField(
        label='Scholarship',
        queryset=None,
        required=False,
        empty_label="All Scholarships",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    is_reversed = forms.NullBooleanField(
        label='Status',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('false', 'Active'),
            ('true', 'Reversed')
        ], attrs={'class': 'form-select'})
    )
    
    application_date_from = forms.DateField(
        label='Applied From',
        required=False,
        widget=DatePickerInput()
    )
    
    application_date_to = forms.DateField(
        label='Applied To',
        required=False,
        widget=DatePickerInput()
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
            self.fields['scholarship'].queryset = StudentScholarship.objects.filter(
                status='ACTIVE'
            ).select_related('scholarship_program').order_by('scholarship_program__name')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")

# =============================================================================
# BAD DEBT WRITE-OFF FORM
# =============================================================================

class BadDebtWriteOffForm(RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """
    Form for creating bad debt write-offs.
    
    Features:
    - Invoice selection with balance validation
    - Accounting method choice (direct vs allowance)
    - Required approval documentation
    - Fiscal period tracking
    """
    
    class Meta:
        model = BadDebtWriteOff
        fields = [
            'invoice',
            'write_off_amount',
            'write_off_date',
            'fiscal_period',
            'use_allowance_method',
            'reason',
        ]
        widgets = {
            'invoice': forms.Select(attrs={
                'class': 'form-select',
                'data-placeholder': 'Select invoice...',
                'id': 'id_invoice'
            }),
            'write_off_amount': MoneyInput(attrs={
                'id': 'id_write_off_amount',
                'placeholder': '0.00'
            }),
            'write_off_date': DatePickerInput(),
            'fiscal_period': forms.Select(attrs={'class': 'form-select'}),
            'use_allowance_method': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'reason': forms.Textarea(attrs={
                'rows': 5,
                'placeholder': '''Provide detailed justification for write-off:
- Collection efforts made (calls, letters, meetings)
- Student/parent circumstances
- Reason invoice is uncollectible
- Any other relevant information
'''
            }),
        }
        help_texts = {
            'invoice': 'Select the invoice to write off (only invoices with outstanding balance shown)',
            'write_off_amount': 'Amount to write off (cannot exceed outstanding balance)',
            'use_allowance_method': 'Check if using allowance method (if you previously set up an allowance for doubtful accounts). Leave unchecked for direct write-off.',
            'reason': 'Required: Document why this debt is being written off (for audit trail)',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Only show invoices with outstanding balance
        try:
            self.fields['invoice'].queryset = FeeInvoice.objects.filter(
                balance__gt=0,
                status__in=['PENDING', 'PARTIALLY_PAID', 'OVERDUE']
            ).select_related('student', 'academic_session').order_by('-issue_date')
            
            # Custom label to show student name, invoice number, and balance
            self.fields['invoice'].label_from_instance = lambda obj: (
                f"{obj.invoice_number} - {obj.student.get_full_name()} - "
                f"Balance: UGX {obj.balance:,.2f}"
            )
        except Exception as e:
            logger.error(f"Error setting invoice queryset: {e}")
        
        # Only show open fiscal periods
        try:
            self.fields['fiscal_period'].queryset = FiscalPeriod.objects.filter(
                status__in=['OPEN', 'CURRENT']
            ).order_by('-start_date')
        except Exception as e:
            logger.error(f"Error setting fiscal period queryset: {e}")
        
        # Set default date and fiscal period
        if not self.is_bound:
            today = get_school_today()
            self.fields['write_off_date'].initial = today
            
            try:
                current_period = FiscalPeriod.get_current_fiscal_period()
                if current_period:
                    self.fields['fiscal_period'].initial = current_period
            except Exception as e:
                logger.error(f"Error getting current fiscal period: {e}")
        
        # Add help text about accounting methods
        self.fields['use_allowance_method'].help_text = (
            "<strong>Accounting Method:</strong><br>"
            "<strong>Unchecked (Direct Write-Off):</strong> DR: Bad Debt Expense, CR: Accounts Receivable<br>"
            "<strong>Checked (Allowance Method):</strong> DR: Allowance for Doubtful Accounts, CR: Accounts Receivable<br>"
            "<small class='text-muted'>Use allowance method only if you previously estimated bad debts.</small>"
        )
    
    def clean_write_off_amount(self):
        """Validate write-off amount"""
        amount = self.cleaned_data.get('write_off_amount')
        
        if amount <= 0:
            raise ValidationError("Write-off amount must be greater than zero.")
        
        return amount
    
    def clean_reason(self):
        """Validate reason has sufficient detail"""
        reason = self.cleaned_data.get('reason', '').strip()
        
        if not reason:
            raise ValidationError("Reason for write-off is required.")
        
        if len(reason) < 50:
            raise ValidationError(
                "Please provide a detailed reason (at least 50 characters). "
                "Include collection efforts made and why the debt is uncollectible."
            )
        
        return reason
    
    def clean(self):
        """Validate write-off data"""
        cleaned_data = super().clean()
        
        invoice = cleaned_data.get('invoice')
        write_off_amount = cleaned_data.get('write_off_amount')
        write_off_date = cleaned_data.get('write_off_date')
        fiscal_period = cleaned_data.get('fiscal_period')
        
        # Validate write-off amount doesn't exceed invoice balance
        if invoice and write_off_amount:
            if write_off_amount > invoice.balance:
                raise ValidationError({
                    'write_off_amount': (
                        f"Write-off amount (UGX {write_off_amount:,.2f}) cannot exceed "
                        f"invoice balance (UGX {invoice.balance:,.2f})."
                    )
                })
        
        # Validate write-off date is within fiscal period
        if write_off_date and fiscal_period:
            if write_off_date < fiscal_period.start_date:
                raise ValidationError({
                    'write_off_date': (
                        f"Write-off date cannot be before fiscal period start date "
                        f"({fiscal_period.start_date})."
                    )
                })
            
            if write_off_date > fiscal_period.end_date:
                raise ValidationError({
                    'write_off_date': (
                        f"Write-off date cannot be after fiscal period end date "
                        f"({fiscal_period.end_date})."
                    )
                })
        
        # Validate fiscal period is not closed
        if fiscal_period and fiscal_period.status == 'CLOSED':
            raise ValidationError({
                'fiscal_period': (
                    "Cannot write off bad debt in a closed fiscal period. "
                    "Please select an open period."
                )
            })
        
        # Validate write-off date is not in the future
        if write_off_date:
            today = get_school_today()
            if write_off_date > today:
                raise ValidationError({
                    'write_off_date': "Write-off date cannot be in the future."
                })
        
        return cleaned_data


# =============================================================================
# BAD DEBT WRITE-OFF FILTER FORM
# =============================================================================

class BadDebtWriteOffFilterForm(DateRangeFormMixin, BootstrapFormMixin, forms.Form):
    """
    Filter form for bad debt write-off search and reporting.
    
    Features:
    - Search by invoice number or student name
    - Filter by date range
    - Filter by fiscal period or academic session
    - Filter by accounting method
    - Filter by approval status
    - Amount range filters
    """
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by invoice number, student name...'
        })
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
    
    write_off_date_from = forms.DateField(
        label='Write-Off Date From',
        required=False,
        widget=DatePickerInput()
    )
    
    write_off_date_to = forms.DateField(
        label='Write-Off Date To',
        required=False,
        widget=DatePickerInput()
    )
    
    accounting_method = forms.ChoiceField(
        label='Accounting Method',
        choices=[
            ('', 'All Methods'),
            ('direct', 'Direct Write-Off'),
            ('allowance', 'Allowance Method'),
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    min_amount = forms.DecimalField(
        label='Min Amount',
        required=False,
        decimal_places=2,
        widget=MoneyInput(attrs={'placeholder': 'Min amount...'})
    )
    
    max_amount = forms.DecimalField(
        label='Max Amount',
        required=False,
        decimal_places=2,
        widget=MoneyInput(attrs={'placeholder': 'Max amount...'})
    )
    
    has_approval = forms.NullBooleanField(
        label='Approval Status',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Approved'),
            ('false', 'Pending Approval')
        ], attrs={'class': 'form-select'})
    )
    
    has_journal_entry = forms.NullBooleanField(
        label='Journal Entry Status',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'With Journal Entry'),
            ('false', 'Missing Journal Entry')
        ], attrs={'class': 'form-select'})
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
            # All sessions (including inactive, for historical reporting)
            self.fields['academic_session'].queryset = AcademicSession.objects.all().order_by('-start_date')
            
            # All fiscal periods
            self.fields['fiscal_period'].queryset = FiscalPeriod.objects.all().order_by('-start_date')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")


# =============================================================================
# QUICK BAD DEBT WRITE-OFF FORM (For Single Invoice)
# =============================================================================

class QuickBadDebtWriteOffForm(RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """
    Simplified form for writing off a specific invoice.
    
    Used when accessing write-off from invoice detail page.
    Invoice is pre-selected and hidden from form.
    """
    
    class Meta:
        model = BadDebtWriteOff
        fields = [
            'write_off_amount',
            'write_off_date',
            'fiscal_period',
            'use_allowance_method',
            'reason',
        ]
        widgets = {
            'write_off_amount': MoneyInput(attrs={
                'placeholder': '0.00',
                'class': 'form-control-lg'
            }),
            'write_off_date': DatePickerInput(),
            'fiscal_period': forms.Select(attrs={'class': 'form-select'}),
            'use_allowance_method': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'reason': forms.Textarea(attrs={
                'rows': 6,
                'placeholder': '''Document collection efforts and reason for write-off:

1. Collection efforts made:
   - Date and method of contact attempts
   - Response from student/parents

2. Student/family circumstances:
   - Financial hardship details
   - Student status (withdrawn, etc.)

3. Conclusion:
   - Why debt is uncollectible
   - Recommendation for write-off
'''
            }),
        }
    
    def __init__(self, *args, invoice=None, **kwargs):
        """
        Initialize form with pre-selected invoice.
        
        Args:
            invoice: FeeInvoice instance to write off
        """
        self.invoice = invoice
        super().__init__(*args, **kwargs)
        
        if self.invoice:
            # Pre-fill write-off amount with full invoice balance
            self.fields['write_off_amount'].initial = self.invoice.balance
            
            # Add invoice info to help text
            self.fields['write_off_amount'].help_text = (
                f"<strong>Invoice:</strong> {self.invoice.invoice_number}<br>"
                f"<strong>Student:</strong> {self.invoice.student.get_full_name()}<br>"
                f"<strong>Total Amount:</strong> UGX {self.invoice.total_amount:,.2f}<br>"
                f"<strong>Paid Amount:</strong> UGX {self.invoice.paid_amount:,.2f}<br>"
                f"<strong>Outstanding Balance:</strong> UGX {self.invoice.balance:,.2f}"
            )
        
        # Only show open fiscal periods
        try:
            self.fields['fiscal_period'].queryset = FiscalPeriod.objects.filter(
                status__in=['OPEN', 'CURRENT']
            ).order_by('-start_date')
        except Exception as e:
            logger.error(f"Error setting fiscal period queryset: {e}")
        
        # Set defaults
        if not self.is_bound:
            today = get_school_today()
            self.fields['write_off_date'].initial = today
            
            try:
                current_period = FiscalPeriod.get_current_fiscal_period()
                if current_period:
                    self.fields['fiscal_period'].initial = current_period
            except Exception as e:
                logger.error(f"Error getting current fiscal period: {e}")
    
    def clean_write_off_amount(self):
        """Validate write-off amount against invoice balance"""
        amount = self.cleaned_data.get('write_off_amount')
        
        if amount <= 0:
            raise ValidationError("Write-off amount must be greater than zero.")
        
        if self.invoice and amount > self.invoice.balance:
            raise ValidationError(
                f"Write-off amount (UGX {amount:,.2f}) cannot exceed "
                f"invoice balance (UGX {self.invoice.balance:,.2f})."
            )
        
        return amount
    
    def clean_reason(self):
        """Validate reason has sufficient detail"""
        reason = self.cleaned_data.get('reason', '').strip()
        
        if not reason:
            raise ValidationError("Reason for write-off is required.")
        
        if len(reason) < 100:
            raise ValidationError(
                "Please provide a comprehensive reason (at least 100 characters). "
                "Document collection efforts, student circumstances, and why the debt is uncollectible."
            )
        
        return reason
    
    def save(self, commit=True):
        """Save with pre-selected invoice"""
        instance = super().save(commit=False)
        
        if self.invoice:
            instance.invoice = self.invoice
        
        if commit:
            instance.save()
        
        return instance


# =============================================================================
# APPROVAL FORM
# =============================================================================

class BadDebtApprovalForm(BootstrapFormMixin, forms.Form):
    """
    Form for approving/rejecting bad debt write-offs.
    
    Used by finance managers to approve write-off requests.
    """
    
    action = forms.ChoiceField(
        label='Decision',
        choices=[
            ('approve', 'Approve Write-Off'),
            ('reject', 'Reject Write-Off'),
        ],
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'})
    )
    
    notes = forms.CharField(
        label='Approval/Rejection Notes',
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 4,
            'placeholder': 'Optional notes about this decision...',
            'class': 'form-control'
        }),
        help_text='Optional notes about why you approved or rejected this write-off'
    )
    
    def clean(self):
        """Require notes if rejecting"""
        cleaned_data = super().clean()
        action = cleaned_data.get('action')
        notes = cleaned_data.get('notes', '').strip()
        
        if action == 'reject' and not notes:
            raise ValidationError({
                'notes': 'Please provide a reason for rejecting this write-off.'
            })
        
        return cleaned_data