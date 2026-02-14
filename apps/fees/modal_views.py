# fees/modal_views.py

"""
Modal Views for Fees Management

These views return HTML fragments for modals loaded via HTMX.
Each modal view is paired with an action view in views.py that handles the POST request.

Pattern:
1. GET request → modal_views.py (loads modal HTML)
2. POST request → views.py (processes action, returns response with headers)

Following the same pattern as loans/modal_views.py with unified modals for create/edit
"""

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from decimal import Decimal
from django.db.models import Q

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
    FeesDiscount,
    Refund,
    StudentAccount,
    AccountTransaction
)

from core.utils import get_school_today


# =============================================================================
# DISPLAY GROUP MODALS
# =============================================================================

@login_required
def display_group_delete_modal(request, pk):
    """Return delete confirmation modal content via HTMX"""
    group = get_object_or_404(DisplayGroup, pk=pk)
    
    # Check if group can be deleted
    category_count = group.feescategory_set.count()
    can_delete = category_count == 0
    
    return render(request, 'fees/display_groups/modals/delete_group.html', {
        'group': group,
        'can_delete': can_delete,
        'category_count': category_count,
    })


@login_required
def display_group_toggle_active_modal(request, pk):
    """Modal for confirming display group toggle active status"""
    group = get_object_or_404(DisplayGroup, pk=pk)
    
    new_status = "activate" if not group.is_active else "deactivate"
    
    return render(request, 'fees/display_groups/modals/toggle_active.html', {
        'group': group,
        'new_status': new_status,
    })


# =============================================================================
# FEE CATEGORY MODALS
# =============================================================================

@login_required
def fee_category_delete_modal(request, pk):
    """Return delete confirmation modal content via HTMX"""
    category = get_object_or_404(FeesCategory, pk=pk)
    
    # Check if category can be deleted
    structure_count = category.structure_items.count()
    invoice_count = category.invoice_items.count()
    
    can_delete = structure_count == 0 and invoice_count == 0
    
    return render(request, 'fees/categories/modals/delete_category.html', {
        'category': category,
        'can_delete': can_delete,
        'structure_count': structure_count,
        'invoice_count': invoice_count,
    })


@login_required
def fee_category_toggle_active_modal(request, pk):
    """Modal for confirming fee category toggle active status"""
    category = get_object_or_404(FeesCategory, pk=pk)
    
    new_status = "activate" if not category.is_active else "deactivate"
    
    return render(request, 'fees/categories/modals/toggle_active.html', {
        'category': category,
        'new_status': new_status,
    })


# =============================================================================
# FEE STRUCTURE MODALS
# =============================================================================

@login_required
def fee_structure_delete_modal(request, pk):
    """Return delete confirmation modal content via HTMX"""
    structure = get_object_or_404(FeesStructure, pk=pk)
    
    # Check if structure can be deleted
    invoice_count = structure.invoices.count()
    can_delete = invoice_count == 0
    
    # Check if structure is active
    has_active_warning = structure.is_active
    
    # Count items
    item_count = structure.items.count()
    
    return render(request, 'fees/structures/modals/delete_structure.html', {
        'structure': structure,
        'can_delete': can_delete,
        'invoice_count': invoice_count,
        'has_active_warning': has_active_warning,
        'item_count': item_count,
    })


@login_required
def fee_structure_clone_modal(request, pk):
    """Modal for cloning fee structure"""
    structure = get_object_or_404(
        FeesStructure.objects.prefetch_related(
            'academic_levels',
            'applicable_sessions',
            'applicable_classes',
            'items__fee_category'
        ),
        pk=pk
    )
    
    # Show info about what will be cloned
    item_count = structure.items.count()
    level_count = structure.academic_levels.count()
    session_count = structure.applicable_sessions.count()
    class_count = structure.applicable_classes.count()
    
    return render(request, 'fees/structures/modals/clone_structure.html', {
        'structure': structure,
        'item_count': item_count,
        'level_count': level_count,
        'session_count': session_count,
        'class_count': class_count,
    })


@login_required
def fee_structure_activate_modal(request, pk):
    """Modal for activating fee structure"""
    structure = get_object_or_404(FeesStructure, pk=pk)
    
    # Check for issues that might prevent activation
    warnings = []
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
    
    # Check for overlapping active structures
    if not structure.is_active:
        overlapping = FeesStructure.objects.filter(
            is_active=True,
            structure_type=structure.structure_type,
            academic_levels__in=structure.academic_levels.all(),
            applicable_sessions__in=structure.applicable_sessions.all()
        ).exclude(pk=structure.pk).distinct()
        
        if overlapping.exists():
            warnings.append(
                f"There are {overlapping.count()} active structure(s) "
                f"with overlapping levels/sessions"
            )
    
    return render(request, 'fees/structures/modals/activate_structure.html', {
        'structure': structure,
        'can_activate': can_activate,
        'warnings': warnings,
    })


@login_required
def fee_structure_deactivate_modal(request, pk):
    """Modal for deactivating fee structure"""
    structure = get_object_or_404(FeesStructure, pk=pk)
    
    # Get active invoice count
    active_invoices = structure.invoices.filter(
        status__in=['PENDING', 'PARTIALLY_PAID']
    ).count()
    
    return render(request, 'fees/structures/modals/deactivate_structure.html', {
        'structure': structure,
        'active_invoices': active_invoices,
    })


