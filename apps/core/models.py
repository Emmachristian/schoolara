# core/models.py

"""
Core models for School Management System
Updated with timezone support and SACCO best practices
"""

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from utils.models import BaseModel
from django.utils import timezone
from zoneinfo import ZoneInfo, available_timezones
import pycountry
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# SCHOOL CONFIGURATION MODEL
# =============================================================================

class SchoolConfiguration(BaseModel):
    """
    Enhanced configuration model for maximum flexibility across all school term systems.
    Singleton model - only one instance allowed per school.
    
    Changes from original:
    - Added timezone configuration
    - Simplified singleton pattern (pk=1)
    - Added timezone helper methods
    - Improved documentation
    """
    
    # -------------------------------------------------------------------------
    # TERM SYSTEM CONFIGURATION
    # -------------------------------------------------------------------------
    
    TERM_SYSTEM_CHOICES = [
        # Most common systems
        ('term', 'Terms (3 per year) - British/Commonwealth'),
        ('semester', 'Semesters (2 per year) - North American'),
        ('quarter', 'Quarters (4 per year)'),
        
        # Alternative naming for 3-period system
        ('trimester', 'Trimesters (3 per year) - Same as Terms, different name'),
        
        # Other systems
        ('module', 'Modules (6-8 per year)'),
        ('block', 'Block Schedule (4-6 per year)'),
        ('yearlong', 'Year-long Program (1 per year)'),
        ('intensive', 'Intensive Programs (8-12 per year)'),
        ('custom', 'Custom System'),
    ]
    
    term_system = models.CharField(
        "Academic Period System",
        max_length=15,
        choices=TERM_SYSTEM_CHOICES,
        default='term',
        help_text="The academic period system used by the school. Note: 'Terms' and 'Trimesters' both mean 3 periods per year."
    )
    
    periods_per_year = models.PositiveIntegerField(
        "Periods Per Year",
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(20)],
        help_text="Number of academic periods in one academic year (1-20)"
    )
    
    # -------------------------------------------------------------------------
    # PERIOD NAMING CONFIGURATION
    # -------------------------------------------------------------------------
    
    period_naming_convention = models.CharField(
        "Period Naming Convention",
        max_length=20,
        choices=[
            ('numeric', 'Numeric (Term 1, Term 2, etc.)'),
            ('ordinal', 'Ordinal (First Term, Second Term, etc.)'),
            ('seasonal', 'Seasonal (Fall, Spring, Summer)'),
            ('monthly', 'Monthly (January, February, etc.)'),
            ('alpha', 'Alphabetical (Term A, Term B, etc.)'),
            ('roman', 'Roman Numerals (Term I, Term II, etc.)'),
            ('custom', 'Custom Names'),
        ],
        default='numeric'
    )
    
    custom_period_names = models.JSONField(
        "Custom Period Names",
        default=dict,
        blank=True,
        help_text='Custom names for each period position. E.g., {"1": "Fall Semester", "2": "Spring Semester"}'
    )
    
    # -------------------------------------------------------------------------
    # ACADEMIC YEAR CONFIGURATION
    # -------------------------------------------------------------------------
    
    MONTH_CHOICES = [
        (1, 'January'), (2, 'February'), (3, 'March'), (4, 'April'),
        (5, 'May'), (6, 'June'), (7, 'July'), (8, 'August'),
        (9, 'September'), (10, 'October'), (11, 'November'), (12, 'December')
    ]
    
    ACADEMIC_YEAR_TYPE_CHOICES = [
        ('calendar', 'Calendar Year (Jan-Dec)'),
        ('northern', 'Northern Hemisphere (Sep-Jun)'),
        ('southern', 'Southern Hemisphere (Feb-Nov)'),
        ('tropical', 'Tropical Regions (Jan-Nov)'),
        ('east_africa', 'East African Calendar (Jan-Nov)'),
        ('west_africa', 'West African Calendar (Sep-Jul)'),
        ('sahel', 'Sahel Region (Oct-Jun)'),
        ('financial', 'Financial Year (Apr-Mar)'),
        ('custom', 'Custom Year Dates'),
    ]
    
    academic_year_type = models.CharField(
        "Academic Year Type",
        max_length=15,
        choices=ACADEMIC_YEAR_TYPE_CHOICES,
        default='east_africa',  # Default for Ugandan context
        help_text="When your academic year typically runs"
    )
    
    academic_year_start_month = models.PositiveIntegerField(
        "Academic Year Start Month",
        choices=MONTH_CHOICES,
        default=2,  # February for East African schools
        validators=[MinValueValidator(1), MaxValueValidator(12)],
        help_text="Month when academic year typically starts (1-12)"
    )
    
    academic_year_start_day = models.PositiveIntegerField(
        "Academic Year Start Day",
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
        help_text="Day when academic year typically starts"
    )
    
    # -------------------------------------------------------------------------
    # TIMEZONE CONFIGURATION ⭐ NEW
    # -------------------------------------------------------------------------
    
    operational_timezone = models.CharField(
        "Operational Timezone",
        max_length=63,  # Max length of IANA timezone identifiers
        default='Africa/Kampala',
        help_text="Timezone for academic schedules, deadlines, and automated processes. "
                  "Critical for: fee due dates, exam schedules, attendance marking, "
                  "report generation, and all date-based business logic."
    )
    
    # -------------------------------------------------------------------------
    # REGIONAL SEASON CONFIGURATION
    # -------------------------------------------------------------------------
    
    REGIONAL_SEASON_CHOICES = [
        ('temperate', 'Temperate (Spring/Summer/Fall/Winter)'),
        ('tropical_wet_dry', 'Tropical (Wet/Dry Seasons)'),
        ('desert', 'Desert (Hot/Cool Seasons)'),
        ('equatorial', 'Equatorial (Year-round)'),
        ('monsoon', 'Monsoon (Pre/Monsoon/Post)'),
        ('custom_regional', 'Custom Regional Seasons'),
    ]
    
    regional_season_type = models.CharField(
        "Regional Season Type",
        max_length=20,
        choices=REGIONAL_SEASON_CHOICES,
        default='equatorial',  # Default for Ugandan context
        help_text="Climate-based season naming for your region"
    )
    
    custom_season_names = models.JSONField(
        "Custom Season Names",
        default=dict,
        blank=True,
        help_text="Regional season names. E.g., {'1': 'Harmattan', '2': 'Rainy Season'}"
    )
    
    # -------------------------------------------------------------------------
    # ACADEMIC PERIOD SETTINGS
    # -------------------------------------------------------------------------
    
    default_period_duration_weeks = models.PositiveIntegerField(
        "Default Period Duration (weeks)",
        default=13,
        validators=[MinValueValidator(1), MaxValueValidator(52)],
        help_text="Typical duration of each academic period in weeks (used as a suggestion when creating sessions)"
    )
    
    # -------------------------------------------------------------------------
    # COMMUNICATION CONFIGURATION
    # -------------------------------------------------------------------------
    
    enable_automatic_reminders = models.BooleanField(
        "Enable Automatic Reminders",
        default=True,
        help_text="Send automatic payment and deadline reminders"
    )

    enable_sms = models.BooleanField(
        "Enable SMS Notifications",
        default=False,
        help_text="Send SMS notifications to parents and students"
    )

    enable_email_notifications = models.BooleanField(
        "Enable Email Notifications",
        default=True,
        help_text="Send email notifications"
    )
    
    # -------------------------------------------------------------------------
    # VALIDATION METHODS
    # -------------------------------------------------------------------------
    
    def clean(self):
        """Enhanced validation for the configuration"""
        super().clean()
        errors = {}
        
        # Validate periods_per_year matches term_system for non-custom systems
        if self.term_system != 'custom':
            expected_periods = self._get_system_period_count(self.term_system)
            if self.periods_per_year != expected_periods:
                # Auto-correct instead of raising error
                self.periods_per_year = expected_periods
        
        # Validate custom period names if using custom naming
        if self.period_naming_convention == 'custom':
            if not self.custom_period_names:
                errors['custom_period_names'] = 'Custom period names are required when using custom naming convention'
            else:
                # Ensure we have names for all periods
                missing_periods = []
                for i in range(1, self.periods_per_year + 1):
                    if str(i) not in self.custom_period_names:
                        missing_periods.append(str(i))
                
                if missing_periods:
                    errors['custom_period_names'] = f'Missing custom names for periods: {", ".join(missing_periods)}'
        
        # Validate academic year dates
        if self.academic_year_type == 'custom':
            try:
                # Test if the date is valid
                test_date = date(2024, self.academic_year_start_month, self.academic_year_start_day)
            except ValueError:
                errors['academic_year_start_day'] = 'Invalid academic year start date'
        
        # Validate timezone ⭐ NEW
        if self.operational_timezone:
            try:
                ZoneInfo(self.operational_timezone)
            except Exception as e:
                errors['operational_timezone'] = f"Invalid timezone: {self.operational_timezone}"
        
        if errors:
            raise ValidationError(errors)
    
    # -------------------------------------------------------------------------
    # HELPER METHODS - PERIOD SYSTEM
    # -------------------------------------------------------------------------
    
    def _get_system_period_count(self, system):
        """Get the standard period count for each system"""
        return {
            'term': 3,           # British/Commonwealth - 3 terms
            'semester': 2,       # North American - 2 semesters
            'quarter': 4,        # Quarterly - 4 quarters
            'trimester': 3,      # Same as terms - 3 trimesters
            'module': 6,         # Module-based - 6 modules
            'block': 4,          # Block schedule - 4 blocks
            'yearlong': 1,       # Year-long - 1 period
            'intensive': 10,     # Intensive - ~10 sessions
            'custom': self.periods_per_year
        }.get(system, 3)
    
    def get_period_count(self):
        """Returns the number of periods per year"""
        if self.term_system == 'custom':
            return self.periods_per_year
        return self._get_system_period_count(self.term_system)
    
    def get_term_system_display_name(self):
        """Get a user-friendly display name for the term system"""
        # Handle the trimester/term equivalence
        if self.term_system == 'trimester':
            return "Trimesters (3 per year, same as Terms)"
        return self.get_term_system_display()
    
    # -------------------------------------------------------------------------
    # TIMEZONE HELPER METHODS ⭐ NEW
    # -------------------------------------------------------------------------
    
    @staticmethod
    def get_timezone_choices():
        """
        Get ALL available timezone choices from the system.
        Returns sorted list of all IANA timezones.
        
        Returns:
            list: List of tuples (timezone_name, timezone_name)
        """
        all_zones = sorted(available_timezones())
        return [(tz, tz) for tz in all_zones]
    
    def get_timezone(self):
        """
        Get the operational timezone as a ZoneInfo object.
        
        Returns:
            ZoneInfo: Timezone object for the configured operational timezone
        
        Example:
            >>> config = SchoolConfiguration.get_instance()
            >>> tz = config.get_timezone()
            >>> current_time = datetime.now(tz=tz)
        """
        try:
            return ZoneInfo(self.operational_timezone)
        except Exception as e:
            logger.warning(f"Invalid timezone '{self.operational_timezone}': {e}. Falling back to Africa/Kampala")
            return ZoneInfo('Africa/Kampala')
    
    def get_current_time(self):
        """
        Get current time in school's operational timezone.
        
        Returns:
            datetime: Current datetime in operational timezone
        
        Example:
            >>> config = SchoolConfiguration.get_instance()
            >>> now = config.get_current_time()
            >>> print(f"Current school time: {now}")
        """
        return timezone.now().astimezone(self.get_timezone())
    
    def get_today(self):
        """
        Get today's date in school's operational timezone.
        
        Returns:
            date: Today's date in operational timezone
        
        Example:
            >>> config = SchoolConfiguration.get_instance()
            >>> today = config.get_today()
            >>> # Check if term is active today
            >>> if term.start_date <= today <= term.end_date:
            >>>     print("Term is active")
        """
        return self.get_current_time().date()
    
    def localize_datetime(self, dt):
        """
        Convert a datetime to school's operational timezone.
        
        Args:
            dt: datetime object (naive or aware)
            
        Returns:
            datetime: Timezone-aware datetime in operational timezone
        
        Example:
            >>> config = SchoolConfiguration.get_instance()
            >>> utc_time = timezone.now()
            >>> local_time = config.localize_datetime(utc_time)
        """
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt)
        return dt.astimezone(self.get_timezone())
    
    @classmethod
    def get_operational_timezone(cls):
        """
        Class method to get operational timezone.
        
        Returns:
            ZoneInfo: Timezone object for operational timezone
        """
        config = cls.get_instance()
        return config.get_timezone() if config else ZoneInfo('Africa/Kampala')
    
    # -------------------------------------------------------------------------
    # PERIOD NAMING METHODS
    # -------------------------------------------------------------------------
    
    def get_period_name(self, position, include_year=False, academic_year=None):
        """Enhanced period naming with more options"""
        max_periods = self.get_period_count()
        
        if position > max_periods or position < 1:
            return None
        
        # Handle custom names first
        if self.period_naming_convention == 'custom' and self.custom_period_names:
            base_name = self.custom_period_names.get(str(position))
            if base_name:
                return self._format_period_name(base_name, include_year, academic_year)
        
        # Handle different naming conventions
        if self.period_naming_convention == 'seasonal':
            base_name = self._get_seasonal_name(position)
        elif self.period_naming_convention == 'ordinal':
            base_name = self._get_ordinal_name(position)
        elif self.period_naming_convention == 'monthly':
            base_name = self._get_monthly_name(position)
        elif self.period_naming_convention == 'alpha':
            base_name = self._get_alpha_name(position)
        elif self.period_naming_convention == 'roman':
            base_name = self._get_roman_name(position)
        else:  # numeric
            base_name = self._get_numeric_name(position)
        
        return self._format_period_name(base_name, include_year, academic_year)
    
    def _format_period_name(self, base_name, include_year=False, academic_year=None):
        """Format the period name with optional year"""
        if include_year and academic_year:
            return f"{base_name} {academic_year}"
        return base_name
    
    def _get_seasonal_name(self, position):
        """Enhanced seasonal naming based on academic year type and period count"""
        period_count = self.get_period_count()
        period_type = self._get_period_type_name()
        
        # Use regional seasonal patterns
        if self.regional_season_type == 'tropical_wet_dry':
            if period_count == 2:
                seasons = {1: 'Dry Season', 2: 'Rainy Season'}
            elif period_count == 3:
                seasons = {1: 'Cool Dry', 2: 'Hot Dry', 3: 'Rainy Season'}
            else:
                seasons = {i+1: f"Period {i+1}" for i in range(period_count)}
        elif self.regional_season_type == 'desert':
            if period_count == 2:
                seasons = {1: 'Cool Season', 2: 'Hot Season'}
            elif period_count == 3:
                seasons = {1: 'Cool', 2: 'Hot', 3: 'Harmattan'}
            else:
                seasons = {i+1: f"Period {i+1}" for i in range(period_count)}
        elif self.regional_season_type == 'equatorial':
            return f"Period {position} {period_type}"
        elif self.regional_season_type == 'custom_regional' and self.custom_season_names:
            season = self.custom_season_names.get(str(position), f"Period {position}")
            return f"{season} {period_type}"
        else:
            # Temperate/Northern hemisphere seasons
            if period_count == 2:
                seasons = {1: 'Fall', 2: 'Spring'}
            elif period_count == 3:
                seasons = {1: 'Fall', 2: 'Spring', 3: 'Summer'}
            elif period_count == 4:
                seasons = {1: 'Fall', 2: 'Winter', 3: 'Spring', 4: 'Summer'}
            else:
                seasons = {i+1: f"Period {i+1}" for i in range(period_count)}
        
        season = seasons.get(position, f"Period {position}")
        return f"{season} {period_type}"
    
    def _get_ordinal_name(self, position):
        """Get ordinal names (First, Second, etc.)"""
        ordinals = [
            '', 'First', 'Second', 'Third', 'Fourth', 'Fifth', 
            'Sixth', 'Seventh', 'Eighth', 'Ninth', 'Tenth',
            'Eleventh', 'Twelfth', 'Thirteenth', 'Fourteenth', 'Fifteenth',
            'Sixteenth', 'Seventeenth', 'Eighteenth', 'Nineteenth', 'Twentieth'
        ]
        period_type = self._get_period_type_name()
        
        if position < len(ordinals):
            return f"{ordinals[position]} {period_type}"
        else:
            return f"{position}th {period_type}"
    
    def _get_monthly_name(self, position):
        """Get monthly names for systems that align with months"""
        months = [
            '', 'January', 'February', 'March', 'April', 'May', 'June',
            'July', 'August', 'September', 'October', 'November', 'December'
        ]
        
        # Start from academic year start month
        start_month = self.academic_year_start_month
        month_index = ((start_month - 1 + position - 1) % 12) + 1
        
        if month_index < len(months):
            period_type = self._get_period_type_name()
            return f"{months[month_index]} {period_type}"
        else:
            return self._get_numeric_name(position)
    
    def _get_alpha_name(self, position):
        """Get alphabetical names (A, B, C, etc.)"""
        import string
        period_type = self._get_period_type_name()
        
        if position <= 26:
            letter = string.ascii_uppercase[position - 1]
            return f"{period_type} {letter}"
        else:
            # For more than 26 periods, use AA, AB, etc.
            first_letter = string.ascii_uppercase[(position - 1) // 26]
            second_letter = string.ascii_uppercase[(position - 1) % 26]
            return f"{period_type} {first_letter}{second_letter}"
    
    def _get_roman_name(self, position):
        """Get Roman numeral names"""
        def int_to_roman(num):
            values = [1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1]
            symbols = ['M', 'CM', 'D', 'CD', 'C', 'XC', 'L', 'XL', 'X', 'IX', 'V', 'IV', 'I']
            result = ''
            for i, value in enumerate(values):
                count = num // value
                result += symbols[i] * count
                num -= value * count
            return result
        
        period_type = self._get_period_type_name()
        roman = int_to_roman(position)
        return f"{period_type} {roman}"
    
    def _get_numeric_name(self, position):
        """Get numeric names (Term 1, Term 2, etc.)"""
        period_type = self._get_period_type_name()
        return f"{period_type} {position}"
    
    def _get_period_type_name(self):
        """Enhanced period type name getter"""
        type_names = {
            'term': 'Term',
            'semester': 'Semester',
            'quarter': 'Quarter',
            'trimester': 'Trimester',
            'module': 'Module',
            'block': 'Block',
            'yearlong': 'Year',
            'intensive': 'Session',
            'custom': 'Period'
        }
        return type_names.get(self.term_system, 'Term')
    
    def get_period_type_name(self):
        """Get the singular name for the period type"""
        return self._get_period_type_name()

    def get_period_type_name_plural(self):
        """Enhanced plural name getter"""
        singular = self.get_period_type_name()
        
        # Handle special cases
        irregular_plurals = {
            'Module': 'Modules',
            'Year': 'Years',
        }
        
        if singular in irregular_plurals:
            return irregular_plurals[singular]
        elif singular.endswith('y'):
            return singular[:-1] + 'ies'
        else:
            return singular + 's'
    
    # -------------------------------------------------------------------------
    # UTILITY METHODS
    # -------------------------------------------------------------------------
    
    def is_last_period(self, position):
        """Check if the period position is the last in the academic year"""
        return position == self.get_period_count()
    
    def validate_period_number(self, period_number):
        """Validate if a period number is valid for the current system"""
        return 1 <= period_number <= self.get_period_count()
    
    def get_all_period_names(self, include_year=False, academic_year=None):
        """Get all period names for the current system"""
        return [
            self.get_period_name(i, include_year, academic_year) 
            for i in range(1, self.get_period_count() + 1)
        ]
    
    # -------------------------------------------------------------------------
    # SINGLETON PATTERN IMPLEMENTATION ⭐ IMPROVED
    # -------------------------------------------------------------------------
    
    @classmethod 
    def get_instance(cls):
        """
        Get or create the singleton instance of SchoolConfiguration.
        Improved singleton pattern using pk=1.
        """
        instance, created = cls.objects.get_or_create(
            pk=1,  # ⭐ Always use pk=1 for singleton
            defaults={
                'term_system': 'term',
                'periods_per_year': 3,
                'period_naming_convention': 'numeric',
                'custom_period_names': {},
                'academic_year_type': 'east_africa',
                'academic_year_start_month': 2,
                'academic_year_start_day': 1,
                'operational_timezone': 'Africa/Kampala',  # ⭐ NEW
                'regional_season_type': 'equatorial',
                'custom_season_names': {},
                'default_period_duration_weeks': 13,
                'enable_automatic_reminders': True,
                'enable_sms': False,
                'enable_email_notifications': True,
            }
        )
        return instance

    def save(self, *args, **kwargs):
        """Ensure only one instance exists (singleton pattern)"""
        self.pk = 1  # ⭐ Force pk=1
        super().save(*args, **kwargs)
        logger.debug(f"SchoolConfiguration saved with pk: {self.pk}")

    def delete(self, *args, **kwargs):
        """Prevent deletion of the singleton instance"""
        logger.warning("Attempted to delete SchoolConfiguration singleton instance - operation blocked")
        pass

    @classmethod 
    def get_cached_instance(cls):
        """
        Get school configuration instance with simple in-memory caching.
        This provides a cached version to avoid repeated database queries.
        """
        import threading
        if not hasattr(threading.current_thread(), '_school_config_cache'):
            threading.current_thread()._school_config_cache = None
        
        cached = threading.current_thread()._school_config_cache
        
        if cached is None:
            try:
                cached = cls.get_instance()
                threading.current_thread()._school_config_cache = cached
            except Exception:
                return None
        
        return cached

    @classmethod 
    def clear_cache(cls):
        """Clear the cached configuration instance"""
        import threading
        if hasattr(threading.current_thread(), '_school_config_cache'):
            threading.current_thread()._school_config_cache = None
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"School Configuration - {self.get_period_type_name_plural()}"

    class Meta:
        verbose_name = "School Configuration"
        verbose_name_plural = "School Configuration"

# =============================================================================
# FINANCIAL SETTINGS MODEL
# =============================================================================

class FinancialSettings(BaseModel):
    """
    Core financial settings for the school.
    Manages currency, formatting, payment terms, and financial policies.
    Singleton pattern - only one instance per school database.
    """

    # -------------------------------------------------------------------------
    # CHOICE FIELDS
    # -------------------------------------------------------------------------

    CURRENCY_POSITION_CHOICES = [
        ('BEFORE', 'Before amount (UGX 100.00)'),
        ('AFTER', 'After amount (100.00 UGX)'),
        ('BEFORE_NO_SPACE', 'Before, no space (UGX100.00)'),
        ('AFTER_NO_SPACE', 'After, no space (100.00UGX)'),
    ]

    # -------------------------------------------------------------------------
    # CURRENCY CONFIGURATION
    # -------------------------------------------------------------------------

    school_currency = models.CharField(
        "School Currency",
        max_length=3,
        default='UGX',
        help_text='Primary currency for this school (ISO 4217 code)'
    )

    currency_position = models.CharField(
        "Currency Position",
        max_length=20,
        choices=CURRENCY_POSITION_CHOICES,
        default='BEFORE',
        help_text="How to display currency symbols"
    )

    decimal_places = models.PositiveIntegerField(
        "Decimal Places",
        default=2,
        validators=[MinValueValidator(0), MaxValueValidator(4)],
        help_text="Number of decimal places for currency display (0-4)"
    )

    use_thousand_separator = models.BooleanField(
        "Use Thousand Separator",
        default=True,
        help_text="Display numbers with comma separators (e.g., 1,000,000)"
    )

    # -------------------------------------------------------------------------
    # NUMBERING CONFIGURATION
    # -------------------------------------------------------------------------

    invoice_prefix = models.CharField(
        "Invoice Number Prefix",
        max_length=10,
        default="INV",
        blank=True,
        help_text="Prefix for invoice numbers (leave blank for no prefix)"
    )

    include_year_in_invoice_number = models.BooleanField(
        "Include Year in Invoice Number",
        default=True,
        help_text="Include year in invoice number format"
    )

    payment_prefix = models.CharField(
        "Payment Number Prefix",
        max_length=10,
        default="PMT",
        blank=True,
        help_text="Prefix for payment numbers (leave blank for no prefix)"
    )

    include_year_in_payment_number = models.BooleanField(
        "Include Year in Payment Number",
        default=True,
        help_text="Include year in payment number format"
    )

    receipt_prefix = models.CharField(
        "Receipt Number Prefix",
        max_length=10,
        default="RCPT",
        blank=True,
        help_text="Prefix for receipt numbers (leave blank for no prefix)"
    )

    expense_prefix = models.CharField(
        "Expense Number Prefix",
        max_length=10,
        default="EXP",
        blank=True,
        help_text="Prefix for expense numbers (leave blank for no prefix)"
    )

    include_year_in_expense_number = models.BooleanField(
        "Include Year in Expense Number",
        default=True,
        help_text="Include year in expense number format"
    )

    # -------------------------------------------------------------------------
    # PAYMENT SETTINGS
    # -------------------------------------------------------------------------

    default_payment_terms_days = models.PositiveIntegerField(
        "Default Payment Terms (Days)",
        default=30,
        validators=[MinValueValidator(1), MaxValueValidator(365)],
        help_text="Default number of days for payment after invoice generation"
    )

    late_fee_enabled = models.BooleanField(
        "Enable Late Fees",
        default=True,
        help_text="Apply late fees to overdue invoices"
    )

    late_fee_percentage = models.DecimalField(
        "Late Fee Percentage",
        max_digits=5,
        decimal_places=2,
        default=Decimal('5.00'),
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text="Percentage charged on overdue amounts (0-100%)"
    )

    grace_period_days = models.PositiveIntegerField(
        "Grace Period (Days)",
        default=7,
        validators=[MinValueValidator(0), MaxValueValidator(90)],
        help_text="Days after due date before late fees apply"
    )

    minimum_payment_amount = models.DecimalField(
        "Minimum Payment Amount",
        max_digits=12,
        decimal_places=2,
        default=Decimal('1000.00'),
        validators=[MinValueValidator(Decimal('0'))],
        help_text="Minimum amount for any payment transaction in school currency"
    )

    allow_partial_payments = models.BooleanField(
        "Allow Partial Payments",
        default=True,
        help_text="Allow parents to make partial payments on invoices"
    )

    # -------------------------------------------------------------------------
    # SCHOLARSHIP & DISCOUNT SETTINGS
    # -------------------------------------------------------------------------

    auto_apply_scholarships = models.BooleanField(
        "Auto Apply Scholarships",
        default=True,
        help_text="Automatically apply approved scholarships to invoices"
    )

    scholarship_approval_required = models.BooleanField(
        "Scholarship Approval Required",
        default=False,
        help_text="Require approval for scholarships"
    )

    auto_apply_discounts = models.BooleanField(
        "Auto Apply Discounts",
        default=True,
        help_text="Automatically apply approved discounts to invoices"
    )

    discount_approval_required = models.BooleanField(
        "Discount Approval Required",
        default=True,
        help_text="Require approval for manual discounts above threshold"
    )

    discount_approval_threshold = models.DecimalField(
        "Discount Approval Threshold",
        max_digits=12,
        decimal_places=2,
        default=Decimal('100000.00'),
        validators=[MinValueValidator(Decimal('0'))],
        help_text="Discount amounts above this require approval"
    )

    early_payment_discount_enabled = models.BooleanField(
        "Enable Early Payment Discount",
        default=False,
        help_text="Offer discount for early payment"
    )

    early_payment_discount_percentage = models.DecimalField(
        "Early Payment Discount Percentage",
        max_digits=5,
        decimal_places=2,
        default=Decimal('2.00'),
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text="Percentage discount for early payment"
    )

    early_payment_discount_days = models.PositiveIntegerField(
        "Early Payment Discount Days",
        default=10,
        validators=[MinValueValidator(1), MaxValueValidator(90)],
        help_text="Days before due date to qualify for early payment discount"
    )

    # -------------------------------------------------------------------------
    # WORKFLOW SETTINGS
    # -------------------------------------------------------------------------

    expense_approval_required = models.BooleanField(
        "Expense Approval Required",
        default=True,
        help_text="Require approval for expenses above limit"
    )

    expense_approval_limit = models.DecimalField(
        "Expense Approval Limit",
        max_digits=12,
        decimal_places=2,
        default=Decimal('100000.00'),
        validators=[MinValueValidator(Decimal('0'))],
        help_text="Expense amounts above this require approval"
    )

    require_payment_confirmation = models.BooleanField(
        "Require Payment Confirmation",
        default=False,
        help_text="Require staff to confirm payment receipt before processing"
    )

    require_expense_receipts = models.BooleanField(
        "Require Expense Receipts",
        default=True,
        help_text="Require receipts/attachments for expense claims"
    )

    require_purchase_orders = models.BooleanField(
        "Require Purchase Orders",
        default=False,
        help_text="Require PO numbers for vendor invoices"
    )

    # -------------------------------------------------------------------------
    # COMMUNICATION SETTINGS
    # -------------------------------------------------------------------------

    send_invoice_emails = models.BooleanField(
        "Send Invoice Emails",
        default=True,
        help_text="Email invoices to parents"
    )

    send_payment_confirmations = models.BooleanField(
        "Send Payment Confirmations",
        default=True,
        help_text="Email payment receipts to parents"
    )

    send_overdue_reminders = models.BooleanField(
        "Send Overdue Reminders",
        default=True,
        help_text="Send automatic reminders for overdue payments"
    )

    overdue_reminder_days = models.PositiveIntegerField(
        "Overdue Reminder Frequency (Days)",
        default=7,
        validators=[MinValueValidator(1), MaxValueValidator(30)],
        help_text="Days between overdue payment reminders"
    )

    send_sms_notifications = models.BooleanField(
        "Send SMS Notifications",
        default=False,
        help_text="Send SMS notifications for financial transactions"
    )

    # -------------------------------------------------------------------------
    # TAX & ACCOUNTING SETTINGS
    # -------------------------------------------------------------------------

    include_tax_in_prices = models.BooleanField(
        "Include Tax in Prices",
        default=False,
        help_text="Whether prices include tax or tax is added on top"
    )

    default_tax_rate = models.DecimalField(
        "Default Tax Rate (%)",
        max_digits=5,
        decimal_places=2,
        default=Decimal('18.00'),
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text="Default tax rate to apply if no specific rate is set"
    )

    multi_currency_enabled = models.BooleanField(
        "Enable Multi-Currency",
        default=False,
        help_text="Allow transactions in multiple currencies"
    )

    auto_generate_recurring_invoices = models.BooleanField(
        "Auto-Generate Recurring Invoices",
        default=True,
        help_text="Automatically generate recurring invoices on schedule"
    )

    # -------------------------------------------------------------------------
    # AGING & COLLECTIONS
    # -------------------------------------------------------------------------

    invoice_aging_periods = models.JSONField(
        "Invoice Aging Periods",
        default=list,
        blank=True,
        help_text="Custom aging periods for AR aging reports (days)"
    )

    bad_debt_write_off_threshold = models.DecimalField(
        "Bad Debt Write-Off Threshold",
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0'))],
        help_text="Minimum amount to require approval for write-offs"
    )

    auto_write_off_days = models.PositiveIntegerField(
        "Auto Write-Off Days",
        default=365,
        validators=[MinValueValidator(90)],
        help_text="Days overdue before invoice can be written off"
    )

    # -------------------------------------------------------------------------
    # HELPER METHODS FOR ACCESSING RELATED MODELS
    # -------------------------------------------------------------------------

    def get_account_mappings(self):
        """Get or create core account mappings"""
        mappings, created = CoreAccountMappings.objects.get_or_create(
            financial_settings=self
        )
        return mappings

    def get_revenue_mappings(self):
        """Get or create revenue account mappings"""
        mappings, created = RevenueAccountMappings.objects.get_or_create(
            financial_settings=self
        )
        return mappings

    def get_payroll_mappings(self):
        """Get or create payroll account mappings"""
        mappings, created = PayrollAccountMappings.objects.get_or_create(
            financial_settings=self
        )
        return mappings

    def get_expense_mappings(self):
        """Get or create expense account mappings"""
        mappings, created = ExpenseAccountMappings.objects.get_or_create(
            financial_settings=self
        )
        return mappings

    def get_special_mappings(self):
        """Get or create special account mappings"""
        mappings, created = SpecialAccountMappings.objects.get_or_create(
            financial_settings=self
        )
        return mappings

    # -------------------------------------------------------------------------
    # CLASS METHODS - ACCOUNT HELPERS
    # -------------------------------------------------------------------------
    
    @classmethod
    def get_revenue_account(cls, invoice_type='TUITION'):
        """Get appropriate revenue account based on invoice type."""
        settings = cls.get_instance()
        if not settings:
            return None
        
        revenue_mappings = settings.get_revenue_mappings()
        core_mappings = settings.get_account_mappings()
        
        revenue_mapping = {
            'UNIFORM': revenue_mappings.uniform_sales_revenue_account,
            'TEXTBOOK': revenue_mappings.textbook_sales_revenue_account,
            'TRANSPORT': revenue_mappings.transport_revenue_account,
            'BOARDING': revenue_mappings.boarding_revenue_account,
            'MEALS': revenue_mappings.meals_revenue_account,
            'LATE_FEE': revenue_mappings.late_fee_revenue_account,
            'PENALTY': revenue_mappings.penalty_revenue_account,
            'SERVICE': core_mappings.default_service_revenue_account,
        }
        
        # Return specific account or fallback to default
        return revenue_mapping.get(invoice_type) or core_mappings.default_revenue_account
    
    @classmethod
    def get_cash_or_bank_account(cls, payment_method):
        """Get appropriate account based on payment method."""
        settings = cls.get_instance()
        if not settings:
            return None
        
        core_mappings = settings.get_account_mappings()
        special_mappings = settings.get_special_mappings()
        
        if hasattr(payment_method, 'code'):
            if payment_method.code in ['CASH', 'PETTY_CASH']:
                return special_mappings.petty_cash_account or core_mappings.default_cash_account
            elif payment_method.code == 'MOBILE_MONEY':
                return special_mappings.mobile_money_clearing_account or core_mappings.default_bank_account
        
        return core_mappings.default_bank_account
    
    @classmethod
    def get_default_account(cls, account_type):
        """Get a default account by type name."""
        settings = cls.get_instance()
        if not settings:
            return None
        
        core_mappings = settings.get_account_mappings()
        field_name = f'default_{account_type}_account'
        return getattr(core_mappings, field_name, None)

    # -------------------------------------------------------------------------
    # CLASS METHODS - Currency & Formatting
    # -------------------------------------------------------------------------

    @staticmethod
    def get_currency_choices():
        """Generate currency choices from pycountry or use defaults."""
        if pycountry:
            try:
                currencies = []
                for currency in pycountry.currencies:
                    currencies.append((
                        currency.alpha_3,
                        f"{currency.name} ({currency.alpha_3})"
                    ))
                return sorted(currencies, key=lambda x: x[1])
            except Exception:
                pass
        
        # Fallback to default currencies
        return [
            ('UGX', 'Ugandan Shilling (UGX)'),
            ('USD', 'US Dollar (USD)'),
            ('EUR', 'Euro (EUR)'),
            ('GBP', 'British Pound (GBP)'),
            ('KES', 'Kenyan Shilling (KES)'),
            ('TZS', 'Tanzanian Shilling (TZS)'),
        ]

    @classmethod
    def get_settings(cls):
        """Get the financial settings instance for this school"""
        return cls.get_instance()

    @classmethod
    def get_school_currency(cls):
        """Get school currency code"""
        settings = cls.get_settings()
        return settings.school_currency if settings else 'UGX'

    @classmethod
    def get_currency_info(cls):
        """Get complete currency configuration"""
        settings = cls.get_settings()
        if settings:
            return {
                'code': settings.school_currency,
                'decimal_places': settings.decimal_places,
                'position': settings.currency_position,
                'use_separator': settings.use_thousand_separator,
            }
        return {
            'code': 'UGX',
            'decimal_places': 2,
            'position': 'BEFORE',
            'use_separator': True,
        }

    # -------------------------------------------------------------------------
    # INSTANCE METHODS - Currency Formatting
    # -------------------------------------------------------------------------

    def format_currency(self, amount, include_symbol=True):
        """Format amount based on school settings."""
        try:
            amount = Decimal(str(amount or 0))
            formatted = f"{amount:,.{self.decimal_places}f}"

            if not self.use_thousand_separator:
                formatted = formatted.replace(',', '')

            if include_symbol:
                symbol = self.school_currency
                if self.currency_position == 'BEFORE':
                    return f"{symbol} {formatted}"
                elif self.currency_position == 'AFTER':
                    return f"{formatted} {symbol}"
                elif self.currency_position == 'BEFORE_NO_SPACE':
                    return f"{symbol}{formatted}"
                elif self.currency_position == 'AFTER_NO_SPACE':
                    return f"{formatted}{symbol}"
            return formatted

        except (ValueError, TypeError, InvalidOperation) as e:
            logger.warning(f"Error formatting currency: {e}")
            return f"{self.school_currency} 0.{'0' * self.decimal_places}"

    @classmethod
    def format_amount(cls, amount, include_symbol=True):
        """Class method to format amount using current settings"""
        settings = cls.get_instance()
        if settings:
            return settings.format_currency(amount, include_symbol)
        return f"UGX {amount:,.2f}" if include_symbol else f"{amount:,.2f}"

    def get_aging_periods(self):
        """Get aging periods or return defaults"""
        if self.invoice_aging_periods:
            return self.invoice_aging_periods
        return [30, 60, 90, 120]  # Default aging periods

    # -------------------------------------------------------------------------
    # VALIDATION METHODS
    # -------------------------------------------------------------------------

    def clean(self):
        """Validate financial settings"""
        super().clean()
        errors = {}

        # Validate currency code
        if self.school_currency:
            if pycountry:
                try:
                    currency = pycountry.currencies.get(alpha_3=self.school_currency.upper())
                    if not currency:
                        errors['school_currency'] = f"'{self.school_currency}' is not a valid ISO 4217 currency code"
                    else:
                        self.school_currency = self.school_currency.upper()
                except Exception:
                    if len(self.school_currency) != 3:
                        errors['school_currency'] = "Currency code must be 3 characters (ISO 4217)"
                    else:
                        self.school_currency = self.school_currency.upper()
            else:
                if len(self.school_currency) != 3:
                    errors['school_currency'] = "Currency code must be 3 characters (ISO 4217)"
                else:
                    self.school_currency = self.school_currency.upper()

        # Validate ranges
        if not (0 <= self.decimal_places <= 4):
            errors['decimal_places'] = "Decimal places must be between 0 and 4"

        if not (0 <= self.late_fee_percentage <= 100):
            errors['late_fee_percentage'] = "Late fee percentage must be between 0 and 100"

        if self.minimum_payment_amount < 0:
            errors['minimum_payment_amount'] = "Minimum payment amount cannot be negative"

        if self.discount_approval_threshold < 0:
            errors['discount_approval_threshold'] = "Discount approval threshold cannot be negative"

        if self.expense_approval_limit < 0:
            errors['expense_approval_limit'] = "Expense approval limit cannot be negative"

        if not (0 <= self.early_payment_discount_percentage <= 100):
            errors['early_payment_discount_percentage'] = "Early payment discount must be between 0 and 100"

        if not (0 <= self.default_tax_rate <= 100):
            errors['default_tax_rate'] = "Default tax rate must be between 0 and 100"

        if errors:
            raise ValidationError(errors)
        
    # -------------------------------------------------------------------------
    # SINGLETON PATTERN METHODS
    # -------------------------------------------------------------------------
    
    @classmethod
    def get_instance(cls):
        """Get or create the singleton instance of FinancialSettings."""
        instance, created = cls.objects.get_or_create(
            pk=1,
            defaults={
                'school_currency': 'UGX',
                'currency_position': 'BEFORE',
                'decimal_places': 2,
                'use_thousand_separator': True,
                'invoice_prefix': 'INV',
                'include_year_in_invoice_number': True,
                'payment_prefix': 'PMT',
                'include_year_in_payment_number': True,
                'receipt_prefix': 'RCPT',
                'expense_prefix': 'EXP',
                'include_year_in_expense_number': True,
                'default_payment_terms_days': 30,
                'late_fee_enabled': True,
                'late_fee_percentage': Decimal('5.00'),
                'grace_period_days': 7,
                'minimum_payment_amount': Decimal('1000.00'),
                'allow_partial_payments': True,
                'auto_apply_scholarships': True,
                'scholarship_approval_required': False,
                'auto_apply_discounts': True,
                'discount_approval_required': True,
                'discount_approval_threshold': Decimal('100000.00'),
                'early_payment_discount_enabled': False,
                'early_payment_discount_percentage': Decimal('2.00'),
                'early_payment_discount_days': 10,
                'expense_approval_required': True,
                'expense_approval_limit': Decimal('100000.00'),
                'require_payment_confirmation': False,
                'require_expense_receipts': True,
                'require_purchase_orders': False,
                'send_invoice_emails': True,
                'send_payment_confirmations': True,
                'send_overdue_reminders': True,
                'overdue_reminder_days': 7,
                'send_sms_notifications': False,
                'include_tax_in_prices': False,
                'default_tax_rate': Decimal('18.00'),
                'multi_currency_enabled': False,
                'auto_generate_recurring_invoices': True,
                'invoice_aging_periods': [30, 60, 90, 120],
                'bad_debt_write_off_threshold': Decimal('0.00'),
                'auto_write_off_days': 365,
            }
        )
        return instance

    def save(self, *args, **kwargs):
        """Ensure only one instance exists (singleton pattern)"""
        self.pk = 1
        super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        """Prevent deletion of the singleton instance"""
        pass
    
    @classmethod
    def load(cls):
        """Alternative method name for getting the instance."""
        return cls.get_instance()

    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------

    def __str__(self):
        return f"Financial Settings - {self.school_currency}"

    class Meta:
        verbose_name = "Financial Settings"
        verbose_name_plural = "Financial Settings"


# =============================================================================
# CORE ACCOUNT MAPPINGS
# =============================================================================

class CoreAccountMappings(BaseModel):
    """Core account mappings for basic financial transactions."""
    
    financial_settings = models.OneToOneField(
        'FinancialSettings',
        on_delete=models.CASCADE,
        related_name='core_account_mappings'
    )
    
    # Revenue & Receivables
    default_revenue_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='core_revenue_mappings',
        null=True,
        blank=True,
        help_text='Default account for fee revenue'
    )
    
    default_receivables_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='core_receivables_mappings',
        null=True,
        blank=True,
        help_text='Default account for student receivables'
    )
    
    default_service_revenue_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='core_service_revenue_mappings',
        null=True,
        blank=True,
        help_text='Default account for other service revenue'
    )
    
    # Cash & Bank
    default_cash_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='core_cash_mappings',
        null=True,
        blank=True,
        help_text='Default cash account for cash payments'
    )
    
    default_bank_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='core_bank_mappings',
        null=True,
        blank=True,
        help_text='Default bank account for bank payments'
    )
    
    # Basic Expenses & Payables
    default_expense_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='core_expense_mappings',
        null=True,
        blank=True,
        help_text='Default account for general expenses'
    )
    
    default_payables_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='core_payables_mappings',
        null=True,
        blank=True,
        help_text='Default account for accounts payable'
    )
    
    # Tax Accounts
    default_tax_payable_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='core_tax_payable_mappings',
        null=True,
        blank=True,
        help_text='Default account for tax payable'
    )
    
    default_tax_receivable_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='core_tax_receivable_mappings',
        null=True,
        blank=True,
        help_text='Default account for tax receivable'
    )
    
    # Scholarships & Discounts
    default_scholarship_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='core_scholarship_mappings',
        null=True,
        blank=True,
        help_text='Default account for scholarship expenses'
    )
    
    default_discount_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='core_discount_mappings',
        null=True,
        blank=True,
        help_text='Default account for fee discounts'
    )

    def __str__(self):
        return f"Core Account Mappings for {self.financial_settings}"

    class Meta:
        verbose_name = "Core Account Mappings"
        verbose_name_plural = "Core Account Mappings"


