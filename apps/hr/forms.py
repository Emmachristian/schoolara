# hr/forms.py

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal
import re
import logging

from .models import (
    Department, Designation, ContractType, Contract, 
    Staff, StaffDesignation, Teacher
)
from academics.models import AcademicLevel, Subject, Class

logger = logging.getLogger(__name__)


# =============================================================================
# DEPARTMENT FORM
# =============================================================================

class DepartmentForm(forms.ModelForm):
    """Form for creating/editing departments"""
    
    class Meta:
        model = Department
        fields = [
            'name', 'code', 'description', 'department_type', 'academic_subtype',
            'is_academic', 'parent_department', 'annual_budget',
            'phone', 'email', 'head', 'is_active', 'capacity', 'location', 'operating_hours'
        ]
        
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Department Name'
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'DEPT CODE (e.g., MATH, ENG)',
                'maxlength': 10
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Department description...'
            }),
            'department_type': forms.Select(attrs={'class': 'form-select'}),
            'academic_subtype': forms.Select(attrs={'class': 'form-select'}),
            'is_academic': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'parent_department': forms.Select(attrs={'class': 'form-select'}),
            'annual_budget': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0.00',
                'step': '0.01'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+256xxxxxxxxx',
                'type': 'tel'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'department@school.com'
            }),
            'head': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'capacity': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Staff capacity',
                'min': 1
            }),
            'location': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Building/Location'
            }),
            'operating_hours': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': '{"monday": "8:00-17:00", "tuesday": "8:00-17:00"}'
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
            self.fields['parent_department'].queryset = Department.objects.filter(is_active=True)
        
        # Filter head to active staff only
        self.fields['head'].queryset = Staff.objects.filter(is_active=True)
        
        # Show/hide academic_subtype based on department_type
        if self.instance.pk and self.instance.department_type != 'ACADEMIC':
            self.fields['academic_subtype'].required = False
    
    def clean_code(self):
        """Validate department code"""
        code = self.cleaned_data.get('code', '').upper().strip()
        
        if not re.match(r'^[A-Z0-9_-]+$', code):
            raise ValidationError("Code must contain only uppercase letters, numbers, hyphens, and underscores.")
        
        # Check uniqueness
        if self.instance.pk:
            if Department.objects.exclude(pk=self.instance.pk).filter(code=code).exists():
                raise ValidationError("A department with this code already exists.")
        else:
            if Department.objects.filter(code=code).exists():
                raise ValidationError("A department with this code already exists.")
        
        return code
    
    def clean(self):
        cleaned_data = super().clean()
        department_type = cleaned_data.get('department_type')
        academic_subtype = cleaned_data.get('academic_subtype')
        parent_department = cleaned_data.get('parent_department')
        
        # Validate academic subtype
        if department_type == 'ACADEMIC' and not academic_subtype:
            self.add_error('academic_subtype', 'Academic subtype is required for academic departments.')
        
        # Prevent circular parent relationships
        if parent_department:
            if self.instance.pk and parent_department.pk == self.instance.pk:
                self.add_error('parent_department', 'A department cannot be its own parent.')
        
        return cleaned_data


# =============================================================================
# DESIGNATION FORM
# =============================================================================

class DesignationForm(forms.ModelForm):
    """Form for creating/editing designations"""
    
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
                'placeholder': 'Designation Name (e.g., Senior Teacher)'
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'CODE (e.g., ST-01)',
                'maxlength': 50
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Designation description...'
            }),
            'department': forms.Select(attrs={'class': 'form-select'}),
            'is_teaching': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_management': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'reports_to': forms.Select(attrs={'class': 'form-select'}),
            'rank_order': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0 (higher rank = lower number)',
                'min': 0
            }),
            'min_salary': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Minimum Salary',
                'step': '0.01'
            }),
            'max_salary': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Maximum Salary',
                'step': '0.01'
            }),
            'required_qualifications': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': '["Bachelor\'s Degree in Education", "Teaching License"]'
            }),
            'key_responsibilities': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Key responsibilities...'
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
            raise ValidationError("Code must contain only uppercase letters, numbers, hyphens, and underscores.")
        
        # Check uniqueness
        if self.instance.pk:
            if Designation.objects.exclude(pk=self.instance.pk).filter(code=code).exists():
                raise ValidationError("A designation with this code already exists.")
        else:
            if Designation.objects.filter(code=code).exists():
                raise ValidationError("A designation with this code already exists.")
        
        return code
    
    def clean(self):
        cleaned_data = super().clean()
        min_salary = cleaned_data.get('min_salary')
        max_salary = cleaned_data.get('max_salary')
        
        # Validate salary range
        if min_salary and max_salary:
            if min_salary > max_salary:
                self.add_error('max_salary', 'Maximum salary must be greater than minimum salary.')
        
        return cleaned_data


