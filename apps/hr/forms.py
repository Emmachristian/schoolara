# hr/forms.py - PART 1 (Filter Forms through Attendance Form)

"""
Human Resources forms with timezone support.
Uses utils/forms for consistent behavior across the application.
"""

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django_countries import countries
from decimal import Decimal
from datetime import date, timedelta
import re
import logging

# Import base form utilities with timezone support ⭐
from utils.forms import (
    BootstrapFormMixin,
    DateRangeFormMixin,
    RequiredFieldsMixin,
    MoneyFieldsMixin,
    BaseFilterForm,
    DateRangeFilterForm,
    AmountRangeFilterForm,
    DatePickerInput,
    DateTimePickerInput,
    PhoneInput,
    MoneyField,
    PercentageField,
    validate_age,  # ⭐ Uses school timezone
    validate_phone_number,
    validate_future_date,  # ⭐ Uses school timezone
    validate_past_date,  # ⭐ Uses school timezone
    validate_date_not_before,  # ⭐ Uses school timezone
    validate_positive_amount,
)

from .models import (
    Department, Designation, Contract, 
    Staff, StaffDesignation, Teacher,
    Attendance, Payroll, PayrollAllowance,
    PayrollDeduction, PayrollBonus
)
from academics.models import AcademicLevel, Subject, Class

logger = logging.getLogger(__name__)


# =============================================================================
# DEPARTMENT FILTER FORMS
# =============================================================================

