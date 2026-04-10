# core/templatetags/currency_filters.py

"""
Template filters for currency and money formatting in school management system.

These filters use the school's financial settings for consistent currency display
across all templates. All filters are timezone-aware and use the school's
configured currency settings.

MULTI-CURRENCY NOTE
───────────────────
Some filters always format using the school's primary currency symbol (UGX, SSD,
etc.) — these are correct for amounts that are already in school currency
(AccountTransaction.amount, Payment.amount_in_school_currency, etc.).

For amounts that may be in a foreign currency (Payment.amount when currency != school
currency, FeeInvoiceItem.amount, UniformSale totals), use:

    {{ payment.amount|format_in_currency:payment.currency }}
    → "USD 500.00"

And the conditional helper:
    {% if payment.currency|is_foreign_currency %}
        {{ payment.amount|format_in_currency:payment.currency }}
        <small>({{ payment.amount_in_school_currency|money }})</small>
    {% else %}
        {{ payment.amount|money }}
    {% endif %}

Usage in templates:
    {% load currency_filters %}

    {{ invoice.total_amount|format_currency }}
    {{ payment.amount_in_school_currency|money }}
    {{ payment.amount|format_in_currency:payment.currency }}
    {{ discount|format_percentage }}
"""

from django import template
from decimal import Decimal, InvalidOperation
import logging

logger = logging.getLogger(__name__)
register = template.Library()


# =============================================================================
# BASIC CURRENCY FORMATTING  (school currency)
# =============================================================================

@register.filter
def format_currency(value):
    """
    Format a currency value according to school financial settings.

    Always uses the school's configured primary currency symbol.
    For foreign-currency amounts use format_in_currency instead.

    Usage:
        {{ amount|format_currency }}
        {{ invoice.total_amount|format_currency }}
        {{ payment.amount_in_school_currency|format_currency }}

    Returns:
        str: Formatted currency string (e.g., "UGX 1,500,000.00")
    """
    from core.utils import format_money
    return format_money(value, include_symbol=True)


@register.filter
def money(value):
    """
    Alias for format_currency (shorter name for convenience).

    Always uses school currency symbol. Use format_in_currency for foreign amounts.

    Usage:
        {{ payment.amount_in_school_currency|money }}
        {{ invoice.total_amount|money }}

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
    """
    if value is None:
        return "0"
    try:
        amount_decimal = Decimal(str(value or 0))
        rounded = int(round(amount_decimal, 0))
        return f"{rounded:,}"
    except (ValueError, TypeError, InvalidOperation):
        return "0"


# =============================================================================
# FOREIGN CURRENCY FORMATTING
# =============================================================================

@register.filter
def format_in_currency(value, currency_code):
    """
    Format a value with a specific currency code rather than school currency.

    Use this for displaying foreign-currency amounts — e.g. on payment receipts
    where a parent paid in USD at a South Sudan school.

    Usage:
        {{ payment.amount|format_in_currency:payment.currency }}
        Output: "USD 500.00"

        {{ item.amount|format_in_currency:item.currency }}
        Output: "UGX 1,500,000.00"

    Typical receipt pattern:
        {% if payment.currency|is_foreign_currency %}
            {{ payment.amount|format_in_currency:payment.currency }}
            <small>({{ payment.amount_in_school_currency|money }} at rate {{ payment.exchange_rate }})</small>
        {% else %}
            {{ payment.amount|money }}
        {% endif %}

    Returns:
        str: Formatted string with the given currency code (e.g., "USD 500.00")
    """
    if not currency_code:
        return format_currency(value)

    currency_code = str(currency_code).upper().strip()

    if value is None:
        return f"{currency_code} 0.00"

    try:
        from core.models import FinancialSettings
        settings = FinancialSettings.get_instance()
        decimal_places = settings.decimal_places if settings else 2
        use_separator  = settings.use_thousand_separator if settings else True
    except Exception:
        decimal_places = 2
        use_separator  = True

    try:
        amt = Decimal(str(value or 0))
        if use_separator:
            formatted = f"{amt:,.{decimal_places}f}"
        else:
            formatted = f"{amt:.{decimal_places}f}"
        return f"{currency_code} {formatted}"
    except (ValueError, TypeError, InvalidOperation):
        return f"{currency_code} 0.{'0' * decimal_places}"


@register.filter
def is_foreign_currency(value):
    """
    Return True if the value (a currency code or an object with .currency)
    differs from the school's primary currency.

    Use this to conditionally show exchange rate information on receipts,
    invoices, and payment detail pages.

    Usage — with a currency code string:
        {% if payment.currency|is_foreign_currency %}
            <small>Rate: {{ payment.exchange_rate }}</small>
        {% endif %}

    Usage — with an object that has a .currency attribute:
        {% if payment|is_foreign_currency %}
            ...
        {% endif %}

    Returns:
        bool: True if the currency differs from school currency
    """
    try:
        from core.models import FinancialSettings
        school_currency = FinancialSettings.get_school_currency()
    except Exception:
        school_currency = 'UGX'

    try:
        if hasattr(value, 'currency'):
            code = value.currency or ''
        else:
            code = str(value or '').upper().strip()
        return bool(code) and code != school_currency
    except Exception:
        return False


