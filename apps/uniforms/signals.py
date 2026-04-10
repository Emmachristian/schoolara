# uniforms/signals.py

"""
Uniform Management Signals

Automatic triggers for:
- Sale number generation
- Cash receipt number generation
- Fiscal period auto-assignment
- Stock synchronisation (UniformItem.current_stock cache)
- Stock decrement on sale issue / restore on return or cancellation
- Payment sync from fees module → UniformSale
- Size recommendation refresh after verified measurement save
- Audit trail logging
- Data integrity enforcement

DESIGN PRINCIPLES
-----------------
1. Stock only moves at issue / return time, NOT when sale items are created.
   - decrement_stock_on_sale_item and restore_stock_on_sale_item_delete have
     been REMOVED. They caused a double-decrement with the issue view, and
     they violated the rule that items only leave the warehouse when handed
     to a student.
   - restore_stock_on_sale_cancellation_or_return has also been REMOVED.
     Stock restoration on cancellation is wrong (nothing was decremented
     pre-issue). Stock restoration on return is handled entirely by
     return_uniform_sale() in utils.py, which goes through UniformStock
     so this signal would double-restore.
   - Stock decrement on issue lives in views.uniform_sale_issue.
   - Stock restoration on return lives in utils.return_uniform_sale().
   - Stock restoration on cancellation: nothing to restore (not issued yet).

2. current_stock is a denormalised cache on UniformItem, maintained
   exclusively by uniform_stock_post_save and uniform_stock_post_delete via
   _sync_item_stock_from_records(). No other code should write current_stock
   directly on UniformItem.

3. MeasurementSession has been removed. The measurement_session_post_save
   and _update_measurement_session_stats helpers are gone with it.

4. Invoice and journal entry creation are NOT done here. They are created
   explicitly by UniformSaleWorkflowService.finalize_sale() so the caller
   always knows exactly what happened. Signals only handle reactive
   side-effects (e.g. a Payment saved in the fees module).

CHANGES FROM PREVIOUS VERSION:
- Removed decrement_stock_on_sale_item (post_save UniformSaleItem)
- Removed restore_stock_on_sale_item_delete (post_delete UniformSaleItem)
- Removed restore_stock_on_sale_cancellation_or_return (post_save UniformSale)
- Removed measurement_session_post_save (MeasurementSession removed)
- Removed _update_measurement_session_stats helper
- Removed _previous_status tracking from uniform_sale_pre_save (no longer
  needed once the stock-restore-on-status-change signal is removed)
- Fixed disable_uniform_signals / enable_uniform_signals to be symmetric
  and only reference signals that still exist
- Fixed uniform_stock_post_save to guard against size=None when logging
  (unsized items have no size.name)
- Fixed _sync_item_stock_from_records extracted as shared helper used by
  both post_save and post_delete signals
- Fixed _update_stock_from_purchase to route unsized items through
  UniformStock (get_or_create size=None) rather than writing current_stock
  directly on UniformItem
- Fixed _create_purchase_order_journal_entry to use filter().first() rather
  than get_or_create for the General Journal lookup, and to include
  entry_number on JournalEntry creation
- Fixed sync_uniform_sale_after_payment consolidated from two handlers into
  one that branches internally to prevent double-sync on payment reversal
- Fixed student_measurement_post_save deferred to transaction.on_commit()
  to avoid running the bulk update_or_create loop synchronously in the
  request cycle
"""

from django.db.models.signals import post_save, pre_save, post_delete, pre_delete
from django.dispatch import receiver
from django.db import transaction
from django.db.models import Sum
from decimal import Decimal
import logging

from .models import (
    UniformSale,
    UniformSaleItem,
    UniformPurchaseOrder,
    UniformPurchaseOrderItem,
    UniformStock,
    StudentMeasurement,
)
from .services import (
    UniformInvoiceService,
    UniformAccountingService,
    UniformStockService,
)
from .utils import (
    generate_uniform_sale_number,
    generate_purchase_order_number,
    generate_cash_receipt_number,
    recommend_size_from_measurements,
)

logger = logging.getLogger(__name__)


# =============================================================================
# UNIFORM SALE SIGNALS
# =============================================================================

