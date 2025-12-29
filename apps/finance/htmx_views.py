# finance/htmx_views.py

from django.http import JsonResponse
from django.shortcuts import render
from django.db.models import Q, Count, Sum, Avg, F, DecimalField, Case, When
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from decimal import Decimal
import logging

from .models import (
    AccountType,
    Account,
    ExpenseCategory,
    Expense,
    ExpensePayment,
    Journal,
    JournalEntry,
    JournalTransaction,
    Budget,
    BudgetLine
)
from utils.utils import parse_filters, paginate_queryset

logger = logging.getLogger(__name__)


# =============================================================================
# ACCOUNT TYPE SEARCH
# =============================================================================

def account_type_search(request):
    """HTMX-compatible account type search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'account_type', 'is_active', 'requires_approval',
        'allows_manual_entries'
    ])
    
    query = filters['q']
    account_type = filters['account_type']
    is_active = filters['is_active']
    requires_approval = filters['requires_approval']
    allows_manual_entries = filters['allows_manual_entries']
    
    # Build queryset
    account_types = AccountType.objects.annotate(
        account_count=Count('accounts', distinct=True)
    ).order_by('account_type', 'display_order', 'name')
    
    # Apply text search
    if query:
        account_types = account_types.filter(
            Q(name__icontains=query) |
            Q(code__icontains=query) |
            Q(description__icontains=query)
        )
    
    # Apply filters
    if account_type:
        account_types = account_types.filter(account_type=account_type)
    
    if is_active is not None:
        account_types = account_types.filter(is_active=(is_active.lower() == 'true'))
    
    if requires_approval is not None:
        account_types = account_types.filter(requires_approval=(requires_approval.lower() == 'true'))
    
    if allows_manual_entries is not None:
        account_types = account_types.filter(allows_manual_entries=(allows_manual_entries.lower() == 'true'))
    
    # Paginate
    account_types_page, paginator = paginate_queryset(request, account_types, per_page=20)
    
    # Calculate stats
    total = account_types.count()
    
    stats = {
        'total': total,
        'active': account_types.filter(is_active=True).count(),
        'asset': account_types.filter(account_type='ASSET').count(),
        'liability': account_types.filter(account_type='LIABILITY').count(),
        'equity': account_types.filter(account_type='EQUITY').count(),
        'revenue': account_types.filter(account_type='REVENUE').count(),
        'expense': account_types.filter(account_type='EXPENSE').count(),
        'total_accounts': sum(at.account_count for at in account_types),
    }
    
    return render(request, 'finance/account_types/_type_results.html', {
        'account_types_page': account_types_page,
        'stats': stats,
    })


# =============================================================================
# ACCOUNT SEARCH
# =============================================================================

def account_search(request):
    """HTMX-compatible account search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'account_type', 'is_active', 'is_bank_account', 
        'is_cash_account', 'is_mobile_money_account', 'is_receivable_account',
        'is_payable_account', 'is_inventory_account', 'is_fixed_asset',
        'is_revenue_account', 'is_expense_account', 'parent_account',
        'min_balance', 'max_balance'
    ])
    
    query = filters['q']
    account_type = filters['account_type']
    is_active = filters['is_active']
    is_bank_account = filters['is_bank_account']
    is_cash_account = filters['is_cash_account']
    is_mobile_money_account = filters['is_mobile_money_account']
    is_receivable_account = filters['is_receivable_account']
    is_payable_account = filters['is_payable_account']
    is_inventory_account = filters['is_inventory_account']
    is_fixed_asset = filters['is_fixed_asset']
    is_revenue_account = filters['is_revenue_account']
    is_expense_account = filters['is_expense_account']
    parent_account = filters['parent_account']
    min_balance = filters['min_balance']
    max_balance = filters['max_balance']
    
    # Build queryset
    accounts = Account.objects.select_related(
        'account_type',
        'parent_account'
    ).annotate(
        child_count=Count('child_accounts', distinct=True),
        transaction_count=Count('journal_transactions', distinct=True)
    ).order_by('account_type__account_type', 'account_number')
    
    # Apply text search
    if query:
        accounts = accounts.filter(
            Q(account_number__icontains=query) |
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(bank_name__icontains=query) |
            Q(account_holder_name__icontains=query)
        )
    
    # Apply filters
    if account_type:
        accounts = accounts.filter(account_type_id=account_type)
    
    if parent_account == 'null':
        accounts = accounts.filter(parent_account__isnull=True)
    elif parent_account == 'has_parent':
        accounts = accounts.filter(parent_account__isnull=False)
    elif parent_account:
        accounts = accounts.filter(parent_account_id=parent_account)
    
    if is_active is not None:
        accounts = accounts.filter(is_active=(is_active.lower() == 'true'))
    
    # Boolean filters
    if is_bank_account and is_bank_account.lower() == 'true':
        accounts = accounts.filter(is_bank_account=True)
    
    if is_cash_account and is_cash_account.lower() == 'true':
        accounts = accounts.filter(is_cash_account=True)
    
    if is_mobile_money_account and is_mobile_money_account.lower() == 'true':
        accounts = accounts.filter(is_mobile_money_account=True)
    
    if is_receivable_account and is_receivable_account.lower() == 'true':
        accounts = accounts.filter(is_receivable_account=True)
    
    if is_payable_account and is_payable_account.lower() == 'true':
        accounts = accounts.filter(is_payable_account=True)
    
    if is_inventory_account and is_inventory_account.lower() == 'true':
        accounts = accounts.filter(is_inventory_account=True)
    
    if is_fixed_asset and is_fixed_asset.lower() == 'true':
        accounts = accounts.filter(is_fixed_asset=True)
    
    if is_revenue_account and is_revenue_account.lower() == 'true':
        accounts = accounts.filter(is_revenue_account=True)
    
    if is_expense_account and is_expense_account.lower() == 'true':
        accounts = accounts.filter(is_expense_account=True)
    
    # Balance filters
    if min_balance:
        try:
            accounts = accounts.filter(current_balance__gte=Decimal(min_balance))
        except:
            pass
    
    if max_balance:
        try:
            accounts = accounts.filter(current_balance__lte=Decimal(max_balance))
        except:
            pass
    
    # Paginate
    accounts_page, paginator = paginate_queryset(request, accounts, per_page=20)
    
    # Calculate stats
    total = accounts.count()
    
    stats = {
        'total': total,
        'active': accounts.filter(is_active=True).count(),
        'bank_accounts': accounts.filter(is_bank_account=True).count(),
        'cash_accounts': accounts.filter(is_cash_account=True).count(),
        'mobile_money': accounts.filter(is_mobile_money_account=True).count(),
        'receivable': accounts.filter(is_receivable_account=True).count(),
        'payable': accounts.filter(is_payable_account=True).count(),
        'revenue': accounts.filter(is_revenue_account=True).count(),
        'expense': accounts.filter(is_expense_account=True).count(),
        'total_balance': accounts.aggregate(Sum('current_balance'))['current_balance__sum'] or 0,
        'parent_accounts': accounts.filter(parent_account__isnull=True).count(),
    }
    
    return render(request, 'finance/accounts/_account_results.html', {
        'accounts_page': accounts_page,
        'stats': stats,
    })


