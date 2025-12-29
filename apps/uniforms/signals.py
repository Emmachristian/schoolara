# uniforms/signals.py

"""
Uniform Management Signals

Automatic triggers for:
- Invoice creation when sale is finalized
- Journal entry creation for accounting
- Stock updates and reservations
- Student account updates
- Automatic numbering
"""

from django.db.models.signals import (
    post_save, pre_save, post_delete, pre_delete
)
from django.dispatch import receiver
from django.db import transaction
from decimal import Decimal
import logging

from .models import (
    UniformSale, UniformSaleItem, UniformPurchaseOrder,
    UniformPurchaseOrderItem, UniformStock, StudentMeasurement,
    MeasurementSession
)
from .services import (
    UniformInvoiceService, UniformAccountingService,
    UniformStockService, UniformWorkflowService
)
from .utils import (
    generate_uniform_sale_number, generate_purchase_order_number,
    recommend_size_from_measurements
)

logger = logging.getLogger(__name__)


# =============================================================================
# UNIFORM SALE SIGNALS
# =============================================================================

@receiver(pre_save, sender=UniformSale)
def uniform_sale_pre_save(sender, instance, **kwargs):
    """
    Pre-save processing for uniform sale.
    - Generate sale number if not set
    - Ensure accounts are assigned
    """
    # Generate sale number if not set
    if not instance.sale_number:
        instance.sale_number = generate_uniform_sale_number()
        logger.info(f"Generated sale number: {instance.sale_number}")
    
    # Ensure fiscal period is set
    if not instance.fiscal_period:
        from core.models import FiscalPeriod
        instance.fiscal_period = FiscalPeriod.get_current_fiscal_period()
        if not instance.fiscal_period:
            logger.warning("No active fiscal period found for uniform sale")


@receiver(post_save, sender=UniformSale)
def uniform_sale_post_save(sender, instance, created, **kwargs):
    """
    Post-save processing for uniform sale.
    - Create invoice when status changes to PENDING/PAID
    - Create journal entry when finalized
    """
    # Skip if in raw mode (fixtures, migrations)
    if kwargs.get('raw', False):
        return
    
    # Only process for SALE type (not issuances/loans)
    if instance.sale_type != 'SALE':
        return
    
    # Skip if sale is DRAFT or CANCELLED
    if instance.status in ['DRAFT', 'CANCELLED']:
        return
    
    try:
        # Create invoice if needed and auto_create_invoice is True
        if instance.auto_create_invoice and not instance.fee_invoice:
            if instance.status in ['PENDING', 'PAID', 'PARTIAL']:
                logger.info(f"Auto-creating invoice for sale {instance.sale_number}")
                UniformInvoiceService.create_invoice_from_sale(instance)
        
        # Create journal entry if needed and auto_create_journal_entry is True
        if instance.auto_create_journal_entry and not instance.journal_entry:
            if instance.status in ['PENDING', 'PAID', 'PARTIAL', 'ISSUED']:
                logger.info(f"Auto-creating journal entry for sale {instance.sale_number}")
                UniformAccountingService.create_journal_entry_for_sale(instance)
        
        # Update invoice if it exists and amounts changed
        if instance.fee_invoice:
            # Check if amounts need updating
            invoice = instance.fee_invoice
            if (invoice.total_amount != instance.total_amount or 
                invoice.balance != instance.balance):
                logger.info(f"Updating invoice for sale {instance.sale_number}")
                UniformInvoiceService.update_invoice_from_sale(instance)
    
    except Exception as e:
        logger.error(f"Error in uniform_sale_post_save: {e}", exc_info=True)


@receiver(pre_delete, sender=UniformSale)
def uniform_sale_pre_delete(sender, instance, **kwargs):
    """
    Pre-delete processing for uniform sale.
    - Release reserved stock
    - Reverse journal entries
    """
    try:
        # Release reserved stock
        if instance.status in ['DRAFT', 'PENDING', 'PARTIAL']:
            logger.info(f"Releasing reserved stock for deleted sale {instance.sale_number}")
            UniformStockService.release_reserved_stock(instance)
        
        # Reverse journal entry if exists
        if instance.journal_entry and instance.journal_entry.status != 'REVERSED':
            logger.info(f"Reversing journal entry for deleted sale {instance.sale_number}")
            UniformAccountingService.reverse_journal_entry_for_sale(
                instance,
                reason="Sale deleted"
            )
    
    except Exception as e:
        logger.error(f"Error in uniform_sale_pre_delete: {e}", exc_info=True)


