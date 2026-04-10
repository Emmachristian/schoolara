# core/stats.py

"""
Core statistics and analytics utilities for School Management System.
Provides comprehensive statistics for configuration, financial settings,
fiscal management, and system-wide metrics.

All date-based calculations use school timezone for consistency via
get_school_today() and get_school_current_time() from core.utils.

CORRECTIONS FROM PREVIOUS VERSION
----------------------------------
1. get_financial_settings_summary() and get_account_mappings_status():
   Fixed 'core_account_mappings' → 'account_mappings' to match the
   actual related_name on CoreAccountMappings.financial_settings.
   The old name was never a valid attribute, so core mappings always
   appeared unconfigured.

2. get_payment_method_usage_stats():
   Fixed 'from finance.models import Payment' → 'from fees.models import Payment'.
   Payment is defined in fees/models.py, not finance/models.py.

3. Removed FinancialSettings.load() calls — load() alias was removed from
   the model. All calls now use get_instance().
"""

from django.db.models import Count, Sum, Q, Avg
from datetime import timedelta
from decimal import Decimal
import logging

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
        dict: Configuration summary including term system, timezone, and settings.

    Example:
        >>> from core.stats import get_school_configuration_summary
        >>> config = get_school_configuration_summary()
        >>> print(f"Term System: {config['term_system']}")
        >>> print(f"Timezone: {config['timezone']}")
    """
    from core.models import SchoolConfiguration

    try:
        config = SchoolConfiguration.get_cached_instance()

        if not config:
            return {
                'error':         'School configuration not found',
                'is_configured': False,
            }

        return {
            'is_configured':               True,
            'term_system':                 config.get_term_system_display(),
            'term_system_code':            config.term_system,
            'periods_per_year':            config.get_period_count(),
            'period_type_name':            config.get_period_type_name(),
            'period_type_plural':          config.get_period_type_name_plural(),
            'timezone':                    config.operational_timezone,
            'timezone_display':            str(config.get_timezone()),
            'academic_year_type':          config.get_academic_year_type_display(),
            'academic_year_start_month':   config.academic_year_start_month,
            'academic_year_start_day':     config.academic_year_start_day,
            'regional_season_type':        config.get_regional_season_type_display(),
            'default_period_duration_weeks': config.default_period_duration_weeks,
            'enable_automatic_reminders':  config.enable_automatic_reminders,
            'enable_sms':                  config.enable_sms,
            'enable_email_notifications':  config.enable_email_notifications,
            'all_period_names':            config.get_all_period_names(),
        }

    except Exception as e:
        logger.error(f"Error getting school configuration summary: {e}")
        return {
            'error':         str(e),
            'is_configured': False,
        }


def get_period_naming_preview(config=None):
    """
    Get a preview of period names for the current configuration.

    Args:
        config: SchoolConfiguration instance (defaults to current)

    Returns:
        list[str]: Period names for display.

    Example:
        >>> from core.stats import get_period_naming_preview
        >>> names = get_period_naming_preview()
        >>> for name in names:
        >>>     print(name)
    """
    from core.models import SchoolConfiguration

    if config is None:
        config = SchoolConfiguration.get_cached_instance()

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
        dict: Financial settings including currency, payment terms, and policies.

    Example:
        >>> from core.stats import get_financial_settings_summary
        >>> settings = get_financial_settings_summary()
        >>> print(f"Currency: {settings['currency']}")
        >>> print(f"Payment Terms: {settings['payment_terms_days']} days")
    """
    from core.models import FinancialSettings

    try:
        settings = FinancialSettings.get_instance()

        if not settings:
            return {
                'error':         'Financial settings not found',
                'is_configured': False,
            }

        # Check account mappings existence via correct related_names.
        # CoreAccountMappings.financial_settings has related_name='account_mappings'.
        # All others match their field names.
        def _has_mapping(attr_name):
            """Safely check if a OneToOneField reverse accessor exists."""
            try:
                return bool(getattr(settings, attr_name))
            except Exception:
                return False

        has_core_mappings    = _has_mapping('account_mappings')
        has_revenue_mappings = _has_mapping('revenue_account_mappings')
        has_payroll_mappings = _has_mapping('payroll_account_mappings')
        has_expense_mappings = _has_mapping('expense_account_mappings')
        has_special_mappings = _has_mapping('special_account_mappings')

        return {
            'is_configured': True,

            # Currency
            'currency':              settings.school_currency,
            'currency_position':     settings.get_currency_position_display(),
            'decimal_places':        settings.decimal_places,
            'use_thousand_separator':settings.use_thousand_separator,

            # Numbering
            'invoice_prefix':            settings.invoice_prefix,
            'payment_prefix':            settings.payment_prefix,
            'receipt_prefix':            settings.receipt_prefix,
            'expense_prefix':            settings.expense_prefix,
            'include_year_in_numbers':   settings.include_year_in_invoice_number,

            # Payment terms
            'payment_terms_days':        settings.default_payment_terms_days,
            'late_fee_enabled':          settings.late_fee_enabled,
            'late_fee_percentage':       float(settings.late_fee_percentage),
            'grace_period_days':         settings.grace_period_days,
            'minimum_payment_amount':    float(settings.minimum_payment_amount),
            'allow_partial_payments':    settings.allow_partial_payments,

            # Scholarships & discounts
            'auto_apply_scholarships':          settings.auto_apply_scholarships,
            'scholarship_approval_required':    settings.scholarship_approval_required,
            'auto_apply_discounts':             settings.auto_apply_discounts,
            'discount_approval_required':       settings.discount_approval_required,
            'discount_approval_threshold':      float(settings.discount_approval_threshold),
            'early_payment_discount_enabled':   settings.early_payment_discount_enabled,
            'early_payment_discount_percentage':float(settings.early_payment_discount_percentage),
            'early_payment_discount_days':      settings.early_payment_discount_days,

            # Workflows
            'expense_approval_required':    settings.expense_approval_required,
            'expense_approval_limit':       float(settings.expense_approval_limit),
            'require_payment_confirmation': settings.require_payment_confirmation,
            'require_expense_receipts':     settings.require_expense_receipts,
            'require_purchase_orders':      settings.require_purchase_orders,

            # Communication
            'send_invoice_emails':        settings.send_invoice_emails,
            'send_payment_confirmations': settings.send_payment_confirmations,
            'send_overdue_reminders':     settings.send_overdue_reminders,
            'overdue_reminder_days':      settings.overdue_reminder_days,
            'send_sms_notifications':     settings.send_sms_notifications,

            # Tax & accounting
            'include_tax_in_prices':             settings.include_tax_in_prices,
            'default_tax_rate':                  float(settings.default_tax_rate),
            'multi_currency_enabled':            settings.multi_currency_enabled,
            'auto_generate_recurring_invoices':  settings.auto_generate_recurring_invoices,

            # Account mappings status
            'has_core_mappings':    has_core_mappings,
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
            'error':         str(e),
            'is_configured': False,
        }


