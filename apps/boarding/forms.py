# boarding/forms.py

"""
Boarding management forms.

All date validations use get_school_today() from core.utils so they respect
the school's configured operational timezone.

REMOVED (dead forms — no view or template instantiates them):
  - DormitoryQuickAddForm   → superseded by DormitoryForm in all modal/page views
  - BoardingApprovalForm    → approval handled directly in views.py without a form;
                              modal renders a plain confirmation template

FIXED:
  - timezone.timedelta → timedelta (from datetime) throughout; bare
    timezone.timedelta is not valid — timezone provides tz utilities, not duration
  - BulkBoardingEnrollmentStudentSelectionForm: removed spurious
    classroom__room_number from current_class order_by
  - BulkBoardingEnrollmentConfirmationForm.clean(): gender incompatibility now
    collects all incompatible student names before raising a single error,
    rather than stopping at the first incompatible student
  - get_school_today() used consistently; no bare timezone.now().date() remains
"""

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from datetime import timedelta
import logging

from utils.forms import (
    BootstrapFormMixin,
    DateRangeFormMixin,
    RequiredFieldsMixin,
    DatePickerInput,
    SearchInput,
    SelectWithDefault,
    PhoneInput,
    validate_phone_number,
)
from core.utils import get_school_today

from .models import Dormitory, BoardingEnrollment
from students.models import Student, Guardian
from academics.models import AcademicSession
from hr.models import Staff

logger = logging.getLogger(__name__)


# =============================================================================
# FILTER FORMS
# =============================================================================

