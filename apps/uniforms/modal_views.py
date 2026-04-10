# uniforms/modal_views.py

"""
Modal Views for Uniform Management

Lightweight views that return HTML partials for HTMX-powered modals.
Full create/edit operations use complete pages in views.py.

CHANGES FROM ORIGINAL:
- Removed all MeasurementSession modal views (model removed):
    measurement_session_delete_modal
    measurement_session_start_modal
    measurement_session_complete_modal
    measurement_session_cancel_modal
    measurement_session_quick_view_modal
- Removed MeasurementSession from imports.
- Simplified bulk_measurement_modal — the measurement_session field no longer
  exists on BulkMeasurementForm; the modal now only needs class and session
  context from academics.
- Fixed duplicate stock_transfer_modal name conflict — the item-level variant
  is now named uniform_item_transfer_modal(item_pk) and the stock-record-level
  variant stays as stock_transfer_modal(stock_pk) so URLs can differentiate
  them cleanly.
- Removed uniform_care_guide_modal — the care_instructions field was removed
  from UniformItem (retail catalogue field, unused in business logic).
- Fixed uniform_sale_quick_view_modal select_related path:
  fiscal_period__related_academic_session (not the removed academic_session FK).
- Fixed purchase_order_receive_modal status guard to include 'APPROVED'
  matching the action view which accepts APPROVED, ORDERED, PARTIAL.
"""

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, F
from decimal import Decimal

from .models import (
    MeasurementType,
    StudentMeasurement,
    UniformSize,
    UniformItem,
    UniformStock,
    UniformPurchaseOrder,
    UniformPurchaseOrderItem,
    UniformSale,
    UniformSaleItem,
    StudentUniformSize,
)

from core.utils import get_school_today


# =============================================================================
# MEASUREMENT TYPE MODALS
# =============================================================================

@login_required
def measurement_type_delete_modal(request, type_pk):
    """Delete confirmation modal for a measurement type."""
    mt = get_object_or_404(MeasurementType, pk=type_pk)

    measurement_count = mt.student_measurements.count()
    can_delete = measurement_count == 0
    warnings   = []

    if measurement_count > 0:
        warnings.append(
            f"Cannot delete — {measurement_count} student measurement(s) "
            f"reference this type"
        )

    return render(request, 'uniforms/measurement_types/modals/delete_type.html', {
        'measurement_type':  mt,
        'can_delete':        can_delete,
        'warnings':          warnings,
    })


@login_required
def measurement_type_toggle_active_modal(request, type_pk):
    """Toggle active/inactive confirmation modal for a measurement type."""
    mt     = get_object_or_404(MeasurementType, pk=type_pk)
    action = 'deactivate' if mt.is_active else 'activate'

    return render(request, 'uniforms/measurement_types/modals/toggle_active.html', {
        'measurement_type': mt,
        'action':           action,
    })


@login_required
def measurement_type_quick_view_modal(request, type_pk):
    """Quick-view summary modal for a measurement type."""
    mt = get_object_or_404(MeasurementType, pk=type_pk)

    return render(request, 'uniforms/measurement_types/modals/quick_view.html', {
        'measurement_type':  mt,
        'measurement_count': mt.student_measurements.count(),
        'verified_count':    mt.student_measurements.filter(is_verified=True).count(),
        'current_count':     mt.student_measurements.filter(is_current=True).count(),
    })


# =============================================================================
# STUDENT MEASUREMENT MODALS
# =============================================================================

@login_required
def student_measurement_delete_modal(request, measurement_pk):
    """Delete confirmation modal for a student measurement."""
    m        = get_object_or_404(StudentMeasurement, pk=measurement_pk)
    warnings = []

    if m.is_verified:
        warnings.append("This measurement has been verified")
    if m.is_current:
        warnings.append(
            "This is the current measurement for this type — "
            "deleting it will leave no current record until a new one is saved"
        )

    return render(request, 'uniforms/measurements/modals/delete_measurement.html', {
        'measurement': m,
        'can_delete':  True,   # always deletable; warnings are advisory
        'warnings':    warnings,
    })


