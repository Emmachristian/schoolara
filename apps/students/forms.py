# students/forms.py

"""
Student registration and management forms with timezone support.
Uses utils/forms for consistent behavior across the application.
"""

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django_countries import countries
from django.contrib.auth import get_user_model
from django.urls import reverse_lazy
import re
import logging

# Import base form utilities with timezone support ⭐
from utils.forms import (
    BootstrapFormMixin,
    HTMXFormMixin,
    HTMXFilterFormMixin,
    DateRangeFormMixin,
    RequiredFieldsMixin,
    BaseFilterForm,
    DateRangeFilterForm,
    DatePickerInput,
    PhoneInput,
    SearchInput,
    SelectWithDefault,
    validate_age,  # ⭐ Uses school timezone
    validate_phone_number,
    validate_future_date,  # ⭐ Uses school timezone
    validate_past_date,  # ⭐ Uses school timezone
)

from .models import Student, Guardian, StudentGuardian

User = get_user_model()
logger = logging.getLogger(__name__)


# =============================================================================
# STUDENT FILTER FORMS (HTMX SEARCH)
# =============================================================================

class StudentFilterForm(HTMXFilterFormMixin, BootstrapFormMixin, forms.Form):
    """
    HTMX-powered student filter form.
    All date validations use school timezone.
    
    Usage:
        form = StudentFilterForm(request.GET)
        if form.is_valid():
            # Apply filters to queryset
    """
    
    # Configuration
    htmx_get = 'students:student_search'  
    htmx_target = '#student-list'
    search_delay = 100  # 300ms debounce for search
    
    # Search field
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by name, admission number, email...'
        })
    )
    
    # Status filters
    enrollment_status = forms.ChoiceField(
        label='Enrollment Status',
        choices=[('', 'All Statuses')] + list(Student.ENROLLMENT_STATUS_CHOICES),
        required=False,
        widget=SelectWithDefault(default_label="All Statuses")
    )
    
    # Academic filters
    current_academic_level = forms.ModelChoiceField(
        label='Grade/Class',
        queryset=None,  # Set in __init__
        required=False,
        widget=SelectWithDefault(default_label="All Grades")
    )
    
    # Demographics
    gender = forms.ChoiceField(
        label='Gender',
        choices=[('', 'All')] + list(Student.GENDER_CHOICES),
        required=False,
        widget=SelectWithDefault(default_label="All")
    )
    
    religious_affiliation = forms.ChoiceField(
        label='Religion',
        choices=[('', 'All')] + list(Student.RELIGIOUS_AFFILIATION_CHOICES),
        required=False,
        widget=SelectWithDefault(default_label="All")
    )
    
    # Health filters
    health_condition = forms.ChoiceField(
        label='Health Condition',
        choices=[('', 'All')] + list(Student.HEALTH_CONDITION_CHOICES),
        required=False,
        widget=SelectWithDefault(default_label="All")
    )
    
    has_special_needs = forms.NullBooleanField(
        label='Special Needs',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Yes'),
            ('false', 'No')
        ], attrs={'class': 'form-select'})
    )
    
    # Transport
    transportation_required = forms.NullBooleanField(
        label='Requires Transport',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Yes'),
            ('false', 'No')
        ], attrs={'class': 'form-select'})
    )
    
    # Date range filters (uses school timezone) ⭐
    admission_date_from = forms.DateField(
        label='Admitted From',
        required=False,
        widget=DatePickerInput()
    )
    
    admission_date_to = forms.DateField(
        label='Admitted To',
        required=False,
        widget=DatePickerInput()
    )
    
    # Age range (calculated using school timezone) ⭐
    age_min = forms.IntegerField(
        label='Min Age',
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': 3,
            'max': 25,
            'placeholder': 'Min'
        })
    )
    
    age_max = forms.IntegerField(
        label='Max Age',
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': 3,
            'max': 25,
            'placeholder': 'Max'
        })
    )
    
    def __init__(self, *args, **kwargs):
        # ⭐ FIX: Extract search URL if provided
        search_url = kwargs.pop('search_url', None)
        if search_url:
            self.htmx_get = search_url
        
        super().__init__(*args, **kwargs)
        
        # Set academic level queryset
        try:
            from academics.models import AcademicLevel
            self.fields['current_academic_level'].queryset = AcademicLevel.objects.filter(
                is_active=True
            ).order_by('order')
        except Exception as e:
            logger.error(f"Error setting academic level queryset: {e}")
            self.fields['current_academic_level'].queryset = AcademicLevel.objects.none()
    
    def clean(self):
        """
        Validate filters using school timezone. ⭐
        """
        cleaned_data = super().clean()
        
        # Validate admission date range (uses school timezone)
        admission_from = cleaned_data.get('admission_date_from')
        admission_to = cleaned_data.get('admission_date_to')
        
        if admission_from and admission_to:
            if admission_from > admission_to:
                raise ValidationError({
                    'admission_date_to': 'End date must be after start date.'
                })
        
        # Validate age range
        age_min = cleaned_data.get('age_min')
        age_max = cleaned_data.get('age_max')
        
        if age_min and age_max:
            if age_min > age_max:
                raise ValidationError({
                    'age_max': 'Maximum age must be greater than minimum age.'
                })
        
        return cleaned_data


