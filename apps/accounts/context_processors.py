# accounts/context_processors.py

"""
Accounts Context Processors for School Management System

Provides global context variables for all templates including:
- Active school information
- User profile and role information
- Theme preferences and customization
- Color schemes and branding
- Navigation and UI preferences

These context processors work alongside core.context_processors to provide
complete template context for the application.
"""

import logging

logger = logging.getLogger(__name__)


def active_school(request):
    """
    Adds the current active school to all templates.
    
    Provides school information based on the authenticated user's profile.
    This is essential for multi-school deployments or when displaying
    school-specific branding and information.
    
    Context variables:
        - active_school: School instance from user's profile
        - school_name: Display name of the school
        - school_logo: URL to school logo
        - school_motto: School motto/slogan
    """
    context = {
        'active_school': None,
        'school_name': None,
        'school_logo': None,
        'school_motto': None,
        'school_type': None,
    }
    
    if request.user.is_authenticated:
        try:
            profile = getattr(request.user, 'profile', None)
            if profile and profile.school:
                school = profile.school
                context['active_school'] = school
                context['school_name'] = school.display_name
                context['school_logo'] = school.school_logo.url if school.school_logo else None
                context['school_motto'] = school.school_motto
                context['school_type'] = school.get_school_type_display()
                context['school_abbreviation'] = school.abbreviation
                context['school_contact_email'] = school.contact_email
                context['school_contact_phone'] = school.contact_phone
        except Exception as e:
            logger.error(f"Error loading active school: {e}")
    
    return context


def user_context(request):
    """
    Provides user-specific context including profile and preferences.
    
    This context processor enriches templates with user profile information,
    role details, and UI preferences. Essential for personalized experiences
    and role-based UI customization.
    
    Context variables:
        - user_first_name: User's first name
        - user_last_name: User's last name
        - user_full_name: Complete name
        - user_email: User's email address
        - user_role: User's role code in the system
        - user_role_display: User's role human-readable name
        - user_profile: Complete UserProfile instance
        - user_profile_pic: URL to profile photo
        - user_school: School the user belongs to
        - user_department: User's department
        - user_position: User's job title/position
    """
    context = {
        'user_first_name': '',
        'user_last_name': '',
        'user_full_name': '',
        'user_email': '',
        'user_role': None,
        'user_role_display': '',
        'user_profile': None,
        'user_profile_pic': None,
        'user_school': None,
        'user_school_name': '',
        'user_department': '',
        'user_position': '',
        'user_employee_id': '',
    }
    
    if request.user.is_authenticated:
        try:
            # Basic user info
            context['user_first_name'] = request.user.first_name or ''
            context['user_last_name'] = request.user.last_name or ''
            
            # Build full name properly
            full_name = request.user.get_full_name().strip()
            if not full_name:
                # If no first/last name, try to use username without email domain
                username = request.user.username
                if '@' in username:
                    # Extract name part before @ and capitalize it
                    full_name = username.split('@')[0].replace('.', ' ').replace('_', ' ').title()
                else:
                    full_name = username
            
            context['user_full_name'] = full_name
            # Email - use email field if set, otherwise use username (which is usually the email)
            context['user_email'] = request.user.email or request.user.username
            
            # Profile-specific info
            profile = getattr(request.user, 'profile', None)
            if profile:
                context['user_profile'] = profile
                context['user_role'] = profile.role
                context['user_role_display'] = profile.get_role_display()
                context['user_profile_pic'] = profile.photo.url if profile.photo else None
                context['user_school'] = profile.school
                context['user_school_name'] = profile.school.display_name if profile.school else ''
                context['user_department'] = profile.department or ''
                context['user_position'] = profile.position or ''
                context['user_employee_id'] = profile.employee_id or ''
                
                # Permission flags for quick template checks
                context['is_admin'] = profile.is_admin_user()
                context['is_teacher'] = profile.is_teacher()
                context['is_senior_staff'] = profile.is_senior_staff()
                context['can_manage_users'] = profile.can_manage_users()
                context['can_manage_finances'] = profile.can_manage_finances()
                context['can_manage_academics'] = profile.can_manage_academics()
                context['can_manage_students'] = profile.can_manage_students()
                context['can_manage_hr'] = profile.can_manage_hr()
                context['can_manage_inventory'] = profile.can_manage_inventory()
                
        except Exception as e:
            logger.error(f"Error loading user context: {e}")
    
    return context