@register.filter
def format_with_rate(value, payment_or_rate):
    """
    Format an amount showing both original currency and school currency equivalent.

    Useful for compact displays in tables or sidebars.

    Usage:
        {{ payment.amount|format_with_rate:payment }}

    Examples:
        Same currency:
            "SSD 1,315,000.00"
        Foreign currency (USD payment at SSD school):
            "USD 500.00 → SSD 657,500.00"

    Args:
        value:            The amount to format
        payment_or_rate:  A Payment instance (uses .currency, .exchange_rate,
                          .amount_in_school_currency) or a plain exchange rate
    """
    try:
        from core.models import FinancialSettings
        school_currency = FinancialSettings.get_school_currency()
    except Exception:
        school_currency = 'UGX'

    try:
        if hasattr(payment_or_rate, 'currency'):
            pay_currency = payment_or_rate.currency or school_currency
            sc_amount    = getattr(payment_or_rate, 'amount_in_school_currency', None)
        else:
            pay_currency = school_currency
            sc_amount    = None

        primary = format_in_currency(value, pay_currency)

        if pay_currency != school_currency and sc_amount is not None:
            secondary = format_in_currency(sc_amount, school_currency)
            return f"{primary} → {secondary}"

        return primary

    except Exception:
        return format_currency(value)


# =============================================================================
# PERCENTAGE FORMATTING
# =============================================================================

@register.filter
def format_percentage(value, decimal_places=2):
    """
    Format a percentage value with proper decimal places.

    Usage:
        {{ rate|format_percentage }}
        {{ rate|format_percentage:3 }}
        {{ discount.percentage|format_percentage:1 }}

    Examples:
        12.5 → "12.50%"
        75   → "75.00%"
    """
    if value is None or value == '':
        return f"0.{'0' * int(decimal_places)}%"

    try:
        try:
            decimal_places = int(decimal_places)
        except (ValueError, TypeError):
            decimal_places = 2

        if isinstance(value, Decimal):
            rate = value
        elif isinstance(value, (int, float)):
            rate = Decimal(str(value))
        elif isinstance(value, str):
            value = value.strip().replace('%', '').replace(',', '')
            if not value:
                return f"0.{'0' * decimal_places}%"
            rate = Decimal(value)
        else:
            rate = Decimal(str(value))

        return f"{rate:.{decimal_places}f}%"

    except (ValueError, TypeError, InvalidOperation) as e:
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
        {{ discount_rate|percentage }}  → "15.00%"
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
        {{ gpa|format_decimal:3 }}

    Examples:
        1500000.5 → "1,500,000.50"
        3.14159   → "3.14"
    """
    if value is None:
        value = 0
    try:
        decimal_places = int(decimal_places)
        amt = Decimal(str(value))
        return f"{amt:,.{decimal_places}f}"
    except (ValueError, TypeError, InvalidOperation):
        return f"0.{'0' * int(decimal_places)}"


@register.filter
def format_number(value):
    """
    Format a number with thousand separators (no decimals).

    Usage:
        {{ student_count|format_number }}  → "1,500"
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

    Returns dict with: code, decimal_places, position, use_separator
    """
    try:
        from core.models import FinancialSettings
        settings = FinancialSettings.get_instance()
        if settings:
            return {
                'code':           settings.school_currency,
                'decimal_places': settings.decimal_places,
                'position':       settings.currency_position,
                'use_separator':  settings.use_thousand_separator,
            }
    except Exception as e:
        logger.warning(f"Could not get currency info: {e}")

    return {
        'code':           'UGX',
        'decimal_places': 2,
        'position':       'BEFORE',
        'use_separator':  True,
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

    Example:
        {{ 500000|multiply_money:3 }}  → "UGX 1,500,000.00"
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
        {{ tuition|add_money:boarding_fee }}  → "UGX 2,000,000.00"
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
        {{ invoice.total_amount|subtract_money:invoice.paid_amount }}
        → "UGX 500,000.00" (balance remaining)
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
        {{ annual_fee|divide_money:3 }}  → "UGX 500,000.00"
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
        paid=750000, total=1000000 → "75.00%"
    """
    if value is None or total is None:
        return "0.00%"
    try:
        value_decimal = Decimal(str(value))
        total_decimal = Decimal(str(total or 1))
        if total_decimal == 0:
            return "0.00%"
        pct = (value_decimal / total_decimal) * 100
        return f"{pct:.2f}%"
    except (ValueError, TypeError, InvalidOperation, ZeroDivisionError):
        return "0.00%"


