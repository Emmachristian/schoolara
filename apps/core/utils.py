# core/utils.py

"""
Central utilities for School Management System operations
Prevents code duplication and ensures consistency across all modules
"""
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import HttpResponse
from django.utils import timezone
from zoneinfo import ZoneInfo
from decimal import Decimal, InvalidOperation
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# CURRENCY & MONEY FORMATTING
# =============================================================================

def get_school_currency():
    """
    Get base currency from school financial settings.
    Safe method that handles circular imports and missing config.
    
    Returns:
        str: Currency code (defaults to 'UGX')
        
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
    Format money amount according to school financial settings.
    
    Args:
        amount: Decimal or numeric value to format
        include_symbol: Whether to include currency symbol
        
    Returns:
        str: Formatted money string
        
    Example:
        >>> from core.utils import format_money
        >>> print(format_money(1500000))  # "UGX 1,500,000.00"
        >>> print(format_money(1500000, include_symbol=False))  # "1,500,000.00"
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
        formatted = f"{amount_decimal:,.2f}"
        return f"UGX {formatted}" if include_symbol else formatted
    except (ValueError, TypeError, InvalidOperation):
        return "UGX 0.00" if include_symbol else "0.00"


def validate_amount(amount, min_amount=None, max_amount=None):
    """
    Validate that an amount is appropriate for school operations.
    
    Args:
        amount: Amount to validate
        min_amount: Optional minimum amount (uses FinancialSettings default if None)
        max_amount: Optional maximum amount
        
    Returns:
        tuple: (is_valid, error_message)
        
    Example:
        >>> from core.utils import validate_amount
        >>> is_valid, error = validate_amount(5000)
        >>> if not is_valid:
        >>>     print(error)
    """
    try:
        amount_decimal = Decimal(str(amount))
        
        if amount_decimal < 0:
            return False, "Amount cannot be negative"
        
        # Get minimum from settings if not provided
        if min_amount is None:
            try:
                from core.models import FinancialSettings
                settings = FinancialSettings.get_instance()
                if settings:
                    min_amount = settings.minimum_payment_amount
            except Exception:
                min_amount = Decimal('1000.00')  # Fallback
        
        if min_amount and amount_decimal < Decimal(str(min_amount)):
            return False, f"Amount must be at least {format_money(min_amount)}"
        
        if max_amount and amount_decimal > Decimal(str(max_amount)):
            return False, f"Amount cannot exceed {format_money(max_amount)}"
        
        return True, None
        
    except (ValueError, TypeError, InvalidOperation):
        return False, "Invalid amount format"


def parse_amount(amount_str):
    """
    Parse amount string to Decimal, removing currency symbols and separators.
    
    Args:
        amount_str: String representation of amount (e.g., "UGX 1,500,000.00")
        
    Returns:
        Decimal: Parsed amount or Decimal('0')
        
    Example:
        >>> from core.utils import parse_amount
        >>> amount = parse_amount("UGX 1,500,000.00")
        >>> print(amount)  # Decimal('1500000.00')
    """
    if not amount_str:
        return Decimal('0')
    
    try:
        # Remove currency symbols and separators
        clean_str = str(amount_str)
        clean_str = clean_str.replace('UGX', '').replace(',', '').strip()
        return Decimal(clean_str)
    except (ValueError, TypeError, InvalidOperation):
        logger.warning(f"Could not parse amount: {amount_str}")
        return Decimal('0')


# =============================================================================
# PERCENTAGE & CALCULATION UTILITIES
# =============================================================================

def calculate_percentage(part, whole, decimal_places=2):
    """
    Calculate percentage with safe division.
    
    Args:
        part: Part value (numerator)
        whole: Whole value (denominator)
        decimal_places: Number of decimal places (default: 2)
        
    Returns:
        Decimal: Percentage value (0 if whole is 0)
        
    Example:
        >>> from core.utils import calculate_percentage
        >>> print(calculate_percentage(750000, 1000000))  # Decimal('75.00')
        >>> print(calculate_percentage(100, 0))  # Decimal('0.00')
    """
    try:
        part_decimal = Decimal(str(part or 0))
        whole_decimal = Decimal(str(whole or 0))
        
        if whole_decimal == 0:
            return Decimal('0.00')
        
        percentage = (part_decimal / whole_decimal) * 100
        return round(percentage, decimal_places)
    except (ValueError, TypeError, InvalidOperation, ZeroDivisionError):
        return Decimal('0.00')


def calculate_amount_from_percentage(base_amount, percentage):
    """
    Calculate amount from percentage of base amount.
    
    Args:
        base_amount: Base amount
        percentage: Percentage to calculate
        
    Returns:
        Decimal: Calculated amount
        
    Example:
        >>> from core.utils import calculate_amount_from_percentage
        >>> print(calculate_amount_from_percentage(1000000, 5))  # Decimal('50000.00')
    """
    try:
        base = Decimal(str(base_amount or 0))
        pct = Decimal(str(percentage or 0))
        
        amount = (base * pct) / 100
        return round(amount, 2)
    except (ValueError, TypeError, InvalidOperation):
        return Decimal('0.00')


# =============================================================================
# FISCAL PERIOD & YEAR UTILITIES
# =============================================================================

def get_active_fiscal_period():
    """
    Get the currently active fiscal period for financial transactions.
    
    Returns:
        FiscalPeriod or None: Active fiscal period
        
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
        FiscalYear or None: Active fiscal year
        
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
        AcademicSession or None: Active academic session
        
    Example:
        >>> from core.utils import get_active_academic_session
        >>> session = get_active_academic_session()
        >>> if session:
        >>>     print(f"Current term: {session.name}")
        >>>     print(f"Session dates: {session.start_date} to {session.end_date}")
    """
    try:
        from academics.models import AcademicSession
        return AcademicSession.get_current_session()
    except Exception as e:
        logger.debug(f"Could not fetch active academic session: {e}")
        return None


# =============================================================================
# TIMEZONE UTILITY FUNCTIONS - THE SINGLE SOURCE OF TRUTH ⭐
# =============================================================================

def get_school_timezone():
    """
    Get the school's operational timezone.
    
    This is the **CENTRAL TIMEZONE UTILITY** for all school operations.
    Use this consistently across the application to ensure all date/time
    calculations use the correct timezone.
    
    **FALLBACK BEHAVIOR:**
    - If SchoolConfiguration exists and operational_timezone is set → Uses that timezone
    - If operational_timezone is not set or invalid → Falls back to Africa/Kampala
    - If SchoolConfiguration doesn't exist → Falls back to Africa/Kampala
    
    **WHY THIS MATTERS:**
    The school's timezone affects EVERY date-based business logic:
    - When invoices are due
    - When terms start/end
    - When to send reminders
    - What "today" means for transactions
    - When fees become overdue
    - Financial period boundaries
    
    Returns:
        ZoneInfo: School's operational timezone (or Africa/Kampala as fallback)
    
    Example:
        >>> from core.utils import get_school_timezone
        >>> tz = get_school_timezone()
        >>> now = datetime.now(tz=tz)
        >>> print(f"Current time in school timezone: {now}")
    """
    try:
        from core.models import SchoolConfiguration
        config = SchoolConfiguration.get_cached_instance()
        
        if config and config.operational_timezone:
            try:
                # Try to get configured timezone
                return ZoneInfo(config.operational_timezone)
            except Exception as tz_error:
                logger.warning(
                    f"Invalid timezone '{config.operational_timezone}' in SchoolConfiguration. "
                    f"Falling back to Africa/Kampala. Error: {tz_error}"
                )
                return ZoneInfo('Africa/Kampala')
        else:
            # No timezone configured, use default for East Africa
            logger.debug("No operational timezone configured, using Africa/Kampala")
            return ZoneInfo('Africa/Kampala')
            
    except Exception as e:
        logger.error(f"Error getting school timezone, falling back to Africa/Kampala: {e}")
        return ZoneInfo('Africa/Kampala')


def get_school_current_time():
    """
    Get current time in school's operational timezone.
    
    **USE THIS FOR ALL TIMESTAMP OPERATIONS!**
    
    Use this when you need the current timestamp with timezone awareness.
    Perfect for:
    - Logging and audit trails
    - Transaction timestamps
    - Record creation/update times
    - Event timestamps
    - Deadline calculations
    
    **IMPORTANT:** This respects the school's configured timezone.
    If no timezone is configured, falls back to Africa/Kampala (EAT).
    
    Returns:
        datetime: Current datetime in school's timezone (timezone-aware)
    
    Example:
        >>> from core.utils import get_school_current_time
        >>> from finance.models import Payment
        >>> 
        >>> # Record payment with correct timestamp
        >>> payment = Payment.objects.create(
        >>>     amount=50000,
        >>>     payment_date=get_school_current_time(),
        >>>     # ... other fields
        >>> )
        >>> 
        >>> # Log entry with correct time
        >>> logger.info(f"Payment received at {get_school_current_time()}")
        
    Example Output:
        >>> print(get_school_current_time())
        >>> # 2025-01-15 14:30:45.123456+03:00  (If school is in Africa/Kampala)
        >>> # 2025-01-15 12:30:45.123456+01:00  (If school is in Africa/Lagos)
    """
    return timezone.now().astimezone(get_school_timezone())


def get_school_today():
    """
    Get today's date in school's operational timezone.
    
    **🔥 CRITICAL FOR ALL DATE-BASED BUSINESS LOGIC! 🔥**
    
    **ALWAYS USE THIS** instead of:
    - ❌ `date.today()` - uses system timezone (could be wrong!)
    - ❌ `timezone.now().date()` - uses UTC or Django's TIME_ZONE
    
    **WHY THIS IS CRITICAL:**
    
    "Today" depends on timezone! Consider:
    - In Uganda (EAT/UTC+3): 2025-01-15 at 02:00 AM
    - In New York (EST/UTC-5): 2025-01-14 at 18:00 PM (still yesterday!)
    - In UTC: 2025-01-14 at 23:00 PM (still yesterday!)
    
    If you use the wrong "today", you could:
    - ✘ Mark fees as overdue when they're not
    - ✘ Start/end terms on wrong dates
    - ✘ Generate reports for wrong days
    - ✘ Send reminders at wrong times
    - ✘ Calculate late fees incorrectly
    
    **USE CASES:**
    - ✓ Check if academic session is active today
    - ✓ Check if invoice is overdue
    - ✓ Get today's transactions
    - ✓ Record transaction with today's date
    - ✓ Check if fee due date has passed
    - ✓ Check if fiscal period is current
    - ✓ Calculate days until deadline
    - ✓ Any date-based business logic!
    
    **FALLBACK BEHAVIOR:**
    - If school timezone is configured → Uses that timezone
    - If not configured → Uses Africa/Kampala (EAT)
    
    Returns:
        date: Today's date in school's timezone
    
    Example:
        >>> from core.utils import get_school_today
        >>> from finance.models import Invoice
        >>> 
        >>> # Check if invoice is overdue
        >>> today = get_school_today()
        >>> if invoice.due_date < today:
        >>>     days_overdue = (today - invoice.due_date).days
        >>>     print(f"Invoice is {days_overdue} days overdue")
        >>> 
        >>> # Check if academic session is active
        >>> today = get_school_today()
        >>> if session.start_date <= today <= session.end_date:
        >>>     print("Session is active today")
        >>> 
        >>> # Get today's payments
        >>> today = get_school_today()
        >>> payments = Payment.objects.filter(payment_date=today)
        >>> 
        >>> # Create transaction with today's date
        >>> today = get_school_today()
        >>> transaction = Transaction.objects.create(
        >>>     date=today,  # ✓ Correct date in school timezone
        >>>     amount=1000
        >>> )
        >>> 
        >>> # Calculate due date (30 days from today)
        >>> today = get_school_today()
        >>> due_date = today + timedelta(days=30)
    """
    return get_school_current_time().date()


def localize_datetime(dt):
    """
    Convert any datetime to school's operational timezone.
    
    Use this to convert UTC or naive datetimes to the school's timezone
    for display or calculations.
    
    **HANDLES:**
    - Naive datetimes (assumes UTC, then converts to school timezone)
    - Aware datetimes (converts from source timezone to school timezone)
    
    Args:
        dt: datetime object (naive or aware)
        
    Returns:
        datetime: Timezone-aware datetime in school's operational timezone
    
    Example:
        >>> from core.utils import localize_datetime
        >>> from django.utils import timezone
        >>> 
        >>> # Convert UTC time to school timezone for display
        >>> utc_time = timezone.now()  # 2025-01-15 11:30:00+00:00
        >>> local_time = localize_datetime(utc_time)  # 2025-01-15 14:30:00+03:00
        >>> 
        >>> # Use in template context
        >>> context = {
        >>>     'payment_time': localize_datetime(payment.created_at),
        >>>     'invoice_date': localize_datetime(invoice.created_at)
        >>> }
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
        # Make aware (assumes UTC) then convert to school timezone
        dt = timezone.make_aware(dt)
    
    return dt.astimezone(get_school_timezone())