def user_theme_preferences(request):
    """
    Provides user's theme and UI preferences.
    
    This context processor handles all theme-related settings including
    layout preferences, color schemes, and UI customization options.
    
    Context variables:
        - fixed_header: Boolean for fixed header
        - fixed_sidebar: Boolean for fixed sidebar
        - fixed_footer: Boolean for fixed footer
        - header_class: CSS class for header
        - sidebar_class: CSS class for sidebar
        - page_tabs_style: Style for page tabs
        - theme_color: Selected theme color
        - email_notifications: Email notification preference
        - sms_notifications: SMS notification preference
    """
    context = {
        'fixed_header': False,
        'fixed_sidebar': False,
        'fixed_footer': False,
        'header_class': '',
        'sidebar_class': '',
        'page_tabs_style': 'body-tabs-shadow',
        'theme_color': 'app-theme-white',
        'email_notifications': True,
        'sms_notifications': False,
        'preferred_language': 'en',
        'preferred_timezone': 'Africa/Kampala',
    }
    
    if request.user.is_authenticated:
        try:
            profile = getattr(request.user, 'profile', None)
            if profile:
                # Layout preferences
                context['fixed_header'] = profile.fixed_header
                context['fixed_sidebar'] = profile.fixed_sidebar
                context['fixed_footer'] = profile.fixed_footer
                context['header_class'] = profile.header_class or ''
                context['sidebar_class'] = profile.sidebar_class or ''
                context['page_tabs_style'] = profile.page_tabs_style or 'body-tabs-shadow'
                context['theme_color'] = profile.theme_color or 'app-theme-white'
                
                # Notification preferences
                context['email_notifications'] = profile.email_notifications
                context['sms_notifications'] = profile.sms_notifications
                
                # Localization preferences
                context['preferred_language'] = profile.language
                context['preferred_timezone'] = profile.timezone
                
        except Exception as e:
            logger.error(f"Error loading theme preferences: {e}")
    
    return context


