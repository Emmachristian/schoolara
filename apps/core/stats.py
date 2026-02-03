# core/stats.py

"""
Core statistics and analytics utilities for School Management System.
Provides comprehensive statistics for configuration, financial settings,
fiscal management, and system-wide metrics.

All date-based calculations use school timezone for consistency.
"""

from django.db.models import Count, Avg, Q, Max, Min, Sum, F, DecimalField
from django.db.models.functions import TruncMonth, TruncDate
from datetime import timedelta
from decimal import Decimal
import logging

# Import centralized utilities (timezone-aware)
from core.utils import (
    get_school_today,
    get_school_current_time,
    get_active_academic_session,
    get_active_fiscal_year,
    get_active_fiscal_period,
    calculate_percentage,
)

logger = logging.getLogger(__name__)


# =============================================================================
# SCHOOL CONFIGURATION STATISTICS
# =============================================================================

def get_school_configuration_summary():
    """
    Get comprehensive school configuration summary.
    
    Returns:
        dict: Configuration summary including term system, timezone, and settings
    
    Example:
        >>> from core.stats import get_school_configuration_summary
        >>> config = get_school_configuration_summary()
        >>> print(f"Term System: {config['term_system']}")
        >>> print(f"Timezone: {config['timezone']}")
    """
    from .models import SchoolConfiguration
    
    try:
        config = SchoolConfiguration.get_instance()
        
        if not config:
            return {
                'error': 'School configuration not found',
                'is_configured': False,
            }
        
        return {
            'is_configured': True,
            'term_system': config.get_term_system_display(),
            'term_system_code': config.term_system,
            'periods_per_year': config.get_period_count(),
            'period_type_name': config.get_period_type_name(),
            'period_type_plural': config.get_period_type_name_plural(),
            'timezone': config.operational_timezone,
            'timezone_display': str(config.get_timezone()),
            'academic_year_type': config.get_academic_year_type_display(),
            'academic_year_start_month': config.academic_year_start_month,
            'academic_year_start_day': config.academic_year_start_day,
            'regional_season_type': config.get_regional_season_type_display(),
            'default_period_duration_weeks': config.default_period_duration_weeks,
            'enable_automatic_reminders': config.enable_automatic_reminders,
            'enable_sms': config.enable_sms,
            'enable_email_notifications': config.enable_email_notifications,
            'all_period_names': config.get_all_period_names(),
        }
        
    except Exception as e:
        logger.error(f"Error getting school configuration summary: {e}")
        return {
            'error': str(e),
            'is_configured': False,
        }


def get_period_naming_preview(config=None):
    """
    Get preview of period names for current configuration.
    
    Args:
        config: SchoolConfiguration instance (defaults to current)
        
    Returns:
        list: List of period names for display
    
    Example:
        >>> from core.stats import get_period_naming_preview
        >>> names = get_period_naming_preview()
        >>> for name in names:
        >>>     print(name)
    """
    from .models import SchoolConfiguration
    
    if config is None:
        config = SchoolConfiguration.get_instance()
    
    if not config:
        return []
    
    return config.get_all_period_names()


# =============================================================================
# FINANCIAL SETTINGS STATISTICS
# =============================================================================