@login_required
def fee_structure_quick_view_modal(request, pk):
    """Quick view modal showing structure summary"""
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
    total_tax = sum((item.amount * item.tax_percentage / 100) for item in items)
    
    # Get usage stats
    invoice_count = structure.invoices.count()
    active_invoice_count = structure.invoices.filter(
        status__in=['PENDING', 'PARTIALLY_PAID']
    ).count()
    
    return render(request, 'fees/structures/modals/structure_quick_view.html', {
        'structure': structure,
        'items': items,
        'total_amount': total_amount,
        'total_tax': total_tax,
        'total_with_tax': total_amount + total_tax,
        'invoice_count': invoice_count,
        'active_invoice_count': active_invoice_count,
    })


@login_required
def fee_structure_compare_modal(request):
    """Modal for comparing multiple fee structures"""
    
    structure_ids = request.GET.getlist('structures')
    
    structures = FeesStructure.objects.filter(
        pk__in=structure_ids
    ).prefetch_related(
        'items__fee_category'
    )
    
    return render(request, 'fees/structures/modals/compare_structures.html', {
        'structures': structures,
    })

# =============================================================================
# FEE INVOICE MODALS
# =============================================================================

@login_required
def invoice_void_modal(request, pk):
    """Modal to void/cancel invoice"""
    invoice = get_object_or_404(FeeInvoice, pk=pk)
    
    # Check if invoice can be voided
    can_void = True
    warnings = []
    
    if invoice.status in ['VOID', 'CANCELLED']:
        can_void = False
        warnings.append("Invoice is already voided/cancelled")
    
    if invoice.status == 'PAID':
        can_void = False
        warnings.append("Cannot void paid invoices - use refund instead")
    
    if invoice.paid_amount > 0:
        warnings.append(
            f"Invoice has payments totaling {invoice.paid_amount} - "
            f"these will need to be handled"
        )
    
    return render(request, 'fees/invoices/modals/void_invoice.html', {
        'invoice': invoice,
        'can_void': can_void,
        'warnings': warnings,
    })


@login_required
def invoice_delete_modal(request, pk):
    """Return delete confirmation modal content via HTMX"""
    invoice = get_object_or_404(FeeInvoice, pk=pk)
    
    # Check if invoice can be deleted
    can_delete = True
    warnings = []
    
    # ✅ VOID and CANCELLED invoices can always be deleted
    if invoice.status in ['VOID', 'CANCELLED']:
        can_delete = True
        warnings.append(
            f"This is a {invoice.get_status_display()} invoice with no financial impact - "
            f"safe to delete"
        )
    # Check other statuses
    elif invoice.status == 'PAID':
        can_delete = False
        warnings.append("Cannot delete paid invoices")
    elif invoice.status == 'PARTIALLY_PAID':
        can_delete = False
        warnings.append("Invoice has payments - cannot delete")
    elif invoice.status not in ['DRAFT', 'VOID', 'CANCELLED']:
        can_delete = False
        warnings.append(f"Invoice is {invoice.get_status_display()} - can only delete DRAFT, VOID, or CANCELLED invoices")
    
    # Check for payments (even VOID shouldn't have payments, but double-check)
    payment_count = invoice.payments.count()
    if payment_count > 0:
        can_delete = False
        warnings.append(f"Invoice has {payment_count} payment(s)")
    
    # Check paid amount
    if invoice.paid_amount > 0:
        can_delete = False
        warnings.append(f"Invoice has received payments totaling {invoice.paid_amount:,.2f}")
    
    # Check for scholarships (informational only for VOID)
    scholarship_count = invoice.scholarship_applications.filter(
        is_reversed=False
    ).count()
    if scholarship_count > 0:
        if invoice.status == 'VOID':
            warnings.append(
                f"Invoice has {scholarship_count} scholarship application(s) "
                f"(will be removed with invoice)"
            )
        else:
            warnings.append(f"Invoice has {scholarship_count} scholarship applications")
    
    # Check for discounts (informational only for VOID)
    discount_count = invoice.discount_applications.count()
    if discount_count > 0:
        if invoice.status == 'VOID':
            warnings.append(
                f"Invoice has {discount_count} discount application(s) "
                f"(will be removed with invoice)"
            )
        else:
            warnings.append(f"Invoice has {discount_count} discount applications")
    
    # Check journal entry
    if invoice.journal_entry:
        if invoice.journal_entry.status == 'POSTED':
            can_delete = False
            warnings.append(
                f"Journal entry {invoice.journal_entry.entry_number} is POSTED - "
                f"cannot delete"
            )
        elif invoice.status in ['VOID', 'CANCELLED']:
            warnings.append(
                "⚠️ VOID invoice should not have a journal entry - "
                "this will be cleaned up during deletion"
            )
    
    return render(request, 'fees/invoices/modals/delete_invoice.html', {
        'invoice': invoice,
        'can_delete': can_delete,
        'warnings': warnings,
    })


@login_required
def invoice_regenerate_modal(request, pk):
    """Modal for regenerating an existing invoice"""
    invoice = get_object_or_404(FeeInvoice, pk=pk)
    
    # Check if has payments
    has_payments = invoice.paid_amount > 0
    payment_count = invoice.payments.count()
    
    warnings = []
    if has_payments:
        warnings.append(
            f"This invoice has {payment_count} payment(s) totaling {invoice.paid_amount}. "
            f"Regenerating will cancel this invoice and create a new one. "
            f"Existing payments will need to be reallocated."
        )
    
    return render(request, 'fees/invoices/modals/regenerate_invoice.html', {
        'invoice': invoice,
        'has_payments': has_payments,
        'payment_count': payment_count,
        'warnings': warnings,
    })


