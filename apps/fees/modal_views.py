# fees/modal_views.py

"""
Modal Views for Fees Management

These views return HTML fragments for modals loaded via HTMX.
Each modal view is paired with an action view in views.py that handles the POST request.

Pattern:
1. GET request → modal_views.py (loads modal HTML)
2. POST request → views.py (processes action, returns response with headers)

"""

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.http import HttpResponse
from decimal import Decimal
from django.db.models import Q, Sum, Count
import logging

from .models import (
    DisplayGroup,
    FeesCategory,
    FeesStructure,
    FeesStructureItem,
    FeeInvoice,
    Payment,
    ScholarshipProgram,
    StudentScholarship,
    StudentScholarshipApplication,
    DiscountPolicy,
    DiscountApplication,
    StudentDiscount,          
    StudentAccount,
    AccountTransaction,
)

from core.utils import get_school_today

logger = logging.getLogger(__name__)


# =============================================================================
# DISPLAY GROUP MODALS
# =============================================================================

@login_required
def display_group_delete_modal(request, pk):
    """Return delete confirmation modal content via HTMX."""
    group          = get_object_or_404(DisplayGroup, pk=pk)
    category_count = group.feescategory_set.count()

    return render(request, 'fees/display_groups/modals/delete_group.html', {
        'group':          group,
        'can_delete':     category_count == 0,
        'category_count': category_count,
    })


@login_required
def display_group_toggle_active_modal(request, pk):
    """Modal for confirming display group active-status toggle."""
    group = get_object_or_404(DisplayGroup, pk=pk)

    return render(request, 'fees/display_groups/modals/toggle_active.html', {
        'group':      group,
        'new_status': 'activate' if not group.is_active else 'deactivate',
    })


# =============================================================================
# FEE CATEGORY MODALS
# =============================================================================

@login_required
def fee_category_delete_modal(request, pk):
    """Return delete confirmation modal content via HTMX."""
    category        = get_object_or_404(FeesCategory, pk=pk)
    structure_count = category.structure_items.count()
    invoice_count   = category.invoice_items.count()

    return render(request, 'fees/categories/modals/delete_category.html', {
        'category':       category,
        'can_delete':     structure_count == 0 and invoice_count == 0,
        'structure_count': structure_count,
        'invoice_count':  invoice_count,
    })


@login_required
def fee_category_toggle_active_modal(request, pk):
    """Modal for confirming fee category active-status toggle."""
    category = get_object_or_404(FeesCategory, pk=pk)

    return render(request, 'fees/categories/modals/toggle_active.html', {
        'category':   category,
        'new_status': 'activate' if not category.is_active else 'deactivate',
    })


# =============================================================================
# FEE STRUCTURE MODALS
# =============================================================================

@login_required
def fee_structure_delete_modal(request, pk):
    """Return delete confirmation modal content via HTMX."""
    structure     = get_object_or_404(FeesStructure, pk=pk)
    invoice_count = structure.invoices.count()

    return render(request, 'fees/structures/modals/delete_structure.html', {
        'structure':          structure,
        'can_delete':         invoice_count == 0,
        'invoice_count':      invoice_count,
        'has_active_warning': structure.is_active,
        'item_count':         structure.items.count(),
    })


@login_required
def fee_structure_clone_modal(request, pk):
    """Modal for cloning fee structure."""
    structure = get_object_or_404(
        FeesStructure.objects.prefetch_related(
            'academic_levels', 'applicable_sessions',
            'applicable_classes', 'items__fee_category',
        ),
        pk=pk,
    )

    return render(request, 'fees/structures/modals/clone_structure.html', {
        'structure':     structure,
        'item_count':    structure.items.count(),
        'level_count':   structure.academic_levels.count(),
        'session_count': structure.applicable_sessions.count(),
        'class_count':   structure.applicable_classes.count(),
    })


@login_required
def fee_structure_activate_modal(request, pk):
    """Modal for activating fee structure."""
    structure    = get_object_or_404(FeesStructure, pk=pk)
    warnings     = []
    can_activate = True

    if not structure.items.exists():
        can_activate = False
        warnings.append("Structure has no fee items defined")

    if not structure.academic_levels.exists():
        can_activate = False
        warnings.append("No academic levels assigned")

    if not structure.applicable_sessions.exists():
        can_activate = False
        warnings.append("No academic sessions assigned")

    if not structure.is_active:
        overlapping = FeesStructure.objects.filter(
            is_active=True,
            structure_type=structure.structure_type,
            academic_levels__in=structure.academic_levels.all(),
            applicable_sessions__in=structure.applicable_sessions.all(),
        ).exclude(pk=structure.pk).distinct()

        if overlapping.exists():
            warnings.append(
                f"There are {overlapping.count()} active structure(s) "
                f"with overlapping levels/sessions"
            )

    return render(request, 'fees/structures/modals/activate_structure.html', {
        'structure':    structure,
        'can_activate': can_activate,
        'warnings':     warnings,
    })


@login_required
def fee_structure_deactivate_modal(request, pk):
    """Modal for deactivating fee structure."""
    structure      = get_object_or_404(FeesStructure, pk=pk)
    active_invoices = structure.invoices.filter(
        status__in=['PENDING', 'PARTIALLY_PAID']
    ).count()

    return render(request, 'fees/structures/modals/deactivate_structure.html', {
        'structure':      structure,
        'active_invoices': active_invoices,
    })