# =============================================================================
# EXPENSE CATEGORY SEARCH
# =============================================================================

def expense_category_search(request):
    """HTMX-compatible expense category search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'category_type', 'is_active', 'requires_approval'
    ])
    
    query = filters['q']
    category_type = filters['category_type']
    is_active = filters['is_active']
    requires_approval = filters['requires_approval']
    
    # Build queryset
    categories = ExpenseCategory.objects.select_related(
        'default_expense_account'
    ).annotate(
        expense_count=Count('expenses', distinct=True)
    ).order_by('category_type', 'name')
    
    # Apply text search
    if query:
        categories = categories.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query)
        )
    
    # Apply filters
    if category_type:
        categories = categories.filter(category_type=category_type)
    
    if is_active is not None:
        categories = categories.filter(is_active=(is_active.lower() == 'true'))
    
    if requires_approval is not None:
        categories = categories.filter(requires_approval=(requires_approval.lower() == 'true'))
    
    # Paginate
    categories_page, paginator = paginate_queryset(request, categories, per_page=20)
    
    # Calculate stats
    total = categories.count()
    
    stats = {
        'total': total,
        'active': categories.filter(is_active=True).count(),
        'requires_approval': categories.filter(requires_approval=True).count(),
        'administrative': categories.filter(category_type='ADMINISTRATIVE').count(),
        'academic': categories.filter(category_type='ACADEMIC').count(),
        'staff': categories.filter(category_type='STAFF').count(),
        'facilities': categories.filter(category_type='FACILITIES').count(),
        'total_expenses': sum(c.expense_count for c in categories),
    }
    
    return render(request, 'finance/expense_categories/_category_results.html', {
        'categories_page': categories_page,
        'stats': stats,
    })


# =============================================================================
# EXPENSE SEARCH
# =============================================================================

def expense_search(request):
    """HTMX-compatible expense search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'status', 'category', 'academic_session', 'fiscal_period',
        'start_date', 'end_date', 'min_amount', 'max_amount',
        'vendor_name', 'is_recurring', 'budget_line'
    ])
    
    query = filters['q']
    status = filters['status']
    category = filters['category']
    academic_session = filters['academic_session']
    fiscal_period = filters['fiscal_period']
    start_date = filters['start_date']
    end_date = filters['end_date']
    min_amount = filters['min_amount']
    max_amount = filters['max_amount']
    vendor_name = filters['vendor_name']
    is_recurring = filters['is_recurring']
    budget_line = filters['budget_line']
    
    # Build queryset
    expenses = Expense.objects.select_related(
        'category',
        'academic_session',
        'fiscal_period',
        'expense_account',
        'budget_line',
        'preferred_payment_method'
    ).prefetch_related(
        'lines',
        'payments'
    ).annotate(
        line_count=Count('lines', distinct=True),
        payment_count=Count('payments', distinct=True)
    ).order_by('-expense_date', '-created_at')
    
    # Apply text search
    if query:
        expenses = expenses.filter(
            Q(expense_number__icontains=query) |
            Q(description__icontains=query) |
            Q(vendor_name__icontains=query) |
            Q(vendor_reference__icontains=query)
        )
    
    # Apply filters
    if status:
        expenses = expenses.filter(status=status)
    
    if category:
        expenses = expenses.filter(category_id=category)
    
    if academic_session:
        expenses = expenses.filter(academic_session_id=academic_session)
    
    if fiscal_period:
        expenses = expenses.filter(fiscal_period_id=fiscal_period)
    
    if budget_line:
        expenses = expenses.filter(budget_line_id=budget_line)
    
    if vendor_name:
        expenses = expenses.filter(vendor_name__icontains=vendor_name)
    
    if start_date:
        expenses = expenses.filter(expense_date__gte=start_date)
    
    if end_date:
        expenses = expenses.filter(expense_date__lte=end_date)
    
    if is_recurring is not None:
        expenses = expenses.filter(is_recurring=(is_recurring.lower() == 'true'))
    
    if min_amount:
        try:
            expenses = expenses.filter(total_amount__gte=Decimal(min_amount))
        except:
            pass
    
    if max_amount:
        try:
            expenses = expenses.filter(total_amount__lte=Decimal(max_amount))
        except:
            pass
    
    # Paginate
    expenses_page, paginator = paginate_queryset(request, expenses, per_page=20)
    
    # Calculate stats
    total = expenses.count()
    
    stats = {
        'total': total,
        'draft': expenses.filter(status='DRAFT').count(),
        'pending_approval': expenses.filter(status='PENDING_APPROVAL').count(),
        'approved': expenses.filter(status='APPROVED').count(),
        'paid': expenses.filter(status='PAID').count(),
        'rejected': expenses.filter(status='REJECTED').count(),
        'total_amount': expenses.aggregate(Sum('total_amount'))['total_amount__sum'] or 0,
        'approved_amount': expenses.filter(status__in=['APPROVED', 'PAID']).aggregate(
            Sum('total_amount'))['total_amount__sum'] or 0,
        'paid_amount': expenses.filter(status='PAID').aggregate(
            Sum('total_amount'))['total_amount__sum'] or 0,
        'recurring': expenses.filter(is_recurring=True).count(),
    }
    
    return render(request, 'finance/expenses/_expense_results.html', {
        'expenses_page': expenses_page,
        'stats': stats,
    })


