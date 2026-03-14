from django import template
from decimal import Decimal

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Retrieve a value from a dict by key. Usage: {{ my_dict|get_item:key_var }}"""
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None


@register.filter
def mul(value, arg):
    """Multiply two values"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def div(value, arg):
    """Divide two values"""
    try:
        return float(value) / float(arg) if float(arg) != 0 else 0
    except (ValueError, TypeError):
        return 0


@register.filter
def subtract(value, arg):
    """Subtract arg from value"""
    try:
        if isinstance(value, Decimal) or isinstance(arg, Decimal):
            return Decimal(str(value)) - Decimal(str(arg))
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def add_values(value, arg):
    """Add two values (alternative to built-in add for numbers)"""
    try:
        if isinstance(value, Decimal) or isinstance(arg, Decimal):
            return Decimal(str(value)) + Decimal(str(arg))
        return float(value) + float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def percentage(value, total):
    """Calculate percentage: (value / total) * 100"""
    try:
        total_float = float(total)
        if total_float == 0:
            return 0
        return (float(value) / total_float) * 100
    except (ValueError, TypeError):
        return 0


@register.filter
def abs_value(value):
    """Return absolute value"""
    try:
        return abs(float(value))
    except (ValueError, TypeError):
        return 0


@register.filter
def money_short(value):
    """
    Format money in short form:
    - 1,234 -> UGX 1.2K
    - 1,234,567 -> UGX 1.2M
    - 1,234,567,890 -> UGX 1.2B
    """
    try:
        value = Decimal(str(value)) if value else Decimal('0')

        from core.models import SchoolConfiguration
        try:
            school_config = SchoolConfiguration.get_current_config()
            currency = school_config.currency
        except Exception:
            currency = 'UGX'

        abs_val = abs(value)

        if abs_val >= 1_000_000_000:
            return f"{currency} {abs_val / 1_000_000_000:.1f}B"
        elif abs_val >= 1_000_000:
            return f"{currency} {abs_val / 1_000_000:.1f}M"
        elif abs_val >= 1_000:
            return f"{currency} {abs_val / 1_000:.1f}K"
        else:
            from django.contrib.humanize.templatetags.humanize import intcomma
            return f"{currency} {intcomma(int(value))}"
    except Exception:
        return "UGX 0"