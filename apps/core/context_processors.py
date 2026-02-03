# core/context_processors.py

"""
Context processors for School Management System.
Provides global data that needs to be available in all templates.

Note: Currency/number formatting should use template filters (currency_filters.py),
not context processors. These processors provide configuration and status data.

Usage:
    Add to settings.py TEMPLATES context_processors:
    'core.context_processors.school_configuration',
    'core.context_processors.active_academic_session',
    'core.context_processors.active_fiscal_period',
    'core.context_processors.payment_methods_context',
    'core.context_processors.system_status',
    'core.context_processors.school_branding',
"""

from django.utils import timezone
from core.models import (
    SchoolConfiguration,
    FinancialSettings,
    FiscalYear,
    FiscalPeriod,
)
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# SCHOOL CONFIGURATION CONTEXT
# =============================================================================

def school_configuration(request):
    """
    Provides school configuration context including term system and settings.
    
    Available in all templates:
    - school_config: Full SchoolConfiguration object
    - term_system: 'term', 'semester', 'quarter', etc.
    - periods_per_year: Number of periods per year
    - period_type_name: 'Term', 'Semester', etc.
    - period_type_name_plural: 'Terms', 'Semesters', etc.
    - period_naming_convention: 'numeric', 'ordinal', 'seasonal', etc.
    - academic_year_type: 'northern', 'southern', 'east_africa', etc.
    - operational_timezone: School's operational timezone
    - school_currency: Currency code (e.g., 'UGX')
    
    Example usage in template:
        <h1>{{ school_config.school_name }}</h1>
        <p>Academic system: {{ term_system }} - {{ periods_per_year }} {{ period_type_name_plural }} per year</p>
        <p>Currency: {{ school_currency }}</p>
    """
    context = {
        'school_config': None,
        'term_system': 'term',
        'periods_per_year': 3,
        'period_type_name': 'Term',
        'period_type_name_plural': 'Terms',
        'period_naming_convention': 'numeric',
        'academic_year_type': 'east_africa',
        'operational_timezone': 'Africa/Kampala',
        'school_currency': 'UGX',
    }
    
    try:
        config = SchoolConfiguration.get_cached_instance()
        if config:
            context['school_config'] = config
            context['term_system'] = config.term_system
            context['periods_per_year'] = config.get_period_count()
            context['period_type_name'] = config.get_period_type_name()
            context['period_type_name_plural'] = config.get_period_type_name_plural()
            context['period_naming_convention'] = config.period_naming_convention
            context['academic_year_type'] = config.academic_year_type
            context['academic_year_start_month'] = config.academic_year_start_month
            context['operational_timezone'] = config.operational_timezone
            context['regional_season_type'] = config.regional_season_type
            context['default_period_duration_weeks'] = config.default_period_duration_weeks
            
            # Communication settings
            context['enable_automatic_reminders'] = config.enable_automatic_reminders
            context['enable_sms'] = config.enable_sms
            context['enable_email_notifications'] = config.enable_email_notifications
            
            # Get currency from financial settings
            fin_settings = FinancialSettings.get_instance()
            if fin_settings:
                context['school_currency'] = fin_settings.school_currency
                context['currency_position'] = fin_settings.currency_position
                context['decimal_places'] = fin_settings.decimal_places
            
    except Exception as e:
        logger.error(f"Error loading school configuration: {e}")
    
    return context


# =============================================================================
# ACTIVE ACADEMIC SESSION CONTEXT
# =============================================================================

