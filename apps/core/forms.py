# core/forms.py

"""
Core configuration forms for School Management System.
All date validations use school timezone for consistency.

Includes forms for:
- SchoolConfiguration (term system, timezone, naming conventions)
- FinancialSettings (currency, payment terms, workflows)
- Account Mappings (core, revenue, payroll, expense, special)
- FiscalYear (academic year management)
- FiscalPeriod (financial periods)
- PaymentMethod (payment configurations)
- TaxRate (tax configurations)
- UnitOfMeasure (measurement units)
"""

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal, InvalidOperation
from datetime import date, timedelta
import logging
import json
import re

# Import base form utilities with timezone support ⭐
from utils.forms import (
    BootstrapFormMixin,
    HTMXFormMixin,
    HTMXFilterFormMixin,
    DateRangeFormMixin,
    RequiredFieldsMixin,
    BaseFilterForm,
    DateRangeFilterForm,
    DatePickerInput,
    SearchInput,
    SelectWithDefault,
    MoneyField,
    MoneyInput,
    PercentageField,
    PercentageInput,
    validate_future_date,  # ⭐ Uses school timezone
    validate_past_date,  # ⭐ Uses school timezone
    validate_percentage,
    validate_positive_amount,
)

from .models import (
    SchoolConfiguration,
    FinancialSettings,
    CoreAccountMappings,
    RevenueAccountMappings,
    PayrollAccountMappings,
    ExpenseAccountMappings,
    SpecialAccountMappings,
    FiscalYear,
    FiscalPeriod,
    PaymentMethod,
    TaxRate,
    UnitOfMeasure,
)

logger = logging.getLogger(__name__)

# =============================================================================
# SCHOOL CONFIGURATION FORM
# =============================================================================

# =============================================================================
# SCHOOL CONFIGURATION FORM
# =============================================================================

