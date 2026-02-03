# utils/templatetags/custom_filters.py

from django import template
from decimal import Decimal

register = template.Library()

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
        # Handle Decimal types
        if isinstance(value, Decimal) or isinstance(arg, Decimal):
            return Decimal(str(value)) - Decimal(str(arg))
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def add_values(value, arg):
    """Add two values (alternative to built-in add for numbers)"""
    try:
        # Handle Decimal types
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
        
        # Get school config for currency
        from core.models import SchoolConfiguration
        try:
            school_config = SchoolConfiguration.get_current_config()
            currency = school_config.currency
        except:
            currency = 'UGX'
        
        abs_value = abs(value)
        
        if abs_value >= 1_000_000_000:  # Billions
            short_value = abs_value / 1_000_000_000
            return f"{currency} {short_value:.1f}B"
        elif abs_value >= 1_000_000:  # Millions
            short_value = abs_value / 1_000_000
            return f"{currency} {short_value:.1f}M"
        elif abs_value >= 1_000:  # Thousands
            short_value = abs_value / 1_000
            return f"{currency} {short_value:.1f}K"
        else:
            # Use humanize for small numbers
            from django.contrib.humanize.templatetags.humanize import intcomma
            return f"{currency} {intcomma(int(value))}"
    except:
        return f"{currency} 0"