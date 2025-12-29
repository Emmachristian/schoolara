# fees/htmx_views.py

from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.db.models import Q, Count, Sum, Avg, F, DecimalField
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from datetime import timedelta, date
from decimal import Decimal
import logging

from .models import (
    StudentAccount,
    AccountTransaction,
    DisplayGroup,
    FeesCategory,
    FeesStructure,
    FeesStructureItem,
    FeeInvoice,
    FeeInvoiceItem,
    Payment,
    ScholarshipProgram,
    StudentScholarshipApplication,
    StudentScholarship,
    ScholarshipApplicationLog,
    FeesDiscount,
    DiscountApplication,
    Refund
)
from utils.utils import parse_filters, paginate_queryset

logger = logging.getLogger(__name__)


# =============================================================================
# STUDENT ACCOUNT SEARCH
# =============================================================================

def student_account_search(request):
    """HTMX-compatible student account search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'status', 'min_balance', 'max_balance', 
        'has_debt', 'has_credit', 'is_active'
    ])
    
    query = filters['q']
    status = filters['status']
    min_balance = filters['min_balance']
    max_balance = filters['max_balance']
    has_debt = filters['has_debt']
    has_credit = filters['has_credit']
    
    # Build queryset
    accounts = StudentAccount.objects.select_related(
        'student'
    ).annotate(
        transaction_count=Count('transactions')
    ).order_by('-current_balance')
    
    # Apply text search
    if query:
        accounts = accounts.filter(
            Q(student__first_name__icontains=query) |
            Q(student__last_name__icontains=query) |
            Q(student__admission_number__icontains=query)
        )
    
    # Apply filters
    if status:
        accounts = accounts.filter(status=status)
    
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
    
    if has_debt and has_debt.lower() == 'true':
        accounts = accounts.filter(current_balance__lt=0)
    
    if has_credit and has_credit.lower() == 'true':
        accounts = accounts.filter(current_balance__gt=0)
    
    # Paginate
    accounts_page, paginator = paginate_queryset(request, accounts, per_page=20)
    
    # Calculate stats
    total = accounts.count()
    
    stats = {
        'total': total,
        'active': accounts.filter(status='ACTIVE').count(),
        'suspended': accounts.filter(status='SUSPENDED').count(),
        'with_debt': accounts.filter(current_balance__lt=0).count(),
        'with_credit': accounts.filter(current_balance__gt=0).count(),
        'zero_balance': accounts.filter(current_balance=0).count(),
        'total_debt': abs(accounts.filter(current_balance__lt=0).aggregate(
            Sum('current_balance'))['current_balance__sum'] or 0),
        'total_credit': accounts.filter(current_balance__gt=0).aggregate(
            Sum('current_balance'))['current_balance__sum'] or 0,
        'avg_balance': accounts.aggregate(Avg('current_balance'))['current_balance__avg'] or 0,
    }
    
    return render(request, 'fees/accounts/_account_results.html', {
        'accounts_page': accounts_page,
        'stats': stats,
    })


# =============================================================================
# ACCOUNT TRANSACTION SEARCH
# =============================================================================

def account_transaction_search(request):
    """HTMX-compatible account transaction search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'transaction_type', 'student_account', 'academic_session',
        'fiscal_period', 'start_date', 'end_date', 'min_amount', 'max_amount'
    ])
    
    query = filters['q']
    transaction_type = filters['transaction_type']
    student_account = filters['student_account']
    academic_session = filters['academic_session']
    fiscal_period = filters['fiscal_period']
    start_date = filters['start_date']
    end_date = filters['end_date']
    min_amount = filters['min_amount']
    max_amount = filters['max_amount']
    
    # Build queryset
    transactions = AccountTransaction.objects.select_related(
        'student_account__student',
        'invoice',
        'payment',
        'academic_session',
        'fiscal_period'
    ).order_by('-created_at')
    
    # Apply text search
    if query:
        transactions = transactions.filter(
            Q(description__icontains=query) |
            Q(reference_number__icontains=query) |
            Q(student_account__student__first_name__icontains=query) |
            Q(student_account__student__last_name__icontains=query)
        )
    
    # Apply filters
    if transaction_type:
        transactions = transactions.filter(transaction_type=transaction_type)
    
    if student_account:
        transactions = transactions.filter(student_account_id=student_account)
    
    if academic_session:
        transactions = transactions.filter(academic_session_id=academic_session)
    
    if fiscal_period:
        transactions = transactions.filter(fiscal_period_id=fiscal_period)
    
    if start_date:
        transactions = transactions.filter(created_at__gte=start_date)
    
    if end_date:
        transactions = transactions.filter(created_at__lte=end_date)
    
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
        'credits': transactions.filter(transaction_type='CREDIT').count(),
        'debits': transactions.filter(transaction_type='DEBIT').count(),
        'payments': transactions.filter(transaction_type='PAYMENT').count(),
        'invoices': transactions.filter(transaction_type='INVOICE').count(),
        'total_credit_amount': transactions.filter(transaction_type__in=['CREDIT', 'PAYMENT']).aggregate(
            Sum('amount'))['amount__sum'] or 0,
        'total_debit_amount': transactions.filter(transaction_type__in=['DEBIT', 'INVOICE']).aggregate(
            Sum('amount'))['amount__sum'] or 0,
    }
    
    return render(request, 'fees/transactions/_transaction_results.html', {
        'transactions_page': transactions_page,
        'stats': stats,
    })


