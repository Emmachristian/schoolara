# core/modal_views.py

"""
Core Configuration Modal Views (HTMX)

Handles HTMX modal operations:
- Fiscal Year CRUD modals + quick actions
- Fiscal Period CRUD modals + quick actions
- Delete confirmations
- Status changes (activate / close / lock / unlock / reopen)
- Bulk operations
- Payment Method, Tax Rate, Unit of Measure modals

All successful mutations return HX-Redirect so the full page reloads cleanly.

CORRECTIONS vs previous version
---------------------------------
1. Delete-guard queries now use fees.models.Payment and fees.models.FeeInvoice
   (not finance.models which does not have those models).
2. All _hx_redirect() calls replaced with view_helpers.htmx_redirect().
3. fiscal_year_delete_modal and fiscal_period_delete_modal no longer import
   finance.Invoice — they check fees.FeeInvoice instead.
"""

import math
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from .models import (
    FiscalPeriod,
    FiscalYear,
    PaymentMethod,
    TaxRate,
    UnitOfMeasure,
)
from .forms import (
    FiscalPeriodForm,
    FiscalYearForm,
    PaymentMethodForm,
    TaxRateForm,
    UnitOfMeasureForm,
)
from .utils import get_school_today
from .view_helpers import htmx_redirect

logger = logging.getLogger(__name__)


# =============================================================================
# FISCAL YEAR — modal form (create / edit)
# =============================================================================

@login_required
def fiscal_year_modal_form(request, pk=None):
    if pk:
        fiscal_year = get_object_or_404(FiscalYear, pk=pk)
        is_edit     = True
        modal_title = f'Edit Fiscal Year: {fiscal_year.name}'
    else:
        fiscal_year = None
        is_edit     = False
        modal_title = 'Create New Fiscal Year'

    if is_edit and fiscal_year.is_locked:
        messages.warning(request, 'Cannot edit a locked fiscal year.')
        return htmx_redirect(reverse('core:fiscal_management'))

    if request.method == 'POST':
        form = FiscalYearForm(request.POST, instance=fiscal_year)
        if form.is_valid():
            try:
                with transaction.atomic():
                    fiscal_year = form.save()
                    action      = 'updated' if is_edit else 'created'
                    messages.success(
                        request,
                        f'Fiscal year "{fiscal_year.name}" {action} successfully!'
                    )
                    return htmx_redirect(reverse('core:fiscal_management'))
            except ValidationError as e:
                form.add_error(None, str(e))
            except Exception as e:
                logger.error(f"Error saving fiscal year: {e}")
                form.add_error(None, f'Unexpected error: {str(e)}')
        else:
            logger.warning(f"FiscalYearForm errors: {form.errors}")

        return render(request, 'core/fiscal_years/_modal_form.html', {
            'form':        form,
            'fiscal_year': fiscal_year,
            'is_edit':     is_edit,
            'modal_title': modal_title,
        })

    form = FiscalYearForm(instance=fiscal_year)
    return render(request, 'core/fiscal_years/_modal_form.html', {
        'form':        form,
        'fiscal_year': fiscal_year,
        'is_edit':     is_edit,
        'modal_title': modal_title,
    })


# =============================================================================
# FISCAL YEAR — quick actions
# =============================================================================

@login_required
@require_http_methods(["POST"])
def fiscal_year_quick_action(request, pk, action):
    """Single POST endpoint for activate / close / lock / unlock."""

    fiscal_year = get_object_or_404(FiscalYear, pk=pk)

    try:
        if action == 'activate':
            if fiscal_year.is_closed:
                raise ValidationError('Cannot activate a closed fiscal year.')
            if fiscal_year.is_locked:
                raise ValidationError('Cannot activate a locked fiscal year.')

            today = get_school_today()
            if today > fiscal_year.end_date:
                messages.warning(
                    request,
                    'Warning: activating a fiscal year that has already ended.'
                )

            with transaction.atomic():
                FiscalYear.objects.exclude(pk=pk).filter(is_active=True).update(
                    is_active=False, status='DRAFT'
                )
                fiscal_year.is_active = True
                fiscal_year.save()

            messages.success(
                request,
                f'"{fiscal_year.name}" is now the active fiscal year.'
            )

        elif action == 'close':
            if fiscal_year.is_closed:
                raise ValidationError('Fiscal year is already closed.')
            if fiscal_year.is_locked:
                raise ValidationError('Cannot close a locked fiscal year.')

            with transaction.atomic():
                fiscal_year.close_fiscal_year(user=request.user)

            messages.success(
                request,
                f'Fiscal year "{fiscal_year.name}" closed. '
                f'All periods have been closed.'
            )

        elif action == 'lock':
            if not fiscal_year.is_closed:
                raise ValidationError(
                    'Fiscal year must be closed before it can be locked.'
                )
            if fiscal_year.is_locked:
                raise ValidationError('Fiscal year is already locked.')

            with transaction.atomic():
                fiscal_year.lock_fiscal_year()

            messages.warning(
                request,
                f'Fiscal year "{fiscal_year.name}" locked for audit compliance.'
            )

        elif action == 'unlock':
            if not fiscal_year.is_locked:
                raise ValidationError('Fiscal year is not locked.')

            with transaction.atomic():
                fiscal_year.unlock_fiscal_year()

            messages.warning(
                request,
                f'Fiscal year "{fiscal_year.name}" unlocked. Use with caution.'
            )

        else:
            return JsonResponse(
                {'success': False, 'error': f'Invalid action: {action}'}, status=400
            )

    except ValidationError as e:
        messages.error(request, str(e))
    except Exception as e:
        logger.error(f"Error in fiscal year quick action '{action}': {e}")
        messages.error(request, f'Error performing action: {str(e)}')

    return htmx_redirect(reverse('core:fiscal_management'))


