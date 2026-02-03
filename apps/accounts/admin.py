# accounts/admin.py

from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.urls import reverse, path
from django.shortcuts import render, redirect
from django.utils.safestring import mark_safe
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.contrib import messages
from .models import School, UserProfile, UserManagementSettings
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# INLINE ADMINS
# =============================================================================

class UserProfileInline(admin.StackedInline):
    """Inline admin for UserProfile"""
    model = UserProfile
    fk_name = 'user'
    can_delete = False
    verbose_name_plural = 'Profile Information'
    
    fieldsets = (
        ('Basic Information', {
            'fields': (
                'school', 'role', 'photo', 'employee_id',
            )
        }),
        ('Personal Details', {
            'fields': (
                'mobile', 'date_of_birth', 'gender', 'national_id',
            ),
            'classes': ('collapse',)
        }),
        ('Location', {
            'fields': (
                'address', 'city', 'state_province', 'postal_code', 'country',
            ),
            'classes': ('collapse',)
        }),
        ('Localization', {
            'fields': (
                'language', 'timezone',
            ),
            'classes': ('collapse',)
        }),
        ('Employment Details', {
            'fields': (
                'department', 'position', 'employment_type',
                'date_of_appointment', 'qualification', 'specialization',
                'reports_to',
            ),
            'classes': ('collapse',)
        }),
        ('Emergency Contact', {
            'fields': (
                'emergency_contact_name', 'emergency_contact_phone',
                'emergency_contact_relationship',
            ),
            'classes': ('collapse',)
        }),
        ('Permissions - Students', {
            'fields': (
                'can_view_student_data', 'can_edit_student_data',
            ),
            'classes': ('collapse',)
        }),
        ('Permissions - Finance', {
            'fields': (
                'can_view_financial_data', 'can_edit_financial_data',
            ),
            'classes': ('collapse',)
        }),
        ('Permissions - Academics', {
            'fields': (
                'can_view_academic_data', 'can_edit_academic_data',
            ),
            'classes': ('collapse',)
        }),
        ('Permissions - HR', {
            'fields': (
                'can_view_hr_data', 'can_edit_hr_data',
            ),
            'classes': ('collapse',)
        }),
        ('Permissions - Inventory', {
            'fields': (
                'can_view_inventory_data', 'can_edit_inventory_data',
            ),
            'classes': ('collapse',)
        }),
        ('Theme Preferences', {
            'fields': (
                'theme_color', 'fixed_header', 'fixed_sidebar', 'fixed_footer',
                'header_class', 'sidebar_class', 'page_tabs_style',
            ),
            'classes': ('collapse',)
        }),
        ('Security', {
            'fields': (
                'password_changed_at', 'failed_login_attempts',
                'account_locked_until', 'last_activity',
                'two_factor_enabled', 'force_password_change',
            ),
            'classes': ('collapse',)
        }),
        ('Notifications', {
            'fields': (
                'email_notifications', 'sms_notifications',
            ),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = (
        'password_changed_at', 'failed_login_attempts',
        'account_locked_until', 'last_activity',
    )


# =============================================================================
# CUSTOM USER ADMIN
# =============================================================================

class CustomUserAdmin(BaseUserAdmin):
    """Enhanced User Admin with profile integration"""
    
    inlines = (UserProfileInline,)
    
    list_display = (
        'username', 'email', 'get_full_name_display', 'get_school',
        'get_role', 'is_active', 'is_staff', 'last_login_display',
    )
    
    list_filter = (
        'is_active', 'is_staff', 'is_superuser',
        'profile__school', 'profile__role', 'date_joined',
    )
    
    search_fields = (
        'username', 'email', 'first_name', 'last_name',
        'profile__employee_id', 'profile__mobile',
    )
    
    ordering = ('-date_joined',)
    
    fieldsets = (
        (None, {
            'fields': ('username', 'password')
        }),
        ('Personal Info', {
            'fields': ('first_name', 'last_name', 'email')
        }),
        ('Permissions', {
            'fields': (
                'is_active', 'is_staff', 'is_superuser',
                'groups', 'user_permissions',
            ),
            'classes': ('collapse',)
        }),
        ('Important Dates', {
            'fields': ('last_login', 'date_joined'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ('last_login', 'date_joined')
    
    # -------------------------------------------------------------------------
    # CUSTOM DISPLAY METHODS
    # -------------------------------------------------------------------------
    
    def get_full_name_display(self, obj):
        """Display full name"""
        full_name = obj.get_full_name()
        return full_name if full_name else '-'
    get_full_name_display.short_description = 'Full Name'
    
    def get_school(self, obj):
        """Display school name with link"""
        try:
            if obj.profile and obj.profile.school:
                url = reverse('admin:accounts_school_change', args=[obj.profile.school.pk])
                return format_html(
                    '<a href="{}">{}</a>',
                    url,
                    obj.profile.school.short_name or obj.profile.school.full_name
                )
            return '-'
        except UserProfile.DoesNotExist:
            return '-'
    get_school.short_description = 'School'
    get_school.admin_order_field = 'profile__school__full_name'
    
    def get_role(self, obj):
        """Display role with color coding"""
        try:
            if obj.profile:
                role = obj.profile.get_role_display()
                role_colors = {
                    'SUPER_ADMIN': '#e74c3c',
                    'ADMINISTRATOR': '#e67e22',
                    'DIRECTOR_STUDIES': '#3498db',
                    'FINANCE_MANAGER': '#27ae60',
                    'HEAD_TEACHER': '#9b59b6',
                }
                color = role_colors.get(obj.profile.role, '#95a5a6')
                return format_html(
                    '<span style="color: {}; font-weight: bold;">{}</span>',
                    color,
                    role
                )
            return '-'
        except UserProfile.DoesNotExist:
            return '-'
    get_role.short_description = 'Role'
    get_role.admin_order_field = 'profile__role'
    
    def last_login_display(self, obj):
        """Display last login with relative time"""
        if obj.last_login:
            from django.utils.timesince import timesince
            time_ago = timesince(obj.last_login)
            return format_html(
                '<span title="{}">{} ago</span>',
                obj.last_login.strftime('%Y-%m-%d %H:%M:%S'),
                time_ago
            )
        return '-'
    last_login_display.short_description = 'Last Login'
    last_login_display.admin_order_field = 'last_login'
    
    # -------------------------------------------------------------------------
    # ACTIONS
    # -------------------------------------------------------------------------
    
    actions = [
        'activate_users',
        'deactivate_users',
        'reset_failed_logins',
        'unlock_accounts',
        'force_password_change_action',
    ]
    
    def activate_users(self, request, queryset):
        """Activate selected users"""
        updated = queryset.update(is_active=True)
        self.message_user(
            request,
            f'{updated} user(s) successfully activated.',
            messages.SUCCESS
        )
    activate_users.short_description = 'Activate selected users'
    
    def deactivate_users(self, request, queryset):
        """Deactivate selected users"""
        updated = queryset.update(is_active=False)
        self.message_user(
            request,
            f'{updated} user(s) successfully deactivated.',
            messages.WARNING
        )
    deactivate_users.short_description = 'Deactivate selected users'
    
    def reset_failed_logins(self, request, queryset):
        """Reset failed login attempts for selected users"""
        count = 0
        for user in queryset:
            try:
                if hasattr(user, 'profile'):
                    user.profile.reset_failed_login_attempts()
                    count += 1
            except Exception as e:
                logger.error(f"Error resetting failed logins for {user.username}: {e}")
        
        self.message_user(
            request,
            f'Reset failed login attempts for {count} user(s).',
            messages.SUCCESS
        )
    reset_failed_logins.short_description = 'Reset failed login attempts'
    
    def unlock_accounts(self, request, queryset):
        """Unlock selected user accounts"""
        count = 0
        for user in queryset:
            try:
                if hasattr(user, 'profile'):
                    user.profile.account_locked_until = None
                    user.profile.failed_login_attempts = 0
                    user.profile.save(update_fields=['account_locked_until', 'failed_login_attempts'])
                    count += 1
            except Exception as e:
                logger.error(f"Error unlocking account for {user.username}: {e}")
        
        self.message_user(
            request,
            f'Unlocked {count} user account(s).',
            messages.SUCCESS
        )
    unlock_accounts.short_description = 'Unlock selected accounts'
    
    def force_password_change_action(self, request, queryset):
        """Force password change on next login for selected users"""
        count = 0
        for user in queryset:
            try:
                if hasattr(user, 'profile'):
                    user.profile.force_password_change = True
                    user.profile.save(update_fields=['force_password_change'])
                    count += 1
            except Exception as e:
                logger.error(f"Error forcing password change for {user.username}: {e}")
        
        self.message_user(
            request,
            f'{count} user(s) will be required to change password on next login.',
            messages.INFO
        )
    force_password_change_action.short_description = 'Force password change on next login'

# =============================================================================
# SCHOOL ADMIN (ENHANCED WITH INITIALIZATION) ⭐
# =============================================================================

@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    """Admin interface for School model with initialization functionality"""
    
    list_display = (
        'full_name', 'short_name', 'school_type', 'boarding_type',
        'gender_type', 'country', 'subscription_status_display',
        'active_subscription_badge', 'user_count', 'student_count',
        'setup_status_display',  # ⭐ NEW
    )
    
    list_filter = (
        'school_type', 'boarding_type', 'gender_type',
        'country', 'is_active_subscription', 'subscription_plan',
        'established_date',
        'is_initial_setup_complete',  # ⭐ NEW
        'accounting_complexity',  # ⭐ NEW
    )
    
    search_fields = (
        'full_name', 'short_name', 'abbreviation', 'domain',
        'database_alias', 'contact_phone', 'contact_email',
    )
    
    readonly_fields = (
        'created_at', 'updated_at', 'subscription_status',
        'user_count', 'student_count', 'active_teachers_count',
        'setup_completed_at', 'setup_completed_by',  # ⭐ NEW
        'recommended_complexity',  # ⭐ NEW
        'recommended_accounts_count',  # ⭐ NEW
    )
    
    fieldsets = (
        ('Basic Information', {
            'fields': (
                'full_name', 'short_name', 'receipt_name',
                'abbreviation', 'description', 'school_motto',
            )
        }),
        ('System Configuration', {
            'fields': (
                'domain', 'database_alias', 'timezone', 'language',
            ),
            'classes': ('collapse',)
        }),
        ('School Classification', {
            'fields': (
                'school_type', 'boarding_type', 'gender_type',
            )
        }),
        ('Location & Contact', {
            'fields': (
                'address', 'city', 'state_province', 'postal_code', 'country',
                'contact_phone', 'alternative_contact', 'contact_email',
            )
        }),
        ('Digital Presence', {
            'fields': (
                'website', 'facebook_page', 'twitter_handle',
                'instagram_handle', 'linkedin_page', 'youtube_channel',
            ),
            'classes': ('collapse',)
        }),
        ('Administrative Details', {
            'fields': (
                'established_date', 'school_license', 'registration_number',
                'tax_id', 'student_capacity', 'operating_hours',
            ),
            'classes': ('collapse',)
        }),
        ('Visual Branding', {
            'fields': (
                'school_logo', 'favicon', 'brand_colors',
            ),
            'classes': ('collapse',)
        }),
        ('Subscription & Billing', {
            'fields': (
                'subscription_plan', 'subscription_start', 'subscription_end',
                'is_active_subscription', 'subscription_status',
            )
        }),
        ('Portal Settings', {
            'fields': (
                'enable_online_applications', 'enable_parent_portal',
                'enable_student_portal',
            ),
            'classes': ('collapse',)
        }),
        # ⭐ NEW SECTION
        ('Financial Configuration', {
            'fields': (
                'accounting_complexity',
                'recommended_complexity',
                'recommended_accounts_count',
            ),
            'description': (
                'Configure accounting complexity based on school size and type. '
                'This determines how many accounts are created during initialization.'
            )
        }),
        # ⭐ NEW SECTION
        ('Initialization Status', {
            'fields': (
                'is_financial_setup_complete',
                'is_academic_setup_complete',
                'is_initial_setup_complete',
                'setup_completed_at',
                'setup_completed_by',
            ),
            'description': 'Track school initialization progress'
        }),
        ('Statistics', {
            'fields': (
                'user_count', 'student_count', 'active_teachers_count',
            ),
            'classes': ('collapse',)
        }),
        ('Audit Information', {
            'fields': (
                'created_at', 'updated_at',
            ),
            'classes': ('collapse',)
        }),
    )
    
    # =========================================================================
    # CUSTOM DISPLAY METHODS ⭐ NEW
    # =========================================================================
    
    def setup_status_display(self, obj):
        """Display setup completion status"""
        if obj.is_initial_setup_complete:
            return format_html(
                '<span style="background-color: #27ae60; color: white; '
                'padding: 3px 10px; border-radius: 3px;">✓ Complete</span>'
            )
        else:
            return format_html(
                '<span style="background-color: #e74c3c; color: white; '
                'padding: 3px 10px; border-radius: 3px;">⚠ Pending</span>'
            )
    setup_status_display.short_description = 'Setup'
    setup_status_display.admin_order_field = 'is_initial_setup_complete'
    
    def recommended_complexity(self, obj):
        """Display recommended accounting complexity"""
        complexity = obj.get_accounting_complexity_level()
        colors = {
            'BASIC': '#3498db',
            'STANDARD': '#27ae60',
            'ADVANCED': '#e67e22',
        }
        color = colors.get(complexity, '#95a5a6')
        
        descriptions = {
            'BASIC': '10-12 accounts (small schools)',
            'STANDARD': '20-30 accounts (medium schools)',
            'ADVANCED': '50-60 accounts (large schools)',
        }
        
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span><br>'
            '<small style="color: #7f8c8d;">{}</small>',
            color,
            complexity,
            descriptions.get(complexity, '')
        )
    recommended_complexity.short_description = 'Recommended Complexity'
    
    def recommended_accounts_count(self, obj):
        """Display recommended number of accounts"""
        count = obj.get_recommended_accounts_count()
        return format_html(
            '<strong>{}</strong> accounts',
            count
        )
    recommended_accounts_count.short_description = 'Recommended Accounts'
    
    # =========================================================================
    # EXISTING DISPLAY METHODS (keep all your existing ones)
    # =========================================================================
    
    def subscription_status_display(self, obj):
        """Display subscription status with color coding"""
        status = obj.subscription_status
        colors = {
            'Active': '#27ae60',
            'Expired': '#e74c3c',
            'Inactive': '#95a5a6',
        }
        color = colors.get(status, '#95a5a6')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            status
        )
    subscription_status_display.short_description = 'Subscription'
    
    def active_subscription_badge(self, obj):
        """Display active subscription badge"""
        if obj.is_subscription_active:
            return format_html(
                '<span style="background-color: #27ae60; color: white; '
                'padding: 3px 10px; border-radius: 3px;">✓ Active</span>'
            )
        else:
            return format_html(
                '<span style="background-color: #e74c3c; color: white; '
                'padding: 3px 10px; border-radius: 3px;">✗ Inactive</span>'
            )
    active_subscription_badge.short_description = 'Status'
    
    def user_count(self, obj):
        """Display count of active users"""
        count = obj.active_users_count
        return format_html(
            '<strong>{}</strong> user{}',
            count,
            's' if count != 1 else ''
        )
    user_count.short_description = 'Users'
    
    def student_count(self, obj):
        """Display count of active students"""
        count = obj.active_students_count
        return format_html(
            '<strong>{}</strong> student{}',
            count,
            's' if count != 1 else ''
        )
    student_count.short_description = 'Students'
    
    def active_teachers_count(self, obj):
        """Display count of active teachers"""
        count = obj.active_teachers_count
        return format_html(
            '<strong>{}</strong> teacher{}',
            count,
            's' if count != 1 else ''
        )
    active_teachers_count.short_description = 'Teachers'
    
    def subscription_status(self, obj):
        """Get subscription status for readonly field"""
        return obj.subscription_status
    subscription_status.short_description = 'Current Status'
    
    # =========================================================================
    # CUSTOM URLS ⭐ NEW
    # =========================================================================
    
    def get_urls(self):
        """Add custom URLs for school initialization"""
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:school_id>/initialize/',
                self.admin_site.admin_view(self.initialize_school_view),
                name='accounts_school_initialize',
            ),
            path(
                '<int:school_id>/reinitialize/',
                self.admin_site.admin_view(self.reinitialize_school_view),
                name='accounts_school_reinitialize',
            ),
        ]
        return custom_urls + urls
    
    # =========================================================================
    # INITIALIZATION VIEWS ⭐ NEW
    # =========================================================================
    
    def initialize_school_view(self, request, school_id):
        """
        View to initialize a school with configuration.
        Shows a form to select accounting complexity and confirm initialization.
        """
        school = self.get_object(request, school_id)
        
        if school is None:
            messages.error(request, "School not found.")
            return redirect('admin:accounts_school_changelist')
        
        # Check if already initialized
        if school.is_initial_setup_complete:
            messages.warning(
                request,
                f"{school.full_name} is already initialized. "
                "Use 'Re-initialize' if you want to reset it."
            )
            return redirect('admin:accounts_school_change', school_id)
        
        if request.method == 'POST':
            # Get user's choices
            accounting_complexity = request.POST.get('accounting_complexity')
            confirm = request.POST.get('confirm')
            
            if not confirm:
                messages.error(request, "Please confirm initialization.")
                return redirect(request.path)
            
            # Update school's accounting complexity if specified
            if accounting_complexity:
                school.accounting_complexity = accounting_complexity
                school.save(update_fields=['accounting_complexity'])
            
            # Perform initialization
            try:
                from apps.core.services.school_init_config import initialize_school
                
                with transaction.atomic():
                    result = initialize_school(school, user=request.user)
                
                if result['success']:
                    messages.success(
                        request,
                        format_html(
                            '<strong>✓ Initialization Successful!</strong><br>'
                            'Created: {} accounts, {} fee categories, {} expense categories<br>'
                            'Complexity: {}',
                            result['created'].get('accounts', 0),
                            result['created'].get('fee_categories', 0),
                            result['created'].get('expense_categories', 0),
                            result['complexity']
                        )
                    )
                    logger.info(f"School {school.full_name} initialized by {request.user.username}")
                    return redirect('admin:accounts_school_change', school_id)
                else:
                    messages.error(
                        request,
                        f"Initialization failed: {', '.join(result['errors'])}"
                    )
                    logger.error(f"Failed to initialize {school.full_name}: {result['errors']}")
                    
            except Exception as e:
                messages.error(request, f"Initialization error: {str(e)}")
                logger.exception(f"Error initializing school {school.full_name}")
        
        # GET request - show confirmation form
        context = {
            'title': f'Initialize {school.full_name}',
            'school': school,
            'opts': self.model._meta,
            'has_view_permission': self.has_view_permission(request, school),
            'site_header': 'Schoolara Administration',
            'site_title': 'School Initialization',
            'recommended_complexity': school.get_accounting_complexity_level(),
            'recommended_accounts': school.get_recommended_accounts_count(),
            'needs_boarding': school.needs_boarding_accounts(),
            'complexity_choices': [
                ('BASIC', 'Basic (10-12 accounts)', 'Small schools, simple tracking'),
                ('STANDARD', 'Standard (20-30 accounts)', 'Medium schools, balanced features'),
                ('ADVANCED', 'Advanced (50-60 accounts)', 'Large schools, detailed tracking'),
            ],
        }
        
        return render(request, 'admin/accounts/school/initialize.html', context)
    
    def reinitialize_school_view(self, request, school_id):
        """
        View to re-initialize a school (wipes and recreates).
        WARNING: This deletes all existing financial data!
        """
        school = self.get_object(request, school_id)
        
        if school is None:
            messages.error(request, "School not found.")
            return redirect('admin:accounts_school_changelist')
        
        if request.method == 'POST':
            confirm_text = request.POST.get('confirm_text', '').strip()
            accounting_complexity = request.POST.get('accounting_complexity')
            
            # Require typing school name for confirmation
            if confirm_text != school.full_name:
                messages.error(
                    request,
                    f"Please type the school name exactly: {school.full_name}"
                )
                return redirect(request.path)
            
            try:
                from finance.models import Account
                from fees.models import FeesCategory
                from core.models import FinancialSettings, CoreAccountMappings
                
                with transaction.atomic():
                    # Delete existing data
                    Account.objects.filter(school=school).delete()
                    FeesCategory.objects.filter(school=school).delete()
                    
                    # Delete financial settings and mappings
                    if hasattr(school, 'financial_settings'):
                        if hasattr(school.financial_settings, 'account_mappings'):
                            school.financial_settings.account_mappings.delete()
                        school.financial_settings.delete()
                    
                    # Reset initialization flags
                    school.is_financial_setup_complete = False
                    school.is_academic_setup_complete = False
                    school.is_initial_setup_complete = False
                    school.setup_completed_at = None
                    school.setup_completed_by = None
                    
                    # Update complexity if specified
                    if accounting_complexity:
                        school.accounting_complexity = accounting_complexity
                    
                    school.save()
                    
                    # Re-initialize
                    from apps.core.services.school_init_config import initialize_school
                    result = initialize_school(school, user=request.user)
                    
                    if result['success']:
                        messages.success(
                            request,
                            format_html(
                                '<strong>✓ Re-initialization Successful!</strong><br>'
                                'All previous data deleted and recreated<br>'
                                'Created: {} accounts, {} fee categories',
                                result['created'].get('accounts', 0),
                                result['created'].get('fee_categories', 0)
                            )
                        )
                        logger.warning(
                            f"School {school.full_name} re-initialized by {request.user.username}"
                        )
                        return redirect('admin:accounts_school_change', school_id)
                    else:
                        messages.error(
                            request,
                            f"Re-initialization failed: {', '.join(result['errors'])}"
                        )
                        
            except Exception as e:
                messages.error(request, f"Re-initialization error: {str(e)}")
                logger.exception(f"Error re-initializing school {school.full_name}")
        
        # GET request - show confirmation form
        context = {
            'title': f'Re-initialize {school.full_name}',
            'school': school,
            'opts': self.model._meta,
            'has_view_permission': self.has_view_permission(request, school),
            'site_header': 'Schoolara Administration',
            'site_title': 'School Re-initialization',
            'warning': 'This will DELETE ALL existing accounts, fee categories, and financial settings!',
            'recommended_complexity': school.get_accounting_complexity_level(),
            'complexity_choices': [
                ('BASIC', 'Basic (10-12 accounts)'),
                ('STANDARD', 'Standard (20-30 accounts)'),
                ('ADVANCED', 'Advanced (50-60 accounts)'),
            ],
        }
        
        return render(request, 'admin/accounts/school/reinitialize.html', context)
    
    # =========================================================================
    # CUSTOM ACTIONS ⭐ NEW
    # =========================================================================
    
    actions = [
        'activate_subscriptions',
        'deactivate_subscriptions',
        'enable_all_portals',
        'initialize_selected_schools',  # ⭐ NEW
    ]
    
    def initialize_selected_schools(self, request, queryset):
        """
        Bulk initialize selected schools.
        Only initializes schools that haven't been initialized yet.
        """
        from apps.core.services.school_init_config import initialize_school
        
        # Filter to only non-initialized schools
        schools_to_init = queryset.filter(is_initial_setup_complete=False)
        
        if not schools_to_init.exists():
            messages.warning(request, "All selected schools are already initialized.")
            return
        
        success_count = 0
        error_count = 0
        
        for school in schools_to_init:
            try:
                with transaction.atomic():
                    result = initialize_school(school, user=request.user)
                    
                    if result['success']:
                        success_count += 1
                        logger.info(f"Bulk initialized {school.full_name}")
                    else:
                        error_count += 1
                        logger.error(f"Failed to bulk initialize {school.full_name}")
                        
            except Exception as e:
                error_count += 1
                logger.exception(f"Error bulk initializing {school.full_name}")
        
        if success_count > 0:
            messages.success(
                request,
                f"✓ Successfully initialized {success_count} school(s)."
            )
        
        if error_count > 0:
            messages.error(
                request,
                f"✗ Failed to initialize {error_count} school(s). Check logs."
            )
    
    initialize_selected_schools.short_description = "Initialize selected schools"
    
    # Your existing actions
    def activate_subscriptions(self, request, queryset):
        """Activate subscriptions for selected schools"""
        updated = queryset.update(is_active_subscription=True)
        self.message_user(
            request,
            f'{updated} school subscription(s) activated.',
            messages.SUCCESS
        )
    activate_subscriptions.short_description = 'Activate subscriptions'
    
    def deactivate_subscriptions(self, request, queryset):
        """Deactivate subscriptions for selected schools"""
        updated = queryset.update(is_active_subscription=False)
        self.message_user(
            request,
            f'{updated} school subscription(s) deactivated.',
            messages.WARNING
        )
    deactivate_subscriptions.short_description = 'Deactivate subscriptions'
    
    def enable_all_portals(self, request, queryset):
        """Enable all portals for selected schools"""
        updated = queryset.update(
            enable_online_applications=True,
            enable_parent_portal=True,
            enable_student_portal=True
        )
        self.message_user(
            request,
            f'All portals enabled for {updated} school(s).',
            messages.SUCCESS
        )
    enable_all_portals.short_description = 'Enable all portals'
    
    # =========================================================================
    # CHANGE FORM TEMPLATE ⭐ NEW
    # =========================================================================
    
    def change_view(self, request, object_id, form_url='', extra_context=None):
        """Add initialize button to change form"""
        extra_context = extra_context or {}
        
        obj = self.get_object(request, object_id)
        if obj:
            extra_context['show_initialize_button'] = not obj.is_initial_setup_complete
            extra_context['show_reinitialize_button'] = obj.is_initial_setup_complete
        
        return super().change_view(request, object_id, form_url, extra_context)


# =============================================================================
# USER PROFILE ADMIN
# =============================================================================

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """Admin interface for UserProfile model"""
    
    list_display = (
        'user', 'get_full_name', 'school', 'role', 'employee_id',
        'department', 'employment_type', 'is_active_display',
        'last_activity_display', 'account_status',
    )
    
    list_filter = (
        'school', 'role', 'employment_type', 'gender',
        'can_view_financial_data', 'can_edit_financial_data',
        'can_view_academic_data', 'can_edit_academic_data',
        'two_factor_enabled', 'user__is_active',
    )
    
    search_fields = (
        'user__username', 'user__email', 'user__first_name', 'user__last_name',
        'employee_id', 'mobile', 'department', 'position',
    )
    
    readonly_fields = (
        'created_at', 'updated_at', 'password_changed_at',
        'failed_login_attempts', 'account_locked_until',
        'last_activity', 'years_of_service_display', 'age_display',
    )
    
    fieldsets = (
        ('User & School', {
            'fields': ('user', 'school', 'role')
        }),
        ('Personal Information', {
            'fields': (
                'photo', 'mobile', 'date_of_birth', 'gender',
                'national_id', 'age_display',
            )
        }),
        ('Location', {
            'fields': (
                'address', 'city', 'state_province', 'postal_code', 'country',
            ),
            'classes': ('collapse',)
        }),
        ('Localization', {
            'fields': ('language', 'timezone'),
            'classes': ('collapse',)
        }),
        ('Employment Details', {
            'fields': (
                'employee_id', 'department', 'position', 'employment_type',
                'date_of_appointment', 'years_of_service_display',
                'qualification', 'specialization', 'reports_to',
            )
        }),
        ('Emergency Contact', {
            'fields': (
                'emergency_contact_name', 'emergency_contact_phone',
                'emergency_contact_relationship',
            ),
            'classes': ('collapse',)
        }),
        ('Permissions - Students', {
            'fields': ('can_view_student_data', 'can_edit_student_data'),
            'classes': ('collapse',)
        }),
        ('Permissions - Finance', {
            'fields': ('can_view_financial_data', 'can_edit_financial_data'),
            'classes': ('collapse',)
        }),
        ('Permissions - Academics', {
            'fields': ('can_view_academic_data', 'can_edit_academic_data'),
            'classes': ('collapse',)
        }),
        ('Permissions - HR', {
            'fields': ('can_view_hr_data', 'can_edit_hr_data'),
            'classes': ('collapse',)
        }),
        ('Permissions - Inventory', {
            'fields': ('can_view_inventory_data', 'can_edit_inventory_data'),
            'classes': ('collapse',)
        }),
        ('Theme Preferences', {
            'fields': (
                'theme_color', 'fixed_header', 'fixed_sidebar', 'fixed_footer',
                'header_class', 'sidebar_class', 'page_tabs_style',
            ),
            'classes': ('collapse',)
        }),
        ('Security', {
            'fields': (
                'password_changed_at', 'failed_login_attempts',
                'account_locked_until', 'last_activity',
                'two_factor_enabled', 'force_password_change',
            )
        }),
        ('Notifications', {
            'fields': ('email_notifications', 'sms_notifications'),
            'classes': ('collapse',)
        }),
        ('Audit Information', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    # -------------------------------------------------------------------------
    # CUSTOM DISPLAY METHODS
    # -------------------------------------------------------------------------
    
    def get_full_name(self, obj):
        """Display user's full name"""
        return obj.full_name
    get_full_name.short_description = 'Full Name'
    get_full_name.admin_order_field = 'user__first_name'
    
    def is_active_display(self, obj):
        """Display active status"""
        if obj.user.is_active:
            return format_html(
                '<span style="color: #27ae60;">✓ Active</span>'
            )
        else:
            return format_html(
                '<span style="color: #e74c3c;">✗ Inactive</span>'
            )
    is_active_display.short_description = 'Active'
    is_active_display.admin_order_field = 'user__is_active'
    
    def last_activity_display(self, obj):
        """Display last activity with relative time"""
        if obj.last_activity:
            from django.utils.timesince import timesince
            time_ago = timesince(obj.last_activity)
            return format_html(
                '<span title="{}">{} ago</span>',
                obj.last_activity.strftime('%Y-%m-%d %H:%M:%S'),
                time_ago
            )
        return '-'
    last_activity_display.short_description = 'Last Activity'
    last_activity_display.admin_order_field = 'last_activity'
    
    def account_status(self, obj):
        """Display account lock status"""
        if obj.is_account_locked:
            return format_html(
                '<span style="background-color: #e74c3c; color: white; '
                'padding: 3px 8px; border-radius: 3px;">🔒 Locked</span>'
            )
        elif obj.force_password_change:
            return format_html(
                '<span style="background-color: #f39c12; color: white; '
                'padding: 3px 8px; border-radius: 3px;">⚠ Password Change Required</span>'
            )
        else:
            return format_html(
                '<span style="color: #27ae60;">✓ OK</span>'
            )
    account_status.short_description = 'Account Status'
    
    def years_of_service_display(self, obj):
        """Display years of service"""
        years = obj.years_of_service
        if years is not None:
            return f"{years} year{'s' if years != 1 else ''}"
        return '-'
    years_of_service_display.short_description = 'Years of Service'
    
    def age_display(self, obj):
        """Display age"""
        age = obj.age
        if age is not None:
            return f"{age} years"
        return '-'
    age_display.short_description = 'Age'
    
    # -------------------------------------------------------------------------
    # ACTIONS
    # -------------------------------------------------------------------------
    
    actions = [
        'reset_failed_logins',
        'unlock_accounts',
        'enable_2fa',
        'disable_2fa',
        'force_password_change',
        'grant_financial_view_permission',
        'grant_academic_view_permission',
    ]
    
    def reset_failed_logins(self, request, queryset):
        """Reset failed login attempts"""
        count = 0
        for profile in queryset:
            profile.reset_failed_login_attempts()
            count += 1
        
        self.message_user(
            request,
            f'Reset failed login attempts for {count} user(s).',
            messages.SUCCESS
        )
    reset_failed_logins.short_description = 'Reset failed login attempts'
    
    def unlock_accounts(self, request, queryset):
        """Unlock user accounts"""
        queryset.update(
            account_locked_until=None,
            failed_login_attempts=0
        )
        
        self.message_user(
            request,
            f'Unlocked {queryset.count()} account(s).',
            messages.SUCCESS
        )
    unlock_accounts.short_description = 'Unlock accounts'
    
    def enable_2fa(self, request, queryset):
        """Enable two-factor authentication"""
        updated = queryset.update(two_factor_enabled=True)
        self.message_user(
            request,
            f'Enabled 2FA for {updated} user(s).',
            messages.SUCCESS
        )
    enable_2fa.short_description = 'Enable two-factor authentication'
    
    def disable_2fa(self, request, queryset):
        """Disable two-factor authentication"""
        updated = queryset.update(two_factor_enabled=False)
        self.message_user(
            request,
            f'Disabled 2FA for {updated} user(s).',
            messages.WARNING
        )
    disable_2fa.short_description = 'Disable two-factor authentication'
    
    def force_password_change(self, request, queryset):
        """Force password change on next login"""
        updated = queryset.update(force_password_change=True)
        self.message_user(
            request,
            f'{updated} user(s) will be required to change password on next login.',
            messages.INFO
        )
    force_password_change.short_description = 'Force password change on next login'
    
    def grant_financial_view_permission(self, request, queryset):
        """Grant financial view permission"""
        updated = queryset.update(can_view_financial_data=True)
        self.message_user(
            request,
            f'Granted financial view permission to {updated} user(s).',
            messages.SUCCESS
        )
    grant_financial_view_permission.short_description = 'Grant financial view permission'
    
    def grant_academic_view_permission(self, request, queryset):
        """Grant academic view permission"""
        updated = queryset.update(can_view_academic_data=True)
        self.message_user(
            request,
            f'Granted academic view permission to {updated} user(s).',
            messages.SUCCESS
        )
    grant_academic_view_permission.short_description = 'Grant academic view permission'


# =============================================================================
# USER MANAGEMENT SETTINGS ADMIN
# =============================================================================

@admin.register(UserManagementSettings)
class UserManagementSettingsAdmin(admin.ModelAdmin):
    """Admin interface for UserManagementSettings model"""
    
    fieldsets = (
        ('Password Policy', {
            'fields': (
                'min_password_length', 'require_uppercase', 'require_lowercase',
                'require_numbers', 'require_special_chars',
                'password_expiry_days', 'password_history_count',
            )
        }),
        ('Session Management', {
            'fields': (
                'default_session_timeout_minutes', 'max_concurrent_sessions',
                'session_warning_minutes',
            ),
            'classes': ('collapse',)
        }),
        ('Account Security', {
            'fields': (
                'max_failed_login_attempts', 'account_lockout_duration_minutes',
                'enable_two_factor_default', 'force_password_change_on_first_login',
            )
        }),
        ('User Registration', {
            'fields': (
                'allow_user_registration', 'require_admin_approval',
                'default_user_role',
            ),
            'classes': ('collapse',)
        }),
        ('Notifications', {
            'fields': (
                'send_welcome_emails', 'send_password_expiry_warnings',
                'password_expiry_warning_days', 'send_account_lockout_notifications',
            ),
            'classes': ('collapse',)
        }),
        ('Audit & Logging', {
            'fields': (
                'log_login_attempts', 'log_permission_changes',
                'log_password_changes',
            ),
            'classes': ('collapse',)
        }),
        ('IP Restrictions', {
            'fields': (
                'enable_ip_whitelist', 'whitelisted_ips',
            ),
            'classes': ('collapse',)
        }),
    )
    
    def has_add_permission(self, request):
        """Prevent adding more than one settings instance"""
        return not UserManagementSettings.objects.exists()
    
    def has_delete_permission(self, request, obj=None):
        """Prevent deletion of settings"""
        return False


# =============================================================================
# UNREGISTER AND RE-REGISTER USER MODEL
# =============================================================================

# Unregister the default User admin
admin.site.unregister(User)

# Register our custom User admin
admin.site.register(User, CustomUserAdmin)


# =============================================================================
# ADMIN SITE CUSTOMIZATION
# =============================================================================

admin.site.site_header = "Schoolara Administration"
admin.site.site_title = "Schoolara Admin"
admin.site.index_title = "Welcome to Schoolara Administration"