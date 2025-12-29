# utils/models.py

from django.db import models
from schoolara.managers import get_current_db, SchoolManager
from datetime import date
import uuid
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
import logging
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)


# =============================================================================
# BASE MODEL - SCHOOL-SPECIFIC DATA
# =============================================================================

class BaseModel(models.Model):
    """
    Enhanced base model with comprehensive audit trail capabilities
    and automatic multi-database routing.
    
    Features:
    - Automatic user tracking (who created/updated)
    - Real IP address tracking (where operations came from)
    - Change reason tracking (why changes were made)
    - Automatic database routing for multi-tenant setup
    - Comprehensive audit trail methods
    - Thread-local context integration
    """
    
    # Core identification
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Timestamp fields
    created_at = models.DateTimeField("Created At", auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField("Updated At", auto_now=True, db_index=True)
    
    # User tracking - CharField to avoid cross-database FK constraints
    created_by_id = models.CharField("Created By ID", max_length=50, null=True, blank=True, db_index=True)
    updated_by_id = models.CharField("Updated By ID", max_length=50, null=True, blank=True, db_index=True)
    
    # Enhanced IP tracking - captures real client IP
    created_from_ip = models.GenericIPAddressField("Created From IP", null=True, blank=True)
    updated_from_ip = models.GenericIPAddressField("Updated From IP", null=True, blank=True)
    
    # Change reason tracking
    change_reason = models.CharField("Change Reason", max_length=255, blank=True, null=True)
    
    # Use SchoolManager for automatic database routing
    objects = SchoolManager()
    
    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=['created_at']),
            models.Index(fields=['updated_at']),
            models.Index(fields=['created_by_id']),
            models.Index(fields=['updated_by_id']),
        ]

    def save(self, *args, **kwargs):
        """
        Override save to:
        1. Populate audit trail fields (created_by, updated_by, IPs)
        2. Automatically route to correct database
        3. Track field changes
        4. Create audit log entry
        """
        from utils.context import get_request_context
        
        # Determine if this is a new object
        is_new = self._state.adding
        
        # =========================================================================
        # STEP 1: POPULATE AUDIT FIELDS FROM REQUEST CONTEXT
        # =========================================================================
        context = get_request_context()
        
        if context:
            user = context.get('user')
            ip_address = context.get('ip_address')
            
            # Set created_by and created_from_ip for new objects
            if is_new:
                if user and not self.created_by_id:
                    self.created_by_id = str(user.id)
                if ip_address and not self.created_from_ip:
                    self.created_from_ip = ip_address
            
            # Always update updated_by and updated_from_ip
            if user:
                self.updated_by_id = str(user.id)
            if ip_address:
                self.updated_from_ip = ip_address
        else:
            # Log when no context is available (e.g., management commands, shell)
            if is_new:
                logger.debug(
                    f"No request context available when creating {self.__class__.__name__}. "
                    f"Audit fields will not be populated."
                )
        
        # =========================================================================
        # STEP 2: TRACK CHANGES FOR EXISTING OBJECTS
        # =========================================================================
        changes = {}
        if not is_new and self.pk:
            try:
                # Get old instance from database with proper routing
                current_db = get_current_db()
                if current_db:
                    old_instance = self.__class__.objects.using(current_db).get(pk=self.pk)
                else:
                    old_instance = self.__class__.objects.get(pk=self.pk)
                
                # Compare fields to detect changes
                for field in self._meta.fields:
                    field_name = field.name
                    
                    # Skip auto-generated fields and audit fields
                    if field_name in ['id', 'created_at', 'updated_at', 'created_by_id', 
                                     'updated_by_id', 'created_from_ip', 'updated_from_ip']:
                        continue
                    
                    old_value = getattr(old_instance, field_name)
                    new_value = getattr(self, field_name)
                    
                    # Record change if values differ
                    if old_value != new_value:
                        changes[field_name] = {
                            'old': str(old_value) if old_value is not None else None,
                            'new': str(new_value) if new_value is not None else None
                        }
            except self.__class__.DoesNotExist:
                logger.debug(f"Old instance not found for {self.__class__.__name__} {self.pk}")
                pass  # Object doesn't exist yet, treat as new
            except Exception as e:
                logger.error(f"Error tracking changes for {self.__class__.__name__}: {e}")
        
        # =========================================================================
        # STEP 3: AUTOMATIC DATABASE ROUTING
        # =========================================================================
        current_db = get_current_db()
        
        # Only set 'using' if not already specified and we have a database context
        if current_db and 'using' not in kwargs:
            kwargs['using'] = current_db
            logger.debug(f"Saving {self.__class__.__name__} to {current_db}")
        
        # =========================================================================
        # STEP 4: SAVE THE OBJECT
        # =========================================================================
        result = super().save(*args, **kwargs)
        
        # =========================================================================
        # STEP 5: CREATE AUDIT LOG ENTRY
        # =========================================================================
        # Only create audit log for school databases (not default)
        # ALSO skip if this IS an AuditLog to prevent infinite recursion
        if current_db and current_db != 'default' and self.__class__.__name__ != 'AuditLog':
            self._create_audit_log(
                action='CREATE' if is_new else 'UPDATE',
                changes=changes if not is_new else {}
            )
        
        return result
    
    def delete(self, *args, **kwargs):
        """Override delete to automatically route to correct database and log deletion"""
        current_db = get_current_db()
        
        if current_db and 'using' not in kwargs:
            kwargs['using'] = current_db
            logger.debug(f"Deleting {self.__class__.__name__} from {current_db}")
        
        # Create audit log before deletion (only for school databases)
        # ALSO skip if this IS an AuditLog to prevent infinite recursion
        if current_db and current_db != 'default' and self.__class__.__name__ != 'AuditLog':
            self._create_audit_log(action='DELETE', changes={})
        
        return super().delete(*args, **kwargs)
    
    def refresh_from_db(self, *args, **kwargs):
        """Override refresh to automatically route to correct database"""
        current_db = get_current_db()
        
        if current_db and 'using' not in kwargs:
            kwargs['using'] = current_db
        
        return super().refresh_from_db(*args, **kwargs)
    
    # -------------------------------------------------------------------------
    # AUDIT TRAIL HELPER METHODS
    # -------------------------------------------------------------------------
    
    def get_created_by(self):
        """Get the user who created this record"""
        if not self.created_by_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            return User.objects.using('default').get(id=self.created_by_id)
        except Exception as e:
            logger.error(f"Error fetching created_by user: {e}")
            return None
    
    def get_updated_by(self):
        """Get the user who last updated this record"""
        if not self.updated_by_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            return User.objects.using('default').get(id=self.updated_by_id)
        except Exception as e:
            logger.error(f"Error fetching updated_by user: {e}")
            return None
    
    def get_audit_trail(self):
        """Get comprehensive audit information for this record"""
        return {
            'id': str(self.id),
            'created_at': self.created_at,
            'created_by_id': self.created_by_id,
            'created_from_ip': self.created_from_ip,
            'updated_at': self.updated_at,
            'updated_by_id': self.updated_by_id,
            'updated_from_ip': self.updated_from_ip,
            'last_change_reason': self.change_reason,
        }
    
    @property
    def created_by_name(self):
        """Get the name of the user who created this record"""
        user = self.get_created_by()
        if user:
            return user.get_full_name() or user.username
        return "System"
    
    @property
    def updated_by_name(self):
        """Get the name of the user who last updated this record"""
        user = self.get_updated_by()
        if user:
            return user.get_full_name() or user.username
        return "System"
    
    def _create_audit_log(self, action, changes):
        """Create an audit log entry for this change"""
        try:
            # Import here to avoid circular imports
            from utils.models import AuditLog
            from utils.context import get_request_context
            
            # Get request context (user, IP, etc.)
            context = get_request_context()
            
            # Get current database to ensure audit log goes to same DB
            current_db = get_current_db()
            
            # Prepare user information
            user_id = None
            user_email = ""
            user_name = ""
            
            if context and context.get('user'):
                user = context['user']
                user_id = str(user.id) if hasattr(user, 'id') else str(user.pk)
                user_email = getattr(user, 'email', '')
                user_name = getattr(user, 'get_full_name', lambda: str(user))()
            
            # Create audit log entry
            audit_log = AuditLog(
                content_type=f"{self._meta.app_label}.{self._meta.model_name}",
                object_id=str(self.pk),
                object_repr=str(self)[:200],
                action=action,
                changes=changes,
                user_id=user_id,
                user_email=user_email,
                user_name=user_name,
                ip_address=context.get('ip_address') if context else None,
                user_agent=context.get('user_agent', '')[:255] if context else '',
                change_reason=self.change_reason or '',
                session_key=context.get('session_key', '') if context else '',
                request_path=context.get('request_path', '') if context else '',
            )
            
            # Save to the same database as the model
            if current_db:
                audit_log.save(using=current_db)
            else:
                audit_log.save()
            
            logger.debug(f"Created audit log for {action} on {self._meta.label} {self.pk}")
            
        except Exception as e:
            # Don't fail the save/delete if audit logging fails
            logger.error(f"Failed to create audit log: {e}", exc_info=True)
    
    def get_history(self, limit=10):
        """
        Get audit history for this object.
        
        Args:
            limit: Maximum number of history entries to return
            
        Returns:
            QuerySet of AuditLog entries
        """
        try:
            from utils.models import AuditLog
            current_db = get_current_db()
            
            queryset = AuditLog.objects.filter(
                content_type=f"{self._meta.app_label}.{self._meta.model_name}",
                object_id=str(self.pk)
            )
            
            # Use correct database if available
            if current_db:
                queryset = queryset.using(current_db)
            
            return queryset.order_by('-timestamp')[:limit]
        except Exception as e:
            logger.error(f"Error fetching history: {e}")
            return []
    
    def set_change_reason(self, reason):
        """
        Set the reason for the next change to this object.
        
        Usage:
            student = Student.objects.get(id=some_id)
            student.status = "GRADUATED"
            student.set_change_reason("Student completed all requirements")
            student.save()
        
        Args:
            reason: String explaining why the change was made
        """
        self.change_reason = reason


