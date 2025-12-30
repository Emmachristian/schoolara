# academics/forms.py

"""
Academic management forms with timezone support and HTMX filters.
All date validations use school timezone for consistency.
"""

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.urls import reverse_lazy
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
    SearchInput,
    SelectWithDefault,
    PercentageField,
    PercentageInput,
    validate_future_date,  # ⭐ Uses school timezone
    validate_past_date,  # ⭐ Uses school timezone
    validate_date_not_before,  # ⭐ Uses school timezone
    validate_date_not_after,  # ⭐ Uses school timezone
)

from .models import (
    AcademicSession,
    Holiday,
    Subject,
    AcademicLevel,
    ClassRoom,
    Class,
    StudentClassEnrollment,
    ClassSubject,
    AcademicProgress,
)

from students.models import Student

User = get_user_model()
logger = logging.getLogger(__name__)


# =============================================================================
# ACADEMIC SESSION FILTER FORMS (HTMX SEARCH)
# =============================================================================

class AcademicSessionFilterForm(HTMXFilterFormMixin, BootstrapFormMixin, forms.Form):
    """
    HTMX-powered academic session filter form.
    All date validations use school timezone. ⭐
    """
    
    # Configuration
    htmx_get =  'academics:session_search'
    htmx_target = '#session-list'
    search_delay = 300
    
    # Search
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by year name, term name...'
        })
    )
    
    # Status filters
    is_current = forms.NullBooleanField(
        label='Current Session',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Current Only'),
            ('false', 'Not Current')
        ], attrs={'class': 'form-select'})
    )
    
    is_active = forms.NullBooleanField(
        label='Active Status',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Active'),
            ('false', 'Inactive')
        ], attrs={'class': 'form-select'})
    )
    
    is_academically_closed = forms.NullBooleanField(
        label='Academic Closure',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Closed'),
            ('false', 'Open')
        ], attrs={'class': 'form-select'})
    )
    
    is_special_session = forms.NullBooleanField(
        label='Session Type',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All Sessions'),
            ('false', 'Regular Only'),
            ('true', 'Special Only')
        ], attrs={'class': 'form-select'})
    )
    
    period_type = forms.ChoiceField(
        label='Period Type',
        choices=[('', 'All Types')] + [
            ('term', 'Term'),
            ('semester', 'Semester'),
            ('quarter', 'Quarter'),
            ('trimester', 'Trimester'),
            ('holiday_program', 'Holiday Program'),
            ('summer_school', 'Summer School'),
            ('remedial', 'Remedial Program'),
        ],
        required=False,
        widget=SelectWithDefault(default_label="All Types")
    )
    
    # Date range filters (uses school timezone) ⭐
    start_date_from = forms.DateField(
        label='Start Date From',
        required=False,
        widget=DatePickerInput()
    )
    
    start_date_to = forms.DateField(
        label='Start Date To',
        required=False,
        widget=DatePickerInput()
    )
    
    # Year filter
    year_name = forms.CharField(
        label='Academic Year',
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g., 2024 or 2024-2025'
        })
    )
    
    def __init__(self, *args, **kwargs):
        search_url = kwargs.pop('search_url', None)
        if search_url:
            self.htmx_get = search_url
        
        super().__init__(*args, **kwargs)


class HolidayFilterForm(HTMXFilterFormMixin, DateRangeFormMixin, BootstrapFormMixin, forms.Form):
    """
    HTMX-powered holiday filter form.
    Uses school timezone for date validations. ⭐
    """
    
    htmx_get = None
    htmx_target = '#holiday-list'
    search_delay = 300
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={'placeholder': 'Search holidays...'})
    )
    
    holiday_type = forms.ChoiceField(
        label='Holiday Type',
        choices=[('', 'All Types')] + Holiday.HOLIDAY_TYPE_CHOICES,
        required=False,
        widget=SelectWithDefault(default_label="All Types")
    )
    
    is_school_closed = forms.NullBooleanField(
        label='School Closed',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Closed'),
            ('false', 'Open')
        ], attrs={'class': 'form-select'})
    )
    
    # Date range (uses school timezone) ⭐
    date_from = forms.DateField(
        label='From Date',
        required=False,
        widget=DatePickerInput()
    )
    
    date_to = forms.DateField(
        label='To Date',
        required=False,
        widget=DatePickerInput()
    )
    
    academic_session = forms.ModelChoiceField(
        label='Academic Session',
        queryset=None,
        required=False,
        widget=SelectWithDefault(default_label="All Sessions")
    )
    
    def __init__(self, *args, **kwargs):
        search_url = kwargs.pop('search_url', None)
        if search_url:
            self.htmx_get = search_url
        
        super().__init__(*args, **kwargs)
        
        # Set academic session queryset
        try:
            self.fields['academic_session'].queryset = AcademicSession.objects.filter(
                is_active=True
            ).order_by('-start_date')
        except Exception as e:
            logger.error(f"Error setting session queryset: {e}")

# =============================================================================
# SUBJECT FILTER FORM
# =============================================================================

class SubjectFilterForm(HTMXFilterFormMixin, BootstrapFormMixin, forms.Form):
    """
    HTMX-powered subject filter form.
    """
    
    htmx_get = 'academics:subject_search'
    htmx_target = '#subject-list'
    search_delay = 100
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by name, code, abbreviation...'
        })
    )
    
    subject_type = forms.ChoiceField(
        label='Subject Type',
        choices=[('', 'All Types')] + Subject.SUBJECT_TYPE_CHOICES,
        required=False,
        widget=SelectWithDefault(default_label="All Types")
    )
    
    is_active = forms.NullBooleanField(
        label='Active Status',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Active'),
            ('false', 'Inactive')
        ], attrs={'class': 'form-select'})
    )
    
    is_compulsory = forms.NullBooleanField(
        label='Compulsory',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Compulsory'),
            ('false', 'Optional')
        ], attrs={'class': 'form-select'})
    )
    
    difficulty_level = forms.ChoiceField(
        label='Difficulty Level',
        choices=[('', 'All Levels')] + [
            ('BEGINNER', 'Beginner'),
            ('INTERMEDIATE', 'Intermediate'),
            ('ADVANCED', 'Advanced'),
            ('EXPERT', 'Expert'),
        ],
        required=False,
        widget=SelectWithDefault(default_label="All Levels")
    )
    
    department = forms.ModelChoiceField(
        label='Department',
        queryset=None,
        required=False,
        widget=SelectWithDefault(default_label="All Departments")
    )
    
    academic_level = forms.ModelChoiceField(
        label='Academic Level',
        queryset=None,
        required=False,
        widget=SelectWithDefault(default_label="All Levels"),
        help_text="Filter by applicable academic level"
    )
    
    def __init__(self, *args, **kwargs):
        search_url = kwargs.pop('search_url', None)
        if search_url:
            self.htmx_get = search_url
        
        super().__init__(*args, **kwargs)
        
        # Set department queryset
        try:
            from hr.models import Department
            self.fields['department'].queryset = Department.objects.filter(
                is_active=True
            ).order_by('name')
        except Exception as e:
            logger.error(f"Error setting department queryset: {e}")
        
        # Set academic level queryset
        try:
            self.fields['academic_level'].queryset = AcademicLevel.objects.filter(
                is_active=True
            ).order_by('order')
        except Exception as e:
            logger.error(f"Error setting level queryset: {e}")


