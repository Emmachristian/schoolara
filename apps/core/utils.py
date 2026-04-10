# core/utils.py

"""
Central utilities for School Management System operations.
Prevents code duplication and ensures consistency across all modules.

SCOPE OF THIS MODULE
--------------------
This module provides:
  - School timezone utilities (the single source of truth for all date/time logic)
  - Currency and money formatting
  - Percentage and calculation helpers
  - Fiscal period and year accessors
  - Date range helpers
  - Pagination and filter helpers
  - Numbering and code generation
  - String utilities
  - Timezone debugging helpers (development use only)

NOT in this module (moved to their correct locations):
  - _get_print_school_context() → core/view_helpers.py
    (builds template context dicts — view layer concern)
  - export_to_csv() → core/view_helpers.py
    (returns HttpResponse — view layer concern)
  - validate_amount(), validate_date_range(), validate_email(),
    validate_phone_number() → utils/forms.py
    (all form-level validators; core/forms.py already imports them
     exclusively from utils/forms.py — no callers in this module)
"""

from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.utils import timezone
from zoneinfo import ZoneInfo
from decimal import Decimal, InvalidOperation
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# TIMEZONE UTILITY FUNCTIONS — THE SINGLE SOURCE OF TRUTH
# =============================================================================

def get_school_timezone():
    """
    Get the school's operational timezone.

    This is the CENTRAL TIMEZONE UTILITY for all school operations.
    Use this consistently across the application to ensure all date/time
    calculations use the correct timezone.

    FALLBACK BEHAVIOUR:
    - SchoolConfiguration exists and operational_timezone is valid → uses it
    - operational_timezone is not set or invalid → falls back to Africa/Kampala
    - SchoolConfiguration doesn't exist → falls back to Africa/Kampala

    WHY THIS MATTERS:
    The school's timezone affects every date-based business logic:
    - When invoices are due
    - When fiscal periods start/end
    - When to send reminders
    - What "today" means for transactions
    - When fees become overdue
    - Financial period boundaries
    - Journal entry timestamps

    NOTE ON SCOPE:
    This timezone currently affects the finance layer only.
    AcademicSession date checks in academics/models.py still use
    server time (timezone.now().date()). Update academics/models.py
    to call get_school_today() to extend timezone awareness to the
    academic layer.

    Returns:
        ZoneInfo: School's operational timezone (Africa/Kampala as fallback)

    Example:
        >>> from core.utils import get_school_timezone
        >>> tz  = get_school_timezone()
        >>> now = datetime.now(tz=tz)
        >>> print(f"Current time in school timezone: {now}")
    """
    try:
        from core.models import SchoolConfiguration
        config = SchoolConfiguration.get_cached_instance()

        if config and config.operational_timezone:
            try:
                return ZoneInfo(config.operational_timezone)
            except Exception as tz_error:
                logger.warning(
                    f"Invalid timezone '{config.operational_timezone}' in "
                    f"SchoolConfiguration. Falling back to Africa/Kampala. "
                    f"Error: {tz_error}"
                )
                return ZoneInfo('Africa/Kampala')
        else:
            logger.debug("No operational timezone configured, using Africa/Kampala")
            return ZoneInfo('Africa/Kampala')

    except Exception as e:
        logger.error(
            f"Error getting school timezone, falling back to Africa/Kampala: {e}"
        )
        return ZoneInfo('Africa/Kampala')


def get_school_current_time():
    """
    Get current time in school's operational timezone.

    USE THIS FOR ALL TIMESTAMP OPERATIONS.

    Use when you need the current datetime with timezone awareness:
    - Logging and audit trails
    - Transaction timestamps
    - Record creation/update times
    - Event timestamps
    - Deadline calculations
    - Journal entry timestamps

    IMPORTANT: Respects the school's configured timezone.
    Falls back to Africa/Kampala if no timezone is configured.

    Returns:
        datetime: Current datetime in school's timezone (timezone-aware)

    Example:
        >>> from core.utils import get_school_current_time
        >>> from finance.models import Payment
        >>>
        >>> payment = Payment.objects.create(
        >>>     amount=50000,
        >>>     payment_date=get_school_current_time(),
        >>> )
        >>>
        >>> # 2025-01-15 14:30:45.123456+03:00  (Africa/Kampala)
        >>> print(get_school_current_time())
    """
    return timezone.now().astimezone(get_school_timezone())