# =============================================================================
# REVENUE ACCOUNT MAPPINGS
# =============================================================================

class RevenueAccountMappings(BaseModel):
    """Specific revenue account mappings for different invoice types."""
    
    financial_settings = models.OneToOneField(
        'FinancialSettings',
        on_delete=models.CASCADE,
        related_name='revenue_account_mappings'
    )
    
    uniform_sales_revenue_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='uniform_revenue_mappings',
        null=True,
        blank=True,
        help_text='Revenue account for uniform sales'
    )
    
    textbook_sales_revenue_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='textbook_revenue_mappings',
        null=True,
        blank=True,
        help_text='Revenue account for textbook sales'
    )
    
    transport_revenue_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='transport_revenue_mappings',
        null=True,
        blank=True,
        help_text='Revenue account for transportation fees'
    )
    
    boarding_revenue_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='boarding_revenue_mappings',
        null=True,
        blank=True,
        help_text='Revenue account for boarding fees'
    )
    
    meals_revenue_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='meals_revenue_mappings',
        null=True,
        blank=True,
        help_text='Revenue account for meal fees'
    )
    
    late_fee_revenue_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='late_fee_revenue_mappings',
        null=True,
        blank=True,
        help_text='Revenue account for late payment fees'
    )
    
    penalty_revenue_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='penalty_revenue_mappings',
        null=True,
        blank=True,
        help_text='Revenue account for penalties and fines'
    )
    
    donation_revenue_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='donation_revenue_mappings',
        null=True,
        blank=True,
        help_text='Revenue account for donations received'
    )
    
    grant_revenue_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='grant_revenue_mappings',
        null=True,
        blank=True,
        help_text='Revenue account for grants received'
    )

    def __str__(self):
        return f"Revenue Account Mappings for {self.financial_settings}"

    class Meta:
        verbose_name = "Revenue Account Mappings"
        verbose_name_plural = "Revenue Account Mappings"


