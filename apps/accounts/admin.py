# accounts/admin.py

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.utils.html import format_html
from .models import School, UserProfile, UserManagementSettings
from image_cropping import ImageCroppingMixin


# -----------------------------------------
# SCHOOL ADMIN
# -----------------------------------------
@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = [
        'full_name', 
        'domain',
        'database_alias',
        'school_type', 
        'country', 
        'boarding_type',
        'gender_type',
        'is_active_subscription',
        'subscription_plan',
        'created_at'
    ]
    
    list_filter = [
        'school_type',
        'country',
        'boarding_type',
        'gender_type',
        'is_active_subscription',
        'subscription_plan',
        'created_at'
    ]
    
    search_fields = [
        'full_name',
        'domain',
        'database_alias',
        'short_name',
        'abbreviation',
        'contact_phone',
        'address'
    ]
    
    readonly_fields = ['created_at', 'updated_at', 'display_logo', 'display_favicon']
    
    fieldsets = (
        ('Basic Information', {
            'fields': (
                'full_name',
                'short_name',
                'abbreviation',
                'receipt_name',
                'domain',
                'database_alias',
                'school_type',
                'established_date',
                'school_license'
            )
        }),
        ('Location & Contact', {
            'fields': (
                'country',
                'timezone',
                'address',
                'contact_phone',
                'alternative_contact'
            )
        }),
        ('School Classifications', {
            'fields': (
                'boarding_type',
                'gender_type',
                'student_capacity',
                'operating_hours'
            )
        }),
        ('Digital Presence', {
            'fields': (
                'website',
                'facebook_page',
                'twitter_handle',
                'instagram_handle',
                'linkedin_page'
            ),
            'classes': ('collapse',)
        }),
        ('Branding', {
            'fields': (
                'school_logo',
                'display_logo',
                'favicon',
                'display_favicon',
                'brand_colors'
            ),
            'classes': ('collapse',)
        }),
        ('Subscription', {
            'fields': (
                'subscription_plan',
                'subscription_start',
                'subscription_end',
                'is_active_subscription'
            )
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def display_logo(self, obj):
        """Display school logo preview"""
        if obj.school_logo:
            return format_html(
                '<img src="{}" width="100" height="100" style="object-fit: contain; border: 1px solid #ddd; border-radius: 4px; padding: 5px;" />',
                obj.school_logo.url
            )
        return format_html('<span style="color: #999;">No logo</span>')
    display_logo.short_description = "Logo Preview"
    
    def display_favicon(self, obj):
        """Display favicon preview"""
        if obj.favicon:
            return format_html(
                '<img src="{}" width="32" height="32" style="object-fit: contain; border: 1px solid #ddd; border-radius: 4px; padding: 2px;" />',
                obj.favicon.url
            )
        return format_html('<span style="color: #999;">No favicon</span>')
    display_favicon.short_description = "Favicon Preview"


# -----------------------------------------
# USER PROFILE INLINE
# -----------------------------------------
class UserProfileInline(ImageCroppingMixin, admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile'
    fk_name = 'user'
    
    fieldsets = (
        ('Profile Information', {
            'fields': (
                'school',
                'name_of_person_in_charge',
                'role',
                'photo',
                'cropping'
            )
        }),
        ('Theme Settings', {
            'fields': (
                'theme_color',
                'page_tabs_style',
                'fixed_header',
                'fixed_sidebar',
                'fixed_footer',
                'header_class',
                'sidebar_class'
            ),
            'classes': ('collapse',)
        })
    )
    
    # Optimize database queries
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.select_related('school')


# -----------------------------------------
# EXTENDED USER ADMIN
# -----------------------------------------
class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline,)
    
    list_display = [
        'username',
        'email',
        'first_name',
        'last_name',
        'get_school',
        'get_role',
        'is_staff',
        'is_superuser',
        'is_active',
        'date_joined'
    ]
    
    list_filter = [
        'is_staff',
        'is_superuser',
        'is_active',
        'date_joined',
        'userprofile__school',
        'userprofile__role'
    ]
    
    search_fields = [
        'username',
        'email',
        'first_name',
        'last_name',
        'userprofile__name_of_person_in_charge'
    ]
    
    # Optimize database queries for list view
    list_select_related = ['userprofile', 'userprofile__school']
    
    def get_school(self, obj):
        """Display user's school"""
        try:
            return obj.userprofile.school.full_name if obj.userprofile.school else '-'
        except UserProfile.DoesNotExist:
            return '-'
    get_school.short_description = 'School'
    get_school.admin_order_field = 'userprofile__school__full_name'
    
    def get_role(self, obj):
        """Display user's role"""
        try:
            return obj.userprofile.role
        except UserProfile.DoesNotExist:
            return '-'
    get_role.short_description = 'Role'
    get_role.admin_order_field = 'userprofile__role'
    
    def get_inline_instances(self, request, obj=None):
        """Only show inlines when editing existing user"""
        if not obj:
            return list()
        return super(UserAdmin, self).get_inline_instances(request, obj)


# -----------------------------------------
# USER MANAGEMENT SETTINGS ADMIN
# -----------------------------------------
@admin.register(UserManagementSettings)
class UserManagementSettingsAdmin(admin.ModelAdmin):
    
    list_display = [
        'id',
        'min_password_length',
        'password_expiry_days',
        'max_failed_login_attempts',
        'default_session_timeout_minutes'
    ]
    
    fieldsets = (
        ('Password Policy', {
            'fields': (
                'min_password_length',
                'require_uppercase',
                'require_lowercase',
                'require_numbers',
                'require_special_chars',
                'password_expiry_days',
                'password_history_count'
            ),
            'description': 'Configure password complexity and expiration rules'
        }),
        ('Session Management', {
            'fields': (
                'default_session_timeout_minutes',
                'max_concurrent_sessions',
                'session_warning_minutes'
            ),
            'description': 'Control user session behavior and timeouts'
        }),
        ('Account Security', {
            'fields': (
                'max_failed_login_attempts',
                'account_lockout_duration_minutes',
                'enable_two_factor_default',
                'force_password_change_on_first_login'
            ),
            'description': 'Security settings for user accounts'
        }),
        ('User Registration', {
            'fields': (
                'allow_user_registration',
                'require_admin_approval',
                'default_user_type'
            ),
            'description': 'Control how new users can register'
        }),
        ('Notifications', {
            'fields': (
                'send_welcome_emails',
                'send_password_expiry_warnings',
                'password_expiry_warning_days'
            ),
            'description': 'Email notification preferences'
        }),
        ('Audit & Logging', {
            'fields': (
                'log_login_attempts',
                'log_permission_changes'
            ),
            'description': 'System logging configuration'
        })
    )
    
    def has_add_permission(self, request):
        """Only allow one settings instance"""
        return not UserManagementSettings.objects.exists()
    
    def has_delete_permission(self, request, obj=None):
        """Prevent deletion of settings"""
        return False
    
    def changelist_view(self, request, extra_context=None):
        """Redirect to change view if settings exist"""
        if UserManagementSettings.objects.exists():
            obj = UserManagementSettings.objects.first()
            from django.urls import reverse
            from django.http import HttpResponseRedirect
            return HttpResponseRedirect(
                reverse('admin:accounts_usermanagementsettings_change', args=[obj.pk])
            )
        return super().changelist_view(request, extra_context)


# -----------------------------------------
# RE-REGISTER USER ADMIN
# -----------------------------------------
admin.site.unregister(User)
admin.site.register(User, UserAdmin)


# -----------------------------------------
# CUSTOMIZE ADMIN SITE
# -----------------------------------------
admin.site.site_header = "Schoolara Administration"
admin.site.site_title = "Schoolara Admin"
admin.site.index_title = "Welcome to Schoolara Administration"