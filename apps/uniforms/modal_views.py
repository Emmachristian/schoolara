# uniforms/modal_views.py

"""
Modal Views for Uniform Management

This module contains modal views for the uniforms app.
These are lightweight views that return HTML partials for modals.

IMPORTANT: This module does NOT contain form modals for create/edit operations.
Create and Edit operations use full template pages in views.py instead.

Modal types included:
- Delete confirmation modals
- Toggle action modals (activate/deactivate)  
- Quick view modals (preview)
- Action confirmation modals (cancel, return, receive, etc.)
- Report option modals
- Bulk operation modals
- Utility modals
"""

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count, Sum, F

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
    MeasurementSession,
)

from core.utils import get_school_today


# =============================================================================
# MEASUREMENT TYPE MODALS
# =============================================================================

@login_required
def measurement_type_delete_modal(request, type_pk):
    """Return delete confirmation modal for measurement type"""
    measurement_type = get_object_or_404(MeasurementType, pk=type_pk)
    
    # Check if can be deleted
    can_delete = True
    warnings = []
    
    # Check for existing measurements
    measurement_count = measurement_type.student_measurements.count()
    if measurement_count > 0:
        can_delete = False
        warnings.append(f"Has {measurement_count} student measurement(s)")
    
    return render(request, 'uniforms/measurement_types/modals/delete_type.html', {
        'measurement_type': measurement_type,
        'can_delete': can_delete,
        'warnings': warnings,
    })


@login_required
def measurement_type_toggle_active_modal(request, type_pk):
    """Toggle active modal for measurement type"""
    measurement_type = get_object_or_404(MeasurementType, pk=type_pk)
    
    action = 'deactivate' if measurement_type.is_active else 'activate'
    
    return render(request, 'uniforms/measurement_types/modals/toggle_active.html', {
        'measurement_type': measurement_type,
        'action': action,
    })


@login_required
def measurement_type_quick_view_modal(request, type_pk):
    """Quick view modal for measurement type"""
    measurement_type = get_object_or_404(MeasurementType, pk=type_pk)
    
    measurement_count = measurement_type.student_measurements.count()
    verified_count = measurement_type.student_measurements.filter(is_verified=True).count()
    
    return render(request, 'uniforms/measurement_types/modals/quick_view.html', {
        'measurement_type': measurement_type,
        'measurement_count': measurement_count,
        'verified_count': verified_count,
    })


# =============================================================================
# STUDENT MEASUREMENT MODALS
# =============================================================================

@login_required
def student_measurement_delete_modal(request, measurement_pk):
    """Return delete confirmation modal for student measurement"""
    measurement = get_object_or_404(StudentMeasurement, pk=measurement_pk)
    
    # Check if can be deleted
    can_delete = True
    warnings = []
    
    if measurement.is_verified:
        warnings.append("Measurement has been verified")
    
    if measurement.is_current:
        warnings.append("This is the current measurement for this type")
    
    return render(request, 'uniforms/measurements/modals/delete_measurement.html', {
        'measurement': measurement,
        'can_delete': can_delete,
        'warnings': warnings,
    })


@login_required
def student_measurement_verify_modal(request, measurement_pk):
    """Return modal for verifying student measurement"""
    measurement = get_object_or_404(StudentMeasurement, pk=measurement_pk)
    
    warnings = []
    if measurement.is_verified:
        warnings.append("Measurement is already verified")
    
    return render(request, 'uniforms/measurements/modals/verify_measurement.html', {
        'measurement': measurement,
        'warnings': warnings,
    })


@login_required
def student_measurement_quick_view_modal(request, measurement_pk):
    """Quick view modal for student measurement"""
    measurement = get_object_or_404(
        StudentMeasurement.objects.select_related('student', 'measurement_type'),
        pk=measurement_pk
    )
    
    return render(request, 'uniforms/measurements/modals/quick_view.html', {
        'measurement': measurement,
    })


@login_required
def bulk_measurement_modal(request):
    """Return modal for bulk measurement entry"""
    from academics.models import Class, AcademicSession
    
    classes = Class.objects.filter(is_active=True).select_related('academic_level')
    sessions = AcademicSession.objects.filter(is_active=True)
    
    return render(request, 'uniforms/measurements/modals/bulk_measurement.html', {
        'classes': classes,
        'sessions': sessions,
    })


# =============================================================================
# UNIFORM SIZE MODALS
# =============================================================================

