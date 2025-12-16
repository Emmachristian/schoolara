# students/forms.py

from django import forms
from django.core.exceptions import ValidationError
from .models import Student, Guardian
import re
import logging
from django.utils import timezone
from datetime import date, timedelta
from django_countries import countries
logger = logging.getLogger(__name__)

# =============================================================================
# STEP 1: BASIC INFORMATION FORM
# =============================================================================

class StudentBasicInfoForm(forms.ModelForm):
    """Step 1: Basic personal information and admission details"""
    
    # Override gender field to use ChoiceField instead of ModelChoiceField
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
            'admission_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'national_student_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'National Student Number (EMIS/UPI)'
            }),
            'birth_certificate_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Birth Certificate Number'
            }),
            'nationality': forms.Select(attrs={'class': 'form-control'}),
            'ethnicity': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ethnicity'
            }),
            'religious_affiliation': forms.Select(attrs={'class': 'form-control'}),
            'birth_place': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Place of Birth'
            }),
            'birth_country': forms.Select(attrs={'class': 'form-control'}),
            'photo': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set required fields
        required_fields = ['first_name', 'last_name', 'admission_date', 'date_of_birth']
        for field_name in required_fields:
            if field_name in self.fields:
                self.fields[field_name].required = True
        
        # Set up nationality choices **with a blank option first**
        nationality_choices = [('', 'Select Nationality')] + list(countries)
        self.fields['nationality'].choices = nationality_choices
        
        # Set up religious affiliation choices
        religious_choices = [('', 'Select Religious Affiliation')] + list(Student.RELIGIOUS_AFFILIATION_CHOICES)
        self.fields['religious_affiliation'].choices = religious_choices
        
        # Set up birth country choices
        birth_country_choices = [('', 'Select Country')] + list(countries)
        self.fields['birth_country'].choices = birth_country_choices
        
        # Set default admission date
        if not self.is_bound:
            self.fields['admission_date'].initial = timezone.now().date()
    
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
            if age < 2:
                raise ValidationError("Student must be at least 2 years old.")
            if age > 30:
                raise ValidationError("Student age seems unusually high. Please verify.")
        return dob
    
    def clean_admission_date(self):
        admission_date = self.cleaned_data.get('admission_date')
        if admission_date:
            today = date.today()
            if admission_date > today:
                raise ValidationError("Admission date cannot be in the future.")
            if admission_date < (today - timedelta(days=10*365)):
                raise ValidationError("Admission date seems too far in the past. Please verify.")
        return admission_date

# =============================================================================
# STEP 2: CONTACT & ADDRESS FORM
# =============================================================================

class StudentContactInfoForm(forms.Form):
    """Step 2: Contact and address information"""
    
    personal_email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'personal@email.com (optional)'
        })
    )
    
    phone_number = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '+256xxxxxxxxx (optional)',
            'type': 'tel'
        })
    )
    
    home_address = forms.CharField(
        required=True,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Complete home address including village/town'
        })
    )
    
    mailing_address = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Mailing address (if different from home address)'
        })
    )
    
    district = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'District'
        })
    )
    
    region = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Region/Province'
        })
    )
    
    country_of_residence = forms.ChoiceField(
        choices=[('UG', 'Uganda')] + [(code, name) for code, name in countries if code != 'UG'],
        initial='UG',
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    # Transportation fields
    transportation_required = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    transport_route = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Transport route'
        })
    )
    
    pickup_point = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Pickup point'
        })
    )
    
    pickup_time = forms.TimeField(
        required=False,
        widget=forms.TimeInput(attrs={
            'class': 'form-control',
            'type': 'time'
        })
    )
    
    def clean(self):
        cleaned_data = super().clean()
        transportation_required = cleaned_data.get('transportation_required', False)
        
        if transportation_required:
            transport_route = cleaned_data.get('transport_route')
            pickup_point = cleaned_data.get('pickup_point')
            
            if not transport_route:
                self.add_error('transport_route', 'Transport route is required when transportation is needed.')
            if not pickup_point:
                self.add_error('pickup_point', 'Pickup point is required when transportation is needed.')
        else:
            cleaned_data['transport_route'] = ''
            cleaned_data['pickup_point'] = ''
            cleaned_data['pickup_time'] = None
        
        return cleaned_data

