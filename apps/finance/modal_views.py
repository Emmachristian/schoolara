# finance/modal_views.py

"""
Modal Views for Finance Management

These views return HTML fragments for modals loaded via HTMX.
Each modal view is paired with an action view in views.py that handles the POST request.

Pattern:
1. GET request → modal_views.py (loads modal HTML)
2. POST request → views.py (processes action, returns response with headers)

CORRECTIONS in this version:
- expense_payment_verify_modal: removed status gate — can_verify = not verified and not reversed.
  Status belongs in the service, not the modal gate.
- bulk_payment_verification_modal: added 'PENDING' to status__in filter
- period_close_modal: added 'PENDING' to unverified_payments status__in filter
- expense_payment_form_modal: uses form.save() directly (avoids recursion from
  passing form.cleaned_data to service with extra key amount_in_school_currency)
- expense_payment_detail_modal: new view (was missing — reference number click target)
"""

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.http import HttpResponse
from django.urls import reverse

from .models import (
    AccountType, Account, ExpenseCategory,
    Expense, ExpenseLine, ExpensePayment,
    Journal, JournalEntry, JournalTransaction,
    Budget, BudgetLine,
)
from .forms import (
    AccountTypeForm, AccountForm, AccountQuickAddForm,
    ExpenseCategoryForm, ExpenseForm, ExpenseLineForm,
    ExpenseApprovalForm, ExpensePaymentForm, ExpensePaymentReversalForm,
    JournalForm, JournalEntryForm, JournalTransactionForm,
    JournalEntryReversalForm, BudgetForm, BudgetLineForm, BudgetApprovalForm,
)


# =============================================================================
# ACCOUNT TYPE MODALS
# =============================================================================

@login_required
def account_type_delete_modal(request, pk):
    account_type         = get_object_or_404(AccountType, pk=pk)
    has_accounts         = account_type.accounts.exists()
    account_count        = account_type.accounts.count()
    active_account_count = account_type.accounts.filter(is_active=True).count()

    return render(request, 'finance/account_types/modals/delete_type.html', {
        'account_type':         account_type,
        'has_accounts':         has_accounts,
        'account_count':        account_count,
        'active_account_count': active_account_count,
        'has_active_accounts':  active_account_count > 0,
    })


# =============================================================================
# ACCOUNT MODALS
# =============================================================================

@login_required
def account_form_modal(request, pk=None):
    account = get_object_or_404(Account, pk=pk) if pk else None
    form    = AccountForm(request.POST, instance=account) if request.method == 'POST' else AccountForm(instance=account)
    return render(request, 'finance/accounts/modals/account_form.html', {'form': form, 'account': account})


@login_required
def account_quick_add_modal(request):
    form = AccountQuickAddForm(request.POST) if request.method == 'POST' else AccountQuickAddForm()
    return render(request, 'finance/accounts/modals/quick_add.html', {'form': form})


@login_required
def account_delete_modal(request, pk):
    account              = get_object_or_404(Account, pk=pk)
    has_transactions     = account.journal_transactions.exists()
    transaction_count    = account.journal_transactions.count()
    has_child_accounts   = account.child_accounts.exists()
    child_count          = account.child_accounts.count()

    return render(request, 'finance/accounts/modals/delete_account.html', {
        'account':              account,
        'has_transactions':     has_transactions,
        'transaction_count':    transaction_count,
        'has_child_accounts':   has_child_accounts,
        'child_count':          child_count,
        'has_non_zero_balance': account.current_balance != 0,
        'can_delete':           not (has_transactions or has_child_accounts),
    })


@login_required
def account_toggle_active_modal(request, pk):
    account = get_object_or_404(Account, pk=pk)
    return render(request, 'finance/accounts/modals/toggle_active.html', {
        'account': account,
        'action':  "deactivate" if account.is_active else "activate",
    })


@login_required
def account_quick_view_modal(request, pk):
    account = get_object_or_404(
        Account.objects.select_related('account_type', 'parent_account'), pk=pk
    )
    recent_transactions = account.journal_transactions.select_related(
        'journal_entry__journal'
    ).order_by('-journal_entry__entry_date', '-created_at')[:10]

    return render(request, 'finance/accounts/modals/quick_view.html', {
        'account': account, 'recent_transactions': recent_transactions,
    })


# =============================================================================
# EXPENSE CATEGORY MODALS
# =============================================================================

@login_required
def expense_category_delete_modal(request, pk):
    category             = get_object_or_404(ExpenseCategory, pk=pk)
    has_expenses         = category.expenses.exists()
    expense_count        = category.expenses.count()
    active_expense_count = category.expenses.filter(
        status__in=['DRAFT', 'PENDING_APPROVAL', 'APPROVED']
    ).count()

    return render(request, 'finance/expense_categories/modals/delete_category.html', {
        'category':             category,
        'has_expenses':         has_expenses,
        'expense_count':        expense_count,
        'active_expense_count': active_expense_count,
        'has_active_expenses':  active_expense_count > 0,
    })


