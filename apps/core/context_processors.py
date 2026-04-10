# core/context_processors.py

"""
Context processors for School Management System.
Provides global data that needs to be available in all templates.

Consolidates both core and accounts context processors into a single module.

Usage:
    Add to settings.py TEMPLATES context_processors list:
        'core.context_processors.school_branding',
        'core.context_processors.user_preferences',
        'core.context_processors.theme_colors',
        'core.context_processors.navigation_permissions',
        'core.context_processors.user_security_context',
        'core.context_processors.school_configuration',
        'core.context_processors.active_academic_session',
        'core.context_processors.active_fiscal_period',
        'core.context_processors.payment_methods_context',

DESIGN NOTES
------------
- PaymentMethod lives in core.models, not finance.models.
- active_fiscal_period does not call get_school_today() directly; fiscal
  year and period instance methods call it internally.
- active_academic_session session properties (progress_percentage,
  days_remaining, etc.) currently use timezone.now().date() inside
  AcademicSession because academics/models.py has not yet been updated to
  call get_school_today(). Once that update is made the values here will
  automatically use school timezone.
- school_configuration uses SchoolConfiguration.get_cached_instance() which
  uses the class-level cache implemented in core/models.py.
"""

from django.utils import timezone
from core.models import (
    SchoolConfiguration,
    FinancialSettings,
    FiscalYear,
    FiscalPeriod,
    PaymentMethod,
)
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# SCHOOL BRANDING CONTEXT
# =============================================================================

def school_branding(request):
    """
    Provides school branding data for header, sidebar, and page titles.

    Available in all templates:
    - active_school:        Full School instance
    - school_name:          Full school name (e.g., 'Kampala High School')
    - school_short_name:    Short/abbreviated name (e.g., 'KHS')
    - school_logo_url:      URL to school logo image or None
    - school_favicon_url:   URL to school favicon image or None
    - school_motto:         School motto/slogan
    - school_type:          Human-readable school type
    - school_abbreviation:  School acronym
    - school_brand_colors:  Dict with 'primary', 'secondary', 'accent' hex values
    - school_contact_email: General contact email
    - school_contact_phone: Primary phone number
    - school_website:       School website URL
    - school_address:       Physical address

    Example:
        <title>{{ school_name|default:"Schoolara" }}</title>
        {% if school_logo_url %}
            <img src="{{ school_logo_url }}" alt="{{ school_name }}">
        {% endif %}
    """
    context = {
        'active_school':        None,
        'school_name':          'School',
        'school_short_name':    None,
        'school_logo_url':      None,
        'school_favicon_url':   None,
        'school_motto':         None,
        'school_type':          None,
        'school_abbreviation':  None,
        'school_brand_colors':  {},
        'school_contact_email': None,
        'school_contact_phone': None,
        'school_website':       None,
        'school_address':       None,
    }

    try:
        from accounts.models import School

        # Prefer the school attached to the authenticated user's profile for
        # accuracy in multi-school deployments; fall back to first active school.
        school = None

        if request.user.is_authenticated:
            profile = getattr(request.user, 'profile', None)
            if profile and getattr(profile, 'school', None):
                school = profile.school

        if not school:
            school = School.objects.filter(is_active_subscription=True).first()

        if school:
            context['active_school']        = school
            context['school_name']          = school.full_name
            context['school_short_name']    = (
                school.short_name
                or school.abbreviation
                or school.full_name
            )
            context['school_motto']         = school.school_motto
            context['school_type']          = school.get_school_type_display()
            context['school_abbreviation']  = school.abbreviation
            context['school_brand_colors']  = school.brand_colors or {}
            context['school_contact_email'] = school.contact_email
            context['school_contact_phone'] = school.contact_phone
            context['school_website']       = school.website
            context['school_address']       = school.address

            if school.school_logo:
                try:
                    context['school_logo_url'] = school.school_logo.url
                except Exception:
                    pass

            if school.favicon:
                try:
                    context['school_favicon_url'] = school.favicon.url
                except Exception:
                    pass

    except Exception as e:
        logger.error(f"Error loading school branding: {e}")

    return context


# =============================================================================
# USER PREFERENCES CONTEXT
# =============================================================================