# =============================================================================
# CONTRACT TYPE FORM
# =============================================================================

class ContractTypeForm(forms.ModelForm):
    """Form for creating/editing contract types"""
    
    class Meta:
        model = ContractType
        fields = [
            'name', 'description', 'default_duration_months',
            'requires_renewal', 'auto_create_probation', 'default_probation_months',
            'is_active'
        ]
        
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Contract Type Name (e.g., Permanent, Temporary)'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Contract type description...'
            }),
            'default_duration_months': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'max': 120
            }),
            'requires_renewal': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'auto_create_probation': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'default_probation_months': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'max': 12
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['name'].required = True


# =============================================================================
# CONTRACT FORM
# =============================================================================

class ContractForm(forms.ModelForm):
    """Form for creating/editing staff contracts"""
    
    class Meta:
        model = Contract
        fields = [
            'staff', 'contract_type', 'contract_number', 'status',
            'start_date', 'end_date', 'signed_date', 'renewal_due_date',
            'basic_salary', 'salary_frequency', 'working_hours_per_week',
            'probation_period_months', 'annual_leave_days',
            'job_title', 'job_description', 'reporting_to',
            'contract_document', 'auto_renew', 'renewal_period_months',
            'termination_date', 'termination_reason', 'termination_notice_period_days',
            'notes'
        ]
        
        widgets = {
            'staff': forms.Select(attrs={'class': 'form-select'}),
            'contract_type': forms.Select(attrs={'class': 'form-select'}),
            'contract_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Will be auto-generated',
                'readonly': True,
                'style': 'background-color: #f8f9fa;'
            }),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'signed_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'renewal_due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'basic_salary': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0.00',
                'step': '0.01'
            }),
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
            'job_title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Job Title'
            }),
            'job_description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Job description and responsibilities...'
            }),
            'reporting_to': forms.Select(attrs={'class': 'form-select'}),
            'contract_document': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf,.doc,.docx'
            }),
            'auto_renew': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'renewal_period_months': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'max': 120
            }),
            'termination_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'termination_reason': forms.Select(attrs={'class': 'form-select'}),
            'termination_notice_period_days': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Contract notes...'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Required fields
        self.fields['staff'].required = True
        self.fields['contract_type'].required = True
        self.fields['start_date'].required = True
        self.fields['end_date'].required = True
        self.fields['job_title'].required = True
        
        # Filter staff to active only
        self.fields['staff'].queryset = Staff.objects.filter(is_active=True)
        self.fields['reporting_to'].queryset = Staff.objects.filter(is_active=True)
        
        # Filter contract types to active only
        self.fields['contract_type'].queryset = ContractType.objects.filter(is_active=True)
        
        # Auto-generate contract number for new contracts
        if not self.instance.pk and not self.is_bound:
            from .utils import generate_contract_number
            contract_number = generate_contract_number()
            self.fields['contract_number'].initial = contract_number
    
    def clean_end_date(self):
        """Validate end date is after start date"""
        start_date = self.cleaned_data.get('start_date')
        end_date = self.cleaned_data.get('end_date')
        
        if start_date and end_date:
            if end_date <= start_date:
                raise ValidationError("End date must be after start date.")
        
        return end_date
    
    def clean_termination_date(self):
        """Validate termination date"""
        start_date = self.cleaned_data.get('start_date')
        termination_date = self.cleaned_data.get('termination_date')
        
        if termination_date and start_date:
            if termination_date < start_date:
                raise ValidationError("Termination date cannot be before contract start date.")
        
        return termination_date
    
    def clean(self):
        cleaned_data = super().clean()
        status = cleaned_data.get('status')
        termination_date = cleaned_data.get('termination_date')
        termination_reason = cleaned_data.get('termination_reason')
        
        # Validate termination fields
        if status == 'TERMINATED':
            if not termination_date:
                self.add_error('termination_date', 'Termination date is required for terminated contracts.')
            if not termination_reason:
                self.add_error('termination_reason', 'Termination reason is required for terminated contracts.')
        
        return cleaned_data


