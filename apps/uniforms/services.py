# uniforms/services.py

"""
Uniform Management Services

Business logic that spans multiple models or requires transactional
coordination. Views and signals delegate to these services so complex
operations stay testable and reusable.

Services in this module:

    UniformInvoiceService
        Manages the relationship between UniformSale and FeeInvoice.
        Creates, syncs and cancels invoices.

    UniformAccountingService
        Creates and reverses journal entries for uniform sales and
        purchase orders.

    UniformStockService
        Manages stock reservation and release for pending/draft sales.
        Does NOT decrement or restore stock — that is handled by:
          - Decrement → views.uniform_sale_issue (on physical handover)
          - Restore   → utils.return_uniform_sale (on physical return)

    UniformSaleWorkflowService
        Orchestrates the full sale lifecycle: finalise → invoice → journal
        entry → issue. Each step is explicit so callers always know what
        happened.

DESIGN RULES
------------
- Stock moves only at issue time (decrement) and return time (restore).
  No service here should touch stock quantities directly — use UniformStock
  through UniformStock.save() so signals keep current_stock accurate.
- MeasurementSession has been removed. No references to it here.
- academic_session is derived from fiscal_period.related_academic_session
  on UniformSale — never stored directly on the sale.
- All database writes that span multiple tables must be wrapped in
  transaction.atomic() at the call site or within the service method.
"""

from django.db import transaction
from django.utils import timezone
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# UNIFORM INVOICE SERVICE
# =============================================================================

class UniformInvoiceService:
    """
    Manages the FeeInvoice linked to a UniformSale.

    A sale may optionally have auto_create_invoice=True, in which case
    finalise_sale() on UniformSaleWorkflowService triggers invoice creation
    here. The invoice drives the payment tracking — paid_amount and balance
    on the sale are synced from the invoice whenever a payment is recorded
    (via the sync_uniform_sale_after_payment signal).
    """

    @staticmethod
    @transaction.atomic
    def create_invoice_for_sale(sale):
        """
        Create a FeeInvoice for a uniform sale and link it to the sale.

        Only creates if:
        - sale.auto_create_invoice is True
        - no invoice is already linked

        Args:
            sale: UniformSale instance (must have items and totals calculated)

        Returns:
            FeeInvoice or None: the created invoice, or None if skipped.
        """
        if not sale.auto_create_invoice:
            logger.debug(
                f"auto_create_invoice=False for {sale.sale_number} — skipping"
            )
            return None

        if sale.fee_invoice_id:
            logger.debug(
                f"Invoice already linked to {sale.sale_number} — skipping"
            )
            return sale.fee_invoice

        try:
            from fees.services import FeeInvoiceService
            from fees.models import FeeInvoice

            invoice = FeeInvoiceService.create_uniform_sale_invoice(sale)

            if invoice:
                # Use queryset update to avoid re-triggering post_save signal.
                from .models import UniformSale
                UniformSale.objects.filter(pk=sale.pk).update(
                    fee_invoice=invoice
                )
                sale.fee_invoice = invoice
                logger.info(
                    f"Created invoice {invoice.invoice_number} "
                    f"for sale {sale.sale_number}"
                )

            return invoice

        except ImportError:
            logger.debug("Fee management module not available — invoice not created")
            return None
        except Exception as e:
            logger.error(
                f"Error creating invoice for sale {sale.sale_number}: {e}",
                exc_info=True,
            )
            raise

    @staticmethod
    @transaction.atomic
    def cancel_invoice_for_sale(sale, reason="Sale cancelled"):
        """
        Cancel the FeeInvoice linked to a sale.

        Args:
            sale:   UniformSale instance
            reason: Human-readable reason for cancellation
        """
        if not sale.fee_invoice_id:
            return

        try:
            invoice = sale.fee_invoice
            if invoice.status not in ('CANCELLED', 'VOID'):
                invoice.status = 'CANCELLED'
                invoice.save()
                logger.info(
                    f"Cancelled invoice {invoice.invoice_number} "
                    f"for sale {sale.sale_number}: {reason}"
                )
        except Exception as e:
            logger.error(
                f"Error cancelling invoice for sale {sale.sale_number}: {e}",
                exc_info=True,
            )
            raise

    @staticmethod
    def sync_sale_from_invoice(sale):
        """
        Sync paid_amount, balance, and status on a UniformSale from its
        linked FeeInvoice. Called by the sync_uniform_sale_after_payment
        signal whenever a Payment is saved in the fees module.

        Uses queryset update to avoid re-triggering the sale post_save signal
        and to avoid a stale-read race condition.

        Args:
            sale: UniformSale instance with fee_invoice linked
        """
        if not sale.fee_invoice_id:
            return

        try:
            from .models import UniformSale

            invoice     = sale.fee_invoice
            paid_amount = invoice.amount_paid or Decimal('0.00')
            balance     = invoice.balance     or Decimal('0.00')

            # Determine the appropriate sale status from invoice state.
            if invoice.status == 'PAID' or balance <= 0:
                new_status = 'PAID'
            elif paid_amount > 0:
                new_status = 'PARTIAL'
            else:
                new_status = sale.status   # leave unchanged

            # Don't overwrite terminal states.
            if sale.status in ('ISSUED', 'CANCELLED', 'RETURNED'):
                new_status = sale.status

            UniformSale.objects.filter(pk=sale.pk).update(
                paid_amount=paid_amount,
                balance=balance,
                status=new_status,
            )

            logger.debug(
                f"Synced sale {sale.sale_number} from invoice — "
                f"paid: {paid_amount}, balance: {balance}, status: {new_status}"
            )

        except Exception as e:
            logger.error(
                f"Error syncing sale {sale.sale_number} from invoice: {e}",
                exc_info=True,
            )


