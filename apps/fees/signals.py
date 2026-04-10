# fees/signals.py

"""
Fee Management Signal Handlers

FEATURES:
- Invoice creation and updates with DRAFT workflow
- Account transaction creation on invoice status transitions
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
1. Invoice created as DRAFT
2. Invoice finalized (DRAFT → PENDING):
   - Journal entry created and posted by the view
   - Signal creates INVOICE AccountTransaction (-amount)
3. Invoice reverted (PENDING → DRAFT):
   - Signal un-posts journal entry
   - Signal creates ADJUSTMENT AccountTransaction (+amount)
4. Payments update invoice status automatically
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
    generate_scholarship_application_number,
)


# =============================================================================
# INVOICE PRE-SAVE SIGNALS
# =============================================================================

@receiver(pre_save, sender='fees.FeeInvoice')
def fee_invoice_pre_save(sender, instance, **kwargs):
    """Auto-generate invoice number and assign fiscal period."""
    if not instance.invoice_number:
        instance.invoice_number = generate_invoice_number()
        logger.info(f"Generated invoice number: {instance.invoice_number}")

    if not instance.fiscal_period:
        from core.models import FiscalPeriod
        instance.fiscal_period = FiscalPeriod.get_current_fiscal_period()
        if not instance.fiscal_period:
            logger.warning(f"No active fiscal period found for invoice {instance.invoice_number}")


@receiver(pre_save, sender='fees.FeeInvoice')
def store_previous_invoice_status(sender, instance, **kwargs):
    """Store previous status for transition detection in post_save."""
    if instance.pk:
        try:
            from fees.models import FeeInvoice
            previous = FeeInvoice.objects.get(pk=instance.pk)
            instance._previous_status = previous.status
        except Exception:
            instance._previous_status = None
    else:
        instance._previous_status = None


# =============================================================================
# INVOICE POST-SAVE SIGNALS
# =============================================================================

@receiver(post_save, sender='fees.FeeInvoice')
def fee_invoice_post_save(sender, instance, created, **kwargs):
    """
    On new invoice creation: ensure StudentAccount exists and
    update last_transaction_date timestamp.
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
def handle_invoice_status_transition(sender, instance, created, **kwargs):
    """
    Watches FeeInvoice status transitions and handles side effects.

    DRAFT → PENDING (finalization):
      - Creates INVOICE AccountTransaction (-amount): student now owes money
      - Journal entry is created and posted by the view, not here

    PENDING → DRAFT (revert):
      - Un-posts the journal entry
      - Creates ADJUSTMENT AccountTransaction (+amount): cancels the debt
    """
    if kwargs.get('raw', False):
        return

    if created:
        return

    if not hasattr(instance, '_previous_status'):
        return

    previous = instance._previous_status
    current  = instance.status

    if previous == current:
        return

    # ── DRAFT → PENDING ───────────────────────────────────────────────────
    if previous == 'DRAFT' and current == 'PENDING':
        if instance.total_amount <= Decimal('0.00'):
            logger.debug(
                f"Skipping account transaction for zero-amount invoice "
                f"{instance.invoice_number}"
            )
            return

        try:
            from fees.models import StudentAccount, AccountTransaction

            student_account, _ = StudentAccount.objects.get_or_create(
                student=instance.student
            )
            current_balance = student_account.get_current_balance()
            new_balance     = current_balance - instance.total_amount

            AccountTransaction.objects.create(
                student_account  = student_account,
                transaction_type = 'INVOICE',
                amount           = -instance.total_amount,
                description      = f"Invoice {instance.invoice_number} — {instance.student.get_full_name()}",
                balance_after    = new_balance,
                invoice          = instance,
                academic_session = instance.academic_session,
                fiscal_period    = instance.fiscal_period,
                reference_number = instance.invoice_number,
            )

            student_account.last_transaction_date = timezone.now()
            student_account.save(update_fields=['last_transaction_date'])

            logger.info(
                f"[OK] Created INVOICE account transaction for "
                f"{instance.invoice_number} ({-instance.total_amount:,.2f})"
            )

        except Exception as e:
            logger.error(
                f"[ERROR] Error creating INVOICE account transaction for "
                f"{instance.invoice_number}: {e}",
                exc_info=True,
            )

    # ── PENDING → DRAFT ───────────────────────────────────────────────────
    elif previous == 'PENDING' and current == 'DRAFT':
        if instance.total_amount <= Decimal('0.00'):
            return

        try:
            from fees.models import StudentAccount, AccountTransaction

            # Un-post the journal entry
            if instance.journal_entry_id:
                try:
                    je = instance.journal_entry
                    if je.status == 'POSTED':
                        je.status    = 'DRAFT'
                        je.posted_at = None
                        je.save(update_fields=['status', 'posted_at'])
                        logger.info(
                            f"[OK] Un-posted journal entry {je.entry_number} "
                            f"for reverted invoice {instance.invoice_number}"
                        )
                except Exception as e:
                    logger.error(
                        f"[ERROR] Error un-posting journal entry for "
                        f"{instance.invoice_number}: {e}",
                        exc_info=True,
                    )

            # Reverse the INVOICE account transaction
            student_account, _ = StudentAccount.objects.get_or_create(
                student=instance.student
            )
            current_balance = student_account.get_current_balance()
            new_balance     = current_balance + instance.total_amount

            AccountTransaction.objects.create(
                student_account  = student_account,
                transaction_type = 'ADJUSTMENT',
                amount           = instance.total_amount,
                description      = f"Reversal — invoice {instance.invoice_number} reverted to DRAFT",
                balance_after    = new_balance,
                invoice          = instance,
                academic_session = instance.academic_session,
                fiscal_period    = instance.fiscal_period,
                reference_number = f"REV-{instance.invoice_number}",
            )

            student_account.last_transaction_date = timezone.now()
            student_account.save(update_fields=['last_transaction_date'])

            logger.info(
                f"[OK] Created ADJUSTMENT account transaction for reverted "
                f"invoice {instance.invoice_number} (+{instance.total_amount:,.2f})"
            )

        except Exception as e:
            logger.error(
                f"[ERROR] Error processing PENDING → DRAFT transition for "
                f"{instance.invoice_number}: {e}",
                exc_info=True,
            )