@receiver(pre_save, sender=UniformSale)
def uniform_sale_pre_save(sender, instance, **kwargs):
    """
    Pre-save processing for UniformSale.

    - Generate sale_number if not yet set.
    - Auto-assign current fiscal period if not yet set.
    - Auto-generate a cash receipt number for CASH payments that have no
      reference number yet.
    """

    # ── Sale number ──────────────────────────────────────────────────────────
    if not instance.sale_number:
        instance.sale_number = generate_uniform_sale_number()
        logger.info(f"Generated sale number: {instance.sale_number}")

    # ── Fiscal period ─────────────────────────────────────────────────────────
    if not instance.fiscal_period_id:
        from core.models import FiscalPeriod
        instance.fiscal_period = FiscalPeriod.get_current_fiscal_period()
        if not instance.fiscal_period:
            logger.warning(
                f"No active fiscal period found for uniform sale "
                f"{instance.sale_number}"
            )

    # ── Cash receipt number ───────────────────────────────────────────────────
    # Only generate for cash payments where no reference has been set yet.
    # External methods (MTN, cheque, etc.) supply their own references.
    if (
        instance.payment_method_id
        and not instance.payment_reference
        and instance.paid_amount
        and instance.paid_amount > 0
    ):
        try:
            from core.models import PaymentMethod
            pm_code = (
                PaymentMethod.objects
                .filter(pk=instance.payment_method_id)
                .values_list('code', flat=True)
                .first()
            )
            if pm_code and pm_code.upper() == 'CASH':
                instance.payment_reference = generate_cash_receipt_number()
                logger.info(
                    f"Generated cash receipt {instance.payment_reference} "
                    f"for sale {instance.sale_number}"
                )
        except Exception as e:
            logger.error(
                f"Error generating cash receipt number for "
                f"{instance.sale_number}: {e}",
                exc_info=True,
            )


@receiver(post_save, sender=UniformSale)
def log_uniform_sale_changes(sender, instance, created, **kwargs):
    """Audit log for sale creation and status changes."""
    if kwargs.get('raw', False):
        return

    try:
        if created:
            logger.info(
                f"AUDIT: Sale created — {instance.sale_number} — "
                f"Student: {instance.student.get_full_name()} — "
                f"Amount: {instance.total_amount}"
            )
        else:
            logger.info(
                f"AUDIT: Sale updated — {instance.sale_number} — "
                f"Status: {instance.status}"
            )
    except Exception as e:
        logger.error(f"Error in sale audit logging: {e}", exc_info=True)


@receiver(pre_delete, sender=UniformSale)
def prevent_delete_issued_sale(sender, instance, **kwargs):
    """
    Block deletion of issued sales — process a return instead.

    Raises ProtectedError (not ValidationError). Django's pre_delete signal
    does NOT abort deletion on ValidationError — the DELETE still executes.
    ProtectedError is what Django uses internally for protected FK
    relationships and is the correct mechanism to abort a deletion from a
    signal.
    """
    if instance.status == 'ISSUED':
        from django.db.models import ProtectedError
        raise ProtectedError(
            "Cannot delete an issued sale — process a return instead.",
            {instance},
        )


@receiver(pre_delete, sender=UniformSale)
def uniform_sale_pre_delete(sender, instance, **kwargs):
    """
    Pre-delete cleanup for uniform sales.

    - Release reserved stock for DRAFT / PENDING / PARTIAL sales.
    - Reverse outstanding journal entries.

    Note: prevent_delete_issued_sale is defined first in this file so it
    fires before this handler. If the sale is ISSUED this handler is never
    reached.
    """
    try:
        if instance.status in ('DRAFT', 'PENDING', 'PARTIAL'):
            logger.info(
                f"Releasing reserved stock for deleted sale {instance.sale_number}"
            )
            UniformStockService.release_reserved_stock(instance)

        if instance.journal_entry and instance.journal_entry.status != 'REVERSED':
            logger.info(
                f"Reversing journal entry for deleted sale {instance.sale_number}"
            )
            UniformAccountingService.reverse_journal_entry_for_sale(
                instance, reason="Sale deleted"
            )
    except Exception as e:
        logger.error(
            f"Error in uniform_sale_pre_delete for {instance.sale_number}: {e}",
            exc_info=True,
        )


# =============================================================================
# PAYMENT SYNC — fees.Payment → UniformSale
# =============================================================================

