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
import uuid

logger = logging.getLogger(__name__)


# =============================================================================
# SINGLETON UUID CONSTANTS
# =============================================================================
# Django's UUIDField stores as 32-char hex in MySQL (no dashes).
# Using fixed deterministic UUIDs so the pk is always predictable.

_FINANCIAL_SETTINGS_UUID   = uuid.UUID('00000000-0000-0000-0000-000000000001')
_SCHOOL_CONFIGURATION_UUID = uuid.UUID('00000000-0000-0000-0000-000000000002')


# =============================================================================
# SCHOOL CONFIGURATION
# =============================================================================

class SchoolConfiguration(BaseModel):
    """
    School academic and operational configuration.
    Singleton — one record per school database.
    pk is always _SCHOOL_CONFIGURATION_UUID (stored as 32-char hex in MySQL).

    Controls:
    - Academic period system (terms, semesters, quarters, etc.)
    - Period naming conventions
    - Academic year start date
    - Operational timezone for financial layer date/time logic
    - Regional season naming
    - Communication preferences

    TIMEZONE SCOPE:
    operational_timezone currently affects the finance layer only
    (fee due dates, fiscal periods, report generation, journal timestamps).
    AcademicSession date checks use server time until academics/models.py
    is updated to call get_school_today() from core.utils.
    """

    # -------------------------------------------------------------------------
    # CLASS-LEVEL CACHE (singleton pattern)
    # -------------------------------------------------------------------------

    _instance_cache: dict = {}

    # -------------------------------------------------------------------------
    # TERM SYSTEM
    # -------------------------------------------------------------------------

    TERM_SYSTEM_CHOICES = [
        ('term',      'Terms (3 per year) — British/Commonwealth'),
        ('semester',  'Semesters (2 per year) — North American'),
        ('quarter',   'Quarters (4 per year)'),
        ('trimester', 'Trimesters (3 per year) — same as Terms'),
        ('module',    'Modules (6-8 per year)'),
        ('block',     'Block Schedule (4-6 per year)'),
        ('yearlong',  'Year-long Program (1 per year)'),
        ('intensive', 'Intensive Programs (8-12 per year)'),
        ('custom',    'Custom System'),
    ]

    term_system = models.CharField(
        "Academic Period System",
        max_length=15,
        choices=TERM_SYSTEM_CHOICES,
        default='term',
    )

    periods_per_year = models.PositiveIntegerField(
        "Periods Per Year",
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(20)],
    )

    # -------------------------------------------------------------------------
    # PERIOD NAMING
    # -------------------------------------------------------------------------

    PERIOD_NAMING_CHOICES = [
        ('numeric',  'Numeric (Term 1, Term 2…)'),
        ('ordinal',  'Ordinal (First Term, Second Term…)'),
        ('seasonal', 'Seasonal (Fall, Spring, Summer)'),
        ('monthly',  'Monthly (January, February…)'),
        ('alpha',    'Alphabetical (Term A, Term B…)'),
        ('roman',    'Roman Numerals (Term I, Term II…)'),
        ('custom',   'Custom Names'),
    ]

    period_naming_convention = models.CharField(
        "Period Naming Convention",
        max_length=20,
        choices=PERIOD_NAMING_CHOICES,
        default='numeric',
    )

    custom_period_names = models.JSONField(
        "Custom Period Names",
        default=dict,
        blank=True,
        help_text='E.g. {"1": "Fall Semester", "2": "Spring Semester"}',
    )

    # -------------------------------------------------------------------------
    # ACADEMIC YEAR
    # -------------------------------------------------------------------------

    ACADEMIC_YEAR_TYPE_CHOICES = [
        ('calendar',    'Calendar Year (Jan–Dec)'),
        ('northern',    'Northern Hemisphere (Sep–Jun)'),
        ('southern',    'Southern Hemisphere (Feb–Nov)'),
        ('east_africa', 'East African Calendar (Jan–Nov)'),
        ('west_africa', 'West African Calendar (Sep–Jul)'),
        ('sahel',       'Sahel Region (Oct–Jun)'),
        ('financial',   'Financial Year (Apr–Mar)'),
        ('custom',      'Custom Year Dates'),
    ]

    MONTH_CHOICES = [(i, date(2000, i, 1).strftime('%B')) for i in range(1, 13)]

    academic_year_type = models.CharField(
        "Academic Year Type",
        max_length=15,
        choices=ACADEMIC_YEAR_TYPE_CHOICES,
        default='east_africa',
    )

    academic_year_start_month = models.PositiveIntegerField(
        "Academic Year Start Month",
        choices=MONTH_CHOICES,
        default=2,
        validators=[MinValueValidator(1), MaxValueValidator(12)],
    )

    academic_year_start_day = models.PositiveIntegerField(
        "Academic Year Start Day",
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
    )

    # -------------------------------------------------------------------------
    # TIMEZONE
    # -------------------------------------------------------------------------

    operational_timezone = models.CharField(
        "Operational Timezone",
        max_length=63,
        default='Africa/Kampala',
        help_text=(
            "School timezone for fee due dates, fiscal periods, report generation, "
            "journal entry timestamps, and all date-based business logic in the "
            "finance layer. "
            "NOTE: AcademicSession date checks currently use server time — "
            "update academics/models.py to use get_school_today() from core.utils "
            "to extend timezone awareness to the academic layer."
        ),
    )

    # -------------------------------------------------------------------------
    # REGIONAL SEASONS
    # -------------------------------------------------------------------------

    REGIONAL_SEASON_CHOICES = [
        ('temperate',        'Temperate (Spring/Summer/Fall/Winter)'),
        ('tropical_wet_dry', 'Tropical (Wet/Dry Seasons)'),
        ('desert',           'Desert (Hot/Cool Seasons)'),
        ('equatorial',       'Equatorial (Year-round)'),
        ('monsoon',          'Monsoon (Pre/Monsoon/Post)'),
        ('custom_regional',  'Custom Regional Seasons'),
    ]

    regional_season_type = models.CharField(
        "Regional Season Type",
        max_length=20,
        choices=REGIONAL_SEASON_CHOICES,
        default='equatorial',
    )

    custom_season_names = models.JSONField(
        "Custom Season Names",
        default=dict,
        blank=True,
        help_text='E.g. {"1": "Harmattan", "2": "Rainy Season"}',
    )

    # -------------------------------------------------------------------------
    # PERIOD SETTINGS
    # -------------------------------------------------------------------------

    default_period_duration_weeks = models.PositiveIntegerField(
        "Default Period Duration (weeks)",
        default=13,
        validators=[MinValueValidator(1), MaxValueValidator(52)],
    )

    # -------------------------------------------------------------------------
    # COMMUNICATION
    # -------------------------------------------------------------------------

    enable_automatic_reminders = models.BooleanField(
        "Enable Automatic Reminders", default=True,
    )
    enable_sms = models.BooleanField(
        "Enable SMS Notifications", default=False,
    )
    enable_email_notifications = models.BooleanField(
        "Enable Email Notifications", default=True,
    )

    # =========================================================================
    # VALIDATION
    # =========================================================================

    def clean(self):
        super().clean()
        errors = {}

        if self.term_system != 'custom':
            expected = self._get_system_period_count(self.term_system)
            if self.periods_per_year != expected:
                self.periods_per_year = expected

        if self.period_naming_convention == 'custom':
            if not self.custom_period_names:
                errors['custom_period_names'] = (
                    'Custom period names are required when using custom naming.'
                )
            else:
                missing = [
                    str(i) for i in range(1, self.periods_per_year + 1)
                    if str(i) not in self.custom_period_names
                ]
                if missing:
                    errors['custom_period_names'] = (
                        f"Missing names for periods: {', '.join(missing)}"
                    )

        if self.operational_timezone:
            try:
                ZoneInfo(self.operational_timezone)
            except Exception:
                errors['operational_timezone'] = (
                    f"Invalid timezone: '{self.operational_timezone}'"
                )

        if errors:
            raise ValidationError(errors)

    # =========================================================================
    # PERIOD SYSTEM HELPERS
    # =========================================================================

    def _get_system_period_count(self, system):
        return {
            'term': 3, 'trimester': 3, 'semester': 2,
            'quarter': 4, 'module': 6, 'block': 4,
            'yearlong': 1, 'intensive': 10,
        }.get(system, self.periods_per_year)

    def get_period_count(self):
        if self.term_system == 'custom':
            return self.periods_per_year
        return self._get_system_period_count(self.term_system)

    def get_period_type_name(self):
        return {
            'term': 'Term', 'trimester': 'Trimester', 'semester': 'Semester',
            'quarter': 'Quarter', 'module': 'Module', 'block': 'Block',
            'yearlong': 'Year', 'intensive': 'Session', 'custom': 'Period',
        }.get(self.term_system, 'Term')

    def get_period_type_name_plural(self):
        singular = self.get_period_type_name()
        if singular in ('Module', 'Year'):
            return singular + 's'
        if singular.endswith('y'):
            return singular[:-1] + 'ies'
        return singular + 's'

    def get_period_name(self, position, include_year=False, academic_year=None):
        """Return the display name for period at `position` (1-based)."""
        if not (1 <= position <= self.get_period_count()):
            return None

        if self.period_naming_convention == 'custom' and self.custom_period_names:
            base = self.custom_period_names.get(str(position))
            if base:
                return f"{base} {academic_year}" if include_year and academic_year else base

        convention  = self.period_naming_convention
        period_type = self.get_period_type_name()

        if convention == 'ordinal':
            ordinals = [
                '', 'First', 'Second', 'Third', 'Fourth', 'Fifth',
                'Sixth', 'Seventh', 'Eighth', 'Ninth', 'Tenth',
            ]
            base = (
                f"{ordinals[position]} {period_type}"
                if position < len(ordinals)
                else f"{position}th {period_type}"
            )
        elif convention == 'alpha':
            import string
            base = f"{period_type} {string.ascii_uppercase[position - 1]}"
        elif convention == 'roman':
            base = f"{period_type} {self._to_roman(position)}"
        else:  # numeric (default)
            base = f"{period_type} {position}"

        return f"{base} {academic_year}" if include_year and academic_year else base

    def get_all_period_names(self, include_year=False, academic_year=None):
        return [
            self.get_period_name(i, include_year, academic_year)
            for i in range(1, self.get_period_count() + 1)
        ]

    @staticmethod
    def _to_roman(num):
        vals = [1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1]
        syms = ['M', 'CM', 'D', 'CD', 'C', 'XC', 'L', 'XL', 'X', 'IX', 'V', 'IV', 'I']
        result = ''
        for v, s in zip(vals, syms):
            while num >= v:
                result += s
                num -= v
        return result

    # =========================================================================
    # PERIOD NUMBER VALIDATION — used by AcademicSession.clean()
    # =========================================================================

    def validate_period_number(self, period_number: int) -> bool:
        """
        Return True if period_number is within the valid range for this school.

        Used by AcademicSession.clean() to validate term_number for regular
        (non-special) sessions against the configured term system.

        Args:
            period_number: 1-based integer position within the academic year.

        Returns:
            bool: True if 1 <= period_number <= get_period_count().
        """
        return 1 <= period_number <= self.get_period_count()

    def get_term_system_display_name(self) -> str:
        """
        Human-readable name for the currently configured term system.

        Used by AcademicSession.clean() error messages.
        Delegates to Django's auto-generated get_term_system_display().

        Returns:
            str: e.g. "Terms (3 per year) — British/Commonwealth"
        """
        return self.get_term_system_display()

    # =========================================================================
    # TIMEZONE HELPERS
    # =========================================================================

    def get_timezone(self):
        """Return ZoneInfo for the operational timezone."""
        try:
            return ZoneInfo(self.operational_timezone)
        except Exception:
            logger.warning(
                f"Invalid timezone '{self.operational_timezone}', "
                f"falling back to Africa/Kampala"
            )
            return ZoneInfo('Africa/Kampala')

    def get_current_time(self):
        return timezone.now().astimezone(self.get_timezone())

    def get_today(self):
        return self.get_current_time().date()

    def localize_datetime(self, dt):
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt)
        return dt.astimezone(self.get_timezone())

    @classmethod
    def get_operational_timezone(cls):
        config = cls.get_cached_instance()
        return config.get_timezone() if config else ZoneInfo('Africa/Kampala')

    # =========================================================================
    # SINGLETON PATTERN WITH REAL CACHE
    # =========================================================================

    @classmethod
    def get_instance(cls, using=None):
        """
        Get or create the singleton SchoolConfiguration.

        Uses `using` when explicitly provided (e.g. from get_cached_instance).
        Otherwise falls back to get_current_db() from managers.py — the
        thread-local set by SchoolDatabaseMiddleware for the current request.
        Final fallback is the first configured school database so that
        management commands and shell sessions don't accidentally hit 'default'
        (core is a school app and its tables never exist in default).

        Automatically creates the record with safe defaults the first time
        any school database is accessed — no manual seeding required.

        Args:
            using: Optional explicit database alias.

        Returns:
            SchoolConfiguration instance, or None on error.
        """

        from schoolara.managers import get_current_db

        db = using or get_current_db()

        # core is a school app — its tables never exist in 'default'.
        # In the shell or management commands get_current_db() returns None
        # because SchoolDatabaseMiddleware hasn't run.  Fall back to the first
        # school database rather than 'default' to avoid the missing-table error.
        if not db or db == 'default':
            from django.conf import settings
            school_dbs = [k for k in settings.DATABASES if k != 'default']
            db = school_dbs[0] if school_dbs else 'default'

        try:
            instance, created = (
                cls.objects
                .using(db)
                .get_or_create(
                    pk=_SCHOOL_CONFIGURATION_UUID,
                    defaults={
                        'term_system':                   'term',
                        'periods_per_year':              3,
                        'period_naming_convention':      'numeric',
                        'custom_period_names':           {},
                        'academic_year_type':            'east_africa',
                        'academic_year_start_month':     2,
                        'academic_year_start_day':       1,
                        'operational_timezone':          'Africa/Kampala',
                        'regional_season_type':          'equatorial',
                        'custom_season_names':           {},
                        'default_period_duration_weeks': 13,
                        'enable_automatic_reminders':    True,
                        'enable_sms':                    False,
                        'enable_email_notifications':    True,
                    },
                )
            )

            if created:
                logger.info(
                    f"SchoolConfiguration created with defaults in database "
                    f"'{db}'. Visit /core/configuration/ to customise."
                )

            return instance

        except Exception as e:
            logger.error(
                f"Error accessing SchoolConfiguration in database '{db}': {e}",
                exc_info=True,
            )
            return None

    @classmethod
    def get_cached_instance(cls, using=None):
        """
        Return the singleton SchoolConfiguration using a per-database
        class-level cache to avoid hitting the DB on every request.

        The cache is a dict keyed by database alias so:
        - Each school database has its own cached instance.
        - Flushing one school's cache does not affect others.
        - The SchoolTimezoneMiddleware can call
        get_cached_instance(using='atepi_palabek') and get the correct
        record even if another school's instance is cached simultaneously.

        Cache is invalidated automatically by save() for the specific
        database that was written to.

        Args:
            using: Optional explicit database alias.
                When None, resolves via get_current_db() → 'default'.

        Returns:
            SchoolConfiguration instance, or None on error.
        """

        from schoolara.managers import get_current_db

        db = using or get_current_db() or 'default'

        if cls._instance_cache.get(db) is None:
            cls._instance_cache[db] = cls.get_instance(using=db)

        return cls._instance_cache[db]

    @classmethod
    def clear_cache(cls, using=None):
        """
        Invalidate the per-database singleton cache.

        Args:
            using: Database alias to clear.
                Pass None to clear ALL databases (e.g. in tests).
                Pass the specific alias to clear only one school's cache
                (this is what save() does automatically).

        Examples:
            # Clear only the school that was just written to:
            SchoolConfiguration.clear_cache(using='atepi_palabek')

            # Clear everything (tests, management commands):
            SchoolConfiguration.clear_cache()
        """
        if using:
            cls._instance_cache.pop(using, None)
            logger.debug(
                f"SchoolConfiguration cache cleared for database '{using}'"
            )
        else:
            cls._instance_cache.clear()
            logger.debug("SchoolConfiguration cache cleared for all databases")

    def save(self, *args, **kwargs):
        """
        Lock pk to the fixed singleton UUID, persist, then invalidate only
        the cache entry for the database this instance was saved to.

        Flushing by specific alias means a save to 'atepi_palabek' does
        not invalidate cached instances for other school databases running
        concurrently in the same process.
        """
        self.pk = _SCHOOL_CONFIGURATION_UUID

        # Determine target database: explicit kwarg → state from last load → default
        db = kwargs.get('using') or self._state.db or 'default'

        super().save(*args, **kwargs)

        SchoolConfiguration.clear_cache(using=db)

    def delete(self, *args, **kwargs):
        """Prevent deletion of the singleton."""
        pass

    def __str__(self):
        return f"School Configuration — {self.get_period_type_name_plural()}"

    class Meta:
        verbose_name        = "School Configuration"
        verbose_name_plural = "School Configuration"


