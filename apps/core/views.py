# core/views.py

"""
Core Configuration Views

What lives here
---------------
- Dashboard
- School Configuration (edit)
- Financial Settings (edit + account mappings)
- Fiscal Management combined accordion view
- Fiscal Year  : detail + print only
- Fiscal Period: detail + print only
- Payment Method : full CRUD + HTMX search
- Tax Rate       : full CRUD + HTMX search
- Unit of Measure: full CRUD + HTMX search
- JSON quick-stats endpoints

Removed vs. previous version
-----------------------------
- fiscal_year_list / create / edit / get_filtered_fiscal_years
- fiscal_period_list / create / edit / get_filtered_fiscal_periods
  All of the above are now handled by fiscal_management_view + modal endpoints.
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count, Sum, Prefetch
from django.http import JsonResponse
from django.core.exceptions import ValidationError
from django.views.decorators.http import require_http_methods
from datetime import timedelta
import logging

from .utils import (
    get_school_today,
    get_school_current_time,
    paginate_queryset,
)

from .models import (
    SchoolConfiguration,
    FinancialSettings,
    CoreAccountMappings,
    RevenueAccountMappings,
    PayrollAccountMappings,
    ExpenseAccountMappings,
    SpecialAccountMappings,
    FiscalYear,
    FiscalPeriod,
    PaymentMethod,
    TaxRate,
    UnitOfMeasure,
)

from .forms import (
    SchoolConfigurationForm,
    FinancialSettingsForm,
    CoreAccountMappingsForm,
    RevenueAccountMappingsForm,
    PayrollAccountMappingsForm,
    ExpenseAccountMappingsForm,
    SpecialAccountMappingsForm,
    PaymentMethodForm,
    PaymentMethodFilterForm,
    TaxRateForm,
    TaxRateFilterForm,
    UnitOfMeasureForm,
    UnitOfMeasureFilterForm,
)

from . import stats as core_stats

logger = logging.getLogger(__name__)


# =============================================================================
# DASHBOARD
# =============================================================================

@login_required
def core_dashboard(request):
    """Main core system dashboard."""

    try:
        system_stats  = core_stats.get_core_system_statistics()
        completeness  = core_stats.get_configuration_completeness()
        fiscal_info   = core_stats.get_current_fiscal_info()
        payment_stats = core_stats.get_payment_statistics_summary()
    except Exception as e:
        logger.error(f"Dashboard statistics error: {e}")
        system_stats  = {}
        completeness  = {'percentage': 0, 'is_complete': False}
        fiscal_info   = {}
        payment_stats = {}

    today = get_school_today()

    return render(request, 'core/home.html', {
        'system_stats':  system_stats,
        'completeness':  completeness,
        'fiscal_info':   fiscal_info,
        'payment_stats': payment_stats,
        'fiscal_years_ending': FiscalYear.objects.filter(
            end_date__gte=today,
            end_date__lte=today + timedelta(days=30),
            is_active=True,
        ).order_by('end_date')[:5],
        'periods_needing_closure': FiscalPeriod.objects.filter(
            end_date__lt=today,
            is_closed=False,
            is_active=True,
        ).order_by('end_date')[:5],
        'tax_rates_expiring': TaxRate.objects.filter(
            effective_to__gte=today,
            effective_to__lte=today + timedelta(days=60),
            is_active=True,
        ).order_by('effective_to')[:5],
        'inactive_payment_methods': PaymentMethod.objects.filter(is_active=False).count(),
    })


# =============================================================================
# SCHOOL CONFIGURATION
# =============================================================================

@login_required
def school_configuration_edit(request):
    config = SchoolConfiguration.get_instance()

    if request.method == 'POST':
        form = SchoolConfigurationForm(request.POST, instance=config)
        if form.is_valid():
            try:
                config = form.save()
                SchoolConfiguration.clear_cache()
                messages.success(request, 'School configuration updated successfully!')
            except Exception as e:
                logger.error(f"Configuration update error: {e}")
                messages.error(request, f'Error: {str(e)}')
    else:
        form = SchoolConfigurationForm(instance=config)

    return render(request, 'core/configuration/school_config.html', {
        'form': form,
        'config': config,
        'title': 'Edit School Configuration',
        'submit_text': 'Update Configuration',
    })


# =============================================================================
# FINANCIAL SETTINGS
# =============================================================================

@login_required
def financial_settings_edit(request):
    settings = FinancialSettings.get_instance()

    if request.method == 'POST':
        form = FinancialSettingsForm(request.POST, instance=settings)
        if form.is_valid():
            try:
                settings = form.save()
                messages.success(request, 'Financial settings updated successfully!')
            except Exception as e:
                logger.error(f"Financial settings error: {e}")
                messages.error(request, f'Error: {str(e)}')
    else:
        form = FinancialSettingsForm(instance=settings)

    return render(request, 'core/configuration/financial_settings.html', {
        'form': form,
        'settings': settings,
        'title': 'Edit Financial Settings',
        'submit_text': 'Update Settings',
    })


@login_required
def account_mappings_edit(request, mapping_type):
    settings = FinancialSettings.get_instance()

    mapping_config = {
        'core':    {'form_class': CoreAccountMappingsForm,    'get_method': 'get_account_mappings', 'title': 'Core Account Mappings'},
        'revenue': {'form_class': RevenueAccountMappingsForm, 'get_method': 'get_revenue_mappings', 'title': 'Revenue Account Mappings'},
        'payroll': {'form_class': PayrollAccountMappingsForm, 'get_method': 'get_payroll_mappings', 'title': 'Payroll Account Mappings'},
        'expense': {'form_class': ExpenseAccountMappingsForm, 'get_method': 'get_expense_mappings', 'title': 'Expense Account Mappings'},
        'special': {'form_class': SpecialAccountMappingsForm, 'get_method': 'get_special_mappings', 'title': 'Special Account Mappings'},
    }

    if mapping_type not in mapping_config:
        messages.error(request, 'Invalid mapping type.')
        return redirect('core:financial_settings_edit')

    cfg              = mapping_config[mapping_type]
    mapping_instance = getattr(settings, cfg['get_method'])()

    if request.method == 'POST':
        form = cfg['form_class'](request.POST, instance=mapping_instance)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, f'{cfg["title"]} updated successfully!')
                return redirect('core:financial_settings_edit')
            except Exception as e:
                logger.error(f"Mappings update error: {e}")
                messages.error(request, f'Error: {str(e)}')
    else:
        form = cfg['form_class'](instance=mapping_instance)

    return render(request, 'core/configuration/mappings_form.html', {
        'form': form,
        'mapping_type': mapping_type,
        'title': f'Edit {cfg["title"]}',
        'submit_text': 'Update Mappings',
    })


# =============================================================================
# FISCAL MANAGEMENT — combined accordion view
# =============================================================================

@login_required
def fiscal_management_view(request):
    """
    Single page showing all fiscal years with periods nested inside.
    Stats are computed here directly so the template never depends on
    external stats functions whose key names may differ.
    """

    fiscal_years = FiscalYear.objects.annotate(
        period_count=Count('fiscal_periods', distinct=True),
    ).prefetch_related(
        Prefetch(
            'fiscal_periods',
            queryset=FiscalPeriod.objects.select_related(
                'related_academic_session'
            ).order_by('period_number'),
            to_attr='prefetched_periods',
        )
    ).order_by('-start_date')

    # Compute stats directly — keys are guaranteed to match the template
    fy_agg = FiscalYear.objects.aggregate(
        total=Count('id'),
        active=Count('id', filter=Q(is_active=True)),
        closed=Count('id', filter=Q(is_closed=True)),
        locked=Count('id', filter=Q(is_locked=True)),
        draft=Count('id', filter=Q(status='DRAFT')),
    )

    period_agg = FiscalPeriod.objects.aggregate(
        total=Count('id'),
        active=Count('id', filter=Q(is_active=True)),
        closed=Count('id', filter=Q(is_closed=True)),
        locked=Count('id', filter=Q(is_locked=True)),
    )

    return render(request, 'core/fiscal_management.html', {
        'fiscal_years':  fiscal_years,
        'fy_stats':      fy_agg,
        'period_stats':  period_agg,
    })


# =============================================================================
# FISCAL YEAR — detail + print
# =============================================================================

@login_required
def fiscal_year_detail(request, pk):
    fiscal_year = get_object_or_404(
        FiscalYear.objects.prefetch_related(
            Prefetch(
                'fiscal_periods',
                queryset=FiscalPeriod.objects.select_related(
                    'related_academic_session'
                ).order_by('period_number'),
                to_attr='prefetched_periods',
            )
        ),
        pk=pk,
    )

    return render(request, 'core/fiscal_years/detail.html', {
        'fiscal_year': fiscal_year,
        'periods':     fiscal_year.prefetched_periods,
        'today':       get_school_today(),
    })


@login_required
def fiscal_year_print_view(request):
    selected_fields = request.GET.getlist('fields') or [
        'name', 'code', 'start_date', 'end_date', 'status', 'is_active',
    ]
    include_stats  = request.GET.get('include_stats') == 'true'
    landscape_mode = request.GET.get('landscape') == 'true'

    fiscal_years = FiscalYear.objects.annotate(
        period_count=Count('fiscal_periods', distinct=True),
    ).order_by('-start_date')

    query  = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    if query:
        fiscal_years = fiscal_years.filter(
            Q(name__icontains=query) | Q(code__icontains=query)
        )
    if status:
        fiscal_years = fiscal_years.filter(status=status)

    rows = [{
        'obj':                 fy,
        'duration_days':       fy.get_duration_days(),
        'progress_percentage': fy.get_progress_percentage(),
        'period_count':        fy.period_count,
    } for fy in fiscal_years]

    return render(request, 'core/fiscal_years/print.html', {
        'rows': rows,
        'stats': {
            'total':  fiscal_years.count(),
            'active': fiscal_years.filter(is_active=True).count(),
            'closed': fiscal_years.filter(is_closed=True).count(),
            'locked': fiscal_years.filter(is_locked=True).count(),
        } if include_stats else None,
        'now': get_school_current_time(),
        'selected_fields': selected_fields,
        'field_labels': {
            'name': 'Fiscal Year', 'code': 'Code',
            'start_date': 'Start Date', 'end_date': 'End Date',
            'status': 'Status', 'is_active': 'Active',
            'is_closed': 'Closed', 'is_locked': 'Locked',
            'period_count': 'Periods',
            'duration_days': 'Duration (Days)',
            'progress_percentage': 'Progress %',
        },
        'landscape': landscape_mode,
        'title': 'Fiscal Years Report',
    })


# =============================================================================
# FISCAL PERIOD — detail + print
# =============================================================================

@login_required
def fiscal_period_detail(request, pk):
    period = get_object_or_404(
        FiscalPeriod.objects.select_related('fiscal_year', 'related_academic_session'),
        pk=pk,
    )

    return render(request, 'core/fiscal_periods/detail.html', {
        'period': period,
        'progress_info': {
            'days_elapsed':            period.get_elapsed_days(),
            'days_remaining':          period.get_remaining_days(),
            'total_days':              period.get_duration_days(),
            'progress_percentage':     period.get_progress_percentage(),
            'is_current':              period.is_current(),
            'is_upcoming':             period.is_upcoming(),
            'is_past':                 period.is_past(),
            'is_in_grace_period':      period.is_in_grace_period(),
            'can_accept_transactions': period.can_accept_transactions(),
        },
        'today': get_school_today(),
    })


@login_required
def fiscal_period_print_view(request):
    selected_fields = request.GET.getlist('fields') or [
        'name', 'code', 'period_number', 'period_type',
        'start_date', 'end_date', 'status',
    ]
    include_stats = request.GET.get('include_stats') == 'true'

    periods = FiscalPeriod.objects.select_related(
        'fiscal_year', 'related_academic_session'
    ).order_by('-fiscal_year__start_date', 'period_number')

    query          = request.GET.get('q', '').strip()
    fiscal_year_id = request.GET.get('fiscal_year', '').strip()
    if query:
        periods = periods.filter(
            Q(name__icontains=query) | Q(code__icontains=query)
        )
    if fiscal_year_id:
        periods = periods.filter(fiscal_year_id=fiscal_year_id)

    rows = [{
        'obj':                 p,
        'duration_days':       p.get_duration_days(),
        'duration_weeks':      p.get_duration_weeks(),
        'progress_percentage': p.get_progress_percentage(),
        'elapsed_days':        p.get_elapsed_days(),
        'remaining_days':      p.get_remaining_days(),
    } for p in periods]

    return render(request, 'core/fiscal_periods/print.html', {
        'rows': rows,
        'stats': {
            'total':  len(rows),
            'active': periods.filter(is_active=True).count(),
            'closed': periods.filter(is_closed=True).count(),
        } if include_stats else None,
        'now': get_school_current_time(),
        'selected_fields': selected_fields,
        'field_labels': {
            'name': 'Period Name', 'code': 'Code',
            'period_number': '#', 'period_type': 'Type',
            'start_date': 'Start Date', 'end_date': 'End Date',
            'status': 'Status', 'duration_days': 'Duration (Days)',
            'progress_percentage': 'Progress %',
        },
        'title': 'Fiscal Periods Report',
    })


# =============================================================================
# PAYMENT METHOD — filter helper + full CRUD + HTMX search
# =============================================================================

def get_filtered_payment_methods(request):
    """Pure queryset builder — no rendering, no pagination."""

    methods = PaymentMethod.objects.all().order_by('display_order', 'name')

    query               = request.GET.get('q', '').strip()
    method_type         = request.GET.get('method_type', '').strip()
    is_active           = request.GET.get('is_active', '').strip()
    is_default          = request.GET.get('is_default', '').strip()
    requires_approval   = request.GET.get('requires_approval', '').strip()
    has_transaction_fee = request.GET.get('has_transaction_fee', '').strip()
    mobile_provider     = request.GET.get('mobile_money_provider', '').strip()

    if query:
        methods = methods.filter(
            Q(name__icontains=query) | Q(code__icontains=query) |
            Q(bank_name__icontains=query) | Q(instructions__icontains=query)
        )
    if method_type:
        methods = methods.filter(method_type=method_type)
    if mobile_provider:
        methods = methods.filter(mobile_money_provider=mobile_provider)
    if is_active:
        methods = methods.filter(is_active=(is_active.lower() == 'true'))
    if is_default:
        methods = methods.filter(is_default=(is_default.lower() == 'true'))
    if requires_approval:
        methods = methods.filter(requires_approval=(requires_approval.lower() == 'true'))
    if has_transaction_fee:
        methods = methods.filter(has_transaction_fee=(has_transaction_fee.lower() == 'true'))

    return methods


@login_required
def payment_method_list(request):
    is_htmx     = request.headers.get('HX-Request') == 'true'
    filter_form = PaymentMethodFilterForm(request.GET or None)
    methods     = get_filtered_payment_methods(request)

    # Stats on a clean queryset so annotations don't interfere with aggregate()
    stats_qs = PaymentMethod.objects.all()
    q = request.GET.get('q', '').strip()
    if q:
        stats_qs = stats_qs.filter(Q(name__icontains=q) | Q(code__icontains=q))

    stats = stats_qs.aggregate(
        total=Count('id'),
        active=Count('id', filter=Q(is_active=True)),
        cash=Count('id', filter=Q(method_type='CASH')),
        mobile_money=Count('id', filter=Q(method_type='MOBILE_MONEY')),
        bank_transfer=Count('id', filter=Q(method_type='BANK_TRANSFER')),
        with_fees=Count('id', filter=Q(has_transaction_fee=True)),
        requires_approval=Count('id', filter=Q(requires_approval=True)),
    )

    methods_page, paginator = paginate_queryset(request, methods, per_page=20)

    context = {
        'payment_methods_page': methods_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }

    if is_htmx:
        return render(request, 'core/payment_methods/_method_results.html', context)
    return render(request, 'core/payment_methods/list.html', context)


@login_required
def payment_method_create(request):
    if request.method == 'POST':
        form = PaymentMethodForm(request.POST)
        if form.is_valid():
            try:
                method = form.save()
                messages.success(request, f'Payment method "{method.name}" created!')
                return redirect('core:payment_method_detail', pk=method.pk)
            except Exception as e:
                logger.error(f"Payment method create error: {e}")
                messages.error(request, f'Error: {str(e)}')
    else:
        form = PaymentMethodForm()

    return render(request, 'core/payment_methods/form.html', {
        'form': form, 'title': 'Create Payment Method', 'submit_text': 'Create Method',
    })


@login_required
def payment_method_detail(request, pk):
    method = get_object_or_404(PaymentMethod, pk=pk)

    try:
        usage_stats  = core_stats.get_payment_method_usage_stats(days=30)
        method_usage = usage_stats.get('by_method', {}).get(method.name, {})
    except Exception as e:
        logger.error(f"Payment method usage stats error: {e}")
        method_usage = {}

    return render(request, 'core/payment_methods/detail.html', {
        'method': method, 'method_usage': method_usage,
    })


@login_required
def payment_method_edit(request, pk):
    method = get_object_or_404(PaymentMethod, pk=pk)

    if request.method == 'POST':
        form = PaymentMethodForm(request.POST, instance=method)
        if form.is_valid():
            try:
                method = form.save()
                messages.success(request, f'Payment method "{method.name}" updated!')
                return redirect('core:payment_method_detail', pk=method.pk)
            except Exception as e:
                logger.error(f"Payment method edit error: {e}")
                messages.error(request, f'Error: {str(e)}')
    else:
        form = PaymentMethodForm(instance=method)

    return render(request, 'core/payment_methods/form.html', {
        'form': form, 'method': method,
        'title': f'Edit {method.name}', 'submit_text': 'Update Method',
    })


@login_required
def payment_method_print_view(request):
    return render(request, 'core/payment_methods/print.html', {
        'methods': get_filtered_payment_methods(request),
        'now': get_school_current_time(),
        'selected_fields': request.GET.getlist('fields') or [
            'name', 'code', 'method_type', 'is_active', 'requires_approval',
        ],
        'title': 'Payment Methods Report',
    })


# =============================================================================
# TAX RATE — filter helper + full CRUD + HTMX search
# =============================================================================

def get_filtered_tax_rates(request):
    """Pure queryset builder — no rendering, no pagination."""

    rates = TaxRate.objects.all().order_by('-effective_from', 'tax_type')

    query               = request.GET.get('q', '').strip()
    tax_type            = request.GET.get('tax_type', '').strip()
    is_active           = request.GET.get('is_active', '').strip()
    applies_to_fees     = request.GET.get('applies_to_fees', '').strip()
    applies_to_services = request.GET.get('applies_to_services', '').strip()
    start_date          = request.GET.get('start_date', '').strip()
    end_date            = request.GET.get('end_date', '').strip()

    if query:
        rates = rates.filter(
            Q(name__icontains=query) | Q(description__icontains=query) |
            Q(legal_reference__icontains=query)
        )
    if tax_type:
        rates = rates.filter(tax_type=tax_type)
    if is_active:
        rates = rates.filter(is_active=(is_active.lower() == 'true'))
    if applies_to_fees:
        rates = rates.filter(applies_to_fees=(applies_to_fees.lower() == 'true'))
    if applies_to_services:
        rates = rates.filter(applies_to_services=(applies_to_services.lower() == 'true'))
    if start_date:
        try:
            rates = rates.filter(effective_from__gte=start_date)
        except Exception:
            pass
    if end_date:
        try:
            rates = rates.filter(
                Q(effective_to__lte=end_date) | Q(effective_to__isnull=True)
            )
        except Exception:
            pass

    return rates


@login_required
def tax_rate_list(request):
    is_htmx     = request.headers.get('HX-Request') == 'true'
    filter_form = TaxRateFilterForm(request.GET or None)
    rates       = get_filtered_tax_rates(request)

    stats_qs = TaxRate.objects.all()
    q = request.GET.get('q', '').strip()
    if q:
        stats_qs = stats_qs.filter(Q(name__icontains=q))

    stats = stats_qs.aggregate(
        total=Count('id'),
        active=Count('id', filter=Q(is_active=True)),
        vat=Count('id', filter=Q(tax_type='VAT')),
        wht=Count('id', filter=Q(tax_type__startswith='WHT')),
        applies_to_fees=Count('id', filter=Q(applies_to_fees=True)),
        applies_to_services=Count('id', filter=Q(applies_to_services=True)),
    )

    rates_page, paginator = paginate_queryset(request, rates, per_page=20)

    context = {
        'tax_rates_page': rates_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }

    if is_htmx:
        return render(request, 'core/tax_rates/_rate_results.html', context)
    return render(request, 'core/tax_rates/list.html', context)


@login_required
def tax_rate_create(request):
    if request.method == 'POST':
        form = TaxRateForm(request.POST)
        if form.is_valid():
            try:
                rate = form.save()
                messages.success(request, f'Tax rate "{rate.name}" created!')
                return redirect('core:tax_rate_detail', pk=rate.pk)
            except Exception as e:
                logger.error(f"Tax rate create error: {e}")
                messages.error(request, f'Error: {str(e)}')
    else:
        form = TaxRateForm()

    return render(request, 'core/tax_rates/form.html', {
        'form': form, 'title': 'Create Tax Rate', 'submit_text': 'Create Rate',
    })


@login_required
def tax_rate_detail(request, pk):
    rate  = get_object_or_404(TaxRate, pk=pk)
    today = get_school_today()
    return render(request, 'core/tax_rates/detail.html', {
        'rate': rate, 'is_effective': rate.is_effective(today), 'today': today,
    })


@login_required
def tax_rate_edit(request, pk):
    rate = get_object_or_404(TaxRate, pk=pk)

    if request.method == 'POST':
        form = TaxRateForm(request.POST, instance=rate)
        if form.is_valid():
            try:
                rate = form.save()
                messages.success(request, f'Tax rate "{rate.name}" updated!')
                return redirect('core:tax_rate_detail', pk=rate.pk)
            except Exception as e:
                logger.error(f"Tax rate edit error: {e}")
                messages.error(request, f'Error: {str(e)}')
    else:
        form = TaxRateForm(instance=rate)

    return render(request, 'core/tax_rates/form.html', {
        'form': form, 'rate': rate,
        'title': f'Edit {rate.name}', 'submit_text': 'Update Rate',
    })


@login_required
def tax_rate_print_view(request):
    return render(request, 'core/tax_rates/print.html', {
        'rates': get_filtered_tax_rates(request),
        'now': get_school_current_time(),
        'selected_fields': request.GET.getlist('fields') or [
            'name', 'tax_type', 'rate', 'effective_from', 'effective_to', 'is_active',
        ],
        'title': 'Tax Rates Report',
    })


# =============================================================================
# UNIT OF MEASURE — filter helper + full CRUD + HTMX search
# =============================================================================

def get_filtered_units(request):
    """Pure queryset builder — no rendering, no pagination."""

    units = UnitOfMeasure.objects.select_related('base_unit').annotate(
        derived_units_count=Count('derived_units', distinct=True)
    ).order_by('uom_type', 'name')

    query         = request.GET.get('q', '').strip()
    uom_type      = request.GET.get('uom_type', '').strip()
    is_active     = request.GET.get('is_active', '').strip()
    is_base_unit  = request.GET.get('is_base_unit', '').strip()
    has_base_unit = request.GET.get('has_base_unit', '').strip()

    if query:
        units = units.filter(
            Q(name__icontains=query) | Q(abbreviation__icontains=query) |
            Q(symbol__icontains=query) | Q(description__icontains=query)
        )
    if uom_type:
        units = units.filter(uom_type=uom_type)
    if is_active:
        units = units.filter(is_active=(is_active.lower() == 'true'))
    if is_base_unit and is_base_unit.lower() == 'true':
        units = units.filter(base_unit__isnull=True)
    elif has_base_unit and has_base_unit.lower() == 'true':
        units = units.filter(base_unit__isnull=False)

    return units


@login_required
def unit_of_measure_list(request):
    is_htmx     = request.headers.get('HX-Request') == 'true'
    filter_form = UnitOfMeasureFilterForm(request.GET or None)
    units       = get_filtered_units(request)

    stats_qs = UnitOfMeasure.objects.all()
    q = request.GET.get('q', '').strip()
    if q:
        stats_qs = stats_qs.filter(
            Q(name__icontains=q) | Q(abbreviation__icontains=q)
        )

    stats = stats_qs.aggregate(
        total=Count('id'),
        active=Count('id', filter=Q(is_active=True)),
        base_units=Count('id', filter=Q(base_unit__isnull=True)),
        derived_units=Count('id', filter=Q(base_unit__isnull=False)),
        length=Count('id', filter=Q(uom_type='LENGTH')),
        weight=Count('id', filter=Q(uom_type='WEIGHT')),
        volume=Count('id', filter=Q(uom_type='VOLUME')),
        area=Count('id', filter=Q(uom_type='AREA')),
        quantity=Count('id', filter=Q(uom_type='QUANTITY')),
    )

    units_page, paginator = paginate_queryset(request, units, per_page=20)

    context = {
        'units_page': units_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }

    if is_htmx:
        return render(request, 'core/units/_unit_results.html', context)
    return render(request, 'core/units/list.html', context)


@login_required
def unit_of_measure_create(request):
    if request.method == 'POST':
        form = UnitOfMeasureForm(request.POST)
        if form.is_valid():
            try:
                unit = form.save()
                messages.success(request, f'Unit "{unit.name}" created!')
                return redirect('core:unit_of_measure_detail', pk=unit.pk)
            except Exception as e:
                logger.error(f"Unit create error: {e}")
                messages.error(request, f'Error: {str(e)}')
    else:
        form = UnitOfMeasureForm()

    return render(request, 'core/units/form.html', {
        'form': form, 'title': 'Create Unit of Measure', 'submit_text': 'Create Unit',
    })


@login_required
def unit_of_measure_detail(request, pk):
    unit = get_object_or_404(UnitOfMeasure, pk=pk)
    return render(request, 'core/units/detail.html', {
        'unit': unit,
        'conversion_examples': unit.get_conversion_examples(),
        'conversion_table':    unit.get_conversion_table(),
        'derived_units':       unit.get_all_derived_units(),
    })


@login_required
def unit_of_measure_edit(request, pk):
    unit = get_object_or_404(UnitOfMeasure, pk=pk)

    if request.method == 'POST':
        form = UnitOfMeasureForm(request.POST, instance=unit)
        if form.is_valid():
            try:
                unit = form.save()
                messages.success(request, f'Unit "{unit.name}" updated!')
                return redirect('core:unit_of_measure_detail', pk=unit.pk)
            except Exception as e:
                logger.error(f"Unit edit error: {e}")
                messages.error(request, f'Error: {str(e)}')
    else:
        form = UnitOfMeasureForm(instance=unit)

    return render(request, 'core/units/form.html', {
        'form': form, 'unit': unit,
        'title': f'Edit {unit.name}', 'submit_text': 'Update Unit',
    })


@login_required
def unit_of_measure_print_view(request):
    return render(request, 'core/units/print.html', {
        'units': get_filtered_units(request),
        'now': get_school_current_time(),
        'selected_fields': request.GET.getlist('fields') or [
            'name', 'abbreviation', 'uom_type',
            'base_unit', 'conversion_factor', 'is_active',
        ],
        'title': 'Units of Measure Report',
    })


# =============================================================================
# JSON QUICK-STATS
# =============================================================================

@login_required
@require_http_methods(["GET"])
def fiscal_year_quick_stats(request):
    current = FiscalYear.get_active_fiscal_year()
    return JsonResponse({
        'total':                 FiscalYear.objects.count(),
        'active':                FiscalYear.objects.filter(is_active=True).count(),
        'draft':                 FiscalYear.objects.filter(status='DRAFT').count(),
        'closed':                FiscalYear.objects.filter(is_closed=True).count(),
        'locked':                FiscalYear.objects.filter(is_locked=True).count(),
        'current_year_name':     current.name if current else None,
        'current_year_progress': current.get_progress_percentage() if current else 0,
    })


@login_required
@require_http_methods(["GET"])
def fiscal_period_quick_stats(request):
    current = FiscalPeriod.get_current_fiscal_period()
    return JsonResponse({
        'total':                   FiscalPeriod.objects.count(),
        'active':                  FiscalPeriod.objects.filter(is_active=True).count(),
        'closed':                  FiscalPeriod.objects.filter(is_closed=True).count(),
        'locked':                  FiscalPeriod.objects.filter(is_locked=True).count(),
        'current_period_name':     current.name if current else None,
        'current_period_progress': current.get_progress_percentage() if current else 0,
    })


@login_required
@require_http_methods(["GET"])
def payment_method_quick_stats(request):
    return JsonResponse({
        'total':         PaymentMethod.objects.filter(is_active=True).count(),
        'cash':          PaymentMethod.objects.filter(method_type='CASH', is_active=True).count(),
        'mobile_money':  PaymentMethod.objects.filter(method_type='MOBILE_MONEY', is_active=True).count(),
        'bank_transfer': PaymentMethod.objects.filter(method_type='BANK_TRANSFER', is_active=True).count(),
        'with_fees':     PaymentMethod.objects.filter(has_transaction_fee=True, is_active=True).count(),
    })


@login_required
@require_http_methods(["GET"])
def tax_rate_quick_stats(request):
    today = get_school_today()
    return JsonResponse({
        'total':            TaxRate.objects.filter(is_active=True).count(),
        'vat':              TaxRate.objects.filter(tax_type='VAT', is_active=True).count(),
        'current_vat_rate': float(TaxRate.get_vat_rate()),
        'effective_today':  TaxRate.objects.filter(
            is_active=True, effective_from__lte=today,
        ).filter(
            Q(effective_to__isnull=True) | Q(effective_to__gte=today)
        ).count(),
    })


@login_required
@require_http_methods(["GET"])
def unit_of_measure_quick_stats(request):
    return JsonResponse({
        'total':         UnitOfMeasure.objects.filter(is_active=True).count(),
        'base_units':    UnitOfMeasure.objects.filter(base_unit__isnull=True, is_active=True).count(),
        'derived_units': UnitOfMeasure.objects.filter(base_unit__isnull=False, is_active=True).count(),
        'length':        UnitOfMeasure.objects.filter(uom_type='LENGTH', is_active=True).count(),
        'weight':        UnitOfMeasure.objects.filter(uom_type='WEIGHT', is_active=True).count(),
        'volume':        UnitOfMeasure.objects.filter(uom_type='VOLUME', is_active=True).count(),
        'quantity':      UnitOfMeasure.objects.filter(uom_type='QUANTITY', is_active=True).count(),
    })


@login_required
@require_http_methods(["GET"])
def system_configuration_stats(request):
    school_config      = SchoolConfiguration.get_instance()
    financial_settings = FinancialSettings.get_instance()
    return JsonResponse({
        'term_system':      school_config.get_term_system_display() if school_config else 'Not Configured',
        'periods_per_year': school_config.get_period_count() if school_config else 0,
        'school_currency':  financial_settings.school_currency if financial_settings else 'UGX',
        'fiscal_years':     FiscalYear.objects.count(),
        'fiscal_periods':   FiscalPeriod.objects.count(),
        'payment_methods':  PaymentMethod.objects.filter(is_active=True).count(),
        'tax_rates':        TaxRate.objects.filter(is_active=True).count(),
        'units_of_measure': UnitOfMeasure.objects.filter(is_active=True).count(),
    })