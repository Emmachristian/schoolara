"""
Modal Views for Finance Management

These views return HTML fragments for modals loaded via HTMX.
Each modal view is paired with an action view in views.py that handles the POST request.

Pattern:
1. GET request → modal_views.py (loads modal HTML)
2. POST request → views.py (processes action, returns response with headers)

Following the same pattern as loans/modal_views.py with unified modals for create/edit
"""

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone

from .models import (
    AccountType,
    Account,
    ExpenseCategory,
    Expense,
    ExpenseLine,
    ExpensePayment,
    Journal,
    JournalEntry,
    JournalTransaction,
    Budget,
    BudgetLine,
)
from .forms import (
    AccountTypeForm,
    AccountForm,
    AccountQuickAddForm,
    ExpenseCategoryForm,
    ExpenseForm,
    ExpenseLineForm,
    ExpenseApprovalForm,
    ExpensePaymentForm,
    ExpensePaymentReversalForm,
    JournalForm,
    JournalEntryForm,
    JournalTransactionForm,
    JournalEntryReversalForm,
    BudgetForm,
    BudgetLineForm,
    BudgetApprovalForm,
)


# =============================================================================
# ACCOUNT TYPE MODALS
# =============================================================================

@login_required
def account_type_delete_modal(request, pk):
    """Return delete confirmation modal content via HTMX"""
    account_type = get_object_or_404(AccountType, pk=pk)
    
    # Check if type has accounts
    has_accounts = account_type.accounts.exists()
    account_count = account_type.accounts.count()
    
    # Check for active accounts specifically
    active_account_count = account_type.accounts.filter(is_active=True).count()
    has_active_accounts = active_account_count > 0
    
    return render(request, 'finance/account_types/modals/delete_type.html', {
        'account_type': account_type,
        'has_accounts': has_accounts,
        'account_count': account_count,
        'active_account_count': active_account_count,
        'has_active_accounts': has_active_accounts,
    })


# =============================================================================
# ACCOUNT MODALS
# =============================================================================

@login_required
def account_form_modal(request, pk=None):
    """
    Unified modal for creating or editing account
    - pk: Optional, if provided it's edit mode
    
    Pattern matches loans module:
    - /accounts/add/ → Create
    - /accounts/<pk>/edit/ → Edit
    """
    account = get_object_or_404(Account, pk=pk) if pk else None
    
    if request.method == 'POST':
        if account:
            form = AccountForm(request.POST, instance=account)
        else:
            form = AccountForm(request.POST)
    else:
        form = AccountForm(instance=account)
    
    return render(request, 'finance/accounts/modals/account_form.html', {
        'form': form,
        'account': account,
    })


@login_required
def account_quick_add_modal(request):
    """Return quick account creation modal via HTMX"""
    if request.method == 'POST':
        form = AccountQuickAddForm(request.POST)
    else:
        form = AccountQuickAddForm()
    
    return render(request, 'finance/accounts/modals/quick_add.html', {
        'form': form
    })


@login_required
def account_delete_modal(request, pk):
    """Return delete confirmation modal content via HTMX"""
    account = get_object_or_404(Account, pk=pk)
    
    # Check if can be deleted
    has_transactions = account.journal_transactions.exists()
    transaction_count = account.journal_transactions.count()
    has_child_accounts = account.child_accounts.exists()
    child_count = account.child_accounts.count()
    
    has_non_zero_balance = account.current_balance != 0
    
    can_delete = not (has_transactions or has_child_accounts)
    
    return render(request, 'finance/accounts/modals/delete_account.html', {
        'account': account,
        'has_transactions': has_transactions,
        'transaction_count': transaction_count,
        'has_child_accounts': has_child_accounts,
        'child_count': child_count,
        'has_non_zero_balance': has_non_zero_balance,
        'can_delete': can_delete,
    })


@login_required
def account_toggle_active_modal(request, pk):
    """Return toggle active status confirmation modal via HTMX"""
    account = get_object_or_404(Account, pk=pk)
    
    action = "deactivate" if account.is_active else "activate"
    
    return render(request, 'finance/accounts/modals/toggle_active.html', {
        'account': account,
        'action': action,
    })


@login_required
def account_quick_view_modal(request, pk):
    """Return account quick view modal via HTMX"""
    account = get_object_or_404(
        Account.objects.select_related('account_type', 'parent_account'),
        pk=pk
    )
    
    # Get recent transactions
    recent_transactions = account.journal_transactions.select_related(
        'journal_entry__journal'
    ).order_by('-journal_entry__entry_date', '-created_at')[:10]
    
    return render(request, 'finance/accounts/modals/quick_view.html', {
        'account': account,
        'recent_transactions': recent_transactions,
    })


# =============================================================================
# EXPENSE CATEGORY MODALS
# =============================================================================

