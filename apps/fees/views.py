# fees/views.py

"""
Fees Management Views

Comprehensive view functions for:
- Fee Dashboard and Analytics
- Student Accounts Management
- Fee Invoices (CRUD + Bulk Generation)
- Payments (CRUD + Verification)
- Scholarships (Programs, Applications, Awards)
- Discounts Management
- Refunds Processing
- Fee Categories and Structures
- Display Groups
- Reports and Exports

All views delegate business logic to services.py
Uses SweetAlert2 for all notifications via Django messages
Uses core.utils for timezone-aware operations
Follows the same patterns as loans/views.py
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.contrib import messages
from django.db.models import Q, Count, Sum, Avg, F, Max, Min, Prefetch
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from django.db import transaction
from django.views.decorators.http import require_http_methods
from datetime import timedelta, date, datetime
from decimal import Decimal, InvalidOperation
import logging

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings

from .models import (
    DisplayGroup,
    FeesCategory,
    FeesStructure,
    FeesStructureItem,
    FeesStructureBillingSplit,
    FeeInvoice,
    FeeInvoiceItem,
    Payment,
    ScholarshipProgram,
    StudentScholarship,
    StudentScholarshipApplication,
    ScholarshipApplicationLog,
    FeesDiscount,
    DiscountApplication,
    Refund,
    StudentAccount,
    AccountTransaction,
)

from .forms import (
    # Display Group Forms
    DisplayGroupForm,
    DisplayGroupFilterForm,
    
    # Fee Category Forms
    FeesCategoryForm,
    FeesCategoryFilterForm,
    
    # Fee Structure Forms
    FeesStructureForm,
    FeesStructureItemForm,
    FeesStructureFilterForm,
    
    # Invoice Forms
    FeeInvoiceForm,
    FeeInvoiceItemForm,
    FeeInvoiceFilterForm,
    BulkInvoiceGenerationForm,
    InvoiceVoidForm,
    
    # Payment Forms
    PaymentForm,
    MultipleInvoicePaymentForm,
    PaymentReversalForm,
    PaymentRefundForm,
    PaymentFilterForm,
    BulkPaymentVerificationForm,
    
    # Scholarship Forms
    ScholarshipProgramForm,
    ScholarshipProgramFilterForm,
    StudentScholarshipForm,
    StudentScholarshipFilterForm,
    StudentScholarshipApplicationForm,
    ScholarshipApplicationFilterForm,
    ScholarshipApplicationApprovalForm,
    
    # Discount Forms
    FeesDiscountForm,
    FeesDiscountFilterForm,
    
    # Refund Forms
    RefundForm,
    RefundFilterForm,
    
    # Student Account Forms
    StudentAccountForm,
    StudentAccountFilterForm,
    StudentAccountAdjustmentForm,
    FeeInvoiceEditForm,
    FeeInvoiceItemFormSet,
    InvoiceItemQuickEditForm,
    InvoiceAddItemForm
)

from core.utils import (
    get_school_today,
    get_school_current_time,
    get_school_timezone,
    localize_datetime,
    get_active_academic_session,
    format_money,
    calculate_percentage,
    validate_date_range,
    paginate_queryset,
    parse_filters,
)

from core.models import FiscalPeriod
from students.models import Student
from academics.models import AcademicSession, AcademicLevel, Class

from fees.invoice_generators import UnifiedStudentInvoiceGenerator

# Import stats functions
from . import stats as fees_stats

# Import wizard forms
from .wizard_forms import (
    FeesStructureBasicForm,
    BillingScheduleFormSet,
    FeeItemFormSet,
    StructureConfirmationForm,
    FEE_STRUCTURE_WIZARD_FORMS,
    FEE_STRUCTURE_STEP_NAMES,
    validate_billing_splits_total,
    get_fee_structure_summary,
)

# Import form tools for wizard
from formtools.wizard.views import SessionWizardView
from django.core.files.storage import FileSystemStorage

logger = logging.getLogger(__name__)


# =============================================================================
# DASHBOARD
# =============================================================================

@login_required
def fees_dashboard(request):
    """Main fees dashboard with overview statistics"""
    
    try:
        # Get current session
        current_session = get_active_academic_session()
        
        # Get comprehensive financial dashboard
        dashboard_data = fees_stats.get_financial_dashboard(
            academic_session_id=current_session.id if current_session else None
        )
        
        # Get detailed statistics
        account_stats = fees_stats.get_student_account_statistics()
        invoice_stats = fees_stats.get_invoice_statistics()
        payment_stats = fees_stats.get_payment_statistics()
        scholarship_stats = fees_stats.get_scholarship_statistics()
        discount_stats = fees_stats.get_discount_statistics()
        
    except Exception as e:
        logger.error(f"Error getting dashboard statistics: {e}")
        dashboard_data = {}
        account_stats = {}
        invoice_stats = {}
        payment_stats = {}
        scholarship_stats = {}
        discount_stats = {}
    
    # Get recent activities
    recent_invoices = FeeInvoice.objects.select_related(
        'student', 'academic_session'
    ).order_by('-created_at')[:10]
    
    recent_payments = Payment.objects.select_related(
        'student', 'invoice', 'payment_method'
    ).order_by('-created_at')[:10]
    
    # Get items needing attention
    today = get_school_today()
    
    overdue_invoices = FeeInvoice.objects.filter(
        due_date__lt=today,
        status__in=['PENDING', 'PARTIALLY_PAID', 'OVERDUE']
    ).select_related('student', 'academic_session').order_by('due_date')[:10]
    
    unverified_payments = Payment.objects.filter(
        is_verified=False,
        status='COMPLETED'
    ).select_related('student', 'payment_method').order_by('-created_at')[:10]
    
    pending_scholarship_applications = StudentScholarshipApplication.objects.filter(
        status='PENDING'
    ).select_related('student', 'scholarship_program').order_by('-application_date')[:10]
    
    accounts_in_debt = StudentAccount.objects.filter(
        current_balance__lt=0
    ).select_related('student').order_by('current_balance')[:10]
    
    context = {
        'dashboard_data': dashboard_data,
        'account_stats': account_stats,
        'invoice_stats': invoice_stats,
        'payment_stats': payment_stats,
        'scholarship_stats': scholarship_stats,
        'discount_stats': discount_stats,
        'current_session': current_session,
        'recent_invoices': recent_invoices,
        'recent_payments': recent_payments,
        'overdue_invoices': overdue_invoices,
        'unverified_payments': unverified_payments,
        'pending_scholarship_applications': pending_scholarship_applications,
        'accounts_in_debt': accounts_in_debt,
    }
    
    return render(request, 'fees/dashboard.html', context)


# =============================================================================
# HELPER FUNCTIONS FOR FILTERING
# =============================================================================

def get_filtered_student_accounts(request):
    """Helper function to get filtered student accounts queryset"""
    accounts = StudentAccount.objects.select_related(
        'student',
        'student__current_academic_level'
    ).annotate(
        calculated_balance=Sum('transactions__amount'),
        transaction_count=Count('transactions', distinct=True)
    ).order_by('calculated_balance', 'student__first_name')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    balance_status = request.GET.get('balance_status', '')
    min_balance = request.GET.get('min_balance', '')
    max_balance = request.GET.get('max_balance', '')
    
    # Apply text search
    if query:
        words = query.strip().split()
        if words:
            combined_q = Q()
            for word in words:
                word_q = (
                    Q(student__first_name__icontains=word) |
                    Q(student__last_name__icontains=word) |
                    Q(student__admission_number__icontains=word)
                )
                combined_q &= word_q
            accounts = accounts.filter(combined_q)
    
    # Apply filters
    if status:
        accounts = accounts.filter(status=status)
    
    if min_balance:
        try:
            accounts = accounts.filter(calculated_balance__gte=Decimal(min_balance))
        except (ValueError, InvalidOperation):
            pass
    
    if max_balance:
        try:
            accounts = accounts.filter(calculated_balance__lte=Decimal(max_balance))
        except (ValueError, InvalidOperation):
            pass
    
    # Apply balance status filter
    if balance_status == 'positive':
        accounts = accounts.filter(calculated_balance__gt=0)
    elif balance_status == 'zero':
        accounts = accounts.filter(calculated_balance=0)
    elif balance_status == 'negative':
        accounts = accounts.filter(calculated_balance__lt=0)
    
    return accounts


def get_filtered_fee_invoices(request):
    """Helper function to get filtered fee invoices queryset"""
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
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    academic_session = request.GET.get('academic_session', '')
    fiscal_period = request.GET.get('fiscal_period', '')
    student = request.GET.get('student', '')
    fee_structure = request.GET.get('fee_structure', '')
    has_scholarships = request.GET.get('has_scholarships', '')
    has_discounts = request.GET.get('has_discounts', '')
    is_overdue = request.GET.get('is_overdue', '')
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')
    min_amount = request.GET.get('min_amount', '')
    max_amount = request.GET.get('max_amount', '')
    
    # Apply text search
    if query:
        words = query.strip().split()
        if words:
            combined_q = Q()
            for word in words:
                word_q = (
                    Q(invoice_number__icontains=word) |
                    Q(student__first_name__icontains=word) |
                    Q(student__middle_name__icontains=word) |
                    Q(student__last_name__icontains=word) |
                    Q(student__admission_number__icontains=word) |
                    Q(notes__icontains=word)
                )
                combined_q &= word_q
            invoices = invoices.filter(combined_q)
    
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
    if has_scholarships and has_scholarships.lower() == 'true':
        invoices = invoices.filter(has_scholarships_applied=True)
    if has_discounts and has_discounts.lower() == 'true':
        invoices = invoices.filter(has_discounts_applied=True)
    if is_overdue and is_overdue.lower() == 'true':
        today = get_school_today()
        invoices = invoices.filter(
            due_date__lt=today,
            status__in=['PENDING', 'PARTIALLY_PAID', 'OVERDUE']
        )
    
    # Apply date filters
    if start_date:
        invoices = invoices.filter(issue_date__gte=start_date)
    if end_date:
        invoices = invoices.filter(issue_date__lte=end_date)
    
    # Apply amount filters
    if min_amount:
        try:
            invoices = invoices.filter(total_amount__gte=Decimal(min_amount))
        except (ValueError, TypeError):
            pass
    if max_amount:
        try:
            invoices = invoices.filter(total_amount__lte=Decimal(max_amount))
        except (ValueError, TypeError):
            pass
    
    return invoices


def get_filtered_payments(request):
    """Helper function to get filtered payments queryset"""
    payments = Payment.objects.select_related(
        'student',
        'invoice',
        'payment_method',
        'academic_session',
        'fiscal_period'
    ).order_by('-payment_date', '-created_at')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    payment_method = request.GET.get('payment_method', '')
    academic_session = request.GET.get('academic_session', '')
    fiscal_period = request.GET.get('fiscal_period', '')
    student = request.GET.get('student', '')
    invoice = request.GET.get('invoice', '')
    is_verified = request.GET.get('is_verified', '')
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')
    min_amount = request.GET.get('min_amount', '')
    max_amount = request.GET.get('max_amount', '')
    
    # Apply text search
    if query:
        words = query.strip().split()
        if words:
            combined_q = Q()
            for word in words:
                word_q = (
                    Q(payment_number__icontains=word) |
                    Q(receipt_number__icontains=word) |
                    Q(reference_number__icontains=word) |
                    Q(transaction_id__icontains=word) |
                    Q(student__first_name__icontains=word) |
                    Q(student__last_name__icontains=word) |
                    Q(paid_by_name__icontains=word)
                )
                combined_q &= word_q
            payments = payments.filter(combined_q)
    
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
    if is_verified:
        payments = payments.filter(is_verified=(is_verified.lower() == 'true'))
    
    # Apply date filters
    if start_date:
        payments = payments.filter(payment_date__gte=start_date)
    if end_date:
        payments = payments.filter(payment_date__lte=end_date)
    
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


def get_filtered_scholarship_programs(request):
    """Helper function to get filtered scholarship programs queryset with category-specific support"""
    programs = ScholarshipProgram.objects.prefetch_related(
        'applicable_fee_categories',
        'applicable_levels',
        'valid_sessions'
    ).annotate(
        application_count=Count('applications', distinct=True),
        active_scholarship_count=Count(
            'student_scholarships',
            filter=Q(student_scholarships__status='ACTIVE'),
            distinct=True
        )
    ).order_by('name')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    scholarship_type = request.GET.get('scholarship_type', '')
    program_type = request.GET.get('program_type', '')  # ⭐ NEW
    discount_type = request.GET.get('discount_type', '')
    is_active = request.GET.get('is_active', '')
    is_accepting_applications = request.GET.get('is_accepting_applications', '')
    academic_session = request.GET.get('academic_session', '')
    
    # Apply text search
    if query:
        words = query.strip().split()
        if words:
            combined_q = Q()
            for word in words:
                word_q = (
                    Q(name__icontains=word) |
                    Q(code__icontains=word) |
                    Q(description__icontains=word) |
                    Q(sponsor_name__icontains=word)
                )
                combined_q &= word_q
            programs = programs.filter(combined_q)
    
    # Apply filters
    if scholarship_type:
        programs = programs.filter(scholarship_type=scholarship_type)
    if program_type:  # ⭐ NEW
        programs = programs.filter(program_type=program_type)
    if discount_type:
        programs = programs.filter(discount_type=discount_type)
    if academic_session:
        programs = programs.filter(valid_sessions__id=academic_session)
    if is_active:
        programs = programs.filter(is_active=(is_active.lower() == 'true'))
    if is_accepting_applications:
        programs = programs.filter(is_accepting_applications=(is_accepting_applications.lower() == 'true'))
    
    return programs

def get_filtered_display_groups(request):
    """Helper function to get filtered display groups queryset"""
    groups = DisplayGroup.objects.annotate(
        category_count=Count('feescategory')
    ).order_by('display_order', 'name')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    is_active = request.GET.get('is_active', '')
    show_as_group = request.GET.get('show_as_group', '')
    
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
            groups = groups.filter(combined_q)
    
    # Apply filters
    if is_active:
        groups = groups.filter(is_active=(is_active.lower() == 'true'))
    
    if show_as_group:
        groups = groups.filter(show_as_group=(show_as_group.lower() == 'true'))
    
    return groups


def get_filtered_fee_categories(request):
    """Helper function to get filtered fee categories queryset"""
    categories = FeesCategory.objects.select_related(
        'display_group'
    ).annotate(
        structure_count=Count('structure_items', distinct=True)
    ).order_by('display_order', 'name')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    category_type = request.GET.get('category_type', '')
    is_active = request.GET.get('is_active', '')
    is_mandatory = request.GET.get('is_mandatory', '')
    is_refundable = request.GET.get('is_refundable', '')
    is_taxable = request.GET.get('is_taxable', '')
    applicability = request.GET.get('applicability', '')
    display_group = request.GET.get('display_group', '')
    frequency = request.GET.get('frequency', '')
    
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
            categories = categories.filter(combined_q)
    
    # Apply filters
    if category_type:
        categories = categories.filter(category_type=category_type)
    if display_group:
        categories = categories.filter(display_group_id=display_group)
    if frequency:
        categories = categories.filter(frequency=frequency)
    if applicability:
        categories = categories.filter(applicability=applicability)
    if is_active:
        categories = categories.filter(is_active=(is_active.lower() == 'true'))
    if is_mandatory:
        categories = categories.filter(is_mandatory=(is_mandatory.lower() == 'true'))
    if is_refundable:
        categories = categories.filter(is_refundable=(is_refundable.lower() == 'true'))
    if is_taxable:
        categories = categories.filter(is_taxable=(is_taxable.lower() == 'true'))
    
    return categories

def get_filtered_fee_structures(request):
    """Helper function to get filtered fee structures queryset"""
    structures = FeesStructure.objects.select_related(
        'academic_year'
    ).prefetch_related(
        'academic_levels',
        'applicable_sessions',
        'applicable_classes',
        'items'
    ).annotate(
        total_amount=Sum('items__amount')
    ).order_by('-created_at')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    structure_type = request.GET.get('structure_type', '')
    academic_year_id = request.GET.get('academic_year', '')
    billing_frequency = request.GET.get('billing_frequency', '')
    boarding_type_filter = request.GET.get('boarding_type_filter', '')
    academic_session_id = request.GET.get('academic_session', '')
    academic_level_id = request.GET.get('academic_level', '')
    is_active = request.GET.get('is_active', '')
    effective_from = request.GET.get('effective_from', '')
    effective_to = request.GET.get('effective_to', '')
    
    # Apply text search
    if query:
        words = query.strip().split()
        if words:
            combined_q = Q()
            for word in words:
                word_q = (
                    Q(name__icontains=word) |
                    Q(description__icontains=word) |
                    Q(academic_year__name__icontains=word)
                )
                combined_q &= word_q
            structures = structures.filter(combined_q)
    
    # Apply filters
    if structure_type:
        structures = structures.filter(structure_type=structure_type)
    if academic_year_id:
        structures = structures.filter(academic_year_id=academic_year_id)
    if billing_frequency:
        structures = structures.filter(billing_frequency=billing_frequency)
    if boarding_type_filter:
        structures = structures.filter(boarding_type_filter=boarding_type_filter)
    if academic_session_id:
        structures = structures.filter(applicable_sessions__id=academic_session_id)
    if academic_level_id:
        structures = structures.filter(academic_levels__id=academic_level_id)
    if is_active:
        if is_active.lower() == 'true':
            structures = structures.filter(is_active=True)
        elif is_active.lower() == 'false':
            structures = structures.filter(is_active=False)
    
    # Date range filters
    if effective_from:
        structures = structures.filter(effective_date__gte=effective_from)
    if effective_to:
        structures = structures.filter(effective_date__lte=effective_to)
    
    # Remove duplicates from M2M filters
    structures = structures.distinct()
    
    return structures

def get_filtered_scholarship_applications(request):
    """Helper function to get filtered scholarship applications queryset"""
    applications = StudentScholarshipApplication.objects.select_related(
        'student',
        'scholarship_program',
        'academic_session'
    ).order_by('-application_date', '-created_at')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    scholarship_program = request.GET.get('scholarship_program', '')
    student = request.GET.get('student', '')
    academic_session = request.GET.get('academic_session', '')
    application_date_from = request.GET.get('application_date_from', '')
    application_date_to = request.GET.get('application_date_to', '')
    min_amount = request.GET.get('min_amount', '')
    max_amount = request.GET.get('max_amount', '')
    
    # Apply text search
    if query:
        words = query.strip().split()
        if words:
            combined_q = Q()
            for word in words:
                word_q = (
                    Q(application_number__icontains=word) |
                    Q(student__first_name__icontains=word) |
                    Q(student__last_name__icontains=word) |
                    Q(student__admission_number__icontains=word) |
                    Q(scholarship_program__name__icontains=word) |
                    Q(scholarship_program__code__icontains=word) |
                    Q(essay__icontains=word) |
                    Q(special_circumstances__icontains=word)
                )
                combined_q &= word_q
            applications = applications.filter(combined_q)
    
    # Apply filters
    if status:
        applications = applications.filter(status=status)
    if scholarship_program:
        applications = applications.filter(scholarship_program_id=scholarship_program)
    if student:
        applications = applications.filter(student_id=student)
    if academic_session:
        applications = applications.filter(academic_session_id=academic_session)
    
    # Apply date filters
    if application_date_from:
        try:
            from_date = datetime.strptime(application_date_from, '%Y-%m-%d').date()
            applications = applications.filter(application_date__gte=from_date)
        except (ValueError, TypeError):
            pass
    
    if application_date_to:
        try:
            to_date = datetime.strptime(application_date_to, '%Y-%m-%d').date()
            applications = applications.filter(application_date__lte=to_date)
        except (ValueError, TypeError):
            pass
    
    # Apply amount filters
    if min_amount:
        try:
            applications = applications.filter(requested_amount__gte=Decimal(min_amount))
        except (ValueError, TypeError):
            pass
    if max_amount:
        try:
            applications = applications.filter(requested_amount__lte=Decimal(max_amount))
        except (ValueError, TypeError):
            pass
    
    return applications


def get_filtered_student_scholarships(request):
    """Helper function to get filtered student scholarships queryset with category-specific support"""
    scholarships = StudentScholarship.objects.select_related(
        'student',
        'scholarship_program',
        'application'
    ).annotate(
        remaining_amount=F('amount_awarded') - F('total_amount_used')
    ).order_by('-awarded_date', '-created_at')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    scholarship_program = request.GET.get('scholarship_program', '')
    program_type = request.GET.get('program_type', '')  # ⭐ NEW
    discount_mode = request.GET.get('discount_mode', '')  # ⭐ NEW
    scholarship_type = request.GET.get('scholarship_type', '')  # ⭐ NEW
    budget_status = request.GET.get('budget_status', '')  # ⭐ NEW
    student = request.GET.get('student', '')
    distribution_method = request.GET.get('distribution_method', '')
    is_renewable = request.GET.get('is_renewable', '')
    academic_session = request.GET.get('academic_session', '')
    active_on_date = request.GET.get('active_on_date', '')  # ⭐ NEW
    
    # Apply text search
    if query:
        words = query.strip().split()
        if words:
            combined_q = Q()
            for word in words:
                word_q = (
                    Q(student__first_name__icontains=word) |
                    Q(student__last_name__icontains=word) |
                    Q(student__admission_number__icontains=word) |
                    Q(scholarship_program__name__icontains=word) |
                    Q(scholarship_program__code__icontains=word)
                )
                combined_q &= word_q
            scholarships = scholarships.filter(combined_q)
    
    # Apply filters
    if status:
        scholarships = scholarships.filter(status=status)
    if scholarship_program:
        scholarships = scholarships.filter(scholarship_program_id=scholarship_program)
    if student:
        scholarships = scholarships.filter(student_id=student)
    if distribution_method:
        scholarships = scholarships.filter(distribution_method=distribution_method)
    if is_renewable:
        scholarships = scholarships.filter(is_renewable=(is_renewable.lower() == 'true'))
    if academic_session:
        scholarships = scholarships.filter(academic_session_id=academic_session)
    
    # ⭐ NEW: Filter by program type
    if program_type:
        scholarships = scholarships.filter(scholarship_program__program_type=program_type)
    
    # ⭐ NEW: Filter by discount mode (global vs category-specific)
    if discount_mode:
        if discount_mode == 'global':
            scholarships = scholarships.filter(use_category_specific_discounts=False)
        elif discount_mode == 'category_specific':
            scholarships = scholarships.filter(use_category_specific_discounts=True)
    
    # ⭐ NEW: Filter by scholarship type (policy vs budget-based)
    if scholarship_type:
        if scholarship_type == 'policy_based':
            scholarships = scholarships.filter(
                scholarship_program__program_type='POLICY_BASED',
                scholarship_program__discount_type__in=['PERCENTAGE', 'FULL_WAIVER']
            )
        elif scholarship_type == 'budget_based':
            scholarships = scholarships.filter(
                scholarship_program__program_type__in=['BUDGETED', 'SPONSORED'],
                amount_awarded__gt=0
            )
    
    # ⭐ NEW: Filter by budget status
    if budget_status:
        if budget_status == 'active':
            # Has balance remaining
            scholarships = scholarships.filter(
                amount_awarded__gt=0,
                total_amount_used__lt=F('amount_awarded')
            )
        elif budget_status == 'exhausted':
            # Budget exhausted
            scholarships = scholarships.filter(
                amount_awarded__gt=0,
                total_amount_used__gte=F('amount_awarded')
            )
        elif budget_status == 'not_applicable':
            # Policy-based (no budget tracking)
            scholarships = scholarships.filter(amount_awarded=0)
    
    # ⭐ NEW: Filter by active on specific date
    if active_on_date:
        try:
            check_date = datetime.strptime(active_on_date, '%Y-%m-%d').date()
            scholarships = scholarships.filter(
                status='ACTIVE',
                start_date__lte=check_date
            ).filter(
                Q(end_date__isnull=True) | Q(end_date__gte=check_date)
            )
        except (ValueError, TypeError):
            pass
    
    return scholarships


def get_filtered_discounts(request):
    """Helper function to get filtered discounts queryset"""
    discounts = FeesDiscount.objects.prefetch_related(
        'applicable_categories',
        'applicable_structures'
    ).annotate(
        application_count=Count('applications', distinct=True)
    ).order_by('priority', 'name')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    discount_type = request.GET.get('discount_type', '')
    eligibility_criteria = request.GET.get('eligibility_criteria', '')
    is_active = request.GET.get('is_active', '')
    academic_session = request.GET.get('academic_session', '')
    auto_apply = request.GET.get('auto_apply', '')
    can_combine = request.GET.get('can_combine', '')
    
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
            discounts = discounts.filter(combined_q)
    
    # Apply filters
    if discount_type:
        discounts = discounts.filter(discount_type=discount_type)
    if eligibility_criteria:
        discounts = discounts.filter(eligibility_criteria=eligibility_criteria)
    if academic_session:
        discounts = discounts.filter(academic_session_id=academic_session)
    if is_active:
        discounts = discounts.filter(is_active=(is_active.lower() == 'true'))
    if auto_apply:
        discounts = discounts.filter(auto_apply=(auto_apply.lower() == 'true'))
    if can_combine:
        discounts = discounts.filter(
            can_combine_with_other_discounts=(can_combine.lower() == 'true')
        )
    
    return discounts


def get_filtered_refunds(request):
    """Helper function to get filtered refunds queryset"""
    refunds = Refund.objects.select_related(
        'student',
        'invoice',
        'payment',
        'academic_session',
        'fiscal_period',
        'payment_method'
    ).order_by('-requested_date', '-created_at')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    refund_type = request.GET.get('refund_type', '')
    student = request.GET.get('student', '')
    academic_session = request.GET.get('academic_session', '')
    fiscal_period = request.GET.get('fiscal_period', '')
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')
    min_amount = request.GET.get('min_amount', '')
    max_amount = request.GET.get('max_amount', '')
    
    # Apply text search
    if query:
        words = query.strip().split()
        if words:
            combined_q = Q()
            for word in words:
                word_q = (
                    Q(refund_number__icontains=word) |
                    Q(student__first_name__icontains=word) |
                    Q(student__last_name__icontains=word) |
                    Q(student__admission_number__icontains=word) |
                    Q(transaction_id__icontains=word)
                )
                combined_q &= word_q
            refunds = refunds.filter(combined_q)
    
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
    
    # Apply date filters
    if start_date:
        refunds = refunds.filter(requested_date__gte=start_date)
    if end_date:
        refunds = refunds.filter(requested_date__lte=end_date)
    
    # Apply amount filters
    if min_amount:
        try:
            refunds = refunds.filter(amount__gte=Decimal(min_amount))
        except (ValueError, TypeError):
            pass
    if max_amount:
        try:
            refunds = refunds.filter(amount__lte=Decimal(max_amount))
        except (ValueError, TypeError):
            pass
    
    return refunds


def get_filtered_account_transactions(request):
    """Helper function to get filtered account transactions queryset"""
    transactions = AccountTransaction.objects.select_related(
        'student_account__student',
        'invoice',
        'payment',
        'academic_session',
        'fiscal_period'
    ).order_by('-created_at')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    transaction_type = request.GET.get('transaction_type', '')
    student_account = request.GET.get('student_account', '')
    academic_session = request.GET.get('academic_session', '')
    fiscal_period = request.GET.get('fiscal_period', '')
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')
    min_amount = request.GET.get('min_amount', '')
    max_amount = request.GET.get('max_amount', '')
    
    # Apply text search
    if query:
        words = query.strip().split()
        if words:
            combined_q = Q()
            for word in words:
                word_q = (
                    Q(description__icontains=word) |
                    Q(reference_number__icontains=word) |
                    Q(student_account__student__first_name__icontains=word) |
                    Q(student_account__student__last_name__icontains=word)
                )
                combined_q &= word_q
            transactions = transactions.filter(combined_q)
    
    # Apply filters
    if transaction_type:
        transactions = transactions.filter(transaction_type=transaction_type)
    if student_account:
        transactions = transactions.filter(student_account_id=student_account)
    if academic_session:
        transactions = transactions.filter(academic_session_id=academic_session)
    if fiscal_period:
        transactions = transactions.filter(fiscal_period_id=fiscal_period)
    
    # Apply date filters
    if start_date:
        transactions = transactions.filter(created_at__gte=start_date)
    if end_date:
        transactions = transactions.filter(created_at__lte=end_date)
    
    # Apply amount filters
    if min_amount:
        try:
            transactions = transactions.filter(amount__gte=Decimal(min_amount))
        except (ValueError, TypeError):
            pass
    if max_amount:
        try:
            transactions = transactions.filter(amount__lte=Decimal(max_amount))
        except (ValueError, TypeError):
            pass
    
    return transactions

# =============================================================================
# STUDENT ACCOUNT VIEWS (CRUD + Print)
# =============================================================================

@login_required
def student_account_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""
    filter_form = StudentAccountFilterForm(request.GET or None)
    accounts = get_filtered_student_accounts(request)
    
    # Calculate statistics
    total_accounts = accounts.count()
    accounts_with_debt = accounts.filter(calculated_balance__lt=0)
    accounts_with_credit = accounts.filter(calculated_balance__gt=0)
    
    stats = {
        'total_accounts': total_accounts,
        'by_status': {
            'active': accounts.filter(status='ACTIVE').count(),
            'suspended': accounts.filter(status='SUSPENDED').count(),
            'frozen': accounts.filter(status='FROZEN').count(),
            'closed': accounts.filter(status='CLOSED').count(),
        },
        'debt_analysis': {
            'total_debtors': accounts_with_debt.count(),
            'total_outstanding': abs(accounts_with_debt.aggregate(total=Sum('calculated_balance'))['total'] or Decimal('0.00')),
            'accounts_with_credit': accounts_with_credit.count(),
            'total_credit': accounts_with_credit.aggregate(total=Sum('calculated_balance'))['total'] or Decimal('0.00'),
            'zero_balance_accounts': accounts.filter(calculated_balance=0).count(),
        },
        'collection_rate': (
            (total_accounts - accounts_with_debt.count()) / total_accounts * 100
            if total_accounts > 0 else 0
        ),
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
        return render(request, 'fees/accounts/partials/_account_results.html', context)
    else:
        return render(request, 'fees/accounts/list.html', context)

@login_required
def student_account_detail(request, pk):
    """View student account details"""
    account = get_object_or_404(
        StudentAccount.objects.select_related('student'),
        pk=pk
    )
    
    # Get transaction history
    transactions = account.transactions.select_related(
        'invoice', 'payment', 'academic_session', 'fiscal_period'
    ).order_by('-created_at')[:50]
    
    # Get related invoices
    invoices = FeeInvoice.objects.filter(
        student=account.student
    ).select_related('academic_session', 'fiscal_period').order_by('-issue_date')[:10]
    
    # Get related payments
    payments = Payment.objects.filter(
        student=account.student
    ).select_related('payment_method', 'invoice').order_by('-payment_date')[:10]
    
    # Get active scholarships
    scholarships = StudentScholarship.objects.filter(
        student=account.student,
        status='ACTIVE'
    ).select_related('scholarship_program')
    
    context = {
        'account': account,
        'transactions': transactions,
        'invoices': invoices,
        'payments': payments,
        'scholarships': scholarships,
    }
    
    return render(request, 'fees/accounts/detail.html', context)

@login_required
def student_account_edit(request, pk):
    """Edit student account"""
    account = get_object_or_404(StudentAccount, pk=pk)
    
    if request.method == 'POST':
        form = StudentAccountForm(request.POST, instance=account)
        if form.is_valid():
            try:
                account = form.save()
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f"Account for {account.student.get_full_name()} updated successfully!"
                    response['HX-Alert-Type'] = 'success'
                    response['HX-Alert-Title'] = 'Updated!'
                    response['HX-Redirect'] = reverse('fees:account_detail', kwargs={'pk': account.pk})
                    return response
                else:
                    messages.success(
                        request,
                        f'Account for {account.student.get_full_name()} updated successfully!',
                        extra_tags='sweetalert'
                    )
                    return redirect('fees:account_detail', pk=account.pk)
                    
            except Exception as e:
                logger.error(f"Error updating account: {e}")
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Error updating account: {str(e)}'
                    response['HX-Alert-Type'] = 'error'
                    response['HX-Alert-Title'] = 'Error!'
                    return response
                else:
                    messages.error(request, f'Error updating account: {str(e)}')
    else:
        form = StudentAccountForm(instance=account)
    
    context = {
        'form': form,
        'account': account,
        'title': f'Edit Account - {account.student.get_full_name()}',
    }
    
    return render(request, 'fees/accounts/form.html', context)

@login_required
@require_http_methods(["POST"])
def student_account_adjust(request, pk):
    """
    Process student account adjustment (manual credit/debit).
    
    Use cases:
    - Write-off bad debt
    - Manual correction
    - Goodwill credit
    - Administrative adjustment
    """
    account = get_object_or_404(StudentAccount, pk=pk)
    
    try:
        adjustment_type = request.POST.get('adjustment_type')  # CREDIT or DEBIT
        amount = Decimal(request.POST.get('amount', '0.00'))
        reason = request.POST.get('reason', '')
        reference = request.POST.get('reference', '')
        
        if amount <= 0:
            raise ValueError("Adjustment amount must be positive")
        
        if not reason:
            raise ValueError("Adjustment reason is required")
        
        with transaction.atomic():
            # Create adjustment transaction
            if adjustment_type == 'CREDIT':
                # Positive amount (reduces debt or adds credit)
                transaction_amount = amount
                description = f"Manual Credit: {reason}"
            else:  # DEBIT
                # Negative amount (adds debt)
                transaction_amount = -amount
                description = f"Manual Debit: {reason}"
            
            # Create transaction
            AccountTransaction.objects.create(
                student_account=account,
                transaction_type='ADJUSTMENT',
                amount=transaction_amount,
                description=description,
                reference_number=reference or f"ADJ-{timezone.now().strftime('%Y%m%d-%H%M%S')}",
                balance_after=account.get_current_balance() + transaction_amount,
                academic_session=get_active_academic_session(),
                fiscal_period=FiscalPeriod.get_current_fiscal_period(),
                processed_by_id=str(request.user.id),
            )
            
            # Create journal entry if applicable
            try:
                from finance.models import JournalEntry, JournalTransaction, Journal
                from finance.utils import generate_journal_entry_number
                from core.models import FinancialSettings
                
                settings_obj = FinancialSettings.get_instance()
                if settings_obj:
                    mappings = settings_obj.get_account_mappings()
                    
                    receivable_account = mappings.student_receivables_account
                    adjustment_account = mappings.get('adjustment_account')  # Configure in settings
                    
                    if receivable_account and adjustment_account:
                        fees_journal, _ = Journal.objects.get_or_create(
                            journal_type='FEES',
                            defaults={'name': 'Fee Collection Journal'}
                        )
                        
                        journal_entry = JournalEntry.objects.create(
                            journal=fees_journal,
                            entry_number=generate_journal_entry_number(fees_journal),
                            entry_date=get_school_today(),
                            fiscal_period=FiscalPeriod.get_current_fiscal_period(),
                            description=description,
                            reference_number=reference,
                            status='POSTED',
                        )
                        
                        if adjustment_type == 'CREDIT':
                            # DEBIT: Adjustment Account (expense/loss)
                            JournalTransaction.objects.create(
                                journal_entry=journal_entry,
                                account=adjustment_account,
                                amount=amount,
                                is_debit=True,
                                description=description,
                            )
                            # CREDIT: Accounts Receivable (reduce asset)
                            JournalTransaction.objects.create(
                                journal_entry=journal_entry,
                                account=receivable_account,
                                amount=amount,
                                is_debit=False,
                                description=f"Adjustment for {account.student.get_full_name()}",
                            )
                        else:  # DEBIT
                            # DEBIT: Accounts Receivable (increase asset)
                            JournalTransaction.objects.create(
                                journal_entry=journal_entry,
                                account=receivable_account,
                                amount=amount,
                                is_debit=True,
                                description=f"Adjustment for {account.student.get_full_name()}",
                            )
                            # CREDIT: Adjustment Account
                            JournalTransaction.objects.create(
                                journal_entry=journal_entry,
                                account=adjustment_account,
                                amount=amount,
                                is_debit=False,
                                description=description,
                            )
            
            except Exception as e:
                logger.error(f"Error creating adjustment journal entry: {e}", exc_info=True)
                # Don't fail the adjustment if journal fails
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Account adjustment of {amount:,.2f} processed successfully!"
            response['HX-Alert-Type'] = 'success'
            response['HX-Alert-Title'] = 'Adjustment Applied'
            response['HX-Redirect'] = reverse('fees:account_detail', kwargs={'pk': account.pk})
            return response
        else:
            messages.success(
                request,
                f"Account adjustment of {amount:,.2f} processed successfully!"
            )
            return redirect('fees:account_detail', pk=account.pk)
    
    except Exception as e:
        logger.error(f"Error processing account adjustment: {e}", exc_info=True)
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f'Error processing adjustment: {str(e)}'
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Error'
            return response
        else:
            messages.error(request, f'Error processing adjustment: {str(e)}')
            return redirect('fees:account_detail', pk=account.pk)
        
@login_required
def student_account_list_print_view(request):
    """
    Generate printable list of student accounts with filters.
    
    Supports:
    - All list filters (status, balance_status, etc.)
    - Custom field selection
    - Summary statistics
    - Landscape/portrait orientation
    - Optional recent transaction history per account
    """
    
    # Get filtered accounts using the same helper function as the list view
    accounts = get_filtered_student_accounts(request)
    
    # Get selected fields from request
    selected_fields = request.GET.getlist('fields')
    if not selected_fields:
        # Default fields if none selected
        selected_fields = [
            'admission_number',
            'student_name',
            'current_balance',
            'total_charged',
            'total_paid',
            'status'
        ]
    
    # Get print options
    include_stats = request.GET.get('include_stats', 'true').lower() == 'true'
    landscape = request.GET.get('landscape', 'false').lower() == 'true'
    show_transactions = request.GET.get('show_transactions', 'false').lower() == 'true'
    direct_print = request.GET.get('direct_print', 'false').lower() == 'true'
    
    # Limit results for performance (optional)
    max_records = 500
    if accounts.count() > max_records:
        messages.warning(
            request,
            f'Only the first {max_records} accounts will be printed. Please apply filters to reduce the result set.'
        )
        accounts = accounts[:max_records]
    
    # Calculate statistics if requested
    stats = None
    if include_stats:
        total_accounts = accounts.count()
        accounts_with_debt = accounts.filter(calculated_balance__lt=0)
        accounts_with_credit = accounts.filter(calculated_balance__gt=0)
        
        stats = {
            'total_accounts': total_accounts,
            'by_status': {
                'active': accounts.filter(status='ACTIVE').count(),
                'suspended': accounts.filter(status='SUSPENDED').count(),
                'frozen': accounts.filter(status='FROZEN').count(),
                'closed': accounts.filter(status='CLOSED').count(),
            },
            'debt_analysis': {
                'total_debtors': accounts_with_debt.count(),
                'total_outstanding': abs(accounts_with_debt.aggregate(
                    total=Sum('calculated_balance')
                )['total'] or Decimal('0.00')),
                'accounts_with_credit': accounts_with_credit.count(),
                'total_credit': accounts_with_credit.aggregate(
                    total=Sum('calculated_balance')
                )['total'] or Decimal('0.00'),
                'zero_balance_accounts': accounts.filter(calculated_balance=0).count(),
            },
            'collection_rate': (
                (total_accounts - accounts_with_debt.count()) / total_accounts * 100
                if total_accounts > 0 else 0
            ),
        }
    
    # Get recent transactions if requested
    transactions_by_account = {}
    if show_transactions:
        for account in accounts:
            transactions_by_account[account.pk] = account.transactions.select_related(
                'invoice', 'payment', 'academic_session'
            ).order_by('-created_at')[:5]
    
    # Field name mapping for display
    field_names = {
        'admission_number': 'Admission Number',
        'student_name': 'Student Name',
        'current_class': 'Current Class',
        'contact': 'Contact Information',
        'current_balance': 'Current Balance',
        'total_charged': 'Total Fees Charged',
        'total_paid': 'Total Payments',
        'credit_limit': 'Credit Limit',
        'status': 'Account Status',
        'last_transaction': 'Last Transaction Date',
        'last_payment': 'Last Payment Date',
    }
    
    selected_field_names = [
        field_names.get(field, field.replace('_', ' ').title()) 
        for field in selected_fields
    ]
    
    # Get current filters for display
    filter_form = StudentAccountFilterForm(request.GET)
    active_filters = {}
    if filter_form.is_valid():
        for field_name, field_value in filter_form.cleaned_data.items():
            if field_value:
                if field_name == 'q':
                    active_filters['Search'] = field_value
                elif field_name == 'status':
                    active_filters['Status'] = dict(filter_form.fields['status'].choices).get(field_value, field_value)
                elif field_name == 'balance_status':
                    active_filters['Balance Status'] = dict(filter_form.fields['balance_status'].choices).get(field_value, field_value)
                elif field_name == 'min_balance':
                    active_filters['Min Balance'] = f"{field_value:,.2f}"
                elif field_name == 'max_balance':
                    active_filters['Max Balance'] = f"{field_value:,.2f}"
    
    context = {
        'accounts': accounts,
        'stats': stats,
        'transactions_by_account': transactions_by_account,
        'selected_fields': selected_fields,
        'selected_field_names': selected_field_names,
        'field_names': field_names,
        'include_stats': include_stats,
        'landscape': landscape,
        'show_transactions': show_transactions,
        'direct_print': direct_print,
        'active_filters': active_filters,
        'now': timezone.now(),
        'title': 'Student Accounts Report',
        'print_date': get_school_today(),
        'printed_by': request.user.get_full_name() if request.user.get_full_name() else request.user.username,
    }
    
    return render(request, 'fees/accounts/print_list.html', context)

@login_required
def student_account_print_view(request):
    """Generate printable student account statement"""
    
    selected_fields = request.GET.getlist('fields')
    if not selected_fields:
        selected_fields = ['created_at', 'description', 'reference_number', 'amount', 'balance_after']
    
    account_id = request.GET.get('account_id')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    include_summary = request.GET.get('include_summary') == 'true'
    
    if not account_id:
        messages.error(request, 'No account specified')
        return redirect('fees:account_list')
    
    account = get_object_or_404(StudentAccount, pk=account_id)
    
    # Build transaction queryset
    transactions = account.transactions.select_related(
        'invoice', 'payment', 'academic_session'
    ).order_by('-created_at')
    
    # Apply date filters
    if date_from:
        transactions = transactions.filter(created_at__gte=date_from)
    if date_to:
        transactions = transactions.filter(created_at__lte=date_to)
    
    # Calculate opening balance
    if date_from:
        opening_transactions = account.transactions.filter(
            created_at__lt=date_from
        ).aggregate(Sum('amount'))
        opening_balance = opening_transactions['amount__sum'] or Decimal('0.00')
    else:
        opening_balance = Decimal('0.00')
    
    # Calculate summary
    summary = None
    if include_summary:
        summary = {
            'opening_balance': opening_balance,
            'total_charges': transactions.filter(amount__lt=0).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00'),
            'total_payments': transactions.filter(amount__gt=0).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00'),
            'closing_balance': account.current_balance,
        }
    
    field_names = {
        'created_at': 'Date',
        'transaction_type': 'Type',
        'description': 'Description',
        'reference_number': 'Reference',
        'amount': 'Amount',
        'balance_after': 'Balance',
        'invoice': 'Invoice',
        'payment': 'Payment',
        'academic_session': 'Session',
    }
    
    selected_field_names = [field_names.get(field, field.replace('_', ' ').title()) for field in selected_fields]
    
    context = {
        'account': account,
        'transactions': transactions,
        'opening_balance': opening_balance,
        'summary': summary,
        'date_from': date_from,
        'date_to': date_to,
        'now': timezone.now(),
        'selected_fields': selected_fields,
        'selected_field_names': selected_field_names,
        'field_names': field_names,
        'title': f'Account Statement - {account.student.get_full_name()}',
    }
    
    return render(request, 'fees/accounts/print_statement.html', context)

# =============================================================================
# ACCOUNT TRANSACTION VIEWS (List + Detail + Print)
# =============================================================================

@login_required
def account_transaction_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""
    from .forms import AccountTransactionFilterForm
    
    filter_form = AccountTransactionFilterForm(request.GET or None)
    transactions = get_filtered_account_transactions(request)
    
    # Calculate statistics
    stats = {
        'total': transactions.count(),
        'credits': transactions.filter(transaction_type='CREDIT').count(),
        'debits': transactions.filter(transaction_type='DEBIT').count(),
        'payments': transactions.filter(transaction_type='PAYMENT').count(),
        'invoices': transactions.filter(transaction_type='INVOICE').count(),
        'total_credit_amount': transactions.filter(
            transaction_type__in=['CREDIT', 'PAYMENT']
        ).aggregate(Sum('amount'))['amount__sum'] or 0,
        'total_debit_amount': transactions.filter(
            transaction_type__in=['DEBIT', 'INVOICE']
        ).aggregate(Sum('amount'))['amount__sum'] or 0,
    }
    
    # Pagination
    paginator = Paginator(transactions, 20)
    page_number = request.GET.get('page', 1)
    transactions_page = paginator.get_page(page_number)
    
    # Detect HTMX request
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'transactions_page': transactions_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    # Return appropriate template
    if is_htmx:
        return render(request, 'fees/transactions/partials/_transaction_results.html', context)
    else:
        return render(request, 'fees/transactions/list.html', context)


@login_required
def transaction_detail(request, pk):
    """View transaction details"""
    
    transaction_obj = get_object_or_404(
        AccountTransaction.objects.select_related(
            'student_account__student', 'invoice', 'payment', 'academic_session'
        ),
        pk=pk
    )
    
    context = {
        'transaction': transaction_obj,
    }
    
    return render(request, 'fees/transactions/detail.html', context)


@login_required
def transaction_list_print_view(request):
    """Generate printable transaction list"""
    
    # Get filter parameters
    filters = {}
    if request.GET.get('student_account'):
        filters['student_account'] = request.GET.get('student_account')
    if request.GET.get('transaction_type'):
        filters['transaction_type'] = request.GET.get('transaction_type')
    if request.GET.get('date_from'):
        filters['date_from'] = request.GET.get('date_from')
    if request.GET.get('date_to'):
        filters['date_to'] = request.GET.get('date_to')
    
    # Build queryset
    transactions = AccountTransaction.objects.select_related(
        'student_account__student', 'invoice', 'payment'
    ).order_by('-transaction_date')
    
    if filters.get('student_account'):
        transactions = transactions.filter(student_account_id=filters['student_account'])
    if filters.get('transaction_type'):
        transactions = transactions.filter(transaction_type=filters['transaction_type'])
    if filters.get('date_from'):
        transactions = transactions.filter(transaction_date__gte=filters['date_from'])
    if filters.get('date_to'):
        transactions = transactions.filter(transaction_date__lte=filters['date_to'])
    
    # Get summary stats
    summary = transactions.aggregate(
        total_credits=Sum('amount', filter=Q(amount__gt=0)),
        total_debits=Sum('amount', filter=Q(amount__lt=0)),
    )
    
    context = {
        'transactions': transactions[:100],
        'summary': summary,
        'filters': filters,
        'now': timezone.now(),
        'title': 'Account Transactions',
    }
    
    return render(request, 'fees/transactions/print_list.html', context)

# =============================================================================
# FEE INVOICE VIEWS (CRUD + Print + Bulk Generation)
# =============================================================================

@login_required
def invoice_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""
    filter_form = FeeInvoiceFilterForm(request.GET or None)
    
    # Get filtered invoices with related data
    invoices = get_filtered_fee_invoices(request).select_related(
        'student',
        'academic_session',
        'fiscal_period',
        'fee_structure'
    ).prefetch_related(
        'items',
        'payments'
    ).annotate(
        item_count=Count('items'),
        payment_count=Count('payments', filter=Q(
            payments__status='COMPLETED',
            payments__reversed=False,
            payments__refunded=False
        ))
    )
    
    # Calculate statistics
    today = get_school_today()
    stats = {
        'total': invoices.count(),
        'draft': invoices.filter(status='DRAFT').count(),
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
    }
    
    # Pagination
    paginator = Paginator(invoices, 20)
    page_number = request.GET.get('page', 1)
    invoices_page = paginator.get_page(page_number)
    
    # Detect HTMX request
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'invoices_page': invoices_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
        'today': today,  # ✅ Add today for overdue checks
    }
    
    # Return appropriate template
    if is_htmx:
        return render(request, 'fees/invoices/partials/_invoice_results.html', context)
    else:
        return render(request, 'fees/invoices/list.html', context)

@login_required
def invoice_create(request):
    """Create new fee invoice"""
    student_id = request.GET.get('student')
    student = None
    if student_id:
        student = get_object_or_404(Student, pk=student_id)
    
    if request.method == 'POST':
        form = FeeInvoiceForm(request.POST)
        if form.is_valid():
            try:
                invoice = form.save()
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f"Invoice '{invoice.invoice_number}' created successfully!"
                    response['HX-Alert-Type'] = 'success'
                    response['HX-Alert-Title'] = 'Created!'
                    response['HX-Redirect'] = reverse('fees:invoice_detail', kwargs={'pk': invoice.pk})
                    return response
                else:
                    messages.success(
                        request,
                        f"Invoice '{invoice.invoice_number}' created successfully!",
                        extra_tags='sweetalert'
                    )
                    return redirect('fees:invoice_detail', pk=invoice.pk)
                    
            except Exception as e:
                logger.error(f"Error creating invoice: {e}")
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Error creating invoice: {str(e)}'
                    response['HX-Alert-Type'] = 'error'
                    response['HX-Alert-Title'] = 'Error!'
                    return response
                else:
                    messages.error(request, f'Error creating invoice: {str(e)}')
    else:
        initial = {}
        if student:
            initial['student'] = student
            initial['academic_session'] = get_active_academic_session()
        
        form = FeeInvoiceForm(initial=initial)
    
    context = {
        'form': form,
        'student': student,
        'title': 'Create Fee Invoice',
    }
    
    return render(request, 'fees/invoices/form.html', context)

@login_required
def invoice_detail(request, pk):
    """View invoice details"""
    invoice = get_object_or_404(
        FeeInvoice.objects.select_related(
            'student', 'academic_session', 'fiscal_period', 'fee_structure'
        ).prefetch_related('items__fee_category'),
        pk=pk
    )
    
    # Get related payments
    payments = invoice.payments.select_related('payment_method').order_by('-payment_date')
    
    # Calculate payment progress
    today = get_school_today()
    
    payment_progress = {
        'paid_percentage': round((invoice.paid_amount / invoice.total_amount * 100), 1) if invoice.total_amount > 0 else 0,
        'is_overdue': invoice.due_date < today and invoice.status in ['PENDING', 'PARTIALLY_PAID', 'OVERDUE'],
        'days_overdue': (today - invoice.due_date).days if invoice.due_date < today else 0,
        'days_until_due': (invoice.due_date - today).days if invoice.due_date >= today else 0,
    }
    
    context = {
        'invoice': invoice,
        'payments': payments,
        'payment_progress': payment_progress,
    }
    
    return render(request, 'fees/invoices/detail.html', context)

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from decimal import Decimal
import logging

from .models import FeeInvoice, FeeInvoiceItem, FeesCategory, AccountTransaction
from .forms import (
    FeeInvoiceEditForm,
    FeeInvoiceItemFormSet,
    InvoiceItemQuickEditForm,
    InvoiceAddItemForm
)

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["GET", "POST"])
def invoice_edit(request, invoice_id):
    """
    Edit invoice items and header information (DRAFT invoices only).
    
    Uses manual edit mode: auto_reapply_discounts=False
    This preserves user's manual changes and doesn't recalculate scholarships.
    """
    invoice = get_object_or_404(
        FeeInvoice.objects.select_related(
            'student',
            'academic_session',
            'fiscal_period'
        ).prefetch_related(
            'items__fee_category',
        ),
        pk=invoice_id
    )
    
    # Check if invoice is editable
    if invoice.status != 'DRAFT':
        messages.error(
            request,
            f'Cannot edit {invoice.get_status_display()} invoice. '
            f'Please revert to DRAFT status first.',
            extra_tags='sweetalert'
        )
        return redirect('fees:invoice_detail', pk=invoice.pk)
    
    if request.method == 'POST':
        header_form = FeeInvoiceEditForm(request.POST, instance=invoice)
        items_formset = FeeInvoiceItemFormSet(
            request.POST,
            instance=invoice,
            queryset=invoice.items.all()
        )
        
        if header_form.is_valid() and items_formset.is_valid():
            try:
                with transaction.atomic():
                    # Save header
                    header_form.save()
                    
                    # Save items and recalculate
                    saved_items = items_formset.save(commit=False)
                    
                    # Delete removed items
                    for item in items_formset.deleted_objects:
                        logger.info(f"Deleting item: {item.description}")
                        item.delete()
                    
                    # Save new/modified items
                    for item in saved_items:
                        # Recalculate item totals
                        item.recalculate_totals()
                        item.save()
                        logger.info(f"Saved item: {item.description} - Amount: {item.final_amount}")
                    
                    # ✅ RECALCULATE WITHOUT AUTO-REAPPLYING DISCOUNTS (Manual Edit Mode)
                    invoice.recalculate_totals(auto_reapply_discounts=False)
                    
                    # Update account transaction if exists
                    if hasattr(invoice, 'account_transaction'):
                        invoice.account_transaction.amount = -invoice.total_amount  # Negative = student owes
                        invoice.account_transaction.save()
                    
                    # Log the edit
                    logger.info(
                        f"Invoice {invoice.invoice_number} edited by {request.user.username}. "
                        f"New total: {invoice.total_amount} (manual edit mode - discounts preserved)"
                    )
                    
                    # Show info message if auto-apply was enabled
                    if invoice.auto_scholarships_applied or invoice.auto_discounts_applied:
                        messages.info(
                            request,
                            'Note: Your changes have been saved. Scholarships and discounts were preserved. '
                            'Use "Re-calculate Scholarships & Discounts" if you want to recalculate them based on the new amounts.',
                            extra_tags='sweetalert'
                        )
                    
                    messages.success(
                        request,
                        f'Invoice {invoice.invoice_number} updated successfully! '
                        f'New total: {invoice.total_amount}',
                        extra_tags='sweetalert'
                    )
                    
                    # Redirect to invoice detail
                    return redirect('fees:invoice_detail', pk=invoice.pk)
                    
            except Exception as e:
                logger.exception(f"Error editing invoice {invoice_id}")
                messages.error(
                    request,
                    f'Error updating invoice: {str(e)}',
                    extra_tags='sweetalert'
                )
    else:
        header_form = FeeInvoiceEditForm(instance=invoice)
        items_formset = FeeInvoiceItemFormSet(
            instance=invoice,
            queryset=invoice.items.all().order_by('fee_category__name')
        )
    
    context = {
        'invoice': invoice,
        'header_form': header_form,
        'items_formset': items_formset,
        'title': f'Edit Invoice {invoice.invoice_number}',
    }
    
    return render(request, 'fees/invoices/invoice_edit.html', context)


@login_required
@require_http_methods(["POST"])
def invoice_reapply_scholarships(request, invoice_id):
    """
    Re-apply auto scholarships and discounts to a DRAFT invoice.
    
    This recalculates the invoice with auto_reapply_discounts=True,
    which resets all discounts and re-applies scholarships/discounts
    based on current item amounts.
    
    Use this when:
    - User manually changed item amounts and wants to recalculate scholarships
    - User wants to refresh scholarship calculations
    - Fee structures or scholarship rules have changed
    """
    invoice = get_object_or_404(FeeInvoice, pk=invoice_id)
    
    # Check if invoice can be modified
    if invoice.status != 'DRAFT':
        messages.error(
            request,
            f'Cannot re-apply scholarships to {invoice.get_status_display()} invoice. '
            f'Only DRAFT invoices can be modified.',
            extra_tags='sweetalert'
        )
        return redirect('fees:invoice_detail', pk=invoice.pk)
    
    # Check if invoice has auto-apply enabled
    if not (invoice.auto_scholarships_applied or invoice.auto_discounts_applied):
        messages.warning(
            request,
            'This invoice does not have auto-apply scholarships or discounts enabled. '
            'No changes were made.',
            extra_tags='sweetalert'
        )
        return redirect('fees:invoice_detail', pk=invoice.pk)
    
    try:
        with transaction.atomic():
            # Store old total for comparison
            old_total = invoice.total_amount
            old_scholarship = invoice.scholarship_discount_amount
            old_discount = invoice.discount_amount
            
            # ✅ RECALCULATE WITH AUTO-REAPPLY (Automatic Mode)
            invoice.recalculate_totals(auto_reapply_discounts=True)
            
            # Update account transaction if exists
            if hasattr(invoice, 'account_transaction'):
                invoice.account_transaction.amount = -invoice.total_amount
                invoice.account_transaction.description = (
                    f"Invoice {invoice.invoice_number} - {invoice.academic_session.name} "
                    f"(Scholarships re-applied by {request.user.username})"
                )
                invoice.account_transaction.save()
            
            # Log the action
            logger.info(
                f"Scholarships/discounts re-applied to invoice {invoice.invoice_number} "
                f"by {request.user.username}. "
                f"Old: Total={old_total}, Scholarship={old_scholarship}, Discount={old_discount}. "
                f"New: Total={invoice.total_amount}, Scholarship={invoice.scholarship_discount_amount}, "
                f"Discount={invoice.discount_amount}"
            )
            
            # Calculate changes
            total_change = invoice.total_amount - old_total
            scholarship_change = invoice.scholarship_discount_amount - old_scholarship
            discount_change = invoice.discount_amount - old_discount
            
            # Build message
            if total_change != 0:
                change_text = "increased" if total_change > 0 else "decreased"
                messages.success(
                    request,
                    f'Scholarships and discounts re-calculated successfully! '
                    f'Total amount {change_text} by {abs(total_change):,.2f}. '
                    f'New total: {invoice.total_amount:,.2f}',
                    extra_tags='sweetalert'
                )
            else:
                messages.success(
                    request,
                    f'Scholarships and discounts re-calculated. Total amount unchanged: {invoice.total_amount:,.2f}',
                    extra_tags='sweetalert'
                )
            
            # Add breakdown if there were changes
            if scholarship_change != 0 or discount_change != 0:
                messages.info(
                    request,
                    f'Breakdown: Scholarship discount: {invoice.scholarship_discount_amount:,.2f}, '
                    f'Regular discount: {invoice.discount_amount:,.2f}',
                    extra_tags='sweetalert'
                )
            
    except Exception as e:
        logger.exception(f"Error re-applying scholarships to invoice {invoice_id}")
        messages.error(
            request,
            f'Error re-applying scholarships: {str(e)}',
            extra_tags='sweetalert'
        )
    
    return redirect('fees:invoice_detail', pk=invoice.pk)


@login_required
@require_http_methods(["POST"])
def invoice_item_quick_edit(request, invoice_id, item_id):
    """
    Quick edit a single item's unit amount (AJAX endpoint).
    
    Returns JSON response for inline editing without full page reload.
    Uses manual edit mode (auto_reapply_discounts=False).
    """
    invoice = get_object_or_404(FeeInvoice, pk=invoice_id)
    item = get_object_or_404(FeeInvoiceItem, pk=item_id, invoice=invoice)
    
    # Check if editable
    if invoice.status != 'DRAFT':
        return JsonResponse({
            'success': False,
            'error': f'Cannot edit {invoice.get_status_display()} invoice'
        }, status=400)
    
    form = InvoiceItemQuickEditForm(request.POST, invoice=invoice)
    
    if form.is_valid():
        try:
            with transaction.atomic():
                new_unit_amount = form.cleaned_data['new_unit_amount']
                reason = form.cleaned_data.get('reason', '')
                
                # Store old amount for logging
                old_unit_amount = item.unit_amount
                
                # Update item
                item.unit_amount = new_unit_amount
                item.recalculate_totals()
                
                # Add reason to notes if provided
                if reason:
                    if item.description:
                        item.description += f" [Edited: {reason}]"
                
                item.save()
                
                # ✅ RECALCULATE WITHOUT AUTO-REAPPLYING (Manual Edit Mode)
                invoice.recalculate_totals(auto_reapply_discounts=False)
                
                # Log the change
                logger.info(
                    f"Item {item.pk} in invoice {invoice.invoice_number} "
                    f"quick-edited by {request.user.username}: "
                    f"{old_unit_amount} -> {new_unit_amount}. Reason: {reason}"
                )
                
                return JsonResponse({
                    'success': True,
                    'item': {
                        'id': str(item.pk),
                        'unit_amount': str(item.unit_amount),
                        'quantity': str(item.quantity),
                        'amount': str(item.amount),
                        'tax_amount': str(item.tax_amount),
                        'final_amount': str(item.final_amount)
                    },
                    'invoice': {
                        'subtotal_amount': str(invoice.subtotal_amount),
                        'tax_amount': str(invoice.tax_amount),
                        'total_amount': str(invoice.total_amount),
                        'balance': str(invoice.balance)
                    },
                    'message': f'Item updated successfully'
                })
                
        except Exception as e:
            logger.exception(f"Error in quick edit for item {item_id}")
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
    else:
        return JsonResponse({
            'success': False,
            'errors': form.errors
        }, status=400)


@login_required
@require_http_methods(["POST"])
def invoice_add_item(request, invoice_id):
    """
    Add a new item to a DRAFT invoice.
    Uses manual edit mode (auto_reapply_discounts=False).
    """
    invoice = get_object_or_404(FeeInvoice, pk=invoice_id)
    
    # Check if editable
    if invoice.status != 'DRAFT':
        messages.error(
            request,
            f'Cannot add items to {invoice.get_status_display()} invoice',
            extra_tags='sweetalert'
        )
        return redirect('fees:invoice_detail', pk=invoice.pk)
    
    form = InvoiceAddItemForm(request.POST, invoice=invoice)
    
    if form.is_valid():
        try:
            with transaction.atomic():
                fee_category_id = form.cleaned_data['fee_category']
                fee_category = FeesCategory.objects.get(pk=fee_category_id)
                
                # Create new item
                item = FeeInvoiceItem(
                    invoice=invoice,
                    fee_category=fee_category,
                    description=form.cleaned_data['description'],
                    unit_amount=form.cleaned_data['unit_amount'],
                    quantity=form.cleaned_data['quantity'],
                    amount=Decimal('0.00'),  # Will be calculated
                    tax_percentage=form.cleaned_data['tax_percentage'],
                    discount_amount=Decimal('0.00'),
                    discount_percentage=Decimal('0.00'),
                    scholarship_discount_amount=Decimal('0.00'),
                    total_discount_amount=Decimal('0.00'),
                    tax_amount=Decimal('0.00'),
                    final_amount=Decimal('0.00'),  # Will be calculated
                )
                
                # Calculate totals
                item.recalculate_totals()
                item.save()
                
                # ✅ RECALCULATE WITHOUT AUTO-REAPPLYING (Manual Edit Mode)
                invoice.recalculate_totals(auto_reapply_discounts=False)
                
                # Log
                logger.info(
                    f"Item added to invoice {invoice.invoice_number} "
                    f"by {request.user.username}: {item.description} - {item.unit_amount}"
                )
                
                messages.success(
                    request,
                    f'Item "{item.description}" added successfully',
                    extra_tags='sweetalert'
                )
                
        except Exception as e:
            logger.exception(f"Error adding item to invoice {invoice_id}")
            messages.error(request, f'Error adding item: {str(e)}')
    else:
        for error in form.errors.values():
            messages.error(request, error)
    
    return redirect('fees:invoice_edit', invoice_id=invoice.pk)


@login_required
@require_http_methods(["POST"])
def invoice_remove_item(request, invoice_id, item_id):
    """
    Remove an item from a DRAFT invoice.
    Uses manual edit mode (auto_reapply_discounts=False).
    """
    invoice = get_object_or_404(FeeInvoice, pk=invoice_id)
    item = get_object_or_404(FeeInvoiceItem, pk=item_id, invoice=invoice)
    
    # Check if editable
    if invoice.status != 'DRAFT':
        messages.error(
            request,
            f'Cannot remove items from {invoice.get_status_display()} invoice',
            extra_tags='sweetalert'
        )
        return redirect('fees:invoice_detail', pk=invoice.pk)
    
    # Check if this is the last item
    if invoice.items.count() <= 1:
        messages.error(
            request,
            'Cannot remove the last item. Invoice must have at least one item.',
            extra_tags='sweetalert'
        )
        return redirect('fees:invoice_edit', invoice_id=invoice.pk)
    
    try:
        with transaction.atomic():
            description = item.description
            item.delete()
            
            # ✅ RECALCULATE WITHOUT AUTO-REAPPLYING (Manual Edit Mode)
            invoice.recalculate_totals(auto_reapply_discounts=False)
            
            # Log
            logger.info(
                f"Item removed from invoice {invoice.invoice_number} "
                f"by {request.user.username}: {description}"
            )
            
            messages.success(
                request,
                f'Item "{description}" removed successfully',
                extra_tags='sweetalert'
            )
            
    except Exception as e:
        logger.exception(f"Error removing item {item_id}")
        messages.error(request, f'Error removing item: {str(e)}')
    
    return redirect('fees:invoice_edit', invoice_id=invoice.pk)


@login_required
@require_http_methods(["GET"])
def invoice_preview_changes(request, invoice_id):
    """
    Preview invoice changes before saving (AJAX endpoint).
    
    Returns JSON with calculated totals based on form data.
    """
    invoice = get_object_or_404(FeeInvoice, pk=invoice_id)
    
    # This would process form data and return calculated totals
    # without saving to database
    # Implementation depends on how you want to handle preview
    
    return JsonResponse({
        'success': True,
        'preview': {
            'subtotal': str(invoice.subtotal),
            'tax_total': str(invoice.tax_total),
            'total_amount': str(invoice.total_amount)
        }
    })

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.core.exceptions import ValidationError
import logging

from academics.models import StudentClassEnrollment
from .forms import SingleInvoiceGenerationForm
from .models import FeeInvoice, StudentScholarship
from .invoice_generators import generate_student_enrollment_invoice

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["GET", "POST"])
def invoice_single_generate_form(request, enrollment_id):
    """
    Display form and generate a single invoice for a student enrollment.
    
    This view provides a form-based interface for invoice generation with
    more control than the simple POST-only invoice_single_generate view.
    
    GET: Display form with pre-populated enrollment information
    POST: Process form and generate invoice
    
    Args:
        enrollment_id: UUID of the StudentClassEnrollment
    
    Returns:
        Rendered form or redirect to invoice detail on success
    """
    # Get enrollment with related data
    enrollment = get_object_or_404(
        StudentClassEnrollment.objects.select_related(
            'student',
            'class_instance',
            'academic_session',
            'academic_session__school'
        ).prefetch_related(
            'student__boarding_enrollment'
        ),
        pk=enrollment_id
    )
    
    school = enrollment.academic_session.school
    student = enrollment.student
    
    # Check for existing invoices for context
    existing_invoices = FeeInvoice.objects.filter(
        student=student,
        academic_session=enrollment.academic_session
    ).exclude(status__in=['VOID', 'CANCELLED']).order_by('-created_at')
    
    # Get active scholarships for display
    active_scholarships = StudentScholarship.objects.filter(
        student=student,
        is_active=True
    ).select_related('scholarship_program')
    
    if request.method == 'POST':
        form = SingleInvoiceGenerationForm(
            request.POST,
            school=school,
            enrollment=enrollment
        )
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Get generation kwargs from form
                    kwargs = form.get_generation_kwargs()
                    
                    # Generate invoice
                    invoice = generate_student_enrollment_invoice(
                        enrollment,
                        **kwargs
                    )
                    
                    # Log success
                    logger.info(
                        f"Invoice {invoice.invoice_number} generated for "
                        f"{student.get_full_name()} by {request.user.username}"
                    )
                    
                    # Prepare success message
                    status_text = "PENDING" if kwargs.get('create_as_pending') else "DRAFT"
                    message_text = (
                        f'Invoice {invoice.invoice_number} generated successfully! '
                        f'Status: {status_text} | Total: {invoice.total_amount}'
                    )
                    
                    # Add scholarship info if applicable
                    if invoice.has_scholarship and invoice.total_scholarship_discount > 0:
                        message_text += f' | Scholarship Discount: {invoice.total_scholarship_discount}'
                    
                    messages.success(
                        request,
                        message_text,
                        extra_tags='sweetalert'
                    )
                    
                    # Redirect to invoice detail
                    return redirect('fees:invoice_detail', pk=invoice.pk)
                    
            except ValidationError as e:
                # Validation errors from invoice generator
                logger.warning(
                    f"Validation error generating invoice for enrollment {enrollment_id}: {str(e)}"
                )
                messages.error(
                    request,
                    f'Validation Error: {str(e)}',
                    extra_tags='sweetalert'
                )
                
            except Exception as e:
                # Unexpected errors
                logger.exception(
                    f"Error generating invoice for enrollment {enrollment_id}"
                )
                messages.error(
                    request,
                    f'Error generating invoice: {str(e)}',
                    extra_tags='sweetalert'
                )
    else:
        # GET request - initialize form
        form = SingleInvoiceGenerationForm(
            school=school,
            enrollment=enrollment
        )
    
    context = {
        'form': form,
        'enrollment': enrollment,
        'student': student,
        'school': school,
        'existing_invoices': existing_invoices,
        'active_scholarships': active_scholarships,
        'title': 'Generate Student Invoice',
    }
    
    return render(request, 'fees/invoices/invoice_single_generate_form.html', context)


@login_required
@require_http_methods(["POST"])
def invoice_single_generate_quick(request, enrollment_id):
    """
    Quick invoice generation without form (original simple version).
    
    This is a simplified POST-only endpoint for generating invoices
    with default settings. Use invoice_single_generate_form for
    more control over invoice parameters.
    
    POST parameters (optional):
        - auto_apply_scholarships (bool, default: True)
        - auto_apply_discounts (bool, default: True)
        - create_as_pending (bool, default: False)
    
    Args:
        enrollment_id: UUID of the StudentClassEnrollment
    
    Returns:
        Redirect to invoice detail on success or enrollment detail on error
    """
    enrollment = get_object_or_404(
        StudentClassEnrollment.objects.select_related(
            'student',
            'class_instance',
            'academic_session'
        ),
        pk=enrollment_id
    )
    
    try:
        # Get optional parameters from POST
        auto_apply_scholarships = request.POST.get('auto_apply_scholarships', 'true').lower() == 'true'
        auto_apply_discounts = request.POST.get('auto_apply_discounts', 'true').lower() == 'true'
        create_as_pending = request.POST.get('create_as_pending', 'false').lower() == 'true'
        
        # Generate invoice with default settings
        invoice = generate_student_enrollment_invoice(
            enrollment,
            auto_apply_scholarships=auto_apply_scholarships,
            auto_apply_discounts=auto_apply_discounts,
            create_as_pending=create_as_pending
        )
        
        # Log success
        logger.info(
            f"Quick invoice {invoice.invoice_number} generated for "
            f"{enrollment.student.get_full_name()} by {request.user.username}"
        )
        
        messages.success(
            request,
            f'Invoice {invoice.invoice_number} generated successfully!',
            extra_tags='sweetalert'
        )
        
        return redirect('fees:invoice_detail', pk=invoice.pk)
        
    except ValidationError as e:
        logger.warning(
            f"Validation error in quick invoice generation for enrollment {enrollment_id}: {str(e)}"
        )
        messages.error(request, f'Validation Error: {str(e)}')
        return redirect('academics:enrollment_detail', pk=enrollment_id)
        
    except Exception as e:
        logger.exception(f"Error in quick invoice generation for enrollment {enrollment_id}")
        messages.error(request, f'Error generating invoice: {str(e)}')
        return redirect('academics:enrollment_detail', pk=enrollment_id)

def invoice_bulk_generate(request):
    """
    OPTIMIZED: Generate invoices in bulk with batch processing.
    
    Key Optimizations:
    1. Prefetch all related data upfront (scholarships, structures, discounts)
    2. Convert QuerySet to list to avoid slicing issues
    3. Batch similar operations together
    4. Reduce per-student queries
    5. Show progress to user (optional: use Celery for async)
    
    FIXES:
    - Converted QuerySet to list before batching to prevent empty batches
    - Replaced Unicode symbols with ASCII for Windows console compatibility
    - Improved logging and error handling
    """
    
    logger.info("=" * 80)
    logger.info("BULK INVOICE GENERATION VIEW CALLED (OPTIMIZED)")
    logger.info(f"Method: {request.method}")
    logger.info("=" * 80)
    
    if request.method == 'POST':
        form = BulkInvoiceGenerationForm(request.POST)
        
        if form.is_valid():
            preview_only = form.cleaned_data.get('preview_only', True)
            
            # =====================================================================
            # PREVIEW MODE
            # =====================================================================
            if preview_only:
                logger.info("PREVIEW MODE - Generating preview data")
                
                try:
                    preview = form.get_preview_data()
                    
                    # Add scholarship analysis
                    session = form.cleaned_data['academic_session']
                    issue_date = form.cleaned_data['issue_date']
                    
                    enrollments = form.get_target_enrollments()
                    student_ids = list(enrollments.values_list('student_id', flat=True))
                    
                    students_with_scholarships = StudentScholarship.objects.filter(
                        student_id__in=student_ids,
                        status='ACTIVE',
                        start_date__lte=issue_date,
                    ).filter(
                        Q(end_date__isnull=True) | Q(end_date__gte=issue_date)
                    ).values_list('student_id', flat=True).distinct()
                    
                    scholarship_eligible_count = len(list(students_with_scholarships))
                    
                    scholarship_programs = []
                    if scholarship_eligible_count > 0:
                        scholarship_programs = list(
                            StudentScholarship.objects.filter(
                                student_id__in=student_ids,
                                status='ACTIVE',
                                start_date__lte=issue_date,
                            ).filter(
                                Q(end_date__isnull=True) | Q(end_date__gte=issue_date)
                            ).select_related('scholarship_program').values_list(
                                'scholarship_program__name', flat=True
                            ).distinct()
                        )
                    
                    preview['scholarship_eligible_count'] = scholarship_eligible_count
                    preview['scholarship_percentage'] = (
                        (scholarship_eligible_count / preview['total_enrollments'] * 100)
                        if preview['total_enrollments'] > 0 else 0
                    )
                    preview['scholarship_programs'] = scholarship_programs
                    
                    if form.cleaned_data.get('auto_apply_discounts', True):
                        active_discounts = FeesDiscount.objects.filter(
                            academic_session=session,
                            is_active=True,
                            auto_apply=True,
                            start_date__lte=issue_date,
                            end_date__gte=issue_date,
                        ).count()
                        preview['active_auto_discounts'] = active_discounts
                    else:
                        preview['active_auto_discounts'] = 0
                    
                    if preview['total_enrollments'] == 0:
                        messages.warning(
                            request,
                            "No students match your selection criteria. "
                            "Please adjust your filters and try again."
                        )
                    else:
                        if scholarship_eligible_count > 0:
                            messages.info(
                                request,
                                f"{scholarship_eligible_count} student(s) have active scholarships that will be applied during generation."
                            )
                    
                    return render(request, 'fees/invoices/bulk_generate_preview.html', {
                        'form': form,
                        'preview': preview,
                        'title': 'Bulk Invoice Generation - Preview',
                    })
                    
                except Exception as e:
                    logger.error(f"ERROR generating preview: {e}", exc_info=True)
                    messages.error(request, f"Error generating preview: {str(e)}")
                    
                    return render(request, 'fees/invoices/bulk_generate.html', {
                        'form': form,
                        'title': 'Bulk Invoice Generation'
                    })
            
            # =====================================================================
            # ACTUAL GENERATION MODE - OPTIMIZED VERSION
            # =====================================================================
            else:
                logger.info("GENERATION MODE - Creating invoices (OPTIMIZED)")
                
                confirmed = form.cleaned_data.get('confirm', False)
                if not confirmed:
                    messages.error(
                        request,
                        "You must check the confirmation box before generating invoices."
                    )
                    return render(request, 'fees/invoices/bulk_generate.html', {
                        'form': form,
                        'title': 'Bulk Invoice Generation'
                    })
                
                try:
                    # =================================================================
                    # STEP 1: GET ALL ENROLLMENTS WITH PREFETCHING (AS QUERYSET)
                    # =================================================================
                    enrollments_qs = form.get_target_enrollments().select_related(
                        'student',
                        'class_instance',
                        'class_instance__academic_level',
                        'academic_session'
                    ).prefetch_related(
                        # Prefetch boarding enrollments
                        Prefetch(
                            'student__boarding_enrollments',
                            queryset=form.cleaned_data['academic_session'].boarding_enrollments.filter(
                                status='ACTIVE'
                            )
                        )
                    )
                    
                    # CRITICAL FIX: Convert QuerySet to list to avoid slicing issues
                    logger.info("Loading enrollments into memory...")
                    enrollments = list(enrollments_qs)
                    total_count = len(enrollments)
                    
                    logger.info(f"OPTIMIZED GENERATION: Loaded {total_count} enrollments into memory")
                    
                    if total_count == 0:
                        messages.warning(request, "No students match your criteria.")
                        return redirect('fees:invoice_bulk_generate')
                    
                    # =================================================================
                    # STEP 2: PREFETCH ALL SCHOLARSHIPS AT ONCE
                    # =================================================================
                    session = form.cleaned_data['academic_session']
                    issue_date = form.cleaned_data['issue_date']
                    
                    student_ids = [enrollment.student_id for enrollment in enrollments]
                    
                    # Get all active scholarships for these students
                    active_scholarships = StudentScholarship.objects.filter(
                        student_id__in=student_ids,
                        status='ACTIVE',
                        start_date__lte=issue_date,
                    ).filter(
                        Q(end_date__isnull=True) | Q(end_date__gte=issue_date)
                    ).select_related('scholarship_program')
                    
                    # Create lookup dict: student_id -> list of scholarships
                    scholarships_by_student = {}
                    for scholarship in active_scholarships:
                        student_id = scholarship.student_id
                        if student_id not in scholarships_by_student:
                            scholarships_by_student[student_id] = []
                        scholarships_by_student[student_id].append(scholarship)
                    
                    logger.info(f"Prefetched scholarships for {len(scholarships_by_student)} students")
                    
                    # =================================================================
                    # STEP 3: PREFETCH ALL APPLICABLE FEE STRUCTURES
                    # =================================================================
                    # Get all fee structures for this session
                    applicable_structures = FeesStructure.objects.filter(
                        applicable_sessions=session,
                        is_active=True
                    ).prefetch_related(
                        'items__fee_category',
                        'academic_levels',
                        'applicable_classes'
                    ).order_by('priority')
                    
                    logger.info(f"Prefetched {applicable_structures.count()} fee structures")
                    
                    # =================================================================
                    # STEP 4: PREFETCH AUTO-DISCOUNTS
                    # =================================================================
                    auto_discounts = FeesDiscount.objects.filter(
                        academic_session=session,
                        is_active=True,
                        auto_apply=True,
                        start_date__lte=issue_date,
                        end_date__gte=issue_date,
                    ).prefetch_related('applicable_structures')
                    
                    logger.info(f"Prefetched {auto_discounts.count()} auto-discounts")
                    
                    # =================================================================
                    # STEP 5: PREPARE GENERATION OPTIONS
                    # =================================================================
                    generation_options = {
                        'issue_date': issue_date,
                        'due_date': form.cleaned_data['due_date'],
                        'fiscal_period': form.cleaned_data['fiscal_period'],
                        'payment_terms': form.cleaned_data.get('payment_terms', ''),
                        'auto_apply_scholarships': form.cleaned_data.get('auto_apply_scholarships', True),
                        'auto_apply_discounts': form.cleaned_data.get('auto_apply_discounts', True),
                        'include_optional': False,
                        'force': False,
                    }
                    
                    logger.info(f"Generation options: {generation_options}")
                    
                    # =================================================================
                    # STEP 6: BATCH PROCESS IN TRANSACTION
                    # =================================================================
                    success_count = 0
                    skipped_count = 0
                    error_count = 0
                    errors = []
                    
                    scholarships_applied_count = 0
                    total_scholarship_discount = Decimal('0.00')
                    discounts_applied_count = 0
                    total_regular_discount = Decimal('0.00')
                    
                    # Process in smaller batches to avoid timeout
                    BATCH_SIZE = 50
                    
                    with transaction.atomic():
                        # Calculate total batches for logging
                        total_batches = (total_count + BATCH_SIZE - 1) // BATCH_SIZE
                        
                        for i in range(0, total_count, BATCH_SIZE):
                            # Slice the Python list (not QuerySet)
                            batch = enrollments[i:i+BATCH_SIZE]
                            batch_num = (i // BATCH_SIZE) + 1
                            
                            logger.info(
                                f"Processing batch {batch_num}/{total_batches} "
                                f"({len(batch)} enrollments, range {i+1}-{i+len(batch)})"
                            )
                            
                            for index, enrollment in enumerate(batch, start=i+1):
                                try:
                                    # Skip if already has invoice
                                    if enrollment.academic_invoice:
                                        skipped_count += 1
                                        logger.debug(f"[{index}/{total_count}] Skipped - already has invoice")
                                        continue
                                    
                                    student_name = enrollment.student.get_full_name()
                                    logger.info(f"[{index}/{total_count}] Processing: {student_name}")
                                    
                                    # Check if student has scholarship BEFORE generation
                                    has_scholarship_before = enrollment.student_id in scholarships_by_student
                                    
                                    if has_scholarship_before:
                                        scholarship_count = len(scholarships_by_student[enrollment.student_id])
                                        logger.info(f"  Student has {scholarship_count} active scholarship(s)")
                                    
                                    # Generate invoice
                                    invoice = UnifiedStudentInvoiceGenerator.generate(
                                        class_enrollment=enrollment,
                                        **generation_options
                                    )
                                    
                                    success_count += 1
                                    
                                    # Track scholarship/discount application
                                    if invoice.has_scholarships_applied:
                                        scholarships_applied_count += 1
                                        total_scholarship_discount += invoice.scholarship_discount_amount
                                        logger.info(f"  SCHOLARSHIP APPLIED: {invoice.scholarship_discount_amount:,.2f}")
                                    elif has_scholarship_before:
                                        logger.warning(f"  WARNING - Student has scholarship but none was applied")
                                    
                                    if invoice.has_discounts_applied:
                                        discounts_applied_count += 1
                                        total_regular_discount += invoice.discount_amount
                                        logger.info(f"  DISCOUNT APPLIED: {invoice.discount_amount:,.2f}")
                                    
                                    logger.info(f"  SUCCESS - Invoice: {invoice.invoice_number} - Total: {invoice.total_amount:,.2f}")
                                    
                                    # Log progress every 10 invoices
                                    if success_count % 10 == 0:
                                        logger.info(f"Progress: {success_count}/{total_count} invoices created")
                                
                                except Exception as e:
                                    error_count += 1
                                    error_msg = f"{enrollment.student.get_full_name()} ({enrollment.class_instance}): {str(e)}"
                                    errors.append(error_msg)
                                    logger.error(f"  ERROR: {error_msg}", exc_info=True)
                    
                    # =================================================================
                    # STEP 7: SHOW RESULTS
                    # =================================================================
                    logger.info("=" * 80)
                    logger.info(f"GENERATION COMPLETE:")
                    logger.info(f"  SUCCESS: {success_count}")
                    logger.info(f"  SKIPPED: {skipped_count}")
                    logger.info(f"  ERRORS: {error_count}")
                    logger.info("=" * 80)
                    
                    # Log scholarship statistics
                    logger.info("SCHOLARSHIP APPLICATION SUMMARY:")
                    scholarship_eligible_count = len(scholarships_by_student)
                    logger.info(f"  Students with active scholarships: {scholarship_eligible_count}")
                    logger.info(f"  Invoices with scholarships applied: {scholarships_applied_count}")
                    
                    if scholarship_eligible_count > 0:
                        application_rate = (scholarships_applied_count / scholarship_eligible_count * 100)
                        logger.info(f"  Application success rate: {application_rate:.1f}%")
                        
                        if scholarships_applied_count < scholarship_eligible_count:
                            not_applied = scholarship_eligible_count - scholarships_applied_count
                            logger.warning(f"  WARNING: {not_applied} students with scholarships did NOT get discount")
                    
                    if total_scholarship_discount > 0:
                        logger.info(f"  Total scholarship discount: {total_scholarship_discount:,.2f}")
                    
                    logger.info("=" * 80)
                    
                    # User messages
                    if success_count > 0:
                        success_msg = f"Successfully generated {success_count} invoice(s)."
                        
                        if scholarships_applied_count > 0:
                            success_msg += f" {scholarships_applied_count} invoice(s) received scholarship discounts totaling {total_scholarship_discount:,.0f}."
                        
                        messages.success(request, success_msg)
                    
                    if skipped_count > 0:
                        messages.info(
                            request,
                            f"Skipped {skipped_count} student(s) who already have invoices."
                        )
                    
                    if scholarship_eligible_count > scholarships_applied_count and success_count > 0:
                        not_applied = scholarship_eligible_count - scholarships_applied_count
                        messages.warning(
                            request,
                            f"Note: {scholarship_eligible_count} student(s) have active scholarships, "
                            f"but only {scholarships_applied_count} received discounts. "
                            f"{not_applied} scholarship(s) may be exhausted or have zero balance."
                        )
                    
                    if error_count > 0:
                        messages.warning(
                            request,
                            f"{error_count} invoice(s) failed to generate. Check the logs for details."
                        )
                    
                    return redirect('fees:invoice_list')
                    
                except Exception as e:
                    logger.error(f"CRITICAL ERROR during bulk generation: {e}", exc_info=True)
                    messages.error(
                        request,
                        f"Critical error during generation: {str(e)}. "
                        f"Transaction rolled back. No invoices were created."
                    )
                    
                    return render(request, 'fees/invoices/bulk_generate.html', {
                        'form': form,
                        'title': 'Bulk Invoice Generation'
                    })
        
        else:
            # Form validation failed
            logger.error("FORM INVALID - ERRORS:")
            for field, field_errors in form.errors.items():
                logger.error(f"  {field}: {field_errors}")
            
            messages.error(request, "Please correct the errors in the form below.")
    
    else:
        # GET request
        form = BulkInvoiceGenerationForm()
    
    return render(request, 'fees/invoices/bulk_generate.html', {
        'form': form,
        'title': 'Bulk Invoice Generation'
    })

def invoice_bulk_preview_search(request):
    """
    HTMX endpoint for filtering students in bulk invoice preview.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Get filter parameters from the preview page
    search_query = request.GET.get('student-search', '').strip()
    filter_class = request.GET.get('filter-class', '').strip()
    filter_level = request.GET.get('filter-level', '').strip()
    session_id = request.GET.get('session-id')
    
    # Get the form's filter criteria from session or GET params
    target_students = request.GET.get('target-students', 'all_enrolled')
    academic_level_ids = request.GET.getlist('academic-level-ids')
    class_ids = request.GET.getlist('class-ids')
    enrollment_types = request.GET.getlist('enrollment-types')
    boarding_types = request.GET.getlist('boarding-types')
    skip_with_invoice = request.GET.get('skip-with-invoice', 'false').lower() == 'true'
    skip_with_pending = request.GET.get('skip-with-pending', 'false').lower() == 'true'
    
    # REMOVE EMOJI: Change from 🔍 to SEARCH
    logger.info(f"HTMX Search - Filters:")
    logger.info(f"  session_id: {session_id}")
    logger.info(f"  target_students: {target_students}")
    logger.info(f"  academic_level_ids: {academic_level_ids}")
    logger.info(f"  class_ids: {class_ids}")
    logger.info(f"  skip_with_invoice: {skip_with_invoice}")
    
    if not session_id:
        return render(request, 'fees/invoices/partials/student_preview_list.html', {
            'error': 'Session ID required',
            'students': [],
            'total_count': 0
        })
    
    # BASE QUERYSET
    from academics.models import StudentClassEnrollment
    
    enrollments = StudentClassEnrollment.objects.filter(
        academic_session_id=session_id,
        is_active=True,
        completion_status='ONGOING'
    ).select_related(
        'student',
        'class_instance',
        'class_instance__academic_level'
    ).prefetch_related(
        'student__boarding_enrollments'
    )
    
    # REMOVE EMOJI: Change from 📊 to DATA
    logger.info(f"DATA: Base enrollments: {enrollments.count()}")
    
    # APPLY FORM'S FILTERS
    if target_students == 'by_level' and academic_level_ids:
        enrollments = enrollments.filter(
            class_instance__academic_level_id__in=academic_level_ids
        )
        logger.info(f"DATA: After level filter: {enrollments.count()}")
    
    elif target_students == 'by_class' and class_ids:
        enrollments = enrollments.filter(
            class_instance_id__in=class_ids
        )
        logger.info(f"DATA: After class filter: {enrollments.count()}")
    
    elif target_students == 'by_enrollment_type' and enrollment_types:
        enrollments = enrollments.filter(
            enrollment_type__in=enrollment_types
        )
        logger.info(f"DATA: After enrollment type filter: {enrollments.count()}")
    
    elif target_students == 'by_boarding' and boarding_types:
        enrollments = enrollments.filter(
            student__boarding_enrollments__academic_session_id=session_id,
            student__boarding_enrollments__status='ACTIVE',
            student__boarding_enrollments__boarding_type__in=boarding_types
        ).distinct()
        logger.info(f"DATA: After boarding filter: {enrollments.count()}")
    
    elif target_students == 'without_invoice':
        enrollments = enrollments.filter(academic_invoice__isnull=True)
        logger.info(f"DATA: After without_invoice filter: {enrollments.count()}")
    
    # Apply exclusions
    if skip_with_invoice:
        enrollments = enrollments.filter(academic_invoice__isnull=True)
        logger.info(f"DATA: After skip_with_invoice: {enrollments.count()}")
    
    if skip_with_pending:
        from fees.models import FeeInvoice
        students_with_pending = FeeInvoice.objects.filter(
            academic_session_id=session_id,
            status__in=['PENDING', 'PARTIALLY_PAID', 'OVERDUE']
        ).values_list('student_id', flat=True)
        enrollments = enrollments.exclude(student_id__in=students_with_pending)
        logger.info(f"DATA: After skip_with_pending: {enrollments.count()}")
    
    # APPLY SEARCH/FILTER FROM USER INPUT
    if search_query:
        enrollments = enrollments.filter(
            Q(student__first_name__icontains=search_query) |
            Q(student__last_name__icontains=search_query) |
            Q(student__admission_number__icontains=search_query)
        )
        logger.info(f"DATA: After search: {enrollments.count()}")
    
    if filter_class:
        enrollments = enrollments.filter(
            class_instance__name__iexact=filter_class
        )
        logger.info(f"DATA: After UI class filter: {enrollments.count()}")
    
    if filter_level:
        enrollments = enrollments.filter(
            class_instance__academic_level__name__iexact=filter_level
        )
        logger.info(f"DATA: After UI level filter: {enrollments.count()}")
    
    # FINALIZE AND RETURN
    enrollments = enrollments.order_by(
        'student__last_name',
        'student__first_name'
    )
    
    total_count = enrollments.count()
    students = list(enrollments[:100])  # First 100 for display
    
    # REMOVE EMOJI: Change from ✅ to SUCCESS
    logger.info(f"SUCCESS: Final count: {total_count}, returning {len(students)} students")
    
    # Add boarding status as attribute to each enrollment
    for enrollment in students:
        enrollment.has_boarding = enrollment.student.boarding_enrollments.filter(
            academic_session_id=session_id,
            status='ACTIVE'
        ).exists()
    
    context = {
        'students': students,
        'total_count': total_count,
        'session_id': session_id,
    }
    
    return render(request, 'fees/invoices/partials/student_preview_list.html', context)

def _calculate_student_fees(enrollment, session_id, auto_apply_scholarships=True, auto_apply_discounts=True, issue_date_str=None):
    """
    Unified fee calculation function used by both preview and breakdown.
    This ensures consistent calculations across all views.
    
    Args:
        enrollment: StudentClassEnrollment instance
        session_id: Academic session UUID
        auto_apply_scholarships: Whether to apply scholarships (default: True)
        auto_apply_discounts: Whether to apply discounts (default: True)
        issue_date_str: Invoice issue date as string 'YYYY-MM-DD' (default: today)
    
    Returns dict with complete fee breakdown.
    """
    from fees.models import StudentScholarship, FeesDiscount, FeesStructure
    from boarding.models import BoardingEnrollment  # ✅ Import BoardingEnrollment
    from django.utils import timezone
    from django.db.models import Q
    import logging
    from datetime import datetime
    
    logger = logging.getLogger(__name__)
    
    # =========================================================================
    # DETERMINE ISSUE DATE FOR SCHOLARSHIP/DISCOUNT VALIDATION
    # =========================================================================
    if issue_date_str:
        try:
            issue_date = datetime.strptime(issue_date_str, '%Y-%m-%d').date()
            logger.info(f"Using provided issue date: {issue_date}")
        except (ValueError, TypeError):
            issue_date = timezone.now().date()
            logger.warning(f"Invalid issue_date_str '{issue_date_str}', using today: {issue_date}")
    else:
        issue_date = timezone.now().date()
        logger.info(f"No issue date provided, using today: {issue_date}")
    
    result = {
        'error': None,
        'academic_items': [],
        'boarding_items': [],
        'academic_subtotal': Decimal('0.00'),
        'academic_tax': Decimal('0.00'),
        'boarding_subtotal': Decimal('0.00'),
        'boarding_tax': Decimal('0.00'),
        'scholarship_breakdown': [],
        'discount_breakdown': [],
        'total_scholarship_discount': Decimal('0.00'),
        'total_regular_discount': Decimal('0.00'),
    }
    
    # =========================================================================
    # STEP 1: FIND ACADEMIC FEE STRUCTURE
    # =========================================================================
    academic_fee_structure = _find_applicable_academic_structure(enrollment)
    
    if not academic_fee_structure:
        result['error'] = 'No fee structure found'
        return result
    
    result['academic_fee_structure'] = academic_fee_structure
    
    logger.info(f"✅ Using academic structure: {academic_fee_structure.name}")
    
    # =========================================================================
    # STEP 2: CALCULATE ACADEMIC FEES (subtotal + tax separately)
    # =========================================================================
    academic_structure_items = academic_fee_structure.items.select_related(
        'fee_category'
    ).filter(print_on_invoice=True).order_by('display_order')
    
    academic_items_count = 0
    for structure_item in academic_structure_items:
        if not structure_item.is_applicable_to_student(enrollment.student):
            continue
        
        amount = structure_item.get_amount_for_student(enrollment.student)
        tax = structure_item.calculate_tax_amount(amount)
        
        item_data = {
            'category': structure_item.fee_category,
            'description': structure_item.get_description(),
            'amount': amount,
            'tax_percentage': structure_item.tax_percentage,
            'tax_amount': tax,
            'final_amount': amount + tax,
            'is_mandatory': structure_item.is_mandatory,
            'type': 'academic',
            'scholarship_eligible': structure_item.scholarship_eligible,
        }
        
        result['academic_items'].append(item_data)
        academic_items_count += 1
        
        if structure_item.is_mandatory:
            result['academic_subtotal'] += amount
            result['academic_tax'] += tax
    
    logger.info(
        f"  Academic items: {academic_items_count} items, "
        f"subtotal={result['academic_subtotal']:,.2f}, "
        f"tax={result['academic_tax']:,.2f}"
    )
    
    # =========================================================================
    # STEP 3: CHECK FOR BOARDING AND CALCULATE BOARDING FEES ⭐ ENHANCED
    # =========================================================================
    logger.info("  Checking for boarding enrollment...")
    
    # ✅ Query BoardingEnrollment explicitly
    boarding_enrollment = BoardingEnrollment.objects.filter(
        student=enrollment.student,
        academic_session=enrollment.academic_session,
        status='ACTIVE'
    ).select_related('dormitory').first()
    
    result['boarding_enrollment'] = boarding_enrollment
    result['boarding_fee_structure'] = None
    
    if boarding_enrollment:
        logger.info(
            f"  ✅ Student has active boarding: {boarding_enrollment.get_boarding_type_display()} "
            f"(Dormitory: {boarding_enrollment.dormitory.name})"
        )
        
        # Find boarding fee structure
        boarding_structures = FeesStructure.objects.filter(
            applicable_sessions=enrollment.academic_session,
            boarding_type_filter__in=[
                boarding_enrollment.boarding_type,
                'BOARDER_ONLY',
            ],
            is_active=True
        ).exclude(
            id=academic_fee_structure.id  # Don't include the academic structure
        ).prefetch_related('items__fee_category').order_by('priority')
        
        logger.info(f"  Found {boarding_structures.count()} boarding fee structure(s)")
        
        if boarding_structures.exists():
            boarding_fee_structure = boarding_structures.first()
            result['boarding_fee_structure'] = boarding_fee_structure
            
            logger.info(
                f"  ✅ Using boarding structure: {boarding_fee_structure.name} "
                f"(Type filter: {boarding_fee_structure.boarding_type_filter})"
            )
            
            boarding_structure_items = boarding_fee_structure.items.select_related(
                'fee_category'
            ).filter(print_on_invoice=True).order_by('display_order')
            
            logger.info(f"  Boarding structure has {boarding_structure_items.count()} items")
            
            boarding_items_count = 0
            for structure_item in boarding_structure_items:
                if not structure_item.is_applicable_to_student(enrollment.student):
                    logger.debug(
                        f"    ⏭️ Skipping non-applicable: {structure_item.fee_category.name}"
                    )
                    continue
                
                amount = structure_item.get_amount_for_student(enrollment.student)
                tax = structure_item.calculate_tax_amount(amount)
                
                logger.info(
                    f"    ➕ Adding boarding item: {structure_item.fee_category.name} - "
                    f"{amount:,.2f} (tax: {tax:,.2f})"
                )
                
                item_data = {
                    'category': structure_item.fee_category,
                    'description': structure_item.get_description(),
                    'amount': amount,
                    'tax_percentage': structure_item.tax_percentage,
                    'tax_amount': tax,
                    'final_amount': amount + tax,
                    'is_mandatory': structure_item.is_mandatory,
                    'type': 'boarding',
                    'scholarship_eligible': structure_item.scholarship_eligible,
                }
                
                result['boarding_items'].append(item_data)
                boarding_items_count += 1
                
                if structure_item.is_mandatory:
                    result['boarding_subtotal'] += amount
                    result['boarding_tax'] += tax
            
            logger.info(
                f"  ✅ Boarding fees calculated: {boarding_items_count} items, "
                f"subtotal={result['boarding_subtotal']:,.2f}, "
                f"tax={result['boarding_tax']:,.2f}, "
                f"total={result['boarding_subtotal'] + result['boarding_tax']:,.2f}"
            )
        else:
            logger.warning(
                f"  ⚠️ No boarding fee structure found for {boarding_enrollment.get_boarding_type_display()}!"
            )
            logger.warning(
                f"     Student will NOT be billed for boarding. Please create a structure with:"
            )
            logger.warning(
                f"     - boarding_type_filter = '{boarding_enrollment.boarding_type}' or 'BOARDER_ONLY'"
            )
            logger.warning(
                f"     - applicable_sessions includes '{enrollment.academic_session.name}'"
            )
    else:
        logger.info("  ℹ️ No active boarding enrollment - student is a day scholar")
    
    # =========================================================================
    # STEP 4: CALCULATE TOTALS BEFORE DISCOUNTS
    # =========================================================================
    result['subtotal'] = result['academic_subtotal'] + result['boarding_subtotal']
    result['tax_total'] = result['academic_tax'] + result['boarding_tax']
    result['gross_total'] = result['subtotal'] + result['tax_total']
    
    logger.info(
        f"📊 Gross totals: subtotal={result['subtotal']:,.2f}, "
        f"tax={result['tax_total']:,.2f}, "
        f"gross_total={result['gross_total']:,.2f}"
    )
    
    # =========================================================================
    # STEP 5: CALCULATE SCHOLARSHIP DISCOUNTS ⭐ ENHANCED
    # =========================================================================
    if auto_apply_scholarships:
        logger.info(f"Checking scholarships for {enrollment.student.get_full_name()}")
        logger.info(f"  Invoice issue date: {issue_date}")
        
        scholarships = StudentScholarship.objects.filter(
            student=enrollment.student,
            status='ACTIVE',
            start_date__lte=issue_date,
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=issue_date)
        ).select_related('scholarship_program')
        
        logger.info(f"  Found {scholarships.count()} potentially active scholarship(s)")
        
        # Log each scholarship's details
        for scholarship in scholarships:
            logger.info(f"  → Scholarship: {scholarship.scholarship_program.name}")
            logger.info(f"     Start: {scholarship.start_date}, End: {scholarship.end_date or 'No end date'}")
            logger.info(f"     Type: {'Policy-based' if scholarship.is_policy_based() else 'Budget-based'}")
            logger.info(f"     Category-specific: {scholarship.use_category_specific_discounts}")
            if scholarship.is_budget_based():
                logger.info(f"     Balance: {scholarship.get_remaining_balance():,.2f}")
        
        # Build a dict to track discounts per item
        item_scholarship_discounts = {}
        
        for scholarship in scholarships:
            try:
                program = scholarship.scholarship_program
                scholarship_total_discount = Decimal('0.00')
                
                # =================================================================
                # MODE 1: CATEGORY-SPECIFIC DISCOUNTS ⭐ NEW
                # =================================================================
                
                if scholarship.use_category_specific_discounts:
                    logger.info(f"  Processing category-specific scholarship: {program.name}")
                    
                    # ✅ Validate category_discounts exists
                    if not scholarship.category_discounts:
                        logger.error(
                            f"    ❌ ERROR: Scholarship has use_category_specific_discounts=True "
                            f"but category_discounts is EMPTY! Skipping this scholarship."
                        )
                        logger.error(
                            f"       Please edit the scholarship to configure category discounts."
                        )
                        continue
                    
                    categories_with_discounts = sum(
                        1 for config in scholarship.category_discounts.values() 
                        if config.get('type') != 'none'
                    )
                    
                    logger.info(
                        f"    Config: {len(scholarship.category_discounts)} categories total, "
                        f"{categories_with_discounts} with active discounts"
                    )
                    
                    # ✅ Process academic items
                    for item in result['academic_items']:
                        category_code = item['category'].category_type or item['category'].code
                        discount_config = scholarship.category_discounts.get(category_code)
                        
                        if not discount_config:
                            logger.debug(
                                f"      • {item['category'].name} ({category_code}): "
                                f"Not in scholarship configuration"
                            )
                            continue
                        
                        if discount_config.get('type') == 'none':
                            logger.debug(
                                f"      • {item['category'].name} ({category_code}): "
                                f"Explicitly excluded (type='none')"
                            )
                            continue
                        
                        # Calculate discount using the helper function
                        item_discount = _calculate_category_discount(
                            item['amount'],
                            discount_config,
                            scholarship
                        )
                        
                        if item_discount > 0:
                            # Track discount for this item
                            item_id = id(item)
                            if item_id not in item_scholarship_discounts:
                                item_scholarship_discounts[item_id] = Decimal('0.00')
                            item_scholarship_discounts[item_id] += item_discount
                            
                            result['total_scholarship_discount'] += item_discount
                            scholarship_total_discount += item_discount
                            
                            logger.info(
                                f"      ✅ {item['category'].name} ({category_code}): "
                                f"{discount_config.get('type')} = {item_discount:,.2f}"
                            )
                        else:
                            logger.debug(
                                f"      • {item['category'].name} ({category_code}): "
                                f"Config present but discount = 0"
                            )
                    
                    # ✅ Process boarding items
                    for item in result['boarding_items']:
                        category_code = item['category'].category_type or item['category'].code
                        discount_config = scholarship.category_discounts.get(category_code)
                        
                        if not discount_config:
                            logger.debug(
                                f"      • {item['category'].name} ({category_code}): "
                                f"Not in scholarship configuration"
                            )
                            continue
                        
                        if discount_config.get('type') == 'none':
                            logger.debug(
                                f"      • {item['category'].name} ({category_code}): "
                                f"Explicitly excluded (type='none')"
                            )
                            continue
                        
                        item_discount = _calculate_category_discount(
                            item['amount'],
                            discount_config,
                            scholarship
                        )
                        
                        if item_discount > 0:
                            item_id = id(item)
                            if item_id not in item_scholarship_discounts:
                                item_scholarship_discounts[item_id] = Decimal('0.00')
                            item_scholarship_discounts[item_id] += item_discount
                            
                            result['total_scholarship_discount'] += item_discount
                            scholarship_total_discount += item_discount
                            
                            logger.info(
                                f"      ✅ {item['category'].name} ({category_code}): "
                                f"{discount_config.get('type')} = {item_discount:,.2f}"
                            )
                        else:
                            logger.debug(
                                f"      • {item['category'].name} ({category_code}): "
                                f"Config present but discount = 0"
                            )
                    
                    # Log scholarship total
                    if scholarship_total_discount > 0:
                        logger.info(
                            f"    Scholarship discount applied: {scholarship_total_discount:,.2f}"
                        )
                        
                        # Add to breakdown
                        result['scholarship_breakdown'].append({
                            'scholarship': scholarship,
                            'program': program,
                            'amount': scholarship_total_discount,
                            'remaining_balance': scholarship.get_remaining_balance() if scholarship.is_budget_based() else None,
                            'start_date': scholarship.start_date,
                            'end_date': scholarship.end_date,
                            'is_active_for_date': scholarship.is_active_for_date(issue_date),
                        })
                    else:
                        logger.warning(
                            f"    ⚠️ No discount applied from scholarship '{program.name}' "
                            f"(no matching items or all excluded)"
                        )
                
                # =================================================================
                # MODE 2: GLOBAL DISCOUNT (Original code - unchanged)
                # =================================================================
                
                else:
                    logger.info(f"  Processing global discount scholarship: {program.name}")
                    
                    # Calculate eligible amount from SUBTOTAL only (excluding tax)
                    eligible_amount = Decimal('0.00')
                    for item in result['academic_items'] + result['boarding_items']:
                        if item.get('scholarship_eligible', True) and item['is_mandatory']:
                            eligible_amount += item['amount']
                    
                    logger.info(f"    Eligible amount: {eligible_amount:,.2f}")
                    
                    remaining_eligible = eligible_amount
                    discount_amount = Decimal('0.00')
                    
                    if program.discount_type == 'PERCENTAGE' and program.discount_percentage is not None:
                        discount_amount = (remaining_eligible * program.discount_percentage / Decimal('100.00'))
                        discount_amount = discount_amount.quantize(Decimal('0.01'))
                        
                        if program.maximum_award_amount and discount_amount > program.maximum_award_amount:
                            logger.info(f"    Capping at maximum: {program.maximum_award_amount:,.2f}")
                            discount_amount = program.maximum_award_amount
                        
                        logger.info(
                            f"    Percentage: {program.discount_percentage}% of {eligible_amount:,.2f} = {discount_amount:,.2f}"
                        )
                    
                    elif program.discount_type == 'FULL_WAIVER':
                        discount_amount = remaining_eligible
                        logger.info(f"    Full waiver: {discount_amount:,.2f}")
                    
                    elif program.discount_type == 'FIXED_AMOUNT' and scholarship.amount_awarded > 0:
                        remaining_balance = scholarship.get_remaining_balance()
                        
                        if remaining_balance and remaining_balance > 0:
                            discount_amount = min(remaining_balance, remaining_eligible)
                            logger.info(
                                f"    Fixed amount: min({remaining_balance:,.2f}, {remaining_eligible:,.2f}) = {discount_amount:,.2f}"
                            )
                        else:
                            logger.warning(f"    Budget exhausted (balance: {remaining_balance:,.2f})")
                    
                    elif program.discount_type == 'CATEGORY_SPECIFIC':
                        # Legacy CATEGORY_SPECIFIC
                        applicable_categories = program.applicable_fee_categories.all()
                        category_eligible = Decimal('0.00')
                        
                        for item in result['academic_items'] + result['boarding_items']:
                            if (item.get('scholarship_eligible', True) and 
                                item['is_mandatory'] and
                                item['category'] in applicable_categories):
                                category_eligible += item['amount']
                        
                        if program.discount_percentage:
                            discount_amount = (category_eligible * program.discount_percentage / Decimal('100.00'))
                        elif program.fixed_discount_amount:
                            discount_amount = min(program.fixed_discount_amount, category_eligible)
                        
                        discount_amount = discount_amount.quantize(Decimal('0.01'))
                        logger.info(f"    Legacy category-specific: {discount_amount:,.2f}")
                    
                    if discount_amount > 0:
                        result['total_scholarship_discount'] += discount_amount
                        remaining_eligible -= discount_amount
                        
                        remaining_balance_display = None
                        if program.discount_type == 'FIXED_AMOUNT' and scholarship.amount_awarded > 0:
                            remaining_balance_display = scholarship.get_remaining_balance() - discount_amount
                        
                        result['scholarship_breakdown'].append({
                            'scholarship': scholarship,
                            'program': program,
                            'amount': discount_amount,
                            'remaining_balance': remaining_balance_display,
                            'start_date': scholarship.start_date,
                            'end_date': scholarship.end_date,
                            'is_active_for_date': scholarship.is_active_for_date(issue_date),
                        })
                        
                        logger.info(f"    ✅ Scholarship discount: {discount_amount:,.2f}")
                        
                        if remaining_eligible <= Decimal('0.01'):
                            break
                    else:
                        logger.warning(f"    ⚠️ No discount applied (amount = 0)")
            
            except Exception as e:
                logger.error(
                    f"❌ Error calculating scholarship {scholarship.id}: {e}",
                    exc_info=True
                )
                continue
    
    # =========================================================================
    # STEP 6: CALCULATE REGULAR DISCOUNTS
    # =========================================================================
    if auto_apply_discounts:
        logger.info("Checking regular discounts...")
        
        discounts = FeesDiscount.objects.filter(
            academic_session_id=session_id,
            is_active=True,
            auto_apply=True,
            start_date__lte=issue_date,
            end_date__gte=issue_date,
        )
        
        logger.info(f"  Found {discounts.count()} active auto-apply discount(s)")
        
        discount_base = result['subtotal'] - result['total_scholarship_discount']
        
        for discount in discounts:
            try:
                if discount.applicable_structures.exists():
                    if not discount.applicable_structures.filter(
                        id=academic_fee_structure.id
                    ).exists():
                        logger.debug(f"  Discount {discount.code}: Not applicable to this structure")
                        continue
                
                if discount_base <= 0:
                    logger.info("  No remaining amount to discount")
                    break
                
                if discount.discount_type == 'PERCENTAGE':
                    discount_amount = (discount_base * discount.discount_value / 100).quantize(Decimal('0.01'))
                else:  # FIXED
                    discount_amount = discount.discount_value
                
                discount_amount = min(discount_amount, discount_base)
                
                if discount_amount > 0:
                    result['total_regular_discount'] += discount_amount
                    discount_base -= discount_amount
                    
                    result['discount_breakdown'].append({
                        'code': discount.code,
                        'name': discount.name,
                        'amount': discount_amount,
                        'type': discount.discount_type,
                    })
                    
                    logger.info(f"  ✅ Applied discount {discount.code}: {discount_amount:,.2f}")
            
            except Exception as e:
                logger.error(f"Error calculating discount {discount.code}: {e}")
                continue
    
    # =========================================================================
    # STEP 7: CALCULATE FINAL TOTALS
    # =========================================================================
    total_discounts = result['total_scholarship_discount'] + result['total_regular_discount']
    result['total_discounts'] = total_discounts
    
    result['total_before_discounts'] = result['gross_total']
    result['net_total'] = result['gross_total'] - total_discounts
    
    if result['net_total'] < 0:
        result['net_total'] = Decimal('0.00')
    
    logger.info("="*80)
    logger.info("FINAL CALCULATION SUMMARY:")
    logger.info(f"  Gross Total:              {result['gross_total']:>15,.2f}")
    logger.info(f"  - Scholarship Discounts:  {result['total_scholarship_discount']:>15,.2f}")
    logger.info(f"  - Regular Discounts:      {result['total_regular_discount']:>15,.2f}")
    logger.info(f"  = Net Total:              {result['net_total']:>15,.2f}")
    logger.info("="*80)
    
    return result


def _calculate_category_discount(amount, config, scholarship=None):
    """
    Calculate discount based on category-specific configuration.
    Used by both invoice generation and preview calculations.
    
    Args:
        amount: Decimal - Amount to calculate discount for
        config: dict - Category discount configuration
        scholarship: StudentScholarship - For budget checking (optional)
    
    Returns:
        Decimal: Discount amount
    """
    discount_type = config.get('type')
    discount_value = Decimal(str(config.get('value', 0)))
    
    # Calculate base discount
    if discount_type == 'percentage':
        discount = (amount * discount_value / Decimal('100.00')).quantize(Decimal('0.01'))
        
    elif discount_type == 'full_waiver':
        # Full waiver is 100%
        discount = amount
        
    elif discount_type == 'fixed_amount':
        # Fixed amount per invoice item (capped at item amount)
        discount = min(discount_value, amount)
        
    elif discount_type == 'none':
        discount = Decimal('0.00')
        
    else:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Unknown discount type: {discount_type}")
        discount = Decimal('0.00')
    
    # Check budget constraints for budget-based scholarships
    if scholarship and scholarship.is_budget_based():
        remaining_balance = scholarship.get_remaining_balance()
        
        if remaining_balance is not None and remaining_balance > 0:
            # Cap discount at remaining balance
            discount = min(discount, remaining_balance)
        elif remaining_balance is not None and remaining_balance <= 0:
            # Budget exhausted
            discount = Decimal('0.00')
    
    return discount.quantize(Decimal('0.01'))


@require_http_methods(["GET"])
def invoice_bulk_preview_fees(request):
    """
    Calculate estimated fees for students in bulk preview.
    NOW USES UNIFIED CALCULATION FUNCTION.
    """
    session_id = request.GET.get('session_id')
    enrollment_ids = request.GET.get('enrollment_ids', '').split(',')
    
    auto_apply_scholarships = request.GET.get('auto_apply_scholarships', 'true').lower() == 'true'
    auto_apply_discounts = request.GET.get('auto_apply_discounts', 'true').lower() == 'true'
    
    # ✅ GET ISSUE DATE FROM QUERY PARAMS
    issue_date_str = request.GET.get('issue_date')
    
    if not session_id:
        return JsonResponse({'error': 'Missing session_id'}, status=400)
    
    if not enrollment_ids or enrollment_ids == ['']:
        return JsonResponse({'error': 'Missing enrollment_ids'}, status=400)
    
    try:
        from academics.models import StudentClassEnrollment
        
        enrollments = StudentClassEnrollment.objects.filter(
            pk__in=enrollment_ids,
            academic_session_id=session_id
        ).select_related(
            'student',
            'class_instance',
            'class_instance__academic_level'
        ).prefetch_related(
            'student__boarding_enrollments',
            'student__scholarships'
        )
        
        student_fees = {}
        
        # Running totals
        gross_total = Decimal('0.00')
        total_scholarship_discount = Decimal('0.00')
        total_regular_discount = Decimal('0.00')
        net_total = Decimal('0.00')
        
        for enrollment in enrollments:
            try:
                # ✅ USE UNIFIED CALCULATION WITH ISSUE DATE
                calc = _calculate_student_fees(
                    enrollment, 
                    session_id, 
                    auto_apply_scholarships, 
                    auto_apply_discounts,
                    issue_date_str=issue_date_str  # ✅ PASS IT HERE
                )
                
                if calc['error']:
                    student_fees[str(enrollment.pk)] = {
                        'error': calc['error'],
                        'amount': 0,
                        'amount_formatted': 'N/A'
                    }
                    continue
                
                # Format for response
                from core.models import FinancialSettings
                settings = FinancialSettings.get_instance()
                currency = settings.school_currency if settings else 'UGX'
                
                student_fees[str(enrollment.pk)] = {
                    # Gross amounts
                    'gross_amount': float(calc['gross_total']),
                    'gross_amount_formatted': f'{calc["gross_total"]:,.0f}',
                    
                    # Academic/Boarding breakdown
                    'academic_amount': float(calc['academic_subtotal'] + calc['academic_tax']),
                    'boarding_amount': float(calc['boarding_subtotal'] + calc['boarding_tax']),
                    'has_boarding': calc['boarding_enrollment'] is not None,
                    
                    # Discounts
                    'scholarship_discount': float(calc['total_scholarship_discount']),
                    'scholarship_discount_formatted': f'{calc["total_scholarship_discount"]:,.0f}',
                    'regular_discount': float(calc['total_regular_discount']),
                    'regular_discount_formatted': f'{calc["total_regular_discount"]:,.0f}',
                    'total_discount': float(calc['total_discounts']),
                    
                    # Net amount (what student actually pays)
                    'amount': float(calc['net_total']),
                    'amount_formatted': f'{calc["net_total"]:,.0f}',
                    
                    'currency': currency,
                }
                
                # Update running totals
                gross_total += calc['gross_total']
                total_scholarship_discount += calc['total_scholarship_discount']
                total_regular_discount += calc['total_regular_discount']
                net_total += calc['net_total']
                
            except Exception as e:
                logger.error(f"Error calculating fees for enrollment {enrollment.pk}: {e}", exc_info=True)
                student_fees[str(enrollment.pk)] = {
                    'error': str(e),
                    'amount': 0,
                    'amount_formatted': 'Error'
                }
        
        from core.models import FinancialSettings
        settings = FinancialSettings.get_instance()
        currency = settings.school_currency if settings else 'UGX'
        
        return JsonResponse({
            'student_fees': student_fees,
            'gross_total': float(gross_total),
            'gross_total_formatted': f'{gross_total:,.0f}',
            'total_scholarship_discount': float(total_scholarship_discount),
            'total_scholarship_discount_formatted': f'{total_scholarship_discount:,.0f}',
            'total_regular_discount': float(total_regular_discount),
            'total_regular_discount_formatted': f'{total_regular_discount:,.0f}',
            'total_all_discounts': float(total_scholarship_discount + total_regular_discount),
            'total_all_discounts_formatted': f'{(total_scholarship_discount + total_regular_discount):,.0f}',
            'total_fees': float(net_total),
            'total_fees_formatted': f'{net_total:,.0f}',
            'net_total': float(net_total),
            'net_total_formatted': f'{net_total:,.0f}',
            'currency': currency,
            'count': len(student_fees),
            'scholarships_applied': auto_apply_scholarships,
            'discounts_applied': auto_apply_discounts,
            'issue_date': issue_date_str,  # ✅ INCLUDE IN RESPONSE
        })
        
    except Exception as e:
        logger.error(f"Error in invoice_bulk_preview_fees: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


def invoice_bulk_preview_breakdown(request):
    """
    AJAX endpoint to get detailed fee breakdown for a student.
    NOW USES UNIFIED CALCULATION FUNCTION.
    """
    enrollment_id = request.GET.get('enrollment_id')
    session_id = request.GET.get('session_id')
    
    auto_apply_scholarships = request.GET.get('auto_apply_scholarships', 'true').lower() == 'true'
    auto_apply_discounts = request.GET.get('auto_apply_discounts', 'true').lower() == 'true'
    
    # ✅ GET ISSUE DATE FROM QUERY PARAMS
    issue_date_str = request.GET.get('issue_date')
    
    if not enrollment_id or not session_id:
        return render(request, 'fees/invoices/partials/fee_breakdown.html', {
            'error': 'Missing parameters'
        })
    
    try:
        from academics.models import StudentClassEnrollment
        
        enrollment = StudentClassEnrollment.objects.select_related(
            'student',
            'class_instance',
            'class_instance__academic_level'
        ).prefetch_related(
            'student__boarding_enrollments',
            'student__scholarships'
        ).get(pk=enrollment_id, academic_session_id=session_id)
    except StudentClassEnrollment.DoesNotExist:
        return render(request, 'fees/invoices/partials/fee_breakdown.html', {
            'error': 'Enrollment not found'
        })
    
    # ✅ USE UNIFIED CALCULATION WITH ISSUE DATE
    calc = _calculate_student_fees(
        enrollment, 
        session_id, 
        auto_apply_scholarships, 
        auto_apply_discounts,
        issue_date_str=issue_date_str  # ✅ PASS IT HERE
    )
    
    if calc['error']:
        return render(request, 'fees/invoices/partials/fee_breakdown.html', {
            'error': calc['error'],
            'enrollment': enrollment
        })
    
    context = {
        'enrollment': enrollment,
        'boarding_enrollment': calc['boarding_enrollment'],
        'fee_structure': calc['academic_fee_structure'],
        'academic_fee_structure': calc['academic_fee_structure'],
        'boarding_fee_structure': calc.get('boarding_fee_structure'),
        'academic_items': calc['academic_items'],
        'boarding_items': calc['boarding_items'],
        'all_items': calc['academic_items'] + calc['boarding_items'],
        'academic_subtotal': calc['academic_subtotal'],
        'academic_tax_total': calc['academic_tax'],
        'boarding_subtotal': calc['boarding_subtotal'],
        'boarding_tax_total': calc['boarding_tax'],
        'subtotal': calc['subtotal'],
        'tax_total': calc['tax_total'],
        'total_before_discounts': calc['total_before_discounts'],
        'has_boarding': calc['boarding_enrollment'] is not None,
        
        # Scholarship data
        'total_scholarship_discount': calc['total_scholarship_discount'],
        'scholarship_breakdown': calc['scholarship_breakdown'],
        'has_scholarships': len(calc['scholarship_breakdown']) > 0,
        'auto_apply_scholarships': auto_apply_scholarships,
        
        # Discount data
        'total_regular_discount': calc['total_regular_discount'],
        'applied_discounts': calc['discount_breakdown'],
        'has_discounts': len(calc['discount_breakdown']) > 0,
        'auto_apply_discounts': auto_apply_discounts,
        
        # Final totals
        'total_discounts': calc['total_discounts'],
        'final_total': calc['net_total'],
        
        # ✅ ADD ISSUE DATE TO CONTEXT
        'issue_date': issue_date_str,
    }
    
    return render(request, 'fees/invoices/partials/fee_breakdown.html', context)

def _find_applicable_academic_structure(class_enrollment):
    """
    Find the most appropriate academic fee structure for a class enrollment.
    
    This is a simplified version for preview purposes.
    For actual invoice generation, use UnifiedStudentInvoiceGenerator._find_applicable_fee_structure()
    
    Args:
        class_enrollment: StudentClassEnrollment instance
        
    Returns:
        FeesStructure instance or None
    """
    from fees.models import FeesStructure
    
    student = class_enrollment.student
    class_instance = class_enrollment.class_instance
    session = class_enrollment.academic_session
    
    # Start with structures for this session and level
    structures = FeesStructure.objects.filter(
        is_active=True,
        applicable_sessions__id=session.id,
        academic_levels__id=class_instance.academic_level.id,
        # ✅ Only academic structures (not boarding-only)
        boarding_type_filter__in=['ALL', 'DAY_ONLY']
    ).order_by('priority')
    
    # Filter by specific classes if structure has class restrictions
    structures_with_classes = structures.filter(
        applicable_classes__isnull=False
    ).distinct()
    
    if structures_with_classes.exists():
        structures = structures.filter(
            applicable_classes__id=class_instance.id
        )
    
    # Filter by student attributes
    for structure in structures:
        if structure.is_applicable_to_student(student, session):
            return structure
    
    return None

@login_required
@require_http_methods(["POST"])
def invoice_single_generate(request, enrollment_id):
    """Generate a single invoice for a class enrollment"""
    from academics.models import StudentClassEnrollment
    from .invoice_generators import generate_student_enrollment_invoice
    
    try:
        enrollment = StudentClassEnrollment.objects.select_related(
            'student', 'class_instance', 'academic_session'
        ).get(pk=enrollment_id)
        
        # Check if already has invoice
        if enrollment.academic_invoice:
            messages.warning(
                request,
                f"Student {enrollment.student.get_full_name()} already has an invoice",
                extra_tags='sweetalert'
            )
            return redirect('academics:enrollment_detail', pk=enrollment_id)
        
        # Generate invoice
        invoice = generate_student_enrollment_invoice(
            enrollment,
            auto_apply_scholarships=True,
            auto_apply_discounts=True
        )
        
        messages.success(
            request,
            f'Invoice {invoice.invoice_number} generated successfully!',
            extra_tags='sweetalert'
        )
        
        return redirect('fees:invoice_detail', pk=invoice.pk)
        
    except Exception as e:
        logger.exception(f"Error generating invoice for enrollment {enrollment_id}")
        messages.error(
            request,
            f'Error generating invoice: {str(e)}',
            extra_tags='sweetalert-error'
        )
        return redirect('academics:enrollment_detail', pk=enrollment_id)


@login_required
@require_http_methods(["POST"])
def invoice_regenerate(request, invoice_id):
    """
    Regenerate an existing invoice (useful for fee structure changes).
    
    This will:
    1. Cancel the old invoice
    2. Generate a new invoice with current fee structures
    """
    from fees.models import FeeInvoice
    
    try:
        old_invoice = FeeInvoice.objects.select_related(
            'student',
            'academic_session'
        ).get(pk=invoice_id)
        
        # Find the enrollment
        enrollment = old_invoice.student.class_enrollments.filter(
            academic_session=old_invoice.academic_session,
            is_active=True
        ).first()
        
        if not enrollment:
            messages.error(
                request,
                "❌ Cannot regenerate: No active enrollment found for this invoice"
            )
            return redirect('fees:invoice_detail', pk=invoice_id)
        
        # Check if invoice has payments
        if old_invoice.paid_amount > 0:
            messages.warning(
                request,
                "⚠️ This invoice has payments. Regenerating will create a new invoice "
                "and cancel this one. Existing payments will need to be reallocated."
            )
        
        with transaction.atomic():
            # Cancel old invoice
            old_invoice.status = 'CANCELLED'
            old_invoice.notes = (
                f"{old_invoice.notes}\n\n"
                f"CANCELLED: Regenerated as new invoice on {timezone.now().date()}"
            )
            old_invoice.save()

            from invoice_generators import generate_student_enrollment_invoice

            # Generate new invoice
            new_invoice = generate_student_enrollment_invoice(
                enrollment,
                auto_apply_scholarships=True,
                auto_apply_discounts=True,
                force=True  # Force generation even if enrollment has invoice
            )
            
            messages.success(
                request,
                f"✅ New invoice {new_invoice.invoice_number} generated successfully! "
                f"Old invoice {old_invoice.invoice_number} has been cancelled."
            )
            
            return redirect('fees:invoice_detail', pk=new_invoice.pk)
            
    except FeeInvoice.DoesNotExist:
        messages.error(request, "❌ Invoice not found")
        return redirect('fees:invoice_list')
    
    except Exception as e:
        logger.exception(f"Error regenerating invoice {invoice_id}")
        messages.error(request, f"❌ Error regenerating invoice: {str(e)}")
        return redirect('fees:invoice_detail', pk=invoice_id)
    
@login_required
@require_http_methods(["POST"])
def invoice_delete(request, pk):
    """Delete invoice with HTMX support"""
    invoice = get_object_or_404(FeeInvoice, pk=pk)
    
    # Check if invoice can be deleted
    if invoice.status in ['PAID', 'PARTIALLY_PAID'] or invoice.payments.exists():
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Cannot delete invoice '{invoice.invoice_number}' because it has payments"
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Cannot Delete'
            response['HX-Close-Modal'] = 'true'
            return response
        else:
            messages.error(
                request,
                f"Cannot delete invoice '{invoice.invoice_number}' because it has payments",
                extra_tags='sweetalert-error'
            )
            return redirect('fees:invoice_detail', pk=pk)
    
    invoice_number = invoice.invoice_number
    invoice.delete()
    
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    if is_htmx:
        response = HttpResponse()
        response['HX-Alert-Message'] = f"Invoice '{invoice_number}' deleted successfully"
        response['HX-Alert-Type'] = 'success'
        response['HX-Alert-Title'] = 'Deleted!'
        response['HX-Close-Modal'] = 'true'
        response['HX-Redirect'] = reverse('fees:invoice_list')
        return response
    else:
        messages.success(
            request,
            f"Invoice '{invoice_number}' deleted successfully",
            extra_tags='sweetalert'
        )
        return redirect('fees:invoice_list')
    
@login_required
@require_http_methods(["POST"])
def invoice_void(request, pk):
    """
    Void/cancel an invoice.
    
    Difference from delete:
    - Void keeps the record for audit trail
    - Delete permanently removes
    """
    invoice = get_object_or_404(FeeInvoice, pk=pk)
    
    # Check if can be voided
    if invoice.status in ['VOID', 'CANCELLED']:
        messages.warning(request, 'Invoice is already voided/cancelled.')
        return redirect('fees:invoice_detail', pk=pk)
    
    if invoice.status == 'PAID':
        messages.error(request, 'Cannot void paid invoices. Use refund process instead.')
        return redirect('fees:invoice_detail', pk=pk)
    
    try:
        void_reason = request.POST.get('void_reason', '')
        
        with transaction.atomic():
            # Update invoice status
            old_status = invoice.status
            invoice.status = 'VOID'
            invoice.notes = f"{invoice.notes}\n\nVOIDED on {timezone.now().date()}: {void_reason}".strip()
            invoice.save()
            
            # Reverse any payments
            if invoice.payments.exists():
                for payment in invoice.payments.all():
                    payment.reversed = True
                    payment.reversed_on = timezone.now()
                    payment.reversed_by_id = str(request.user.id)
                    payment.reversal_reason = f"Invoice voided: {void_reason}"
                    payment.status = 'REVERSED'
                    payment.save()
            
            # Create negative transaction to reverse the invoice
            student_account, _ = StudentAccount.objects.get_or_create(
                student=invoice.student
            )
            
            AccountTransaction.objects.create(
                student_account=student_account,
                transaction_type='ADJUSTMENT',
                amount=invoice.total_amount,  # Positive to reverse negative invoice
                description=f"Void invoice {invoice.invoice_number}: {void_reason}",
                reference_number=f"VOID-{invoice.invoice_number}",
                balance_after=student_account.get_current_balance() + invoice.total_amount,
                invoice=invoice,
                academic_session=invoice.academic_session,
                fiscal_period=invoice.fiscal_period,
                processed_by_id=str(request.user.id),
            )
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Invoice {invoice.invoice_number} voided successfully!"
            response['HX-Alert-Type'] = 'success'
            response['HX-Alert-Title'] = 'Invoice Voided'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('fees:invoice_detail', kwargs={'pk': invoice.pk})
            return response
        else:
            messages.success(request, f"Invoice {invoice.invoice_number} voided successfully!")
            return redirect('fees:invoice_detail', pk=invoice.pk)
    
    except Exception as e:
        logger.error(f"Error voiding invoice: {e}", exc_info=True)
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f'Error voiding invoice: {str(e)}'
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Error'
            return response
        else:
            messages.error(request, f'Error voiding invoice: {str(e)}')
            return redirect('fees:invoice_detail', pk=pk)


@login_required
@require_http_methods(["POST"])
def invoice_apply_penalty(request, pk):
    """Apply late fee penalty to overdue invoice"""
    invoice = get_object_or_404(FeeInvoice, pk=pk)
    
    today = get_school_today()
    
    if invoice.due_date >= today:
        messages.warning(request, 'Invoice is not yet overdue.')
        return redirect('fees:invoice_detail', pk=pk)
    
    if invoice.status not in ['PENDING', 'PARTIALLY_PAID', 'OVERDUE']:
        messages.warning(request, 'Cannot apply penalty to this invoice status.')
        return redirect('fees:invoice_detail', pk=pk)
    
    try:
        penalty_amount = Decimal(request.POST.get('penalty_amount', '0.00'))
        penalty_reason = request.POST.get('penalty_reason', '')
        
        if penalty_amount <= 0:
            raise ValueError("Penalty amount must be positive")
        
        with transaction.atomic():
            # Update invoice
            invoice.late_fee_amount = invoice.late_fee_amount + penalty_amount
            invoice.total_amount = invoice.total_amount + penalty_amount
            invoice.balance = invoice.balance + penalty_amount
            invoice.status = 'OVERDUE'
            invoice.notes = f"{invoice.notes}\n\nPenalty of {penalty_amount} applied on {today}: {penalty_reason}".strip()
            invoice.save()
            
            # Create transaction
            student_account, _ = StudentAccount.objects.get_or_create(
                student=invoice.student
            )
            
            AccountTransaction.objects.create(
                student_account=student_account,
                transaction_type='INVOICE',
                amount=-penalty_amount,  # Negative = charge
                description=f"Late fee penalty on invoice {invoice.invoice_number}: {penalty_reason}",
                reference_number=f"PENALTY-{invoice.invoice_number}",
                balance_after=student_account.get_current_balance() - penalty_amount,
                invoice=invoice,
                academic_session=invoice.academic_session,
                fiscal_period=invoice.fiscal_period,
                processed_by_id=str(request.user.id),
            )
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Late fee penalty of {penalty_amount:,.2f} applied successfully!"
            response['HX-Alert-Type'] = 'success'
            response['HX-Alert-Title'] = 'Penalty Applied'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('fees:invoice_detail', kwargs={'pk': invoice.pk})
            return response
        else:
            messages.success(request, f"Late fee penalty of {penalty_amount:,.2f} applied successfully!")
            return redirect('fees:invoice_detail', pk=invoice.pk)
    
    except Exception as e:
        logger.error(f"Error applying penalty: {e}", exc_info=True)
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f'Error applying penalty: {str(e)}'
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Error'
            return response
        else:
            messages.error(request, f'Error applying penalty: {str(e)}')
            return redirect('fees:invoice_detail', pk=pk)


@login_required
@require_http_methods(["POST"])
def invoice_waive_late_fees(request, pk):
    """Waive late fees on an invoice (goodwill gesture)"""
    invoice = get_object_or_404(FeeInvoice, pk=pk)
    
    if invoice.late_fee_amount <= 0:
        messages.info(request, 'Invoice has no late fees to waive.')
        return redirect('fees:invoice_detail', pk=pk)
    
    try:
        waive_reason = request.POST.get('waive_reason', '')
        waive_amount = Decimal(request.POST.get('waive_amount', str(invoice.late_fee_amount)))
        
        if waive_amount > invoice.late_fee_amount:
            waive_amount = invoice.late_fee_amount
        
        with transaction.atomic():
            # Update invoice
            invoice.late_fee_amount = invoice.late_fee_amount - waive_amount
            invoice.total_amount = invoice.total_amount - waive_amount
            invoice.balance = invoice.balance - waive_amount
            invoice.notes = f"{invoice.notes}\n\nLate fees of {waive_amount} waived on {get_school_today()}: {waive_reason}".strip()
            invoice.save()
            
            # Create positive adjustment transaction
            student_account, _ = StudentAccount.objects.get_or_create(
                student=invoice.student
            )
            
            AccountTransaction.objects.create(
                student_account=student_account,
                transaction_type='ADJUSTMENT',
                amount=waive_amount,  # Positive = credit
                description=f"Late fee waiver on invoice {invoice.invoice_number}: {waive_reason}",
                reference_number=f"WAIVE-{invoice.invoice_number}",
                balance_after=student_account.get_current_balance() + waive_amount,
                invoice=invoice,
                academic_session=invoice.academic_session,
                fiscal_period=invoice.fiscal_period,
                processed_by_id=str(request.user.id),
            )
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Late fees of {waive_amount:,.2f} waived successfully!"
            response['HX-Alert-Type'] = 'success'
            response['HX-Alert-Title'] = 'Fees Waived'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('fees:invoice_detail', kwargs={'pk': invoice.pk})
            return response
        else:
            messages.success(request, f"Late fees of {waive_amount:,.2f} waived successfully!")
            return redirect('fees:invoice_detail', pk=invoice.pk)
    
    except Exception as e:
        logger.error(f"Error waiving late fees: {e}", exc_info=True)
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f'Error waiving fees: {str(e)}'
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Error'
            return response
        else:
            messages.error(request, f'Error waiving fees: {str(e)}')
            return redirect('fees:invoice_detail', pk=pk)


@login_required
@require_http_methods(["POST"])
def invoice_adjust_amount(request, pk):
    """
    Adjust invoice amount (increase or decrease).
    
    Use cases:
    - Add forgotten charges
    - Remove incorrect charges
    - Price corrections
    """
    invoice = get_object_or_404(FeeInvoice, pk=pk)
    
    if invoice.status in ['PAID', 'VOID', 'CANCELLED']:
        messages.error(request, f"Cannot adjust {invoice.get_status_display()} invoice.")
        return redirect('fees:invoice_detail', pk=pk)
    
    try:
        adjustment_type = request.POST.get('adjustment_type')  # INCREASE or DECREASE
        adjustment_amount = Decimal(request.POST.get('adjustment_amount', '0.00'))
        adjustment_reason = request.POST.get('adjustment_reason', '')
        
        if adjustment_amount <= 0:
            raise ValueError("Adjustment amount must be positive")
        
        if not adjustment_reason:
            raise ValueError("Adjustment reason is required")
        
        with transaction.atomic():
            if adjustment_type == 'INCREASE':
                invoice.total_amount += adjustment_amount
                invoice.balance += adjustment_amount
                transaction_amount = -adjustment_amount  # Negative = charge
                description = f"Invoice adjustment (increase): {adjustment_reason}"
            else:  # DECREASE
                if adjustment_amount > invoice.balance:
                    raise ValueError("Cannot decrease by more than current balance")
                invoice.total_amount -= adjustment_amount
                invoice.balance -= adjustment_amount
                transaction_amount = adjustment_amount  # Positive = credit
                description = f"Invoice adjustment (decrease): {adjustment_reason}"
            
            invoice.notes = f"{invoice.notes}\n\nAmount adjusted by {adjustment_amount} ({adjustment_type}) on {get_school_today()}: {adjustment_reason}".strip()
            invoice.save()
            
            # Create transaction
            student_account, _ = StudentAccount.objects.get_or_create(
                student=invoice.student
            )
            
            AccountTransaction.objects.create(
                student_account=student_account,
                transaction_type='ADJUSTMENT',
                amount=transaction_amount,
                description=description,
                reference_number=f"ADJ-{invoice.invoice_number}",
                balance_after=student_account.get_current_balance() + transaction_amount,
                invoice=invoice,
                academic_session=invoice.academic_session,
                fiscal_period=invoice.fiscal_period,
                processed_by_id=str(request.user.id),
            )
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Invoice adjusted by {adjustment_amount:,.2f} successfully!"
            response['HX-Alert-Type'] = 'success'
            response['HX-Alert-Title'] = 'Invoice Adjusted'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('fees:invoice_detail', kwargs={'pk': invoice.pk})
            return response
        else:
            messages.success(request, f"Invoice adjusted by {adjustment_amount:,.2f} successfully!")
            return redirect('fees:invoice_detail', pk=invoice.pk)
    
    except Exception as e:
        logger.error(f"Error adjusting invoice: {e}", exc_info=True)
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f'Error adjusting invoice: {str(e)}'
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Error'
            return response
        else:
            messages.error(request, f'Error adjusting invoice: {str(e)}')
            return redirect('fees:invoice_detail', pk=pk)


@login_required
@require_http_methods(["POST"])
def invoice_send_email(request, pk):
    """Send invoice via email to student/parents"""
    invoice = get_object_or_404(FeeInvoice, pk=pk)
    
    try:
        # Get recipient emails from form
        recipient_emails = request.POST.getlist('recipients')
        include_pdf = request.POST.get('include_pdf', 'true') == 'true'
        custom_message = request.POST.get('custom_message', '')
        
        if not recipient_emails:
            raise ValueError("At least one recipient email is required")
        
        # Render email content
        email_context = {
            'invoice': invoice,
            'custom_message': custom_message,
            'school_name': getattr(settings, 'SCHOOL_NAME', 'School'),
        }
        
        email_body = render_to_string('fees/emails/invoice_email.html', email_context)
        
        # Send email
        send_mail(
            subject=f"Fee Invoice {invoice.invoice_number} - {invoice.student.get_full_name()}",
            message='',  # Plain text version
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipient_emails,
            html_message=email_body,
            fail_silently=False,
        )
        
        # Log email sent
        invoice.notes = f"{invoice.notes}\n\nInvoice emailed to {', '.join(recipient_emails)} on {timezone.now()}".strip()
        invoice.save()
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Invoice sent to {len(recipient_emails)} recipient(s) successfully!"
            response['HX-Alert-Type'] = 'success'
            response['HX-Alert-Title'] = 'Email Sent'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('fees:invoice_detail', kwargs={'pk': invoice.pk})
            return response
        else:
            messages.success(request, f"Invoice sent to {len(recipient_emails)} recipient(s) successfully!")
            return redirect('fees:invoice_detail', pk=invoice.pk)
    
    except Exception as e:
        logger.error(f"Error sending invoice email: {e}", exc_info=True)
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f'Error sending email: {str(e)}'
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Error'
            return response
        else:
            messages.error(request, f'Error sending email: {str(e)}')
            return redirect('fees:invoice_detail', pk=pk)


@login_required
@require_http_methods(["POST"])
def send_payment_reminder(request, pk):
    """Send payment reminder email for overdue invoice"""
    invoice = get_object_or_404(FeeInvoice, pk=pk)
    
    today = get_school_today()
    
    if invoice.due_date >= today:
        messages.warning(request, 'Invoice is not yet overdue.')
        return redirect('fees:invoice_detail', pk=pk)
    
    try:
        recipient_emails = request.POST.getlist('recipients')
        reminder_type = request.POST.get('reminder_type', 'FRIENDLY')  # FRIENDLY, URGENT, FINAL
        
        if not recipient_emails:
            raise ValueError("At least one recipient email is required")
        
        days_overdue = (today - invoice.due_date).days
        
        # Render reminder email
        email_context = {
            'invoice': invoice,
            'days_overdue': days_overdue,
            'reminder_type': reminder_type,
            'school_name': getattr(settings, 'SCHOOL_NAME', 'School'),
        }
        
        subject_map = {
            'FRIENDLY': f"Payment Reminder: Invoice {invoice.invoice_number}",
            'URGENT': f"URGENT: Overdue Payment - Invoice {invoice.invoice_number}",
            'FINAL': f"FINAL NOTICE: Payment Required - Invoice {invoice.invoice_number}",
        }
        
        email_body = render_to_string('fees/emails/payment_reminder.html', email_context)
        
        send_mail(
            subject=subject_map.get(reminder_type, subject_map['FRIENDLY']),
            message='',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipient_emails,
            html_message=email_body,
            fail_silently=False,
        )
        
        # Log reminder sent
        invoice.notes = f"{invoice.notes}\n\n{reminder_type} payment reminder sent to {', '.join(recipient_emails)} on {timezone.now()}".strip()
        invoice.save()
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Payment reminder sent to {len(recipient_emails)} recipient(s)!"
            response['HX-Alert-Type'] = 'success'
            response['HX-Alert-Title'] = 'Reminder Sent'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('fees:invoice_detail', kwargs={'pk': invoice.pk})
            return response
        else:
            messages.success(request, f"Payment reminder sent to {len(recipient_emails)} recipient(s)!")
            return redirect('fees:invoice_detail', pk=invoice.pk)
    
    except Exception as e:
        logger.error(f"Error sending payment reminder: {e}", exc_info=True)
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f'Error sending reminder: {str(e)}'
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Error'
            return response
        else:
            messages.error(request, f'Error sending reminder: {str(e)}')
            return redirect('fees:invoice_detail', pk=pk)


@login_required
@require_http_methods(["POST"])
def invoice_clone_to_student(request, pk):
    """
    Clone an invoice to another student.
    
    Use case: Similar fee structure for multiple students
    """
    original_invoice = get_object_or_404(FeeInvoice, pk=pk)
    
    try:
        target_student_id = request.POST.get('target_student')
        adjust_amounts = request.POST.get('adjust_amounts', 'false') == 'true'
        
        if not target_student_id:
            raise ValueError("Target student is required")
        
        target_student = get_object_or_404(Student, pk=target_student_id)
        
        with transaction.atomic():
            # Clone the invoice
            new_invoice = FeeInvoice.objects.create(
                student=target_student,
                academic_session=original_invoice.academic_session,
                fiscal_period=original_invoice.fiscal_period,
                fee_structure=original_invoice.fee_structure,
                invoice_number=None,  # Will be auto-generated
                issue_date=get_school_today(),
                due_date=original_invoice.due_date,
                payment_terms=original_invoice.payment_terms,
                subtotal=original_invoice.subtotal,
                discount_amount=Decimal('0.00') if adjust_amounts else original_invoice.discount_amount,
                scholarship_discount_amount=Decimal('0.00'),  # Don't copy scholarships
                tax_amount=original_invoice.tax_amount,
                total_amount=original_invoice.total_amount - (original_invoice.discount_amount if adjust_amounts else 0),
                paid_amount=Decimal('0.00'),
                balance=original_invoice.total_amount - (original_invoice.discount_amount if adjust_amounts else 0),
                status='PENDING',
                notes=f"Cloned from invoice {original_invoice.invoice_number}",
            )
            
            # Clone items
            for item in original_invoice.items.all():
                FeeInvoiceItem.objects.create(
                    invoice=new_invoice,
                    fee_category=item.fee_category,
                    description=item.description,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    amount=item.amount,
                    tax_percentage=item.tax_percentage,
                    tax_amount=item.tax_amount,
                    discount_percentage=Decimal('0.00') if adjust_amounts else item.discount_percentage,
                    discount_amount=Decimal('0.00') if adjust_amounts else item.discount_amount,
                    scholarship_discount_amount=Decimal('0.00'),
                    final_amount=item.amount + item.tax_amount - (item.discount_amount if not adjust_amounts else 0),
                )
            
            # Create transaction
            student_account, _ = StudentAccount.objects.get_or_create(
                student=target_student
            )
            
            AccountTransaction.objects.create(
                student_account=student_account,
                transaction_type='INVOICE',
                amount=-new_invoice.total_amount,
                description=f"Invoice {new_invoice.invoice_number} (cloned)",
                reference_number=new_invoice.invoice_number,
                balance_after=student_account.get_current_balance() - new_invoice.total_amount,
                invoice=new_invoice,
                academic_session=new_invoice.academic_session,
                fiscal_period=new_invoice.fiscal_period,
            )
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Invoice cloned successfully as {new_invoice.invoice_number}!"
            response['HX-Alert-Type'] = 'success'
            response['HX-Alert-Title'] = 'Invoice Cloned'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('fees:invoice_detail', kwargs={'pk': new_invoice.pk})
            return response
        else:
            messages.success(request, f"Invoice cloned successfully as {new_invoice.invoice_number}!")
            return redirect('fees:invoice_detail', pk=new_invoice.pk)
    
    except Exception as e:
        logger.error(f"Error cloning invoice: {e}", exc_info=True)
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f'Error cloning invoice: {str(e)}'
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Error'
            return response
        else:
            messages.error(request, f'Error cloning invoice: {str(e)}')
            return redirect('fees:invoice_detail', pk=pk)


@login_required
@require_http_methods(["POST"])
def invoice_merge(request):
    """
    Merge multiple invoices into one.
    
    Requirements:
    - All invoices must belong to same student
    - No invoice can be PAID
    """
    try:
        invoice_ids = request.POST.getlist('invoice_ids')
        
        if len(invoice_ids) < 2:
            raise ValueError("At least 2 invoices required for merge")
        
        invoices = FeeInvoice.objects.filter(pk__in=invoice_ids).select_related('student')
        
        # Validate all belong to same student
        students = set(inv.student for inv in invoices)
        if len(students) > 1:
            raise ValueError("All invoices must belong to the same student")
        
        # Validate no paid invoices
        if invoices.filter(status='PAID').exists():
            raise ValueError("Cannot merge paid invoices")
        
        student = invoices.first().student
        
        with transaction.atomic():
            # Create merged invoice
            merged_invoice = FeeInvoice.objects.create(
                student=student,
                academic_session=invoices.first().academic_session,
                fiscal_period=invoices.first().fiscal_period,
                fee_structure=invoices.first().fee_structure,
                issue_date=get_school_today(),
                due_date=min(inv.due_date for inv in invoices),
                subtotal=sum(inv.subtotal for inv in invoices),
                discount_amount=sum(inv.discount_amount for inv in invoices),
                scholarship_discount_amount=sum(inv.scholarship_discount_amount for inv in invoices),
                tax_amount=sum(inv.tax_amount for inv in invoices),
                total_amount=sum(inv.total_amount for inv in invoices),
                paid_amount=sum(inv.paid_amount for inv in invoices),
                balance=sum(inv.balance for inv in invoices),
                status='PENDING',
                notes=f"Merged from invoices: {', '.join(inv.invoice_number for inv in invoices)}",
            )
            
            # Copy all items
            for invoice in invoices:
                for item in invoice.items.all():
                    FeeInvoiceItem.objects.create(
                        invoice=merged_invoice,
                        fee_category=item.fee_category,
                        description=f"{item.description} (from {invoice.invoice_number})",
                        quantity=item.quantity,
                        unit_price=item.unit_price,
                        amount=item.amount,
                        tax_percentage=item.tax_percentage,
                        tax_amount=item.tax_amount,
                        discount_percentage=item.discount_percentage,
                        discount_amount=item.discount_amount,
                        scholarship_discount_amount=item.scholarship_discount_amount,
                        final_amount=item.final_amount,
                    )
            
            # Void old invoices
            for invoice in invoices:
                invoice.status = 'VOID'
                invoice.notes = f"{invoice.notes}\n\nMerged into {merged_invoice.invoice_number}".strip()
                invoice.save()
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"{len(invoice_ids)} invoices merged successfully into {merged_invoice.invoice_number}!"
            response['HX-Alert-Type'] = 'success'
            response['HX-Alert-Title'] = 'Invoices Merged'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('fees:invoice_detail', kwargs={'pk': merged_invoice.pk})
            return response
        else:
            messages.success(request, f"{len(invoice_ids)} invoices merged successfully!")
            return redirect('fees:invoice_detail', pk=merged_invoice.pk)
    
    except Exception as e:
        logger.error(f"Error merging invoices: {e}", exc_info=True)
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f'Error merging invoices: {str(e)}'
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Error'
            return response
        else:
            messages.error(request, f'Error merging invoices: {str(e)}')
            return redirect('fees:invoice_list')


@login_required
@require_http_methods(["POST"])
def invoice_split(request, pk):
    """
    Split invoice into installments.
    
    Creates multiple smaller invoices from one large invoice.
    """
    original_invoice = get_object_or_404(FeeInvoice, pk=pk)
    
    if original_invoice.status != 'PENDING':
        messages.error(request, 'Can only split PENDING invoices.')
        return redirect('fees:invoice_detail', pk=pk)
    
    if original_invoice.paid_amount > 0:
        messages.error(request, 'Cannot split invoice with payments.')
        return redirect('fees:invoice_detail', pk=pk)
    
    try:
        num_installments = int(request.POST.get('num_installments', '2'))
        
        if num_installments < 2 or num_installments > 12:
            raise ValueError("Number of installments must be between 2 and 12")
        
        with transaction.atomic():
            # Calculate installment amount
            installment_amount = (original_invoice.total_amount / num_installments).quantize(Decimal('0.01'))
            
            # Handle rounding difference
            total_allocated = installment_amount * (num_installments - 1)
            last_installment_amount = original_invoice.total_amount - total_allocated
            
            # Get billing periods
            fiscal_periods = original_invoice.academic_session.fiscal_periods.filter(
                is_active=True,
                is_closed=False
            ).order_by('period_number')[:num_installments]
            
            # Create installment invoices
            for i in range(num_installments):
                amount = last_installment_amount if i == num_installments - 1 else installment_amount
                
                # Calculate due date
                if i < len(fiscal_periods):
                    due_date = fiscal_periods[i].end_date
                else:
                    # Default to 30 days apart
                    due_date = original_invoice.due_date + timedelta(days=30 * i)
                
                installment_invoice = FeeInvoice.objects.create(
                    student=original_invoice.student,
                    academic_session=original_invoice.academic_session,
                    fiscal_period=fiscal_periods[i] if i < len(fiscal_periods) else original_invoice.fiscal_period,
                    fee_structure=original_invoice.fee_structure,
                    issue_date=get_school_today(),
                    due_date=due_date,
                    subtotal=amount,
                    total_amount=amount,
                    balance=amount,
                    status='PENDING',
                    notes=f"Installment {i+1} of {num_installments} from invoice {original_invoice.invoice_number}",
                )
                
                # Create single item for installment
                FeeInvoiceItem.objects.create(
                    invoice=installment_invoice,
                    fee_category=original_invoice.items.first().fee_category,
                    description=f"Installment {i+1}/{num_installments}",
                    amount=amount,
                    final_amount=amount,
                )
                
                # Create transaction
                student_account, _ = StudentAccount.objects.get_or_create(
                    student=original_invoice.student
                )
                
                AccountTransaction.objects.create(
                    student_account=student_account,
                    transaction_type='INVOICE',
                    amount=-amount,
                    description=f"Invoice {installment_invoice.invoice_number} (installment)",
                    reference_number=installment_invoice.invoice_number,
                    balance_after=student_account.get_current_balance() - amount,
                    invoice=installment_invoice,
                    academic_session=installment_invoice.academic_session,
                    fiscal_period=installment_invoice.fiscal_period,
                )
            
            # Void original invoice
            original_invoice.status = 'VOID'
            original_invoice.notes = f"{original_invoice.notes}\n\nSplit into {num_installments} installments".strip()
            original_invoice.save()
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Invoice split into {num_installments} installments successfully!"
            response['HX-Alert-Type'] = 'success'
            response['HX-Alert-Title'] = 'Invoice Split'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('fees:invoice_list')
            return response
        else:
            messages.success(request, f"Invoice split into {num_installments} installments successfully!")
            return redirect('fees:invoice_list')
    
    except Exception as e:
        logger.error(f"Error splitting invoice: {e}", exc_info=True)
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f'Error splitting invoice: {str(e)}'
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Error'
            return response
        else:
            messages.error(request, f'Error splitting invoice: {str(e)}')
            return redirect('fees:invoice_detail', pk=pk)
        
@login_required
@require_http_methods(["POST"])
def invoice_finalize(request, pk):
    """
    Finalize invoice (DRAFT → PENDING).
    
    This will:
    - Change invoice status to PENDING
    - Update existing journal entry (if exists) OR create new one
    - Post the journal entry (DRAFT → POSTED)
    - Allow payments to be received
    
    Journal Entry Update Logic:
    - DELETES all existing transactions
    - RE-CREATES transactions with current invoice amounts
    - This ensures revenue split matches current invoice items
    """
    invoice = get_object_or_404(FeeInvoice, pk=pk)
    
    # Check if invoice is already finalized
    if invoice.status != 'DRAFT':
        error_msg = f"Invoice is already {invoice.get_status_display()}"
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = error_msg
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Cannot Finalize'
            return response
        else:
            messages.error(request, error_msg)
            return redirect('fees:invoice_detail', pk=pk)
    
    try:
        with transaction.atomic():
            from finance.models import Journal, JournalEntry, JournalTransaction
            from core.models import FinancialSettings
            from django.db.models import Sum
            
            # ================================================================
            # CHECK FOR ZERO-AMOUNT INVOICE (SKIP JOURNAL ENTRY)
            # ================================================================
            
            if invoice.total_amount <= Decimal('0.00'):
                logger.info(
                    f"Skipping journal entry for {invoice.invoice_number} - "
                    f"zero amount invoice (full scholarship/waiver applied)"
                )
                
                # Just change status to PENDING (no journal entry needed)
                invoice.status = 'PENDING'
                invoice.save(update_fields=['status'])
                
                success_msg = (
                    f"Invoice {invoice.invoice_number} finalized successfully! "
                    f"(No journal entry created - zero amount invoice)"
                )
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = success_msg
                    response['HX-Alert-Type'] = 'success'
                    response['HX-Alert-Title'] = 'Invoice Finalized'
                    response['HX-Close-Modal'] = 'true'
                    response['HX-Redirect'] = reverse('fees:invoice_detail', kwargs={'pk': invoice.pk})
                    return response
                else:
                    messages.success(request, success_msg)
                    return redirect('fees:invoice_detail', pk=invoice.pk)
            
            # ================================================================
            # GET ACCOUNT MAPPINGS
            # ================================================================
            
            settings = FinancialSettings.get_instance()
            if not settings or not hasattr(settings, 'account_mappings'):
                from django.core.exceptions import ValidationError
                raise ValidationError("Account mappings not configured. Please set up financial settings.")
            
            mappings = settings.account_mappings
            receivable_account = mappings.student_receivables_account
            
            # Get Fee Collection Journal
            fees_journal, _ = Journal.objects.get_or_create(
                journal_type='FEES',
                defaults={
                    'name': 'Fee Collection Journal',
                    'description': 'Student fee invoices and collections',
                    'is_active': True,
                }
            )
            
            # ================================================================
            # UPDATE OR CREATE JOURNAL ENTRY
            # ================================================================
            
            journal_entry_created = False
            
            if invoice.journal_entry:
                # ============================================================
                # SCENARIO: Journal entry exists (revert → modify → finalize)
                # ============================================================
                
                journal_entry = invoice.journal_entry
                old_entry_number = journal_entry.entry_number
                
                logger.info(
                    f"Updating existing journal entry {old_entry_number} "
                    f"for invoice {invoice.invoice_number}"
                )
                
                # Update journal entry header
                journal_entry.entry_date = invoice.issue_date
                journal_entry.fiscal_period = invoice.fiscal_period
                journal_entry.academic_session = invoice.academic_session
                journal_entry.description = (
                    f"Student Fee Invoice - {invoice.student.get_full_name()} (Updated)"
                )
                journal_entry.save(update_fields=[
                    'entry_date',
                    'fiscal_period',
                    'academic_session',
                    'description'
                ])
                
                # ============================================================
                # DELETE OLD TRANSACTIONS AND CREATE NEW ONES
                # ============================================================
                # This is simpler and more reliable than trying to update
                # multiple revenue lines that may have changed
                
                journal_entry.transactions.all().delete()
                logger.info(f"Deleted old transactions from {old_entry_number}")
                
            else:
                # ============================================================
                # SCENARIO: No journal entry exists (first-time finalization)
                # ============================================================
                
                logger.info(
                    f"Creating new journal entry for invoice {invoice.invoice_number}"
                )
                
                # Generate entry number
                from finance.utils import generate_journal_entry_number
                entry_number = generate_journal_entry_number(fees_journal)
                
                # Create journal entry
                journal_entry = JournalEntry.objects.create(
                    entry_number=entry_number,
                    journal=fees_journal,
                    entry_date=invoice.issue_date,
                    fiscal_period=invoice.fiscal_period,
                    academic_session=invoice.academic_session,
                    reference_number=invoice.invoice_number,
                    description=f"Student Fee Invoice - {invoice.student.get_full_name()}",
                    status='DRAFT',
                )
                
                # Link to invoice
                invoice.journal_entry = journal_entry
                
                journal_entry_created = True
                
                logger.info(f"Created journal entry {journal_entry.entry_number}")
            
            # ================================================================
            # CREATE JOURNAL TRANSACTIONS (DEBIT + CREDITS)
            # ================================================================
            
            # DEBIT: Student Receivables (single line)
            JournalTransaction.objects.create(
                journal_entry=journal_entry,
                account=receivable_account,
                amount=invoice.total_amount,
                is_debit=True,
                description=f"Student fees - {invoice.student.get_full_name()}",
            )
            
            # CREDIT: Revenue accounts (split by category type)
            # This logic matches your invoice_generators.py exactly
            
            revenue_breakdown = invoice.items.values(
                'fee_category__category_type',
                'fee_category__code'
            ).annotate(
                total_amount=Sum('final_amount')
            ).order_by('fee_category__category_type')
            
            if not revenue_breakdown.exists():
                # No items - use default revenue account
                JournalTransaction.objects.create(
                    journal_entry=journal_entry,
                    account=mappings.default_revenue_account,
                    amount=invoice.total_amount,
                    is_debit=False,
                    description=f"Fee revenue - {invoice.academic_session.name}",
                )
            else:
                # Process each category group (same logic as invoice_generators.py)
                for item in revenue_breakdown:
                    category_type = item['fee_category__category_type'] or ''
                    category_code = item['fee_category__code'] or ''
                    amount = item['total_amount']
                    
                    # ============================================================
                    # REVENUE ACCOUNT MAPPING LOGIC (from invoice_generators.py)
                    # ============================================================
                    
                    # GROUP 1: TUITION, ACADEMIC & UNIVERSAL SERVICES → Account 4000
                    if category_type in [
                        'TUITION', 'EXAM', 'DEVELOPMENT', 'MEDICAL', 'SPORT',
                        'MEALS',  # MEALS is universal
                        'TECHNOLOGY', 'LABORATORY', 'LIBRARY', 'TRANSPORT',
                        'ADMISSION', 'REGISTRATION', 'CLUB', 'LATE_PAYMENT',
                        'FIELD_TRIP', 'GRADUATION', 'INSURANCE', 'BOOKS', 'OTHER'
                    ]:
                        revenue_account = mappings.default_revenue_account
                        description = f"{category_type.replace('_', ' ').title()} revenue"
                    
                    # GROUP 2: BOARDING-ONLY SERVICES → Account 4100
                    elif category_type in ['BOARDING', 'LAUNDRY']:
                        revenue_account = mappings.boarding_revenue_account or mappings.default_revenue_account
                        description = "Boarding services revenue"
                    
                    # GROUP 3: UNIFORM SALES → Account 4200
                    elif category_type == 'UNIFORM':
                        revenue_account = mappings.uniform_and_book_sales_account or mappings.default_revenue_account
                        description = "Uniform sales revenue"
                    
                    # GROUP 4: EMPTY category_type - check code
                    elif not category_type:
                        code_mapping = {
                            'TUITION': (mappings.default_revenue_account, "Tuition revenue"),
                            'EXAM': (mappings.default_revenue_account, "Examination revenue"),
                            'BOARD': (mappings.boarding_revenue_account or mappings.default_revenue_account, "Boarding revenue"),
                            'MEALS': (mappings.default_revenue_account, "Meals revenue"),
                        }
                        
                        if category_code in code_mapping:
                            revenue_account, description = code_mapping[category_code]
                        else:
                            revenue_account = mappings.default_revenue_account
                            description = f"{category_code} revenue" if category_code else "Other revenue"
                    
                    # GROUP 5: FALLBACK
                    else:
                        revenue_account = mappings.default_revenue_account
                        description = f"{category_type.replace('_', ' ').title()} revenue"
                    
                    # Create credit transaction
                    JournalTransaction.objects.create(
                        journal_entry=journal_entry,
                        account=revenue_account,
                        amount=amount,
                        is_debit=False,
                        description=description,
                    )
            
            # ================================================================
            # FINALIZE INVOICE AND POST JOURNAL ENTRY
            # ================================================================
            
            # Change invoice status to PENDING
            invoice.status = 'PENDING'
            invoice.save(update_fields=['status', 'journal_entry'])
            
            # Post the journal entry
            journal_entry.status = 'POSTED'
            journal_entry.posted_at = timezone.now()
            journal_entry.posted_by_id = str(request.user.id)
            journal_entry.save(update_fields=['status', 'posted_at', 'posted_by_id'])
            
            logger.info(
                f"✅ Finalized invoice {invoice.invoice_number}: "
                f"Status → PENDING, Journal entry {journal_entry.entry_number} → POSTED"
            )
            
            # ================================================================
            # SUCCESS RESPONSE
            # ================================================================
            
            action = "created and posted" if journal_entry_created else "updated and posted"
            transaction_count = journal_entry.transactions.count()
            
            success_msg = (
                f"Invoice {invoice.invoice_number} finalized successfully! "
                f"Journal entry {journal_entry.entry_number} {action} "
                f"({transaction_count} transactions)."
            )
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = success_msg
                response['HX-Alert-Type'] = 'success'
                response['HX-Alert-Title'] = 'Invoice Finalized'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('fees:invoice_detail', kwargs={'pk': invoice.pk})
                return response
            else:
                messages.success(request, success_msg)
                return redirect('fees:invoice_detail', pk=invoice.pk)
    
    except Exception as e:
        logger.error(f"Error finalizing invoice: {e}", exc_info=True)
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f'Error finalizing invoice: {str(e)}'
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Error'
            return response
        else:
            messages.error(request, f'Error finalizing invoice: {str(e)}')
            return redirect('fees:invoice_detail', pk=pk)
        
@login_required
@require_http_methods(["POST"])
def invoice_revert_to_draft(request, pk):
    """
    Revert invoice from PENDING back to DRAFT.
    
    This will:
    - Change invoice status to DRAFT
    - Un-post journal entry (POSTED → DRAFT)
    - Allow invoice modifications again
    
    Only allowed if:
    - Invoice is PENDING
    - No payments have been made
    """
    invoice = get_object_or_404(FeeInvoice, pk=pk)
    
    # Check if can revert
    if invoice.status != 'PENDING':
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f'Invoice is {invoice.get_status_display()}, not PENDING'
            response['HX-Alert-Type'] = 'warning'
            response['HX-Alert-Title'] = 'Cannot Revert'
            return response
        else:
            messages.warning(request, f'Invoice is {invoice.get_status_display()}, not PENDING')
            return redirect('fees:invoice_detail', pk=pk)
    
    if invoice.paid_amount > 0:
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f'Cannot revert to DRAFT - invoice has payments ({invoice.paid_amount:,.2f})'
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Cannot Revert'
            return response
        else:
            messages.error(
                request, 
                f'Cannot revert to DRAFT - invoice has payments ({invoice.paid_amount:,.2f})'
            )
            return redirect('fees:invoice_detail', pk=pk)
    
    # ✅ NEW: Check fiscal period
    if invoice.fiscal_period and invoice.fiscal_period.is_closed:
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f'Cannot revert - fiscal period {invoice.fiscal_period.name} is closed'
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Cannot Revert'
            return response
        else:
            messages.error(
                request, 
                f'Cannot revert - fiscal period {invoice.fiscal_period.name} is closed'
            )
            return redirect('fees:invoice_detail', pk=pk)
    
    try:
        with transaction.atomic():
            # ✅ Un-post the journal entry (if exists and is posted)
            if invoice.journal_entry and invoice.journal_entry.status == 'POSTED':
                journal_entry = invoice.journal_entry
                entry_number = journal_entry.entry_number
                
                # Change journal entry status back to DRAFT
                journal_entry.status = 'DRAFT'
                journal_entry.posted_at = None
                journal_entry.save(update_fields=['status', 'posted_at'])
                
                logger.info(
                    f"Un-posted journal entry {entry_number} "
                    f"for invoice {invoice.invoice_number}"
                )
            
            # Change status back to DRAFT
            invoice.status = 'DRAFT'
            
            # Add note about reversion
            reverted_by = request.user.get_full_name() if hasattr(request.user, 'get_full_name') else str(request.user)
            invoice.notes = f"{invoice.notes}\n\nReverted to DRAFT by {reverted_by} on {timezone.now()}".strip()
            
            invoice.save()
            
            logger.info(
                f"Invoice {invoice.invoice_number} reverted to DRAFT by {request.user}"
            )
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f'Invoice {invoice.invoice_number} reverted to DRAFT successfully! Journal entry un-posted.'
            response['HX-Alert-Type'] = 'success'
            response['HX-Alert-Title'] = 'Invoice Reverted'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('fees:invoice_detail', kwargs={'pk': invoice.pk})
            return response
        else:
            messages.success(
                request, 
                f'Invoice {invoice.invoice_number} reverted to DRAFT successfully! Journal entry un-posted.'
            )
            return redirect('fees:invoice_detail', pk=invoice.pk)
    
    except Exception as e:
        logger.error(f"Error reverting invoice {invoice.invoice_number}: {e}", exc_info=True)
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f'Error reverting invoice: {str(e)}'
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Error'
            return response
        else:
            messages.error(request, f'Error reverting invoice: {str(e)}')
            return redirect('fees:invoice_detail', pk=pk)
        
@login_required
@require_http_methods(["POST"])
def remove_scholarship_from_invoice(request, invoice_pk):
    """
    Remove scholarship(s) from invoice and recalculate totals.
    
    IMPORTANT: Only allows removal from DRAFT invoices to maintain
    accounting integrity. PENDING/PAID invoices must be reverted to
    DRAFT first to ensure journal entries remain accurate.
    
    This view:
    1. Validates invoice is in DRAFT status
    2. Reverses scholarship application logs
    3. Optionally refunds amount to scholarship budget
    4. Recalculates invoice totals
    5. Updates invoice flags
    6. Logs the action for audit
    
    Supports removing:
    - A specific scholarship (scholarship_id = UUID)
    - All scholarships (scholarship_id = 'all')
    """
    invoice = get_object_or_404(FeeInvoice, pk=invoice_pk)
    
    # =========================================================================
    # EXTRACT AND VALIDATE FORM DATA
    # =========================================================================
    
    scholarship_id = request.POST.get('scholarship_id')
    removal_reason = request.POST.get('removal_reason', '').strip()
    refund_to_budget = request.POST.get('refund_to_budget') == 'on'
    
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    # Validate required fields
    if not scholarship_id:
        error_msg = "Please select a scholarship to remove"
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = error_msg
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Invalid Request'
            return response
        else:
            messages.error(request, error_msg)
            return redirect('fees:invoice_detail', pk=invoice_pk)
    
    if not removal_reason:
        error_msg = "Removal reason is required"
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = error_msg
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Missing Information'
            return response
        else:
            messages.error(request, error_msg)
            return redirect('fees:invoice_detail', pk=invoice_pk)
    
    # =========================================================================
    # CRITICAL: ONLY ALLOW REMOVAL FROM DRAFT INVOICES
    # =========================================================================
    
    if invoice.status != 'DRAFT':
        error_msg = (
            f"Cannot remove scholarship from {invoice.get_status_display()} invoice. "
            f"Journal entries have been posted for this invoice. "
            f"Please revert the invoice to DRAFT status first, then remove the scholarship."
        )
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = error_msg
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Invoice Must Be DRAFT'
            response['HX-Redirect'] = reverse('fees:invoice_detail', kwargs={'pk': invoice_pk})
            return response
        else:
            messages.error(request, error_msg)
            return redirect('fees:invoice_detail', pk=invoice_pk)
    
    # Check fiscal period
    if invoice.fiscal_period and invoice.fiscal_period.is_closed:
        error_msg = f"Cannot remove scholarship: Fiscal period {invoice.fiscal_period.name} is closed"
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = error_msg
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Period Closed'
            return response
        else:
            messages.error(request, error_msg)
            return redirect('fees:invoice_detail', pk=invoice_pk)
    
    # =========================================================================
    # PROCESS SCHOLARSHIP REMOVAL
    # =========================================================================
    
    try:
        with transaction.atomic():
            
            # -----------------------------------------------------------------
            # STEP 1: Get scholarship logs to reverse
            # -----------------------------------------------------------------
            
            if scholarship_id == 'all':
                # Remove all scholarships
                logs = invoice.scholarship_application_logs.filter(
                    is_reversed=False
                ).select_related('scholarship__scholarship_program')
                
                logger.info(
                    f"Removing ALL scholarships from invoice {invoice.invoice_number} "
                    f"({logs.count()} scholarships)"
                )
            else:
                # Remove specific scholarship
                scholarship = get_object_or_404(StudentScholarship, pk=scholarship_id)
                
                # Verify scholarship belongs to invoice student
                if scholarship.student != invoice.student:
                    error_msg = "Scholarship does not belong to this student"
                    
                    if is_htmx:
                        response = HttpResponse()
                        response['HX-Alert-Message'] = error_msg
                        response['HX-Alert-Type'] = 'error'
                        response['HX-Alert-Title'] = 'Invalid Scholarship'
                        return response
                    else:
                        messages.error(request, error_msg)
                        return redirect('fees:invoice_detail', pk=invoice_pk)
                
                logs = invoice.scholarship_application_logs.filter(
                    scholarship=scholarship,
                    is_reversed=False
                ).select_related('scholarship__scholarship_program')
                
                logger.info(
                    f"Removing scholarship {scholarship.scholarship_program.name} "
                    f"from invoice {invoice.invoice_number}"
                )
            
            # Check if any scholarships found
            if not logs.exists():
                warning_msg = "No active scholarships found on this invoice"
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = warning_msg
                    response['HX-Alert-Type'] = 'warning'
                    response['HX-Alert-Title'] = 'No Scholarships'
                    response['HX-Redirect'] = reverse('fees:invoice_detail', kwargs={'pk': invoice_pk})
                    return response
                else:
                    messages.warning(request, warning_msg)
                    return redirect('fees:invoice_detail', pk=invoice_pk)
            
            # -----------------------------------------------------------------
            # STEP 2: Reverse each scholarship application
            # -----------------------------------------------------------------
            
            total_removed = Decimal('0.00')
            scholarships_processed = []
            
            for log in logs:
                # Store scholarship info for logging
                scholarship_info = {
                    'program_name': log.scholarship.scholarship_program.name,
                    'amount': log.amount_applied,
                    'scholarship_id': log.scholarship.pk
                }
                scholarships_processed.append(scholarship_info)
                
                # Mark as reversed
                log.is_reversed = True
                log.reversal_reason = removal_reason
                log.reversed_date = get_school_today()
                log.reversed_by_id = str(request.user.id)
                log.save(update_fields=[
                    'is_reversed',
                    'reversal_reason',
                    'reversed_date',
                    'reversed_by_id'
                ])
                
                total_removed += log.amount_applied
                
                logger.info(
                    f"Reversed scholarship log {log.pk}: "
                    f"{log.scholarship.scholarship_program.name} - {log.amount_applied}"
                )
                
                # ---------------------------------------------------------
                # STEP 3: Refund to scholarship budget (if requested)
                # ---------------------------------------------------------
                
                if refund_to_budget and log.scholarship.requires_budget_tracking():
                    scholarship = log.scholarship
                    old_balance = scholarship.get_remaining_balance()
                    
                    # Restore amount to scholarship
                    scholarship.total_amount_used -= log.amount_applied
                    
                    # Ensure total_amount_used doesn't go negative
                    if scholarship.total_amount_used < Decimal('0.00'):
                        logger.warning(
                            f"Scholarship {scholarship.pk} total_amount_used went negative "
                            f"({scholarship.total_amount_used}), resetting to 0"
                        )
                        scholarship.total_amount_used = Decimal('0.00')
                    
                    scholarship.save(update_fields=['total_amount_used'])
                    
                    new_balance = scholarship.get_remaining_balance()
                    
                    logger.info(
                        f"Refunded {log.amount_applied} to scholarship {scholarship.pk} "
                        f"({scholarship.scholarship_program.name}): "
                        f"Balance {old_balance} → {new_balance}"
                    )
            
            # -----------------------------------------------------------------
            # STEP 4: Update invoice totals
            # -----------------------------------------------------------------
            
            # Store old values for logging
            old_scholarship_discount = invoice.scholarship_discount_amount
            old_total = invoice.total_amount
            old_balance = invoice.balance
            
            # Update scholarship discount
            invoice.scholarship_discount_amount -= total_removed
            
            # Ensure scholarship discount doesn't go negative
            if invoice.scholarship_discount_amount < Decimal('0.00'):
                logger.warning(
                    f"Invoice {invoice.invoice_number} scholarship_discount_amount went negative "
                    f"({invoice.scholarship_discount_amount}), resetting to 0"
                )
                invoice.scholarship_discount_amount = Decimal('0.00')
            
            # Add removed scholarship amount back to total
            invoice.total_amount += total_removed
            
            # Recalculate balance
            invoice.balance = invoice.total_amount - invoice.paid_amount
            
            # -----------------------------------------------------------------
            # STEP 5: Update scholarship flags
            # -----------------------------------------------------------------
            
            # Check if any scholarships still remain
            remaining_scholarships = invoice.scholarship_application_logs.filter(
                is_reversed=False
            ).exists()
            
            if not remaining_scholarships:
                # No scholarships left - clear flags
                invoice.has_scholarships_applied = False
                invoice.auto_scholarships_applied = False
                invoice.scholarship_discount_amount = Decimal('0.00')
                
                logger.info(
                    f"All scholarships removed from invoice {invoice.invoice_number} - "
                    f"cleared scholarship flags"
                )
            
            # Save invoice
            invoice.save(update_fields=[
                'scholarship_discount_amount',
                'total_amount',
                'balance',
                'has_scholarships_applied',
                'auto_scholarships_applied'
            ])
            
            # -----------------------------------------------------------------
            # STEP 6: Log the complete action
            # -----------------------------------------------------------------
            
            logger.info(
                f"✅ Successfully removed {len(scholarships_processed)} scholarship(s) "
                f"from invoice {invoice.invoice_number}:"
            )
            logger.info(f"   Reason: {removal_reason}")
            logger.info(f"   Removed by: {request.user.get_full_name() if hasattr(request.user, 'get_full_name') else request.user}")
            logger.info(f"   Total amount removed: {total_removed}")
            logger.info(f"   Refunded to budget: {'Yes' if refund_to_budget else 'No'}")
            logger.info(f"   Scholarship discount: {old_scholarship_discount} → {invoice.scholarship_discount_amount}")
            logger.info(f"   Invoice total: {old_total} → {invoice.total_amount}")
            logger.info(f"   Invoice balance: {old_balance} → {invoice.balance}")
            
            for scholarship_info in scholarships_processed:
                logger.info(
                    f"   - {scholarship_info['program_name']}: {scholarship_info['amount']}"
                )
            
            # -----------------------------------------------------------------
            # STEP 7: Success response
            # -----------------------------------------------------------------
            
            # Build success message
            if len(scholarships_processed) == 1:
                success_msg = (
                    f"Successfully removed scholarship '{scholarships_processed[0]['program_name']}' "
                    f"totaling {total_removed:,.2f}. "
                    f"New invoice total: {invoice.total_amount:,.2f}, "
                    f"Balance: {invoice.balance:,.2f}"
                )
            else:
                success_msg = (
                    f"Successfully removed {len(scholarships_processed)} scholarship(s) "
                    f"totaling {total_removed:,.2f}. "
                    f"New invoice total: {invoice.total_amount:,.2f}, "
                    f"Balance: {invoice.balance:,.2f}"
                )
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = success_msg
                response['HX-Alert-Type'] = 'success'
                response['HX-Alert-Title'] = 'Scholarship Removed'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('fees:invoice_detail', kwargs={'pk': invoice_pk})
                return response
            else:
                messages.success(request, success_msg)
                return redirect('fees:invoice_detail', pk=invoice_pk)
    
    # =========================================================================
    # ERROR HANDLING
    # =========================================================================
    
    except StudentScholarship.DoesNotExist:
        error_msg = "Scholarship not found"
        logger.error(f"Scholarship {scholarship_id} not found")
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = error_msg
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Not Found'
            return response
        else:
            messages.error(request, error_msg)
            return redirect('fees:invoice_detail', pk=invoice_pk)
    
    except Exception as e:
        error_msg = f"Error removing scholarship: {str(e)}"
        logger.error(
            f"Error removing scholarship from invoice {invoice.invoice_number}: {e}",
            exc_info=True
        )
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = error_msg
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Error'
            return response
        else:
            messages.error(request, error_msg)
            return redirect('fees:invoice_detail', pk=invoice_pk)
        
@login_required
@require_http_methods(["POST"])
def apply_scholarship_to_invoice(request, invoice_pk):
    """Apply selected scholarship(s) to invoice"""
    invoice = get_object_or_404(FeeInvoice, pk=invoice_pk)
    
    scholarship_ids = request.POST.getlist('scholarship_ids')  # Can select multiple
    application_reason = request.POST.get('application_reason', '').strip()
    
    if not scholarship_ids:
        messages.error(request, "Please select at least one scholarship")
        return redirect('fees:invoice_detail', pk=invoice_pk)
    
    if not application_reason:
        messages.error(request, "Application reason is required")
        return redirect('fees:invoice_detail', pk=invoice_pk)
    
    try:
        with transaction.atomic():
            total_discount = Decimal('0.00')
            
            for scholarship_id in scholarship_ids:
                scholarship = get_object_or_404(
                    StudentScholarship, 
                    pk=scholarship_id,
                    student=invoice.student
                )
                
                # Check if already applied
                if invoice.scholarship_application_logs.filter(
                    scholarship=scholarship,
                    is_reversed=False
                ).exists():
                    messages.warning(
                        request, 
                        f"Scholarship {scholarship.scholarship_program.name} is already applied"
                    )
                    continue
                
                # Calculate discount
                if scholarship.is_policy_based():
                    discount = (invoice.subtotal_amount * scholarship.scholarship_program.discount_percentage) / 100
                else:
                    # Budget-based
                    available = scholarship.get_remaining_balance()
                    discount = min(available, invoice.subtotal_amount)
                    
                    # Update scholarship usage
                    scholarship.total_amount_used += discount
                    scholarship.save(update_fields=['total_amount_used'])
                
                # Create application log
                from fees.models import ScholarshipApplicationLog
                ScholarshipApplicationLog.objects.create(
                    invoice=invoice,
                    scholarship=scholarship,
                    amount_applied=discount,
                    application_date=get_school_today(),
                    applied_by_id=str(request.user.id),
                    application_reason=application_reason,
                    is_reversed=False,
                )
                
                total_discount += discount
                
                logger.info(
                    f"Applied scholarship {scholarship.scholarship_program.name} "
                    f"to invoice {invoice.invoice_number}: {discount}"
                )
            
            # Update invoice totals
            invoice.scholarship_discount_amount += total_discount
            invoice.total_amount -= total_discount
            invoice.balance = invoice.total_amount - invoice.paid_amount
            invoice.has_scholarships_applied = True
            
            invoice.save(update_fields=[
                'scholarship_discount_amount',
                'total_amount',
                'balance',
                'has_scholarships_applied',
            ])
            
            messages.success(
                request,
                f"Successfully applied {len(scholarship_ids)} scholarship(s) "
                f"totaling {total_discount:,.2f}. New invoice total: {invoice.total_amount:,.2f}"
            )
    
    except Exception as e:
        logger.error(f"Error applying scholarship: {e}", exc_info=True)
        messages.error(request, f"Error applying scholarship: {str(e)}")
    
    return redirect('fees:invoice_detail', pk=invoice_pk)

@login_required
def invoice_print_view(request, pk):
    """Generate printable invoice"""
    invoice = get_object_or_404(
        FeeInvoice.objects.select_related(
            'student', 'academic_session', 'fiscal_period', 'fee_structure'
        ).prefetch_related('items__fee_category'),
        pk=pk
    )
    
    context = {
        'invoice': invoice,
        'now': timezone.now(),
        'title': f'Invoice {invoice.invoice_number}',
    }
    
    return render(request, 'fees/invoices/print.html', context)


@login_required
def invoice_list_print_view(request):
    """Generate printable invoice list"""
    
    # Get filter parameters
    filters = {}
    if request.GET.get('session'):
        filters['academic_session'] = request.GET.get('session')
    if request.GET.get('status'):
        filters['status'] = request.GET.get('status')
    if request.GET.get('date_from'):
        filters['date_from'] = request.GET.get('date_from')
    if request.GET.get('date_to'):
        filters['date_to'] = request.GET.get('date_to')
    
    # Build queryset
    invoices = FeeInvoice.objects.select_related(
        'student', 'academic_session'
    ).order_by('-issue_date')
    
    if filters.get('academic_session'):
        invoices = invoices.filter(academic_session_id=filters['academic_session'])
    if filters.get('status'):
        invoices = invoices.filter(status=filters['status'])
    if filters.get('date_from'):
        invoices = invoices.filter(issue_date__gte=filters['date_from'])
    if filters.get('date_to'):
        invoices = invoices.filter(issue_date__lte=filters['date_to'])
    
    # Get summary stats
    summary = invoices.aggregate(
        total_amount=Sum('total_amount'),
        total_paid=Sum('paid_amount'),
        total_balance=Sum('balance'),
    )
    
    context = {
        'invoices': invoices[:100],  # Limit to 100 for print
        'summary': summary,
        'filters': filters,
        'now': timezone.now(),
        'title': 'Invoice List',
    }
    
    return render(request, 'fees/invoices/print_list.html', context)

# =============================================================================
# PAYMENT LIST
# =============================================================================

@login_required
def payment_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""
    filter_form = PaymentFilterForm(request.GET or None)
    payments = get_filtered_payments(request)
    
    # Calculate statistics
    stats = {
        'total': payments.count(),
        'completed': payments.filter(status='COMPLETED').count(),
        'pending': payments.filter(status='PENDING').count(),
        'failed': payments.filter(status='FAILED').count(),
        'verified': payments.filter(is_verified=True).count(),
        'unverified': payments.filter(is_verified=False).count(),
        'total_amount': payments.filter(status='COMPLETED').aggregate(Sum('amount'))['amount__sum'] or 0,
    }
    
    # Pagination
    paginator = Paginator(payments, 20)
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
        return render(request, 'fees/payments/partials/_payment_results.html', context)
    else:
        return render(request, 'fees/payments/list.html', context)

@login_required
def payment_create(request):
    """
    Create new payment for a single invoice.
    
    URL params:
    - invoice: Pre-populate with invoice ID (optional)
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Get invoice if specified
    invoice_id = request.GET.get('invoice')
    invoice = None
    if invoice_id:
        invoice = get_object_or_404(FeeInvoice, pk=invoice_id)
        logger.info(f"Invoice pre-selected: {invoice.invoice_number} (ID: {invoice.id})")
    
    if request.method == 'POST':
        logger.info("=" * 80)
        logger.info("PAYMENT FORM SUBMISSION")
        logger.info("=" * 80)
        
        # Log POST data (excluding CSRF token)
        for key, value in request.POST.items():
            if key != 'csrfmiddlewaretoken':
                logger.info(f"POST[{key}] = {value}")
        
        form = PaymentForm(request.POST, invoice=invoice)
        
        logger.info(f"Form is_valid: {form.is_valid()}")
        
        if not form.is_valid():
            logger.error("Form validation failed!")
            logger.error(f"Form errors: {form.errors}")
            
            for field_name, errors in form.errors.items():
                logger.error(f"  Field '{field_name}': {errors}")
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = 'Please correct the errors below.'
                response['HX-Alert-Type'] = 'error'
                response['HX-Alert-Title'] = 'Validation Error'
                return response
            else:
                messages.error(
                    request,
                    'Please correct the errors below.'
                )
        else:
            logger.info("✅ Form validation passed")
            
            try:
                with transaction.atomic():
                    # Save payment (commit=False to set additional fields)
                    payment = form.save(commit=False)
                    
                    logger.info(f"Payment object created (not saved yet)")
                    logger.info(f"  Invoice: {payment.invoice}")
                    logger.info(f"  Student: {payment.student}")
                    logger.info(f"  Amount: {payment.amount}")
                    
                    # Set who received/processed the payment
                    payment.received_by_id = str(request.user.id)
                    payment.processed_by_id = str(request.user.id)
                    
                    # Auto-issue receipt
                    payment.receipt_issued = True
                    
                    # ✅ EXPLICITLY SET FISCAL PERIOD (before save)
                    logger.info("Checking fiscal period...")
                    logger.info(f"payment.fiscal_period_id before: {payment.fiscal_period_id}")
                    
                    if not payment.fiscal_period_id:
                        from core.models import FiscalPeriod
                        fiscal_period = FiscalPeriod.get_current_fiscal_period()
                        
                        logger.info(f"FiscalPeriod.get_current_fiscal_period() returned: {fiscal_period}")
                        
                        if not fiscal_period:
                            is_htmx = request.headers.get('HX-Request') == 'true'
                            
                            if is_htmx:
                                response = HttpResponse()
                                response['HX-Alert-Message'] = 'No active fiscal period found. Please activate a fiscal period in Finance settings before recording payments.'
                                response['HX-Alert-Type'] = 'error'
                                response['HX-Alert-Title'] = 'Error!'
                                return response
                            else:
                                messages.error(
                                    request,
                                    'No active fiscal period found. Please activate a fiscal period '
                                    'in Finance settings before recording payments.'
                                )
                                
                                context = {
                                    'form': form,
                                    'invoice': invoice,
                                    'title': 'Record Payment',
                                    'submit_text': 'Record Payment',
                                }
                                return render(request, 'fees/payments/form.html', context)
                        
                        payment.fiscal_period = fiscal_period
                        logger.info(f"✅ Set fiscal_period to: {fiscal_period}")
                    
                    # Save payment (signals will handle the rest)
                    logger.info(f"Saving payment with fiscal_period_id: {payment.fiscal_period_id}")
                    payment.save()
                    
                    logger.info(f"✅ Payment saved successfully!")
                    logger.info(f"  Payment number: {payment.payment_number}")
                    logger.info(f"  Receipt number: {payment.receipt_number}")
                    logger.info(f"  Fiscal period: {payment.fiscal_period}")
                    
                    is_htmx = request.headers.get('HX-Request') == 'true'
                    
                    if is_htmx:
                        response = HttpResponse()
                        response['HX-Alert-Message'] = f"Payment '{payment.payment_number}' recorded successfully! Receipt: {payment.receipt_number}"
                        response['HX-Alert-Type'] = 'success'
                        response['HX-Alert-Title'] = 'Payment Recorded!'
                        response['HX-Redirect'] = reverse('fees:payment_list')
                        return response
                    else:
                        messages.success(
                            request,
                            f'Payment {payment.payment_number} recorded successfully! '
                            f'Receipt: {payment.receipt_number}'
                        )
                        return redirect('fees:payment_list')
                    
            except Exception as e:
                logger.error(f"Error creating payment: {e}", exc_info=True)
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Error creating payment: {str(e)}'
                    response['HX-Alert-Type'] = 'error'
                    response['HX-Alert-Title'] = 'Error!'
                    return response
                else:
                    messages.error(request, f'Error creating payment: {str(e)}')
    else:
        # GET request - initialize form
        logger.info("GET request - initializing form")
        
        from core.utils import get_school_today
        
        initial_data = {
            'payment_date': get_school_today(),
        }
        
        if invoice:
            initial_data['amount'] = invoice.balance
            logger.info(f"Pre-filling amount with balance: {invoice.balance}")
        
        # Pass invoice as kwarg - form's __init__ handles the rest
        form = PaymentForm(initial=initial_data, invoice=invoice)
        
        # Debug logging
        logger.info("=" * 80)
        logger.info("FORM STATE AFTER INITIALIZATION")
        logger.info("=" * 80)
        logger.info(f"Invoice widget: {type(form.fields['invoice'].widget).__name__}")
        logger.info(f"Student widget: {type(form.fields['student'].widget).__name__}")
        logger.info(f"Form.initial['invoice']: {form.initial.get('invoice')}")
        logger.info(f"Form.initial['student']: {form.initial.get('student')}")
        logger.info("=" * 80)
    
    context = {
        'form': form,
        'invoice': invoice,
        'title': 'Record Payment',
        'submit_text': 'Record Payment',
    }
    
    return render(request, 'fees/payments/form.html', context)

@login_required
def multiple_invoice_payment_create(request):
    """
    Create payment that covers MULTIPLE invoices.
    
    Use cases:
    - Parent paying for multiple children
    - Parent paying multiple terms for same student
    - Clearing all outstanding invoices
    """
    
    if request.method == 'POST':
        form = MultipleInvoicePaymentForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Get payment allocation
                    allocation = form.get_payment_allocation()
                    
                    if not allocation:
                        is_htmx = request.headers.get('HX-Request') == 'true'
                        
                        if is_htmx:
                            response = HttpResponse()
                            response['HX-Alert-Message'] = 'No invoices selected or payment allocation failed.'
                            response['HX-Alert-Type'] = 'error'
                            response['HX-Alert-Title'] = 'Error!'
                            return response
                        else:
                            messages.error(request, 'No invoices selected or payment allocation failed.')
                            return redirect('fees:multiple_payment_create')
                    
                    # Get common payment details from form
                    payment_date = form.cleaned_data['payment_date']
                    payment_method = form.cleaned_data['payment_method']
                    reference_number = form.cleaned_data.get('reference_number', '')
                    transaction_id = form.cleaned_data.get('transaction_id', '')
                    bank_name = form.cleaned_data.get('bank_name', '')
                    account_number = form.cleaned_data.get('account_number', '')
                    cheque_number = form.cleaned_data.get('cheque_number', '')
                    cheque_date = form.cleaned_data.get('cheque_date')
                    mobile_money_provider = form.cleaned_data.get('mobile_money_provider', '')
                    mobile_number = form.cleaned_data.get('mobile_number', '')
                    paid_by_name = form.cleaned_data.get('paid_by_name', '')
                    paid_by_phone = form.cleaned_data.get('paid_by_phone', '')
                    paid_by_email = form.cleaned_data.get('paid_by_email', '')
                    paid_by_relationship = form.cleaned_data.get('paid_by_relationship', '')
                    remarks = form.cleaned_data.get('remarks', '')
                    
                    # Create individual payments for each invoice
                    created_payments = []
                    
                    for item in allocation:
                        invoice = item['invoice']
                        amount = item['amount']
                        
                        if amount <= 0:
                            continue
                        
                        # Calculate amount applied to invoice vs overpayment
                        amount_applied = min(amount, invoice.balance)
                        overpayment = max(Decimal('0.00'), amount - invoice.balance)
                        
                        # Create payment
                        payment = Payment.objects.create(
                            invoice=invoice,
                            student=invoice.student,
                            amount=amount,
                            amount_applied_to_invoice=amount_applied,
                            overpayment_amount=overpayment,
                            payment_date=payment_date,
                            payment_method=payment_method,
                            reference_number=reference_number,
                            transaction_id=transaction_id,
                            bank_name=bank_name,
                            account_number=account_number,
                            cheque_number=cheque_number,
                            cheque_date=cheque_date,
                            mobile_money_provider=mobile_money_provider,
                            mobile_number=mobile_number,
                            paid_by_name=paid_by_name,
                            paid_by_phone=paid_by_phone,
                            paid_by_email=paid_by_email,
                            paid_by_relationship=paid_by_relationship,
                            remarks=f"{remarks}\n[Multiple invoice payment - {len(allocation)} invoices]" if remarks else f"Multiple invoice payment - {len(allocation)} invoices",
                            received_by_id=str(request.user.id),
                            processed_by_id=str(request.user.id),
                            status='COMPLETED',
                            receipt_issued=True,
                        )
                        
                        created_payments.append(payment)
                    
                    # Success message
                    total_amount = sum(p.amount for p in created_payments)
                    
                    is_htmx = request.headers.get('HX-Request') == 'true'
                    
                    if is_htmx:
                        response = HttpResponse()
                        response['HX-Alert-Message'] = f"Successfully created {len(created_payments)} payment(s) totaling UGX {total_amount:,.2f}"
                        response['HX-Alert-Type'] = 'success'
                        response['HX-Alert-Title'] = 'Payments Created!'
                        if created_payments:
                            response['HX-Redirect'] = reverse('fees:payment_detail', kwargs={'pk': created_payments[0].pk})
                        else:
                            response['HX-Redirect'] = reverse('fees:payment_list')
                        return response
                    else:
                        messages.success(
                            request,
                            f'Successfully created {len(created_payments)} payment(s) '
                            f'totaling UGX {total_amount:,.2f} across {len(allocation)} invoice(s).'
                        )
                        
                        # Redirect to payment list or first payment detail
                        if created_payments:
                            return redirect('fees:payment_detail', pk=created_payments[0].pk)
                        else:
                            return redirect('fees:payment_list')
                    
            except Exception as e:
                logger.error(f"Error creating multiple invoice payment: {e}", exc_info=True)
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Error creating payment: {str(e)}'
                    response['HX-Alert-Type'] = 'error'
                    response['HX-Alert-Title'] = 'Error!'
                    return response
                else:
                    messages.error(request, f'Error creating payment: {str(e)}')
    else:
        form = MultipleInvoicePaymentForm()
    
    context = {
        'form': form,
        'title': 'Multiple Invoice Payment',
        'submit_text': 'Record Payment',
    }
    
    return render(request, 'fees/payments/multiple_payment_form.html', context)

@login_required
def payment_detail(request, pk):
    """View payment details"""
    payment = get_object_or_404(
        Payment.objects.select_related(
            'student', 'invoice', 'payment_method',
            'academic_session', 'fiscal_period',
            'journal_entry', 'reversal_journal_entry', 'refund_journal_entry'
        ),
        pk=pk
    )
    
    # Get audit trail
    try:
        audit_trail = payment.get_audit_trail()
    except Exception as e:
        logger.error(f"Error getting audit trail: {e}")
        audit_trail = []
    
    # Get account summary for this student
    try:
        account_summary = payment.student.financial_account.get_account_summary()
    except Exception as e:
        logger.error(f"Error getting account summary: {e}")
        account_summary = None
    
    context = {
        'payment': payment,
        'audit_trail': audit_trail,
        'account_summary': account_summary,
    }
    
    return render(request, 'fees/payments/detail.html', context)

@login_required
def payment_update(request, pk):
    """
    Update payment.
    
    Restrictions:
    - Cannot edit reversed payments
    - Cannot edit refunded payments
    - Can only edit remarks for verified payments
    """
    
    payment = get_object_or_404(Payment, pk=pk)
    
    # Check if payment can be edited
    if payment.reversed:
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = 'Cannot edit reversed payment.'
            response['HX-Alert-Type'] = 'warning'
            response['HX-Alert-Title'] = 'Cannot Edit'
            response['HX-Redirect'] = reverse('fees:payment_detail', kwargs={'pk': pk})
            return response
        else:
            messages.error(request, 'Cannot edit reversed payment.')
            return redirect('fees:payment_detail', pk=pk)
    
    if payment.refunded:
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = 'Cannot edit refunded payment.'
            response['HX-Alert-Type'] = 'warning'
            response['HX-Alert-Title'] = 'Cannot Edit'
            response['HX-Redirect'] = reverse('fees:payment_detail', kwargs={'pk': pk})
            return response
        else:
            messages.error(request, 'Cannot edit refunded payment.')
            return redirect('fees:payment_detail', pk=pk)
    
    if request.method == 'POST':
        form = PaymentForm(request.POST, instance=payment)
        if form.is_valid():
            try:
                with transaction.atomic():
                    payment = form.save()
                    
                    is_htmx = request.headers.get('HX-Request') == 'true'
                    
                    if is_htmx:
                        response = HttpResponse()
                        response['HX-Alert-Message'] = f"Payment '{payment.payment_number}' updated successfully!"
                        response['HX-Alert-Type'] = 'success'
                        response['HX-Alert-Title'] = 'Updated!'
                        response['HX-Redirect'] = reverse('fees:payment_detail', kwargs={'pk': payment.pk})
                        return response
                    else:
                        messages.success(
                            request,
                            f'Payment {payment.payment_number} updated successfully!'
                        )
                        return redirect('fees:payment_detail', pk=payment.pk)
                    
            except Exception as e:
                logger.error(f"Error updating payment: {e}", exc_info=True)
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Error updating payment: {str(e)}'
                    response['HX-Alert-Type'] = 'error'
                    response['HX-Alert-Title'] = 'Error!'
                    return response
                else:
                    messages.error(request, f'Error updating payment: {str(e)}')
    else:
        form = PaymentForm(instance=payment)
    
    context = {
        'form': form,
        'payment': payment,
        'title': f'Edit Payment {payment.payment_number}',
        'submit_text': 'Update Payment',
    }
    
    return render(request, 'fees/payments/form.html', context)

@login_required
@require_http_methods(["POST"])
def payment_delete(request, pk):
    """Delete payment with HTMX support"""
    payment = get_object_or_404(Payment, pk=pk)
    
    # Check if payment can be deleted
    if not payment.reversed and not payment.refunded:
        if payment.is_verified or payment.status == 'COMPLETED':
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f"Cannot delete verified payment '{payment.payment_number}'. Use 'Reverse Payment' instead."
                response['HX-Alert-Type'] = 'error'
                response['HX-Alert-Title'] = 'Cannot Delete'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(
                    request,
                    f"Cannot delete verified payment '{payment.payment_number}'",
                    extra_tags='sweetalert-error'
                )
                return redirect('fees:payment_detail', pk=pk)
    
    payment_number = payment.payment_number
    
    try:
        payment.delete()
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Payment '{payment_number}' deleted successfully"
            response['HX-Alert-Type'] = 'success'
            response['HX-Alert-Title'] = 'Deleted!'
            response['HX-Close-Modal'] = 'true'
            # ✅ Trigger refresh instead of redirect
            response['HX-Trigger'] = 'refreshPaymentList'
            return response
        else:
            messages.success(
                request,
                f"Payment '{payment_number}' deleted successfully",
                extra_tags='sweetalert'
            )
            return redirect('fees:payment_list')
    
    except Exception as e:
        logger.error(f"Error deleting payment {payment_number}: {e}", exc_info=True)
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Error deleting payment: {str(e)}"
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Delete Failed'
            response['HX-Close-Modal'] = 'true'
            return response
        else:
            messages.error(
                request,
                f"Error deleting payment: {str(e)}",
                extra_tags='sweetalert-error'
            )
            return redirect('fees:payment_list')

@login_required
def payment_reverse(request, pk):
    payment = get_object_or_404(Payment, pk=pk)
    
    can_reverse, reason = payment.can_be_reversed()
    if not can_reverse:
        messages.error(request, f'Cannot reverse: {reason}')
        return redirect('fees:payment_detail', pk=pk)
    
    if request.method == 'POST':
        form = PaymentReversalForm(payment, request.user, request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Just mark as reversed - signal handles the rest
                    payment.reversed = True
                    payment.reversed_on = timezone.now()
                    payment.reversed_by_id = str(request.user.id)
                    payment.reversal_reason = form.cleaned_data['reversal_reason']
                    payment.status = 'REVERSED'
                    payment.save()  # Signal creates journal entry
                    
                messages.success(request, 'Payment reversed successfully')
                return redirect('fees:payment_detail', pk=pk)
                    
            except Exception as e:
                logger.error(f"Error reversing payment: {e}", exc_info=True)
                messages.error(request, f'Error: {str(e)}')
    else:
        form = PaymentReversalForm(payment, request.user)
    
    return render(request, 'fees/payments/reverse_form.html', {
        'form': form,
        'payment': payment,
    })

@login_required
def payment_refund(request, pk):
    """
    Refund a payment (actual money returned to payer).
    Signal handles journal entry creation and account updates.
    """
    payment = get_object_or_404(Payment, pk=pk)
    
    # Check if payment can be refunded
    can_refund, reason = payment.can_be_refunded()
    if not can_refund:
        messages.error(request, f'Cannot refund this payment: {reason}')
        return redirect('fees:payment_detail', pk=pk)
    
    if request.method == 'POST':
        form = PaymentRefundForm(payment, request.user, request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Extract form data
                    refund_amount = form.cleaned_data['refund_amount']
                    refund_method = form.cleaned_data['refund_method']
                    refund_reference = form.cleaned_data['refund_reference']
                    refund_reason = form.cleaned_data['refund_reason']
                    refund_notes = form.cleaned_data.get('refund_notes', '')
                    
                    # Validate refund amount
                    if refund_amount > payment.amount:
                        messages.error(request, 'Refund amount cannot exceed payment amount')
                        return render(request, 'fees/payments/refund_form.html', {
                            'form': form,
                            'payment': payment,
                        })
                    
                    # Check for partial refund
                    is_partial_refund = refund_amount < payment.amount
                    
                    if is_partial_refund:
                        # Partial refunds not yet supported - needs separate model
                        messages.error(
                            request, 
                            'Partial refunds are not supported. Please refund the full amount.'
                        )
                        return render(request, 'fees/payments/refund_form.html', {
                            'form': form,
                            'payment': payment,
                        })
                    
                    # Mark payment as refunded - signal handles everything else
                    payment.refunded = True
                    payment.refunded_on = timezone.now()
                    payment.refunded_by_id = str(request.user.id)
                    payment.refund_method = refund_method
                    payment.refund_reference = refund_reference
                    payment.refund_notes = f"{refund_reason}\n\n{refund_notes}".strip()
                    payment.status = 'REFUNDED'
                    payment.save()  # ✅ Signal creates journal entry automatically
                    
                    messages.success(
                        request,
                        f'Payment {payment.payment_number} refunded successfully. '
                        f'Amount refunded: UGX {refund_amount:,.2f} via {refund_method}'
                    )
                    
                    return redirect('fees:payment_detail', pk=payment.pk)
                    
            except Exception as e:
                logger.error(f"Error refunding payment: {e}", exc_info=True)
                messages.error(request, f'Error refunding payment: {str(e)}')
    else:
        form = PaymentRefundForm(payment, request.user)
    
    context = {
        'form': form,
        'payment': payment,
        'title': f'Refund Payment {payment.payment_number}',
        'submit_text': 'Issue Refund',
    }
    
    return render(request, 'fees/payments/refund_form.html', context)

@login_required
@require_http_methods(["POST"])
def payment_verify(request, pk):
    """
    Verify a payment (HTMX-triggered from modal).
    
    Used by finance team to mark payments as verified after reconciliation.
    """
    
    payment = get_object_or_404(Payment, pk=pk)
    
    if payment.is_verified:
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = 'Payment is already verified.'
            response['HX-Alert-Type'] = 'info'
            response['HX-Alert-Title'] = 'Already Verified'
            response['HX-Redirect'] = reverse('fees:payment_detail', kwargs={'pk': pk})
            return response
        else:
            messages.info(request, 'Payment is already verified.')
            return redirect('fees:payment_detail', pk=pk)
    
    if payment.reversed or payment.refunded:
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = 'Cannot verify reversed or refunded payments.'
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Cannot Verify'
            response['HX-Redirect'] = reverse('fees:payment_detail', kwargs={'pk': pk})
            return response
        else:
            messages.error(request, 'Cannot verify reversed or refunded payments.')
            return redirect('fees:payment_detail', pk=pk)
    
    try:
        with transaction.atomic():
            # Get verification notes from form if provided
            verification_notes = request.POST.get('verification_notes', '').strip()
            
            payment.is_verified = True
            payment.verified_by_id = str(request.user.id)
            payment.verification_date = get_school_current_time()
            payment.status = 'COMPLETED'
            
            # Add verification notes if provided
            if verification_notes:
                if payment.internal_notes:
                    payment.internal_notes = f"{payment.internal_notes}\n\nVerification: {verification_notes}"
                else:
                    payment.internal_notes = f"Verification: {verification_notes}"
            
            payment.save()
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Payment {payment.payment_number} verified successfully!'
                response['HX-Alert-Type'] = 'success'
                response['HX-Alert-Title'] = 'Verified!'
                response['HX-Redirect'] = reverse('fees:payment_detail', kwargs={'pk': payment.pk})
                return response
            else:
                messages.success(
                    request,
                    f'Payment {payment.payment_number} verified successfully!',
                    extra_tags='sweetalert'
                )
                return redirect('fees:payment_detail', pk=payment.pk)
                
    except Exception as e:
        logger.error(f"Error verifying payment: {e}", exc_info=True)
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f'Error verifying payment: {str(e)}'
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Error'
            return response
        else:
            messages.error(request, f'Error verifying payment: {str(e)}')
            return redirect('fees:payment_detail', pk=pk)


@login_required
@require_http_methods(["POST"])
def payment_bulk_verify(request):
    """
    Verify multiple payments at once (HTMX-triggered from modal).
    
    Used by finance team after bank reconciliation.
    """
    
    try:
        with transaction.atomic():
            # Get payment IDs from POST data
            payment_ids = request.POST.getlist('payment_ids')
            
            if not payment_ids:
                raise ValueError("No payments selected for verification")
            
            verification_notes = request.POST.get('verification_notes', '').strip()
            
            # Get payments
            payments = Payment.objects.filter(
                id__in=payment_ids,
                is_verified=False  # Only verify unverified payments
            )
            
            if not payments.exists():
                raise ValueError("No unverified payments found with the provided IDs")
            
            # Mark all as verified
            verified_count = 0
            verification_time = get_school_current_time()
            
            for payment in payments:
                # Skip already verified, reversed, or refunded payments
                if payment.is_verified or payment.reversed or payment.refunded:
                    continue
                
                payment.is_verified = True
                payment.verified_by_id = str(request.user.id)
                payment.verification_date = verification_time
                payment.status = 'COMPLETED'
                
                # Add verification notes if provided
                if verification_notes:
                    if payment.internal_notes:
                        payment.internal_notes = f"{payment.internal_notes}\n\nBulk Verification: {verification_notes}"
                    else:
                        payment.internal_notes = f"Bulk Verification: {verification_notes}"
                
                payment.save()
                verified_count += 1
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Successfully verified {verified_count} payment(s)!'
                response['HX-Alert-Type'] = 'success'
                response['HX-Alert-Title'] = 'Bulk Verification Complete'
                response['HX-Redirect'] = reverse('fees:payment_list')
                return response
            else:
                messages.success(
                    request,
                    f'Successfully verified {verified_count} payment(s)!',
                    extra_tags='sweetalert'
                )
                return redirect('fees:payment_list')
                
    except ValueError as e:
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = str(e)
            response['HX-Alert-Type'] = 'warning'
            response['HX-Alert-Title'] = 'Validation Error'
            return response
        else:
            messages.warning(request, str(e))
            return redirect('fees:payment_list')
            
    except Exception as e:
        logger.error(f"Error bulk verifying payments: {e}", exc_info=True)
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f'Error verifying payments: {str(e)}'
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Error'
            return response
        else:
            messages.error(request, f'Error verifying payments: {str(e)}')
            return redirect('fees:payment_list')

@login_required
@require_http_methods(["POST"])
def payment_send_receipt(request, pk):
    """Send payment receipt via email"""
    payment = get_object_or_404(Payment, pk=pk)
    
    try:
        recipient_emails = request.POST.getlist('recipients')
        
        if not recipient_emails:
            raise ValueError("At least one recipient email is required")
        
        # Render receipt email
        email_context = {
            'payment': payment,
            'school_name': getattr(settings, 'SCHOOL_NAME', 'School'),
        }
        
        email_body = render_to_string('fees/emails/payment_receipt.html', email_context)
        
        send_mail(
            subject=f"Payment Receipt {payment.receipt_number or payment.payment_number}",
            message='',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipient_emails,
            html_message=email_body,
            fail_silently=False,
        )
        
        # Log receipt sent
        payment.internal_notes = f"{payment.internal_notes}\n\nReceipt emailed to {', '.join(recipient_emails)} on {timezone.now()}".strip()
        payment.save()
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Receipt sent to {len(recipient_emails)} recipient(s)!"
            response['HX-Alert-Type'] = 'success'
            response['HX-Alert-Title'] = 'Receipt Sent'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('fees:payment_detail', kwargs={'pk': payment.pk})
            return response
        else:
            messages.success(request, f"Receipt sent to {len(recipient_emails)} recipient(s)!")
            return redirect('fees:payment_detail', pk=payment.pk)
    
    except Exception as e:
        logger.error(f"Error sending receipt: {e}", exc_info=True)
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f'Error sending receipt: {str(e)}'
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Error'
            return response
        else:
            messages.error(request, f'Error sending receipt: {str(e)}')
            return redirect('fees:payment_detail', pk=pk)

@login_required
def payment_print_receipt(request, pk):
    """Generate printable payment receipt"""
    
    payment = get_object_or_404(
        Payment.objects.select_related(
            'student', 'invoice', 'payment_method'
        ),
        pk=pk
    )
    
    context = {
        'payment': payment,
        'now': timezone.now(),
        'title': f'Receipt {payment.receipt_number or payment.payment_number}',
    }
    
    return render(request, 'fees/payments/print_receipt.html', context)


@login_required
def payment_list_print_view(request):
    """Generate printable payment list"""
    
    # Get filter parameters
    filters = {}
    if request.GET.get('session'):
        filters['academic_session'] = request.GET.get('session')
    if request.GET.get('status'):
        filters['status'] = request.GET.get('status')
    if request.GET.get('date_from'):
        filters['date_from'] = request.GET.get('date_from')
    if request.GET.get('date_to'):
        filters['date_to'] = request.GET.get('date_to')
    
    # Build queryset
    payments = Payment.objects.select_related(
        'student', 'payment_method'
    ).order_by('-payment_date')
    
    if filters.get('academic_session'):
        payments = payments.filter(academic_session_id=filters['academic_session'])
    if filters.get('status'):
        payments = payments.filter(status=filters['status'])
    if filters.get('date_from'):
        payments = payments.filter(payment_date__gte=filters['date_from'])
    if filters.get('date_to'):
        payments = payments.filter(payment_date__lte=filters['date_to'])
    
    # Get summary stats
    summary = payments.aggregate(
        total_amount=Sum('amount'),
        total_applied=Sum('amount_applied_to_invoice'),
    )
    
    context = {
        'payments': payments[:100],  # Limit to 100 for print
        'summary': summary,
        'filters': filters,
        'now': timezone.now(),
        'title': 'Payment List',
    }
    
    return render(request, 'fees/payments/print_list.html', context)

@login_required
@require_http_methods(["GET"])
def api_get_student_invoices(request):
    """
    API endpoint to get outstanding invoices for selected students.
    
    Used by multiple invoice payment form to show real-time preview
    of which invoices will be paid.
    
    Query params:
    - students[]: List of student UUIDs
    
    Returns:
    - JSON: {invoices: [{id, number, student, balance, date}, ...]}
    """
    student_ids = request.GET.getlist('students[]')
    
    if not student_ids:
        return JsonResponse({'error': 'No students selected'}, status=400)
    
    try:
        invoices = FeeInvoice.objects.filter(
            student_id__in=student_ids,
            status__in=['PENDING', 'PARTIALLY_PAID', 'OVERDUE']
        ).select_related('student').order_by('issue_date')
        
        data = [{
            'id': str(invoice.id),
            'number': invoice.invoice_number,
            'student': invoice.student.get_full_name(),
            'student_id': str(invoice.student.id),
            'balance': float(invoice.balance),
            'total': float(invoice.total_amount),
            'paid': float(invoice.paid_amount),
            'date': invoice.issue_date.strftime('%Y-%m-%d'),
            'session': invoice.academic_session.name if invoice.academic_session else 'N/A'
        } for invoice in invoices]
        
        total_balance = sum(float(inv.balance) for inv in invoices)
        
        return JsonResponse({
            'success': True,
            'invoices': data,
            'total_balance': total_balance,
            'count': len(data)
        })
        
    except Exception as e:
        logger.error(f"Error fetching student invoices: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def api_validate_invoice_numbers(request):
    """
    API endpoint to validate and fetch invoices by invoice numbers.
    
    Used by multiple invoice payment form to validate invoice numbers
    entered by user and show preview.
    
    POST params:
    - invoice_numbers: String of invoice numbers (newline or comma separated)
    
    Returns:
    - JSON: {invoices: [...], missing: [...]}
    """
    import json
    
    try:
        data = json.loads(request.body)
        invoice_numbers_str = data.get('invoice_numbers', '').strip()
        
        if not invoice_numbers_str:
            return JsonResponse({'error': 'No invoice numbers provided'}, status=400)
        
        # Parse invoice numbers (handle both newline and comma separation)
        invoice_list = []
        for line in invoice_numbers_str.replace(',', '\n').split('\n'):
            number = line.strip()
            if number:
                invoice_list.append(number)
        
        if not invoice_list:
            return JsonResponse({'error': 'No valid invoice numbers found'}, status=400)
        
        # Get invoices by number
        invoices = FeeInvoice.objects.filter(
            invoice_number__in=invoice_list,
            status__in=['PENDING', 'PARTIALLY_PAID', 'OVERDUE']
        ).select_related('student')
        
        found_data = [{
            'id': str(invoice.id),
            'number': invoice.invoice_number,
            'student': invoice.student.get_full_name(),
            'student_id': str(invoice.student.id),
            'balance': float(invoice.balance),
            'total': float(invoice.total_amount),
            'paid': float(invoice.paid_amount),
            'date': invoice.issue_date.strftime('%Y-%m-%d'),
            'session': invoice.academic_session.name if invoice.academic_session else 'N/A'
        } for invoice in invoices]
        
        # Check for missing invoices
        found_numbers = set(invoice.invoice_number for invoice in invoices)
        missing = [num for num in invoice_list if num not in found_numbers]
        
        total_balance = sum(float(inv.balance) for inv in invoices)
        
        return JsonResponse({
            'success': True,
            'invoices': found_data,
            'missing': missing,
            'total_balance': total_balance,
            'count': len(found_data)
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        logger.error(f"Error validating invoice numbers: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)

# =============================================================================
# SCHOLARSHIP PROGRAM VIEWS (CRUD + Print)
# =============================================================================

@login_required
def scholarship_program_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""
    filter_form = ScholarshipProgramFilterForm(request.GET or None)
    programs = get_filtered_scholarship_programs(request)
    
    # Calculate statistics
    stats = {
        'total': programs.count(),
        'active': programs.filter(is_active=True).count(),
        'accepting_applications': programs.filter(is_accepting_applications=True).count(),
        'total_budget': programs.aggregate(Sum('total_budget_amount'))['total_budget_amount__sum'] or 0,
        'total_used': programs.aggregate(Sum('current_budget_used'))['current_budget_used__sum'] or 0,
        'total_recipients': programs.aggregate(Sum('current_recipient_count'))['current_recipient_count__sum'] or 0,
    }
    
    # Pagination
    paginator = Paginator(programs, 20)
    page_number = request.GET.get('page', 1)
    programs_page = paginator.get_page(page_number)
    
    # Detect HTMX request
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'programs_page': programs_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    # Return appropriate template
    if is_htmx:
        return render(request, 'fees/scholarships/partials/_program_results.html', context)
    else:
        return render(request, 'fees/scholarships/program_list.html', context)

@login_required
def scholarship_program_create(request):
    """Create new scholarship program"""
    if request.method == 'POST':
        form = ScholarshipProgramForm(request.POST)
        if form.is_valid():
            try:
                program = form.save()
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f"Scholarship program '{program.name}' created successfully!"
                    response['HX-Alert-Type'] = 'success'
                    response['HX-Alert-Title'] = 'Created!'
                    response['HX-Redirect'] = reverse('fees:scholarship_program_detail', kwargs={'pk': program.pk})
                    return response
                else:
                    messages.success(
                        request,
                        f"Scholarship program '{program.name}' created successfully!",
                        extra_tags='sweetalert'
                    )
                    return redirect('fees:scholarship_program_detail', pk=program.pk)
                    
            except Exception as e:
                logger.error(f"Error creating scholarship program: {e}")
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Error creating program: {str(e)}'
                    response['HX-Alert-Type'] = 'error'
                    response['HX-Alert-Title'] = 'Error!'
                    return response
                else:
                    messages.error(request, f'Error creating program: {str(e)}')
    else:
        form = ScholarshipProgramForm()
    
    context = {
        'form': form,
        'title': 'Create Scholarship Program',
        'submit_text': 'Create Program',  # ⭐ NEW
        'submit_icon': 'fa-plus',  # ⭐ NEW
    }
    
    return render(request, 'fees/scholarships/program_form.html', context)

@login_required
def scholarship_program_detail(request, pk):
    """View scholarship program details with category discount summary"""
    program = get_object_or_404(ScholarshipProgram, pk=pk)
    
    # Get recipients
    recipients = program.student_scholarships.select_related(
        'student'
    ).filter(status='ACTIVE').order_by('-start_date')[:20]
    
    # Get applications
    applications = program.applications.select_related(
        'student'
    ).order_by('-application_date')[:20]
    
    # Calculate stats
    total_disbursed = recipients.aggregate(
        total=Sum('total_amount_used')
    )['total'] or Decimal('0.00')
    
    # Handle budget remaining calculation
    if program.total_budget_amount is not None:
        budget_remaining = program.total_budget_amount - (program.current_budget_used or Decimal('0'))
    else:
        budget_remaining = None
    
    # ⭐ NEW: Get category discount summary
    discount_summary = program.get_discount_summary()
    category_template = None
    
    if program.is_category_specific_discount():
        category_template = program.get_category_discount_template()
        
        # Get all fee categories for display
        all_categories = FeesCategory.objects.filter(is_active=True).order_by(
            'display_group__display_order', 'display_order'
        )
    else:
        all_categories = None
    
    context = {
        'program': program,
        'recipients': recipients,
        'applications': applications,
        'total_disbursed': total_disbursed,
        'budget_remaining': budget_remaining,
        'discount_summary': discount_summary,  # ⭐ NEW
        'category_template': category_template,  # ⭐ NEW
        'all_categories': all_categories,  # ⭐ NEW
    }
    
    return render(request, 'fees/scholarships/program_detail.html', context)

@login_required
def scholarship_program_edit(request, pk):
    """Edit scholarship program"""
    program = get_object_or_404(ScholarshipProgram, pk=pk)
    
    if request.method == 'POST':
        form = ScholarshipProgramForm(request.POST, instance=program)
        if form.is_valid():
            try:
                program = form.save()
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f"Scholarship program '{program.name}' updated successfully!"
                    response['HX-Alert-Type'] = 'success'
                    response['HX-Alert-Title'] = 'Updated!'
                    response['HX-Redirect'] = reverse('fees:scholarship_program_detail', kwargs={'pk': program.pk})
                    return response
                else:
                    messages.success(
                        request,
                        f"Scholarship program '{program.name}' updated successfully!",
                        extra_tags='sweetalert'
                    )
                    return redirect('fees:scholarship_program_detail', pk=program.pk)
                    
            except Exception as e:
                logger.error(f"Error updating scholarship program: {e}")
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Error updating program: {str(e)}'
                    response['HX-Alert-Type'] = 'error'
                    response['HX-Alert-Title'] = 'Error!'
                    return response
                else:
                    messages.error(request, f'Error updating program: {str(e)}')
    else:
        form = ScholarshipProgramForm(instance=program)
    
    context = {
        'form': form,
        'program': program,
        'title': f'Edit Scholarship Program - {program.name}',
        'submit_text': 'Update Program',  # ⭐ NEW
        'submit_icon': 'fa-save',  # ⭐ NEW
    }
    
    return render(request, 'fees/scholarships/program_form.html', context)

@login_required
@require_http_methods(["POST"])
def scholarship_program_delete(request, pk):
    """Delete scholarship program with HTMX support"""
    program = get_object_or_404(ScholarshipProgram, pk=pk)
    
    # Check if program has active scholarships
    if program.student_scholarships.filter(status='ACTIVE').exists():
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Cannot delete '{program.name}' because it has active scholarships"
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Cannot Delete'
            response['HX-Close-Modal'] = 'true'
            return response
        else:
            messages.error(
                request,
                f"Cannot delete '{program.name}' because it has active scholarships",
                extra_tags='sweetalert-error'
            )
            return redirect('fees:scholarship_program_detail', pk=pk)
    
    program_name = program.name
    program.delete()
    
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    if is_htmx:
        response = HttpResponse()
        response['HX-Alert-Message'] = f"Scholarship program '{program_name}' deleted successfully"
        response['HX-Alert-Type'] = 'success'
        response['HX-Alert-Title'] = 'Deleted!'
        response['HX-Close-Modal'] = 'true'
        response['HX-Redirect'] = reverse('fees:scholarship_program_list')
        return response
    else:
        messages.success(
            request,
            f"Scholarship program '{program_name}' deleted successfully",
            extra_tags='sweetalert'
        )
        return redirect('fees:scholarship_program_list')
    
@login_required
@require_http_methods(["POST"])
def scholarship_program_activate(request, pk):
    """Activate scholarship program"""
    program = get_object_or_404(ScholarshipProgram, pk=pk)
    
    try:
        with transaction.atomic():
            program.is_active = True
            program.save()
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Scholarship program '{program.name}' activated!"
            response['HX-Alert-Type'] = 'success'
            response['HX-Alert-Title'] = 'Program Activated'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('fees:scholarship_program_detail', kwargs={'pk': program.pk})
            return response
        else:
            messages.success(request, f"Scholarship program '{program.name}' activated!")
            return redirect('fees:scholarship_program_detail', pk=program.pk)
    
    except Exception as e:
        logger.error(f"Error activating scholarship program: {e}", exc_info=True)
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f'Error activating program: {str(e)}'
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Error'
            return response
        else:
            messages.error(request, f'Error activating program: {str(e)}')
            return redirect('fees:scholarship_program_detail', pk=pk)


@login_required
@require_http_methods(["POST"])
def scholarship_program_deactivate(request, pk):
    """Deactivate scholarship program"""
    program = get_object_or_404(ScholarshipProgram, pk=pk)
    
    try:
        deactivation_reason = request.POST.get('deactivation_reason', '')
        
        with transaction.atomic():
            program.is_active = False
            program.is_accepting_applications = False
            if deactivation_reason:
                program.description = f"{program.description}\n\nDeactivated: {deactivation_reason}".strip()
            program.save()
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Scholarship program '{program.name}' deactivated!"
            response['HX-Alert-Type'] = 'success'
            response['HX-Alert-Title'] = 'Program Deactivated'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('fees:scholarship_program_detail', kwargs={'pk': program.pk})
            return response
        else:
            messages.success(request, f"Scholarship program '{program.name}' deactivated!")
            return redirect('fees:scholarship_program_detail', pk=program.pk)
    
    except Exception as e:
        logger.error(f"Error deactivating scholarship program: {e}", exc_info=True)
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f'Error deactivating program: {str(e)}'
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Error'
            return response
        else:
            messages.error(request, f'Error deactivating program: {str(e)}')
            return redirect('fees:scholarship_program_detail', pk=pk)


@login_required
@require_http_methods(["POST"])
def scholarship_toggle_accepting(request, pk):
    """Toggle whether scholarship program is accepting applications"""
    program = get_object_or_404(ScholarshipProgram, pk=pk)
    
    try:
        with transaction.atomic():
            program.is_accepting_applications = not program.is_accepting_applications
            program.save()
        
        status = "accepting" if program.is_accepting_applications else "not accepting"
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Program is now {status} applications!"
            response['HX-Alert-Type'] = 'success'
            response['HX-Alert-Title'] = 'Status Updated'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('fees:scholarship_program_detail', kwargs={'pk': program.pk})
            return response
        else:
            messages.success(request, f"Program is now {status} applications!")
            return redirect('fees:scholarship_program_detail', pk=program.pk)
    
    except Exception as e:
        logger.error(f"Error toggling application status: {e}", exc_info=True)
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f'Error updating status: {str(e)}'
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Error'
            return response
        else:
            messages.error(request, f'Error updating status: {str(e)}')
            return redirect('fees:scholarship_program_detail', pk=pk)

@login_required
def scholarship_program_list_print_view(request):
    """Generate printable scholarship program list"""
    
    programs = ScholarshipProgram.objects.annotate(
        recipient_count=Count('student_scholarships', filter=Q(student_scholarships__status='ACTIVE'))
    ).order_by('name')
    
    # Get summary stats
    summary = programs.aggregate(
        total_budget=Sum('total_budget_amount'),
        total_used=Sum('current_budget_used'),
        total_recipients=Sum('current_recipient_count'),
    )
    
    context = {
        'programs': programs,
        'summary': summary,
        'now': timezone.now(),
        'title': 'Scholarship Programs',
    }
    
    return render(request, 'fees/scholarships/print_program_list.html', context)


# =============================================================================
# SCHOLARSHIP APPLICATION VIEWS (CRUD + Approval)
# =============================================================================

@login_required
def scholarship_application_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""
    filter_form = ScholarshipApplicationFilterForm(request.GET or None)
    applications = get_filtered_scholarship_applications(request)
    
    # Calculate statistics
    stats = {
        'total': applications.count(),
        'submitted': applications.filter(status='SUBMITTED').count(),
        'under_review': applications.filter(status='UNDER_REVIEW').count(),
        'approved': applications.filter(status='APPROVED').count(),
        'rejected': applications.filter(status='REJECTED').count(),
        'total_requested': applications.aggregate(Sum('requested_amount'))['requested_amount__sum'] or 0,
        'total_approved_amount': applications.filter(status='APPROVED').aggregate(
            Sum('approved_amount'))['approved_amount__sum'] or 0,
    }
    
    # Pagination
    paginator = Paginator(applications, 20)
    page_number = request.GET.get('page', 1)
    applications_page = paginator.get_page(page_number)
    
    # Detect HTMX request
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'applications_page': applications_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    # Return appropriate template
    if is_htmx:
        return render(request, 'fees/scholarships/partials/_application_results.html', context)
    else:
        return render(request, 'fees/scholarships/application_list.html', context)

@login_required
def scholarship_application_create(request):
    """Create new scholarship application"""
    
    # Get student if specified
    student_id = request.GET.get('student')
    student = None
    if student_id:
        student = get_object_or_404(Student, pk=student_id)
    
    if request.method == 'POST':
        form = StudentScholarshipApplicationForm(request.POST)
        if form.is_valid():
            try:
                application = form.save()
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = 'Scholarship application submitted successfully!'
                    response['HX-Alert-Type'] = 'success'
                    response['HX-Alert-Title'] = 'Submitted!'
                    response['HX-Redirect'] = reverse('fees:scholarship_application_detail', kwargs={'pk': application.pk})
                    return response
                else:
                    messages.success(
                        request,
                        'Scholarship application submitted successfully!'
                    )
                    return redirect('fees:scholarship_application_detail', pk=application.pk)
                    
            except Exception as e:
                logger.error(f"Error creating scholarship application: {e}")
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Error creating application: {str(e)}'
                    response['HX-Alert-Type'] = 'error'
                    response['HX-Alert-Title'] = 'Error!'
                    return response
                else:
                    messages.error(request, f'Error creating application: {str(e)}')
    else:
        initial = {}
        if student:
            initial['student'] = student
        
        form = StudentScholarshipApplicationForm(initial=initial, student=student)
    
    context = {
        'form': form,
        'student': student,
        'title': 'Apply for Scholarship',
        'submit_text': 'Submit Application',
    }
    
    return render(request, 'fees/scholarships/application_form.html', context)

@login_required
@require_http_methods(["POST"])
def scholarship_application_delete(request, pk):
    """Delete scholarship application with HTMX support"""
    application = get_object_or_404(StudentScholarshipApplication, pk=pk)
    
    # Cannot delete approved applications
    if application.status == 'APPROVED':
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = "Cannot delete approved scholarship applications"
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Cannot Delete'
            response['HX-Close-Modal'] = 'true'
            return response
        else:
            messages.error(
                request,
                "Cannot delete approved scholarship applications",
                extra_tags='sweetalert-error'
            )
            return redirect('fees:scholarship_application_detail', pk=pk)
    
    application.delete()
    
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    if is_htmx:
        response = HttpResponse()
        response['HX-Alert-Message'] = "Scholarship application deleted successfully"
        response['HX-Alert-Type'] = 'success'
        response['HX-Alert-Title'] = 'Deleted!'
        response['HX-Close-Modal'] = 'true'
        response['HX-Redirect'] = reverse('fees:scholarship_application_list')
        return response
    else:
        messages.success(
            request,
            "Scholarship application deleted successfully",
            extra_tags='sweetalert'
        )
        return redirect('fees:scholarship_application_list')

@login_required
def scholarship_application_detail(request, pk):
    """View scholarship application details"""
    
    application = get_object_or_404(
        StudentScholarshipApplication.objects.select_related(
            'student', 'scholarship_program', 'academic_session'
        ),
        pk=pk
    )
    
    context = {
        'application': application,
    }
    
    return render(request, 'fees/scholarships/application_detail.html', context)


@login_required
def scholarship_application_approve(request, pk):
    """Approve or reject scholarship application"""
    
    application = get_object_or_404(StudentScholarshipApplication, pk=pk)
    
    if application.status != 'PENDING':
        messages.info(request, 'Application has already been processed.')
        return redirect('fees:scholarship_program_detail', pk=application.scholarship_program.pk)
    
    if request.method == 'POST':
        form = ScholarshipApplicationApprovalForm(request.POST)
        if form.is_valid():
            try:
                decision = form.cleaned_data['decision']
                approved_amount = form.cleaned_data.get('approved_amount')
                notes = form.cleaned_data.get('decision_reason', '')
                
                with transaction.atomic():
                    if decision == 'APPROVE':
                        # Update application
                        application.status = 'APPROVED'
                        application.approved_by_id = str(request.user.id)
                        application.approval_date = timezone.now()
                        application.approved_amount = approved_amount
                        application.decision_reason = notes
                        application.save()
                        
                        # Create student scholarship
                        StudentScholarship.objects.create(
                            student=application.student,
                            scholarship_program=application.scholarship_program,
                            academic_session=application.academic_session,
                            amount_awarded=approved_amount,
                            status='ACTIVE',
                            application=application,
                        )
                        
                        messages.success(request, 'Scholarship application approved!')
                        
                    elif decision == 'REJECT':
                        application.status = 'REJECTED'
                        application.approved_by_id = str(request.user.id)
                        application.approval_date = timezone.now()
                        application.decision_reason = notes
                        application.save()
                        
                        messages.info(request, 'Scholarship application rejected.')
                        
                    else:  # WAITLIST
                        application.status = 'WAITLISTED'
                        application.decision_reason = notes
                        application.save()
                        
                        messages.info(request, 'Application added to waitlist.')
                
                return redirect('fees:scholarship_program_detail', pk=application.scholarship_program.pk)
                
            except Exception as e:
                logger.error(f"Error processing application: {e}")
                messages.error(request, f'Error processing application: {str(e)}')
    else:
        form = ScholarshipApplicationApprovalForm(
            initial={'approved_amount': application.requested_amount}
        )
    
    context = {
        'form': form,
        'application': application,
        'title': f'Review Application - {application.student.get_full_name()}',
    }
    
    return render(request, 'fees/scholarships/approve_application.html', context)


@login_required
def scholarship_application_list_print_view(request):
    """Generate printable scholarship application list"""
    
    # Get filter parameters
    filters = {}
    if request.GET.get('program'):
        filters['scholarship_program'] = request.GET.get('program')
    if request.GET.get('status'):
        filters['status'] = request.GET.get('status')
    
    # Build queryset
    applications = StudentScholarshipApplication.objects.select_related(
        'student', 'scholarship_program'
    ).order_by('-application_date')
    
    if filters.get('scholarship_program'):
        applications = applications.filter(scholarship_program_id=filters['scholarship_program'])
    if filters.get('status'):
        applications = applications.filter(status=filters['status'])
    
    # Get summary stats
    summary = applications.aggregate(
        total_requested=Sum('requested_amount'),
        total_approved=Sum('approved_amount'),
    )
    
    context = {
        'applications': applications[:100],
        'summary': summary,
        'filters': filters,
        'now': timezone.now(),
        'title': 'Scholarship Applications',
    }
    
    return render(request, 'fees/scholarships/print_application_list.html', context)


# =============================================================================
# STUDENT SCHOLARSHIP VIEWS (CRUD)
# =============================================================================

@login_required
def student_scholarship_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""
    filter_form = StudentScholarshipFilterForm(request.GET or None)
    scholarships = get_filtered_student_scholarships(request)
    
    # ⭐ ENHANCED: Calculate statistics with category-specific breakdown
    stats = {
        'total': scholarships.count(),
        'active': scholarships.filter(status='ACTIVE').count(),
        'suspended': scholarships.filter(status='SUSPENDED').count(),
        'completed': scholarships.filter(status='COMPLETED').count(),
        'total_awarded': scholarships.aggregate(Sum('amount_awarded'))['amount_awarded__sum'] or 0,
        'total_used': scholarships.aggregate(Sum('total_amount_used'))['total_amount_used__sum'] or 0,
        'renewable': scholarships.filter(is_renewable=True).count(),
        
        # ⭐ NEW: Category-specific stats
        'category_specific_count': scholarships.filter(use_category_specific_discounts=True).count(),
        'global_discount_count': scholarships.filter(use_category_specific_discounts=False).count(),
        'policy_based_count': scholarships.filter(
            scholarship_program__program_type='POLICY_BASED'
        ).count(),
        'budget_based_count': scholarships.filter(
            scholarship_program__program_type__in=['BUDGETED', 'SPONSORED'],
            amount_awarded__gt=0
        ).count(),
    }
    
    # Pagination
    paginator = Paginator(scholarships, 20)
    page_number = request.GET.get('page', 1)
    scholarships_page = paginator.get_page(page_number)
    
    # Detect HTMX request
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'scholarships_page': scholarships_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    # Return appropriate template
    if is_htmx:
        return render(request, 'fees/scholarships/partials/_scholarship_results.html', context)
    else:
        return render(request, 'fees/scholarships/scholarship_list.html', context)

@login_required
def student_scholarship_create(request):
    """Create new student scholarship (manual award)"""
    
    # Get application if specified
    application_id = request.GET.get('application')
    application = None
    if application_id:
        application = get_object_or_404(StudentScholarshipApplication, pk=application_id)
    
    if request.method == 'POST':
        form = StudentScholarshipForm(request.POST)
        if form.is_valid():
            try:
                scholarship = form.save()
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f"Scholarship awarded to {scholarship.student.get_full_name()} successfully!"
                    response['HX-Alert-Type'] = 'success'
                    response['HX-Alert-Title'] = 'Awarded!'
                    response['HX-Redirect'] = reverse('fees:student_scholarship_detail', kwargs={'pk': scholarship.pk})
                    return response
                else:
                    messages.success(
                        request,
                        f"Scholarship awarded to {scholarship.student.get_full_name()} successfully!"
                    )
                    return redirect('fees:student_scholarship_detail', pk=scholarship.pk)
                    
            except Exception as e:
                logger.error(f"Error awarding scholarship: {e}")
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Error awarding scholarship: {str(e)}'
                    response['HX-Alert-Type'] = 'error'
                    response['HX-Alert-Title'] = 'Error!'
                    return response
                else:
                    messages.error(request, f'Error awarding scholarship: {str(e)}')
    else:
        initial = {}
        if application:
            initial = {
                'student': application.student,
                'scholarship_program': application.scholarship_program,
                'application': application,
                'amount_awarded': application.approved_amount or application.requested_amount,
            }
        
        form = StudentScholarshipForm(initial=initial, application=application)
    
    context = {
        'form': form,
        'application': application,
        'title': 'Award Scholarship',
        'submit_text': 'Award Scholarship',
    }
    
    return render(request, 'fees/scholarships/scholarship_form.html', context)

@login_required
def student_scholarship_detail(request, pk):
    """View student scholarship details with category discount info"""
    
    scholarship = get_object_or_404(
        StudentScholarship.objects.select_related(
            'student', 'scholarship_program', 'application'
        ),
        pk=pk
    )
    
    # Get application logs
    application_logs = scholarship.application_logs.select_related(
        'invoice'
    ).order_by('-created_at')[:20]
    
    # ⭐ NEW: Get category discount summary
    discount_summary = scholarship.get_category_discount_summary()
    
    # ⭐ NEW: Get all categories if category-specific
    if scholarship.is_category_specific():
        all_categories = FeesCategory.objects.filter(is_active=True).order_by(
            'display_group__display_order', 'display_order'
        )
    else:
        all_categories = None
    
    context = {
        'scholarship': scholarship,
        'application_logs': application_logs,
        'discount_summary': discount_summary,  # ⭐ NEW
        'all_categories': all_categories,  # ⭐ NEW
    }
    
    return render(request, 'fees/scholarships/scholarship_detail.html', context)

@login_required
def student_scholarship_edit(request, pk):
    """Edit student scholarship"""
    
    scholarship = get_object_or_404(StudentScholarship, pk=pk)
    
    if request.method == 'POST':
        form = StudentScholarshipForm(request.POST, instance=scholarship)
        if form.is_valid():
            try:
                scholarship = form.save()
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f"Scholarship for {scholarship.student.get_full_name()} updated successfully!"
                    response['HX-Alert-Type'] = 'success'
                    response['HX-Alert-Title'] = 'Updated!'
                    response['HX-Redirect'] = reverse('fees:student_scholarship_detail', kwargs={'pk': scholarship.pk})
                    return response
                else:
                    messages.success(
                        request,
                        f"Scholarship for {scholarship.student.get_full_name()} updated successfully!"
                    )
                    return redirect('fees:student_scholarship_detail', pk=scholarship.pk)
                    
            except Exception as e:
                logger.error(f"Error updating scholarship: {e}")
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Error updating scholarship: {str(e)}'
                    response['HX-Alert-Type'] = 'error'
                    response['HX-Alert-Title'] = 'Error!'
                    return response
                else:
                    messages.error(request, f'Error updating scholarship: {str(e)}')
    else:
        form = StudentScholarshipForm(instance=scholarship)
    
    context = {
        'form': form,
        'scholarship': scholarship,
        'title': f'Edit Scholarship - {scholarship.student.get_full_name()}',
        'submit_text': 'Update Scholarship',
    }
    
    return render(request, 'fees/scholarships/scholarship_form.html', context)

@login_required
@require_http_methods(["POST"])
def student_scholarship_delete(request, pk):
    """Delete student scholarship with HTMX support"""
    scholarship = get_object_or_404(StudentScholarship, pk=pk)
    
    # Cannot delete active scholarships
    if scholarship.status == 'ACTIVE':
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = "Cannot delete active scholarships. Suspend or terminate first."
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Cannot Delete'
            response['HX-Close-Modal'] = 'true'
            return response
        else:
            messages.error(
                request,
                "Cannot delete active scholarships. Suspend or terminate first.",
                extra_tags='sweetalert-error'
            )
            return redirect('fees:student_scholarship_detail', pk=pk)
    
    scholarship.delete()
    
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    if is_htmx:
        response = HttpResponse()
        response['HX-Alert-Message'] = "Scholarship deleted successfully"
        response['HX-Alert-Type'] = 'success'
        response['HX-Alert-Title'] = 'Deleted!'
        response['HX-Close-Modal'] = 'true'
        response['HX-Redirect'] = reverse('fees:student_scholarship_list')
        return response
    else:
        messages.success(
            request,
            "Scholarship deleted successfully",
            extra_tags='sweetalert'
        )
        return redirect('fees:student_scholarship_list')

@login_required
def student_scholarship_suspend(request, pk):
    """Suspend student scholarship"""
    
    scholarship = get_object_or_404(StudentScholarship, pk=pk)
    
    if scholarship.status != 'ACTIVE':
        messages.warning(request, 'Only active scholarships can be suspended.')
        return redirect('fees:student_scholarship_detail', pk=pk)
    
    if request.method == 'POST':
        try:
            scholarship.status = 'SUSPENDED'
            scholarship.save()
            
            messages.success(
                request,
                f'Scholarship for {scholarship.student.get_full_name()} suspended.'
            )
            return redirect('fees:student_scholarship_detail', pk=pk)
            
        except Exception as e:
            logger.error(f"Error suspending scholarship: {e}")
            messages.error(request, f'Error suspending scholarship: {str(e)}')
    
    context = {
        'scholarship': scholarship,
        'title': 'Suspend Scholarship',
    }
    
    return render(request, 'fees/scholarships/suspend_scholarship.html', context)


@login_required
def student_scholarship_terminate(request, pk):
    """Terminate student scholarship"""
    
    scholarship = get_object_or_404(StudentScholarship, pk=pk)
    
    if scholarship.status == 'TERMINATED':
        messages.warning(request, 'Scholarship is already terminated.')
        return redirect('fees:student_scholarship_detail', pk=pk)
    
    if request.method == 'POST':
        try:
            scholarship.status = 'TERMINATED'
            scholarship.save()
            
            messages.success(
                request,
                f'Scholarship for {scholarship.student.get_full_name()} terminated.'
            )
            return redirect('fees:student_scholarship_detail', pk=pk)
            
        except Exception as e:
            logger.error(f"Error terminating scholarship: {e}")
            messages.error(request, f'Error terminating scholarship: {str(e)}')
    
    context = {
        'scholarship': scholarship,
        'title': 'Terminate Scholarship',
    }
    
    return render(request, 'fees/scholarships/terminate_scholarship.html', context)

@login_required
@require_http_methods(["POST"])
def student_scholarship_reactivate(request, pk):
    """Reactivate suspended scholarship"""
    scholarship = get_object_or_404(StudentScholarship, pk=pk)
    
    if scholarship.status != 'SUSPENDED':
        messages.warning(request, 'Only suspended scholarships can be reactivated.')
        return redirect('fees:student_scholarship_detail', pk=pk)
    
    try:
        reactivation_reason = request.POST.get('reactivation_reason', '')
        
        with transaction.atomic():
            scholarship.status = 'ACTIVE'
            scholarship.notes = f"{scholarship.notes}\n\nReactivated on {get_school_today()}: {reactivation_reason}".strip()
            scholarship.save()
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Scholarship for {scholarship.student.get_full_name()} reactivated!"
            response['HX-Alert-Type'] = 'success'
            response['HX-Alert-Title'] = 'Scholarship Reactivated'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('fees:student_scholarship_detail', kwargs={'pk': scholarship.pk})
            return response
        else:
            messages.success(request, f"Scholarship for {scholarship.student.get_full_name()} reactivated!")
            return redirect('fees:student_scholarship_detail', pk=scholarship.pk)
    
    except Exception as e:
        logger.error(f"Error reactivating scholarship: {e}", exc_info=True)
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f'Error reactivating scholarship: {str(e)}'
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Error'
            return response
        else:
            messages.error(request, f'Error reactivating scholarship: {str(e)}')
            return redirect('fees:student_scholarship_detail', pk=pk)


@login_required
@require_http_methods(["POST"])
def student_scholarship_complete(request, pk):
    """Mark scholarship as completed"""
    scholarship = get_object_or_404(StudentScholarship, pk=pk)
    
    if scholarship.status != 'ACTIVE':
        messages.warning(request, 'Only active scholarships can be marked as completed.')
        return redirect('fees:student_scholarship_detail', pk=pk)
    
    try:
        completion_reason = request.POST.get('completion_reason', '')
        
        with transaction.atomic():
            scholarship.status = 'COMPLETED'
            scholarship.end_date = get_school_today()
            scholarship.notes = f"{scholarship.notes}\n\nCompleted on {get_school_today()}: {completion_reason}".strip()
            scholarship.save()
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Scholarship for {scholarship.student.get_full_name()} marked as completed!"
            response['HX-Alert-Type'] = 'success'
            response['HX-Alert-Title'] = 'Scholarship Completed'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('fees:student_scholarship_detail', kwargs={'pk': scholarship.pk})
            return response
        else:
            messages.success(request, f"Scholarship for {scholarship.student.get_full_name()} marked as completed!")
            return redirect('fees:student_scholarship_detail', pk=scholarship.pk)
    
    except Exception as e:
        logger.error(f"Error completing scholarship: {e}", exc_info=True)
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f'Error completing scholarship: {str(e)}'
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Error'
            return response
        else:
            messages.error(request, f'Error completing scholarship: {str(e)}')
            return redirect('fees:student_scholarship_detail', pk=pk)


@login_required
@require_http_methods(["POST"])
def apply_scholarship_to_invoice(request, invoice_pk, scholarship_pk):
    """Manually apply scholarship to specific invoice"""
    invoice = get_object_or_404(FeeInvoice, pk=invoice_pk)
    scholarship = get_object_or_404(StudentScholarship, pk=scholarship_pk)
    
    # Validate
    if scholarship.student != invoice.student:
        messages.error(request, 'Scholarship and invoice belong to different students.')
        return redirect('fees:invoice_detail', pk=invoice_pk)
    
    if scholarship.status != 'ACTIVE':
        messages.error(request, f'Scholarship is {scholarship.get_status_display()}, not ACTIVE.')
        return redirect('fees:invoice_detail', pk=invoice_pk)
    
    if invoice.status not in ['PENDING', 'PARTIALLY_PAID', 'OVERDUE']:
        messages.error(request, f'Cannot apply scholarship to {invoice.get_status_display()} invoice.')
        return redirect('fees:invoice_detail', pk=invoice_pk)
    
    try:
        with transaction.atomic():
            # Apply scholarship using model method
            discount_applied = scholarship.apply_discount_to_invoice(invoice)
            
            if discount_applied > 0:
                invoice.has_scholarships_applied = True
                invoice.save()
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Scholarship discount of {discount_applied:,.2f} applied to invoice!"
            response['HX-Alert-Type'] = 'success'
            response['HX-Alert-Title'] = 'Scholarship Applied'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('fees:invoice_detail', kwargs={'pk': invoice.pk})
            return response
        else:
            messages.success(request, f"Scholarship discount of {discount_applied:,.2f} applied to invoice!")
            return redirect('fees:invoice_detail', pk=invoice.pk)
    
    except Exception as e:
        logger.error(f"Error applying scholarship to invoice: {e}", exc_info=True)
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f'Error applying scholarship: {str(e)}'
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Error'
            return response
        else:
            messages.error(request, f'Error applying scholarship: {str(e)}')
            return redirect('fees:invoice_detail', pk=invoice_pk)

@login_required
def student_scholarship_list_print_view(request):
    """Generate printable student scholarship list"""
    
    scholarships = StudentScholarship.objects.select_related(
        'student', 'scholarship_program'
    ).order_by('-awarded_date')
    
    # Get summary stats
    summary = scholarships.aggregate(
        total_awarded=Sum('amount_awarded'),
        total_used=Sum('total_amount_used'),
    )
    
    context = {
        'scholarships': scholarships[:100],
        'summary': summary,
        'now': timezone.now(),
        'title': 'Student Scholarships',
    }
    
    return render(request, 'fees/scholarships/print_scholarship_list.html', context)


# =============================================================================
# DISCOUNT VIEWS (CRUD + Print)
# =============================================================================

@login_required
def discount_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""
    filter_form = FeesDiscountFilterForm(request.GET or None)
    discounts = get_filtered_discounts(request)
    
    # Calculate statistics
    stats = {
        'total': discounts.count(),
        'active': discounts.filter(is_active=True).count(),
        'auto_apply': discounts.filter(auto_apply=True).count(),
        'percentage': discounts.filter(discount_type='PERCENTAGE').count(),
        'fixed': discounts.filter(discount_type='FIXED').count(),
        'total_budget': discounts.aggregate(Sum('budget_limit'))['budget_limit__sum'] or 0,
        'total_used': discounts.aggregate(Sum('current_budget_used'))['current_budget_used__sum'] or 0,
    }
    
    # Pagination
    paginator = Paginator(discounts, 20)
    page_number = request.GET.get('page', 1)
    discounts_page = paginator.get_page(page_number)
    
    # Detect HTMX request
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'discounts_page': discounts_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    # Return appropriate template
    if is_htmx:
        return render(request, 'fees/discounts/partials/_discount_results.html', context)
    else:
        return render(request, 'fees/discounts/list.html', context)

@login_required
def discount_create(request):
    """Create new discount"""
    
    if request.method == 'POST':
        form = FeesDiscountForm(request.POST)
        if form.is_valid():
            try:
                discount = form.save()
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f"Discount '{discount.name}' created successfully!"
                    response['HX-Alert-Type'] = 'success'
                    response['HX-Alert-Title'] = 'Created!'
                    response['HX-Redirect'] = reverse('fees:discount_detail', kwargs={'pk': discount.pk})
                    return response
                else:
                    messages.success(
                        request,
                        f"Discount '{discount.name}' created successfully!"
                    )
                    return redirect('fees:discount_detail', pk=discount.pk)
                    
            except Exception as e:
                logger.error(f"Error creating discount: {e}")
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Error creating discount: {str(e)}'
                    response['HX-Alert-Type'] = 'error'
                    response['HX-Alert-Title'] = 'Error!'
                    return response
                else:
                    messages.error(request, f'Error creating discount: {str(e)}')
    else:
        form = FeesDiscountForm()
    
    context = {
        'form': form,
        'title': 'Create Fee Discount',
        'submit_text': 'Create Discount',
    }
    
    return render(request, 'fees/discounts/form.html', context)

@login_required
def discount_detail(request, pk):
    """View discount details"""
    
    discount = get_object_or_404(FeesDiscount, pk=pk)
    
    # Get recent applications
    applications = discount.applications.select_related(
        'student', 'invoice'
    ).order_by('-applied_at')[:20]
    
    context = {
        'discount': discount,
        'applications': applications,
    }
    
    return render(request, 'fees/discounts/detail.html', context)

@login_required
def discount_edit(request, pk):
    """Edit discount"""
    
    discount = get_object_or_404(FeesDiscount, pk=pk)
    
    if request.method == 'POST':
        form = FeesDiscountForm(request.POST, instance=discount)
        if form.is_valid():
            try:
                discount = form.save()
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f"Discount '{discount.name}' updated successfully!"
                    response['HX-Alert-Type'] = 'success'
                    response['HX-Alert-Title'] = 'Updated!'
                    response['HX-Redirect'] = reverse('fees:discount_detail', kwargs={'pk': discount.pk})
                    return response
                else:
                    messages.success(
                        request,
                        f"Discount '{discount.name}' updated successfully!"
                    )
                    return redirect('fees:discount_detail', pk=discount.pk)
                    
            except Exception as e:
                logger.error(f"Error updating discount: {e}")
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Error updating discount: {str(e)}'
                    response['HX-Alert-Type'] = 'error'
                    response['HX-Alert-Title'] = 'Error!'
                    return response
                else:
                    messages.error(request, f'Error updating discount: {str(e)}')
    else:
        form = FeesDiscountForm(instance=discount)
    
    context = {
        'form': form,
        'discount': discount,
        'title': f'Edit Discount - {discount.name}',
        'submit_text': 'Update Discount',
    }
    
    return render(request, 'fees/discounts/form.html', context)

@login_required
@require_http_methods(["POST"])
def discount_delete(request, pk):
    """Delete discount with HTMX support"""
    discount = get_object_or_404(FeesDiscount, pk=pk)
    
    # Check if discount has many applications
    application_count = discount.applications.count()
    if application_count > 10:
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Cannot delete '{discount.name}' because it has {application_count} applications"
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Cannot Delete'
            response['HX-Close-Modal'] = 'true'
            return response
        else:
            messages.error(
                request,
                f"Cannot delete '{discount.name}' because it has {application_count} applications",
                extra_tags='sweetalert-error'
            )
            return redirect('fees:discount_detail', pk=pk)
    
    discount_name = discount.name
    discount.delete()
    
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    if is_htmx:
        response = HttpResponse()
        response['HX-Alert-Message'] = f"Discount '{discount_name}' deleted successfully"
        response['HX-Alert-Type'] = 'success'
        response['HX-Alert-Title'] = 'Deleted!'
        response['HX-Close-Modal'] = 'true'
        response['HX-Redirect'] = reverse('fees:discount_list')
        return response
    else:
        messages.success(
            request,
            f"Discount '{discount_name}' deleted successfully",
            extra_tags='sweetalert'
        )
        return redirect('fees:discount_list')
    
@login_required
@require_http_methods(["POST"])
def discount_toggle_active(request, pk):
    """Toggle discount active status"""
    discount = get_object_or_404(FeesDiscount, pk=pk)
    
    try:
        with transaction.atomic():
            discount.is_active = not discount.is_active
            discount.save()
        
        status = "activated" if discount.is_active else "deactivated"
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Discount '{discount.name}' {status}!"
            response['HX-Alert-Type'] = 'success'
            response['HX-Alert-Title'] = 'Status Updated'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('fees:discount_detail', kwargs={'pk': discount.pk})
            return response
        else:
            messages.success(request, f"Discount '{discount.name}' {status}!")
            return redirect('fees:discount_detail', pk=discount.pk)
    
    except Exception as e:
        logger.error(f"Error toggling discount status: {e}", exc_info=True)
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f'Error updating status: {str(e)}'
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Error'
            return response
        else:
            messages.error(request, f'Error updating status: {str(e)}')
            return redirect('fees:discount_detail', pk=pk)


@login_required
@require_http_methods(["POST"])
def apply_discount_to_invoice(request, invoice_pk, discount_pk=None):
    """Manually apply discount to invoice"""
    invoice = get_object_or_404(FeeInvoice, pk=invoice_pk)
    
    if invoice.status not in ['PENDING', 'PARTIALLY_PAID', 'OVERDUE']:
        messages.error(request, f'Cannot apply discount to {invoice.get_status_display()} invoice.')
        return redirect('fees:invoice_detail', pk=invoice_pk)
    
    try:
        # Get discount from POST if not in URL
        if not discount_pk:
            discount_pk = request.POST.get('discount_id')
        
        if not discount_pk:
            raise ValueError("Discount ID is required")
        
        discount = get_object_or_404(FeesDiscount, pk=discount_pk)
        
        # Validate discount is active
        if not discount.is_active:
            raise ValueError("Discount is not active")
        
        # Check date validity
        today = get_school_today()
        if discount.start_date and today < discount.start_date:
            raise ValueError("Discount period has not started")
        if discount.end_date and today > discount.end_date:
            raise ValueError("Discount period has ended")
        
        with transaction.atomic():
            # Calculate discount amount
            if discount.discount_type == 'PERCENTAGE':
                discount_amount = (invoice.balance * discount.discount_value / 100).quantize(Decimal('0.01'))
            else:  # FIXED
                discount_amount = discount.discount_value
            
            discount_amount = min(discount_amount, invoice.balance)
            
            # Apply discount
            invoice.discount_amount += discount_amount
            invoice.total_amount -= discount_amount
            invoice.balance -= discount_amount
            invoice.has_discounts_applied = True
            invoice.save()
            
            # Create discount application record
            DiscountApplication.objects.create(
                discount=discount,
                student=invoice.student,
                invoice=invoice,
                amount=discount_amount,
                applied_at=timezone.now(),
                applied_by_id=str(request.user.id),
            )
            
            # Update discount usage
            discount.current_usage_count = F('current_usage_count') + 1
            discount.current_budget_used = F('current_budget_used') + discount_amount
            discount.save()
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Discount of {discount_amount:,.2f} applied to invoice!"
            response['HX-Alert-Type'] = 'success'
            response['HX-Alert-Title'] = 'Discount Applied'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('fees:invoice_detail', kwargs={'pk': invoice.pk})
            return response
        else:
            messages.success(request, f"Discount of {discount_amount:,.2f} applied to invoice!")
            return redirect('fees:invoice_detail', pk=invoice.pk)
    
    except Exception as e:
        logger.error(f"Error applying discount to invoice: {e}", exc_info=True)
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f'Error applying discount: {str(e)}'
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Error'
            return response
        else:
            messages.error(request, f'Error applying discount: {str(e)}')
            return redirect('fees:invoice_detail', pk=invoice_pk)
        
@login_required
def discount_list_print_view(request):
    """Generate printable discount list"""
    
    discounts = FeesDiscount.objects.order_by('priority', 'name')
    
    # Get summary stats
    summary = discounts.aggregate(
        total_budget=Sum('budget_limit'),
        total_used=Sum('current_budget_used'),
        total_usage=Sum('current_usage_count'),
    )
    
    context = {
        'discounts': discounts,
        'summary': summary,
        'now': timezone.now(),
        'title': 'Fee Discounts',
    }
    
    return render(request, 'fees/discounts/print_list.html', context)


# =============================================================================
# REFUND VIEWS (CRUD + Print)
# =============================================================================

@login_required
def refund_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""
    filter_form = RefundFilterForm(request.GET or None)
    refunds = get_filtered_refunds(request)
    
    # Calculate statistics
    stats = {
        'total': refunds.count(),
        'requested': refunds.filter(status='REQUESTED').count(),
        'under_review': refunds.filter(status='UNDER_REVIEW').count(),
        'approved': refunds.filter(status='APPROVED').count(),
        'rejected': refunds.filter(status='REJECTED').count(),
        'completed': refunds.filter(status='COMPLETED').count(),
        'total_amount': refunds.aggregate(Sum('amount'))['amount__sum'] or 0,
        'total_approved': refunds.filter(
            status__in=['APPROVED', 'PROCESSING', 'COMPLETED']
        ).aggregate(Sum('approved_amount'))['approved_amount__sum'] or 0,
    }
    
    # Pagination
    paginator = Paginator(refunds, 20)
    page_number = request.GET.get('page', 1)
    refunds_page = paginator.get_page(page_number)
    
    # Detect HTMX request
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'refunds_page': refunds_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    # Return appropriate template
    if is_htmx:
        return render(request, 'fees/refunds/partials/_refund_results.html', context)
    else:
        return render(request, 'fees/refunds/list.html', context)

@login_required
def refund_create(request):
    """Create new refund"""
    
    # Get invoice if specified
    invoice_id = request.GET.get('invoice')
    invoice = None
    if invoice_id:
        invoice = get_object_or_404(FeeInvoice, pk=invoice_id)
    
    if request.method == 'POST':
        form = RefundForm(request.POST)
        if form.is_valid():
            try:
                # Signals will auto-generate refund number and assign accounts
                refund = form.save()
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f"Refund '{refund.refund_number}' created successfully!"
                    response['HX-Alert-Type'] = 'success'
                    response['HX-Alert-Title'] = 'Created!'
                    response['HX-Redirect'] = reverse('fees:refund_detail', kwargs={'pk': refund.pk})
                    return response
                else:
                    messages.success(
                        request,
                        f"Refund '{refund.refund_number}' created successfully!"
                    )
                    return redirect('fees:refund_detail', pk=refund.pk)
                    
            except Exception as e:
                logger.error(f"Error creating refund: {e}")
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Error creating refund: {str(e)}'
                    response['HX-Alert-Type'] = 'error'
                    response['HX-Alert-Title'] = 'Error!'
                    return response
                else:
                    messages.error(request, f'Error creating refund: {str(e)}')
    else:
        initial = {}
        if invoice:
            initial['invoice'] = invoice
            initial['student'] = invoice.student
            initial['academic_session'] = invoice.academic_session
        
        form = RefundForm(initial=initial)
    
    context = {
        'form': form,
        'invoice': invoice,
        'title': 'Process Refund',
        'submit_text': 'Create Refund',
    }
    
    return render(request, 'fees/refunds/form.html', context)

@login_required
@require_http_methods(["POST"])
def refund_delete(request, pk):
    """Delete refund with HTMX support"""
    refund = get_object_or_404(Refund, pk=pk)
    
    # Cannot delete approved/completed refunds
    if refund.status in ['APPROVED', 'PROCESSING', 'COMPLETED']:
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Cannot delete refund with status: {refund.get_status_display()}"
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Cannot Delete'
            response['HX-Close-Modal'] = 'true'
            return response
        else:
            messages.error(
                request,
                f"Cannot delete refund with status: {refund.get_status_display()}",
                extra_tags='sweetalert-error'
            )
            return redirect('fees:refund_detail', pk=pk)
    
    refund_number = refund.refund_number
    refund.delete()
    
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    if is_htmx:
        response = HttpResponse()
        response['HX-Alert-Message'] = f"Refund '{refund_number}' deleted successfully"
        response['HX-Alert-Type'] = 'success'
        response['HX-Alert-Title'] = 'Deleted!'
        response['HX-Close-Modal'] = 'true'
        response['HX-Redirect'] = reverse('fees:refund_list')
        return response
    else:
        messages.success(
            request,
            f"Refund '{refund_number}' deleted successfully",
            extra_tags='sweetalert'
        )
        return redirect('fees:refund_list')
        
@login_required
def refund_detail(request, pk):
    """View refund details"""
    
    refund = get_object_or_404(
        Refund.objects.select_related(
            'student', 'invoice', 'payment', 'payment_method', 'academic_session'
        ),
        pk=pk
    )
    
    context = {
        'refund': refund,
    }
    
    return render(request, 'fees/refunds/detail.html', context)


@login_required
def refund_approve(request, pk):
    """Approve refund request"""
    
    refund = get_object_or_404(Refund, pk=pk)
    
    if refund.status not in ['REQUESTED', 'UNDER_REVIEW']:
        messages.warning(request, 'Refund has already been processed.')
        return redirect('fees:refund_detail', pk=pk)
    
    if request.method == 'POST':
        try:
            approved_amount = request.POST.get('approved_amount')
            notes = request.POST.get('notes', '')
            
            with transaction.atomic():
                refund.status = 'APPROVED'
                refund.approved_by_id = str(request.user.id)
                refund.approval_date = timezone.now()
                refund.approved_amount = Decimal(approved_amount) if approved_amount else refund.amount
                refund.approval_notes = notes
                refund.save()
            
            messages.success(request, f'Refund {refund.refund_number} approved.')
            return redirect('fees:refund_detail', pk=pk)
            
        except Exception as e:
            logger.error(f"Error approving refund: {e}")
            messages.error(request, f'Error approving refund: {str(e)}')
    
    context = {
        'refund': refund,
        'title': 'Approve Refund',
    }
    
    return render(request, 'fees/refunds/approve.html', context)


@login_required
def refund_process(request, pk):
    """Process approved refund"""
    
    refund = get_object_or_404(Refund, pk=pk)
    
    if refund.status != 'APPROVED':
        messages.warning(request, 'Only approved refunds can be processed.')
        return redirect('fees:refund_detail', pk=pk)
    
    if request.method == 'POST':
        try:
            transaction_id = request.POST.get('transaction_id', '')
            notes = request.POST.get('notes', '')
            
            with transaction.atomic():
                refund.status = 'COMPLETED'
                refund.processed_by_id = str(request.user.id)
                refund.processed_date = timezone.now()
                refund.transaction_id = transaction_id
                refund.processing_notes = notes
                refund.save()
            
            messages.success(request, f'Refund {refund.refund_number} processed successfully.')
            return redirect('fees:refund_detail', pk=pk)
            
        except Exception as e:
            logger.error(f"Error processing refund: {e}")
            messages.error(request, f'Error processing refund: {str(e)}')
    
    context = {
        'refund': refund,
        'title': 'Process Refund',
    }
    
    return render(request, 'fees/refunds/process.html', context)


@login_required
def refund_list_print_view(request):
    """Generate printable refund list"""
    
    # Get filter parameters
    filters = {}
    if request.GET.get('status'):
        filters['status'] = request.GET.get('status')
    
    # Build queryset
    refunds = Refund.objects.select_related(
        'student', 'payment_method'
    ).order_by('-requested_date')
    
    if filters.get('status'):
        refunds = refunds.filter(status=filters['status'])
    
    # Get summary stats
    summary = refunds.aggregate(
        total_amount=Sum('amount'),
        total_approved=Sum('approved_amount'),
    )
    
    context = {
        'refunds': refunds[:100],
        'summary': summary,
        'filters': filters,
        'now': timezone.now(),
        'title': 'Refund List',
    }
    
    return render(request, 'fees/refunds/print_list.html', context)

# =============================================================================
# DISPLAY GROUP VIEWS (CRUD + Print)
# =============================================================================

@login_required
def display_group_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""
    filter_form = DisplayGroupFilterForm(request.GET or None)
    groups = get_filtered_display_groups(request)
    
    # Calculate statistics
    stats = {
        'total': groups.count(),
        'active': groups.filter(is_active=True).count(),
        'grouped': groups.filter(show_as_group=True).count(),
        'ungrouped': groups.filter(show_as_group=False).count(),
        'total_categories': sum(g.category_count or 0 for g in groups),
    }
    
    # Pagination
    paginator = Paginator(groups, 10)
    page_number = request.GET.get('page', 1)
    groups_page = paginator.get_page(page_number)
    
    # Detect HTMX request
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'groups_page': groups_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    # Return appropriate template
    if is_htmx:
        return render(request, 'fees/display_groups/partials/_group_results.html', context)
    else:
        return render(request, 'fees/display_groups/list.html', context)


@login_required
def display_group_create(request):
    """Create new display group"""
    
    if request.method == 'POST':
        form = DisplayGroupForm(request.POST)
        if form.is_valid():
            try:
                group = form.save()
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f"Display group '{group.name}' created successfully!"
                    response['HX-Alert-Type'] = 'success'
                    response['HX-Alert-Title'] = 'Created!'
                    response['HX-Redirect'] = reverse('fees:display_group_detail', kwargs={'pk': group.pk})
                    return response
                else:
                    messages.success(
                        request,
                        f"Display group '{group.name}' created successfully!",
                        extra_tags='sweetalert'
                    )
                    return redirect('fees:display_group_detail', pk=group.pk)
                    
            except Exception as e:
                logger.error(f"Error creating display group: {e}")
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Error creating group: {str(e)}'
                    response['HX-Alert-Type'] = 'error'
                    response['HX-Alert-Title'] = 'Error!'
                    return response
                else:
                    messages.error(request, f'Error creating group: {str(e)}')
    else:
        form = DisplayGroupForm()
    
    context = {
        'form': form,
        'title': 'Create Display Group',
        'submit_text': 'Create Group',
    }
    
    return render(request, 'fees/display_groups/form.html', context)


@login_required
def display_group_detail(request, pk):
    """View display group details"""
    
    group = get_object_or_404(DisplayGroup, pk=pk)
    
    # Get categories in this group
    categories = group.feescategory_set.order_by('display_order')
    
    context = {
        'group': group,
        'categories': categories,
    }
    
    return render(request, 'fees/display_groups/detail.html', context)


@login_required
def display_group_edit(request, pk):
    """Edit display group"""
    group = get_object_or_404(DisplayGroup, pk=pk)
    
    if request.method == 'POST':
        form = DisplayGroupForm(request.POST, instance=group)
        if form.is_valid():
            try:
                group = form.save()
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f"Display group '{group.name}' updated successfully!"
                    response['HX-Alert-Type'] = 'success'
                    response['HX-Alert-Title'] = 'Updated!'
                    response['HX-Redirect'] = reverse('fees:display_group_detail', kwargs={'pk': group.pk})
                    return response
                else:
                    messages.success(
                        request,
                        f"Display group '{group.name}' updated successfully!",
                        extra_tags='sweetalert'
                    )
                    return redirect('fees:display_group_detail', pk=group.pk)
                    
            except Exception as e:
                logger.error(f"Error updating display group: {e}")
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Error updating group: {str(e)}'
                    response['HX-Alert-Type'] = 'error'
                    response['HX-Alert-Title'] = 'Error!'
                    return response
                else:
                    messages.error(request, f'Error updating group: {str(e)}')
    else:
        form = DisplayGroupForm(instance=group)
    
    context = {
        'form': form,
        'group': group,
        'title': f'Edit Display Group - {group.name}',
        'submit_text': 'Update Group',
    }
    
    return render(request, 'fees/display_groups/form.html', context)

@login_required
@require_http_methods(["POST"])
def display_group_delete(request, pk):
    """Delete display group with HTMX support"""
    group = get_object_or_404(DisplayGroup, pk=pk)
    
    # Check if group has categories
    if group.feescategory_set.exists():
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Cannot delete '{group.name}' because it has associated fee categories"
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Cannot Delete'
            response['HX-Close-Modal'] = 'true'
            return response
        else:
            messages.error(
                request,
                f"Cannot delete '{group.name}' because it has associated fee categories",
                extra_tags='sweetalert-error'
            )
            return redirect('fees:display_group_list')
    
    group_name = group.name
    group.delete()
    
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    if is_htmx:
        response = HttpResponse()
        response['HX-Alert-Message'] = f"Display group '{group_name}' deleted successfully"
        response['HX-Alert-Type'] = 'success'
        response['HX-Alert-Title'] = 'Deleted!'
        response['HX-Close-Modal'] = 'true'
        response['HX-Redirect'] = reverse('fees:display_group_list')
        return response
    else:
        messages.success(
            request,
            f"Display group '{group_name}' deleted successfully",
            extra_tags='sweetalert'
        )
        return redirect('fees:display_group_list')

@login_required
@require_http_methods(["POST"])
def display_group_toggle_active(request, pk):
    """Toggle display group active status"""
    group = get_object_or_404(DisplayGroup, pk=pk)
    
    try:
        with transaction.atomic():
            group.is_active = not group.is_active
            group.save()
        
        status = "activated" if group.is_active else "deactivated"
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Display group '{group.name}' {status}!"
            response['HX-Alert-Type'] = 'success'
            response['HX-Alert-Title'] = 'Status Updated'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('fees:display_group_detail', kwargs={'pk': group.pk})
            return response
        else:
            messages.success(request, f"Display group '{group.name}' {status}!")
            return redirect('fees:display_group_detail', pk=group.pk)
    
    except Exception as e:
        logger.error(f"Error toggling display group status: {e}", exc_info=True)
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f'Error updating status: {str(e)}'
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Error'
            return response
        else:
            messages.error(request, f'Error updating status: {str(e)}')
            return redirect('fees:display_group_detail', pk=pk)

@login_required
def display_group_list_print_view(request):
    """Generate printable display group list"""
    
    groups = DisplayGroup.objects.prefetch_related(
        'feescategory_set'
    ).order_by('display_order')
    
    context = {
        'groups': groups,
        'now': timezone.now(),
        'title': 'Display Groups',
    }
    
    return render(request, 'fees/display_groups/print_list.html', context)

# =============================================================================
# FEE CATEGORY VIEWS (CRUD + Print)
# =============================================================================

@login_required
def fee_category_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""
    filter_form = FeesCategoryFilterForm(request.GET or None)
    categories = get_filtered_fee_categories(request)
    
    # Calculate statistics
    stats = {
        'total': categories.count(),
        'active': categories.filter(is_active=True).count(),
        'mandatory': categories.filter(is_mandatory=True).count(),
        'optional': categories.filter(is_mandatory=False).count(),
        'refundable': categories.filter(is_refundable=True).count(),
        'taxable': categories.filter(is_taxable=True).count(),
        'recurring': categories.filter(is_recurring=True).count(),
        'tuition': categories.filter(category_type='TUITION').count(),
        'boarding': categories.filter(category_type='BOARDING').count(),
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
        return render(request, 'fees/categories/partials/_category_results.html', context)
    else:
        return render(request, 'fees/categories/list.html', context)

@login_required
def fee_category_create(request):
    """Create new fee category"""
    
    if request.method == 'POST':
        form = FeesCategoryForm(request.POST)
        if form.is_valid():
            try:
                category = form.save()
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f"Fee category '{category.name}' created successfully!"
                    response['HX-Alert-Type'] = 'success'
                    response['HX-Alert-Title'] = 'Created!'
                    response['HX-Redirect'] = reverse('fees:category_detail', kwargs={'pk': category.pk})
                    return response
                else:
                    messages.success(
                        request,
                        f"Fee category '{category.name}' created successfully!",
                        extra_tags='sweetalert'
                    )
                    return redirect('fees:category_detail', pk=category.pk)
                    
            except Exception as e:
                logger.error(f"Error creating category: {e}")
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Error creating category: {str(e)}'
                    response['HX-Alert-Type'] = 'error'
                    response['HX-Alert-Title'] = 'Error!'
                    return response
                else:
                    messages.error(request, f'Error creating category: {str(e)}')
    else:
        form = FeesCategoryForm()
    
    context = {
        'form': form,
        'title': 'Create Fee Category',
        'submit_text': 'Create Category',
    }
    
    return render(request, 'fees/categories/form.html', context)

@login_required
def fee_category_detail(request, pk):
    """View fee category details"""
    category = get_object_or_404(FeesCategory, pk=pk)
    
    # Get related fee structures through structure items
    structure_items = category.structure_items.select_related(
        'fee_structure',
        'fee_structure__academic_year'
    ).order_by('-fee_structure__created_at')[:10]
    
    # Get statistics
    total_structures = category.structure_items.values('fee_structure').distinct().count()
    
    context = {
        'category': category,
        'structure_items': structure_items,
        'total_structures': total_structures,
    }
    
    return render(request, 'fees/categories/detail.html', context)

@login_required
def fee_category_edit(request, pk):
    """Edit fee category"""
    category = get_object_or_404(FeesCategory, pk=pk)
    
    if request.method == 'POST':
        form = FeesCategoryForm(request.POST, instance=category)
        if form.is_valid():
            try:
                category = form.save()
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f"Fee category '{category.name}' updated successfully!"
                    response['HX-Alert-Type'] = 'success'
                    response['HX-Alert-Title'] = 'Updated!'
                    response['HX-Redirect'] = reverse('fees:category_detail', kwargs={'pk': category.pk})
                    return response
                else:
                    messages.success(
                        request,
                        f"Fee category '{category.name}' updated successfully!",
                        extra_tags='sweetalert'
                    )
                    return redirect('fees:category_detail', pk=category.pk)
                    
            except Exception as e:
                logger.error(f"Error updating category: {e}")
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Error updating category: {str(e)}'
                    response['HX-Alert-Type'] = 'error'
                    response['HX-Alert-Title'] = 'Error!'
                    return response
                else:
                    messages.error(request, f'Error updating category: {str(e)}')
    else:
        form = FeesCategoryForm(instance=category)
    
    context = {
        'form': form,
        'category': category,
        'title': f'Edit Category - {category.name}',
        'submit_text': 'Update Category',
    }
    
    return render(request, 'fees/categories/form.html', context)

@login_required
@require_http_methods(["POST"])
def fee_category_delete(request, pk):
    """Delete fee category with HTMX support"""
    category = get_object_or_404(FeesCategory, pk=pk)
    
    # Check if category is used in structures or invoices
    if category.structure_items.exists() or category.invoice_items.exists():
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Cannot delete '{category.name}' because it's used in fee structures or invoices"
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Cannot Delete'
            response['HX-Close-Modal'] = 'true'
            return response
        else:
            messages.error(
                request,
                f"Cannot delete '{category.name}' because it's used in fee structures or invoices",
                extra_tags='sweetalert-error'
            )
            return redirect('fees:category_list')
    
    category_name = category.name
    category.delete()
    
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    if is_htmx:
        response = HttpResponse()
        response['HX-Alert-Message'] = f"Fee category '{category_name}' deleted successfully"
        response['HX-Alert-Type'] = 'success'
        response['HX-Alert-Title'] = 'Deleted!'
        response['HX-Close-Modal'] = 'true'
        response['HX-Redirect'] = reverse('fees:category_list')
        return response
    else:
        messages.success(
            request,
            f"Fee category '{category_name}' deleted successfully",
            extra_tags='sweetalert'
        )
        return redirect('fees:category_list')
    
@login_required
@require_http_methods(["POST"])
def fee_category_toggle_active(request, pk):
    """Toggle fee category active status"""
    category = get_object_or_404(FeesCategory, pk=pk)
    
    try:
        with transaction.atomic():
            category.is_active = not category.is_active
            category.save()
        
        status = "activated" if category.is_active else "deactivated"
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Fee category '{category.name}' {status}!"
            response['HX-Alert-Type'] = 'success'
            response['HX-Alert-Title'] = 'Status Updated'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('fees:category_detail', kwargs={'pk': category.pk})
            return response
        else:
            messages.success(request, f"Fee category '{category.name}' {status}!")
            return redirect('fees:category_detail', pk=category.pk)
    
    except Exception as e:
        logger.error(f"Error toggling category status: {e}", exc_info=True)
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f'Error updating status: {str(e)}'
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Error'
            return response
        else:
            messages.error(request, f'Error updating status: {str(e)}')
            return redirect('fees:category_detail', pk=pk)

@login_required
def fee_category_list_print_view(request):
    """Generate printable fee category list"""
    
    categories = FeesCategory.objects.select_related(
        'display_group'
    ).order_by('display_order', 'name')
    
    context = {
        'categories': categories,
        'now': timezone.now(),
        'title': 'Fee Categories',
    }
    
    return render(request, 'fees/categories/print_list.html', context)


# =============================================================================
# FEE STRUCTURE VIEWS (CRUD + Print + Clone + HTMX Search)
# =============================================================================

@login_required
def fee_structure_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""
    filter_form = FeesStructureFilterForm(request.GET or None)
    structures = get_filtered_fee_structures(request)
    
    # Calculate statistics
    stats = {
        'total': structures.count(),
        'active': structures.filter(is_active=True).count(),
        'standard': structures.filter(structure_type='STANDARD').count(),
        'with_late_fees': structures.filter(charges_late_fee=True).count(),
    }
    
    # Pagination
    paginator = Paginator(structures, 25)
    page_number = request.GET.get('page', 1)
    structures_page = paginator.get_page(page_number)
    
    # Detect HTMX request
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'structures_page': structures_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    # Return appropriate template
    if is_htmx:
        return render(request, 'fees/structures/partials/_structure_results.html', context)
    else:
        return render(request, 'fees/structures/list.html', context)

class FeeStructureCreateWizard(SessionWizardView):
    """
    Multi-step wizard for creating fee structures.
    
    Conditional Steps:
    - billing_schedule: Only shown if billing_frequency = 'SPLIT_CUSTOM'
    """
    
    form_list = FEE_STRUCTURE_WIZARD_FORMS
    template_name = 'fees/structures/wizard.html'
    
    def get_template_names(self):
        """Return template for all steps"""
        return [self.template_name]
    
    # -------------------------------------------------------------------------
    # CONDITIONAL STEP LOGIC
    # -------------------------------------------------------------------------
    
    def show_billing_schedule_form(self):
        """
        Only show billing schedule formset if billing_frequency = 'SPLIT_CUSTOM'.
        
        For 'ONCE' or 'PER_PERIOD', we auto-create the billing splits in done().
        """
        basic_data = self.get_cleaned_data_for_step('basic_info') or {}
        billing_frequency = basic_data.get('billing_frequency', 'ONCE')
        return billing_frequency == 'SPLIT_CUSTOM'
    
    condition_dict = {
        'billing_schedule': show_billing_schedule_form
    }
    
    # -------------------------------------------------------------------------
    # CONTEXT DATA
    # -------------------------------------------------------------------------
    
    def get_context_data(self, form, **kwargs):
        """Add step names, progress, and review data"""
        context = super().get_context_data(form=form, **kwargs)
        
        # Progress tracking
        total_steps = len(self.get_form_list())
        current_step_index = list(self.get_form_list().keys()).index(self.steps.current)
        
        context.update({
            'step_names': FEE_STRUCTURE_STEP_NAMES,
            'current_step_name': FEE_STRUCTURE_STEP_NAMES.get(
                self.steps.current, 'Step'
            ),
            'progress_percentage': (
                ((current_step_index) / (total_steps - 1)) * 100 
                if total_steps > 1 else 100
            ),
        })
        
        # Review data for confirmation step
        if self.steps.current == 'confirmation':
            context['basic_data'] = self.get_cleaned_data_for_step('basic_info')
            
            # ✅ FIXED: Only get billing_schedule if it was shown (conditional step)
            if 'billing_schedule' in self.get_form_list():
                try:
                    billing_formset = self.get_form(
                        step='billing_schedule',
                        data=self.storage.get_step_data('billing_schedule'),
                        files=self.storage.get_step_files('billing_schedule')
                    )
                    if billing_formset and hasattr(billing_formset, 'cleaned_data'):
                        context['billing_data'] = billing_formset.cleaned_data
                    else:
                        context['billing_data'] = None
                except KeyError:
                    # Step was skipped, no data
                    context['billing_data'] = None
            else:
                # Billing schedule step was skipped (not SPLIT_CUSTOM)
                context['billing_data'] = None
            
            # Get fee items formset
            items_formset = self.get_form(
                step='fee_items',
                data=self.storage.get_step_data('fee_items'),
                files=self.storage.get_step_files('fee_items')
            )
            if items_formset and hasattr(items_formset, 'cleaned_data'):
                context['items_data'] = items_formset.cleaned_data
            else:
                context['items_data'] = []
            
            # Calculate totals for review
            items_data = context['items_data'] or []
            if items_data:
                total_amount = sum(
                    item.get('amount', Decimal('0.00')) 
                    for item in items_data 
                    if not item.get('DELETE', False)
                )
                context['total_amount'] = total_amount
        
        return context
    
    def get_form_kwargs(self, step=None):
        """Pass additional kwargs to forms"""
        kwargs = super().get_form_kwargs(step)
        
        # For billing schedule formset, pass academic year from basic_info
        if step == 'billing_schedule':
            basic_data = self.get_cleaned_data_for_step('basic_info')
            if basic_data:
                kwargs['academic_year'] = basic_data.get('academic_year')
        
        return kwargs
    
    # -------------------------------------------------------------------------
    # ✅ NEW: FORMSET HANDLING METHODS
    # -------------------------------------------------------------------------
    
    def get_formset_data(self, step_name):
        """
        Get cleaned data from a formset step.
        
        Returns list of dicts for each form in the formset.
        """
        try:
            formset = self.get_form(
                step=step_name,
                data=self.storage.get_step_data(step_name),
                files=self.storage.get_step_files(step_name)
            )
            
            if formset and hasattr(formset, 'cleaned_data'):
                # Return list of form data, excluding deleted items
                return [
                    form_data for form_data in formset.cleaned_data
                    if form_data and not form_data.get('DELETE', False)
                ]
            
            return []
            
        except Exception as e:
            logger.error(f"Error getting formset data for {step_name}: {e}")
            return []
    
    # -------------------------------------------------------------------------
    # FORM PROCESSING
    # -------------------------------------------------------------------------
    
    @transaction.atomic
    def done(self, form_list, **kwargs):
        """
        Save all wizard data and create fee structure.
        
        Process:
        1. Create FeesStructure from basic_info
        2. Create billing splits (auto or custom)
        3. Create fee structure items
        4. Success message and redirect
        """
        
        logger.info("=" * 80)
        logger.info("FEE STRUCTURE WIZARD - Creating Structure")
        logger.info("=" * 80)
        
        try:
            # Get cleaned data from all steps
            basic_data = self.get_cleaned_data_for_step('basic_info')
            
            # ✅ FIXED: Get formset data properly
            billing_data = self.get_formset_data('billing_schedule')
            items_data = self.get_formset_data('fee_items')
            
            confirmation_data = self.get_cleaned_data_for_step('confirmation')
            
            logger.info(f"Basic data: {basic_data.get('name') if basic_data else 'None'}")
            logger.info(f"Billing data items: {len(billing_data)}")
            logger.info(f"Fee items: {len(items_data)}")
            
            # ------------------------------------------------------------------
            # STEP 1: Create Fee Structure
            # ------------------------------------------------------------------
            structure = FeesStructure.objects.create(
                name=basic_data['name'],
                description=basic_data.get('description', ''),
                structure_type=basic_data['structure_type'],
                academic_year=basic_data['academic_year'],
                billing_frequency=basic_data['billing_frequency'],
                boarding_type_filter=basic_data['boarding_type_filter'],
                student_type_filter=basic_data['student_type_filter'],
                payment_terms_days=basic_data['payment_terms_days'],
                charges_late_fee=basic_data.get('charges_late_fee', False),
                late_fee_amount=basic_data.get('late_fee_amount', Decimal('0.00')),
                late_fee_percentage=basic_data.get('late_fee_percentage', Decimal('0.00')),
                grace_period_days=basic_data.get('grace_period_days', 7),
                priority=basic_data.get('priority', 100),
                is_active=basic_data.get('is_active', True),
                effective_date=basic_data['effective_date'],
                expiry_date=basic_data.get('expiry_date'),
            )
            
            # Add M2M relationships
            structure.applicable_sessions.set(basic_data['applicable_sessions'])
            structure.academic_levels.set(basic_data['academic_levels'])
            
            if basic_data.get('applicable_classes'):
                structure.applicable_classes.set(basic_data['applicable_classes'])
            
            logger.info(f"✓ Created fee structure: {structure.name}")
            
            # ------------------------------------------------------------------
            # STEP 2: Create Billing Splits
            # ------------------------------------------------------------------
            billing_frequency = basic_data['billing_frequency']
            
            if billing_frequency == 'SPLIT_CUSTOM':
                # Custom splits from formset
                if billing_data:
                    for split_data in billing_data:
                        FeesStructureBillingSplit.objects.create(
                            fee_structure=structure,
                            fiscal_period=split_data['fiscal_period'],
                            percentage=split_data['percentage'],
                            sequence=split_data.get('sequence', 1),
                            description=split_data.get('description', '')
                        )
                    logger.info(f"✓ Created {len(billing_data)} custom billing splits")
                else:
                    logger.warning("⚠️  SPLIT_CUSTOM selected but no billing data!")
            
            elif billing_frequency == 'ONCE':
                # Auto-create single billing split for first fiscal period
                first_period = structure.academic_year.fiscal_periods.filter(
                    is_active=True,
                    is_closed=False
                ).order_by('period_number').first()
                
                if first_period:
                    FeesStructureBillingSplit.objects.create(
                        fee_structure=structure,
                        fiscal_period=first_period,
                        percentage=Decimal('100.00'),
                        sequence=1,
                        description="Full Payment"
                    )
                    logger.info(f"✓ Auto-created single billing split: {first_period}")
                else:
                    logger.warning("⚠️  No active fiscal periods found for ONCE billing!")
            
            elif billing_frequency == 'PER_PERIOD':
                # Auto-create equal splits for all fiscal periods
                periods = structure.academic_year.fiscal_periods.filter(
                    is_active=True,
                    is_closed=False
                ).order_by('period_number')
                
                count = periods.count()
                if count > 0:
                    percentage = Decimal('100.00') / count
                    
                    for idx, period in enumerate(periods, 1):
                        FeesStructureBillingSplit.objects.create(
                            fee_structure=structure,
                            fiscal_period=period,
                            percentage=percentage,
                            sequence=idx,
                            description=f"Installment {idx} of {count}"
                        )
                    logger.info(f"✓ Auto-created {count} equal billing splits")
                else:
                    logger.warning("⚠️  No active fiscal periods found for PER_PERIOD billing!")
            
            # ------------------------------------------------------------------
            # STEP 3: Create Fee Items
            # ------------------------------------------------------------------
            if items_data:
                created_count = 0
                for item_data in items_data:
                    FeesStructureItem.objects.create(
                        fee_structure=structure,
                        fee_category=item_data['fee_category'],
                        amount=item_data['amount'],
                        use_variable_amount=item_data.get('use_variable_amount', False),
                        is_taxable=item_data.get('is_taxable', False),
                        tax_percentage=item_data.get('tax_percentage', Decimal('0.00')),
                        default_discount_percentage=item_data.get(
                            'default_discount_percentage', Decimal('0.00')
                        ),
                        scholarship_eligible=item_data.get('scholarship_eligible', True),
                        max_scholarship_discount=item_data.get('max_scholarship_discount'),
                        is_mandatory=item_data.get('is_mandatory', True),
                        is_conditional=item_data.get('is_conditional', False),
                        print_on_invoice=item_data.get('print_on_invoice', True),
                        display_order=item_data.get('display_order', 1),
                    )
                    created_count += 1
                logger.info(f"✓ Created {created_count} fee items")
            else:
                logger.warning("⚠️  No fee items created!")
            
            # ------------------------------------------------------------------
            # SUCCESS
            # ------------------------------------------------------------------
            total_amount = structure.get_total_amount()
            
            messages.success(
                self.request,
                f'Fee structure "{structure.name}" created successfully! '
                f'Total amount: UGX {total_amount:,.2f}',
                extra_tags='sweetalert'
            )
            
            logger.info("=" * 80)
            logger.info(f"✅ SUCCESS: Fee structure {structure.pk} created")
            logger.info(f"   Name: {structure.name}")
            logger.info(f"   Total Amount: UGX {total_amount:,.2f}")
            logger.info(f"   Fee Items: {structure.items.count()}")
            logger.info(f"   Billing Splits: {structure.billing_splits.count()}")
            logger.info("=" * 80)
            
            return redirect('fees:structure_detail', pk=structure.pk)
        
        except Exception as exc:
            logger.exception("❌ ERROR in fee structure wizard:")
            logger.exception(exc)
            
            messages.error(
                self.request,
                f"Error creating fee structure: {exc}",
                extra_tags='sweetalert-error'
            )
            return redirect('fees:structure_list')


# View entry point
fee_structure_create = FeeStructureCreateWizard.as_view()

@login_required
def fee_structure_detail(request, pk):
    """View fee structure details"""
    structure = get_object_or_404(
        FeesStructure.objects.prefetch_related(
            'academic_levels',
            'applicable_sessions',
            'applicable_classes__academic_level',
            'items__fee_category__display_group'
        ),
        pk=pk
    )
    
    # Get structure items ordered by display group and category
    items = structure.items.select_related(
        'fee_category__display_group'
    ).order_by(
        'fee_category__display_group__display_order',
        'fee_category__display_order'
    )
    
    # Calculate totals
    total_amount = sum(item.amount for item in items)
    total_tax = sum((item.amount * item.tax_percentage / 100) for item in items)
    total_with_tax = total_amount + total_tax
    
    # Get invoices using this structure
    invoices = structure.invoices.select_related(
        'student', 'academic_session'
    ).prefetch_related('items__fee_category').order_by('-issue_date')[:10]
    
    # Get usage statistics
    invoice_count = structure.invoices.count()
    active_invoice_count = structure.invoices.filter(status='UNPAID').count()
    
    context = {
        'structure': structure,
        'items': items,
        'total_amount': total_amount,
        'total_tax': total_tax,
        'total_with_tax': total_with_tax,
        'invoices': invoices,
        'invoice_count': invoice_count,
        'active_invoice_count': active_invoice_count,
    }
    
    return render(request, 'fees/structures/detail.html', context)


@login_required
def fee_structure_edit(request, pk):
    """Edit fee structure"""
    structure = get_object_or_404(
        FeesStructure.objects.prefetch_related(
            'academic_levels', 'applicable_sessions', 'applicable_classes'
        ),
        pk=pk
    )
    
    if request.method == 'POST':
        form = FeesStructureForm(request.POST, instance=structure)
        if form.is_valid():
            try:
                structure = form.save()
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f"Fee structure '{structure.name}' updated successfully!"
                    response['HX-Alert-Type'] = 'success'
                    response['HX-Alert-Title'] = 'Updated!'
                    response['HX-Redirect'] = reverse('fees:structure_detail', kwargs={'pk': structure.pk})
                    return response
                else:
                    messages.success(
                        request,
                        f"Fee structure '{structure.name}' updated successfully!",
                        extra_tags='sweetalert'
                    )
                    return redirect('fees:structure_detail', pk=structure.pk)
                    
            except Exception as e:
                logger.error(f"Error updating structure: {e}")
                
                is_htmx = request.headers.get('HX-Request') == 'true'
                
                if is_htmx:
                    response = HttpResponse()
                    response['HX-Alert-Message'] = f'Error updating structure: {str(e)}'
                    response['HX-Alert-Type'] = 'error'
                    response['HX-Alert-Title'] = 'Error!'
                    return response
                else:
                    messages.error(request, f'Error updating structure: {str(e)}')
    else:
        form = FeesStructureForm(instance=structure)
    
    # Get existing items for display
    items = structure.items.select_related(
        'fee_category__display_group'
    ).order_by(
        'fee_category__display_group__display_order',
        'fee_category__display_order'
    )
    
    context = {
        'form': form,
        'structure': structure,
        'items': items,
        'title': f'Edit Structure - {structure.name}',
    }
    
    return render(request, 'fees/structures/form.html', context)

@login_required
def fee_structure_clone(request, pk):
    """Clone existing fee structure"""
    
    original_structure = get_object_or_404(
        FeesStructure.objects.prefetch_related(
            'academic_levels',
            'applicable_classes',
            'applicable_sessions',
            'items__fee_category'
        ),
        pk=pk
    )
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Clone the structure
                new_structure = FeesStructure.objects.get(pk=original_structure.pk)
                new_structure.pk = None
                new_structure._state.adding = True  # Ensure Django treats it as new
                new_structure.name = f"{original_structure.name} (Copy)"
                new_structure.is_active = False  # Deactivate by default
                new_structure.save()
                
                # Clone M2M relationships
                new_structure.academic_levels.set(
                    original_structure.academic_levels.all()
                )
                new_structure.applicable_classes.set(
                    original_structure.applicable_classes.all()
                )
                new_structure.applicable_sessions.set(
                    original_structure.applicable_sessions.all()
                )
                
                # Clone items
                for item in original_structure.items.all():
                    FeesStructureItem.objects.create(
                        fee_structure=new_structure,
                        fee_category=item.fee_category,
                        amount=item.amount,
                        tax_percentage=item.tax_percentage,
                        discount_percentage=item.discount_percentage,
                        scholarship_eligible=item.scholarship_eligible,
                        max_scholarship_discount=item.max_scholarship_discount,
                        is_conditional=item.is_conditional,
                        condition_description=item.condition_description,
                        condition_criteria=item.condition_criteria,
                        is_payable_in_installments=item.is_payable_in_installments,
                        number_of_installments=item.number_of_installments,
                    )
            
            messages.success(
                request,
                f'Fee structure cloned successfully as "{new_structure.name}"! '
                f'The cloned structure is inactive by default. Edit and activate when ready.'
            )
            
            # Redirect to edit page with cloned flag
            return redirect(f"{reverse('fees:structure_edit', kwargs={'pk': new_structure.pk})}?cloned=1")
            
        except Exception as e:
            logger.error(f"Error cloning structure: {e}", exc_info=True)
            messages.error(request, f'Error cloning structure: {str(e)}')
            return redirect('fees:structure_detail', pk=pk)
    
    context = {
        'original_structure': original_structure,
        'items': original_structure.items.select_related(
            'fee_category__display_group'
        ).order_by(
            'fee_category__display_group__display_order',
            'fee_category__display_order'
        ),
        'title': f'Clone Structure - {original_structure.name}',
    }
    
    return render(request, 'fees/structures/clone.html', context)

@login_required
@require_http_methods(["POST"])
def fee_structure_activate(request, pk):
    """Activate fee structure"""
    structure = get_object_or_404(FeesStructure, pk=pk)
    
    # Validate can be activated
    if not structure.items.exists():
        messages.error(request, 'Cannot activate structure with no fee items.')
        return redirect('fees:structure_detail', pk=pk)
    
    if not structure.academic_levels.exists():
        messages.error(request, 'Cannot activate structure with no academic levels assigned.')
        return redirect('fees:structure_detail', pk=pk)
    
    if not structure.applicable_sessions.exists():
        messages.error(request, 'Cannot activate structure with no academic sessions assigned.')
        return redirect('fees:structure_detail', pk=pk)
    
    try:
        with transaction.atomic():
            structure.is_active = True
            structure.save()
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Fee structure '{structure.name}' activated!"
            response['HX-Alert-Type'] = 'success'
            response['HX-Alert-Title'] = 'Structure Activated'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('fees:structure_detail', kwargs={'pk': structure.pk})
            return response
        else:
            messages.success(request, f"Fee structure '{structure.name}' activated!")
            return redirect('fees:structure_detail', pk=structure.pk)
    
    except Exception as e:
        logger.error(f"Error activating fee structure: {e}", exc_info=True)
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f'Error activating structure: {str(e)}'
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Error'
            return response
        else:
            messages.error(request, f'Error activating structure: {str(e)}')
            return redirect('fees:structure_detail', pk=pk)


@login_required
@require_http_methods(["POST"])
def fee_structure_deactivate(request, pk):
    """Deactivate fee structure"""
    structure = get_object_or_404(FeesStructure, pk=pk)
    
    try:
        deactivation_reason = request.POST.get('deactivation_reason', '')
        
        with transaction.atomic():
            structure.is_active = False
            if deactivation_reason:
                structure.description = f"{structure.description}\n\nDeactivated: {deactivation_reason}".strip()
            structure.save()
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f"Fee structure '{structure.name}' deactivated!"
            response['HX-Alert-Type'] = 'success'
            response['HX-Alert-Title'] = 'Structure Deactivated'
            response['HX-Close-Modal'] = 'true'
            response['HX-Redirect'] = reverse('fees:structure_detail', kwargs={'pk': structure.pk})
            return response
        else:
            messages.success(request, f"Fee structure '{structure.name}' deactivated!")
            return redirect('fees:structure_detail', pk=structure.pk)
    
    except Exception as e:
        logger.error(f"Error deactivating fee structure: {e}", exc_info=True)
        
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if is_htmx:
            response = HttpResponse()
            response['HX-Alert-Message'] = f'Error deactivating structure: {str(e)}'
            response['HX-Alert-Type'] = 'error'
            response['HX-Alert-Title'] = 'Error'
            return response
        else:
            messages.error(request, f'Error deactivating structure: {str(e)}')
            return redirect('fees:structure_detail', pk=pk)

@login_required
def fee_structure_delete(request, pk):
    """Delete fee structure (soft delete recommended)"""
    
    structure = get_object_or_404(FeesStructure, pk=pk)
    
    if request.method == 'POST':
        try:
            # Check if structure is in use
            invoice_count = structure.invoices.count()
            
            if invoice_count > 0:
                messages.warning(
                    request,
                    f'Cannot delete "{structure.name}" - it has {invoice_count} associated invoice(s). '
                    f'Consider deactivating it instead.'
                )
                return redirect('fees:structure_detail', pk=pk)
            
            with transaction.atomic():
                structure_name = structure.name
                structure.delete()
            
            messages.success(
                request,
                f'Fee structure "{structure_name}" deleted successfully!'
            )
            return redirect('fees:structure_list')
            
        except Exception as e:
            logger.error(f"Error deleting structure: {e}", exc_info=True)
            messages.error(request, f'Error deleting structure: {str(e)}')
            return redirect('fees:structure_detail', pk=pk)
    
    # Check usage
    invoice_count = structure.invoices.count()
    
    context = {
        'structure': structure,
        'invoice_count': invoice_count,
        'can_delete': invoice_count == 0,
    }
    
    return render(request, 'fees/structures/delete_confirm.html', context)


@login_required
def fee_structure_list_print_view(request):
    """Generate printable fee structure list"""
    
    # Apply same filters as main list
    filter_form = FeesStructureFilterForm(request.GET)
    
    structures = FeesStructure.objects.prefetch_related(
        'academic_levels',
        'applicable_sessions',
        'items__fee_category__display_group'
    )
    
    if filter_form.is_valid():
        # Apply filters (same as search view)
        q = filter_form.cleaned_data.get('q')
        if q:
            structures = structures.filter(
                Q(name__icontains=q) | Q(description__icontains=q)
            )
        
        structure_type = filter_form.cleaned_data.get('structure_type')
        if structure_type:
            structures = structures.filter(structure_type=structure_type)
        
        is_active = filter_form.cleaned_data.get('is_active')
        if is_active is not None:
            structures = structures.filter(is_active=is_active)
    
    structures = structures.order_by('structure_type', 'priority', 'name')
    
    context = {
        'structures': structures,
        'now': timezone.now(),
        'title': 'Fee Structures',
        'filters_applied': filter_form.is_valid() and any(filter_form.cleaned_data.values()),
    }
    
    return render(request, 'fees/structures/print_list.html', context)


@login_required
def fee_structure_print_view(request, pk):
    """Generate printable fee structure detail"""
    structure = get_object_or_404(
        FeesStructure.objects.prefetch_related(
            'academic_levels',
            'applicable_sessions',
            'applicable_classes__academic_level',
            'items__fee_category__display_group'
        ),
        pk=pk
    )
    
    # Get items grouped by display group
    items = structure.items.select_related(
        'fee_category__display_group'
    ).order_by(
        'fee_category__display_group__display_order',
        'fee_category__display_order'
    )
    
    # Calculate totals
    total_amount = sum(item.amount for item in items)
    
    context = {
        'structure': structure,
        'items': items,
        'total_amount': total_amount,
        'now': timezone.now(),
    }
    
    return render(request, 'fees/structures/print_detail.html', context)

# =============================================================================
# REPORTS
# =============================================================================

@login_required
def fee_collection_report(request):
    """Fee collection report with comprehensive analytics"""
    
    # Get filter parameters
    session_id = request.GET.get('session')
    period_id = request.GET.get('period')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    # Build filters for stats
    filters = {}
    if session_id:
        filters['academic_session'] = session_id
    if period_id:
        filters['fiscal_period'] = period_id
    if date_from:
        filters['date_from'] = date_from
    if date_to:
        filters['date_to'] = date_to
    
    # Get comprehensive statistics
    try:
        invoice_stats = fees_stats.get_invoice_statistics(filters)
        payment_stats = fees_stats.get_payment_statistics(filters)
        account_stats = fees_stats.get_student_account_statistics()
    except Exception as e:
        logger.error(f"Error getting report statistics: {e}")
        invoice_stats = {}
        payment_stats = {}
        account_stats = {}
    
    context = {
        'invoice_stats': invoice_stats,
        'payment_stats': payment_stats,
        'account_stats': account_stats,
        'session_id': session_id,
        'period_id': period_id,
        'date_from': date_from,
        'date_to': date_to,
    }
    
    return render(request, 'fees/reports/collection_report.html', context)


@login_required
def outstanding_fees_report(request):
    """Outstanding fees report with aging analysis"""
    
    # Get filter parameters
    session_id = request.GET.get('session')
    level_id = request.GET.get('level')
    
    # Build queryset for overdue invoices (uses school timezone) ⭐
    today = get_school_today()
    
    overdue_invoices = FeeInvoice.objects.filter(
        due_date__lt=today,
        status__in=['PENDING', 'PARTIALLY_PAID', 'OVERDUE']
    ).select_related('student', 'academic_session')
    
    if session_id:
        overdue_invoices = overdue_invoices.filter(academic_session_id=session_id)
    
    if level_id:
        overdue_invoices = overdue_invoices.filter(
            student__current_academic_level_id=level_id
        )
    
    # Get statistics
    try:
        invoice_stats = fees_stats.get_invoice_statistics({'is_overdue': True})
    except Exception as e:
        logger.error(f"Error getting outstanding statistics: {e}")
        invoice_stats = {}
    
    context = {
        'overdue_invoices': overdue_invoices[:100],
        'invoice_stats': invoice_stats,
        'session_id': session_id,
        'level_id': level_id,
    }
    
    return render(request, 'fees/reports/outstanding_report.html', context)


@login_required
def scholarship_report(request):
    """Comprehensive scholarship report"""
    
    # Get filter parameters
    program_id = request.GET.get('program')
    session_id = request.GET.get('session')
    
    # Build filters
    filters = {}
    if program_id:
        filters['program_id'] = program_id
    if session_id:
        filters['academic_session'] = session_id
    
    # Get statistics
    try:
        scholarship_stats = fees_stats.get_scholarship_statistics(filters)
    except Exception as e:
        logger.error(f"Error getting scholarship statistics: {e}")
        scholarship_stats = {}
    
    context = {
        'scholarship_stats': scholarship_stats,
        'program_id': program_id,
        'session_id': session_id,
    }
    
    return render(request, 'fees/reports/scholarship_report.html', context)


@login_required
def discount_report(request):
    """Comprehensive discount report"""
    
    # Get filter parameters
    session_id = request.GET.get('session')
    
    # Build filters
    filters = {}
    if session_id:
        filters['academic_session'] = session_id
    
    # Get statistics
    try:
        discount_stats = fees_stats.get_discount_statistics(filters)
    except Exception as e:
        logger.error(f"Error getting discount statistics: {e}")
        discount_stats = {}
    
    context = {
        'discount_stats': discount_stats,
        'session_id': session_id,
    }
    
    return render(request, 'fees/reports/discount_report.html', context)


@login_required
def student_account_report(request, pk):
    """Detailed student account report"""
    
    account = get_object_or_404(
        StudentAccount.objects.select_related('student'),
        pk=pk
    )
    
    # Get date range filters
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    # Build transaction queryset
    transactions = account.transactions.select_related(
        'invoice', 'payment', 'academic_session'
    ).order_by('transaction_date')
    
    if date_from:
        transactions = transactions.filter(transaction_date__gte=date_from)
    if date_to:
        transactions = transactions.filter(transaction_date__lte=date_to)
    
    # Get invoices
    invoices = FeeInvoice.objects.filter(
        student=account.student
    ).select_related('academic_session')
    
    if date_from:
        invoices = invoices.filter(issue_date__gte=date_from)
    if date_to:
        invoices = invoices.filter(issue_date__lte=date_to)
    
    # Get payments
    payments = Payment.objects.filter(
        student=account.student
    ).select_related('payment_method')
    
    if date_from:
        payments = payments.filter(payment_date__gte=date_from)
    if date_to:
        payments = payments.filter(payment_date__lte=date_to)
    
    # Calculate summary
    summary = {
        'total_invoiced': invoices.aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0.00'),
        'total_paid': payments.filter(status='COMPLETED').aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00'),
        'total_outstanding': invoices.aggregate(Sum('balance'))['balance__sum'] or Decimal('0.00'),
        'current_balance': account.current_balance,
    }
    
    context = {
        'account': account,
        'transactions': transactions,
        'invoices': invoices,
        'payments': payments,
        'summary': summary,
        'date_from': date_from,
        'date_to': date_to,
    }
    
    return render(request, 'fees/reports/student_account_report.html', context)


@login_required
def aging_report(request):
    """Aging analysis report for outstanding invoices"""
    
    # Uses school timezone ⭐
    today = get_school_today()
    
    # Define aging buckets
    aging_data = {
        'current': {
            'label': 'Current (Not Due)',
            'invoices': FeeInvoice.objects.filter(
                due_date__gte=today,
                status__in=['PENDING', 'PARTIALLY_PAID']
            )
        },
        '1_30': {
            'label': '1-30 Days Overdue',
            'invoices': FeeInvoice.objects.filter(
                due_date__lt=today,
                due_date__gte=today - timedelta(days=30),
                status__in=['PENDING', 'PARTIALLY_PAID', 'OVERDUE']
            )
        },
        '31_60': {
            'label': '31-60 Days Overdue',
            'invoices': FeeInvoice.objects.filter(
                due_date__lt=today - timedelta(days=30),
                due_date__gte=today - timedelta(days=60),
                status__in=['PENDING', 'PARTIALLY_PAID', 'OVERDUE']
            )
        },
        '61_90': {
            'label': '61-90 Days Overdue',
            'invoices': FeeInvoice.objects.filter(
                due_date__lt=today - timedelta(days=60),
                due_date__gte=today - timedelta(days=90),
                status__in=['PENDING', 'PARTIALLY_PAID', 'OVERDUE']
            )
        },
        'over_90': {
            'label': 'Over 90 Days Overdue',
            'invoices': FeeInvoice.objects.filter(
                due_date__lt=today - timedelta(days=90),
                status__in=['PENDING', 'PARTIALLY_PAID', 'OVERDUE']
            )
        }
    }
    
    # Calculate totals for each bucket
    for key, data in aging_data.items():
        data['count'] = data['invoices'].count()
        data['total'] = data['invoices'].aggregate(Sum('balance'))['balance__sum'] or Decimal('0.00')
    
    context = {
        'aging_data': aging_data,
        'today': today,
    }
    
    return render(request, 'fees/reports/aging_report.html', context)


@login_required
def payment_methods_report(request):
    """Payment methods analysis report"""
    
    # Get date range filters
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    # Build queryset
    payments = Payment.objects.filter(status='COMPLETED')
    
    if date_from:
        payments = payments.filter(payment_date__gte=date_from)
    if date_to:
        payments = payments.filter(payment_date__lte=date_to)
    
    # Group by payment method
    method_stats = payments.values(
        'payment_method__name',
        'payment_method__method_type'
    ).annotate(
        count=Count('id'),
        total_amount=Sum('amount'),
        avg_amount=Avg('amount')
    ).order_by('-total_amount')
    
    # Calculate grand totals
    grand_total = payments.aggregate(
        total_count=Count('id'),
        total_amount=Sum('amount'),
        avg_amount=Avg('amount')
    )
    
    context = {
        'method_stats': method_stats,
        'grand_total': grand_total,
        'date_from': date_from,
        'date_to': date_to,
    }
    
    return render(request, 'fees/reports/payment_methods_report.html', context)

# =============================================================================
# EXPORT FUNCTIONS
# =============================================================================

@login_required
def export_invoices_excel(request):
    """Export invoices to Excel with filters applied"""
    invoices = get_filtered_fee_invoices(request)
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Fee Invoices"
    
    # Define styles
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_alignment = Alignment(horizontal="center", vertical="center")
    
    # Headers
    headers = [
        '#', 'Invoice Number', 'Student', 'Session', 'Issue Date',
        'Due Date', 'Total Amount', 'Paid Amount', 'Balance', 'Status'
    ]
    ws.append(headers)
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
    
    # Data rows
    for idx, invoice in enumerate(invoices, start=1):
        ws.append([
            idx,
            invoice.invoice_number,
            invoice.student.get_full_name(),
            invoice.academic_session.name if invoice.academic_session else 'N/A',
            invoice.issue_date.strftime('%Y-%m-%d'),
            invoice.due_date.strftime('%Y-%m-%d'),
            float(invoice.total_amount),
            float(invoice.paid_amount),
            float(invoice.balance),
            invoice.get_status_display(),
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
    filename = f"invoices_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response

@login_required
def export_student_accounts_excel(request):
    """Export student accounts to Excel with filters applied"""
    accounts = get_filtered_student_accounts(request)
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Student Accounts"
    
    # Define styles
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_alignment = Alignment(horizontal="center", vertical="center")
    
    # Headers
    headers = [
        '#', 'Student ID', 'Student Name', 'Current Balance', 
        'Total Charges', 'Total Payments', 'Outstanding Amount',
        'Credit Limit', 'Status', 'Last Transaction'
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
            account.student.admission_number,
            account.student.get_full_name(),
            float(account.get_current_balance()),
            float(account.get_total_charges()),
            float(account.get_total_payments()),
            float(account.get_outstanding_amount()),
            float(account.credit_limit) if account.credit_limit else 0,
            account.get_status_display(),
            account.last_transaction_date.strftime('%Y-%m-%d') if account.last_transaction_date else 'N/A',
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
    filename = f"student_accounts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


@login_required
def export_account_transactions_excel(request):
    """Export account transactions to Excel with filters applied"""
    transactions = get_filtered_account_transactions(request)
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Account Transactions"
    
    # Define styles
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_alignment = Alignment(horizontal="center", vertical="center")
    
    # Headers
    headers = [
        '#', 'Date', 'Student', 'Transaction Type', 'Description',
        'Reference', 'Amount', 'Balance After', 'Session', 'Fiscal Period'
    ]
    ws.append(headers)
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
    
    # Data rows
    for idx, transaction in enumerate(transactions, start=1):
        ws.append([
            idx,
            transaction.created_at.strftime('%Y-%m-%d %H:%M'),
            transaction.student_account.student.get_full_name(),
            transaction.get_transaction_type_display(),
            transaction.description,
            transaction.reference_number or '',
            float(transaction.amount),
            float(transaction.balance_after),
            transaction.academic_session.name if transaction.academic_session else 'N/A',
            transaction.fiscal_period.name if transaction.fiscal_period else 'N/A',
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
    filename = f"account_transactions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


@login_required
def export_payments_excel(request):
    """Export payments to Excel with filters applied"""
    payments = get_filtered_payments(request)
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Payments"
    
    # Define styles
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_alignment = Alignment(horizontal="center", vertical="center")
    
    # Headers
    headers = [
        '#', 'Payment Number', 'Receipt Number', 'Date', 'Student',
        'Invoice Number', 'Amount', 'Amount Applied', 'Overpayment',
        'Payment Method', 'Paid By', 'Status', 'Verified', 'Session'
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
            payment.payment_number,
            payment.receipt_number or '',
            payment.payment_date.strftime('%Y-%m-%d'),
            payment.student.get_full_name(),
            payment.invoice.invoice_number if payment.invoice else 'N/A',
            float(payment.amount),
            float(payment.amount_applied_to_invoice),
            float(payment.overpayment_amount),
            payment.payment_method.name if payment.payment_method else 'N/A',
            payment.paid_by_name or '',
            payment.get_status_display(),
            'Yes' if payment.is_verified else 'No',
            payment.academic_session.name if payment.academic_session else 'N/A',
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
    filename = f"payments_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


@login_required
def export_scholarship_programs_excel(request):
    """Export scholarship programs to Excel with filters applied"""
    programs = get_filtered_scholarship_programs(request)
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Scholarship Programs"
    
    # Define styles
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_alignment = Alignment(horizontal="center", vertical="center")
    
    # Headers
    headers = [
        '#', 'Code', 'Name', 'Type', 'Discount Type', 'Discount Value',
        'Total Budget', 'Budget Used', 'Recipients', 'Applications',
        'Active', 'Accepting Applications'
    ]
    ws.append(headers)
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
    
    # Data rows
    for idx, program in enumerate(programs, start=1):
        ws.append([
            idx,
            program.code,
            program.name,
            program.get_scholarship_type_display(),
            program.get_discount_type_display(),
            float(program.discount_percentage or 0) if program.discount_type == 'PERCENTAGE' else float(program.fixed_discount_amount or 0),
            float(program.total_budget_amount) if program.total_budget_amount else 0,
            float(program.current_budget_used or 0),
            program.current_recipient_count or 0,
            program.application_count,
            'Yes' if program.is_active else 'No',
            'Yes' if program.is_accepting_applications else 'No',
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
    filename = f"scholarship_programs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


@login_required
def export_scholarship_applications_excel(request):
    """Export scholarship applications to Excel with filters applied"""
    applications = get_filtered_scholarship_applications(request)
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Scholarship Applications"
    
    # Define styles
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_alignment = Alignment(horizontal="center", vertical="center")
    
    # Headers
    headers = [
        '#', 'Application Number', 'Application Date', 'Student', 
        'Program', 'Requested Amount', 'Approved Amount', 'Current GPA',
        'Status', 'Reviewed By', 'Review Date'
    ]
    ws.append(headers)
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
    
    # Data rows
    for idx, application in enumerate(applications, start=1):
        ws.append([
            idx,
            application.application_number,
            application.application_date.strftime('%Y-%m-%d'),
            application.student.get_full_name(),
            application.scholarship_program.name,
            float(application.requested_amount or 0),
            float(application.approved_amount or 0),
            float(application.current_gpa) if application.current_gpa else 'N/A',
            application.get_status_display(),
            application.approved_by.get_full_name() if application.approved_by else 'N/A',
            application.approval_date.strftime('%Y-%m-%d') if application.approval_date else 'N/A',
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
    filename = f"scholarship_applications_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


@login_required
def export_student_scholarships_excel(request):
    """Export student scholarships to Excel with filters applied"""
    scholarships = get_filtered_student_scholarships(request)
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Student Scholarships"
    
    # Define styles
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_alignment = Alignment(horizontal="center", vertical="center")
    
    # Headers
    headers = [
        '#', 'Student', 'Program', 'Amount Awarded', 'Amount Used',
        'Remaining Balance', 'Start Date', 'End Date', 'Status',
        'Distribution Method', 'Is Renewable'
    ]
    ws.append(headers)
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
    
    # Data rows
    for idx, scholarship in enumerate(scholarships, start=1):
        remaining = scholarship.get_remaining_balance()
        ws.append([
            idx,
            scholarship.student.get_full_name(),
            scholarship.scholarship_program.name,
            float(scholarship.amount_awarded),
            float(scholarship.total_amount_used),
            float(remaining) if remaining else 0,
            scholarship.start_date.strftime('%Y-%m-%d'),
            scholarship.end_date.strftime('%Y-%m-%d') if scholarship.end_date else 'N/A',
            scholarship.get_status_display(),
            scholarship.get_distribution_method_display(),
            'Yes' if scholarship.is_renewable else 'No',
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
    filename = f"student_scholarships_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


@login_required
def export_discounts_excel(request):
    """Export discounts to Excel with filters applied"""
    discounts = get_filtered_discounts(request)
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Discounts"
    
    # Define styles
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_alignment = Alignment(horizontal="center", vertical="center")
    
    # Headers
    headers = [
        '#', 'Code', 'Name', 'Type', 'Value', 'Eligibility',
        'Budget Limit', 'Budget Used', 'Usage Count', 'Usage Limit',
        'Start Date', 'End Date', 'Active', 'Auto Apply'
    ]
    ws.append(headers)
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
    
    # Data rows
    for idx, discount in enumerate(discounts, start=1):
        ws.append([
            idx,
            discount.code,
            discount.name,
            discount.get_discount_type_display(),
            float(discount.discount_value),
            discount.get_eligibility_criteria_display(),
            float(discount.budget_limit) if discount.budget_limit else 'N/A',
            float(discount.current_budget_used or 0),
            discount.current_usage_count or 0,
            discount.max_usage_count if discount.max_usage_count else 'N/A',
            discount.start_date.strftime('%Y-%m-%d'),
            discount.end_date.strftime('%Y-%m-%d'),
            'Yes' if discount.is_active else 'No',
            'Yes' if discount.auto_apply else 'No',
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
    filename = f"discounts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


@login_required
def export_refunds_excel(request):
    """Export refunds to Excel with filters applied"""
    refunds = get_filtered_refunds(request)
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Refunds"
    
    # Define styles
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_alignment = Alignment(horizontal="center", vertical="center")
    
    # Headers
    headers = [
        '#', 'Refund Number', 'Request Date', 'Student', 'Refund Type',
        'Amount', 'Approved Amount', 'Status', 'Payment Method',
        'Requested By', 'Approved By', 'Processed Date'
    ]
    ws.append(headers)
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
    
    # Data rows
    for idx, refund in enumerate(refunds, start=1):
        ws.append([
            idx,
            refund.refund_number,
            refund.requested_date.strftime('%Y-%m-%d'),
            refund.student.get_full_name(),
            refund.get_refund_type_display(),
            float(refund.amount),
            float(refund.approved_amount or 0),
            refund.get_status_display(),
            refund.payment_method.name if refund.payment_method else 'N/A',
            refund.requested_by.get_full_name() if refund.requested_by else 'N/A',
            refund.approved_by.get_full_name() if refund.approved_by else 'N/A',
            refund.processed_date.strftime('%Y-%m-%d') if refund.processed_date else 'N/A',
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
    filename = f"refunds_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


@login_required
def export_display_groups_excel(request):
    """Export display groups to Excel"""
    groups = get_filtered_display_groups(request)
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Display Groups"
    
    # Define styles
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_alignment = Alignment(horizontal="center", vertical="center")
    
    # Headers
    headers = [
        '#', 'Name', 'Description', 'Display Order', 
        'Show as Group', 'Active', 'Category Count'
    ]
    ws.append(headers)
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
    
    # Data rows
    for idx, group in enumerate(groups, start=1):
        ws.append([
            idx,
            group.name,
            group.description or '',
            group.display_order,
            'Yes' if group.show_as_group else 'No',
            'Yes' if group.is_active else 'No',
            group.category_count or 0,
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
    filename = f"display_groups_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


@login_required
def export_fee_categories_excel(request):
    """Export fee categories to Excel with filters applied"""
    categories = get_filtered_fee_categories(request)
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Fee Categories"
    
    # Define styles
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_alignment = Alignment(horizontal="center", vertical="center")
    
    # Headers
    headers = [
        '#', 'Code', 'Name', 'Category Type', 'Display Group',
        'Applicability', 'Frequency', 'Mandatory', 'Refundable',
        'Taxable', 'Active', 'Display Order'
    ]
    ws.append(headers)
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
    
    # Data rows
    for idx, category in enumerate(categories, start=1):
        ws.append([
            idx,
            category.code,
            category.name,
            category.get_category_type_display(),
            category.display_group.name if category.display_group else 'N/A',
            category.get_applicability_display(),
            category.get_frequency_display() if category.frequency else 'N/A',
            'Yes' if category.is_mandatory else 'No',
            'Yes' if category.is_refundable else 'No',
            'Yes' if category.is_taxable else 'No',
            'Yes' if category.is_active else 'No',
            category.display_order,
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
    filename = f"fee_categories_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


@login_required
def export_fee_structures_excel(request):
    """Export fee structures to Excel with filters applied"""
    structures = get_filtered_fee_structures(request)
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Fee Structures"
    
    # Define styles
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_alignment = Alignment(horizontal="center", vertical="center")
    
    # Headers
    headers = [
        '#', 'Name', 'Structure Type', 'Academic Year', 'Billing Frequency',
        'Total Amount', 'Payment Terms (Days)', 'Charges Late Fee',
        'Active', 'Effective Date', 'Expiry Date', 'Priority'
    ]
    ws.append(headers)
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
    
    # Data rows
    for idx, structure in enumerate(structures, start=1):
        ws.append([
            idx,
            structure.name,
            structure.get_structure_type_display(),
            structure.academic_year.name if structure.academic_year else 'N/A',
            structure.get_billing_frequency_display(),
            float(structure.total_amount or 0),
            structure.payment_terms_days,
            'Yes' if structure.charges_late_fee else 'No',
            'Yes' if structure.is_active else 'No',
            structure.effective_date.strftime('%Y-%m-%d'),
            structure.expiry_date.strftime('%Y-%m-%d') if structure.expiry_date else 'N/A',
            structure.priority,
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
    filename = f"fee_structures_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


# =============================================================================
# REPORT EXPORT FUNCTIONS
# =============================================================================

@login_required
def export_collection_report_excel(request):
    """Export fee collection report to Excel"""
    
    # Get filter parameters
    session_id = request.GET.get('session')
    period_id = request.GET.get('period')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    # Build filters for stats
    filters = {}
    if session_id:
        filters['academic_session'] = session_id
    if period_id:
        filters['fiscal_period'] = period_id
    if date_from:
        filters['date_from'] = date_from
    if date_to:
        filters['date_to'] = date_to
    
    # Get statistics
    invoice_stats = fees_stats.get_invoice_statistics(filters)
    payment_stats = fees_stats.get_payment_statistics(filters)
    
    # Create workbook with multiple sheets
    wb = Workbook()
    
    # ========== SUMMARY SHEET ==========
    ws_summary = wb.active
    ws_summary.title = "Summary"
    
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    
    ws_summary.append(['Fee Collection Report'])
    ws_summary.append([])
    ws_summary.append(['Report Period:'])
    ws_summary.append(['Session:', session_id or 'All'])
    ws_summary.append(['Period:', period_id or 'All'])
    ws_summary.append(['From:', date_from or 'N/A'])
    ws_summary.append(['To:', date_to or 'N/A'])
    ws_summary.append([])
    
    # Invoice Summary
    ws_summary.append(['Invoice Summary'])
    ws_summary.append(['Total Invoices:', invoice_stats.get('total_count', 0)])
    ws_summary.append(['Total Amount:', float(invoice_stats.get('total_amount', 0))])
    ws_summary.append(['Total Paid:', float(invoice_stats.get('total_paid', 0))])
    ws_summary.append(['Total Outstanding:', float(invoice_stats.get('total_outstanding', 0))])
    ws_summary.append([])
    
    # Payment Summary
    ws_summary.append(['Payment Summary'])
    ws_summary.append(['Total Payments:', payment_stats.get('total_count', 0)])
    ws_summary.append(['Total Amount Collected:', float(payment_stats.get('total_amount', 0))])
    ws_summary.append([])
    
    # Create response
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"collection_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


@login_required
def export_outstanding_report_excel(request):
    """Export outstanding fees report to Excel"""
    
    # Get filter parameters
    session_id = request.GET.get('session')
    level_id = request.GET.get('level')
    
    today = get_school_today()
    
    # Build queryset
    overdue_invoices = FeeInvoice.objects.filter(
        due_date__lt=today,
        status__in=['PENDING', 'PARTIALLY_PAID', 'OVERDUE']
    ).select_related('student', 'academic_session')
    
    if session_id:
        overdue_invoices = overdue_invoices.filter(academic_session_id=session_id)
    
    if level_id:
        overdue_invoices = overdue_invoices.filter(
            student__current_academic_level_id=level_id
        )
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Outstanding Fees"
    
    # Define styles
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_alignment = Alignment(horizontal="center", vertical="center")
    
    # Headers
    headers = [
        '#', 'Invoice Number', 'Student', 'Session', 'Issue Date',
        'Due Date', 'Days Overdue', 'Total Amount', 'Paid Amount',
        'Balance', 'Status'
    ]
    ws.append(headers)
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
    
    # Data rows
    for idx, invoice in enumerate(overdue_invoices, start=1):
        days_overdue = (today - invoice.due_date).days
        ws.append([
            idx,
            invoice.invoice_number,
            invoice.student.get_full_name(),
            invoice.academic_session.name if invoice.academic_session else 'N/A',
            invoice.issue_date.strftime('%Y-%m-%d'),
            invoice.due_date.strftime('%Y-%m-%d'),
            days_overdue,
            float(invoice.total_amount),
            float(invoice.paid_amount),
            float(invoice.balance),
            invoice.get_status_display(),
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
    filename = f"outstanding_fees_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


@login_required
def export_aging_report_excel(request):
    """Export aging analysis report to Excel"""
    
    today = get_school_today()
    
    # Define aging buckets
    aging_buckets = [
        ('Current', today, None),
        ('1-30 Days', today - timedelta(days=30), today),
        ('31-60 Days', today - timedelta(days=60), today - timedelta(days=30)),
        ('61-90 Days', today - timedelta(days=90), today - timedelta(days=60)),
        ('Over 90 Days', None, today - timedelta(days=90)),
    ]
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Aging Analysis"
    
    # Define styles
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_alignment = Alignment(horizontal="center", vertical="center")
    
    # Headers
    headers = ['Aging Bucket', 'Invoice Count', 'Total Amount', 'Percentage']
    ws.append(headers)
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
    
    # Calculate data for each bucket
    grand_total = Decimal('0.00')
    bucket_data = []
    
    for bucket_name, date_from, date_to in aging_buckets:
        invoices = FeeInvoice.objects.filter(
            status__in=['PENDING', 'PARTIALLY_PAID', 'OVERDUE']
        )
        
        if bucket_name == 'Current':
            invoices = invoices.filter(due_date__gte=today)
        elif bucket_name == 'Over 90 Days':
            invoices = invoices.filter(due_date__lt=date_to)
        else:
            invoices = invoices.filter(due_date__lt=date_to, due_date__gte=date_from)
        
        count = invoices.count()
        total = invoices.aggregate(Sum('balance'))['balance__sum'] or Decimal('0.00')
        
        bucket_data.append((bucket_name, count, total))
        grand_total += total
    
    # Data rows
    for bucket_name, count, total in bucket_data:
        percentage = (float(total) / float(grand_total) * 100) if grand_total > 0 else 0
        ws.append([
            bucket_name,
            count,
            float(total),
            f"{percentage:.1f}%"
        ])
    
    # Add totals row
    ws.append([])
    ws.append(['TOTAL', sum(d[1] for d in bucket_data), float(grand_total), '100.0%'])
    
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
    filename = f"aging_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


@login_required
def export_payment_methods_report_excel(request):
    """Export payment methods analysis report to Excel"""
    
    # Get date range filters
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    # Build queryset
    payments = Payment.objects.filter(status='COMPLETED')
    
    if date_from:
        payments = payments.filter(payment_date__gte=date_from)
    if date_to:
        payments = payments.filter(payment_date__lte=date_to)
    
    # Group by payment method
    method_stats = payments.values(
        'payment_method__name',
        'payment_method__method_type'
    ).annotate(
        count=Count('id'),
        total_amount=Sum('amount'),
        avg_amount=Avg('amount')
    ).order_by('-total_amount')
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Payment Methods"
    
    # Define styles
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_alignment = Alignment(horizontal="center", vertical="center")
    
    # Headers
    headers = ['Payment Method', 'Method Type', 'Transaction Count', 'Total Amount', 'Average Amount']
    ws.append(headers)
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
    
    # Data rows
    grand_total = Decimal('0.00')
    total_count = 0
    
    for stat in method_stats:
        ws.append([
            stat['payment_method__name'] or 'N/A',
            stat['payment_method__method_type'] or 'N/A',
            stat['count'],
            float(stat['total_amount'] or 0),
            float(stat['avg_amount'] or 0),
        ])
        grand_total += (stat['total_amount'] or 0)
        total_count += stat['count']
    
    # Add totals row
    ws.append([])
    ws.append(['TOTAL', '', total_count, float(grand_total), ''])
    
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
    filename = f"payment_methods_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response