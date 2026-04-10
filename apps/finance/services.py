# finance/services.py

"""
Core Finance Operations

Handles CRUD, payments, approvals, journal entries, and budget operations.

FIXES applied to the original:
- _get_period_for_date: was calling itself recursively instead of
  FiscalPeriod.get_period_for_date(date) — infinite recursion bug
- create_expense_payment_journal_entry: payment.payment_method.is_cash
  → payment.payment_method.method_type == 'CASH'
  (PaymentMethod has no is_cash attribute — use method_type field)
- create_expense: academic_session FK removed from Expense model
- add_expense_line: expense_account, tax_rate, tax_amount removed from ExpenseLine
- approve_expense: auto_create_journal_entry guard removed (field deleted)
- create_expense_journal_entry: expense.academic_session →
  getattr(expense.fiscal_period, 'related_academic_session', None)
- verify_payment: auto_create_journal_entry guard removed
- FiscalPeriod and FiscalYear imported from core.models (not finance.models)
"""

from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from datetime import timedelta
from django.db.models import Sum, Q, F
import logging

from finance.models import (
    Expense, ExpenseCategory, ExpenseLine, ExpensePayment,
    Journal, JournalEntry, JournalTransaction,
    Budget, BudgetLine, Account, PaymentMethod,
)
# FIX: FiscalPeriod and FiscalYear live in core.models
from core.models import FiscalPeriod, FiscalYear, FinancialSettings
from core.utils import get_school_today, get_school_current_time

logger = logging.getLogger(__name__)


def _get_period_for_date(date):
    """
    Resolve the fiscal period for a given date.

    FIX: original called `return _get_period_for_date(date)` (itself) causing
    infinite recursion. Correct call is FiscalPeriod.get_period_for_date(date).

    Falls back to a direct ORM query if the classmethod hasn't been added yet
    (see fiscal_period_patch.py).
    """
    if date is None:
        return None
    if hasattr(FiscalPeriod, 'get_period_for_date'):
        return FiscalPeriod.get_period_for_date(date)   # FIX: was _get_period_for_date(date)
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
# EXPENSE SERVICE
# =============================================================================

