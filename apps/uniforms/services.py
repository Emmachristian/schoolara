# uniforms/services.py

"""
Uniform Sales Service Layer

Handles all business logic for uniform sales including:
- Invoice creation from uniform sales
- Journal entry creation for inventory and revenue
- Stock management and reservations
- Cost of Goods Sold (COGS) calculations
- Automatic accounting entries

Payment processing is handled entirely by the fees module.
When a Payment is saved against a FeeInvoice, fees/signals.py
automatically updates invoice balances, creates journal entries,
and updates student accounts. UniformSale.paid_amount is a
read-only mirror synced via UniformInvoiceService.update_invoice_from_sale().

All operations are transactional to ensure data consistency.
"""

from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from decimal import Decimal
import logging

from .models import (
    UniformSale, UniformSaleItem, UniformStock,
    UniformItem, UniformSize
)
from fees.models import FeeInvoice, FeesCategory
from fees.services import InvoiceService
from fees.utils import generate_invoice_number
from finance.models import (
    JournalEntry, JournalTransaction, Journal, Account
)
from core.models import FiscalPeriod, FinancialSettings

logger = logging.getLogger(__name__)


# =============================================================================
# UNIFORM SALE INVOICE SERVICE
# =============================================================================

class UniformInvoiceService:
    """Service to create and sync fee invoices from uniform sales."""

    @staticmethod
    @transaction.atomic
    def create_invoice_from_sale(uniform_sale):
        """
        Create a FeeInvoice from a finalized uniform sale.

        Only called for sale_type == 'SALE'. Issuances, loans and
        replacements never generate invoices.

        Args:
            uniform_sale: UniformSale instance (must be SALE type)

        Returns:
            FeeInvoice: Newly created invoice

        Raises:
            ValidationError: If preconditions are not met
        """
        if uniform_sale.sale_type != 'SALE':
            raise ValidationError(
                "Only sales (not issuances/loans/replacements) can have invoices"
            )

        if uniform_sale.fee_invoice:
            logger.warning(
                f"Invoice already exists for sale {uniform_sale.sale_number}"
            )
            return uniform_sale.fee_invoice

        if uniform_sale.status == 'CANCELLED':
            raise ValidationError("Cannot create invoice for a cancelled sale")

        # Resolve uniform fee category
        try:
            uniform_category = FeesCategory.objects.get(code='UNIFORM')
        except FeesCategory.DoesNotExist:
            raise ValidationError(
                "Uniform fee category not found. "
                "Create a FeesCategory with code='UNIFORM' before processing sales."
            )

        # Resolve fiscal period
        fiscal_period = uniform_sale.fiscal_period or FiscalPeriod.get_current_fiscal_period()
        if not fiscal_period:
            raise ValidationError("No active fiscal period found")

        # Ensure GL accounts are assigned before creating the invoice
        uniform_sale.ensure_accounts_assigned()

        invoice = FeeInvoice.objects.create(
            student=uniform_sale.student,
            academic_session=uniform_sale.academic_session,
            fiscal_period=fiscal_period,
            fee_structure=None,          # Uniform invoices have no fee structure
            invoice_number=generate_invoice_number(),
            issue_date=uniform_sale.sale_date,
            due_date=uniform_sale.sale_date,   # Uniforms: pay on collection
            subtotal_amount=uniform_sale.subtotal,
            discount_amount=uniform_sale.discount_amount,
            tax_amount=uniform_sale.tax_amount,
            total_amount=uniform_sale.total_amount,
            paid_amount=Decimal('0.00'),
            balance=uniform_sale.total_amount,
            status='PENDING',
            notes=f"Uniform sale: {uniform_sale.sale_number}",
        )

        for sale_item in uniform_sale.items.all():
            size_desc = f" - Size {sale_item.size.name}" if sale_item.size else ""
            item = InvoiceService.add_invoice_item(invoice, {
                'fee_category': uniform_category,
                'description': f"{sale_item.uniform_item.name}{size_desc}",
                'quantity': sale_item.quantity,
                'unit_amount': sale_item.unit_price,
                'amount': sale_item.unit_price,        # per-unit; recalculate_totals multiplies by qty
                'tax_percentage': sale_item.tax_percentage,
                'discount_percentage': sale_item.discount_percentage,
                'discount_amount': sale_item.discount_amount,
            })
            # Derive amount, tax_amount, total_discount_amount, final_amount
            # using the same logic as every other invoice in the system
            item.recalculate_totals()
            item.save()

        # Link invoice back to sale
        uniform_sale.fee_invoice = invoice
        uniform_sale.save(update_fields=['fee_invoice'])

        logger.info(
            f"Created invoice {invoice.invoice_number} "
            f"for uniform sale {uniform_sale.sale_number}"
        )
        return invoice

    @staticmethod
    @transaction.atomic
    def sync_sale_from_invoice(uniform_sale):
        """
        Sync UniformSale payment fields FROM the linked FeeInvoice.

        Called by a post_save signal on Payment after fees/signals.py has
        already updated the FeeInvoice, so that UniformSale.paid_amount,
        .balance, and .status stay accurate.

        Direction is always: FeeInvoice -> UniformSale
        Never the reverse -- the invoice is the source of truth for payments.

        Args:
            uniform_sale: UniformSale instance with a linked fee_invoice

        Returns:
            UniformSale: Updated instance, or original if no invoice linked
        """
        if not uniform_sale.fee_invoice:
            logger.warning(
                f"Cannot sync payment state: no invoice linked to sale "
                f"{uniform_sale.sale_number}"
            )
            return uniform_sale

        invoice = uniform_sale.fee_invoice

        uniform_sale.paid_amount = invoice.paid_amount
        uniform_sale.balance = invoice.balance

        if invoice.balance <= 0:
            uniform_sale.status = 'PAID'
        elif invoice.paid_amount > 0:
            uniform_sale.status = 'PARTIAL'
        # Leave PENDING/ISSUED/etc. untouched if no payment has been made yet

        uniform_sale.save(update_fields=['paid_amount', 'balance', 'status'])

        logger.info(
            f"Synced payment state to uniform sale {uniform_sale.sale_number} "
            f"from invoice {invoice.invoice_number} "
            f"(paid={invoice.paid_amount}, balance={invoice.balance})"
        )
        return uniform_sale