# =============================================================================
# STEP 3: ACADEMIC INFORMATION FORM
# =============================================================================

class StudentAcademicInfoForm(forms.Form):
    """Step 3: Academic and educational information"""
    
    admission_academic_level = forms.ModelChoiceField(
        queryset=None,
        required=True,
        widget=forms.Select(attrs={'class': 'form-control'}),
        help_text="Academic level at time of admission"
    )
    
    current_academic_level = forms.ModelChoiceField(
        queryset=None,
        required=True,
        widget=forms.Select(attrs={'class': 'form-control'}),
        help_text="Current academic level"
    )
    
    enrollment_status = forms.ChoiceField(
        choices=Student.ENROLLMENT_STATUS_CHOICES,
        required=True,
        initial='active',
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    # Previous education
    previous_school = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Previous school name'
        })
    )
    
    previous_school_address = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Previous school address'
        })
    )
    
    previous_academic_level = forms.ModelChoiceField(
        queryset=None,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'}),
        help_text="Academic level completed at previous school"
    )
    
    transfer_certificate_number = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Transfer certificate number'
        })
    )
    
    previous_school_completion_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    
    transfer_reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Reason for transfer (if applicable)'
        })
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Import here to avoid circular imports
        from academics.models import AcademicLevel
        
        # Set querysets
        try:
            queryset = AcademicLevel.objects.filter(is_active=True).order_by('order')
            self.fields['admission_academic_level'].queryset = queryset
            self.fields['current_academic_level'].queryset = queryset
            self.fields['previous_academic_level'].queryset = queryset
        except Exception as e:
            logger.error(f"Error setting academic level queryset: {e}")

# =============================================================================
# STEP 4: HEALTH & MEDICAL FORM
# =============================================================================

class StudentHealthInfoForm(forms.Form):
    """Step 4: Health and medical information (all optional)"""
    
    health_condition = forms.ChoiceField(
        choices=Student.HEALTH_CONDITION_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    blood_type = forms.ChoiceField(
        choices=Student.BLOOD_TYPE_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    medical_conditions = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Any existing medical conditions'
        })
    )
    
    allergies = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Known allergies'
        })
    )
    
    medications = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Current medications'
        })
    )
    
    special_medical_needs = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Special medical needs or care instructions'
        })
    )
    
    emergency_medical_contact = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '+256xxxxxxxxx',
            'type': 'tel'
        })
    )
    
    preferred_hospital = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Preferred hospital/clinic'
        })
    )
    
    medical_insurance = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Medical insurance provider'
        })
    )
    
    insurance_policy_number = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Insurance policy number'
        })
    )
    
    # Special needs
    has_special_needs = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    special_needs_description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Description of special needs'
        })
    )
    
    learning_disabilities = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Learning disabilities or challenges'
        })
    )
    
    learning_accommodations = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
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
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Special diet requirements'
        })
    )
    
    def clean(self):
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