# =============================================================================
# EXPENSE ACCOUNT MAPPINGS
# =============================================================================

class ExpenseAccountMappings(BaseModel):
    """Expense account mappings for different expense categories."""
    
    financial_settings = models.OneToOneField(
        'FinancialSettings',
        on_delete=models.CASCADE,
        related_name='expense_account_mappings'
    )
    
    # Inventory & COGS
    default_inventory_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='inventory_mappings',
        null=True,
        blank=True,
        help_text='Default account for inventory asset'
    )
    
    default_cogs_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='cogs_mappings',
        null=True,
        blank=True,
        help_text='Default account for cost of goods sold'
    )
    
    # Operational Expenses
    supplies_expense_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='supplies_expense_mappings',
        null=True,
        blank=True,
        help_text='Expense account for school supplies'
    )
    
    utilities_expense_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='utilities_expense_mappings',
        null=True,
        blank=True,
        help_text='Expense account for utilities'
    )
    
    maintenance_expense_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='maintenance_expense_mappings',
        null=True,
        blank=True,
        help_text='Expense account for maintenance'
    )
    
    # Fixed Assets & Depreciation
    fixed_assets_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='fixed_assets_mappings',
        null=True,
        blank=True,
        help_text='Asset account for property, plant, equipment'
    )
    
    accumulated_depreciation_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='accumulated_depreciation_mappings',
        null=True,
        blank=True,
        help_text='Contra-asset account for depreciation'
    )
    
    depreciation_expense_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='depreciation_expense_mappings',
        null=True,
        blank=True,
        help_text='Expense account for depreciation charges'
    )

    def __str__(self):
        return f"Expense Account Mappings for {self.financial_settings}"

    class Meta:
        verbose_name = "Expense Account Mappings"
        verbose_name_plural = "Expense Account Mappings"