def theme_colors(request):
    """
    Provides comprehensive theme color configuration for templates.
    
    This includes color schemes, text color mappings, and theme options
    used throughout the application for consistent branding and UI.
    
    Context variables:
        - color_schemes: Dictionary of all available colors
        - basic_colors: List of basic Bootstrap colors
        - gradient_colors: List of gradient/premium colors
        - all_colors: Combined list of all colors
        - theme_options: Available theme options
        - tab_style_options: Available tab styles
    """
    
    # Define color schemes with their properties
    COLOR_SCHEMES = {
        # Basic Bootstrap colors
        'primary': {'label': 'Primary Blue', 'text': 'light'},
        'secondary': {'label': 'Secondary Gray', 'text': 'light'},
        'success': {'label': 'Success Green', 'text': 'light'},
        'info': {'label': 'Info Cyan', 'text': 'light'},
        'warning': {'label': 'Warning Yellow', 'text': 'dark'},
        'danger': {'label': 'Danger Red', 'text': 'light'},
        'light': {'label': 'Light', 'text': 'dark'},
        'dark': {'label': 'Dark', 'text': 'light'},
        'focus': {'label': 'Focus Purple', 'text': 'light'},
        'alternate': {'label': 'Alternate', 'text': 'light'},
        
        # Gradient/Premium colors
        'vicious-stance': {'label': 'Vicious Stance', 'text': 'light'},
        'midnight-bloom': {'label': 'Midnight Bloom', 'text': 'light'},
        'night-sky': {'label': 'Night Sky', 'text': 'light'},
        'slick-carbon': {'label': 'Slick Carbon', 'text': 'light'},
        'asteroid': {'label': 'Asteroid', 'text': 'light'},
        'royal': {'label': 'Royal', 'text': 'light'},
        'warm-flame': {'label': 'Warm Flame', 'text': 'dark'},
        'night-fade': {'label': 'Night Fade', 'text': 'dark'},
        'sunny-morning': {'label': 'Sunny Morning', 'text': 'dark'},
        'tempting-azure': {'label': 'Tempting Azure', 'text': 'dark'},
        'amy-crisp': {'label': 'Amy Crisp', 'text': 'dark'},
        'heavy-rain': {'label': 'Heavy Rain', 'text': 'dark'},
        'mean-fruit': {'label': 'Mean Fruit', 'text': 'dark'},
        'malibu-beach': {'label': 'Malibu Beach', 'text': 'light'},
        'deep-blue': {'label': 'Deep Blue', 'text': 'dark'},
        'ripe-malin': {'label': 'Ripe Malin', 'text': 'light'},
        'arielle-smile': {'label': 'Arielle Smile', 'text': 'light'},
        'plum-plate': {'label': 'Plum Plate', 'text': 'light'},
        'happy-fisher': {'label': 'Happy Fisher', 'text': 'dark'},
        'happy-itmeo': {'label': 'Happy Itmeo', 'text': 'light'},
        'mixed-hopes': {'label': 'Mixed Hopes', 'text': 'light'},
        'strong-bliss': {'label': 'Strong Bliss', 'text': 'light'},
        'grow-early': {'label': 'Grow Early', 'text': 'light'},
        'love-kiss': {'label': 'Love Kiss', 'text': 'light'},
        'premium-dark': {'label': 'Premium Dark', 'text': 'light'},
        'happy-green': {'label': 'Happy Green', 'text': 'light'},
    }
    
    # Separate basic and gradient colors for template organization
    basic_color_keys = [
        'primary', 'secondary', 'success', 'info', 
        'warning', 'danger', 'light', 'dark', 'focus', 'alternate'
    ]
    
    gradient_color_keys = [k for k in COLOR_SCHEMES.keys() if k not in basic_color_keys]
    
    # Build color lists with full information
    basic_colors = [
        {
            'key': key,
            'label': COLOR_SCHEMES[key]['label'],
            'text_class': COLOR_SCHEMES[key]['text'],
            'bg_class': f'bg-{key}',
            'full_class': f"bg-{key} header-text-{COLOR_SCHEMES[key]['text']}"
        }
        for key in basic_color_keys
    ]
    
    gradient_colors = [
        {
            'key': key,
            'label': COLOR_SCHEMES[key]['label'],
            'text_class': COLOR_SCHEMES[key]['text'],
            'bg_class': f'bg-{key}',
            'full_class': f"bg-{key} header-text-{COLOR_SCHEMES[key]['text']}"
        }
        for key in gradient_color_keys
    ]
    
    # Get user's current theme preferences if authenticated
    current_theme_color = 'app-theme-white'
    current_tab_style = 'body-tabs-shadow'
    
    if request.user.is_authenticated:
        profile = getattr(request.user, 'profile', None)
        if profile:
            current_theme_color = profile.theme_color or 'app-theme-white'
            current_tab_style = profile.page_tabs_style or 'body-tabs-shadow'
    
    # Theme options
    theme_options = [
        {
            'value': 'app-theme-white',
            'label': 'White Theme',
            'class': 'light',
            'active': current_theme_color == 'app-theme-white'
        },
        {
            'value': 'app-theme-gray',
            'label': 'Gray Theme',
            'class': 'light',
            'active': current_theme_color == 'app-theme-gray'
        },
    ]
    
    # Tab style options
    tab_style_options = [
        {
            'value': 'body-tabs-shadow',
            'label': 'Shadow',
            'active': current_tab_style == 'body-tabs-shadow'
        },
        {
            'value': 'body-tabs-line',
            'label': 'Line',
            'active': current_tab_style == 'body-tabs-line'
        },
    ]
    
    # Helper function to get text class for a color
    def get_text_class(color_key):
        return COLOR_SCHEMES.get(color_key, {}).get('text', 'light')
    
    return {
        'color_schemes': COLOR_SCHEMES,
        'basic_colors': basic_colors,
        'gradient_colors': gradient_colors,
        'all_colors': basic_colors + gradient_colors,
        'theme_options': theme_options,
        'tab_style_options': tab_style_options,
        'get_text_class': get_text_class,  # Helper for templates
        'current_theme_color': current_theme_color,
        'current_tab_style': current_tab_style,
    }


