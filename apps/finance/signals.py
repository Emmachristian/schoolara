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
    JournalEntry, JournalTransaction, Expense, ExpensePayment,
    Budget, Account
)
from finance.utils import (
    generate_journal_entry_number,
    generate_expense_number,
    generate_payment_reference_number,
    validate_journal_entry,
    validate_fiscal_period,
    update_journal_entry_accounts
)

logger = logging.getLogger(__name__)


def _get_period_for_date(date):
    """
    Resolve the fiscal period for a given date.
    FiscalPeriod lives in core.models (confirmed via core/utils.py).
    Uses FiscalPeriod.get_period_for_date() when available (fiscal_period_patch.py).
    Falls back to a direct query so the signal works without the model patch.
    """
    if date is None:
        return None
    from core.models import FiscalPeriod
    if hasattr(FiscalPeriod, 'get_period_for_date'):
        return FiscalPeriod.get_period_for_date(date)
    return (
        FiscalPeriod.objects.filter(
            start_date__lte=date,
            end_date__gte=date,
            is_closed=False,
            is_locked=False,
        ).order_by('-is_active', 'period_number').first()
        or
        FiscalPeriod.objects.filter(
            start_date__lte=date,
            end_date__gte=date,
        ).order_by('-is_active', 'period_number').first()
    )