# =============================================================================
# PAYROLL ACCOUNT MAPPINGS
# =============================================================================

class PayrollAccountMappings(BaseModel):
    """Payroll-specific account mappings."""
    
    financial_settings = models.OneToOneField(
        'FinancialSettings',
        on_delete=models.CASCADE,
        related_name='payroll_account_mappings'
    )
    
    # Salary & Wages
    salaries_expense_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='salaries_expense_mappings',
        null=True,
        blank=True,
        help_text='Expense account for staff salaries'
    )
    
    wages_payable_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='wages_payable_mappings',
        null=True,
        blank=True,
        help_text='Liability account for accrued salaries'
    )
    
    # Payroll Tax & Statutory Deductions
    payroll_tax_payable_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='payroll_tax_mappings',
        null=True,
        blank=True,
        help_text='Liability account for payroll taxes'
    )
    
    social_security_payable_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='social_security_mappings',
        null=True,
        blank=True,
        help_text='Liability account for social security'
    )
    
    pension_payable_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='pension_payable_mappings',
        null=True,
        blank=True,
        help_text='Liability account for pension contributions'
    )
    
    # Staff Allowances
    housing_allowance_expense_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='housing_allowance_mappings',
        null=True,
        blank=True,
        help_text='Expense account for housing allowances'
    )
    
    transport_allowance_expense_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='transport_allowance_mappings',
        null=True,
        blank=True,
        help_text='Expense account for transport allowances'
    )
    
    medical_allowance_expense_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='medical_allowance_mappings',
        null=True,
        blank=True,
        help_text='Expense account for medical allowances'
    )
    
    general_allowance_expense_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='general_allowance_mappings',
        null=True,
        blank=True,
        help_text='Expense account for other allowances'
    )
    
    # Bonuses & Overtime
    overtime_expense_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='overtime_expense_mappings',
        null=True,
        blank=True,
        help_text='Expense account for overtime payments'
    )
    
    bonus_expense_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='bonus_expense_mappings',
        null=True,
        blank=True,
        help_text='Expense account for bonuses'
    )
    
    commission_expense_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='commission_expense_mappings',
        null=True,
        blank=True,
        help_text='Expense account for sales commissions'
    )
    
    # Staff Benefits
    staff_benefits_expense_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='staff_benefits_mappings',
        null=True,
        blank=True,
        help_text='Expense account for employee benefits'
    )
    
    staff_insurance_expense_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='staff_insurance_mappings',
        null=True,
        blank=True,
        help_text='Expense account for staff insurance'
    )
    
    staff_pension_contribution_expense_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='staff_pension_contribution_mappings',
        null=True,
        blank=True,
        help_text='Expense account for pension contributions'
    )

    def __str__(self):
        return f"Payroll Account Mappings for {self.financial_settings}"

    class Meta:
        verbose_name = "Payroll Account Mappings"
        verbose_name_plural = "Payroll Account Mappings"


# =============================================================================
# SPECIAL ACCOUNT MAPPINGS
# =============================================================================

class SpecialAccountMappings(BaseModel):
    """Special account mappings for specific transactions."""
    
    financial_settings = models.OneToOneField(
        'FinancialSettings',
        on_delete=models.CASCADE,
        related_name='special_account_mappings'
    )
    
    # Student Deposits & Credit Balances
    default_student_deposit_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='student_deposit_mappings',
        null=True,
        blank=True,
        help_text='Liability account for student deposits'
    )
    
    student_credit_balance_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='student_credit_mappings',
        null=True,
        blank=True,
        help_text='Liability account for student overpayments'
    )
    
    unearned_revenue_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='unearned_revenue_mappings',
        null=True,
        blank=True,
        help_text='Liability account for advance payments'
    )
    
    # Mobile Money & Payment Processing
    mobile_money_clearing_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='mobile_money_mappings',
        null=True,
        blank=True,
        help_text='Clearing account for mobile money'
    )
    
    payment_processing_fee_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='payment_processing_fee_mappings',
        null=True,
        blank=True,
        help_text='Expense account for payment processing fees'
    )
    
    # Refunds & Bad Debt
    default_refund_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='refund_mappings',
        null=True,
        blank=True,
        help_text='Contra-revenue account for refunds'
    )
    
    bad_debt_expense_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='bad_debt_mappings',
        null=True,
        blank=True,
        help_text='Expense account for bad debt write-offs'
    )
    
    allowance_for_doubtful_accounts = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='doubtful_accounts_mappings',
        null=True,
        blank=True,
        help_text='Contra-asset account for doubtful accounts'
    )
    
    # Currency & Rounding
    default_rounding_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='rounding_mappings',
        null=True,
        blank=True,
        help_text='Account for currency rounding differences'
    )
    
    default_currency_gain_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='currency_gain_mappings',
        null=True,
        blank=True,
        help_text='Account for foreign currency gains'
    )
    
    default_currency_loss_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='currency_loss_mappings',
        null=True,
        blank=True,
        help_text='Account for foreign currency losses'
    )
    
    # Withholding Tax
    withholding_tax_payable_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='withholding_tax_mappings',
        null=True,
        blank=True,
        help_text='Liability account for withholding tax'
    )
    
    # Petty Cash & Suspense
    petty_cash_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='petty_cash_mappings',
        null=True,
        blank=True,
        help_text='Cash account for petty cash fund'
    )
    
    suspense_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='suspense_mappings',
        null=True,
        blank=True,
        help_text='Temporary holding account'
    )
    
    bank_reconciliation_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='bank_reconciliation_mappings',
        null=True,
        blank=True,
        help_text='Temporary account for bank reconciliation'
    )
    
    # Staff Loans & Advances
    staff_loan_receivable_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='staff_loan_mappings',
        null=True,
        blank=True,
        help_text='Asset account for staff loans'
    )
    
    staff_advance_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='staff_advance_mappings',
        null=True,
        blank=True,
        help_text='Asset account for salary advances'
    )
    
    # Training & Recruitment
    recruitment_expense_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='recruitment_expense_mappings',
        null=True,
        blank=True,
        help_text='Expense account for recruitment costs'
    )
    
    staff_training_expense_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='staff_training_mappings',
        null=True,
        blank=True,
        help_text='Expense account for staff training'
    )
    
    # Severance & Gratuity
    severance_expense_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='severance_expense_mappings',
        null=True,
        blank=True,
        help_text='Expense account for severance payments'
    )
    
    gratuity_payable_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='gratuity_payable_mappings',
        null=True,
        blank=True,
        help_text='Liability account for gratuity accrued'
    )

    def __str__(self):
        return f"Special Account Mappings for {self.financial_settings}"

    class Meta:
        verbose_name = "Special Account Mappings"
        verbose_name_plural = "Special Account Mappings"

# =============================================================================
# FISCAL YEAR MODEL
# =============================================================================

