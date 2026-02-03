# boarding/signals.py 

from django.db.models.signals import pre_delete, post_save, pre_save
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from django.db import transaction
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# UPDATED SIGNAL - HANDLES VOID INVOICES
# =============================================================================

@receiver(pre_delete, sender='boarding.BoardingEnrollment')
def boarding_enrollment_pre_delete(sender, instance, **kwargs):
    """
    Handle invoice when boarding enrollment is being deleted.
    
    SAFE deletion (removes boarding items from invoice):
    - Invoice is DRAFT or VOID
    - No payments made
    - Journal entry is DRAFT or doesn't exist
    
    UNSAFE deletion (blocks deletion):
    - Invoice is finalized (PENDING, PAID, etc.) but not VOID
    - Payments have been made
    - Journal entry is POSTED or REVERSED
    
    In unsafe cases, user must:
    1. Mark enrollment as TERMINATED (don't delete)
    2. Issue credit note for unused fees
    3. Process refund if applicable
    """
    if not instance.boarding_invoice:
        # No invoice linked - safe to delete
        logger.info(f"Deleting boarding enrollment {instance.id} - no invoice linked")
        return
    
    invoice = instance.boarding_invoice
    
    # PRIMARY CHECK: Journal Entry Status (highest priority)
    if invoice.journal_entry:
        je_status = invoice.journal_entry.status
        
        if je_status == 'POSTED':
            raise ValidationError({
                'boarding_invoice': (
                    f"Cannot delete boarding enrollment: Journal entry {invoice.journal_entry.entry_number} already posted\n\n"
                    f"This boarding enrollment has a posted journal entry.\n\n"
                    f"To cancel boarding:\n"
                    f"1. Change enrollment status to 'TERMINATED' (don't delete)\n"
                    f"2. Issue a credit note for unused boarding fees\n"
                    f"3. Process refund if applicable\n\n"
                    f"Contact finance team for assistance."
                )
            })
        
        elif je_status == 'REVERSED':
            raise ValidationError({
                'boarding_invoice': (
                    f"Cannot delete boarding enrollment: Journal entry {invoice.journal_entry.entry_number} has been reversed\n\n"
                    f"This boarding enrollment has a reversed journal entry.\n\n"
                    f"To cancel boarding:\n"
                    f"1. Change enrollment status to 'TERMINATED' (don't delete)\n"
                    f"2. Issue a credit note for unused boarding fees\n"
                    f"3. Process refund if applicable\n\n"
                    f"Contact finance team for assistance."
                )
            })
    
    # SECONDARY CHECK: Invoice Status
    # Allow deletion for DRAFT and VOID invoices
    if invoice.status not in ['DRAFT', 'VOID']:
        raise ValidationError({
            'boarding_invoice': (
                f"Cannot delete boarding enrollment: Invoice status is {invoice.get_status_display()}\n\n"
                f"This boarding enrollment has a finalized invoice ({invoice.invoice_number}).\n\n"
                f"To cancel boarding:\n"
                f"1. Change enrollment status to 'TERMINATED' (don't delete)\n"
                f"2. Issue a credit note for unused boarding fees\n"
                f"3. Process refund if applicable\n\n"
                f"Contact finance team for assistance."
            )
        })
    
    # TERTIARY CHECK: Payments
    if invoice.paid_amount > 0:
        raise ValidationError({
            'boarding_invoice': (
                f"Cannot delete boarding enrollment: Invoice has payments of {invoice.paid_amount}\n\n"
                f"This boarding enrollment has received payments.\n\n"
                f"To cancel boarding:\n"
                f"1. Change enrollment status to 'TERMINATED' (don't delete)\n"
                f"2. Issue a credit note for unused boarding fees\n"
                f"3. Process refund if applicable\n\n"
                f"Contact finance team for assistance."
            )
        })
    
    # ALL CHECKS PASSED - SAFE TO DELETE
    # Remove boarding items from DRAFT/VOID invoice
    logger.info(
        f"Deleting boarding enrollment {instance.id} - "
        f"removing boarding items from {invoice.status} invoice {invoice.invoice_number}"
    )
    
    # Get boarding-related items
    boarding_items = invoice.items.filter(
        fee_category__category_type__in=['BOARDING', 'LAUNDRY']
    )
    
    deleted_count = boarding_items.count()
    
    if deleted_count > 0:
        # Delete boarding items
        boarding_items.delete()
        
        logger.info(
            f"✓ Removed {deleted_count} boarding items from invoice {invoice.invoice_number}"
        )
        
        # Delete DRAFT journal entry (will be recreated when invoice finalized)
        if invoice.journal_entry and invoice.journal_entry.status == 'DRAFT':
            je_number = invoice.journal_entry.entry_number
            invoice.journal_entry.delete()
            invoice.journal_entry = None
            invoice.save(update_fields=['journal_entry'])
            logger.info(
                f"✓ Deleted DRAFT journal entry {je_number} - "
                f"will be recreated with correct totals when invoice finalized"
            )
        
        # Recalculate invoice totals (only for non-VOID invoices)
        if invoice.status != 'VOID':
            invoice.recalculate_totals()
        
        # Update invoice notes
        if invoice.notes:
            invoice.notes += "\n\n[Boarding enrollment cancelled - boarding fees removed]"
        else:
            invoice.notes = "[Boarding enrollment cancelled - boarding fees removed]"
        invoice.save(update_fields=['notes'])
        
        logger.info(
            f"✅ Successfully removed boarding fees from invoice {invoice.invoice_number}. "
            f"New total: {invoice.total_amount}"
        )
    else:
        logger.warning(
            f"No boarding items found on invoice {invoice.invoice_number} to remove"
        )