@login_required
def student_measurement_verify_modal(request, measurement_pk):
    """Verification confirmation modal for a student measurement."""
    m        = get_object_or_404(StudentMeasurement, pk=measurement_pk)
    warnings = []

    if m.is_verified:
        warnings.append("This measurement is already verified")

    return render(request, 'uniforms/measurements/modals/verify_measurement.html', {
        'measurement': m,
        'warnings':    warnings,
    })


@login_required
def student_measurement_quick_view_modal(request, measurement_pk):
    """Quick-view summary modal for a student measurement."""
    m = get_object_or_404(
        StudentMeasurement.objects.select_related(
            'student', 'measurement_type__unit', 'academic_session'
        ),
        pk=measurement_pk,
    )
    return render(request, 'uniforms/measurements/modals/quick_view.html', {
        'measurement': m,
    })


@login_required
def bulk_measurement_modal(request):
    """
    Modal for setting up a bulk measurement run.

    Provides class and session context for the BulkMeasurementForm.
    The measurement_session field no longer exists — each measurement is
    recorded directly as a StudentMeasurement with context=UNIFORM_ORDER.
    """
    from academics.models import Class, AcademicSession

    classes  = Class.objects.filter(is_active=True).select_related('academic_level')
    sessions = AcademicSession.objects.filter(is_active=True).order_by('-start_date')

    return render(request, 'uniforms/measurements/modals/bulk_measurement.html', {
        'classes':  classes,
        'sessions': sessions,
    })


# =============================================================================
# UNIFORM SIZE MODALS
# =============================================================================

@login_required
def uniform_size_delete_modal(request, size_pk):
    """Delete confirmation modal for a uniform size."""
    size = get_object_or_404(UniformSize, pk=size_pk)

    item_count           = size.uniform_items.count()
    stock_count          = size.stock_records.count()
    recommendation_count = size.student_recommendations.count()

    can_delete = item_count == 0 and stock_count == 0
    warnings   = []

    if item_count > 0:
        warnings.append(f"Cannot delete — used by {item_count} uniform item(s)")
    if stock_count > 0:
        warnings.append(f"Cannot delete — has {stock_count} stock record(s)")
    if recommendation_count > 0:
        warnings.append(
            f"{recommendation_count} student size recommendation(s) reference this size"
        )

    return render(request, 'uniforms/sizes/modals/delete_size.html', {
        'size':       size,
        'can_delete': can_delete,
        'warnings':   warnings,
    })


@login_required
def uniform_size_toggle_active_modal(request, size_pk):
    """Toggle active/inactive confirmation modal for a uniform size."""
    size   = get_object_or_404(UniformSize, pk=size_pk)
    action = 'deactivate' if size.is_active else 'activate'

    return render(request, 'uniforms/sizes/modals/toggle_active.html', {
        'size':   size,
        'action': action,
    })


@login_required
def uniform_size_quick_view_modal(request, size_pk):
    """Quick-view summary modal for a uniform size."""
    size = get_object_or_404(UniformSize, pk=size_pk)

    stock_total = (
        size.stock_records.aggregate(Sum('quantity'))['quantity__sum'] or 0
    )

    return render(request, 'uniforms/sizes/modals/quick_view.html', {
        'size':        size,
        'item_count':  size.uniform_items.count(),
        'stock_total': stock_total,
    })


# =============================================================================
# UNIFORM ITEM MODALS
# =============================================================================

@login_required
def uniform_item_delete_modal(request, item_pk):
    """Delete confirmation modal for a uniform item."""
    item       = get_object_or_404(UniformItem, pk=item_pk)
    can_delete = True
    warnings   = []

    if item.current_stock > 0:
        can_delete = False
        warnings.append(
            f"Cannot delete — {item.current_stock} unit(s) in stock. "
            f"Adjust stock to zero first."
        )
    if item.sale_items.exists():
        warnings.append(
            f"{item.sale_items.count()} historical sale record(s) — "
            f"history will be preserved after deletion"
        )
    if item.purchase_order_items.exists():
        warnings.append(
            f"{item.purchase_order_items.count()} purchase order line(s) reference this item"
        )

    return render(request, 'uniforms/items/modals/delete_item.html', {
        'item':       item,
        'can_delete': can_delete,
        'warnings':   warnings,
    })