@login_required
def fee_structure_quick_view_modal(request, pk):
    """Quick view modal showing structure summary."""
    structure = get_object_or_404(
        FeesStructure.objects.prefetch_related(
            'academic_levels', 'applicable_sessions',
            'applicable_classes__academic_level',
            'items__fee_category__display_group',
        ),
        pk=pk,
    )

    items        = structure.items.select_related('fee_category__display_group').order_by(
        'fee_category__display_group__display_order',
        'fee_category__display_order',
    )
    total_amount = sum(item.amount for item in items)
    total_tax    = sum((item.amount * item.tax_percentage / 100) for item in items)

    return render(request, 'fees/structures/modals/structure_quick_view.html', {
        'structure':            structure,
        'items':                items,
        'total_amount':         total_amount,
        'total_tax':            total_tax,
        'total_with_tax':       total_amount + total_tax,
        'invoice_count':        structure.invoices.count(),
        'active_invoice_count': structure.invoices.filter(status__in=['PENDING', 'PARTIALLY_PAID']).count(),
    })


# =============================================================================
# FEE INVOICE MODALS
# =============================================================================

@login_required
def invoice_void_modal(request, pk):
    """Modal to void/cancel an invoice."""
    invoice  = get_object_or_404(FeeInvoice, pk=pk)
    can_void = True
    warnings = []

    if invoice.status in ['VOID', 'CANCELLED']:
        can_void = False
        warnings.append("Invoice is already voided/cancelled")

    if invoice.status == 'PAID':
        can_void = False
        warnings.append("Cannot void paid invoices — use refund instead")

    if invoice.paid_amount > 0:
        warnings.append(
            f"Invoice has payments totalling {invoice.paid_amount:,.2f} — "
            f"these will need to be handled"
        )

    return render(request, 'fees/invoices/modals/void_invoice.html', {
        'invoice':  invoice,
        'can_void': can_void,
        'warnings': warnings,
    })


@login_required
def invoice_delete_modal(request, pk):
    """Return delete confirmation modal content via HTMX."""
    invoice  = get_object_or_404(FeeInvoice, pk=pk)
    can_delete = True
    warnings   = []

    if invoice.status in ['VOID', 'CANCELLED']:
        can_delete = True
        warnings.append(
            f"This is a {invoice.get_status_display()} invoice with no financial "
            f"impact — safe to delete"
        )
    elif invoice.status == 'PAID':
        can_delete = False
        warnings.append("Cannot delete paid invoices")
    elif invoice.status == 'PARTIALLY_PAID':
        can_delete = False
        warnings.append("Invoice has payments — cannot delete")
    elif invoice.status not in ['DRAFT', 'VOID', 'CANCELLED']:
        can_delete = False
        warnings.append(
            f"Invoice is {invoice.get_status_display()} — "
            f"can only delete DRAFT, VOID, or CANCELLED invoices"
        )

    payment_count = invoice.payments.count()
    if payment_count > 0:
        can_delete = False
        warnings.append(f"Invoice has {payment_count} payment(s)")

    if invoice.paid_amount > 0:
        can_delete = False
        warnings.append(f"Invoice has received payments totalling {invoice.paid_amount:,.2f}")

    scholarship_count = invoice.scholarship_application_logs.filter(is_reversed=False).count()
    if scholarship_count > 0:
        warnings.append(
            f"Invoice has {scholarship_count} scholarship application(s)"
            + (" (will be removed with invoice)" if invoice.status == 'VOID' else "")
        )

    discount_count = invoice.discount_applications.count()
    if discount_count > 0:
        warnings.append(
            f"Invoice has {discount_count} discount application(s)"
            + (" (will be removed with invoice)" if invoice.status == 'VOID' else "")
        )

    if invoice.journal_entry_id:
        if invoice.journal_entry.status == 'POSTED':
            can_delete = False
            warnings.append(
                f"Journal entry {invoice.journal_entry.entry_number} is POSTED — cannot delete"
            )
        elif invoice.status in ['VOID', 'CANCELLED']:
            warnings.append(
                "⚠️ VOID invoice should not have a journal entry — "
                "will be cleaned up during deletion"
            )

    return render(request, 'fees/invoices/modals/delete_invoice.html', {
        'invoice':    invoice,
        'can_delete': can_delete,
        'warnings':   warnings,
    })


@login_required
def invoice_quick_view_modal(request, pk):
    """Quick view modal for invoice."""
    invoice = get_object_or_404(
        FeeInvoice.objects.select_related(
            'student', 'academic_session', 'fee_structure'
        ).prefetch_related('items__fee_category'),
        pk=pk,
    )

    return render(request, 'fees/invoices/modals/invoice_quick_view.html', {
        'invoice': invoice,
    })