# =============================================================================
# DEFAULT DATABASE MODEL - SYSTEM-WIDE DATA
# =============================================================================

class DefaultDatabaseModel(models.Model):
    """
    Base model for entities that ALWAYS use the default database.
    
    Use this for:
    - User accounts
    - School registry
    - System-wide configuration
    - Any cross-tenant data
    
    This model includes basic audit fields but forces all operations
    to the default database regardless of thread-local context.
    """
    
    # Core identification
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Timestamp fields
    created_at = models.DateTimeField("Created At", auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField("Updated At", auto_now=True, db_index=True)
    
    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=['created_at']),
            models.Index(fields=['updated_at']),
        ]
    
    def save(self, *args, **kwargs):
        """Force save to default database"""
        kwargs['using'] = 'default'
        return super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        """Force delete from default database"""
        kwargs['using'] = 'default'
        return super().delete(*args, **kwargs)
    
    def refresh_from_db(self, *args, **kwargs):
        """Force refresh from default database"""
        kwargs['using'] = 'default'
        return super().refresh_from_db(*args, **kwargs)

# =============================================================================
# AUDIT LOG MODEL
# =============================================================================

class AuditLog(models.Model):
    """
    Comprehensive audit trail for all model changes.
    
    Tracks:
    - What changed (model, object_id, field changes)
    - Who made the change (user)
    - When it happened (timestamp)
    - Where it came from (IP address)
    - Why it was changed (reason)
    
    This model is stored in the SAME database as the model being tracked,
    so each school database has its own audit trail.
    """
    
    ACTION_CHOICES = (
        ('CREATE', 'Created'),
        ('UPDATE', 'Updated'),
        ('DELETE', 'Deleted'),
    )
    
    # What was changed
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    content_type = models.CharField("Model Type", max_length=100, db_index=True)
    object_id = models.CharField("Object ID", max_length=100, db_index=True)
    object_repr = models.CharField("Object Representation", max_length=200)
    action = models.CharField("Action", max_length=10, choices=ACTION_CHOICES, db_index=True)
    
    # Field-level changes (JSON format)
    changes = models.JSONField(
        "Changes",
        help_text="Dictionary of field changes: {'field_name': {'old': 'value', 'new': 'value'}}",
        default=dict,
        blank=True
    )
    
    # Who made the change
    user_id = models.CharField("User ID", max_length=50, db_index=True, null=True, blank=True)
    user_email = models.EmailField("User Email", max_length=255, blank=True)
    user_name = models.CharField("User Name", max_length=255, blank=True)
    
    # When it happened
    timestamp = models.DateTimeField("Timestamp", auto_now_add=True, db_index=True)
    
    # Where it came from
    ip_address = models.GenericIPAddressField("IP Address", null=True, blank=True)
    user_agent = models.TextField("User Agent", blank=True)
    
    # Why it changed
    change_reason = models.CharField("Change Reason", max_length=255, blank=True)
    
    # Additional context
    session_key = models.CharField("Session Key", max_length=100, blank=True)
    request_path = models.CharField("Request Path", max_length=255, blank=True)
    
    # Use SchoolManager for automatic database routing
    objects = SchoolManager()
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['user_id', 'timestamp']),
            models.Index(fields=['timestamp']),
            models.Index(fields=['action']),
        ]
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"
    
    def __str__(self):
        return f"{self.action} {self.content_type} {self.object_id} at {self.timestamp}"
    
    def save(self, *args, **kwargs):
        """Route to current database"""
        current_db = get_current_db()
        if current_db and 'using' not in kwargs:
            kwargs['using'] = current_db
        return super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        """Route to current database"""
        current_db = get_current_db()
        if current_db and 'using' not in kwargs:
            kwargs['using'] = current_db
        return super().delete(*args, **kwargs)
    
    # -------------------------------------------------------------------------
    # AUDIT LOG HELPER METHODS
    # -------------------------------------------------------------------------
    
    def get_user(self):
        """Get the user who made this change"""
        if not self.user_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            return User.objects.using('default').get(id=self.user_id)
        except Exception as e:
            logger.error(f"Error fetching audit log user: {e}")
            return None
    
    def get_changes_display(self):
        """Get a human-readable display of changes"""
        if not self.changes:
            return "No field changes recorded"
        
        lines = []
        for field, change in self.changes.items():
            old_val = change.get('old', 'N/A')
            new_val = change.get('new', 'N/A')
            lines.append(f"{field}: '{old_val}' → '{new_val}'")
        
        return "\n".join(lines)
    
    def get_summary(self):
        """Get a brief summary of this audit entry"""
        user_display = self.user_name or self.user_email or self.user_id or "Unknown User"
        return f"{user_display} {self.get_action_display().lower()} {self.content_type}"
    
    @classmethod
    def get_recent_activity(cls, limit=50):
        """Get recent audit activity across all models"""
        return cls.objects.all().order_by('-timestamp')[:limit]
    
    @classmethod
    def get_user_activity(cls, user_id, limit=50):
        """Get recent activity for a specific user"""
        return cls.objects.filter(user_id=str(user_id)).order_by('-timestamp')[:limit]
    
    @classmethod
    def get_model_history(cls, model_label, limit=50):
        """Get history for a specific model type"""
        return cls.objects.filter(content_type=model_label).order_by('-timestamp')[:limit]
    
    @classmethod
    def get_object_history(cls, obj):
        """Get complete history for a specific object"""
        content_type = f"{obj._meta.app_label}.{obj._meta.model_name}"
        return cls.objects.filter(
            content_type=content_type,
            object_id=str(obj.pk)
        ).order_by('-timestamp')


