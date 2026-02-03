# core/views.py

"""
Core Configuration Views

Comprehensive view functions for:
- School Configuration (Read/Update)
- Financial Settings (Read/Update + Account Mappings)
- Fiscal Years (CRUD + Print)
- Fiscal Periods (CRUD + Print)
- Payment Methods (CRUD + Print)
- Tax Rates (CRUD + Print)
- Units of Measure (CRUD + Print)
- System Dashboard and Reports

All views delegate business logic to services.py (when needed)
Uses stats.py for comprehensive statistics and analytics
Uses SweetAlert2 for all notifications via Django messages
Uses core.utils for timezone-aware operations
Audit trail automatically handled by BaseModel
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count, Sum, Avg, Prefetch, F
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from django.db import transaction
from django.core.exceptions import ValidationError
from datetime import timedelta, date, datetime
from decimal import Decimal
import logging

# ⭐ Import timezone utilities from core
from .utils import (
    get_school_today,
    get_school_current_time,
    get_school_timezone,
    get_active_fiscal_year,
    get_active_fiscal_period,
    format_money,
    calculate_percentage,
    validate_date_range,
    paginate_queryset,
    parse_filters,
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
    FinancialSettingsQuickForm,
    CoreAccountMappingsForm,
    RevenueAccountMappingsForm,
    PayrollAccountMappingsForm,
    ExpenseAccountMappingsForm,
    SpecialAccountMappingsForm,
    FiscalYearForm,
    FiscalYearFilterForm,
    FiscalPeriodForm,
    FiscalPeriodFilterForm,
    PaymentMethodForm,
    PaymentMethodFilterForm,
    TaxRateForm,
    TaxRateFilterForm,
    UnitOfMeasureForm,
    UnitOfMeasureFilterForm,
)

# Import stats functions
from . import stats as core_stats

logger = logging.getLogger(__name__)


# =============================================================================
# SYSTEM DASHBOARD
# =============================================================================

@login_required
def core_dashboard(request):
    """Main core system dashboard with configuration overview"""
    
    try:
        # Get comprehensive system statistics
        system_stats = core_stats.get_core_system_statistics()
        
        # Get configuration completeness
        completeness = core_stats.get_configuration_completeness()
        
        # Get current fiscal info
        fiscal_info = core_stats.get_current_fiscal_info()
        
        # Get payment statistics
        payment_stats = core_stats.get_payment_statistics_summary()
        
    except Exception as e:
        logger.error(f"Error getting dashboard statistics: {e}")
        system_stats = {}
        completeness = {'percentage': 0, 'is_complete': False}
        fiscal_info = {}
        payment_stats = {}
    
    # Get items needing attention
    today = get_school_today()
    
    # Fiscal years ending soon
    fiscal_years_ending = FiscalYear.objects.filter(
        end_date__gte=today,
        end_date__lte=today + timedelta(days=30),
        is_active=True
    ).order_by('end_date')[:5]
    
    # Fiscal periods needing closure
    periods_needing_closure = FiscalPeriod.objects.filter(
        end_date__lt=today,
        is_closed=False,
        is_active=True
    ).order_by('end_date')[:5]
    
    # Tax rates expiring soon
    tax_rates_expiring = TaxRate.objects.filter(
        effective_to__gte=today,
        effective_to__lte=today + timedelta(days=60),
        is_active=True
    ).order_by('effective_to')[:5]
    
    # Inactive payment methods
    inactive_payment_methods = PaymentMethod.objects.filter(
        is_active=False
    ).count()
    
    context = {
        'system_stats': system_stats,
        'completeness': completeness,
        'fiscal_info': fiscal_info,
        'payment_stats': payment_stats,
        'fiscal_years_ending': fiscal_years_ending,
        'periods_needing_closure': periods_needing_closure,
        'tax_rates_expiring': tax_rates_expiring,
        'inactive_payment_methods': inactive_payment_methods,
    }
    
    return render(request, 'core/home.html', context)


# =============================================================================
# SCHOOL CONFIGURATION VIEWS
# =============================================================================

@login_required
def school_configuration_edit(request):
    """Edit school configuration"""
    
    config = SchoolConfiguration.get_instance()
    
    if request.method == 'POST':
        form = SchoolConfigurationForm(request.POST, instance=config)
        if form.is_valid():
            try:
                config = form.save()
                
                # Clear cache
                SchoolConfiguration.clear_cache()
                
                messages.success(
                    request,
                    'School configuration updated successfully!'
                )
                
            except Exception as e:
                logger.error(f"Error updating configuration: {e}")
                messages.error(request, f'Error updating configuration: {str(e)}')
    else:
        form = SchoolConfigurationForm(instance=config)
    
    context = {
        'form': form,
        'config': config,
        'title': 'Edit School Configuration',
        'submit_text': 'Update Configuration',
    }
    
    return render(request, 'core/configuration/school_config.html', context)

# =============================================================================
# FINANCIAL SETTINGS VIEWS
# =============================================================================

@login_required
def financial_settings_edit(request):
    """Edit financial settings"""
    
    settings = FinancialSettings.get_instance()
    
    if request.method == 'POST':
        form = FinancialSettingsForm(request.POST, instance=settings)
        if form.is_valid():
            try:
                settings = form.save()
                
                messages.success(
                    request,
                    'Financial settings updated successfully!'
                )
                
            except Exception as e:
                logger.error(f"Error updating financial settings: {e}")
                messages.error(request, f'Error: {str(e)}')
    else:
        form = FinancialSettingsForm(instance=settings)
    
    context = {
        'form': form,
        'settings': settings,
        'title': 'Edit Financial Settings',
        'submit_text': 'Update Settings',
    }
    
    return render(request, 'core/configuration/financial_settings.html', context)


@login_required
def account_mappings_edit(request, mapping_type):
    """Edit account mappings by type"""
    
    settings = FinancialSettings.get_instance()
    
    # Map types to forms and get/create methods
    mapping_config = {
        'core': {
            'form_class': CoreAccountMappingsForm,
            'get_method': 'get_account_mappings',
            'title': 'Core Account Mappings',
        },
        'revenue': {
            'form_class': RevenueAccountMappingsForm,
            'get_method': 'get_revenue_mappings',
            'title': 'Revenue Account Mappings',
        },
        'payroll': {
            'form_class': PayrollAccountMappingsForm,
            'get_method': 'get_payroll_mappings',
            'title': 'Payroll Account Mappings',
        },
        'expense': {
            'form_class': ExpenseAccountMappingsForm,
            'get_method': 'get_expense_mappings',
            'title': 'Expense Account Mappings',
        },
        'special': {
            'form_class': SpecialAccountMappingsForm,
            'get_method': 'get_special_mappings',
            'title': 'Special Account Mappings',
        },
    }
    
    if mapping_type not in mapping_config:
        messages.error(request, 'Invalid mapping type')
        return redirect('core:financial_settings_view')
    
    config = mapping_config[mapping_type]
    mapping_instance = getattr(settings, config['get_method'])()
    
    if request.method == 'POST':
        form = config['form_class'](request.POST, instance=mapping_instance)
        if form.is_valid():
            try:
                form.save()
                
                messages.success(
                    request,
                    f'{config["title"]} updated successfully!'
                )
                return redirect('core:financial_settings_edit')
                
            except Exception as e:
                logger.error(f"Error updating mappings: {e}")
                messages.error(request, f'Error: {str(e)}')
    else:
        form = config['form_class'](instance=mapping_instance)
    
    context = {
        'form': form,
        'mapping_type': mapping_type,
        'title': f'Edit {config["title"]}',
        'submit_text': 'Update Mappings',
    }
    
    return render(request, 'core/configuration/mappings_form.html', context)


# =============================================================================
# FISCAL YEAR VIEWS (CRUD + Print)
# =============================================================================

# core/views.py

@login_required
def fiscal_management_view(request):
    """
    Combined fiscal year and period management view.
    Displays all fiscal years with their periods in an accordion/selector style.
    """
    
    # Get all fiscal years with period counts
    fiscal_years = FiscalYear.objects.annotate(
        period_count=Count('fiscal_periods')
    ).prefetch_related('fiscal_periods').order_by('-start_date')
    
    # Get statistics
    try:
        from . import stats as core_stats
        fy_stats = core_stats.get_fiscal_year_statistics()
        period_stats = core_stats.get_fiscal_period_statistics()
    except Exception as e:
        logger.error(f"Error getting statistics: {e}")
        fy_stats = {}
        period_stats = {}
    
    context = {
        'fiscal_years': fiscal_years,
        'fy_stats': fy_stats,
        'period_stats': period_stats,
    }
    
    return render(request, 'core/fiscal_management.html', context)


@login_required
def fiscal_year_list(request):
    """List all fiscal years - HTMX loads data on page load"""
    
    # Initialize filter form
    filter_form = FiscalYearFilterForm()
    
    # Get initial stats from stats.py
    try:
        initial_stats = core_stats.get_fiscal_year_statistics()
        timeline = core_stats.get_fiscal_year_timeline()
    except Exception as e:
        logger.error(f"Error getting fiscal year statistics: {e}")
        initial_stats = {}
        timeline = {}
    
    context = {
        'filter_form': filter_form,
        'stats': initial_stats,
        'timeline': timeline,
        'FiscalYear': FiscalYear,
    }
    
    return render(request, 'core/fiscal_years/list.html', context)


@login_required
def fiscal_year_create(request):
    """Create new fiscal year"""
    
    if request.method == 'POST':
        form = FiscalYearForm(request.POST)
        if form.is_valid():
            try:
                fiscal_year = form.save()
                
                messages.success(
                    request,
                    f'Fiscal year "{fiscal_year.name}" created successfully!'
                )
                return redirect('core:fiscal_year_detail', pk=fiscal_year.pk)
                
            except Exception as e:
                logger.error(f"Error creating fiscal year: {e}")
                messages.error(request, f'Error: {str(e)}')
    else:
        form = FiscalYearForm()
    
    context = {
        'form': form,
        'title': 'Create Fiscal Year',
        'submit_text': 'Create Fiscal Year',
    }
    
    return render(request, 'core/fiscal_years/form.html', context)


@login_required
def fiscal_year_detail(request, pk):
    """View fiscal year details"""
    
    fiscal_year = get_object_or_404(FiscalYear, pk=pk)
    
    # Get periods for this fiscal year
    try:
        periods_info = core_stats.get_fiscal_periods_by_year(fiscal_year)
    except Exception as e:
        logger.error(f"Error getting periods info: {e}")
        periods_info = {}
    
    # ⭐ Calculate progress using school timezone
    today = get_school_today()
    progress_info = {
        'days_elapsed': fiscal_year.get_elapsed_days(),
        'days_remaining': fiscal_year.get_remaining_days(),
        'total_days': fiscal_year.get_duration_days(),
        'progress_percentage': fiscal_year.get_progress_percentage(),
        'is_current': fiscal_year.is_current(),
        'is_upcoming': fiscal_year.is_upcoming(),
        'is_past': fiscal_year.is_past(),
    }
    
    context = {
        'fiscal_year': fiscal_year,
        'periods_info': periods_info,
        'progress_info': progress_info,
        'today': today,
    }
    
    return render(request, 'core/fiscal_years/detail.html', context)


@login_required
def fiscal_year_edit(request, pk):
    """Edit fiscal year"""
    
    fiscal_year = get_object_or_404(FiscalYear, pk=pk)
    
    # Check if can be edited
    if fiscal_year.is_locked:
        messages.warning(request, 'Cannot edit locked fiscal year.')
        return redirect('core:fiscal_year_detail', pk=pk)
    
    if request.method == 'POST':
        form = FiscalYearForm(request.POST, instance=fiscal_year)
        if form.is_valid():
            try:
                fiscal_year = form.save()
                
                messages.success(
                    request,
                    f'Fiscal year "{fiscal_year.name}" updated successfully!'
                )
                return redirect('core:fiscal_year_detail', pk=fiscal_year.pk)
                
            except Exception as e:
                logger.error(f"Error updating fiscal year: {e}")
                messages.error(request, f'Error: {str(e)}')
    else:
        form = FiscalYearForm(instance=fiscal_year)
    
    context = {
        'form': form,
        'fiscal_year': fiscal_year,
        'title': f'Edit {fiscal_year.name}',
        'submit_text': 'Update Fiscal Year',
    }
    
    return render(request, 'core/fiscal_years/form.html', context)


@login_required
def fiscal_year_close(request, pk):
    """Close fiscal year"""
    
    fiscal_year = get_object_or_404(FiscalYear, pk=pk)
    
    if request.method == 'POST':
        try:
            fiscal_year.close_fiscal_year(user=request.user)
            
            messages.success(
                request,
                f'Fiscal year "{fiscal_year.name}" closed successfully!'
            )
            
        except Exception as e:
            logger.error(f"Error closing fiscal year: {e}")
            messages.error(request, f'Error: {str(e)}')
    
    return redirect('core:fiscal_year_detail', pk=pk)


@login_required
def fiscal_year_lock(request, pk):
    """Lock fiscal year for audit compliance"""
    
    fiscal_year = get_object_or_404(FiscalYear, pk=pk)
    
    if request.method == 'POST':
        try:
            fiscal_year.lock_fiscal_year()
            
            messages.success(
                request,
                f'Fiscal year "{fiscal_year.name}" locked successfully!'
            )
            
        except ValidationError as e:
            messages.error(request, str(e))
        except Exception as e:
            logger.error(f"Error locking fiscal year: {e}")
            messages.error(request, f'Error: {str(e)}')
    
    return redirect('core:fiscal_year_detail', pk=pk)


@login_required
def fiscal_year_unlock(request, pk):
    """Unlock fiscal year"""
    
    fiscal_year = get_object_or_404(FiscalYear, pk=pk)
    
    if request.method == 'POST':
        try:
            fiscal_year.unlock_fiscal_year()
            
            messages.warning(
                request,
                f'Fiscal year "{fiscal_year.name}" unlocked. Use with caution!'
            )
            
        except Exception as e:
            logger.error(f"Error unlocking fiscal year: {e}")
            messages.error(request, f'Error: {str(e)}')
    
    return redirect('core:fiscal_year_detail', pk=pk)


@login_required
def fiscal_year_print_view(request):
    """Generate printable fiscal year list"""
    
    # Get selected fields
    selected_fields = request.GET.getlist('fields')
    if not selected_fields:
        selected_fields = ['name', 'code', 'start_date', 'end_date', 'status', 'is_active']
    
    include_stats = request.GET.get('include_stats') == 'true'
    landscape_mode = request.GET.get('landscape') == 'true'
    
    # Get filters
    query = request.GET.get('q', '')
    status = request.GET.get('status', '')
    is_active = request.GET.get('is_active', '')
    
    # Build queryset
    fiscal_years = FiscalYear.objects.annotate(
        period_count=Count('fiscal_periods')
    ).order_by('-start_date')
    
    # Apply filters
    if query:
        fiscal_years = fiscal_years.filter(
            Q(name__icontains=query) |
            Q(code__icontains=query)
        )
    
    if status:
        fiscal_years = fiscal_years.filter(status=status)
    
    if is_active:
        fiscal_years = fiscal_years.filter(is_active=(is_active == 'true'))
    
    # Calculate stats
    stats = None
    if include_stats:
        total = fiscal_years.count()
        stats = {
            'total': total,
            'active': fiscal_years.filter(is_active=True).count(),
            'closed': fiscal_years.filter(is_closed=True).count(),
            'locked': fiscal_years.filter(is_locked=True).count(),
        }
    
    field_names = {
        'name': 'Fiscal Year',
        'code': 'Code',
        'start_date': 'Start Date',
        'end_date': 'End Date',
        'status': 'Status',
        'is_active': 'Active',
        'is_closed': 'Closed',
        'is_locked': 'Locked',
        'period_count': 'Periods',
        'duration_days': 'Duration (Days)',
        'progress_percentage': 'Progress %',
    }
    
    selected_field_names = [field_names.get(f, f) for f in selected_fields]
    
    context = {
        'fiscal_years': fiscal_years,
        'stats': stats,
        'now': get_school_current_time(),
        'selected_fields': selected_fields,
        'selected_field_names': selected_field_names,
        'landscape': landscape_mode,
        'title': 'Fiscal Years Report',
    }
    
    return render(request, 'core/fiscal_years/print.html', context)


# =============================================================================
# FISCAL PERIOD VIEWS (CRUD + Print)
# =============================================================================

@login_required
def fiscal_period_list(request):
    """List all fiscal periods - HTMX loads data"""
    
    filter_form = FiscalPeriodFilterForm()
    
    try:
        initial_stats = core_stats.get_fiscal_period_statistics()
    except Exception as e:
        logger.error(f"Error getting period statistics: {e}")
        initial_stats = {}
    
    context = {
        'filter_form': filter_form,
        'stats': initial_stats,
        'FiscalPeriod': FiscalPeriod,
    }
    
    return render(request, 'core/fiscal_periods/list.html', context)


@login_required
def fiscal_period_create(request):
    """Create new fiscal period"""
    
    if request.method == 'POST':
        form = FiscalPeriodForm(request.POST)
        if form.is_valid():
            try:
                period = form.save()
                
                messages.success(
                    request,
                    f'Fiscal period "{period.name}" created successfully!'
                )
                return redirect('core:fiscal_period_detail', pk=period.pk)
                
            except Exception as e:
                logger.error(f"Error creating period: {e}")
                messages.error(request, f'Error: {str(e)}')
    else:
        form = FiscalPeriodForm()
    
    context = {
        'form': form,
        'title': 'Create Fiscal Period',
        'submit_text': 'Create Period',
    }
    
    return render(request, 'core/fiscal_periods/form.html', context)


@login_required
def fiscal_period_detail(request, pk):
    """View fiscal period details"""
    
    period = get_object_or_404(
        FiscalPeriod.objects.select_related('fiscal_year', 'related_academic_session'),
        pk=pk
    )
    
    # ⭐ Calculate progress using school timezone
    today = get_school_today()
    progress_info = {
        'days_elapsed': period.get_elapsed_days(),
        'days_remaining': period.get_remaining_days(),
        'total_days': period.get_duration_days(),
        'progress_percentage': period.get_progress_percentage(),
        'is_current': period.is_current(),
        'is_upcoming': period.is_upcoming(),
        'is_past': period.is_past(),
        'is_in_grace_period': period.is_in_grace_period(),
        'can_accept_transactions': period.can_accept_transactions(),
    }
    
    context = {
        'period': period,
        'progress_info': progress_info,
        'today': today,
    }
    
    return render(request, 'core/fiscal_periods/detail.html', context)


@login_required
def fiscal_period_edit(request, pk):
    """Edit fiscal period"""
    
    period = get_object_or_404(FiscalPeriod, pk=pk)
    
    if period.is_locked:
        messages.warning(request, 'Cannot edit locked fiscal period.')
        return redirect('core:fiscal_period_detail', pk=pk)
    
    if request.method == 'POST':
        form = FiscalPeriodForm(request.POST, instance=period)
        if form.is_valid():
            try:
                period = form.save()
                
                messages.success(
                    request,
                    f'Fiscal period "{period.name}" updated successfully!'
                )
                return redirect('core:fiscal_period_detail', pk=period.pk)
                
            except Exception as e:
                logger.error(f"Error updating period: {e}")
                messages.error(request, f'Error: {str(e)}')
    else:
        form = FiscalPeriodForm(instance=period)
    
    context = {
        'form': form,
        'period': period,
        'title': f'Edit {period.name}',
        'submit_text': 'Update Period',
    }
    
    return render(request, 'core/fiscal_periods/form.html', context)


@login_required
def fiscal_period_close(request, pk):
    """Close fiscal period"""
    
    period = get_object_or_404(FiscalPeriod, pk=pk)
    
    if request.method == 'POST':
        try:
            period.close_period(user=request.user)
            
            messages.success(
                request,
                f'Fiscal period "{period.name}" closed successfully!'
            )
            
        except Exception as e:
            logger.error(f"Error closing period: {e}")
            messages.error(request, f'Error: {str(e)}')
    
    return redirect('core:fiscal_period_detail', pk=pk)


@login_required
def fiscal_period_print_view(request):
    """Generate printable fiscal period list"""
    
    selected_fields = request.GET.getlist('fields')
    if not selected_fields:
        selected_fields = ['name', 'code', 'period_number', 'period_type', 'start_date', 'end_date', 'status']
    
    include_stats = request.GET.get('include_stats') == 'true'
    
    # Build queryset with filters
    periods = FiscalPeriod.objects.select_related(
        'fiscal_year', 'related_academic_session'
    ).order_by('-fiscal_year__start_date', 'period_number')
    
    query = request.GET.get('q', '')
    if query:
        periods = periods.filter(
            Q(name__icontains=query) | Q(code__icontains=query)
        )
    
    stats = None
    if include_stats:
        total = periods.count()
        stats = {
            'total': total,
            'active': periods.filter(is_active=True).count(),
            'closed': periods.filter(is_closed=True).count(),
        }
    
    context = {
        'periods': periods,
        'stats': stats,
        'now': get_school_current_time(),
        'selected_fields': selected_fields,
        'title': 'Fiscal Periods Report',
    }
    
    return render(request, 'core/fiscal_periods/print.html', context)


# =============================================================================
# PAYMENT METHOD VIEWS (CRUD + Print)
# =============================================================================

@login_required
def payment_method_list(request):
    """List all payment methods"""
    
    filter_form = PaymentMethodFilterForm()
    
    try:
        initial_stats = core_stats.get_payment_method_statistics()
    except Exception as e:
        logger.error(f"Error getting payment method stats: {e}")
        initial_stats = {}
    
    context = {
        'filter_form': filter_form,
        'stats': initial_stats,
    }
    
    return render(request, 'core/payment_methods/list.html', context)


@login_required
def payment_method_create(request):
    """Create new payment method"""
    
    if request.method == 'POST':
        form = PaymentMethodForm(request.POST)
        if form.is_valid():
            try:
                method = form.save()
                
                messages.success(
                    request,
                    f'Payment method "{method.name}" created successfully!'
                )
                return redirect('core:payment_method_detail', pk=method.pk)
                
            except Exception as e:
                logger.error(f"Error creating payment method: {e}")
                messages.error(request, f'Error: {str(e)}')
    else:
        form = PaymentMethodForm()
    
    context = {
        'form': form,
        'title': 'Create Payment Method',
        'submit_text': 'Create Method',
    }
    
    return render(request, 'core/payment_methods/form.html', context)


@login_required
def payment_method_detail(request, pk):
    """View payment method details"""
    
    method = get_object_or_404(PaymentMethod, pk=pk)
    
    # Get usage stats if available
    try:
        usage_stats = core_stats.get_payment_method_usage_stats(days=30)
        method_usage = usage_stats.get('by_method', {}).get(method.name, {})
    except Exception as e:
        logger.error(f"Error getting usage stats: {e}")
        method_usage = {}
    
    context = {
        'method': method,
        'method_usage': method_usage,
    }
    
    return render(request, 'core/payment_methods/detail.html', context)


@login_required
def payment_method_edit(request, pk):
    """Edit payment method"""
    
    method = get_object_or_404(PaymentMethod, pk=pk)
    
    if request.method == 'POST':
        form = PaymentMethodForm(request.POST, instance=method)
        if form.is_valid():
            try:
                method = form.save()
                
                messages.success(
                    request,
                    f'Payment method "{method.name}" updated successfully!'
                )
                return redirect('core:payment_method_detail', pk=method.pk)
                
            except Exception as e:
                logger.error(f"Error updating payment method: {e}")
                messages.error(request, f'Error: {str(e)}')
    else:
        form = PaymentMethodForm(instance=method)
    
    context = {
        'form': form,
        'method': method,
        'title': f'Edit {method.name}',
        'submit_text': 'Update Method',
    }
    
    return render(request, 'core/payment_methods/form.html', context)


@login_required
def payment_method_print_view(request):
    """Generate printable payment method list"""
    
    selected_fields = request.GET.getlist('fields')
    if not selected_fields:
        selected_fields = ['name', 'code', 'method_type', 'is_active', 'requires_approval']
    
    methods = PaymentMethod.objects.all().order_by('display_order', 'name')
    
    # Apply filters
    query = request.GET.get('q', '')
    if query:
        methods = methods.filter(Q(name__icontains=query) | Q(code__icontains=query))
    
    context = {
        'methods': methods,
        'now': get_school_current_time(),
        'selected_fields': selected_fields,
        'title': 'Payment Methods Report',
    }
    
    return render(request, 'core/payment_methods/print.html', context)


# =============================================================================
# TAX RATE VIEWS (CRUD + Print)
# =============================================================================

@login_required
def tax_rate_list(request):
    """List all tax rates"""
    
    filter_form = TaxRateFilterForm()
    
    try:
        initial_stats = core_stats.get_tax_rate_statistics()
    except Exception as e:
        logger.error(f"Error getting tax rate stats: {e}")
        initial_stats = {}
    
    context = {
        'filter_form': filter_form,
        'stats': initial_stats,
    }
    
    return render(request, 'core/tax_rates/list.html', context)


@login_required
def tax_rate_create(request):
    """Create new tax rate"""
    
    if request.method == 'POST':
        form = TaxRateForm(request.POST)
        if form.is_valid():
            try:
                rate = form.save()
                
                messages.success(
                    request,
                    f'Tax rate "{rate.name}" created successfully!'
                )
                return redirect('core:tax_rate_detail', pk=rate.pk)
                
            except Exception as e:
                logger.error(f"Error creating tax rate: {e}")
                messages.error(request, f'Error: {str(e)}')
    else:
        form = TaxRateForm()
    
    context = {
        'form': form,
        'title': 'Create Tax Rate',
        'submit_text': 'Create Rate',
    }
    
    return render(request, 'core/tax_rates/form.html', context)


@login_required
def tax_rate_detail(request, pk):
    """View tax rate details"""
    
    rate = get_object_or_404(TaxRate, pk=pk)
    
    # Check if currently effective
    today = get_school_today()
    is_effective = rate.is_effective(today)
    
    context = {
        'rate': rate,
        'is_effective': is_effective,
        'today': today,
    }
    
    return render(request, 'core/tax_rates/detail.html', context)


@login_required
def tax_rate_edit(request, pk):
    """Edit tax rate"""
    
    rate = get_object_or_404(TaxRate, pk=pk)
    
    if request.method == 'POST':
        form = TaxRateForm(request.POST, instance=rate)
        if form.is_valid():
            try:
                rate = form.save()
                
                messages.success(
                    request,
                    f'Tax rate "{rate.name}" updated successfully!'
                )
                return redirect('core:tax_rate_detail', pk=rate.pk)
                
            except Exception as e:
                logger.error(f"Error updating tax rate: {e}")
                messages.error(request, f'Error: {str(e)}')
    else:
        form = TaxRateForm(instance=rate)
    
    context = {
        'form': form,
        'rate': rate,
        'title': f'Edit {rate.name}',
        'submit_text': 'Update Rate',
    }
    
    return render(request, 'core/tax_rates/form.html', context)


@login_required
def tax_rate_print_view(request):
    """Generate printable tax rate list"""
    
    selected_fields = request.GET.getlist('fields')
    if not selected_fields:
        selected_fields = ['name', 'tax_type', 'rate', 'effective_from', 'effective_to', 'is_active']
    
    rates = TaxRate.objects.all().order_by('-effective_from', 'tax_type')
    
    context = {
        'rates': rates,
        'now': get_school_current_time(),
        'selected_fields': selected_fields,
        'title': 'Tax Rates Report',
    }
    
    return render(request, 'core/tax_rates/print.html', context)


# =============================================================================
# UNIT OF MEASURE VIEWS (CRUD + Print)
# =============================================================================

@login_required
def unit_of_measure_list(request):
    """List all units of measure"""
    
    filter_form = UnitOfMeasureFilterForm()
    
    try:
        initial_stats = core_stats.get_unit_of_measure_statistics()
    except Exception as e:
        logger.error(f"Error getting UOM stats: {e}")
        initial_stats = {}
    
    context = {
        'filter_form': filter_form,
        'stats': initial_stats,
    }
    
    return render(request, 'core/units/list.html', context)


@login_required
def unit_of_measure_create(request):
    """Create new unit of measure"""
    
    if request.method == 'POST':
        form = UnitOfMeasureForm(request.POST)
        if form.is_valid():
            try:
                unit = form.save()
                
                messages.success(
                    request,
                    f'Unit "{unit.name}" created successfully!'
                )
                return redirect('core:unit_of_measure_detail', pk=unit.pk)
                
            except Exception as e:
                logger.error(f"Error creating unit: {e}")
                messages.error(request, f'Error: {str(e)}')
    else:
        form = UnitOfMeasureForm()
    
    context = {
        'form': form,
        'title': 'Create Unit of Measure',
        'submit_text': 'Create Unit',
    }
    
    return render(request, 'core/units/form.html', context)


@login_required
def unit_of_measure_detail(request, pk):
    """View unit of measure details"""
    
    unit = get_object_or_404(UnitOfMeasure, pk=pk)
    
    # Get conversion examples
    conversion_examples = unit.get_conversion_examples()
    conversion_table = unit.get_conversion_table()
    derived_units = unit.get_all_derived_units()
    
    context = {
        'unit': unit,
        'conversion_examples': conversion_examples,
        'conversion_table': conversion_table,
        'derived_units': derived_units,
    }
    
    return render(request, 'core/units/detail.html', context)


@login_required
def unit_of_measure_edit(request, pk):
    """Edit unit of measure"""
    
    unit = get_object_or_404(UnitOfMeasure, pk=pk)
    
    if request.method == 'POST':
        form = UnitOfMeasureForm(request.POST, instance=unit)
        if form.is_valid():
            try:
                unit = form.save()
                
                messages.success(
                    request,
                    f'Unit "{unit.name}" updated successfully!'
                )
                return redirect('core:unit_of_measure_detail', pk=unit.pk)
                
            except Exception as e:
                logger.error(f"Error updating unit: {e}")
                messages.error(request, f'Error: {str(e)}')
    else:
        form = UnitOfMeasureForm(instance=unit)
    
    context = {
        'form': form,
        'unit': unit,
        'title': f'Edit {unit.name}',
        'submit_text': 'Update Unit',
    }
    
    return render(request, 'core/units/form.html', context)


@login_required
def unit_of_measure_print_view(request):
    """Generate printable unit of measure list"""
    
    selected_fields = request.GET.getlist('fields')
    if not selected_fields:
        selected_fields = ['name', 'abbreviation', 'uom_type', 'base_unit', 'conversion_factor', 'is_active']
    
    units = UnitOfMeasure.objects.select_related('base_unit').order_by('uom_type', 'name')
    
    context = {
        'units': units,
        'now': get_school_current_time(),
        'selected_fields': selected_fields,
        'title': 'Units of Measure Report',
    }
    
    return render(request, 'core/units/print.html', context)