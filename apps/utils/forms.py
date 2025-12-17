from django import forms
from django.core.exceptions import ValidationError
import json
from decimal import Decimal
from .models import (
    FinancialSettings, SchoolConfiguration
)

# =============================================================================
# FINANCIAL SETTINGS FORMS
# =============================================================================

class FinancialSettingsForm(forms.ModelForm):
    """
    Form for managing financial settings with currency choices and previews.
    """
    
    # Override school_currency to use a ChoiceField
    school_currency = forms.ChoiceField(
        label="School Primary Currency",
        choices=[],  # Populated dynamically in __init__
        widget=forms.Select(attrs={
            'class': 'form-select',
            'onchange': 'updateCurrencyPreview()'
        }),
        help_text="Primary currency for all school financial transactions"
    )
    
    # Field for currency preview
    currency_preview = forms.CharField(
        label="Currency Preview",
        required=False,
        widget=forms.TextInput(attrs={
            'readonly': True,
            'class': 'form-control bg-light',
            'placeholder': 'Amount formatting preview will appear here'
        }),
        help_text="Preview of how amounts will be formatted"
    )

    class Meta:
        model = FinancialSettings
        fields = [
            'school_currency',
            'currency_position',
            'decimal_places',
            'use_thousand_separator',
            'default_payment_terms_days',
            'late_fee_enabled',
            'late_fee_percentage',
            'grace_period_days',
            'minimum_payment_amount',
            'auto_apply_scholarships',
            'scholarship_approval_required',
            'auto_apply_discounts',
            'discount_approval_required',
            'expense_approval_required',
            'expense_approval_limit',
            'send_invoice_emails',
            'send_payment_confirmations',
            'send_overdue_reminders',
        ]
        widgets = {
            'currency_position': forms.Select(attrs={'class': 'form-select', 'onchange': 'updateCurrencyPreview()'}),
            'decimal_places': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 4, 'onchange': 'updateCurrencyPreview()'}),
            'use_thousand_separator': forms.CheckboxInput(attrs={'class': 'form-check-input', 'onchange': 'updateCurrencyPreview()'}),
            'default_payment_terms_days': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 365}),
            'late_fee_percentage': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': 0, 'max': 100}),
            'grace_period_days': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 90}),
            'minimum_payment_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': 0}),
            'expense_approval_limit': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': 0}),
            'auto_apply_scholarships': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'scholarship_approval_required': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'auto_apply_discounts': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'discount_approval_required': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'expense_approval_required': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'send_invoice_emails': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'send_payment_confirmations': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'send_overdue_reminders': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Define currency choices
        CURRENCY_CHOICES = [
            ('', '---------'),
            ('UGX', 'UGX - Ugandan Shilling'),
            ('KES', 'KES - Kenyan Shilling'),
            ('TZS', 'TZS - Tanzanian Shilling'),
            ('RWF', 'RWF - Rwandan Franc'),
            ('ETB', 'ETB - Ethiopian Birr'),
            ('SSP', 'SSP - South Sudanese Pound'),
            ('USD', 'USD - US Dollar'),
            ('EUR', 'EUR - Euro'),
            ('GBP', 'GBP - British Pound Sterling'),
            ('JPY', 'JPY - Japanese Yen'),
            ('CHF', 'CHF - Swiss Franc'),
            ('ZAR', 'ZAR - South African Rand'),
            ('NGN', 'NGN - Nigerian Naira'),
            ('GHS', 'GHS - Ghanaian Cedi'),
            ('EGP', 'EGP - Egyptian Pound'),
            # Add other currencies as needed...
        ]

        self.fields['school_currency'].choices = CURRENCY_CHOICES

        # Populate currency preview for existing instance
        if self.instance and self.instance.pk:
            try:
                preview_amount = Decimal('12345.67')
                formatted_preview = self.instance.format_currency(preview_amount)
                self.fields['currency_preview'].initial = f"Example: {formatted_preview}"
            except Exception:
                self.fields['currency_preview'].initial = "Example: UGX 12,345.67"

    # Validation methods
    def clean_school_currency(self):
        currency = self.cleaned_data.get('school_currency')
        if currency and len(currency) != 3:
            raise ValidationError('Currency code must be exactly 3 characters')
        return currency

    def clean_late_fee_percentage(self):
        percentage = self.cleaned_data.get('late_fee_percentage')
        if percentage is not None and not (0 <= percentage <= 100):
            raise ValidationError('Late fee percentage must be between 0 and 100')
        return percentage

    def clean_minimum_payment_amount(self):
        amount = self.cleaned_data.get('minimum_payment_amount')
        if amount is not None and amount < 0:
            raise ValidationError('Minimum payment amount cannot be negative')
        return amount

    def clean_expense_approval_limit(self):
        limit = self.cleaned_data.get('expense_approval_limit')
        if limit is not None and limit < 0:
            raise ValidationError('Expense approval limit cannot be negative')
        return limit

    def clean_default_payment_terms_days(self):
        days = self.cleaned_data.get('default_payment_terms_days')
        if days is not None and not (1 <= days <= 365):
            raise ValidationError('Payment terms must be between 1 and 365 days')
        return days

    def clean_grace_period_days(self):
        days = self.cleaned_data.get('grace_period_days')
        if days is not None and not (0 <= days <= 90):
            raise ValidationError('Grace period must be between 0 and 90 days')
        return days

    def clean_decimal_places(self):
        decimal_places = self.cleaned_data.get('decimal_places')
        if decimal_places is not None and not (0 <= decimal_places <= 4):
            raise ValidationError('Decimal places must be between 0 and 4')
        return decimal_places

    def clean(self):
        cleaned_data = super().clean()
        # Additional cross-field validations can be added here
        return cleaned_data

