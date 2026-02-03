# core/modal_views.py

"""
Core Configuration Modal Views (HTMX)

Handles HTMX modal operations including:
- Fiscal Year CRUD modals
- Fiscal Period CRUD modals
- Delete confirmations and operations
- Quick actions (set active, close, lock/unlock)
- Status changes
- Bulk operations

All modals use HTMX for seamless UX
Uses core.utils for timezone awareness
Audit trail automatically handled by BaseModel
"""

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.urls import reverse
from django.db import transaction
from django.db.models import Q, Count
from django.views.decorators.http import require_http_methods
from django.core.exceptions import ValidationError
import logging

# ⭐ Import timezone utilities from core
from .utils import (
    get_school_today,
    get_school_current_time,
)

from .models import (
    SchoolConfiguration,
    FinancialSettings,
    FiscalYear,
    FiscalPeriod,
    PaymentMethod,
    TaxRate,
    UnitOfMeasure,
)

from .forms import (
    FiscalYearForm,
    FiscalPeriodForm,
    PaymentMethodForm,
    TaxRateForm,
    UnitOfMeasureForm,
)

logger = logging.getLogger(__name__)


# =============================================================================
# FISCAL YEAR MODAL VIEWS (HTMX)
# =============================================================================

@login_required
def fiscal_year_modal_form(request, pk=None):
    """
    HTMX endpoint for fiscal year create/edit modal form.
    """
    
    # Determine if this is create or edit
    if pk:
        fiscal_year = get_object_or_404(FiscalYear, pk=pk)
        is_edit = True
        modal_title = f'Edit Fiscal Year: {fiscal_year.name}'
    else:
        fiscal_year = None
        is_edit = False
        modal_title = 'Create New Fiscal Year'
    
    # Check permissions for locked fiscal years
    if is_edit and fiscal_year.is_locked:
        messages.warning(
            request, 
            'Cannot edit locked fiscal year. Please unlock it first.'
        )
        response = HttpResponse()
        response['HX-Redirect'] = reverse('core:fiscal_management')
        return response
    
    if request.method == 'POST':
        logger.info("Processing POST request")
        form = FiscalYearForm(request.POST, instance=fiscal_year)
        
        if form.is_valid():
            logger.info("Form is valid, saving...")
            try:
                with transaction.atomic():
                    fiscal_year = form.save()
                    
                    action = 'updated' if is_edit else 'created'
                    messages.success(
                        request,
                        f'Fiscal year "{fiscal_year.name}" {action} successfully!'
                    )
                    
                    logger.info(f"Fiscal year {action} successfully: {fiscal_year.name}")
                    
                    # ⭐ Return HX-Redirect to reload the page
                    response = HttpResponse()
                    response['HX-Redirect'] = reverse('core:fiscal_management')
                    return response
                    
            except ValidationError as e:
                logger.error(f"Validation error: {e}")
                messages.error(request, str(e))
                # ⭐ Add error to form so it displays
                form.add_error(None, str(e))
            except Exception as e:
                logger.error(f"Error saving fiscal year: {e}")
                messages.error(request, f'Error saving fiscal year: {str(e)}')
                # ⭐ Add error to form so it displays
                form.add_error(None, f'Error saving fiscal year: {str(e)}')
        else:
            logger.warning(f"Form has errors: {form.errors}")
        
        # ⭐ Form has errors - re-render COMPLETE modal (header + body + footer)
        context = {
            'form': form,
            'fiscal_year': fiscal_year,
            'is_edit': is_edit,
            'modal_title': modal_title,
        }
        # Return the same template
        return render(request, 'core/fiscal_years/_modal_form.html', context)
    
    # GET request - render form
    logger.info("Rendering GET form")
    form = FiscalYearForm(instance=fiscal_year)
    
    context = {
        'form': form,
        'fiscal_year': fiscal_year,
        'is_edit': is_edit,
        'modal_title': modal_title,
    }
    
    return render(request, 'core/fiscal_years/_modal_form.html', context)