@login_required
def invoice_quick_view_modal(request, pk):
    """Quick view modal for invoice"""
    invoice = get_object_or_404(
        FeeInvoice.objects.select_related(
            'student', 'academic_session', 'fee_structure'
        ).prefetch_related('items__fee_category'),
        pk=pk
    )
    
    return render(request, 'fees/invoices/modals/invoice_quick_view.html', {
        'invoice': invoice,
    })

@login_required
def invoice_finalize_modal(request, pk):
    """Modal to confirm invoice finalization"""
    invoice = get_object_or_404(FeeInvoice, pk=pk)
    
    # Check if can be finalized
    can_finalize = invoice.status == 'DRAFT'
    
    warnings = []
    info = []
    
    if not can_finalize:
        warnings.append(f"Invoice is already {invoice.status}")
    else:
        info.append("Finalizing will:")
        info.append("• Change invoice status to PENDING")
        
        # ✅ FIX: Check journal_entry_id first
        if invoice.journal_entry_id:
            info.append("• Update and post the journal entry to General Ledger")
            # Now safe to access the relationship
            journal_entry = invoice.journal_entry
            info.append(f"• Journal Entry: {journal_entry.entry_number} (currently {journal_entry.status})")
        else:
            info.append("• Create and post journal entry to General Ledger")
            info.append("• Journal Entry: Will be created during finalization")
        
        info.append("• Allow payments to be received")
        info.append("• Lock invoice from major modifications")
    
    return render(request, 'fees/invoices/modals/finalize_invoice.html', {
        'invoice': invoice,
        'can_finalize': can_finalize,
        'warnings': warnings,
        'info': info,
    })


@login_required
def invoice_revert_to_draft_modal(request, pk):
    """
    Modal to confirm reverting invoice to draft.
    
    Shows:
    - Invoice details
    - What will happen when reverted
    - Journal entry information
    - Warnings if cannot revert
    """
    invoice = get_object_or_404(FeeInvoice, pk=pk)
    
    # Check if can be reverted
    can_revert = True
    warnings = []
    
    # Check status
    if invoice.status != 'PENDING':
        can_revert = False
        warnings.append(f"Invoice status is {invoice.get_status_display()}, not PENDING")
    
    # Check for payments
    if invoice.paid_amount > 0:
        can_revert = False
        warnings.append(f"Invoice has payments totaling {invoice.paid_amount:,.2f}")
    
    # Check payment count
    payment_count = invoice.payments.filter(
        status='COMPLETED',
        reversed=False,
        refunded=False
    ).count()
    
    if payment_count > 0:
        can_revert = False
        warnings.append(f"Invoice has {payment_count} active payment(s)")
    
    # ✅ FIX: Check journal entry status safely
    journal_posted = False
    if invoice.journal_entry_id:
        # Safe to access now
        journal_entry = invoice.journal_entry
        if journal_entry.status == 'POSTED':
            journal_posted = True
    
    # Additional checks for fiscal period
    if invoice.fiscal_period and invoice.fiscal_period.is_closed:
        can_revert = False
        warnings.append(f"Fiscal period {invoice.fiscal_period.name} is closed")
    
    return render(request, 'fees/invoices/modals/revert_to_draft.html', {
        'invoice': invoice,
        'can_revert': can_revert,
        'warnings': warnings,
        'journal_posted': journal_posted,
        'payment_count': payment_count,
    })

@login_required
def send_payment_reminder_modal(request, pk):
    """Modal to send payment reminder for overdue invoice"""
    invoice = get_object_or_404(FeeInvoice, pk=pk)
    
    # Check if overdue using school timezone
    today = get_school_today()
    
    is_overdue = (
        invoice.due_date < today and 
        invoice.status in ['PENDING', 'PARTIALLY_PAID', 'OVERDUE']
    )
    days_overdue = (today - invoice.due_date).days if is_overdue else 0
    
    return render(request, 'fees/invoices/modals/send_payment_reminder.html', {
        'invoice': invoice,
        'is_overdue': is_overdue,
        'days_overdue': days_overdue,
        'today': today,
    })


@login_required
def invoice_send_email_modal(request, pk):
    """Modal for sending invoice via email"""
    invoice = get_object_or_404(FeeInvoice, pk=pk)
    
    # Get student email
    student_email = invoice.student.email if hasattr(invoice.student, 'email') else None
    
    # Get parent/guardian emails if available
    parent_emails = []
    if hasattr(invoice.student, 'parents'):
        parent_emails = [
            p.email for p in invoice.student.parents.all() 
            if hasattr(p, 'email') and p.email
        ]
    
    return render(request, 'fees/invoices/modals/send_email.html', {
        'invoice': invoice,
        'student_email': student_email,
        'parent_emails': parent_emails,
    })


@login_required
def invoice_apply_penalty_modal(request, pk):
    """Modal for manually applying penalty to invoice"""
    invoice = get_object_or_404(FeeInvoice, pk=pk)
    
    # Check if invoice is overdue
    today = get_school_today()
    is_overdue = invoice.due_date < today and invoice.status in ['PENDING', 'PARTIALLY_PAID', 'OVERDUE']
    
    return render(request, 'fees/invoices/modals/apply_penalty.html', {
        'invoice': invoice,
        'is_overdue': is_overdue,
        'days_overdue': (today - invoice.due_date).days if is_overdue else 0,
    })