class ExpenseService:

    @staticmethod
    @transaction.atomic
    def create_expense(expense_data):
        lines_data = expense_data.pop('lines', [])

        if 'expense_date' not in expense_data:
            expense_data['expense_date'] = get_school_today()

        if isinstance(expense_data.get('category'), int):
            expense_data['category'] = ExpenseCategory.objects.get(pk=expense_data['category'])

        # academic_session FK removed from Expense — do not set it

        if 'fiscal_period' not in expense_data:
            expense_data['fiscal_period'] = _get_period_for_date(expense_data['expense_date'])
        elif isinstance(expense_data.get('fiscal_period'), int):
            expense_data['fiscal_period'] = FiscalPeriod.objects.get(pk=expense_data['fiscal_period'])

        if expense_data.get('preferred_payment_method'):
            if isinstance(expense_data['preferred_payment_method'], str):
                expense_data['preferred_payment_method'] = PaymentMethod.objects.get(
                    code=expense_data['preferred_payment_method']
                )

        category = expense_data['category']

        if not expense_data.get('expense_account'):
            if category.default_expense_account:
                expense_data['expense_account'] = category.default_expense_account
            else:
                settings = FinancialSettings.get_instance()
                if settings:
                    mappings = settings.get_account_mappings()
                    expense_data['expense_account'] = mappings.get_expense_account(category)

        if 'status' not in expense_data:
            expense_data['status'] = 'PENDING_APPROVAL' if category.requires_approval else 'APPROVED'

        if lines_data:
            expense_data['subtotal_amount'] = sum(
                Decimal(str(line.get('amount', 0))) for line in lines_data
            )
        elif 'subtotal_amount' not in expense_data:
            expense_data['subtotal_amount'] = expense_data.get('total_amount', Decimal('0.00'))

        if 'tax_amount' not in expense_data:
            expense_data['tax_amount'] = Decimal('0.00')

        expense = Expense.objects.create(**expense_data)

        for line_data in lines_data:
            ExpenseService.add_expense_line(expense, line_data)

        logger.info(
            f"Created expense {expense.expense_number} for {expense.description} "
            f"(amount: {expense.total_amount}, status: {expense.status})"
        )
        return expense

    @staticmethod
    @transaction.atomic
    def add_expense_line(expense, line_data):
        """
        FIX: expense_account, tax_rate, tax_amount removed from ExpenseLine.
        Account resolved at Expense level via get_expense_account().
        """
        if 'quantity' not in line_data:
            line_data['quantity'] = Decimal('1.00')

        if 'unit_price' not in line_data and 'amount' in line_data:
            qty = line_data['quantity'] or Decimal('1.00')
            line_data['unit_price'] = Decimal(str(line_data['amount'])) / qty

        line = ExpenseLine.objects.create(expense=expense, **line_data)
        logger.debug(f"Added line to expense {expense.expense_number}: {line.description}")
        return line

    @staticmethod
    @transaction.atomic
    def update_expense(expense, update_data):
        if expense.status == 'PAID':
            raise ValidationError("Cannot update paid expense")
        if expense.status == 'CANCELLED':
            raise ValidationError("Cannot update cancelled expense")

        for field, value in update_data.items():
            if hasattr(expense, field):
                setattr(expense, field, value)

        expense.save()
        logger.info(f"Updated expense {expense.expense_number}")
        return expense

    @staticmethod
    @transaction.atomic
    def submit_for_approval(expense, requested_by_id=None):
        if expense.status != 'DRAFT':
            raise ValidationError(f"Cannot submit {expense.get_status_display()} expense for approval")

        expense.status = 'PENDING_APPROVAL'
        if requested_by_id:
            expense.requested_by_id = str(requested_by_id)
        expense.save()

        logger.info(f"Submitted expense {expense.expense_number} for approval (by user {requested_by_id or 'System'})")
        return expense

    @staticmethod
    @transaction.atomic
    def approve_expense(expense, approved_by_id, notes='', auto_create_journal=True):
        if expense.status not in ['PENDING_APPROVAL', 'DRAFT']:
            raise ValidationError(f"Cannot approve {expense.get_status_display()} expense")

        expense.status         = 'APPROVED'
        expense.approved_by_id = str(approved_by_id)
        expense.approval_date  = get_school_current_time()
        if notes:
            expense.approval_notes = notes
        expense.save()

        # FIX: auto_create_journal_entry field removed — creation is unconditional
        if auto_create_journal:
            try:
                journal_entry       = JournalEntryService.create_expense_journal_entry(expense)
                expense.journal_entry = journal_entry
                expense.save(update_fields=['journal_entry'])
            except Exception as e:
                logger.error(f"Error creating journal entry for expense {expense.expense_number}: {e}")

        logger.info(f"Approved expense {expense.expense_number} (by user {approved_by_id})")
        return expense

    @staticmethod
    @transaction.atomic
    def reject_expense(expense, rejected_by_id, reason):
        if expense.status != 'PENDING_APPROVAL':
            raise ValidationError(f"Cannot reject {expense.get_status_display()} expense")

        expense.status           = 'REJECTED'
        expense.rejected_by_id   = str(rejected_by_id)
        expense.rejection_date   = get_school_current_time()
        expense.rejection_reason = reason
        expense.save()

        logger.info(f"Rejected expense {expense.expense_number}: {reason} (by user {rejected_by_id})")
        return expense

    @staticmethod
    @transaction.atomic
    def cancel_expense(expense, reason):
        if expense.status == 'PAID':
            raise ValidationError("Cannot cancel paid expense. Reverse payments instead.")

        active_payments = expense.payments.filter(reversed=False)
        if active_payments.exists():
            raise ValidationError(
                f"Expense has {active_payments.count()} active payment(s). "
                "Reverse payments before cancelling."
            )

        expense.status = 'CANCELLED'
        expense.notes  = (
            f"{expense.notes}\n\nCANCELLED: {reason}" if expense.notes
            else f"CANCELLED: {reason}"
        )
        expense.save()

        logger.info(f"Cancelled expense {expense.expense_number}: {reason}")
        return expense

    @staticmethod
    def get_expense_status(expense):
        active_payments = expense.payments.filter(reversed=False)
        total_paid      = active_payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        return {
            'status':           expense.status,
            'status_display':   expense.get_status_display(),
            'total_amount':     expense.total_amount,
            'paid_amount':      total_paid,
            'balance':          expense.total_amount - total_paid,
            'payment_count':    active_payments.count(),
            'is_fully_paid':    total_paid >= expense.total_amount,
            'can_be_approved':  expense.status in ['DRAFT', 'PENDING_APPROVAL'],
            'can_be_paid':      expense.status == 'APPROVED',
            'can_be_cancelled': expense.status in ['DRAFT', 'PENDING_APPROVAL', 'REJECTED'] or (
                expense.status == 'APPROVED' and total_paid == 0
            ),
        }