def get_financial_settings_summary():
    """
    Get comprehensive financial settings summary.
    
    Returns:
        dict: Financial settings including currency, payment terms, and policies
    
    Example:
        >>> from core.stats import get_financial_settings_summary
        >>> settings = get_financial_settings_summary()
        >>> print(f"Currency: {settings['currency']}")
        >>> print(f"Payment Terms: {settings['payment_terms_days']} days")
    """
    from .models import FinancialSettings
    
    try:
        settings = FinancialSettings.get_instance()
        
        if not settings:
            return {
                'error': 'Financial settings not found',
                'is_configured': False,
            }
        
        # Get account mappings status
        has_core_mappings = hasattr(settings, 'core_account_mappings')
        has_revenue_mappings = hasattr(settings, 'revenue_account_mappings')
        has_payroll_mappings = hasattr(settings, 'payroll_account_mappings')
        has_expense_mappings = hasattr(settings, 'expense_account_mappings')
        has_special_mappings = hasattr(settings, 'special_account_mappings')
        
        return {
            'is_configured': True,
            
            # Currency
            'currency': settings.school_currency,
            'currency_position': settings.get_currency_position_display(),
            'decimal_places': settings.decimal_places,
            'use_thousand_separator': settings.use_thousand_separator,
            
            # Numbering
            'invoice_prefix': settings.invoice_prefix,
            'payment_prefix': settings.payment_prefix,
            'receipt_prefix': settings.receipt_prefix,
            'expense_prefix': settings.expense_prefix,
            'include_year_in_numbers': settings.include_year_in_invoice_number,
            
            # Payment Terms
            'payment_terms_days': settings.default_payment_terms_days,
            'late_fee_enabled': settings.late_fee_enabled,
            'late_fee_percentage': float(settings.late_fee_percentage),
            'grace_period_days': settings.grace_period_days,
            'minimum_payment_amount': float(settings.minimum_payment_amount),
            'allow_partial_payments': settings.allow_partial_payments,
            
            # Scholarships & Discounts
            'auto_apply_scholarships': settings.auto_apply_scholarships,
            'scholarship_approval_required': settings.scholarship_approval_required,
            'auto_apply_discounts': settings.auto_apply_discounts,
            'discount_approval_required': settings.discount_approval_required,
            'discount_approval_threshold': float(settings.discount_approval_threshold),
            'early_payment_discount_enabled': settings.early_payment_discount_enabled,
            'early_payment_discount_percentage': float(settings.early_payment_discount_percentage),
            'early_payment_discount_days': settings.early_payment_discount_days,
            
            # Workflows
            'expense_approval_required': settings.expense_approval_required,
            'expense_approval_limit': float(settings.expense_approval_limit),
            'require_payment_confirmation': settings.require_payment_confirmation,
            'require_expense_receipts': settings.require_expense_receipts,
            'require_purchase_orders': settings.require_purchase_orders,
            
            # Communication
            'send_invoice_emails': settings.send_invoice_emails,
            'send_payment_confirmations': settings.send_payment_confirmations,
            'send_overdue_reminders': settings.send_overdue_reminders,
            'overdue_reminder_days': settings.overdue_reminder_days,
            'send_sms_notifications': settings.send_sms_notifications,
            
            # Tax & Accounting
            'include_tax_in_prices': settings.include_tax_in_prices,
            'default_tax_rate': float(settings.default_tax_rate),
            'multi_currency_enabled': settings.multi_currency_enabled,
            'auto_generate_recurring_invoices': settings.auto_generate_recurring_invoices,
            
            # Account Mappings Status
            'has_core_mappings': has_core_mappings,
            'has_revenue_mappings': has_revenue_mappings,
            'has_payroll_mappings': has_payroll_mappings,
            'has_expense_mappings': has_expense_mappings,
            'has_special_mappings': has_special_mappings,
            'account_mappings_complete': all([
                has_core_mappings,
                has_revenue_mappings,
                has_payroll_mappings,
                has_expense_mappings,
                has_special_mappings,
            ]),
        }
        
    except Exception as e:
        logger.error(f"Error getting financial settings summary: {e}")
        return {
            'error': str(e),
            'is_configured': False,
        }


def get_account_mappings_status():
    """
    Get status of all account mappings.
    
    Returns:
        dict: Status of each account mapping category with completion percentage
    
    Example:
        >>> from core.stats import get_account_mappings_status
        >>> status = get_account_mappings_status()
        >>> print(f"Core Mappings: {status['core']['completion_percentage']}%")
    """
    from .models import (
        FinancialSettings,
        CoreAccountMappings,
        RevenueAccountMappings,
        PayrollAccountMappings,
        ExpenseAccountMappings,
        SpecialAccountMappings,
    )
    
    try:
        settings = FinancialSettings.get_instance()
        if not settings:
            return {'error': 'Financial settings not found'}
        
        def get_mapping_status(mapping_model, mapping_attr):
            """Helper to get completion status for a mapping category"""
            try:
                mapping = getattr(settings, mapping_attr)
                if not mapping:
                    return {
                        'exists': False,
                        'completion_percentage': 0,
                        'mapped_count': 0,
                        'total_fields': 0,
                    }
                
                # Count non-null account fields
                total_fields = 0
                mapped_fields = 0
                
                for field in mapping._meta.fields:
                    if field.name.endswith('_account') and field.name != 'financial_settings':
                        total_fields += 1
                        if getattr(mapping, field.name) is not None:
                            mapped_fields += 1
                
                completion = (mapped_fields / total_fields * 100) if total_fields > 0 else 0
                
                return {
                    'exists': True,
                    'completion_percentage': round(completion, 1),
                    'mapped_count': mapped_fields,
                    'total_fields': total_fields,
                }
                
            except Exception as e:
                logger.error(f"Error getting mapping status for {mapping_attr}: {e}")
                return {
                    'exists': False,
                    'completion_percentage': 0,
                    'mapped_count': 0,
                    'total_fields': 0,
                    'error': str(e),
                }
        
        return {
            'core': get_mapping_status(CoreAccountMappings, 'core_account_mappings'),
            'revenue': get_mapping_status(RevenueAccountMappings, 'revenue_account_mappings'),
            'payroll': get_mapping_status(PayrollAccountMappings, 'payroll_account_mappings'),
            'expense': get_mapping_status(ExpenseAccountMappings, 'expense_account_mappings'),
            'special': get_mapping_status(SpecialAccountMappings, 'special_account_mappings'),
        }
        
    except Exception as e:
        logger.error(f"Error getting account mappings status: {e}")
        return {'error': str(e)}


