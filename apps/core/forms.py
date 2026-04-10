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
- ExchangeRate (manual rate entry)
"""

from django import forms
from django.core.exceptions import ValidationError
from decimal import Decimal, InvalidOperation
from datetime import date
import logging
import json
import re

# Import base form utilities with timezone support
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
    validate_future_date,
    validate_past_date,
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
    ExchangeRate,
)

logger = logging.getLogger(__name__)


# =============================================================================
# WARNINGS MIXIN
# =============================================================================

class WarningsMixin:
    """
    Mixin that adds non-blocking warning messages to forms.

    Unlike validation errors, warnings do not prevent saving.
    They are collected in self._warnings and can be displayed
    in templates alongside the form.

    Usage:
        class MyForm(WarningsMixin, BootstrapFormMixin, forms.ModelForm):
            ...
            def clean(self):
                cleaned_data = super().clean()
                if some_condition:
                    self.add_warning('field_name', 'This looks unusual.')
                return cleaned_data

    In the template:
        {% if form._warnings %}
            {% for field, messages in form._warnings.items %}
                {% for message in messages %}
                    <div class="alert alert-warning">{{ message }}</div>
                {% endfor %}
            {% endfor %}
        {% endif %}
    """

    def add_warning(self, field_name, message):
        """
        Add a non-blocking warning message for a field.

        Args:
            field_name: Field name the warning relates to (use None for
                        form-level warnings not tied to a specific field).
            message:    Warning message string.
        """
        if not hasattr(self, '_warnings'):
            self._warnings = {}
        self._warnings.setdefault(field_name, []).append(message)


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
        model  = SchoolConfiguration
        fields = [
            'term_system',
            'periods_per_year',
            'period_naming_convention',
            'custom_period_names',
            'academic_year_type',
            'academic_year_start_month',
            'academic_year_start_day',
            'operational_timezone',
            'regional_season_type',
            'custom_season_names',
            'default_period_duration_weeks',
            'enable_automatic_reminders',
            'enable_sms',
            'enable_email_notifications',
        ]

        widgets = {
            'term_system': forms.Select(attrs={
                'class': 'form-select',
                'id':    'id_term_system',
            }),
            'periods_per_year': forms.NumberInput(attrs={
                'min':   '1',
                'max':   '20',
                'class': 'form-control',
                'id':    'id_periods_per_year',
            }),
            'period_naming_convention': forms.Select(attrs={
                'class': 'form-select',
                'id':    'id_period_naming_convention',
            }),
            'custom_period_names': forms.Textarea(attrs={
                'rows':        6,
                'class':       'form-control font-monospace',
                'id':          'id_custom_period_names',
                'placeholder': '{\n  "1": "First Term",\n  "2": "Second Term",\n  "3": "Third Term"\n}',
            }),
            'academic_year_type': forms.Select(attrs={
                'class': 'form-select',
                'id':    'id_academic_year_type',
            }),
            'academic_year_start_month': forms.Select(attrs={
                'class': 'form-select',
                'id':    'id_academic_year_start_month',
            }),
            'academic_year_start_day': forms.NumberInput(attrs={
                'min':   '1',
                'max':   '31',
                'class': 'form-control',
                'id':    'id_academic_year_start_day',
            }),
            'operational_timezone': forms.Select(attrs={
                'class':            'form-select select2',
                'id':               'id_operational_timezone',
                'data-placeholder': 'Select timezone...',
            }),
            'regional_season_type': forms.Select(attrs={
                'class': 'form-select',
                'id':    'id_regional_season_type',
            }),
            'custom_season_names': forms.Textarea(attrs={
                'rows':        4,
                'class':       'form-control font-monospace',
                'id':          'id_custom_season_names',
                'placeholder': '{\n  "1": "Rainy Season",\n  "2": "Dry Season"\n}',
            }),
            'default_period_duration_weeks': forms.NumberInput(attrs={
                'min':   '1',
                'max':   '52',
                'class': 'form-control',
                'id':    'id_default_period_duration_weeks',
            }),
            'enable_automatic_reminders': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'id':    'id_enable_automatic_reminders',
            }),
            'enable_sms': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'id':    'id_enable_sms',
            }),
            'enable_email_notifications': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'id':    'id_enable_email_notifications',
            }),
        }

        help_texts = {
            'term_system': (
                'Choose the academic period system used by your school. '
                'This affects how terms/semesters are named and counted.'
            ),
            'periods_per_year': (
                'Auto-set based on term system (editable for custom systems only).'
            ),
            'period_naming_convention': (
                'How academic periods should be named throughout the system.'
            ),
            'custom_period_names': (
                'JSON format: {"1": "Name 1", "2": "Name 2", ...}. '
                'Required only when using custom naming convention.'
            ),
            'academic_year_type': (
                'When your academic year typically runs '
                '(affects default period scheduling).'
            ),
            'academic_year_start_month': 'Month when academic year typically starts.',
            'academic_year_start_day':   'Day of month when academic year typically starts.',
            'operational_timezone': (
                'School timezone for fee due dates, fiscal periods, report generation, '
                'and all date-based business logic in the finance layer. '
                'Usually set to your school\'s physical location. '
                'Example: Africa/Kampala for Uganda, Africa/Nairobi for Kenya.'
            ),
            'regional_season_type': (
                'Climate-based season naming for your region '
                '(affects seasonal naming conventions).'
            ),
            'custom_season_names': (
                'JSON format: {"1": "Season 1", "2": "Season 2", ...}. '
                'Used when regional season type is "Custom".'
            ),
            'default_period_duration_weeks': (
                'Typical duration of each academic period in weeks '
                '(used as suggestion when creating sessions).'
            ),
            'enable_automatic_reminders': (
                'Send automatic payment and deadline reminders to parents and students.'
            ),
            'enable_sms': (
                'Enable SMS notifications for important updates '
                '(requires SMS gateway configuration).'
            ),
            'enable_email_notifications': (
                'Send email notifications for academic and financial events.'
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Popular East African timezones at the top for better UX
        from zoneinfo import available_timezones
        popular_timezones = [
            ('Africa/Kampala',       'Africa/Kampala (Uganda — EAT)'),
            ('Africa/Nairobi',       'Africa/Nairobi (Kenya — EAT)'),
            ('Africa/Dar_es_Salaam', 'Africa/Dar_es_Salaam (Tanzania — EAT)'),
            ('Africa/Kigali',        'Africa/Kigali (Rwanda — CAT)'),
            ('Africa/Addis_Ababa',   'Africa/Addis_Ababa (Ethiopia — EAT)'),
            ('Africa/Juba',          'Africa/Juba (South Sudan — CAT)'),
            ('---',                  '--- All Timezones ---'),
        ]
        all_timezones = [(tz, tz) for tz in sorted(available_timezones())]
        self.fields['operational_timezone'].widget.choices = (
            popular_timezones + all_timezones
        )

        # Dynamic placeholder and read-only logic for existing instances
        if self.instance and self.instance.pk:
            periods_count = self.instance.get_period_count()
            period_type   = self.instance.get_period_type_name()

            period_example = {
                str(i): f"{self._get_ordinal_number(i)} {period_type}"
                for i in range(1, min(periods_count + 1, 4))
            }
            self.fields['custom_period_names'].widget.attrs['placeholder'] = json.dumps(
                period_example, indent=2
            )

            if self.instance.regional_season_type == 'custom_regional':
                self.fields['custom_season_names'].widget.attrs['placeholder'] = json.dumps(
                    {"1": "First Season", "2": "Second Season"}, indent=2
                )

            if self.instance.term_system != 'custom':
                self.fields['periods_per_year'].widget.attrs['readonly'] = True
                self.fields['periods_per_year'].widget.attrs['class'] += ' bg-light'
                self.fields['periods_per_year'].help_text = (
                    f'Auto-calculated based on {self.instance.get_term_system_display()}. '
                    'Change term system to "Custom" to edit manually.'
                )

        self.fields['custom_period_names'].required = False
        self.fields['custom_season_names'].required = False

    # -------------------------------------------------------------------------
    # HELPERS
    # -------------------------------------------------------------------------

    def _get_ordinal_number(self, n):
        ordinals = {
            1: '1st', 2: '2nd', 3: '3rd', 4: '4th', 5: '5th',
            6: '6th', 7: '7th', 8: '8th', 9: '9th', 10: '10th',
            11: '11th', 12: '12th',
        }
        return ordinals.get(n, f'{n}th')

    # -------------------------------------------------------------------------
    # FIELD-LEVEL VALIDATION
    # -------------------------------------------------------------------------

    def clean_periods_per_year(self):
        periods_per_year = self.cleaned_data.get('periods_per_year')
        term_system      = self.cleaned_data.get('term_system')

        if term_system and term_system != 'custom':
            system_periods = {
                'term': 3, 'semester': 2, 'quarter': 4, 'trimester': 3,
                'module': 6, 'block': 4, 'yearlong': 1, 'intensive': 10,
            }
            return system_periods.get(term_system, 3)

        if not periods_per_year:
            raise ValidationError('Periods per year is required for custom term systems.')

        if not (1 <= periods_per_year <= 20):
            raise ValidationError('Periods per year must be between 1 and 20.')

        return periods_per_year

    def clean_operational_timezone(self):
        tz_str = self.cleaned_data.get('operational_timezone')

        if not tz_str:
            return 'Africa/Kampala'

        if tz_str == '---':
            raise ValidationError('Please select a valid timezone from the list.')

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
        data               = self.cleaned_data.get('custom_period_names')
        naming_convention  = self.cleaned_data.get('period_naming_convention')

        if naming_convention != 'custom':
            return {} if data is None else data

        if not data or (isinstance(data, str) and not data.strip()):
            raise ValidationError(
                'Custom period names are required when using custom naming convention. '
                'Provide a JSON dictionary mapping period numbers to names.'
            )

        try:
            names = json.loads(data) if isinstance(data, str) else data

            if not isinstance(names, dict):
                raise ValidationError(
                    'Custom period names must be a JSON object/dictionary. '
                    'Example: {"1": "First Term", "2": "Second Term", "3": "Third Term"}'
                )

            term_system = self.cleaned_data.get('term_system')
            if term_system == 'custom':
                periods_per_year = self.cleaned_data.get('periods_per_year')
            else:
                periods_per_year = self.instance.get_period_count() if self.instance else 3

            if not periods_per_year:
                raise ValidationError(
                    'Cannot validate custom names without knowing periods per year.'
                )

            missing_periods = [
                str(i) for i in range(1, periods_per_year + 1)
                if str(i) not in names
            ]
            empty_names = [
                str(i) for i in range(1, periods_per_year + 1)
                if str(i) in names and not str(names[str(i)]).strip()
            ]
            invalid_keys = [
                k for k in names.keys()
                if not k.isdigit() or not (1 <= int(k) <= periods_per_year)
            ]

            errors = []
            if missing_periods:
                errors.append(f'Missing names for period(s): {", ".join(missing_periods)}')
            if empty_names:
                errors.append(f'Empty names for period(s): {", ".join(empty_names)}')
            if invalid_keys:
                errors.append(f'Invalid period number(s): {", ".join(invalid_keys)}')

            if errors:
                raise ValidationError(' | '.join(errors))

            return {
                k: str(v).strip()
                for k, v in names.items()
                if k.isdigit() and 1 <= int(k) <= periods_per_year
            }

        except json.JSONDecodeError as e:
            raise ValidationError(
                f'Invalid JSON format: {str(e)}. '
                'Expected format: {"1": "Name 1", "2": "Name 2", "3": "Name 3"}'
            )

    def clean_custom_season_names(self):
        data        = self.cleaned_data.get('custom_season_names')
        season_type = self.cleaned_data.get('regional_season_type')

        if season_type != 'custom_regional':
            return {} if data is None else data

        if not data or (isinstance(data, str) and not data.strip()):
            raise ValidationError(
                'Custom season names are required when using custom regional season type. '
                'Provide a JSON dictionary mapping season numbers to names.'
            )

        try:
            names = json.loads(data) if isinstance(data, str) else data

            if not isinstance(names, dict):
                raise ValidationError(
                    'Custom season names must be a JSON object/dictionary. '
                    'Example: {"1": "Wet Season", "2": "Dry Season"}'
                )

            if not names:
                raise ValidationError('At least one season name is required.')

            cleaned_names = {
                k: str(v).strip()
                for k, v in names.items()
                if k.isdigit() and v and str(v).strip()
            }

            if not cleaned_names:
                raise ValidationError('No valid season names provided.')

            return cleaned_names

        except json.JSONDecodeError as e:
            raise ValidationError(
                f'Invalid JSON format: {str(e)}. '
                'Expected format: {"1": "Season 1", "2": "Season 2"}'
            )

    def clean_academic_year_start_day(self):
        day   = self.cleaned_data.get('academic_year_start_day')
        month = self.cleaned_data.get('academic_year_start_month')

        if not day:
            return 1

        if not (1 <= day <= 31):
            raise ValidationError('Day must be between 1 and 31.')

        if month:
            try:
                date(2024, month, day)
            except ValueError:
                month_names = {
                    1: 'January',  2: 'February',  3: 'March',
                    4: 'April',    5: 'May',        6: 'June',
                    7: 'July',     8: 'August',     9: 'September',
                    10: 'October', 11: 'November',  12: 'December',
                }
                raise ValidationError(
                    f'Day {day} is not valid for {month_names.get(month, "this month")}. '
                    'Please select a valid day.'
                )

        return day

    # -------------------------------------------------------------------------
    # CROSS-FIELD VALIDATION
    # -------------------------------------------------------------------------

    def clean(self):
        cleaned_data = super().clean()

        start_month = cleaned_data.get('academic_year_start_month')
        start_day   = cleaned_data.get('academic_year_start_day')
        if start_month and start_day:
            try:
                date(2024, start_month, start_day)
            except ValueError:
                self.add_error(
                    'academic_year_start_day',
                    f'Invalid date: Month {start_month} does not have {start_day} days.',
                )

        if cleaned_data.get('period_naming_convention') == 'custom':
            custom_names     = cleaned_data.get('custom_period_names', {})
            periods_per_year = cleaned_data.get('periods_per_year')
            if custom_names and periods_per_year:
                provided_count = len([k for k in custom_names.keys() if k.isdigit()])
                if provided_count != periods_per_year:
                    self.add_error(
                        'custom_period_names',
                        f'Expected {periods_per_year} period names, '
                        f'but got {provided_count}. '
                        f'Please provide names for all {periods_per_year} periods.',
                    )

        duration_weeks = cleaned_data.get('default_period_duration_weeks')
        if duration_weeks:
            periods     = cleaned_data.get('periods_per_year', 1)
            total_weeks = duration_weeks * periods
            if total_weeks > 52:
                self.add_error(
                    'default_period_duration_weeks',
                    f'Period duration of {duration_weeks} weeks × {periods} periods = '
                    f'{total_weeks} weeks, which exceeds 52 weeks in a year. '
                    'Please adjust the duration.',
                )

        return cleaned_data

    # -------------------------------------------------------------------------
    # SAVE
    # -------------------------------------------------------------------------

    def save(self, commit=True):
        """
        Save with singleton pattern enforcement.

        The model's own save() locks self.pk to _SCHOOL_CONFIGURATION_UUID
        and invalidates the class-level cache. No pk override needed here.
        """
        instance = super().save(commit=False)
        if commit:
            instance.save()
            logger.info("School configuration updated")
        return instance


# =============================================================================
# FINANCIAL SETTINGS FORM
# =============================================================================

class FinancialSettingsForm(BootstrapFormMixin, RequiredFieldsMixin, forms.ModelForm):
    """
    Comprehensive form for financial settings.
    Handles currency, payment terms, fees, workflows, and exchange rate config.
    """

    class Meta:
        model  = FinancialSettings
        fields = [
            'school_currency',
            'currency_position',
            'decimal_places',
            'use_thousand_separator',
            'auto_update_exchange_rates',
            'exchange_rate_update_frequency',
            'tracked_currencies',
            'invoice_prefix',
            'include_year_in_invoice_number',
            'payment_prefix',
            'include_year_in_payment_number',
            'receipt_prefix',
            'expense_prefix',
            'include_year_in_expense_number',
            'default_payment_terms_days',
            'late_fee_enabled',
            'late_fee_percentage',
            'grace_period_days',
            'minimum_payment_amount',
            'allow_partial_payments',
            'auto_apply_scholarships',
            'scholarship_approval_required',
            'auto_apply_discounts',
            'discount_approval_required',
            'discount_approval_threshold',
            'early_payment_discount_enabled',
            'early_payment_discount_percentage',
            'early_payment_discount_days',
            'expense_approval_required',
            'expense_approval_limit',
            'require_payment_confirmation',
            'require_expense_receipts',
            'require_purchase_orders',
            'send_invoice_emails',
            'send_payment_confirmations',
            'send_overdue_reminders',
            'overdue_reminder_days',
            'send_sms_notifications',
            'include_tax_in_prices',
            'default_tax_rate',
            'multi_currency_enabled',
            'auto_generate_recurring_invoices',
            'bad_debt_write_off_threshold',
            'auto_write_off_days',
        ]
        widgets = {
            'school_currency':  forms.Select(attrs={'class': 'form-select select2'}),
            'currency_position': forms.Select(attrs={'class': 'form-select'}),
            'decimal_places':   forms.NumberInput(attrs={'min': '0', 'max': '4', 'class': 'form-control'}),
            'exchange_rate_update_frequency': forms.NumberInput(attrs={
                'min': '1', 'max': '168', 'class': 'form-control', 'placeholder': '6',
            }),
            'invoice_prefix': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'INV'}),
            'payment_prefix': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'PMT'}),
            'receipt_prefix': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'RCPT'}),
            'expense_prefix': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'EXP'}),
            'default_payment_terms_days': forms.NumberInput(attrs={'min': '1', 'max': '365', 'class': 'form-control'}),
            'late_fee_percentage':              PercentageInput(),
            'grace_period_days':               forms.NumberInput(attrs={'min': '0', 'max': '90', 'class': 'form-control'}),
            'minimum_payment_amount':          MoneyInput(),
            'discount_approval_threshold':     MoneyInput(),
            'early_payment_discount_percentage': PercentageInput(),
            'early_payment_discount_days':     forms.NumberInput(attrs={'min': '1', 'max': '90', 'class': 'form-control'}),
            'expense_approval_limit':          MoneyInput(),
            'overdue_reminder_days':           forms.NumberInput(attrs={'min': '1', 'max': '30', 'class': 'form-control'}),
            'default_tax_rate':                PercentageInput(),
            'bad_debt_write_off_threshold':    MoneyInput(),
            'auto_write_off_days':             forms.NumberInput(attrs={'min': '90', 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # ── Currency choices ────────────────────────────────────────────
        try:
            currency_choices = FinancialSettings.get_currency_choices()
            self.fields['school_currency'].widget.choices = currency_choices
        except Exception as e:
            logger.error(f"Error loading currency choices: {e}")
            currency_choices = []

        # ── tracked_currencies ──────────────────────────────────────────
        # IMPORTANT: Replace the auto-generated JSONFormField with a
        # MultipleChoiceField. Leaving it as JSONFormField but swapping
        # the widget to SelectMultiple causes TypeError during re-render
        # after validation failure because JSONFormField.to_python() calls
        # json.loads() on the list that SelectMultiple.value_from_datadict()
        # returns, raising "must be str, bytes or bytearray, not list".
        try:
            initial_tracked = []
            if self.instance and self.instance.pk:
                raw = self.instance.tracked_currencies
                if isinstance(raw, list):
                    initial_tracked = raw
                elif isinstance(raw, str) and raw.strip():
                    import json as _json
                    try:
                        initial_tracked = _json.loads(raw)
                    except Exception:
                        initial_tracked = []

            self.fields['tracked_currencies'] = forms.MultipleChoiceField(
                choices=currency_choices,
                required=False,
                label='Tracked Currencies',
                widget=forms.SelectMultiple(attrs={
                    'class':            'form-select select2',
                    'data-placeholder': 'Select currencies to track (e.g. USD, EUR)',
                    'style':            'min-height: 100px;',
                    'data-group':       'exchange_rates',
                }),
            )
            self.initial['tracked_currencies'] = initial_tracked

        except Exception as e:
            logger.error(f"Error configuring tracked_currencies widget: {e}")

        self.fields['exchange_rate_update_frequency'].help_text = (
            "Only used when Auto-Update Exchange Rates is enabled. "
            "Minimum 1 hour, maximum 168 hours (1 week)."
        )

        self._add_field_groups()

    def _add_field_groups(self):
        """Add data-group attributes for tabbed template rendering."""
        groups = {
            'currency': [
                'school_currency', 'currency_position',
                'decimal_places', 'use_thousand_separator',
            ],
            'exchange_rates': [
                'auto_update_exchange_rates',
                'exchange_rate_update_frequency',
                'tracked_currencies',
            ],
        }
        for group, fields in groups.items():
            for field in fields:
                if field in self.fields:
                    self.fields[field].widget.attrs['data-group'] = group

    # -------------------------------------------------------------------------
    # FIELD-LEVEL VALIDATION
    # -------------------------------------------------------------------------

    def clean_late_fee_percentage(self):
        percentage = self.cleaned_data.get('late_fee_percentage')
        if percentage is not None:
            validate_percentage(percentage)
        return percentage

    def clean_early_payment_discount_percentage(self):
        percentage = self.cleaned_data.get('early_payment_discount_percentage')
        if percentage is not None:
            validate_percentage(percentage)
        return percentage

    def clean_default_tax_rate(self):
        percentage = self.cleaned_data.get('default_tax_rate')
        if percentage is not None:
            validate_percentage(percentage)
        return percentage

    def clean_tracked_currencies(self):
        """
        Coerce SelectMultiple output (list of strings) back to the JSON list
        that the model field expects, and validate each code.
        """
        raw = self.cleaned_data.get('tracked_currencies')

        if not raw:
            return []

        if isinstance(raw, str):
            codes = [c.strip().upper() for c in raw.split(',') if c.strip()]
        else:
            codes = [str(c).strip().upper() for c in raw if str(c).strip()]

        invalid = [c for c in codes if len(c) != 3]
        if invalid:
            raise forms.ValidationError(
                f"Invalid currency codes (must be 3-character ISO 4217): "
                f"{', '.join(invalid)}"
            )

        # Deduplicate while preserving order
        seen, deduped = set(), []
        for code in codes:
            if code not in seen:
                seen.add(code)
                deduped.append(code)

        return deduped

    def clean_exchange_rate_update_frequency(self):
        freq = self.cleaned_data.get('exchange_rate_update_frequency')
        if freq is not None and not (1 <= freq <= 168):
            raise forms.ValidationError(
                "Update frequency must be between 1 and 168 hours."
            )
        return freq

    # -------------------------------------------------------------------------
    # CROSS-FIELD VALIDATION
    # -------------------------------------------------------------------------

    def clean(self):
        cleaned_data = super().clean()

        for field in ('minimum_payment_amount', 'discount_approval_threshold', 'expense_approval_limit'):
            value = cleaned_data.get(field)
            if value is not None:
                validate_positive_amount(value)

        auto_update    = cleaned_data.get('auto_update_exchange_rates', False)
        tracked        = cleaned_data.get('tracked_currencies', [])
        school_currency= cleaned_data.get('school_currency', '')

        if auto_update:
            foreign = [c for c in tracked if c != school_currency]
            if not foreign:
                self.add_error(
                    'tracked_currencies',
                    "Add at least one foreign currency to track when auto-update is enabled. "
                    "The school currency itself does not need a rate.",
                )

        return cleaned_data


# =============================================================================
# ACCOUNT MAPPINGS FORMS
# =============================================================================

class CoreAccountMappingsForm(BootstrapFormMixin, forms.ModelForm):
    """Form for core account mappings."""

    class Meta:
        model  = CoreAccountMappings
        fields = [
            'default_bank_account',
            'default_cash_account',
            'student_receivables_account',
            'default_payable_account',
            'default_equity_account',
            'default_revenue_account',
            'default_expense_account',
            'scholarship_discount_account',
            'petty_cash_account',
            'mobile_money_account',
            'boarding_revenue_account',
            'uniform_and_book_sales_account',
            'salaries_account',
            'utilities_account',
            'boarding_expense_account',
        ]
        widgets = {
            'default_bank_account': forms.Select(attrs={
                'class': 'form-select select2',
                'data-placeholder': 'Select Primary Bank Account',
                'required': True,
            }),
            'default_cash_account': forms.Select(attrs={
                'class': 'form-select select2',
                'data-placeholder': 'Select Cash on Hand Account',
                'required': True,
            }),
            'student_receivables_account': forms.Select(attrs={
                'class': 'form-select select2',
                'data-placeholder': 'Select Student Receivables Account',
                'required': True,
            }),
            'default_payable_account': forms.Select(attrs={
                'class': 'form-select select2',
                'data-placeholder': 'Select Accounts Payable Account',
                'required': True,
            }),
            'default_equity_account': forms.Select(attrs={
                'class': 'form-select select2',
                'data-placeholder': 'Select Capital/Equity Account',
                'required': True,
            }),
            'default_revenue_account': forms.Select(attrs={
                'class': 'form-select select2',
                'data-placeholder': 'Select Default Revenue Account',
                'required': True,
            }),
            'default_expense_account': forms.Select(attrs={
                'class': 'form-select select2',
                'data-placeholder': 'Select Default Expense Account',
                'required': True,
            }),
            'scholarship_discount_account': forms.Select(attrs={
                'class': 'form-select select2',
                'data-placeholder': 'Select Scholarship/Discount Account',
                'required': True,
            }),
            'petty_cash_account': forms.Select(attrs={
                'class': 'form-select select2',
                'data-placeholder': 'Select Petty Cash Account (Optional)',
            }),
            'mobile_money_account': forms.Select(attrs={
                'class': 'form-select select2',
                'data-placeholder': 'Select Mobile Money Account (Optional)',
            }),
            'boarding_revenue_account': forms.Select(attrs={
                'class': 'form-select select2',
                'data-placeholder': 'Select Boarding Revenue Account (Optional)',
            }),
            'uniform_and_book_sales_account': forms.Select(attrs={
                'class': 'form-select select2',
                'data-placeholder': 'Select Uniform & Book Sales Account (Optional)',
            }),
            'salaries_account': forms.Select(attrs={
                'class': 'form-select select2',
                'data-placeholder': 'Select Salaries Account (Optional)',
            }),
            'utilities_account': forms.Select(attrs={
                'class': 'form-select select2',
                'data-placeholder': 'Select Utilities Account (Optional)',
            }),
            'boarding_expense_account': forms.Select(attrs={
                'class': 'form-select select2',
                'data-placeholder': 'Select Boarding Expense Account (Optional)',
            }),
        }
        help_texts = {
            'default_bank_account':           'Primary bank account for school operations (Required — ASSET)',
            'default_cash_account':           'Cash on hand account for physical cash (Required — ASSET)',
            'student_receivables_account':    'Accounts Receivable — Students control account (Required — ASSET)',
            'default_payable_account':        'Accounts Payable for vendors and suppliers (Required — LIABILITY)',
            'default_equity_account':         'Capital or Retained Earnings account (Required — EQUITY)',
            'default_revenue_account':        'Default account for all school fees revenue (Required — REVENUE)',
            'default_expense_account':        'Default account for general expenses (Required — EXPENSE)',
            'scholarship_discount_account':   'Account for scholarships and discounts (Required — EXPENSE)',
            'petty_cash_account': (
                'Separate petty cash account — falls back to default cash if not set.'
            ),
            'mobile_money_account': (
                'Mobile money clearing account — falls back to default bank if not set.'
            ),
            'boarding_revenue_account': (
                'Boarding/meals revenue for category-level routing. '
                'Distinct from RevenueAccountMappings.boarding_revenue_account '
                '(which handles invoice-type routing). '
                'Falls back to default revenue if not set.'
            ),
            'uniform_and_book_sales_account': (
                'Uniform and book sales revenue. Used as fallback when '
                'RevenueAccountMappings.uniform_sales_revenue_account is not set. '
                'Falls back to default revenue if not set.'
            ),
            'salaries_account': (
                'Staff salaries expense — falls back to default expense if not set.'
            ),
            'utilities_account': (
                'Utilities expenses — falls back to default expense if not set.'
            ),
            'boarding_expense_account': (
                'Boarding operational expenses — falls back to default expense if not set.'
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        try:
            from finance.models import Account

            # Helper: active, non-header accounts by account type category
            def qs(account_type_code):
                return Account.objects.filter(
                    account_type__account_type=account_type_code,
                    is_active=True,
                    is_header=False,
                ).order_by('account_number')

            asset_qs     = qs('ASSET')
            liability_qs = qs('LIABILITY')
            equity_qs    = qs('EQUITY')
            revenue_qs   = qs('REVENUE')
            expense_qs   = qs('EXPENSE')

            # Required fields
            bank_qs = asset_qs.filter(is_bank_account=True)
            self.fields['default_bank_account'].queryset = (
                bank_qs if bank_qs.exists() else asset_qs
            )
            self.fields['default_bank_account'].label = 'Primary Bank Account *'

            cash_qs = asset_qs.filter(is_cash_account=True)
            self.fields['default_cash_account'].queryset = (
                cash_qs if cash_qs.exists() else asset_qs
            )
            self.fields['default_cash_account'].label = 'Cash on Hand Account *'

            recv_qs = asset_qs.filter(is_receivable_account=True)
            self.fields['student_receivables_account'].queryset = (
                recv_qs if recv_qs.exists() else asset_qs
            )
            self.fields['student_receivables_account'].label = 'Student Receivables Account *'

            self.fields['default_payable_account'].queryset = liability_qs
            self.fields['default_payable_account'].label    = 'Accounts Payable Account *'

            self.fields['default_equity_account'].queryset = equity_qs
            self.fields['default_equity_account'].label    = 'Capital/Equity Account *'

            self.fields['default_revenue_account'].queryset = revenue_qs
            self.fields['default_revenue_account'].label    = 'Default Revenue Account *'

            self.fields['default_expense_account'].queryset = expense_qs
            self.fields['default_expense_account'].label    = 'Default Expense Account *'

            self.fields['scholarship_discount_account'].queryset = expense_qs
            self.fields['scholarship_discount_account'].label    = 'Scholarship/Discount Account *'

            # Optional fields
            self.fields['petty_cash_account'].queryset  = (
                cash_qs if cash_qs.exists() else asset_qs
            )
            self.fields['petty_cash_account'].required  = False
            self.fields['petty_cash_account'].label     = 'Petty Cash Account (Optional)'

            self.fields['mobile_money_account'].queryset = asset_qs
            self.fields['mobile_money_account'].required = False
            self.fields['mobile_money_account'].label    = 'Mobile Money Account (Optional)'

            self.fields['boarding_revenue_account'].queryset = revenue_qs
            self.fields['boarding_revenue_account'].required = False
            self.fields['boarding_revenue_account'].label    = 'Boarding Revenue Account (Optional)'

            self.fields['uniform_and_book_sales_account'].queryset = revenue_qs
            self.fields['uniform_and_book_sales_account'].required = False
            self.fields['uniform_and_book_sales_account'].label    = 'Uniform & Book Sales Account (Optional)'

            self.fields['salaries_account'].queryset = expense_qs
            self.fields['salaries_account'].required = False
            self.fields['salaries_account'].label    = 'Salaries Account (Optional)'

            self.fields['utilities_account'].queryset = expense_qs
            self.fields['utilities_account'].required = False
            self.fields['utilities_account'].label    = 'Utilities Account (Optional)'

            self.fields['boarding_expense_account'].queryset = expense_qs
            self.fields['boarding_expense_account'].required = False
            self.fields['boarding_expense_account'].label    = 'Boarding Expense Account (Optional)'

        except ImportError:
            logger.warning("Finance app not available — account mappings disabled")
        except Exception as e:
            logger.error(f"Error setting up account mappings form: {e}")

    def clean(self):
        cleaned_data = super().clean()

        required_fields = [
            'default_bank_account', 'default_cash_account',
            'student_receivables_account', 'default_payable_account',
            'default_equity_account', 'default_revenue_account',
            'default_expense_account', 'scholarship_discount_account',
        ]
        for field in required_fields:
            if not cleaned_data.get(field):
                self.add_error(field, 'This field is required.')

        bank_account = cleaned_data.get('default_bank_account')
        cash_account = cleaned_data.get('default_cash_account')
        if bank_account and cash_account and bank_account == cash_account:
            self.add_error(
                'default_cash_account',
                'Cash account must be different from bank account. '
                'Use separate accounts for cash on hand and bank.',
            )

        # Account type validation (defensive — model clean() also checks these)
        type_checks = [
            ('default_bank_account',         'ASSET'),
            ('default_cash_account',         'ASSET'),
            ('student_receivables_account',  'ASSET'),
            ('default_payable_account',      'LIABILITY'),
            ('default_equity_account',       'EQUITY'),
            ('default_revenue_account',      'REVENUE'),
            ('default_expense_account',      'EXPENSE'),
            ('scholarship_discount_account', 'EXPENSE'),
        ]
        for field_name, expected_type in type_checks:
            account = cleaned_data.get(field_name)
            if account and account.account_type.account_type != expected_type:
                self.add_error(field_name, f'Must be a {expected_type} account.')

        # Header account validation
        all_mapped_fields = required_fields + [
            'petty_cash_account', 'mobile_money_account',
            'boarding_revenue_account', 'uniform_and_book_sales_account',
            'salaries_account', 'utilities_account', 'boarding_expense_account',
        ]
        for field_name in all_mapped_fields:
            account = cleaned_data.get(field_name)
            if account and account.is_header:
                self.add_error(
                    field_name,
                    f"'{account.name}' is a header account and cannot receive "
                    "postings. Select a posting account.",
                )

        return cleaned_data


class RevenueAccountMappingsForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model  = RevenueAccountMappings
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
    class Meta:
        model  = PayrollAccountMappings
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
    class Meta:
        model  = ExpenseAccountMappings
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
    """
    Form for special account mappings.

    Note: petty_cash_account is intentionally excluded — it belongs on
    CoreAccountMappings, not SpecialAccountMappings.
    """

    class Meta:
        model  = SpecialAccountMappings
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
    Uses school timezone for date validations.
    """

    class Meta:
        model  = FiscalYear
        fields = [
            'name',
            'code',
            'start_date',
            'end_date',
            'is_active',
            'description',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class':       'form-control',
                'placeholder': 'e.g., 2024 or Academic Year 2024-2025',
            }),
            'code': forms.TextInput(attrs={
                'class':       'form-control',
                'placeholder': 'e.g., FY2024 or AY2024-25',
            }),
            'start_date':  DatePickerInput(),
            'end_date':    DatePickerInput(),
            'description': forms.Textarea(attrs={
                'rows':        3,
                'class':       'form-control',
                'placeholder': 'Optional description',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['is_active'].help_text = (
            'Only one fiscal year can be active at a time. '
            'Setting this will deactivate other fiscal years.'
        )

    def clean_start_date(self):
        start_date = self.cleaned_data.get('start_date')
        if start_date:
            from core.utils import get_school_today
            from datetime import timedelta
            today      = get_school_today()
            max_future = today + timedelta(days=3 * 365)
            if start_date > max_future:
                raise ValidationError(
                    "Start date cannot be more than 3 years in the future."
                )
        return start_date

    def clean(self):
        cleaned_data = super().clean()
        start_date   = cleaned_data.get('start_date')
        end_date     = cleaned_data.get('end_date')

        if start_date and end_date:
            if start_date >= end_date:
                raise ValidationError({'end_date': 'End date must be after start date.'})

            duration = (end_date - start_date).days
            if duration < 90:
                raise ValidationError(
                    'Fiscal year duration seems too short (less than 90 days). '
                    'Please verify dates.'
                )
            if duration > 400:
                raise ValidationError(
                    'Fiscal year duration seems too long (more than 400 days). '
                    'Please verify dates.'
                )

        return cleaned_data


class FiscalYearFilterForm(HTMXFilterFormMixin, DateRangeFormMixin, BootstrapFormMixin, forms.Form):
    """HTMX-powered fiscal year filter form."""

    htmx_get    = 'core:fiscal_year_search'
    htmx_target = '#fiscal-year-list'
    search_delay = 300

    q = forms.CharField(
        label='Search', required=False,
        widget=SearchInput(attrs={'placeholder': 'Search by name, code...'}),
    )
    status = forms.ChoiceField(
        label='Status',
        choices=[('', 'All Statuses')] + FiscalYear.STATUS_CHOICES,
        required=False,
        widget=SelectWithDefault(default_label="All Statuses"),
    )
    is_active = forms.NullBooleanField(
        label='Active', required=False,
        widget=forms.Select(choices=[
            ('', 'All'), ('true', 'Active'), ('false', 'Inactive'),
        ], attrs={'class': 'form-select'}),
    )
    is_closed = forms.NullBooleanField(
        label='Closed', required=False,
        widget=forms.Select(choices=[
            ('', 'All'), ('true', 'Closed'), ('false', 'Open'),
        ], attrs={'class': 'form-select'}),
    )
    start_date_from = forms.DateField(
        label='Start Date From', required=False, widget=DatePickerInput(),
    )
    start_date_to = forms.DateField(
        label='Start Date To', required=False, widget=DatePickerInput(),
    )


# =============================================================================
# FISCAL PERIOD FORMS
# =============================================================================

class FiscalPeriodForm(BootstrapFormMixin, RequiredFieldsMixin, forms.ModelForm):
    """
    Form for creating/editing fiscal periods.
    Uses school timezone for date validations.

    Note: status, is_active, is_closed, is_locked are auto-calculated
    by the model save() method and are not included in this form.
    """

    class Meta:
        model  = FiscalPeriod
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
            'fiscal_year':  forms.Select(attrs={'class': 'form-select'}),
            'name': forms.TextInput(attrs={
                'class':       'form-control',
                'placeholder': 'e.g., Term 1 2024 Fiscal Period',
            }),
            'code': forms.TextInput(attrs={
                'class':       'form-control',
                'placeholder': 'e.g., FP_2024_T1',
            }),
            'period_number': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.1', 'min': '0.1',
            }),
            'period_type':  forms.Select(attrs={'class': 'form-select'}),
            'related_academic_session': forms.Select(attrs={'class': 'form-select'}),
            'start_date':      DatePickerInput(),
            'end_date':        DatePickerInput(),
            'auto_close_date': DatePickerInput(),
            'grace_period_days': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'notes': forms.Textarea(attrs={
                'rows':        2,
                'class':       'form-control',
                'placeholder': 'Internal notes for accounting team',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        logger.info(
            f"FiscalPeriodForm.__init__ — instance.pk = "
            f"{self.instance.pk if self.instance else 'No instance'}, "
            f"_state.adding = "
            f"{self.instance._state.adding if self.instance else 'No instance'}"
        )

        try:
            from academics.models import AcademicSession
            self.fields['related_academic_session'].queryset = (
                AcademicSession.objects.all().order_by('-start_date')
            )
            self.fields['related_academic_session'].required    = False
            self.fields['related_academic_session'].empty_label = (
                "Select Academic Session (Optional)"
            )
        except Exception as e:
            logger.error(f"Error setting academic session queryset: {e}")
            self.fields['related_academic_session'].widget   = forms.HiddenInput()
            self.fields['related_academic_session'].required = False

        self.fields['period_number'].help_text = (
            'Sequential number within fiscal year. '
            'Use decimals (e.g., 1.5) for break periods between regular periods.'
        )
        self.fields['grace_period_days'].help_text = (
            'Days beyond end_date when transactions are still accepted.'
        )

        # An instance is being edited only if it is saved to the database
        is_editing = (
            self.instance
            and self.instance.pk
            and not self.instance._state.adding
        )

        logger.info(f"FiscalPeriodForm.__init__ — is_editing = {is_editing}")

        if is_editing:
            self.fields['fiscal_year'].disabled  = True
            self.fields['fiscal_year'].help_text = (
                'Cannot change fiscal year for an existing period. '
                'Create a new period if a different fiscal year is needed.'
            )
        else:
            self.fields['fiscal_year'].disabled  = False
            self.fields['fiscal_year'].required  = True
            self.fields['fiscal_year'].help_text = (
                'Select the fiscal year for this period.'
            )
            if self.initial.get('fiscal_year'):
                logger.info(
                    f"Form initialized with fiscal_year: {self.initial['fiscal_year']}"
                )

    def clean_start_date(self):
        start_date = self.cleaned_data.get('start_date')
        if start_date:
            from core.utils import get_school_today
            from datetime import timedelta
            today      = get_school_today()
            max_future = today + timedelta(days=2 * 365)
            if start_date > max_future:
                raise ValidationError(
                    "Start date cannot be more than 2 years in the future."
                )
        return start_date

    def clean_period_number(self):
        period_number = self.cleaned_data.get('period_number')
        fiscal_year   = self.cleaned_data.get('fiscal_year')

        if period_number and fiscal_year:
            existing = FiscalPeriod.objects.filter(
                fiscal_year=fiscal_year,
                period_number=period_number,
            )
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise ValidationError(
                    f'Period number {period_number} already exists in '
                    f'{fiscal_year.name}. Use a different number or decimal '
                    f'(e.g., {float(period_number) + 0.5}).'
                )

        return period_number

    def clean_code(self):
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
        cleaned_data   = super().clean()
        start_date     = cleaned_data.get('start_date')
        end_date       = cleaned_data.get('end_date')
        auto_close_date= cleaned_data.get('auto_close_date')
        fiscal_year    = cleaned_data.get('fiscal_year')

        # When editing, fiscal_year field is disabled so Django excludes it from
        # cleaned_data. Restore it from the instance.
        if not fiscal_year and self.instance and self.instance.pk:
            try:
                if self.instance.fiscal_year_id:
                    fiscal_year = FiscalYear.objects.get(pk=self.instance.fiscal_year_id)
                    cleaned_data['fiscal_year'] = fiscal_year
            except (FiscalYear.DoesNotExist, AttributeError):
                pass

        if start_date and end_date:
            if start_date >= end_date:
                raise ValidationError({'end_date': 'End date must be after start date.'})
            if (end_date - start_date).days < 1:
                raise ValidationError('Period must be at least 1 day long.')

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

            overlapping = FiscalPeriod.objects.filter(
                fiscal_year=fiscal_year,
                start_date__lt=end_date,
                end_date__gt=start_date,
            )
            if self.instance.pk:
                overlapping = overlapping.exclude(pk=self.instance.pk)
            if overlapping.exists():
                overlap_names = ', '.join([p.name for p in overlapping[:3]])
                if overlapping.count() > 3:
                    overlap_names += f' and {overlapping.count() - 3} more'
                raise ValidationError({
                    'start_date': (
                        f'This period overlaps with existing period(s): '
                        f'{overlap_names}. Please adjust the dates.'
                    )
                })

        if auto_close_date and start_date and auto_close_date < start_date:
            raise ValidationError({
                'auto_close_date': 'Auto close date cannot be before start date.'
            })

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if 'fiscal_year' in self.cleaned_data:
            instance.fiscal_year = self.cleaned_data['fiscal_year']
        if commit:
            instance.save()
        return instance


class FiscalPeriodFilterForm(
    HTMXFilterFormMixin, DateRangeFormMixin, BootstrapFormMixin, forms.Form
):
    """HTMX-powered fiscal period filter form."""

    htmx_get    = 'core:fiscal_period_search'
    htmx_target = '#fiscal-period-list'
    search_delay = 300

    q = forms.CharField(
        label='Search', required=False,
        widget=SearchInput(attrs={'placeholder': 'Search by name, code...'}),
    )
    fiscal_year = forms.ModelChoiceField(
        label='Fiscal Year', queryset=None, required=False,
        widget=SelectWithDefault(default_label="All Fiscal Years"),
    )
    period_type = forms.ChoiceField(
        label='Period Type',
        choices=[('', 'All Types')] + FiscalPeriod.PERIOD_TYPE_CHOICES,
        required=False,
        widget=SelectWithDefault(default_label="All Types"),
    )
    status = forms.ChoiceField(
        label='Status',
        choices=[('', 'All Statuses')] + FiscalPeriod.STATUS_CHOICES,
        required=False,
        widget=SelectWithDefault(default_label="All Statuses"),
    )
    is_active = forms.NullBooleanField(
        label='Active', required=False,
        widget=forms.Select(choices=[
            ('', 'All'), ('true', 'Active'), ('false', 'Inactive'),
        ], attrs={'class': 'form-select'}),
    )
    is_closed = forms.NullBooleanField(
        label='Closed', required=False,
        widget=forms.Select(choices=[
            ('', 'All'), ('true', 'Closed'), ('false', 'Open'),
        ], attrs={'class': 'form-select'}),
    )
    start_date_from = forms.DateField(
        label='Start Date From', required=False, widget=DatePickerInput(),
    )
    start_date_to = forms.DateField(
        label='Start Date To', required=False, widget=DatePickerInput(),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.fields['fiscal_year'].queryset = (
                FiscalYear.objects.all().order_by('-start_date')
            )
        except Exception as e:
            logger.error(f"Error setting fiscal year queryset: {e}")


# =============================================================================
# PAYMENT METHOD FORMS
# =============================================================================

class PaymentMethodForm(BootstrapFormMixin, RequiredFieldsMixin, forms.ModelForm):
    """Form for creating/editing payment methods."""

    class Meta:
        model  = PaymentMethod
        fields = [
            'name', 'code', 'method_type', 'mobile_money_provider',
            'bank_name', 'bank_account_number', 'bank_branch', 'swift_code',
            'is_active', 'is_default', 'requires_approval',
            'minimum_amount', 'maximum_amount',
            'has_transaction_fee', 'transaction_fee_type', 'transaction_fee_amount',
            'fee_bearer', 'processing_time', 'requires_reference',
            'icon', 'color_code', 'display_order', 'instructions', 'notes',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Cash, MTN Mobile Money',
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'e.g., CASH, MTN_MM',
            }),
            'method_type':           forms.Select(attrs={'class': 'form-select'}),
            'mobile_money_provider': forms.Select(attrs={'class': 'form-select'}),
            'bank_name':             forms.TextInput(attrs={'class': 'form-control'}),
            'bank_account_number':   forms.TextInput(attrs={'class': 'form-control'}),
            'bank_branch':           forms.TextInput(attrs={'class': 'form-control'}),
            'swift_code':            forms.TextInput(attrs={'class': 'form-control'}),
            'minimum_amount':        MoneyInput(),
            'maximum_amount':        MoneyInput(),
            'transaction_fee_type':  forms.Select(attrs={'class': 'form-select'}),
            'transaction_fee_amount': MoneyInput(),
            'fee_bearer':            forms.Select(attrs={'class': 'form-select'}),
            'processing_time': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Instant, 1-2 business days',
            }),
            'icon': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., fa-money-bill, fa-mobile-alt',
            }),
            'color_code': forms.TextInput(attrs={
                'type': 'color', 'class': 'form-control form-control-color',
            }),
            'display_order': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'instructions': forms.Textarea(attrs={
                'rows': 3, 'class': 'form-control',
                'placeholder': 'Payment instructions for users',
            }),
            'notes': forms.Textarea(attrs={
                'rows': 2, 'class': 'form-control', 'placeholder': 'Internal notes',
            }),
        }
        
    def clean_code(self):
            code = self.cleaned_data.get('code')
            if code:
                return code.upper().replace(' ', '_')
            return code

    def clean(self):
        cleaned_data   = super().clean()
        method_type    = cleaned_data.get('method_type')
        min_amount     = cleaned_data.get('minimum_amount')
        max_amount     = cleaned_data.get('maximum_amount')
        has_fee        = cleaned_data.get('has_transaction_fee')
        fee_type       = cleaned_data.get('transaction_fee_type')
        fee_amount     = cleaned_data.get('transaction_fee_amount')

        if method_type == 'MOBILE_MONEY' and not cleaned_data.get('mobile_money_provider'):
            raise ValidationError({
                'mobile_money_provider': (
                    'Mobile money provider is required for mobile money payment methods.'
                )
            })

        if min_amount and max_amount and min_amount >= max_amount:
            raise ValidationError({
                'maximum_amount': 'Maximum amount must be greater than minimum amount.'
            })

        if has_fee:
            if not fee_type:
                raise ValidationError({
                    'transaction_fee_type': (
                        'Fee type is required when transaction fees are enabled.'
                    )
                })
            if not fee_amount:
                raise ValidationError({
                    'transaction_fee_amount': (
                        'Fee amount is required when transaction fees are enabled.'
                    )
                })

        return cleaned_data