@receiver(post_save, sender='fees.FeeInvoice')
def log_invoice_status_change(sender, instance, created, **kwargs):
    """Audit log for invoice status changes."""
    if kwargs.get('raw', False):
        return

    if not created and hasattr(instance, '_previous_status'):
        if instance._previous_status != instance.status:
            logger.info(
                f"AUDIT: Invoice status changed - {instance.invoice_number} - "
                f"From: {instance._previous_status} To: {instance.status}"
            )


# =============================================================================
# INVOICE PRE-DELETE SIGNAL
# =============================================================================

@receiver(pre_delete, sender='fees.FeeInvoice')
def fee_invoice_pre_delete(sender, instance, **kwargs):
    """
    Clean up related records when invoice is deleted.

    Allow deletion if:
    - Invoice is DRAFT, VOID, or CANCELLED

    Block deletion if:
    - Invoice has payments
    - Journal entry is POSTED
    """
    from finance.models import JournalEntry
    from fees.models import AccountTransaction

    logger.info(f"Attempting to delete invoice: {instance.invoice_number}")

    # Allow VOID / CANCELLED without further checks
    if instance.status in ['VOID', 'CANCELLED']:
        logger.info(
            f"Deleting {instance.status} invoice {instance.invoice_number} - "
            f"no financial impact"
        )

        try:
            deleted_count = AccountTransaction.objects.filter(invoice=instance).delete()[0]
            if deleted_count > 0:
                logger.warning(
                    f"Deleted {deleted_count} AccountTransaction(s) for VOID invoice "
                    f"{instance.invoice_number} (these should not have existed)"
                )
        except Exception as e:
            logger.error(f"Error cleaning up account transactions: {e}")

        if instance.journal_entry_id:
            logger.warning(
                f"VOID invoice {instance.invoice_number} has journal entry "
                f"{instance.journal_entry_id} - this is unexpected"
            )
        return

    # DRAFT invoices — standard safety checks
    if instance.status != 'DRAFT':
        raise ValidationError(
            f"Cannot delete invoice {instance.invoice_number}: "
            f"Invoice status is {instance.status} (must be DRAFT, VOID, or CANCELLED)\n\n"
            f"Use 'Void' or 'Cancel' status instead of deleting finalized invoices."
        )

    journal_entry_id = instance.journal_entry_id
    journal_entry    = None

    if journal_entry_id:
        try:
            journal_entry = JournalEntry.objects.get(pk=journal_entry_id)
        except JournalEntry.DoesNotExist:
            journal_entry = None

    if journal_entry and journal_entry.status != 'DRAFT':
        raise ValidationError(
            f"Cannot delete invoice {instance.invoice_number}: "
            f"Journal entry {journal_entry.entry_number} is {journal_entry.status} "
            f"(must be DRAFT)\n\n"
            f"Use 'Void' or 'Cancel' status instead of deleting finalized invoices."
        )

    if instance.paid_amount > 0:
        raise ValidationError(
            f"Cannot delete invoice {instance.invoice_number}: "
            f"Invoice has payments totaling {instance.paid_amount}"
        )

    logger.info(
        f"Safety checks passed - proceeding with deletion of DRAFT invoice "
        f"{instance.invoice_number}"
    )

    # Step 1: Delete AccountTransactions
    try:
        deleted_count = AccountTransaction.objects.filter(invoice=instance).delete()[0]
        if deleted_count > 0:
            logger.info(
                f"Deleted {deleted_count} AccountTransaction(s) for invoice "
                f"{instance.invoice_number}"
            )

        if instance.student:
            from fees.models import StudentAccount
            student_account, _ = StudentAccount.objects.get_or_create(student=instance.student)
            student_account.last_transaction_date = timezone.now()
            student_account.save(update_fields=['last_transaction_date'])

    except Exception as e:
        logger.error(f"Error deleting AccountTransactions: {e}", exc_info=True)

    # Step 2: Delete DRAFT journal entry
    if journal_entry and journal_entry.status == 'DRAFT':
        try:
            entry_number = journal_entry.entry_number
            journal_entry.delete()
            logger.info(f"Deleted DRAFT journal entry {entry_number}")
        except Exception as e:
            logger.error(f"Error deleting journal entry: {e}", exc_info=True)

    logger.info(f"Pre-delete cleanup completed for invoice {instance.invoice_number}")


# =============================================================================
# PAYMENT PRE-SAVE SIGNALS
# =============================================================================