# =============================================================================
# ACADEMIC LEVEL FILTER FORM
# =============================================================================

class AcademicLevelFilterForm(HTMXFilterFormMixin, BootstrapFormMixin, forms.Form):
    """
    HTMX-powered academic level filter form.
    """
    
    htmx_get = 'academics:level_search'
    htmx_target = '#level-list'
    search_delay = 100
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by name, code...'
        })
    )
    
    is_active = forms.NullBooleanField(
        label='Active Status',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Active'),
            ('false', 'Inactive')
        ], attrs={'class': 'form-select'})
    )
    
    has_sections = forms.NullBooleanField(
        label='Has Sections',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'With Sections'),
            ('false', 'No Sections')
        ], attrs={'class': 'form-select'})
    )
    
    is_graduation_level = forms.NullBooleanField(
        label='Graduation Level',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Graduation Level'),
            ('false', 'Not Graduation Level')
        ], attrs={'class': 'form-select'})
    )
    
    def __init__(self, *args, **kwargs):
        search_url = kwargs.pop('search_url', None)
        if search_url:
            self.htmx_get = search_url
        
        super().__init__(*args, **kwargs)


# =============================================================================
# CLASSROOM FILTER FORM
# =============================================================================

class ClassRoomFilterForm(HTMXFilterFormMixin, BootstrapFormMixin, forms.Form):
    """
    HTMX-powered classroom filter form.
    """
    
    htmx_get =  'academics:classroom_search'
    htmx_target = '#classroom-list'
    search_delay = 300
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by name, room number, building...'
        })
    )
    
    room_type = forms.ChoiceField(
        label='Room Type',
        choices=[('', 'All Types')] + ClassRoom.ROOM_TYPE_CHOICES,
        required=False,
        widget=SelectWithDefault(default_label="All Types")
    )
    
    building = forms.CharField(
        label='Building',
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Building name'
        })
    )
    
    floor = forms.CharField(
        label='Floor',
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Floor number'
        })
    )
    
    is_active = forms.NullBooleanField(
        label='Active Status',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Active'),
            ('false', 'Inactive')
        ], attrs={'class': 'form-select'})
    )
    
    is_bookable = forms.NullBooleanField(
        label='Bookable',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Bookable'),
            ('false', 'Not Bookable')
        ], attrs={'class': 'form-select'})
    )
    
    has_projector = forms.NullBooleanField(
        label='Has Projector',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Yes'),
            ('false', 'No')
        ], attrs={'class': 'form-select'})
    )
    
    has_computer = forms.NullBooleanField(
        label='Has Computer',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Yes'),
            ('false', 'No')
        ], attrs={'class': 'form-select'})
    )
    
    has_smart_board = forms.NullBooleanField(
        label='Has Smart Board',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Yes'),
            ('false', 'No')
        ], attrs={'class': 'form-select'})
    )
    
    min_capacity = forms.IntegerField(
        label='Minimum Capacity',
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Min capacity',
            'min': '0'
        })
    )
    
    is_accessible = forms.NullBooleanField(
        label='Accessible',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Accessible'),
            ('false', 'Not Accessible')
        ], attrs={'class': 'form-select'})
    )
    
    def __init__(self, *args, **kwargs):
        search_url = kwargs.pop('search_url', None)
        if search_url:
            self.htmx_get = search_url
        
        super().__init__(*args, **kwargs)


# =============================================================================
# CLASS FILTER FORM (COMPLETE FIX)
# =============================================================================

class ClassFilterForm(HTMXFilterFormMixin, BootstrapFormMixin, forms.Form):
    """
    HTMX-powered class filter form with robust queryset handling.
    """
    
    htmx_get = 'academics:class_search'
    htmx_target = '#class-list'
    search_delay = 300
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search classes...'
        })
    )
    
    academic_level = forms.ModelChoiceField(
        label='Academic Level',
        queryset=AcademicLevel.objects.none(),  # ⭐ Initialize with empty queryset
        required=False,
        widget=SelectWithDefault(default_label="All Levels")
    )
    
    academic_session = forms.ModelChoiceField(
        label='Academic Session',
        queryset=AcademicSession.objects.none(),  # ⭐ Initialize with empty queryset
        required=False,
        widget=SelectWithDefault(default_label="All Sessions")
    )
    
    section = forms.CharField(
        label='Section',
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g., A, B, C'
        })
    )
    
    class_teacher = forms.ModelChoiceField(
        label='Class Teacher',
        queryset=None,  # Will be set in __init__
        required=False,
        widget=SelectWithDefault(default_label="All Teachers")
    )
    
    classroom = forms.ModelChoiceField(
        label='Classroom',
        queryset=ClassRoom.objects.none(),  # ⭐ Initialize with empty queryset
        required=False,
        widget=SelectWithDefault(default_label="All Rooms")
    )
    
    is_active = forms.NullBooleanField(
        label='Active Status',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Active'),
            ('false', 'Inactive')
        ], attrs={'class': 'form-select'})
    )
    
    has_capacity = forms.NullBooleanField(
        label='Has Capacity',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Has Space'),
            ('false', 'Full')
        ], attrs={'class': 'form-select'}),
        help_text="Filter by available enrollment capacity"
    )
    
    def __init__(self, *args, **kwargs):
        search_url = kwargs.pop('search_url', None)
        if search_url:
            self.htmx_get = search_url
        
        super().__init__(*args, **kwargs)
        
        # Set academic level queryset
        try:
            self.fields['academic_level'].queryset = AcademicLevel.objects.filter(
                is_active=True
            ).order_by('order')
        except Exception as e:
            logger.error(f"Error setting level queryset: {e}")
            self.fields['academic_level'].queryset = AcademicLevel.objects.none()
        
        # Set academic session queryset
        try:
            self.fields['academic_session'].queryset = AcademicSession.objects.filter(
                is_active=True
            ).order_by('-start_date')
        except Exception as e:
            logger.error(f"Error setting session queryset: {e}")
            self.fields['academic_session'].queryset = AcademicSession.objects.none()
        
        # Set teacher queryset
        try:
            from hr.models import Teacher
            self.fields['class_teacher'].queryset = Teacher.objects.filter(
                is_active=True
            ).order_by('user__last_name', 'user__first_name')
        except Exception as e:
            logger.error(f"Error setting teacher queryset: {e}")
            # Create empty queryset with proper model
            try:
                from hr.models import Teacher
                self.fields['class_teacher'].queryset = Teacher.objects.none()
            except:
                # If Teacher model doesn't exist, remove the field
                self.fields['class_teacher'].widget = forms.HiddenInput()
                self.fields['class_teacher'].required = False
        
        # Set classroom queryset
        try:
            self.fields['classroom'].queryset = ClassRoom.objects.filter(
                is_active=True
            ).order_by('building', 'room_number')
        except Exception as e:
            logger.error(f"Error setting classroom queryset: {e}")
            self.fields['classroom'].queryset = ClassRoom.objects.none()