class DepartmentFilterForm(BaseFilterForm):
    """Filter form for department search"""
    
    department_type = forms.ChoiceField(
        label=_('Department Type'),
        choices=[('', _('All Types'))] + list(Department.DEPARTMENT_TYPES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    is_academic = forms.NullBooleanField(
        label=_('Academic'),
        required=False,
        widget=forms.Select(
            choices=[('', _('All')), ('true', _('Academic')), ('false', _('Non-Academic'))],
            attrs={'class': 'form-select'}
        )
    )
    
    is_active = forms.NullBooleanField(
        label=_('Active Status'),
        required=False,
        widget=forms.Select(
            choices=[('', _('All')), ('true', _('Active')), ('false', _('Inactive'))],
            attrs={'class': 'form-select'}
        )
    )


# =============================================================================
# DESIGNATION FILTER FORMS
# =============================================================================

class DesignationFilterForm(BaseFilterForm):
    """Filter form for designation search"""
    
    department = forms.ModelChoiceField(
        label=_('Department'),
        queryset=None,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    is_teaching = forms.NullBooleanField(
        label=_('Teaching Position'),
        required=False,
        widget=forms.Select(
            choices=[('', _('All')), ('true', _('Teaching')), ('false', _('Non-Teaching'))],
            attrs={'class': 'form-select'}
        )
    )
    
    is_management = forms.NullBooleanField(
        label=_('Management Position'),
        required=False,
        widget=forms.Select(
            choices=[('', _('All')), ('true', _('Management')), ('false', _('Non-Management'))],
            attrs={'class': 'form-select'}
        )
    )
    
    is_active = forms.NullBooleanField(
        label=_('Active Status'),
        required=False,
        widget=forms.Select(
            choices=[('', _('All')), ('true', _('Active')), ('false', _('Inactive'))],
            attrs={'class': 'form-select'}
        )
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['department'].queryset = Department.objects.filter(
            is_active=True
        ).order_by('name')


# =============================================================================
# STAFF FILTER FORMS
# =============================================================================

class StaffFilterForm(DateRangeFilterForm):
    """
    Filter form for staff search.
    All date validations use school timezone.
    """
    
    primary_department = forms.ModelChoiceField(
        label=_('Department'),
        queryset=None,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    employment_status = forms.ChoiceField(
        label=_('Employment Status'),
        choices=[('', _('All Statuses'))] + list(Staff.EMPLOYMENT_STATUS_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    gender = forms.ChoiceField(
        label=_('Gender'),
        choices=[('', _('All'))] + list(Staff.GENDER_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    is_active = forms.NullBooleanField(
        label=_('Active Status'),
        required=False,
        widget=forms.Select(
            choices=[('', _('All')), ('true', _('Active')), ('false', _('Inactive'))],
            attrs={'class': 'form-select'}
        )
    )
    
    # Override date fields for joining date range
    date_from = forms.DateField(
        label=_('Joined From'),
        required=False,
        widget=DatePickerInput()
    )
    
    date_to = forms.DateField(
        label=_('Joined To'),
        required=False,
        widget=DatePickerInput()
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set department queryset
        try:
            self.fields['primary_department'].queryset = Department.objects.filter(
                is_active=True
            ).order_by('name')
        except Exception as e:
            logger.error(f"Error setting department queryset: {e}")
            self.fields['primary_department'].queryset = Department.objects.none()


class TeacherFilterForm(BaseFilterForm):
    """Filter form for teacher search"""
    
    primary_department = forms.ModelChoiceField(
        label=_('Department'),
        queryset=None,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    qualified_subject = forms.ModelChoiceField(
        label=_('Qualified Subject'),
        queryset=None,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    preferred_academic_level = forms.ModelChoiceField(
        label=_('Academic Level'),
        queryset=None,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    is_class_teacher = forms.NullBooleanField(
        label=_('Class Teacher'),
        required=False,
        widget=forms.Select(
            choices=[('', _('All')), ('true', _('Class Teachers')), ('false', _('Subject Teachers Only'))],
            attrs={'class': 'form-select'}
        )
    )
    
    can_teach_online = forms.NullBooleanField(
        label=_('Can Teach Online'),
        required=False,
        widget=forms.Select(
            choices=[('', _('All')), ('true', _('Yes')), ('false', _('No'))],
            attrs={'class': 'form-select'}
        )
    )
    
    digital_literacy_level = forms.ChoiceField(
        label=_('Digital Literacy'),
        choices=[('', _('All Levels'))] + [
            ('BASIC', _('Basic')),
            ('INTERMEDIATE', _('Intermediate')),
            ('ADVANCED', _('Advanced')),
            ('EXPERT', _('Expert')),
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    is_active = forms.NullBooleanField(
        label=_('Status'),
        required=False,
        widget=forms.Select(
            choices=[('', _('All')), ('true', _('Active Only')), ('false', _('Inactive Only'))],
            attrs={'class': 'form-select'}
        )
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
            self.fields['primary_department'].queryset = Department.objects.filter(
                is_active=True, is_academic=True
            ).order_by('name')
            
            self.fields['qualified_subject'].queryset = Subject.objects.filter(
                is_active=True
            ).order_by('name')
            
            self.fields['preferred_academic_level'].queryset = AcademicLevel.objects.filter(
                is_active=True
            ).order_by('order')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")


class AttendanceFilterForm(DateRangeFilterForm):
    """Filter form for attendance search"""
    
    staff = forms.ModelChoiceField(
        label=_('Staff Member'),
        queryset=None,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    department = forms.ModelChoiceField(
        label=_('Department'),
        queryset=None,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    status = forms.ChoiceField(
        label=_('Status'),
        choices=[('', _('All Statuses'))] + list(Attendance.STATUS_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    work_mode = forms.ChoiceField(
        label=_('Work Mode'),
        choices=[('', _('All Modes'))] + list(Attendance.WORK_MODE_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    # Override date fields
    date_from = forms.DateField(
        label=_('From Date'),
        required=False,
        widget=DatePickerInput()
    )
    
    date_to = forms.DateField(
        label=_('To Date'),
        required=False,
        widget=DatePickerInput()
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
            self.fields['staff'].queryset = Staff.objects.filter(
                is_active=True
            ).order_by('first_name', 'last_name')
            
            self.fields['department'].queryset = Department.objects.filter(
                is_active=True
            ).order_by('name')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")


class PayrollFilterForm(DateRangeFilterForm):
    """
    Filter form for payroll search.
    
    Supports filtering by:
    - Staff member
    - Fiscal period (accounting period)
    - Pay period dates (actual work period)
    - Payment dates
    - Pay frequency
    - Status (including reversed payrolls)
    """
    
    staff = forms.ModelChoiceField(
        label=_('Staff Member'),
        queryset=None,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    fiscal_period = forms.ModelChoiceField(  # ⭐ RENAMED from 'period'
        label=_('Fiscal Period'),
        queryset=None,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text=_('Accounting period (e.g., Term 1)')
    )
    
    fiscal_year = forms.ModelChoiceField(
        label=_('Fiscal Year'),
        queryset=None,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    pay_frequency = forms.ChoiceField(  # ⭐ NEW
        label=_('Pay Frequency'),
        choices=[('', _('All Frequencies'))] + list(Payroll.PAY_FREQUENCY_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    status = forms.ChoiceField(
        label=_('Status'),
        choices=[('', _('All Statuses'))] + list(Payroll.STATUS_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    payment_method = forms.ModelChoiceField(
        label=_('Payment Method'),
        queryset=None,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    # ⭐ NEW: Filter for reversed payrolls
    include_reversed = forms.BooleanField(
        label=_('Include Reversed Payrolls'),
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text=_('Show payrolls that have been reversed')
    )
    
    only_reversed = forms.BooleanField(
        label=_('Only Reversed Payrolls'),
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text=_('Show only reversed payrolls')
    )
    
    # ⭐ NEW: Proration filter
    only_prorated = forms.BooleanField(
        label=_('Only Prorated Payrolls'),
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text=_('Show only payrolls with prorated salaries')
    )
    
    # =========================================================================
    # DATE FILTERS - Multiple options for different use cases
    # =========================================================================
    
    # Payment date range (when salary was/will be paid)
    payment_date_from = forms.DateField(
        label=_('Payment From'),
        required=False,
        widget=DatePickerInput(),
        help_text=_('Filter by payment date')
    )
    
    payment_date_to = forms.DateField(
        label=_('Payment To'),
        required=False,
        widget=DatePickerInput()
    )
    
    # ⭐ NEW: Pay period date range (work period)
    pay_period_from = forms.DateField(
        label=_('Pay Period From'),
        required=False,
        widget=DatePickerInput(),
        help_text=_('Filter by pay period start date')
    )
    
    pay_period_to = forms.DateField(
        label=_('Pay Period To'),
        required=False,
        widget=DatePickerInput(),
        help_text=_('Filter by pay period end date')
    )
    
    # ⭐ NEW: Quick filters for common periods
    quick_filter = forms.ChoiceField(
        label=_('Quick Filter'),
        choices=[
            ('', _('Custom Range')),
            ('current_month', _('Current Month')),
            ('last_month', _('Last Month')),
            ('current_quarter', _('Current Quarter')),
            ('current_year', _('Current Year')),
            ('last_quarter', _('Last Quarter')),
            ('last_year', _('Last Year')),
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text=_('Quick date range filters')
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
            from core.models import FiscalPeriod, FiscalYear, PaymentMethod
            
            # Staff queryset - include inactive for historical searches
            self.fields['staff'].queryset = Staff.objects.all().order_by(
                'first_name', 'last_name'
            )
            
            # Fiscal period - show all (including closed) for historical searches
            self.fields['fiscal_period'].queryset = FiscalPeriod.objects.all().order_by(
                '-start_date'
            )
            
            # Fiscal year - show all
            self.fields['fiscal_year'].queryset = FiscalYear.objects.all().order_by(
                '-start_date'
            )
            
            # Payment methods - active only
            self.fields['payment_method'].queryset = PaymentMethod.objects.filter(
                is_active=True
            ).order_by('name')
            
        except Exception as e:
            logger.error(f"Error setting querysets in PayrollFilterForm: {e}")
    
    def clean(self):
        """Apply quick filters and validate date ranges"""
        cleaned_data = super().clean()
        
        quick_filter = cleaned_data.get('quick_filter')
        
        # ⭐ Apply quick filters using school timezone
        if quick_filter:
            from core.utils import get_school_today
            from datetime import timedelta
            from calendar import monthrange
            
            today = get_school_today()
            
            if quick_filter == 'current_month':
                first_day = today.replace(day=1)
                last_day_num = monthrange(today.year, today.month)[1]
                last_day = today.replace(day=last_day_num)
                
                cleaned_data['pay_period_from'] = first_day
                cleaned_data['pay_period_to'] = last_day
            
            elif quick_filter == 'last_month':
                # Get first day of current month, then go back one day
                first_of_current = today.replace(day=1)
                last_of_previous = first_of_current - timedelta(days=1)
                first_of_previous = last_of_previous.replace(day=1)
                
                cleaned_data['pay_period_from'] = first_of_previous
                cleaned_data['pay_period_to'] = last_of_previous
            
            elif quick_filter == 'current_quarter':
                # Calculate current quarter
                quarter = (today.month - 1) // 3 + 1
                first_month = (quarter - 1) * 3 + 1
                
                first_day = today.replace(month=first_month, day=1)
                
                # Last day of quarter (3 months later)
                if first_month + 2 <= 12:
                    last_month = first_month + 2
                    last_year = today.year
                else:
                    last_month = (first_month + 2) % 12
                    last_year = today.year + 1
                
                last_day_num = monthrange(last_year, last_month)[1]
                last_day = today.replace(year=last_year, month=last_month, day=last_day_num)
                
                cleaned_data['pay_period_from'] = first_day
                cleaned_data['pay_period_to'] = last_day
            
            elif quick_filter == 'current_year':
                cleaned_data['pay_period_from'] = today.replace(month=1, day=1)
                cleaned_data['pay_period_to'] = today.replace(month=12, day=31)
            
            elif quick_filter == 'last_quarter':
                # Calculate previous quarter
                current_quarter = (today.month - 1) // 3 + 1
                if current_quarter == 1:
                    # Previous quarter is Q4 of last year
                    first_month = 10
                    year = today.year - 1
                else:
                    first_month = ((current_quarter - 2) * 3) + 1
                    year = today.year
                
                first_day = today.replace(year=year, month=first_month, day=1)
                
                last_month = first_month + 2
                last_day_num = monthrange(year, last_month)[1]
                last_day = today.replace(year=year, month=last_month, day=last_day_num)
                
                cleaned_data['pay_period_from'] = first_day
                cleaned_data['pay_period_to'] = last_day
            
            elif quick_filter == 'last_year':
                last_year = today.year - 1
                cleaned_data['pay_period_from'] = today.replace(year=last_year, month=1, day=1)
                cleaned_data['pay_period_to'] = today.replace(year=last_year, month=12, day=31)
        
        # ⭐ Validate date ranges
        payment_from = cleaned_data.get('payment_date_from')
        payment_to = cleaned_data.get('payment_date_to')
        
        if payment_from and payment_to:
            if payment_to < payment_from:
                raise ValidationError({
                    'payment_date_to': _('Payment "to" date cannot be before "from" date')
                })
        
        pay_period_from = cleaned_data.get('pay_period_from')
        pay_period_to = cleaned_data.get('pay_period_to')
        
        if pay_period_from and pay_period_to:
            if pay_period_to < pay_period_from:
                raise ValidationError({
                    'pay_period_to': _('Pay period "to" date cannot be before "from" date')
                })
        
        # ⭐ Validate reversed filter logic
        include_reversed = cleaned_data.get('include_reversed')
        only_reversed = cleaned_data.get('only_reversed')
        
        if only_reversed and include_reversed:
            # If only_reversed is True, include_reversed is redundant
            cleaned_data['include_reversed'] = False
        
        return cleaned_data
    
    def apply_filters(self, queryset):
        """
        Apply all filters to a payroll queryset.
        
        Usage:
            form = PayrollFilterForm(request.GET)
            if form.is_valid():
                payrolls = form.apply_filters(Payroll.objects.all())
        """
        if not self.is_valid():
            return queryset
        
        data = self.cleaned_data
        
        # Staff filter
        if data.get('staff'):
            queryset = queryset.filter(staff=data['staff'])
        
        # Fiscal period filter
        if data.get('fiscal_period'):
            queryset = queryset.filter(fiscal_period=data['fiscal_period'])
        
        # Fiscal year filter
        if data.get('fiscal_year'):
            queryset = queryset.filter(fiscal_year=data['fiscal_year'])
        
        # Pay frequency filter
        if data.get('pay_frequency'):
            queryset = queryset.filter(pay_frequency=data['pay_frequency'])
        
        # Status filter
        if data.get('status'):
            queryset = queryset.filter(status=data['status'])
        
        # Payment method filter
        if data.get('payment_method'):
            queryset = queryset.filter(payment_method=data['payment_method'])
        
        # Reversed payroll filters
        only_reversed = data.get('only_reversed')
        include_reversed = data.get('include_reversed')
        
        if only_reversed:
            queryset = queryset.filter(reversed=True)
        elif not include_reversed:
            # By default, exclude reversed payrolls
            queryset = queryset.filter(reversed=False)
        # If include_reversed is True, no filter applied (show all)
        
        # Prorated filter
        if data.get('only_prorated'):
            queryset = queryset.filter(is_prorated=True)
        
        # Payment date range
        if data.get('payment_date_from'):
            queryset = queryset.filter(payment_date__gte=data['payment_date_from'])
        
        if data.get('payment_date_to'):
            queryset = queryset.filter(payment_date__lte=data['payment_date_to'])
        
        # Pay period date range
        if data.get('pay_period_from'):
            # Find payrolls where pay period overlaps with filter range
            queryset = queryset.filter(pay_period_end__gte=data['pay_period_from'])
        
        if data.get('pay_period_to'):
            queryset = queryset.filter(pay_period_start__lte=data['pay_period_to'])
        
        return queryset


class StaffDesignationFilterForm(BaseFilterForm):
    """Filter form for staff designation search"""
    
    staff = forms.ModelChoiceField(
        label=_('Staff Member'),
        queryset=None,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    designation = forms.ModelChoiceField(
        label=_('Designation'),
        queryset=None,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    department = forms.ModelChoiceField(
        label=_('Department'),
        queryset=None,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    is_primary = forms.NullBooleanField(
        label=_('Primary Designation'),
        required=False,
        widget=forms.Select(
            choices=[('', _('All')), ('true', _('Primary')), ('false', _('Additional'))],
            attrs={'class': 'form-select'}
        )
    )
    
    assignment_type = forms.ChoiceField(
        label=_('Assignment Type'),
        choices=[('', _('All Types'))] + list(StaffDesignation.ASSIGNMENT_TYPE_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    is_active = forms.NullBooleanField(
        label=_('Active Status'),
        required=False,
        widget=forms.Select(
            choices=[('', _('All')), ('true', _('Active')), ('false', _('Inactive'))],
            attrs={'class': 'form-select'}
        )
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
            self.fields['staff'].queryset = Staff.objects.filter(
                is_active=True
            ).order_by('first_name', 'last_name')
            
            self.fields['designation'].queryset = Designation.objects.filter(
                is_active=True
            ).order_by('name')
            
            self.fields['department'].queryset = Department.objects.filter(
                is_active=True
            ).order_by('name')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")


class ContractFilterForm(DateRangeFilterForm):
    """Filter form for contract search"""
    
    # Contract type filter
    contract_type = forms.ChoiceField(
        label=_('Contract Type'),
        choices=[('', _('All Types'))] + list(Contract.CONTRACT_TYPE_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    # Status filter
    status = forms.ChoiceField(
        label=_('Status'),
        choices=[('', _('All Statuses'))] + list(Contract.CONTRACT_STATUS_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    # Override date fields for start date range
    date_from = forms.DateField(
        label=_('Start From'),
        required=False,
        widget=DatePickerInput()
    )
    
    date_to = forms.DateField(
        label=_('Start To'),
        required=False,
        widget=DatePickerInput()
    )


# =============================================================================
# DEPARTMENT FORM
# =============================================================================

class DepartmentForm(BootstrapFormMixin, RequiredFieldsMixin, MoneyFieldsMixin, forms.ModelForm):
    """Form for creating/editing departments"""
    
    annual_budget = MoneyField(label=_('Annual Budget'), required=False)
    
    class Meta:
        model = Department
        fields = [
            'name', 'code', 'description', 'department_type', 'academic_subtype',
            'is_academic', 'parent_department', 'annual_budget',
            'phone', 'email', 'head_id', 'is_active', 'capacity', 'location', 
            'operating_hours'
        ]
        
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Department Name')
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('DEPT CODE (e.g., MATH, ENG)'),
                'maxlength': 10
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': _('Department description...')
            }),
            'department_type': forms.Select(attrs={'class': 'form-select'}),
            'academic_subtype': forms.Select(attrs={'class': 'form-select'}),
            'is_academic': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'parent_department': forms.Select(attrs={'class': 'form-select'}),
            'phone': PhoneInput(),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': _('department@school.com')
            }),
            'head_id': forms.TextInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'capacity': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': _('Staff capacity'),
                'min': 1
            }),
            'location': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Building/Location')
            }),
            'operating_hours': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': _('{"monday": "8:00-17:00", "tuesday": "8:00-17:00"}')
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Required fields
        self.fields['name'].required = True
        self.fields['code'].required = True
        self.fields['department_type'].required = True
        
        # Filter parent department to exclude self
        if self.instance.pk:
            self.fields['parent_department'].queryset = Department.objects.exclude(
                pk=self.instance.pk
            ).filter(is_active=True)
        else:
            self.fields['parent_department'].queryset = Department.objects.filter(
                is_active=True
            )
    
    def clean_code(self):
        """Validate department code"""
        code = self.cleaned_data.get('code', '').upper().strip()
        
        if not re.match(r'^[A-Z0-9_-]+$', code):
            raise ValidationError(
                _("Code must contain only uppercase letters, numbers, hyphens, and underscores.")
            )
        
        # Check uniqueness
        if self.instance.pk:
            if Department.objects.exclude(pk=self.instance.pk).filter(code=code).exists():
                raise ValidationError(_("A department with this code already exists."))
        else:
            if Department.objects.filter(code=code).exists():
                raise ValidationError(_("A department with this code already exists."))
        
        return code
    
    def clean(self):
        cleaned_data = super().clean()
        department_type = cleaned_data.get('department_type')
        academic_subtype = cleaned_data.get('academic_subtype')
        parent_department = cleaned_data.get('parent_department')
        
        # Validate academic subtype
        if department_type == 'ACADEMIC' and not academic_subtype:
            self.add_error(
                'academic_subtype', 
                _('Academic subtype is required for academic departments.')
            )
        
        # Prevent circular parent relationships
        if parent_department:
            if self.instance.pk and parent_department.pk == self.instance.pk:
                self.add_error(
                    'parent_department', 
                    _('A department cannot be its own parent.')
                )
        
        return cleaned_data


# =============================================================================
# DESIGNATION FORM
# =============================================================================

class DesignationForm(BootstrapFormMixin, RequiredFieldsMixin, MoneyFieldsMixin, forms.ModelForm):
    """Form for creating/editing designations"""
    
    min_salary = MoneyField(
        label=_("Minimum Salary (Reference)"),
        required=False,
        help_text=_("Reference minimum salary for this designation")
    )
    
    max_salary = MoneyField(
        label=_("Maximum Salary (Reference)"),
        required=False,
        help_text=_("Reference maximum salary for this designation")
    )
    
    class Meta:
        model = Designation
        fields = [
            'name', 'code', 'description', 'department',
            'is_teaching', 'is_management', 'reports_to', 'rank_order',
            'min_salary', 'max_salary',
            'required_qualifications', 'key_responsibilities', 'is_active'
        ]
        
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Designation Name (e.g., Senior Teacher)')
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('CODE (e.g., ST-01)'),
                'maxlength': 50
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': _('Designation description...')
            }),
            'department': forms.Select(attrs={'class': 'form-select'}),
            'is_teaching': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_management': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'reports_to': forms.Select(attrs={'class': 'form-select'}),
            'rank_order': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': _('0 (higher rank = lower number)'),
                'min': 0
            }),
            'required_qualifications': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': _('["Bachelor\'s Degree in Education", "Teaching License"]')
            }),
            'key_responsibilities': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': _('Key responsibilities...')
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Required fields
        self.fields['name'].required = True
        self.fields['code'].required = True
        self.fields['department'].required = True
        
        # Filter departments
        self.fields['department'].queryset = Department.objects.filter(is_active=True)
        
        # Filter reports_to to exclude self
        if self.instance.pk:
            self.fields['reports_to'].queryset = Designation.objects.exclude(
                pk=self.instance.pk
            ).filter(is_active=True)
        else:
            self.fields['reports_to'].queryset = Designation.objects.filter(is_active=True)
    
    def clean_code(self):
        """Validate designation code"""
        code = self.cleaned_data.get('code', '').upper().strip()
        
        if not re.match(r'^[A-Z0-9_-]+$', code):
            raise ValidationError(
                _("Code must contain only uppercase letters, numbers, hyphens, and underscores.")
            )
        
        # Check uniqueness
        if self.instance.pk:
            if Designation.objects.exclude(pk=self.instance.pk).filter(code=code).exists():
                raise ValidationError(_("A designation with this code already exists."))
        else:
            if Designation.objects.filter(code=code).exists():
                raise ValidationError(_("A designation with this code already exists."))
        
        return code
    
    def clean(self):
        cleaned_data = super().clean()
        min_salary = cleaned_data.get('min_salary')
        max_salary = cleaned_data.get('max_salary')
        
        # Validate salary range
        if min_salary and max_salary:
            if min_salary > max_salary:
                self.add_error(
                    'max_salary', 
                    _('Maximum salary must be greater than minimum salary.')
                )
        
        return cleaned_data


# =============================================================================
# CONTRACT FORM
# =============================================================================

class ContractForm(BootstrapFormMixin, RequiredFieldsMixin, MoneyFieldsMixin, forms.ModelForm):
    """
    Form for creating/editing staff contracts.
    Uses school timezone for all date validations. ⭐
    """
    
    basic_salary = MoneyField(
        label=_("Basic Salary"),
        help_text=_("Basic salary amount - interpreted based on salary_frequency")
    )
    
    class Meta:
        model = Contract
        fields = [
            'staff', 'contract_type', 'contract_number', 'status',
            'start_date', 'end_date', 'signed_date', 'renewal_due_date',
            'basic_salary', 'salary_frequency', 'working_hours_per_week',
            'probation_period_months', 'annual_leave_days',
            'job_title', 'job_description', 'reporting_to_id',
            'contract_document', 'auto_renew', 'renewal_period_months',
            'requires_renewal_approval',
            'termination_date', 'termination_reason', 'termination_notice_period_days',
            'termination_notes', 'benefits_package', 'special_terms', 'notes'
        ]
        
        widgets = {
            'staff': forms.Select(attrs={'class': 'form-select'}),
            'contract_type': forms.Select(attrs={'class': 'form-select'}),
            'contract_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Will be auto-generated'),
                'readonly': True,
                'style': 'background-color: #f8f9fa;'
            }),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'start_date': DatePickerInput(),
            'end_date': DatePickerInput(),
            'signed_date': DatePickerInput(),
            'renewal_due_date': DatePickerInput(),
            'termination_date': DatePickerInput(),
            'salary_frequency': forms.Select(attrs={'class': 'form-select'}),
            'working_hours_per_week': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'max': 168
            }),
            'probation_period_months': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'max': 12
            }),
            'annual_leave_days': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'max': 60
            }),
            'renewal_period_months': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'max': 120
            }),
            'termination_notice_period_days': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0
            }),
            'job_title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Job Title')
            }),
            'job_description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': _('Job description and responsibilities...')
            }),
            'reporting_to_id': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Staff ID of supervisor')
            }),
            'contract_document': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf,.doc,.docx'
            }),
            'auto_renew': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'requires_renewal_approval': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'termination_reason': forms.Select(attrs={'class': 'form-select'}),
            'termination_notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': _('Termination notes...')
            }),
            'benefits_package': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': _('{"health_insurance": true, "housing": 500000}')
            }),
            'special_terms': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': _('Special terms and conditions...')
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': _('Contract notes...')
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Required fields
        self.fields['staff'].required = True
        self.fields['contract_type'].required = True
        self.fields['start_date'].required = True
        self.fields['job_title'].required = True
        self.fields['basic_salary'].required = True
        
        # Filter staff to active only
        self.fields['staff'].queryset = Staff.objects.filter(is_active=True)
        
        # Auto-generate contract number for new contracts
        if not self.instance.pk and not self.is_bound:
            from .utils import generate_contract_number
            try:
                contract_number = generate_contract_number()
                self.fields['contract_number'].initial = contract_number
            except Exception as e:
                logger.error(f"Error generating contract number: {e}")
    
    def clean_start_date(self):
        """Validate start date using school timezone ⭐"""
        start_date = self.cleaned_data.get('start_date')
        if start_date:
            from core.utils import get_school_today
            from datetime import timedelta
            
            today = get_school_today()  # ⭐ USE SCHOOL TIMEZONE
            
            # Allow reasonable past dates (up to 10 years)
            if start_date < (today - timedelta(days=10*365)):
                raise ValidationError(
                    _("Start date seems too far in the past. Please verify.")
                )
        
        return start_date
    
    def clean_end_date(self):
        """Validate end date is after start date"""
        start_date = self.cleaned_data.get('start_date')
        end_date = self.cleaned_data.get('end_date')
        
        if start_date and end_date:
            if end_date <= start_date:
                raise ValidationError(_("End date must be after start date."))
        
        return end_date
    
    def clean_termination_date(self):
        """Validate termination date using school timezone ⭐"""
        start_date = self.cleaned_data.get('start_date')
        termination_date = self.cleaned_data.get('termination_date')
        
        if termination_date:
            if start_date and termination_date < start_date:
                raise ValidationError(
                    _("Termination date cannot be before contract start date.")
                )
        
        return termination_date
    
    def clean(self):
        cleaned_data = super().clean()
        contract_type = cleaned_data.get('contract_type')
        end_date = cleaned_data.get('end_date')
        status = cleaned_data.get('status')
        termination_date = cleaned_data.get('termination_date')
        termination_reason = cleaned_data.get('termination_reason')
        
        # Permanent contracts should not have end dates
        if contract_type == 'PERMANENT' and end_date:
            self.add_error(
                'end_date', 
                _('Permanent contracts should not have an end date.')
            )
        
        # Fixed term contracts must have end dates
        if contract_type in ['FIXED_TERM', 'PROBATION', 'TEMPORARY', 'SEASONAL', 'PROJECT_BASED']:
            if not end_date:
                self.add_error(
                    'end_date',
                    _(f'{dict(Contract.CONTRACT_TYPE_CHOICES)[contract_type]} must have an end date.')
                )
        
        # Validate termination fields
        if status == 'TERMINATED':
            if not termination_date:
                self.add_error(
                    'termination_date', 
                    _('Termination date is required for terminated contracts.')
                )
            if not termination_reason:
                self.add_error(
                    'termination_reason', 
                    _('Termination reason is required for terminated contracts.')
                )
        
        return cleaned_data


# =============================================================================
# ATTENDANCE FORM
# =============================================================================

class AttendanceForm(BootstrapFormMixin, RequiredFieldsMixin, forms.ModelForm):
    """
    Form for recording staff attendance.
    Uses school timezone for date/time validations. ⭐
    """
    
    class Meta:
        model = Attendance
        fields = [
            'staff', 'date', 'check_in', 'check_out', 'status',
            'work_hours', 'overtime_hours', 'work_location', 'work_mode', 'notes'
        ]
        
        widgets = {
            'staff': forms.Select(attrs={'class': 'form-select'}),
            'date': DatePickerInput(),
            'check_in': DateTimePickerInput(),
            'check_out': DateTimePickerInput(),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'work_hours': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'max': '24'
            }),
            'overtime_hours': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'work_location': forms.TextInput(attrs={'class': 'form-control'}),
            'work_mode': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set default date (school timezone) ⭐
        if not self.is_bound:
            from core.utils import get_school_today
            self.fields['date'].initial = get_school_today()
        
        # Filter active staff
        self.fields['staff'].queryset = Staff.objects.filter(is_active=True)
    
    def clean_date(self):
        """Validate attendance date using school timezone ⭐"""
        attendance_date = self.cleaned_data.get('date')
        if attendance_date:
            from core.utils import get_school_today
            
            today = get_school_today()  # ⭐ USE SCHOOL TIMEZONE
            
            # Don't allow future dates
            if attendance_date > today:
                raise ValidationError(_("Attendance date cannot be in the future."))
            
            # Don't allow too far in past (30 days)
            if attendance_date < (today - timedelta(days=30)):
                raise ValidationError(
                    _("Attendance date cannot be more than 30 days in the past.")
                )
        
        return attendance_date
    
    def clean(self):
        cleaned_data = super().clean()
        check_in = cleaned_data.get('check_in')
        check_out = cleaned_data.get('check_out')
        
        if check_in and check_out:
            if check_out <= check_in:
                raise ValidationError({
                    'check_out': _('Check-out time must be after check-in time.')
                })
        
        return cleaned_data
    
# =============================================================================
# PAYROLL FORMS
# =============================================================================

class PayrollForm(BootstrapFormMixin, RequiredFieldsMixin, MoneyFieldsMixin, forms.ModelForm):
    """
    Form for creating/editing payroll records.
    
    Features:
    - Uses school timezone and fiscal periods
    - Supports pay period tracking (multiple payrolls per fiscal period)
    - Auto-calculates gross pay, deductions, net pay
    - Validates against closed periods
    - Handles reversal restrictions
    """
    
    basic_salary = MoneyField(label=_("Basic Salary"))
    gross_pay = MoneyField(label=_("Gross Pay"), required=False)  # Auto-calculated
    total_deductions = MoneyField(label=_("Total Deductions"), required=False)  # Auto-calculated
    net_pay = MoneyField(label=_("Net Pay"), required=False)  # Auto-calculated
    
    class Meta:
        model = Payroll
        fields = [
            # Staff and period info
            'staff', 'fiscal_period', 'pay_frequency',
            # Pay period dates
            'pay_period_start', 'pay_period_end', 'payment_date',
            # Salary components
            'basic_salary', 'gross_pay', 'total_deductions', 'net_pay',
            # Working days (optional)
            'total_working_days', 'days_worked', 'is_prorated',
            # Payment details
            'payment_method', 'bank_account', 'payment_reference',
            # Status and notes
            'status', 'notes'
        ]
        
        widgets = {
            'staff': forms.Select(attrs={'class': 'form-select'}),
            'fiscal_period': forms.Select(attrs={'class': 'form-select'}),
            'pay_frequency': forms.Select(attrs={'class': 'form-select'}),
            
            # Date pickers for pay period
            'pay_period_start': DatePickerInput(),
            'pay_period_end': DatePickerInput(),
            'payment_date': DatePickerInput(),
            
            # Working days
            'total_working_days': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': _('Total working days in period')
            }),
            'days_worked': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': _('Actual days worked')
            }),
            'is_prorated': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            
            # Payment details
            'payment_method': forms.Select(attrs={'class': 'form-select'}),
            'bank_account': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Bank account number for salary payment')
            }),
            'payment_reference': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Payment reference/transaction ID')
            }),
            
            # Status and notes
            'status': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': _('Additional notes about this payroll...')
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # =====================================================================
        # FILTER QUERYSETS
        # =====================================================================
        
        # Filter active staff only
        self.fields['staff'].queryset = Staff.objects.filter(
            is_active=True
        ).order_by('first_name', 'last_name')
        
        # Filter open fiscal periods only (can't create payroll in closed periods)
        from core.models import FiscalPeriod, PaymentMethod
        self.fields['fiscal_period'].queryset = FiscalPeriod.objects.filter(
            is_closed=False
        ).order_by('-start_date')
        
        self.fields['payment_method'].queryset = PaymentMethod.objects.filter(
            is_active=True
        ).order_by('name')
        
        # =====================================================================
        # SET DEFAULTS USING SCHOOL TIMEZONE ⭐
        # =====================================================================
        
        if not self.is_bound and not self.instance.pk:
            from core.utils import get_school_today
            from datetime import timedelta
            from calendar import monthrange
            
            today = get_school_today()
            
            # Default to current month
            first_day = today.replace(day=1)
            last_day_num = monthrange(today.year, today.month)[1]
            last_day = today.replace(day=last_day_num)
            
            self.fields['pay_period_start'].initial = first_day
            self.fields['pay_period_end'].initial = last_day
            self.fields['payment_date'].initial = last_day
            self.fields['pay_frequency'].initial = 'MONTHLY'
        
        # =====================================================================
        # DISABLE EDITING FOR REVERSED OR PAID PAYROLLS
        # =====================================================================
        
        if self.instance.pk:
            if self.instance.reversed:
                # Make all fields read-only for reversed payroll
                for field in self.fields:
                    self.fields[field].disabled = True
                    self.fields[field].help_text = _("Cannot edit reversed payroll")
            
            elif self.instance.status == 'PAID':
                # Restrict editing for paid payroll (only notes can be updated)
                restricted_fields = [
                    'staff', 'fiscal_period', 'pay_period_start', 'pay_period_end',
                    'basic_salary', 'gross_pay', 'total_deductions', 'net_pay',
                    'payment_date', 'total_working_days', 'days_worked'
                ]
                for field in restricted_fields:
                    if field in self.fields:
                        self.fields[field].disabled = True
                        self.fields[field].help_text = _("Cannot modify paid payroll")
        
        # =====================================================================
        # MAKE CALCULATED FIELDS READ-ONLY
        # =====================================================================
        
        self.fields['gross_pay'].widget.attrs['readonly'] = True
        self.fields['total_deductions'].widget.attrs['readonly'] = True
        self.fields['net_pay'].widget.attrs['readonly'] = True
        
        # =====================================================================
        # ADD HELPFUL TOOLTIPS
        # =====================================================================
        
        self.fields['fiscal_period'].help_text = _(
            "Accounting period (e.g., Term 1). Multiple payrolls can exist in one fiscal period."
        )
        self.fields['pay_frequency'].help_text = _(
            "How often this employee is paid (usually monthly for schools)"
        )
        self.fields['pay_period_start'].help_text = _(
            "Start of the period being paid (e.g., Jan 1 for January salary)"
        )
        self.fields['pay_period_end'].help_text = _(
            "End of the period being paid (e.g., Jan 31 for January salary)"
        )
        self.fields['payment_date'].help_text = _(
            "Date when salary will be/was actually paid"
        )
        self.fields['basic_salary'].help_text = _(
            "Base salary for this period (without allowances)"
        )
        self.fields['gross_pay'].help_text = _(
            "Calculated: Basic salary + allowances + bonuses"
        )
        self.fields['total_deductions'].help_text = _(
            "Calculated: All deductions (statutory + voluntary)"
        )
        self.fields['net_pay'].help_text = _(
            "Calculated: Gross pay - Total deductions"
        )
        self.fields['total_working_days'].help_text = _(
            "Total working days in this pay period (for proration)"
        )
        self.fields['days_worked'].help_text = _(
            "Actual days worked (leave blank for full period)"
        )
        self.fields['is_prorated'].help_text = _(
            "Check if salary should be prorated based on days worked"
        )
    
    def clean_pay_period_start(self):
        """Validate pay period start date"""
        pay_period_start = self.cleaned_data.get('pay_period_start')
        
        if pay_period_start:
            from core.utils import get_school_today
            today = get_school_today()
            
            # Allow reasonable past dates (up to 12 months)
            if pay_period_start < (today - timedelta(days=365)):
                raise ValidationError(
                    _("Pay period start seems too far in the past. "
                    "Please verify the date.")
                )
            
            # Allow some future dates (for advance payroll creation)
            if pay_period_start > (today + timedelta(days=90)):
                raise ValidationError(
                    _("Pay period start seems too far in the future. "
                    "Maximum 90 days allowed.")
                )
        
        return pay_period_start
    
    def clean_pay_period_end(self):
        """Validate pay period end date"""
        pay_period_end = self.cleaned_data.get('pay_period_end')
        
        if pay_period_end:
            from core.utils import get_school_today
            today = get_school_today()
            
            # Allow reasonable past/future dates
            if pay_period_end < (today - timedelta(days=365)):
                raise ValidationError(
                    _("Pay period end seems too far in the past.")
                )
            
            if pay_period_end > (today + timedelta(days=90)):
                raise ValidationError(
                    _("Pay period end seems too far in the future.")
                )
        
        return pay_period_end
    
    def clean_payment_date(self):
        """Validate payment date using school timezone ⭐"""
        payment_date = self.cleaned_data.get('payment_date')
        
        if payment_date:
            from core.utils import get_school_today
            today = get_school_today()  # ⭐ USE SCHOOL TIMEZONE
            
            # Allow reasonable past/future dates
            if payment_date < (today - timedelta(days=90)):
                raise ValidationError(
                    _("Payment date seems too far in the past. "
                    "Please verify the date or contact administrator.")
                )
            
            if payment_date > (today + timedelta(days=90)):
                raise ValidationError(
                    _("Payment date seems too far in the future. "
                    "Maximum 90 days allowed.")
                )
        
        return payment_date
    
    def clean_fiscal_period(self):
        """Validate fiscal period is not closed"""
        fiscal_period = self.cleaned_data.get('fiscal_period')
        
        if fiscal_period and hasattr(fiscal_period, 'is_closed'):
            if fiscal_period.is_closed:
                raise ValidationError(
                    _(f"Cannot create payroll in closed period: {fiscal_period.name}. "
                    "Please select an open fiscal period.")
                )
        
        return fiscal_period
    
    def clean(self):
        """Additional validation"""
        cleaned_data = super().clean()
        
        staff = cleaned_data.get('staff')
        fiscal_period = cleaned_data.get('fiscal_period')
        pay_period_start = cleaned_data.get('pay_period_start')
        pay_period_end = cleaned_data.get('pay_period_end')
        payment_date = cleaned_data.get('payment_date')
        
        # =====================================================================
        # PAY PERIOD VALIDATION
        # =====================================================================
        
        if pay_period_start and pay_period_end:
            if pay_period_end < pay_period_start:
                raise ValidationError({
                    'pay_period_end': _("Pay period end cannot be before start")
                })
        
        # =====================================================================
        # FISCAL PERIOD VALIDATION (All dates must be within fiscal period)
        # =====================================================================
        
        if fiscal_period and pay_period_start and pay_period_end:
            # Pay period must be within fiscal period
            if pay_period_start < fiscal_period.start_date:
                raise ValidationError({
                    'pay_period_start': _(
                        f"Pay period cannot start before fiscal period start date "
                        f"({fiscal_period.start_date})"
                    )
                })
            
            if pay_period_end > fiscal_period.end_date:
                raise ValidationError({
                    'pay_period_end': _(
                        f"Pay period cannot end after fiscal period end date "
                        f"({fiscal_period.end_date})"
                    )
                })
            
            # Payment date validation (with grace period)
            if payment_date:
                from datetime import timedelta
                
                if payment_date < fiscal_period.start_date:
                    raise ValidationError({
                        'payment_date': _(
                            f"Payment date cannot be before fiscal period start "
                            f"({fiscal_period.start_date})"
                        )
                    })
                
                # Calculate max allowed payment date (including grace period)
                max_allowed_date = fiscal_period.end_date
                if hasattr(fiscal_period, 'grace_period_days') and fiscal_period.grace_period_days > 0:
                    max_allowed_date = (
                        fiscal_period.end_date + 
                        timedelta(days=fiscal_period.grace_period_days)
                    )
                
                if payment_date > max_allowed_date:
                    grace_note = ""
                    if hasattr(fiscal_period, 'grace_period_days') and fiscal_period.grace_period_days > 0:
                        grace_note = f" (including {fiscal_period.grace_period_days} days grace period)"
                    
                    raise ValidationError({
                        'payment_date': _(
                            f"Payment date cannot be after fiscal period end date "
                            f"({fiscal_period.end_date}){grace_note}"
                        )
                    })
        
        # =====================================================================
        # CHECK FOR DUPLICATE PAYROLL
        # =====================================================================
        
        if staff and pay_period_start and pay_period_end:
            duplicate = Payroll.objects.filter(
                staff=staff,
                pay_period_start=pay_period_start,
                pay_period_end=pay_period_end,
                reversed=False  # Don't count reversed payrolls
            )
            
            # Exclude current instance if editing
            if self.instance.pk:
                duplicate = duplicate.exclude(pk=self.instance.pk)
            
            if duplicate.exists():
                existing = duplicate.first()
                raise ValidationError(
                    _(f"Payroll already exists for {staff.full_name()} "
                    f"for pay period {pay_period_start} to {pay_period_end}. "
                    f"Status: {existing.get_status_display()}. "
                    "Each staff member can only have one active payroll per pay period.")
                )
        
        # =====================================================================
        # WORKING DAYS VALIDATION
        # =====================================================================
        
        days_worked = cleaned_data.get('days_worked')
        total_working_days = cleaned_data.get('total_working_days')
        is_prorated = cleaned_data.get('is_prorated')
        
        if is_prorated:
            if not days_worked or not total_working_days:
                raise ValidationError({
                    'is_prorated': _(
                        "If salary is prorated, you must specify both "
                        "'Days Worked' and 'Total Working Days'"
                    )
                })
        
        if days_worked is not None and total_working_days is not None:
            if days_worked > total_working_days:
                raise ValidationError({
                    'days_worked': _("Days worked cannot exceed total working days")
                })
        
        # =====================================================================
        # AMOUNT VALIDATION
        # =====================================================================
        
        basic_salary = cleaned_data.get('basic_salary')
        gross_pay = cleaned_data.get('gross_pay')
        total_deductions = cleaned_data.get('total_deductions')
        net_pay = cleaned_data.get('net_pay')
        
        if all([basic_salary, gross_pay, total_deductions, net_pay]):
            # Gross pay should be >= basic salary
            if gross_pay < basic_salary:
                raise ValidationError({
                    'gross_pay': _("Gross pay cannot be less than basic salary")
                })
            
            # Net pay should equal gross pay minus deductions
            expected_net_pay = gross_pay - total_deductions
            if abs(net_pay - expected_net_pay) > Decimal('0.01'):  # Allow for rounding
                raise ValidationError({
                    'net_pay': _(f"Net pay should be {expected_net_pay:,.2f} "
                              f"(Gross pay - Total deductions)")
                })
        
        return cleaned_data