class PaymentMethodFilterForm(BootstrapFormMixin, forms.Form):
    """
    Payment method filter form.
    Uses plain GET submission — no HTMX dependency.
    """

    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={'placeholder': 'Search by name, code...'}),
    )
    method_type = forms.ChoiceField(
        label='Method Type',
        choices=[('', 'All Types')] + PaymentMethod.METHOD_TYPE_CHOICES,
        required=False,
        widget=SelectWithDefault(default_label="All Types"),
    )
    is_active = forms.NullBooleanField(
        label='Active',
        required=False,
        widget=forms.Select(
            choices=[('', 'All'), ('true', 'Active'), ('false', 'Inactive')],
            attrs={'class': 'form-select'},
        ),
    )
    has_transaction_fee = forms.NullBooleanField(
        label='Has Transaction Fee',
        required=False,
        widget=forms.Select(
            choices=[('', 'All'), ('true', 'Yes'), ('false', 'No')],
            attrs={'class': 'form-select'},
        ),
    )


# =============================================================================
# TAX RATE FORMS
# =============================================================================

class TaxRateForm(BootstrapFormMixin, RequiredFieldsMixin, forms.ModelForm):
    """
    Form for creating/editing tax rates.
    Uses school timezone for date validations.
    """

    class Meta:
        model  = TaxRate
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
                'class':       'form-control',
                'placeholder': 'e.g., VAT 18%',
            }),
            'tax_type':        forms.Select(attrs={'class': 'form-select'}),
            'rate':            PercentageInput(),
            'effective_from':  DatePickerInput(),
            'effective_to':    DatePickerInput(),
            'description':     forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'legal_reference': forms.TextInput(attrs={
                'class':       'form-control',
                'placeholder': 'e.g., VAT Act 2013',
            }),
        }

    def clean_rate(self):
        rate = self.cleaned_data.get('rate')
        if rate is not None:
            validate_percentage(rate)
        return rate

    def clean_effective_from(self):
        """Validate effective from date using school timezone."""
        effective_from = self.cleaned_data.get('effective_from')
        if effective_from:
            from core.utils import get_school_today
            from datetime import timedelta
            today      = get_school_today()
            max_future = today + timedelta(days=2 * 365)
            if effective_from > max_future:
                raise ValidationError(
                    "Effective from date cannot be more than 2 years in the future."
                )
        return effective_from

    def clean(self):
        """Validate date range using school timezone."""
        cleaned_data   = super().clean()
        effective_from = cleaned_data.get('effective_from')
        effective_to   = cleaned_data.get('effective_to')

        if effective_from and effective_to:
            if effective_to <= effective_from:
                raise ValidationError({
                    'effective_to': (
                        'Effective to date must be after effective from date.'
                    )
                })

        return cleaned_data


