# uniforms/forms.py

"""
Uniform Management Forms

All date validations use school timezone via get_school_today() from core.utils.

CHANGES FROM ORIGINAL:
- Removed MeasurementSession model — MeasurementSessionForm,
  MeasurementSessionFilterForm, and the measurement_session field on
  BulkMeasurementForm have all been removed.
- Removed applicable_age_min / applicable_age_max from MeasurementTypeForm
  — those fields were removed from the MeasurementType model.
- Fixed MeasurementTypeFilterForm to reference MeasurementType.CATEGORY_CHOICES
  instead of the renamed MeasurementType.MEASUREMENT_CATEGORIES.
- Removed min_age / max_age from UniformSizeForm — those fields were removed
  from the UniformSize model.
- Added is_current filter to StudentMeasurementFilterForm — used by the view's
  get_filtered_student_measurements() helper.
- Added GL account override fields (inventory_account, cogs_account,
  revenue_account) to UniformItemForm under an advanced section so staff
  can override the FinancialSettings defaults per item.
- UniformItemForm: category, subcategory, barcode, maximum_stock,
  supplier_name, supplier_contact, supplier_item_code, material, and
  care_instructions are not included — those fields no longer exist on
  the model.
- UniformItemFilterForm: category filter removed — field no longer on model.
"""

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
import logging

from utils.forms import (
    BootstrapFormMixin,
    HTMXFilterFormMixin,
    DateRangeFormMixin,
    RequiredFieldsMixin,
    MoneyFieldsMixin,
    BaseFilterForm,
    DateRangeFilterForm,
    DatePickerInput,
    SearchInput,
    SelectWithDefault,
    MoneyInput,
    PercentageInput,
)

from .models import (
    MeasurementType,
    StudentMeasurement,
    UniformSize,
    UniformItem,
    UniformStock,
    UniformPurchaseOrder,
    UniformPurchaseOrderItem,
    UniformSale,
    UniformSaleItem,
    StudentUniformSize,
)
from students.models import Student
from academics.models import AcademicSession, Class
from core.models import UnitOfMeasure, PaymentMethod, TaxRate, FiscalPeriod
from finance.models import Account

logger = logging.getLogger(__name__)


# =============================================================================
# MEASUREMENT TYPE FORMS
# =============================================================================

