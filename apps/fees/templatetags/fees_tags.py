# fees/templatetags/fees_tags.py
"""
Custom template tags and filters for the fees app.
"""

from django import template

register = template.Library()


@register.filter
def get_structure_type_display(value):
    """
    Get display value for structure_type field.
    
    Usage in template:
        {{ basic_data.structure_type|get_structure_type_display }}
    """
    STRUCTURE_TYPE_CHOICES = {
        'STANDARD': 'Standard Structure',
        'DAY_SCHOLAR': 'Day Scholar Structure',
        'BOARDER': 'Boarder Structure',
        'WEEKLY_BOARDER': 'Weekly Boarder Structure',
        'FULL_BOARDER': 'Full Boarder Structure',
        'FLEXI_BOARDER': 'Flexible Boarder Structure',
        'SCHOLARSHIP': 'Scholarship Structure',
        'CUSTOM': 'Custom Structure',
        'STAFF_CHILD': 'Staff Child Structure',
        'SIBLING_DISCOUNT': 'Sibling Discount Structure',
        'NEED_BASED': 'Need-Based Structure',
        'MERIT_BASED': 'Merit-Based Structure',
    }
    
    return STRUCTURE_TYPE_CHOICES.get(value, value)


@register.filter
def get_billing_frequency_display(value):
    """
    Get display value for billing_frequency field.
    
    Usage in template:
        {{ basic_data.billing_frequency|get_billing_frequency_display }}
    """
    BILLING_FREQUENCY_CHOICES = {
        'ONCE': 'Bill Once (Full Amount)',
        'PER_PERIOD': 'Bill Per Fiscal Period',
        'SPLIT_CUSTOM': 'Custom Split Across Periods',
        'ON_ENROLLMENT': 'Bill on Student Enrollment',
    }
    
    return BILLING_FREQUENCY_CHOICES.get(value, value)


@register.filter
def get_boarding_type_display(value):
    """
    Get display value for boarding_type_filter field.
    
    Usage in template:
        {{ basic_data.boarding_type_filter|get_boarding_type_display }}
    """
    BOARDING_TYPE_CHOICES = {
        'ALL': 'All Students',
        'DAY_ONLY': 'Day Scholars Only',
        'BOARDER_ONLY': 'Boarders Only',
        'FULL_BOARDER': 'Full Boarders Only',
        'WEEKLY_BOARDER': 'Weekly Boarders Only',
        'FLEXI_BOARDER': 'Flexible Boarders Only',
    }
    
    return BOARDING_TYPE_CHOICES.get(value, value)


@register.filter
def get_student_type_display(value):
    """
    Get display value for student_type_filter field.
    
    Usage in template:
        {{ basic_data.student_type_filter|get_student_type_display }}
    """
    STUDENT_TYPE_CHOICES = {
        'ALL': 'All Students',
        'NEW_ONLY': 'New Students Only',
        'CONTINUING_ONLY': 'Continuing Students Only',
        'SCHOLARSHIP_ONLY': 'Scholarship Students Only',
    }
    
    return STUDENT_TYPE_CHOICES.get(value, value)