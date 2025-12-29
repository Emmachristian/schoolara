# core/htmx_views.py

from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.db.models import Q, Count, Sum, Avg, F, DecimalField, Case, When
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from datetime import timedelta
from decimal import Decimal
import logging

from .models import (
    SchoolConfiguration,
    FinancialSettings,
    FiscalYear,
    FiscalPeriod,
    PaymentMethod,
    TaxRate,
    UnitOfMeasure
)
from utils.utils import parse_filters, paginate_queryset

logger = logging.getLogger(__name__)


# =============================================================================
# FISCAL YEAR SEARCH
# =============================================================================

def fiscal_year_search(request):
    """HTMX-compatible fiscal year search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'status', 'is_active', 'is_closed', 'is_locked',
        'start_year', 'end_year'
    ])
    
    query = filters['q']
    status = filters['status']
    is_active = filters['is_active']
    is_closed = filters['is_closed']
    is_locked = filters['is_locked']
    start_year = filters['start_year']
    end_year = filters['end_year']
    
    # Build queryset
    fiscal_years = FiscalYear.objects.annotate(
        period_count=Count('fiscal_periods', distinct=True),
        active_period_count=Count(
            'fiscal_periods',
            filter=Q(fiscal_periods__is_active=True),
            distinct=True
        )
    ).order_by('-start_date')
    
    # Apply text search
    if query:
        fiscal_years = fiscal_years.filter(
            Q(name__icontains=query) |
            Q(code__icontains=query) |
            Q(description__icontains=query)
        )
    
    # Apply filters
    if status:
        fiscal_years = fiscal_years.filter(status=status)
    
    if is_active is not None:
        fiscal_years = fiscal_years.filter(is_active=(is_active.lower() == 'true'))
    
    if is_closed is not None:
        fiscal_years = fiscal_years.filter(is_closed=(is_closed.lower() == 'true'))
    
    if is_locked is not None:
        fiscal_years = fiscal_years.filter(is_locked=(is_locked.lower() == 'true'))
    
    if start_year:
        try:
            fiscal_years = fiscal_years.filter(start_date__year__gte=int(start_year))
        except:
            pass
    
    if end_year:
        try:
            fiscal_years = fiscal_years.filter(end_date__year__lte=int(end_year))
        except:
            pass
    
    # Paginate
    fiscal_years_page, paginator = paginate_queryset(request, fiscal_years, per_page=20)
    
    # Calculate stats
    total = fiscal_years.count()
    
    stats = {
        'total': total,
        'active': fiscal_years.filter(is_active=True).count(),
        'draft': fiscal_years.filter(status='DRAFT').count(),
        'closed': fiscal_years.filter(is_closed=True).count(),
        'locked': fiscal_years.filter(is_locked=True).count(),
        'total_periods': fiscal_years.aggregate(Sum('period_count'))['period_count__sum'] or 0,
    }
    
    return render(request, 'core/fiscal_years/_fiscal_year_results.html', {
        'fiscal_years_page': fiscal_years_page,
        'stats': stats,
    })


# =============================================================================
# FISCAL PERIOD SEARCH
# =============================================================================

def fiscal_period_search(request):
    """HTMX-compatible fiscal period search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'fiscal_year', 'period_type', 'status', 'is_active',
        'is_closed', 'is_locked', 'start_date', 'end_date',
        'related_academic_session'
    ])
    
    query = filters['q']
    fiscal_year = filters['fiscal_year']
    period_type = filters['period_type']
    status = filters['status']
    is_active = filters['is_active']
    is_closed = filters['is_closed']
    is_locked = filters['is_locked']
    start_date = filters['start_date']
    end_date = filters['end_date']
    related_academic_session = filters['related_academic_session']
    
    # Build queryset
    periods = FiscalPeriod.objects.select_related(
        'fiscal_year',
        'related_academic_session'
    ).order_by('-fiscal_year__start_date', 'period_number')
    
    # Apply text search
    if query:
        periods = periods.filter(
            Q(name__icontains=query) |
            Q(code__icontains=query) |
            Q(description__icontains=query) |
            Q(notes__icontains=query)
        )
    
    # Apply filters
    if fiscal_year:
        periods = periods.filter(fiscal_year_id=fiscal_year)
    
    if period_type:
        periods = periods.filter(period_type=period_type)
    
    if status:
        periods = periods.filter(status=status)
    
    if related_academic_session:
        periods = periods.filter(related_academic_session_id=related_academic_session)
    
    if is_active is not None:
        periods = periods.filter(is_active=(is_active.lower() == 'true'))
    
    if is_closed is not None:
        periods = periods.filter(is_closed=(is_closed.lower() == 'true'))
    
    if is_locked is not None:
        periods = periods.filter(is_locked=(is_locked.lower() == 'true'))
    
    if start_date:
        periods = periods.filter(start_date__gte=start_date)
    
    if end_date:
        periods = periods.filter(end_date__lte=end_date)
    
    # Paginate
    periods_page, paginator = paginate_queryset(request, periods, per_page=20)
    
    # Calculate stats
    total = periods.count()
    
    stats = {
        'total': total,
        'active': periods.filter(is_active=True).count(),
        'closed': periods.filter(is_closed=True).count(),
        'locked': periods.filter(is_locked=True).count(),
        'academic_aligned': periods.filter(period_type='ACADEMIC_ALIGNED').count(),
        'break_period': periods.filter(period_type='BREAK_PERIOD').count(),
        'grace_period': periods.filter(period_type='GRACE_PERIOD').count(),
        'monthly': periods.filter(period_type='MONTHLY').count(),
        'quarterly': periods.filter(period_type='QUARTERLY').count(),
    }
    
    return render(request, 'core/fiscal_periods/_period_results.html', {
        'periods_page': periods_page,
        'stats': stats,
    })


