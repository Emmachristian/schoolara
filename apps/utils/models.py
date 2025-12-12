from django.db import models
import uuid

# Create your models here.
class BaseModel(models.Model):
    """
    Enhanced base model with comprehensive audit trail capabilities.
    
    Features:
    - Automatic user tracking (who created/updated)
    - Real IP address tracking (where operations came from)
    - Change reason tracking (why changes were made)
    - Comprehensive audit trail methods
    - Thread-local context integration
    """
    
    # Core identification
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Timestamp fields
    created_at = models.DateTimeField("Created At", auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField("Updated At", auto_now=True, db_index=True)
    
    # User tracking
    created_by_id = models.CharField("Created By ID", max_length=100, null=True, blank=True, db_index=True)
    updated_by_id = models.CharField("Updated By ID", max_length=100, null=True, blank=True, db_index=True)
    
    # Enhanced IP tracking - captures real client IP
    created_from_ip = models.GenericIPAddressField("Created From IP", null=True, blank=True)
    updated_from_ip = models.GenericIPAddressField("Updated From IP", null=True, blank=True)
    
    # Change reason tracking
    change_reason = models.CharField("Change Reason", max_length=255, blank=True, null=True)
    
    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=['created_at']),
            models.Index(fields=['updated_at']),
            models.Index(fields=['created_by_id']),
            models.Index(fields=['updated_by_id']),
        ]