# fees/signals.py - COMPLETE VERSION WITH AUTO-POSTING ON FINALIZATION

"""
Fee Management Signal Handlers

FEATURES:
- Invoice creation and updates with DRAFT workflow
- Auto-posting journal entries when invoice finalized
- Payment processing with journal entries
- Payment reversal handling (internal corrections)
- Payment refund handling (actual money returned)
- Discount and scholarship tracking
- Bad debt write-offs
- Auto-invoice generation
- Audit logging and validation

ACCOUNTING METHOD: Accrual Basis

INVOICE WORKFLOW:
1. Invoice created as DRAFT with DRAFT journal entry
2. Invoice finalized (manually or via payment) → journal auto-posted
3. Payments update invoice status automatically
"""

from django.db.models.signals import pre_save, post_save, post_delete, pre_delete
from django.dispatch import receiver
from django.utils import timezone
from django.core.exceptions import ValidationError
from decimal import Decimal
from django.db.models import Sum
import logging

logger = logging.getLogger(__name__)

from academics.models import StudentClassEnrollment
from boarding.models import BoardingEnrollment

from fees.utils import (
    generate_invoice_number,
    generate_payment_number,
    generate_receipt_number,
    generate_refund_number,
    generate_scholarship_application_number,
)


# =============================================================================
# INVOICE SIGNALS - ACCRUAL ACCOUNTING
# =============================================================================

@receiver(pre_save, sender='fees.FeeInvoice')
def fee_invoice_pre_save(sender, instance, **kwargs):
    """Pre-save processing for fee invoices"""
    if not instance.invoice_number:
        instance.invoice_number = generate_invoice_number()
        logger.info(f"Generated invoice number: {instance.invoice_number}")
    
    if not instance.fiscal_period:
        from core.models import FiscalPeriod
        instance.fiscal_period = FiscalPeriod.get_current_fiscal_period()
        if not instance.fiscal_period:
            logger.warning(f"No active fiscal period found for invoice {instance.invoice_number}")


@receiver(post_save, sender='fees.FeeInvoice')
def fee_invoice_post_save(sender, instance, created, **kwargs):
    """
    Post-save processing for fee invoices.
    
    NOTE: AccountTransaction and JournalEntry creation moved to invoice_generators.py
    This signal now only updates timestamps.
    """
    if kwargs.get('raw', False):
        return
    
    if not created:
        return
    
    logger.info(
        f"Processing new invoice: {instance.invoice_number} - "
        f"Student: {instance.student.get_full_name()} - "
        f"Amount: {instance.total_amount}"
    )
    
    # Update student account timestamp
    try:
        from fees.models import StudentAccount
        
        student_account, account_created = StudentAccount.objects.get_or_create(
            student=instance.student
        )
        
        if account_created:
            logger.info(f"Created new student account for {instance.student.get_full_name()}")
        
        student_account.last_transaction_date = timezone.now()
        student_account.save(update_fields=['last_transaction_date'])
        
        logger.info("[OK] Updated student account timestamp")
    
    except Exception as e:
        logger.error(f"[ERROR] Error updating student account timestamp: {e}", exc_info=True)

@receiver(post_save, sender='fees.FeeInvoice')
def post_journal_entry_when_invoice_finalized(sender, instance, **kwargs):
    """
    Post journal entry when invoice is finalized.
    
    Finalized means invoice status changed from DRAFT to:
    - PENDING (manual finalization by admin)
    - PARTIALLY_PAID (payment made to DRAFT invoice)
    - PAID (full payment made to DRAFT invoice)
    
    This ensures journal entries are posted at the right time regardless
    of whether the invoice was manually approved or payment-triggered.
    
    NOTE: Zero-amount invoices (scholarships/waivers) don't have journal entries.
    """
    if kwargs.get('raw', False):
        return
    
    # ✅ Skip zero-amount invoices (no journal entry by design)
    if instance.total_amount <= Decimal('0.00'):
        logger.debug(
            f"Skipping journal entry posting for zero-amount invoice {instance.invoice_number}"
        )
        return
    
    if not instance.journal_entry:
        # This shouldn't happen for non-zero invoices
        logger.warning(
            f"⚠️ Non-zero invoice {instance.invoice_number} (total: {instance.total_amount}) "
            f"has no journal entry - this may indicate an issue"
        )
        return
    
    if not instance.pk:
        return
    
    # ✅ CRITICAL FIX: Only proceed if journal entry is still DRAFT
    if instance.journal_entry.status != 'DRAFT':
        logger.debug(
            f"Journal entry {instance.journal_entry.entry_number} is already "
            f"{instance.journal_entry.status} - skipping auto-post"
        )
        return
    
    try:
        # Get the old invoice state
        old_invoice = sender.objects.get(pk=instance.pk)
        
        # Define finalized statuses
        finalized_statuses = ['PENDING', 'PARTIALLY_PAID', 'PAID']
        
        # Check if invoice was finalized (DRAFT → finalized status)
        if (old_invoice.status == 'DRAFT' and 
            instance.status in finalized_statuses):
            
            # POST the journal entry
            journal_entry = instance.journal_entry
            journal_entry.status = 'POSTED'
            journal_entry.posted_at = timezone.now()
            journal_entry.save(update_fields=['status', 'posted_at'])
            
            # Determine how it was finalized
            finalization_method = {
                'PENDING': 'manual approval',
                'PARTIALLY_PAID': 'payment received',
                'PAID': 'full payment received'
            }.get(instance.status, 'status change')
            
            logger.info(
                f"✅ Posted journal entry {journal_entry.entry_number} "
                f"for invoice {instance.invoice_number} "
                f"(finalized via {finalization_method}: {old_invoice.status} → {instance.status})"
            )
    
    except sender.DoesNotExist:
        pass
    except Exception as e:
        logger.error(
            f"Error posting journal entry for invoice {instance.invoice_number}: {e}",
            exc_info=True
        )

