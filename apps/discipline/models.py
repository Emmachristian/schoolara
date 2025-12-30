# discipline/models.py

from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import Q
from datetime import datetime
import logging

from utils.models import BaseModel
from students.models import Student
from schoolara.managers import SchoolManager

logger = logging.getLogger(__name__)


# =============================================================================
# DISCIPLINARY MODELS
# =============================================================================

class DisciplinaryRecord(BaseModel):
    """Enhanced model for tracking student disciplinary actions"""
    
    INCIDENT_TYPE_CHOICES = [
        ('tardiness', 'Tardiness'),
        ('absence', 'Unexcused Absence'),
        ('disrespect', 'Disrespect to Staff'),
        ('bullying', 'Bullying'),
        ('fighting', 'Fighting'),
        ('academic_dishonesty', 'Academic Dishonesty'),
        ('inappropriate_behavior', 'Inappropriate Behavior'),
        ('dress_code', 'Dress Code Violation'),
        ('technology_misuse', 'Technology Misuse'),
        ('vandalism', 'Vandalism'),
        ('substance_abuse', 'Substance Abuse'),
        ('theft', 'Theft'),
        ('insubordination', 'Insubordination'),
        ('disruption', 'Classroom Disruption'),
        ('truancy', 'Truancy'),
        ('harassment', 'Harassment'),
        ('inappropriate_language', 'Inappropriate Language'),
        ('safety_violation', 'Safety Violation'),
        ('property_damage', 'Property Damage'),
        ('other', 'Other'),
    ]
    
    ACTION_TAKEN_CHOICES = [
        ('verbal_warning', 'Verbal Warning'),
        ('written_warning', 'Written Warning'),
        ('detention', 'Detention'),
        ('in_school_suspension', 'In-School Suspension'),
        ('out_of_school_suspension', 'Out-of-School Suspension'),
        ('expulsion', 'Expulsion'),
        ('counseling', 'Counseling Required'),
        ('parent_conference', 'Parent Conference'),
        ('community_service', 'Community Service'),
        ('behavioral_contract', 'Behavioral Contract'),
        ('loss_of_privileges', 'Loss of Privileges'),
        ('restitution', 'Restitution Required'),
        ('referral_external', 'External Referral'),
        ('mentoring', 'Mentoring Program'),
        ('probation', 'Academic/Behavioral Probation'),
        ('no_action', 'No Action Taken'),
        ('other', 'Other'),
    ]
    
    SEVERITY_LEVEL_CHOICES = [
        ('minor', 'Minor'),
        ('moderate', 'Moderate'),
        ('major', 'Major'),
        ('severe', 'Severe'),
    ]
    
    RECORD_STATUS_CHOICES = [
        ('reported', 'Reported'),
        ('investigating', 'Under Investigation'),
        ('action_pending', 'Action Pending'),
        ('action_taken', 'Action Taken'),
        ('resolved', 'Resolved'),
        ('appealed', 'Under Appeal'),
        ('dismissed', 'Dismissed'),
    ]
    
    NOTIFICATION_METHOD_CHOICES = [
        ('phone', 'Phone Call'),
        ('email', 'Email'),
        ('letter', 'Letter'),
        ('in_person', 'In Person'),
        ('sms', 'SMS'),
        ('multiple', 'Multiple Methods'),
    ]
    
    APPEAL_OUTCOME_CHOICES = [
        ('upheld', 'Upheld'),
        ('modified', 'Modified'),
        ('overturned', 'Overturned'),
        ('pending', 'Pending'),
    ]
    
    # -------------------------------------------------------------------------
    # CORE RELATIONSHIPS
    # -------------------------------------------------------------------------
    
    student = models.ForeignKey(
        Student,
        verbose_name="Student",
        on_delete=models.CASCADE,
        related_name='disciplinary_records'
    )
    
    academic_session = models.ForeignKey(
        'core.FiscalPeriod',
        verbose_name="Academic Session",
        on_delete=models.CASCADE,
        related_name='disciplinary_records',
        help_text="Academic session when incident occurred"
    )
    
    # -------------------------------------------------------------------------
    # INCIDENT DETAILS
    # -------------------------------------------------------------------------
    
    incident_number = models.CharField(
        "Incident Number",
        max_length=20,
        unique=True,
        db_index=True,
        help_text="Unique identifier for this incident"
    )
    
    incident_date = models.DateField("Incident Date", db_index=True)
    incident_time = models.TimeField("Incident Time", null=True, blank=True)
    
    incident_type = models.CharField(
        "Incident Type",
        max_length=25,
        choices=INCIDENT_TYPE_CHOICES,
        db_index=True
    )
    
    severity_level = models.CharField(
        "Severity Level",
        max_length=10,
        choices=SEVERITY_LEVEL_CHOICES,
        default='minor',
        db_index=True
    )
    
    incident_description = models.TextField(
        "Incident Description",
        help_text="Detailed description of what happened"
    )
    
    location = models.CharField("Location", max_length=100, blank=True)
    
    # -------------------------------------------------------------------------
    # ADDITIONAL INCIDENT CONTEXT
    # -------------------------------------------------------------------------
    
    class_period = models.CharField(
        "Class Period",
        max_length=50,
        blank=True,
        help_text="Class or period when incident occurred"
    )
    
    related_subject = models.ForeignKey(
        'academics.Subject',
        verbose_name="Related Subject",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Subject/class where incident occurred"
    )
    
    # -------------------------------------------------------------------------
    # MULTIPLE STUDENTS INVOLVED
    # -------------------------------------------------------------------------
    
    other_students_involved = models.ManyToManyField(
        Student,
        verbose_name="Other Students Involved",
        blank=True,
        related_name='involved_disciplinary_records'
    )
    
    # -------------------------------------------------------------------------
    # REPORTING AND INVESTIGATION
    # -------------------------------------------------------------------------
    
    reported_by_id = models.CharField(
        "Reported By ID",
        max_length=50,
        null=True,
        blank=True,
        help_text="User ID who reported this incident"
    )
    
    report_date = models.DateTimeField(
        "Report Date",
        auto_now_add=True,
        db_index=True
    )
    
    witnesses = models.TextField("Witnesses", blank=True)
    
    staff_witnesses = models.ManyToManyField(
        'hr.Staff',
        verbose_name="Staff Witnesses",
        blank=True,
        related_name='witnessed_incidents'
    )
    
    # -------------------------------------------------------------------------
    # INVESTIGATION DETAILS
    # -------------------------------------------------------------------------
    
    investigated_by_id = models.CharField(
        "Investigated By ID",
        max_length=50,
        null=True,
        blank=True,
        help_text="User ID who investigated this incident"
    )
    
    investigation_date = models.DateTimeField(
        "Investigation Date",
        null=True,
        blank=True
    )
    
    investigation_notes = models.TextField(
        "Investigation Notes",
        blank=True
    )
    
    # -------------------------------------------------------------------------
    # EVIDENCE AND DOCUMENTATION
    # -------------------------------------------------------------------------
    
    evidence_collected = models.TextField(
        "Evidence Collected",
        blank=True
    )
    
    student_statement = models.TextField(
        "Student Statement",
        blank=True,
        help_text="Student's account of the incident"
    )
    
    # -------------------------------------------------------------------------
    # ACTION AND CONSEQUENCES
    # -------------------------------------------------------------------------
    
    action_taken = models.CharField(
        "Primary Action Taken",
        max_length=25,
        choices=ACTION_TAKEN_CHOICES,
        db_index=True
    )
    
    # Support for multiple actions
    additional_actions = models.JSONField(
        "Additional Actions",
        blank=True,
        default=list,
        help_text="List of additional actions taken"
    )
    
    action_description = models.TextField(
        "Action Description",
        help_text="Detailed description of actions taken"
    )
    
    # -------------------------------------------------------------------------
    # TIMING FOR ACTIONS (ESPECIALLY SUSPENSIONS)
    # -------------------------------------------------------------------------
    
    action_start_date = models.DateField(
        "Action Start Date",
        null=True,
        blank=True,
        db_index=True,
        help_text="Date when action begins (e.g., suspension start)"
    )
    
    action_end_date = models.DateField(
        "Action End Date",
        null=True,
        blank=True,
        db_index=True,
        help_text="Date when action ends (e.g., suspension end)"
    )
    
    # -------------------------------------------------------------------------
    # WHO AUTHORIZED THE ACTION
    # -------------------------------------------------------------------------
    
    action_authorized_by_id = models.CharField(
        "Action Authorized By ID",
        max_length=50,
        null=True,
        blank=True,
        help_text="User ID who authorized the disciplinary action"
    )
    
    authorization_date = models.DateTimeField(
        "Authorization Date",
        null=True,
        blank=True
    )
    
    # -------------------------------------------------------------------------
    # PARENT/GUARDIAN COMMUNICATION
    # -------------------------------------------------------------------------
    
    parent_notified = models.BooleanField("Parent Notified", default=False)
    
    parent_notification_date = models.DateTimeField(
        "Parent Notification Date",
        null=True,
        blank=True
    )
    
    notification_method = models.CharField(
        "Notification Method",
        max_length=20,
        choices=NOTIFICATION_METHOD_CHOICES,
        blank=True
    )
    
    notified_by_id = models.CharField(
        "Notified By ID",
        max_length=50,
        null=True,
        blank=True,
        help_text="User ID who notified the parent"
    )
    
    parent_response = models.TextField(
        "Parent Response",
        blank=True,
        help_text="Parent's response to notification"
    )
    
    parent_meeting_scheduled = models.BooleanField(
        "Parent Meeting Scheduled",
        default=False
    )
    
    parent_meeting_date = models.DateTimeField(
        "Parent Meeting Date",
        null=True,
        blank=True
    )
    
    # -------------------------------------------------------------------------
    # FOLLOW-UP AND MONITORING
    # -------------------------------------------------------------------------
    
    follow_up_required = models.BooleanField("Follow-up Required", default=False)
    follow_up_date = models.DateField("Follow-up Date", null=True, blank=True)
    follow_up_notes = models.TextField("Follow-up Notes", blank=True)
    follow_up_completed = models.BooleanField("Follow-up Completed", default=False)
    
    # -------------------------------------------------------------------------
    # MONITORING AND PROGRESS
    # -------------------------------------------------------------------------
    
    monitoring_required = models.BooleanField(
        "Ongoing Monitoring Required",
        default=False
    )
    
    monitoring_period_days = models.PositiveIntegerField(
        "Monitoring Period (Days)",
        null=True,
        blank=True
    )
    
    progress_updates = models.TextField(
        "Progress Updates",
        blank=True
    )
    
    # -------------------------------------------------------------------------
    # RESOLUTION AND CLOSURE
    # -------------------------------------------------------------------------
    
    record_status = models.CharField(
        "Record Status",
        max_length=15,
        choices=RECORD_STATUS_CHOICES,
        default='reported',
        db_index=True
    )
    
    is_resolved = models.BooleanField("Is Resolved", default=False, db_index=True)
    resolution_date = models.DateTimeField("Resolution Date", null=True, blank=True)
    resolution_notes = models.TextField("Resolution Notes", blank=True)
    
    resolved_by_id = models.CharField(
        "Resolved By ID",
        max_length=50,
        null=True,
        blank=True,
        help_text="User ID who resolved this record"
    )
    
    # -------------------------------------------------------------------------
    # APPEAL INFORMATION
    # -------------------------------------------------------------------------
    
    appealed = models.BooleanField("Appealed", default=False)
    appeal_date = models.DateTimeField("Appeal Date", null=True, blank=True)
    appeal_notes = models.TextField("Appeal Notes", blank=True)
    appeal_outcome = models.CharField(
        "Appeal Outcome",
        max_length=20,
        choices=APPEAL_OUTCOME_CHOICES,
        blank=True
    )
    
    # -------------------------------------------------------------------------
    # PREVENTION AND LEARNING
    # -------------------------------------------------------------------------
    
    preventive_measures = models.TextField(
        "Preventive Measures",
        blank=True,
        help_text="Measures put in place to prevent similar incidents"
    )
    
    lessons_learned = models.TextField(
        "Lessons Learned",
        blank=True,
        help_text="Key insights from this incident"
    )
    
    # -------------------------------------------------------------------------
    # BEHAVIORAL INTERVENTION PLAN
    # -------------------------------------------------------------------------
    
    intervention_plan = models.TextField(
        "Intervention Plan",
        blank=True,
        help_text="Specific interventions or support for student"
    )
    
    counseling_recommended = models.BooleanField(
        "Counseling Recommended",
        default=False
    )
    
    counseling_completed = models.BooleanField(
        "Counseling Completed",
        default=False
    )
    
    # Use SchoolManager for automatic database routing
    objects = SchoolManager()
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Disciplinary Record"
        verbose_name_plural = "Disciplinary Records"
        ordering = ['-incident_date', '-report_date']
        indexes = [
            models.Index(fields=['student', 'incident_date']),
            models.Index(fields=['incident_type']),
            models.Index(fields=['severity_level']),
            models.Index(fields=['record_status']),
            models.Index(fields=['is_resolved']),
            models.Index(fields=['action_taken']),
            models.Index(fields=['academic_session']),
            models.Index(fields=['incident_number']),
            models.Index(fields=['action_start_date', 'action_end_date']),
            models.Index(fields=['student', 'record_status']),
            models.Index(fields=['incident_date', 'severity_level']),
        ]
        
        constraints = [
            models.CheckConstraint(
                check=Q(action_end_date__gte=models.F('action_start_date')) | Q(action_end_date__isnull=True),
                name='action_end_after_start'
            ),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.incident_number} - {self.student.get_full_name()} - {self.get_incident_type_display()}"
    
    # -------------------------------------------------------------------------
    # SAVE METHOD
    # -------------------------------------------------------------------------
    
    def save(self, *args, **kwargs):
        """Generate incident number if not provided"""
        if not self.incident_number:
            self.incident_number = self.generate_incident_number()
        super().save(*args, **kwargs)
    
    # -------------------------------------------------------------------------
    # VALIDATION METHODS
    # -------------------------------------------------------------------------
    
    def clean(self):
        """Validate disciplinary record"""
        super().clean()
        errors = {}
        
        # Validate action dates
        if self.action_start_date and self.action_end_date:
            if self.action_end_date < self.action_start_date:
                errors['action_end_date'] = "End date cannot be before start date"
        
        # Validate incident date is not in future
        if self.incident_date and self.incident_date > timezone.now().date():
            errors['incident_date'] = "Incident date cannot be in the future"
        
        # Validate parent notification
        if self.parent_notified and not self.parent_notification_date:
            errors['parent_notification_date'] = "Notification date required when parent is notified"
        
        # Validate resolution
        if self.is_resolved and not self.resolution_date:
            errors['resolution_date'] = "Resolution date required when record is resolved"
        
        # Validate follow-up
        if self.follow_up_required and not self.follow_up_date:
            errors['follow_up_date'] = "Follow-up date required when follow-up is needed"
        
        if errors:
            raise ValidationError(errors)
    
    # -------------------------------------------------------------------------
    # HELPER METHODS - NUMBER GENERATION
    # -------------------------------------------------------------------------
    
    def generate_incident_number(self):
        """Generate unique incident number"""
        # Format: DIS-YYYY-NNNNNN (e.g., DIS-2024-000001)
        year = self.incident_date.year if self.incident_date else datetime.now().year
        
        # Get the last incident number for this year
        last_record = DisciplinaryRecord.objects.filter(
            incident_number__startswith=f'DIS-{year}-'
        ).order_by('-incident_number').first()
        
        if last_record:
            last_num = int(last_record.incident_number.split('-')[-1])
            new_num = last_num + 1
        else:
            new_num = 1
        
        return f'DIS-{year}-{new_num:06d}'
    
    # -------------------------------------------------------------------------
    # HELPER METHODS - DISPLAY
    # -------------------------------------------------------------------------
    
    def get_severity_color(self):
        """Get color class for severity level"""
        colors = {
            'minor': 'info',
            'moderate': 'warning',
            'major': 'danger',
            'severe': 'dark'
        }
        return colors.get(self.severity_level, 'secondary')
    
    def get_severity_badge_class(self):
        """Get Bootstrap badge class for severity level"""
        return f"badge-{self.get_severity_color()}"
    
    def get_status_color(self):
        """Get color class for record status"""
        colors = {
            'reported': 'info',
            'investigating': 'warning',
            'action_pending': 'warning',
            'action_taken': 'primary',
            'resolved': 'success',
            'appealed': 'secondary',
            'dismissed': 'muted'
        }
        return colors.get(self.record_status, 'secondary')
    
    def get_status_badge_class(self):
        """Get Bootstrap badge class for status"""
        return f"badge-{self.get_status_color()}"
    
    def get_action_badge_class(self):
        """Get Bootstrap badge class for action type"""
        action_colors = {
            'verbal_warning': 'info',
            'written_warning': 'info',
            'detention': 'warning',
            'in_school_suspension': 'warning',
            'out_of_school_suspension': 'danger',
            'expulsion': 'dark',
            'counseling': 'primary',
            'parent_conference': 'primary',
            'community_service': 'warning',
            'behavioral_contract': 'warning',
            'loss_of_privileges': 'warning',
            'restitution': 'warning',
            'referral_external': 'primary',
            'mentoring': 'success',
            'probation': 'danger',
            'no_action': 'secondary',
            'other': 'secondary',
        }
        color = action_colors.get(self.action_taken, 'secondary')
        return f"badge-{color}"
    
    # -------------------------------------------------------------------------
    # HELPER METHODS - USER RETRIEVAL
    # -------------------------------------------------------------------------
    
    def get_reported_by_user(self):
        """Get the user who reported this incident"""
        if not self.reported_by_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            return User.objects.using('default').get(id=self.reported_by_id)
        except Exception as e:
            logger.error(f"Error fetching reported_by user: {e}")
            return None
    
    def get_investigated_by_user(self):
        """Get the user who investigated this incident"""
        if not self.investigated_by_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            return User.objects.using('default').get(id=self.investigated_by_id)
        except Exception as e:
            logger.error(f"Error fetching investigated_by user: {e}")
            return None
    
    def get_action_authorized_by_user(self):
        """Get the user who authorized the action"""
        if not self.action_authorized_by_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            return User.objects.using('default').get(id=self.action_authorized_by_id)
        except Exception as e:
            logger.error(f"Error fetching action_authorized_by user: {e}")
            return None
    
    def get_notified_by_user(self):
        """Get the user who notified the parent"""
        if not self.notified_by_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            return User.objects.using('default').get(id=self.notified_by_id)
        except Exception as e:
            logger.error(f"Error fetching notified_by user: {e}")
            return None
    
    def get_resolved_by_user(self):
        """Get the user who resolved this record"""
        if not self.resolved_by_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            return User.objects.using('default').get(id=self.resolved_by_id)
        except Exception as e:
            logger.error(f"Error fetching resolved_by user: {e}")
            return None
    
    # -------------------------------------------------------------------------
    # PROPERTIES
    # -------------------------------------------------------------------------
    
    @property
    def reported_by_name(self):
        """Get name of user who reported incident"""
        user = self.get_reported_by_user()
        if user:
            return user.get_full_name() or user.username
        return "Unknown"
    
    @property
    def investigated_by_name(self):
        """Get name of user who investigated incident"""
        user = self.get_investigated_by_user()
        if user:
            return user.get_full_name() or user.username
        return "Not Investigated"
    
    @property
    def action_authorized_by_name(self):
        """Get name of user who authorized action"""
        user = self.get_action_authorized_by_user()
        if user:
            return user.get_full_name() or user.username
        return "Unknown"
    
    @property
    def resolved_by_name(self):
        """Get name of user who resolved record"""
        user = self.get_resolved_by_user()
        if user:
            return user.get_full_name() or user.username
        return "Not Resolved"
    
    @property
    def is_active_suspension(self):
        """Check if this is an active suspension"""
        if self.action_taken not in ['in_school_suspension', 'out_of_school_suspension']:
            return False
        
        if not self.action_start_date or not self.action_end_date:
            return False
        
        today = timezone.now().date()
        return self.action_start_date <= today <= self.action_end_date
    
    @property
    def days_until_action_end(self):
        """Calculate days until action ends"""
        if not self.action_end_date:
            return None
        
        today = timezone.now().date()
        if today > self.action_end_date:
            return 0
        
        return (self.action_end_date - today).days
    
    @property
    def action_duration_days(self):
        """Calculate total duration of action in days"""
        if not self.action_start_date or not self.action_end_date:
            return None
        
        return (self.action_end_date - self.action_start_date).days + 1
    
    # -------------------------------------------------------------------------
    # ACTION METHODS
    # -------------------------------------------------------------------------
    
    def mark_as_resolved(self, user=None, notes=''):
        """Mark this record as resolved"""
        self.is_resolved = True
        self.record_status = 'resolved'
        self.resolution_date = timezone.now()
        self.resolution_notes = notes
        
        if user:
            self.resolved_by_id = str(user.id) if hasattr(user, 'id') else str(user.pk)
        
        self.save()
    
    def mark_parent_notified(self, user=None, method='', response=''):
        """Mark that parent has been notified"""
        self.parent_notified = True
        self.parent_notification_date = timezone.now()
        
        if method:
            self.notification_method = method
        
        if response:
            self.parent_response = response
        
        if user:
            self.notified_by_id = str(user.id) if hasattr(user, 'id') else str(user.pk)
        
        self.save()
    
    def record_investigation(self, user=None, notes=''):
        """Record investigation details"""
        self.investigation_date = timezone.now()
        self.investigation_notes = notes
        self.record_status = 'investigating'
        
        if user:
            self.investigated_by_id = str(user.id) if hasattr(user, 'id') else str(user.pk)
        
        self.save()
    
    def authorize_action(self, user=None):
        """Authorize the disciplinary action"""
        self.authorization_date = timezone.now()
        self.record_status = 'action_taken'
        
        if user:
            self.action_authorized_by_id = str(user.id) if hasattr(user, 'id') else str(user.pk)
        
        self.save()
    
    def file_appeal(self, notes=''):
        """File an appeal for this record"""
        self.appealed = True
        self.appeal_date = timezone.now()
        self.appeal_notes = notes
        self.appeal_outcome = 'pending'
        self.record_status = 'appealed'
        self.save()
    
    def resolve_appeal(self, outcome, notes=''):
        """Resolve an appeal"""
        self.appeal_outcome = outcome
        
        # Update appeal notes
        if notes:
            if self.appeal_notes:
                self.appeal_notes += f"\n\nResolution: {notes}"
            else:
                self.appeal_notes = notes
        
        # Update status based on outcome
        if outcome == 'overturned':
            self.record_status = 'dismissed'
            self.is_resolved = True
            self.resolution_date = timezone.now()
        elif outcome == 'upheld':
            self.record_status = 'action_taken'
        elif outcome == 'modified':
            self.record_status = 'action_pending'
        
        self.save()
    
    # -------------------------------------------------------------------------
    # CLASS METHODS
    # -------------------------------------------------------------------------
    
    @classmethod
    def get_student_records(cls, student):
        """Get all disciplinary records for a student"""
        return cls.objects.filter(student=student).order_by('-incident_date')
    
    @classmethod
    def get_active_suspensions(cls):
        """Get all active suspensions"""
        today = timezone.now().date()
        return cls.objects.filter(
            action_taken__in=['in_school_suspension', 'out_of_school_suspension'],
            action_start_date__lte=today,
            action_end_date__gte=today
        )
    
    @classmethod
    def get_pending_actions(cls):
        """Get records pending action"""
        return cls.objects.filter(
            record_status__in=['reported', 'investigating', 'action_pending'],
            is_resolved=False
        )
    
    @classmethod
    def get_unresolved_records(cls):
        """Get all unresolved records"""
        return cls.objects.filter(is_resolved=False)
    
    @classmethod
    def get_records_by_severity(cls, severity_level):
        """Get records filtered by severity level"""
        return cls.objects.filter(severity_level=severity_level)
    
    @classmethod
    def get_records_by_type(cls, incident_type):
        """Get records filtered by incident type"""
        return cls.objects.filter(incident_type=incident_type)
    
    @classmethod
    def get_records_for_session(cls, academic_session):
        """Get all records for an academic session"""
        return cls.objects.filter(academic_session=academic_session).order_by('-incident_date')
    
    @classmethod
    def get_recent_records(cls, days=30):
        """Get records from recent days"""
        from datetime import timedelta
        cutoff_date = timezone.now().date() - timedelta(days=days)
        return cls.objects.filter(incident_date__gte=cutoff_date)
    
    @classmethod
    def get_records_requiring_followup(cls):
        """Get records that require follow-up"""
        return cls.objects.filter(
            follow_up_required=True,
            follow_up_completed=False
        ).order_by('follow_up_date')
    
    @classmethod
    def get_statistics_for_session(cls, academic_session):
        """Get statistics for an academic session"""
        from django.db.models import Count
        
        records = cls.objects.filter(academic_session=academic_session)
        
        return {
            'total_incidents': records.count(),
            'by_type': records.values('incident_type').annotate(count=Count('id')),
            'by_severity': records.values('severity_level').annotate(count=Count('id')),
            'by_action': records.values('action_taken').annotate(count=Count('id')),
            'resolved': records.filter(is_resolved=True).count(),
            'pending': records.filter(is_resolved=False).count(),
            'appealed': records.filter(appealed=True).count(),
        }