class PayrollReversalForm(BootstrapFormMixin, RequiredFieldsMixin, forms.Form):
    """
    Form for reversing a payroll.
    
    Used when payroll was created in error or with wrong amounts.
    Requires detailed reason and may require approval for paid payrolls.
    """
    
    reversal_reason = forms.CharField(
        label=_("Reversal Reason"),
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 4,
            'placeholder': _(
                'Provide detailed reason for reversal:\n'
                '- Was payroll calculated incorrectly?\n'
                '- Was it created for wrong employee?\n'
                '- Were wrong deductions applied?\n'
                '- Other specific details...'
            )
        }),
        help_text=_("Detailed explanation required for audit trail")
    )
    
    statutory_adjustments_notes = forms.CharField(
        label=_("Statutory Adjustments Notes"),
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': _(
                'For PAID payrolls only:\n'
                '- How will PAYE/tax be adjusted?\n'
                '- How will NSSF be handled?\n'
                '- Any other statutory implications...'
            )
        }),
        required=False,
        help_text=_("Required if payroll was already paid and had statutory deductions")
    )
    
    confirm_reversal = forms.BooleanField(
        label=_("I confirm this payroll should be reversed"),
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text=_("This action cannot be undone. Reversal will be logged in audit trail.")
    )
    
    def __init__(self, payroll, user, *args, **kwargs):
        self.payroll = payroll
        self.user = user
        super().__init__(*args, **kwargs)
        
        # Check if statutory adjustments required
        if payroll.status == 'PAID' and payroll.requires_statutory_adjustments():
            self.fields['statutory_adjustments_notes'].required = True
            self.fields['statutory_adjustments_notes'].help_text += (
                _(" (REQUIRED - This payroll has statutory deductions that were paid)")
            )
        else:
            # Hide statutory field if not needed
            if 'statutory_adjustments_notes' in self.fields:
                del self.fields['statutory_adjustments_notes']
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Validate payroll can be reversed
        can_reverse, reason = self.payroll.can_be_reversed()
        if not can_reverse:
            raise ValidationError(_(f"Cannot reverse this payroll: {reason}"))
        
        # Additional validation for paid payrolls
        if self.payroll.status == 'PAID':
            if not cleaned_data.get('statutory_adjustments_notes'):
                if self.payroll.requires_statutory_adjustments():
                    raise ValidationError({
                        'statutory_adjustments_notes': _(
                            "Required for paid payroll with statutory deductions. "
                            "Explain how tax/NSSF will be adjusted."
                        )
                    })
        
        return cleaned_data