def user_preferences(request):
    """
    Provides the authenticated user's profile, theme preferences, and role info.
    Returns safe defaults for unauthenticated users.

    Available in all templates:
    - user_full_name:           Display name
    - user_first_name:          First name
    - user_last_name:           Last name
    - user_email:               Email address
    - user_role:                Raw role code (e.g., 'ADMINISTRATOR')
    - user_role_display:        Human-readable role label
    - user_profile:             Full UserProfile instance
    - user_school:              School instance the user belongs to
    - user_school_name:         School display name string
    - user_profile_pic:         URL to profile photo or None
    - user_employee_id:         Staff ID
    - user_department:          Department name
    - user_position:            Job title
    - theme_color:              CSS class (e.g., 'app-theme-white')
    - header_class:             CSS class for header colour scheme
    - sidebar_class:            CSS class for sidebar colour scheme
    - page_tabs_style:          CSS class for tab style
    - fixed_header:             Boolean
    - fixed_sidebar:            Boolean
    - fixed_footer:             Boolean
    - preferred_language:       Language code
    - preferred_timezone:       Timezone string
    - email_notifications:      Boolean
    - sms_notifications:        Boolean
    - is_admin:                 Boolean shortcut
    - is_teacher:               Boolean shortcut
    - is_senior_staff:          Boolean shortcut
    - can_manage_*:             Permission booleans

    Example:
        <div class="app-container {{ theme_color }}
            {% if fixed_header %}fixed-header{% endif %}
            {% if fixed_sidebar %}fixed-sidebar{% endif %}
            {% if fixed_footer %}fixed-footer{% endif %}
            {{ page_tabs_style }}">
    """
    context = {
        # User info
        'user_full_name':       '',
        'user_first_name':      '',
        'user_last_name':       '',
        'user_email':           '',
        'user_role':            None,
        'user_role_display':    '',
        'user_profile':         None,
        'user_school':          None,
        'user_school_name':     '',
        'user_profile_pic':     None,
        'user_employee_id':     '',
        'user_department':      '',
        'user_position':        '',
        # Theme defaults — match UserProfile field defaults
        'theme_color':          'app-theme-white',
        'header_class':         '',
        'sidebar_class':        '',
        'page_tabs_style':      'body-tabs-shadow',
        'fixed_header':         False,
        'fixed_sidebar':        False,
        'fixed_footer':         False,
        # Localisation
        'preferred_language':   'en',
        'preferred_timezone':   'Africa/Kampala',
        # Notifications
        'email_notifications':  True,
        'sms_notifications':    False,
        # Permission shortcuts
        'is_admin':             False,
        'is_teacher':           False,
        'is_senior_staff':      False,
        'can_manage_users':     False,
        'can_manage_finances':  False,
        'can_manage_academics': False,
        'can_manage_students':  False,
        'can_manage_hr':        False,
        'can_manage_inventory': False,
    }

    if not request.user.is_authenticated:
        return context

    try:
        from accounts.models import UserProfile

        profile = (
            UserProfile.objects
            .select_related('user', 'school')
            .get(user=request.user)
        )

        # Basic user info
        context['user_first_name'] = request.user.first_name or ''
        context['user_last_name']  = request.user.last_name  or ''
        context['user_email']      = request.user.email or request.user.username

        full_name = request.user.get_full_name().strip()
        if not full_name:
            username = request.user.username
            if '@' in username:
                full_name = (
                    username.split('@')[0]
                    .replace('.', ' ')
                    .replace('_', ' ')
                    .title()
                )
            else:
                full_name = username
        context['user_full_name'] = full_name

        # Profile info
        context['user_profile']     = profile
        context['user_role']        = profile.role
        context['user_role_display']= profile.get_role_display()
        context['user_employee_id'] = profile.employee_id or ''
        context['user_department']  = profile.department  or ''
        context['user_position']    = profile.position    or ''

        if profile.school:
            context['user_school']      = profile.school
            context['user_school_name'] = profile.school.display_name

        if profile.photo:
            try:
                context['user_profile_pic'] = profile.photo.url
            except Exception:
                pass

        # Theme preferences
        context['theme_color']      = profile.theme_color      or 'app-theme-white'
        context['header_class']     = profile.header_class      or ''
        context['sidebar_class']    = profile.sidebar_class     or ''
        context['page_tabs_style']  = profile.page_tabs_style   or 'body-tabs-shadow'
        context['fixed_header']     = profile.fixed_header
        context['fixed_sidebar']    = profile.fixed_sidebar
        context['fixed_footer']     = profile.fixed_footer

        # Localisation
        context['preferred_language'] = profile.language or 'en'
        context['preferred_timezone'] = profile.timezone or 'Africa/Kampala'

        # Notification preferences
        context['email_notifications'] = profile.email_notifications
        context['sms_notifications']   = profile.sms_notifications

        # Permission shortcuts
        context['is_admin']             = profile.is_admin_user()
        context['is_teacher']           = profile.is_teacher()
        context['is_senior_staff']      = profile.is_senior_staff()
        context['can_manage_users']     = profile.can_manage_users()
        context['can_manage_finances']  = profile.can_manage_finances()
        context['can_manage_academics'] = profile.can_manage_academics()
        context['can_manage_students']  = profile.can_manage_students()
        context['can_manage_hr']        = profile.can_manage_hr()
        context['can_manage_inventory'] = profile.can_manage_inventory()

    except Exception as e:
        if 'DoesNotExist' in type(e).__name__:
            logger.warning(
                f"No UserProfile found for user: {request.user.username}"
            )
        else:
            logger.error(f"Error loading user preferences: {e}")

    return context