class DormitoryFilterForm(BootstrapFormMixin, forms.Form):
    """Filter form for the dormitory list view."""

    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by name, code, building…'
        })
    )

    dormitory_type = forms.ChoiceField(
        label='Dormitory Type',
        choices=[('', 'All Types')] + list(Dormitory.DORMITORY_TYPE_CHOICES),
        required=False,
        widget=SelectWithDefault(default_label='All Types'),
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

    is_available_for_new_admissions = forms.NullBooleanField(
        label='Available for Admissions',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Available'),
            ('false', 'Not Available'),
        ], attrs={'class': 'form-select'})
    )

    maintenance_status = forms.ChoiceField(
        label='Maintenance Status',
        choices=[('', 'All Statuses')] + list(Dormitory.MAINTENANCE_STATUS_CHOICES),
        required=False,
        widget=SelectWithDefault(default_label='All Statuses'),
    )

    occupancy_level = forms.ChoiceField(
        label='Occupancy Level',
        choices=[
            ('',       'All Levels'),
            ('empty',  'Empty'),
            ('low',    'Low (<70 %)'),
            ('medium', 'Medium (70–90 %)'),
            ('high',   'High (>90 %)'),
        ],
        required=False,
        widget=SelectWithDefault(default_label='All Levels'),
    )

    dormitory_master = forms.ModelChoiceField(
        label='Dormitory Master',
        queryset=None,
        required=False,
        widget=SelectWithDefault(default_label='All Masters'),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            # Only show staff who are already managing at least one dormitory
            self.fields['dormitory_master'].queryset = Staff.objects.filter(
                is_active=True,
                managed_dormitories__isnull=False,
            ).distinct().order_by('first_name', 'last_name')
        except Exception as e:
            logger.error("Error setting dormitory master queryset: %s", e)


class BoardingEnrollmentFilterForm(DateRangeFormMixin, BootstrapFormMixin, forms.Form):
    """Filter form for the boarding enrollment list view."""

    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by student name, roll number…'
        })
    )

    academic_session = forms.ModelChoiceField(
        label='Academic Session',
        queryset=None,
        required=False,
        widget=SelectWithDefault(default_label='All Sessions'),
    )

    boarding_type = forms.ChoiceField(
        label='Boarding Type',
        choices=[('', 'All Types')] + list(BoardingEnrollment.BOARDING_TYPE_CHOICES),
        required=False,
        widget=SelectWithDefault(default_label='All Types'),
    )

    status = forms.ChoiceField(
        label='Status',
        choices=[('', 'All Statuses')] + list(BoardingEnrollment.ENROLLMENT_STATUS_CHOICES),
        required=False,
        widget=SelectWithDefault(default_label='All Statuses'),
    )

    dormitory = forms.ModelChoiceField(
        label='Dormitory',
        queryset=None,
        required=False,
        widget=SelectWithDefault(default_label='All Dormitories'),
    )

    guardian_consent = forms.NullBooleanField(
        label='Guardian Consent',
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true',  'With Consent'),
            ('false', 'Without Consent'),
        ], attrs={'class': 'form-select'})
    )

    enrollment_date_from = forms.DateField(
        label='Enrolled From',
        required=False,
        widget=DatePickerInput(),
    )

    enrollment_date_to = forms.DateField(
        label='Enrolled To',
        required=False,
        widget=DatePickerInput(),
    )

    student_gender = forms.ChoiceField(
        label='Gender',
        choices=[('', 'All'), ('M', 'Male'), ('F', 'Female')],
        required=False,
        widget=SelectWithDefault(default_label='All'),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.fields['academic_session'].queryset = AcademicSession.objects.filter(
                is_active=True,
            ).order_by('-start_date')
        except Exception as e:
            logger.error("Error setting session queryset: %s", e)

        try:
            self.fields['dormitory'].queryset = Dormitory.objects.filter(
                is_active=True,
            ).order_by('dormitory_type', 'name')
        except Exception as e:
            logger.error("Error setting dormitory queryset: %s", e)


# =============================================================================
# DORMITORY FORM
# =============================================================================

class DormitoryForm(forms.ModelForm):
    """Form for creating and editing dormitories."""

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
            'maintenance_status',
            'last_maintenance_date', 'next_maintenance_due',
            'rules_and_regulations', 'emergency_procedures',
            'dormitory_phone', 'dormitory_email', 'notes',
        ]
        widgets = {
            'last_maintenance_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'next_maintenance_due':  forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        try:
            # Staff model has first_name / last_name directly — not via a user relation.
            from schoolara.managers import get_current_db
            db = get_current_db()
            staff_qs = Staff.objects.using(db).filter(
            is_active=True
            ).order_by('first_name', 'last_name')
            self.fields['dormitory_master'].queryset           = staff_qs
            self.fields['assistant_dormitory_master'].queryset = staff_qs

        except Exception as e:
            logger.error("Error setting staff querysets: %s", e)

        self.fields['dormitory_master'].required           = False
        self.fields['assistant_dormitory_master'].required = False

        self.fields['code'].help_text = (
            "Unique short identifier (e.g., DORM-B-001)"
        )
        self.fields['total_capacity'].help_text = (
            "Maximum number of students this dormitory can hold"
        )

        # Style widgets
        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault('class', 'form-check-input')
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault('class', 'form-select')
            elif isinstance(field.widget, forms.Textarea):
                field.widget.attrs.update({'class': 'form-control', 'rows': 3})
            else:
                field.widget.attrs.setdefault('class', 'form-control')

    def clean(self):
        cleaned_data = super().clean()

        dormitory_master = cleaned_data.get('dormitory_master')
        assistant_master = cleaned_data.get('assistant_dormitory_master')

        if dormitory_master and assistant_master and dormitory_master == assistant_master:
            raise ValidationError(
                "The dormitory master and assistant dormitory master cannot be "
                "the same person."
            )

        total_capacity = cleaned_data.get('total_capacity')
        room_count     = cleaned_data.get('room_count')
        beds_per_room  = cleaned_data.get('beds_per_room')

        if room_count and beds_per_room and total_capacity:
            calculated = room_count * beds_per_room
            if total_capacity > calculated * 1.5:
                raise ValidationError(
                    f"Total capacity ({total_capacity}) seems too high compared to "
                    f"calculated capacity ({calculated} = {room_count} rooms × "
                    f"{beds_per_room} beds). Please verify your numbers."
                )

        last_maintenance = cleaned_data.get('last_maintenance_date')
        next_maintenance = cleaned_data.get('next_maintenance_due')

        if last_maintenance and next_maintenance and next_maintenance < last_maintenance:
            raise ValidationError(
                "Next maintenance date cannot be before the last maintenance date."
            )

        return cleaned_data


# =============================================================================
# BOARDING ENROLLMENT FORM
# =============================================================================

class BoardingEnrollmentForm(RequiredFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """
    Form for creating or editing a single boarding enrollment.

    CREATE MODE: Shows student, session, dates, reason, and auto_create_invoice.
                 Hides status and admin_notes (admin-only post-creation fields).

    EDIT MODE:   Locks student, session, all date fields, reason, and
                 auto_create_invoice (changing them after creation creates
                 accounting inconsistencies).
                 Shows status and admin_notes so staff can manage the record.

    boarding_days is overridden as a MultipleChoiceField (checkboxes) so the
    browser submits a list; save() converts it to a JSON-serialisable list for
    the JSONField.
    """

    # Override so the browser sends a proper list rather than a JSON string.
    boarding_days = forms.MultipleChoiceField(
        required=False,
        label='Boarding Days',
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        choices=[
            ('Monday',    'Monday'),
            ('Tuesday',   'Tuesday'),
            ('Wednesday', 'Wednesday'),
            ('Thursday',  'Thursday'),
            ('Friday',    'Friday'),
            ('Saturday',  'Saturday'),
            ('Sunday',    'Sunday'),
        ],
        help_text='Select the days this student will board (Flexible Boarders only)',
    )

    class Meta:
        model  = BoardingEnrollment
        fields = [
            # core
            'student', 'academic_session', 'boarding_type',
            # accommodation
            'dormitory', 'room_number', 'bed_number',
            # dates
            'enrollment_date', 'effective_start_date', 'effective_end_date',
            # schedule
            'boarding_days',
            # consent
            'guardian_consent', 'consent_date', 'consenting_guardian',
            # requirements
            'dietary_requirements', 'medical_requirements', 'special_accommodations',
            # emergency contact
            'emergency_contact_during_boarding', 'emergency_contact_name',
            'emergency_contact_relationship',
            # reason and invoice
            'reason_for_boarding', 'auto_create_invoice',
            # admin fields (shown in edit mode only)
            'status', 'admin_notes',
        ]
        widgets = {
            'student':          forms.Select(attrs={'class': 'form-select'}),
            'academic_session': forms.Select(attrs={'class': 'form-select'}),
            'boarding_type':    forms.Select(attrs={'class': 'form-select'}),
            'dormitory':        forms.Select(attrs={'class': 'form-select'}),
            'room_number': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'e.g., 101',
            }),
            'bed_number': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'e.g., A',
            }),
            'enrollment_date':      DatePickerInput(),
            'effective_start_date': DatePickerInput(),
            'effective_end_date':   DatePickerInput(),
            'consent_date':         DatePickerInput(),
            'consenting_guardian':  forms.Select(attrs={'class': 'form-select'}),
            'guardian_consent': forms.CheckboxInput(
                attrs={'class': 'form-check-input'}
            ),
            'dietary_requirements': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 2,
                'placeholder': 'Any special dietary needs…',
            }),
            'medical_requirements': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 2,
                'placeholder': 'Any medical conditions or requirements…',
            }),
            'special_accommodations': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 2,
                'placeholder': 'Any special accommodations needed…',
            }),
            'emergency_contact_during_boarding': PhoneInput(),
            'emergency_contact_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Full name of emergency contact',
            }),
            'emergency_contact_relationship': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Parent, Guardian, Relative',
            }),
            'reason_for_boarding': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3,
                'placeholder': 'Reason for requesting boarding…',
            }),
            'auto_create_invoice': forms.CheckboxInput(
                attrs={'class': 'form-check-input'}
            ),
            'status':      forms.Select(attrs={'class': 'form-select'}),
            'admin_notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    # -------------------------------------------------------------------------
    # Fields locked in edit mode (changing them after creation creates
    # accounting inconsistencies or violates session integrity).
    # -------------------------------------------------------------------------
    _CREATE_ONLY_FIELDS = [
        'student',
        'academic_session',
        'enrollment_date',
        'effective_start_date',
        'effective_end_date',
        'reason_for_boarding',
        'auto_create_invoice',
    ]

    # Fields that only make sense after the record has been created.
    _EDIT_ONLY_FIELDS = ['status', 'admin_notes']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        is_edit_mode = not self.instance._state.adding

        # -- Remove fields inappropriate for the current mode ----------------
        fields_to_remove = (
            self._EDIT_ONLY_FIELDS if not is_edit_mode
            else self._CREATE_ONLY_FIELDS
        )
        for field_name in fields_to_remove:
            self.fields.pop(field_name, None)

        # -- Populate boarding_days from instance (edit mode) ----------------
        if is_edit_mode and self.instance.boarding_days:
            self.fields['boarding_days'].initial = self.instance.boarding_days

        # -- Set default dates (create mode only) ----------------------------
        if not self.is_bound and not is_edit_mode:
            today = get_school_today()
            self.fields['enrollment_date'].initial      = today
            self.fields['effective_start_date'].initial = today

        # -- Querysets --------------------------------------------------------
        try:
            self.fields['student'].queryset = Student.objects.filter(
                enrollment_status='ACTIVE',
            ).order_by('first_name', 'last_name')
        except Exception as e:
            logger.error("Error setting student queryset: %s", e)

        try:
            self.fields['academic_session'].queryset = AcademicSession.objects.all().order_by(
                '-start_date'
            )
        except Exception as e:
            logger.error("Error setting session queryset: %s", e)

        try:
            self.fields['dormitory'].queryset = Dormitory.objects.filter(
                is_active=True,
                is_available_for_new_admissions=True,
            ).order_by('dormitory_type', 'name')
        except Exception as e:
            logger.error("Error setting dormitory queryset: %s", e)

        # Guardian queryset: scoped to the student's guardians in edit mode
        try:
            if is_edit_mode and self.instance.student_id:
                from students.models import StudentGuardian
                self.fields['consenting_guardian'].queryset = Guardian.objects.filter(
                    id__in=StudentGuardian.objects.filter(
                        student=self.instance.student,
                        is_active=True,
                    ).values_list('guardian_id', flat=True)
                ).order_by('first_name', 'last_name')
            else:
                # Create mode — all active guardians (filtered to selected
                # student's guardians via JavaScript after student selection).
                self.fields['consenting_guardian'].queryset = Guardian.objects.filter(
                    student_relationships__is_active=True,
                ).distinct().order_by('first_name', 'last_name')
        except Exception as e:
            logger.error("Error setting guardian queryset: %s", e)

        # -- Optional fields --------------------------------------------------
        self.fields['consent_date'].required        = False
        self.fields['consenting_guardian'].required = False
        self.fields['room_number'].help_text        = "Optional — can be assigned later"
        self.fields['bed_number'].help_text         = "Optional — can be assigned later"
        self.fields['boarding_type'].help_text = (
            "Full Boarder: Mon–Sun | Weekly Boarder: Mon–Fri | "
            "Flexible: select days below"
        )
        if 'auto_create_invoice' in self.fields:
            self.fields['auto_create_invoice'].help_text = (
                "Automatically create a boarding fee invoice when this "
                "enrollment is approved"
            )

    def clean(self):
        cleaned_data     = super().clean()
        is_edit_mode     = not self.instance._state.adding
        today            = get_school_today()

        dormitory        = cleaned_data.get('dormitory')
        boarding_type    = cleaned_data.get('boarding_type')
        boarding_days    = cleaned_data.get('boarding_days')
        guardian_consent = cleaned_data.get('guardian_consent')
        consent_date     = cleaned_data.get('consent_date')
        consenting_guardian = cleaned_data.get('consenting_guardian')

        # In edit mode, student comes from the instance (field was removed).
        student = (
            cleaned_data.get('student')
            if not is_edit_mode
            else self.instance.student
        )

        # Date fields are only present in create mode.
        start_date       = cleaned_data.get('effective_start_date')
        end_date         = cleaned_data.get('effective_end_date')
        academic_session = cleaned_data.get('academic_session')

        # -- Date range -------------------------------------------------------
        if start_date and end_date and end_date < start_date:
            raise ValidationError({
                'effective_end_date': 'End date cannot be before start date.'
            })

        # -- Start date within session bounds (create mode only) --------------
        if academic_session and start_date:
            if start_date < academic_session.start_date:
                raise ValidationError({
                    'effective_start_date': (
                        f"Start date cannot be before session start "
                        f"({academic_session.start_date})."
                    )
                })
            if start_date > academic_session.end_date:
                raise ValidationError({
                    'effective_start_date': (
                        f"Start date cannot be after session end "
                        f"({academic_session.end_date})."
                    )
                })

        # -- Boarding days required for flexible boarders ---------------------
        if boarding_type == 'FLEXI_BOARDER':
            if not boarding_days:
                raise ValidationError({
                    'boarding_days': (
                        'Boarding days must be selected for flexible boarders.'
                    )
                })

        # -- Dormitory gender compatibility -----------------------------------
        if dormitory and student:
            can_accommodate, message = dormitory.can_accommodate(student)
            if not can_accommodate:
                raise ValidationError({'dormitory': message})

        # -- Guardian consent consistency ------------------------------------
        if guardian_consent:
            if not consent_date:
                raise ValidationError({
                    'consent_date': (
                        'Consent date is required when guardian consent is recorded.'
                    )
                })
            if consent_date and consent_date > today:
                raise ValidationError({
                    'consent_date': 'Consent date cannot be in the future.'
                })
            if not consenting_guardian:
                raise ValidationError({
                    'consenting_guardian': (
                        'Please select which guardian provided consent.'
                    )
                })

        # -- Emergency contact phone format ----------------------------------
        emergency_contact = cleaned_data.get('emergency_contact_during_boarding')
        if emergency_contact:
            try:
                validate_phone_number(emergency_contact)
            except ValidationError as exc:
                raise ValidationError({
                    'emergency_contact_during_boarding': exc.message
                })

        return cleaned_data

    def save(self, commit=True):
        """Convert boarding_days list to JSON-serialisable list for the JSONField."""
        instance = super().save(commit=False)

        if 'boarding_days' in self.cleaned_data:
            days = self.cleaned_data.get('boarding_days')
            instance.boarding_days = list(days) if days else []

        if commit:
            instance.save()
            if hasattr(self, 'save_m2m'):
                self.save_m2m()

        return instance


