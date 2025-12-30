# boarding/forms.py

"""
Boarding management forms with timezone support and HTMX filters.
All date validations use school timezone for consistency.
"""

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import Q
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
    DateTimePickerInput,
    SearchInput,
    SelectWithDefault,
    PhoneNumberField,
    PhoneInput,
    validate_future_date,  # ⭐ Uses school timezone
    validate_past_date,  # ⭐ Uses school timezone
    validate_date_not_before,  # ⭐ Uses school timezone
    validate_date_not_after,  # ⭐ Uses school timezone
    validate_phone_number,
)

from .models import Dormitory, BoardingEnrollment
from students.models import Student, Guardian
from academics.models import AcademicSession
from hr.models import Staff

logger = logging.getLogger(__name__)


# =============================================================================
# DORMITORY FORMS
# =============================================================================

class DormitoryForm(RequiredFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """
    Form for creating/editing dormitories.
    Uses school timezone for maintenance date validations. ⭐
    """
    
    class Meta:
        model = Dormitory
        fields = [
            'name', 'code', 'dormitory_type', 'description',
            'building', 'floor', 'wing',
            'total_capacity', 'room_count', 'beds_per_room',
            'has_bathroom', 'has_study_area', 'has_common_room', 
            'has_laundry', 'has_kitchen', 'has_wifi', 'has_security',
            'facilities_description',
            'dormitory_master', 'assistant_dormitory_master',
            'is_active', 'is_available_for_new_admissions',
            'maintenance_status', 'last_maintenance_date', 'next_maintenance_due',
            'rules_and_regulations', 'emergency_procedures',
            'dormitory_phone', 'dormitory_email', 'notes',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'e.g., Boys Dormitory A'
            }),
            'code': forms.TextInput(attrs={
                'placeholder': 'e.g., DORM-B-A',
                'style': 'text-transform: uppercase;'
            }),
            'dormitory_type': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Brief description of the dormitory...'
            }),
            'building': forms.TextInput(attrs={
                'placeholder': 'e.g., Main Building, Block A'
            }),
            'floor': forms.TextInput(attrs={
                'placeholder': 'e.g., Ground Floor, 2nd Floor'
            }),
            'wing': forms.TextInput(attrs={
                'placeholder': 'e.g., East Wing, North Section'
            }),
            'total_capacity': forms.NumberInput(attrs={
                'min': '1',
                'placeholder': 'Total number of beds'
            }),
            'room_count': forms.NumberInput(attrs={
                'min': '0',
                'placeholder': 'Number of rooms'
            }),
            'beds_per_room': forms.NumberInput(attrs={
                'min': '1',
                'placeholder': 'Average beds per room'
            }),
            'facilities_description': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Describe available facilities...'
            }),
            'dormitory_master': forms.Select(attrs={'class': 'form-select'}),
            'assistant_dormitory_master': forms.Select(attrs={'class': 'form-select'}),
            'maintenance_status': forms.Select(attrs={'class': 'form-select'}),
            'last_maintenance_date': DatePickerInput(),
            'next_maintenance_due': DatePickerInput(),
            'rules_and_regulations': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': 'List dormitory rules and regulations...'
            }),
            'emergency_procedures': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': 'Describe emergency procedures and contact information...'
            }),
            'dormitory_phone': PhoneInput(attrs={
                'placeholder': '+256700000000'
            }),
            'dormitory_email': forms.EmailInput(attrs={
                'placeholder': 'dormitory@school.com'
            }),
            'notes': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Internal administrative notes...'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Filter staff queryset for dormitory masters
        try:
            active_staff = Staff.objects.filter(is_active=True).order_by('first_name', 'last_name')
            self.fields['dormitory_master'].queryset = active_staff
            self.fields['assistant_dormitory_master'].queryset = active_staff
        except Exception as e:
            logger.error(f"Error setting staff queryset: {e}")
        
        # Set help text
        self.fields['code'].help_text = "Unique code for the dormitory (e.g., DORM-B-A)"
        self.fields['total_capacity'].help_text = "Maximum number of students that can be accommodated"
        self.fields['current_occupancy'].help_text = "Auto-calculated based on active enrollments"
    
    def clean_code(self):
        """Ensure dormitory code is uppercase"""
        code = self.cleaned_data.get('code', '')
        return code.upper()
    
    def clean(self):
        """Validate dormitory data using school timezone ⭐"""
        cleaned_data = super().clean()
        
        # Validate maintenance dates (uses school timezone) ⭐
        last_maintenance = cleaned_data.get('last_maintenance_date')
        next_maintenance = cleaned_data.get('next_maintenance_due')
        
        if last_maintenance and next_maintenance:
            if next_maintenance < last_maintenance:
                raise ValidationError({
                    'next_maintenance_due': 'Next maintenance date cannot be before last maintenance date.'
                })
        
        # Validate capacity
        total_capacity = cleaned_data.get('total_capacity')
        room_count = cleaned_data.get('room_count')
        beds_per_room = cleaned_data.get('beds_per_room')
        
        if room_count and beds_per_room:
            calculated_capacity = room_count * beds_per_room
            if total_capacity and total_capacity > calculated_capacity * 1.5:
                self.add_error('total_capacity', 
                    f'Total capacity seems too high. With {room_count} rooms and {beds_per_room} beds per room, '
                    f'capacity should be around {calculated_capacity}.'
                )
        
        # Validate dormitory master assignments
        master = cleaned_data.get('dormitory_master')
        assistant = cleaned_data.get('assistant_dormitory_master')
        
        if master and assistant and master == assistant:
            raise ValidationError({
                'assistant_dormitory_master': 'Assistant cannot be the same as dormitory master.'
            })
        
        return cleaned_data