def get_account_mappings_status():
    """
    Get the completion status of all account mapping categories.

    Returns:
        dict: Completion percentage and mapped/total field counts per category.
              Keys: 'core', 'revenue', 'payroll', 'expense', 'special'.

    Example:
        >>> from core.stats import get_account_mappings_status
        >>> status = get_account_mappings_status()
        >>> print(f"Core mappings: {status['core']['completion_percentage']}%")
    """
    from core.models import (
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

        def _get_mapping_status(mapping_attr):
            """
            Return completion metadata for one mapping category.

            Counts FK fields whose names end in '_account' as the total,
            then counts how many are non-null as 'mapped'.
            """
            try:
                mapping = getattr(settings, mapping_attr)
            except Exception:
                # RelatedObjectDoesNotExist or AttributeError — not configured
                return {
                    'exists':                False,
                    'completion_percentage': 0,
                    'mapped_count':          0,
                    'total_fields':          0,
                }

            if not mapping:
                return {
                    'exists':                False,
                    'completion_percentage': 0,
                    'mapped_count':          0,
                    'total_fields':          0,
                }

            total_fields  = 0
            mapped_fields = 0

            for field in mapping._meta.fields:
                # Count only FK account fields — the financial_settings FK
                # does not end in '_account' so it is correctly excluded.
                if field.name.endswith('_account'):
                    total_fields += 1
                    if getattr(mapping, field.name) is not None:
                        mapped_fields += 1

            completion = (
                (mapped_fields / total_fields * 100)
                if total_fields > 0
                else 0
            )

            return {
                'exists':                True,
                'completion_percentage': round(completion, 1),
                'mapped_count':          mapped_fields,
                'total_fields':          total_fields,
            }

        return {
            # CoreAccountMappings.financial_settings has related_name='account_mappings'
            # All other mapping models use their own name as the related_name.
            'core':    _get_mapping_status('account_mappings'),
            'revenue': _get_mapping_status('revenue_account_mappings'),
            'payroll': _get_mapping_status('payroll_account_mappings'),
            'expense': _get_mapping_status('expense_account_mappings'),
            'special': _get_mapping_status('special_account_mappings'),
        }

    except Exception as e:
        logger.error(f"Error getting account mappings status: {e}")
        return {'error': str(e)}


# =============================================================================
# FISCAL YEAR STATISTICS
# =============================================================================

def get_fiscal_year_statistics():
    """
    Get comprehensive fiscal year statistics using school timezone.

    Returns:
        dict: Counts, status breakdown, and active year details.

    Example:
        >>> from core.stats import get_fiscal_year_statistics
        >>> stats = get_fiscal_year_statistics()
        >>> print(f"Total Fiscal Years: {stats['total_count']}")
        >>> print(f"Active Year: {stats['active_year']['name']}")
    """
    from core.models import FiscalYear

    try:
        today         = get_school_today()
        fiscal_years  = FiscalYear.objects.all()

        total_count   = fiscal_years.count()
        active_count  = fiscal_years.filter(is_active=True).count()
        closed_count  = fiscal_years.filter(is_closed=True).count()
        locked_count  = fiscal_years.filter(is_locked=True).count()

        status_breakdown = {
            status_code: fiscal_years.filter(status=status_code).count()
            for status_code, _ in FiscalYear.STATUS_CHOICES
        }

        current_count = fiscal_years.filter(
            start_date__lte=today,
            end_date__gte=today,
        ).count()
        past_count    = fiscal_years.filter(end_date__lt=today).count()
        future_count  = fiscal_years.filter(start_date__gt=today).count()

        active_year     = get_active_fiscal_year()
        active_year_info= None

        if active_year:
            active_year_info = {
                'id':                  active_year.id,
                'name':                active_year.name,
                'code':                active_year.code,
                'start_date':          active_year.start_date,
                'end_date':            active_year.end_date,
                'duration_days':       active_year.get_duration_days(),
                'elapsed_days':        active_year.get_elapsed_days(),
                'remaining_days':      active_year.get_remaining_days(),
                'progress_percentage': active_year.get_progress_percentage(),
                'is_current':          active_year.is_current(),
                'period_count':        active_year.get_period_count(),
            }

        return {
            'total_count':    total_count,
            'active_count':   active_count,
            'closed_count':   closed_count,
            'locked_count':   locked_count,
            'current_count':  current_count,
            'past_count':     past_count,
            'future_count':   future_count,
            'status_breakdown': status_breakdown,
            'active_year':    active_year_info,
        }

    except Exception as e:
        logger.error(f"Error getting fiscal year statistics: {e}")
        return {
            'error':       str(e),
            'total_count': 0,
        }


def get_fiscal_year_timeline():
    """
    Get a timeline of past, current, and future fiscal years using school timezone.

    Returns:
        dict: Lists of serialised fiscal years under 'past', 'current', 'future'.

    Example:
        >>> from core.stats import get_fiscal_year_timeline
        >>> timeline = get_fiscal_year_timeline()
        >>> print(f"Past Years: {len(timeline['past'])}")
    """
    from core.models import FiscalYear

    try:
        today = get_school_today()

        past_years    = FiscalYear.objects.filter(
            end_date__lt=today
        ).order_by('-end_date')[:5]

        current_years = FiscalYear.objects.filter(
            start_date__lte=today,
            end_date__gte=today,
        ).order_by('start_date')

        future_years  = FiscalYear.objects.filter(
            start_date__gt=today
        ).order_by('start_date')[:5]

        def _serialise(year):
            return {
                'id':         year.id,
                'name':       year.name,
                'code':       year.code,
                'start_date': year.start_date,
                'end_date':   year.end_date,
                'status':     year.get_status_display(),
                'is_active':  year.is_active,
                'is_closed':  year.is_closed,
                'is_locked':  year.is_locked,
            }

        return {
            'past':    [_serialise(y) for y in past_years],
            'current': [_serialise(y) for y in current_years],
            'future':  [_serialise(y) for y in future_years],
        }

    except Exception as e:
        logger.error(f"Error getting fiscal year timeline: {e}")
        return {
            'error':   str(e),
            'past':    [],
            'current': [],
            'future':  [],
        }


# =============================================================================
# FISCAL PERIOD STATISTICS
# =============================================================================

def get_fiscal_period_statistics():
    """
    Get comprehensive fiscal period statistics using school timezone.

    Returns:
        dict: Counts, type breakdown, status breakdown, and current period details.

    Example:
        >>> from core.stats import get_fiscal_period_statistics
        >>> stats = get_fiscal_period_statistics()
        >>> print(f"Total Periods: {stats['total_count']}")
        >>> print(f"Active Period: {stats['current_period']['name']}")
    """
    from core.models import FiscalPeriod

    try:
        today   = get_school_today()
        periods = FiscalPeriod.objects.all()

        total_count  = periods.count()
        active_count = periods.filter(is_active=True).count()
        closed_count = periods.filter(is_closed=True).count()
        locked_count = periods.filter(is_locked=True).count()

        type_breakdown = {
            type_code: periods.filter(period_type=type_code).count()
            for type_code, _ in FiscalPeriod.PERIOD_TYPE_CHOICES
        }

        status_breakdown = {
            status_code: periods.filter(status=status_code).count()
            for status_code, _ in FiscalPeriod.STATUS_CHOICES
        }

        current_count = periods.filter(
            start_date__lte=today,
            end_date__gte=today,
        ).count()
        past_count    = periods.filter(end_date__lt=today).count()
        future_count  = periods.filter(start_date__gt=today).count()

        # Count periods currently in grace window
        grace_period_count = sum(
            1 for p in periods.filter(is_active=True)
            if p.is_in_grace_period()
        )

        current_period     = get_active_fiscal_period()
        current_period_info= None

        if current_period:
            current_period_info = {
                'id':                    current_period.id,
                'name':                  current_period.name,
                'code':                  current_period.code,
                'period_number':         float(current_period.period_number),
                'period_type':           current_period.get_period_type_display(),
                'start_date':            current_period.start_date,
                'end_date':              current_period.end_date,
                'duration_days':         current_period.get_duration_days(),
                'elapsed_days':          current_period.get_elapsed_days(),
                'remaining_days':        current_period.get_remaining_days(),
                'progress_percentage':   current_period.get_progress_percentage(),
                'can_accept_transactions': current_period.can_accept_transactions(),
                'is_in_grace_period':    current_period.is_in_grace_period(),
                'grace_period_days':     current_period.grace_period_days,
            }

        return {
            'total_count':       total_count,
            'active_count':      active_count,
            'closed_count':      closed_count,
            'locked_count':      locked_count,
            'current_count':     current_count,
            'past_count':        past_count,
            'future_count':      future_count,
            'grace_period_count':grace_period_count,
            'type_breakdown':    type_breakdown,
            'status_breakdown':  status_breakdown,
            'current_period':    current_period_info,
        }

    except Exception as e:
        logger.error(f"Error getting fiscal period statistics: {e}")
        return {
            'error':       str(e),
            'total_count': 0,
        }


def get_fiscal_periods_by_year(fiscal_year=None):
    """
    Get all fiscal periods for a specific fiscal year, grouped by status.

    Args:
        fiscal_year: FiscalYear instance or ID (defaults to the active year).

    Returns:
        dict: Periods grouped into 'active', 'closed', 'locked', 'draft',
              plus 'total_count'.

    Example:
        >>> from core.stats import get_fiscal_periods_by_year
        >>> periods = get_fiscal_periods_by_year()
        >>> print(f"Active Periods: {len(periods['active'])}")
    """
    from core.models import FiscalPeriod

    try:
        if fiscal_year is None:
            fiscal_year = get_active_fiscal_year()
            if fiscal_year is None:
                return {
                    'error':       'No fiscal year provided and no active year found',
                    'total_count': 0,
                }

        fiscal_year_id = (
            fiscal_year.id if hasattr(fiscal_year, 'id') else fiscal_year
        )

        periods = FiscalPeriod.objects.filter(
            fiscal_year_id=fiscal_year_id
        ).order_by('period_number')

        def _serialise(period):
            return {
                'id':            period.id,
                'name':          period.name,
                'code':          period.code,
                'period_number': float(period.period_number),
                'period_type':   period.get_period_type_display(),
                'start_date':    period.start_date,
                'end_date':      period.end_date,
                'status':        period.get_status_display(),
                'can_accept_transactions': period.can_accept_transactions(),
            }

        return {
            'total_count': periods.count(),
            'active':  [_serialise(p) for p in periods.filter(is_active=True)],
            'closed':  [_serialise(p) for p in periods.filter(is_closed=True, is_locked=False)],
            'locked':  [_serialise(p) for p in periods.filter(is_locked=True)],
            'draft':   [_serialise(p) for p in periods.filter(status='DRAFT')],
        }

    except Exception as e:
        logger.error(f"Error getting fiscal periods by year: {e}")
        return {
            'error':       str(e),
            'total_count': 0,
        }


# =============================================================================
# PAYMENT METHOD STATISTICS
# =============================================================================

def get_payment_method_statistics():
    """
    Get comprehensive payment method statistics.

    PaymentMethod is in core.models.

    Returns:
        dict: Counts, type breakdown, mobile money providers, and default method.

    Example:
        >>> from core.stats import get_payment_method_statistics
        >>> stats = get_payment_method_statistics()
        >>> print(f"Total Methods: {stats['total_count']}")
    """
    from core.models import PaymentMethod

    try:
        methods       = PaymentMethod.objects.all()
        total_count   = methods.count()
        active_count  = methods.filter(is_active=True).count()
        default_method= methods.filter(is_default=True).first()

        type_breakdown = {}
        for type_code, type_name in PaymentMethod.METHOD_TYPE_CHOICES:
            count = methods.filter(method_type=type_code, is_active=True).count()
            if count > 0:
                type_breakdown[type_code] = {'count': count, 'name': type_name}

        approval_required_count  = methods.filter(is_active=True, requires_approval=True).count()
        fee_methods_count        = methods.filter(is_active=True, has_transaction_fee=True).count()
        reference_required_count = methods.filter(is_active=True, requires_reference=True).count()

        mobile_money_providers = {}
        for method in methods.filter(method_type='MOBILE_MONEY', is_active=True):
            if method.mobile_money_provider:
                provider = method.get_mobile_money_provider_display()
                mobile_money_providers[provider] = (
                    mobile_money_providers.get(provider, 0) + 1
                )

        return {
            'total_count':              total_count,
            'active_count':             active_count,
            'inactive_count':           total_count - active_count,
            'type_breakdown':           type_breakdown,
            'approval_required_count':  approval_required_count,
            'fee_methods_count':        fee_methods_count,
            'reference_required_count': reference_required_count,
            'mobile_money_providers':   mobile_money_providers,
            'default_method': {
                'id':   default_method.id,
                'name': default_method.name,
                'code': default_method.code,
                'type': default_method.get_method_type_display(),
            } if default_method else None,
        }

    except Exception as e:
        logger.error(f"Error getting payment method statistics: {e}")
        return {
            'error':       str(e),
            'total_count': 0,
        }


def get_payment_method_usage_stats(days=30):
    """
    Get payment method usage statistics for recent transactions.

    Payment is in fees.models (not finance.models).

    Args:
        days: Number of days to analyse (default: 30)

    Returns:
        dict: Usage statistics by payment method.

    Example:
        >>> from core.stats import get_payment_method_usage_stats
        >>> usage = get_payment_method_usage_stats(days=30)
        >>> for method, stats in usage['by_method'].items():
        >>>     print(f"{method}: {stats['count']} payments")
    """
    from core.models import PaymentMethod

    try:
        today      = get_school_today()
        start_date = today - timedelta(days=days)

        try:
            # Payment is defined in fees/models.py
            from fees.models import Payment

            payments = Payment.objects.filter(
                payment_date__gte=start_date,
                payment_date__lte=today,
                status='COMPLETED',
                reversed=False,
                refunded=False,
            )

            total_payments = payments.count()
            total_amount   = (
                payments.aggregate(total=Sum('amount_in_school_currency'))['total']
                or Decimal('0.00')
            )

            by_method = {}
            for method in PaymentMethod.objects.filter(is_active=True):
                method_payments = payments.filter(payment_method=method)
                count  = method_payments.count()
                amount = (
                    method_payments.aggregate(
                        total=Sum('amount_in_school_currency')
                    )['total'] or Decimal('0.00')
                )

                if count > 0:
                    by_method[method.name] = {
                        'count':      count,
                        'amount':     float(amount),
                        'percentage': float(
                            calculate_percentage(count, total_payments)
                        ),
                    }

            return {
                'period_days':   days,
                'start_date':    start_date,
                'end_date':      today,
                'total_payments':total_payments,
                'total_amount':  float(total_amount),
                'by_method':     by_method,
            }

        except ImportError:
            logger.warning("fees.Payment model not found — cannot get usage stats")
            return {
                'error':          'Payment model not available',
                'total_payments': 0,
            }

    except Exception as e:
        logger.error(f"Error getting payment method usage stats: {e}")
        return {
            'error':          str(e),
            'total_payments': 0,
        }


# =============================================================================
# TAX RATE STATISTICS
# =============================================================================

def get_tax_rate_statistics():
    """
    Get comprehensive tax rate statistics using school timezone.

    Returns:
        dict: Counts, type breakdown, and currently active rates per type.

    Example:
        >>> from core.stats import get_tax_rate_statistics
        >>> stats = get_tax_rate_statistics()
        >>> print(f"Total Tax Rates: {stats['total_count']}")
    """
    from core.models import TaxRate

    try:
        today      = get_school_today()
        tax_rates  = TaxRate.objects.all()

        total_count  = tax_rates.count()
        active_count = tax_rates.filter(is_active=True).count()

        effective_count = tax_rates.filter(
            is_active=True,
            effective_from__lte=today,
        ).filter(
            Q(effective_to__isnull=True) | Q(effective_to__gte=today)
        ).count()

        type_breakdown = {}
        for type_code, type_name in TaxRate.TAX_TYPE_CHOICES:
            count = tax_rates.filter(tax_type=type_code).count()
            if count > 0:
                type_breakdown[type_code] = {'count': count, 'name': type_name}

        active_rates_by_type = {}
        for type_code, _ in TaxRate.TAX_TYPE_CHOICES:
            rate = TaxRate.get_active_rate(type_code, today)
            if rate:
                active_rates_by_type[type_code] = {
                    'id':             rate.id,
                    'name':           rate.name,
                    'rate':           float(rate.rate),
                    'effective_from': rate.effective_from,
                    'effective_to':   rate.effective_to,
                }

        fee_applicable_count     = tax_rates.filter(is_active=True, applies_to_fees=True).count()
        service_applicable_count = tax_rates.filter(is_active=True, applies_to_services=True).count()

        return {
            'total_count':         total_count,
            'active_count':        active_count,
            'effective_count':     effective_count,
            'inactive_count':      total_count - active_count,
            'type_breakdown':      type_breakdown,
            'fee_applicable_count':     fee_applicable_count,
            'service_applicable_count': service_applicable_count,
            'active_rates_by_type':     active_rates_by_type,
        }

    except Exception as e:
        logger.error(f"Error getting tax rate statistics: {e}")
        return {
            'error':       str(e),
            'total_count': 0,
        }


def get_tax_rate_history(tax_type=None, months=12):
    """
    Get historical tax rate changes using school timezone.

    Args:
        tax_type: Specific tax type to filter by (optional)
        months:   Number of months to look back (default: 12)

    Returns:
        list[dict]: Historical tax rate entries, newest first.

    Example:
        >>> from core.stats import get_tax_rate_history
        >>> history = get_tax_rate_history('VAT', months=24)
        >>> for change in history:
        >>>     print(f"{change['effective_from']}: {change['rate']}%")
    """
    from core.models import TaxRate

    try:
        today      = get_school_today()
        start_date = today - timedelta(days=months * 30)

        rates = TaxRate.objects.filter(
            effective_from__gte=start_date
        ).order_by('-effective_from')

        if tax_type:
            rates = rates.filter(tax_type=tax_type)

        return [
            {
                'id':             rate.id,
                'name':           rate.name,
                'tax_type':       rate.get_tax_type_display(),
                'rate':           float(rate.rate),
                'effective_from': rate.effective_from,
                'effective_to':   rate.effective_to,
                'is_active':      rate.is_active,
                'is_effective':   rate.is_effective(today),
            }
            for rate in rates
        ]

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
        dict: Counts, type breakdown, and most-used base units.

    Example:
        >>> from core.stats import get_unit_of_measure_statistics
        >>> stats = get_unit_of_measure_statistics()
        >>> print(f"Total Units: {stats['total_count']}")
        >>> print(f"Base Units: {stats['base_units_count']}")
    """
    from core.models import UnitOfMeasure

    try:
        units = UnitOfMeasure.objects.all()

        total_count        = units.count()
        active_count       = units.filter(is_active=True).count()
        base_units_count   = units.filter(base_unit__isnull=True,  is_active=True).count()
        derived_units_count= units.filter(base_unit__isnull=False, is_active=True).count()

        type_breakdown = {}
        for type_code, type_name in UnitOfMeasure.UOM_TYPE_CHOICES:
            count = units.filter(uom_type=type_code, is_active=True).count()
            if count > 0:
                type_breakdown[type_code] = {
                    'name':          type_name,
                    'total':         count,
                    'base_units':    units.filter(
                        uom_type=type_code, is_active=True,
                        base_unit__isnull=True
                    ).count(),
                    'derived_units': units.filter(
                        uom_type=type_code, is_active=True,
                        base_unit__isnull=False
                    ).count(),
                }

        # Top 5 base units by number of derived units
        base_units_usage = []
        for base_unit in units.filter(base_unit__isnull=True, is_active=True):
            derived_count = base_unit.get_derived_units_count()
            if derived_count > 0:
                base_units_usage.append({
                    'id':            base_unit.id,
                    'name':          base_unit.name,
                    'abbreviation':  base_unit.abbreviation,
                    'type':          base_unit.get_uom_type_display(),
                    'derived_count': derived_count,
                })

        base_units_usage.sort(key=lambda x: x['derived_count'], reverse=True)

        return {
            'total_count':          total_count,
            'active_count':         active_count,
            'inactive_count':       total_count - active_count,
            'base_units_count':     base_units_count,
            'derived_units_count':  derived_units_count,
            'type_breakdown':       type_breakdown,
            'most_used_base_units': base_units_usage[:5],
        }

    except Exception as e:
        logger.error(f"Error getting unit of measure statistics: {e}")
        return {
            'error':       str(e),
            'total_count': 0,
        }


def get_unit_conversion_examples(uom_type=None, limit=5):
    """
    Get example conversions for derived units.

    Args:
        uom_type: Specific UOM type to filter by (optional)
        limit:    Maximum number of examples (default: 5)

    Returns:
        list[dict]: Conversion examples with 'formatted' string.

    Example:
        >>> from core.stats import get_unit_conversion_examples
        >>> examples = get_unit_conversion_examples('LENGTH')
        >>> for ex in examples:
        >>>     print(ex['formatted'])
    """
    from core.models import UnitOfMeasure

    try:
        units = UnitOfMeasure.objects.filter(
            is_active=True,
            base_unit__isnull=False,
        )

        if uom_type:
            units = units.filter(uom_type=uom_type)

        units = units.order_by('uom_type', 'name')[:limit]

        return [
            example
            for unit in units
            for example in [unit.get_conversion_example(value=10)]
            if example
        ]

    except Exception as e:
        logger.error(f"Error getting unit conversion examples: {e}")
        return []


# =============================================================================
# SYSTEM-WIDE STATISTICS
# =============================================================================

def get_core_system_statistics():
    """
    Get comprehensive system-wide statistics by combining all core stats.

    Returns:
        dict: Complete system statistics with a UTC timestamp.

    Example:
        >>> from core.stats import get_core_system_statistics
        >>> stats = get_core_system_statistics()
        >>> print(f"System configured: {stats['is_configured']}")
    """
    try:
        return {
            'is_configured':    True,
            'timestamp':        get_school_current_time(),
            'school_config':    get_school_configuration_summary(),
            'financial_settings': get_financial_settings_summary(),
            'account_mappings': get_account_mappings_status(),
            'fiscal_years':     get_fiscal_year_statistics(),
            'fiscal_periods':   get_fiscal_period_statistics(),
            'payment_methods':  get_payment_method_statistics(),
            'tax_rates':        get_tax_rate_statistics(),
            'units_of_measure': get_unit_of_measure_statistics(),
        }

    except Exception as e:
        logger.error(f"Error getting core system statistics: {e}")
        return {
            'error':         str(e),
            'is_configured': False,
        }


def get_configuration_completeness():
    """
    Check the completeness of the system configuration and return
    a percentage score with a list of incomplete items.

    Thresholds:
        ≥90% → is_complete    = True
        ≥70% → is_operational = True (basic operations possible)

    Returns:
        dict: {
            'percentage':        float,
            'completed_checks':  int,
            'total_checks':      int,
            'incomplete_items':  list[str],
            'is_complete':       bool,
            'is_operational':    bool,
        }

    Example:
        >>> from core.stats import get_configuration_completeness
        >>> completeness = get_configuration_completeness()
        >>> print(f"Configuration: {completeness['percentage']}% complete")
        >>> for item in completeness['incomplete_items']:
        >>>     print(f"Missing: {item}")
    """
    try:
        incomplete_items  = []
        total_checks      = 0
        completed_checks  = 0

        # 1. School configuration
        total_checks += 1
        config = get_school_configuration_summary()
        if config.get('is_configured'):
            completed_checks += 1
        else:
            incomplete_items.append('School Configuration')

        # 2. Financial settings
        total_checks += 1
        fin_settings = get_financial_settings_summary()
        if fin_settings.get('is_configured'):
            completed_checks += 1
        else:
            incomplete_items.append('Financial Settings')

        # 3. Account mapping categories (5 categories, 80% threshold each)
        total_checks += 5
        mappings = get_account_mappings_status()

        category_labels = {
            'core':    'Core Account Mappings',
            'revenue': 'Revenue Account Mappings',
            'payroll': 'Payroll Account Mappings',
            'expense': 'Expense Account Mappings',
            'special': 'Special Account Mappings',
        }

        for category_key, label in category_labels.items():
            status = mappings.get(category_key, {})
            if not isinstance(status, dict) or status.get('error'):
                incomplete_items.append(label)
            elif status.get('completion_percentage', 0) >= 80:
                completed_checks += 1
            else:
                incomplete_items.append(label)

        # 4. Active fiscal year
        total_checks += 1
        fiscal_stats = get_fiscal_year_statistics()
        if fiscal_stats.get('active_year'):
            completed_checks += 1
        else:
            incomplete_items.append('Active Fiscal Year')

        # 5. Payment methods
        total_checks += 1
        payment_stats = get_payment_method_statistics()
        if payment_stats.get('active_count', 0) > 0:
            completed_checks += 1
        else:
            incomplete_items.append('Payment Methods')

        percentage = float(calculate_percentage(completed_checks, total_checks))

        return {
            'percentage':       percentage,
            'completed_checks': completed_checks,
            'total_checks':     total_checks,
            'incomplete_items': incomplete_items,
            'is_complete':      percentage >= 90,
            'is_operational':   percentage >= 70,
        }

    except Exception as e:
        logger.error(f"Error checking configuration completeness: {e}")
        return {
            'error':         str(e),
            'percentage':    0,
            'is_complete':   False,
            'is_operational':False,
        }


# =============================================================================
# QUICK ACCESS FUNCTIONS
# =============================================================================

def get_current_fiscal_info():
    """
    Quick access to current fiscal year, period, and academic session.

    Returns:
        dict with keys:
            year              (FiscalYear | None)
            period            (FiscalPeriod | None)
            academic_session  (AcademicSession | None)
            today             (date — school timezone)

    Example:
        >>> from core.stats import get_current_fiscal_info
        >>> info = get_current_fiscal_info()
        >>> print(f"Current Year: {info['year']}")
        >>> print(f"Current Period: {info['period']}")
    """
    return {
        'year':             get_active_fiscal_year(),
        'period':           get_active_fiscal_period(),
        'academic_session': get_active_academic_session(),
        'today':            get_school_today(),
    }


def get_payment_statistics_summary():
    """
    Quick summary combining payment method and tax rate statistics.

    Returns:
        dict with keys:
            active_methods      (int)
            default_method      (dict | None)
            active_tax_rates    (int)
            effective_tax_rates (int)

    Example:
        >>> from core.stats import get_payment_statistics_summary
        >>> summary = get_payment_statistics_summary()
        >>> print(f"Active methods: {summary['active_methods']}")
    """
    payment_stats = get_payment_method_statistics()
    tax_stats     = get_tax_rate_statistics()

    return {
        'active_methods':      payment_stats.get('active_count',    0),
        'default_method':      payment_stats.get('default_method',  None),
        'active_tax_rates':    tax_stats.get('active_count',        0),
        'effective_tax_rates': tax_stats.get('effective_count',     0),
    }