@receiver(pre_delete, sender='fees.FeeInvoice')
def fee_invoice_pre_delete(sender, instance, **kwargs):
    """
    Clean up related records when invoice is deleted.
    
    Allow deletion if:
    - Invoice is DRAFT (not finalized yet)
    - Invoice is VOID (no financial impact)
    - Invoice is CANCELLED (no financial impact)
    
    Block deletion if:
    - Invoice has payments
    - Journal entry is POSTED
    """
    from finance.models import JournalEntry
    from fees.models import AccountTransaction
    
    logger.info(f"Attempting to delete invoice: {instance.invoice_number}")
    
    # =========================================================================
    # ✅ ALLOW DELETION OF VOID/CANCELLED INVOICES
    # =========================================================================
    if instance.status in ['VOID', 'CANCELLED']:
        logger.info(
            f"Deleting {instance.status} invoice {instance.invoice_number} - "
            f"no financial impact (zero amount or cancelled)"
        )
        
        # Clean up any stray account transactions (shouldn't exist for VOID)
        try:
            deleted_count = AccountTransaction.objects.filter(
                invoice=instance
            ).delete()[0]
            
            if deleted_count > 0:
                logger.warning(
                    f"⚠️ Deleted {deleted_count} AccountTransaction(s) for VOID invoice "
                    f"{instance.invoice_number} (these shouldn't have existed)"
                )
        except Exception as e:
            logger.error(f"Error cleaning up account transactions: {e}")
        
        # VOID invoices shouldn't have journal entries, but check anyway
        if instance.journal_entry_id:
            logger.warning(
                f"⚠️ VOID invoice {instance.invoice_number} has journal entry "
                f"{instance.journal_entry_id} - this is unexpected"
            )
        
        logger.info(f"✅ VOID/CANCELLED invoice deletion allowed")
        return  # ← Allow deletion to proceed
    
    # =========================================================================
    # DRAFT INVOICES - Standard safety checks
    # =========================================================================
    if instance.status != 'DRAFT':
        raise ValidationError(
            f"Cannot delete invoice {instance.invoice_number}: "
            f"Invoice status is {instance.status} (must be DRAFT, VOID, or CANCELLED)\n\n"
            f"Use 'Void' or 'Cancel' status instead of deleting finalized invoices."
        )
    
    # Get fresh journal entry from database (not cached relationship)
    journal_entry_id = instance.journal_entry_id
    journal_entry = None
    
    if journal_entry_id:
        try:
            journal_entry = JournalEntry.objects.get(pk=journal_entry_id)
        except JournalEntry.DoesNotExist:
            # Journal entry was already deleted - this is OK
            logger.info(
                f"Deleting invoice {instance.invoice_number} - "
                f"journal entry was already deleted"
            )
            journal_entry = None
    
    # Check journal entry status (if it still exists)
    if journal_entry and journal_entry.status != 'DRAFT':
        raise ValidationError(
            f"Cannot delete invoice {instance.invoice_number}: "
            f"Journal entry {journal_entry.entry_number} is {journal_entry.status} (must be DRAFT)\n\n"
            f"Use 'Void' or 'Cancel' status instead of deleting finalized invoices."
        )
    
    # Check payments
    if instance.paid_amount > 0:
        raise ValidationError(
            f"Cannot delete invoice {instance.invoice_number}: "
            f"Invoice has payments totaling {instance.paid_amount}"
        )
    
    logger.info(f"✓ Safety checks passed - proceeding with deletion of DRAFT invoice {instance.invoice_number}")
    
    # =========================================================================
    # STEP 1: Delete AccountTransactions FIRST (before journal entry)
    # =========================================================================
    try:
        # Delete ALL AccountTransactions related to this invoice
        deleted_count = AccountTransaction.objects.filter(
            invoice=instance
        ).delete()[0]
        
        if deleted_count > 0:
            logger.info(f"✓ Deleted {deleted_count} AccountTransaction(s) for invoice {instance.invoice_number}")
        
        # Also update student account timestamp
        if instance.student:
            from fees.models import StudentAccount
            student_account, _ = StudentAccount.objects.get_or_create(
                student=instance.student
            )
            student_account.last_transaction_date = timezone.now()
            student_account.save(update_fields=['last_transaction_date'])
            logger.info(f"✓ Updated student account timestamp")
    
    except Exception as e:
        logger.error(f"✗ Error deleting AccountTransactions: {e}", exc_info=True)
        # Don't raise - continue with deletion
    
    # =========================================================================
    # STEP 2: Delete journal entry if it still exists and is DRAFT
    # =========================================================================
    if journal_entry and journal_entry.status == 'DRAFT':
        try:
            entry_number = journal_entry.entry_number
            journal_entry.delete()
            logger.info(f"✓ Deleted DRAFT journal entry {entry_number}")
        except Exception as e:
            logger.error(f"✗ Error deleting journal entry: {e}", exc_info=True)
            # Don't raise - continue with deletion
    elif journal_entry:
        logger.warning(
            f"⚠️ Journal entry {journal_entry.entry_number} is {journal_entry.status} "
            f"- skipping deletion (should have been caught earlier)"
        )
    
    logger.info(f"✅ Pre-delete cleanup completed for invoice {instance.invoice_number}")

# =============================================================================
# PAYMENT PRE-SAVE SIGNALS
# =============================================================================

@receiver(pre_save, sender='fees.Payment')
def payment_pre_save(sender, instance, **kwargs):
    """
    Pre-save processing for payments.
    Handles reversal and refund detection.
    """
    # Generate payment number if needed
    if not instance.payment_number:
        instance.payment_number = generate_payment_number()
        logger.info(f"Generated payment number: {instance.payment_number}")
    
    # Generate receipt number if needed
    if not instance.receipt_number and instance.receipt_issued:
        instance.receipt_number = generate_receipt_number()
        logger.info(f"Generated receipt number: {instance.receipt_number}")
    
    # Set fiscal period if not set
    if not instance.fiscal_period:
        from core.models import FiscalPeriod
        instance.fiscal_period = FiscalPeriod.get_current_fiscal_period()
        if not instance.fiscal_period:
            logger.warning(f"No active fiscal period found for payment {instance.payment_number}")
    
    # Set receipt issued date
    if instance.receipt_issued and not instance.receipt_issued_date:
        from core.utils import get_school_current_time
        instance.receipt_issued_date = get_school_current_time()
    
    # Detect if payment is being reversed or refunded
    if instance.pk:
        try:
            from fees.models import Payment
            old_payment = Payment.objects.get(pk=instance.pk)
            
            # Store old state for comparison in post_save
            instance._old_reversed = old_payment.reversed
            instance._old_refunded = old_payment.refunded
            
        except Payment.DoesNotExist:
            instance._old_reversed = False
            instance._old_refunded = False
    else:
        instance._old_reversed = False
        instance._old_refunded = False


# =============================================================================
# PAYMENT POST-SAVE SIGNAL - HANDLES NEW PAYMENTS, REVERSALS, AND REFUNDS
# =============================================================================

@receiver(post_save, sender='fees.Payment')
def payment_post_save(sender, instance, created, **kwargs):
    """
    Post-save processing for payments.
    
    Handles:
    1. New payment creation (journal entry)
    2. Payment reversals (create reversal journal entry)
    3. Payment refunds (create refund journal entry)
    """
    if kwargs.get('raw', False):
        return
    
    # Check if payment was just reversed
    was_just_reversed = (
        hasattr(instance, '_old_reversed') and 
        not instance._old_reversed and 
        instance.reversed
    )
    
    # Check if payment was just refunded
    was_just_refunded = (
        hasattr(instance, '_old_refunded') and 
        not instance._old_refunded and 
        instance.refunded
    )
    
    # Handle reversal
    if was_just_reversed:
        _handle_payment_reversal(instance)
        return
    
    # Handle refund
    if was_just_refunded:
        _handle_payment_refund(instance)
        return
    
    # Skip inactive payments (already reversed or refunded)
    if not instance.is_active:
        logger.info(f"Skipping inactive payment {instance.payment_number}")
        return
    
    # Skip if payment already has journal entry (prevent duplicates)
    if instance.journal_entry:
        logger.info(
            f"Payment {instance.payment_number} already has journal entry "
            f"{instance.journal_entry.entry_number} - skipping journal creation"
        )
        # Still update invoice and student account
        _update_invoice_balance(instance)
        _update_student_account_for_payment(instance)
        return
    
    # Handle new payment
    if created:
        logger.info(
            f"Processing new payment: {instance.payment_number} - "
            f"Student: {instance.student.get_full_name()} - "
            f"Amount: {instance.amount:,.2f}"
        )
        
        _update_invoice_balance(instance)
        _update_student_account_for_payment(instance)
        _create_payment_journal_entry(instance)