class PayrollAllowanceForm(BootstrapFormMixin, RequiredFieldsMixin, MoneyFieldsMixin, forms.ModelForm):
    """Form for adding allowances to payroll"""
    
    amount = MoneyField(label=_("Amount"))
    
    class Meta:
        model = PayrollAllowance
        fields = [
            'allowance_type', 'description', 'amount', 'is_taxable',
            'is_recurring', 'reference_number'
        ]
        
        widgets = {
            'allowance_type': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('E.g., Housing allowance for January 2024')
            }),
            'is_taxable': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_recurring': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'reference_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Reference number (if applicable)')
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Add helpful help text
        self.fields['is_taxable'].help_text = _(
            "Check if this allowance should be included in taxable income"
        )
        self.fields['is_recurring'].help_text = _(
            "Check if this allowance recurs every pay period"
        )
        self.fields['reference_number'].help_text = _(
            "Policy reference, approval number, etc."
        )


class PayrollDeductionForm(BootstrapFormMixin, RequiredFieldsMixin, MoneyFieldsMixin, forms.ModelForm):
    """Form for adding deductions to payroll"""
    
    amount = MoneyField(label=_("Amount"))
    
    class Meta:
        model = PayrollDeduction
        fields = [
            'deduction_type', 'description', 'amount', 'is_pretax',
            'reference_number', 'is_recurring', 'loan_balance_remaining'
        ]
        
        widgets = {
            'deduction_type': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('E.g., PAYE for January 2024')
            }),
            'is_pretax': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'reference_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Reference number (if applicable)')
            }),
            'is_recurring': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'loan_balance_remaining': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': _('Remaining balance after this deduction')
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Add helpful help text
        self.fields['is_pretax'].help_text = _(
            "Check if this deduction is taken before calculating PAYE/tax"
        )
        self.fields['reference_number'].help_text = _(
            "E.g., loan number, NSSF reference, etc."
        )
        self.fields['is_recurring'].help_text = _(
            "Check if this deduction recurs every pay period"
        )
        self.fields['loan_balance_remaining'].help_text = _(
            "For loan deductions: remaining balance after this payment"
        )
        
        # Make loan_balance_remaining optional
        self.fields['loan_balance_remaining'].required = False