# =============================================================================
# PAYMENT METHOD SEARCH
# =============================================================================

def payment_method_search(request):
    """HTMX-compatible payment method search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'method_type', 'is_active', 'is_default',
        'requires_approval', 'has_transaction_fee',
        'mobile_money_provider'
    ])
    
    query = filters['q']
    method_type = filters['method_type']
    is_active = filters['is_active']
    is_default = filters['is_default']
    requires_approval = filters['requires_approval']
    has_transaction_fee = filters['has_transaction_fee']
    mobile_money_provider = filters['mobile_money_provider']
    
    # Build queryset
    payment_methods = PaymentMethod.objects.all().order_by('display_order', 'name')
    
    # Apply text search
    if query:
        payment_methods = payment_methods.filter(
            Q(name__icontains=query) |
            Q(code__icontains=query) |
            Q(bank_name__icontains=query) |
            Q(instructions__icontains=query)
        )
    
    # Apply filters
    if method_type:
        payment_methods = payment_methods.filter(method_type=method_type)
    
    if mobile_money_provider:
        payment_methods = payment_methods.filter(mobile_money_provider=mobile_money_provider)
    
    if is_active is not None:
        payment_methods = payment_methods.filter(is_active=(is_active.lower() == 'true'))
    
    if is_default is not None:
        payment_methods = payment_methods.filter(is_default=(is_default.lower() == 'true'))
    
    if requires_approval is not None:
        payment_methods = payment_methods.filter(requires_approval=(requires_approval.lower() == 'true'))
    
    if has_transaction_fee is not None:
        payment_methods = payment_methods.filter(has_transaction_fee=(has_transaction_fee.lower() == 'true'))
    
    # Paginate
    payment_methods_page, paginator = paginate_queryset(request, payment_methods, per_page=20)
    
    # Calculate stats
    total = payment_methods.count()
    
    stats = {
        'total': total,
        'active': payment_methods.filter(is_active=True).count(),
        'cash': payment_methods.filter(method_type='CASH').count(),
        'mobile_money': payment_methods.filter(method_type='MOBILE_MONEY').count(),
        'bank_transfer': payment_methods.filter(method_type='BANK_TRANSFER').count(),
        'with_fees': payment_methods.filter(has_transaction_fee=True).count(),
        'requires_approval': payment_methods.filter(requires_approval=True).count(),
    }
    
    return render(request, 'core/payment_methods/_method_results.html', {
        'payment_methods_page': payment_methods_page,
        'stats': stats,
    })


# =============================================================================
# TAX RATE SEARCH
# =============================================================================

def tax_rate_search(request):
    """HTMX-compatible tax rate search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'tax_type', 'is_active', 'applies_to_fees',
        'applies_to_services', 'start_date', 'end_date'
    ])
    
    query = filters['q']
    tax_type = filters['tax_type']
    is_active = filters['is_active']
    applies_to_fees = filters['applies_to_fees']
    applies_to_services = filters['applies_to_services']
    start_date = filters['start_date']
    end_date = filters['end_date']
    
    # Build queryset
    tax_rates = TaxRate.objects.all().order_by('-effective_from', 'tax_type')
    
    # Apply text search
    if query:
        tax_rates = tax_rates.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(legal_reference__icontains=query)
        )
    
    # Apply filters
    if tax_type:
        tax_rates = tax_rates.filter(tax_type=tax_type)
    
    if is_active is not None:
        tax_rates = tax_rates.filter(is_active=(is_active.lower() == 'true'))
    
    if applies_to_fees is not None:
        tax_rates = tax_rates.filter(applies_to_fees=(applies_to_fees.lower() == 'true'))
    
    if applies_to_services is not None:
        tax_rates = tax_rates.filter(applies_to_services=(applies_to_services.lower() == 'true'))
    
    if start_date:
        tax_rates = tax_rates.filter(effective_from__gte=start_date)
    
    if end_date:
        tax_rates = tax_rates.filter(
            Q(effective_to__lte=end_date) | Q(effective_to__isnull=True)
        )
    
    # Paginate
    tax_rates_page, paginator = paginate_queryset(request, tax_rates, per_page=20)
    
    # Calculate stats
    total = tax_rates.count()
    
    stats = {
        'total': total,
        'active': tax_rates.filter(is_active=True).count(),
        'vat': tax_rates.filter(tax_type='VAT').count(),
        'wht': tax_rates.filter(tax_type__startswith='WHT').count(),
        'applies_to_fees': tax_rates.filter(applies_to_fees=True).count(),
        'applies_to_services': tax_rates.filter(applies_to_services=True).count(),
    }
    
    return render(request, 'core/tax_rates/_rate_results.html', {
        'tax_rates_page': tax_rates_page,
        'stats': stats,
    })