# =============================================================================
# NEW SIGNAL - ADD THIS (handles adding boarding fees when enrollment activated)
# =============================================================================

@receiver(post_save, sender='boarding.BoardingEnrollment')
def auto_add_boarding_fees_to_invoice(sender, instance, created, **kwargs):
    """
    Automatically add boarding fees when enrollment is created.
    
    Behavior:
    - If student has DRAFT invoice: Add boarding items to it
    - If student has finalized invoice: Create supplementary invoice
    - If no invoice exists: Do nothing (will be included when invoice is generated)
    """
    # ✅ COMPREHENSIVE LOGGING
    logger.info(
        f"[BOARDING SIGNAL] Triggered for enrollment {instance.id}\n"
        f"  Student: {instance.student.get_full_name()}\n"
        f"  Status: {instance.status}\n"
        f"  Created: {created}\n"
        f"  auto_create_invoice: {instance.auto_create_invoice}"
    )
    
    # Only proceed for NEW enrollments
    if not created:
        logger.debug(f"[BOARDING SIGNAL] Skipped - not a new enrollment")
        return
    
    # Only proceed if auto_create_invoice is enabled
    if not instance.auto_create_invoice:
        logger.info(f"[BOARDING SIGNAL] Skipped - auto_create_invoice disabled")
        return
    
    # Skip if already has invoice linked
    if instance.boarding_invoice:
        logger.info(f"[BOARDING SIGNAL] Skipped - already has invoice")
        return
    
    logger.info(f"[BOARDING SIGNAL] ✅ Processing boarding fees for new enrollment")
    
    with transaction.atomic():
        _add_boarding_fees_to_student_invoice(instance)