# =============================================================================
# FISCAL YEAR STATISTICS
# =============================================================================

def get_fiscal_year_statistics():
    """
    Get comprehensive fiscal year statistics (using school timezone).
    
    Returns:
        dict: Fiscal year statistics including counts, status breakdown, and active year info
    
    Example:
        >>> from core.stats import get_fiscal_year_statistics
        >>> stats = get_fiscal_year_statistics()
        >>> print(f"Total Fiscal Years: {stats['total_count']}")
        >>> print(f"Active Year: {stats['active_year']['name']}")
    """
    from .models import FiscalYear
    
    try:
        today = get_school_today()  # ⭐ SCHOOL TIMEZONE
        
        fiscal_years = FiscalYear.objects.all()
        
        # Basic counts
        total_count = fiscal_years.count()
        active_count = fiscal_years.filter(is_active=True).count()
        closed_count = fiscal_years.filter(is_closed=True).count()
        locked_count = fiscal_years.filter(is_locked=True).count()
        
        # Status breakdown
        status_breakdown = {}
        for status_code, status_name in FiscalYear.STATUS_CHOICES:
            status_breakdown[status_code] = fiscal_years.filter(
                status=status_code
            ).count()
        
        # Current/Past/Future counts
        current_count = fiscal_years.filter(
            start_date__lte=today,
            end_date__gte=today
        ).count()
        
        past_count = fiscal_years.filter(end_date__lt=today).count()
        future_count = fiscal_years.filter(start_date__gt=today).count()
        
        # Active fiscal year details
        active_year = get_active_fiscal_year()
        active_year_info = None
        
        if active_year:
            active_year_info = {
                'id': active_year.id,
                'name': active_year.name,
                'code': active_year.code,
                'start_date': active_year.start_date,
                'end_date': active_year.end_date,
                'duration_days': active_year.get_duration_days(),
                'elapsed_days': active_year.get_elapsed_days(),
                'remaining_days': active_year.get_remaining_days(),
                'progress_percentage': active_year.get_progress_percentage(),
                'is_current': active_year.is_current(),
                'period_count': active_year.get_period_count(),
            }
        
        return {
            'total_count': total_count,
            'active_count': active_count,
            'closed_count': closed_count,
            'locked_count': locked_count,
            'current_count': current_count,
            'past_count': past_count,
            'future_count': future_count,
            'status_breakdown': status_breakdown,
            'active_year': active_year_info,
        }
        
    except Exception as e:
        logger.error(f"Error getting fiscal year statistics: {e}")
        return {
            'error': str(e),
            'total_count': 0,
        }


def get_fiscal_year_timeline():
    """
    Get timeline of all fiscal years (past, current, future) using school timezone.
    
    Returns:
        dict: Timeline with past, current, and future fiscal years
    
    Example:
        >>> from core.stats import get_fiscal_year_timeline
        >>> timeline = get_fiscal_year_timeline()
        >>> print(f"Past Years: {len(timeline['past'])}")
        >>> print(f"Future Years: {len(timeline['future'])}")
    """
    from .models import FiscalYear
    
    try:
        today = get_school_today()  # ⭐ SCHOOL TIMEZONE
        
        past_years = FiscalYear.objects.filter(
            end_date__lt=today
        ).order_by('-end_date')[:5]  # Last 5 past years
        
        current_years = FiscalYear.objects.filter(
            start_date__lte=today,
            end_date__gte=today
        ).order_by('start_date')
        
        future_years = FiscalYear.objects.filter(
            start_date__gt=today
        ).order_by('start_date')[:5]  # Next 5 future years
        
        def serialize_year(year):
            return {
                'id': year.id,
                'name': year.name,
                'code': year.code,
                'start_date': year.start_date,
                'end_date': year.end_date,
                'status': year.get_status_display(),
                'is_active': year.is_active,
                'is_closed': year.is_closed,
                'is_locked': year.is_locked,
            }
        
        return {
            'past': [serialize_year(y) for y in past_years],
            'current': [serialize_year(y) for y in current_years],
            'future': [serialize_year(y) for y in future_years],
        }
        
    except Exception as e:
        logger.error(f"Error getting fiscal year timeline: {e}")
        return {
            'error': str(e),
            'past': [],
            'current': [],
            'future': [],
        }