# =============================================================================
# PAYMENT REVERSAL HANDLER
# =============================================================================

def _handle_payment_reversal(payment):
    """
    Handle payment reversal (internal correction, no money returned).
    
    Creates:
    - Reversal journal entry
    - Negative AccountTransaction
    - Updates invoice balance
    """
    from fees.models import StudentAccount, AccountTransaction
    from finance.models import JournalEntry, JournalTransaction, Journal
    from finance.utils import generate_journal_entry_number
    from core.models import FiscalPeriod
    
    logger.info(f"Processing reversal for payment {payment.payment_number}")
    
    try:
        # 1. Update invoice balance
        if payment.invoice:
            invoice = payment.invoice
            invoice.paid_amount -= payment.amount_applied_to_invoice
            invoice.balance = invoice.total_amount - invoice.paid_amount
            
            if invoice.balance >= invoice.total_amount:
                invoice.status = 'PENDING'
            elif invoice.paid_amount > 0:
                invoice.status = 'PARTIALLY_PAID'
            
            invoice.save(update_fields=['paid_amount', 'balance', 'status'])
            logger.info(f"[OK] Updated invoice {invoice.invoice_number}")
        
        # 2. Create negative AccountTransaction
        student_account, _ = StudentAccount.objects.get_or_create(
            student=payment.student
        )
        
        new_balance = student_account.get_current_balance() - payment.amount
        
        AccountTransaction.objects.create(
            student_account=student_account,
            transaction_type='ADJUSTMENT',
            amount=-payment.amount,
            description=f"Reversal of payment {payment.payment_number}: {payment.reversal_reason}",
            balance_after=new_balance,
            invoice=payment.invoice,
            payment=payment,
            academic_session=payment.academic_session,
            fiscal_period=payment.fiscal_period,
            reference_number=f"REV-{payment.payment_number}",
        )
        
        student_account.last_transaction_date = timezone.now()
        student_account.save(update_fields=['last_transaction_date'])
        
        logger.info(f"[OK] Created reversal transaction")
        
        # 3. Create reversal journal entry
        # ✅ FIX: Get accounts properly
        receivable_account = payment.get_receivable_account()
        cash_account = payment.get_deposit_account()  # ✅ Use payment's method
        
        if not receivable_account:
            logger.error("[ERROR] Student receivables account not configured")
            return
            
        if not cash_account:
            logger.error("[ERROR] Cash/Bank account not found for payment method")
            return
        
        fees_journal, _ = Journal.objects.get_or_create(
            journal_type='FEES',
            defaults={
                'name': 'Fee Collections',
                'description': 'Journal for recording student fee payments',
                'is_active': True
            }
        )
        
        # Generate entry number
        entry_number = generate_journal_entry_number(fees_journal)
        
        reversal_entry = JournalEntry.objects.create(
            journal=fees_journal,
            entry_number=entry_number,
            entry_date=timezone.now().date(),
            fiscal_period=FiscalPeriod.get_current_fiscal_period() or payment.fiscal_period,
            academic_session=payment.academic_session,
            description=f"Payment reversal - {payment.student.get_full_name()}: {payment.reversal_reason}",
            reference_number=f"REV-{payment.payment_number}",
            status='POSTED',
        )
        
        # DR: Accounts Receivable (restore debt)
        JournalTransaction.objects.create(
            journal_entry=reversal_entry,
            account=receivable_account,
            amount=payment.amount,
            is_debit=True,
            description=f"Reversal of payment {payment.payment_number}",
        )
        
        # CR: Cash/Bank (correct cash record)
        JournalTransaction.objects.create(
            journal_entry=reversal_entry,
            account=cash_account,
            amount=payment.amount,
            is_debit=False,
            description=f"Payment reversal - internal correction",
        )
        
        # Link reversal journal entry using update() to avoid signal loop
        from fees.models import Payment
        Payment.objects.filter(pk=payment.pk).update(
            reversal_journal_entry=reversal_entry
        )
        
        logger.info(f"[OK] Created reversal journal entry {reversal_entry.entry_number}")
    
    except Exception as e:
        logger.error(f"[ERROR] Error handling payment reversal: {e}", exc_info=True)


# =============================================================================
# PAYMENT REFUND HANDLER
# =============================================================================