@login_required
def uniform_item_toggle_active_modal(request, item_pk):
    """Toggle active/inactive confirmation modal for a uniform item."""
    item   = get_object_or_404(UniformItem, pk=item_pk)
    action = 'deactivate' if item.is_active else 'activate'

    return render(request, 'uniforms/items/modals/toggle_active.html', {
        'item':   item,
        'action': action,
    })


@login_required
def uniform_item_quick_view_modal(request, item_pk):
    """Quick-view summary modal for a uniform item."""
    item = get_object_or_404(UniformItem, pk=item_pk)

    stock_records = item.stock_records.select_related('size').order_by(
        'size__display_order'
    )
    total_sold = (
        item.sale_items.aggregate(Sum('quantity'))['quantity__sum'] or 0
    )

    return render(request, 'uniforms/items/modals/quick_view.html', {
        'item':          item,
        'stock_records': stock_records,
        'total_sold':    total_sold,
    })


@login_required
def stock_adjustment_modal(request, item_pk):
    """Modal for adjusting stock on an unsized item."""
    item = get_object_or_404(UniformItem, pk=item_pk)

    # Get the unsized stock record if it exists so the modal can show
    # the current quantity before adjustment.
    try:
        stock = UniformStock.objects.get(uniform_item=item, size__isnull=True)
    except UniformStock.DoesNotExist:
        stock = None

    return render(request, 'uniforms/items/modals/stock_adjustment.html', {
        'item':  item,
        'stock': stock,
    })


@login_required
def uniform_item_transfer_modal(request, item_pk):
    """
    Modal for transferring stock between size variants of an item.

    Renamed from stock_transfer_modal(item_pk) to avoid a name conflict
    with stock_transfer_modal(stock_pk) in the stock section below.
    URLs should map to this view when the context is an item (not a stock record).
    """
    item          = get_object_or_404(UniformItem, pk=item_pk)
    stock_records = item.stock_records.select_related('size').order_by(
        'size__display_order'
    )

    return render(request, 'uniforms/items/modals/stock_transfer.html', {
        'item':          item,
        'stock_records': stock_records,
    })


# =============================================================================
# PURCHASE ORDER MODALS
# =============================================================================

@login_required
def purchase_order_delete_modal(request, po_pk):
    """Delete confirmation modal for a purchase order."""
    po         = get_object_or_404(UniformPurchaseOrder, pk=po_pk)
    can_delete = po.status == 'DRAFT'
    warnings   = []

    if po.status != 'DRAFT':
        warnings.append(
            f"Cannot delete — PO is in '{po.get_status_display()}' status. "
            f"Only draft purchase orders can be deleted."
        )
    if po.journal_entry:
        warnings.append("Has an associated journal entry")

    return render(request, 'uniforms/purchase_orders/modals/delete_po.html', {
        'po':         po,
        'can_delete': can_delete,
        'warnings':   warnings,
    })


@login_required
def purchase_order_submit_modal(request, po_pk):
    """Submission confirmation modal for a purchase order."""
    po       = get_object_or_404(UniformPurchaseOrder, pk=po_pk)
    warnings = []

    if po.status != 'DRAFT':
        warnings.append(
            f"PO is not in draft status (current: {po.get_status_display()})"
        )
    if not po.items.exists():
        warnings.append("PO has no items — add items before submitting")

    return render(request, 'uniforms/purchase_orders/modals/submit_po.html', {
        'po':       po,
        'warnings': warnings,
    })


@login_required
def purchase_order_approve_modal(request, po_pk):
    """Approval confirmation modal for a purchase order."""
    po       = get_object_or_404(UniformPurchaseOrder, pk=po_pk)
    warnings = []

    if po.status != 'SUBMITTED':
        warnings.append(
            f"PO is not in submitted status (current: {po.get_status_display()})"
        )

    return render(request, 'uniforms/purchase_orders/modals/approve_po.html', {
        'po':       po,
        'warnings': warnings,
    })