def user_security_context(request):
    """
    Provides security-related context for the user.
    
    This includes account security status, password expiry information,
    and two-factor authentication status.
    
    Context variables:
        - account_locked: Boolean if account is locked
        - password_expired: Boolean if password has expired
        - password_expiring_soon: Boolean if password expires within 7 days
        - days_until_password_expiry: Days until password expires
        - two_factor_enabled: Boolean for 2FA status
        - force_password_change: Boolean if password change required
    """
    context = {
        'account_locked': False,
        'password_expired': False,
        'password_expiring_soon': False,
        'days_until_password_expiry': None,
        'two_factor_enabled': False,
        'force_password_change': False,
        'last_activity': None,
    }
    
    if request.user.is_authenticated:
        try:
            profile = getattr(request.user, 'profile', None)
            if profile:
                # Account lock status
                context['account_locked'] = profile.is_account_locked
                
                # Two-factor authentication
                context['two_factor_enabled'] = profile.two_factor_enabled
                
                # Force password change
                context['force_password_change'] = profile.force_password_change
                
                # Last activity
                context['last_activity'] = profile.last_activity
                
                # Password expiry (requires password_changed_at and settings)
                if profile.password_changed_at:
                    from django.utils import timezone
                    from datetime import timedelta
                    
                    try:
                        from accounts.models import UserManagementSettings
                        settings = UserManagementSettings.get_instance()
                        
                        password_age_days = (timezone.now() - profile.password_changed_at).days
                        expiry_days = settings.password_expiry_days
                        days_until_expiry = expiry_days - password_age_days
                        
                        context['days_until_password_expiry'] = days_until_expiry
                        context['password_expired'] = days_until_expiry <= 0
                        context['password_expiring_soon'] = 0 < days_until_expiry <= 7
                        
                    except:
                        pass
                        
        except Exception as e:
            logger.error(f"Error loading security context: {e}")
    
    return context


def navigation_permissions(request):
    """
    Provides navigation-specific permission flags.
    
    This helps control which navigation items are visible based on
    user permissions and role.
    
    Context variables:
        - show_admin_menu: Boolean for admin menu visibility
        - show_finance_menu: Boolean for finance menu
        - show_academics_menu: Boolean for academics menu
        - show_hr_menu: Boolean for HR menu
        - show_students_menu: Boolean for students menu
        - show_inventory_menu: Boolean for inventory menu
        - show_reports_menu: Boolean for reports menu
    """
    context = {
        'show_admin_menu': False,
        'show_finance_menu': False,
        'show_academics_menu': False,
        'show_hr_menu': False,
        'show_students_menu': False,
        'show_inventory_menu': False,
        'show_reports_menu': False,
        'show_settings_menu': False,
    }
    
    if request.user.is_authenticated:
        try:
            profile = getattr(request.user, 'profile', None)
            if profile:
                # Admin menu - for administrators and super admins
                context['show_admin_menu'] = profile.is_admin_user() or request.user.is_superuser
                
                # Finance menu - for users with finance permissions
                context['show_finance_menu'] = (
                    profile.can_manage_finances() or 
                    profile.can_view_financial_data or
                    request.user.is_superuser
                )
                
                # Academics menu - for teachers and academic staff
                context['show_academics_menu'] = (
                    profile.can_manage_academics() or 
                    profile.can_view_academic_data or
                    profile.is_teacher() or
                    request.user.is_superuser
                )
                
                # HR menu - for HR managers and admins
                context['show_hr_menu'] = (
                    profile.can_manage_hr() or 
                    profile.can_view_hr_data or
                    request.user.is_superuser
                )
                
                # Students menu - for registrars and academic staff
                context['show_students_menu'] = (
                    profile.can_manage_students() or 
                    profile.can_view_student_data or
                    request.user.is_superuser
                )
                
                # Inventory menu - for inventory managers
                context['show_inventory_menu'] = (
                    profile.can_manage_inventory() or 
                    profile.can_view_inventory_data or
                    request.user.is_superuser
                )
                
                # Reports menu - for senior staff and those with view permissions
                context['show_reports_menu'] = (
                    profile.is_senior_staff() or
                    profile.can_view_financial_data or
                    profile.can_view_academic_data or
                    request.user.is_superuser
                )
                
                # Settings menu - for admins
                context['show_settings_menu'] = (
                    profile.is_admin_user() or 
                    request.user.is_superuser
                )
                
        except Exception as e:
            logger.error(f"Error loading navigation permissions: {e}")
    
    return context


def user_notifications_count(request):
    """
    Provides counts for user notifications and pending items.
    
    This is used for notification badges in the navigation.
    
    Context variables:
        - unread_notifications_count: Count of unread notifications
        - pending_tasks_count: Count of pending tasks
        - pending_approvals_count: Count of items needing approval
    """
    context = {
        'unread_notifications_count': 0,
        'pending_tasks_count': 0,
        'pending_approvals_count': 0,
    }
    
    if request.user.is_authenticated:
        try:
            # Try to get notification counts if notification system exists
            # This is a placeholder - implement based on your notification system
            pass
            
        except Exception as e:
            logger.error(f"Error loading notification counts: {e}")
    
    return context