class PayrollBonusForm(BootstrapFormMixin, RequiredFieldsMixin, MoneyFieldsMixin, forms.ModelForm):
    """Form for adding bonuses to payroll"""
    
    amount = MoneyField(label=_("Amount"))
    
    class Meta:
        model = PayrollBonus
        fields = [
            'bonus_type', 'description', 'amount', 'is_taxable',
            'is_recurring', 'reference_number', 'overtime_hours', 'overtime_rate'
        ]
        
        widgets = {
            'bonus_type': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('E.g., Performance bonus for Q4 2023')
            }),
            'is_taxable': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_recurring': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'reference_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Reference number (if applicable)')
            }),
            'overtime_hours': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': _('Hours of overtime')
            }),
            'overtime_rate': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': _('Rate per hour')
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Add helpful help text
        self.fields['is_taxable'].help_text = _(
            "Most bonuses are taxable. Uncheck only if exempt by law."
        )
        self.fields['is_recurring'].help_text = _(
            "Check if this bonus recurs every pay period"
        )
        self.fields['reference_number'].help_text = _(
            "Approval number, performance review reference, etc."
        )
        self.fields['overtime_hours'].help_text = _(
            "For overtime bonuses: number of hours worked"
        )
        self.fields['overtime_rate'].help_text = _(
            "For overtime bonuses: hourly rate"
        )
        
        # Make optional fields truly optional
        self.fields['overtime_hours'].required = False
        self.fields['overtime_rate'].required = False
    
    def clean(self):
        """Validate overtime bonus calculations"""
        cleaned_data = super().clean()
        
        bonus_type = cleaned_data.get('bonus_type')
        amount = cleaned_data.get('amount')
        overtime_hours = cleaned_data.get('overtime_hours')
        overtime_rate = cleaned_data.get('overtime_rate')
        
        # If overtime bonus, validate hours and rate match amount
        if bonus_type == 'OVERTIME':
            if overtime_hours and overtime_rate:
                calculated_amount = overtime_hours * overtime_rate
                if abs(calculated_amount - amount) > Decimal('0.01'):
                    raise ValidationError({
                        'amount': _(
                            f"Amount ({amount}) doesn't match calculated overtime "
                            f"({calculated_amount} = {overtime_hours}h × {overtime_rate})"
                        )
                    })
        
        return cleaned_data


class BulkPayrollApprovalForm(BootstrapFormMixin, forms.Form):
    """
    Form for approving multiple payrolls at once.
    
    Used by HR Manager to approve entire month's payroll.
    """
    
    payroll_ids = forms.CharField(
        widget=forms.HiddenInput(),
        required=True
    )
    
    approval_notes = forms.CharField(
        label=_("Approval Notes"),
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': _('Any notes for this approval batch...')
        }),
        required=False
    )
    
    confirm_approval = forms.BooleanField(
        label=_("I confirm approval of all selected payrolls"),
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text=_("All selected payrolls will be marked as approved")
    )
    
    def clean_payroll_ids(self):
        """Validate and parse payroll IDs"""
        ids_string = self.cleaned_data.get('payroll_ids', '')
        
        try:
            payroll_ids = [int(id.strip()) for id in ids_string.split(',') if id.strip()]
        except ValueError:
            raise ValidationError(_("Invalid payroll IDs"))
        
        if not payroll_ids:
            raise ValidationError(_("No payrolls selected"))
        
        # Validate all payrolls exist and are in DRAFT status
        payrolls = Payroll.objects.filter(id__in=payroll_ids)
        
        if payrolls.count() != len(payroll_ids):
            raise ValidationError(_("Some selected payrolls do not exist"))
        
        non_draft = payrolls.exclude(status='DRAFT')
        if non_draft.exists():
            raise ValidationError(
                _(f"{non_draft.count()} payroll(s) are not in DRAFT status and cannot be approved")
            )
        
        reversed_payrolls = payrolls.filter(reversed=True)
        if reversed_payrolls.exists():
            raise ValidationError(
                _(f"{reversed_payrolls.count()} payroll(s) are reversed and cannot be approved")
            )
        
        return payroll_ids


class BulkPayrollPaymentForm(BootstrapFormMixin, RequiredFieldsMixin, forms.Form):
    """
    Form for marking multiple payrolls as paid.
    
    Used when processing payment batch (e.g., bank upload completed).
    """
    
    payroll_ids = forms.CharField(
        widget=forms.HiddenInput(),
        required=True
    )
    
    payment_date = forms.DateField(
        label=_("Payment Date"),
        widget=DatePickerInput(),
        help_text=_("Date when payments were actually disbursed")
    )
    
    payment_reference = forms.CharField(
        label=_("Payment Reference"),
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('E.g., BATCH-2024-01 or bank upload reference')
        }),
        help_text=_("Reference number for this payment batch")
    )
    
    payment_notes = forms.CharField(
        label=_("Payment Notes"),
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': _('Any notes about this payment batch...')
        }),
        required=False
    )
    
    confirm_payment = forms.BooleanField(
        label=_("I confirm all selected payrolls have been paid"),
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text=_("Money has been disbursed to all employees")
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set default payment date
        if not self.is_bound:
            from core.utils import get_school_today
            self.fields['payment_date'].initial = get_school_today()
    
    def clean_payroll_ids(self):
        """Validate and parse payroll IDs"""
        ids_string = self.cleaned_data.get('payroll_ids', '')
        
        try:
            payroll_ids = [int(id.strip()) for id in ids_string.split(',') if id.strip()]
        except ValueError:
            raise ValidationError(_("Invalid payroll IDs"))
        
        if not payroll_ids:
            raise ValidationError(_("No payrolls selected"))
        
        # Validate all payrolls exist and are APPROVED
        payrolls = Payroll.objects.filter(id__in=payroll_ids)
        
        if payrolls.count() != len(payroll_ids):
            raise ValidationError(_("Some selected payrolls do not exist"))
        
        non_approved = payrolls.exclude(status='APPROVED')
        if non_approved.exists():
            raise ValidationError(
                _(f"{non_approved.count()} payroll(s) are not APPROVED and cannot be marked as paid. "
                "Only approved payrolls can be paid.")
            )
        
        reversed_payrolls = payrolls.filter(reversed=True)
        if reversed_payrolls.exists():
            raise ValidationError(
                _(f"{reversed_payrolls.count()} payroll(s) are reversed and cannot be paid")
            )
        
        return payroll_ids
    
    def clean_payment_date(self):
        """Validate payment date"""
        payment_date = self.cleaned_data.get('payment_date')
        
        if payment_date:
            from core.utils import get_school_today
            today = get_school_today()
            
            if payment_date > today:
                raise ValidationError(
                    _("Payment date cannot be in the future. "
                    "Use actual date when payment was disbursed.")
                )
            
            if payment_date < (today - timedelta(days=90)):
                raise ValidationError(
                    _("Payment date seems too far in the past. Please verify.")
                )
        
        return payment_date


# =============================================================================
# ADDITIONAL HELPER FORMS
# =============================================================================

class PayrollCalculationForm(BootstrapFormMixin, forms.Form):
    """
    Form for triggering payroll calculation for a staff member.
    
    Helps auto-generate payroll from contract details.
    """
    
    staff = forms.ModelChoiceField(
        label=_("Staff Member"),
        queryset=Staff.objects.filter(is_active=True).order_by('first_name', 'last_name'),
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text=_("Select staff member to calculate payroll for")
    )
    
    fiscal_period = forms.ModelChoiceField(
        label=_("Fiscal Period"),
        queryset=None,  # Set in __init__
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text=_("Accounting period for this payroll")
    )
    
    pay_period_start = forms.DateField(
        label=_("Pay Period Start"),
        widget=DatePickerInput(),
        help_text=_("Start of the period being paid")
    )
    
    pay_period_end = forms.DateField(
        label=_("Pay Period End"),
        widget=DatePickerInput(),
        help_text=_("End of the period being paid")
    )
    
    include_recurring_allowances = forms.BooleanField(
        label=_("Include Recurring Allowances"),
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text=_("Auto-add recurring allowances from previous payrolls")
    )
    
    include_recurring_deductions = forms.BooleanField(
        label=_("Include Recurring Deductions"),
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text=_("Auto-add recurring deductions from previous payrolls")
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        from core.models import FiscalPeriod
        
        # Filter open fiscal periods
        self.fields['fiscal_period'].queryset = FiscalPeriod.objects.filter(
            is_closed=False
        ).order_by('-start_date')
        
        # Set defaults
        if not self.is_bound:
            from core.utils import get_school_today
            from datetime import timedelta
            from calendar import monthrange
            
            today = get_school_today()
            
            # Default to current month
            first_day = today.replace(day=1)
            last_day_num = monthrange(today.year, today.month)[1]
            last_day = today.replace(day=last_day_num)
            
            self.fields['pay_period_start'].initial = first_day
            self.fields['pay_period_end'].initial = last_day

# =============================================================================
# STAFF WIZARD FORMS
# =============================================================================

class StaffBasicInfoForm(BootstrapFormMixin, RequiredFieldsMixin, forms.ModelForm):
    """
    Step 1: Basic personal information.
    Uses school timezone for date validations. ⭐
    """
    
    # Override gender field to use radio buttons
    gender = forms.ChoiceField(
        label=_("Gender"),
        choices=Staff.GENDER_CHOICES,
        widget=forms.RadioSelect(),
        required=True
    )

    # Add designation field with special handling
    designation = forms.ModelChoiceField(
        queryset=None,
        label=_("Primary Designation"),
        widget=forms.Select(attrs={'class': 'form-select'}),
        required=True,
        help_text=_("Select the primary role/position for this staff member")
    )
    
    # Add option to mark as primary designation
    is_primary_designation = forms.BooleanField(
        label=_("Set as Primary Designation"),
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
            'checked': 'checked'
        }),
        help_text=_("Check if this is the main role for this staff member")
    )
    
    class Meta:
        model = Staff
        fields = [
            'salutation', 'first_name', 'middle_name', 'last_name',
            'date_of_birth', 'gender', 'marital_status',
            'nationality', 'ethnicity', 'religious_affiliation',
            'national_id', 'passport_number'
        ]
        
        widgets = {
            'salutation': forms.Select(attrs={'class': 'form-select'}),
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('First Name')
            }),
            'middle_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Middle Name (optional)')
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Last Name')
            }),
            'date_of_birth': DatePickerInput(),
            'marital_status': forms.Select(attrs={'class': 'form-select'}),
            'nationality': forms.Select(attrs={'class': 'form-select'}),
            'ethnicity': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Ethnicity (optional)')
            }),
            'religious_affiliation': forms.Select(attrs={'class': 'form-select'}),
            'national_id': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('National ID Number')
            }),
            'passport_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Passport Number (optional)')
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set required fields
        required_fields = ['first_name', 'last_name', 'date_of_birth', 'gender']
        for field_name in required_fields:
            if field_name in self.fields:
                self.fields[field_name].required = True
        
        # Set up designation choices
        try:
            designations = Designation.objects.filter(
                is_active=True
            ).select_related('department').order_by('department__name', 'name')
            
            self.fields['designation'].queryset = designations
            
        except Exception as e:
            logger.error(f"Error setting designation queryset: {e}")
            self.fields['designation'].queryset = Designation.objects.none()
        
        # Set up nationality choices with Uganda as default
        nationality_choices = [('', _('Select Nationality'))] + [('UG', 'Uganda')] + [
            (code, name) for code, name in countries if code != 'UG'
        ]
        self.fields['nationality'].choices = nationality_choices
        if not self.is_bound:
            self.fields['nationality'].initial = 'UG'
    
    def clean_first_name(self):
        value = self.cleaned_data.get('first_name')
        if value:
            value = ' '.join(value.strip().split()).title()
            if not re.match(r"^[a-zA-Z\s\-']+$", value):
                raise ValidationError(
                    _("First name should only contain letters, spaces, hyphens, and apostrophes.")
                )
            if len(value) < 2:
                raise ValidationError(_("First name must be at least 2 characters long."))
        return value
    
    def clean_last_name(self):
        value = self.cleaned_data.get('last_name')
        if value:
            value = ' '.join(value.strip().split()).title()
            if not re.match(r"^[a-zA-Z\s\-']+$", value):
                raise ValidationError(
                    _("Last name should only contain letters, spaces, hyphens, and apostrophes.")
                )
            if len(value) < 2:
                raise ValidationError(_("Last name must be at least 2 characters long."))
        return value
    
    def clean_date_of_birth(self):
        """Validate DOB using school timezone ⭐"""
        dob = self.cleaned_data.get('date_of_birth')
        if dob:
            validate_future_date(dob)  # ⭐ Uses school timezone
            validate_age(dob, min_age=18, max_age=75)  # ⭐ Uses school timezone
        return dob