# =============================================================================
# FINANCIAL AUDIT LOG
# =============================================================================

class FinancialAuditLog(models.Model):
    """
    Specialized audit log for financial transactions and sensitive operations.
    Provides enhanced tracking for compliance and security purposes.
    """
    
    # Financial-specific action types
    FINANCIAL_ACTIONS = [
        # Student financial actions
        ('INVOICE_CREATE', 'Invoice Created'),
        ('INVOICE_UPDATE', 'Invoice Updated'),
        ('INVOICE_CANCEL', 'Invoice Cancelled'),
        ('PAYMENT_RECEIVE', 'Payment Received'),
        ('PAYMENT_REFUND', 'Payment Refunded'),
        ('BALANCE_ADJUST', 'Student Balance Adjusted'),
        
        # Scholarship and discount actions
        ('SCHOLARSHIP_APPLY', 'Scholarship Applied'),
        ('SCHOLARSHIP_REMOVE', 'Scholarship Removed'),
        ('DISCOUNT_APPLY', 'Discount Applied'),
        ('DISCOUNT_REMOVE', 'Discount Removed'),
        
        # Administrative actions
        ('FEE_STRUCTURE_CREATE', 'Fee Structure Created'),
        ('FEE_STRUCTURE_UPDATE', 'Fee Structure Updated'),
        ('BULK_INVOICE_CREATE', 'Bulk Invoice Generation'),
        ('FINANCIAL_REPORT_GENERATE', 'Financial Report Generated'),
        
        # Security actions
        ('FINANCIAL_DATA_EXPORT', 'Financial Data Exported'),
        ('SETTINGS_CHANGE', 'Financial Settings Changed'),
        ('USER_ACCESS_FINANCIAL', 'Financial Module Accessed'),
        
        # System actions
        ('ACCOUNT_CREATE', 'Account Created'),
        ('ACCOUNT_UPDATE', 'Account Updated'),
        ('JOURNAL_POST', 'Journal Entry Posted'),
        ('RECONCILIATION', 'Account Reconciliation'),
        
        # Enhanced actions
        ('EXPENSE_CREATE', 'Expense Created'),
        ('EXPENSE_APPROVE', 'Expense Approved'),
        ('BUDGET_CREATE', 'Budget Created'),
        ('BUDGET_APPROVE', 'Budget Approved'),
    ]
    
    # Core audit fields
    id = models.AutoField(primary_key=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    action = models.CharField(max_length=30, choices=FINANCIAL_ACTIONS, db_index=True)
    
    # User information
    user_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    user_name = models.CharField(max_length=200, null=True, blank=True)
    user_role = models.CharField(max_length=100, null=True, blank=True)
    
    # Session and request context
    session_key = models.CharField(max_length=40, null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    user_agent = models.TextField(null=True, blank=True)
    
    # Target object (what was changed)
    content_type = models.ForeignKey(
        ContentType, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True
    )
    object_id = models.CharField(max_length=100, null=True, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')
    object_description = models.CharField(max_length=500, null=True, blank=True)
    
    # Financial-specific fields
    amount_involved = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Monetary amount involved in the action"
    )
    currency = models.CharField(max_length=3, null=True, blank=True, default='UGX')
    
    # Student context (for student-related financial actions)
    student_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    student_name = models.CharField(max_length=200, null=True, blank=True)
    student_admission_number = models.CharField(max_length=50, null=True, blank=True)
    
    # Academic context
    academic_session_id = models.CharField(max_length=100, null=True, blank=True)
    academic_session_name = models.CharField(max_length=100, null=True, blank=True)
    
    # Change tracking
    old_values = models.JSONField(null=True, blank=True, help_text="Values before change")
    new_values = models.JSONField(null=True, blank=True, help_text="Values after change")
    changes_summary = models.TextField(null=True, blank=True, help_text="Human-readable summary of changes")
    
    # Risk and compliance
    risk_level = models.CharField(
        max_length=10,
        choices=[
            ('LOW', 'Low Risk'),
            ('MEDIUM', 'Medium Risk'),
            ('HIGH', 'High Risk'),
            ('CRITICAL', 'Critical Risk'),
        ],
        default='LOW',
        db_index=True
    )
    compliance_flags = models.JSONField(
        default=list, 
        blank=True,
        help_text="Compliance-related flags or concerns"
    )
    
    # Additional context
    additional_data = models.JSONField(
        default=dict, 
        blank=True,
        help_text="Additional context-specific data"
    )
    notes = models.TextField(null=True, blank=True)
    
    # Processing information
    is_automated = models.BooleanField(
        default=False,
        help_text="Whether this action was performed automatically by the system"
    )
    batch_id = models.CharField(
        max_length=100, 
        null=True, 
        blank=True,
        help_text="For grouping related bulk operations"
    )
    
    # Use SchoolManager for automatic database routing
    objects = SchoolManager()
    
    class Meta:
        verbose_name = "Financial Audit Log"
        verbose_name_plural = "Financial Audit Logs"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['timestamp', 'action']),
            models.Index(fields=['user_id', 'timestamp']),
            models.Index(fields=['student_id', 'timestamp']),
            models.Index(fields=['risk_level', 'timestamp']),
            models.Index(fields=['ip_address', 'timestamp']),
            models.Index(fields=['academic_session_id', 'action']),
        ]
    
    def __str__(self):
        return f"{self.get_action_display()} at {self.timestamp}"
    
    def save(self, *args, **kwargs):
        """Route to current database"""
        current_db = get_current_db()
        if current_db and 'using' not in kwargs:
            kwargs['using'] = current_db
        return super().save(*args, **kwargs)
    
    # -------------------------------------------------------------------------
    # CLASS METHODS - Creating Financial Audit Logs
    # -------------------------------------------------------------------------
    
    @classmethod
    def log_financial_action(
        cls,
        action,
        user=None,
        request=None,
        target_object=None,
        amount=None,
        student=None,
        academic_session=None,
        old_values=None,
        new_values=None,
        risk_level='LOW',
        additional_data=None,
        notes=None,
        currency=None,
        **kwargs
    ):
        """
        Class method to log financial actions.

        Handles:
        - academic_session as object or string/UUID
        - currency as object or string (or None → default 'UGX')
        
        Args:
            action: Action type from FINANCIAL_ACTIONS
            user: User performing the action
            request: Django request object
            target_object: Object being acted upon
            amount: Monetary amount involved
            student: Student object (for student-related actions)
            academic_session: Academic session/period
            old_values: Values before change
            new_values: Values after change
            risk_level: Risk level of the action
            additional_data: Additional contextual data
            notes: Optional notes
            currency: Currency code or object
            **kwargs: Additional parameters
            
        Returns:
            FinancialAuditLog: Created audit log entry or None if failed
        """
        from django.utils import timezone
        from django.contrib.contenttypes.models import ContentType

        try:
            # Prepare base log payload
            log_data = {
                'action': action,
                'risk_level': risk_level,
                'timestamp': timezone.now(),
                'notes': (notes or '')[:2000],  # Limit length
                'old_values': old_values,
                'new_values': new_values,
                'additional_data': (additional_data or {}),
                'is_automated': bool(kwargs.get('is_automated', False)),
                'batch_id': kwargs.get('batch_id'),
            }
            
            # Handle currency
            if currency:
                if hasattr(currency, 'code'):
                    log_data['currency'] = currency.code
                else:
                    log_data['currency'] = str(currency)[:3].upper()
            else:
                log_data['currency'] = 'UGX'
            
            # Handle amount
            if amount is not None:
                try:
                    log_data['amount_involved'] = Decimal(str(amount))
                except (ValueError, InvalidOperation, TypeError):
                    logger.warning(f"Invalid amount for financial audit log: {amount}")
                    log_data['amount_involved'] = None

            # User info
            if user:
                full_name = getattr(user, 'get_full_name', lambda: '')() or getattr(user, 'username', '') or str(user)
                role = getattr(user, 'role', '') or getattr(user, 'user_type', '') or ''
                log_data.update({
                    'user_id': str(getattr(user, 'pk', '')),
                    'user_name': full_name[:200],
                    'user_role': role[:100],
                })

            # Request info
            if request:
                session_key = getattr(getattr(request, 'session', None), 'session_key', None)
                user_agent = getattr(request, 'META', {}).get('HTTP_USER_AGENT', '')
                # Safe IP extraction
                xff = getattr(request, 'META', {}).get('HTTP_X_FORWARDED_FOR')
                ip = (xff.split(',')[0].strip() if xff else getattr(request, 'META', {}).get('REMOTE_ADDR', ''))
                log_data.update({
                    'session_key': session_key,
                    'ip_address': ip,
                    'user_agent': user_agent[:512],
                })

            # Target object info
            if target_object is not None:
                try:
                    ct = ContentType.objects.get_for_model(target_object, for_concrete_model=False)
                except Exception:
                    ct = None
                log_data.update({
                    'content_type': ct,
                    'object_id': str(getattr(target_object, 'pk', '')),
                    'object_description': (str(target_object)[:500] if target_object is not None else ''),
                })

            # Student info
            if student:
                student_name = getattr(student, 'get_full_name', lambda: str(student))()
                log_data.update({
                    'student_id': str(getattr(student, 'pk', '')),
                    'student_name': student_name[:200],
                    'student_admission_number': str(getattr(student, 'admission_number', ''))[:50],
                })

            # Academic session
            if academic_session:
                try:
                    if hasattr(academic_session, 'pk'):
                        log_data.update({
                            'academic_session_id': str(academic_session.pk),
                            'academic_session_name': str(academic_session)[:100],
                        })
                    else:
                        # String or unknown type
                        session_str = str(academic_session)
                        # Try resolve UUID → object
                        try:
                            import uuid as uuid_lib
                            from core.models import Period
                            uuid_lib.UUID(session_str)
                            session_obj = Period.objects.filter(id=session_str).first()
                        except Exception:
                            session_obj = None

                        if session_obj:
                            log_data.update({
                                'academic_session_id': str(session_obj.pk),
                                'academic_session_name': str(session_obj)[:100],
                            })
                        else:
                            log_data.update({
                                'academic_session_id': session_str[:100],
                                'academic_session_name': session_str[:100],
                            })
                except Exception as session_error:
                    logger.warning(f"Error processing academic_session for audit log: {session_error}")
                    ss = str(academic_session)
                    log_data.update({
                        'academic_session_id': ss[:100],
                        'academic_session_name': ss[:100],
                    })

            return cls.objects.create(**log_data)

        except Exception as e:
            logger.error(f"Error creating financial audit log: {e}", exc_info=True)
            return None
    
    # -------------------------------------------------------------------------
    # INSTANCE METHODS
    # -------------------------------------------------------------------------
    
    def get_user(self):
        """Get the user who performed this action"""
        if not self.user_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            return User.objects.using('default').get(id=self.user_id)
        except Exception as e:
            logger.error(f"Error fetching financial audit user: {e}")
            return None
    
    def get_student(self):
        """Get the student associated with this action"""
        if not self.student_id:
            return None
        try:
            from students.models import Student
            return Student.objects.get(id=self.student_id)
        except Exception as e:
            logger.error(f"Error fetching student: {e}")
            return None
    
    def get_summary(self):
        """Get a brief summary of this financial audit entry"""
        parts = []
        
        # User
        if self.user_name:
            parts.append(self.user_name)
        elif self.user_id:
            parts.append(f"User {self.user_id}")
        else:
            parts.append("System")
        
        # Action
        parts.append(self.get_action_display().lower())
        
        # Student (if applicable)
        if self.student_name:
            parts.append(f"for {self.student_name}")
        
        # Amount (if applicable)
        if self.amount_involved:
            parts.append(f"({self.currency} {self.amount_involved:,.2f})")
        
        return " ".join(parts)
    
    def get_risk_badge_class(self):
        """Get CSS class for risk level badge"""
        risk_classes = {
            'LOW': 'badge-success',
            'MEDIUM': 'badge-warning',
            'HIGH': 'badge-danger',
            'CRITICAL': 'badge-dark',
        }
        return risk_classes.get(self.risk_level, 'badge-secondary')
    
    # -------------------------------------------------------------------------
    # QUERY METHODS
    # -------------------------------------------------------------------------
    
    @classmethod
    def get_recent_activity(cls, limit=50):
        """Get recent financial activity"""
        return cls.objects.all().order_by('-timestamp')[:limit]
    
    @classmethod
    def get_high_risk_actions(cls, days=30):
        """Get high-risk actions from recent days"""
        from django.utils import timezone
        from datetime import timedelta
        
        cutoff_date = timezone.now() - timedelta(days=days)
        return cls.objects.filter(
            timestamp__gte=cutoff_date,
            risk_level__in=['HIGH', 'CRITICAL']
        ).order_by('-timestamp')
    
    @classmethod
    def get_student_financial_history(cls, student_id, limit=50):
        """Get financial history for a specific student"""
        return cls.objects.filter(
            student_id=str(student_id)
        ).order_by('-timestamp')[:limit]
    
    @classmethod
    def get_user_financial_actions(cls, user_id, limit=50):
        """Get financial actions performed by a specific user"""
        return cls.objects.filter(
            user_id=str(user_id)
        ).order_by('-timestamp')[:limit]
    
    @classmethod
    def get_actions_by_type(cls, action_type, limit=50):
        """Get actions of a specific type"""
        return cls.objects.filter(
            action=action_type
        ).order_by('-timestamp')[:limit]
    
    @classmethod
    def get_session_financial_activity(cls, session_id):
        """Get all financial activity for an academic session"""
        return cls.objects.filter(
            academic_session_id=str(session_id)
        ).order_by('-timestamp')
    
    @classmethod
    def get_amount_summary(cls, action_type=None, days=30):
        """Get summary of amounts involved in financial actions"""
        from django.utils import timezone
        from datetime import timedelta
        from django.db.models import Sum, Count, Avg
        
        cutoff_date = timezone.now() - timedelta(days=days)
        queryset = cls.objects.filter(timestamp__gte=cutoff_date)
        
        if action_type:
            queryset = queryset.filter(action=action_type)
        
        return queryset.aggregate(
            total_amount=Sum('amount_involved'),
            count=Count('id'),
            average_amount=Avg('amount_involved')
        )