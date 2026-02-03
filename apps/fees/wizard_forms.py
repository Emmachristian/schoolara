# fees/wizard_forms.py - COMPLETE WIZARD FORM CLASSES

"""
Fee Structure Wizard Forms

Complete form classes for the multi-step fee structure creation wizard.
Each form represents one step in the wizard process.
"""

from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory, BaseInlineFormSet
from decimal import Decimal
import logging

from .models import (
    FeesStructure,
    FeesStructureBillingSplit,
    FeesStructureItem,
    FeesCategory,
)
from core.models import FiscalYear, FiscalPeriod
from academics.models import AcademicSession, AcademicLevel, Class

logger = logging.getLogger(__name__)


# =============================================================================
# STEP 1: BASIC STRUCTURE INFORMATION
# =============================================================================

class FeesStructureBasicForm(forms.ModelForm):
    """
    Step 1: Basic fee structure information and academic coverage.
    
    This form captures:
    - Structure name and type
    - Academic year and sessions (WHAT coverage)
    - Academic levels and classes
    - Student filters (boarding, enrollment type)
    - Billing frequency (determines if Step 2 formset is shown)
    - Payment terms and late fees
    """
    
    class Meta:
        model = FeesStructure
        fields = [
            # Basic Information
            'name',
            'description',
            'structure_type',
            
            # Academic Coverage (WHAT)
            'academic_year',
            'applicable_sessions',
            'academic_levels',
            'applicable_classes',
            
            # Billing Configuration (WHEN)
            'billing_frequency',  # KEY: Controls Step 2 visibility
            
            # Student Filters
            'boarding_type_filter',
            'student_type_filter',
            
            # Payment Terms
            'payment_terms_days',
            'charges_late_fee',
            'late_fee_amount',
            'late_fee_percentage',
            'grace_period_days',
            
            # Priority & Status
            'priority',
            'is_active',
            'effective_date',
            'expiry_date',
        ]
        
        widgets = {
            # Text inputs
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Form 1 Day Scholar - Term 1 2024'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Description of this fee structure...'
            }),
            
            # Single selects
            'structure_type': forms.Select(attrs={'class': 'form-select'}),
            'academic_year': forms.Select(attrs={'class': 'form-select'}),
            'billing_frequency': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_billing_frequency'  # For JavaScript conditional logic
            }),
            'boarding_type_filter': forms.Select(attrs={'class': 'form-select'}),
            'student_type_filter': forms.Select(attrs={'class': 'form-select'}),
            
            # Multi-selects
            'applicable_sessions': forms.SelectMultiple(attrs={
                'class': 'form-select',
                'size': '5',
                'id': 'id_applicable_sessions'
            }),
            'academic_levels': forms.SelectMultiple(attrs={
                'class': 'form-select',
                'size': '5'
            }),
            'applicable_classes': forms.SelectMultiple(attrs={
                'class': 'form-select',
                'size': '5'
            }),
            
            # Number inputs
            'payment_terms_days': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'value': '30'
            }),
            'grace_period_days': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'value': '7'
            }),
            'priority': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'value': '100'
            }),
            
            # Money inputs
            'late_fee_amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'step': '0.01',
                'placeholder': '0.00'
            }),
            'late_fee_percentage': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'max': '100',
                'step': '0.01',
                'placeholder': '0.00'
            }),
            
            # Date inputs
            'effective_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
            'expiry_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
            
            # Checkboxes
            'charges_late_fee': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'id': 'id_charges_late_fee'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # =====================================================================
        # SET QUERYSETS
        # =====================================================================
        
        # Academic Year
        self.fields['academic_year'].queryset = FiscalYear.objects.all().order_by('-start_date')
        
        # Academic Sessions
        self.fields['applicable_sessions'].queryset = AcademicSession.objects.filter(
            is_active=True
        ).order_by('-start_date')
        
        # Academic Levels
        self.fields['academic_levels'].queryset = AcademicLevel.objects.filter(
            is_active=True
        ).order_by('order')
        
        # Classes
        self.fields['applicable_classes'].queryset = Class.objects.filter(
            is_active=True
        ).select_related('academic_level', 'academic_session').order_by(
            '-academic_session__start_date',  # Session first
            'academic_level__order',          # Then level
            'section'                         # Then section
        )
        
        # =====================================================================
        # SET DEFAULTS
        # =====================================================================
        
        if not self.is_bound and not self.instance.pk:
            from core.utils import get_school_today
            
            # Default effective date to today
            self.fields['effective_date'].initial = get_school_today()
            
            # Default to current academic year
            current_year = FiscalYear.get_active_fiscal_year()
            if current_year:
                self.fields['academic_year'].initial = current_year
            
            # Default billing frequency
            self.fields['billing_frequency'].initial = 'ONCE'
        
        # =====================================================================
        # SET HELP TEXT
        # =====================================================================
        
        self.fields['name'].help_text = (
            'Descriptive name for this fee structure'
        )
        
        self.fields['academic_year'].help_text = (
            'Academic/Fiscal year this structure belongs to'
        )
        
        self.fields['applicable_sessions'].help_text = (
            'Which academic sessions this fee structure covers. '
            'Can select multiple sessions for annual structures.'
        )
        
        self.fields['academic_levels'].help_text = (
            'Academic levels this structure applies to (e.g., Form 1, Form 2)'
        )
        
        self.fields['applicable_classes'].help_text = (
            'Leave empty to apply to ALL classes in selected levels/sessions. '
            'If specified, must belong to the selected sessions.'
        )
        
        self.fields['billing_frequency'].help_text = (
            'ONCE: Bill full amount in first period | '
            'PER_PERIOD: Bill equally across all periods | '
            'SPLIT_CUSTOM: Custom percentage splits (configure in next step) | '
            'ON_ENROLLMENT: Bill when student enrolls'
        )
        
        self.fields['payment_terms_days'].help_text = (
            'Number of days from invoice date for payment due date'
        )
        
        self.fields['priority'].help_text = (
            'Lower number = higher priority when multiple structures match a student'
        )
        
        # =====================================================================
        # SET REQUIRED FIELDS
        # =====================================================================
        
        required_fields = [
            'name',
            'structure_type',
            'academic_year',
            'applicable_sessions',
            'academic_levels',
            'billing_frequency',
            'payment_terms_days',
            'effective_date',
        ]
        
        for field_name in required_fields:
            if field_name in self.fields:
                self.fields[field_name].required = True
    
    def clean_name(self):
        """Clean and validate structure name"""
        name = self.cleaned_data.get('name')
        if name:
            name = ' '.join(name.strip().split())  # Normalize whitespace
            
            # Check for duplicate names (case-insensitive)
            exists = FeesStructure.objects.filter(
                name__iexact=name
            ).exclude(pk=self.instance.pk if self.instance else None).exists()
            
            if exists:
                raise ValidationError(
                    f'A fee structure with the name "{name}" already exists. '
                    'Please choose a different name.'
                )
        
        return name
    
    def clean(self):
        """Comprehensive validation"""
        cleaned_data = super().clean()
        
        # =====================================================================
        # DATE VALIDATION
        # =====================================================================
        
        effective_date = cleaned_data.get('effective_date')
        expiry_date = cleaned_data.get('expiry_date')
        
        if effective_date and expiry_date:
            if expiry_date <= effective_date:
                self.add_error('expiry_date',
                    'Expiry date must be after effective date.'
                )
        
        # =====================================================================
        # ACADEMIC YEAR VALIDATION
        # =====================================================================
        
        academic_year = cleaned_data.get('academic_year')
        applicable_sessions = cleaned_data.get('applicable_sessions')
        
        if academic_year and applicable_sessions:
            # Check that sessions belong to the selected year
            session_years = set()
            for session in applicable_sessions:
                session_years.add(session.year_name)
            
            if len(session_years) > 1:
                self.add_error('applicable_sessions',
                    f'Selected sessions span multiple years: {", ".join(session_years)}. '
                    f'Please select sessions from {academic_year.name} only.'
                )
        
        # =====================================================================
        # SESSION VALIDATION
        # =====================================================================
        
        if not applicable_sessions:
            self.add_error('applicable_sessions',
                'At least one academic session must be selected.'
            )
        
        # =====================================================================
        # LEVEL VALIDATION
        # =====================================================================
        
        academic_levels = cleaned_data.get('academic_levels')
        if not academic_levels:
            self.add_error('academic_levels',
                'At least one academic level must be selected.'
            )
        
        # =====================================================================
        # CLASS VALIDATION
        # =====================================================================
        
        applicable_classes = cleaned_data.get('applicable_classes')
        
        if applicable_classes and applicable_sessions:
            # Get sessions from selected classes
            class_sessions = set(
                cls.academic_session.id for cls in applicable_classes
            )
            selected_sessions = set(
                session.id for session in applicable_sessions
            )
            
            # Check if classes belong to selected sessions
            mismatched = class_sessions - selected_sessions
            if mismatched:
                mismatched_sessions = AcademicSession.objects.filter(
                    id__in=mismatched
                )
                self.add_error('applicable_classes',
                    f'Some selected classes belong to sessions not in "Applicable Sessions": '
                    f'{", ".join(str(s) for s in mismatched_sessions)}. '
                    f'Please select only classes from the chosen sessions.'
                )
        
        # =====================================================================
        # LATE FEE VALIDATION
        # =====================================================================
        
        charges_late_fee = cleaned_data.get('charges_late_fee', False)
        late_fee_amount = cleaned_data.get('late_fee_amount') or Decimal('0.00')
        late_fee_percentage = cleaned_data.get('late_fee_percentage') or Decimal('0.00')
        
        if charges_late_fee:
            if late_fee_amount == 0 and late_fee_percentage == 0:
                self.add_error('charges_late_fee',
                    'Either late fee amount or percentage must be specified '
                    'when charging late fees.'
                )
        
        return cleaned_data


