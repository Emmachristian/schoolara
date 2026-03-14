"""
Finance Management Views

Comprehensive view functions for:
- Account Types (CRUD + Print)
- Accounts (CRUD + Print + Reconciliation)
- Expense Categories (CRUD + Print)
- Expenses (CRUD + Print + Approval + Bulk)
- Expense Payments (CRUD + Print + Verification + Reversal)
- Journals (CRUD + Print)
- Journal Entries (CRUD + Print + Posting + Reversal)
- Budgets (CRUD + Print + Approval)
- Reports and Analytics

All views delegate business logic to services.py
Uses SweetAlert2 for all notifications via Django messages
Follows the same patterns as loans/views.py
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.contrib import messages
from django.db.models import Q, Count, Sum, Avg, F, Max, Min, DecimalField, Case, When
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from django.db import transaction
from datetime import timedelta, date, datetime
from decimal import Decimal
import logging

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

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
    AccountTypeFilterForm,
    AccountFilterForm,
    ExpenseCategoryFilterForm,
    ExpenseFilterForm,
    ExpensePaymentFilterForm,
    ExpensePaymentReversalForm,
    JournalFilterForm,
    JournalEntryFilterForm,
    BudgetFilterForm,
    AccountTypeForm,
    AccountForm,
    AccountQuickAddForm,
    ExpenseCategoryForm,
    ExpenseForm,
    ExpenseLineForm,
    ExpenseApprovalForm,
    ExpensePaymentForm,
    BulkExpensePaymentForm,
    BulkExpensePaymentVerificationForm,
    JournalForm,
    JournalEntryForm,
    JournalTransactionForm,
    JournalEntryReversalForm,
    BudgetForm,
    BudgetLineForm,
    BudgetApprovalForm,
    AccountReconciliationForm,
)

# Import services
from .services import (
    ExpenseService,
    ExpensePaymentService,
    JournalEntryService,
    BudgetService,
)

from core.utils import (
    get_school_today,
    get_school_current_time,
    format_money,
    get_school_currency,
)
from academics.models import AcademicSession
from core.models import FiscalYear, FiscalPeriod

# Import stats functions
from . import stats as finance_stats

logger = logging.getLogger(__name__)


# =============================================================================
# DASHBOARD
# =============================================================================

@login_required
def finance_dashboard(request):
    """Main finance dashboard with overview statistics"""
    
    try:
        # Get current fiscal period
        current_period = FiscalPeriod.get_current_fiscal_period()
        
        # Account statistics
        account_stats = {
            'total': Account.objects.filter(is_active=True).count(),
            'bank_accounts': Account.objects.filter(is_bank_account=True, is_active=True).count(),
            'cash_accounts': Account.objects.filter(is_cash_account=True, is_active=True).count(),
            'total_cash_balance': Account.objects.filter(
                is_cash_account=True, is_active=True
            ).aggregate(Sum('current_balance'))['current_balance__sum'] or Decimal('0.00'),
            'total_bank_balance': Account.objects.filter(
                is_bank_account=True, is_active=True
            ).aggregate(Sum('current_balance'))['current_balance__sum'] or Decimal('0.00'),
        }
        
        # Expense statistics (uses school timezone)
        today = get_school_today()
        this_month_start = today.replace(day=1)
        
        expense_stats = {
            'total_pending': Expense.objects.filter(status='PENDING_APPROVAL').count(),
            'total_approved': Expense.objects.filter(status='APPROVED').count(),
            'this_month_count': Expense.objects.filter(
                expense_date__gte=this_month_start
            ).count(),
            'this_month_amount': Expense.objects.filter(
                expense_date__gte=this_month_start
            ).aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0.00'),
            'pending_amount': Expense.objects.filter(
                status='PENDING_APPROVAL'
            ).aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0.00'),
        }
        
        # Budget statistics
        active_budgets = Budget.objects.filter(status='ACTIVE')
        budget_stats = {
            'total_active': active_budgets.count(),
            'total_revenue_budget': active_budgets.aggregate(
                Sum('total_revenue_budget'))['total_revenue_budget__sum'] or Decimal('0.00'),
            'total_expense_budget': active_budgets.aggregate(
                Sum('total_expense_budget'))['total_expense_budget__sum'] or Decimal('0.00'),
            'total_actual_revenue': active_budgets.aggregate(
                Sum('actual_revenue_total'))['actual_revenue_total__sum'] or Decimal('0.00'),
            'total_actual_expense': active_budgets.aggregate(
                Sum('actual_expense_total'))['actual_expense_total__sum'] or Decimal('0.00'),
        }
        
        # Journal Entry statistics
        journal_stats = {
            'total_draft': JournalEntry.objects.filter(status='DRAFT').count(),
            'total_posted': JournalEntry.objects.filter(status='POSTED').count(),
            'this_month_count': JournalEntry.objects.filter(
                entry_date__gte=this_month_start
            ).count(),
        }
        
        # Payment statistics
        payment_stats = {
            'unverified': ExpensePayment.objects.filter(
                is_verified=False,
                status='PROCESSED'
            ).count(),
            'verified': ExpensePayment.objects.filter(is_verified=True).count(),
            'reversed': ExpensePayment.objects.filter(reversed=True).count(),
        }
        
    except Exception as e:
        logger.error(f"Error getting dashboard statistics: {e}")
        account_stats = {}
        expense_stats = {}
        budget_stats = {}
        journal_stats = {}
        payment_stats = {}
    
    # Get recent activities
    recent_expenses = Expense.objects.select_related(
        'category', 'fiscal_period'
    ).order_by('-created_at')[:10]
    
    recent_payments = ExpensePayment.objects.select_related(
        'expense', 'payment_method', 'account'
    ).filter(
        reversed=False
    ).order_by('-payment_date')[:10]
    
    recent_entries = JournalEntry.objects.select_related(
        'journal', 'fiscal_period'
    ).order_by('-entry_date')[:10]
    
    # Items needing attention
    pending_expenses = Expense.objects.filter(
        status='PENDING_APPROVAL'
    ).select_related('category').order_by('expense_date')[:10]
    
    unverified_payments = ExpensePayment.objects.filter(
        is_verified=False,
        status='PROCESSED',
        reversed=False
    ).select_related('expense', 'payment_method').order_by('-payment_date')[:10]
    
    draft_entries = JournalEntry.objects.filter(
        status='DRAFT'
    ).select_related('journal').order_by('entry_date')[:10]
    
    over_budget = BudgetLine.objects.filter(
        actual_amount__gt=F('budgeted_amount'),
        budget__status='ACTIVE'
    ).select_related('budget', 'account').order_by('-actual_amount')[:10]
    
    context = {
        'current_period': current_period,
        'account_stats': account_stats,
        'expense_stats': expense_stats,
        'budget_stats': budget_stats,
        'journal_stats': journal_stats,
        'payment_stats': payment_stats,
        'recent_expenses': recent_expenses,
        'recent_payments': recent_payments,
        'recent_entries': recent_entries,
        'pending_expenses': pending_expenses,
        'unverified_payments': unverified_payments,
        'draft_entries': draft_entries,
        'over_budget': over_budget,
        'currency': get_school_currency(),
    }
    
    return render(request, 'finance/dashboard.html', context)


# =============================================================================
# HELPER FUNCTIONS FOR FILTERING
# =============================================================================

def get_filtered_account_types(request):
    """Helper function to get filtered account types queryset"""
    account_types = AccountType.objects.annotate(
        account_count=Count('accounts', distinct=True)
    ).order_by('account_type', 'display_order', 'name')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    account_type = request.GET.get('account_type', '')
    is_active = request.GET.get('is_active', '')
    
    # Apply text search
    if query:
        words = query.strip().split()
        if words:
            combined_q = Q()
            for word in words:
                word_q = (
                    Q(name__icontains=word) |
                    Q(code__icontains=word) |
                    Q(description__icontains=word)
                )
                combined_q &= word_q
            account_types = account_types.filter(combined_q)
    
    # Apply filters
    if account_type:
        account_types = account_types.filter(account_type=account_type)
    if is_active:
        account_types = account_types.filter(is_active=(is_active.lower() == 'true'))
    
    return account_types


def get_filtered_accounts(request):
    """Helper function to get filtered accounts queryset"""
    accounts = Account.objects.select_related(
        'account_type',
        'parent_account'
    ).annotate(
        child_count=Count('child_accounts', distinct=True),
        transaction_count=Count('journal_transactions', distinct=True)
    ).order_by('account_type__account_type', 'account_number')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    account_type = request.GET.get('account_type', '')
    account_category = request.GET.get('account_category', '')
    is_active = request.GET.get('is_active', '')
    is_reconcilable = request.GET.get('is_reconcilable', '')
    min_balance = request.GET.get('min_balance', '')
    max_balance = request.GET.get('max_balance', '')
    
    # Apply text search
    if query:
        words = query.strip().split()
        if words:
            combined_q = Q()
            for word in words:
                word_q = (
                    Q(account_number__icontains=word) |
                    Q(name__icontains=word) |
                    Q(description__icontains=word) |
                    Q(bank_name__icontains=word)
                )
                combined_q &= word_q
            accounts = accounts.filter(combined_q)
    
    # Apply filters
    if account_type:
        accounts = accounts.filter(account_type_id=account_type)
    
    if account_category:
        if account_category == 'bank':
            accounts = accounts.filter(is_bank_account=True)
        elif account_category == 'cash':
            accounts = accounts.filter(is_cash_account=True)
        elif account_category == 'mobile_money':
            accounts = accounts.filter(is_mobile_money_account=True)
        elif account_category == 'receivable':
            accounts = accounts.filter(is_receivable_account=True)
        elif account_category == 'payable':
            accounts = accounts.filter(is_payable_account=True)
        elif account_category == 'inventory':
            accounts = accounts.filter(is_inventory_account=True)
        elif account_category == 'fixed_asset':
            accounts = accounts.filter(is_fixed_asset=True)
        elif account_category == 'revenue':
            accounts = accounts.filter(is_revenue_account=True)
        elif account_category == 'expense':
            accounts = accounts.filter(is_expense_account=True)
    
    if is_active:
        accounts = accounts.filter(is_active=(is_active.lower() == 'true'))
    
    if is_reconcilable:
        accounts = accounts.filter(is_reconcilable=(is_reconcilable.lower() == 'true'))
    
    # Apply balance filters
    if min_balance:
        try:
            accounts = accounts.filter(current_balance__gte=Decimal(min_balance))
        except (ValueError, TypeError):
            pass
    
    if max_balance:
        try:
            accounts = accounts.filter(current_balance__lte=Decimal(max_balance))
        except (ValueError, TypeError):
            pass
    
    return accounts


def get_filtered_expense_categories(request):
    """Helper function to get filtered expense categories queryset"""
    categories = ExpenseCategory.objects.select_related(
        'default_expense_account'
    ).annotate(
        expense_count=Count('expenses', distinct=True)
    ).order_by('category_type', 'name')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    category_type = request.GET.get('category_type', '')
    is_active = request.GET.get('is_active', '')
    requires_approval = request.GET.get('requires_approval', '')
    
    # Apply text search
    if query:
        words = query.strip().split()
        if words:
            combined_q = Q()
            for word in words:
                word_q = (
                    Q(name__icontains=word) |
                    Q(description__icontains=word)
                )
                combined_q &= word_q
            categories = categories.filter(combined_q)
    
    # Apply filters
    if category_type:
        categories = categories.filter(category_type=category_type)
    if is_active:
        categories = categories.filter(is_active=(is_active.lower() == 'true'))
    if requires_approval:
        categories = categories.filter(requires_approval=(requires_approval.lower() == 'true'))
    
    return categories


def get_filtered_expenses(request):
    """Helper function to get filtered expenses queryset"""
    expenses = Expense.objects.select_related(
        'category',
        'academic_session',
        'fiscal_period',
        'expense_account',
        'budget_line'
    ).prefetch_related(
        'lines',
        'payments'
    ).annotate(
        line_count=Count('lines', distinct=True),
        payment_count=Count('payments', distinct=True, filter=Q(payments__reversed=False))
    ).order_by('-expense_date', '-created_at')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    category = request.GET.get('category', '')
    academic_session = request.GET.get('academic_session', '')
    fiscal_period = request.GET.get('fiscal_period', '')
    expense_date_from = request.GET.get('expense_date_from', '')
    expense_date_to = request.GET.get('expense_date_to', '')
    min_amount = request.GET.get('min_amount', '')
    max_amount = request.GET.get('max_amount', '')
    
    # Apply text search
    if query:
        words = query.strip().split()
        if words:
            combined_q = Q()
            for word in words:
                word_q = (
                    Q(expense_number__icontains=word) |
                    Q(description__icontains=word) |
                    Q(vendor_name__icontains=word) |
                    Q(vendor_reference__icontains=word)
                )
                combined_q &= word_q
            expenses = expenses.filter(combined_q)
    
    # Apply filters
    if status:
        expenses = expenses.filter(status=status)
    if category:
        expenses = expenses.filter(category_id=category)
    if academic_session:
        expenses = expenses.filter(academic_session_id=academic_session)
    if fiscal_period:
        expenses = expenses.filter(fiscal_period_id=fiscal_period)
    
    # Apply date filters
    if expense_date_from:
        expenses = expenses.filter(expense_date__gte=expense_date_from)
    if expense_date_to:
        expenses = expenses.filter(expense_date__lte=expense_date_to)
    
    # Apply amount filters
    if min_amount:
        try:
            expenses = expenses.filter(total_amount__gte=Decimal(min_amount))
        except (ValueError, TypeError):
            pass
    if max_amount:
        try:
            expenses = expenses.filter(total_amount__lte=Decimal(max_amount))
        except (ValueError, TypeError):
            pass
    
    return expenses


def get_filtered_expense_payments(request):
    """Helper function to get filtered expense payments queryset"""
    payments = ExpensePayment.objects.select_related(
        'expense__category',
        'payment_method',
        'account',
        'fiscal_period'
    ).order_by('-payment_date', '-created_at')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    payment_state = request.GET.get('payment_state', '')
    payment_method = request.GET.get('payment_method', '')
    account = request.GET.get('account', '')
    fiscal_period = request.GET.get('fiscal_period', '')
    is_verified = request.GET.get('is_verified', '')
    payment_date_from = request.GET.get('payment_date_from', '')
    payment_date_to = request.GET.get('payment_date_to', '')
    min_amount = request.GET.get('min_amount', '')
    max_amount = request.GET.get('max_amount', '')
    
    # Apply text search
    if query:
        words = query.strip().split()
        if words:
            combined_q = Q()
            for word in words:
                word_q = (
                    Q(reference_number__icontains=word) |
                    Q(transaction_id__icontains=word) |
                    Q(expense__expense_number__icontains=word) |
                    Q(expense__vendor_name__icontains=word)
                )
                combined_q &= word_q
            payments = payments.filter(combined_q)
    
    # Apply filters
    if status:
        payments = payments.filter(status=status)
    
    if payment_state:
        if payment_state == 'active':
            payments = payments.filter(reversed=False)
        elif payment_state == 'reversed':
            payments = payments.filter(reversed=True)
    
    if payment_method:
        payments = payments.filter(payment_method_id=payment_method)
    if account:
        payments = payments.filter(account_id=account)
    if fiscal_period:
        payments = payments.filter(fiscal_period_id=fiscal_period)
    if is_verified:
        payments = payments.filter(is_verified=(is_verified.lower() == 'true'))
    
    # Apply date filters
    if payment_date_from:
        payments = payments.filter(payment_date__gte=payment_date_from)
    if payment_date_to:
        payments = payments.filter(payment_date__lte=payment_date_to)
    
    # Apply amount filters
    if min_amount:
        try:
            payments = payments.filter(amount__gte=Decimal(min_amount))
        except (ValueError, TypeError):
            pass
    if max_amount:
        try:
            payments = payments.filter(amount__lte=Decimal(max_amount))
        except (ValueError, TypeError):
            pass
    
    return payments


def get_filtered_journals(request):
    """Helper function to get filtered journals queryset"""
    journals = Journal.objects.annotate(
        entry_count=Count('entries', distinct=True)
    ).order_by('journal_type', 'name')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    journal_type = request.GET.get('journal_type', '')
    is_active = request.GET.get('is_active', '')
    
    # Apply text search
    if query:
        words = query.strip().split()
        if words:
            combined_q = Q()
            for word in words:
                word_q = (
                    Q(name__icontains=word) |
                    Q(description__icontains=word)
                )
                combined_q &= word_q
            journals = journals.filter(combined_q)
    
    # Apply filters
    if journal_type:
        journals = journals.filter(journal_type=journal_type)
    if is_active:
        journals = journals.filter(is_active=(is_active.lower() == 'true'))
    
    return journals


def get_filtered_journal_entries(request):
    """Helper function to get filtered journal entries queryset"""
    entries = JournalEntry.objects.select_related(
        'journal',
        'academic_session',
        'fiscal_period'
    ).prefetch_related(
        'transactions__account'
    ).annotate(
        transaction_count=Count('transactions', distinct=True),
        total_debit=Sum(
            Case(
                When(transactions__is_debit=True, then=F('transactions__amount')),
                default=0,
                output_field=DecimalField()
            )
        ),
        total_credit=Sum(
            Case(
                When(transactions__is_debit=False, then=F('transactions__amount')),
                default=0,
                output_field=DecimalField()
            )
        )
    ).order_by('-entry_date', '-created_at')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    journal = request.GET.get('journal', '')
    academic_session = request.GET.get('academic_session', '')
    fiscal_period = request.GET.get('fiscal_period', '')
    entry_date_from = request.GET.get('entry_date_from', '')
    entry_date_to = request.GET.get('entry_date_to', '')
    
    # Apply text search
    if query:
        words = query.strip().split()
        if words:
            combined_q = Q()
            for word in words:
                word_q = (
                    Q(entry_number__icontains=word) |
                    Q(reference_number__icontains=word) |
                    Q(description__icontains=word)
                )
                combined_q &= word_q
            entries = entries.filter(combined_q)
    
    # Apply filters
    if status:
        entries = entries.filter(status=status)
    if journal:
        entries = entries.filter(journal_id=journal)
    if academic_session:
        entries = entries.filter(academic_session_id=academic_session)
    if fiscal_period:
        entries = entries.filter(fiscal_period_id=fiscal_period)
    
    # Apply date filters
    if entry_date_from:
        entries = entries.filter(entry_date__gte=entry_date_from)
    if entry_date_to:
        entries = entries.filter(entry_date__lte=entry_date_to)
    
    return entries


def get_filtered_budgets(request):
    """Helper function to get filtered budgets queryset"""
    budgets = Budget.objects.select_related(
        'fiscal_year',
        'academic_session',
        'parent_budget'
    ).prefetch_related(
        'lines'
    ).annotate(
        line_count=Count('lines', distinct=True),
        child_count=Count('child_budgets', distinct=True)
    ).order_by('-start_date', 'name')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    budget_type = request.GET.get('budget_type', '')
    status = request.GET.get('status', '')
    fiscal_year = request.GET.get('fiscal_year', '')
    academic_session = request.GET.get('academic_session', '')
    
    # Apply text search
    if query:
        words = query.strip().split()
        if words:
            combined_q = Q()
            for word in words:
                word_q = (
                    Q(name__icontains=word) |
                    Q(description__icontains=word)
                )
                combined_q &= word_q
            budgets = budgets.filter(combined_q)
    
    # Apply filters
    if budget_type:
        budgets = budgets.filter(budget_type=budget_type)
    if status:
        budgets = budgets.filter(status=status)
    if fiscal_year:
        budgets = budgets.filter(fiscal_year_id=fiscal_year)
    if academic_session:
        budgets = budgets.filter(academic_session_id=academic_session)
    
    return budgets


# =============================================================================
# ACCOUNT TYPE VIEWS
# =============================================================================

@login_required
def account_type_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""
    filter_form = AccountTypeFilterForm(request.GET or None)
    account_types = get_filtered_account_types(request)
    
    # Calculate statistics
    stats = {
        'total': account_types.count(),
        'active': account_types.filter(is_active=True).count(),
        'asset': account_types.filter(account_type='ASSET').count(),
        'liability': account_types.filter(account_type='LIABILITY').count(),
        'equity': account_types.filter(account_type='EQUITY').count(),
        'revenue': account_types.filter(account_type='REVENUE').count(),
        'expense': account_types.filter(account_type='EXPENSE').count(),
        'total_accounts': sum(at.account_count or 0 for at in account_types),
    }
    
    # Pagination
    paginator = Paginator(account_types, 20)
    page_number = request.GET.get('page', 1)
    account_types_page = paginator.get_page(page_number)
    
    # Detect HTMX request
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'account_types_page': account_types_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    # Return appropriate template
    if is_htmx:
        return render(request, 'finance/account_types/partials/_type_results.html', context)
    else:
        return render(request, 'finance/account_types/list.html', context)


@login_required
def account_type_create(request):
    """Create new account type"""
    if request.method == 'POST':
        form = AccountTypeForm(request.POST)
        if form.is_valid():
            account_type = form.save()
            messages.success(
                request,
                f"Account type '{account_type.name}' created successfully",
                extra_tags='sweetalert'
            )
            return redirect('finance:account_type_detail', pk=account_type.pk)
    else:
        form = AccountTypeForm()
    
    context = {
        'form': form,
        'title': 'Create Account Type',
    }
    
    return render(request, 'finance/account_types/form.html', context)


@login_required
def account_type_edit(request, pk):
    """Edit existing account type"""
    account_type = get_object_or_404(AccountType, pk=pk)
    
    if request.method == 'POST':
        form = AccountTypeForm(request.POST, instance=account_type)
        if form.is_valid():
            account_type = form.save()
            messages.success(
                request,
                f"Account type '{account_type.name}' updated successfully",
                extra_tags='sweetalert'
            )
            return redirect('finance:account_type_detail', pk=account_type.pk)
    else:
        form = AccountTypeForm(instance=account_type)
    
    context = {
        'form': form,
        'account_type': account_type,
        'title': f'Edit {account_type.name}',
    }
    
    return render(request, 'finance/account_types/form.html', context)


@login_required
def account_type_detail(request, pk):
    """View account type details"""
    account_type = get_object_or_404(AccountType, pk=pk)
    
    # Get accounts under this type
    accounts = account_type.accounts.filter(
        is_active=True
    ).annotate(
        transaction_count=Count('journal_transactions')
    ).order_by('account_number')[:50]
    
    # Statistics
    account_count = account_type.accounts.count()
    active_count = account_type.accounts.filter(is_active=True).count()
    total_balance = account_type.accounts.aggregate(
        Sum('current_balance'))['current_balance__sum'] or Decimal('0.00')
    
    context = {
        'account_type': account_type,
        'accounts': accounts,
        'account_count': account_count,
        'active_count': active_count,
        'total_balance': total_balance,
    }
    
    return render(request, 'finance/account_types/detail.html', context)


@login_required
def account_type_delete(request, pk):
    """Delete account type with HTMX support"""
    account_type = get_object_or_404(AccountType, pk=pk)
    
    if request.method == 'POST':
        # Check if type has accounts
        if account_type.accounts.exists():
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f"Cannot delete '{account_type.name}' because it has associated accounts"
                response['HX-Alert-Type'] = 'error'
                response['HX-Alert-Title'] = 'Cannot Delete'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(
                    request,
                    f"Cannot delete '{account_type.name}' because it has associated accounts",
                    extra_tags='sweetalert-error'
                )
                return redirect('finance:account_type_list')
        
        type_name = account_type.name
        account_type.delete()
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Account type '{type_name}' deleted successfully"
            response['HX-Alert-Type'] = 'success'
            response['HX-Alert-Title'] = 'Deleted!'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('finance:account_type_list')
            return response
        else:
            messages.success(
                request,
                f"Account type '{type_name}' deleted successfully",
                extra_tags='sweetalert'
            )
            return redirect('finance:account_type_list')


# =============================================================================
# ACCOUNT VIEWS
# =============================================================================

@login_required
def account_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""
    filter_form = AccountFilterForm(request.GET or None)
    accounts = get_filtered_accounts(request)
    
    # Calculate statistics
    stats = {
        'total': accounts.count(),
        'active': accounts.filter(is_active=True).count(),
        'bank_accounts': accounts.filter(is_bank_account=True).count(),
        'cash_accounts': accounts.filter(is_cash_account=True).count(),
        'mobile_money': accounts.filter(is_mobile_money_account=True).count(),
        'total_balance': accounts.aggregate(Sum('current_balance'))['current_balance__sum'] or Decimal('0.00'),
    }
    
    # Pagination
    paginator = Paginator(accounts, 20)
    page_number = request.GET.get('page', 1)
    accounts_page = paginator.get_page(page_number)
    
    # Detect HTMX request
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'accounts_page': accounts_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    # Return appropriate template
    if is_htmx:
        return render(request, 'finance/accounts/partials/_account_results.html', context)
    else:
        return render(request, 'finance/accounts/list.html', context)


@login_required
def account_create(request):
    """Create new account"""
    if request.method == 'POST':
        form = AccountForm(request.POST)
        if form.is_valid():
            account = form.save()
            messages.success(
                request,
                f"Account '{account.name}' ({account.account_number}) created successfully",
                extra_tags='sweetalert'
            )
            return redirect('finance:account_detail', pk=account.pk)
    else:
        form = AccountForm()
    
    context = {
        'form': form,
        'title': 'Create Account',
    }
    
    return render(request, 'finance/accounts/form.html', context)


@login_required
def account_edit(request, pk):
    """Edit existing account"""
    account = get_object_or_404(Account, pk=pk)
    
    if request.method == 'POST':
        form = AccountForm(request.POST, instance=account)
        if form.is_valid():
            account = form.save()
            messages.success(
                request,
                f"Account '{account.name}' updated successfully",
                extra_tags='sweetalert'
            )
            return redirect('finance:account_detail', pk=account.pk)
    else:
        form = AccountForm(instance=account)
    
    context = {
        'form': form,
        'account': account,
        'title': f'Edit {account.name}',
    }
    
    return render(request, 'finance/accounts/form.html', context)


@login_required
def account_detail(request, pk):
    """View account details"""
    account = get_object_or_404(
        Account.objects.select_related('account_type', 'parent_account'),
        pk=pk
    )
    
    # Get recent transactions
    transactions = account.journal_transactions.select_related(
        'journal_entry__journal',
        'journal_entry__fiscal_period'
    ).order_by('-journal_entry__entry_date', '-created_at')[:50]
    
    # Get child accounts
    child_accounts = account.child_accounts.filter(
        is_active=True
    ).annotate(
        transaction_count=Count('journal_transactions')
    ).order_by('account_number')
    
    # Statistics
    transaction_count = account.journal_transactions.count()
    
    # Calculate debit/credit totals
    debit_total = account.journal_transactions.filter(
        is_debit=True,
        journal_entry__status='POSTED'
    ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    
    credit_total = account.journal_transactions.filter(
        is_debit=False,
        journal_entry__status='POSTED'
    ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    
    context = {
        'account': account,
        'transactions': transactions,
        'child_accounts': child_accounts,
        'transaction_count': transaction_count,
        'debit_total': debit_total,
        'credit_total': credit_total,
    }
    
    return render(request, 'finance/accounts/detail.html', context)


@login_required
def account_delete(request, pk):
    """Delete account with HTMX support"""
    account = get_object_or_404(Account, pk=pk)
    
    if request.method == 'POST':
        # Check if account has transactions
        if account.journal_transactions.exists():
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f"Cannot delete '{account.name}' because it has transactions"
                response['HX-Alert-Type'] = 'error'
                response['HX-Alert-Title'] = 'Cannot Delete'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(
                    request,
                    f"Cannot delete '{account.name}' because it has transactions",
                    extra_tags='sweetalert-error'
                )
                return redirect('finance:account_list')
        
        # Check for child accounts
        if account.child_accounts.exists():
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f"Cannot delete '{account.name}' because it has child accounts"
                response['HX-Alert-Type'] = 'error'
                response['HX-Alert-Title'] = 'Cannot Delete'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(
                    request,
                    f"Cannot delete '{account.name}' because it has child accounts",
                    extra_tags='sweetalert-error'
                )
                return redirect('finance:account_list')
        
        account_name = f"{account.account_number} - {account.name}"
        account.delete()
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Account '{account_name}' deleted successfully"
            response['HX-Alert-Type'] = 'success'
            response['HX-Alert-Title'] = 'Deleted!'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('finance:account_list')
            return response
        else:
            messages.success(
                request,
                f"Account '{account_name}' deleted successfully",
                extra_tags='sweetalert'
            )
            return redirect('finance:account_list')


@login_required
def account_toggle_active(request, pk):
    """Toggle account active status with HTMX support"""
    account = get_object_or_404(Account, pk=pk)
    
    if request.method == 'POST':
        account.is_active = not account.is_active
        account.save(update_fields=['is_active', 'updated_at'])
        
        status = "activated" if account.is_active else "deactivated"
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Account {account.account_number} {status}"
            response['HX-Alert-Type'] = 'success' if account.is_active else 'warning'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('finance:account_detail', kwargs={'pk': pk})
            return response
        else:
            messages.success(request, f"Account {status}", extra_tags='sweetalert')
            return redirect('finance:account_detail', pk=pk)


@login_required
def account_reconcile(request, pk):
    """Reconcile account"""
    account = get_object_or_404(Account, pk=pk)
    
    if not account.is_reconcilable:
        messages.warning(request, f"Account '{account.name}' is not marked as reconcilable.")
        return redirect('finance:account_detail', pk=pk)
    
    if request.method == 'POST':
        form = AccountReconciliationForm(request.POST)
        if form.is_valid():
            try:
                reconciliation_date = form.cleaned_data['reconciliation_date']
                statement_balance = form.cleaned_data['statement_balance']
                notes = form.cleaned_data['notes']
                
                # Calculate difference
                difference = account.current_balance - statement_balance
                
                # Update account reconciliation info
                account.last_reconciled_date = reconciliation_date
                account.reconciliation_balance = statement_balance
                account.save(update_fields=['last_reconciled_date', 'reconciliation_balance', 'updated_at'])
                
                messages.success(
                    request,
                    f"Account reconciled. Difference: {format_money(abs(difference))}",
                    extra_tags='sweetalert'
                )
                return redirect('finance:account_detail', pk=account.pk)
                
            except Exception as e:
                logger.error(f"Error reconciling account: {e}")
                messages.error(request, f"Error reconciling account: {str(e)}", extra_tags='sweetalert-error')
    else:
        form = AccountReconciliationForm(initial={'account': account})
    
    context = {
        'form': form,
        'account': account,
        'title': f'Reconcile Account - {account.name}',
    }
    
    return render(request, 'finance/accounts/reconcile.html', context)


@login_required
def account_print_view(request, pk):
    """Generate printable account statement"""
    account = get_object_or_404(Account, pk=pk)
    
    # Get filter parameters
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    # Build transaction queryset
    transactions = account.journal_transactions.select_related(
        'journal_entry__journal',
        'journal_entry__fiscal_period'
    ).filter(
        journal_entry__status='POSTED'
    ).order_by('journal_entry__entry_date', 'created_at')
    
    # Apply date filters if provided
    if date_from:
        transactions = transactions.filter(journal_entry__entry_date__gte=date_from)
    if date_to:
        transactions = transactions.filter(journal_entry__entry_date__lte=date_to)
    
    # Calculate opening balance for the period
    if date_from:
        opening_debits = account.journal_transactions.filter(
            is_debit=True,
            journal_entry__status='POSTED',
            journal_entry__entry_date__lt=date_from
        ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
        
        opening_credits = account.journal_transactions.filter(
            is_debit=False,
            journal_entry__status='POSTED',
            journal_entry__entry_date__lt=date_from
        ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
        
        opening_balance = opening_debits - opening_credits
    else:
        opening_balance = Decimal('0.00')
    
    # Calculate totals
    total_debits = transactions.filter(is_debit=True).aggregate(
        Sum('amount'))['amount__sum'] or Decimal('0.00')
    total_credits = transactions.filter(is_debit=False).aggregate(
        Sum('amount'))['amount__sum'] or Decimal('0.00')
    closing_balance = opening_balance + total_debits - total_credits
    
    context = {
        'account': account,
        'transactions': transactions,
        'opening_balance': opening_balance,
        'total_debits': total_debits,
        'total_credits': total_credits,
        'closing_balance': closing_balance,
        'date_from': date_from,
        'date_to': date_to,
        'now': timezone.now(),
        'title': f'Account Statement - {account.name}',
    }
    
    return render(request, 'finance/accounts/print_statement.html', context)


@login_required
def export_accounts_excel(request):
    """Export accounts to Excel with filters applied"""
    
    accounts = get_filtered_accounts(request)
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Accounts"
    
    # Define styles
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_alignment = Alignment(horizontal="center", vertical="center")
    
    # Headers
    headers = [
        '#', 'Account Number', 'Account Name', 'Account Type',
        'Category', 'Current Balance', 'Active'
    ]
    ws.append(headers)
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
    
    # Data rows
    for idx, account in enumerate(accounts, start=1):
        ws.append([
            idx,
            account.account_number,
            account.name,
            account.account_type.name,
            account.get_category_display(),
            float(account.current_balance),
            'Yes' if account.is_active else 'No',
        ])
    
    # Auto-adjust column widths
    for column in ws.columns:
        max_length = 0
        column_letter = get_column_letter(column[0].column)
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(cell.value)
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        ws.column_dimensions[column_letter].width = adjusted_width
    
    # Create response
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"accounts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


# =============================================================================
# EXPENSE CATEGORY VIEWS
# =============================================================================

@login_required
def expense_category_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""
    filter_form = ExpenseCategoryFilterForm(request.GET or None)
    categories = get_filtered_expense_categories(request)
    
    # Calculate statistics
    stats = {
        'total': categories.count(),
        'active': categories.filter(is_active=True).count(),
        'requires_approval': categories.filter(requires_approval=True).count(),
        'total_expenses': sum(c.expense_count or 0 for c in categories),
    }
    
    # Pagination
    paginator = Paginator(categories, 10)
    page_number = request.GET.get('page', 1)
    categories_page = paginator.get_page(page_number)
    
    # Detect HTMX request
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'categories_page': categories_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    # Return appropriate template
    if is_htmx:
        return render(request, 'finance/expense_categories/partials/_category_results.html', context)
    else:
        return render(request, 'finance/expense_categories/list.html', context)


@login_required
def expense_category_create(request):
    """Create new expense category"""
    if request.method == 'POST':
        form = ExpenseCategoryForm(request.POST)
        if form.is_valid():
            category = form.save()
            messages.success(
                request,
                f"Expense category '{category.name}' created successfully",
                extra_tags='sweetalert'
            )
            return redirect('finance:expense_category_detail', pk=category.pk)
    else:
        form = ExpenseCategoryForm()
    
    context = {
        'form': form,
        'title': 'Create Expense Category',
    }
    
    return render(request, 'finance/expense_categories/form.html', context)


@login_required
def expense_category_edit(request, pk):
    """Edit existing expense category"""
    category = get_object_or_404(ExpenseCategory, pk=pk)
    
    if request.method == 'POST':
        form = ExpenseCategoryForm(request.POST, instance=category)
        if form.is_valid():
            category = form.save()
            messages.success(
                request,
                f"Expense category '{category.name}' updated successfully",
                extra_tags='sweetalert'
            )
            return redirect('finance:expense_category_detail', pk=category.pk)
    else:
        form = ExpenseCategoryForm(instance=category)
    
    context = {
        'form': form,
        'category': category,
        'title': f'Edit {category.name}',
    }
    
    return render(request, 'finance/expense_categories/form.html', context)


@login_required
def expense_category_detail(request, pk):
    """View expense category details"""
    category = get_object_or_404(
        ExpenseCategory.objects.select_related('default_expense_account'),
        pk=pk
    )
    
    # Get recent expenses in this category
    expenses = category.expenses.select_related(
        'fiscal_period', 'academic_session'
    ).order_by('-expense_date')[:50]
    
    # Statistics
    expense_count = category.expenses.count()
    total_amount = category.expenses.filter(
        status__in=['APPROVED', 'PAID']
    ).aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0.00')
    
    # This month
    today = get_school_today()
    this_month_start = today.replace(day=1)
    this_month_amount = category.expenses.filter(
        expense_date__gte=this_month_start,
        status__in=['APPROVED', 'PAID']
    ).aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0.00')
    
    context = {
        'category': category,
        'expenses': expenses,
        'expense_count': expense_count,
        'total_amount': total_amount,
        'this_month_amount': this_month_amount,
    }
    
    return render(request, 'finance/expense_categories/detail.html', context)


@login_required
def expense_category_delete(request, pk):
    """Delete expense category with HTMX support"""
    category = get_object_or_404(ExpenseCategory, pk=pk)
    
    if request.method == 'POST':
        # Check if category has expenses
        if category.expenses.exists():
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f"Cannot delete '{category.name}' because it has associated expenses"
                response['HX-Alert-Type'] = 'error'
                response['HX-Alert-Title'] = 'Cannot Delete'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(
                    request,
                    f"Cannot delete '{category.name}' because it has associated expenses",
                    extra_tags='sweetalert-error'
                )
                return redirect('finance:expense_category_list')
        
        category_name = category.name
        category.delete()
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Category '{category_name}' deleted successfully"
            response['HX-Alert-Type'] = 'success'
            response['HX-Alert-Title'] = 'Deleted!'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('finance:expense_category_list')
            return response
        else:
            messages.success(
                request,
                f"Category '{category_name}' deleted successfully",
                extra_tags='sweetalert'
            )
            return redirect('finance:expense_category_list')


@login_required
def expense_category_toggle_active(request, pk):
    """Toggle expense category active status with HTMX support"""
    category = get_object_or_404(ExpenseCategory, pk=pk)
    
    if request.method == 'POST':
        category.is_active = not category.is_active
        category.save(update_fields=['is_active', 'updated_at'])
        
        status = "activated" if category.is_active else "deactivated"
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Category '{category.name}' {status}"
            response['HX-Alert-Type'] = 'success' if category.is_active else 'warning'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('finance:expense_category_detail', kwargs={'pk': pk})
            return response
        else:
            messages.success(request, f"Category {status}", extra_tags='sweetalert')
            return redirect('finance:expense_category_detail', pk=pk)

@login_required
def expense_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""
    filter_form = ExpenseFilterForm(request.GET or None)
    expenses = get_filtered_expenses(request)
    
    # Calculate statistics
    stats = {
        'total': expenses.count(),
        'draft': expenses.filter(status='DRAFT').count(),
        'pending_approval': expenses.filter(status='PENDING_APPROVAL').count(),
        'approved': expenses.filter(status='APPROVED').count(),
        'paid': expenses.filter(status='PAID').count(),
        'rejected': expenses.filter(status='REJECTED').count(),
        'total_amount': expenses.aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0.00'),
        'approved_amount': expenses.filter(status__in=['APPROVED', 'PAID']).aggregate(
            Sum('total_amount'))['total_amount__sum'] or Decimal('0.00'),
    }
    
    # Pagination
    paginator = Paginator(expenses, 10)
    page_number = request.GET.get('page', 1)
    expenses_page = paginator.get_page(page_number)
    
    # Detect HTMX request
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'expenses_page': expenses_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    # Return appropriate template
    if is_htmx:
        return render(request, 'finance/expenses/partials/_expense_results.html', context)
    else:
        return render(request, 'finance/expenses/list.html', context)


@login_required
def expense_create(request):
    """Create new expense"""
    if request.method == 'POST':
        form = ExpenseForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                # Use service to create expense
                expense = ExpenseService.create_expense(
                    expense_data=form.cleaned_data,
                    user=request.user
                )
                
                messages.success(
                    request,
                    f"Expense {expense.expense_number} created successfully",
                    extra_tags='sweetalert'
                )
                return redirect('finance:expense_detail', pk=expense.pk)
                
            except Exception as e:
                logger.error(f"Error creating expense: {e}")
                messages.error(
                    request,
                    f"Error creating expense: {str(e)}",
                    extra_tags='sweetalert-error'
                )
    else:
        form = ExpenseForm()
    
    context = {
        'form': form,
        'title': 'Create Expense',
    }
    
    return render(request, 'finance/expenses/form.html', context)


@login_required
def expense_edit(request, pk):
    """Edit existing expense"""
    expense = get_object_or_404(Expense, pk=pk)
    
    # Check if expense can be edited
    if expense.status in ['APPROVED', 'PAID']:
        messages.warning(
            request,
            f"Cannot edit expense with status: {expense.get_status_display()}",
            extra_tags='sweetalert'
        )
        return redirect('finance:expense_detail', pk=pk)
    
    if request.method == 'POST':
        form = ExpenseForm(request.POST, request.FILES, instance=expense)
        if form.is_valid():
            try:
                expense = form.save()
                
                messages.success(
                    request,
                    f"Expense {expense.expense_number} updated successfully",
                    extra_tags='sweetalert'
                )
                return redirect('finance:expense_detail', pk=expense.pk)
                
            except Exception as e:
                logger.error(f"Error updating expense: {e}")
                messages.error(
                    request,
                    f"Error updating expense: {str(e)}",
                    extra_tags='sweetalert-error'
                )
    else:
        form = ExpenseForm(instance=expense)
    
    context = {
        'form': form,
        'expense': expense,
        'title': f'Edit Expense {expense.expense_number}',
    }
    
    return render(request, 'finance/expenses/form.html', context)


@login_required
def expense_detail(request, pk):
    """View expense details"""
    expense = get_object_or_404(
        Expense.objects.select_related(
            'category',
            'academic_session',
            'fiscal_period',
            'expense_account',
            'budget_line',
            'journal_entry'
        ).prefetch_related('lines', 'payments'),
        pk=pk
    )
    
    # Get related items
    lines = expense.lines.select_related('expense_account', 'tax_rate')
    payments = expense.payments.select_related('payment_method', 'account').order_by('-payment_date')
    
    # Calculate payment summary
    total_paid = sum(p.amount for p in payments if p.is_active)
    remaining = expense.total_amount - total_paid
    
    context = {
        'expense': expense,
        'lines': lines,
        'payments': payments,
        'total_paid': total_paid,
        'remaining': remaining,
    }
    
    return render(request, 'finance/expenses/detail.html', context)


@login_required
def expense_delete(request, pk):
    """Delete expense with HTMX support"""
    expense = get_object_or_404(Expense, pk=pk)
    
    if request.method == 'POST':
        # Check if expense can be deleted
        if expense.status in ['APPROVED', 'PAID']:
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f"Cannot delete expense with status: {expense.get_status_display()}"
                response['HX-Alert-Type'] = 'error'
                response['HX-Alert-Title'] = 'Cannot Delete'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(
                    request,
                    f"Cannot delete expense with status: {expense.get_status_display()}",
                    extra_tags='sweetalert-error'
                )
                return redirect('finance:expense_list')
        
        # Check for payments
        if expense.payments.filter(reversed=False).exists():
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f"Cannot delete expense with active payments"
                response['HX-Alert-Type'] = 'error'
                response['HX-Alert-Title'] = 'Cannot Delete'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(
                    request,
                    "Cannot delete expense with active payments",
                    extra_tags='sweetalert-error'
                )
                return redirect('finance:expense_list')
        
        expense_number = expense.expense_number
        expense.delete()
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Expense {expense_number} deleted successfully"
            response['HX-Alert-Type'] = 'success'
            response['HX-Alert-Title'] = 'Deleted!'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('finance:expense_list')
            return response
        else:
            messages.success(
                request,
                f"Expense {expense_number} deleted successfully",
                extra_tags='sweetalert'
            )
            return redirect('finance:expense_list')


@login_required
def expense_submit(request, pk):
    """Submit expense for approval with HTMX support"""
    expense = get_object_or_404(Expense, pk=pk)
    
    if request.method == 'POST':
        if expense.status != 'DRAFT':
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f"Can only submit draft expenses"
                response['HX-Alert-Type'] = 'warning'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.warning(request, "Can only submit draft expenses", extra_tags='sweetalert')
                return redirect('finance:expense_detail', pk=pk)
        
        try:
            # Use service to submit expense
            ExpenseService.submit_expense(expense, user=request.user)
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f"Expense {expense.expense_number} submitted for approval"
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('finance:expense_detail', kwargs={'pk': pk})
                return response
            else:
                messages.success(
                    request,
                    f"Expense submitted for approval",
                    extra_tags='sweetalert'
                )
                return redirect('finance:expense_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error submitting expense: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f"Error submitting expense: {str(e)}"
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(
                    request,
                    f"Error submitting expense: {str(e)}",
                    extra_tags='sweetalert-error'
                )
                return redirect('finance:expense_detail', pk=pk)


@login_required
def expense_approve(request, pk):
    """Approve expense with HTMX support"""
    expense = get_object_or_404(Expense, pk=pk)
    
    if request.method == 'POST':
        form = ExpenseApprovalForm(request.POST)
        if form.is_valid():
            try:
                decision = form.cleaned_data['decision']
                notes = form.cleaned_data['notes']
                
                if decision == 'APPROVE':
                    # Use service to approve expense
                    ExpenseService.approve_expense(
                        expense=expense,
                        user=request.user,
                        notes=notes
                    )
                    
                    message = f"Expense {expense.expense_number} approved successfully"
                    alert_type = 'success'
                else:  # REJECT
                    # Use service to reject expense
                    ExpenseService.reject_expense(
                        expense=expense,
                        user=request.user,
                        reason=notes
                    )
                    
                    message = f"Expense {expense.expense_number} rejected"
                    alert_type = 'warning'
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = message
                    response['HX-Alert-Type'] = alert_type
                    response['HX-Close-Modal'] = 'true'
                    response['HX-Redirect'] = reverse('finance:expense_detail', kwargs={'pk': pk})
                    return response
                else:
                    if alert_type == 'success':
                        messages.success(request, message, extra_tags='sweetalert')
                    else:
                        messages.warning(request, message, extra_tags='sweetalert')
                    return redirect('finance:expense_detail', pk=pk)
                    
            except Exception as e:
                logger.error(f"Error processing expense approval: {e}")
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f"Error: {str(e)}"
                    response['HX-Alert-Type'] = 'error'
                    response['HX-Close-Modal'] = 'true'
                    return response
                else:
                    messages.error(request, f"Error: {str(e)}", extra_tags='sweetalert-error')
                    return redirect('finance:expense_detail', pk=pk)


@login_required
def expense_print_view(request, pk):
    """Generate printable expense"""
    expense = get_object_or_404(
        Expense.objects.select_related(
            'category',
            'fiscal_period',
            'fiscal_period__fiscal_year',
            'academic_session',
            'expense_account',
            'budget_line__budget',
            'budget_line__account',
            'journal_entry',
        ).prefetch_related(
            'lines__expense_account',
            'lines__tax_rate',
            'lines__unit_of_measure',
            'payments__payment_method',
            'payments__account',
        ),
        pk=pk
    )

    payments = expense.payments.select_related(
        'payment_method', 'account'
    ).order_by('-payment_date')

    lines = expense.lines.select_related(
        'expense_account', 'tax_rate', 'unit_of_measure'
    )

    total_paid = sum(p.amount for p in payments if p.is_active)
    remaining  = expense.total_amount - total_paid

    context = {
        'expense':   expense,
        'lines':     lines,
        'payments':  payments,
        'total_paid': total_paid,
        'remaining':  remaining,
        'now':        timezone.now(),
        'title':      f'Expense {expense.expense_number}',
    }

    return render(request, 'finance/expenses/print.html', context)


@login_required
def export_expenses_excel(request):
    """Export expenses to Excel with filters applied"""
    
    expenses = get_filtered_expenses(request)
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Expenses"
    
    # Define styles
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_alignment = Alignment(horizontal="center", vertical="center")
    
    # Headers
    headers = [
        '#', 'Expense Number', 'Date', 'Category', 'Description',
        'Vendor', 'Total Amount', 'Status'
    ]
    ws.append(headers)
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
    
    # Data rows
    for idx, expense in enumerate(expenses, start=1):
        ws.append([
            idx,
            expense.expense_number,
            expense.expense_date.strftime('%Y-%m-%d'),
            expense.category.name,
            expense.description,
            expense.vendor_name or '',
            float(expense.total_amount),
            expense.get_status_display(),
        ])
    
    # Auto-adjust column widths
    for column in ws.columns:
        max_length = 0
        column_letter = get_column_letter(column[0].column)
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(cell.value)
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        ws.column_dimensions[column_letter].width = adjusted_width
    
    # Create response
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"expenses_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


# =============================================================================
# EXPENSE PAYMENT VIEWS
# =============================================================================

@login_required
def expense_payment_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""
    filter_form = ExpensePaymentFilterForm(request.GET or None)
    payments = get_filtered_expense_payments(request)
    
    # Calculate statistics
    stats = {
        'total': payments.count(),
        'pending': payments.filter(status='PENDING').count(),
        'processed': payments.filter(status='PROCESSED').count(),
        'verified': payments.filter(is_verified=True).count(),
        'reversed': payments.filter(reversed=True).count(),
        'total_amount': payments.filter(reversed=False).aggregate(
            Sum('amount'))['amount__sum'] or Decimal('0.00'),
    }
    
    # Pagination
    paginator = Paginator(payments, 10)
    page_number = request.GET.get('page', 1)
    payments_page = paginator.get_page(page_number)
    
    # Detect HTMX request
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'payments_page': payments_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    # Return appropriate template
    if is_htmx:
        return render(request, 'finance/expense_payments/partials/_payment_results.html', context)
    else:
        return render(request, 'finance/expense_payments/list.html', context)


@login_required
def expense_payment_create(request, expense_pk=None):
    """Create new expense payment"""
    expense = None
    if expense_pk:
        expense = get_object_or_404(Expense, pk=expense_pk)
        
        # Check if expense can accept payments
        if expense.status not in ['APPROVED', 'PAID']:
            messages.warning(
                request,
                f"Cannot process payment for expense with status: {expense.get_status_display()}",
                extra_tags='sweetalert'
            )
            return redirect('finance:expense_detail', pk=expense.pk)
    
    if request.method == 'POST':
        form = ExpensePaymentForm(request.POST)
        if form.is_valid():
            try:
                # Use service to create payment
                payment = ExpensePaymentService.create_payment(
                    payment_data=form.cleaned_data,
                    user=request.user
                )
                
                messages.success(
                    request,
                    "Payment recorded successfully",
                    extra_tags='sweetalert'
                )
                return redirect('finance:expense_payment_detail', pk=payment.pk)
                
            except Exception as e:
                logger.error(f"Error creating payment: {e}")
                messages.error(
                    request,
                    f"Error creating payment: {str(e)}",
                    extra_tags='sweetalert-error'
                )
    else:
        initial = {'expense': expense} if expense else {}
        form = ExpensePaymentForm(initial=initial)
    
    context = {
        'form': form,
        'expense': expense,
        'title': 'Record Expense Payment',
    }
    
    return render(request, 'finance/expense_payments/form.html', context)


@login_required
def expense_payment_edit(request, pk):
    """Edit existing expense payment"""
    payment = get_object_or_404(ExpensePayment, pk=pk)
    
    # Check if payment can be edited
    if payment.reversed:
        messages.warning(
            request,
            "Cannot edit reversed payment",
            extra_tags='sweetalert'
        )
        return redirect('finance:expense_payment_detail', pk=pk)
    
    if payment.is_verified:
        messages.warning(
            request,
            "Cannot edit verified payment",
            extra_tags='sweetalert'
        )
        return redirect('finance:expense_payment_detail', pk=pk)
    
    if request.method == 'POST':
        form = ExpensePaymentForm(request.POST, instance=payment)
        if form.is_valid():
            try:
                payment = form.save()
                
                messages.success(
                    request,
                    "Payment updated successfully",
                    extra_tags='sweetalert'
                )
                return redirect('finance:expense_payment_detail', pk=payment.pk)
                
            except Exception as e:
                logger.error(f"Error updating payment: {e}")
                messages.error(
                    request,
                    f"Error updating payment: {str(e)}",
                    extra_tags='sweetalert-error'
                )
    else:
        form = ExpensePaymentForm(instance=payment)
    
    context = {
        'form': form,
        'payment': payment,
        'title': 'Edit Payment',
    }
    
    return render(request, 'finance/expense_payments/form.html', context)


@login_required
def expense_payment_detail(request, pk):
    """View payment details"""
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
    
    context = {
        'payment': payment,
        'audit_trail': audit_trail,
    }
    
    return render(request, 'finance/expense_payments/detail.html', context)


@login_required
def expense_payment_delete(request, pk):
    """Delete expense payment with HTMX support"""
    payment = get_object_or_404(ExpensePayment, pk=pk)
    
    if request.method == 'POST':
        # Check if payment can be deleted
        if payment.is_verified:
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = "Cannot delete verified payment"
                response['HX-Alert-Type'] = 'error'
                response['HX-Alert-Title'] = 'Cannot Delete'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(
                    request,
                    "Cannot delete verified payment",
                    extra_tags='sweetalert-error'
                )
                return redirect('finance:expense_payment_list')
        
        if payment.reversed:
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = "Cannot delete reversed payment"
                response['HX-Alert-Type'] = 'error'
                response['HX-Alert-Title'] = 'Cannot Delete'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(
                    request,
                    "Cannot delete reversed payment",
                    extra_tags='sweetalert-error'
                )
                return redirect('finance:expense_payment_list')
        
        reference = payment.reference_number or 'Payment'
        payment.delete()
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Payment deleted successfully"
            response['HX-Alert-Type'] = 'success'
            response['HX-Alert-Title'] = 'Deleted!'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('finance:expense_payment_list')
            return response
        else:
            messages.success(
                request,
                "Payment deleted successfully",
                extra_tags='sweetalert'
            )
            return redirect('finance:expense_payment_list')


@login_required
def expense_payment_verify(request, pk):
    """Verify expense payment with HTMX support"""
    payment = get_object_or_404(ExpensePayment, pk=pk)
    
    if request.method == 'POST':
        if payment.is_verified:
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = "Payment is already verified"
                response['HX-Alert-Type'] = 'warning'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.warning(request, "Payment is already verified", extra_tags='sweetalert')
                return redirect('finance:expense_payment_detail', pk=pk)
        
        try:
            # Use service to verify payment
            ExpensePaymentService.verify_payment(payment, user=request.user)
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = "Payment verified successfully"
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('finance:expense_payment_detail', kwargs={'pk': pk})
                return response
            else:
                messages.success(request, "Payment verified successfully", extra_tags='sweetalert')
                return redirect('finance:expense_payment_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error verifying payment: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f"Error: {str(e)}"
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f"Error: {str(e)}", extra_tags='sweetalert-error')
                return redirect('finance:expense_payment_detail', pk=pk)


@login_required
def expense_payment_reverse(request, pk):
    """Reverse expense payment with HTMX support"""
    payment = get_object_or_404(ExpensePayment, pk=pk)
    
    if request.method == 'POST':
        form = ExpensePaymentReversalForm(payment, request.user, request.POST)
        if form.is_valid():
            try:
                reversal_reason = form.cleaned_data['reversal_reason']
                
                # Use service to reverse payment
                ExpensePaymentService.reverse_payment(
                    payment=payment,
                    user=request.user,
                    reason=reversal_reason
                )
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = "Payment reversed successfully"
                    response['HX-Alert-Type'] = 'success'
                    response['HX-Close-Modal'] = 'true'
                    response['HX-Redirect'] = reverse('finance:expense_payment_detail', kwargs={'pk': pk})
                    return response
                else:
                    messages.success(request, "Payment reversed successfully", extra_tags='sweetalert')
                    return redirect('finance:expense_payment_detail', pk=pk)
                    
            except Exception as e:
                logger.error(f"Error reversing payment: {e}")
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f"Error: {str(e)}"
                    response['HX-Alert-Type'] = 'error'
                    response['HX-Close-Modal'] = 'true'
                    return response
                else:
                    messages.error(request, f"Error: {str(e)}", extra_tags='sweetalert-error')
                    return redirect('finance:expense_payment_detail', pk=pk)


@login_required
def bulk_expense_payment_verification(request):
    """Bulk verify expense payments"""
    if request.method == 'POST':
        form = BulkExpensePaymentVerificationForm(request.POST)
        if form.is_valid():
            try:
                payment_ids = form.cleaned_data['payment_ids']
                verification_notes = form.cleaned_data.get('verification_notes', '')
                
                # Get payments
                payments = ExpensePayment.objects.filter(
                    id__in=payment_ids,
                    is_verified=False,
                    status='PROCESSED',
                    reversed=False
                )
                
                verified_count = 0
                
                with transaction.atomic():
                    for payment in payments:
                        try:
                            ExpensePaymentService.verify_payment(payment, user=request.user)
                            verified_count += 1
                        except Exception as e:
                            logger.error(f"Error verifying payment {payment.pk}: {e}")
                
                messages.success(
                    request,
                    f"Successfully verified {verified_count} payment(s)",
                    extra_tags='sweetalert'
                )
                
            except Exception as e:
                logger.error(f"Error in bulk verification: {e}")
                messages.error(
                    request,
                    f"Error: {str(e)}",
                    extra_tags='sweetalert-error'
                )
        
        return redirect('finance:expense_payment_list')


@login_required
def expense_payment_print_view(request):
    """Generate printable expense payment list"""
    
    payments = get_filtered_expense_payments(request)
    
    # Calculate totals
    total_amount = payments.filter(reversed=False).aggregate(
        Sum('amount'))['amount__sum'] or Decimal('0.00')
    total_fees = payments.filter(reversed=False).aggregate(
        Sum('processing_fee'))['processing_fee__sum'] or Decimal('0.00')
    
    context = {
        'payments': payments,
        'total_amount': total_amount,
        'total_fees': total_fees,
        'now': timezone.now(),
        'title': 'Expense Payments Report',
    }
    
    return render(request, 'finance/expense_payments/print.html', context)


@login_required
def export_expense_payments_excel(request):
    """Export expense payments to Excel with filters applied"""
    
    payments = get_filtered_expense_payments(request)
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Expense Payments"
    
    # Define styles
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_alignment = Alignment(horizontal="center", vertical="center")
    
    # Headers
    headers = [
        '#', 'Reference', 'Date', 'Expense Number', 'Amount',
        'Payment Method', 'Status', 'Verified', 'Reversed'
    ]
    ws.append(headers)
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
    
    # Data rows
    for idx, payment in enumerate(payments, start=1):
        ws.append([
            idx,
            payment.reference_number or '',
            payment.payment_date.strftime('%Y-%m-%d'),
            payment.expense.expense_number,
            float(payment.amount),
            payment.payment_method.name if payment.payment_method else '',
            payment.get_status_display(),
            'Yes' if payment.is_verified else 'No',
            'Yes' if payment.reversed else 'No',
        ])
    
    # Auto-adjust column widths
    for column in ws.columns:
        max_length = 0
        column_letter = get_column_letter(column[0].column)
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(cell.value)
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        ws.column_dimensions[column_letter].width = adjusted_width
    
    # Create response
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"expense_payments_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response

@login_required
def expense_payment_print_receipt(request, pk):
    """
    Generate a printable payment receipt for an expense payment.
    
    Renders a clean, printer-friendly receipt showing:
    - Payment details (reference, date, amount)
    - Expense details (number, description, vendor)
    - Account and payment method info
    - Verification status
    - Reversal notice (if reversed)
    - Journal entry reference
    """
    payment = get_object_or_404(
        ExpensePayment.objects.select_related(
            'expense__category',
            'expense__fiscal_period',
            'payment_method',
            'account',
            'fiscal_period',
            'journal_entry',
            'reversal_journal_entry',
        ),
        pk=pk
    )

    # Resolve user display names safely
    performed_by_user = payment.get_performed_by_user()
    verified_by_user  = payment.get_verified_by_user()
    reversed_by_user  = payment.get_reversed_by_user()

    context = {
        'payment': payment,
        'performed_by_user': performed_by_user,
        'verified_by_user': verified_by_user,
        'reversed_by_user': reversed_by_user,
        'now': timezone.now(),
        'title': f'Payment Receipt – {payment.reference_number or payment.pk}',
    }

    return render(request, 'finance/expense_payments/print_receipt.html', context)

@login_required
def expense_payment_reversal_detail(request, pk):
    """
    Display full reversal details for a reversed expense payment.

    The URL pk is the pk of the *original* payment that was reversed.
    This view shows:
    - Original payment info
    - Who reversed it, when, and why
    - The reversing journal entry
    - Full audit trail
    
    Note: There is no separate Reversal model – reversal metadata is stored
    directly on the ExpensePayment instance (reversed=True, reversed_on,
    reversed_by_id, reversal_reason, reversal_journal_entry).
    """
    payment = get_object_or_404(
        ExpensePayment.objects.select_related(
            'expense__category',
            'expense__fiscal_period',
            'payment_method',
            'account',
            'fiscal_period',
            'journal_entry',
            'reversal_journal_entry',
        ),
        pk=pk
    )

    # This view only makes sense for reversed payments
    if not payment.reversed:
        messages.warning(
            request,
            "This payment has not been reversed.",
            extra_tags='sweetalert'
        )
        return redirect('finance:expense_payment_detail', pk=pk)

    # Resolve user objects
    performed_by_user         = payment.get_performed_by_user()
    verified_by_user          = payment.get_verified_by_user()
    reversed_by_user          = payment.get_reversed_by_user()
    reversal_approved_by_user = payment.get_reversal_approved_by_user()

    # Full audit trail
    audit_trail = payment.get_audit_trail()

    context = {
        'payment': payment,
        'performed_by_user': performed_by_user,
        'verified_by_user': verified_by_user,
        'reversed_by_user': reversed_by_user,
        'reversal_approved_by_user': reversal_approved_by_user,
        'audit_trail': audit_trail,
        'title': f'Reversal Details – {payment.reference_number or payment.pk}',
    }

    return render(request, 'finance/expense_payments/reversal_detail.html', context)

# =============================================================================
# JOURNAL VIEWS
# =============================================================================

@login_required
def journal_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""
    filter_form = JournalFilterForm(request.GET or None)
    journals = get_filtered_journals(request)
    
    # Calculate statistics
    stats = {
        'total': journals.count(),
        'active': journals.filter(is_active=True).count(),
        'general': journals.filter(journal_type='GENERAL').count(),
        'expenses': journals.filter(journal_type='EXPENSES').count(),
        'total_entries': sum(j.entry_count or 0 for j in journals),
    }
    
    # Pagination
    paginator = Paginator(journals, 10)
    page_number = request.GET.get('page', 1)
    journals_page = paginator.get_page(page_number)
    
    # Detect HTMX request
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'journals_page': journals_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    # Return appropriate template
    if is_htmx:
        return render(request, 'finance/journals/partials/_journal_results.html', context)
    else:
        return render(request, 'finance/journals/list.html', context)


@login_required
def journal_create(request):
    """Create new journal"""
    if request.method == 'POST':
        form = JournalForm(request.POST)
        if form.is_valid():
            journal = form.save()
            messages.success(
                request,
                f"Journal '{journal.name}' created successfully",
                extra_tags='sweetalert'
            )
            return redirect('finance:journal_detail', pk=journal.pk)
    else:
        form = JournalForm()
    
    context = {
        'form': form,
        'title': 'Create Journal',
    }
    
    return render(request, 'finance/journals/form.html', context)


@login_required
def journal_edit(request, pk):
    """Edit existing journal"""
    journal = get_object_or_404(Journal, pk=pk)
    
    if request.method == 'POST':
        form = JournalForm(request.POST, instance=journal)
        if form.is_valid():
            journal = form.save()
            messages.success(
                request,
                f"Journal '{journal.name}' updated successfully",
                extra_tags='sweetalert'
            )
            return redirect('finance:journal_detail', pk=journal.pk)
    else:
        form = JournalForm(instance=journal)
    
    context = {
        'form': form,
        'journal': journal,
        'title': f'Edit {journal.name}',
    }
    
    return render(request, 'finance/journals/form.html', context)


@login_required
def journal_detail(request, pk):
    """View journal details"""
    journal = get_object_or_404(Journal, pk=pk)
    
    # Get recent entries
    entries = journal.entries.select_related(
        'fiscal_period', 'academic_session'
    ).annotate(
        transaction_count=Count('transactions')
    ).order_by('-entry_date', '-created_at')[:50]
    
    # Statistics
    entry_count = journal.entries.count()
    posted_count = journal.entries.filter(status='POSTED').count()
    draft_count = journal.entries.filter(status='DRAFT').count()
    
    context = {
        'journal': journal,
        'entries': entries,
        'entry_count': entry_count,
        'posted_count': posted_count,
        'draft_count': draft_count,
    }
    
    return render(request, 'finance/journals/detail.html', context)


@login_required
def journal_delete(request, pk):
    """Delete journal with HTMX support"""
    journal = get_object_or_404(Journal, pk=pk)
    
    if request.method == 'POST':
        # Check if journal has entries
        if journal.entries.exists():
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f"Cannot delete '{journal.name}' because it has entries"
                response['HX-Alert-Type'] = 'error'
                response['HX-Alert-Title'] = 'Cannot Delete'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(
                    request,
                    f"Cannot delete '{journal.name}' because it has entries",
                    extra_tags='sweetalert-error'
                )
                return redirect('finance:journal_list')
        
        journal_name = journal.name
        journal.delete()
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Journal '{journal_name}' deleted successfully"
            response['HX-Alert-Type'] = 'success'
            response['HX-Alert-Title'] = 'Deleted!'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('finance:journal_list')
            return response
        else:
            messages.success(
                request,
                f"Journal '{journal_name}' deleted successfully",
                extra_tags='sweetalert'
            )
            return redirect('finance:journal_list')


@login_required
def journal_toggle_active(request, pk):
    """Toggle journal active status with HTMX support"""
    journal = get_object_or_404(Journal, pk=pk)
    
    if request.method == 'POST':
        journal.is_active = not journal.is_active
        journal.save(update_fields=['is_active', 'updated_at'])
        
        status = "activated" if journal.is_active else "deactivated"
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Journal '{journal.name}' {status}"
            response['HX-Alert-Type'] = 'success' if journal.is_active else 'warning'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('finance:journal_detail', kwargs={'pk': pk})
            return response
        else:
            messages.success(request, f"Journal {status}", extra_tags='sweetalert')
            return redirect('finance:journal_detail', pk=pk)


# =============================================================================
# JOURNAL ENTRY VIEWS
# =============================================================================

@login_required
def journal_entry_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""
    filter_form = JournalEntryFilterForm(request.GET or None)
    entries = get_filtered_journal_entries(request)
    
    # Calculate statistics
    stats = {
        'total': entries.count(),
        'draft': entries.filter(status='DRAFT').count(),
        'posted': entries.filter(status='POSTED').count(),
        'reversed': entries.filter(status='REVERSED').count(),
        'total_debits': entries.filter(status='POSTED').aggregate(
            Sum('total_debit'))['total_debit__sum'] or Decimal('0.00'),
        'total_credits': entries.filter(status='POSTED').aggregate(
            Sum('total_credit'))['total_credit__sum'] or Decimal('0.00'),
    }
    
    # Pagination
    paginator = Paginator(entries, 10)
    page_number = request.GET.get('page', 1)
    entries_page = paginator.get_page(page_number)
    
    # Detect HTMX request
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'entries_page': entries_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    # Return appropriate template
    if is_htmx:
        return render(request, 'finance/journal_entries/partials/_entry_results.html', context)
    else:
        return render(request, 'finance/journal_entries/list.html', context)


@login_required
def journal_entry_create(request):
    """Create new journal entry"""
    if request.method == 'POST':
        form = JournalEntryForm(request.POST)
        if form.is_valid():
            try:
                # Use service to create entry
                entry = JournalEntryService.create_entry(
                    entry_data=form.cleaned_data,
                    user=request.user
                )
                
                messages.success(
                    request,
                    f"Journal entry {entry.entry_number} created successfully",
                    extra_tags='sweetalert'
                )
                return redirect('finance:journal_entry_detail', pk=entry.pk)
                
            except Exception as e:
                logger.error(f"Error creating journal entry: {e}")
                messages.error(
                    request,
                    f"Error creating entry: {str(e)}",
                    extra_tags='sweetalert-error'
                )
    else:
        form = JournalEntryForm()
    
    context = {
        'form': form,
        'title': 'Create Journal Entry',
    }
    
    return render(request, 'finance/journal_entries/form.html', context)


@login_required
def journal_entry_edit(request, pk):
    """Edit existing journal entry"""
    entry = get_object_or_404(JournalEntry, pk=pk)
    
    # Check if entry can be edited
    if entry.status == 'POSTED':
        messages.warning(
            request,
            "Cannot edit posted journal entries",
            extra_tags='sweetalert'
        )
        return redirect('finance:journal_entry_detail', pk=pk)
    
    if request.method == 'POST':
        form = JournalEntryForm(request.POST, instance=entry)
        if form.is_valid():
            try:
                entry = form.save()
                
                messages.success(
                    request,
                    f"Entry {entry.entry_number} updated successfully",
                    extra_tags='sweetalert'
                )
                return redirect('finance:journal_entry_detail', pk=entry.pk)
                
            except Exception as e:
                logger.error(f"Error updating entry: {e}")
                messages.error(
                    request,
                    f"Error updating entry: {str(e)}",
                    extra_tags='sweetalert-error'
                )
    else:
        form = JournalEntryForm(instance=entry)
    
    context = {
        'form': form,
        'entry': entry,
        'title': f'Edit Entry {entry.entry_number}',
    }
    
    return render(request, 'finance/journal_entries/form.html', context)


@login_required
def journal_entry_detail(request, pk):
    """View journal entry details"""
    entry = get_object_or_404(
        JournalEntry.objects.select_related(
            'journal',
            'academic_session',
            'fiscal_period',
            'original_entry'
        ).prefetch_related('transactions__account'),
        pk=pk
    )
    
    # Get transactions
    transactions = entry.transactions.select_related(
        'account__account_type'
    ).order_by('id')
    
    # Calculate totals
    debit_total = sum(t.amount for t in transactions if t.is_debit)
    credit_total = sum(t.amount for t in transactions if not t.is_debit)
    is_balanced = debit_total == credit_total
    
    context = {
        'entry': entry,
        'transactions': transactions,
        'debit_total': debit_total,
        'credit_total': credit_total,
        'is_balanced': is_balanced,
    }
    
    return render(request, 'finance/journal_entries/detail.html', context)


@login_required
def journal_entry_delete(request, pk):
    """Delete journal entry with HTMX support"""
    entry = get_object_or_404(JournalEntry, pk=pk)
    
    if request.method == 'POST':
        # Check if entry can be deleted
        if entry.status == 'POSTED':
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = "Cannot delete posted entries - use reversal instead"
                response['HX-Alert-Type'] = 'error'
                response['HX-Alert-Title'] = 'Cannot Delete'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(
                    request,
                    "Cannot delete posted entries - use reversal instead",
                    extra_tags='sweetalert-error'
                )
                return redirect('finance:journal_entry_list')
        
        entry_number = entry.entry_number
        entry.delete()
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Entry {entry_number} deleted successfully"
            response['HX-Alert-Type'] = 'success'
            response['HX-Alert-Title'] = 'Deleted!'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('finance:journal_entry_list')
            return response
        else:
            messages.success(
                request,
                f"Entry {entry_number} deleted successfully",
                extra_tags='sweetalert'
            )
            return redirect('finance:journal_entry_list')


@login_required
def journal_entry_post(request, pk):
    """Post journal entry with HTMX support"""
    entry = get_object_or_404(JournalEntry, pk=pk)
    
    if request.method == 'POST':
        if entry.status != 'DRAFT':
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = "Only draft entries can be posted"
                response['HX-Alert-Type'] = 'warning'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.warning(request, "Only draft entries can be posted", extra_tags='sweetalert')
                return redirect('finance:journal_entry_detail', pk=pk)
        
        try:
            # Use service to post entry
            JournalEntryService.post_entry(entry, user=request.user)
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f"Entry {entry.entry_number} posted successfully"
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('finance:journal_entry_detail', kwargs={'pk': pk})
                return response
            else:
                messages.success(
                    request,
                    f"Entry posted successfully",
                    extra_tags='sweetalert'
                )
                return redirect('finance:journal_entry_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error posting entry: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f"Error: {str(e)}"
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f"Error: {str(e)}", extra_tags='sweetalert-error')
                return redirect('finance:journal_entry_detail', pk=pk)


@login_required
def journal_entry_reverse(request, pk):
    """Reverse journal entry with HTMX support"""
    entry = get_object_or_404(JournalEntry, pk=pk)
    
    if request.method == 'POST':
        form = JournalEntryReversalForm(request.POST)
        if form.is_valid():
            try:
                reversal_reason = form.cleaned_data['reversal_reason']
                reversal_date = form.cleaned_data['reversal_date']
                
                # Use service to reverse entry
                reversal_entry = JournalEntryService.reverse_entry(
                    entry=entry,
                    user=request.user,
                    reversal_date=reversal_date,
                    reason=reversal_reason
                )
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f"Entry reversed. Reversal entry: {reversal_entry.entry_number}"
                    response['HX-Alert-Type'] = 'success'
                    response['HX-Close-Modal'] = 'true'
                    response['HX-Redirect'] = reverse('finance:journal_entry_detail', kwargs={'pk': reversal_entry.pk})
                    return response
                else:
                    messages.success(
                        request,
                        f"Entry reversed. Reversal entry: {reversal_entry.entry_number}",
                        extra_tags='sweetalert'
                    )
                    return redirect('finance:journal_entry_detail', pk=reversal_entry.pk)
                    
            except Exception as e:
                logger.error(f"Error reversing entry: {e}")
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f"Error: {str(e)}"
                    response['HX-Alert-Type'] = 'error'
                    response['HX-Close-Modal'] = 'true'
                    return response
                else:
                    messages.error(request, f"Error: {str(e)}", extra_tags='sweetalert-error')
                    return redirect('finance:journal_entry_detail', pk=pk)


@login_required
def journal_entry_print_view(request, pk):
    """Generate printable journal entry"""
    entry = get_object_or_404(
        JournalEntry.objects.select_related(
            'journal', 'fiscal_period'
        ).prefetch_related('transactions__account'),
        pk=pk
    )
    
    context = {
        'entry': entry,
        'now': timezone.now(),
        'title': f'Journal Entry {entry.entry_number}',
    }
    
    return render(request, 'finance/journal_entries/print.html', context)


@login_required
def export_journal_entries_excel(request):
    """Export journal entries to Excel with filters applied"""
    
    entries = get_filtered_journal_entries(request)
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Journal Entries"
    
    # Define styles
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_alignment = Alignment(horizontal="center", vertical="center")
    
    # Headers
    headers = [
        '#', 'Entry Number', 'Date', 'Journal', 'Description',
        'Total Debit', 'Total Credit', 'Status'
    ]
    ws.append(headers)
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
    
    # Data rows
    for idx, entry in enumerate(entries, start=1):
        ws.append([
            idx,
            entry.entry_number,
            entry.entry_date.strftime('%Y-%m-%d'),
            entry.journal.name,
            entry.description,
            float(entry.total_debit or 0),
            float(entry.total_credit or 0),
            entry.get_status_display(),
        ])
    
    # Auto-adjust column widths
    for column in ws.columns:
        max_length = 0
        column_letter = get_column_letter(column[0].column)
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(cell.value)
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        ws.column_dimensions[column_letter].width = adjusted_width
    
    # Create response
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"journal_entries_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


# =============================================================================
# BUDGET VIEWS
# =============================================================================

@login_required
def budget_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""
    filter_form = BudgetFilterForm(request.GET or None)
    budgets = get_filtered_budgets(request)
    
    # Calculate statistics
    stats = {
        'total': budgets.count(),
        'draft': budgets.filter(status='DRAFT').count(),
        'approved': budgets.filter(status='APPROVED').count(),
        'active': budgets.filter(status='ACTIVE').count(),
        'closed': budgets.filter(status='CLOSED').count(),
        'total_revenue_budget': budgets.aggregate(
            Sum('total_revenue_budget'))['total_revenue_budget__sum'] or Decimal('0.00'),
        'total_expense_budget': budgets.aggregate(
            Sum('total_expense_budget'))['total_expense_budget__sum'] or Decimal('0.00'),
    }
    
    # Pagination
    paginator = Paginator(budgets, 10)
    page_number = request.GET.get('page', 1)
    budgets_page = paginator.get_page(page_number)
    
    # Detect HTMX request
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'budgets_page': budgets_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    # Return appropriate template
    if is_htmx:
        return render(request, 'finance/budgets/partials/_budget_results.html', context)
    else:
        return render(request, 'finance/budgets/list.html', context)


@login_required
def budget_create(request):
    """Create new budget"""
    if request.method == 'POST':
        form = BudgetForm(request.POST)
        if form.is_valid():
            try:
                # Use service to create budget
                budget = BudgetService.create_budget(
                    budget_data=form.cleaned_data,
                    user=request.user
                )
                
                messages.success(
                    request,
                    f"Budget '{budget.name}' created successfully",
                    extra_tags='sweetalert'
                )
                return redirect('finance:budget_detail', pk=budget.pk)
                
            except Exception as e:
                logger.error(f"Error creating budget: {e}")
                messages.error(
                    request,
                    f"Error creating budget: {str(e)}",
                    extra_tags='sweetalert-error'
                )
    else:
        form = BudgetForm()
    
    context = {
        'form': form,
        'title': 'Create Budget',
    }
    
    return render(request, 'finance/budgets/form.html', context)


@login_required
def budget_edit(request, pk):
    """Edit existing budget"""
    budget = get_object_or_404(Budget, pk=pk)
    
    # Check if budget can be edited
    if budget.status in ['APPROVED', 'ACTIVE', 'CLOSED']:
        messages.warning(
            request,
            f"Cannot edit budget with status: {budget.get_status_display()}",
            extra_tags='sweetalert'
        )
        return redirect('finance:budget_detail', pk=pk)
    
    if request.method == 'POST':
        form = BudgetForm(request.POST, instance=budget)
        if form.is_valid():
            try:
                budget = form.save()
                
                messages.success(
                    request,
                    f"Budget '{budget.name}' updated successfully",
                    extra_tags='sweetalert'
                )
                return redirect('finance:budget_detail', pk=budget.pk)
                
            except Exception as e:
                logger.error(f"Error updating budget: {e}")
                messages.error(
                    request,
                    f"Error updating budget: {str(e)}",
                    extra_tags='sweetalert-error'
                )
    else:
        form = BudgetForm(instance=budget)
    
    context = {
        'form': form,
        'budget': budget,
        'title': f'Edit Budget - {budget.name}',
    }
    
    return render(request, 'finance/budgets/form.html', context)


@login_required
def budget_detail(request, pk):
    """View budget details"""
    budget = get_object_or_404(
        Budget.objects.select_related(
            'fiscal_year',
            'academic_session',
            'parent_budget'
        ).prefetch_related('lines__account'),
        pk=pk
    )
    
    # Get budget lines
    revenue_lines = budget.lines.filter(line_type='REVENUE').select_related('account')
    expense_lines = budget.lines.filter(line_type='EXPENSE').select_related('account')
    
    # Calculate variance
    revenue_variance = budget.total_revenue_budget - budget.actual_revenue_total
    expense_variance = budget.total_expense_budget - budget.actual_expense_total
    
    # Calculate percentages
    #revenue_percentage = calculate_percentage(budget.actual_revenue_total, budget.total_revenue_budget)
    #expense_percentage = calculate_percentage(budget.actual_expense_total, budget.total_expense_budget)
    
    context = {
        'budget': budget,
        'revenue_lines': revenue_lines,
        'expense_lines': expense_lines,
        'revenue_variance': revenue_variance,
        'expense_variance': expense_variance,
        #'revenue_percentage': revenue_percentage,
        #'expense_percentage': expense_percentage,
    }
    
    return render(request, 'finance/budgets/detail.html', context)


@login_required
def budget_delete(request, pk):
    """Delete budget with HTMX support"""
    budget = get_object_or_404(Budget, pk=pk)
    
    if request.method == 'POST':
        # Check if budget can be deleted
        if budget.status in ['APPROVED', 'ACTIVE', 'CLOSED']:
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f"Cannot delete budget with status: {budget.get_status_display()}"
                response['HX-Alert-Type'] = 'error'
                response['HX-Alert-Title'] = 'Cannot Delete'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(
                    request,
                    f"Cannot delete budget with status: {budget.get_status_display()}",
                    extra_tags='sweetalert-error'
                )
                return redirect('finance:budget_list')
        
        # Check for child budgets
        if budget.child_budgets.exists():
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = "Cannot delete budget with child budgets"
                response['HX-Alert-Type'] = 'error'
                response['HX-Alert-Title'] = 'Cannot Delete'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(
                    request,
                    "Cannot delete budget with child budgets",
                    extra_tags='sweetalert-error'
                )
                return redirect('finance:budget_list')
        
        budget_name = budget.name
        budget.delete()
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Budget '{budget_name}' deleted successfully"
            response['HX-Alert-Type'] = 'success'
            response['HX-Alert-Title'] = 'Deleted!'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('finance:budget_list')
            return response
        else:
            messages.success(
                request,
                f"Budget '{budget_name}' deleted successfully",
                extra_tags='sweetalert'
            )
            return redirect('finance:budget_list')


@login_required
def budget_approve(request, pk):
    """Approve budget with HTMX support"""
    budget = get_object_or_404(Budget, pk=pk)
    
    if request.method == 'POST':
        form = BudgetApprovalForm(request.POST)
        if form.is_valid():
            try:
                decision = form.cleaned_data['decision']
                notes = form.cleaned_data['notes']
                
                if decision == 'APPROVE':
                    # Use service to approve budget
                    BudgetService.approve_budget(
                        budget=budget,
                        user=request.user,
                        notes=notes
                    )
                    
                    message = f"Budget '{budget.name}' approved successfully"
                    alert_type = 'success'
                elif decision == 'REQUEST_REVISION':
                    budget.status = 'DRAFT'
                    budget.save(update_fields=['status', 'updated_at'])
                    
                    message = f"Budget '{budget.name}' sent back for revision"
                    alert_type = 'warning'
                else:  # REJECT
                    budget.status = 'REJECTED'
                    budget.save(update_fields=['status', 'updated_at'])
                    
                    message = f"Budget '{budget.name}' rejected"
                    alert_type = 'warning'
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = message
                    response['HX-Alert-Type'] = alert_type
                    response['HX-Close-Modal'] = 'true'
                    response['HX-Redirect'] = reverse('finance:budget_detail', kwargs={'pk': pk})
                    return response
                else:
                    if alert_type == 'success':
                        messages.success(request, message, extra_tags='sweetalert')
                    else:
                        messages.warning(request, message, extra_tags='sweetalert')
                    return redirect('finance:budget_detail', pk=pk)
                    
            except Exception as e:
                logger.error(f"Error processing budget approval: {e}")
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f"Error: {str(e)}"
                    response['HX-Alert-Type'] = 'error'
                    response['HX-Close-Modal'] = 'true'
                    return response
                else:
                    messages.error(request, f"Error: {str(e)}", extra_tags='sweetalert-error')
                    return redirect('finance:budget_detail', pk=pk)


@login_required
def budget_activate(request, pk):
    """Activate budget with HTMX support"""
    budget = get_object_or_404(Budget, pk=pk)
    
    if request.method == 'POST':
        if budget.status != 'APPROVED':
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = "Only approved budgets can be activated"
                response['HX-Alert-Type'] = 'warning'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.warning(request, "Only approved budgets can be activated", extra_tags='sweetalert')
                return redirect('finance:budget_detail', pk=pk)
        
        try:
            # Use service to activate budget
            BudgetService.activate_budget(budget, user=request.user)
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f"Budget '{budget.name}' activated successfully"
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('finance:budget_detail', kwargs={'pk': pk})
                return response
            else:
                messages.success(
                    request,
                    f"Budget activated successfully",
                    extra_tags='sweetalert'
                )
                return redirect('finance:budget_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error activating budget: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f"Error: {str(e)}"
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f"Error: {str(e)}", extra_tags='sweetalert-error')
                return redirect('finance:budget_detail', pk=pk)


@login_required
def budget_close(request, pk):
    """Close budget with HTMX support"""
    budget = get_object_or_404(Budget, pk=pk)
    
    if request.method == 'POST':
        if budget.status != 'ACTIVE':
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = "Only active budgets can be closed"
                response['HX-Alert-Type'] = 'warning'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.warning(request, "Only active budgets can be closed", extra_tags='sweetalert')
                return redirect('finance:budget_detail', pk=pk)
        
        try:
            # Use service to close budget
            BudgetService.close_budget(budget, user=request.user)
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f"Budget '{budget.name}' closed successfully"
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('finance:budget_detail', kwargs={'pk': pk})
                return response
            else:
                messages.success(
                    request,
                    f"Budget closed successfully",
                    extra_tags='sweetalert'
                )
                return redirect('finance:budget_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error closing budget: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f"Error: {str(e)}"
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f"Error: {str(e)}", extra_tags='sweetalert-error')
                return redirect('finance:budget_detail', pk=pk)


@login_required
def budget_print_view(request, pk):
    """Generate printable budget"""
    budget = get_object_or_404(
        Budget.objects.select_related(
            'fiscal_year', 'academic_session'
        ).prefetch_related('lines__account'),
        pk=pk
    )
    
    context = {
        'budget': budget,
        'now': timezone.now(),
        'title': f'Budget - {budget.name}',
    }
    
    return render(request, 'finance/budgets/print.html', context)


@login_required
def export_budgets_excel(request):
    """Export budgets to Excel with filters applied"""
    
    budgets = get_filtered_budgets(request)
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Budgets"
    
    # Define styles
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_alignment = Alignment(horizontal="center", vertical="center")
    
    # Headers
    headers = [
        '#', 'Budget Name', 'Type', 'Start Date', 'End Date',
        'Revenue Budget', 'Expense Budget', 'Net Budget', 'Status'
    ]
    ws.append(headers)
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
    
    # Data rows
    for idx, budget in enumerate(budgets, start=1):
        ws.append([
            idx,
            budget.name,
            budget.get_budget_type_display(),
            budget.start_date.strftime('%Y-%m-%d'),
            budget.end_date.strftime('%Y-%m-%d'),
            float(budget.total_revenue_budget),
            float(budget.total_expense_budget),
            float(budget.net_budget),
            budget.get_status_display(),
        ])
    
    # Auto-adjust column widths
    for column in ws.columns:
        max_length = 0
        column_letter = get_column_letter(column[0].column)
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(cell.value)
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        ws.column_dimensions[column_letter].width = adjusted_width
    
    # Create response
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"budgets_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response