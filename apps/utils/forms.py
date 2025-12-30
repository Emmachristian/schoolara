# utils/forms.py

"""
Base form utilities and mixins for consistent form handling across the application.
Provides reusable form components, widgets, and validation helpers.

Updated with school timezone support for all date/time validations.
"""

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal, InvalidOperation
from datetime import date, datetime
import re
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# CUSTOM WIDGETS
# =============================================================================

class DatePickerInput(forms.DateInput):
    """Date picker widget with HTML5 date input"""
    input_type = 'date'
    
    def __init__(self, attrs=None, format=None):
        default_attrs = {'class': 'form-control'}
        if attrs:
            default_attrs.update(attrs)
        super().__init__(attrs=default_attrs, format=format or '%Y-%m-%d')


class DateTimePickerInput(forms.DateTimeInput):
    """DateTime picker widget with HTML5 datetime-local input"""
    input_type = 'datetime-local'
    
    def __init__(self, attrs=None, format=None):
        default_attrs = {'class': 'form-control'}
        if attrs:
            default_attrs.update(attrs)
        super().__init__(attrs=default_attrs, format=format or '%Y-%m-%dT%H:%M')


class MoneyInput(forms.NumberInput):
    """Money input widget with proper formatting"""
    
    def __init__(self, attrs=None):
        default_attrs = {
            'class': 'form-control money-input',
            'step': '0.01',
            'min': '0',
            'placeholder': '0.00'
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(attrs=default_attrs)


class PercentageInput(forms.NumberInput):
    """Percentage input widget"""
    
    def __init__(self, attrs=None):
        default_attrs = {
            'class': 'form-control percentage-input',
            'step': '0.01',
            'min': '0',
            'max': '100',
            'placeholder': '0.00'
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(attrs=default_attrs)


class PhoneInput(forms.TextInput):
    """Phone number input widget"""
    
    def __init__(self, attrs=None):
        default_attrs = {
            'class': 'form-control phone-input',
            'placeholder': '+256700000000',
            'pattern': r'^\+?1?\d{9,15}$'
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(attrs=default_attrs)


class SearchInput(forms.TextInput):
    """Search input widget"""
    
    def __init__(self, attrs=None):
        default_attrs = {
            'class': 'form-control search-input',
            'placeholder': 'Search...',
            'type': 'search',
            'autocomplete': 'off'
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(attrs=default_attrs)


class SelectWithDefault(forms.Select):
    """Select widget with a default "All" option"""
    
    def __init__(self, attrs=None, choices=(), default_label="All"):
        super().__init__(attrs, choices)
        self.default_label = default_label
    
    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        # Prepend default option if not already present
        if context['widget']['optgroups']:
            first_choice = context['widget']['optgroups'][0][1][0]['value']
            if first_choice != '':
                context['widget']['optgroups'].insert(
                    0, 
                    (None, [{'name': name, 'value': '', 'label': self.default_label, 'selected': value == ''}], 0)
                )
        return context


# =============================================================================
# CUSTOM FORM FIELDS
# =============================================================================

class MoneyField(forms.DecimalField):
    """Custom field for money amounts with proper validation"""
    
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('max_digits', 15)
        kwargs.setdefault('decimal_places', 2)
        kwargs.setdefault('min_value', Decimal('0.00'))
        kwargs.setdefault('widget', MoneyInput())
        super().__init__(*args, **kwargs)
    
    def clean(self, value):
        """Clean and validate money value"""
        if value in self.empty_values:
            return super().clean(value)
        
        # Remove currency symbols and commas
        if isinstance(value, str):
            value = re.sub(r'[^\d.-]', '', value)
        
        try:
            value = Decimal(value)
        except (ValueError, InvalidOperation):
            raise ValidationError('Enter a valid amount.')
        
        return super().clean(value)


class PercentageField(forms.DecimalField):
    """Custom field for percentage values"""
    
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('max_digits', 5)
        kwargs.setdefault('decimal_places', 2)
        kwargs.setdefault('min_value', Decimal('0.00'))
        kwargs.setdefault('max_value', Decimal('100.00'))
        kwargs.setdefault('widget', PercentageInput())
        super().__init__(*args, **kwargs)


class PhoneNumberField(forms.CharField):
    """Custom field for phone numbers with validation"""
    
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('max_length', 20)
        kwargs.setdefault('widget', PhoneInput())
        super().__init__(*args, **kwargs)
    
    def clean(self, value):
        """Clean and validate phone number"""
        value = super().clean(value)
        
        if value in self.empty_values:
            return value
        
        # Remove spaces and special characters except +
        cleaned = re.sub(r'[^\d+]', '', value)
        
        # Validate format
        if not re.match(r'^\+?1?\d{9,15}$', cleaned):
            raise ValidationError('Enter a valid phone number.')
        
        return cleaned


# =============================================================================
# FORM MIXINS
# =============================================================================

class BootstrapFormMixin:
    """Mixin to add Bootstrap classes to form fields"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()
    
    def apply_bootstrap_classes(self):
        """Apply Bootstrap classes to all form fields"""
        for field_name, field in self.fields.items():
            # Add form-control class to input fields
            if isinstance(field.widget, (
                forms.TextInput,
                forms.NumberInput,
                forms.EmailInput,
                forms.PasswordInput,
                forms.Textarea,
                forms.Select,
                forms.DateInput,
                forms.DateTimeInput,
                forms.TimeInput,
                forms.URLInput,
            )):
                existing_classes = field.widget.attrs.get('class', '')
                if 'form-control' not in existing_classes:
                    field.widget.attrs['class'] = f"{existing_classes} form-control".strip()
            
            # Add form-check-input class to checkboxes and radios
            elif isinstance(field.widget, (forms.CheckboxInput, forms.RadioSelect)):
                existing_classes = field.widget.attrs.get('class', '')
                if 'form-check-input' not in existing_classes:
                    field.widget.attrs['class'] = f"{existing_classes} form-check-input".strip()
            
            # Add form-select class to select fields
            elif isinstance(field.widget, forms.Select):
                existing_classes = field.widget.attrs.get('class', '')
                if 'form-select' not in existing_classes:
                    field.widget.attrs['class'] = f"{existing_classes} form-select".strip()
            
            # Add placeholder if field has help_text
            if field.help_text and not field.widget.attrs.get('placeholder'):
                if isinstance(field.widget, (forms.TextInput, forms.EmailInput, forms.NumberInput)):
                    field.widget.attrs['placeholder'] = field.help_text


class HTMXFormMixin:
    """
    Mixin to add HTMX attributes to forms.
    
    Usage:
        class MyForm(HTMXFormMixin, BootstrapFormMixin, forms.Form):
            htmx_post = '/api/submit/'
            htmx_target = '#results'
            htmx_swap = 'innerHTML'
    """
    
    htmx_post = None  # URL to post to
    htmx_get = None  # URL to get from
    htmx_target = None  # Target element ID or selector
    htmx_swap = 'innerHTML'  # Swap method
    htmx_trigger = 'submit'  # Trigger event
    htmx_indicator = None  # Loading indicator selector
    htmx_push_url = None  # Whether to push URL to history
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_htmx_attributes()
    
    def apply_htmx_attributes(self):
        """Apply HTMX attributes to form"""
        # Get or create attrs dict
        if not hasattr(self, 'attrs'):
            self.attrs = {}
        
        # Add HTMX post/get
        if self.htmx_post:
            self.attrs['hx-post'] = self.htmx_post
        elif self.htmx_get:
            self.attrs['hx-get'] = self.htmx_get
        
        # Add target
        if self.htmx_target:
            if not self.htmx_target.startswith('#') and not self.htmx_target.startswith('.'):
                self.attrs['hx-target'] = f"#{self.htmx_target}"
            else:
                self.attrs['hx-target'] = self.htmx_target
        
        # Add swap method
        if self.htmx_swap:
            self.attrs['hx-swap'] = self.htmx_swap
        
        # Add trigger if not default submit
        if self.htmx_trigger and self.htmx_trigger != 'submit':
            self.attrs['hx-trigger'] = self.htmx_trigger
        
        # Add loading indicator
        if self.htmx_indicator:
            self.attrs['hx-indicator'] = self.htmx_indicator
        
        # Add URL push
        if self.htmx_push_url is not None:
            self.attrs['hx-push-url'] = 'true' if self.htmx_push_url else 'false'


class HTMXFilterFormMixin:
    """
    Enhanced mixin for HTMX-powered filter/search forms.
    Automatically configures fields for live filtering.
    
    Usage:
        class StudentFilterForm(HTMXFilterFormMixin, BootstrapFormMixin, forms.Form):
            htmx_get = '/students/list/'
            htmx_target = '#student-list'
            search_delay = 300  # ms
    """
    
    htmx_get = None  # URL for GET requests
    htmx_target = '#results'  # Target element
    htmx_swap = 'innerHTML'  # Swap method
    htmx_indicator = '.htmx-indicator'  # Loading indicator
    htmx_push_url = True  # Push URL to history
    search_delay = 500  # Delay in ms for search fields
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.configure_htmx_filters()
    
    def configure_htmx_filters(self):
        """Configure HTMX attributes on all filter fields"""
        for field_name, field in self.fields.items():
            widget_attrs = field.widget.attrs
            
            # Add HTMX attributes
            if self.htmx_get:
                widget_attrs['hx-get'] = self.htmx_get
            
            if self.htmx_target:
                widget_attrs['hx-target'] = self.htmx_target
            
            if self.htmx_swap:
                widget_attrs['hx-swap'] = self.htmx_swap
            
            if self.htmx_indicator:
                widget_attrs['hx-indicator'] = self.htmx_indicator
            
            # Include all form fields in request
            widget_attrs['hx-include'] = '[name]'
            
            # Different triggers for different field types
            if isinstance(field.widget, (forms.TextInput, forms.Textarea, SearchInput)):
                # Text fields: trigger on keyup with delay
                widget_attrs['hx-trigger'] = f'keyup changed delay:{self.search_delay}ms, search'
            elif isinstance(field.widget, forms.Select):
                # Select fields: trigger on change immediately
                widget_attrs['hx-trigger'] = 'change'
            elif isinstance(field.widget, (forms.CheckboxInput, forms.RadioSelect)):
                # Checkboxes/radios: trigger on change
                widget_attrs['hx-trigger'] = 'change'
            elif isinstance(field.widget, (DatePickerInput, forms.DateInput)):
                # Date fields: trigger on change
                widget_attrs['hx-trigger'] = 'change'
            
            # Push URL for better UX
            if self.htmx_push_url:
                widget_attrs['hx-push-url'] = 'true'


class DateRangeFormMixin:
    """
    Mixin for forms with date range fields.
    Uses school timezone for validation. ⭐
    """
    
    def clean(self):
        """Validate date range using school timezone"""
        cleaned_data = super().clean()
        
        start_date = cleaned_data.get('start_date') or cleaned_data.get('date_from')
        end_date = cleaned_data.get('end_date') or cleaned_data.get('date_to')
        
        if start_date and end_date:
            if start_date > end_date:
                raise ValidationError({
                    'end_date': 'End date must be after start date.'
                })
            
            # ⭐ Validate against school timezone "today"
            from core.utils import get_school_today
            today = get_school_today()
            
            # Optional: Check if dates are reasonable (not too far in past/future)
            # Can be enabled per form by setting validate_reasonable_dates = True
            if getattr(self, 'validate_reasonable_dates', False):
                from datetime import timedelta
                
                # Warn if start date is more than 10 years in the past
                if start_date < today - timedelta(days=3650):
                    self.add_error('start_date', 'Start date seems unusually far in the past.')
                
                # Warn if end date is more than 5 years in the future
                if end_date > today + timedelta(days=1825):
                    self.add_error('end_date', 'End date seems unusually far in the future.')
        
        return cleaned_data


class MoneyFieldsMixin:
    """Mixin for forms with money fields to ensure proper formatting"""
    
    def clean(self):
        """Clean money fields"""
        cleaned_data = super().clean()
        
        # Find all money fields
        for field_name, field in self.fields.items():
            if isinstance(field, (forms.DecimalField, MoneyField)):
                value = cleaned_data.get(field_name)
                if value is not None:
                    # Ensure it's a Decimal
                    if not isinstance(value, Decimal):
                        try:
                            cleaned_data[field_name] = Decimal(str(value))
                        except (ValueError, InvalidOperation):
                            self.add_error(field_name, 'Invalid amount.')
        
        return cleaned_data


class RequiredFieldsMixin:
    """Mixin to mark required fields with asterisk in label"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mark_required_fields()
    
    def mark_required_fields(self):
        """Add asterisk to required field labels"""
        for field_name, field in self.fields.items():
            if field.required and field.label:
                if not field.label.endswith(' *'):
                    field.label = f"{field.label} *"


# =============================================================================
# BASE FILTER FORMS
# =============================================================================

class BaseFilterForm(HTMXFilterFormMixin, BootstrapFormMixin, forms.Form):
    """
    Base form for HTMX search/filter forms.
    
    Usage:
        class StudentFilterForm(BaseFilterForm):
            htmx_get = '/students/list/'
            htmx_target = '#student-list'
            
            # Add your filter fields
            grade = forms.ChoiceField(...)
            status = forms.ChoiceField(...)
    """
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput()
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Remove 'q' field if not needed
        if not self.use_search_field:
            self.fields.pop('q', None)
    
    @property
    def use_search_field(self):
        """Override to disable search field"""
        return True


class BaseSearchForm(HTMXFilterFormMixin, BootstrapFormMixin, forms.Form):
    """
    Simpler search-only form.
    
    Usage:
        class StudentSearchForm(BaseSearchForm):
            htmx_get = '/students/search/'
            search_placeholder = 'Search students by name, admission number...'
    """
    
    search_placeholder = 'Search...'
    
    q = forms.CharField(
        label='',
        required=False,
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set placeholder from class attribute
        self.fields['q'].widget.attrs['placeholder'] = self.search_placeholder
        # Hide label
        self.fields['q'].label = ''


# =============================================================================
# DATE RANGE FILTER FORM
# =============================================================================

class DateRangeFilterForm(BaseFilterForm, DateRangeFormMixin):
    """
    Filter form with date range using school timezone. ⭐
    
    Usage:
        class TransactionFilterForm(DateRangeFilterForm):
            htmx_get = '/finance/transactions/list/'
    """
    
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


# =============================================================================
# AMOUNT RANGE FILTER FORM
# =============================================================================

class AmountRangeFilterForm(BaseFilterForm):
    """Filter form with amount range"""
    
    min_amount = MoneyField(
        label='Minimum Amount',
        required=False
    )
    
    max_amount = MoneyField(
        label='Maximum Amount',
        required=False
    )
    
    def clean(self):
        """Validate amount range"""
        cleaned_data = super().clean()
        
        min_amount = cleaned_data.get('min_amount')
        max_amount = cleaned_data.get('max_amount')
        
        if min_amount and max_amount:
            if min_amount > max_amount:
                raise ValidationError({
                    'max_amount': 'Maximum amount must be greater than minimum amount.'
                })
        
        return cleaned_data


# =============================================================================
# VALIDATION HELPERS ⭐ UPDATED WITH SCHOOL TIMEZONE
# =============================================================================

def validate_future_date(value):
    """
    Validate that date is not in the future (uses school timezone). ⭐
    
    Args:
        value: Date to validate
        
    Raises:
        ValidationError: If date is in the future
    """
    from core.utils import get_school_today  # ⭐ USE SCHOOL TIMEZONE
    
    if value > get_school_today():
        raise ValidationError('Date cannot be in the future.')


def validate_past_date(value):
    """
    Validate that date is not in the past (uses school timezone). ⭐
    
    Args:
        value: Date to validate
        
    Raises:
        ValidationError: If date is in the past
    """
    from core.utils import get_school_today  # ⭐ USE SCHOOL TIMEZONE
    
    if value < get_school_today():
        raise ValidationError('Date cannot be in the past.')


def validate_age(date_of_birth, min_age=18, max_age=120):
    """
    Validate age based on date of birth (uses school timezone). ⭐
    
    Args:
        date_of_birth: Date of birth to validate
        min_age: Minimum age requirement
        max_age: Maximum age allowed
        
    Raises:
        ValidationError: If age is outside valid range
    """
    if not date_of_birth:
        return
    
    from core.utils import get_school_today  # ⭐ USE SCHOOL TIMEZONE
    today = get_school_today()
    
    age = today.year - date_of_birth.year - (
        (today.month, today.day) < (date_of_birth.month, date_of_birth.day)
    )
    
    if age < min_age:
        raise ValidationError(f'Must be at least {min_age} years old.')
    
    if age > max_age:
        raise ValidationError(f'Age cannot exceed {max_age} years.')


def validate_date_not_before(value, earliest_date=None, error_message=None):
    """
    Validate that date is not before a specific date (uses school timezone). ⭐
    
    Args:
        value: Date to validate
        earliest_date: Earliest allowed date (defaults to school's today)
        error_message: Custom error message
        
    Raises:
        ValidationError: If date is before earliest_date
    """
    from core.utils import get_school_today  # ⭐ USE SCHOOL TIMEZONE
    
    if earliest_date is None:
        earliest_date = get_school_today()
    
    if value < earliest_date:
        if error_message:
            raise ValidationError(error_message)
        else:
            raise ValidationError(f'Date cannot be before {earliest_date}.')


def validate_date_not_after(value, latest_date=None, error_message=None):
    """
    Validate that date is not after a specific date (uses school timezone). ⭐
    
    Args:
        value: Date to validate
        latest_date: Latest allowed date (defaults to school's today)
        error_message: Custom error message
        
    Raises:
        ValidationError: If date is after latest_date
    """
    from core.utils import get_school_today  # ⭐ USE SCHOOL TIMEZONE
    
    if latest_date is None:
        latest_date = get_school_today()
    
    if value > latest_date:
        if error_message:
            raise ValidationError(error_message)
        else:
            raise ValidationError(f'Date cannot be after {latest_date}.')


def validate_phone_number(value):
    """Validate phone number format"""
    if not value:
        return
    
    cleaned = re.sub(r'[^\d+]', '', value)
    
    if not re.match(r'^\+?1?\d{9,15}$', cleaned):
        raise ValidationError('Enter a valid phone number.')


def validate_positive_amount(value):
    """Validate that amount is positive"""
    if value is not None and value <= 0:
        raise ValidationError('Amount must be greater than zero.')


def validate_percentage(value):
    """Validate percentage value"""
    if value is not None:
        if value < 0 or value > 100:
            raise ValidationError('Percentage must be between 0 and 100.')


def validate_id_number(value):
    """Validate ID number format (customize based on your country)"""
    if not value:
        return
    
    # Example validation for Uganda National ID (NIN)
    # Format: CMXXXXXXXXXX (CM followed by 12 digits)
    if not re.match(r'^[A-Z]{2}\d{12}$', value.upper()):
        raise ValidationError('Enter a valid ID number.')


def validate_academic_year_format(value):
    """
    Validate academic year format (e.g., '2024', '2024/2025', '2024-2025').
    
    Args:
        value: Academic year string
        
    Raises:
        ValidationError: If format is invalid
    """
    if not value:
        return
    
    # Match patterns like: 2024, 2024/2025, 2024-2025
    if not re.match(r'^\d{4}(/|-\d{4})?$', value):
        raise ValidationError('Enter a valid academic year (e.g., 2024 or 2024/2025).')


# =============================================================================
# FORM HELPERS
# =============================================================================

def get_form_errors_as_dict(form):
    """Convert form errors to a dictionary for JSON responses"""
    errors = {}
    
    for field, error_list in form.errors.items():
        errors[field] = [str(error) for error in error_list]
    
    return errors


def get_form_errors_as_string(form):
    """Convert form errors to a formatted string"""
    error_messages = []
    
    for field, error_list in form.errors.items():
        field_label = form.fields[field].label if field in form.fields else field
        for error in error_list:
            error_messages.append(f"{field_label}: {error}")
    
    return '\n'.join(error_messages)


def get_form_errors_as_html(form):
    """
    Convert form errors to HTML for HTMX responses.
    
    Returns:
        str: HTML string with Bootstrap alert styling
    """
    if not form.errors:
        return ''
    
    error_html = '<div class="alert alert-danger alert-dismissible fade show" role="alert">'
    error_html += '<strong>Please correct the following errors:</strong><ul class="mb-0 mt-2">'
    
    for field, error_list in form.errors.items():
        field_label = form.fields[field].label if field in form.fields else field
        for error in error_list:
            error_html += f'<li>{field_label}: {error}</li>'
    
    error_html += '</ul>'
    error_html += '<button type="button" class="btn-close" data-bs-dismiss="alert"></button>'
    error_html += '</div>'
    
    return error_html


def set_form_field_order(form, field_order):
    """Reorder form fields"""
    if not field_order:
        return form
    
    fields = form.fields
    ordered_fields = {}
    
    for field_name in field_order:
        if field_name in fields:
            ordered_fields[field_name] = fields[field_name]
    
    # Add remaining fields
    for field_name, field in fields.items():
        if field_name not in ordered_fields:
            ordered_fields[field_name] = field
    
    form.fields = ordered_fields
    return form


def disable_form_fields(form, field_names):
    """Disable specific form fields"""
    for field_name in field_names:
        if field_name in form.fields:
            form.fields[field_name].widget.attrs['disabled'] = 'disabled'
            form.fields[field_name].required = False


def make_fields_readonly(form, field_names):
    """Make specific form fields readonly"""
    for field_name in field_names:
        if field_name in form.fields:
            form.fields[field_name].widget.attrs['readonly'] = 'readonly'


def add_field_css_class(form, field_name, css_class):
    """Add CSS class to a specific field"""
    if field_name in form.fields:
        existing = form.fields[field_name].widget.attrs.get('class', '')
        form.fields[field_name].widget.attrs['class'] = f"{existing} {css_class}".strip()


# =============================================================================
# FORMSET HELPERS
# =============================================================================

def create_formset_with_initial(formset_class, queryset=None, initial_data=None, extra=1):
    """Create a formset with initial data"""
    if queryset is not None:
        formset = formset_class(queryset=queryset)
    elif initial_data is not None:
        formset = formset_class(initial=initial_data)
    else:
        formset = formset_class()
    
    formset.extra = extra
    return formset


def get_formset_errors(formset):
    """Get all errors from a formset"""
    errors = []
    
    # Non-form errors
    if formset.non_form_errors():
        errors.extend(formset.non_form_errors())
    
    # Form errors
    for i, form in enumerate(formset):
        if form.errors:
            for field, error_list in form.errors.items():
                for error in error_list:
                    errors.append(f"Form {i+1} - {field}: {error}")
    
    return errors


def get_formset_errors_as_html(formset):
    """Get formset errors as HTML"""
    errors = get_formset_errors(formset)
    if not errors:
        return ''
    
    error_html = '<div class="alert alert-danger alert-dismissible fade show" role="alert">'
    error_html += '<strong>Please correct the following errors:</strong><ul class="mb-0 mt-2">'
    
    for error in errors:
        error_html += f'<li>{error}</li>'
    
    error_html += '</ul>'
    error_html += '<button type="button" class="btn-close" data-bs-dismiss="alert"></button>'
    error_html += '</div>'
    
    return error_html


# =============================================================================
# COMMON FORM PATTERNS
# =============================================================================

class ConfirmationForm(BootstrapFormMixin, forms.Form):
    """Simple confirmation form"""
    
    confirm = forms.BooleanField(
        label='I confirm this action',
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    reason = forms.CharField(
        label='Reason (optional)',
        required=False,
        widget=forms.Textarea(attrs={'rows': 3})
    )


class CommentForm(BootstrapFormMixin, forms.Form):
    """Simple comment/notes form"""
    
    comment = forms.CharField(
        label='Comment',
        required=True,
        widget=forms.Textarea(attrs={'rows': 4, 'placeholder': 'Enter your comment...'})
    )


class ApprovalForm(BootstrapFormMixin, forms.Form):
    """Approval form with approve/reject options"""
    
    DECISION_CHOICES = [
        ('', '-- Select Decision --'),
        ('APPROVE', 'Approve'),
        ('REJECT', 'Reject'),
    ]
    
    decision = forms.ChoiceField(
        label='Decision',
        choices=DECISION_CHOICES,
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    notes = forms.CharField(
        label='Notes',
        required=False,
        widget=forms.Textarea(attrs={'rows': 3})
    )
    
    def clean_decision(self):
        """Ensure a decision is selected"""
        decision = self.cleaned_data.get('decision')
        if not decision:
            raise ValidationError('Please select a decision.')
        return decision


class DateRangeForm(BootstrapFormMixin, DateRangeFormMixin, forms.Form):
    """
    Standalone date range form (uses school timezone). ⭐
    
    Usage:
        form = DateRangeForm(request.GET)
        if form.is_valid():
            start = form.cleaned_data['start_date']
            end = form.cleaned_data['end_date']
    """
    
    start_date = forms.DateField(
        label='Start Date',
        required=True,
        widget=DatePickerInput()
    )
    
    end_date = forms.DateField(
        label='End Date',
        required=True,
        widget=DatePickerInput()
    )


class BulkActionForm(BootstrapFormMixin, forms.Form):
    """
    Form for bulk actions on selected items.
    
    Usage:
        class StudentBulkActionForm(BulkActionForm):
            ACTION_CHOICES = [
                ('promote', 'Promote to next grade'),
                ('graduate', 'Mark as graduated'),
                ('suspend', 'Suspend students'),
            ]
    """
    
    ACTION_CHOICES = [
        ('', '-- Select Action --'),
    ]
    
    action = forms.ChoiceField(
        label='Action',
        choices=ACTION_CHOICES,
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    selected_ids = forms.CharField(
        widget=forms.HiddenInput(),
        required=True
    )
    
    confirm = forms.BooleanField(
        label='I confirm this bulk action',
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    def clean_selected_ids(self):
        """Parse selected IDs"""
        ids_str = self.cleaned_data.get('selected_ids', '')
        if not ids_str:
            raise ValidationError('No items selected.')
        
        try:
            ids = [id.strip() for id in ids_str.split(',') if id.strip()]
            if not ids:
                raise ValidationError('No valid items selected.')
            return ids
        except Exception:
            raise ValidationError('Invalid selection format.')