# =============================================================================
# UNIFORM ACCOUNTING SERVICE
# =============================================================================

class UniformAccountingService:
    """
    Creates and reverses journal entries for uniform sales.

    Journal entry structure for a sale:
        DR Student Receivables   (total_amount)
        CR Uniform Revenue       (total_amount)
        DR COGS                  (total_cost)
        CR Inventory             (total_cost)

    Reversal (on return):
        DR Uniform Revenue       (total_amount)
        CR Student Receivables   (total_amount)
        DR Inventory             (total_cost)
        CR COGS                  (total_cost)

    Return reversals are handled by utils.return_uniform_sale() which calls
    this class indirectly. Purchase order journal entries are handled by
    _create_purchase_order_journal_entry() in signals.py.
    """

    @staticmethod
    @transaction.atomic
    def create_journal_entry_for_sale(sale):
        """
        Create the initial journal entry for a finalised uniform sale.

        Only creates if:
        - sale.auto_create_journal_entry is True
        - no journal entry is already linked

        Args:
            sale: UniformSale instance with totals calculated

        Returns:
            JournalEntry or None
        """
        if not sale.auto_create_journal_entry:
            return None

        if sale.journal_entry_id:
            logger.debug(
                f"Journal entry already linked to {sale.sale_number} — skipping"
            )
            return sale.journal_entry

        try:
            from finance.models import JournalEntry, JournalTransaction, Journal

            journal = Journal.objects.filter(journal_type='GENERAL').first()
            if not journal:
                logger.warning(
                    f"No General Journal found — skipping journal entry "
                    f"for sale {sale.sale_number}"
                )
                return None

            if not sale.fiscal_period_id:
                logger.warning(
                    f"No fiscal period on sale {sale.sale_number} — "
                    f"skipping journal entry"
                )
                return None

            receivable_account = sale.get_receivable_account()
            revenue_account    = sale.get_revenue_account()
            cogs_account       = sale.get_cogs_account()
            inventory_account  = sale.get_inventory_account()

            if not all([
                receivable_account, revenue_account,
                cogs_account, inventory_account,
            ]):
                logger.warning(
                    f"One or more GL accounts not configured — journal entry "
                    f"for sale {sale.sale_number} not created"
                )
                return None

            entry = JournalEntry.objects.create(
                journal=journal,
                entry_number=f"JE-US-{sale.sale_number}",
                entry_date=sale.sale_date,
                fiscal_period=sale.fiscal_period,
                reference_number=sale.sale_number,
                description=(
                    f"Uniform sale {sale.sale_number} — "
                    f"{sale.student.get_full_name()}"
                ),
                status='POSTED',
            )

            # Revenue recognition: DR Receivables / CR Revenue
            JournalTransaction.objects.create(
                journal_entry=entry,
                account=receivable_account,
                amount=sale.total_amount,
                is_debit=True,
                description=f"Receivable — uniform sale {sale.sale_number}",
            )
            JournalTransaction.objects.create(
                journal_entry=entry,
                account=revenue_account,
                amount=sale.total_amount,
                is_debit=False,
                description=f"Uniform sales revenue — {sale.sale_number}",
            )

            # COGS: DR COGS / CR Inventory
            if sale.total_cost > 0:
                JournalTransaction.objects.create(
                    journal_entry=entry,
                    account=cogs_account,
                    amount=sale.total_cost,
                    is_debit=True,
                    description=f"COGS — uniform sale {sale.sale_number}",
                )
                JournalTransaction.objects.create(
                    journal_entry=entry,
                    account=inventory_account,
                    amount=sale.total_cost,
                    is_debit=False,
                    description=f"Inventory reduction — uniform sale {sale.sale_number}",
                )

            # Use queryset update to avoid re-triggering post_save signal.
            from .models import UniformSale
            UniformSale.objects.filter(pk=sale.pk).update(journal_entry=entry)
            sale.journal_entry = entry

            logger.info(
                f"Created journal entry {entry.entry_number} "
                f"for sale {sale.sale_number}"
            )
            return entry

        except Exception as e:
            logger.error(
                f"Error creating journal entry for sale {sale.sale_number}: {e}",
                exc_info=True,
            )
            raise

    @staticmethod
    @transaction.atomic
    def reverse_journal_entry_for_sale(sale, reason="Sale deleted"):
        """
        Reverse the journal entry linked to a sale.

        Called by uniform_sale_pre_delete when a non-issued sale is deleted
        and by return_uniform_sale() in utils.py for returned sales.

        Args:
            sale:   UniformSale instance
            reason: Human-readable reversal reason
        """
        if not sale.journal_entry_id:
            return

        try:
            entry = sale.journal_entry

            if entry.status == 'REVERSED':
                logger.debug(
                    f"Journal entry {entry.entry_number} already reversed — skipping"
                )
                return

            if hasattr(entry, 'reverse'):
                # If JournalEntry has a built-in reverse method, use it.
                entry.reverse(reason=reason)
            else:
                entry.status = 'REVERSED'
                entry.save()

            logger.info(
                f"Reversed journal entry {entry.entry_number} "
                f"for sale {sale.sale_number}: {reason}"
            )

        except Exception as e:
            logger.error(
                f"Error reversing journal entry for sale {sale.sale_number}: {e}",
                exc_info=True,
            )
            raise


