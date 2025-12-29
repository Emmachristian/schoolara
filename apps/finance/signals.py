# finance/signals.py

"""
Finance Management Signals

Automatic triggers for:
- Journal entry number generation
- Expense number generation
- Account balance updates
- Journal entry validation
- Fiscal period enforcement
- Audit logging
"""

from django.db.models.signals import pre_save, post_save, post_delete, pre_delete
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from django.utils import timezone
import logging

from finance.models import (
    JournalEntry, JournalTransaction, Expense, 
    Budget, Account
)
from finance.utils import (
    generate_journal_entry_number, generate_expense_number,
    validate_journal_entry, validate_fiscal_period
)

logger = logging.getLogger(__name__)


# =============================================================================
# JOURNAL ENTRY SIGNALS
# =============================================================================

@receiver(pre_save, sender=JournalEntry)
def journal_entry_pre_save(sender, instance, **kwargs):
    """
    Pre-save processing for journal entries:
    - Auto-generate entry number
    - Set fiscal period if not set
    - Validate entry date is in open period
    """
    # Generate entry number if not set
    if not instance.entry_number:
        instance.entry_number = generate_journal_entry_number(instance.journal)
        logger.info(f"Generated journal entry number: {instance.entry_number}")
    
    # Set fiscal period if not set
    if not instance.fiscal_period:
        from core.models import FiscalPeriod
        instance.fiscal_period = FiscalPeriod.get_current_fiscal_period()
        if not instance.fiscal_period:
            logger.warning(f"No active fiscal period found for journal entry {instance.entry_number}")
    
    # Validate fiscal period if posting
    if instance.status == 'POSTED' and instance.fiscal_period:
        validation = validate_fiscal_period(instance.fiscal_period)
        if not validation['valid']:
            raise ValidationError(
                f"Cannot post journal entry to closed fiscal period: {', '.join(validation['errors'])}"
            )
    
    # Set posted date when status changes to POSTED
    if instance.status == 'POSTED' and not instance.posted_at:
        instance.posted_at = timezone.now()


@receiver(post_save, sender=JournalEntry)
def journal_entry_post_save(sender, instance, created, **kwargs):
    """
    Post-save processing for journal entries:
    - Validate entry is balanced (when posted)
    - Log entry creation
    """
    # Skip if in raw mode
    if kwargs.get('raw', False):
        return
    
    if created:
        logger.info(
            f"Journal entry created: {instance.entry_number} - "
            f"Date: {instance.entry_date} - "
            f"Status: {instance.status}"
        )
    
    # Validate if posted
    if instance.status == 'POSTED':
        validation = validate_journal_entry(instance)
        
        if not validation['valid']:
            logger.error(
                f"Posted journal entry {instance.entry_number} has validation errors: "
                f"{', '.join(validation['errors'])}"
            )
            # Note: We log but don't raise exception here since entry is already saved
            # Validation should happen in views/forms before posting
        
        if not validation['balanced']:
            logger.error(
                f"Posted journal entry {instance.entry_number} is not balanced! "
                f"Debits: {validation['debit_total']}, Credits: {validation['credit_total']}"
            )


@receiver(pre_delete, sender=JournalEntry)
def journal_entry_pre_delete(sender, instance, **kwargs):
    """
    Pre-delete processing for journal entries:
    - Prevent deletion of posted entries
    """
    if instance.status == 'POSTED':
        raise ValidationError(
            f"Cannot delete posted journal entry {instance.entry_number}. "
            f"Reverse the entry instead."
        )
    
    logger.info(f"Deleting journal entry: {instance.entry_number}")


# =============================================================================
# JOURNAL TRANSACTION SIGNALS
# =============================================================================

@receiver(post_save, sender=JournalTransaction)
def journal_transaction_post_save(sender, instance, created, **kwargs):
    """
    Post-save processing for journal transactions:
    - Update journal entry totals
    - Log transaction creation
    """
    # Skip if in raw mode
    if kwargs.get('raw', False):
        return
    
    if created:
        logger.debug(
            f"Journal transaction created: Entry {instance.journal_entry.entry_number} - "
            f"Account {instance.account.code} - "
            f"{'Debit' if instance.is_debit else 'Credit'}: {instance.amount}"
        )


@receiver(post_delete, sender=JournalTransaction)
def journal_transaction_post_delete(sender, instance, **kwargs):
    """
    Post-delete processing for journal transactions:
    - Log transaction deletion
    """
    logger.debug(
        f"Journal transaction deleted: Entry {instance.journal_entry.entry_number} - "
        f"Account {instance.account.code}"
    )