# =============================================================================
# STEP 2: BILLING SCHEDULE (CONDITIONAL - ONLY FOR SPLIT_CUSTOM)
# =============================================================================

class BillingScheduleSplitForm(forms.ModelForm):
    """
    Individual form for one billing split.
    Used in BillingScheduleFormSet.
    """
    
    class Meta:
        model = FeesStructureBillingSplit
        fields = ['fiscal_period', 'percentage', 'sequence', 'description']
        widgets = {
            'fiscal_period': forms.Select(attrs={
                'class': 'form-select'
            }),
            'percentage': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0.01',
                'max': '100.00',
                'step': '0.01',
                'placeholder': 'e.g., 33.33'
            }),
            'sequence': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'placeholder': '1'
            }),
            'description': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., First Installment'
            })
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set help text
        self.fields['fiscal_period'].help_text = (
            'Which fiscal period to bill in'
        )
        self.fields['percentage'].help_text = (
            'Percentage of total fee to bill in this period'
        )
        self.fields['sequence'].help_text = (
            'Billing order (1 = first, 2 = second, etc.)'
        )
        self.fields['description'].help_text = (
            'Optional description for this installment'
        )
    
    def clean_percentage(self):
        """Validate percentage range"""
        percentage = self.cleaned_data.get('percentage')
        
        if percentage and (percentage <= 0 or percentage > 100):
            raise ValidationError(
                'Percentage must be between 0.01 and 100.00'
            )
        
        return percentage