def _handle_payment_refund(payment):
    """Handle payment refund (actual money returned to payer)."""
    from fees.models import StudentAccount, AccountTransaction
    from finance.models import JournalEntry, JournalTransaction, Journal
    from finance.utils import generate_journal_entry_number
    from core.models import FiscalPeriod, FinancialSettings
    
    logger.info(f"Processing refund for payment {payment.payment_number}")
    
    try:
        # 1. Update invoice balance
        if payment.invoice:
            invoice = payment.invoice
            invoice.paid_amount -= payment.amount_applied_to_invoice
            invoice.balance = invoice.total_amount - invoice.paid_amount
            
            if invoice.balance >= invoice.total_amount:
                invoice.status = 'PENDING'
            elif invoice.paid_amount > 0:
                invoice.status = 'PARTIALLY_PAID'
            
            invoice.save(update_fields=['paid_amount', 'balance', 'status'])
            logger.info(f"[OK] Updated invoice {invoice.invoice_number}")
        
        # 2. Create negative AccountTransaction
        student_account, _ = StudentAccount.objects.get_or_create(
            student=payment.student
        )
        
        new_balance = student_account.get_current_balance() - payment.amount
        
        AccountTransaction.objects.create(
            student_account=student_account,
            transaction_type='REFUND',
            amount=-payment.amount,
            description=f"Refund of payment {payment.payment_number}: {payment.refund_notes}",
            balance_after=new_balance,
            invoice=payment.invoice,
            payment=payment,
            academic_session=payment.academic_session,
            fiscal_period=payment.fiscal_period,
            reference_number=payment.refund_reference or f"REF-{payment.payment_number}",
        )
        
        student_account.last_transaction_date = timezone.now()
        student_account.save(update_fields=['last_transaction_date'])
        
        logger.info(f"[OK] Created refund transaction")
        
        # 3. Create refund journal entry
        settings = FinancialSettings.get_instance()
        if not settings:
            logger.error("[ERROR] FinancialSettings not configured")
            return
        
        # ✅ FIX: Get accounts properly
        receivable_account = payment.get_receivable_account()
        cash_account = payment.get_deposit_account()  # ✅ Use payment's method
        
        special_mappings = settings.get_special_mappings()
        credit_balance_account = special_mappings.student_credit_balance_account
        
        if not receivable_account or not cash_account:
            logger.error("[ERROR] Required accounts not found for refund")
            return
        
        # Check if student had credit balance before refund
        had_credit_balance = (student_account.get_current_balance() + payment.amount) > 0
        
        fees_journal, _ = Journal.objects.get_or_create(
            journal_type='FEES',
            defaults={
                'name': 'Fee Collections',
                'description': 'Journal for recording student fee payments',
                'is_active': True
            }
        )
        
        entry_number = generate_journal_entry_number(fees_journal)
        
        refund_entry = JournalEntry.objects.create(
            journal=fees_journal,
            entry_number=entry_number,
            entry_date=timezone.now().date(),
            fiscal_period=FiscalPeriod.get_current_fiscal_period() or payment.fiscal_period,
            academic_session=payment.academic_session,
            description=f"Payment refund - {payment.student.get_full_name()}: {payment.refund_notes}",
            reference_number=payment.refund_reference or f"REF-{payment.payment_number}",
            status='POSTED',
        )
        
        if had_credit_balance and credit_balance_account:
            # DR: Student Credit Balance (reduce credit)
            JournalTransaction.objects.create(
                journal_entry=refund_entry,
                account=credit_balance_account,
                amount=payment.amount,
                is_debit=True,
                description=f"Refund from credit balance",
            )
            logger.info(f"[OK] Refund from credit balance")
        else:
            # DR: Accounts Receivable (create new debt)
            JournalTransaction.objects.create(
                journal_entry=refund_entry,
                account=receivable_account,
                amount=payment.amount,
                is_debit=True,
                description=f"Refund creates receivable",
            )
            logger.info(f"[OK] Refund creates receivable")
        
        # CR: Cash/Bank (money going out)
        JournalTransaction.objects.create(
            journal_entry=refund_entry,
            account=cash_account,
            amount=payment.amount,
            is_debit=False,
            description=f"Refund to {payment.student.get_full_name()} via {payment.refund_method}",
        )
        
        # Link refund journal entry using update() to avoid signal loop
        from fees.models import Payment
        Payment.objects.filter(pk=payment.pk).update(
            refund_journal_entry=refund_entry
        )
        
        logger.info(f"[OK] Created refund journal entry {refund_entry.entry_number}")
    
    except Exception as e:
        logger.error(f"[ERROR] Error handling payment refund: {e}", exc_info=True)


# =============================================================================
# PAYMENT HELPER FUNCTIONS
# =============================================================================