def active_academic_session(request):
    """
    Provides active academic session context for teaching/learning activities.
    
    Available in all templates:
    - today: Current date (in school timezone)
    - current_session: Current AcademicSession object
    - session_name: e.g., '2024 - Term 1'
    - session_year: e.g., '2024'
    - session_term: e.g., 'Term 1'
    - session_type: e.g., 'term', 'semester'
    - session_is_special: Boolean
    - session_progress: Progress percentage (0-100)
    - session_days_remaining: Days until session ends
    - session_ending_soon: Boolean warning (14 days)
    - session_is_enrollment_open: Boolean
    - session_allows_promotion: Boolean
    
    Example usage in template:
        <div class="current-session">
            <h3>{{ session_name }}</h3>
            <div class="progress">
                <div class="progress-bar" style="width: {{ session_progress }}%"></div>
            </div>
            <p>{{ session_days_remaining }} days remaining</p>
        </div>
    """
    from core.utils import get_school_today
    
    today = get_school_today()  # Use school timezone
    
    context = {
        'today': today,
        'current_session': None,
        'session_name': None,
        'session_year': None,
        'session_term': None,
        'session_type': None,
        'session_is_special': False,
        'session_progress': 0,
        'session_days_remaining': 0,
        'session_ending_soon': False,
        'session_is_enrollment_open': False,
        'session_allows_promotion': False,
    }
    
    try:
        from academics.models import AcademicSession
        
        # Get current session
        session = AcademicSession.get_current_session()
        if session:
            context['current_session'] = session
            context['session_name'] = session.name
            context['session_year'] = session.year_name
            context['session_term'] = session.term_name
            context['session_type'] = session.period_type
            context['session_number'] = session.term_number
            context['session_is_special'] = session.is_special_session
            context['session_start_date'] = session.start_date
            context['session_end_date'] = session.end_date
            context['session_progress'] = session.progress_percentage
            context['session_days_remaining'] = session.days_remaining
            context['session_days_elapsed'] = session.days_elapsed
            context['session_total_days'] = session.total_days
            context['session_status'] = session.status_display
            context['session_is_enrollment_open'] = session.is_enrollment_open
            context['session_allows_promotion'] = session.allows_promotion
            context['session_promotion_done'] = session.promotion_done
            context['session_is_academically_closed'] = session.is_academically_closed
            
            # Session ending soon warning (14 days)
            if 0 < session.days_remaining <= 14:
                context['session_ending_soon'] = True
        
        # Get sessions open for enrollment
        enrollment_sessions = AcademicSession.get_open_for_enrollment()
        context['enrollment_sessions'] = enrollment_sessions
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
    
    Available in all templates:
    - active_fiscal_year: Active FiscalYear object
    - active_fiscal_period: Active FiscalPeriod object
    - fiscal_year_name: e.g., '2024'
    - fiscal_period_name: e.g., 'Term 1 2024 Fiscal Period'
    - fiscal_year_progress: Progress percentage (0-100)
    - fiscal_period_progress: Progress percentage (0-100)
    - fiscal_year_ending_soon: Boolean warning (90 days)
    - fiscal_period_ending_soon: Boolean warning (14 days)
    - can_accept_transactions: Boolean
    - can_generate_invoices: Boolean
    
    Example usage in template:
        {% if active_fiscal_period %}
            <div class="fiscal-info">
                <p>Fiscal Period: {{ fiscal_period_name }}</p>
                <p>Year: {{ fiscal_year_name }}</p>
                {% if fiscal_period_ending_soon %}
                    <div class="alert alert-warning">Period ending soon!</div>
                {% endif %}
            </div>
        {% else %}
            <div class="alert alert-danger">No active fiscal period</div>
        {% endif %}
    """
    from core.utils import get_school_today
    
    today = get_school_today()  # Use school timezone
    
    context = {
        'active_fiscal_year': None,
        'active_fiscal_period': None,
        'fiscal_year_name': None,
        'fiscal_period_name': None,
        'fiscal_year_progress': 0,
        'fiscal_period_progress': 0,
        'fiscal_year_ending_soon': False,
        'fiscal_period_ending_soon': False,
        'days_until_fy_end': None,
        'days_until_period_end': None,
        'can_accept_transactions': False,
        'can_generate_invoices': False,
    }
    
    try:
        # Get active fiscal year
        fiscal_year = FiscalYear.get_active_fiscal_year()
        if fiscal_year:
            context['active_fiscal_year'] = fiscal_year
            context['fiscal_year_name'] = fiscal_year.name
            context['fiscal_year_code'] = fiscal_year.code
            context['fiscal_year_start_date'] = fiscal_year.start_date
            context['fiscal_year_end_date'] = fiscal_year.end_date
            context['fiscal_year_progress'] = fiscal_year.get_progress_percentage()
            context['fiscal_year_status'] = fiscal_year.status
            context['fiscal_year_is_closed'] = fiscal_year.is_closed
            context['fiscal_year_is_locked'] = fiscal_year.is_locked
            context['fiscal_year_remaining_days'] = fiscal_year.get_remaining_days()
            context['fiscal_year_elapsed_days'] = fiscal_year.get_elapsed_days()
            context['fiscal_year_period_count'] = fiscal_year.get_period_count()
            
            # Fiscal year ending soon warning (90 days)
            days_until_end = fiscal_year.get_remaining_days()
            context['days_until_fy_end'] = days_until_end
            if 0 < days_until_end <= 90:
                context['fiscal_year_ending_soon'] = True
        
        # Get active fiscal period
        period = FiscalPeriod.get_current_fiscal_period()
        if period:
            context['active_fiscal_period'] = period
            context['fiscal_period_name'] = period.name
            context['fiscal_period_number'] = period.period_number
            context['fiscal_period_type'] = period.period_type
            context['fiscal_period_start_date'] = period.start_date
            context['fiscal_period_end_date'] = period.end_date
            context['fiscal_period_progress'] = period.get_progress_percentage()
            context['fiscal_period_status'] = period.status
            context['fiscal_period_is_closed'] = period.is_closed
            context['fiscal_period_is_locked'] = period.is_locked
            context['fiscal_period_remaining_days'] = period.get_remaining_days()
            context['fiscal_period_elapsed_days'] = period.get_elapsed_days()
            
            # Period ending soon warning (14 days)
            days_until_period_end = period.get_remaining_days()
            context['days_until_period_end'] = days_until_period_end
            if 0 < days_until_period_end <= 14:
                context['fiscal_period_ending_soon'] = True
            
            # Transaction permissions
            context['can_accept_transactions'] = period.can_accept_transactions()
            context['can_generate_invoices'] = period.can_generate_invoices()
            context['can_process_refunds'] = period.can_process_refunds()
            context['can_accept_advance_payments'] = period.can_accept_advance_payment()
            context['can_accept_arrears_payments'] = period.can_accept_arrears_payment()
            
            # Grace period info
            context['fiscal_period_in_grace'] = period.is_in_grace_period()
            context['fiscal_period_grace_days'] = period.grace_period_days
            
            # Academic session relationship
            if period.related_academic_session:
                context['fiscal_period_academic_session'] = period.related_academic_session
                
    except Exception as e:
        logger.error(f"Error loading active fiscal period: {e}")
    
    return context


# =============================================================================
# PAYMENT METHODS CONTEXT
# =============================================================================

def payment_methods_context(request):
    """
    Provides available payment methods for dropdowns and forms.
    
    Available in all templates:
    - active_payment_methods: All active payment methods
    - payment_methods_count: Count of active methods
    - has_mobile_money: Boolean
    - has_bank_transfer: Boolean
    - has_cash: Boolean
    
    Example usage in template:
        <select name="payment_method">
            {% for method in active_payment_methods %}
                <option value="{{ method.id }}">{{ method.name }}</option>
            {% endfor %}
        </select>
    """
    context = {
        'active_payment_methods': [],
        'payment_methods_count': 0,
        'has_mobile_money': False,
        'has_bank_transfer': False,
        'has_cash': False,
    }
    
    try:
        from finance.models import PaymentMethod
        
        # Get all active payment methods
        active_methods = PaymentMethod.objects.filter(is_active=True).order_by('name')
        context['active_payment_methods'] = active_methods
        context['payment_methods_count'] = active_methods.count()
        
        # Check for specific payment types
        for method in active_methods:
            code = method.code if hasattr(method, 'code') else ''
            
            if code in ['MOBILE_MONEY', 'MTN_MOBILE_MONEY', 'AIRTEL_MONEY']:
                context['has_mobile_money'] = True
            elif code in ['BANK_TRANSFER', 'BANK_DEPOSIT']:
                context['has_bank_transfer'] = True
            elif code in ['CASH', 'PETTY_CASH']:
                context['has_cash'] = True
        
    except Exception as e:
        logger.error(f"Error loading payment methods: {e}")
    
    return context