class StudentQuickSearchForm(BootstrapFormMixin, forms.Form):
    """
    Quick search form for students (name, admission number only).
    """
    
    q = forms.CharField(
        label='',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search students...',
            'autofocus': True
        })
    )
    
    def __init__(self, *args, **kwargs):
        search_url = kwargs.pop('search_url', None)
        super().__init__(*args, **kwargs)
        
        if search_url:
            self.fields['q'].widget.attrs.update({
                'hx-get': str(search_url),
                'hx-trigger': 'keyup changed delay:300ms, search',
                'hx-target': '#quick-search-results',
                'hx-indicator': '.htmx-indicator'
            })


# =============================================================================
# GUARDIAN FILTER FORM
# =============================================================================

class GuardianFilterForm(HTMXFilterFormMixin, BootstrapFormMixin, forms.Form):
    """
    HTMX-powered guardian filter form.
    """
    
    # Configuration
    htmx_get = 'students:guardian_search'  # ⭐ FIX: Use URL name
    htmx_target = '#guardian-list'
    search_delay = 300
    
    # Search field
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by name, phone, email...'
        })
    )
    
    # Guardian type filter
    guardian_type = forms.ChoiceField(
        label='Guardian Type',
        choices=[('', 'All Types')] + list(Guardian.GUARDIAN_TYPE_CHOICES),
        required=False,
        widget=SelectWithDefault(default_label="All Types")
    )
    
    # Gender filter
    gender = forms.ChoiceField(
        label='Gender',
        choices=[('', 'All')] + list(Guardian.GENDER_CHOICES),
        required=False,
        widget=SelectWithDefault(default_label="All")
    )
    
    # Active status
    is_active = forms.NullBooleanField(
        label='Active Status',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Active'),
            ('false', 'Inactive')
        ], attrs={'class': 'form-select'})
    )
    
    # Country filter
    country = forms.ChoiceField(
        label='Country',
        choices=[('', 'All Countries')] + list(countries),
        required=False,
        widget=SelectWithDefault(default_label="All Countries")
    )
    
    def __init__(self, *args, **kwargs):
        search_url = kwargs.pop('search_url', None)
        if search_url:
            self.htmx_get = search_url
        
        super().__init__(*args, **kwargs)


# =============================================================================
# STEP 1: BASIC INFORMATION FORM
# =============================================================================

