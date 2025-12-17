# utils/models.py

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from schoolara.managers import get_current_db, SchoolManager
from datetime import date
import uuid
from djmoney.models.fields import MoneyField, CurrencyField
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
    
    # User tracking - REDUCED from 100 to 50
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
        1. Automatically route to correct database
        2. Capture audit trail information
        3. Create audit log entry
        """
        # Determine if this is a new object
        is_new = self._state.adding
        
        # Track changes for existing objects
        changes = {}
        if not is_new and self.pk:
            try:
                # Get old instance from database
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
                pass  # Object doesn't exist yet, treat as new
        
        # Get current database context
        current_db = get_current_db()
        
        # Only set 'using' if not already specified and we have a database context
        if current_db and 'using' not in kwargs:
            kwargs['using'] = current_db
            logger.debug(f"Saving {self.__class__.__name__} to {current_db}")
        
        # Save the object
        result = super().save(*args, **kwargs)
        
        # Create audit log entry (only if we have a database context)
        if current_db and current_db != 'default':
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
        if current_db and current_db != 'default':
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
            
            return AuditLog.objects.filter(
                content_type=f"{self._meta.app_label}.{self._meta.model_name}",
                object_id=str(self.pk)
            ).order_by('-timestamp')[:limit]
        except Exception as e:
            logger.error(f"Error fetching history: {e}")
            return []
        
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
    
    # Who made the change - REDUCED from 100 to 50
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

# =============================================================================
# FINANCIAL AUDIT LOG
# =============================================================================

class FinancialAuditLog(models.Model):
    """Specialized audit log for financial transactions and sensitive operations"""
    
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
        
        # Enhanced actions from utils integration
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
    currency = models.CharField(max_length=3, null=True, blank=True)
    
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
        """
        from decimal import Decimal, InvalidOperation
        from django.utils import timezone
        from django.contrib.contenttypes.models import ContentType
        import logging

        logger = logging.getLogger(__name__)

        try:
            # Prepare base log payload
            log_data = {
                'action': action,
                'risk_level': risk_level,
                'timestamp': timezone.now(),
                'notes': (notes or '')[:2000],  # keep it bounded
                'old_values': old_values,
                'new_values': new_values,
                'additional_data': (additional_data or {}),
                'is_automated': bool(kwargs.get('is_automated', False)),
                'batch_id': kwargs.get('batch_id'),
            }

            # User info
            if user:
                # get_full_name() may exist but return ''
                full_name = getattr(user, 'get_full_name', lambda: '')() or getattr(user, 'username', '') or str(user)
                role = getattr(user, 'role', '') or getattr(user, 'user_type', '') or ''
                log_data.update({
                    'user_id': str(getattr(user, 'pk', '')),
                    'user_name': full_name[:255],
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
                    'student_name': student_name[:255],
                    'student_admission_number': str(getattr(student, 'admission_number', ''))[:64],
                })

            # Academic session
            if academic_session:
                try:
                    if hasattr(academic_session, 'pk'):
                        log_data.update({
                            'academic_session_id': str(academic_session.pk),
                            'academic_session_name': str(academic_session)[:255],
                        })
                    else:
                        # string or unknown type
                        session_str = str(academic_session)
                        # Try resolve UUID → object
                        try:
                            import uuid
                            from academics.models import AcademicSession
                            uuid.UUID(session_str)
                            session_obj = AcademicSession.objects.filter(id=session_str).first()
                        except Exception:
                            session_obj = None

                        if session_obj:
                            log_data.update({
                                'academic_session_id': str(session_obj.pk),
                                'academic_session_name': str(session_obj)[:255],
                            })
                        else:
                            log_data.update({
                                'academic_session_id': session_str[:64],
                                'academic_session_name': session_str[:255],
                            })
                except Exception as session_error:
                    logger.warning(f"Error processing academic_session for audit log: {session_error}")
                    ss = str(academic_session)
                    log_data.update({
                        'academic_session_id': ss[:64],
                        'academic_session_name': ss[:255],
                    })

            return cls.objects.create(**log_data)

        except Exception as e:
            logger.error(f"Error creating financial audit log: {e}", exc_info=True)
            return None

    @staticmethod
    def _get_client_ip(request):
        """Get client IP from request"""
        try:
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip = x_forwarded_for.split(',')[0]
            else:
                ip = request.META.get('REMOTE_ADDR')
            return ip
        except:
            return None
    
    @staticmethod
    def _get_client_ip(request):
        """Get client IP from request"""
        try:
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip = x_forwarded_for.split(',')[0]
            else:
                ip = request.META.get('REMOTE_ADDR')
            return ip
        except:
            return None
        