def format_school_datetime(dt, format_string='%Y-%m-%d %H:%M:%S %Z'):
    """
    Format datetime in school's operational timezone.
    
    Converts datetime to school timezone and formats it according to
    the provided format string. Perfect for displaying timestamps to users.
    
    Args:
        dt: datetime object (naive or aware)
        format_string: strftime format string (default includes timezone name)
        
    Returns:
        str: Formatted datetime string in school timezone, or empty string if dt is None
    
    Example:
        >>> from core.utils import format_school_datetime
        >>> 
        >>> # Default format
        >>> formatted = format_school_datetime(payment.created_at)
        >>> # Output: "2025-01-15 14:30:45 EAT"
        >>> 
        >>> # Custom format - user-friendly
        >>> formatted = format_school_datetime(
        >>>     invoice.created_at,
        >>>     format_string='%B %d, %Y at %I:%M %p'
        >>> )
        >>> # Output: "January 15, 2025 at 02:30 PM"
        >>> 
        >>> # Short date format
        >>> formatted = format_school_datetime(
        >>>     transaction.date,
        >>>     format_string='%d/%m/%Y'
        >>> )
        >>> # Output: "15/01/2025"
        >>> 
        >>> # In template (via context processor or filter)
        >>> {{ payment.created_at|format_datetime }}
    """
    if dt is None:
        return ''
    
    local_dt = localize_datetime(dt)
    return local_dt.strftime(format_string)


