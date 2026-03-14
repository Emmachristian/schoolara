# uniforms/forms.py

"""
Uniform Management Forms with timezone support and HTMX filters.
All date validations use school timezone for consistency.

CHANGES:
- UniformItemForm: removed barcode, category, subcategory, maximum_stock,
  supplier_name, supplier_contact, supplier_item_code, material,
  care_instructions (removed from model).
- UniformItemForm.clean(): removed maximum_stock > current_stock validation
  (field no longer exists).
- UniformItemFilterForm: removed category filter field (field no longer
  exists on the model).
"""

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import Q
from decimal import Decimal
import logging

from utils.forms import (
    BootstrapFormMixin,
    HTMXFormMixin,
    HTMXFilterFormMixin,
    DateRangeFormMixin,
    RequiredFieldsMixin,
    MoneyFieldsMixin,
    BaseFilterForm,
    DateRangeFilterForm,
    DatePickerInput,
    DateTimePickerInput,
    SearchInput,
    SelectWithDefault,
    MoneyField,
    MoneyInput,
    PercentageField,
    PercentageInput,
    validate_future_date,
    validate_past_date,
    validate_date_not_before,
    validate_date_not_after,
    validate_positive_amount,
)

from .models import (
    MeasurementType, StudentMeasurement, UniformSize, UniformItem, UniformStock,
    UniformPurchaseOrder, UniformPurchaseOrderItem, UniformSale, UniformSaleItem,
    StudentUniformSize, MeasurementSession
)
from students.models import Student
from academics.models import AcademicSession, Class
from core.models import (
    UnitOfMeasure, PaymentMethod, TaxRate, FiscalPeriod
)
from finance.models import Account

logger = logging.getLogger(__name__)


# =============================================================================
# MEASUREMENT TYPE FORMS
# =============================================================================