@login_required
def expense_category_delete_modal(request, pk):
    """Return delete confirmation modal content via HTMX"""
    category = get_object_or_404(ExpenseCategory, pk=pk)
    
    # Check if category has expenses
    has_expenses = category.expenses.exists()
    expense_count = category.expenses.count()
    
    # Check for active expenses specifically
    active_expense_count = category.expenses.filter(
        status__in=['DRAFT', 'PENDING_APPROVAL', 'APPROVED']
    ).count()
    has_active_expenses = active_expense_count > 0
    
    return render(request, 'finance/expense_categories/modals/delete_category.html', {
        'category': category,
        'has_expenses': has_expenses,
        'expense_count': expense_count,
        'active_expense_count': active_expense_count,
        'has_active_expenses': has_active_expenses,
    })


@login_required
def expense_category_toggle_active_modal(request, pk):
    """Return toggle active status confirmation modal via HTMX"""
    category = get_object_or_404(ExpenseCategory, pk=pk)
    
    action = "deactivate" if category.is_active else "activate"
    
    return render(request, 'finance/expense_categories/modals/toggle_active.html', {
        'category': category,
        'action': action,
    })


# =============================================================================
# EXPENSE MODALS
# =============================================================================

@login_required
def expense_form_modal(request, pk=None):
    """
    Unified modal for creating or editing expense
    - pk: Optional, if provided it's edit mode
    
    Pattern matches loans module:
    - /expenses/add/ → Create
    - /expenses/<pk>/edit/ → Edit
    """
    expense = get_object_or_404(Expense, pk=pk) if pk else None
    
    # Check if expense can be edited
    can_edit = True
    message = None
    if expense:
        if expense.status in ['APPROVED', 'PAID']:
            can_edit = False
            message = f"Cannot edit expense with status: {expense.get_status_display()}"
    
    if request.method == 'POST':
        form = ExpenseForm(request.POST, request.FILES, instance=expense)
    else:
        form = ExpenseForm(instance=expense)
    
    return render(request, 'finance/expenses/modals/expense_form.html', {
        'form': form,
        'expense': expense,
        'can_edit': can_edit,
        'message': message,
    })


@login_required
def expense_submit_modal(request, pk):
    """Return expense submission confirmation modal via HTMX"""
    expense = get_object_or_404(Expense, pk=pk)
    
    # Check if can be submitted
    can_submit = expense.status == 'DRAFT'
    
    # Validate expense is complete
    validation_errors = []
    if not expense.description:
        validation_errors.append("Description is required")
    if not expense.total_amount:
        validation_errors.append("Total amount is required")
    if not expense.category:
        validation_errors.append("Category is required")
    if expense.lines.count() == 0:
        validation_errors.append("At least one line item is required")
    
    return render(request, 'finance/expenses/modals/submit_expense.html', {
        'expense': expense,
        'can_submit': can_submit and not validation_errors,
        'validation_errors': validation_errors,
    })


@login_required
def expense_approve_modal(request, pk):
    """Return expense approval modal with form via HTMX"""
    expense = get_object_or_404(Expense, pk=pk)
    
    # Check if can be approved
    can_approve = expense.status == 'PENDING_APPROVAL'
    
    if request.method == 'POST':
        form = ExpenseApprovalForm(request.POST)
    else:
        form = ExpenseApprovalForm()
    
    return render(request, 'finance/expenses/modals/approve_expense.html', {
        'form': form,
        'expense': expense,
        'can_approve': can_approve,
    })


@login_required
def expense_reject_modal(request, pk):
    """Return expense rejection modal with reason input via HTMX"""
    expense = get_object_or_404(Expense, pk=pk)
    
    return render(request, 'finance/expenses/modals/reject_expense.html', {
        'expense': expense
    })


@login_required
def expense_delete_modal(request, pk):
    """Return delete confirmation modal content via HTMX"""
    expense = get_object_or_404(Expense, pk=pk)
    
    # Check if can be deleted
    can_delete = expense.status in ['DRAFT', 'REJECTED', 'CANCELLED']
    has_payments = expense.payments.filter(reversed=False).exists()
    has_journal_entry = expense.journal_entry is not None
    
    return render(request, 'finance/expenses/modals/delete_expense.html', {
        'expense': expense,
        'can_delete': can_delete and not has_payments and not has_journal_entry,
        'has_payments': has_payments,
        'has_journal_entry': has_journal_entry,
    })


@login_required
def expense_quick_view_modal(request, pk):
    """Return expense quick view modal via HTMX"""
    expense = get_object_or_404(
        Expense.objects.select_related(
            'category', 'fiscal_period', 'expense_account'
        ).prefetch_related('lines', 'payments'),
        pk=pk
    )
    
    return render(request, 'finance/expenses/modals/quick_view.html', {
        'expense': expense
    })


# =============================================================================
# EXPENSE PAYMENT MODALS
# =============================================================================