class TaxRateFilterForm(BootstrapFormMixin, DateRangeFormMixin, forms.Form):
    """
    Tax rate filter form.
    Uses plain GET submission — no HTMX dependency.
    """

    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={'placeholder': 'Search by name...'}),
    )
    tax_type = forms.ChoiceField(
        label='Tax Type',
        choices=[('', 'All Types')] + TaxRate.TAX_TYPE_CHOICES,
        required=False,
        widget=SelectWithDefault(default_label="All Types"),
    )
    is_active = forms.NullBooleanField(
        label='Active',
        required=False,
        widget=forms.Select(
            choices=[('', 'All'), ('true', 'Active'), ('false', 'Inactive')],
            attrs={'class': 'form-select'},
        ),
    )
    effective_from = forms.DateField(
        label='Effective From',
        required=False,
        widget=DatePickerInput(),
    )
    effective_to = forms.DateField(
        label='Effective To',
        required=False,
        widget=DatePickerInput(),
    )


# =============================================================================
# UNIT OF MEASURE FORMS
# =============================================================================

class UnitOfMeasureForm(WarningsMixin, BootstrapFormMixin, RequiredFieldsMixin, forms.ModelForm):
    """
    Form for creating/editing units of measure.

    Uses WarningsMixin to surface non-blocking advisory messages
    (e.g. suspicious conversion factor) without preventing save.
    """

    class Meta:
        model  = UnitOfMeasure
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
                'class':       'form-control',
                'placeholder': 'e.g., Meter, Kilogram',
            }),
            'abbreviation': forms.TextInput(attrs={
                'class':       'form-control',
                'placeholder': 'e.g., m, kg',
            }),
            'symbol': forms.TextInput(attrs={
                'class':       'form-control',
                'placeholder': 'e.g., m, kg (optional)',
            }),
            'uom_type': forms.Select(attrs={'class': 'form-select'}),
            'base_unit': forms.Select(attrs={
                'class':            'form-select',
                'data-placeholder': 'Select Base Unit (Optional)',
            }),
            'conversion_factor': forms.NumberInput(attrs={
                'class':       'form-control',
                'step':        '0.000001',
                'min':         '0.000001',
                'placeholder': '1.0',
            }),
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Filter base_unit to same UOM type, excluding self to prevent circular refs
        if self.instance.pk:
            self.fields['base_unit'].queryset = UnitOfMeasure.objects.filter(
                uom_type=self.instance.uom_type,
                is_active=True,
            ).exclude(pk=self.instance.pk)
        else:
            self.fields['base_unit'].queryset = UnitOfMeasure.objects.filter(
                is_active=True,
            )

        self.fields['conversion_factor'].help_text = (
            'Multiply by this factor to convert to the base unit. '
            'Example: for centimetres to metres, factor is 0.01.'
        )
        self.fields['base_unit'].help_text = (
            'Leave blank if this is a base unit. '
            'Otherwise, select the base unit this derives from.'
        )

    def clean_conversion_factor(self):
        factor = self.cleaned_data.get('conversion_factor')
        if factor is not None and factor <= 0:
            raise ValidationError('Conversion factor must be greater than zero.')
        return factor

    def clean(self):
        cleaned_data       = super().clean()
        base_unit          = cleaned_data.get('base_unit')
        conversion_factor  = cleaned_data.get('conversion_factor')

        # Advisory warnings — do not block save
        if base_unit and conversion_factor == 1:
            self.add_warning(
                'conversion_factor',
                'A conversion factor of 1.0 with a base unit set suggests '
                'this might should be a base unit itself.',
            )

        if not base_unit and conversion_factor and conversion_factor != 1:
            self.add_warning(
                'conversion_factor',
                'Base units typically have a conversion factor of 1.0. '
                'Did you mean to select a base unit?',
            )

        return cleaned_data


