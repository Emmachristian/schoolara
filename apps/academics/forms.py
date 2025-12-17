# academics/forms.py

from django import forms
from django.core.exceptions import ValidationError
from .models import AcademicLevel, Subject, ClassRoom, Class, AcademicSession, Holiday, ClassSubject
from django.utils import timezone
from datetime import timedelta, date

# =============================================================================
# ACADEMIC SESSION FORMS (Enhanced)
# =============================================================================

# =============================================================================
# ACADEMIC SESSION FORMS (Enhanced)
# =============================================================================

class AcademicSessionForm(forms.ModelForm):
    """Enhanced form for creating and editing academic sessions with intelligent break detection"""
    
    auto_create_breaks = forms.BooleanField(
        label="Auto-create breaks",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text="Automatically create holiday records for breaks between sessions"
    )
    
    check_overlaps = forms.BooleanField(
        label="Check for overlaps",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text="Validate that this session doesn't overlap with existing sessions"
    )
    
    validate_sequence = forms.BooleanField(
        label="Validate Sequence",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text="Check that this session fits properly in the academic year sequence"
    )
    
    class Meta:
        model = AcademicSession
        fields = [
            'year_name', 'term_number', 'term_name', 'period_type',
            'start_date', 'end_date', 'is_current', 'is_active',
            'allows_promotion', 'registration_fee_required',
            'late_payment_penalty_rate', 'enrollment_deadline', 
            'late_enrollment_allowed'
        ]
        widgets = {
            'year_name': forms.TextInput(attrs={
                'placeholder': 'e.g., 2024-2025',
                'pattern': r'^(20\d{2})([\/-](20\d{2}))?$'
            }),
            'term_number': forms.NumberInput(attrs={'min': 1, 'max': 20}),
            'term_name': forms.TextInput(attrs={
                'placeholder': 'e.g., Term 1, Fall Semester'
            }),
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
            'enrollment_deadline': forms.DateInput(attrs={'type': 'date'}),
            'late_payment_penalty_rate': forms.NumberInput(attrs={
                'step': '0.01', 'min': '0', 'max': '100', 'placeholder': '0.00'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        
        help_texts = {
            'year_name': 'Academic year in format "YYYY-YYYY" or "YYYY"',
            'term_number': 'Position of this period within the year (adapts to school system)',
            'term_name': 'Name of the period (auto-generated if left empty)',
            'period_type': 'Type of academic period (auto-set from school configuration)',
            'late_payment_penalty_rate': 'Percentage penalty for late payments (e.g., 5.00 for 5%)',
            'is_active': 'Whether this session is active and available for operations',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Enhanced configuration based on school settings
        from utils.models import SchoolConfiguration
        config = SchoolConfiguration.get_cached_instance()
        if config:
            max_periods = config.get_period_count()
            self.fields['term_number'].widget.attrs['max'] = max_periods
            
            # Set default period_type from config
            if not self.instance.pk:
                self.fields['period_type'].initial = config.term_system
                self.fields['auto_create_breaks'].initial = config.auto_create_breaks
            
            # Enhanced help text for term_number
            system_display = config.get_term_system_display()
            period_type_name = config.get_period_type_name()
            self.fields['term_number'].help_text = (
                f'Position of this {period_type_name.lower()} within the year '
                f'(1 to {max_periods} for {system_display})'
            )
            
            # Add period name suggestions
            if not self.instance.pk:
                suggestions = []
                for i in range(1, min(max_periods + 1, 6)):  # Show first 5 suggestions
                    suggestions.append(config.get_period_name(i))
                
                if suggestions:
                    self.fields['term_name'].help_text = (
                        f'Suggestions: {", ".join(suggestions)}. Leave empty for auto-generation.'
                    )
        else:
            self.fields['term_number'].widget.attrs['max'] = 8
            self.fields['auto_create_breaks'].initial = True
        
        # Make term_name optional for auto-generation
        self.fields['term_name'].required = False
        
        # Add break impact information if editing existing session
        if self.instance.pk:
            self._add_break_impact_info()
    
    def _add_break_impact_info(self):
        """Add information about break impact for existing sessions"""
        try:
            # Get preceding and following breaks
            preceding_breaks = self.instance.preceding_breaks.all()
            following_breaks = self.instance.following_breaks.all()
            
            impact_info = []
            if preceding_breaks.exists():
                impact_info.append(f"{preceding_breaks.count()} preceding break(s)")
            if following_breaks.exists():
                impact_info.append(f"{following_breaks.count()} following break(s)")
            
            if impact_info:
                self.fields['auto_create_breaks'].help_text += f" (Currently has: {', '.join(impact_info)})"
        except Exception:
            pass
    
    def clean_term_number(self):
        """Enhanced term number validation with dynamic limits"""
        term_number = self.cleaned_data.get('term_number')
        if term_number is not None:
            from utils.models import SchoolConfiguration
            config = SchoolConfiguration.get_cached_instance()
            if config:
                if not config.validate_period_number(term_number):
                    system_display = config.get_term_system_display()
                    raise ValidationError(
                        f"Period number {term_number} is invalid for {system_display} "
                        f"system (max: {config.get_period_count()})"
                    )
            else:
                if term_number < 1 or term_number > 20:
                    raise ValidationError("Period number must be between 1 and 20")
        
        return term_number
    
    def clean(self):
        """Enhanced validation with break impact analysis, sequence checking, and is_active field logic"""
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        year_name = cleaned_data.get('year_name')
        term_number = cleaned_data.get('term_number')
        check_overlaps = cleaned_data.get('check_overlaps', True)
        validate_sequence = cleaned_data.get('validate_sequence', True)
        is_active = cleaned_data.get('is_active', True)
        is_current = cleaned_data.get('is_current', False)
        
        # Validate is_active and is_current relationship
        if is_current and not is_active:
            self.add_error('is_active', 'Current session must be active')
        
        # If making this session current, ensure no other session is current
        if is_current:
            existing_current = AcademicSession.objects.filter(is_current=True)
            if self.instance.pk:
                existing_current = existing_current.exclude(pk=self.instance.pk)
            
            if existing_current.exists():
                current_session = existing_current.first()
                self.add_error('is_current', 
                    f'Another session is already marked as current: {current_session.name}. '
                    'Only one session can be current at a time.'
                )
        
        # Enhanced date validation
        if start_date and end_date:
            if start_date > end_date:
                raise ValidationError('Start date cannot be after end date')
            
            # Check minimum session duration (at least 7 days)
            if (end_date - start_date).days < 7:
                raise ValidationError('Academic session must be at least 7 days long')
            
            # Check maximum reasonable session duration (e.g., 1 year)
            if (end_date - start_date).days > 365:
                self.add_error('end_date', 'Academic session cannot be longer than 365 days')
            
            # Check for overlaps with existing sessions if requested
            if check_overlaps:
                self._check_session_overlaps(start_date, end_date)
            
            # Enhanced break impact analysis
            if cleaned_data.get('auto_create_breaks'):
                self._analyze_break_impact(start_date, end_date)
            
            # Validate dates are reasonable (not too far in past or future)
            current_date = timezone.now().date()
            if start_date < current_date - timedelta(days=365*2):  # 2 years in past
                self.add_error('start_date', 'Start date cannot be more than 2 years in the past')
            
            if end_date > current_date + timedelta(days=365*3):  # 3 years in future
                self.add_error('end_date', 'End date cannot be more than 3 years in the future')
        
        # Enrollment deadline validation
        enrollment_deadline = cleaned_data.get('enrollment_deadline')
        if enrollment_deadline and start_date and end_date:
            if enrollment_deadline < start_date - timedelta(days=30):
                self.add_error('enrollment_deadline', 
                    'Enrollment deadline should not be more than 30 days before session starts')
            
            if enrollment_deadline > end_date:
                self.add_error('enrollment_deadline', 'Enrollment deadline cannot be after session ends')
        
        # Check for duplicate sessions
        if year_name and term_number:
            existing = AcademicSession.objects.filter(
                year_name=year_name,
                term_number=term_number
            )
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            
            if existing.exists():
                existing_session = existing.first()
                raise ValidationError(
                    f'A session for {year_name} Period {term_number} already exists: {existing_session.term_name}'
                )
        
        # Enhanced sequence validation
        if validate_sequence and year_name and term_number and start_date and end_date:
            self._validate_session_sequence(year_name, term_number, start_date, end_date)
        
        # Validate financial settings
        penalty_rate = cleaned_data.get('late_payment_penalty_rate')
        if penalty_rate is not None and (penalty_rate < 0 or penalty_rate > 100):
            self.add_error('late_payment_penalty_rate', 'Penalty rate must be between 0 and 100')
        
        # Validate that inactive sessions cannot have certain features
        if not is_active:
            if is_current:
                self.add_error('is_active', 'Current session cannot be inactive')
            
            allows_promotion = cleaned_data.get('allows_promotion', False)
            if allows_promotion:
                self.add_error('allows_promotion', 'Inactive sessions cannot allow promotion')
        
        # Auto-generate term name if not provided
        if not cleaned_data.get('term_name') and term_number:
            from utils.models import SchoolConfiguration
            config = SchoolConfiguration.get_cached_instance()
            if config:
                generated_name = config.get_period_name(term_number)
                if generated_name:
                    cleaned_data['term_name'] = generated_name
            
            # Fallback generation if config not available
            if not cleaned_data.get('term_name'):
                period_type = cleaned_data.get('period_type', 'term')
                period_types = {
                    'semester': 'Semester',
                    'quarter': 'Quarter',
                    'trimester': 'Trimester',
                    'module': 'Module',
                    'block': 'Block',
                    'yearlong': 'Year',
                    'intensive': 'Session'
                }
                period_name = period_types.get(period_type, 'Term')
                cleaned_data['term_name'] = f"{period_name} {term_number}"
        
        # Validate year name format more strictly
        if year_name:
            if '/' in year_name or '-' in year_name:
                # Multi-year format
                parts = year_name.replace('/', '-').split('-')
                if len(parts) != 2:
                    self.add_error('year_name', 
                        'Multi-year format must have exactly two years (e.g., "2024-2025")')
                else:
                    try:
                        start_year = int(parts[0])
                        end_year = int(parts[1])
                        if end_year != start_year + 1:
                            self.add_error('year_name', 
                                'Multi-year format must be consecutive years (e.g., "2024-2025")')
                        if start_year < 2000 or start_year > 2100:
                            self.add_error('year_name', 'Year must be between 2000 and 2100')
                    except ValueError:
                        self.add_error('year_name', 'Invalid year format. Use "YYYY-YYYY" or "YYYY"')
            else:
                # Single year format
                try:
                    year = int(year_name)
                    if year < 2000 or year > 2100:
                        self.add_error('year_name', 'Year must be between 2000 and 2100')
                except ValueError:
                    self.add_error('year_name', 'Invalid year format. Use "YYYY-YYYY" or "YYYY"')
        
        return cleaned_data
    
    def _check_session_overlaps(self, start_date, end_date):
        """Enhanced overlap checking with detailed feedback"""
        overlapping = AcademicSession.objects.filter(
            start_date__lt=end_date,
            end_date__gt=start_date
        )
        
        if self.instance.pk:
            overlapping = overlapping.exclude(pk=self.instance.pk)
        
        if overlapping.exists():
            overlapping_session = overlapping.first()
            overlap_days = min(end_date, overlapping_session.end_date) - max(start_date, overlapping_session.start_date)
            
            raise ValidationError(
                f'This session overlaps with existing session: {overlapping_session} '
                f'({overlapping_session.start_date} to {overlapping_session.end_date}) '
                f'by {overlap_days.days + 1} days'
            )
    
    def _analyze_break_impact(self, start_date, end_date):
        """Analyze how this session will impact existing breaks"""
        try:
            from .utils import analyze_break_gaps
            analysis = analyze_break_gaps(include_statistics=False)
            
            # Check if this session will create or affect breaks
            affected_breaks = []
            new_breaks = []
            
            for gap in analysis.get('gaps', []):
                gap_start = gap['start_date']
                gap_end = gap['end_date']
                
                # Check if session overlaps with gap
                if start_date <= gap_end and end_date >= gap_start:
                    if gap['break_exists']:
                        affected_breaks.append(gap)
                    else:
                        # This will create a new break
                        new_breaks.append(gap)
            
            # Store analysis results for potential use in template
            self._break_impact = {
                'affected_existing': len(affected_breaks),
                'will_create_new': len(new_breaks),
                'total_impact': len(affected_breaks) + len(new_breaks)
            }
                
        except Exception:
            pass  # Silently fail if analysis not available
    
    def _validate_session_sequence(self, year_name, term_number, start_date, end_date):
        """Validate session fits properly in academic year sequence"""
        try:
            # Get other sessions in the same year
            year_sessions = AcademicSession.objects.filter(
                year_name=year_name
            ).exclude(pk=self.instance.pk if self.instance.pk else None)
            
            # Check if term number sequence makes sense
            for session in year_sessions:
                # Sessions should generally be in chronological order by term number
                if session.term_number < term_number and session.start_date > start_date:
                    self.add_error('start_date', 
                        f'Start date seems out of sequence. {session.term_name} starts after this session.'
                    )
                
                elif session.term_number > term_number and session.start_date < start_date:
                    self.add_error('start_date', 
                        f'Start date seems out of sequence. {session.term_name} starts before this session.'
                    )
        
        except Exception:
            pass  # Silently fail validation if there's an error

# =============================================================================
# HOLIDAY FORMS (Enhanced)
# =============================================================================

class HolidayForm(forms.ModelForm):
    """Enhanced form for creating and editing school holidays with intelligent break detection"""
    
    create_break = forms.BooleanField(
        label="Create as Term Break",
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
            'onchange': 'toggleBreakMode(this.checked)'
        }),
        help_text="Automatically set holiday as a break between terms"
    )
    
    auto_detect_sessions = forms.BooleanField(
        label="Auto-detect Sessions",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text="Automatically find sessions before and after this break"
    )
    
    validate_against_config = forms.BooleanField(
        label="Validate Against School Config",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text="Check if break meets school's minimum duration requirements"
    )
    
    # Add gap suggestion field
    suggested_gap = forms.ChoiceField(
        label="Detected Gap",
        required=False,
        choices=[],
        widget=forms.Select(attrs={
            'class': 'form-select',
            'onchange': 'populateFromGap(this.value)'
        }),
        help_text="Select from automatically detected gaps between sessions"
    )
    
    class Meta:
        model = Holiday
        fields = [
            'name', 'holiday_type', 'break_type',
            'start_date', 'end_date', 'description',
            'academic_session', 'previous_session', 'next_session'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'Holiday name',
                'required': True
            }),
            'holiday_type': forms.Select(attrs={
                'onchange': 'toggleBreakFields(this.value)'
            }),
            'start_date': forms.DateInput(attrs={
                'type': 'date',
                'required': True,
                'onchange': 'detectAdjacentSessions()'
            }),
            'end_date': forms.DateInput(attrs={
                'type': 'date',
                'onchange': 'detectAdjacentSessions()'
            }),
            'description': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Optional description (auto-generated for breaks)'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Enhanced session choices with better organization
        sessions = AcademicSession.objects.all().order_by('-start_date', 'term_number')
        session_choices = [('', '---------')]
        
        # Group sessions by year for better UX
        current_year_sessions = []
        other_sessions = []
        current_year = date.today().year
        
        for session in sessions:
            session_display = f"{session.year_name} - {session.term_name} ({session.start_date} to {session.end_date})"
            if str(current_year) in session.year_name or str(current_year + 1) in session.year_name:
                current_year_sessions.append((session.id, session_display))
            else:
                other_sessions.append((session.id, session_display))
        
        if current_year_sessions:
            session_choices.append(('Current Academic Year', current_year_sessions))
        if other_sessions:
            session_choices.append(('Other Years', other_sessions))
        
        self.fields['academic_session'].choices = session_choices
        self.fields['previous_session'].choices = session_choices
        self.fields['next_session'].choices = session_choices
        
        # Add break gap analysis for new holidays
        if not self.instance.pk:
            self._populate_gap_suggestions()
    
    def _populate_gap_suggestions(self):
        """Populate form with detected gaps for quick break creation"""
        try:
            from .utils import analyze_break_gaps
            analysis = analyze_break_gaps(include_statistics=False)
            missing_breaks = analysis.get('missing_breaks', [])
            
            if missing_breaks:
                gap_choices = [('', 'Select a detected gap (optional)')]
                for i, gap in enumerate(missing_breaks[:5]):  # Show top 5
                    duration_text = f"{gap['duration_days']} days"
                    previous_session = gap['previous_session']['name']
                    choice_text = f"{gap['start_date']} to {gap['end_date']} ({duration_text}) - After {previous_session}"
                    gap_choices.append((i, choice_text))
                
                self.fields['suggested_gap'].choices = gap_choices
                
                # Store gap data for JavaScript use
                self._gap_data = missing_breaks[:5]
                
                # Add helpful hint
                self.fields['suggested_gap'].help_text += f" ({len(missing_breaks)} gaps detected)"
        except Exception:
            pass  # Silently fail if gap detection not available
    
    def clean(self):
        """Enhanced validation with gap analysis and school config checking"""
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        holiday_type = cleaned_data.get('holiday_type')
        validate_config = cleaned_data.get('validate_against_config', True)
        
        # Basic date validation
        if start_date and end_date and start_date > end_date:
            raise ValidationError('End date cannot be before start date')
        
        # Enhanced validation for breaks
        if holiday_type == 'BREAK' and start_date and end_date:
            duration = (end_date - start_date).days + 1
            
            # Check against school configuration
            from utils.models import SchoolConfiguration
            if validate_config:
                config = SchoolConfiguration.get_cached_instance()
                if config and duration < config.minimum_break_days:
                    self.add_error('end_date', 
                        f'Break duration ({duration} days) is less than school '
                        f'minimum ({config.minimum_break_days} days)'
                    )
            
            # Auto-detect adjacent sessions if requested
            if cleaned_data.get('auto_detect_sessions'):
                self._auto_detect_adjacent_sessions(start_date, end_date, cleaned_data)
        
        return cleaned_data
    
    def _auto_detect_adjacent_sessions(self, start_date, end_date, cleaned_data):
        """Automatically detect sessions before and after this break"""
        try:
            # Find session that ends just before this break
            previous_session = AcademicSession.objects.filter(
                end_date__lt=start_date
            ).order_by('-end_date').first()
            
            # Find session that starts just after this break
            next_session = AcademicSession.objects.filter(
                start_date__gt=end_date
            ).order_by('start_date').first()
            
            if previous_session and not cleaned_data.get('previous_session'):
                cleaned_data['previous_session'] = previous_session
            
            if next_session and not cleaned_data.get('next_session'):
                cleaned_data['next_session'] = next_session
                
        except Exception:
            pass  # Silently fail if detection not available
    
# =============================================================================
# ACADEMIC LEVEL FORM
# =============================================================================

class AcademicLevelForm(forms.ModelForm):
    """Form for creating and updating academic levels"""

    class Meta:
        model = AcademicLevel
        fields = [
            'name',
            'code',
            'description',
            'order',
            'next_level',
            'has_sections',
            'is_active',
            'is_graduation_level',
        ]

        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'order': forms.NumberInput(attrs={'min': 1, 'class': 'form-control'}),
            'next_level': forms.Select(attrs={'class': 'form-select'}),
            'has_sections': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_graduation_level': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


# =============================================================================
# SUBJECT FORM
# =============================================================================

class SubjectForm(forms.ModelForm):
    """Form for creating and updating subjects"""

    prerequisites = forms.ModelMultipleChoiceField(
        queryset=Subject.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        help_text="Select subjects that must be completed before taking this subject",
    )

    applicable_levels = forms.ModelMultipleChoiceField(
        queryset=AcademicLevel.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        help_text="Select academic levels where this subject is offered",
    )

    class Meta:
        model = Subject
        fields = [
            'name',
            'abbreviation',
            'code',
            'description',
            'subject_type',
            'credit_hours',
            'prerequisites',
            'department',
            'is_active',
            'is_compulsory',
            'pass_mark',
            'applicable_levels',
            'difficulty_level',
            'weight_factor',
            'textbook_required',
            'recommended_textbooks',
            'required_materials',
        ]

        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'credit_hours': forms.NumberInput(attrs={'step': '0.5', 'min': '0.5', 'max': '20'}),
            'pass_mark': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'max': '100'}),
            'weight_factor': forms.NumberInput(attrs={'step': '0.01', 'min': '0.5', 'max': '3'}),
            'recommended_textbooks': forms.Textarea(attrs={'rows': 3}),
            'required_materials': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Prerequisites: active subjects, exclude self
        prerequisites_qs = Subject.objects.filter(is_active=True)
        if self.instance and self.instance.pk:
            prerequisites_qs = prerequisites_qs.exclude(pk=self.instance.pk)
        self.fields['prerequisites'].queryset = prerequisites_qs

        # Academic levels
        self.fields['applicable_levels'].queryset = (
            AcademicLevel.objects.filter(is_active=True).order_by('order')
        )

        # Department
        from hr.models import Department
        self.fields['department'].queryset = Department.objects.filter(is_active=True)

        # Required fields
        for field in ['name', 'code', 'subject_type']:
            self.fields[field].required = True

    # -------------------------------------------------------------------------
    # FIELD VALIDATION
    # -------------------------------------------------------------------------

    def clean_name(self):
        name = self.cleaned_data.get('name')
        if not name:
            return name

        existing = Subject.objects.filter(name__iexact=name)
        if self.instance and self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)

        if existing.exists():
            raise ValidationError("A subject with this name already exists.")

        return name.strip()

    def clean_code(self):
        code = self.cleaned_data.get('code')
        if not code:
            return code

        code = code.upper().strip()
        existing = Subject.objects.filter(code=code)
        if self.instance and self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)

        if existing.exists():
            raise ValidationError("A subject with this code already exists.")

        return code

    def clean_abbreviation(self):
        abbreviation = self.cleaned_data.get('abbreviation')
        if not abbreviation:
            return abbreviation

        abbreviation = abbreviation.upper().strip()
        existing = Subject.objects.filter(abbreviation=abbreviation)
        if self.instance and self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)

        if existing.exists():
            raise ValidationError("A subject with this abbreviation already exists.")

        return abbreviation

    # -------------------------------------------------------------------------
    # FORM-LEVEL VALIDATION
    # -------------------------------------------------------------------------

    def clean(self):
        cleaned_data = super().clean()

        prerequisites = cleaned_data.get('prerequisites')
        if prerequisites and self.instance and self.instance.pk:
            for prereq in prerequisites:
                if self.instance in prereq.prerequisites.all():
                    raise ValidationError({
                        'prerequisites': f"Circular prerequisite detected with subject: {prereq.name}"
                    })

        return cleaned_data
    