class FiscalYear(BaseModel):
    """
    Fiscal/Academic year for school operations.
    Represents the entire year with multiple periods/terms within it.
    
    Changes from original:
    - Uses get_school_today() from utils for timezone-aware operations
    - Added is_upcoming() and is_past() methods
    - Improved documentation with examples
    """
    
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('ACTIVE', 'Active'),
        ('CLOSED', 'Closed'),
        ('LOCKED', 'Locked'),
    ]
    
    # Core fields
    name = models.CharField(
        "Academic Year Name",
        max_length=50,
        unique=True,
        help_text="e.g., '2024', '2024/2025', 'Academic Year 2024-2025'"
    )
    
    code = models.CharField(
        "Academic Year Code",
        max_length=20,
        unique=True,
        help_text="Short code e.g., 'AY2024', '2024-25'"
    )
    
    # Date range
    start_date = models.DateField(
        "Start Date",
        db_index=True,
        help_text="When this academic year begins"
    )
    
    end_date = models.DateField(
        "End Date",
        db_index=True,
        help_text="When this academic year ends"
    )
    
    # Status
    status = models.CharField(
        "Status",
        max_length=10,
        choices=STATUS_CHOICES,
        default='DRAFT',
        db_index=True
    )
    
    is_active = models.BooleanField(
        "Is Active",
        default=False,
        db_index=True,
        help_text="Only one academic year can be active at a time"
    )
    
    is_closed = models.BooleanField(
        "Is Closed",
        default=False,
        help_text="Academic year has been closed and finalized"
    )
    
    is_locked = models.BooleanField(
        "Is Locked",
        default=False,
        help_text="Academic year is locked for editing (for auditing)"
    )
    
    # Metadata
    description = models.TextField(
        "Description",
        blank=True,
        help_text="Optional description or notes about this academic year"
    )
    
    closed_at = models.DateTimeField(
        "Closed At",
        null=True,
        blank=True,
        help_text="When this academic year was closed"
    )
    
    closed_by_id = models.CharField(
        "Closed By",
        max_length=50,
        null=True,
        blank=True,
        help_text="User ID who closed this academic year"
    )
    
    class Meta:
        ordering = ['-start_date']
        indexes = [
            models.Index(fields=['start_date', 'end_date']),
            models.Index(fields=['status']),
            models.Index(fields=['is_active']),
        ]
        verbose_name = "Academic Year"
        verbose_name_plural = "Academic Years"
    
    def __str__(self):
        return self.name
    
    def clean(self):
        """Validate academic year"""
        super().clean()
        errors = {}
        
        # Validate date range
        if self.start_date and self.end_date:
            if self.start_date >= self.end_date:
                errors['end_date'] = "End date must be after start date"
            
            # Check for overlapping academic years
            overlapping = FiscalYear.objects.filter(
                models.Q(start_date__lte=self.end_date) & models.Q(end_date__gte=self.start_date)
            ).exclude(pk=self.pk)
            
            if overlapping.exists():
                errors['start_date'] = f"This academic year overlaps with: {', '.join([str(fy) for fy in overlapping])}"
        
        if errors:
            raise ValidationError(errors)
    
    def save(self, *args, **kwargs):
        """Save with automatic status sync"""
        # Sync status field with boolean flags
        if self.is_locked:
            self.status = 'LOCKED'
        elif self.is_closed:
            self.status = 'CLOSED'
        elif self.is_active:
            self.status = 'ACTIVE'
        else:
            self.status = 'DRAFT'
        
        # Validate before saving
        self.full_clean()
        
        # If setting as active, deactivate other academic years
        if self.is_active:
            FiscalYear.objects.exclude(pk=self.pk).update(is_active=False)
        
        super().save(*args, **kwargs)
    
    # -------------------------------------------------------------------------
    # CLASS METHODS
    # -------------------------------------------------------------------------
    
    @classmethod
    def get_active_fiscal_year(cls):
        """Get the currently active academic year"""
        return cls.objects.filter(is_active=True).first()
    
    @classmethod
    def get_current_year_name(cls):
        """Get the current academic year name"""
        active = cls.get_active_fiscal_year()
        return active.name if active else None
    
    @classmethod
    def get_by_date(cls, check_date):
        """Get academic year that contains a specific date"""
        return cls.objects.filter(
            start_date__lte=check_date,
            end_date__gte=check_date
        ).first()

    # -------------------------------------------------------------------------
    # PROGRESS TRACKING METHODS ⭐ USES TIMEZONE-AWARE UTILS
    # -------------------------------------------------------------------------

    def get_progress_percentage(self):
        """
        Calculate the progress percentage of this academic year using school timezone.
        
        Returns:
            float: Progress percentage (0-100)
        
        Example:
            >>> fiscal_year = FiscalYear.objects.get(name='2024')
            >>> progress = fiscal_year.get_progress_percentage()
            >>> print(f"Year is {progress}% complete")
        """
        from core.utils import get_school_today  # ⭐ USE SCHOOL TIMEZONE
        
        today = get_school_today()
        duration_days = self.get_duration_days()
        
        # If academic year hasn't started yet
        if today < self.start_date:
            return 0.0
        
        # If academic year has ended
        if today > self.end_date:
            return 100.0
        
        # Calculate progress
        if duration_days > 0:
            elapsed_days = (today - self.start_date).days
            progress = (elapsed_days / duration_days) * 100
            return round(min(progress, 100.0), 2)
        
        return 0.0
    
    def get_elapsed_days(self):
        """
        Get the number of days elapsed in this academic year using school timezone.
        
        Returns:
            int: Days elapsed (0 if not started, duration if ended)
        """
        from core.utils import get_school_today  # ⭐ USE SCHOOL TIMEZONE
        
        today = get_school_today()
        
        if today < self.start_date:
            return 0
        
        if today > self.end_date:
            return self.get_duration_days()
        
        return (today - self.start_date).days
    
    def get_remaining_days(self):
        """
        Get the number of days remaining in this academic year using school timezone.
        
        Returns:
            int: Days remaining (0 if ended, duration if not started)
        """
        from core.utils import get_school_today  # ⭐ USE SCHOOL TIMEZONE
        
        today = get_school_today()
        
        if today > self.end_date:
            return 0
        
        if today < self.start_date:
            return self.get_duration_days()
        
        return (self.end_date - today).days
    
    def is_current(self):
        """
        Check if today's date falls within this academic year using school timezone.
        
        Returns:
            bool: True if current, False otherwise
        
        Example:
            >>> if fiscal_year.is_current():
            >>>     print("This is the current academic year")
        """
        from core.utils import get_school_today  # ⭐ USE SCHOOL TIMEZONE
        
        today = get_school_today()
        return self.start_date <= today <= self.end_date
    
    def is_upcoming(self):
        """
        Check if this academic year is upcoming (starts in the future) using school timezone.
        ⭐ NEW METHOD
        
        Returns:
            bool: True if upcoming, False otherwise
        
        Example:
            >>> upcoming_years = FiscalYear.objects.filter(is_active=False)
            >>> for year in upcoming_years:
            >>>     if year.is_upcoming():
            >>>         print(f"{year.name} starts in {year.get_remaining_days()} days")
        """
        from core.utils import get_school_today  # ⭐ USE SCHOOL TIMEZONE
        
        today = get_school_today()
        return self.start_date > today
    
    def is_past(self):
        """
        Check if this academic year is in the past (already ended) using school timezone.
        ⭐ NEW METHOD
        
        Returns:
            bool: True if past, False otherwise
        
        Example:
            >>> past_years = FiscalYear.objects.all()
            >>> for year in past_years:
            >>>     if year.is_past() and not year.is_closed:
            >>>         print(f"Warning: {year.name} ended but is not closed")
        """
        from core.utils import get_school_today  # ⭐ USE SCHOOL TIMEZONE
        
        today = get_school_today()
        return self.end_date < today
    
    def get_status_display_class(self):
        """
        Get CSS class for status display.
        
        Returns:
            str: CSS class name
        """
        if self.is_locked:
            return 'status-locked'
        elif self.is_closed:
            return 'status-closed'
        elif self.is_active:
            return 'status-active'
        else:
            return 'status-draft'
    
    # -------------------------------------------------------------------------
    # INSTANCE METHODS
    # -------------------------------------------------------------------------
    
    def close_fiscal_year(self, user=None):
        """Close this academic year using school timezone for timestamp"""
        if self.is_closed:
            return
        
        from core.utils import get_school_current_time  # ⭐ USE SCHOOL TIMEZONE
        
        # Close all periods in this academic year
        for period in self.periods.all():
            if not period.is_closed:
                period.close_period(user)
        
        self.is_closed = True
        self.is_active = False
        self.status = 'CLOSED'
        self.closed_at = get_school_current_time()  # ⭐ USE SCHOOL TIMEZONE
        
        if user:
            self.closed_by_id = str(user.id) if hasattr(user, 'id') else str(user.pk)
        
        self.save()
    
    def lock_fiscal_year(self):
        """Lock this academic year for editing"""
        if not self.is_closed:
            raise ValidationError("Academic year must be closed before it can be locked")
        
        # Lock all periods in this academic year
        self.periods.all().update(is_locked=True, status='LOCKED')
        
        self.is_locked = True
        self.status = 'LOCKED'
        self.save()
    
    def unlock_fiscal_year(self):
        """Unlock this academic year"""
        # Unlock all periods in this academic year
        for period in self.periods.all():
            period.unlock_period()
        
        self.is_locked = False
        self.status = 'CLOSED' if self.is_closed else 'DRAFT'
        self.save()
    
    def is_date_in_year(self, check_date):
        """Check if a date falls within this academic year"""
        return self.start_date <= check_date <= self.end_date
    
    def get_duration_days(self):
        """Get the duration of this academic year in days"""
        if self.start_date and self.end_date:
            return (self.end_date - self.start_date).days + 1
        return 0
    
    def get_duration_weeks(self):
        """Get the duration of this academic year in weeks"""
        days = self.get_duration_days()
        return days // 7 if days > 0 else 0
    
    def get_period_count(self):
        """Get the number of periods in this academic year"""
        return self.periods.count()
    
    def get_active_period(self):
        """Get the currently active period within this academic year"""
        return self.periods.filter(is_active=True).first()
    
    def get_all_periods(self):
        """Get all periods in this academic year, ordered by period number"""
        return self.periods.all().order_by('period_number')
    
    def can_be_deleted(self):
        """Check if this academic year can be deleted"""
        # Can't delete if it has periods with transactions
        return self.get_period_count() == 0
    
    def get_closed_by(self):
        """Get user who closed this academic year"""
        if not self.closed_by_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            return User.objects.using('default').get(id=self.closed_by_id)
        except Exception as e:
            logger.error(f"Error fetching closed_by user: {e}")
            return None

    @property
    def closed_by_name(self):
        """Get name of user who closed academic year"""
        user = self.get_closed_by()
        if user:
            return user.get_full_name() or user.username
        return "System"

# =============================================================================
# FISCAL PERIOD MODEL
# =============================================================================