# =============================================================================
# THEME COLORS CONTEXT
# =============================================================================

def theme_colors(request):
    """
    Provides comprehensive theme colour configuration for templates.
    Used primarily by the theme settings panel.

    Available in all templates:
    - color_schemes:         Dict of all available colours with metadata
    - basic_colors:          List of standard Bootstrap colour dicts
    - gradient_colors:       List of gradient/premium colour dicts
    - all_colors:            Combined list
    - theme_options:         Available app theme options with active state
    - tab_style_options:     Available tab styles with active state
    - current_theme_color:   Currently selected theme
    - current_tab_style:     Currently selected tab style

    Each colour dict contains:
        { 'key', 'label', 'text_class', 'bg_class', 'full_class' }
    """

    COLOR_SCHEMES = {
        # Bootstrap base colours
        'primary':   {'label': 'Primary Blue',   'text': 'light'},
        'secondary': {'label': 'Secondary Gray',  'text': 'light'},
        'success':   {'label': 'Success Green',   'text': 'light'},
        'info':      {'label': 'Info Cyan',       'text': 'light'},
        'warning':   {'label': 'Warning Yellow',  'text': 'dark'},
        'danger':    {'label': 'Danger Red',      'text': 'light'},
        'light':     {'label': 'Light',           'text': 'dark'},
        'dark':      {'label': 'Dark',            'text': 'light'},
        'focus':     {'label': 'Focus Purple',    'text': 'light'},
        'alternate': {'label': 'Alternate',       'text': 'light'},
        # Gradient / premium
        'vicious-stance':  {'label': 'Vicious Stance',  'text': 'light'},
        'midnight-bloom':  {'label': 'Midnight Bloom',  'text': 'light'},
        'night-sky':       {'label': 'Night Sky',       'text': 'light'},
        'slick-carbon':    {'label': 'Slick Carbon',    'text': 'light'},
        'asteroid':        {'label': 'Asteroid',        'text': 'light'},
        'royal':           {'label': 'Royal',           'text': 'light'},
        'warm-flame':      {'label': 'Warm Flame',      'text': 'dark'},
        'night-fade':      {'label': 'Night Fade',      'text': 'dark'},
        'sunny-morning':   {'label': 'Sunny Morning',   'text': 'dark'},
        'tempting-azure':  {'label': 'Tempting Azure',  'text': 'dark'},
        'amy-crisp':       {'label': 'Amy Crisp',       'text': 'dark'},
        'heavy-rain':      {'label': 'Heavy Rain',      'text': 'dark'},
        'mean-fruit':      {'label': 'Mean Fruit',      'text': 'dark'},
        'malibu-beach':    {'label': 'Malibu Beach',    'text': 'light'},
        'deep-blue':       {'label': 'Deep Blue',       'text': 'dark'},
        'ripe-malin':      {'label': 'Ripe Malin',      'text': 'light'},
        'arielle-smile':   {'label': 'Arielle Smile',   'text': 'light'},
        'plum-plate':      {'label': 'Plum Plate',      'text': 'light'},
        'happy-fisher':    {'label': 'Happy Fisher',    'text': 'dark'},
        'happy-itmeo':     {'label': 'Happy Itmeo',     'text': 'light'},
        'mixed-hopes':     {'label': 'Mixed Hopes',     'text': 'light'},
        'strong-bliss':    {'label': 'Strong Bliss',    'text': 'light'},
        'grow-early':      {'label': 'Grow Early',      'text': 'light'},
        'love-kiss':       {'label': 'Love Kiss',       'text': 'light'},
        'premium-dark':    {'label': 'Premium Dark',    'text': 'light'},
        'happy-green':     {'label': 'Happy Green',     'text': 'light'},
    }

    BASIC_KEYS = [
        'primary', 'secondary', 'success', 'info',
        'warning', 'danger', 'light', 'dark', 'focus', 'alternate',
    ]

    def _build_color(key):
        scheme = COLOR_SCHEMES[key]
        return {
            'key':        key,
            'label':      scheme['label'],
            'text_class': scheme['text'],
            'bg_class':   f'bg-{key}',
            'full_class': f"bg-{key} header-text-{scheme['text']}",
        }

    basic_colors    = [_build_color(k) for k in BASIC_KEYS]
    gradient_colors = [
        _build_color(k) for k in COLOR_SCHEMES if k not in BASIC_KEYS
    ]

    # Resolve current selections from profile if available
    current_theme_color = 'app-theme-white'
    current_tab_style   = 'body-tabs-shadow'

    if request.user.is_authenticated:
        profile = getattr(request.user, 'profile', None)
        if profile:
            current_theme_color = getattr(profile, 'theme_color',     'app-theme-white') or 'app-theme-white'
            current_tab_style   = getattr(profile, 'page_tabs_style', 'body-tabs-shadow') or 'body-tabs-shadow'

    theme_options = [
        {
            'value':  'app-theme-white',
            'label':  'White Theme',
            'active': current_theme_color == 'app-theme-white',
        },
        {
            'value':  'app-theme-gray',
            'label':  'Gray Theme',
            'active': current_theme_color == 'app-theme-gray',
        },
    ]

    tab_style_options = [
        {
            'value':  'body-tabs-shadow',
            'label':  'Shadow',
            'active': current_tab_style == 'body-tabs-shadow',
        },
        {
            'value':  'body-tabs-line',
            'label':  'Line',
            'active': current_tab_style == 'body-tabs-line',
        },
    ]

    return {
        'color_schemes':       COLOR_SCHEMES,
        'basic_colors':        basic_colors,
        'gradient_colors':     gradient_colors,
        'all_colors':          basic_colors + gradient_colors,
        'theme_options':       theme_options,
        'tab_style_options':   tab_style_options,
        'current_theme_color': current_theme_color,
        'current_tab_style':   current_tab_style,
    }