# =============================================================================
# UNIFORM SALE ITEM SIGNALS
# =============================================================================

@receiver(post_save, sender=UniformSaleItem)
def uniform_sale_item_post_save(sender, instance, created, **kwargs):
    """
    Post-save processing for sale item.
    - Recalculate sale totals
    """
    # Skip if in raw mode
    if kwargs.get('raw', False):
        return
    
    try:
        # Recalculate sale totals
        sale = instance.sale
        sale.calculate_totals()
        logger.debug(f"Recalculated totals for sale {sale.sale_number}")
    
    except Exception as e:
        logger.error(f"Error in uniform_sale_item_post_save: {e}", exc_info=True)


@receiver(post_delete, sender=UniformSaleItem)
def uniform_sale_item_post_delete(sender, instance, **kwargs):
    """
    Post-delete processing for sale item.
    - Recalculate sale totals
    """
    try:
        # Recalculate sale totals
        sale = instance.sale
        sale.calculate_totals()
        logger.debug(f"Recalculated totals after item deletion for sale {sale.sale_number}")
    
    except Exception as e:
        logger.error(f"Error in uniform_sale_item_post_delete: {e}", exc_info=True)


# =============================================================================
# UNIFORM PURCHASE ORDER SIGNALS
# =============================================================================

@receiver(pre_save, sender=UniformPurchaseOrder)
def purchase_order_pre_save(sender, instance, **kwargs):
    """
    Pre-save processing for purchase order.
    - Generate PO number if not set
    """
    # Generate PO number if not set
    if not instance.po_number:
        instance.po_number = generate_purchase_order_number()
        logger.info(f"Generated PO number: {instance.po_number}")
    
    # Set fiscal period if not set
    if not instance.fiscal_period:
        from core.models import FiscalPeriod
        instance.fiscal_period = FiscalPeriod.get_current_fiscal_period()


@receiver(post_save, sender=UniformPurchaseOrder)
def purchase_order_post_save(sender, instance, created, **kwargs):
    """
    Post-save processing for purchase order.
    - Update stock when status changes to RECEIVED
    - Create journal entry for goods receipt
    """
    # Skip if in raw mode
    if kwargs.get('raw', False):
        return
    
    # Only process if status is RECEIVED and journal entry not created
    if instance.status == 'RECEIVED' and instance.auto_create_journal_entry:
        if not instance.journal_entry:
            try:
                # Create journal entry for goods receipt
                create_purchase_order_journal_entry(instance)
            except Exception as e:
                logger.error(f"Error creating journal entry for PO: {e}", exc_info=True)


def create_purchase_order_journal_entry(purchase_order):
    """
    Create journal entry when goods are received.
    
    Entry:
    Debit: Inventory (Asset increases)
    Credit: Accounts Payable (Liability increases)
    """
    from finance.models import JournalEntry, JournalTransaction, Journal
    from core.models import FinancialSettings
    
    # Get default accounts
    settings = FinancialSettings.get_instance()
    if not settings:
        logger.warning("FinancialSettings not found, skipping journal entry")
        return
    
    inventory_account = settings.default_inventory_account
    payable_account = settings.default_payables_account
    
    if not inventory_account or not payable_account:
        logger.warning("Required accounts not configured, skipping journal entry")
        return
    
    # Get or create journal
    journal, _ = Journal.objects.get_or_create(
        journal_type='GENERAL',
        defaults={
            'name': 'General Journal',
            'description': 'General accounting journal'
        }
    )
    
    # Create journal entry
    entry = JournalEntry.objects.create(
        journal=journal,
        entry_number=f"JE-PO-{purchase_order.po_number}",
        entry_date=purchase_order.actual_delivery_date or purchase_order.order_date,
        fiscal_period=purchase_order.fiscal_period,
        reference_number=purchase_order.po_number,
        description=f"Goods receipt - PO {purchase_order.po_number} from {purchase_order.supplier_name}",
        status='POSTED'
    )
    
    # Debit: Inventory
    JournalTransaction.objects.create(
        journal_entry=entry,
        account=inventory_account,
        description=f"Uniform inventory receipt - PO {purchase_order.po_number}",
        amount=purchase_order.total_amount,
        is_debit=True
    )
    
    # Credit: Accounts Payable
    JournalTransaction.objects.create(
        journal_entry=entry,
        account=payable_account,
        description=f"Payable to {purchase_order.supplier_name} - PO {purchase_order.po_number}",
        amount=purchase_order.total_amount,
        is_debit=False
    )
    
    # Link entry to PO
    purchase_order.journal_entry = entry
    purchase_order.save()
    
    logger.info(f"Created journal entry {entry.entry_number} for PO {purchase_order.po_number}")