class StudentBasicInfoForm(BootstrapFormMixin, RequiredFieldsMixin, forms.ModelForm):
    """
    Step 1: Basic personal information and admission details.
    Uses school timezone for all date validations. ⭐
    """
    
    # Override gender field to use radio buttons
    gender = forms.ChoiceField(
        label="Gender",
        choices=Student.GENDER_CHOICES,
        widget=forms.RadioSelect(),
        required=True
    )
    
    class Meta:
        model = Student
        fields = [
            'first_name', 'middle_name', 'last_name', 
            'admission_date', 'national_student_number', 'birth_certificate_number',
            'date_of_birth', 'gender', 'nationality', 'ethnicity', 
            'birth_place', 'birth_country', 'religious_affiliation',
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={'placeholder': 'First Name'}),
            'middle_name': forms.TextInput(attrs={'placeholder': 'Middle Name (optional)'}),
            'last_name': forms.TextInput(attrs={'placeholder': 'Last Name'}),
            'date_of_birth': DatePickerInput(),
            'admission_date': DatePickerInput(),
            'national_student_number': forms.TextInput(attrs={
                'placeholder': 'National Student Number (EMIS/UPI)'
            }),
            'birth_certificate_number': forms.TextInput(attrs={
                'placeholder': 'Birth Certificate Number'
            }),
            'ethnicity': forms.TextInput(attrs={'placeholder': 'Ethnicity'}),
            'religious_affiliation': forms.Select(),
            'birth_place': forms.TextInput(attrs={'placeholder': 'Place of Birth'}),
            'photo': forms.FileInput(attrs={'accept': 'image/*'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set required fields
        required_fields = ['first_name', 'last_name', 'admission_date', 'date_of_birth']
        for field_name in required_fields:
            if field_name in self.fields:
                self.fields[field_name].required = True
        
        # Set up nationality choices with blank option
        nationality_choices = [('', 'Select Nationality')] + list(countries)
        self.fields['nationality'].choices = nationality_choices
        
        # Set up religious affiliation choices
        religious_choices = [('', 'Select Religious Affiliation')] + list(
            Student.RELIGIOUS_AFFILIATION_CHOICES
        )
        self.fields['religious_affiliation'].choices = religious_choices
        
        # Set up birth country choices
        birth_country_choices = [('', 'Select Country')] + list(countries)
        self.fields['birth_country'].choices = birth_country_choices
        
        # Set default admission date to today (school timezone) ⭐
        if not self.is_bound and not self.instance.pk:
            from core.utils import get_school_today
            self.fields['admission_date'].initial = get_school_today()
    
    def clean_first_name(self):
        """Clean and validate first name"""
        value = self.cleaned_data.get('first_name')
        if value:
            value = ' '.join(value.strip().split()).title()
            if not re.match(r"^[a-zA-Z\s\-']+$", value):
                raise ValidationError(
                    "First name should only contain letters, spaces, hyphens, and apostrophes."
                )
            if len(value) < 2:
                raise ValidationError("First name must be at least 2 characters long.")
        return value
    
    def clean_last_name(self):
        """Clean and validate last name"""
        value = self.cleaned_data.get('last_name')
        if value:
            value = ' '.join(value.strip().split()).title()
            if not re.match(r"^[a-zA-Z\s\-']+$", value):
                raise ValidationError(
                    "Last name should only contain letters, spaces, hyphens, and apostrophes."
                )
            if len(value) < 2:
                raise ValidationError("Last name must be at least 2 characters long.")
        return value
    
    def clean_date_of_birth(self):
        """
        Validate date of birth using school timezone. ⭐
        """
        dob = self.cleaned_data.get('date_of_birth')
        if dob:
            # Validate not in future (uses school timezone) ⭐
            validate_future_date(dob)
            
            # Validate age (uses school timezone) ⭐
            validate_age(dob, min_age=2, max_age=30)
        
        return dob
    
    def clean_admission_date(self):
        """
        Validate admission date using school timezone. ⭐
        """
        admission_date = self.cleaned_data.get('admission_date')
        if admission_date:
            from core.utils import get_school_today
            from datetime import timedelta
            
            today = get_school_today()  # ⭐ USE SCHOOL TIMEZONE
            
            # Validate not in future
            if admission_date > today:
                raise ValidationError("Admission date cannot be in the future.")
            
            # Validate not too far in past (10 years)
            if admission_date < (today - timedelta(days=10*365)):
                raise ValidationError(
                    "Admission date seems too far in the past. Please verify."
                )
        
        return admission_date
    
    def clean(self):
        """
        Cross-field validation using school timezone. ⭐
        """
        cleaned_data = super().clean()
        dob = cleaned_data.get('date_of_birth')
        admission_date = cleaned_data.get('admission_date')
        
        # Validate admission date is after date of birth
        if dob and admission_date:
            if admission_date < dob:
                raise ValidationError({
                    'admission_date': 'Admission date cannot be before date of birth.'
                })
        
        return cleaned_data


# =============================================================================
# STEP 2: CONTACT & ADDRESS FORM
# =============================================================================

class StudentContactInfoForm(BootstrapFormMixin, forms.Form):
    """
    Step 2: Contact and address information.
    """
    
    personal_email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={
            'placeholder': 'personal@email.com (optional)'
        })
    )
    
    phone_number = forms.CharField(
        max_length=20,
        required=False,
        widget=PhoneInput(attrs={
            'placeholder': '+256xxxxxxxxx (optional)'
        })
    )
    
    home_address = forms.CharField(
        required=True,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'Complete home address including village/town'
        })
    )
    
    mailing_address = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'Mailing address (if different from home address)'
        })
    )
    
    district = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'District'})
    )
    
    region = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Region/Province'})
    )
    
    country_of_residence = forms.ChoiceField(
        choices=[('UG', 'Uganda')] + [
            (code, name) for code, name in countries if code != 'UG'
        ],
        initial='UG',
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    # Transportation fields
    transportation_required = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    transport_route = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Transport route'})
    )
    
    pickup_point = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Pickup point'})
    )
    
    pickup_time = forms.TimeField(
        required=False,
        widget=forms.TimeInput(attrs={
            'class': 'form-control',
            'type': 'time'
        })
    )
    
    def clean_phone_number(self):
        """Validate phone number"""
        phone = self.cleaned_data.get('phone_number')
        if phone:
            validate_phone_number(phone)
        return phone
    
    def clean(self):
        """Validate transportation fields"""
        cleaned_data = super().clean()
        transportation_required = cleaned_data.get('transportation_required', False)
        
        if transportation_required:
            transport_route = cleaned_data.get('transport_route')
            pickup_point = cleaned_data.get('pickup_point')
            
            if not transport_route:
                self.add_error(
                    'transport_route',
                    'Transport route is required when transportation is needed.'
                )
            if not pickup_point:
                self.add_error(
                    'pickup_point',
                    'Pickup point is required when transportation is needed.'
                )
        else:
            # Clear transport fields if not required
            cleaned_data['transport_route'] = ''
            cleaned_data['pickup_point'] = ''
            cleaned_data['pickup_time'] = None
        
        return cleaned_data