def _update_invoice_balance(payment):
    """Update invoice balance based on active payments"""
    if not payment.invoice:
        return
    
    try:
        invoice = payment.invoice
        
        # Recalculate total paid from ALL active completed payments
        total_paid = invoice.payments.filter(
            status='COMPLETED',
            reversed=False,
            refunded=False
        ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
        
        # Update invoice fields
        invoice.paid_amount = total_paid
        invoice.balance = invoice.total_amount - invoice.paid_amount
        
        # Update status
        if invoice.balance <= Decimal('0.00'):
            invoice.status = 'PAID'
        elif invoice.paid_amount > Decimal('0.00'):
            invoice.status = 'PARTIALLY_PAID'
        else:
            invoice.status = 'PENDING'
        
        invoice.save(update_fields=['paid_amount', 'balance', 'status'])
        
        logger.info(
            f"✓ Updated invoice {invoice.invoice_number} - "
            f"Paid: {invoice.paid_amount:,.2f}, Balance: {invoice.balance:,.2f}, "
            f"Status: {invoice.status}"
        )
    
    except Exception as e:
        logger.error(f"✗ Error updating invoice balance: {e}", exc_info=True)


def _update_student_account_for_payment(payment):
    """Update student account with payment transaction"""
    try:
        from fees.models import StudentAccount, AccountTransaction
        from core.utils import get_school_current_time
        
        student_account, _ = StudentAccount.objects.get_or_create(
            student=payment.student
        )
        
        # Get current balance
        current_balance = student_account.get_current_balance()
        
        # Calculate new balance after this payment
        new_balance = current_balance + payment.amount
        
        # Create transaction record
        AccountTransaction.objects.create(
            student_account=student_account,
            transaction_type='PAYMENT',
            amount=payment.amount,
            description=f"Payment {payment.payment_number}",
            balance_after=new_balance,
            invoice=payment.invoice,
            payment=payment,
            academic_session=payment.academic_session,
            fiscal_period=payment.fiscal_period,
            reference_number=payment.payment_number
        )
        
        # Update timestamp fields
        student_account.last_payment_date = get_school_current_time()
        student_account.last_transaction_date = get_school_current_time()
        student_account.save(update_fields=['last_payment_date', 'last_transaction_date'])
        
        logger.info(f"✓ Updated student account - New balance: {new_balance:,.2f}")
    
    except Exception as e:
        logger.error(f"✗ Error updating student account: {e}", exc_info=True)


def _create_payment_journal_entry(payment):
    """Create journal entry for new payment"""
    try:
        from finance.models import Journal, JournalEntry, JournalTransaction
        from core.models import FinancialSettings
        
        settings = FinancialSettings.get_instance()
        if not settings:
            logger.error("✗ FinancialSettings not found")
            return
        
        core_mappings = settings.get_account_mappings()
        special_mappings = settings.get_special_mappings()
        
        # Get required accounts
        cash_account = core_mappings.get_cash_or_bank_account(payment.payment_method)
        receivable_account = core_mappings.student_receivables_account
        unearned_revenue_account = special_mappings.unearned_revenue_account
        credit_balance_account = special_mappings.student_credit_balance_account
        
        if not cash_account or not receivable_account:
            logger.error("✗ Required accounts not configured")
            return
        
        # Get or create FEES journal
        fees_journal, _ = Journal.objects.get_or_create(
            journal_type='FEES',
            defaults={
                'name': 'Fee Collections',
                'description': 'Journal for recording student fee payments',
                'is_active': True
            }
        )
        
        # Get student account
        from fees.models import StudentAccount
        student_account, _ = StudentAccount.objects.get_or_create(student=payment.student)
        
        # Calculate outstanding balance BEFORE this payment
        current_balance = student_account.get_current_balance()
        balance_before_payment = current_balance - payment.amount
        outstanding_before_payment = abs(balance_before_payment) if balance_before_payment < 0 else Decimal('0.00')
        
        # Scenario A: Payment against invoice with outstanding balance
        if payment.invoice and outstanding_before_payment > 0:
            amount_to_receivable = min(payment.amount, outstanding_before_payment)
            overpayment_amount = payment.amount - amount_to_receivable
            
            logger.info(
                f"Payment scenario: Against invoice | "
                f"Amount: {payment.amount:,.2f} | "
                f"To A/R: {amount_to_receivable:,.2f} | "
                f"Overpayment: {overpayment_amount:,.2f}"
            )
            
            journal_entry = JournalEntry.objects.create(
                journal=fees_journal,
                entry_date=payment.payment_date,
                fiscal_period=payment.fiscal_period,
                academic_session=payment.academic_session,
                description=f"Payment received - {payment.student.get_full_name()}",
                reference_number=payment.payment_number,
                status='POSTED',
            )
            
            # DR: Cash/Bank
            JournalTransaction.objects.create(
                journal_entry=journal_entry,
                account=cash_account,
                amount=payment.amount,
                is_debit=True,
                description=f"Payment from {payment.student.get_full_name()}",
            )
            
            # CR: Accounts Receivable
            if amount_to_receivable > 0:
                JournalTransaction.objects.create(
                    journal_entry=journal_entry,
                    account=receivable_account,
                    amount=amount_to_receivable,
                    is_debit=False,
                    description=f"Payment against invoice {payment.invoice.invoice_number}",
                )
            
            # CR: Student Credit Balance
            if overpayment_amount > 0 and credit_balance_account:
                JournalTransaction.objects.create(
                    journal_entry=journal_entry,
                    account=credit_balance_account,
                    amount=overpayment_amount,
                    is_debit=False,
                    description=f"Student overpayment - credit balance",
                )
        
        # Scenario B: Advance payment (no invoice)
        elif not payment.invoice and unearned_revenue_account:
            logger.info(f"Payment scenario: Advance payment | Amount: {payment.amount:,.2f}")
            
            journal_entry = JournalEntry.objects.create(
                journal=fees_journal,
                entry_date=payment.payment_date,
                fiscal_period=payment.fiscal_period,
                academic_session=payment.academic_session,
                description=f"Advance payment - {payment.student.get_full_name()}",
                reference_number=payment.payment_number,
                status='POSTED',
            )
            
            # DR: Cash/Bank
            JournalTransaction.objects.create(
                journal_entry=journal_entry,
                account=cash_account,
                amount=payment.amount,
                is_debit=True,
                description=f"Advance payment from {payment.student.get_full_name()}",
            )
            
            # CR: Unearned Revenue
            JournalTransaction.objects.create(
                journal_entry=journal_entry,
                account=unearned_revenue_account,
                amount=payment.amount,
                is_debit=False,
                description=f"Advance payment - unearned revenue",
            )
        
        # Scenario C: Standard payment (fallback)
        else:
            logger.info(f"Payment scenario: Standard payment | Amount: {payment.amount:,.2f}")
            
            journal_entry = JournalEntry.objects.create(
                journal=fees_journal,
                entry_date=payment.payment_date,
                fiscal_period=payment.fiscal_period,
                academic_session=payment.academic_session,
                description=f"Payment received - {payment.student.get_full_name()}",
                reference_number=payment.payment_number,
                status='POSTED',
            )
            
            # DR: Cash/Bank
            JournalTransaction.objects.create(
                journal_entry=journal_entry,
                account=cash_account,
                amount=payment.amount,
                is_debit=True,
                description=f"Payment from {payment.student.get_full_name()}",
            )
            
            # CR: Accounts Receivable
            JournalTransaction.objects.create(
                journal_entry=journal_entry,
                account=receivable_account,
                amount=payment.amount,
                is_debit=False,
                description=f"Payment against fees",
            )
        
        # Link journal entry using update() to avoid signal loop
        from fees.models import Payment
        Payment.objects.filter(pk=payment.pk).update(journal_entry=journal_entry)
        
        logger.info(f"✓ Created journal entry {journal_entry.entry_number}")
    
    except Exception as e:
        logger.error(f"✗ Error creating payment journal entry: {e}", exc_info=True)


# =============================================================================
# PAYMENT DELETE SIGNAL
# =============================================================================

@receiver(pre_delete, sender='fees.Payment')
def payment_pre_delete(sender, instance, **kwargs):
    """
    Validate payment deletion is safe.
    
    Allow deletion if:
    - Payment is REVERSED or REFUNDED (inactive payments)
    - Payment is unverified and has no journal entry
    
    Block deletion if:
    - Payment is COMPLETED and verified
    - Fiscal period is closed
    """
    from django.core.exceptions import ValidationError
    
    logger.info(f"Pre-delete check for payment {instance.payment_number}")
    
    # Allow deletion of reversed/refunded payments
    if instance.reversed or instance.refunded:
        logger.info(
            f"[OK] Allowing deletion of {'reversed' if instance.reversed else 'refunded'} "
            f"payment {instance.payment_number}"
        )
        return  # Allow deletion
    
    # Allow deletion of unverified payments without journal entries
    if not instance.is_verified and not instance.journal_entry_id:
        logger.info(f"[OK] Allowing deletion of unverified payment {instance.payment_number}")
        return
    
    # Check fiscal period
    if instance.fiscal_period and hasattr(instance.fiscal_period, 'is_closed'):
        if instance.fiscal_period.is_closed:
            raise ValidationError(
                f"Cannot delete payment {instance.payment_number}: "
                f"Fiscal period {instance.fiscal_period.name} is closed"
            )
    
    # Block deletion of verified/completed active payments
    if instance.is_verified or instance.status == 'COMPLETED':
        raise ValidationError(
            f"Cannot delete payment {instance.payment_number}: "
            f"Payment is {instance.status} and verified. "
            f"Use 'Reverse Payment' instead to maintain audit trail."
        )
    
    logger.info(f"[OK] Payment {instance.payment_number} can be safely deleted")


@receiver(post_delete, sender='fees.Payment')
def payment_post_delete(sender, instance, **kwargs):
    """
    Handle payment deletion with COMPLETE cleanup.
    
    When a payment is deleted:
    1. Update invoice balance
    2. Delete AccountTransaction
    3. DELETE journal entries (after changing to DRAFT status)
    4. Update student account timestamp
    """
    logger.info(f"Processing deletion of payment {instance.payment_number}")
    
    # =====================================================================
    # STEP 1: UPDATE INVOICE BALANCE
    # =====================================================================
    invoice_id = instance.invoice_id
    if invoice_id:
        try:
            from fees.models import FeeInvoice
            invoice = FeeInvoice.objects.get(pk=invoice_id)
            
            # Recalculate total paid from remaining active payments
            from django.db.models import Sum
            total_paid = invoice.payments.filter(
                status='COMPLETED',
                reversed=False,
                refunded=False
            ).exclude(pk=instance.pk).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
            
            # Update invoice
            invoice.paid_amount = total_paid
            invoice.balance = invoice.total_amount - invoice.paid_amount
            
            # Update status
            if invoice.balance <= Decimal('0.00'):
                invoice.status = 'PAID'
            elif invoice.paid_amount > Decimal('0.00'):
                invoice.status = 'PARTIALLY_PAID'
            else:
                invoice.status = 'PENDING'
            
            invoice.save(update_fields=['paid_amount', 'balance', 'status'])
            
            logger.info(
                f"[OK] Updated invoice {invoice.invoice_number} after payment deletion - "
                f"Paid: {invoice.paid_amount:,.2f}, Balance: {invoice.balance:,.2f}"
            )
        
        except Exception as e:
            logger.error(f"[ERROR] Error updating invoice after payment deletion: {e}", exc_info=True)
    
    # =====================================================================
    # STEP 2: DELETE ACCOUNTTRANSACTION
    # =====================================================================
    try:
        from fees.models import AccountTransaction
        
        deleted_count = AccountTransaction.objects.filter(
            payment=instance
        ).delete()[0]
        
        if deleted_count > 0:
            logger.info(f"[OK] Deleted {deleted_count} AccountTransaction(s) for payment {instance.payment_number}")
        else:
            logger.warning(f"[WARNING] No AccountTransaction found for payment {instance.payment_number}")
    
    except Exception as e:
        logger.error(f"[ERROR] Error deleting AccountTransaction: {e}", exc_info=True)
    
    # =====================================================================
    # STEP 3: DELETE JOURNAL ENTRIES (Change to DRAFT first)
    # =====================================================================
    
    # Use _id fields to avoid querying deleted relationships
    journal_entry_ids = {
        'journal_entry': instance.journal_entry_id,
        'reversal_journal_entry': instance.reversal_journal_entry_id,
        'refund_journal_entry': instance.refund_journal_entry_id,
    }
    
    from finance.models import JournalEntry
    
    for entry_name, entry_id in journal_entry_ids.items():
        if entry_id:
            try:
                # Get journal entry by ID (avoids relationship access in broken transaction)
                journal_entry = JournalEntry.objects.get(pk=entry_id)
                entry_number = journal_entry.entry_number
                
                # Check if fiscal period is closed
                if journal_entry.fiscal_period and hasattr(journal_entry.fiscal_period, 'is_closed'):
                    if journal_entry.fiscal_period.is_closed:
                        logger.error(
                            f"[ERROR] Cannot delete journal entry {entry_number}: "
                            f"Fiscal period {journal_entry.fiscal_period.name} is CLOSED"
                        )
                        continue
                
                # CRITICAL FIX: Change status to DRAFT before deleting
                # This allows the journal entry to be deleted without validation errors
                if journal_entry.status == 'POSTED':
                    journal_entry.status = 'DRAFT'
                    journal_entry.save(update_fields=['status'])
                    logger.info(f"[OK] Changed {entry_number} status to DRAFT")
                
                # Now delete it (won't be blocked by finance signal)
                journal_entry.delete()
                logger.info(f"[OK] Deleted journal entry {entry_number} ({entry_name})")
            
            except JournalEntry.DoesNotExist:
                logger.warning(f"[WARNING] Journal entry {entry_id} not found (already deleted)")
            except Exception as e:
                logger.error(f"[ERROR] Error deleting {entry_name}: {e}", exc_info=True)
    
    # =====================================================================
    # STEP 4: UPDATE STUDENT ACCOUNT TIMESTAMP
    # =====================================================================
    try:
        from fees.models import StudentAccount
        
        student_account, _ = StudentAccount.objects.get_or_create(
            student=instance.student
        )
        
        student_account.last_transaction_date = timezone.now()
        student_account.save(update_fields=['last_transaction_date'])
        
        logger.info(f"[OK] Updated student account timestamp after payment deletion")
    
    except Exception as e:
        logger.error(f"[ERROR] Error updating student account: {e}", exc_info=True)
    
    logger.info(f"[SUCCESS] Completed payment deletion cleanup for {instance.payment_number}")

# =============================================================================
# REFUND SIGNALS (for Refund model, not Payment.refunded)
# =============================================================================

@receiver(pre_save, sender='fees.Refund')
def refund_pre_save(sender, instance, **kwargs):
    """Pre-save processing for refunds"""
    if not instance.refund_number:
        instance.refund_number = generate_refund_number()
        logger.info(f"Generated refund number: {instance.refund_number}")
    
    if not instance.fiscal_period:
        from core.models import FiscalPeriod
        instance.fiscal_period = FiscalPeriod.get_current_fiscal_period()


@receiver(post_save, sender='fees.Refund')
def refund_post_save(sender, instance, created, **kwargs):
    """Post-save processing for refunds (Refund model)"""
    if kwargs.get('raw', False):
        return
    
    if not created:
        return
    
    logger.info(
        f"Processing new refund: {instance.refund_number} - "
        f"Student: {instance.student.get_full_name()} - "
        f"Amount: {instance.amount}"
    )
    
    # Update invoice balance
    if instance.invoice:
        try:
            invoice = instance.invoice
            invoice.paid_amount -= instance.amount
            invoice.balance = invoice.total_amount - invoice.paid_amount
            
            if invoice.balance <= 0:
                invoice.status = 'PAID'
            elif invoice.paid_amount > 0:
                invoice.status = 'PARTIALLY_PAID'
            else:
                invoice.status = 'PENDING'
            
            invoice.save(update_fields=['paid_amount', 'balance', 'status'])
            logger.info(f"✓ Updated invoice after refund")
        except Exception as e:
            logger.error(f"✗ Error updating invoice: {e}", exc_info=True)
    
    # Update student account
    try:
        from fees.models import StudentAccount, AccountTransaction
        
        student_account, _ = StudentAccount.objects.get_or_create(student=instance.student)
        
        transaction_amount = -instance.amount
        new_balance = student_account.get_current_balance() + transaction_amount
        
        AccountTransaction.objects.create(
            student_account=student_account,
            transaction_type='REFUND',
            amount=transaction_amount,
            description=f"Refund {instance.refund_number}",
            balance_after=new_balance,
            invoice=instance.invoice,
            academic_session=instance.academic_session,
            fiscal_period=instance.fiscal_period,
            reference_number=instance.refund_number
        )
        
        student_account.last_transaction_date = timezone.now()
        student_account.save(update_fields=['last_transaction_date'])
        
        logger.info(f"✓ Updated student account for refund")
    except Exception as e:
        logger.error(f"✗ Error updating student account: {e}", exc_info=True)
    
    # Create journal entry
    try:
        from finance.models import JournalEntry, JournalTransaction, Journal
        from core.models import FinancialSettings
        
        settings = FinancialSettings.get_instance()
        if not settings:
            return
        
        core_mappings = settings.get_account_mappings()
        special_mappings = settings.get_special_mappings()
        
        cash_account = core_mappings.get_cash_or_bank_account(instance.payment_method)
        receivable_account = core_mappings.student_receivables_account
        credit_balance_account = special_mappings.student_credit_balance_account
        
        if not cash_account or not receivable_account:
            logger.error("✗ Required accounts not configured")
            return
        
        student_account, _ = StudentAccount.objects.get_or_create(student=instance.student)
        had_credit_balance = (student_account.get_current_balance() + instance.amount) > 0
        
        fees_journal, _ = Journal.objects.get_or_create(
            journal_type='FEES',
            defaults={'name': 'Fee Collections'}
        )
        
        journal_entry = JournalEntry.objects.create(
            journal=fees_journal,
            entry_date=instance.requested_date,
            fiscal_period=instance.fiscal_period,
            description=f"Refund issued - {instance.student.get_full_name()}",
            reference_number=instance.refund_number,
            status='POSTED',
        )
        
        if had_credit_balance and credit_balance_account:
            # Refunding from credit balance
            JournalTransaction.objects.create(
                journal_entry=journal_entry,
                account=credit_balance_account,
                amount=instance.amount,
                is_debit=True,
                description=f"Refund from credit balance",
            )
        else:
            # Creating new receivable
            JournalTransaction.objects.create(
                journal_entry=journal_entry,
                account=receivable_account,
                amount=instance.amount,
                is_debit=True,
                description=f"Refund reversal",
            )
        
        # CR: Cash/Bank
        JournalTransaction.objects.create(
            journal_entry=journal_entry,
            account=cash_account,
            amount=instance.amount,
            is_debit=False,
            description=f"Refund to {instance.student.get_full_name()}",
        )
        
        # Link using save (not update since this is Refund model)
        instance.journal_entry = journal_entry
        instance.save(update_fields=['journal_entry'])
        
        logger.info(f"✓ Created refund journal entry")
    except Exception as e:
        logger.error(f"✗ Error creating refund journal entry: {e}", exc_info=True)


# =============================================================================
# DISCOUNT/SCHOLARSHIP SIGNALS
# =============================================================================

@receiver(post_save, sender='fees.DiscountApplication')
def discount_application_post_save(sender, instance, created, **kwargs):
    """Post-save processing for discount applications"""
    if kwargs.get('raw', False):
        return
    
    if not created:
        return
    
    logger.info(f"Processing discount on invoice {instance.invoice.invoice_number}")
    
    # Update student account
    try:
        from fees.models import StudentAccount, AccountTransaction
        
        student_account, _ = StudentAccount.objects.get_or_create(student=instance.student)
        
        transaction_amount = instance.discount_amount
        new_balance = student_account.get_current_balance() + transaction_amount
        
        AccountTransaction.objects.create(
            student_account=student_account,
            transaction_type='DISCOUNT',
            amount=transaction_amount,
            description=f"Discount on invoice {instance.invoice.invoice_number}",
            balance_after=new_balance,
            invoice=instance.invoice,
            academic_session=instance.invoice.academic_session,
            fiscal_period=instance.invoice.fiscal_period,
            reference_number=f"DISC-{instance.invoice.invoice_number}",
        )
        
        student_account.last_transaction_date = timezone.now()
        student_account.save(update_fields=['last_transaction_date'])
        
        logger.info("✓ Updated student account for discount")
    except Exception as e:
        logger.error(f"✗ Error updating student account: {e}", exc_info=True)
    
    # Create journal entry
    try:
        from finance.models import JournalEntry, JournalTransaction, Journal
        from core.models import FinancialSettings
        
        settings = FinancialSettings.get_instance()
        if not settings:
            return
        
        core_mappings = settings.get_account_mappings()
        
        scholarship_account = core_mappings.scholarship_discount_account
        receivable_account = core_mappings.student_receivables_account
        
        if not scholarship_account or not receivable_account:
            logger.error("✗ Required accounts not configured")
            return
        
        fees_journal, _ = Journal.objects.get_or_create(
            journal_type='FEES',
            defaults={'name': 'Fee Collections'}
        )
        
        journal_entry = JournalEntry.objects.create(
            journal=fees_journal,
            entry_date=instance.application_date,
            fiscal_period=instance.invoice.fiscal_period,
            description=f"Discount applied - {instance.student.get_full_name()}",
            reference_number=f"DISC-{instance.invoice.invoice_number}",
            status='POSTED',
        )
        
        # DR: Scholarship/Discount Expense
        JournalTransaction.objects.create(
            journal_entry=journal_entry,
            account=scholarship_account,
            amount=instance.discount_amount,
            is_debit=True,
            description=f"Discount on invoice {instance.invoice.invoice_number}",
        )
        
        # CR: Accounts Receivable
        JournalTransaction.objects.create(
            journal_entry=journal_entry,
            account=receivable_account,
            amount=instance.discount_amount,
            is_debit=False,
            description=f"Discount adjustment",
        )
        
        logger.info("✓ Created discount journal entry")
    except Exception as e:
        logger.error(f"✗ Error creating discount journal entry: {e}", exc_info=True)


# =============================================================================
# BAD DEBT WRITE-OFF SIGNALS
# =============================================================================

@receiver(post_save, sender='fees.BadDebtWriteOff')
def bad_debt_write_off_post_save(sender, instance, created, **kwargs):
    """Post-save processing for bad debt write-offs"""
    if kwargs.get('raw', False):
        return
    
    if not created:
        return
    
    logger.info(f"Processing bad debt write-off for {instance.invoice.invoice_number}")
    
    # Update student account
    try:
        from fees.models import StudentAccount, AccountTransaction
        
        student_account, _ = StudentAccount.objects.get_or_create(student=instance.invoice.student)
        
        transaction_amount = instance.write_off_amount
        new_balance = student_account.get_current_balance() + transaction_amount
        
        AccountTransaction.objects.create(
            student_account=student_account,
            transaction_type='ADJUSTMENT',
            amount=transaction_amount,
            description=f"Bad debt write-off - Invoice {instance.invoice.invoice_number}",
            balance_after=new_balance,
            invoice=instance.invoice,
            academic_session=instance.invoice.academic_session,
            fiscal_period=instance.fiscal_period,
            reference_number=f"WO-{instance.invoice.invoice_number}",
        )
        
        student_account.last_transaction_date = timezone.now()
        student_account.save(update_fields=['last_transaction_date'])
        
        logger.info("✓ Updated student account for write-off")
    except Exception as e:
        logger.error(f"✗ Error updating student account: {e}", exc_info=True)
    
    # Create journal entry
    try:
        from finance.models import JournalEntry, JournalTransaction, Journal
        from core.models import FinancialSettings
        
        settings = FinancialSettings.get_instance()
        if not settings:
            return
        
        core_mappings = settings.get_account_mappings()
        special_mappings = settings.get_special_mappings()
        
        bad_debt_account = special_mappings.bad_debt_expense_account
        allowance_account = special_mappings.allowance_for_doubtful_accounts
        receivable_account = core_mappings.student_receivables_account
        
        if not bad_debt_account or not receivable_account:
            logger.error("✗ Required accounts not configured")
            return
        
        fees_journal, _ = Journal.objects.get_or_create(
            journal_type='FEES',
            defaults={'name': 'Fee Collections'}
        )
        
        journal_entry = JournalEntry.objects.create(
            journal=fees_journal,
            entry_date=instance.write_off_date,
            fiscal_period=instance.fiscal_period,
            description=f"Bad debt write-off - {instance.invoice.student.get_full_name()}",
            reference_number=f"WO-{instance.invoice.invoice_number}",
            status='POSTED',
        )
        
        if allowance_account and instance.use_allowance_method:
            # Using allowance method
            JournalTransaction.objects.create(
                journal_entry=journal_entry,
                account=allowance_account,
                amount=instance.write_off_amount,
                is_debit=True,
                description=f"Write-off from allowance",
            )
        else:
            # Direct write-off method
            JournalTransaction.objects.create(
                journal_entry=journal_entry,
                account=bad_debt_account,
                amount=instance.write_off_amount,
                is_debit=True,
                description=f"Bad debt expense",
            )
        
        # CR: Accounts Receivable
        JournalTransaction.objects.create(
            journal_entry=journal_entry,
            account=receivable_account,
            amount=instance.write_off_amount,
            is_debit=False,
            description=f"Write-off uncollectible amount",
        )
        
        logger.info("✓ Created bad debt write-off journal entry")
    except Exception as e:
        logger.error(f"✗ Error creating write-off journal entry: {e}", exc_info=True)


# =============================================================================
# INVOICE ITEM SIGNALS
# =============================================================================

@receiver(post_save, sender='fees.FeeInvoiceItem')
def fee_invoice_item_post_save(sender, instance, created, **kwargs):
    """Recalculate invoice totals when items change"""
    if kwargs.get('raw', False):
        return
    
    try:
        invoice = instance.invoice
        items = invoice.items.all()
        
        invoice.subtotal_amount = sum(item.amount for item in items)
        invoice.tax_amount = sum(item.tax_amount for item in items)
        invoice.total_amount = sum(item.final_amount for item in items)
        invoice.balance = invoice.total_amount - invoice.paid_amount
        
        invoice.save(update_fields=['subtotal_amount', 'tax_amount', 'total_amount', 'balance'])
        
        logger.debug(f"Recalculated totals for invoice {invoice.invoice_number}")
    except Exception as e:
        logger.error(f"Error recalculating invoice totals: {e}", exc_info=True)


# =============================================================================
# SCHOLARSHIP APPLICATION SIGNALS
# =============================================================================

@receiver(pre_save, sender='fees.StudentScholarshipApplication')
def scholarship_application_pre_save(sender, instance, **kwargs):
    """Auto-generate application number"""
    if not instance.application_number:
        # Extract year from application_date if available, otherwise use current year
        year = None
        if instance.application_date:
            year = instance.application_date.year
        
        # Pass the scholarship program to get the correct type prefix
        instance.application_number = generate_scholarship_application_number(
            scholarship_program=instance.scholarship_program,
            year=year
        )


# =============================================================================
# AUDIT LOGGING
# =============================================================================

@receiver(pre_save, sender='fees.FeeInvoice')
def store_previous_invoice_status(sender, instance, **kwargs):
    """Store previous status for comparison"""
    if instance.pk:
        try:
            from fees.models import FeeInvoice
            previous = FeeInvoice.objects.get(pk=instance.pk)
            instance._previous_status = previous.status
        except:
            instance._previous_status = None


@receiver(post_save, sender='fees.FeeInvoice')
def log_invoice_status_change(sender, instance, created, **kwargs):
    """Log invoice status changes"""
    if kwargs.get('raw', False):
        return
    
    if not created and hasattr(instance, '_previous_status'):
        if instance._previous_status != instance.status:
            logger.info(
                f"AUDIT: Invoice status changed - {instance.invoice_number} - "
                f"From: {instance._previous_status} To: {instance.status}"
            )


# =============================================================================
# DATA INTEGRITY SIGNALS (VALIDATION)
# =============================================================================

@receiver(pre_save, sender='fees.Payment')
def validate_payment_amount(sender, instance, **kwargs):
    """Validate payment amount"""
    if instance.amount < 0:
        raise ValidationError("Payment amount cannot be negative")


@receiver(pre_save, sender='fees.Refund')
def validate_refund_amount(sender, instance, **kwargs):
    """Validate refund amount"""
    if instance.amount < 0:
        raise ValidationError("Refund amount cannot be negative")
    
    if instance.invoice and instance.amount > instance.invoice.paid_amount:
        raise ValidationError(
            f"Refund amount ({instance.amount}) cannot exceed "
            f"paid amount ({instance.invoice.paid_amount})"
        )


# =============================================================================
# AUTO-INVOICE GENERATION SIGNALS
# =============================================================================

@receiver(post_save, sender=StudentClassEnrollment)
def auto_generate_unified_student_invoice(sender, instance, created, **kwargs):
    """Auto-generate unified invoice with smart delay for pending boarding"""
    if kwargs.get('raw', False):
        return
    
    if not instance.auto_create_invoice:
        return
    
    if not (instance.is_active and instance.completion_status == 'ONGOING'):
        return
    
    if instance.academic_invoice:
        return
    
    pending_boarding = instance.student.boarding_enrollments.filter(
        academic_session=instance.academic_session,
        status='PENDING'
    ).exists()
    
    if pending_boarding:
        logger.info(f"⏳ Delaying invoice - waiting for boarding approval")
        return
    
    try:
        from fees.invoice_generators import UnifiedStudentInvoiceGenerator
        
        invoice = UnifiedStudentInvoiceGenerator.generate(instance)
        instance.academic_invoice = invoice
        instance.save(update_fields=['academic_invoice'])
        
        logger.info(f"✅ Generated DRAFT invoice {invoice.invoice_number}")
    except Exception as e:
        logger.error(f"✗ Error generating invoice: {e}", exc_info=True)


@receiver(post_save, sender=BoardingEnrollment)
def auto_generate_invoice_on_boarding_approval(sender, instance, created, **kwargs):
    """Generate unified invoice when boarding is approved"""
    if kwargs.get('raw', False):
        return
    
    if not instance.auto_create_invoice:
        return
    
    if not (instance.status == 'ACTIVE' and instance.guardian_consent):
        return
    
    class_enrollment = instance.student.class_enrollments.filter(
        academic_session=instance.academic_session,
        is_active=True,
        completion_status='ONGOING'
    ).first()
    
    if not class_enrollment:
        return
    
    if not class_enrollment.academic_invoice:
        try:
            from fees.invoice_generators import UnifiedStudentInvoiceGenerator
            
            invoice = UnifiedStudentInvoiceGenerator.generate(class_enrollment)
            
            class_enrollment.academic_invoice = invoice
            class_enrollment.save(update_fields=['academic_invoice'])
            
            instance.boarding_invoice = invoice
            instance.save(update_fields=['boarding_invoice'])
            
            logger.info(f"✅ Generated unified DRAFT invoice after boarding approval")
        except Exception as e:
            logger.error(f"✗ Error: {e}", exc_info=True)
    else:
        logger.warning("⚠️ Boarding approved after invoice exists")


@receiver(pre_save, sender=BoardingEnrollment)
def track_boarding_status_change(sender, instance, **kwargs):
    """Track status changes for boarding approval detection"""
    if instance.pk:
        try:
            old = BoardingEnrollment.objects.get(pk=instance.pk)
            instance._original_status = old.status
        except BoardingEnrollment.DoesNotExist:
            instance._original_status = None