# =============================================================================
# JOURNAL ENTRY SIGNALS
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
    if instance.pk:
        try:
            old_instance = JournalEntry.objects.get(pk=instance.pk)
            instance._previous_status = old_instance.status
        except JournalEntry.DoesNotExist:
            instance._previous_status = None
    else:
        instance._previous_status = None

    if not instance.entry_number:
        instance.entry_number = generate_journal_entry_number(instance.journal)
        logger.info(f"Generated journal entry number: {instance.entry_number}")

    if not instance.fiscal_period:
        from core.models import FiscalPeriod
        instance.fiscal_period = FiscalPeriod.get_current_fiscal_period()
        if not instance.fiscal_period:
            logger.warning(f"No active fiscal period found for journal entry {instance.entry_number}")

    if instance.status == 'POSTED' and instance.fiscal_period:
        validation = validate_fiscal_period(instance.fiscal_period)
        if not validation['valid']:
            raise ValidationError(
                f"Cannot post journal entry to closed fiscal period: {', '.join(validation['errors'])}"
            )

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
    - Created as POSTED: Skip — transactions not yet attached
    - DRAFT → POSTED: Update balances
    - POSTED → REVERSED: Update balances (recalculate without this entry)
    """
    if kwargs.get('raw', False):
        return

    previous_status = getattr(instance, '_previous_status', None)
    current_status  = instance.status

    if created:
        logger.info(
            f"Journal entry created: {instance.entry_number} - "
            f"Date: {instance.entry_date} - "
            f"Status: {instance.status} - "
            f"Description: {instance.description[:50]}"
        )

    should_update_balances = False
    action = None

    if created and current_status == 'POSTED':
        should_update_balances = True
        action = 'CREATED_AS_POSTED'
    elif not created and previous_status != current_status:
        if previous_status == 'DRAFT' and current_status == 'POSTED':
            should_update_balances = True
            action = 'POSTED'
        elif previous_status == 'POSTED' and current_status == 'REVERSED':
            should_update_balances = True
            action = 'REVERSED'

    if should_update_balances:

        # Skip when JE is brand new — transactions haven't been added yet.
        # The finalize view creates the JE first, then adds JournalTransactions,
        # then posts it. Balance update will happen correctly on the
        # DRAFT → POSTED transition which fires after transactions exist.
        if created:
            logger.debug(
                f"Skipping balance update for newly created JE "
                f"{instance.entry_number} — transactions not yet attached"
            )
            return

        if current_status == 'POSTED':
            validation = validate_journal_entry(instance)
            if not validation['valid'] or not validation['balanced']:
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
                return

        try:
            results = update_journal_entry_accounts(instance)
            logger.info(
                f"✓ Updated {len(results)} account balances: "
                f"Entry {instance.entry_number} - Action: {action} "
                f"({previous_status or 'NEW'} → {current_status})"
            )
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
                exc_info=True,
            )

    if current_status == 'REVERSED' and not created:
        logger.info(
            f"Journal entry reversed: {instance.entry_number} - "
            f"Reason: {instance.reversal_reason}"
        )


@receiver(pre_delete, sender=JournalEntry)
def journal_entry_pre_delete(sender, instance, **kwargs):
    """Prevent deletion of posted entries."""
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
    if not instance.account.is_active:
        raise ValidationError(
            f"Cannot create transaction for inactive account {instance.account.account_number}"
        )

    if instance.account.is_header:
        raise ValidationError(
            f"Cannot create transaction for header account {instance.account.account_number}. "
            f"Use a child account instead."
        )

    if instance.amount <= 0:
        raise ValidationError("Transaction amount must be positive")

    if instance.pk:
        try:
            previous = JournalTransaction.objects.get(pk=instance.pk)
            if previous.journal_entry.status == 'POSTED':
                raise ValidationError(
                    f"Cannot modify transaction in posted journal entry "
                    f"{instance.journal_entry.entry_number}"
                )
        except JournalTransaction.DoesNotExist:
            pass


@receiver(post_save, sender=JournalTransaction)
def journal_transaction_post_save(sender, instance, created, **kwargs):
    """Log transaction creation."""
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
    """Prevent deletion from posted entries."""
    if instance.journal_entry.status == 'POSTED':
        raise ValidationError(
            f"Cannot delete transaction from posted journal entry "
            f"{instance.journal_entry.entry_number}"
        )


@receiver(post_delete, sender=JournalTransaction)
def journal_transaction_post_delete(sender, instance, **kwargs):
    logger.debug(
        f"Journal transaction deleted: Entry {instance.journal_entry.entry_number} - "
        f"Account {instance.account.account_number}"
    )


# =============================================================================
# EXPENSE SIGNALS
# =============================================================================

@receiver(pre_save, sender=Expense)
def store_previous_expense_status(sender, instance, **kwargs):
    """Store previous status before save for audit logging."""
    if instance.pk:
        try:
            instance._previous_status = Expense.objects.get(pk=instance.pk).status
        except Expense.DoesNotExist:
            instance._previous_status = None


@receiver(pre_save, sender=Expense)
def expense_pre_save(sender, instance, **kwargs):
    if not instance.expense_number:
        instance.expense_number = generate_expense_number()
        logger.info(f"Generated expense number: {instance.expense_number}")

    # Auto-set expense date if not supplied
    if not instance.expense_date:
        from core.utils import get_school_today
        instance.expense_date = get_school_today()
        logger.info(
            f"Auto-set expense date to {instance.expense_date} "
            f"for expense {instance.expense_number}"
        )

    if not instance.fiscal_period:
        from core.models import FiscalPeriod
        from core.utils import get_school_today

        date = instance.expense_date or get_school_today()

        # SchoolRouter routes these queries to the correct school DB automatically
        period = (
            FiscalPeriod.objects.filter(
                start_date__lte=date,
                end_date__gte=date,
                is_closed=False,
                is_locked=False,
            ).order_by('-is_active', 'period_number').first()
            or
            FiscalPeriod.objects.filter(
                start_date__lte=date,
                end_date__gte=date,
            ).order_by('-is_active', 'period_number').first()
        )

        if period is None:
            period = FiscalPeriod.objects.filter(
                is_active=True, is_closed=False, is_locked=False,
            ).order_by('period_number').first()

        if period is None:
            period = FiscalPeriod.objects.filter(
                is_locked=False,
            ).order_by('-is_active', '-end_date').first()

        if period is None:
            raise ValidationError(
                "No fiscal period found. Please create and activate a fiscal "
                "period in Finance → Fiscal Periods before recording expenses."
            )
        instance.fiscal_period = period

    if instance.fiscal_period:
        validation = validate_fiscal_period(instance.fiscal_period)
        if not validation['valid']:
            raise ValidationError(
                f"Cannot create expense in closed fiscal period: "
                f"{', '.join(validation['errors'])}"
            )


@receiver(post_save, sender=Expense)
def expense_post_save(sender, instance, created, **kwargs):
    """
    Post-save processing for expenses:
    - Create journal entry if approved
    - Update budget actuals if a budget line is linked
    - Log creation and status changes
    """
    if kwargs.get('raw', False):
        return

    if created:
        logger.info(
            f"Expense created: {instance.expense_number} - "
            f"Amount: {instance.total_amount} - "
            # FIX: was instance.vendor_name — field renamed to payee_name
            f"Payee: {instance.payee_name}"
        )

    # FIX: removed auto_create_journal_entry guard — field was removed from
    # the model. Journal entry creation is now unconditional on approval.
    if instance.status == 'APPROVED' and not instance.journal_entry:
        try:
            create_expense_journal_entry(instance)
        except Exception as e:
            logger.error(
                f"Error creating journal entry for expense {instance.expense_number}: {e}",
                exc_info=True
            )

    # Access the parent Budget via budget_line.budget (Expense has no direct budget FK)
    if instance.budget_line_id:
        try:
            update_budget_spent_amount(instance.budget_line.budget)
        except Exception as e:
            logger.error(
                f"Error updating budget for expense {instance.expense_number}: {e}",
                exc_info=True
            )


# expense_line_pre_save REMOVED.
# ExpenseLine no longer carries its own expense_account FK.
# All lines within an expense belong to the same category, so the GL account
# is resolved once at the Expense level via Expense.get_expense_account()
# (checks expense.expense_account → category.default_expense_account →
# FinancialSettings fallback). That account is what posts to the journal —
# see create_expense_journal_entry() in this file.


@receiver(post_save, sender=Expense)
def log_expense_status_change(sender, instance, created, **kwargs):
    """Log important expense status changes."""
    if kwargs.get('raw', False):
        return
    if not created and hasattr(instance, '_previous_status'):
        if instance._previous_status != instance.status:
            logger.info(
                f"AUDIT: Expense status changed - {instance.expense_number} - "
                f"From: {instance._previous_status} To: {instance.status}"
            )


def create_expense_journal_entry(expense):
    """
    Create a journal entry for an approved expense.

    Entry:
      Debit:  Expense Account   (expense incurred)
      Credit: Accounts Payable  (obligation to pay)
    """
    from core.models import FinancialSettings

    settings = FinancialSettings.get_instance()
    if not settings:
        logger.warning(
            "FinancialSettings not found — skipping journal entry creation "
            f"for expense {expense.expense_number}"
        )
        return

    payable_account = expense.get_payable_account()
    if not payable_account:
        logger.warning(
            f"No payable account found — skipping journal entry for {expense.expense_number}"
        )
        return

    expense_account = expense.get_expense_account()
    if not expense_account:
        logger.warning(
            f"No expense account found — skipping journal entry for {expense.expense_number}"
        )
        return

    from finance.models import Journal, JournalTransaction

    journal, _ = Journal.objects.get_or_create(
        journal_type='EXPENSES',
        defaults={
            'name': 'Expense Journal',
            'description': 'Journal for expense transactions',
        }
    )

    # FIX: derive academic_session from fiscal_period — Expense has no direct
    # academic_session FK; it is accessible via fiscal_period.related_academic_session.
    academic_session = getattr(expense.fiscal_period, 'related_academic_session', None)

    # Create as DRAFT first so transactions can be added without triggering
    # the "posted entry" guard in journal_transaction_pre_save
    entry = JournalEntry.objects.create(
        journal=journal,
        entry_date=expense.expense_date,
        fiscal_period=expense.fiscal_period,
        academic_session=academic_session,
        reference_number=expense.expense_number,
        # FIX: was expense.description or expense.vendor_name — vendor_name
        # was replaced by payee_name
        description=f"Expense: {expense.description or expense.payee_name}",
        status='DRAFT',
    )

    JournalTransaction.objects.create(
        journal_entry=entry,
        account=expense_account,
        # FIX: was expense.vendor_name — replaced by payee_name
        description=f"Expense - {expense.payee_name or expense.expense_number}",
        amount=expense.total_amount,
        is_debit=True,
    )

    JournalTransaction.objects.create(
        journal_entry=entry,
        account=payable_account,
        description=f"Payable for {expense.expense_number}",
        amount=expense.total_amount,
        is_debit=False,
    )

    # Post the entry — this triggers balance updates via journal_entry_post_save
    entry.status    = 'POSTED'
    entry.posted_at = timezone.now()
    entry.save(update_fields=['status', 'posted_at'])

    # Link back to expense (use update_fields to avoid re-triggering expense signals)
    Expense.objects.filter(pk=expense.pk).update(journal_entry=entry)
    logger.info(
        f"Created journal entry {entry.entry_number} for expense {expense.expense_number}"
    )


def update_budget_spent_amount(budget):
    """
    Recalculate and save the budget's actual expense total
    from all approved/paid expenses linked to any of its lines.
    """
    from django.db.models import Sum

    # Traverse budget_line → budget, summing across all lines of this budget
    total_spent = Expense.objects.filter(
        budget_line__budget=budget,
        status__in=['APPROVED', 'PAID'],
    ).aggregate(total=Sum('total_amount'))['total'] or 0

    budget.actual_expense_total = total_spent
    budget.save(update_fields=['actual_expense_total'])
    logger.debug(f"Updated budget '{budget.name}': actual_expense_total = {total_spent}")


# =============================================================================
# BUDGET SIGNALS
# =============================================================================

@receiver(pre_save, sender=Budget)
def budget_pre_save(sender, instance, **kwargs):
    """Calculate net budget and validate amounts."""
    instance.net_budget = instance.total_revenue_budget - instance.total_expense_budget

    if instance.total_revenue_budget < 0:
        raise ValidationError("Budget revenue cannot be negative")

    if instance.total_expense_budget < 0:
        raise ValidationError("Budget expenses cannot be negative")


@receiver(post_save, sender=Budget)
def budget_post_save(sender, instance, created, **kwargs):
    """Log budget creation and over-budget warnings."""
    if kwargs.get('raw', False):
        return

    if created:
        logger.info(
            f"Budget created: {instance.name} - "
            f"Revenue: {instance.total_revenue_budget} - "
            f"Expenses: {instance.total_expense_budget} - "
            f"Fiscal Year: {instance.fiscal_year.name if instance.fiscal_year else 'N/A'}"
        )

    if instance.actual_expense_total > instance.total_expense_budget:
        logger.warning(
            f"BUDGET ALERT: Budget '{instance.name}' is over budget on expenses! "
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
    Validate account hierarchy:
    - No self-reference
    - No circular reference
    - Parent and child must share same account type
    """
    if instance.parent_account:
        if instance.pk and instance.parent_account_id == instance.pk:
            raise ValidationError("Account cannot be its own parent")

        parent = instance.parent_account
        max_depth = 10
        depth = 0
        while parent and depth < max_depth:
            if parent.pk == instance.pk:
                raise ValidationError(
                    "Circular reference detected in account hierarchy"
                )
            parent = parent.parent_account
            depth += 1

        if instance.account_type_id != instance.parent_account.account_type_id:
            raise ValidationError(
                "Child account must have the same account type as parent"
            )