# =============================================================================
# CLASSROOM FORM
# =============================================================================

class ClassRoomForm(forms.ModelForm):
    """Form for creating and updating classrooms"""
    
    class Meta:
        model = ClassRoom
        fields = [
            'name', 'room_number', 'building', 'floor', 'wing', 'capacity',
            'room_type', 'has_projector', 'has_computer', 'has_air_conditioning',
            'has_whiteboard', 'has_blackboard', 'has_smart_board', 'has_internet',
            'has_sound_system', 'specialized_equipment', 'is_accessible',
            'accessibility_features', 'is_bookable', 'requires_approval',
            'last_maintenance_date', 'safety_inspection_date', 'is_active'
        ]
        
        widgets = {
            'capacity': forms.NumberInput(attrs={'min': '1'}),
            'specialized_equipment': forms.Textarea(attrs={'rows': 3}),
            'accessibility_features': forms.Textarea(attrs={'rows': 2}),
            'last_maintenance_date': forms.DateInput(attrs={'type': 'date'}),
            'safety_inspection_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Required fields
        required_fields = ['name', 'room_number', 'capacity']
        for field in required_fields:
            if field in self.fields:
                self.fields[field].required = True

    def clean_name(self):
        return self.clean_name_field('name')

    def clean_room_number(self):
        room_number = self.cleaned_data.get('room_number')
        if room_number:
            room_number = room_number.strip().upper()
            
            # Check uniqueness
            existing = ClassRoom.objects.filter(room_number=room_number)
            if self.instance and self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            
            if existing.exists():
                raise ValidationError("A classroom with this room number already exists.")
        
        return room_number
    
# =============================================================================
# CLASS FORM
# =============================================================================
    
class ClassForm(forms.ModelForm):
    """Form for creating and updating classes"""

    class Meta:
        model = Class
        fields = [
            'academic_level',
            'section',
            'academic_session',
            'class_teacher',
            'assistant_teacher',
            'classroom',
            'max_students',
            'class_schedule',
            'start_time',
            'end_time',
            'class_motto',
            'class_colors',
            'is_active',
        ]

        widgets = {
            'class_schedule': forms.Textarea(attrs={'rows': 3}),
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time'}),
            'max_students': forms.NumberInput(attrs={'min': '1'}),
            'class_motto': forms.TextInput(attrs={'placeholder': 'Class motto or slogan'}),
            'class_colors': forms.TextInput(attrs={'placeholder': 'e.g., Blue and White'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Academic levels
        self.fields['academic_level'].queryset = (
            AcademicLevel.objects.filter(is_active=True).order_by('order')
        )

        # Academic sessions
        self.fields['academic_session'].queryset = (
            AcademicSession.objects.all().order_by('-start_date')
        )

        # Classrooms
        self.fields['classroom'].queryset = (
            ClassRoom.objects.filter(is_active=True).order_by('building', 'room_number')
        )

        # Teachers
        from hr.models import Teacher
        teacher_qs = Teacher.objects.filter(is_active=True)
        self.fields['class_teacher'].queryset = teacher_qs
        self.fields['assistant_teacher'].queryset = teacher_qs

        # Set current academic session by default (new records only)
        if not self.instance.pk:
            current_session = AcademicSession.get_current()
            if current_session:
                self.fields['academic_session'].initial = current_session

        # Required fields
        for field in ['academic_level', 'academic_session']:
            self.fields[field].required = True

    # -------------------------------------------------------------------------
    # FORM-LEVEL VALIDATION
    # -------------------------------------------------------------------------

    def clean(self):
        cleaned_data = super().clean()

        academic_level = cleaned_data.get('academic_level')
        section = cleaned_data.get('section')
        academic_session = cleaned_data.get('academic_session')
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        class_teacher = cleaned_data.get('class_teacher')
        assistant_teacher = cleaned_data.get('assistant_teacher')

        # Section rules
        if academic_level and academic_level.has_sections and not section:
            raise ValidationError({'section': 'Section is required for this academic level.'})

        if academic_level and not academic_level.has_sections and section:
            raise ValidationError({'section': 'This academic level does not use sections.'})

        # Time validation
        if start_time and end_time and start_time >= end_time:
            raise ValidationError({'end_time': 'End time must be after start time.'})

        # Teacher assignment
        if class_teacher and assistant_teacher and class_teacher == assistant_teacher:
            raise ValidationError({
                'assistant_teacher': 'Assistant teacher cannot be the same as class teacher.'
            })

        # Prevent duplicate classes per session
        if academic_level and academic_session:
            existing = Class.objects.filter(
                academic_level=academic_level,
                section=section,
                academic_session=academic_session,
            )

            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)

            if existing.exists():
                raise ValidationError(
                    'A class with this academic level, section, and session already exists.'
                )

        return cleaned_data
    
# =============================================================================
# CLASS SUBJECT FORM
# =============================================================================

class ClassSubjectForm(forms.ModelForm):
    """Form for assigning subjects to classes"""

    class Meta:
        model = ClassSubject
        fields = [
            'class_instance',
            'subject',
            'teacher',
            'is_optional',
            'hours_per_week',
            'total_hours',
            'schedule_days',
            'preferred_periods',
            'syllabus',
            'learning_objectives',
            'assessment_criteria',
            'continuous_assessment_weight',
            'final_exam_weight',
            'textbook',
            'reference_materials',
            'required_equipment',
            'is_active',
        ]

        widgets = {
            'hours_per_week': forms.NumberInput(attrs={'min': '1'}),
            'total_hours': forms.NumberInput(attrs={'min': '0'}),
            'syllabus': forms.Textarea(attrs={'rows': 4}),
            'learning_objectives': forms.Textarea(attrs={'rows': 3}),
            'assessment_criteria': forms.Textarea(attrs={'rows': 3}),
            'continuous_assessment_weight': forms.NumberInput(
                attrs={'step': '0.01', 'min': '0', 'max': '100'}
            ),
            'final_exam_weight': forms.NumberInput(
                attrs={'step': '0.01', 'min': '0', 'max': '100'}
            ),
            'reference_materials': forms.Textarea(attrs={'rows': 2}),
            'required_equipment': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Active classes
        self.fields['class_instance'].queryset = Class.objects.filter(is_active=True)

        # Active subjects
        self.fields['subject'].queryset = Subject.objects.filter(is_active=True)

        # Active teachers
        from hr.models import Teacher
        self.fields['teacher'].queryset = Teacher.objects.filter(is_active=True)

        # Make some fields required
        required_fields = ['class_instance', 'subject', 'teacher', 'hours_per_week']
        for field in required_fields:
            if field in self.fields:
                self.fields[field].required = True

    def clean(self):
        cleaned_data = super().clean()
        hours_per_week = cleaned_data.get('hours_per_week')
        total_hours = cleaned_data.get('total_hours')
        ca_weight = cleaned_data.get('continuous_assessment_weight')
        exam_weight = cleaned_data.get('final_exam_weight')

        # Validate hours
        if hours_per_week and hours_per_week <= 0:
            raise ValidationError({'hours_per_week': 'Hours per week must be greater than zero.'})

        if total_hours is not None and total_hours < 0:
            raise ValidationError({'total_hours': 'Total hours cannot be negative.'})

        # Validate assessment weights
        if ca_weight is not None and exam_weight is not None:
            total_weight = ca_weight + exam_weight
            if total_weight != 100:
                raise ValidationError('Continuous assessment and final exam weights must sum to 100.')

        return cleaned_data

