# boarding/models.py

from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from utils.models import BaseModel
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# DORMITORY MODEL
# =============================================================================

class Dormitory(BaseModel):
    """Model for managing dormitories and residential facilities"""
    
    # -------------------------------------------------------------------------
    # CHOICE FIELDS
    # -------------------------------------------------------------------------
    
    DORMITORY_TYPE_CHOICES = [
        ('BOYS', 'Boys Dormitory'),
        ('GIRLS', 'Girls Dormitory'),
        ('MIXED', 'Mixed Dormitory'),
        ('STAFF', 'Staff Quarters'),
    ]
    
    MAINTENANCE_STATUS_CHOICES = [
        ('EXCELLENT', 'Excellent Condition'),
        ('GOOD', 'Good Condition'),
        ('FAIR', 'Fair Condition'),
        ('NEEDS_REPAIR', 'Needs Repair'),
        ('UNDER_MAINTENANCE', 'Under Maintenance'),
        ('CONDEMNED', 'Condemned'),
    ]
    
    # -------------------------------------------------------------------------
    # BASIC INFORMATION
    # -------------------------------------------------------------------------
    
    name = models.CharField("Dormitory Name", max_length=100)
    code = models.CharField(
        "Dormitory Code",
        max_length=20,
        unique=True,
        db_index=True
    )
    dormitory_type = models.CharField(
        "Dormitory Type",
        max_length=10,
        choices=DORMITORY_TYPE_CHOICES,
        db_index=True
    )
    
    description = models.TextField("Description", blank=True)
    
    # -------------------------------------------------------------------------
    # LOCATION DETAILS
    # -------------------------------------------------------------------------
    
    building = models.CharField("Building", max_length=100, blank=True)
    floor = models.CharField("Floor", max_length=10, blank=True)
    wing = models.CharField("Wing/Section", max_length=50, blank=True)
    
    # -------------------------------------------------------------------------
    # CAPACITY MANAGEMENT
    # -------------------------------------------------------------------------
    
    total_capacity = models.PositiveIntegerField(
        "Total Capacity",
        validators=[MinValueValidator(1)]
    )
    current_occupancy = models.PositiveIntegerField(
        "Current Occupancy",
        default=0,
        validators=[MinValueValidator(0)]
    )
    room_count = models.PositiveIntegerField(
        "Number of Rooms",
        default=0,
        validators=[MinValueValidator(0)]
    )
    beds_per_room = models.PositiveIntegerField(
        "Beds per Room",
        default=1,
        validators=[MinValueValidator(1)]
    )
    
    # -------------------------------------------------------------------------
    # FACILITIES
    # -------------------------------------------------------------------------
    
    has_bathroom = models.BooleanField("Has Bathroom", default=True)
    has_study_area = models.BooleanField("Has Study Area", default=False)
    has_common_room = models.BooleanField("Has Common Room", default=False)
    has_laundry = models.BooleanField("Has Laundry Facilities", default=False)
    has_kitchen = models.BooleanField("Has Kitchen", default=False)
    has_wifi = models.BooleanField("Has WiFi", default=False)
    has_security = models.BooleanField("Has Security", default=True)
    
    facilities_description = models.TextField("Facilities Description", blank=True)
    
    # -------------------------------------------------------------------------
    # MANAGEMENT STAFF
    # -------------------------------------------------------------------------
    
    dormitory_master = models.ForeignKey(
        'hr.Staff',
        verbose_name="Dormitory Master",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='managed_dormitories',
        help_text="Primary person responsible for this dormitory"
    )
    
    assistant_dormitory_master = models.ForeignKey(
        'hr.Staff',
        verbose_name="Assistant Dormitory Master",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assisted_dormitories',
        help_text="Assistant/deputy dormitory master"
    )
    
    # -------------------------------------------------------------------------
    # STATUS AND CONDITION
    # -------------------------------------------------------------------------
    
    is_active = models.BooleanField("Is Active", default=True, db_index=True)
    is_available_for_new_admissions = models.BooleanField(
        "Available for New Admissions",
        default=True,
        help_text="Whether new students can be assigned to this dormitory"
    )
    
    maintenance_status = models.CharField(
        "Maintenance Status",
        max_length=20,
        choices=MAINTENANCE_STATUS_CHOICES,
        default='GOOD',
        db_index=True
    )
    
    last_maintenance_date = models.DateField(
        "Last Maintenance Date",
        null=True,
        blank=True
    )
    next_maintenance_due = models.DateField(
        "Next Maintenance Due",
        null=True,
        blank=True
    )
    
    # -------------------------------------------------------------------------
    # RULES AND SAFETY
    # -------------------------------------------------------------------------
    
    rules_and_regulations = models.TextField("Rules and Regulations", blank=True)
    emergency_procedures = models.TextField("Emergency Procedures", blank=True)
    
    # -------------------------------------------------------------------------
    # CONTACT INFORMATION
    # -------------------------------------------------------------------------
    
    dormitory_phone = models.CharField("Dormitory Phone", max_length=20, blank=True)
    dormitory_email = models.EmailField("Dormitory Email", blank=True)
    
    # -------------------------------------------------------------------------
    # ADDITIONAL NOTES
    # -------------------------------------------------------------------------
    
    notes = models.TextField("Administrative Notes", blank=True)
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        ordering = ['dormitory_type', 'name']
        verbose_name = "Dormitory"
        verbose_name_plural = "Dormitories"
        indexes = [
            models.Index(fields=['dormitory_type', 'is_active']),
            models.Index(fields=['code']),
            models.Index(fields=['maintenance_status']),
            models.Index(fields=['is_available_for_new_admissions']),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(current_occupancy__lte=models.F('total_capacity')),
                name='occupancy_not_exceed_capacity'
            ),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.name} ({self.get_dormitory_type_display()})"
    
    # -------------------------------------------------------------------------
    # PROPERTIES
    # -------------------------------------------------------------------------
    
    @property
    def available_capacity(self):
        """Get available capacity"""
        return self.get_available_capacity()
    
    @property
    def occupancy_percentage(self):
        """Get occupancy as percentage"""
        return self.get_occupancy_percentage()
    
    @property
    def is_full(self):
        """Check if dormitory is at capacity"""
        return self.current_occupancy >= self.total_capacity
    
    @property
    def is_nearly_full(self, threshold=0.9):
        """Check if dormitory is nearly full (90% by default)"""
        if self.total_capacity == 0:
            return False
        return (self.current_occupancy / self.total_capacity) >= threshold
    
    # -------------------------------------------------------------------------
    # CAPACITY METHODS
    # -------------------------------------------------------------------------
    
    def get_available_capacity(self):
        """Get available capacity"""
        return max(0, self.total_capacity - self.current_occupancy)
    
    def get_occupancy_percentage(self):
        """Get occupancy as percentage"""
        if self.total_capacity == 0:
            return 0
        return round((self.current_occupancy / self.total_capacity) * 100, 1)
    
    def get_occupancy_level(self):
        """Get occupancy level as string"""
        if self.total_capacity == 0:
            return 'empty'
        
        ratio = self.current_occupancy / self.total_capacity
        if ratio < 0.7:
            return 'low'
        elif ratio < 0.9:
            return 'medium'
        else:
            return 'high'
    
    def get_occupancy_color(self):
        """Get color class for occupancy level"""
        level = self.get_occupancy_level()
        colors = {
            'empty': 'secondary',
            'low': 'success',
            'medium': 'warning',
            'high': 'danger',
        }
        return colors.get(level, 'secondary')
    
    # -------------------------------------------------------------------------
    # VALIDATION METHODS
    # -------------------------------------------------------------------------
    
    def can_accommodate(self, student):
        """Check if dormitory can accommodate a specific student"""
        # Check capacity
        if self.is_full:
            return False, "Dormitory is at full capacity"
        
        # Check if active and available
        if not self.is_active:
            return False, "Dormitory is not active"
        
        if not self.is_available_for_new_admissions:
            return False, "Dormitory is not accepting new admissions"
        
        # Check gender compatibility
        can_accommodate_gender = self.can_accommodate_gender(student.gender)
        if not can_accommodate_gender:
            return False, f"Dormitory cannot accommodate {student.get_gender_display()} students"
        
        # Check maintenance status
        if self.maintenance_status in ['CONDEMNED', 'UNDER_MAINTENANCE']:
            return False, f"Dormitory is {self.get_maintenance_status_display()}"
        
        return True, "Can accommodate"
    
    def can_accommodate_gender(self, gender):
        """Check if dormitory can accommodate specific gender"""
        if self.dormitory_type == 'MIXED':
            return True
        elif self.dormitory_type == 'BOYS' and gender == 'M':
            return True
        elif self.dormitory_type == 'GIRLS' and gender == 'F':
            return True
        return False
    
    # -------------------------------------------------------------------------
    # STUDENT QUERY METHODS
    # -------------------------------------------------------------------------
    
    def get_current_residents(self):
        """Get current residents of this dormitory"""
        from students.models import Student
        
        return Student.objects.filter(
            boarding_enrollments__dormitory=self,
            boarding_enrollments__status='ACTIVE',
            enrollment_status='ACTIVE'
        ).distinct()
    
    def get_resident_count(self):
        """Get count of current residents"""
        return self.boarding_enrollments.filter(status='ACTIVE').count()
    
    def get_residents_by_class(self):
        """Get residents grouped by class"""
        from students.models import Student
        
        residents = self.get_current_residents()
        
        # Group by current academic level
        grouped = {}
        for student in residents.select_related('current_academic_level'):
            level = student.current_academic_level
            if level:
                level_name = str(level)
                if level_name not in grouped:
                    grouped[level_name] = []
                grouped[level_name].append(student)
        
        return grouped
    
    # -------------------------------------------------------------------------
    # UTILITY METHODS
    # -------------------------------------------------------------------------
    
    def get_full_location(self):
        """Get full location description"""
        location_parts = [self.name]
        if self.building:
            location_parts.append(self.building)
        if self.floor:
            location_parts.append(f"Floor {self.floor}")
        if self.wing:
            location_parts.append(self.wing)
        return ", ".join(location_parts)
    
    def get_facilities_list(self):
        """Get list of available facilities"""
        facilities = []
        
        facility_map = {
            'has_bathroom': 'Bathroom',
            'has_study_area': 'Study Area',
            'has_common_room': 'Common Room',
            'has_laundry': 'Laundry',
            'has_kitchen': 'Kitchen',
            'has_wifi': 'WiFi',
            'has_security': 'Security',
        }
        
        for field, name in facility_map.items():
            if getattr(self, field):
                facilities.append(name)
        
        return facilities
    
    def needs_maintenance(self):
        """Check if maintenance is due"""
        if not self.next_maintenance_due:
            return False
        return timezone.now().date() >= self.next_maintenance_due
    
    # -------------------------------------------------------------------------
    # OCCUPANCY UPDATE METHODS
    # -------------------------------------------------------------------------
    
    def update_occupancy_count(self):
        """Update current occupancy based on active enrollments"""
        active_count = self.boarding_enrollments.filter(status='ACTIVE').count()
        if self.current_occupancy != active_count:
            self.current_occupancy = active_count
            self.save(update_fields=['current_occupancy'])
        return active_count
    
    # -------------------------------------------------------------------------
    # VALIDATION
    # -------------------------------------------------------------------------
    
    def clean(self):
        """Validate dormitory data"""
        super().clean()
        errors = {}
        
        # Validate occupancy
        if self.current_occupancy > self.total_capacity:
            errors['current_occupancy'] = "Current occupancy cannot exceed total capacity"
        
        # Validate maintenance dates
        if self.last_maintenance_date and self.next_maintenance_due:
            if self.next_maintenance_due < self.last_maintenance_date:
                errors['next_maintenance_due'] = "Next maintenance date cannot be before last maintenance date"
        
        if errors:
            raise ValidationError(errors)