# =============================================================================
# SCHOOL ACADEMIC & CONFIGURATION MODEL
# =============================================================================

class FinancialSettings(BaseModel):
    """Model for managing core financial settings for the school"""

    # -------------------------------------------------------------------------
    # CHOICE FIELDS
    # -------------------------------------------------------------------------

    CURRENCY_POSITION_CHOICES = [
        ('BEFORE', 'Before amount (UGX 100.00)'),
        ('AFTER', 'After amount (100.00 UGX)'),
        ('BEFORE_NO_SPACE', 'Before, no space (UGX100.00)'),
        ('AFTER_NO_SPACE', 'After, no space (100.00UGX)'),
    ]

    # -------------------------------------------------------------------------
    # CORE CONFIGURATION
    # -------------------------------------------------------------------------

    school_currency = CurrencyField(
        "School Primary Currency",
        default='UGX',
        help_text="Primary currency for this school"
    )

    currency_position = models.CharField(
        "Currency Position",
        max_length=20,
        choices=CURRENCY_POSITION_CHOICES,
        default='BEFORE'
    )

    decimal_places = models.PositiveIntegerField(
        "Decimal Places",
        default=2,
        validators=[MinValueValidator(0), MaxValueValidator(4)],
        help_text="Number of decimal places for currency display"
    )

    use_thousand_separator = models.BooleanField(
        "Use Thousand Separator",
        default=True
    )

    # -------------------------------------------------------------------------
    # PAYMENT SETTINGS
    # -------------------------------------------------------------------------

    default_payment_terms_days = models.PositiveIntegerField(
        "Default Payment Terms (Days)",
        default=30
    )

    late_fee_enabled = models.BooleanField(
        "Enable Late Fees",
        default=True
    )

    late_fee_percentage = models.DecimalField(
        "Default Late Fee Percentage",
        max_digits=5,
        decimal_places=2,
        default=Decimal('5.00'),
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))]
    )

    grace_period_days = models.PositiveIntegerField(
        "Default Grace Period (Days)",
        default=7
    )

    minimum_payment_amount = models.DecimalField(
        "Minimum Payment Amount",
        max_digits=12,
        decimal_places=2,
        default=Decimal('1000.00'),
        help_text="Minimum amount for any payment transaction in school currency"
    )

    # -------------------------------------------------------------------------
    # WORKFLOW SETTINGS
    # -------------------------------------------------------------------------

    auto_apply_scholarships = models.BooleanField(
        "Auto Apply Scholarships",
        default=True
    )

    scholarship_approval_required = models.BooleanField(
        "Scholarship Approval Required",
        default=False
    )

    auto_apply_discounts = models.BooleanField(
        "Auto Apply Discounts",
        default=True
    )

    discount_approval_required = models.BooleanField(
        "Discount Approval Required",
        default=True
    )

    expense_approval_required = models.BooleanField(
        "Expense Approval Required",
        default=True
    )

    expense_approval_limit = models.DecimalField(
        "Expense Approval Limit",
        max_digits=12,
        decimal_places=2,
        default=Decimal('100000.00')
    )

    # -------------------------------------------------------------------------
    # COMMUNICATION SETTINGS
    # -------------------------------------------------------------------------

    send_invoice_emails = models.BooleanField(
        "Send Invoice Emails",
        default=True
    )

    send_payment_confirmations = models.BooleanField(
        "Send Payment Confirmations",
        default=True
    )

    send_overdue_reminders = models.BooleanField(
        "Send Overdue Reminders",
        default=True
    )

    # -------------------------------------------------------------------------
    # CORE METHODS
    # -------------------------------------------------------------------------

    @classmethod
    def get_settings(cls):
        """Return the first financial settings instance"""
        return cls.objects.first()

    @classmethod
    def get_school_currency(cls):
        """Return school currency code"""
        settings = cls.get_settings()
        return settings.school_currency.code if settings else 'UGX'

    @classmethod
    def get_currency_info(cls):
        """Return full currency configuration"""
        settings = cls.get_settings()
        if settings:
            return {
                'code': settings.school_currency.code,
                'decimal_places': settings.decimal_places,
                'position': settings.currency_position,
                'use_separator': settings.use_thousand_separator,
            }
        return {
            'code': 'UGX',
            'decimal_places': 2,
            'position': 'BEFORE',
            'use_separator': True,
        }

    def format_currency(self, amount, include_symbol=True):
        """Format amount based on school settings"""
        try:
            amount = Decimal(str(amount or 0))
            formatted = f"{amount:,.{self.decimal_places}f}"

            if not self.use_thousand_separator:
                formatted = formatted.replace(',', '')

            if include_symbol:
                symbol = self.school_currency.code
                if self.currency_position == 'BEFORE':
                    return f"{symbol} {formatted}"
                elif self.currency_position == 'AFTER':
                    return f"{formatted} {symbol}"
                elif self.currency_position == 'BEFORE_NO_SPACE':
                    return f"{symbol}{formatted}"
                elif self.currency_position == 'AFTER_NO_SPACE':
                    return f"{formatted}{symbol}"
            return formatted

        except (ValueError, TypeError, InvalidOperation):
            return f"{self.school_currency.code} 0.{'0' * self.decimal_places}"

    @classmethod
    def format_amount(cls, amount, include_symbol=True):
        settings = cls.get_settings()
        return settings.format_currency(amount, include_symbol) if settings else f"UGX {amount:,.2f}"

    # -------------------------------------------------------------------------
    # VALIDATION METHODS
    # -------------------------------------------------------------------------

    def clean(self):
        """Validate financial settings"""
        super().clean()
        errors = {}

        if not (0 <= self.decimal_places <= 4):
            errors['decimal_places'] = "Decimal places must be between 0 and 4"

        if not (0 <= self.late_fee_percentage <= 100):
            errors['late_fee_percentage'] = "Late fee percentage must be between 0 and 100"

        if self.minimum_payment_amount <= 0:
            errors['minimum_payment_amount'] = "Minimum payment amount must be positive"

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """Save with validation"""
        self.full_clean()
        super().save(*args, **kwargs)

    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------

    def __str__(self):
        return f"Financial Settings - {self.school_currency.code}"