@login_required
def expense_category_toggle_active_modal(request, pk):
    category = get_object_or_404(ExpenseCategory, pk=pk)
    return render(request, 'finance/expense_categories/modals/toggle_active.html', {
        'category': category,
        'action':   "deactivate" if category.is_active else "activate",
    })


# =============================================================================
# EXPENSE MODALS
# =============================================================================

@login_required
def expense_form_modal(request, pk=None):
    expense  = get_object_or_404(Expense, pk=pk) if pk else None
    can_edit = True
    message  = None

    if expense and expense.status in ['APPROVED', 'PAID']:
        can_edit = False
        message  = f"Cannot edit expense with status: {expense.get_status_display()}"

    form = (
        ExpenseForm(request.POST, request.FILES, instance=expense)
        if request.method == 'POST'
        else ExpenseForm(instance=expense)
    )
    return render(request, 'finance/expenses/modals/expense_form.html', {
        'form': form, 'expense': expense, 'can_edit': can_edit, 'message': message,
    })


@login_required
def expense_submit_modal(request, pk):
    expense           = get_object_or_404(Expense, pk=pk)
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
        'expense':           expense,
        'can_submit':        expense.status == 'DRAFT' and not validation_errors,
        'validation_errors': validation_errors,
    })


@login_required
def expense_approve_modal(request, pk):
    expense     = get_object_or_404(Expense, pk=pk)
    can_approve = expense.status == 'PENDING_APPROVAL'
    form        = ExpenseApprovalForm(request.POST) if request.method == 'POST' else ExpenseApprovalForm()
    return render(request, 'finance/expenses/modals/approve_expense.html', {
        'form': form, 'expense': expense, 'can_approve': can_approve,
    })