class MeasurementTypeForm(RequiredFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """
    Create / edit a MeasurementType.

    applicable_age_min and applicable_age_max have been removed from both
    the model and this form — they were never used in validation logic.
    """

    class Meta:
        model  = MeasurementType
        fields = [
            'name', 'code', 'category', 'description', 'unit',
            'min_value', 'max_value',
            'display_order', 'is_required', 'is_active',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'e.g., Height, Chest, Waist'
            }),
            'code': forms.TextInput(attrs={
                'placeholder':  'e.g., HEIGHT, CHEST, WAIST',
                'style':        'text-transform: uppercase;',
            }),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={
                'rows':        3,
                'placeholder': 'Description of this measurement type...',
            }),
            'unit': forms.Select(attrs={'class': 'form-select'}),
            'min_value': forms.NumberInput(attrs={
                'step': '0.01', 'placeholder': 'Minimum reasonable value'
            }),
            'max_value': forms.NumberInput(attrs={
                'step': '0.01', 'placeholder': 'Maximum reasonable value'
            }),
            'display_order': forms.NumberInput(attrs={'min': '1'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.fields['unit'].queryset = UnitOfMeasure.objects.filter(
                is_active=True
            ).order_by('name')
        except Exception as e:
            logger.error(f"Error setting unit queryset: {e}")

        self.fields['code'].help_text = (
            "Uppercase code used by the size-recommendation algorithm "
            "(e.g. HEIGHT, CHEST, WAIST). Do not change after setup."
        )

    def clean_code(self):
        return self.cleaned_data.get('code', '').upper().strip()

    def clean(self):
        cleaned_data = super().clean()
        min_val = cleaned_data.get('min_value')
        max_val = cleaned_data.get('max_value')
        if min_val is not None and max_val is not None and min_val >= max_val:
            raise ValidationError({
                'max_value': 'Maximum value must be greater than minimum value.'
            })
        return cleaned_data


class MeasurementTypeFilterForm(BaseFilterForm):
    """Filter / search form for measurement types."""

    q = forms.CharField(
        label='Search', required=False,
        widget=SearchInput(attrs={'placeholder': 'Search by name or code...'})
    )
    # Fixed: was MeasurementType.MEASUREMENT_CATEGORIES — renamed CATEGORY_CHOICES.
    category = forms.ChoiceField(
        label='Category',
        choices=[('', 'All Categories')] + list(MeasurementType.CATEGORY_CHOICES),
        required=False,
        widget=SelectWithDefault(default_label="All Categories"),
    )
    unit = forms.ModelChoiceField(
        label='Unit', queryset=None, required=False,
        widget=SelectWithDefault(default_label="All Units"),
    )
    is_active = forms.NullBooleanField(
        label='Status', required=False,
        widget=forms.Select(
            choices=[('', 'All'), ('true', 'Active'), ('false', 'Inactive')],
            attrs={'class': 'form-select'},
        ),
    )
    is_required = forms.NullBooleanField(
        label='Required', required=False,
        widget=forms.Select(
            choices=[('', 'All'), ('true', 'Required'), ('false', 'Optional')],
            attrs={'class': 'form-select'},
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.fields['unit'].queryset = UnitOfMeasure.objects.filter(
                is_active=True
            ).order_by('name')
        except Exception as e:
            logger.error(f"Error setting unit queryset: {e}")


# =============================================================================
# STUDENT MEASUREMENT FORMS
# =============================================================================

class StudentMeasurementForm(RequiredFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """
    Record a single student measurement.

    measurement_type is still a FK to MeasurementType (kept as a separate
    model). academic_session is required — needed for term-based reporting
    and for scoping StudentUniformSize recommendations.
    """

    class Meta:
        model  = StudentMeasurement
        fields = [
            'student', 'measurement_type', 'value', 'measurement_date',
            'academic_session', 'measurement_context', 'measurement_method',
            'is_verified', 'notes',
        ]
        widgets = {
            'student': forms.Select(attrs={
                'class':            'form-select',
                'data-placeholder': 'Select student...',
            }),
            'measurement_type': forms.Select(attrs={'class': 'form-select'}),
            'value': forms.NumberInput(attrs={
                'step': '0.01', 'placeholder': 'Measurement value'
            }),
            'measurement_date': DatePickerInput(),
            'academic_session': forms.Select(attrs={'class': 'form-select'}),
            'measurement_context': forms.Select(attrs={'class': 'form-select'}),
            'measurement_method':  forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={
                'rows': 3, 'placeholder': 'Additional notes...'
            }),
        }

    def __init__(self, *args, **kwargs):
        student = kwargs.pop('student', None)
        super().__init__(*args, **kwargs)

        try:
            if student:
                self.fields['student'].initial = student
                self.fields['student'].widget.attrs['readonly'] = True
            else:
                self.fields['student'].queryset = Student.objects.filter(
                    enrollment_status='ACTIVE'
                ).order_by('first_name', 'last_name')

            self.fields['measurement_type'].queryset = (
                MeasurementType.objects.filter(is_active=True)
                .order_by('category', 'display_order')
            )
            self.fields['academic_session'].queryset = (
                AcademicSession.objects.filter(is_active=True)
                .order_by('-start_date')
            )
        except Exception as e:
            logger.error(f"Error setting querysets in StudentMeasurementForm: {e}")

        if not self.is_bound:
            from core.utils import get_school_today
            self.fields['measurement_date'].initial = get_school_today()

    def clean(self):
        cleaned_data      = super().clean()
        measurement_date  = cleaned_data.get('measurement_date')
        measurement_type  = cleaned_data.get('measurement_type')
        value             = cleaned_data.get('value')

        from core.utils import get_school_today
        if measurement_date and measurement_date > get_school_today():
            raise ValidationError({
                'measurement_date': 'Measurement date cannot be in the future.'
            })

        # Mirror the model's clean() so errors surface in the form, not as
        # an unhandled IntegrityError on save.
        if measurement_type and value is not None:
            if (measurement_type.min_value is not None
                    and value < measurement_type.min_value):
                self.add_error(
                    'value',
                    f"Value is below the minimum for "
                    f"{measurement_type.name} "
                    f"({measurement_type.min_value} "
                    f"{measurement_type.unit.abbreviation}).",
                )
            if (measurement_type.max_value is not None
                    and value > measurement_type.max_value):
                self.add_error(
                    'value',
                    f"Value is above the maximum for "
                    f"{measurement_type.name} "
                    f"({measurement_type.max_value} "
                    f"{measurement_type.unit.abbreviation}).",
                )
        return cleaned_data


class BulkMeasurementForm(RequiredFieldsMixin, BootstrapFormMixin, forms.Form):
    """
    Set up a bulk measurement run (measure all students in a class in one go).

    The measurement_session field has been removed — MeasurementSession model
    is gone. Each measurement is recorded directly as a StudentMeasurement
    with the context / method chosen here.
    """

    academic_session = forms.ModelChoiceField(
        label='Academic Session', queryset=None, required=True,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    measurement_date = forms.DateField(
        label='Measurement Date', required=True, widget=DatePickerInput(),
    )
    measurement_context = forms.ChoiceField(
        label='Context',
        choices=StudentMeasurement.MEASUREMENT_CONTEXT_CHOICES,
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    measurement_method = forms.ChoiceField(
        label='Method',
        choices=StudentMeasurement.MEASUREMENT_METHOD_CHOICES,
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    target_class = forms.ModelChoiceField(
        label='Target Class', queryset=None, required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Measure all students in this class. Leave blank to select students individually.',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.fields['academic_session'].queryset = (
                AcademicSession.objects.filter(is_active=True).order_by('-start_date')
            )
            self.fields['target_class'].queryset = (
                Class.objects.filter(is_active=True)
                .order_by('academic_level__level_order', 'name')
            )
        except Exception as e:
            logger.error(f"Error setting querysets in BulkMeasurementForm: {e}")

        if not self.is_bound:
            from core.utils import get_school_today
            self.fields['measurement_date'].initial = get_school_today()

    def clean_measurement_date(self):
        date = self.cleaned_data.get('measurement_date')
        from core.utils import get_school_today
        if date and date > get_school_today():
            raise ValidationError('Measurement date cannot be in the future.')
        return date


class StudentMeasurementFilterForm(DateRangeFilterForm):
    """Filter / search form for student measurements."""

    q = forms.CharField(
        label='Search', required=False,
        widget=SearchInput(attrs={'placeholder': 'Search by student name or admission number...'})
    )
    student = forms.ModelChoiceField(
        label='Student', queryset=None, required=False,
        widget=SelectWithDefault(default_label="All Students"),
    )
    measurement_type = forms.ModelChoiceField(
        label='Measurement Type', queryset=None, required=False,
        widget=SelectWithDefault(default_label="All Types"),
    )
    academic_session = forms.ModelChoiceField(
        label='Academic Session', queryset=None, required=False,
        widget=SelectWithDefault(default_label="All Sessions"),
    )
    measurement_context = forms.ChoiceField(
        label='Context',
        choices=[('', 'All Contexts')] + list(StudentMeasurement.MEASUREMENT_CONTEXT_CHOICES),
        required=False,
        widget=SelectWithDefault(default_label="All Contexts"),
    )
    is_verified = forms.NullBooleanField(
        label='Verification', required=False,
        widget=forms.Select(
            choices=[('', 'All'), ('true', 'Verified'), ('false', 'Unverified')],
            attrs={'class': 'form-select'},
        ),
    )
    # Added: used by get_filtered_student_measurements() in views.py
    is_current = forms.NullBooleanField(
        label='Current Only', required=False,
        widget=forms.Select(
            choices=[('', 'All'), ('true', 'Current'), ('false', 'Historical')],
            attrs={'class': 'form-select'},
        ),
    )
    measurement_date_from = forms.DateField(
        label='Date From', required=False, widget=DatePickerInput(),
    )
    measurement_date_to = forms.DateField(
        label='Date To', required=False, widget=DatePickerInput(),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.fields['student'].queryset = (
                Student.objects.filter(enrollment_status='ACTIVE')
                .order_by('first_name', 'last_name')
            )
            self.fields['measurement_type'].queryset = (
                MeasurementType.objects.filter(is_active=True)
                .order_by('category', 'display_order')
            )
            self.fields['academic_session'].queryset = (
                AcademicSession.objects.filter(is_active=True)
                .order_by('-start_date')
            )
        except Exception as e:
            logger.error(f"Error setting querysets in StudentMeasurementFilterForm: {e}")


# =============================================================================
# UNIFORM SIZE FORMS
# =============================================================================

class UniformSizeForm(RequiredFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """
    Create / edit a UniformSize.

    min_age and max_age have been removed from both the model and this form —
    school uniforms are sized by body measurements, not age.
    """

    class Meta:
        model  = UniformSize
        fields = [
            'name', 'code', 'size_type', 'description',
            'min_height', 'max_height',
            'min_chest',  'max_chest',
            'min_waist',  'max_waist',
            'display_order', 'is_active',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'e.g., S, M, L, XL, 32, 34'
            }),
            'code': forms.TextInput(attrs={
                'placeholder': 'e.g., S, M, L, 32',
                'style':       'text-transform: uppercase;',
            }),
            'size_type': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={
                'rows': 2, 'placeholder': 'Size description...'
            }),
            'min_height': forms.NumberInput(attrs={
                'step': '0.1', 'placeholder': 'Min height (cm)'
            }),
            'max_height': forms.NumberInput(attrs={
                'step': '0.1', 'placeholder': 'Max height (cm)'
            }),
            'min_chest': forms.NumberInput(attrs={
                'step': '0.1', 'placeholder': 'Min chest (cm)'
            }),
            'max_chest': forms.NumberInput(attrs={
                'step': '0.1', 'placeholder': 'Max chest (cm)'
            }),
            'min_waist': forms.NumberInput(attrs={
                'step': '0.1', 'placeholder': 'Min waist (cm)'
            }),
            'max_waist': forms.NumberInput(attrs={
                'step': '0.1', 'placeholder': 'Max waist (cm)'
            }),
            'display_order': forms.NumberInput(attrs={'min': '1'}),
        }

    def clean_code(self):
        return self.cleaned_data.get('code', '').upper().strip()

    def clean(self):
        cleaned_data = super().clean()
        pairs = [
            ('min_height', 'max_height', 'Height'),
            ('min_chest',  'max_chest',  'Chest'),
            ('min_waist',  'max_waist',  'Waist'),
        ]
        for min_field, max_field, label in pairs:
            lo = cleaned_data.get(min_field)
            hi = cleaned_data.get(max_field)
            if lo is not None and hi is not None and lo >= hi:
                raise ValidationError({
                    max_field: f'{label} maximum must be greater than minimum.'
                })
        return cleaned_data


class UniformSizeFilterForm(BaseFilterForm):
    """Filter / search form for uniform sizes."""

    q = forms.CharField(
        label='Search', required=False,
        widget=SearchInput(attrs={'placeholder': 'Search by name or code...'})
    )
    size_type = forms.ChoiceField(
        label='Size Type',
        choices=[('', 'All Types')] + list(UniformSize.SIZE_TYPE_CHOICES),
        required=False,
        widget=SelectWithDefault(default_label="All Types"),
    )
    is_active = forms.NullBooleanField(
        label='Status', required=False,
        widget=forms.Select(
            choices=[('', 'All'), ('true', 'Active'), ('false', 'Inactive')],
            attrs={'class': 'form-select'},
        ),
    )


# =============================================================================
# UNIFORM ITEM FORMS
# =============================================================================

class UniformItemForm(RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """
    Create / edit a UniformItem.

    Fields NOT included (removed from model):
        barcode, category, subcategory, maximum_stock,
        supplier_name, supplier_contact, supplier_item_code,
        material, care_instructions

    GL account overrides (inventory_account, cogs_account, revenue_account)
    are included in an "Advanced" fieldset. Leave them blank to use the
    FinancialSettings defaults.

    STOCK FIELD BEHAVIOUR:
        Create mode — editable for the opening balance.
        Edit mode   — always disabled. current_stock is a signal-maintained
                      Sum() cache. All changes must go through UniformStock
                      or the stock-adjustment views so the signal fires.
    """

    class Meta:
        model  = UniformItem
        fields = [
            # Basic
            'name', 'code', 'description', 'item_type', 'gender',
            # Sizing
            'requires_sizing', 'available_sizes',
            # Unit
            'unit_of_measure',
            # Pricing
            'unit_cost', 'selling_price',
            # Inventory
            'sku', 'current_stock', 'reorder_level',
            # Details
            'image', 'color',
            # Tax
            'is_taxable', 'tax_rate',
            # GL overrides (advanced)
            'inventory_account', 'cogs_account', 'revenue_account',
            # Status
            'is_active', 'is_mandatory', 'notes',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'e.g., Boys Shirt — White, Sports Shorts'
            }),
            'code': forms.TextInput(attrs={
                'placeholder': 'e.g., UNI-BS-W, SPT-SH-B',
                'style':       'text-transform: uppercase;',
            }),
            'description': forms.Textarea(attrs={
                'rows': 3, 'placeholder': 'Detailed item description...'
            }),
            'item_type':        forms.Select(attrs={'class': 'form-select'}),
            'gender':           forms.Select(attrs={'class': 'form-select'}),
            'available_sizes':  forms.SelectMultiple(attrs={'class': 'form-select', 'size': '5'}),
            'unit_of_measure':  forms.Select(attrs={'class': 'form-select'}),
            'unit_cost':        MoneyInput(),
            'selling_price':    MoneyInput(),
            'sku':              forms.TextInput(attrs={'placeholder': 'Stock Keeping Unit (optional)'}),
            'current_stock':    forms.NumberInput(attrs={'min': '0'}),
            'reorder_level':    forms.NumberInput(attrs={'min': '0'}),
            'color':            forms.TextInput(attrs={'placeholder': 'e.g., White, Navy Blue'}),
            'tax_rate':         forms.Select(attrs={'class': 'form-select'}),
            'inventory_account':forms.Select(attrs={'class': 'form-select'}),
            'cogs_account':     forms.Select(attrs={'class': 'form-select'}),
            'revenue_account':  forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Additional notes...'}),
        }

    # Read by templates to conditionally show/hide stock help text.
    is_edit_mode: bool = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        try:
            self.fields['available_sizes'].queryset = (
                UniformSize.objects.filter(is_active=True).order_by('display_order')
            )
            self.fields['unit_of_measure'].queryset = (
                UnitOfMeasure.objects.filter(is_active=True, uom_type='QUANTITY')
                .order_by('name')
            )
            self.fields['tax_rate'].queryset = (
                TaxRate.objects.filter(is_active=True).order_by('name')
            )
            # GL account overrides — only income/asset accounts are sensible
            # here but we leave filtering to the admin to keep it simple.
            gl_qs = Account.objects.filter(is_active=True).order_by('code')
            self.fields['inventory_account'].queryset = gl_qs
            self.fields['cogs_account'].queryset      = gl_qs
            self.fields['revenue_account'].queryset   = gl_qs
        except Exception as e:
            logger.error(f"Error setting querysets in UniformItemForm: {e}")

        self.fields['code'].help_text         = "Unique item code — uppercase recommended"
        self.fields['unit_cost'].help_text     = "Cost price used for COGS calculations"
        self.fields['selling_price'].help_text = "Price charged to students"
        self.fields['inventory_account'].help_text = "Leave blank to use FinancialSettings default"
        self.fields['cogs_account'].help_text      = "Leave blank to use FinancialSettings default"
        self.fields['revenue_account'].help_text   = "Leave blank to use FinancialSettings default"

        # Make GL override fields optional
        for f in ('inventory_account', 'cogs_account', 'revenue_account', 'tax_rate'):
            self.fields[f].required = False

        # ── current_stock lock ────────────────────────────────────────────────
        self.is_edit_mode = bool(self.instance and self.instance.pk)

        if self.is_edit_mode:
            self.fields['current_stock'].disabled   = True
            self.fields['current_stock'].help_text  = (
                "Read-only in edit mode — managed automatically by stock records. "
                "Use Stock Adjustment or Purchase Orders to change stock levels."
            )
        else:
            self.fields['current_stock'].help_text = (
                "Opening stock balance. After creation, manage stock via "
                "Stock Adjustment or Purchase Orders."
            )

    def clean_code(self):
        return self.cleaned_data.get('code', '').upper().strip()

    def clean(self):
        cleaned_data  = super().clean()
        unit_cost     = cleaned_data.get('unit_cost')
        selling_price = cleaned_data.get('selling_price')

        if unit_cost and selling_price and selling_price < unit_cost:
            self.add_error(
                'selling_price',
                'Selling price is lower than unit cost — the school would sell '
                'at a loss. Please verify.',
            )
        return cleaned_data


class UniformItemFilterForm(BaseFilterForm):
    """
    Filter / search form for uniform items.

    category field removed — that field no longer exists on UniformItem.
    Use item_type instead.
    """

    q = forms.CharField(
        label='Search', required=False,
        widget=SearchInput(attrs={'placeholder': 'Search by name, code, or SKU...'})
    )
    item_type = forms.ChoiceField(
        label='Item Type',
        choices=[('', 'All Types')] + list(UniformItem.ITEM_TYPE_CHOICES),
        required=False,
        widget=SelectWithDefault(default_label="All Types"),
    )
    gender = forms.ChoiceField(
        label='Gender',
        choices=[('', 'All')] + list(UniformItem.GENDER_CHOICES),
        required=False,
        widget=SelectWithDefault(default_label="All"),
    )
    stock_status = forms.ChoiceField(
        label='Stock Status',
        choices=[
            ('',             'All'),
            ('in_stock',     'In Stock'),
            ('low_stock',    'Low Stock'),
            ('out_of_stock', 'Out of Stock'),
        ],
        required=False,
        widget=SelectWithDefault(default_label="All"),
    )
    is_active = forms.NullBooleanField(
        label='Status', required=False,
        widget=forms.Select(
            choices=[('', 'All'), ('true', 'Active'), ('false', 'Inactive')],
            attrs={'class': 'form-select'},
        ),
    )
    is_mandatory = forms.NullBooleanField(
        label='Mandatory', required=False,
        widget=forms.Select(
            choices=[('', 'All'), ('true', 'Mandatory'), ('false', 'Optional')],
            attrs={'class': 'form-select'},
        ),
    )

class UniformStockFilterForm(BaseFilterForm):
    """
    Filter / search form for the stock list view.

    Covers all four axes the view supports:
      q            — full-text search across item name, code, and size name
      item         — filter to a single UniformItem
      size         — filter to a single UniformSize
      stock_status — in_stock / low_stock / out_of_stock
    """

    q = forms.CharField(
        label='Search', required=False,
        widget=SearchInput(attrs={'placeholder': 'Item name, code or size…'})
    )
    item = forms.ModelChoiceField(
        label='Item', queryset=None, required=False,
        widget=SelectWithDefault(default_label='All Items'),
    )
    size = forms.ModelChoiceField(
        label='Size', queryset=None, required=False,
        widget=SelectWithDefault(default_label='All Sizes'),
    )
    stock_status = forms.ChoiceField(
        label='Stock Status',
        choices=[
            ('',             'All'),
            ('in_stock',     'In Stock'),
            ('low_stock',    'Low Stock'),
            ('out_of_stock', 'Out of Stock'),
        ],
        required=False,
        widget=SelectWithDefault(default_label='All'),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.fields['item'].queryset = (
                UniformItem.objects.filter(is_active=True).order_by('name')
            )
            self.fields['size'].queryset = (
                UniformSize.objects.filter(is_active=True).order_by('display_order')
            )
        except Exception as e:
            logger.error(f'Error setting querysets in UniformStockFilterForm: {e}')


# =============================================================================
# UNIFORM STOCK FORMS
# =============================================================================

class UniformStockForm(RequiredFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """
    Create / edit a UniformStock record.

    The DB has two unique constraints:
      - unique (uniform_item, size) where size IS NOT NULL
      - unique (uniform_item)       where size IS NULL

    clean() surfaces these as friendly form errors before the DB raises
    an IntegrityError.
    """

    class Meta:
        model  = UniformStock
        fields = [
            'uniform_item', 'size', 'quantity', 'reserved_quantity',
            'location', 'bin_number',
        ]
        widgets = {
            'uniform_item':     forms.Select(attrs={'class': 'form-select'}),
            'size':             forms.Select(attrs={'class': 'form-select'}),
            'quantity':         forms.NumberInput(attrs={'min': '0'}),
            'reserved_quantity':forms.NumberInput(attrs={'min': '0'}),
            'location':         forms.TextInput(attrs={'placeholder': 'Storage location'}),
            'bin_number':       forms.TextInput(attrs={'placeholder': 'Bin / shelf number'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.fields['uniform_item'].queryset = (
                UniformItem.objects.filter(is_active=True).order_by('name')
            )
            self.fields['size'].queryset = (
                UniformSize.objects.filter(is_active=True).order_by('display_order')
            )
        except Exception as e:
            logger.error(f"Error setting querysets in UniformStockForm: {e}")

        self.fields['size'].required = False
        self.fields['size'].help_text = (
            'Leave blank for items that do not require sizing'
        )

    def clean(self):
        cleaned_data = super().clean()
        uniform_item = cleaned_data.get('uniform_item')
        size         = cleaned_data.get('size')

        if uniform_item is None:
            return cleaned_data

        if uniform_item.requires_sizing:
            if not size:
                self.add_error('size', 'This item requires a size — please select one.')
        else:
            # Clear any accidentally submitted size value for unsized items.
            cleaned_data['size'] = None

            # Surface the unique constraint as a friendly error.
            qs = UniformStock.objects.filter(
                uniform_item=uniform_item, size__isnull=True
            )
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error(
                    'uniform_item',
                    'A stock record already exists for this item. '
                    'Edit the existing record instead of creating a new one.',
                )
        return cleaned_data


class StockAdjustmentForm(RequiredFieldsMixin, BootstrapFormMixin, forms.Form):
    """Adjust stock level for a single UniformStock record."""

    ADJUSTMENT_TYPE_CHOICES = [
        ('ADD',    'Add Stock'),
        ('REMOVE', 'Remove Stock'),
        ('SET',    'Set Stock Level'),
    ]

    adjustment_type = forms.ChoiceField(
        label='Adjustment Type',
        choices=ADJUSTMENT_TYPE_CHOICES,
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    quantity = forms.IntegerField(
        label='Quantity',
        min_value=0,
        required=True,
        widget=forms.NumberInput(attrs={'min': '0', 'placeholder': 'Quantity'}),
    )
    reason = forms.CharField(
        label='Reason',
        required=True,
        widget=forms.Textarea(attrs={
            'rows': 3, 'placeholder': 'Reason for this stock adjustment...'
        }),
    )


# =============================================================================
# UNIFORM PURCHASE ORDER FORMS
# =============================================================================

class UniformPurchaseOrderForm(
    RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.ModelForm
):
    """Create / edit a uniform purchase order."""

    class Meta:
        model  = UniformPurchaseOrder
        fields = [
            'supplier_name', 'supplier_contact', 'supplier_email', 'supplier_phone',
            'order_date', 'expected_delivery_date', 'fiscal_period',
            'shipping_cost', 'payment_terms',
            'auto_create_journal_entry', 'notes',
        ]
        widgets = {
            'supplier_name':    forms.TextInput(attrs={'placeholder': 'Supplier name'}),
            'supplier_contact': forms.TextInput(attrs={'placeholder': 'Contact person'}),
            'supplier_email':   forms.EmailInput(attrs={'placeholder': 'email@supplier.com'}),
            'supplier_phone':   forms.TextInput(attrs={'placeholder': '+256700000000'}),
            'order_date':               DatePickerInput(),
            'expected_delivery_date':   DatePickerInput(),
            'fiscal_period':    forms.Select(attrs={'class': 'form-select'}),
            'shipping_cost':    MoneyInput(),
            'payment_terms':    forms.TextInput(attrs={
                'placeholder': 'e.g., Net 30, Payment on Delivery'
            }),
            'notes': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Additional notes...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.fields['fiscal_period'].queryset = (
                FiscalPeriod.objects.filter(is_active=True, is_closed=False)
                .order_by('-start_date')
            )
        except Exception as e:
            logger.error(f"Error setting querysets in UniformPurchaseOrderForm: {e}")

        if not self.is_bound:
            from core.utils import get_school_today
            self.fields['order_date'].initial = get_school_today()

    def clean(self):
        cleaned_data           = super().clean()
        order_date             = cleaned_data.get('order_date')
        expected_delivery_date = cleaned_data.get('expected_delivery_date')

        from core.utils import get_school_today
        today = get_school_today()

        if order_date and order_date > today:
            raise ValidationError({'order_date': 'Order date cannot be in the future.'})

        if order_date and expected_delivery_date and expected_delivery_date < order_date:
            raise ValidationError({
                'expected_delivery_date': (
                    'Expected delivery date cannot be before the order date.'
                )
            })
        return cleaned_data


class UniformPurchaseOrderItemForm(
    RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.ModelForm
):
    """Purchase order line item (used in inline formsets)."""

    class Meta:
        model  = UniformPurchaseOrderItem
        fields = ['uniform_item', 'size', 'quantity_ordered', 'unit_price', 'notes']
        widgets = {
            'uniform_item':    forms.Select(attrs={'class': 'form-select'}),
            'size':            forms.Select(attrs={'class': 'form-select'}),
            'quantity_ordered':forms.NumberInput(attrs={'min': '1'}),
            'unit_price':      MoneyInput(),
            'notes':           forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.fields['uniform_item'].queryset = (
                UniformItem.objects.filter(is_active=True).order_by('name')
            )
            self.fields['size'].queryset = (
                UniformSize.objects.filter(is_active=True).order_by('display_order')
            )
        except Exception as e:
            logger.error(f"Error setting querysets in UniformPurchaseOrderItemForm: {e}")

        self.fields['size'].required = False


class UniformPurchaseOrderFilterForm(DateRangeFilterForm):
    """Filter / search form for purchase orders."""

    q = forms.CharField(
        label='Search', required=False,
        widget=SearchInput(attrs={'placeholder': 'Search by PO number or supplier...'})
    )
    status = forms.ChoiceField(
        label='Status',
        choices=[('', 'All Statuses')] + list(UniformPurchaseOrder.STATUS_CHOICES),
        required=False,
        widget=SelectWithDefault(default_label="All Statuses"),
    )
    fiscal_period = forms.ModelChoiceField(
        label='Fiscal Period', queryset=None, required=False,
        widget=SelectWithDefault(default_label="All Periods"),
    )
    order_date_from = forms.DateField(
        label='Order Date From', required=False, widget=DatePickerInput()
    )
    order_date_to = forms.DateField(
        label='Order Date To', required=False, widget=DatePickerInput()
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.fields['fiscal_period'].queryset = (
                FiscalPeriod.objects.all().order_by('-start_date')
            )
        except Exception as e:
            logger.error(f"Error setting querysets in UniformPurchaseOrderFilterForm: {e}")


# =============================================================================
# UNIFORM SALE FORMS
# =============================================================================

class UniformSaleForm(
    RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.ModelForm
):
    """
    Create / edit a uniform sale header.

    fiscal_period is auto-assigned by the uniform_sale_pre_save signal.
    academic_session is a property derived from fiscal_period — not a field.
    auto_create_invoice and auto_create_journal_entry are always True and
    are not exposed in the form.
    """

    class Meta:
        model  = UniformSale
        fields = [
            'student', 'sale_type', 'sale_date',
            'discount_amount', 'discount_reason',
            'payment_method', 'payment_reference',
            'return_date', 'notes',
        ]
        widgets = {
            'student': forms.Select(attrs={
                'class':            'form-select',
                'data-placeholder': 'Select student...',
            }),
            'sale_type':          forms.Select(attrs={'class': 'form-select'}),
            'sale_date':          DatePickerInput(),
            'discount_amount':    MoneyInput(),
            'discount_reason':    forms.TextInput(attrs={
                'placeholder': 'Reason for discount (if applicable)...'
            }),
            'payment_method':     forms.Select(attrs={'class': 'form-select'}),
            'payment_reference':  forms.TextInput(attrs={'placeholder': 'Payment reference'}),
            'return_date':        DatePickerInput(),
            'notes': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Additional notes...'}),
        }

    def __init__(self, *args, **kwargs):
        student = kwargs.pop('student', None)
        super().__init__(*args, **kwargs)

        try:
            if student:
                self.fields['student'].initial = student
            else:
                self.fields['student'].queryset = (
                    Student.objects.filter(enrollment_status='ACTIVE')
                    .order_by('first_name', 'last_name')
                )
            self.fields['payment_method'].queryset = (
                PaymentMethod.objects.filter(is_active=True).order_by('name')
            )
        except Exception as e:
            logger.error(f"Error setting querysets in UniformSaleForm: {e}")

        self.fields['discount_amount'].required = False
        self.fields['return_date'].required     = False
        self.fields['payment_method'].required  = False
        self.fields['payment_reference'].required = False

        if not self.is_bound:
            from core.utils import get_school_today
            self.fields['sale_date'].initial = get_school_today()

    def clean(self):
        cleaned_data  = super().clean()
        sale_date     = cleaned_data.get('sale_date')
        sale_type     = cleaned_data.get('sale_type')
        return_date   = cleaned_data.get('return_date')

        from core.utils import get_school_today
        today = get_school_today()

        if sale_date and sale_date > today:
            raise ValidationError({'sale_date': 'Sale date cannot be in the future.'})

        if sale_type == 'LOAN' and not return_date:
            self.add_error('return_date', 'Return date is required for loaned items.')

        if sale_date and return_date and return_date < sale_date:
            raise ValidationError({
                'return_date': 'Return date cannot be before the sale date.'
            })
        return cleaned_data


class UniformSaleItemForm(
    RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.ModelForm
):
    """Uniform sale line item (used in inline formsets)."""

    class Meta:
        model  = UniformSaleItem
        fields = [
            'uniform_item', 'size', 'quantity',
            'unit_price', 'unit_cost',
            'tax_rate', 'tax_percentage',
            'discount_percentage', 'notes',
        ]
        widgets = {
            'uniform_item':       forms.Select(attrs={'class': 'form-select'}),
            'size':               forms.Select(attrs={'class': 'form-select'}),
            'quantity':           forms.NumberInput(attrs={'min': '1'}),
            'unit_price':         MoneyInput(),
            'unit_cost':          MoneyInput(),
            'tax_rate':           forms.Select(attrs={'class': 'form-select'}),
            'tax_percentage':     PercentageInput(),
            'discount_percentage':PercentageInput(),
            'notes':              forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.fields['uniform_item'].queryset = (
                UniformItem.objects.filter(is_active=True).order_by('name')
            )
            self.fields['size'].queryset = (
                UniformSize.objects.filter(is_active=True).order_by('display_order')
            )
            self.fields['tax_rate'].queryset = (
                TaxRate.objects.filter(is_active=True).order_by('name')
            )
        except Exception as e:
            logger.error(f"Error setting querysets in UniformSaleItemForm: {e}")

        self.fields['size'].required     = False
        self.fields['tax_rate'].required = False


class UniformSaleFilterForm(DateRangeFilterForm):
    """
    Filter / search form for uniform sales.

    academic_session filters via fiscal_period__related_academic_session
    in the view — not via a direct field on UniformSale (which has none).
    """

    q = forms.CharField(
        label='Search', required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by sale number, student name or admission number...'
        })
    )
    academic_session = forms.ModelChoiceField(
        label='Academic Session', queryset=None, required=False,
        widget=SelectWithDefault(default_label="All Sessions"),
        help_text='Filters via the linked fiscal period',
    )
    fiscal_period = forms.ModelChoiceField(
        label='Fiscal Period', queryset=None, required=False,
        widget=SelectWithDefault(default_label="All Periods"),
    )
    sale_type = forms.ChoiceField(
        label='Sale Type',
        choices=[('', 'All Types')] + list(UniformSale.SALE_TYPE_CHOICES),
        required=False,
        widget=SelectWithDefault(default_label="All Types"),
    )
    status = forms.ChoiceField(
        label='Status',
        choices=[('', 'All Statuses')] + list(UniformSale.STATUS_CHOICES),
        required=False,
        widget=SelectWithDefault(default_label="All Statuses"),
    )
    sale_date_from = forms.DateField(
        label='Sale Date From', required=False, widget=DatePickerInput()
    )
    sale_date_to = forms.DateField(
        label='Sale Date To', required=False, widget=DatePickerInput()
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.fields['academic_session'].queryset = (
                AcademicSession.objects.all().order_by('-start_date')
            )
            self.fields['fiscal_period'].queryset = (
                FiscalPeriod.objects.all().order_by('-start_date')
            )
        except Exception as e:
            logger.error(f"Error setting querysets in UniformSaleFilterForm: {e}")


# =============================================================================
# STUDENT UNIFORM SIZE RECOMMENDATION FORM
# =============================================================================

class StudentUniformSizeForm(
    RequiredFieldsMixin, BootstrapFormMixin, forms.ModelForm
):
    """
    Create / edit a StudentUniformSize recommendation.

    Recommendations are normally generated automatically by the
    student_measurement_post_save signal, but staff can override them here
    by selecting a different size and setting sizing_method to FITTED or
    PARENT_PROVIDED.
    """

    class Meta:
        model  = StudentUniformSize
        fields = [
            'student', 'uniform_item', 'recommended_size', 'academic_session',
            'sizing_method', 'confidence_level', 'recommendation_date',
            'growth_allowance', 'notes',
        ]
        widgets = {
            'student': forms.Select(attrs={
                'class':            'form-select',
                'data-placeholder': 'Select student...',
            }),
            'uniform_item':       forms.Select(attrs={'class': 'form-select'}),
            'recommended_size':   forms.Select(attrs={'class': 'form-select'}),
            'academic_session':   forms.Select(attrs={'class': 'form-select'}),
            'sizing_method':      forms.Select(attrs={'class': 'form-select'}),
            'confidence_level':   forms.Select(attrs={'class': 'form-select'}),
            'recommendation_date':DatePickerInput(),
            'notes': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Additional notes...'}),
        }

    def __init__(self, *args, **kwargs):
        student = kwargs.pop('student', None)
        super().__init__(*args, **kwargs)

        try:
            if student:
                self.fields['student'].initial = student
            else:
                self.fields['student'].queryset = (
                    Student.objects.filter(enrollment_status='ACTIVE')
                    .order_by('first_name', 'last_name')
                )
            self.fields['uniform_item'].queryset = (
                UniformItem.objects.filter(is_active=True, requires_sizing=True)
                .order_by('name')
            )
            self.fields['recommended_size'].queryset = (
                UniformSize.objects.filter(is_active=True).order_by('display_order')
            )
            self.fields['academic_session'].queryset = (
                AcademicSession.objects.filter(is_active=True).order_by('-start_date')
            )
        except Exception as e:
            logger.error(f"Error setting querysets in StudentUniformSizeForm: {e}")

        if not self.is_bound:
            from core.utils import get_school_today
            self.fields['recommendation_date'].initial = get_school_today()

        self.fields['confidence_level'].help_text = (
            'Set automatically by the recommendation algorithm. '
            'Adjust if you are overriding the suggestion.'
        )