# =============================================================================
# USER SECURITY CONTEXT
# =============================================================================

def user_security_context(request):
    """
    Provides security-related context for the authenticated user.
    Used to show password expiry warnings, lock notices, and 2FA prompts.

    Available in all templates:
    - account_locked:              Boolean — account is currently locked
    - password_expired:            Boolean — password has expired
    - password_expiring_soon:      Boolean — expires within 7 days
    - days_until_password_expiry:  Integer or None
    - two_factor_enabled:          Boolean
    - force_password_change:       Boolean — must change on next login
    - last_activity:               Datetime of last user action

    Example:
        {% if force_password_change %}
            <div class="alert alert-warning">
                Please change your password before continuing.
            </div>
        {% endif %}
        {% if password_expiring_soon %}
            <div class="alert alert-info">
                Your password expires in {{ days_until_password_expiry }} day(s).
            </div>
        {% endif %}
    """
    context = {
        'account_locked':             False,
        'password_expired':           False,
        'password_expiring_soon':     False,
        'days_until_password_expiry': None,
        'two_factor_enabled':         False,
        'force_password_change':      False,
        'last_activity':              None,
    }

    if not request.user.is_authenticated:
        return context

    try:
        profile = getattr(request.user, 'profile', None)
        if not profile:
            return context

        context['account_locked']        = profile.is_account_locked
        context['two_factor_enabled']    = profile.two_factor_enabled
        context['force_password_change'] = profile.force_password_change
        context['last_activity']         = profile.last_activity

        if profile.password_changed_at:
            try:
                from accounts.models import UserManagementSettings

                mgmt              = UserManagementSettings.get_instance()
                password_age_days = (
                    timezone.now() - profile.password_changed_at
                ).days
                days_until_expiry = mgmt.password_expiry_days - password_age_days

                context['days_until_password_expiry'] = days_until_expiry
                context['password_expired']           = days_until_expiry <= 0
                context['password_expiring_soon']     = 0 < days_until_expiry <= 7

            except Exception:
                pass

    except Exception as e:
        logger.error(f"Error loading security context: {e}")

    return context


# =============================================================================
# NAVIGATION PERMISSIONS CONTEXT
# =============================================================================