@receiver(pre_save, sender='fees.Payment')
def payment_pre_save(sender, instance, **kwargs):
    """Pre-save processing for payments."""
    if not instance.payment_number:
        instance.payment_number = generate_payment_number()
        logger.info(f"Generated payment number: {instance.payment_number}")

    if not instance.receipt_number and instance.receipt_issued:
        instance.receipt_number = generate_receipt_number()
        logger.info(f"Generated receipt number: {instance.receipt_number}")

    if not instance.payment_date:
        from core.utils import get_school_today
        instance.payment_date = get_school_today()
        logger.info(
            f"Auto-set payment date to {instance.payment_date} "
            f"for payment {instance.payment_number}"
        )

    if not instance.fiscal_period_id:
        from core.models import FiscalPeriod
        period = FiscalPeriod.get_period_for_date(instance.payment_date)
        if period:
            instance.fiscal_period = period
        else:
            logger.warning(
                f"No fiscal period found for date {instance.payment_date} "
                f"on payment {instance.payment_number}"
            )

    if instance.receipt_issued and not instance.receipt_issued_date:
        from core.utils import get_school_current_time
        instance.receipt_issued_date = get_school_current_time()

    if instance.pk:
        try:
            from fees.models import Payment
            old_payment = Payment.objects.get(pk=instance.pk)
            instance._old_reversed = old_payment.reversed
            instance._old_refunded = old_payment.refunded
        except Exception:
            instance._old_reversed = False
            instance._old_refunded = False
    else:
        instance._old_reversed = False
        instance._old_refunded = False


@receiver(pre_save, sender='fees.Payment')
def validate_payment_amount(sender, instance, **kwargs):
    """Validate payment amount is not negative."""
    if instance.amount < 0:
        raise ValidationError("Payment amount cannot be negative")


# =============================================================================
# PAYMENT POST-SAVE SIGNAL
# =============================================================================

