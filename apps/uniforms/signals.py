# uniforms/signals.py

"""
Uniform Management Signals

Automatic triggers for:
- Sale number generation
- Cash receipt number generation
- Fiscal period auto-assignment
- Stock updates and reservations
- Stock decrement on sale, restore on cancellation/return
- Syncing UniformSale payment state after fees-module payments
- Student account updates
- Audit trail logging
- Data integrity enforcement

NOTE ON INVOICE / JOURNAL ENTRY CREATION:
  These are NOT created here. They are created explicitly by
  UniformSaleWorkflowService.finalize_sale() so the caller always
  knows exactly what happened. Signals only handle side-effects that
  are genuinely reactive (e.g. a Payment being saved in the fees module).

CHANGES FROM PREVIOUS VERSION:
- Fixed: prevent_delete_issued_sale and prevent_delete_issued_sale_item now
  raise ProtectedError instead of ValidationError. Django's pre_delete signal
  does NOT stop deletion on ValidationError — the delete proceeds regardless.
  ProtectedError is what Django itself uses for protected FK relationships and
  is the correct mechanism to abort a deletion from a signal.
- Fixed: uniform_stock_post_save now syncs current_stock for ALL items (sized
  and unsized) via a single Sum() aggregate. Previously the requires_sizing
  guard meant unsized items' current_stock was never updated from their stock
  record, causing the two values to drift.
- Fixed: uniform_stock_post_save log lines now guard against size=None so
  accessing instance.size.name does not raise AttributeError on unsized items.
- Fixed: Added uniform_stock_post_delete signal. Without it, deleting a stock
  record leaves current_stock stale on the parent item because post_save never
  fires on deletion. The delete handler runs the same Sum() aggregate and
  writes current_stock if it has changed.
- Fixed: _sync_item_stock_from_records extracted as a shared helper used by
  both post_save and post_delete so the sync logic lives in one place.
- Fixed: _update_stock_from_purchase now routes unsized items through
  UniformStock (get_or_create with size=None) instead of writing
  current_stock directly on the item. Writing current_stock directly bypassed
  the signal, and any subsequent stock record save would silently overwrite
  current_stock back to the stale value.
- Fixed: enable_uniform_signals() now uses explicit connect() calls mirroring
  disable_uniform_signals() instead of module reload, which was unreliable
  for string-based senders like 'fees.Payment'.
- Fixed: _create_purchase_order_journal_entry replaced Journal.get_or_create()
  with filter().first() + early return on missing journal, avoiding silent
  creation of an incomplete Journal record.
- Fixed: sync_uniform_sale_after_payment and sync_uniform_sale_after_reversal
  consolidated into a single sync_uniform_sale_after_payment handler that
  branches internally, preventing double-sync when a reversed payment satisfies
  both handlers' conditions simultaneously.
- Fixed: _update_size_recommendations_for_student deferred to
  transaction.on_commit() to avoid running 50+ update_or_create calls
  synchronously on the request cycle that saved the measurement.
- Added: decrement_stock_on_sale_item — decrements UniformStock when a
  UniformSaleItem is created. Floors at 0, never goes negative.
- Added: restore_stock_on_sale_item_delete — restores stock when a sale item
  is deleted before the sale is issued.
- Added: restore_stock_on_sale_cancellation_or_return — restores stock for
  all line items when a sale transitions to CANCELLED or RETURNED. Uses
  _previous_status (stored in uniform_sale_pre_save) to fire exactly once
  on the transition, not on every subsequent save of an already-cancelled sale.
- Updated: disable_uniform_signals() and enable_uniform_signals() updated to
  include the three new stock handlers.

NOTE ON MIGRATED SALES:
  The 139 migrated uniform sales were inserted directly via SQL without
  triggering signals. Stock quantities were set manually to reflect current
  physical stock after those sales. The new stock signals only fire for
  new sales going forward — do NOT backfill decrements for migrated records.
"""

