# academics/forms.py

"""
Academic management forms with timezone support.
All date validations use school timezone for consistency.

HTMX configuration removed - to be handled in views and templates.
"""

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db.models import Q
from decimal import Decimal
from django.urls import reverse_lazy
import re
import logging

# Import base form utilities with timezone support ⭐
from utils.forms import (
    BootstrapFormMixin,
    DateRangeFormMixin,
    RequiredFieldsMixin,
    DatePickerInput,
    SearchInput,
    PercentageField,
    PercentageInput,
    validate_future_date,  # ⭐ Uses school timezone
    validate_past_date,  # ⭐ Uses school timezone
    validate_date_not_before,  # ⭐ Uses school timezone
    validate_date_not_after,  # ⭐ Uses school timezone
)

# Import school timezone utilities ⭐
from core.utils import get_school_today, get_school_current_time

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
# ACADEMIC SESSION FILTER FORMS
# =============================================================================

class AcademicSessionFilterForm(BootstrapFormMixin, forms.Form):
    """Filter form for academic session search"""
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by year name, term name...'
        })
    )
    
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
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
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
    
    year_name = forms.CharField(
        label='Academic Year',
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g., 2024 or 2024-2025'
        })
    )


class HolidayFilterForm(DateRangeFormMixin, BootstrapFormMixin, forms.Form):
    """Filter form for holiday search"""
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={'placeholder': 'Search holidays...'})
    )
    
    holiday_type = forms.ChoiceField(
        label='Holiday Type',
        choices=[('', 'All Types')] + Holiday.HOLIDAY_TYPE_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
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
        empty_label="All Sessions",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
            self.fields['academic_session'].queryset = AcademicSession.objects.filter(
                is_active=True
            ).order_by('-start_date')
        except Exception as e:
            logger.error(f"Error setting session queryset: {e}")


# =============================================================================
# SUBJECT FILTER FORM
# =============================================================================

class SubjectFilterForm(BootstrapFormMixin, forms.Form):
    """Filter form for subject search"""
    
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
        widget=forms.Select(attrs={'class': 'form-select'})
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
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    department = forms.ModelChoiceField(
        label='Department',
        queryset=None,
        required=False,
        empty_label="All Departments",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    academic_level = forms.ModelChoiceField(
        label='Academic Level',
        queryset=None,
        required=False,
        empty_label="All Levels",
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Filter by applicable academic level"
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
            from hr.models import Department
            self.fields['department'].queryset = Department.objects.filter(
                is_active=True
            ).order_by('name')
        except Exception as e:
            logger.error(f"Error setting department queryset: {e}")
        
        try:
            self.fields['academic_level'].queryset = AcademicLevel.objects.filter(
                is_active=True
            ).order_by('order')
        except Exception as e:
            logger.error(f"Error setting level queryset: {e}")


# =============================================================================
# ACADEMIC LEVEL FILTER FORM
# =============================================================================

class AcademicLevelFilterForm(BootstrapFormMixin, forms.Form):
    """Filter form for academic level search"""
    
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


# =============================================================================
# CLASSROOM FILTER FORM
# =============================================================================

class ClassRoomFilterForm(BootstrapFormMixin, forms.Form):
    """Filter form for classroom search"""
    
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
        widget=forms.Select(attrs={'class': 'form-select'})
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


# =============================================================================
# CLASS FILTER FORM
# =============================================================================

class ClassFilterForm(BootstrapFormMixin, forms.Form):
    """Filter form for class search"""
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search classes...'
        })
    )
    
    academic_level = forms.ModelChoiceField(
        label='Academic Level',
        queryset=AcademicLevel.objects.none(),
        required=False,
        empty_label="All Levels",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    academic_session = forms.ModelChoiceField(
        label='Academic Session',
        queryset=AcademicSession.objects.none(),
        required=False,
        empty_label="All Sessions",
        widget=forms.Select(attrs={'class': 'form-select'})
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
        queryset=None,
        required=False,
        empty_label="All Teachers",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    classroom = forms.ModelChoiceField(
        label='Classroom',
        queryset=ClassRoom.objects.none(),
        required=False,
        empty_label="All Rooms",
        widget=forms.Select(attrs={'class': 'form-select'})
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
        super().__init__(*args, **kwargs)
        
        try:
            self.fields['academic_level'].queryset = AcademicLevel.objects.filter(
                is_active=True
            ).order_by('order')
        except Exception as e:
            logger.error(f"Error setting level queryset: {e}")
            self.fields['academic_level'].queryset = AcademicLevel.objects.none()
        
        try:
            self.fields['academic_session'].queryset = AcademicSession.objects.filter(
                is_active=True
            ).order_by('-start_date')
        except Exception as e:
            logger.error(f"Error setting session queryset: {e}")
            self.fields['academic_session'].queryset = AcademicSession.objects.none()
        
        try:
            from hr.models import Teacher
            self.fields['class_teacher'].queryset = Teacher.objects.filter(
                is_active=True
            ).order_by('user__last_name', 'user__first_name')
        except ImportError:
            logger.error("Teacher model not found - hr app may not be installed")
            self.fields['class_teacher'].widget = forms.HiddenInput()
            self.fields['class_teacher'].required = False
        except Exception as e:
            logger.error(f"Error setting teacher queryset: {e}")
            try:
                from hr.models import Teacher
                self.fields['class_teacher'].queryset = Teacher.objects.none()
            except:
                pass
        
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

class StudentClassEnrollmentFilterForm(DateRangeFormMixin, BootstrapFormMixin, forms.Form):
    """Filter form for student class enrollment search"""
    
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
        empty_label="All Classes",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    academic_session = forms.ModelChoiceField(
        label='Academic Session',
        queryset=None,
        required=False,
        empty_label="All Sessions",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    enrollment_type = forms.ChoiceField(
        label='Enrollment Type',
        choices=[('', 'All Types')] + list(StudentClassEnrollment.ENROLLMENT_TYPE_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    completion_status = forms.ChoiceField(
        label='Completion Status',
        choices=[('', 'All Statuses')] + list(StudentClassEnrollment.COMPLETION_STATUS_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    progression_type = forms.ChoiceField(
        label='Progression Type',
        choices=[('', 'All Types')] + list(StudentClassEnrollment.PROGRESSION_TYPE_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    is_active = forms.ChoiceField(
        label='Active Status',
        required=False,
        choices=[
            ('', 'All'),
            ('true', 'Active'),
            ('false', 'Inactive')
        ],
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    has_invoice = forms.ChoiceField(
        label='Invoice Status',
        required=False,
        choices=[
            ('', 'All'),
            ('true', 'Has Invoice'),
            ('false', 'No Invoice')
        ],
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
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
        super().__init__(*args, **kwargs)
        
        try:
            self.fields['class_instance'].queryset = Class.objects.select_related(
                'academic_level', 'academic_session'
            ).order_by(
                '-academic_session__start_date',
                'academic_level__order',
                'section'
            )
        except Exception as e:
            logger.error(f"Error setting class queryset: {e}")
            self.fields['class_instance'].queryset = Class.objects.none()
        
        try:
            self.fields['academic_session'].queryset = AcademicSession.objects.all().order_by(
                '-start_date'
            )
        except Exception as e:
            logger.error(f"Error setting session queryset: {e}")
            self.fields['academic_session'].queryset = AcademicSession.objects.none()
    
    def clean(self):
        """Validate date range"""
        cleaned_data = super().clean()
        
        enrollment_date_from = cleaned_data.get('enrollment_date_from')
        enrollment_date_to = cleaned_data.get('enrollment_date_to')
        
        if enrollment_date_from and enrollment_date_to:
            if enrollment_date_from > enrollment_date_to:
                raise ValidationError({
                    'enrollment_date_to': 'End date must be after start date.'
                })
        
        return cleaned_data
    
    def get_boolean_value(self, field_name):
        """Convert string boolean values to actual booleans"""
        value = self.cleaned_data.get(field_name)
        if value == 'true':
            return True
        elif value == 'false':
            return False
        return None
    
    def get_filter_summary(self):
        """
        Generate a human-readable summary of active filters
        Returns a list of tuples: (field_label, display_value)
        """
        if not self.is_valid():
            return []
        
        summary = []
        cleaned_data = self.cleaned_data
        
        # Search query
        if cleaned_data.get('q'):
            summary.append(('Search', cleaned_data['q']))
        
        # Class instance
        if cleaned_data.get('class_instance'):
            summary.append(('Class', str(cleaned_data['class_instance'])))
        
        # Academic session
        if cleaned_data.get('academic_session'):
            summary.append(('Academic Session', str(cleaned_data['academic_session'])))
        
        # Enrollment type
        if cleaned_data.get('enrollment_type'):
            display = dict(StudentClassEnrollment.ENROLLMENT_TYPE_CHOICES).get(
                cleaned_data['enrollment_type']
            )
            summary.append(('Enrollment Type', display))
        
        # Completion status
        if cleaned_data.get('completion_status'):
            display = dict(StudentClassEnrollment.COMPLETION_STATUS_CHOICES).get(
                cleaned_data['completion_status']
            )
            summary.append(('Completion Status', display))
        
        # Progression type
        if cleaned_data.get('progression_type'):
            display = dict(StudentClassEnrollment.PROGRESSION_TYPE_CHOICES).get(
                cleaned_data['progression_type']
            )
            summary.append(('Progression Type', display))
        
        # Active status
        is_active = self.get_boolean_value('is_active')
        if is_active is not None:
            summary.append(('Active Status', 'Active' if is_active else 'Inactive'))
        
        # Invoice status
        has_invoice = self.get_boolean_value('has_invoice')
        if has_invoice is not None:
            summary.append(('Invoice Status', 'Has Invoice' if has_invoice else 'No Invoice'))
        
        # Date range
        date_from = cleaned_data.get('enrollment_date_from')
        date_to = cleaned_data.get('enrollment_date_to')
        
        if date_from and date_to:
            summary.append(('Enrollment Date', f'{date_from} to {date_to}'))
        elif date_from:
            summary.append(('Enrolled From', str(date_from)))
        elif date_to:
            summary.append(('Enrolled To', str(date_to)))
        
        return summary


# =============================================================================
# CLASS SUBJECT FILTER FORM
# =============================================================================

class ClassSubjectFilterForm(BootstrapFormMixin, forms.Form):
    """Filter form for class subject search"""
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by subject name, class, or code...',
            'autocomplete': 'off'
        })
    )
    
    class_instance = forms.ModelChoiceField(
        label='Class',
        queryset=None,
        required=False,
        empty_label="All Classes",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    subject = forms.ModelChoiceField(
        label='Subject',
        queryset=None,
        required=False,
        empty_label="All Subjects",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    teacher = forms.ModelChoiceField(
        label='Teacher',
        queryset=None,
        required=False,
        empty_label="All Teachers",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    is_optional = forms.NullBooleanField(
        label='Subject Type',
        required=False,
        widget=forms.Select(
            choices=[
                ('', 'All Types'),
                ('false', 'Compulsory'),
                ('true', 'Optional')
            ],
            attrs={'class': 'form-select'}
        )
    )
    
    is_active = forms.NullBooleanField(
        label='Status',
        required=False,
        widget=forms.Select(
            choices=[
                ('', 'All Status'),
                ('true', 'Active'),
                ('false', 'Inactive')
            ],
            attrs={'class': 'form-select'}
        )
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
            self.fields['class_instance'].queryset = Class.objects.select_related(
                'academic_level',
                'academic_session'
            ).filter(
                is_active=True
            ).order_by(
                '-academic_session__start_date',
                'academic_level__order',
                'section'
            )
            
            self.fields['class_instance'].label_from_instance = lambda obj: (
                f"{obj.academic_level.name}"
                f"{f' {obj.section}' if obj.section else ''}"
                f" - {obj.academic_session.year_name}"
            )
            
        except Exception as e:
            logger.error(f"Error setting class_instance queryset: {e}")
            self.fields['class_instance'].queryset = Class.objects.none()
        
        try:
            self.fields['subject'].queryset = Subject.objects.filter(
                is_active=True
            ).order_by('name')
            
            self.fields['subject'].label_from_instance = lambda obj: (
                f"{obj.code} - {obj.name}"
            )
            
        except Exception as e:
            logger.error(f"Error setting subject queryset: {e}")
            self.fields['subject'].queryset = Subject.objects.none()
        
        try:
            from hr.models import Teacher
            
            self.fields['teacher'].queryset = Teacher.objects.select_related(
                'staff'
            ).filter(
                staff__is_active=True
            ).order_by(
                'staff__first_name',
                'staff__last_name'
            )
            
            self.fields['teacher'].label_from_instance = lambda obj: (
                f"{obj.staff.full_name()} ({obj.staff.staff_id})"
            )
            
        except ImportError:
            logger.error("Teacher model not found - hr app may not be installed")
            self.fields['teacher'].queryset = Teacher.objects.none()
        except Exception as e:
            logger.error(f"Error setting teacher queryset: {e}")
            try:
                from hr.models import Teacher
                self.fields['teacher'].queryset = Teacher.objects.none()
            except:
                pass


# =============================================================================
# ACADEMIC PROGRESS FILTER FORM
# =============================================================================

class AcademicProgressFilterForm(BootstrapFormMixin, forms.Form):
    """Filter form for academic progress search"""
    
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
        empty_label="All Sessions",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    class_enrollment = forms.ModelChoiceField(
        label='Class',
        queryset=None,
        required=False,
        empty_label="All Classes",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    progress_status = forms.ChoiceField(
        label='Progress Status',
        choices=[('', 'All Statuses')] + AcademicProgress.PROGRESS_STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    promotion_decision = forms.ChoiceField(
        label='Promotion Decision',
        choices=[('', 'All Decisions')] + AcademicProgress.PROMOTION_DECISION_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
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
        super().__init__(*args, **kwargs)
        
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
                'placeholder': 'e.g., 2024 or 2024-2025',
                'class': 'form-control'
            }),
            'term_number': forms.NumberInput(attrs={
                'min': '1',
                'max': '20',
                'placeholder': '1',
                'class': 'form-control'
            }),
            'term_name': forms.TextInput(attrs={
                'placeholder': 'Leave blank to auto-generate',
                'class': 'form-control'
            }),
            'period_type': forms.Select(attrs={
                'class': 'form-select'
            }),
            'start_date': DatePickerInput(),
            'end_date': DatePickerInput(),
            'enrollment_deadline': DatePickerInput(),
            'minimum_attendance_percentage': PercentageInput(),
            'description': forms.Textarea(attrs={
                'rows': 3,
                'class': 'form-control',
                'placeholder': 'Optional description or notes about this session'
            }),
            'is_special_session': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'late_enrollment_allowed': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'is_current': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'allows_promotion': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
            from core.models import SchoolConfiguration
            config = SchoolConfiguration.get_instance()
            
            if config:
                self.fields['term_number'].help_text = (
                    f'Position within academic year (1-{config.get_period_count()} for regular sessions, '
                    f'1-20 for special sessions). Your school uses {config.get_term_system_display_name()}.'
                )
                
                self.fields['term_name'].help_text = (
                    f'Leave blank for regular sessions (will auto-generate as "{config.get_period_type_name()} 1", '
                    f'"{config.get_period_type_name()} 2", etc.). Provide custom name for special sessions.'
                )
                
                self.fields['period_type'].help_text = (
                    f'Leave blank to use school default ({config.get_term_system_display_name()}). '
                    f'Select manually for special sessions.'
                )
            else:
                self._set_fallback_help_text()
        except Exception as e:
            logger.warning(f"Could not load SchoolConfiguration for form help text: {e}")
            self._set_fallback_help_text()
        
        self.fields['year_name'].help_text = (
            'Format: "YYYY" (e.g., 2025) or "YYYY-YYYY" (e.g., 2024-2025) or "YYYY/YYYY" (e.g., 2024/2025)'
        )
        
        self.fields['term_name'].required = False
        self.fields['period_type'].required = False
        self.fields['enrollment_deadline'].required = False
        self.fields['description'].required = False
    
    def _set_fallback_help_text(self):
        """Set fallback help text when SchoolConfiguration is not available"""
        self.fields['term_number'].help_text = (
            'Position within academic year (1-12 for regular sessions, 1-20 for special sessions)'
        )
        
        self.fields['term_name'].help_text = (
            'Leave blank for regular sessions (auto-generated). '
            'Provide custom name for special sessions.'
        )
        
        self.fields['period_type'].help_text = (
            'Leave blank to auto-set. Select manually for special sessions.'
        )
    
    def clean_year_name(self):
        """Validate year name format"""
        year_name = self.cleaned_data.get('year_name')
        
        if not year_name:
            raise ValidationError('Academic year is required.')
        
        if '/' in year_name or '-' in year_name:
            pattern = r'^(20\d{2})[\/-](20\d{2})$'
            if not re.match(pattern, year_name):
                raise ValidationError(
                    'Year name must be in format "YYYY-YYYY" or "YYYY/YYYY" (e.g., "2024-2025" or "2024/2025")'
                )
            
            parts = year_name.replace('/', '-').split('-')
            if len(parts) == 2:
                year1, year2 = int(parts[0]), int(parts[1])
                if year2 != year1 + 1:
                    raise ValidationError(
                        'For multi-year format, the second year must be exactly one year after the first '
                        '(e.g., "2024-2025" not "2024-2026")'
                    )
        else:
            pattern = r'^20\d{2}$'
            if not re.match(pattern, year_name):
                raise ValidationError(
                    'Year name must be in format "YYYY" (e.g., "2025")'
                )
        
        return year_name
    
    def clean_term_number(self):
        """Validate term number"""
        term_number = self.cleaned_data.get('term_number')
        is_special_session = self.cleaned_data.get('is_special_session', False)
        
        if not term_number:
            raise ValidationError('Period number is required.')
        
        if term_number < 1:
            raise ValidationError('Period number must be at least 1.')
        
        if not is_special_session:
            try:
                from core.models import SchoolConfiguration
                config = SchoolConfiguration.get_instance()
                
                if config:
                    max_periods = config.get_period_count()
                    if term_number > max_periods:
                        raise ValidationError(
                            f'Period number cannot exceed {max_periods} for regular sessions in your '
                            f'{config.get_term_system_display_name()} system. '
                            f'Check "Special Session" if this is outside the regular term structure.'
                        )
            except Exception as e:
                logger.warning(f"Could not validate term_number against SchoolConfiguration: {e}")
                if term_number > 12:
                    raise ValidationError(
                        'Period number cannot exceed 12 for regular sessions. '
                        'Check "Special Session" for programs outside the regular term structure.'
                    )
        else:
            if term_number > 20:
                raise ValidationError('Period number cannot exceed 20, even for special sessions.')
        
        return term_number
    
    def clean_start_date(self):
        """Validate start date using school timezone ⭐"""
        start_date = self.cleaned_data.get('start_date')
        
        if not start_date:
            raise ValidationError('Start date is required.')
        
        from datetime import timedelta
        today = get_school_today()  # ⭐ SCHOOL TIMEZONE
        
        min_past = today - timedelta(days=2*365)
        if start_date < min_past:
            raise ValidationError(
                f"Start date cannot be more than 2 years in the past (before {min_past.strftime('%Y-%m-%d')})."
            )
        
        max_future = today + timedelta(days=2*365)
        if start_date > max_future:
            raise ValidationError(
                f"Start date cannot be more than 2 years in the future (after {max_future.strftime('%Y-%m-%d')})."
            )
        
        return start_date
    
    def clean_end_date(self):
        """Validate end date"""
        end_date = self.cleaned_data.get('end_date')
        
        if not end_date:
            raise ValidationError('End date is required.')
        
        return end_date
    
    def clean_minimum_attendance_percentage(self):
        """Validate attendance percentage"""
        percentage = self.cleaned_data.get('minimum_attendance_percentage')
        
        if percentage is None:
            return Decimal('75.00')
        
        if not (0 <= percentage <= 100):
            raise ValidationError('Attendance percentage must be between 0 and 100.')
        
        return percentage
    
    def clean(self):
        """Cross-field validation using school timezone ⭐"""
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        enrollment_deadline = cleaned_data.get('enrollment_deadline')
        is_special_session = cleaned_data.get('is_special_session', False)
        term_name = cleaned_data.get('term_name')
        period_type = cleaned_data.get('period_type')
        
        if start_date and end_date:
            if start_date >= end_date:
                raise ValidationError({
                    'end_date': 'End date must be after start date.'
                })
            
            duration = (end_date - start_date).days
            if duration < 7:
                raise ValidationError({
                    'end_date': 'Session must be at least 1 week long.'
                })
            
            if duration > 180:
                logger.warning(f"Session duration is {duration} days (over 6 months)")
        
        if enrollment_deadline:
            if start_date and enrollment_deadline < start_date:
                raise ValidationError({
                    'enrollment_deadline': 'Enrollment deadline cannot be before start date.'
                })
            
            if end_date and enrollment_deadline > end_date:
                raise ValidationError({
                    'enrollment_deadline': 'Enrollment deadline cannot be after end date.'
                })
        
        if is_special_session:
            if not term_name:
                raise ValidationError({
                    'term_name': 'Period name is required for special sessions.'
                })
            
            if not period_type:
                raise ValidationError({
                    'period_type': 'Period type is required for special sessions.'
                })
        
        if start_date and end_date:
            year_name = cleaned_data.get('year_name')
            term_number = cleaned_data.get('term_number')
            
            if year_name and term_number:
                existing = AcademicSession.objects.filter(
                    year_name=year_name,
                    term_number=term_number
                )
                
                if self.instance and self.instance.pk:
                    existing = existing.exclude(pk=self.instance.pk)
                
                if existing.exists():
                    raise ValidationError(
                        f'An academic session already exists for {year_name}, Period {term_number}. '
                        f'Please use a different period number or year.'
                    )
        
        return cleaned_data
    
    def save(self, commit=True):
        """Save the form with additional processing"""
        instance = super().save(commit=False)
        
        if instance.pk:
            logger.info(f"Updating academic session: {instance.year_name} - Period {instance.term_number}")
        else:
            logger.info(f"Creating academic session: {instance.year_name} - Period {instance.term_number}")
        
        if commit:
            try:
                instance.save()
                logger.info(f"Academic session saved successfully: {instance.name}")
            except Exception as e:
                logger.error(f"Error saving academic session: {e}", exc_info=True)
                raise
        
        return instance


# =============================================================================
# HOLIDAY FORM
# =============================================================================

class HolidayForm(BootstrapFormMixin, RequiredFieldsMixin, forms.ModelForm):
    """Form for creating/editing holidays"""
    
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
        
        try:
            self.fields['academic_session'].queryset = AcademicSession.objects.filter(
                is_active=True
            ).order_by('-start_date')
        except Exception as e:
            logger.error(f"Error setting session queryset: {e}")
        
        self.fields['end_date'].help_text = 'Leave blank for single-day holidays'
        self.fields['is_recurring'].help_text = 'Check if this holiday repeats annually'
    
    def clean_start_date(self):
        """Validate start date using school timezone ⭐"""
        start_date = self.cleaned_data.get('start_date')
        if start_date:
            from datetime import timedelta
            
            today = get_school_today()  # ⭐ SCHOOL TIMEZONE
            max_future = today + timedelta(days=2*365)
            if start_date > max_future:
                raise ValidationError(
                    "Start date cannot be more than 2 years in the future."
                )
        
        return start_date
    
    def clean(self):
        """Validate date range"""
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
    """Form for creating/editing subjects"""
    
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
    """Form for creating/editing academic levels"""
    
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
        
        if self.instance.pk:
            self.fields['next_level'].queryset = AcademicLevel.objects.exclude(
                pk=self.instance.pk
            )


# =============================================================================
# CLASSROOM FORM
# =============================================================================

class ClassRoomForm(BootstrapFormMixin, RequiredFieldsMixin, forms.ModelForm):
    """Form for creating/editing classrooms"""
    
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
# CLASS FORM
# =============================================================================

class ClassForm(BootstrapFormMixin, RequiredFieldsMixin, forms.ModelForm):
    """Form for creating/editing classes"""
    
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
        
        try:
            self.fields['academic_level'].queryset = AcademicLevel.objects.filter(
                is_active=True
            ).order_by('order')
        except Exception as e:
            logger.error(f"Error setting academic level queryset: {e}")
            self.fields['academic_level'].queryset = AcademicLevel.objects.none()
        
        try:
            self.fields['academic_session'].queryset = AcademicSession.objects.filter(
                is_active=True
            ).order_by('-start_date')
        except Exception as e:
            logger.error(f"Error setting session queryset: {e}")
            self.fields['academic_session'].queryset = AcademicSession.objects.none()
        
        try:
            self.fields['classroom'].queryset = ClassRoom.objects.filter(
                is_active=True
            ).order_by('building', 'room_number')
        except Exception as e:
            logger.error(f"Error setting classroom queryset: {e}")
            self.fields['classroom'].queryset = ClassRoom.objects.none()
        
        # =====================================================================
        # TEACHER QUERYSET - FIXED ⭐
        # =====================================================================
        try:
            from hr.models import Teacher
            
            # ✅ FIXED: Order by staff fields, not user fields
            teacher_queryset = Teacher.objects.filter(
                is_active=True
            ).select_related('staff').order_by(
                'staff__first_name', 
                'staff__last_name'
            )
            
            self.fields['class_teacher'].queryset = teacher_queryset
            self.fields['assistant_teacher'].queryset = teacher_queryset
            
        except ImportError:
            logger.error("Teacher model not found - hr app may not be installed")
            self.fields['class_teacher'].widget = forms.HiddenInput()
            self.fields['class_teacher'].required = False
            self.fields['assistant_teacher'].widget = forms.HiddenInput()
            self.fields['assistant_teacher'].required = False
            
        except Exception as e:
            logger.error(f"Error setting teacher queryset: {e}", exc_info=True)
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
        
        if start_time and end_time:
            if start_time >= end_time:
                raise ValidationError({
                    'end_time': 'End time must be after start time.'
                })
        
        # Validate that class teacher and assistant teacher are different
        class_teacher = cleaned_data.get('class_teacher')
        assistant_teacher = cleaned_data.get('assistant_teacher')
        
        if class_teacher and assistant_teacher:
            if class_teacher == assistant_teacher:
                raise ValidationError({
                    'assistant_teacher': 'Assistant teacher must be different from class teacher.'
                })
        
        return cleaned_data


# =============================================================================
# STUDENT CLASS ENROLLMENT FORMS
# =============================================================================

class BulkEnrollmentStudentSelectionForm(BootstrapFormMixin, forms.Form):
    """Step 1: Filter and select students for bulk enrollment"""
    
    search = forms.CharField(
        label='Search Students',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by name, admission number...',
            'autofocus': True
        })
    )
    
    current_level = forms.ModelChoiceField(
        queryset=AcademicLevel.objects.filter(is_active=True),
        required=False,
        empty_label='All Levels',
        label='Current Academic Level',
        help_text='Filter students by their current level'
    )
    
    enrollment_status = forms.ChoiceField(
        choices=[('', 'All Statuses')] + list(Student.ENROLLMENT_STATUS_CHOICES),
        required=False,
        label='Enrollment Status',
        initial='ACTIVE'
    )
    
    gender = forms.ChoiceField(
        choices=[('', 'All Genders')] + list(Student.GENDER_CHOICES),
        required=False,
        label='Gender'
    )
    
    exclude_already_enrolled = forms.BooleanField(
        initial=True,
        required=False,
        label='Hide already enrolled students',
        help_text='Exclude students already enrolled in the target session',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    show_only_eligible = forms.BooleanField(
        initial=False,
        required=False,
        label='Show only promotion-eligible students',
        help_text='Only show students eligible for promotion',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
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
        label='Sort By'
    )
    
    def __init__(self, *args, academic_session=None, target_class=None, **kwargs):
        self.academic_session = academic_session
        self.target_class = target_class
        
        super().__init__(*args, **kwargs)
        
        if self.academic_session:
            self.fields['exclude_already_enrolled'].help_text = (
                f'Exclude students already enrolled in {self.academic_session.name}'
            )


class BulkEnrollmentConfirmationForm(RequiredFieldsMixin, BootstrapFormMixin, forms.Form):
    """Step 2: Configure enrollment details for selected students"""
    
    academic_session = forms.ModelChoiceField(
        queryset=AcademicSession.objects.none(),
        required=True,
        label='Academic Session',
        empty_label='Select Academic Session',
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Only sessions open for enrollment are shown'
    )
    
    class_instance = forms.ModelChoiceField(
        queryset=Class.objects.filter(is_active=True),
        required=True,
        label='Class'
    )
    
    enrollment_date = forms.DateField(
        widget=DatePickerInput(),
        required=True,
        label='Enrollment Date'
    )
    
    enrollment_type = forms.ChoiceField(
        choices=StudentClassEnrollment.ENROLLMENT_TYPE_CHOICES,
        initial='CONTINUING',
        required=True,
        label='Enrollment Type'
    )
    
    auto_create_invoice = forms.BooleanField(
        initial=True,
        required=False,
        label='Auto-create Fee Invoices',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    selected_student_ids = forms.CharField(
        widget=forms.HiddenInput(),
        required=True
    )
    
    confirm_enrollment = forms.BooleanField(
        required=True,
        label='I confirm this bulk enrollment',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    def __init__(self, *args, **kwargs):
        self.student_count = kwargs.pop('student_count', 0)
        super().__init__(*args, **kwargs)
        
        if self.student_count:
            self.fields['confirm_enrollment'].label = (
                f'I confirm enrollment of {self.student_count} student(s)'
            )
        
        self.fields['academic_session'].queryset = AcademicSession.get_open_for_enrollment()
        
        if not self.data and not self.initial.get('enrollment_date'):
            self.fields['enrollment_date'].initial = get_school_today()  # ⭐ SCHOOL TIMEZONE
    
    def clean_selected_student_ids(self):
        """Parse and validate selected student IDs"""
        ids_str = self.cleaned_data.get('selected_student_ids', '')
        
        if not ids_str:
            raise ValidationError('No students selected for enrollment.')
        
        try:
            ids = [id.strip() for id in ids_str.split(',') if id.strip()]
            if not ids:
                raise ValidationError('No valid student IDs provided.')
            
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
        
        from datetime import timedelta
        today = get_school_today()  # ⭐ SCHOOL TIMEZONE
        
        if enrollment_date > today + timedelta(days=365):
            raise ValidationError('Enrollment date cannot be more than 1 year in the future.')
        
        return enrollment_date
    
    def clean(self):
        """Cross-field validation"""
        cleaned_data = super().clean()
        
        academic_session = cleaned_data.get('academic_session')
        class_instance = cleaned_data.get('class_instance')
        enrollment_date = cleaned_data.get('enrollment_date')
        student_ids = cleaned_data.get('selected_student_ids', [])
        
        if class_instance and academic_session:
            if class_instance.academic_session != academic_session:
                raise ValidationError({
                    'class_instance': 'Selected class does not belong to the selected session.'
                })
        
        if enrollment_date and academic_session:
            if enrollment_date > academic_session.end_date:
                raise ValidationError({
                    'enrollment_date': f'Enrollment date cannot be after session end date ({academic_session.end_date})'
                })
        
        if class_instance and student_ids:
            current_count = class_instance.enrollments.filter(
                completion_status='ONGOING'
            ).count()
            
            if hasattr(class_instance, 'max_capacity') and class_instance.max_capacity:
                available = class_instance.max_capacity - current_count
                if len(student_ids) > available:
                    raise ValidationError({
                        'class_instance': (
                            f'Class has only {available} available spots, '
                            f'but you are trying to enroll {len(student_ids)} students.'
                        )
                    })
        
        if academic_session and student_ids:
            existing_enrollments = StudentClassEnrollment.objects.filter(
                academic_session=academic_session,
                student_id__in=student_ids,
                completion_status='ONGOING'
            ).select_related('student', 'class_instance')
            
            if existing_enrollments.exists():
                duplicates = [
                    f"{e.student.get_full_name()} (in {e.class_instance})"
                    for e in existing_enrollments[:5]
                ]
                
                error_msg = 'Already enrolled:\n' + '\n'.join(duplicates)
                if existing_enrollments.count() > 5:
                    error_msg += f'\n... and {existing_enrollments.count() - 5} more'
                
                raise ValidationError(error_msg)
        
        return cleaned_data


class StudentEnrollmentForm(RequiredFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """Form for enrolling a single student into a class"""
    
    class Meta:
        model = StudentClassEnrollment
        fields = [
            'academic_session',
            'student',
            'class_instance',
            'enrollment_date',
            'enrollment_type',
            # 'roll_number',  # ❌ EXCLUDED - auto-generated by signal
            'auto_create_invoice',
            'enrollment_notes',
        ]
        widgets = {
            'enrollment_date': DatePickerInput(),
            'enrollment_notes': forms.Textarea(attrs={'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set default enrollment date for new enrollments
        if not self.instance.pk:
            self.fields['enrollment_date'].initial = get_school_today()
        
        # Set querysets
        self.fields['academic_session'].queryset = AcademicSession.objects.filter(
            is_active=True
        )
        self.fields['class_instance'].queryset = Class.objects.filter(
            is_active=True
        )
        self.fields['student'].queryset = Student.objects.filter(
            enrollment_status='ACTIVE'
        )
    
    def clean(self):
        """Validate enrollment"""
        cleaned_data = super().clean()
        
        student = cleaned_data.get('student')
        class_instance = cleaned_data.get('class_instance')
        academic_session = cleaned_data.get('academic_session')
        
        # Check for duplicate enrollment
        if student and class_instance and academic_session:
            existing = StudentClassEnrollment.objects.filter(
                student=student,
                class_instance=class_instance,
                academic_session=academic_session
            )
            
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            
            if existing.exists():
                raise ValidationError(
                    f"{student.get_full_name()} is already enrolled in "
                    f"{class_instance.get_display_name()} for {academic_session.name}"
                )
        
        return cleaned_data


class QuickEnrollmentForm(BootstrapFormMixin, forms.Form):
    """Quick enrollment form with minimal fields"""
    
    student = forms.ModelChoiceField(
        queryset=Student.objects.filter(enrollment_status='ACTIVE'),
        required=True,
        label='Student',
        widget=forms.Select(attrs={
            'class': 'form-select select2',
            'data-placeholder': 'Select student...'
        })
    )
    
    enrollment_type = forms.ChoiceField(
        choices=StudentClassEnrollment.ENROLLMENT_TYPE_CHOICES,
        initial='PROMOTED',
        required=True,
        label='Type'
    )
    
    def __init__(self, *args, academic_session=None, class_instance=None, **kwargs):
        self.academic_session = academic_session
        self.class_instance = class_instance
        
        super().__init__(*args, **kwargs)
    
    def save(self):
        """Create enrollment record"""
        enrollment = StudentClassEnrollment.objects.create(
            student=self.cleaned_data['student'],
            academic_session=self.academic_session,
            class_instance=self.class_instance,
            enrollment_type=self.cleaned_data['enrollment_type'],
            enrollment_date=get_school_today(),  # ⭐ SCHOOL TIMEZONE
            is_active=True,
            completion_status='ONGOING'
        )
        
        return enrollment


class BulkEnrollmentForm(BootstrapFormMixin, forms.Form):
    """Form for bulk student enrollment"""
    
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
        
        # Set default date using school timezone ⭐
        if not self.is_bound:
            self.fields['enrollment_date'].initial = get_school_today()  # ⭐ SCHOOL TIMEZONE
        
        try:
            self.fields['class_instance'].queryset = Class.objects.filter(
                is_active=True
            ).select_related('academic_level', 'academic_session')
        except Exception as e:
            logger.error(f"Error setting class queryset: {e}")
        
        try:
            self.fields['students'].queryset = Student.objects.filter(
                enrollment_status='ACTIVE'
            ).order_by('last_name', 'first_name')
        except Exception as e:
            logger.error(f"Error setting student queryset: {e}")


# =============================================================================
# CLASS SUBJECT FORMS
# =============================================================================

class ClassSubjectForm(BootstrapFormMixin, RequiredFieldsMixin, forms.ModelForm):
    """Form for creating or editing individual class subject assignments"""
    
    continuous_assessment_weight = PercentageField(
        label='Continuous Assessment Weight (%)',
        help_text='Percentage weight of continuous assessment',
        required=True,
        initial=40.00
    )
    
    final_exam_weight = PercentageField(
        label='Final Exam Weight (%)',
        help_text='Percentage weight of final examination',
        required=True,
        initial=60.00
    )
    
    class Meta:
        model = ClassSubject
        fields = [
            'class_instance', 
            'subject', 
            'teacher',
            'is_optional', 
            'hours_per_week', 
            'total_hours',
            'continuous_assessment_weight', 
            'final_exam_weight',
            'textbook', 
            'reference_materials', 
            'required_equipment',
            'syllabus', 
            'learning_objectives', 
            'assessment_criteria',
            'is_active',
        ]
        widgets = {
            'hours_per_week': forms.NumberInput(attrs={
                'min': '1', 
                'value': '3',
                'class': 'form-control'
            }),
            'total_hours': forms.NumberInput(attrs={
                'min': '0', 
                'value': '0',
                'class': 'form-control'
            }),
            'textbook': forms.TextInput(attrs={
                'placeholder': 'Enter textbook name',
                'class': 'form-control'
            }),
            'reference_materials': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'List reference materials...',
                'class': 'form-control'
            }),
            'required_equipment': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'List required equipment...',
                'class': 'form-control'
            }),
            'syllabus': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': 'Enter syllabus overview...',
                'class': 'form-control'
            }),
            'learning_objectives': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Enter learning objectives...',
                'class': 'form-control'
            }),
            'assessment_criteria': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Enter assessment criteria...',
                'class': 'form-control'
            }),
            'class_instance': forms.Select(attrs={'class': 'form-select'}),
            'subject': forms.Select(attrs={'class': 'form-select'}),
            'teacher': forms.Select(attrs={'class': 'form-select'}),
            'is_optional': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
            from hr.models import Teacher
            
            self.fields['teacher'].queryset = Teacher.objects.select_related(
                'staff'
            ).filter(
                staff__is_active=True
            ).order_by(
                'staff__first_name',
                'staff__last_name'
            )
            
            self.fields['teacher'].label_from_instance = lambda obj: (
                f"{obj.staff.full_name()} ({obj.staff.staff_id})"
            )
            
        except ImportError:
            logger.error("Teacher model not found - hr app may not be installed")
            self.fields['teacher'].widget = forms.HiddenInput()
            self.fields['teacher'].required = False
        except Exception as e:
            logger.error(f"Error setting teacher queryset: {e}")
            try:
                from hr.models import Teacher
                self.fields['teacher'].queryset = Teacher.objects.none()
            except:
                pass
        
        try:
            self.fields['class_instance'].queryset = Class.objects.filter(
                is_active=True
            ).select_related(
                'academic_level',
                'academic_session'
            ).order_by(
                '-academic_session__start_date',
                'academic_level__order',
                'section'
            )
        except Exception as e:
            logger.error(f"Error setting class queryset: {e}")
        
        try:
            self.fields['subject'].queryset = Subject.objects.filter(
                is_active=True
            ).order_by('subject_type', 'name')
        except Exception as e:
            logger.error(f"Error setting subject queryset: {e}")
        
        self.fields['teacher'].required = False
        self.fields['teacher'].help_text = 'Select teacher for this subject (optional, can be assigned later)'
    
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


class BulkClassSubjectForm(BootstrapFormMixin, RequiredFieldsMixin, forms.Form):
    """Form for assigning multiple subjects to a single class"""
    
    class_instance = forms.ModelChoiceField(
        label='Target Class',
        queryset=Class.objects.none(),
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Select the class to assign subjects to'
    )
    
    subjects = forms.ModelMultipleChoiceField(
        label='Subjects to Assign',
        queryset=Subject.objects.none(),
        required=True,
        widget=forms.SelectMultiple(attrs={
            'class': 'form-select',
            'size': '12'
        }),
        help_text='Select one or more subjects to assign to this class (hold Ctrl/Cmd to select multiple)'
    )
    
    default_hours_per_week = forms.IntegerField(
        label='Hours Per Week',
        initial=3,
        min_value=1,
        max_value=20,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '1',
            'max': '20'
        }),
        help_text='Default weekly teaching hours for all selected subjects'
    )
    
    default_total_hours = forms.IntegerField(
        label='Total Hours (Optional)',
        initial=0,
        min_value=0,
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '0'
        }),
        help_text='Total course hours for the term/year (0 = not set)'
    )
    
    continuous_assessment_weight = PercentageField(
        label='Continuous Assessment Weight (%)',
        initial=Decimal('40.00'),
        help_text='Default CA weight for all subjects (must total 100% with exam weight)'
    )
    
    final_exam_weight = PercentageField(
        label='Final Exam Weight (%)',
        initial=Decimal('60.00'),
        help_text='Default exam weight for all subjects (must total 100% with CA weight)'
    )
    
    mark_all_optional = forms.BooleanField(
        label='Mark all subjects as optional',
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text='Check this if all selected subjects should be marked as optional (not compulsory)'
    )
    
    skip_existing = forms.BooleanField(
        label='Skip existing assignments',
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text='Skip subjects that are already assigned to this class (recommended to avoid duplicates)'
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
            self.fields['class_instance'].queryset = Class.objects.filter(
                is_active=True
            ).select_related(
                'academic_level',
                'academic_session'
            ).order_by(
                '-academic_session__start_date',
                'academic_level__order',
                'section'
            )
            
            self.fields['class_instance'].label_from_instance = lambda obj: (
                f"{obj.academic_level.name}"
                f"{f' {obj.section}' if obj.section else ''}"
                f" - {obj.academic_session.year_name} {obj.academic_session.term_name}"
            )
        except Exception as e:
            logger.error(f"Error setting class queryset: {e}")
            self.fields['class_instance'].queryset = Class.objects.none()
        
        try:
            self.fields['subjects'].queryset = Subject.objects.filter(
                is_active=True
            ).order_by('subject_type', 'name')
            
            self.fields['subjects'].label_from_instance = lambda obj: (
                f"{obj.code} - {obj.name}"
                f"{' ⭐ (Compulsory)' if obj.is_compulsory else ' (Optional)'}"
            )
        except Exception as e:
            logger.error(f"Error setting subjects queryset: {e}")
            self.fields['subjects'].queryset = Subject.objects.none()
    
    def clean(self):
        """Validate form data"""
        cleaned_data = super().clean()
        
        ca_weight = cleaned_data.get('continuous_assessment_weight')
        exam_weight = cleaned_data.get('final_exam_weight')
        
        if ca_weight is not None and exam_weight is not None:
            total = ca_weight + exam_weight
            if total != 100:
                raise ValidationError(
                    f'Assessment weights must total 100%. '
                    f'Current total: {total}% (CA: {ca_weight}%, Exam: {exam_weight}%)'
                )
        
        class_instance = cleaned_data.get('class_instance')
        if class_instance and not class_instance.is_active:
            raise ValidationError({
                'class_instance': 'Cannot assign subjects to an inactive class. '
                                'Please select an active class.'
            })
        
        subjects = cleaned_data.get('subjects')
        if not subjects or subjects.count() == 0:
            raise ValidationError({
                'subjects': 'Please select at least one subject to assign.'
            })
        
        hours_per_week = cleaned_data.get('default_hours_per_week')
        if hours_per_week and hours_per_week < 1:
            raise ValidationError({
                'default_hours_per_week': 'Hours per week must be at least 1.'
            })
        
        return cleaned_data


# =============================================================================
# ACADEMIC PROGRESS FORMS
# =============================================================================

class AcademicProgressForm(BootstrapFormMixin, RequiredFieldsMixin, forms.ModelForm):
    """Form for recording academic progress"""
    
    attendance_percentage = PercentageField(
        label='Attendance Percentage',
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
        
        try:
            self.fields['student'].queryset = Student.objects.filter(
                enrollment_status='ACTIVE'
            ).order_by('last_name', 'first_name')
        except Exception as e:
            logger.error(f"Error setting student queryset: {e}")
        
        if self.instance.pk and self.instance.is_final:
            for field_name in self.fields:
                if field_name not in ['teacher_comments', 'head_teacher_comments']:
                    self.fields[field_name].widget.attrs['readonly'] = True
                    self.fields[field_name].disabled = True


class AcademicProgressQuickForm(BootstrapFormMixin, forms.ModelForm):
    """Quick form for basic progress entry"""
    
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

class CloseSessionForm(BootstrapFormMixin, forms.Form):
    """Form for closing academic sessions"""
    
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
    """Form for promoting students to next level"""
    
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