def _add_boarding_fees_to_student_invoice(boarding_enrollment):
    """
    Add boarding fees to student's invoice for the session.
    
    Args:
        boarding_enrollment: BoardingEnrollment instance
    """
    from fees.models import FeeInvoice, FeeInvoiceItem, FeesStructure
    from fees.invoice_generators import UnifiedStudentInvoiceGenerator
    
    student = boarding_enrollment.student
    session = boarding_enrollment.academic_session
    
    logger.info(
        f"Processing boarding fees for {student.get_full_name()} "
        f"in {session.name}"
    )
    
    # =========================================================================
    # FIND EXISTING INVOICE
    # =========================================================================
    
    # Look for student's invoice for this session
    existing_invoice = FeeInvoice.objects.filter(
        student=student,
        academic_session=session,
    ).order_by('-created_at').first()
    
    if not existing_invoice:
        logger.info(
            f"No existing invoice found for {student.get_full_name()} "
            f"in {session.name} - boarding fees will be included when invoice is generated"
        )
        return
    
    logger.info(f"Found existing invoice: {existing_invoice.invoice_number} (Status: {existing_invoice.status})")
    
    # =========================================================================
    # HANDLE BASED ON INVOICE STATUS
    # =========================================================================
    
    if existing_invoice.status == 'DRAFT':
        # Invoice is still DRAFT - we can add items to it
        logger.info(f"Invoice {existing_invoice.invoice_number} is DRAFT - adding boarding items")
        _add_boarding_items_to_draft_invoice(existing_invoice, boarding_enrollment)
        
        # Link this invoice to boarding enrollment
        boarding_enrollment.boarding_invoice = existing_invoice
        boarding_enrollment.save(update_fields=['boarding_invoice'])
        
    elif existing_invoice.status in ['PENDING', 'PARTIALLY_PAID', 'PAID', 'OVERDUE']:
        # Invoice is finalized - create supplementary invoice for boarding
        logger.info(
            f"Invoice {existing_invoice.invoice_number} is {existing_invoice.status} "
            f"- creating supplementary boarding invoice"
        )
        _create_supplementary_boarding_invoice(boarding_enrollment)
        
    else:
        logger.warning(
            f"Cannot add boarding fees - invoice {existing_invoice.invoice_number} "
            f"has status {existing_invoice.status}"
        )


def _add_boarding_items_to_draft_invoice(invoice, boarding_enrollment):
    """
    Add boarding fee items to an existing DRAFT invoice.
    
    Args:
        invoice: FeeInvoice instance (must be DRAFT)
        boarding_enrollment: BoardingEnrollment instance
    """
    from fees.models import FeeInvoiceItem, FeesStructure
    
    # Verify invoice is DRAFT
    if invoice.status != 'DRAFT':
        raise ValueError(f"Cannot add items to invoice with status {invoice.status}")
    
    # =========================================================================
    # FIND BOARDING FEE STRUCTURE
    # =========================================================================
    
    boarding_fee_structure = FeesStructure.objects.filter(
        applicable_sessions=boarding_enrollment.academic_session,
        boarding_type_filter__in=[
            boarding_enrollment.boarding_type,
            'BOARDER_ONLY',
        ],
        is_active=True
    ).order_by('priority').first()
    
    if not boarding_fee_structure:
        logger.warning(
            f"No boarding fee structure found for "
            f"{boarding_enrollment.get_boarding_type_display()} "
            f"in {boarding_enrollment.academic_session.name}"
        )
        return
    
    logger.info(f"Using boarding fee structure: {boarding_fee_structure.name}")
    
    # =========================================================================
    # ADD BOARDING ITEMS
    # =========================================================================
    
    items_added = 0
    student = boarding_enrollment.student
    
    for structure_item in boarding_fee_structure.items.all().order_by('display_order'):
        # Check if item applies to this student
        if not structure_item.is_applicable_to_student(student):
            logger.debug(f"Skipping non-applicable item: {structure_item.fee_category.name}")
            continue
        
        # Skip if not mandatory (only add required boarding fees)
        if not structure_item.is_mandatory:
            logger.debug(f"Skipping optional item: {structure_item.fee_category.name}")
            continue
        
        # Check if this category is already on the invoice
        if invoice.items.filter(fee_category=structure_item.fee_category).exists():
            logger.debug(f"Item already exists: {structure_item.fee_category.name}")
            continue
        
        # Get amount
        amount = structure_item.get_amount_for_student(student)
        tax_amount = structure_item.calculate_tax_amount(amount)
        
        # Create invoice item
        FeeInvoiceItem.objects.create(
            invoice=invoice,
            fee_category=structure_item.fee_category,
            description=structure_item.get_description(),
            quantity=Decimal('1.00'),
            unit_amount=amount,
            amount=amount,
            tax_percentage=structure_item.tax_percentage,
            tax_amount=tax_amount,
            final_amount=amount + tax_amount,
            original_amount=amount,
        )
        
        items_added += 1
        logger.info(f"Added boarding item: {structure_item.fee_category.name} - {amount}")
    
    if items_added == 0:
        logger.warning("No boarding items added to invoice")
        return
    
    # =========================================================================
    # RECALCULATE INVOICE TOTALS
    # =========================================================================
    
    logger.info(f"Recalculating invoice totals after adding {items_added} boarding items")
    invoice.recalculate_totals()
    
    # Update invoice notes
    if invoice.notes:
        invoice.notes += f"\n\n[Boarding fees added - {boarding_enrollment.get_boarding_type_display()}]"
    else:
        invoice.notes = f"[Boarding fees added - {boarding_enrollment.get_boarding_type_display()}]"
    invoice.save(update_fields=['notes'])
    
    # Delete DRAFT journal entry if exists (will be recreated with correct totals)
    if invoice.journal_entry and invoice.journal_entry.status == 'DRAFT':
        je_number = invoice.journal_entry.entry_number
        invoice.journal_entry.delete()
        invoice.journal_entry = None
        invoice.save(update_fields=['journal_entry'])
        logger.info(f"Deleted DRAFT journal entry {je_number} - will be recreated when finalized")
    
    # Recreate journal entry with new totals
    from fees.invoice_generators import UnifiedStudentInvoiceGenerator
    UnifiedStudentInvoiceGenerator._create_journal_entry(invoice)
    
    logger.info(
        f"✅ Added {items_added} boarding items to invoice {invoice.invoice_number}. "
        f"New total: {invoice.total_amount}"
    )