# =============================================================================
# UNIFORM SALE ACCOUNTING SERVICE
# =============================================================================

class UniformAccountingService:
    """Service to create journal entries for uniform sales."""

    @staticmethod
    @transaction.atomic
    def create_journal_entry_for_sale(uniform_sale):
        """
        Create the revenue + COGS journal entry when a sale is finalised.

        Two sets of double-entry lines are created:
          Revenue recognition  — DR Accounts Receivable / CR Uniform Revenue
          COGS recognition     — DR Cost of Goods Sold  / CR Inventory

        Payment journal entries (DR Cash/Bank, CR A/R) are created
        automatically by fees/signals.py when a Payment is saved.

        Args:
            uniform_sale: UniformSale instance

        Returns:
            JournalEntry: Posted journal entry

        Raises:
            ValidationError: If required accounts are missing
        """
        if uniform_sale.journal_entry:
            logger.warning(
                f"Journal entry already exists for sale {uniform_sale.sale_number}"
            )
            return uniform_sale.journal_entry

        if uniform_sale.status in ('DRAFT', 'CANCELLED'):
            raise ValidationError(
                f"Cannot create journal entry for a {uniform_sale.status} sale"
            )

        uniform_sale.ensure_accounts_assigned()

        if not all([
            uniform_sale.receivable_account,
            uniform_sale.revenue_account,
            uniform_sale.inventory_account,
            uniform_sale.cogs_account,
        ]):
            raise ValidationError(
                "All four GL accounts (receivable, revenue, inventory, COGS) "
                "must be assigned before creating a journal entry"
            )

        journal, _ = Journal.objects.get_or_create(
            journal_type='FEES',
            defaults={
                'name': 'Fee Collection Journal',
                'description': 'Journal for fee and uniform sales',
            },
        )

        entry = JournalEntry.objects.create(
            journal=journal,
            entry_number=f"JE-{uniform_sale.sale_number}",
            entry_date=uniform_sale.sale_date,
            fiscal_period=uniform_sale.fiscal_period,
            academic_session=uniform_sale.academic_session,
            reference_number=uniform_sale.sale_number,
            description=(
                f"Uniform sale to {uniform_sale.student.get_full_name()} "
                f"- {uniform_sale.sale_number}"
            ),
            status='POSTED',
        )

        student_name = uniform_sale.student.get_full_name()

        # --- Revenue recognition ---
        JournalTransaction.objects.create(
            journal_entry=entry,
            account=uniform_sale.receivable_account,
            description=f"Uniform sale receivable - {student_name}",
            amount=uniform_sale.total_amount,
            is_debit=True,
        )
        JournalTransaction.objects.create(
            journal_entry=entry,
            account=uniform_sale.revenue_account,
            description=f"Uniform sales revenue - {student_name}",
            amount=uniform_sale.total_amount,
            is_debit=False,
        )

        # --- COGS recognition (only when cost data is present) ---
        if uniform_sale.total_cost > 0:
            JournalTransaction.objects.create(
                journal_entry=entry,
                account=uniform_sale.cogs_account,
                description=f"COGS - uniform sale {uniform_sale.sale_number}",
                amount=uniform_sale.total_cost,
                is_debit=True,
            )
            JournalTransaction.objects.create(
                journal_entry=entry,
                account=uniform_sale.inventory_account,
                description=f"Inventory reduction - sale {uniform_sale.sale_number}",
                amount=uniform_sale.total_cost,
                is_debit=False,
            )

        uniform_sale.journal_entry = entry
        uniform_sale.save(update_fields=['journal_entry'])

        logger.info(
            f"Created journal entry {entry.entry_number} "
            f"for uniform sale {uniform_sale.sale_number}"
        )
        return entry

    @staticmethod
    @transaction.atomic
    def reverse_journal_entry_for_sale(uniform_sale, reason=""):
        """
        Create a reversal journal entry for a cancelled or returned sale.

        Args:
            uniform_sale: UniformSale instance
            reason: Human-readable reason for the reversal

        Returns:
            JournalEntry: Reversal entry, or None if no original entry exists
        """
        if not uniform_sale.journal_entry:
            logger.warning(
                f"No journal entry to reverse for sale {uniform_sale.sale_number}"
            )
            return None

        original = uniform_sale.journal_entry

        if original.status == 'REVERSED':
            logger.warning(
                f"Journal entry {original.entry_number} is already reversed"
            )
            return original

        reversal_reason = reason or f"Reversal for cancelled/returned sale {uniform_sale.sale_number}"

        reversal = JournalEntry.objects.create(
            journal=original.journal,
            entry_number=f"JE-REV-{uniform_sale.sale_number}",
            entry_date=timezone.now().date(),
            fiscal_period=FiscalPeriod.get_current_fiscal_period(),
            academic_session=uniform_sale.academic_session,
            reference_number=f"REV-{original.reference_number}",
            description=f"REVERSAL: {original.description}",
            status='POSTED',
            original_entry=original,
            reversal_reason=reversal_reason,
        )

        for txn in original.transactions.all():
            JournalTransaction.objects.create(
                journal_entry=reversal,
                account=txn.account,
                description=f"REVERSAL: {txn.description}",
                amount=txn.amount,
                is_debit=not txn.is_debit,    # Swap debit <-> credit
            )

        original.status = 'REVERSED'
        original.reversed_at = timezone.now()
        original.save(update_fields=['status', 'reversed_at'])

        logger.info(
            f"Created reversal entry {reversal.entry_number} "
            f"for sale {uniform_sale.sale_number}"
        )
        return reversal