@login_required
def invoice_waive_late_fees_modal(request, pk):
    """Modal for waiving late fees on an invoice"""
    invoice = get_object_or_404(FeeInvoice, pk=pk)
    
    # Check if has late fees to waive
    has_late_fees = invoice.late_fee_amount > 0
    
    return render(request, 'fees/invoices/modals/waive_late_fees.html', {
        'invoice': invoice,
        'has_late_fees': has_late_fees,
    })


@login_required
def invoice_adjust_amount_modal(request, pk):
    """Modal for making amount adjustment to invoice"""
    invoice = get_object_or_404(FeeInvoice, pk=pk)
    
    # Check if invoice can be adjusted
    can_adjust = invoice.status not in ['PAID', 'VOID', 'CANCELLED']
    
    return render(request, 'fees/invoices/modals/adjust_amount.html', {
        'invoice': invoice,
        'can_adjust': can_adjust,
    })


@login_required
def invoice_clone_to_student_modal(request, pk):
    """Modal for cloning invoice to another student"""
    original_invoice = get_object_or_404(FeeInvoice, pk=pk)
    
    return render(request, 'fees/invoices/modals/clone_to_student.html', {
        'original_invoice': original_invoice,
    })


@login_required
def invoice_merge_modal(request):
    """Modal for merging multiple invoices"""
    
    invoice_ids = request.GET.getlist('invoices')
    
    invoices = FeeInvoice.objects.filter(
        pk__in=invoice_ids
    ).select_related('student', 'academic_session')
    
    # Check if all invoices belong to same student
    students = set(inv.student for inv in invoices)
    can_merge = len(students) == 1
    
    warnings = []
    if not can_merge:
        warnings.append("All invoices must belong to the same student")
    
    # Check if any are paid
    paid_invoices = [inv for inv in invoices if inv.status == 'PAID']
    if paid_invoices:
        warnings.append(f"{len(paid_invoices)} invoice(s) are already paid")
    
    return render(request, 'fees/invoices/modals/merge_invoices.html', {
        'invoices': invoices,
        'can_merge': can_merge,
        'warnings': warnings,
    })


@login_required
def invoice_split_modal(request, pk):
    """Modal for splitting invoice into installments"""
    invoice = get_object_or_404(FeeInvoice, pk=pk)
    
    can_split = invoice.status == 'PENDING' and invoice.paid_amount == 0
    
    return render(request, 'fees/invoices/modals/split_invoice.html', {
        'invoice': invoice,
        'can_split': can_split,
    })

@login_required
def apply_scholarship_to_invoice_modal(request, invoice_pk):
    """Modal to manually apply scholarship to existing invoice"""
    invoice = get_object_or_404(FeeInvoice, pk=invoice_pk)
    
    # Check if can modify invoice
    can_modify, reason = invoice.can_be_safely_modified()
    warnings = []
    can_apply = True
    
    if not can_modify and invoice.status not in ['DRAFT', 'PENDING']:
        can_apply = False
        warnings.append(reason)
    
    if invoice.fiscal_period and invoice.fiscal_period.is_closed:
        can_apply = False
        warnings.append(f"Fiscal period {invoice.fiscal_period.name} is closed")
    
    # Get eligible scholarships (not already on invoice)
    already_applied_ids = invoice.scholarship_application_logs.filter(
        is_reversed=False
    ).values_list('scholarship_id', flat=True)
    
    eligible_scholarships = StudentScholarship.objects.filter(
        student=invoice.student,
        status='ACTIVE',
        effective_start_date__lte=invoice.issue_date,
    ).filter(
        Q(effective_end_date__isnull=True) | Q(effective_end_date__gte=invoice.issue_date)
    ).exclude(
        pk__in=already_applied_ids
    ).select_related('scholarship_program')
    
    # Calculate preview for each scholarship
    scholarship_previews = []
    for scholarship in eligible_scholarships:
        # Calculate potential discount
        if scholarship.is_policy_based():
            # Percentage discount
            discount = (invoice.subtotal_amount * scholarship.scholarship_program.discount_percentage) / 100
        else:
            # Fixed amount
            discount = min(scholarship.get_remaining_balance(), invoice.subtotal_amount)
        
        scholarship_previews.append({
            'scholarship': scholarship,
            'potential_discount': discount,
            'new_total': invoice.total_amount - discount,
        })
    
    context = {
        'invoice': invoice,
        'can_apply': can_apply,
        'warnings': warnings,
        'scholarship_previews': scholarship_previews,
        'has_eligible_scholarships': eligible_scholarships.exists(),
    }
    
    return render(request, 'fees/scholarships/modals/apply_to_invoice.html', context)

@login_required
def remove_scholarship_from_invoice_modal(request, invoice_pk, scholarship_pk=None):
    """Modal for removing scholarship from invoice"""
    invoice = get_object_or_404(FeeInvoice, pk=invoice_pk)
    
    # Get all scholarship applications on this invoice
    scholarship_logs = invoice.scholarship_application_logs.filter(
        is_reversed=False
    ).select_related('scholarship__scholarship_program')
    
    # If specific scholarship provided
    scholarship = None
    scholarship_log = None
    if scholarship_pk:
        scholarship = get_object_or_404(StudentScholarship, pk=scholarship_pk)
        scholarship_log = scholarship_logs.filter(scholarship=scholarship).first()
    
    # Check if invoice allows scholarship removal
    can_remove = True
    warnings = []
    
    # Check invoice status
    if invoice.status == 'DRAFT':
        # Draft invoices can be modified freely
        pass
    elif invoice.status in ['PENDING', 'PARTIALLY_PAID']:
        # Pending/partially paid can remove scholarships with recalculation
        warnings.append("Invoice will be recalculated and balance updated")
    elif invoice.status in ['PAID', 'VOID', 'CANCELLED']:
        can_remove = False
        warnings.append(f"Cannot remove scholarships from {invoice.get_status_display()} invoices")
    
    # Check if invoice has payments that would create issues
    if invoice.paid_amount > 0:
        warnings.append(
            f"Invoice has payments totaling {invoice.paid_amount:,.2f}. "
            f"Removing scholarship will increase the balance."
        )
    
    # Check fiscal period
    if invoice.fiscal_period and invoice.fiscal_period.is_closed:
        can_remove = False
        warnings.append(f"Fiscal period {invoice.fiscal_period.name} is closed")
    
    return render(request, 'fees/scholarships/modals/remove_from_invoice.html', {
        'invoice': invoice,
        'scholarship': scholarship,
        'scholarship_log': scholarship_log,
        'scholarship_logs': scholarship_logs,
        'can_remove': can_remove,
        'warnings': warnings,
    })