class FiscalPeriod(BaseModel):
    """
    Fiscal/Financial period within a fiscal year.
    
    Purpose: Track financial transaction windows and accounting periods.
    Unlike AcademicSession (which tracks teaching/learning periods with strict dates),
    FiscalPeriod provides flexible windows for financial operations.
    
    Changes from original:
    - Uses get_school_today() from utils for timezone-aware operations
    - Added is_upcoming() and is_past() methods
    - Improved documentation with examples
    """
    
    # -------------------------------------------------------------------------
    # PERIOD TYPE CHOICES
    # -------------------------------------------------------------------------
    
    PERIOD_TYPE_CHOICES = [
        ('ACADEMIC_ALIGNED', 'Academic-Aligned Period'),
        ('BREAK_PERIOD', 'Break/Holiday Period'),
        ('GRACE_PERIOD', 'Grace Period'),
        ('MONTHLY', 'Monthly Period'),
        ('QUARTERLY', 'Quarterly Period'),
        ('TERTIAL', 'Tertial Period'),  
        ('SEMI_ANNUAL', 'Semi-Annual Period'),
        ('ANNUAL', 'Annual Period'),
        ('CUSTOM', 'Custom Period'),
    ]
    
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('ACTIVE', 'Active'),
        ('CLOSED', 'Closed'),
        ('LOCKED', 'Locked'),
    ]
    
    # -------------------------------------------------------------------------
    # CORE FIELDS
    # -------------------------------------------------------------------------
    
    fiscal_year = models.ForeignKey(
        FiscalYear,
        on_delete=models.PROTECT,
        related_name='fiscal_periods',
        verbose_name="Fiscal Year",
        help_text="Parent fiscal year for accounting hierarchy"
    )
    
    name = models.CharField(
        "Period Name",
        max_length=100,
        help_text="e.g., 'Term 1 2024 Fiscal Period', 'Q1 2024', 'April Break 2024'"
    )
    
    code = models.CharField(
        "Period Code",
        max_length=20,
        unique=True,
        help_text="Unique code e.g., 'FP_2024_T1', 'Q1_2024', 'BREAK_APR_2024'"
    )
    
    period_number = models.DecimalField(
        "Period Number",
        max_digits=4,
        decimal_places=1,
        validators=[MinValueValidator(Decimal('0.1'))],
        db_index=True,
        help_text="Sequential number within fiscal year (1, 2, 3... or 1.5 for break periods)"
    )
    
    period_type = models.CharField(
        "Period Type",
        max_length=20,
        choices=PERIOD_TYPE_CHOICES,
        default='ACADEMIC_ALIGNED',
        db_index=True,
        help_text="Type of fiscal period"
    )
    
    # -------------------------------------------------------------------------
    # ACADEMIC SESSION RELATIONSHIP (Optional)
    # -------------------------------------------------------------------------
    
    related_academic_session = models.ForeignKey(
        'academics.AcademicSession',
        on_delete=models.SET_NULL,
        related_name='fiscal_periods',
        null=True,
        blank=True,
        verbose_name="Related Academic Session",
        help_text="Associated academic session (if applicable) - for reference/tracking only"
    )
    
    # -------------------------------------------------------------------------
    # DATE RANGE (Flexible - can extend beyond academic session)
    # -------------------------------------------------------------------------
    
    start_date = models.DateField(
        "Start Date",
        db_index=True,
        help_text="When this fiscal period begins"
    )
    
    end_date = models.DateField(
        "End Date",
        db_index=True,
        help_text="When this fiscal period ends"
    )
    
    # -------------------------------------------------------------------------
    # STATUS AND CLOSURE
    # -------------------------------------------------------------------------
    
    status = models.CharField(
        "Status",
        max_length=10,
        choices=STATUS_CHOICES,
        default='DRAFT',
        db_index=True
    )
    
    is_active = models.BooleanField(
        "Is Active",
        default=False,
        db_index=True,
        help_text="Whether this period is currently active for transactions"
    )
    
    is_closed = models.BooleanField(
        "Is Closed",
        default=False,
        help_text="Period has been closed (month-end/period-end close)"
    )
    
    is_locked = models.BooleanField(
        "Is Locked",
        default=False,
        help_text="Period is locked for audit compliance (no changes allowed)"
    )
    
    # Closure tracking
    closed_at = models.DateTimeField(
        "Closed At",
        null=True,
        blank=True,
        help_text="When this period was closed"
    )
    
    closed_by_id = models.CharField(
        "Closed By",
        max_length=50,
        null=True,
        blank=True,
        help_text="User ID who closed this period"
    )
    
    locked_at = models.DateTimeField(
        "Locked At",
        null=True,
        blank=True,
        help_text="When this period was locked"
    )
    
    locked_by_id = models.CharField(
        "Locked By",
        max_length=50,
        null=True,
        blank=True,
        help_text="User ID who locked this period"
    )
    
    # -------------------------------------------------------------------------
    # FINANCIAL SETTINGS
    # -------------------------------------------------------------------------
    
    allow_advance_payments = models.BooleanField(
        "Allow Advance Payments",
        default=True,
        help_text="Accept payments for future academic sessions"
    )
    
    allow_arrears_payments = models.BooleanField(
        "Allow Arrears Payments",
        default=True,
        help_text="Accept payments for past academic sessions"
    )
    
    allow_invoice_generation = models.BooleanField(
        "Allow Invoice Generation",
        default=True,
        help_text="Allow creating new invoices in this period"
    )
    
    allow_refunds = models.BooleanField(
        "Allow Refunds",
        default=True,
        help_text="Allow processing refunds in this period"
    )
    
    require_approval_for_transactions = models.BooleanField(
        "Require Approval",
        default=False,
        help_text="Require manager approval for transactions in this period"
    )
    
    # -------------------------------------------------------------------------
    # AUTO-CLOSURE SETTINGS
    # -------------------------------------------------------------------------
    
    auto_close_date = models.DateField(
        "Auto Close Date",
        null=True,
        blank=True,
        help_text="Automatically close this period on this date"
    )
    
    grace_period_days = models.PositiveIntegerField(
        "Grace Period Days",
        default=0,
        help_text="Days beyond end_date when transactions are still accepted"
    )
    
    # -------------------------------------------------------------------------
    # METADATA
    # -------------------------------------------------------------------------
    
    description = models.TextField(
        "Description",
        blank=True,
        help_text="Optional description or notes about this fiscal period"
    )
    
    notes = models.TextField(
        "Internal Notes",
        blank=True,
        help_text="Internal notes for accounting team"
    )
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        ordering = ['fiscal_year', 'period_number']
        unique_together = [['fiscal_year', 'period_number']]
        verbose_name = "Fiscal Period"
        verbose_name_plural = "Fiscal Periods"
        indexes = [
            models.Index(fields=['fiscal_year', 'period_number']),
            models.Index(fields=['start_date', 'end_date']),
            models.Index(fields=['status', 'is_active']),
            models.Index(fields=['period_type']),
            models.Index(fields=['is_active', 'is_closed']),
            models.Index(fields=['related_academic_session']),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(start_date__lt=models.F('end_date')),
                name='fiscal_period_start_before_end'
            ),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.name} ({self.fiscal_year})"
    
    def get_full_display(self):
        """Get full display with dates"""
        return f"{self.name} ({self.start_date} to {self.end_date})"
    
    # -------------------------------------------------------------------------
    # VALIDATION
    # -------------------------------------------------------------------------
    
    def clean(self):
        """Validate fiscal period"""
        super().clean()
        errors = {}
        
        # Date validation
        if self.start_date and self.end_date:
            if self.start_date >= self.end_date:
                errors['end_date'] = "End date must be after start date"
        
        # Fiscal year validation
        if self.fiscal_year and self.start_date and self.end_date:
            if self.start_date < self.fiscal_year.start_date:
                errors['start_date'] = (
                    f"Period cannot start before fiscal year start date "
                    f"({self.fiscal_year.start_date})"
                )
            if self.end_date > self.fiscal_year.end_date:
                errors['end_date'] = (
                    f"Period cannot end after fiscal year end date "
                    f"({self.fiscal_year.end_date})"
                )
        
        # Academic session validation (if applicable)
        if self.related_academic_session and self.period_type == 'ACADEMIC_ALIGNED':
            session = self.related_academic_session
            
            if self.start_date > session.start_date:
                errors['start_date'] = (
                    f"For academic-aligned periods, start date should be at or before "
                    f"session start ({session.start_date})"
                )
            
            if self.end_date < session.end_date:
                errors['end_date'] = (
                    f"For academic-aligned periods, end date should be at or after "
                    f"session end ({session.end_date})"
                )
        
        # Check for overlapping periods within same fiscal year
        if self.fiscal_year and self.start_date and self.end_date:
            overlapping = FiscalPeriod.objects.filter(
                fiscal_year=self.fiscal_year,
                start_date__lt=self.end_date,
                end_date__gt=self.start_date
            ).exclude(pk=self.pk)
            
            if overlapping.exists():
                errors['start_date'] = (
                    f"This period overlaps with: {', '.join([str(p) for p in overlapping])}"
                )
        
        if errors:
            raise ValidationError(errors)
    
    def save(self, *args, **kwargs):
        """Save with automatic status sync"""
        # Sync status field with boolean flags
        if self.is_locked:
            self.status = 'LOCKED'
        elif self.is_closed:
            self.status = 'CLOSED'
        elif self.is_active:
            self.status = 'ACTIVE'
        else:
            self.status = 'DRAFT'
        
        # Validate before saving
        self.full_clean()
        
        super().save(*args, **kwargs)
    
    # -------------------------------------------------------------------------
    # TRANSACTION PERMISSION METHODS
    # -------------------------------------------------------------------------
    
    def can_accept_transactions(self):
        """
        Check if this period can accept financial transactions using school timezone.
        
        Returns:
            bool: True if transactions allowed, False otherwise
        """
        from core.utils import get_school_today  # ⭐ USE SCHOOL TIMEZONE
        
        if self.is_closed or self.is_locked:
            return False
        
        if not self.is_active:
            return False
        
        today = get_school_today()
        
        # Check if within date range
        if not (self.start_date <= today <= self.end_date):
            # Check grace period
            if self.grace_period_days > 0:
                grace_end = self.end_date + timedelta(days=self.grace_period_days)
                if today > grace_end:
                    return False
            else:
                return False
        
        return True
    
    def can_accept_payments(self):
        """Check if period can accept payment receipts"""
        return self.can_accept_transactions()
    
    def can_generate_invoices(self):
        """Check if period can generate new invoices"""
        return self.can_accept_transactions() and self.allow_invoice_generation
    
    def can_process_refunds(self):
        """Check if period can process refunds"""
        return self.can_accept_transactions() and self.allow_refunds
    
    def can_accept_advance_payment(self):
        """Check if period accepts advance payments"""
        return self.can_accept_transactions() and self.allow_advance_payments
    
    def can_accept_arrears_payment(self):
        """Check if period accepts arrears payments"""
        return self.can_accept_transactions() and self.allow_arrears_payments
    
    # -------------------------------------------------------------------------
    # CLOSURE METHODS
    # -------------------------------------------------------------------------
    
    def close_period(self, user=None):
        """
        Close this fiscal period (month-end/period-end close) using school timezone.
        
        Args:
            user: User performing the closure
        """
        from core.utils import get_school_current_time  # ⭐ USE SCHOOL TIMEZONE
        
        if self.is_closed:
            logger.warning(f"Fiscal period {self} is already closed")
            return
        
        self.is_closed = True
        self.is_active = False
        self.status = 'CLOSED'
        self.closed_at = get_school_current_time()  # ⭐ USE SCHOOL TIMEZONE
        
        if user:
            self.closed_by_id = str(user.id) if hasattr(user, 'id') else str(user.pk)
        
        self.save()
        
        logger.info(f"Fiscal period {self} closed by {self.get_closed_by_name()}")
    
    def lock_period(self, user=None):
        """
        Lock period for audit compliance using school timezone.
        Once locked, no changes can be made to transactions in this period.
        
        Args:
            user: User performing the lock
        """
        from core.utils import get_school_current_time  # ⭐ USE SCHOOL TIMEZONE
        
        if not self.is_closed:
            raise ValidationError("Period must be closed before it can be locked")
        
        if self.is_locked:
            logger.warning(f"Fiscal period {self} is already locked")
            return
        
        self.is_locked = True
        self.status = 'LOCKED'
        self.locked_at = get_school_current_time()  # ⭐ USE SCHOOL TIMEZONE
        
        if user:
            self.locked_by_id = str(user.id) if hasattr(user, 'id') else str(user.pk)
        
        self.save()
        
        logger.info(f"Fiscal period {self} locked by {self.get_locked_by_name()}")
    
    def unlock_period(self, user=None):
        """
        Unlock period (requires proper authorization).
        
        Args:
            user: User performing the unlock
        """
        if not self.is_locked:
            logger.warning(f"Fiscal period {self} is not locked")
            return
        
        self.is_locked = False
        self.status = 'CLOSED' if self.is_closed else 'DRAFT'
        self.locked_at = None
        self.locked_by_id = None
        
        self.save()
        
        user_name = user.get_full_name() if user else "System"
        logger.warning(f"Fiscal period {self} unlocked by {user_name}")
    
    def reopen_period(self, user=None):
        """
        Reopen a closed period (requires proper authorization).
        
        Args:
            user: User performing the reopen
        """
        if self.is_locked:
            raise ValidationError("Cannot reopen a locked period. Unlock it first.")
        
        if not self.is_closed:
            logger.warning(f"Fiscal period {self} is not closed")
            return
        
        self.is_closed = False
        self.is_active = True
        self.status = 'ACTIVE'
        self.closed_at = None
        self.closed_by_id = None
        
        self.save()
        
        user_name = user.get_full_name() if user else "System"
        logger.warning(f"Fiscal period {self} reopened by {user_name}")
    
    # -------------------------------------------------------------------------
    # STATUS CHECK METHODS ⭐ USES TIMEZONE-AWARE UTILS
    # -------------------------------------------------------------------------
    
    def is_current(self):
        """
        Check if today's date falls within this period using school timezone.
        
        Returns:
            bool: True if current, False otherwise
        """
        from core.utils import get_school_today  # ⭐ USE SCHOOL TIMEZONE
        
        today = get_school_today()
        return self.start_date <= today <= self.end_date and self.is_active
    
    def is_current_period(self):
        """Alias for is_current() for consistency"""
        return self.is_current()
    
    def is_upcoming(self):
        """
        Check if period is in the future using school timezone.
        ⭐ NEW METHOD
        
        Returns:
            bool: True if upcoming, False otherwise
        """
        from core.utils import get_school_today  # ⭐ USE SCHOOL TIMEZONE
        
        today = get_school_today()
        return self.start_date > today
    
    def is_past(self):
        """
        Check if period has ended using school timezone.
        ⭐ NEW METHOD
        
        Returns:
            bool: True if past, False otherwise
        """
        from core.utils import get_school_today  # ⭐ USE SCHOOL TIMEZONE
        
        today = get_school_today()
        return self.end_date < today
    
    def is_in_grace_period(self):
        """Check if currently in grace period using school timezone"""
        from core.utils import get_school_today  # ⭐ USE SCHOOL TIMEZONE
        
        if self.grace_period_days == 0:
            return False
        
        today = get_school_today()
        if today <= self.end_date:
            return False
        
        grace_end = self.end_date + timedelta(days=self.grace_period_days)
        return today <= grace_end
    
    # -------------------------------------------------------------------------
    # DURATION AND PROGRESS METHODS ⭐ USES TIMEZONE-AWARE UTILS
    # -------------------------------------------------------------------------
    
    def get_duration_days(self):
        """Get the duration of this period in days"""
        if self.start_date and self.end_date:
            return (self.end_date - self.start_date).days + 1
        return 0
    
    def get_duration_weeks(self):
        """Get the duration of this period in weeks"""
        days = self.get_duration_days()
        return days // 7 if days > 0 else 0
    
    def get_duration_months(self):
        """Get the approximate duration of this period in months"""
        days = self.get_duration_days()
        return days // 30 if days > 0 else 0
    
    def get_progress_percentage(self):
        """
        Calculate the progress percentage of this period using school timezone.
        
        Returns:
            float: Progress percentage (0-100)
        """
        from core.utils import get_school_today  # ⭐ USE SCHOOL TIMEZONE
        
        today = get_school_today()
        duration_days = self.get_duration_days()
        
        if today < self.start_date:
            return 0.0
        
        if today > self.end_date:
            return 100.0
        
        if duration_days > 0:
            elapsed_days = (today - self.start_date).days
            progress = (elapsed_days / duration_days) * 100
            return round(min(progress, 100.0), 2)
        
        return 0.0
    
    def get_elapsed_days(self):
        """Get the number of days elapsed in this period using school timezone"""
        from core.utils import get_school_today  # ⭐ USE SCHOOL TIMEZONE
        
        today = get_school_today()
        
        if today < self.start_date:
            return 0
        
        if today > self.end_date:
            return self.get_duration_days()
        
        return (today - self.start_date).days
    
    def get_remaining_days(self):
        """Get the number of days remaining in this period using school timezone"""
        from core.utils import get_school_today  # ⭐ USE SCHOOL TIMEZONE
        
        today = get_school_today()
        
        if today > self.end_date:
            return 0
        
        if today < self.start_date:
            return self.get_duration_days()
        
        return (self.end_date - today).days
    
    # -------------------------------------------------------------------------
    # USER REFERENCE METHODS
    # -------------------------------------------------------------------------
    
    def get_closed_by(self):
        """Get user who closed this period"""
        if not self.closed_by_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            return User.objects.using('default').get(id=self.closed_by_id)
        except Exception as e:
            logger.error(f"Error fetching closed_by user: {e}")
            return None
    
    def get_closed_by_name(self):
        """Get name of user who closed period"""
        user = self.get_closed_by()
        if user:
            return user.get_full_name() or user.username
        return "System"
    
    def get_locked_by(self):
        """Get user who locked this period"""
        if not self.locked_by_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            return User.objects.using('default').get(id=self.locked_by_id)
        except Exception as e:
            logger.error(f"Error fetching locked_by user: {e}")
            return None
    
    def get_locked_by_name(self):
        """Get name of user who locked period"""
        user = self.get_locked_by()
        if user:
            return user.get_full_name() or user.username
        return "System"
    
    # -------------------------------------------------------------------------
    # DISPLAY HELPER METHODS
    # -------------------------------------------------------------------------
    
    def get_status_display_class(self):
        """Get CSS class for status display"""
        if self.is_locked:
            return 'status-locked'
        elif self.is_closed:
            return 'status-closed'
        elif self.is_active:
            return 'status-active'
        else:
            return 'status-draft'
    
    def get_period_type_badge_class(self):
        """Get CSS class for period type badge"""
        badge_map = {
            'ACADEMIC_ALIGNED': 'badge-primary',
            'BREAK_PERIOD': 'badge-info',
            'GRACE_PERIOD': 'badge-warning',
            'MONTHLY': 'badge-secondary',
            'QUARTERLY': 'badge-success',
            'TERTIAL': 'badge-purple',
            'SEMI_ANNUAL': 'badge-dark',
            'ANNUAL': 'badge-danger',
            'CUSTOM': 'badge-light',
        }
        return badge_map.get(self.period_type, 'badge-secondary')
    
    # -------------------------------------------------------------------------
    # CLASS METHODS - CURRENT PERIOD
    # -------------------------------------------------------------------------
    
    @classmethod
    def get_current_fiscal_period(cls):
        """
        Get the current active fiscal period for transactions using school timezone.
        
        Returns:
            FiscalPeriod or None: Currently active period
        """
        from core.utils import get_school_today  # ⭐ USE SCHOOL TIMEZONE
        
        today = get_school_today()
        return cls.objects.filter(
            start_date__lte=today,
            end_date__gte=today,
            is_active=True,
            is_closed=False
        ).first()
    
    @classmethod
    def get_current_or_upcoming(cls):
        """Get current period or next upcoming period"""
        from core.utils import get_school_today  # ⭐ USE SCHOOL TIMEZONE
        
        current = cls.get_current_fiscal_period()
        if current:
            return current
        
        # Get next upcoming period
        today = get_school_today()
        return cls.objects.filter(
            start_date__gt=today,
            is_active=True
        ).order_by('start_date').first()
    
    # -------------------------------------------------------------------------
    # FINANCIAL SUMMARY METHODS
    # -------------------------------------------------------------------------
    
    def get_total_invoiced(self):
        """Get total amount invoiced in this period"""
        try:
            from django.db.models import Sum
            total = self.invoices.aggregate(total=Sum('total_amount'))['total']
            return total or Decimal('0.00')
        except Exception as e:
            logger.error(f"Error calculating total invoiced: {e}")
            return Decimal('0.00')
    
    def get_total_collected(self):
        """Get total amount collected in this period"""
        try:
            from django.db.models import Sum
            total = self.payments.aggregate(total=Sum('amount'))['total']
            return total or Decimal('0.00')
        except Exception as e:
            logger.error(f"Error calculating total collected: {e}")
            return Decimal('0.00')
    
    def get_collection_rate(self):
        """Get collection rate as percentage"""
        from core.utils import calculate_percentage
        
        invoiced = self.get_total_invoiced()
        if invoiced == 0:
            return Decimal('0.00')
        
        collected = self.get_total_collected()
        return calculate_percentage(collected, invoiced)
    
    def get_transaction_count(self):
        """Get total number of transactions in this period"""
        try:
            invoice_count = self.invoices.count()
            payment_count = self.payments.count()
            return invoice_count + payment_count
        except Exception as e:
            logger.error(f"Error counting transactions: {e}")
            return 0