from django.db.models.signals import (
    post_save, pre_save, post_delete, pre_delete
)
from django.dispatch import receiver
from django.db import transaction
from django.db.models import Sum
from decimal import Decimal
import logging

from .models import (
    UniformSale, UniformSaleItem, UniformPurchaseOrder,
    UniformPurchaseOrderItem, UniformStock, StudentMeasurement,
    MeasurementSession
)
from .services import (
    UniformInvoiceService, UniformAccountingService,
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
    Pre-save processing for uniform sale.

    - Generate sale number if not set
    - Auto-assign current fiscal period if not set
    - Auto-generate cash receipt number for cash payments without a reference
    - Store previous status for audit logging in post_save and for the
      stock restore signal (restore_stock_on_sale_cancellation_or_return)
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
                f"No active fiscal period found for uniform sale {instance.sale_number}"
            )

    # ── Cash receipt number ───────────────────────────────────────────────────
    # For cash payments the school is the source of truth for the reference.
    # External payment methods (MTN, cheque, etc.) provide their own references.
    if (
        instance.payment_method_id and
        not instance.payment_reference and
        instance.paid_amount and instance.paid_amount > 0
    ):
        try:
            pm_code = (
                instance.payment_method.code
                if hasattr(instance, '_payment_method_cache')
                else None
            )
            if pm_code is None:
                from core.models import PaymentMethod
                pm_code = PaymentMethod.objects.filter(
                    pk=instance.payment_method_id
                ).values_list('code', flat=True).first()

            if pm_code and pm_code.upper() == 'CASH':
                instance.payment_reference = generate_cash_receipt_number()
                logger.info(
                    f"Generated cash receipt number {instance.payment_reference} "
                    f"for sale {instance.sale_number}"
                )
        except Exception as e:
            logger.error(f"Error generating cash receipt number: {e}", exc_info=True)

    # ── Store previous status for post_save handlers ──────────────────────────
    if instance.pk:
        try:
            instance._previous_status = UniformSale.objects.get(pk=instance.pk).status
        except UniformSale.DoesNotExist:
            instance._previous_status = None
    else:
        instance._previous_status = None


@receiver(post_save, sender=UniformSale)
def log_uniform_sale_changes(sender, instance, created, **kwargs):
    """
    Audit logging for uniform sale creates and status transitions.
    """
    if kwargs.get('raw', False):
        return

    try:
        if created:
            logger.info(
                f"AUDIT: Uniform sale created — {instance.sale_number} — "
                f"Student: {instance.student.get_full_name()} — "
                f"Amount: {instance.total_amount}"
            )
        else:
            prev = getattr(instance, '_previous_status', None)
            if prev and prev != instance.status:
                logger.info(
                    f"AUDIT: Sale status change — {instance.sale_number} — "
                    f"{prev} -> {instance.status}"
                )
    except Exception as e:
        logger.error(f"Error in uniform sale audit logging: {e}", exc_info=True)


@receiver(pre_delete, sender=UniformSale)
def prevent_delete_issued_sale(sender, instance, **kwargs):
    """
    Block deletion of issued sales — process a return instead.

    Raises ProtectedError instead of ValidationError. Django's pre_delete
    signal does NOT abort the deletion when ValidationError is raised — the
    DELETE statement still executes. ProtectedError is what Django uses
    internally for protected FK relationships and is the correct way to abort
    a deletion from a signal.
    """
    if instance.status == 'ISSUED':
        from django.db.models import ProtectedError
        raise ProtectedError(
            "Cannot delete an issued sale. Process a return instead.",
            {instance},
        )