class MeasurementTypeForm(RequiredFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """Form for creating/editing measurement types"""

    class Meta:
        model = MeasurementType
        fields = [
            'name', 'code', 'category', 'description', 'unit',
            'min_value', 'max_value', 'applicable_age_min', 'applicable_age_max',
            'display_order', 'is_required', 'is_active'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'e.g., Height, Chest, Waist'
            }),
            'code': forms.TextInput(attrs={
                'placeholder': 'e.g., HGT, CHT, WST',
                'style': 'text-transform: uppercase;'
            }),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Description of this measurement...'
            }),
            'unit': forms.Select(attrs={'class': 'form-select'}),
            'min_value': forms.NumberInput(attrs={
                'step': '0.01', 'placeholder': 'Minimum value'
            }),
            'max_value': forms.NumberInput(attrs={
                'step': '0.01', 'placeholder': 'Maximum value'
            }),
            'applicable_age_min': forms.NumberInput(attrs={
                'min': '0', 'placeholder': 'Min age'
            }),
            'applicable_age_max': forms.NumberInput(attrs={
                'min': '0', 'placeholder': 'Max age'
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
        self.fields['code'].help_text = "Unique code for this measurement"

    def clean_code(self):
        return self.cleaned_data.get('code', '').upper()

    def clean(self):
        cleaned_data = super().clean()
        min_value = cleaned_data.get('min_value')
        max_value = cleaned_data.get('max_value')
        if min_value and max_value and min_value >= max_value:
            raise ValidationError({
                'max_value': 'Maximum value must be greater than minimum value.'
            })
        min_age = cleaned_data.get('applicable_age_min')
        max_age = cleaned_data.get('applicable_age_max')
        if min_age and max_age and min_age >= max_age:
            raise ValidationError({
                'applicable_age_max': 'Maximum age must be greater than minimum age.'
            })
        return cleaned_data


class MeasurementTypeFilterForm(BaseFilterForm):
    """Filter form for measurement types"""

    q = forms.CharField(
        label='Search', required=False,
        widget=SearchInput(attrs={'placeholder': 'Search by name, code...'})
    )
    category = forms.ChoiceField(
        label='Category',
        choices=[('', 'All Categories')] + list(MeasurementType.MEASUREMENT_CATEGORIES),
        required=False,
        widget=SelectWithDefault(default_label="All Categories")
    )
    is_active = forms.NullBooleanField(
        label='Status', required=False,
        widget=forms.Select(
            choices=[('', 'All'), ('true', 'Active'), ('false', 'Inactive')],
            attrs={'class': 'form-select'}
        )
    )
    is_required = forms.NullBooleanField(
        label='Required', required=False,
        widget=forms.Select(
            choices=[('', 'All'), ('true', 'Required'), ('false', 'Optional')],
            attrs={'class': 'form-select'}
        )
    )


# =============================================================================
# STUDENT MEASUREMENT FORMS
# =============================================================================

class StudentMeasurementForm(RequiredFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """Form for recording student measurements. Uses school timezone. ⭐"""

    class Meta:
        model = StudentMeasurement
        fields = [
            'student', 'measurement_type', 'value', 'measurement_date',
            'academic_session', 'measurement_context', 'measurement_method',
            'is_verified', 'notes'
        ]
        widgets = {
            'student': forms.Select(attrs={
                'class': 'form-select', 'data-placeholder': 'Select student...'
            }),
            'measurement_type': forms.Select(attrs={'class': 'form-select'}),
            'value': forms.NumberInput(attrs={
                'step': '0.01', 'placeholder': 'Measurement value'
            }),
            'measurement_date': DatePickerInput(),
            'academic_session': forms.Select(attrs={'class': 'form-select'}),
            'measurement_context': forms.Select(attrs={'class': 'form-select'}),
            'measurement_method': forms.Select(attrs={'class': 'form-select'}),
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
            self.fields['measurement_type'].queryset = MeasurementType.objects.filter(
                is_active=True
            ).order_by('category', 'display_order')
            self.fields['academic_session'].queryset = AcademicSession.objects.filter(
                is_active=True
            ).order_by('-start_date')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")

        if not self.is_bound:
            from core.utils import get_school_today
            self.fields['measurement_date'].initial = get_school_today()

    def clean(self):
        cleaned_data = super().clean()
        measurement_date = cleaned_data.get('measurement_date')
        from core.utils import get_school_today
        today = get_school_today()
        if measurement_date and measurement_date > today:
            raise ValidationError({
                'measurement_date': 'Measurement date cannot be in the future.'
            })
        measurement_type = cleaned_data.get('measurement_type')
        value = cleaned_data.get('value')
        if measurement_type and value:
            if measurement_type.min_value and value < measurement_type.min_value:
                self.add_error('value',
                    f'Value is below minimum allowed ({measurement_type.min_value}).')
            if measurement_type.max_value and value > measurement_type.max_value:
                self.add_error('value',
                    f'Value is above maximum allowed ({measurement_type.max_value}).')
        return cleaned_data


class BulkMeasurementForm(RequiredFieldsMixin, BootstrapFormMixin, forms.Form):
    """Form for recording measurements for multiple students. Uses school timezone. ⭐"""

    measurement_session = forms.ModelChoiceField(
        label='Measurement Session', queryset=None, required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Optional: Link to a measurement session'
    )
    academic_session = forms.ModelChoiceField(
        label='Academic Session', queryset=None, required=True,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    measurement_date = forms.DateField(
        label='Measurement Date', required=True, widget=DatePickerInput()
    )
    measurement_context = forms.ChoiceField(
        label='Measurement Context',
        choices=StudentMeasurement.MEASUREMENT_CONTEXT_CHOICES,
        required=True, widget=forms.Select(attrs={'class': 'form-select'})
    )
    measurement_method = forms.ChoiceField(
        label='Measurement Method',
        choices=StudentMeasurement.MEASUREMENT_METHOD_CHOICES,
        required=True, widget=forms.Select(attrs={'class': 'form-select'})
    )
    target_class = forms.ModelChoiceField(
        label='Target Class', queryset=None, required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Measure all students in this class'
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.fields['measurement_session'].queryset = MeasurementSession.objects.filter(
                status__in=['PLANNED', 'IN_PROGRESS']
            ).order_by('-session_date')
            self.fields['academic_session'].queryset = AcademicSession.objects.filter(
                is_active=True
            ).order_by('-start_date')
            self.fields['target_class'].queryset = Class.objects.filter(
                is_active=True
            ).order_by('academic_level__level_order', 'name')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")
        if not self.is_bound:
            from core.utils import get_school_today
            self.fields['measurement_date'].initial = get_school_today()


class StudentMeasurementFilterForm(DateRangeFilterForm):
    """Filter form for student measurements. Uses school timezone. ⭐"""

    q = forms.CharField(
        label='Search', required=False,
        widget=SearchInput(attrs={'placeholder': 'Search by student name...'})
    )
    student = forms.ModelChoiceField(
        label='Student', queryset=None, required=False,
        widget=SelectWithDefault(default_label="All Students")
    )
    measurement_type = forms.ModelChoiceField(
        label='Measurement Type', queryset=None, required=False,
        widget=SelectWithDefault(default_label="All Types")
    )
    academic_session = forms.ModelChoiceField(
        label='Academic Session', queryset=None, required=False,
        widget=SelectWithDefault(default_label="All Sessions")
    )
    measurement_context = forms.ChoiceField(
        label='Context',
        choices=[('', 'All Contexts')] + list(StudentMeasurement.MEASUREMENT_CONTEXT_CHOICES),
        required=False,
        widget=SelectWithDefault(default_label="All Contexts")
    )
    is_verified = forms.NullBooleanField(
        label='Verification', required=False,
        widget=forms.Select(
            choices=[('', 'All'), ('true', 'Verified'), ('false', 'Unverified')],
            attrs={'class': 'form-select'}
        )
    )
    measurement_date_from = forms.DateField(
        label='Date From', required=False, widget=DatePickerInput()
    )
    measurement_date_to = forms.DateField(
        label='Date To', required=False, widget=DatePickerInput()
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.fields['student'].queryset = Student.objects.filter(
                enrollment_status='ACTIVE'
            ).order_by('first_name', 'last_name')
            self.fields['measurement_type'].queryset = MeasurementType.objects.filter(
                is_active=True
            ).order_by('category', 'display_order')
            self.fields['academic_session'].queryset = AcademicSession.objects.filter(
                is_active=True
            ).order_by('-start_date')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")


# =============================================================================
# UNIFORM SIZE FORMS
# =============================================================================

class UniformSizeForm(RequiredFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """Form for creating/editing uniform sizes"""

    class Meta:
        model = UniformSize
        fields = [
            'name', 'code', 'size_type', 'description',
            'min_height', 'max_height', 'min_chest', 'max_chest',
            'min_waist', 'max_waist', 'min_age', 'max_age',
            'display_order', 'is_active'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g., S, M, L, XL, 32, 34'}),
            'code': forms.TextInput(attrs={
                'placeholder': 'e.g., S, M, L, 32',
                'style': 'text-transform: uppercase;'
            }),
            'size_type': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Size description...'}),
            'min_height': forms.NumberInput(attrs={'step': '0.1', 'placeholder': 'Min height (cm)'}),
            'max_height': forms.NumberInput(attrs={'step': '0.1', 'placeholder': 'Max height (cm)'}),
            'min_chest': forms.NumberInput(attrs={'step': '0.1', 'placeholder': 'Min chest (cm)'}),
            'max_chest': forms.NumberInput(attrs={'step': '0.1', 'placeholder': 'Max chest (cm)'}),
            'min_waist': forms.NumberInput(attrs={'step': '0.1', 'placeholder': 'Min waist (cm)'}),
            'max_waist': forms.NumberInput(attrs={'step': '0.1', 'placeholder': 'Max waist (cm)'}),
            'min_age': forms.NumberInput(attrs={'min': '0'}),
            'max_age': forms.NumberInput(attrs={'min': '0'}),
            'display_order': forms.NumberInput(attrs={'min': '1'}),
        }

    def clean_code(self):
        return self.cleaned_data.get('code', '').upper()


class UniformSizeFilterForm(BaseFilterForm):
    """Filter form for uniform sizes"""

    q = forms.CharField(
        label='Search', required=False,
        widget=SearchInput(attrs={'placeholder': 'Search by name, code...'})
    )
    size_type = forms.ChoiceField(
        label='Size Type',
        choices=[('', 'All Types')] + list(UniformSize.SIZE_TYPE_CHOICES),
        required=False,
        widget=SelectWithDefault(default_label="All Types")
    )
    is_active = forms.NullBooleanField(
        label='Status', required=False,
        widget=forms.Select(
            choices=[('', 'All'), ('true', 'Active'), ('false', 'Inactive')],
            attrs={'class': 'form-select'}
        )
    )


# =============================================================================
# UNIFORM ITEM FORMS
# =============================================================================

class UniformItemForm(RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """
    Form for creating/editing uniform items.

    REMOVED FIELDS (no longer on the model):
      barcode, category, subcategory, maximum_stock,
      supplier_name, supplier_contact, supplier_item_code,
      material, care_instructions

    STOCK FIELD BEHAVIOUR:
      Create mode — editable for initial bootstrapping (before any UniformStock
                    records exist for unsized items).
      Edit mode   — always disabled. current_stock is a signal-maintained
                    denormalised cache (Sum of UniformStock.quantity). Writing
                    to it directly causes drift; all changes must go through
                    UniformStock / stock-adjustment views which fire the signal.
    """

    class Meta:
        model = UniformItem
        fields = [
            'name', 'code', 'description', 'item_type', 'gender',
            'requires_sizing', 'available_sizes',
            'unit_of_measure', 'unit_cost', 'selling_price',
            'sku', 'current_stock', 'reorder_level',
            'image', 'color',
            'is_taxable', 'tax_rate',
            'is_active', 'is_mandatory', 'notes',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'e.g., Boys Shirt - White, Sports Shorts'
            }),
            'code': forms.TextInput(attrs={
                'placeholder': 'e.g., UNI-BS-W, SPT-SH-B',
                'style': 'text-transform: uppercase;'
            }),
            'description': forms.Textarea(attrs={
                'rows': 3, 'placeholder': 'Detailed description...'
            }),
            'item_type': forms.Select(attrs={'class': 'form-select'}),
            'gender': forms.Select(attrs={'class': 'form-select'}),
            'available_sizes': forms.SelectMultiple(attrs={
                'class': 'form-select', 'size': '5'
            }),
            'unit_of_measure': forms.Select(attrs={'class': 'form-select'}),
            'unit_cost': MoneyInput(),
            'selling_price': MoneyInput(),
            'sku': forms.TextInput(attrs={'placeholder': 'Stock Keeping Unit'}),
            'current_stock': forms.NumberInput(attrs={'min': '0'}),
            'reorder_level': forms.NumberInput(attrs={'min': '0'}),
            'color': forms.TextInput(attrs={'placeholder': 'e.g., White, Blue'}),
            'tax_rate': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={
                'rows': 2, 'placeholder': 'Additional notes...'
            }),
        }

    # ------------------------------------------------------------------
    # Properties set in __init__ and read by the template to avoid
    # duplicating the is_edit_mode logic in multiple places.
    # ------------------------------------------------------------------
    is_edit_mode: bool = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        try:
            self.fields['available_sizes'].queryset = UniformSize.objects.filter(
                is_active=True
            ).order_by('display_order')
            self.fields['unit_of_measure'].queryset = UnitOfMeasure.objects.filter(
                is_active=True, uom_type='QUANTITY'
            ).order_by('name')
            self.fields['tax_rate'].queryset = TaxRate.objects.filter(
                is_active=True
            ).order_by('name')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")

        self.fields['code'].help_text = "Unique item code"
        self.fields['unit_cost'].help_text = "Cost price (for COGS calculation)"
        self.fields['selling_price'].help_text = "Selling price to students"

        # ----------------------------------------------------------------
        # current_stock lock
        #
        # CREATE mode: allow direct entry so staff can set an opening
        #   balance before any UniformStock records have been created.
        #
        # EDIT mode: disable unconditionally.  The field is a
        #   signal-maintained Sum() cache — overwriting it manually causes
        #   the value to drift out of sync the next time any stock record
        #   is saved.  All stock changes must go through UniformStock or
        #   the stock-adjustment views.
        # ----------------------------------------------------------------
        self.is_edit_mode = bool(self.instance and self.instance.pk)

        if self.is_edit_mode:
            self.fields['current_stock'].disabled = True
            self.fields['current_stock'].help_text = (
                "Read-only in edit mode. Use Stock Adjustment to update stock levels."
            )
        else:
            self.fields['current_stock'].help_text = (
                "Opening stock balance. After creation, manage stock via "
                "Stock Adjustment or Purchase Orders."
            )

    def clean_code(self):
        return self.cleaned_data.get('code', '').upper()

    def clean(self):
        cleaned_data = super().clean()
        unit_cost = cleaned_data.get('unit_cost')
        selling_price = cleaned_data.get('selling_price')
        if unit_cost and selling_price and selling_price < unit_cost:
            self.add_error(
                'selling_price',
                'Selling price should typically be higher than unit cost.'
            )
        return cleaned_data


class UniformItemFilterForm(BaseFilterForm):
    """
    Filter form for uniform items.

    REMOVED: category field (no longer on the model — use item_type instead).
    """

    q = forms.CharField(
        label='Search', required=False,
        widget=SearchInput(attrs={'placeholder': 'Search by name, code, SKU...'})
    )
    item_type = forms.ChoiceField(
        label='Item Type',
        choices=[('', 'All Types')] + list(UniformItem.ITEM_TYPE_CHOICES),
        required=False,
        widget=SelectWithDefault(default_label="All Types")
    )
    gender = forms.ChoiceField(
        label='Gender',
        choices=[('', 'All')] + list(UniformItem.GENDER_CHOICES),
        required=False,
        widget=SelectWithDefault(default_label="All")
    )
    stock_status = forms.ChoiceField(
        label='Stock Status',
        choices=[
            ('', 'All'),
            ('in_stock', 'In Stock'),
            ('low_stock', 'Low Stock'),
            ('out_of_stock', 'Out of Stock'),
        ],
        required=False,
        widget=SelectWithDefault(default_label="All")
    )
    is_active = forms.NullBooleanField(
        label='Status', required=False,
        widget=forms.Select(
            choices=[('', 'All'), ('true', 'Active'), ('false', 'Inactive')],
            attrs={'class': 'form-select'}
        )
    )
    is_mandatory = forms.NullBooleanField(
        label='Mandatory', required=False,
        widget=forms.Select(
            choices=[('', 'All'), ('true', 'Mandatory'), ('false', 'Optional')],
            attrs={'class': 'form-select'}
        )
    )


# =============================================================================
# UNIFORM STOCK FORMS
# =============================================================================

class UniformStockForm(RequiredFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """Form for managing uniform stock by size"""

    class Meta:
        model = UniformStock
        fields = [
            'uniform_item', 'size', 'quantity', 'reserved_quantity',
            'location', 'bin_number'
        ]
        widgets = {
            'uniform_item': forms.Select(attrs={'class': 'form-select'}),
            'size': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={'min': '0'}),
            'reserved_quantity': forms.NumberInput(attrs={'min': '0'}),
            'location': forms.TextInput(attrs={'placeholder': 'Storage location'}),
            'bin_number': forms.TextInput(attrs={'placeholder': 'Bin/shelf number'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.fields['uniform_item'].queryset = UniformItem.objects.filter(
                is_active=True
            ).order_by('name')
            self.fields['size'].queryset = UniformSize.objects.filter(
                is_active=True
            ).order_by('display_order')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")

        # Size required-ness is enforced conditionally in clean() below.
        # The JS in form.html hides the field entirely for unsized items.
        self.fields['size'].required = False

    def clean(self):
        cleaned_data = super().clean()
        uniform_item = cleaned_data.get('uniform_item')
        size = cleaned_data.get('size')

        if uniform_item is None:
            return cleaned_data

        if uniform_item.requires_sizing:
            if not size:
                self.add_error('size', 'This item requires a size. Please select one.')
        else:
            # Clear any accidentally submitted size value
            cleaned_data['size'] = None

            # Surface the DB unique constraint as a clean form error
            existing_qs = UniformStock.objects.filter(
                uniform_item=uniform_item, size__isnull=True
            )
            if self.instance and self.instance.pk:
                existing_qs = existing_qs.exclude(pk=self.instance.pk)
            if existing_qs.exists():
                self.add_error(
                    'uniform_item',
                    'A stock record already exists for this item. '
                    'Edit the existing record instead of creating a new one.'
                )
        return cleaned_data


class StockAdjustmentForm(RequiredFieldsMixin, BootstrapFormMixin, forms.Form):
    """Form for adjusting stock levels"""

    ADJUSTMENT_TYPE_CHOICES = [
        ('ADD', 'Add Stock'),
        ('REMOVE', 'Remove Stock'),
        ('SET', 'Set Stock Level'),
    ]

    adjustment_type = forms.ChoiceField(
        label='Adjustment Type', choices=ADJUSTMENT_TYPE_CHOICES, required=True,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    quantity = forms.IntegerField(
        label='Quantity', min_value=0, required=True,
        widget=forms.NumberInput(attrs={'min': '0', 'placeholder': 'Quantity'})
    )
    reason = forms.CharField(
        label='Reason', required=True,
        widget=forms.Textarea(attrs={
            'rows': 3, 'placeholder': 'Reason for stock adjustment...'
        })
    )


# =============================================================================
# UNIFORM PURCHASE ORDER FORMS
# =============================================================================

class UniformPurchaseOrderForm(RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """Form for creating/editing uniform purchase orders. Uses school timezone. ⭐"""

    class Meta:
        model = UniformPurchaseOrder
        fields = [
            'supplier_name', 'supplier_contact', 'supplier_email', 'supplier_phone',
            'order_date', 'expected_delivery_date', 'fiscal_period',
            'shipping_cost', 'payment_terms',
            'auto_create_journal_entry', 'notes'
        ]
        widgets = {
            'supplier_name': forms.TextInput(attrs={'placeholder': 'Supplier name'}),
            'supplier_contact': forms.TextInput(attrs={'placeholder': 'Contact person'}),
            'supplier_email': forms.EmailInput(attrs={'placeholder': 'email@example.com'}),
            'supplier_phone': forms.TextInput(attrs={'placeholder': '+256700000000'}),
            'order_date': DatePickerInput(),
            'expected_delivery_date': DatePickerInput(),
            'fiscal_period': forms.Select(attrs={'class': 'form-select'}),
            'shipping_cost': MoneyInput(),
            'payment_terms': forms.TextInput(attrs={
                'placeholder': 'e.g., Net 30, Payment on Delivery'
            }),
            'notes': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Additional notes...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.fields['fiscal_period'].queryset = FiscalPeriod.objects.filter(
                is_active=True,
                is_closed=False,
            ).order_by('-start_date')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")
        if not self.is_bound:
            from core.utils import get_school_today
            self.fields['order_date'].initial = get_school_today()

    def clean(self):
        cleaned_data = super().clean()
        order_date = cleaned_data.get('order_date')
        expected_delivery_date = cleaned_data.get('expected_delivery_date')
        from core.utils import get_school_today
        today = get_school_today()
        if order_date and order_date > today:
            raise ValidationError({'order_date': 'Order date cannot be in the future.'})
        if order_date and expected_delivery_date and expected_delivery_date < order_date:
            raise ValidationError({
                'expected_delivery_date': 'Expected delivery date cannot be before order date.'
            })
        return cleaned_data


class UniformPurchaseOrderItemForm(RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """Form for purchase order items (inline formset use)"""

    class Meta:
        model = UniformPurchaseOrderItem
        fields = ['uniform_item', 'size', 'quantity_ordered', 'unit_price', 'notes']
        widgets = {
            'uniform_item': forms.Select(attrs={'class': 'form-select'}),
            'size': forms.Select(attrs={'class': 'form-select'}),
            'quantity_ordered': forms.NumberInput(attrs={'min': '1'}),
            'unit_price': MoneyInput(),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.fields['uniform_item'].queryset = UniformItem.objects.filter(
                is_active=True
            ).order_by('name')
            self.fields['size'].queryset = UniformSize.objects.filter(
                is_active=True
            ).order_by('display_order')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")


class UniformPurchaseOrderFilterForm(DateRangeFilterForm):
    """Filter form for purchase orders. Uses school timezone. ⭐"""

    q = forms.CharField(
        label='Search', required=False,
        widget=SearchInput(attrs={'placeholder': 'Search by PO number, supplier...'})
    )
    status = forms.ChoiceField(
        label='Status',
        choices=[('', 'All Statuses')] + list(UniformPurchaseOrder.STATUS_CHOICES),
        required=False,
        widget=SelectWithDefault(default_label="All Statuses")
    )
    fiscal_period = forms.ModelChoiceField(
        label='Fiscal Period', queryset=None, required=False,
        widget=SelectWithDefault(default_label="All Periods")
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
            logger.error(f"Error setting querysets: {e}")


# =============================================================================
# UNIFORM SALE FORMS
# =============================================================================

class UniformSaleForm(RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """
    Form for creating/editing uniform sales. Uses school timezone. ⭐

    NOTE: fiscal_period is auto-assigned by the pre_save signal.
    NOTE: academic_session is a property derived from fiscal_period.
    NOTE: auto_create_invoice / auto_create_journal_entry are always True
          and are not exposed in the form.
    """

    class Meta:
        model = UniformSale
        fields = [
            'student', 'sale_type', 'sale_date',
            'discount_amount', 'discount_reason',
            'payment_method', 'payment_reference',
            'return_date', 'notes'
        ]
        widgets = {
            'student': forms.Select(attrs={
                'class': 'form-select', 'data-placeholder': 'Select student...'
            }),
            'sale_type': forms.Select(attrs={'class': 'form-select'}),
            'sale_date': DatePickerInput(),
            'discount_amount': MoneyInput(),
            'discount_reason': forms.TextInput(attrs={
                'placeholder': 'Reason for discount (if applicable)...'
            }),
            'payment_method': forms.Select(attrs={'class': 'form-select'}),
            'payment_reference': forms.TextInput(attrs={'placeholder': 'Payment reference'}),
            'return_date': DatePickerInput(),
            'notes': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Additional notes...'}),
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
            self.fields['payment_method'].queryset = PaymentMethod.objects.filter(
                is_active=True
            ).order_by('name')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")
        if not self.is_bound:
            from core.utils import get_school_today
            self.fields['sale_date'].initial = get_school_today()

    def clean(self):
        cleaned_data = super().clean()
        sale_date = cleaned_data.get('sale_date')
        from core.utils import get_school_today
        today = get_school_today()
        if sale_date and sale_date > today:
            raise ValidationError({'sale_date': 'Sale date cannot be in the future.'})
        sale_type = cleaned_data.get('sale_type')
        return_date = cleaned_data.get('return_date')
        if sale_type == 'LOAN' and not return_date:
            self.add_error('return_date', 'Return date is required for loaned items.')
        if sale_date and return_date and return_date < sale_date:
            raise ValidationError({
                'return_date': 'Return date cannot be before sale date.'
            })
        return cleaned_data


class UniformSaleItemForm(RequiredFieldsMixin, MoneyFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """Form for uniform sale items (inline formset use)"""

    class Meta:
        model = UniformSaleItem
        fields = [
            'uniform_item', 'size', 'quantity', 'unit_price', 'unit_cost',
            'tax_rate', 'tax_percentage', 'discount_percentage', 'notes'
        ]
        widgets = {
            'uniform_item': forms.Select(attrs={'class': 'form-select'}),
            'size': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={'min': '1'}),
            'unit_price': MoneyInput(),
            'unit_cost': MoneyInput(),
            'tax_rate': forms.Select(attrs={'class': 'form-select'}),
            'tax_percentage': PercentageInput(),
            'discount_percentage': PercentageInput(),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.fields['uniform_item'].queryset = UniformItem.objects.filter(
                is_active=True
            ).order_by('name')
            self.fields['size'].queryset = UniformSize.objects.filter(
                is_active=True
            ).order_by('display_order')
            self.fields['tax_rate'].queryset = TaxRate.objects.filter(
                is_active=True
            ).order_by('name')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")


class UniformSaleFilterForm(DateRangeFilterForm):
    """
    Filter form for uniform sales. Uses school timezone. ⭐

    NOTE: academic_session filters via fiscal_period__related_academic_session
          in the view — not via a direct field on UniformSale.
    """

    q = forms.CharField(
        label='Search', required=False,
        widget=SearchInput(attrs={'placeholder': 'Search by sale number, student...'})
    )
    academic_session = forms.ModelChoiceField(
        label='Academic Session', queryset=None, required=False,
        widget=SelectWithDefault(default_label="All Sessions")
    )
    fiscal_period = forms.ModelChoiceField(
        label='Fiscal Period', queryset=None, required=False,
        widget=SelectWithDefault(default_label="All Periods")
    )
    sale_type = forms.ChoiceField(
        label='Sale Type',
        choices=[('', 'All Types')] + list(UniformSale.SALE_TYPE_CHOICES),
        required=False,
        widget=SelectWithDefault(default_label="All Types")
    )
    status = forms.ChoiceField(
        label='Status',
        choices=[('', 'All Statuses')] + list(UniformSale.STATUS_CHOICES),
        required=False,
        widget=SelectWithDefault(default_label="All Statuses")
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
            logger.error(f"Error setting querysets: {e}")


# =============================================================================
# MEASUREMENT SESSION FORMS
# =============================================================================

class MeasurementSessionForm(RequiredFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """Form for creating/editing measurement sessions. Uses school timezone. ⭐"""

    class Meta:
        model = MeasurementSession
        fields = [
            'session_name', 'session_type', 'session_date', 'start_time', 'end_time',
            'academic_session', 'target_classes', 'target_students', 'notes'
        ]
        widgets = {
            'session_name': forms.TextInput(attrs={
                'placeholder': 'e.g., Form 1 Annual Measurements 2024'
            }),
            'session_type': forms.Select(attrs={'class': 'form-select'}),
            'session_date': DatePickerInput(),
            'start_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'end_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'academic_session': forms.Select(attrs={'class': 'form-select'}),
            'target_classes': forms.SelectMultiple(attrs={'class': 'form-select', 'size': '5'}),
            'target_students': forms.SelectMultiple(attrs={'class': 'form-select', 'size': '5'}),
            'notes': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Session notes...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.fields['academic_session'].queryset = AcademicSession.objects.filter(
                is_active=True
            ).order_by('-start_date')
            self.fields['target_classes'].queryset = Class.objects.filter(
                is_active=True
            ).order_by('academic_level__level_order', 'name')
            self.fields['target_students'].queryset = Student.objects.filter(
                enrollment_status='ACTIVE'
            ).order_by('first_name', 'last_name')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")
        if not self.is_bound:
            from core.utils import get_school_today
            self.fields['session_date'].initial = get_school_today()
        self.fields['target_classes'].help_text = "Leave empty to measure all students"
        self.fields['target_students'].help_text = "Leave empty if measuring by class"

    def clean(self):
        cleaned_data = super().clean()
        session_date = cleaned_data.get('session_date')
        from core.utils import get_school_today
        today = get_school_today()
        if session_date and session_date < today - timezone.timedelta(days=365):
            self.add_error('session_date',
                'Session date is more than a year in the past. Please verify.')
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        if start_time and end_time and end_time <= start_time:
            raise ValidationError({'end_time': 'End time must be after start time.'})
        return cleaned_data


class MeasurementSessionFilterForm(DateRangeFilterForm):
    """Filter form for measurement sessions. Uses school timezone. ⭐"""

    q = forms.CharField(
        label='Search', required=False,
        widget=SearchInput(attrs={'placeholder': 'Search by session name...'})
    )
    session_type = forms.ChoiceField(
        label='Session Type',
        choices=[('', 'All Types')] + list(MeasurementSession.SESSION_TYPES),
        required=False,
        widget=SelectWithDefault(default_label="All Types")
    )
    academic_session = forms.ModelChoiceField(
        label='Academic Session', queryset=None, required=False,
        widget=SelectWithDefault(default_label="All Sessions")
    )
    status = forms.ChoiceField(
        label='Status',
        choices=[('', 'All Statuses')] + list(MeasurementSession.STATUS_CHOICES),
        required=False,
        widget=SelectWithDefault(default_label="All Statuses")
    )
    session_date_from = forms.DateField(
        label='Session Date From', required=False, widget=DatePickerInput()
    )
    session_date_to = forms.DateField(
        label='Session Date To', required=False, widget=DatePickerInput()
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.fields['academic_session'].queryset = AcademicSession.objects.filter(
                is_active=True
            ).order_by('-start_date')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")


# =============================================================================
# STUDENT UNIFORM SIZE RECOMMENDATION FORM
# =============================================================================

class StudentUniformSizeForm(RequiredFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """Form for student uniform size recommendations. Uses school timezone. ⭐"""

    class Meta:
        model = StudentUniformSize
        fields = [
            'student', 'uniform_item', 'recommended_size', 'academic_session',
            'sizing_method', 'confidence_level', 'recommendation_date',
            'growth_allowance', 'notes'
        ]
        widgets = {
            'student': forms.Select(attrs={
                'class': 'form-select', 'data-placeholder': 'Select student...'
            }),
            'uniform_item': forms.Select(attrs={'class': 'form-select'}),
            'recommended_size': forms.Select(attrs={'class': 'form-select'}),
            'academic_session': forms.Select(attrs={'class': 'form-select'}),
            'sizing_method': forms.Select(attrs={'class': 'form-select'}),
            'confidence_level': forms.Select(attrs={'class': 'form-select'}),
            'recommendation_date': DatePickerInput(),
            'notes': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Additional notes...'}),
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
            self.fields['uniform_item'].queryset = UniformItem.objects.filter(
                is_active=True, requires_sizing=True
            ).order_by('name')
            self.fields['recommended_size'].queryset = UniformSize.objects.filter(
                is_active=True
            ).order_by('display_order')
            self.fields['academic_session'].queryset = AcademicSession.objects.filter(
                is_active=True
            ).order_by('-start_date')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")
        if not self.is_bound:
            from core.utils import get_school_today
            self.fields['recommendation_date'].initial = get_school_today()