@login_required
def expense_payment_form_modal(request, expense_pk=None, payment_pk=None):
    """
    Unified modal for creating or editing expense payment
    - expense_pk: Optional, pre-fill expense
    - payment_pk: Optional, if provided it's edit mode
    
    Pattern matches loans module:
    - /payments/add/ → Create (no expense)
    - /expenses/<expense_pk>/payments/add/ → Create (with expense)
    - /payments/<payment_pk>/edit/ → Edit
    """
    expense = None
    if expense_pk:
        expense = get_object_or_404(Expense, pk=expense_pk)
    
    payment = get_object_or_404(ExpensePayment, pk=payment_pk) if payment_pk else None
    
    # Check if expense can accept payments
    can_pay = True
    message = None
    if expense:
        if expense.status not in ['APPROVED', 'PAID']:
            can_pay = False
            message = f"Cannot process payment for expense with status: {expense.get_status_display()}"
    
    # Check if payment can be edited
    if payment:
        if payment.reversed:
            can_pay = False
            message = "Cannot edit reversed payment"
        elif payment.is_verified:
            can_pay = False
            message = "Cannot edit verified payment"
    
    if request.method == 'POST':
        form = ExpensePaymentForm(request.POST, instance=payment)
    else:
        initial = {'expense': expense, 'payment_date': timezone.now().date()} if expense and not payment else {}
        form = ExpensePaymentForm(instance=payment, initial=initial)
    
    return render(request, 'finance/expense_payments/modals/payment_form.html', {
        'form': form,
        'expense': expense,
        'payment': payment,
        'can_pay': can_pay,
        'message': message,
    })


@login_required
def expense_payment_verify_modal(request, pk):
    """Return payment verification confirmation modal via HTMX"""
    payment = get_object_or_404(ExpensePayment, pk=pk)
    
    # Check if can be verified
    can_verify = not payment.is_verified and payment.status == 'PROCESSED' and not payment.reversed
    
    return render(request, 'finance/expense_payments/modals/verify_payment.html', {
        'payment': payment,
        'can_verify': can_verify,
    })


@login_required
def expense_payment_reverse_modal(request, pk):
    """Return payment reversal modal with reason input via HTMX"""
    payment = get_object_or_404(ExpensePayment, pk=pk)
    
    # Check if can be reversed
    can_reverse, reason = payment.can_be_reversed()
    
    if request.method == 'POST':
        form = ExpensePaymentReversalForm(payment, request.user, request.POST)
    else:
        form = ExpensePaymentReversalForm(payment, request.user)
    
    return render(request, 'finance/expense_payments/modals/reverse_payment.html', {
        'form': form,
        'payment': payment,
        'can_reverse': can_reverse,
        'reason': reason if not can_reverse else None,
    })


@login_required
def expense_payment_delete_modal(request, pk):
    """Return delete confirmation modal content via HTMX"""
    payment = get_object_or_404(ExpensePayment, pk=pk)
    
    # Check if can be deleted
    can_delete = not payment.is_verified and not payment.reversed
    
    return render(request, 'finance/expense_payments/modals/delete_payment.html', {
        'payment': payment,
        'can_delete': can_delete,
    })


@login_required
def expense_payment_detail_modal(request, pk):
    """Return payment details modal via HTMX"""
    payment = get_object_or_404(
        ExpensePayment.objects.select_related(
            'expense__category',
            'payment_method',
            'account',
            'fiscal_period'
        ),
        pk=pk
    )
    
    # Get audit trail
    audit_trail = payment.get_audit_trail()
    
    return render(request, 'finance/expense_payments/modals/payment_detail.html', {
        'payment': payment,
        'audit_trail': audit_trail,
    })


@login_required
def bulk_payment_verification_modal(request):
    """Return bulk payment verification modal via HTMX"""
    
    # Get unverified processed payments
    unverified_payments = ExpensePayment.objects.filter(
        is_verified=False,
        status='PROCESSED',
        reversed=False
    ).select_related('expense__category', 'payment_method', 'account').order_by('-payment_date')[:50]
    
    total_amount = sum(p.amount for p in unverified_payments)
    
    return render(request, 'finance/expense_payments/modals/bulk_verify.html', {
        'unverified_payments': unverified_payments,
        'total_amount': total_amount,
    })


# =============================================================================
# JOURNAL MODALS
# =============================================================================

@login_required
def journal_delete_modal(request, pk):
    """Return delete confirmation modal content via HTMX"""
    journal = get_object_or_404(Journal, pk=pk)
    
    # Check if journal has entries
    has_entries = journal.entries.exists()
    entry_count = journal.entries.count()
    
    # Check for posted entries
    posted_count = journal.entries.filter(status='POSTED').count()
    has_posted_entries = posted_count > 0
    
    return render(request, 'finance/journals/modals/delete_journal.html', {
        'journal': journal,
        'has_entries': has_entries,
        'entry_count': entry_count,
        'posted_count': posted_count,
        'has_posted_entries': has_posted_entries,
    })


@login_required
def journal_toggle_active_modal(request, pk):
    """Return toggle active status confirmation modal via HTMX"""
    journal = get_object_or_404(Journal, pk=pk)
    
    action = "deactivate" if journal.is_active else "activate"
    
    return render(request, 'finance/journals/modals/toggle_active.html', {
        'journal': journal,
        'action': action,
    })


# =============================================================================
# JOURNAL ENTRY MODALS
# =============================================================================

