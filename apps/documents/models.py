# documents/models.py

from django.db import models
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
import os
import logging

from utils.models import BaseModel
from students.models import Student

logger = logging.getLogger(__name__)


# =============================================================================
# DOCUMENT MANAGEMENT MODELS
# =============================================================================

class StudentDocument(BaseModel):
    """Model for managing student documents"""
    
    DOCUMENT_TYPE_CHOICES = (
        ('birth_certificate', 'Birth Certificate'),
        ('passport', 'Passport'),
        ('national_id', 'National ID'),
        ('immunization_record', 'Immunization Record'),
        ('medical_report', 'Medical Report'),
        ('previous_school_report', 'Previous School Report'),
        ('transfer_certificate', 'Transfer Certificate'),
        ('admission_letter', 'Admission Letter'),
        ('parent_letter', 'Parent/Guardian Letter'),
        ('photo', 'Photograph'),
        ('scholarship_document', 'Scholarship Document'),
        ('disciplinary_record', 'Disciplinary Record'),
        ('achievement_certificate', 'Achievement Certificate'),
        ('sports_certificate', 'Sports Certificate'),
        ('other', 'Other Document'),
    )
    
    DOCUMENT_STATUS_CHOICES = (
        ('pending_review', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('expired', 'Expired'),
        ('requires_update', 'Requires Update'),
    )
    
    CONFIDENTIALITY_LEVEL_CHOICES = (
        ('public', 'Public'),
        ('internal', 'Internal'),
        ('confidential', 'Confidential'),
        ('restricted', 'Restricted'),
    )
    
    # -------------------------------------------------------------------------
    # CORE FIELDS
    # -------------------------------------------------------------------------
    
    student = models.ForeignKey(
        Student,
        verbose_name="Student",
        on_delete=models.CASCADE,
        related_name='documents'
    )
    
    document_type = models.CharField(
        "Document Type",
        max_length=30,
        choices=DOCUMENT_TYPE_CHOICES,
        db_index=True
    )
    
    document_name = models.CharField(
        "Document Name",
        max_length=100,
        help_text="Descriptive name for the document"
    )
    
    document_file = models.FileField(
        "Document File",
        upload_to='student_documents/%Y/%m/',
        help_text="Upload document file (PDF, DOC, DOCX, JPG, PNG)"
    )
    
    # -------------------------------------------------------------------------
    # DOCUMENT METADATA
    # -------------------------------------------------------------------------
    
    document_number = models.CharField(
        "Document Number",
        max_length=50,
        blank=True,
        help_text="Official document number (if applicable)"
    )
    
    issue_date = models.DateField(
        "Issue Date",
        null=True,
        blank=True,
        help_text="Date when document was issued"
    )
    
    expiry_date = models.DateField(
        "Expiry Date",
        null=True,
        blank=True,
        db_index=True,
        help_text="Date when document expires"
    )
    
    issuing_authority = models.CharField(
        "Issuing Authority",
        max_length=100,
        blank=True,
        help_text="Organization that issued the document"
    )
    
    # -------------------------------------------------------------------------
    # STATUS & VERIFICATION
    # -------------------------------------------------------------------------
    
    status = models.CharField(
        "Status",
        max_length=20,
        choices=DOCUMENT_STATUS_CHOICES,
        default='pending_review',
        db_index=True
    )
    
    is_verified = models.BooleanField(
        "Is Verified",
        default=False,
        db_index=True,
        help_text="Whether document has been verified by staff"
    )
    
    verified_by_id = models.CharField(
        "Verified By ID",
        max_length=50,
        null=True,
        blank=True,
        help_text="User ID who verified this document"
    )
    
    verification_date = models.DateTimeField(
        "Verification Date",
        null=True,
        blank=True
    )
    
    verification_notes = models.TextField(
        "Verification Notes",
        blank=True,
        help_text="Notes from document verification process"
    )
    
    # -------------------------------------------------------------------------
    # ACCESS CONTROL
    # -------------------------------------------------------------------------
    
    confidentiality_level = models.CharField(
        "Confidentiality Level",
        max_length=15,
        choices=CONFIDENTIALITY_LEVEL_CHOICES,
        default='internal',
        db_index=True
    )
    
    is_required = models.BooleanField(
        "Is Required",
        default=False,
        help_text="Whether this document is required for enrollment"
    )
    
    is_active = models.BooleanField(
        "Is Active",
        default=True,
        db_index=True,
        help_text="Whether document is currently active"
    )
    
    # -------------------------------------------------------------------------
    # ADDITIONAL METADATA
    # -------------------------------------------------------------------------
    
    description = models.TextField(
        "Description",
        blank=True,
        help_text="Additional description or notes about the document"
    )
    
    tags = models.CharField(
        "Tags",
        max_length=200,
        blank=True,
        help_text="Comma-separated tags for easy searching"
    )
    
    # -------------------------------------------------------------------------
    # FILE METADATA (AUTO-POPULATED)
    # -------------------------------------------------------------------------
    
    file_size = models.BigIntegerField(
        "File Size",
        null=True,
        blank=True,
        help_text="File size in bytes"
    )
    
    file_type = models.CharField(
        "File Type",
        max_length=10,
        blank=True,
        help_text="File extension"
    )
    
    # -------------------------------------------------------------------------
    # TRACKING FIELDS
    # -------------------------------------------------------------------------
    
    upload_date = models.DateTimeField(
        "Upload Date",
        auto_now_add=True,
        db_index=True
    )
    
    last_accessed = models.DateTimeField(
        "Last Accessed",
        null=True,
        blank=True
    )
    
    access_count = models.PositiveIntegerField(
        "Access Count",
        default=0,
        help_text="Number of times document has been accessed"
    )
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Student Document"
        verbose_name_plural = "Student Documents"
        ordering = ['-upload_date']
        indexes = [
            models.Index(fields=['student', 'document_type']),
            models.Index(fields=['status']),
            models.Index(fields=['is_verified']),
            models.Index(fields=['expiry_date']),
            models.Index(fields=['student', 'is_active']),
            models.Index(fields=['confidentiality_level']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'document_type', 'document_number'],
                condition=models.Q(document_number__isnull=False) & ~models.Q(document_number=''),
                name='unique_student_document_number'
            ),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.student.get_full_name()} - {self.get_document_type_display()}"
    
    # -------------------------------------------------------------------------
    # VALIDATION METHODS
    # -------------------------------------------------------------------------
    
    def clean(self):
        """Validate document"""
        super().clean()
        errors = {}
        
        # Validate file type
        if self.document_file:
            allowed_extensions = ['.pdf', '.doc', '.docx', '.jpg', '.jpeg', '.png', '.gif']
            file_extension = os.path.splitext(self.document_file.name)[1].lower()
            
            if file_extension not in allowed_extensions:
                errors['document_file'] = 'File type not allowed. Allowed types: PDF, DOC, DOCX, JPG, PNG, GIF'
            
            # Check file size (max 10MB)
            elif self.document_file.size > 10 * 1024 * 1024:
                errors['document_file'] = 'File size must be less than 10MB'
        
        # Validate dates
        if self.issue_date and self.expiry_date:
            if self.issue_date > self.expiry_date:
                errors['expiry_date'] = 'Expiry date cannot be before issue date'
        
        if errors:
            raise ValidationError(errors)
    
    # -------------------------------------------------------------------------
    # SAVE METHOD
    # -------------------------------------------------------------------------
    
    def save(self, *args, **kwargs):
        """Override save to populate metadata"""
        if self.document_file:
            # Populate file size
            self.file_size = self.document_file.size
            
            # Populate file type
            file_extension = os.path.splitext(self.document_file.name)[1].lower()
            self.file_type = file_extension.replace('.', '')
        
        # Auto-expire if past expiry date
        if self.expiry_date and timezone.now().date() > self.expiry_date:
            if self.status != 'expired':
                self.status = 'expired'
        
        super().save(*args, **kwargs)
    
    # -------------------------------------------------------------------------
    # PROPERTIES
    # -------------------------------------------------------------------------
    
    @property
    def is_expired(self):
        """Check if document is expired"""
        if self.expiry_date:
            return timezone.now().date() > self.expiry_date
        return False
    
    def expires_soon(self, days=30):
        """Check if document expires within specified days"""
        if self.expiry_date:
            cutoff_date = timezone.now().date() + timedelta(days=days)
            return self.expiry_date <= cutoff_date and not self.is_expired
        return False
    
    @property
    def file_size_human(self):
        """Return human-readable file size"""
        if not self.file_size:
            return "Unknown"
        
        size = float(self.file_size)
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"
    
    # -------------------------------------------------------------------------
    # HELPER METHODS
    # -------------------------------------------------------------------------
    
    def get_download_url(self):
        """Get URL for downloading document"""
        return reverse('students:student_document_download', kwargs={'pk': self.pk})
    
    def get_status_color(self):
        """Get color class for document status"""
        status_colors = {
            'pending_review': 'warning',
            'approved': 'success',
            'rejected': 'danger',
            'expired': 'danger',
            'requires_update': 'warning'
        }
        return status_colors.get(self.status, 'secondary')
    
    def get_status_badge_class(self):
        """Get Bootstrap badge class for status"""
        return f"badge-{self.get_status_color()}"
    
    def get_confidentiality_badge_class(self):
        """Get Bootstrap badge class for confidentiality level"""
        confidentiality_colors = {
            'public': 'success',
            'internal': 'info',
            'confidential': 'warning',
            'restricted': 'danger'
        }
        color = confidentiality_colors.get(self.confidentiality_level, 'secondary')
        return f"badge-{color}"
    
    def get_verified_by_user(self):
        """Get the user who verified this document"""
        if not self.verified_by_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            return User.objects.using('default').get(id=self.verified_by_id)
        except Exception as e:
            logger.error(f"Error fetching verified_by user: {e}")
            return None
    
    @property
    def verified_by_name(self):
        """Get name of user who verified document"""
        user = self.get_verified_by_user()
        if user:
            return user.get_full_name() or user.username
        return "Unknown"
    
    def mark_as_verified(self, user=None, notes=''):
        """Mark document as verified"""
        self.is_verified = True
        self.status = 'approved'
        self.verification_date = timezone.now()
        self.verification_notes = notes
        
        if user:
            self.verified_by_id = str(user.id) if hasattr(user, 'id') else str(user.pk)
        
        self.save()
    
    def mark_as_rejected(self, user=None, notes=''):
        """Mark document as rejected"""
        self.is_verified = False
        self.status = 'rejected'
        self.verification_date = timezone.now()
        self.verification_notes = notes
        
        if user:
            self.verified_by_id = str(user.id) if hasattr(user, 'id') else str(user.pk)
        
        self.save()
    
    def increment_access_count(self):
        """Increment access counter and update last accessed time"""
        self.access_count += 1
        self.last_accessed = timezone.now()
        self.save(update_fields=['access_count', 'last_accessed'])
    
    # -------------------------------------------------------------------------
    # CLASS METHODS
    # -------------------------------------------------------------------------
    
    @classmethod
    def get_expired_documents(cls):
        """Get all expired documents"""
        return cls.objects.filter(
            expiry_date__lt=timezone.now().date(),
            is_active=True
        )
    
    @classmethod
    def get_expiring_soon(cls, days=30):
        """Get documents expiring within specified days"""
        cutoff_date = timezone.now().date() + timedelta(days=days)
        return cls.objects.filter(
            expiry_date__lte=cutoff_date,
            expiry_date__gt=timezone.now().date(),
            is_active=True
        )
    
    @classmethod
    def get_pending_verification(cls):
        """Get documents pending verification"""
        return cls.objects.filter(
            status='pending_review',
            is_active=True
        )
    
    @classmethod
    def get_student_documents(cls, student):
        """Get all documents for a student"""
        return cls.objects.filter(
            student=student,
            is_active=True
        ).order_by('-upload_date')
    
    @classmethod
    def get_required_documents(cls, student=None):
        """Get required documents (optionally for a specific student)"""
        queryset = cls.objects.filter(is_required=True, is_active=True)
        if student:
            queryset = queryset.filter(student=student)
        return queryset


