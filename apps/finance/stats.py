# finance/stats.py

"""
Comprehensive statistics utility functions for Finance models.
Provides detailed analytics for accounts, expenses, journal entries, 
budgets, and overall financial performance tracking.
"""

from django.utils import timezone
from django.db.models import (
    Count, Q, Avg, Sum, Max, Min, F, Case, When,
    IntegerField, FloatField, DecimalField, Value,
    Subquery, OuterRef, Exists
)
from django.db.models.functions import (
    TruncMonth, TruncYear, TruncWeek, TruncDate, 
    TruncQuarter, Coalesce
)
from datetime import timedelta, date, datetime
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

# =============================================================================
# ACCOUNT STATISTICS
# =============================================================================

def get_account_statistics(filters=None):
    """
    Get comprehensive account statistics
    
    Args:
        filters (dict): Optional filters
            - account_type: Filter by account type ID
            - account_type_category: Filter by account category (ASSET, LIABILITY, etc.)
            - is_active: Filter by active status
            - is_bank_account: Filter bank accounts
            - is_cash_account: Filter cash accounts
            - has_balance: Filter accounts with non-zero balances
    
    Returns:
        dict: Account statistics
    """
    from .models import Account, AccountType
    
    accounts = Account.objects.select_related('account_type')
    
    # Apply filters
    if filters:
        if filters.get('account_type'):
            accounts = accounts.filter(account_type_id=filters['account_type'])
        
        if filters.get('account_type_category'):
            accounts = accounts.filter(
                account_type__account_type=filters['account_type_category']
            )
        
        if filters.get('is_active') is not None:
            accounts = accounts.filter(is_active=filters['is_active'])
        
        if filters.get('is_bank_account') is not None:
            accounts = accounts.filter(is_bank_account=filters['is_bank_account'])
        
        if filters.get('is_cash_account') is not None:
            accounts = accounts.filter(is_cash_account=filters['is_cash_account'])
        
        if filters.get('has_balance'):
            accounts = accounts.exclude(current_balance=0)
    
    total_accounts = accounts.count()
    
    stats = {
        'total_accounts': total_accounts,
        'active_accounts': accounts.filter(is_active=True).count(),
        'inactive_accounts': accounts.filter(is_active=False).count(),
    }
    
    # By account type category
    category_stats = accounts.values(
        'account_type__account_type'
    ).annotate(
        count=Count('id'),
        total_balance=Coalesce(Sum('current_balance'), Decimal('0.00')),
    ).order_by('account_type__account_type')
    
    stats['by_category'] = {
        item['account_type__account_type']: {
            'count': item['count'],
            'total_balance': float(item['total_balance']),
        }
        for item in category_stats
    }
    
    # Account type breakdown
    type_stats = accounts.values(
        'account_type__name',
        'account_type__account_type'
    ).annotate(
        count=Count('id'),
        total_balance=Coalesce(Sum('current_balance'), Decimal('0.00')),
    ).order_by('-count')[:20]
    
    stats['by_type'] = [
        {
            'type_name': item['account_type__name'],
            'category': item['account_type__account_type'],
            'count': item['count'],
            'total_balance': float(item['total_balance']),
        }
        for item in type_stats
    ]
    
    # Balance analysis
    balance_stats = accounts.aggregate(
        total_balance=Coalesce(Sum('current_balance'), Decimal('0.00')),
        avg_balance=Coalesce(Avg('current_balance'), Decimal('0.00')),
        max_balance=Coalesce(Max('current_balance'), Decimal('0.00')),
        min_balance=Coalesce(Min('current_balance'), Decimal('0.00')),
    )
    
    stats['balance_summary'] = {
        'total_balance': float(balance_stats['total_balance']),
        'average_balance': float(balance_stats['avg_balance']),
        'max_balance': float(balance_stats['max_balance']),
        'min_balance': float(balance_stats['min_balance']),
    }
    
    # Asset accounts
    asset_accounts = accounts.filter(account_type__account_type='ASSET')
    asset_stats = asset_accounts.aggregate(
        total=Coalesce(Sum('current_balance'), Decimal('0.00')),
        count=Count('id'),
    )
    
    stats['assets'] = {
        'total_accounts': asset_stats['count'],
        'total_value': float(asset_stats['total']),
        'cash_accounts': accounts.filter(is_cash_account=True).count(),
        'bank_accounts': accounts.filter(is_bank_account=True).count(),
        'receivable_accounts': accounts.filter(is_receivable_account=True).count(),
        'inventory_accounts': accounts.filter(is_inventory_account=True).count(),
        'fixed_assets': accounts.filter(is_fixed_asset=True).count(),
    }
    
    # Liability accounts
    liability_accounts = accounts.filter(account_type__account_type='LIABILITY')
    liability_stats = liability_accounts.aggregate(
        total=Coalesce(Sum('current_balance'), Decimal('0.00')),
        count=Count('id'),
    )
    
    stats['liabilities'] = {
        'total_accounts': liability_stats['count'],
        'total_value': float(liability_stats['total']),
        'payable_accounts': accounts.filter(is_payable_account=True).count(),
        'loan_accounts': accounts.filter(is_loan_account=True).count(),
    }
    
    # Equity accounts
    equity_accounts = accounts.filter(account_type__account_type='EQUITY')
    equity_stats = equity_accounts.aggregate(
        total=Coalesce(Sum('current_balance'), Decimal('0.00')),
        count=Count('id'),
    )
    
    stats['equity'] = {
        'total_accounts': equity_stats['count'],
        'total_value': float(equity_stats['total']),
    }
    
    # Revenue accounts
    revenue_accounts = accounts.filter(account_type__account_type='REVENUE')
    revenue_stats = revenue_accounts.aggregate(
        total=Coalesce(Sum('current_balance'), Decimal('0.00')),
        count=Count('id'),
    )
    
    stats['revenue'] = {
        'total_accounts': revenue_stats['count'],
        'total_value': float(revenue_stats['total']),
    }
    
    # Expense accounts
    expense_accounts = accounts.filter(account_type__account_type='EXPENSE')
    expense_stats = expense_accounts.aggregate(
        total=Coalesce(Sum('current_balance'), Decimal('0.00')),
        count=Count('id'),
    )
    
    stats['expenses'] = {
        'total_accounts': expense_stats['count'],
        'total_value': float(expense_stats['total']),
    }
    
    # Cash and bank accounts detail
    cash_bank_stats = accounts.filter(
        Q(is_cash_account=True) | Q(is_bank_account=True)
    ).aggregate(
        total_liquid=Coalesce(Sum('current_balance'), Decimal('0.00')),
        count=Count('id'),
    )
    
    stats['liquid_assets'] = {
        'total_accounts': cash_bank_stats['count'],
        'total_value': float(cash_bank_stats['total_liquid']),
    }
    
    # Mobile money accounts
    mobile_money = accounts.filter(is_mobile_money_account=True)
    mobile_stats = mobile_money.aggregate(
        total=Coalesce(Sum('current_balance'), Decimal('0.00')),
        count=Count('id'),
    )
    
    stats['mobile_money'] = {
        'total_accounts': mobile_stats['count'],
        'total_balance': float(mobile_stats['total']),
    }
    
    # Reconciliation status
    reconcilable = accounts.filter(is_reconcilable=True)
    stats['reconciliation'] = {
        'reconcilable_accounts': reconcilable.count(),
        'recently_reconciled': reconcilable.filter(
            last_reconciled_date__gte=timezone.now().date() - timedelta(days=30)
        ).count(),
        'never_reconciled': reconcilable.filter(
            last_reconciled_date__isnull=True
        ).count(),
    }
    
    # Top accounts by balance (positive)
    top_positive = accounts.filter(
        current_balance__gt=0
    ).order_by('-current_balance')[:10]
    
    stats['top_positive_balances'] = [
        {
            'account_number': acc.account_number,
            'account_name': acc.name,
            'account_type': acc.account_type.name,
            'balance': float(acc.current_balance),
        }
        for acc in top_positive
    ]
    
    # Top accounts by balance (negative - debts/liabilities)
    top_negative = accounts.filter(
        current_balance__lt=0
    ).order_by('current_balance')[:10]
    
    stats['top_negative_balances'] = [
        {
            'account_number': acc.account_number,
            'account_name': acc.name,
            'account_type': acc.account_type.name,
            'balance': float(acc.current_balance),
        }
        for acc in top_negative
    ]
    
    return stats


