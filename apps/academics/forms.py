# academics/forms.py

"""
Academic management forms with timezone support.
All date validations use school timezone for consistency.

HTMX configuration removed — handled in views and templates.

REMOVED (dead forms — never instantiated by any view or modal):
  - BulkEnrollmentForm          → superseded by the two-step wizard
  - QuickEnrollmentForm         → superseded by StudentEnrollmentForm
  - ClassFilterForm             → level_detail.html renders its own raw HTML filter bar
  - ClassSubjectFilterForm      → class_detail.html renders its own raw HTML filter bar
  - StudentClassEnrollmentFilterForm → class_detail.html renders its own raw HTML filter bar
  - AcademicProgressQuickForm   → no view instantiates it; AcademicProgressForm covers all fields
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

# Import base form utilities with timezone support
from utils.forms import (
    BootstrapFormMixin,
    DateRangeFormMixin,
    RequiredFieldsMixin,
    DatePickerInput,
    SearchInput,
    PercentageField,
    PercentageInput,
    validate_future_date,
    validate_past_date,
    validate_date_not_before,
    validate_date_not_after,
)

# Import school timezone utilities
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
# FILTER FORMS
# (Only forms that are actually rendered by a view are kept here.
#  Raw HTML filter bars in level_detail.html and class_detail.html are
#  intentionally NOT backed by a Django form — they post directly to
#  HTMX partial views that read request.GET.)
# =============================================================================

class AcademicSessionFilterForm(BootstrapFormMixin, forms.Form):
    """Filter form for the academic session list view."""

    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by year name, term name…'
        })
    )

    is_current = forms.NullBooleanField(
        label='Current Session',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Current Only'),
            ('false', 'Not Current'),
        ], attrs={'class': 'form-select'})
    )

    is_active = forms.NullBooleanField(
        label='Active Status',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Active'),
            ('false', 'Inactive'),
        ], attrs={'class': 'form-select'})
    )

    is_academically_closed = forms.NullBooleanField(
        label='Academic Closure',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Closed'),
            ('false', 'Open'),
        ], attrs={'class': 'form-select'})
    )

    is_special_session = forms.NullBooleanField(
        label='Session Type',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All Sessions'),
            ('false', 'Regular Only'),
            ('true', 'Special Only'),
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
            'placeholder': 'e.g., 2024 or 2024-2025',
        })
    )


class HolidayFilterForm(DateRangeFormMixin, BootstrapFormMixin, forms.Form):
    """Filter form for the holiday list view."""

    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={'placeholder': 'Search holidays…'})
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
            ('false', 'Open'),
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
        empty_label='All Sessions',
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


class SubjectFilterForm(BootstrapFormMixin, forms.Form):
    """Filter form for the subject list view."""

    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by name, code, abbreviation…'
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
            ('false', 'Inactive'),
        ], attrs={'class': 'form-select'})
    )

    is_compulsory = forms.NullBooleanField(
        label='Compulsory',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Compulsory'),
            ('false', 'Optional'),
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
        empty_label='All Departments',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    academic_level = forms.ModelChoiceField(
        label='Academic Level',
        queryset=None,
        required=False,
        empty_label='All Levels',
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Filter by applicable academic level'
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


class AcademicLevelFilterForm(BootstrapFormMixin, forms.Form):
    """Filter form for the academic level list view."""

    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={'placeholder': 'Search by name, code…'})
    )

    is_active = forms.NullBooleanField(
        label='Active Status',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Active'),
            ('false', 'Inactive'),
        ], attrs={'class': 'form-select'})
    )

    has_sections = forms.NullBooleanField(
        label='Has Sections',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'With Sections'),
            ('false', 'No Sections'),
        ], attrs={'class': 'form-select'})
    )

    is_graduation_level = forms.NullBooleanField(
        label='Graduation Level',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Graduation Level'),
            ('false', 'Not Graduation Level'),
        ], attrs={'class': 'form-select'})
    )


class ClassRoomFilterForm(BootstrapFormMixin, forms.Form):
    """Filter form for the classroom list view."""

    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by name, room number, building…'
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
            'placeholder': 'Building name',
        })
    )

    floor = forms.CharField(
        label='Floor',
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Floor number',
        })
    )

    is_active = forms.NullBooleanField(
        label='Active Status',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Active'),
            ('false', 'Inactive'),
        ], attrs={'class': 'form-select'})
    )

    is_bookable = forms.NullBooleanField(
        label='Bookable',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Bookable'),
            ('false', 'Not Bookable'),
        ], attrs={'class': 'form-select'})
    )

    has_projector = forms.NullBooleanField(
        label='Has Projector',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Yes'),
            ('false', 'No'),
        ], attrs={'class': 'form-select'})
    )

    has_computer = forms.NullBooleanField(
        label='Has Computer',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Yes'),
            ('false', 'No'),
        ], attrs={'class': 'form-select'})
    )

    has_smart_board = forms.NullBooleanField(
        label='Has Smart Board',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Yes'),
            ('false', 'No'),
        ], attrs={'class': 'form-select'})
    )

    min_capacity = forms.IntegerField(
        label='Minimum Capacity',
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Min capacity',
            'min': '0',
        })
    )

    is_accessible = forms.NullBooleanField(
        label='Accessible',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Accessible'),
            ('false', 'Not Accessible'),
        ], attrs={'class': 'form-select'})
    )


class AcademicProgressFilterForm(BootstrapFormMixin, forms.Form):
    """Filter form for the academic progress list view."""

    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={'placeholder': 'Search by student name…'})
    )

    academic_session = forms.ModelChoiceField(
        label='Academic Session',
        queryset=None,
        required=False,
        empty_label='All Sessions',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class_enrollment = forms.ModelChoiceField(
        label='Class',
        queryset=None,
        required=False,
        empty_label='All Classes',
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
            ('false', 'Not Eligible'),
        ], attrs={'class': 'form-select'})
    )

    is_final = forms.NullBooleanField(
        label='Finalized',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Finalized'),
            ('false', 'Not Finalized'),
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
            'max': '100',
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
            'max': '100',
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
            'max': '4',
        })
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.fields['academic_session'].queryset = AcademicSession.objects.all().order_by(
                '-start_date'
            )
        except Exception as e:
            logger.error(f"Error setting session queryset: {e}")

        try:
            self.fields['class_enrollment'].queryset = Class.objects.filter(
                is_active=True
            ).select_related('academic_level', 'academic_session').order_by(
                '-academic_session__start_date',
                'academic_level__order',
            )
        except Exception as e:
            logger.error(f"Error setting class queryset: {e}")


# =============================================================================
# ACADEMIC SESSION FORM
# =============================================================================

class AcademicSessionForm(BootstrapFormMixin, RequiredFieldsMixin, forms.ModelForm):
    """Form for creating / editing academic sessions."""

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
                'class': 'form-control',
            }),
            'term_number': forms.NumberInput(attrs={
                'min': '1', 'max': '20', 'placeholder': '1',
                'class': 'form-control',
            }),
            'term_name': forms.TextInput(attrs={
                'placeholder': 'Leave blank to auto-generate',
                'class': 'form-control',
            }),
            'period_type': forms.Select(attrs={'class': 'form-select'}),
            'start_date': DatePickerInput(),
            'end_date': DatePickerInput(),
            'enrollment_deadline': DatePickerInput(),
            'minimum_attendance_percentage': PercentageInput(),
            'description': forms.Textarea(attrs={
                'rows': 3, 'class': 'form-control',
                'placeholder': 'Optional description or notes about this session',
            }),
            'is_special_session':      forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'late_enrollment_allowed': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_current':              forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active':               forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'allows_promotion':        forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        try:
            from core.models import SchoolConfiguration
            config = SchoolConfiguration.get_instance()
            if config:
                self.fields['term_number'].help_text = (
                    f'Position within academic year (1–{config.get_period_count()} for regular sessions, '
                    f'1–20 for special sessions). Your school uses {config.get_term_system_display_name()}.'
                )
                self.fields['term_name'].help_text = (
                    f'Leave blank for regular sessions (will auto-generate as '
                    f'"{config.get_period_type_name()} 1", etc.). '
                    f'Provide custom name for special sessions.'
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
            'Format: "YYYY" (e.g., 2025) or "YYYY-YYYY" / "YYYY/YYYY" (e.g., 2024-2025)'
        )
        self.fields['term_name'].required = False
        self.fields['period_type'].required = False
        self.fields['enrollment_deadline'].required = False
        self.fields['description'].required = False

    def _set_fallback_help_text(self):
        self.fields['term_number'].help_text = (
            'Position within academic year (1–12 for regular sessions, 1–20 for special sessions)'
        )
        self.fields['term_name'].help_text = (
            'Leave blank for regular sessions (auto-generated). '
            'Provide custom name for special sessions.'
        )
        self.fields['period_type'].help_text = (
            'Leave blank to auto-set. Select manually for special sessions.'
        )

    def clean_year_name(self):
        year_name = self.cleaned_data.get('year_name')
        if not year_name:
            raise ValidationError('Academic year is required.')

        if '/' in year_name or '-' in year_name:
            pattern = r'^(20\d{2})[\/-](20\d{2})$'
            if not re.match(pattern, year_name):
                raise ValidationError(
                    'Year name must be in format "YYYY-YYYY" or "YYYY/YYYY" '
                    '(e.g., "2024-2025" or "2024/2025")'
                )
            parts = year_name.replace('/', '-').split('-')
            if len(parts) == 2:
                year1, year2 = int(parts[0]), int(parts[1])
                if year2 != year1 + 1:
                    raise ValidationError(
                        'For multi-year format, the second year must be exactly one year after '
                        'the first (e.g., "2024-2025" not "2024-2026")'
                    )
        else:
            if not re.match(r'^20\d{2}$', year_name):
                raise ValidationError('Year name must be in format "YYYY" (e.g., "2025")')

        return year_name

    def clean_term_number(self):
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
            except ValidationError:
                raise
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
        start_date = self.cleaned_data.get('start_date')
        if not start_date:
            raise ValidationError('Start date is required.')

        from datetime import timedelta
        today = get_school_today()
        if start_date < today - timedelta(days=2 * 365):
            raise ValidationError(
                f"Start date cannot be more than 2 years in the past "
                f"(before {(today - timedelta(days=2*365)).strftime('%Y-%m-%d')})."
            )
        if start_date > today + timedelta(days=2 * 365):
            raise ValidationError(
                f"Start date cannot be more than 2 years in the future "
                f"(after {(today + timedelta(days=2*365)).strftime('%Y-%m-%d')})."
            )
        return start_date

    def clean_end_date(self):
        end_date = self.cleaned_data.get('end_date')
        if not end_date:
            raise ValidationError('End date is required.')
        return end_date

    def clean_minimum_attendance_percentage(self):
        percentage = self.cleaned_data.get('minimum_attendance_percentage')
        if percentage is None:
            return Decimal('75.00')
        if not (0 <= percentage <= 100):
            raise ValidationError('Attendance percentage must be between 0 and 100.')
        return percentage

    def clean(self):
        cleaned_data = super().clean()
        start_date         = cleaned_data.get('start_date')
        end_date           = cleaned_data.get('end_date')
        enrollment_deadline = cleaned_data.get('enrollment_deadline')
        is_special_session = cleaned_data.get('is_special_session', False)
        term_name          = cleaned_data.get('term_name')
        period_type        = cleaned_data.get('period_type')

        if start_date and end_date:
            if start_date >= end_date:
                raise ValidationError({'end_date': 'End date must be after start date.'})
            duration = (end_date - start_date).days
            if duration < 7:
                raise ValidationError({'end_date': 'Session must be at least 1 week long.'})
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
                raise ValidationError({'term_name': 'Period name is required for special sessions.'})
            if not period_type:
                raise ValidationError({'period_type': 'Period type is required for special sessions.'})

        if start_date and end_date:
            year_name    = cleaned_data.get('year_name')
            term_number  = cleaned_data.get('term_number')
            if year_name and term_number:
                existing = AcademicSession.objects.filter(
                    year_name=year_name, term_number=term_number
                )
                if self.instance and self.instance.pk:
                    existing = existing.exclude(pk=self.instance.pk)
                if existing.exists():
                    raise ValidationError(
                        f'An academic session already exists for {year_name}, '
                        f'Period {term_number}. Please use a different period number or year.'
                    )

        return cleaned_data

    def save(self, commit=True):
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
    """Form for creating / editing holidays."""

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
            'name':        forms.TextInput(attrs={'placeholder': 'Holiday name'}),
            'start_date':  DatePickerInput(),
            'end_date':    DatePickerInput(),
            'color':       forms.TextInput(attrs={
                'type': 'color',
                'class': 'form-control form-control-color',
            }),
            'description': forms.Textarea(attrs={'rows': 3}),
            'notes':       forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.fields['academic_session'].queryset = AcademicSession.objects.filter(
                is_active=True
            ).order_by('-start_date')
        except Exception as e:
            logger.error(f"Error setting session queryset: {e}")

        self.fields['end_date'].help_text   = 'Leave blank for single-day holidays'
        self.fields['is_recurring'].help_text = 'Check if this holiday repeats annually'

    def clean_start_date(self):
        start_date = self.cleaned_data.get('start_date')
        if start_date:
            from datetime import timedelta
            today = get_school_today()
            if start_date > today + timedelta(days=2 * 365):
                raise ValidationError('Start date cannot be more than 2 years in the future.')
        return start_date

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date   = cleaned_data.get('end_date')
        if start_date and end_date and start_date > end_date:
            raise ValidationError({'end_date': 'End date cannot be before start date.'})
        return cleaned_data


# =============================================================================
# SUBJECT FORM
# =============================================================================

class SubjectForm(BootstrapFormMixin, RequiredFieldsMixin, forms.ModelForm):
    """Form for creating / editing subjects."""

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
            'name':         forms.TextInput(attrs={'placeholder': 'Subject name'}),
            'abbreviation': forms.TextInput(attrs={'placeholder': 'e.g., MATH'}),
            'code':         forms.TextInput(attrs={'placeholder': 'e.g., MTH101'}),
            'credit_hours': forms.NumberInput(attrs={'step': '0.5', 'min': '0.5', 'max': '20'}),
            'pass_mark':    forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'max': '100'}),
            'weight_factor': forms.NumberInput(attrs={'step': '0.01', 'min': '0.5', 'max': '3.0'}),
            'description':  forms.Textarea(attrs={'rows': 3}),
            'recommended_textbooks': forms.Textarea(attrs={'rows': 2}),
            'required_materials':    forms.Textarea(attrs={'rows': 2}),
        }


# =============================================================================
# ACADEMIC LEVEL FORM
# =============================================================================

class AcademicLevelForm(BootstrapFormMixin, RequiredFieldsMixin, forms.ModelForm):
    """Form for creating / editing academic levels."""

    class Meta:
        model = AcademicLevel
        fields = [
            'name', 'code', 'order', 'next_level',
            'has_sections', 'is_active', 'is_graduation_level',
            'description',
        ]
        widgets = {
            'name':        forms.TextInput(attrs={'placeholder': 'e.g., Grade 1'}),
            'code':        forms.TextInput(attrs={'placeholder': 'e.g., G1'}),
            'order':       forms.NumberInput(attrs={'min': '1'}),
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
    """Form for creating / editing classrooms."""

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
            'name':                  forms.TextInput(attrs={'placeholder': 'Room name'}),
            'room_number':           forms.TextInput(attrs={'placeholder': 'e.g., A101'}),
            'capacity':              forms.NumberInput(attrs={'min': '1'}),
            'specialized_equipment': forms.Textarea(attrs={'rows': 2}),
            'accessibility_features': forms.Textarea(attrs={'rows': 2}),
        }

    def clean_last_maintenance_date(self):
        date = self.cleaned_data.get('last_maintenance_date')
        if date:
            validate_future_date(date)
        return date

    def clean_safety_inspection_date(self):
        date = self.cleaned_data.get('safety_inspection_date')
        if date:
            validate_future_date(date)
        return date


# =============================================================================
# CLASS FORM
# =============================================================================

class ClassForm(BootstrapFormMixin, RequiredFieldsMixin, forms.ModelForm):
    """Form for creating / editing classes. Used by class_create_modal and class_edit_modal."""

    start_time = forms.TimeField(
        label='Start Time',
        required=False,
        widget=forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'})
    )

    end_time = forms.TimeField(
        label='End Time',
        required=False,
        widget=forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'})
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
            'section':      forms.TextInput(attrs={'placeholder': 'e.g., A, B, C'}),
            'max_students': forms.NumberInput(attrs={'min': '1', 'value': '30'}),
            'class_motto':  forms.TextInput(attrs={'placeholder': 'Class motto'}),
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

        try:
            from hr.models import Teacher
            teacher_qs = Teacher.objects.filter(
                is_active=True
            ).select_related('staff').order_by('staff__first_name', 'staff__last_name')
            self.fields['class_teacher'].queryset     = teacher_qs
            self.fields['assistant_teacher'].queryset = teacher_qs
        except ImportError:
            logger.error("Teacher model not found — hr app may not be installed")
            self.fields['class_teacher'].widget     = forms.HiddenInput()
            self.fields['class_teacher'].required   = False
            self.fields['assistant_teacher'].widget  = forms.HiddenInput()
            self.fields['assistant_teacher'].required = False
        except Exception as e:
            logger.error(f"Error setting teacher queryset: {e}", exc_info=True)
            try:
                from hr.models import Teacher
                self.fields['class_teacher'].queryset     = Teacher.objects.none()
                self.fields['assistant_teacher'].queryset = Teacher.objects.none()
            except Exception:
                pass

    def clean(self):
        cleaned_data   = super().clean()
        start_time     = cleaned_data.get('start_time')
        end_time       = cleaned_data.get('end_time')
        class_teacher  = cleaned_data.get('class_teacher')
        asst_teacher   = cleaned_data.get('assistant_teacher')

        if start_time and end_time and start_time >= end_time:
            raise ValidationError({'end_time': 'End time must be after start time.'})

        if class_teacher and asst_teacher and class_teacher == asst_teacher:
            raise ValidationError({
                'assistant_teacher': 'Assistant teacher must be different from class teacher.'
            })

        return cleaned_data


# =============================================================================
# BULK ENROLLMENT FORMS  (two-step wizard)
# =============================================================================

class BulkEnrollmentStudentSelectionForm(BootstrapFormMixin, forms.Form):
    """Step 1 — filter and select students for bulk enrollment."""

    search = forms.CharField(
        label='Search Students',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by name, admission number…',
            'autofocus': True,
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
            ('name',           'Name (A–Z)'),
            ('-name',          'Name (Z–A)'),
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
        self.target_class     = target_class
        super().__init__(*args, **kwargs)
        if self.academic_session:
            self.fields['exclude_already_enrolled'].help_text = (
                f'Exclude students already enrolled in {self.academic_session.name}'
            )

    def get_filtered_queryset(self):
        from students.models import Student
        from django.db.models import Q

        qs = Student.objects.select_related(
            'current_academic_level', 'admission_academic_level'
        )

        status = self.cleaned_data.get('enrollment_status')
        qs = qs.filter(enrollment_status=status) if status else qs.filter(enrollment_status='ACTIVE')

        query = self.cleaned_data.get('search', '').strip()
        if query:
            qs = qs.filter(
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query) |
                Q(admission_number__icontains=query)
            )

        level = self.cleaned_data.get('current_level')
        if level:
            qs = qs.filter(current_academic_level=level)

        gender = self.cleaned_data.get('gender')
        if gender:
            qs = qs.filter(gender=gender)

        if self.cleaned_data.get('exclude_already_enrolled') and self.academic_session:
            enrolled_ids = StudentClassEnrollment.objects.filter(
                academic_session=self.academic_session,
                completion_status='ONGOING'
            ).values_list('student_id', flat=True)
            qs = qs.exclude(id__in=enrolled_ids)

        if self.cleaned_data.get('show_only_eligible'):
            from academics.models import AcademicProgress
            eligible_ids = AcademicProgress.objects.filter(
                is_eligible_for_promotion=True
            ).values_list('student_id', flat=True)
            qs = qs.filter(id__in=eligible_ids)

        sort_map = {
            'name':            ('first_name', 'last_name'),
            '-name':           ('-first_name', '-last_name'),
            'admission_number': ('admission_number',),
            '-admission_date': ('-admission_date',),
            'admission_date':  ('admission_date',),
        }
        return qs.order_by(*sort_map.get(self.cleaned_data.get('sort_by', 'name'), ('first_name', 'last_name')))


class BulkEnrollmentConfirmationForm(RequiredFieldsMixin, BootstrapFormMixin, forms.Form):
    """Step 2 — configure enrollment details for selected students."""

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
            self.fields['enrollment_date'].initial = get_school_today()

    def clean_selected_student_ids(self):
        ids_str = self.cleaned_data.get('selected_student_ids', '')
        if not ids_str:
            raise ValidationError('No students selected for enrollment.')

        try:
            ids = [i.strip() for i in ids_str.split(',') if i.strip()]
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
        enrollment_date = self.cleaned_data.get('enrollment_date')
        if not enrollment_date:
            return enrollment_date

        from datetime import timedelta
        today = get_school_today()
        if enrollment_date > today + timedelta(days=365):
            raise ValidationError('Enrollment date cannot be more than 1 year in the future.')
        return enrollment_date

    def clean(self):
        cleaned_data     = super().clean()
        academic_session = cleaned_data.get('academic_session')
        class_instance   = cleaned_data.get('class_instance')
        enrollment_date  = cleaned_data.get('enrollment_date')
        student_ids      = cleaned_data.get('selected_student_ids', [])

        if class_instance and academic_session:
            if class_instance.academic_session != academic_session:
                raise ValidationError({
                    'class_instance': 'Selected class does not belong to the selected session.'
                })

        if enrollment_date and academic_session:
            if enrollment_date > academic_session.end_date:
                raise ValidationError({
                    'enrollment_date': (
                        f'Enrollment date cannot be after session end date '
                        f'({academic_session.end_date})'
                    )
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
            existing = StudentClassEnrollment.objects.filter(
                academic_session=academic_session,
                student_id__in=student_ids,
                completion_status='ONGOING'
            ).select_related('student', 'class_instance')

            if existing.exists():
                duplicates = [
                    f"{e.student.get_full_name()} (in {e.class_instance})"
                    for e in existing[:5]
                ]
                error_msg = 'Already enrolled:\n' + '\n'.join(duplicates)
                if existing.count() > 5:
                    error_msg += f'\n… and {existing.count() - 5} more'
                raise ValidationError(error_msg)

        return cleaned_data


# =============================================================================
# SINGLE STUDENT ENROLLMENT FORM
# =============================================================================

class StudentEnrollmentForm(RequiredFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """Form for enrolling a single student into a class. Used by enrollment_create_modal."""

    class Meta:
        model = StudentClassEnrollment
        fields = [
            'academic_session',
            'student',
            'class_instance',
            'enrollment_date',
            'enrollment_type',
            'auto_create_invoice',
            'enrollment_notes',
        ]
        widgets = {
            'enrollment_date':  DatePickerInput(),
            'enrollment_notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not self.instance.pk:
            self.fields['enrollment_date'].initial = get_school_today()

        self.fields['academic_session'].queryset = AcademicSession.objects.filter(
            is_active=True
        )
        self.fields['class_instance'].queryset = Class.objects.filter(is_active=True)
        self.fields['student'].queryset = Student.objects.filter(enrollment_status='ACTIVE')

    def clean(self):
        cleaned_data     = super().clean()
        student          = cleaned_data.get('student')
        class_instance   = cleaned_data.get('class_instance')
        academic_session = cleaned_data.get('academic_session')

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


# =============================================================================
# CLASS SUBJECT FORM
# =============================================================================

class ClassSubjectForm(BootstrapFormMixin, RequiredFieldsMixin, forms.ModelForm):
    """Form for creating / editing class subject assignments.
    Used by class_subject_create_modal and class_subject_edit_modal."""

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
                'min': '1', 'value': '3', 'class': 'form-control',
            }),
            'total_hours': forms.NumberInput(attrs={
                'min': '0', 'value': '0', 'class': 'form-control',
            }),
            'textbook': forms.TextInput(attrs={
                'placeholder': 'Enter textbook name', 'class': 'form-control',
            }),
            'reference_materials': forms.Textarea(attrs={
                'rows': 3, 'placeholder': 'List reference materials…', 'class': 'form-control',
            }),
            'required_equipment': forms.Textarea(attrs={
                'rows': 3, 'placeholder': 'List required equipment…', 'class': 'form-control',
            }),
            'syllabus': forms.Textarea(attrs={
                'rows': 4, 'placeholder': 'Enter syllabus overview…', 'class': 'form-control',
            }),
            'learning_objectives': forms.Textarea(attrs={
                'rows': 3, 'placeholder': 'Enter learning objectives…', 'class': 'form-control',
            }),
            'assessment_criteria': forms.Textarea(attrs={
                'rows': 3, 'placeholder': 'Enter assessment criteria…', 'class': 'form-control',
            }),
            'class_instance': forms.Select(attrs={'class': 'form-select'}),
            'subject':        forms.Select(attrs={'class': 'form-select'}),
            'teacher':        forms.Select(attrs={'class': 'form-select'}),
            'is_optional':    forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active':      forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # class_instance is injected by the view after save(commit=False)
        self.fields['class_instance'].required = False

        # total_hours has a model default of 0; make it optional in the form
        self.fields['total_hours'].required = False
        self.fields['total_hours'].initial  = 0

        self.fields['teacher'].required  = False
        self.fields['teacher'].help_text = (
            'Select teacher for this subject (optional, can be assigned later)'
        )

        try:
            from hr.models import Teacher
            self.fields['teacher'].queryset = Teacher.objects.select_related(
                'staff'
            ).filter(staff__is_active=True).order_by('staff__first_name', 'staff__last_name')
            self.fields['teacher'].label_from_instance = lambda obj: (
                f"{obj.staff.full_name()} ({obj.staff.staff_id})"
            )
        except ImportError:
            logger.error("Teacher model not found — hr app may not be installed")
            self.fields['teacher'].widget = forms.HiddenInput()
        except Exception as e:
            logger.error(f"Error setting teacher queryset: {e}")
            try:
                from hr.models import Teacher
                self.fields['teacher'].queryset = Teacher.objects.none()
            except Exception:
                pass

        try:
            self.fields['class_instance'].queryset = Class.objects.filter(
                is_active=True
            ).select_related('academic_level', 'academic_session').order_by(
                '-academic_session__start_date', 'academic_level__order', 'section'
            )
        except Exception as e:
            logger.error(f"Error setting class queryset: {e}")

        try:
            self.fields['subject'].queryset = Subject.objects.filter(
                is_active=True
            ).order_by('subject_type', 'name')
        except Exception as e:
            logger.error(f"Error setting subject queryset: {e}")

    def clean(self):
        cleaned_data = super().clean()
        ca_weight    = cleaned_data.get('continuous_assessment_weight')
        exam_weight  = cleaned_data.get('final_exam_weight')

        if ca_weight is not None and exam_weight is not None:
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
    """Form for recording / editing academic progress."""

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
                'step': '0.01', 'min': '0', 'max': '4', 'placeholder': '0.00',
            }),
            'percentage': forms.NumberInput(attrs={
                'step': '0.01', 'min': '0', 'max': '100', 'placeholder': '0.00',
            }),
            'total_school_days': forms.NumberInput(attrs={'min': '0'}),
            'days_attended':     forms.NumberInput(attrs={'min': '0'}),
            'total_subjects':    forms.NumberInput(attrs={'min': '0'}),
            'subjects_passed':   forms.NumberInput(attrs={'min': '0'}),
            'subjects_failed':   forms.NumberInput(attrs={'min': '0'}),
            'teacher_comments':      forms.Textarea(attrs={'rows': 4}),
            'head_teacher_comments': forms.Textarea(attrs={'rows': 4}),
            'recommendations':       forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.fields['student'].queryset = Student.objects.filter(
                enrollment_status='ACTIVE'
            ).order_by('last_name', 'first_name')
        except Exception as e:
            logger.error(f"Error setting student queryset: {e}")

        # Lock most fields once the record is finalised
        if self.instance.pk and self.instance.is_final:
            for field_name in self.fields:
                if field_name not in ('teacher_comments', 'head_teacher_comments'):
                    self.fields[field_name].widget.attrs['readonly'] = True
                    self.fields[field_name].disabled = True


# =============================================================================
# BULK OPERATIONS FORMS
# =============================================================================

class CloseSessionForm(BootstrapFormMixin, forms.Form):
    """Confirmation form for closing an academic session."""

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
            'placeholder': 'Optional: Reason for closing this session',
        })
    )


class PromoteStudentsForm(BootstrapFormMixin, forms.Form):
    """Form for promoting students to the next academic level."""

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
            level_qs = AcademicLevel.objects.filter(is_active=True).order_by('order')
            self.fields['from_level'].queryset = level_qs
            self.fields['to_level'].queryset   = level_qs
        except Exception as e:
            logger.error(f"Error setting level queryset: {e}")

        try:
            self.fields['academic_session'].queryset = AcademicSession.objects.filter(
                is_active=True
            ).order_by('-start_date')
        except Exception as e:
            logger.error(f"Error setting session queryset: {e}")