class SchoolConfigurationForm(BootstrapFormMixin, RequiredFieldsMixin, forms.ModelForm):
    """
    Form for school-wide configuration settings.
    Handles term system, timezone, and naming conventions.
    
    Features:
    - Dynamic timezone choices with popular options first
    - Auto-calculated fields based on term system
    - Smart placeholder generation for JSON fields
    - Comprehensive validation with detailed error messages
    - Pure JavaScript interactions (no HTMX conflicts)
    """
    
    class Meta:
        model = SchoolConfiguration
        fields = [
            # Term System Configuration
            'term_system',
            'periods_per_year',
            
            # Period Naming
            'period_naming_convention',
            'custom_period_names',
            
            # Academic Year Configuration
            'academic_year_type',
            'academic_year_start_month',
            'academic_year_start_day',
            
            # Timezone Configuration ⭐
            'operational_timezone',
            
            # Regional Seasons
            'regional_season_type',
            'custom_season_names',
            
            # Academic Period Settings
            'default_period_duration_weeks',
            
            # Communication
            'enable_automatic_reminders',
            'enable_sms',
            'enable_email_notifications',
        ]
        
        widgets = {
            # ================================================================
            # TERM SYSTEM - NO HTMX (JavaScript handles updates)
            # ================================================================
            'term_system': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_term_system'
            }),
            'periods_per_year': forms.NumberInput(attrs={
                'min': '1',
                'max': '20',
                'class': 'form-control',
                'id': 'id_periods_per_year'
            }),
            
            # ================================================================
            # PERIOD NAMING - NO HTMX (JavaScript handles updates)
            # ================================================================
            'period_naming_convention': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_period_naming_convention'
            }),
            'custom_period_names': forms.Textarea(attrs={
                'rows': 6,
                'class': 'form-control font-monospace',
                'id': 'id_custom_period_names',
                'placeholder': '{\n  "1": "First Term",\n  "2": "Second Term",\n  "3": "Third Term"\n}'
            }),
            
            # ================================================================
            # ACADEMIC YEAR
            # ================================================================
            'academic_year_type': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_academic_year_type'
            }),
            'academic_year_start_month': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_academic_year_start_month'
            }),
            'academic_year_start_day': forms.NumberInput(attrs={
                'min': '1',
                'max': '31',
                'class': 'form-control',
                'id': 'id_academic_year_start_day'
            }),
            
            # ================================================================
            # TIMEZONE ⭐ Enhanced
            # ================================================================
            'operational_timezone': forms.Select(attrs={
                'class': 'form-select select2',
                'id': 'id_operational_timezone',
                'data-placeholder': 'Select timezone...'
            }),
            
            # ================================================================
            # REGIONAL SEASONS
            # ================================================================
            'regional_season_type': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_regional_season_type'
            }),
            'custom_season_names': forms.Textarea(attrs={
                'rows': 4,
                'class': 'form-control font-monospace',
                'id': 'id_custom_season_names',
                'placeholder': '{\n  "1": "Rainy Season",\n  "2": "Dry Season"\n}'
            }),
            
            # ================================================================
            # ACADEMIC PERIOD SETTINGS
            # ================================================================
            'default_period_duration_weeks': forms.NumberInput(attrs={
                'min': '1',
                'max': '52',
                'class': 'form-control',
                'id': 'id_default_period_duration_weeks'
            }),
            
            # ================================================================
            # COMMUNICATION SETTINGS
            # ================================================================
            'enable_automatic_reminders': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'id': 'id_enable_automatic_reminders'
            }),
            'enable_sms': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'id': 'id_enable_sms'
            }),
            'enable_email_notifications': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'id': 'id_enable_email_notifications'
            }),
        }
        
        # ⭐ ENHANCED: More detailed, context-specific help text
        help_texts = {
            'term_system': 'Choose the academic period system used by your school. This affects how terms/semesters are named and counted.',
            'periods_per_year': 'Will be auto-set based on term system (editable for custom systems)',
            'period_naming_convention': 'How academic periods should be named throughout the system',
            'custom_period_names': 'JSON format: {"1": "Name 1", "2": "Name 2", ...}. Required only when using custom naming convention.',
            'academic_year_type': 'When your academic year typically runs (affects default period scheduling)',
            'academic_year_start_month': 'Month when academic year typically starts',
            'academic_year_start_day': 'Day of month when academic year typically starts',
            'operational_timezone': 'Critical for: fee due dates, exam schedules, attendance marking, report generation, and all date-based business logic. Usually set to your school\'s location.',
            'regional_season_type': 'Climate-based season naming for your region (affects seasonal naming conventions)',
            'custom_season_names': 'JSON format: {"1": "Season 1", "2": "Season 2", ...}. Used when regional season type is "Custom".',
            'default_period_duration_weeks': 'Typical duration of each academic period in weeks (used as suggestion when creating sessions)',
            'enable_automatic_reminders': 'Send automatic payment and deadline reminders to parents and students',
            'enable_sms': 'Enable SMS notifications for important updates (requires SMS gateway configuration)',
            'enable_email_notifications': 'Send email notifications for academic and financial events',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # ⭐ ENHANCED: Popular timezones first for better UX
        from zoneinfo import available_timezones
        
        # Popular East African timezones at the top
        popular_timezones = [
            ('Africa/Kampala', 'Africa/Kampala (Uganda - EAT)'),
            ('Africa/Nairobi', 'Africa/Nairobi (Kenya - EAT)'),
            ('Africa/Dar_es_Salaam', 'Africa/Dar_es_Salaam (Tanzania - EAT)'),
            ('Africa/Kigali', 'Africa/Kigali (Rwanda - CAT)'),
            ('Africa/Addis_Ababa', 'Africa/Addis_Ababa (Ethiopia - EAT)'),
            ('Africa/Juba', 'Africa/Juba (South Sudan - CAT)'),
            ('---', '--- All Timezones ---'),
        ]
        
        # Get all available timezones
        all_timezones = [(tz, tz) for tz in sorted(available_timezones())]
        
        # Combine popular with all timezones
        self.fields['operational_timezone'].widget.choices = (
            popular_timezones + all_timezones
        )
        
        # ⭐ ENHANCED: Dynamic placeholder generation based on actual config
        if self.instance and self.instance.pk:
            # Generate period names example
            periods_count = self.instance.get_period_count()
            period_type = self.instance.get_period_type_name()
            
            period_example = {}
            for i in range(1, min(periods_count + 1, 4)):
                period_example[str(i)] = f"{self._get_ordinal_number(i)} {period_type}"
            
            self.fields['custom_period_names'].widget.attrs['placeholder'] = json.dumps(
                period_example, indent=2
            )
            
            # Generate season names example
            if self.instance.regional_season_type == 'custom_regional':
                season_example = {
                    "1": "First Season",
                    "2": "Second Season"
                }
                self.fields['custom_season_names'].widget.attrs['placeholder'] = json.dumps(
                    season_example, indent=2
                )
            
            # ⭐ ENHANCED: Make auto-calculated fields read-only with clear explanation
            if self.instance.term_system != 'custom':
                self.fields['periods_per_year'].widget.attrs['readonly'] = True
                self.fields['periods_per_year'].widget.attrs['class'] += ' bg-light'
                self.fields['periods_per_year'].help_text = (
                    f'Auto-calculated based on {self.instance.get_term_system_display()}. '
                    'Change term system to "Custom" to edit manually.'
                )
        
        # Make custom fields not required initially
        self.fields['custom_period_names'].required = False
        self.fields['custom_season_names'].required = False
    
    def _get_ordinal_number(self, n):
        """Helper to get ordinal suffix (1st, 2nd, 3rd, etc.)"""
        ordinals = {
            1: '1st', 2: '2nd', 3: '3rd', 4: '4th', 5: '5th',
            6: '6th', 7: '7th', 8: '8th', 9: '9th', 10: '10th',
            11: '11th', 12: '12th'
        }
        return ordinals.get(n, f'{n}th')
    
    # =========================================================================
    # FIELD-SPECIFIC VALIDATION
    # =========================================================================
    
    def clean_periods_per_year(self):
        """
        Validate and auto-set periods_per_year based on term_system.
        ⭐ ENHANCED: Better auto-calculation logic
        """
        periods_per_year = self.cleaned_data.get('periods_per_year')
        term_system = self.cleaned_data.get('term_system')
        
        # Auto-set for non-custom systems
        if term_system and term_system != 'custom':
            system_periods = {
                'term': 3,
                'semester': 2,
                'quarter': 4,
                'trimester': 3,
                'module': 6,
                'block': 4,
                'yearlong': 1,
                'intensive': 10,
            }
            return system_periods.get(term_system, 3)
        
        # For custom systems, validate range
        if not periods_per_year:
            raise ValidationError('Periods per year is required for custom term systems.')
        
        if not (1 <= periods_per_year <= 20):
            raise ValidationError('Periods per year must be between 1 and 20.')
        
        return periods_per_year
    
    def clean_operational_timezone(self):
        """
        Validate timezone string.
        ⭐ ENHANCED: Better validation and error messages
        """
        tz_str = self.cleaned_data.get('operational_timezone')
        
        if not tz_str:
            return 'Africa/Kampala'  # Default for East African schools
        
        # Skip validation for separator
        if tz_str == '---':
            raise ValidationError('Please select a valid timezone from the list.')
        
        # Validate that it's a valid IANA timezone
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo(tz_str)
            return tz_str
        except Exception:
            raise ValidationError(
                f"'{tz_str}' is not a valid timezone identifier. "
                "Please select a timezone from the dropdown list."
            )
    
    def clean_custom_period_names(self):
        """
        Validate and parse custom period names JSON.
        ⭐ ENHANCED: Better validation with specific error messages
        """
        data = self.cleaned_data.get('custom_period_names')
        naming_convention = self.cleaned_data.get('period_naming_convention')
        
        # Only required if using custom naming convention
        if naming_convention != 'custom':
            return {} if data is None else data
        
        # Custom naming requires data
        if not data or (isinstance(data, str) and not data.strip()):
            raise ValidationError(
                'Custom period names are required when using custom naming convention. '
                'Provide a JSON dictionary mapping period numbers to names.'
            )
        
        try:
            # Parse JSON if string
            if isinstance(data, str):
                names = json.loads(data)
            else:
                names = data
            
            # Validate structure
            if not isinstance(names, dict):
                raise ValidationError(
                    'Custom period names must be a JSON object/dictionary. '
                    'Example: {"1": "First Term", "2": "Second Term", "3": "Third Term"}'
                )
            
            # Get expected number of periods
            term_system = self.cleaned_data.get('term_system')
            if term_system == 'custom':
                periods_per_year = self.cleaned_data.get('periods_per_year')
            else:
                periods_per_year = self.instance.get_period_count() if self.instance else 3
            
            if not periods_per_year:
                raise ValidationError('Cannot validate custom names without knowing periods per year.')
            
            # ⭐ ENHANCED: Detailed validation like SACCO
            missing_periods = []
            empty_names = []
            invalid_keys = []
            
            # Check for all required periods
            for i in range(1, periods_per_year + 1):
                key = str(i)
                if key not in names:
                    missing_periods.append(key)
                elif not names[key] or not str(names[key]).strip():
                    empty_names.append(key)
            
            # Check for invalid keys
            for key in names.keys():
                if not key.isdigit() or not (1 <= int(key) <= periods_per_year):
                    invalid_keys.append(key)
            
            # Collect all errors
            errors = []
            if missing_periods:
                errors.append(f'Missing names for period(s): {", ".join(missing_periods)}')
            if empty_names:
                errors.append(f'Empty names for period(s): {", ".join(empty_names)}')
            if invalid_keys:
                errors.append(f'Invalid period number(s): {", ".join(invalid_keys)}')
            
            if errors:
                raise ValidationError(' | '.join(errors))
            
            # Clean up and return
            cleaned_names = {}
            for key, value in names.items():
                if key.isdigit() and 1 <= int(key) <= periods_per_year:
                    cleaned_names[key] = str(value).strip()
            
            return cleaned_names
            
        except json.JSONDecodeError as e:
            raise ValidationError(
                f'Invalid JSON format: {str(e)}. '
                'Expected format: {"1": "Name 1", "2": "Name 2", "3": "Name 3"}'
            )
    
    def clean_custom_season_names(self):
        """
        Validate and parse custom season names JSON.
        ⭐ ENHANCED: Similar validation to custom_period_names
        """
        data = self.cleaned_data.get('custom_season_names')
        season_type = self.cleaned_data.get('regional_season_type')
        
        # Only required if using custom regional seasons
        if season_type != 'custom_regional':
            return {} if data is None else data
        
        # Custom seasons require data
        if not data or (isinstance(data, str) and not data.strip()):
            raise ValidationError(
                'Custom season names are required when using custom regional season type. '
                'Provide a JSON dictionary mapping season numbers to names.'
            )
        
        try:
            # Parse JSON if string
            if isinstance(data, str):
                names = json.loads(data)
            else:
                names = data
            
            # Validate structure
            if not isinstance(names, dict):
                raise ValidationError(
                    'Custom season names must be a JSON object/dictionary. '
                    'Example: {"1": "Wet Season", "2": "Dry Season"}'
                )
            
            # Basic validation - at least one season name
            if not names:
                raise ValidationError('At least one season name is required.')
            
            # Clean up and return
            cleaned_names = {}
            for key, value in names.items():
                if key.isdigit() and value and str(value).strip():
                    cleaned_names[key] = str(value).strip()
            
            if not cleaned_names:
                raise ValidationError('No valid season names provided.')
            
            return cleaned_names
            
        except json.JSONDecodeError as e:
            raise ValidationError(
                f'Invalid JSON format: {str(e)}. '
                'Expected format: {"1": "Season 1", "2": "Season 2"}'
            )
    
    def clean_academic_year_start_day(self):
        """
        Validate start day is valid for the start month.
        ⭐ ENHANCED: Better error messages
        """
        day = self.cleaned_data.get('academic_year_start_day')
        month = self.cleaned_data.get('academic_year_start_month')
        
        if not day:
            return 1
        
        if not (1 <= day <= 31):
            raise ValidationError('Day must be between 1 and 31.')
        
        if month:
            try:
                # Test if date is valid for this month
                from datetime import date
                test_date = date(2024, month, day)  # Use leap year for February
            except ValueError:
                month_names = {
                    1: 'January', 2: 'February', 3: 'March', 4: 'April',
                    5: 'May', 6: 'June', 7: 'July', 8: 'August',
                    9: 'September', 10: 'October', 11: 'November', 12: 'December'
                }
                raise ValidationError(
                    f'Day {day} is not valid for {month_names.get(month, "month")}. '
                    f'Please select a valid day for this month.'
                )
        
        return day
    
    # =========================================================================
    # CROSS-FIELD VALIDATION
    # =========================================================================
    
    def clean(self):
        """
        Cross-field validation.
        ⭐ ENHANCED: More comprehensive validation
        """
        cleaned_data = super().clean()
        
        # Validate academic year start date
        start_month = cleaned_data.get('academic_year_start_month')
        start_day = cleaned_data.get('academic_year_start_day')
        
        if start_month and start_day:
            try:
                from datetime import date
                # Test date validity
                date(2024, start_month, start_day)
            except ValueError:
                self.add_error(
                    'academic_year_start_day',
                    f'Invalid date: Month {start_month} does not have {start_day} days.'
                )
        
        # Validate custom period names count matches periods_per_year
        if cleaned_data.get('period_naming_convention') == 'custom':
            custom_names = cleaned_data.get('custom_period_names', {})
            periods_per_year = cleaned_data.get('periods_per_year')
            
            if custom_names and periods_per_year:
                provided_count = len([k for k in custom_names.keys() if k.isdigit()])
                if provided_count != periods_per_year:
                    self.add_error(
                        'custom_period_names',
                        f'Expected {periods_per_year} period names, but got {provided_count}. '
                        f'Please provide names for all {periods_per_year} periods.'
                    )
        
        # Validate period duration is reasonable
        duration_weeks = cleaned_data.get('default_period_duration_weeks')
        if duration_weeks:
            periods = cleaned_data.get('periods_per_year', 1)
            total_weeks = duration_weeks * periods
            
            if total_weeks > 52:
                self.add_error(
                    'default_period_duration_weeks',
                    f'Period duration of {duration_weeks} weeks × {periods} periods = {total_weeks} weeks, '
                    f'which exceeds 52 weeks in a year. Please adjust the duration.'
                )
        
        return cleaned_data
    
    # =========================================================================
    # SAVE METHOD
    # =========================================================================
    
    def save(self, commit=True):
        """
        Save with singleton pattern enforcement.
        ⭐ ENHANCED: Explicit singleton enforcement
        """
        instance = super().save(commit=False)
        
        # Enforce singleton pattern
        instance.pk = 1
        
        if commit:
            instance.save()
            logger.info(f"School configuration updated")
        
        return instance

# =============================================================================
# FINANCIAL SETTINGS FORM
# =============================================================================

class FinancialSettingsForm(BootstrapFormMixin, RequiredFieldsMixin, forms.ModelForm):
    """
    Comprehensive form for financial settings.
    Handles currency, payment terms, fees, and workflows.
    """
    
    class Meta:
        model = FinancialSettings
        fields = [
            # Currency Configuration
            'school_currency',
            'currency_position',
            'decimal_places',
            'use_thousand_separator',
            
            # Numbering Configuration
            'invoice_prefix',
            'include_year_in_invoice_number',
            'payment_prefix',
            'include_year_in_payment_number',
            'receipt_prefix',
            'expense_prefix',
            'include_year_in_expense_number',
            
            # Payment Settings
            'default_payment_terms_days',
            'late_fee_enabled',
            'late_fee_percentage',
            'grace_period_days',
            'minimum_payment_amount',
            'allow_partial_payments',
            
            # Scholarship & Discount Settings
            'auto_apply_scholarships',
            'scholarship_approval_required',
            'auto_apply_discounts',
            'discount_approval_required',
            'discount_approval_threshold',
            'early_payment_discount_enabled',
            'early_payment_discount_percentage',
            'early_payment_discount_days',
            
            # Workflow Settings
            'expense_approval_required',
            'expense_approval_limit',
            'require_payment_confirmation',
            'require_expense_receipts',
            'require_purchase_orders',
            
            # Communication Settings
            'send_invoice_emails',
            'send_payment_confirmations',
            'send_overdue_reminders',
            'overdue_reminder_days',
            'send_sms_notifications',
            
            # Tax & Accounting
            'include_tax_in_prices',
            'default_tax_rate',
            'multi_currency_enabled',
            'auto_generate_recurring_invoices',
            
            # Aging & Collections
            'bad_debt_write_off_threshold',
            'auto_write_off_days',
        ]
        widgets = {
            'school_currency': forms.Select(attrs={'class': 'form-select select2'}),
            'currency_position': forms.Select(attrs={'class': 'form-select'}),
            'decimal_places': forms.NumberInput(attrs={
                'min': '0',
                'max': '4',
                'class': 'form-control'
            }),
            'invoice_prefix': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'INV'
            }),
            'payment_prefix': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'PMT'
            }),
            'receipt_prefix': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'RCPT'
            }),
            'expense_prefix': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'EXP'
            }),
            'default_payment_terms_days': forms.NumberInput(attrs={
                'min': '1',
                'max': '365',
                'class': 'form-control'
            }),
            'late_fee_percentage': PercentageInput(),
            'grace_period_days': forms.NumberInput(attrs={
                'min': '0',
                'max': '90',
                'class': 'form-control'
            }),
            'minimum_payment_amount': MoneyInput(),
            'discount_approval_threshold': MoneyInput(),
            'early_payment_discount_percentage': PercentageInput(),
            'early_payment_discount_days': forms.NumberInput(attrs={
                'min': '1',
                'max': '90',
                'class': 'form-control'
            }),
            'expense_approval_limit': MoneyInput(),
            'overdue_reminder_days': forms.NumberInput(attrs={
                'min': '1',
                'max': '30',
                'class': 'form-control'
            }),
            'default_tax_rate': PercentageInput(),
            'bad_debt_write_off_threshold': MoneyInput(),
            'auto_write_off_days': forms.NumberInput(attrs={
                'min': '90',
                'class': 'form-control'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set currency choices
        try:
            currency_choices = FinancialSettings.get_currency_choices()
            self.fields['school_currency'].widget.choices = currency_choices
        except Exception as e:
            logger.error(f"Error loading currency choices: {e}")
        
        # Group fields for better organization
        self._add_field_groups()
    
    def _add_field_groups(self):
        """Add CSS classes to group related fields visually"""
        currency_fields = [
            'school_currency', 'currency_position',
            'decimal_places', 'use_thousand_separator'
        ]
        for field in currency_fields:
            if field in self.fields:
                self.fields[field].widget.attrs['data-group'] = 'currency'
    
    def clean_late_fee_percentage(self):
        """Validate late fee percentage"""
        percentage = self.cleaned_data.get('late_fee_percentage')
        if percentage is not None:
            validate_percentage(percentage)
        return percentage
    
    def clean_early_payment_discount_percentage(self):
        """Validate early payment discount percentage"""
        percentage = self.cleaned_data.get('early_payment_discount_percentage')
        if percentage is not None:
            validate_percentage(percentage)
        return percentage
    
    def clean_default_tax_rate(self):
        """Validate tax rate percentage"""
        percentage = self.cleaned_data.get('default_tax_rate')
        if percentage is not None:
            validate_percentage(percentage)
        return percentage
    
    def clean(self):
        """Cross-field validation"""
        cleaned_data = super().clean()
        
        # Validate minimum payment amount is positive
        min_payment = cleaned_data.get('minimum_payment_amount')
        if min_payment is not None:
            validate_positive_amount(min_payment)
        
        # Validate approval threshold is positive
        discount_threshold = cleaned_data.get('discount_approval_threshold')
        if discount_threshold is not None:
            validate_positive_amount(discount_threshold)
        
        # Validate expense limit is positive
        expense_limit = cleaned_data.get('expense_approval_limit')
        if expense_limit is not None:
            validate_positive_amount(expense_limit)
        
        return cleaned_data


class FinancialSettingsQuickForm(BootstrapFormMixin, forms.ModelForm):
    """Quick form for essential financial settings only"""
    
    class Meta:
        model = FinancialSettings
        fields = [
            'school_currency',
            'default_payment_terms_days',
            'late_fee_enabled',
            'late_fee_percentage',
            'allow_partial_payments',
        ]
        widgets = {
            'school_currency': forms.Select(attrs={'class': 'form-select select2'}),
            'default_payment_terms_days': forms.NumberInput(attrs={
                'min': '1',
                'class': 'form-control'
            }),
            'late_fee_percentage': PercentageInput(),
        }


# =============================================================================
# ACCOUNT MAPPINGS FORMS
# =============================================================================

class CoreAccountMappingsForm(BootstrapFormMixin, forms.ModelForm):
    """Form for core account mappings"""
    
    class Meta:
        model = CoreAccountMappings
        fields = [
            # Required fields (The Big 7+)
            'default_bank_account',
            'default_cash_account',
            'student_receivables_account',
            'default_payable_account',
            'default_equity_account',
            'default_revenue_account',
            'default_expense_account',
            'scholarship_discount_account',
            # Optional specialized accounts
            'petty_cash_account',
            'mobile_money_account',
            'boarding_revenue_account',
            'uniform_and_book_sales_account',
            'salaries_account',
            'utilities_account',
            'boarding_expense_account',
        ]
        widgets = {
            # Required ASSET accounts
            'default_bank_account': forms.Select(attrs={
                'class': 'form-select select2',
                'data-placeholder': 'Select Primary Bank Account',
                'required': True
            }),
            'default_cash_account': forms.Select(attrs={
                'class': 'form-select select2',
                'data-placeholder': 'Select Cash on Hand Account',
                'required': True
            }),
            'student_receivables_account': forms.Select(attrs={
                'class': 'form-select select2',
                'data-placeholder': 'Select Student Receivables Account',
                'required': True
            }),
            # Required LIABILITY account
            'default_payable_account': forms.Select(attrs={
                'class': 'form-select select2',
                'data-placeholder': 'Select Accounts Payable Account',
                'required': True
            }),
            # Required EQUITY account
            'default_equity_account': forms.Select(attrs={
                'class': 'form-select select2',
                'data-placeholder': 'Select Capital/Equity Account',
                'required': True
            }),
            # Required REVENUE account
            'default_revenue_account': forms.Select(attrs={
                'class': 'form-select select2',
                'data-placeholder': 'Select Default Revenue Account',
                'required': True
            }),
            # Required EXPENSE accounts
            'default_expense_account': forms.Select(attrs={
                'class': 'form-select select2',
                'data-placeholder': 'Select Default Expense Account',
                'required': True
            }),
            'scholarship_discount_account': forms.Select(attrs={
                'class': 'form-select select2',
                'data-placeholder': 'Select Scholarship/Discount Account',
                'required': True
            }),
            # Optional fields
            'petty_cash_account': forms.Select(attrs={
                'class': 'form-select select2',
                'data-placeholder': 'Select Petty Cash Account (Optional)'
            }),
            'mobile_money_account': forms.Select(attrs={
                'class': 'form-select select2',
                'data-placeholder': 'Select Mobile Money Account (Optional)'
            }),
            'boarding_revenue_account': forms.Select(attrs={
                'class': 'form-select select2',
                'data-placeholder': 'Select Boarding Revenue Account (Optional)'
            }),
            'uniform_and_book_sales_account': forms.Select(attrs={
                'class': 'form-select select2',
                'data-placeholder': 'Select Uniform & Book Sales Account (Optional)'
            }),
            'salaries_account': forms.Select(attrs={
                'class': 'form-select select2',
                'data-placeholder': 'Select Salaries Account (Optional)'
            }),
            'utilities_account': forms.Select(attrs={
                'class': 'form-select select2',
                'data-placeholder': 'Select Utilities Account (Optional)'
            }),
            'boarding_expense_account': forms.Select(attrs={
                'class': 'form-select select2',
                'data-placeholder': 'Select Boarding Expense Account (Optional)'
            }),
        }
        help_texts = {
            'default_bank_account': 'Primary bank account for school operations (Required - ASSET)',
            'default_cash_account': 'Cash on hand account for physical cash (Required - ASSET)',
            'student_receivables_account': 'Accounts Receivable - Students control account (Required - ASSET)',
            'default_payable_account': 'Accounts Payable for vendors and suppliers (Required - LIABILITY)',
            'default_equity_account': 'Capital or Retained Earnings account (Required - EQUITY)',
            'default_revenue_account': 'Default account for all school fees revenue (Required - REVENUE)',
            'default_expense_account': 'Default account for general expenses (Required - EXPENSE)',
            'scholarship_discount_account': 'Account for scholarships and discounts (Required - EXPENSE)',
            'petty_cash_account': 'Separate petty cash account - falls back to default cash if not set',
            'mobile_money_account': 'Mobile money clearing account - falls back to default bank if not set',
            'boarding_revenue_account': 'Separate boarding revenue account - falls back to default revenue if not set',
            'uniform_and_book_sales_account': 'Uniform and book sales revenue - falls back to default revenue if not set',
            'salaries_account': 'Staff salaries expense - falls back to default expense if not set',
            'utilities_account': 'Utilities expenses - falls back to default expense if not set',
            'boarding_expense_account': 'Boarding operational expenses - falls back to default expense if not set',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set querysets for account fields
        try:
            from finance.models import Account
            
            # ✅ FIXED: Changed 'number' to 'account_number'
            # Get accounts by type
            asset_accounts = Account.objects.filter(
                account_type__account_type='ASSET',
                is_active=True
            ).order_by('account_number')  # ✅ Changed from 'number'
            
            liability_accounts = Account.objects.filter(
                account_type__account_type='LIABILITY',
                is_active=True
            ).order_by('account_number')  # ✅ Changed from 'number'
            
            equity_accounts = Account.objects.filter(
                account_type__account_type='EQUITY',
                is_active=True
            ).order_by('account_number')  # ✅ Changed from 'number'
            
            revenue_accounts = Account.objects.filter(
                account_type__account_type='REVENUE',
                is_active=True
            ).order_by('account_number')  # ✅ Changed from 'number'
            
            expense_accounts = Account.objects.filter(
                account_type__account_type='EXPENSE',
                is_active=True
            ).order_by('account_number')  # ✅ Changed from 'number'
            
            # Set querysets for REQUIRED ASSET fields
            self.fields['default_bank_account'].queryset = asset_accounts.filter(
                is_bank_account=True
            ) if asset_accounts.filter(is_bank_account=True).exists() else asset_accounts
            self.fields['default_bank_account'].label = 'Primary Bank Account *'
            
            self.fields['default_cash_account'].queryset = asset_accounts.filter(
                is_cash_account=True
            ) if asset_accounts.filter(is_cash_account=True).exists() else asset_accounts
            self.fields['default_cash_account'].label = 'Cash on Hand Account *'
            
            self.fields['student_receivables_account'].queryset = asset_accounts.filter(
                is_receivable_account=True
            ) if asset_accounts.filter(is_receivable_account=True).exists() else asset_accounts
            self.fields['student_receivables_account'].label = 'Student Receivables Account *'
            
            # Set querysets for REQUIRED LIABILITY field
            self.fields['default_payable_account'].queryset = liability_accounts
            self.fields['default_payable_account'].label = 'Accounts Payable Account *'
            
            # Set querysets for REQUIRED EQUITY field
            self.fields['default_equity_account'].queryset = equity_accounts
            self.fields['default_equity_account'].label = 'Capital/Equity Account *'
            
            # Set querysets for REQUIRED REVENUE field
            self.fields['default_revenue_account'].queryset = revenue_accounts
            self.fields['default_revenue_account'].label = 'Default Revenue Account *'
            
            # Set querysets for REQUIRED EXPENSE fields
            self.fields['default_expense_account'].queryset = expense_accounts
            self.fields['default_expense_account'].label = 'Default Expense Account *'
            
            self.fields['scholarship_discount_account'].queryset = expense_accounts
            self.fields['scholarship_discount_account'].label = 'Scholarship/Discount Account *'
            
            # Set querysets for OPTIONAL fields
            self.fields['petty_cash_account'].queryset = asset_accounts.filter(
                is_cash_account=True
            ) if asset_accounts.filter(is_cash_account=True).exists() else asset_accounts
            self.fields['petty_cash_account'].required = False
            self.fields['petty_cash_account'].label = 'Petty Cash Account (Optional)'
            
            self.fields['mobile_money_account'].queryset = asset_accounts
            self.fields['mobile_money_account'].required = False
            self.fields['mobile_money_account'].label = 'Mobile Money Account (Optional)'
            
            self.fields['boarding_revenue_account'].queryset = revenue_accounts
            self.fields['boarding_revenue_account'].required = False
            self.fields['boarding_revenue_account'].label = 'Boarding Revenue Account (Optional)'
            
            self.fields['uniform_and_book_sales_account'].queryset = revenue_accounts
            self.fields['uniform_and_book_sales_account'].required = False
            self.fields['uniform_and_book_sales_account'].label = 'Uniform & Book Sales Account (Optional)'
            
            self.fields['salaries_account'].queryset = expense_accounts
            self.fields['salaries_account'].required = False
            self.fields['salaries_account'].label = 'Salaries Account (Optional)'
            
            self.fields['utilities_account'].queryset = expense_accounts
            self.fields['utilities_account'].required = False
            self.fields['utilities_account'].label = 'Utilities Account (Optional)'
            
            self.fields['boarding_expense_account'].queryset = expense_accounts
            self.fields['boarding_expense_account'].required = False
            self.fields['boarding_expense_account'].label = 'Boarding Expense Account (Optional)'
            
        except ImportError:
            logger.warning("Finance app not available - account mappings disabled")
        except Exception as e:
            logger.error(f"Error setting up account mappings form: {e}")
    
    def clean(self):
        """Additional validation"""
        cleaned_data = super().clean()
        
        # Validate that all required fields are set
        required_fields = [
            'default_bank_account',
            'default_cash_account',
            'student_receivables_account',
            'default_payable_account',
            'default_equity_account',
            'default_revenue_account',
            'default_expense_account',
            'scholarship_discount_account'
        ]
        
        for field in required_fields:
            if not cleaned_data.get(field):
                self.add_error(field, f'This field is required.')
        
        # Validate that bank and cash accounts are different
        bank_account = cleaned_data.get('default_bank_account')
        cash_account = cleaned_data.get('default_cash_account')
        
        if bank_account and cash_account and bank_account == cash_account:
            self.add_error('default_cash_account', 
                'Cash account must be different from bank account. Use separate accounts for cash and bank.')
        
        # Validate account types (defensive check)
        if bank_account and bank_account.account_type.account_type != 'ASSET':
            self.add_error('default_bank_account', 'Must be an ASSET account.')
        
        if cash_account and cash_account.account_type.account_type != 'ASSET':
            self.add_error('default_cash_account', 'Must be an ASSET account.')
        
        receivables = cleaned_data.get('student_receivables_account')
        if receivables and receivables.account_type.account_type != 'ASSET':
            self.add_error('student_receivables_account', 'Must be an ASSET account.')
        
        payable = cleaned_data.get('default_payable_account')
        if payable and payable.account_type.account_type != 'LIABILITY':
            self.add_error('default_payable_account', 'Must be a LIABILITY account.')
        
        equity = cleaned_data.get('default_equity_account')
        if equity and equity.account_type.account_type != 'EQUITY':
            self.add_error('default_equity_account', 'Must be an EQUITY account.')
        
        revenue = cleaned_data.get('default_revenue_account')
        if revenue and revenue.account_type.account_type != 'REVENUE':
            self.add_error('default_revenue_account', 'Must be a REVENUE account.')
        
        expense = cleaned_data.get('default_expense_account')
        if expense and expense.account_type.account_type != 'EXPENSE':
            self.add_error('default_expense_account', 'Must be an EXPENSE account.')
        
        scholarship = cleaned_data.get('scholarship_discount_account')
        if scholarship and scholarship.account_type.account_type != 'EXPENSE':
            self.add_error('scholarship_discount_account', 'Must be an EXPENSE account.')
        
        return cleaned_data

class RevenueAccountMappingsForm(BootstrapFormMixin, forms.ModelForm):
    """Form for revenue account mappings"""
    
    class Meta:
        model = RevenueAccountMappings
        fields = [
            'uniform_sales_revenue_account',
            'textbook_sales_revenue_account',
            'transport_revenue_account',
            'boarding_revenue_account',
            'meals_revenue_account',
            'late_fee_revenue_account',
            'penalty_revenue_account',
            'donation_revenue_account',
            'grant_revenue_account',
        ]


class PayrollAccountMappingsForm(BootstrapFormMixin, forms.ModelForm):
    """Form for payroll account mappings"""
    
    class Meta:
        model = PayrollAccountMappings
        fields = [
            'salaries_expense_account',
            'wages_payable_account',
            'payroll_tax_payable_account',
            'social_security_payable_account',
            'pension_payable_account',
            'housing_allowance_expense_account',
            'transport_allowance_expense_account',
            'medical_allowance_expense_account',
            'general_allowance_expense_account',
            'overtime_expense_account',
            'bonus_expense_account',
            'commission_expense_account',
            'staff_benefits_expense_account',
            'staff_insurance_expense_account',
            'staff_pension_contribution_expense_account',
        ]


class ExpenseAccountMappingsForm(BootstrapFormMixin, forms.ModelForm):
    """Form for expense account mappings"""
    
    class Meta:
        model = ExpenseAccountMappings
        fields = [
            'default_inventory_account',
            'default_cogs_account',
            'supplies_expense_account',
            'utilities_expense_account',
            'maintenance_expense_account',
            'fixed_assets_account',
            'accumulated_depreciation_account',
            'depreciation_expense_account',
        ]


class SpecialAccountMappingsForm(BootstrapFormMixin, forms.ModelForm):
    """Form for special account mappings"""
    
    class Meta:
        model = SpecialAccountMappings
        fields = [
            'default_student_deposit_account',
            'student_credit_balance_account',
            'unearned_revenue_account',
            'mobile_money_clearing_account',
            'payment_processing_fee_account',
            'default_refund_account',
            'bad_debt_expense_account',
            'allowance_for_doubtful_accounts',
            'default_rounding_account',
            'default_currency_gain_account',
            'default_currency_loss_account',
            'withholding_tax_payable_account',
            'petty_cash_account',
            'suspense_account',
            'bank_reconciliation_account',
            'staff_loan_receivable_account',
            'staff_advance_account',
            'recruitment_expense_account',
            'staff_training_expense_account',
            'severance_expense_account',
            'gratuity_payable_account',
        ]


# =============================================================================
# FISCAL YEAR FORMS
# =============================================================================

class FiscalYearForm(BootstrapFormMixin, RequiredFieldsMixin, forms.ModelForm):
    """
    Form for creating/editing fiscal years.
    Uses school timezone for date validations. ⭐
    """
    
    class Meta:
        model = FiscalYear
        fields = [
            'name',
            'code',
            'start_date',
            'end_date',
            'is_active',  # Remove 'status' - it's auto-calculated
            'description',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., 2024 or Academic Year 2024-2025'
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., FY2024 or AY2024-25'
            }),
            'start_date': DatePickerInput(),
            'end_date': DatePickerInput(),
            'description': forms.Textarea(attrs={
                'rows': 3,
                'class': 'form-control',
                'placeholder': 'Optional description'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Help text
        self.fields['is_active'].help_text = (
            'Only one fiscal year can be active at a time. '
            'Setting this will deactivate other fiscal years.'
        )
    
    def clean_start_date(self):
        """Validate start date using school timezone ⭐"""
        start_date = self.cleaned_data.get('start_date')
        if start_date:
            from core.utils import get_school_today
            from datetime import timedelta
            
            today = get_school_today()  # ⭐ SCHOOL TIMEZONE
            
            # Allow fiscal years to be created up to 3 years in advance
            max_future = today + timedelta(days=3*365)
            if start_date > max_future:
                raise ValidationError(
                    "Start date cannot be more than 3 years in the future."
                )
        
        return start_date
    
    def clean(self):
        """Validate date range using school timezone ⭐"""
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        
        if start_date and end_date:
            if start_date >= end_date:
                raise ValidationError({
                    'end_date': 'End date must be after start date.'
                })
            
            # Check duration is reasonable (at least 90 days, at most 400 days)
            duration = (end_date - start_date).days
            if duration < 90:
                raise ValidationError(
                    'Fiscal year duration seems too short (less than 90 days). Please verify dates.'
                )
            if duration > 400:
                raise ValidationError(
                    'Fiscal year duration seems too long (more than 400 days). Please verify dates.'
                )
        
        return cleaned_data


class FiscalYearFilterForm(HTMXFilterFormMixin, DateRangeFormMixin, BootstrapFormMixin, forms.Form):
    """
    HTMX-powered fiscal year filter form.
    Uses school timezone for date validations. ⭐
    """
    
    htmx_get = 'core:fiscal_year_search'
    htmx_target = '#fiscal-year-list'
    search_delay = 300
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by name, code...'
        })
    )
    
    status = forms.ChoiceField(
        label='Status',
        choices=[('', 'All Statuses')] + FiscalYear.STATUS_CHOICES,
        required=False,
        widget=SelectWithDefault(default_label="All Statuses")
    )
    
    is_active = forms.NullBooleanField(
        label='Active',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Active'),
            ('false', 'Inactive')
        ], attrs={'class': 'form-select'})
    )
    
    is_closed = forms.NullBooleanField(
        label='Closed',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Closed'),
            ('false', 'Open')
        ], attrs={'class': 'form-select'})
    )
    
    start_date_from = forms.DateField(
        label='Start Date From',
        required=False,
        widget=DatePickerInput()
    )
    
    start_date_to = forms.DateField(
        label='Start Date To',
        required=False,
        widget=DatePickerInput()
    )