# =============================================================================
# EXPENSE PAYMENT SEARCH
# =============================================================================

def expense_payment_search(request):
    """HTMX-compatible expense payment search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'status', 'payment_method', 'account', 'fiscal_period',
        'start_date', 'end_date', 'is_verified', 'batch_number',
        'min_amount', 'max_amount'
    ])
    
    query = filters['q']
    status = filters['status']
    payment_method = filters['payment_method']
    account = filters['account']
    fiscal_period = filters['fiscal_period']
    start_date = filters['start_date']
    end_date = filters['end_date']
    is_verified = filters['is_verified']
    batch_number = filters['batch_number']
    min_amount = filters['min_amount']
    max_amount = filters['max_amount']
    
    # Build queryset
    payments = ExpensePayment.objects.select_related(
        'expense__category',
        'payment_method',
        'account',
        'fiscal_period'
    ).order_by('-payment_date', '-created_at')
    
    # Apply text search
    if query:
        payments = payments.filter(
            Q(reference_number__icontains=query) |
            Q(transaction_id__icontains=query) |
            Q(check_number__icontains=query) |
            Q(expense__expense_number__icontains=query) |
            Q(expense__vendor_name__icontains=query)
        )
    
    # Apply filters
    if status:
        payments = payments.filter(status=status)
    
    if payment_method:
        payments = payments.filter(payment_method_id=payment_method)
    
    if account:
        payments = payments.filter(account_id=account)
    
    if fiscal_period:
        payments = payments.filter(fiscal_period_id=fiscal_period)
    
    if batch_number:
        payments = payments.filter(batch_number=batch_number)
    
    if start_date:
        payments = payments.filter(payment_date__gte=start_date)
    
    if end_date:
        payments = payments.filter(payment_date__lte=end_date)
    
    if is_verified is not None:
        payments = payments.filter(is_verified=(is_verified.lower() == 'true'))
    
    if min_amount:
        try:
            payments = payments.filter(amount__gte=Decimal(min_amount))
        except:
            pass
    
    if max_amount:
        try:
            payments = payments.filter(amount__lte=Decimal(max_amount))
        except:
            pass
    
    # Paginate
    payments_page, paginator = paginate_queryset(request, payments, per_page=20)
    
    # Calculate stats
    total = payments.count()
    
    stats = {
        'total': total,
        'pending': payments.filter(status='PENDING').count(),
        'processed': payments.filter(status='PROCESSED').count(),
        'verified': payments.filter(is_verified=True).count(),
        'unverified': payments.filter(is_verified=False).count(),
        'total_amount': payments.filter(status__in=['PROCESSED', 'VERIFIED']).aggregate(
            Sum('amount'))['amount__sum'] or 0,
        'total_fees': payments.aggregate(Sum('processing_fee'))['processing_fee__sum'] or 0,
        'total_bank_charges': payments.aggregate(Sum('bank_charges'))['bank_charges__sum'] or 0,
    }
    
    return render(request, 'finance/expense_payments/_payment_results.html', {
        'payments_page': payments_page,
        'stats': stats,
    })


# =============================================================================
# JOURNAL SEARCH
# =============================================================================

def journal_search(request):
    """HTMX-compatible journal search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'journal_type', 'is_active'
    ])
    
    query = filters['q']
    journal_type = filters['journal_type']
    is_active = filters['is_active']
    
    # Build queryset
    journals = Journal.objects.annotate(
        entry_count=Count('entries', distinct=True)
    ).order_by('journal_type', 'name')
    
    # Apply text search
    if query:
        journals = journals.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query)
        )
    
    # Apply filters
    if journal_type:
        journals = journals.filter(journal_type=journal_type)
    
    if is_active is not None:
        journals = journals.filter(is_active=(is_active.lower() == 'true'))
    
    # Paginate
    journals_page, paginator = paginate_queryset(request, journals, per_page=20)
    
    # Calculate stats
    total = journals.count()
    
    stats = {
        'total': total,
        'active': journals.filter(is_active=True).count(),
        'general': journals.filter(journal_type='GENERAL').count(),
        'fees': journals.filter(journal_type='FEES').count(),
        'expenses': journals.filter(journal_type='EXPENSES').count(),
        'cash': journals.filter(journal_type='CASH').count(),
        'bank': journals.filter(journal_type='BANK').count(),
        'payroll': journals.filter(journal_type='PAYROLL').count(),
        'total_entries': sum(j.entry_count for j in journals),
    }
    
    return render(request, 'finance/journals/_journal_results.html', {
        'journals_page': journals_page,
        'stats': stats,
    })