@login_required
def journal_entry_form_modal(request, pk=None):
    """
    Unified modal for creating or editing journal entry
    - pk: Optional, if provided it's edit mode
    
    Pattern matches loans module:
    - /journal-entries/add/ → Create
    - /journal-entries/<pk>/edit/ → Edit
    """
    entry = get_object_or_404(JournalEntry, pk=pk) if pk else None
    
    # Check if entry can be edited
    can_edit = True
    message = None
    if entry:
        if entry.status == 'POSTED':
            can_edit = False
            message = "Cannot edit posted journal entries"
    
    if request.method == 'POST':
        form = JournalEntryForm(request.POST, instance=entry)
    else:
        form = JournalEntryForm(instance=entry)
    
    return render(request, 'finance/journal_entries/modals/entry_form.html', {
        'form': form,
        'entry': entry,
        'can_edit': can_edit,
        'message': message,
    })


@login_required
def journal_entry_post_modal(request, pk):
    """Return journal entry posting confirmation modal via HTMX"""
    entry = get_object_or_404(JournalEntry, pk=pk)
    
    # Check if can be posted
    can_post = entry.status == 'DRAFT'
    
    # Validate entry
    from .utils import validate_journal_entry
    validation = validate_journal_entry(entry)
    
    return render(request, 'finance/journal_entries/modals/post_entry.html', {
        'entry': entry,
        'can_post': can_post and validation['valid'] and validation['balanced'],
        'validation': validation,
    })


@login_required
def journal_entry_reverse_modal(request, pk):
    """Return journal entry reversal modal with form via HTMX"""
    entry = get_object_or_404(JournalEntry, pk=pk)
    
    # Check if can be reversed
    can_reverse = entry.status == 'POSTED'
    
    if request.method == 'POST':
        form = JournalEntryReversalForm(request.POST)
    else:
        form = JournalEntryReversalForm()
    
    return render(request, 'finance/journal_entries/modals/reverse_entry.html', {
        'form': form,
        'entry': entry,
        'can_reverse': can_reverse,
    })


@login_required
def journal_entry_delete_modal(request, pk):
    """Return delete confirmation modal content via HTMX"""
    entry = get_object_or_404(JournalEntry, pk=pk)
    
    # Check if can be deleted
    can_delete = entry.status == 'DRAFT'
    has_transactions = entry.transactions.exists()
    transaction_count = entry.transactions.count()
    
    return render(request, 'finance/journal_entries/modals/delete_entry.html', {
        'entry': entry,
        'can_delete': can_delete,
        'has_transactions': has_transactions,
        'transaction_count': transaction_count,
    })


@login_required
def journal_entry_quick_view_modal(request, pk):
    """Return journal entry quick view modal via HTMX"""
    entry = get_object_or_404(
        JournalEntry.objects.select_related(
            'journal', 'fiscal_period'
        ).prefetch_related('transactions__account'),
        pk=pk
    )
    
    # Calculate totals
    transactions = entry.transactions.all()
    debit_total = sum(t.amount for t in transactions if t.is_debit)
    credit_total = sum(t.amount for t in transactions if not t.is_debit)
    
    return render(request, 'finance/journal_entries/modals/quick_view.html', {
        'entry': entry,
        'transactions': transactions,
        'debit_total': debit_total,
        'credit_total': credit_total,
        'is_balanced': debit_total == credit_total,
    })


# =============================================================================
# BUDGET MODALS
# =============================================================================

@login_required
def budget_form_modal(request, pk=None):
    """
    Unified modal for creating or editing budget
    - pk: Optional, if provided it's edit mode
    
    Pattern matches loans module:
    - /budgets/add/ → Create
    - /budgets/<pk>/edit/ → Edit
    """
    budget = get_object_or_404(Budget, pk=pk) if pk else None
    
    # Check if budget can be edited
    can_edit = True
    message = None
    if budget:
        if budget.status in ['APPROVED', 'ACTIVE', 'CLOSED']:
            can_edit = False
            message = f"Cannot edit budget with status: {budget.get_status_display()}"
    
    if request.method == 'POST':
        form = BudgetForm(request.POST, instance=budget)
    else:
        form = BudgetForm(instance=budget)
    
    return render(request, 'finance/budgets/modals/budget_form.html', {
        'form': form,
        'budget': budget,
        'can_edit': can_edit,
        'message': message,
    })


@login_required
def budget_approve_modal(request, pk):
    """Return budget approval modal with form via HTMX"""
    budget = get_object_or_404(Budget, pk=pk)
    
    # Check if can be approved
    can_approve = budget.status in ['DRAFT', 'SUBMITTED']
    
    # Check if budget has lines
    has_lines = budget.lines.exists()
    line_count = budget.lines.count()
    
    # Check if budget is balanced
    is_deficit = budget.total_revenue_budget < budget.total_expense_budget
    
    if request.method == 'POST':
        form = BudgetApprovalForm(request.POST)
    else:
        form = BudgetApprovalForm()
    
    return render(request, 'finance/budgets/modals/approve_budget.html', {
        'form': form,
        'budget': budget,
        'can_approve': can_approve and has_lines,
        'has_lines': has_lines,
        'line_count': line_count,
        'is_deficit': is_deficit,
    })