# =============================================================================
# EXPENSE PAYMENT SERVICE
# =============================================================================

class ExpensePaymentService:

    @staticmethod
    @transaction.atomic
    def create_payment(expense, payment_data):
        if expense.status == 'CANCELLED':
            raise ValidationError("Cannot create payment for cancelled expense")

        if expense.status != 'APPROVED':
            raise ValidationError(
                f"Expense must be approved before payment. "
                f"Current status: {expense.get_status_display()}"
            )

        amount = Decimal(str(payment_data['amount']))
        if amount <= 0:
            raise ValidationError("Payment amount must be positive")

        active_payments = expense.payments.filter(reversed=False)
        total_paid      = active_payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        remaining       = expense.total_amount - total_paid

        if amount > remaining:
            raise ValidationError(
                f"Payment amount ({amount:,.0f}) exceeds the outstanding balance "
                f"({remaining:,.0f}). Invoice total is {expense.total_amount:,.0f}."
            )

        if 'payment_date' not in payment_data:
            payment_data['payment_date'] = get_school_today()

        if 'fiscal_period' not in payment_data:
            payment_data['fiscal_period'] = _get_period_for_date(payment_data['payment_date'])
        elif isinstance(payment_data.get('fiscal_period'), int):
            payment_data['fiscal_period'] = FiscalPeriod.objects.get(pk=payment_data['fiscal_period'])

        if isinstance(payment_data.get('payment_method'), str):
            payment_data['payment_method'] = PaymentMethod.objects.get(code=payment_data['payment_method'])

        if isinstance(payment_data.get('account'), int):
            payment_data['account'] = Account.objects.get(pk=payment_data['account'])

        if payment_data.get('processing_fee') and payment_data['processing_fee'] > 0:
            if not payment_data.get('processing_fee_account'):
                settings = FinancialSettings.get_instance()
                if settings:
                    special_mappings = getattr(settings, 'special_account_mappings', None)
                    if special_mappings and hasattr(special_mappings, 'payment_processing_fee_account'):
                        payment_data['processing_fee_account'] = special_mappings.payment_processing_fee_account

        payment_data.setdefault('processing_fee', Decimal('0.00'))
        payment_data.setdefault('bank_charges',   Decimal('0.00'))
        payment_data.setdefault('status',         'PENDING')

        payment = ExpensePayment.objects.create(expense=expense, **payment_data)

        logger.info(
            f"Created payment for expense {expense.expense_number}: "
            f"{amount} via {payment.payment_method.name} (ref: {payment.reference_number})"
        )
        return payment

    @staticmethod
    @transaction.atomic
    def verify_payment(payment, verified_by_id, notes='', auto_create_journal=True):
        if payment.status == 'VERIFIED':
            raise ValidationError("Payment is already verified")
        if payment.reversed:
            raise ValidationError("Cannot verify reversed payment")

        payment.is_verified       = True
        payment.verified_by_id    = str(verified_by_id)
        payment.verification_date = get_school_current_time()
        if notes:
            payment.verification_notes = notes
        payment.status = 'VERIFIED'
        payment.save()

        # FIX: auto_create_journal_entry field removed — creation is unconditional
        if auto_create_journal:
            try:
                journal_entry         = JournalEntryService.create_expense_payment_journal_entry(payment)
                payment.journal_entry = journal_entry
                payment.save(update_fields=['journal_entry'])
            except Exception as e:
                logger.error(f"Error creating journal entry for payment {payment.reference_number}: {e}")

        payment.update_expense_status()

        logger.info(f"Verified payment {payment.reference_number} (by user {verified_by_id})")
        return payment

    @staticmethod
    @transaction.atomic
    def reverse_payment(payment, reversed_by_id, reason, requires_approval=True):
        can_reverse, message = payment.can_be_reversed()
        if not can_reverse:
            raise ValidationError(message)

        if requires_approval and not payment.reversal_approved_by_id:
            payment.reversal_approval_required = True
            payment.reversal_reason            = reason
            payment.save(update_fields=['reversal_approval_required', 'reversal_reason'])
            logger.info(f"Reversal requested for payment {payment.reference_number}: {reason} (awaiting approval)")
            return payment

        payment.reversed        = True
        payment.reversed_by_id  = str(reversed_by_id)
        payment.reversed_on     = get_school_current_time()
        payment.reversal_reason = reason
        payment.status          = 'REVERSED'
        payment.save()

        if payment.journal_entry:
            try:
                reversal_entry                 = JournalEntryService.reverse_journal_entry(
                    payment.journal_entry,
                    reason=f"Payment reversal: {reason}",
                    reversed_by_id=reversed_by_id,
                )
                payment.reversal_journal_entry = reversal_entry
                payment.save(update_fields=['reversal_journal_entry'])
            except Exception as e:
                logger.error(f"Error creating reversal journal entry for payment {payment.reference_number}: {e}")

        payment.update_expense_status()

        logger.info(f"Reversed payment {payment.reference_number}: {reason} (by user {reversed_by_id})")
        return payment

    @staticmethod
    @transaction.atomic
    def approve_reversal(payment, approved_by_id):
        if not payment.reversal_approval_required:
            raise ValidationError("This payment reversal does not require approval")
        if payment.reversal_approved_by_id:
            raise ValidationError("Reversal already approved")

        payment.reversal_approved_by_id = str(approved_by_id)
        payment.reversal_approved_on    = get_school_current_time()
        payment.save()

        return ExpensePaymentService.reverse_payment(
            payment,
            reversed_by_id=payment.reversed_by_id or approved_by_id,
            reason=payment.reversal_reason,
            requires_approval=False,
        )

    @staticmethod
    def get_payment_summary(expense):
        all_payments      = expense.payments.all()
        active_payments   = all_payments.filter(reversed=False)
        reversed_payments = all_payments.filter(reversed=True)

        total_paid     = active_payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        total_reversed = reversed_payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        total_fees     = active_payments.aggregate(
            total=Sum(F('processing_fee') + F('bank_charges'))
        )['total'] or Decimal('0.00')

        return {
            'total_amount':      expense.total_amount,
            'total_paid':        total_paid,
            'total_reversed':    total_reversed,
            'total_fees':        total_fees,
            'net_disbursed':     total_paid + total_fees,
            'balance':           expense.total_amount - total_paid,
            'payment_count':     active_payments.count(),
            'reversed_count':    reversed_payments.count(),
            'last_payment_date': (
                active_payments.order_by('-payment_date').first().payment_date
                if active_payments.exists() else None
            ),
        }