@login_required
@require_http_methods(["POST"])
def fiscal_year_quick_action(request, pk, action):
    """
    Handle quick actions for fiscal years via HTMX.
    
    Supported actions:
    - activate: Set as active fiscal year
    - close: Close the fiscal year
    - lock: Lock for audit compliance
    - unlock: Unlock the fiscal year
    
    Args:
        pk: Fiscal year UUID
        action: Action to perform
    
    Returns:
        HX-Redirect response or error JSON
    """
    
    fiscal_year = get_object_or_404(FiscalYear, pk=pk)
    
    try:
        if action == 'activate':
            # Validate fiscal year can be activated
            today = get_school_today()
            
            if fiscal_year.is_closed:
                raise ValidationError('Cannot activate a closed fiscal year.')
            
            if fiscal_year.is_locked:
                raise ValidationError('Cannot activate a locked fiscal year.')
            
            # Check if dates are reasonable
            if today > fiscal_year.end_date:
                messages.warning(
                    request,
                    f'Warning: Activating a fiscal year that has already ended.'
                )
            
            # Deactivate all other fiscal years
            with transaction.atomic():
                FiscalYear.objects.filter(is_active=True).update(is_active=False)
                fiscal_year.is_active = True
                fiscal_year.save()
            
            messages.success(
                request,
                f'Fiscal year "{fiscal_year.name}" is now active!'
            )
            
        elif action == 'close':
            # Close fiscal year and all its periods
            if fiscal_year.is_closed:
                raise ValidationError('Fiscal year is already closed.')
            
            if fiscal_year.is_locked:
                raise ValidationError('Cannot close a locked fiscal year. Unlock it first.')
            
            with transaction.atomic():
                fiscal_year.close_fiscal_year(user=request.user)
            
            messages.success(
                request,
                f'Fiscal year "{fiscal_year.name}" closed successfully. '
                f'All periods have been closed.'
            )
            
        elif action == 'lock':
            # Lock fiscal year for audit compliance
            if not fiscal_year.is_closed:
                raise ValidationError('Fiscal year must be closed before it can be locked.')
            
            if fiscal_year.is_locked:
                raise ValidationError('Fiscal year is already locked.')
            
            with transaction.atomic():
                fiscal_year.lock_fiscal_year()
            
            messages.warning(
                request,
                f'Fiscal year "{fiscal_year.name}" locked for audit compliance. '
                f'All periods are now locked.'
            )
            
        elif action == 'unlock':
            # Unlock fiscal year
            if not fiscal_year.is_locked:
                raise ValidationError('Fiscal year is not locked.')
            
            with transaction.atomic():
                fiscal_year.unlock_fiscal_year()
            
            messages.warning(
                request,
                f'Fiscal year "{fiscal_year.name}" unlocked. '
                f'Use with caution - this should only be done with proper authorization.'
            )
            
        else:
            return JsonResponse({
                'success': False, 
                'error': f'Invalid action: {action}'
            }, status=400)
        
        # Return HX-Redirect to reload the page
        response = HttpResponse()
        response['HX-Redirect'] = reverse('core:fiscal_management')
        return response
        
    except ValidationError as e:
        messages.error(request, str(e))
        response = HttpResponse()
        response['HX-Redirect'] = reverse('core:fiscal_management')
        return response
        
    except Exception as e:
        logger.error(f"Error in fiscal year quick action '{action}': {e}")
        messages.error(request, f'Error performing action: {str(e)}')
        response = HttpResponse()
        response['HX-Redirect'] = reverse('core:fiscal_management')
        return response


@login_required
def fiscal_year_delete_modal(request, pk):
    """Show delete confirmation modal for fiscal year"""
    
    fiscal_year = get_object_or_404(FiscalYear, pk=pk)
    
    # Check if can be deleted
    can_delete = True
    warnings = []
    errors = []
    
    # Check if locked
    if fiscal_year.is_locked:
        can_delete = False
        errors.append("Fiscal year is locked for audit compliance")
    
    # Check if active
    if fiscal_year.is_active:
        can_delete = False
        errors.append("Cannot delete active fiscal year")
    
    # Check for periods
    period_count = fiscal_year.fiscal_periods.count()
    if period_count > 0:
        can_delete = False
        errors.append(f"Fiscal year has {period_count} fiscal periods")
    
    # Check for transactions (if finance app available)
    try:
        from finance.models import Invoice, Payment
        
        invoice_count = Invoice.objects.filter(fiscal_year=fiscal_year).count()
        if invoice_count > 0:
            can_delete = False
            errors.append(f"Fiscal year has {invoice_count} invoices")
        
        payment_count = Payment.objects.filter(fiscal_period__fiscal_year=fiscal_year).count()
        if payment_count > 0:
            can_delete = False
            errors.append(f"Fiscal year has {payment_count} payments")
    except ImportError:
        pass
    
    # Additional warnings (not blocking)
    if fiscal_year.is_closed:
        warnings.append("This fiscal year has been closed")
    
    context = {
        'object': fiscal_year,
        'object_name': 'Fiscal Year',
        'object_title': fiscal_year.name,
        'can_delete': can_delete,
        'warnings': warnings,
        'errors': errors,
        'delete_url': 'core:fiscal_year_delete',
    }
    
    if request.method == 'POST':
        if not can_delete:
            messages.error(
                request, 
                f'Cannot delete fiscal year: {", ".join(errors)}'
            )
        else:
            try:
                fiscal_year_name = fiscal_year.name
                fiscal_year.delete()
                
                messages.success(
                    request,
                    f'Fiscal year "{fiscal_year_name}" deleted successfully.'
                )
            except Exception as e:
                logger.error(f"Error deleting fiscal year: {e}")
                messages.error(request, f'Error deleting fiscal year: {str(e)}')
        
        response = HttpResponse()
        response['HX-Redirect'] = reverse('core:fiscal_management')
        return response
    
    return render(request, 'core/modals/delete_confirmation.html', context)


@login_required
@require_http_methods(["POST"])
def fiscal_year_delete(request, pk):
    """Delete fiscal year via HTMX (Legacy endpoint - redirects to delete_modal)"""
    
    fiscal_year = get_object_or_404(FiscalYear, pk=pk)
    year_name = fiscal_year.name
    
    # Final validation
    if fiscal_year.is_locked:
        messages.error(request, 'Cannot delete locked fiscal year')
        response = HttpResponse()
        response['HX-Redirect'] = reverse('core:fiscal_management')
        return response
    
    if fiscal_year.is_active:
        messages.error(request, 'Cannot delete active fiscal year')
        response = HttpResponse()
        response['HX-Redirect'] = reverse('core:fiscal_management')
        return response
    
    if fiscal_year.fiscal_periods.exists():
        messages.error(request, 'Cannot delete fiscal year with periods')
        response = HttpResponse()
        response['HX-Redirect'] = reverse('core:fiscal_management')
        return response
    
    try:
        fiscal_year.delete()
        messages.success(request, f'Fiscal year "{year_name}" deleted successfully.')
        
    except Exception as e:
        logger.error(f"Error deleting fiscal year: {e}")
        messages.error(request, f'Error deleting fiscal year: {str(e)}')
    
    response = HttpResponse()
    response['HX-Redirect'] = reverse('core:fiscal_management')
    return response


