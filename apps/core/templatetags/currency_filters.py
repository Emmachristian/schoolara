# core/templatetags/currency_filters.py

"""
Template filters for currency and money formatting in school management system.

These filters use the school's financial settings for consistent currency display
across all templates. All filters are timezone-aware and use the school's
configured currency settings.

Usage in templates:
    {% load currency_filters %}
    
    {{ invoice.total_amount|format_currency }}
    {{ payment.amount|money }}
    {{ discount|format_percentage }}
"""

from django import template
from decimal import Decimal, InvalidOperation
import logging

logger = logging.getLogger(__name__)
register = template.Library()


# =============================================================================
# BASIC CURRENCY FORMATTING
# =============================================================================

@register.filter
def format_currency(value):
    """
    Format a currency value according to school financial settings.
    
    This filter automatically uses the school's configured currency settings
    from FinancialSettings (currency, position, decimal places, thousand separator).
    
    Usage in template:
        {{ amount|format_currency }}
        {{ invoice.total_amount|format_currency }}
        {{ 1500000|format_currency }}
    
    Returns:
        str: Formatted currency string (e.g., "UGX 1,500,000.00")
        
    Example:
        Template:
            <p>Invoice Total: {{ invoice.total_amount|format_currency }}</p>
            
        Output:
            <p>Invoice Total: UGX 1,500,000.00</p>
    """
    # Use the centralized format_money function from core.utils
    from core.utils import format_money
    return format_money(value, include_symbol=True)


@register.filter
def money(value):
    """
    Alias for format_currency (shorter name for convenience).
    
    Usage:
        {{ amount|money }}
        {{ fee.amount|money }}
        
    Example:
        {{ student.balance|money }}  → "UGX 250,000.00"
    """
    from core.utils import format_money
    return format_money(value, include_symbol=True)


@register.filter
def currency(value):
    """
    Format with currency symbol (alias for semantic clarity).
    
    Usage:
        {{ amount|currency }}
        {{ scholarship.amount|currency }}
        
    Example:
        {{ invoice.total|currency }}  → "UGX 1,500,000.00"
    """
    from core.utils import format_money
    return format_money(value, include_symbol=True)


@register.filter
def amount(value):
    """
    Format amount WITHOUT currency symbol.
    
    Usage:
        {{ invoice.total_amount|amount }}
        
    Output:
        1,500,000.00 (without "UGX")
        
    Example:
        <td class="text-right">{{ payment.amount|amount }}</td>
        Output: <td class="text-right">1,500,000.00</td>
    """
    from core.utils import format_money
    return format_money(value, include_symbol=False)


@register.filter
def amount_no_decimals(value):
    """
    Format amount without currency symbol and without decimals.
    
    Usage:
        {{ invoice.total_amount|amount_no_decimals }}
        
    Output:
        1,500,000 (no symbol, no decimals)
        
    Example:
        For large amounts where decimals aren't important:
        {{ scholarship.total|amount_no_decimals }}  → "1,500,000"
    """
    if value is None:
        return "0"
    
    try:
        amount_decimal = Decimal(str(value or 0))
        # Round to nearest integer
        rounded = int(round(amount_decimal, 0))
        return f"{rounded:,}"
    except (ValueError, TypeError, InvalidOperation):
        return "0"


# =============================================================================
# PERCENTAGE FORMATTING
# =============================================================================

@register.filter
def format_percentage(value, decimal_places=2):
    """
    Format a percentage value with proper decimal places.
    
    Usage:
        {{ rate|format_percentage }}
        {{ rate|format_percentage:3 }}  # 3 decimal places
        {{ discount.percentage|format_percentage:1 }}
        
    Examples:
        12.5 → "12.50%"
        0.125 → "0.13%"
        75 → "75.00%"
        
    Template Example:
        <span class="discount">{{ scholarship.percentage|format_percentage }}</span>
        Output: <span class="discount">25.00%</span>
    """
    # Handle None, empty string, or whitespace
    if value is None or value == '':
        return f"0.{'0' * int(decimal_places)}%"
    
    try:
        # Ensure decimal_places is an integer
        try:
            decimal_places = int(decimal_places)
        except (ValueError, TypeError):
            decimal_places = 2
        
        # Handle different input types
        if isinstance(value, Decimal):
            rate = value
        elif isinstance(value, (int, float)):
            rate = Decimal(str(value))
        elif isinstance(value, str):
            # Clean the string
            value = value.strip()
            if not value:
                return f"0.{'0' * decimal_places}%"
            
            # Remove any existing % sign
            value = value.replace('%', '').strip()
            
            # Remove thousand separators if present
            value = value.replace(',', '')
            
            # Convert to Decimal
            rate = Decimal(value)
        else:
            # Last resort: try direct conversion
            rate = Decimal(str(value))
        
        # Format with specified decimal places
        return f"{rate:.{decimal_places}f}%"
        
    except (ValueError, TypeError, InvalidOperation) as e:
        # Log the error for debugging
        logger.warning(
            f"Could not format percentage value. "
            f"Value: {repr(value)}, Type: {type(value).__name__}, Error: {e}"
        )
        return f"0.{'0' * decimal_places}%"