# =============================================================================
# JOURNAL ENTRY SERVICE
# =============================================================================

class JournalEntryService:

    @staticmethod
    @transaction.atomic
    def create_expense_journal_entry(expense):
        """
        DR: Expense Account
        CR: Accounts Payable
        """
        if expense.status != 'APPROVED':
            raise ValidationError("Can only create journal entry for approved expenses")
        if expense.journal_entry:
            raise ValidationError("Journal entry already exists for this expense")

        expense_account = expense.get_expense_account()
        payable_account = expense.get_payable_account()

        if not expense_account:
            raise ValidationError("Expense account not configured")
        if not payable_account:
            raise ValidationError("Accounts payable account not configured")

        journal, _ = Journal.objects.get_or_create(
            journal_type='EXPENSES',
            defaults={'name': 'Expense Journal', 'description': 'Journal for recording approved expenses'},
        )

        # FIX: expense.academic_session FK removed — derive from fiscal_period
        entry = JournalEntry.objects.create(
            journal=journal,
            entry_date=expense.expense_date,
            fiscal_period=expense.fiscal_period,
            academic_session=getattr(expense.fiscal_period, 'related_academic_session', None),
            description=f"Expense: {expense.description}",
            reference_number=expense.expense_number,
            status='POSTED',
            posted_at=get_school_current_time(),
        )

        JournalTransaction.objects.create(
            journal_entry=entry, account=expense_account,
            description=f"Expense: {expense.description}",
            amount=expense.total_amount, is_debit=True,
        )
        JournalTransaction.objects.create(
            journal_entry=entry, account=payable_account,
            description=f"Payable for: {expense.description}",
            amount=expense.total_amount, is_debit=False,
        )

        logger.info(f"Created journal entry {entry.entry_number} for expense {expense.expense_number}")
        return entry

    @staticmethod
    @transaction.atomic
    def create_expense_payment_journal_entry(payment):
        """
        DR: Accounts Payable
        DR: Processing Fee (if applicable)
        CR: Cash/Bank Account

        FIX: was payment.payment_method.is_cash (attribute doesn't exist).
             Use payment.payment_method.method_type == 'CASH' instead.
        """
        if not payment.is_verified:
            raise ValidationError("Can only create journal entry for verified payments")
        if payment.reversed:
            raise ValidationError("Cannot create journal entry for reversed payment")
        if payment.journal_entry:
            raise ValidationError("Journal entry already exists for this payment")

        payable_account = payment.get_payable_account()
        payment_account = payment.get_payment_account()

        if not payable_account:
            raise ValidationError("Accounts payable account not configured")
        if not payment_account:
            raise ValidationError("Payment account not configured")

        # FIX: use method_type field — is_cash does not exist on PaymentMethod
        is_cash = payment.payment_method.method_type == 'CASH'
        journal, _ = Journal.objects.get_or_create(
            journal_type='CASH' if is_cash else 'BANK',
            defaults={
                'name':        'Cash Journal' if is_cash else 'Bank Journal',
                'description': f"Journal for {'cash' if is_cash else 'bank'} transactions",
            }
        )

        entry = JournalEntry.objects.create(
            journal=journal,
            entry_date=payment.payment_date,
            fiscal_period=payment.fiscal_period,
            description=f"Payment for: {payment.expense.description}",
            reference_number=payment.reference_number or payment.transaction_id,
            status='POSTED',
            posted_at=get_school_current_time(),
        )

        # DR: Accounts Payable
        JournalTransaction.objects.create(
            journal_entry=entry, account=payable_account,
            description=f"Payment: {payment.expense.expense_number}",
            amount=payment.amount, is_debit=True,
        )

        # DR: Processing Fee (if applicable)
        if payment.processing_fee > 0:
            fee_account = payment.get_processing_fee_account()
            if fee_account:
                JournalTransaction.objects.create(
                    journal_entry=entry, account=fee_account,
                    description=f"Processing fee: {payment.payment_method.name}",
                    amount=payment.processing_fee, is_debit=True,
                )

        # CR: Cash/Bank Account
        total_credit = payment.amount + payment.processing_fee + payment.bank_charges
        JournalTransaction.objects.create(
            journal_entry=entry, account=payment_account,
            description=f"Payment via {payment.payment_method.name}",
            amount=total_credit, is_debit=False,
        )

        logger.info(f"Created journal entry {entry.entry_number} for payment {payment.reference_number}")
        return entry

    @staticmethod
    @transaction.atomic
    def reverse_journal_entry(original_entry, reason, reversed_by_id=None):
        if original_entry.status == 'REVERSED':
            raise ValidationError("Journal entry is already reversed")
        if original_entry.status != 'POSTED':
            raise ValidationError("Can only reverse posted journal entries")

        reversal_entry = JournalEntry.objects.create(
            journal=original_entry.journal,
            entry_date=get_school_today(),
            fiscal_period=_get_period_for_date(get_school_today()),
            academic_session=original_entry.academic_session,
            description=f"REVERSAL: {original_entry.description}",
            reference_number=f"REV-{original_entry.entry_number}",
            notes=f"Reversal of {original_entry.entry_number}: {reason}",
            status='POSTED',
            posted_at=get_school_current_time(),
            original_entry=original_entry,
        )

        for txn in original_entry.transactions.all():
            JournalTransaction.objects.create(
                journal_entry=reversal_entry, account=txn.account,
                description=f"Reversal: {txn.description}",
                amount=txn.amount, is_debit=not txn.is_debit,
            )

        original_entry.status          = 'REVERSED'
        original_entry.reversed_at     = get_school_current_time()
        original_entry.reversed_by_id  = str(reversed_by_id) if reversed_by_id else None
        original_entry.reversal_reason = reason
        original_entry.save()

        logger.info(f"Created reversal entry {reversal_entry.entry_number} for {original_entry.entry_number}: {reason}")
        return reversal_entry