@login_required
def fiscal_year_set_active_modal(request, pk):
    """Modal to set fiscal year as active"""
    
    fiscal_year = get_object_or_404(FiscalYear, pk=pk)
    
    can_set_active = True
    warnings = []
    
    # ⭐ Check against school timezone
    today = get_school_today()
    
    if today < fiscal_year.start_date:
        warnings.append("Fiscal year hasn't started yet")
    elif today > fiscal_year.end_date:
        warnings.append("Fiscal year has already ended")
    
    if fiscal_year.is_closed:
        can_set_active = False
        warnings.append("Cannot activate closed fiscal year")
    
    if fiscal_year.is_locked:
        can_set_active = False
        warnings.append("Cannot activate locked fiscal year")
    
    context = {
        'fiscal_year': fiscal_year,
        'can_set_active': can_set_active,
        'warnings': warnings,
        'today': today,
    }
    
    return render(request, 'core/modals/set_active_fiscal_year.html', context)


@login_required
@require_http_methods(["POST"])
def fiscal_year_set_active(request, pk):
    """Set fiscal year as active via HTMX (Legacy - use quick_action instead)"""
    
    fiscal_year = get_object_or_404(FiscalYear, pk=pk)
    
    try:
        # Deactivate all other fiscal years
        FiscalYear.objects.filter(is_active=True).update(is_active=False)
        
        # Set this as active
        fiscal_year.is_active = True
        fiscal_year.save()
        
        messages.success(request, f'"{fiscal_year.name}" is now the active fiscal year.')
        
    except Exception as e:
        logger.error(f"Error setting active fiscal year: {e}")
        messages.error(request, f'Error: {str(e)}')
    
    response = HttpResponse()
    response['HX-Redirect'] = reverse('core:fiscal_management')
    return response


@login_required
def fiscal_year_close_modal(request, pk):
    """Modal to confirm fiscal year closure"""
    
    fiscal_year = get_object_or_404(FiscalYear, pk=pk)
    
    can_close = True
    warnings = []
    info = []
    
    # Check if already closed
    if fiscal_year.is_closed:
        can_close = False
        warnings.append("Fiscal year is already closed")
    
    # Check for open periods
    open_periods = fiscal_year.fiscal_periods.filter(is_closed=False).count()
    if open_periods > 0:
        warnings.append(f"{open_periods} fiscal periods are still open and will be closed")
    
    # Get period summary
    total_periods = fiscal_year.get_period_count()
    if total_periods > 0:
        info.append(f"Total periods: {total_periods}")
    
    context = {
        'fiscal_year': fiscal_year,
        'can_close': can_close,
        'warnings': warnings,
        'info': info,
        'open_periods': open_periods,
    }
    
    return render(request, 'core/modals/close_fiscal_year.html', context)


@login_required
@require_http_methods(["POST"])
def fiscal_year_close(request, pk):
    """Close fiscal year via HTMX (Legacy - use quick_action instead)"""
    
    fiscal_year = get_object_or_404(FiscalYear, pk=pk)
    
    try:
        fiscal_year.close_fiscal_year(user=request.user)
        messages.success(
            request,
            f'Fiscal year "{fiscal_year.name}" closed successfully!'
        )
    except Exception as e:
        logger.error(f"Error closing fiscal year: {e}")
        messages.error(request, f'Error: {str(e)}')
    
    response = HttpResponse()
    response['HX-Redirect'] = reverse('core:fiscal_management')
    return response


@login_required
@require_http_methods(["POST"])
def fiscal_year_lock(request, pk):
    """Lock fiscal year via HTMX (Legacy - use quick_action instead)"""
    
    fiscal_year = get_object_or_404(FiscalYear, pk=pk)
    
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
    
    response = HttpResponse()
    response['HX-Redirect'] = reverse('core:fiscal_management')
    return response


@login_required
@require_http_methods(["POST"])
def fiscal_year_unlock(request, pk):
    """Unlock fiscal year via HTMX (Legacy - use quick_action instead)"""
    
    fiscal_year = get_object_or_404(FiscalYear, pk=pk)
    
    try:
        fiscal_year.unlock_fiscal_year()
        messages.warning(
            request,
            f'Fiscal year "{fiscal_year.name}" unlocked. Use with caution!'
        )
    except Exception as e:
        logger.error(f"Error unlocking fiscal year: {e}")
        messages.error(request, f'Error: {str(e)}')
    
    response = HttpResponse()
    response['HX-Redirect'] = reverse('core:fiscal_management')
    return response


# =============================================================================
# FISCAL PERIOD MODAL VIEWS (HTMX)
# =============================================================================