# =============================================================================
# PAYMENT MODALS
# =============================================================================

@login_required
def payment_reverse_modal(request, pk):
    """Modal for reversing a payment - handles both GET and POST"""
    from fees.models import Payment  # ✅ Changed from FeePayment
    from django.http import HttpResponse
    from django.shortcuts import render, get_object_or_404
    import logging
    
    logger = logging.getLogger(__name__)
    payment = get_object_or_404(Payment, pk=pk)  # ✅ Changed from FeePayment
    
    # Check if payment can be reversed
    can_reverse, reason = payment.can_be_reversed()  # ✅ Use the model method
    
    if request.method == 'POST':
        if not can_reverse:
            response = HttpResponse()
            response['HX-Alert-Message'] = reason
            response['HX-Alert-Type'] = 'error'
            response['HX-Close-Modal'] = 'true'
            return response
        
        reversal_reason = request.POST.get('reason', '').strip()
        
        if not reversal_reason:
            # Return modal with error
            return render(request, 'fees/payments/modals/reverse_payment.html', {
                'payment': payment,
                'can_reverse': can_reverse,
                'reason': reason,
                'error_message': 'Reversal reason is required',
            })
        
        try:
            # Perform reversal using the model's reverse method
            payment.reverse(reason=reversal_reason, reversed_by=request.user)
            
            logger.info(
                f"Payment {payment.payment_number} reversed by {request.user.get_full_name()}. "
                f"Reason: {reversal_reason}"
            )
            
            # Return success response with HTMX headers
            response = HttpResponse()
            response['HX-Alert-Message'] = f'Payment {payment.payment_number} reversed successfully'
            response['HX-Alert-Type'] = 'success'
            response['HX-Alert-Title'] = 'Payment Reversed'
            response['HX-Close-Modal'] = 'true'
            response['HX-Trigger'] = 'refreshPaymentList'  # ✅ Trigger refresh
            return response
            
        except Exception as e:
            logger.error(f"Error reversing payment {payment.pk}: {e}", exc_info=True)
            
            # Return modal with error
            return render(request, 'fees/payments/modals/reverse_payment.html', {
                'payment': payment,
                'can_reverse': can_reverse,
                'reason': reason,
                'error_message': f'Error reversing payment: {str(e)}',
            })
    
    # GET request - show the modal form
    return render(request, 'fees/payments/modals/reverse_payment.html', {
        'payment': payment,
        'can_reverse': can_reverse,
        'reason': reason,
    })


@login_required
def payment_refund_modal(request, pk):
    """Return payment refund modal with form via HTMX"""
    payment = get_object_or_404(Payment, pk=pk)
    
    # Check if can be refunded
    can_refund, reason = payment.can_be_refunded()
    
    return render(request, 'fees/payments/modals/refund_payment.html', {
        'payment': payment,
        'can_refund': can_refund,
        'reason': reason if not can_refund else None,
    })


@login_required
def payment_verify_modal(request, pk):
    """Modal for payment verification"""
    payment = get_object_or_404(Payment, pk=pk)
    
    # Check if payment can be verified
    can_verify = True
    warnings = []
    
    if payment.is_verified:
        can_verify = False
        warnings.append("Payment is already verified")
    
    if payment.status == 'FAILED':
        warnings.append("Payment is marked as failed")
    
    return render(request, 'fees/payments/modals/verify_payment.html', {
        'payment': payment,
        'can_verify': can_verify,
        'warnings': warnings,
    })


@login_required
def payment_delete_modal(request, pk):
    """Return delete confirmation modal content via HTMX"""
    payment = get_object_or_404(Payment, pk=pk)
    
    # Check if payment can be deleted
    can_delete = True
    warnings = []
    
    if payment.is_verified:
        can_delete = False
        warnings.append("Cannot delete verified payments")
    
    if payment.status == 'COMPLETED':
        warnings.append("Payment has been completed")
    
    if payment.invoice and payment.invoice.status == 'PAID':
        warnings.append("Invoice is marked as PAID - deletion will affect invoice status")
    
    return render(request, 'fees/payments/modals/delete_payment.html', {
        'payment': payment,
        'can_delete': can_delete,
        'warnings': warnings,
    })


@login_required
def payment_quick_view_modal(request, pk):
    """Quick view modal for payment"""
    payment = get_object_or_404(
        Payment.objects.select_related(
            'student', 'invoice', 'payment_method'
        ),
        pk=pk
    )
    
    return render(request, 'fees/payments/modals/payment_quick_view.html', {
        'payment': payment,
    })