# =============================================================================
# STUDENT CLASS ENROLLMENT FILTER FORM
# =============================================================================

class StudentClassEnrollmentFilterForm(HTMXFilterFormMixin, DateRangeFormMixin, BootstrapFormMixin, forms.Form):
    """
    HTMX-powered student class enrollment filter form.
    Uses school timezone for date validations.
    """
    
    htmx_get = 'academics:enrollment_search'
    htmx_target = '#enrollment-list'
    search_delay = 300
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by student name, roll number...'
        })
    )
    
    class_instance = forms.ModelChoiceField(
        label='Class',
        queryset=None,
        required=False,
        widget=SelectWithDefault(default_label="All Classes")
    )
    
    academic_session = forms.ModelChoiceField(
        label='Academic Session',
        queryset=None,
        required=False,
        widget=SelectWithDefault(default_label="All Sessions")
    )
    
    enrollment_type = forms.ChoiceField(
        label='Enrollment Type',
        choices=[('', 'All Types')] + StudentClassEnrollment.ENROLLMENT_TYPE_CHOICES,
        required=False,
        widget=SelectWithDefault(default_label="All Types")
    )
    
    completion_status = forms.ChoiceField(
        label='Completion Status',
        choices=[('', 'All Statuses')] + StudentClassEnrollment.COMPLETION_STATUS_CHOICES,
        required=False,
        widget=SelectWithDefault(default_label="All Statuses")
    )
    
    progression_type = forms.ChoiceField(
        label='Progression Type',
        choices=[('', 'All Types')] + StudentClassEnrollment.PROGRESSION_TYPE_CHOICES,
        required=False,
        widget=SelectWithDefault(default_label="All Types")
    )
    
    is_active = forms.NullBooleanField(
        label='Active Status',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Active'),
            ('false', 'Inactive')
        ], attrs={'class': 'form-select'})
    )
    
    has_invoice = forms.NullBooleanField(
        label='Invoice Status',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Has Invoice'),
            ('false', 'No Invoice')
        ], attrs={'class': 'form-select'})
    )
    
    # Date range filters
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
    
    def __init__(self, *args, **kwargs):
        search_url = kwargs.pop('search_url', None)
        if search_url:
            self.htmx_get = search_url
        
        super().__init__(*args, **kwargs)
        
        # Set querysets
        try:
            self.fields['class_instance'].queryset = Class.objects.filter(
                is_active=True
            ).select_related('academic_level', 'academic_session').order_by(
                '-academic_session__start_date',
                'academic_level__order',
                'section'
            )
        except Exception as e:
            logger.error(f"Error setting class queryset: {e}")
        
        try:
            self.fields['academic_session'].queryset = AcademicSession.objects.filter(
                is_active=True
            ).order_by('-start_date')
        except Exception as e:
            logger.error(f"Error setting session queryset: {e}")


# =============================================================================
# CLASS SUBJECT FILTER FORM
# =============================================================================

class ClassSubjectFilterForm(HTMXFilterFormMixin, BootstrapFormMixin, forms.Form):
    """
    HTMX-powered class subject filter form.
    """
    
    htmx_get = None
    htmx_target = '#class-subject-list'
    search_delay = 300
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search subjects...'
        })
    )
    
    class_instance = forms.ModelChoiceField(
        label='Class',
        queryset=None,
        required=False,
        widget=SelectWithDefault(default_label="All Classes")
    )
    
    subject = forms.ModelChoiceField(
        label='Subject',
        queryset=None,
        required=False,
        widget=SelectWithDefault(default_label="All Subjects")
    )
    
    teacher = forms.ModelChoiceField(
        label='Teacher',
        queryset=None,
        required=False,
        widget=SelectWithDefault(default_label="All Teachers")
    )
    
    is_optional = forms.NullBooleanField(
        label='Optional',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Optional'),
            ('false', 'Compulsory')
        ], attrs={'class': 'form-select'})
    )
    
    is_active = forms.NullBooleanField(
        label='Active Status',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Active'),
            ('false', 'Inactive')
        ], attrs={'class': 'form-select'})
    )
    
    def __init__(self, *args, **kwargs):
        search_url = kwargs.pop('search_url', None)
        if search_url:
            self.htmx_get = search_url
        
        super().__init__(*args, **kwargs)
        
        # Set querysets
        try:
            self.fields['class_instance'].queryset = Class.objects.filter(
                is_active=True
            ).select_related('academic_level', 'academic_session').order_by(
                'academic_level__order',
                'section'
            )
        except Exception as e:
            logger.error(f"Error setting class queryset: {e}")
        
        try:
            self.fields['subject'].queryset = Subject.objects.filter(
                is_active=True
            ).order_by('name')
        except Exception as e:
            logger.error(f"Error setting subject queryset: {e}")
        
        try:
            from hr.models import Teacher
            self.fields['teacher'].queryset = Teacher.objects.filter(
                is_active=True
            ).order_by('user__last_name', 'user__first_name')
        except Exception as e:
            logger.error(f"Error setting teacher queryset: {e}")


# =============================================================================
# ACADEMIC PROGRESS FILTER FORM
# =============================================================================

