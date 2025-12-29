# fees/views.py

"""
Fee Management Views

Comprehensive view functions for:
- Student Accounts and Transactions
- Display Groups and Fee Categories
- Fee Structures and Items
- Invoices and Payments
- Scholarship Programs and Applications
- Discounts and Refunds

All views include proper permissions, messaging, and error handling
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import (
    Q, Count, Sum, Avg, F, Prefetch, DecimalField,
    Case, When, Value, IntegerField
)
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
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
from .forms import (
    StudentAccountForm,
    AccountTransactionForm,
    DisplayGroupForm,
    FeesCategoryForm,
    FeesStructureForm,
    FeesStructureItemForm,
    FeeInvoiceForm,
    FeeInvoiceItemForm,
    PaymentForm,
    PaymentVerificationForm,
    ScholarshipProgramForm,
    StudentScholarshipApplicationForm,
    ScholarshipApplicationReviewForm,
    StudentScholarshipForm,
    FeesDiscountForm,
    DiscountApplicationForm,
    RefundForm,
    RefundApprovalForm,
    BulkInvoiceGenerationForm,
)

# Import utility functions from utils.py
from .utils import (
    generate_invoice_number,
    generate_payment_number,
    generate_receipt_number,
    generate_refund_number,
    generate_scholarship_application_number,
    get_invoice_items_organized,
    format_invoice_for_display,
    validate_invoice_data,
    validate_payment_data,
    get_invoice_status_color,
    calculate_line_item_totals,
)

# Import statistics functions from stats.py
from .stats import get_financial_dashboard

from students.models import Student
from academics.models import AcademicSession

logger = logging.getLogger(__name__)


# =============================================================================
# UTILITY FUNCTIONS (View-specific only)
# =============================================================================

def get_student_account_summary(student_account):
    """
    Get comprehensive summary for a student account (view-specific aggregation)
    
    Args:
        student_account: StudentAccount instance
        
    Returns:
        dict: Summary data for display in account detail view
    """
    
    # Transaction summary
    transactions = student_account.transactions.all()
    
    # Invoice summary
    invoices = FeeInvoice.objects.filter(student=student_account.student)
    
    # Payment summary
    payments = Payment.objects.filter(student=student_account.student)
    
    # Scholarship summary
    scholarships = StudentScholarship.objects.filter(
        student=student_account.student,
        status='ACTIVE'
    )
    
    return {
        'total_transactions': transactions.count(),
        'recent_transactions': transactions.order_by('-created_at')[:10],
        'total_invoices': invoices.count(),
        'unpaid_invoices': invoices.filter(
            status__in=['PENDING', 'PARTIALLY_PAID', 'OVERDUE']
        ).count(),
        'total_payments': payments.filter(status='COMPLETED').count(),
        'active_scholarships': scholarships.count(),
        'total_scholarship_balance': scholarships.aggregate(
            total=Sum(F('amount_awarded') - F('total_amount_used'))
        )['total'] or Decimal('0'),
    }


# =============================================================================
# DASHBOARD
# =============================================================================

@login_required
def fees_dashboard(request):
    """Main fees dashboard with overview statistics"""
    
    try:
        # Use centralized dashboard statistics from stats.py
        stats = get_financial_dashboard()
    except Exception as e:
        logger.error(f"Error getting dashboard statistics: {e}")
        stats = {}
    
    # Get recent activities
    recent_invoices = FeeInvoice.objects.select_related(
        'student', 'academic_session'
    ).order_by('-created_at')[:10]
    
    recent_payments = Payment.objects.select_related(
        'student', 'invoice', 'payment_method'
    ).order_by('-created_at')[:10]
    
    # Get overdue invoices
    today = timezone.now().date()
    overdue_invoices = FeeInvoice.objects.filter(
        due_date__lt=today,
        status__in=['PENDING', 'PARTIALLY_PAID', 'OVERDUE']
    ).select_related('student').order_by('due_date')[:10]
    
    # Get pending applications
    pending_applications = StudentScholarshipApplication.objects.filter(
        status__in=['SUBMITTED', 'UNDER_REVIEW']
    ).select_related(
        'student', 'scholarship_program'
    ).order_by('-application_date')[:10]
    
    context = {
        'stats': stats,
        'recent_invoices': recent_invoices,
        'recent_payments': recent_payments,
        'overdue_invoices': overdue_invoices,
        'pending_applications': pending_applications,
    }
    
    return render(request, 'fees/dashboard.html', context)


# =============================================================================
# STUDENT ACCOUNT VIEWS
# =============================================================================

@login_required
def student_account_list(request):
    """List all student accounts - HTMX loads data on page load"""
    
    # Get initial stats
    try:
        total_accounts = StudentAccount.objects.count()
        active_accounts = StudentAccount.objects.filter(status='ACTIVE').count()
        accounts_with_debt = StudentAccount.objects.filter(
            current_balance__lt=0
        ).count()
        accounts_with_credit = StudentAccount.objects.filter(
            current_balance__gt=0
        ).count()
        
        initial_stats = {
            'total_accounts': total_accounts,
            'active_accounts': active_accounts,
            'accounts_with_debt': accounts_with_debt,
            'accounts_with_credit': accounts_with_credit,
            'total_debt': abs(StudentAccount.objects.filter(
                current_balance__lt=0
            ).aggregate(Sum('current_balance'))['current_balance__sum'] or 0),
            'total_credit': StudentAccount.objects.filter(
                current_balance__gt=0
            ).aggregate(Sum('current_balance'))['current_balance__sum'] or 0,
        }
    except Exception as e:
        logger.error(f"Error getting student account statistics: {e}")
        initial_stats = {}
    
    context = {
        'stats': initial_stats,
    }
    
    return render(request, 'fees/accounts/list.html', context)


@login_required
def student_account_create(request):
    """Create a new student account"""
    if request.method == "POST":
        form = StudentAccountForm(request.POST)
        if form.is_valid():
            account = form.save()
            messages.success(
                request,
                f"Account created for {account.student.get_full_name()}"
            )
            return redirect("fees:student_account_detail", pk=account.pk)
    else:
        form = StudentAccountForm()
    
    context = {
        'form': form,
        'title': 'Create Student Account',
    }
    return render(request, 'fees/accounts/form.html', context)


@login_required
def student_account_edit(request, pk):
    """Edit existing student account"""
    account = get_object_or_404(StudentAccount, pk=pk)
    
    if request.method == "POST":
        form = StudentAccountForm(request.POST, instance=account)
        if form.is_valid():
            account = form.save()
            messages.success(
                request,
                f"Account updated for {account.student.get_full_name()}"
            )
            return redirect("fees:student_account_detail", pk=account.pk)
    else:
        form = StudentAccountForm(instance=account)
    
    context = {
        'form': form,
        'account': account,
        'title': 'Update Student Account',
    }
    return render(request, 'fees/accounts/form.html', context)


@login_required
def student_account_detail(request, pk):
    """View student account details with transactions, invoices, and payments"""
    account = get_object_or_404(
        StudentAccount.objects.select_related('student').prefetch_related(
            Prefetch(
                'transactions',
                queryset=AccountTransaction.objects.order_by('-created_at')
            ),
        ),
        pk=pk
    )
    
    # Get comprehensive summary
    summary = get_student_account_summary(account)
    
    # Get invoices
    invoices = FeeInvoice.objects.filter(
        student=account.student
    ).select_related('academic_session', 'fee_structure').order_by('-issue_date')
    
    # Get payments
    payments = Payment.objects.filter(
        student=account.student
    ).select_related('invoice', 'payment_method').order_by('-payment_date')
    
    # Get scholarships
    scholarships = StudentScholarship.objects.filter(
        student=account.student
    ).select_related('scholarship_program').order_by('-awarded_date')
    
    context = {
        'account': account,
        'summary': summary,
        'invoices': invoices[:20],
        'payments': payments[:20],
        'scholarships': scholarships,
    }
    
    return render(request, 'fees/accounts/detail.html', context)


# =============================================================================
# DISPLAY GROUP VIEWS
# =============================================================================

@login_required
def display_group_list(request):
    """List all display groups"""
    
    try:
        total_groups = DisplayGroup.objects.count()
        active_groups = DisplayGroup.objects.filter(is_active=True).count()
        
        initial_stats = {
            'total_groups': total_groups,
            'active_groups': active_groups,
        }
    except Exception as e:
        logger.error(f"Error getting display group statistics: {e}")
        initial_stats = {}
    
    context = {
        'stats': initial_stats,
    }
    
    return render(request, 'fees/display_groups/list.html', context)


@login_required
def display_group_create(request):
    """Create a new display group"""
    if request.method == "POST":
        form = DisplayGroupForm(request.POST)
        if form.is_valid():
            group = form.save()
            messages.success(
                request,
                f"Display group '{group.name}' was created successfully"
            )
            return redirect("fees:display_group_list")
    else:
        form = DisplayGroupForm()
    
    context = {
        'form': form,
        'title': 'Create Display Group',
    }
    return render(request, 'fees/display_groups/form.html', context)


@login_required
def display_group_edit(request, pk):
    """Edit existing display group"""
    group = get_object_or_404(DisplayGroup, pk=pk)
    
    if request.method == "POST":
        form = DisplayGroupForm(request.POST, instance=group)
        if form.is_valid():
            group = form.save()
            messages.success(
                request,
                f"Display group '{group.name}' was updated successfully"
            )
            return redirect("fees:display_group_list")
    else:
        form = DisplayGroupForm(instance=group)
    
    context = {
        'form': form,
        'group': group,
        'title': 'Update Display Group',
    }
    return render(request, 'fees/display_groups/form.html', context)


@login_required
def display_group_delete(request, pk):
    """Delete a display group"""
    group = get_object_or_404(DisplayGroup, pk=pk)
    
    if request.method == "POST":
        # Check if group has categories
        if group.feescategory_set.exists():
            messages.error(
                request,
                f"Cannot delete group '{group.name}' - it has associated fee categories"
            )
            return redirect("fees:display_group_list")
        
        group_name = group.name
        group.delete()
        messages.success(
            request,
            f"Display group '{group_name}' was deleted successfully"
        )
        return redirect("fees:display_group_list")
    
    return redirect("fees:display_group_list")


# =============================================================================
# FEE CATEGORY VIEWS
# =============================================================================

@login_required
def fee_category_list(request):
    """List all fee categories - HTMX loads data on page load"""
    
    try:
        total_categories = FeesCategory.objects.count()
        active_categories = FeesCategory.objects.filter(is_active=True).count()
        mandatory_categories = FeesCategory.objects.filter(is_mandatory=True).count()
        
        initial_stats = {
            'total_categories': total_categories,
            'active_categories': active_categories,
            'mandatory_categories': mandatory_categories,
            'optional_categories': FeesCategory.objects.filter(
                is_mandatory=False
            ).count(),
        }
    except Exception as e:
        logger.error(f"Error getting fee category statistics: {e}")
        initial_stats = {}
    
    # Get display groups for filtering
    display_groups = DisplayGroup.objects.filter(is_active=True).order_by('name')
    
    context = {
        'stats': initial_stats,
        'display_groups': display_groups,
    }
    
    return render(request, 'fees/categories/list.html', context)


@login_required
def fee_category_create(request):
    """Create a new fee category"""
    if request.method == "POST":
        form = FeesCategoryForm(request.POST)
        if form.is_valid():
            category = form.save()
            messages.success(
                request,
                f"Fee category '{category.name}' ({category.code}) was created successfully"
            )
            return redirect("fees:fee_category_detail", pk=category.pk)
    else:
        form = FeesCategoryForm()
    
    context = {
        'form': form,
        'title': 'Create Fee Category',
    }
    return render(request, 'fees/categories/form.html', context)


@login_required
def fee_category_edit(request, pk):
    """Edit existing fee category"""
    category = get_object_or_404(FeesCategory, pk=pk)
    
    if request.method == "POST":
        form = FeesCategoryForm(request.POST, instance=category)
        if form.is_valid():
            category = form.save()
            messages.success(
                request,
                f"Fee category '{category.name}' was updated successfully"
            )
            return redirect("fees:fee_category_detail", pk=category.pk)
    else:
        form = FeesCategoryForm(instance=category)
    
    context = {
        'form': form,
        'category': category,
        'title': 'Update Fee Category',
    }
    return render(request, 'fees/categories/form.html', context)


@login_required
def fee_category_delete(request, pk):
    """Delete a fee category"""
    category = get_object_or_404(FeesCategory, pk=pk)
    
    if request.method == "POST":
        # Check if category is used in structures
        if category.feesstructureitem_set.exists():
            messages.error(
                request,
                f"Cannot delete category '{category.name}' - it is used in fee structures"
            )
            return redirect("fees:fee_category_detail", pk=pk)
        
        # Check if category is used in invoices
        if category.feeinvoiceitem_set.exists():
            messages.error(
                request,
                f"Cannot delete category '{category.name}' - it is used in invoices"
            )
            return redirect("fees:fee_category_detail", pk=pk)
        
        category_name = category.name
        category_code = category.code
        category.delete()
        messages.success(
            request,
            f"Fee category '{category_name}' ({category_code}) was deleted successfully"
        )
        return redirect("fees:fee_category_list")
    
    return redirect("fees:fee_category_detail", pk=pk)


@login_required
def fee_category_detail(request, pk):
    """View fee category details"""
    category = get_object_or_404(
        FeesCategory.objects.select_related(
            'display_group'
        ).prefetch_related(
            'applicable_levels',
            Prefetch(
                'feesstructureitem_set',
                queryset=FeesStructureItem.objects.select_related('fee_structure')
            ),
        ),
        pk=pk
    )
    
    # Get structures using this category
    structures = FeesStructure.objects.filter(
        items__fee_category=category
    ).distinct().order_by('name')
    
    # Get usage statistics
    total_invoices = FeeInvoiceItem.objects.filter(
        fee_category=category
    ).count()
    
    total_revenue = FeeInvoiceItem.objects.filter(
        fee_category=category,
        invoice__status='PAID'
    ).aggregate(total=Sum('final_amount'))['total'] or Decimal('0')
    
    context = {
        'category': category,
        'structures': structures,
        'total_invoices': total_invoices,
        'total_revenue': total_revenue,
    }
    
    return render(request, 'fees/categories/detail.html', context)


# =============================================================================
# FEE STRUCTURE VIEWS
# =============================================================================

@login_required
def fee_structure_list(request):
    """List all fee structures - HTMX loads data on page load"""
    
    try:
        total_structures = FeesStructure.objects.count()
        active_structures = FeesStructure.objects.filter(is_active=True).count()
        
        initial_stats = {
            'total_structures': total_structures,
            'active_structures': active_structures,
        }
    except Exception as e:
        logger.error(f"Error getting fee structure statistics: {e}")
        initial_stats = {}
    
    # Get sessions for filtering
    sessions = AcademicSession.objects.filter(is_active=True).order_by('-start_date')
    
    context = {
        'stats': initial_stats,
        'sessions': sessions,
    }
    
    return render(request, 'fees/structures/list.html', context)


@login_required
def fee_structure_create(request):
    """Create a new fee structure"""
    if request.method == "POST":
        form = FeesStructureForm(request.POST)
        if form.is_valid():
            structure = form.save()
            messages.success(
                request,
                f"Fee structure '{structure.name}' was created successfully"
            )
            return redirect("fees:fee_structure_detail", pk=structure.pk)
    else:
        form = FeesStructureForm()
    
    context = {
        'form': form,
        'title': 'Create Fee Structure',
    }
    return render(request, 'fees/structures/form.html', context)


@login_required
def fee_structure_edit(request, pk):
    """Edit existing fee structure"""
    structure = get_object_or_404(FeesStructure, pk=pk)
    
    if request.method == "POST":
        form = FeesStructureForm(request.POST, instance=structure)
        if form.is_valid():
            structure = form.save()
            messages.success(
                request,
                f"Fee structure '{structure.name}' was updated successfully"
            )
            return redirect("fees:fee_structure_detail", pk=structure.pk)
    else:
        form = FeesStructureForm(instance=structure)
    
    context = {
        'form': form,
        'structure': structure,
        'title': 'Update Fee Structure',
    }
    return render(request, 'fees/structures/form.html', context)


@login_required
def fee_structure_delete(request, pk):
    """Delete a fee structure"""
    structure = get_object_or_404(FeesStructure, pk=pk)
    
    if request.method == "POST":
        # Check if structure has invoices
        if structure.invoices.exists():
            messages.error(
                request,
                f"Cannot delete structure '{structure.name}' - it has associated invoices"
            )
            return redirect("fees:fee_structure_detail", pk=pk)
        
        structure_name = structure.name
        structure.delete()
        messages.success(
            request,
            f"Fee structure '{structure_name}' was deleted successfully"
        )
        return redirect("fees:fee_structure_list")
    
    return redirect("fees:fee_structure_detail", pk=pk)


@login_required
def fee_structure_detail(request, pk):
    """View fee structure details with items and statistics"""
    structure = get_object_or_404(
        FeesStructure.objects.prefetch_related(
            'academic_levels',
            'applicable_sessions',
            'applicable_classes',
            Prefetch(
                'items',
                queryset=FeesStructureItem.objects.select_related('fee_category')
            ),
        ),
        pk=pk
    )
    
    # Calculate total amount
    total_amount = structure.items.aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0')
    
    # Get invoices using this structure
    invoices_count = structure.invoices.count()
    invoices_total = structure.invoices.aggregate(
        total=Sum('total_amount')
    )['total'] or Decimal('0')
    
    context = {
        'structure': structure,
        'total_amount': total_amount,
        'invoices_count': invoices_count,
        'invoices_total': invoices_total,
    }
    
    return render(request, 'fees/structures/detail.html', context)

# =============================================================================
# FEE INVOICE VIEWS
# =============================================================================

@login_required
def fee_invoice_list(request):
    """List all fee invoices - HTMX loads data on page load"""
    
    try:
        today = timezone.now().date()
        
        total_invoices = FeeInvoice.objects.count()
        pending_invoices = FeeInvoice.objects.filter(
            status__in=['PENDING', 'PARTIALLY_PAID']
        ).count()
        paid_invoices = FeeInvoice.objects.filter(status='PAID').count()
        overdue_invoices = FeeInvoice.objects.filter(
            due_date__lt=today,
            status__in=['PENDING', 'PARTIALLY_PAID', 'OVERDUE']
        ).count()
        
        initial_stats = {
            'total_invoices': total_invoices,
            'pending_invoices': pending_invoices,
            'paid_invoices': paid_invoices,
            'overdue_invoices': overdue_invoices,
            'total_outstanding': FeeInvoice.objects.filter(
                status__in=['PENDING', 'PARTIALLY_PAID', 'OVERDUE']
            ).aggregate(Sum('balance'))['balance__sum'] or Decimal('0'),
        }
    except Exception as e:
        logger.error(f"Error getting invoice statistics: {e}")
        initial_stats = {}
    
    # Get sessions for filtering
    sessions = AcademicSession.objects.filter(is_active=True).order_by('-start_date')
    
    context = {
        'stats': initial_stats,
        'sessions': sessions,
    }
    
    return render(request, 'fees/invoices/list.html', context)


@login_required
def fee_invoice_create(request):
    """Create a new fee invoice"""
    if request.method == "POST":
        form = FeeInvoiceForm(request.POST)
        if form.is_valid():
            invoice = form.save(commit=False)
            # Number is auto-generated by signal, but can be overridden here if needed
            if not invoice.invoice_number:
                invoice.invoice_number = generate_invoice_number()
            invoice.save()
            form.save_m2m()
            
            messages.success(
                request,
                f"Invoice {invoice.invoice_number} created for {invoice.student.get_full_name()}"
            )
            return redirect("fees:fee_invoice_detail", pk=invoice.pk)
    else:
        form = FeeInvoiceForm()
    
    context = {
        'form': form,
        'title': 'Create Fee Invoice',
    }
    return render(request, 'fees/invoices/form.html', context)


@login_required
def fee_invoice_edit(request, pk):
    """Edit existing fee invoice"""
    invoice = get_object_or_404(FeeInvoice, pk=pk)
    
    # Only allow editing draft invoices
    if invoice.status != 'DRAFT':
        messages.error(
            request,
            f"Cannot edit invoice {invoice.invoice_number} - only draft invoices can be edited"
        )
        return redirect("fees:fee_invoice_detail", pk=pk)
    
    if request.method == "POST":
        form = FeeInvoiceForm(request.POST, instance=invoice)
        if form.is_valid():
            invoice = form.save()
            messages.success(
                request,
                f"Invoice {invoice.invoice_number} was updated successfully"
            )
            return redirect("fees:fee_invoice_detail", pk=invoice.pk)
    else:
        form = FeeInvoiceForm(instance=invoice)
    
    context = {
        'form': form,
        'invoice': invoice,
        'title': 'Update Fee Invoice',
    }
    return render(request, 'fees/invoices/form.html', context)


@login_required
def fee_invoice_delete(request, pk):
    """Delete a fee invoice"""
    invoice = get_object_or_404(FeeInvoice, pk=pk)
    
    if request.method == "POST":
        # Only allow deleting draft invoices
        if invoice.status != 'DRAFT':
            messages.error(
                request,
                f"Cannot delete invoice {invoice.invoice_number} - only draft invoices can be deleted"
            )
            return redirect("fees:fee_invoice_detail", pk=pk)
        
        # Check if invoice has payments
        if invoice.payments.exists():
            messages.error(
                request,
                f"Cannot delete invoice {invoice.invoice_number} - it has associated payments"
            )
            return redirect("fees:fee_invoice_detail", pk=pk)
        
        invoice_number = invoice.invoice_number
        invoice.delete()
        messages.success(
            request,
            f"Invoice {invoice_number} was deleted successfully"
        )
        return redirect("fees:fee_invoice_list")
    
    return redirect("fees:fee_invoice_detail", pk=pk)


@login_required
def fee_invoice_detail(request, pk):
    """View fee invoice details with items, payments, and history"""
    invoice = get_object_or_404(
        FeeInvoice.objects.select_related(
            'student',
            'academic_session',
            'fiscal_period',
            'fee_structure'
        ).prefetch_related(
            Prefetch(
                'items',
                queryset=FeeInvoiceItem.objects.select_related('fee_category')
            ),
            Prefetch(
                'payments',
                queryset=Payment.objects.order_by('-payment_date')
            ),
        ),
        pk=pk
    )
    
    # Get payment summary
    total_paid = invoice.payments.filter(
        status='COMPLETED'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    
    # Get scholarship applications
    scholarship_logs = ScholarshipApplicationLog.objects.filter(
        invoice=invoice
    ).select_related('scholarship__scholarship_program')
    
    # Get discount applications
    discount_applications = DiscountApplication.objects.filter(
        invoice=invoice
    ).select_related('discount')
    
    context = {
        'invoice': invoice,
        'total_paid': total_paid,
        'scholarship_logs': scholarship_logs,
        'discount_applications': discount_applications,
    }
    
    return render(request, 'fees/invoices/detail.html', context)


# =============================================================================
# PAYMENT VIEWS
# =============================================================================

@login_required
def payment_list(request):
    """List all payments - HTMX loads data on page load"""
    
    try:
        total_payments = Payment.objects.filter(status='COMPLETED').count()
        verified_payments = Payment.objects.filter(
            status='COMPLETED',
            is_verified=True
        ).count()
        unverified_payments = Payment.objects.filter(
            status='COMPLETED',
            is_verified=False
        ).count()
        
        total_amount = Payment.objects.filter(
            status='COMPLETED'
        ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
        
        initial_stats = {
            'total_payments': total_payments,
            'verified_payments': verified_payments,
            'unverified_payments': unverified_payments,
            'total_amount': total_amount,
        }
    except Exception as e:
        logger.error(f"Error getting payment statistics: {e}")
        initial_stats = {}
    
    # Get sessions for filtering
    sessions = AcademicSession.objects.filter(is_active=True).order_by('-start_date')
    
    context = {
        'stats': initial_stats,
        'sessions': sessions,
    }
    
    return render(request, 'fees/payments/list.html', context)


@login_required
def payment_create(request):
    """Create a new payment"""
    if request.method == "POST":
        form = PaymentForm(request.POST)
        if form.is_valid():
            payment = form.save(commit=False)
            # Numbers are auto-generated by signal, but can be overridden if needed
            if not payment.payment_number:
                payment.payment_number = generate_payment_number()
            if not payment.receipt_number:
                payment.receipt_number = generate_receipt_number()
            payment.save()
            
            messages.success(
                request,
                f"Payment {payment.payment_number} recorded for {payment.student.get_full_name()}"
            )
            return redirect("fees:payment_detail", pk=payment.pk)
    else:
        form = PaymentForm()
    
    context = {
        'form': form,
        'title': 'Record Payment',
    }
    return render(request, 'fees/payments/form.html', context)


@login_required
def payment_edit(request, pk):
    """Edit existing payment"""
    payment = get_object_or_404(Payment, pk=pk)
    
    # Only allow editing unverified payments
    if payment.is_verified:
        messages.error(
            request,
            f"Cannot edit payment {payment.payment_number} - verified payments cannot be edited"
        )
        return redirect("fees:payment_detail", pk=pk)
    
    if request.method == "POST":
        form = PaymentForm(request.POST, instance=payment)
        if form.is_valid():
            payment = form.save()
            messages.success(
                request,
                f"Payment {payment.payment_number} was updated successfully"
            )
            return redirect("fees:payment_detail", pk=payment.pk)
    else:
        form = PaymentForm(instance=payment)
    
    context = {
        'form': form,
        'payment': payment,
        'title': 'Update Payment',
    }
    return render(request, 'fees/payments/form.html', context)


@login_required
def payment_delete(request, pk):
    """Delete a payment"""
    payment = get_object_or_404(Payment, pk=pk)
    
    if request.method == "POST":
        # Only allow deleting unverified payments
        if payment.is_verified:
            messages.error(
                request,
                f"Cannot delete payment {payment.payment_number} - verified payments cannot be deleted"
            )
            return redirect("fees:payment_detail", pk=pk)
        
        payment_number = payment.payment_number
        payment.delete()
        messages.success(
            request,
            f"Payment {payment_number} was deleted successfully"
        )
        return redirect("fees:payment_list")
    
    return redirect("fees:payment_detail", pk=pk)


@login_required
def payment_detail(request, pk):
    """View payment details"""
    payment = get_object_or_404(
        Payment.objects.select_related(
            'student',
            'invoice',
            'payment_method',
            'academic_session',
            'fiscal_period'
        ),
        pk=pk
    )
    
    context = {
        'payment': payment,
    }
    
    return render(request, 'fees/payments/detail.html', context)


@login_required
def payment_verify(request, pk):
    """Verify a payment"""
    payment = get_object_or_404(Payment, pk=pk)
    
    if request.method == "POST":
        form = PaymentVerificationForm(request.POST, instance=payment)
        if form.is_valid():
            payment = form.save(commit=False)
            if payment.is_verified:
                payment.verification_date = timezone.now()
                # Set verified_by_id from request.user
            payment.save()
            
            messages.success(
                request,
                f"Payment {payment.payment_number} verification status updated"
            )
            return redirect("fees:payment_detail", pk=payment.pk)
    else:
        form = PaymentVerificationForm(instance=payment)
    
    context = {
        'form': form,
        'payment': payment,
        'title': 'Verify Payment',
    }
    return render(request, 'fees/payments/verify_form.html', context)


# =============================================================================
# SCHOLARSHIP PROGRAM VIEWS
# =============================================================================

@login_required
def scholarship_program_list(request):
    """List all scholarship programs - HTMX loads data on page load"""
    
    try:
        total_programs = ScholarshipProgram.objects.count()
        active_programs = ScholarshipProgram.objects.filter(is_active=True).count()
        accepting_programs = ScholarshipProgram.objects.filter(
            is_accepting_applications=True
        ).count()
        
        initial_stats = {
            'total_programs': total_programs,
            'active_programs': active_programs,
            'accepting_programs': accepting_programs,
        }
    except Exception as e:
        logger.error(f"Error getting scholarship program statistics: {e}")
        initial_stats = {}
    
    context = {
        'stats': initial_stats,
    }
    
    return render(request, 'fees/scholarships/programs/list.html', context)


@login_required
def scholarship_program_create(request):
    """Create a new scholarship program"""
    if request.method == "POST":
        form = ScholarshipProgramForm(request.POST)
        if form.is_valid():
            program = form.save()
            messages.success(
                request,
                f"Scholarship program '{program.name}' ({program.code}) was created successfully"
            )
            return redirect("fees:scholarship_program_detail", pk=program.pk)
    else:
        form = ScholarshipProgramForm()
    
    context = {
        'form': form,
        'title': 'Create Scholarship Program',
    }
    return render(request, 'fees/scholarships/programs/form.html', context)


@login_required
def scholarship_program_edit(request, pk):
    """Edit existing scholarship program"""
    program = get_object_or_404(ScholarshipProgram, pk=pk)
    
    if request.method == "POST":
        form = ScholarshipProgramForm(request.POST, instance=program)
        if form.is_valid():
            program = form.save()
            messages.success(
                request,
                f"Scholarship program '{program.name}' was updated successfully"
            )
            return redirect("fees:scholarship_program_detail", pk=program.pk)
    else:
        form = ScholarshipProgramForm(instance=program)
    
    context = {
        'form': form,
        'program': program,
        'title': 'Update Scholarship Program',
    }
    return render(request, 'fees/scholarships/programs/form.html', context)


@login_required
def scholarship_program_delete(request, pk):
    """Delete a scholarship program"""
    program = get_object_or_404(ScholarshipProgram, pk=pk)
    
    if request.method == "POST":
        # Check if program has applications
        if program.applications.exists():
            messages.error(
                request,
                f"Cannot delete program '{program.name}' - it has associated applications"
            )
            return redirect("fees:scholarship_program_detail", pk=pk)
        
        # Check if program has active scholarships
        if program.student_scholarships.exists():
            messages.error(
                request,
                f"Cannot delete program '{program.name}' - it has active scholarships"
            )
            return redirect("fees:scholarship_program_detail", pk=pk)
        
        program_name = program.name
        program_code = program.code
        program.delete()
        messages.success(
            request,
            f"Scholarship program '{program_name}' ({program_code}) was deleted successfully"
        )
        return redirect("fees:scholarship_program_list")
    
    return redirect("fees:scholarship_program_detail", pk=pk)


@login_required
def scholarship_program_detail(request, pk):
    """View scholarship program details with applications and statistics"""
    program = get_object_or_404(
        ScholarshipProgram.objects.prefetch_related(
            'applicable_fee_categories',
            'applicable_levels',
            'valid_sessions',
            Prefetch(
                'applications',
                queryset=StudentScholarshipApplication.objects.select_related('student')
            ),
            Prefetch(
                'student_scholarships',
                queryset=StudentScholarship.objects.select_related('student')
            ),
        ),
        pk=pk
    )
    
    # Get statistics
    total_applications = program.applications.count()
    pending_applications = program.applications.filter(
        status__in=['SUBMITTED', 'UNDER_REVIEW']
    ).count()
    approved_applications = program.applications.filter(
        status='APPROVED'
    ).count()
    
    active_scholarships = program.student_scholarships.filter(
        status='ACTIVE'
    ).count()
    
    total_awarded = program.student_scholarships.filter(
        status='ACTIVE'
    ).aggregate(total=Sum('amount_awarded'))['total'] or Decimal('0')
    
    total_used = program.student_scholarships.filter(
        status='ACTIVE'
    ).aggregate(total=Sum('total_amount_used'))['total'] or Decimal('0')
    
    context = {
        'program': program,
        'total_applications': total_applications,
        'pending_applications': pending_applications,
        'approved_applications': approved_applications,
        'active_scholarships': active_scholarships,
        'total_awarded': total_awarded,
        'total_used': total_used,
    }
    
    return render(request, 'fees/scholarships/programs/detail.html', context)

# =============================================================================
# STUDENT SCHOLARSHIP VIEWS
# =============================================================================

@login_required
def student_scholarship_list(request):
    """List all student scholarships - HTMX loads data on page load"""
    
    try:
        total_scholarships = StudentScholarship.objects.count()
        active_scholarships = StudentScholarship.objects.filter(
            status='ACTIVE'
        ).count()
        
        total_awarded = StudentScholarship.objects.filter(
            status='ACTIVE'
        ).aggregate(Sum('amount_awarded'))['amount_awarded__sum'] or Decimal('0')
        
        total_used = StudentScholarship.objects.filter(
            status='ACTIVE'
        ).aggregate(Sum('total_amount_used'))['total_amount_used__sum'] or Decimal('0')
        
        initial_stats = {
            'total_scholarships': total_scholarships,
            'active_scholarships': active_scholarships,
            'total_awarded': total_awarded,
            'total_used': total_used,
            'total_remaining': total_awarded - total_used,
        }
    except Exception as e:
        logger.error(f"Error getting scholarship statistics: {e}")
        initial_stats = {}
    
    context = {
        'stats': initial_stats,
    }
    
    return render(request, 'fees/scholarships/student_scholarships/list.html', context)


@login_required
def student_scholarship_create(request):
    """Create a new student scholarship"""
    if request.method == "POST":
        form = StudentScholarshipForm(request.POST)
        if form.is_valid():
            scholarship = form.save()
            messages.success(
                request,
                f"Scholarship awarded to {scholarship.student.get_full_name()}"
            )
            return redirect("fees:student_scholarship_detail", pk=scholarship.pk)
    else:
        form = StudentScholarshipForm()
    
    context = {
        'form': form,
        'title': 'Award Scholarship',
    }
    return render(request, 'fees/scholarships/student_scholarships/form.html', context)


@login_required
def student_scholarship_edit(request, pk):
    """Edit existing student scholarship"""
    scholarship = get_object_or_404(StudentScholarship, pk=pk)
    
    if request.method == "POST":
        form = StudentScholarshipForm(request.POST, instance=scholarship)
        if form.is_valid():
            scholarship = form.save()
            messages.success(
                request,
                f"Scholarship for {scholarship.student.get_full_name()} was updated"
            )
            return redirect("fees:student_scholarship_detail", pk=scholarship.pk)
    else:
        form = StudentScholarshipForm(instance=scholarship)
    
    context = {
        'form': form,
        'scholarship': scholarship,
        'title': 'Update Scholarship',
    }
    return render(request, 'fees/scholarships/student_scholarships/form.html', context)


@login_required
def student_scholarship_detail(request, pk):
    """View student scholarship details with usage history"""
    scholarship = get_object_or_404(
        StudentScholarship.objects.select_related(
            'student',
            'scholarship_program',
            'application'
        ).prefetch_related(
            Prefetch(
                'application_logs',
                queryset=ScholarshipApplicationLog.objects.select_related('invoice')
            ),
        ),
        pk=pk
    )
    
    # Calculate remaining balance
    remaining_balance = scholarship.amount_awarded - scholarship.total_amount_used
    
    # Get usage statistics
    total_applications = scholarship.application_logs.count()
    total_applied = scholarship.application_logs.aggregate(
        total=Sum('amount_applied')
    )['total'] or Decimal('0')
    
    context = {
        'scholarship': scholarship,
        'remaining_balance': remaining_balance,
        'total_applications': total_applications,
        'total_applied': total_applied,
    }
    
    return render(request, 'fees/scholarships/student_scholarships/detail.html', context)


# =============================================================================
# SCHOLARSHIP APPLICATION VIEWS
# =============================================================================

@login_required
def scholarship_application_list(request):
    """List all scholarship applications - HTMX loads data on page load"""
    
    try:
        total_applications = StudentScholarshipApplication.objects.count()
        pending_applications = StudentScholarshipApplication.objects.filter(
            status__in=['SUBMITTED', 'UNDER_REVIEW']
        ).count()
        approved_applications = StudentScholarshipApplication.objects.filter(
            status='APPROVED'
        ).count()
        rejected_applications = StudentScholarshipApplication.objects.filter(
            status='REJECTED'
        ).count()
        
        initial_stats = {
            'total_applications': total_applications,
            'pending_applications': pending_applications,
            'approved_applications': approved_applications,
            'rejected_applications': rejected_applications,
        }
    except Exception as e:
        logger.error(f"Error getting scholarship application statistics: {e}")
        initial_stats = {}
    
    context = {
        'stats': initial_stats,
    }
    
    return render(request, 'fees/scholarships/applications/list.html', context)


@login_required
def scholarship_application_create(request):
    """Create a new scholarship application"""
    if request.method == "POST":
        form = StudentScholarshipApplicationForm(request.POST)
        if form.is_valid():
            application = form.save(commit=False)
            # Number is auto-generated by signal, but can be overridden if needed
            if not application.application_number:
                application.application_number = generate_scholarship_application_number()
            application.save()
            form.save_m2m()
            
            messages.success(
                request,
                f"Application {application.application_number} submitted for {application.student.get_full_name()}"
            )
            return redirect("fees:scholarship_application_detail", pk=application.pk)
    else:
        form = StudentScholarshipApplicationForm()
    
    context = {
        'form': form,
        'title': 'Submit Scholarship Application',
    }
    return render(request, 'fees/scholarships/applications/form.html', context)


@login_required
def scholarship_application_detail(request, pk):
    """View scholarship application details"""
    application = get_object_or_404(
        StudentScholarshipApplication.objects.select_related(
            'student',
            'scholarship_program',
            'academic_session'
        ),
        pk=pk
    )
    
    context = {
        'application': application,
    }
    
    return render(request, 'fees/scholarships/applications/detail.html', context)


@login_required
def scholarship_application_review(request, pk):
    """Review scholarship application"""
    application = get_object_or_404(StudentScholarshipApplication, pk=pk)
    
    if request.method == "POST":
        form = ScholarshipApplicationReviewForm(request.POST, instance=application)
        if form.is_valid():
            application = form.save(commit=False)
            application.review_date = timezone.now()
            # Set reviewed_by_id from request.user
            application.save()
            
            messages.success(
                request,
                f"Application {application.application_number} review completed"
            )
            return redirect("fees:scholarship_application_detail", pk=application.pk)
    else:
        form = ScholarshipApplicationReviewForm(instance=application)
    
    context = {
        'form': form,
        'application': application,
        'title': 'Review Scholarship Application',
    }
    return render(request, 'fees/scholarships/applications/review_form.html', context)


# =============================================================================
# DISCOUNT VIEWS
# =============================================================================

@login_required
def discount_list(request):
    """List all discounts - HTMX loads data on page load"""
    
    try:
        total_discounts = FeesDiscount.objects.count()
        active_discounts = FeesDiscount.objects.filter(is_active=True).count()
        auto_apply_discounts = FeesDiscount.objects.filter(
            auto_apply=True
        ).count()
        
        initial_stats = {
            'total_discounts': total_discounts,
            'active_discounts': active_discounts,
            'auto_apply_discounts': auto_apply_discounts,
        }
    except Exception as e:
        logger.error(f"Error getting discount statistics: {e}")
        initial_stats = {}
    
    context = {
        'stats': initial_stats,
    }
    
    return render(request, 'fees/discounts/list.html', context)


@login_required
def discount_create(request):
    """Create a new discount"""
    if request.method == "POST":
        form = FeesDiscountForm(request.POST)
        if form.is_valid():
            discount = form.save()
            messages.success(
                request,
                f"Discount '{discount.name}' ({discount.code}) was created successfully"
            )
            return redirect("fees:discount_detail", pk=discount.pk)
    else:
        form = FeesDiscountForm()
    
    context = {
        'form': form,
        'title': 'Create Discount',
    }
    return render(request, 'fees/discounts/form.html', context)


@login_required
def discount_edit(request, pk):
    """Edit existing discount"""
    discount = get_object_or_404(FeesDiscount, pk=pk)
    
    if request.method == "POST":
        form = FeesDiscountForm(request.POST, instance=discount)
        if form.is_valid():
            discount = form.save()
            messages.success(
                request,
                f"Discount '{discount.name}' was updated successfully"
            )
            return redirect("fees:discount_detail", pk=discount.pk)
    else:
        form = FeesDiscountForm(instance=discount)
    
    context = {
        'form': form,
        'discount': discount,
        'title': 'Update Discount',
    }
    return render(request, 'fees/discounts/form.html', context)


@login_required
def discount_delete(request, pk):
    """Delete a discount"""
    discount = get_object_or_404(FeesDiscount, pk=pk)
    
    if request.method == "POST":
        # Check if discount has applications
        if discount.applications.exists():
            messages.error(
                request,
                f"Cannot delete discount '{discount.name}' - it has been applied to invoices"
            )
            return redirect("fees:discount_detail", pk=pk)
        
        discount_name = discount.name
        discount_code = discount.code
        discount.delete()
        messages.success(
            request,
            f"Discount '{discount_name}' ({discount_code}) was deleted successfully"
        )
        return redirect("fees:discount_list")
    
    return redirect("fees:discount_detail", pk=pk)


@login_required
def discount_detail(request, pk):
    """View discount details with usage statistics"""
    discount = get_object_or_404(
        FeesDiscount.objects.prefetch_related(
            'applicable_categories',
            'applicable_structures',
            Prefetch(
                'applications',
                queryset=DiscountApplication.objects.select_related('invoice', 'student')
            ),
        ),
        pk=pk
    )
    
    # Get usage statistics
    total_applications = discount.applications.count()
    total_amount = discount.applications.aggregate(
        total=Sum('discount_amount')
    )['total'] or Decimal('0')
    
    # Calculate remaining budget
    remaining_budget = None
    if discount.budget_limit:
        remaining_budget = discount.budget_limit - discount.current_budget_used
    
    # Calculate remaining usage
    remaining_usage = None
    if discount.max_usage_count:
        remaining_usage = discount.max_usage_count - discount.current_usage_count
    
    context = {
        'discount': discount,
        'total_applications': total_applications,
        'total_amount': total_amount,
        'remaining_budget': remaining_budget,
        'remaining_usage': remaining_usage,
    }
    
    return render(request, 'fees/discounts/detail.html', context)


# =============================================================================
# REFUND VIEWS
# =============================================================================

@login_required
def refund_list(request):
    """List all refunds - HTMX loads data on page load"""
    
    try:
        total_refunds = Refund.objects.count()
        pending_refunds = Refund.objects.filter(
            status__in=['REQUESTED', 'UNDER_REVIEW']
        ).count()
        approved_refunds = Refund.objects.filter(
            status__in=['APPROVED', 'PROCESSING', 'COMPLETED']
        ).count()
        
        total_amount = Refund.objects.filter(
            status='COMPLETED'
        ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
        
        initial_stats = {
            'total_refunds': total_refunds,
            'pending_refunds': pending_refunds,
            'approved_refunds': approved_refunds,
            'total_amount': total_amount,
        }
    except Exception as e:
        logger.error(f"Error getting refund statistics: {e}")
        initial_stats = {}
    
    context = {
        'stats': initial_stats,
    }
    
    return render(request, 'fees/refunds/list.html', context)


@login_required
def refund_create(request):
    """Create a new refund request"""
    if request.method == "POST":
        form = RefundForm(request.POST)
        if form.is_valid():
            refund = form.save(commit=False)
            # Number is auto-generated by signal, but can be overridden if needed
            if not refund.refund_number:
                refund.refund_number = generate_refund_number()
            refund.save()
            
            messages.success(
                request,
                f"Refund request {refund.refund_number} created for {refund.student.get_full_name()}"
            )
            return redirect("fees:refund_detail", pk=refund.pk)
    else:
        form = RefundForm()
    
    context = {
        'form': form,
        'title': 'Create Refund Request',
    }
    return render(request, 'fees/refunds/form.html', context)


@login_required
def refund_edit(request, pk):
    """Edit existing refund request"""
    refund = get_object_or_404(Refund, pk=pk)
    
    # Only allow editing requested refunds
    if refund.status != 'REQUESTED':
        messages.error(
            request,
            f"Cannot edit refund {refund.refund_number} - only requested refunds can be edited"
        )
        return redirect("fees:refund_detail", pk=pk)
    
    if request.method == "POST":
        form = RefundForm(request.POST, instance=refund)
        if form.is_valid():
            refund = form.save()
            messages.success(
                request,
                f"Refund request {refund.refund_number} was updated successfully"
            )
            return redirect("fees:refund_detail", pk=refund.pk)
    else:
        form = RefundForm(instance=refund)
    
    context = {
        'form': form,
        'refund': refund,
        'title': 'Update Refund Request',
    }
    return render(request, 'fees/refunds/form.html', context)


@login_required
def refund_delete(request, pk):
    """Delete a refund request"""
    refund = get_object_or_404(Refund, pk=pk)
    
    if request.method == "POST":
        # Only allow deleting requested refunds
        if refund.status != 'REQUESTED':
            messages.error(
                request,
                f"Cannot delete refund {refund.refund_number} - only requested refunds can be deleted"
            )
            return redirect("fees:refund_detail", pk=pk)
        
        refund_number = refund.refund_number
        refund.delete()
        messages.success(
            request,
            f"Refund request {refund_number} was deleted successfully"
        )
        return redirect("fees:refund_list")
    
    return redirect("fees:refund_detail", pk=pk)


@login_required
def refund_detail(request, pk):
    """View refund details"""
    refund = get_object_or_404(
        Refund.objects.select_related(
            'student',
            'invoice',
            'payment',
            'academic_session',
            'fiscal_period',
            'payment_method'
        ),
        pk=pk
    )
    
    context = {
        'refund': refund,
    }
    
    return render(request, 'fees/refunds/detail.html', context)


@login_required
def refund_approve(request, pk):
    """Approve or reject refund request"""
    refund = get_object_or_404(Refund, pk=pk)
    
    if request.method == "POST":
        form = RefundApprovalForm(request.POST, instance=refund)
        if form.is_valid():
            refund = form.save(commit=False)
            refund.review_date = timezone.now()
            # Set reviewed_by_id and approved_by_id from request.user
            if refund.status == 'APPROVED':
                refund.approval_date = timezone.now()
            refund.save()
            
            messages.success(
                request,
                f"Refund request {refund.refund_number} review completed"
            )
            return redirect("fees:refund_detail", pk=refund.pk)
    else:
        form = RefundApprovalForm(instance=refund)
    
    context = {
        'form': form,
        'refund': refund,
        'title': 'Review Refund Request',
    }
    return render(request, 'fees/refunds/approval_form.html', context)