@receiver(post_save, sender=Account)
def account_post_save(sender, instance, created, **kwargs):
    """Log account creation."""
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
    Prevent deletion of accounts that have transactions or child accounts.
    Deactivate instead.
    """
    if instance.journal_transactions.exists():
        raise ValidationError(
            f"Cannot delete account {instance.account_number} because it has transactions. "
            f"Deactivate it instead."
        )

    if Account.objects.filter(parent_account=instance).exists():
        raise ValidationError(
            f"Cannot delete account {instance.account_number} because it has child accounts."
        )

    logger.info(f"Deleting account: {instance.account_number} - {instance.name}")


# =============================================================================
# JOURNAL ENTRY AUDIT SIGNALS
# =============================================================================

@receiver(pre_save, sender=JournalEntry)
def store_previous_journal_entry_status(sender, instance, **kwargs):
    """Store previous status for comparison in post_save."""
    if instance.pk:
        try:
            instance._previous_status = JournalEntry.objects.get(pk=instance.pk).status
        except JournalEntry.DoesNotExist:
            instance._previous_status = None


@receiver(post_save, sender=JournalEntry)
def log_journal_entry_status_change(sender, instance, created, **kwargs):
    """Log important journal entry status changes."""
    if kwargs.get('raw', False):
        return

    if not created and hasattr(instance, '_previous_status'):
        if instance._previous_status != instance.status:
            logger.info(
                f"AUDIT: Journal entry status changed - {instance.entry_number} - "
                f"From: {instance._previous_status} To: {instance.status}"
            )
            if instance.status == 'REVERSED':
                logger.info(
                    f"AUDIT: Journal entry reversed - {instance.entry_number} - "
                    f"Reason: {instance.reversal_reason or 'Not specified'}"
                )


# =============================================================================
# REVERSAL HANDLING
# =============================================================================

@receiver(post_save, sender=JournalEntry)
def handle_journal_entry_reversal(sender, instance, created, **kwargs):
    """
    When a reversal entry is saved, mark the original entry as REVERSED.
    Uses update_fields to avoid re-triggering the full post_save chain.
    """
    if kwargs.get('raw', False):
        return

    if (
        instance.original_entry_id
        and instance.original_entry.status != 'REVERSED'
    ):
        JournalEntry.objects.filter(pk=instance.original_entry_id).update(
            status='REVERSED',
            reversed_at=timezone.now(),
        )
        logger.info(
            f"Marked journal entry {instance.original_entry.entry_number} as reversed "
            f"by {instance.entry_number}"
        )


# =============================================================================
# DATA INTEGRITY
# =============================================================================

@receiver(pre_save, sender=JournalTransaction)
def prevent_transaction_account_change(sender, instance, **kwargs):
    """Prevent changing the account on an existing transaction (audit trail integrity)."""
    if instance.pk:
        try:
            previous = JournalTransaction.objects.get(pk=instance.pk)
            if previous.account_id != instance.account_id:
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
    Disconnect finance signals temporarily for bulk operations.

    Example:
        >>> disable_finance_signals()
        >>> # ... bulk import ...
        >>> enable_finance_signals()
        >>> from finance.utils import recalculate_all_account_balances
        >>> recalculate_all_account_balances()
    """
    from django.db.models import signals

    signals.pre_save.disconnect(journal_entry_pre_save,              sender=JournalEntry)
    signals.pre_save.disconnect(store_previous_journal_entry_status, sender=JournalEntry)
    signals.post_save.disconnect(journal_entry_post_save,            sender=JournalEntry)
    signals.post_save.disconnect(log_journal_entry_status_change,    sender=JournalEntry)
    signals.post_save.disconnect(handle_journal_entry_reversal,      sender=JournalEntry)
    signals.pre_delete.disconnect(journal_entry_pre_delete,          sender=JournalEntry)

    signals.pre_save.disconnect(journal_transaction_pre_save,        sender=JournalTransaction)
    signals.pre_save.disconnect(prevent_transaction_account_change,  sender=JournalTransaction)
    signals.post_save.disconnect(journal_transaction_post_save,      sender=JournalTransaction)
    signals.pre_delete.disconnect(journal_transaction_pre_delete,    sender=JournalTransaction)
    signals.post_delete.disconnect(journal_transaction_post_delete,  sender=JournalTransaction)

    signals.pre_save.disconnect(store_previous_expense_status,       sender=Expense)
    signals.pre_save.disconnect(expense_pre_save,                    sender=Expense)
    signals.post_save.disconnect(expense_post_save,                  sender=Expense)
    signals.post_save.disconnect(log_expense_status_change,          sender=Expense)

    signals.pre_save.disconnect(budget_pre_save,                     sender=Budget)
    signals.post_save.disconnect(budget_post_save,                   sender=Budget)

    signals.pre_save.disconnect(account_pre_save,                    sender=Account)
    signals.post_save.disconnect(account_post_save,                  sender=Account)
    signals.pre_delete.disconnect(account_pre_delete,                sender=Account)

    logger.info("Finance signals disabled")