# =============================================================================
# DISPLAY GROUP SEARCH
# =============================================================================

def display_group_search(request):
    """HTMX-compatible display group search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'is_active', 'show_as_group'
    ])
    
    query = filters['q']
    is_active = filters['is_active']
    show_as_group = filters['show_as_group']
    
    # Build queryset
    groups = DisplayGroup.objects.annotate(
        category_count=Count('feescategory')
    ).order_by('display_order', 'name')
    
    # Apply text search
    if query:
        groups = groups.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query)
        )
    
    # Apply filters
    if is_active is not None:
        groups = groups.filter(is_active=(is_active.lower() == 'true'))
    
    if show_as_group is not None:
        groups = groups.filter(show_as_group=(show_as_group.lower() == 'true'))
    
    # Paginate
    groups_page, paginator = paginate_queryset(request, groups, per_page=20)
    
    # Calculate stats
    total = groups.count()
    
    stats = {
        'total': total,
        'active': groups.filter(is_active=True).count(),
        'grouped': groups.filter(show_as_group=True).count(),
        'ungrouped': groups.filter(show_as_group=False).count(),
        'total_categories': sum(g.category_count for g in groups),
    }
    
    return render(request, 'fees/display_groups/_group_results.html', {
        'groups_page': groups_page,
        'stats': stats,
    })


# =============================================================================
# FEE CATEGORY SEARCH
# =============================================================================

def fee_category_search(request):
    """HTMX-compatible fee category search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'category_type', 'is_active', 'is_mandatory', 
        'is_refundable', 'is_taxable', 'applicability',
        'display_group', 'frequency'
    ])
    
    query = filters['q']
    category_type = filters['category_type']
    is_active = filters['is_active']
    is_mandatory = filters['is_mandatory']
    is_refundable = filters['is_refundable']
    is_taxable = filters['is_taxable']
    applicability = filters['applicability']
    display_group = filters['display_group']
    frequency = filters['frequency']
    
    # Build queryset
    categories = FeesCategory.objects.select_related(
        'display_group'
    ).prefetch_related(
        'applicable_levels'
    ).annotate(
        structure_count=Count('feesstructureitem')
    ).order_by('display_order', 'name')
    
    # Apply text search
    if query:
        categories = categories.filter(
            Q(name__icontains=query) |
            Q(code__icontains=query) |
            Q(description__icontains=query)
        )
    
    # Apply filters
    if category_type:
        categories = categories.filter(category_type=category_type)
    
    if display_group:
        categories = categories.filter(display_group_id=display_group)
    
    if frequency:
        categories = categories.filter(frequency=frequency)
    
    if applicability:
        categories = categories.filter(applicability=applicability)
    
    if is_active is not None:
        categories = categories.filter(is_active=(is_active.lower() == 'true'))
    
    if is_mandatory is not None:
        categories = categories.filter(is_mandatory=(is_mandatory.lower() == 'true'))
    
    if is_refundable is not None:
        categories = categories.filter(is_refundable=(is_refundable.lower() == 'true'))
    
    if is_taxable is not None:
        categories = categories.filter(is_taxable=(is_taxable.lower() == 'true'))
    
    # Paginate
    categories_page, paginator = paginate_queryset(request, categories, per_page=20)
    
    # Calculate stats
    total = categories.count()
    
    stats = {
        'total': total,
        'active': categories.filter(is_active=True).count(),
        'mandatory': categories.filter(is_mandatory=True).count(),
        'optional': categories.filter(is_mandatory=False).count(),
        'refundable': categories.filter(is_refundable=True).count(),
        'taxable': categories.filter(is_taxable=True).count(),
        'recurring': categories.filter(is_recurring=True).count(),
        'tuition': categories.filter(category_type='TUITION').count(),
        'boarding': categories.filter(category_type='BOARDING').count(),
    }
    
    return render(request, 'fees/categories/_category_results.html', {
        'categories_page': categories_page,
        'stats': stats,
    })