@login_required
def bulk_payment_verification_modal(request):
    """Modal for bulk payment verification"""
    
    # Get unverified completed payments
    unverified_payments = Payment.objects.filter(
        is_verified=False,
        status='COMPLETED'
    ).select_related('student', 'payment_method').order_by('-payment_date')[:50]
    
    return render(request, 'fees/payments/modals/bulk_verify_payments.html', {
        'unverified_payments': unverified_payments,
        'total_amount': sum(p.amount for p in unverified_payments),
    })


@login_required
def payment_send_receipt_modal(request, pk):
    """Modal for sending payment receipt via email"""
    payment = get_object_or_404(Payment, pk=pk)
    
    # Get email addresses
    student_email = payment.student.email if hasattr(payment.student, 'email') else None
    paid_by_email = payment.paid_by_email
    
    return render(request, 'fees/payments/modals/send_receipt.html', {
        'payment': payment,
        'student_email': student_email,
        'paid_by_email': paid_by_email,
    })


@login_required
def payment_allocation_detail_modal(request, pk):
    """Modal showing how payment was allocated"""
    payment = get_object_or_404(Payment, pk=pk)
    
    # Get allocation breakdown
    allocation = {
        'principal': payment.amount_applied_to_invoice,
        'late_fees': getattr(payment, 'late_fee_amount', Decimal('0.00')),
        'penalties': getattr(payment, 'penalty_amount', Decimal('0.00')),
        'overpayment': payment.overpayment_amount,
    }
    
    return render(request, 'fees/payments/modals/allocation_detail.html', {
        'payment': payment,
        'allocation': allocation,
    })

# =============================================================================
# SCHOLARSHIP PROGRAM MODALS
# =============================================================================

@login_required
def scholarship_program_delete_modal(request, pk):
    """Return delete confirmation modal content via HTMX"""
    program = get_object_or_404(ScholarshipProgram, pk=pk)
    
    # Check if program can be deleted
    can_delete = True
    warnings = []
    
    # Check for active scholarships
    active_count = program.student_scholarships.filter(status='ACTIVE').count()
    if active_count > 0:
        can_delete = False
        warnings.append(f"Program has {active_count} active scholarships")
    
    # Check for applications
    application_count = program.applications.count()
    if application_count > 0:
        warnings.append(f"Program has {application_count} applications")
    
    # Check if currently accepting applications
    if program.is_accepting_applications:
        warnings.append("Program is currently accepting applications")
    
    return render(request, 'fees/scholarships/modals/delete_program.html', {
        'program': program,
        'can_delete': can_delete,
        'warnings': warnings,
    })


@login_required
def scholarship_program_activate_modal(request, pk):
    """Return activation confirmation modal content via HTMX"""
    program = get_object_or_404(ScholarshipProgram, pk=pk)
    
    return render(request, 'fees/scholarships/modals/activate_program.html', {
        'program': program,
    })


@login_required
def scholarship_program_deactivate_modal(request, pk):
    """Return deactivation confirmation modal content via HTMX"""
    program = get_object_or_404(ScholarshipProgram, pk=pk)
    
    # Get active scholarship/application count
    active_scholarships = program.student_scholarships.filter(status='ACTIVE').count()
    pending_applications = program.applications.filter(
        status__in=['SUBMITTED', 'UNDER_REVIEW']
    ).count()
    
    return render(request, 'fees/scholarships/modals/deactivate_program.html', {
        'program': program,
        'active_scholarships': active_scholarships,
        'pending_applications': pending_applications,
    })


@login_required
def scholarship_toggle_accepting_modal(request, pk):
    """Modal to toggle scholarship application acceptance"""
    program = get_object_or_404(ScholarshipProgram, pk=pk)
    
    # Check dates against school timezone
    today = get_school_today()
    
    warnings = []
    
    if program.application_start_date and today < program.application_start_date:
        warnings.append("Application period hasn't started yet")
    
    if program.application_end_date and today > program.application_end_date:
        warnings.append("Application period has ended")
    
    if program.current_budget_used >= program.total_budget_amount:
        warnings.append("Program budget is fully utilized")
    
    return render(request, 'fees/scholarships/modals/toggle_accepting.html', {
        'program': program,
        'warnings': warnings,
        'today': today,
    })


# =============================================================================
# SCHOLARSHIP APPLICATION MODALS
# =============================================================================

@login_required
def scholarship_application_approve_modal(request, pk):
    """Return application approval modal with form via HTMX"""
    application = get_object_or_404(StudentScholarshipApplication, pk=pk)
    
    # Check if can be approved
    can_approve = application.status in ['SUBMITTED', 'UNDER_REVIEW']
    
    return render(request, 'fees/scholarships/modals/approve_application.html', {
        'application': application,
        'can_approve': can_approve,
    })


@login_required
def scholarship_application_reject_modal(request, pk):
    """Return application rejection modal with reason input via HTMX"""
    application = get_object_or_404(StudentScholarshipApplication, pk=pk)
    
    return render(request, 'fees/scholarships/modals/reject_application.html', {
        'application': application,
    })


@login_required
def scholarship_application_delete_modal(request, pk):
    """Return delete confirmation modal content via HTMX"""
    application = get_object_or_404(StudentScholarshipApplication, pk=pk)
    
    # Check if application can be deleted
    can_delete = application.status != 'APPROVED'
    
    return render(request, 'fees/scholarships/modals/delete_application.html', {
        'application': application,
        'can_delete': can_delete,
    })