@login_required
def period_modal_form(request, pk=None):
    """
    HTMX endpoint for period create/edit modal form.
    """
    
    # Determine if this is create or edit
    if pk:
        period = get_object_or_404(FiscalPeriod, pk=pk)
        is_edit = True
        modal_title = f'Edit Period: {period.name}'
    else:
        period = None  # ⭐ CRITICAL: Must be None for new periods
        is_edit = False
        modal_title = 'Create New Period'
    
    # Get fiscal year from query param (for new periods)
    fiscal_year_id = request.GET.get('fiscal_year_id')
    
    # Check permissions for locked periods
    if is_edit and period.is_locked:
        messages.warning(
            request, 
            'Cannot edit locked period. Please unlock it first.'
        )
        response = HttpResponse()
        response['HX-Redirect'] = reverse('core:fiscal_management')
        return response
    
    if request.method == 'POST':
        logger.info(f"Processing POST request for period (is_edit={is_edit}, pk={pk})")
        
        # ⭐ CRITICAL: Pass instance=None for new periods, instance=period for edits
        form = FiscalPeriodForm(request.POST, instance=period if is_edit else None)
        
        # ⭐ DEBUG: Log form state
        logger.info(f"Form instance.pk = {form.instance.pk if hasattr(form, 'instance') else 'No instance'}")
        
        if form.is_valid():
            logger.info("Form is valid, saving...")
            try:
                with transaction.atomic():
                    period = form.save()
                    
                    action = 'updated' if is_edit else 'created'
                    messages.success(
                        request,
                        f'Period "{period.name}" {action} successfully!'
                    )
                    
                    logger.info(f"Period {action} successfully: {period.name}")
                    
                    # ⭐ Return HX-Redirect to reload the page
                    response = HttpResponse()
                    response['HX-Redirect'] = reverse('core:fiscal_management')
                    return response
                    
            except ValidationError as e:
                logger.error(f"Validation error: {e}")
                messages.error(request, str(e))
                form.add_error(None, str(e))
            except Exception as e:
                logger.error(f"Error saving period: {e}")
                messages.error(request, f'Error saving period: {str(e)}')
                form.add_error(None, f'Error saving period: {str(e)}')
        else:
            logger.warning(f"Form has errors: {form.errors}")
            # ⭐ DEBUG: Log which fields have errors
            for field, errors in form.errors.items():
                logger.warning(f"Field '{field}' errors: {errors}")
        
        # Form has errors - re-render COMPLETE modal
        context = {
            'form': form,
            'period': period if is_edit else None,  # ⭐ Pass None for new periods
            'is_edit': is_edit,
            'modal_title': modal_title,
        }
        return render(request, 'core/periods/_modal_form.html', context)
    
    # GET request - render form
    logger.info(f"Rendering GET form for period (is_edit={is_edit}, pk={pk})")
    
    # ⭐ FIX: Create form with initial data for fiscal_year
    initial_data = {}
    
    # Pre-select fiscal year if provided and creating new period
    if fiscal_year_id and not is_edit:
        try:
            fiscal_year = FiscalYear.objects.get(pk=fiscal_year_id)
            initial_data['fiscal_year'] = fiscal_year.pk  # ⭐ Use PK
            
            # Suggest next period number
            last_period = fiscal_year.fiscal_periods.order_by('-period_number').first()
            if last_period:
                import math
                next_number = math.ceil(float(last_period.period_number)) + 1
                initial_data['period_number'] = next_number
            else:
                initial_data['period_number'] = 1
            
            # Suggest code
            initial_data['code'] = f"FP_{fiscal_year.code}_P{int(initial_data['period_number'])}"
            
            # Suggest name
            initial_data['name'] = f"Period {int(initial_data['period_number'])} - {fiscal_year.name}"
            
            # Suggest dates (same as fiscal year)
            initial_data['start_date'] = fiscal_year.start_date
            initial_data['end_date'] = fiscal_year.end_date
            
            logger.info(f"Pre-populating form with fiscal_year: {fiscal_year.name} (ID: {fiscal_year.pk})")
                
        except FiscalYear.DoesNotExist:
            logger.warning(f"Fiscal year {fiscal_year_id} not found")
    
    # ⭐ CRITICAL: Create form with instance=None for new periods
    form = FiscalPeriodForm(
        instance=period if is_edit else None,  # ⭐ None for new, period for edit
        initial=initial_data if not is_edit else {}
    )
    
    # ⭐ DEBUG: Log form state
    logger.info(f"Form created - instance.pk = {form.instance.pk if hasattr(form, 'instance') and form.instance else 'None'}")
    logger.info(f"Form fiscal_year field disabled = {form.fields['fiscal_year'].disabled}")
    
    context = {
        'form': form,
        'period': period if is_edit else None,  # ⭐ Pass None for new periods
        'is_edit': is_edit,
        'modal_title': modal_title,
    }
    
    return render(request, 'core/periods/_modal_form.html', context)