@login_required
def invoice_finalize_modal(request, pk):
    """Modal to confirm invoice finalization."""
    invoice      = get_object_or_404(FeeInvoice, pk=pk)
    can_finalize = invoice.status == 'DRAFT'
    warnings     = []
    info         = []

    if not can_finalize:
        warnings.append(f"Invoice is already {invoice.get_status_display()}")
    else:
        info.append("Finalizing will:")
        info.append("• Change invoice status to PENDING")

        if invoice.journal_entry_id:
            je = invoice.journal_entry
            info.append("• Update and post the journal entry to General Ledger")
            info.append(f"• Journal Entry: {je.entry_number} (currently {je.status})")
        else:
            info.append("• Create and post journal entry to General Ledger")
            info.append("• Journal Entry: Will be created during finalization")

        info.append("• Allow payments to be received")
        info.append("• Lock invoice from major modifications")

    return render(request, 'fees/invoices/modals/finalize_invoice.html', {
        'invoice':      invoice,
        'can_finalize': can_finalize,
        'warnings':     warnings,
        'info':         info,
    })

@login_required
@require_http_methods(["GET"])
def invoice_bulk_finalize_modal(request):
    """
    Modal to preview and confirm bulk finalization.

    Accepts either:
      • ?pk=1&pk=2&pk=3        — explicit PKs from bulk selection
      • ?all_draft_pages=1     — sentinel: resolve all DRAFTs server-side
        (+ any active search filter params carried by hx-include="#searchForm")
    """
    from fees.models import FeeInvoice

    all_draft_pages = request.GET.get('all_draft_pages')

    if all_draft_pages:
        invoices = list(
            FeeInvoice.objects
            .filter(status='DRAFT')
            .select_related('student', 'academic_session', 'fiscal_period')
            .order_by('student__last_name')
        )
        pks = [inv.pk for inv in invoices]
    else:
        pks = request.GET.getlist('pk')
        if not pks:
            return HttpResponse(
                '<div class="alert alert-danger m-3">No invoices selected.</div>'
            )
        invoices = list(
            FeeInvoice.objects
            .filter(pk__in=pks, status='DRAFT')
            .select_related('student', 'academic_session', 'fiscal_period')
            .order_by('student__last_name')
        )

    eligible   = []
    ineligible = []

    for invoice in invoices:
        if invoice.status != 'DRAFT':
            ineligible.append({
                'invoice': invoice,
                'reason':  f"Status is {invoice.get_status_display()}, not DRAFT",
            })
        elif (invoice.fiscal_period and
              hasattr(invoice.fiscal_period, 'is_closed') and
              invoice.fiscal_period.is_closed):
            ineligible.append({
                'invoice': invoice,
                'reason':  f"Fiscal period {invoice.fiscal_period.name} is closed",
            })
        else:
            eligible.append(invoice)

    zero_count  = sum(1 for inv in eligible if inv.total_amount <= 0)
    total_amount = sum(inv.total_amount for inv in eligible)

    steps = [
        "Change each invoice status from DRAFT to PENDING",
        "Create and post a journal entry to the General Ledger for each invoice",
        "Record a debt charge on each student's account",
    ]
    if zero_count:
        steps.append(
            f"{zero_count} zero-amount invoice{'s' if zero_count > 1 else ''} "
            f"will be finalized without a journal entry"
        )

    return render(request, 'fees/invoices/modals/bulk_finalize_invoices.html', {
        'eligible':        eligible,
        'ineligible':      ineligible,
        'pks':             [inv.pk for inv in eligible],
        'all_draft_pages': bool(all_draft_pages),
        'total_amount':    total_amount,
        'zero_count':      zero_count,
        'steps':           steps,
    })

@login_required
def invoice_revert_to_draft_modal(request, pk):
    """Modal to confirm reverting invoice to DRAFT."""
    invoice = get_object_or_404(
        FeeInvoice.objects.select_related(
            'student', 'fiscal_period', 'journal_entry',
        ),
        pk=pk,
    )

    can_revert = True
    warnings   = []

    if invoice.status != 'PENDING':
        can_revert = False
        warnings.append(
            f"Invoice status is {invoice.get_status_display()}, not PENDING"
        )

    payment_count = invoice.payments.filter(
        status='COMPLETED', reversed=False, refunded=False,
    ).count()
    if payment_count > 0:
        can_revert = False
        warnings.append(
            f"Invoice has {payment_count} active payment{'s' if payment_count > 1 else ''} "
            f"totalling {invoice.paid_amount:,.2f}"
        )

    if invoice.fiscal_period and invoice.fiscal_period.is_closed:
        can_revert = False
        warnings.append(
            f"Fiscal period {invoice.fiscal_period.name} is closed"
        )

    journal_posted = (
        invoice.journal_entry_id and
        invoice.journal_entry.status == 'POSTED'
    )

    return render(request, 'fees/invoices/modals/revert_to_draft.html', {
        'invoice':        invoice,
        'can_revert':     can_revert,
        'warnings':       warnings,
        'journal_posted': journal_posted,
        'payment_count':  payment_count,
    })


@login_required
def send_payment_reminder_modal(request, pk):
    """Modal to send payment reminder for an overdue invoice."""
    invoice      = get_object_or_404(FeeInvoice, pk=pk)
    today        = get_school_today()
    is_overdue   = (
        invoice.due_date < today and
        invoice.status in ['PENDING', 'PARTIALLY_PAID', 'OVERDUE']
    )
    days_overdue = (today - invoice.due_date).days if is_overdue else 0

    return render(request, 'fees/invoices/modals/send_payment_reminder.html', {
        'invoice':      invoice,
        'is_overdue':   is_overdue,
        'days_overdue': days_overdue,
        'today':        today,
    })


