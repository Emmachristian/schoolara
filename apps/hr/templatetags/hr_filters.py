# hr/templatetags/hr_filters.py 

from django import template

register = template.Library()

@register.filter
def sum_field(queryset, field_name):
    """
    Sum a specific field across a queryset.
    
    Usage: {{ payroll.allowances.all|sum_field:"amount" }}
    """
    try:
        return sum(getattr(item, field_name, 0) for item in queryset)
    except (TypeError, AttributeError):
        return 0