# =============================================================================
# FISCAL PERIOD STATISTICS
# =============================================================================

def get_fiscal_period_statistics():
    """
    Get comprehensive fiscal period statistics (using school timezone).
    
    Returns:
        dict: Fiscal period statistics including counts, types, and current period info
    
    Example:
        >>> from core.stats import get_fiscal_period_statistics
        >>> stats = get_fiscal_period_statistics()
        >>> print(f"Total Periods: {stats['total_count']}")
        >>> print(f"Active Period: {stats['current_period']['name']}")
    """
    from .models import FiscalPeriod
    
    try:
        today = get_school_today()  # ⭐ SCHOOL TIMEZONE
        
        periods = FiscalPeriod.objects.all()
        
        # Basic counts
        total_count = periods.count()
        active_count = periods.filter(is_active=True).count()
        closed_count = periods.filter(is_closed=True).count()
        locked_count = periods.filter(is_locked=True).count()
        
        # Period type breakdown
        type_breakdown = {}
        for type_code, type_name in FiscalPeriod.PERIOD_TYPE_CHOICES:
            type_breakdown[type_code] = periods.filter(
                period_type=type_code
            ).count()
        
        # Status breakdown
        status_breakdown = {}
        for status_code, status_name in FiscalPeriod.STATUS_CHOICES:
            status_breakdown[status_code] = periods.filter(
                status=status_code
            ).count()
        
        # Current/Past/Future counts
        current_count = periods.filter(
            start_date__lte=today,
            end_date__gte=today
        ).count()
        
        past_count = periods.filter(end_date__lt=today).count()
        future_count = periods.filter(start_date__gt=today).count()
        
        # Periods in grace period
        grace_period_count = 0
        for period in periods.filter(is_active=True):
            if period.is_in_grace_period():
                grace_period_count += 1
        
        # Current fiscal period details
        current_period = get_active_fiscal_period()
        current_period_info = None
        
        if current_period:
            current_period_info = {
                'id': current_period.id,
                'name': current_period.name,
                'code': current_period.code,
                'period_number': float(current_period.period_number),
                'period_type': current_period.get_period_type_display(),
                'start_date': current_period.start_date,
                'end_date': current_period.end_date,
                'duration_days': current_period.get_duration_days(),
                'elapsed_days': current_period.get_elapsed_days(),
                'remaining_days': current_period.get_remaining_days(),
                'progress_percentage': current_period.get_progress_percentage(),
                'can_accept_transactions': current_period.can_accept_transactions(),
                'is_in_grace_period': current_period.is_in_grace_period(),
                'grace_period_days': current_period.grace_period_days,
            }
        
        return {
            'total_count': total_count,
            'active_count': active_count,
            'closed_count': closed_count,
            'locked_count': locked_count,
            'current_count': current_count,
            'past_count': past_count,
            'future_count': future_count,
            'grace_period_count': grace_period_count,
            'type_breakdown': type_breakdown,
            'status_breakdown': status_breakdown,
            'current_period': current_period_info,
        }
        
    except Exception as e:
        logger.error(f"Error getting fiscal period statistics: {e}")
        return {
            'error': str(e),
            'total_count': 0,
        }