class StudentGuardianInfoForm(forms.Form):
    """Step 5: Guardian information"""
    
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
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    # New guardian fields
    guardian_first_name = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Guardian first name'
        })
    )
    
    guardian_last_name = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Guardian last name'
        })
    )
    
    guardian_phone = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '+256xxxxxxxxx',
            'type': 'tel'
        })
    )
    
    guardian_email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'guardian@example.com'
        })
    )
    
    guardian_address = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Guardian address'
        })
    )
    
    guardian_occupation = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Occupation'
        })
    )
    
    # Relationship details
    relationship = forms.ChoiceField(
        choices=[('', 'Select Relationship')] + list(Guardian.RELATION_CHOICES),
        required=True,
        widget=forms.Select(attrs={'class': 'form-control'})
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

    def clean(self):
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
            required_fields = ['guardian_first_name', 'guardian_last_name', 'guardian_phone']
            errors = {}
            
            for field in required_fields:
                if not cleaned_data.get(field):
                    field_display = field.replace("guardian_", "").replace("_", " ").title()
                    errors[field] = f'{field_display} is required when adding a new guardian.'
            
            if errors:
                raise ValidationError(errors)
        
        # Validate relationship
        if not cleaned_data.get('relationship'):
            raise ValidationError({
                'relationship': 'Please select the relationship between the guardian and student.'
            })
        
        return cleaned_data

# =============================================================================
# STEP 6: CONFIRMATION FORM
# =============================================================================

class StudentConfirmationForm(forms.Form):
    """Step 6: Final confirmation"""
    
    confirm_creation = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="I confirm that all the information provided is correct"
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
# GENERAL STUDENT FORM
# =============================================================================

class StudentForm(forms.ModelForm):

    religious_affiliation = forms.ChoiceField(
        choices=Student.RELIGIOUS_AFFILIATION_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = Student
        fields = [
            # Identification & Basic Info
            'admission_number',
            'admission_date',
            'national_student_number',
            'birth_certificate_number',
            'first_name',
            'middle_name',
            'last_name',
            'date_of_birth',
            'gender',

            # Academic Information
            'current_academic_level',
            'admission_academic_level',

            # Demographics & Cultural Info
            'nationality',
            'ethnicity',
            'birth_place',
            'birth_country',
            'religious_affiliation',

            # Contact & Address Information
            'personal_email',
            'phone_number',
            'home_address',
            'mailing_address',
            'district',
            'region',
            'country_of_residence',

            # Health & Medical Information
            'health_condition',
            'blood_type',
            'medical_conditions',
            'allergies',
            'medications',
            'special_medical_needs',
            'emergency_medical_contact',
            'preferred_hospital',
            'medical_insurance',
            'insurance_policy_number',

            # Special Needs & Accommodations
            'has_special_needs',
            'special_needs_description',
            'requires_special_diet',
            'special_diet_details',
            'learning_disabilities',
            'learning_accommodations',

            # Transport Information
            'transportation_required',
            'transport_route',
            'pickup_point',
            'pickup_time',

            # Previous Education
            'previous_school',
            'previous_school_address',
            'previous_academic_level',
            'transfer_reason',
            'transfer_certificate_number',
            'previous_school_completion_date',

            # Media & Documents
            'photo',

            # Guardian Relationships
            'guardians',

            # Status & Tracking
            'enrollment_status',
            'graduation_date',
            'withdrawal_date',
        ]

        widgets = {
            'admission_number': forms.TextInput(attrs={'class': 'form-control'}),
            'admission_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'national_student_number': forms.TextInput(attrs={'class': 'form-control'}),
            'birth_certificate_number': forms.TextInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'middle_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'date_of_birth': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'gender': forms.Select(choices=Student.GENDER_CHOICES,  attrs={'class': 'form-control'}),
            'current_academic_level': forms.Select(attrs={'class': 'form-select'}),
            'admission_academic_level': forms.Select(attrs={'class': 'form-select'}),
            'nationality': forms.Select(attrs={'class': 'form-select'}),
            'ethnicity': forms.TextInput(attrs={'class': 'form-control'}),
            'birth_place': forms.TextInput(attrs={'class': 'form-control'}),
            'birth_country': forms.Select(attrs={'class': 'form-select'}),
            'personal_email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
            'home_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'mailing_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'district': forms.TextInput(attrs={'class': 'form-control'}),
            'region': forms.TextInput(attrs={'class': 'form-control'}),
            'country_of_residence': forms.Select(attrs={'class': 'form-select'}),
            'health_condition': forms.Select(choices=Student.HEALTH_CONDITION_CHOICES, attrs={'class': 'form-select'}),
            'blood_type': forms.Select(choices=Student.BLOOD_TYPE_CHOICES, attrs={'class': 'form-select'}),
            'medical_conditions': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'allergies': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'medications': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'special_medical_needs': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'emergency_medical_contact': forms.TextInput(attrs={'class': 'form-control'}),
            'preferred_hospital': forms.TextInput(attrs={'class': 'form-control'}),
            'medical_insurance': forms.TextInput(attrs={'class': 'form-control'}),
            'insurance_policy_number': forms.TextInput(attrs={'class': 'form-control'}),
            'has_special_needs': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'special_needs_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'requires_special_diet': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'special_diet_details': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'learning_disabilities': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'learning_accommodations': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'transportation_required': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'transport_route': forms.TextInput(attrs={'class': 'form-control'}),
            'pickup_point': forms.TextInput(attrs={'class': 'form-control'}),
            'pickup_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'previous_school': forms.TextInput(attrs={'class': 'form-control'}),
            'previous_school_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'previous_academic_level': forms.Select(attrs={'class': 'form-select'}),
            'transfer_reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'transfer_certificate_number': forms.TextInput(attrs={'class': 'form-control'}),
            'previous_school_completion_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'photo': forms.FileInput(attrs={'class': 'form-control'}),
            'guardians': forms.SelectMultiple(attrs={'class': 'form-select'}),
            'enrollment_status': forms.Select(choices=Student.ENROLLMENT_STATUS_CHOICES, attrs={'class': 'form-select'}),
            'graduation_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'withdrawal_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        from academics.models import AcademicLevel
        # Dynamic queryset for admission_academic_level
        self.fields['admission_academic_level'].queryset = AcademicLevel.objects.filter(is_active=True).order_by('order')
        self.fields['admission_academic_level'].required = True
        self.fields['admission_academic_level'].help_text = "Academic level at time of admission"

        # Dynamic queryset for current_academic_level
        self.fields['current_academic_level'].queryset = AcademicLevel.objects.filter(is_active=True).order_by('order')
        self.fields['current_academic_level'].required = True
        self.fields['current_academic_level'].help_text = "Current academic level of the student"

        # Set up nationality choices with Uganda as default
        nationality_choices = [('UG', 'Uganda')] + [(code, name) for code, name in countries if code != 'UG']
        self.fields['nationality'].choices = nationality_choices
        self.fields['nationality'].initial = 'UG'

        # Auto-generate admission number for new instances only
        if not self.instance.pk and not self.is_bound:
            from .utils import generate_student_admission_number
            admission_number = generate_student_admission_number(user=getattr(self, 'user', None))
            self.fields['admission_number'].initial = admission_number
        
        # Set default admission date
        if not self.is_bound:
            self.fields['admission_date'].initial = timezone.now().date()

class GuardianForm(forms.ModelForm):
    class Meta:
        model = Guardian
        fields = [
            'first_name',
            'middle_name',
            'last_name',
            'gender',
            'guardian_type',
            'date_of_birth',
            'primary_phone',
            'secondary_phone',
            'email',
            'occupation',
            'employer',
            'work_phone',
            'monthly_income',
            'home_address',
            'work_address',
            'national_id',
            'passport_number',
            'photo',
            'is_active',
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First Name'}),
            'middle_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Middle Name'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last Name'}),
            'gender': forms.RadioSelect(choices=Guardian.GENDER_CHOICES, attrs={'class': 'custom-radio-buttons'}),
            'guardian_type': forms.Select(choices=Guardian.GUARDIAN_TYPE_CHOICES, attrs={'class': 'form-select'}),
            'date_of_birth': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'primary_phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Primary Phone'}),
            'secondary_phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Secondary Phone'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email'}),
            'occupation': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Occupation'}),
            'employer': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Employer'}),
            'work_phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Work Phone'}),
            'monthly_income': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Monthly Income'}),
            'home_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Home Address'}),
            'work_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Work Address'}),
            'national_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'National ID'}),
            'passport_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Passport Number'}),
            'photo': forms.FileInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Optional: mark some fields as required
        self.fields['first_name'].required = True
        self.fields['last_name'].required = True
        self.fields['primary_phone'].required = True
        self.fields['home_address'].required = True