# =============================================================================
# FISCAL YEAR — delete modal
# =============================================================================

@login_required
def fiscal_year_delete_modal(request, pk):
    fiscal_year = get_object_or_404(FiscalYear, pk=pk)
    can_delete  = True
    warnings    = []
    errors      = []

    if fiscal_year.is_locked:
        can_delete = False
        errors.append('Fiscal year is locked for audit compliance.')
    if fiscal_year.is_active:
        can_delete = False
        errors.append('Cannot delete the active fiscal year.')

    period_count = fiscal_year.fiscal_periods.count()
    if period_count > 0:
        can_delete = False
        errors.append(f'Fiscal year has {period_count} fiscal period(s).')

    # Check for financial transactions — Payment and FeeInvoice live in fees
    try:
        from fees.models import FeeInvoice, Payment
        invoice_count = FeeInvoice.objects.filter(
            fiscal_period__fiscal_year=fiscal_year
        ).count()
        if invoice_count > 0:
            can_delete = False
            errors.append(f'{invoice_count} invoice(s) belong to this fiscal year.')
        payment_count = Payment.objects.filter(
            fiscal_period__fiscal_year=fiscal_year
        ).count()
        if payment_count > 0:
            can_delete = False
            errors.append(f'{payment_count} payment(s) belong to this fiscal year.')
    except ImportError:
        pass

    if fiscal_year.is_closed:
        warnings.append('This fiscal year has already been closed.')

    if request.method == 'POST':
        if not can_delete:
            messages.error(request, f'Cannot delete: {", ".join(errors)}')
        else:
            try:
                name = fiscal_year.name
                fiscal_year.delete()
                messages.success(request, f'Fiscal year "{name}" deleted.')
            except Exception as e:
                logger.error(f"Error deleting fiscal year: {e}")
                messages.error(request, f'Error: {str(e)}')
        return htmx_redirect(reverse('core:fiscal_management'))

    return render(request, 'core/modals/delete_confirmation.html', {
        'object':       fiscal_year,
        'object_name':  'Fiscal Year',
        'object_title': fiscal_year.name,
        'can_delete':   can_delete,
        'warnings':     warnings,
        'errors':       errors,
        'delete_url':   'core:fiscal_year_delete_modal',
    })


@login_required
@require_http_methods(["POST"])
def fiscal_year_delete(request, pk):
    """Legacy direct-POST delete (no confirmation modal)."""
    fiscal_year = get_object_or_404(FiscalYear, pk=pk)

    if fiscal_year.is_locked:
        messages.error(request, 'Cannot delete a locked fiscal year.')
        return htmx_redirect(reverse('core:fiscal_management'))
    if fiscal_year.is_active:
        messages.error(request, 'Cannot delete the active fiscal year.')
        return htmx_redirect(reverse('core:fiscal_management'))
    if fiscal_year.fiscal_periods.exists():
        messages.error(request, 'Cannot delete a fiscal year that has periods.')
        return htmx_redirect(reverse('core:fiscal_management'))

    try:
        name = fiscal_year.name
        fiscal_year.delete()
        messages.success(request, f'Fiscal year "{name}" deleted.')
    except Exception as e:
        logger.error(f"Error deleting fiscal year: {e}")
        messages.error(request, f'Error: {str(e)}')

    return htmx_redirect(reverse('core:fiscal_management'))


# =============================================================================
# FISCAL YEAR — legacy modal views (backward-compat URL entries)
# =============================================================================