# =============================================================================
# JOURNAL ENTRY SEARCH
# =============================================================================

def journal_entry_search(request):
    """HTMX-compatible journal entry search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'status', 'journal', 'academic_session', 'fiscal_period',
        'start_date', 'end_date'
    ])
    
    query = filters['q']
    status = filters['status']
    journal = filters['journal']
    academic_session = filters['academic_session']
    fiscal_period = filters['fiscal_period']
    start_date = filters['start_date']
    end_date = filters['end_date']
    
    # Build queryset
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
    
    # Apply text search
    if query:
        entries = entries.filter(
            Q(entry_number__icontains=query) |
            Q(reference_number__icontains=query) |
            Q(description__icontains=query)
        )
    
    # Apply filters
    if status:
        entries = entries.filter(status=status)
    
    if journal:
        entries = entries.filter(journal_id=journal)
    
    if academic_session:
        entries = entries.filter(academic_session_id=academic_session)
    
    if fiscal_period:
        entries = entries.filter(fiscal_period_id=fiscal_period)
    
    if start_date:
        entries = entries.filter(entry_date__gte=start_date)
    
    if end_date:
        entries = entries.filter(entry_date__lte=end_date)
    
    # Paginate
    entries_page, paginator = paginate_queryset(request, entries, per_page=20)
    
    # Calculate stats
    total = entries.count()
    
    stats = {
        'total': total,
        'draft': entries.filter(status='DRAFT').count(),
        'posted': entries.filter(status='POSTED').count(),
        'reversed': entries.filter(status='REVERSED').count(),
        'total_debits': entries.filter(status='POSTED').aggregate(
            Sum('total_debit'))['total_debit__sum'] or 0,
        'total_credits': entries.filter(status='POSTED').aggregate(
            Sum('total_credit'))['total_credit__sum'] or 0,
    }
    
    return render(request, 'finance/journal_entries/_entry_results.html', {
        'entries_page': entries_page,
        'stats': stats,
    })


# =============================================================================
# JOURNAL TRANSACTION SEARCH
# =============================================================================

def journal_transaction_search(request):
    """HTMX-compatible journal transaction search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'journal_entry', 'account', 'is_debit',
        'start_date', 'end_date', 'min_amount', 'max_amount'
    ])
    
    query = filters['q']
    journal_entry = filters['journal_entry']
    account = filters['account']
    is_debit = filters['is_debit']
    start_date = filters['start_date']
    end_date = filters['end_date']
    min_amount = filters['min_amount']
    max_amount = filters['max_amount']
    
    # Build queryset
    transactions = JournalTransaction.objects.select_related(
        'journal_entry__journal',
        'journal_entry__fiscal_period',
        'account__account_type'
    ).order_by('-journal_entry__entry_date', 'id')
    
    # Apply text search
    if query:
        transactions = transactions.filter(
            Q(description__icontains=query) |
            Q(journal_entry__entry_number__icontains=query) |
            Q(account__account_number__icontains=query) |
            Q(account__name__icontains=query)
        )
    
    # Apply filters
    if journal_entry:
        transactions = transactions.filter(journal_entry_id=journal_entry)
    
    if account:
        transactions = transactions.filter(account_id=account)
    
    if is_debit is not None:
        transactions = transactions.filter(is_debit=(is_debit.lower() == 'true'))
    
    if start_date:
        transactions = transactions.filter(journal_entry__entry_date__gte=start_date)
    
    if end_date:
        transactions = transactions.filter(journal_entry__entry_date__lte=end_date)
    
    if min_amount:
        try:
            transactions = transactions.filter(amount__gte=Decimal(min_amount))
        except:
            pass
    
    if max_amount:
        try:
            transactions = transactions.filter(amount__lte=Decimal(max_amount))
        except:
            pass
    
    # Paginate
    transactions_page, paginator = paginate_queryset(request, transactions, per_page=20)
    
    # Calculate stats
    total = transactions.count()
    
    stats = {
        'total': total,
        'debits': transactions.filter(is_debit=True).count(),
        'credits': transactions.filter(is_debit=False).count(),
        'total_debit_amount': transactions.filter(is_debit=True).aggregate(
            Sum('amount'))['amount__sum'] or 0,
        'total_credit_amount': transactions.filter(is_debit=False).aggregate(
            Sum('amount'))['amount__sum'] or 0,
    }
    
    return render(request, 'finance/transactions/_transaction_results.html', {
        'transactions_page': transactions_page,
        'stats': stats,
    })