def _create_supplementary_boarding_invoice(boarding_enrollment):
    """
    Create a separate supplementary invoice for boarding fees.
    
    Used when the main academic invoice is already finalized.
    
    Args:
        boarding_enrollment: BoardingEnrollment instance
    """
    from fees.invoice_generators import UnifiedStudentInvoiceGenerator
    
    student = boarding_enrollment.student
    session = boarding_enrollment.academic_session
    
    # Find class enrollment for this session
    class_enrollment = student.class_enrollments.filter(
        academic_session=session,
        is_active=True,
        completion_status='ONGOING'
    ).first()
    
    if not class_enrollment:
        logger.error(
            f"Cannot create boarding invoice: {student.get_full_name()} "
            f"has no active class enrollment for {session.name}"
        )
        return
    
    # Generate boarding-only invoice
    try:
        invoice = UnifiedStudentInvoiceGenerator.generate(
            class_enrollment,
            include_boarding=True,
            force=True,  # Allow even though enrollment may have invoice
        )
        
        # Mark as supplementary
        invoice.notes = f"SUPPLEMENTARY INVOICE - Boarding fees added mid-session\n\n{invoice.notes or ''}"
        invoice.save(update_fields=['notes'])
        
        # Link to boarding enrollment
        boarding_enrollment.boarding_invoice = invoice
        boarding_enrollment.save(update_fields=['boarding_invoice'])
        
        logger.info(
            f"✅ Created supplementary boarding invoice {invoice.invoice_number} "
            f"for {student.get_full_name()}"
        )
        
    except Exception as e:
        logger.error(f"Error creating supplementary boarding invoice: {e}", exc_info=True)

@receiver(pre_save, sender='boarding.BoardingEnrollment')
def auto_generate_roll_number(sender, instance, **kwargs):
    """
    Automatically generate roll number when creating a new enrollment.
    Handles both None and empty string cases.
    """
    # Check if this is a new enrollment (not yet saved to database)
    is_new = instance._state.adding
    
    # Check if we need to generate a roll number
    needs_roll_number = (
        is_new and  # New enrollment (not an update)
        (not instance.boarding_roll_number or instance.boarding_roll_number.strip() == '')  # No roll number provided
    )
    
    if needs_roll_number:
        from boarding.utils import generate_boarding_roll_number
        
        try:
            instance.boarding_roll_number = generate_boarding_roll_number(
                dormitory=instance.dormitory,
                academic_session=instance.academic_session
            )
            logger.info(
                f"Auto-generated boarding roll number {instance.boarding_roll_number} for "
                f"{instance.student.get_full_name()} in {instance.dormitory.name}"
            )
        except Exception as e:
            logger.error(
                f"Error auto-generating boarding roll number for "
                f"{instance.student.get_full_name()}: {e}",
                exc_info=True
            )