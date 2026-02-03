# finance/signals.py

"""
Finance Management Signals

Automatic triggers for:
- Journal entry number generation
- Expense number generation
- Account balance updates (AUTOMATIC BALANCE TRACKING)
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
    generate_journal_entry_number, 
    generate_expense_number,
    validate_journal_entry, 
    validate_fiscal_period,
    update_journal_entry_accounts
)

logger = logging.getLogger(__name__)


# =============================================================================
# JOURNAL ENTRY SIGNALS - COMBINED AND CORRECTED
# =============================================================================

@receiver(pre_save, sender=JournalEntry)
def journal_entry_pre_save(sender, instance, **kwargs):
    """
    Pre-save processing for journal entries:
    - Track previous status for detecting transitions
    - Auto-generate entry number
    - Set fiscal period if not set
    - Validate entry date is in open period
    - Set posted date when posting
    """
    # Track previous status for post_save signal
    if instance.pk:  # Only for existing entries
        try:
            old_instance = JournalEntry.objects.get(pk=instance.pk)
            instance._previous_status = old_instance.status
        except JournalEntry.DoesNotExist:
            instance._previous_status = None
    else:
        instance._previous_status = None
    
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
    1. Log creation
    2. Validate when posted
    3. Update account balances when status transitions occur
    
    Status Transitions Handled:
    - Created as POSTED: Update balances (from payment signals)
    - DRAFT → POSTED: Update balances
    - POSTED → REVERSED: Update balances (recalculate without this entry)
    """
    # Skip if in raw mode (fixtures, loaddata)
    if kwargs.get('raw', False):
        return
    
    # Get previous status (set by pre_save signal)
    previous_status = getattr(instance, '_previous_status', None)
    current_status = instance.status
    
    # =========================================================================
    # 1. LOG CREATION
    # =========================================================================
    if created:
        logger.info(
            f"Journal entry created: {instance.entry_number} - "
            f"Date: {instance.entry_date} - "
            f"Status: {instance.status} - "
            f"Description: {instance.description[:50]}"
        )
    
    # =========================================================================
    # 2. DETERMINE IF BALANCE UPDATE NEEDED
    # =========================================================================
    should_update_balances = False
    action = None
    
    if created and current_status == 'POSTED':
        # Entry created directly as POSTED (common from payment signals)
        should_update_balances = True
        action = 'CREATED_AS_POSTED'
    
    elif not created and previous_status != current_status:
        # Status changed
        if previous_status == 'DRAFT' and current_status == 'POSTED':
            should_update_balances = True
            action = 'POSTED'
        
        elif previous_status == 'POSTED' and current_status == 'REVERSED':
            should_update_balances = True
            action = 'REVERSED'
    
    # =========================================================================
    # 3. VALIDATE AND UPDATE BALANCES
    # =========================================================================
    if should_update_balances:
        
        # Validate entry before updating balances
        if current_status == 'POSTED':
            validation = validate_journal_entry(instance)
            
            if not validation['valid'] or not validation['balanced']:
                # Log critical errors
                errors = []
                if not validation['valid']:
                    errors.extend(validation['errors'])
                if not validation['balanced']:
                    errors.append(
                        f"Entry not balanced! Debits: {validation['debit_total']}, "
                        f"Credits: {validation['credit_total']}"
                    )
                
                logger.error(
                    f"CRITICAL: Posted journal entry {instance.entry_number} "
                    f"has validation errors: {', '.join(errors)}"
                )
                
                # Don't update balances for invalid entries
                return
        
        # Update account balances
        try:
            results = update_journal_entry_accounts(instance)
            
            logger.info(
                f"✓ Updated {len(results)} account balances: "
                f"Entry {instance.entry_number} - Action: {action} "
                f"({previous_status or 'NEW'} → {current_status})"
            )
            
            # Detailed logging in debug mode
            if logger.isEnabledFor(logging.DEBUG):
                for account_number, data in results.items():
                    logger.debug(
                        f"  - {account_number}: "
                        f"{data['old_balance']:,.2f} → {data['new_balance']:,.2f} "
                        f"(Δ {data['change']:+,.2f})"
                    )
        
        except Exception as e:
            logger.error(
                f"Error updating account balances for entry {instance.entry_number}: {e}",
                exc_info=True
            )
            # Don't re-raise - we don't want to block the save
            # Balances can be recalculated later if needed
    
    # =========================================================================
    # 4. LOG REVERSALS
    # =========================================================================
    if current_status == 'REVERSED' and not created:
        logger.info(
            f"Journal entry reversed: {instance.entry_number} - "
            f"Reason: {instance.reversal_reason}"
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
            f"Cannot create transaction for inactive account {instance.account.account_number}"
        )
    
    if instance.account.is_header:
        raise ValidationError(
            f"Cannot create transaction for header account {instance.account.account_number}. "
            f"Use a child account instead."
        )
    
    # Validate amount
    if instance.amount <= 0:
        raise ValidationError("Transaction amount must be positive")
    
    # Only prevent changes to EXISTING transactions in posted entries
    if instance.pk:  # Only check for existing transactions
        try:
            previous = JournalTransaction.objects.get(pk=instance.pk)
            # Check if trying to modify an existing transaction in a posted entry
            if previous.journal_entry.status == 'POSTED':
                raise ValidationError(
                    f"Cannot modify transaction in posted journal entry {instance.journal_entry.entry_number}"
                )
        except JournalTransaction.DoesNotExist:
            # Transaction doesn't exist yet, allow creation
            pass