# =============================================================================
# BUDGET SEARCH
# =============================================================================

def budget_search(request):
    """HTMX-compatible budget search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'budget_type', 'status', 'fiscal_year', 'academic_session',
        'start_date', 'end_date', 'parent_budget'
    ])
    
    query = filters['q']
    budget_type = filters['budget_type']
    status = filters['status']
    fiscal_year = filters['fiscal_year']
    academic_session = filters['academic_session']
    start_date = filters['start_date']
    end_date = filters['end_date']
    parent_budget = filters['parent_budget']
    
    # Build queryset
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
    
    # Apply text search
    if query:
        budgets = budgets.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query)
        )
    
    # Apply filters
    if budget_type:
        budgets = budgets.filter(budget_type=budget_type)
    
    if status:
        budgets = budgets.filter(status=status)
    
    if fiscal_year:
        budgets = budgets.filter(fiscal_year_id=fiscal_year)
    
    if academic_session:
        budgets = budgets.filter(academic_session_id=academic_session)
    
    if parent_budget == 'null':
        budgets = budgets.filter(parent_budget__isnull=True)
    elif parent_budget == 'has_parent':
        budgets = budgets.filter(parent_budget__isnull=False)
    elif parent_budget:
        budgets = budgets.filter(parent_budget_id=parent_budget)
    
    if start_date:
        budgets = budgets.filter(start_date__gte=start_date)
    
    if end_date:
        budgets = budgets.filter(end_date__lte=end_date)
    
    # Paginate
    budgets_page, paginator = paginate_queryset(request, budgets, per_page=20)
    
    # Calculate stats
    total = budgets.count()
    
    stats = {
        'total': total,
        'draft': budgets.filter(status='DRAFT').count(),
        'approved': budgets.filter(status='APPROVED').count(),
        'active': budgets.filter(status='ACTIVE').count(),
        'closed': budgets.filter(status='CLOSED').count(),
        'total_revenue_budget': budgets.aggregate(
            Sum('total_revenue_budget'))['total_revenue_budget__sum'] or 0,
        'total_expense_budget': budgets.aggregate(
            Sum('total_expense_budget'))['total_expense_budget__sum'] or 0,
        'total_actual_revenue': budgets.aggregate(
            Sum('actual_revenue_total'))['actual_revenue_total__sum'] or 0,
        'total_actual_expense': budgets.aggregate(
            Sum('actual_expense_total'))['actual_expense_total__sum'] or 0,
    }
    
    return render(request, 'finance/budgets/_budget_results.html', {
        'budgets_page': budgets_page,
        'stats': stats,
    })


# =============================================================================
# BUDGET LINE SEARCH
# =============================================================================

def budget_line_search(request):
    """HTMX-compatible budget line search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'budget', 'line_type', 'account',
        'min_budgeted', 'max_budgeted'
    ])
    
    query = filters['q']
    budget = filters['budget']
    line_type = filters['line_type']
    account = filters['account']
    min_budgeted = filters['min_budgeted']
    max_budgeted = filters['max_budgeted']
    
    # Build queryset
    lines = BudgetLine.objects.select_related(
        'budget',
        'account__account_type'
    ).annotate(
        variance=F('budgeted_amount') - F('actual_amount'),
        variance_pct=Case(
            When(budgeted_amount=0, then=0),
            default=(F('actual_amount') / F('budgeted_amount') * 100),
            output_field=DecimalField()
        )
    ).order_by('budget', 'line_type', 'account__account_number')
    
    # Apply text search
    if query:
        lines = lines.filter(
            Q(description__icontains=query) |
            Q(account__account_number__icontains=query) |
            Q(account__name__icontains=query) |
            Q(budget__name__icontains=query)
        )
    
    # Apply filters
    if budget:
        lines = lines.filter(budget_id=budget)
    
    if line_type:
        lines = lines.filter(line_type=line_type)
    
    if account:
        lines = lines.filter(account_id=account)
    
    if min_budgeted:
        try:
            lines = lines.filter(budgeted_amount__gte=Decimal(min_budgeted))
        except:
            pass
    
    if max_budgeted:
        try:
            lines = lines.filter(budgeted_amount__lte=Decimal(max_budgeted))
        except:
            pass
    
    # Paginate
    lines_page, paginator = paginate_queryset(request, lines, per_page=20)
    
    # Calculate stats
    total = lines.count()
    
    stats = {
        'total': total,
        'revenue_lines': lines.filter(line_type='REVENUE').count(),
        'expense_lines': lines.filter(line_type='EXPENSE').count(),
        'total_budgeted': lines.aggregate(Sum('budgeted_amount'))['budgeted_amount__sum'] or 0,
        'total_actual': lines.aggregate(Sum('actual_amount'))['actual_amount__sum'] or 0,
        'total_variance': lines.aggregate(Sum('variance'))['variance__sum'] or 0,
        'over_budget': lines.filter(actual_amount__gt=F('budgeted_amount')).count(),
        'under_budget': lines.filter(actual_amount__lt=F('budgeted_amount')).count(),
    }
    
    return render(request, 'finance/budget_lines/_line_results.html', {
        'lines_page': lines_page,
        'stats': stats,
    })


