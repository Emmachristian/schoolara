# uniforms/services.py

"""
Uniform Sales Service Layer

Handles all business logic for uniform sales including:
- Invoice creation from uniform sales
- Journal entry creation for inventory and revenue
- Stock management and reservations
- Payment processing integration
- Cost of Goods Sold (COGS) calculations
- Automatic accounting entries

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
from fees.models import (
    FeeInvoice, FeeInvoiceItem, FeesCategory, 
    Payment, StudentAccount, AccountTransaction
)
from finance.models import (
    JournalEntry, JournalTransaction, Journal, Account
)
from core.models import FiscalPeriod, FinancialSettings

logger = logging.getLogger(__name__)


# =============================================================================
# UNIFORM SALE INVOICE SERVICE
# =============================================================================

class UniformInvoiceService:
    """Service to create fee invoices from uniform sales"""
    
    @staticmethod
    @transaction.atomic
    def create_invoice_from_sale(uniform_sale):
        """
        Create a fee invoice from a uniform sale.
        
        Args:
            uniform_sale: UniformSale instance
            
        Returns:
            FeeInvoice: Created invoice
            
        Raises:
            ValidationError: If validation fails
        """
        # Validate sale
        if uniform_sale.sale_type != 'SALE':
            raise ValidationError(
                "Only sales (not issuances/loans) can have invoices created"
            )
        
        if uniform_sale.fee_invoice:
            logger.warning(f"Invoice already exists for sale {uniform_sale.sale_number}")
            return uniform_sale.fee_invoice
        
        if uniform_sale.status == 'CANCELLED':
            raise ValidationError("Cannot create invoice for cancelled sale")
        
        # Get uniform fee category
        try:
            uniform_category = FeesCategory.objects.get(code='UNIFORM')
        except FeesCategory.DoesNotExist:
            raise ValidationError(
                "Uniform fee category not found. Please create a fee category with code 'UNIFORM'"
            )
        
        # Get fiscal period
        fiscal_period = uniform_sale.fiscal_period
        if not fiscal_period:
            fiscal_period = FiscalPeriod.get_current_fiscal_period()
            if not fiscal_period:
                raise ValidationError("No active fiscal period found")
        
        # Ensure accounts are assigned
        uniform_sale.ensure_accounts_assigned()
        
        # Generate invoice number (using sale number or generate new)
        invoice_number = f"INV-{uniform_sale.sale_number}"
        
        # Create invoice
        invoice = FeeInvoice.objects.create(
            student=uniform_sale.student,
            academic_session=uniform_sale.academic_session,
            fiscal_period=fiscal_period,
            fee_structure=None,  # Uniforms don't use fee structure
            invoice_number=invoice_number,
            issue_date=uniform_sale.sale_date,
            due_date=uniform_sale.sale_date,  # Immediate payment for uniforms
            subtotal_amount=uniform_sale.subtotal,
            discount_amount=uniform_sale.discount_amount,
            tax_amount=uniform_sale.tax_amount,
            total_amount=uniform_sale.total_amount,
            paid_amount=uniform_sale.paid_amount,
            balance=uniform_sale.balance,
            status='PENDING' if uniform_sale.balance > 0 else 'PAID',
            revenue_account=uniform_sale.revenue_account,
            receivable_account=uniform_sale.receivable_account,
            notes=f"Uniform sale: {uniform_sale.sale_number}"
        )
        
        # Create invoice items
        for sale_item in uniform_sale.items.all():
            size_desc = f" - Size {sale_item.size.name}" if sale_item.size else ""
            
            FeeInvoiceItem.objects.create(
                invoice=invoice,
                fee_category=uniform_category,
                description=f"{sale_item.uniform_item.name}{size_desc}",
                quantity=sale_item.quantity,
                unit_amount=sale_item.unit_price,
                amount=sale_item.total_price,
                tax_percentage=sale_item.tax_percentage,
                tax_amount=sale_item.tax_amount,
                discount_percentage=sale_item.discount_percentage,
                discount_amount=sale_item.discount_amount,
                total_discount_amount=sale_item.discount_amount,
                final_amount=sale_item.total_price + sale_item.tax_amount - sale_item.discount_amount
            )
        
        # Link invoice to sale
        uniform_sale.fee_invoice = invoice
        uniform_sale.save()
        
        logger.info(f"Created invoice {invoice.invoice_number} for uniform sale {uniform_sale.sale_number}")
        
        return invoice
    
    @staticmethod
    @transaction.atomic
    def update_invoice_from_sale(uniform_sale):
        """
        Update existing invoice when sale is modified.
        
        Args:
            uniform_sale: UniformSale instance
            
        Returns:
            FeeInvoice: Updated invoice
        """
        if not uniform_sale.fee_invoice:
            return UniformInvoiceService.create_invoice_from_sale(uniform_sale)
        
        invoice = uniform_sale.fee_invoice
        
        # Update invoice totals
        invoice.subtotal_amount = uniform_sale.subtotal
        invoice.discount_amount = uniform_sale.discount_amount
        invoice.tax_amount = uniform_sale.tax_amount
        invoice.total_amount = uniform_sale.total_amount
        invoice.paid_amount = uniform_sale.paid_amount
        invoice.balance = uniform_sale.balance
        
        # Update status
        if uniform_sale.balance == 0:
            invoice.status = 'PAID'
        elif uniform_sale.paid_amount > 0:
            invoice.status = 'PARTIALLY_PAID'
        else:
            invoice.status = 'PENDING'
        
        invoice.save()
        
        logger.info(f"Updated invoice {invoice.invoice_number} for uniform sale {uniform_sale.sale_number}")
        
        return invoice


# =============================================================================
# UNIFORM SALE ACCOUNTING SERVICE
# =============================================================================

class UniformAccountingService:
    """Service to create journal entries for uniform sales"""
    
    @staticmethod
    @transaction.atomic
    def create_journal_entry_for_sale(uniform_sale):
        """
        Create journal entry for uniform sale.
        
        This creates TWO sets of entries:
        1. Revenue recognition (Debit: A/R, Credit: Revenue)
        2. COGS recognition (Debit: COGS, Credit: Inventory)
        
        Args:
            uniform_sale: UniformSale instance
            
        Returns:
            JournalEntry: Created journal entry
        """
        # Validate
        if uniform_sale.journal_entry:
            logger.warning(f"Journal entry already exists for sale {uniform_sale.sale_number}")
            return uniform_sale.journal_entry
        
        if uniform_sale.status in ['DRAFT', 'CANCELLED']:
            raise ValidationError(f"Cannot create journal entry for {uniform_sale.status} sale")
        
        # Ensure accounts are assigned
        uniform_sale.ensure_accounts_assigned()
        
        # Validate required accounts
        if not all([
            uniform_sale.receivable_account,
            uniform_sale.revenue_account,
            uniform_sale.inventory_account,
            uniform_sale.cogs_account
        ]):
            raise ValidationError("All accounting accounts must be assigned before creating journal entry")
        
        # Get or create uniform sales journal
        journal, _ = Journal.objects.get_or_create(
            journal_type='FEES',
            defaults={
                'name': 'Fee Collection Journal',
                'description': 'Journal for fee and uniform sales'
            }
        )
        
        # Create journal entry
        entry = JournalEntry.objects.create(
            journal=journal,
            entry_number=f"JE-{uniform_sale.sale_number}",
            entry_date=uniform_sale.sale_date,
            fiscal_period=uniform_sale.fiscal_period,
            academic_session=uniform_sale.academic_session,
            reference_number=uniform_sale.sale_number,
            description=f"Uniform sale to {uniform_sale.student.get_full_name()} - {uniform_sale.sale_number}",
            status='POSTED'
        )
        
        # =====================================================================
        # ENTRY 1: REVENUE RECOGNITION
        # =====================================================================
        
        # Debit: Accounts Receivable (Asset increases)
        JournalTransaction.objects.create(
            journal_entry=entry,
            account=uniform_sale.receivable_account,
            description=f"Uniform sale - {uniform_sale.student.get_full_name()}",
            amount=uniform_sale.total_amount,
            is_debit=True
        )
        
        # Credit: Uniform Sales Revenue (Revenue increases)
        JournalTransaction.objects.create(
            journal_entry=entry,
            account=uniform_sale.revenue_account,
            description=f"Uniform sales revenue - {uniform_sale.student.get_full_name()}",
            amount=uniform_sale.total_amount,
            is_debit=False
        )
        
        # =====================================================================
        # ENTRY 2: COST OF GOODS SOLD (COGS)
        # =====================================================================
        
        if uniform_sale.total_cost > 0:
            # Debit: Cost of Goods Sold (Expense increases)
            JournalTransaction.objects.create(
                journal_entry=entry,
                account=uniform_sale.cogs_account,
                description=f"COGS - Uniform sale {uniform_sale.sale_number}",
                amount=uniform_sale.total_cost,
                is_debit=True
            )
            
            # Credit: Inventory (Asset decreases)
            JournalTransaction.objects.create(
                journal_entry=entry,
                account=uniform_sale.inventory_account,
                description=f"Inventory reduction - Sale {uniform_sale.sale_number}",
                amount=uniform_sale.total_cost,
                is_debit=False
            )
        
        # Link entry to sale
        uniform_sale.journal_entry = entry
        uniform_sale.save()
        
        logger.info(f"Created journal entry {entry.entry_number} for uniform sale {uniform_sale.sale_number}")
        
        return entry
    
    @staticmethod
    @transaction.atomic
    def create_journal_entry_for_payment(uniform_sale, payment):
        """
        Create journal entry when payment is received for uniform sale.
        
        Entry:
        Debit: Cash/Bank (Asset increases)
        Credit: Accounts Receivable (Asset decreases)
        
        Args:
            uniform_sale: UniformSale instance
            payment: Payment instance
            
        Returns:
            JournalEntry: Created journal entry
        """
        # Get cash/bank account from payment method
        cash_account = FinancialSettings.get_cash_or_bank_account(payment.payment_method)
        if not cash_account:
            raise ValidationError("No cash/bank account configured for payment method")
        
        # Get receivable account
        receivable_account = uniform_sale.receivable_account
        if not receivable_account:
            raise ValidationError("Receivable account not set on uniform sale")
        
        # Get or create journal
        journal, _ = Journal.objects.get_or_create(
            journal_type='CASH',
            defaults={
                'name': 'Cash Journal',
                'description': 'Journal for cash and bank transactions'
            }
        )
        
        # Create journal entry
        entry = JournalEntry.objects.create(
            journal=journal,
            entry_number=f"JE-PMT-{payment.payment_number}",
            entry_date=payment.payment_date,
            fiscal_period=payment.fiscal_period,
            academic_session=payment.academic_session,
            reference_number=payment.payment_number,
            description=f"Payment received for uniform sale {uniform_sale.sale_number}",
            status='POSTED'
        )
        
        # Debit: Cash/Bank (Asset increases)
        JournalTransaction.objects.create(
            journal_entry=entry,
            account=cash_account,
            description=f"Payment received - {uniform_sale.student.get_full_name()}",
            amount=payment.amount,
            is_debit=True
        )
        
        # Credit: Accounts Receivable (Asset decreases)
        JournalTransaction.objects.create(
            journal_entry=entry,
            account=receivable_account,
            description=f"Clear receivable - {uniform_sale.student.get_full_name()}",
            amount=payment.amount,
            is_debit=False
        )
        
        # Link entry to payment
        payment.journal_entry = entry
        payment.save()
        
        logger.info(f"Created journal entry {entry.entry_number} for payment {payment.payment_number}")
        
        return entry
    
    @staticmethod
    @transaction.atomic
    def reverse_journal_entry_for_sale(uniform_sale, reason=""):
        """
        Reverse journal entry for cancelled/returned sale.
        
        Args:
            uniform_sale: UniformSale instance
            reason: Reason for reversal
            
        Returns:
            JournalEntry: Reversal journal entry
        """
        if not uniform_sale.journal_entry:
            logger.warning(f"No journal entry to reverse for sale {uniform_sale.sale_number}")
            return None
        
        original_entry = uniform_sale.journal_entry
        
        if original_entry.status == 'REVERSED':
            logger.warning(f"Journal entry {original_entry.entry_number} already reversed")
            return original_entry
        
        # Get journal
        journal = original_entry.journal
        
        # Create reversal entry
        reversal_entry = JournalEntry.objects.create(
            journal=journal,
            entry_number=f"JE-REV-{uniform_sale.sale_number}",
            entry_date=timezone.now().date(),
            fiscal_period=FiscalPeriod.get_current_fiscal_period(),
            academic_session=uniform_sale.academic_session,
            reference_number=f"REV-{original_entry.reference_number}",
            description=f"REVERSAL: {original_entry.description}",
            status='POSTED',
            original_entry=original_entry,
            reversal_reason=reason or f"Reversal for cancelled/returned sale {uniform_sale.sale_number}"
        )
        
        # Create reversal transactions (swap debits and credits)
        for transaction in original_entry.transactions.all():
            JournalTransaction.objects.create(
                journal_entry=reversal_entry,
                account=transaction.account,
                description=f"REVERSAL: {transaction.description}",
                amount=transaction.amount,
                is_debit=not transaction.is_debit  # Reverse debit/credit
            )
        
        # Mark original as reversed
        original_entry.status = 'REVERSED'
        original_entry.reversed_at = timezone.now()
        original_entry.save()
        
        logger.info(f"Created reversal entry {reversal_entry.entry_number} for sale {uniform_sale.sale_number}")
        
        return reversal_entry


# =============================================================================
# UNIFORM STOCK SERVICE
# =============================================================================

class UniformStockService:
    """Service to manage uniform stock and reservations"""
    
    @staticmethod
    @transaction.atomic
    def reserve_stock_for_sale(uniform_sale):
        """
        Reserve stock for a uniform sale.
        Used for sales in DRAFT or PENDING status.
        
        Args:
            uniform_sale: UniformSale instance
            
        Raises:
            ValidationError: If insufficient stock
        """
        for sale_item in uniform_sale.items.all():
            if sale_item.uniform_item.requires_sizing and sale_item.size:
                # Get or create stock record
                stock, _ = UniformStock.objects.get_or_create(
                    uniform_item=sale_item.uniform_item,
                    size=sale_item.size
                )
                
                # Check availability
                available = stock.available_quantity
                if available < sale_item.quantity:
                    raise ValidationError(
                        f"Insufficient stock for {sale_item.uniform_item.name} "
                        f"Size {sale_item.size.name}. Available: {available}, Requested: {sale_item.quantity}"
                    )
                
                # Reserve stock
                stock.reserved_quantity += sale_item.quantity
                stock.save()
                
                logger.info(
                    f"Reserved {sale_item.quantity} units of {sale_item.uniform_item.name} "
                    f"Size {sale_item.size.name} for sale {uniform_sale.sale_number}"
                )
            else:
                # Non-sized item - check total stock
                item = sale_item.uniform_item
                if item.current_stock < sale_item.quantity:
                    raise ValidationError(
                        f"Insufficient stock for {item.name}. "
                        f"Available: {item.current_stock}, Requested: {sale_item.quantity}"
                    )
    
    @staticmethod
    @transaction.atomic
    def release_reserved_stock(uniform_sale):
        """
        Release reserved stock when sale is cancelled.
        
        Args:
            uniform_sale: UniformSale instance
        """
        for sale_item in uniform_sale.items.all():
            if sale_item.uniform_item.requires_sizing and sale_item.size:
                try:
                    stock = UniformStock.objects.get(
                        uniform_item=sale_item.uniform_item,
                        size=sale_item.size
                    )
                    
                    # Release reservation
                    stock.reserved_quantity = max(0, stock.reserved_quantity - sale_item.quantity)
                    stock.save()
                    
                    logger.info(
                        f"Released {sale_item.quantity} units of {sale_item.uniform_item.name} "
                        f"Size {sale_item.size.name} for cancelled sale {uniform_sale.sale_number}"
                    )
                except UniformStock.DoesNotExist:
                    logger.warning(
                        f"Stock record not found for {sale_item.uniform_item.name} "
                        f"Size {sale_item.size.name}"
                    )
    
    @staticmethod
    @transaction.atomic
    def deduct_stock_for_sale(uniform_sale):
        """
        Deduct actual stock when sale is issued.
        Converts reservations to actual deductions.
        
        Args:
            uniform_sale: UniformSale instance
        """
        for sale_item in uniform_sale.items.all():
            if sale_item.uniform_item.requires_sizing and sale_item.size:
                stock = UniformStock.objects.get(
                    uniform_item=sale_item.uniform_item,
                    size=sale_item.size
                )
                
                # Deduct from quantity
                stock.quantity -= sale_item.quantity
                
                # Release reservation
                stock.reserved_quantity = max(0, stock.reserved_quantity - sale_item.quantity)
                
                stock.save()
                
                logger.info(
                    f"Deducted {sale_item.quantity} units of {sale_item.uniform_item.name} "
                    f"Size {sale_item.size.name} for issued sale {uniform_sale.sale_number}"
                )
            else:
                # Non-sized item
                item = sale_item.uniform_item
                item.current_stock -= sale_item.quantity
                item.save()
                
                logger.info(
                    f"Deducted {sale_item.quantity} units of {item.name} "
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
                    size=sale_item.size
                )
                
                # Add back to quantity
                stock.quantity += sale_item.quantity
                stock.save()
                
                logger.info(
                    f"Restored {sale_item.quantity} units of {sale_item.uniform_item.name} "
                    f"Size {sale_item.size.name} for returned sale {uniform_sale.sale_number}"
                )
            else:
                # Non-sized item
                item = sale_item.uniform_item
                item.current_stock += sale_item.quantity
                item.save()
                
                logger.info(
                    f"Restored {sale_item.quantity} units of {item.name} "
                    f"for returned sale {uniform_sale.sale_number}"
                )


# =============================================================================
# UNIFORM PAYMENT SERVICE
# =============================================================================

class UniformPaymentService:
    """Service to process payments for uniform sales"""
    
    @staticmethod
    @transaction.atomic
    def create_payment_for_sale(uniform_sale, payment_data):
        """
        Create payment for a uniform sale.
        
        Args:
            uniform_sale: UniformSale instance
            payment_data: Dict with payment details:
                - amount: Decimal
                - payment_method: PaymentMethod instance
                - payment_date: date
                - reference_number: str (optional)
                - notes: str (optional)
                
        Returns:
            Payment: Created payment
        """
        # Validate
        if not uniform_sale.fee_invoice:
            raise ValidationError("Cannot create payment without invoice")
        
        amount = payment_data['amount']
        if amount <= 0:
            raise ValidationError("Payment amount must be positive")
        
        if amount > uniform_sale.balance:
            raise ValidationError(
                f"Payment amount ({amount}) exceeds balance ({uniform_sale.balance})"
            )
        
        # Get fiscal period
        fiscal_period = FiscalPeriod.get_current_fiscal_period()
        if not fiscal_period:
            raise ValidationError("No active fiscal period found")
        
        # Get deposit account from payment method
        deposit_account = FinancialSettings.get_cash_or_bank_account(
            payment_data['payment_method']
        )
        if not deposit_account:
            raise ValidationError("No deposit account configured for payment method")
        
        # Create payment
        payment = Payment.objects.create(
            payment_number=f"PMT-{uniform_sale.sale_number}-{Payment.objects.count() + 1}",
            invoice=uniform_sale.fee_invoice,
            student=uniform_sale.student,
            amount=amount,
            amount_applied_to_invoice=amount,
            payment_date=payment_data.get('payment_date', timezone.now().date()),
            payment_method=payment_data['payment_method'],
            reference_number=payment_data.get('reference_number', ''),
            academic_session=uniform_sale.academic_session,
            fiscal_period=fiscal_period,
            deposit_account=deposit_account,
            receivable_account=uniform_sale.receivable_account,
            status='COMPLETED',
            is_verified=True,
            verification_date=timezone.now(),
            receipt_number=f"RCPT-{uniform_sale.sale_number}-{Payment.objects.count() + 1}",
            receipt_issued=True,
            receipt_issued_date=timezone.now(),
            remarks=payment_data.get('notes', ''),
            fee_breakdown={'uniform_sale': uniform_sale.sale_number}
        )
        
        # Update sale amounts
        uniform_sale.paid_amount += amount
        uniform_sale.balance -= amount
        
        # Update status
        if uniform_sale.balance == 0:
            uniform_sale.status = 'PAID'
        elif uniform_sale.paid_amount > 0:
            uniform_sale.status = 'PARTIAL'
        
        uniform_sale.save()
        
        # Update invoice
        invoice = uniform_sale.fee_invoice
        invoice.paid_amount += amount
        invoice.balance -= amount
        
        if invoice.balance == 0:
            invoice.status = 'PAID'
        elif invoice.paid_amount > 0:
            invoice.status = 'PARTIALLY_PAID'
        
        invoice.save()
        
        # Create journal entry for payment
        if uniform_sale.auto_create_journal_entry:
            UniformAccountingService.create_journal_entry_for_payment(uniform_sale, payment)
        
        # Update student account
        UniformPaymentService._update_student_account(uniform_sale, payment)
        
        logger.info(
            f"Created payment {payment.payment_number} for {amount} "
            f"on uniform sale {uniform_sale.sale_number}"
        )
        
        return payment
    
    @staticmethod
    def _update_student_account(uniform_sale, payment):
        """Update student financial account with payment"""
        try:
            # Get or create student account
            student_account, _ = StudentAccount.objects.get_or_create(
                student=uniform_sale.student
            )
            
            # Calculate new balance
            new_balance = student_account.current_balance + payment.amount
            
            # Create transaction record
            AccountTransaction.objects.create(
                student_account=student_account,
                transaction_type='PAYMENT',
                amount=payment.amount,
                description=f"Payment for uniform sale {uniform_sale.sale_number}",
                balance_after=new_balance,
                invoice=uniform_sale.fee_invoice,
                payment=payment,
                academic_session=uniform_sale.academic_session,
                fiscal_period=payment.fiscal_period,
                reference_number=payment.payment_number
            )
            
            # Update account balance
            student_account.current_balance = new_balance
            student_account.total_payments_received += payment.amount
            student_account.last_payment_date = payment.payment_date
            student_account.last_transaction_date = timezone.now()
            student_account.save()
            
            logger.info(
                f"Updated student account for {uniform_sale.student.get_full_name()} "
                f"with payment {payment.payment_number}"
            )
            
        except Exception as e:
            logger.error(f"Error updating student account: {e}")


# =============================================================================
# UNIFORM SALE WORKFLOW SERVICE
# =============================================================================

class UniformSaleWorkflowService:
    """Service to manage uniform sale workflow and state transitions"""
    
    @staticmethod
    @transaction.atomic
    def finalize_sale(uniform_sale, user=None):
        """
        Finalize a uniform sale.
        
        Steps:
        1. Validate sale
        2. Reserve stock
        3. Create invoice
        4. Create journal entry
        5. Update status
        
        Args:
            uniform_sale: UniformSale instance
            user: User performing action (optional)
            
        Returns:
            dict: Results with invoice and journal_entry
        """
        # Validate
        if uniform_sale.status != 'DRAFT':
            raise ValidationError(f"Can only finalize DRAFT sales, current status: {uniform_sale.status}")
        
        if not uniform_sale.items.exists():
            raise ValidationError("Cannot finalize sale without items")
        
        # Recalculate totals
        uniform_sale.calculate_totals()
        
        # Ensure accounts assigned
        uniform_sale.ensure_accounts_assigned()
        
        # Reserve stock
        try:
            UniformStockService.reserve_stock_for_sale(uniform_sale)
        except ValidationError as e:
            raise ValidationError(f"Stock reservation failed: {str(e)}")
        
        # Create invoice (if sale type is SALE)
        invoice = None
        if uniform_sale.sale_type == 'SALE' and uniform_sale.auto_create_invoice:
            try:
                invoice = UniformInvoiceService.create_invoice_from_sale(uniform_sale)
            except Exception as e:
                logger.error(f"Error creating invoice: {e}")
                raise
        
        # Create journal entry
        journal_entry = None
        if uniform_sale.sale_type == 'SALE' and uniform_sale.auto_create_journal_entry:
            try:
                journal_entry = UniformAccountingService.create_journal_entry_for_sale(uniform_sale)
            except Exception as e:
                logger.error(f"Error creating journal entry: {e}")
                raise
        
        # Update status
        uniform_sale.status = 'PENDING' if uniform_sale.balance > 0 else 'PAID'
        uniform_sale.save()
        
        logger.info(f"Finalized uniform sale {uniform_sale.sale_number}")
        
        return {
            'uniform_sale': uniform_sale,
            'invoice': invoice,
            'journal_entry': journal_entry,
        }
    
    @staticmethod
    @transaction.atomic
    def issue_sale(uniform_sale, user=None):
        """
        Issue uniforms to student (mark as issued).
        
        Steps:
        1. Validate payment status
        2. Deduct actual stock
        3. Update status
        
        Args:
            uniform_sale: UniformSale instance
            user: User performing action
            
        Returns:
            UniformSale: Updated sale
        """
        # Validate
        if uniform_sale.status not in ['PAID', 'PARTIAL']:
            raise ValidationError(
                f"Can only issue PAID or PARTIAL sales, current status: {uniform_sale.status}"
            )
        
        # Deduct stock
        try:
            UniformStockService.deduct_stock_for_sale(uniform_sale)
        except Exception as e:
            logger.error(f"Error deducting stock: {e}")
            raise ValidationError(f"Stock deduction failed: {str(e)}")
        
        # Update status
        uniform_sale.status = 'ISSUED'
        uniform_sale.issued_at = timezone.now()
        
        if user:
            uniform_sale.issued_by_id = str(user.id) if hasattr(user, 'id') else str(user.pk)
        
        uniform_sale.save()
        
        logger.info(f"Issued uniform sale {uniform_sale.sale_number}")
        
        return uniform_sale
    
    @staticmethod
    @transaction.atomic
    def cancel_sale(uniform_sale, reason="", user=None):
        """
        Cancel a uniform sale.
        
        Steps:
        1. Validate status
        2. Release reserved stock
        3. Reverse journal entry
        4. Cancel invoice
        5. Update status
        
        Args:
            uniform_sale: UniformSale instance
            reason: Cancellation reason
            user: User performing action
            
        Returns:
            UniformSale: Cancelled sale
        """
        # Validate
        if uniform_sale.status == 'CANCELLED':
            raise ValidationError("Sale is already cancelled")
        
        if uniform_sale.status == 'ISSUED':
            raise ValidationError("Cannot cancel issued sale. Use return instead.")
        
        # Release reserved stock
        UniformStockService.release_reserved_stock(uniform_sale)
        
        # Reverse journal entry if exists
        if uniform_sale.journal_entry:
            UniformAccountingService.reverse_journal_entry_for_sale(
                uniform_sale,
                reason=reason or "Sale cancelled"
            )
        
        # Cancel invoice
        if uniform_sale.fee_invoice:
            invoice = uniform_sale.fee_invoice
            invoice.status = 'CANCELLED'
            invoice.notes += f"\nCANCELLED: {reason}"
            invoice.save()
        
        # Update status
        uniform_sale.status = 'CANCELLED'
        uniform_sale.notes += f"\nCANCELLED: {reason}"
        uniform_sale.save()
        
        logger.info(f"Cancelled uniform sale {uniform_sale.sale_number}")
        
        return uniform_sale
    
    @staticmethod
    @transaction.atomic
    def return_sale(uniform_sale, reason="", user=None):
        """
        Process return of issued uniforms.
        
        Steps:
        1. Validate status
        2. Restore stock
        3. Reverse journal entry
        4. Process refund if needed
        5. Update status
        
        Args:
            uniform_sale: UniformSale instance
            reason: Return reason
            user: User performing action
            
        Returns:
            UniformSale: Returned sale
        """
        # Validate
        if uniform_sale.status != 'ISSUED':
            raise ValidationError(f"Can only return ISSUED sales, current status: {uniform_sale.status}")
        
        # Restore stock
        UniformStockService.restore_stock_for_return(uniform_sale)
        
        # Reverse journal entry
        if uniform_sale.journal_entry:
            UniformAccountingService.reverse_journal_entry_for_sale(
                uniform_sale,
                reason=reason or "Uniforms returned"
            )
        
        # TODO: Process refund if payment was made
        # This would create a Refund record and reverse payment journal entries
        
        # Update status
        uniform_sale.status = 'RETURNED'
        uniform_sale.notes += f"\nRETURNED: {reason}"
        uniform_sale.save()
        
        logger.info(f"Processed return for uniform sale {uniform_sale.sale_number}")
        
        return uniform_sale


# =============================================================================
# UNIFORM SALE BUILDER SERVICE
# =============================================================================

class UniformSaleBuilder:
    """Builder pattern for creating uniform sales with items"""
    
    def __init__(self, student, academic_session, sale_type='SALE'):
        """
        Initialize builder.
        
        Args:
            student: Student instance
            academic_session: AcademicSession instance
            sale_type: Sale type (SALE, ISSUANCE, LOAN, REPLACEMENT)
        """
        self.student = student
        self.academic_session = academic_session
        self.sale_type = sale_type
        self.items = []
        self.discount_amount = Decimal('0.00')
        self.discount_reason = ""
        self.notes = ""
    
    def add_item(self, uniform_item, size=None, quantity=1):
        """
        Add item to sale.
        
        Args:
            uniform_item: UniformItem instance
            size: UniformSize instance (optional)
            quantity: Quantity to sell
            
        Returns:
            self: For method chaining
        """
        # Validate size requirement
        if uniform_item.requires_sizing and not size:
            raise ValidationError(f"{uniform_item.name} requires a size")
        
        # Get pricing
        unit_price = uniform_item.selling_price
        unit_cost = uniform_item.unit_cost
        
        # Get tax rate
        tax_rate = uniform_item.tax_rate
        tax_percentage = Decimal('0.00')
        
        if uniform_item.is_taxable:
            if tax_rate:
                tax_percentage = tax_rate.rate
            else:
                # Use default tax rate
                settings = FinancialSettings.get_instance()
                if settings:
                    tax_percentage = settings.default_tax_rate
        
        self.items.append({
            'uniform_item': uniform_item,
            'size': size,
            'quantity': quantity,
            'unit_price': unit_price,
            'unit_cost': unit_cost,
            'tax_percentage': tax_percentage,
        })
        
        return self
    
    def set_discount(self, amount, reason=""):
        """
        Set discount on entire sale.
        
        Args:
            amount: Discount amount
            reason: Discount reason
            
        Returns:
            self: For method chaining
        """
        self.discount_amount = amount
        self.discount_reason = reason
        return self
    
    def set_notes(self, notes):
        """Set notes"""
        self.notes = notes
        return self
    
    @transaction.atomic
    def build(self):
        """
        Build and save the uniform sale.
        
        Returns:
            UniformSale: Created sale (in DRAFT status)
        """
        if not self.items:
            raise ValidationError("Cannot create sale without items")
        
        # Get fiscal period
        fiscal_period = FiscalPeriod.get_current_fiscal_period()
        if not fiscal_period:
            raise ValidationError("No active fiscal period found")
        
        # Generate sale number
        sale_count = UniformSale.objects.count() + 1
        sale_number = f"US-{timezone.now().year}-{sale_count:05d}"
        
        # Create sale
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
            status='DRAFT'
        )
        
        # Create sale items
        for item_data in self.items:
            UniformSaleItem.objects.create(
                sale=sale,
                uniform_item=item_data['uniform_item'],
                size=item_data['size'],
                quantity=item_data['quantity'],
                unit_price=item_data['unit_price'],
                unit_cost=item_data['unit_cost'],
                tax_percentage=item_data['tax_percentage']
            )
        
        # Calculate totals
        sale.calculate_totals()
        
        logger.info(f"Created uniform sale {sale.sale_number} in DRAFT status")
        
        return sale


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def create_uniform_sale(student, academic_session, items, **kwargs):
    """
    Convenience function to create uniform sale.
    
    Args:
        student: Student instance
        academic_session: AcademicSession instance
        items: List of dicts with 'uniform_item', 'size' (optional), 'quantity'
        **kwargs: Additional sale parameters (discount_amount, notes, etc.)
        
    Returns:
        UniformSale: Created sale in DRAFT status
        
    Example:
        sale = create_uniform_sale(
            student=student,
            academic_session=session,
            items=[
                {'uniform_item': shirt, 'size': size_m, 'quantity': 2},
                {'uniform_item': trousers, 'size': size_32, 'quantity': 1},
            ],
            discount_amount=Decimal('5000.00'),
            notes="Staff child discount"
        )
    """
    builder = UniformSaleBuilder(
        student=student,
        academic_session=academic_session,
        sale_type=kwargs.get('sale_type', 'SALE')
    )
    
    # Add items
    for item_data in items:
        builder.add_item(
            uniform_item=item_data['uniform_item'],
            size=item_data.get('size'),
            quantity=item_data.get('quantity', 1)
        )
    
    # Set discount if provided
    if 'discount_amount' in kwargs:
        builder.set_discount(
            amount=kwargs['discount_amount'],
            reason=kwargs.get('discount_reason', '')
        )
    
    # Set notes if provided
    if 'notes' in kwargs:
        builder.set_notes(kwargs['notes'])
    
    return builder.build()


def finalize_and_issue_sale(uniform_sale, user=None):
    """
    Convenience function to finalize and immediately issue a sale.
    
    Args:
        uniform_sale: UniformSale instance
        user: User performing action
        
    Returns:
        dict: Results with sale, invoice, journal_entry
    """
    # Finalize
    results = UniformSaleWorkflowService.finalize_sale(uniform_sale, user)
    
    # Issue
    issued_sale = UniformSaleWorkflowService.issue_sale(uniform_sale, user)
    
    results['uniform_sale'] = issued_sale
    
    return results