@login_required
def uniform_size_delete_modal(request, size_pk):
    """Return delete confirmation modal for uniform size"""
    size = get_object_or_404(UniformSize, pk=size_pk)
    
    # Check if can be deleted
    can_delete = True
    warnings = []
    
    # Check for items using this size
    item_count = size.uniform_items.count()
    if item_count > 0:
        can_delete = False
        warnings.append(f"Used by {item_count} uniform item(s)")
    
    # Check for stock records
    stock_count = size.stock_records.count()
    if stock_count > 0:
        can_delete = False
        warnings.append(f"Has {stock_count} stock record(s)")
    
    # Check for recommendations
    recommendation_count = size.student_recommendations.count()
    if recommendation_count > 0:
        warnings.append(f"Has {recommendation_count} student recommendation(s)")
    
    return render(request, 'uniforms/sizes/modals/delete_size.html', {
        'size': size,
        'can_delete': can_delete,
        'warnings': warnings,
    })


@login_required
def uniform_size_toggle_active_modal(request, size_pk):
    """Toggle active modal for uniform size"""
    size = get_object_or_404(UniformSize, pk=size_pk)
    
    action = 'deactivate' if size.is_active else 'activate'
    
    return render(request, 'uniforms/sizes/modals/toggle_active.html', {
        'size': size,
        'action': action,
    })


@login_required
def uniform_size_quick_view_modal(request, size_pk):
    """Quick view modal for uniform size"""
    size = get_object_or_404(UniformSize, pk=size_pk)
    
    item_count = size.uniform_items.count()
    stock_total = size.stock_records.aggregate(Sum('quantity'))['quantity__sum'] or 0
    
    return render(request, 'uniforms/sizes/modals/quick_view.html', {
        'size': size,
        'item_count': item_count,
        'stock_total': stock_total,
    })


# =============================================================================
# UNIFORM ITEM MODALS
# =============================================================================

@login_required
def uniform_item_delete_modal(request, item_pk):
    """Return delete confirmation modal for uniform item"""
    item = get_object_or_404(UniformItem, pk=item_pk)
    
    # Check if can be deleted
    can_delete = True
    warnings = []
    
    # Check for stock
    if item.current_stock > 0:
        can_delete = False
        warnings.append(f"Has {item.current_stock} units in stock")
    
    # Check for sales
    sale_count = item.sale_items.count()
    if sale_count > 0:
        warnings.append(f"Has {sale_count} sale record(s)")
    
    # Check for purchase orders
    po_count = item.purchase_order_items.count()
    if po_count > 0:
        warnings.append(f"Has {po_count} purchase order(s)")
    
    return render(request, 'uniforms/items/modals/delete_item.html', {
        'item': item,
        'can_delete': can_delete,
        'warnings': warnings,
    })


@login_required
def uniform_item_toggle_active_modal(request, item_pk):
    """Toggle active modal for uniform item"""
    item = get_object_or_404(UniformItem, pk=item_pk)
    
    action = 'deactivate' if item.is_active else 'activate'
    
    return render(request, 'uniforms/items/modals/toggle_active.html', {
        'item': item,
        'action': action,
    })


@login_required
def uniform_item_quick_view_modal(request, item_pk):
    """Quick view modal for uniform item"""
    item = get_object_or_404(UniformItem, pk=item_pk)
    
    total_sales = item.sale_items.aggregate(Sum('quantity'))['quantity__sum'] or 0
    
    return render(request, 'uniforms/items/modals/quick_view.html', {
        'item': item,
        'total_sales': total_sales,
    })


@login_required
def stock_adjustment_modal(request, item_pk):
    """Return modal for adjusting stock levels"""
    item = get_object_or_404(UniformItem, pk=item_pk)
    
    return render(request, 'uniforms/items/modals/stock_adjustment.html', {
        'item': item,
    })


@login_required
def stock_transfer_modal(request, item_pk):
    """Return modal for transferring stock between locations"""
    item = get_object_or_404(UniformItem, pk=item_pk)
    
    stock_records = item.stock_records.select_related('size')
    
    return render(request, 'uniforms/items/modals/stock_transfer.html', {
        'item': item,
        'stock_records': stock_records,
    })


# =============================================================================
# PURCHASE ORDER MODALS
# =============================================================================

@login_required
def purchase_order_delete_modal(request, po_pk):
    """Return delete confirmation modal for purchase order"""
    po = get_object_or_404(UniformPurchaseOrder, pk=po_pk)
    
    # Check if can be deleted
    can_delete = True
    warnings = []
    
    if po.status not in ['DRAFT', 'CANCELLED']:
        can_delete = False
        warnings.append(f"Purchase order is in '{po.get_status_display()}' status")
    
    if po.journal_entry:
        can_delete = False
        warnings.append("Has associated journal entry")
    
    return render(request, 'uniforms/purchase_orders/modals/delete_po.html', {
        'po': po,
        'can_delete': can_delete,
        'warnings': warnings,
    })