@receiver(pre_delete, sender=UniformSale)
def uniform_sale_pre_delete(sender, instance, **kwargs):
    """
    Pre-delete cleanup for uniform sale.

    - Release any reserved stock
    - Reverse outstanding journal entries

    Note: prevent_delete_issued_sale is registered first (defined first in
    this file) so it fires before this handler. If the sale is ISSUED this
    handler is never reached.
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
            exc_info=True
        )


# =============================================================================
# PAYMENT SYNC — fees.Payment -> UniformSale
# =============================================================================

@receiver(post_save, sender='fees.Payment')
def sync_uniform_sale_after_payment(sender, instance, created, **kwargs):
    """
    After a Payment is saved in the fees module, sync the linked UniformSale
    so paid_amount / balance / status stay accurate.

    Consolidated from two previous handlers into one that branches internally
    so every relevant state change triggers exactly one sync. A reversed
    payment satisfies instance.is_active == False AND instance.reversed == True,
    meaning it passed neither of the old handlers' guards and was silently
    ignored on reversal.

    Ignored cases:
    - Raw fixtures (raw=True)
    - Payments not linked to any uniform sale invoice
    """
    if kwargs.get('raw', False):
        return

    # A payment is relevant if it is active, reversed, or refunded.
    is_relevant = instance.is_active or instance.reversed or instance.refunded
    if not is_relevant:
        return

    try:
        invoice = instance.invoice

        uniform_sale = getattr(invoice, 'uniform_sale', None)
        if uniform_sale is None:
            try:
                uniform_sale = UniformSale.objects.get(fee_invoice=invoice)
            except UniformSale.DoesNotExist:
                return

        UniformInvoiceService.sync_sale_from_invoice(uniform_sale)

    except Exception as e:
        logger.error(
            f"Error syncing uniform sale after payment {instance.payment_number}: {e}",
            exc_info=True
        )


# =============================================================================
# UNIFORM SALE ITEM SIGNALS
# =============================================================================

@receiver(post_save, sender=UniformSaleItem)
def uniform_sale_item_post_save(sender, instance, created, **kwargs):
    """
    Recalculate parent sale totals whenever a line item is saved.
    """
    if kwargs.get('raw', False):
        return

    try:
        instance.sale.calculate_totals()
        logger.debug(f"Recalculated totals for sale {instance.sale.sale_number}")
    except Exception as e:
        logger.error(f"Error in uniform_sale_item_post_save: {e}", exc_info=True)


@receiver(post_delete, sender=UniformSaleItem)
def uniform_sale_item_post_delete(sender, instance, **kwargs):
    """
    Recalculate parent sale totals whenever a line item is deleted.
    """
    try:
        instance.sale.calculate_totals()
        logger.debug(
            f"Recalculated totals after item deletion for sale "
            f"{instance.sale.sale_number}"
        )
    except Exception as e:
        logger.error(f"Error in uniform_sale_item_post_delete: {e}", exc_info=True)


@receiver(pre_delete, sender=UniformSaleItem)
def prevent_delete_issued_sale_item(sender, instance, **kwargs):
    """
    Block deletion of line items belonging to an issued sale.

    Raises ProtectedError instead of ValidationError — ValidationError does
    not abort deletion from a pre_delete signal.
    """
    if instance.sale.status == 'ISSUED':
        from django.db.models import ProtectedError
        raise ProtectedError(
            "Cannot delete items from an issued sale. Process a return instead.",
            {instance},
        )


@receiver(post_save, sender=UniformSaleItem)
def update_uniform_item_accounts(sender, instance, created, **kwargs):
    """
    Ensure the uniform item on this line has GL accounts assigned.
    """
    if kwargs.get('raw', False):
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
                logger.debug(f"Assigned accounts to {uniform_item.name}")
    except Exception as e:
        logger.error(f"Error assigning accounts to uniform item: {e}", exc_info=True)


# =============================================================================
# STOCK DECREMENT / RESTORE ON SALE
# =============================================================================

@receiver(post_save, sender=UniformSaleItem)
def decrement_stock_on_sale_item(sender, instance, created, **kwargs):
    """
    Decrement UniformStock when a sale item is created.

    Only fires on creation — edits to an existing line item (price changes,
    quantity corrections) are intentionally not reflected here because they
    require an explicit stock adjustment workflow, not a silent signal.

    Floors at 0 — stock never goes negative. A warning is logged when a sale
    would push stock below zero so staff can investigate.

    NOTE: The 139 migrated sales were inserted directly via SQL without
    triggering signals. Do not backfill decrements for those records.
    """
    if kwargs.get('raw', False):
        return
    if not created:
        return

    try:
        stock = UniformStock.objects.filter(
            uniform_item=instance.uniform_item,
            size=instance.size,
        ).first()

        if stock:
            if stock.quantity < instance.quantity:
                logger.warning(
                    f"OVERSELL: {instance.uniform_item.name} "
                    f"{'size ' + instance.size.name if instance.size else '(unsized)'} — "
                    f"selling {instance.quantity} but only {stock.quantity} in stock"
                )
            stock.quantity = max(stock.quantity - instance.quantity, 0)
            stock.save()  # triggers uniform_stock_post_save → syncs current_stock
            logger.info(
                f"Stock decremented: {instance.uniform_item.name} "
                f"{'size ' + instance.size.name if instance.size else '(unsized)'} "
                f"-{instance.quantity} (now {stock.quantity})"
            )
        else:
            logger.warning(
                f"No stock record found for {instance.uniform_item.name} "
                f"{'size ' + instance.size.name if instance.size else '(unsized)'} "
                f"— stock not decremented. Create a stock record first."
            )
    except Exception as e:
        logger.error(
            f"Error decrementing stock on sale item save: {e}", exc_info=True
        )


@receiver(post_delete, sender=UniformSaleItem)
def restore_stock_on_sale_item_delete(sender, instance, **kwargs):
    """
    Restore stock when a sale item is deleted.

    Covers cases where a draft or pending sale has a line item removed
    before the sale is issued. Issued sales are blocked from item deletion
    by prevent_delete_issued_sale_item so this handler is safe to restore
    unconditionally.
    """
    try:
        stock = UniformStock.objects.filter(
            uniform_item=instance.uniform_item,
            size=instance.size,
        ).first()

        if stock:
            stock.quantity += instance.quantity
            stock.save()
            logger.info(
                f"Stock restored on item delete: {instance.uniform_item.name} "
                f"{'size ' + instance.size.name if instance.size else '(unsized)'} "
                f"+{instance.quantity} (now {stock.quantity})"
            )
        else:
            logger.warning(
                f"No stock record found for {instance.uniform_item.name} "
                f"{'size ' + instance.size.name if instance.size else '(unsized)'} "
                f"— stock not restored on item delete"
            )
    except Exception as e:
        logger.error(
            f"Error restoring stock on sale item delete: {e}", exc_info=True
        )


@receiver(post_save, sender=UniformSale)
def restore_stock_on_sale_cancellation_or_return(sender, instance, created, **kwargs):
    """
    Restore stock for all line items when a sale is cancelled or returned.

    Uses _previous_status (stored in uniform_sale_pre_save) to fire exactly
    once on the CANCELLED/RETURNED transition — not on every subsequent save
    of an already-cancelled or already-returned sale.

    This complements decrement_stock_on_sale_item: decrement fires per item
    on creation, restore fires per sale on status transition.
    """
    if kwargs.get('raw', False):
        return
    if created:
        return

    prev = getattr(instance, '_previous_status', None)
    is_now_cancelled = instance.status == 'CANCELLED' and prev != 'CANCELLED'
    is_now_returned = instance.status == 'RETURNED' and prev != 'RETURNED'

    if not (is_now_cancelled or is_now_returned):
        return

    transition = 'cancellation' if is_now_cancelled else 'return'

    try:
        for item in instance.items.select_related('uniform_item', 'size').all():
            stock = UniformStock.objects.filter(
                uniform_item=item.uniform_item,
                size=item.size,
            ).first()

            if stock:
                stock.quantity += item.quantity
                stock.save()
                logger.info(
                    f"Stock restored on sale {instance.sale_number} {transition}: "
                    f"{item.uniform_item.name} "
                    f"{'size ' + item.size.name if item.size else '(unsized)'} "
                    f"+{item.quantity} (now {stock.quantity})"
                )
            else:
                logger.warning(
                    f"No stock record found for {item.uniform_item.name} "
                    f"{'size ' + item.size.name if item.size else '(unsized)'} "
                    f"— stock not restored on {transition} of sale "
                    f"{instance.sale_number}"
                )
    except Exception as e:
        logger.error(
            f"Error restoring stock on sale {instance.sale_number} "
            f"{transition}: {e}",
            exc_info=True
        )


# =============================================================================
# UNIFORM PURCHASE ORDER SIGNALS
# =============================================================================

@receiver(pre_save, sender=UniformPurchaseOrder)
def purchase_order_pre_save(sender, instance, **kwargs):
    """
    Pre-save processing for purchase order.

    - Generate PO number if not set
    - Auto-assign current fiscal period if not set
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
    Create goods-receipt journal entry when a PO is marked as RECEIVED.
    Only fires once (checks that no journal entry is linked yet).
    """
    if kwargs.get('raw', False):
        return

    if instance.status == 'RECEIVED' and not instance.journal_entry_id:
        try:
            _create_purchase_order_journal_entry(instance)
        except Exception as e:
            logger.error(
                f"Error creating journal entry for PO {instance.po_number}: {e}",
                exc_info=True
            )


def _create_purchase_order_journal_entry(purchase_order):
    """
    Create journal entry when goods are received.

    Entry:
        DR Inventory        (asset increases)
        CR Accounts Payable (liability increases)

    Uses filter().first() instead of get_or_create() to avoid silently
    creating an incomplete Journal record if the General Journal doesn't
    exist yet. Logs a warning and bails early instead.
    """
    from finance.models import JournalEntry, JournalTransaction, Journal
    from core.models import FinancialSettings

    settings = FinancialSettings.get_instance()
    if not settings:
        logger.warning(
            f"FinancialSettings not configured — skipping journal entry for "
            f"PO {purchase_order.po_number}"
        )
        return

    inventory_account = getattr(settings, 'default_inventory_account', None)
    payable_account = getattr(settings, 'default_payables_account', None)

    if not inventory_account or not payable_account:
        logger.warning(
            f"Inventory or payables account not configured — skipping journal "
            f"entry for PO {purchase_order.po_number}"
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

    # Update via queryset to avoid re-triggering post_save
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
    Store the previous quantity_received so post_save can compute the delta.
    """
    if instance.pk:
        try:
            instance._previous_quantity_received = (
                UniformPurchaseOrderItem.objects.get(pk=instance.pk).quantity_received
            )
        except UniformPurchaseOrderItem.DoesNotExist:
            instance._previous_quantity_received = 0
    else:
        instance._previous_quantity_received = 0