# =============================================================================
# FEE STRUCTURE SEARCH
# =============================================================================

def fee_structure_search(request):
    """HTMX-compatible fee structure search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'structure_type', 'boarding_type_filter', 'student_type_filter',
        'is_active', 'academic_session', 'academic_level'
    ])
    
    query = filters['q']
    structure_type = filters['structure_type']
    boarding_type_filter = filters['boarding_type_filter']
    student_type_filter = filters['student_type_filter']
    is_active = filters['is_active']
    academic_session = filters['academic_session']
    academic_level = filters['academic_level']
    
    # Build queryset
    structures = FeesStructure.objects.prefetch_related(
        'academic_levels',
        'applicable_sessions',
        'applicable_classes',
        'items__fee_category'
    ).annotate(
        item_count=Count('items', distinct=True),
        total_amount=Sum('items__amount')
    ).order_by('structure_type', 'priority', 'name')
    
    # Apply text search
    if query:
        structures = structures.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query)
        )
    
    # Apply filters
    if structure_type:
        structures = structures.filter(structure_type=structure_type)
    
    if boarding_type_filter:
        structures = structures.filter(boarding_type_filter=boarding_type_filter)
    
    if student_type_filter:
        structures = structures.filter(student_type_filter=student_type_filter)
    
    if academic_session:
        structures = structures.filter(applicable_sessions__id=academic_session)
    
    if academic_level:
        structures = structures.filter(academic_levels__id=academic_level)
    
    if is_active is not None:
        structures = structures.filter(is_active=(is_active.lower() == 'true'))
    
    # Paginate
    structures_page, paginator = paginate_queryset(request, structures, per_page=20)
    
    # Calculate stats
    total = structures.count()
    
    stats = {
        'total': total,
        'active': structures.filter(is_active=True).count(),
        'standard': structures.filter(structure_type='STANDARD').count(),
        'boarder': structures.filter(structure_type='BOARDER').count(),
        'day_scholar': structures.filter(structure_type='DAY_SCHOLAR').count(),
        'scholarship': structures.filter(structure_type='SCHOLARSHIP').count(),
        'with_late_fees': structures.filter(charges_late_fee=True).count(),
    }
    
    return render(request, 'fees/structures/_structure_results.html', {
        'structures_page': structures_page,
        'stats': stats,
    })


# =============================================================================
# FEE INVOICE SEARCH
# =============================================================================

def fee_invoice_search(request):
    """HTMX-compatible fee invoice search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'status', 'academic_session', 'fiscal_period',
        'start_date', 'end_date', 'student', 'fee_structure',
        'has_scholarships', 'has_discounts', 'is_overdue'
    ])
    
    query = filters['q']
    status = filters['status']
    academic_session = filters['academic_session']
    fiscal_period = filters['fiscal_period']
    start_date = filters['start_date']
    end_date = filters['end_date']
    student = filters['student']
    fee_structure = filters['fee_structure']
    has_scholarships = filters['has_scholarships']
    has_discounts = filters['has_discounts']
    is_overdue = filters['is_overdue']
    
    # Build queryset
    invoices = FeeInvoice.objects.select_related(
        'student',
        'academic_session',
        'fiscal_period',
        'fee_structure'
    ).prefetch_related(
        'items__fee_category',
        'payments'
    ).annotate(
        payment_count=Count('payments', distinct=True),
        item_count=Count('items', distinct=True)
    ).order_by('-issue_date', '-created_at')
    
    # Apply text search
    if query:
        invoices = invoices.filter(
            Q(invoice_number__icontains=query) |
            Q(student__first_name__icontains=query) |
            Q(student__last_name__icontains=query) |
            Q(student__admission_number__icontains=query)
        )
    
    # Apply filters
    if status:
        invoices = invoices.filter(status=status)
    
    if academic_session:
        invoices = invoices.filter(academic_session_id=academic_session)
    
    if fiscal_period:
        invoices = invoices.filter(fiscal_period_id=fiscal_period)
    
    if student:
        invoices = invoices.filter(student_id=student)
    
    if fee_structure:
        invoices = invoices.filter(fee_structure_id=fee_structure)
    
    if start_date:
        invoices = invoices.filter(issue_date__gte=start_date)
    
    if end_date:
        invoices = invoices.filter(issue_date__lte=end_date)
    
    if has_scholarships and has_scholarships.lower() == 'true':
        invoices = invoices.filter(has_scholarships_applied=True)
    
    if has_discounts and has_discounts.lower() == 'true':
        invoices = invoices.filter(has_discounts_applied=True)
    
    if is_overdue and is_overdue.lower() == 'true':
        today = timezone.now().date()
        invoices = invoices.filter(
            due_date__lt=today,
            status__in=['PENDING', 'PARTIALLY_PAID', 'OVERDUE']
        )
    
    # Paginate
    invoices_page, paginator = paginate_queryset(request, invoices, per_page=20)
    
    # Calculate stats
    total = invoices.count()
    today = timezone.now().date()
    
    stats = {
        'total': total,
        'pending': invoices.filter(status='PENDING').count(),
        'partially_paid': invoices.filter(status='PARTIALLY_PAID').count(),
        'paid': invoices.filter(status='PAID').count(),
        'overdue': invoices.filter(
            due_date__lt=today,
            status__in=['PENDING', 'PARTIALLY_PAID', 'OVERDUE']
        ).count(),
        'total_amount': invoices.aggregate(Sum('total_amount'))['total_amount__sum'] or 0,
        'total_paid': invoices.aggregate(Sum('paid_amount'))['paid_amount__sum'] or 0,
        'total_balance': invoices.aggregate(Sum('balance'))['balance__sum'] or 0,
        'with_scholarships': invoices.filter(has_scholarships_applied=True).count(),
        'with_discounts': invoices.filter(has_discounts_applied=True).count(),
    }
    
    return render(request, 'fees/invoices/_invoice_results.html', {
        'invoices_page': invoices_page,
        'stats': stats,
    })