@login_required
def purchase_order_receive_modal(request, po_pk):
    """
    Goods-receipt modal for a purchase order.

    Status guard matches purchase_order_receive() in views.py which
    accepts APPROVED, ORDERED, and PARTIAL.
    """
    po    = get_object_or_404(UniformPurchaseOrder, pk=po_pk)
    items = po.items.select_related('uniform_item', 'size')

    warnings = []
    if po.status not in ('APPROVED', 'ORDERED', 'PARTIAL'):
        warnings.append(
            f"PO is not ready for receiving (current: {po.get_status_display()}). "
            f"PO must be Approved, Ordered, or Partially Received."
        )

    return render(request, 'uniforms/purchase_orders/modals/receive_goods.html', {
        'po':       po,
        'items':    items,
        'warnings': warnings,
    })


@login_required
def purchase_order_cancel_modal(request, po_pk):
    """Cancellation confirmation modal for a purchase order."""
    po       = get_object_or_404(UniformPurchaseOrder, pk=po_pk)
    warnings = []

    if po.status in ('RECEIVED', 'CANCELLED'):
        warnings.append(
            f"PO is already {po.get_status_display()} — cannot cancel"
        )
    if po.journal_entry:
        warnings.append(
            "Has an associated journal entry that may need manual reversal"
        )

    return render(request, 'uniforms/purchase_orders/modals/cancel_po.html', {
        'po':       po,
        'warnings': warnings,
    })


@login_required
def purchase_order_quick_view_modal(request, po_pk):
    """Quick-view summary modal for a purchase order."""
    po = get_object_or_404(
        UniformPurchaseOrder.objects.select_related('fiscal_period'),
        pk=po_pk,
    )
    return render(request, 'uniforms/purchase_orders/modals/quick_view.html', {
        'po':         po,
        'item_count': po.items.count(),
    })


# =============================================================================
# UNIFORM SALE MODALS
# =============================================================================

@login_required
def uniform_sale_delete_modal(request, sale_pk):
    """Delete confirmation modal for a uniform sale."""
    sale = get_object_or_404(UniformSale, pk=sale_pk)

    can_delete = sale.status == 'DRAFT' and not sale.cancelled and not sale.returned
    warnings   = []

    if sale.status != 'DRAFT':
        warnings.append(
            f"Cannot delete — sale is in '{sale.get_status_display()}' status. "
            f"Only draft sales can be deleted."
        )
    if sale.fee_invoice:
        warnings.append("Has an associated fee invoice")
    if sale.journal_entry:
        warnings.append("Has an associated journal entry")
    if sale.cancelled or sale.returned:
        warnings.append("Sale has already been cancelled or returned")

    return render(request, 'uniforms/sales/modals/delete_sale.html', {
        'sale':       sale,
        'can_delete': can_delete,
        'warnings':   warnings,
    })


@login_required
def uniform_sale_cancel_modal(request, sale_pk):
    """Cancellation confirmation modal for a uniform sale."""
    sale = get_object_or_404(UniformSale, pk=sale_pk)

    can_cancel, block_reason = sale.can_be_cancelled()
    warnings = []

    if not can_cancel:
        warnings.append(block_reason)
    if sale.paid_amount > 0:
        warnings.append(
            f"Customer has paid {sale.paid_amount:,.2f} — "
            f"a refund may need to be processed separately"
        )

    return render(request, 'uniforms/sales/modals/cancel_sale.html', {
        'sale':       sale,
        'can_cancel': can_cancel,
        'warnings':   warnings,
    })


@login_required
def uniform_sale_return_modal(request, sale_pk):
    """Return-processing modal for a uniform sale."""
    sale = get_object_or_404(UniformSale, pk=sale_pk)

    can_return, block_reason = sale.can_be_returned()
    warnings = []

    if not can_return:
        warnings.append(block_reason)
    if sale.paid_amount > 0:
        warnings.append(
            f"Customer has paid {sale.paid_amount:,.2f} — "
            f"a refund may need to be processed separately"
        )

    items = sale.items.select_related('uniform_item', 'size')

    return render(request, 'uniforms/sales/modals/return_sale.html', {
        'sale':       sale,
        'items':      items,
        'can_return': can_return,
        'warnings':   warnings,
        'return_condition_choices': UniformSale.return_condition.field.choices,
    })