# =============================================================================
# STAFF FORM
# =============================================================================

class StaffForm(forms.ModelForm):
    """Form for creating/editing staff"""
    
    # Override gender field to use radio buttons
    gender = forms.ChoiceField(
        label="Gender",
        choices=Staff.GENDER_CHOICES,
        widget=forms.RadioSelect(),
        required=False
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
                'placeholder': 'First Name'
            }),
            'middle_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Middle Name (optional)'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Last Name'
            }),
            'staff_id': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Will be auto-generated',
                'readonly': True,
                'style': 'background-color: #f8f9fa;'
            }),
            'date_of_birth': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'ethnicity': forms.TextInput(attrs={'class': 'form-control'}),
            'religious_affiliation': forms.Select(attrs={'class': 'form-select'}),
            'marital_status': forms.Select(attrs={'class': 'form-select'}),
            'nationality': forms.Select(attrs={'class': 'form-select'}),
            'national_id': forms.TextInput(attrs={'class': 'form-control'}),
            'passport_number': forms.TextInput(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+256xxxxxxxxx',
                'type': 'tel'
            }),
            'alternative_phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+256xxxxxxxxx',
                'type': 'tel'
            }),
            'personal_email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'email@example.com'
            }),
            'emergency_contact_name': forms.TextInput(attrs={'class': 'form-control'}),
            'emergency_contact_relationship': forms.TextInput(attrs={'class': 'form-control'}),
            'emergency_contact_phone': forms.TextInput(attrs={
                'class': 'form-control',
                'type': 'tel'
            }),
            'emergency_contact_address': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2
            }),
            'primary_department': forms.Select(attrs={'class': 'form-select'}),
            'employment_status': forms.Select(attrs={'class': 'form-select'}),
            'date_of_joining': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'date_of_leaving': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
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
            'photo': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Required fields
        self.fields['first_name'].required = True
        self.fields['last_name'].required = True
        self.fields['date_of_joining'].required = True
        
        # Filter departments
        self.fields['primary_department'].queryset = Department.objects.filter(is_active=True)
        
        # Set default date of joining
        if not self.is_bound:
            self.fields['date_of_joining'].initial = timezone.now().date()
        
        # Auto-generate staff ID for new staff
        if not self.instance.pk and not self.is_bound:
            from .utils import generate_staff_id
            staff_id = generate_staff_id()
            self.fields['staff_id'].initial = staff_id
    
    def clean_first_name(self):
        value = self.cleaned_data.get('first_name')
        if value:
            value = ' '.join(value.strip().split()).title()
            if not re.match(r"^[a-zA-Z\s\-']+$", value):
                raise ValidationError("First name should only contain letters, spaces, hyphens, and apostrophes.")
            if len(value) < 2:
                raise ValidationError("First name must be at least 2 characters long.")
        return value
    
    def clean_last_name(self):
        value = self.cleaned_data.get('last_name')
        if value:
            value = ' '.join(value.strip().split()).title()
            if not re.match(r"^[a-zA-Z\s\-']+$", value):
                raise ValidationError("Last name should only contain letters, spaces, hyphens, and apostrophes.")
            if len(value) < 2:
                raise ValidationError("Last name must be at least 2 characters long.")
        return value
    
    def clean_date_of_birth(self):
        dob = self.cleaned_data.get('date_of_birth')
        if dob:
            today = date.today()
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            
            if dob > today:
                raise ValidationError("Date of birth cannot be in the future.")
            if age < 18:
                raise ValidationError("Staff member must be at least 18 years old.")
            if age > 70:
                raise ValidationError("Age seems unusually high. Please verify.")
        return dob
    
    def clean_date_of_leaving(self):
        date_of_joining = self.cleaned_data.get('date_of_joining')
        date_of_leaving = self.cleaned_data.get('date_of_leaving')
        
        if date_of_leaving and date_of_joining:
            if date_of_leaving < date_of_joining:
                raise ValidationError("Date of leaving cannot be before date of joining.")
        
        return date_of_leaving
    