# =============================================================================
# SCHOOL CONFIGURATION FORMS
# =============================================================================

class SchoolConfigurationForm(forms.ModelForm):
    """Form for managing school configuration with validation and impact analysis."""

    sync_breaks_after_save = forms.BooleanField(
        label="Sync Breaks After Save",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text="Automatically update all breaks when configuration changes"
    )

    preview_changes = forms.BooleanField(
        label="Preview Changes",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text="Show preview of how changes will affect existing sessions and breaks"
    )

    validate_existing_sessions = forms.BooleanField(
        label="Validate Existing Sessions",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text="Check if existing sessions are compatible with new configuration"
    )

    class Meta:
        model = SchoolConfiguration
        fields = [
            # Academic System
            'term_system', 'periods_per_year', 'period_naming_convention', 'custom_period_names',
            # Academic Year
            'academic_year_type', 'regional_season_type', 'custom_season_names',
            'academic_year_start_month', 'academic_year_start_day',
            # Breaks
            'auto_create_breaks', 'minimum_break_days', 'default_period_duration_weeks',
            # Communication
            'enable_automatic_reminders', 'enable_sms', 'enable_email_notifications',
        ]
        widgets = {
            'term_system': forms.Select(attrs={'class': 'form-select', 'onchange': 'updateTermFields(this.value)'}),
            'periods_per_year': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 20, 'placeholder': 'Number of periods per year', 'onchange': 'updatePeriodPreview()'}),
            'period_naming_convention': forms.Select(attrs={'class': 'form-select', 'onchange': 'toggleCustomNamesField()'}),
            'custom_period_names': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': '{"1": "Fall Semester", "2": "Spring Semester"}'}),
            'academic_year_type': forms.Select(attrs={'class': 'form-select', 'onchange': 'updatePeriodPreview()'}),
            'regional_season_type': forms.Select(attrs={'class': 'form-select', 'onchange': 'toggleCustomSeasonsField()'}),
            'custom_season_names': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': '{"1": "Harmattan", "2": "Rainy Season"}'}),
            'academic_year_start_month': forms.Select(attrs={'class': 'form-select'}),
            'academic_year_start_day': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 31, 'placeholder': 'Day of month'}),
            'auto_create_breaks': forms.CheckboxInput(attrs={'class': 'form-check-input', 'onchange': 'toggleBreakFields(this.checked)'}),
            'minimum_break_days': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 30, 'placeholder': 'Minimum days for a break'}),
            'default_period_duration_weeks': forms.NumberInput(attrs={'class': 'form-control', 'min': 4, 'max': 26, 'placeholder': 'Weeks per period'}),
            'enable_automatic_reminders': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'enable_sms': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'enable_email_notifications': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._initialize_fields()
        if self.instance.pk:
            self._add_current_config_info()
        self._add_impact_analysis_info()

    def _initialize_fields(self):
        """Set initial defaults and help texts."""
        if not self.instance.pk:
            defaults = {
                'term_system': 'term',
                'periods_per_year': 3,
                'period_naming_convention': 'numeric',
                'academic_year_type': 'northern',
                'regional_season_type': 'temperate',
                'academic_year_start_month': 9,
                'academic_year_start_day': 1,
                'auto_create_breaks': True,
                'minimum_break_days': 1,
                'default_period_duration_weeks': 12,
                'default_payment_due_days': 30,
                'allow_partial_payments': True,
                'enable_automatic_reminders': True,
                'enable_email_notifications': True,
                'enable_sms': False
            }
            for field, value in defaults.items():
                self.fields[field].initial = value

    def _add_current_config_info(self):
        """Add info about current period names."""
        try:
            period_names = [self.instance.get_period_name(i) for i in range(1, min(self.instance.periods_per_year + 1, 6))]
            if len(period_names) < self.instance.periods_per_year:
                period_names.append(f"... and {self.instance.periods_per_year - len(period_names)} more")
            self.fields['period_naming_convention'].help_text += f" (Current: {', '.join(period_names)})"
        except Exception:
            pass

    def _add_impact_analysis_info(self):
        """Show potential impact on existing sessions and breaks."""
        try:
            from academics.models import AcademicSession, Holiday
            session_count = AcademicSession.objects.count()
            break_count = Holiday.objects.filter(holiday_type='BREAK').count()
            info = []
            if session_count: info.append(f"{session_count} existing sessions")
            if break_count: info.append(f"{break_count} breaks")
            if info:
                self.fields['sync_breaks_after_save'].help_text += f" ({', '.join(info)})"
        except Exception:
            pass

    def clean_periods_per_year(self):
        periods = self.cleaned_data.get('periods_per_year')
        term_system = self.cleaned_data.get('term_system')
        if term_system == 'custom':
            if not periods or not (1 <= periods <= 20):
                raise ValidationError('Periods per year must be between 1 and 20 for custom system')
        else:
            expected = {
                'term': 3, 'semester': 2, 'quarter': 4, 'trimester': 3, 'module': 6,
                'block': 4, 'yearlong': 1, 'intensive': 10
            }.get(term_system, 3)
            if periods != expected:
                periods = expected
        # Validate impact on existing sessions
        if self.instance.pk and periods != self.instance.periods_per_year:
            try:
                from academics.models import AcademicSession
                invalid_sessions = AcademicSession.objects.filter(term_number__gt=periods)
                if invalid_sessions.exists():
                    raise ValidationError(f"Cannot reduce periods per year to {periods} because {invalid_sessions.count()} existing sessions exceed this limit.")
            except ImportError:
                pass
        return periods

    def clean_custom_period_names(self):
        custom_names = self.cleaned_data.get('custom_period_names')
        naming_convention = self.cleaned_data.get('period_naming_convention')
        periods_per_year = self.cleaned_data.get('periods_per_year', 3)
        if naming_convention == 'custom':
            if not custom_names:
                raise ValidationError('Custom period names are required for custom naming.')
            if isinstance(custom_names, str):
                try:
                    custom_names = json.loads(custom_names)
                    self.cleaned_data['custom_period_names'] = custom_names
                except (json.JSONDecodeError, TypeError) as e:
                    raise ValidationError(f'Custom period names must be valid JSON. Error: {e}')
            missing = [str(i) for i in range(1, periods_per_year + 1) if str(i) not in custom_names or not custom_names[str(i)].strip()]
            if missing:
                raise ValidationError(f'Missing custom names for periods: {", ".join(missing)}')
            for period, name in custom_names.items():
                if len(name.strip()) > 50:
                    raise ValidationError(f'Period name for period {period} is too long (max 50 characters)')
        else:
            custom_names = {}
        return custom_names

    def clean_custom_season_names(self):
        custom_seasons = self.cleaned_data.get('custom_season_names')
        if self.cleaned_data.get('regional_season_type') == 'custom_regional':
            if not custom_seasons:
                raise ValidationError('Custom season names are required for custom regional seasons.')
            if isinstance(custom_seasons, str):
                try:
                    custom_seasons = json.loads(custom_seasons)
                    self.cleaned_data['custom_season_names'] = custom_seasons
                except (json.JSONDecodeError, TypeError) as e:
                    raise ValidationError(f'Custom season names must be valid JSON. Error: {e}')
        else:
            custom_seasons = {}
        return custom_seasons

    def clean(self):
        cleaned_data = super().clean()
        # Validate academic year start date
        start_month = cleaned_data.get('academic_year_start_month')
        start_day = cleaned_data.get('academic_year_start_day')
        if start_month and start_day:
            try:
                from datetime import date
                date(2024, start_month, start_day)
            except ValueError:
                self.add_error('academic_year_start_day', 'Invalid academic year start date')
        # Breaks
        min_break_days = cleaned_data.get('minimum_break_days')
        if cleaned_data.get('auto_create_breaks') and min_break_days and min_break_days > 60:
            self.add_error('minimum_break_days', 'Minimum break days seems too high; consider 30 or less')
        # Financial
        due_days = cleaned_data.get('default_payment_due_days')
        if due_days and not (1 <= due_days <= 365):
            self.add_error('default_payment_due_days', 'Payment due days must be between 1 and 365')
        # Validate existing sessions
        if cleaned_data.get('validate_existing_sessions', True):
            self._validate_existing_sessions(cleaned_data)
        return cleaned_data

    def _validate_existing_sessions(self, cleaned_data):
        try:
            from academics.models import AcademicSession
            periods = cleaned_data.get('periods_per_year')
            if periods and self.instance.pk:
                invalid = AcademicSession.objects.filter(term_number__gt=periods)
                if invalid.exists():
                    sample = [str(s) for s in invalid[:3]]
                    if invalid.count() > 3:
                        sample.append(f"and {invalid.count() - 3} more")
                    self.add_error('periods_per_year', f'Existing sessions would be invalid: {", ".join(sample)}. Update or remove them first.')
        except Exception:
            pass