# =============================================================================
# PAYMENT METHOD MODEL
# =============================================================================

class PaymentMethod(BaseModel):
    """Payment methods for fee transactions"""
    
    METHOD_TYPE_CHOICES = [
        ('CASH', 'Cash'),
        ('MOBILE_MONEY', 'Mobile Money'),
        ('BANK_TRANSFER', 'Bank Transfer'),
        ('CHEQUE', 'Cheque'),
        ('CARD', 'Card Payment'),
        ('DIRECT_DEBIT', 'Direct Debit'),
        ('STANDING_ORDER', 'Standing Order'),
        ('OTHER', 'Other'),
    ]
    
    MOBILE_MONEY_PROVIDER_CHOICES = [
        ('MTN', 'MTN Mobile Money'),
        ('AIRTEL', 'Airtel Money'),
        ('AFRICELL', 'Africell Money'),
        ('SAFARICOM', 'M-Pesa (Safaricom)'),
        ('VODACOM', 'M-Pesa (Vodacom)'),
        ('TIGO', 'Tigo Pesa'),
        ('ORANGE', 'Orange Money'),
        ('OTHER', 'Other Provider'),
    ]
    
    name = models.CharField("Payment Method Name", max_length=100)
    method_type = models.CharField("Method Type", max_length=20, choices=METHOD_TYPE_CHOICES, db_index=True)
    code = models.CharField("Method Code", max_length=20, unique=True)
    mobile_money_provider = models.CharField("Mobile Money Provider", max_length=20, choices=MOBILE_MONEY_PROVIDER_CHOICES, blank=True, null=True)
    bank_name = models.CharField("Bank Name", max_length=100, blank=True)
    bank_account_number = models.CharField("Bank Account Number", max_length=50, blank=True)
    bank_branch = models.CharField("Bank Branch", max_length=100, blank=True)
    swift_code = models.CharField("SWIFT/BIC Code", max_length=20, blank=True)
    is_active = models.BooleanField("Is Active", default=True, db_index=True)
    is_default = models.BooleanField("Is Default", default=False)
    requires_approval = models.BooleanField("Requires Approval", default=False)
    minimum_amount = models.DecimalField("Minimum Amount", max_digits=12, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal('0'))])
    maximum_amount = models.DecimalField("Maximum Amount", max_digits=12, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal('0'))])
    has_transaction_fee = models.BooleanField("Has Transaction Fee", default=False)
    transaction_fee_type = models.CharField("Fee Type", max_length=20, choices=[('FIXED', 'Fixed'), ('PERCENTAGE', 'Percentage'), ('TIERED', 'Tiered')], blank=True, null=True)
    transaction_fee_amount = models.DecimalField("Fee Amount", max_digits=10, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal('0'))])
    fee_bearer = models.CharField("Fee Bearer", max_length=20, choices=[('PARENT', 'Parent'), ('SCHOOL', 'School'), ('SHARED', 'Shared')], default='PARENT', blank=True)
    processing_time = models.CharField("Processing Time", max_length=100, blank=True)
    requires_reference = models.BooleanField("Requires Reference Number", default=False)
    icon = models.CharField("Icon CSS Class", max_length=50, blank=True)
    color_code = models.CharField("Color Code", max_length=7, blank=True)
    display_order = models.PositiveIntegerField("Display Order", default=0)
    instructions = models.TextField("Payment Instructions", blank=True)
    notes = models.TextField("Internal Notes", blank=True)
    
    class Meta:
        ordering = ['display_order', 'name']
        indexes = [
            models.Index(fields=['method_type', 'is_active']),
            models.Index(fields=['is_active', 'display_order']),
            models.Index(fields=['code']),
        ]
        verbose_name = "Payment Method"
        verbose_name_plural = "Payment Methods"
    
    def __str__(self):
        return f"{self.name} ({self.get_method_type_display()})"
    
    def clean(self):
        super().clean()
        errors = {}
        if self.method_type == 'MOBILE_MONEY' and not self.mobile_money_provider:
            errors['mobile_money_provider'] = "Mobile money provider required"
        
        # Make bank fields optional - they can be added later
        if self.method_type == 'BANK_TRANSFER':
            pass  # Bank fields are optional
        
        if self.minimum_amount and self.maximum_amount and self.minimum_amount >= self.maximum_amount:
            errors['maximum_amount'] = "Maximum must be greater than minimum"
        if self.has_transaction_fee:
            if not self.transaction_fee_type:
                errors['transaction_fee_type'] = "Fee type required when fees enabled"
            if not self.transaction_fee_amount:
                errors['transaction_fee_amount'] = "Fee amount required when fees enabled"
        if self.color_code:
            import re
            if not re.match(r'^#[0-9A-Fa-f]{6}$', self.color_code):
                errors['color_code'] = "Invalid hex color"
        if errors:
            raise ValidationError(errors)
    
    def save(self, *args, **kwargs):
        if self.code:
            self.code = self.code.upper().replace(' ', '_')
        if self.is_default:
            PaymentMethod.objects.exclude(pk=self.pk).update(is_default=False)
        self.full_clean()
        super().save(*args, **kwargs)
    
    @classmethod
    def get_active_methods(cls):
        return cls.objects.filter(is_active=True).order_by('display_order', 'name')
    
    @classmethod
    def get_default_method(cls):
        return cls.objects.filter(is_active=True, is_default=True).first()
    
    @classmethod
    def get_mobile_money_methods(cls):
        return cls.objects.filter(method_type='MOBILE_MONEY', is_active=True).order_by('display_order')
    
    @classmethod
    def get_cash_method(cls):
        return cls.objects.filter(method_type='CASH', is_active=True).first()
    
    @classmethod
    def get_by_code(cls, code):
        return cls.objects.filter(code=code.upper(), is_active=True).first()
    
    def calculate_transaction_fee(self, amount):
        if not self.has_transaction_fee:
            return Decimal('0.00')
        try:
            amount = Decimal(str(amount))
        except (ValueError, InvalidOperation):
            return Decimal('0.00')
        if self.transaction_fee_type == 'FIXED':
            return self.transaction_fee_amount or Decimal('0.00')
        elif self.transaction_fee_type == 'PERCENTAGE':
            rate = (self.transaction_fee_amount or Decimal('0.00')) / Decimal('100')
            return (amount * rate).quantize(Decimal('0.01'))
        return Decimal('0.00')
    
    def get_total_amount_with_fee(self, amount):
        fee = self.calculate_transaction_fee(amount)
        if self.fee_bearer == 'PARENT':
            return Decimal(str(amount)) + fee, fee
        return Decimal(str(amount)), fee
    
    def validate_transaction_amount(self, amount):
        try:
            amount = Decimal(str(amount))
        except (ValueError, InvalidOperation):
            return False, "Invalid amount"
        if self.minimum_amount and amount < self.minimum_amount:
            return False, f"Below minimum of {self.minimum_amount}"
        if self.maximum_amount and amount > self.maximum_amount:
            return False, f"Exceeds maximum of {self.maximum_amount}"
        return True, None


# =============================================================================
# TAX RATE MODEL
# =============================================================================

class TaxRate(BaseModel):
    """Tax rate configuration for school fees"""
    
    TAX_TYPE_CHOICES = [
        ('WHT_INTEREST', 'Withholding Tax on Interest'),
        ('WHT_DIVIDEND', 'Withholding Tax on Dividend'),
        ('VAT', 'Value Added Tax'),
        ('LOCAL_SERVICE', 'Local Service Tax'),
        ('EDUCATION_TAX', 'Education Tax'),
        ('OTHER', 'Other Tax'),
    ]
    
    name = models.CharField("Tax Name", max_length=100)
    tax_type = models.CharField("Tax Type", max_length=20, choices=TAX_TYPE_CHOICES, db_index=True)
    rate = models.DecimalField("Tax Rate (%)", max_digits=5, decimal_places=2, validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))])
    effective_from = models.DateField("Effective From", db_index=True)
    effective_to = models.DateField("Effective To", null=True, blank=True, db_index=True)
    is_active = models.BooleanField("Is Active", default=True, db_index=True)
    applies_to_fees = models.BooleanField("Applies to School Fees", default=True)
    applies_to_services = models.BooleanField("Applies to Services", default=False)
    description = models.TextField("Description", blank=True)
    legal_reference = models.CharField("Legal Reference", max_length=255, blank=True)
    
    class Meta:
        ordering = ['-effective_from', 'tax_type']
        indexes = [
            models.Index(fields=['tax_type', 'effective_from']),
            models.Index(fields=['is_active', 'effective_from']),
        ]
        verbose_name = "Tax Rate"
        verbose_name_plural = "Tax Rates"
    
    def __str__(self):
        return f"{self.name} - {self.rate}%"
    
    def clean(self):
        super().clean()
        errors = {}
        if not (0 <= self.rate <= 100):
            errors['rate'] = "Rate must be between 0 and 100"
        if self.effective_to and self.effective_from and self.effective_to <= self.effective_from:
            errors['effective_to'] = "Must be after effective from date"
        if errors:
            raise ValidationError(errors)
    
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
    
    @classmethod
    def get_active_rate(cls, tax_type, as_of_date=None):
        if as_of_date is None:
            as_of_date = timezone.now().date()
        return cls.objects.filter(
            tax_type=tax_type,
            is_active=True,
            effective_from__lte=as_of_date
        ).filter(
            models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=as_of_date)
        ).first()
    
    @classmethod
    def get_vat_rate(cls, as_of_date=None):
        rate_obj = cls.get_active_rate('VAT', as_of_date)
        return rate_obj.rate if rate_obj else Decimal('18.00')
    
    @classmethod
    def get_wht_interest_rate(cls, as_of_date=None):
        rate_obj = cls.get_active_rate('WHT_INTEREST', as_of_date)
        return rate_obj.rate if rate_obj else Decimal('15.00')
    
    def is_valid_on_date(self, check_date):
        if not self.is_active:
            return False
        if check_date < self.effective_from:
            return False
        if self.effective_to and check_date > self.effective_to:
            return False
        return True
    
    def get_rate_decimal(self):
        return self.rate / Decimal('100')
    
    def calculate_tax(self, amount):
        try:
            amount = Decimal(str(amount))
            return (amount * self.get_rate_decimal()).quantize(Decimal('0.01'))
        except (ValueError, InvalidOperation):
            return Decimal('0.00')
        
    def is_effective(self, check_date=None):
        """
        Check if this tax rate is currently effective.
        Alias for is_valid_on_date() for better readability.
        
        Args:
            check_date: Date to check (defaults to today)
            
        Returns:
            bool: True if effective on the given date, False otherwise
        """
        if check_date is None:
            check_date = timezone.now().date()
        
        return self.is_valid_on_date(check_date)
    
    def get_status_display_class(self):
        """
        Get CSS class for status display based on effectiveness.
        
        Returns:
            str: CSS class name
        """
        if not self.is_active:
            return 'status-inactive'
        elif self.is_effective():
            return 'status-effective'
        else:
            return 'status-scheduled'
        
# =============================================================================
# UNITS OF MEASURE
# =============================================================================