@login_required
def fiscal_year_set_active_modal(request, pk):
    fiscal_year    = get_object_or_404(FiscalYear, pk=pk)
    today          = get_school_today()
    can_set_active = not fiscal_year.is_closed and not fiscal_year.is_locked
    warnings       = []

    if today < fiscal_year.start_date:
        warnings.append("Fiscal year hasn't started yet.")
    elif today > fiscal_year.end_date:
        warnings.append("Fiscal year has already ended.")
    if fiscal_year.is_closed:
        warnings.append("Cannot activate a closed fiscal year.")
    if fiscal_year.is_locked:
        warnings.append("Cannot activate a locked fiscal year.")

    return render(request, 'core/modals/set_active_fiscal_year.html', {
        'fiscal_year':    fiscal_year,
        'can_set_active': can_set_active,
        'warnings':       warnings,
        'today':          today,
    })


@login_required
@require_http_methods(["POST"])
def fiscal_year_set_active(request, pk):
    fiscal_year = get_object_or_404(FiscalYear, pk=pk)
    try:
        FiscalYear.objects.exclude(pk=pk).filter(is_active=True).update(
            is_active=False, status='DRAFT'
        )
        fiscal_year.is_active = True
        fiscal_year.save()
        messages.success(
            request, f'"{fiscal_year.name}" is now the active fiscal year.'
        )
    except Exception as e:
        logger.error(f"Error setting active fiscal year: {e}")
        messages.error(request, f'Error: {str(e)}')
    return htmx_redirect(reverse('core:fiscal_management'))


@login_required
def fiscal_year_close_modal(request, pk):
    fiscal_year  = get_object_or_404(FiscalYear, pk=pk)
    can_close    = not fiscal_year.is_closed
    open_periods = fiscal_year.fiscal_periods.filter(is_closed=False).count()
    warnings     = []
    info         = []

    if fiscal_year.is_closed:
        warnings.append('Fiscal year is already closed.')
    if open_periods > 0:
        warnings.append(f'{open_periods} open period(s) will also be closed.')
    if fiscal_year.get_period_count() > 0:
        info.append(f'Total periods: {fiscal_year.get_period_count()}')

    return render(request, 'core/modals/close_fiscal_year.html', {
        'fiscal_year': fiscal_year,
        'can_close':   can_close,
        'warnings':    warnings,
        'info':        info,
        'open_periods':open_periods,
    })


@login_required
@require_http_methods(["POST"])
def fiscal_year_close(request, pk):
    fiscal_year = get_object_or_404(FiscalYear, pk=pk)
    try:
        fiscal_year.close_fiscal_year(user=request.user)
        messages.success(request, f'Fiscal year "{fiscal_year.name}" closed.')
    except Exception as e:
        logger.error(f"Error closing fiscal year: {e}")
        messages.error(request, f'Error: {str(e)}')
    return htmx_redirect(reverse('core:fiscal_management'))


@login_required
@require_http_methods(["POST"])
def fiscal_year_lock(request, pk):
    fiscal_year = get_object_or_404(FiscalYear, pk=pk)
    try:
        fiscal_year.lock_fiscal_year()
        messages.success(request, f'Fiscal year "{fiscal_year.name}" locked.')
    except ValidationError as e:
        messages.error(request, str(e))
    except Exception as e:
        logger.error(f"Error locking fiscal year: {e}")
        messages.error(request, f'Error: {str(e)}')
    return htmx_redirect(reverse('core:fiscal_management'))


@login_required
@require_http_methods(["POST"])
def fiscal_year_unlock(request, pk):
    fiscal_year = get_object_or_404(FiscalYear, pk=pk)
    try:
        fiscal_year.unlock_fiscal_year()
        messages.warning(request, f'Fiscal year "{fiscal_year.name}" unlocked.')
    except Exception as e:
        logger.error(f"Error unlocking fiscal year: {e}")
        messages.error(request, f'Error: {str(e)}')
    return htmx_redirect(reverse('core:fiscal_management'))


# =============================================================================
# FISCAL PERIOD — modal form (create / edit)
# =============================================================================