@login_required
def purchase_order_submit_modal(request, po_pk):
    """Return modal for submitting purchase order"""
    po = get_object_or_404(UniformPurchaseOrder, pk=po_pk)
    
    warnings = []
    if po.status != 'DRAFT':
        warnings.append("Purchase order is not in draft status")
    
    if not po.items.exists():
        warnings.append("Purchase order has no items")
    
    return render(request, 'uniforms/purchase_orders/modals/submit_po.html', {
        'po': po,
        'warnings': warnings,
    })


@login_required
def purchase_order_approve_modal(request, po_pk):
    """Return modal for approving purchase order"""
    po = get_object_or_404(UniformPurchaseOrder, pk=po_pk)
    
    warnings = []
    if po.status != 'SUBMITTED':
        warnings.append("Purchase order is not in submitted status")
    
    return render(request, 'uniforms/purchase_orders/modals/approve_po.html', {
        'po': po,
        'warnings': warnings,
    })


@login_required
def purchase_order_receive_modal(request, po_pk):
    """Return modal for receiving purchase order goods"""
    po = get_object_or_404(UniformPurchaseOrder, pk=po_pk)
    
    warnings = []
    if po.status not in ['ORDERED', 'PARTIAL']:
        warnings.append("Purchase order is not ready for receiving")
    
    items = po.items.select_related('uniform_item', 'size')
    
    return render(request, 'uniforms/purchase_orders/modals/receive_goods.html', {
        'po': po,
        'items': items,
        'warnings': warnings,
    })


@login_required
def purchase_order_cancel_modal(request, po_pk):
    """Return modal for cancelling purchase order"""
    po = get_object_or_404(UniformPurchaseOrder, pk=po_pk)
    
    warnings = []
    if po.status in ['RECEIVED', 'CANCELLED']:
        warnings.append(f"Purchase order is already {po.get_status_display()}")
    
    if po.journal_entry:
        warnings.append("Has associated journal entry that will need to be reversed")
    
    return render(request, 'uniforms/purchase_orders/modals/cancel_po.html', {
        'po': po,
        'warnings': warnings,
    })


@login_required
def purchase_order_quick_view_modal(request, po_pk):
    """Quick view modal for purchase order"""
    po = get_object_or_404(
        UniformPurchaseOrder.objects.select_related('fiscal_period'),
        pk=po_pk
    )
    
    item_count = po.items.count()
    
    return render(request, 'uniforms/purchase_orders/modals/quick_view.html', {
        'po': po,
        'item_count': item_count,
    })


# =============================================================================
# UNIFORM SALE MODALS
# =============================================================================

@login_required
def uniform_sale_delete_modal(request, sale_pk):
    """Return delete confirmation modal for uniform sale"""
    sale = get_object_or_404(UniformSale, pk=sale_pk)
    
    # Check if can be deleted
    can_delete = True
    warnings = []
    
    if sale.status not in ['DRAFT']:
        can_delete = False
        warnings.append(f"Sale is in '{sale.get_status_display()}' status")
    
    if sale.fee_invoice:
        can_delete = False
        warnings.append("Has associated invoice")
    
    if sale.journal_entry:
        can_delete = False
        warnings.append("Has associated journal entry")
    
    if sale.cancelled or sale.returned:
        warnings.append("Sale has already been cancelled or returned")
    
    return render(request, 'uniforms/sales/modals/delete_sale.html', {
        'sale': sale,
        'can_delete': can_delete,
        'warnings': warnings,
    })


@login_required
def uniform_sale_cancel_modal(request, sale_pk):
    """Return modal for cancelling uniform sale"""
    sale = get_object_or_404(UniformSale, pk=sale_pk)
    
    can_cancel, reason = sale.can_be_cancelled()
    warnings = []
    
    if not can_cancel:
        warnings.append(reason)
    
    if sale.paid_amount > 0:
        warnings.append(f"Customer has paid {sale.paid_amount:,.2f} - refund may be needed")
    
    return render(request, 'uniforms/sales/modals/cancel_sale.html', {
        'sale': sale,
        'can_cancel': can_cancel,
        'warnings': warnings,
    })


@login_required
def uniform_sale_return_modal(request, sale_pk):
    """Return modal for processing uniform sale return"""
    sale = get_object_or_404(UniformSale, pk=sale_pk)
    
    can_return, reason = sale.can_be_returned()
    warnings = []
    
    if not can_return:
        warnings.append(reason)
    
    if sale.paid_amount > 0:
        warnings.append(f"Customer has paid {sale.paid_amount:,.2f} - refund may be needed")
    
    items = sale.items.select_related('uniform_item', 'size')
    
    return render(request, 'uniforms/sales/modals/return_sale.html', {
        'sale': sale,
        'items': items,
        'can_return': can_return,
        'warnings': warnings,
    })