@login_required
def scholarship_application_history_modal(request, pk):
    """Modal showing application status history"""
    application = get_object_or_404(StudentScholarshipApplication, pk=pk)
    
    # Get application logs/history
    history = []
    if hasattr(application, 'logs'):
        history = application.logs.order_by('-created_at')
    
    return render(request, 'fees/scholarships/modals/application_history.html', {
        'application': application,
        'history': history,
    })

# =============================================================================
# STUDENT SCHOLARSHIP MODALS
# =============================================================================

@login_required
def student_scholarship_suspend_modal(request, pk):
    """Modal to suspend student scholarship"""
    scholarship = get_object_or_404(StudentScholarship, pk=pk)
    
    can_suspend = scholarship.status == 'ACTIVE'
    
    return render(request, 'fees/scholarships/modals/suspend_scholarship.html', {
        'scholarship': scholarship,
        'can_suspend': can_suspend,
    })


@login_required
def student_scholarship_terminate_modal(request, pk):
    """Modal to terminate student scholarship"""
    scholarship = get_object_or_404(StudentScholarship, pk=pk)
    
    can_terminate = scholarship.status in ['ACTIVE', 'SUSPENDED']
    
    return render(request, 'fees/scholarships/modals/terminate_scholarship.html', {
        'scholarship': scholarship,
        'can_terminate': can_terminate,
    })


@login_required
def student_scholarship_reactivate_modal(request, pk):
    """Modal to reactivate suspended student scholarship"""
    scholarship = get_object_or_404(StudentScholarship, pk=pk)
    
    can_reactivate = scholarship.status == 'SUSPENDED'
    
    return render(request, 'fees/scholarships/modals/reactivate_scholarship.html', {
        'scholarship': scholarship,
        'can_reactivate': can_reactivate,
    })


@login_required
def student_scholarship_complete_modal(request, pk):
    """Modal to mark student scholarship as completed"""
    scholarship = get_object_or_404(StudentScholarship, pk=pk)
    
    can_complete = scholarship.status == 'ACTIVE'
    
    # Check if scholarship term has ended
    today = get_school_today()
    term_ended = False
    if scholarship.end_date:
        term_ended = today >= scholarship.end_date
    
    return render(request, 'fees/scholarships/modals/complete_scholarship.html', {
        'scholarship': scholarship,
        'can_complete': can_complete,
        'term_ended': term_ended,
    })


@login_required
def student_scholarship_delete_modal(request, pk):
    """Return delete confirmation modal content via HTMX"""
    scholarship = get_object_or_404(StudentScholarship, pk=pk)
    
    # Check if scholarship can be deleted
    can_delete = True
    warnings = []
    
    if scholarship.status == 'ACTIVE':
        can_delete = False
        warnings.append("Cannot delete active scholarships - suspend or terminate first")
    
    # Check for application logs
    log_count = scholarship.application_logs.filter(is_reversed=False).count()
    if log_count > 0:
        warnings.append(f"Scholarship has been applied to {log_count} invoice(s)")
    
    return render(request, 'fees/scholarships/modals/delete_scholarship.html', {
        'scholarship': scholarship,
        'can_delete': can_delete,
        'warnings': warnings,
    })


@login_required
def apply_scholarship_to_invoice_modal(request, invoice_pk, scholarship_pk):
    """Modal for applying scholarship to specific invoice"""
    invoice = get_object_or_404(FeeInvoice, pk=invoice_pk)
    scholarship = get_object_or_404(StudentScholarship, pk=scholarship_pk)
    
    # Check if scholarship can be applied
    can_apply = True
    warnings = []
    
    if scholarship.student != invoice.student:
        can_apply = False
        warnings.append("Scholarship and invoice belong to different students")
    
    if scholarship.status != 'ACTIVE':
        can_apply = False
        warnings.append(f"Scholarship status is {scholarship.get_status_display()}")
    
    # Check if scholarship has remaining balance
    remaining_balance = scholarship.get_remaining_balance()
    if remaining_balance <= 0:
        can_apply = False
        warnings.append("Scholarship has no remaining balance")
    
    # Calculate potential discount
    potential_discount = min(remaining_balance, invoice.balance)
    
    return render(request, 'fees/scholarships/modals/apply_to_invoice.html', {
        'invoice': invoice,
        'scholarship': scholarship,
        'can_apply': can_apply,
        'warnings': warnings,
        'remaining_balance': remaining_balance,
        'potential_discount': potential_discount,
    })

# =============================================================================
# DISCOUNT MODALS
# =============================================================================

@login_required
def discount_delete_modal(request, pk):
    """Return delete confirmation modal content via HTMX"""
    discount = get_object_or_404(FeesDiscount, pk=pk)
    
    # Check if discount can be deleted
    can_delete = True
    warnings = []
    
    # Check for applications
    application_count = discount.applications.count()
    if application_count > 0:
        warnings.append(f"Discount has been applied {application_count} times")
        if application_count > 10:
            can_delete = False
    
    # Check if active
    if discount.is_active:
        warnings.append("Discount is currently active")
    
    # Check usage
    if discount.current_usage_count > 0:
        warnings.append(f"Discount has been used {discount.current_usage_count} times")
    
    return render(request, 'fees/discounts/modals/delete_discount.html', {
        'discount': discount,
        'can_delete': can_delete,
        'warnings': warnings,
    })


@login_required
def discount_toggle_active_modal(request, pk):
    """Modal to toggle discount active status"""
    discount = get_object_or_404(FeesDiscount, pk=pk)
    
    return render(request, 'fees/discounts/modals/toggle_active.html', {
        'discount': discount,
    })