# =============================================================================
# FINANCIAL SETTINGS
# =============================================================================

class FinancialSettings(BaseModel):
    """
    School financial system configuration.
    Singleton — one record per school database.
    pk is always _FINANCIAL_SETTINGS_UUID (stored as 32-char hex in MySQL).
 
    CACHING
    -------
    get_cached_instance() caches per database alias, matching the
    SchoolConfiguration pattern. A save() to 'atepi_palabek' invalidates only
    that school's cache entry, leaving other schools' caches intact.
 
    Always call get_cached_instance() from application code.
    Call get_instance() only when you need a guaranteed fresh DB read
    (e.g., after an explicit settings update in an admin action).
 
    GL ROUTING
    ----------
    get_account_for_fee_category(fee_category) is the single entry point for
    resolving a FeesCategory instance to a GL account. It handles all types
    including DEPOSIT (liability) and penalty types. Use it from invoice
    generators and payment processing code instead of calling
    get_revenue_account() directly.
    """
 
    # -------------------------------------------------------------------------
    # CLASS-LEVEL CACHE (singleton pattern — mirrors SchoolConfiguration)
    # -------------------------------------------------------------------------
 
    _instance_cache: dict = {}
 
    # -------------------------------------------------------------------------
    # CURRENCY
    # -------------------------------------------------------------------------
 
    CURRENCY_POSITION_CHOICES = [
        ('BEFORE',          'Before amount  — UGX 100.00'),
        ('AFTER',           'After amount   — 100.00 UGX'),
        ('BEFORE_NO_SPACE', 'Before no space — UGX100.00'),
        ('AFTER_NO_SPACE',  'After no space  — 100.00UGX'),
    ]
 
    school_currency = models.CharField(
        "School Currency", max_length=3, default='UGX',
        help_text='ISO 4217 currency code',
    )
    currency_position = models.CharField(
        "Currency Position", max_length=20,
        choices=CURRENCY_POSITION_CHOICES, default='BEFORE',
    )
    decimal_places = models.PositiveIntegerField(
        "Decimal Places", default=2,
        validators=[MinValueValidator(0), MaxValueValidator(4)],
    )
    use_thousand_separator = models.BooleanField(
        "Use Thousand Separator", default=True,
    )
 
    # -------------------------------------------------------------------------
    # EXCHANGE RATES
    # -------------------------------------------------------------------------
 
    auto_update_exchange_rates = models.BooleanField(
        "Auto-Update Exchange Rates", default=False,
        help_text="When disabled, cashiers enter rates manually.",
    )
    exchange_rate_update_frequency = models.PositiveIntegerField(
        "Exchange Rate Update Frequency (Hours)", default=6,
        validators=[MinValueValidator(1), MaxValueValidator(168)],
    )
    tracked_currencies = models.JSONField(
        "Tracked Currencies", default=list, blank=True,
        help_text='ISO 4217 codes. E.g. ["USD", "EUR"]. School currency auto-excluded.',
    )
 
    # -------------------------------------------------------------------------
    # NUMBERING PREFIXES
    # -------------------------------------------------------------------------
 
    invoice_prefix                 = models.CharField("Invoice Prefix",  max_length=10, default='INV',  blank=True)
    include_year_in_invoice_number = models.BooleanField("Year in Invoice Number",  default=True)
    payment_prefix                 = models.CharField("Payment Prefix",  max_length=10, default='PMT',  blank=True)
    include_year_in_payment_number = models.BooleanField("Year in Payment Number",  default=True)
    receipt_prefix                 = models.CharField("Receipt Prefix",  max_length=10, default='RCPT', blank=True)
    expense_prefix                 = models.CharField("Expense Prefix",  max_length=10, default='EXP',  blank=True)
    include_year_in_expense_number = models.BooleanField("Year in Expense Number",  default=True)
 
    # -------------------------------------------------------------------------
    # PAYMENT TERMS
    # -------------------------------------------------------------------------
 
    default_payment_terms_days = models.PositiveIntegerField(
        "Default Payment Terms (Days)", default=30,
        validators=[MinValueValidator(1), MaxValueValidator(365)],
    )
    late_fee_enabled = models.BooleanField("Enable Late Fees", default=True)
    late_fee_percentage = models.DecimalField(
        "Late Fee Percentage", max_digits=5, decimal_places=2,
        default=Decimal('5.00'),
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
    )
    grace_period_days = models.PositiveIntegerField(
        "Grace Period (Days)", default=7,
        validators=[MinValueValidator(0), MaxValueValidator(90)],
    )
    minimum_payment_amount = models.DecimalField(
        "Minimum Payment Amount", max_digits=12, decimal_places=2,
        default=Decimal('1000.00'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    allow_partial_payments = models.BooleanField(
        "Allow Partial Payments", default=True,
    )
 
    # -------------------------------------------------------------------------
    # SCHOLARSHIPS AND DISCOUNTS
    # -------------------------------------------------------------------------
 
    auto_apply_scholarships       = models.BooleanField("Auto Apply Scholarships",    default=True)
    scholarship_approval_required = models.BooleanField("Scholarship Approval Required", default=False)
    auto_apply_discounts          = models.BooleanField("Auto Apply Discounts",        default=True)
    discount_approval_required    = models.BooleanField("Discount Approval Required",  default=True)
    discount_approval_threshold   = models.DecimalField(
        "Discount Approval Threshold", max_digits=12, decimal_places=2,
        default=Decimal('100000.00'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    early_payment_discount_enabled    = models.BooleanField("Enable Early Payment Discount", default=False)
    early_payment_discount_percentage = models.DecimalField(
        "Early Payment Discount %", max_digits=5, decimal_places=2,
        default=Decimal('2.00'),
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
    )
    early_payment_discount_days = models.PositiveIntegerField(
        "Early Payment Discount Days", default=10,
        validators=[MinValueValidator(1), MaxValueValidator(90)],
    )
 
    # -------------------------------------------------------------------------
    # EXPENSE WORKFLOW
    # -------------------------------------------------------------------------
 
    expense_approval_required    = models.BooleanField("Expense Approval Required", default=True)
    expense_approval_limit       = models.DecimalField(
        "Expense Approval Limit", max_digits=12, decimal_places=2,
        default=Decimal('100000.00'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    require_payment_confirmation = models.BooleanField("Require Payment Confirmation", default=False)
    require_expense_receipts     = models.BooleanField("Require Expense Receipts",     default=True)
    require_purchase_orders      = models.BooleanField("Require Purchase Orders",      default=False)
 
    # -------------------------------------------------------------------------
    # NOTIFICATIONS
    # -------------------------------------------------------------------------
 
    send_invoice_emails        = models.BooleanField("Send Invoice Emails",        default=True)
    send_payment_confirmations = models.BooleanField("Send Payment Confirmations", default=True)
    send_overdue_reminders     = models.BooleanField("Send Overdue Reminders",     default=True)
    overdue_reminder_days      = models.PositiveIntegerField(
        "Overdue Reminder Frequency (Days)", default=7,
        validators=[MinValueValidator(1), MaxValueValidator(30)],
    )
    send_sms_notifications = models.BooleanField("Send SMS Notifications", default=False)
 
    # -------------------------------------------------------------------------
    # TAX AND ACCOUNTING
    # -------------------------------------------------------------------------
 
    include_tax_in_prices            = models.BooleanField("Include Tax in Prices", default=False)
    default_tax_rate                 = models.DecimalField(
        "Default Tax Rate (%)", max_digits=5, decimal_places=2,
        default=Decimal('18.00'),
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
    )
    multi_currency_enabled           = models.BooleanField("Enable Multi-Currency",           default=False)
    auto_generate_recurring_invoices = models.BooleanField("Auto-Generate Recurring Invoices", default=True)
 
    # -------------------------------------------------------------------------
    # AGING AND BAD DEBT
    # -------------------------------------------------------------------------
 
    invoice_aging_periods = models.JSONField(
        "Invoice Aging Periods (days)", default=list, blank=True,
    )
    bad_debt_write_off_threshold = models.DecimalField(
        "Bad Debt Write-Off Threshold", max_digits=12, decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    auto_write_off_days = models.PositiveIntegerField(
        "Auto Write-Off Days", default=365,
        validators=[MinValueValidator(90)],
    )
 
    # =========================================================================
    # CURRENCY CHOICES
    # =========================================================================
 
    @classmethod
    def get_currency_choices(cls):
        """
        Return (code, label) tuples for all ISO 4217 currencies, sorted by code.
        Falls back to a minimal list if pycountry is unavailable.
        """
        try:
            import pycountry
            return sorted(
                [(c.alpha_3, f"{c.alpha_3} — {c.name}") for c in pycountry.currencies],
                key=lambda x: x[0],
            )
        except ImportError:
            return [
                ('UGX', 'UGX — Ugandan Shilling'),
                ('USD', 'USD — US Dollar'),
                ('EUR', 'EUR — Euro'),
                ('GBP', 'GBP — British Pound'),
                ('KES', 'KES — Kenyan Shilling'),
                ('SSD', 'SSD — South Sudanese Pound'),
                ('TZS', 'TZS — Tanzanian Shilling'),
                ('RWF', 'RWF — Rwandan Franc'),
            ]
 
    # =========================================================================
    # ACCOUNT MAPPING ACCESSORS
    # =========================================================================
 
    def get_account_mappings(self):
        """
        Return CoreAccountMappings, creating with intelligent defaults if missing.
 
        Required accounts — The Big 7 + scholarship:
        1020 → default_bank_account        (Bank Account - Main)
        1000 → default_cash_account        (Cash on Hand)
        1100 → student_receivables_account
        2000 → default_payable_account
        3000 → default_equity_account
        4000 → default_revenue_account
        5990 → default_expense_account     (Miscellaneous Expenses)
        5800 → scholarship_discount_account
 
        Raises ValueError if required accounts are missing — callers must
        ensure the chart of accounts is initialized before calling this.
        """
        try:
            return CoreAccountMappings.objects.get(financial_settings=self)
        except CoreAccountMappings.DoesNotExist:
            pass
 
        from finance.models import Account
 
        required_map = {
            'default_bank_account':         '1020',
            'default_cash_account':         '1000',
            'student_receivables_account':  '1100',
            'default_payable_account':      '2000',
            'default_equity_account':       '3000',
            'default_revenue_account':      '4000',
            'default_expense_account':      '5990',
            'scholarship_discount_account': '5800',
        }
        account_type_fallback = {
            'default_bank_account':         'ASSET',
            'default_cash_account':         'ASSET',
            'student_receivables_account':  'ASSET',
            'default_payable_account':      'LIABILITY',
            'default_equity_account':       'EQUITY',
            'default_revenue_account':      'REVENUE',
            'default_expense_account':      'EXPENSE',
            'scholarship_discount_account': 'EXPENSE',
        }
        optional_map = {
            'petty_cash_account':             '1010',
            'mobile_money_account':           '1030',
            'boarding_revenue_account':       '4100',
            'uniform_and_book_sales_account': '4200',
            'salaries_account':               '5000',
            'utilities_account':              '5100',
            'boarding_expense_account':       '5600',
        }
 
        defaults = {}
 
        for field_name, account_number in required_map.items():
            account = Account.objects.filter(
                account_number=account_number,
                is_active=True,
                is_header=False,
            ).first()
            if not account:
                account = Account.objects.filter(
                    account_type__account_type=account_type_fallback[field_name],
                    is_active=True,
                    is_header=False,
                ).first()
            if account:
                defaults[field_name] = account
 
        if len(defaults) < len(required_map):
            missing = set(required_map.keys()) - set(defaults.keys())
            raise ValueError(
                f"Cannot create CoreAccountMappings: {len(missing)} required accounts "
                f"missing: {missing}. Run: python manage.py init_school --database <alias>"
            )
 
        for field_name, account_number in optional_map.items():
            account = Account.objects.filter(
                account_number=account_number,
                is_active=True,
                is_header=False,
            ).first()
            if account:
                defaults[field_name] = account
 
        return CoreAccountMappings.objects.create(financial_settings=self, **defaults)
 
    def get_payroll_mappings(self):
        mappings, _ = PayrollAccountMappings.objects.get_or_create(financial_settings=self)
        return mappings
 
    def get_revenue_mappings(self):
        mappings, _ = RevenueAccountMappings.objects.get_or_create(financial_settings=self)
        return mappings
 
    def get_expense_mappings(self):
        mappings, _ = ExpenseAccountMappings.objects.get_or_create(financial_settings=self)
        return mappings
 
    def get_special_mappings(self):
        mappings, _ = SpecialAccountMappings.objects.get_or_create(financial_settings=self)
        return mappings
 
    # =========================================================================
    # CLASS-LEVEL ACCOUNT HELPERS
    # =========================================================================
 
    @classmethod
    def get_revenue_account(cls, invoice_type='TUITION'):
        """
        Return the GL revenue account for a given invoice type string.
 
        invoice_type is the overall invoice classification, not a FeesCategory
        category_type. For per-line-item routing from a FeesCategory instance
        use get_account_for_fee_category() instead.
 
        Supported invoice types:
            TUITION, UNIFORM, TEXTBOOK, TRANSPORT, BOARDING, MEALS, LAUNDRY,
            LATE_FEE, PENALTY, SERVICE
        """
        settings = cls.get_cached_instance()
        if not settings:
            return None
        rm = settings.get_revenue_mappings()
        cm = settings.get_account_mappings()
        mapping = {
            'UNIFORM':   rm.uniform_sales_revenue_account,
            'TEXTBOOK':  rm.textbook_sales_revenue_account,
            'TRANSPORT': rm.transport_revenue_account,
            'BOARDING':  rm.boarding_revenue_account,
            'MEALS':     rm.meals_revenue_account,
            'LAUNDRY':   rm.boarding_revenue_account,   # laundry is boarding-related revenue
            'LATE_FEE':  rm.late_fee_revenue_account,
            'PENALTY':   rm.penalty_revenue_account,
            'SERVICE':   cm.default_revenue_account,
        }
        return mapping.get(invoice_type) or cm.default_revenue_account
 
    @classmethod
    def get_account_for_fee_category(cls, fee_category):
        """
        Single entry point for FeesCategory instance → GL account resolution.
 
        This is the method invoice generators and payment processors should call.
        It handles all category types including:
          - DEPOSIT   → SpecialAccountMappings.default_student_deposit_account
                        (LIABILITY — never revenue; returns None with a warning
                        if the deposit account is not configured)
          - LATE_PAYMENT / PENALTY / TRANSPORT → RevenueAccountMappings
          - BOARDING / MEALS / LAUNDRY         → boarding_revenue_account
          - UNIFORM / BOOKS                    → uniform_and_book_sales_account
          - Everything else                    → default_revenue_account
 
        Returns:
            Account instance, or None for DEPOSIT when no deposit account is
            configured. Callers MUST handle None and must NOT fall back to
            default_revenue_account — doing so would book a liability as income.
        """
        settings = cls.get_cached_instance()
        if not settings:
            return None
        return settings.get_account_mappings().get_account_for_fee_category(fee_category)
 
    @classmethod
    def get_uniform_revenue_account(cls):
        """
        Canonical resolution for uniform sales revenue account.
 
        Resolution order:
        1. RevenueAccountMappings.uniform_sales_revenue_account
        2. CoreAccountMappings.uniform_and_book_sales_account
        3. CoreAccountMappings.default_revenue_account
        """
        settings = cls.get_cached_instance()
        if not settings:
            return None
        rm = settings.get_revenue_mappings()
        if rm.uniform_sales_revenue_account:
            return rm.uniform_sales_revenue_account
        cm = settings.get_account_mappings()
        if cm.uniform_and_book_sales_account:
            return cm.uniform_and_book_sales_account
        return cm.default_revenue_account
 
    @classmethod
    def get_cash_or_bank_account(cls, payment_method):
        """
        Return the GL cash/bank account for a given payment method.
        Delegates to CoreAccountMappings.get_cash_or_bank_account() which is
        the single source of truth for cash/bank routing logic.
        """
        settings = cls.get_cached_instance()
        if not settings:
            return None
        return settings.get_account_mappings().get_cash_or_bank_account(payment_method)
 
    # =========================================================================
    # CURRENCY HELPERS
    # =========================================================================
 
    @classmethod
    def get_school_currency(cls):
        settings = cls.get_cached_instance()
        return settings.school_currency if settings else 'UGX'
 
    @classmethod
    def get_currency_info(cls):
        settings = cls.get_cached_instance()
        if settings:
            return {
                'code':           settings.school_currency,
                'decimal_places': settings.decimal_places,
                'position':       settings.currency_position,
                'use_separator':  settings.use_thousand_separator,
            }
        return {
            'code': 'UGX', 'decimal_places': 2,
            'position': 'BEFORE', 'use_separator': True,
        }
 
    def format_currency(self, amount, include_symbol=True):
        """Format an amount using this school's currency settings."""
        try:
            amount    = Decimal(str(amount or 0))
            formatted = f"{amount:,.{self.decimal_places}f}"
            if not self.use_thousand_separator:
                formatted = formatted.replace(',', '')
            if include_symbol:
                sym = self.school_currency
                if   self.currency_position == 'BEFORE':          return f"{sym} {formatted}"
                elif self.currency_position == 'AFTER':           return f"{formatted} {sym}"
                elif self.currency_position == 'BEFORE_NO_SPACE': return f"{sym}{formatted}"
                elif self.currency_position == 'AFTER_NO_SPACE':  return f"{formatted}{sym}"
            return formatted
        except (ValueError, TypeError, InvalidOperation):
            return f"{self.school_currency} 0.{'0' * self.decimal_places}"
 
    @classmethod
    def format_amount(cls, amount, include_symbol=True):
        settings = cls.get_cached_instance()
        if settings:
            return settings.format_currency(amount, include_symbol)
        return f"UGX {amount:,.2f}" if include_symbol else f"{amount:,.2f}"
 
    def get_aging_periods(self):
        return self.invoice_aging_periods or [30, 60, 90, 120]
 
    # =========================================================================
    # TRACKED CURRENCY HELPERS
    # =========================================================================
 
    def get_currencies_needing_rates(self):
        return [c for c in (self.tracked_currencies or []) if c != self.school_currency]
 
    def add_tracked_currency(self, code):
        code = code.upper().strip()
        if not code or code == self.school_currency:
            return False
        if not self.tracked_currencies:
            self.tracked_currencies = []
        if code not in self.tracked_currencies:
            self.tracked_currencies.append(code)
            self.save(update_fields=['tracked_currencies'])
            return True
        return False
 
    def remove_tracked_currency(self, code):
        code = code.upper().strip()
        if self.tracked_currencies and code in self.tracked_currencies:
            self.tracked_currencies.remove(code)
            self.save(update_fields=['tracked_currencies'])
            return True
        return False
 
    # =========================================================================
    # VALIDATION
    # =========================================================================
 
    def clean(self):
        super().clean()
        errors = {}
 
        if self.school_currency:
            try:
                import pycountry
                currency = pycountry.currencies.get(alpha_3=self.school_currency.upper())
                if not currency:
                    errors['school_currency'] = (
                        f"'{self.school_currency}' is not a valid ISO 4217 currency code."
                    )
                else:
                    self.school_currency = self.school_currency.upper()
            except ImportError:
                if len(self.school_currency) != 3:
                    errors['school_currency'] = "Currency code must be 3 characters (ISO 4217)."
                else:
                    self.school_currency = self.school_currency.upper()
 
        if self.tracked_currencies:
            invalid = [
                c for c in self.tracked_currencies
                if not isinstance(c, str) or len(c) != 3
            ]
            if invalid:
                errors['tracked_currencies'] = (
                    f"Invalid currency codes (must be 3-char ISO 4217): {invalid}"
                )
 
        if errors:
            raise ValidationError(errors)
 
    # =========================================================================
    # SINGLETON PATTERN WITH CACHE
    # =========================================================================
 
    @classmethod
    def get_instance(cls, using=None):
        """
        Get or create the singleton FinancialSettings for the given database.
 
        Uses `using` when explicitly provided. Otherwise resolves via
        get_current_db() → 'default'. Creates with safe defaults on first
        access — no manual seeding required.
 
        Prefer get_cached_instance() in application code to avoid hitting
        the database on every request.
 
        Args:
            using: Optional explicit database alias.
 
        Returns:
            FinancialSettings instance, or None on error.
        """
        from schoolara.managers import get_current_db
 
        db = using or get_current_db() or 'default'
 
        try:
            instance, created = (
                cls.objects
                .using(db)
                .get_or_create(
                    pk=_FINANCIAL_SETTINGS_UUID,
                    defaults={
                        'school_currency':                    'UGX',
                        'currency_position':                  'BEFORE',
                        'decimal_places':                     2,
                        'use_thousand_separator':             True,
                        'auto_update_exchange_rates':         False,
                        'exchange_rate_update_frequency':     6,
                        'tracked_currencies':                 [],
                        'invoice_prefix':                     'INV',
                        'include_year_in_invoice_number':     True,
                        'payment_prefix':                     'PMT',
                        'include_year_in_payment_number':     True,
                        'receipt_prefix':                     'RCPT',
                        'expense_prefix':                     'EXP',
                        'include_year_in_expense_number':     True,
                        'default_payment_terms_days':         30,
                        'late_fee_enabled':                   True,
                        'late_fee_percentage':                Decimal('5.00'),
                        'grace_period_days':                  7,
                        'minimum_payment_amount':             Decimal('1000.00'),
                        'allow_partial_payments':             True,
                        'auto_apply_scholarships':            True,
                        'scholarship_approval_required':      False,
                        'auto_apply_discounts':               True,
                        'discount_approval_required':         True,
                        'discount_approval_threshold':        Decimal('100000.00'),
                        'early_payment_discount_enabled':     False,
                        'early_payment_discount_percentage':  Decimal('2.00'),
                        'early_payment_discount_days':        10,
                        'expense_approval_required':          True,
                        'expense_approval_limit':             Decimal('100000.00'),
                        'require_payment_confirmation':       False,
                        'require_expense_receipts':           True,
                        'require_purchase_orders':            False,
                        'send_invoice_emails':                True,
                        'send_payment_confirmations':         True,
                        'send_overdue_reminders':             True,
                        'overdue_reminder_days':              7,
                        'send_sms_notifications':             False,
                        'include_tax_in_prices':              False,
                        'default_tax_rate':                   Decimal('18.00'),
                        'multi_currency_enabled':             False,
                        'auto_generate_recurring_invoices':   True,
                        'invoice_aging_periods':              [30, 60, 90, 120],
                        'bad_debt_write_off_threshold':       Decimal('0.00'),
                        'auto_write_off_days':                365,
                    }
                )
            )
 
            if created:
                logger.info(
                    f"FinancialSettings created with defaults in database '{db}'. "
                    "Visit /core/financial-settings/ to customise."
                )
 
            return instance
 
        except Exception as e:
            logger.error(
                f"Error accessing FinancialSettings in database '{db}': {e}",
                exc_info=True,
            )
            return None
 
    @classmethod
    def get_cached_instance(cls, using=None):
        """
        Return the singleton FinancialSettings using a per-database
        class-level cache to avoid hitting the DB on every request.
 
        The cache is a dict keyed by database alias so:
        - Each school database has its own cached instance.
        - Flushing one school's cache does not affect others.
        - Cache is invalidated automatically by save() for the specific
          database that was written to.
 
        Args:
            using: Optional explicit database alias.
 
        Returns:
            FinancialSettings instance, or None on error.
        """
        from schoolara.managers import get_current_db
 
        db = using or get_current_db() or 'default'
 
        if cls._instance_cache.get(db) is None:
            cls._instance_cache[db] = cls.get_instance(using=db)
 
        return cls._instance_cache[db]
 
    @classmethod
    def clear_cache(cls, using=None):
        """
        Invalidate the per-database singleton cache.
 
        Args:
            using: Database alias to clear.
                   Pass None to clear ALL databases (e.g. in tests).
                   Pass the specific alias to clear only one school's cache
                   (this is what save() does automatically).
        """
        if using:
            cls._instance_cache.pop(using, None)
            logger.debug(
                f"FinancialSettings cache cleared for database '{using}'"
            )
        else:
            cls._instance_cache.clear()
            logger.debug("FinancialSettings cache cleared for all databases")
 
    def save(self, *args, **kwargs):
        """
        Lock pk to the fixed singleton UUID, persist, then invalidate only
        the cache entry for the database this instance was saved to.
        """
        self.pk = _FINANCIAL_SETTINGS_UUID
        db = kwargs.get('using') or self._state.db or 'default'
        super().save(*args, **kwargs)
        FinancialSettings.clear_cache(using=db)
 
    def delete(self, *args, **kwargs):
        """Prevent deletion of the singleton."""
        pass
 
    def __str__(self):
        return f"Financial Settings — {self.school_currency}"
 
    class Meta:
        verbose_name        = "Financial Settings"
        verbose_name_plural = "Financial Settings"


# =============================================================================
# SIMPLIFIED CORE ACCOUNT MAPPINGS
# =============================================================================

class CoreAccountMappings(BaseModel):
    """
    Simplified core account mappings that work universally for all schools.
 
    The Big 7 Required Accounts:
    1. default_bank_account         (ASSET)
    2. default_cash_account         (ASSET)
    3. student_receivables_account  (ASSET — control account)
    4. default_payable_account      (LIABILITY)
    5. default_equity_account       (EQUITY)
    6. default_revenue_account      (REVENUE)
    7. default_expense_account      (EXPENSE)
    +  scholarship_discount_account (EXPENSE — special case)
 
    GL ROUTING ENTRY POINTS
    -----------------------
    get_account_for_fee_category(fee_category)
        The recommended entry point for invoice generators and payment
        processors. Handles ALL FeesCategory types including:
          - DEPOSIT    → SpecialAccountMappings.default_student_deposit_account
                         Returns None (not revenue) if account not configured.
          - LATE_PAYMENT / PENALTY / TRANSPORT
                       → RevenueAccountMappings specific accounts
          - BOARDING / MEALS / LAUNDRY
                       → boarding_revenue_account
          - UNIFORM / BOOKS
                       → uniform_and_book_sales_account
          - Everything else → default_revenue_account
 
    get_revenue_account(fee_category)
        Lower-level method — handles boarding/uniform routing only.
        Does NOT handle DEPOSIT, PENALTY, or TRANSPORT types.
        Call get_account_for_fee_category() instead.
 
    get_cash_or_bank_account(payment_method)
        Single source of truth for payment method → cash/bank account routing.
 
    CASH/BANK ROUTING
    -----------------
    All payment-method-to-account routing is handled by get_cash_or_bank_account()
    on this class. FinancialSettings.get_cash_or_bank_account() delegates here
    and must not duplicate the routing logic.
 
    UNIFORM REVENUE
    ---------------
    uniform_and_book_sales_account is an optional specialised field.
    For uniform-specific revenue resolution use
    FinancialSettings.get_uniform_revenue_account() which checks
    RevenueAccountMappings.uniform_sales_revenue_account first.
    """
 
    financial_settings = models.OneToOneField(
        'FinancialSettings',
        on_delete=models.CASCADE,
        related_name='account_mappings',
    )
 
    # =========================================================================
    # REQUIRED: THE BIG 7+ ACCOUNTS
    # =========================================================================
 
    default_bank_account = models.ForeignKey(
        'finance.Account', on_delete=models.PROTECT,
        related_name='default_bank_mappings',
        help_text='Primary bank account for school operations (ASSET)',
    )
    default_cash_account = models.ForeignKey(
        'finance.Account', on_delete=models.PROTECT,
        related_name='default_cash_mappings',
        help_text='Primary cash account - Cash on Hand (ASSET)',
    )
    student_receivables_account = models.ForeignKey(
        'finance.Account', on_delete=models.PROTECT,
        related_name='receivables_mappings',
        help_text='Accounts Receivable - Students (ASSET - CONTROL ACCOUNT)',
    )
    default_payable_account = models.ForeignKey(
        'finance.Account', on_delete=models.PROTECT,
        related_name='default_payable_mappings',
        help_text='Accounts Payable - vendors and suppliers (LIABILITY)',
    )
    default_equity_account = models.ForeignKey(
        'finance.Account', on_delete=models.PROTECT,
        related_name='default_equity_mappings',
        help_text='Capital/Retained Earnings account (EQUITY)',
    )
    default_revenue_account = models.ForeignKey(
        'finance.Account', on_delete=models.PROTECT,
        related_name='default_revenue_mappings',
        help_text='Default account for all school fees revenue (REVENUE)',
    )
    default_expense_account = models.ForeignKey(
        'finance.Account', on_delete=models.PROTECT,
        related_name='default_expense_mappings',
        help_text='Default account for general expenses (EXPENSE)',
    )
    scholarship_discount_account = models.ForeignKey(
        'finance.Account', on_delete=models.PROTECT,
        related_name='scholarship_mappings',
        help_text='Account for scholarships and discounts (EXPENSE)',
    )
 
    # =========================================================================
    # OPTIONAL: COMMON SPECIALISED ACCOUNTS
    # =========================================================================
 
    petty_cash_account = models.ForeignKey(
        'finance.Account', on_delete=models.PROTECT,
        related_name='core_petty_cash_mappings',
        null=True, blank=True,
        help_text='Separate petty cash account (ASSET - optional)',
    )
    mobile_money_account = models.ForeignKey(
        'finance.Account', on_delete=models.PROTECT,
        related_name='core_mobile_money_mappings',
        null=True, blank=True,
        help_text='Mobile money clearing account (ASSET - optional)',
    )
    boarding_revenue_account = models.ForeignKey(
        'finance.Account', on_delete=models.PROTECT,
        related_name='core_boarding_revenue_mappings',
        null=True, blank=True,
        help_text=(
            "Boarding revenue for BOARDING, MEALS, and LAUNDRY category types. "
            "Distinct from RevenueAccountMappings.boarding_revenue_account which "
            "handles invoice-type-level routing. Falls back to default_revenue_account."
        ),
    )
    uniform_and_book_sales_account = models.ForeignKey(
        'finance.Account', on_delete=models.PROTECT,
        related_name='uniform_book_sales_mappings',
        null=True, blank=True,
        help_text=(
            "Uniform and book sales revenue (REVENUE - optional). "
            "Used as fallback by FinancialSettings.get_uniform_revenue_account(). "
            "Falls back to default_revenue_account if not set."
        ),
    )
    salaries_account = models.ForeignKey(
        'finance.Account', on_delete=models.PROTECT,
        related_name='salaries_mappings',
        null=True, blank=True,
        help_text='Staff salaries expense (EXPENSE - optional, falls back to default)',
    )
    utilities_account = models.ForeignKey(
        'finance.Account', on_delete=models.PROTECT,
        related_name='utilities_mappings',
        null=True, blank=True,
        help_text='Utilities expenses (EXPENSE - optional, falls back to default)',
    )
    boarding_expense_account = models.ForeignKey(
        'finance.Account', on_delete=models.PROTECT,
        related_name='boarding_expense_mappings',
        null=True, blank=True,
        help_text='Boarding operational expenses (EXPENSE - optional, falls back to default)',
    )
 
    # =========================================================================
    # CASH/BANK ROUTING — single source of truth
    # =========================================================================
 
    def get_cash_or_bank_account(self, payment_method=None):
        """
        Get appropriate cash or bank account for a payment method.
 
        This is the SINGLE SOURCE OF TRUTH for payment-method-to-account routing.
        FinancialSettings.get_cash_or_bank_account() delegates here.
 
        Resolution order:
        1. PETTY_CASH          → petty_cash_account (falls back to default_cash_account)
        2. MOBILE_MONEY codes  → mobile_money_account (falls back to default_bank_account)
        3. CASH / CASH_ON_HAND → default_cash_account
        4. Everything else     → default_bank_account
        """
        if payment_method and hasattr(payment_method, 'code'):
            code = payment_method.code
 
            if code == 'PETTY_CASH':
                return self.petty_cash_account or self.default_cash_account
 
            if code in ('MOBILE_MONEY', 'MTN_MOBILE', 'AIRTEL_MOBILE'):
                return self.mobile_money_account or self.default_bank_account
 
            if code in ('CASH', 'CASH_ON_HAND'):
                return self.default_cash_account
 
        return self.default_bank_account
 
    # =========================================================================
    # REVENUE ACCOUNT RESOLUTION
    # =========================================================================
 
    def get_revenue_account(self, fee_category=None):
        """
        Get appropriate revenue account for boarding and uniform category types.
 
        NOTE: This is a lower-level routing method. It does NOT handle:
          - DEPOSIT (liability, not revenue)
          - LATE_PAYMENT / PENALTY / TRANSPORT (need RevenueAccountMappings)
 
        For complete routing across all category types use
        get_account_for_fee_category() instead.
 
        Resolution order:
        1. BOARDING / MEALS / LAUNDRY → boarding_revenue_account (if set)
        2. UNIFORM / BOOKS            → uniform_and_book_sales_account (if set)
        3. default_revenue_account    (always set — required field)
        """
        if fee_category and hasattr(fee_category, 'category_type'):
            category_type = fee_category.category_type
 
            # Guard: DEPOSIT must never route to revenue.
            # Callers should use get_account_for_fee_category() to avoid this.
            if category_type == 'DEPOSIT':
                logger.error(
                    f"get_revenue_account() called with DEPOSIT category "
                    f"'{getattr(fee_category, 'name', category_type)}'. "
                    "DEPOSIT is a liability type — it must never post to a revenue account. "
                    "Call get_account_for_fee_category() instead."
                )
                return None
 
            # Boarding-related — includes LAUNDRY (was missing in original)
            if category_type in ('BOARDING', 'MEALS', 'LAUNDRY'):
                if self.boarding_revenue_account:
                    return self.boarding_revenue_account
 
            # Uniform and book sales
            if category_type in ('UNIFORM', 'BOOKS'):
                if self.uniform_and_book_sales_account:
                    return self.uniform_and_book_sales_account
 
        return self.default_revenue_account
 
    def get_account_for_fee_category(self, fee_category):
        """
        Single source of truth for FeesCategory → GL account resolution.
 
        Handles all category types from FeesCategory.CATEGORY_TYPE_CHOICES
        including the types added in the FeesCategory rewrite (DEPOSIT,
        PENALTY, PTA, PHOTO, PUBLICATION).
 
        DEPOSIT → SpecialAccountMappings.default_student_deposit_account
                  Returns None if that account is not configured. Caller MUST
                  handle None and must NOT fall back to any revenue account.
 
        LATE_PAYMENT / PENALTY / TRANSPORT
                  → RevenueAccountMappings dedicated accounts (if set)
                  → default_revenue_account (fallback)
 
        BOARDING / MEALS / LAUNDRY → boarding_revenue_account
        UNIFORM / BOOKS            → uniform_and_book_sales_account
        Everything else            → default_revenue_account
 
        Args:
            fee_category: FeesCategory instance or None
 
        Returns:
            Account instance, or None for DEPOSIT when no deposit account
            is configured (caller must handle this case explicitly).
        """
        if not fee_category:
            return self.default_revenue_account
 
        category_type = getattr(fee_category, 'category_type', None)
        if not category_type:
            return self.default_revenue_account
 
        # ── DEPOSIT — liability, never revenue ────────────────────────────────
        # Check is_liability_type() via the method if available, or by type string.
        is_liability = (
            fee_category.is_liability_type()
            if callable(getattr(fee_category, 'is_liability_type', None))
            else category_type == 'DEPOSIT'
        )
        if is_liability:
            try:
                special = self.financial_settings.special_account_mappings
                if special.default_student_deposit_account:
                    return special.default_student_deposit_account
            except Exception:
                pass
            logger.warning(
                f"No student deposit liability account configured for DEPOSIT "
                f"fee category '{getattr(fee_category, 'name', category_type)}'. "
                "Configure SpecialAccountMappings.default_student_deposit_account "
                "to prevent incorrect posting to revenue."
            )
            return None  # Caller must handle — do NOT fall through to revenue
 
        # ── Penalty / transport — try RevenueAccountMappings ──────────────────
        try:
            rm = self.financial_settings.revenue_account_mappings
 
            if category_type == 'LATE_PAYMENT' and rm.late_fee_revenue_account:
                return rm.late_fee_revenue_account
 
            if category_type == 'PENALTY' and rm.penalty_revenue_account:
                return rm.penalty_revenue_account
 
            if category_type == 'TRANSPORT' and rm.transport_revenue_account:
                return rm.transport_revenue_account
 
        except Exception as e:
            logger.debug(
                f"RevenueAccountMappings not accessible for fee category "
                f"'{getattr(fee_category, 'name', category_type)}': {e}"
            )
 
        # ── All other types — standard revenue routing ────────────────────────
        return self.get_revenue_account(fee_category)
 
    # =========================================================================
    # EXPENSE ACCOUNT RESOLUTION
    # =========================================================================
 
    def get_expense_account(self, expense_category=None):
        """
        Get appropriate expense account with intelligent fallback.
 
        Resolution order:
        1. expense_category.default_expense_account (if set on category)
        2. category_type == 'STAFF'      → salaries_account (if set)
        3. category_type == 'UTILITIES'  → utilities_account (if set)
        4. category_type == 'MEALS'      → boarding_expense_account (if set)
        5. default_expense_account       (always set — required field)
        """
        if expense_category:
            if (hasattr(expense_category, 'default_expense_account')
                    and expense_category.default_expense_account):
                return expense_category.default_expense_account
 
            if hasattr(expense_category, 'category_type'):
                category_type = expense_category.category_type
 
                if category_type == 'STAFF' and self.salaries_account:
                    return self.salaries_account
 
                if category_type == 'UTILITIES' and self.utilities_account:
                    return self.utilities_account
 
                if category_type == 'MEALS' and self.boarding_expense_account:
                    return self.boarding_expense_account
 
        return self.default_expense_account
 
    def get_scholarship_account(self):
        return self.scholarship_discount_account
 
    def get_payable_account(self):
        return self.default_payable_account
 
    def get_equity_account(self):
        return self.default_equity_account
 
    # =========================================================================
    # VALIDATION
    # =========================================================================
 
    def clean(self):
        """
        Validate account type categories and that no mapped account
        is a header account (header accounts cannot receive journal postings).
        """
        super().clean()
        errors = {}
 
        # ── Account type validation ───────────────────────────────────────────
 
        _type_requirements = [
            ('default_bank_account',         'ASSET'),
            ('default_cash_account',         'ASSET'),
            ('student_receivables_account',  'ASSET'),
            ('default_payable_account',      'LIABILITY'),
            ('default_equity_account',       'EQUITY'),
            ('default_revenue_account',      'REVENUE'),
            ('default_expense_account',      'EXPENSE'),
            ('scholarship_discount_account', 'EXPENSE'),
            ('petty_cash_account',           'ASSET'),
            ('mobile_money_account',         'ASSET'),
            ('boarding_revenue_account',     'REVENUE'),
            ('uniform_and_book_sales_account','REVENUE'),
            ('salaries_account',             'EXPENSE'),
            ('utilities_account',            'EXPENSE'),
            ('boarding_expense_account',     'EXPENSE'),
        ]
 
        for field_name, expected_type in _type_requirements:
            account = getattr(self, field_name, None)
            if account and account.account_type.account_type != expected_type:
                errors[field_name] = f"Must be a {expected_type} account"
 
        # ── Header account validation ─────────────────────────────────────────
 
        _postable_fields = [
            field_name for field_name, _ in _type_requirements
        ]
        for field_name in _postable_fields:
            account = getattr(self, field_name, None)
            if account and account.is_header:
                errors[field_name] = (
                    f"'{account.name}' is a header account and cannot receive "
                    "postings. Select a posting account."
                )
 
        if errors:
            raise ValidationError(errors)
 
    class Meta:
        verbose_name        = "Core Account Mappings"
        verbose_name_plural = "Core Account Mappings"
 
    def __str__(self):
        return f"Account Mappings for {self.financial_settings}"


# =============================================================================
# REVENUE ACCOUNT MAPPINGS
# =============================================================================

class RevenueAccountMappings(BaseModel):
    """Specific revenue account mappings for different invoice types."""

    financial_settings = models.OneToOneField(
        'FinancialSettings',
        on_delete=models.CASCADE,
        related_name='revenue_account_mappings',
    )

    uniform_sales_revenue_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='uniform_revenue_mappings',
        null=True, blank=True,
        help_text='Revenue account for uniform sales',
    )

    textbook_sales_revenue_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='textbook_revenue_mappings',
        null=True, blank=True,
        help_text='Revenue account for textbook sales',
    )

    transport_revenue_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='transport_revenue_mappings',
        null=True, blank=True,
        help_text='Revenue account for transportation fees',
    )

    boarding_revenue_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='boarding_revenue_mappings',
        null=True, blank=True,
        help_text=(
            "Revenue account for boarding fees (invoice-type-level routing). "
            "Distinct from CoreAccountMappings.boarding_revenue_account "
            "which handles category-level routing."
        ),
    )

    meals_revenue_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='meals_revenue_mappings',
        null=True, blank=True,
        help_text='Revenue account for meal fees',
    )

    late_fee_revenue_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='late_fee_revenue_mappings',
        null=True, blank=True,
        help_text='Revenue account for late payment fees',
    )

    penalty_revenue_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='penalty_revenue_mappings',
        null=True, blank=True,
        help_text='Revenue account for penalties and fines',
    )

    donation_revenue_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='donation_revenue_mappings',
        null=True, blank=True,
        help_text='Revenue account for donations received',
    )

    grant_revenue_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='grant_revenue_mappings',
        null=True, blank=True,
        help_text='Revenue account for grants received',
    )

    def __str__(self):
        return f"Revenue Account Mappings for {self.financial_settings}"

    class Meta:
        verbose_name        = "Revenue Account Mappings"
        verbose_name_plural = "Revenue Account Mappings"