@login_required
def period_modal_form(request, pk=None):
    if pk:
        period      = get_object_or_404(FiscalPeriod, pk=pk)
        is_edit     = True
        modal_title = f'Edit Period: {period.name}'
    else:
        period      = None
        is_edit     = False
        modal_title = 'Create New Period'

    fiscal_year_id = request.GET.get('fiscal_year_id', '').strip()

    if is_edit and period.is_locked:
        messages.warning(request, 'Cannot edit a locked period.')
        return htmx_redirect(reverse('core:fiscal_management'))

    if request.method == 'POST':
        form = FiscalPeriodForm(
            request.POST,
            instance=period if is_edit else None,
        )
        if form.is_valid():
            try:
                with transaction.atomic():
                    period = form.save()
                    action = 'updated' if is_edit else 'created'
                    messages.success(
                        request, f'Period "{period.name}" {action} successfully!'
                    )
                    return htmx_redirect(reverse('core:fiscal_management'))
            except ValidationError as e:
                form.add_error(None, str(e))
            except Exception as e:
                logger.error(f"Error saving period: {e}")
                form.add_error(None, f'Unexpected error: {str(e)}')
        else:
            logger.warning(f"FiscalPeriodForm errors: {form.errors}")

        return render(request, 'core/fiscal_periods/_modal_form.html', {
            'form':        form,
            'period':      period if is_edit else None,
            'is_edit':     is_edit,
            'modal_title': modal_title,
        })

    # GET — build initial data for a new period
    initial = {}
    if fiscal_year_id and not is_edit:
        try:
            fiscal_year = FiscalYear.objects.get(pk=fiscal_year_id)
            last_period = fiscal_year.fiscal_periods.order_by(
                '-period_number'
            ).first()
            next_number = (
                math.ceil(float(last_period.period_number)) + 1
                if last_period
                else 1
            )
            initial['fiscal_year']   = fiscal_year.pk
            initial['period_number'] = next_number
            initial['code']          = f"FP_{fiscal_year.code}_P{int(next_number)}"
            initial['name']          = f"Period {int(next_number)} — {fiscal_year.name}"
            initial['start_date']    = fiscal_year.start_date
            initial['end_date']      = fiscal_year.end_date
        except FiscalYear.DoesNotExist:
            logger.warning(
                f"Fiscal year {fiscal_year_id} not found for period pre-fill."
            )

    form = FiscalPeriodForm(
        instance=period if is_edit else None,
        initial=initial  if not is_edit else {},
    )

    return render(request, 'core/fiscal_periods/_modal_form.html', {
        'form':        form,
        'period':      period if is_edit else None,
        'is_edit':     is_edit,
        'modal_title': modal_title,
    })


# =============================================================================
# FISCAL PERIOD — quick actions
# =============================================================================

@login_required
@require_http_methods(["POST"])
def period_quick_action(request, pk, action):
    """Single POST endpoint for activate / close / lock / unlock / reopen."""

    period = get_object_or_404(FiscalPeriod, pk=pk)

    try:
        if action == 'activate':
            if period.is_closed:
                raise ValidationError('Cannot activate a closed period.')
            if period.is_locked:
                raise ValidationError('Cannot activate a locked period.')

            with transaction.atomic():
                FiscalPeriod.objects.exclude(pk=pk).filter(
                    is_active=True
                ).update(is_active=False, status='DRAFT')
                period.is_active = True
                period.save()

            messages.success(request, f'Period "{period.name}" is now active.')

        elif action == 'close':
            if period.is_closed:
                raise ValidationError('Period is already closed.')
            if period.is_locked:
                raise ValidationError('Cannot close a locked period.')

            with transaction.atomic():
                period.close_period(user=request.user)

            messages.success(request, f'Period "{period.name}" closed.')

        elif action == 'lock':
            if not period.is_closed:
                raise ValidationError('Period must be closed before locking.')
            if period.is_locked:
                raise ValidationError('Period is already locked.')

            with transaction.atomic():
                period.lock_period(user=request.user)

            messages.warning(
                request,
                f'Period "{period.name}" locked for audit compliance.'
            )

        elif action == 'unlock':
            if not period.is_locked:
                raise ValidationError('Period is not locked.')

            with transaction.atomic():
                period.unlock_period(user=request.user)

            messages.warning(
                request,
                f'Period "{period.name}" unlocked. Use with caution.'
            )

        elif action == 'reopen':
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
                f'New transactions can now be posted.'
            )

        else:
            return JsonResponse(
                {'success': False, 'error': f'Invalid action: {action}'}, status=400
            )

    except ValidationError as e:
        messages.error(request, str(e))
    except Exception as e:
        logger.error(f"Error in period quick action '{action}': {e}")
        messages.error(request, f'Error performing action: {str(e)}')

    return htmx_redirect(reverse('core:fiscal_management'))


# =============================================================================
# FISCAL PERIOD — delete modal
# =============================================================================

@login_required
def fiscal_period_delete_modal(request, pk):
    period     = get_object_or_404(FiscalPeriod, pk=pk)
    can_delete = True
    warnings   = []
    errors     = []

    if period.is_locked:
        can_delete = False
        errors.append('Period is locked for audit compliance.')
    if period.is_closed:
        warnings.append('Period is closed.')
    if period.is_active:
        warnings.append('Period is currently active.')

    # FeeInvoice and Payment live in fees, not finance
    try:
        from fees.models import FeeInvoice, Payment
        invoice_count = FeeInvoice.objects.filter(fiscal_period=period).count()
        if invoice_count > 0:
            can_delete = False
            errors.append(f'{invoice_count} invoice(s) belong to this period.')
        payment_count = Payment.objects.filter(fiscal_period=period).count()
        if payment_count > 0:
            can_delete = False
            errors.append(f'{payment_count} payment(s) belong to this period.')
    except ImportError:
        pass

    if request.method == 'POST':
        if not can_delete:
            messages.error(request, f'Cannot delete: {", ".join(errors)}')
        else:
            try:
                name = period.name
                period.delete()
                messages.success(request, f'Period "{name}" deleted.')
            except Exception as e:
                logger.error(f"Error deleting period: {e}")
                messages.error(request, f'Error: {str(e)}')
        return htmx_redirect(reverse('core:fiscal_management'))

    return render(request, 'core/modals/delete_confirmation.html', {
        'object':       period,
        'object_name':  'Fiscal Period',
        'object_title': period.name,
        'can_delete':   can_delete,
        'warnings':     warnings,
        'errors':       errors,
        'delete_url':   'core:fiscal_period_delete_modal',
    })