@register.filter
def percentage(value):
    """
    Simple percentage formatter (2 decimal places default).
    
    Usage:
        {{ discount_rate|percentage }}
        
    Example:
        {{ scholarship.discount_rate|percentage }}  → "15.00%"
    """
    return format_percentage(value, 2)


# =============================================================================
# DECIMAL NUMBER FORMATTING
# =============================================================================

@register.filter
def format_decimal(value, decimal_places=2):
    """
    Format a decimal number with specified decimal places.
    
    Usage:
        {{ value|format_decimal }}
        {{ value|format_decimal:4 }}
        {{ gpa|format_decimal:3 }}
        
    Examples:
        1500000.5 → "1,500,000.50"
        3.14159 → "3.14"
        3.14159 with :3 → "3.142"
        
    Template Example:
        <p>GPA: {{ student.gpa|format_decimal:3 }}</p>
        Output: <p>GPA: 3.500</p>
    """
    if value is None:
        value = 0
    
    try:
        decimal_places = int(decimal_places)
        amount = Decimal(str(value))
        return f"{amount:,.{decimal_places}f}"
    except (ValueError, TypeError, InvalidOperation):
        return f"0.{'0' * int(decimal_places)}"


@register.filter
def format_number(value):
    """
    Format a number with thousand separators (no decimals).
    
    Usage:
        {{ student_count|format_number }}
        {{ total_students|format_number }}
        
    Example:
        {{ school.total_students|format_number }}  → "1,500"
    """
    if value is None:
        return "0"
    
    try:
        num = int(Decimal(str(value)))
        return f"{num:,}"
    except (ValueError, TypeError, InvalidOperation):
        return "0"


# =============================================================================
# CURRENCY INFORMATION TAGS
# =============================================================================

@register.simple_tag
def get_currency_symbol():
    """
    Get the school's currency symbol/code.
    
    Usage:
        {% get_currency_symbol %} → "UGX"
        
    Example:
        <p>All amounts in {% get_currency_symbol %}</p>
        Output: <p>All amounts in UGX</p>
    """
    from core.utils import get_school_currency
    return get_school_currency()


@register.simple_tag
def currency_info():
    """
    Get complete currency configuration as dict.
    
    Usage:
        {% currency_info as curr %}
        <p>Currency: {{ curr.code }}</p>
        <p>Decimals: {{ curr.decimal_places }}</p>
        
    Returns dict with:
        - code: Currency code (e.g., 'UGX')
        - decimal_places: Number of decimal places
        - position: Currency position ('BEFORE', 'AFTER', etc.)
        - use_separator: Whether to use thousand separators
        
    Example:
        {% currency_info as curr %}
        <div class="currency-info">
            <span>Currency: {{ curr.code }}</span>
            <span>Format: {{ curr.position }}</span>
        </div>
    """
    try:
        from core.models import FinancialSettings
        settings = FinancialSettings.get_instance()
        if settings:
            return {
                'code': settings.school_currency,
                'decimal_places': settings.decimal_places,
                'position': settings.currency_position,
                'use_separator': settings.use_thousand_separator,
            }
    except Exception as e:
        logger.warning(f"Could not get currency info: {e}")
    
    # Fallback
    return {
        'code': 'UGX',
        'decimal_places': 2,
        'position': 'BEFORE',
        'use_separator': True,
    }


# =============================================================================
# MONEY ARITHMETIC FILTERS
# =============================================================================