# =============================================================================
# UNIFORM STOCK SERVICE
# =============================================================================

class UniformStockService:
    """
    Manages stock reservation for pending/draft sales.

    IMPORTANT — stock quantity changes are NOT handled here.
    - Decrement on physical issue  → views.uniform_sale_issue
    - Restore on physical return   → utils.return_uniform_sale
    - Restore on cancellation      → nothing to restore (not issued yet)

    This service only manages the reserved_quantity field on UniformStock,
    which tracks units earmarked for pending sales but not yet physically
    issued.
    """

    @staticmethod
    @transaction.atomic
    def reserve_stock_for_sale(sale):
        """
        Increment reserved_quantity for every line item on a pending sale.

        Called when a sale transitions from DRAFT to PENDING so that the
        reserved units are excluded from available_quantity checks for
        other sales.

        Args:
            sale: UniformSale instance

        Returns:
            tuple: (success: bool, errors: list of str)
        """
        from .models import UniformStock

        errors = []

        for item in sale.items.select_related('uniform_item', 'size').all():
            try:
                if item.uniform_item.requires_sizing and item.size:
                    stock = UniformStock.objects.select_for_update().get(
                        uniform_item=item.uniform_item,
                        size=item.size,
                    )
                else:
                    stock = UniformStock.objects.select_for_update().get(
                        uniform_item=item.uniform_item,
                        size__isnull=True,
                    )

                if stock.available_quantity < item.quantity:
                    size_label = f" Size {item.size.name}" if item.size else ""
                    errors.append(
                        f"Insufficient stock for {item.uniform_item.name}"
                        f"{size_label}: "
                        f"{stock.available_quantity} available, "
                        f"{item.quantity} requested"
                    )
                    continue

                stock.reserved_quantity += item.quantity
                stock.save()

            except UniformStock.DoesNotExist:
                size_label = f" Size {item.size.name}" if item.size else ""
                errors.append(
                    f"No stock record found for "
                    f"{item.uniform_item.name}{size_label}"
                )

        if errors:
            logger.warning(
                f"Stock reservation errors for sale {sale.sale_number}: "
                f"{errors}"
            )

        return len(errors) == 0, errors

    @staticmethod
    @transaction.atomic
    def release_reserved_stock(sale):
        """
        Decrement reserved_quantity for every line item on a sale.

        Called when a draft/pending sale is deleted before it is issued,
        so that the reserved units become available again.

        Args:
            sale: UniformSale instance
        """
        from .models import UniformStock

        for item in sale.items.select_related('uniform_item', 'size').all():
            try:
                if item.uniform_item.requires_sizing and item.size:
                    stock = UniformStock.objects.select_for_update().get(
                        uniform_item=item.uniform_item,
                        size=item.size,
                    )
                else:
                    stock = UniformStock.objects.select_for_update().get(
                        uniform_item=item.uniform_item,
                        size__isnull=True,
                    )

                stock.reserved_quantity = max(
                    0, stock.reserved_quantity - item.quantity
                )
                stock.save()

                size_label = f" Size {item.size.name}" if item.size else ""
                logger.debug(
                    f"Released reservation: {item.uniform_item.name}"
                    f"{size_label} -{item.quantity}"
                )

            except UniformStock.DoesNotExist:
                # Stock record may have been deleted already — log and continue.
                size_label = f" Size {item.size.name}" if item.size else ""
                logger.warning(
                    f"No stock record to release for "
                    f"{item.uniform_item.name}{size_label}"
                )

    @staticmethod
    def check_stock_for_sale(sale):
        """
        Validate that sufficient stock exists for every line item on a sale
        before it is issued.

        Reads available_quantity from UniformStock (which excludes reserved
        units) so double-bookings are caught.

        Args:
            sale: UniformSale instance

        Returns:
            tuple: (all_available: bool, errors: list of str)
        """
        from .models import UniformStock

        errors = []

        for item in sale.items.select_related('uniform_item', 'size').all():
            try:
                if item.uniform_item.requires_sizing and item.size:
                    stock = UniformStock.objects.get(
                        uniform_item=item.uniform_item,
                        size=item.size,
                    )
                else:
                    stock = UniformStock.objects.get(
                        uniform_item=item.uniform_item,
                        size__isnull=True,
                    )
                available = stock.available_quantity
            except UniformStock.DoesNotExist:
                available = 0

            if available < item.quantity:
                size_label = f" Size {item.size.name}" if item.size else ""
                errors.append(
                    f"{item.uniform_item.name}{size_label}: "
                    f"{available} available, {item.quantity} required"
                )

        return len(errors) == 0, errors