# =============================================================================
# EXPENSE STATISTICS
# =============================================================================

def get_expense_statistics(filters=None):
    """
    Get comprehensive expense statistics
    
    Args:
        filters (dict): Optional filters
            - status: Filter by expense status
            - category: Filter by expense category ID
            - category_type: Filter by category type
            - academic_session: Filter by session ID
            - fiscal_period: Filter by fiscal period ID
            - date_from: Start date for expense_date filter
            - date_to: End date for expense_date filter
            - vendor_name: Filter by vendor
    
    Returns:
        dict: Expense statistics
    """
    from .models import Expense, ExpenseCategory, ExpenseLine
    
    expenses = Expense.objects.select_related(
        'category', 'academic_session', 'fiscal_period', 'expense_account'
    )
    
    # Apply filters
    if filters:
        if filters.get('status'):
            expenses = expenses.filter(status=filters['status'])
        
        if filters.get('category'):
            expenses = expenses.filter(category_id=filters['category'])
        
        if filters.get('category_type'):
            expenses = expenses.filter(category__category_type=filters['category_type'])
        
        if filters.get('academic_session'):
            expenses = expenses.filter(academic_session_id=filters['academic_session'])
        
        if filters.get('fiscal_period'):
            expenses = expenses.filter(fiscal_period_id=filters['fiscal_period'])
        
        if filters.get('date_from'):
            expenses = expenses.filter(expense_date__gte=filters['date_from'])
        
        if filters.get('date_to'):
            expenses = expenses.filter(expense_date__lte=filters['date_to'])
        
        if filters.get('vendor_name'):
            expenses = expenses.filter(vendor_name__icontains=filters['vendor_name'])
    
    total_expenses = expenses.count()
    
    stats = {
        'total_expenses': total_expenses,
    }
    
    # Status breakdown
    status_breakdown = expenses.values('status').annotate(
        count=Count('id'),
        total_amount=Coalesce(Sum('total_amount'), Decimal('0.00')),
        total_tax=Coalesce(Sum('tax_amount'), Decimal('0.00')),
    ).order_by('-count')
    
    stats['by_status'] = {
        item['status']: {
            'count': item['count'],
            'total_amount': float(item['total_amount']),
            'total_tax': float(item['total_tax']),
        }
        for item in status_breakdown
    }
    
    # Financial totals
    financial_totals = expenses.aggregate(
        total_amount=Coalesce(Sum('total_amount'), Decimal('0.00')),
        subtotal=Coalesce(Sum('subtotal_amount'), Decimal('0.00')),
        total_tax=Coalesce(Sum('tax_amount'), Decimal('0.00')),
        avg_expense=Coalesce(Avg('total_amount'), Decimal('0.00')),
        max_expense=Coalesce(Max('total_amount'), Decimal('0.00')),
        min_expense=Coalesce(Min('total_amount'), Decimal('0.00')),
    )
    
    stats['financial_totals'] = {
        'total_expenses': float(financial_totals['total_amount']),
        'subtotal': float(financial_totals['subtotal']),
        'total_tax': float(financial_totals['total_tax']),
        'average_expense': float(financial_totals['avg_expense']),
        'largest_expense': float(financial_totals['max_expense']),
        'smallest_expense': float(financial_totals['min_expense']),
    }
    
    # Category breakdown
    category_stats = expenses.values(
        'category__name',
        'category__category_type'
    ).annotate(
        count=Count('id'),
        total_amount=Coalesce(Sum('total_amount'), Decimal('0.00')),
    ).order_by('-total_amount')[:20]
    
    stats['by_category'] = [
        {
            'category': item['category__name'],
            'type': item['category__category_type'],
            'count': item['count'],
            'total_amount': float(item['total_amount']),
            'percentage': round(
                (item['total_amount'] / financial_totals['total_amount'] * 100)
                if financial_totals['total_amount'] > 0 else 0,
                2
            ),
        }
        for item in category_stats
    ]
    
    # Category type breakdown
    type_stats = expenses.values(
        'category__category_type'
    ).annotate(
        count=Count('id'),
        total_amount=Coalesce(Sum('total_amount'), Decimal('0.00')),
    ).order_by('-total_amount')
    
    stats['by_category_type'] = [
        {
            'type': item['category__category_type'],
            'count': item['count'],
            'total_amount': float(item['total_amount']),
            'percentage': round(
                (item['total_amount'] / financial_totals['total_amount'] * 100)
                if financial_totals['total_amount'] > 0 else 0,
                2
            ),
        }
        for item in type_stats
    ]
    
    # Approval statistics
    approved = expenses.filter(status='APPROVED')
    pending = expenses.filter(status='PENDING_APPROVAL')
    rejected = expenses.filter(status='REJECTED')
    
    stats['approval'] = {
        'approved_count': approved.count(),
        'approved_amount': float(
            approved.aggregate(total=Coalesce(Sum('total_amount'), Decimal('0.00')))['total']
        ),
        'pending_count': pending.count(),
        'pending_amount': float(
            pending.aggregate(total=Coalesce(Sum('total_amount'), Decimal('0.00')))['total']
        ),
        'rejected_count': rejected.count(),
        'rejected_amount': float(
            rejected.aggregate(total=Coalesce(Sum('total_amount'), Decimal('0.00')))['total']
        ),
        'approval_rate': round(
            (approved.count() / total_expenses * 100) if total_expenses > 0 else 0,
            2
        ),
    }
    
    # Payment status
    paid = expenses.filter(status='PAID')
    unpaid = expenses.exclude(status='PAID')
    
    stats['payment_status'] = {
        'paid_count': paid.count(),
        'paid_amount': float(
            paid.aggregate(total=Coalesce(Sum('total_amount'), Decimal('0.00')))['total']
        ),
        'unpaid_count': unpaid.count(),
        'unpaid_amount': float(
            unpaid.aggregate(total=Coalesce(Sum('total_amount'), Decimal('0.00')))['total']
        ),
    }
    
    # Vendor analysis
    vendor_stats = expenses.exclude(vendor_name='').values(
        'vendor_name'
    ).annotate(
        count=Count('id'),
        total_amount=Coalesce(Sum('total_amount'), Decimal('0.00')),
    ).order_by('-total_amount')[:20]
    
    stats['top_vendors'] = [
        {
            'vendor_name': item['vendor_name'],
            'expense_count': item['count'],
            'total_amount': float(item['total_amount']),
        }
        for item in vendor_stats
    ]
    
    # Session breakdown
    session_stats = expenses.filter(
        academic_session__isnull=False
    ).values(
        'academic_session__year_name',
        'academic_session__term_name'
    ).annotate(
        count=Count('id'),
        total_amount=Coalesce(Sum('total_amount'), Decimal('0.00')),
    ).order_by('-total_amount')[:10]
    
    stats['by_session'] = [
        {
            'session': f"{item['academic_session__year_name']} - {item['academic_session__term_name']}",
            'count': item['count'],
            'total_amount': float(item['total_amount']),
        }
        for item in session_stats
    ]
    
    # Fiscal period breakdown
    period_stats = expenses.values(
        'fiscal_period__name',
        'fiscal_period__fiscal_year__name'
    ).annotate(
        count=Count('id'),
        total_amount=Coalesce(Sum('total_amount'), Decimal('0.00')),
    ).order_by('-fiscal_period__start_date')[:12]
    
    stats['by_fiscal_period'] = [
        {
            'period': item['fiscal_period__name'],
            'fiscal_year': item['fiscal_period__fiscal_year__name'],
            'count': item['count'],
            'total_amount': float(item['total_amount']),
        }
        for item in period_stats
    ]
    
    # Time trends
    if expenses.exists():
        # Monthly expenses
        monthly_expenses = expenses.annotate(
            month=TruncMonth('expense_date')
        ).values('month').annotate(
            count=Count('id'),
            total=Coalesce(Sum('total_amount'), Decimal('0.00')),
        ).order_by('-month')[:12]
        
        stats['monthly_trends'] = [
            {
                'month': item['month'].strftime('%Y-%m'),
                'count': item['count'],
                'total': float(item['total']),
            }
            for item in monthly_expenses
        ]
        
        # Daily expenses (last 30 days)
        thirty_days_ago = timezone.now().date() - timedelta(days=30)
        daily_expenses = expenses.filter(
            expense_date__gte=thirty_days_ago
        ).annotate(
            day=TruncDate('expense_date')
        ).values('day').annotate(
            count=Count('id'),
            total=Coalesce(Sum('total_amount'), Decimal('0.00')),
        ).order_by('day')
        
        stats['daily_trends'] = [
            {
                'date': item['day'].isoformat(),
                'count': item['count'],
                'total': float(item['total']),
            }
            for item in daily_expenses
        ]
    
    # Recurring expenses
    recurring = expenses.filter(is_recurring=True)
    stats['recurring_expenses'] = {
        'count': recurring.count(),
        'total_amount': float(
            recurring.aggregate(total=Coalesce(Sum('total_amount'), Decimal('0.00')))['total']
        ),
    }
    
    # Budget tracking
    with_budget = expenses.filter(budget_line__isnull=False)
    stats['budget_tracking'] = {
        'expenses_with_budget': with_budget.count(),
        'expenses_without_budget': expenses.filter(budget_line__isnull=True).count(),
    }
    
    # Recent activity
    now = timezone.now()
    stats['recent_activity'] = {
        'created_last_24_hours': expenses.filter(
            created_at__gte=now - timedelta(hours=24)
        ).count(),
        'created_last_7_days': expenses.filter(
            created_at__gte=now - timedelta(days=7)
        ).count(),
        'created_last_30_days': expenses.filter(
            created_at__gte=now - timedelta(days=30)
        ).count(),
        'approved_last_7_days': expenses.filter(
            status='APPROVED',
            approval_date__gte=now - timedelta(days=7)
        ).count(),
    }
    
    return stats