@login_required
def uniform_sale_issue_modal(request, sale_pk):
    """Issue-confirmation modal for a uniform sale."""
    sale = get_object_or_404(UniformSale, pk=sale_pk)

    warnings = []

    if sale.status == 'ISSUED':
        warnings.append("Items have already been issued")
    elif sale.status == 'DRAFT':
        warnings.append("Sale is still a draft — finalise it before issuing")
    elif sale.status not in ('PAID', 'PARTIAL'):
        warnings.append(
            f"Sale must be PAID or PARTIALLY PAID before issuing "
            f"(current: {sale.get_status_display()})"
        )

    if sale.balance > 0:
        warnings.append(
            f"Outstanding balance: {sale.balance:,.2f} — "
            f"items can still be issued if a partial payment was accepted"
        )

    items = sale.items.select_related('uniform_item', 'size')

    return render(request, 'uniforms/sales/modals/issue_items.html', {
        'sale':     sale,
        'items':    items,
        'warnings': warnings,
    })


@login_required
def uniform_sale_finalize_modal(request, sale_pk):
    """Finalisation confirmation modal for a draft uniform sale."""
    sale = get_object_or_404(UniformSale, pk=sale_pk)

    warnings = []

    if sale.status != 'DRAFT':
        warnings.append(
            f"Sale is not in DRAFT status (current: {sale.get_status_display()})"
        )
    if not sale.items.exists():
        warnings.append("Sale has no items — add items before finalising")

    return render(request, 'uniforms/sales/modals/finalize_sale.html', {
        'sale':     sale,
        'warnings': warnings,
    })


@login_required
def uniform_sale_quick_view_modal(request, sale_pk):
    """
    Quick-view summary modal for a uniform sale.

    Uses fiscal_period__related_academic_session in select_related —
    academic_session is a @property on UniformSale, not a DB field.
    """
    sale = get_object_or_404(
        UniformSale.objects.select_related(
            'student',
            'fiscal_period__related_academic_session',
            'payment_method',
        ),
        pk=sale_pk,
    )
    return render(request, 'uniforms/sales/modals/quick_view.html', {
        'sale':       sale,
        'item_count': sale.items.count(),
    })


# =============================================================================
# STUDENT UNIFORM SIZE MODALS
# =============================================================================

@login_required
def student_uniform_size_delete_modal(request, size_rec_pk):
    """Delete confirmation modal for a student uniform size recommendation."""
    rec      = get_object_or_404(StudentUniformSize, pk=size_rec_pk)
    warnings = []

    if rec.is_current:
        warnings.append(
            "This is the current size recommendation — deleting it will leave "
            "no current recommendation until a new measurement triggers a refresh"
        )

    return render(request, 'uniforms/student_sizes/modals/delete_size_rec.html', {
        'size_rec':  rec,
        'can_delete':True,   # always deletable; warning is advisory
        'warnings':  warnings,
    })


@login_required
def student_uniform_size_quick_view_modal(request, size_rec_pk):
    """Quick-view summary modal for a student uniform size recommendation."""
    rec = get_object_or_404(
        StudentUniformSize.objects.select_related(
            'student', 'uniform_item', 'recommended_size', 'academic_session'
        ),
        pk=size_rec_pk,
    )
    return render(request, 'uniforms/student_sizes/modals/quick_view.html', {
        'size_rec': rec,
    })

# =============================================================================
# UNIFORM STOCK MODALS
# =============================================================================

@login_required
def uniform_stock_delete_modal(request, stock_pk):
    """Delete confirmation modal for a stock record."""
    stock      = get_object_or_404(
        UniformStock.objects.select_related('uniform_item', 'size'), pk=stock_pk
    )
    can_delete = stock.quantity == 0 and stock.reserved_quantity == 0
    warnings   = []

    if stock.quantity > 0:
        warnings.append(
            f"Cannot delete — {stock.quantity} unit(s) in stock. "
            f"Adjust quantity to zero first."
        )
    if stock.reserved_quantity > 0:
        warnings.append(
            f"Cannot delete — {stock.reserved_quantity} reserved unit(s). "
            f"Release all reservations first."
        )

    sale_count = stock.uniform_item.sale_items.filter(size=stock.size).count()
    if sale_count > 0:
        warnings.append(
            f"{sale_count} historical sale(s) for this size — "
            f"history is preserved after deletion"
        )

    return render(request, 'uniforms/stock/modals/delete_stock.html', {
        'stock':      stock,
        'can_delete': can_delete,
        'warnings':   warnings,
    })