# =============================================================================
# PAYMENT SEARCH
# =============================================================================

def payment_search(request):
    """HTMX-compatible payment search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'status', 'payment_method', 'academic_session', 'fiscal_period',
        'start_date', 'end_date', 'student', 'invoice', 'is_verified',
        'min_amount', 'max_amount'
    ])
    
    query = filters['q']
    status = filters['status']
    payment_method = filters['payment_method']
    academic_session = filters['academic_session']
    fiscal_period = filters['fiscal_period']
    start_date = filters['start_date']
    end_date = filters['end_date']
    student = filters['student']
    invoice = filters['invoice']
    is_verified = filters['is_verified']
    min_amount = filters['min_amount']
    max_amount = filters['max_amount']
    
    # Build queryset
    payments = Payment.objects.select_related(
        'student',
        'invoice',
        'payment_method',
        'academic_session',
        'fiscal_period'
    ).order_by('-payment_date', '-created_at')
    
    # Apply text search
    if query:
        payments = payments.filter(
            Q(payment_number__icontains=query) |
            Q(receipt_number__icontains=query) |
            Q(reference_number__icontains=query) |
            Q(transaction_id__icontains=query) |
            Q(student__first_name__icontains=query) |
            Q(student__last_name__icontains=query) |
            Q(student__admission_number__icontains=query) |
            Q(paid_by_name__icontains=query)
        )
    
    # Apply filters
    if status:
        payments = payments.filter(status=status)
    
    if payment_method:
        payments = payments.filter(payment_method_id=payment_method)
    
    if academic_session:
        payments = payments.filter(academic_session_id=academic_session)
    
    if fiscal_period:
        payments = payments.filter(fiscal_period_id=fiscal_period)
    
    if student:
        payments = payments.filter(student_id=student)
    
    if invoice:
        payments = payments.filter(invoice_id=invoice)
    
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
        'completed': payments.filter(status='COMPLETED').count(),
        'pending': payments.filter(status='PENDING').count(),
        'failed': payments.filter(status='FAILED').count(),
        'verified': payments.filter(is_verified=True).count(),
        'unverified': payments.filter(is_verified=False).count(),
        'total_amount': payments.filter(status='COMPLETED').aggregate(
            Sum('amount'))['amount__sum'] or 0,
        'total_overpayment': payments.aggregate(
            Sum('overpayment_amount'))['overpayment_amount__sum'] or 0,
        'avg_payment': payments.filter(status='COMPLETED').aggregate(
            Avg('amount'))['amount__avg'] or 0,
    }
    
    return render(request, 'fees/payments/_payment_results.html', {
        'payments_page': payments_page,
        'stats': stats,
    })


# =============================================================================
# SCHOLARSHIP PROGRAM SEARCH
# =============================================================================

def scholarship_program_search(request):
    """HTMX-compatible scholarship program search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'scholarship_type', 'discount_type', 'is_active',
        'is_accepting_applications', 'academic_session'
    ])
    
    query = filters['q']
    scholarship_type = filters['scholarship_type']
    discount_type = filters['discount_type']
    is_active = filters['is_active']
    is_accepting_applications = filters['is_accepting_applications']
    academic_session = filters['academic_session']
    
    # Build queryset
    programs = ScholarshipProgram.objects.prefetch_related(
        'applicable_fee_categories',
        'applicable_levels',
        'valid_sessions'
    ).annotate(
        application_count=Count('applications', distinct=True),
        active_scholarship_count=Count('student_scholarships', 
            filter=Q(student_scholarships__status='ACTIVE'), 
            distinct=True)
    ).order_by('name')
    
    # Apply text search
    if query:
        programs = programs.filter(
            Q(name__icontains=query) |
            Q(code__icontains=query) |
            Q(description__icontains=query) |
            Q(sponsor_name__icontains=query)
        )
    
    # Apply filters
    if scholarship_type:
        programs = programs.filter(scholarship_type=scholarship_type)
    
    if discount_type:
        programs = programs.filter(discount_type=discount_type)
    
    if academic_session:
        programs = programs.filter(valid_sessions__id=academic_session)
    
    if is_active is not None:
        programs = programs.filter(is_active=(is_active.lower() == 'true'))
    
    if is_accepting_applications is not None:
        programs = programs.filter(
            is_accepting_applications=(is_accepting_applications.lower() == 'true')
        )
    
    # Paginate
    programs_page, paginator = paginate_queryset(request, programs, per_page=20)
    
    # Calculate stats
    total = programs.count()
    
    stats = {
        'total': total,
        'active': programs.filter(is_active=True).count(),
        'accepting_applications': programs.filter(is_accepting_applications=True).count(),
        'total_budget': programs.aggregate(Sum('total_budget_amount'))['total_budget_amount__sum'] or 0,
        'total_used': programs.aggregate(Sum('current_budget_used'))['current_budget_used__sum'] or 0,
        'total_recipients': programs.aggregate(Sum('current_recipient_count'))['current_recipient_count__sum'] or 0,
        'academic_merit': programs.filter(scholarship_type='ACADEMIC_MERIT').count(),
        'need_based': programs.filter(scholarship_type='NEED_BASED').count(),
        'full_scholarship': programs.filter(scholarship_type='FULL_SCHOLARSHIP').count(),
    }
    
    return render(request, 'fees/scholarships/_program_results.html', {
        'programs_page': programs_page,
        'stats': stats,
    })