# =============================================================================
# EXPENSE PAYMENT STATISTICS
# =============================================================================

def get_expense_payment_statistics(filters=None):
    """
    Get comprehensive expense payment statistics
    
    Args:
        filters (dict): Optional filters
            - status: Filter by payment status
            - payment_method: Filter by payment method ID
            - fiscal_period: Filter by fiscal period ID
            - date_from: Start date filter
            - date_to: End date filter
            - is_verified: Filter by verification status
    
    Returns:
        dict: Expense payment statistics
    """
    from .models import ExpensePayment
    
    payments = ExpensePayment.objects.select_related(
        'expense', 'payment_method', 'account', 'fiscal_period'
    )
    
    # Apply filters
    if filters:
        if filters.get('status'):
            payments = payments.filter(status=filters['status'])
        
        if filters.get('payment_method'):
            payments = payments.filter(payment_method_id=filters['payment_method'])
        
        if filters.get('fiscal_period'):
            payments = payments.filter(fiscal_period_id=filters['fiscal_period'])
        
        if filters.get('date_from'):
            payments = payments.filter(payment_date__gte=filters['date_from'])
        
        if filters.get('date_to'):
            payments = payments.filter(payment_date__lte=filters['date_to'])
        
        if filters.get('is_verified') is not None:
            payments = payments.filter(is_verified=filters['is_verified'])
    
    total_payments = payments.count()
    
    stats = {
        'total_payments': total_payments,
    }
    
    # Status breakdown
    status_breakdown = payments.values('status').annotate(
        count=Count('id'),
        total_amount=Coalesce(Sum('amount'), Decimal('0.00')),
        total_fees=Coalesce(Sum('processing_fee'), Decimal('0.00')),
    ).order_by('-count')
    
    stats['by_status'] = {
        item['status']: {
            'count': item['count'],
            'total_amount': float(item['total_amount']),
            'total_fees': float(item['total_fees']),
        }
        for item in status_breakdown
    }
    
    # Financial totals
    financial_totals = payments.aggregate(
        total_amount=Coalesce(Sum('amount'), Decimal('0.00')),
        total_fees=Coalesce(Sum('processing_fee'), Decimal('0.00')),
        total_bank_charges=Coalesce(Sum('bank_charges'), Decimal('0.00')),
        avg_payment=Coalesce(Avg('amount'), Decimal('0.00')),
        max_payment=Coalesce(Max('amount'), Decimal('0.00')),
        min_payment=Coalesce(Min('amount'), Decimal('0.00')),
    )
    
    stats['financial_totals'] = {
        'total_paid': float(financial_totals['total_amount']),
        'total_processing_fees': float(financial_totals['total_fees']),
        'total_bank_charges': float(financial_totals['total_bank_charges']),
        'total_costs': float(
            financial_totals['total_fees'] + financial_totals['total_bank_charges']
        ),
        'net_paid': float(
            financial_totals['total_amount'] + 
            financial_totals['total_fees'] + 
            financial_totals['total_bank_charges']
        ),
        'average_payment': float(financial_totals['avg_payment']),
        'largest_payment': float(financial_totals['max_payment']),
        'smallest_payment': float(financial_totals['min_payment']),
    }
    
    # Payment method breakdown
    method_stats = payments.values(
        'payment_method__name',
        'payment_method__method_type'
    ).annotate(
        count=Count('id'),
        total_amount=Coalesce(Sum('amount'), Decimal('0.00')),
        total_fees=Coalesce(Sum('processing_fee'), Decimal('0.00')),
    ).order_by('-total_amount')
    
    stats['by_payment_method'] = [
        {
            'method': item['payment_method__name'],
            'type': item['payment_method__method_type'],
            'count': item['count'],
            'total_amount': float(item['total_amount']),
            'total_fees': float(item['total_fees']),
            'percentage': round(
                (item['count'] / total_payments * 100) if total_payments > 0 else 0,
                2
            ),
        }
        for item in method_stats
    ]
    
    # Account breakdown
    account_stats = payments.values(
        'account__account_number',
        'account__name'
    ).annotate(
        count=Count('id'),
        total_amount=Coalesce(Sum('amount'), Decimal('0.00')),
    ).order_by('-total_amount')[:10]
    
    stats['by_account'] = [
        {
            'account': f"{item['account__account_number']} - {item['account__name']}",
            'count': item['count'],
            'total_amount': float(item['total_amount']),
        }
        for item in account_stats
    ]
    
    # Verification status
    verified = payments.filter(is_verified=True)
    unverified = payments.filter(is_verified=False)
    
    stats['verification'] = {
        'verified_count': verified.count(),
        'verified_amount': float(
            verified.aggregate(total=Coalesce(Sum('amount'), Decimal('0.00')))['total']
        ),
        'unverified_count': unverified.count(),
        'unverified_amount': float(
            unverified.aggregate(total=Coalesce(Sum('amount'), Decimal('0.00')))['total']
        ),
        'verification_rate': round(
            (verified.count() / total_payments * 100) if total_payments > 0 else 0,
            2
        ),
    }
    
    # Fiscal period breakdown
    period_stats = payments.values(
        'fiscal_period__name',
        'fiscal_period__fiscal_year__name'
    ).annotate(
        count=Count('id'),
        total_amount=Coalesce(Sum('amount'), Decimal('0.00')),
    ).order_by('-fiscal_period__start_date')[:12]
    
    stats['by_fiscal_period'] = [
        {
            'period': item['fiscal_period__name'],
            'fiscal_year': item['fiscal_period__fiscal_year__name'],
            'count': item['count'],
            'total_amount': float(item['total_amount']),
        }
        for item in period_stats
    ]
    
    # Time trends
    if payments.exists():
        # Monthly payments
        monthly_payments = payments.annotate(
            month=TruncMonth('payment_date')
        ).values('month').annotate(
            count=Count('id'),
            total=Coalesce(Sum('amount'), Decimal('0.00')),
        ).order_by('-month')[:12]
        
        stats['monthly_trends'] = [
            {
                'month': item['month'].strftime('%Y-%m'),
                'count': item['count'],
                'total': float(item['total']),
            }
            for item in monthly_payments
        ]
        
        # Daily payments (last 30 days)
        thirty_days_ago = timezone.now().date() - timedelta(days=30)
        daily_payments = payments.filter(
            payment_date__gte=thirty_days_ago
        ).annotate(
            day=TruncDate('payment_date')
        ).values('day').annotate(
            count=Count('id'),
            total=Coalesce(Sum('amount'), Decimal('0.00')),
        ).order_by('day')
        
        stats['daily_trends'] = [
            {
                'date': item['day'].isoformat(),
                'count': item['count'],
                'total': float(item['total']),
            }
            for item in daily_payments
        ]
    
    # Batch analysis
    batched = payments.exclude(batch_number='')
    stats['batch_payments'] = {
        'count': batched.count(),
        'total_amount': float(
            batched.aggregate(total=Coalesce(Sum('amount'), Decimal('0.00')))['total']
        ),
        'unique_batches': batched.values('batch_number').distinct().count(),
    }
    
    # Recent activity
    now = timezone.now()
    stats['recent_activity'] = {
        'payments_last_24_hours': payments.filter(
            created_at__gte=now - timedelta(hours=24)
        ).count(),
        'payments_last_7_days': payments.filter(
            created_at__gte=now - timedelta(days=7)
        ).count(),
        'payments_last_30_days': payments.filter(
            created_at__gte=now - timedelta(days=30)
        ).count(),
        'verified_last_7_days': payments.filter(
            is_verified=True,
            verification_date__gte=now - timedelta(days=7)
        ).count(),
    }
    
    return stats