@receiver(pre_save, sender=JournalTransaction)
def journal_transaction_pre_save(sender, instance, **kwargs):
    """
    Pre-save processing for journal transactions:
    - Validate account is active and not a header
    - Validate amount is positive
    - Prevent changes to posted entries
    """
    # Validate account
    if not instance.account.is_active:
        raise ValidationError(
            f"Cannot create transaction for inactive account {instance.account.code}"
        )
    
    if instance.account.is_header:
        raise ValidationError(
            f"Cannot create transaction for header account {instance.account.code}. "
            f"Use a child account instead."
        )
    
    # Validate amount
    if instance.amount <= 0:
        raise ValidationError("Transaction amount must be positive")
    
    # Prevent changes to posted entries
    if instance.pk:  # Existing transaction
        if instance.journal_entry.status == 'POSTED':
            raise ValidationError(
                f"Cannot modify transaction in posted journal entry {instance.journal_entry.entry_number}"
            )


@receiver(pre_delete, sender=JournalTransaction)
def journal_transaction_pre_delete(sender, instance, **kwargs):
    """
    Pre-delete processing for journal transactions:
    - Prevent deletion from posted entries
    """
    if instance.journal_entry.status == 'POSTED':
        raise ValidationError(
            f"Cannot delete transaction from posted journal entry {instance.journal_entry.entry_number}"
        )


# =============================================================================
# EXPENSE SIGNALS
# =============================================================================

@receiver(pre_save, sender=Expense)
def expense_pre_save(sender, instance, **kwargs):
    """
    Pre-save processing for expenses:
    - Auto-generate expense number
    - Set fiscal period if not set
    - Validate fiscal period
    """
    # Generate expense number if not set
    if not instance.expense_number:
        instance.expense_number = generate_expense_number()
        logger.info(f"Generated expense number: {instance.expense_number}")
    
    # Set fiscal period if not set
    if not instance.fiscal_period:
        from core.models import FiscalPeriod
        instance.fiscal_period = FiscalPeriod.get_current_fiscal_period()
        if not instance.fiscal_period:
            logger.warning(f"No active fiscal period found for expense {instance.expense_number}")
    
    # Validate fiscal period
    if instance.fiscal_period:
        validation = validate_fiscal_period(instance.fiscal_period)
        if not validation['valid']:
            raise ValidationError(
                f"Cannot create expense in closed fiscal period: {', '.join(validation['errors'])}"
            )


@receiver(post_save, sender=Expense)
def expense_post_save(sender, instance, created, **kwargs):
    """
    Post-save processing for expenses:
    - Create journal entry if approved
    - Update budget if linked
    - Log expense creation
    """
    # Skip if in raw mode
    if kwargs.get('raw', False):
        return
    
    if created:
        logger.info(
            f"Expense created: {instance.expense_number} - "
            f"Amount: {instance.amount} - "
            f"Vendor: {instance.vendor_name}"
        )
    
    # Create journal entry if approved and not already created
    if instance.status == 'APPROVED' and not instance.journal_entry:
        try:
            create_expense_journal_entry(instance)
        except Exception as e:
            logger.error(f"Error creating journal entry for expense: {e}", exc_info=True)
    
    # Update budget spent amount if linked
    if instance.budget:
        try:
            update_budget_spent_amount(instance.budget)
        except Exception as e:
            logger.error(f"Error updating budget: {e}", exc_info=True)


def create_expense_journal_entry(expense):
    """
    Create journal entry for an approved expense.
    
    Entry:
    Debit: Expense Account
    Credit: Cash/Bank or Accounts Payable
    """
    from core.models import FinancialSettings
    
    # Get default accounts
    settings = FinancialSettings.get_instance()
    if not settings:
        logger.warning("FinancialSettings not found, skipping journal entry creation")
        return
    
    # Determine credit account based on payment status
    if expense.payment_status == 'PAID':
        # Use cash or bank account
        if hasattr(expense, 'payment_method') and expense.payment_method:
            if hasattr(expense.payment_method, 'is_cash') and expense.payment_method.is_cash:
                credit_account = settings.default_cash_account
            else:
                credit_account = settings.default_bank_account
        else:
            credit_account = settings.default_cash_account
    else:
        # Use accounts payable
        credit_account = settings.default_payables_account
    
    if not credit_account:
        logger.warning("No credit account found for expense journal entry")
        return
    
    # Get or create journal
    from finance.models import Journal
    journal, _ = Journal.objects.get_or_create(
        journal_type='EXPENSE',
        defaults={
            'name': 'Expense Journal',
            'description': 'Journal for expense transactions'
        }
    )
    
    # Create journal entry
    entry = JournalEntry.objects.create(
        journal=journal,
        entry_number=f"JE-EXP-{expense.expense_number}",
        entry_date=expense.expense_date,
        fiscal_period=expense.fiscal_period,
        academic_session=expense.academic_session,
        reference_number=expense.expense_number,
        description=f"Expense: {expense.description or expense.vendor_name}",
        status='POSTED'
    )
    
    # Debit: Expense Account
    JournalTransaction.objects.create(
        journal_entry=entry,
        account=expense.expense_account,
        description=f"Expense - {expense.vendor_name}",
        amount=expense.amount,
        is_debit=True
    )
    
    # Credit: Cash/Bank or Accounts Payable
    JournalTransaction.objects.create(
        journal_entry=entry,
        account=credit_account,
        description=f"Payment for expense {expense.expense_number}",
        amount=expense.amount,
        is_debit=False
    )
    
    # Link entry to expense
    expense.journal_entry = entry
    expense.save()
    
    logger.info(f"Created journal entry {entry.entry_number} for expense {expense.expense_number}")