@login_required
@require_http_methods(["POST"])
def fiscal_period_delete(request, pk):
    period = get_object_or_404(FiscalPeriod, pk=pk)

    if period.is_locked:
        messages.error(request, 'Cannot delete a locked period.')
        return htmx_redirect(reverse('core:fiscal_management'))

    try:
        name = period.name
        period.delete()
        messages.success(request, f'Period "{name}" deleted.')
    except Exception as e:
        logger.error(f"Error deleting fiscal period: {e}")
        messages.error(request, f'Error: {str(e)}')

    return htmx_redirect(reverse('core:fiscal_management'))


# =============================================================================
# FISCAL PERIOD — legacy modal views
# =============================================================================

@login_required
def fiscal_period_close_modal(request, pk):
    period    = get_object_or_404(FiscalPeriod, pk=pk)
    can_close = not period.is_closed and not period.is_locked
    warnings  = []
    info      = []

    if period.is_closed:
        warnings.append('Period is already closed.')
    if period.is_locked:
        warnings.append('Period is locked.')

    # Check transaction counts (fees app)
    try:
        from fees.models import FeeInvoice, Payment
        ic = FeeInvoice.objects.filter(fiscal_period=period).count()
        pc = Payment.objects.filter(fiscal_period=period).count()
        if ic:
            info.append(f'Invoices: {ic}')
        if pc:
            info.append(f'Payments: {pc}')
    except ImportError:
        pass

    return render(request, 'core/modals/close_fiscal_period.html', {
        'period':    period,
        'can_close': can_close,
        'warnings':  warnings,
        'info':      info,
    })


@login_required
def fiscal_period_reopen_modal(request, pk):
    period     = get_object_or_404(FiscalPeriod, pk=pk)
    can_reopen = period.is_closed and not period.is_locked
    warnings   = [
        'Reopening allows new transactions to be posted to this period.',
        'This should only be done with proper authorisation.',
    ]
    if period.is_locked:
        warnings.insert(0, 'Cannot reopen a locked period. Unlock it first.')
    if not period.is_closed:
        warnings.insert(0, 'Period is not closed.')

    return render(request, 'core/modals/reopen_fiscal_period.html', {
        'period':     period,
        'can_reopen': can_reopen,
        'warnings':   warnings,
    })


@login_required
@require_http_methods(["POST"])
def fiscal_period_close(request, pk):
    period = get_object_or_404(FiscalPeriod, pk=pk)
    try:
        period.close_period(user=request.user)
        messages.success(request, f'Period "{period.name}" closed.')
    except Exception as e:
        logger.error(f"Error closing period: {e}")
        messages.error(request, f'Error: {str(e)}')
    return htmx_redirect(reverse('core:fiscal_management'))


@login_required
@require_http_methods(["POST"])
def fiscal_period_reopen(request, pk):
    period = get_object_or_404(FiscalPeriod, pk=pk)
    try:
        period.reopen_period(user=request.user)
        messages.warning(request, f'Period "{period.name}" reopened.')
    except ValidationError as e:
        messages.error(request, str(e))
    except Exception as e:
        logger.error(f"Error reopening period: {e}")
        messages.error(request, f'Error: {str(e)}')
    return htmx_redirect(reverse('core:fiscal_management'))


# =============================================================================
# PAYMENT METHOD — modals
# =============================================================================

@login_required
def payment_method_modal_form(request, pk=None):
    """Create or edit payment method via modal."""
    if pk:
        method      = get_object_or_404(PaymentMethod, pk=pk)
        is_edit     = True
        modal_title = f'Edit Payment Method: {method.name}'
    else:
        method      = None
        is_edit     = False
        modal_title = 'Create Payment Method'

    if request.method == 'POST':
        form = PaymentMethodForm(request.POST, instance=method)
        if form.is_valid():
            try:
                with transaction.atomic():
                    method = form.save()
                    action = 'updated' if is_edit else 'created'
                    messages.success(
                        request,
                        f'Payment method "{method.name}" {action} successfully!'
                    )
                    return htmx_redirect(reverse('core:payment_method_list'))
            except ValidationError as e:
                form.add_error(None, str(e))
            except Exception as e:
                logger.error(f"Error saving payment method: {e}")
                form.add_error(None, f'Unexpected error: {str(e)}')
        else:
            logger.warning(f"PaymentMethodForm errors: {form.errors}")

        return render(request, 'core/payment_methods/_modal_form.html', {
            'form':        form,
            'method':      method,
            'is_edit':     is_edit,
            'modal_title': modal_title,
        })

    form = PaymentMethodForm(instance=method)
    return render(request, 'core/payment_methods/_modal_form.html', {
        'form':        form,
        'method':      method,
        'is_edit':     is_edit,
        'modal_title': modal_title,
    })