@receiver(post_save, sender='fees.Payment')
def sync_uniform_sale_after_payment(sender, instance, created, **kwargs):
    """
    After a Payment is saved in the fees module, sync the linked UniformSale
    so paid_amount / balance / status stay accurate.

    Handles all payment states in a single handler (active, reversed,
    refunded) to prevent double-sync when a reversed payment would otherwise
    satisfy two separate handlers simultaneously.

    Ignored when:
    - Loading fixtures (raw=True)
    - The payment is not linked to any uniform sale invoice
    """
    if kwargs.get('raw', False):
        return

    if not (instance.is_active or instance.reversed or instance.refunded):
        return

    try:
        invoice = instance.invoice

        try:
            uniform_sale = invoice.uniform_sale
        except UniformSale.DoesNotExist:
            uniform_sale = None

        if uniform_sale is None:
            try:
                uniform_sale = UniformSale.objects.get(fee_invoice=invoice)
            except UniformSale.DoesNotExist:
                return

        UniformInvoiceService.sync_sale_from_invoice(uniform_sale)

    except Exception as e:
        logger.error(
            f"Error syncing uniform sale after payment "
            f"{getattr(instance, 'payment_number', instance.pk)}: {e}",
            exc_info=True,
        )


# =============================================================================
# UNIFORM SALE ITEM SIGNALS
# =============================================================================

@receiver(post_save, sender=UniformSaleItem)
def uniform_sale_item_post_save(sender, instance, created, **kwargs):
    """
    Recalculate parent sale totals whenever a line item is saved.

    Note: this signal does NOT move stock. Stock is decremented only when
    the sale is issued (uniform_sale_issue view) and restored only when
    items are returned (return_uniform_sale in utils.py).
    """
    if kwargs.get('raw', False):
        return

    try:
        instance.sale.calculate_totals()
        logger.debug(
            f"Recalculated totals for sale {instance.sale.sale_number}"
        )
    except Exception as e:
        logger.error(
            f"Error in uniform_sale_item_post_save: {e}", exc_info=True
        )


@receiver(post_delete, sender=UniformSaleItem)
def uniform_sale_item_post_delete(sender, instance, **kwargs):
    """
    Recalculate parent sale totals whenever a line item is deleted.

    Note: this signal does NOT restore stock. Stock only moves at issue /
    return time, not when sale items are added or removed.
    """
    try:
        instance.sale.calculate_totals()
        logger.debug(
            f"Recalculated totals after item deletion for sale "
            f"{instance.sale.sale_number}"
        )
    except Exception as e:
        logger.error(
            f"Error in uniform_sale_item_post_delete: {e}", exc_info=True
        )


@receiver(pre_delete, sender=UniformSaleItem)
def prevent_delete_issued_sale_item(sender, instance, **kwargs):
    """
    Block deletion of line items belonging to an issued sale.

    Raises ProtectedError — ValidationError does not abort deletion from a
    pre_delete signal.
    """
    if instance.sale.status == 'ISSUED':
        from django.db.models import ProtectedError
        raise ProtectedError(
            "Cannot delete items from an issued sale — process a return instead.",
            {instance},
        )


@receiver(post_save, sender=UniformSaleItem)
def update_uniform_item_accounts(sender, instance, created, **kwargs):
    """
    Ensure the uniform item on a new sale line has GL accounts assigned.
    Only runs on creation — edits to existing lines don't need this check.
    """
    if kwargs.get('raw', False):
        return
    if not created:
        return

    try:
        uniform_item = instance.uniform_item
        if not all([
            getattr(uniform_item, 'inventory_account', None),
            getattr(uniform_item, 'cogs_account', None),
            getattr(uniform_item, 'revenue_account', None),
        ]):
            if hasattr(uniform_item, 'ensure_accounts_assigned'):
                uniform_item.ensure_accounts_assigned()
                logger.debug(
                    f"Assigned GL accounts to {uniform_item.name}"
                )
    except Exception as e:
        logger.error(
            f"Error assigning GL accounts to uniform item: {e}", exc_info=True
        )


# =============================================================================
# UNIFORM PURCHASE ORDER SIGNALS
# =============================================================================