@register.filter
def multiply_money(value, multiplier):
    """
    Multiply a money value and format it.
    
    Usage:
        {{ fee_per_term|multiply_money:num_terms }}
        {{ unit_price|multiply_money:quantity }}
        
    Example:
        fee_per_term = 500000, num_terms = 3
        {{ fee_per_term|multiply_money:num_terms }}
        Output: "UGX 1,500,000.00"
        
    Template Example:
        <tr>
            <td>Tuition (3 terms)</td>
            <td>{{ fee.amount|multiply_money:3 }}</td>
        </tr>
    """
    if value is None or multiplier is None:
        return format_currency(0)
    
    try:
        result = Decimal(str(value)) * Decimal(str(multiplier))
        return format_currency(result)
    except (ValueError, TypeError, InvalidOperation):
        return format_currency(0)


@register.filter
def add_money(value, addend):
    """
    Add two money values and format.
    
    Usage:
        {{ tuition|add_money:boarding_fee }}
        {{ principal|add_money:interest }}
        
    Example:
        {{ invoice.tuition|add_money:invoice.boarding }}
        Output: "UGX 2,000,000.00"
        
    Template Example:
        <tr class="total">
            <td>Total Fees</td>
            <td>{{ tuition_fee|add_money:boarding_fee }}</td>
        </tr>
    """
    if value is None:
        value = 0
    if addend is None:
        addend = 0
    
    try:
        result = Decimal(str(value)) + Decimal(str(addend))
        return format_currency(result)
    except (ValueError, TypeError, InvalidOperation):
        return format_currency(0)


@register.filter
def subtract_money(value, subtrahend):
    """
    Subtract money values and format.
    
    Usage:
        {{ total|subtract_money:paid }}
        {{ invoice.total|subtract_money:invoice.paid_amount }}
        
    Example:
        {{ invoice.total_amount|subtract_money:invoice.paid_amount }}
        Output: "UGX 500,000.00"  (balance remaining)
        
    Template Example:
        <tr class="balance">
            <td>Balance Due</td>
            <td>{{ invoice.total|subtract_money:invoice.paid }}</td>
        </tr>
    """
    if value is None:
        value = 0
    if subtrahend is None:
        subtrahend = 0
    
    try:
        result = Decimal(str(value)) - Decimal(str(subtrahend))
        return format_currency(result)
    except (ValueError, TypeError, InvalidOperation):
        return format_currency(0)


@register.filter
def divide_money(value, divisor):
    """
    Divide money value and format.
    
    Usage:
        {{ total_fee|divide_money:num_installments }}
        
    Example:
        {{ annual_fee|divide_money:3 }}  # Divide by 3 terms
        Output: "UGX 500,000.00"  (per term)
        
    Template Example:
        <tr>
            <td>Fee per Term</td>
            <td>{{ annual_fee|divide_money:3 }}</td>
        </tr>
    """
    if value is None:
        return format_currency(0)
    
    try:
        divisor_decimal = Decimal(str(divisor or 1))
        if divisor_decimal == 0:
            return format_currency(0)
        
        result = Decimal(str(value)) / divisor_decimal
        return format_currency(result)
    except (ValueError, TypeError, InvalidOperation, ZeroDivisionError):
        return format_currency(0)


@register.filter
def percentage_of(value, total):
    """
    Calculate what percentage 'value' is of 'total'.
    
    Usage:
        {{ paid_amount|percentage_of:total_amount }}
        
    Example:
        paid = 750000, total = 1000000
        {{ paid|percentage_of:total }}
        Output: "75.00%"
        
    Template Example:
        <div class="progress-text">
            Payment Progress: {{ invoice.paid_amount|percentage_of:invoice.total_amount }}
        </div>
    """
    if value is None or total is None:
        return "0.00%"
    
    try:
        value_decimal = Decimal(str(value))
        total_decimal = Decimal(str(total or 1))
        
        if total_decimal == 0:
            return "0.00%"
        
        percentage = (value_decimal / total_decimal) * 100
        return f"{percentage:.2f}%"
    except (ValueError, TypeError, InvalidOperation, ZeroDivisionError):
        return "0.00%"


@register.filter
def apply_percentage(value, percentage):
    """
    Calculate percentage of a value and format as money.
    
    Usage:
        {{ total|apply_percentage:discount_rate }}
        
    Example:
        total = 1000000, discount = 10
        {{ total|apply_percentage:discount }}
        Output: "UGX 100,000.00"  (10% of 1,000,000)
        
    Template Example:
        <tr>
            <td>Discount ({{ discount_rate }}%)</td>
            <td>{{ invoice.total|apply_percentage:discount_rate }}</td>
        </tr>
    """
    if value is None or percentage is None:
        return format_currency(0)
    
    try:
        value_decimal = Decimal(str(value))
        percentage_decimal = Decimal(str(percentage))
        
        result = (value_decimal * percentage_decimal) / 100
        return format_currency(result)
    except (ValueError, TypeError, InvalidOperation):
        return format_currency(0)