@receiver(post_save, sender=UniformPurchaseOrderItem)
def purchase_order_item_post_save(sender, instance, created, **kwargs):
    """
    Update stock when quantity_received increases on an existing PO item.

    This is the single source of truth for stock updates on goods receipt.
    views.purchase_order_receive only records the received quantities and
    sets the PO status — it does NOT touch stock directly.
    """
    if kwargs.get('raw', False):
        return

    if not created and instance.quantity_received > 0:
        try:
            qty_change = (
                instance.quantity_received
                - getattr(instance, '_previous_quantity_received', 0)
            )
            if qty_change > 0:
                _update_stock_from_purchase(instance, qty_change)
        except Exception as e:
            logger.error(
                f"Error updating stock from PO item: {e}", exc_info=True
            )


def _update_stock_from_purchase(po_item, quantity):
    """
    Increment stock levels when goods arrive from a purchase order.

    Both sized and unsized items go through UniformStock so the
    uniform_stock_post_save signal keeps current_stock accurate for both.

    Previously the unsized path wrote current_stock directly on the item,
    which bypassed the signal entirely. Any subsequent UniformStock save
    for that item would then overwrite current_stock back to the stale
    stock-record value.
    """
    uniform_item = po_item.uniform_item
    size = po_item.size

    if uniform_item.requires_sizing and size:
        stock, _ = UniformStock.objects.get_or_create(
            uniform_item=uniform_item,
            size=size,
        )
        stock.quantity += quantity
        stock.save()
        logger.info(
            f"Stock updated: {uniform_item.name} size {size.name} "
            f"+{quantity} (now {stock.quantity})"
        )
    else:
        # Unsized item — get or create the single sizeless stock record.
        # uniform_stock_post_save syncs current_stock after save().
        stock, _ = UniformStock.objects.get_or_create(
            uniform_item=uniform_item,
            size=None,
        )
        stock.quantity += quantity
        stock.save()
        logger.info(
            f"Stock updated: {uniform_item.name} (unsized) "
            f"+{quantity} (now {stock.quantity})"
        )