# =============================================================================
# EXPENSE ACCOUNT MAPPINGS
# =============================================================================

class ExpenseAccountMappings(BaseModel):
    """Expense account mappings for different expense categories."""

    financial_settings = models.OneToOneField(
        'FinancialSettings',
        on_delete=models.CASCADE,
        related_name='expense_account_mappings',
    )

    default_inventory_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='inventory_mappings',
        null=True, blank=True,
        help_text='Default account for inventory asset',
    )

    default_cogs_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='cogs_mappings',
        null=True, blank=True,
        help_text='Default account for cost of goods sold',
    )

    supplies_expense_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='supplies_expense_mappings',
        null=True, blank=True,
        help_text='Expense account for school supplies',
    )

    utilities_expense_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='utilities_expense_mappings',
        null=True, blank=True,
        help_text='Expense account for utilities',
    )

    maintenance_expense_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='maintenance_expense_mappings',
        null=True, blank=True,
        help_text='Expense account for maintenance',
    )

    fixed_assets_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='fixed_assets_mappings',
        null=True, blank=True,
        help_text='Asset account for property, plant, equipment',
    )

    accumulated_depreciation_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='accumulated_depreciation_mappings',
        null=True, blank=True,
        help_text='Contra-asset account for depreciation',
    )

    depreciation_expense_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='depreciation_expense_mappings',
        null=True, blank=True,
        help_text='Expense account for depreciation charges',
    )

    def __str__(self):
        return f"Expense Account Mappings for {self.financial_settings}"

    class Meta:
        verbose_name        = "Expense Account Mappings"
        verbose_name_plural = "Expense Account Mappings"


