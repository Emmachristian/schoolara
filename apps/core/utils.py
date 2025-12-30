# core/utils.py

"""
Central utilities for School Management System
Prevents code duplication and ensures consistency across all apps
"""
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import HttpResponse
from decimal import Decimal, InvalidOperation
from datetime import date, datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# Thread-local storage for recursion detection
import threading
_thread_locals = threading.local()

def _is_in_timezone_query():
    """Check if we're currently in a timezone query to prevent recursion"""
    return getattr(_thread_locals, 'in_timezone_query', False)

def _set_timezone_query_flag(value):
    """Set the timezone query flag"""
    _thread_locals.in_timezone_query = value


# =============================================================================
# CURRENCY & MONEY FORMATTING
# =============================================================================

def get_base_currency():
    """
    Get base currency from school financial settings.
    Safe method that handles circular imports and missing config.
    
    Returns:
        str: Currency code (defaults to 'UGX')
    
    Example:
        >>> from core.utils import get_base_currency
        >>> currency = get_base_currency()
        >>> print(f"School currency: {currency}")
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
        formatted = f"{amount_decimal:,.2f}"
        return f"UGX {formatted}" if include_symbol else formatted
    except (ValueError, TypeError):
        return "UGX 0.00" if include_symbol else "0.00"


def validate_amount_in_currency(amount, currency_code=None):
    """
    Validate that an amount is appropriate for the school's currency.
    
    Args:
        amount: Amount to validate
        currency_code: Optional currency code to check against
        
    Returns:
        tuple: (is_valid, error_message)
    
    Example:
        >>> from core.utils import validate_amount_in_currency
        >>> is_valid, error = validate_amount_in_currency(1500000)
        >>> if not is_valid:
        >>>     print(f"Error: {error}")
    """
    if currency_code is None:
        currency_code = get_base_currency()
    
    try:
        amount_decimal = Decimal(str(amount))
        
        if amount_decimal < 0:
            return False, "Amount cannot be negative"
        
        # Currency-specific validations
        # For example, some currencies don't use decimal places
        if currency_code in ['JPY', 'KRW', 'VND']:  # No decimal currencies
            if amount_decimal != amount_decimal.quantize(Decimal('1')):
                return False, f"{currency_code} does not use decimal places"
        
        return True, None
        
    except (ValueError, TypeError):
        return False, "Invalid amount format"


def calculate_percentage(part, whole, decimal_places=2):
    """
    Calculate percentage with safe division.
    
    Args:
        part: The part value
        whole: The whole value
        decimal_places: Number of decimal places (default: 2)
        
    Returns:
        Decimal: Percentage value, 0 if whole is 0
    
    Example:
        >>> from core.utils import calculate_percentage
        >>> percentage = calculate_percentage(75, 100)  # 75.00
        >>> completion = calculate_percentage(30, 120)  # 25.00
    """
    try:
        part = Decimal(str(part or 0))
        whole = Decimal(str(whole or 0))
        
        if whole == 0:
            return Decimal('0.00')
        
        percentage = (part / whole) * 100
        return percentage.quantize(Decimal(f'0.{"0" * decimal_places}'))
    except (ValueError, TypeError, ZeroDivisionError):
        return Decimal('0.00')


# =============================================================================
# TIMEZONE UTILITY FUNCTIONS
# =============================================================================

def get_school_timezone():
    """
    Get the school's operational timezone.
    
    This is the central timezone utility for all school operations.
    Use this consistently across the application to ensure all date/time
    calculations use the correct timezone.
    
    Returns:
        ZoneInfo: School's operational timezone (defaults to Africa/Kampala)
    """
    from zoneinfo import ZoneInfo
    
    # Prevent recursion - if we're already querying timezone, return default immediately
    if _is_in_timezone_query():
        logger.debug("Recursion detected in get_school_timezone, returning default")
        return ZoneInfo('Africa/Kampala')
    
    try:
        # Set flag to prevent recursion
        _set_timezone_query_flag(True)
        
        try:
            from core.models import SchoolConfiguration
            # Use get_cached_instance to avoid repeated DB queries
            config = SchoolConfiguration.get_cached_instance()
            if config and hasattr(config, 'get_timezone'):
                return config.get_timezone()
            # Fallback if timezone not yet implemented
            return ZoneInfo('Africa/Kampala')
        finally:
            # Always clear flag, even if exception occurs
            _set_timezone_query_flag(False)
            
    except Exception as e:
        logger.error(f"Error getting school timezone: {e}")
        _set_timezone_query_flag(False)  # Clear flag on error too
        return ZoneInfo('Africa/Kampala')


def get_school_current_time():
    """
    Get current time in school's operational timezone.
    
    Use this when you need the current timestamp with timezone awareness.
    Perfect for logging, audit trails, and transaction timestamps.
    
    Returns:
        datetime: Current datetime in school's timezone
    
    Example:
        >>> from core.utils import get_school_current_time
        >>> current_time = get_school_current_time()
        >>> payment.timestamp = current_time
        >>> print(f"Payment time: {current_time}")
    """
    from django.utils import timezone
    return timezone.now().astimezone(get_school_timezone())


def get_school_today():
    """
    Get today's date in school's operational timezone.
    
    **CRITICAL**: Always use this instead of date.today() or timezone.now().date()
    for any business logic that depends on dates!
    
    This is essential for:
    - Academic session/term boundary checks (is term active today?)
    - Fee payment due date calculations (is payment overdue?)
    - Attendance marking (today's attendance records)
    - Exam scheduling (exams scheduled for today)
    - Report generation (data as of today)
    - Late fee calculations (days overdue as of today)
    - Student enrollment status (enrolled as of today)
    - Any date-based business logic
    
    Why? Because "today" depends on timezone:
    - In Uganda (EAT/UTC+3), it might be Feb 15 at 1:00 AM
    - In New York (EST/UTC-5), it's still Feb 14 at 5:00 PM
    - In Tokyo (JST/UTC+9), it's Feb 15 at 7:00 AM
    - Using UTC would give wrong results for local school operations
    
    Real-world scenarios:
    - Boarding school: Students check in "today" at midnight
    - Fee deadline: Payment due "today" at 11:59 PM school time
    - Attendance: Marked for "today" even if parent abroad logs in
    - Report cards: Generated with data as of "today" in school timezone
    
    Returns:
        date: Today's date in school's timezone
    
    Example:
        >>> from core.utils import get_school_today
        >>> today = get_school_today()
        >>> 
        >>> # Check if term is active
        >>> if session.start_date <= today <= session.end_date:
        >>>     print("Term is active today")
        >>> 
        >>> # Check if fee payment is overdue
        >>> if invoice.due_date < today:
        >>>     days_overdue = (today - invoice.due_date).days
        >>>     print(f"Payment is {days_overdue} days overdue")
        >>> 
        >>> # Get today's attendance records
        >>> attendance = Attendance.objects.filter(date=today)
        >>> 
        >>> # Check student enrollment status
        >>> if enrollment.start_date <= today <= enrollment.end_date:
        >>>     print("Student is currently enrolled")
    """
    return get_school_current_time().date()


def localize_datetime(dt):
    """
    Convert a datetime to school's operational timezone.
    
    Use this to convert UTC or naive datetimes to the school's timezone
    for display or calculations.
    
    Args:
        dt: datetime object (naive or aware)
        
    Returns:
        datetime: Timezone-aware datetime in school's operational timezone
    
    Example:
        >>> from core.utils import localize_datetime
        >>> utc_time = timezone.now()  # In UTC
        >>> local_time = localize_datetime(utc_time)
        >>> print(f"Local school time: {local_time}")
        >>> 
        >>> # Convert payment timestamp to school time
        >>> payment_local = localize_datetime(payment.created_at)
        >>> print(f"Payment received at: {payment_local}")
    """
    from django.utils import timezone
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    return dt.astimezone(get_school_timezone())


def is_same_day_in_school_timezone(dt1, dt2):
    """
    Check if two datetimes fall on the same calendar day in school timezone.
    
    Args:
        dt1: First datetime
        dt2: Second datetime
        
    Returns:
        bool: True if same day in school timezone
    
    Example:
        >>> from core.utils import is_same_day_in_school_timezone
        >>> 
        >>> # Check if two payments were made on the same school day
        >>> same_day = is_same_day_in_school_timezone(
        >>>     payment1.created_at,
        >>>     payment2.created_at
        >>> )
    """
    local_dt1 = localize_datetime(dt1)
    local_dt2 = localize_datetime(dt2)
    return local_dt1.date() == local_dt2.date()


# =============================================================================
# ACADEMIC PERIOD & YEAR UTILITIES
# =============================================================================

def get_active_academic_session():
    """
    Get the currently active academic session/term.
    
    Returns:
        AcademicSession or None: Active academic session
    
    Example:
        >>> from core.utils import get_active_academic_session
        >>> session = get_active_academic_session()
        >>> if session:
        >>>     print(f"Current term: {session.name}")
    """
    try:
        from academics.models import AcademicSession
        return AcademicSession.get_active_session()
    except Exception as e:
        logger.error(f"Error fetching active academic session: {e}")
        return None


def get_active_fiscal_year():
    """
    Get the currently active fiscal year.
    
    Returns:
        FiscalYear or None: Active fiscal year
    
    Example:
        >>> from core.utils import get_active_fiscal_year
        >>> fiscal_year = get_active_fiscal_year()
        >>> if fiscal_year:
        >>>     print(f"Current fiscal year: {fiscal_year.name}")
    """
    try:
        from core.models import FiscalYear
        return FiscalYear.get_active_fiscal_year()
    except Exception as e:
        logger.error(f"Error fetching active fiscal year: {e}")
        return None


def get_active_fiscal_period():
    """
    Get the currently active fiscal period.
    
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


def get_academic_session_by_date(check_date=None):
    """
    Get the academic session that contains a specific date.
    
    Args:
        check_date: Date to check (defaults to today in school timezone)
        
    Returns:
        AcademicSession or None: Session containing the date
    
    Example:
        >>> from core.utils import get_academic_session_by_date, get_school_today
        >>> 
        >>> # Get current session
        >>> current_session = get_academic_session_by_date()
        >>> 
        >>> # Get session for specific date
        >>> from datetime import date
        >>> session = get_academic_session_by_date(date(2024, 3, 15))
    """
    if check_date is None:
        check_date = get_school_today()
    
    try:
        from academics.models import AcademicSession
        return AcademicSession.objects.filter(
            start_date__lte=check_date,
            end_date__gte=check_date
        ).first()
    except Exception as e:
        logger.error(f"Error fetching academic session by date: {e}")
        return None


def get_fiscal_period_by_date(check_date=None):
    """
    Get the fiscal period that contains a specific date.
    
    Args:
        check_date: Date to check (defaults to today in school timezone)
        
    Returns:
        FiscalPeriod or None: Period containing the date
    
    Example:
        >>> from core.utils import get_fiscal_period_by_date
        >>> period = get_fiscal_period_by_date()
        >>> if period:
        >>>     print(f"Current period: {period.name}")
    """
    if check_date is None:
        check_date = get_school_today()
    
    try:
        from core.models import FiscalPeriod
        return FiscalPeriod.objects.filter(
            start_date__lte=check_date,
            end_date__gte=check_date
        ).first()
    except Exception as e:
        logger.error(f"Error fetching fiscal period by date: {e}")
        return None


def get_school_configuration():
    """
    Get school configuration instance safely.
    
    Returns:
        SchoolConfiguration or None: Configuration instance
    
    Example:
        >>> from core.utils import get_school_configuration
        >>> config = get_school_configuration()
        >>> if config:
        >>>     print(f"Term system: {config.get_term_system_display()}")
    """
    try:
        from core.models import SchoolConfiguration
        return SchoolConfiguration.get_cached_instance()
    except Exception as e:
        logger.error(f"Error fetching school configuration: {e}")
        return None


# =============================================================================
# DATE & ACADEMIC CALENDAR UTILITIES
# =============================================================================

def calculate_days_between(start_date, end_date, inclusive=True):
    """
    Calculate number of days between two dates.
    
    Args:
        start_date: Start date
        end_date: End date
        inclusive: Include both start and end dates (default: True)
        
    Returns:
        int: Number of days
    
    Example:
        >>> from datetime import date
        >>> from core.utils import calculate_days_between
        >>> 
        >>> days = calculate_days_between(date(2024, 1, 1), date(2024, 1, 10))
        >>> print(f"Days: {days}")  # 10 days (inclusive)
        >>> 
        >>> days = calculate_days_between(date(2024, 1, 1), date(2024, 1, 10), inclusive=False)
        >>> print(f"Days: {days}")  # 9 days
    """
    if not start_date or not end_date:
        return 0
    
    delta = (end_date - start_date).days
    return delta + 1 if inclusive else delta


def calculate_weeks_between(start_date, end_date):
    """
    Calculate number of weeks between two dates.
    
    Args:
        start_date: Start date
        end_date: End date
        
    Returns:
        int: Number of weeks (rounded down)
    
    Example:
        >>> from datetime import date
        >>> from core.utils import calculate_weeks_between
        >>> weeks = calculate_weeks_between(date(2024, 1, 1), date(2024, 3, 31))
        >>> print(f"Weeks: {weeks}")
    """
    days = calculate_days_between(start_date, end_date, inclusive=True)
    return days // 7


def is_school_day(check_date=None, exclude_weekends=True):
    """
    Check if a date is a school day (not weekend/holiday).
    
    Args:
        check_date: Date to check (defaults to today)
        exclude_weekends: Exclude Saturday and Sunday (default: True)
        
    Returns:
        bool: True if school day
    
    Example:
        >>> from core.utils import is_school_day, get_school_today
        >>> 
        >>> if is_school_day():
        >>>     print("Today is a school day")
        >>> 
        >>> # Check specific date
        >>> from datetime import date
        >>> if is_school_day(date(2024, 12, 25)):
        >>>     print("Dec 25 is a school day")
    
    Note:
        This is a basic implementation. Extend with:
        - School holiday calendar integration
        - Public holiday checking
        - Half-day/exam day handling
    """
    if check_date is None:
        check_date = get_school_today()
    
    # Check weekend
    if exclude_weekends and check_date.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    
    # TODO: Check against school holiday calendar
    # TODO: Check against public holidays
    
    return True


def get_school_days_between(start_date, end_date, exclude_weekends=True):
    """
    Count school days between two dates (excluding weekends/holidays).
    
    Args:
        start_date: Start date
        end_date: End date
        exclude_weekends: Exclude weekends (default: True)
        
    Returns:
        int: Number of school days
    
    Example:
        >>> from datetime import date
        >>> from core.utils import get_school_days_between
        >>> 
        >>> school_days = get_school_days_between(
        >>>     date(2024, 1, 1),
        >>>     date(2024, 1, 31)
        >>> )
        >>> print(f"School days in January: {school_days}")
    """
    if not start_date or not end_date or start_date > end_date:
        return 0
    
    count = 0
    current = start_date
    
    while current <= end_date:
        if is_school_day(current, exclude_weekends):
            count += 1
        current += timedelta(days=1)
    
    return count


# =============================================================================
# PAGINATION & FILTERING
# =============================================================================

def paginate_queryset(request, queryset, per_page=20):
    """
    Paginate a queryset with sensible defaults.
    
    Args:
        request: HTTP request object
        queryset: Django queryset to paginate
        per_page: Items per page (default: 20)
        
    Returns:
        tuple: (page_obj, paginator)
    
    Example:
        >>> from core.utils import paginate_queryset
        >>> 
        >>> def student_list(request):
        >>>     students = Student.objects.all()
        >>>     page_obj, paginator = paginate_queryset(request, students, per_page=25)
        >>>     return render(request, 'students.html', {'page_obj': page_obj})
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
    Extract filter values from request.GET.
    
    Args:
        request: HTTP request object
        filter_keys: list of filter names to extract
        
    Returns:
        dict: {key: value or None}
    
    Example:
        >>> from core.utils import parse_filters
        >>> 
        >>> def student_search(request):
        >>>     filters = parse_filters(request, ['grade', 'stream', 'search'])
        >>>     queryset = Student.objects.all()
        >>>     
        >>>     if filters['grade']:
        >>>         queryset = queryset.filter(grade=filters['grade'])
        >>>     if filters['search']:
        >>>         queryset = queryset.filter(name__icontains=filters['search'])
        >>>     
        >>>     return queryset
    """
    filters = {}
    for key in filter_keys:
        value = request.GET.get(key, '').strip()
        filters[key] = value if value else None
    return filters


def build_filter_dict(filters, field_mappings=None):
    """
    Build Django ORM filter dictionary from parsed filters.
    
    Args:
        filters: Dict of filter key-value pairs
        field_mappings: Optional dict mapping filter keys to model fields
        
    Returns:
        dict: Django ORM filter dict
    
    Example:
        >>> from core.utils import parse_filters, build_filter_dict
        >>> 
        >>> filters = parse_filters(request, ['grade', 'status', 'search'])
        >>> 
        >>> filter_dict = build_filter_dict(filters, {
        >>>     'grade': 'grade__id',
        >>>     'status': 'enrollment_status',
        >>>     'search': 'name__icontains'
        >>> })
        >>> 
        >>> students = Student.objects.filter(**filter_dict)
    """
    if field_mappings is None:
        field_mappings = {}
    
    filter_dict = {}
    for key, value in filters.items():
        if value is not None:
            field_name = field_mappings.get(key, key)
            filter_dict[field_name] = value
    
    return filter_dict


# =============================================================================
# NUMBER & CALCULATION UTILITIES
# =============================================================================

def safe_decimal(value, default=Decimal('0.00')):
    """
    Safely convert value to Decimal.
    
    Args:
        value: Value to convert
        default: Default value if conversion fails
        
    Returns:
        Decimal: Converted value or default
    
    Example:
        >>> from core.utils import safe_decimal
        >>> amount = safe_decimal(user_input)
        >>> amount = safe_decimal("invalid", Decimal('0.00'))
    """
    try:
        return Decimal(str(value))
    except (ValueError, TypeError, InvalidOperation):
        return default


def calculate_proportional_amount(total, numerator, denominator):
    """
    Calculate proportional amount (for pro-rata calculations).
    
    Args:
        total: Total amount
        numerator: Proportion numerator (e.g., days attended)
        denominator: Proportion denominator (e.g., total days)
        
    Returns:
        Decimal: Proportional amount
    
    Example:
        >>> from core.utils import calculate_proportional_amount
        >>> 
        >>> # Student attended 45 out of 90 days in term
        >>> # Calculate proportional tuition fee
        >>> full_fee = Decimal('1500000.00')
        >>> prorated = calculate_proportional_amount(full_fee, 45, 90)
        >>> print(f"Pro-rated fee: {prorated}")  # 750000.00
    """
    try:
        total = Decimal(str(total))
        numerator = Decimal(str(numerator))
        denominator = Decimal(str(denominator))
        
        if denominator == 0:
            return Decimal('0.00')
        
        return (total * numerator / denominator).quantize(Decimal('0.01'))
    except (ValueError, TypeError, ZeroDivisionError):
        return Decimal('0.00')


def round_to_currency(amount, currency_code=None):
    """
    Round amount to appropriate decimal places for currency.
    
    Args:
        amount: Amount to round
        currency_code: Currency code (defaults to school currency)
        
    Returns:
        Decimal: Rounded amount
    
    Example:
        >>> from core.utils import round_to_currency
        >>> amount = round_to_currency(1500000.567)  # 1500000.57
        >>> amount = round_to_currency(1500.5, 'JPY')  # 1501 (no decimals)
    """
    if currency_code is None:
        currency_code = get_base_currency()
    
    try:
        amount = Decimal(str(amount))
        
        # Currencies without decimal places
        if currency_code in ['JPY', 'KRW', 'VND', 'CLP', 'PYG']:
            return amount.quantize(Decimal('1'))
        
        # Standard 2 decimal places
        return amount.quantize(Decimal('0.01'))
        
    except (ValueError, TypeError):
        return Decimal('0.00')


# =============================================================================
# STRING & TEXT UTILITIES
# =============================================================================

def truncate_text(text, max_length=50, suffix='...'):
    """
    Truncate text to maximum length.
    
    Args:
        text: Text to truncate
        max_length: Maximum length
        suffix: Suffix to add when truncated
        
    Returns:
        str: Truncated text
    
    Example:
        >>> from core.utils import truncate_text
        >>> long_text = "This is a very long description that needs to be shortened"
        >>> short = truncate_text(long_text, 30)
        >>> print(short)  # "This is a very long descri..."
    """
    if not text:
        return ''
    
    text = str(text)
    if len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix


def generate_reference_number(prefix, sequence_number, year=None):
    """
    Generate formatted reference number.
    
    Args:
        prefix: Reference prefix (e.g., 'INV', 'PMT', 'RCPT')
        sequence_number: Sequence number
        year: Optional year (defaults to current year)
        
    Returns:
        str: Formatted reference number
    
    Example:
        >>> from core.utils import generate_reference_number
        >>> ref = generate_reference_number('INV', 123, 2024)
        >>> print(ref)  # "INV-2024-00123"
    """
    if year is None:
        today = get_school_today()
        year = today.year
    
    return f"{prefix}-{year}-{sequence_number:05d}"


# =============================================================================
# VALIDATION UTILITIES
# =============================================================================

def validate_date_range(start_date, end_date, allow_same_day=True):
    """
    Validate date range.
    
    Args:
        start_date: Start date
        end_date: End date
        allow_same_day: Allow start and end to be same day
        
    Returns:
        tuple: (is_valid, error_message)
    
    Example:
        >>> from datetime import date
        >>> from core.utils import validate_date_range
        >>> 
        >>> is_valid, error = validate_date_range(
        >>>     date(2024, 1, 1),
        >>>     date(2024, 12, 31)
        >>> )
        >>> if not is_valid:
        >>>     print(f"Error: {error}")
    """
    if not start_date or not end_date:
        return False, "Both start and end dates are required"
    
    if allow_same_day:
        if start_date > end_date:
            return False, "Start date must be on or before end date"
    else:
        if start_date >= end_date:
            return False, "Start date must be before end date"
    
    return True, None


def validate_no_overlap(start_date, end_date, existing_ranges, obj_to_exclude=None):
    """
    Validate that date range doesn't overlap with existing ranges.
    
    Args:
        start_date: New range start date
        end_date: New range end date
        existing_ranges: List of (start, end) tuples
        obj_to_exclude: Optional object to exclude from check (for updates)
        
    Returns:
        tuple: (is_valid, overlapping_range)
    
    Example:
        >>> from core.utils import validate_no_overlap
        >>> 
        >>> existing = [
        >>>     (date(2024, 1, 1), date(2024, 4, 30)),
        >>>     (date(2024, 5, 1), date(2024, 8, 31)),
        >>> ]
        >>> 
        >>> is_valid, overlap = validate_no_overlap(
        >>>     date(2024, 4, 1),
        >>>     date(2024, 5, 31),
        >>>     existing
        >>> )
    """
    for existing_start, existing_end in existing_ranges:
        # Check for overlap: new range starts before existing ends AND new range ends after existing starts
        if start_date <= existing_end and end_date >= existing_start:
            return False, (existing_start, existing_end)
    
    return True, None


# =============================================================================
# EXPORT UTILITIES
# =============================================================================

def generate_csv_response(data, filename, headers=None):
    """
    Generate CSV HTTP response from data.
    
    Args:
        data: List of lists/tuples containing row data
        filename: Output filename
        headers: Optional list of column headers
        
    Returns:
        HttpResponse: CSV download response
    
    Example:
        >>> from core.utils import generate_csv_response
        >>> 
        >>> def export_students(request):
        >>>     students = Student.objects.all()
        >>>     data = [[s.admission_number, s.name, s.grade] for s in students]
        >>>     headers = ['Admission No', 'Name', 'Grade']
        >>>     return generate_csv_response(data, 'students.csv', headers)
    """
    import csv
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    writer = csv.writer(response)
    
    if headers:
        writer.writerow(headers)
    
    for row in data:
        writer.writerow(row)
    
    return response


# =============================================================================
# LOGGING UTILITIES
# =============================================================================

def log_user_action(user, action, details=None, level='INFO'):
    """
    Log user action for audit trail.
    
    Args:
        user: User object
        action: Action description
        details: Optional additional details dict
        level: Log level (INFO, WARNING, ERROR)
    
    Example:
        >>> from core.utils import log_user_action
        >>> 
        >>> log_user_action(
        >>>     request.user,
        >>>     'Invoice Generated',
        >>>     {'invoice_id': invoice.pk, 'amount': invoice.total_amount}
        >>> )
    """
    username = getattr(user, 'username', 'anonymous')
    log_message = f"User: {username} | Action: {action}"
    
    if details:
        log_message += f" | Details: {details}"
    
    log_func = getattr(logger, level.lower(), logger.info)
    log_func(log_message)