@login_required
def apply_discount_to_invoice_modal(request, invoice_pk, discount_pk=None):
    """Modal for applying discount to specific invoice"""
    invoice = get_object_or_404(FeeInvoice, pk=invoice_pk)
    
    discount = None
    if discount_pk:
        discount = get_object_or_404(FeesDiscount, pk=discount_pk)
    
    # Check if invoice can receive discounts
    can_apply = True
    warnings = []
    
    if invoice.status in ['PAID', 'VOID', 'CANCELLED']:
        can_apply = False
        warnings.append(f"Cannot apply discount to {invoice.get_status_display()} invoice")
    
    if discount:
        # Check if discount is active
        if not discount.is_active:
            can_apply = False
            warnings.append("Discount is not active")
        
        # Check date validity
        today = get_school_today()
        if discount.start_date and today < discount.start_date:
            can_apply = False
            warnings.append("Discount period has not started")
        
        if discount.end_date and today > discount.end_date:
            can_apply = False
            warnings.append("Discount period has ended")
        
        # Check if discount is applicable to this structure
        if discount.applicable_structures.exists():
            if invoice.fee_structure not in discount.applicable_structures.all():
                can_apply = False
                warnings.append("Discount is not applicable to this fee structure")
        
        # Calculate discount amount
        if discount.discount_type == 'PERCENTAGE':
            discount_amount = (invoice.balance * discount.discount_value / 100).quantize(Decimal('0.01'))
        else:  # FIXED
            discount_amount = discount.discount_value
        
        discount_amount = min(discount_amount, invoice.balance)
    else:
        discount_amount = None
    
    # Get available discounts for this invoice
    today = get_school_today()
    available_discounts = FeesDiscount.objects.filter(
        is_active=True,
        start_date__lte=today,
        end_date__gte=today,
    )
    
    # Filter by structure if applicable
    if invoice.fee_structure:
        structure_discounts = available_discounts.filter(
            applicable_structures=invoice.fee_structure
        )
        if structure_discounts.exists():
            available_discounts = structure_discounts
    
    return render(request, 'fees/discounts/modals/apply_to_invoice.html', {
        'invoice': invoice,
        'discount': discount,
        'can_apply': can_apply,
        'warnings': warnings,
        'discount_amount': discount_amount,
        'available_discounts': available_discounts,
    })

# =============================================================================
# REFUND MODALS
# =============================================================================

@login_required
def refund_approve_modal(request, pk):
    """Modal for approving refund"""
    refund = get_object_or_404(Refund, pk=pk)
    
    can_approve = refund.status in ['REQUESTED', 'UNDER_REVIEW']
    
    return render(request, 'fees/refunds/modals/approve_refund.html', {
        'refund': refund,
        'can_approve': can_approve,
    })


@login_required
def refund_process_modal(request, pk):
    """Modal for processing approved refund"""
    refund = get_object_or_404(Refund, pk=pk)
    
    can_process = refund.status == 'APPROVED'
    
    return render(request, 'fees/refunds/modals/process_refund.html', {
        'refund': refund,
        'can_process': can_process,
    })


@login_required
def refund_delete_modal(request, pk):
    """Return delete confirmation modal content via HTMX"""
    refund = get_object_or_404(Refund, pk=pk)
    
    # Check if refund can be deleted
    can_delete = refund.status not in ['APPROVED', 'PROCESSING', 'COMPLETED']
    
    return render(request, 'fees/refunds/modals/delete_refund.html', {
        'refund': refund,
        'can_delete': can_delete,
    })


# =============================================================================
# STUDENT ACCOUNT MODALS
# =============================================================================

@login_required
def student_account_adjust_modal(request, pk):
    """Modal for account adjustment"""
    account = get_object_or_404(StudentAccount, pk=pk)
    
    return render(request, 'fees/accounts/modals/adjust_account.html', {
        'account': account,
    })


@login_required
def student_account_quick_view_modal(request, pk):
    """Quick view modal for student account"""
    account = get_object_or_404(
        StudentAccount.objects.select_related('student'),
        pk=pk
    )
    
    # Get recent transactions
    recent_transactions = account.transactions.select_related(
        'invoice', 'payment'
    ).order_by('-created_at')[:10]
    
    return render(request, 'fees/accounts/modals/account_quick_view.html', {
        'account': account,
        'recent_transactions': recent_transactions,
    })

# =============================================================================
# ACCOUNT TRANSACTION MODALS (Quick views)
# =============================================================================

@login_required
def account_transaction_detail_modal(request, pk):
    """Quick view modal for account transaction"""
    transaction = get_object_or_404(
        AccountTransaction.objects.select_related(
            'student_account__student',
            'invoice',
            'payment',
            'academic_session'
        ),
        pk=pk
    )
    
    return render(request, 'fees/transactions/modals/transaction_detail.html', {
        'transaction': transaction,
    })


# =============================================================================
# BULK OPERATION MODALS (Confirmations for bulk actions)
# =============================================================================

@login_required
def bulk_late_fee_application_modal(request):
    """Modal for bulk late fee application"""
    
    today = get_school_today()
    
    # Get count of overdue invoices
    overdue_count = FeeInvoice.objects.filter(
        due_date__lt=today,
        status__in=['PENDING', 'PARTIALLY_PAID', 'OVERDUE']
    ).count()
    
    return render(request, 'fees/invoices/modals/bulk_late_fees.html', {
        'overdue_count': overdue_count,
        'today': today,
    })