@login_required
def payment_method_delete_modal(request, pk):
    method     = get_object_or_404(PaymentMethod, pk=pk)
    can_delete = True
    warnings   = []
    errors     = []

    if method.is_default:
        can_delete = False
        errors.append('Cannot delete the default payment method.')

    # Payment lives in fees.models
    try:
        from fees.models import Payment
        count = Payment.objects.filter(payment_method=method).count()
        if count > 0:
            can_delete = False
            errors.append(f'Method has been used in {count} payment(s).')
    except ImportError:
        pass

    if not can_delete and method.is_active:
        warnings.append('Consider deactivating instead of deleting.')

    if request.method == 'POST':
        if not can_delete:
            messages.error(request, f'Cannot delete: {", ".join(errors)}')
        else:
            try:
                name = method.name
                method.delete()
                messages.success(request, f'Payment method "{name}" deleted.')
            except Exception as e:
                logger.error(f"Error deleting payment method: {e}")
                messages.error(request, f'Error: {str(e)}')
        return htmx_redirect(reverse('core:payment_method_list'))

    return render(request, 'core/modals/delete_confirmation.html', {
        'object':            method,
        'object_name':       'Payment Method',
        'object_title':      method.name,
        'can_delete':        can_delete,
        'warnings':          warnings,
        'errors':            errors,
        'delete_url':        'core:payment_method_delete_modal',
        'alternative_action':'Deactivate instead' if not can_delete else None,
    })


@login_required
@require_http_methods(["POST"])
def payment_method_delete(request, pk):
    method = get_object_or_404(PaymentMethod, pk=pk)

    if method.is_default:
        messages.error(request, 'Cannot delete the default payment method.')
        return htmx_redirect(reverse('core:payment_method_list'))

    try:
        from fees.models import Payment
        if Payment.objects.filter(payment_method=method).exists():
            messages.error(
                request,
                'Cannot delete — method has been used in payments. '
                'Deactivate it instead.'
            )
            return htmx_redirect(reverse('core:payment_method_list'))
    except ImportError:
        pass

    try:
        name = method.name
        method.delete()
        messages.success(request, f'Payment method "{name}" deleted.')
    except Exception as e:
        logger.error(f"Error deleting payment method: {e}")
        messages.error(request, f'Error: {str(e)}')

    return htmx_redirect(reverse('core:payment_method_list'))


@login_required
def payment_method_toggle_status_modal(request, pk):
    method   = get_object_or_404(PaymentMethod, pk=pk)
    action   = 'activate' if not method.is_active else 'deactivate'
    warnings = []

    if action == 'deactivate':
        if method.is_default:
            warnings.append(
                'This is the default method — set another as default first.'
            )
        warnings.append(
            'Users will not be able to select this method for payments.'
        )
    else:
        warnings.append('This method will become available for payments.')

    return render(request, 'core/modals/toggle_payment_method.html', {
        'method':   method,
        'action':   action,
        'warnings': warnings,
    })


@login_required
@require_http_methods(["POST"])
def payment_method_toggle_status(request, pk):
    method = get_object_or_404(PaymentMethod, pk=pk)

    try:
        if method.is_active and method.is_default:
            raise ValidationError(
                'Cannot deactivate the default payment method. '
                'Set another as default first.'
            )
        method.is_active = not method.is_active
        method.save()
        status = 'activated' if method.is_active else 'deactivated'
        messages.success(
            request, f'Payment method "{method.name}" {status}.'
        )
    except ValidationError as e:
        messages.error(request, str(e))
    except Exception as e:
        logger.error(f"Error toggling payment method: {e}")
        messages.error(request, f'Error: {str(e)}')

    return htmx_redirect(reverse('core:payment_method_list'))


# =============================================================================
# TAX RATE — modals
# =============================================================================