class BaseBillingScheduleFormSet(BaseInlineFormSet):
    """
    Custom formset for billing schedule splits.
    
    Features:
    - Filters fiscal periods by academic year from Step 1
    - Validates total percentages = 100%
    - Prevents duplicate fiscal periods
    """
    
    def __init__(self, *args, **kwargs):
        # Get academic year from Step 1 to filter fiscal periods
        self.academic_year = kwargs.pop('academic_year', None)
        super().__init__(*args, **kwargs)
        
        # Filter fiscal periods for all forms
        if self.academic_year:
            for form in self.forms:
                form.fields['fiscal_period'].queryset = FiscalPeriod.objects.filter(
                    fiscal_year=self.academic_year,
                    is_active=True,
                    is_closed=False
                ).order_by('period_number')
        else:
            # Show all active periods if no year specified
            for form in self.forms:
                form.fields['fiscal_period'].queryset = FiscalPeriod.objects.filter(
                    is_active=True,
                    is_closed=False
                ).select_related('fiscal_year').order_by(
                    'fiscal_year__start_date', 'period_number'
                )
    
    def clean(self):
        """
        Validate the entire formset.
        
        Checks:
        1. Total percentages = 100%
        2. No duplicate fiscal periods
        3. At least one split if formset is shown
        """
        if any(self.errors):
            return
        
        total_percentage = Decimal('0.00')
        fiscal_periods = []
        valid_forms = 0
        
        for form in self.forms:
            if form.cleaned_data and not form.cleaned_data.get('DELETE', False):
                valid_forms += 1
                
                # Add to total percentage
                percentage = form.cleaned_data.get('percentage', Decimal('0.00'))
                total_percentage += percentage
                
                # Check for duplicate fiscal periods
                fiscal_period = form.cleaned_data.get('fiscal_period')
                if fiscal_period:
                    if fiscal_period in fiscal_periods:
                        raise ValidationError(
                            f'Fiscal period "{fiscal_period}" is selected multiple times. '
                            'Each period can only be used once.'
                        )
                    fiscal_periods.append(fiscal_period)
        
        # Validate at least one split
        if valid_forms == 0:
            raise ValidationError(
                'At least one billing split is required for custom billing frequency.'
            )
        
        # Validate total percentage
        if total_percentage != Decimal('100.00'):
            raise ValidationError(
                f'Billing split percentages must total exactly 100%. '
                f'Current total: {total_percentage}%'
            )


