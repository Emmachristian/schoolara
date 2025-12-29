# fees/stats.py

"""
Comprehensive statistics utility functions for Fees models.
Provides detailed analytics for student accounts, invoices, payments, 
scholarships, discounts, and financial performance.
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
    from .models import StudentAccount
    from students.models import Student
    
    accounts = StudentAccount.objects.select_related('student')
    
    # Apply filters
    if filters:
        if filters.get('status'):
            accounts = accounts.filter(status=filters['status'])
        
        if filters.get('has_balance') is not None:
            if filters['has_balance']:
                accounts = accounts.exclude(current_balance=0)
            else:
                accounts = accounts.filter(current_balance=0)
        
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
    
    # Balance analysis
    balance_stats = accounts.aggregate(
        total_balance=Coalesce(Sum('current_balance'), Decimal('0.00')),
        avg_balance=Coalesce(Avg('current_balance'), Decimal('0.00')),
        max_balance=Coalesce(Max('current_balance'), Decimal('0.00')),
        min_balance=Coalesce(Min('current_balance'), Decimal('0.00')),
        total_fees_charged=Coalesce(Sum('total_fees_charged'), Decimal('0.00')),
        total_payments=Coalesce(Sum('total_payments_received'), Decimal('0.00')),
        total_discounts=Coalesce(Sum('total_discounts_applied'), Decimal('0.00')),
        total_refunds=Coalesce(Sum('total_refunds_issued'), Decimal('0.00')),
    )
    
    stats['balances'] = {
        'total_balance': float(balance_stats['total_balance']),
        'average_balance': float(balance_stats['avg_balance']),
        'max_balance': float(balance_stats['max_balance']),
        'min_balance': float(balance_stats['min_balance']),
        'total_fees_charged': float(balance_stats['total_fees_charged']),
        'total_payments_received': float(balance_stats['total_payments']),
        'total_discounts_applied': float(balance_stats['total_discounts']),
        'total_refunds_issued': float(balance_stats['total_refunds']),
    }
    
    # Debt analysis (negative balances = outstanding)
    debtors = accounts.filter(current_balance__lt=0)
    credit_accounts = accounts.filter(current_balance__gt=0)
    zero_balance = accounts.filter(current_balance=0)
    
    stats['debt_analysis'] = {
        'total_debtors': debtors.count(),
        'total_outstanding': float(
            debtors.aggregate(
                total=Coalesce(Sum('current_balance'), Decimal('0.00'))
            )['total'] * -1  # Make positive for display
        ),
        'average_debt': float(
            debtors.aggregate(
                avg=Coalesce(Avg('current_balance'), Decimal('0.00'))
            )['avg'] * -1
        ) if debtors.exists() else 0,
        'accounts_with_credit': credit_accounts.count(),
        'total_credit': float(
            credit_accounts.aggregate(
                total=Coalesce(Sum('current_balance'), Decimal('0.00'))
            )['total']
        ),
        'zero_balance_accounts': zero_balance.count(),
    }
    
    # Collection rate
    if balance_stats['total_fees_charged'] > 0:
        collection_rate = (
            balance_stats['total_payments'] / 
            balance_stats['total_fees_charged'] * 100
        )
        stats['collection_rate'] = round(float(collection_rate), 2)
    else:
        stats['collection_rate'] = 0
    
    # Top debtors
    top_debtors = debtors.order_by('current_balance')[:10]
    stats['top_debtors'] = [
        {
            'student_id': str(acc.student.id),
            'student_name': acc.student.get_full_name(),
            'admission_number': acc.student.admission_number,
            'outstanding': float(acc.current_balance * -1),
            'total_charged': float(acc.total_fees_charged),
            'total_paid': float(acc.total_payments_received),
        }
        for acc in top_debtors
    ]
    
    # Credit limit usage
    accounts_with_limit = accounts.filter(credit_limit__gt=0)
    stats['credit_limits'] = {
        'accounts_with_limit': accounts_with_limit.count(),
        'total_limit_allocated': float(
            accounts_with_limit.aggregate(
                total=Coalesce(Sum('credit_limit'), Decimal('0.00'))
            )['total']
        ),
        'average_limit': float(
            accounts_with_limit.aggregate(
                avg=Coalesce(Avg('credit_limit'), Decimal('0.00'))
            )['avg']
        ) if accounts_with_limit.exists() else 0,
    }
    
    # Activity tracking
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
            today = timezone.now().date()
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
    today = timezone.now().date()
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
    today = timezone.now().date()
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