def navigation_permissions(request):
    """
    Provides navigation visibility flags and notification badge counts.
    Controls which sidebar sections are rendered for the current user.

    Available in all templates:
    - show_admin_menu:              Boolean
    - show_finance_menu:            Boolean
    - show_academics_menu:          Boolean
    - show_hr_menu:                 Boolean
    - show_students_menu:           Boolean
    - show_inventory_menu:          Boolean
    - show_reports_menu:            Boolean
    - show_settings_menu:           Boolean
    - unread_notifications_count:   Integer badge count
    - pending_tasks_count:          Integer badge count
    - pending_approvals_count:      Integer badge count

    Example:
        {% if show_finance_menu %}
            <li>...</li>
        {% endif %}
    """
    context = {
        'show_admin_menu':            False,
        'show_finance_menu':          False,
        'show_academics_menu':        False,
        'show_hr_menu':               False,
        'show_students_menu':         False,
        'show_inventory_menu':        False,
        'show_reports_menu':          False,
        'show_settings_menu':         False,
        'unread_notifications_count': 0,
        'pending_tasks_count':        0,
        'pending_approvals_count':    0,
    }

    if not request.user.is_authenticated:
        return context

    try:
        profile  = getattr(request.user, 'profile', None)
        if not profile:
            return context

        is_super = request.user.is_superuser

        context['show_admin_menu'] = profile.is_admin_user() or is_super

        context['show_finance_menu'] = (
            profile.can_manage_finances()
            or getattr(profile, 'can_view_financial_data', False)
            or is_super
        )

        context['show_academics_menu'] = (
            profile.can_manage_academics()
            or getattr(profile, 'can_view_academic_data', False)
            or profile.is_teacher()
            or is_super
        )

        context['show_hr_menu'] = (
            profile.can_manage_hr()
            or getattr(profile, 'can_view_hr_data', False)
            or is_super
        )

        context['show_students_menu'] = (
            profile.can_manage_students()
            or getattr(profile, 'can_view_student_data', False)
            or is_super
        )

        context['show_inventory_menu'] = (
            profile.can_manage_inventory()
            or getattr(profile, 'can_view_inventory_data', False)
            or is_super
        )

        context['show_reports_menu'] = (
            profile.is_senior_staff()
            or getattr(profile, 'can_view_financial_data', False)
            or getattr(profile, 'can_view_academic_data',  False)
            or is_super
        )

        context['show_settings_menu'] = profile.is_admin_user() or is_super

        # Extend here when a notification model is available:
        # context['unread_notifications_count'] = (
        #     Notification.objects.filter(
        #         user=request.user, is_read=False
        #     ).count()
        # )

    except Exception as e:
        logger.error(f"Error loading navigation permissions: {e}")

    return context


# =============================================================================
# SCHOOL CONFIGURATION CONTEXT
# =============================================================================

def school_configuration(request):
    """
    Provides school configuration and financial settings context.

    Uses SchoolConfiguration.get_cached_instance() — the class-level cache
    implemented in core/models.py — so this processor does not hit the
    database on every request once the cache is warm.

    Available in all templates:
    - school_config:                 Full SchoolConfiguration object
    - term_system:                   'term', 'semester', 'quarter', etc.
    - periods_per_year:              Number of periods per year
    - period_type_name:              'Term', 'Semester', etc.
    - period_type_name_plural:       'Terms', 'Semesters', etc.
    - period_naming_convention:      'numeric', 'ordinal', 'seasonal', etc.
    - academic_year_type:            'northern', 'southern', 'east_africa', etc.
    - academic_year_start_month:     Integer 1–12
    - operational_timezone:          School's operational timezone string
    - regional_season_type:          Regional season scheme
    - default_period_duration_weeks: Integer weeks
    - enable_automatic_reminders:    Boolean
    - enable_sms:                    Boolean
    - enable_email_notifications:    Boolean
    - school_currency:               Currency code (e.g., 'UGX')
    - currency_position:             'BEFORE', 'AFTER', etc.
    - decimal_places:                Integer

    Example:
        <p>{{ periods_per_year }} {{ period_type_name_plural }} per year</p>
        <p>Currency: {{ school_currency }}</p>
    """
    context = {
        'school_config':                 None,
        'term_system':                   'term',
        'periods_per_year':              3,
        'period_type_name':              'Term',
        'period_type_name_plural':       'Terms',
        'period_naming_convention':      'numeric',
        'academic_year_type':            'east_africa',
        'academic_year_start_month':     2,
        'operational_timezone':          'Africa/Kampala',
        'regional_season_type':          'equatorial',
        'default_period_duration_weeks': 13,
        'enable_automatic_reminders':    True,
        'enable_sms':                    False,
        'enable_email_notifications':    True,
        'school_currency':               'UGX',
        'currency_position':             'BEFORE',
        'decimal_places':                2,
    }

    try:
        # get_cached_instance() uses the class-level cache on SchoolConfiguration.
        # Cache is invalidated automatically whenever SchoolConfiguration.save()
        # is called, so this is safe to call on every request.
        config = SchoolConfiguration.get_cached_instance()

        if config:
            context['school_config']                 = config
            context['term_system']                   = config.term_system
            context['periods_per_year']              = config.get_period_count()
            context['period_type_name']              = config.get_period_type_name()
            context['period_type_name_plural']       = config.get_period_type_name_plural()
            context['period_naming_convention']      = config.period_naming_convention
            context['academic_year_type']            = config.academic_year_type
            context['academic_year_start_month']     = config.academic_year_start_month
            context['operational_timezone']          = config.operational_timezone
            context['regional_season_type']          = config.regional_season_type
            context['default_period_duration_weeks'] = config.default_period_duration_weeks
            context['enable_automatic_reminders']    = config.enable_automatic_reminders
            context['enable_sms']                    = config.enable_sms
            context['enable_email_notifications']    = config.enable_email_notifications

        fin_settings = FinancialSettings.get_instance()
        if fin_settings:
            context['school_currency']   = fin_settings.school_currency
            context['currency_position'] = fin_settings.currency_position
            context['decimal_places']    = fin_settings.decimal_places

    except Exception as e:
        logger.error(f"Error loading school configuration: {e}")

    return context