# =============================================================================
# JOURNAL STATISTICS
# =============================================================================

def get_journal_statistics(filters=None):
    """
    Get comprehensive journal statistics
    
    Args:
        filters (dict): Optional filters
            - journal_type: Filter by journal type
            - is_active: Filter by active status
    
    Returns:
        dict: Journal statistics
    """
    from .models import Journal, JournalEntry
    
    journals = Journal.objects.all()
    
    if filters:
        if filters.get('journal_type'):
            journals = journals.filter(journal_type=filters['journal_type'])
        if filters.get('is_active') is not None:
            journals = journals.filter(is_active=filters['is_active'])
    
    total_journals = journals.count()
    
    stats = {
        'total_journals': total_journals,
        'active_journals': journals.filter(is_active=True).count(),
        'inactive_journals': journals.filter(is_active=False).count(),
    }
    
    # By type
    type_stats = journals.values('journal_type').annotate(
        count=Count('id'),
        entry_count=Count('entries', distinct=True),
    ).order_by('-count')
    
    stats['by_type'] = {
        item['journal_type']: {
            'count': item['count'],
            'entry_count': item['entry_count'],
        }
        for item in type_stats
    }
    
    # Entry statistics per journal
    journal_entry_stats = journals.annotate(
        entry_count=Count('entries', distinct=True),
        posted_entries=Count(
            'entries',
            filter=Q(entries__status='POSTED'),
            distinct=True
        ),
        draft_entries=Count(
            'entries',
            filter=Q(entries__status='DRAFT'),
            distinct=True
        ),
    ).order_by('-entry_count')[:10]
    
    stats['top_journals_by_entries'] = [
        {
            'journal_id': str(j.id),
            'name': j.name,
            'type': j.journal_type,
            'total_entries': j.entry_count,
            'posted_entries': j.posted_entries,
            'draft_entries': j.draft_entries,
        }
        for j in journal_entry_stats
    ]
    
    # Total entries across all journals
    total_entries = JournalEntry.objects.filter(journal__in=journals).count()
    
    stats['total_entries'] = total_entries
    stats['average_entries_per_journal'] = round(
        total_entries / total_journals if total_journals > 0 else 0,
        2
    )
    
    return stats