# =============================================================================
# BUDGET SERVICE
# =============================================================================

class BudgetService:

    @staticmethod
    @transaction.atomic
    def create_budget(budget_data):
        lines_data = budget_data.pop('lines', [])

        if isinstance(budget_data.get('fiscal_year'), int):
            budget_data['fiscal_year'] = FiscalYear.objects.get(pk=budget_data['fiscal_year'])
        if isinstance(budget_data.get('parent_budget'), int):
            budget_data['parent_budget'] = Budget.objects.get(pk=budget_data['parent_budget'])

        budget_data.setdefault('status',               'DRAFT')
        budget_data.setdefault('total_revenue_budget', Decimal('0.00'))
        budget_data.setdefault('total_expense_budget', Decimal('0.00'))
        budget_data.setdefault('net_budget',           Decimal('0.00'))

        budget = Budget.objects.create(**budget_data)
        for line_data in lines_data:
            BudgetService.add_budget_line(budget, line_data)

        logger.info(f"Created budget {budget.name}")
        return budget

    @staticmethod
    @transaction.atomic
    def add_budget_line(budget, line_data):
        if isinstance(line_data.get('account'), int):
            line_data['account'] = Account.objects.get(pk=line_data['account'])

        line_data.setdefault('actual_amount', Decimal('0.00'))
        line = BudgetLine.objects.create(budget=budget, **line_data)
        BudgetService._update_budget_totals(budget)
        logger.debug(f"Added budget line to {budget.name}: {line.account.name}")
        return line

    @staticmethod
    @transaction.atomic
    def approve_budget(budget, approved_by_id):
        if budget.status not in ['DRAFT', 'SUBMITTED']:
            raise ValidationError(f"Cannot approve {budget.get_status_display()} budget")

        budget.status         = 'APPROVED'
        budget.approved_by_id = str(approved_by_id)
        budget.approval_date  = get_school_current_time()
        budget.save()

        logger.info(f"Approved budget {budget.name} (by user {approved_by_id})")
        return budget

    @staticmethod
    @transaction.atomic
    def activate_budget(budget):
        if budget.status != 'APPROVED':
            raise ValidationError("Budget must be approved before activation")

        budget.status = 'ACTIVE'
        budget.save()

        logger.info(f"Activated budget {budget.name}")
        return budget

    @staticmethod
    def sync_budget_actuals(budget):
        updated_lines = 0

        for line in budget.lines.all():
            actual = JournalTransaction.objects.filter(
                account=line.account,
                journal_entry__entry_date__gte=budget.start_date,
                journal_entry__entry_date__lte=budget.end_date,
                journal_entry__status='POSTED',
            ).aggregate(
                total=(
                    Sum('amount', filter=Q(is_debit=True)) -
                    Sum('amount', filter=Q(is_debit=False))
                )
            )['total'] or Decimal('0.00')

            if line.actual_amount != actual:
                line.actual_amount = actual
                line.save(update_fields=['actual_amount'])
                updated_lines += 1

        revenue_actual = budget.lines.filter(line_type='REVENUE').aggregate(
            total=Sum('actual_amount')
        )['total'] or Decimal('0.00')
        expense_actual = budget.lines.filter(line_type='EXPENSE').aggregate(
            total=Sum('actual_amount')
        )['total'] or Decimal('0.00')

        budget.actual_revenue_total = revenue_actual
        budget.actual_expense_total = expense_actual
        budget.last_actuals_sync    = get_school_current_time()
        budget.save(update_fields=['actual_revenue_total', 'actual_expense_total', 'last_actuals_sync'])

        logger.info(f"Synced actuals for budget {budget.name}: {updated_lines} lines updated")
        return {
            'updated_lines':  updated_lines,
            'revenue_actual': revenue_actual,
            'expense_actual': expense_actual,
            'sync_time':      budget.last_actuals_sync,
        }

    @staticmethod
    def get_budget_variance_analysis(budget):
        if budget.auto_sync_actuals:
            BudgetService.sync_budget_actuals(budget)

        revenue_variance = budget.actual_revenue_total - budget.total_revenue_budget
        expense_variance = budget.actual_expense_total - budget.total_expense_budget
        net_variance     = revenue_variance - expense_variance

        revenue_pct = (
            revenue_variance / budget.total_revenue_budget * 100
            if budget.total_revenue_budget > 0 else Decimal('0.00')
        )
        expense_pct = (
            expense_variance / budget.total_expense_budget * 100
            if budget.total_expense_budget > 0 else Decimal('0.00')
        )

        line_variances = []
        for line in budget.lines.all():
            variance     = line.actual_amount - line.budgeted_amount
            variance_pct = (
                variance / line.budgeted_amount * 100
                if line.budgeted_amount > 0 else Decimal('0.00')
            )
            line_variances.append({
                'account':             line.account.name,
                'line_type':           line.get_line_type_display(),
                'budgeted':            line.budgeted_amount,
                'actual':              line.actual_amount,
                'variance':            variance,
                'variance_percentage': variance_pct,
                'status': 'OVER' if variance > 0 else 'UNDER' if variance < 0 else 'ON_TARGET',
            })

        return {
            'budget_name': budget.name,
            'period':      f"{budget.start_date} to {budget.end_date}",
            'revenue': {
                'budgeted':            budget.total_revenue_budget,
                'actual':              budget.actual_revenue_total,
                'variance':            revenue_variance,
                'variance_percentage': revenue_pct,
            },
            'expenses': {
                'budgeted':            budget.total_expense_budget,
                'actual':              budget.actual_expense_total,
                'variance':            expense_variance,
                'variance_percentage': expense_pct,
            },
            'net': {
                'budgeted': budget.net_budget,
                'actual':   budget.actual_revenue_total - budget.actual_expense_total,
                'variance': net_variance,
            },
            'line_variances': line_variances,
            'last_sync':      budget.last_actuals_sync,
        }

    @staticmethod
    def _update_budget_totals(budget):
        revenue_total = budget.lines.filter(line_type='REVENUE').aggregate(
            total=Sum('budgeted_amount')
        )['total'] or Decimal('0.00')
        expense_total = budget.lines.filter(line_type='EXPENSE').aggregate(
            total=Sum('budgeted_amount')
        )['total'] or Decimal('0.00')

        budget.total_revenue_budget = revenue_total
        budget.total_expense_budget = expense_total
        budget.net_budget           = revenue_total - expense_total
        budget.save(update_fields=['total_revenue_budget', 'total_expense_budget', 'net_budget'])


# =============================================================================
# BULK OPERATIONS
# =============================================================================

class ExpenseBulkOperations:

    @staticmethod
    @transaction.atomic
    def bulk_approve_expenses(expenses, approved_by_id, notes=''):
        results = {'approved': [], 'failed': [], 'total': len(expenses)}
        for expense in expenses:
            try:
                ExpenseService.approve_expense(expense, approved_by_id, notes)
                results['approved'].append(expense)
            except Exception as e:
                logger.error(f"Error approving expense {expense.expense_number}: {e}")
                results['failed'].append({'expense': expense, 'error': str(e)})
        return results

    @staticmethod
    @transaction.atomic
    def bulk_cancel_expenses(expenses, reason):
        results = {'cancelled': [], 'failed': [], 'total': len(expenses)}
        for expense in expenses:
            try:
                ExpenseService.cancel_expense(expense, reason)
                results['cancelled'].append(expense)
            except Exception as e:
                logger.error(f"Error cancelling expense {expense.expense_number}: {e}")
                results['failed'].append({'expense': expense, 'error': str(e)})
        return results