# =============================================================================
# ACTIVE ACADEMIC SESSION CONTEXT
# =============================================================================

def active_academic_session(request):
    """
    Provides active academic session context for teaching/learning activities.

    Uses get_school_today() from core.utils for the 'today' value so
    templates use the school's configured timezone.

    NOTE ON SESSION PROPERTIES:
    session.progress_percentage, session.days_remaining, session.days_elapsed,
    and session.total_days currently call timezone.now().date() internally
    inside AcademicSession (academics/models.py has not yet been updated to
    use get_school_today()). These values will automatically use school
    timezone once that update is made.

    Available in all templates:
    - today:                         date (school timezone)
    - current_session:               AcademicSession object or None
    - session_name:                  e.g., '2024 - Term 1'
    - session_year:                  e.g., '2024'
    - session_term:                  e.g., 'Term 1'
    - session_type:                  period_type code
    - session_number:                term_number integer
    - session_is_special:            Boolean
    - session_start_date:            date
    - session_end_date:              date
    - session_progress:              0–100 float
    - session_days_remaining:        Integer
    - session_days_elapsed:          Integer
    - session_total_days:            Integer
    - session_status:                Human-readable status string
    - session_ending_soon:           Boolean (≤14 days remaining)
    - session_is_enrollment_open:    Boolean
    - session_allows_promotion:      Boolean
    - session_promotion_done:        Boolean
    - session_is_academically_closed: Boolean
    - enrollment_sessions:           Queryset open for enrollment
    - enrollment_sessions_count:     Integer
    """
    from core.utils import get_school_today

    today = get_school_today()

    context = {
        'today':                          today,
        'current_session':                None,
        'session_name':                   None,
        'session_year':                   None,
        'session_term':                   None,
        'session_type':                   None,
        'session_number':                 None,
        'session_is_special':             False,
        'session_start_date':             None,
        'session_end_date':               None,
        'session_progress':               0,
        'session_days_remaining':         0,
        'session_days_elapsed':           0,
        'session_total_days':             0,
        'session_status':                 None,
        'session_ending_soon':            False,
        'session_is_enrollment_open':     False,
        'session_allows_promotion':       False,
        'session_promotion_done':         False,
        'session_is_academically_closed': False,
        'enrollment_sessions':            [],
        'enrollment_sessions_count':      0,
    }

    try:
        from academics.models import AcademicSession

        session = AcademicSession.get_current_session()

        if session:
            context['current_session']                = session
            context['session_name']                   = session.name
            context['session_year']                   = session.year_name
            context['session_term']                   = session.term_name
            context['session_type']                   = session.period_type
            context['session_number']                 = session.term_number
            context['session_is_special']             = session.is_special_session
            context['session_start_date']             = session.start_date
            context['session_end_date']               = session.end_date
            context['session_status']                 = session.status_display
            context['session_is_enrollment_open']     = session.is_enrollment_open
            context['session_allows_promotion']       = session.allows_promotion
            context['session_promotion_done']         = session.promotion_done
            context['session_is_academically_closed'] = session.is_academically_closed

            # NOTE: These properties use timezone.now().date() internally until
            # academics/models.py is updated to call get_school_today().
            context['session_progress']       = session.progress_percentage
            context['session_days_remaining'] = session.days_remaining
            context['session_days_elapsed']   = session.days_elapsed
            context['session_total_days']     = session.total_days

            if 0 < session.days_remaining <= 14:
                context['session_ending_soon'] = True

        enrollment_sessions = AcademicSession.get_open_for_enrollment()
        context['enrollment_sessions']       = enrollment_sessions
        context['enrollment_sessions_count'] = enrollment_sessions.count()

    except Exception as e:
        logger.error(f"Error loading active academic session: {e}")

    return context