# Create the formset
BillingScheduleFormSet = inlineformset_factory(
    FeesStructure,
    FeesStructureBillingSplit,
    form=BillingScheduleSplitForm,
    formset=BaseBillingScheduleFormSet,
    extra=3,  # Show 3 empty forms initially
    can_delete=True,
    min_num=1,  # At least 1 required
    validate_min=True,
    max_num=12,  # Maximum 12 billing periods
)


# =============================================================================
# STEP 3: FEE ITEMS
# =============================================================================

class FeeItemForm(forms.ModelForm):
    """
    Individual form for one fee item.
    Used in FeeItemFormSet.
    """
    
    class Meta:
        model = FeesStructureItem
        fields = [
            'fee_category',
            'amount',
            'use_variable_amount',
            'is_taxable',
            'tax_percentage',
            'default_discount_percentage',
            'scholarship_eligible',
            'max_scholarship_discount',
            'is_mandatory',
            'is_conditional',
            'print_on_invoice',
            'display_order',
        ]
        widgets = {
            'fee_category': forms.Select(attrs={
                'class': 'form-select'
            }),
            'amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'step': '0.01',
                'placeholder': '0.00'
            }),
            'tax_percentage': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'max': '100',
                'step': '0.01',
                'placeholder': '0.00'
            }),
            'default_discount_percentage': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'max': '100',
                'step': '0.01',
                'placeholder': '0.00'
            }),
            'max_scholarship_discount': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'max': '100',
                'step': '0.01',
                'placeholder': '100.00'
            }),
            'display_order': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'placeholder': '1'
            }),
            
            # Checkboxes
            'use_variable_amount': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'is_taxable': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'scholarship_eligible': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'is_mandatory': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'is_conditional': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'print_on_invoice': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set fee category queryset
        self.fields['fee_category'].queryset = FeesCategory.objects.filter(
            is_active=True
        ).select_related('display_group').order_by(
            'display_group__display_order', 'display_order'
        )
        
        # Set help text
        self.fields['amount'].help_text = 'Base amount for this fee item'
        
        self.fields['use_variable_amount'].help_text = (
            'Amount varies based on student attributes '
            '(configure variable_amount_rules separately after creation)'
        )
        
        self.fields['is_taxable'].help_text = 'Apply tax to this item'
        
        self.fields['tax_percentage'].help_text = (
            'Tax rate for this item (only applies if taxable)'
        )
        
        self.fields['scholarship_eligible'].help_text = (
            'Can scholarship discounts be applied to this item?'
        )
        
        self.fields['max_scholarship_discount'].help_text = (
            'Maximum scholarship discount percentage (leave blank for no limit)'
        )
        
        self.fields['is_mandatory'].help_text = (
            'Must be included on invoice (cannot be opted out)'
        )
        
        self.fields['is_conditional'].help_text = (
            'Only include if certain conditions are met '
            '(configure condition_criteria separately after creation)'
        )
        
        self.fields['print_on_invoice'].help_text = (
            'Include this item on printed invoices'
        )
        
        self.fields['display_order'].help_text = (
            'Order on invoice (lower numbers appear first)'
        )
        
        # Set defaults for new forms
        if not self.instance.pk:
            self.fields['is_mandatory'].initial = True
            self.fields['scholarship_eligible'].initial = True
            self.fields['print_on_invoice'].initial = True
            self.fields['display_order'].initial = 1
    
    def clean(self):
        """Validate fee item data"""
        cleaned_data = super().clean()
        
        # =====================================================================
        # SCHOLARSHIP VALIDATION
        # =====================================================================
        
        scholarship_eligible = cleaned_data.get('scholarship_eligible', False)
        max_scholarship_discount = cleaned_data.get('max_scholarship_discount')
        
        if not scholarship_eligible and max_scholarship_discount:
            self.add_error('max_scholarship_discount',
                'Cannot set max scholarship discount if item is not scholarship eligible.'
            )
        
        # =====================================================================
        # TAX VALIDATION
        # =====================================================================
        
        is_taxable = cleaned_data.get('is_taxable', False)
        tax_percentage = cleaned_data.get('tax_percentage') or Decimal('0.00')
        
        if is_taxable and tax_percentage == 0:
            self.add_error('tax_percentage',
                'Tax percentage must be greater than 0 if item is taxable.'
            )
        
        if not is_taxable and tax_percentage > 0:
            # Auto-set is_taxable if percentage is provided
            cleaned_data['is_taxable'] = True
        
        return cleaned_data