@receiver(post_save, sender=UniformPurchaseOrderItem)
def purchase_order_item_post_save(sender, instance, created, **kwargs):
    """
    Post-save processing for PO item.
    - Update stock when quantity_received changes
    """
    # Skip if in raw mode
    if kwargs.get('raw', False):
        return
    
    # If quantity_received changed, update stock
    if not created and instance.quantity_received > 0:
        try:
            # Get previous quantity_received
            if hasattr(instance, '_previous_quantity_received'):
                previous_qty = instance._previous_quantity_received
            else:
                previous_qty = 0
            
            # Calculate quantity newly received
            qty_change = instance.quantity_received - previous_qty
            
            if qty_change > 0:
                update_stock_from_purchase(instance, qty_change)
        
        except Exception as e:
            logger.error(f"Error updating stock from PO item: {e}", exc_info=True)


def update_stock_from_purchase(po_item, quantity):
    """Update stock levels when goods are received"""
    uniform_item = po_item.uniform_item
    size = po_item.size
    
    if uniform_item.requires_sizing and size:
        # Update size-specific stock
        stock, created = UniformStock.objects.get_or_create(
            uniform_item=uniform_item,
            size=size
        )
        stock.quantity += quantity
        stock.save()
        
        logger.info(
            f"Updated stock: {uniform_item.name} Size {size.name} +{quantity} "
            f"(now {stock.quantity})"
        )
    else:
        # Update total stock
        uniform_item.current_stock += quantity
        uniform_item.save()
        
        logger.info(
            f"Updated stock: {uniform_item.name} +{quantity} "
            f"(now {uniform_item.current_stock})"
        )


@receiver(pre_save, sender=UniformPurchaseOrderItem)
def purchase_order_item_pre_save(sender, instance, **kwargs):
    """
    Pre-save processing for PO item.
    - Store previous quantity_received for comparison
    """
    if instance.pk:
        try:
            previous = UniformPurchaseOrderItem.objects.get(pk=instance.pk)
            instance._previous_quantity_received = previous.quantity_received
        except UniformPurchaseOrderItem.DoesNotExist:
            instance._previous_quantity_received = 0


# =============================================================================
# STOCK UPDATE SIGNALS
# =============================================================================

@receiver(post_save, sender=UniformStock)
def uniform_stock_post_save(sender, instance, created, **kwargs):
    """
    Post-save processing for uniform stock.
    - Update parent item's total stock
    - Check for low stock alerts
    """
    # Skip if in raw mode
    if kwargs.get('raw', False):
        return
    
    try:
        # Update parent item's total stock if sized item
        uniform_item = instance.uniform_item
        
        if uniform_item.requires_sizing:
            # Recalculate total stock from all sizes
            total_stock = sum(
                stock.quantity 
                for stock in uniform_item.stock_records.all()
            )
            
            if uniform_item.current_stock != total_stock:
                uniform_item.current_stock = total_stock
                uniform_item.save(update_fields=['current_stock'])
                logger.debug(f"Updated total stock for {uniform_item.name}: {total_stock}")
        
        # Check for low stock
        if instance.available_quantity <= uniform_item.reorder_level:
            logger.warning(
                f"LOW STOCK ALERT: {uniform_item.name} Size {instance.size.name} - "
                f"Available: {instance.available_quantity}, Reorder Level: {uniform_item.reorder_level}"
            )
    
    except Exception as e:
        logger.error(f"Error in uniform_stock_post_save: {e}", exc_info=True)


# =============================================================================
# STUDENT MEASUREMENT SIGNALS
# =============================================================================

@receiver(post_save, sender=StudentMeasurement)
def student_measurement_post_save(sender, instance, created, **kwargs):
    """
    Post-save processing for student measurement.
    - Update size recommendations when measurements change
    """
    # Skip if in raw mode
    if kwargs.get('raw', False):
        return
    
    # Only process for current measurements
    if not instance.is_current:
        return
    
    try:
        # If this is a verified measurement, trigger size recommendation update
        if instance.is_verified:
            update_size_recommendations_for_student(instance.student, instance.academic_session)
    
    except Exception as e:
        logger.error(f"Error in student_measurement_post_save: {e}", exc_info=True)


