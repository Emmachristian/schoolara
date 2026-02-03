# utils/models.py

"""
Base models for School Management System with comprehensive audit trail
and timezone-aware timestamp handling.

Key Features:
- Automatic school timezone handling for all timestamps
- Comprehensive audit trail tracking
- Multi-database routing support
- User and IP tracking
- Change reason tracking
- Financial audit logging with compliance features

CRITICAL TIMEZONE BEHAVIOR:
- All timestamps use the school's operational timezone (e.g., Africa/Kampala)
- NOT Django's default TIME_ZONE (UTC)
- This ensures consistency for schools operating across different time zones
- Parents/staff see timestamps in their school's local time
- Fee deadlines, attendance records, and reports use consistent school time

Example:
    If a payment is made at 11:30 PM East Africa Time (EAT):
    - Without school timezone: Stored as next day in UTC (wrong!)
    - With school timezone: Correctly stored as 11:30 PM in school time (correct!)

Updated: January 2025
- Removed auto_now/auto_now_add in favor of manual timezone setting
- All timestamps now use get_school_current_time() from core.utils
- Enhanced documentation and safety checks
"""

from django.db import models
from django.core.exceptions import ValidationError
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from schoolara.managers import get_current_db, SchoolManager
from datetime import date
from decimal import Decimal, InvalidOperation
import uuid
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# BASE MODEL - SCHOOL-SPECIFIC DATA
# =============================================================================