@receiver(post_save, sender=JournalTransaction)
def journal_transaction_post_save(sender, instance, created, **kwargs):
    """
    Post-save processing for journal transactions:
    - Log transaction creation
    """
    # Skip if in raw mode
    if kwargs.get('raw', False):
        return
    
    if created:
        logger.debug(
            f"Journal transaction created: Entry {instance.journal_entry.entry_number} - "
            f"Account {instance.account.account_number} - "
            f"{'Debit' if instance.is_debit else 'Credit'}: {instance.amount}"
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


@receiver(post_delete, sender=JournalTransaction)
def journal_transaction_post_delete(sender, instance, **kwargs):
    """
    Post-delete processing for journal transactions:
    - Log transaction deletion
    """
    logger.debug(
        f"Journal transaction deleted: Entry {instance.journal_entry.entry_number} - "
        f"Account {instance.account.account_number}"
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
            f"Amount: {instance.total_amount} - "
            f"Vendor: {instance.vendor_name}"
        )
    
    # Create journal entry if approved and auto-create is enabled
    if instance.status == 'APPROVED' and instance.auto_create_journal_entry and not instance.journal_entry:
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
    Credit: Accounts Payable
    """
    from core.models import FinancialSettings
    
    # Get default accounts
    settings = FinancialSettings.get_instance()
    if not settings:
        logger.warning("FinancialSettings not found, skipping journal entry creation")
        return
    
    # Get payable account from expense method
    payable_account = expense.get_payable_account()
    
    if not payable_account:
        logger.warning("No payable account found for expense journal entry")
        return
    
    # Get or create journal
    from finance.models import Journal, JournalTransaction
    journal, _ = Journal.objects.get_or_create(
        journal_type='EXPENSES',
        defaults={
            'name': 'Expense Journal',
            'description': 'Journal for expense transactions'
        }
    )
    
    # Create journal entry as DRAFT first
    entry = JournalEntry.objects.create(
        journal=journal,
        entry_date=expense.expense_date,
        fiscal_period=expense.fiscal_period,
        academic_session=expense.academic_session,
        reference_number=expense.expense_number,
        description=f"Expense: {expense.description or expense.vendor_name}",
        status='DRAFT'
    )
    
    # Debit: Expense Account
    JournalTransaction.objects.create(
        journal_entry=entry,
        account=expense.expense_account,
        description=f"Expense - {expense.vendor_name}",
        amount=expense.total_amount,
        is_debit=True
    )
    
    # Credit: Accounts Payable
    JournalTransaction.objects.create(
        journal_entry=entry,
        account=payable_account,
        description=f"Payable for expense {expense.expense_number}",
        amount=expense.total_amount,
        is_debit=False
    )
    
    # Now post the entry after transactions are added
    # This will trigger the balance update signals
    entry.status = 'POSTED'
    entry.posted_at = timezone.now()
    entry.save(update_fields=['status', 'posted_at'])
    
    # Link entry to expense
    expense.journal_entry = entry
    expense.save(update_fields=['journal_entry'])
    
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
    ).aggregate(total=Sum('total_amount'))['total'] or 0
    
    budget.actual_expense_total = total_spent
    budget.save(update_fields=['actual_expense_total'])
    
    logger.debug(f"Updated budget {budget.name}: Spent {total_spent}")


# =============================================================================
# BUDGET SIGNALS
# =============================================================================

@receiver(pre_save, sender=Budget)
def budget_pre_save(sender, instance, **kwargs):
    """
    Pre-save processing for budgets:
    - Calculate net budget
    - Validate amounts
    """
    # Calculate net budget
    instance.net_budget = instance.total_revenue_budget - instance.total_expense_budget
    
    # Validate amounts
    if instance.total_revenue_budget < 0:
        raise ValidationError("Budget revenue cannot be negative")
    
    if instance.total_expense_budget < 0:
        raise ValidationError("Budget expenses cannot be negative")


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
            f"Budget created: {instance.name} - "
            f"Revenue: {instance.total_revenue_budget} - "
            f"Expenses: {instance.total_expense_budget} - "
            f"Fiscal Year: {instance.fiscal_year.name if instance.fiscal_year else 'N/A'}"
        )
    
    # Check for over-budget on expenses
    if instance.actual_expense_total > instance.total_expense_budget:
        logger.warning(
            f"BUDGET ALERT: Budget {instance.name} is over budget on expenses! "
            f"Budgeted: {instance.total_expense_budget}, "
            f"Actual: {instance.actual_expense_total}, "
            f"Over by: {instance.actual_expense_total - instance.total_expense_budget}"
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
        max_depth = 10  # Prevent infinite loop
        depth = 0
        while parent and depth < max_depth:
            if parent.pk == instance.pk:
                raise ValidationError("Circular reference detected in account hierarchy")
            parent = parent.parent_account
            depth += 1
        
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
            f"Account created: {instance.account_number} - {instance.name} - "
            f"Type: {instance.account_type.name}"
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
            f"Cannot delete account {instance.account_number} because it has transactions. "
            f"Deactivate it instead."
        )
    
    # Check for child accounts
    if Account.objects.filter(parent_account=instance).exists():
        raise ValidationError(
            f"Cannot delete account {instance.account_number} because it has child accounts"
        )
    
    logger.info(f"Deleting account: {instance.account_number} - {instance.name}")


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
    
    Example:
        >>> from finance.signals import disable_finance_signals, enable_finance_signals
        >>> disable_finance_signals()
        >>> # ... bulk import operations ...
        >>> enable_finance_signals()
    """
    from django.db.models import signals

    # Reconnect JournalEntry signals
    signals.pre_save.connect(journal_entry_pre_save, sender=JournalEntry)
    signals.post_save.connect(journal_entry_post_save, sender=JournalEntry)
    signals.pre_delete.connect(journal_entry_pre_delete, sender=JournalEntry)
    
    # Reconnect JournalTransaction signals
    signals.pre_save.connect(journal_transaction_pre_save, sender=JournalTransaction)
    signals.post_save.connect(journal_transaction_post_save, sender=JournalTransaction)
    signals.pre_delete.connect(journal_transaction_pre_delete, sender=JournalTransaction)
    
    # Reconnect Expense signals 
    signals.pre_save.connect(expense_pre_save, sender=Expense)
    signals.post_save.connect(expense_post_save, sender=Expense) 
    
    # Reconnect Budget signals 
    signals.post_save.connect(budget_post_save, sender=Budget)
    
    logger.info("Finance signals disabled")


def enable_finance_signals():
    """
    Re-enable finance signals after bulk operations.
    
    Example:
        >>> from finance.signals import disable_finance_signals, enable_finance_signals
        >>> disable_finance_signals()
        >>> # ... bulk import operations ...
        >>> enable_finance_signals()
        >>> 
        >>> # Then recalculate balances
        >>> from finance.utils import recalculate_all_account_balances
        >>> recalculate_all_account_balances()
    """
    import importlib
    import sys
    
    # Reload the signals module to reconnect all signals
    if 'finance.signals' in sys.modules:
        importlib.reload(sys.modules['finance.signals'])
    
    logger.info("Finance signals re-enabled")