def make_timezone_aware(dt, tz=None):
    """
    Make a naive datetime timezone-aware.
    
    Args:
        dt: Naive datetime object
        tz: Optional timezone (defaults to school timezone)
        
    Returns:
        datetime: Timezone-aware datetime, or None if dt is None
        
    Example:
        >>> from datetime import datetime
        >>> from core.utils import make_timezone_aware
        >>> 
        >>> # Make naive datetime aware
        >>> naive_dt = datetime(2025, 1, 15, 10, 30)
        >>> aware_dt = make_timezone_aware(naive_dt)
        >>> print(aware_dt)  # 2025-01-15 10:30:00+03:00
        >>> 
        >>> # Already aware datetime - returns as-is
        >>> aware_dt = make_timezone_aware(aware_dt)
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
    Convert school timezone datetime to UTC.
    
    Useful for storing datetimes in database (Django stores as UTC by default).
    
    Args:
        dt: datetime object in school timezone
        
    Returns:
        datetime: Timezone-aware datetime in UTC
        
    Example:
        >>> from core.utils import convert_to_utc, get_school_current_time
        >>> 
        >>> school_time = get_school_current_time()  # 2025-01-15 14:30:00+03:00
        >>> utc_time = convert_to_utc(school_time)   # 2025-01-15 11:30:00+00:00
    """
    if dt is None:
        return None
    
    if timezone.is_naive(dt):
        dt = make_timezone_aware(dt)
    
    return dt.astimezone(ZoneInfo('UTC'))