# =============================================================================
# JOURNAL ENTRY STATISTICS
# =============================================================================

def get_journal_entry_statistics(filters=None):
    """
    Get comprehensive journal entry statistics
    
    Args:
        filters (dict): Optional filters
            - journal: Filter by journal ID
            - journal_type: Filter by journal type
            - status: Filter by entry status
            - fiscal_period: Filter by fiscal period ID
            - academic_session: Filter by session ID
            - date_from: Start date filter
            - date_to: End date filter
    
    Returns:
        dict: Journal entry statistics
    """
    from .models import JournalEntry, JournalTransaction
    
    entries = JournalEntry.objects.select_related(
        'journal', 'fiscal_period', 'academic_session'
    )
    
    # Apply filters
    if filters:
        if filters.get('journal'):
            entries = entries.filter(journal_id=filters['journal'])
        
        if filters.get('journal_type'):
            entries = entries.filter(journal__journal_type=filters['journal_type'])
        
        if filters.get('status'):
            entries = entries.filter(status=filters['status'])
        
        if filters.get('fiscal_period'):
            entries = entries.filter(fiscal_period_id=filters['fiscal_period'])
        
        if filters.get('academic_session'):
            entries = entries.filter(academic_session_id=filters['academic_session'])
        
        if filters.get('date_from'):
            entries = entries.filter(entry_date__gte=filters['date_from'])
        
        if filters.get('date_to'):
            entries = entries.filter(entry_date__lte=filters['date_to'])
    
    total_entries = entries.count()
    
    stats = {
        'total_entries': total_entries,
    }
    
    # Status breakdown
    status_breakdown = entries.values('status').annotate(
        count=Count('id')
    ).order_by('-count')
    
    stats['by_status'] = {
        item['status']: item['count']
        for item in status_breakdown
    }
    
    # Journal type breakdown
    journal_stats = entries.values(
        'journal__name',
        'journal__journal_type'
    ).annotate(
        count=Count('id')
    ).order_by('-count')
    
    stats['by_journal'] = [
        {
            'journal': item['journal__name'],
            'type': item['journal__journal_type'],
            'count': item['count'],
        }
        for item in journal_stats
    ]
    
    # Transaction analysis
    transactions = JournalTransaction.objects.filter(
        journal_entry__in=entries
    )
    
    transaction_stats = transactions.aggregate(
        total_debits=Coalesce(
            Sum('amount', filter=Q(is_debit=True)),
            Decimal('0.00')
        ),
        total_credits=Coalesce(
            Sum('amount', filter=Q(is_debit=False)),
            Decimal('0.00')
        ),
        total_transactions=Count('id'),
        debit_count=Count('id', filter=Q(is_debit=True)),
        credit_count=Count('id', filter=Q(is_debit=False)),
    )
    
    stats['transactions'] = {
        'total_count': transaction_stats['total_transactions'],
        'debit_count': transaction_stats['debit_count'],
        'credit_count': transaction_stats['credit_count'],
        'total_debits': float(transaction_stats['total_debits']),
        'total_credits': float(transaction_stats['total_credits']),
        'balance': float(
            transaction_stats['total_debits'] - transaction_stats['total_credits']
        ),
    }
    
    # Posted vs Draft
    posted = entries.filter(status='POSTED')
    draft = entries.filter(status='DRAFT')
    reversed = entries.filter(status='REVERSED')
    
    stats['entry_status'] = {
        'posted': posted.count(),
        'draft': draft.count(),
        'reversed': reversed.count(),
        'posting_rate': round(
            (posted.count() / total_entries * 100) if total_entries > 0 else 0,
            2
        ),
    }
    
    # Fiscal period breakdown
    period_stats = entries.values(
        'fiscal_period__name',
        'fiscal_period__fiscal_year__name'
    ).annotate(
        count=Count('id')
    ).order_by('-fiscal_period__start_date')[:12]
    
    stats['by_fiscal_period'] = [
        {
            'period': item['fiscal_period__name'],
            'fiscal_year': item['fiscal_period__fiscal_year__name'],
            'count': item['count'],
        }
        for item in period_stats
    ]
    
    # Session breakdown
    session_stats = entries.filter(
        academic_session__isnull=False
    ).values(
        'academic_session__year_name',
        'academic_session__term_name'
    ).annotate(
        count=Count('id')
    ).order_by('-count')[:10]
    
    stats['by_session'] = [
        {
            'session': f"{item['academic_session__year_name']} - {item['academic_session__term_name']}",
            'count': item['count'],
        }
        for item in session_stats
    ]
    
    # Time trends
    if entries.exists():
        # Monthly entries
        monthly_entries = entries.annotate(
            month=TruncMonth('entry_date')
        ).values('month').annotate(
            count=Count('id')
        ).order_by('-month')[:12]
        
        stats['monthly_trends'] = [
            {
                'month': item['month'].strftime('%Y-%m'),
                'count': item['count'],
            }
            for item in monthly_entries
        ]
    
    # Reversal analysis
    stats['reversals'] = {
        'total_reversed': reversed.count(),
        'reversal_rate': round(
            (reversed.count() / total_entries * 100) if total_entries > 0 else 0,
            2
        ),
    }
    
    # Recent activity
    now = timezone.now()
    stats['recent_activity'] = {
        'created_last_24_hours': entries.filter(
            created_at__gte=now - timedelta(hours=24)
        ).count(),
        'created_last_7_days': entries.filter(
            created_at__gte=now - timedelta(days=7)
        ).count(),
        'created_last_30_days': entries.filter(
            created_at__gte=now - timedelta(days=30)
        ).count(),
        'posted_last_7_days': entries.filter(
            status='POSTED',
            posted_at__gte=now - timedelta(days=7)
        ).count(),
    }
    
    return stats