@login_required
def invoice_send_email_modal(request, pk):
    """Modal for sending invoice via email."""
    invoice       = get_object_or_404(FeeInvoice, pk=pk)
    student_email = invoice.student.email if hasattr(invoice.student, 'email') else None
    parent_emails = []
    if hasattr(invoice.student, 'parents'):
        parent_emails = [
            p.email for p in invoice.student.parents.all()
            if hasattr(p, 'email') and p.email
        ]

    return render(request, 'fees/invoices/modals/send_email.html', {
        'invoice':       invoice,
        'student_email': student_email,
        'parent_emails': parent_emails,
    })


@login_required
def invoice_apply_penalty_modal(request, pk):
    """Modal for manually applying a late-payment penalty to an invoice."""
    invoice      = get_object_or_404(FeeInvoice, pk=pk)
    today        = get_school_today()
    is_overdue   = (
        invoice.due_date < today and
        invoice.status in ['PENDING', 'PARTIALLY_PAID', 'OVERDUE']
    )

    return render(request, 'fees/invoices/modals/apply_penalty.html', {
        'invoice':      invoice,
        'is_overdue':   is_overdue,
        'days_overdue': (today - invoice.due_date).days if is_overdue else 0,
    })


@login_required
def invoice_waive_late_fees_modal(request, pk):
    """Modal for waiving late fees on an invoice."""
    invoice = get_object_or_404(FeeInvoice, pk=pk)

    return render(request, 'fees/invoices/modals/waive_late_fees.html', {
        'invoice':       invoice,
        'has_late_fees': invoice.late_fee_amount > 0,
    })


@login_required
def invoice_adjust_amount_modal(request, pk):
    """Modal for making an amount adjustment to an invoice."""
    invoice = get_object_or_404(FeeInvoice, pk=pk)

    return render(request, 'fees/invoices/modals/adjust_amount.html', {
        'invoice':    invoice,
        'can_adjust': invoice.status not in ['PAID', 'VOID', 'CANCELLED'],
    })


# =============================================================================
# PAYMENT MODALS
# =============================================================================

@login_required
def payment_reverse_modal(request, pk):
    """
    Modal for reversing a payment — handles both GET (show form) and
    POST (process reversal).
    """
    payment = get_object_or_404(Payment, pk=pk)
    can_reverse, reason = payment.can_be_reversed()

    if request.method == 'POST':
        if not can_reverse:
            r = HttpResponse()
            r['HX-Alert-Message'] = reason
            r['HX-Alert-Type']    = 'error'
            r['HX-Close-Modal']   = 'true'
            return r

        reversal_reason = request.POST.get('reason', '').strip()
        if not reversal_reason:
            return render(request, 'fees/payments/modals/reverse_payment.html', {
                'payment':       payment,
                'can_reverse':   can_reverse,
                'reason':        reason,
                'error_message': 'Reversal reason is required',
            })

        try:
            payment.reverse(reason=reversal_reason, reversed_by=request.user)
            r = HttpResponse()
            r['HX-Alert-Message'] = f'Payment {payment.payment_number} reversed successfully'
            r['HX-Alert-Type']    = 'success'
            r['HX-Alert-Title']   = 'Payment Reversed'
            r['HX-Close-Modal']   = 'true'
            r['HX-Trigger']       = 'refreshPaymentList'
            return r
        except Exception as e:
            logger.error(f"Error reversing payment {payment.pk}: {e}", exc_info=True)
            return render(request, 'fees/payments/modals/reverse_payment.html', {
                'payment':       payment,
                'can_reverse':   can_reverse,
                'reason':        reason,
                'error_message': f'Error reversing payment: {str(e)}',
            })

    return render(request, 'fees/payments/modals/reverse_payment.html', {
        'payment':     payment,
        'can_reverse': can_reverse,
        'reason':      reason,
    })


@login_required
def payment_refund_modal(request, pk):
    """Return payment refund modal with form via HTMX."""
    payment              = get_object_or_404(Payment, pk=pk)
    can_refund, reason   = payment.can_be_refunded()

    return render(request, 'fees/payments/modals/refund_payment.html', {
        'payment':    payment,
        'can_refund': can_refund,
        'reason':     reason if not can_refund else None,
    })


@login_required
def payment_verify_modal(request, pk):
    """Modal for payment verification."""
    payment  = get_object_or_404(Payment, pk=pk)
    warnings = []

    if payment.is_verified:
        warnings.append("Payment is already verified")
    if payment.status == 'FAILED':
        warnings.append("Payment is marked as failed")

    return render(request, 'fees/payments/modals/verify_payment.html', {
        'payment':    payment,
        'can_verify': not payment.is_verified,
        'warnings':   warnings,
    })