@receiver(post_save, sender='fees.Payment')
def payment_post_save(sender, instance, created, **kwargs):
    """
    Post-save processing for payments.

    Handles:
    1. New payment creation — update invoice balance, student account, journal entry
    2. Payment reversals — create reversal journal entry
    3. Payment refunds — create refund journal entry
    """
    if kwargs.get('raw', False):
        return

    was_just_reversed = (
        hasattr(instance, '_old_reversed') and
        not instance._old_reversed and
        instance.reversed
    )

    was_just_refunded = (
        hasattr(instance, '_old_refunded') and
        not instance._old_refunded and
        instance.refunded
    )

    if was_just_reversed:
        _handle_payment_reversal(instance)
        return

    if was_just_refunded:
        _handle_payment_refund(instance)
        return

    if not instance.is_active:
        logger.info(f"Skipping inactive payment {instance.payment_number}")
        return

    if instance.journal_entry:
        logger.info(
            f"Payment {instance.payment_number} already has journal entry "
            f"{instance.journal_entry.entry_number} - skipping journal creation"
        )
        _update_invoice_balance(instance)
        _update_student_account_for_payment(instance)
        return

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
    """Handle payment reversal (internal correction, no money returned)."""
    from fees.models import StudentAccount, AccountTransaction
    from finance.models import JournalEntry, JournalTransaction, Journal
    from finance.utils import generate_journal_entry_number
    from core.models import FiscalPeriod

    logger.info(f"Processing reversal for payment {payment.payment_number}")

    try:
        if payment.invoice:
            invoice = payment.invoice
            invoice.paid_amount -= payment.amount_applied_to_invoice
            invoice.balance      = invoice.total_amount - invoice.paid_amount

            if invoice.balance >= invoice.total_amount:
                invoice.status = 'PENDING'
            elif invoice.paid_amount > 0:
                invoice.status = 'PARTIALLY_PAID'

            invoice.save(update_fields=['paid_amount', 'balance', 'status'])
            logger.info(f"[OK] Updated invoice {invoice.invoice_number}")

        student_account, _ = StudentAccount.objects.get_or_create(student=payment.student)
        new_balance = student_account.get_current_balance() - payment.amount

        AccountTransaction.objects.create(
            student_account  = student_account,
            transaction_type = 'ADJUSTMENT',
            amount           = -payment.amount,
            description      = (
                f"Reversal of payment {payment.payment_number}: {payment.reversal_reason}"
            ),
            balance_after    = new_balance,
            invoice          = payment.invoice,
            payment          = payment,
            academic_session = payment.academic_session,
            fiscal_period    = payment.fiscal_period,
            reference_number = f"REV-{payment.payment_number}",
        )

        student_account.last_transaction_date = timezone.now()
        student_account.save(update_fields=['last_transaction_date'])
        logger.info(f"[OK] Created reversal transaction")

        receivable_account = payment.get_receivable_account()
        cash_account       = payment.get_deposit_account()

        if not receivable_account:
            logger.error("[ERROR] Student receivables account not configured")
            return
        if not cash_account:
            logger.error("[ERROR] Cash/Bank account not found for payment method")
            return

        fees_journal, _ = Journal.objects.get_or_create(
            journal_type='FEES',
            defaults={
                'name':        'Fee Collections',
                'description': 'Journal for recording student fee payments',
                'is_active':   True,
            },
        )

        reversal_entry = JournalEntry.objects.create(
            journal          = fees_journal,
            entry_number     = generate_journal_entry_number(fees_journal),
            entry_date       = timezone.now().date(),
            fiscal_period    = FiscalPeriod.get_current_fiscal_period() or payment.fiscal_period,
            academic_session = payment.academic_session,
            description      = (
                f"Payment reversal - {payment.student.get_full_name()}: "
                f"{payment.reversal_reason}"
            ),
            reference_number = f"REV-{payment.payment_number}",
            status           = 'POSTED',
        )

        JournalTransaction.objects.create(
            journal_entry = reversal_entry,
            account       = receivable_account,
            amount        = payment.amount,
            is_debit      = True,
            description   = f"Reversal of payment {payment.payment_number}",
        )

        JournalTransaction.objects.create(
            journal_entry = reversal_entry,
            account       = cash_account,
            amount        = payment.amount,
            is_debit      = False,
            description   = "Payment reversal - internal correction",
        )

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
        if payment.invoice:
            invoice = payment.invoice
            invoice.paid_amount -= payment.amount_applied_to_invoice
            invoice.balance      = invoice.total_amount - invoice.paid_amount

            if invoice.balance >= invoice.total_amount:
                invoice.status = 'PENDING'
            elif invoice.paid_amount > 0:
                invoice.status = 'PARTIALLY_PAID'

            invoice.save(update_fields=['paid_amount', 'balance', 'status'])
            logger.info(f"[OK] Updated invoice {invoice.invoice_number}")

        student_account, _ = StudentAccount.objects.get_or_create(student=payment.student)
        new_balance = student_account.get_current_balance() - payment.amount

        AccountTransaction.objects.create(
            student_account  = student_account,
            transaction_type = 'REFUND',
            amount           = -payment.amount,
            description      = f"Refund of payment {payment.payment_number}: {payment.refund_notes}",
            balance_after    = new_balance,
            invoice          = payment.invoice,
            payment          = payment,
            academic_session = payment.academic_session,
            fiscal_period    = payment.fiscal_period,
            reference_number = payment.refund_reference or f"REF-{payment.payment_number}",
        )

        student_account.last_transaction_date = timezone.now()
        student_account.save(update_fields=['last_transaction_date'])
        logger.info(f"[OK] Created refund transaction")

        settings = FinancialSettings.get_instance()
        if not settings:
            logger.error("[ERROR] FinancialSettings not configured")
            return

        receivable_account     = payment.get_receivable_account()
        cash_account           = payment.get_deposit_account()
        special_mappings       = settings.get_special_mappings()
        credit_balance_account = special_mappings.student_credit_balance_account

        if not receivable_account or not cash_account:
            logger.error("[ERROR] Required accounts not found for refund")
            return

        had_credit_balance = (student_account.get_current_balance() + payment.amount) > 0

        fees_journal, _ = Journal.objects.get_or_create(
            journal_type='FEES',
            defaults={
                'name':        'Fee Collections',
                'description': 'Journal for recording student fee payments',
                'is_active':   True,
            },
        )

        refund_entry = JournalEntry.objects.create(
            journal          = fees_journal,
            entry_number     = generate_journal_entry_number(fees_journal),
            entry_date       = timezone.now().date(),
            fiscal_period    = FiscalPeriod.get_current_fiscal_period() or payment.fiscal_period,
            academic_session = payment.academic_session,
            description      = (
                f"Payment refund - {payment.student.get_full_name()}: {payment.refund_notes}"
            ),
            reference_number = payment.refund_reference or f"REF-{payment.payment_number}",
            status           = 'POSTED',
        )

        if had_credit_balance and credit_balance_account:
            JournalTransaction.objects.create(
                journal_entry = refund_entry,
                account       = credit_balance_account,
                amount        = payment.amount,
                is_debit      = True,
                description   = "Refund from credit balance",
            )
            logger.info(f"[OK] Refund from credit balance")
        else:
            JournalTransaction.objects.create(
                journal_entry = refund_entry,
                account       = receivable_account,
                amount        = payment.amount,
                is_debit      = True,
                description   = "Refund creates receivable",
            )
            logger.info(f"[OK] Refund creates receivable")

        JournalTransaction.objects.create(
            journal_entry = refund_entry,
            account       = cash_account,
            amount        = payment.amount,
            is_debit      = False,
            description   = (
                f"Refund to {payment.student.get_full_name()} via {payment.refund_method}"
            ),
        )

        from fees.models import Payment
        Payment.objects.filter(pk=payment.pk).update(refund_journal_entry=refund_entry)

        logger.info(f"[OK] Created refund journal entry {refund_entry.entry_number}")

    except Exception as e:
        logger.error(f"[ERROR] Error handling payment refund: {e}", exc_info=True)


# =============================================================================
# PAYMENT HELPER FUNCTIONS
# =============================================================================