# =============================================================================
# QUICK STATS ENDPOINTS (for dashboard widgets)
# =============================================================================

@require_http_methods(["GET"])
def account_quick_stats(request):
    """Get quick statistics for accounts"""
    
    stats = {
        'total': Account.objects.filter(is_active=True).count(),
        'bank_accounts': Account.objects.filter(is_bank_account=True, is_active=True).count(),
        'cash_accounts': Account.objects.filter(is_cash_account=True, is_active=True).count(),
        'revenue_accounts': Account.objects.filter(is_revenue_account=True, is_active=True).count(),
        'expense_accounts': Account.objects.filter(is_expense_account=True, is_active=True).count(),
        'total_cash_balance': Account.objects.filter(
            is_cash_account=True,
            is_active=True
        ).aggregate(Sum('current_balance'))['current_balance__sum'] or 0,
        'total_bank_balance': Account.objects.filter(
            is_bank_account=True,
            is_active=True
        ).aggregate(Sum('current_balance'))['current_balance__sum'] or 0,
    }
    
    return JsonResponse(stats)


@require_http_methods(["GET"])
def expense_quick_stats(request):
    """Get quick statistics for expenses"""
    
    today = timezone.now().date()
    
    stats = {
        'total': Expense.objects.count(),
        'pending_approval': Expense.objects.filter(status='PENDING_APPROVAL').count(),
        'approved': Expense.objects.filter(status='APPROVED').count(),
        'paid': Expense.objects.filter(status='PAID').count(),
        'this_month': Expense.objects.filter(
            expense_date__month=today.month,
            expense_date__year=today.year
        ).count(),
        'total_pending_amount': Expense.objects.filter(
            status='PENDING_APPROVAL'
        ).aggregate(Sum('total_amount'))['total_amount__sum'] or 0,
        'total_unpaid_amount': Expense.objects.filter(
            status='APPROVED'
        ).aggregate(Sum('total_amount'))['total_amount__sum'] or 0,
    }
    
    return JsonResponse(stats)