# =============================================================================
# UNIFORM STOCK SERVICE
# =============================================================================

class UniformStockService:
    """Service to manage uniform stock and reservations."""

    @staticmethod
    @transaction.atomic
    def reserve_stock_for_sale(uniform_sale):
        """
        Reserve stock when a sale is finalised (moves into PENDING/PAID).

        Args:
            uniform_sale: UniformSale instance

        Raises:
            ValidationError: If any item has insufficient available stock
        """
        for sale_item in uniform_sale.items.all():
            if sale_item.uniform_item.requires_sizing and sale_item.size:
                stock, _ = UniformStock.objects.get_or_create(
                    uniform_item=sale_item.uniform_item,
                    size=sale_item.size,
                )
                available = stock.available_quantity
                if available < sale_item.quantity:
                    raise ValidationError(
                        f"Insufficient stock for {sale_item.uniform_item.name} "
                        f"size {sale_item.size.name}. "
                        f"Available: {available}, requested: {sale_item.quantity}"
                    )
                stock.reserved_quantity += sale_item.quantity
                stock.save()
                logger.info(
                    f"Reserved {sale_item.quantity}x {sale_item.uniform_item.name} "
                    f"size {sale_item.size.name} for sale {uniform_sale.sale_number}"
                )
            else:
                item = sale_item.uniform_item
                if item.current_stock < sale_item.quantity:
                    raise ValidationError(
                        f"Insufficient stock for {item.name}. "
                        f"Available: {item.current_stock}, requested: {sale_item.quantity}"
                    )

    @staticmethod
    @transaction.atomic
    def release_reserved_stock(uniform_sale):
        """
        Release reserved stock when a sale is cancelled.

        Args:
            uniform_sale: UniformSale instance
        """
        for sale_item in uniform_sale.items.all():
            if sale_item.uniform_item.requires_sizing and sale_item.size:
                try:
                    stock = UniformStock.objects.get(
                        uniform_item=sale_item.uniform_item,
                        size=sale_item.size,
                    )
                    stock.reserved_quantity = max(
                        0, stock.reserved_quantity - sale_item.quantity
                    )
                    stock.save()
                    logger.info(
                        f"Released reservation: {sale_item.quantity}x "
                        f"{sale_item.uniform_item.name} size {sale_item.size.name} "
                        f"(cancelled sale {uniform_sale.sale_number})"
                    )
                except UniformStock.DoesNotExist:
                    logger.warning(
                        f"Stock record not found for {sale_item.uniform_item.name} "
                        f"size {sale_item.size.name} — skipping release"
                    )

    @staticmethod
    @transaction.atomic
    def deduct_stock_for_sale(uniform_sale):
        """
        Physically deduct stock when uniforms are issued to the student.

        Converts the earlier reservation into an actual stock deduction.

        Args:
            uniform_sale: UniformSale instance
        """
        for sale_item in uniform_sale.items.all():
            if sale_item.uniform_item.requires_sizing and sale_item.size:
                stock = UniformStock.objects.get(
                    uniform_item=sale_item.uniform_item,
                    size=sale_item.size,
                )
                stock.quantity -= sale_item.quantity
                stock.reserved_quantity = max(
                    0, stock.reserved_quantity - sale_item.quantity
                )
                stock.save()
                logger.info(
                    f"Deducted {sale_item.quantity}x {sale_item.uniform_item.name} "
                    f"size {sale_item.size.name} for issued sale {uniform_sale.sale_number}"
                )
            else:
                item = sale_item.uniform_item
                item.current_stock -= sale_item.quantity
                item.save()
                logger.info(
                    f"Deducted {sale_item.quantity}x {item.name} "
                    f"for issued sale {uniform_sale.sale_number}"
                )

    @staticmethod
    @transaction.atomic
    def restore_stock_for_return(uniform_sale):
        """
        Restore stock when uniforms are returned.

        Args:
            uniform_sale: UniformSale instance
        """
        for sale_item in uniform_sale.items.all():
            if sale_item.uniform_item.requires_sizing and sale_item.size:
                stock = UniformStock.objects.get(
                    uniform_item=sale_item.uniform_item,
                    size=sale_item.size,
                )
                stock.quantity += sale_item.quantity
                stock.save()
                logger.info(
                    f"Restored {sale_item.quantity}x {sale_item.uniform_item.name} "
                    f"size {sale_item.size.name} for returned sale {uniform_sale.sale_number}"
                )
            else:
                item = sale_item.uniform_item
                item.current_stock += sale_item.quantity
                item.save()
                logger.info(
                    f"Restored {sale_item.quantity}x {item.name} "
                    f"for returned sale {uniform_sale.sale_number}"
                )