def get_school_today():
    """
    Get today's date in school's operational timezone.

    ALWAYS USE THIS instead of:
      - date.today()        — uses system timezone (may be wrong)
      - timezone.now().date() — uses UTC or Django's TIME_ZONE setting

    WHY THIS IS CRITICAL:
    "Today" depends on timezone. Consider a school in Uganda (EAT/UTC+3):
    - At 2025-01-15 01:00 AM EAT the school considers it January 15th.
    - UTC says it is January 14th 22:00 PM (still "yesterday").
    - Using the wrong "today" causes:
        ✘ Fees marked overdue when they are not
        ✘ Fiscal periods starting/ending on wrong dates
        ✘ Reports covering wrong days
        ✘ Reminders sent at wrong times
        ✘ Late fees calculated incorrectly

    USE CASES (always use this):
      ✓ Check if fiscal period is current
      ✓ Check if invoice is overdue
      ✓ Get today's transactions
      ✓ Record a transaction with today's date
      ✓ Check if fee due date has passed
      ✓ Calculate days until a deadline
      ✓ Any date-based business logic in the finance layer

    FALLBACK BEHAVIOUR:
    - School timezone configured → uses it
    - Not configured → uses Africa/Kampala (EAT)

    Returns:
        date: Today's date in school's timezone

    Example:
        >>> from core.utils import get_school_today
        >>> from fees.models import FeeInvoice
        >>>
        >>> today = get_school_today()
        >>> overdue = FeeInvoice.objects.filter(
        >>>     due_date__lt=today,
        >>>     status='PENDING',
        >>> )
        >>>
        >>> # Calculate due date 30 days from today
        >>> from datetime import timedelta
        >>> due_date = get_school_today() + timedelta(days=30)
    """
    return get_school_current_time().date()


def localize_datetime(dt):
    """
    Convert any datetime to school's operational timezone.

    Use this to convert UTC or naive datetimes to the school's timezone
    for display or calculations.

    HANDLES:
    - Naive datetimes (assumes UTC, then converts to school timezone)
    - Aware datetimes (converts from source timezone to school timezone)
    - None (returns None — safe for nullable timestamp fields)

    Args:
        dt: datetime object (naive or aware) or None

    Returns:
        datetime: Timezone-aware datetime in school's operational timezone,
                  or None if dt is None.

    Example:
        >>> from core.utils import localize_datetime
        >>> from django.utils import timezone
        >>>
        >>> utc_time   = timezone.now()          # 2025-01-15 11:30:00+00:00
        >>> local_time = localize_datetime(utc_time) # 2025-01-15 14:30:00+03:00
        >>>
        >>> # Convert naive datetime
        >>> from datetime import datetime
        >>> naive_dt = datetime(2025, 1, 15, 14, 30)
        >>> local_dt = localize_datetime(naive_dt)
        >>> print(local_dt)  # 2025-01-15 14:30:00+03:00
    """
    if dt is None:
        return None

    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt)

    return dt.astimezone(get_school_timezone())


def format_school_datetime(dt, format_string='%Y-%m-%d %H:%M:%S %Z'):
    """
    Format datetime in school's operational timezone.

    Converts datetime to school timezone and formats it according to
    the provided format string. Use for displaying timestamps to users.

    Args:
        dt:            datetime object (naive or aware) or None
        format_string: strftime format string.
                       Default includes timezone abbreviation (%Z).

    Returns:
        str: Formatted datetime string in school timezone,
             or empty string if dt is None.

    Example:
        >>> from core.utils import format_school_datetime
        >>>
        >>> # Default format
        >>> formatted = format_school_datetime(payment.created_at)
        >>> # "2025-01-15 14:30:45 EAT"
        >>>
        >>> # User-friendly format
        >>> formatted = format_school_datetime(
        >>>     invoice.created_at,
        >>>     format_string='%B %d, %Y at %I:%M %p'
        >>> )
        >>> # "January 15, 2025 at 02:30 PM"
        >>>
        >>> # Short date
        >>> formatted = format_school_datetime(
        >>>     transaction.date,
        >>>     format_string='%d/%m/%Y'
        >>> )
        >>> # "15/01/2025"
    """
    if dt is None:
        return ''

    local_dt = localize_datetime(dt)
    return local_dt.strftime(format_string)