# =============================================================================
# BUDGET STATISTICS
# =============================================================================

def get_budget_statistics(filters=None):
    """
    Get comprehensive budget statistics
    
    Args:
        filters (dict): Optional filters
            - budget_type: Filter by budget type
            - status: Filter by budget status
            - fiscal_year: Filter by fiscal year ID
            - academic_session: Filter by session ID
    
    Returns:
        dict: Budget statistics
    """
    from .models import Budget, BudgetLine
    
    budgets = Budget.objects.select_related(
        'fiscal_year', 'academic_session'
    )
    
    # Apply filters
    if filters:
        if filters.get('budget_type'):
            budgets = budgets.filter(budget_type=filters['budget_type'])
        
        if filters.get('status'):
            budgets = budgets.filter(status=filters['status'])
        
        if filters.get('fiscal_year'):
            budgets = budgets.filter(fiscal_year_id=filters['fiscal_year'])
        
        if filters.get('academic_session'):
            budgets = budgets.filter(academic_session_id=filters['academic_session'])
    
    total_budgets = budgets.count()
    
    stats = {
        'total_budgets': total_budgets,
    }
    
    # Status breakdown
    status_breakdown = budgets.values('status').annotate(
        count=Count('id'),
        total_revenue=Coalesce(Sum('total_revenue_budget'), Decimal('0.00')),
        total_expense=Coalesce(Sum('total_expense_budget'), Decimal('0.00')),
    ).order_by('-count')
    
    stats['by_status'] = {
        item['status']: {
            'count': item['count'],
            'total_revenue': float(item['total_revenue']),
            'total_expense': float(item['total_expense']),
        }
        for item in status_breakdown
    }
    
    # Type breakdown
    type_stats = budgets.values('budget_type').annotate(
        count=Count('id'),
        total_revenue=Coalesce(Sum('total_revenue_budget'), Decimal('0.00')),
        total_expense=Coalesce(Sum('total_expense_budget'), Decimal('0.00')),
    ).order_by('-count')
    
    stats['by_type'] = {
        item['budget_type']: {
            'count': item['count'],
            'total_revenue': float(item['total_revenue']),
            'total_expense': float(item['total_expense']),
        }
        for item in type_stats
    }
    
    # Financial totals
    financial_totals = budgets.aggregate(
        total_revenue_budget=Coalesce(Sum('total_revenue_budget'), Decimal('0.00')),
        total_expense_budget=Coalesce(Sum('total_expense_budget'), Decimal('0.00')),
        total_net_budget=Coalesce(Sum('net_budget'), Decimal('0.00')),
        actual_revenue=Coalesce(Sum('actual_revenue_total'), Decimal('0.00')),
        actual_expense=Coalesce(Sum('actual_expense_total'), Decimal('0.00')),
    )
    
    stats['financial_totals'] = {
        'total_revenue_budgeted': float(financial_totals['total_revenue_budget']),
        'total_expense_budgeted': float(financial_totals['total_expense_budget']),
        'net_budget': float(financial_totals['total_net_budget']),
        'actual_revenue': float(financial_totals['actual_revenue']),
        'actual_expense': float(financial_totals['actual_expense']),
        'actual_net': float(
            financial_totals['actual_revenue'] - financial_totals['actual_expense']
        ),
    }
    
    # Variance analysis
    revenue_variance = (
        financial_totals['actual_revenue'] - 
        financial_totals['total_revenue_budget']
    )
    expense_variance = (
        financial_totals['actual_expense'] - 
        financial_totals['total_expense_budget']
    )
    
    stats['variance_analysis'] = {
        'revenue_variance': float(revenue_variance),
        'revenue_variance_percentage': round(
            (revenue_variance / financial_totals['total_revenue_budget'] * 100)
            if financial_totals['total_revenue_budget'] > 0 else 0,
            2
        ),
        'expense_variance': float(expense_variance),
        'expense_variance_percentage': round(
            (expense_variance / financial_totals['total_expense_budget'] * 100)
            if financial_totals['total_expense_budget'] > 0 else 0,
            2
        ),
    }
    
    # Utilization rates
    if financial_totals['total_revenue_budget'] > 0:
        revenue_utilization = (
            financial_totals['actual_revenue'] / 
            financial_totals['total_revenue_budget'] * 100
        )
    else:
        revenue_utilization = 0
    
    if financial_totals['total_expense_budget'] > 0:
        expense_utilization = (
            financial_totals['actual_expense'] / 
            financial_totals['total_expense_budget'] * 100
        )
    else:
        expense_utilization = 0
    
    stats['utilization'] = {
        'revenue_utilization': round(float(revenue_utilization), 2),
        'expense_utilization': round(float(expense_utilization), 2),
    }
    
    # Budget lines analysis
    budget_lines = BudgetLine.objects.filter(budget__in=budgets)
    
    line_stats = budget_lines.aggregate(
        total_lines=Count('id'),
        revenue_lines=Count('id', filter=Q(line_type='REVENUE')),
        expense_lines=Count('id', filter=Q(line_type='EXPENSE')),
        total_budgeted=Coalesce(Sum('budgeted_amount'), Decimal('0.00')),
        total_actual=Coalesce(Sum('actual_amount'), Decimal('0.00')),
    )
    
    stats['budget_lines'] = {
        'total_lines': line_stats['total_lines'],
        'revenue_lines': line_stats['revenue_lines'],
        'expense_lines': line_stats['expense_lines'],
        'total_budgeted': float(line_stats['total_budgeted']),
        'total_actual': float(line_stats['total_actual']),
        'variance': float(line_stats['total_actual'] - line_stats['total_budgeted']),
    }
    
    # Top budget lines by variance
    top_variances = budget_lines.annotate(
        variance=F('actual_amount') - F('budgeted_amount'),
        variance_pct=Case(
            When(budgeted_amount__gt=0,
                 then=(F('actual_amount') - F('budgeted_amount')) / F('budgeted_amount') * 100),
            default=Value(0),
            output_field=FloatField(),
        )
    ).select_related('account', 'budget').order_by('-variance')[:10]
    
    stats['top_variances'] = [
        {
            'budget': line.budget.name,
            'account': f"{line.account.account_number} - {line.account.name}",
            'line_type': line.line_type,
            'budgeted': float(line.budgeted_amount),
            'actual': float(line.actual_amount),
            'variance': float(line.variance),
            'variance_percentage': round(float(line.variance_pct), 2),
        }
        for line in top_variances
    ]
    
    # Fiscal year breakdown
    fiscal_stats = budgets.values(
        'fiscal_year__name'
    ).annotate(
        count=Count('id'),
        total_revenue=Coalesce(Sum('total_revenue_budget'), Decimal('0.00')),
        total_expense=Coalesce(Sum('total_expense_budget'), Decimal('0.00')),
    ).order_by('-fiscal_year__start_date')[:5]
    
    stats['by_fiscal_year'] = [
        {
            'fiscal_year': item['fiscal_year__name'],
            'count': item['count'],
            'total_revenue': float(item['total_revenue']),
            'total_expense': float(item['total_expense']),
        }
        for item in fiscal_stats
    ]
    
    # Session breakdown
    session_stats = budgets.values(
        'academic_session__year_name',
        'academic_session__term_name'
    ).annotate(
        count=Count('id'),
        total_revenue=Coalesce(Sum('total_revenue_budget'), Decimal('0.00')),
        total_expense=Coalesce(Sum('total_expense_budget'), Decimal('0.00')),
    ).order_by('-count')[:10]
    
    stats['by_session'] = [
        {
            'session': f"{item['academic_session__year_name']} - {item['academic_session__term_name']}",
            'count': item['count'],
            'total_revenue': float(item['total_revenue']),
            'total_expense': float(item['total_expense']),
        }
        for item in session_stats
    ]
    
    # Approval statistics
    approved = budgets.filter(status='APPROVED')
    pending = budgets.filter(status='SUBMITTED')
    
    stats['approval'] = {
        'approved_count': approved.count(),
        'pending_approval': pending.count(),
        'approval_rate': round(
            (approved.count() / total_budgets * 100) if total_budgets > 0 else 0,
            2
        ),
    }
    
    return stats