# =============================================================================
# BALANCE & STATUS DISPLAY FILTERS
# =============================================================================

@register.filter
def balance_color_class(balance):
    """
    Return CSS class based on balance value.
    
    Usage:
        <span class="{{ student.balance|balance_color_class }}">
            {{ student.balance|money }}
        </span>
        
    Returns:
        - 'text-danger' if balance > 0 (owes money)
        - 'text-success' if balance < 0 (credit balance)
        - 'text-muted' if balance = 0 (fully paid)
        
    Example:
        {{ invoice.balance|balance_color_class }}
        Output: "text-danger" (for positive balance)
    """
    if balance is None:
        return 'text-muted'
    
    try:
        balance_decimal = Decimal(str(balance))
        
        if balance_decimal > 0:
            return 'text-danger'  # Owes money
        elif balance_decimal < 0:
            return 'text-success'  # Credit balance
        else:
            return 'text-muted'  # Fully paid
    except (ValueError, TypeError, InvalidOperation):
        return 'text-muted'


@register.filter
def payment_status_badge(status):
    """
    Return Bootstrap badge class based on payment status.
    
    Usage:
        <span class="badge {{ invoice.status|payment_status_badge }}">
            {{ invoice.get_status_display }}
        </span>
        
    Returns appropriate badge class for:
        - PAID: badge-success
        - PARTIAL: badge-warning
        - PENDING: badge-info
        - OVERDUE: badge-danger
        - CANCELLED: badge-secondary
        
    Example:
        <span class="badge {{ invoice.status|payment_status_badge }}">
            {{ invoice.get_status_display }}
        </span>
        Output: <span class="badge badge-danger">Overdue</span>
    """
    status_map = {
        'PAID': 'badge-success',
        'PARTIAL': 'badge-warning',
        'PENDING': 'badge-info',
        'OVERDUE': 'badge-danger',
        'CANCELLED': 'badge-secondary',
        'DRAFT': 'badge-light',
        'VOID': 'badge-dark',
    }
    
    return status_map.get(str(status).upper(), 'badge-secondary')


@register.filter
def abs_money(value):
    """
    Return absolute value of money amount, formatted.
    
    Usage:
        {{ balance|abs_money }}
        
    Example:
        balance = -50000
        {{ balance|abs_money }}
        Output: "UGX 50,000.00"
        
    Useful for displaying credit balances as positive amounts.
    """
    if value is None:
        return format_currency(0)
    
    try:
        amount = abs(Decimal(str(value)))
        return format_currency(amount)
    except (ValueError, TypeError, InvalidOperation):
        return format_currency(0)


# =============================================================================
# COMPARISON FILTERS
# =============================================================================

@register.filter
def is_positive(value):
    """
    Check if value is positive.
    
    Usage:
        {% if balance|is_positive %}
            <span class="text-danger">Owes Money</span>
        {% endif %}
        
    Returns:
        bool: True if value > 0
    """
    if value is None:
        return False
    
    try:
        return Decimal(str(value)) > 0
    except (ValueError, TypeError, InvalidOperation):
        return False


@register.filter
def is_negative(value):
    """
    Check if value is negative.
    
    Usage:
        {% if balance|is_negative %}
            <span class="text-success">Credit Balance</span>
        {% endif %}
        
    Returns:
        bool: True if value < 0
    """
    if value is None:
        return False
    
    try:
        return Decimal(str(value)) < 0
    except (ValueError, TypeError, InvalidOperation):
        return False


@register.filter
def is_zero(value):
    """
    Check if value is zero.
    
    Usage:
        {% if balance|is_zero %}
            <span class="text-success">Fully Paid</span>
        {% endif %}
        
    Returns:
        bool: True if value == 0
    """
    if value is None:
        return True
    
    try:
        return Decimal(str(value)) == 0
    except (ValueError, TypeError, InvalidOperation):
        return True


# =============================================================================
# FORMATTING FOR REPORTS
# =============================================================================

