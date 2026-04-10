"""
exams/forms.py
==============
Forms for the Examinations app.

Layout
------
  1. Imports
  2. ExamCategory forms
  3. GradingSystem → GradingRange forms + inline formset
  4. ClassGradingSystem forms
  5. Examination forms
  6. StudentExamResult forms
  7. Action / workflow forms (lock, unlock, publish)
  8. Filter forms
  9. Filter utility helpers
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.db.models import Q

from utils.forms import (
    BootstrapFormMixin,
    DateRangeFormMixin,
    RequiredFieldsMixin,
    DatePickerInput,
    SearchInput,
    SelectWithDefault,
)

from academics.models import AcademicLevel, AcademicSession, Class, ClassRoom, Subject
from hr.models import Staff
from students.models import Student

from .models import (
    ClassGradingSystem,
    ExamCategory,
    Examination,
    GradingRange,
    GradingSystem,
    StudentExamResult,
)

logger = logging.getLogger(__name__)


# =============================================================================
# EXAM CATEGORY FORMS
# =============================================================================

class ExamCategoryForm(RequiredFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """Create / edit an exam category."""

    class Meta:
        model  = ExamCategory
        fields = [
            'name', 'abbreviation', 'code', 'description',
            'category_type', 'applicable_levels', 'applicable_subject_types',
            'curriculum_compatibility', 'frequency', 'weight_percentage',
            'required_payment_percentage', 'consider_all_outstanding_balances',
            'allows_retakes', 'max_retakes',
            'includes_in_report_cards', 'public_results', 'results_publication_days',
            'is_active', 'effective_date', 'valid_sessions',
        ]
        widgets = {
            'name':                       forms.TextInput(attrs={'placeholder': 'e.g., Mid-Term Examination'}),
            'abbreviation':               forms.TextInput(attrs={'placeholder': 'e.g., MTE'}),
            'code':                       forms.TextInput(attrs={'placeholder': 'e.g., EXAM-MID'}),
            'description':                forms.Textarea(attrs={'rows': 3}),
            'category_type':              forms.Select(attrs={'class': 'form-select'}),
            'applicable_levels':          forms.SelectMultiple(attrs={'class': 'form-select', 'size': '6'}),
            'curriculum_compatibility':   forms.Select(attrs={'class': 'form-select'}),
            'frequency':                  forms.Select(attrs={'class': 'form-select'}),
            'weight_percentage':          forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'max': '100'}),
            'required_payment_percentage':forms.NumberInput(attrs={'min': '0', 'max': '100'}),
            'max_retakes':                forms.NumberInput(attrs={'min': '0', 'max': '10'}),
            'results_publication_days':   forms.NumberInput(attrs={'min': '0'}),
            'effective_date':             DatePickerInput(),
            'valid_sessions':             forms.SelectMultiple(attrs={'class': 'form-select', 'size': '4'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['applicable_levels'].queryset = AcademicLevel.objects.filter(
            is_active=True
        ).order_by('order')

        self.fields['valid_sessions'].queryset = AcademicSession.objects.filter(
            is_active=True
        ).order_by('-start_date')

        self.fields['weight_percentage'].help_text = (
            "Percentage contribution to overall grade (0–100)."
        )
        self.fields['required_payment_percentage'].help_text = (
            "Minimum percentage of fees paid before a student may sit this exam (0–100)."
        )

        if not self.instance.pk:
            from core.utils import get_school_today
            self.fields['effective_date'].initial = get_school_today()

    def clean(self):
        cleaned_data = super().clean()

        if cleaned_data.get('allows_retakes') and not cleaned_data.get('max_retakes'):
            self.add_error('max_retakes', 'Specify the maximum retakes allowed.')

        if not cleaned_data.get('allows_retakes'):
            cleaned_data['max_retakes'] = 0

        return cleaned_data


class ExamCategoryFilterForm(BootstrapFormMixin, forms.Form):
    """Filter / search form for the exam-category list view."""

    q = forms.CharField(
        label='Search', required=False,
        widget=SearchInput(attrs={'placeholder': 'Search by name or code…'}),
    )
    category_type = forms.ChoiceField(
        label='Category Type', required=False,
        choices=[('', 'All Types')] + list(ExamCategory.CATEGORY_TYPES),
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    frequency = forms.ChoiceField(
        label='Frequency', required=False,
        choices=[('', 'All Frequencies')] + list(ExamCategory.FREQUENCY_CHOICES),
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    is_active = forms.ChoiceField(
        label='Status', required=False,
        choices=[('', 'All'), ('true', 'Active'), ('false', 'Inactive')],
        widget=forms.Select(attrs={'class': 'form-select'}),
    )


# =============================================================================
# GRADING SYSTEM FORMS
# =============================================================================

class GradingSystemForm(RequiredFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """Create / edit a grading system."""

    class Meta:
        model  = GradingSystem
        fields = [
            'name', 'code', 'description',
            'grading_type', 'scale_type',
            'minimum_score', 'maximum_score', 'pass_mark',
            'uses_letter_grades', 'uses_numerical_scores', 'uses_aggregates',
            'uses_color_codes', 'uses_gpa',
            'minimum_subjects_required', 'maximum_subjects_considered',
            'subject_selection_method', 'mandatory_subjects', 'optional_subjects',
            'uses_subject_weighting', 'aggregate_calculation_method',
            'maximum_failures_allowed',
            'requires_mathematics', 'requires_english', 'requires_science',
            'include_positions', 'calculate_average', 'calculate_totals',
            'round_to_nearest', 'display_format',
            'applicable_levels', 'applicable_subjects',
            'curriculum_compatibility',
            'subject_type_specific', 'applicable_subject_types',
            'is_active', 'is_default', 'effective_date', 'expiry_date',
        ]
        widgets = {
            'name':                        forms.TextInput(attrs={'placeholder': 'e.g., Cambridge IGCSE Grading'}),
            'code':                        forms.TextInput(attrs={'placeholder': 'e.g., IGCSE-GRADE'}),
            'description':                 forms.Textarea(attrs={'rows': 3}),
            'grading_type':                forms.Select(attrs={'class': 'form-select'}),
            'scale_type':                  forms.Select(attrs={'class': 'form-select'}),
            'minimum_score':               forms.NumberInput(attrs={'step': '0.01'}),
            'maximum_score':               forms.NumberInput(attrs={'step': '0.01'}),
            'pass_mark':                   forms.NumberInput(attrs={'step': '0.01'}),
            'minimum_subjects_required':   forms.NumberInput(attrs={'min': '1'}),
            'maximum_subjects_considered': forms.NumberInput(attrs={'min': '1'}),
            'subject_selection_method':    forms.Select(attrs={'class': 'form-select'}),
            'mandatory_subjects':          forms.SelectMultiple(attrs={'class': 'form-select', 'size': '6'}),
            'optional_subjects':           forms.SelectMultiple(attrs={'class': 'form-select', 'size': '6'}),
            'aggregate_calculation_method':forms.Select(attrs={'class': 'form-select'}),
            'maximum_failures_allowed':    forms.NumberInput(attrs={'min': '0'}),
            'round_to_nearest':            forms.NumberInput(attrs={'step': '0.01'}),
            'display_format':              forms.TextInput(attrs={'placeholder': '{grade} ({score})'}),
            'applicable_levels':           forms.SelectMultiple(attrs={'class': 'form-select', 'size': '6'}),
            'applicable_subjects':         forms.SelectMultiple(attrs={'class': 'form-select', 'size': '6'}),
            'curriculum_compatibility':    forms.Select(attrs={'class': 'form-select'}),
            'effective_date':              DatePickerInput(),
            'expiry_date':                 DatePickerInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        active_subjects = Subject.objects.filter(is_active=True).order_by('name')

        self.fields['applicable_levels'].queryset = AcademicLevel.objects.filter(
            is_active=True
        ).order_by('order')

        for field_name in ('applicable_subjects', 'mandatory_subjects', 'optional_subjects'):
            self.fields[field_name].queryset = active_subjects

        self.fields['maximum_subjects_considered'].required = False
        self.fields['maximum_failures_allowed'].required    = False
        self.fields['expiry_date'].required                 = False

        if not self.instance.pk:
            from core.utils import get_school_today
            self.fields['effective_date'].initial = get_school_today()

    def clean(self):
        cleaned_data  = super().clean()
        minimum_score = cleaned_data.get('minimum_score')
        maximum_score = cleaned_data.get('maximum_score')
        pass_mark     = cleaned_data.get('pass_mark')
        effective_date= cleaned_data.get('effective_date')
        expiry_date   = cleaned_data.get('expiry_date')

        if minimum_score is not None and maximum_score is not None:
            if minimum_score >= maximum_score:
                self.add_error('maximum_score', 'Maximum score must be greater than minimum score.')

        if pass_mark is not None and minimum_score is not None and maximum_score is not None:
            if not (minimum_score <= pass_mark <= maximum_score):
                self.add_error('pass_mark', 'Pass mark must be between minimum and maximum scores.')

        if effective_date and expiry_date and expiry_date <= effective_date:
            self.add_error('expiry_date', 'Expiry date must be after effective date.')

        return cleaned_data


# =============================================================================
# GRADING RANGE FORM + INLINE FORMSET
# =============================================================================

class GradingRangeForm(BootstrapFormMixin, forms.ModelForm):
    """
    Form for a single grading range row.

    Note: ``grading_system`` is intentionally excluded — it is supplied by the
    inline formset's parent relationship.
    """

    class Meta:
        model  = GradingRange
        fields = [
            'grade', 'grade_name',
            'min_score', 'max_score',
            'aggregate', 'gpa_points', 'quality_points',
            'color_code', 'text_color',
            'comments', 'performance_level',
            'is_passing_grade', 'display_order',
        ]
        widgets = {
            'grade':             forms.TextInput(attrs={
                'class': 'form-control form-control-sm',
                'placeholder': 'e.g., A, B+, D1',
            }),
            'grade_name':        forms.TextInput(attrs={
                'class': 'form-control form-control-sm',
                'placeholder': 'e.g., Excellent',
            }),
            'min_score':         forms.NumberInput(attrs={
                'class': 'form-control form-control-sm', 'step': '0.01',
            }),
            'max_score':         forms.NumberInput(attrs={
                'class': 'form-control form-control-sm', 'step': '0.01',
            }),
            'aggregate':         forms.TextInput(attrs={
                'class': 'form-control form-control-sm',
                'placeholder': 'e.g., D1, C6',
            }),
            'gpa_points':        forms.NumberInput(attrs={
                'class': 'form-control form-control-sm', 'step': '0.01',
            }),
            'quality_points':    forms.NumberInput(attrs={
                'class': 'form-control form-control-sm', 'step': '0.01',
            }),
            'color_code':        forms.TextInput(attrs={
                'type': 'color',
                'class': 'form-control form-control-color form-control-sm',
            }),
            'text_color':        forms.TextInput(attrs={
                'type': 'color',
                'class': 'form-control form-control-color form-control-sm',
            }),
            'comments':          forms.Textarea(attrs={
                'class': 'form-control form-control-sm', 'rows': 2,
            }),
            'performance_level': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'display_order':     forms.NumberInput(attrs={
                'class': 'form-control form-control-sm', 'min': '0',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # These sub-fields are optional / auto-derived
        for f in ('grade_name', 'aggregate', 'gpa_points', 'quality_points',
                  'color_code', 'text_color', 'comments', 'performance_level',
                  'display_order'):
            self.fields[f].required = False

    def clean(self):
        cleaned_data = super().clean()
        min_score    = cleaned_data.get('min_score')
        max_score    = cleaned_data.get('max_score')

        if min_score is not None and max_score is not None:
            if min_score >= max_score:
                self.add_error(
                    'max_score',
                    'Maximum score must be greater than minimum score.',
                )

        return cleaned_data


# ---------------------------------------------------------------------------
# Custom base formset — keeps cross-form validation separate from the factory
# ---------------------------------------------------------------------------

class _GradingRangeBaseFormSet(BaseInlineFormSet):
    """
    Validates the complete set of grade ranges for a GradingSystem.

    Cross-form rules:
      1. No two ranges may overlap.
      2. Ranges must start at ``GradingSystem.minimum_score``.
      3. Ranges must reach ``GradingSystem.maximum_score``.
      4. No score gaps are allowed between consecutive ranges.
      5. Grade labels must be unique within the set.
    """

    def clean(self):
        super().clean()

        # Skip if individual forms already have errors
        if any(self.errors):
            return

        live_forms = [
            f for f in self.forms
            if f.cleaned_data and not f.cleaned_data.get('DELETE', False)
        ]

        if not live_forms:
            raise ValidationError('At least one grade range is required.')

        # Collect ranges that have both scores present
        ranges: list[dict] = []
        for form in live_forms:
            min_s = form.cleaned_data.get('min_score')
            max_s = form.cleaned_data.get('max_score')
            grade = form.cleaned_data.get('grade', '')
            if min_s is not None and max_s is not None:
                ranges.append({'min': min_s, 'max': max_s, 'grade': grade})

        if not ranges:
            raise ValidationError(
                'At least one complete grade range (min score and max score) is required.'
            )

        ranges.sort(key=lambda r: r['min'])

        # ── 1. Duplicate grade labels ────────────────────────────────────────
        grades = [r['grade'] for r in ranges if r['grade']]
        duplicates = [g for g in set(grades) if grades.count(g) > 1]
        if duplicates:
            raise ValidationError(
                f"Duplicate grade label(s): {', '.join(duplicates)}. "
                "Each grade must be unique within a grading system."
            )

        # ── 2. Overlapping ranges ────────────────────────────────────────────
        for i in range(len(ranges) - 1):
            curr = ranges[i]
            nxt  = ranges[i + 1]
            if curr['max'] >= nxt['min']:
                raise ValidationError(
                    f"Ranges overlap: '{curr['grade']}' ({curr['min']}–{curr['max']}) "
                    f"and '{nxt['grade']}' ({nxt['min']}–{nxt['max']}). "
                    "Ranges must not overlap."
                )

        # ── 3 & 4. Coverage against GradingSystem bounds + gap check ─────────
        gs = self.instance  # GradingSystem instance set by inlineformset_factory
        if gs and gs.pk and gs.minimum_score is not None and gs.maximum_score is not None:
            sys_min = gs.minimum_score
            sys_max = gs.maximum_score

            if ranges[0]['min'] > sys_min:
                raise ValidationError(
                    f"Ranges don't start at the system minimum ({sys_min}). "
                    f"First range ('{ranges[0]['grade']}') begins at {ranges[0]['min']}."
                )

            if ranges[-1]['max'] < sys_max:
                raise ValidationError(
                    f"Ranges don't reach the system maximum ({sys_max}). "
                    f"Last range ('{ranges[-1]['grade']}') ends at {ranges[-1]['max']}."
                )

            for i in range(len(ranges) - 1):
                gap = ranges[i + 1]['min'] - ranges[i]['max']
                if gap > Decimal('0.01'):
                    raise ValidationError(
                        f"Score gap between '{ranges[i]['grade']}' (ends {ranges[i]['max']}) "
                        f"and '{ranges[i + 1]['grade']}' (starts {ranges[i + 1]['min']}): "
                        f"{gap} point(s) uncovered."
                    )


# Inline formset: GradingSystem ──< GradingRange
GradingRangeInlineFormSet = inlineformset_factory(
    GradingSystem,
    GradingRange,
    form=GradingRangeForm,
    formset=_GradingRangeBaseFormSet,
    extra=0,
    min_num=1,
    validate_min=True,
    can_delete=True,
    can_delete_extra=True,
)


# =============================================================================
# CLASS GRADING SYSTEM FORMS
# =============================================================================

class ClassGradingSystemForm(RequiredFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """Assign a grading system to a class for a specific session."""

    class Meta:
        model  = ClassGradingSystem
        fields = [
            'class_instance', 'grading_system', 'academic_session', 'subject',
            'effective_date', 'end_date',
            'priority', 'is_active', 'is_default_for_class',
            'assignment_reason',
            'custom_pass_mark', 'custom_maximum_score',
            'curriculum_override',
            'include_in_report_cards', 'show_grade_breakdown',
        ]
        widgets = {
            'class_instance':      forms.Select(attrs={'class': 'form-select'}),
            'grading_system':      forms.Select(attrs={'class': 'form-select'}),
            'academic_session':    forms.Select(attrs={'class': 'form-select'}),
            'subject':             forms.Select(attrs={'class': 'form-select'}),
            'effective_date':      DatePickerInput(),
            'end_date':            DatePickerInput(),
            'priority':            forms.NumberInput(attrs={'min': '1'}),
            'assignment_reason':   forms.Textarea(attrs={'rows': 2}),
            'custom_pass_mark':    forms.NumberInput(attrs={'step': '0.01'}),
            'custom_maximum_score':forms.NumberInput(attrs={'step': '0.01'}),
            'curriculum_override': forms.TextInput(attrs={'placeholder': 'Optional override'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['class_instance'].queryset = Class.objects.filter(
            is_active=True
        ).select_related('academic_level').order_by('academic_level__order', 'name')

        self.fields['grading_system'].queryset = GradingSystem.objects.filter(
            is_active=True
        ).order_by('name')

        self.fields['academic_session'].queryset = AcademicSession.objects.filter(
            is_active=True
        ).order_by('-start_date')

        self.fields['subject'].queryset = Subject.objects.filter(
            is_active=True
        ).order_by('name')

        self.fields['subject'].required          = False
        self.fields['subject'].help_text         = "Leave blank for a class-wide assignment."
        self.fields['end_date'].required         = False
        self.fields['custom_pass_mark'].required    = False
        self.fields['custom_maximum_score'].required= False
        self.fields['curriculum_override'].required = False

        if not self.instance.pk:
            from core.utils import get_school_today
            self.fields['effective_date'].initial = get_school_today()

    def clean(self):
        cleaned_data     = super().clean()
        effective_date   = cleaned_data.get('effective_date')
        end_date         = cleaned_data.get('end_date')
        academic_session = cleaned_data.get('academic_session')
        class_instance   = cleaned_data.get('class_instance')

        if effective_date and end_date and end_date <= effective_date:
            self.add_error('end_date', 'End date must be after effective date.')

        if academic_session and effective_date:
            if effective_date < academic_session.start_date:
                self.add_error(
                    'effective_date',
                    'Effective date cannot be before the session start date.',
                )
            if end_date and end_date > academic_session.end_date:
                self.add_error(
                    'end_date',
                    'End date cannot be after the session end date.',
                )

        if class_instance and academic_session:
            if class_instance.academic_session_id != academic_session.pk:
                self.add_error(
                    'class_instance',
                    f"'{class_instance}' belongs to '{class_instance.academic_session}', "
                    f"not the selected session '{academic_session}'.",
                )

        return cleaned_data


class GradingSystemFilterForm(BootstrapFormMixin, forms.Form):
    """Filter / search form for the grading-system list view."""

    q = forms.CharField(
        label='Search', required=False,
        widget=SearchInput(attrs={'placeholder': 'Search by name or code…'}),
    )
    grading_type = forms.ChoiceField(
        label='Grading Type', required=False,
        choices=[('', 'All Types')] + list(GradingSystem.GRADING_TYPES),
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    scale_type = forms.ChoiceField(
        label='Scale Type', required=False,
        choices=[('', 'All Scales')] + list(GradingSystem.SCALE_TYPES),
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    is_active = forms.ChoiceField(
        label='Status', required=False,
        choices=[('', 'All'), ('true', 'Active'), ('false', 'Inactive')],
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    is_default = forms.ChoiceField(
        label='Default System', required=False,
        choices=[('', 'All'), ('true', 'Default Only'), ('false', 'Non-Default')],
        widget=forms.Select(attrs={'class': 'form-select'}),
    )


class ClassGradingSystemFilterForm(BootstrapFormMixin, forms.Form):
    """Filter / search form for class grading-system assignments."""

    q = forms.CharField(
        label='Search', required=False,
        widget=SearchInput(attrs={'placeholder': 'Search by class or system…'}),
    )
    academic_session = forms.ModelChoiceField(
        label='Academic Session', queryset=None, required=False,
        widget=SelectWithDefault(default_label='All Sessions'),
    )
    class_instance = forms.ModelChoiceField(
        label='Class', queryset=None, required=False,
        widget=SelectWithDefault(default_label='All Classes'),
    )
    grading_system = forms.ModelChoiceField(
        label='Grading System', queryset=None, required=False,
        widget=SelectWithDefault(default_label='All Systems'),
    )
    subject = forms.ModelChoiceField(
        label='Subject', queryset=None, required=False,
        widget=SelectWithDefault(default_label='All Subjects'),
    )
    is_active = forms.ChoiceField(
        label='Status', required=False,
        choices=[('', 'All'), ('true', 'Active'), ('false', 'Inactive')],
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    is_default_for_class = forms.ChoiceField(
        label='Default Assignment', required=False,
        choices=[('', 'All'), ('true', 'Default'), ('false', 'Not Default')],
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['academic_session'].queryset = AcademicSession.objects.filter(
            is_active=True
        ).order_by('-start_date')

        self.fields['class_instance'].queryset = Class.objects.filter(
            is_active=True
        ).select_related('academic_level').order_by('academic_level__order', 'section')

        self.fields['grading_system'].queryset = GradingSystem.objects.filter(
            is_active=True
        ).order_by('name')

        self.fields['subject'].queryset = Subject.objects.filter(
            is_active=True
        ).order_by('name')


# =============================================================================
# EXAMINATION FORMS
# =============================================================================

class ExaminationForm(RequiredFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """Create / edit an examination."""

    class Meta:
        model  = Examination
        fields = [
            'name', 'code', 'description',
            'exam_category', 'exam_mode',
            'academic_session', 'subject', 'target_classes',
            'curriculum_type', 'subject_type_weight',
            'grading_system',
            'exam_date', 'start_time', 'end_time', 'duration_minutes',
            'total_marks', 'pass_marks',
            'instructions', 'materials_allowed', 'special_requirements',
            'examination_venue', 'classroom',
            'auto_submit', 'show_results_immediately', 'allow_review',
            'invigilators', 'status', 'notes',
        ]
        widgets = {
            'name':                forms.TextInput(attrs={'placeholder': 'e.g., Mathematics Mid-Term Exam'}),
            'code':                forms.TextInput(attrs={'placeholder': 'Auto-generated if left blank'}),
            'description':         forms.Textarea(attrs={'rows': 3}),
            'exam_category':       forms.Select(attrs={'class': 'form-select'}),
            'exam_mode':           forms.Select(attrs={'class': 'form-select'}),
            'academic_session':    forms.Select(attrs={'class': 'form-select'}),
            'subject':             forms.Select(attrs={'class': 'form-select'}),
            'target_classes':      forms.SelectMultiple(attrs={'class': 'form-select', 'size': '6'}),
            'curriculum_type':     forms.Select(attrs={'class': 'form-select'}),
            'subject_type_weight': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'grading_system':      forms.Select(attrs={'class': 'form-select'}),
            'exam_date':           DatePickerInput(),
            'start_time':          forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'end_time':            forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'duration_minutes':    forms.NumberInput(attrs={'min': '1'}),
            'total_marks':         forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
            'pass_marks':          forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'instructions':        forms.Textarea(attrs={'rows': 4}),
            'materials_allowed':   forms.Textarea(attrs={'rows': 2}),
            'special_requirements':forms.Textarea(attrs={'rows': 2}),
            'examination_venue':   forms.TextInput(attrs={'placeholder': 'e.g., Main Hall'}),
            'classroom':           forms.Select(attrs={'class': 'form-select'}),
            'status':              forms.Select(attrs={'class': 'form-select'}),
            'invigilators':        forms.SelectMultiple(attrs={'class': 'form-select', 'size': '4'}),
            'notes':               forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['exam_category'].queryset = ExamCategory.objects.filter(
            is_active=True
        ).order_by('name')

        self.fields['academic_session'].queryset = AcademicSession.objects.filter(
            is_active=True
        ).order_by('-start_date')

        self.fields['subject'].queryset = Subject.objects.filter(
            is_active=True
        ).order_by('name')

        self.fields['target_classes'].queryset = Class.objects.filter(
            is_active=True
        ).select_related('academic_level').order_by('academic_level__order', 'name')

        self.fields['grading_system'].queryset = GradingSystem.objects.filter(
            is_active=True
        ).order_by('name')

        self.fields['classroom'].queryset = ClassRoom.objects.filter(
            is_active=True
        ).order_by('building', 'floor', 'room_number')

        self.fields['invigilators'].queryset = Staff.objects.filter(
            is_active=True
        ).order_by('first_name', 'last_name')

        # Optional fields
        self.fields['code'].required            = False
        self.fields['grading_system'].required  = False
        self.fields['classroom'].required       = False
        self.fields['invigilators'].required    = False
        self.fields['duration_minutes'].required= False

        self.fields['grading_system'].help_text  = "Leave blank to inherit from class assignment."
        self.fields['duration_minutes'].help_text = "Derived automatically from start/end times if left blank."

    def clean(self):
        cleaned_data     = super().clean()
        exam_date        = cleaned_data.get('exam_date')
        start_time       = cleaned_data.get('start_time')
        end_time         = cleaned_data.get('end_time')
        duration_minutes = cleaned_data.get('duration_minutes')
        total_marks      = cleaned_data.get('total_marks')
        pass_marks       = cleaned_data.get('pass_marks')
        academic_session = cleaned_data.get('academic_session')

        from core.utils import get_school_today
        today = get_school_today()

        # New examinations cannot be in the past
        if not self.instance.pk and exam_date and exam_date < today:
            self.add_error('exam_date', 'Examination date cannot be in the past.')

        # Date must fall within the academic session
        if exam_date and academic_session:
            if not (academic_session.start_date <= exam_date <= academic_session.end_date):
                self.add_error(
                    'exam_date',
                    f"Date must be within the session period "
                    f"({academic_session.start_date} – {academic_session.end_date}).",
                )

        # Time range consistency
        if start_time and end_time:
            if start_time >= end_time:
                self.add_error('end_time', 'End time must be after start time.')
            elif not duration_minutes and exam_date:
                from datetime import datetime
                start_dt = datetime.combine(exam_date, start_time)
                end_dt   = datetime.combine(exam_date, end_time)
                cleaned_data['duration_minutes'] = int(
                    (end_dt - start_dt).total_seconds() / 60
                )

        # Pass marks vs total marks
        if total_marks is not None and total_marks <= 0:
            self.add_error('total_marks', 'Total marks must be greater than zero.')

        if total_marks and pass_marks is not None:
            if pass_marks < 0:
                self.add_error('pass_marks', 'Pass marks cannot be negative.')
            elif pass_marks > total_marks:
                self.add_error('pass_marks', 'Pass marks cannot exceed total marks.')

        return cleaned_data


class ExaminationFilterForm(DateRangeFormMixin, BootstrapFormMixin, forms.Form):
    """Filter / search form for the examination list view."""

    q = forms.CharField(
        label='Search', required=False,
        widget=SearchInput(attrs={'placeholder': 'Search by name or code…'}),
    )
    academic_session = forms.ModelChoiceField(
        label='Academic Session', queryset=None, required=False,
        widget=SelectWithDefault(default_label='All Sessions'),
    )
    exam_category = forms.ModelChoiceField(
        label='Category', queryset=None, required=False,
        widget=SelectWithDefault(default_label='All Categories'),
    )
    subject = forms.ModelChoiceField(
        label='Subject', queryset=None, required=False,
        widget=SelectWithDefault(default_label='All Subjects'),
    )
    status = forms.ChoiceField(
        label='Status', required=False,
        choices=[('', 'All Statuses')] + list(Examination.EXAM_STATUS_CHOICES),
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    exam_mode = forms.ChoiceField(
        label='Mode', required=False,
        choices=[('', 'All Modes')] + list(Examination.EXAM_MODES),
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    exam_date_from = forms.DateField(
        label='From Date', required=False,
        widget=DatePickerInput(),
    )
    exam_date_to = forms.DateField(
        label='To Date', required=False,
        widget=DatePickerInput(),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['academic_session'].queryset = AcademicSession.objects.filter(
            is_active=True
        ).order_by('-start_date')

        self.fields['exam_category'].queryset = ExamCategory.objects.filter(
            is_active=True
        ).order_by('name')

        self.fields['subject'].queryset = Subject.objects.filter(
            is_active=True
        ).order_by('name')

    def clean(self):
        cleaned_data   = super().clean()
        date_from      = cleaned_data.get('exam_date_from')
        date_to        = cleaned_data.get('exam_date_to')

        if date_from and date_to and date_from > date_to:
            self.add_error('exam_date_to', 'End date must be on or after start date.')

        return cleaned_data


# =============================================================================
# STUDENT EXAM RESULT FORMS
# =============================================================================

class StudentExamResultForm(RequiredFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """Create or edit a single StudentExamResult."""

    class Meta:
        model  = StudentExamResult
        fields = [
            'student', 'examination', 'score', 'status',
            'correct_answers', 'incorrect_answers', 'unanswered',
            'teacher_comments', 'examiner_comments',
        ]
        widgets = {
            'student':           forms.Select(attrs={'class': 'form-select'}),
            'examination':       forms.Select(attrs={'class': 'form-select'}),
            'score':             forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'status':            forms.Select(attrs={'class': 'form-select'}),
            'correct_answers':   forms.NumberInput(attrs={'min': '0'}),
            'incorrect_answers': forms.NumberInput(attrs={'min': '0'}),
            'unanswered':        forms.NumberInput(attrs={'min': '0'}),
            'teacher_comments':  forms.Textarea(attrs={'rows': 3}),
            'examiner_comments': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['student'].queryset = Student.objects.filter(
            enrollment_status='ACTIVE'
        ).order_by('last_name', 'first_name')

        self.fields['examination'].queryset = Examination.objects.filter(
            status__in=['ONGOING', 'COMPLETED']
        ).select_related('subject', 'academic_session').order_by('-exam_date')

        for f in ('correct_answers', 'incorrect_answers', 'unanswered',
                  'teacher_comments', 'examiner_comments'):
            self.fields[f].required = False

    def clean_score(self):
        score       = self.cleaned_data.get('score')
        examination = self.cleaned_data.get('examination') or (
            self.instance.examination if self.instance.pk else None
        )

        if score is not None and examination:
            if score < 0:
                raise ValidationError('Score cannot be negative.')
            if score > examination.total_marks:
                raise ValidationError(
                    f"Score {score} exceeds total marks ({examination.total_marks})."
                )

        return score

    def clean(self):
        cleaned_data = super().clean()
        student      = cleaned_data.get('student')
        examination  = cleaned_data.get('examination')

        if examination and examination.is_grade_locked if hasattr(examination, 'is_grade_locked') else False:
            raise ValidationError(
                "This examination's results are locked. Contact an administrator."
            )

        # Verify the student belongs to one of the exam's target classes
        if student and examination:
            target_class_ids = set(
                examination.target_classes.values_list('id', flat=True)
            )
            student_class_ids = set(
                student.class_enrollments.filter(
                    is_active=True,
                    academic_session=examination.academic_session,
                ).values_list('class_instance_id', flat=True)
            )
            if not (target_class_ids & student_class_ids):
                self.add_error(
                    'student',
                    f"{student.get_full_name()} is not enrolled in any of the "
                    "target classes for this examination.",
                )

        return cleaned_data



class StudentExamResultFilterForm(BootstrapFormMixin, forms.Form):
    """Filter / search form for the student-result list view."""

    q = forms.CharField(
        label='Search', required=False,
        widget=SearchInput(attrs={'placeholder': 'Student name or admission no.…'}),
    )
    examination = forms.ModelChoiceField(
        label='Examination', queryset=None, required=False,
        widget=SelectWithDefault(default_label='All Examinations'),
    )
    class_instance = forms.ModelChoiceField(
        label='Class', queryset=None, required=False,
        widget=SelectWithDefault(default_label='All Classes'),
    )
    status = forms.ChoiceField(
        label='Status', required=False,
        choices=[('', 'All Statuses')] + list(StudentExamResult.RESULT_STATUS_CHOICES),
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    is_published = forms.ChoiceField(
        label='Published', required=False,
        choices=[('', 'All'), ('true', 'Published'), ('false', 'Unpublished')],
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    is_grade_locked = forms.ChoiceField(
        label='Grade Locked', required=False,
        choices=[('', 'All'), ('true', 'Locked'), ('false', 'Unlocked')],
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    is_pass = forms.ChoiceField(
        label='Pass / Fail', required=False,
        choices=[('', 'All'), ('true', 'Pass'), ('false', 'Fail')],
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    min_score = forms.DecimalField(
        label='Min Score', required=False, decimal_places=2,
        widget=forms.NumberInput(attrs={
            'class': 'form-control', 'step': '0.01', 'placeholder': '0',
        }),
    )
    max_score = forms.DecimalField(
        label='Max Score', required=False, decimal_places=2,
        widget=forms.NumberInput(attrs={
            'class': 'form-control', 'step': '0.01', 'placeholder': '100',
        }),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['examination'].queryset = Examination.objects.all().select_related(
            'subject', 'academic_session'
        ).order_by('-exam_date')

        self.fields['class_instance'].queryset = Class.objects.filter(
            is_active=True
        ).select_related('academic_level').order_by('academic_level__order', 'section')

    def clean(self):
        cleaned_data = super().clean()
        min_score    = cleaned_data.get('min_score')
        max_score    = cleaned_data.get('max_score')

        if min_score is not None and min_score < 0:
            self.add_error('min_score', 'Minimum score cannot be negative.')

        if min_score is not None and max_score is not None and min_score > max_score:
            self.add_error('max_score', 'Maximum score must be greater than minimum score.')

        return cleaned_data


# =============================================================================
# ACTION / WORKFLOW FORMS
# =============================================================================

class GradeLockForm(BootstrapFormMixin, forms.Form):
    """Confirm locking of exam grade(s)."""

    lock_reason = forms.CharField(
        label='Reason for Locking',
        required=True,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'e.g., Results verified and approved by HOD.',
        }),
        help_text='Stored in the audit trail for each locked result.',
    )
    confirm = forms.BooleanField(
        label='I confirm locking these grade(s) — this cannot be undone without admin access.',
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )


class GradeUnlockForm(BootstrapFormMixin, forms.Form):
    """Confirm unlocking of exam grade(s). Requires elevated permission."""

    unlock_reason = forms.CharField(
        label='Reason for Unlocking',
        required=True,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'e.g., Data entry error in original score.',
        }),
        help_text='Unlocking allows the grade to be recalculated from the current grading system.',
    )
    confirm = forms.BooleanField(
        label='I understand that unlocking will allow score modifications.',
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )


class ResultPublishForm(BootstrapFormMixin, forms.Form):
    """Confirm publication of examination results."""

    auto_lock_grades = forms.BooleanField(
        label='Lock grades automatically after publication',
        initial=True,
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text='Recommended — locked grades cannot be altered without an explicit unlock.',
    )
    notes = forms.CharField(
        label='Publication Notes',
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'Optional notes visible to administrators.',
        }),
    )
    confirm = forms.BooleanField(
        label='I confirm publishing these results — they will become visible to authorised users.',
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )


# =============================================================================
# FILTER UTILITY HELPERS
# =============================================================================

def apply_examination_filters(queryset, form: ExaminationFilterForm):
    """
    Apply validated filter fields from ``ExaminationFilterForm`` to a queryset.

    Args:
        queryset: ``Examination`` queryset
        form:     Bound and validated ``ExaminationFilterForm``

    Returns:
        Filtered queryset (unchanged if form is invalid)
    """
    if not form.is_valid():
        return queryset

    cd = form.cleaned_data

    if cd.get('q'):
        queryset = queryset.filter(
            Q(name__icontains=cd['q']) |
            Q(code__icontains=cd['q']) |
            Q(description__icontains=cd['q'])
        )

    if cd.get('academic_session'):
        queryset = queryset.filter(academic_session=cd['academic_session'])

    if cd.get('exam_category'):
        queryset = queryset.filter(exam_category=cd['exam_category'])

    if cd.get('subject'):
        queryset = queryset.filter(subject=cd['subject'])

    if cd.get('status'):
        queryset = queryset.filter(status=cd['status'])

    if cd.get('exam_mode'):
        queryset = queryset.filter(exam_mode=cd['exam_mode'])

    if cd.get('exam_date_from'):
        queryset = queryset.filter(exam_date__gte=cd['exam_date_from'])

    if cd.get('exam_date_to'):
        queryset = queryset.filter(exam_date__lte=cd['exam_date_to'])

    return queryset


def apply_result_filters(queryset, form: StudentExamResultFilterForm):
    """
    Apply validated filter fields from ``StudentExamResultFilterForm`` to a queryset.

    Args:
        queryset: ``StudentExamResult`` queryset
        form:     Bound and validated ``StudentExamResultFilterForm``

    Returns:
        Filtered queryset (unchanged if form is invalid)
    """
    if not form.is_valid():
        return queryset

    cd = form.cleaned_data

    if cd.get('q'):
        queryset = queryset.filter(
            Q(student__first_name__icontains=cd['q']) |
            Q(student__last_name__icontains=cd['q'])  |
            Q(student__admission_number__icontains=cd['q'])
        )

    if cd.get('examination'):
        queryset = queryset.filter(examination=cd['examination'])

    if cd.get('status'):
        queryset = queryset.filter(status=cd['status'])

    if cd.get('is_published') in ('true', 'false'):
        queryset = queryset.filter(is_published=cd['is_published'] == 'true')

    if cd.get('is_grade_locked') in ('true', 'false'):
        queryset = queryset.filter(is_grade_locked=cd['is_grade_locked'] == 'true')

    if cd.get('is_pass') in ('true', 'false'):
        queryset = queryset.filter(is_pass=cd['is_pass'] == 'true')

    if cd.get('min_score') is not None:
        queryset = queryset.filter(score__gte=cd['min_score'])

    if cd.get('max_score') is not None:
        queryset = queryset.filter(score__lte=cd['max_score'])

    if cd.get('class_instance'):
        queryset = queryset.filter(
            student__class_enrollments__class_instance=cd['class_instance'],
            student__class_enrollments__is_active=True,
        ).distinct()

    return queryset