# =============================================================================
# SCHOLARSHIP APPLICATION SEARCH
# =============================================================================

def scholarship_application_search(request):
    """HTMX-compatible scholarship application search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'status', 'scholarship_program', 'academic_session',
        'student', 'start_date', 'end_date'
    ])
    
    query = filters['q']
    status = filters['status']
    scholarship_program = filters['scholarship_program']
    academic_session = filters['academic_session']
    student = filters['student']
    start_date = filters['start_date']
    end_date = filters['end_date']
    
    # Build queryset
    applications = StudentScholarshipApplication.objects.select_related(
        'student',
        'scholarship_program',
        'academic_session'
    ).order_by('-application_date')
    
    # Apply text search
    if query:
        applications = applications.filter(
            Q(application_number__icontains=query) |
            Q(student__first_name__icontains=query) |
            Q(student__last_name__icontains=query) |
            Q(student__admission_number__icontains=query)
        )
    
    # Apply filters
    if status:
        applications = applications.filter(status=status)
    
    if scholarship_program:
        applications = applications.filter(scholarship_program_id=scholarship_program)
    
    if academic_session:
        applications = applications.filter(academic_session_id=academic_session)
    
    if student:
        applications = applications.filter(student_id=student)
    
    if start_date:
        applications = applications.filter(application_date__gte=start_date)
    
    if end_date:
        applications = applications.filter(application_date__lte=end_date)
    
    # Paginate
    applications_page, paginator = paginate_queryset(request, applications, per_page=20)
    
    # Calculate stats
    total = applications.count()
    
    stats = {
        'total': total,
        'submitted': applications.filter(status='SUBMITTED').count(),
        'under_review': applications.filter(status='UNDER_REVIEW').count(),
        'approved': applications.filter(status='APPROVED').count(),
        'rejected': applications.filter(status='REJECTED').count(),
        'waitlisted': applications.filter(status='WAITLISTED').count(),
        'total_requested': applications.aggregate(
            Sum('requested_amount'))['requested_amount__sum'] or 0,
        'total_approved': applications.filter(status='APPROVED').aggregate(
            Sum('approved_amount'))['approved_amount__sum'] or 0,
    }
    
    return render(request, 'fees/scholarships/_application_results.html', {
        'applications_page': applications_page,
        'stats': stats,
    })


# =============================================================================
# STUDENT SCHOLARSHIP SEARCH
# =============================================================================

def student_scholarship_search(request):
    """HTMX-compatible student scholarship search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'status', 'scholarship_program', 'student',
        'distribution_method', 'is_renewable'
    ])
    
    query = filters['q']
    status = filters['status']
    scholarship_program = filters['scholarship_program']
    student = filters['student']
    distribution_method = filters['distribution_method']
    is_renewable = filters['is_renewable']
    
    # Build queryset
    scholarships = StudentScholarship.objects.select_related(
        'student',
        'scholarship_program',
        'application'
    ).annotate(
        remaining_amount=F('amount_awarded') - F('total_amount_used')
    ).order_by('-awarded_date')
    
    # Apply text search
    if query:
        scholarships = scholarships.filter(
            Q(student__first_name__icontains=query) |
            Q(student__last_name__icontains=query) |
            Q(student__admission_number__icontains=query) |
            Q(scholarship_program__name__icontains=query)
        )
    
    # Apply filters
    if status:
        scholarships = scholarships.filter(status=status)
    
    if scholarship_program:
        scholarships = scholarships.filter(scholarship_program_id=scholarship_program)
    
    if student:
        scholarships = scholarships.filter(student_id=student)
    
    if distribution_method:
        scholarships = scholarships.filter(distribution_method=distribution_method)
    
    if is_renewable is not None:
        scholarships = scholarships.filter(is_renewable=(is_renewable.lower() == 'true'))
    
    # Paginate
    scholarships_page, paginator = paginate_queryset(request, scholarships, per_page=20)
    
    # Calculate stats
    total = scholarships.count()
    
    stats = {
        'total': total,
        'active': scholarships.filter(status='ACTIVE').count(),
        'suspended': scholarships.filter(status='SUSPENDED').count(),
        'completed': scholarships.filter(status='COMPLETED').count(),
        'total_awarded': scholarships.aggregate(
            Sum('amount_awarded'))['amount_awarded__sum'] or 0,
        'total_used': scholarships.aggregate(
            Sum('total_amount_used'))['total_amount_used__sum'] or 0,
        'total_remaining': scholarships.aggregate(
            Sum('remaining_amount'))['remaining_amount__sum'] or 0,
        'renewable': scholarships.filter(is_renewable=True).count(),
    }
    
    return render(request, 'fees/scholarships/_scholarship_results.html', {
        'scholarships_page': scholarships_page,
        'stats': stats,
    })