# =============================================================================
# UNIT OF MEASURE SEARCH
# =============================================================================

def unit_of_measure_search(request):
    """HTMX-compatible unit of measure search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'uom_type', 'is_active', 'is_base_unit',
        'has_base_unit'
    ])
    
    query = filters['q']
    uom_type = filters['uom_type']
    is_active = filters['is_active']
    is_base_unit = filters['is_base_unit']
    has_base_unit = filters['has_base_unit']
    
    # Build queryset
    units = UnitOfMeasure.objects.select_related(
        'base_unit'
    ).annotate(
        derived_units_count=Count('derived_units', distinct=True)
    ).order_by('uom_type', 'name')
    
    # Apply text search
    if query:
        units = units.filter(
            Q(name__icontains=query) |
            Q(abbreviation__icontains=query) |
            Q(symbol__icontains=query) |
            Q(description__icontains=query)
        )
    
    # Apply filters
    if uom_type:
        units = units.filter(uom_type=uom_type)
    
    if is_active is not None:
        units = units.filter(is_active=(is_active.lower() == 'true'))
    
    if is_base_unit and is_base_unit.lower() == 'true':
        units = units.filter(base_unit__isnull=True)
    
    if has_base_unit and has_base_unit.lower() == 'true':
        units = units.filter(base_unit__isnull=False)
    
    # Paginate
    units_page, paginator = paginate_queryset(request, units, per_page=20)
    
    # Calculate stats
    total = units.count()
    
    stats = {
        'total': total,
        'active': units.filter(is_active=True).count(),
        'base_units': units.filter(base_unit__isnull=True).count(),
        'derived_units': units.filter(base_unit__isnull=False).count(),
        'length': units.filter(uom_type='LENGTH').count(),
        'weight': units.filter(uom_type='WEIGHT').count(),
        'volume': units.filter(uom_type='VOLUME').count(),
        'area': units.filter(uom_type='AREA').count(),
        'quantity': units.filter(uom_type='QUANTITY').count(),
    }
    
    return render(request, 'core/units/_unit_results.html', {
        'units_page': units_page,
        'stats': stats,
    })


# =============================================================================
# QUICK STATS ENDPOINTS
# =============================================================================

@require_http_methods(["GET"])
def fiscal_year_quick_stats(request):
    """Get quick statistics for fiscal years"""
    
    current_year = FiscalYear.get_active_fiscal_year()
    
    stats = {
        'total': FiscalYear.objects.count(),
        'active': FiscalYear.objects.filter(is_active=True).count(),
        'draft': FiscalYear.objects.filter(status='DRAFT').count(),
        'closed': FiscalYear.objects.filter(is_closed=True).count(),
        'locked': FiscalYear.objects.filter(is_locked=True).count(),
        'current_year_name': current_year.name if current_year else None,
        'current_year_progress': current_year.get_progress_percentage() if current_year else 0,
    }
    
    return JsonResponse(stats)


@require_http_methods(["GET"])
def fiscal_period_quick_stats(request):
    """Get quick statistics for fiscal periods"""
    
    current_period = FiscalPeriod.get_current_fiscal_period()
    
    stats = {
        'total': FiscalPeriod.objects.count(),
        'active': FiscalPeriod.objects.filter(is_active=True).count(),
        'closed': FiscalPeriod.objects.filter(is_closed=True).count(),
        'locked': FiscalPeriod.objects.filter(is_locked=True).count(),
        'current_period_name': current_period.name if current_period else None,
        'current_period_progress': current_period.get_progress_percentage() if current_period else 0,
    }
    
    return JsonResponse(stats)


@require_http_methods(["GET"])
def payment_method_quick_stats(request):
    """Get quick statistics for payment methods"""
    
    stats = {
        'total': PaymentMethod.objects.filter(is_active=True).count(),
        'cash': PaymentMethod.objects.filter(method_type='CASH', is_active=True).count(),
        'mobile_money': PaymentMethod.objects.filter(method_type='MOBILE_MONEY', is_active=True).count(),
        'bank_transfer': PaymentMethod.objects.filter(method_type='BANK_TRANSFER', is_active=True).count(),
        'with_fees': PaymentMethod.objects.filter(has_transaction_fee=True, is_active=True).count(),
    }
    
    return JsonResponse(stats)


@require_http_methods(["GET"])
def tax_rate_quick_stats(request):
    """Get quick statistics for tax rates"""
    
    today = timezone.now().date()
    
    stats = {
        'total': TaxRate.objects.filter(is_active=True).count(),
        'vat': TaxRate.objects.filter(tax_type='VAT', is_active=True).count(),
        'current_vat_rate': float(TaxRate.get_vat_rate()),
        'effective_today': TaxRate.objects.filter(
            is_active=True,
            effective_from__lte=today
        ).filter(
            Q(effective_to__isnull=True) | Q(effective_to__gte=today)
        ).count(),
    }
    
    return JsonResponse(stats)


@require_http_methods(["GET"])
def unit_of_measure_quick_stats(request):
    """Get quick statistics for units of measure"""
    
    stats = {
        'total': UnitOfMeasure.objects.filter(is_active=True).count(),
        'base_units': UnitOfMeasure.objects.filter(base_unit__isnull=True, is_active=True).count(),
        'derived_units': UnitOfMeasure.objects.filter(base_unit__isnull=False, is_active=True).count(),
        'length': UnitOfMeasure.objects.filter(uom_type='LENGTH', is_active=True).count(),
        'weight': UnitOfMeasure.objects.filter(uom_type='WEIGHT', is_active=True).count(),
        'volume': UnitOfMeasure.objects.filter(uom_type='VOLUME', is_active=True).count(),
        'quantity': UnitOfMeasure.objects.filter(uom_type='QUANTITY', is_active=True).count(),
    }
    
    return JsonResponse(stats)


@require_http_methods(["GET"])
def system_configuration_stats(request):
    """Get system configuration overview statistics"""
    
    school_config = SchoolConfiguration.get_instance()
    financial_settings = FinancialSettings.get_instance()
    
    stats = {
        'term_system': school_config.get_term_system_display() if school_config else 'Not Configured',
        'periods_per_year': school_config.get_period_count() if school_config else 0,
        'school_currency': financial_settings.school_currency if financial_settings else 'UGX',
        'fiscal_years': FiscalYear.objects.count(),
        'fiscal_periods': FiscalPeriod.objects.count(),
        'payment_methods': PaymentMethod.objects.filter(is_active=True).count(),
        'tax_rates': TaxRate.objects.filter(is_active=True).count(),
        'units_of_measure': UnitOfMeasure.objects.filter(is_active=True).count(),
    }
    
    return JsonResponse(stats)