# =============================================================================
# ACTIVE FISCAL PERIOD CONTEXT
# =============================================================================

def active_fiscal_period(request):
    """
    Provides active fiscal year and period context for financial operations.

    Fiscal year and period instance methods (get_progress_percentage,
    get_remaining_days, can_accept_transactions, etc.) call get_school_today()
    internally, so school timezone is applied automatically — no need to call
    get_school_today() directly in this processor.

    'today' is already provided by active_academic_session for templates
    that need it.

    Available in all templates:
    - active_fiscal_year:              FiscalYear object or None
    - active_fiscal_period:            FiscalPeriod object or None
    - fiscal_year_name:                e.g., '2024'
    - fiscal_year_code:                e.g., 'FY2024'
    - fiscal_year_start_date:          date
    - fiscal_year_end_date:            date
    - fiscal_year_progress:            0–100 float
    - fiscal_year_status:              'DRAFT'|'ACTIVE'|'CLOSED'|'LOCKED'
    - fiscal_year_is_closed:           Boolean
    - fiscal_year_is_locked:           Boolean
    - fiscal_year_remaining_days:      Integer
    - fiscal_year_elapsed_days:        Integer
    - fiscal_year_period_count:        Integer
    - fiscal_year_ending_soon:         Boolean (≤90 days)
    - days_until_fy_end:               Integer or None
    - fiscal_period_name:              e.g., 'Term 1 2024 Fiscal Period'
    - fiscal_period_number:            Decimal
    - fiscal_period_type:              period_type code
    - fiscal_period_start_date:        date
    - fiscal_period_end_date:          date
    - fiscal_period_progress:          0–100 float
    - fiscal_period_status:            'DRAFT'|'ACTIVE'|'CLOSED'|'LOCKED'
    - fiscal_period_is_closed:         Boolean
    - fiscal_period_is_locked:         Boolean
    - fiscal_period_remaining_days:    Integer
    - fiscal_period_elapsed_days:      Integer
    - fiscal_period_ending_soon:       Boolean (≤14 days)
    - days_until_period_end:           Integer or None
    - fiscal_period_in_grace:          Boolean
    - fiscal_period_grace_days:        Integer
    - fiscal_period_academic_session:  AcademicSession or None
    - can_accept_transactions:         Boolean
    - can_generate_invoices:           Boolean
    - can_process_refunds:             Boolean
    - can_accept_advance_payments:     Boolean
    - can_accept_arrears_payments:     Boolean
    """
    context = {
        # Fiscal year
        'active_fiscal_year':          None,
        'fiscal_year_name':            None,
        'fiscal_year_code':            None,
        'fiscal_year_start_date':      None,
        'fiscal_year_end_date':        None,
        'fiscal_year_progress':        0,
        'fiscal_year_status':          None,
        'fiscal_year_is_closed':       False,
        'fiscal_year_is_locked':       False,
        'fiscal_year_remaining_days':  None,
        'fiscal_year_elapsed_days':    None,
        'fiscal_year_period_count':    0,
        'fiscal_year_ending_soon':     False,
        'days_until_fy_end':           None,
        # Fiscal period
        'active_fiscal_period':        None,
        'fiscal_period_name':          None,
        'fiscal_period_number':        None,
        'fiscal_period_type':          None,
        'fiscal_period_start_date':    None,
        'fiscal_period_end_date':      None,
        'fiscal_period_progress':      0,
        'fiscal_period_status':        None,
        'fiscal_period_is_closed':     False,
        'fiscal_period_is_locked':     False,
        'fiscal_period_remaining_days': None,
        'fiscal_period_elapsed_days':  None,
        'fiscal_period_ending_soon':   False,
        'days_until_period_end':       None,
        'fiscal_period_in_grace':      False,
        'fiscal_period_grace_days':    0,
        'fiscal_period_academic_session': None,
        # Transaction permissions
        'can_accept_transactions':      False,
        'can_generate_invoices':        False,
        'can_process_refunds':          False,
        'can_accept_advance_payments':  False,
        'can_accept_arrears_payments':  False,
    }

    try:
        fiscal_year = FiscalYear.get_active_fiscal_year()

        if fiscal_year:
            days_until_fy_end = fiscal_year.get_remaining_days()

            context['active_fiscal_year']         = fiscal_year
            context['fiscal_year_name']           = fiscal_year.name
            context['fiscal_year_code']           = fiscal_year.code
            context['fiscal_year_start_date']     = fiscal_year.start_date
            context['fiscal_year_end_date']       = fiscal_year.end_date
            context['fiscal_year_progress']       = fiscal_year.get_progress_percentage()
            context['fiscal_year_status']         = fiscal_year.status
            context['fiscal_year_is_closed']      = fiscal_year.is_closed
            context['fiscal_year_is_locked']      = fiscal_year.is_locked
            context['fiscal_year_remaining_days'] = days_until_fy_end
            context['fiscal_year_elapsed_days']   = fiscal_year.get_elapsed_days()
            context['fiscal_year_period_count']   = fiscal_year.get_period_count()
            context['days_until_fy_end']          = days_until_fy_end

            if 0 < days_until_fy_end <= 90:
                context['fiscal_year_ending_soon'] = True

    except Exception as e:
        logger.error(f"Error loading active fiscal year: {e}")

    try:
        period = FiscalPeriod.get_current_fiscal_period()

        if period:
            days_until_period_end = period.get_remaining_days()

            context['active_fiscal_period']          = period
            context['fiscal_period_name']            = period.name
            context['fiscal_period_number']          = period.period_number
            context['fiscal_period_type']            = period.period_type
            context['fiscal_period_start_date']      = period.start_date
            context['fiscal_period_end_date']        = period.end_date
            context['fiscal_period_progress']        = period.get_progress_percentage()
            context['fiscal_period_status']          = period.status
            context['fiscal_period_is_closed']       = period.is_closed
            context['fiscal_period_is_locked']       = period.is_locked
            context['fiscal_period_remaining_days']  = days_until_period_end
            context['fiscal_period_elapsed_days']    = period.get_elapsed_days()
            context['days_until_period_end']         = days_until_period_end
            context['fiscal_period_in_grace']        = period.is_in_grace_period()
            context['fiscal_period_grace_days']      = period.grace_period_days

            context['can_accept_transactions']     = period.can_accept_transactions()
            context['can_generate_invoices']       = period.can_generate_invoices()
            context['can_process_refunds']         = period.can_process_refunds()
            context['can_accept_advance_payments'] = period.can_accept_advance_payment()
            context['can_accept_arrears_payments'] = period.can_accept_arrears_payment()

            if 0 < days_until_period_end <= 14:
                context['fiscal_period_ending_soon'] = True

            if period.related_academic_session:
                context['fiscal_period_academic_session'] = (
                    period.related_academic_session
                )

    except Exception as e:
        logger.error(f"Error loading active fiscal period: {e}")

    return context