# =============================================================================
# DATE RANGE UTILITIES
# =============================================================================

def get_date_range_for_period(period_type='month', reference_date=None):
    """
    Get start and end dates for various period types.
    
    Args:
        period_type: 'today', 'week', 'month', 'quarter', 'year'
        reference_date: Optional reference date (uses school today if None)
        
    Returns:
        tuple: (start_date, end_date) in school timezone
        
    Example:
        >>> from core.utils import get_date_range_for_period
        >>> 
        >>> # This month's range
        >>> start, end = get_date_range_for_period('month')
        >>> payments = Payment.objects.filter(
        >>>     payment_date__gte=start,
        >>>     payment_date__lte=end
        >>> )
        >>> 
        >>> # This week's range
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
        end = start + timedelta(days=6)
        return start, end
    
    elif period_type == 'month':
        # First to last day of month
        start = reference_date.replace(day=1)
        last_day = monthrange(reference_date.year, reference_date.month)[1]
        end = reference_date.replace(day=last_day)
        return start, end
    
    elif period_type == 'quarter':
        # Quarter start/end
        quarter = (reference_date.month - 1) // 3 + 1
        start_month = (quarter - 1) * 3 + 1
        start = reference_date.replace(month=start_month, day=1)
        
        end_month = start_month + 2
        last_day = monthrange(reference_date.year, end_month)[1]
        end = reference_date.replace(month=end_month, day=last_day)
        return start, end
    
    elif period_type == 'year':
        # Calendar year
        start = reference_date.replace(month=1, day=1)
        end = reference_date.replace(month=12, day=31)
        return start, end
    
    else:
        # Default to today
        return reference_date, reference_date


# =============================================================================
# PAGINATION & FILTERING
# =============================================================================

def paginate_queryset(request, queryset, per_page=20):
    """
    Paginate a queryset with sensible defaults and error handling.
    
    Args:
        request: HTTP request object
        queryset: Django queryset to paginate
        per_page: Items per page (default: 20)
        
    Returns:
        tuple: (page_obj, paginator)
        
    Example:
        >>> from core.utils import paginate_queryset
        >>> from finance.models import Invoice
        >>> 
        >>> def invoice_list(request):
        >>>     invoices = Invoice.objects.all()
        >>>     page_obj, paginator = paginate_queryset(request, invoices, per_page=50)
        >>>     return render(request, 'invoices.html', {
        >>>         'page_obj': page_obj,
        >>>         'paginator': paginator
        >>>     })
    """
    paginator = Paginator(queryset, per_page)
    page = request.GET.get('page', 1)
    
    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)
    
    return page_obj, paginator


def parse_filters(request, filter_keys):
    """
    Extract filter values from request.GET with validation.
    
    Args:
        request: HTTP request object
        filter_keys: list of filter names to extract
        
    Returns:
        dict: {key: value or None}
        
    Example:
        >>> from core.utils import parse_filters
        >>> 
        >>> def invoice_list(request):
        >>>     filters = parse_filters(request, [
        >>>         'status', 'student', 'academic_session', 'date_from', 'date_to'
        >>>     ])
        >>>     
        >>>     invoices = Invoice.objects.all()
        >>>     if filters['status']:
        >>>         invoices = invoices.filter(status=filters['status'])
        >>>     if filters['student']:
        >>>         invoices = invoices.filter(student_id=filters['student'])
        >>>     # ... more filters
    """
    filters = {}
    for key in filter_keys:
        value = request.GET.get(key, '').strip()
        filters[key] = value if value else None
    return filters


# =============================================================================
# NUMBERING & CODE GENERATION
# =============================================================================

def generate_next_number(prefix, last_number, include_year=True, year=None):
    """
    Generate next sequential number with prefix and optional year.
    
    Args:
        prefix: Number prefix (e.g., 'INV', 'PMT')
        last_number: Last used number (e.g., 'INV-2025-00042')
        include_year: Whether to include year in format
        year: Optional year (uses current academic year if None)
        
    Returns:
        str: Next number in sequence
        
    Example:
        >>> from core.utils import generate_next_number
        >>> 
        >>> # With year
        >>> next_num = generate_next_number('INV', 'INV-2025-00042', include_year=True)
        >>> print(next_num)  # 'INV-2025-00043'
        >>> 
        >>> # Without year
        >>> next_num = generate_next_number('PMT', 'PMT-00156', include_year=False)
        >>> print(next_num)  # 'PMT-00157'
        >>> 
        >>> # First number
        >>> next_num = generate_next_number('RCPT', None, include_year=True)
        >>> print(next_num)  # 'RCPT-2025-00001'
    """
    from datetime import date
    
    # Determine year
    if year is None:
        fiscal_year = get_active_fiscal_year()
        if fiscal_year:
            year = fiscal_year.start_date.year
        else:
            year = date.today().year
    
    # Extract sequence number from last_number
    if last_number:
        try:
            # Handle formats: PREFIX-YEAR-00042 or PREFIX-00042
            parts = last_number.split('-')
            sequence_part = parts[-1]
            current_sequence = int(sequence_part)
            next_sequence = current_sequence + 1
        except (ValueError, IndexError):
            next_sequence = 1
    else:
        next_sequence = 1
    
    # Format new number
    if include_year:
        return f"{prefix}-{year}-{next_sequence:05d}"
    else:
        return f"{prefix}-{next_sequence:05d}"


# =============================================================================
# TIMEZONE DEBUGGING UTILITIES (for development/troubleshooting)
# =============================================================================

def debug_timezone_info():
    """
    Get comprehensive timezone information for debugging.
    
    **FOR DEVELOPMENT/TROUBLESHOOTING ONLY!**
    
    Returns:
        dict: Dictionary with timezone debugging information
        
    Example:
        >>> from core.utils import debug_timezone_info
        >>> import json
        >>> 
        >>> # In Django shell or view
        >>> info = debug_timezone_info()
        >>> print(json.dumps(info, indent=2))
        >>> 
        >>> # Or in a debug view
        >>> def debug_view(request):
        >>>     return JsonResponse(debug_timezone_info())
    """
    from django.conf import settings
    
    try:
        from core.models import SchoolConfiguration
        config = SchoolConfiguration.get_cached_instance()
        configured_tz = config.operational_timezone if config else None
    except Exception as e:
        configured_tz = f"Error: {e}"
    
    current_time = get_school_current_time()
    
    return {
        'django_timezone_setting': settings.TIME_ZONE,
        'django_use_tz': settings.USE_TZ,
        'school_configured_timezone': configured_tz,
        'effective_school_timezone': str(get_school_timezone()),
        'current_utc_time': timezone.now().isoformat(),
        'current_school_time': current_time.isoformat(),
        'current_school_date': get_school_today().isoformat(),
        'timezone_offset': current_time.strftime('%z'),
        'timezone_name': current_time.strftime('%Z'),
        'available_timezones_sample': [
            'Africa/Kampala', 'Africa/Nairobi', 'Africa/Lagos',
            'Africa/Johannesburg', 'Europe/London', 'America/New_York'
        ]
    }


# =============================================================================
# VALIDATION UTILITIES
# =============================================================================

def validate_date_range(start_date, end_date):
    """
    Validate that start_date is before end_date.
    
    Args:
        start_date: Start date
        end_date: End date
        
    Returns:
        tuple: (is_valid, error_message)
        
    Example:
        >>> from core.utils import validate_date_range
        >>> from datetime import date
        >>> 
        >>> is_valid, error = validate_date_range(
        >>>     date(2025, 1, 1),
        >>>     date(2025, 12, 31)
        >>> )
        >>> if not is_valid:
        >>>     print(error)
    """
    if start_date and end_date:
        if start_date > end_date:
            return False, "Start date must be before end date"
    
    return True, None


def validate_email(email):
    """
    Simple email validation.
    
    Args:
        email: Email address to validate
        
    Returns:
        tuple: (is_valid, error_message)
    """
    import re
    
    if not email:
        return False, "Email is required"
    
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_regex, email):
        return False, "Invalid email format"
    
    return True, None


def validate_phone_number(phone, country_code='UG'):
    """
    Validate phone number format.
    
    Args:
        phone: Phone number to validate
        country_code: Country code for validation (default: UG for Uganda)
        
    Returns:
        tuple: (is_valid, error_message)
        
    Example:
        >>> from core.utils import validate_phone_number
        >>> is_valid, error = validate_phone_number('0782123456')
        >>> if not is_valid:
        >>>     print(error)
    """
    if not phone:
        return False, "Phone number is required"
    
    # Remove spaces and common separators
    clean_phone = phone.replace(' ', '').replace('-', '').replace('+', '')
    
    # Uganda phone number validation (example)
    if country_code == 'UG':
        # Should be 10 digits starting with 0, or 12 digits starting with 256
        if len(clean_phone) == 10 and clean_phone.startswith('0'):
            return True, None
        elif len(clean_phone) == 12 and clean_phone.startswith('256'):
            return True, None
        else:
            return False, "Invalid Uganda phone number format (should be 07XXXXXXXX or 2567XXXXXXXX)"
    
    # Generic validation - at least 7 digits
    if len(clean_phone) < 7:
        return False, "Phone number too short"
    
    return True, None


# =============================================================================
# STRING UTILITIES
# =============================================================================

def truncate_string(text, max_length=50, suffix='...'):
    """
    Truncate string to maximum length with suffix.
    
    Args:
        text: String to truncate
        max_length: Maximum length including suffix
        suffix: Suffix to add (default: '...')
        
    Returns:
        str: Truncated string
        
    Example:
        >>> from core.utils import truncate_string
        >>> long_text = "This is a very long description that needs truncating"
        >>> short_text = truncate_string(long_text, max_length=30)
        >>> print(short_text)  # "This is a very long descr..."
    """
    if not text:
        return ''
    
    if len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix


def slugify_filename(filename):
    """
    Create a safe filename slug.
    
    Args:
        filename: Original filename
        
    Returns:
        str: Safe filename
        
    Example:
        >>> from core.utils import slugify_filename
        >>> safe = slugify_filename("Student Report (Term 1).pdf")
        >>> print(safe)  # "student_report_term_1.pdf"
    """
    from django.utils.text import slugify
    import os
    
    # Split filename and extension
    name, ext = os.path.splitext(filename)
    
    # Slugify the name part
    safe_name = slugify(name)
    
    # Return with original extension
    return f"{safe_name}{ext.lower()}"


# =============================================================================
# EXPORT UTILITIES
# =============================================================================

def export_to_csv(queryset, fields, filename='export.csv'):
    """
    Export queryset to CSV response.
    
    Args:
        queryset: Django queryset to export
        fields: List of field names to include
        filename: Output filename
        
    Returns:
        HttpResponse: CSV file response
        
    Example:
        >>> from core.utils import export_to_csv
        >>> from finance.models import Invoice
        >>> 
        >>> def export_invoices(request):
        >>>     invoices = Invoice.objects.all()
        >>>     return export_to_csv(
        >>>         invoices,
        >>>         fields=['invoice_number', 'student', 'total_amount', 'status'],
        >>>         filename='invoices_export.csv'
        >>>     )
    """
    import csv
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    writer = csv.writer(response)
    
    # Write header
    writer.writerow(fields)
    
    # Write data
    for obj in queryset:
        row = []
        for field in fields:
            value = getattr(obj, field, '')
            row.append(str(value))
        writer.writerow(row)
    
    return response