def get_fiscal_periods_by_year(fiscal_year=None):
    """
    Get all fiscal periods for a specific fiscal year.
    
    Args:
        fiscal_year: FiscalYear instance or ID (defaults to active year)
        
    Returns:
        dict: Periods grouped by status with summary
    
    Example:
        >>> from core.stats import get_fiscal_periods_by_year
        >>> periods = get_fiscal_periods_by_year()
        >>> print(f"Active Periods: {len(periods['active'])}")
    """
    from .models import FiscalPeriod
    
    try:
        # Default to active fiscal year
        if fiscal_year is None:
            fiscal_year = get_active_fiscal_year()
            if fiscal_year is None:
                return {
                    'error': 'No fiscal year provided and no active year found',
                    'total_count': 0,
                }
        
        # Get periods for the year
        if hasattr(fiscal_year, 'id'):
            periods = FiscalPeriod.objects.filter(
                fiscal_year=fiscal_year
            ).order_by('period_number')
        else:
            periods = FiscalPeriod.objects.filter(
                fiscal_year_id=fiscal_year
            ).order_by('period_number')
        
        # Group by status
        active_periods = periods.filter(is_active=True)
        closed_periods = periods.filter(is_closed=True, is_locked=False)
        locked_periods = periods.filter(is_locked=True)
        draft_periods = periods.filter(status='DRAFT')
        
        def serialize_period(period):
            return {
                'id': period.id,
                'name': period.name,
                'code': period.code,
                'period_number': float(period.period_number),
                'period_type': period.get_period_type_display(),
                'start_date': period.start_date,
                'end_date': period.end_date,
                'status': period.get_status_display(),
                'can_accept_transactions': period.can_accept_transactions(),
            }
        
        return {
            'total_count': periods.count(),
            'active': [serialize_period(p) for p in active_periods],
            'closed': [serialize_period(p) for p in closed_periods],
            'locked': [serialize_period(p) for p in locked_periods],
            'draft': [serialize_period(p) for p in draft_periods],
        }
        
    except Exception as e:
        logger.error(f"Error getting fiscal periods by year: {e}")
        return {
            'error': str(e),
            'total_count': 0,
        }


# =============================================================================
# PAYMENT METHOD STATISTICS
# =============================================================================

def get_payment_method_statistics():
    """
    Get comprehensive payment method statistics.
    
    Returns:
        dict: Payment method statistics including counts, types, and usage
    
    Example:
        >>> from core.stats import get_payment_method_statistics
        >>> stats = get_payment_method_statistics()
        >>> print(f"Total Methods: {stats['total_count']}")
        >>> print(f"Active Methods: {stats['active_count']}")
    """
    from .models import PaymentMethod
    
    try:
        methods = PaymentMethod.objects.all()
        
        # Basic counts
        total_count = methods.count()
        active_count = methods.filter(is_active=True).count()
        default_method = methods.filter(is_default=True).first()
        
        # Method type breakdown
        type_breakdown = {}
        for type_code, type_name in PaymentMethod.METHOD_TYPE_CHOICES:
            count = methods.filter(method_type=type_code, is_active=True).count()
            if count > 0:
                type_breakdown[type_code] = {
                    'count': count,
                    'name': type_name,
                }
        
        # Methods requiring approval
        approval_required_count = methods.filter(
            is_active=True,
            requires_approval=True
        ).count()
        
        # Methods with transaction fees
        fee_methods_count = methods.filter(
            is_active=True,
            has_transaction_fee=True
        ).count()
        
        # Methods requiring reference
        reference_required_count = methods.filter(
            is_active=True,
            requires_reference=True
        ).count()
        
        # Mobile money providers
        mobile_money_methods = methods.filter(
            method_type='MOBILE_MONEY',
            is_active=True
        )
        
        mobile_money_providers = {}
        for method in mobile_money_methods:
            if method.mobile_money_provider:
                provider = method.get_mobile_money_provider_display()
                if provider not in mobile_money_providers:
                    mobile_money_providers[provider] = 0
                mobile_money_providers[provider] += 1
        
        return {
            'total_count': total_count,
            'active_count': active_count,
            'inactive_count': total_count - active_count,
            'type_breakdown': type_breakdown,
            'approval_required_count': approval_required_count,
            'fee_methods_count': fee_methods_count,
            'reference_required_count': reference_required_count,
            'mobile_money_providers': mobile_money_providers,
            'default_method': {
                'id': default_method.id,
                'name': default_method.name,
                'code': default_method.code,
                'type': default_method.get_method_type_display(),
            } if default_method else None,
        }
        
    except Exception as e:
        logger.error(f"Error getting payment method statistics: {e}")
        return {
            'error': str(e),
            'total_count': 0,
        }


