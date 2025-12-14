# utils/admin.py

from django.contrib import admin
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = [
        'timestamp', 'action', 'content_type', 'object_repr', 
        'user_name', 'ip_address'
    ]
    list_filter = ['action', 'timestamp', 'content_type']
    search_fields = ['object_repr', 'user_name', 'user_email', 'object_id']
    readonly_fields = [
        'id', 'content_type', 'object_id', 'object_repr', 'action',
        'changes', 'user_id', 'user_email', 'user_name', 'timestamp',
        'ip_address', 'user_agent', 'change_reason', 'session_key',
        'request_path', 'changes_display'
    ]
    
    fieldsets = (
        ('What Changed', {
            'fields': ('content_type', 'object_id', 'object_repr', 'action', 'changes_display')
        }),
        ('Who Changed It', {
            'fields': ('user_id', 'user_name', 'user_email')
        }),
        ('When & Where', {
            'fields': ('timestamp', 'ip_address', 'request_path', 'session_key')
        }),
        ('Additional Info', {
            'fields': ('change_reason', 'user_agent'),
            'classes': ('collapse',)
        }),
    )
    
    def has_add_permission(self, request):
        # Audit logs should not be created manually
        return False
    
    def has_delete_permission(self, request, obj=None):
        # Consider making audit logs non-deletable
        return request.user.is_superuser
    
    def changes_display(self, obj):
        """Display changes in a readable format"""
        return obj.get_changes_display()
    changes_display.short_description = 'Changes'