class AcademicProgressFilterForm(HTMXFilterFormMixin, BootstrapFormMixin, forms.Form):
    """
    HTMX-powered academic progress filter form.
    """
    
    htmx_get = None
    htmx_target = '#progress-list'
    search_delay = 300
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by student name...'
        })
    )
    
    academic_session = forms.ModelChoiceField(
        label='Academic Session',
        queryset=None,
        required=False,
        widget=SelectWithDefault(default_label="All Sessions")
    )
    
    class_enrollment = forms.ModelChoiceField(
        label='Class',
        queryset=None,
        required=False,
        widget=SelectWithDefault(default_label="All Classes")
    )
    
    progress_status = forms.ChoiceField(
        label='Progress Status',
        choices=[('', 'All Statuses')] + AcademicProgress.PROGRESS_STATUS_CHOICES,
        required=False,
        widget=SelectWithDefault(default_label="All Statuses")
    )
    
    promotion_decision = forms.ChoiceField(
        label='Promotion Decision',
        choices=[('', 'All Decisions')] + AcademicProgress.PROMOTION_DECISION_CHOICES,
        required=False,
        widget=SelectWithDefault(default_label="All Decisions")
    )
    
    is_eligible_for_promotion = forms.NullBooleanField(
        label='Promotion Eligibility',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Eligible'),
            ('false', 'Not Eligible')
        ], attrs={'class': 'form-select'})
    )
    
    is_final = forms.NullBooleanField(
        label='Finalized',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Finalized'),
            ('false', 'Not Finalized')
        ], attrs={'class': 'form-select'})
    )
    
    min_percentage = forms.DecimalField(
        label='Minimum Percentage',
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Min %',
            'step': '0.01',
            'min': '0',
            'max': '100'
        })
    )
    
    max_percentage = forms.DecimalField(
        label='Maximum Percentage',
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Max %',
            'step': '0.01',
            'min': '0',
            'max': '100'
        })
    )
    
    min_gpa = forms.DecimalField(
        label='Minimum GPA',
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Min GPA',
            'step': '0.01',
            'min': '0',
            'max': '4'
        })
    )
    
    def __init__(self, *args, **kwargs):
        search_url = kwargs.pop('search_url', None)
        if search_url:
            self.htmx_get = search_url
        
        super().__init__(*args, **kwargs)
        
        # Set querysets
        try:
            self.fields['academic_session'].queryset = AcademicSession.objects.all().order_by('-start_date')
        except Exception as e:
            logger.error(f"Error setting session queryset: {e}")
        
        try:
            self.fields['class_enrollment'].queryset = Class.objects.filter(
                is_active=True
            ).select_related('academic_level', 'academic_session').order_by(
                '-academic_session__start_date',
                'academic_level__order'
            )
        except Exception as e:
            logger.error(f"Error setting class queryset: {e}")

# =============================================================================
# ACADEMIC SESSION FORM
# =============================================================================