# hr/forms.py (add these after your existing forms)

# =============================================================================
# STAFF WIZARD FORMS
# =============================================================================

# =============================================================================
# STEP 1: BASIC INFORMATION FORM
# =============================================================================

class StaffBasicInfoForm(forms.ModelForm):
    """Step 1: Basic personal information"""
    
    # Override gender field to use ChoiceField instead of ModelChoiceField
    gender = forms.ChoiceField(
        label="Gender",
        choices=Staff.GENDER_CHOICES,
        widget=forms.RadioSelect(),
        required=True
    )
    
    class Meta:
        model = Staff
        fields = [
            'salutation', 'first_name', 'middle_name', 'last_name',
            'date_of_birth', 'gender', 'marital_status',
            'nationality', 'ethnicity', 'religious_affiliation',
            'national_id', 'passport_number', 'photo'
        ]
        
        widgets = {
            'salutation': forms.Select(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'First Name'
            }),
            'middle_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Middle Name (optional)'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Last Name'
            }),
            'date_of_birth': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'marital_status': forms.Select(attrs={'class': 'form-control'}),
            'nationality': forms.Select(attrs={'class': 'form-control'}),
            'ethnicity': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ethnicity (optional)'
            }),
            'religious_affiliation': forms.Select(attrs={'class': 'form-control'}),
            'national_id': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'National ID Number'
            }),
            'passport_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Passport Number (optional)'
            }),
            'photo': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set required fields
        required_fields = ['first_name', 'last_name', 'date_of_birth', 'gender']
        for field_name in required_fields:
            if field_name in self.fields:
                self.fields[field_name].required = True
        
        # Set up nationality choices with Uganda as default
        from django_countries import countries
        nationality_choices = [('', 'Select Nationality')] + [('UG', 'Uganda')] + [
            (code, name) for code, name in countries if code != 'UG'
        ]
        self.fields['nationality'].choices = nationality_choices
        if not self.is_bound:
            self.fields['nationality'].initial = 'UG'
        
        # Set up religious affiliation choices
        religious_choices = [('', 'Select Religious Affiliation')] + list(Staff.RELIGIOUS_AFFILIATION_CHOICES)
        self.fields['religious_affiliation'].choices = religious_choices
        
        # Set up marital status choices
        marital_choices = [('', 'Select Marital Status')] + list(Staff.MARITAL_STATUS_CHOICES)
        self.fields['marital_status'].choices = marital_choices
    
    def clean_first_name(self):
        value = self.cleaned_data.get('first_name')
        if value:
            value = ' '.join(value.strip().split()).title()
            if not re.match(r"^[a-zA-Z\s\-']+$", value):
                raise ValidationError("First name should only contain letters, spaces, hyphens, and apostrophes.")
            if len(value) < 2:
                raise ValidationError("First name must be at least 2 characters long.")
        return value
    
    def clean_last_name(self):
        value = self.cleaned_data.get('last_name')
        if value:
            value = ' '.join(value.strip().split()).title()
            if not re.match(r"^[a-zA-Z\s\-']+$", value):
                raise ValidationError("Last name should only contain letters, spaces, hyphens, and apostrophes.")
            if len(value) < 2:
                raise ValidationError("Last name must be at least 2 characters long.")
        return value
    
    def clean_date_of_birth(self):
        dob = self.cleaned_data.get('date_of_birth')
        if dob:
            today = date.today()
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            
            if dob > today:
                raise ValidationError("Date of birth cannot be in the future.")
            if age < 18:
                raise ValidationError("Staff member must be at least 18 years old.")
            if age > 75:
                raise ValidationError("Age seems unusually high. Please verify.")
        return dob