def update_size_recommendations_for_student(student, academic_session):
    """
    Update all size recommendations for a student based on current measurements.
    """
    from .models import UniformItem, StudentUniformSize
    
    # Get all active uniform items
    uniform_items = UniformItem.objects.filter(
        is_active=True,
        requires_sizing=True
    )
    
    for uniform_item in uniform_items:
        try:
            # Get size recommendation
            recommendation = recommend_size_from_measurements(student, uniform_item)
            
            if recommendation['recommended_size']:
                # Create or update size recommendation
                StudentUniformSize.objects.update_or_create(
                    student=student,
                    uniform_item=uniform_item,
                    academic_session=academic_session,
                    is_current=True,
                    defaults={
                        'recommended_size': recommendation['recommended_size'],
                        'sizing_method': 'MEASURED',
                        'confidence_level': recommendation['confidence'],
                        'notes': recommendation['reason'],
                        'alternative_sizes': [
                            s.id for s in recommendation['alternative_sizes']
                        ] if recommendation['alternative_sizes'] else None
                    }
                )
                
                logger.info(
                    f"Updated size recommendation for {student.get_full_name()} - "
                    f"{uniform_item.name}: Size {recommendation['recommended_size'].name}"
                )
        
        except Exception as e:
            logger.error(
                f"Error updating size recommendation for {uniform_item.name}: {e}",
                exc_info=True
            )


@receiver(post_save, sender=MeasurementSession)
def measurement_session_post_save(sender, instance, created, **kwargs):
    """
    Post-save processing for measurement session.
    - Update statistics when session is completed
    """
    # Skip if in raw mode
    if kwargs.get('raw', False):
        return
    
    # Only process when status changes to COMPLETED
    if instance.status == 'COMPLETED':
        try:
            # Update session statistics
            update_measurement_session_stats(instance)
        except Exception as e:
            logger.error(f"Error updating measurement session stats: {e}", exc_info=True)


def update_measurement_session_stats(session):
    """Update statistics for a measurement session"""
    from django.db.models import Count, Q
    
    # Count unique students measured in this session
    students_measured = StudentMeasurement.objects.filter(
        measurement_date=session.session_date,
        academic_session=session.academic_session
    ).values('student').distinct().count()
    
    # Count total measurements taken
    total_measurements = StudentMeasurement.objects.filter(
        measurement_date=session.session_date,
        academic_session=session.academic_session
    ).count()
    
    # Update session
    session.total_students_measured = students_measured
    session.total_measurements_taken = total_measurements
    session.save(update_fields=['total_students_measured', 'total_measurements_taken'])
    
    logger.info(
        f"Updated measurement session {session.session_name}: "
        f"{students_measured} students, {total_measurements} measurements"
    )


# =============================================================================
# ACCOUNT BALANCE UPDATE SIGNALS
# =============================================================================

@receiver(post_save, sender=UniformSaleItem)
def update_uniform_item_accounts(sender, instance, created, **kwargs):
    """
    Ensure uniform items have accounting accounts assigned.
    """
    # Skip if in raw mode
    if kwargs.get('raw', False):
        return
    
    try:
        uniform_item = instance.uniform_item
        
        # Ensure accounts are assigned
        if not all([
            uniform_item.inventory_account,
            uniform_item.cogs_account,
            uniform_item.revenue_account
        ]):
            uniform_item.ensure_accounts_assigned()
            logger.debug(f"Assigned accounts to {uniform_item.name}")
    
    except Exception as e:
        logger.error(f"Error assigning accounts to uniform item: {e}", exc_info=True)


# =============================================================================
# LOW STOCK NOTIFICATIONS
# =============================================================================

@receiver(post_save, sender=UniformStock)
def check_low_stock_notification(sender, instance, **kwargs):
    """
    Check for low stock and trigger notifications.
    """
    # Skip if in raw mode
    if kwargs.get('raw', False):
        return
    
    try:
        uniform_item = instance.uniform_item
        
        # Check if below reorder level
        if instance.available_quantity <= uniform_item.reorder_level:
            # Log low stock warning
            logger.warning(
                f"LOW STOCK: {uniform_item.name} Size {instance.size.name} - "
                f"Available: {instance.available_quantity}, "
                f"Reorder Level: {uniform_item.reorder_level}"
            )
            
            # TODO: Send notification to inventory manager
            # This could trigger an email, SMS, or in-app notification
            # Example:
            # send_low_stock_notification(uniform_item, instance)
        
        # Check if out of stock
        if instance.available_quantity == 0:
            logger.error(
                f"OUT OF STOCK: {uniform_item.name} Size {instance.size.name}"
            )
            
            # TODO: Send urgent notification
            # send_out_of_stock_notification(uniform_item, instance)
    
    except Exception as e:
        logger.error(f"Error in low stock check: {e}", exc_info=True)