@login_required
def uniform_sale_issue_modal(request, sale_pk):
    """Return modal for issuing uniform to student"""
    sale = get_object_or_404(UniformSale, pk=sale_pk)
    
    warnings = []
    if sale.status == 'ISSUED':
        warnings.append("Items have already been issued")
    
    if sale.status == 'DRAFT':
        warnings.append("Sale is still in draft - finalize first")
    
    if sale.balance > 0:
        warnings.append(f"Outstanding balance: {sale.balance:,.2f}")
    
    items = sale.items.select_related('uniform_item', 'size')
    
    return render(request, 'uniforms/sales/modals/issue_items.html', {
        'sale': sale,
        'items': items,
        'warnings': warnings,
    })


@login_required
def uniform_sale_quick_view_modal(request, sale_pk):
    """Quick view modal for uniform sale"""
    sale = get_object_or_404(
        UniformSale.objects.select_related('student', 'academic_session'),
        pk=sale_pk
    )
    
    item_count = sale.items.count()
    
    return render(request, 'uniforms/sales/modals/quick_view.html', {
        'sale': sale,
        'item_count': item_count,
    })


@login_required
def uniform_sale_create_invoice_modal(request, sale_pk):
    """Return modal for creating invoice from uniform sale"""
    sale = get_object_or_404(UniformSale, pk=sale_pk)
    
    has_invoice = sale.fee_invoice is not None
    warnings = []
    
    if has_invoice:
        warnings.append("Invoice already exists for this sale")
    
    return render(request, 'uniforms/sales/modals/create_invoice.html', {
        'sale': sale,
        'has_invoice': has_invoice,
        'warnings': warnings,
    })


@login_required
def uniform_sale_record_payment_modal(request, sale_pk):
    """Return modal for recording payment for uniform sale"""
    sale = get_object_or_404(UniformSale, pk=sale_pk)
    
    warnings = []
    if sale.balance <= 0:
        warnings.append("Sale is fully paid")
    
    return render(request, 'uniforms/sales/modals/record_payment.html', {
        'sale': sale,
        'warnings': warnings,
    })


# =============================================================================
# STUDENT UNIFORM SIZE MODALS
# =============================================================================

@login_required
def student_uniform_size_delete_modal(request, size_rec_pk):
    """Return delete confirmation modal for student uniform size"""
    size_rec = get_object_or_404(StudentUniformSize, pk=size_rec_pk)
    
    can_delete = True
    warnings = []
    
    if size_rec.is_current:
        warnings.append("This is the current size recommendation")
    
    return render(request, 'uniforms/student_sizes/modals/delete_size_rec.html', {
        'size_rec': size_rec,
        'can_delete': can_delete,
        'warnings': warnings,
    })


@login_required
def student_uniform_size_quick_view_modal(request, size_rec_pk):
    """Quick view modal for student uniform size"""
    size_rec = get_object_or_404(
        StudentUniformSize.objects.select_related('student', 'uniform_item', 'recommended_size'),
        pk=size_rec_pk
    )
    
    return render(request, 'uniforms/student_sizes/modals/quick_view.html', {
        'size_rec': size_rec,
    })


@login_required
def bulk_size_recommendation_modal(request):
    """Return modal for bulk size recommendation"""
    from academics.models import Class
    
    classes = Class.objects.filter(is_active=True).select_related('academic_level')
    items = UniformItem.objects.filter(is_active=True, requires_sizing=True)
    
    return render(request, 'uniforms/student_sizes/modals/bulk_recommendation.html', {
        'classes': classes,
        'items': items,
    })


# =============================================================================
# MEASUREMENT SESSION MODALS
# =============================================================================

@login_required
def measurement_session_delete_modal(request, session_pk):
    """Return delete confirmation modal for measurement session"""
    session = get_object_or_404(MeasurementSession, pk=session_pk)
    
    can_delete = True
    warnings = []
    
    if session.status == 'COMPLETED':
        warnings.append("Session is completed")
    
    if session.total_measurements_taken > 0:
        warnings.append(f"Has {session.total_measurements_taken} measurement(s) recorded")
    
    return render(request, 'uniforms/measurement_sessions/modals/delete_session.html', {
        'session': session,
        'can_delete': can_delete,
        'warnings': warnings,
    })