# =============================================================================
# DISCOUNT SEARCH
# =============================================================================

def discount_search(request):
    """HTMX-compatible discount search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'discount_type', 'eligibility_criteria', 'is_active',
        'academic_session', 'auto_apply', 'can_combine'
    ])
    
    query = filters['q']
    discount_type = filters['discount_type']
    eligibility_criteria = filters['eligibility_criteria']
    is_active = filters['is_active']
    academic_session = filters['academic_session']
    auto_apply = filters['auto_apply']
    can_combine = filters['can_combine']
    
    # Build queryset
    discounts = FeesDiscount.objects.prefetch_related(
        'applicable_categories',
        'applicable_structures'
    ).annotate(
        application_count=Count('applications', distinct=True)
    ).order_by('priority', 'name')
    
    # Apply text search
    if query:
        discounts = discounts.filter(
            Q(name__icontains=query) |
            Q(code__icontains=query) |
            Q(description__icontains=query)
        )
    
    # Apply filters
    if discount_type:
        discounts = discounts.filter(discount_type=discount_type)
    
    if eligibility_criteria:
        discounts = discounts.filter(eligibility_criteria=eligibility_criteria)
    
    if academic_session:
        discounts = discounts.filter(academic_session_id=academic_session)
    
    if is_active is not None:
        discounts = discounts.filter(is_active=(is_active.lower() == 'true'))
    
    if auto_apply is not None:
        discounts = discounts.filter(auto_apply=(auto_apply.lower() == 'true'))
    
    if can_combine is not None:
        discounts = discounts.filter(
            can_combine_with_other_discounts=(can_combine.lower() == 'true')
        )
    
    # Paginate
    discounts_page, paginator = paginate_queryset(request, discounts, per_page=20)
    
    # Calculate stats
    total = discounts.count()
    
    stats = {
        'total': total,
        'active': discounts.filter(is_active=True).count(),
        'auto_apply': discounts.filter(auto_apply=True).count(),
        'percentage': discounts.filter(discount_type='PERCENTAGE').count(),
        'fixed': discounts.filter(discount_type='FIXED').count(),
        'waiver': discounts.filter(discount_type='WAIVER').count(),
        'total_budget': discounts.aggregate(
            Sum('budget_limit'))['budget_limit__sum'] or 0,
        'total_used': discounts.aggregate(
            Sum('current_budget_used'))['current_budget_used__sum'] or 0,
    }
    
    return render(request, 'fees/discounts/_discount_results.html', {
        'discounts_page': discounts_page,
        'stats': stats,
    })


# =============================================================================
# REFUND SEARCH
# =============================================================================

def refund_search(request):
    """HTMX-compatible refund search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'status', 'refund_type', 'student', 'academic_session',
        'fiscal_period', 'start_date', 'end_date', 'min_amount', 'max_amount'
    ])
    
    query = filters['q']
    status = filters['status']
    refund_type = filters['refund_type']
    student = filters['student']
    academic_session = filters['academic_session']
    fiscal_period = filters['fiscal_period']
    start_date = filters['start_date']
    end_date = filters['end_date']
    min_amount = filters['min_amount']
    max_amount = filters['max_amount']
    
    # Build queryset
    refunds = Refund.objects.select_related(
        'student',
        'invoice',
        'payment',
        'academic_session',
        'fiscal_period',
        'payment_method'
    ).order_by('-requested_date')
    
    # Apply text search
    if query:
        refunds = refunds.filter(
            Q(refund_number__icontains=query) |
            Q(student__first_name__icontains=query) |
            Q(student__last_name__icontains=query) |
            Q(student__admission_number__icontains=query) |
            Q(transaction_id__icontains=query)
        )
    
    # Apply filters
    if status:
        refunds = refunds.filter(status=status)
    
    if refund_type:
        refunds = refunds.filter(refund_type=refund_type)
    
    if student:
        refunds = refunds.filter(student_id=student)
    
    if academic_session:
        refunds = refunds.filter(academic_session_id=academic_session)
    
    if fiscal_period:
        refunds = refunds.filter(fiscal_period_id=fiscal_period)
    
    if start_date:
        refunds = refunds.filter(requested_date__gte=start_date)
    
    if end_date:
        refunds = refunds.filter(requested_date__lte=end_date)
    
    if min_amount:
        try:
            refunds = refunds.filter(amount__gte=Decimal(min_amount))
        except:
            pass
    
    if max_amount:
        try:
            refunds = refunds.filter(amount__lte=Decimal(max_amount))
        except:
            pass
    
    # Paginate
    refunds_page, paginator = paginate_queryset(request, refunds, per_page=20)
    
    # Calculate stats
    total = refunds.count()
    
    stats = {
        'total': total,
        'requested': refunds.filter(status='REQUESTED').count(),
        'under_review': refunds.filter(status='UNDER_REVIEW').count(),
        'approved': refunds.filter(status='APPROVED').count(),
        'rejected': refunds.filter(status='REJECTED').count(),
        'completed': refunds.filter(status='COMPLETED').count(),
        'total_amount': refunds.aggregate(Sum('amount'))['amount__sum'] or 0,
        'total_approved': refunds.filter(status__in=['APPROVED', 'PROCESSING', 'COMPLETED']).aggregate(
            Sum('approved_amount'))['approved_amount__sum'] or 0,
        'overpayment': refunds.filter(refund_type='OVERPAYMENT').count(),
        'withdrawal': refunds.filter(refund_type='WITHDRAWAL').count(),
    }
    
    return render(request, 'fees/refunds/_refund_results.html', {
        'refunds_page': refunds_page,
        'stats': stats,
    })


