# fees/stats.py

"""
Comprehensive statistics utility functions for Fees models.
Provides detailed analytics for student accounts, invoices, payments, 
scholarships, discounts, fee structures, and financial performance.
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
# STUDENT ACCOUNT STATISTICS
# =============================================================================

def get_student_account_statistics(filters=None):
    """
    Get comprehensive student account statistics
    
    Args:
        filters (dict): Optional filters
            - status: Filter by account status
            - has_balance: Filter accounts with balances
            - academic_level: Filter by academic level ID
            - enrollment_status: Filter by student enrollment status
    
    Returns:
        dict: Student account statistics
    """
    from .models import StudentAccount, AccountTransaction
    from students.models import Student
    from django.db.models import Q, Count, Sum, Avg, Max, Min, Case, When, DecimalField
    from django.db.models.functions import Coalesce
    
    accounts = StudentAccount.objects.select_related('student')
    
    # Apply filters
    if filters:
        if filters.get('status'):
            accounts = accounts.filter(status=filters['status'])
        
        if filters.get('academic_level'):
            accounts = accounts.filter(
                student__current_academic_level_id=filters['academic_level']
            )
        
        if filters.get('enrollment_status'):
            accounts = accounts.filter(
                student__enrollment_status=filters['enrollment_status']
            )
    
    total_accounts = accounts.count()
    
    # Basic counts by status
    stats = {
        'total_accounts': total_accounts,
        'by_status': {
            'active': accounts.filter(status='ACTIVE').count(),
            'suspended': accounts.filter(status='SUSPENDED').count(),
            'frozen': accounts.filter(status='FROZEN').count(),
            'closed': accounts.filter(status='CLOSED').count(),
        },
    }
    
    # =========================================================================
    # CALCULATE FINANCIAL TOTALS FROM TRANSACTIONS (Not from stored fields)
    # =========================================================================
    
    # Get account IDs for filtering transactions
    account_ids = list(accounts.values_list('id', flat=True))
    
    # Calculate totals from AccountTransaction
    if account_ids:
        transaction_totals = AccountTransaction.objects.filter(
            student_account_id__in=account_ids
        ).aggregate(
            # Total charges (INVOICE + DEBIT) - stored as negative
            total_charges=Coalesce(
                Sum('amount', filter=Q(transaction_type__in=['INVOICE', 'DEBIT'])),
                Decimal('0.00')
            ),
            # Total payments - stored as positive
            total_payments=Coalesce(
                Sum('amount', filter=Q(transaction_type='PAYMENT')),
                Decimal('0.00')
            ),
            # Total discounts - stored as positive
            total_discounts=Coalesce(
                Sum('amount', filter=Q(transaction_type='DISCOUNT')),
                Decimal('0.00')
            ),
            # Total refunds - stored as negative
            total_refunds=Coalesce(
                Sum('amount', filter=Q(transaction_type='REFUND')),
                Decimal('0.00')
            ),
            # Net balance (sum of all transactions)
            total_balance=Coalesce(Sum('amount'), Decimal('0.00'))
        )
    else:
        transaction_totals = {
            'total_charges': Decimal('0.00'),
            'total_payments': Decimal('0.00'),
            'total_discounts': Decimal('0.00'),
            'total_refunds': Decimal('0.00'),
            'total_balance': Decimal('0.00'),
        }
    
    stats['balances'] = {
        'total_balance': float(transaction_totals['total_balance']),
        'total_fees_charged': float(abs(transaction_totals['total_charges'])),  # Make positive for display
        'total_payments_received': float(transaction_totals['total_payments']),
        'total_discounts_applied': float(transaction_totals['total_discounts']),
        'total_refunds_issued': float(abs(transaction_totals['total_refunds'])),  # Make positive for display
    }
    
    # =========================================================================
    # DEBT ANALYSIS - Calculate per-account balances
    # =========================================================================
    
    # Annotate each account with its calculated balance
    accounts_with_balance = accounts.annotate(
        calculated_balance=Coalesce(
            Sum('transactions__amount'),
            Decimal('0.00')
        )
    )
    
    # Apply balance filter if provided
    if filters and filters.get('has_balance') is not None:
        if filters['has_balance']:
            accounts_with_balance = accounts_with_balance.exclude(calculated_balance=0)
        else:
            accounts_with_balance = accounts_with_balance.filter(calculated_balance=0)
    
    # Separate into debtors, credit accounts, and zero balance
    debtors = accounts_with_balance.filter(calculated_balance__lt=0)
    credit_accounts = accounts_with_balance.filter(calculated_balance__gt=0)
    zero_balance = accounts_with_balance.filter(calculated_balance=0)
    
    # Calculate debt statistics
    debt_totals = debtors.aggregate(
        total_debt=Coalesce(Sum('calculated_balance'), Decimal('0.00')),
        avg_debt=Coalesce(Avg('calculated_balance'), Decimal('0.00')),
        max_debt=Coalesce(Min('calculated_balance'), Decimal('0.00'))  # Min because negative
    )
    
    credit_totals = credit_accounts.aggregate(
        total_credit=Coalesce(Sum('calculated_balance'), Decimal('0.00')),
        avg_credit=Coalesce(Avg('calculated_balance'), Decimal('0.00'))
    )
    
    stats['debt_analysis'] = {
        'total_debtors': debtors.count(),
        'total_outstanding': float(abs(debt_totals['total_debt'])),  # Make positive
        'average_debt': float(abs(debt_totals['avg_debt'])),  # Make positive
        'largest_debt': float(abs(debt_totals['max_debt'])),  # Make positive
        'accounts_with_credit': credit_accounts.count(),
        'total_credit': float(credit_totals['total_credit']),
        'average_credit': float(credit_totals['avg_credit']) if credit_accounts.exists() else 0,
        'zero_balance_accounts': zero_balance.count(),
    }
    
    # =========================================================================
    # COLLECTION RATE
    # =========================================================================
    
    total_charged = abs(transaction_totals['total_charges'])
    total_paid = transaction_totals['total_payments']
    
    if total_charged > 0:
        collection_rate = (total_paid / total_charged * 100)
        stats['collection_rate'] = round(float(collection_rate), 2)
    else:
        stats['collection_rate'] = 0
    
    # =========================================================================
    # TOP DEBTORS (accounts with most negative balance)
    # =========================================================================
    
    top_debtors = debtors.select_related('student').order_by('calculated_balance')[:10]
    
    stats['top_debtors'] = []
    for acc in top_debtors:
        # Calculate individual totals for this account
        account_totals = AccountTransaction.objects.filter(
            student_account=acc
        ).aggregate(
            charged=Coalesce(
                Sum('amount', filter=Q(transaction_type__in=['INVOICE', 'DEBIT'])),
                Decimal('0.00')
            ),
            paid=Coalesce(
                Sum('amount', filter=Q(transaction_type='PAYMENT')),
                Decimal('0.00')
            )
        )
        
        stats['top_debtors'].append({
            'student_id': str(acc.student.id),
            'student_name': acc.student.get_full_name(),
            'admission_number': acc.student.admission_number,
            'outstanding': float(abs(acc.calculated_balance)),
            'total_charged': float(abs(account_totals['charged'])),
            'total_paid': float(account_totals['paid']),
        })
    
    # =========================================================================
    # CREDIT LIMIT USAGE
    # =========================================================================
    
    accounts_with_limit = accounts_with_balance.filter(credit_limit__gt=0)
    
    if accounts_with_limit.exists():
        limit_totals = accounts_with_limit.aggregate(
            total_limit=Coalesce(Sum('credit_limit'), Decimal('0.00')),
            avg_limit=Coalesce(Avg('credit_limit'), Decimal('0.00'))
        )
        
        # Count accounts over limit (negative balance exceeds credit limit)
        over_limit_count = 0
        for acc in accounts_with_limit:
            if acc.calculated_balance < 0 and abs(acc.calculated_balance) > acc.credit_limit:
                over_limit_count += 1
        
        stats['credit_limits'] = {
            'accounts_with_limit': accounts_with_limit.count(),
            'total_limit_allocated': float(limit_totals['total_limit']),
            'average_limit': float(limit_totals['avg_limit']),
            'accounts_over_limit': over_limit_count,
        }
    else:
        stats['credit_limits'] = {
            'accounts_with_limit': 0,
            'total_limit_allocated': 0,
            'average_limit': 0,
            'accounts_over_limit': 0,
        }
    
    # =========================================================================
    # ACTIVITY TRACKING
    # =========================================================================
    
    now = timezone.now()
    
    stats['activity'] = {
        'transactions_last_7_days': accounts.filter(
            last_transaction_date__gte=now - timedelta(days=7)
        ).count(),
        'transactions_last_30_days': accounts.filter(
            last_transaction_date__gte=now - timedelta(days=30)
        ).count(),
        'payments_last_7_days': accounts.filter(
            last_payment_date__gte=now - timedelta(days=7)
        ).count(),
        'payments_last_30_days': accounts.filter(
            last_payment_date__gte=now - timedelta(days=30)
        ).count(),
        'dormant_accounts': accounts.filter(
            Q(last_transaction_date__lt=now - timedelta(days=90)) |
            Q(last_transaction_date__isnull=True)
        ).count(),
    }
    
    # =========================================================================
    # TRANSACTION VOLUME STATISTICS
    # =========================================================================
    
    if account_ids:
        transaction_counts = AccountTransaction.objects.filter(
            student_account_id__in=account_ids
        ).aggregate(
            total_transactions=Count('id'),
            invoices=Count('id', filter=Q(transaction_type='INVOICE')),
            payments=Count('id', filter=Q(transaction_type='PAYMENT')),
            discounts=Count('id', filter=Q(transaction_type='DISCOUNT')),
            refunds=Count('id', filter=Q(transaction_type='REFUND')),
        )
        
        stats['transaction_volume'] = {
            'total_transactions': transaction_counts['total_transactions'],
            'total_invoices': transaction_counts['invoices'],
            'total_payments': transaction_counts['payments'],
            'total_discounts': transaction_counts['discounts'],
            'total_refunds': transaction_counts['refunds'],
        }
    else:
        stats['transaction_volume'] = {
            'total_transactions': 0,
            'total_invoices': 0,
            'total_payments': 0,
            'total_discounts': 0,
            'total_refunds': 0,
        }
    
    # =========================================================================
    # AVERAGE STATISTICS
    # =========================================================================
    
    if total_accounts > 0:
        stats['averages'] = {
            'avg_balance_per_account': float(transaction_totals['total_balance'] / total_accounts),
            'avg_charged_per_account': float(abs(transaction_totals['total_charges']) / total_accounts),
            'avg_paid_per_account': float(transaction_totals['total_payments'] / total_accounts),
        }
    else:
        stats['averages'] = {
            'avg_balance_per_account': 0,
            'avg_charged_per_account': 0,
            'avg_paid_per_account': 0,
        }
    
    return stats

# =============================================================================
# ACCOUNT TRANSACTION STATISTICS
# =============================================================================

def get_account_transaction_statistics(filters=None):
    """
    Get comprehensive account transaction statistics
    
    Args:
        filters (dict): Optional filters
            - transaction_type: Filter by transaction type
            - academic_session: Filter by session ID
            - fiscal_period: Filter by fiscal period ID
            - date_from: Start date filter
            - date_to: End date filter
            - student_account: Filter by student account ID
    
    Returns:
        dict: Account transaction statistics
    """
    from .models import AccountTransaction
    
    transactions = AccountTransaction.objects.select_related(
        'student_account', 'student_account__student',
        'academic_session', 'fiscal_period'
    )
    
    # Apply filters
    if filters:
        if filters.get('transaction_type'):
            transactions = transactions.filter(
                transaction_type=filters['transaction_type']
            )
        
        if filters.get('academic_session'):
            transactions = transactions.filter(
                academic_session_id=filters['academic_session']
            )
        
        if filters.get('fiscal_period'):
            transactions = transactions.filter(
                fiscal_period_id=filters['fiscal_period']
            )
        
        if filters.get('date_from'):
            transactions = transactions.filter(
                created_at__gte=filters['date_from']
            )
        
        if filters.get('date_to'):
            transactions = transactions.filter(
                created_at__lte=filters['date_to']
            )
        
        if filters.get('student_account'):
            transactions = transactions.filter(
                student_account_id=filters['student_account']
            )
    
    total_transactions = transactions.count()
    
    stats = {
        'total_transactions': total_transactions,
    }
    
    # Transaction type breakdown
    type_stats = transactions.values('transaction_type').annotate(
        count=Count('id'),
        total_amount=Coalesce(Sum('amount'), Decimal('0.00')),
        avg_amount=Coalesce(Avg('amount'), Decimal('0.00')),
    ).order_by('-count')
    
    stats['by_type'] = {
        item['transaction_type']: {
            'count': item['count'],
            'total_amount': float(item['total_amount']),
            'average_amount': float(item['avg_amount']),
            'percentage': round(
                (item['count'] / total_transactions * 100) 
                if total_transactions > 0 else 0,
                2
            ),
        }
        for item in type_stats
    }
    
    # Financial totals
    financial_totals = transactions.aggregate(
        total_debits=Coalesce(
            Sum('amount', filter=Q(transaction_type__in=['DEBIT', 'INVOICE'])),
            Decimal('0.00')
        ),
        total_credits=Coalesce(
            Sum('amount', filter=Q(transaction_type__in=['CREDIT', 'PAYMENT'])),
            Decimal('0.00')
        ),
        total_adjustments=Coalesce(
            Sum('amount', filter=Q(transaction_type='ADJUSTMENT')),
            Decimal('0.00')
        ),
        total_refunds=Coalesce(
            Sum('amount', filter=Q(transaction_type='REFUND')),
            Decimal('0.00')
        ),
        total_discounts=Coalesce(
            Sum('amount', filter=Q(transaction_type='DISCOUNT')),
            Decimal('0.00')
        ),
    )
    
    stats['financial_totals'] = {
        'total_debits': float(financial_totals['total_debits']),
        'total_credits': float(financial_totals['total_credits']),
        'total_adjustments': float(financial_totals['total_adjustments']),
        'total_refunds': float(financial_totals['total_refunds']),
        'total_discounts': float(financial_totals['total_discounts']),
        'net_amount': float(
            financial_totals['total_credits'] - financial_totals['total_debits']
        ),
    }
    
    # Time-based analysis
    if transactions.exists():
        # Daily transactions (last 30 days)
        thirty_days_ago = timezone.now() - timedelta(days=30)
        daily_transactions = transactions.filter(
            created_at__gte=thirty_days_ago
        ).annotate(
            day=TruncDate('created_at')
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
            for item in daily_transactions
        ]
    
    # Session breakdown
    session_stats = transactions.filter(
        academic_session__isnull=False
    ).values(
        'academic_session__year_name',
        'academic_session__term_name'
    ).annotate(
        count=Count('id'),
        total_amount=Coalesce(Sum('amount'), Decimal('0.00')),
    ).order_by('-count')[:10]
    
    stats['by_session'] = [
        {
            'session': f"{item['academic_session__year_name']} - {item['academic_session__term_name']}" 
                       if item['academic_session__year_name'] else 'Unknown',
            'count': item['count'],
            'total_amount': float(item['total_amount']),
        }
        for item in session_stats
    ]
    
    # Most active accounts
    active_accounts = transactions.values(
        'student_account__student__first_name',
        'student_account__student__last_name',
        'student_account__student__admission_number'
    ).annotate(
        transaction_count=Count('id'),
        total_amount=Coalesce(Sum('amount'), Decimal('0.00')),
    ).order_by('-transaction_count')[:10]
    
    stats['most_active_accounts'] = [
        {
            'student_name': f"{item['student_account__student__first_name']} {item['student_account__student__last_name']}",
            'admission_number': item['student_account__student__admission_number'],
            'transaction_count': item['transaction_count'],
            'total_amount': float(item['total_amount']),
        }
        for item in active_accounts
    ]
    
    # Recent activity
    now = timezone.now()
    stats['recent_activity'] = {
        'last_24_hours': transactions.filter(
            created_at__gte=now - timedelta(hours=24)
        ).count(),
        'last_7_days': transactions.filter(
            created_at__gte=now - timedelta(days=7)
        ).count(),
        'last_30_days': transactions.filter(
            created_at__gte=now - timedelta(days=30)
        ).count(),
    }
    
    return stats


# =============================================================================
# FEE STRUCTURE STATISTICS
# =============================================================================

def get_fee_structure_statistics(filters=None):
    """
    Get comprehensive fee structure statistics
    
    Args:
        filters (dict): Optional filters
            - structure_type: Filter by structure type
            - boarding_type_filter: Filter by boarding type
            - student_type_filter: Filter by student type
            - is_active: Filter by active status
            - academic_session: Filter by applicable session ID
            - academic_level: Filter by applicable level ID
            - has_expired: Filter expired structures
    
    Returns:
        dict: Fee structure statistics
    """
    from .models import FeesStructure, FeesStructureItem, FeeInvoice
    from core.utils import get_school_today
    
    structures = FeesStructure.objects.prefetch_related(
        'academic_levels',
        'applicable_classes',
        'applicable_sessions',
        'items',
        'items__fee_category'
    )
    
    today = get_school_today()
    
    # Apply filters
    if filters:
        if filters.get('structure_type'):
            structures = structures.filter(
                structure_type=filters['structure_type']
            )
        
        if filters.get('boarding_type_filter'):
            structures = structures.filter(
                boarding_type_filter=filters['boarding_type_filter']
            )
        
        if filters.get('student_type_filter'):
            structures = structures.filter(
                student_type_filter=filters['student_type_filter']
            )
        
        if filters.get('is_active') is not None:
            structures = structures.filter(is_active=filters['is_active'])
        
        if filters.get('academic_session'):
            structures = structures.filter(
                applicable_sessions__id=filters['academic_session']
            )
        
        if filters.get('academic_level'):
            structures = structures.filter(
                academic_levels__id=filters['academic_level']
            )
        
        if filters.get('has_expired'):
            structures = structures.filter(
                expiry_date__lt=today
            )
    
    total_structures = structures.count()
    
    stats = {
        'total_structures': total_structures,
        'active_structures': structures.filter(is_active=True).count(),
        'inactive_structures': structures.filter(is_active=False).count(),
    }
    
    # Status breakdown
    stats['status_breakdown'] = {
        'active': structures.filter(
            is_active=True,
            effective_date__lte=today,
        ).filter(
            Q(expiry_date__isnull=True) | Q(expiry_date__gte=today)
        ).count(),
        'not_yet_effective': structures.filter(
            is_active=True,
            effective_date__gt=today
        ).count(),
        'expired': structures.filter(
            expiry_date__lt=today
        ).count(),
        'inactive': structures.filter(is_active=False).count(),
    }
    
    # Structure type breakdown
    type_stats = structures.values('structure_type').annotate(
        count=Count('id'),
        active_count=Count('id', filter=Q(is_active=True)),
    ).order_by('-count')
    
    stats['by_type'] = [
        {
            'type': item['structure_type'],
            'total_count': item['count'],
            'active_count': item['active_count'],
            'inactive_count': item['count'] - item['active_count'],
        }
        for item in type_stats
    ]
    
    # Boarding type distribution
    boarding_stats = structures.values('boarding_type_filter').annotate(
        count=Count('id')
    ).order_by('-count')
    
    stats['by_boarding_type'] = [
        {
            'boarding_type': item['boarding_type_filter'],
            'count': item['count'],
            'percentage': round(
                (item['count'] / total_structures * 100) 
                if total_structures > 0 else 0,
                2
            ),
        }
        for item in boarding_stats
    ]
    
    # Student type distribution
    student_type_stats = structures.values('student_type_filter').annotate(
        count=Count('id')
    ).order_by('-count')
    
    stats['by_student_type'] = [
        {
            'student_type': item['student_type_filter'],
            'count': item['count'],
        }
        for item in student_type_stats
    ]
    
    # Financial analysis (from structure items)
    structure_items = FeesStructureItem.objects.filter(
        fee_structure__in=structures
    )
    
    financial_stats = structure_items.aggregate(
        total_items=Count('id'),
        total_amount=Coalesce(Sum('amount'), Decimal('0.00')),
        avg_amount=Coalesce(Avg('amount'), Decimal('0.00')),
        max_amount=Coalesce(Max('amount'), Decimal('0.00')),
        min_amount=Coalesce(Min('amount'), Decimal('0.00')),
        total_tax=Coalesce(Sum(
            F('amount') * F('tax_percentage') / 100
        ), Decimal('0.00')),
        total_discount=Coalesce(Sum(
            F('amount') * F('discount_percentage') / 100
        ), Decimal('0.00')),
    )
    
    stats['financial_summary'] = {
        'total_items_across_structures': financial_stats['total_items'],
        'total_fee_amount': float(financial_stats['total_amount']),
        'average_item_amount': float(financial_stats['avg_amount']),
        'max_item_amount': float(financial_stats['max_amount']),
        'min_item_amount': float(financial_stats['min_amount']),
        'total_tax_amount': float(financial_stats['total_tax']),
        'total_discount_amount': float(financial_stats['total_discount']),
    }
    
    # Items per structure analysis
    items_per_structure = structures.annotate(
        item_count=Count('items'),
        total_fees=Coalesce(Sum('items__amount'), Decimal('0.00')),
    ).aggregate(
        avg_items=Coalesce(Avg('item_count'), Decimal('0.00')),
        max_items=Coalesce(Max('item_count'), 0),
        min_items=Coalesce(Min('item_count'), 0),
        avg_total_fees=Coalesce(Avg('total_fees'), Decimal('0.00')),
        max_total_fees=Coalesce(Max('total_fees'), Decimal('0.00')),
        min_total_fees=Coalesce(Min('total_fees'), Decimal('0.00')),
    )
    
    stats['structure_complexity'] = {
        'avg_items_per_structure': float(items_per_structure['avg_items']),
        'max_items_in_structure': items_per_structure['max_items'],
        'min_items_in_structure': items_per_structure['min_items'],
        'avg_total_fees': float(items_per_structure['avg_total_fees']),
        'max_total_fees': float(items_per_structure['max_total_fees']),
        'min_total_fees': float(items_per_structure['min_total_fees']),
    }
    
    # Top structures by total fees
    top_structures = structures.annotate(
        total_fees=Coalesce(Sum('items__amount'), Decimal('0.00')),
        item_count=Count('items'),
    ).order_by('-total_fees')[:10]
    
    stats['top_structures_by_fees'] = [
        {
            'structure_id': str(structure.id),
            'name': structure.name,
            'type': structure.structure_type,
            'boarding_type': structure.boarding_type_filter,
            'total_fees': float(structure.total_fees),
            'item_count': structure.item_count,
            'is_active': structure.is_active,
        }
        for structure in top_structures
    ]
    
    # Usage statistics (from invoices)
    usage_stats = structures.annotate(
        invoice_count=Count('invoices'),
        total_billed=Coalesce(Sum('invoices__total_amount'), Decimal('0.00')),
        total_paid=Coalesce(Sum('invoices__paid_amount'), Decimal('0.00')),
    ).aggregate(
        structures_with_invoices=Count('id', filter=Q(invoice_count__gt=0)),
        total_invoices=Coalesce(Sum('invoice_count'), 0),
        total_billed=Coalesce(Sum('total_billed'), Decimal('0.00')),
        total_paid=Coalesce(Sum('total_paid'), Decimal('0.00')),
        avg_invoices_per_structure=Coalesce(Avg('invoice_count'), Decimal('0.00')),
    )
    
    stats['usage_statistics'] = {
        'structures_with_invoices': usage_stats['structures_with_invoices'],
        'structures_without_invoices': total_structures - usage_stats['structures_with_invoices'],
        'total_invoices_generated': usage_stats['total_invoices'],
        'total_amount_billed': float(usage_stats['total_billed']),
        'total_amount_collected': float(usage_stats['total_paid']),
        'avg_invoices_per_structure': float(usage_stats['avg_invoices_per_structure']),
        'collection_rate': round(
            (usage_stats['total_paid'] / usage_stats['total_billed'] * 100)
            if usage_stats['total_billed'] > 0 else 0,
            2
        ),
    }
    
    # Most used structures
    most_used = structures.annotate(
        invoice_count=Count('invoices')
    ).filter(
        invoice_count__gt=0
    ).order_by('-invoice_count')[:10]
    
    stats['most_used_structures'] = [
        {
            'structure_id': str(structure.id),
            'name': structure.name,
            'type': structure.structure_type,
            'invoice_count': structure.invoice_count,
            'is_active': structure.is_active,
        }
        for structure in most_used
    ]
    
    # Priority distribution
    priority_stats = structures.values('priority').annotate(
        count=Count('id')
    ).order_by('priority')[:10]
    
    stats['priority_distribution'] = [
        {
            'priority': item['priority'],
            'count': item['count'],
        }
        for item in priority_stats
    ]
    
    # Late fee configuration
    with_late_fees = structures.filter(charges_late_fee=True)
    late_fee_stats = with_late_fees.aggregate(
        count=Count('id'),
        avg_late_fee_amount=Coalesce(Avg('late_fee_amount'), Decimal('0.00')),
        avg_late_fee_percentage=Coalesce(Avg('late_fee_percentage'), Decimal('0.00')),
        avg_grace_period=Coalesce(Avg('grace_period_days'), Decimal('0.00')),
    )
    
    stats['late_fee_configuration'] = {
        'structures_with_late_fees': late_fee_stats['count'],
        'structures_without_late_fees': total_structures - late_fee_stats['count'],
        'avg_late_fee_amount': float(late_fee_stats['avg_late_fee_amount']),
        'avg_late_fee_percentage': float(late_fee_stats['avg_late_fee_percentage']),
        'avg_grace_period_days': float(late_fee_stats['avg_grace_period']),
    }
    
    # Session coverage
    session_coverage = structures.prefetch_related('applicable_sessions').annotate(
        session_count=Count('applicable_sessions')
    ).aggregate(
        avg_sessions=Coalesce(Avg('session_count'), Decimal('0.00')),
        max_sessions=Coalesce(Max('session_count'), 0),
        structures_with_no_sessions=Count('id', filter=Q(session_count=0)),
    )
    
    stats['session_coverage'] = {
        'avg_sessions_per_structure': float(session_coverage['avg_sessions']),
        'max_sessions_covered': session_coverage['max_sessions'],
        'structures_with_no_sessions': session_coverage['structures_with_no_sessions'],
    }
    
    # Academic level coverage
    level_coverage = structures.prefetch_related('academic_levels').annotate(
        level_count=Count('academic_levels')
    ).aggregate(
        avg_levels=Coalesce(Avg('level_count'), Decimal('0.00')),
        max_levels=Coalesce(Max('level_count'), 0),
        structures_with_no_levels=Count('id', filter=Q(level_count=0)),
    )
    
    stats['level_coverage'] = {
        'avg_levels_per_structure': float(level_coverage['avg_levels']),
        'max_levels_covered': level_coverage['max_levels'],
        'structures_with_no_levels': level_coverage['structures_with_no_levels'],
    }
    
    # Scholarship eligibility in structure items
    scholarship_eligible_items = structure_items.filter(
        scholarship_eligible=True
    ).count()
    
    stats['scholarship_configuration'] = {
        'total_items': financial_stats['total_items'],
        'scholarship_eligible_items': scholarship_eligible_items,
        'non_eligible_items': financial_stats['total_items'] - scholarship_eligible_items,
        'eligibility_rate': round(
            (scholarship_eligible_items / financial_stats['total_items'] * 100)
            if financial_stats['total_items'] > 0 else 0,
            2
        ),
    }
    
    # Conditional items
    conditional_items = structure_items.filter(is_conditional=True).count()
    
    stats['conditional_items'] = {
        'total_conditional_items': conditional_items,
        'unconditional_items': financial_stats['total_items'] - conditional_items,
        'conditional_rate': round(
            (conditional_items / financial_stats['total_items'] * 100)
            if financial_stats['total_items'] > 0 else 0,
            2
        ),
    }
    
    # Installment configuration
    installment_items = structure_items.filter(
        is_payable_in_installments=True
    )
    installment_stats = installment_items.aggregate(
        count=Count('id'),
        avg_installments=Coalesce(Avg('number_of_installments'), Decimal('0.00')),
        max_installments=Coalesce(Max('number_of_installments'), 0),
    )
    
    stats['installment_configuration'] = {
        'items_with_installments': installment_stats['count'],
        'avg_installment_count': float(installment_stats['avg_installments']),
        'max_installments': installment_stats['max_installments'],
    }
    
    return stats


# =============================================================================
# FEE INVOICE STATISTICS
# =============================================================================

def get_invoice_statistics(filters=None):
    """
    Get comprehensive invoice statistics
    
    Args:
        filters (dict): Optional filters
            - status: Filter by invoice status
            - academic_session: Filter by session ID
            - fiscal_period: Filter by fiscal period ID
            - date_from: Start date for issue_date filter
            - date_to: End date for issue_date filter
            - is_overdue: Filter overdue invoices
    
    Returns:
        dict: Invoice statistics
    """
    from .models import FeeInvoice
    
    invoices = FeeInvoice.objects.select_related(
        'student', 'academic_session', 'fiscal_period', 'fee_structure'
    )
    
    # Apply filters
    if filters:
        if filters.get('status'):
            invoices = invoices.filter(status=filters['status'])
        
        if filters.get('academic_session'):
            invoices = invoices.filter(academic_session_id=filters['academic_session'])
        
        if filters.get('fiscal_period'):
            invoices = invoices.filter(fiscal_period_id=filters['fiscal_period'])
        
        if filters.get('date_from'):
            invoices = invoices.filter(issue_date__gte=filters['date_from'])
        
        if filters.get('date_to'):
            invoices = invoices.filter(issue_date__lte=filters['date_to'])
        
        if filters.get('is_overdue'):
            from core.utils import get_school_today
            today = get_school_today()
            invoices = invoices.filter(
                due_date__lt=today,
                status__in=['PENDING', 'PARTIALLY_PAID', 'OVERDUE']
            )
    
    total_invoices = invoices.count()
    
    # Status breakdown
    stats = {
        'total_invoices': total_invoices,
        'by_status': {},
    }
    
    status_breakdown = invoices.values('status').annotate(
        count=Count('id'),
        total_amount=Coalesce(Sum('total_amount'), Decimal('0.00')),
        total_balance=Coalesce(Sum('balance'), Decimal('0.00')),
    ).order_by('-count')
    
    for item in status_breakdown:
        stats['by_status'][item['status']] = {
            'count': item['count'],
            'total_amount': float(item['total_amount']),
            'total_balance': float(item['total_balance']),
        }
    
    # Financial totals
    financial_totals = invoices.aggregate(
        total_amount=Coalesce(Sum('total_amount'), Decimal('0.00')),
        subtotal=Coalesce(Sum('subtotal_amount'), Decimal('0.00')),
        total_discounts=Coalesce(Sum('discount_amount'), Decimal('0.00')),
        total_scholarship_discounts=Coalesce(
            Sum('scholarship_discount_amount'), Decimal('0.00')
        ),
        total_tax=Coalesce(Sum('tax_amount'), Decimal('0.00')),
        total_paid=Coalesce(Sum('paid_amount'), Decimal('0.00')),
        total_balance=Coalesce(Sum('balance'), Decimal('0.00')),
        total_late_fees=Coalesce(Sum('late_fee_amount'), Decimal('0.00')),
        avg_invoice_amount=Coalesce(Avg('total_amount'), Decimal('0.00')),
    )
    
    stats['financial_totals'] = {
        'total_billed': float(financial_totals['total_amount']),
        'subtotal': float(financial_totals['subtotal']),
        'total_discounts': float(financial_totals['total_discounts']),
        'total_scholarship_discounts': float(
            financial_totals['total_scholarship_discounts']
        ),
        'total_tax': float(financial_totals['total_tax']),
        'total_paid': float(financial_totals['total_paid']),
        'total_outstanding': float(financial_totals['total_balance']),
        'total_late_fees': float(financial_totals['total_late_fees']),
        'average_invoice': float(financial_totals['avg_invoice_amount']),
    }
    
    # Payment progress
    if financial_totals['total_amount'] > 0:
        payment_rate = (
            financial_totals['total_paid'] / 
            financial_totals['total_amount'] * 100
        )
        stats['payment_rate'] = round(float(payment_rate), 2)
    else:
        stats['payment_rate'] = 0
    
    # Overdue analysis
    from core.utils import get_school_today
    today = get_school_today()
    overdue_invoices = invoices.filter(
        due_date__lt=today,
        status__in=['PENDING', 'PARTIALLY_PAID', 'OVERDUE']
    )
    
    overdue_stats = overdue_invoices.aggregate(
        count=Count('id'),
        total_overdue=Coalesce(Sum('balance'), Decimal('0.00')),
    )
    
    stats['overdue'] = {
        'count': overdue_stats['count'],
        'total_amount': float(overdue_stats['total_overdue']),
        'percentage_of_total': round(
            (overdue_stats['count'] / total_invoices * 100) 
            if total_invoices > 0 else 0, 
            2
        ),
    }
    
    # Aging analysis
    aging_ranges = [
        ('current', Q(due_date__gte=today)),
        ('1_30_days', Q(due_date__lt=today, due_date__gte=today - timedelta(days=30))),
        ('31_60_days', Q(
            due_date__lt=today - timedelta(days=30),
            due_date__gte=today - timedelta(days=60)
        )),
        ('61_90_days', Q(
            due_date__lt=today - timedelta(days=60),
            due_date__gte=today - timedelta(days=90)
        )),
        ('over_90_days', Q(due_date__lt=today - timedelta(days=90))),
    ]
    
    stats['aging'] = {}
    for label, condition in aging_ranges:
        aging_data = invoices.filter(
            condition,
            status__in=['PENDING', 'PARTIALLY_PAID', 'OVERDUE']
        ).aggregate(
            count=Count('id'),
            total=Coalesce(Sum('balance'), Decimal('0.00')),
        )
        stats['aging'][label] = {
            'count': aging_data['count'],
            'total': float(aging_data['total']),
        }
    
    # Scholarship and discount usage
    with_scholarships = invoices.filter(has_scholarships_applied=True)
    with_discounts = invoices.filter(has_discounts_applied=True)
    
    stats['discounts_and_scholarships'] = {
        'invoices_with_scholarships': with_scholarships.count(),
        'invoices_with_discounts': with_discounts.count(),
        'total_scholarship_value': float(
            with_scholarships.aggregate(
                total=Coalesce(Sum('scholarship_discount_amount'), Decimal('0.00'))
            )['total']
        ),
        'total_discount_value': float(
            with_discounts.aggregate(
                total=Coalesce(Sum('discount_amount'), Decimal('0.00'))
            )['total']
        ),
    }
    
    # Session breakdown
    session_stats = invoices.values(
        'academic_session__year_name',
        'academic_session__term_name'
    ).annotate(
        count=Count('id'),
        total_amount=Coalesce(Sum('total_amount'), Decimal('0.00')),
        total_paid=Coalesce(Sum('paid_amount'), Decimal('0.00')),
        total_balance=Coalesce(Sum('balance'), Decimal('0.00')),
    ).order_by('-count')[:10]
    
    stats['by_session'] = [
        {
            'session': f"{item['academic_session__year_name']} - {item['academic_session__term_name']}",
            'count': item['count'],
            'total_amount': float(item['total_amount']),
            'total_paid': float(item['total_paid']),
            'balance': float(item['total_balance']),
        }
        for item in session_stats
    ]
    
    # Fee structure breakdown
    structure_stats = invoices.values(
        'fee_structure__name',
        'fee_structure__structure_type'
    ).annotate(
        count=Count('id'),
        total_amount=Coalesce(Sum('total_amount'), Decimal('0.00')),
    ).order_by('-total_amount')[:10]
    
    stats['by_fee_structure'] = [
        {
            'structure': item['fee_structure__name'],
            'type': item['fee_structure__structure_type'],
            'count': item['count'],
            'total_amount': float(item['total_amount']),
        }
        for item in structure_stats
    ]
    
    # Recent activity
    now = timezone.now()
    stats['recent_activity'] = {
        'created_last_7_days': invoices.filter(
            created_at__gte=now - timedelta(days=7)
        ).count(),
        'created_last_30_days': invoices.filter(
            created_at__gte=now - timedelta(days=30)
        ).count(),
        'paid_last_7_days': invoices.filter(
            status='PAID',
            updated_at__gte=now - timedelta(days=7)
        ).count(),
        'paid_last_30_days': invoices.filter(
            status='PAID',
            updated_at__gte=now - timedelta(days=30)
        ).count(),
    }
    
    return stats


# =============================================================================
# PAYMENT STATISTICS
# =============================================================================

def get_payment_statistics(filters=None):
    """
    Get comprehensive payment statistics
    
    Args:
        filters (dict): Optional filters
            - status: Filter by payment status
            - payment_method: Filter by payment method ID
            - academic_session: Filter by session ID
            - fiscal_period: Filter by fiscal period ID
            - date_from: Start date filter
            - date_to: End date filter
            - is_verified: Filter by verification status
    
    Returns:
        dict: Payment statistics
    """
    from .models import Payment
    
    payments = Payment.objects.select_related(
        'student', 'invoice', 'payment_method', 
        'academic_session', 'fiscal_period'
    )
    
    # Apply filters
    if filters:
        if filters.get('status'):
            payments = payments.filter(status=filters['status'])
        
        if filters.get('payment_method'):
            payments = payments.filter(payment_method_id=filters['payment_method'])
        
        if filters.get('academic_session'):
            payments = payments.filter(academic_session_id=filters['academic_session'])
        
        if filters.get('fiscal_period'):
            payments = payments.filter(fiscal_period_id=filters['fiscal_period'])
        
        if filters.get('date_from'):
            payments = payments.filter(payment_date__gte=filters['date_from'])
        
        if filters.get('date_to'):
            payments = payments.filter(payment_date__lte=filters['date_to'])
        
        if filters.get('is_verified') is not None:
            payments = payments.filter(is_verified=filters['is_verified'])
    
    total_payments = payments.count()
    
    # Status breakdown
    stats = {
        'total_payments': total_payments,
        'by_status': {},
    }
    
    status_breakdown = payments.values('status').annotate(
        count=Count('id'),
        total_amount=Coalesce(Sum('amount'), Decimal('0.00')),
    ).order_by('-count')
    
    for item in status_breakdown:
        stats['by_status'][item['status']] = {
            'count': item['count'],
            'total_amount': float(item['total_amount']),
        }
    
    # Financial totals
    financial_totals = payments.aggregate(
        total_amount=Coalesce(Sum('amount'), Decimal('0.00')),
        total_applied=Coalesce(Sum('amount_applied_to_invoice'), Decimal('0.00')),
        total_overpayment=Coalesce(Sum('overpayment_amount'), Decimal('0.00')),
        avg_payment=Coalesce(Avg('amount'), Decimal('0.00')),
        max_payment=Coalesce(Max('amount'), Decimal('0.00')),
        min_payment=Coalesce(Min('amount'), Decimal('0.00')),
    )
    
    stats['financial_totals'] = {
        'total_received': float(financial_totals['total_amount']),
        'total_applied_to_invoices': float(financial_totals['total_applied']),
        'total_overpayments': float(financial_totals['total_overpayment']),
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
        avg_amount=Coalesce(Avg('amount'), Decimal('0.00')),
    ).order_by('-total_amount')
    
    stats['by_payment_method'] = [
        {
            'method': item['payment_method__name'],
            'type': item['payment_method__method_type'],
            'count': item['count'],
            'total_amount': float(item['total_amount']),
            'average_amount': float(item['avg_amount']),
            'percentage': round(
                (item['count'] / total_payments * 100) if total_payments > 0 else 0,
                2
            ),
        }
        for item in method_stats
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
    
    # Receipt status
    with_receipt = payments.filter(receipt_issued=True)
    without_receipt = payments.filter(receipt_issued=False)
    
    stats['receipts'] = {
        'issued': with_receipt.count(),
        'pending': without_receipt.count(),
        'issue_rate': round(
            (with_receipt.count() / total_payments * 100) if total_payments > 0 else 0,
            2
        ),
    }
    
    # Time-based analysis
    if payments.exists():
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
    
    # Session breakdown
    session_stats = payments.values(
        'academic_session__year_name',
        'academic_session__term_name'
    ).annotate(
        count=Count('id'),
        total_amount=Coalesce(Sum('amount'), Decimal('0.00')),
    ).order_by('-total_amount')[:10]
    
    stats['by_session'] = [
        {
            'session': f"{item['academic_session__year_name']} - {item['academic_session__term_name']}" 
                       if item['academic_session__year_name'] else 'Unknown',
            'count': item['count'],
            'total_amount': float(item['total_amount']),
        }
        for item in session_stats
    ]
    
    # Top payers
    top_payers = payments.values(
        'student__id',
        'student__first_name',
        'student__last_name',
        'student__admission_number'
    ).annotate(
        payment_count=Count('id'),
        total_paid=Coalesce(Sum('amount'), Decimal('0.00')),
    ).order_by('-total_paid')[:10]
    
    stats['top_payers'] = [
        {
            'student_id': str(item['student__id']),
            'student_name': f"{item['student__first_name']} {item['student__last_name']}",
            'admission_number': item['student__admission_number'],
            'payment_count': item['payment_count'],
            'total_paid': float(item['total_paid']),
        }
        for item in top_payers
    ]
    
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
        'amount_last_24_hours': float(
            payments.filter(
                created_at__gte=now - timedelta(hours=24)
            ).aggregate(total=Coalesce(Sum('amount'), Decimal('0.00')))['total']
        ),
    }
    
    return stats


# =============================================================================
# SCHOLARSHIP STATISTICS
# =============================================================================

def get_scholarship_statistics(filters=None):
    """
    Get comprehensive scholarship statistics
    
    Args:
        filters (dict): Optional filters
            - program_id: Filter by scholarship program
            - status: Filter by scholarship status
            - academic_session: Filter by session
            - scholarship_type: Filter by type
    
    Returns:
        dict: Scholarship statistics
    """
    from .models import (
        ScholarshipProgram, StudentScholarship, 
        StudentScholarshipApplication, ScholarshipApplicationLog
    )
    
    # Programs
    programs = ScholarshipProgram.objects.all()
    if filters and filters.get('scholarship_type'):
        programs = programs.filter(scholarship_type=filters['scholarship_type'])
    
    # Student scholarships
    scholarships = StudentScholarship.objects.select_related(
        'student', 'scholarship_program'
    )
    
    if filters:
        if filters.get('program_id'):
            scholarships = scholarships.filter(
                scholarship_program_id=filters['program_id']
            )
        if filters.get('status'):
            scholarships = scholarships.filter(status=filters['status'])
    
    stats = {
        'programs': {
            'total': programs.count(),
            'active': programs.filter(is_active=True).count(),
            'accepting_applications': programs.filter(
                is_accepting_applications=True
            ).count(),
        },
    }
    
    # Program types
    program_type_stats = programs.values('scholarship_type').annotate(
        count=Count('id'),
        total_budget=Coalesce(Sum('total_budget_amount'), Decimal('0.00')),
        budget_used=Coalesce(Sum('current_budget_used'), Decimal('0.00')),
        recipients=Coalesce(Sum('current_recipient_count'), 0),
    ).order_by('-budget_used')
    
    stats['programs']['by_type'] = [
        {
            'type': item['scholarship_type'],
            'count': item['count'],
            'total_budget': float(item['total_budget']),
            'budget_used': float(item['budget_used']),
            'recipients': item['recipients'],
        }
        for item in program_type_stats
    ]
    
    # Budget analysis
    budget_stats = programs.aggregate(
        total_budget=Coalesce(Sum('total_budget_amount'), Decimal('0.00')),
        total_used=Coalesce(Sum('current_budget_used'), Decimal('0.00')),
        avg_award=Coalesce(Avg('maximum_award_amount'), Decimal('0.00')),
    )
    
    stats['budget'] = {
        'total_allocated': float(budget_stats['total_budget']),
        'total_disbursed': float(budget_stats['total_used']),
        'remaining': float(
            budget_stats['total_budget'] - budget_stats['total_used']
        ),
        'utilization_rate': round(
            (budget_stats['total_used'] / budget_stats['total_budget'] * 100)
            if budget_stats['total_budget'] > 0 else 0,
            2
        ),
        'average_award': float(budget_stats['avg_award']),
    }
    
    # Student scholarships
    total_scholarships = scholarships.count()
    
    scholarship_stats = scholarships.aggregate(
        total_awarded=Coalesce(Sum('amount_awarded'), Decimal('0.00')),
        total_used=Coalesce(Sum('total_amount_used'), Decimal('0.00')),
        avg_awarded=Coalesce(Avg('amount_awarded'), Decimal('0.00')),
    )
    
    stats['scholarships'] = {
        'total_active': scholarships.filter(status='ACTIVE').count(),
        'total_suspended': scholarships.filter(status='SUSPENDED').count(),
        'total_terminated': scholarships.filter(status='TERMINATED').count(),
        'total_completed': scholarships.filter(status='COMPLETED').count(),
        'total_amount_awarded': float(scholarship_stats['total_awarded']),
        'total_amount_used': float(scholarship_stats['total_used']),
        'remaining_to_disburse': float(
            scholarship_stats['total_awarded'] - scholarship_stats['total_used']
        ),
        'average_award': float(scholarship_stats['avg_awarded']),
    }
    
    # Applications
    applications = StudentScholarshipApplication.objects.all()
    
    application_stats = applications.values('status').annotate(
        count=Count('id')
    )
    
    stats['applications'] = {
        'total': applications.count(),
        'by_status': {
            item['status']: item['count']
            for item in application_stats
        },
    }
    
    # Top programs by usage
    top_programs = programs.annotate(
        recipient_count=Count('student_scholarships'),
        total_disbursed=Coalesce(
            Sum('student_scholarships__total_amount_used'),
            Decimal('0.00')
        ),
    ).order_by('-total_disbursed')[:10]
    
    stats['top_programs'] = [
        {
            'program_id': str(prog.id),
            'name': prog.name,
            'code': prog.code,
            'type': prog.scholarship_type,
            'recipients': prog.recipient_count,
            'total_disbursed': float(prog.total_disbursed),
        }
        for prog in top_programs
    ]
    
    # Impact tracking
    application_logs = ScholarshipApplicationLog.objects.filter(
        is_reversed=False
    )
    
    impact_stats = application_logs.aggregate(
        total_applications=Count('id'),
        total_impact=Coalesce(Sum('amount_applied'), Decimal('0.00')),
        unique_students=Count('student', distinct=True),
        unique_invoices=Count('invoice', distinct=True),
    )
    
    stats['impact'] = {
        'total_applications_to_invoices': impact_stats['total_applications'],
        'total_discount_provided': float(impact_stats['total_impact']),
        'students_benefited': impact_stats['unique_students'],
        'invoices_affected': impact_stats['unique_invoices'],
    }
    
    return stats


# =============================================================================
# DISCOUNT STATISTICS
# =============================================================================

def get_discount_statistics(filters=None):
    """
    Get comprehensive discount statistics
    
    Args:
        filters (dict): Optional filters
            - eligibility_criteria: Filter by criteria
            - is_active: Filter by active status
            - academic_session: Filter by session
    
    Returns:
        dict: Discount statistics
    """
    from .models import FeesDiscount, DiscountApplication
    
    discounts = FeesDiscount.objects.all()
    
    if filters:
        if filters.get('eligibility_criteria'):
            discounts = discounts.filter(
                eligibility_criteria=filters['eligibility_criteria']
            )
        if filters.get('is_active') is not None:
            discounts = discounts.filter(is_active=filters['is_active'])
        if filters.get('academic_session'):
            discounts = discounts.filter(
                academic_session_id=filters['academic_session']
            )
    
    total_discounts = discounts.count()
    
    stats = {
        'total_discounts': total_discounts,
        'active_discounts': discounts.filter(is_active=True).count(),
        'inactive_discounts': discounts.filter(is_active=False).count(),
    }
    
    # By type
    type_stats = discounts.values('discount_type').annotate(
        count=Count('id'),
        avg_value=Coalesce(Avg('discount_value'), Decimal('0.00')),
    )
    
    stats['by_type'] = {
        item['discount_type']: {
            'count': item['count'],
            'average_value': float(item['avg_value']),
        }
        for item in type_stats
    }
    
    # By eligibility criteria
    criteria_stats = discounts.values('eligibility_criteria').annotate(
        count=Count('id')
    ).order_by('-count')
    
    stats['by_criteria'] = [
        {
            'criteria': item['eligibility_criteria'],
            'count': item['count'],
        }
        for item in criteria_stats
    ]
    
    # Usage statistics
    usage_stats = discounts.aggregate(
        total_usage=Coalesce(Sum('current_usage_count'), 0),
        avg_usage=Coalesce(Avg('current_usage_count'), Decimal('0.00')),
        total_budget_used=Coalesce(Sum('current_budget_used'), Decimal('0.00')),
    )
    
    stats['usage'] = {
        'total_applications': usage_stats['total_usage'],
        'average_per_discount': float(usage_stats['avg_usage']),
        'total_value_given': float(usage_stats['total_budget_used']),
    }
    
    # Applications
    applications = DiscountApplication.objects.select_related(
        'discount', 'invoice', 'student'
    )
    
    app_stats = applications.aggregate(
        total_applications=Count('id'),
        total_value=Coalesce(Sum('discount_amount'), Decimal('0.00')),
        avg_discount=Coalesce(Avg('discount_amount'), Decimal('0.00')),
        unique_students=Count('student', distinct=True),
    )
    
    stats['applications'] = {
        'total_applications': app_stats['total_applications'],
        'total_discount_value': float(app_stats['total_value']),
        'average_discount': float(app_stats['avg_discount']),
        'students_benefited': app_stats['unique_students'],
    }
    
    # Top discounts by usage
    top_discounts = discounts.order_by('-current_usage_count')[:10]
    
    stats['top_discounts'] = [
        {
            'discount_id': str(disc.id),
            'name': disc.name,
            'code': disc.code,
            'type': disc.discount_type,
            'usage_count': disc.current_usage_count,
            'budget_used': float(disc.current_budget_used),
        }
        for disc in top_discounts
    ]
    
    # Budget tracking
    with_budget = discounts.filter(budget_limit__isnull=False)
    budget_stats = with_budget.aggregate(
        total_budget=Coalesce(Sum('budget_limit'), Decimal('0.00')),
        total_used=Coalesce(Sum('current_budget_used'), Decimal('0.00')),
    )
    
    stats['budget'] = {
        'discounts_with_budget': with_budget.count(),
        'total_budget_allocated': float(budget_stats['total_budget']),
        'total_budget_used': float(budget_stats['total_used']),
        'budget_utilization': round(
            (budget_stats['total_used'] / budget_stats['total_budget'] * 100)
            if budget_stats['total_budget'] > 0 else 0,
            2
        ),
    }
    
    return stats


# =============================================================================
# DISPLAY GROUP STATISTICS
# =============================================================================

def get_display_group_statistics(filters=None):
    """
    Get comprehensive display group statistics
    
    Args:
        filters (dict): Optional filters
            - is_active: Filter by active status
            - show_as_group: Filter by grouping behavior
    
    Returns:
        dict: Display group statistics
    """
    from .models import DisplayGroup, FeesCategory, FeeInvoiceItem
    
    groups = DisplayGroup.objects.prefetch_related('feescategory_set')
    
    # Apply filters
    if filters:
        if filters.get('is_active') is not None:
            groups = groups.filter(is_active=filters['is_active'])
        
        if filters.get('show_as_group') is not None:
            groups = groups.filter(show_as_group=filters['show_as_group'])
    
    total_groups = groups.count()
    
    stats = {
        'total_groups': total_groups,
        'active_groups': groups.filter(is_active=True).count(),
        'inactive_groups': groups.filter(is_active=False).count(),
    }
    
    # Grouping behavior breakdown
    stats['grouping_behavior'] = {
        'show_as_group': groups.filter(show_as_group=True).count(),
        'show_individually': groups.filter(show_as_group=False).count(),
        'show_subtotals': groups.filter(
            show_as_group=True,
            show_group_subtotal=True
        ).count(),
        'no_subtotals': groups.filter(
            show_as_group=True,
            show_group_subtotal=False
        ).count(),
    }
    
    # Category distribution
    groups_with_categories = groups.annotate(
        category_count=Count('feescategory')
    )
    
    category_stats = groups_with_categories.aggregate(
        total_categories=Coalesce(Sum('category_count'), 0),
        avg_categories_per_group=Coalesce(Avg('category_count'), Decimal('0.00')),
        max_categories=Coalesce(Max('category_count'), 0),
        min_categories=Coalesce(Min('category_count'), 0),
        groups_with_no_categories=Count('id', filter=Q(category_count=0)),
    )
    
    stats['category_distribution'] = {
        'total_categories_assigned': category_stats['total_categories'],
        'avg_categories_per_group': float(category_stats['avg_categories_per_group']),
        'max_categories_in_group': category_stats['max_categories'],
        'min_categories_in_group': category_stats['min_categories'],
        'groups_with_no_categories': category_stats['groups_with_no_categories'],
        'groups_with_categories': total_groups - category_stats['groups_with_no_categories'],
    }
    
    # Display order analysis
    display_order_stats = groups.aggregate(
        avg_display_order=Coalesce(Avg('display_order'), Decimal('0.00')),
        min_display_order=Coalesce(Min('display_order'), 0),
        max_display_order=Coalesce(Max('display_order'), 0),
    )
    
    stats['display_order'] = {
        'avg_order': float(display_order_stats['avg_display_order']),
        'min_order': display_order_stats['min_display_order'],
        'max_order': display_order_stats['max_display_order'],
    }
    
    # Revenue by display group (from invoice items through categories)
    revenue_by_group = []
    for group in groups:
        categories_in_group = group.feescategory_set.all()
        
        if categories_in_group.exists():
            revenue_data = FeeInvoiceItem.objects.filter(
                fee_category__in=categories_in_group
            ).aggregate(
                total_revenue=Coalesce(Sum('final_amount'), Decimal('0.00')),
                invoice_count=Count('invoice', distinct=True),
                item_count=Count('id'),
            )
            
            revenue_by_group.append({
                'group_id': str(group.id),
                'group_name': group.name,
                'display_order': group.display_order,
                'category_count': categories_in_group.count(),
                'total_revenue': float(revenue_data['total_revenue']),
                'invoice_count': revenue_data['invoice_count'],
                'item_count': revenue_data['item_count'],
                'is_active': group.is_active,
                'show_as_group': group.show_as_group,
            })
    
    # Sort by revenue
    revenue_by_group.sort(key=lambda x: x['total_revenue'], reverse=True)
    
    stats['revenue_by_group'] = revenue_by_group[:20]  # Top 20
    
    # Total revenue across all groups
    total_revenue = sum(item['total_revenue'] for item in revenue_by_group)
    stats['total_revenue_all_groups'] = total_revenue
    
    # Groups by category count
    groups_by_size = groups_with_categories.order_by('-category_count')[:10]
    
    stats['largest_groups'] = [
        {
            'group_id': str(group.id),
            'name': group.name,
            'category_count': group.category_count,
            'display_order': group.display_order,
            'is_active': group.is_active,
        }
        for group in groups_by_size
    ]
    
    # Groups with no categories (potential cleanup candidates)
    empty_groups = groups.annotate(
        category_count=Count('feescategory')
    ).filter(category_count=0)
    
    stats['empty_groups'] = [
        {
            'group_id': str(group.id),
            'name': group.name,
            'display_order': group.display_order,
            'is_active': group.is_active,
        }
        for group in empty_groups
    ]
    
    # Color code usage (grouping similar colors)
    color_stats = groups.values('color_code').annotate(
        count=Count('id')
    ).order_by('-count')
    
    stats['color_distribution'] = [
        {
            'color_code': item['color_code'],
            'count': item['count'],
        }
        for item in color_stats[:10]  # Top 10 colors
    ]
    
    # Most used display orders
    order_usage = groups.values('display_order').annotate(
        count=Count('id')
    ).order_by('display_order')
    
    stats['display_order_usage'] = [
        {
            'order': item['display_order'],
            'count': item['count'],
        }
        for item in order_usage
    ]
    
    # Configuration summary
    stats['configuration_summary'] = {
        'total_active_with_categories': groups.filter(
            is_active=True
        ).annotate(
            category_count=Count('feescategory')
        ).filter(category_count__gt=0).count(),
        'total_inactive_with_categories': groups.filter(
            is_active=False
        ).annotate(
            category_count=Count('feescategory')
        ).filter(category_count__gt=0).count(),
        'showing_as_groups': groups.filter(
            is_active=True,
            show_as_group=True
        ).count(),
        'showing_individually': groups.filter(
            is_active=True,
            show_as_group=False
        ).count(),
    }
    
    return stats


# =============================================================================
# DISPLAY GROUP STATISTICS
# =============================================================================

def get_display_group_statistics(filters=None):
    """
    Get comprehensive display group statistics
    
    Args:
        filters (dict): Optional filters
            - is_active: Filter by active status
            - show_as_group: Filter by grouping behavior
    
    Returns:
        dict: Display group statistics
    """
    from .models import DisplayGroup, FeesCategory, FeeInvoiceItem
    
    groups = DisplayGroup.objects.prefetch_related('feescategory_set')
    
    # Apply filters
    if filters:
        if filters.get('is_active') is not None:
            groups = groups.filter(is_active=filters['is_active'])
        
        if filters.get('show_as_group') is not None:
            groups = groups.filter(show_as_group=filters['show_as_group'])
    
    total_groups = groups.count()
    
    stats = {
        'total_groups': total_groups,
        'active_groups': groups.filter(is_active=True).count(),
        'inactive_groups': groups.filter(is_active=False).count(),
    }
    
    # Grouping behavior
    stats['grouping_behavior'] = {
        'show_as_group': groups.filter(show_as_group=True).count(),
        'show_individually': groups.filter(show_as_group=False).count(),
        'show_subtotal': groups.filter(
            show_as_group=True,
            show_group_subtotal=True
        ).count(),
        'hide_subtotal': groups.filter(
            show_as_group=True,
            show_group_subtotal=False
        ).count(),
    }
    
    # Categories per group
    groups_with_categories = groups.annotate(
        category_count=Count('feescategory')
    )
    
    category_stats = groups_with_categories.aggregate(
        avg_categories=Coalesce(Avg('category_count'), Decimal('0.00')),
        max_categories=Coalesce(Max('category_count'), 0),
        min_categories=Coalesce(Min('category_count'), 0),
        groups_with_no_categories=Count('id', filter=Q(category_count=0)),
    )
    
    stats['category_distribution'] = {
        'avg_categories_per_group': float(category_stats['avg_categories']),
        'max_categories_in_group': category_stats['max_categories'],
        'min_categories_in_group': category_stats['min_categories'],
        'groups_with_no_categories': category_stats['groups_with_no_categories'],
        'groups_with_categories': total_groups - category_stats['groups_with_no_categories'],
    }
    
    # Display order analysis
    order_stats = groups.aggregate(
        avg_order=Coalesce(Avg('display_order'), Decimal('0.00')),
        min_order=Coalesce(Min('display_order'), 0),
        max_order=Coalesce(Max('display_order'), 0),
    )
    
    stats['display_order'] = {
        'avg_order': float(order_stats['avg_order']),
        'min_order': order_stats['min_order'],
        'max_order': order_stats['max_order'],
        'order_range': order_stats['max_order'] - order_stats['min_order'],
    }
    
    # Groups by number of categories
    groups_by_size = groups_with_categories.values('category_count').annotate(
        count=Count('id')
    ).order_by('category_count')
    
    stats['groups_by_size'] = [
        {
            'category_count': item['category_count'],
            'group_count': item['count'],
        }
        for item in groups_by_size
    ]
    
    # Top groups by category count
    top_groups = groups_with_categories.order_by('-category_count')[:10]
    
    stats['largest_groups'] = [
        {
            'group_id': str(group.id),
            'name': group.name,
            'category_count': group.category_count,
            'display_order': group.display_order,
            'show_as_group': group.show_as_group,
            'is_active': group.is_active,
        }
        for group in top_groups
    ]
    
    # Revenue analysis by display group (from invoice items)
    revenue_by_group = FeeInvoiceItem.objects.filter(
        fee_category__display_group__isnull=False
    ).values(
        'fee_category__display_group__id',
        'fee_category__display_group__name'
    ).annotate(
        total_revenue=Coalesce(Sum('final_amount'), Decimal('0.00')),
        item_count=Count('id'),
        avg_amount=Coalesce(Avg('final_amount'), Decimal('0.00')),
    ).order_by('-total_revenue')[:10]
    
    stats['revenue_by_group'] = [
        {
            'group_id': str(item['fee_category__display_group__id']),
            'group_name': item['fee_category__display_group__name'],
            'total_revenue': float(item['total_revenue']),
            'item_count': item['item_count'],
            'avg_amount': float(item['avg_amount']),
        }
        for item in revenue_by_group
    ]
    
    # Categories without display group
    categories_without_group = FeesCategory.objects.filter(
        display_group__isnull=True
    ).count()
    
    stats['ungrouped_categories'] = {
        'count': categories_without_group,
    }
    
    # Color code usage
    color_usage = groups.values('color_code').annotate(
        count=Count('id')
    ).order_by('-count')
    
    stats['color_distribution'] = [
        {
            'color_code': item['color_code'],
            'usage_count': item['count'],
        }
        for item in color_usage[:10]  # Top 10 most used colors
    ]
    
    # Most used colors
    most_common_color = color_usage.first()
    if most_common_color:
        stats['most_common_color'] = {
            'color_code': most_common_color['color_code'],
            'usage_count': most_common_color['count'],
        }
    
    # Groups with duplicate display orders (potential ordering conflicts)
    duplicate_orders = groups.values('display_order').annotate(
        count=Count('id')
    ).filter(count__gt=1).order_by('display_order')
    
    stats['ordering_conflicts'] = {
        'has_duplicates': duplicate_orders.exists(),
        'duplicate_orders': [
            {
                'display_order': item['display_order'],
                'group_count': item['count'],
            }
            for item in duplicate_orders
        ],
    }
    
    # Active vs inactive comparison
    active_groups = groups.filter(is_active=True)
    inactive_groups = groups.filter(is_active=False)
    
    active_stats = active_groups.aggregate(
        total_categories=Count('feescategory')
    )
    
    inactive_stats = inactive_groups.aggregate(
        total_categories=Count('feescategory')
    )
    
    stats['active_vs_inactive'] = {
        'active': {
            'count': active_groups.count(),
            'total_categories': active_stats['total_categories'],
        },
        'inactive': {
            'count': inactive_groups.count(),
            'total_categories': inactive_stats['total_categories'],
        },
    }
    
    return stats


# =============================================================================
# FEE CATEGORY STATISTICS
# =============================================================================

def get_fee_category_statistics(filters=None):
    """
    Get fee category statistics
    
    Args:
        filters (dict): Optional filters
            - category_type: Filter by category type
            - is_active: Filter by active status
            - applicability: Filter by applicability
    
    Returns:
        dict: Fee category statistics
    """
    from .models import FeesCategory, FeeInvoiceItem
    
    categories = FeesCategory.objects.all()
    
    if filters:
        if filters.get('category_type'):
            categories = categories.filter(category_type=filters['category_type'])
        if filters.get('is_active') is not None:
            categories = categories.filter(is_active=filters['is_active'])
        if filters.get('applicability'):
            categories = categories.filter(applicability=filters['applicability'])
    
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
    
    # By applicability
    applicability_stats = categories.values('applicability').annotate(
        count=Count('id')
    ).order_by('-count')
    
    stats['by_applicability'] = [
        {
            'applicability': item['applicability'],
            'count': item['count'],
        }
        for item in applicability_stats
    ]
    
    # Configuration flags
    stats['configuration'] = {
        'mandatory': categories.filter(is_mandatory=True).count(),
        'optional': categories.filter(is_mandatory=False).count(),
        'refundable': categories.filter(is_refundable=True).count(),
        'non_refundable': categories.filter(is_refundable=False).count(),
        'taxable': categories.filter(is_taxable=True).count(),
        'non_taxable': categories.filter(is_taxable=False).count(),
        'partial_payment_allowed': categories.filter(
            allows_partial_payment=True
        ).count(),
    }
    
    # Revenue by category (from invoice items)
    revenue_stats = FeeInvoiceItem.objects.values(
        'fee_category__name',
        'fee_category__category_type'
    ).annotate(
        total_amount=Coalesce(Sum('final_amount'), Decimal('0.00')),
        count=Count('id'),
    ).order_by('-total_amount')[:10]
    
    stats['top_revenue_categories'] = [
        {
            'category': item['fee_category__name'],
            'type': item['fee_category__category_type'],
            'total_revenue': float(item['total_amount']),
            'invoice_count': item['count'],
        }
        for item in revenue_stats
    ]
    
    return stats


# =============================================================================
# REFUND STATISTICS
# =============================================================================

def get_refund_statistics(filters=None):
    """
    Get comprehensive refund statistics
    
    Args:
        filters (dict): Optional filters
            - status: Filter by refund status
            - refund_type: Filter by refund type
            - academic_session: Filter by session ID
            - fiscal_period: Filter by fiscal period ID
            - date_from: Start date filter
            - date_to: End date filter
    
    Returns:
        dict: Refund statistics
    """
    from .models import Refund
    
    refunds = Refund.objects.select_related(
        'student', 'invoice', 'payment', 'payment_method',
        'academic_session', 'fiscal_period'
    )
    
    # Apply filters
    if filters:
        if filters.get('status'):
            refunds = refunds.filter(status=filters['status'])
        
        if filters.get('refund_type'):
            refunds = refunds.filter(refund_type=filters['refund_type'])
        
        if filters.get('academic_session'):
            refunds = refunds.filter(academic_session_id=filters['academic_session'])
        
        if filters.get('fiscal_period'):
            refunds = refunds.filter(fiscal_period_id=filters['fiscal_period'])
        
        if filters.get('date_from'):
            refunds = refunds.filter(requested_date__gte=filters['date_from'])
        
        if filters.get('date_to'):
            refunds = refunds.filter(requested_date__lte=filters['date_to'])
    
    total_refunds = refunds.count()
    
    stats = {
        'total_refunds': total_refunds,
    }
    
    # Status breakdown
    status_stats = refunds.values('status').annotate(
        count=Count('id'),
        total_amount=Coalesce(Sum('amount'), Decimal('0.00')),
    ).order_by('-count')
    
    stats['by_status'] = {
        item['status']: {
            'count': item['count'],
            'total_amount': float(item['total_amount']),
        }
        for item in status_stats
    }
    
    # Refund type breakdown
    type_stats = refunds.values('refund_type').annotate(
        count=Count('id'),
        total_amount=Coalesce(Sum('amount'), Decimal('0.00')),
    ).order_by('-total_amount')
    
    stats['by_type'] = [
        {
            'type': item['refund_type'],
            'count': item['count'],
            'total_amount': float(item['total_amount']),
        }
        for item in type_stats
    ]
    
    # Financial totals
    financial_totals = refunds.aggregate(
        total_requested=Coalesce(Sum('amount'), Decimal('0.00')),
        total_approved=Coalesce(
            Sum('approved_amount', filter=Q(status__in=['APPROVED', 'PROCESSING', 'COMPLETED'])),
            Decimal('0.00')
        ),
        total_completed=Coalesce(
            Sum('amount', filter=Q(status='COMPLETED')),
            Decimal('0.00')
        ),
        avg_refund=Coalesce(Avg('amount'), Decimal('0.00')),
        max_refund=Coalesce(Max('amount'), Decimal('0.00')),
    )
    
    stats['financial_totals'] = {
        'total_requested': float(financial_totals['total_requested']),
        'total_approved': float(financial_totals['total_approved']),
        'total_completed': float(financial_totals['total_completed']),
        'average_refund': float(financial_totals['avg_refund']),
        'largest_refund': float(financial_totals['max_refund']),
    }
    
    # Approval metrics
    approved = refunds.filter(status__in=['APPROVED', 'PROCESSING', 'COMPLETED'])
    rejected = refunds.filter(status='REJECTED')
    pending = refunds.filter(status__in=['REQUESTED', 'UNDER_REVIEW'])
    
    stats['approval_metrics'] = {
        'approved_count': approved.count(),
        'rejected_count': rejected.count(),
        'pending_count': pending.count(),
        'approval_rate': round(
            (approved.count() / total_refunds * 100) if total_refunds > 0 else 0,
            2
        ),
        'rejection_rate': round(
            (rejected.count() / total_refunds * 100) if total_refunds > 0 else 0,
            2
        ),
    }
    
    # Processing time analysis (for completed refunds)
    completed_refunds = refunds.filter(
        status='COMPLETED',
        payment_date__isnull=False
    )
    
    if completed_refunds.exists():
        # Calculate average processing days
        processing_times = []
        for refund in completed_refunds:
            days = (refund.payment_date - refund.requested_date).days
            processing_times.append(days)
        
        if processing_times:
            stats['processing_metrics'] = {
                'avg_processing_days': round(sum(processing_times) / len(processing_times), 1),
                'min_processing_days': min(processing_times),
                'max_processing_days': max(processing_times),
            }
    
    # Payment method breakdown
    method_stats = refunds.values(
        'payment_method__name'
    ).annotate(
        count=Count('id'),
        total_amount=Coalesce(Sum('amount'), Decimal('0.00')),
    ).order_by('-total_amount')
    
    stats['by_payment_method'] = [
        {
            'method': item['payment_method__name'],
            'count': item['count'],
            'total_amount': float(item['total_amount']),
        }
        for item in method_stats
    ]
    
    # Session breakdown
    session_stats = refunds.filter(
        academic_session__isnull=False
    ).values(
        'academic_session__year_name',
        'academic_session__term_name'
    ).annotate(
        count=Count('id'),
        total_amount=Coalesce(Sum('amount'), Decimal('0.00')),
    ).order_by('-total_amount')[:10]
    
    stats['by_session'] = [
        {
            'session': f"{item['academic_session__year_name']} - {item['academic_session__term_name']}" 
                       if item['academic_session__year_name'] else 'Unknown',
            'count': item['count'],
            'total_amount': float(item['total_amount']),
        }
        for item in session_stats
    ]
    
    # Recent activity
    now = timezone.now()
    stats['recent_activity'] = {
        'requested_last_7_days': refunds.filter(
            requested_date__gte=now.date() - timedelta(days=7)
        ).count(),
        'requested_last_30_days': refunds.filter(
            requested_date__gte=now.date() - timedelta(days=30)
        ).count(),
        'completed_last_7_days': refunds.filter(
            status='COMPLETED',
            payment_date__gte=now.date() - timedelta(days=7)
        ).count(),
        'completed_last_30_days': refunds.filter(
            status='COMPLETED',
            payment_date__gte=now.date() - timedelta(days=30)
        ).count(),
    }
    
    return stats


# =============================================================================
# CONSOLIDATED FINANCIAL DASHBOARD
# =============================================================================

def get_financial_dashboard(academic_session_id=None, fiscal_period_id=None):
    """
    Get consolidated financial dashboard with key metrics
    
    Args:
        academic_session_id: Optional academic session filter
        fiscal_period_id: Optional fiscal period filter
    
    Returns:
        dict: Comprehensive financial dashboard data
    """
    from .models import FeeInvoice, Payment, StudentAccount
    
    # Build base querysets
    invoices = FeeInvoice.objects.all()
    payments = Payment.objects.all()
    accounts = StudentAccount.objects.all()
    
    if academic_session_id:
        invoices = invoices.filter(academic_session_id=academic_session_id)
        payments = payments.filter(academic_session_id=academic_session_id)
    
    if fiscal_period_id:
        invoices = invoices.filter(fiscal_period_id=fiscal_period_id)
        payments = payments.filter(fiscal_period_id=fiscal_period_id)
    
    # Quick stats
    dashboard = {
        'summary': {
            'total_invoices': invoices.count(),
            'total_payments': payments.count(),
            'total_accounts': accounts.count(),
        },
    }
    
    # Financial overview
    financial = invoices.aggregate(
        total_billed=Coalesce(Sum('total_amount'), Decimal('0.00')),
        total_paid=Coalesce(Sum('paid_amount'), Decimal('0.00')),
        total_outstanding=Coalesce(Sum('balance'), Decimal('0.00')),
    )
    
    payment_total = payments.filter(status='COMPLETED').aggregate(
        total=Coalesce(Sum('amount'), Decimal('0.00'))
    )
    
    dashboard['financial_overview'] = {
        'total_billed': float(financial['total_billed']),
        'total_collected': float(payment_total['total']),
        'total_outstanding': float(financial['total_outstanding']),
        'collection_rate': round(
            (payment_total['total'] / financial['total_billed'] * 100)
            if financial['total_billed'] > 0 else 0,
            2
        ),
    }
    
    # Invoice status breakdown
    invoice_status = invoices.values('status').annotate(
        count=Count('id'),
        amount=Coalesce(Sum('total_amount'), Decimal('0.00')),
    )
    
    dashboard['invoice_status'] = {
        item['status']: {
            'count': item['count'],
            'amount': float(item['amount']),
        }
        for item in invoice_status
    }
    
    # Payment trends (last 30 days)
    thirty_days_ago = timezone.now().date() - timedelta(days=30)
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
            'amount': float(item['total']),
        }
        for item in recent_payments
    ]
    
    # Outstanding by aging
    from core.utils import get_school_today
    today = get_school_today()
    dashboard['outstanding_aging'] = {
        'current': float(
            invoices.filter(
                due_date__gte=today,
                status__in=['PENDING', 'PARTIALLY_PAID']
            ).aggregate(total=Coalesce(Sum('balance'), Decimal('0.00')))['total']
        ),
        'overdue_1_30': float(
            invoices.filter(
                due_date__lt=today,
                due_date__gte=today - timedelta(days=30),
                status__in=['PENDING', 'PARTIALLY_PAID', 'OVERDUE']
            ).aggregate(total=Coalesce(Sum('balance'), Decimal('0.00')))['total']
        ),
        'overdue_31_60': float(
            invoices.filter(
                due_date__lt=today - timedelta(days=30),
                due_date__gte=today - timedelta(days=60),
                status__in=['PENDING', 'PARTIALLY_PAID', 'OVERDUE']
            ).aggregate(total=Coalesce(Sum('balance'), Decimal('0.00')))['total']
        ),
        'overdue_over_60': float(
            invoices.filter(
                due_date__lt=today - timedelta(days=60),
                status__in=['PENDING', 'PARTIALLY_PAID', 'OVERDUE']
            ).aggregate(total=Coalesce(Sum('balance'), Decimal('0.00')))['total']
        ),
    }
    
    return dashboard