@login_required
def uniform_stock_quick_view_modal(request, stock_pk):
    """Quick-view summary modal for a stock record."""
    stock = get_object_or_404(
        UniformStock.objects.select_related('uniform_item', 'size'), pk=stock_pk
    )
    return render(request, 'uniforms/stock/modals/quick_view.html', {
        'stock': stock,
    })


@login_required
def stock_receive_modal(request, stock_pk):
    """Modal for recording stock received directly against a stock record."""
    stock = get_object_or_404(
        UniformStock.objects.select_related('uniform_item', 'size'), pk=stock_pk
    )
    return render(request, 'uniforms/stock/modals/receive_stock.html', {
        'stock': stock,
    })


@login_required
def stock_transfer_modal(request, stock_pk):
    """
    Modal for transferring stock from one size variant to another.

    Takes stock_pk (the source record) so the modal can pre-populate
    the from-size and show available alternatives.

    Note: The item-level transfer modal is uniform_item_transfer_modal(item_pk)
    — a separate view to avoid a name conflict.
    """
    stock = get_object_or_404(
        UniformStock.objects.select_related('uniform_item', 'size'), pk=stock_pk
    )
    other_records = (
        UniformStock.objects
        .filter(uniform_item=stock.uniform_item)
        .exclude(pk=stock.pk)
        .select_related('size')
        .order_by('size__display_order')
    )

    return render(request, 'uniforms/stock/modals/stock_transfer.html', {
        'stock':               stock,
        'other_stock_records': other_records,
    })


# =============================================================================
# REPORT AND EXPORT MODALS
# =============================================================================

@login_required
def inventory_report_options_modal(request):
    """Options modal for the inventory report."""
    return render(request, 'uniforms/reports/modals/inventory_options.html')


@login_required
def sales_report_options_modal(request):
    """Options modal for the sales report."""
    from academics.models import AcademicSession

    sessions = AcademicSession.objects.filter(is_active=True).order_by('-start_date')

    return render(request, 'uniforms/reports/modals/sales_options.html', {
        'sessions': sessions,
    })


@login_required
def measurement_report_options_modal(request):
    """Options modal for the measurement summary report."""
    from academics.models import AcademicSession, Class

    sessions = AcademicSession.objects.filter(is_active=True).order_by('-start_date')
    classes  = Class.objects.filter(is_active=True).select_related('academic_level')

    return render(request, 'uniforms/reports/modals/measurement_options.html', {
        'sessions': sessions,
        'classes':  classes,
    })


@login_required
def stock_valuation_modal(request):
    """Modal showing a quick stock valuation summary."""
    items = UniformItem.objects.filter(is_active=True)

    cost_value    = items.aggregate(
        total=Sum(F('current_stock') * F('unit_cost'))
    )['total'] or Decimal('0.00')

    selling_value = items.aggregate(
        total=Sum(F('current_stock') * F('selling_price'))
    )['total'] or Decimal('0.00')

    return render(request, 'uniforms/reports/modals/stock_valuation.html', {
        'total_cost_value':    cost_value,
        'total_selling_value': selling_value,
        'potential_profit':    selling_value - cost_value,
        'item_count':          items.count(),
    })


# =============================================================================
# UTILITY MODALS
# =============================================================================

@login_required
def uniform_size_chart_modal(request):
    """Size chart reference modal showing all active sizes with measurement ranges."""
    sizes = UniformSize.objects.filter(is_active=True).order_by(
        'size_type', 'display_order'
    )
    return render(request, 'uniforms/utility/modals/size_chart.html', {
        'sizes': sizes,
    })


@login_required
def measurement_guide_modal(request):
    """Measurement-taking guide modal for uniform measurements."""
    measurement_types = MeasurementType.objects.filter(
        is_active=True, category='UNIFORM'
    ).select_related('unit').order_by('display_order')

    return render(request, 'uniforms/utility/modals/measurement_guide.html', {
        'measurement_types': measurement_types,
    })