@login_required
def payment_delete_modal(request, pk):
    """Return delete confirmation modal content via HTMX."""
    payment    = get_object_or_404(Payment, pk=pk)
    can_delete = True
    warnings   = []

    if payment.is_verified:
        can_delete = False
        warnings.append("Cannot delete verified payments")
    if payment.status == 'COMPLETED':
        warnings.append("Payment has been completed")
    if payment.invoice and payment.invoice.status == 'PAID':
        warnings.append("Invoice is marked as PAID — deletion will affect invoice status")

    return render(request, 'fees/payments/modals/delete_payment.html', {
        'payment':    payment,
        'can_delete': can_delete,
        'warnings':   warnings,
    })


@login_required
def payment_quick_view_modal(request, pk):
    """Quick view modal for payment."""
    payment = get_object_or_404(
        Payment.objects.select_related('student', 'invoice', 'payment_method'),
        pk=pk,
    )

    return render(request, 'fees/payments/modals/payment_quick_view.html', {
        'payment': payment,
    })


@login_required
def bulk_payment_verification_modal(request):
    """Modal for bulk payment verification."""
    unverified_payments = Payment.objects.filter(
        is_verified=False, status='COMPLETED'
    ).select_related('student', 'payment_method').order_by('-payment_date')[:50]

    return render(request, 'fees/payments/modals/bulk_verify_payments.html', {
        'unverified_payments': unverified_payments,
        'total_amount':        sum(p.amount for p in unverified_payments),
    })


@login_required
def payment_send_receipt_modal(request, pk):
    """Modal for sending payment receipt via email."""
    payment       = get_object_or_404(Payment, pk=pk)
    student_email = payment.student.email if hasattr(payment.student, 'email') else None

    return render(request, 'fees/payments/modals/send_receipt.html', {
        'payment':       payment,
        'student_email': student_email,
        'paid_by_email': payment.paid_by_email,
    })


# =============================================================================
# SCHOLARSHIP PROGRAM MODALS
# =============================================================================

@login_required
def scholarship_program_delete_modal(request, pk):
    """Return delete confirmation modal content via HTMX."""
    program          = get_object_or_404(ScholarshipProgram, pk=pk)
    active_count     = program.student_scholarships.filter(status='ACTIVE').count()
    application_count = program.applications.count()
    warnings         = []

    if active_count > 0:
        warnings.append(f"Program has {active_count} active scholarships")
    if application_count > 0:
        warnings.append(f"Program has {application_count} applications")
    if program.is_accepting_applications:
        warnings.append("Program is currently accepting applications")

    return render(request, 'fees/scholarships/modals/delete_program.html', {
        'program':    program,
        'can_delete': active_count == 0,
        'warnings':   warnings,
    })


@login_required
def scholarship_program_activate_modal(request, pk):
    """Return activation confirmation modal content via HTMX."""
    program = get_object_or_404(ScholarshipProgram, pk=pk)

    return render(request, 'fees/scholarships/modals/activate_program.html', {
        'program': program,
    })


@login_required
def scholarship_program_deactivate_modal(request, pk):
    """Return deactivation confirmation modal content via HTMX."""
    program = get_object_or_404(ScholarshipProgram, pk=pk)

    return render(request, 'fees/scholarships/modals/deactivate_program.html', {
        'program':             program,
        'active_scholarships': program.student_scholarships.filter(status='ACTIVE').count(),
        'pending_applications': program.applications.filter(
            status__in=['SUBMITTED', 'UNDER_REVIEW']
        ).count(),
    })


# =============================================================================
# SCHOLARSHIP APPLICATION MODALS
# =============================================================================

@login_required
def scholarship_application_approve_modal(request, pk):
    """Return application approval modal with form via HTMX."""
    application = get_object_or_404(StudentScholarshipApplication, pk=pk)

    return render(request, 'fees/scholarships/modals/approve_application.html', {
        'application': application,
        'can_approve': application.status in ['SUBMITTED', 'UNDER_REVIEW'],
    })


@login_required
def scholarship_application_reject_modal(request, pk):
    """Return application rejection modal with reason input via HTMX."""
    application = get_object_or_404(StudentScholarshipApplication, pk=pk)

    return render(request, 'fees/scholarships/modals/reject_application.html', {
        'application': application,
    })


@login_required
def scholarship_application_delete_modal(request, pk):
    """Return delete confirmation modal content via HTMX."""
    application = get_object_or_404(StudentScholarshipApplication, pk=pk)

    return render(request, 'fees/scholarships/modals/delete_application.html', {
        'application': application,
        'can_delete':  application.status != 'APPROVED',
    })


@login_required
def scholarship_application_history_modal(request, pk):
    """Modal showing application status history."""
    application = get_object_or_404(StudentScholarshipApplication, pk=pk)
    history     = []
    if hasattr(application, 'logs'):
        history = application.logs.order_by('-created_at')

    return render(request, 'fees/scholarships/modals/application_history.html', {
        'application': application,
        'history':     history,
    })


# =============================================================================
# STUDENT SCHOLARSHIP MODALS
# =============================================================================

@login_required
def student_scholarship_suspend_modal(request, pk):
    """Modal to suspend student scholarship."""
    scholarship = get_object_or_404(StudentScholarship, pk=pk)

    return render(request, 'fees/scholarships/modals/suspend_scholarship.html', {
        'scholarship': scholarship,
        'can_suspend': scholarship.status == 'ACTIVE',
    })