class UnitOfMeasureFilterForm(BootstrapFormMixin, forms.Form):
    """
    Unit of measure filter form.
    Uses plain GET submission — no HTMX dependency.
    """

    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={'placeholder': 'Search by name, abbreviation...'}),
    )
    uom_type = forms.ChoiceField(
        label='Unit Type',
        choices=[('', 'All Types')] + UnitOfMeasure.UOM_TYPE_CHOICES,
        required=False,
        widget=SelectWithDefault(default_label="All Types"),
    )
    is_active = forms.NullBooleanField(
        label='Active',
        required=False,
        widget=forms.Select(
            choices=[('', 'All'), ('true', 'Active'), ('false', 'Inactive')],
            attrs={'class': 'form-select'},
        ),
    )
    has_base_unit = forms.NullBooleanField(
        label='Has Base Unit',
        required=False,
        widget=forms.Select(
            choices=[
                ('', 'All'),
                ('true',  'Derived Units'),
                ('false', 'Base Units'),
            ],
            attrs={'class': 'form-select'},
        ),
    )


# =============================================================================
# FISCAL YEAR FILTER FORM (no HTMX)
# =============================================================================

class FiscalYearFilterForm(BootstrapFormMixin, DateRangeFormMixin, forms.Form):
    """
    Fiscal year filter form.
    Uses plain GET submission — no HTMX dependency.
    """

    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={'placeholder': 'Search by name, code...'}),
    )
    status = forms.ChoiceField(
        label='Status',
        choices=[('', 'All Statuses')] + FiscalYear.STATUS_CHOICES,
        required=False,
        widget=SelectWithDefault(default_label="All Statuses"),
    )
    is_active = forms.NullBooleanField(
        label='Active',
        required=False,
        widget=forms.Select(
            choices=[('', 'All'), ('true', 'Active'), ('false', 'Inactive')],
            attrs={'class': 'form-select'},
        ),
    )
    is_closed = forms.NullBooleanField(
        label='Closed',
        required=False,
        widget=forms.Select(
            choices=[('', 'All'), ('true', 'Closed'), ('false', 'Open')],
            attrs={'class': 'form-select'},
        ),
    )
    start_date_from = forms.DateField(
        label='Start Date From',
        required=False,
        widget=DatePickerInput(),
    )
    start_date_to = forms.DateField(
        label='Start Date To',
        required=False,
        widget=DatePickerInput(),
    )