# =============================================================================
# CONSOLIDATED FINANCIAL DASHBOARD
# =============================================================================

def get_financial_dashboard(fiscal_period_id=None, academic_session_id=None):
    """
    Get consolidated financial dashboard with key metrics
    
    Args:
        fiscal_period_id: Optional fiscal period filter
        academic_session_id: Optional academic session filter
    
    Returns:
        dict: Comprehensive financial dashboard data
    """
    from .models import (
        Account, Expense, ExpensePayment, 
        JournalEntry, Budget
    )
    
    # Build base querysets
    accounts = Account.objects.all()
    expenses = Expense.objects.all()
    payments = ExpensePayment.objects.all()
    entries = JournalEntry.objects.all()
    budgets = Budget.objects.all()
    
    if fiscal_period_id:
        expenses = expenses.filter(fiscal_period_id=fiscal_period_id)
        payments = payments.filter(fiscal_period_id=fiscal_period_id)
        entries = entries.filter(fiscal_period_id=fiscal_period_id)
    
    if academic_session_id:
        expenses = expenses.filter(academic_session_id=academic_session_id)
        entries = entries.filter(academic_session_id=academic_session_id)
        budgets = budgets.filter(academic_session_id=academic_session_id)
    
    dashboard = {
        'summary': {
            'total_accounts': accounts.count(),
            'active_accounts': accounts.filter(is_active=True).count(),
            'total_expenses': expenses.count(),
            'total_payments': payments.count(),
            'total_journal_entries': entries.count(),
            'total_budgets': budgets.count(),
        },
    }
    
    # Balance sheet summary
    assets = accounts.filter(account_type__account_type='ASSET').aggregate(
        total=Coalesce(Sum('current_balance'), Decimal('0.00'))
    )
    liabilities = accounts.filter(account_type__account_type='LIABILITY').aggregate(
        total=Coalesce(Sum('current_balance'), Decimal('0.00'))
    )
    equity = accounts.filter(account_type__account_type='EQUITY').aggregate(
        total=Coalesce(Sum('current_balance'), Decimal('0.00'))
    )
    
    dashboard['balance_sheet'] = {
        'total_assets': float(assets['total']),
        'total_liabilities': float(liabilities['total']),
        'total_equity': float(equity['total']),
        'net_worth': float(assets['total'] - liabilities['total']),
    }
    
    # Income statement summary
    revenue = accounts.filter(account_type__account_type='REVENUE').aggregate(
        total=Coalesce(Sum('current_balance'), Decimal('0.00'))
    )
    expense_accounts = accounts.filter(account_type__account_type='EXPENSE').aggregate(
        total=Coalesce(Sum('current_balance'), Decimal('0.00'))
    )
    
    dashboard['income_statement'] = {
        'total_revenue': float(revenue['total']),
        'total_expenses': float(expense_accounts['total']),
        'net_income': float(revenue['total'] - expense_accounts['total']),
    }
    
    # Cash flow summary
    cash_accounts = accounts.filter(
        Q(is_cash_account=True) | Q(is_bank_account=True)
    ).aggregate(
        total=Coalesce(Sum('current_balance'), Decimal('0.00'))
    )
    
    dashboard['cash_flow'] = {
        'total_liquid_assets': float(cash_accounts['total']),
    }
    
    # Expense summary
    expense_totals = expenses.aggregate(
        total=Coalesce(Sum('total_amount'), Decimal('0.00')),
        approved=Coalesce(
            Sum('total_amount', filter=Q(status='APPROVED')),
            Decimal('0.00')
        ),
        paid=Coalesce(
            Sum('total_amount', filter=Q(status='PAID')),
            Decimal('0.00')
        ),
    )
    
    dashboard['expenses'] = {
        'total_expenses': float(expense_totals['total']),
        'approved_expenses': float(expense_totals['approved']),
        'paid_expenses': float(expense_totals['paid']),
    }
    
    # Payment summary
    payment_totals = payments.aggregate(
        total=Coalesce(Sum('amount'), Decimal('0.00')),
        verified=Coalesce(
            Sum('amount', filter=Q(is_verified=True)),
            Decimal('0.00')
        ),
    )
    
    dashboard['payments'] = {
        'total_payments': float(payment_totals['total']),
        'verified_payments': float(payment_totals['verified']),
    }
    
    # Budget summary
    budget_totals = budgets.aggregate(
        revenue_budget=Coalesce(Sum('total_revenue_budget'), Decimal('0.00')),
        expense_budget=Coalesce(Sum('total_expense_budget'), Decimal('0.00')),
        actual_revenue=Coalesce(Sum('actual_revenue_total'), Decimal('0.00')),
        actual_expense=Coalesce(Sum('actual_expense_total'), Decimal('0.00')),
    )
    
    dashboard['budget'] = {
        'revenue_budgeted': float(budget_totals['revenue_budget']),
        'expense_budgeted': float(budget_totals['expense_budget']),
        'actual_revenue': float(budget_totals['actual_revenue']),
        'actual_expense': float(budget_totals['actual_expense']),
        'revenue_variance': float(
            budget_totals['actual_revenue'] - budget_totals['revenue_budget']
        ),
        'expense_variance': float(
            budget_totals['actual_expense'] - budget_totals['expense_budget']
        ),
    }
    
    # Recent trends (last 30 days)
    thirty_days_ago = timezone.now().date() - timedelta(days=30)
    
    recent_expenses = expenses.filter(
        expense_date__gte=thirty_days_ago
    ).annotate(
        day=TruncDate('expense_date')
    ).values('day').annotate(
        count=Count('id'),
        total=Coalesce(Sum('total_amount'), Decimal('0.00')),
    ).order_by('day')
    
    dashboard['expense_trends'] = [
        {
            'date': item['day'].isoformat(),
            'count': item['count'],
            'total': float(item['total']),
        }
        for item in recent_expenses
    ]
    
    recent_payments = payments.filter(
        payment_date__gte=thirty_days_ago
    ).annotate(
        day=TruncDate('payment_date')
    ).values('day').annotate(
        count=Count('id'),
        total=Coalesce(Sum('amount'), Decimal('0.00')),
    ).order_by('day')
    
    dashboard['payment_trends'] = [
        {
            'date': item['day'].isoformat(),
            'count': item['count'],
            'total': float(item['total']),
        }
        for item in recent_payments
    ]
    
    return dashboard