@login_required
def budget_activate_modal(request, pk):
    """Return budget activation confirmation modal via HTMX"""
    budget = get_object_or_404(Budget, pk=pk)
    
    # Check if can be activated
    can_activate = budget.status == 'APPROVED'
    
    # Check dates
    from core.utils import get_school_today
    today = get_school_today()
    
    date_warnings = []
    if budget.start_date > today:
        date_warnings.append(f"Budget start date is in the future ({budget.start_date})")
    if budget.end_date < today:
        date_warnings.append(f"Budget end date has passed ({budget.end_date})")
    
    return render(request, 'finance/budgets/modals/activate_budget.html', {
        'budget': budget,
        'can_activate': can_activate,
        'date_warnings': date_warnings,
    })


@login_required
def budget_close_modal(request, pk):
    """Return budget closing confirmation modal via HTMX"""
    budget = get_object_or_404(Budget, pk=pk)
    
    # Check if can be closed
    can_close = budget.status == 'ACTIVE'
    
    return render(request, 'finance/budgets/modals/close_budget.html', {
        'budget': budget,
        'can_close': can_close,
    })


@login_required
def budget_delete_modal(request, pk):
    """Return delete confirmation modal content via HTMX"""
    budget = get_object_or_404(Budget, pk=pk)
    
    # Check if can be deleted
    can_delete = budget.status in ['DRAFT', 'REJECTED']
    has_lines = budget.lines.exists()
    line_count = budget.lines.count()
    has_child_budgets = budget.child_budgets.exists()
    child_count = budget.child_budgets.count()
    
    return render(request, 'finance/budgets/modals/delete_budget.html', {
        'budget': budget,
        'can_delete': can_delete and not has_child_budgets,
        'has_lines': has_lines,
        'line_count': line_count,
        'has_child_budgets': has_child_budgets,
        'child_count': child_count,
    })


@login_required
def budget_quick_view_modal(request, pk):
    """Return budget quick view modal via HTMX"""
    budget = get_object_or_404(
        Budget.objects.select_related(
            'fiscal_year', 'academic_session'
        ).prefetch_related('lines__account'),
        pk=pk
    )
    
    # Get summary by line type
    revenue_lines = budget.lines.filter(line_type='REVENUE')
    expense_lines = budget.lines.filter(line_type='EXPENSE')
    
    return render(request, 'finance/budgets/modals/quick_view.html', {
        'budget': budget,
        'revenue_lines': revenue_lines,
        'expense_lines': expense_lines,
    })

# [Continuing from previous modal_views.py...]

# =============================================================================
# ADDITIONAL EXPENSE MODALS (if any were missed)
# =============================================================================

@login_required
def expense_cancel_modal(request, pk):
    """Return expense cancellation modal with reason input via HTMX"""
    expense = get_object_or_404(Expense, pk=pk)
    
    # Check if can be cancelled
    can_cancel = expense.status not in ['APPROVED', 'PAID', 'CANCELLED']
    
    return render(request, 'finance/expenses/modals/cancel_expense.html', {
        'expense': expense,
        'can_cancel': can_cancel,
    })


# =============================================================================
# ADDITIONAL BUDGET MODALS
# =============================================================================

@login_required
def budget_submit_modal(request, pk):
    """Return budget submission confirmation modal via HTMX"""
    budget = get_object_or_404(Budget, pk=pk)
    
    # Check if can be submitted
    can_submit = budget.status == 'DRAFT'
    
    # Validate budget is complete
    validation_errors = []
    if not budget.name:
        validation_errors.append("Budget name is required")
    if budget.lines.count() == 0:
        validation_errors.append("At least one budget line is required")
    
    return render(request, 'finance/budgets/modals/submit_budget.html', {
        'budget': budget,
        'can_submit': can_submit and not validation_errors,
        'validation_errors': validation_errors,
    })


@login_required
def budget_reject_modal(request, pk):
    """Return budget rejection modal with reason input via HTMX"""
    budget = get_object_or_404(Budget, pk=pk)
    
    return render(request, 'finance/budgets/modals/reject_budget.html', {
        'budget': budget
    })


# =============================================================================
# ACCOUNT RECONCILIATION MODAL
# =============================================================================

@login_required
def account_reconciliation_modal(request, pk):
    """Return account reconciliation modal with form via HTMX"""
    account = get_object_or_404(Account, pk=pk)
    
    # Check if account is reconcilable
    can_reconcile = account.is_reconcilable
    
    if request.method == 'POST':
        from .forms import AccountReconciliationForm
        form = AccountReconciliationForm(request.POST)
    else:
        from .forms import AccountReconciliationForm
        form = AccountReconciliationForm(initial={'account': account})
    
    return render(request, 'finance/accounts/modals/reconcile.html', {
        'form': form,
        'account': account,
        'can_reconcile': can_reconcile,
    })


# =============================================================================
# BULK OPERATIONS MODALS
# =============================================================================