@register.filter
def apply_percentage(value, percentage):
    """
    Calculate percentage of a value and format as money.

    Usage:
        {{ total|apply_percentage:discount_rate }}

    Example:
        {{ 1000000|apply_percentage:10 }}  → "UGX 100,000.00"
    """
    if value is None or percentage is None:
        return format_currency(0)
    try:
        result = (Decimal(str(value)) * Decimal(str(percentage))) / 100
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

    Returns:
        'text-danger'  — balance > 0 (owes money)
        'text-success' — balance < 0 (credit balance)
        'text-muted'   — balance = 0 (fully paid)

    Usage:
        <span class="{{ invoice.balance|balance_color_class }}">
            {{ invoice.balance|money }}
        </span>
    """
    if balance is None:
        return 'text-muted'
    try:
        b = Decimal(str(balance))
        if b > 0:
            return 'text-danger'
        elif b < 0:
            return 'text-success'
        return 'text-muted'
    except (ValueError, TypeError, InvalidOperation):
        return 'text-muted'


@register.filter
def payment_status_badge(status):
    """
    Return Bootstrap badge class based on payment/invoice status.

    Usage:
        <span class="badge {{ invoice.status|payment_status_badge }}">
            {{ invoice.get_status_display }}
        </span>
    """
    status_map = {
        'PAID':      'badge-success',
        'PARTIAL':   'badge-warning',
        'PENDING':   'badge-info',
        'OVERDUE':   'badge-danger',
        'CANCELLED': 'badge-secondary',
        'DRAFT':     'badge-light',
        'VOID':      'badge-dark',
    }
    return status_map.get(str(status).upper(), 'badge-secondary')


@register.filter
def abs_money(value):
    """
    Return absolute value of money amount, formatted with school currency.

    Usage:
        {{ balance|abs_money }}

    Example:
        balance = -50000  →  "UGX 50,000.00"
    """
    if value is None:
        return format_currency(0)
    try:
        return format_currency(abs(Decimal(str(value))))
    except (ValueError, TypeError, InvalidOperation):
        return format_currency(0)


# =============================================================================
# COMPARISON FILTERS
# =============================================================================

@register.filter
def is_positive(value):
    """True if value > 0."""
    if value is None:
        return False
    try:
        return Decimal(str(value)) > 0
    except (ValueError, TypeError, InvalidOperation):
        return False


@register.filter
def is_negative(value):
    """True if value < 0."""
    if value is None:
        return False
    try:
        return Decimal(str(value)) < 0
    except (ValueError, TypeError, InvalidOperation):
        return False


@register.filter
def is_zero(value):
    """True if value == 0."""
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
    """
    from core.utils import format_money
    return format_money(value, include_symbol=False).rjust(20)


@register.filter
def format_with_sign(value):
    """
    Format money with explicit + or - sign.

    Usage:
        {{ change_amount|format_with_sign }}

    Examples:
        +50000 → "+UGX 50,000.00"
        -25000 → "-UGX 25,000.00"
        0      → "UGX 0.00"
    """
    if value is None:
        return format_currency(0)
    try:
        amt = Decimal(str(value))
        formatted = format_currency(abs(amt))
        if amt > 0:
            return f"+{formatted}"
        elif amt < 0:
            return f"-{formatted}"
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
        1500      → "1.5K"
        1500000   → "1.5M"
        1500000000→ "1.5B"
        500       → "500"
    """
    if value is None:
        return "0"
    try:
        num     = Decimal(str(value))
        abs_num = abs(num)

        if abs_num >= 1_000_000_000:
            formatted, suffix = num / Decimal('1000000000'), 'B'
        elif abs_num >= 1_000_000:
            formatted, suffix = num / Decimal('1000000'), 'M'
        elif abs_num >= 1_000:
            formatted, suffix = num / Decimal('1000'), 'K'
        else:
            return f"{int(num):,}"

        return f"{f'{formatted:.1f}'.rstrip('0').rstrip('.')}{suffix}"
    except (ValueError, TypeError, InvalidOperation):
        return "0"


@register.filter
def money_short(value):
    """
    Format large numbers in short form WITH school currency symbol (K, M, B).

    Usage:
        {{ stats.total_revenue|money_short }}

    Examples:
        1500000 → "UGX 1.5M"
        1500    → "UGX 1.5K"
    """
    from core.utils import get_school_currency
    currency_code = get_school_currency()

    if value is None:
        return f"{currency_code} 0"
    try:
        num     = Decimal(str(value))
        abs_num = abs(num)

        if abs_num >= 1_000_000_000:
            formatted, suffix = num / Decimal('1000000000'), 'B'
        elif abs_num >= 1_000_000:
            formatted, suffix = num / Decimal('1000000'), 'M'
        elif abs_num >= 1_000:
            formatted, suffix = num / Decimal('1000'), 'K'
        else:
            return f"{currency_code} {int(num):,}"

        return f"{currency_code} {f'{formatted:.1f}'.rstrip('0').rstrip('.')}{suffix}"
    except (ValueError, TypeError, InvalidOperation):
        return f"{currency_code} 0"


@register.filter
def abs_value(value):
    """
    Return absolute numeric value (not formatted).

    Usage:
        {% widthratio balance|abs_value 1 credit_limit as utilization %}

    Note: Returns a number, not a formatted string. Use abs_money for display.
    """
    if value is None:
        return 0
    try:
        return abs(Decimal(str(value)))
    except (ValueError, TypeError, InvalidOperation):
        return 0