class AcademicSessionForm(BootstrapFormMixin, RequiredFieldsMixin, forms.ModelForm):
    """
    Form for creating/editing academic sessions.
    All date validations use school timezone. ⭐
    """
    
    class Meta:
        model = AcademicSession
        fields = [
            'year_name', 'term_number', 'term_name', 'period_type',
            'is_special_session', 'start_date', 'end_date',
            'enrollment_deadline', 'late_enrollment_allowed',
            'is_current', 'is_active', 'allows_promotion',
            'minimum_attendance_percentage', 'description',
        ]
        widgets = {
            'year_name': forms.TextInput(attrs={
                'placeholder': 'e.g., 2024 or 2024-2025'
            }),
            'term_number': forms.NumberInput(attrs={
                'min': '1',
                'max': '20',
                'placeholder': '1'
            }),
            'term_name': forms.TextInput(attrs={
                'placeholder': 'Leave blank to auto-generate'
            }),
            'period_type': forms.Select(),
            'start_date': DatePickerInput(),
            'end_date': DatePickerInput(),
            'enrollment_deadline': DatePickerInput(),
            'minimum_attendance_percentage': PercentageInput(),
            'description': forms.Textarea(attrs={'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Add help text
        self.fields['year_name'].help_text = (
            'Format: "YYYY" or "YYYY-YYYY" or "YYYY/YYYY"'
        )
        self.fields['term_number'].help_text = (
            'Position within academic year (1, 2, 3, etc.)'
        )
        self.fields['term_name'].help_text = (
            'Leave blank for regular sessions (auto-generated). '
            'Provide custom name for special sessions.'
        )
        self.fields['is_special_session'].help_text = (
            'Check for holiday programs, summer school, or remedial classes'
        )
    
    def clean_start_date(self):
        """Validate start date using school timezone ⭐"""
        start_date = self.cleaned_data.get('start_date')
        if start_date:
            from core.utils import get_school_today
            from datetime import timedelta
            
            today = get_school_today()  # ⭐ SCHOOL TIMEZONE
            
            # Allow sessions to be created up to 2 years in advance
            max_future = today + timedelta(days=2*365)
            if start_date > max_future:
                raise ValidationError(
                    "Start date cannot be more than 2 years in the future."
                )
        
        return start_date
    
    def clean(self):
        """
        Cross-field validation using school timezone. ⭐
        """
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        enrollment_deadline = cleaned_data.get('enrollment_deadline')
        
        # Validate date range
        if start_date and end_date:
            if start_date >= end_date:
                raise ValidationError({
                    'end_date': 'End date must be after start date.'
                })
        
        # Validate enrollment deadline
        if enrollment_deadline:
            if start_date and enrollment_deadline < start_date:
                raise ValidationError({
                    'enrollment_deadline': 'Enrollment deadline cannot be before start date.'
                })
            
            if end_date and enrollment_deadline > end_date:
                raise ValidationError({
                    'enrollment_deadline': 'Enrollment deadline cannot be after end date.'
                })
        
        return cleaned_data


# =============================================================================
# HOLIDAY FORM
# =============================================================================

class HolidayForm(BootstrapFormMixin, RequiredFieldsMixin, forms.ModelForm):
    """
    Form for creating/editing holidays.
    Uses school timezone for date validations. ⭐
    """
    
    class Meta:
        model = Holiday
        fields = [
            'name', 'holiday_type', 'start_date', 'end_date',
            'academic_session', 'is_school_closed', 'is_partial_closure',
            'affects_attendance', 'affects_payroll', 'is_recurring',
            'color', 'notify_parents', 'notify_staff',
            'description', 'notes',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Holiday name'}),
            'start_date': DatePickerInput(),
            'end_date': DatePickerInput(),
            'color': forms.TextInput(attrs={
                'type': 'color',
                'class': 'form-control form-control-color'
            }),
            'description': forms.Textarea(attrs={'rows': 3}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set academic session queryset
        try:
            self.fields['academic_session'].queryset = AcademicSession.objects.filter(
                is_active=True
            ).order_by('-start_date')
        except Exception as e:
            logger.error(f"Error setting session queryset: {e}")
        
        # Help text
        self.fields['end_date'].help_text = 'Leave blank for single-day holidays'
        self.fields['is_recurring'].help_text = 'Check if this holiday repeats annually'
    
    def clean_start_date(self):
        """Validate start date using school timezone ⭐"""
        start_date = self.cleaned_data.get('start_date')
        if start_date:
            from core.utils import get_school_today
            from datetime import timedelta
            
            today = get_school_today()  # ⭐ SCHOOL TIMEZONE
            
            # Allow holidays to be created up to 2 years in advance
            max_future = today + timedelta(days=2*365)
            if start_date > max_future:
                raise ValidationError(
                    "Start date cannot be more than 2 years in the future."
                )
        
        return start_date
    
    def clean(self):
        """Validate date range using school timezone ⭐"""
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        
        if start_date and end_date:
            if start_date > end_date:
                raise ValidationError({
                    'end_date': 'End date cannot be before start date.'
                })
        
        return cleaned_data


# =============================================================================
# SUBJECT FORM
# =============================================================================

class SubjectForm(BootstrapFormMixin, RequiredFieldsMixin, forms.ModelForm):
    """Form for creating/editing subjects."""
    
    class Meta:
        model = Subject
        fields = [
            'name', 'abbreviation', 'code', 'subject_type',
            'credit_hours', 'pass_mark', 'difficulty_level',
            'weight_factor', 'is_compulsory', 'is_active',
            'prerequisites', 'applicable_levels', 'department',
            'textbook_required', 'recommended_textbooks',
            'required_materials', 'description',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Subject name'}),
            'abbreviation': forms.TextInput(attrs={'placeholder': 'e.g., MATH'}),
            'code': forms.TextInput(attrs={'placeholder': 'e.g., MTH101'}),
            'credit_hours': forms.NumberInput(attrs={
                'step': '0.5',
                'min': '0.5',
                'max': '20'
            }),
            'pass_mark': forms.NumberInput(attrs={
                'step': '0.01',
                'min': '0',
                'max': '100'
            }),
            'weight_factor': forms.NumberInput(attrs={
                'step': '0.01',
                'min': '0.5',
                'max': '3.0'
            }),
            'description': forms.Textarea(attrs={'rows': 3}),
            'recommended_textbooks': forms.Textarea(attrs={'rows': 2}),
            'required_materials': forms.Textarea(attrs={'rows': 2}),
        }


# =============================================================================
# ACADEMIC LEVEL FORM
# =============================================================================

class AcademicLevelForm(BootstrapFormMixin, RequiredFieldsMixin, forms.ModelForm):
    """Form for creating/editing academic levels."""
    
    class Meta:
        model = AcademicLevel
        fields = [
            'name', 'code', 'order', 'next_level',
            'has_sections', 'is_active', 'is_graduation_level',
            'description',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g., Grade 1'}),
            'code': forms.TextInput(attrs={'placeholder': 'e.g., G1'}),
            'order': forms.NumberInput(attrs={'min': '1'}),
            'description': forms.Textarea(attrs={'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Filter next_level to exclude self
        if self.instance.pk:
            self.fields['next_level'].queryset = AcademicLevel.objects.exclude(
                pk=self.instance.pk
            )


# =============================================================================
# CLASSROOM FORM
# =============================================================================

class ClassRoomForm(BootstrapFormMixin, RequiredFieldsMixin, forms.ModelForm):
    """Form for creating/editing classrooms."""
    
    last_maintenance_date = forms.DateField(
        label='Last Maintenance Date',
        required=False,
        widget=DatePickerInput()
    )
    
    safety_inspection_date = forms.DateField(
        label='Safety Inspection Date',
        required=False,
        widget=DatePickerInput()
    )
    
    class Meta:
        model = ClassRoom
        fields = [
            'name', 'room_number', 'building', 'floor', 'wing',
            'capacity', 'room_type', 'is_active',
            'has_projector', 'has_computer', 'has_air_conditioning',
            'has_whiteboard', 'has_blackboard', 'has_smart_board',
            'has_internet', 'has_sound_system',
            'specialized_equipment', 'is_accessible', 'accessibility_features',
            'is_bookable', 'requires_approval',
            'last_maintenance_date', 'safety_inspection_date',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Room name'}),
            'room_number': forms.TextInput(attrs={'placeholder': 'e.g., A101'}),
            'capacity': forms.NumberInput(attrs={'min': '1'}),
            'specialized_equipment': forms.Textarea(attrs={'rows': 2}),
            'accessibility_features': forms.Textarea(attrs={'rows': 2}),
        }
    
    def clean_last_maintenance_date(self):
        """Validate maintenance date using school timezone ⭐"""
        date = self.cleaned_data.get('last_maintenance_date')
        if date:
            validate_future_date(date)  # ⭐ Uses school timezone
        return date
    
    def clean_safety_inspection_date(self):
        """Validate inspection date using school timezone ⭐"""
        date = self.cleaned_data.get('safety_inspection_date')
        if date:
            validate_future_date(date)  # ⭐ Uses school timezone
        return date

# =============================================================================
# CLASS FORM (COMPLETE FIX)
# =============================================================================

class ClassForm(BootstrapFormMixin, RequiredFieldsMixin, forms.ModelForm):
    """Form for creating/editing classes with proper queryset handling."""
    
    start_time = forms.TimeField(
        label='Start Time',
        required=False,
        widget=forms.TimeInput(attrs={
            'type': 'time',
            'class': 'form-control'
        })
    )
    
    end_time = forms.TimeField(
        label='End Time',
        required=False,
        widget=forms.TimeInput(attrs={
            'type': 'time',
            'class': 'form-control'
        })
    )
    
    class Meta:
        model = Class
        fields = [
            'academic_level', 'section', 'academic_session',
            'class_teacher', 'assistant_teacher', 'classroom',
            'max_students', 'start_time', 'end_time',
            'class_motto', 'class_colors', 'is_active',
        ]
        widgets = {
            'section': forms.TextInput(attrs={'placeholder': 'e.g., A, B, C'}),
            'max_students': forms.NumberInput(attrs={'min': '1', 'value': '30'}),
            'class_motto': forms.TextInput(attrs={'placeholder': 'Class motto'}),
            'class_colors': forms.TextInput(attrs={'placeholder': 'e.g., Blue and White'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # ⭐ Set academic level queryset
        try:
            self.fields['academic_level'].queryset = AcademicLevel.objects.filter(
                is_active=True
            ).order_by('order')
        except Exception as e:
            logger.error(f"Error setting academic level queryset: {e}")
            self.fields['academic_level'].queryset = AcademicLevel.objects.none()
        
        # ⭐ Set academic session queryset
        try:
            self.fields['academic_session'].queryset = AcademicSession.objects.filter(
                is_active=True
            ).order_by('-start_date')
        except Exception as e:
            logger.error(f"Error setting session queryset: {e}")
            self.fields['academic_session'].queryset = AcademicSession.objects.none()
        
        # ⭐ Set classroom queryset
        try:
            self.fields['classroom'].queryset = ClassRoom.objects.filter(
                is_active=True
            ).order_by('building', 'room_number')
        except Exception as e:
            logger.error(f"Error setting classroom queryset: {e}")
            self.fields['classroom'].queryset = ClassRoom.objects.none()
        
        # ⭐ Set teacher querysets
        try:
            from hr.models import Teacher
            teacher_queryset = Teacher.objects.filter(
                is_active=True
            ).order_by('user__last_name', 'user__first_name')
            
            self.fields['class_teacher'].queryset = teacher_queryset
            self.fields['assistant_teacher'].queryset = teacher_queryset
        except ImportError:
            logger.error("Teacher model not found - hr app may not be installed")
            # Hide teacher fields if hr app not available
            self.fields['class_teacher'].widget = forms.HiddenInput()
            self.fields['class_teacher'].required = False
            self.fields['assistant_teacher'].widget = forms.HiddenInput()
            self.fields['assistant_teacher'].required = False
        except Exception as e:
            logger.error(f"Error setting teacher queryset: {e}")
            try:
                from hr.models import Teacher
                self.fields['class_teacher'].queryset = Teacher.objects.none()
                self.fields['assistant_teacher'].queryset = Teacher.objects.none()
            except:
                pass
    
    def clean(self):
        """Validate class configuration"""
        cleaned_data = super().clean()
        
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        
        # Validate time schedule
        if start_time and end_time:
            if start_time >= end_time:
                raise ValidationError({
                    'end_time': 'End time must be after start time.'
                })
        
        return cleaned_data

# =============================================================================
# STUDENT CLASS ENROLLMENT FORM
# =============================================================================

class StudentClassEnrollmentForm(BootstrapFormMixin, RequiredFieldsMixin, forms.ModelForm):
    """
    Form for enrolling students in classes.
    Uses school timezone for date validations. ⭐
    """
    
    class Meta:
        model = StudentClassEnrollment
        fields = [
            'student', 'class_instance', 'academic_session',
            'enrollment_date', 'enrollment_type', 'roll_number',
            'progression_type', 'is_active', 'auto_create_invoice',
            'enrollment_notes',
        ]
        widgets = {
            'enrollment_date': DatePickerInput(),
            'roll_number': forms.TextInput(attrs={'placeholder': 'Roll number'}),
            'enrollment_notes': forms.Textarea(attrs={'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set default enrollment date (school timezone) ⭐
        if not self.is_bound and not self.instance.pk:
            from core.utils import get_school_today
            self.fields['enrollment_date'].initial = get_school_today()
        
        # Set querysets
        try:
            from students.models import Student
            self.fields['student'].queryset = Student.objects.filter(
                enrollment_status='ACTIVE'
            ).order_by('last_name', 'first_name')
        except Exception as e:
            logger.error(f"Error setting student queryset: {e}")
        
        try:
            self.fields['academic_session'].queryset = AcademicSession.objects.filter(
                is_active=True
            ).order_by('-start_date')
        except Exception as e:
            logger.error(f"Error setting session queryset: {e}")
        
        try:
            self.fields['class_instance'].queryset = Class.objects.filter(
                is_active=True
            ).select_related('academic_level', 'academic_session')
        except Exception as e:
            logger.error(f"Error setting class queryset: {e}")
    
    def clean_enrollment_date(self):
        """Validate enrollment date using school timezone ⭐"""
        enrollment_date = self.cleaned_data.get('enrollment_date')
        if enrollment_date:
            from core.utils import get_school_today
            from datetime import timedelta
            
            today = get_school_today()  # ⭐ SCHOOL TIMEZONE
            
            # Validate not in future
            if enrollment_date > today:
                raise ValidationError("Enrollment date cannot be in the future.")
            
            # Validate not too far in past (2 years)
            if enrollment_date < (today - timedelta(days=2*365)):
                raise ValidationError(
                    "Enrollment date seems too far in the past. Please verify."
                )
        
        return enrollment_date


class StudentClassEnrollmentQuickForm(BootstrapFormMixin, forms.ModelForm):
    """Quick enrollment form (minimal fields)."""
    
    class Meta:
        model = StudentClassEnrollment
        fields = ['student', 'class_instance', 'enrollment_date']
        widgets = {
            'enrollment_date': DatePickerInput()
        }
    
    def __init__(self, *args, **kwargs):
        # Pre-set class_instance if provided
        class_instance = kwargs.pop('class_instance', None)
        super().__init__(*args, **kwargs)
        
        if class_instance:
            self.fields['class_instance'].initial = class_instance
            self.fields['class_instance'].widget = forms.HiddenInput()
        
        # Set default date (school timezone) ⭐
        if not self.is_bound and not self.instance.pk:
            from core.utils import get_school_today
            self.fields['enrollment_date'].initial = get_school_today()
        
        # Set student queryset
        try:
            from students.models import Student
            self.fields['student'].queryset = Student.objects.filter(
                enrollment_status='ACTIVE'
            ).order_by('last_name', 'first_name')
        except Exception as e:
            logger.error(f"Error setting student queryset: {e}")

# =============================================================================
# BULK ENROLLMENT FORMS (Updated to use utils/forms.py properly!)
# =============================================================================

class BulkEnrollmentForm(BootstrapFormMixin, RequiredFieldsMixin, forms.Form):
    """
    Enhanced bulk enrollment form using your utils/forms.py components.
    Now properly integrated with all your form utilities!
    """
    
    ENROLLMENT_TYPE_CHOICES = [
        ('BULK', 'Bulk Enrollment'),
        ('NEW', 'New Student'),
        ('PROMOTED', 'Promoted'),
        ('TRANSFERRED', 'Transfer In'),
        ('READMIT', 'Readmission'),
    ]
    
    # Core fields using your custom widgets
    academic_session = forms.ModelChoiceField(
        queryset=AcademicSession.objects.filter(is_active=True),
        label="Academic Session",
        help_text="Select the academic session for enrollment",
        widget=forms.Select(attrs={
            'class': 'form-control select2',
            'data-placeholder': 'Select Academic Session'
        })
    )
    
    class_instance = forms.ModelChoiceField(
        queryset=Class.objects.none(),
        label="Class",
        help_text="Select the class to enroll students in",
        widget=forms.Select(attrs={
            'class': 'form-control select2',
            'data-placeholder': 'Select Class'
        })
    )
    
    students = forms.ModelMultipleChoiceField(
        queryset=Student.objects.none(),
        label="Students",
        help_text="Select students to enroll (hold Ctrl/Cmd for multiple selection)",
        widget=forms.SelectMultiple(attrs={
            'class': 'form-control select2-multiple',
            'data-placeholder': 'Select Students',
            'multiple': True,
            'size': '10'
        })
    )
    
    enrollment_type = forms.ChoiceField(
        choices=ENROLLMENT_TYPE_CHOICES,
        initial='BULK',
        label="Enrollment Type",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    auto_create_invoices = forms.BooleanField(
        required=False,
        initial=True,
        label="Create Fee Invoices",
        help_text="Automatically create fee invoices for enrolled students",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    enrollment_notes = forms.CharField(
        required=False,
        label="Enrollment Notes",
        help_text="Optional notes for this bulk enrollment",
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Add any notes about this bulk enrollment...'
        })
    )
    
    # ✅ Use your ConfirmationForm pattern
    confirm_enrollment = forms.BooleanField(
        required=True,
        label="I confirm this bulk enrollment",
        help_text="Check this box to confirm you want to proceed with the bulk enrollment",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        
        # Populate querysets based on available data
        self._populate_academic_sessions()
        self._populate_classes()
        self._populate_available_students()
    
    def _populate_academic_sessions(self):
        """Populate academic session choices"""
        try:
            sessions = AcademicSession.objects.filter(
                is_active=True
            ).order_by('-is_current', '-start_date')
            
            self.fields['academic_session'].queryset = sessions
            
            # Set current session as initial if available
            current_session = sessions.filter(is_current=True).first()
            if current_session and not self.initial.get('academic_session'):
                self.initial['academic_session'] = current_session
                
        except Exception as e:
            logger.error(f"Error populating academic sessions: {e}")
            self.fields['academic_session'].queryset = AcademicSession.objects.none()
    
    def _populate_classes(self):
        """Populate class choices"""
        try:
            classes = Class.objects.filter(
                academic_session__is_active=True,
                is_active=True
            ).select_related(
                'academic_level', 'academic_session'
            ).order_by('academic_level__order', 'section')
            
            self.fields['class_instance'].queryset = classes
            
        except Exception as e:
            logger.error(f"Error populating classes: {e}")
            self.fields['class_instance'].queryset = Class.objects.none()
    
    def _populate_available_students(self):
        """Populate students available for enrollment"""
        try:
            available_students = Student.objects.filter(
                enrollment_status='ACTIVE'
            ).exclude(
                class_enrollments__is_active=True,
                class_enrollments__completion_status='ONGOING'
            ).order_by('last_name', 'first_name')
            
            self.fields['students'].queryset = available_students
            
        except Exception as e:
            logger.error(f"Error populating available students: {e}")
            self.fields['students'].queryset = Student.objects.none()
    
    def clean(self):
        """Enhanced validation using your validation patterns"""
        cleaned_data = super().clean()
        
        class_instance = cleaned_data.get('class_instance')
        students = cleaned_data.get('students')
        academic_session = cleaned_data.get('academic_session')
        
        if not class_instance or not students or not academic_session:
            return cleaned_data
        
        # Validate class capacity using your utilities
        self._validate_class_capacity(class_instance, students)
        
        # Validate session compatibility
        self._validate_session_compatibility(class_instance, academic_session)
        
        # Validate individual student enrollments
        self._validate_student_enrollments(students, class_instance, academic_session)
        
        return cleaned_data
    
    def _validate_class_capacity(self, class_instance, students):
        """Validate that class has sufficient capacity"""
        try:
            from .utils import get_class_capacity_summary
            
            capacity_info = get_class_capacity_summary(class_instance)
            selected_count = students.count() if hasattr(students, 'count') else len(students)
            available_capacity = capacity_info['available_capacity']
            
            if selected_count > available_capacity:
                raise ValidationError(
                    f"Cannot enroll {selected_count} students. "
                    f"Class {class_instance} only has {available_capacity} available spots "
                    f"(capacity: {class_instance.max_students}, "
                    f"current: {capacity_info['current_enrollment']})."
                )
                
        except Exception as e:
            logger.error(f"Error validating class capacity: {e}")
            raise ValidationError(f"Error checking class capacity: {str(e)}")
    
    def _validate_session_compatibility(self, class_instance, academic_session):
        """Validate that class belongs to the selected session"""
        if class_instance.academic_session != academic_session:
            raise ValidationError(
                f"Class {class_instance} belongs to {class_instance.academic_session}, "
                f"not {academic_session}. Please select a class from the chosen academic session."
            )
    
    def _validate_student_enrollments(self, students, class_instance, academic_session):
        """Validate individual student enrollment eligibility"""
        errors = []
        
        for student in students:
            # Check if student already has an active enrollment in this session
            existing_enrollment = StudentClassEnrollment.objects.filter(
                student=student,
                academic_session=academic_session,
                is_active=True,
                completion_status='ONGOING'
            ).first()
            
            if existing_enrollment:
                errors.append(
                    f"{student.get_full_name()} is already enrolled in "
                    f"{existing_enrollment.class_instance} for {academic_session}."
                )
            
            # Check if student is active
            if student.enrollment_status != 'ACTIVE':
                errors.append(
                    f"{student.get_full_name()} has status '{student.get_enrollment_status_display()}' "
                    f"and cannot be enrolled."
                )
            
            # Limit error messages to avoid overwhelming the user
            if len(errors) >= 5:
                errors.append(f"...and {len(students) - 5} more validation errors.")
                break
        
        if errors:
            raise ValidationError(errors)
    
    def save(self):
        """Process the bulk enrollment using services"""
        try:
            from .services import BulkEnrollmentService
            
            students = self.cleaned_data['students']
            class_instance = self.cleaned_data['class_instance']
            academic_session = self.cleaned_data['academic_session']
            enrollment_type = self.cleaned_data['enrollment_type']
            auto_create_invoices = self.cleaned_data['auto_create_invoices']
            notes = self.cleaned_data.get('enrollment_notes', '')
            
            # Use the bulk enrollment service
            result = BulkEnrollmentService.bulk_enroll_students(
                students=students,
                class_instance=class_instance,
                session=academic_session,
                enrollment_type=enrollment_type,
                auto_create_invoices=auto_create_invoices,
                notes=notes,
                user=self.user
            )
            
            return {
                'success': True,
                'success_count': len(result['enrolled']),
                'failure_count': len(result['failed']),
                'enrolled_students': result['enrolled'],
                'failed_students': result['failed'],
                'invoices_created': result['invoices'],
            }
            
        except Exception as e:
            logger.error(f"Error in bulk enrollment save: {e}")
            return {
                'success': False,
                'error': str(e),
                'success_count': 0,
                'failure_count': 0,
            }
        
# =============================================================================
# CLASS SUBJECT FORM
# =============================================================================

class ClassSubjectForm(BootstrapFormMixin, RequiredFieldsMixin, forms.ModelForm):
    """Form for assigning subjects to classes."""
    
    continuous_assessment_weight = PercentageField(
        label='Continuous Assessment Weight (%)',
        help_text='Percentage weight of continuous assessment'
    )
    
    final_exam_weight = PercentageField(
        label='Final Exam Weight (%)',
        help_text='Percentage weight of final examination'
    )
    
    class Meta:
        model = ClassSubject
        fields = [
            'class_instance', 'subject', 'teacher',
            'is_optional', 'hours_per_week', 'total_hours',
            'continuous_assessment_weight', 'final_exam_weight',
            'textbook', 'reference_materials', 'required_equipment',
            'syllabus', 'learning_objectives', 'assessment_criteria',
            'is_active',
        ]
        widgets = {
            'hours_per_week': forms.NumberInput(attrs={'min': '1', 'value': '3'}),
            'total_hours': forms.NumberInput(attrs={'min': '0', 'value': '0'}),
            'textbook': forms.TextInput(attrs={'placeholder': 'Textbook name'}),
            'reference_materials': forms.Textarea(attrs={'rows': 2}),
            'required_equipment': forms.Textarea(attrs={'rows': 2}),
            'syllabus': forms.Textarea(attrs={'rows': 4}),
            'learning_objectives': forms.Textarea(attrs={'rows': 3}),
            'assessment_criteria': forms.Textarea(attrs={'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set teacher queryset
        try:
            from hr.models import Teacher
            self.fields['teacher'].queryset = Teacher.objects.filter(
                is_active=True
            )
        except Exception as e:
            logger.error(f"Error setting teacher queryset: {e}")
    
    def clean(self):
        """Validate assessment weights"""
        cleaned_data = super().clean()
        ca_weight = cleaned_data.get('continuous_assessment_weight')
        exam_weight = cleaned_data.get('final_exam_weight')
        
        if ca_weight and exam_weight:
            total = ca_weight + exam_weight
            if total != 100:
                raise ValidationError(
                    f'Assessment weights must total 100% (currently {total}%)'
                )
        
        return cleaned_data


# =============================================================================
# ACADEMIC PROGRESS FORM
# =============================================================================

class AcademicProgressForm(BootstrapFormMixin, RequiredFieldsMixin, forms.ModelForm):
    """
    Form for recording academic progress.
    Uses school timezone for date validations. ⭐
    """
    
    attendance_percentage = PercentageField(
        label='Attendance Percentage',
        required=False
    )
    
    pass_rate = PercentageField(
        label='Pass Rate',
        required=False
    )
    
    class Meta:
        model = AcademicProgress
        fields = [
            'student', 'academic_session', 'class_enrollment',
            'overall_grade', 'gpa', 'percentage',
            'total_school_days', 'days_attended', 'attendance_percentage',
            'progress_status', 'is_eligible_for_promotion',
            'promotion_decision', 'promoted_to_level',
            'total_subjects', 'subjects_passed', 'subjects_failed',
            'teacher_comments', 'head_teacher_comments',
            'recommendations',
        ]
        widgets = {
            'overall_grade': forms.TextInput(attrs={'placeholder': 'e.g., A, B+'}),
            'gpa': forms.NumberInput(attrs={
                'step': '0.01',
                'min': '0',
                'max': '4',
                'placeholder': '0.00'
            }),
            'percentage': forms.NumberInput(attrs={
                'step': '0.01',
                'min': '0',
                'max': '100',
                'placeholder': '0.00'
            }),
            'total_school_days': forms.NumberInput(attrs={'min': '0'}),
            'days_attended': forms.NumberInput(attrs={'min': '0'}),
            'total_subjects': forms.NumberInput(attrs={'min': '0'}),
            'subjects_passed': forms.NumberInput(attrs={'min': '0'}),
            'subjects_failed': forms.NumberInput(attrs={'min': '0'}),
            'teacher_comments': forms.Textarea(attrs={'rows': 4}),
            'head_teacher_comments': forms.Textarea(attrs={'rows': 4}),
            'recommendations': forms.Textarea(attrs={'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set querysets
        try:
            from students.models import Student
            self.fields['student'].queryset = Student.objects.filter(
                enrollment_status='ACTIVE'
            ).order_by('last_name', 'first_name')
        except Exception as e:
            logger.error(f"Error setting student queryset: {e}")
        
        # Read-only fields if record is finalized
        if self.instance.pk and self.instance.is_final:
            for field_name in self.fields:
                if field_name not in ['teacher_comments', 'head_teacher_comments']:
                    self.fields[field_name].widget.attrs['readonly'] = True
                    self.fields[field_name].disabled = True


class AcademicProgressQuickForm(BootstrapFormMixin, forms.ModelForm):
    """Quick form for basic progress entry."""
    
    class Meta:
        model = AcademicProgress
        fields = [
            'overall_grade', 'percentage',
            'days_attended', 'total_school_days',
            'teacher_comments',
        ]
        widgets = {
            'overall_grade': forms.TextInput(attrs={'placeholder': 'Grade'}),
            'percentage': forms.NumberInput(attrs={
                'step': '0.01',
                'min': '0',
                'max': '100'
            }),
            'teacher_comments': forms.Textarea(attrs={'rows': 3}),
        }


# =============================================================================
# BULK OPERATIONS FORMS
# =============================================================================

class BulkEnrollmentForm(BootstrapFormMixin, forms.Form):
    """Form for bulk student enrollment."""
    
    class_instance = forms.ModelChoiceField(
        label='Class',
        queryset=None,
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    students = forms.ModelMultipleChoiceField(
        label='Students',
        queryset=None,
        required=True,
        widget=forms.SelectMultiple(attrs={'class': 'form-select', 'size': '10'})
    )
    
    enrollment_date = forms.DateField(
        label='Enrollment Date',
        required=True,
        widget=DatePickerInput()
    )
    
    enrollment_type = forms.ChoiceField(
        label='Enrollment Type',
        choices=StudentClassEnrollment.ENROLLMENT_TYPE_CHOICES,
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set default date (school timezone) ⭐
        if not self.is_bound:
            from core.utils import get_school_today
            self.fields['enrollment_date'].initial = get_school_today()
        
        # Set querysets
        try:
            self.fields['class_instance'].queryset = Class.objects.filter(
                is_active=True
            ).select_related('academic_level', 'academic_session')
        except Exception as e:
            logger.error(f"Error setting class queryset: {e}")
        
        try:
            from students.models import Student
            self.fields['students'].queryset = Student.objects.filter(
                enrollment_status='ACTIVE'
            ).order_by('last_name', 'first_name')
        except Exception as e:
            logger.error(f"Error setting student queryset: {e}")


class CloseSessionForm(BootstrapFormMixin, forms.Form):
    """Form for closing academic sessions."""
    
    confirm = forms.BooleanField(
        label='I confirm that I want to close this academic session',
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    reason = forms.CharField(
        label='Reason for Closure',
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'Optional: Reason for closing this session'
        })
    )


class PromoteStudentsForm(BootstrapFormMixin, forms.Form):
    """Form for promoting students to next level."""
    
    from_level = forms.ModelChoiceField(
        label='From Level',
        queryset=None,
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    to_level = forms.ModelChoiceField(
        label='To Level',
        queryset=None,
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    academic_session = forms.ModelChoiceField(
        label='Academic Session',
        queryset=None,
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    only_eligible = forms.BooleanField(
        label='Only promote eligible students',
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set querysets
        try:
            self.fields['from_level'].queryset = AcademicLevel.objects.filter(
                is_active=True
            ).order_by('order')
            self.fields['to_level'].queryset = AcademicLevel.objects.filter(
                is_active=True
            ).order_by('order')
        except Exception as e:
            logger.error(f"Error setting level queryset: {e}")
        
        try:
            self.fields['academic_session'].queryset = AcademicSession.objects.filter(
                is_active=True
            ).order_by('-start_date')
        except Exception as e:
            logger.error(f"Error setting session queryset: {e}")