@login_required
def tax_rate_modal_form(request, pk=None):
    """Create or edit tax rate via modal."""
    if pk:
        rate        = get_object_or_404(TaxRate, pk=pk)
        is_edit     = True
        modal_title = f'Edit Tax Rate: {rate.name}'
    else:
        rate        = None
        is_edit     = False
        modal_title = 'Create Tax Rate'

    if request.method == 'POST':
        form = TaxRateForm(request.POST, instance=rate)
        if form.is_valid():
            try:
                with transaction.atomic():
                    rate   = form.save()
                    action = 'updated' if is_edit else 'created'
                    messages.success(
                        request, f'Tax rate "{rate.name}" {action} successfully!'
                    )
                    return htmx_redirect(reverse('core:tax_rate_list'))
            except ValidationError as e:
                form.add_error(None, str(e))
            except Exception as e:
                logger.error(f"Error saving tax rate: {e}")
                form.add_error(None, f'Unexpected error: {str(e)}')
        else:
            logger.warning(f"TaxRateForm errors: {form.errors}")

        return render(request, 'core/tax_rates/_modal_form.html', {
            'form':        form,
            'rate':        rate,
            'is_edit':     is_edit,
            'modal_title': modal_title,
        })

    form = TaxRateForm(instance=rate)
    return render(request, 'core/tax_rates/_modal_form.html', {
        'form':        form,
        'rate':        rate,
        'is_edit':     is_edit,
        'modal_title': modal_title,
    })


@login_required
def tax_rate_delete_modal(request, pk):
    rate       = get_object_or_404(TaxRate, pk=pk)
    today      = get_school_today()
    can_delete = True
    warnings   = []
    errors     = []

    if rate.is_effective(today):
        warnings.append('This tax rate is currently effective.')

    # TaxRate is not directly FK'd from FeeInvoice in the current model
    # (TaxRate is a reference table — invoices store the rate value at time
    # of issue, not a live FK). No FK check needed here.
    # If a direct FK is added in future, add the check here.

    if request.method == 'POST':
        if not can_delete:
            messages.error(request, f'Cannot delete: {", ".join(errors)}')
        else:
            try:
                name = rate.name
                rate.delete()
                messages.success(request, f'Tax rate "{name}" deleted.')
            except Exception as e:
                logger.error(f"Error deleting tax rate: {e}")
                messages.error(request, f'Error: {str(e)}')
        return htmx_redirect(reverse('core:tax_rate_list'))

    return render(request, 'core/modals/delete_confirmation.html', {
        'object':       rate,
        'object_name':  'Tax Rate',
        'object_title': rate.name,
        'can_delete':   can_delete,
        'warnings':     warnings,
        'errors':       errors,
        'delete_url':   'core:tax_rate_delete_modal',
    })


@login_required
@require_http_methods(["POST"])
def tax_rate_delete(request, pk):
    rate = get_object_or_404(TaxRate, pk=pk)
    try:
        name = rate.name
        rate.delete()
        messages.success(request, f'Tax rate "{name}" deleted.')
    except Exception as e:
        logger.error(f"Error deleting tax rate: {e}")
        messages.error(request, f'Error: {str(e)}')
    return htmx_redirect(reverse('core:tax_rate_list'))


# =============================================================================
# UNIT OF MEASURE — modals
# =============================================================================

@login_required
def unit_of_measure_modal_form(request, pk=None):
    """Create or edit unit of measure via modal."""
    if pk:
        unit        = get_object_or_404(UnitOfMeasure, pk=pk)
        is_edit     = True
        modal_title = f'Edit Unit: {unit.name}'
    else:
        unit        = None
        is_edit     = False
        modal_title = 'Create Unit of Measure'

    if request.method == 'POST':
        form = UnitOfMeasureForm(request.POST, instance=unit)
        if form.is_valid():
            try:
                with transaction.atomic():
                    unit   = form.save()
                    action = 'updated' if is_edit else 'created'
                    messages.success(
                        request, f'Unit "{unit.name}" {action} successfully!'
                    )
                    return htmx_redirect(reverse('core:unit_of_measure_list'))
            except ValidationError as e:
                form.add_error(None, str(e))
            except Exception as e:
                logger.error(f"Error saving unit of measure: {e}")
                form.add_error(None, f'Unexpected error: {str(e)}')
        else:
            logger.warning(f"UnitOfMeasureForm errors: {form.errors}")

        return render(request, 'core/units/_modal_form.html', {
            'form':        form,
            'unit':        unit,
            'is_edit':     is_edit,
            'modal_title': modal_title,
        })

    form = UnitOfMeasureForm(instance=unit)
    return render(request, 'core/units/_modal_form.html', {
        'form':        form,
        'unit':        unit,
        'is_edit':     is_edit,
        'modal_title': modal_title,
    })