# =============================================================================
# STEP 2: CONTACT INFORMATION FORM
# =============================================================================

class StaffContactInfoForm(forms.Form):
    """Step 2: Contact information"""
    
    phone_number = forms.CharField(
        max_length=20,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '+256xxxxxxxxx',
            'type': 'tel'
        })
    )
    
    alternative_phone = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '+256xxxxxxxxx (optional)',
            'type': 'tel'
        })
    )
    
    personal_email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'email@example.com (optional)'
        })
    )
    
    # Emergency contact information
    emergency_contact_name = forms.CharField(
        max_length=100,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Emergency Contact Name'
        })
    )
    
    emergency_contact_relationship = forms.CharField(
        max_length=20,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Relationship (e.g., Spouse, Parent)'
        })
    )
    
    emergency_contact_phone = forms.CharField(
        max_length=20,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '+256xxxxxxxxx',
            'type': 'tel'
        })
    )
    
    emergency_contact_address = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Emergency contact address (optional)'
        })
    )


# =============================================================================
# STEP 3: EMPLOYMENT INFORMATION FORM
# =============================================================================

class StaffEmploymentInfoForm(forms.Form):
    """Step 3: Employment and department information"""
    
    staff_id = forms.CharField(
        max_length=30,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Will be auto-generated',
            'readonly': True,
            'style': 'background-color: #f8f9fa;'
        })
    )
    
    date_of_joining = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        }),
        help_text="Date when staff member joined the school"
    )
    
    employment_status = forms.ChoiceField(
        choices=Staff.EMPLOYMENT_STATUS_CHOICES,
        required=True,
        initial='FT',
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    primary_department = forms.ModelChoiceField(
        queryset=None,
        required=True,
        widget=forms.Select(attrs={'class': 'form-control'}),
        help_text="Primary department for this staff member"
    )
    
    date_of_leaving = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        }),
        help_text="Leave blank if staff is still employed"
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
        
        # Set default joining date
        if not self.is_bound:
            self.fields['date_of_joining'].initial = timezone.now().date()
        
        # Auto-generate staff ID
        if not self.is_bound:
            from .utils import generate_staff_id
            try:
                staff_id = generate_staff_id()
                self.fields['staff_id'].initial = staff_id
            except Exception as e:
                logger.error(f"Error generating staff ID: {e}")
    
    def clean_date_of_joining(self):
        date_of_joining = self.cleaned_data.get('date_of_joining')
        if date_of_joining:
            today = date.today()
            if date_of_joining > today:
                raise ValidationError("Date of joining cannot be in the future.")
            if date_of_joining < (today - timedelta(days=50*365)):
                raise ValidationError("Date of joining seems too far in the past. Please verify.")
        return date_of_joining
    
    def clean(self):
        cleaned_data = super().clean()
        date_of_joining = cleaned_data.get('date_of_joining')
        date_of_leaving = cleaned_data.get('date_of_leaving')
        
        if date_of_leaving and date_of_joining:
            if date_of_leaving < date_of_joining:
                self.add_error('date_of_leaving', 'Date of leaving cannot be before date of joining.')
        
        return cleaned_data


# =============================================================================
# STEP 4: QUALIFICATIONS & EXPERIENCE FORM
# =============================================================================

class StaffQualificationsForm(forms.Form):
    """Step 4: Educational qualifications and experience"""
    
    qualification = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 4,
            'placeholder': 'Educational qualifications (e.g., Bachelor of Education, Master\'s Degree)'
        }),
        help_text="List educational qualifications"
    )
    
    experience = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 4,
            'placeholder': 'Previous work experience'
        }),
        help_text="Describe previous work experience"
    )
    
    skills = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Professional skills (e.g., Computer literacy, Leadership, Communication)'
        }),
        help_text="List relevant skills"
    )
    
    languages_spoken = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Languages spoken (e.g., English, Luganda, Swahili)'
        }),
        help_text="List languages and proficiency levels"
    )
    
    professional_memberships = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Professional associations or memberships'
        })
    )
    
    certifications = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Professional certifications and licenses'
        })
    )