@login_required
def student_scholarship_terminate_modal(request, pk):
    """Modal to terminate student scholarship."""
    scholarship = get_object_or_404(StudentScholarship, pk=pk)

    return render(request, 'fees/scholarships/modals/terminate_scholarship.html', {
        'scholarship':   scholarship,
        'can_terminate': scholarship.status in ['ACTIVE', 'SUSPENDED'],
    })


@login_required
def student_scholarship_reactivate_modal(request, pk):
    """Modal to reactivate a suspended student scholarship."""
    scholarship = get_object_or_404(StudentScholarship, pk=pk)

    return render(request, 'fees/scholarships/modals/reactivate_scholarship.html', {
        'scholarship':    scholarship,
        'can_reactivate': scholarship.status == 'SUSPENDED',
    })


@login_required
def student_scholarship_complete_modal(request, pk):
    """Modal to mark student scholarship as completed."""
    scholarship = get_object_or_404(StudentScholarship, pk=pk)
    today       = get_school_today()
    term_ended  = bool(scholarship.end_date and today >= scholarship.end_date)

    return render(request, 'fees/scholarships/modals/complete_scholarship.html', {
        'scholarship':  scholarship,
        'can_complete': scholarship.status == 'ACTIVE',
        'term_ended':   term_ended,
    })


@login_required
def student_scholarship_delete_modal(request, pk):
    """Return delete confirmation modal content via HTMX."""
    scholarship = get_object_or_404(StudentScholarship, pk=pk)
    warnings    = []
    can_delete  = True

    if scholarship.status == 'ACTIVE':
        can_delete = False
        warnings.append("Cannot delete active scholarships — suspend or terminate first")

    log_count = scholarship.application_logs.filter(is_reversed=False).count()
    if log_count > 0:
        warnings.append(f"Scholarship has been applied to {log_count} invoice(s)")

    return render(request, 'fees/scholarships/modals/delete_scholarship.html', {
        'scholarship': scholarship,
        'can_delete':  can_delete,
        'warnings':    warnings,
    })


# =============================================================================
# DISCOUNT MODALS  (DiscountPolicy + StudentDiscount + DiscountApplication)
# =============================================================================

@login_required
def discount_delete_modal(request, pk):
    """Return delete confirmation modal content via HTMX."""
    policy            = get_object_or_404(DiscountPolicy, pk=pk)
    application_count = DiscountApplication.objects.filter(
        student_discount__policy=policy
    ).count()
    active_awards = policy.student_awards.filter(status='ACTIVE').count()
    warnings      = []
    can_delete    = True

    if application_count > 0:
        warnings.append(f"Policy has been applied {application_count} time(s)")
        if application_count > 10:
            can_delete = False

    if active_awards > 0:
        warnings.append(f"Policy has {active_awards} active student award(s)")
        can_delete = False

    if policy.is_active:
        warnings.append("Policy is currently active")

    return render(request, 'fees/discounts/modals/delete_discount.html', {
        'policy':            policy,
        'can_delete':        can_delete,
        'warnings':          warnings,
        'application_count': application_count,
        'active_awards':     active_awards,
    })


@login_required
def discount_toggle_active_modal(request, pk):
    """Modal to toggle DiscountPolicy active status."""
    policy        = get_object_or_404(DiscountPolicy, pk=pk)
    active_awards = policy.student_awards.filter(status='ACTIVE').count()
    warnings      = []

    if policy.is_active and active_awards > 0:
        warnings.append(
            f"Deactivating will prevent this policy from being auto-applied, "
            f"but {active_awards} existing award(s) will not be affected"
        )

    return render(request, 'fees/discounts/modals/toggle_active.html', {
        'policy':        policy,
        'new_status':    'activate' if not policy.is_active else 'deactivate',
        'active_awards': active_awards,
        'warnings':      warnings,
    })