# =============================================================================
# DOCUMENT ACCESS LOG MODEL
# =============================================================================

class DocumentAccessLog(BaseModel):
    """Log document access for audit trail"""
    
    ACCESS_TYPE_CHOICES = (
        ('view', 'View'),
        ('download', 'Download'),
        ('edit', 'Edit'),
        ('delete', 'Delete'),
        ('upload', 'Upload'),
        ('print', 'Print'),
        ('share', 'Share'),
        ('verify', 'Verify'),
        ('reject', 'Reject'),
    )
    
    # -------------------------------------------------------------------------
    # CORE FIELDS
    # -------------------------------------------------------------------------
    
    document = models.ForeignKey(
        StudentDocument,
        verbose_name="Document",
        on_delete=models.CASCADE,
        related_name='access_logs'
    )
    
    access_datetime = models.DateTimeField(
        "Access Date/Time",
        auto_now_add=True,
        db_index=True
    )
    
    access_type = models.CharField(
        "Access Type",
        max_length=20,
        choices=ACCESS_TYPE_CHOICES,
        default='view',
        db_index=True
    )
    
    # -------------------------------------------------------------------------
    # NETWORK AND BROWSER INFORMATION
    # -------------------------------------------------------------------------
    
    ip_address = models.GenericIPAddressField(
        "IP Address",
        null=True,
        blank=True,
        db_index=True
    )
    
    user_agent = models.TextField(
        "User Agent",
        blank=True,
        help_text="Browser user agent string"
    )
    
    # -------------------------------------------------------------------------
    # ADDITIONAL CONTEXT
    # -------------------------------------------------------------------------
    
    session_id = models.CharField(
        "Session ID",
        max_length=40,
        blank=True,
        help_text="User session identifier"
    )
    
    referrer_url = models.URLField(
        "Referrer URL",
        blank=True,
        max_length=500,
        help_text="URL that referred to this access"
    )
    
    # -------------------------------------------------------------------------
    # ACCESS DETAILS
    # -------------------------------------------------------------------------
    
    access_duration = models.DurationField(
        "Access Duration",
        null=True,
        blank=True,
        help_text="How long the document was accessed (for view operations)"
    )
    
    file_size_at_access = models.BigIntegerField(
        "File Size at Access",
        null=True,
        blank=True,
        help_text="Size of file when accessed (in bytes)"
    )
    
    # -------------------------------------------------------------------------
    # SUCCESS/FAILURE TRACKING
    # -------------------------------------------------------------------------
    
    was_successful = models.BooleanField(
        "Was Successful",
        default=True,
        db_index=True,
        help_text="Whether the access operation was successful"
    )
    
    error_message = models.TextField(
        "Error Message",
        blank=True,
        help_text="Error message if access failed"
    )
    
    # -------------------------------------------------------------------------
    # ADDITIONAL METADATA
    # -------------------------------------------------------------------------
    
    notes = models.TextField(
        "Notes",
        blank=True,
        help_text="Additional notes about this access"
    )
    
    # -------------------------------------------------------------------------
    # GEOGRAPHIC INFORMATION (OPTIONAL)
    # -------------------------------------------------------------------------
    
    country_code = models.CharField(
        "Country Code",
        max_length=2,
        blank=True,
        help_text="ISO country code from IP geolocation"
    )
    
    city = models.CharField(
        "City",
        max_length=100,
        blank=True,
        help_text="City from IP geolocation"
    )
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Document Access Log"
        verbose_name_plural = "Document Access Logs"
        ordering = ['-access_datetime']
        indexes = [
            models.Index(fields=['document', 'access_datetime']),
            models.Index(fields=['access_type']),
            models.Index(fields=['ip_address']),
            models.Index(fields=['was_successful']),
            models.Index(fields=['access_datetime']),
            models.Index(fields=['document', 'access_type']),
            models.Index(fields=['created_by_id', 'access_datetime']),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        user = self.get_accessed_by_user()
        user_display = user.get_full_name() if user else "Unknown User"
        return f"{self.document} {self.access_type} by {user_display} on {self.access_datetime}"
    
    # -------------------------------------------------------------------------
    # HELPER METHODS
    # -------------------------------------------------------------------------
    
    def get_accessed_by_user(self):
        """Get the user who accessed this document"""
        return self.get_created_by()
    
    def get_access_type_icon(self):
        """Get appropriate icon for access type"""
        icons = {
            'view': 'fas fa-eye',
            'download': 'fas fa-download',
            'edit': 'fas fa-edit',
            'delete': 'fas fa-trash',
            'upload': 'fas fa-upload',
            'print': 'fas fa-print',
            'share': 'fas fa-share',
            'verify': 'fas fa-check-circle',
            'reject': 'fas fa-times-circle'
        }
        return icons.get(self.access_type, 'fas fa-file')
    
    def get_access_type_color(self):
        """Get color class for access type"""
        colors = {
            'view': 'info',
            'download': 'primary',
            'edit': 'warning',
            'delete': 'danger',
            'upload': 'success',
            'print': 'secondary',
            'share': 'info',
            'verify': 'success',
            'reject': 'danger'
        }
        return colors.get(self.access_type, 'secondary')
    
    def get_access_type_badge_class(self):
        """Get Bootstrap badge class for access type"""
        return f"badge-{self.get_access_type_color()}"
    
    @property
    def duration_human(self):
        """Return human-readable duration"""
        if not self.access_duration:
            return "N/A"
        
        total_seconds = int(self.access_duration.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        
        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"
    
    # -------------------------------------------------------------------------
    # CLASS METHODS
    # -------------------------------------------------------------------------
    
    @classmethod
    def log_access(cls, document, access_type, user=None, request=None, **kwargs):
        """
        Create an access log entry.
        
        Args:
            document: StudentDocument instance
            access_type: Type of access from ACCESS_TYPE_CHOICES
            user: User performing the access
            request: Django request object
            **kwargs: Additional fields to set
            
        Returns:
            DocumentAccessLog instance
        """
        log_data = {
            'document': document,
            'access_type': access_type,
        }
        
        # Extract request data if available
        if request:
            log_data['ip_address'] = cls._get_client_ip(request)
            log_data['user_agent'] = request.META.get('HTTP_USER_AGENT', '')[:500]
            log_data['session_id'] = request.session.session_key if hasattr(request, 'session') else ''
            log_data['referrer_url'] = request.META.get('HTTP_REFERER', '')[:500]
        
        # Add file size if document has file
        if document.document_file:
            log_data['file_size_at_access'] = document.file_size
        
        # Add any additional kwargs
        log_data.update(kwargs)
        
        # Create the log entry
        return cls.objects.create(**log_data)
    
    @staticmethod
    def _get_client_ip(request):
        """Extract client IP from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    @classmethod
    def get_recent_activity(cls, limit=50):
        """Get recent document access activity"""
        return cls.objects.all().select_related('document', 'document__student')[:limit]
    
    @classmethod
    def get_document_activity(cls, document, limit=50):
        """Get access history for a specific document"""
        return cls.objects.filter(document=document).order_by('-access_datetime')[:limit]
    
    @classmethod
    def get_user_activity(cls, user_id, limit=50):
        """Get access history for a specific user"""
        return cls.objects.filter(created_by_id=str(user_id)).order_by('-access_datetime')[:limit]
    
    @classmethod
    def get_failed_access_attempts(cls, days=7):
        """Get failed access attempts within specified days"""
        cutoff_date = timezone.now() - timedelta(days=days)
        return cls.objects.filter(
            was_successful=False,
            access_datetime__gte=cutoff_date
        ).order_by('-access_datetime')