@login_required
def unit_of_measure_delete_modal(request, pk):
    unit       = get_object_or_404(UnitOfMeasure, pk=pk)
    can_delete = unit.can_be_deleted()
    warnings   = unit.get_deletion_warnings()
    errors     = [] if can_delete else [
        'Unit has dependent units or is in use by inventory/uniform items.'
    ]

    if request.method == 'POST':
        if not can_delete:
            messages.error(
                request, 'Cannot delete — unit has dependants or is in use.'
            )
        else:
            try:
                name = unit.name
                unit.delete()
                messages.success(request, f'Unit "{name}" deleted.')
            except Exception as e:
                logger.error(f"Error deleting unit: {e}")
                messages.error(request, f'Error: {str(e)}')
        return htmx_redirect(reverse('core:unit_of_measure_list'))

    return render(request, 'core/modals/delete_confirmation.html', {
        'object':       unit,
        'object_name':  'Unit of Measure',
        'object_title': unit.name,
        'can_delete':   can_delete,
        'warnings':     warnings,
        'errors':       errors,
        'delete_url':   'core:unit_of_measure_delete_modal',
    })


@login_required
@require_http_methods(["POST"])
def unit_of_measure_delete(request, pk):
    unit = get_object_or_404(UnitOfMeasure, pk=pk)

    if not unit.can_be_deleted():
        messages.error(
            request,
            'Unit cannot be deleted — it has dependants or is in use.'
        )
        return htmx_redirect(reverse('core:unit_of_measure_list'))

    try:
        name = unit.name
        unit.delete()
        messages.success(request, f'Unit "{name}" deleted.')
    except Exception as e:
        logger.error(f"Error deleting unit: {e}")
        messages.error(request, f'Error: {str(e)}')

    return htmx_redirect(reverse('core:unit_of_measure_list'))


# =============================================================================
# BULK OPERATIONS
# =============================================================================

@login_required
def bulk_close_periods_modal(request):
    today = get_school_today()

    closeable_periods = FiscalPeriod.objects.filter(
        end_date__lt=today,
        is_closed=False,
        is_locked=False,
    ).select_related('fiscal_year').order_by('end_date')[:20]

    if request.method == 'POST':
        period_ids   = request.POST.getlist('periods')
        if not period_ids:
            messages.error(request, 'No periods selected.')
        else:
            closed_count = 0
            close_errors = []
            with transaction.atomic():
                for period in FiscalPeriod.objects.filter(
                    id__in=period_ids,
                    is_closed=False,
                    is_locked=False,
                ):
                    try:
                        period.close_period(user=request.user)
                        closed_count += 1
                    except Exception as e:
                        logger.error(f"Error closing period {period}: {e}")
                        close_errors.append(f"{period.name}: {str(e)}")

            if closed_count:
                messages.success(
                    request,
                    f'Successfully closed {closed_count} period(s).'
                )
            if close_errors:
                messages.warning(
                    request,
                    f'Failed to close some periods: {"; ".join(close_errors)}'
                )

        return htmx_redirect(reverse('core:fiscal_management'))

    return render(request, 'core/modals/bulk_close_periods.html', {
        'periods': closeable_periods,
        'count':   closeable_periods.count(),
    })


@login_required
@require_http_methods(["POST"])
def bulk_close_periods(request):
    """Legacy direct bulk-close POST."""
    period_ids = request.POST.getlist('periods')

    if not period_ids:
        messages.error(request, 'No periods selected.')
        return htmx_redirect(reverse('core:fiscal_management'))

    closed_count = 0
    for period in FiscalPeriod.objects.filter(
        id__in=period_ids,
        is_closed=False,
        is_locked=False,
    ):
        try:
            period.close_period(user=request.user)
            closed_count += 1
        except Exception as e:
            logger.error(f"Error closing period {period}: {e}")

    messages.success(request, f'Successfully closed {closed_count} period(s).')
    return htmx_redirect(reverse('core:fiscal_management'))


# =============================================================================
# STANDARD UNITS — modal
# =============================================================================

@login_required
def create_standard_units_modal(request):
    existing_count = UnitOfMeasure.objects.count()

    if request.method == 'POST':
        try:
            created_units = UnitOfMeasure.create_standard_units()
            messages.success(
                request,
                f'Created/verified {len(created_units)} standard unit(s) of measure.'
            )
        except Exception as e:
            logger.error(f"Error creating standard units: {e}")
            messages.error(request, f'Error: {str(e)}')
        return htmx_redirect(reverse('core:unit_of_measure_list'))

    return render(request, 'core/modals/create_standard_units.html', {
        'existing_count': existing_count,
        'has_existing':   existing_count > 0,
    })


@login_required
@require_http_methods(["POST"])
def create_standard_units(request):
    """Legacy direct-POST."""
    try:
        created_units = UnitOfMeasure.create_standard_units()
        messages.success(
            request,
            f'Created/verified {len(created_units)} standard unit(s) of measure.'
        )
    except Exception as e:
        logger.error(f"Error creating standard units: {e}")
        messages.error(request, f'Error: {str(e)}')
    return htmx_redirect(reverse('core:unit_of_measure_list'))