# =============================================================================
# BOARDING TERMINATION FORM
# =============================================================================

class BoardingTerminationForm(BootstrapFormMixin, forms.Form):
    """Confirmation form for terminating a boarding enrollment."""

    termination_reason = forms.CharField(
        label='Reason for Termination',
        required=True,
        widget=forms.Textarea(attrs={
            'rows': 4,
            'placeholder': 'Please provide a detailed reason for terminating boarding…',
        })
    )

    effective_termination_date = forms.DateField(
        label='Effective Termination Date',
        required=True,
        widget=DatePickerInput(),
        help_text='Date when boarding enrollment ends',
    )

    confirm = forms.BooleanField(
        label='I confirm this termination',
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.fields['effective_termination_date'].initial = get_school_today()

    def clean_effective_termination_date(self):
        termination_date = self.cleaned_data.get('effective_termination_date')
        if not termination_date:
            return termination_date

        today = get_school_today()

        # Allow retroactive terminations up to 90 days back.
        # FIX: was timezone.timedelta — timedelta is from the datetime module.
        if termination_date < today - timedelta(days=90):
            raise ValidationError(
                'Termination date is more than 90 days in the past. '
                'Please contact administration for backdated terminations.'
            )

        return termination_date


# =============================================================================
# BULK ENROLLMENT — STEP 1: STUDENT SELECTION
# =============================================================================

class BulkBoardingEnrollmentStudentSelectionForm(BootstrapFormMixin, forms.Form):
    """Step 1 of bulk boarding enrollment — filter and select students."""

    search = forms.CharField(
        label='Search Students',
        required=False,
        widget=SearchInput(attrs={
            'placeholder': 'Search by name, admission number…',
            'autofocus':   True,
        })
    )

    current_level = forms.ModelChoiceField(
        queryset=None,
        required=False,
        empty_label='All Levels',
        label='Current Academic Level',
        help_text='Filter students by their current level',
        widget=SelectWithDefault(default_label='All Levels'),
    )

    current_class = forms.ModelChoiceField(
        queryset=None,
        required=False,
        empty_label='All Classes',
        label='Current Class',
        help_text='Filter students by their current class',
        widget=SelectWithDefault(default_label='All Classes'),
    )

    enrollment_status = forms.ChoiceField(
        choices=[('', 'All Statuses')] + list(Student.ENROLLMENT_STATUS_CHOICES),
        required=False,
        label='Enrollment Status',
        initial='ACTIVE',
        widget=SelectWithDefault(default_label='All Statuses'),
    )

    gender = forms.ChoiceField(
        choices=[('', 'All Genders')] + list(Student.GENDER_CHOICES),
        required=False,
        label='Gender',
        widget=SelectWithDefault(default_label='All Genders'),
    )

    exclude_already_enrolled = forms.BooleanField(
        initial=True,
        required=False,
        label='Hide already enrolled boarders',
        help_text=(
            'Exclude students already enrolled in boarding for the target session'
        ),
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )

    dormitory_type = forms.ChoiceField(
        choices=[('', 'All Types')] + list(Dormitory.DORMITORY_TYPE_CHOICES),
        required=False,
        label='Dormitory Type',
        help_text='Filter by compatible dormitory type',
        widget=SelectWithDefault(default_label='All Types'),
    )

    sort_by = forms.ChoiceField(
        choices=[
            ('name',             'Name (A–Z)'),
            ('-name',            'Name (Z–A)'),
            ('admission_number', 'Admission Number'),
            ('-admission_date',  'Recently Admitted'),
            ('admission_date',   'Oldest Admission'),
        ],
        required=True,
        initial='name',
        label='Sort By',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    def __init__(self, *args, academic_session=None, target_dormitory=None, **kwargs):
        self.academic_session  = academic_session
        self.target_dormitory  = target_dormitory
        super().__init__(*args, **kwargs)

        try:
            from academics.models import AcademicLevel, Class
            self.fields['current_level'].queryset = AcademicLevel.objects.filter(
                is_active=True,
            ).order_by('order')

            # FIX: removed spurious classroom__room_number from order_by —
            # classes should sort by level then section, not by room number.
            self.fields['current_class'].queryset = Class.objects.filter(
                is_active=True,
            ).select_related('academic_level').order_by(
                'academic_level__order', 'section',
            )
        except Exception as e:
            logger.error("Error setting level / class querysets: %s", e)

        if self.academic_session:
            self.fields['exclude_already_enrolled'].help_text = (
                f"Exclude students already enrolled in boarding for "
                f"{self.academic_session.name}"
            )


# =============================================================================
# BULK ENROLLMENT — STEP 2: CONFIRMATION
# =============================================================================

class BulkBoardingEnrollmentConfirmationForm(RequiredFieldsMixin, BootstrapFormMixin, forms.Form):
    """
    Step 2 of bulk boarding enrollment — configure details and confirm.

    Validation here intentionally overlaps with BulkBoardingEnrollmentService
    pre-flight checks.  The form catches obvious problems before any DB write;
    the service handles race conditions and per-student failures.
    """

    academic_session = forms.ModelChoiceField(
        queryset=None,
        required=True,
        label='Academic Session',
        empty_label='Select Academic Session',
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Only active sessions are shown',
    )

    dormitory = forms.ModelChoiceField(
        queryset=None,
        required=True,
        label='Dormitory',
        empty_label='Select Dormitory',
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Only active dormitories available for new admissions are shown',
    )

    boarding_type = forms.ChoiceField(
        choices=BoardingEnrollment.BOARDING_TYPE_CHOICES,
        initial='FULL_BOARDER',
        required=True,
        label='Boarding Type',
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Full Boarder: Mon–Sun | Weekly Boarder: Mon–Fri | Flexible: select days',
    )

    enrollment_date = forms.DateField(
        widget=DatePickerInput(),
        required=True,
        label='Enrollment Date',
    )

    effective_start_date = forms.DateField(
        widget=DatePickerInput(),
        required=True,
        label='Effective Start Date',
        help_text='Date when boarding actually starts',
    )

    effective_end_date = forms.DateField(
        widget=DatePickerInput(),
        required=False,
        label='Effective End Date',
        help_text='Leave blank to use session end date',
    )

    boarding_days = forms.MultipleChoiceField(
        choices=[
            ('Monday',    'Monday'),
            ('Tuesday',   'Tuesday'),
            ('Wednesday', 'Wednesday'),
            ('Thursday',  'Thursday'),
            ('Friday',    'Friday'),
            ('Saturday',  'Saturday'),
            ('Sunday',    'Sunday'),
        ],
        required=False,
        label='Boarding Days',
        widget=forms.CheckboxSelectMultiple(),
        help_text='Required for Flexible Boarders only',
    )

    auto_create_invoice = forms.BooleanField(
        initial=True,
        required=False,
        label='Auto-create Boarding Fee Invoices',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text='Automatically create boarding fee invoices when approved',
    )

    require_guardian_consent = forms.BooleanField(
        initial=True,
        required=False,
        label='Require Guardian Consent',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text='Mark enrollments as requiring guardian consent for minors',
    )

    reason_for_boarding = forms.CharField(
        required=False,
        label='Reason for Boarding (Optional)',
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'Common reason applied to all selected enrollments…',
        }),
    )

    # Hidden field carrying the comma-separated student PKs from step 1.
    selected_student_ids = forms.CharField(
        widget=forms.HiddenInput(),
        required=True,
    )

    confirm_enrollment = forms.BooleanField(
        required=True,
        label='I confirm this bulk boarding enrollment',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )

    def __init__(self, *args, **kwargs):
        self.student_count = kwargs.pop('student_count', 0)
        super().__init__(*args, **kwargs)

        if self.student_count:
            self.fields['confirm_enrollment'].label = (
                f"I confirm boarding enrollment of {self.student_count} student(s)"
            )

        try:
            self.fields['academic_session'].queryset = AcademicSession.objects.filter(
                is_active=True,
            ).order_by('-start_date')
        except Exception as e:
            logger.error("Error setting session queryset: %s", e)

        try:
            self.fields['dormitory'].queryset = Dormitory.objects.filter(
                is_active=True,
                is_available_for_new_admissions=True,
            ).order_by('dormitory_type', 'name')
        except Exception as e:
            logger.error("Error setting dormitory queryset: %s", e)

        if not self.data and not self.initial.get('enrollment_date'):
            today = get_school_today()
            self.fields['enrollment_date'].initial      = today
            self.fields['effective_start_date'].initial = today

    def clean_selected_student_ids(self):
        ids_str = self.cleaned_data.get('selected_student_ids', '')
        if not ids_str:
            raise ValidationError('No students selected for boarding enrollment.')

        ids = [i.strip() for i in ids_str.split(',') if i.strip()]
        if not ids:
            raise ValidationError('No valid student IDs provided.')

        actual_count = Student.objects.filter(id__in=ids).count()
        if actual_count != len(ids):
            raise ValidationError(
                f"Some students no longer exist. "
                f"Found {actual_count} of {len(ids)}."
            )
        return ids

    def clean_enrollment_date(self):
        enrollment_date = self.cleaned_data.get('enrollment_date')
        if not enrollment_date:
            return enrollment_date

        today = get_school_today()

        # FIX: was timezone.timedelta — timedelta is from the datetime module.
        if enrollment_date < today - timedelta(days=365):
            raise ValidationError(
                'Enrollment date is more than a year in the past. Please verify.'
            )
        if enrollment_date > today + timedelta(days=365):
            raise ValidationError(
                'Enrollment date cannot be more than 1 year in the future.'
            )
        return enrollment_date

    def clean_effective_start_date(self):
        start_date = self.cleaned_data.get('effective_start_date')
        if not start_date:
            return start_date

        today = get_school_today()

        # FIX: was timezone.timedelta — timedelta is from the datetime module.
        if start_date < today - timedelta(days=365):
            raise ValidationError(
                'Effective start date is more than a year in the past. '
                'Please verify.'
            )
        return start_date

    def clean(self):
        cleaned_data     = super().clean()
        academic_session = cleaned_data.get('academic_session')
        dormitory        = cleaned_data.get('dormitory')
        boarding_type    = cleaned_data.get('boarding_type')
        start_date       = cleaned_data.get('effective_start_date')
        end_date         = cleaned_data.get('effective_end_date')
        boarding_days    = cleaned_data.get('boarding_days')
        student_ids      = cleaned_data.get('selected_student_ids', [])

        # -- Boarding days required for flexible boarders ---------------------
        if boarding_type == 'FLEXI_BOARDER' and not boarding_days:
            raise ValidationError({
                'boarding_days': (
                    'Boarding days must be selected for flexible boarders.'
                )
            })

        # -- Date range -------------------------------------------------------
        if start_date and end_date and end_date < start_date:
            raise ValidationError({
                'effective_end_date': 'End date cannot be before start date.'
            })

        # -- Dates within session bounds --------------------------------------
        if academic_session and start_date:
            if start_date < academic_session.start_date:
                raise ValidationError({
                    'effective_start_date': (
                        f"Start date cannot be before session start date "
                        f"({academic_session.start_date})."
                    )
                })
            if start_date > academic_session.end_date:
                raise ValidationError({
                    'effective_start_date': (
                        f"Start date cannot be after session end date "
                        f"({academic_session.end_date})."
                    )
                })

        # -- Dormitory capacity -----------------------------------------------
        if dormitory and student_ids:
            available = dormitory.get_available_capacity()
            if len(student_ids) > available:
                raise ValidationError({
                    'dormitory': (
                        f"Dormitory '{dormitory.name}' has only {available} "
                        f"available bed(s), but {len(student_ids)} student(s) "
                        f"are selected."
                    )
                })

        # -- Dormitory gender compatibility (collect all, raise once) ---------
        # FIX: original raised on the first incompatible student and stopped.
        # Now all incompatible names are collected before raising.
        if dormitory and student_ids and dormitory.dormitory_type != 'MIXED':
            students = Student.objects.filter(id__in=student_ids)
            incompatible = [
                s.get_full_name()
                for s in students
                if not dormitory.can_accommodate_gender(s.gender)
            ]
            if incompatible:
                names = ', '.join(incompatible)
                raise ValidationError({
                    'dormitory': (
                        f"The following students are not compatible with "
                        f"'{dormitory.name}' "
                        f"({dormitory.get_dormitory_type_display()}): {names}."
                    )
                })

        # -- Already enrolled (hard block at form level) ----------------------
        # The service will demote duplicates to warnings during execution,
        # but a clean block here prevents obviously invalid batch submissions.
        if academic_session and student_ids:
            existing = BoardingEnrollment.objects.filter(
                academic_session=academic_session,
                student_id__in=student_ids,
                status__in=('PENDING', 'ACTIVE'),
            ).select_related('student', 'dormitory')

            if existing.exists():
                duplicates = [
                    f"{e.student.get_full_name()} (in {e.dormitory.name})"
                    for e in existing[:5]
                ]
                msg = 'Already enrolled in boarding:\n' + '\n'.join(duplicates)
                if existing.count() > 5:
                    msg += f'\n… and {existing.count() - 5} more'
                raise ValidationError(msg)

        return cleaned_data