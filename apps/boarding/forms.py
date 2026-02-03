# boarding/forms.py

"""
Boarding management forms with timezone support.
All date validations use school timezone for consistency.
HTMX functionality handled in views and templates.
"""

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import Q
import logging

# Import base form utilities with timezone support ⭐
from utils.forms import (
    BootstrapFormMixin,
    DateRangeFormMixin,
    RequiredFieldsMixin,
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

class DormitoryForm(forms.ModelForm):
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
            'dormitory_phone', 'dormitory_email', 'notes'
        ]
        widgets = {
            'last_maintenance_date': forms.DateInput(attrs={'type': 'date'}),
            'next_maintenance_due': forms.DateInput(attrs={'type': 'date'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Get active staff for dormitory master selection
        # ⭐ Staff model has direct name fields (first_name, last_name), NOT a 'user' relation
        active_staff = Staff.objects.filter(
            is_active=True,
            employment_status='ACTIVE'
        ).order_by('first_name', 'last_name')  # ✅ Changed from 'user__first_name'
        
        # Set staff querysets
        self.fields['dormitory_master'].queryset = active_staff
        self.fields['assistant_dormitory_master'].queryset = active_staff
        
        # Make fields optional
        self.fields['dormitory_master'].required = False
        self.fields['assistant_dormitory_master'].required = False
        
        # Add help texts
        self.fields['code'].help_text = "Unique identifier for the dormitory (e.g., DORM-B-001)"
        self.fields['total_capacity'].help_text = "Maximum number of students this dormitory can accommodate"
        
        # Only modify current_occupancy if it exists in the form
        if 'current_occupancy' in self.fields:
            self.fields['current_occupancy'].help_text = "Auto-calculated based on active enrollments"
            self.fields['current_occupancy'].disabled = True
        
        # Style form fields
        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({'class': 'form-check-input'})
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.update({'class': 'form-select'})
            elif isinstance(field.widget, forms.Textarea):
                field.widget.attrs.update({'class': 'form-control', 'rows': 3})
            else:
                field.widget.attrs.update({'class': 'form-control'})
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Validate that dormitory master and assistant are not the same person
        dormitory_master = cleaned_data.get('dormitory_master')
        assistant_master = cleaned_data.get('assistant_dormitory_master')
        
        if dormitory_master and assistant_master and dormitory_master == assistant_master:
            raise forms.ValidationError(
                "The dormitory master and assistant dormitory master cannot be the same person."
            )
        
        # Validate capacity
        total_capacity = cleaned_data.get('total_capacity')
        room_count = cleaned_data.get('room_count')
        beds_per_room = cleaned_data.get('beds_per_room')
        
        if room_count and beds_per_room and total_capacity:
            calculated_capacity = room_count * beds_per_room
            # Allow some variance (e.g., some rooms might have different bed counts)
            if total_capacity > calculated_capacity * 1.5:
                raise forms.ValidationError(
                    f"Total capacity ({total_capacity}) seems too high compared to "
                    f"calculated capacity ({calculated_capacity} = {room_count} rooms × {beds_per_room} beds). "
                    f"Please verify your numbers."
                )
        
        # Validate maintenance dates
        last_maintenance = cleaned_data.get('last_maintenance_date')
        next_maintenance = cleaned_data.get('next_maintenance_due')
        
        if last_maintenance and next_maintenance and next_maintenance < last_maintenance:
            raise forms.ValidationError(
                "Next maintenance date cannot be before the last maintenance date."
            )
        
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
    Adapts field availability based on whether editing existing enrollment.
    Uses school timezone for all date validations.
    """
    
    # Override boarding_days field to use MultipleChoiceField instead of JSONField
    boarding_days = forms.MultipleChoiceField(
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={
            'class': 'form-check-input'
        }),
        choices=[
            ('Monday', 'Monday'),
            ('Tuesday', 'Tuesday'),
            ('Wednesday', 'Wednesday'),
            ('Thursday', 'Thursday'),
            ('Friday', 'Friday'),
            ('Saturday', 'Saturday'),
            ('Sunday', 'Sunday'),
        ],
        help_text='Select the days this student will board',
        label='Boarding Days'
    )
    
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
            'status', 'admin_notes',
        ]
        widgets = {
            'student': forms.Select(attrs={
                'class': 'form-select',
                'data-placeholder': 'Select a student...'
            }),
            'academic_session': forms.Select(attrs={
                'class': 'form-select'
            }),
            'boarding_type': forms.Select(attrs={'class': 'form-select'}),
            'dormitory': forms.Select(attrs={'class': 'form-select'}),
            'room_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., 101, A-12'
            }),
            'bed_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., 1, A, Top'
            }),
            'enrollment_date': DatePickerInput(),
            'effective_start_date': DatePickerInput(),
            'effective_end_date': DatePickerInput(),
            # ✅ REMOVED boarding_days from widgets - defined as field above
            'consent_date': DatePickerInput(),
            'consenting_guardian': forms.Select(attrs={'class': 'form-select'}),
            'guardian_consent': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'dietary_requirements': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Any special dietary needs...'
            }),
            'medical_requirements': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Any medical conditions or requirements...'
            }),
            'special_accommodations': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Any special accommodations needed...'
            }),
            'emergency_contact_during_boarding': PhoneInput(),
            'emergency_contact_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Full name of emergency contact'
            }),
            'emergency_contact_relationship': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Parent, Guardian, Relative'
            }),
            'reason_for_boarding': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Reason for requesting boarding...'
            }),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'admin_notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            }),
            'auto_create_invoice': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Detect edit mode (works with UUID and all PK types)
        is_edit_mode = not self.instance._state.adding
        
        # ✅ Set initial value for boarding_days from instance
        if is_edit_mode and self.instance.boarding_days:
            # boarding_days is stored as JSON list in database
            self.fields['boarding_days'].initial = self.instance.boarding_days
        
        # Set querysets
        try:
            # Active students only
            self.fields['student'].queryset = Student.objects.filter(
                enrollment_status='ACTIVE'
            ).order_by('first_name', 'last_name')
            
            # Active academic sessions
            self.fields['academic_session'].queryset = AcademicSession.objects.all().order_by(
                '-start_date'
            )
            
            # Active dormitories available for new admissions
            self.fields['dormitory'].queryset = Dormitory.objects.filter(
                is_active=True,
                is_available_for_new_admissions=True
            ).order_by('dormitory_type', 'name')
            
        except Exception as e:
            logger.error(f"Error setting form querysets: {e}")
        
        # Remove fields based on mode
        if is_edit_mode:
            # Can't change these after enrollment created
            fields_to_remove = [
                'student',
                'academic_session', 
                'enrollment_date',
                'effective_start_date',
                'effective_end_date',
                'reason_for_boarding',
                'auto_create_invoice',
            ]
            for field_name in fields_to_remove:
                if field_name in self.fields:
                    del self.fields[field_name]
        else:
            # Remove admin-only fields in create mode
            fields_to_remove = ['status', 'admin_notes']
            for field_name in fields_to_remove:
                if field_name in self.fields:
                    del self.fields[field_name]
        
        # Set default dates (uses school timezone) - CREATE MODE ONLY
        if not self.is_bound and not is_edit_mode:
            from core.utils import get_school_today
            today = get_school_today()
            
            if 'enrollment_date' in self.fields:
                self.fields['enrollment_date'].initial = today
            if 'effective_start_date' in self.fields:
                self.fields['effective_start_date'].initial = today
        
        # Update field for guardian selection based on student
        if self.instance and self.instance.student_id:
            try:
                from students.models import StudentGuardian
                
                self.fields['consenting_guardian'].queryset = Guardian.objects.filter(
                    id__in=StudentGuardian.objects.filter(
                        student=self.instance.student,
                        is_active=True
                    ).values_list('guardian_id', flat=True)
                ).order_by('first_name', 'last_name')
            except Exception as e:
                logger.error(f"Error setting guardian queryset: {e}")
        else:
            # Create mode - show all guardians (will be filtered via JS)
            self.fields['consenting_guardian'].queryset = Guardian.objects.filter(
                student_relationships__is_active=True
            ).distinct().order_by('first_name', 'last_name')
        
        # Set help text
        if 'boarding_type' in self.fields:
            self.fields['boarding_type'].help_text = (
                "Full Boarder: Mon-Sun, Weekly Boarder: Mon-Fri, Flexible: Custom days"
            )
        if 'auto_create_invoice' in self.fields:
            self.fields['auto_create_invoice'].help_text = (
                "Automatically create a boarding fee invoice when enrollment is approved"
            )
        if 'room_number' in self.fields:
            self.fields['room_number'].help_text = "Optional: Can be assigned later"
        if 'bed_number' in self.fields:
            self.fields['bed_number'].help_text = "Optional: Can be assigned later"
        
        # Make consent fields optional (conditional validation)
        if 'consent_date' in self.fields:
            self.fields['consent_date'].required = False
        if 'consenting_guardian' in self.fields:
            self.fields['consenting_guardian'].required = False
    
    def clean(self):
        """Validate enrollment data using school timezone"""
        cleaned_data = super().clean()
        
        # Validate dates (uses school timezone)
        enrollment_date = cleaned_data.get('enrollment_date')
        start_date = cleaned_data.get('effective_start_date')
        end_date = cleaned_data.get('effective_end_date')
        academic_session = cleaned_data.get('academic_session')
        
        from core.utils import get_school_today
        today = get_school_today()
        
        # Validate date range
        if start_date and end_date:
            if end_date < start_date:
                raise ValidationError({
                    'effective_end_date': 'End date cannot be before start date.'
                })
        
        # Validate dates within academic session (CREATE MODE ONLY)
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
        
        # Validate guardian consent for minors (CREATE MODE ONLY)
        guardian_consent = cleaned_data.get('guardian_consent')
        student = cleaned_data.get('student') or (self.instance.student if not self.instance._state.adding else None)
        
        if student and not guardian_consent:
            student_age = student.get_age() if hasattr(student, 'get_age') else None
            if student_age and student_age < 18:
                logger.warning(
                    f"Boarding enrollment for minor {student.get_full_name()} "
                    f"(age {student_age}) without guardian consent"
                )
        
        # Validate consent date
        consent_date = cleaned_data.get('consent_date')
        if guardian_consent and consent_date:
            if consent_date > today:
                raise ValidationError({
                    'consent_date': 'Consent date cannot be in the future.'
                })
        
        # If consent is given, require date and guardian
        if guardian_consent:
            if not consent_date:
                raise ValidationError({
                    'consent_date': 'Consent date is required when guardian consent is given.'
                })
            
            consenting_guardian = cleaned_data.get('consenting_guardian')
            if not consenting_guardian:
                raise ValidationError({
                    'consenting_guardian': 'Please select which guardian gave consent.'
                })
        
        # Validate dormitory can accommodate student (CREATE MODE ONLY)
        dormitory = cleaned_data.get('dormitory')
        if dormitory and student and self.instance._state.adding:
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
    
    def save(self, commit=True):
        """Ensure boarding_days is properly serialized for JSONField"""
        instance = super().save(commit=False)
        
        # ✅ Convert boarding_days list to JSON-compatible format
        if 'boarding_days' in self.cleaned_data:
            boarding_days = self.cleaned_data.get('boarding_days')
            if boarding_days:
                # Convert to list (it's already a list from MultipleChoiceField)
                instance.boarding_days = list(boarding_days)
            else:
                instance.boarding_days = []  # Empty list instead of None
        
        if commit:
            instance.save()
            if hasattr(self, 'save_m2m'):
                self.save_m2m()
        
        return instance


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
# BULK BOARDING ENROLLMENT FORMS
# =============================================================================

class BulkBoardingEnrollmentStudentSelectionForm(BootstrapFormMixin, forms.Form):
    """Step 1: Filter and select students for bulk boarding enrollment"""
    
    search = forms.CharField(
        label='Search Students',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by name, admission number...',
            'autofocus': True
        })
    )
    
    current_level = forms.ModelChoiceField(
        queryset=None,
        required=False,
        empty_label='All Levels',
        label='Current Academic Level',
        help_text='Filter students by their current level',
        widget=SelectWithDefault(default_label="All Levels")
    )
    
    current_class = forms.ModelChoiceField(
        queryset=None,
        required=False,
        empty_label='All Classes',
        label='Current Class',
        help_text='Filter students by their current class',
        widget=SelectWithDefault(default_label="All Classes")
    )
    
    enrollment_status = forms.ChoiceField(
        choices=[('', 'All Statuses')] + list(Student.ENROLLMENT_STATUS_CHOICES),
        required=False,
        label='Enrollment Status',
        initial='ACTIVE',
        widget=SelectWithDefault(default_label="All Statuses")
    )
    
    gender = forms.ChoiceField(
        choices=[('', 'All Genders')] + list(Student.GENDER_CHOICES),
        required=False,
        label='Gender',
        widget=SelectWithDefault(default_label="All Genders")
    )
    
    exclude_already_enrolled = forms.BooleanField(
        initial=True,
        required=False,
        label='Hide already enrolled boarders',
        help_text='Exclude students already enrolled in boarding for the target session',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    dormitory_type = forms.ChoiceField(
        choices=[('', 'All Types')] + list(Dormitory.DORMITORY_TYPE_CHOICES),
        required=False,
        label='Dormitory Type',
        help_text='Filter by compatible dormitory type',
        widget=SelectWithDefault(default_label="All Types")
    )
    
    sort_by = forms.ChoiceField(
        choices=[
            ('name', 'Name (A-Z)'),
            ('-name', 'Name (Z-A)'),
            ('admission_number', 'Admission Number'),
            ('-admission_date', 'Recently Admitted'),
            ('admission_date', 'Oldest Admission'),
        ],
        required=True,
        initial='name',
        label='Sort By',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    def __init__(self, *args, academic_session=None, target_dormitory=None, **kwargs):
        self.academic_session = academic_session
        self.target_dormitory = target_dormitory
        
        super().__init__(*args, **kwargs)
        
        # Set querysets
        try:
            from academics.models import AcademicLevel, Class
            
            self.fields['current_level'].queryset = AcademicLevel.objects.filter(
                is_active=True
            ).order_by('order')
            
            self.fields['current_class'].queryset = Class.objects.filter(
                is_active=True
            ).select_related(
                'academic_level',
                'classroom'
            ).order_by('academic_level__order', 'section', 'classroom__room_number')
            
        except Exception as e:
            logger.error(f"Error setting queryset: {e}")
        
        if self.academic_session:
            self.fields['exclude_already_enrolled'].help_text = (
                f'Exclude students already enrolled in boarding for {self.academic_session.name}'
            )


class BulkBoardingEnrollmentConfirmationForm(RequiredFieldsMixin, BootstrapFormMixin, forms.Form):
    """Step 2: Configure boarding enrollment details for selected students"""
    
    academic_session = forms.ModelChoiceField(
        queryset=None,
        required=True,
        label='Academic Session',
        empty_label='Select Academic Session',
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Only active sessions are shown'
    )
    
    dormitory = forms.ModelChoiceField(
        queryset=None,
        required=True,
        label='Dormitory',
        empty_label='Select Dormitory',
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Only active dormitories available for new admissions are shown'
    )
    
    boarding_type = forms.ChoiceField(
        choices=BoardingEnrollment.BOARDING_TYPE_CHOICES,
        initial='FULL_BOARDER',
        required=True,
        label='Boarding Type',
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Full Boarder: Mon-Sun, Weekly Boarder: Mon-Fri, Flexible: Custom days'
    )
    
    enrollment_date = forms.DateField(
        widget=DatePickerInput(),
        required=True,
        label='Enrollment Date'
    )
    
    effective_start_date = forms.DateField(
        widget=DatePickerInput(),
        required=True,
        label='Effective Start Date',
        help_text='Date when boarding actually starts'
    )
    
    effective_end_date = forms.DateField(
        widget=DatePickerInput(),
        required=False,
        label='Effective End Date',
        help_text='Optional: Date when boarding ends (leave blank for session end)'
    )
    
    boarding_days = forms.MultipleChoiceField(
        choices=[
            ('Monday', 'Monday'),
            ('Tuesday', 'Tuesday'),
            ('Wednesday', 'Wednesday'),
            ('Thursday', 'Thursday'),
            ('Friday', 'Friday'),
            ('Saturday', 'Saturday'),
            ('Sunday', 'Sunday'),
        ],
        required=False,
        label='Boarding Days',
        widget=forms.CheckboxSelectMultiple(),
        help_text='Required for flexible boarders only'
    )
    
    auto_create_invoice = forms.BooleanField(
        initial=True,
        required=False,
        label='Auto-create Boarding Fee Invoices',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text='Automatically create boarding fee invoices when approved'
    )
    
    require_guardian_consent = forms.BooleanField(
        initial=True,
        required=False,
        label='Require Guardian Consent',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text='Mark enrollments as requiring guardian consent for minors'
    )
    
    selected_student_ids = forms.CharField(
        widget=forms.HiddenInput(),
        required=True
    )
    
    reason_for_boarding = forms.CharField(
        required=False,
        label='Reason for Boarding (Optional)',
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'Common reason for all selected students...'
        }),
        help_text='This will be applied to all enrollments'
    )
    
    confirm_enrollment = forms.BooleanField(
        required=True,
        label='I confirm this bulk boarding enrollment',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    def __init__(self, *args, **kwargs):
        self.student_count = kwargs.pop('student_count', 0)
        super().__init__(*args, **kwargs)
        
        # Update confirmation label with student count
        if self.student_count:
            self.fields['confirm_enrollment'].label = (
                f'I confirm boarding enrollment of {self.student_count} student(s)'
            )
        
        # Set querysets
        try:
            self.fields['academic_session'].queryset = AcademicSession.objects.filter(
                is_active=True
            ).order_by('-start_date')
            
            self.fields['dormitory'].queryset = Dormitory.objects.filter(
                is_active=True,
                is_available_for_new_admissions=True
            ).order_by('dormitory_type', 'name')
        except Exception as e:
            logger.error(f"Error setting queryset: {e}")
        
        # Set default dates (uses school timezone) ⭐
        if not self.data and not self.initial.get('enrollment_date'):
            from core.utils import get_school_today  # ⭐
            today = get_school_today()
            
            self.fields['enrollment_date'].initial = today
            self.fields['effective_start_date'].initial = today
    
    def clean_selected_student_ids(self):
        """Parse and validate selected student IDs"""
        ids_str = self.cleaned_data.get('selected_student_ids', '')
        
        if not ids_str:
            raise ValidationError('No students selected for boarding enrollment.')
        
        try:
            ids = [id.strip() for id in ids_str.split(',') if id.strip()]
            if not ids:
                raise ValidationError('No valid student IDs provided.')
            
            # Verify all students exist
            actual_count = Student.objects.filter(id__in=ids).count()
            if actual_count != len(ids):
                raise ValidationError(
                    f'Some students no longer exist. Found {actual_count} of {len(ids)}.'
                )
            
            return ids
            
        except ValueError:
            raise ValidationError('Invalid student ID format.')
    
    def clean_enrollment_date(self):
        """Validate enrollment date using school timezone ⭐"""
        enrollment_date = self.cleaned_data.get('enrollment_date')
        
        if not enrollment_date:
            return enrollment_date
        
        from core.utils import get_school_today  # ⭐
        today = get_school_today()
        
        # Allow past dates but warn if too far in the past
        if enrollment_date < today - timezone.timedelta(days=365):
            raise ValidationError(
                'Enrollment date is more than a year in the past. Please verify.'
            )
        
        # Don't allow too far in the future
        if enrollment_date > today + timezone.timedelta(days=365):
            raise ValidationError('Enrollment date cannot be more than 1 year in the future.')
        
        return enrollment_date
    
    def clean_effective_start_date(self):
        """Validate start date using school timezone ⭐"""
        start_date = self.cleaned_data.get('effective_start_date')
        
        if not start_date:
            return start_date
        
        from core.utils import get_school_today  # ⭐
        today = get_school_today()
        
        if start_date < today - timezone.timedelta(days=365):
            raise ValidationError(
                'Start date is more than a year in the past. Please verify.'
            )
        
        return start_date
    
    def clean(self):
        """Cross-field validation using school timezone ⭐"""
        cleaned_data = super().clean()
        
        academic_session = cleaned_data.get('academic_session')
        dormitory = cleaned_data.get('dormitory')
        boarding_type = cleaned_data.get('boarding_type')
        enrollment_date = cleaned_data.get('enrollment_date')
        start_date = cleaned_data.get('effective_start_date')
        end_date = cleaned_data.get('effective_end_date')
        boarding_days = cleaned_data.get('boarding_days')
        student_ids = cleaned_data.get('selected_student_ids', [])
        
        # Validate boarding days for flexible boarders
        if boarding_type == 'FLEXI_BOARDER':
            if not boarding_days or len(boarding_days) == 0:
                raise ValidationError({
                    'boarding_days': 'Boarding days must be specified for flexible boarders.'
                })
        
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
                    f'Start date cannot be before session start date ({academic_session.start_date}).'
                })
            if start_date > academic_session.end_date:
                raise ValidationError({
                    'effective_start_date': 
                    f'Start date cannot be after session end date ({academic_session.end_date}).'
                })
        
        # Validate dormitory capacity
        if dormitory and student_ids:
            current_occupancy = dormitory.current_occupancy or 0
            available_capacity = dormitory.total_capacity - current_occupancy
            
            if len(student_ids) > available_capacity:
                raise ValidationError({
                    'dormitory': (
                        f'Dormitory has only {available_capacity} available beds, '
                        f'but you are trying to enroll {len(student_ids)} students.'
                    )
                })
        
        # Validate gender compatibility
        if dormitory and student_ids:
            students = Student.objects.filter(id__in=student_ids)
            
            for student in students:
                can_accommodate, message = dormitory.can_accommodate(student)
                if not can_accommodate:
                    raise ValidationError({
                        'dormitory': f'{student.get_full_name()}: {message}'
                    })
        
        # Check for existing enrollments
        if academic_session and student_ids:
            existing_enrollments = BoardingEnrollment.objects.filter(
                academic_session=academic_session,
                student_id__in=student_ids,
                status__in=['PENDING', 'APPROVED', 'ACTIVE']
            ).select_related('student', 'dormitory')
            
            if existing_enrollments.exists():
                duplicates = [
                    f"{e.student.get_full_name()} (in {e.dormitory.name})"
                    for e in existing_enrollments[:5]
                ]
                
                error_msg = 'Already enrolled in boarding:\n' + '\n'.join(duplicates)
                if existing_enrollments.count() > 5:
                    error_msg += f'\n... and {existing_enrollments.count() - 5} more'
                
                raise ValidationError(error_msg)
        
        return cleaned_data

# =============================================================================
# FILTER FORMS (NO HTMX - Pure Django Forms)
# =============================================================================

class DormitoryFilterForm(BootstrapFormMixin, forms.Form):
    """
    Filter form for dormitories.
    Uses school timezone for date filters. ⭐
    HTMX handling done in views/templates.
    """
    
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
        super().__init__(*args, **kwargs)
        
        # Set staff queryset
        try:
            self.fields['dormitory_master'].queryset = Staff.objects.filter(
                is_active=True,
                managed_dormitories__isnull=False
            ).distinct().order_by('first_name', 'last_name')
        except Exception as e:
            logger.error(f"Error setting staff queryset: {e}")


class BoardingEnrollmentFilterForm(DateRangeFormMixin, BootstrapFormMixin, forms.Form):
    """
    Filter form for boarding enrollments.
    Uses school timezone for date filters. ⭐
    HTMX handling done in views/templates.
    """
    
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