def _update_invoice_balance(payment):
    """Recompute invoice paid_amount, balance, and status from active payments."""
    if not payment.invoice:
        return

    try:
        invoice = payment.invoice

        total_paid = invoice.payments.filter(
            status='COMPLETED',
            reversed=False,
            refunded=False,
        ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')

        invoice.paid_amount = total_paid
        invoice.balance     = invoice.total_amount - invoice.paid_amount

        if invoice.balance <= Decimal('0.00'):
            invoice.status = 'PAID'
        elif invoice.paid_amount > Decimal('0.00'):
            invoice.status = 'PARTIALLY_PAID'
        else:
            invoice.status = 'PENDING'

        invoice.save(update_fields=['paid_amount', 'balance', 'status'])

        logger.info(
            f"Updated invoice {invoice.invoice_number} - "
            f"Paid: {invoice.paid_amount:,.2f}, Balance: {invoice.balance:,.2f}, "
            f"Status: {invoice.status}"
        )

    except Exception as e:
        logger.error(f"Error updating invoice balance: {e}", exc_info=True)


def _update_student_account_for_payment(payment):
    """Create PAYMENT AccountTransaction and update student account timestamps."""
    try:
        from fees.models import StudentAccount, AccountTransaction
        from core.utils import get_school_current_time

        student_account, _ = StudentAccount.objects.get_or_create(student=payment.student)

        current_balance = student_account.get_current_balance()
        new_balance     = current_balance + payment.amount

        AccountTransaction.objects.create(
            student_account  = student_account,
            transaction_type = 'PAYMENT',
            amount           = payment.amount,
            description      = f"Payment {payment.payment_number}",
            balance_after    = new_balance,
            invoice          = payment.invoice,
            payment          = payment,
            academic_session = payment.academic_session,
            fiscal_period    = payment.fiscal_period,
            reference_number = payment.payment_number,
        )

        student_account.last_payment_date     = get_school_current_time()
        student_account.last_transaction_date = get_school_current_time()
        student_account.save(update_fields=['last_payment_date', 'last_transaction_date'])

        logger.info(f"Updated student account - New balance: {new_balance:,.2f}")

    except Exception as e:
        logger.error(f"Error updating student account: {e}", exc_info=True)


def _create_payment_journal_entry(payment):
    """Create and post journal entry for a new payment."""
    try:
        from finance.models import Journal, JournalEntry, JournalTransaction
        from core.models import FinancialSettings

        settings = FinancialSettings.get_instance()
        if not settings:
            logger.error("FinancialSettings not found")
            return

        core_mappings           = settings.get_account_mappings()
        special_mappings        = settings.get_special_mappings()
        cash_account            = core_mappings.get_cash_or_bank_account(payment.payment_method)
        receivable_account      = core_mappings.student_receivables_account
        unearned_revenue_account = special_mappings.unearned_revenue_account
        credit_balance_account  = special_mappings.student_credit_balance_account

        if not cash_account or not receivable_account:
            logger.error("Required accounts not configured")
            return

        fees_journal, _ = Journal.objects.get_or_create(
            journal_type='FEES',
            defaults={
                'name':        'Fee Collections',
                'description': 'Journal for recording student fee payments',
                'is_active':   True,
            },
        )

        from fees.models import StudentAccount
        student_account, _ = StudentAccount.objects.get_or_create(student=payment.student)

        current_balance        = student_account.get_current_balance()
        balance_before_payment = current_balance - payment.amount
        outstanding_before     = abs(balance_before_payment) if balance_before_payment < 0 else Decimal('0.00')

        # Scenario A: Payment against invoice with outstanding balance
        if payment.invoice and outstanding_before > 0:
            amount_to_receivable = min(payment.amount, outstanding_before)
            overpayment_amount   = payment.amount - amount_to_receivable

            journal_entry = JournalEntry.objects.create(
                journal          = fees_journal,
                entry_date       = payment.payment_date,
                fiscal_period    = payment.fiscal_period,
                academic_session = payment.academic_session,
                description      = f"Payment received - {payment.student.get_full_name()}",
                reference_number = payment.payment_number,
                status           = 'POSTED',
            )

            JournalTransaction.objects.create(
                journal_entry = journal_entry,
                account       = cash_account,
                amount        = payment.amount,
                is_debit      = True,
                description   = f"Payment from {payment.student.get_full_name()}",
            )

            if amount_to_receivable > 0:
                JournalTransaction.objects.create(
                    journal_entry = journal_entry,
                    account       = receivable_account,
                    amount        = amount_to_receivable,
                    is_debit      = False,
                    description   = f"Payment against invoice {payment.invoice.invoice_number}",
                )

            if overpayment_amount > 0 and credit_balance_account:
                JournalTransaction.objects.create(
                    journal_entry = journal_entry,
                    account       = credit_balance_account,
                    amount        = overpayment_amount,
                    is_debit      = False,
                    description   = "Student overpayment - credit balance",
                )

        # Scenario B: Advance payment (no invoice)
        elif not payment.invoice and unearned_revenue_account:
            journal_entry = JournalEntry.objects.create(
                journal          = fees_journal,
                entry_date       = payment.payment_date,
                fiscal_period    = payment.fiscal_period,
                academic_session = payment.academic_session,
                description      = f"Advance payment - {payment.student.get_full_name()}",
                reference_number = payment.payment_number,
                status           = 'POSTED',
            )

            JournalTransaction.objects.create(
                journal_entry = journal_entry,
                account       = cash_account,
                amount        = payment.amount,
                is_debit      = True,
                description   = f"Advance payment from {payment.student.get_full_name()}",
            )

            JournalTransaction.objects.create(
                journal_entry = journal_entry,
                account       = unearned_revenue_account,
                amount        = payment.amount,
                is_debit      = False,
                description   = "Advance payment - unearned revenue",
            )

        # Scenario C: Standard fallback
        else:
            journal_entry = JournalEntry.objects.create(
                journal          = fees_journal,
                entry_date       = payment.payment_date,
                fiscal_period    = payment.fiscal_period,
                academic_session = payment.academic_session,
                description      = f"Payment received - {payment.student.get_full_name()}",
                reference_number = payment.payment_number,
                status           = 'POSTED',
            )

            JournalTransaction.objects.create(
                journal_entry = journal_entry,
                account       = cash_account,
                amount        = payment.amount,
                is_debit      = True,
                description   = f"Payment from {payment.student.get_full_name()}",
            )

            JournalTransaction.objects.create(
                journal_entry = journal_entry,
                account       = receivable_account,
                amount        = payment.amount,
                is_debit      = False,
                description   = "Payment against fees",
            )

        from fees.models import Payment
        Payment.objects.filter(pk=payment.pk).update(journal_entry=journal_entry)

        logger.info(f"Created journal entry {journal_entry.entry_number}")

    except Exception as e:
        logger.error(f"Error creating payment journal entry: {e}", exc_info=True)


# =============================================================================
# PAYMENT DELETE SIGNALS
# =============================================================================

@receiver(pre_delete, sender='fees.Payment')
def payment_pre_delete(sender, instance, **kwargs):
    """Validate payment deletion is safe."""
    logger.info(f"Pre-delete check for payment {instance.payment_number}")

    if instance.reversed or instance.refunded:
        logger.info(
            f"[OK] Allowing deletion of "
            f"{'reversed' if instance.reversed else 'refunded'} "
            f"payment {instance.payment_number}"
        )
        return

    if not instance.is_verified and not instance.journal_entry_id:
        logger.info(f"[OK] Allowing deletion of unverified payment {instance.payment_number}")
        return

    if instance.fiscal_period and hasattr(instance.fiscal_period, 'is_closed'):
        if instance.fiscal_period.is_closed:
            raise ValidationError(
                f"Cannot delete payment {instance.payment_number}: "
                f"Fiscal period {instance.fiscal_period.name} is closed"
            )

    if instance.is_verified or instance.status == 'COMPLETED':
        raise ValidationError(
            f"Cannot delete payment {instance.payment_number}: "
            f"Payment is {instance.status} and verified. "
            f"Use 'Reverse Payment' instead to maintain audit trail."
        )

    logger.info(f"[OK] Payment {instance.payment_number} can be safely deleted")


@receiver(post_delete, sender='fees.Payment')
def payment_post_delete(sender, instance, **kwargs):
    """Handle payment deletion with complete cleanup."""
    logger.info(f"Processing deletion of payment {instance.payment_number}")

    # Step 1: Update invoice balance
    invoice_id = instance.invoice_id
    if invoice_id:
        try:
            from fees.models import FeeInvoice
            invoice = FeeInvoice.objects.get(pk=invoice_id)

            total_paid = invoice.payments.filter(
                status='COMPLETED',
                reversed=False,
                refunded=False,
            ).exclude(pk=instance.pk).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')

            invoice.paid_amount = total_paid
            invoice.balance     = invoice.total_amount - invoice.paid_amount

            if invoice.balance <= Decimal('0.00'):
                invoice.status = 'PAID'
            elif invoice.paid_amount > Decimal('0.00'):
                invoice.status = 'PARTIALLY_PAID'
            else:
                invoice.status = 'PENDING'

            invoice.save(update_fields=['paid_amount', 'balance', 'status'])
            logger.info(
                f"[OK] Updated invoice {invoice.invoice_number} after payment deletion"
            )

        except Exception as e:
            logger.error(f"[ERROR] Error updating invoice after payment deletion: {e}", exc_info=True)

    # Step 2: Delete AccountTransaction
    try:
        from fees.models import AccountTransaction
        deleted_count = AccountTransaction.objects.filter(payment=instance).delete()[0]
        if deleted_count > 0:
            logger.info(
                f"[OK] Deleted {deleted_count} AccountTransaction(s) for payment "
                f"{instance.payment_number}"
            )
        else:
            logger.warning(
                f"[WARNING] No AccountTransaction found for payment {instance.payment_number}"
            )
    except Exception as e:
        logger.error(f"[ERROR] Error deleting AccountTransaction: {e}", exc_info=True)

    # Step 3: Delete journal entries
    journal_entry_ids = {
        'journal_entry':          instance.journal_entry_id,
        'reversal_journal_entry': instance.reversal_journal_entry_id,
        'refund_journal_entry':   instance.refund_journal_entry_id,
    }

    from finance.models import JournalEntry

    for entry_name, entry_id in journal_entry_ids.items():
        if entry_id:
            try:
                journal_entry = JournalEntry.objects.get(pk=entry_id)
                entry_number  = journal_entry.entry_number

                if journal_entry.fiscal_period and hasattr(journal_entry.fiscal_period, 'is_closed'):
                    if journal_entry.fiscal_period.is_closed:
                        logger.error(
                            f"[ERROR] Cannot delete journal entry {entry_number}: "
                            f"Fiscal period {journal_entry.fiscal_period.name} is CLOSED"
                        )
                        continue

                if journal_entry.status == 'POSTED':
                    journal_entry.status = 'DRAFT'
                    journal_entry.save(update_fields=['status'])
                    logger.info(f"[OK] Changed {entry_number} status to DRAFT")

                journal_entry.delete()
                logger.info(f"[OK] Deleted journal entry {entry_number} ({entry_name})")

            except JournalEntry.DoesNotExist:
                logger.warning(f"[WARNING] Journal entry {entry_id} not found (already deleted)")
            except Exception as e:
                logger.error(f"[ERROR] Error deleting {entry_name}: {e}", exc_info=True)

    # Step 4: Update student account timestamp
    try:
        from fees.models import StudentAccount
        student_account, _ = StudentAccount.objects.get_or_create(student=instance.student)
        student_account.last_transaction_date = timezone.now()
        student_account.save(update_fields=['last_transaction_date'])
        logger.info(f"[OK] Updated student account timestamp after payment deletion")
    except Exception as e:
        logger.error(f"[ERROR] Error updating student account: {e}", exc_info=True)

    logger.info(f"[SUCCESS] Completed payment deletion cleanup for {instance.payment_number}")


# =============================================================================
# INVOICE ITEM SIGNALS
# =============================================================================

@receiver(post_save, sender='fees.FeeInvoiceItem')
def fee_invoice_item_post_save(sender, instance, created, **kwargs):
    """Recalculate invoice totals when line items change."""
    if kwargs.get('raw', False):
        return

    try:
        invoice = instance.invoice
        items   = invoice.items.all()

        invoice.subtotal_amount = sum(item.amount       for item in items)
        invoice.tax_amount      = sum(item.tax_amount   for item in items)
        invoice.total_amount    = sum(item.final_amount for item in items)
        invoice.balance         = invoice.total_amount - invoice.paid_amount

        invoice.save(update_fields=[
            'subtotal_amount', 'tax_amount', 'total_amount', 'balance'
        ])

        logger.debug(f"Recalculated totals for invoice {invoice.invoice_number}")

    except Exception as e:
        logger.error(f"Error recalculating invoice totals: {e}", exc_info=True)


# =============================================================================
# DISCOUNT SIGNALS
# =============================================================================

@receiver(post_save, sender='fees.DiscountApplication')
def discount_application_post_save(sender, instance, created, **kwargs):
    """Create AccountTransaction and journal entry when discount is applied."""
    if kwargs.get('raw', False):
        return

    if not created:
        return

    logger.info(f"Processing discount on invoice {instance.invoice.invoice_number}")

    try:
        from fees.models import StudentAccount, AccountTransaction

        student_account, _ = StudentAccount.objects.get_or_create(student=instance.student)

        new_balance = student_account.get_current_balance() + instance.discount_amount

        AccountTransaction.objects.create(
            student_account  = student_account,
            transaction_type = 'DISCOUNT',
            amount           = instance.discount_amount,
            description      = f"Discount on invoice {instance.invoice.invoice_number}",
            balance_after    = new_balance,
            invoice          = instance.invoice,
            academic_session = instance.invoice.academic_session,
            fiscal_period    = instance.invoice.fiscal_period,
            reference_number = f"DISC-{instance.invoice.invoice_number}",
        )

        student_account.last_transaction_date = timezone.now()
        student_account.save(update_fields=['last_transaction_date'])
        logger.info("[OK] Updated student account for discount")

    except Exception as e:
        logger.error(f"Error updating student account for discount: {e}", exc_info=True)

    try:
        from finance.models import JournalEntry, JournalTransaction, Journal
        from core.models import FinancialSettings

        settings = FinancialSettings.get_instance()
        if not settings:
            return

        core_mappings       = settings.get_account_mappings()
        scholarship_account = core_mappings.scholarship_discount_account
        receivable_account  = core_mappings.student_receivables_account

        if not scholarship_account or not receivable_account:
            logger.error("Required accounts not configured for discount journal entry")
            return

        fees_journal, _ = Journal.objects.get_or_create(
            journal_type='FEES',
            defaults={'name': 'Fee Collections'},
        )

        journal_entry = JournalEntry.objects.create(
            journal          = fees_journal,
            entry_date       = instance.application_date,
            fiscal_period    = instance.invoice.fiscal_period,
            description      = f"Discount applied - {instance.student.get_full_name()}",
            reference_number = f"DISC-{instance.invoice.invoice_number}",
            status           = 'POSTED',
        )

        JournalTransaction.objects.create(
            journal_entry = journal_entry,
            account       = scholarship_account,
            amount        = instance.discount_amount,
            is_debit      = True,
            description   = f"Discount on invoice {instance.invoice.invoice_number}",
        )

        JournalTransaction.objects.create(
            journal_entry = journal_entry,
            account       = receivable_account,
            amount        = instance.discount_amount,
            is_debit      = False,
            description   = "Discount adjustment",
        )

        logger.info("[OK] Created discount journal entry")

    except Exception as e:
        logger.error(f"Error creating discount journal entry: {e}", exc_info=True)


# =============================================================================
# BAD DEBT WRITE-OFF SIGNALS
# =============================================================================

@receiver(post_save, sender='fees.BadDebtWriteOff')
def bad_debt_write_off_post_save(sender, instance, created, **kwargs):
    """Create AccountTransaction and journal entry for bad debt write-offs."""
    if kwargs.get('raw', False):
        return

    if not created:
        return

    logger.info(f"Processing bad debt write-off for {instance.invoice.invoice_number}")

    try:
        from fees.models import StudentAccount, AccountTransaction

        student_account, _ = StudentAccount.objects.get_or_create(
            student=instance.invoice.student
        )

        new_balance = student_account.get_current_balance() + instance.write_off_amount

        AccountTransaction.objects.create(
            student_account  = student_account,
            transaction_type = 'ADJUSTMENT',
            amount           = instance.write_off_amount,
            description      = f"Bad debt write-off - Invoice {instance.invoice.invoice_number}",
            balance_after    = new_balance,
            invoice          = instance.invoice,
            academic_session = instance.invoice.academic_session,
            fiscal_period    = instance.fiscal_period,
            reference_number = f"WO-{instance.invoice.invoice_number}",
        )

        student_account.last_transaction_date = timezone.now()
        student_account.save(update_fields=['last_transaction_date'])
        logger.info("[OK] Updated student account for write-off")

    except Exception as e:
        logger.error(f"Error updating student account for write-off: {e}", exc_info=True)

    try:
        from finance.models import JournalEntry, JournalTransaction, Journal
        from core.models import FinancialSettings

        settings = FinancialSettings.get_instance()
        if not settings:
            return

        core_mappings      = settings.get_account_mappings()
        special_mappings   = settings.get_special_mappings()
        bad_debt_account   = special_mappings.bad_debt_expense_account
        allowance_account  = special_mappings.allowance_for_doubtful_accounts
        receivable_account = core_mappings.student_receivables_account

        if not bad_debt_account or not receivable_account:
            logger.error("Required accounts not configured for write-off journal entry")
            return

        fees_journal, _ = Journal.objects.get_or_create(
            journal_type='FEES',
            defaults={'name': 'Fee Collections'},
        )

        journal_entry = JournalEntry.objects.create(
            journal          = fees_journal,
            entry_date       = instance.write_off_date,
            fiscal_period    = instance.fiscal_period,
            description      = f"Bad debt write-off - {instance.invoice.student.get_full_name()}",
            reference_number = f"WO-{instance.invoice.invoice_number}",
            status           = 'POSTED',
        )

        if allowance_account and instance.use_allowance_method:
            JournalTransaction.objects.create(
                journal_entry = journal_entry,
                account       = allowance_account,
                amount        = instance.write_off_amount,
                is_debit      = True,
                description   = "Write-off from allowance",
            )
        else:
            JournalTransaction.objects.create(
                journal_entry = journal_entry,
                account       = bad_debt_account,
                amount        = instance.write_off_amount,
                is_debit      = True,
                description   = "Bad debt expense",
            )

        JournalTransaction.objects.create(
            journal_entry = journal_entry,
            account       = receivable_account,
            amount        = instance.write_off_amount,
            is_debit      = False,
            description   = "Write-off uncollectible amount",
        )

        logger.info("[OK] Created bad debt write-off journal entry")

    except Exception as e:
        logger.error(f"Error creating write-off journal entry: {e}", exc_info=True)


# =============================================================================
# SCHOLARSHIP APPLICATION SIGNALS
# =============================================================================

@receiver(pre_save, sender='fees.StudentScholarshipApplication')
def scholarship_application_pre_save(sender, instance, **kwargs):
    """Auto-generate scholarship application number."""
    if not instance.application_number:
        year = instance.application_date.year if instance.application_date else None
        instance.application_number = generate_scholarship_application_number(
            scholarship_program=instance.scholarship_program,
            year=year,
        )


# =============================================================================
# AUTO-INVOICE GENERATION SIGNALS
# =============================================================================

@receiver(post_save, sender=StudentClassEnrollment)
def auto_generate_unified_student_invoice(sender, instance, created, **kwargs):
    """Auto-generate invoice when a new class enrollment is created."""
    if kwargs.get('raw', False):
        return

    if not created:
        return

    if not instance.auto_create_invoice:
        return

    if not (instance.is_active and instance.completion_status == 'ONGOING'):
        return

    if instance.academic_invoice:
        return

    pending_boarding = instance.student.boarding_enrollments.filter(
        academic_session=instance.academic_session,
        status='PENDING',
    ).exists()

    if pending_boarding:
        logger.info(
            f"Delaying invoice for {instance.student.get_full_name()} - "
            f"waiting for boarding approval"
        )
        return

    try:
        from fees.invoice_generators import UnifiedStudentInvoiceGenerator

        invoice = UnifiedStudentInvoiceGenerator.generate(instance)
        instance.academic_invoice = invoice
        instance.save(update_fields=['academic_invoice'])

        logger.info(
            f"Generated DRAFT invoice {invoice.invoice_number} for "
            f"{instance.student.get_full_name()}"
        )
    except Exception as e:
        logger.error(
            f"Error generating invoice for {instance.student.get_full_name()}: {e}",
            exc_info=True,
        )


@receiver(post_save, sender=BoardingEnrollment)
def auto_generate_invoice_on_boarding_approval(sender, instance, created, **kwargs):
    """Generate unified invoice when boarding enrollment is approved."""
    if kwargs.get('raw', False):
        return

    if not instance.auto_create_invoice:
        return

    if not (instance.status == 'ACTIVE' and instance.guardian_consent):
        return

    class_enrollment = instance.student.class_enrollments.filter(
        academic_session=instance.academic_session,
        is_active=True,
        completion_status='ONGOING',
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

            logger.info(
                f"Generated unified DRAFT invoice {invoice.invoice_number} "
                f"after boarding approval for {instance.student.get_full_name()}"
            )

        except Exception as e:
            logger.error(
                f"Error generating invoice after boarding approval: {e}",
                exc_info=True,
            )
    else:
        logger.warning(
            f"Boarding approved for {instance.student.get_full_name()} "
            f"but invoice already exists — skipping generation"
        )


@receiver(pre_save, sender=BoardingEnrollment)
def track_boarding_status_change(sender, instance, **kwargs):
    """Track boarding status changes for approval detection."""
    if instance.pk:
        try:
            old = BoardingEnrollment.objects.get(pk=instance.pk)
            instance._original_status = old.status
        except BoardingEnrollment.DoesNotExist:
            instance._original_status = None