class UnitOfMeasure(BaseModel):
    """Enhanced model for different units of measurement used by the school"""
    
    UOM_TYPE_CHOICES = [
        ('LENGTH', 'Length'),
        ('WEIGHT', 'Weight'),
        ('VOLUME', 'Volume'),
        ('AREA', 'Area'), 
        ('QUANTITY', 'Quantity'),
        ('TIME', 'Time'),
        ('OTHER', 'Other')
    ]
    
    # Basic information
    name = models.CharField("Name", max_length=50)  # e.g., "Meter", "Kilogram"
    abbreviation = models.CharField("Abbreviation", max_length=10)  # e.g., "m", "kg"
    symbol = models.CharField("Symbol", max_length=10, blank=True, null=True)
    description = models.TextField("Description", blank=True, null=True)
    
    # Categorization
    uom_type = models.CharField("UOM Type", max_length=20, choices=UOM_TYPE_CHOICES)
    
    # Conversion information
    base_unit = models.ForeignKey(
        'self', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='derived_units',
        verbose_name="Base Unit",
        help_text="The base unit this unit is derived from"
    )
    conversion_factor = models.DecimalField(
        "Conversion Factor",
        max_digits=16, 
        decimal_places=6, 
        default=1.0,
        validators=[MinValueValidator(Decimal('0.000001'))],
        help_text="Multiply by this factor to convert to the base unit"
    )
    
    # Status
    is_active = models.BooleanField("Is Active", default=True)
    
    def clean(self):
        """Enhanced validation"""
        super().clean()
        errors = {}
        
        # Cannot be its own base unit
        if self.base_unit == self:
            errors['base_unit'] = 'Unit cannot be its own base unit'
        
        # Conversion factor must be positive
        if self.conversion_factor <= 0:
            errors['conversion_factor'] = 'Conversion factor must be positive'
        
        if errors:
            raise ValidationError(errors)
    
    # =============================================================================
    # CONVERSION AND CALCULATION METHODS
    # =============================================================================
    
    def get_conversion_example(self, value=10):
        """Get conversion example for a given value"""
        if not self.base_unit or not self.conversion_factor:
            return None
        
        converted_value = float(self.conversion_factor) * value
        return {
            'original_value': value,
            'original_unit': self.abbreviation,
            'converted_value': converted_value,
            'converted_unit': self.base_unit.abbreviation,
            'formatted': f"{value} {self.abbreviation} = {converted_value:,.6f} {self.base_unit.abbreviation}".rstrip('0').rstrip('.')
        }
    
    def get_conversion_examples(self):
        """Get multiple conversion examples for common values"""
        if not self.base_unit:
            return []
        
        examples = []
        test_values = [0.5, 1, 5, 10, 100]
        
        for value in test_values:
            example = self.get_conversion_example(value)
            if example:
                examples.append(example)
        
        return examples
    
    def convert_to_base(self, value):
        """Convert a value from this unit to the base unit"""
        if not self.base_unit:
            return value  # Already a base unit
        
        return float(value) * float(self.conversion_factor)
    
    def convert_from_base(self, value):
        """Convert a value from the base unit to this unit"""
        if not self.base_unit:
            return value  # Already a base unit
        
        return float(value) / float(self.conversion_factor)
    
    def convert_to_unit(self, value, target_unit):
        """Convert a value from this unit to another unit of the same type"""
        if not isinstance(target_unit, UnitOfMeasure):
            return None
        
        if self.uom_type != target_unit.uom_type:
            return None  # Cannot convert between different types
        
        # Convert to base unit first
        base_value = self.convert_to_base(value)
        
        # Then convert from base to target unit
        return target_unit.convert_from_base(base_value)
    
    # =============================================================================
    # DISPLAY AND FORMATTING METHODS
    # =============================================================================
    
    def get_quick_conversion_text(self, value=10):
        """Get a quick conversion text for display in templates"""
        if not self.base_unit:
            return f"Base unit for {self.get_uom_type_display().lower()}"
        
        converted = float(self.conversion_factor) * value
        formatted_converted = f"{converted:,.6f}".rstrip('0').rstrip('.')
        
        return f"{value} {self.abbreviation} = {formatted_converted} {self.base_unit.abbreviation}"
    
    def format_conversion_factor(self, decimal_places=6):
        """Format the conversion factor with proper decimal places"""
        if not self.conversion_factor:
            return "1.0"
        
        formatted = f"{float(self.conversion_factor):.{decimal_places}f}"
        return formatted.rstrip('0').rstrip('.')
    
    def get_display_name(self):
        """Get display name with abbreviation"""
        if self.symbol:
            return f"{self.name} ({self.abbreviation}, {self.symbol})"
        return f"{self.name} ({self.abbreviation})"
    
    def get_short_display(self):
        """Get short display name"""
        return f"{self.abbreviation}" + (f" ({self.symbol})" if self.symbol else "")
    
    # =============================================================================
    # RELATIONSHIP AND HIERARCHY METHODS
    # =============================================================================
    
    def get_derived_units_count(self):
        """Get count of units that use this as a base unit"""
        return self.derived_units.filter(is_active=True).count()
    
    def get_all_derived_units(self):
        """Get all units that use this as a base unit"""
        return self.derived_units.filter(is_active=True).order_by('name')
    
    def is_base_unit(self):
        """Check if this is a base unit (has no base_unit)"""
        return self.base_unit is None
    
    def is_derived_unit(self):
        """Check if this is a derived unit (has a base_unit)"""
        return self.base_unit is not None
    
    def get_unit_hierarchy(self):
        """Get the full hierarchy path for this unit"""
        if self.is_base_unit():
            return [self]
        
        hierarchy = []
        current_unit = self
        seen_units = set()  # Prevent infinite loops
        
        while current_unit and current_unit.id not in seen_units:
            hierarchy.append(current_unit)
            seen_units.add(current_unit.id)
            current_unit = current_unit.base_unit
            
            # Additional safety check
            if len(hierarchy) > 10:
                break
        
        return hierarchy
    
    def get_root_base_unit(self):
        """Get the root base unit in the hierarchy"""
        hierarchy = self.get_unit_hierarchy()
        return hierarchy[-1] if hierarchy else self
    
    def get_conversion_chain_display(self):
        """Get display text for the conversion chain"""
        hierarchy = self.get_unit_hierarchy()
        
        if len(hierarchy) == 1:
            return f"Base unit for {self.get_uom_type_display()}"
        
        chain_parts = []
        for i, unit in enumerate(hierarchy[:-1]):
            next_unit = hierarchy[i + 1]
            chain_parts.append(f"{unit.abbreviation} → {next_unit.abbreviation}")
        
        return " → ".join(chain_parts)
    
    # =============================================================================
    # STATUS AND VALIDATION METHODS
    # =============================================================================
    
    def get_status_display_class(self):
        """Get CSS class for status display"""
        return "status-active" if self.is_active else "status-inactive"
    
    def get_type_icon_class(self):
        """Get CSS class for unit type icon"""
        icon_map = {
            'LENGTH': 'fa-ruler',
            'WEIGHT': 'fa-weight',
            'VOLUME': 'fa-flask',
            'AREA': 'fa-square',
            'QUANTITY': 'fa-hashtag',
            'TIME': 'fa-clock',
            'OTHER': 'fa-cube',
        }
        return icon_map.get(self.uom_type, 'fa-cube')
    
    def get_type_badge_class(self):
        """Get CSS class for unit type badge"""
        badge_map = {
            'LENGTH': 'badge-primary',
            'WEIGHT': 'badge-success',
            'VOLUME': 'badge-info',
            'AREA': 'badge-warning',
            'QUANTITY': 'badge-secondary',
            'TIME': 'badge-dark',
            'OTHER': 'badge-light',
        }
        return badge_map.get(self.uom_type, 'badge-light')
    
    def can_be_deleted(self):
        """Check if this unit can be safely deleted"""
        # Cannot delete if it has derived units
        return self.derived_units.count() == 0
    
    def get_deletion_warnings(self):
        """Get warnings about deleting this unit"""
        warnings = []
        
        derived_count = self.derived_units.count()
        if derived_count > 0:
            warnings.append(f"Has {derived_count} derived unit{'s' if derived_count != 1 else ''}")
        
        # Check for usage in inventory (if inventory app is installed)
        try:
            from inventory.models import Item
            items_using = Item.objects.filter(unit_of_measure=self).count()
            if items_using > 0:
                warnings.append(f"Used by {items_using} inventory item{'s' if items_using != 1 else ''}")
        except ImportError:
            pass
        
        # Check for usage in uniforms (if uniforms app is installed)
        try:
            from uniforms.models import UniformItem
            uniforms_using = UniformItem.objects.filter(unit_of_measure=self).count()
            if uniforms_using > 0:
                warnings.append(f"Used by {uniforms_using} uniform item{'s' if uniforms_using != 1 else ''}")
        except ImportError:
            pass
        
        if not self.is_active:
            warnings.append("Unit is already inactive")
        
        return warnings
    
    def can_be_base_unit_for(self, other_unit):
        """Check if this unit can be a base unit for another unit"""
        if not isinstance(other_unit, UnitOfMeasure):
            return False
        
        # Must be same type
        if self.uom_type != other_unit.uom_type:
            return False
        
        # Cannot be base for itself
        if self == other_unit:
            return False
        
        # Check for circular references
        if other_unit in self.get_unit_hierarchy():
            return False
        
        return True
    
    # =============================================================================
    # UTILITY AND HELPER METHODS
    # =============================================================================
    
    def get_similar_units(self):
        """Get other units of the same type"""
        return UnitOfMeasure.objects.filter(
            uom_type=self.uom_type,
            is_active=True
        ).exclude(pk=self.pk).order_by('name')
    
    def get_conversion_table(self):
        """Get conversion table for all units of the same type"""
        similar_units = self.get_similar_units()
        table = []
        
        for unit in similar_units:
            if unit != self:
                # Try to convert 1 of this unit to the other unit
                try:
                    converted_value = self.convert_to_unit(1, unit)
                    if converted_value is not None:
                        table.append({
                            'unit': unit,
                            'conversion': f"1 {self.abbreviation} = {converted_value:,.6f} {unit.abbreviation}".rstrip('0').rstrip('.')
                        })
                except:
                    pass
        
        return table
    
    def validate_conversion_factor(self):
        """Validate that the conversion factor makes sense"""
        errors = []
        
        if self.conversion_factor <= 0:
            errors.append("Conversion factor must be positive")
        
        if self.conversion_factor == 1 and self.base_unit:
            errors.append("Conversion factor of 1 suggests this should be a base unit")
        
        return errors

    def get_short_factor(self):
        """Get conversion factor with 3 decimal places"""
        return self.format_conversion_factor(3)
    
    def get_usage_stats(self):
        """Get usage statistics for this unit"""
        stats = {
            'derived_units': self.get_derived_units_count(),
            'is_base': self.is_base_unit(),
            'hierarchy_depth': len(self.get_unit_hierarchy()),
            'can_delete': self.can_be_deleted(),
        }
        
        # Add inventory usage if available
        try:
            from inventory.models import Item
            stats['inventory_items'] = Item.objects.filter(unit_of_measure=self).count()
        except ImportError:
            stats['inventory_items'] = 0
        
        # Add uniform usage if available
        try:
            from uniforms.models import UniformItem
            stats['uniform_items'] = UniformItem.objects.filter(unit_of_measure=self).count()
        except ImportError:
            stats['uniform_items'] = 0
        
        return stats
    
    # =============================================================================
    # CLASS METHODS
    # =============================================================================
    
    @classmethod
    def get_active_by_type(cls, uom_type):
        """Get all active units of a specific type"""
        return cls.objects.filter(
            uom_type=uom_type,
            is_active=True
        ).order_by('name')
    
    @classmethod
    def get_base_units(cls):
        """Get all base units (units with no parent)"""
        return cls.objects.filter(
            base_unit__isnull=True,
            is_active=True
        ).order_by('uom_type', 'name')
    
    @classmethod
    def get_derived_units(cls):
        """Get all derived units (units with a parent)"""
        return cls.objects.filter(
            base_unit__isnull=False,
            is_active=True
        ).order_by('uom_type', 'name')
    
    @classmethod
    def get_by_abbreviation(cls, abbreviation):
        """Get unit by abbreviation"""
        return cls.objects.filter(
            abbreviation__iexact=abbreviation,
            is_active=True
        ).first()
    
    @classmethod
    def create_standard_units(cls):
        """
        Create standard units for common measurements.
        Useful for initial setup or testing.
        """
        standard_units = []
        
        # Length units
        meter = cls.objects.get_or_create(
            name='Meter',
            defaults={
                'abbreviation': 'm',
                'uom_type': 'LENGTH',
                'description': 'Standard unit of length',
                'is_active': True
            }
        )[0]
        standard_units.append(meter)
        
        cls.objects.get_or_create(
            name='Centimeter',
            defaults={
                'abbreviation': 'cm',
                'uom_type': 'LENGTH',
                'base_unit': meter,
                'conversion_factor': Decimal('0.01'),
                'description': 'One hundredth of a meter',
                'is_active': True
            }
        )
        
        cls.objects.get_or_create(
            name='Kilometer',
            defaults={
                'abbreviation': 'km',
                'uom_type': 'LENGTH',
                'base_unit': meter,
                'conversion_factor': Decimal('1000'),
                'description': 'One thousand meters',
                'is_active': True
            }
        )
        
        # Weight units
        kilogram = cls.objects.get_or_create(
            name='Kilogram',
            defaults={
                'abbreviation': 'kg',
                'uom_type': 'WEIGHT',
                'description': 'Standard unit of weight',
                'is_active': True
            }
        )[0]
        standard_units.append(kilogram)
        
        cls.objects.get_or_create(
            name='Gram',
            defaults={
                'abbreviation': 'g',
                'uom_type': 'WEIGHT',
                'base_unit': kilogram,
                'conversion_factor': Decimal('0.001'),
                'description': 'One thousandth of a kilogram',
                'is_active': True
            }
        )
        
        # Volume units
        liter = cls.objects.get_or_create(
            name='Liter',
            defaults={
                'abbreviation': 'L',
                'uom_type': 'VOLUME',
                'description': 'Standard unit of volume',
                'is_active': True
            }
        )[0]
        standard_units.append(liter)
        
        cls.objects.get_or_create(
            name='Milliliter',
            defaults={
                'abbreviation': 'mL',
                'uom_type': 'VOLUME',
                'base_unit': liter,
                'conversion_factor': Decimal('0.001'),
                'description': 'One thousandth of a liter',
                'is_active': True
            }
        )
        
        # Quantity units
        cls.objects.get_or_create(
            name='Piece',
            defaults={
                'abbreviation': 'pcs',
                'uom_type': 'QUANTITY',
                'description': 'Individual items',
                'is_active': True
            }
        )
        
        cls.objects.get_or_create(
            name='Dozen',
            defaults={
                'abbreviation': 'doz',
                'uom_type': 'QUANTITY',
                'description': 'Twelve items',
                'is_active': True
            }
        )
        
        cls.objects.get_or_create(
            name='Box',
            defaults={
                'abbreviation': 'box',
                'uom_type': 'QUANTITY',
                'description': 'Container of items',
                'is_active': True
            }
        )
        
        logger.info(f"Created/verified {len(standard_units)} standard units of measure")
        return standard_units
    
    # =============================================================================
    # STRING REPRESENTATION AND META
    # =============================================================================
    
    def __str__(self):
        return f"{self.name} ({self.abbreviation})"
    
    class Meta:
        ordering = ['uom_type', 'name']
        verbose_name = "Unit of Measure"
        verbose_name_plural = "Units of Measure"
        indexes = [
            models.Index(fields=['uom_type', 'is_active']),
            models.Index(fields=['base_unit', 'uom_type']),
            models.Index(fields=['is_active', 'uom_type']),
            models.Index(fields=['abbreviation']),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(conversion_factor__gt=0),
                name='positive_conversion_factor'
            ),
        ]