# =============================================================================
# PAYROLL ACCOUNT MAPPINGS
# =============================================================================

class PayrollAccountMappings(BaseModel):
    """Payroll-specific account mappings."""

    financial_settings = models.OneToOneField(
        'FinancialSettings',
        on_delete=models.CASCADE,
        related_name='payroll_account_mappings',
    )

    salaries_expense_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='salaries_expense_mappings',
        null=True, blank=True,
        help_text='Expense account for staff salaries',
    )

    wages_payable_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='wages_payable_mappings',
        null=True, blank=True,
        help_text='Liability account for accrued salaries',
    )

    payroll_tax_payable_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='payroll_tax_mappings',
        null=True, blank=True,
        help_text='Liability account for payroll taxes',
    )

    social_security_payable_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='social_security_mappings',
        null=True, blank=True,
        help_text='Liability account for social security',
    )

    pension_payable_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='pension_payable_mappings',
        null=True, blank=True,
        help_text='Liability account for pension contributions',
    )

    housing_allowance_expense_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='housing_allowance_mappings',
        null=True, blank=True,
        help_text='Expense account for housing allowances',
    )

    transport_allowance_expense_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='transport_allowance_mappings',
        null=True, blank=True,
        help_text='Expense account for transport allowances',
    )

    medical_allowance_expense_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='medical_allowance_mappings',
        null=True, blank=True,
        help_text='Expense account for medical allowances',
    )

    general_allowance_expense_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='general_allowance_mappings',
        null=True, blank=True,
        help_text='Expense account for other allowances',
    )

    overtime_expense_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='overtime_expense_mappings',
        null=True, blank=True,
        help_text='Expense account for overtime payments',
    )

    bonus_expense_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='bonus_expense_mappings',
        null=True, blank=True,
        help_text='Expense account for bonuses',
    )

    commission_expense_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='commission_expense_mappings',
        null=True, blank=True,
        help_text='Expense account for sales commissions',
    )

    staff_benefits_expense_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='staff_benefits_mappings',
        null=True, blank=True,
        help_text='Expense account for employee benefits',
    )

    staff_insurance_expense_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='staff_insurance_mappings',
        null=True, blank=True,
        help_text='Expense account for staff insurance',
    )

    staff_pension_contribution_expense_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='staff_pension_contribution_mappings',
        null=True, blank=True,
        help_text='Expense account for pension contributions',
    )

    def __str__(self):
        return f"Payroll Account Mappings for {self.financial_settings}"

    class Meta:
        verbose_name        = "Payroll Account Mappings"
        verbose_name_plural = "Payroll Account Mappings"