# =============================================================================
# STEP 3: ACADEMIC INFORMATION FORM
# =============================================================================

class StudentAcademicInfoForm(BootstrapFormMixin, forms.Form):
    """
    Step 3: Academic and educational information.
    """
    
    admission_academic_level = forms.ModelChoiceField(
        queryset=None,
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Academic level at time of admission"
    )
    
    current_academic_level = forms.ModelChoiceField(
        queryset=None,
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Current academic level"
    )
    
    enrollment_status = forms.ChoiceField(
        choices=Student.ENROLLMENT_STATUS_CHOICES,
        required=True,
        initial='ACTIVE',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    # Previous education
    previous_school = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Previous school name'})
    )
    
    previous_school_address = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 2,
            'placeholder': 'Previous school address'
        })
    )
    
    previous_academic_level = forms.ModelChoiceField(
        queryset=None,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Academic level completed at previous school"
    )
    
    transfer_certificate_number = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Transfer certificate number'})
    )
    
    previous_school_completion_date = forms.DateField(
        required=False,
        widget=DatePickerInput()
    )
    
    transfer_reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 2,
            'placeholder': 'Reason for transfer (if applicable)'
        })
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Import here to avoid circular imports
        try:
            from academics.models import AcademicLevel
            
            # Set querysets
            queryset = AcademicLevel.objects.filter(is_active=True).order_by('order')
            self.fields['admission_academic_level'].queryset = queryset
            self.fields['current_academic_level'].queryset = queryset
            self.fields['previous_academic_level'].queryset = queryset
        except Exception as e:
            logger.error(f"Error setting academic level queryset: {e}")
    
    def clean_previous_school_completion_date(self):
        """
        Validate completion date using school timezone. ⭐
        """
        completion_date = self.cleaned_data.get('previous_school_completion_date')
        if completion_date:
            # Validate not in future (uses school timezone) ⭐
            validate_future_date(completion_date)
        
        return completion_date


# =============================================================================
# STEP 4: HEALTH & MEDICAL FORM
# =============================================================================