@login_required
def bulk_expense_approval_modal(request):
    """Return bulk expense approval modal via HTMX"""
    
    # Get pending expenses
    pending_expenses = Expense.objects.filter(
        status='PENDING_APPROVAL'
    ).select_related('category').order_by('expense_date')[:50]
    
    total_amount = sum(e.total_amount for e in pending_expenses)
    
    return render(request, 'finance/expenses/modals/bulk_approve.html', {
        'pending_expenses': pending_expenses,
        'total_amount': total_amount,
    })


@login_required
def bulk_expense_payment_modal(request):
    """Return bulk expense payment modal via HTMX"""
    
    # Get approved expenses without full payment
    approved_expenses = Expense.objects.filter(
        status='APPROVED'
    ).select_related('category').order_by('expense_date')[:50]
    
    # Filter to only show expenses that need payment
    unpaid_expenses = []
    for expense in approved_expenses:
        total_paid = sum(
            p.amount for p in expense.payments.all()
            if p.is_active
        )
        if total_paid < expense.total_amount:
            unpaid_expenses.append({
                'expense': expense,
                'remaining': expense.total_amount - total_paid
            })
    
    total_amount = sum(e['remaining'] for e in unpaid_expenses)
    
    return render(request, 'finance/expenses/modals/bulk_payment.html', {
        'unpaid_expenses': unpaid_expenses,
        'total_amount': total_amount,
    })


@login_required
def bulk_journal_entry_posting_modal(request):
    """Return bulk journal entry posting modal via HTMX"""
    
    # Get draft entries that are balanced
    from .utils import validate_journal_entry
    
    draft_entries = JournalEntry.objects.filter(
        status='DRAFT'
    ).select_related('journal', 'fiscal_period').order_by('entry_date')[:50]
    
    # Filter to only balanced entries
    postable_entries = []
    for entry in draft_entries:
        validation = validate_journal_entry(entry)
        if validation['valid'] and validation['balanced']:
            postable_entries.append(entry)
    
    return render(request, 'finance/journal_entries/modals/bulk_post.html', {
        'postable_entries': postable_entries,
    })


# =============================================================================
# REPORT GENERATION MODALS
# =============================================================================

@login_required
def financial_report_modal(request):
    """Return financial report generation modal via HTMX"""
    
    from .forms import FinancialReportForm
    
    if request.method == 'POST':
        form = FinancialReportForm(request.POST)
    else:
        form = FinancialReportForm()
    
    return render(request, 'finance/reports/modals/generate_report.html', {
        'form': form
    })


@login_required
def trial_balance_modal(request):
    """Return trial balance generation modal via HTMX"""
    
    from .forms import TrialBalanceForm
    
    if request.method == 'POST':
        form = TrialBalanceForm(request.POST)
    else:
        form = TrialBalanceForm()
    
    return render(request, 'finance/reports/modals/trial_balance.html', {
        'form': form
    })


@login_required
def income_statement_modal(request):
    """Return income statement generation modal via HTMX"""
    
    from .forms import IncomeStatementForm
    
    if request.method == 'POST':
        form = IncomeStatementForm(request.POST)
    else:
        form = IncomeStatementForm()
    
    return render(request, 'finance/reports/modals/income_statement.html', {
        'form': form
    })


@login_required
def balance_sheet_modal(request):
    """Return balance sheet generation modal via HTMX"""
    
    from .forms import BalanceSheetForm
    
    if request.method == 'POST':
        form = BalanceSheetForm(request.POST)
    else:
        form = BalanceSheetForm()
    
    return render(request, 'finance/reports/modals/balance_sheet.html', {
        'form': form
    })


@login_required
def cash_flow_statement_modal(request):
    """Return cash flow statement generation modal via HTMX"""
    
    from .forms import CashFlowStatementForm
    
    if request.method == 'POST':
        form = CashFlowStatementForm(request.POST)
    else:
        form = CashFlowStatementForm()
    
    return render(request, 'finance/reports/modals/cash_flow.html', {
        'form': form
    })


@login_required
def budget_variance_report_modal(request):
    """Return budget variance report generation modal via HTMX"""
    
    from .forms import BudgetVarianceReportForm
    
    if request.method == 'POST':
        form = BudgetVarianceReportForm(request.POST)
    else:
        form = BudgetVarianceReportForm()
    
    return render(request, 'finance/reports/modals/budget_variance.html', {
        'form': form
    })


# =============================================================================
# EXPENSE LINE MODALS (for inline management)
# =============================================================================

@login_required
def expense_line_form_modal(request, expense_pk, line_pk=None):
    """
    Unified modal for creating or editing expense line
    - expense_pk: Required, parent expense
    - line_pk: Optional, if provided it's edit mode
    """
    expense = get_object_or_404(Expense, pk=expense_pk)
    line = get_object_or_404(ExpenseLine, pk=line_pk) if line_pk else None
    
    # Check if expense allows line editing
    can_edit = expense.status in ['DRAFT', 'PENDING_APPROVAL']
    
    if request.method == 'POST':
        form = ExpenseLineForm(request.POST, instance=line)
    else:
        initial = {'expense': expense} if not line else {}
        form = ExpenseLineForm(instance=line, initial=initial)
    
    return render(request, 'finance/expenses/modals/line_form.html', {
        'form': form,
        'expense': expense,
        'line': line,
        'can_edit': can_edit,
    })