# =============================================================================
# UNIFORM STOCK SIGNALS
# =============================================================================

def _sync_item_stock_from_records(uniform_item):
    """
    Recalculate current_stock from the Sum() of all stock records and write
    it back if it has changed.

    Shared by uniform_stock_post_save and uniform_stock_post_delete so the
    sync logic lives in exactly one place.
    """
    total_stock = (
        uniform_item.stock_records.aggregate(
            total=Sum('quantity')
        )['total'] or 0
    )
    if uniform_item.current_stock != total_stock:
        uniform_item.current_stock = total_stock
        uniform_item.save(update_fields=['current_stock'])
        logger.debug(
            f"Synced total stock for {uniform_item.name}: {total_stock}"
        )


@receiver(post_save, sender=UniformStock)
def uniform_stock_post_save(sender, instance, created, **kwargs):
    """
    Keep UniformItem.current_stock in sync with stock record totals,
    and emit low-stock / out-of-stock warnings.

    Syncs current_stock for ALL items (sized and unsized) via a single
    Sum() aggregate. The previous version only ran this for requires_sizing
    items, meaning unsized items' current_stock was never updated from their
    stock record and drifted silently.

    size is nullable (unsized items have size=None) so all references to
    instance.size are guarded before accessing attributes.
    """
    if kwargs.get('raw', False):
        return

    try:
        _sync_item_stock_from_records(instance.uniform_item)

        # Guard: size is None for unsized items
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
    Keep UniformItem.current_stock in sync when a stock record is deleted.

    Without this handler, deleting a stock record leaves current_stock stale
    on the parent item — post_save never fires on deletion so the sync would
    not happen until the next unrelated save triggered it.
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
    for the student so uniform sizing stays up to date.

    Deferred to transaction.on_commit() so the potentially expensive bulk
    update_or_create loop does not run synchronously inside the request cycle
    that saved the measurement. If the transaction rolls back the
    recommendations are not regenerated, which is correct.
    """
    if kwargs.get('raw', False):
        return

    if instance.is_current and instance.is_verified:
        student = instance.student
        academic_session = instance.academic_session

        transaction.on_commit(
            lambda: _update_size_recommendations_for_student(
                student, academic_session
            )
        )


def _update_size_recommendations_for_student(student, academic_session):
    """
    Regenerate StudentUniformSize recommendations for every active,
    sized uniform item after measurements change.

    Called via transaction.on_commit() so it runs after the measurement
    record is fully committed, never inside an open transaction.
    """
    from .models import UniformItem, StudentUniformSize

    uniform_items = UniformItem.objects.filter(is_active=True, requires_sizing=True)

    for uniform_item in uniform_items:
        try:
            recommendation = recommend_size_from_measurements(student, uniform_item)

            if recommendation['recommended_size']:
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
                        'alternative_sizes': (
                            [str(s.id) for s in recommendation['alternative_sizes']]
                            if recommendation['alternative_sizes'] else None
                        ),
                    }
                )
                logger.info(
                    f"Size recommendation updated — {student.get_full_name()} / "
                    f"{uniform_item.name}: size {recommendation['recommended_size'].name}"
                )
        except Exception as e:
            logger.error(
                f"Error updating size recommendation for {uniform_item.name}: {e}",
                exc_info=True
            )


# =============================================================================
# MEASUREMENT SESSION SIGNALS
# =============================================================================

@receiver(post_save, sender=MeasurementSession)
def measurement_session_post_save(sender, instance, created, **kwargs):
    """
    Refresh session statistics when a session is marked as COMPLETED.
    """
    if kwargs.get('raw', False):
        return

    if instance.status == 'COMPLETED':
        try:
            _update_measurement_session_stats(instance)
        except Exception as e:
            logger.error(
                f"Error updating measurement session stats: {e}", exc_info=True
            )


def _update_measurement_session_stats(session):
    """
    Count students measured and total measurements for the session date
    and write the figures back to the session record via queryset update
    (avoids re-triggering the post_save signal).
    """
    from .models import StudentMeasurement

    base_qs = StudentMeasurement.objects.filter(
        measurement_date=session.session_date,
        academic_session=session.academic_session,
    )

    students_measured = base_qs.values('student').distinct().count()
    total_measurements = base_qs.count()

    MeasurementSession.objects.filter(pk=session.pk).update(
        total_students_measured=students_measured,
        total_measurements_taken=total_measurements,
    )

    logger.info(
        f"Session stats updated — {session.session_name}: "
        f"{students_measured} students, {total_measurements} measurements"
    )


# =============================================================================
# SIGNAL TOGGLING (for bulk operations)
# =============================================================================

def disable_uniform_signals():
    """
    Temporarily disconnect the most expensive uniform signals.
    Use around bulk import / migration operations.

    Usage:
        disable_uniform_signals()
        # ... bulk work ...
        enable_uniform_signals()

    Note: decrement_stock_on_sale_item, restore_stock_on_sale_item_delete,
    and restore_stock_on_sale_cancellation_or_return are included so that
    bulk SQL inserts (e.g. the uniform data migration) do not trigger
    incorrect stock movements. Stock quantities must be set manually after
    any bulk operation.
    """
    post_save.disconnect(log_uniform_sale_changes, sender=UniformSale)
    post_save.disconnect(restore_stock_on_sale_cancellation_or_return, sender=UniformSale)
    post_save.disconnect(uniform_sale_item_post_save, sender=UniformSaleItem)
    post_save.disconnect(decrement_stock_on_sale_item, sender=UniformSaleItem)
    post_delete.disconnect(restore_stock_on_sale_item_delete, sender=UniformSaleItem)
    post_save.disconnect(uniform_stock_post_save, sender=UniformStock)
    post_delete.disconnect(uniform_stock_post_delete, sender=UniformStock)
    post_save.disconnect(student_measurement_post_save, sender=StudentMeasurement)
    post_save.disconnect(sync_uniform_sale_after_payment, sender='fees.Payment')

    logger.info("Uniform signals disabled")


def enable_uniform_signals():
    """
    Reconnect uniform signals after bulk operations.

    Uses explicit connect() calls mirroring disable_uniform_signals() instead
    of module reload. Module reload was unreliable because string-based senders
    like 'fees.Payment' are resolved at connect time and reload could register
    duplicate handlers. Explicit connect() is predictable and idempotent when
    dispatch_uid is not used — Django deduplicates by (receiver_func, sender).
    """
    post_save.connect(log_uniform_sale_changes, sender=UniformSale)
    post_save.connect(restore_stock_on_sale_cancellation_or_return, sender=UniformSale)
    post_save.connect(uniform_sale_item_post_save, sender=UniformSaleItem)
    post_save.connect(decrement_stock_on_sale_item, sender=UniformSaleItem)
    post_delete.connect(restore_stock_on_sale_item_delete, sender=UniformSaleItem)
    post_save.connect(uniform_stock_post_save, sender=UniformStock)
    post_delete.connect(uniform_stock_post_delete, sender=UniformStock)
    post_save.connect(student_measurement_post_save, sender=StudentMeasurement)
    post_save.connect(sync_uniform_sale_after_payment, sender='fees.Payment')

    logger.info("Uniform signals re-enabled")