@require_http_methods(["GET"])
def budget_quick_stats(request):
    """Get quick statistics for budgets"""
    
    active_budgets = Budget.objects.filter(status='ACTIVE')
    
    stats = {
        'total': Budget.objects.count(),
        'active': active_budgets.count(),
        'approved': Budget.objects.filter(status='APPROVED').count(),
        'total_revenue_budget': active_budgets.aggregate(
            Sum('total_revenue_budget'))['total_revenue_budget__sum'] or 0,
        'total_expense_budget': active_budgets.aggregate(
            Sum('total_expense_budget'))['total_expense_budget__sum'] or 0,
        'total_actual_revenue': active_budgets.aggregate(
            Sum('actual_revenue_total'))['actual_revenue_total__sum'] or 0,
        'total_actual_expense': active_budgets.aggregate(
            Sum('actual_expense_total'))['actual_expense_total__sum'] or 0,
    }
    
    return JsonResponse(stats)


@require_http_methods(["GET"])
def journal_entry_quick_stats(request):
    """Get quick statistics for journal entries"""
    
    today = timezone.now().date()
    
    stats = {
        'total': JournalEntry.objects.count(),
        'draft': JournalEntry.objects.filter(status='DRAFT').count(),
        'posted': JournalEntry.objects.filter(status='POSTED').count(),
        'this_month': JournalEntry.objects.filter(
            entry_date__month=today.month,
            entry_date__year=today.year
        ).count(),
        'pending_post': JournalEntry.objects.filter(status='DRAFT').count(),
    }
    
    return JsonResponse(stats)