def make_timezone_aware(dt, tz=None):
    """
    Make a naive datetime timezone-aware.

    If dt is already timezone-aware it is returned unchanged.
    If dt is None it is returned as None.

    Args:
        dt: datetime object (naive or aware) or None
        tz: Optional ZoneInfo timezone.
            Defaults to school timezone if not provided.

    Returns:
        datetime: Timezone-aware datetime, or None if dt is None.

    Example:
        >>> from datetime import datetime
        >>> from core.utils import make_timezone_aware
        >>>
        >>> naive_dt = datetime(2025, 1, 15, 10, 30)
        >>> aware_dt = make_timezone_aware(naive_dt)
        >>> print(aware_dt)  # 2025-01-15 10:30:00+03:00
    """
    if dt is None:
        return None

    if timezone.is_aware(dt):
        return dt

    if tz is None:
        tz = get_school_timezone()

    return timezone.make_aware(dt, timezone=tz)


def convert_to_utc(dt):
    """
    Convert a datetime to UTC.

    Useful when you need to store or compare datetimes in UTC after
    working with school-timezone values.

    Args:
        dt: datetime object (naive or aware) or None

    Returns:
        datetime: Timezone-aware datetime in UTC, or None if dt is None.

    Example:
        >>> from core.utils import convert_to_utc, get_school_current_time
        >>>
        >>> school_time = get_school_current_time()  # 2025-01-15 14:30:00+03:00
        >>> utc_time    = convert_to_utc(school_time)  # 2025-01-15 11:30:00+00:00
    """
    if dt is None:
        return None

    if timezone.is_naive(dt):
        dt = make_timezone_aware(dt)

    return dt.astimezone(ZoneInfo('UTC'))


# =============================================================================
# CURRENCY & MONEY FORMATTING
# =============================================================================

def get_school_currency():
    """
    Get the school's base currency code from FinancialSettings.

    Safe method that handles circular imports and missing configuration.

    Returns:
        str: ISO 4217 currency code (defaults to 'UGX')

    Example:
        >>> from core.utils import get_school_currency
        >>> currency = get_school_currency()
        >>> print(f"School uses: {currency}")  # "UGX"
    """
    try:
        from core.models import FinancialSettings
        settings = FinancialSettings.get_instance()
        return settings.school_currency if settings else 'UGX'
    except Exception as e:
        logger.warning(f"Could not fetch currency from settings: {e}")
        return 'UGX'


def format_money(amount, include_symbol=True):
    """
    Format a money amount according to school financial settings.

    Delegates to FinancialSettings.format_currency() which applies
    the school's configured decimal places, thousands separator,
    and currency symbol position.

    Args:
        amount:         Decimal or numeric value to format
        include_symbol: Whether to include the currency symbol

    Returns:
        str: Formatted money string

    Example:
        >>> from core.utils import format_money
        >>> print(format_money(1500000))         # "UGX 1,500,000.00"
        >>> print(format_money(1500000, False))  # "1,500,000.00"
    """
    try:
        from core.models import FinancialSettings
        settings = FinancialSettings.get_instance()
        if settings:
            return settings.format_currency(amount, include_symbol)
    except Exception as e:
        logger.warning(f"Could not format using settings: {e}")

    # Fallback formatting
    try:
        amount_decimal = Decimal(str(amount or 0))
        formatted      = f"{amount_decimal:,.2f}"
        return f"UGX {formatted}" if include_symbol else formatted
    except (ValueError, TypeError, InvalidOperation):
        return "UGX 0.00" if include_symbol else "0.00"


def parse_amount(amount_str):
    """
    Parse an amount string to Decimal, removing currency symbols and separators.

    Args:
        amount_str: String representation of amount (e.g., "UGX 1,500,000.00")

    Returns:
        Decimal: Parsed amount or Decimal('0') if parsing fails.

    Example:
        >>> from core.utils import parse_amount
        >>> amount = parse_amount("UGX 1,500,000.00")
        >>> print(amount)  # Decimal('1500000.00')
    """
    if not amount_str:
        return Decimal('0')

    try:
        clean_str = str(amount_str).replace('UGX', '').replace(',', '').strip()
        return Decimal(clean_str)
    except (ValueError, TypeError, InvalidOperation):
        logger.warning(f"Could not parse amount: {amount_str}")
        return Decimal('0')


# =============================================================================
# PERCENTAGE & CALCULATION UTILITIES
# =============================================================================