class StudentHealthInfoForm(BootstrapFormMixin, forms.Form):
    """
    Step 4: Health and medical information (all optional).
    """
    
    health_condition = forms.ChoiceField(
        choices=Student.HEALTH_CONDITION_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    blood_type = forms.ChoiceField(
        choices=Student.BLOOD_TYPE_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    medical_conditions = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'Any existing medical conditions'
        })
    )
    
    allergies = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 2,
            'placeholder': 'Known allergies'
        })
    )
    
    medications = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 2,
            'placeholder': 'Current medications'
        })
    )
    
    special_medical_needs = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 2,
            'placeholder': 'Special medical needs or care instructions'
        })
    )
    
    emergency_medical_contact = forms.CharField(
        max_length=20,
        required=False,
        widget=PhoneInput(attrs={'placeholder': '+256xxxxxxxxx'})
    )
    
    preferred_hospital = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Preferred hospital/clinic'})
    )
    
    medical_insurance = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Medical insurance provider'})
    )
    
    insurance_policy_number = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Insurance policy number'})
    )
    
    # Special needs
    has_special_needs = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    special_needs_description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'Description of special needs'
        })
    )
    
    learning_disabilities = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 2,
            'placeholder': 'Learning disabilities or challenges'
        })
    )
    
    learning_accommodations = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 2,
            'placeholder': 'Required learning accommodations'
        })
    )
    
    # Special diet
    requires_special_diet = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    special_diet_details = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 2,
            'placeholder': 'Special diet requirements'
        })
    )
    
    def clean_emergency_medical_contact(self):
        """Validate emergency contact phone"""
        phone = self.cleaned_data.get('emergency_medical_contact')
        if phone:
            validate_phone_number(phone)
        return phone
    
    def clean(self):
        """Clear dependent fields when parent field is False"""
        cleaned_data = super().clean()
        
        # Clear special needs fields if not needed
        if not cleaned_data.get('has_special_needs', False):
            cleaned_data['special_needs_description'] = ''
            cleaned_data['learning_disabilities'] = ''
            cleaned_data['learning_accommodations'] = ''
        
        # Clear special diet fields if not needed
        if not cleaned_data.get('requires_special_diet', False):
            cleaned_data['special_diet_details'] = ''
        
        return cleaned_data


# =============================================================================
# STEP 5: GUARDIAN INFORMATION FORM
# =============================================================================

class StudentGuardianInfoForm(BootstrapFormMixin, forms.Form):
    """
    Step 5: Guardian information.
    """
    
    guardian_option = forms.ChoiceField(
        choices=[
            ('new', 'Add New Guardian'),
            ('existing', 'Select Existing Guardian')
        ],
        required=True,
        widget=forms.RadioSelect(),
        initial='new'
    )
    
    existing_guardian = forms.ModelChoiceField(
        queryset=None,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    # New guardian fields
    guardian_first_name = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Guardian first name'})
    )
    
    guardian_last_name = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Guardian last name'})
    )
    
    guardian_phone = forms.CharField(
        max_length=20,
        required=False,
        widget=PhoneInput(attrs={'placeholder': '+256xxxxxxxxx'})
    )
    
    guardian_email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={'placeholder': 'guardian@example.com'})
    )
    
    guardian_address = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 2,
            'placeholder': 'Guardian address'
        })
    )
    
    guardian_occupation = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Occupation'})
    )
    
    # Relationship details
    relationship = forms.ChoiceField(
        choices=[('', 'Select Relationship')] + list(StudentGuardian.RELATIONSHIP_CHOICES),
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        
        # Set up existing guardian queryset
        try:
            self.fields['existing_guardian'].queryset = Guardian.objects.filter(
                is_active=True
            ).order_by('last_name', 'first_name')
        except Exception as e:
            logger.error(f"Error setting guardian queryset: {e}")
            self.fields['existing_guardian'].queryset = Guardian.objects.none()
    
    def clean_guardian_phone(self):
        """Validate guardian phone"""
        phone = self.cleaned_data.get('guardian_phone')
        if phone:
            validate_phone_number(phone)
        return phone

    def clean(self):
        """Validate based on guardian option"""
        cleaned_data = super().clean()
        guardian_option = cleaned_data.get('guardian_option')
        
        if guardian_option == 'existing':
            existing_guardian = cleaned_data.get('existing_guardian')
            if not existing_guardian:
                raise ValidationError({
                    'existing_guardian': 'Please select an existing guardian.'
                })
        else:
            # Validate new guardian fields
            required_fields = [
                'guardian_first_name', 
                'guardian_last_name', 
                'guardian_phone'
            ]
            errors = {}
            
            for field in required_fields:
                if not cleaned_data.get(field):
                    field_display = field.replace("guardian_", "").replace("_", " ").title()
                    errors[field] = (
                        f'{field_display} is required when adding a new guardian.'
                    )
            
            if errors:
                raise ValidationError(errors)
        
        # Validate relationship
        if not cleaned_data.get('relationship'):
            raise ValidationError({
                'relationship': 'Please select the relationship between guardian and student.'
            })
        
        return cleaned_data


# =============================================================================
# STEP 6: CONFIRMATION FORM
# =============================================================================

class StudentConfirmationForm(BootstrapFormMixin, forms.Form):
    """
    Step 6: Final confirmation.
    """
    
    confirm_creation = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="I confirm that all the information provided is correct"
    )
    
    additional_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 4,
            'placeholder': 'Any additional notes or comments (optional)'
        }),
        help_text="Optional notes for record keeping"
    )