@login_required
@require_http_methods(["POST"])
def period_quick_action(request, pk, action):
    """
    Handle quick actions for periods via HTMX.
    
    Supported actions:
    - activate: Set as active period
    - close: Close the period
    - lock: Lock for audit compliance
    - unlock: Unlock the period
    - reopen: Reopen a closed period
    
    Args:
        pk: Period UUID
        action: Action to perform
    
    Returns:
        HX-Redirect response or error JSON
    """
    
    period = get_object_or_404(FiscalPeriod, pk=pk)
    
    try:
        if action == 'activate':
            # Validate period can be activated
            if period.is_closed:
                raise ValidationError('Cannot activate a closed period.')
            
            if period.is_locked:
                raise ValidationError('Cannot activate a locked period.')
            
            # Deactivate all other periods
            with transaction.atomic():
                FiscalPeriod.objects.filter(is_active=True).update(is_active=False)
                period.is_active = True
                period.save()
            
            messages.success(
                request,
                f'Period "{period.name}" is now active!'
            )
            
        elif action == 'close':
            # Close period
            if period.is_closed:
                raise ValidationError('Period is already closed.')
            
            if period.is_locked:
                raise ValidationError('Cannot close a locked period. Unlock it first.')
            
            with transaction.atomic():
                period.close_period(user=request.user)
            
            messages.success(
                request,
                f'Period "{period.name}" closed successfully.'
            )
            
        elif action == 'lock':
            # Lock period for audit compliance
            if not period.is_closed:
                raise ValidationError('Period must be closed before it can be locked.')
            
            if period.is_locked:
                raise ValidationError('Period is already locked.')
            
            with transaction.atomic():
                period.lock_period(user=request.user)
            
            messages.warning(
                request,
                f'Period "{period.name}" locked for audit compliance.'
            )
            
        elif action == 'unlock':
            # Unlock period
            if not period.is_locked:
                raise ValidationError('Period is not locked.')
            
            with transaction.atomic():
                period.unlock_period(user=request.user)
            
            messages.warning(
                request,
                f'Period "{period.name}" unlocked. '
                f'Use with caution - this should only be done with proper authorization.'
            )
            
        elif action == 'reopen':
            # Reopen a closed period
            if period.is_locked:
                raise ValidationError(
                    'Cannot reopen a locked period. Unlock it first.'
                )
            
            if not period.is_closed:
                raise ValidationError('Period is not closed.')
            
            with transaction.atomic():
                period.reopen_period(user=request.user)
            
            messages.warning(
                request,
                f'Period "{period.name}" reopened. '
                f'New transactions can now be posted to this period.'
            )
            
        else:
            return JsonResponse({
                'success': False, 
                'error': f'Invalid action: {action}'
            }, status=400)
        
        # Return HX-Redirect to reload the page
        response = HttpResponse()
        response['HX-Redirect'] = reverse('core:fiscal_management')
        return response
        
    except ValidationError as e:
        messages.error(request, str(e))
        response = HttpResponse()
        response['HX-Redirect'] = reverse('core:fiscal_management')
        return response
        
    except Exception as e:
        logger.error(f"Error in period quick action '{action}': {e}")
        messages.error(request, f'Error performing action: {str(e)}')
        response = HttpResponse()
        response['HX-Redirect'] = reverse('core:fiscal_management')
        return response


@login_required
def fiscal_period_delete_modal(request, pk):
    """Show delete confirmation modal for fiscal period"""
    
    period = get_object_or_404(FiscalPeriod, pk=pk)
    
    can_delete = True
    warnings = []
    errors = []
    
    # Check if locked
    if period.is_locked:
        can_delete = False
        errors.append("Period is locked for audit compliance")
    
    # Check if closed
    if period.is_closed:
        warnings.append("Period is closed")
    
    # Check if active
    if period.is_active:
        warnings.append("Period is currently active")
    
    # Check for transactions (if available)
    try:
        from finance.models import Invoice, Payment
        
        invoice_count = Invoice.objects.filter(fiscal_period=period).count()
        if invoice_count > 0:
            can_delete = False
            errors.append(f"Period has {invoice_count} invoices")
        
        payment_count = Payment.objects.filter(fiscal_period=period).count()
        if payment_count > 0:
            can_delete = False
            errors.append(f"Period has {payment_count} payments")
    except ImportError:
        pass
    
    context = {
        'object': period,
        'object_name': 'Fiscal Period',
        'object_title': period.name,
        'can_delete': can_delete,
        'warnings': warnings,
        'errors': errors,
        'delete_url': 'core:fiscal_period_delete',
    }
    
    if request.method == 'POST':
        if not can_delete:
            messages.error(
                request, 
                f'Cannot delete period: {", ".join(errors)}'
            )
        else:
            try:
                period_name = period.name
                period.delete()
                
                messages.success(
                    request,
                    f'Period "{period_name}" deleted successfully.'
                )
            except Exception as e:
                logger.error(f"Error deleting period: {e}")
                messages.error(request, f'Error deleting period: {str(e)}')
        
        response = HttpResponse()
        response['HX-Redirect'] = reverse('core:fiscal_management')
        return response
    
    return render(request, 'core/modals/delete_confirmation.html', context)


@login_required
@require_http_methods(["POST"])
def fiscal_period_delete(request, pk):
    """Delete fiscal period via HTMX (Legacy - redirects to delete_modal)"""
    
    period = get_object_or_404(FiscalPeriod, pk=pk)
    period_name = period.name
    
    # Final validation
    if period.is_locked:
        messages.error(request, 'Cannot delete locked period')
        response = HttpResponse()
        response['HX-Redirect'] = reverse('core:fiscal_management')
        return response
    
    try:
        period.delete()
        messages.success(request, f'Fiscal period "{period_name}" deleted successfully.')
        
    except Exception as e:
        logger.error(f"Error deleting fiscal period: {e}")
        messages.error(request, f'Error: {str(e)}')
    
    response = HttpResponse()
    response['HX-Redirect'] = reverse('core:fiscal_management')
    return response