@login_required
def apply_discount_to_invoice_modal(request, invoice_pk, discount_pk=None):
    """
    Modal for manually applying a DiscountPolicy to a specific invoice.
    Shows available policies and previews the calculated discount amount.
    """
    invoice         = get_object_or_404(FeeInvoice, pk=invoice_pk)
    policy          = None
    can_apply       = True
    warnings        = []
    discount_amount = None
    today           = get_school_today()

    if discount_pk:
        policy = get_object_or_404(DiscountPolicy, pk=discount_pk)

    # ── Invoice-level checks ──────────────────────────────────────────────────
    if invoice.status in ['PAID', 'VOID', 'CANCELLED']:
        can_apply = False
        warnings.append(f"Cannot apply discount to a {invoice.get_status_display()} invoice")

    if invoice.balance <= Decimal('0.00'):
        can_apply = False
        warnings.append("Invoice balance is zero — nothing to discount")

    # ── Policy-level checks ───────────────────────────────────────────────────
    if policy:
        if not policy.is_active:
            can_apply = False
            warnings.append("Discount policy is not active")

        if policy.valid_from and today < policy.valid_from:
            can_apply = False
            warnings.append(
                f"Policy period has not started yet (opens {policy.valid_from})"
            )

        if policy.valid_until and today > policy.valid_until:
            can_apply = False
            warnings.append(
                f"Policy period has ended (expired {policy.valid_until})"
            )

        if policy.total_budget is not None:
            remaining_budget = policy.total_budget - (policy.budget_used or Decimal('0.00'))
            if remaining_budget <= Decimal('0.00'):
                can_apply = False
                warnings.append("Policy budget is exhausted")
            elif remaining_budget < invoice.balance:
                warnings.append(
                    f"Only {remaining_budget:,.2f} remaining in policy budget"
                )

        if policy.max_beneficiaries is not None:
            current_awards = policy.student_awards.filter(status='ACTIVE').count()
            if current_awards >= policy.max_beneficiaries:
                can_apply = False
                warnings.append(
                    f"Maximum beneficiaries ({policy.max_beneficiaries}) already reached"
                )

        if policy.max_discount_per_student:
            already_given = DiscountApplication.objects.filter(
                student_discount__student=invoice.student,
                student_discount__policy=policy,
                is_reversed=False,
            ).aggregate(total=Sum('amount_discounted'))['total'] or Decimal('0.00')
            remaining_cap = policy.max_discount_per_student - already_given
            if remaining_cap <= Decimal('0.00'):
                can_apply = False
                warnings.append(
                    f"Per-student cap of {policy.max_discount_per_student:,.2f} already reached "
                    f"({already_given:,.2f} previously given)"
                )

        # ── Preview discount amount ───────────────────────────────────────────
        if policy.value_mode == 'FLAT_PERCENTAGE' and policy.flat_percentage:
            discount_amount = (
                invoice.subtotal_amount * policy.flat_percentage / Decimal('100')
            ).quantize(Decimal('0.01'))
        elif policy.value_mode == 'FLAT_FIXED' and policy.flat_fixed_amount:
            discount_amount = policy.flat_fixed_amount
        elif policy.value_mode == 'FLAT_WAIVER':
            discount_amount = invoice.balance
        else:
            discount_amount = Decimal('0.00')

        # Apply caps
        discount_amount = min(discount_amount, invoice.balance)
        if policy.max_discount_per_student:
            already_given   = DiscountApplication.objects.filter(
                student_discount__student=invoice.student,
                student_discount__policy=policy,
                is_reversed=False,
            ).aggregate(total=Sum('amount_discounted'))['total'] or Decimal('0.00')
            remaining_cap   = policy.max_discount_per_student - already_given
            discount_amount = min(discount_amount, remaining_cap)

        if discount_amount <= Decimal('0.00') and can_apply:
            can_apply = False
            warnings.append("Calculated discount is zero — nothing to apply")

    # ── Available policies for the picker ────────────────────────────────────
    available_policies = DiscountPolicy.objects.filter(
        is_active=True
    ).exclude(
        # Exclude policies whose valid_until has passed
        valid_until__lt=today,
    ).exclude(
        # Exclude policies that haven't started yet
        valid_from__gt=today,
    )

    if invoice.academic_session:
        session_scoped = available_policies.filter(
            Q(valid_sessions__isnull=True) |
            Q(valid_sessions=invoice.academic_session)
        ).distinct()
        if session_scoped.exists():
            available_policies = session_scoped

    available_policies = available_policies.order_by('priority', 'name')

    # ── Already-applied policies on this invoice ──────────────────────────────
    already_applied_policy_ids = set(
        DiscountApplication.objects.filter(
            invoice=invoice, is_reversed=False
        ).values_list('student_discount__policy_id', flat=True)
    )

    return render(request, 'fees/discounts/modals/apply_to_invoice.html', {
        'invoice':                  invoice,
        'policy':                   policy,
        'can_apply':                can_apply,
        'warnings':                 warnings,
        'discount_amount':          discount_amount,
        'available_policies':       available_policies,
        'already_applied_policy_ids': already_applied_policy_ids,
        'today':                    today,
    })


@login_required
def discount_application_reverse_modal(request, pk):
    """
    Modal for reversing a specific DiscountApplication.
    Shows the impact on the parent invoice balance before confirming.
    """
    application  = get_object_or_404(
        DiscountApplication.objects.select_related(
            'invoice', 'student_discount__policy', 'student_discount__student',
            'invoice_item__fee_category',
        ),
        pk=pk,
    )
    can_reverse  = not application.is_reversed
    warnings     = []

    if application.is_reversed:
        warnings.append("This discount application has already been reversed")

    invoice = application.invoice
    if invoice.status in ['PAID']:
        warnings.append(
            "Invoice is fully paid — reversing this discount will create a "
            "positive balance on the invoice"
        )

    if invoice.fiscal_period and getattr(invoice.fiscal_period, 'is_closed', False):
        can_reverse = False
        warnings.append(
            f"Fiscal period {invoice.fiscal_period.name} is closed — "
            f"cannot reverse discounts in a closed period"
        )

    # Preview what the invoice balance will look like after reversal
    new_balance = invoice.balance + application.amount_discounted

    return render(request, 'fees/discounts/modals/reverse_application.html', {
        'application':   application,
        'invoice':       invoice,
        'can_reverse':   can_reverse,
        'warnings':      warnings,
        'new_balance':   new_balance,
    })


# ── StudentDiscount (Award) modals ────────────────────────────────────────────