# =============================================================================
# EXPENSE CATEGORY STATISTICS
# =============================================================================

def get_expense_category_statistics(filters=None):
    """
    Get expense category statistics
    
    Args:
        filters (dict): Optional filters
            - category_type: Filter by category type
            - is_active: Filter by active status
    
    Returns:
        dict: Expense category statistics
    """
    from .models import ExpenseCategory, Expense
    
    categories = ExpenseCategory.objects.all()
    
    if filters:
        if filters.get('category_type'):
            categories = categories.filter(category_type=filters['category_type'])
        if filters.get('is_active') is not None:
            categories = categories.filter(is_active=filters['is_active'])
    
    total_categories = categories.count()
    
    stats = {
        'total_categories': total_categories,
        'active_categories': categories.filter(is_active=True).count(),
        'inactive_categories': categories.filter(is_active=False).count(),
    }
    
    # By type
    type_stats = categories.values('category_type').annotate(
        count=Count('id')
    ).order_by('-count')
    
    stats['by_type'] = [
        {
            'type': item['category_type'],
            'count': item['count'],
        }
        for item in type_stats
    ]
    
    # Configuration flags
    stats['configuration'] = {
        'requiring_approval': categories.filter(requires_approval=True).count(),
        'with_approval_limit': categories.filter(
            approval_limit__isnull=False
        ).count(),
    }
    
    # Usage by category (from expenses)
    usage_stats = Expense.objects.values(
        'category__name',
        'category__category_type'
    ).annotate(
        total_amount=Coalesce(Sum('total_amount'), Decimal('0.00')),
        count=Count('id'),
    ).order_by('-total_amount')[:10]
    
    stats['top_used_categories'] = [
        {
            'category': item['category__name'],
            'type': item['category__category_type'],
            'total_spent': float(item['total_amount']),
            'expense_count': item['count'],
        }
        for item in usage_stats
    ]
    
    return stats