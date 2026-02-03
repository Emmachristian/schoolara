# exams/templatetags/exam_filters.py

from django import template

register = template.Library()

@register.filter
def sum_attr(queryset, attr_name):
    """Sum a specific attribute across all items in queryset"""
    return sum(getattr(item, attr_name, 0) for item in queryset)

@register.filter
def subtract(value, arg):
    """Subtract arg from value"""
    try:
        return int(value) - int(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def multiply_float(value, arg):
    """Multiply value by arg (for float calculations)"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def subtract_float(value, arg):
    """Subtract arg from value (for float calculations)"""
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return 0
    
@register.filter
def get_item(dictionary, key):
    """
    Get an item from a dictionary.
    Usage: {{ my_dict|get_item:key }}
    """
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None

@register.filter
def dict_length(dictionary, key):
    """
    Get the length of a dictionary item.
    Usage: {{ my_dict|dict_length:key }}
    """
    if isinstance(dictionary, dict):
        item = dictionary.get(key)
        if item:
            try:
                return len(item)
            except TypeError:
                return 0
    return 0