def get_payment_method_usage_stats(days=30):
    """
    Get payment method usage statistics for recent transactions.
    
    Args:
        days: Number of days to analyze (default: 30)
        
    Returns:
        dict: Usage statistics by payment method
    
    Example:
        >>> from core.stats import get_payment_method_usage_stats
        >>> usage = get_payment_method_usage_stats(days=30)
        >>> for method, stats in usage['by_method'].items():
        >>>     print(f"{method}: {stats['count']} payments")
    """
    from .models import PaymentMethod
    
    try:
        today = get_school_today()  # ⭐ SCHOOL TIMEZONE
        start_date = today - timedelta(days=days)
        
        # Try to import Payment model (may not exist yet)
        try:
            from finance.models import Payment
            
            # Get payments in date range
            payments = Payment.objects.filter(
                payment_date__gte=start_date,
                payment_date__lte=today
            )
            
            total_payments = payments.count()
            total_amount = payments.aggregate(
                total=Sum('amount')
            )['total'] or Decimal('0.00')
            
            # Group by payment method
            by_method = {}
            for method in PaymentMethod.objects.filter(is_active=True):
                method_payments = payments.filter(payment_method=method)
                count = method_payments.count()
                amount = method_payments.aggregate(
                    total=Sum('amount')
                )['total'] or Decimal('0.00')
                
                if count > 0:
                    by_method[method.name] = {
                        'count': count,
                        'amount': float(amount),
                        'percentage': calculate_percentage(count, total_payments),
                    }
            
            return {
                'period_days': days,
                'start_date': start_date,
                'end_date': today,
                'total_payments': total_payments,
                'total_amount': float(total_amount),
                'by_method': by_method,
            }
            
        except ImportError:
            logger.warning("Payment model not found - cannot get usage stats")
            return {
                'error': 'Payment model not available',
                'total_payments': 0,
            }
        
    except Exception as e:
        logger.error(f"Error getting payment method usage stats: {e}")
        return {
            'error': str(e),
            'total_payments': 0,
        }


# =============================================================================
# TAX RATE STATISTICS
# =============================================================================

def get_tax_rate_statistics():
    """
    Get comprehensive tax rate statistics (using school timezone).
    
    Returns:
        dict: Tax rate statistics including counts, types, and active rates
    
    Example:
        >>> from core.stats import get_tax_rate_statistics
        >>> stats = get_tax_rate_statistics()
        >>> print(f"Total Tax Rates: {stats['total_count']}")
        >>> print(f"Active Rates: {stats['active_count']}")
    """
    from .models import TaxRate
    
    try:
        today = get_school_today()  # ⭐ SCHOOL TIMEZONE
        
        tax_rates = TaxRate.objects.all()
        
        # Basic counts
        total_count = tax_rates.count()
        active_count = tax_rates.filter(is_active=True).count()
        
        # Currently effective rates (within date range)
        effective_count = tax_rates.filter(
            is_active=True,
            effective_from__lte=today
        ).filter(
            Q(effective_to__isnull=True) | Q(effective_to__gte=today)
        ).count()
        
        # Tax type breakdown
        type_breakdown = {}
        for type_code, type_name in TaxRate.TAX_TYPE_CHOICES:
            count = tax_rates.filter(tax_type=type_code).count()
            if count > 0:
                type_breakdown[type_code] = {
                    'count': count,
                    'name': type_name,
                }
        
        # Get active rate for each type
        active_rates_by_type = {}
        for type_code, type_name in TaxRate.TAX_TYPE_CHOICES:
            rate = TaxRate.get_active_rate(type_code, today)
            if rate:
                active_rates_by_type[type_code] = {
                    'id': rate.id,
                    'name': rate.name,
                    'rate': float(rate.rate),
                    'effective_from': rate.effective_from,
                    'effective_to': rate.effective_to,
                }
        
        # Rates by application
        fee_applicable_count = tax_rates.filter(
            is_active=True,
            applies_to_fees=True
        ).count()
        
        service_applicable_count = tax_rates.filter(
            is_active=True,
            applies_to_services=True
        ).count()
        
        return {
            'total_count': total_count,
            'active_count': active_count,
            'effective_count': effective_count,
            'inactive_count': total_count - active_count,
            'type_breakdown': type_breakdown,
            'fee_applicable_count': fee_applicable_count,
            'service_applicable_count': service_applicable_count,
            'active_rates_by_type': active_rates_by_type,
        }
        
    except Exception as e:
        logger.error(f"Error getting tax rate statistics: {e}")
        return {
            'error': str(e),
            'total_count': 0,
        }


def get_tax_rate_history(tax_type=None, months=12):
    """
    Get historical tax rate changes (using school timezone).
    
    Args:
        tax_type: Specific tax type to analyze (optional)
        months: Number of months to look back (default: 12)
        
    Returns:
        list: Historical tax rate changes
    
    Example:
        >>> from core.stats import get_tax_rate_history
        >>> history = get_tax_rate_history('VAT', months=24)
        >>> for change in history:
        >>>     print(f"{change['date']}: {change['rate']}%")
    """
    from .models import TaxRate
    
    try:
        today = get_school_today()  # ⭐ SCHOOL TIMEZONE
        start_date = today - timedelta(days=months * 30)
        
        rates = TaxRate.objects.filter(
            effective_from__gte=start_date
        ).order_by('-effective_from')
        
        if tax_type:
            rates = rates.filter(tax_type=tax_type)
        
        history = []
        for rate in rates:
            history.append({
                'id': rate.id,
                'name': rate.name,
                'tax_type': rate.get_tax_type_display(),
                'rate': float(rate.rate),
                'effective_from': rate.effective_from,
                'effective_to': rate.effective_to,
                'is_active': rate.is_active,
                'is_effective': rate.is_effective(today),
            })
        
        return history
        
    except Exception as e:
        logger.error(f"Error getting tax rate history: {e}")
        return []