@login_required
def expense_line_delete_modal(request, pk):
    """Return expense line delete confirmation modal via HTMX"""
    line = get_object_or_404(ExpenseLine, pk=pk)
    
    # Check if can be deleted
    can_delete = line.expense.status in ['DRAFT', 'PENDING_APPROVAL']
    
    return render(request, 'finance/expenses/modals/delete_line.html', {
        'line': line,
        'can_delete': can_delete,
    })


# =============================================================================
# BUDGET LINE MODALS (for inline management)
# =============================================================================

@login_required
def budget_line_form_modal(request, budget_pk, line_pk=None):
    """
    Unified modal for creating or editing budget line
    - budget_pk: Required, parent budget
    - line_pk: Optional, if provided it's edit mode
    """
    budget = get_object_or_404(Budget, pk=budget_pk)
    line = get_object_or_404(BudgetLine, pk=line_pk) if line_pk else None
    
    # Check if budget allows line editing
    can_edit = budget.status in ['DRAFT', 'SUBMITTED']
    
    if request.method == 'POST':
        form = BudgetLineForm(request.POST, instance=line)
    else:
        initial = {'budget': budget} if not line else {}
        form = BudgetLineForm(instance=line, initial=initial)
    
    return render(request, 'finance/budgets/modals/line_form.html', {
        'form': form,
        'budget': budget,
        'line': line,
        'can_edit': can_edit,
    })


@login_required
def budget_line_delete_modal(request, pk):
    """Return budget line delete confirmation modal via HTMX"""
    line = get_object_or_404(BudgetLine, pk=pk)
    
    # Check if can be deleted
    can_delete = line.budget.status in ['DRAFT', 'SUBMITTED']
    
    return render(request, 'finance/budgets/modals/delete_line.html', {
        'line': line,
        'can_delete': can_delete,
    })


# =============================================================================
# JOURNAL TRANSACTION MODALS (for inline management)
# =============================================================================

@login_required
def journal_transaction_form_modal(request, entry_pk, transaction_pk=None):
    """
    Unified modal for creating or editing journal transaction
    - entry_pk: Required, parent journal entry
    - transaction_pk: Optional, if provided it's edit mode
    """
    entry = get_object_or_404(JournalEntry, pk=entry_pk)
    transaction = get_object_or_404(JournalTransaction, pk=transaction_pk) if transaction_pk else None
    
    # Check if entry allows transaction editing
    can_edit = entry.status == 'DRAFT'
    
    if request.method == 'POST':
        form = JournalTransactionForm(request.POST, instance=transaction)
    else:
        initial = {'journal_entry': entry} if not transaction else {}
        form = JournalTransactionForm(instance=transaction, initial=initial)
    
    return render(request, 'finance/journal_entries/modals/transaction_form.html', {
        'form': form,
        'entry': entry,
        'transaction': transaction,
        'can_edit': can_edit,
    })


@login_required
def journal_transaction_delete_modal(request, pk):
    """Return journal transaction delete confirmation modal via HTMX"""
    transaction = get_object_or_404(JournalTransaction, pk=pk)
    
    # Check if can be deleted
    can_delete = transaction.journal_entry.status == 'DRAFT'
    
    return render(request, 'finance/journal_entries/modals/delete_transaction.html', {
        'transaction': transaction,
        'can_delete': can_delete,
    })


# =============================================================================
# FISCAL PERIOD OPERATIONS MODALS
# =============================================================================

@login_required
def period_close_modal(request, pk):
    """Return fiscal period close confirmation modal via HTMX"""
    from core.models import FiscalPeriod
    period = get_object_or_404(FiscalPeriod, pk=pk)
    
    # Check if can be closed
    can_close = not period.is_closed
    
    # Check for pending items
    pending_expenses = Expense.objects.filter(
        fiscal_period=period,
        status='PENDING_APPROVAL'
    ).count()
    
    unverified_payments = ExpensePayment.objects.filter(
        fiscal_period=period,
        is_verified=False,
        reversed=False
    ).count()
    
    draft_entries = JournalEntry.objects.filter(
        fiscal_period=period,
        status='DRAFT'
    ).count()
    
    warnings = []
    if pending_expenses > 0:
        warnings.append(f"{pending_expenses} expense(s) pending approval")
    if unverified_payments > 0:
        warnings.append(f"{unverified_payments} payment(s) unverified")
    if draft_entries > 0:
        warnings.append(f"{draft_entries} draft journal entry(ies)")
    
    return render(request, 'finance/periods/modals/close_period.html', {
        'period': period,
        'can_close': can_close,
        'warnings': warnings,
    })


@login_required
def period_reopen_modal(request, pk):
    """Return fiscal period reopen confirmation modal via HTMX"""
    from core.models import FiscalPeriod
    period = get_object_or_404(FiscalPeriod, pk=pk)
    
    # Check if can be reopened
    can_reopen = period.is_closed
    
    return render(request, 'finance/periods/modals/reopen_period.html', {
        'period': period,
        'can_reopen': can_reopen,
    })