# =============================================================================
# WIZARD CONFIGURATION
# =============================================================================

STUDENT_WIZARD_FORMS = [
    ("basic_info", StudentBasicInfoForm),
    ("contact_info", StudentContactInfoForm),
    ("academic_info", StudentAcademicInfoForm),
    ("health_info", StudentHealthInfoForm),
    ("guardian_info", StudentGuardianInfoForm),
    ("confirmation", StudentConfirmationForm),
]

STUDENT_WIZARD_STEP_NAMES = {
    'basic_info': 'Personal & Admission Information',
    'contact_info': 'Contact & Address Information',
    'academic_info': 'Academic Information',
    'health_info': 'Health & Medical Information',
    'guardian_info': 'Guardian Information',
    'confirmation': 'Review & Confirmation'
}


# =============================================================================
# GENERAL STUDENT FORM (SINGLE PAGE)
# =============================================================================

class StudentForm(BootstrapFormMixin, RequiredFieldsMixin, forms.ModelForm):
    """
    Complete student form (all fields in one page).
    Uses school timezone for all date validations. ⭐
    """

    religious_affiliation = forms.ChoiceField(
        choices=Student.RELIGIOUS_AFFILIATION_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = Student
        fields = [
            # Identification & Basic Info
            'admission_number', 'admission_date', 'national_student_number',
            'birth_certificate_number', 'first_name', 'middle_name', 'last_name',
            'date_of_birth', 'gender',
            
            # Academic Information
            'current_academic_level', 'admission_academic_level',
            
            # Demographics & Cultural Info
            'nationality', 'ethnicity', 'birth_place', 'birth_country',
            'religious_affiliation',
            
            # Contact & Address Information
            'personal_email', 'phone_number', 'home_address', 'mailing_address',
            'district', 'region', 'country_of_residence',
            
            # Health & Medical Information
            'health_condition', 'blood_type', 'medical_conditions', 'allergies',
            'medications', 'special_medical_needs', 'emergency_medical_contact',
            'preferred_hospital', 'medical_insurance', 'insurance_policy_number',
            
            # Special Needs & Accommodations
            'has_special_needs', 'special_needs_description', 'requires_special_diet',
            'special_diet_details', 'learning_disabilities', 'learning_accommodations',
            
            # Transport Information
            'transportation_required', 'transport_route', 'pickup_point', 'pickup_time',
            
            # Previous Education
            'previous_school', 'previous_school_address', 'previous_academic_level',
            'transfer_reason', 'transfer_certificate_number',
            'previous_school_completion_date',
            
            # Media & Documents
            'photo',
            
            # Status & Tracking
            'enrollment_status', 'graduation_date', 'withdrawal_date',
        ]

        widgets = {
            'admission_number': forms.TextInput(attrs={'class': 'form-control'}),
            'admission_date': DatePickerInput(),
            'date_of_birth': DatePickerInput(),
            'gender': forms.Select(choices=Student.GENDER_CHOICES, attrs={'class': 'form-select'}),
            'photo': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'graduation_date': DatePickerInput(),
            'withdrawal_date': DatePickerInput(),
            'previous_school_completion_date': DatePickerInput(),
            'pickup_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        from academics.models import AcademicLevel
        
        # Set up academic level querysets
        try:
            queryset = AcademicLevel.objects.filter(is_active=True).order_by('order')
            self.fields['admission_academic_level'].queryset = queryset
            self.fields['current_academic_level'].queryset = queryset
            self.fields['previous_academic_level'].queryset = queryset
        except Exception as e:
            logger.error(f"Error setting academic level queryset: {e}")
        
        # Set up nationality choices
        nationality_choices = [('UG', 'Uganda')] + [
            (code, name) for code, name in countries if code != 'UG'
        ]
        self.fields['nationality'].choices = nationality_choices
        self.fields['nationality'].initial = 'UG'
        
        # Set default admission date (school timezone) ⭐
        if not self.is_bound and not self.instance.pk:
            from core.utils import get_school_today
            self.fields['admission_date'].initial = get_school_today()
    
    def clean_date_of_birth(self):
        """Validate DOB using school timezone ⭐"""
        dob = self.cleaned_data.get('date_of_birth')
        if dob:
            validate_future_date(dob)
            validate_age(dob, min_age=2, max_age=30)
        return dob
    
    def clean_admission_date(self):
        """Validate admission date using school timezone ⭐"""
        admission_date = self.cleaned_data.get('admission_date')
        if admission_date:
            from core.utils import get_school_today
            from datetime import timedelta
            
            today = get_school_today()  # ⭐
            
            if admission_date > today:
                raise ValidationError("Admission date cannot be in the future.")
            
            if admission_date < (today - timedelta(days=10*365)):
                raise ValidationError("Admission date seems too far in the past.")
        
        return admission_date


# =============================================================================
# GUARDIAN FORM
# =============================================================================

class GuardianForm(BootstrapFormMixin, RequiredFieldsMixin, forms.ModelForm):
    """
    Form for creating/editing guardians.
    Uses school timezone for date validations. ⭐
    """
    
    class Meta:
        model = Guardian
        fields = [
            'first_name', 'middle_name', 'last_name', 'gender', 'guardian_type',
            'date_of_birth', 'primary_phone', 'secondary_phone', 'email',
            'occupation', 'employer', 'work_phone', 'monthly_income',
            'home_address', 'work_address', 'district', 'city', 'country',
            'national_id', 'passport_number', 'photo', 'is_active',
        ]
        widgets = {
            'date_of_birth': DatePickerInput(),
            'gender': forms.RadioSelect(choices=Guardian.GENDER_CHOICES),
            'primary_phone': PhoneInput(),
            'secondary_phone': PhoneInput(),
            'work_phone': PhoneInput(),
            'monthly_income': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'photo': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set required fields
        self.fields['first_name'].required = True
        self.fields['last_name'].required = True
        self.fields['primary_phone'].required = True
        self.fields['home_address'].required = True
    
    def clean_date_of_birth(self):
        """Validate DOB using school timezone ⭐"""
        dob = self.cleaned_data.get('date_of_birth')
        if dob:
            validate_future_date(dob)
            validate_age(dob, min_age=18, max_age=100)
        return dob


# =============================================================================
# STUDENT-GUARDIAN RELATIONSHIP FORM
# =============================================================================

class StudentGuardianForm(BootstrapFormMixin, forms.ModelForm):
    """
    Form for managing student-guardian relationships.
    Uses school timezone for date validations. ⭐
    """
    
    class Meta:
        model = StudentGuardian
        fields = [
            'student', 'guardian', 'relationship',
            'is_primary', 'is_financial_responsible', 'can_pickup',
            'can_authorize_medical', 'emergency_contact_priority',
            'has_custody', 'custody_percentage',
            'receives_academic_reports', 'receives_financial_statements',
            'receives_emergency_notifications', 'is_active',
            'relationship_start_date', 'relationship_end_date', 'notes',
        ]
        widgets = {
            'relationship_start_date': DatePickerInput(),
            'relationship_end_date': DatePickerInput(),
            'emergency_contact_priority': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'max': '999'
            }),
            'custody_percentage': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'max': '100',
                'step': '0.01'
            }),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }
    
    def clean_relationship_start_date(self):
        """Validate start date using school timezone ⭐"""
        start_date = self.cleaned_data.get('relationship_start_date')
        if start_date:
            validate_future_date(start_date)
        return start_date
    
    def clean(self):
        """Validate date range using school timezone ⭐"""
        cleaned_data = super().clean()
        start_date = cleaned_data.get('relationship_start_date')
        end_date = cleaned_data.get('relationship_end_date')
        
        if start_date and end_date:
            if end_date < start_date:
                raise ValidationError({
                    'relationship_end_date': 'End date cannot be before start date.'
                })
        
        return cleaned_data