class BaseModel(models.Model):
    """
    Enhanced base model with comprehensive audit trail capabilities,
    automatic multi-database routing, and school timezone support.
    
    Features:
    - Automatic user tracking (who created/updated)
    - Real IP address tracking (where operations came from)
    - Change reason tracking (why changes were made)
    - School timezone-aware timestamps (when operations happened)
    - Automatic database routing for multi-tenant setup
    - Comprehensive audit trail methods
    - Thread-local context integration
    
    Timezone Behavior:
    - All timestamps (created_at, updated_at) use the school's operational timezone
    - This ensures consistency for schools operating across different time zones
    - Parents/staff see timestamps in their school's local time
    - Fee deadlines, attendance records, and reports use consistent school time
    
    Why blank=True and null=True on timestamp fields?
    - Django's auto_now/auto_now_add use server timezone (UTC)
    - We need manual control to use school timezone instead
    - Fields are optional for form validation
    - save() method ensures they're ALWAYS set before database write
    - So timestamps are never actually NULL in the database
    
    Example:
        If a fee invoice is created at 11:30 PM East Africa Time (EAT):
        - Server time: 08:30 PM UTC (3 hours behind)
        - Django's auto_now_add would store: 08:30 PM UTC (next day in date format!)
        - Our approach stores: 11:30 PM EAT (correct date and time!)
        
        This prevents:
        - Fee deadlines appearing on wrong day
        - Attendance marked for wrong date
        - Reports showing incorrect timestamps
        - Parents seeing confusing transaction times
    
    Usage:
        class Student(BaseModel):
            name = models.CharField(max_length=200)
            # Don't need to define created_at, updated_at - inherited!
        
        # In forms, don't include timestamp fields:
        class StudentForm(forms.ModelForm):
            class Meta:
                model = Student
                fields = ['name']  # created_at/updated_at set automatically
    """
    
    # =========================================================================
    # CORE IDENTIFICATION
    # =========================================================================
    
    id = models.UUIDField(
        primary_key=True, 
        default=uuid.uuid4, 
        editable=False,
        help_text="Unique identifier for this record"
    )
    
    # =========================================================================
    # TIMESTAMP FIELDS - AUTOMATICALLY MANAGED IN SAVE() METHOD
    # =========================================================================
    # ⭐ CRITICAL DESIGN DECISION:
    # - These fields are blank=True, null=True to allow form validation to pass
    # - They are ALWAYS set in save() method before database write
    # - So they will NEVER actually be NULL in the database
    # 
    # Why not use auto_now_add and auto_now?
    # - Those use Django's TIME_ZONE setting (typically UTC) automatically
    # - We need school timezone for consistency across time zones
    # - Manual setting in save() gives us full control over timezone
    # 
    # Flow:
    # 1. Form validation passes (fields are optional)
    # 2. save() method is called
    # 3. Timestamps are set in school timezone using get_school_current_time()
    # 4. Object is saved to database (timestamps are never NULL)
    
    created_at = models.DateTimeField(
        "Created At",
        blank=True,  # ⭐ Allows form validation without this field
        null=True,   # ⭐ Allows temporary NULL (set in save())
        db_index=True,
        help_text="When this record was created (in school's operational timezone)"
    )
    
    updated_at = models.DateTimeField(
        "Updated At",
        blank=True,  # ⭐ Allows form validation without this field
        null=True,   # ⭐ Allows temporary NULL (set in save())
        db_index=True,
        help_text="When this record was last updated (in school's operational timezone)"
    )
    
    # =========================================================================
    # USER TRACKING FIELDS
    # =========================================================================
    # CharField instead of ForeignKey to avoid cross-database constraints
    # in multi-tenant setup (users in 'default' db, data in school dbs)
    
    created_by_id = models.CharField(
        "Created By ID", 
        max_length=50, 
        null=True, 
        blank=True, 
        db_index=True,
        help_text="ID of user who created this record"
    )
    
    updated_by_id = models.CharField(
        "Updated By ID", 
        max_length=50, 
        null=True, 
        blank=True, 
        db_index=True,
        help_text="ID of user who last updated this record"
    )
    
    # =========================================================================
    # IP ADDRESS TRACKING
    # =========================================================================
    # Captures real client IP (handles proxies via X-Forwarded-For)
    
    created_from_ip = models.GenericIPAddressField(
        "Created From IP", 
        null=True, 
        blank=True,
        help_text="IP address from which this record was created"
    )
    
    updated_from_ip = models.GenericIPAddressField(
        "Updated From IP", 
        null=True, 
        blank=True,
        help_text="IP address from which this record was last updated"
    )
    
    # =========================================================================
    # CHANGE REASON TRACKING
    # =========================================================================
    
    change_reason = models.CharField(
        "Change Reason", 
        max_length=255, 
        blank=True, 
        null=True,
        help_text="Explanation for why this change was made"
    )
    
    # =========================================================================
    # MANAGER - AUTOMATIC DATABASE ROUTING
    # =========================================================================
    
    objects = SchoolManager()
    
    # =========================================================================
    # META CLASS
    # =========================================================================
    
    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=['created_at']),
            models.Index(fields=['updated_at']),
            models.Index(fields=['created_by_id']),
            models.Index(fields=['updated_by_id']),
        ]

    # =========================================================================
    # SAVE METHOD - CORE LOGIC
    # =========================================================================

    def save(self, *args, **kwargs):
        """
        Override save to:
        1. Set timestamps in school timezone (NOT UTC!)
        2. Populate audit trail fields (created_by, updated_by, IPs)
        3. Automatically route to correct database
        4. Track field changes
        5. Create audit log entry
        
        The key improvement: Uses school timezone for all timestamps
        instead of Django's default UTC behavior.
        
        Flow:
        1. Form validates (created_at/updated_at can be NULL)
        2. save() is called
        3. Timestamps are set in school timezone
        4. Audit fields are populated from request context
        5. Changes are tracked (for existing objects)
        6. Object is saved to database (timestamps never actually NULL)
        7. Audit log entry is created
        
        Example:
            >>> student = Student(name="John Doe")
            >>> student.save()
            >>> print(student.created_at)  # Shows time in school timezone
            2025-01-10 14:30:00+03:00  # East Africa Time (EAT)
        """
        from utils.context import get_request_context
        from core.utils import get_school_current_time  
        
        # Determine if this is a new object
        is_new = self._state.adding
        
        # =====================================================================
        # STEP 1: SET TIMESTAMPS IN SCHOOL TIMEZONE ⭐ CRITICAL
        # =====================================================================
        # Django's auto_now/auto_now_add uses server timezone (usually UTC)
        # We override this to use the school's operational timezone
        
        if is_new:
            # For new objects, set created_at in school timezone
            # Only set if not already provided (respects manual override)
            if not self.created_at:
                self.created_at = get_school_current_time()
                logger.debug(
                    f"Set created_at for new {self.__class__.__name__}: {self.created_at}"
                )
            
            # New objects also need updated_at
            if not self.updated_at:
                self.updated_at = get_school_current_time()
        else:
            # For updates, always refresh updated_at to current school time
            self.updated_at = get_school_current_time()
            logger.debug(
                f"Updated updated_at for {self.__class__.__name__}: {self.updated_at}"
            )
        
        # ⭐ SAFETY CHECK: Ensure timestamps are NEVER NULL before database write
        # This guarantees data integrity even if something went wrong above
        if not self.created_at:
            logger.warning(
                f"created_at was NULL for {self.__class__.__name__}, "
                f"setting to current time"
            )
            self.created_at = get_school_current_time()
        
        if not self.updated_at:
            logger.warning(
                f"updated_at was NULL for {self.__class__.__name__}, "
                f"setting to current time"
            )
            self.updated_at = get_school_current_time()
        
        # =====================================================================
        # STEP 2: POPULATE AUDIT FIELDS FROM REQUEST CONTEXT
        # =====================================================================
        context = get_request_context()
        
        if context:
            user = context.get('user')
            ip_address = context.get('ip_address')
            
            # Set created_by and created_from_ip for new objects
            if is_new:
                if user and not self.created_by_id:
                    self.created_by_id = str(user.id)
                    logger.debug(f"Set created_by_id: {self.created_by_id}")
                
                if ip_address and not self.created_from_ip:
                    self.created_from_ip = ip_address
                    logger.debug(f"Set created_from_ip: {self.created_from_ip}")
            
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
                    f"Audit fields will not be populated. "
                    f"This is normal for management commands, shell, or background tasks."
                )
        
        # =====================================================================
        # STEP 3: TRACK CHANGES FOR EXISTING OBJECTS
        # =====================================================================
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
                
                if changes:
                    logger.debug(f"Changes detected for {self.__class__.__name__}: {changes}")
                    
            except self.__class__.DoesNotExist:
                # Object doesn't exist yet in database, treat as new
                logger.debug(
                    f"Old instance not found for {self.__class__.__name__} {self.pk}. "
                    f"Treating as new record."
                )
            except Exception as e:
                # Don't fail save if change tracking fails
                logger.error(
                    f"Error tracking changes for {self.__class__.__name__}: {e}",
                    exc_info=True
                )
        
        # =====================================================================
        # STEP 4: AUTOMATIC DATABASE ROUTING
        # =====================================================================
        current_db = get_current_db()
        
        # Only set 'using' if not already specified and we have a database context
        if current_db and 'using' not in kwargs:
            kwargs['using'] = current_db
            logger.debug(f"Saving {self.__class__.__name__} to database: {current_db}")
        
        # =====================================================================
        # STEP 5: SAVE THE OBJECT TO DATABASE
        # =====================================================================
        result = super().save(*args, **kwargs)
        
        # =====================================================================
        # STEP 6: CREATE AUDIT LOG ENTRY (POST-SAVE)
        # =====================================================================
        # Only create audit log for school databases (not default)
        # ALSO skip if this IS an AuditLog to prevent infinite recursion
        if current_db and current_db != 'default' and self.__class__.__name__ != 'AuditLog':
            try:
                self._create_audit_log(
                    action='CREATE' if is_new else 'UPDATE',
                    changes=changes if not is_new else {}
                )
            except Exception as e:
                # Don't fail the save if audit logging fails
                logger.error(
                    f"Failed to create audit log for {self.__class__.__name__}: {e}",
                    exc_info=True
                )
        
        return result
    
    # =========================================================================
    # DELETE METHOD
    # =========================================================================
    
    def delete(self, *args, **kwargs):
        """
        Override delete to automatically route to correct database and log deletion.
        Deletion timestamp in audit log will use school timezone.
        
        Example:
            >>> student = Student.objects.get(name="John Doe")
            >>> student.delete()
            >>> # Audit log entry created with school timezone timestamp
        """
        current_db = get_current_db()
        
        if current_db and 'using' not in kwargs:
            kwargs['using'] = current_db
            logger.debug(f"Deleting {self.__class__.__name__} from database: {current_db}")
        
        # Create audit log before deletion (only for school databases)
        # ALSO skip if this IS an AuditLog to prevent infinite recursion
        if current_db and current_db != 'default' and self.__class__.__name__ != 'AuditLog':
            try:
                self._create_audit_log(action='DELETE', changes={})
            except Exception as e:
                # Don't fail the delete if audit logging fails
                logger.error(
                    f"Failed to create audit log for deletion of {self.__class__.__name__}: {e}",
                    exc_info=True
                )
        
        return super().delete(*args, **kwargs)
    
    # =========================================================================
    # REFRESH METHOD
    # =========================================================================
    
    def refresh_from_db(self, *args, **kwargs):
        """
        Override refresh to automatically route to correct database.
        Ensures object is reloaded from the same database it was saved to.
        
        Example:
            >>> student = Student.objects.first()
            >>> student.name = "Updated Name"
            >>> student.refresh_from_db()  # Reloads from correct database
        """
        current_db = get_current_db()
        
        if current_db and 'using' not in kwargs:
            kwargs['using'] = current_db
        
        return super().refresh_from_db(*args, **kwargs)
    
    # =========================================================================
    # AUDIT TRAIL HELPER METHODS
    # =========================================================================
    
    def get_created_by(self):
        """
        Get the user who created this record.
        
        Returns:
            User object or None
            
        Example:
            >>> fiscal_year = FiscalYear.objects.first()
            >>> creator = fiscal_year.get_created_by()
            >>> if creator:
            >>>     print(f"Created by: {creator.get_full_name()}")
        """
        if not self.created_by_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            # Always get users from default database
            return User.objects.using('default').get(id=self.created_by_id)
        except Exception as e:
            logger.debug(f"Error fetching created_by user for {self.__class__.__name__}: {e}")
            return None
    
    def get_updated_by(self):
        """
        Get the user who last updated this record.
        
        Returns:
            User object or None
            
        Example:
            >>> fiscal_year = FiscalYear.objects.first()
            >>> updater = fiscal_year.get_updated_by()
            >>> if updater:
            >>>     print(f"Last updated by: {updater.get_full_name()}")
        """
        if not self.updated_by_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            # Always get users from default database
            return User.objects.using('default').get(id=self.updated_by_id)
        except Exception as e:
            logger.debug(f"Error fetching updated_by user for {self.__class__.__name__}: {e}")
            return None
    
    def get_audit_trail(self):
        """
        Get comprehensive audit information for this record.
        All timestamps are in school timezone.
        
        Returns:
            dict: Audit trail information including timestamps, users, IPs
            
        Example:
            >>> fiscal_year = FiscalYear.objects.first()
            >>> audit = fiscal_year.get_audit_trail()
            >>> print(f"Created: {audit['created_at']}")
            >>> print(f"By: {audit['created_by_name']}")
            >>> print(f"From IP: {audit['created_from_ip']}")
        """
        return {
            'id': str(self.id),
            'created_at': self.created_at,  # Already in school timezone
            'created_by_id': self.created_by_id,
            'created_by_name': self.created_by_name,
            'created_from_ip': self.created_from_ip,
            'updated_at': self.updated_at,  # Already in school timezone
            'updated_by_id': self.updated_by_id,
            'updated_by_name': self.updated_by_name,
            'updated_from_ip': self.updated_from_ip,
            'last_change_reason': self.change_reason,
        }
    
    @property
    def created_by_name(self):
        """
        Get the name of the user who created this record.
        
        Returns:
            str: User's full name or "System"
            
        Example:
            >>> print(f"Created by: {fiscal_year.created_by_name}")
            Created by: John Doe
        """
        user = self.get_created_by()
        if user:
            return user.get_full_name() or user.username
        return "System"
    
    @property
    def updated_by_name(self):
        """
        Get the name of the user who last updated this record.
        
        Returns:
            str: User's full name or "System"
            
        Example:
            >>> print(f"Updated by: {fiscal_year.updated_by_name}")
            Updated by: Jane Smith
        """
        user = self.get_updated_by()
        if user:
            return user.get_full_name() or user.username
        return "System"
    
    def get_created_at_local(self):
        """
        Get created_at timestamp in school timezone (for display).
        
        Since we now store in school timezone, this is just an alias,
        but kept for backward compatibility and explicit intent.
        
        Returns:
            datetime: Created timestamp in school timezone
            
        Example:
            >>> local_time = fiscal_year.get_created_at_local()
            >>> print(local_time.strftime('%Y-%m-%d %H:%M:%S %Z'))
            2024-01-15 14:30:00 EAT
        """
        from core.utils import localize_datetime
        return localize_datetime(self.created_at)
    
    def get_updated_at_local(self):
        """
        Get updated_at timestamp in school timezone (for display).
        
        Since we now store in school timezone, this is just an alias,
        but kept for backward compatibility and explicit intent.
        
        Returns:
            datetime: Updated timestamp in school timezone
            
        Example:
            >>> local_time = fiscal_year.get_updated_at_local()
            >>> print(local_time.strftime('%Y-%m-%d %H:%M:%S %Z'))
            2024-01-15 14:30:00 EAT
        """
        from core.utils import localize_datetime
        return localize_datetime(self.updated_at)
    
    def _create_audit_log(self, action, changes):
        """
        Create an audit log entry for this change.
        Audit log timestamp will automatically use school timezone.
        
        This is an internal method called automatically by save() and delete().
        
        Args:
            action: 'CREATE', 'UPDATE', or 'DELETE'
            changes: Dict of field changes
            
        Note:
            This method is called automatically. You don't need to call it directly.
            Audit logs are created automatically during save() and delete() operations.
        """
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
            # Note: AuditLog.save() will set timestamp in school timezone
            audit_log = AuditLog(
                content_type=f"{self._meta.app_label}.{self._meta.model_name}",
                object_id=str(self.pk),
                object_repr=str(self)[:200],  # Truncate to fit in field
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
            
            logger.debug(
                f"Created audit log for {action} on "
                f"{self._meta.label} {self.pk} in database {current_db or 'default'}"
            )
            
        except Exception as e:
            # Don't fail the save/delete if audit logging fails
            # This is important for system stability
            logger.error(
                f"Failed to create audit log for {action} on "
                f"{self._meta.label} {self.pk}: {e}",
                exc_info=True
            )
    
    def get_history(self, limit=10):
        """
        Get audit history for this object.
        All timestamps in history will be in school timezone.
        
        Args:
            limit: Maximum number of history entries to return (default: 10)
            
        Returns:
            QuerySet of AuditLog entries, ordered by timestamp (newest first)
            
        Example:
            >>> fiscal_year = FiscalYear.objects.first()
            >>> history = fiscal_year.get_history(limit=5)
            >>> for entry in history:
            >>>     print(f"{entry.action} at {entry.timestamp} by {entry.user_name}")
            UPDATE at 2024-01-15 14:30:00+03:00 by John Doe
            CREATE at 2024-01-10 09:00:00+03:00 by Jane Smith
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
            logger.error(
                f"Error fetching history for {self._meta.label} {self.pk}: {e}",
                exc_info=True
            )
            return []
    
    def set_change_reason(self, reason):
        """
        Set the reason for the next change to this object.
        This will be recorded in the audit log.
        
        Args:
            reason: String explaining why the change was made
            
        Example:
            >>> fiscal_year = FiscalYear.objects.get(name='2024')
            >>> fiscal_year.is_closed = True
            >>> fiscal_year.set_change_reason("End of academic year - all periods closed")
            >>> fiscal_year.save()
            
        Note:
            The change reason is only used for the NEXT save operation.
            After saving, it will be reset to None.
        """
        self.change_reason = reason
    
    def get_time_since_created(self):
        """
        Get human-readable time since creation.
        
        Returns:
            str: Human-readable time difference (e.g., "5 days ago")
            
        Example:
            >>> print(fiscal_year.get_time_since_created())
            5 days ago
        """
        from django.utils.timesince import timesince
        from core.utils import get_school_current_time
        
        if self.created_at:
            now = get_school_current_time()
            return timesince(self.created_at, now)
        return "Unknown"
    
    def get_time_since_updated(self):
        """
        Get human-readable time since last update.
        
        Returns:
            str: Human-readable time difference (e.g., "2 hours ago")
            
        Example:
            >>> print(fiscal_year.get_time_since_updated())
            2 hours ago
        """
        from django.utils.timesince import timesince
        from core.utils import get_school_current_time
        
        if self.updated_at:
            now = get_school_current_time()
            return timesince(self.updated_at, now)
        return "Unknown"


# =============================================================================
# DEFAULT DATABASE MODEL - SYSTEM-WIDE DATA
# =============================================================================

class DefaultDatabaseModel(models.Model):
    """
    Base model for entities that ALWAYS use the default database.
    
    Use this for:
    - User accounts (stored centrally)
    - School registry (list of all schools)
    - System-wide configuration
    - Any cross-tenant data
    
    This model includes basic audit fields but forces all operations
    to the default database regardless of thread-local context.
    
    Timezone Note:
    - Timestamps for default database models use Django's TIME_ZONE setting
    - Typically UTC for system-wide data
    - This is intentional - system data uses consistent global timezone
    - School-specific data (BaseModel) uses school timezone
    
    Example:
        class School(DefaultDatabaseModel):
            name = models.CharField(max_length=200)
            database_alias = models.CharField(max_length=100)
            # This school registry data always in default DB with UTC timestamps
    """
    
    # =========================================================================
    # CORE IDENTIFICATION
    # =========================================================================
    
    id = models.UUIDField(
        primary_key=True, 
        default=uuid.uuid4, 
        editable=False,
        help_text="Unique identifier for this record"
    )
    
    # =========================================================================
    # TIMESTAMP FIELDS - USE DJANGO'S DEFAULT TIMEZONE (UTC)
    # =========================================================================
    
    created_at = models.DateTimeField(
        "Created At", 
        auto_now_add=True, 
        db_index=True,
        help_text="When this record was created (UTC for system-wide data)"
    )
    
    updated_at = models.DateTimeField(
        "Updated At", 
        auto_now=True, 
        db_index=True,
        help_text="When this record was last updated (UTC for system-wide data)"
    )
    
    # =========================================================================
    # META CLASS
    # =========================================================================
    
    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=['created_at']),
            models.Index(fields=['updated_at']),
        ]
    
    # =========================================================================
    # DATABASE ROUTING METHODS
    # =========================================================================
    
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
    - When it happened (timestamp in school timezone) ⭐
    - Where it came from (IP address)
    - Why it was changed (reason)
    
    This model is stored in the SAME database as the model being tracked,
    so each school database has its own audit trail.
    
    Timezone Behavior:
    - Timestamps use school timezone (NOT UTC)
    - Ensures audit logs match school's operational context
    - Reports and analytics use consistent school time
    - Compliance audits show transactions in school's local time
    
    Example:
        >>> # Audit log automatically created when you save a model
        >>> student = Student(name="John Doe")
        >>> student.save()
        >>> 
        >>> # View audit trail
        >>> history = student.get_history()
        >>> for entry in history:
        >>>     print(f"{entry.action} at {entry.timestamp}")
        CREATE at 2025-01-10 14:30:00+03:00
    """
    
    # =========================================================================
    # ACTION CHOICES
    # =========================================================================
    
    ACTION_CHOICES = (
        ('CREATE', 'Created'),
        ('UPDATE', 'Updated'),
        ('DELETE', 'Deleted'),
    )
    
    # =========================================================================
    # CORE IDENTIFICATION
    # =========================================================================
    
    id = models.UUIDField(
        primary_key=True, 
        default=uuid.uuid4, 
        editable=False
    )
    
    # =========================================================================
    # WHAT WAS CHANGED
    # =========================================================================
    
    content_type = models.CharField(
        "Model Type", 
        max_length=100, 
        db_index=True,
        help_text="Type of model that was changed (e.g., 'students.student')"
    )
    
    object_id = models.CharField(
        "Object ID", 
        max_length=100, 
        db_index=True,
        help_text="ID of the object that was changed"
    )
    
    object_repr = models.CharField(
        "Object Representation", 
        max_length=200,
        help_text="String representation of the object"
    )
    
    action = models.CharField(
        "Action", 
        max_length=10, 
        choices=ACTION_CHOICES, 
        db_index=True,
        help_text="Type of action performed"
    )
    
    # =========================================================================
    # FIELD-LEVEL CHANGES
    # =========================================================================
    
    changes = models.JSONField(
        "Changes",
        help_text="Dictionary of field changes: {'field_name': {'old': 'value', 'new': 'value'}}",
        default=dict,
        blank=True
    )
    
    # =========================================================================
    # WHO MADE THE CHANGE
    # =========================================================================
    # CharField to avoid cross-database FK
    
    user_id = models.CharField(
        "User ID", 
        max_length=50, 
        db_index=True, 
        null=True, 
        blank=True,
        help_text="ID of user who performed this action"
    )
    
    user_email = models.EmailField(
        "User Email", 
        max_length=255, 
        blank=True,
        help_text="Email of user who performed this action"
    )
    
    user_name = models.CharField(
        "User Name", 
        max_length=255, 
        blank=True,
        help_text="Name of user who performed this action"
    )
    
    # =========================================================================
    # WHEN IT HAPPENED - SCHOOL TIMEZONE ⭐
    # =========================================================================
    
    timestamp = models.DateTimeField(
        "Timestamp", 
        db_index=True,
        help_text="When this action occurred (in school's operational timezone)"
    )
    
    # =========================================================================
    # WHERE IT CAME FROM
    # =========================================================================
    
    ip_address = models.GenericIPAddressField(
        "IP Address", 
        null=True, 
        blank=True,
        help_text="IP address from which this action was performed"
    )
    
    user_agent = models.TextField(
        "User Agent", 
        blank=True,
        help_text="Browser/client information"
    )
    
    # =========================================================================
    # WHY IT CHANGED
    # =========================================================================
    
    change_reason = models.CharField(
        "Change Reason", 
        max_length=255, 
        blank=True,
        help_text="Explanation for why this change was made"
    )
    
    # =========================================================================
    # ADDITIONAL CONTEXT
    # =========================================================================
    
    session_key = models.CharField(
        "Session Key", 
        max_length=100, 
        blank=True,
        help_text="Session key for tracking user sessions"
    )
    
    request_path = models.CharField(
        "Request Path", 
        max_length=255, 
        blank=True,
        help_text="URL path where action was performed"
    )
    
    # =========================================================================
    # MANAGER - AUTOMATIC DATABASE ROUTING
    # =========================================================================
    
    objects = SchoolManager()
    
    # =========================================================================
    # META CLASS
    # =========================================================================
    
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
    
    # =========================================================================
    # STRING REPRESENTATION
    # =========================================================================
    
    def __str__(self):
        return f"{self.action} {self.content_type} {self.object_id} at {self.timestamp}"
    
    # =========================================================================
    # SAVE METHOD
    # =========================================================================
    
    def save(self, *args, **kwargs):
        """
        Override save to:
        1. Set timestamp in school timezone ⭐
        2. Route to current database
        
        Example:
            >>> # Audit log automatically created with school timezone
            >>> audit = AuditLog(action='CREATE', ...)
            >>> audit.save()
            >>> print(audit.timestamp)  # School timezone
            2025-01-10 14:30:00+03:00
        """
        from core.utils import get_school_current_time  # ⭐ USE SCHOOL TIMEZONE
        
        # Set timestamp in school timezone if not provided
        if not self.timestamp:
            self.timestamp = get_school_current_time()
        
        # Route to current database
        current_db = get_current_db()
        if current_db and 'using' not in kwargs:
            kwargs['using'] = current_db
        
        return super().save(*args, **kwargs)
    
    # =========================================================================
    # DELETE METHOD
    # =========================================================================
    
    def delete(self, *args, **kwargs):
        """Route to current database"""
        current_db = get_current_db()
        if current_db and 'using' not in kwargs:
            kwargs['using'] = current_db
        return super().delete(*args, **kwargs)
    
    # =========================================================================
    # AUDIT LOG HELPER METHODS
    # =========================================================================
    
    def get_user(self):
        """
        Get the user who made this change.
        
        Returns:
            User object or None
        """
        if not self.user_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            return User.objects.using('default').get(id=self.user_id)
        except Exception as e:
            logger.debug(f"Error fetching audit log user: {e}")
            return None
    
    def get_changes_display(self):
        """
        Get a human-readable display of changes.
        
        Returns:
            str: Formatted string showing field changes
            
        Example:
            >>> print(audit.get_changes_display())
            name: 'John' → 'John Doe'
            email: 'old@email.com' → 'new@email.com'
        """
        if not self.changes:
            return "No field changes recorded"
        
        lines = []
        for field, change in self.changes.items():
            old_val = change.get('old', 'N/A')
            new_val = change.get('new', 'N/A')
            lines.append(f"{field}: '{old_val}' → '{new_val}'")
        
        return "\n".join(lines)
    
    def get_summary(self):
        """
        Get a brief summary of this audit entry.
        
        Returns:
            str: One-line summary of the audit entry
            
        Example:
            >>> print(audit.get_summary())
            John Doe created students.student
        """
        user_display = self.user_name or self.user_email or self.user_id or "Unknown User"
        return f"{user_display} {self.get_action_display().lower()} {self.content_type}"
    
    def get_timestamp_local(self):
        """
        Get timestamp in school timezone (for display).
        
        Since we now store in school timezone, this is just an alias,
        but kept for clarity and backward compatibility.
        
        Returns:
            datetime: Timestamp in school timezone
        """
        from core.utils import localize_datetime
        return localize_datetime(self.timestamp)
    
    # =========================================================================
    # CLASS METHODS - QUERYING AUDIT LOGS
    # =========================================================================
    
    @classmethod
    def get_recent_activity(cls, limit=50):
        """
        Get recent audit activity across all models.
        
        Args:
            limit: Maximum number of entries to return
            
        Returns:
            QuerySet: Recent audit log entries
        """
        return cls.objects.all().order_by('-timestamp')[:limit]
    
    @classmethod
    def get_user_activity(cls, user_id, limit=50):
        """
        Get recent activity for a specific user.
        
        Args:
            user_id: User ID
            limit: Maximum number of entries to return
            
        Returns:
            QuerySet: User's audit log entries
        """
        return cls.objects.filter(user_id=str(user_id)).order_by('-timestamp')[:limit]
    
    @classmethod
    def get_model_history(cls, model_label, limit=50):
        """
        Get history for a specific model type.
        
        Args:
            model_label: Model label (e.g., 'students.student')
            limit: Maximum number of entries to return
            
        Returns:
            QuerySet: Audit log entries for the model
        """
        return cls.objects.filter(content_type=model_label).order_by('-timestamp')[:limit]
    
    @classmethod
    def get_object_history(cls, obj):
        """
        Get complete history for a specific object.
        
        Args:
            obj: Model instance
            
        Returns:
            QuerySet: All audit log entries for the object
        """
        content_type = f"{obj._meta.app_label}.{obj._meta.model_name}"
        return cls.objects.filter(
            content_type=content_type,
            object_id=str(obj.pk)
        ).order_by('-timestamp')
    
    @classmethod
    def get_activity_by_date_range(cls, start_date, end_date):
        """
        Get activity within a date range (uses school timezone).
        
        Args:
            start_date: Start date (will be converted to school timezone)
            end_date: End date (will be converted to school timezone)
            
        Returns:
            QuerySet: Audit logs within date range
            
        Example:
            >>> from datetime import date
            >>> start = date(2025, 1, 1)
            >>> end = date(2025, 1, 31)
            >>> january_activity = AuditLog.get_activity_by_date_range(start, end)
        """
        from core.utils import get_school_timezone
        from datetime import datetime
        from django.utils import timezone as django_tz
        
        # Convert dates to school timezone datetimes
        tz = get_school_timezone()
        start_dt = django_tz.make_aware(datetime.combine(start_date, datetime.min.time()), tz)
        end_dt = django_tz.make_aware(datetime.combine(end_date, datetime.max.time()), tz)
        
        return cls.objects.filter(
            timestamp__gte=start_dt,
            timestamp__lte=end_dt
        ).order_by('-timestamp')


# =============================================================================
# FINANCIAL AUDIT LOG
# =============================================================================

class FinancialAuditLog(models.Model):
    """
    Specialized audit log for financial transactions and sensitive operations.
    Provides enhanced tracking for compliance and security purposes.
    
    Timezone Behavior:
    - All timestamps use school timezone ⭐
    - Financial reports show transactions in school's operational time
    - Compliance audits use consistent school time
    - Parent portals show transaction times in school timezone
    - Critical for accurate financial reporting and compliance
    
    Features:
    - Enhanced tracking for financial operations
    - Risk level classification
    - Compliance flagging
    - Student context tracking
    - Academic session linking
    - Bulk operation tracking
    
    Example:
        >>> FinancialAuditLog.log_financial_action(
        >>>     action='PAYMENT_RECEIVE',
        >>>     user=request.user,
        >>>     request=request,
        >>>     target_object=payment,
        >>>     amount=payment.amount,
        >>>     student=payment.student,
        >>>     risk_level='LOW'
        >>> )
    """
    
    # =========================================================================
    # FINANCIAL-SPECIFIC ACTION TYPES
    # =========================================================================
    
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
    
    # =========================================================================
    # CORE AUDIT FIELDS
    # =========================================================================
    
    id = models.AutoField(primary_key=True)
    
    # When it happened - Stored in school timezone ⭐
    timestamp = models.DateTimeField(
        db_index=True,
        help_text="When this financial action occurred (in school's operational timezone)"
    )
    
    action = models.CharField(
        max_length=30, 
        choices=FINANCIAL_ACTIONS, 
        db_index=True,
        help_text="Type of financial action performed"
    )
    
    # =========================================================================
    # USER INFORMATION
    # =========================================================================
    # CharField to avoid cross-database FK
    
    user_id = models.CharField(
        max_length=100, 
        null=True, 
        blank=True, 
        db_index=True,
        help_text="ID of user who performed this action"
    )
    
    user_name = models.CharField(
        max_length=200, 
        null=True, 
        blank=True,
        help_text="Name of user who performed this action"
    )
    
    user_role = models.CharField(
        max_length=100, 
        null=True, 
        blank=True,
        help_text="Role of user who performed this action"
    )
    
    # =========================================================================
    # SESSION AND REQUEST CONTEXT
    # =========================================================================
    
    session_key = models.CharField(
        max_length=40, 
        null=True, 
        blank=True,
        help_text="Session key for tracking user sessions"
    )
    
    ip_address = models.GenericIPAddressField(
        null=True, 
        blank=True, 
        db_index=True,
        help_text="IP address from which action was performed"
    )
    
    user_agent = models.TextField(
        null=True, 
        blank=True,
        help_text="Browser/client information"
    )
    
    # =========================================================================
    # TARGET OBJECT (WHAT WAS CHANGED)
    # =========================================================================
    
    content_type = models.ForeignKey(
        ContentType, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        help_text="Type of object that was changed"
    )
    
    object_id = models.CharField(
        max_length=100, 
        null=True, 
        blank=True,
        help_text="ID of object that was changed"
    )
    
    content_object = GenericForeignKey('content_type', 'object_id')
    
    object_description = models.CharField(
        max_length=500, 
        null=True, 
        blank=True,
        help_text="Description of object that was changed"
    )
    
    # =========================================================================
    # FINANCIAL-SPECIFIC FIELDS
    # =========================================================================
    
    amount_involved = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Monetary amount involved in the action"
    )
    
    currency = models.CharField(
        max_length=3, 
        null=True, 
        blank=True, 
        default='UGX',
        help_text="Currency code (e.g., UGX, USD, EUR)"
    )
    
    # =========================================================================
    # STUDENT CONTEXT
    # =========================================================================
    
    student_id = models.CharField(
        max_length=100, 
        null=True, 
        blank=True, 
        db_index=True,
        help_text="ID of student related to this action"
    )
    
    student_name = models.CharField(
        max_length=200, 
        null=True, 
        blank=True,
        help_text="Name of student related to this action"
    )
    
    student_admission_number = models.CharField(
        max_length=50, 
        null=True, 
        blank=True,
        help_text="Admission number of student"
    )
    
    # =========================================================================
    # ACADEMIC CONTEXT
    # =========================================================================
    
    academic_session_id = models.CharField(
        max_length=100, 
        null=True, 
        blank=True,
        help_text="ID of related academic session"
    )
    
    academic_session_name = models.CharField(
        max_length=100, 
        null=True, 
        blank=True,
        help_text="Name of related academic session"
    )
    
    # =========================================================================
    # CHANGE TRACKING
    # =========================================================================
    
    old_values = models.JSONField(
        null=True, 
        blank=True, 
        help_text="Values before change"
    )
    
    new_values = models.JSONField(
        null=True, 
        blank=True, 
        help_text="Values after change"
    )
    
    changes_summary = models.TextField(
        null=True, 
        blank=True, 
        help_text="Human-readable summary of changes"
    )
    
    # =========================================================================
    # RISK AND COMPLIANCE
    # =========================================================================
    
    risk_level = models.CharField(
        max_length=10,
        choices=[
            ('LOW', 'Low Risk'),
            ('MEDIUM', 'Medium Risk'),
            ('HIGH', 'High Risk'),
            ('CRITICAL', 'Critical Risk'),
        ],
        default='LOW',
        db_index=True,
        help_text="Risk level of this action"
    )
    
    compliance_flags = models.JSONField(
        default=list, 
        blank=True,
        help_text="Compliance-related flags or concerns"
    )
    
    # =========================================================================
    # ADDITIONAL CONTEXT
    # =========================================================================
    
    additional_data = models.JSONField(
        default=dict, 
        blank=True,
        help_text="Additional context-specific data"
    )
    
    notes = models.TextField(
        null=True, 
        blank=True,
        help_text="Additional notes about this action"
    )
    
    # =========================================================================
    # PROCESSING INFORMATION
    # =========================================================================
    
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
    
    # =========================================================================
    # MANAGER - AUTOMATIC DATABASE ROUTING
    # =========================================================================
    
    objects = SchoolManager()
    
    # =========================================================================
    # META CLASS
    # =========================================================================
    
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
    
    # =========================================================================
    # STRING REPRESENTATION
    # =========================================================================
    
    def __str__(self):
        return f"{self.get_action_display()} at {self.timestamp}"
    
    # =========================================================================
    # SAVE METHOD
    # =========================================================================
    
    def save(self, *args, **kwargs):
        """
        Override save to:
        1. Set timestamp in school timezone ⭐
        2. Route to current database
        """
        from core.utils import get_school_current_time  # ⭐ USE SCHOOL TIMEZONE
        
        # Set timestamp in school timezone if not provided
        if not self.timestamp:
            self.timestamp = get_school_current_time()
        
        # Route to current database
        current_db = get_current_db()
        if current_db and 'using' not in kwargs:
            kwargs['using'] = current_db
        
        return super().save(*args, **kwargs)
    
    # =========================================================================
    # CLASS METHOD - CREATE FINANCIAL AUDIT LOG
    # =========================================================================
    
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
        Class method to log financial actions with school timezone support.

        This is the primary way to create financial audit log entries.
        Handles all the complexity of extracting context and setting timezone.
        
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
            risk_level: Risk level of the action ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')
            additional_data: Additional contextual data
            notes: Optional notes
            currency: Currency code or object
            **kwargs: Additional parameters (is_automated, batch_id)
            
        Returns:
            FinancialAuditLog: Created audit log entry or None if failed
        
        Example:
            >>> FinancialAuditLog.log_financial_action(
            >>>     action='PAYMENT_RECEIVE',
            >>>     user=request.user,
            >>>     request=request,
            >>>     target_object=payment,
            >>>     amount=payment.amount,
            >>>     student=payment.student,
            >>>     academic_session=payment.academic_session,
            >>>     risk_level='LOW',
            >>>     notes='Payment received via mobile money'
            >>> )
        """
        from django.contrib.contenttypes.models import ContentType
        from core.utils import get_school_current_time  # ⭐ USE SCHOOL TIMEZONE

        try:
            # Prepare base log payload with school timezone ⭐
            log_data = {
                'action': action,
                'risk_level': risk_level,
                'timestamp': get_school_current_time(),  # ⭐ SCHOOL TIMEZONE
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
                # Get from FinancialSettings
                try:
                    from core.models import FinancialSettings
                    settings = FinancialSettings.get_instance()
                    if settings and settings.school_currency:
                        log_data['currency'] = settings.school_currency[:3].upper()
                    else:
                        log_data['currency'] = 'UGX'
                except Exception:
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
                            from academics.models import AcademicSession
                            uuid_lib.UUID(session_str)
                            session_obj = AcademicSession.objects.filter(id=session_str).first()
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
    
    # =========================================================================
    # INSTANCE METHODS
    # =========================================================================
    
    def get_user(self):
        """
        Get the user who performed this action.
        
        Returns:
            User object or None
        """
        if not self.user_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            return User.objects.using('default').get(id=self.user_id)
        except Exception as e:
            logger.debug(f"Error fetching financial audit user: {e}")
            return None
    
    def get_student(self):
        """
        Get the student associated with this action.
        
        Returns:
            Student object or None
        """
        if not self.student_id:
            return None
        try:
            from students.models import Student
            return Student.objects.get(id=self.student_id)
        except Exception as e:
            logger.debug(f"Error fetching student: {e}")
            return None
    
    def get_summary(self):
        """
        Get a brief summary of this financial audit entry.
        
        Returns:
            str: One-line summary
            
        Example:
            >>> print(audit.get_summary())
            John Doe received payment for Jane Smith (UGX 500,000.00)
        """
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
        """
        Get CSS class for risk level badge.
        
        Returns:
            str: Bootstrap badge class
            
        Example:
            >>> print(f'<span class="{audit.get_risk_badge_class()}">{audit.risk_level}</span>')
        """
        risk_classes = {
            'LOW': 'badge-success',
            'MEDIUM': 'badge-warning',
            'HIGH': 'badge-danger',
            'CRITICAL': 'badge-dark',
        }
        return risk_classes.get(self.risk_level, 'badge-secondary')
    
    def get_timestamp_local(self):
        """
        Get timestamp in school timezone (for display).
        
        Since we now store in school timezone, this is just an alias,
        but kept for clarity and backward compatibility.
        
        Returns:
            datetime: Timestamp in school timezone
        """
        from core.utils import localize_datetime
        return localize_datetime(self.timestamp)
    
    # =========================================================================
    # QUERY METHODS
    # =========================================================================
    
    @classmethod
    def get_recent_activity(cls, limit=50):
        """
        Get recent financial activity.
        
        Args:
            limit: Maximum number of entries to return
            
        Returns:
            QuerySet: Recent financial audit log entries
        """
        return cls.objects.all().order_by('-timestamp')[:limit]
    
    @classmethod
    def get_high_risk_actions(cls, days=30):
        """
        Get high-risk actions from recent days (uses school timezone).
        
        Args:
            days: Number of days to look back
            
        Returns:
            QuerySet: High-risk financial audit log entries
        """
        from core.utils import get_school_current_time  # ⭐ USE SCHOOL TIMEZONE
        from datetime import timedelta
        
        cutoff_date = get_school_current_time() - timedelta(days=days)
        return cls.objects.filter(
            timestamp__gte=cutoff_date,
            risk_level__in=['HIGH', 'CRITICAL']
        ).order_by('-timestamp')
    
    @classmethod
    def get_student_financial_history(cls, student_id, limit=50):
        """
        Get financial history for a specific student.
        
        Args:
            student_id: Student ID
            limit: Maximum number of entries to return
            
        Returns:
            QuerySet: Student's financial audit log entries
        """
        return cls.objects.filter(
            student_id=str(student_id)
        ).order_by('-timestamp')[:limit]
    
    @classmethod
    def get_user_financial_actions(cls, user_id, limit=50):
        """
        Get financial actions performed by a specific user.
        
        Args:
            user_id: User ID
            limit: Maximum number of entries to return
            
        Returns:
            QuerySet: User's financial audit log entries
        """
        return cls.objects.filter(
            user_id=str(user_id)
        ).order_by('-timestamp')[:limit]
    
    @classmethod
    def get_actions_by_type(cls, action_type, limit=50):
        """
        Get actions of a specific type.
        
        Args:
            action_type: Action type (e.g., 'PAYMENT_RECEIVE')
            limit: Maximum number of entries to return
            
        Returns:
            QuerySet: Financial audit log entries of specified type
        """
        return cls.objects.filter(
            action=action_type
        ).order_by('-timestamp')[:limit]
    
    @classmethod
    def get_session_financial_activity(cls, session_id):
        """
        Get all financial activity for an academic session.
        
        Args:
            session_id: Academic session ID
            
        Returns:
            QuerySet: Financial audit log entries for the session
        """
        return cls.objects.filter(
            academic_session_id=str(session_id)
        ).order_by('-timestamp')
    
    @classmethod
    def get_amount_summary(cls, action_type=None, days=30):
        """
        Get summary of amounts involved in financial actions (uses school timezone).
        
        Args:
            action_type: Optional action type to filter by
            days: Number of days to look back
            
        Returns:
            dict: Summary with total_amount, count, average_amount
            
        Example:
            >>> summary = FinancialAuditLog.get_amount_summary('PAYMENT_RECEIVE', days=7)
            >>> print(f"Total: {summary['total_amount']}, Count: {summary['count']}")
        """
        from core.utils import get_school_current_time  # ⭐ USE SCHOOL TIMEZONE
        from datetime import timedelta
        from django.db.models import Sum, Count, Avg
        
        cutoff_date = get_school_current_time() - timedelta(days=days)
        queryset = cls.objects.filter(timestamp__gte=cutoff_date)
        
        if action_type:
            queryset = queryset.filter(action=action_type)
        
        return queryset.aggregate(
            total_amount=Sum('amount_involved'),
            count=Count('id'),
            average_amount=Avg('amount_involved')
        )
    
    @classmethod
    def get_activity_by_date_range(cls, start_date, end_date):
        """
        Get financial activity within a date range (uses school timezone).
        
        Args:
            start_date: Start date (will be converted to school timezone)
            end_date: End date (will be converted to school timezone)
            
        Returns:
            QuerySet: Financial audit logs within date range
            
        Example:
            >>> from datetime import date
            >>> start = date(2025, 1, 1)
            >>> end = date(2025, 1, 31)
            >>> january_activity = FinancialAuditLog.get_activity_by_date_range(start, end)
        """
        from core.utils import get_school_timezone
        from datetime import datetime
        from django.utils import timezone as django_tz
        
        # Convert dates to school timezone datetimes
        tz = get_school_timezone()
        start_dt = django_tz.make_aware(datetime.combine(start_date, datetime.min.time()), tz)
        end_dt = django_tz.make_aware(datetime.combine(end_date, datetime.max.time()), tz)
        
        return cls.objects.filter(
            timestamp__gte=start_dt,
            timestamp__lte=end_dt
        ).order_by('-timestamp')