class SchoolConfiguration(BaseModel):
    """Enhanced configuration model for maximum flexibility across all school term systems"""
    
    # -------------------------------------------------------------------------
    # TERM SYSTEM CONFIGURATION
    # -------------------------------------------------------------------------
    
    TERM_SYSTEM_CHOICES = [
        ('term', 'Terms (3 per year)'),
        ('semester', 'Semesters (2 per year)'),
        ('quarter', 'Quarters (4 per year)'),
        ('trimester', 'Trimesters (3 per year)'),
        ('module', 'Modules (6-8 per year)'),
        ('block', 'Block Schedule (4-6 per year)'),
        ('yearlong', 'Year-long Program (1 per year)'),
        ('intensive', 'Intensive Programs (8-12 per year)'),
        ('custom', 'Custom System'),
    ]
    
    term_system = models.CharField(
        "Academic Period System",
        max_length=15,
        choices=TERM_SYSTEM_CHOICES,
        default='term',
        help_text="The academic period system used by the school"
    )
    
    periods_per_year = models.PositiveIntegerField(
        "Periods Per Year",
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(20)],
        help_text="Number of academic periods in one academic year (1-20)"
    )
    
    # -------------------------------------------------------------------------
    # PERIOD NAMING CONFIGURATION
    # -------------------------------------------------------------------------
    
    period_naming_convention = models.CharField(
        "Period Naming Convention",
        max_length=20,
        choices=[
            ('numeric', 'Numeric (Term 1, Term 2, etc.)'),
            ('ordinal', 'Ordinal (First Term, Second Term, etc.)'),
            ('seasonal', 'Seasonal (Fall, Spring, Summer)'),
            ('monthly', 'Monthly (January, February, etc.)'),
            ('alpha', 'Alphabetical (Term A, Term B, etc.)'),
            ('roman', 'Roman Numerals (Term I, Term II, etc.)'),
            ('custom', 'Custom Names'),
        ],
        default='numeric'
    )
    
    custom_period_names = models.JSONField(
        "Custom Period Names",
        default=dict,
        blank=True,
        help_text='Custom names for each period position. E.g., {"1": "Fall Semester", "2": "Spring Semester"}'
    )
    
    # -------------------------------------------------------------------------
    # ACADEMIC YEAR CONFIGURATION
    # -------------------------------------------------------------------------
    
    MONTH_CHOICES = [
        (1, 'January'), (2, 'February'), (3, 'March'), (4, 'April'),
        (5, 'May'), (6, 'June'), (7, 'July'), (8, 'August'),
        (9, 'September'), (10, 'October'), (11, 'November'), (12, 'December')
    ]
    
    ACADEMIC_YEAR_TYPE_CHOICES = [
        ('calendar', 'Calendar Year (Jan-Dec)'),
        ('northern', 'Northern Hemisphere (Sep-Jun)'),
        ('southern', 'Southern Hemisphere (Feb-Nov)'),
        ('tropical', 'Tropical Regions (Jan-Nov)'),
        ('east_africa', 'East African Calendar (Jan-Nov)'),
        ('west_africa', 'West African Calendar (Sep-Jul)'),
        ('sahel', 'Sahel Region (Oct-Jun)'),
        ('financial', 'Financial Year (Apr-Mar)'),
        ('custom', 'Custom Year Dates'),
    ]
    
    academic_year_type = models.CharField(
        "Academic Year Type",
        max_length=15,
        choices=ACADEMIC_YEAR_TYPE_CHOICES,
        default='northern',
        help_text="When your academic year typically runs"
    )
    
    academic_year_start_month = models.PositiveIntegerField(
        "Academic Year Start Month",
        choices=MONTH_CHOICES,
        default=9,  # September
        validators=[MinValueValidator(1), MaxValueValidator(12)],
        help_text="Month when academic year typically starts (1-12)"
    )
    
    academic_year_start_day = models.PositiveIntegerField(
        "Academic Year Start Day",
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
        help_text="Day when academic year typically starts"
    )
    
    # -------------------------------------------------------------------------
    # REGIONAL SEASON CONFIGURATION
    # -------------------------------------------------------------------------
    
    REGIONAL_SEASON_CHOICES = [
        ('temperate', 'Temperate (Spring/Summer/Fall/Winter)'),
        ('tropical_wet_dry', 'Tropical (Wet/Dry Seasons)'),
        ('desert', 'Desert (Hot/Cool Seasons)'),
        ('equatorial', 'Equatorial (Year-round)'),
        ('monsoon', 'Monsoon (Pre/Monsoon/Post)'),
        ('custom_regional', 'Custom Regional Seasons'),
    ]
    
    regional_season_type = models.CharField(
        "Regional Season Type",
        max_length=20,
        choices=REGIONAL_SEASON_CHOICES,
        default='temperate',
        help_text="Climate-based season naming for your region"
    )
    
    custom_season_names = models.JSONField(
        "Custom Season Names",
        default=dict,
        blank=True,
        help_text="Regional season names. E.g., {'1': 'Harmattan', '2': 'Rainy Season'}"
    )
    
    # -------------------------------------------------------------------------
    # BREAK CONFIGURATION
    # -------------------------------------------------------------------------
    
    auto_create_breaks = models.BooleanField(
        "Auto-Create Term Breaks",
        default=True,
        help_text="Automatically create holiday records for breaks between terms"
    )
    
    minimum_break_days = models.PositiveIntegerField(
        "Minimum Break Days",
        default=1,
        help_text="Minimum number of days for a break to be considered significant"
    )
    
    default_period_duration_weeks = models.PositiveIntegerField(
        "Default Period Duration (weeks)",
        default=12,
        validators=[MinValueValidator(1), MaxValueValidator(52)],
        help_text="Typical duration of each academic period in weeks"
    )
    
    # -------------------------------------------------------------------------
    # COMMUNICATION CONFIGURATION
    # -------------------------------------------------------------------------
    
    enable_automatic_reminders = models.BooleanField(
        "Enable Automatic Reminders",
        default=True,
        help_text="Send automatic payment and deadline reminders"
    )

    enable_sms = models.BooleanField(
        "Enable SMS Notifications",
        default=False,
        help_text="Send SMS notifications to parents and students"
    )

    enable_email_notifications = models.BooleanField(
        "Enable Email Notifications",
        default=True,
        help_text="Send email notifications"
    )
    
    # -------------------------------------------------------------------------
    # VALIDATION METHODS
    # -------------------------------------------------------------------------
    
    def clean(self):
        """Enhanced validation for the configuration"""
        super().clean()
        errors = {}
        
        # Validate periods_per_year matches term_system for non-custom systems
        if self.term_system != 'custom':
            expected_periods = self._get_system_period_count(self.term_system)
            if self.periods_per_year != expected_periods:
                # Auto-correct instead of raising error
                self.periods_per_year = expected_periods
        
        # Validate custom period names if using custom naming
        if self.period_naming_convention == 'custom':
            if not self.custom_period_names:
                errors['custom_period_names'] = 'Custom period names are required when using custom naming convention'
            else:
                # Ensure we have names for all periods
                missing_periods = []
                for i in range(1, self.periods_per_year + 1):
                    if str(i) not in self.custom_period_names:
                        missing_periods.append(str(i))
                
                if missing_periods:
                    errors['custom_period_names'] = f'Missing custom names for periods: {", ".join(missing_periods)}'
        
        # Validate academic year dates
        if self.academic_year_type == 'custom':
            try:
                # Test if the date is valid
                test_date = date(2024, self.academic_year_start_month, self.academic_year_start_day)
            except ValueError:
                errors['academic_year_start_day'] = 'Invalid academic year start date'
        
        if errors:
            raise ValidationError(errors)
    
    # -------------------------------------------------------------------------
    # HELPER METHODS - PERIOD SYSTEM
    # -------------------------------------------------------------------------
    
    def _get_system_period_count(self, system):
        """Get the standard period count for each system"""
        return {
            'term': 3,
            'semester': 2,
            'quarter': 4,
            'trimester': 3,
            'module': 6,
            'block': 4,
            'yearlong': 1,
            'intensive': 10,  # Average for intensive programs
            'custom': self.periods_per_year
        }.get(system, 3)
    
    def get_period_count(self):
        """Returns the number of periods per year"""
        if self.term_system == 'custom':
            return self.periods_per_year
        return self._get_system_period_count(self.term_system)
    
    # -------------------------------------------------------------------------
    # PERIOD NAMING METHODS
    # -------------------------------------------------------------------------
    
    def get_period_name(self, position, include_year=False, academic_year=None):
        """Enhanced period naming with more options"""
        max_periods = self.get_period_count()
        
        if position > max_periods or position < 1:
            return None
        
        # Handle custom names first
        if self.period_naming_convention == 'custom' and self.custom_period_names:
            base_name = self.custom_period_names.get(str(position))
            if base_name:
                return self._format_period_name(base_name, include_year, academic_year)
        
        # Handle different naming conventions
        if self.period_naming_convention == 'seasonal':
            base_name = self._get_seasonal_name(position)
        elif self.period_naming_convention == 'ordinal':
            base_name = self._get_ordinal_name(position)
        elif self.period_naming_convention == 'monthly':
            base_name = self._get_monthly_name(position)
        elif self.period_naming_convention == 'alpha':
            base_name = self._get_alpha_name(position)
        elif self.period_naming_convention == 'roman':
            base_name = self._get_roman_name(position)
        else:  # numeric
            base_name = self._get_numeric_name(position)
        
        return self._format_period_name(base_name, include_year, academic_year)
    
    def _format_period_name(self, base_name, include_year=False, academic_year=None):
        """Format the period name with optional year"""
        if include_year and academic_year:
            return f"{base_name} {academic_year}"
        return base_name
    
    def _get_seasonal_name(self, position):
        """Enhanced seasonal naming based on academic year type and period count"""
        period_count = self.get_period_count()
        period_type = self._get_period_type_name()
        
        # Use regional seasonal patterns
        if self.regional_season_type == 'tropical_wet_dry':
            if period_count == 2:
                seasons = {1: 'Dry Season', 2: 'Rainy Season'}
            elif period_count == 3:
                seasons = {1: 'Cool Dry', 2: 'Hot Dry', 3: 'Rainy Season'}
            else:
                seasons = {i+1: f"Period {i+1}" for i in range(period_count)}
        elif self.regional_season_type == 'desert':
            if period_count == 2:
                seasons = {1: 'Cool Season', 2: 'Hot Season'}
            elif period_count == 3:
                seasons = {1: 'Cool', 2: 'Hot', 3: 'Harmattan'}
            else:
                seasons = {i+1: f"Period {i+1}" for i in range(period_count)}
        elif self.regional_season_type == 'equatorial':
            return f"Period {position} {period_type}"
        elif self.regional_season_type == 'custom_regional' and self.custom_season_names:
            season = self.custom_season_names.get(str(position), f"Period {position}")
            return f"{season} {period_type}"
        else:
            # Temperate/Northern hemisphere seasons
            if period_count == 2:
                seasons = {1: 'Fall', 2: 'Spring'}
            elif period_count == 3:
                seasons = {1: 'Fall', 2: 'Spring', 3: 'Summer'}
            elif period_count == 4:
                seasons = {1: 'Fall', 2: 'Winter', 3: 'Spring', 4: 'Summer'}
            else:
                seasons = {i+1: f"Period {i+1}" for i in range(period_count)}
        
        season = seasons.get(position, f"Period {position}")
        return f"{season} {period_type}"
    
    def _get_ordinal_name(self, position):
        """Get ordinal names (First, Second, etc.)"""
        ordinals = [
            '', 'First', 'Second', 'Third', 'Fourth', 'Fifth', 
            'Sixth', 'Seventh', 'Eighth', 'Ninth', 'Tenth',
            'Eleventh', 'Twelfth', 'Thirteenth', 'Fourteenth', 'Fifteenth',
            'Sixteenth', 'Seventeenth', 'Eighteenth', 'Nineteenth', 'Twentieth'
        ]
        period_type = self._get_period_type_name()
        
        if position < len(ordinals):
            return f"{ordinals[position]} {period_type}"
        else:
            return f"{position}th {period_type}"
    
    def _get_monthly_name(self, position):
        """Get monthly names for systems that align with months"""
        months = [
            '', 'January', 'February', 'March', 'April', 'May', 'June',
            'July', 'August', 'September', 'October', 'November', 'December'
        ]
        
        # Start from academic year start month
        start_month = self.academic_year_start_month
        month_index = ((start_month - 1 + position - 1) % 12) + 1
        
        if month_index < len(months):
            period_type = self._get_period_type_name()
            return f"{months[month_index]} {period_type}"
        else:
            return self._get_numeric_name(position)
    
    def _get_alpha_name(self, position):
        """Get alphabetical names (A, B, C, etc.)"""
        import string
        period_type = self._get_period_type_name()
        
        if position <= 26:
            letter = string.ascii_uppercase[position - 1]
            return f"{period_type} {letter}"
        else:
            # For more than 26 periods, use AA, AB, etc.
            first_letter = string.ascii_uppercase[(position - 1) // 26]
            second_letter = string.ascii_uppercase[(position - 1) % 26]
            return f"{period_type} {first_letter}{second_letter}"
    
    def _get_roman_name(self, position):
        """Get Roman numeral names"""
        def int_to_roman(num):
            values = [1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1]
            symbols = ['M', 'CM', 'D', 'CD', 'C', 'XC', 'L', 'XL', 'X', 'IX', 'V', 'IV', 'I']
            result = ''
            for i, value in enumerate(values):
                count = num // value
                result += symbols[i] * count
                num -= value * count
            return result
        
        period_type = self._get_period_type_name()
        roman = int_to_roman(position)
        return f"{period_type} {roman}"
    
    def _get_numeric_name(self, position):
        """Get numeric names (Term 1, Term 2, etc.)"""
        period_type = self._get_period_type_name()
        return f"{period_type} {position}"
    
    def _get_period_type_name(self):
        """Enhanced period type name getter"""
        type_names = {
            'term': 'Term',
            'semester': 'Semester',
            'quarter': 'Quarter',
            'trimester': 'Trimester',
            'module': 'Module',
            'block': 'Block',
            'yearlong': 'Year',
            'intensive': 'Session',
            'custom': 'Period'
        }
        return type_names.get(self.term_system, 'Term')
    
    def get_period_type_name(self):
        """Get the singular name for the period type"""
        return self._get_period_type_name()

    def get_period_type_name_plural(self):
        """Enhanced plural name getter"""
        singular = self.get_period_type_name()
        
        # Handle special cases
        irregular_plurals = {
            'Module': 'Modules',
            'Year': 'Years',
        }
        
        if singular in irregular_plurals:
            return irregular_plurals[singular]
        elif singular.endswith('y'):
            return singular[:-1] + 'ies'
        else:
            return singular + 's'
    
    # -------------------------------------------------------------------------
    # UTILITY METHODS
    # -------------------------------------------------------------------------
    
    def is_last_period(self, position):
        """Check if the period position is the last in the academic year"""
        return position == self.get_period_count()
    
    def validate_period_number(self, period_number):
        """Validate if a period number is valid for the current system"""
        return 1 <= period_number <= self.get_period_count()
    
    def get_all_period_names(self, include_year=False, academic_year=None):
        """Get all period names for the current system"""
        return [
            self.get_period_name(i, include_year, academic_year) 
            for i in range(1, self.get_period_count() + 1)
        ]
    
    @classmethod 
    def get_instance(cls):
        """Get school configuration instance"""
        return cls.objects.first()
    
    def save(self, *args, **kwargs):
        """Simplified save method without problematic singleton logic"""
        super().save(*args, **kwargs)
        logger.debug(f"SchoolConfiguration saved with UUID: {self.pk}")

    @classmethod 
    def get_cached_instance(cls):
        """
        Get school configuration instance with simple in-memory caching
        
        This method provides a cached version of the singleton configuration
        to avoid repeated database queries within the same request.
        """
        # Try to get from thread-local storage first (per-request cache)
        import threading
        if not hasattr(threading.current_thread(), '_school_config_cache'):
            threading.current_thread()._school_config_cache = None
        
        cached = threading.current_thread()._school_config_cache
        
        if cached is None:
            try:
                cached = cls.objects.first()
                threading.current_thread()._school_config_cache = cached
            except Exception:
                return None
        
        return cached

    @classmethod 
    def clear_cache(cls):
        """Clear the cached configuration instance"""
        import threading
        if hasattr(threading.current_thread(), '_school_config_cache'):
            threading.current_thread()._school_config_cache = None
    