# =============================================================================
# FISCAL PERIOD FORMS
# =============================================================================

class FiscalPeriodForm(BootstrapFormMixin, RequiredFieldsMixin, forms.ModelForm):
    """
    Form for creating/editing fiscal periods.
    Uses school timezone for date validations. ⭐
    
    Note: status, is_active, is_closed, is_locked are auto-calculated by the model
    and should not be included in the form.
    """
    
    class Meta:
        model = FiscalPeriod
        fields = [
            'fiscal_year',
            'name',
            'code',
            'period_number',
            'period_type',
            'related_academic_session',
            'start_date',
            'end_date',
            'allow_advance_payments',
            'allow_arrears_payments',
            'allow_invoice_generation',
            'allow_refunds',
            'require_approval_for_transactions',
            'auto_close_date',
            'grace_period_days',
            'description',
            'notes',
        ]
        widgets = {
            'fiscal_year': forms.Select(attrs={'class': 'form-select'}),
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Term 1 2024 Fiscal Period'
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., FP_2024_T1'
            }),
            'period_number': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.1',
                'min': '0.1'
            }),
            'period_type': forms.Select(attrs={'class': 'form-select'}),
            'related_academic_session': forms.Select(attrs={
                'class': 'form-select',
            }),
            'start_date': DatePickerInput(),
            'end_date': DatePickerInput(),
            'auto_close_date': DatePickerInput(),
            'grace_period_days': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0'
            }),
            'description': forms.Textarea(attrs={
                'rows': 3,
                'class': 'form-control'
            }),
            'notes': forms.Textarea(attrs={
                'rows': 2,
                'class': 'form-control',
                'placeholder': 'Internal notes for accounting team'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # ⭐ DEBUG: Log instance state
        logger.info(f"FiscalPeriodForm.__init__ - instance.pk = {self.instance.pk if self.instance else 'No instance'}")
        logger.info(f"FiscalPeriodForm.__init__ - instance._state.adding = {self.instance._state.adding if self.instance else 'No instance'}")
        
        # Set academic session queryset
        try:
            from academics.models import AcademicSession
            self.fields['related_academic_session'].queryset = AcademicSession.objects.all().order_by('-start_date')
            self.fields['related_academic_session'].required = False
            self.fields['related_academic_session'].empty_label = "Select Academic Session (Optional)"
        except Exception as e:
            logger.error(f"Error setting academic session queryset: {e}")
            self.fields['related_academic_session'].widget = forms.HiddenInput()
            self.fields['related_academic_session'].required = False
        
        # Help text
        self.fields['period_number'].help_text = (
            'Sequential number within fiscal year. Use decimals (e.g., 1.5) '
            'for break periods between regular periods.'
        )
        self.fields['grace_period_days'].help_text = (
            'Days beyond end_date when transactions are still accepted'
        )
        
        # ⭐ FIX: Check if instance is saved to database, not just if it has a pk
        # For UUID fields, pk is auto-generated even for unsaved instances
        is_editing = self.instance and self.instance.pk and not self.instance._state.adding
        
        logger.info(f"FiscalPeriodForm.__init__ - is_editing = {is_editing}")
        
        if is_editing:  # Editing existing period
            self.fields['fiscal_year'].disabled = True
            self.fields['fiscal_year'].help_text = (
                'Cannot change fiscal year for existing period. '
                'Create a new period if needed in a different fiscal year.'
            )
            logger.info("Fiscal year field set to DISABLED (editing)")
        else:  # Creating new period
            self.fields['fiscal_year'].disabled = False
            self.fields['fiscal_year'].required = True
            self.fields['fiscal_year'].help_text = (
                'Select the fiscal year for this period.'
            )
            logger.info("Fiscal year field set to ENABLED (creating)")
            
            # ⭐ If we have an initial fiscal_year value, log it
            if self.initial.get('fiscal_year'):
                logger.info(f"Form initialized with fiscal_year: {self.initial['fiscal_year']}")
    
    def clean_start_date(self):
        """Validate start date using school timezone ⭐"""
        start_date = self.cleaned_data.get('start_date')
        if start_date:
            from core.utils import get_school_today
            from datetime import timedelta
            
            today = get_school_today()
            
            # Allow periods to be created up to 2 years in advance
            max_future = today + timedelta(days=2*365)
            if start_date > max_future:
                raise ValidationError(
                    "Start date cannot be more than 2 years in the future."
                )
        
        return start_date
    
    def clean_period_number(self):
        """Validate period number is unique within fiscal year"""
        period_number = self.cleaned_data.get('period_number')
        fiscal_year = self.cleaned_data.get('fiscal_year')
        
        if period_number and fiscal_year:
            existing = FiscalPeriod.objects.filter(
                fiscal_year=fiscal_year,
                period_number=period_number
            )
            
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            
            if existing.exists():
                raise ValidationError(
                    f'Period number {period_number} already exists in {fiscal_year.name}. '
                    f'Use a different number or decimal (e.g., {float(period_number) + 0.5}).'
                )
        
        return period_number
    
    def clean_code(self):
        """Validate code is unique"""
        code = self.cleaned_data.get('code')
        
        if code:
            existing = FiscalPeriod.objects.filter(code=code)
            
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            
            if existing.exists():
                raise ValidationError(
                    f'Period code "{code}" already exists. Please use a unique code.'
                )
        
        return code
    
    def clean(self):
        """Validate fiscal period configuration using school timezone ⭐"""
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        auto_close_date = cleaned_data.get('auto_close_date')
        fiscal_year = cleaned_data.get('fiscal_year')
        period_type = cleaned_data.get('period_type')
        
        # ⭐ FIX: If editing and fiscal_year is disabled, get it from instance
        if not fiscal_year and self.instance.pk:
            try:
                # Use fiscal_year_id to avoid RelatedObjectDoesNotExist
                if self.instance.fiscal_year_id:
                    fiscal_year = FiscalYear.objects.get(pk=self.instance.fiscal_year_id)
                    cleaned_data['fiscal_year'] = fiscal_year
            except (FiscalYear.DoesNotExist, AttributeError):
                pass
        
        # Validate date range
        if start_date and end_date:
            if start_date >= end_date:
                raise ValidationError({
                    'end_date': 'End date must be after start date.'
                })
            
            duration = (end_date - start_date).days
            if duration < 1:
                raise ValidationError(
                    'Period must be at least 1 day long.'
                )
        
        # Validate fiscal year dates
        if fiscal_year and start_date and end_date:
            if start_date < fiscal_year.start_date:
                raise ValidationError({
                    'start_date': (
                        f'Period cannot start before fiscal year start date '
                        f'({fiscal_year.start_date.strftime("%b %d, %Y")})'
                    )
                })
            if end_date > fiscal_year.end_date:
                raise ValidationError({
                    'end_date': (
                        f'Period cannot end after fiscal year end date '
                        f'({fiscal_year.end_date.strftime("%b %d, %Y")})'
                    )
                })
            
            # Check for overlapping periods
            if start_date and end_date:
                overlapping = FiscalPeriod.objects.filter(
                    fiscal_year=fiscal_year,
                    start_date__lt=end_date,
                    end_date__gt=start_date
                )
                
                if self.instance.pk:
                    overlapping = overlapping.exclude(pk=self.instance.pk)
                
                if overlapping.exists():
                    overlapping_names = ', '.join([p.name for p in overlapping[:3]])
                    if overlapping.count() > 3:
                        overlapping_names += f' and {overlapping.count() - 3} more'
                    
                    raise ValidationError({
                        'start_date': (
                            f'This period overlaps with existing period(s): {overlapping_names}. '
                            f'Please adjust the dates.'
                        )
                    })
        
        # Validate auto close date
        if auto_close_date:
            if start_date and auto_close_date < start_date:
                raise ValidationError({
                    'auto_close_date': 'Auto close date cannot be before start date.'
                })
        
        return cleaned_data
    
    def save(self, commit=True):
        """Save the fiscal period."""
        instance = super().save(commit=False)
        
        # ⭐ FIX: Ensure fiscal_year is set from cleaned_data
        if 'fiscal_year' in self.cleaned_data:
            instance.fiscal_year = self.cleaned_data['fiscal_year']
        
        if commit:
            instance.save()
        
        return instance


class FiscalPeriodFilterForm(HTMXFilterFormMixin, DateRangeFormMixin, BootstrapFormMixin, forms.Form):
    """
    HTMX-powered fiscal period filter form.
    Uses school timezone for date validations. ⭐
    """
    
    htmx_get = 'core:fiscal_period_search'
    htmx_target = '#fiscal-period-list'
    search_delay = 300
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by name, code...'
        })
    )
    
    fiscal_year = forms.ModelChoiceField(
        label='Fiscal Year',
        queryset=None,
        required=False,
        widget=SelectWithDefault(default_label="All Fiscal Years")
    )
    
    period_type = forms.ChoiceField(
        label='Period Type',
        choices=[('', 'All Types')] + FiscalPeriod.PERIOD_TYPE_CHOICES,
        required=False,
        widget=SelectWithDefault(default_label="All Types")
    )
    
    status = forms.ChoiceField(
        label='Status',
        choices=[('', 'All Statuses')] + FiscalPeriod.STATUS_CHOICES,
        required=False,
        widget=SelectWithDefault(default_label="All Statuses")
    )
    
    is_active = forms.NullBooleanField(
        label='Active',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Active'),
            ('false', 'Inactive')
        ], attrs={'class': 'form-select'})
    )
    
    is_closed = forms.NullBooleanField(
        label='Closed',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Closed'),
            ('false', 'Open')
        ], attrs={'class': 'form-select'})
    )
    
    start_date_from = forms.DateField(
        label='Start Date From',
        required=False,
        widget=DatePickerInput()
    )
    
    start_date_to = forms.DateField(
        label='Start Date To',
        required=False,
        widget=DatePickerInput()
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set fiscal year queryset
        try:
            self.fields['fiscal_year'].queryset = FiscalYear.objects.all().order_by('-start_date')
        except Exception as e:
            logger.error(f"Error setting fiscal year queryset: {e}")


# =============================================================================
# PAYMENT METHOD FORMS
# =============================================================================

class PaymentMethodForm(BootstrapFormMixin, RequiredFieldsMixin, forms.ModelForm):
    """Form for creating/editing payment methods"""
    
    class Meta:
        model = PaymentMethod
        fields = [
            'name',
            'code',
            'method_type',
            'mobile_money_provider',
            'bank_name',
            'bank_account_number',
            'bank_branch',
            'swift_code',
            'is_active',
            'is_default',
            'requires_approval',
            'minimum_amount',
            'maximum_amount',
            'has_transaction_fee',
            'transaction_fee_type',
            'transaction_fee_amount',
            'fee_bearer',
            'processing_time',
            'requires_reference',
            'icon',
            'color_code',
            'display_order',
            'instructions',
            'notes',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Cash, MTN Mobile Money'
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., CASH, MTN_MM'
            }),
            'method_type': forms.Select(attrs={'class': 'form-select'}),
            'mobile_money_provider': forms.Select(attrs={'class': 'form-select'}),
            'bank_name': forms.TextInput(attrs={'class': 'form-control'}),
            'bank_account_number': forms.TextInput(attrs={'class': 'form-control'}),
            'bank_branch': forms.TextInput(attrs={'class': 'form-control'}),
            'swift_code': forms.TextInput(attrs={'class': 'form-control'}),
            'minimum_amount': MoneyInput(),
            'maximum_amount': MoneyInput(),
            'transaction_fee_type': forms.Select(attrs={'class': 'form-select'}),
            'transaction_fee_amount': MoneyInput(),
            'fee_bearer': forms.Select(attrs={'class': 'form-select'}),
            'processing_time': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Instant, 1-2 business days'
            }),
            'icon': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., fa-money-bill, fa-mobile-alt'
            }),
            'color_code': forms.TextInput(attrs={
                'type': 'color',
                'class': 'form-control form-control-color'
            }),
            'display_order': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0'
            }),
            'instructions': forms.Textarea(attrs={
                'rows': 3,
                'class': 'form-control',
                'placeholder': 'Payment instructions for users'
            }),
            'notes': forms.Textarea(attrs={
                'rows': 2,
                'class': 'form-control',
                'placeholder': 'Internal notes'
            }),
        }
    
    def clean_code(self):
        """Normalize code to uppercase"""
        code = self.cleaned_data.get('code')
        if code:
            return code.upper().replace(' ', '_')
        return code
    
    def clean(self):
        """Validate payment method configuration"""
        cleaned_data = super().clean()
        
        method_type = cleaned_data.get('method_type')
        min_amount = cleaned_data.get('minimum_amount')
        max_amount = cleaned_data.get('maximum_amount')
        has_fee = cleaned_data.get('has_transaction_fee')
        fee_type = cleaned_data.get('transaction_fee_type')
        fee_amount = cleaned_data.get('transaction_fee_amount')
        
        # Validate mobile money provider
        if method_type == 'MOBILE_MONEY' and not cleaned_data.get('mobile_money_provider'):
            raise ValidationError({
                'mobile_money_provider': 'Mobile money provider is required for mobile money payment methods.'
            })
        
        # Validate amount range
        if min_amount and max_amount:
            if min_amount >= max_amount:
                raise ValidationError({
                    'maximum_amount': 'Maximum amount must be greater than minimum amount.'
                })
        
        # Validate transaction fees
        if has_fee:
            if not fee_type:
                raise ValidationError({
                    'transaction_fee_type': 'Fee type is required when transaction fees are enabled.'
                })
            if not fee_amount:
                raise ValidationError({
                    'transaction_fee_amount': 'Fee amount is required when transaction fees are enabled.'
                })
        
        return cleaned_data