def enable_finance_signals():
    """
    Reconnect finance signals after bulk operations.

    Example:
        >>> disable_finance_signals()
        >>> # ... bulk import ...
        >>> enable_finance_signals()
        >>> from finance.utils import recalculate_all_account_balances
        >>> recalculate_all_account_balances()
    """
    import importlib
    import sys

    if 'finance.signals' in sys.modules:
        importlib.reload(sys.modules['finance.signals'])

    logger.info("Finance signals re-enabled")


# =============================================================================
# EXPENSE PAYMENT SIGNALS
# =============================================================================

@receiver(pre_save, sender=ExpensePayment)
def payment_pre_save(sender, instance, **kwargs):
    """
    Pre-save processing for expense payments.

    SchoolRouter automatically routes FiscalPeriod queries to the correct
    school database via get_current_db() — no .using() needed here.

    - payment_date  → auto-set to school today (not shown in form)
    - fiscal_period → auto-set from payment_date via router
    """
    # Use _state.adding instead of `if instance.pk`.
    # UUID primary keys are generated before save so instance.pk is already
    # set on new instances — the old check wrongly treated them as edits and
    # returned early, leaving payment_date and fiscal_period unset.
    if not instance._state.adding:
        return

    # ── reference_number ─────────────────────────────────────────────────────
    # Auto-generate a sequential reference if none was provided (e.g. cash
    # payments where the reference field is hidden in the form).
    # Uses generate_payment_reference_number() from finance/utils.py which
    # mirrors generate_expense_number() with select_for_update() + Max()
    # for race-condition safety.
    if not instance.reference_number:
        instance.reference_number = generate_payment_reference_number()

    # ── payment_date ─────────────────────────────────────────────────────────
    if not instance.payment_date:
        from core.utils import get_school_today
        instance.payment_date = get_school_today()

    # ── fiscal_period ─────────────────────────────────────────────────────────
    if not instance.fiscal_period_id and instance.payment_date:
        try:
            from core.models import FiscalPeriod

            # Try 1: period whose date range covers payment_date
            period = (
                FiscalPeriod.objects.filter(
                    start_date__lte=instance.payment_date,
                    end_date__gte=instance.payment_date,
                    is_closed=False,
                    is_locked=False,
                ).order_by('-is_active', 'period_number').first()
                or
                FiscalPeriod.objects.filter(
                    start_date__lte=instance.payment_date,
                    end_date__gte=instance.payment_date,
                ).order_by('-is_active', 'period_number').first()
            )

            # Try 2: any currently active open period
            if period is None:
                period = FiscalPeriod.objects.filter(
                    is_active=True, is_closed=False, is_locked=False,
                ).order_by('period_number').first()

            # Try 3: any non-locked period at all
            if period is None:
                period = FiscalPeriod.objects.filter(
                    is_locked=False,
                ).order_by('-is_active', '-end_date').first()

            if period is None:
                raise ValidationError(
                    "No fiscal period found. Please create and activate a fiscal "
                    "period in Finance → Fiscal Periods before recording payments."
                )

            instance.fiscal_period = period

        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"Could not auto-assign fiscal period for payment: {e}", exc_info=True)
            raise ValidationError(f"Could not determine fiscal period: {e}")