# =============================================================================
# STEP 5: BANKING & STATUTORY INFORMATION FORM
# =============================================================================

class StaffBankingInfoForm(forms.Form):
    """Step 5: Banking and statutory information"""
    
    # Banking information
    bank_account_name = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Account holder name'
        })
    )
    
    bank_account_number = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Bank account number'
        })
    )
    
    bank_name = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Bank name (e.g., Stanbic Bank)'
        })
    )
    
    bank_branch = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Bank branch'
        })
    )
    
    # Statutory information
    tax_identification_number = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'TIN (Tax Identification Number)'
        }),
        help_text="Uganda Revenue Authority TIN"
    )
    
    social_security_number = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'NSSF Number'
        }),
        help_text="National Social Security Fund Number"
    )
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Check if any banking info is provided
        bank_fields = ['bank_account_name', 'bank_account_number', 'bank_name', 'bank_branch']
        bank_info_provided = any(cleaned_data.get(field) for field in bank_fields)
        
        # If any banking info is provided, require account number and bank name
        if bank_info_provided:
            if not cleaned_data.get('bank_account_number'):
                self.add_error('bank_account_number', 'Bank account number is required when banking information is provided.')
            if not cleaned_data.get('bank_name'):
                self.add_error('bank_name', 'Bank name is required when banking information is provided.')
        
        return cleaned_data


# =============================================================================
# STEP 6: DESIGNATION & CONTRACT FORM
# =============================================================================

class StaffDesignationContractForm(forms.Form):
    """Step 6: Designation and contract setup (optional)"""
    
    create_designation = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="Assign a designation to this staff member"
    )
    
    designation = forms.ModelChoiceField(
        queryset=None,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'}),
        help_text="Primary designation/role"
    )
    
    is_primary_designation = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="Set as primary designation"
    )
    
    role_allowance = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        initial=0,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': '0.00',
            'step': '0.01'
        }),
        help_text="Role-specific allowance (optional)"
    )
    
    # Contract information
    create_contract = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="Create an employment contract"
    )
    
    contract_type = forms.ModelChoiceField(
        queryset=None,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'}),
        help_text="Type of employment contract"
    )
    
    contract_start_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        }),
        help_text="Contract start date"
    )
    
    contract_duration_months = forms.IntegerField(
        required=False,
        initial=12,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': 1,
            'max': 120
        }),
        help_text="Contract duration in months"
    )
    
    basic_salary = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': '0.00',
            'step': '0.01'
        }),
        help_text="Basic monthly salary"
    )
    
    job_title = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Job title for contract'
        })
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set querysets
        try:
            self.fields['designation'].queryset = Designation.objects.filter(
                is_active=True
            ).select_related('department').order_by('department__name', 'name')
            
            self.fields['contract_type'].queryset = ContractType.objects.filter(
                is_active=True
            ).order_by('name')
        except Exception as e:
            logger.error(f"Error setting queryset: {e}")
            self.fields['designation'].queryset = Designation.objects.none()
            self.fields['contract_type'].queryset = ContractType.objects.none()
        
        # Set default contract start date
        if not self.is_bound:
            self.fields['contract_start_date'].initial = timezone.now().date()
    
    def clean(self):
        cleaned_data = super().clean()
        create_designation = cleaned_data.get('create_designation', False)
        create_contract = cleaned_data.get('create_contract', False)
        
        # Validate designation fields
        if create_designation:
            if not cleaned_data.get('designation'):
                self.add_error('designation', 'Please select a designation.')
        
        # Validate contract fields
        if create_contract:
            required_contract_fields = {
                'contract_type': 'Please select a contract type.',
                'contract_start_date': 'Please provide a contract start date.',
                'basic_salary': 'Please provide a basic salary.',
                'job_title': 'Please provide a job title.'
            }
            
            for field, error_msg in required_contract_fields.items():
                if not cleaned_data.get(field):
                    self.add_error(field, error_msg)
        
        return cleaned_data