# =============================================================================
# QUICK STATS ENDPOINTS (for dashboard widgets)
# =============================================================================

@require_http_methods(["GET"])
def invoice_quick_stats(request):
    """Get quick statistics for invoices"""
    
    today = timezone.now().date()
    
    stats = {
        'total': FeeInvoice.objects.count(),
        'pending': FeeInvoice.objects.filter(status='PENDING').count(),
        'paid': FeeInvoice.objects.filter(status='PAID').count(),
        'overdue': FeeInvoice.objects.filter(
            due_date__lt=today,
            status__in=['PENDING', 'PARTIALLY_PAID', 'OVERDUE']
        ).count(),
        'total_outstanding': FeeInvoice.objects.filter(
            status__in=['PENDING', 'PARTIALLY_PAID', 'OVERDUE']
        ).aggregate(Sum('balance'))['balance__sum'] or 0,
    }
    
    return JsonResponse(stats)


@require_http_methods(["GET"])
def payment_quick_stats(request):
    """Get quick statistics for payments"""
    
    today = timezone.now().date()
    
    stats = {
        'total': Payment.objects.filter(status='COMPLETED').count(),
        'today': Payment.objects.filter(
            payment_date=today,
            status='COMPLETED'
        ).count(),
        'this_month': Payment.objects.filter(
            payment_date__month=today.month,
            payment_date__year=today.year,
            status='COMPLETED'
        ).count(),
        'unverified': Payment.objects.filter(
            is_verified=False,
            status='COMPLETED'
        ).count(),
        'total_amount': Payment.objects.filter(status='COMPLETED').aggregate(
            Sum('amount'))['amount__sum'] or 0,
    }
    
    return JsonResponse(stats)


@require_http_methods(["GET"])
def scholarship_quick_stats(request):
    """Get quick statistics for scholarships"""
    
    stats = {
        'total_programs': ScholarshipProgram.objects.filter(is_active=True).count(),
        'active_scholarships': StudentScholarship.objects.filter(status='ACTIVE').count(),
        'pending_applications': StudentScholarshipApplication.objects.filter(
            status__in=['SUBMITTED', 'UNDER_REVIEW']
        ).count(),
        'total_awarded': StudentScholarship.objects.filter(
            status='ACTIVE'
        ).aggregate(Sum('amount_awarded'))['amount_awarded__sum'] or 0,
        'total_used': StudentScholarship.objects.filter(
            status='ACTIVE'
        ).aggregate(Sum('total_amount_used'))['total_amount_used__sum'] or 0,
    }
    
    return JsonResponse(stats)