# =============================================================================
# UNIFORM SALE WORKFLOW SERVICE
# =============================================================================

class UniformSaleWorkflowService:
    """
    Orchestrates the full uniform sale lifecycle.

    Lifecycle stages:
        DRAFT → (finalise) → PENDING / PAID → (issue) → ISSUED
                                                       → (return) → RETURNED
              → (cancel)  → CANCELLED

    Each method is explicit about what it does so callers always know exactly
    what side-effects occurred. Invoice and journal entry creation happen here
    — not in signals — so there is a single, auditable code path.

    Stock movement:
        - Issue  → views.uniform_sale_issue (decrement)
        - Return → utils.return_uniform_sale (restore via UniformStock)
        - Cancel → nothing (stock was never decremented pre-issue)
    """

    @staticmethod
    @transaction.atomic
    def finalise_sale(sale, user=None):
        """
        Transition a DRAFT sale to PENDING (or PAID if total is zero).

        Steps:
        1. Validate the sale has at least one item.
        2. Recalculate totals.
        3. Create a fee invoice (if auto_create_invoice=True).
        4. Create a journal entry (if auto_create_journal_entry=True).
        5. Set status to PAID (zero-amount) or PENDING.

        Args:
            sale: UniformSale instance in DRAFT status
            user: User performing the action (for audit)

        Returns:
            tuple: (success: bool, message: str, sale: UniformSale)

        Raises:
            ValueError: If the sale is not in DRAFT status or has no items.
        """
        if sale.status != 'DRAFT':
            return False, f"Sale is not in DRAFT status (current: {sale.status})", sale

        if not sale.items.exists():
            return False, "Cannot finalise a sale with no items", sale

        try:
            # 1. Recalculate totals from current line items.
            sale.calculate_totals()

            # 2. Create fee invoice.
            invoice = UniformInvoiceService.create_invoice_for_sale(sale)

            # 3. Create journal entry.
            entry = UniformAccountingService.create_journal_entry_for_sale(sale)

            # 4. Set status.
            sale.status = 'PAID' if sale.total_amount == 0 else 'PENDING'
            sale.save()

            logger.info(
                f"Sale {sale.sale_number} finalised — "
                f"status: {sale.status}, "
                f"invoice: {invoice.invoice_number if invoice else 'none'}, "
                f"journal: {entry.entry_number if entry else 'none'}"
            )
            return True, f"Sale {sale.sale_number} finalised successfully", sale

        except Exception as e:
            logger.error(
                f"Error finalising sale {sale.sale_number}: {e}", exc_info=True
            )
            raise

    @staticmethod
    @transaction.atomic
    def issue_sale(sale, user):
        """
        Physically issue uniform items to the student.

        Validates stock availability for every line, decrements stock
        through UniformStock.save() (so signals keep current_stock
        accurate), then marks the sale as ISSUED.

        Args:
            sale: UniformSale instance in PAID or PARTIAL status
            user: User performing the issue (stored on the sale)

        Returns:
            tuple: (success: bool, message: str)
        """
        from .models import UniformStock
        from core.utils import get_school_current_time

        if sale.status not in ('PAID', 'PARTIAL'):
            return (
                False,
                f"Sale must be PAID or PARTIALLY PAID before issuing "
                f"(current status: {sale.status})",
            )

        if sale.cancelled or sale.returned:
            return False, "Cannot issue a cancelled or returned sale"

        # Validate stock first so we either issue everything or nothing.
        all_ok, stock_errors = UniformStockService.check_stock_for_sale(sale)
        if not all_ok:
            return False, f"Insufficient stock: {'; '.join(stock_errors)}"

        try:
            for item in sale.items.select_related('uniform_item', 'size').all():
                if item.uniform_item.requires_sizing and item.size:
                    stock = UniformStock.objects.select_for_update().get(
                        uniform_item=item.uniform_item,
                        size=item.size,
                    )
                else:
                    try:
                        stock = UniformStock.objects.select_for_update().get(
                            uniform_item=item.uniform_item,
                            size__isnull=True,
                        )
                    except UniformStock.DoesNotExist:
                        size_label = f" Size {item.size.name}" if item.size else ""
                        return (
                            False,
                            f"No stock record found for "
                            f"{item.uniform_item.name}{size_label}",
                        )

                stock.quantity -= item.quantity

                # Also release any reservation held for this item.
                stock.reserved_quantity = max(
                    0, stock.reserved_quantity - item.quantity
                )
                stock.save()
                # uniform_stock_post_save signal syncs current_stock.

                size_label = f" Size {item.size.name}" if item.size else ""
                logger.info(
                    f"Issued {item.quantity}× {item.uniform_item.name}"
                    f"{size_label} for sale {sale.sale_number}"
                )

            sale.status      = 'ISSUED'
            sale.issued_by_id= str(user.id) if user else None
            sale.issued_at   = get_school_current_time()
            sale.save()

            logger.info(
                f"Sale {sale.sale_number} issued to "
                f"{sale.student.get_full_name()} by {user}"
            )
            return True, f"Uniforms issued to {sale.student.get_full_name()}"

        except Exception as e:
            logger.error(
                f"Error issuing sale {sale.sale_number}: {e}", exc_info=True
            )
            raise

    @staticmethod
    @transaction.atomic
    def mark_paid(sale, amount, payment_method=None, payment_reference=None):
        """
        Record a payment against a uniform sale without going through the
        full fee-invoice payment workflow (e.g. for cash payments at the
        counter that bypass the fee system).

        Updates paid_amount, balance, and status directly on the sale.
        If a fee invoice is linked, the invoice is updated too.

        Args:
            sale:               UniformSale instance (PENDING or PARTIAL)
            amount:             Decimal amount received
            payment_method:     PaymentMethod instance (optional)
            payment_reference:  str reference (optional)

        Returns:
            tuple: (success: bool, message: str)
        """
        if sale.status not in ('PENDING', 'PARTIAL'):
            return (
                False,
                f"Sale must be PENDING or PARTIAL to record payment "
                f"(current: {sale.status})",
            )

        amount = Decimal(str(amount))
        if amount <= 0:
            return False, "Payment amount must be greater than zero"

        new_paid    = min(sale.paid_amount + amount, sale.total_amount)
        new_balance = sale.total_amount - new_paid
        new_status  = 'PAID' if new_balance <= 0 else 'PARTIAL'

        from .models import UniformSale
        update_fields = {
            'paid_amount': new_paid,
            'balance':     new_balance,
            'status':      new_status,
        }
        if payment_method:
            update_fields['payment_method'] = payment_method
        if payment_reference:
            update_fields['payment_reference'] = payment_reference

        UniformSale.objects.filter(pk=sale.pk).update(**update_fields)

        # Sync the linked invoice if one exists.
        if sale.fee_invoice_id:
            try:
                invoice = sale.fee_invoice
                invoice.amount_paid = new_paid
                invoice.balance     = new_balance
                invoice.status      = 'PAID' if new_balance <= 0 else 'PARTIALLY_PAID'
                invoice.save()
            except Exception as e:
                logger.warning(
                    f"Could not sync invoice for sale {sale.sale_number}: {e}"
                )

        logger.info(
            f"Payment recorded for sale {sale.sale_number}: "
            f"{amount} — new status: {new_status}"
        )
        return True, f"Payment of {amount} recorded. Status: {new_status}"

    @staticmethod
    def get_sale_summary(sale):
        """
        Return a flat dict summarising a sale's current state — useful for
        API responses and print views that need a single data structure.

        Args:
            sale: UniformSale instance

        Returns:
            dict: Sale summary
        """
        items = list(
            sale.items.select_related('uniform_item', 'size').values(
                'uniform_item__name',
                'uniform_item__code',
                'size__name',
                'quantity',
                'unit_price',
                'unit_cost',
                'total_price',
                'total_cost',
                'tax_amount',
                'discount_amount',
            )
        )

        return {
            'sale_number':    sale.sale_number,
            'sale_date':      sale.sale_date,
            'student':        sale.student.get_full_name(),
            'admission_no':   sale.student.admission_number,
            'status':         sale.get_status_display(),
            'sale_state':     sale.sale_state,
            'sale_type':      sale.get_sale_type_display(),
            'items':          items,
            'subtotal':       sale.subtotal,
            'discount':       sale.discount_amount,
            'tax':            sale.tax_amount,
            'total':          sale.total_amount,
            'paid':           sale.paid_amount,
            'balance':        sale.balance,
            'gross_profit':   sale.gross_profit,
            'gross_margin':   sale.gross_margin_percentage,
            'invoice_number': (
                sale.fee_invoice.invoice_number if sale.fee_invoice_id else None
            ),
            'academic_session': (
                str(sale.academic_session) if sale.academic_session else None
            ),
            'currency':       sale.currency,
            'exchange_rate':  sale.exchange_rate,
            'audit_trail':    sale.get_audit_trail(),
        }