@login_required
def fiscal_period_close_modal(request, pk):
    """Modal to confirm fiscal period closure"""
    
    period = get_object_or_404(FiscalPeriod, pk=pk)
    
    can_close = True
    warnings = []
    info = []
    
    # Check if already closed
    if period.is_closed:
        can_close = False
        warnings.append("Period is already closed")
    
    # Check if locked
    if period.is_locked:
        can_close = False
        warnings.append("Period is locked")
    
    # Get transaction summary (if available)
    try:
        from finance.models import Invoice, Payment
        
        invoice_count = Invoice.objects.filter(fiscal_period=period).count()
        payment_count = Payment.objects.filter(fiscal_period=period).count()
        
        if invoice_count > 0:
            info.append(f"Invoices: {invoice_count}")
        if payment_count > 0:
            info.append(f"Payments: {payment_count}")
    except ImportError:
        pass
    
    context = {
        'period': period,
        'can_close': can_close,
        'warnings': warnings,
        'info': info,
    }
    
    return render(request, 'core/modals/close_fiscal_period.html', context)


@login_required
@require_http_methods(["POST"])
def fiscal_period_close(request, pk):
    """Close fiscal period via HTMX (Legacy - use quick_action instead)"""
    
    period = get_object_or_404(FiscalPeriod, pk=pk)
    
    try:
        period.close_period(user=request.user)
        messages.success(
            request,
            f'Fiscal period "{period.name}" closed successfully!'
        )
    except Exception as e:
        logger.error(f"Error closing period: {e}")
        messages.error(request, f'Error: {str(e)}')
    
    response = HttpResponse()
    response['HX-Redirect'] = reverse('core:fiscal_management')
    return response


@login_required
def fiscal_period_reopen_modal(request, pk):
    """Modal to confirm fiscal period reopening"""
    
    period = get_object_or_404(FiscalPeriod, pk=pk)
    
    can_reopen = True
    warnings = []
    
    # Check if locked
    if period.is_locked:
        can_reopen = False
        warnings.append("Cannot reopen locked period. Unlock it first.")
    
    # Check if closed
    if not period.is_closed:
        can_reopen = False
        warnings.append("Period is not closed")
    
    warnings.append("Reopening a period allows new transactions to be posted")
    warnings.append("This should only be done with proper authorization")
    
    context = {
        'period': period,
        'can_reopen': can_reopen,
        'warnings': warnings,
    }
    
    return render(request, 'core/modals/reopen_fiscal_period.html', context)


@login_required
@require_http_methods(["POST"])
def fiscal_period_reopen(request, pk):
    """Reopen fiscal period via HTMX (Legacy - use quick_action instead)"""
    
    period = get_object_or_404(FiscalPeriod, pk=pk)
    
    try:
        period.reopen_period(user=request.user)
        
        messages.warning(
            request,
            f'Fiscal period "{period.name}" reopened. Use with caution!'
        )
        
    except ValidationError as e:
        messages.error(request, str(e))
    except Exception as e:
        logger.error(f"Error reopening period: {e}")
        messages.error(request, f'Error: {str(e)}')
    
    response = HttpResponse()
    response['HX-Redirect'] = reverse('core:fiscal_management')
    return response


# =============================================================================
# PAYMENT METHOD MODALS
# =============================================================================

@login_required
def payment_method_delete_modal(request, pk):
    """Show delete confirmation modal for payment method"""
    
    method = get_object_or_404(PaymentMethod, pk=pk)
    
    can_delete = True
    warnings = []
    errors = []
    
    # Check if default
    if method.is_default:
        can_delete = False
        errors.append("Cannot delete default payment method")
    
    # Check for usage (if finance app available)
    try:
        from finance.models import Payment
        
        payment_count = Payment.objects.filter(payment_method=method).count()
        if payment_count > 0:
            can_delete = False
            errors.append(f"Method has been used in {payment_count} payments")
    except ImportError:
        pass
    
    # Suggest deactivation instead
    if not can_delete and method.is_active:
        warnings.append("Consider deactivating instead of deleting")
    
    context = {
        'object': method,
        'object_name': 'Payment Method',
        'object_title': method.name,
        'can_delete': can_delete,
        'warnings': warnings,
        'errors': errors,
        'delete_url': 'core:payment_method_delete',
        'alternative_action': 'Deactivate this method instead' if not can_delete else None,
    }
    
    if request.method == 'POST':
        if not can_delete:
            messages.error(
                request, 
                f'Cannot delete payment method: {", ".join(errors)}'
            )
        else:
            try:
                method_name = method.name
                method.delete()
                
                messages.success(
                    request,
                    f'Payment method "{method_name}" deleted successfully.'
                )
            except Exception as e:
                logger.error(f"Error deleting payment method: {e}")
                messages.error(request, f'Error: {str(e)}')
        
        response = HttpResponse()
        response['HX-Redirect'] = reverse('core:payment_methods_list')
        return response
    
    return render(request, 'core/modals/delete_confirmation.html', context)