def calculate_percentage(part, whole, decimal_places=2):
    """
    Calculate a percentage with safe division.

    Returns Decimal('0.00') when whole is zero rather than raising
    ZeroDivisionError.

    Args:
        part:           Part value (numerator)
        whole:          Whole value (denominator)
        decimal_places: Number of decimal places to round to (default: 2)

    Returns:
        Decimal: Percentage value (0.00 if whole is zero)

    Example:
        >>> from core.utils import calculate_percentage
        >>> print(calculate_percentage(750000, 1000000))  # Decimal('75.00')
        >>> print(calculate_percentage(100, 0))           # Decimal('0.00')
    """
    try:
        part_decimal  = Decimal(str(part  or 0))
        whole_decimal = Decimal(str(whole or 0))

        if whole_decimal == 0:
            return Decimal('0.00')

        percentage = (part_decimal / whole_decimal) * 100
        return round(percentage, decimal_places)
    except (ValueError, TypeError, InvalidOperation, ZeroDivisionError):
        return Decimal('0.00')


def calculate_amount_from_percentage(base_amount, percentage):
    """
    Calculate an amount as a percentage of a base amount.

    Args:
        base_amount: Base amount
        percentage:  Percentage to apply

    Returns:
        Decimal: Calculated amount rounded to 2 decimal places.

    Example:
        >>> from core.utils import calculate_amount_from_percentage
        >>> print(calculate_amount_from_percentage(1000000, 5))  # Decimal('50000.00')
    """
    try:
        base = Decimal(str(base_amount or 0))
        pct  = Decimal(str(percentage  or 0))
        return round((base * pct) / 100, 2)
    except (ValueError, TypeError, InvalidOperation):
        return Decimal('0.00')


# =============================================================================
# FISCAL PERIOD & YEAR ACCESSORS
# =============================================================================

def get_active_fiscal_period():
    """
    Get the currently active fiscal period for financial transactions.

    Returns:
        FiscalPeriod or None

    Example:
        >>> from core.utils import get_active_fiscal_period
        >>> period = get_active_fiscal_period()
        >>> if period:
        >>>     print(f"Current fiscal period: {period.name}")
    """
    try:
        from core.models import FiscalPeriod
        return FiscalPeriod.get_current_fiscal_period()
    except Exception as e:
        logger.error(f"Error fetching active fiscal period: {e}")
        return None


def get_active_fiscal_year():
    """
    Get the currently active fiscal/academic year.

    Returns:
        FiscalYear or None

    Example:
        >>> from core.utils import get_active_fiscal_year
        >>> year = get_active_fiscal_year()
        >>> if year:
        >>>     print(f"Current academic year: {year.name}")
    """
    try:
        from core.models import FiscalYear
        return FiscalYear.get_active_fiscal_year()
    except Exception as e:
        logger.error(f"Error fetching active fiscal year: {e}")
        return None


def get_active_academic_session():
    """
    Get the currently active academic session for teaching/learning.

    Returns:
        AcademicSession or None

    Example:
        >>> from core.utils import get_active_academic_session
        >>> session = get_active_academic_session()
        >>> if session:
        >>>     print(f"Current term: {session.name}")
        >>>     print(f"Dates: {session.start_date} to {session.end_date}")
    """
    try:
        from academics.models import AcademicSession
        return AcademicSession.get_current_session()
    except Exception as e:
        logger.debug(f"Could not fetch active academic session: {e}")
        return None


# =============================================================================
# DATE RANGE UTILITIES
# =============================================================================