# =============================================================================
# UNIT OF MEASURE STATISTICS
# =============================================================================

def get_unit_of_measure_statistics():
    """
    Get comprehensive unit of measure statistics.
    
    Returns:
        dict: UOM statistics including counts, types, and conversion info
    
    Example:
        >>> from core.stats import get_unit_of_measure_statistics
        >>> stats = get_unit_of_measure_statistics()
        >>> print(f"Total Units: {stats['total_count']}")
        >>> print(f"Base Units: {stats['base_units_count']}")
    """
    from .models import UnitOfMeasure
    
    try:
        units = UnitOfMeasure.objects.all()
        
        # Basic counts
        total_count = units.count()
        active_count = units.filter(is_active=True).count()
        base_units_count = units.filter(base_unit__isnull=True, is_active=True).count()
        derived_units_count = units.filter(base_unit__isnull=False, is_active=True).count()
        
        # Type breakdown
        type_breakdown = {}
        for type_code, type_name in UnitOfMeasure.UOM_TYPE_CHOICES:
            count = units.filter(uom_type=type_code, is_active=True).count()
            if count > 0:
                # Get base and derived counts for this type
                base_count = units.filter(
                    uom_type=type_code,
                    is_active=True,
                    base_unit__isnull=True
                ).count()
                derived_count = units.filter(
                    uom_type=type_code,
                    is_active=True,
                    base_unit__isnull=False
                ).count()
                
                type_breakdown[type_code] = {
                    'name': type_name,
                    'total': count,
                    'base_units': base_count,
                    'derived_units': derived_count,
                }
        
        # Most used base units (units with most derivatives)
        base_units_usage = []
        for base_unit in units.filter(base_unit__isnull=True, is_active=True):
            derived_count = base_unit.get_derived_units_count()
            if derived_count > 0:
                base_units_usage.append({
                    'id': base_unit.id,
                    'name': base_unit.name,
                    'abbreviation': base_unit.abbreviation,
                    'type': base_unit.get_uom_type_display(),
                    'derived_count': derived_count,
                })
        
        # Sort by derived count
        base_units_usage.sort(key=lambda x: x['derived_count'], reverse=True)
        
        return {
            'total_count': total_count,
            'active_count': active_count,
            'inactive_count': total_count - active_count,
            'base_units_count': base_units_count,
            'derived_units_count': derived_units_count,
            'type_breakdown': type_breakdown,
            'most_used_base_units': base_units_usage[:5],  # Top 5
        }
        
    except Exception as e:
        logger.error(f"Error getting unit of measure statistics: {e}")
        return {
            'error': str(e),
            'total_count': 0,
        }


def get_unit_conversion_examples(uom_type=None, limit=5):
    """
    Get example conversions for units.
    
    Args:
        uom_type: Specific UOM type (optional)
        limit: Maximum number of examples (default: 5)
        
    Returns:
        list: Conversion examples
    
    Example:
        >>> from core.stats import get_unit_conversion_examples
        >>> examples = get_unit_conversion_examples('LENGTH')
        >>> for ex in examples:
        >>>     print(ex['formatted'])
    """
    from .models import UnitOfMeasure
    
    try:
        units = UnitOfMeasure.objects.filter(
            is_active=True,
            base_unit__isnull=False  # Only derived units
        )
        
        if uom_type:
            units = units.filter(uom_type=uom_type)
        
        units = units.order_by('uom_type', 'name')[:limit]
        
        examples = []
        for unit in units:
            example = unit.get_conversion_example(value=10)
            if example:
                examples.append(example)
        
        return examples
        
    except Exception as e:
        logger.error(f"Error getting unit conversion examples: {e}")
        return []


# =============================================================================
# SYSTEM-WIDE STATISTICS
# =============================================================================