@login_required
@require_http_methods(["POST"])
def payment_method_delete(request, pk):
    """Delete payment method via HTMX (Legacy)"""
    
    method = get_object_or_404(PaymentMethod, pk=pk)
    method_name = method.name
    
    # Final validation
    if method.is_default:
        messages.error(request, 'Cannot delete default payment method')
        response = HttpResponse()
        response['HX-Redirect'] = reverse('core:payment_methods_list')
        return response
    
    try:
        method.delete()
        messages.success(request, f'Payment method "{method_name}" deleted successfully.')
        
    except Exception as e:
        logger.error(f"Error deleting payment method: {e}")
        messages.error(request, f'Error: {str(e)}')
    
    response = HttpResponse()
    response['HX-Redirect'] = reverse('core:payment_methods_list')
    return response


@login_required
def payment_method_toggle_status_modal(request, pk):
    """Modal to toggle payment method active status"""
    
    method = get_object_or_404(PaymentMethod, pk=pk)
    
    action = 'activate' if not method.is_active else 'deactivate'
    warnings = []
    
    if action == 'deactivate':
        if method.is_default:
            warnings.append("This is the default method. Set another method as default first.")
        warnings.append("Users will not be able to select this method for payments")
    else:
        warnings.append("This method will be available for payments")
    
    context = {
        'method': method,
        'action': action,
        'warnings': warnings,
    }
    
    return render(request, 'core/modals/toggle_payment_method.html', context)


@login_required
@require_http_methods(["POST"])
def payment_method_toggle_status(request, pk):
    """Toggle payment method status via HTMX"""
    
    method = get_object_or_404(PaymentMethod, pk=pk)
    
    try:
        # Check if can deactivate (if it's default)
        if method.is_active and method.is_default:
            raise ValidationError(
                'Cannot deactivate the default payment method. '
                'Set another method as default first.'
            )
        
        method.is_active = not method.is_active
        method.save()
        
        status = 'activated' if method.is_active else 'deactivated'
        messages.success(request, f'Payment method "{method.name}" {status}.')
        
    except ValidationError as e:
        messages.error(request, str(e))
    except Exception as e:
        logger.error(f"Error toggling payment method: {e}")
        messages.error(request, f'Error: {str(e)}')
    
    response = HttpResponse()
    response['HX-Redirect'] = reverse('core:payment_methods_list')
    return response


# =============================================================================
# TAX RATE MODALS
# =============================================================================

@login_required
def tax_rate_delete_modal(request, pk):
    """Show delete confirmation modal for tax rate"""
    
    rate = get_object_or_404(TaxRate, pk=pk)
    
    can_delete = True
    warnings = []
    errors = []
    
    # Check if currently effective
    today = get_school_today()
    if rate.is_effective(today):
        warnings.append("This tax rate is currently effective")
    
    # Check for usage (if finance app available)
    try:
        from finance.models import Invoice
        
        invoice_count = Invoice.objects.filter(tax_rate=rate).count()
        if invoice_count > 0:
            can_delete = False
            errors.append(f"Tax rate has been applied to {invoice_count} invoices")
    except ImportError:
        pass
    
    context = {
        'object': rate,
        'object_name': 'Tax Rate',
        'object_title': rate.name,
        'can_delete': can_delete,
        'warnings': warnings,
        'errors': errors,
        'delete_url': 'core:tax_rate_delete',
    }
    
    if request.method == 'POST':
        if not can_delete:
            messages.error(
                request, 
                f'Cannot delete tax rate: {", ".join(errors)}'
            )
        else:
            try:
                rate_name = rate.name
                rate.delete()
                
                messages.success(
                    request,
                    f'Tax rate "{rate_name}" deleted successfully.'
                )
            except Exception as e:
                logger.error(f"Error deleting tax rate: {e}")
                messages.error(request, f'Error: {str(e)}')
        
        response = HttpResponse()
        response['HX-Redirect'] = reverse('core:tax_rates_list')
        return response
    
    return render(request, 'core/modals/delete_confirmation.html', context)


@login_required
@require_http_methods(["POST"])
def tax_rate_delete(request, pk):
    """Delete tax rate via HTMX (Legacy)"""
    
    rate = get_object_or_404(TaxRate, pk=pk)
    rate_name = rate.name
    
    try:
        rate.delete()
        messages.success(request, f'Tax rate "{rate_name}" deleted successfully.')
        
    except Exception as e:
        logger.error(f"Error deleting tax rate: {e}")
        messages.error(request, f'Error: {str(e)}')
    
    response = HttpResponse()
    response['HX-Redirect'] = reverse('core:tax_rates_list')
    return response


# =============================================================================
# UNIT OF MEASURE MODALS
# =============================================================================

@login_required
def unit_of_measure_delete_modal(request, pk):
    """Show delete confirmation modal for unit of measure"""
    
    unit = get_object_or_404(UnitOfMeasure, pk=pk)
    
    can_delete = unit.can_be_deleted()
    warnings = unit.get_deletion_warnings()
    errors = []
    
    if not can_delete:
        errors.append("Unit has dependent units or is in use")
    
    context = {
        'object': unit,
        'object_name': 'Unit of Measure',
        'object_title': unit.name,
        'can_delete': can_delete,
        'warnings': warnings,
        'errors': errors,
        'delete_url': 'core:unit_of_measure_delete',
    }
    
    if request.method == 'POST':
        if not can_delete:
            messages.error(
                request, 
                'Cannot delete unit - it has dependent units or is in use'
            )
        else:
            try:
                unit_name = unit.name
                unit.delete()
                
                messages.success(
                    request,
                    f'Unit "{unit_name}" deleted successfully.'
                )
            except Exception as e:
                logger.error(f"Error deleting unit: {e}")
                messages.error(request, f'Error: {str(e)}')
        
        response = HttpResponse()
        response['HX-Redirect'] = reverse('core:units_list')
        return response
    
    return render(request, 'core/modals/delete_confirmation.html', context)