@receiver(pre_save, sender=UniformPurchaseOrder)
def purchase_order_pre_save(sender, instance, **kwargs):
    """
    Pre-save processing for UniformPurchaseOrder.

    - Generate PO number if not yet set.
    - Auto-assign current fiscal period if not yet set.
    """
    if not instance.po_number:
        instance.po_number = generate_purchase_order_number()
        logger.info(f"Generated PO number: {instance.po_number}")

    if not instance.fiscal_period_id:
        from core.models import FiscalPeriod
        instance.fiscal_period = FiscalPeriod.get_current_fiscal_period()


@receiver(post_save, sender=UniformPurchaseOrder)
def purchase_order_post_save(sender, instance, created, **kwargs):
    """
    Create a goods-receipt journal entry when a PO transitions to RECEIVED.
    Only fires once — checks that no journal entry is linked yet.
    """
    if kwargs.get('raw', False):
        return

    if instance.status == 'RECEIVED' and not instance.journal_entry_id:
        try:
            _create_purchase_order_journal_entry(instance)
        except Exception as e:
            logger.error(
                f"Error creating journal entry for PO {instance.po_number}: {e}",
                exc_info=True,
            )


def _create_purchase_order_journal_entry(purchase_order):
    """
    Create the goods-receipt journal entry for a received purchase order.

    Entry:
        DR Inventory        (asset increases)
        CR Accounts Payable (liability increases)

    Uses filter().first() for the General Journal lookup — not get_or_create()
    — to avoid silently creating an incomplete Journal record if none exists.
    Logs a warning and returns early instead.
    """
    from finance.models import JournalEntry, JournalTransaction, Journal
    from core.models import FinancialSettings

    settings = FinancialSettings.get_instance()
    if not settings:
        logger.warning(
            f"FinancialSettings not configured — skipping journal entry "
            f"for PO {purchase_order.po_number}"
        )
        return

    inventory_account = getattr(settings, 'default_inventory_account', None)
    payable_account   = getattr(settings, 'default_payables_account', None)

    if not inventory_account or not payable_account:
        logger.warning(
            f"Inventory or payables account not configured — skipping "
            f"journal entry for PO {purchase_order.po_number}"
        )
        return

    journal = Journal.objects.filter(journal_type='GENERAL').first()
    if not journal:
        logger.warning(
            f"No General Journal found — skipping journal entry for "
            f"PO {purchase_order.po_number}. Create a General Journal first."
        )
        return

    entry = JournalEntry.objects.create(
        journal=journal,
        entry_number=f"JE-PO-{purchase_order.po_number}",
        entry_date=(
            purchase_order.actual_delivery_date or purchase_order.order_date
        ),
        fiscal_period=purchase_order.fiscal_period,
        reference_number=purchase_order.po_number,
        description=(
            f"Goods receipt — PO {purchase_order.po_number} "
            f"from {purchase_order.supplier_name}"
        ),
        status='POSTED',
    )

    JournalTransaction.objects.create(
        journal_entry=entry,
        account=inventory_account,
        description=f"Uniform inventory receipt — PO {purchase_order.po_number}",
        amount=purchase_order.total_amount,
        is_debit=True,
    )
    JournalTransaction.objects.create(
        journal_entry=entry,
        account=payable_account,
        description=(
            f"Payable to {purchase_order.supplier_name} — "
            f"PO {purchase_order.po_number}"
        ),
        amount=purchase_order.total_amount,
        is_debit=False,
    )

    # Use queryset update to avoid re-triggering post_save.
    UniformPurchaseOrder.objects.filter(pk=purchase_order.pk).update(
        journal_entry=entry
    )

    logger.info(
        f"Created journal entry {entry.entry_number} "
        f"for PO {purchase_order.po_number}"
    )


# =============================================================================
# UNIFORM PURCHASE ORDER ITEM SIGNALS
# =============================================================================

@receiver(pre_save, sender=UniformPurchaseOrderItem)
def purchase_order_item_pre_save(sender, instance, **kwargs):
    """
    Store the previous quantity_received so post_save can compute the delta
    and only increment stock for genuinely new units received.
    """
    if instance.pk:
        try:
            instance._previous_quantity_received = (
                UniformPurchaseOrderItem.objects
                .get(pk=instance.pk)
                .quantity_received
            )
        except UniformPurchaseOrderItem.DoesNotExist:
            instance._previous_quantity_received = 0
    else:
        instance._previous_quantity_received = 0