@login_required
def measurement_session_start_modal(request, session_pk):
    """Return modal for starting measurement session"""
    session = get_object_or_404(MeasurementSession, pk=session_pk)
    
    warnings = []
    if session.status != 'PLANNED':
        warnings.append(f"Session is not in planned status (current: {session.get_status_display()})")
    
    return render(request, 'uniforms/measurement_sessions/modals/start_session.html', {
        'session': session,
        'warnings': warnings,
    })


@login_required
def measurement_session_complete_modal(request, session_pk):
    """Return modal for completing measurement session"""
    session = get_object_or_404(MeasurementSession, pk=session_pk)
    
    warnings = []
    if session.status != 'IN_PROGRESS':
        warnings.append(f"Session is not in progress (current: {session.get_status_display()})")
    
    if session.total_measurements_taken == 0:
        warnings.append("No measurements have been recorded")
    
    return render(request, 'uniforms/measurement_sessions/modals/complete_session.html', {
        'session': session,
        'warnings': warnings,
    })


@login_required
def measurement_session_cancel_modal(request, session_pk):
    """Return modal for cancelling measurement session"""
    session = get_object_or_404(MeasurementSession, pk=session_pk)
    
    warnings = []
    if session.status == 'COMPLETED':
        warnings.append("Session is already completed")
    
    if session.total_measurements_taken > 0:
        warnings.append(f"Has {session.total_measurements_taken} measurement(s) recorded - these will not be deleted")
    
    return render(request, 'uniforms/measurement_sessions/modals/cancel_session.html', {
        'session': session,
        'warnings': warnings,
    })


@login_required
def measurement_session_quick_view_modal(request, session_pk):
    """Quick view modal for measurement session"""
    session = get_object_or_404(
        MeasurementSession.objects.select_related('academic_session'),
        pk=session_pk
    )
    
    return render(request, 'uniforms/measurement_sessions/modals/quick_view.html', {
        'session': session,
    })


# =============================================================================
# REPORT AND EXPORT MODALS
# =============================================================================

@login_required
def inventory_report_options_modal(request):
    """Return modal for inventory report options"""
    return render(request, 'uniforms/reports/modals/inventory_options.html')


@login_required
def sales_report_options_modal(request):
    """Return modal for sales report options"""
    from academics.models import AcademicSession
    
    sessions = AcademicSession.objects.filter(is_active=True)
    
    return render(request, 'uniforms/reports/modals/sales_options.html', {
        'sessions': sessions,
    })


@login_required
def measurement_report_options_modal(request):
    """Return modal for measurement report options"""
    from academics.models import AcademicSession, Class
    
    sessions = AcademicSession.objects.filter(is_active=True)
    classes = Class.objects.filter(is_active=True).select_related('academic_level')
    
    return render(request, 'uniforms/reports/modals/measurement_options.html', {
        'sessions': sessions,
        'classes': classes,
    })


@login_required
def stock_valuation_modal(request):
    """Return modal showing stock valuation"""
    from decimal import Decimal
    
    items = UniformItem.objects.filter(is_active=True)
    
    total_cost_value = items.aggregate(
        total=Sum(F('current_stock') * F('unit_cost'))
    )['total'] or Decimal('0.00')
    
    total_selling_value = items.aggregate(
        total=Sum(F('current_stock') * F('selling_price'))
    )['total'] or Decimal('0.00')
    
    potential_profit = total_selling_value - total_cost_value
    
    return render(request, 'uniforms/reports/modals/stock_valuation.html', {
        'total_cost_value': total_cost_value,
        'total_selling_value': total_selling_value,
        'potential_profit': potential_profit,
        'item_count': items.count(),
    })


# =============================================================================
# UTILITY MODALS
# =============================================================================

@login_required
def uniform_size_chart_modal(request):
    """Display uniform size chart reference"""
    sizes = UniformSize.objects.filter(is_active=True).order_by('size_type', 'display_order')
    
    return render(request, 'uniforms/utility/modals/size_chart.html', {
        'sizes': sizes,
    })


@login_required
def measurement_guide_modal(request):
    """Display measurement taking guide"""
    measurement_types = MeasurementType.objects.filter(
        is_active=True,
        category='UNIFORM'
    ).order_by('display_order')
    
    return render(request, 'uniforms/utility/modals/measurement_guide.html', {
        'measurement_types': measurement_types,
    })


@login_required
def uniform_care_guide_modal(request, item_pk):
    """Display care instructions for uniform item"""
    item = get_object_or_404(UniformItem, pk=item_pk)
    
    return render(request, 'uniforms/utility/modals/care_guide.html', {
        'item': item,
    })