# =============================================================================
# UNIFORM SALE WORKFLOW SERVICE
# =============================================================================

class UniformSaleWorkflowService:
    """Service to manage uniform sale state transitions."""

    @staticmethod
    @transaction.atomic
    def finalize_sale(uniform_sale, user=None):
        """
        Finalise a DRAFT sale.

        Steps:
          1. Validate sale has items
          2. Recalculate totals
          3. Ensure GL accounts assigned
          4. Reserve stock
          5. Create FeeInvoice (SALE type only)
          6. Create journal entry (SALE type only)
          7. Advance status

        For non-SALE types (ISSUANCE, LOAN, REPLACEMENT), no invoice or
        journal entry is created; stock is still reserved and status
        advances to PENDING (ready to hand to student).

        Args:
            uniform_sale: UniformSale instance in DRAFT status
            user: User performing the action (optional)

        Returns:
            dict: {uniform_sale, invoice, journal_entry}

        Raises:
            ValidationError: If preconditions are not met
        """
        if uniform_sale.status != 'DRAFT':
            raise ValidationError(
                f"Only DRAFT sales can be finalised "
                f"(current status: {uniform_sale.status})"
            )

        if not uniform_sale.items.exists():
            raise ValidationError("Cannot finalise a sale with no items")

        uniform_sale.calculate_totals()
        uniform_sale.ensure_accounts_assigned()

        try:
            UniformStockService.reserve_stock_for_sale(uniform_sale)
        except ValidationError as e:
            raise ValidationError(f"Stock reservation failed: {e}")

        invoice = None
        journal_entry = None

        if uniform_sale.sale_type == 'SALE':
            invoice = UniformInvoiceService.create_invoice_from_sale(uniform_sale)
            journal_entry = UniformAccountingService.create_journal_entry_for_sale(uniform_sale)
            # Status reflects payment state for billable sales
            uniform_sale.status = 'PENDING' if uniform_sale.balance > 0 else 'PAID'
        else:
            # ISSUANCE / LOAN / REPLACEMENT: no money involved, ready to issue
            uniform_sale.status = 'PENDING'

        uniform_sale.save()

        logger.info(f"Finalised uniform sale {uniform_sale.sale_number}")

        return {
            'uniform_sale': uniform_sale,
            'invoice': invoice,
            'journal_entry': journal_entry,
        }

    @staticmethod
    @transaction.atomic
    def issue_sale(uniform_sale, user=None):
        """
        Hand uniforms to the student and mark the sale as ISSUED.

        For SALE type, payment may still be outstanding — schools commonly
        issue items before full payment is received (collect-on-delivery).
        For non-SALE types the sale will be in PENDING with no payment needed.

        Steps:
          1. Validate status allows issuing
          2. Deduct actual stock (converts reservations to real deductions)
          3. Update status to ISSUED

        Args:
            uniform_sale: UniformSale instance
            user: User performing the action (optional)

        Returns:
            UniformSale: Updated instance

        Raises:
            ValidationError: If sale cannot be issued in its current state
        """
        issuable_statuses = ('PENDING', 'PARTIAL', 'PAID')
        if uniform_sale.status not in issuable_statuses:
            raise ValidationError(
                f"Cannot issue a sale with status '{uniform_sale.status}'. "
                f"Allowed: {', '.join(issuable_statuses)}"
            )

        try:
            UniformStockService.deduct_stock_for_sale(uniform_sale)
        except Exception as e:
            raise ValidationError(f"Stock deduction failed: {e}")

        uniform_sale.status = 'ISSUED'
        uniform_sale.issued_at = timezone.now()

        if user:
            uniform_sale.issued_by_id = str(getattr(user, 'id', user.pk))

        uniform_sale.save()

        logger.info(f"Issued uniform sale {uniform_sale.sale_number}")
        return uniform_sale

    @staticmethod
    @transaction.atomic
    def cancel_sale(uniform_sale, reason="", user=None):
        """
        Cancel a sale that has not yet been issued.

        Steps:
          1. Block cancellation of ISSUED sales (use return instead)
          2. Release reserved stock
          3. Reverse journal entry (if one exists)
          4. Cancel linked invoice (if one exists)
          5. Mark sale as CANCELLED

        Args:
            uniform_sale: UniformSale instance
            reason: Cancellation reason
            user: User performing the action (optional)

        Returns:
            UniformSale: Cancelled instance

        Raises:
            ValidationError: If sale is already cancelled or has been issued
        """
        if uniform_sale.status == 'CANCELLED':
            raise ValidationError("Sale is already cancelled")

        if uniform_sale.status == 'ISSUED':
            raise ValidationError(
                "Cannot cancel an issued sale — use 'Process Return' instead"
            )

        UniformStockService.release_reserved_stock(uniform_sale)

        if uniform_sale.journal_entry:
            UniformAccountingService.reverse_journal_entry_for_sale(
                uniform_sale, reason=reason or "Sale cancelled"
            )

        if uniform_sale.fee_invoice:
            invoice = uniform_sale.fee_invoice
            invoice.status = 'CANCELLED'
            invoice.notes = (
                f"{invoice.notes}\nCANCELLED: {reason}"
                if invoice.notes
                else f"CANCELLED: {reason}"
            )
            invoice.save()

        uniform_sale.status = 'CANCELLED'
        uniform_sale.notes = (
            f"{uniform_sale.notes}\nCANCELLED: {reason}"
            if uniform_sale.notes
            else f"CANCELLED: {reason}"
        )
        uniform_sale.save()

        logger.info(f"Cancelled uniform sale {uniform_sale.sale_number}")
        return uniform_sale

    @staticmethod
    @transaction.atomic
    def return_sale(uniform_sale, reason="", user=None):
        """
        Process a return of already-issued uniforms.

        Steps:
          1. Validate sale is ISSUED
          2. Restore stock
          3. Reverse journal entry
          4. Mark sale as RETURNED

        Any refund owed to the student is processed separately via the
        fees module against the linked FeeInvoice.

        Args:
            uniform_sale: UniformSale instance
            reason: Return reason
            user: User performing the action (optional)

        Returns:
            UniformSale: Updated instance

        Raises:
            ValidationError: If sale is not in ISSUED status
        """
        if uniform_sale.status != 'ISSUED':
            raise ValidationError(
                f"Only ISSUED sales can be returned "
                f"(current status: {uniform_sale.status})"
            )

        UniformStockService.restore_stock_for_return(uniform_sale)

        if uniform_sale.journal_entry:
            UniformAccountingService.reverse_journal_entry_for_sale(
                uniform_sale, reason=reason or "Uniforms returned"
            )

        uniform_sale.status = 'RETURNED'
        uniform_sale.notes = (
            f"{uniform_sale.notes}\nRETURNED: {reason}"
            if uniform_sale.notes
            else f"RETURNED: {reason}"
        )
        uniform_sale.save()

        logger.info(f"Processed return for uniform sale {uniform_sale.sale_number}")
        return uniform_sale