# =============================================================================
# AUDIT LOG SIGNALS
# =============================================================================

@receiver(post_save, sender=UniformSale)
def log_uniform_sale_changes(sender, instance, created, **kwargs):
    """
    Log important changes to uniform sales for audit trail.
    """
    # Skip if in raw mode
    if kwargs.get('raw', False):
        return
    
    try:
        if created:
            logger.info(
                f"AUDIT: Uniform sale created - {instance.sale_number} - "
                f"Student: {instance.student.get_full_name()} - "
                f"Amount: {instance.total_amount}"
            )
        else:
            # Log status changes
            if hasattr(instance, '_previous_status'):
                if instance._previous_status != instance.status:
                    logger.info(
                        f"AUDIT: Uniform sale status changed - {instance.sale_number} - "
                        f"From: {instance._previous_status} To: {instance.status}"
                    )
    
    except Exception as e:
        logger.error(f"Error in audit logging: {e}", exc_info=True)


@receiver(pre_save, sender=UniformSale)
def store_previous_uniform_sale_status(sender, instance, **kwargs):
    """
    Store previous status for comparison in post_save.
    """
    if instance.pk:
        try:
            previous = UniformSale.objects.get(pk=instance.pk)
            instance._previous_status = previous.status
        except UniformSale.DoesNotExist:
            instance._previous_status = None


# =============================================================================
# DATA INTEGRITY SIGNALS
# =============================================================================

@receiver(pre_delete, sender=UniformSaleItem)
def prevent_delete_issued_sale_item(sender, instance, **kwargs):
    """
    Prevent deletion of sale items for issued sales.
    """
    if instance.sale.status == 'ISSUED':
        from django.core.exceptions import ValidationError
        raise ValidationError(
            "Cannot delete items from an issued sale. "
            "Process a return instead."
        )


@receiver(pre_delete, sender=UniformSale)
def prevent_delete_issued_sale(sender, instance, **kwargs):
    """
    Prevent deletion of issued sales.
    """
    if instance.status == 'ISSUED':
        from django.core.exceptions import ValidationError
        raise ValidationError(
            "Cannot delete an issued sale. "
            "Process a return instead."
        )


# =============================================================================
# SIGNAL TOGGLING (for bulk operations)
# =============================================================================

def disable_uniform_signals():
    """
    Disable uniform signals temporarily.
    Useful for bulk operations to improve performance.
    
    Usage:
        from uniforms.signals import disable_uniform_signals, enable_uniform_signals
        
        disable_uniform_signals()
        # Perform bulk operations
        enable_uniform_signals()
    """
    from django.db.models import signals
    
    signals.post_save.disconnect(uniform_sale_post_save, sender=UniformSale)
    signals.post_save.disconnect(uniform_sale_item_post_save, sender=UniformSaleItem)
    signals.post_save.disconnect(uniform_stock_post_save, sender=UniformStock)
    signals.post_save.disconnect(student_measurement_post_save, sender=StudentMeasurement)
    
    logger.info("Uniform signals disabled")


def enable_uniform_signals():
    """
    Re-enable uniform signals after bulk operations.
    """
    # Signals are automatically reconnected by the decorators
    # Just need to re-import the module
    import importlib
    import sys
    
    if 'uniforms.signals' in sys.modules:
        importlib.reload(sys.modules['uniforms.signals'])
    
    logger.info("Uniform signals re-enabled")


# =============================================================================
# HELPER FUNCTIONS FOR SIGNAL HANDLERS
# =============================================================================

def should_process_signal(kwargs):
    """
    Check if signal should be processed.
    Returns False if in raw mode (fixtures, migrations).
    """
    return not kwargs.get('raw', False)


def get_user_from_request():
    """
    Get current user from request if available.
    Useful for audit logging.
    """
    try:
        from django.contrib.auth.middleware import get_user
        from threading import local
        _thread_locals = local()
        if hasattr(_thread_locals, 'request'):
            return get_user(_thread_locals.request)
    except:
        pass
    
    return None