# =============================================================================
# SPECIAL ACCOUNT MAPPINGS
# =============================================================================

class SpecialAccountMappings(BaseModel):
    """Special account mappings for specific transactions."""

    financial_settings = models.OneToOneField(
        'FinancialSettings',
        on_delete=models.CASCADE,
        related_name='special_account_mappings',
    )

    default_student_deposit_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='student_deposit_mappings',
        null=True, blank=True,
        help_text='Liability account for student deposits',
    )

    student_credit_balance_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='student_credit_mappings',
        null=True, blank=True,
        help_text='Liability account for student overpayments',
    )

    unearned_revenue_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='unearned_revenue_mappings',
        null=True, blank=True,
        help_text='Liability account for advance payments',
    )

    mobile_money_clearing_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='mobile_money_mappings',
        null=True, blank=True,
        help_text=(
            'Clearing/suspense account for mobile money reconciliation. '
            'NOT used for payment routing — use CoreAccountMappings.mobile_money_account instead.'
        ),
    )

    payment_processing_fee_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='payment_processing_fee_mappings',
        null=True, blank=True,
        help_text='Expense account for payment processing fees',
    )

    default_refund_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='refund_mappings',
        null=True, blank=True,
        help_text='Contra-revenue account for refunds',
    )

    bad_debt_expense_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='bad_debt_mappings',
        null=True, blank=True,
        help_text='Expense account for bad debt write-offs',
    )

    allowance_for_doubtful_accounts = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='doubtful_accounts_mappings',
        null=True, blank=True,
        help_text='Contra-asset account for doubtful accounts',
    )

    default_rounding_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='rounding_mappings',
        null=True, blank=True,
        help_text='Account for currency rounding differences',
    )

    default_currency_gain_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='currency_gain_mappings',
        null=True, blank=True,
        help_text='Account for foreign currency gains',
    )

    default_currency_loss_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='currency_loss_mappings',
        null=True, blank=True,
        help_text='Account for foreign currency losses',
    )

    withholding_tax_payable_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='withholding_tax_mappings',
        null=True, blank=True,
        help_text='Liability account for withholding tax',
    )

    suspense_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='suspense_mappings',
        null=True, blank=True,
        help_text='Temporary holding account',
    )

    bank_reconciliation_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='bank_reconciliation_mappings',
        null=True, blank=True,
        help_text='Temporary account for bank reconciliation',
    )

    staff_loan_receivable_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='staff_loan_mappings',
        null=True, blank=True,
        help_text='Asset account for staff loans',
    )

    staff_advance_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='staff_advance_mappings',
        null=True, blank=True,
        help_text='Asset account for salary advances',
    )

    recruitment_expense_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='recruitment_expense_mappings',
        null=True, blank=True,
        help_text='Expense account for recruitment costs',
    )

    staff_training_expense_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='staff_training_mappings',
        null=True, blank=True,
        help_text='Expense account for staff training',
    )

    severance_expense_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='severance_expense_mappings',
        null=True, blank=True,
        help_text='Expense account for severance payments',
    )

    gratuity_payable_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='gratuity_payable_mappings',
        null=True, blank=True,
        help_text='Liability account for gratuity accrued',
    )

    def __str__(self):
        return f"Special Account Mappings for {self.financial_settings}"

    class Meta:
        verbose_name        = "Special Account Mappings"
        verbose_name_plural = "Special Account Mappings"


# =============================================================================
# FISCAL YEAR MODEL
# =============================================================================