class BaseFeeItemFormSet(BaseInlineFormSet):
    """
    Custom formset for fee structure items.
    
    Features:
    - Validates at least one item
    - Prevents duplicate fee categories
    - Auto-assigns display order
    """
    
    def clean(self):
        """Validate the entire formset"""
        if any(self.errors):
            return
        
        fee_categories = []
        valid_forms = 0
        
        for form in self.forms:
            if form.cleaned_data and not form.cleaned_data.get('DELETE', False):
                valid_forms += 1
                
                # Check for duplicate fee categories
                fee_category = form.cleaned_data.get('fee_category')
                if fee_category:
                    if fee_category in fee_categories:
                        raise ValidationError(
                            f'Fee category "{fee_category}" is selected multiple times. '
                            'Each category can only be used once per structure.'
                        )
                    fee_categories.append(fee_category)
        
        # Validate at least one item
        if valid_forms == 0:
            raise ValidationError(
                'At least one fee item is required for a fee structure.'
            )


# Create the formset
FeeItemFormSet = inlineformset_factory(
    FeesStructure,
    FeesStructureItem,
    form=FeeItemForm,
    formset=BaseFeeItemFormSet,
    extra=5,  # Show 5 empty forms initially
    can_delete=True,
    min_num=1,  # At least 1 fee item required
    validate_min=True,
    max_num=50,  # Maximum 50 fee items
)