def get_core_system_statistics():
    """
    Get comprehensive system-wide statistics.
    Combines all core statistics into one summary.
    
    Returns:
        dict: Complete system statistics
    
    Example:
        >>> from core.stats import get_core_system_statistics
        >>> stats = get_core_system_statistics()
        >>> print(f"System configured: {stats['is_configured']}")
        >>> print(f"Active fiscal year: {stats['fiscal']['active_year']['name']}")
    """
    try:
        return {
            'is_configured': True,
            'timestamp': get_school_current_time(),
            'school_config': get_school_configuration_summary(),
            'financial_settings': get_financial_settings_summary(),
            'account_mappings': get_account_mappings_status(),
            'fiscal_years': get_fiscal_year_statistics(),
            'fiscal_periods': get_fiscal_period_statistics(),
            'payment_methods': get_payment_method_statistics(),
            'tax_rates': get_tax_rate_statistics(),
            'units_of_measure': get_unit_of_measure_statistics(),
        }
        
    except Exception as e:
        logger.error(f"Error getting core system statistics: {e}")
        return {
            'error': str(e),
            'is_configured': False,
        }


def get_configuration_completeness():
    """
    Check completeness of system configuration.
    
    Returns:
        dict: Configuration completeness status with percentage
    
    Example:
        >>> from core.stats import get_configuration_completeness
        >>> completeness = get_configuration_completeness()
        >>> print(f"Configuration: {completeness['percentage']}% complete")
        >>> for item in completeness['incomplete_items']:
        >>>     print(f"Missing: {item}")
    """
    try:
        incomplete_items = []
        total_checks = 0
        completed_checks = 0
        
        # Check school configuration
        total_checks += 1
        config = get_school_configuration_summary()
        if config.get('is_configured'):
            completed_checks += 1
        else:
            incomplete_items.append('School Configuration')
        
        # Check financial settings
        total_checks += 1
        fin_settings = get_financial_settings_summary()
        if fin_settings.get('is_configured'):
            completed_checks += 1
        else:
            incomplete_items.append('Financial Settings')
        
        # Check account mappings
        total_checks += 5  # 5 mapping categories
        mappings = get_account_mappings_status()
        for category, status in mappings.items():
            if category != 'error':
                if status.get('completion_percentage', 0) >= 80:  # 80% threshold
                    completed_checks += 1
                else:
                    incomplete_items.append(f'{category.title()} Account Mappings')
        
        # Check fiscal year
        total_checks += 1
        fiscal_stats = get_fiscal_year_statistics()
        if fiscal_stats.get('active_year'):
            completed_checks += 1
        else:
            incomplete_items.append('Active Fiscal Year')
        
        # Check payment methods
        total_checks += 1
        payment_stats = get_payment_method_statistics()
        if payment_stats.get('active_count', 0) > 0:
            completed_checks += 1
        else:
            incomplete_items.append('Payment Methods')
        
        # Calculate percentage
        percentage = calculate_percentage(completed_checks, total_checks)
        
        return {
            'percentage': float(percentage),
            'completed_checks': completed_checks,
            'total_checks': total_checks,
            'incomplete_items': incomplete_items,
            'is_complete': percentage >= 90,  # 90% threshold
            'is_operational': percentage >= 70,  # 70% threshold for basic operations
        }
        
    except Exception as e:
        logger.error(f"Error checking configuration completeness: {e}")
        return {
            'error': str(e),
            'percentage': 0,
            'is_complete': False,
        }


# =============================================================================
# QUICK ACCESS FUNCTIONS
# =============================================================================

def get_current_fiscal_info():
    """
    Quick access to current fiscal year and period information.
    
    Returns:
        dict: Current fiscal year and period details
    
    Example:
        >>> from core.stats import get_current_fiscal_info
        >>> info = get_current_fiscal_info()
        >>> print(f"Current Year: {info['year']['name']}")
        >>> print(f"Current Period: {info['period']['name']}")
    """
    return {
        'year': get_active_fiscal_year(),
        'period': get_active_fiscal_period(),
        'academic_session': get_active_academic_session(),
        'today': get_school_today(),
    }


def get_payment_statistics_summary():
    """
    Quick summary of payment-related statistics.
    
    Returns:
        dict: Payment methods and tax rate summary
    
    Example:
        >>> from core.stats import get_payment_statistics_summary
        >>> summary = get_payment_statistics_summary()
        >>> print(f"Active methods: {summary['active_methods']}")
    """
    payment_stats = get_payment_method_statistics()
    tax_stats = get_tax_rate_statistics()
    
    return {
        'active_methods': payment_stats.get('active_count', 0),
        'default_method': payment_stats.get('default_method'),
        'active_tax_rates': tax_stats.get('active_count', 0),
        'effective_tax_rates': tax_stats.get('effective_count', 0),
    }