# =============================================================================
# ACCOUNT HIERARCHY MODALS
# =============================================================================

@login_required
def account_move_modal(request, pk):
    """Return account move (change parent) modal via HTMX"""
    account = get_object_or_404(Account, pk=pk)
    
    # Get potential parent accounts (exclude self and descendants)
    from .forms import AccountMoveForm
    
    if request.method == 'POST':
        form = AccountMoveForm(request.POST, instance=account)
    else:
        form = AccountMoveForm(instance=account)
    
    return render(request, 'finance/accounts/modals/move_account.html', {
        'form': form,
        'account': account,
    })


# =============================================================================
# APPROVAL WORKFLOW MODALS
# =============================================================================

@login_required
def approval_history_modal(request, model_name, pk):
    """Return approval history modal via HTMX"""
    
    # Get the object based on model name
    if model_name == 'expense':
        obj = get_object_or_404(Expense, pk=pk)
        template = 'finance/expenses/modals/approval_history.html'
    elif model_name == 'budget':
        obj = get_object_or_404(Budget, pk=pk)
        template = 'finance/budgets/modals/approval_history.html'
    else:
        from django.http import HttpResponseBadRequest
        return HttpResponseBadRequest("Invalid model name")
    
    return render(request, template, {
        'object': obj,
    })


# =============================================================================
# IMPORT/EXPORT MODALS
# =============================================================================

@login_required
def import_accounts_modal(request):
    """Return import accounts modal via HTMX"""
    
    from .forms import ImportAccountsForm
    
    if request.method == 'POST':
        form = ImportAccountsForm(request.POST, request.FILES)
    else:
        form = ImportAccountsForm()
    
    return render(request, 'finance/accounts/modals/import.html', {
        'form': form
    })


@login_required
def import_expenses_modal(request):
    """Return import expenses modal via HTMX"""
    
    from .forms import ImportExpensesForm
    
    if request.method == 'POST':
        form = ImportExpensesForm(request.POST, request.FILES)
    else:
        form = ImportExpensesForm()
    
    return render(request, 'finance/expenses/modals/import.html', {
        'form': form
    })


@login_required
def export_options_modal(request, model_name):
    """Return export options modal via HTMX"""
    
    from .forms import ExportOptionsForm
    
    if request.method == 'POST':
        form = ExportOptionsForm(request.POST)
    else:
        form = ExportOptionsForm()
    
    # Model-specific options
    if model_name == 'accounts':
        title = 'Export Accounts'
        fields = ['account_number', 'name', 'account_type', 'current_balance', 'is_active']
    elif model_name == 'expenses':
        title = 'Export Expenses'
        fields = ['expense_number', 'expense_date', 'category', 'vendor', 'total_amount', 'status']
    elif model_name == 'payments':
        title = 'Export Payments'
        fields = ['reference_number', 'payment_date', 'expense', 'amount', 'payment_method', 'status']
    elif model_name == 'entries':
        title = 'Export Journal Entries'
        fields = ['entry_number', 'entry_date', 'journal', 'description', 'total_debit', 'total_credit', 'status']
    elif model_name == 'budgets':
        title = 'Export Budgets'
        fields = ['name', 'budget_type', 'start_date', 'end_date', 'total_revenue', 'total_expense', 'status']
    else:
        title = 'Export Data'
        fields = []
    
    return render(request, 'finance/common/modals/export_options.html', {
        'form': form,
        'title': title,
        'model_name': model_name,
        'available_fields': fields,
    })


# =============================================================================
# SETTINGS AND CONFIGURATION MODALS
# =============================================================================

@login_required
def financial_settings_modal(request):
    """Return financial settings modal via HTMX"""
    
    from core.models import FinancialSettings
    from .forms import FinancialSettingsForm
    
    settings = FinancialSettings.get_instance()
    
    if request.method == 'POST':
        form = FinancialSettingsForm(request.POST, instance=settings)
    else:
        form = FinancialSettingsForm(instance=settings)
    
    return render(request, 'finance/settings/modals/financial_settings.html', {
        'form': form,
        'settings': settings,
    })


@login_required
def account_mapping_modal(request):
    """Return account mapping configuration modal via HTMX"""
    
    from .forms import AccountMappingForm
    
    if request.method == 'POST':
        form = AccountMappingForm(request.POST)
    else:
        form = AccountMappingForm()
    
    return render(request, 'finance/settings/modals/account_mapping.html', {
        'form': form
    })


# =============================================================================
# CONFIRMATION MODALS (generic)
# =============================================================================

@login_required
def confirm_action_modal(request):
    """Return generic confirmation modal via HTMX"""
    
    action = request.GET.get('action', 'perform this action')
    message = request.GET.get('message', f'Are you sure you want to {action}?')
    confirm_url = request.GET.get('confirm_url', '#')
    confirm_method = request.GET.get('confirm_method', 'POST')
    
    return render(request, 'finance/common/modals/confirm_action.html', {
        'action': action,
        'message': message,
        'confirm_url': confirm_url,
        'confirm_method': confirm_method,
    })