class PaymentMethodFilterForm(HTMXFilterFormMixin, BootstrapFormMixin, forms.Form):
    """HTMX-powered payment method filter form"""
    
    htmx_get = 'core:payment_method_search'
    htmx_target = '#payment-method-list'
    search_delay = 300
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by name, code...'
        })
    )
    
    method_type = forms.ChoiceField(
        label='Method Type',
        choices=[('', 'All Types')] + PaymentMethod.METHOD_TYPE_CHOICES,
        required=False,
        widget=SelectWithDefault(default_label="All Types")
    )
    
    is_active = forms.NullBooleanField(
        label='Active',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Active'),
            ('false', 'Inactive')
        ], attrs={'class': 'form-select'})
    )
    
    has_transaction_fee = forms.NullBooleanField(
        label='Has Transaction Fee',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Yes'),
            ('false', 'No')
        ], attrs={'class': 'form-select'})
    )


# =============================================================================
# TAX RATE FORMS
# =============================================================================

class TaxRateForm(BootstrapFormMixin, RequiredFieldsMixin, forms.ModelForm):
    """
    Form for creating/editing tax rates.
    Uses school timezone for date validations. ⭐
    """
    
    class Meta:
        model = TaxRate
        fields = [
            'name',
            'tax_type',
            'rate',
            'effective_from',
            'effective_to',
            'is_active',
            'applies_to_fees',
            'applies_to_services',
            'description',
            'legal_reference',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., VAT 18%'
            }),
            'tax_type': forms.Select(attrs={'class': 'form-select'}),
            'rate': PercentageInput(),
            'effective_from': DatePickerInput(),
            'effective_to': DatePickerInput(),
            'description': forms.Textarea(attrs={
                'rows': 3,
                'class': 'form-control'
            }),
            'legal_reference': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., VAT Act 2013'
            }),
        }
    
    def clean_rate(self):
        """Validate tax rate percentage"""
        rate = self.cleaned_data.get('rate')
        if rate is not None:
            validate_percentage(rate)
        return rate
    
    def clean_effective_from(self):
        """Validate effective from date using school timezone ⭐"""
        date = self.cleaned_data.get('effective_from')
        if date:
            from core.utils import get_school_today
            from datetime import timedelta
            
            today = get_school_today()  # ⭐ SCHOOL TIMEZONE
            
            # Allow tax rates to be created up to 2 years in advance
            max_future = today + timedelta(days=2*365)
            if date > max_future:
                raise ValidationError(
                    "Effective from date cannot be more than 2 years in the future."
                )
        
        return date
    
    def clean(self):
        """Validate date range using school timezone ⭐"""
        cleaned_data = super().clean()
        effective_from = cleaned_data.get('effective_from')
        effective_to = cleaned_data.get('effective_to')
        
        if effective_from and effective_to:
            if effective_to <= effective_from:
                raise ValidationError({
                    'effective_to': 'Effective to date must be after effective from date.'
                })
        
        return cleaned_data