@login_required
def expense_reject_modal(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    return render(request, 'finance/expenses/modals/reject_expense.html', {'expense': expense})


@login_required
def expense_delete_modal(request, pk):
    expense           = get_object_or_404(Expense, pk=pk)
    has_payments      = expense.payments.filter(reversed=False).exists()
    has_journal_entry = expense.journal_entry is not None
    can_delete        = (
        expense.status in ['DRAFT', 'REJECTED', 'CANCELLED']
        and not has_payments
        and not has_journal_entry
    )
    return render(request, 'finance/expenses/modals/delete_expense.html', {
        'expense':           expense,
        'can_delete':        can_delete,
        'has_payments':      has_payments,
        'has_journal_entry': has_journal_entry,
    })


@login_required
def expense_cancel_modal(request, pk):
    expense    = get_object_or_404(Expense, pk=pk)
    can_cancel = expense.status not in ['APPROVED', 'PAID', 'CANCELLED']
    return render(request, 'finance/expenses/modals/cancel_expense.html', {
        'expense': expense, 'can_cancel': can_cancel,
    })


@login_required
def expense_quick_view_modal(request, pk):
    expense = get_object_or_404(
        Expense.objects.select_related(
            'category', 'fiscal_period', 'expense_account'
        ).prefetch_related('lines', 'payments'),
        pk=pk,
    )
    return render(request, 'finance/expenses/modals/quick_view.html', {'expense': expense})


# =============================================================================
# EXPENSE LINE MODALS
# =============================================================================

@login_required
def expense_line_form_modal(request, expense_pk, line_pk=None):
    """
    Unified modal for creating or editing an expense line.
    GET  → blank or pre-filled ExpenseLineForm
    POST → validate and save; HX headers on success, re-render with errors on failure
    """
    expense  = get_object_or_404(Expense, pk=expense_pk)
    line     = get_object_or_404(ExpenseLine, pk=line_pk) if line_pk else None
    can_edit = expense.status in ['DRAFT', 'PENDING_APPROVAL']

    if request.method == 'POST' and can_edit:
        form = ExpenseLineForm(request.POST, instance=line)

        if form.is_valid():
            line_instance         = form.save(commit=False)
            line_instance.expense = expense
            line_instance.save()

            is_htmx = request.headers.get('HX-Request') == 'true'
            action  = 'updated' if line else 'added'

            if is_htmx:
                r = HttpResponse()
                r['HX-Alert-Message'] = f"Line item {action} successfully."
                r['HX-Alert-Type']    = 'success'
                r['HX-Close-Modal']   = 'true'
                r['HX-Redirect']      = reverse('finance:expense_detail', kwargs={'pk': str(expense.pk)})
                return r
            return redirect('finance:expense_detail', pk=expense.pk)

    else:
        initial = {'expense': expense} if not line else {}
        form    = ExpenseLineForm(instance=line, initial=initial)

    return render(request, 'finance/expenses/modals/line_form.html', {
        'form': form, 'expense': expense, 'line': line, 'can_edit': can_edit,
    })


@login_required
def expense_line_delete_modal(request, pk):
    """
    Delete confirmation modal for an expense line.
    GET  → render delete_line.html
    POST → delete and return HX headers
    """
    line       = get_object_or_404(ExpenseLine, pk=pk)
    can_delete = line.expense.status in ['DRAFT', 'PENDING_APPROVAL']

    if request.method == 'POST':
        is_htmx    = request.headers.get('HX-Request') == 'true'
        expense_pk = line.expense.pk

        if not can_delete:
            if is_htmx:
                r = HttpResponse()
                r['HX-Alert-Message'] = "Cannot delete lines on an expense that is not Draft or Pending."
                r['HX-Alert-Type']    = 'warning'
                r['HX-Close-Modal']   = 'true'
                return r
            return redirect('finance:expense_detail', pk=expense_pk)

        try:
            line.delete()
            if is_htmx:
                r = HttpResponse()
                r['HX-Alert-Message'] = "Line item removed."
                r['HX-Alert-Type']    = 'success'
                r['HX-Close-Modal']   = 'true'
                r['HX-Redirect']      = reverse('finance:expense_detail', kwargs={'pk': str(expense_pk)})
                return r
            return redirect('finance:expense_detail', pk=expense_pk)

        except Exception as e:
            if is_htmx:
                r = HttpResponse()
                r['HX-Alert-Message'] = f"Error removing line: {str(e)}"
                r['HX-Alert-Type']    = 'error'
                r['HX-Close-Modal']   = 'true'
                return r
            return redirect('finance:expense_detail', pk=expense_pk)

    return render(request, 'finance/expenses/modals/delete_line.html', {
        'line': line, 'can_delete': can_delete,
    })


# =============================================================================
# EXPENSE PAYMENT MODALS
# =============================================================================

@login_required
def expense_payment_form_modal(request, expense_pk=None, payment_pk=None):
    """
    Unified modal for recording or editing an expense payment.

    GET  → render payment_form.html with form + payment_methods_json (drives JS)
    POST → form.save(commit=False) + save() to avoid recursion from extra keys
           in form.cleaned_data (e.g. amount_in_school_currency).

    payment_date and fiscal_period are auto-set by payment_pre_save signal.
    """
    import json
    from finance.models import PaymentMethod as PM

    expense = get_object_or_404(Expense, pk=expense_pk) if expense_pk else None
    payment = get_object_or_404(ExpensePayment, pk=payment_pk) if payment_pk else None

    can_pay = True
    message = None

    if expense and expense.status not in ['APPROVED', 'PAID']:
        can_pay = False
        message = (
            f"Cannot process payment — expense is {expense.get_status_display()}. "
            "Approve the expense first."
        )
    if payment:
        if payment.reversed:
            can_pay = False
            message = "Cannot edit a reversed payment."
        elif payment.is_verified:
            can_pay = False
            message = "Cannot edit a verified payment."

    def _detect_type(pm):
        name = pm.name.lower()
        if any(k in name for k in ['cash', 'petty']):      return 'cash'
        if any(k in name for k in ['mobile', 'momo', 'mtn', 'airtel', 'mpesa']): return 'mobile_money'
        if any(k in name for k in ['cheque', 'check']):    return 'cheque'
        if any(k in name for k in ['bank', 'transfer', 'rtgs', 'wire', 'eft']): return 'bank'
        return 'other'

    payment_methods_json = json.dumps({
        str(pm.pk): {'type': _detect_type(pm)}
        for pm in PM.objects.filter(is_active=True)
    })

    _expense_obj     = expense or (payment.expense if payment else None)
    remaining_amount = None
    if _expense_obj:
        from django.db.models import Sum as _Sum
        paid             = _expense_obj.payments.filter(reversed=False).aggregate(t=_Sum('amount'))['t'] or 0
        remaining_amount = _expense_obj.total_amount - paid

    context = {
        'expense':              _expense_obj,
        'payment':              payment,
        'can_pay':              can_pay,
        'message':              message,
        'payment_methods_json': payment_methods_json,
        'remaining_amount':     remaining_amount,
    }

    if request.method == 'POST' and can_pay:
        form    = ExpensePaymentForm(request.POST, instance=payment)
        is_htmx = request.headers.get('HX-Request') == 'true'

        if form.is_valid():
            try:
                saved_payment = form.save(commit=False)
                if not payment:
                    saved_payment.expense = expense or form.cleaned_data.get('expense')
                saved_payment.save()   # triggers payment_pre_save signal

                msg = "Payment updated." if payment else f"Payment recorded for {saved_payment.expense.expense_number}."

                if is_htmx:
                    r = HttpResponse()
                    r['HX-Alert-Message'] = msg
                    r['HX-Alert-Type']    = 'success'
                    r['HX-Close-Modal']   = 'true'
                    r['HX-Redirect']      = reverse('finance:expense_detail', kwargs={'pk': str(saved_payment.expense.pk)})
                    return r
                return redirect('finance:expense_detail', pk=saved_payment.expense.pk)

            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Payment modal save error: {e}", exc_info=True)
                form.add_error(None, str(e))

        context['form'] = form
        return render(request, 'finance/expense_payments/modals/payment_form.html', context)

    initial         = {'expense': expense} if expense and not payment else {}
    context['form'] = ExpensePaymentForm(instance=payment, initial=initial)
    return render(request, 'finance/expense_payments/modals/payment_form.html', context)


@login_required
def expense_payment_detail_modal(request, pk):
    """Read-only payment detail modal — opened by clicking the reference number."""
    payment = get_object_or_404(
        ExpensePayment.objects.select_related(
            'expense__category', 'payment_method', 'account', 'fiscal_period',
            'journal_entry', 'reversal_journal_entry',
        ).prefetch_related(
            'journal_entry__transactions__account',
        ),
        pk=pk,
    )
    return render(request, 'finance/expense_payments/modals/payment_detail.html', {
        'payment':     payment,
        'audit_trail': payment.get_audit_trail() if hasattr(payment, 'get_audit_trail') else [],
    })


@login_required
def expense_payment_verify_modal(request, pk):
    """
    Confirm-verify modal. POST target is expense_payment_verify in views.py.

    FIX: removed status gate (status__in=['PROCESSING','PROCESSED']).
    A PENDING payment is verifiable — the service enforces business rules,
    not the modal gate.
    """
    payment    = get_object_or_404(
        ExpensePayment.objects.select_related('expense', 'payment_method'), pk=pk
    )
    can_verify = not payment.is_verified and not payment.reversed
    return render(request, 'finance/expense_payments/modals/verify_payment.html', {
        'payment': payment, 'can_verify': can_verify,
    })


@login_required
def expense_payment_reverse_modal(request, pk):
    """
    Reversal-reason modal. POST target is expense_payment_reverse in views.py.
    Hard-blocks only (already reversed, failed, cancelled).
    Service enforces approval-workflow rules.
    """
    payment     = get_object_or_404(
        ExpensePayment.objects.select_related('expense', 'payment_method'), pk=pk
    )
    can_reverse = not payment.reversed and payment.status not in ['FAILED', 'CANCELLED']
    _, reason   = payment.can_be_reversed()
    reason      = reason if not can_reverse else None

    form = (
        ExpensePaymentReversalForm(payment, request.user, request.POST)
        if request.method == 'POST'
        else ExpensePaymentReversalForm(payment, request.user)
    )
    return render(request, 'finance/expense_payments/modals/reverse_payment.html', {
        'form': form, 'payment': payment, 'can_reverse': can_reverse, 'reason': reason,
    })


@login_required
def expense_payment_delete_modal(request, pk):
    """Confirm-delete modal. POST target is expense_payment_delete in views.py."""
    payment    = get_object_or_404(
        ExpensePayment.objects.select_related('expense', 'payment_method'), pk=pk
    )
    can_delete = not payment.is_verified and not payment.reversed
    return render(request, 'finance/expense_payments/modals/delete_payment.html', {
        'payment': payment, 'can_delete': can_delete,
    })


@login_required
def bulk_payment_verification_modal(request):
    """
    FIX: added 'PENDING' to status__in — PENDING payments are unverified
    and should appear in the bulk verification list.
    """
    unverified_payments = ExpensePayment.objects.filter(
        is_verified=False,
        status__in=['PENDING', 'PROCESSING', 'PROCESSED'],   # FIX
        reversed=False,
    ).select_related(
        'expense__category', 'payment_method', 'account'
    ).order_by('-payment_date')[:50]

    total_amount = sum(p.amount for p in unverified_payments)
    return render(request, 'finance/expense_payments/modals/bulk_verify.html', {
        'unverified_payments': unverified_payments,
        'total_amount':        total_amount,
    })


# =============================================================================
# JOURNAL MODALS
# =============================================================================

@login_required
def journal_delete_modal(request, pk):
    journal      = get_object_or_404(Journal, pk=pk)
    has_entries  = journal.entries.exists()
    entry_count  = journal.entries.count()
    posted_count = journal.entries.filter(status='POSTED').count()

    return render(request, 'finance/journals/modals/delete_journal.html', {
        'journal':            journal,
        'has_entries':        has_entries,
        'entry_count':        entry_count,
        'posted_count':       posted_count,
        'has_posted_entries': posted_count > 0,
    })


@login_required
def journal_toggle_active_modal(request, pk):
    journal = get_object_or_404(Journal, pk=pk)
    return render(request, 'finance/journals/modals/toggle_active.html', {
        'journal': journal,
        'action':  "deactivate" if journal.is_active else "activate",
    })


# =============================================================================
# JOURNAL ENTRY MODALS
# =============================================================================

@login_required
def journal_entry_form_modal(request, pk=None):
    entry    = get_object_or_404(JournalEntry, pk=pk) if pk else None
    can_edit = True
    message  = None

    if entry and entry.status == 'POSTED':
        can_edit = False
        message  = "Cannot edit posted journal entries"

    form = (
        JournalEntryForm(request.POST, instance=entry)
        if request.method == 'POST'
        else JournalEntryForm(instance=entry)
    )
    return render(request, 'finance/journal_entries/modals/entry_form.html', {
        'form': form, 'entry': entry, 'can_edit': can_edit, 'message': message,
    })


@login_required
def journal_entry_post_modal(request, pk):
    entry    = get_object_or_404(JournalEntry, pk=pk)
    can_post = entry.status == 'DRAFT'

    from .utils import validate_journal_entry
    validation = validate_journal_entry(entry)

    return render(request, 'finance/journal_entries/modals/post_entry.html', {
        'entry':      entry,
        'can_post':   can_post and validation['valid'] and validation['balanced'],
        'validation': validation,
    })


@login_required
def journal_entry_reverse_modal(request, pk):
    entry       = get_object_or_404(JournalEntry, pk=pk)
    can_reverse = entry.status == 'POSTED'
    form        = (
        JournalEntryReversalForm(request.POST)
        if request.method == 'POST'
        else JournalEntryReversalForm()
    )
    return render(request, 'finance/journal_entries/modals/reverse_entry.html', {
        'form': form, 'entry': entry, 'can_reverse': can_reverse,
    })


@login_required
def journal_entry_delete_modal(request, pk):
    entry             = get_object_or_404(JournalEntry, pk=pk)
    has_transactions  = entry.transactions.exists()
    transaction_count = entry.transactions.count()
    return render(request, 'finance/journal_entries/modals/delete_entry.html', {
        'entry':             entry,
        'can_delete':        entry.status == 'DRAFT',
        'has_transactions':  has_transactions,
        'transaction_count': transaction_count,
    })


@login_required
def journal_entry_quick_view_modal(request, pk):
    entry = get_object_or_404(
        JournalEntry.objects.select_related('journal', 'fiscal_period').prefetch_related('transactions__account'),
        pk=pk,
    )
    transactions = entry.transactions.all()
    debit_total  = sum(t.amount for t in transactions if t.is_debit)
    credit_total = sum(t.amount for t in transactions if not t.is_debit)

    return render(request, 'finance/journal_entries/modals/quick_view.html', {
        'entry':        entry,
        'transactions': transactions,
        'debit_total':  debit_total,
        'credit_total': credit_total,
        'is_balanced':  debit_total == credit_total,
    })


# =============================================================================
# JOURNAL TRANSACTION MODALS
# =============================================================================

@login_required
def journal_transaction_form_modal(request, entry_pk, transaction_pk=None):
    entry       = get_object_or_404(JournalEntry, pk=entry_pk)
    transaction = get_object_or_404(JournalTransaction, pk=transaction_pk) if transaction_pk else None
    can_edit    = entry.status == 'DRAFT'

    if request.method == 'POST':
        form = JournalTransactionForm(request.POST, instance=transaction)
    else:
        initial = {'journal_entry': entry} if not transaction else {}
        form    = JournalTransactionForm(instance=transaction, initial=initial)

    return render(request, 'finance/journal_entries/modals/transaction_form.html', {
        'form': form, 'entry': entry, 'transaction': transaction, 'can_edit': can_edit,
    })


@login_required
def journal_transaction_delete_modal(request, pk):
    transaction = get_object_or_404(JournalTransaction, pk=pk)
    can_delete  = transaction.journal_entry.status == 'DRAFT'
    return render(request, 'finance/journal_entries/modals/delete_transaction.html', {
        'transaction': transaction, 'can_delete': can_delete,
    })


# =============================================================================
# BUDGET MODALS
# =============================================================================

@login_required
def budget_form_modal(request, pk=None):
    budget   = get_object_or_404(Budget, pk=pk) if pk else None
    can_edit = True
    message  = None

    if budget and budget.status in ['APPROVED', 'ACTIVE', 'CLOSED']:
        can_edit = False
        message  = f"Cannot edit budget with status: {budget.get_status_display()}"

    form = (
        BudgetForm(request.POST, instance=budget)
        if request.method == 'POST'
        else BudgetForm(instance=budget)
    )
    return render(request, 'finance/budgets/modals/budget_form.html', {
        'form': form, 'budget': budget, 'can_edit': can_edit, 'message': message,
    })


@login_required
def budget_approve_modal(request, pk):
    budget      = get_object_or_404(Budget, pk=pk)
    has_lines   = budget.lines.exists()
    line_count  = budget.lines.count()
    is_deficit  = budget.total_revenue_budget < budget.total_expense_budget
    form        = BudgetApprovalForm(request.POST) if request.method == 'POST' else BudgetApprovalForm()

    return render(request, 'finance/budgets/modals/approve_budget.html', {
        'form':        form,
        'budget':      budget,
        'can_approve': budget.status in ['DRAFT', 'SUBMITTED'] and has_lines,
        'has_lines':   has_lines,
        'line_count':  line_count,
        'is_deficit':  is_deficit,
    })


@login_required
def budget_activate_modal(request, pk):
    budget       = get_object_or_404(Budget, pk=pk)
    can_activate = budget.status == 'APPROVED'

    from core.utils import get_school_today
    today         = get_school_today()
    date_warnings = []
    if budget.start_date > today:
        date_warnings.append(f"Budget start date is in the future ({budget.start_date})")
    if budget.end_date < today:
        date_warnings.append(f"Budget end date has passed ({budget.end_date})")

    return render(request, 'finance/budgets/modals/activate_budget.html', {
        'budget': budget, 'can_activate': can_activate, 'date_warnings': date_warnings,
    })


@login_required
def budget_close_modal(request, pk):
    budget    = get_object_or_404(Budget, pk=pk)
    can_close = budget.status == 'ACTIVE'
    return render(request, 'finance/budgets/modals/close_budget.html', {
        'budget': budget, 'can_close': can_close,
    })


@login_required
def budget_delete_modal(request, pk):
    budget            = get_object_or_404(Budget, pk=pk)
    has_lines         = budget.lines.exists()
    has_child_budgets = budget.child_budgets.exists()

    return render(request, 'finance/budgets/modals/delete_budget.html', {
        'budget':            budget,
        'can_delete':        budget.status in ['DRAFT', 'REJECTED'] and not has_child_budgets,
        'has_lines':         has_lines,
        'line_count':        budget.lines.count(),
        'has_child_budgets': has_child_budgets,
        'child_count':       budget.child_budgets.count(),
    })


@login_required
def budget_submit_modal(request, pk):
    budget            = get_object_or_404(Budget, pk=pk)
    validation_errors = []
    if not budget.name:
        validation_errors.append("Budget name is required")
    if budget.lines.count() == 0:
        validation_errors.append("At least one budget line is required")

    return render(request, 'finance/budgets/modals/submit_budget.html', {
        'budget':            budget,
        'can_submit':        budget.status == 'DRAFT' and not validation_errors,
        'validation_errors': validation_errors,
    })


@login_required
def budget_reject_modal(request, pk):
    budget = get_object_or_404(Budget, pk=pk)
    return render(request, 'finance/budgets/modals/reject_budget.html', {'budget': budget})


@login_required
def budget_quick_view_modal(request, pk):
    budget = get_object_or_404(
        Budget.objects.select_related('fiscal_year', 'academic_session').prefetch_related('lines__account'),
        pk=pk,
    )
    return render(request, 'finance/budgets/modals/quick_view.html', {
        'budget':        budget,
        'revenue_lines': budget.lines.filter(line_type='REVENUE'),
        'expense_lines': budget.lines.filter(line_type='EXPENSE'),
    })


# =============================================================================
# BUDGET LINE MODALS
# =============================================================================

@login_required
def budget_line_form_modal(request, budget_pk, line_pk=None):
    budget   = get_object_or_404(Budget, pk=budget_pk)
    line     = get_object_or_404(BudgetLine, pk=line_pk) if line_pk else None
    can_edit = budget.status in ['DRAFT', 'SUBMITTED']

    if request.method == 'POST':
        form = BudgetLineForm(request.POST, instance=line)
    else:
        initial = {'budget': budget} if not line else {}
        form    = BudgetLineForm(instance=line, initial=initial)

    return render(request, 'finance/budgets/modals/line_form.html', {
        'form': form, 'budget': budget, 'line': line, 'can_edit': can_edit,
    })


@login_required
def budget_line_delete_modal(request, pk):
    line       = get_object_or_404(BudgetLine, pk=pk)
    can_delete = line.budget.status in ['DRAFT', 'SUBMITTED']
    return render(request, 'finance/budgets/modals/delete_line.html', {
        'line': line, 'can_delete': can_delete,
    })


# =============================================================================
# FISCAL PERIOD MODALS
# =============================================================================

@login_required
def period_close_modal(request, pk):
    """
    FIX: added 'PENDING' to unverified_payments status__in — PENDING payments
    are unverified and should count as a pre-close warning.
    """
    from core.models import FiscalPeriod
    period    = get_object_or_404(FiscalPeriod, pk=pk)
    can_close = not period.is_closed

    pending_expenses    = Expense.objects.filter(fiscal_period=period, status='PENDING_APPROVAL').count()
    unverified_payments = ExpensePayment.objects.filter(
        fiscal_period=period,
        is_verified=False,
        status__in=['PENDING', 'PROCESSING', 'PROCESSED'],   # FIX: added PENDING
        reversed=False,
    ).count()
    draft_entries       = JournalEntry.objects.filter(fiscal_period=period, status='DRAFT').count()

    warnings = []
    if pending_expenses:
        warnings.append(f"{pending_expenses} expense(s) pending approval")
    if unverified_payments:
        warnings.append(f"{unverified_payments} payment(s) unverified")
    if draft_entries:
        warnings.append(f"{draft_entries} draft journal entry(ies)")

    return render(request, 'finance/periods/modals/close_period.html', {
        'period': period, 'can_close': can_close, 'warnings': warnings,
    })


@login_required
def period_reopen_modal(request, pk):
    from core.models import FiscalPeriod
    period     = get_object_or_404(FiscalPeriod, pk=pk)
    can_reopen = period.is_closed
    return render(request, 'finance/periods/modals/reopen_period.html', {
        'period': period, 'can_reopen': can_reopen,
    })


# =============================================================================
# ACCOUNT RECONCILIATION MODAL
# =============================================================================

@login_required
def account_reconciliation_modal(request, pk):
    account       = get_object_or_404(Account, pk=pk)
    can_reconcile = account.is_reconcilable
    from .forms import AccountReconciliationForm
    form = (
        AccountReconciliationForm(request.POST)
        if request.method == 'POST'
        else AccountReconciliationForm(initial={'account': account})
    )
    return render(request, 'finance/accounts/modals/reconcile.html', {
        'form': form, 'account': account, 'can_reconcile': can_reconcile,
    })


# =============================================================================
# ACCOUNT HIERARCHY MODALS
# =============================================================================

@login_required
def account_move_modal(request, pk):
    account = get_object_or_404(Account, pk=pk)
    from .forms import AccountMoveForm
    form = (
        AccountMoveForm(request.POST, instance=account)
        if request.method == 'POST'
        else AccountMoveForm(instance=account)
    )
    return render(request, 'finance/accounts/modals/move_account.html', {
        'form': form, 'account': account,
    })


# =============================================================================
# BULK OPERATIONS MODALS
# =============================================================================

@login_required
def bulk_expense_approval_modal(request):
    pending_expenses = Expense.objects.filter(
        status='PENDING_APPROVAL'
    ).select_related('category').order_by('expense_date')[:50]

    return render(request, 'finance/expenses/modals/bulk_approve.html', {
        'pending_expenses': pending_expenses,
        'total_amount':     sum(e.total_amount for e in pending_expenses),
    })


@login_required
def bulk_expense_payment_modal(request):
    approved_expenses = Expense.objects.filter(
        status='APPROVED'
    ).select_related('category').prefetch_related('payments').order_by('expense_date')[:50]

    unpaid_expenses = []
    for expense in approved_expenses:
        total_paid = sum(p.amount for p in expense.payments.all() if p.is_active)
        if total_paid < expense.total_amount:
            unpaid_expenses.append({'expense': expense, 'remaining': expense.total_amount - total_paid})

    return render(request, 'finance/expenses/modals/bulk_payment.html', {
        'unpaid_expenses': unpaid_expenses,
        'total_amount':    sum(e['remaining'] for e in unpaid_expenses),
    })


@login_required
def bulk_journal_entry_posting_modal(request):
    from .utils import validate_journal_entry

    draft_entries = JournalEntry.objects.filter(
        status='DRAFT'
    ).select_related('journal', 'fiscal_period').order_by('entry_date')[:50]

    postable_entries = [
        entry for entry in draft_entries
        if validate_journal_entry(entry)['valid'] and validate_journal_entry(entry)['balanced']
    ]
    return render(request, 'finance/journal_entries/modals/bulk_post.html', {
        'postable_entries': postable_entries,
    })


# =============================================================================
# APPROVAL WORKFLOW MODALS
# =============================================================================

@login_required
def approval_history_modal(request, model_name, pk):
    if model_name == 'expense':
        obj      = get_object_or_404(Expense, pk=pk)
        template = 'finance/expenses/modals/approval_history.html'
    elif model_name == 'budget':
        obj      = get_object_or_404(Budget, pk=pk)
        template = 'finance/budgets/modals/approval_history.html'
    else:
        from django.http import HttpResponseBadRequest
        return HttpResponseBadRequest("Invalid model name")
    return render(request, template, {'object': obj})


# =============================================================================
# REPORT GENERATION MODALS
# =============================================================================

@login_required
def financial_report_modal(request):
    from .forms import FinancialReportForm
    form = FinancialReportForm(request.POST) if request.method == 'POST' else FinancialReportForm()
    return render(request, 'finance/reports/modals/generate_report.html', {'form': form})


@login_required
def trial_balance_modal(request):
    from .forms import TrialBalanceForm
    form = TrialBalanceForm(request.POST) if request.method == 'POST' else TrialBalanceForm()
    return render(request, 'finance/reports/modals/trial_balance.html', {'form': form})


@login_required
def income_statement_modal(request):
    from .forms import IncomeStatementForm
    form = IncomeStatementForm(request.POST) if request.method == 'POST' else IncomeStatementForm()
    return render(request, 'finance/reports/modals/income_statement.html', {'form': form})


@login_required
def balance_sheet_modal(request):
    from .forms import BalanceSheetForm
    form = BalanceSheetForm(request.POST) if request.method == 'POST' else BalanceSheetForm()
    return render(request, 'finance/reports/modals/balance_sheet.html', {'form': form})


@login_required
def cash_flow_statement_modal(request):
    from .forms import CashFlowStatementForm
    form = CashFlowStatementForm(request.POST) if request.method == 'POST' else CashFlowStatementForm()
    return render(request, 'finance/reports/modals/cash_flow.html', {'form': form})


@login_required
def budget_variance_report_modal(request):
    from .forms import BudgetVarianceReportForm
    form = BudgetVarianceReportForm(request.POST) if request.method == 'POST' else BudgetVarianceReportForm()
    return render(request, 'finance/reports/modals/budget_variance.html', {'form': form})


# =============================================================================
# IMPORT / EXPORT MODALS
# =============================================================================

@login_required
def import_accounts_modal(request):
    from .forms import ImportAccountsForm
    form = ImportAccountsForm(request.POST, request.FILES) if request.method == 'POST' else ImportAccountsForm()
    return render(request, 'finance/accounts/modals/import.html', {'form': form})


@login_required
def import_expenses_modal(request):
    from .forms import ImportExpensesForm
    form = ImportExpensesForm(request.POST, request.FILES) if request.method == 'POST' else ImportExpensesForm()
    return render(request, 'finance/expenses/modals/import.html', {'form': form})


@login_required
def export_options_modal(request, model_name):
    from .forms import ExportOptionsForm
    form = ExportOptionsForm(request.POST) if request.method == 'POST' else ExportOptionsForm()

    field_map = {
        'accounts': {'title': 'Export Accounts',        'fields': ['account_number', 'name', 'account_type', 'current_balance', 'is_active']},
        'expenses': {'title': 'Export Expenses',        'fields': ['expense_number', 'expense_date', 'category', 'vendor', 'total_amount', 'status']},
        'payments': {'title': 'Export Payments',        'fields': ['reference_number', 'payment_date', 'expense', 'amount', 'payment_method', 'status']},
        'entries':  {'title': 'Export Journal Entries', 'fields': ['entry_number', 'entry_date', 'journal', 'description', 'total_debit', 'total_credit', 'status']},
        'budgets':  {'title': 'Export Budgets',         'fields': ['name', 'budget_type', 'start_date', 'end_date', 'total_revenue', 'total_expense', 'status']},
    }
    meta = field_map.get(model_name, {'title': 'Export Data', 'fields': []})

    return render(request, 'finance/common/modals/export_options.html', {
        'form':             form,
        'title':            meta['title'],
        'model_name':       model_name,
        'available_fields': meta['fields'],
    })


# =============================================================================
# SETTINGS AND CONFIGURATION MODALS
# =============================================================================

@login_required
def financial_settings_modal(request):
    from core.models import FinancialSettings
    from .forms import FinancialSettingsForm
    settings = FinancialSettings.get_instance()
    form     = (
        FinancialSettingsForm(request.POST, instance=settings)
        if request.method == 'POST'
        else FinancialSettingsForm(instance=settings)
    )
    return render(request, 'finance/settings/modals/financial_settings.html', {
        'form': form, 'settings': settings,
    })


@login_required
def account_mapping_modal(request):
    from .forms import AccountMappingForm
    form = AccountMappingForm(request.POST) if request.method == 'POST' else AccountMappingForm()
    return render(request, 'finance/settings/modals/account_mapping.html', {'form': form})


# =============================================================================
# GENERIC CONFIRMATION MODAL
# =============================================================================

@login_required
def confirm_action_modal(request):
    action         = request.GET.get('action', 'perform this action')
    message        = request.GET.get('message', f'Are you sure you want to {action}?')
    confirm_url    = request.GET.get('confirm_url', '#')
    confirm_method = request.GET.get('confirm_method', 'POST')

    return render(request, 'finance/common/modals/confirm_action.html', {
        'action':         action,
        'message':        message,
        'confirm_url':    confirm_url,
        'confirm_method': confirm_method,
    })