class StaffContactInfoForm(BootstrapFormMixin, forms.Form):
    """Step 2: Contact information"""
    
    phone_number = forms.CharField(
        max_length=20,
        required=True,
        widget=PhoneInput(attrs={'placeholder': _('+256xxxxxxxxx')})
    )
    
    alternative_phone = forms.CharField(
        max_length=20,
        required=False,
        widget=PhoneInput(attrs={'placeholder': _('+256xxxxxxxxx (optional)')})
    )
    
    personal_email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': _('email@example.com (optional)')
        })
    )
    
    # Emergency contact information
    emergency_contact_name = forms.CharField(
        max_length=100,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('Emergency Contact Name')
        })
    )
    
    emergency_contact_relationship = forms.CharField(
        max_length=20,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('Relationship (e.g., Spouse, Parent)')
        })
    )
    
    emergency_contact_phone = forms.CharField(
        max_length=20,
        required=True,
        widget=PhoneInput(attrs={'placeholder': _('+256xxxxxxxxx')})
    )
    
    emergency_contact_address = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': _('Emergency contact address (optional)')
        })
    )
    
    def clean_phone_number(self):
        """Validate phone number"""
        phone = self.cleaned_data.get('phone_number')
        if phone:
            validate_phone_number(phone)
        return phone
    
    def clean_alternative_phone(self):
        """Validate alternative phone"""
        phone = self.cleaned_data.get('alternative_phone')
        if phone:
            validate_phone_number(phone)
        return phone
    
    def clean_emergency_contact_phone(self):
        """Validate emergency contact phone"""
        phone = self.cleaned_data.get('emergency_contact_phone')
        if phone:
            validate_phone_number(phone)
        return phone


class StaffEmploymentInfoForm(BootstrapFormMixin, forms.Form):
    """
    Step 3: Employment and department information.
    Uses school timezone for date validations. ⭐
    """
    
    staff_id = forms.CharField(
        max_length=30,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('Will be auto-generated'),
            'readonly': True,
            'style': 'background-color: #f8f9fa;'
        })
    )
    
    date_of_joining = forms.DateField(
        required=True,
        widget=DatePickerInput(),
        help_text=_("Date when staff member joined the school")
    )
    
    employment_status = forms.ChoiceField(
        choices=Staff.EMPLOYMENT_STATUS_CHOICES,
        required=True,
        initial='FT',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    primary_department = forms.ModelChoiceField(
        queryset=None,
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text=_("Primary department for this staff member")
    )
    
    date_of_leaving = forms.DateField(
        required=False,
        widget=DatePickerInput(),
        help_text=_("Leave blank if staff is still employed")
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set querysets
        try:
            self.fields['primary_department'].queryset = Department.objects.filter(
                is_active=True
            ).order_by('name')
        except Exception as e:
            logger.error(f"Error setting department queryset: {e}")
            self.fields['primary_department'].queryset = Department.objects.none()
        
        # Set default joining date (school timezone) ⭐
        if not self.is_bound:
            from core.utils import get_school_today
            self.fields['date_of_joining'].initial = get_school_today()
        
        # Auto-generate staff ID
        if not self.is_bound:
            from .utils import generate_staff_id
            try:
                staff_id = generate_staff_id()
                self.fields['staff_id'].initial = staff_id
            except Exception as e:
                logger.error(f"Error generating staff ID: {e}")
    
    def clean_date_of_joining(self):
        """Validate joining date using school timezone ⭐"""
        date_of_joining = self.cleaned_data.get('date_of_joining')
        if date_of_joining:
            from core.utils import get_school_today
            
            today = get_school_today()  # ⭐ USE SCHOOL TIMEZONE
            
            if date_of_joining > today:
                raise ValidationError(_("Date of joining cannot be in the future."))
            
            if date_of_joining < (today - timedelta(days=50*365)):
                raise ValidationError(
                    _("Date of joining seems too far in the past. Please verify.")
                )
        
        return date_of_joining
    
    def clean(self):
        cleaned_data = super().clean()
        date_of_joining = cleaned_data.get('date_of_joining')
        date_of_leaving = cleaned_data.get('date_of_leaving')
        
        if date_of_leaving and date_of_joining:
            if date_of_leaving < date_of_joining:
                self.add_error(
                    'date_of_leaving', 
                    _('Date of leaving cannot be before date of joining.')
                )
        
        return cleaned_data


class StaffQualificationsForm(BootstrapFormMixin, forms.Form):
    """Step 4: Educational qualifications and experience"""
    
    qualification = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 4,
            'placeholder': _('Educational qualifications (e.g., Bachelor of Education, Master\'s Degree)')
        }),
        help_text=_("List educational qualifications")
    )
    
    experience = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 4,
            'placeholder': _('Previous work experience')
        }),
        help_text=_("Describe previous work experience")
    )
    
    skills = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': _('Professional skills (e.g., Computer literacy, Leadership, Communication)')
        }),
        help_text=_("List relevant skills")
    )
    
    languages_spoken = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': _('Languages spoken (e.g., English, Luganda, Swahili)')
        }),
        help_text=_("List languages and proficiency levels")
    )
    
    professional_memberships = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': _('Professional associations or memberships')
        })
    )
    
    certifications = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': _('Professional certifications and licenses')
        })
    )


class StaffBankingInfoForm(BootstrapFormMixin, forms.Form):
    """Step 5: Banking and statutory information"""
    
    # Banking information
    bank_account_name = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('Account holder name')
        })
    )
    
    bank_account_number = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('Bank account number')
        })
    )
    
    bank_name = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('Bank name (e.g., Stanbic Bank)')
        })
    )
    
    bank_branch = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('Bank branch')
        })
    )
    
    # Statutory information
    tax_identification_number = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('TIN (Tax Identification Number)')
        }),
        help_text=_("Uganda Revenue Authority TIN")
    )
    
    social_security_number = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('NSSF Number')
        }),
        help_text=_("National Social Security Fund Number")
    )
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Check if any banking info is provided
        bank_fields = ['bank_account_name', 'bank_account_number', 'bank_name', 'bank_branch']
        bank_info_provided = any(cleaned_data.get(field) for field in bank_fields)
        
        # If any banking info is provided, require account number and bank name
        if bank_info_provided:
            if not cleaned_data.get('bank_account_number'):
                self.add_error(
                    'bank_account_number', 
                    _('Bank account number is required when banking information is provided.')
                )
            if not cleaned_data.get('bank_name'):
                self.add_error(
                    'bank_name', 
                    _('Bank name is required when banking information is provided.')
                )
        
        return cleaned_data


class StaffDesignationContractForm(BootstrapFormMixin, MoneyFieldsMixin, forms.Form):
    """
    Step 6: Designation and contract setup (optional).
    Uses school timezone for date validations. ⭐
    """
    
    create_designation = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label=_("Assign a designation to this staff member")
    )
    
    designation = forms.ModelChoiceField(
        queryset=None,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text=_("Primary designation/role")
    )
    
    is_primary_designation = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label=_("Set as primary designation")
    )
    
    role_allowance = MoneyField(
        required=False,
        initial=Decimal('0.00'),
        help_text=_("Role-specific allowance (optional)")
    )
    
    # Contract information
    create_contract = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label=_("Create an employment contract")
    )
    
    contract_type = forms.ChoiceField(
        choices=[('', _('Select Type'))] + list(Contract.CONTRACT_TYPE_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text=_("Type of employment contract")
    )
    
    contract_start_date = forms.DateField(
        required=False,
        widget=DatePickerInput(),
        help_text=_("Contract start date")
    )
    
    contract_duration_months = forms.IntegerField(
        required=False,
        initial=12,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': 1,
            'max': 120
        }),
        help_text=_("Contract duration in months")
    )
    
    basic_salary = MoneyField(
        required=False,
        help_text=_("Basic monthly salary")
    )
    
    job_title = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('Job title for contract')
        })
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set querysets
        try:
            self.fields['designation'].queryset = Designation.objects.filter(
                is_active=True
            ).select_related('department').order_by('department__name', 'name')
        except Exception as e:
            logger.error(f"Error setting queryset: {e}")
            self.fields['designation'].queryset = Designation.objects.none()
        
        # Set default contract start date (school timezone) ⭐
        if not self.is_bound:
            from core.utils import get_school_today
            self.fields['contract_start_date'].initial = get_school_today()
    
    def clean_contract_start_date(self):
        """Validate contract start date using school timezone ⭐"""
        start_date = self.cleaned_data.get('contract_start_date')
        if start_date:
            from core.utils import get_school_today
            
            today = get_school_today()  # ⭐ USE SCHOOL TIMEZONE
            
            # Allow reasonable past/future dates
            if start_date < (today - timedelta(days=365)):
                raise ValidationError(
                    _("Contract start date seems too far in the past.")
                )
            
            if start_date > (today + timedelta(days=365)):
                raise ValidationError(
                    _("Contract start date seems too far in the future.")
                )
        
        return start_date
    
    def clean(self):
        cleaned_data = super().clean()
        create_designation = cleaned_data.get('create_designation', False)
        create_contract = cleaned_data.get('create_contract', False)
        
        # Validate designation fields
        if create_designation:
            if not cleaned_data.get('designation'):
                self.add_error('designation', _('Please select a designation.'))
        
        # Validate contract fields
        if create_contract:
            required_contract_fields = {
                'contract_type': _('Please select a contract type.'),
                'contract_start_date': _('Please provide a contract start date.'),
                'basic_salary': _('Please provide a basic salary.'),
                'job_title': _('Please provide a job title.')
            }
            
            for field, error_msg in required_contract_fields.items():
                if not cleaned_data.get(field):
                    self.add_error(field, error_msg)
        
        return cleaned_data