# =============================================================================
# UNIFORM SALE BUILDER SERVICE
# =============================================================================

class UniformSaleBuilder:
    """
    Builder pattern for creating uniform sales with line items.

    Usage:
        sale = (
            UniformSaleBuilder(student, session)
            .add_item(shirt, size_m, quantity=2)
            .add_item(trousers, size_32)
            .set_discount(Decimal('5000'), reason="Staff child")
            .build()
        )
    """

    def __init__(self, student, academic_session, sale_type='SALE'):
        self.student = student
        self.academic_session = academic_session
        self.sale_type = sale_type
        self._items = []
        self.discount_amount = Decimal('0.00')
        self.discount_reason = ""
        self.notes = ""

    def add_item(self, uniform_item, size=None, quantity=1):
        """
        Queue a line item to be added to the sale.

        Args:
            uniform_item: UniformItem instance
            size: UniformSize instance (required when item requires_sizing)
            quantity: Number of units

        Returns:
            self (for method chaining)
        """
        if uniform_item.requires_sizing and not size:
            raise ValidationError(f"'{uniform_item.name}' requires a size selection")

        tax_percentage = Decimal('0.00')
        if uniform_item.is_taxable:
            if uniform_item.tax_rate:
                tax_percentage = uniform_item.tax_rate.rate
            else:
                settings = FinancialSettings.get_instance()
                if settings:
                    tax_percentage = settings.default_tax_rate

        self._items.append({
            'uniform_item': uniform_item,
            'size': size,
            'quantity': quantity,
            'unit_price': uniform_item.selling_price,
            'unit_cost': uniform_item.unit_cost,
            'tax_percentage': tax_percentage,
        })
        return self

    def set_discount(self, amount, reason=""):
        """Set a sale-level discount amount."""
        self.discount_amount = amount
        self.discount_reason = reason
        return self

    def set_notes(self, notes):
        """Set free-text notes on the sale."""
        self.notes = notes
        return self

    @transaction.atomic
    def build(self):
        """
        Persist the sale and its items in DRAFT status.

        Returns:
            UniformSale in DRAFT status

        Raises:
            ValidationError: If no items have been added
        """
        if not self._items:
            raise ValidationError("Cannot create a sale with no items")

        fiscal_period = FiscalPeriod.get_current_fiscal_period()
        if not fiscal_period:
            raise ValidationError("No active fiscal period found")

        sale_count = UniformSale.objects.count() + 1
        sale_number = f"US-{timezone.now().year}-{sale_count:05d}"

        sale = UniformSale.objects.create(
            sale_number=sale_number,
            student=self.student,
            academic_session=self.academic_session,
            fiscal_period=fiscal_period,
            sale_type=self.sale_type,
            sale_date=timezone.now().date(),
            discount_amount=self.discount_amount,
            discount_reason=self.discount_reason,
            notes=self.notes,
            status='DRAFT',
        )

        for item_data in self._items:
            UniformSaleItem.objects.create(
                sale=sale,
                uniform_item=item_data['uniform_item'],
                size=item_data['size'],
                quantity=item_data['quantity'],
                unit_price=item_data['unit_price'],
                unit_cost=item_data['unit_cost'],
                tax_percentage=item_data['tax_percentage'],
            )

        sale.calculate_totals()

        logger.info(f"Created uniform sale {sale.sale_number} in DRAFT status")
        return sale


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def create_uniform_sale(student, academic_session, items, **kwargs):
    """
    Convenience wrapper around UniformSaleBuilder.

    Args:
        student: Student instance
        academic_session: AcademicSession instance
        items: List of dicts with keys: uniform_item, size (optional), quantity
        **kwargs: sale_type, discount_amount, discount_reason, notes

    Returns:
        UniformSale in DRAFT status

    Example:
        sale = create_uniform_sale(
            student=student,
            academic_session=session,
            items=[
                {'uniform_item': shirt, 'size': size_m, 'quantity': 2},
                {'uniform_item': trousers, 'size': size_32, 'quantity': 1},
            ],
            discount_amount=Decimal('5000.00'),
            discount_reason="Staff child discount",
        )
    """
    builder = UniformSaleBuilder(
        student=student,
        academic_session=academic_session,
        sale_type=kwargs.get('sale_type', 'SALE'),
    )

    for item_data in items:
        builder.add_item(
            uniform_item=item_data['uniform_item'],
            size=item_data.get('size'),
            quantity=item_data.get('quantity', 1),
        )

    if 'discount_amount' in kwargs:
        builder.set_discount(
            amount=kwargs['discount_amount'],
            reason=kwargs.get('discount_reason', ''),
        )

    if 'notes' in kwargs:
        builder.set_notes(kwargs['notes'])

    return builder.build()


def finalize_and_issue_sale(uniform_sale, user=None):
    """
    Convenience wrapper: finalise a DRAFT sale and immediately issue it.

    Useful for walk-in sales where the student collects items on the spot.

    Args:
        uniform_sale: UniformSale instance in DRAFT status
        user: User performing the action

    Returns:
        dict: {uniform_sale, invoice, journal_entry}
    """
    results = UniformSaleWorkflowService.finalize_sale(uniform_sale, user)
    issued_sale = UniformSaleWorkflowService.issue_sale(uniform_sale, user)
    results['uniform_sale'] = issued_sale
    return results