class FiscalYear(BaseModel):
    """
    Fiscal/Academic year for school operations.
    Represents the entire year with multiple periods/terms within it.
    """

    STATUS_CHOICES = [
        ('DRAFT',  'Draft'),
        ('ACTIVE', 'Active'),
        ('CLOSED', 'Closed'),
        ('LOCKED', 'Locked'),
    ]

    name = models.CharField(
        "Academic Year Name",
        max_length=50,
        unique=True,
        help_text="e.g., '2024', '2024/2025', 'Academic Year 2024-2025'",
    )

    code = models.CharField(
        "Academic Year Code",
        max_length=20,
        unique=True,
        help_text="Short code e.g., 'AY2024', '2024-25'",
    )

    start_date = models.DateField(
        "Start Date",
        db_index=True,
        help_text="When this academic year begins",
    )

    end_date = models.DateField(
        "End Date",
        db_index=True,
        help_text="When this academic year ends",
    )

    status = models.CharField(
        "Status",
        max_length=10,
        choices=STATUS_CHOICES,
        default='DRAFT',
        blank=True,
    )

    is_active = models.BooleanField(
        "Is Active",
        default=False,
        db_index=True,
        help_text="Only one academic year can be active at a time",
    )

    is_closed = models.BooleanField(
        "Is Closed",
        default=False,
        help_text="Academic year has been closed and finalized",
    )

    is_locked = models.BooleanField(
        "Is Locked",
        default=False,
        help_text="Academic year is locked for editing (for auditing)",
    )

    description = models.TextField(
        "Description",
        blank=True,
        help_text="Optional description or notes about this academic year",
    )

    closed_at = models.DateTimeField(
        "Closed At",
        null=True, blank=True,
        help_text="When this academic year was closed",
    )

    closed_by_id = models.CharField(
        "Closed By",
        max_length=50,
        null=True, blank=True,
        help_text="User ID who closed this academic year",
    )

    class Meta:
        ordering = ['-start_date']
        indexes = [
            models.Index(fields=['start_date', 'end_date']),
            models.Index(fields=['status']),
            models.Index(fields=['is_active']),
        ]
        verbose_name        = "Academic Year"
        verbose_name_plural = "Academic Years"

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        errors = {}

        if self.start_date and self.end_date:
            if self.start_date >= self.end_date:
                errors['end_date'] = "End date must be after start date"

            overlapping = FiscalYear.objects.filter(
                models.Q(start_date__lte=self.end_date)
                & models.Q(end_date__gte=self.start_date)
            ).exclude(pk=self.pk)

            if overlapping.exists():
                errors['start_date'] = (
                    f"This academic year overlaps with: "
                    f"{', '.join([str(fy) for fy in overlapping])}"
                )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.is_locked:
            self.status = 'LOCKED'
        elif self.is_closed:
            self.status = 'CLOSED'
        elif self.is_active:
            self.status = 'ACTIVE'
        else:
            self.status = 'DRAFT'

        self.full_clean()

        if self.is_active:
            FiscalYear.objects.exclude(pk=self.pk).update(is_active=False)

        super().save(*args, **kwargs)

    # -------------------------------------------------------------------------
    # CLASS METHODS
    # -------------------------------------------------------------------------

    @classmethod
    def get_active_fiscal_year(cls):
        return cls.objects.filter(is_active=True).first()

    @classmethod
    def get_current_year_name(cls):
        active = cls.get_active_fiscal_year()
        return active.name if active else None

    @classmethod
    def get_by_date(cls, check_date):
        return cls.objects.filter(
            start_date__lte=check_date,
            end_date__gte=check_date,
        ).first()

    # -------------------------------------------------------------------------
    # PROGRESS TRACKING METHODS
    # -------------------------------------------------------------------------

    def get_progress_percentage(self):
        from core.utils import get_school_today
        today         = get_school_today()
        duration_days = self.get_duration_days()

        if today < self.start_date:
            return 0.0
        if today > self.end_date:
            return 100.0
        if duration_days > 0:
            elapsed  = (today - self.start_date).days
            progress = (elapsed / duration_days) * 100
            return round(min(progress, 100.0), 2)
        return 0.0

    def get_elapsed_days(self):
        from core.utils import get_school_today
        today = get_school_today()
        if today < self.start_date:
            return 0
        if today > self.end_date:
            return self.get_duration_days()
        return (today - self.start_date).days

    def get_remaining_days(self):
        from core.utils import get_school_today
        today = get_school_today()
        if today > self.end_date:
            return 0
        if today < self.start_date:
            return self.get_duration_days()
        return (self.end_date - today).days

    def is_current(self):
        from core.utils import get_school_today
        today = get_school_today()
        return self.start_date <= today <= self.end_date

    def is_upcoming(self):
        from core.utils import get_school_today
        return self.start_date > get_school_today()

    def is_past(self):
        from core.utils import get_school_today
        return self.end_date < get_school_today()

    def get_status_display_class(self):
        if self.is_locked:
            return 'status-locked'
        elif self.is_closed:
            return 'status-closed'
        elif self.is_active:
            return 'status-active'
        return 'status-draft'

    # -------------------------------------------------------------------------
    # INSTANCE METHODS
    # -------------------------------------------------------------------------

    def close_fiscal_year(self, user=None):
        if self.is_closed:
            return
        from core.utils import get_school_current_time
        for period in self.fiscal_periods.all():
            if not period.is_closed:
                period.close_period(user)
        self.is_closed  = True
        self.is_active  = False
        self.status     = 'CLOSED'
        self.closed_at  = get_school_current_time()
        if user:
            self.closed_by_id = str(user.id) if hasattr(user, 'id') else str(user.pk)
        self.save()

    def lock_fiscal_year(self):
        if not self.is_closed:
            raise ValidationError("Academic year must be closed before it can be locked")
        self.fiscal_periods.all().update(is_locked=True, status='LOCKED')
        self.is_locked = True
        self.status    = 'LOCKED'
        self.save()

    def unlock_fiscal_year(self):
        for period in self.fiscal_periods.all():
            period.unlock_period()
        self.is_locked = False
        self.status    = 'CLOSED' if self.is_closed else 'DRAFT'
        self.save()

    def is_date_in_year(self, check_date):
        return self.start_date <= check_date <= self.end_date

    def get_duration_days(self):
        if self.start_date and self.end_date:
            return (self.end_date - self.start_date).days + 1
        return 0

    def get_duration_weeks(self):
        days = self.get_duration_days()
        return days // 7 if days > 0 else 0

    def get_period_count(self):
        return self.fiscal_periods.count()

    def get_active_period(self):
        return self.fiscal_periods.filter(is_active=True).first()

    def get_all_periods(self):
        return self.fiscal_periods.all().order_by('period_number')

    def can_be_deleted(self):
        return self.get_period_count() == 0

    def get_closed_by(self):
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
    Unlike AcademicSession (which tracks teaching/learning periods with
    strict dates), FiscalPeriod provides flexible windows for financial
    operations and may extend beyond the academic session dates.

    RELATIONSHIP TO ACADEMIC SESSION:
    related_academic_session is optional. For ACADEMIC_ALIGNED periods,
    the fiscal period start date should be at or before the session start
    (invoices go out before term begins) and end date at or after session
    end date (collections continue after term ends). This is intentional
    and validated in clean().
    """

    PERIOD_TYPE_CHOICES = [
        ('ACADEMIC_ALIGNED', 'Academic-Aligned Period'),
        ('BREAK_PERIOD',     'Break/Holiday Period'),
        ('GRACE_PERIOD',     'Grace Period'),
        ('MONTHLY',          'Monthly Period'),
        ('QUARTERLY',        'Quarterly Period'),
        ('TERTIAL',          'Tertial Period'),
        ('SEMI_ANNUAL',      'Semi-Annual Period'),
        ('ANNUAL',           'Annual Period'),
        ('CUSTOM',           'Custom Period'),
    ]

    STATUS_CHOICES = [
        ('DRAFT',  'Draft'),
        ('ACTIVE', 'Active'),
        ('CLOSED', 'Closed'),
        ('LOCKED', 'Locked'),
    ]

    fiscal_year = models.ForeignKey(
        FiscalYear,
        on_delete=models.PROTECT,
        related_name='fiscal_periods',
        verbose_name="Fiscal Year",
        help_text="Parent fiscal year for accounting hierarchy",
    )

    name = models.CharField(
        "Period Name",
        max_length=100,
        help_text="e.g., 'Term 1 2024 Fiscal Period', 'Q1 2024', 'April Break 2024'",
    )

    code = models.CharField(
        "Period Code",
        max_length=20,
        unique=True,
        help_text="Unique code e.g., 'FP_2024_T1', 'Q1_2024', 'BREAK_APR_2024'",
    )

    period_number = models.DecimalField(
        "Period Number",
        max_digits=4,
        decimal_places=1,
        validators=[MinValueValidator(Decimal('0.1'))],
        db_index=True,
        help_text="Sequential number within fiscal year (1, 2, 3… or 1.5 for break periods)",
    )

    period_type = models.CharField(
        "Period Type",
        max_length=20,
        choices=PERIOD_TYPE_CHOICES,
        default='ACADEMIC_ALIGNED',
        db_index=True,
        help_text="Type of fiscal period",
    )

    related_academic_session = models.ForeignKey(
        'academics.AcademicSession',
        on_delete=models.SET_NULL,
        related_name='fiscal_periods',
        null=True, blank=True,
        verbose_name="Related Academic Session",
        help_text=(
            "Associated academic session (optional). "
            "For ACADEMIC_ALIGNED periods, the fiscal period start date should "
            "be at or before the session start date (invoices go out before term "
            "begins) and end date at or after session end date (collections "
            "continue after term ends). Not required for BREAK_PERIOD, "
            "MONTHLY, QUARTERLY, or other non-academic period types."
        ),
    )

    start_date = models.DateField(
        "Start Date",
        db_index=True,
        help_text="When this fiscal period begins",
    )

    end_date = models.DateField(
        "End Date",
        db_index=True,
        help_text="When this fiscal period ends",
    )

    status = models.CharField(
        "Status",
        max_length=10,
        choices=STATUS_CHOICES,
        default='DRAFT',
        db_index=True,
    )

    is_active = models.BooleanField(
        "Is Active",
        default=False,
        db_index=True,
        help_text="Whether this period is currently active for transactions",
    )

    is_closed = models.BooleanField(
        "Is Closed",
        default=False,
        help_text="Period has been closed (month-end/period-end close)",
    )

    is_locked = models.BooleanField(
        "Is Locked",
        default=False,
        help_text="Period is locked for audit compliance (no changes allowed)",
    )

    closed_at = models.DateTimeField(
        "Closed At", null=True, blank=True,
        help_text="When this period was closed",
    )
    closed_by_id = models.CharField(
        "Closed By", max_length=50, null=True, blank=True,
        help_text="User ID who closed this period",
    )
    locked_at = models.DateTimeField(
        "Locked At", null=True, blank=True,
        help_text="When this period was locked",
    )
    locked_by_id = models.CharField(
        "Locked By", max_length=50, null=True, blank=True,
        help_text="User ID who locked this period",
    )

    allow_advance_payments = models.BooleanField(
        "Allow Advance Payments", default=True,
        help_text="Accept payments for future academic sessions",
    )
    allow_arrears_payments = models.BooleanField(
        "Allow Arrears Payments", default=True,
        help_text="Accept payments for past academic sessions",
    )
    allow_invoice_generation = models.BooleanField(
        "Allow Invoice Generation", default=True,
        help_text="Allow creating new invoices in this period",
    )
    allow_refunds = models.BooleanField(
        "Allow Refunds", default=True,
        help_text="Allow processing refunds in this period",
    )
    require_approval_for_transactions = models.BooleanField(
        "Require Approval", default=False,
        help_text="Require manager approval for transactions in this period",
    )

    auto_close_date = models.DateField(
        "Auto Close Date", null=True, blank=True,
        help_text="Automatically close this period on this date",
    )
    grace_period_days = models.PositiveIntegerField(
        "Grace Period Days", default=0,
        help_text="Days beyond end_date when transactions are still accepted",
    )

    description = models.TextField(
        "Description", blank=True,
        help_text="Optional description or notes about this fiscal period",
    )
    notes = models.TextField(
        "Internal Notes", blank=True,
        help_text="Internal notes for accounting team",
    )

    class Meta:
        ordering       = ['fiscal_year', 'period_number']
        unique_together = [['fiscal_year', 'period_number']]
        verbose_name        = "Fiscal Period"
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
                name='fiscal_period_start_before_end',
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.fiscal_year})"

    def get_full_display(self):
        return f"{self.name} ({self.start_date} to {self.end_date})"

    # -------------------------------------------------------------------------
    # VALIDATION
    # -------------------------------------------------------------------------

    def clean(self):
        super().clean()
        errors = {}

        if self.start_date and self.end_date:
            if self.start_date >= self.end_date:
                errors['end_date'] = "End date must be after start date"

        if self.fiscal_year_id and self.start_date and self.end_date:
            try:
                fiscal_year = FiscalYear.objects.get(pk=self.fiscal_year_id)
                if self.start_date < fiscal_year.start_date:
                    errors['start_date'] = (
                        f"Period cannot start before fiscal year start date "
                        f"({fiscal_year.start_date})"
                    )
                if self.end_date > fiscal_year.end_date:
                    errors['end_date'] = (
                        f"Period cannot end after fiscal year end date "
                        f"({fiscal_year.end_date})"
                    )
            except FiscalYear.DoesNotExist:
                errors['fiscal_year'] = "Invalid fiscal year selected"

        if (self.related_academic_session_id
                and self.period_type == 'ACADEMIC_ALIGNED'):
            try:
                from academics.models import AcademicSession
                session = AcademicSession.objects.get(
                    pk=self.related_academic_session_id
                )
                if self.start_date and self.start_date > session.start_date:
                    errors['start_date'] = (
                        f"For academic-aligned periods, start date should be at or "
                        f"before session start ({session.start_date}) so invoices "
                        f"can be issued before term begins."
                    )
                if self.end_date and self.end_date < session.end_date:
                    errors['end_date'] = (
                        f"For academic-aligned periods, end date should be at or "
                        f"after session end ({session.end_date}) so collections "
                        f"can continue after term ends."
                    )
            except Exception:
                pass

        if self.fiscal_year_id and self.start_date and self.end_date:
            overlapping = FiscalPeriod.objects.filter(
                fiscal_year_id=self.fiscal_year_id,
                start_date__lt=self.end_date,
                end_date__gt=self.start_date,
            ).exclude(pk=self.pk)

            if overlapping.exists():
                errors['start_date'] = (
                    f"This period overlaps with: "
                    f"{', '.join([str(p) for p in overlapping])}"
                )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.is_locked:
            self.status = 'LOCKED'
        elif self.is_closed:
            self.status = 'CLOSED'
        elif self.is_active:
            self.status = 'ACTIVE'
        else:
            self.status = 'DRAFT'
        self.full_clean()
        super().save(*args, **kwargs)

    # -------------------------------------------------------------------------
    # TRANSACTION PERMISSION METHODS
    # -------------------------------------------------------------------------

    def can_accept_transactions(self):
        from core.utils import get_school_today
        if self.is_closed or self.is_locked:
            return False
        if not self.is_active:
            return False
        today = get_school_today()
        if not (self.start_date <= today <= self.end_date):
            if self.grace_period_days > 0:
                grace_end = self.end_date + timedelta(days=self.grace_period_days)
                if today > grace_end:
                    return False
            else:
                return False
        return True

    def can_accept_payments(self):
        return self.can_accept_transactions()

    def can_generate_invoices(self):
        return self.can_accept_transactions() and self.allow_invoice_generation

    def can_process_refunds(self):
        return self.can_accept_transactions() and self.allow_refunds

    def can_accept_advance_payment(self):
        return self.can_accept_transactions() and self.allow_advance_payments

    def can_accept_arrears_payment(self):
        return self.can_accept_transactions() and self.allow_arrears_payments

    # -------------------------------------------------------------------------
    # CLOSURE METHODS
    # -------------------------------------------------------------------------

    def close_period(self, user=None):
        from core.utils import get_school_current_time
        if self.is_closed:
            logger.warning(f"Fiscal period {self} is already closed")
            return
        self.is_closed  = True
        self.is_active  = False
        self.status     = 'CLOSED'
        self.closed_at  = get_school_current_time()
        if user:
            self.closed_by_id = str(user.id) if hasattr(user, 'id') else str(user.pk)
        self.save()
        logger.info(f"Fiscal period {self} closed by {self.get_closed_by_name()}")

    def lock_period(self, user=None):
        from core.utils import get_school_current_time
        if not self.is_closed:
            raise ValidationError("Period must be closed before it can be locked")
        if self.is_locked:
            logger.warning(f"Fiscal period {self} is already locked")
            return
        self.is_locked  = True
        self.status     = 'LOCKED'
        self.locked_at  = get_school_current_time()
        if user:
            self.locked_by_id = str(user.id) if hasattr(user, 'id') else str(user.pk)
        self.save()
        logger.info(f"Fiscal period {self} locked by {self.get_locked_by_name()}")

    def unlock_period(self, user=None):
        if not self.is_locked:
            logger.warning(f"Fiscal period {self} is not locked")
            return
        self.is_locked    = False
        self.status       = 'CLOSED' if self.is_closed else 'DRAFT'
        self.locked_at    = None
        self.locked_by_id = None
        self.save()
        user_name = user.get_full_name() if user else "System"
        logger.warning(f"Fiscal period {self} unlocked by {user_name}")

    def reopen_period(self, user=None):
        if self.is_locked:
            raise ValidationError("Cannot reopen a locked period. Unlock it first.")
        if not self.is_closed:
            logger.warning(f"Fiscal period {self} is not closed")
            return
        self.is_closed    = False
        self.is_active    = True
        self.status       = 'ACTIVE'
        self.closed_at    = None
        self.closed_by_id = None
        self.save()
        user_name = user.get_full_name() if user else "System"
        logger.warning(f"Fiscal period {self} reopened by {user_name}")

    # -------------------------------------------------------------------------
    # STATUS CHECK METHODS
    # -------------------------------------------------------------------------

    def is_current(self):
        from core.utils import get_school_today
        today = get_school_today()
        return self.start_date <= today <= self.end_date and self.is_active

    # NOTE: is_current_period() alias removed — use is_current() directly.

    def is_upcoming(self):
        from core.utils import get_school_today
        return self.start_date > get_school_today()

    def is_past(self):
        from core.utils import get_school_today
        return self.end_date < get_school_today()

    def is_in_grace_period(self):
        from core.utils import get_school_today
        if self.grace_period_days == 0:
            return False
        today = get_school_today()
        if today <= self.end_date:
            return False
        grace_end = self.end_date + timedelta(days=self.grace_period_days)
        return today <= grace_end

    # -------------------------------------------------------------------------
    # DURATION AND PROGRESS METHODS
    # -------------------------------------------------------------------------

    def get_duration_days(self):
        if self.start_date and self.end_date:
            return (self.end_date - self.start_date).days + 1
        return 0

    def get_duration_weeks(self):
        days = self.get_duration_days()
        return days // 7 if days > 0 else 0

    def get_duration_months(self):
        days = self.get_duration_days()
        return days // 30 if days > 0 else 0

    def get_progress_percentage(self):
        from core.utils import get_school_today
        today         = get_school_today()
        duration_days = self.get_duration_days()
        if today < self.start_date:
            return 0.0
        if today > self.end_date:
            return 100.0
        if duration_days > 0:
            elapsed  = (today - self.start_date).days
            progress = (elapsed / duration_days) * 100
            return round(min(progress, 100.0), 2)
        return 0.0

    def get_elapsed_days(self):
        from core.utils import get_school_today
        today = get_school_today()
        if today < self.start_date:
            return 0
        if today > self.end_date:
            return self.get_duration_days()
        return (today - self.start_date).days

    def get_remaining_days(self):
        from core.utils import get_school_today
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
        user = self.get_closed_by()
        if user:
            return user.get_full_name() or user.username
        return "System"

    def get_locked_by(self):
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
        user = self.get_locked_by()
        if user:
            return user.get_full_name() or user.username
        return "System"

    # -------------------------------------------------------------------------
    # DISPLAY HELPER METHODS
    # -------------------------------------------------------------------------

    def get_status_display_class(self):
        if self.is_locked:
            return 'status-locked'
        elif self.is_closed:
            return 'status-closed'
        elif self.is_active:
            return 'status-active'
        return 'status-draft'

    def get_period_type_badge_class(self):
        badge_map = {
            'ACADEMIC_ALIGNED': 'badge-primary',
            'BREAK_PERIOD':     'badge-info',
            'GRACE_PERIOD':     'badge-warning',
            'MONTHLY':          'badge-secondary',
            'QUARTERLY':        'badge-success',
            'TERTIAL':          'badge-purple',
            'SEMI_ANNUAL':      'badge-dark',
            'ANNUAL':           'badge-danger',
            'CUSTOM':           'badge-light',
        }
        return badge_map.get(self.period_type, 'badge-secondary')

    @classmethod
    def get_current_fiscal_period(cls, db=None):
        from schoolara.managers import get_current_db
        target_db = db or get_current_db()
        qs = cls.objects.using(target_db) if target_db else cls.objects
        return qs.filter(is_active=True, is_closed=False).first()

    @classmethod
    def get_current_or_upcoming(cls):
        from core.utils import get_school_today
        current = cls.get_current_fiscal_period()
        if current:
            return current
        today = get_school_today()
        return cls.objects.filter(
            start_date__gt=today, is_active=True,
        ).order_by('start_date').first()

    # -------------------------------------------------------------------------
    # FINANCIAL SUMMARY METHODS
    # NOTE: These aggregate from fees.FeeInvoice and fees.Payment via reverse
    # relations. They work correctly (related_name='invoices' and
    # related_name='payments' confirmed in fees/models.py) but create a
    # dependency from core → fees. For a cleaner architecture these should
    # move to a FiscalPeriodFinanceService in finance/services.py.
    # -------------------------------------------------------------------------

    def get_total_invoiced(self):
        try:
            from django.db.models import Sum
            total = self.invoices.aggregate(total=Sum('total_amount'))['total']
            return total or Decimal('0.00')
        except Exception as e:
            logger.error(f"Error calculating total invoiced: {e}")
            return Decimal('0.00')

    def get_total_collected(self):
        try:
            from django.db.models import Sum
            total = self.payments.aggregate(total=Sum('amount'))['total']
            return total or Decimal('0.00')
        except Exception as e:
            logger.error(f"Error calculating total collected: {e}")
            return Decimal('0.00')

    def get_collection_rate(self):
        from core.utils import calculate_percentage
        invoiced = self.get_total_invoiced()
        if invoiced == 0:
            return Decimal('0.00')
        return calculate_percentage(self.get_total_collected(), invoiced)

    def get_transaction_count(self):
        try:
            return self.invoices.count() + self.payments.count()
        except Exception as e:
            logger.error(f"Error counting transactions: {e}")
            return 0
        
    @classmethod
    def get_period_for_date(cls, date, db=None):
        if date is None:
            return None
        from schoolara.managers import get_current_db
        target_db = db or get_current_db()
        qs = cls.objects.using(target_db) if target_db else cls.objects

        period = qs.filter(
            start_date__lte=date,
            end_date__gte=date,
            is_closed=False,
            is_locked=False,
        ).order_by('-is_active', 'period_number').first()

        if period:
            return period

        return qs.filter(
            start_date__lte=date,
            end_date__gte=date,
        ).order_by('-is_active', '-status', 'period_number').first()


# =============================================================================
# PAYMENT METHOD MODEL
# =============================================================================

class PaymentMethod(BaseModel):
    """
    Payment methods for fee and payroll transactions.
 
    ACCOUNT ROUTING
    ---------------
    CoreAccountMappings.get_cash_or_bank_account() uses self.code to route
    payments to the correct GL cash or bank account. The routing codes are:
      PETTY_CASH                    → petty_cash_account
      MOBILE_MONEY / MTN_MOBILE /
      AIRTEL_MOBILE                 → mobile_money_account
      CASH / CASH_ON_HAND           → default_cash_account
      Everything else               → default_bank_account
 
    REFERENCE NUMBERS
    -----------------
    requires_reference is auto-set to True on first save for BANK_TRANSFER,
    CHEQUE, DIRECT_DEBIT, and STANDING_ORDER methods. Bank-based payments
    without a reference number cannot be reconciled. This default can be
    overridden in the admin after creation if a school genuinely does not
    use references for a particular method.
 
    TRANSACTION LIMITS
    ------------------
    minimum_amount and maximum_amount should be set for mobile money methods
    to reflect real-world provider limits (e.g. MTN Uganda caps per-transaction
    amounts). Seeded methods include sensible defaults for Ugandan providers.
    """
 
    METHOD_TYPE_CHOICES = [
        ('CASH',           'Cash'),
        ('MOBILE_MONEY',   'Mobile Money'),
        ('BANK_TRANSFER',  'Bank Transfer'),
        ('CHEQUE',         'Cheque'),
        ('CARD',           'Card Payment'),
        ('DIRECT_DEBIT',   'Direct Debit'),
        ('STANDING_ORDER', 'Standing Order'),
        ('OTHER',          'Other'),
    ]
 
    MOBILE_MONEY_PROVIDER_CHOICES = [
        ('MTN',       'MTN Mobile Money'),
        ('AIRTEL',    'Airtel Money'),
        ('AFRICELL',  'Africell Money'),
        ('SAFARICOM', 'M-Pesa (Safaricom)'),
        ('VODACOM',   'M-Pesa (Vodacom)'),
        ('TIGO',      'Tigo Pesa'),
        ('ORANGE',    'Orange Money'),
        ('OTHER',     'Other Provider'),
    ]
 
    # Methods that require a reference number for reconciliation.
    # Used by clean() and save() — defined at class level so external code
    # can check without instantiating the model.
    _REFERENCE_REQUIRED_TYPES = frozenset({
        'BANK_TRANSFER', 'CHEQUE', 'DIRECT_DEBIT', 'STANDING_ORDER',
    })
 
    # Methods that route to the mobile money account in CoreAccountMappings.
    _MOBILE_MONEY_TYPES = frozenset({'MOBILE_MONEY'})
 
    # Methods that route to the cash account in CoreAccountMappings.
    _CASH_TYPES = frozenset({'CASH'})
 
    name                  = models.CharField("Payment Method Name",       max_length=100)
    method_type           = models.CharField("Method Type",                max_length=20, choices=METHOD_TYPE_CHOICES, db_index=True)
    code                  = models.CharField("Method Code",                max_length=20, unique=True)
    mobile_money_provider = models.CharField("Mobile Money Provider",      max_length=20, choices=MOBILE_MONEY_PROVIDER_CHOICES, blank=True, null=True)
    bank_name             = models.CharField("Bank Name",                  max_length=100, blank=True)
    bank_account_number   = models.CharField("Bank Account Number",        max_length=50, blank=True)
    bank_branch           = models.CharField("Bank Branch",                max_length=100, blank=True)
    swift_code            = models.CharField("SWIFT/BIC Code",             max_length=20, blank=True)
    is_active             = models.BooleanField("Is Active",               default=True, db_index=True)
    is_default            = models.BooleanField("Is Default",              default=False)
    requires_approval     = models.BooleanField("Requires Approval",       default=False)
    minimum_amount        = models.DecimalField("Minimum Amount",          max_digits=12, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal('0'))])
    maximum_amount        = models.DecimalField("Maximum Amount",          max_digits=12, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal('0'))])
    has_transaction_fee   = models.BooleanField("Has Transaction Fee",     default=False)
    transaction_fee_type  = models.CharField("Fee Type",                   max_length=20, choices=[('FIXED', 'Fixed'), ('PERCENTAGE', 'Percentage'), ('TIERED', 'Tiered')], blank=True, null=True)
    transaction_fee_amount= models.DecimalField("Fee Amount",              max_digits=10, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal('0'))])
    fee_bearer            = models.CharField("Fee Bearer",                 max_length=20, choices=[('PARENT', 'Parent'), ('SCHOOL', 'School'), ('SHARED', 'Shared')], default='PARENT', blank=True)
    processing_time       = models.CharField("Processing Time",            max_length=100, blank=True, help_text="e.g. 'Instant', '1–3 business days'. Displayed to cashiers at payment entry.")
    requires_reference    = models.BooleanField(
        "Requires Reference Number",
        default=False,
        help_text=(
            "Auto-set to True on first save for BANK_TRANSFER, CHEQUE, "
            "DIRECT_DEBIT, and STANDING_ORDER. Can be overridden after creation."
        ),
    )
    icon                  = models.CharField("Icon CSS Class",   max_length=50, blank=True)
    color_code            = models.CharField("Color Code",       max_length=7, blank=True)
    display_order         = models.PositiveIntegerField("Display Order", default=0)
    instructions          = models.TextField("Payment Instructions", blank=True)
    notes                 = models.TextField("Internal Notes", blank=True)
 
    # =========================================================================
    # TYPE PROPERTIES
    # =========================================================================
 
    @property
    def is_mobile_money(self):
        """True for MOBILE_MONEY method type."""
        return self.method_type == 'MOBILE_MONEY'
 
    @property
    def is_cash(self):
        """True for CASH method type."""
        return self.method_type == 'CASH'
 
    @property
    def is_bank_based(self):
        """
        True for BANK_TRANSFER, CHEQUE, DIRECT_DEBIT, STANDING_ORDER.
        These all route to default_bank_account in CoreAccountMappings and
        should always have requires_reference=True for reconciliation.
        """
        return self.method_type in self._REFERENCE_REQUIRED_TYPES
 
    @property
    def is_cheque(self):
        """True for CHEQUE method type."""
        return self.method_type == 'CHEQUE'
 
    @property
    def is_card(self):
        """True for CARD method type."""
        return self.method_type == 'CARD'
 
    # =========================================================================
    # ROUTING HELPERS
    # =========================================================================
 
    def get_account_routing_code(self):
        """
        Return the code key used by CoreAccountMappings.get_cash_or_bank_account().
 
        This is always self.code. The helper exists to make the routing
        contract explicit — call this when building audit trails or logging
        which routing key was used for a payment.
        """
        return self.code
 
    # =========================================================================
    # VALIDATION
    # =========================================================================
 
    def clean(self):
        super().clean()
        errors = {}
 
        if self.method_type == 'MOBILE_MONEY' and not self.mobile_money_provider:
            errors['mobile_money_provider'] = "Mobile money provider is required."
 
        if (self.minimum_amount and self.maximum_amount
                and self.minimum_amount >= self.maximum_amount):
            errors['maximum_amount'] = "Maximum must be greater than minimum."
 
        if self.has_transaction_fee:
            if not self.transaction_fee_type:
                errors['transaction_fee_type'] = "Fee type is required when fees are enabled."
            if not self.transaction_fee_amount:
                errors['transaction_fee_amount'] = "Fee amount is required when fees are enabled."
 
        if self.color_code:
            import re
            if not re.match(r'^#[0-9A-Fa-f]{6}$', self.color_code):
                errors['color_code'] = "Invalid hex color. Use format #RRGGBB."
 
        # Warn when a bank-based method has requires_reference disabled.
        # This is allowed (the admin may have a deliberate reason) but unusual.
        if (self.method_type in self._REFERENCE_REQUIRED_TYPES
                and not self.requires_reference
                and self.pk):  # only for existing records — new ones are auto-set in save()
            errors['requires_reference'] = (
                f"{self.get_method_type_display()} payments without a reference number "
                "cannot be reliably reconciled against bank statements. "
                "Enable 'Requires Reference Number' unless you have a specific reason not to."
            )
 
        if errors:
            raise ValidationError(errors)
 
    # =========================================================================
    # SAVE
    # =========================================================================
 
    def save(self, *args, **kwargs):
        if self.code:
            self.code = self.code.upper().replace(' ', '_')
 
        if self.is_default:
            PaymentMethod.objects.exclude(pk=self.pk).update(is_default=False)
 
        # On first save, auto-set requires_reference for bank-based methods.
        # This ensures seeded methods and new admin-created methods get the
        # correct default without requiring the setup wizard to set it explicitly.
        # Existing records are not overridden — the admin may have changed this.
        if not self.pk and self.method_type in self._REFERENCE_REQUIRED_TYPES:
            self.requires_reference = True
 
        self.full_clean()
        super().save(*args, **kwargs)
 
    # =========================================================================
    # TRANSACTION CALCULATIONS
    # =========================================================================
 
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
            return False, f"Below minimum of {self.minimum_amount:,.2f}"
        if self.maximum_amount and amount > self.maximum_amount:
            return False, f"Exceeds maximum of {self.maximum_amount:,.2f}"
        return True, None
 
    # =========================================================================
    # CLASS METHODS
    # =========================================================================
 
    @classmethod
    def get_active_methods(cls):
        return cls.objects.filter(is_active=True).order_by('display_order', 'name')
 
    @classmethod
    def get_default_method(cls):
        return cls.objects.filter(is_active=True, is_default=True).first()
 
    @classmethod
    def get_mobile_money_methods(cls):
        return cls.objects.filter(
            method_type='MOBILE_MONEY', is_active=True,
        ).order_by('display_order')
 
    @classmethod
    def get_cash_method(cls):
        return cls.objects.filter(method_type='CASH', is_active=True).first()
 
    @classmethod
    def get_bank_based_methods(cls):
        """Return all active bank-based payment methods."""
        return cls.objects.filter(
            method_type__in=cls._REFERENCE_REQUIRED_TYPES,
            is_active=True,
        ).order_by('display_order')
 
    @classmethod
    def get_by_code(cls, code):
        return cls.objects.filter(code=code.upper(), is_active=True).first()
 
    # =========================================================================
    # META
    # =========================================================================
 
    class Meta:
        ordering = ['display_order', 'name']
        indexes = [
            models.Index(fields=['method_type', 'is_active']),
            models.Index(fields=['is_active', 'display_order']),
            models.Index(fields=['code']),
            models.Index(fields=['is_default']),
        ]
        verbose_name        = "Payment Method"
        verbose_name_plural = "Payment Methods"
 
    def __str__(self):
        return f"{self.name} ({self.get_method_type_display()})"
    


# =============================================================================
# TAX RATE MODEL
# =============================================================================

class TaxRate(BaseModel):
    """Tax rate configuration for school fees"""

    TAX_TYPE_CHOICES = [
        ('WHT_INTEREST',  'Withholding Tax on Interest'),
        ('WHT_DIVIDEND',  'Withholding Tax on Dividend'),
        ('VAT',           'Value Added Tax'),
        ('LOCAL_SERVICE', 'Local Service Tax'),
        ('EDUCATION_TAX', 'Education Tax'),
        ('OTHER',         'Other Tax'),
    ]

    name            = models.CharField("Tax Name", max_length=100)
    tax_type        = models.CharField("Tax Type", max_length=20, choices=TAX_TYPE_CHOICES, db_index=True)
    rate            = models.DecimalField("Tax Rate (%)", max_digits=5, decimal_places=2, validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))])
    effective_from  = models.DateField("Effective From", db_index=True)
    effective_to    = models.DateField("Effective To", null=True, blank=True, db_index=True)
    is_active       = models.BooleanField("Is Active", default=True, db_index=True)
    applies_to_fees     = models.BooleanField("Applies to School Fees", default=True)
    applies_to_services = models.BooleanField("Applies to Services",    default=False)
    description         = models.TextField("Description", blank=True)
    legal_reference     = models.CharField("Legal Reference", max_length=255, blank=True)

    class Meta:
        ordering = ['-effective_from', 'tax_type']
        indexes = [
            models.Index(fields=['tax_type', 'effective_from']),
            models.Index(fields=['is_active', 'effective_from']),
        ]
        verbose_name        = "Tax Rate"
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
            effective_from__lte=as_of_date,
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
        if check_date is None:
            check_date = timezone.now().date()
        return self.is_valid_on_date(check_date)

    def get_status_display_class(self):
        if not self.is_active:
            return 'status-inactive'
        elif self.is_effective():
            return 'status-effective'
        return 'status-scheduled'


# =============================================================================
# UNITS OF MEASURE
# =============================================================================

class UnitOfMeasure(BaseModel):
    """Enhanced model for different units of measurement used by the school"""

    UOM_TYPE_CHOICES = [
        ('LENGTH',   'Length'),
        ('WEIGHT',   'Weight'),
        ('VOLUME',   'Volume'),
        ('AREA',     'Area'),
        ('QUANTITY', 'Quantity'),
        ('TIME',     'Time'),
        ('OTHER',    'Other'),
    ]

    name         = models.CharField("Name", max_length=50)
    abbreviation = models.CharField("Abbreviation", max_length=10)
    symbol       = models.CharField("Symbol", max_length=10, blank=True, null=True)
    description  = models.TextField("Description", blank=True, null=True)
    uom_type     = models.CharField("UOM Type", max_length=20, choices=UOM_TYPE_CHOICES)

    base_unit = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='derived_units',
        verbose_name="Base Unit",
        help_text="The base unit this unit is derived from",
    )
    conversion_factor = models.DecimalField(
        "Conversion Factor",
        max_digits=16,
        decimal_places=6,
        default=1.0,
        validators=[MinValueValidator(Decimal('0.000001'))],
        help_text="Multiply by this factor to convert to the base unit",
    )

    is_active = models.BooleanField("Is Active", default=True)

    def clean(self):
        super().clean()
        errors = {}
        if self.base_unit == self:
            errors['base_unit'] = 'Unit cannot be its own base unit'
        if self.conversion_factor <= 0:
            errors['conversion_factor'] = 'Conversion factor must be positive'
        if errors:
            raise ValidationError(errors)

    # -------------------------------------------------------------------------
    # CONVERSION METHODS
    # -------------------------------------------------------------------------

    def get_conversion_example(self, value=10):
        if not self.base_unit or not self.conversion_factor:
            return None
        converted_value = float(self.conversion_factor) * value
        return {
            'original_value':  value,
            'original_unit':   self.abbreviation,
            'converted_value': converted_value,
            'converted_unit':  self.base_unit.abbreviation,
            'formatted': (
                f"{value} {self.abbreviation} = "
                f"{converted_value:,.6f} {self.base_unit.abbreviation}"
            ).rstrip('0').rstrip('.'),
        }

    def get_conversion_examples(self):
        if not self.base_unit:
            return []
        return [
            ex for ex in (
                self.get_conversion_example(v) for v in [0.5, 1, 5, 10, 100]
            ) if ex
        ]

    def convert_to_base(self, value):
        if not self.base_unit:
            return value
        return float(value) * float(self.conversion_factor)

    def convert_from_base(self, value):
        if not self.base_unit:
            return value
        return float(value) / float(self.conversion_factor)

    def convert_to_unit(self, value, target_unit):
        if not isinstance(target_unit, UnitOfMeasure):
            return None
        if self.uom_type != target_unit.uom_type:
            return None
        return target_unit.convert_from_base(self.convert_to_base(value))

    # -------------------------------------------------------------------------
    # DISPLAY METHODS
    # -------------------------------------------------------------------------

    def get_quick_conversion_text(self, value=10):
        if not self.base_unit:
            return f"Base unit for {self.get_uom_type_display().lower()}"
        converted = float(self.conversion_factor) * value
        formatted = f"{converted:,.6f}".rstrip('0').rstrip('.')
        return f"{value} {self.abbreviation} = {formatted} {self.base_unit.abbreviation}"

    def format_conversion_factor(self, decimal_places=6):
        if not self.conversion_factor:
            return "1.0"
        return f"{float(self.conversion_factor):.{decimal_places}f}".rstrip('0').rstrip('.')

    def get_display_name(self):
        if self.symbol:
            return f"{self.name} ({self.abbreviation}, {self.symbol})"
        return f"{self.name} ({self.abbreviation})"

    def get_short_display(self):
        return f"{self.abbreviation}" + (f" ({self.symbol})" if self.symbol else "")

    # -------------------------------------------------------------------------
    # HIERARCHY METHODS
    # -------------------------------------------------------------------------

    def get_derived_units_count(self):
        return self.derived_units.filter(is_active=True).count()

    def get_all_derived_units(self):
        return self.derived_units.filter(is_active=True).order_by('name')

    def is_base_unit(self):
        return self.base_unit is None

    def is_derived_unit(self):
        return self.base_unit is not None

    def get_unit_hierarchy(self):
        if self.is_base_unit():
            return [self]
        hierarchy  = []
        current    = self
        seen       = set()
        while current and current.id not in seen:
            hierarchy.append(current)
            seen.add(current.id)
            current = current.base_unit
            if len(hierarchy) > 10:
                break
        return hierarchy

    def get_root_base_unit(self):
        hierarchy = self.get_unit_hierarchy()
        return hierarchy[-1] if hierarchy else self

    def get_conversion_chain_display(self):
        hierarchy = self.get_unit_hierarchy()
        if len(hierarchy) == 1:
            return f"Base unit for {self.get_uom_type_display()}"
        chain_parts = []
        for i, unit in enumerate(hierarchy[:-1]):
            next_unit = hierarchy[i + 1]
            chain_parts.append(f"{unit.abbreviation} → {next_unit.abbreviation}")
        return " → ".join(chain_parts)

    # -------------------------------------------------------------------------
    # STATUS AND VALIDATION METHODS
    # -------------------------------------------------------------------------

    def get_status_display_class(self):
        return "status-active" if self.is_active else "status-inactive"

    def get_type_icon_class(self):
        icon_map = {
            'LENGTH':   'fa-ruler',
            'WEIGHT':   'fa-weight',
            'VOLUME':   'fa-flask',
            'AREA':     'fa-square',
            'QUANTITY': 'fa-hashtag',
            'TIME':     'fa-clock',
            'OTHER':    'fa-cube',
        }
        return icon_map.get(self.uom_type, 'fa-cube')

    def get_type_badge_class(self):
        badge_map = {
            'LENGTH':   'badge-primary',
            'WEIGHT':   'badge-success',
            'VOLUME':   'badge-info',
            'AREA':     'badge-warning',
            'QUANTITY': 'badge-secondary',
            'TIME':     'badge-dark',
            'OTHER':    'badge-light',
        }
        return badge_map.get(self.uom_type, 'badge-light')

    def can_be_deleted(self):
        return self.derived_units.count() == 0

    def get_deletion_warnings(self):
        warnings = []
        derived_count = self.derived_units.count()
        if derived_count > 0:
            warnings.append(
                f"Has {derived_count} derived unit{'s' if derived_count != 1 else ''}"
            )
        try:
            from inventory.models import Item
            items_using = Item.objects.filter(unit_of_measure=self).count()
            if items_using > 0:
                warnings.append(
                    f"Used by {items_using} inventory item{'s' if items_using != 1 else ''}"
                )
        except ImportError:
            pass
        try:
            from uniforms.models import UniformItem
            uniforms_using = UniformItem.objects.filter(unit_of_measure=self).count()
            if uniforms_using > 0:
                warnings.append(
                    f"Used by {uniforms_using} uniform item{'s' if uniforms_using != 1 else ''}"
                )
        except ImportError:
            pass
        if not self.is_active:
            warnings.append("Unit is already inactive")
        return warnings

    def can_be_base_unit_for(self, other_unit):
        if not isinstance(other_unit, UnitOfMeasure):
            return False
        if self.uom_type != other_unit.uom_type:
            return False
        if self == other_unit:
            return False
        if other_unit in self.get_unit_hierarchy():
            return False
        return True

    # -------------------------------------------------------------------------
    # UTILITY METHODS
    # -------------------------------------------------------------------------

    def get_similar_units(self):
        return UnitOfMeasure.objects.filter(
            uom_type=self.uom_type, is_active=True,
        ).exclude(pk=self.pk).order_by('name')

    def get_conversion_table(self):
        table = []
        for unit in self.get_similar_units():
            try:
                converted_value = self.convert_to_unit(1, unit)
                if converted_value is not None:
                    table.append({
                        'unit':       unit,
                        'conversion': (
                            f"1 {self.abbreviation} = "
                            f"{converted_value:,.6f} {unit.abbreviation}"
                        ).rstrip('0').rstrip('.'),
                    })
            except Exception:
                pass
        return table

    def validate_conversion_factor(self):
        errors = []
        if self.conversion_factor <= 0:
            errors.append("Conversion factor must be positive")
        if self.conversion_factor == 1 and self.base_unit:
            errors.append("Conversion factor of 1 suggests this should be a base unit")
        return errors

    def get_short_factor(self):
        return self.format_conversion_factor(3)

    def get_usage_stats(self):
        stats = {
            'derived_units':   self.get_derived_units_count(),
            'is_base':         self.is_base_unit(),
            'hierarchy_depth': len(self.get_unit_hierarchy()),
            'can_delete':      self.can_be_deleted(),
        }
        try:
            from inventory.models import Item
            stats['inventory_items'] = Item.objects.filter(unit_of_measure=self).count()
        except ImportError:
            stats['inventory_items'] = 0
        try:
            from uniforms.models import UniformItem
            stats['uniform_items'] = UniformItem.objects.filter(unit_of_measure=self).count()
        except ImportError:
            stats['uniform_items'] = 0
        return stats

    # -------------------------------------------------------------------------
    # CLASS METHODS
    # -------------------------------------------------------------------------

    @classmethod
    def get_active_by_type(cls, uom_type):
        return cls.objects.filter(uom_type=uom_type, is_active=True).order_by('name')

    @classmethod
    def get_base_units(cls):
        return cls.objects.filter(
            base_unit__isnull=True, is_active=True,
        ).order_by('uom_type', 'name')

    @classmethod
    def get_derived_units(cls):
        return cls.objects.filter(
            base_unit__isnull=False, is_active=True,
        ).order_by('uom_type', 'name')

    @classmethod
    def get_by_abbreviation(cls, abbreviation):
        return cls.objects.filter(
            abbreviation__iexact=abbreviation, is_active=True,
        ).first()

    @classmethod
    def create_standard_units(cls):
        standard_units = []

        meter = cls.objects.get_or_create(
            name='Meter',
            defaults={
                'abbreviation': 'm', 'uom_type': 'LENGTH',
                'description': 'Standard unit of length', 'is_active': True,
            }
        )[0]
        standard_units.append(meter)

        cls.objects.get_or_create(
            name='Centimeter',
            defaults={
                'abbreviation': 'cm', 'uom_type': 'LENGTH',
                'base_unit': meter, 'conversion_factor': Decimal('0.01'),
                'description': 'One hundredth of a meter', 'is_active': True,
            }
        )
        cls.objects.get_or_create(
            name='Kilometer',
            defaults={
                'abbreviation': 'km', 'uom_type': 'LENGTH',
                'base_unit': meter, 'conversion_factor': Decimal('1000'),
                'description': 'One thousand meters', 'is_active': True,
            }
        )

        kilogram = cls.objects.get_or_create(
            name='Kilogram',
            defaults={
                'abbreviation': 'kg', 'uom_type': 'WEIGHT',
                'description': 'Standard unit of weight', 'is_active': True,
            }
        )[0]
        standard_units.append(kilogram)

        cls.objects.get_or_create(
            name='Gram',
            defaults={
                'abbreviation': 'g', 'uom_type': 'WEIGHT',
                'base_unit': kilogram, 'conversion_factor': Decimal('0.001'),
                'description': 'One thousandth of a kilogram', 'is_active': True,
            }
        )

        liter = cls.objects.get_or_create(
            name='Liter',
            defaults={
                'abbreviation': 'L', 'uom_type': 'VOLUME',
                'description': 'Standard unit of volume', 'is_active': True,
            }
        )[0]
        standard_units.append(liter)

        cls.objects.get_or_create(
            name='Milliliter',
            defaults={
                'abbreviation': 'mL', 'uom_type': 'VOLUME',
                'base_unit': liter, 'conversion_factor': Decimal('0.001'),
                'description': 'One thousandth of a liter', 'is_active': True,
            }
        )

        cls.objects.get_or_create(
            name='Piece',
            defaults={
                'abbreviation': 'pcs', 'uom_type': 'QUANTITY',
                'description': 'Individual items', 'is_active': True,
            }
        )
        cls.objects.get_or_create(
            name='Dozen',
            defaults={
                'abbreviation': 'doz', 'uom_type': 'QUANTITY',
                'description': 'Twelve items', 'is_active': True,
            }
        )
        cls.objects.get_or_create(
            name='Box',
            defaults={
                'abbreviation': 'box', 'uom_type': 'QUANTITY',
                'description': 'Container of items', 'is_active': True,
            }
        )

        logger.info(f"Created/verified {len(standard_units)} standard units of measure")
        return standard_units

    def __str__(self):
        return f"{self.name} ({self.abbreviation})"

    class Meta:
        ordering = ['uom_type', 'name']
        verbose_name        = "Unit of Measure"
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
                name='positive_conversion_factor',
            ),
        ]


# =============================================================================
# EXCHANGE RATE MODEL
# =============================================================================

class ExchangeRate(BaseModel):
    """
    Historical exchange rates for multi-currency transactions.

    PURPOSE
    -------
    This is a SUGGESTION ENGINE, not a ledger.

    - Auto-fetched rates (via UniversalExchangeRateMiddleware) populate this
      table daily when FinancialSettings.auto_update_exchange_rates = True.
    - Manual rates can be entered by finance staff at any time.
    - When a cashier opens a payment form, the view calls get_rate() to
      pre-fill the exchange_rate field. Cashier accepts or overrides.
    - Whatever rate was used is stored permanently on Payment.exchange_rate.
      That field is the legal record — this table is reference only.

    MANUAL entries take priority over auto-fetched entries in get_rate().
    This means the bursar can always override a fetched rate for a specific
    date (e.g. "bank gave us a better rate than the published one today").

    WHAT NEVER CHANGES
    ------------------
    Payment.exchange_rate, FeeInvoice.exchange_rate, UniformSale.exchange_rate
    are frozen at transaction time and must never be recalculated from this
    table after the fact. The ExchangeRate table can be updated, corrected,
    or deleted without affecting historical transactions.
    """

    from_currency = models.CharField(
        "From Currency", max_length=3, db_index=True,
        help_text="ISO 4217 code of the source currency (e.g. USD)",
    )
    to_currency = models.CharField(
        "To Currency", max_length=3, db_index=True,
        help_text="ISO 4217 code of the target currency (e.g. UGX)",
    )
    rate = models.DecimalField(
        "Exchange Rate",
        max_digits=12, decimal_places=6,
        validators=[MinValueValidator(Decimal('0.000001'))],
        help_text="How many units of to_currency equal one unit of from_currency.",
    )
    date = models.DateField(
        "Rate Date", db_index=True,
        help_text="The date this rate applies to.",
    )
    source = models.CharField(
        "Source",
        max_length=50,
        default='MANUAL',
        help_text=(
            "Where this rate came from: "
            "MANUAL / ExchangeRate-API / Fixer.io / OpenExchangeRates / "
            "<source> (inverse) for auto-computed inverse rates."
        ),
    )
    is_active = models.BooleanField(
        "Is Active", default=True, db_index=True,
        help_text="Inactive rates are ignored by get_rate() lookups.",
    )
    notes = models.TextField(
        "Notes", blank=True,
        help_text="Optional note — e.g. 'Bank of Uganda official closing rate'.",
    )

    # -------------------------------------------------------------------------
    # LOOKUP
    # -------------------------------------------------------------------------

    @classmethod
    def get_rate(cls, from_currency, to_currency, on_date=None):
        """
        Get the most recent active rate on or before a given date.

        Resolution order:
          1. MANUAL entries for that date range — highest priority
          2. Any auto-fetched entry — most recent

        Returns:
            Decimal or None if no rate found.
        """
        from core.utils import get_school_today
        on_date = on_date or get_school_today()

        manual = cls.objects.filter(
            from_currency=from_currency,
            to_currency=to_currency,
            date__lte=on_date,
            is_active=True,
            source='MANUAL',
        ).order_by('-date').first()

        if manual:
            return manual.rate

        auto = cls.objects.filter(
            from_currency=from_currency,
            to_currency=to_currency,
            date__lte=on_date,
            is_active=True,
        ).order_by('-date').first()

        return auto.rate if auto else None

    @classmethod
    def get_rate_or_default(cls, from_currency, to_currency, on_date=None):
        """
        Like get_rate() but returns Decimal('1.000000') instead of None.
        Safe for same-currency transactions where rate is irrelevant.
        """
        return cls.get_rate(from_currency, to_currency, on_date) or Decimal('1.000000')

    # -------------------------------------------------------------------------
    # HELPERS
    # -------------------------------------------------------------------------

    def get_inverse_rate(self):
        """Return the inverse rate (to_currency → from_currency)."""
        if self.rate:
            return (Decimal('1') / self.rate).quantize(Decimal('0.000001'))
        return None

    def __str__(self):
        return (
            f"1 {self.from_currency} = {self.rate} {self.to_currency} "
            f"({self.date}) [{self.source}]"
        )

    class Meta:
        verbose_name        = "Exchange Rate"
        verbose_name_plural = "Exchange Rates"
        ordering            = ['-date', 'from_currency']
        unique_together     = ('from_currency', 'to_currency', 'date', 'source')
        indexes = [
            models.Index(fields=['from_currency', 'to_currency', 'date']),
            models.Index(fields=['date', 'is_active']),
            models.Index(fields=['source']),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(rate__gt=0),
                name='exchange_rate_positive',
            ),
        ]