class StaffConfirmationForm(BootstrapFormMixin, forms.Form):
    """Step 7: Final confirmation"""
    
    confirm_creation = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label=_("I confirm that all the information provided is correct")
    )
    
    send_welcome_email = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label=_("Send welcome email to staff member (if email provided)")
    )
    
    additional_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 4,
            'placeholder': _('Any additional notes or comments (optional)')
        }),
        help_text=_("Optional notes for record keeping")
    )


# =============================================================================
# WIZARD CONFIGURATION
# =============================================================================

STAFF_WIZARD_FORMS = [
    ("basic_info", StaffBasicInfoForm),
    ("contact_info", StaffContactInfoForm),
    ("employment_info", StaffEmploymentInfoForm),
    ("qualifications", StaffQualificationsForm),
    ("banking_info", StaffBankingInfoForm),
    ("designation_contract", StaffDesignationContractForm),
    ("confirmation", StaffConfirmationForm),
]

STAFF_WIZARD_STEP_NAMES = {
    'basic_info': _('Personal Information'),
    'contact_info': _('Contact Information'),
    'employment_info': _('Employment Details'),
    'qualifications': _('Qualifications & Experience'),
    'banking_info': _('Banking & Statutory Information'),
    'designation_contract': _('Designation & Contract'),
    'confirmation': _('Review & Confirmation')
}


# hr/forms.py - PART 3 (General Staff Form, StaffDesignation Form, Teacher Form)

# =============================================================================
# GENERAL STAFF FORM (SINGLE PAGE)
# =============================================================================

class StaffForm(BootstrapFormMixin, RequiredFieldsMixin, forms.ModelForm):
    """
    Complete staff form (all fields in one page).
    Uses school timezone for all date validations. ⭐
    """

    # Override gender field to use radio buttons
    gender = forms.ChoiceField(
        label=_("Gender"),
        choices=Staff.GENDER_CHOICES,
        widget=forms.RadioSelect(),
        required=False
    )

    # Add designation field with special handling
    designation = forms.ModelChoiceField(
        queryset=None,
        label=_("Primary Designation"),
        widget=forms.Select(attrs={'class': 'form-select'}),
        required=True,
        help_text=_("Select the primary role/position for this staff member")
    )
    
    # Add option to mark as primary designation
    is_primary_designation = forms.BooleanField(
        label=_("Set as Primary Designation"),
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
            'checked': 'checked'
        }),
        help_text=_("Check if this is the main role for this staff member")
    )
    
    class Meta:
        model = Staff
        fields = [
            'salutation', 'first_name', 'middle_name', 'last_name',
            'staff_id', 'date_of_birth', 'gender',
            'ethnicity', 'religious_affiliation', 'marital_status',
            'nationality', 'national_id', 'passport_number',
            'phone_number', 'alternative_phone', 'personal_email',
            'emergency_contact_name', 'emergency_contact_relationship',
            'emergency_contact_phone', 'emergency_contact_address',
            'primary_department', 'employment_status',
            'date_of_joining', 'date_of_leaving',
            'qualification', 'experience', 'skills',
            'languages_spoken', 'professional_memberships', 'certifications',
            'bank_account_name', 'bank_account_number', 'bank_name', 'bank_branch',
            'tax_identification_number', 'social_security_number',
            'photo', 'is_active'
        ]
        
        widgets = {
            'salutation': forms.Select(attrs={'class': 'form-select'}),
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('First Name')
            }),
            'middle_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Middle Name (optional)')
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Last Name')
            }),
            'staff_id': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Will be auto-generated'),
                'readonly': True,
                'style': 'background-color: #f8f9fa;'
            }),
            'date_of_birth': DatePickerInput(),
            'date_of_joining': DatePickerInput(),
            'date_of_leaving': DatePickerInput(),
            'ethnicity': forms.TextInput(attrs={'class': 'form-control'}),
            'religious_affiliation': forms.Select(attrs={'class': 'form-select'}),
            'marital_status': forms.Select(attrs={'class': 'form-select'}),
            'nationality': forms.Select(attrs={'class': 'form-select'}),
            'national_id': forms.TextInput(attrs={'class': 'form-control'}),
            'passport_number': forms.TextInput(attrs={'class': 'form-control'}),
            'phone_number': PhoneInput(attrs={'placeholder': _('+256xxxxxxxxx')}),
            'alternative_phone': PhoneInput(attrs={'placeholder': _('+256xxxxxxxxx')}),
            'personal_email': forms.EmailInput(attrs={'class': 'form-control'}),
            'emergency_contact_name': forms.TextInput(attrs={'class': 'form-control'}),
            'emergency_contact_relationship': forms.TextInput(attrs={'class': 'form-control'}),
            'emergency_contact_phone': PhoneInput(attrs={'placeholder': _('+256xxxxxxxxx')}),
            'emergency_contact_address': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2
            }),
            'primary_department': forms.Select(attrs={'class': 'form-select'}),
            'employment_status': forms.Select(attrs={'class': 'form-select'}),
            'qualification': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'experience': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'skills': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'languages_spoken': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'professional_memberships': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'certifications': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'bank_account_name': forms.TextInput(attrs={'class': 'form-control'}),
            'bank_account_number': forms.TextInput(attrs={'class': 'form-control'}),
            'bank_name': forms.TextInput(attrs={'class': 'form-control'}),
            'bank_branch': forms.TextInput(attrs={'class': 'form-control'}),
            'tax_identification_number': forms.TextInput(attrs={'class': 'form-control'}),
            'social_security_number': forms.TextInput(attrs={'class': 'form-control'}),
            'photo': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Required fields
        self.fields['first_name'].required = True
        self.fields['last_name'].required = True
        self.fields['date_of_joining'].required = True
        self.fields['designation'].required = True
        
        # Set up designation queryset
        try:
            self.fields['designation'].queryset = Designation.objects.filter(
                is_active=True
            ).select_related('department').order_by('department__name', 'rank_order', 'name')
            
            # If editing existing staff, show current designation
            if self.instance.pk:
                try:
                    current_designation = StaffDesignation.objects.filter(
                        staff=self.instance,
                        is_primary=True,
                        is_active=True
                    ).first()
                    
                    if current_designation:
                        self.fields['designation'].initial = current_designation.designation
                except Exception as e:
                    logger.error(f"Error getting current designation: {e}")
                    
        except Exception as e:
            logger.error(f"Error setting designation queryset: {e}")
            self.fields['designation'].queryset = Designation.objects.none()
        
        # Filter departments
        self.fields['primary_department'].queryset = Department.objects.filter(is_active=True)
        
        # Set default date of joining (school timezone) ⭐
        if not self.is_bound:
            from core.utils import get_school_today
            self.fields['date_of_joining'].initial = get_school_today()
        
        # Auto-generate staff ID for new staff
        if not self.instance.pk and not self.is_bound:
            from .utils import generate_staff_id
            try:
                staff_id = generate_staff_id()
                self.fields['staff_id'].initial = staff_id
            except Exception as e:
                logger.error(f"Error generating staff ID: {e}")
    
    def clean_first_name(self):
        value = self.cleaned_data.get('first_name')
        if value:
            value = ' '.join(value.strip().split()).title()
            if not re.match(r"^[a-zA-Z\s\-']+$", value):
                raise ValidationError(
                    _("First name should only contain letters, spaces, hyphens, and apostrophes.")
                )
            if len(value) < 2:
                raise ValidationError(_("First name must be at least 2 characters long."))
        return value
    
    def clean_last_name(self):
        value = self.cleaned_data.get('last_name')
        if value:
            value = ' '.join(value.strip().split()).title()
            if not re.match(r"^[a-zA-Z\s\-']+$", value):
                raise ValidationError(
                    _("Last name should only contain letters, spaces, hyphens, and apostrophes.")
                )
            if len(value) < 2:
                raise ValidationError(_("Last name must be at least 2 characters long."))
        return value
    
    def clean_date_of_birth(self):
        """Validate DOB using school timezone ⭐"""
        dob = self.cleaned_data.get('date_of_birth')
        if dob:
            validate_future_date(dob)  # ⭐ Uses school timezone
            validate_age(dob, min_age=18, max_age=80)  # ⭐ Uses school timezone
        return dob
    
    def clean_date_of_joining(self):
        """Validate joining date using school timezone ⭐"""
        date_of_joining = self.cleaned_data.get('date_of_joining')
        if date_of_joining:
            from core.utils import get_school_today
            
            today = get_school_today()  # ⭐ USE SCHOOL TIMEZONE
            
            if date_of_joining > today:
                raise ValidationError(_("Date of joining cannot be in the future."))
            
            if date_of_joining < (today - timedelta(days=50*365)):
                raise ValidationError(
                    _("Date of joining seems too far in the past. Please verify.")
                )
        
        return date_of_joining
    
    def clean_date_of_leaving(self):
        date_of_joining = self.cleaned_data.get('date_of_joining')
        date_of_leaving = self.cleaned_data.get('date_of_leaving')
        
        if date_of_leaving and date_of_joining:
            if date_of_leaving < date_of_joining:
                raise ValidationError(_("Date of leaving cannot be before date of joining."))
        
        return date_of_leaving
    
    def save(self, commit=True):
        staff = super().save(commit=commit)
        
        if commit:
            designation = self.cleaned_data.get('designation')
            is_primary = self.cleaned_data.get('is_primary_designation', True)
            
            if designation:
                # Check if staff already has this designation
                existing_designation = StaffDesignation.objects.filter(
                    staff=staff,
                    designation=designation,
                    is_active=True
                ).first()
                
                if not existing_designation:
                    # If marking as primary, unset other primary designations
                    if is_primary:
                        StaffDesignation.objects.filter(
                            staff=staff,
                            is_primary=True
                        ).update(is_primary=False)
                    
                    # Create new designation assignment
                    from core.utils import get_school_today
                    
                    staff_designation = StaffDesignation.objects.create(
                        staff=staff,
                        designation=designation,
                        is_primary=is_primary,
                        start_date=get_school_today(),
                        is_active=True,
                        assignment_type='PERMANENT'
                    )
                    
                    # ⭐ AUTO-CREATE TEACHER PROFILE if designation is teaching
                    if designation.is_teaching and not hasattr(staff, 'teacher'):
                        Teacher.objects.create(
                            staff=staff,
                            specialization=designation.name,
                            max_hours_per_week=40,
                            digital_literacy_level='BASIC',
                            is_class_teacher=False,
                            can_teach_online=False,
                        )
                        logger.info(
                            f"Auto-created teacher profile for {staff.full_name()} "
                            f"due to teaching designation: {designation.name}"
                        )
                
                elif is_primary:
                    # Update existing to be primary
                    StaffDesignation.objects.filter(
                        staff=staff,
                        is_primary=True
                    ).exclude(id=existing_designation.id).update(is_primary=False)
                    
                    existing_designation.is_primary = True
                    existing_designation.save()
                    
                    # ⭐ AUTO-CREATE TEACHER PROFILE if needed
                    if designation.is_teaching and not hasattr(staff, 'teacher'):
                        Teacher.objects.create(
                            staff=staff,
                            specialization=designation.name,
                            max_hours_per_week=40,
                            digital_literacy_level='BASIC',
                            is_class_teacher=False,
                            can_teach_online=False,
                        )
        
        return staff