def get_date_range_for_period(period_type='month', reference_date=None):
    """
    Get start and end dates for a named period type.

    All returned dates use school timezone via get_school_today().

    Args:
        period_type:    'today' | 'week' | 'month' | 'quarter' | 'year'
        reference_date: Optional date to use as reference.
                        Defaults to school today if not provided.

    Returns:
        tuple[date, date]: (start_date, end_date)

    Example:
        >>> from core.utils import get_date_range_for_period
        >>>
        >>> # This month's range
        >>> start, end = get_date_range_for_period('month')
        >>> payments = Payment.objects.filter(
        >>>     payment_date__gte=start,
        >>>     payment_date__lte=end,
        >>> )
        >>>
        >>> # This week
        >>> start, end = get_date_range_for_period('week')
        >>>
        >>> # Today only
        >>> start, end = get_date_range_for_period('today')
    """
    from datetime import timedelta
    from calendar import monthrange

    if reference_date is None:
        reference_date = get_school_today()

    if period_type == 'today':
        return reference_date, reference_date

    elif period_type == 'week':
        # Monday to Sunday
        start = reference_date - timedelta(days=reference_date.weekday())
        end   = start + timedelta(days=6)
        return start, end

    elif period_type == 'month':
        start    = reference_date.replace(day=1)
        last_day = monthrange(reference_date.year, reference_date.month)[1]
        end      = reference_date.replace(day=last_day)
        return start, end

    elif period_type == 'quarter':
        quarter     = (reference_date.month - 1) // 3 + 1
        start_month = (quarter - 1) * 3 + 1
        start       = reference_date.replace(month=start_month, day=1)
        end_month   = start_month + 2
        last_day    = monthrange(reference_date.year, end_month)[1]
        end         = reference_date.replace(month=end_month, day=last_day)
        return start, end

    elif period_type == 'year':
        start = reference_date.replace(month=1,  day=1)
        end   = reference_date.replace(month=12, day=31)
        return start, end

    else:
        # Default to today for unrecognised period types
        logger.warning(
            f"Unknown period_type '{period_type}' passed to "
            f"get_date_range_for_period(). Defaulting to today."
        )
        return reference_date, reference_date


# =============================================================================
# PAGINATION & FILTERING
# =============================================================================

def paginate_queryset(request, queryset, per_page=20):
    """
    Paginate a queryset with sensible defaults and error handling.

    Reads the 'page' parameter from request.GET. Falls back to page 1
    if the value is not an integer and to the last page if it is out
    of range.

    Args:
        request:  HTTP request object
        queryset: Django queryset to paginate
        per_page: Items per page (default: 20)

    Returns:
        tuple[Page, Paginator]: (page_obj, paginator)

    Example:
        >>> from core.utils import paginate_queryset
        >>> from fees.models import FeeInvoice
        >>>
        >>> def invoice_list(request):
        >>>     invoices = FeeInvoice.objects.all()
        >>>     page_obj, paginator = paginate_queryset(request, invoices, per_page=50)
        >>>     return render(request, 'invoices.html', {
        >>>         'page_obj':  page_obj,
        >>>         'paginator': paginator,
        >>>     })
    """
    paginator = Paginator(queryset, per_page)
    page      = request.GET.get('page', 1)

    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    return page_obj, paginator


def parse_filters(request, filter_keys):
    """
    Extract filter values from request.GET with None normalisation.

    Empty strings are normalised to None so callers can do simple
    truthiness checks.

    Args:
        request:     HTTP request object
        filter_keys: List of GET parameter names to extract

    Returns:
        dict[str, str | None]: {key: value_or_None}

    Example:
        >>> from core.utils import parse_filters
        >>>
        >>> def invoice_list(request):
        >>>     filters = parse_filters(request, [
        >>>         'status', 'student', 'academic_session',
        >>>         'date_from', 'date_to',
        >>>     ])
        >>>
        >>>     invoices = FeeInvoice.objects.all()
        >>>     if filters['status']:
        >>>         invoices = invoices.filter(status=filters['status'])
        >>>     if filters['student']:
        >>>         invoices = invoices.filter(student_id=filters['student'])
    """
    filters = {}
    for key in filter_keys:
        value        = request.GET.get(key, '').strip()
        filters[key] = value if value else None
    return filters


# =============================================================================
# NUMBERING & CODE GENERATION
# =============================================================================

def generate_next_number(prefix, last_number, include_year=True, year=None):
    """
    Generate the next sequential number with prefix and optional year.

    Parses the sequence component from last_number by splitting on '-'
    and taking the last segment. If last_number is None or unparseable
    the sequence starts at 1.

    Args:
        prefix:       Number prefix (e.g., 'INV', 'PMT', 'RCPT')
        last_number:  Last used number string (e.g., 'INV-2025-00042')
                      or None for the first number in a sequence.
        include_year: Whether to include the year in the format (default: True)
        year:         Optional year integer. Defaults to the active fiscal
                      year start year, then falls back to calendar year.

    Returns:
        str: Next number in sequence

    Example:
        >>> from core.utils import generate_next_number
        >>>
        >>> # With year
        >>> next_num = generate_next_number('INV', 'INV-2025-00042')
        >>> print(next_num)  # 'INV-2025-00043'
        >>>
        >>> # Without year
        >>> next_num = generate_next_number('PMT', 'PMT-00156', include_year=False)
        >>> print(next_num)  # 'PMT-00157'
        >>>
        >>> # First number in a new sequence
        >>> next_num = generate_next_number('RCPT', None)
        >>> print(next_num)  # 'RCPT-2025-00001'
    """
    from datetime import date as _date

    if year is None:
        fiscal_year = get_active_fiscal_year()
        if fiscal_year:
            year = fiscal_year.start_date.year
        else:
            year = get_school_today().year

    if last_number:
        try:
            parts           = last_number.split('-')
            sequence_part   = parts[-1]
            current_sequence= int(sequence_part)
            next_sequence   = current_sequence + 1
        except (ValueError, IndexError):
            next_sequence = 1
    else:
        next_sequence = 1

    if include_year:
        return f"{prefix}-{year}-{next_sequence:05d}"
    else:
        return f"{prefix}-{next_sequence:05d}"