@login_required
def student_discount_delete_modal(request, pk):
    """Return delete confirmation modal for a StudentDiscount award."""
    discount          = get_object_or_404(
        StudentDiscount.objects.select_related('student', 'policy'),
        pk=pk,
    )
    active_applications = discount.applications.filter(is_reversed=False).count()
    warnings            = []
    can_delete          = True

    if discount.status == 'ACTIVE':
        can_delete = False
        warnings.append("Cannot delete an active award — suspend or revoke it first")

    if active_applications > 0:
        can_delete = False
        warnings.append(
            f"Award has been applied to {active_applications} invoice(s) — "
            f"reverse those applications before deleting"
        )

    return render(request, 'fees/discounts/modals/delete_student_discount.html', {
        'discount':            discount,
        'can_delete':          can_delete,
        'warnings':            warnings,
        'active_applications': active_applications,
    })


@login_required
def student_discount_suspend_modal(request, pk):
    """Modal to confirm suspending a StudentDiscount award."""
    discount    = get_object_or_404(
        StudentDiscount.objects.select_related('student', 'policy'),
        pk=pk,
    )
    can_suspend = discount.status == 'ACTIVE'
    warnings    = []

    if not can_suspend:
        warnings.append(
            f"Award is currently {discount.get_status_display()} — "
            f"only ACTIVE awards can be suspended"
        )

    pending_invoices = 0
    try:
        pending_invoices = FeeInvoice.objects.filter(
            student=discount.student,
            status__in=['DRAFT', 'PENDING'],
        ).count()
        if pending_invoices > 0:
            warnings.append(
                f"Student has {pending_invoices} pending invoice(s) — "
                f"suspending will prevent this discount from auto-applying to new invoices"
            )
    except Exception:
        pass

    return render(request, 'fees/discounts/modals/suspend_student_discount.html', {
        'discount':        discount,
        'can_suspend':     can_suspend,
        'warnings':        warnings,
        'pending_invoices': pending_invoices,
    })


@login_required
def student_discount_revoke_modal(request, pk):
    """Modal to confirm revoking a StudentDiscount award."""
    discount   = get_object_or_404(
        StudentDiscount.objects.select_related('student', 'policy'),
        pk=pk,
    )
    can_revoke = discount.status != 'REVOKED'
    warnings   = []

    if not can_revoke:
        warnings.append("Award is already revoked")

    if discount.status == 'ACTIVE':
        warnings.append(
            "Revoking an active award will immediately stop this discount "
            "from being applied to any future invoices"
        )

    active_applications = discount.applications.filter(is_reversed=False).count()
    if active_applications > 0:
        warnings.append(
            f"Award has {active_applications} existing application(s) on invoices — "
            f"these will NOT be automatically reversed"
        )

    return render(request, 'fees/discounts/modals/revoke_student_discount.html', {
        'discount':             discount,
        'can_revoke':           can_revoke,
        'warnings':             warnings,
        'active_applications':  active_applications,
    })


@login_required
def student_discount_quick_view_modal(request, pk):
    """Quick view modal showing a StudentDiscount award summary."""
    discount = get_object_or_404(
        StudentDiscount.objects.select_related(
            'student', 'policy'
        ).prefetch_related('policy__tiers'),
        pk=pk,
    )
    recent_applications = DiscountApplication.objects.filter(
        student_discount=discount
    ).select_related('invoice').order_by('-created_at')[:5]

    total_discounted = DiscountApplication.objects.filter(
        student_discount=discount, is_reversed=False
    ).aggregate(total=Sum('amount_discounted'))['total'] or Decimal('0.00')

    budget_remaining = None
    if discount.policy.max_discount_per_student:
        budget_remaining = discount.policy.max_discount_per_student - total_discounted

    return render(request, 'fees/discounts/modals/student_discount_quick_view.html', {
        'discount':            discount,
        'recent_applications': recent_applications,
        'total_discounted':    total_discounted,
        'budget_remaining':    budget_remaining,
        'today':               get_school_today(),
    })


# =============================================================================
# STUDENT ACCOUNT MODALS
# =============================================================================

@login_required
def student_account_adjust_modal(request, pk):
    """Modal for account adjustment."""
    account = get_object_or_404(StudentAccount, pk=pk)

    return render(request, 'fees/accounts/modals/adjust_account.html', {
        'account': account,
    })


@login_required
def student_account_quick_view_modal(request, pk):
    """Quick view modal for student account."""
    account = get_object_or_404(StudentAccount.objects.select_related('student'), pk=pk)
    recent_transactions = account.transactions.select_related(
        'invoice', 'payment'
    ).order_by('-created_at')[:10]

    return render(request, 'fees/accounts/modals/account_quick_view.html', {
        'account':             account,
        'recent_transactions': recent_transactions,
    })


# =============================================================================
# ACCOUNT TRANSACTION MODALS
# =============================================================================

@login_required
def account_transaction_detail_modal(request, pk):
    """Quick view modal for account transaction."""
    transaction_obj = get_object_or_404(
        AccountTransaction.objects.select_related(
            'student_account__student', 'invoice', 'payment', 'academic_session'
        ),
        pk=pk,
    )

    return render(request, 'fees/transactions/modals/transaction_detail.html', {
        'transaction': transaction_obj,
    })