# =============================================================================
# BOARDING ENROLLMENT MODEL
# =============================================================================

class BoardingEnrollment(BaseModel):
    """Model for tracking student boarding enrollment"""
    
    # -------------------------------------------------------------------------
    # CHOICE FIELDS
    # -------------------------------------------------------------------------
    
    BOARDING_TYPE_CHOICES = [
        ('FULL_BOARDER', 'Full Boarder'),
        ('WEEKLY_BOARDER', 'Weekly Boarder'),
        ('FLEXI_BOARDER', 'Flexible Boarder'),
    ]
    
    ENROLLMENT_STATUS_CHOICES = [
        ('PENDING', 'Pending Approval'),
        ('ACTIVE', 'Active'),
        ('SUSPENDED', 'Suspended'),
        ('TERMINATED', 'Terminated'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    # -------------------------------------------------------------------------
    # CORE RELATIONSHIPS
    # -------------------------------------------------------------------------
    
    student = models.ForeignKey(
        'students.Student',
        verbose_name="Student",
        on_delete=models.CASCADE,
        related_name='boarding_enrollments'
    )
    
    academic_session = models.ForeignKey(
        'academics.AcademicSession',
        verbose_name="Academic Session",
        on_delete=models.CASCADE,
        related_name='boarding_enrollments'
    )
    
    # -------------------------------------------------------------------------
    # BOARDING CONFIGURATION
    # -------------------------------------------------------------------------
    
    boarding_type = models.CharField(
        "Boarding Type",
        max_length=20,
        choices=BOARDING_TYPE_CHOICES,
        help_text="Type of boarding arrangement"
    )

    # =========================================================================
    # FINANCIAL INTEGRATION - LINK TO INVOICE
    # =========================================================================
    
    boarding_invoice = models.OneToOneField(
        'fees.FeeInvoice',
        verbose_name="Boarding Invoice",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='boarding_enrollment',
        help_text="Invoice generated for this boarding enrollment"
    )
    
    auto_create_invoice = models.BooleanField(
        "Auto-Create Invoice",
        default=True,
        help_text="Automatically create invoice when enrollment is approved"
    )
    
    # -------------------------------------------------------------------------
    # ACCOMMODATION ASSIGNMENT
    # -------------------------------------------------------------------------
    
    dormitory = models.ForeignKey(
        Dormitory,
        verbose_name="Dormitory",
        on_delete=models.PROTECT,
        related_name='boarding_enrollments'
    )
    
    room_number = models.CharField("Room Number", max_length=20, blank=True)
    bed_number = models.CharField("Bed Number", max_length=20, blank=True)
    
    # -------------------------------------------------------------------------
    # ROLL NUMBER FOR BOARDING
    # -------------------------------------------------------------------------
    
    boarding_roll_number = models.CharField(
        "Boarding Roll Number",
        max_length=20,
        blank=True,
        help_text="Roll number for dormitory attendance and management"
    )
    
    # -------------------------------------------------------------------------
    # DATES AND STATUS
    # -------------------------------------------------------------------------
    
    enrollment_date = models.DateField("Boarding Enrollment Date")
    effective_start_date = models.DateField(
        "Effective Start Date",
        help_text="Date when boarding actually starts"
    )
    effective_end_date = models.DateField(
        "Effective End Date",
        null=True,
        blank=True,
        help_text="Date when boarding ends"
    )
    
    status = models.CharField(
        "Status",
        max_length=20,
        choices=ENROLLMENT_STATUS_CHOICES,
        default='PENDING',
        db_index=True
    )
    
    # -------------------------------------------------------------------------
    # GUARDIAN CONSENT
    # -------------------------------------------------------------------------
    
    guardian_consent = models.BooleanField(
        "Guardian Consent",
        default=False,
        help_text="Whether guardian has provided written consent"
    )
    
    consent_date = models.DateField("Consent Date", null=True, blank=True)
    
    consenting_guardian = models.ForeignKey(
        'students.Guardian',
        verbose_name="Consenting Guardian",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='boarding_consents'
    )
    
    consent_document = models.FileField(
        "Consent Document",
        upload_to='boarding/consents/%Y/%m/',
        null=True,
        blank=True
    )
    
    # -------------------------------------------------------------------------
    # FLEXIBLE BOARDING SCHEDULE
    # -------------------------------------------------------------------------
    
    boarding_days = models.JSONField(
        "Boarding Days",
        null=True,
        blank=True,
        help_text="JSON array of days (e.g., ['Monday', 'Tuesday', 'Wednesday'])"
    )
    
    # -------------------------------------------------------------------------
    # MEDICAL AND DIETARY REQUIREMENTS
    # -------------------------------------------------------------------------
    
    dietary_requirements = models.TextField("Dietary Requirements", blank=True)
    medical_requirements = models.TextField("Medical Requirements", blank=True)
    special_accommodations = models.TextField("Special Accommodations", blank=True)
    
    # -------------------------------------------------------------------------
    # EMERGENCY CONTACTS
    # -------------------------------------------------------------------------
    
    emergency_contact_during_boarding = models.CharField(
        "Emergency Contact During Boarding",
        max_length=20,
        blank=True
    )
    
    emergency_contact_name = models.CharField(
        "Emergency Contact Name",
        max_length=100,
        blank=True
    )
    
    emergency_contact_relationship = models.CharField(
        "Emergency Contact Relationship",
        max_length=50,
        blank=True
    )
    
    # -------------------------------------------------------------------------
    # REASONS AND NOTES
    # -------------------------------------------------------------------------
    
    reason_for_boarding = models.TextField("Reason for Boarding", blank=True)
    termination_reason = models.TextField("Termination Reason", blank=True)
    admin_notes = models.TextField("Administrative Notes", blank=True)
    
    # -------------------------------------------------------------------------
    # APPROVAL WORKFLOW
    # -------------------------------------------------------------------------
    
    approved_by = models.ForeignKey(
        'hr.Staff',
        verbose_name="Approved By",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_boarding_enrollments'
    )
    
    approval_date = models.DateTimeField("Approval Date", null=True, blank=True)
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        ordering = ['-academic_session__start_date', 'dormitory', 'boarding_roll_number']
        verbose_name = "Boarding Enrollment"
        verbose_name_plural = "Boarding Enrollments"
        
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'academic_session'],
                condition=Q(status__in=['ACTIVE', 'PENDING']),
                name='unique_active_boarding_per_student_session'
            ),
            models.UniqueConstraint(
                fields=['dormitory', 'academic_session', 'boarding_roll_number'],
                condition=Q(boarding_roll_number__isnull=False) & ~Q(boarding_roll_number='') & Q(status='ACTIVE'),
                name='unique_boarding_roll_per_dormitory_session'
            ),
        ]
        
        indexes = [
            models.Index(fields=['student', 'academic_session']),
            models.Index(fields=['boarding_type']),
            models.Index(fields=['status']),
            models.Index(fields=['dormitory', 'status']),
            models.Index(fields=['enrollment_date']),
            models.Index(fields=['effective_start_date']),
            models.Index(fields=['boarding_roll_number']),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        display = f"{self.student.get_full_name()} - {self.get_boarding_type_display()} ({self.academic_session})"
        if self.boarding_roll_number:
            display += f" [Roll: {self.boarding_roll_number}]"
        return display
    
    # -------------------------------------------------------------------------
    # PROPERTIES
    # -------------------------------------------------------------------------
    
    @property
    def is_current(self):
        """Check if enrollment is currently active"""
        return self.is_currently_active()
    
    @property
    def duration_days(self):
        """Get duration in days"""
        return self.get_duration_days()
    
    # -------------------------------------------------------------------------
    # SAVE METHOD
    # -------------------------------------------------------------------------
    
    def save(self, *args, **kwargs):
        """Auto-generate boarding roll number and update dormitory occupancy"""
        # Set effective start date if not provided
        if not self.effective_start_date:
            self.effective_start_date = self.enrollment_date
        
        # Track status change
        is_new = self._state.adding
        old_status = None
        
        if not is_new:
            try:
                old_instance = BoardingEnrollment.objects.get(pk=self.pk)
                old_status = old_instance.status
            except BoardingEnrollment.DoesNotExist:
                pass
        
        super().save(*args, **kwargs)
        
        # Update dormitory occupancy if status changed
        if old_status != self.status:
            self.dormitory.update_occupancy_count()
    
    def delete(self, *args, **kwargs):
        """Update dormitory occupancy on delete"""
        dormitory = self.dormitory
        super().delete(*args, **kwargs)
        dormitory.update_occupancy_count()
    
    # -------------------------------------------------------------------------
    # VALIDATION METHODS
    # -------------------------------------------------------------------------
    
    def clean(self):
        """Validate boarding enrollment"""
        super().clean()
        errors = {}
        
        # Validate dates
        if self.effective_end_date and self.effective_start_date:
            if self.effective_end_date < self.effective_start_date:
                errors['effective_end_date'] = "End date cannot be before start date"
        
        # Validate academic session dates
        if self.effective_start_date and self.academic_session:
            if (self.effective_start_date < self.academic_session.start_date or
                self.effective_start_date > self.academic_session.end_date):
                errors['effective_start_date'] = "Start date must be within the academic session period"
        
        # Validate boarding days for flexible boarders
        if self.boarding_type == 'FLEXI_BOARDER':
            if not self.boarding_days:
                errors['boarding_days'] = "Boarding days must be specified for flexible boarders"
            elif not isinstance(self.boarding_days, list) or len(self.boarding_days) == 0:
                errors['boarding_days'] = "Boarding days must be a non-empty list"
        
        # Validate dormitory assignment
        if self.status == 'ACTIVE' and not self.dormitory:
            errors['dormitory'] = "Dormitory assignment is required for active boarding students"
        
        # Validate gender compatibility with dormitory
        if self.dormitory and hasattr(self.student, 'gender'):
            if not self.dormitory.can_accommodate_gender(self.student.gender):
                errors['dormitory'] = f"Selected dormitory cannot accommodate {self.student.get_gender_display()} students"
        
        # Validate guardian consent for minors
        if not self.guardian_consent and self.status in ['ACTIVE', 'PENDING']:
            student_age = self.student.get_age() if hasattr(self.student, 'get_age') else None
            if student_age and student_age < 18:
                errors['guardian_consent'] = "Guardian consent is required for boarding students under 18"
        
        if errors:
            raise ValidationError(errors)
    
    # -------------------------------------------------------------------------
    # HELPER METHODS
    # -------------------------------------------------------------------------
    
    def get_duration_days(self):
        """Get duration of boarding enrollment in days"""
        if not self.effective_end_date:
            end_date = timezone.now().date()
        else:
            end_date = self.effective_end_date
        
        return (end_date - self.effective_start_date).days
    
    def is_currently_active(self):
        """Check if boarding enrollment is currently active"""
        if self.status != 'ACTIVE':
            return False
        
        today = timezone.now().date()
        if today < self.effective_start_date:
            return False
        
        if self.effective_end_date and today > self.effective_end_date:
            return False
        
        return True
    
    def get_boarding_schedule_display(self):
        """Get formatted boarding schedule"""
        if self.boarding_type == 'FULL_BOARDER':
            return "Monday - Sunday (Full Week)"
        elif self.boarding_type == 'WEEKLY_BOARDER':
            return "Monday - Friday (Weekdays)"
        elif self.boarding_type == 'FLEXI_BOARDER' and self.boarding_days:
            days = ", ".join(self.boarding_days)
            return f"Flexible: {days}"
        return "Not specified"
    
    def get_status_color(self):
        """Get color class for status display"""
        status_colors = {
            'PENDING': 'warning',
            'ACTIVE': 'success',
            'SUSPENDED': 'danger',
            'TERMINATED': 'dark',
            'COMPLETED': 'info',
            'CANCELLED': 'secondary',
        }
        return status_colors.get(self.status, 'secondary')
    
    def approve(self, approved_by):
        """Approve this boarding enrollment"""
        self.status = 'ACTIVE'
        self.approved_by = approved_by
        self.approval_date = timezone.now()
        self.save()
    
    def suspend(self, reason=None):
        """Suspend this boarding enrollment"""
        self.status = 'SUSPENDED'
        if reason:
            self.admin_notes = f"{self.admin_notes}\n\nSuspended: {reason}" if self.admin_notes else f"Suspended: {reason}"
        self.save()
    
    def terminate(self, reason=None):
        """Terminate this boarding enrollment"""
        self.status = 'TERMINATED'
        self.effective_end_date = timezone.now().date()
        if reason:
            self.termination_reason = reason
        self.save()