# =============================================================================
# STEP 4: CONFIRMATION
# =============================================================================

class StructureConfirmationForm(forms.Form):
    """
    Step 4: Final confirmation before creating fee structure.
    
    Simple form with:
    - Confirmation checkbox (required)
    - Optional notes field
    """
    
    confirm_creation = forms.BooleanField(
        required=True,
        label="I confirm that all information is correct",
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
            'id': 'id_confirm_creation'
        }),
        help_text="You must confirm before creating the fee structure"
    )
    
    notes = forms.CharField(
        required=False,
        label="Additional Notes",
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 4,
            'placeholder': 'Optional notes for record keeping...'
        }),
        help_text="Optional notes about this fee structure"
    )


# =============================================================================
# WIZARD CONFIGURATION
# =============================================================================

FEE_STRUCTURE_WIZARD_FORMS = [
    ("basic_info", FeesStructureBasicForm),
    ("billing_schedule", BillingScheduleFormSet),
    ("fee_items", FeeItemFormSet),
    ("confirmation", StructureConfirmationForm),
]

FEE_STRUCTURE_STEP_NAMES = {
    'basic_info': 'Basic Structure Information',
    'billing_schedule': 'Billing Schedule',
    'fee_items': 'Fee Items',
    'confirmation': 'Review & Confirmation'
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def validate_billing_splits_total(formset):
    """
    Standalone validation function for billing splits.
    
    Can be used outside of formset validation if needed.
    
    Args:
        formset: BillingScheduleFormSet instance
    
    Returns:
        str or None: Error message if validation fails, None if valid
    
    Example:
        error = validate_billing_splits_total(billing_formset)
        if error:
            messages.error(request, error)
    """
    total_percentage = Decimal('0.00')
    
    for form in formset:
        if form.cleaned_data and not form.cleaned_data.get('DELETE', False):
            percentage = form.cleaned_data.get('percentage', Decimal('0.00'))
            total_percentage += percentage
    
    if total_percentage != Decimal('100.00'):
        return (
            f'Billing split percentages must total 100%. '
            f'Current total: {total_percentage}%'
        )
    
    return None  # Valid


def get_fee_structure_summary(basic_data, billing_data, items_data):
    """
    Generate summary dict for confirmation step.
    
    Args:
        basic_data: Cleaned data from Step 1
        billing_data: Cleaned data from Step 2 (or None)
        items_data: Cleaned data from Step 3
    
    Returns:
        dict: Summary with totals, counts, etc.
    
    Example:
        summary = get_fee_structure_summary(basic_data, billing_data, items_data)
        context['summary'] = summary
    """
    summary = {
        'structure_name': basic_data.get('name', 'Unnamed'),
        'academic_year': basic_data.get('academic_year'),
        'billing_frequency': basic_data.get('billing_frequency'),
        'session_count': len(basic_data.get('applicable_sessions', [])),
        'level_count': len(basic_data.get('academic_levels', [])),
    }
    
    # Calculate billing split count
    if billing_data:
        split_count = sum(
            1 for item in billing_data 
            if item and not item.get('DELETE', False)
        )
        summary['billing_split_count'] = split_count
    else:
        summary['billing_split_count'] = 0
    
    # Calculate fee items totals
    if items_data:
        total_amount = Decimal('0.00')
        item_count = 0
        
        for item in items_data:
            if item and not item.get('DELETE', False):
                item_count += 1
                amount = item.get('amount', Decimal('0.00'))
                total_amount += amount
        
        summary['item_count'] = item_count
        summary['total_amount'] = total_amount
        summary['average_item_amount'] = (
            total_amount / item_count if item_count > 0 else Decimal('0.00')
        )
    else:
        summary['item_count'] = 0
        summary['total_amount'] = Decimal('0.00')
        summary['average_item_amount'] = Decimal('0.00')
    
    return summary