# =============================================================================
# STEP 7: CONFIRMATION FORM
# =============================================================================

class StaffConfirmationForm(forms.Form):
    """Step 7: Final confirmation"""
    
    confirm_creation = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="I confirm that all the information provided is correct"
    )
    
    send_welcome_email = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="Send welcome email to staff member (if email provided)"
    )
    
    additional_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 4,
            'placeholder': 'Any additional notes or comments (optional)'
        }),
        help_text="Optional notes for record keeping"
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
    'basic_info': 'Personal Information',
    'contact_info': 'Contact Information',
    'employment_info': 'Employment Details',
    'qualifications': 'Qualifications & Experience',
    'banking_info': 'Banking & Statutory Information',
    'designation_contract': 'Designation & Contract',
    'confirmation': 'Review & Confirmation'
}

# =============================================================================
# STAFF DESIGNATION FORM
# =============================================================================

class StaffDesignationForm(forms.ModelForm):
    """Form for assigning designations to staff"""
    
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
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'role_allowance': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'placeholder': '0.00'
            }),
            'assignment_type': forms.Select(attrs={'class': 'form-select'}),
            'assignment_order_number': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Assignment notes...'
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
        
        # Set default start date
        if not self.is_bound:
            self.fields['start_date'].initial = timezone.now().date()
    
    def clean_end_date(self):
        """Validate end date is after start date"""
        start_date = self.cleaned_data.get('start_date')
        end_date = self.cleaned_data.get('end_date')
        
        if start_date and end_date:
            if end_date < start_date:
                raise ValidationError("End date must be after start date.")
        
        return end_date


# =============================================================================
# TEACHER FORM
# =============================================================================

class TeacherForm(forms.ModelForm):
    """Form for creating/editing teacher profiles"""
    
    class Meta:
        model = Teacher
        fields = [
            'staff', 'specialization', 'teaching_philosophy',
            'max_hours_per_week', 'current_teaching_load',
            'preferred_academic_levels', 'qualified_subjects',
            'available_days', 'preferred_time_slots',
            'is_class_teacher', 'assigned_classes',
            'digital_literacy_level', 'can_teach_online'
        ]
        
        widgets = {
            'staff': forms.Select(attrs={'class': 'form-select'}),
            'specialization': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Subject specialization'
            }),
            'teaching_philosophy': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Teaching philosophy and approach...'
            }),
            'max_hours_per_week': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'max': 60
            }),
            'current_teaching_load': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'readonly': True,
                'style': 'background-color: #f8f9fa;'
            }),
            'preferred_academic_levels': forms.SelectMultiple(attrs={'class': 'form-select'}),
            'qualified_subjects': forms.SelectMultiple(attrs={'class': 'form-select'}),
            'available_days': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': '["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]'
            }),
            'preferred_time_slots': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': '["08:00-10:00", "10:00-12:00"]'
            }),
            'is_class_teacher': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'assigned_classes': forms.SelectMultiple(attrs={'class': 'form-select'}),
            'digital_literacy_level': forms.Select(attrs={'class': 'form-select'}),
            'can_teach_online': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Required fields
        self.fields['staff'].required = True
        
        # Filter staff to those not already teachers
        if self.instance.pk:
            self.fields['staff'].queryset = Staff.objects.filter(is_active=True)
        else:
            existing_teacher_staff_ids = Teacher.objects.values_list('staff_id', flat=True)
            self.fields['staff'].queryset = Staff.objects.filter(
                is_active=True
            ).exclude(id__in=existing_teacher_staff_ids)
        
        # Filter related fields
        self.fields['preferred_academic_levels'].queryset = AcademicLevel.objects.filter(is_active=True)
        self.fields['qualified_subjects'].queryset = Subject.objects.filter(is_active=True)
        self.fields['assigned_classes'].queryset = Class.objects.filter(is_active=True)