@receiver(post_save, sender=UniformPurchaseOrderItem)
def purchase_order_item_post_save(sender, instance, created, **kwargs):
    """
    Update stock when quantity_received increases on an existing PO line.

    This is the single source of truth for stock updates on goods receipt.
    views.purchase_order_receive only records the received quantities and
    sets the PO status — it does NOT touch stock directly.
    """
    if kwargs.get('raw', False):
        return
    if created:
        return

    if instance.quantity_received > 0:
        try:
            delta = (
                instance.quantity_received
                - getattr(instance, '_previous_quantity_received', 0)
            )
            if delta > 0:
                _update_stock_from_purchase(instance, delta)
        except Exception as e:
            logger.error(
                f"Error updating stock from PO item: {e}", exc_info=True
            )


def _update_stock_from_purchase(po_item, quantity):
    """
    Increment UniformStock when goods arrive from a purchase order.

    Both sized and unsized items go through UniformStock.save() so the
    uniform_stock_post_save signal keeps UniformItem.current_stock accurate.
    Never writes current_stock directly on UniformItem.
    """
    uniform_item = po_item.uniform_item
    size         = po_item.size

    if uniform_item.requires_sizing and size:
        stock, _ = UniformStock.objects.get_or_create(
            uniform_item=uniform_item,
            size=size,
        )
    else:
        # Unsized item — get or create the single sizeless stock record.
        stock, _ = UniformStock.objects.get_or_create(
            uniform_item=uniform_item,
            size=None,
        )

    stock.quantity += quantity
    stock.save()
    # uniform_stock_post_save signal syncs uniform_item.current_stock.

    size_label = f" size {size.name}" if size else " (unsized)"
    logger.info(
        f"Stock received: {uniform_item.name}{size_label} "
        f"+{quantity} (now {stock.quantity})"
    )


# =============================================================================
# UNIFORM STOCK SIGNALS
# =============================================================================

def _sync_item_stock_from_records(uniform_item):
    """
    Recompute UniformItem.current_stock as the Sum() of all its stock records
    and write it back with a targeted UPDATE if it has changed.

    Shared by uniform_stock_post_save and uniform_stock_post_delete so the
    sync logic lives in exactly one place.
    """
    total = (
        UniformStock.objects
        .filter(uniform_item_id=uniform_item.pk)
        .aggregate(total=Sum('quantity'))['total'] or 0
    )
    if uniform_item.current_stock != total:
        from .models import UniformItem
        UniformItem.objects.filter(pk=uniform_item.pk).update(current_stock=total)
        logger.debug(
            f"Synced current_stock for {uniform_item.name}: {total}"
        )


@receiver(post_save, sender=UniformStock)
def uniform_stock_post_save(sender, instance, created, **kwargs):
    """
    Keep UniformItem.current_stock in sync after every stock record save.

    Also emits low-stock / out-of-stock warnings to the log so ops teams
    can monitor inventory levels without running a separate query.
    """
    if kwargs.get('raw', False):
        return

    try:
        _sync_item_stock_from_records(instance.uniform_item)

        # Guard: instance.size is None for unsized items.
        size_label = f" size {instance.size.name}" if instance.size else ""

        if instance.available_quantity == 0:
            logger.error(
                f"OUT OF STOCK: {instance.uniform_item.name}{size_label}"
            )
        elif instance.available_quantity <= instance.uniform_item.reorder_level:
            logger.warning(
                f"LOW STOCK: {instance.uniform_item.name}{size_label} — "
                f"available: {instance.available_quantity}, "
                f"reorder level: {instance.uniform_item.reorder_level}"
            )
    except Exception as e:
        logger.error(f"Error in uniform_stock_post_save: {e}", exc_info=True)


@receiver(post_delete, sender=UniformStock)
def uniform_stock_post_delete(sender, instance, **kwargs):
    """
    Keep UniformItem.current_stock in sync after a stock record is deleted.

    Without this handler, deleting a stock record leaves current_stock stale
    on the parent item — post_save never fires on deletion.
    """
    try:
        _sync_item_stock_from_records(instance.uniform_item)
    except Exception as e:
        logger.error(f"Error in uniform_stock_post_delete: {e}", exc_info=True)


# =============================================================================
# STUDENT MEASUREMENT SIGNALS
# =============================================================================

