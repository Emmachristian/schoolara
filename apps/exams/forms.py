# exams/forms.py

"""
Examination management forms with timezone support.
All date validations use school timezone for consistency.
"""

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import Q
from django.forms import inlineformset_factory
from decimal import Decimal
import logging

# Import base form utilities with timezone support
from utils.forms import (
    BootstrapFormMixin,
    DateRangeFormMixin,
    RequiredFieldsMixin,
    MoneyFieldsMixin,
    DatePickerInput,
    DateTimePickerInput,
    SearchInput,
    SelectWithDefault,
    MoneyField,
    PercentageField,
    validate_future_date,
    validate_past_date,
    validate_date_not_before,
    validate_date_not_after,
    validate_positive_amount,
    validate_percentage,
)

from .models import (
    ExamCategory,
    GradingSystem,
    GradingRange,
    ClassGradingSystem,
    Examination,
    ExamRegistration,
    StudentExamResult,
)
from students.models import Student
from academics.models import Class, Subject, AcademicLevel, AcademicSession, ClassRoom
from hr.models import Staff

logger = logging.getLogger(__name__)


# =============================================================================
# EXAM CATEGORY FORMS
# =============================================================================

class ExamCategoryForm(RequiredFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """Form for creating/editing exam categories"""
    
    class Meta:
        model = ExamCategory
        fields = [
            'name', 'abbreviation', 'code', 'description',
            'category_type', 'applicable_levels', 'applicable_subject_types',
            'curriculum_compatibility', 'frequency', 'weight_percentage',
            'required_payment_percentage', 'consider_all_outstanding_balances',
            'requires_registration', 'registration_deadline_days',
            'allows_retakes', 'max_retakes',
            'includes_in_report_cards', 'public_results', 'results_publication_days',
            'is_active', 'effective_date', 'valid_sessions',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g., Mid-Term Examination'}),
            'abbreviation': forms.TextInput(attrs={'placeholder': 'e.g., MTE'}),
            'code': forms.TextInput(attrs={'placeholder': 'e.g., EXAM-MID'}),
            'description': forms.Textarea(attrs={'rows': 3}),
            'category_type': forms.Select(attrs={'class': 'form-select'}),
            'applicable_levels': forms.SelectMultiple(attrs={'class': 'form-select', 'size': '6'}),
            'curriculum_compatibility': forms.Select(attrs={'class': 'form-select'}),
            'frequency': forms.Select(attrs={'class': 'form-select'}),
            'weight_percentage': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'max': '100'}),
            'required_payment_percentage': forms.NumberInput(attrs={'min': '0', 'max': '100'}),
            'registration_deadline_days': forms.NumberInput(attrs={'min': '0'}),
            'max_retakes': forms.NumberInput(attrs={'min': '0', 'max': '10'}),
            'results_publication_days': forms.NumberInput(attrs={'min': '0'}),
            'effective_date': DatePickerInput(),
            'valid_sessions': forms.SelectMultiple(attrs={'class': 'form-select', 'size': '4'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set querysets
        try:
            self.fields['applicable_levels'].queryset = AcademicLevel.objects.filter(
                is_active=True
            ).order_by('order')
            
            self.fields['valid_sessions'].queryset = AcademicSession.objects.filter(
                is_active=True
            ).order_by('-start_date')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")
        
        # Set help texts
        self.fields['weight_percentage'].help_text = "Percentage contribution to overall grade (0-100)"
        self.fields['required_payment_percentage'].help_text = "Minimum % of fees paid to participate (0-100)"
        
        # Set default effective date using school timezone
        if not self.instance.pk:
            from core.utils import get_school_today
            self.fields['effective_date'].initial = get_school_today()


# =============================================================================
# GRADING SYSTEM FORMS
# =============================================================================

class GradingSystemForm(RequiredFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """Form for creating/editing grading systems"""
    
    class Meta:
        model = GradingSystem
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
            'curriculum_compatibility', 'subject_type_specific', 'applicable_subject_types',
            'is_active', 'is_default', 'effective_date', 'expiry_date',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g., Cambridge IGCSE Grading'}),
            'code': forms.TextInput(attrs={'placeholder': 'e.g., IGCSE-GRADE'}),
            'description': forms.Textarea(attrs={'rows': 3}),
            'grading_type': forms.Select(attrs={'class': 'form-select'}),
            'scale_type': forms.Select(attrs={'class': 'form-select'}),
            'minimum_score': forms.NumberInput(attrs={'step': '0.01'}),
            'maximum_score': forms.NumberInput(attrs={'step': '0.01'}),
            'pass_mark': forms.NumberInput(attrs={'step': '0.01'}),
            'minimum_subjects_required': forms.NumberInput(attrs={'min': '1'}),
            'maximum_subjects_considered': forms.NumberInput(attrs={'min': '1'}),
            'subject_selection_method': forms.Select(attrs={'class': 'form-select'}),
            'mandatory_subjects': forms.SelectMultiple(attrs={'class': 'form-select', 'size': '6'}),
            'optional_subjects': forms.SelectMultiple(attrs={'class': 'form-select', 'size': '6'}),
            'aggregate_calculation_method': forms.Select(attrs={'class': 'form-select'}),
            'maximum_failures_allowed': forms.NumberInput(attrs={'min': '0'}),
            'round_to_nearest': forms.NumberInput(attrs={'step': '0.01'}),
            'display_format': forms.TextInput(attrs={'placeholder': '{grade} ({score})'}),
            'applicable_levels': forms.SelectMultiple(attrs={'class': 'form-select', 'size': '6'}),
            'applicable_subjects': forms.SelectMultiple(attrs={'class': 'form-select', 'size': '6'}),
            'curriculum_compatibility': forms.Select(attrs={'class': 'form-select'}),
            'effective_date': DatePickerInput(),
            'expiry_date': DatePickerInput(),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set querysets
        try:
            self.fields['applicable_levels'].queryset = AcademicLevel.objects.filter(
                is_active=True
            ).order_by('order')
            
            self.fields['applicable_subjects'].queryset = Subject.objects.filter(
                is_active=True
            ).order_by('name')
            
            self.fields['mandatory_subjects'].queryset = Subject.objects.filter(
                is_active=True
            ).order_by('name')
            
            self.fields['optional_subjects'].queryset = Subject.objects.filter(
                is_active=True
            ).order_by('name')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")
        
        # Set default effective date using school timezone
        if not self.instance.pk:
            from core.utils import get_school_today
            self.fields['effective_date'].initial = get_school_today()
    
    def clean(self):
        """Validate grading system configuration"""
        cleaned_data = super().clean()
        
        minimum_score = cleaned_data.get('minimum_score')
        maximum_score = cleaned_data.get('maximum_score')
        pass_mark = cleaned_data.get('pass_mark')
        effective_date = cleaned_data.get('effective_date')
        expiry_date = cleaned_data.get('expiry_date')
        
        # Validate score ranges
        if minimum_score and maximum_score:
            if minimum_score >= maximum_score:
                raise ValidationError({
                    'maximum_score': 'Maximum score must be greater than minimum score.'
                })
        
        # Validate pass mark
        if pass_mark and minimum_score and maximum_score:
            if pass_mark < minimum_score or pass_mark > maximum_score:
                raise ValidationError({
                    'pass_mark': 'Pass mark must be between minimum and maximum scores.'
                })
        
        # Validate date range
        if effective_date and expiry_date:
            if expiry_date <= effective_date:
                raise ValidationError({
                    'expiry_date': 'Expiry date must be after effective date.'
                })
        
        return cleaned_data


class GradingRangeForm(BootstrapFormMixin, forms.ModelForm):
    """Form for creating/editing grading ranges (used in formset)"""
    
    class Meta:
        model = GradingRange
        fields = [
            # NOTE: 'grading_system' is NOT included - handled by formset
            'grade', 'grade_name',
            'min_score', 'max_score', 'aggregate',
            'gpa_points', 'quality_points',
            'color_code', 'text_color',
            'comments', 'description', 'performance_level',
            'is_passing_grade', 'display_order',
        ]
        widgets = {
            'grade': forms.TextInput(attrs={'placeholder': 'e.g., A, B+, D1', 'class': 'form-control'}),
            'grade_name': forms.TextInput(attrs={'placeholder': 'e.g., Excellent, Good', 'class': 'form-control'}),
            'min_score': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control'}),
            'max_score': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control'}),
            'aggregate': forms.TextInput(attrs={'placeholder': 'e.g., D1, C6', 'class': 'form-control'}),
            'gpa_points': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control'}),
            'quality_points': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control'}),
            'color_code': forms.TextInput(attrs={
                'type': 'color',
                'placeholder': '#00FF00',
                'class': 'form-control form-control-color'
            }),
            'text_color': forms.TextInput(attrs={
                'type': 'color',
                'placeholder': '#FFFFFF',
                'class': 'form-control form-control-color'
            }),
            'comments': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
            'performance_level': forms.Select(attrs={'class': 'form-select'}),
            'display_order': forms.NumberInput(attrs={'min': '0', 'class': 'form-control'}),
        }
    
    def clean(self):
        """Basic validation for individual grading range"""
        cleaned_data = super().clean()
        
        min_score = cleaned_data.get('min_score')
        max_score = cleaned_data.get('max_score')
        
        # Validate score range
        if min_score is not None and max_score is not None:
            if min_score >= max_score:
                raise ValidationError({
                    'max_score': 'Maximum score must be greater than minimum score.'
                })
        
        # Note: System bounds and overlap validation happens in formset.clean()
        return cleaned_data


# =============================================================================
# GRADING RANGE INLINE FORMSET
# =============================================================================

# Base formset factory
BaseGradingRangeFormSet = inlineformset_factory(
    GradingSystem,                     # Parent model
    GradingRange,                       # Child model
    form=GradingRangeForm,             # Use our custom form
    extra=5,                            # Show 5 empty forms by default
    min_num=1,                          # Require at least 1 grade range
    validate_min=True,
    can_delete=True,                    # Allow deletion of existing ranges
    can_delete_extra=True,              # Allow deletion of extra empty forms
)


class GradingRangeFormSet(BaseGradingRangeFormSet):
    """
    Enhanced formset for grading ranges with comprehensive validation.
    
    Validates:
    - No overlapping score ranges
    - Complete coverage of grading system min-max spectrum
    - No gaps in score coverage
    - Proper ordering of ranges
    """
    
    def clean(self):
        """
        Enhanced validation across all forms in the formset.
        Checks for overlapping ranges and gaps in score coverage.
        """
        if any(self.errors):
            # Don't proceed with formset validation if individual forms have errors
            return
        
        super().clean()
        
        # Get all valid forms (not deleted, not empty)
        valid_forms = [
            form for form in self.forms
            if form.cleaned_data and not form.cleaned_data.get('DELETE', False)
        ]
        
        if not valid_forms:
            raise ValidationError("At least one grade range is required.")
        
        # Extract score ranges with form reference
        ranges = []
        for form in valid_forms:
            data = form.cleaned_data
            min_score = data.get('min_score')
            max_score = data.get('max_score')
            
            if min_score is not None and max_score is not None:
                ranges.append({
                    'min': min_score,
                    'max': max_score,
                    'grade': data.get('grade', ''),
                    'form': form
                })
        
        if not ranges:
            raise ValidationError("At least one complete grade range (with min and max scores) is required.")
        
        # Sort ranges by min_score for easier validation
        ranges.sort(key=lambda x: x['min'])
        
        # =====================================================================
        # VALIDATION 1: Check for overlapping ranges
        # =====================================================================
        for i in range(len(ranges) - 1):
            current = ranges[i]
            next_range = ranges[i + 1]
            
            # Check if current range's max overlaps with next range's min
            if current['max'] >= next_range['min']:
                raise ValidationError(
                    f"Grade ranges overlap: '{current['grade']}' "
                    f"({current['min']}-{current['max']}) overlaps with "
                    f"'{next_range['grade']}' ({next_range['min']}-{next_range['max']}). "
                    f"Ranges must not overlap."
                )
        
        # =====================================================================
        # VALIDATION 2: Check coverage against grading system bounds
        # =====================================================================
        grading_system = self.instance
        
        if grading_system and grading_system.minimum_score is not None and grading_system.maximum_score is not None:
            system_min = grading_system.minimum_score
            system_max = grading_system.maximum_score
            
            # Check if ranges start at system minimum
            if ranges[0]['min'] > system_min:
                raise ValidationError(
                    f"Grade ranges don't start at system minimum ({system_min}). "
                    f"First range ('{ranges[0]['grade']}') starts at {ranges[0]['min']}. "
                    f"Please add a range covering scores from {system_min}."
                )
            
            # Check if ranges reach system maximum
            if ranges[-1]['max'] < system_max:
                raise ValidationError(
                    f"Grade ranges don't reach system maximum ({system_max}). "
                    f"Last range ('{ranges[-1]['grade']}') ends at {ranges[-1]['max']}. "
                    f"Please add a range covering scores up to {system_max}."
                )
            
            # ================================================================
            # VALIDATION 3: Check for gaps between consecutive ranges
            # ================================================================
            for i in range(len(ranges) - 1):
                current = ranges[i]
                next_range = ranges[i + 1]
                
                # Check if there's a gap between current max and next min
                # Allow for small floating point differences (0.01)
                gap = next_range['min'] - current['max']
                if gap > Decimal('0.01'):
                    raise ValidationError(
                        f"Gap detected in grade ranges: '{current['grade']}' ends at {current['max']}, "
                        f"but '{next_range['grade']}' starts at {next_range['min']}. "
                        f"There is a gap of {gap} points. Please ensure complete coverage."
                    )
        
        # =====================================================================
        # VALIDATION 4: Check for duplicate grades
        # =====================================================================
        grades = [r['grade'] for r in ranges if r['grade']]
        if len(grades) != len(set(grades)):
            duplicates = [grade for grade in set(grades) if grades.count(grade) > 1]
            raise ValidationError(
                f"Duplicate grade(s) found: {', '.join(duplicates)}. "
                f"Each grade must be unique within a grading system."
            )
        
        return self.cleaned_data


# =============================================================================
# CLASS GRADING SYSTEM FORMS
# =============================================================================

class ClassGradingSystemForm(RequiredFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """Form for assigning grading systems to classes"""
    
    class Meta:
        model = ClassGradingSystem
        fields = [
            'class_instance', 'grading_system', 'academic_session', 'subject',
            'effective_date', 'end_date', 'priority', 'is_active', 'is_default_for_class',
            'assignment_reason', 'custom_pass_mark', 'custom_maximum_score',
            'curriculum_override', 'include_in_report_cards', 'show_grade_breakdown',
        ]
        widgets = {
            'class_instance': forms.Select(attrs={'class': 'form-select'}),
            'grading_system': forms.Select(attrs={'class': 'form-select'}),
            'academic_session': forms.Select(attrs={'class': 'form-select'}),
            'subject': forms.Select(attrs={'class': 'form-select'}),
            'effective_date': DatePickerInput(),
            'end_date': DatePickerInput(),
            'priority': forms.NumberInput(attrs={'min': '1'}),
            'assignment_reason': forms.Textarea(attrs={'rows': 2}),
            'custom_pass_mark': forms.NumberInput(attrs={'step': '0.01'}),
            'custom_maximum_score': forms.NumberInput(attrs={'step': '0.01'}),
            'curriculum_override': forms.TextInput(attrs={'placeholder': 'Optional'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set querysets
        try:
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
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")
        
        # Make subject optional
        self.fields['subject'].required = False
        self.fields['subject'].help_text = "Leave blank for class-wide assignment"
        
        # Set default dates using school timezone
        if not self.instance.pk:
            from core.utils import get_school_today
            self.fields['effective_date'].initial = get_school_today()
    
    def clean(self):
        """Validate class grading system assignment"""
        cleaned_data = super().clean()
        
        effective_date = cleaned_data.get('effective_date')
        end_date = cleaned_data.get('end_date')
        academic_session = cleaned_data.get('academic_session')
        class_instance = cleaned_data.get('class_instance')
        
        # Validate date range
        if effective_date and end_date:
            if end_date <= effective_date:
                raise ValidationError({
                    'end_date': 'End date must be after effective date.'
                })
        
        # Validate dates within session
        if academic_session and effective_date:
            if effective_date < academic_session.start_date:
                raise ValidationError({
                    'effective_date': 'Effective date cannot be before session start.'
                })
            
            if end_date and end_date > academic_session.end_date:
                raise ValidationError({
                    'end_date': 'End date cannot be after session end.'
                })
        
        # Validate class belongs to the selected session
        if class_instance and academic_session:
            if class_instance.academic_session != academic_session:
                raise ValidationError({
                    'class_instance': f'Selected class belongs to {class_instance.academic_session}, not {academic_session}.'
                })
        
        return cleaned_data


# =============================================================================
# EXAMINATION FORMS
# =============================================================================

class ExaminationForm(RequiredFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """Form for creating/editing examinations"""
    
    class Meta:
        model = Examination
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
            'name': forms.TextInput(attrs={'placeholder': 'e.g., Mathematics Mid-Term Exam'}),
            'code': forms.TextInput(attrs={'placeholder': 'e.g., MATH-MTE-2024'}),
            'description': forms.Textarea(attrs={'rows': 3}),
            'exam_category': forms.Select(attrs={'class': 'form-select'}),
            'exam_mode': forms.Select(attrs={'class': 'form-select'}),
            'academic_session': forms.Select(attrs={'class': 'form-select'}),
            'subject': forms.Select(attrs={'class': 'form-select'}),
            'target_classes': forms.SelectMultiple(attrs={'class': 'form-select', 'size': '6'}),
            'curriculum_type': forms.Select(attrs={'class': 'form-select'}),
            'subject_type_weight': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'grading_system': forms.Select(attrs={'class': 'form-select'}),
            'exam_date': DatePickerInput(),
            'start_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'end_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'duration_minutes': forms.NumberInput(attrs={'min': '1'}),
            'total_marks': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'pass_marks': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'instructions': forms.Textarea(attrs={'rows': 4}),
            'materials_allowed': forms.Textarea(attrs={'rows': 2}),
            'special_requirements': forms.Textarea(attrs={'rows': 2}),
            'examination_venue': forms.TextInput(attrs={'placeholder': 'e.g., Main Hall'}),
            'classroom': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'invigilators': forms.SelectMultiple(attrs={'class': 'form-select', 'size': '4'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set querysets
        try:
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
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")
        
        # Make some fields optional
        self.fields['grading_system'].required = False
        self.fields['grading_system'].help_text = "Leave blank to use class default"
        self.fields['classroom'].required = False
        
        # Set help texts
        self.fields['duration_minutes'].help_text = "Duration in minutes"
        self.fields['total_marks'].help_text = "Total marks for this examination"
        self.fields['pass_marks'].help_text = "Minimum marks to pass"
    
    def clean(self):
        """Validate examination data using school timezone"""
        cleaned_data = super().clean()
        
        exam_date = cleaned_data.get('exam_date')
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        duration_minutes = cleaned_data.get('duration_minutes')
        total_marks = cleaned_data.get('total_marks')
        pass_marks = cleaned_data.get('pass_marks')
        academic_session = cleaned_data.get('academic_session')
        
        from core.utils import get_school_today
        today = get_school_today()
        
        # Validate exam date for new exams
        if not self.instance.pk and exam_date:
            if exam_date < today:
                raise ValidationError({
                    'exam_date': 'Examination date cannot be in the past.'
                })
        
        # Validate exam date within academic session
        if exam_date and academic_session:
            if exam_date < academic_session.start_date or exam_date > academic_session.end_date:
                raise ValidationError({
                    'exam_date': f'Examination date must be within the academic session period ({academic_session.start_date} to {academic_session.end_date}).'
                })
        
        # Validate time range
        if start_time and end_time:
            if start_time >= end_time:
                raise ValidationError({
                    'end_time': 'End time must be after start time.'
                })
            
            # Calculate duration if not provided
            if not duration_minutes:
                from datetime import datetime
                start_dt = datetime.combine(exam_date or today, start_time)
                end_dt = datetime.combine(exam_date or today, end_time)
                duration = end_dt - start_dt
                cleaned_data['duration_minutes'] = int(duration.total_seconds() / 60)
        
        # Validate pass marks
        if total_marks and pass_marks:
            if pass_marks > total_marks:
                raise ValidationError({
                    'pass_marks': 'Pass marks cannot exceed total marks.'
                })
            
            if pass_marks < 0:
                raise ValidationError({
                    'pass_marks': 'Pass marks must be a positive value.'
                })
        
        # Validate total marks is positive
        if total_marks and total_marks <= 0:
            raise ValidationError({
                'total_marks': 'Total marks must be greater than zero.'
            })
        
        return cleaned_data


# =============================================================================
# EXAM REGISTRATION FORMS
# =============================================================================

class ExamRegistrationForm(RequiredFieldsMixin, BootstrapFormMixin, forms.ModelForm):
    """Form for exam registration"""
    
    class Meta:
        model = ExamRegistration
        fields = [
            'student', 'examination',
            'special_accommodations', 'requires_assistance',
            'notes',
        ]
        widgets = {
            'student': forms.Select(attrs={'class': 'form-select'}),
            'examination': forms.Select(attrs={'class': 'form-select'}),
            'special_accommodations': forms.Textarea(attrs={'rows': 3}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set querysets
        try:
            self.fields['student'].queryset = Student.objects.filter(
                enrollment_status='ACTIVE'
            ).order_by('first_name', 'last_name')
            
            self.fields['examination'].queryset = Examination.objects.filter(
                status__in=['PLANNED', 'SCHEDULED']
            ).select_related('subject', 'academic_session').order_by('-exam_date')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")

    def clean(self):
        cleaned_data = super().clean()
        student = cleaned_data.get('student')
        examination = cleaned_data.get('examination')
        
        if student and examination:
            # Check for existing registration
            existing = ExamRegistration.objects.filter(
                student=student,
                examination=examination
            ).exclude(pk=self.instance.pk if self.instance.pk else None)
            
            if existing.exists():
                raise ValidationError({
                    'student': f'{student.get_full_name()} is already registered for this examination.'
                })
            
            # Check if student is in target classes
            from students.models import StudentClassEnrollment
            
            student_classes = StudentClassEnrollment.objects.filter(
                student=student,
                academic_session=examination.academic_session,
                is_active=True,
                completion_status='ONGOING'
            ).values_list('class_instance', flat=True)
            
            exam_target_classes = examination.target_classes.values_list('id', flat=True)
            
            if not any(cls in exam_target_classes for cls in student_classes):
                raise ValidationError({
                    'student': f'{student.get_full_name()} is not enrolled in any of the target classes for this examination.'
                })
            
            # Check exam category registration requirements
            if examination.exam_category and examination.exam_category.requires_registration:
                # Check registration deadline
                if examination.exam_category.registration_deadline_days:
                    from core.utils import get_school_today
                    from datetime import timedelta
                    
                    today = get_school_today()
                    deadline = examination.exam_date - timedelta(
                        days=examination.exam_category.registration_deadline_days
                    )
                    
                    if today > deadline:
                        raise ValidationError(
                            f'Registration deadline has passed. Deadline was {deadline}.'
                        )
        
        return cleaned_data


# =============================================================================
# STUDENT EXAM RESULT FORMS
# =============================================================================

class StudentExamResultForm(RequiredFieldsMixin, BootstrapFormMixin, MoneyFieldsMixin, forms.ModelForm):
    """Form for entering/editing exam results"""
    
    class Meta:
        model = StudentExamResult
        fields = [
            'student', 'examination', 'score', 'status',
            'correct_answers', 'incorrect_answers', 'unanswered',
            'teacher_comments', 'examiner_comments',
        ]
        widgets = {
            'student': forms.Select(attrs={'class': 'form-select'}),
            'examination': forms.Select(attrs={'class': 'form-select'}),
            'score': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'correct_answers': forms.NumberInput(attrs={'min': '0'}),
            'incorrect_answers': forms.NumberInput(attrs={'min': '0'}),
            'unanswered': forms.NumberInput(attrs={'min': '0'}),
            'teacher_comments': forms.Textarea(attrs={'rows': 3}),
            'examiner_comments': forms.Textarea(attrs={'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set querysets
        try:
            self.fields['student'].queryset = Student.objects.filter(
                enrollment_status='ACTIVE'
            ).order_by('first_name', 'last_name')
            
            self.fields['examination'].queryset = Examination.objects.filter(
                status__in=['ONGOING', 'COMPLETED']
            ).select_related('subject').order_by('-exam_date')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")
        
        # Disable grade fields (auto-calculated)
        if 'grade' in self.fields:
            self.fields['grade'].disabled = True
        if 'percentage' in self.fields:
            self.fields['percentage'].disabled = True
    
    def clean_score(self):
        """Validate score against examination total marks"""
        score = self.cleaned_data.get('score')
        examination = self.cleaned_data.get('examination') or self.instance.examination
        
        if score is not None and examination:
            if score > examination.total_marks:
                raise ValidationError(
                    f'Score cannot exceed total marks ({examination.total_marks}).'
                )
            if score < 0:
                raise ValidationError('Score cannot be negative.')
        
        return score
    
    def clean(self):
        cleaned_data = super().clean()
        student = cleaned_data.get('student')
        examination = cleaned_data.get('examination')
        
        if student and examination:
            # Check if student is enrolled in one of the exam's target classes
            from students.models import StudentClassEnrollment
            
            student_classes = StudentClassEnrollment.objects.filter(
                student=student,
                academic_session=examination.academic_session,
                is_active=True,
                completion_status='ONGOING'
            ).values_list('class_instance', flat=True)
            
            exam_target_classes = examination.target_classes.values_list('id', flat=True)
            
            if not any(cls in exam_target_classes for cls in student_classes):
                raise ValidationError({
                    'student': f'{student.get_full_name()} is not enrolled in any of the target classes for this examination.'
                })
        
        return cleaned_data


# =============================================================================
# GRADE LOCKING FORMS
# =============================================================================

class GradeLockForm(BootstrapFormMixin, forms.Form):
    """Form for locking exam grades"""
    
    lock_reason = forms.CharField(
        label='Reason for Locking',
        required=True,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'Provide a reason for locking these grades...'
        }),
        help_text='This action will prevent future grade changes'
    )
    
    confirm = forms.BooleanField(
        label='I confirm locking these grades',
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )


class GradeUnlockForm(BootstrapFormMixin, forms.Form):
    """Form for unlocking exam grades"""
    
    unlock_reason = forms.CharField(
        label='Reason for Unlocking',
        required=True,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'Provide a reason for unlocking these grades...'
        }),
        help_text='This will allow grades to be recalculated based on current grading system'
    )
    
    confirm = forms.BooleanField(
        label='I understand this will allow grade modifications',
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )


class ResultPublishForm(BootstrapFormMixin, forms.Form):
    """Form for publishing exam results"""
    
    auto_lock_grades = forms.BooleanField(
        label='Automatically lock grades after publication',
        initial=True,
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text='Locked grades cannot be changed without explicit unlocking'
    )
    
    notes = forms.CharField(
        label='Publication Notes',
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'Optional notes about this publication...'
        })
    )
    
    confirm = forms.BooleanField(
        label='I confirm publishing these results',
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )


# =============================================================================
# FILTER FORMS
# =============================================================================

class ExaminationFilterForm(DateRangeFormMixin, BootstrapFormMixin, forms.Form):
    """Filter form for examinations using school timezone"""
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={'placeholder': 'Search by name, code...'})
    )
    
    academic_session = forms.ModelChoiceField(
        label='Academic Session',
        queryset=None,
        required=False,
        widget=SelectWithDefault(default_label="All Sessions")
    )
    
    exam_category = forms.ModelChoiceField(
        label='Category',
        queryset=None,
        required=False,
        widget=SelectWithDefault(default_label="All Categories")
    )
    
    subject = forms.ModelChoiceField(
        label='Subject',
        queryset=None,
        required=False,
        widget=SelectWithDefault(default_label="All Subjects")
    )
    
    status = forms.ChoiceField(
        label='Status',
        choices=[('', 'All Statuses')] + list(Examination.EXAM_STATUS_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    exam_date_from = forms.DateField(
        label='From Date',
        required=False,
        widget=DatePickerInput()
    )
    
    exam_date_to = forms.DateField(
        label='To Date',
        required=False,
        widget=DatePickerInput()
    )
    
    exam_mode = forms.ChoiceField(
        label='Exam Mode',
        choices=[('', 'All Modes')] + list(Examination.EXAM_MODES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
            self.fields['academic_session'].queryset = AcademicSession.objects.filter(
                is_active=True
            ).order_by('-start_date')
            
            self.fields['exam_category'].queryset = ExamCategory.objects.filter(
                is_active=True
            ).order_by('name')
            
            self.fields['subject'].queryset = Subject.objects.filter(
                is_active=True
            ).order_by('name')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")
    
    def clean(self):
        """Validate filter form data"""
        cleaned_data = super().clean()
        
        exam_date_from = cleaned_data.get('exam_date_from')
        exam_date_to = cleaned_data.get('exam_date_to')
        
        # Validate date range
        if exam_date_from and exam_date_to:
            if exam_date_from > exam_date_to:
                raise ValidationError({
                    'exam_date_to': 'End date must be after start date.'
                })
        
        return cleaned_data


class StudentExamResultFilterForm(BootstrapFormMixin, forms.Form):
    """Filter form for student exam results"""
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={'placeholder': 'Search by student name...'})
    )
    
    examination = forms.ModelChoiceField(
        label='Examination',
        queryset=None,
        required=False,
        widget=SelectWithDefault(default_label="All Examinations")
    )
    
    status = forms.ChoiceField(
        label='Status',
        choices=[('', 'All Statuses')] + list(StudentExamResult.RESULT_STATUS_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    is_published = forms.ChoiceField(
        label='Published',
        choices=[
            ('', 'All'),
            ('true', 'Published'),
            ('false', 'Unpublished')
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    is_grade_locked = forms.ChoiceField(
        label='Grade Locked',
        choices=[
            ('', 'All'),
            ('true', 'Locked'),
            ('false', 'Unlocked')
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    is_pass = forms.ChoiceField(
        label='Pass/Fail',
        choices=[
            ('', 'All'),
            ('true', 'Pass'),
            ('false', 'Fail')
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    min_score = forms.DecimalField(
        label='Minimum Score',
        required=False,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Min score',
            'step': '0.01'
        })
    )
    
    max_score = forms.DecimalField(
        label='Maximum Score',
        required=False,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Max score',
            'step': '0.01'
        })
    )
    
    class_instance = forms.ModelChoiceField(
        label='Class',
        queryset=None,
        required=False,
        widget=SelectWithDefault(default_label="All Classes")
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
            self.fields['examination'].queryset = Examination.objects.all().select_related(
                'subject', 'academic_session'
            ).order_by('-exam_date')
            
            from academics.models import Class
            self.fields['class_instance'].queryset = Class.objects.filter(
                is_active=True
            ).select_related('academic_level').order_by('academic_level__order', 'section')
            
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")
    
    def clean(self):
        """Validate filter form data"""
        cleaned_data = super().clean()
        
        min_score = cleaned_data.get('min_score')
        max_score = cleaned_data.get('max_score')
        
        # Validate score range
        if min_score is not None and max_score is not None:
            if min_score > max_score:
                raise ValidationError({
                    'max_score': 'Maximum score must be greater than minimum score.'
                })
        
        # Validate min_score is not negative
        if min_score is not None and min_score < 0:
            raise ValidationError({
                'min_score': 'Minimum score cannot be negative.'
            })
        
        return cleaned_data


class ExamCategoryFilterForm(BootstrapFormMixin, forms.Form):
    """Filter form for exam categories"""
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={'placeholder': 'Search by name, code...'})
    )
    
    category_type = forms.ChoiceField(
        label='Category Type',
        choices=[('', 'All Types')] + list(ExamCategory.CATEGORY_TYPES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    frequency = forms.ChoiceField(
        label='Frequency',
        choices=[('', 'All Frequencies')] + list(ExamCategory.FREQUENCY_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    is_active = forms.ChoiceField(
        label='Status',
        choices=[
            ('', 'All'),
            ('true', 'Active'),
            ('false', 'Inactive')
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    requires_registration = forms.ChoiceField(
        label='Requires Registration',
        choices=[
            ('', 'All'),
            ('true', 'Yes'),
            ('false', 'No')
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )


class GradingSystemFilterForm(BootstrapFormMixin, forms.Form):
    """Filter form for grading systems"""
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={'placeholder': 'Search by name, code...'})
    )
    
    grading_type = forms.ChoiceField(
        label='Grading Type',
        choices=[('', 'All Types')] + list(GradingSystem.GRADING_TYPES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    scale_type = forms.ChoiceField(
        label='Scale Type',
        choices=[('', 'All Scales')] + list(GradingSystem.SCALE_TYPES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    is_active = forms.ChoiceField(
        label='Status',
        choices=[
            ('', 'All'),
            ('true', 'Active'),
            ('false', 'Inactive')
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    is_default = forms.ChoiceField(
        label='Default System',
        choices=[
            ('', 'All'),
            ('true', 'Default'),
            ('false', 'Not Default')
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )


class ExamRegistrationFilterForm(BootstrapFormMixin, forms.Form):
    """Filter form for exam registrations"""
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={'placeholder': 'Search by student name...'})
    )
    
    examination = forms.ModelChoiceField(
        label='Examination',
        queryset=None,
        required=False,
        widget=SelectWithDefault(default_label="All Examinations")
    )
    
    registration_status = forms.ChoiceField(
        label='Registration Status',
        choices=[('', 'All')] + list(ExamRegistration.REGISTRATION_STATUS_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    requires_assistance = forms.ChoiceField(
        label='Requires Assistance',
        choices=[
            ('', 'All'),
            ('true', 'Yes'),
            ('false', 'No')
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    payment_verified = forms.ChoiceField(
        label='Payment Verified',
        choices=[
            ('', 'All'),
            ('true', 'Verified'),
            ('false', 'Not Verified')
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
            self.fields['examination'].queryset = Examination.objects.filter(
                status__in=['PLANNED', 'SCHEDULED', 'ONGOING']
            ).select_related('subject', 'academic_session').order_by('-exam_date')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")


class ClassGradingSystemFilterForm(BootstrapFormMixin, forms.Form):
    """Filter form for class grading system assignments"""
    
    q = forms.CharField(
        label='Search',
        required=False,
        widget=SearchInput(attrs={'placeholder': 'Search by class, system...'})
    )
    
    academic_session = forms.ModelChoiceField(
        label='Academic Session',
        queryset=None,
        required=False,
        widget=SelectWithDefault(default_label="All Sessions")
    )
    
    class_instance = forms.ModelChoiceField(
        label='Class',
        queryset=None,
        required=False,
        widget=SelectWithDefault(default_label="All Classes")
    )
    
    grading_system = forms.ModelChoiceField(
        label='Grading System',
        queryset=None,
        required=False,
        widget=SelectWithDefault(default_label="All Systems")
    )
    
    subject = forms.ModelChoiceField(
        label='Subject',
        queryset=None,
        required=False,
        widget=SelectWithDefault(default_label="All Subjects")
    )
    
    is_active = forms.ChoiceField(
        label='Status',
        choices=[
            ('', 'All'),
            ('true', 'Active'),
            ('false', 'Inactive')
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    is_default_for_class = forms.ChoiceField(
        label='Default Assignment',
        choices=[
            ('', 'All'),
            ('true', 'Default'),
            ('false', 'Not Default')
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
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
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")


# =============================================================================
# BULK OPERATIONS FORMS
# =============================================================================

class BulkResultEntryForm(BootstrapFormMixin, forms.Form):
    """Form for bulk result entry configuration"""
    
    examination = forms.ModelChoiceField(
        label='Examination',
        queryset=None,
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Select the examination to enter results for'
    )
    
    target_class = forms.ModelChoiceField(
        label='Class',
        queryset=None,
        required=False,
        widget=SelectWithDefault(default_label="All Classes"),
        help_text='Optional: Filter students by class'
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
            self.fields['examination'].queryset = Examination.objects.filter(
                status__in=['ONGOING', 'COMPLETED']
            ).select_related('subject', 'academic_session').order_by('-exam_date')
            
            self.fields['target_class'].queryset = Class.objects.filter(
                is_active=True
            ).select_related('academic_level').order_by('academic_level__order', 'name')
        except Exception as e:
            logger.error(f"Error setting querysets: {e}")


# =============================================================================
# UTILITY FUNCTIONS FOR FILTERS
# =============================================================================

def apply_examination_filters(queryset, form):
    """
    Apply filters from ExaminationFilterForm to a queryset.
    
    Usage in views:
        form = ExaminationFilterForm(request.GET)
        if form.is_valid():
            exams = apply_examination_filters(Examination.objects.all(), form)
    """
    if not form.is_valid():
        return queryset
    
    # Search query
    q = form.cleaned_data.get('q')
    if q:
        from django.db.models import Q
        queryset = queryset.filter(
            Q(name__icontains=q) |
            Q(code__icontains=q) |
            Q(description__icontains=q)
        )
    
    # Academic session filter
    academic_session = form.cleaned_data.get('academic_session')
    if academic_session:
        queryset = queryset.filter(academic_session=academic_session)
    
    # Exam category filter
    exam_category = form.cleaned_data.get('exam_category')
    if exam_category:
        queryset = queryset.filter(exam_category=exam_category)
    
    # Subject filter
    subject = form.cleaned_data.get('subject')
    if subject:
        queryset = queryset.filter(subject=subject)
    
    # Status filter
    status = form.cleaned_data.get('status')
    if status:
        queryset = queryset.filter(status=status)
    
    # Exam mode filter
    exam_mode = form.cleaned_data.get('exam_mode')
    if exam_mode:
        queryset = queryset.filter(exam_mode=exam_mode)
    
    # Date range filters
    exam_date_from = form.cleaned_data.get('exam_date_from')
    if exam_date_from:
        queryset = queryset.filter(exam_date__gte=exam_date_from)
    
    exam_date_to = form.cleaned_data.get('exam_date_to')
    if exam_date_to:
        queryset = queryset.filter(exam_date__lte=exam_date_to)
    
    return queryset


def apply_result_filters(queryset, form):
    """
    Apply filters from StudentExamResultFilterForm to a queryset.
    """
    if not form.is_valid():
        return queryset
    
    from django.db.models import Q
    
    # Search query
    q = form.cleaned_data.get('q')
    if q:
        queryset = queryset.filter(
            Q(student__first_name__icontains=q) |
            Q(student__last_name__icontains=q) |
            Q(student__admission_number__icontains=q)
        )
    
    # Examination filter
    examination = form.cleaned_data.get('examination')
    if examination:
        queryset = queryset.filter(examination=examination)
    
    # Status filter
    status = form.cleaned_data.get('status')
    if status:
        queryset = queryset.filter(status=status)
    
    # Boolean filters
    is_published = form.cleaned_data.get('is_published')
    if is_published == 'true':
        queryset = queryset.filter(is_published=True)
    elif is_published == 'false':
        queryset = queryset.filter(is_published=False)
    
    is_grade_locked = form.cleaned_data.get('is_grade_locked')
    if is_grade_locked == 'true':
        queryset = queryset.filter(is_grade_locked=True)
    elif is_grade_locked == 'false':
        queryset = queryset.filter(is_grade_locked=False)
    
    is_pass = form.cleaned_data.get('is_pass')
    if is_pass == 'true':
        queryset = queryset.filter(is_pass=True)
    elif is_pass == 'false':
        queryset = queryset.filter(is_pass=False)
    
    # Score range filters
    min_score = form.cleaned_data.get('min_score')
    if min_score is not None:
        queryset = queryset.filter(score__gte=min_score)
    
    max_score = form.cleaned_data.get('max_score')
    if max_score is not None:
        queryset = queryset.filter(score__lte=max_score)
    
    # Class filter
    class_instance = form.cleaned_data.get('class_instance')
    if class_instance:
        queryset = queryset.filter(
            student__class_enrollments__class_instance=class_instance,
            student__class_enrollments__is_active=True
        )
    
    return queryset