# =============================================================================
# FISCAL PERIOD FILTER FORM (no HTMX)
# =============================================================================

class FiscalPeriodFilterForm(BootstrapFormMixin, DateRangeFormMixin, forms.Form):
    """
    Fiscal period filter form.
    Uses plain GET submission — no HTMX dependency.
    """

    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={'placeholder': 'Search by name, code...'}),
    )
    fiscal_year = forms.ModelChoiceField(
        label='Fiscal Year',
        queryset=None,
        required=False,
        widget=SelectWithDefault(default_label="All Fiscal Years"),
    )
    period_type = forms.ChoiceField(
        label='Period Type',
        choices=[('', 'All Types')] + FiscalPeriod.PERIOD_TYPE_CHOICES,
        required=False,
        widget=SelectWithDefault(default_label="All Types"),
    )
    status = forms.ChoiceField(
        label='Status',
        choices=[('', 'All Statuses')] + FiscalPeriod.STATUS_CHOICES,
        required=False,
        widget=SelectWithDefault(default_label="All Statuses"),
    )
    is_active = forms.NullBooleanField(
        label='Active',
        required=False,
        widget=forms.Select(
            choices=[('', 'All'), ('true', 'Active'), ('false', 'Inactive')],
            attrs={'class': 'form-select'},
        ),
    )
    is_closed = forms.NullBooleanField(
        label='Closed',
        required=False,
        widget=forms.Select(
            choices=[('', 'All'), ('true', 'Closed'), ('false', 'Open')],
            attrs={'class': 'form-select'},
        ),
    )
    start_date_from = forms.DateField(
        label='Start Date From',
        required=False,
        widget=DatePickerInput(),
    )
    start_date_to = forms.DateField(
        label='Start Date To',
        required=False,
        widget=DatePickerInput(),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.fields['fiscal_year'].queryset = (
                FiscalYear.objects.all().order_by('-start_date')
            )
        except Exception as e:
            logger.error(f"Error setting fiscal year queryset: {e}")


# =============================================================================
# EXCHANGE RATE FORMS
# =============================================================================

class ExchangeRateForm(BootstrapFormMixin, RequiredFieldsMixin, forms.ModelForm):
    """
    Bursar enters today's exchange rate from the bank.

    KEY BEHAVIOURS:
    - source is always forced to 'MANUAL' — not exposed in the form.
    - Saving this form automatically creates/updates the inverse rate too
      (to → from direction) so the bursar only needs to type one direction.
    - MANUAL rates take priority over auto-fetched rates in ExchangeRate.get_rate().
      This means the bursar can always override a fetched rate.

    IMPORTANT: This form only records a *suggested* rate for cashier pre-fill.
    The rate stored on Payment.exchange_rate / FeeInvoice.exchange_rate /
    UniformSale.exchange_rate is the legal record and is never recalculated
    from this table after the transaction is saved.
    """

    class Meta:
        model  = ExchangeRate
        fields = ['from_currency', 'to_currency', 'rate', 'date', 'notes']
        widgets = {
            'rate': forms.NumberInput(attrs={
                'class':       'form-control',
                'step':        '0.000001',
                'placeholder': 'e.g. 1315.000000',
            }),
            'date': forms.DateInput(attrs={
                'class': 'form-control',
                'type':  'date',
            }),
            'notes': forms.TextInput(attrs={
                'class':       'form-control',
                'placeholder': 'e.g. Bank of Uganda official closing rate',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Currency dropdowns — populated from FinancialSettings.get_currency_choices()
        # which now exists as a classmethod on the model.
        currency_choices = [('', '--- Select ---')] + FinancialSettings.get_currency_choices()

        self.fields['from_currency'] = forms.ChoiceField(
            label='From Currency',
            choices=currency_choices,
            widget=forms.Select(attrs={'class': 'form-select select2'}),
        )
        self.fields['to_currency'] = forms.ChoiceField(
            label='To Currency',
            choices=currency_choices,
            widget=forms.Select(attrs={'class': 'form-select select2'}),
        )

        # Default date to today in school timezone
        from core.utils import get_school_today
        if not self.initial.get('date') and not self.data.get('date'):
            self.fields['date'].initial = get_school_today()

        # Pre-fill to_currency with the school's primary currency
        try:
            school_currency = FinancialSettings.get_school_currency()
            if not self.initial.get('to_currency') and not self.data.get('to_currency'):
                self.fields['to_currency'].initial = school_currency
        except Exception:
            pass

        self.fields['from_currency'].help_text = (
            "The currency you are converting FROM (e.g. USD)."
        )
        self.fields['to_currency'].help_text = (
            "The currency you are converting TO (e.g. UGX). "
            "The inverse rate is saved automatically so you only need to enter one direction."
        )
        self.fields['rate'].help_text = (
            "How many units of 'To Currency' equal one unit of 'From Currency'. "
            "Example: if 1 USD = 3,850 SSD, enter 3850."
        )
        self.fields['notes'].required = False

    # -------------------------------------------------------------------------
    # VALIDATION
    # -------------------------------------------------------------------------

    def clean_from_currency(self):
        code = self.cleaned_data.get('from_currency', '').upper().strip()
        if not code:
            raise ValidationError("Please select a currency.")
        if len(code) != 3:
            raise ValidationError("Currency code must be 3 characters (ISO 4217).")
        return code

    def clean_to_currency(self):
        code = self.cleaned_data.get('to_currency', '').upper().strip()
        if not code:
            raise ValidationError("Please select a currency.")
        if len(code) != 3:
            raise ValidationError("Currency code must be 3 characters (ISO 4217).")
        return code

    def clean_rate(self):
        rate = self.cleaned_data.get('rate')
        if rate is None:
            raise ValidationError("Rate is required.")
        if rate <= 0:
            raise ValidationError("Rate must be greater than zero.")
        return rate

    def clean(self):
        cleaned_data  = super().clean()
        from_currency = cleaned_data.get('from_currency')
        to_currency   = cleaned_data.get('to_currency')

        if from_currency and to_currency and from_currency == to_currency:
            raise ValidationError(
                "'From Currency' and 'To Currency' cannot be the same."
            )

        return cleaned_data

    # -------------------------------------------------------------------------
    # SAVE — writes the entered rate AND the inverse
    # -------------------------------------------------------------------------

    def save(self, commit=True):
        """
        Save the entered rate with source='MANUAL' and is_active=True,
        then automatically create/update the inverse rate (to → from).

        Bursar only needs to enter one direction.
        """
        instance           = super().save(commit=False)
        instance.source    = 'MANUAL'
        instance.is_active = True

        if commit:
            instance.save()
            self._save_inverse(instance)

        return instance

    def _save_inverse(self, instance):
        """
        Create or update the inverse exchange rate (to → from).

        Uses update_or_create so multiple saves on the same day do not
        create duplicate records.
        """
        try:
            inverse_rate = (
                Decimal('1') / instance.rate
            ).quantize(Decimal('0.000001'))

            ExchangeRate.objects.update_or_create(
                from_currency=instance.to_currency,
                to_currency=instance.from_currency,
                date=instance.date,
                source='MANUAL (inverse)',
                defaults={
                    'rate':      inverse_rate,
                    'is_active': True,
                    'notes': (
                        f"Auto-computed inverse of: "
                        f"1 {instance.from_currency} = {instance.rate} "
                        f"{instance.to_currency} ({instance.date})"
                    ),
                },
            )
        except Exception as e:
            logger.error(
                f"Failed to save inverse rate for {instance}: {e}",
                exc_info=True,
            )


class ExchangeRateFilterForm(BootstrapFormMixin, forms.Form):
    """
    Exchange rate filter form.
    Uses plain GET submission — no HTMX dependency.
    """

    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={'placeholder': 'Search by currency code, notes...'}),
    )
    from_currency = forms.ChoiceField(
        label='From Currency',
        choices=[],
        required=False,
        widget=SelectWithDefault(default_label="All Currencies"),
    )
    to_currency = forms.ChoiceField(
        label='To Currency',
        choices=[],
        required=False,
        widget=SelectWithDefault(default_label="All Currencies"),
    )
    source = forms.ChoiceField(
        label='Source',
        choices=[
            ('',              'All Sources'),
            ('MANUAL',        'Manual'),
            ('MANUAL (inverse)', 'Manual (Inverse)'),
        ],
        required=False,
        widget=SelectWithDefault(default_label="All Sources"),
    )
    is_active = forms.NullBooleanField(
        label='Active',
        required=False,
        widget=forms.Select(
            choices=[('', 'All'), ('true', 'Active'), ('false', 'Inactive')],
            attrs={'class': 'form-select'},
        ),
    )
    date_from = forms.DateField(
        label='Date From',
        required=False,
        widget=DatePickerInput(),
    )
    date_to = forms.DateField(
        label='Date To',
        required=False,
        widget=DatePickerInput(),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Populate currency choices from FinancialSettings
        try:
            currency_choices = (
                [('', 'All Currencies')]
                + FinancialSettings.get_currency_choices()
            )
            self.fields['from_currency'].choices = currency_choices
            self.fields['to_currency'].choices   = currency_choices
        except Exception as e:
            logger.error(f"Error loading currency choices for filter form: {e}")


# =============================================================================
# PAYMENT CURRENCY MIXIN
# =============================================================================

class PaymentCurrencyMixin:
    """
    Mixin for PaymentForm — adds currency and exchange_rate field handling.

    Attach to any ModelForm whose model has:
        currency                  — CharField (ISO 4217 or blank for school currency)
        exchange_rate             — DecimalField (rate to school currency)
        amount_in_school_currency — DecimalField (calculated: amount × exchange_rate)

    Usage:
        class PaymentForm(PaymentCurrencyMixin, BootstrapFormMixin, forms.ModelForm):
            class Meta:
                model  = Payment
                fields = [..., 'currency', 'exchange_rate', 'amount_in_school_currency']

            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.setup_currency_fields()

    The mixin:
      1. Populates the currency selector with ISO 4217 choices.
      2. Pre-fills exchange_rate from ExchangeRate.get_rate() for today
         if a foreign currency is already selected.
      3. Calculates amount_in_school_currency in clean().
      4. Validates that exchange_rate > 0 when a foreign currency is chosen.
    """

    def setup_currency_fields(self):
        """
        Call from the host form's __init__ after super().__init__().
        Configures currency/rate/school-currency fields.
        """
        try:
            school_currency = FinancialSettings.get_school_currency()
        except Exception:
            school_currency = 'UGX'

        # ----------------------------------------------------------------
        # Currency selector
        # ----------------------------------------------------------------
        if 'currency' in self.fields:
            currency_choices = (
                [('', f'School Currency ({school_currency})')]
                + FinancialSettings.get_currency_choices()
            )
            self.fields['currency'].widget = forms.Select(
                choices=currency_choices,
                attrs={
                    'class':                'form-select select2',
                    'data-school-currency': school_currency,
                    'id':                   'id_currency',
                },
            )
            self.fields['currency'].required  = False
            self.fields['currency'].help_text = (
                f"Leave blank if paying in {school_currency}. "
                "Select a different currency if the parent is paying in foreign currency."
            )
            if not self.initial.get('currency'):
                self.fields['currency'].initial = school_currency

        # ----------------------------------------------------------------
        # Exchange rate field
        # ----------------------------------------------------------------
        if 'exchange_rate' in self.fields:
            self.fields['exchange_rate'].widget = forms.NumberInput(attrs={
                'class':       'form-control',
                'step':        '0.000001',
                'placeholder': '1.000000',
                'id':          'id_exchange_rate',
            })
            self.fields['exchange_rate'].help_text = (
                "Rate used for this payment. "
                "Pre-filled from today's exchange rates — confirm or override. "
                "This value is stored permanently with the payment and is never "
                "recalculated after saving."
            )
            self.fields['exchange_rate'].initial = Decimal('1.000000')

            # Pre-fill rate if a currency is already selected
            selected_currency = (
                self.initial.get('currency')
                or (
                    self.instance.currency
                    if self.instance and self.instance.pk
                    else None
                )
                or school_currency
            )
            if selected_currency and selected_currency != school_currency:
                self._prefill_rate(selected_currency, school_currency)

        # ----------------------------------------------------------------
        # amount_in_school_currency — read-only, calculated on clean()
        # ----------------------------------------------------------------
        if 'amount_in_school_currency' in self.fields:
            self.fields['amount_in_school_currency'].widget = forms.NumberInput(attrs={
                'class':    'form-control',
                'readonly': True,
                'id':       'id_amount_in_school_currency',
            })
            self.fields['amount_in_school_currency'].required  = False
            self.fields['amount_in_school_currency'].help_text = (
                f"Calculated: amount × exchange rate. "
                f"This is what credits the student account in {school_currency}."
            )

    def _prefill_rate(self, from_currency, to_currency):
        """Pre-fill exchange_rate from today's ExchangeRate table."""
        try:
            rate = ExchangeRate.get_rate(from_currency, to_currency)
            if rate and 'exchange_rate' in self.fields:
                self.fields['exchange_rate'].initial = rate
                logger.debug(
                    f"Pre-filled exchange rate {from_currency}→{to_currency}: {rate}"
                )
            elif 'exchange_rate' in self.fields:
                logger.warning(
                    f"No exchange rate found for {from_currency}→{to_currency}. "
                    "Cashier must enter manually."
                )
        except Exception as e:
            logger.error(f"Error pre-filling exchange rate: {e}")

    # -------------------------------------------------------------------------
    # FIELD-LEVEL VALIDATION
    # -------------------------------------------------------------------------

    def clean_currency(self):
        currency = self.cleaned_data.get('currency', '').upper().strip()
        if not currency:
            return FinancialSettings.get_school_currency()
        if len(currency) != 3:
            raise ValidationError("Currency code must be 3 characters (ISO 4217).")
        return currency

    def clean_exchange_rate(self):
        rate = self.cleaned_data.get('exchange_rate')
        if rate is None:
            return Decimal('1.000000')
        if rate <= 0:
            raise ValidationError("Exchange rate must be greater than zero.")
        return rate

    # -------------------------------------------------------------------------
    # CROSS-FIELD VALIDATION AND SCHOOL-CURRENCY CALCULATION
    # -------------------------------------------------------------------------

    def clean(self):
        cleaned_data    = super().clean()
        currency        = cleaned_data.get('currency', '')
        exchange_rate   = cleaned_data.get('exchange_rate', Decimal('1.000000'))
        amount          = cleaned_data.get('amount')

        try:
            school_currency = FinancialSettings.get_school_currency()
        except Exception:
            school_currency = 'UGX'

        # Advisory log when cashier overrides a rate for which no DB entry exists
        if currency and currency != school_currency:
            db_rate = ExchangeRate.get_rate(currency, school_currency)
            if not db_rate:
                logger.warning(
                    f"No exchange rate in DB for {currency}→{school_currency}. "
                    f"Cashier is using manually entered rate: {exchange_rate}"
                )

        # Calculate amount_in_school_currency
        if amount and exchange_rate:
            try:
                cleaned_data['amount_in_school_currency'] = (
                    Decimal(str(amount)) * Decimal(str(exchange_rate))
                ).quantize(Decimal('0.01'))
            except Exception as e:
                logger.error(f"Error calculating amount_in_school_currency: {e}")
                cleaned_data['amount_in_school_currency'] = amount

        return cleaned_data

    # -------------------------------------------------------------------------
    # SAVE HELPER
    # -------------------------------------------------------------------------

    def save_with_currency(self, commit=True):
        """
        Call instead of save() when using this mixin.

        Sets currency, exchange_rate, and amount_in_school_currency on the
        instance from cleaned_data before saving.
        """
        instance = self.instance

        instance.currency = self.cleaned_data.get(
            'currency', FinancialSettings.get_school_currency()
        )
        instance.exchange_rate = self.cleaned_data.get(
            'exchange_rate', Decimal('1.000000')
        )
        instance.amount_in_school_currency = self.cleaned_data.get(
            'amount_in_school_currency',
            getattr(instance, 'amount', Decimal('0.00')),
        )

        if commit:
            instance.save()

        return instance