@receiver(post_save, sender=StudentMeasurement)
def student_measurement_post_save(sender, instance, created, **kwargs):
    """
    When a verified current measurement is saved, refresh size recommendations
    for the student so StudentUniformSize records stay up to date.

    Deferred to transaction.on_commit() so the potentially expensive
    bulk update_or_create loop does not run synchronously in the request
    cycle that saved the measurement. If the transaction rolls back the
    recommendations are not regenerated — which is correct.
    """
    if kwargs.get('raw', False):
        return

    if not (instance.is_current and instance.is_verified):
        return

    student          = instance.student
    academic_session = instance.academic_session

    transaction.on_commit(
        lambda: _update_size_recommendations_for_student(student, academic_session)
    )


def _update_size_recommendations_for_student(student, academic_session):
    """
    Regenerate StudentUniformSize recommendations for every active sized item
    after a student's measurements change.

    Called via transaction.on_commit() — never inside an open transaction.
    """
    from .models import UniformItem, StudentUniformSize

    uniform_items = UniformItem.objects.filter(
        is_active=True,
        requires_sizing=True,
    )

    for uniform_item in uniform_items:
        try:
            result = recommend_size_from_measurements(student, uniform_item)

            if not result['recommended_size']:
                continue

            StudentUniformSize.objects.update_or_create(
                student=student,
                uniform_item=uniform_item,
                academic_session=academic_session,
                is_current=True,
                defaults={
                    'recommended_size': result['recommended_size'],
                    'sizing_method':    'MEASURED',
                    'confidence_level': result['confidence'],
                    'notes':            result['reason'],
                    'alternative_sizes': (
                        [str(s.id) for s in result['alternative_sizes']]
                        if result['alternative_sizes'] else None
                    ),
                },
            )
            logger.info(
                f"Size recommendation updated — "
                f"{student.get_full_name()} / {uniform_item.name}: "
                f"Size {result['recommended_size'].name} "
                f"({result['confidence']})"
            )
        except Exception as e:
            logger.error(
                f"Error updating size recommendation for "
                f"{uniform_item.name}: {e}",
                exc_info=True,
            )


# =============================================================================
# SIGNAL TOGGLING (for bulk operations / data migrations)
# =============================================================================

def disable_uniform_signals():
    """
    Temporarily disconnect the most expensive uniform signals.

    Use around bulk import / migration operations to prevent spurious
    side-effects. After the bulk operation, call enable_uniform_signals()
    and then manually reconcile UniformItem.current_stock values with
    _sync_item_stock_from_records() or a management command.

    Note: stock-movement signals (decrement on item create, restore on
    cancel/return) no longer exist — stock only moves via the issue view
    and return_uniform_sale() in utils.py, which are not called during
    bulk imports.
    """
    post_save.disconnect(log_uniform_sale_changes,        sender=UniformSale)
    post_save.disconnect(uniform_sale_item_post_save,     sender=UniformSaleItem)
    post_delete.disconnect(uniform_sale_item_post_delete, sender=UniformSaleItem)
    post_save.disconnect(uniform_stock_post_save,         sender=UniformStock)
    post_delete.disconnect(uniform_stock_post_delete,     sender=UniformStock)
    post_save.disconnect(student_measurement_post_save,   sender=StudentMeasurement)
    post_save.disconnect(sync_uniform_sale_after_payment, sender='fees.Payment')

    logger.info("Uniform signals disabled")


def enable_uniform_signals():
    """
    Reconnect uniform signals after bulk operations.

    Uses explicit connect() calls mirroring disable_uniform_signals()
    exactly. Explicit connect() is predictable and idempotent when
    dispatch_uid is not used — Django deduplicates by (receiver_func, sender).
    """
    post_save.connect(log_uniform_sale_changes,        sender=UniformSale)
    post_save.connect(uniform_sale_item_post_save,     sender=UniformSaleItem)
    post_delete.connect(uniform_sale_item_post_delete, sender=UniformSaleItem)
    post_save.connect(uniform_stock_post_save,         sender=UniformStock)
    post_delete.connect(uniform_stock_post_delete,     sender=UniformStock)
    post_save.connect(student_measurement_post_save,   sender=StudentMeasurement)
    post_save.connect(sync_uniform_sale_after_payment, sender='fees.Payment')

    logger.info("Uniform signals re-enabled")