def update_budget_spent_amount(budget):
    """
    Update budget's spent amount from linked expenses.
    """
    from django.db.models import Sum
    
    # Get all approved expenses for this budget
    total_spent = Expense.objects.filter(
        budget=budget,
        status__in=['APPROVED', 'PAID']
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    budget.spent_amount = total_spent
    budget.remaining_amount = budget.allocated_amount - total_spent
    budget.save(update_fields=['spent_amount', 'remaining_amount'])
    
    logger.debug(f"Updated budget {budget.budget_code}: Spent {total_spent}")


# =============================================================================
# BUDGET SIGNALS
# =============================================================================

@receiver(pre_save, sender=Budget)
def budget_pre_save(sender, instance, **kwargs):
    """
    Pre-save processing for budgets:
    - Calculate remaining amount
    - Validate allocated amount is positive
    """
    # Calculate remaining amount
    instance.remaining_amount = instance.allocated_amount - instance.spent_amount
    
    # Validate allocated amount
    if instance.allocated_amount < 0:
        raise ValidationError("Budget allocated amount cannot be negative")


@receiver(post_save, sender=Budget)
def budget_post_save(sender, instance, created, **kwargs):
    """
    Post-save processing for budgets:
    - Log budget creation
    - Check for over-budget warnings
    """
    # Skip if in raw mode
    if kwargs.get('raw', False):
        return
    
    if created:
        logger.info(
            f"Budget created: {instance.budget_code} - "
            f"Allocated: {instance.allocated_amount} - "
            f"Fiscal Year: {instance.fiscal_year.year}"
        )
    
    # Check for over-budget
    if instance.spent_amount > instance.allocated_amount:
        logger.warning(
            f"BUDGET ALERT: Budget {instance.budget_code} is over budget! "
            f"Allocated: {instance.allocated_amount}, Spent: {instance.spent_amount}, "
            f"Over by: {instance.spent_amount - instance.allocated_amount}"
        )


# =============================================================================
# ACCOUNT SIGNALS
# =============================================================================

@receiver(pre_save, sender=Account)
def account_pre_save(sender, instance, **kwargs):
    """
    Pre-save processing for accounts:
    - Validate account code uniqueness
    - Validate parent account relationships
    - Ensure header accounts have children
    """
    # Validate parent account
    if instance.parent_account:
        # Prevent circular references
        if instance.pk and instance.parent_account == instance:
            raise ValidationError("Account cannot be its own parent")
        
        # Check for circular reference in hierarchy
        parent = instance.parent_account
        while parent:
            if parent == instance:
                raise ValidationError("Circular reference detected in account hierarchy")
            parent = parent.parent_account
        
        # Parent and child must be same account type
        if instance.account_type != instance.parent_account.account_type:
            raise ValidationError(
                "Child account must have the same account type as parent"
            )


@receiver(post_save, sender=Account)
def account_post_save(sender, instance, created, **kwargs):
    """
    Post-save processing for accounts:
    - Log account creation
    """
    # Skip if in raw mode
    if kwargs.get('raw', False):
        return
    
    if created:
        logger.info(
            f"Account created: {instance.code} - {instance.name} - "
            f"Type: {instance.account_type.code}"
        )


@receiver(pre_delete, sender=Account)
def account_pre_delete(sender, instance, **kwargs):
    """
    Pre-delete processing for accounts:
    - Prevent deletion of accounts with transactions
    - Prevent deletion of accounts with children
    """
    # Check for transactions
    if instance.journal_transactions.exists():
        raise ValidationError(
            f"Cannot delete account {instance.code} because it has transactions. "
            f"Deactivate it instead."
        )
    
    # Check for child accounts
    if Account.objects.filter(parent_account=instance).exists():
        raise ValidationError(
            f"Cannot delete account {instance.code} because it has child accounts"
        )
    
    logger.info(f"Deleting account: {instance.code} - {instance.name}")


# =============================================================================
# AUDIT LOGGING
# =============================================================================

@receiver(post_save, sender=JournalEntry)
def log_journal_entry_status_change(sender, instance, created, **kwargs):
    """Log important journal entry status changes"""
    # Skip if in raw mode
    if kwargs.get('raw', False):
        return
    
    if not created and hasattr(instance, '_previous_status'):
        if instance._previous_status != instance.status:
            logger.info(
                f"AUDIT: Journal entry status changed - {instance.entry_number} - "
                f"From: {instance._previous_status} To: {instance.status}"
            )
            
            # Log reversal
            if instance.status == 'REVERSED':
                logger.info(
                    f"AUDIT: Journal entry reversed - {instance.entry_number} - "
                    f"Reason: {instance.reversal_reason or 'Not specified'}"
                )


@receiver(pre_save, sender=JournalEntry)
def store_previous_journal_entry_status(sender, instance, **kwargs):
    """Store previous status for comparison"""
    if instance.pk:
        try:
            previous = JournalEntry.objects.get(pk=instance.pk)
            instance._previous_status = previous.status
        except JournalEntry.DoesNotExist:
            instance._previous_status = None


@receiver(post_save, sender=Expense)
def log_expense_status_change(sender, instance, created, **kwargs):
    """Log important expense status changes"""
    # Skip if in raw mode
    if kwargs.get('raw', False):
        return
    
    if not created and hasattr(instance, '_previous_status'):
        if instance._previous_status != instance.status:
            logger.info(
                f"AUDIT: Expense status changed - {instance.expense_number} - "
                f"From: {instance._previous_status} To: {instance.status}"
            )


@receiver(pre_save, sender=Expense)
def store_previous_expense_status(sender, instance, **kwargs):
    """Store previous status for comparison"""
    if instance.pk:
        try:
            previous = Expense.objects.get(pk=instance.pk)
            instance._previous_status = previous.status
        except Expense.DoesNotExist:
            instance._previous_status = None


# =============================================================================
# REVERSAL HANDLING
# =============================================================================

@receiver(post_save, sender=JournalEntry)
def handle_journal_entry_reversal(sender, instance, created, **kwargs):
    """
    Handle journal entry reversal - mark original as reversed.
    """
    # Skip if in raw mode
    if kwargs.get('raw', False):
        return
    
    # If this is a reversal entry, mark the original as reversed
    if instance.original_entry and instance.original_entry.status != 'REVERSED':
        instance.original_entry.status = 'REVERSED'
        instance.original_entry.reversed_at = timezone.now()
        instance.original_entry.save(update_fields=['status', 'reversed_at'])
        
        logger.info(
            f"Marked journal entry {instance.original_entry.entry_number} as reversed "
            f"by {instance.entry_number}"
        )


# =============================================================================
# DATA INTEGRITY SIGNALS
# =============================================================================

@receiver(pre_save, sender=JournalTransaction)
def prevent_transaction_account_change(sender, instance, **kwargs):
    """
    Prevent changing the account on an existing transaction.
    This maintains audit trail integrity.
    """
    if instance.pk:  # Existing transaction
        try:
            previous = JournalTransaction.objects.get(pk=instance.pk)
            if previous.account != instance.account:
                raise ValidationError(
                    "Cannot change account on existing transaction. "
                    "Delete and create a new transaction instead."
                )
        except JournalTransaction.DoesNotExist:
            pass


# =============================================================================
# SIGNAL TOGGLING (for bulk operations)
# =============================================================================

def disable_finance_signals():
    """
    Disable finance signals temporarily.
    Useful for bulk operations to improve performance.
    """
    from django.db.models import signals
    
    signals.post_save.disconnect(journal_entry_post_save, sender=JournalEntry)
    signals.post_save.disconnect(journal_transaction_post_save, sender=JournalTransaction)
    signals.post_save.disconnect(expense_post_save, sender=Expense)
    signals.post_save.disconnect(budget_post_save, sender=Budget)
    
    logger.info("Finance signals disabled")


def enable_finance_signals():
    """
    Re-enable finance signals after bulk operations.
    """
    import importlib
    import sys
    
    if 'finance.signals' in sys.modules:
        importlib.reload(sys.modules['finance.signals'])
    
    logger.info("Finance signals re-enabled")