class TaxRateFilterForm(HTMXFilterFormMixin, DateRangeFormMixin, BootstrapFormMixin, forms.Form):
    """
    HTMX-powered tax rate filter form.
    Uses school timezone for date validations. ⭐
    """
    
    htmx_get = 'core:tax_rate_search'
    htmx_target = '#tax-rate-list'
    search_delay = 300
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by name...'
        })
    )
    
    tax_type = forms.ChoiceField(
        label='Tax Type',
        choices=[('', 'All Types')] + TaxRate.TAX_TYPE_CHOICES,
        required=False,
        widget=SelectWithDefault(default_label="All Types")
    )
    
    is_active = forms.NullBooleanField(
        label='Active',
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


# =============================================================================
# UNIT OF MEASURE FORMS
# =============================================================================

class UnitOfMeasureForm(BootstrapFormMixin, RequiredFieldsMixin, forms.ModelForm):
    """Form for creating/editing units of measure"""
    
    class Meta:
        model = UnitOfMeasure
        fields = [
            'name',
            'abbreviation',
            'symbol',
            'uom_type',
            'base_unit',
            'conversion_factor',
            'is_active',
            'description',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Meter, Kilogram'
            }),
            'abbreviation': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., m, kg'
            }),
            'symbol': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., m, kg (optional)'
            }),
            'uom_type': forms.Select(attrs={'class': 'form-select'}),
            'base_unit': forms.Select(attrs={
                'class': 'form-select',
                'data-placeholder': 'Select Base Unit (Optional)'
            }),
            'conversion_factor': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.000001',
                'min': '0.000001',
                'placeholder': '1.0'
            }),
            'description': forms.Textarea(attrs={
                'rows': 3,
                'class': 'form-control'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Filter base unit to exclude self and show only same type
        if self.instance.pk:
            self.fields['base_unit'].queryset = UnitOfMeasure.objects.filter(
                uom_type=self.instance.uom_type,
                is_active=True
            ).exclude(pk=self.instance.pk)
        
        # Help text
        self.fields['conversion_factor'].help_text = (
            'Multiply by this factor to convert to the base unit. '
            'Example: For centimeters to meters, factor is 0.01'
        )
        self.fields['base_unit'].help_text = (
            'Leave blank if this is a base unit. Otherwise, select the base unit this derives from.'
        )
    
    def clean_conversion_factor(self):
        """Validate conversion factor is positive"""
        factor = self.cleaned_data.get('conversion_factor')
        if factor is not None and factor <= 0:
            raise ValidationError('Conversion factor must be greater than zero.')
        return factor
    
    def clean(self):
        """Validate unit configuration"""
        cleaned_data = super().clean()
        
        base_unit = cleaned_data.get('base_unit')
        conversion_factor = cleaned_data.get('conversion_factor')
        
        # If base unit is set, conversion factor must not be 1
        if base_unit and conversion_factor == 1:
            self.add_warning(
                'conversion_factor',
                'Conversion factor of 1.0 suggests this should be a base unit.'
            )
        
        # If no base unit, conversion factor should be 1
        if not base_unit and conversion_factor != 1:
            self.add_warning(
                'conversion_factor',
                'Base units typically have a conversion factor of 1.0'
            )
        
        return cleaned_data


class UnitOfMeasureFilterForm(HTMXFilterFormMixin, BootstrapFormMixin, forms.Form):
    """HTMX-powered unit of measure filter form"""
    
    htmx_get = 'core:unit_of_measure_search'
    htmx_target = '#unit-list'
    search_delay = 300
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by name, abbreviation...'
        })
    )
    
    uom_type = forms.ChoiceField(
        label='Unit Type',
        choices=[('', 'All Types')] + UnitOfMeasure.UOM_TYPE_CHOICES,
        required=False,
        widget=SelectWithDefault(default_label="All Types")
    )
    
    is_active = forms.NullBooleanField(
        label='Active',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Active'),
            ('false', 'Inactive')
        ], attrs={'class': 'form-select'})
    )
    
    has_base_unit = forms.NullBooleanField(
        label='Has Base Unit',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Derived Units'),
            ('false', 'Base Units')
        ], attrs={'class': 'form-select'})
    )


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def add_warning(form, field_name, message):
    """Add a warning message to a form field (non-blocking)"""
    if not hasattr(form, '_warnings'):
        form._warnings = {}
    
    if field_name not in form._warnings:
        form._warnings[field_name] = []
    
    form._warnings[field_name].append(message)


# Monkey patch to add warnings capability to forms
forms.Form.add_warning = add_warning
forms.ModelForm.add_warning = add_warning