class DormitoryQuickAddForm(BootstrapFormMixin, forms.ModelForm):
    """Simplified form for quick dormitory creation"""
    
    class Meta:
        model = Dormitory
        fields = [
            'name', 'code', 'dormitory_type',
            'total_capacity', 'dormitory_master',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Dormitory name'}),
            'code': forms.TextInput(attrs={'placeholder': 'DORM-CODE'}),
            'dormitory_type': forms.Select(attrs={'class': 'form-select'}),
            'total_capacity': forms.NumberInput(attrs={'min': '1'}),
            'dormitory_master': forms.Select(attrs={'class': 'form-select'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.fields['dormitory_master'].queryset = Staff.objects.filter(
                is_active=True
            ).order_by('first_name', 'last_name')
        except Exception as e:
            logger.error(f"Error setting staff queryset: {e}")


# =============================================================================
# BOARDING ENROLLMENT FORMS
# =============================================================================

class BoardingEnrollmentForm(RequiredFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """
    Form for creating/editing boarding enrollments.
    Uses school timezone for all date validations. ⭐
    """
    
    class Meta:
        model = BoardingEnrollment
        fields = [
            'student', 'academic_session', 'boarding_type',
            'dormitory', 'room_number', 'bed_number',
            'enrollment_date', 'effective_start_date', 'effective_end_date',
            'boarding_days',
            'guardian_consent', 'consent_date', 'consenting_guardian',
            'dietary_requirements', 'medical_requirements', 'special_accommodations',
            'emergency_contact_during_boarding', 'emergency_contact_name', 
            'emergency_contact_relationship',
            'reason_for_boarding', 'auto_create_invoice',
        ]
        widgets = {
            'student': forms.Select(attrs={
                'class': 'form-select',
                'data-placeholder': 'Select a student...'
            }),
            'academic_session': forms.Select(attrs={'class': 'form-select'}),
            'boarding_type': forms.Select(attrs={'class': 'form-select'}),
            'dormitory': forms.Select(attrs={'class': 'form-select'}),
            'room_number': forms.TextInput(attrs={'placeholder': 'e.g., 101, A-12'}),
            'bed_number': forms.TextInput(attrs={'placeholder': 'e.g., 1, A, Top'}),
            'enrollment_date': DatePickerInput(),
            'effective_start_date': DatePickerInput(),
            'effective_end_date': DatePickerInput(),
            'boarding_days': forms.SelectMultiple(attrs={
                'class': 'form-select',
                'size': '7'
            }),
            'consent_date': DatePickerInput(),
            'consenting_guardian': forms.Select(attrs={'class': 'form-select'}),
            'dietary_requirements': forms.Textarea(attrs={
                'rows': 2,
                'placeholder': 'Any special dietary needs...'
            }),
            'medical_requirements': forms.Textarea(attrs={
                'rows': 2,
                'placeholder': 'Any medical conditions or requirements...'
            }),
            'special_accommodations': forms.Textarea(attrs={
                'rows': 2,
                'placeholder': 'Any special accommodations needed...'
            }),
            'emergency_contact_during_boarding': PhoneInput(),
            'emergency_contact_name': forms.TextInput(attrs={
                'placeholder': 'Full name of emergency contact'
            }),
            'emergency_contact_relationship': forms.TextInput(attrs={
                'placeholder': 'e.g., Parent, Guardian, Relative'
            }),
            'reason_for_boarding': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Reason for requesting boarding...'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set querysets
        try:
            # Active students only
            self.fields['student'].queryset = Student.objects.filter(
                enrollment_status='ACTIVE'
            ).order_by('first_name', 'last_name')
            
            # Active academic sessions
            self.fields['academic_session'].queryset = AcademicSession.objects.filter(
                is_active=True
            ).order_by('-start_date')
            
            # Active dormitories available for new admissions
            self.fields['dormitory'].queryset = Dormitory.objects.filter(
                is_active=True,
                is_available_for_new_admissions=True
            ).order_by('dormitory_type', 'name')
            
        except Exception as e:
            logger.error(f"Error setting form querysets: {e}")
        
        # Set default dates (uses school timezone) ⭐
        if not self.is_bound:
            from core.utils import get_school_today  # ⭐
            today = get_school_today()
            
            self.fields['enrollment_date'].initial = today
            self.fields['effective_start_date'].initial = today
        
        # Configure boarding days choices for flexible boarders
        self.fields['boarding_days'].choices = [
            ('Monday', 'Monday'),
            ('Tuesday', 'Tuesday'),
            ('Wednesday', 'Wednesday'),
            ('Thursday', 'Thursday'),
            ('Friday', 'Friday'),
            ('Saturday', 'Saturday'),
            ('Sunday', 'Sunday'),
        ]
        
        # Update field for guardian selection based on student
        if self.instance and self.instance.student_id:
            try:
                self.fields['consenting_guardian'].queryset = Guardian.objects.filter(
                    student_relationships__student=self.instance.student,
                    student_relationships__is_active=True
                ).distinct()
            except Exception as e:
                logger.error(f"Error setting guardian queryset: {e}")
        
        # Set help text
        self.fields['boarding_type'].help_text = (
            "Full Boarder: Mon-Sun, Weekly Boarder: Mon-Fri, Flexible: Custom days"
        )
        self.fields['auto_create_invoice'].help_text = (
            "Automatically create a boarding fee invoice when enrollment is approved"
        )
    
    def clean(self):
        """Validate enrollment data using school timezone ⭐"""
        cleaned_data = super().clean()
        
        # Validate dates (uses school timezone) ⭐
        enrollment_date = cleaned_data.get('enrollment_date')
        start_date = cleaned_data.get('effective_start_date')
        end_date = cleaned_data.get('effective_end_date')
        academic_session = cleaned_data.get('academic_session')
        
        from core.utils import get_school_today  # ⭐
        today = get_school_today()
        
        # Validate enrollment date is not too far in the past
        if enrollment_date and enrollment_date < today - timezone.timedelta(days=365):
            self.add_error('enrollment_date', 
                'Enrollment date is more than a year in the past. Please verify.'
            )
        
        # Validate date range
        if start_date and end_date:
            if end_date < start_date:
                raise ValidationError({
                    'effective_end_date': 'End date cannot be before start date.'
                })
        
        # Validate dates within academic session
        if academic_session and start_date:
            if start_date < academic_session.start_date:
                raise ValidationError({
                    'effective_start_date': 
                    f'Start date cannot be before academic session start date ({academic_session.start_date}).'
                })
            if start_date > academic_session.end_date:
                raise ValidationError({
                    'effective_start_date': 
                    f'Start date cannot be after academic session end date ({academic_session.end_date}).'
                })
        
        # Validate boarding days for flexible boarders
        boarding_type = cleaned_data.get('boarding_type')
        boarding_days = cleaned_data.get('boarding_days')
        
        if boarding_type == 'FLEXI_BOARDER':
            if not boarding_days or len(boarding_days) == 0:
                raise ValidationError({
                    'boarding_days': 'Boarding days must be specified for flexible boarders.'
                })
        
        # Validate guardian consent for minors
        guardian_consent = cleaned_data.get('guardian_consent')
        student = cleaned_data.get('student')
        
        if student and not guardian_consent:
            student_age = student.get_age() if hasattr(student, 'get_age') else None
            if student_age and student_age < 18:
                self.add_error('guardian_consent', 
                    'Guardian consent is required for students under 18 years old.'
                )
        
        # Validate consent date
        consent_date = cleaned_data.get('consent_date')
        if guardian_consent and consent_date:
            if consent_date > today:
                raise ValidationError({
                    'consent_date': 'Consent date cannot be in the future.'
                })
        
        # Validate dormitory can accommodate student
        dormitory = cleaned_data.get('dormitory')
        if dormitory and student:
            can_accommodate, message = dormitory.can_accommodate(student)
            if not can_accommodate:
                raise ValidationError({
                    'dormitory': message
                })
        
        # Validate emergency contact
        emergency_contact = cleaned_data.get('emergency_contact_during_boarding')
        if emergency_contact:
            try:
                validate_phone_number(emergency_contact)
            except ValidationError as e:
                raise ValidationError({
                    'emergency_contact_during_boarding': e.message
                })
        
        return cleaned_data


class BoardingEnrollmentUpdateForm(BootstrapFormMixin, forms.ModelForm):
    """Form for updating existing boarding enrollment details"""
    
    class Meta:
        model = BoardingEnrollment
        fields = [
            'boarding_type', 'dormitory', 'room_number', 'bed_number',
            'boarding_days', 'status',
            'dietary_requirements', 'medical_requirements', 'special_accommodations',
            'emergency_contact_during_boarding', 'emergency_contact_name',
            'emergency_contact_relationship', 'admin_notes',
        ]
        widgets = {
            'boarding_type': forms.Select(attrs={'class': 'form-select'}),
            'dormitory': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'room_number': forms.TextInput(attrs={'placeholder': 'Room number'}),
            'bed_number': forms.TextInput(attrs={'placeholder': 'Bed number'}),
            'boarding_days': forms.SelectMultiple(attrs={'class': 'form-select'}),
            'dietary_requirements': forms.Textarea(attrs={'rows': 2}),
            'medical_requirements': forms.Textarea(attrs={'rows': 2}),
            'special_accommodations': forms.Textarea(attrs={'rows': 2}),
            'emergency_contact_during_boarding': PhoneInput(),
            'emergency_contact_name': forms.TextInput(),
            'emergency_contact_relationship': forms.TextInput(),
            'admin_notes': forms.Textarea(attrs={'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Configure boarding days
        self.fields['boarding_days'].choices = [
            ('Monday', 'Monday'),
            ('Tuesday', 'Tuesday'),
            ('Wednesday', 'Wednesday'),
            ('Thursday', 'Thursday'),
            ('Friday', 'Friday'),
            ('Saturday', 'Saturday'),
            ('Sunday', 'Sunday'),
        ]


class BoardingApprovalForm(BootstrapFormMixin, forms.Form):
    """Form for approving/rejecting boarding enrollments"""
    
    DECISION_CHOICES = [
        ('', '-- Select Decision --'),
        ('APPROVE', 'Approve Boarding Enrollment'),
        ('REJECT', 'Reject Boarding Enrollment'),
    ]
    
    decision = forms.ChoiceField(
        label='Decision',
        choices=DECISION_CHOICES,
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    notes = forms.CharField(
        label='Approval Notes',
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'Enter approval or rejection notes...'
        })
    )
    
    def clean_decision(self):
        """Ensure a decision is selected"""
        decision = self.cleaned_data.get('decision')
        if not decision:
            raise ValidationError('Please select a decision.')
        return decision


class BoardingTerminationForm(BootstrapFormMixin, forms.Form):
    """
    Form for terminating boarding enrollment.
    Uses school timezone for termination date. ⭐
    """
    
    termination_reason = forms.CharField(
        label='Reason for Termination',
        required=True,
        widget=forms.Textarea(attrs={
            'rows': 4,
            'placeholder': 'Please provide a detailed reason for terminating boarding...'
        })
    )
    
    effective_termination_date = forms.DateField(
        label='Effective Termination Date',
        required=True,
        widget=DatePickerInput(),
        help_text='Date when boarding enrollment ends'
    )
    
    confirm = forms.BooleanField(
        label='I confirm this termination',
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set default termination date (uses school timezone) ⭐
        if not self.is_bound:
            from core.utils import get_school_today  # ⭐
            self.fields['effective_termination_date'].initial = get_school_today()
    
    def clean_effective_termination_date(self):
        """Validate termination date using school timezone ⭐"""
        date = self.cleaned_data.get('effective_termination_date')
        
        from core.utils import get_school_today  # ⭐
        today = get_school_today()
        
        # Allow termination date to be in the past (retroactive termination)
        # but warn if too far in the past
        if date < today - timezone.timedelta(days=90):
            raise ValidationError(
                'Termination date is more than 90 days in the past. '
                'Please contact administration for backdated terminations.'
            )
        
        return date


# =============================================================================
# FILTER FORMS (HTMX-POWERED)
# =============================================================================

class DormitoryFilterForm(HTMXFilterFormMixin, BootstrapFormMixin, forms.Form):
    """
    HTMX-powered dormitory filter form.
    Uses school timezone for date filters. ⭐
    """
    
    # Configuration
    htmx_get = 'boarding:dormitory_search'
    htmx_target = '#dormitory-list'
    search_delay = 300
    
    # Search
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by name, code, building...'
        })
    )
    
    # Type filter
    dormitory_type = forms.ChoiceField(
        label='Dormitory Type',
        choices=[('', 'All Types')] + list(Dormitory.DORMITORY_TYPE_CHOICES),
        required=False,
        widget=SelectWithDefault(default_label="All Types")
    )
    
    # Status filters
    is_active = forms.NullBooleanField(
        label='Active Status',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Active'),
            ('false', 'Inactive')
        ], attrs={'class': 'form-select'})
    )
    
    is_available_for_new_admissions = forms.NullBooleanField(
        label='Available for Admissions',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Available'),
            ('false', 'Not Available')
        ], attrs={'class': 'form-select'})
    )
    
    # Maintenance status filter
    maintenance_status = forms.ChoiceField(
        label='Maintenance Status',
        choices=[('', 'All Statuses')] + list(Dormitory.MAINTENANCE_STATUS_CHOICES),
        required=False,
        widget=SelectWithDefault(default_label="All Statuses")
    )
    
    # Occupancy filters
    occupancy_level = forms.ChoiceField(
        label='Occupancy Level',
        choices=[
            ('', 'All Levels'),
            ('empty', 'Empty'),
            ('low', 'Low (<70%)'),
            ('medium', 'Medium (70-90%)'),
            ('high', 'High (>90%)'),
        ],
        required=False,
        widget=SelectWithDefault(default_label="All Levels")
    )
    
    # Dormitory master filter
    dormitory_master = forms.ModelChoiceField(
        label='Dormitory Master',
        queryset=None,
        required=False,
        widget=SelectWithDefault(default_label="All Masters")
    )
    
    def __init__(self, *args, **kwargs):
        search_url = kwargs.pop('search_url', None)
        if search_url:
            self.htmx_get = search_url
        
        super().__init__(*args, **kwargs)
        
        # Set staff queryset
        try:
            self.fields['dormitory_master'].queryset = Staff.objects.filter(
                is_active=True,
                managed_dormitories__isnull=False
            ).distinct().order_by('first_name', 'last_name')
        except Exception as e:
            logger.error(f"Error setting staff queryset: {e}")


class BoardingEnrollmentFilterForm(HTMXFilterFormMixin, DateRangeFormMixin, BootstrapFormMixin, forms.Form):
    """
    HTMX-powered boarding enrollment filter form.
    Uses school timezone for date filters. ⭐
    """
    
    # Configuration
    htmx_get = 'boarding:enrollment_search'
    htmx_target = '#enrollment-list'
    search_delay = 300
    
    # Search
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by student name, roll number...'
        })
    )
    
    # Academic session filter
    academic_session = forms.ModelChoiceField(
        label='Academic Session',
        queryset=None,
        required=False,
        widget=SelectWithDefault(default_label="All Sessions")
    )
    
    # Boarding type filter
    boarding_type = forms.ChoiceField(
        label='Boarding Type',
        choices=[('', 'All Types')] + list(BoardingEnrollment.BOARDING_TYPE_CHOICES),
        required=False,
        widget=SelectWithDefault(default_label="All Types")
    )
    
    # Status filter
    status = forms.ChoiceField(
        label='Status',
        choices=[('', 'All Statuses')] + list(BoardingEnrollment.ENROLLMENT_STATUS_CHOICES),
        required=False,
        widget=SelectWithDefault(default_label="All Statuses")
    )
    
    # Dormitory filter
    dormitory = forms.ModelChoiceField(
        label='Dormitory',
        queryset=None,
        required=False,
        widget=SelectWithDefault(default_label="All Dormitories")
    )
    
    # Consent filter
    guardian_consent = forms.NullBooleanField(
        label='Guardian Consent',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'With Consent'),
            ('false', 'Without Consent')
        ], attrs={'class': 'form-select'})
    )
    
    # Date range filters (uses school timezone) ⭐
    enrollment_date_from = forms.DateField(
        label='Enrolled From',
        required=False,
        widget=DatePickerInput()
    )
    
    enrollment_date_to = forms.DateField(
        label='Enrolled To',
        required=False,
        widget=DatePickerInput()
    )
    
    # Student gender filter
    student_gender = forms.ChoiceField(
        label='Gender',
        choices=[
            ('', 'All'),
            ('M', 'Male'),
            ('F', 'Female'),
        ],
        required=False,
        widget=SelectWithDefault(default_label="All")
    )
    
    def __init__(self, *args, **kwargs):
        search_url = kwargs.pop('search_url', None)
        if search_url:
            self.htmx_get = search_url
        
        super().__init__(*args, **kwargs)
        
        # Set querysets
        try:
            self.fields['academic_session'].queryset = AcademicSession.objects.filter(
                is_active=True
            ).order_by('-start_date')
            
            self.fields['dormitory'].queryset = Dormitory.objects.filter(
                is_active=True
            ).order_by('dormitory_type', 'name')
        except Exception as e:
            logger.error(f"Error setting form querysets: {e}")