# =============================================================================
# PAYMENT METHODS CONTEXT
# =============================================================================

def payment_methods_context(request):
    """
    Provides available payment methods for dropdowns and forms.

    PaymentMethod is defined in core.models (not finance.models).

    Uses method_type from METHOD_TYPE_CHOICES (the stable field) rather
    than method.code (which varies by school configuration) to determine
    whether mobile money, bank transfer, and cash options are available.

    Available in all templates:
    - active_payment_methods: Queryset of active PaymentMethod objects,
                              ordered by display_order then name.
    - payment_methods_count:  Integer
    - has_mobile_money:       Boolean — at least one MOBILE_MONEY method active
    - has_bank_transfer:      Boolean — at least one BANK_TRANSFER method active
    - has_cash:               Boolean — at least one CASH method active

    Example:
        <select name="payment_method">
            {% for method in active_payment_methods %}
                <option value="{{ method.id }}">{{ method.name }}</option>
            {% endfor %}
        </select>
    """
    context = {
        'active_payment_methods': [],
        'payment_methods_count':  0,
        'has_mobile_money':       False,
        'has_bank_transfer':      False,
        'has_cash':               False,
    }

    try:
        # PaymentMethod is in core.models — imported at module level above.
        active_methods = PaymentMethod.objects.filter(
            is_active=True
        ).order_by('display_order', 'name')

        context['active_payment_methods'] = active_methods
        context['payment_methods_count']  = active_methods.count()

        # Use method_type (stable field from METHOD_TYPE_CHOICES) rather than
        # method.code (school-configurable, varies by setup).
        method_type_flags = {
            'MOBILE_MONEY':  'has_mobile_money',
            'BANK_TRANSFER': 'has_bank_transfer',
            'CASH':          'has_cash',
        }

        for method in active_methods:
            flag = method_type_flags.get(method.method_type)
            if flag:
                context[flag] = True

    except Exception as e:
        logger.error(f"Error loading payment methods: {e}")

    return context