# =============================================================================
# STAFF DESIGNATION FORM
# =============================================================================

class StaffDesignationForm(BootstrapFormMixin, RequiredFieldsMixin, MoneyFieldsMixin, forms.ModelForm):
    """
    Form for assigning designations to staff.
    Uses school timezone for date validations. ⭐
    """
    
    role_allowance = MoneyField(
        label=_("Role-Specific Allowance"),
        required=False,
        initial=Decimal('0.00')
    )
    
    class Meta:
        model = StaffDesignation
        fields = [
            'staff', 'designation', 'is_primary',
            'start_date', 'end_date', 'is_active',
            'role_allowance', 'assignment_type', 'assignment_order_number',
            'notes'
        ]
        
        widgets = {
            'staff': forms.Select(attrs={'class': 'form-select'}),
            'designation': forms.Select(attrs={'class': 'form-select'}),
            'is_primary': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'start_date': DatePickerInput(),
            'end_date': DatePickerInput(),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'assignment_type': forms.Select(attrs={'class': 'form-select'}),
            'assignment_order_number': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': _('Assignment notes...')
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Required fields
        self.fields['staff'].required = True
        self.fields['designation'].required = True
        
        # Filter to active records
        self.fields['staff'].queryset = Staff.objects.filter(is_active=True)
        self.fields['designation'].queryset = Designation.objects.filter(is_active=True)
        
        # Set default start date (school timezone) ⭐
        if not self.is_bound:
            from core.utils import get_school_today
            self.fields['start_date'].initial = get_school_today()
    
    def clean_start_date(self):
        """Validate start date using school timezone ⭐"""
        start_date = self.cleaned_data.get('start_date')
        if start_date:
            from core.utils import get_school_today
            
            today = get_school_today()  # ⭐ USE SCHOOL TIMEZONE
            
            # Allow reasonable past dates
            if start_date < (today - timedelta(days=10*365)):
                raise ValidationError(_("Start date seems too far in the past."))
        
        return start_date
    
    def clean_end_date(self):
        """Validate end date is after start date"""
        start_date = self.cleaned_data.get('start_date')
        end_date = self.cleaned_data.get('end_date')
        
        if start_date and end_date:
            if end_date < start_date:
                raise ValidationError(_("End date must be after start date."))
        
        return end_date
    
    def save(self, commit=True):
        staff_designation = super().save(commit=commit)
        
        if commit:
            # If marking as primary, unset other primary designations
            if staff_designation.is_primary:
                StaffDesignation.objects.filter(
                    staff=staff_designation.staff,
                    is_primary=True
                ).exclude(pk=staff_designation.pk).update(is_primary=False)
            
            # ⭐ AUTO-CREATE TEACHER PROFILE if designation is teaching
            if staff_designation.designation.is_teaching and staff_designation.is_active:
                # Check if teacher profile doesn't exist
                if not hasattr(staff_designation.staff, 'teacher'):
                    Teacher.objects.create(
                        staff=staff_designation.staff,
                        specialization=staff_designation.designation.name,
                        max_hours_per_week=40,
                        digital_literacy_level='BASIC',
                        is_class_teacher=False,
                        can_teach_online=False,
                    )
                    logger.info(
                        f"Auto-created teacher profile for {staff_designation.staff.full_name()} "
                        f"due to teaching designation: {staff_designation.designation.name}"
                    )
        
        return staff_designation


# =============================================================================
# TEACHER FORM
# =============================================================================

class TeacherForm(BootstrapFormMixin, RequiredFieldsMixin, forms.ModelForm):
    """Form for creating/editing teacher profiles with soft delete support"""
    
    class Meta:
        model = Teacher
        fields = [
            'staff', 'specialization', 'teaching_philosophy',
            'max_hours_per_week', 'current_teaching_load',
            'preferred_academic_levels', 'qualified_subjects',
            'available_days', 'preferred_time_slots',
            'is_class_teacher', 'assigned_classes',
            'digital_literacy_level', 'can_teach_online', 
            'is_active'  # ⭐ Added for soft delete
        ]
        
        widgets = {
            'staff': forms.Select(attrs={'class': 'form-select'}),
            'specialization': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('e.g., Mathematics, Science, English Language')
            }),
            'teaching_philosophy': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': _('Describe your teaching philosophy and approach to education...')
            }),
            'max_hours_per_week': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1, 
                'max': 60,
                'placeholder': '40'
            }),
            'current_teaching_load': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'readonly': True,
                'style': 'background-color: #f8f9fa;',
                'placeholder': _('Auto-calculated from schedule')
            }),
            'preferred_academic_levels': forms.SelectMultiple(attrs={'class': 'form-select'}),
            'qualified_subjects': forms.SelectMultiple(attrs={'class': 'form-select'}),
            'available_days': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': _('["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]')
            }),
            'preferred_time_slots': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': _('["08:00-10:00", "10:00-12:00", "14:00-16:00"]')
            }),
            'is_class_teacher': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'assigned_classes': forms.SelectMultiple(attrs={'class': 'form-select'}),
            'digital_literacy_level': forms.Select(attrs={'class': 'form-select'}),
            'can_teach_online': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Required fields
        self.fields['staff'].required = True
        self.fields['max_hours_per_week'].required = True
        self.fields['digital_literacy_level'].required = True
        
        # ⭐ Help text for is_active field (soft delete)
        self.fields['is_active'].help_text = _(
            "Uncheck to deactivate this teacher profile. "
            "Profile will be automatically reactivated when a teaching designation is assigned."
        )
        
        # ⭐ Filter staff to those not already teachers OR the current instance
        if self.instance.pk:
            # Editing existing teacher - allow current staff + active staff without teacher profiles
            self.fields['staff'].queryset = Staff.objects.filter(is_active=True)
            
            # Make staff field read-only when editing
            self.fields['staff'].disabled = True
            self.fields['staff'].help_text = _("Staff member cannot be changed after teacher profile is created")
        else:
            # Creating new teacher - exclude staff who already have ACTIVE teacher profiles
            existing_teacher_staff_ids = Teacher.objects.filter(
                is_active=True  # ⭐ Only exclude staff with ACTIVE teacher profiles
            ).values_list('staff_id', flat=True)
            
            self.fields['staff'].queryset = Staff.objects.filter(
                is_active=True
            ).exclude(id__in=existing_teacher_staff_ids)
            
            self.fields['staff'].help_text = _("Select a staff member who doesn't already have an active teacher profile")
        
        # Filter related fields to active records only
        try:
            self.fields['preferred_academic_levels'].queryset = AcademicLevel.objects.filter(
                is_active=True
            ).order_by('level_order')
            
            self.fields['qualified_subjects'].queryset = Subject.objects.filter(
                is_active=True
            ).order_by('name')
            
            self.fields['assigned_classes'].queryset = Class.objects.filter(
                is_active=True
            ).select_related('academic_level').order_by('academic_level__level_order', 'name')
            
        except Exception as e:
            logger.error(f"Error setting queryset for teacher form: {e}")
        
        # Add placeholder text for multi-select fields
        self.fields['preferred_academic_levels'].help_text = _(
            "Select academic levels (classes) this teacher prefers to teach"
        )
        self.fields['qualified_subjects'].help_text = _(
            "Select all subjects this teacher is qualified to teach"
        )
        self.fields['assigned_classes'].help_text = _(
            "Select classes this teacher is responsible for as class teacher"
        )
        
        # Set initial value for is_active (default to True for new teachers)
        if not self.instance.pk:
            self.fields['is_active'].initial = True
    
    def clean_staff(self):
        """
        Validate staff selection and check for teaching designation.
        Provides warnings but doesn't block creation.
        """
        staff = self.cleaned_data.get('staff')
        
        if staff:
            # ⭐ Check if staff has at least one active teaching designation
            has_teaching_designation = StaffDesignation.objects.filter(
                staff=staff,
                designation__is_teaching=True,
                is_active=True
            ).exists()
            
            if not has_teaching_designation:
                if not self.instance.pk:
                    # Creating new teacher without teaching designation
                    logger.warning(
                        f"Creating teacher profile for {staff.full_name()} "
                        f"without active teaching designation. "
                        f"Consider assigning a teaching designation first."
                    )
                    
                    # Add a non-field error to inform the user
                    self.add_error(None, 
                        _(f"Note: {staff.full_name()} does not have an active teaching designation. "
                        f"The teacher profile will be created, but consider assigning a teaching "
                        f"designation for consistency.")
                    )
                else:
                    # Editing existing teacher who lost teaching designation
                    logger.warning(
                        f"Teacher {staff.full_name()} has no active teaching designation. "
                        f"Profile may have been auto-deactivated."
                    )
            
            # ⭐ Check if this staff already has an INACTIVE teacher profile
            if not self.instance.pk:
                try:
                    inactive_teacher = Teacher.objects.get(
                        staff=staff,
                        is_active=False
                    )
                    # Found inactive profile - suggest reactivation instead
                    raise forms.ValidationError(
                        _(f"{staff.full_name()} already has an inactive teacher profile. "
                        f"Please reactivate the existing profile instead of creating a new one.")
                    )
                except Teacher.DoesNotExist:
                    # No inactive profile - proceed normally
                    pass
        
        return staff
    
    def clean_current_teaching_load(self):
        """
        Validate current teaching load doesn't exceed maximum hours.
        """
        current_load = self.cleaned_data.get('current_teaching_load', 0)
        max_hours = self.cleaned_data.get('max_hours_per_week', 40)
        
        if current_load and max_hours:
            if current_load > max_hours:
                logger.warning(
                    f"Current teaching load ({current_load}) exceeds maximum hours ({max_hours})"
                )
                self.add_error('current_teaching_load',
                    _(f"Current teaching load ({current_load} hours) exceeds the maximum "
                    f"allowed hours per week ({max_hours} hours). This may indicate overload.")
                )
        
        return current_load
    
    def clean_assigned_classes(self):
        """
        Validate assigned classes when is_class_teacher is True.
        """
        assigned_classes = self.cleaned_data.get('assigned_classes')
        is_class_teacher = self.cleaned_data.get('is_class_teacher', False)
        
        if is_class_teacher and not assigned_classes:
            logger.info("Teacher marked as class teacher but no classes assigned")
        
        return assigned_classes
    
    def clean(self):
        """
        Perform cross-field validation.
        """
        cleaned_data = super().clean()
        
        # Validate JSON fields if provided
        available_days = cleaned_data.get('available_days')
        if available_days:
            try:
                import json
                if isinstance(available_days, str):
                    json.loads(available_days)
            except json.JSONDecodeError:
                self.add_error('available_days', 
                    _('Invalid JSON format. Use format: ["Monday", "Tuesday", "Wednesday"]')
                )
        
        preferred_time_slots = cleaned_data.get('preferred_time_slots')
        if preferred_time_slots:
            try:
                import json
                if isinstance(preferred_time_slots, str):
                    json.loads(preferred_time_slots)
            except json.JSONDecodeError:
                self.add_error('preferred_time_slots',
                    _('Invalid JSON format. Use format: ["08:00-10:00", "10:00-12:00"]')
                )
        
        return cleaned_data
    
    def save(self, commit=True):
        """
        Save the teacher profile.
        Log important status changes.
        """
        teacher = super().save(commit=False)
        
        # Track if this is a new teacher or status change
        is_new = not teacher.pk
        status_changed = False
        
        if not is_new:
            try:
                old_teacher = Teacher.objects.get(pk=teacher.pk)
                if old_teacher.is_active != teacher.is_active:
                    status_changed = True
                    status_change = "activated" if teacher.is_active else "deactivated"
                    logger.info(
                        f"Teacher profile {status_change} for {teacher.staff.full_name()}"
                    )
            except Teacher.DoesNotExist:
                pass
        
        if commit:
            teacher.save()
            self.save_m2m()  # Save many-to-many relationships
            
            if is_new:
                logger.info(
                    f"New teacher profile created for {teacher.staff.full_name()} "
                    f"(Specialization: {teacher.specialization})"
                )
        
        return teacher