# =============================================================================
# STRING UTILITIES
# =============================================================================

def truncate_string(text, max_length=50, suffix='...'):
    """
    Truncate a string to a maximum length with a suffix.

    If the text is shorter than or equal to max_length it is returned
    unchanged. The suffix is included in the max_length count.

    Args:
        text:       String to truncate
        max_length: Maximum total length including suffix (default: 50)
        suffix:     Suffix to append when truncating (default: '...')

    Returns:
        str: Truncated string, or empty string if text is falsy.

    Example:
        >>> from core.utils import truncate_string
        >>> text  = "This is a very long description that needs truncating"
        >>> short = truncate_string(text, max_length=30)
        >>> print(short)  # "This is a very long descr..."
    """
    if not text:
        return ''

    if len(text) <= max_length:
        return text

    return text[:max_length - len(suffix)] + suffix


def slugify_filename(filename):
    """
    Create a safe, lowercase filename slug preserving the file extension.

    Applies Django's slugify to the name part and lowercases the extension.

    Args:
        filename: Original filename (e.g., "Student Report (Term 1).pdf")

    Returns:
        str: Safe filename (e.g., "student-report-term-1.pdf")

    Example:
        >>> from core.utils import slugify_filename
        >>> safe = slugify_filename("Student Report (Term 1).pdf")
        >>> print(safe)  # "student-report-term-1.pdf"
    """
    from django.utils.text import slugify
    import os

    name, ext = os.path.splitext(filename)
    safe_name = slugify(name)
    return f"{safe_name}{ext.lower()}"


# =============================================================================
# TIMEZONE DEBUGGING UTILITIES (development / troubleshooting only)
# =============================================================================

def debug_timezone_info():
    """
    Get comprehensive timezone information for debugging.

    FOR DEVELOPMENT AND TROUBLESHOOTING ONLY.
    Do not call this in production request handlers.

    Returns:
        dict: Timezone debugging information including Django settings,
              school configuration, current times, and offset.

    Example:
        >>> from core.utils import debug_timezone_info
        >>> import json
        >>>
        >>> # Django shell
        >>> info = debug_timezone_info()
        >>> print(json.dumps(info, indent=2, default=str))
        >>>
        >>> # Debug view
        >>> from django.http import JsonResponse
        >>> def debug_view(request):
        >>>     return JsonResponse(debug_timezone_info(), default=str)
    """
    from django.conf import settings

    try:
        from core.models import SchoolConfiguration
        config         = SchoolConfiguration.get_cached_instance()
        configured_tz  = config.operational_timezone if config else None
    except Exception as e:
        configured_tz  = f"Error: {e}"

    current_time = get_school_current_time()

    return {
        'django_timezone_setting':    settings.TIME_ZONE,
        'django_use_tz':              settings.USE_TZ,
        'school_configured_timezone': configured_tz,
        'effective_school_timezone':  str(get_school_timezone()),
        'current_utc_time':           timezone.now().isoformat(),
        'current_school_time':        current_time.isoformat(),
        'current_school_date':        get_school_today().isoformat(),
        'timezone_offset':            current_time.strftime('%z'),
        'timezone_name':              current_time.strftime('%Z'),
        'available_timezones_sample': [
            'Africa/Kampala',       'Africa/Nairobi',
            'Africa/Dar_es_Salaam', 'Africa/Lagos',
            'Africa/Johannesburg',  'Africa/Kigali',
            'Africa/Juba',          'Europe/London',
            'America/New_York',     'Asia/Kolkata',
        ],
    }