@register.filter
def format_for_report(value):
    """
    Format currency for financial reports (right-aligned, consistent width).
    
    Usage:
        <td class="text-right">{{ amount|format_for_report }}</td>
        
    Returns formatted string with consistent spacing for better report alignment.
    """
    from core.utils import format_money
    formatted = format_money(value, include_symbol=False)
    
    # Ensure consistent width (pad with spaces)
    return formatted.rjust(20)


@register.filter
def format_with_sign(value):
    """
    Format money with explicit + or - sign.
    
    Usage:
        {{ change_amount|format_with_sign }}
        
    Example:
        +50000 → "+UGX 50,000.00"
        -25000 → "-UGX 25,000.00"
        0 → "UGX 0.00"
        
    Useful for showing increases/decreases in financial reports.
    """
    if value is None:
        return format_currency(0)
    
    try:
        amount = Decimal(str(value))
        formatted = format_currency(abs(amount))
        
        if amount > 0:
            return f"+{formatted}"
        elif amount < 0:
            return f"-{formatted}"
        else:
            return formatted
    except (ValueError, TypeError, InvalidOperation):
        return format_currency(0)
    
@register.filter
def format_number_short(value):
    """
    Format large numbers in short form (K, M, B).
    
    Usage:
        {{ amount|format_number_short }}
        
    Examples:
        1500 → "1.5K"
        1500000 → "1.5M"
        1500000000 → "1.5B"
        500 → "500"
        
    Template Example:
        <h3>{{ stats.total_revenue|format_number_short }}</h3>
        Output: <h3>1.5M</h3>
    """
    if value is None:
        return "0"
    
    try:
        num = Decimal(str(value))
        abs_num = abs(num)
        
        # Determine suffix and divisor
        if abs_num >= 1_000_000_000:  # Billions
            formatted = num / Decimal('1000000000')
            suffix = 'B'
        elif abs_num >= 1_000_000:  # Millions
            formatted = num / Decimal('1000000')
            suffix = 'M'
        elif abs_num >= 1_000:  # Thousands
            formatted = num / Decimal('1000')
            suffix = 'K'
        else:
            # Less than 1000, just format with commas
            return f"{int(num):,}"
        
        # Format with 1 decimal place, remove trailing zeros
        formatted_str = f"{formatted:.1f}".rstrip('0').rstrip('.')
        return f"{formatted_str}{suffix}"
        
    except (ValueError, TypeError, InvalidOperation):
        return "0"
    
@register.filter
def money_short(value):
    """
    Format large numbers in short form WITH currency symbol (K, M, B).
    
    Usage:
        {{ amount|money_short }}
        
    Examples:
        1500 → "UGX 1.5K"
        1500000 → "UGX 1.5M"
        1500000000 → "UGX 1.5B"
        500 → "UGX 500"
        
    Template Example:
        <h3>{{ stats.total_revenue|money_short }}</h3>
        Output: <h3>UGX 1.5M</h3>
    """
    from core.utils import get_school_currency
    
    if value is None:
        return f"{get_school_currency()} 0"
    
    try:
        num = Decimal(str(value))
        abs_num = abs(num)
        currency = get_school_currency()
        
        # Determine suffix and divisor
        if abs_num >= 1_000_000_000:  # Billions
            formatted = num / Decimal('1000000000')
            suffix = 'B'
        elif abs_num >= 1_000_000:  # Millions
            formatted = num / Decimal('1000000')
            suffix = 'M'
        elif abs_num >= 1_000:  # Thousands
            formatted = num / Decimal('1000')
            suffix = 'K'
        else:
            # Less than 1000, just format with commas
            return f"{currency} {int(num):,}"
        
        # Format with 1 decimal place, remove trailing zeros
        formatted_str = f"{formatted:.1f}".rstrip('0').rstrip('.')
        return f"{currency} {formatted_str}{suffix}"
        
    except (ValueError, TypeError, InvalidOperation):
        return f"{get_school_currency()} 0"
    
@register.filter
def abs_value(value):
    """
    Return absolute value of a number (for use with widthratio and calculations).
    
    Usage:
        {% widthratio balance|abs_value 1 credit_limit as utilization %}
        
    Example:
        balance = -50000
        {{ balance|abs_value }}  → 50000 (numeric, not formatted)
        
    Note: This returns a numeric value, not a formatted string.
          Use abs_money filter for formatted currency display.
    """
    if value is None:
        return 0
    
    try:
        return abs(Decimal(str(value)))
    except (ValueError, TypeError, InvalidOperation):
        return 0