@login_required
@require_http_methods(["POST"])
def unit_of_measure_delete(request, pk):
    """Delete unit of measure via HTMX (Legacy)"""
    
    unit = get_object_or_404(UnitOfMeasure, pk=pk)
    unit_name = unit.name
    
    # Final validation
    if not unit.can_be_deleted():
        messages.error(request, 'Unit cannot be deleted - it has dependent units or is in use')
        response = HttpResponse()
        response['HX-Redirect'] = reverse('core:units_list')
        return response
    
    try:
        unit.delete()
        messages.success(request, f'Unit "{unit_name}" deleted successfully.')
        
    except Exception as e:
        logger.error(f"Error deleting unit: {e}")
        messages.error(request, f'Error: {str(e)}')
    
    response = HttpResponse()
    response['HX-Redirect'] = reverse('core:units_list')
    return response


# =============================================================================
# BULK OPERATIONS
# =============================================================================

@login_required
def bulk_close_periods_modal(request):
    """Modal for bulk closing fiscal periods"""
    
    # Get closeable periods
    today = get_school_today()
    
    closeable_periods = FiscalPeriod.objects.filter(
        end_date__lt=today,
        is_closed=False,
        is_locked=False
    ).select_related('fiscal_year').order_by('end_date')[:20]
    
    context = {
        'periods': closeable_periods,
        'count': closeable_periods.count(),
    }
    
    if request.method == 'POST':
        period_ids = request.POST.getlist('periods')
        
        if not period_ids:
            messages.error(request, 'No periods selected')
        else:
            try:
                periods = FiscalPeriod.objects.filter(
                    id__in=period_ids,
                    is_closed=False,
                    is_locked=False
                )
                
                closed_count = 0
                errors = []
                
                with transaction.atomic():
                    for period in periods:
                        try:
                            period.close_period(user=request.user)
                            closed_count += 1
                        except Exception as e:
                            logger.error(f"Error closing period {period}: {e}")
                            errors.append(f"{period.name}: {str(e)}")
                
                if closed_count > 0:
                    messages.success(
                        request,
                        f'Successfully closed {closed_count} fiscal period(s).'
                    )
                
                if errors:
                    messages.warning(
                        request,
                        f'Failed to close some periods: {"; ".join(errors)}'
                    )
                    
            except Exception as e:
                logger.error(f"Error in bulk close: {e}")
                messages.error(request, f'Error: {str(e)}')
        
        response = HttpResponse()
        response['HX-Redirect'] = reverse('core:fiscal_management')
        return response
    
    return render(request, 'core/modals/bulk_close_periods.html', context)


@login_required
@require_http_methods(["POST"])
def bulk_close_periods(request):
    """Bulk close fiscal periods via HTMX (Legacy - use modal POST instead)"""
    
    period_ids = request.POST.getlist('periods')
    
    if not period_ids:
        messages.error(request, 'No periods selected')
        response = HttpResponse()
        response['HX-Redirect'] = reverse('core:fiscal_management')
        return response
    
    try:
        periods = FiscalPeriod.objects.filter(
            id__in=period_ids,
            is_closed=False,
            is_locked=False
        )
        
        closed_count = 0
        for period in periods:
            try:
                period.close_period(user=request.user)
                closed_count += 1
            except Exception as e:
                logger.error(f"Error closing period {period}: {e}")
        
        messages.success(
            request,
            f'Successfully closed {closed_count} fiscal period(s).'
        )
        
    except Exception as e:
        logger.error(f"Error in bulk close: {e}")
        messages.error(request, f'Error: {str(e)}')
    
    response = HttpResponse()
    response['HX-Redirect'] = reverse('core:fiscal_management')
    return response


@login_required
def create_standard_units_modal(request):
    """Modal to confirm creation of standard units"""
    
    # Check if units already exist
    existing_count = UnitOfMeasure.objects.count()
    
    context = {
        'existing_count': existing_count,
        'has_existing': existing_count > 0,
    }
    
    if request.method == 'POST':
        try:
            created_units = UnitOfMeasure.create_standard_units()
            
            messages.success(
                request,
                f'Successfully created/verified {len(created_units)} standard units of measure.'
            )
            
        except Exception as e:
            logger.error(f"Error creating standard units: {e}")
            messages.error(request, f'Error: {str(e)}')
        
        response = HttpResponse()
        response['HX-Redirect'] = reverse('core:units_list')
        return response
    
    return render(request, 'core/modals/create_standard_units.html', context)


@login_required
@require_http_methods(["POST"])
def create_standard_units(request):
    """Create standard units of measure via HTMX (Legacy - use modal POST instead)"""
    
    try:
        created_units = UnitOfMeasure.create_standard_units()
        
        messages.success(
            request,
            f'Successfully created/verified {len(created_units)} standard units of measure.'
        )
        
    except Exception as e:
        logger.error(f"Error creating standard units: {e}")
        messages.error(request, f'Error: {str(e)}')
    
    response = HttpResponse()
    response['HX-Redirect'] = reverse('core:units_list')
    return response