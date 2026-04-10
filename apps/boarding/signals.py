# boarding/signals.py

from django.db.models.signals import pre_delete, post_save, pre_save
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from django.db import transaction
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# ROLL NUMBER GENERATION
# =============================================================================

@receiver(pre_save, sender='boarding.BoardingEnrollment')
def auto_generate_roll_number(sender, instance, **kwargs):
    """
    Automatically generate a boarding roll number when a new enrollment is
    created without one.  Handles both None and empty-string cases.
    """
    if not instance._state.adding:
        return

    needs_roll_number = (
        not instance.boarding_roll_number or
        instance.boarding_roll_number.strip() == ''
    )

    if needs_roll_number:
        from boarding.utils import generate_boarding_roll_number
        try:
            instance.boarding_roll_number = generate_boarding_roll_number(
                dormitory=instance.dormitory,
                academic_session=instance.academic_session,
            )
            logger.info(
                f"Auto-generated boarding roll number {instance.boarding_roll_number} for "
                f"{instance.student.get_full_name()} in {instance.dormitory.name}"
            )
        except Exception as e:
            logger.error(
                f"Error auto-generating boarding roll number for "
                f"{instance.student.get_full_name()}: {e}",
                exc_info=True,
            )


# =============================================================================
# PREVIOUS-STATUS CAPTURE
# =============================================================================

@receiver(pre_save, sender='boarding.BoardingEnrollment')
def capture_previous_status(sender, instance, **kwargs):
    """
    Stash the current DB status on the instance before it is overwritten so
    that auto_add_boarding_fees_to_invoice can detect transitions.

    Sets instance._previous_status = None for new records (adding=True).
    """
    if instance._state.adding:
        instance._previous_status = None
        return

    try:
        instance._previous_status = (
            sender.objects.get(pk=instance.pk).status
        )
    except sender.DoesNotExist:
        instance._previous_status = None


# =============================================================================
# FEE ATTACHMENT  —  fires on approval and reverses on suspension/termination
# =============================================================================

@receiver(post_save, sender='boarding.BoardingEnrollment')
def auto_add_boarding_fees_to_invoice(sender, instance, created, **kwargs):
    """
    Attach or detach boarding fees based on enrollment status transitions.

    ATTACH (→ ACTIVE):
        Any transition from a non-ACTIVE status to ACTIVE triggers fee
        attachment.  This covers both:
          - New enrollments created directly as ACTIVE.
          - Existing PENDING enrollments that are approved.

    DETACH (ACTIVE →  SUSPENDED / TERMINATED / COMPLETED):
        When an enrollment leaves ACTIVE status its boarding fee items are
        removed from the linked invoice (if the invoice is still DRAFT).
        If the invoice is already finalized the finance team must handle it
        via credit note — a warning is logged but no exception is raised.

    SKIPPED when auto_create_invoice is False (bulk-created records).
    """
    if not instance.auto_create_invoice:
        logger.debug(
            f"[BOARDING SIGNAL] Skipped {instance.id} — auto_create_invoice=False"
        )
        return

    previous = getattr(instance, '_previous_status', None)
    current  = instance.status

    logger.info(
        f"[BOARDING SIGNAL] {instance.id}  "
        f"prev={previous!r}  current={current!r}  created={created}"
    )

    # ── Attach on transition TO ACTIVE ──────────────────────────────────────
    if current == 'ACTIVE' and previous != 'ACTIVE':
        if instance.boarding_invoice:
            logger.info(
                f"[BOARDING SIGNAL] Skipped attach — already has invoice "
                f"{instance.boarding_invoice.invoice_number}"
            )
            return
        logger.info(
            f"[BOARDING SIGNAL] {previous!r} → ACTIVE — attaching boarding fees"
        )
        with transaction.atomic():
            _add_boarding_fees_to_student_invoice(instance)
        return

    # ── Detach on transition FROM ACTIVE ────────────────────────────────────
    if previous == 'ACTIVE' and current in ('SUSPENDED', 'TERMINATED', 'COMPLETED'):
        logger.info(
            f"[BOARDING SIGNAL] ACTIVE → {current!r} — removing boarding fees"
        )
        if instance.boarding_invoice:
            with transaction.atomic():
                _remove_boarding_fees_from_invoice(instance)
        else:
            logger.info(
                f"[BOARDING SIGNAL] No invoice linked — nothing to remove"
            )
        return

    logger.debug(
        f"[BOARDING SIGNAL] No fee action required for {previous!r} → {current!r}"
    )


# =============================================================================
# HELPERS  —  ADD
# =============================================================================

def _add_boarding_fees_to_student_invoice(boarding_enrollment):
    """
    Add boarding fees to the student's existing invoice for the session, or
    create a supplementary invoice when the main one is already finalized.
    """
    from fees.models import FeeInvoice

    student = boarding_enrollment.student
    session = boarding_enrollment.academic_session

    logger.info(
        f"Processing boarding fees for {student.get_full_name()} "
        f"in {session.name}"
    )

    existing_invoice = FeeInvoice.objects.filter(
        student=student,
        academic_session=session,
    ).order_by('-created_at').first()

    if not existing_invoice:
        logger.info(
            f"No existing invoice found for {student.get_full_name()} — "
            f"boarding fees will be included when the academic invoice is generated"
        )
        return

    logger.info(
        f"Found invoice {existing_invoice.invoice_number} "
        f"(status={existing_invoice.status})"
    )

    if existing_invoice.status == 'DRAFT':
        _add_boarding_items_to_draft_invoice(existing_invoice, boarding_enrollment)
        boarding_enrollment.boarding_invoice = existing_invoice
        boarding_enrollment.save(update_fields=['boarding_invoice'])

    elif existing_invoice.status in ('PENDING', 'PARTIALLY_PAID', 'PAID', 'OVERDUE'):
        _create_supplementary_boarding_invoice(boarding_enrollment)

    else:
        logger.warning(
            f"Cannot add boarding fees — invoice {existing_invoice.invoice_number} "
            f"has status {existing_invoice.status}"
        )


def _add_boarding_items_to_draft_invoice(invoice, boarding_enrollment):
    """Add boarding fee line items to an existing DRAFT invoice."""
    from fees.models import FeeInvoiceItem, FeesStructure

    if invoice.status != 'DRAFT':
        raise ValueError(
            f"Cannot add items to invoice with status {invoice.status}"
        )

    boarding_fee_structure = FeesStructure.objects.filter(
        applicable_sessions=boarding_enrollment.academic_session,
        boarding_type_filter__in=[
            boarding_enrollment.boarding_type,
            'BOARDER_ONLY',
        ],
        is_active=True,
    ).order_by('priority').first()

    if not boarding_fee_structure:
        logger.warning(
            f"No boarding fee structure found for "
            f"{boarding_enrollment.get_boarding_type_display()} "
            f"in {boarding_enrollment.academic_session.name}"
        )
        return

    logger.info(f"Using fee structure: {boarding_fee_structure.name}")

    student     = boarding_enrollment.student
    session     = boarding_enrollment.academic_session   # FIX 2: needed for get_amount_for_student
    items_added = 0

    for item in boarding_fee_structure.items.all().order_by('display_order'):
        # FIX 1: renamed from is_applicable_to_student() → is_condition_met_for_student()
        if not item.is_condition_met_for_student(student):
            continue
        if not item.is_mandatory:
            continue
        if invoice.items.filter(fee_category=item.fee_category).exists():
            logger.debug(f"Item already exists: {item.fee_category.name}")
            continue

        # FIX 2: pass session as second arg — required for boarding-type-dependent amounts
        amount = item.get_amount_for_student(student, session)

        # FIX 3: FeesStructureItem has no calculate_tax_amount() — compute inline
        if item.is_taxable and item.tax_percentage:
            tax_amount = (
                amount * item.tax_percentage / Decimal('100')
            ).quantize(Decimal('0.01'))
        else:
            tax_amount = Decimal('0.00')

        FeeInvoiceItem.objects.create(
            invoice=invoice,
            fee_category=item.fee_category,
            description=item.get_description(),
            quantity=Decimal('1.00'),
            unit_amount=amount,
            amount=amount,
            tax_percentage=item.tax_percentage,
            tax_amount=tax_amount,
            discount_amount=Decimal('0.00'),
            discount_percentage=Decimal('0.00'),
            scholarship_discount_amount=Decimal('0.00'),
            total_discount_amount=Decimal('0.00'),
            final_amount=amount + tax_amount,
            original_amount=amount,
            amount_in_school_currency=amount + tax_amount,
        )
        items_added += 1
        logger.info(f"Added: {item.fee_category.name} — {amount}")

    if items_added == 0:
        logger.warning("No boarding items added to invoice")
        return

    invoice.recalculate_totals()

    note = f"[Boarding fees added — {boarding_enrollment.get_boarding_type_display()}]"
    invoice.notes = (f"{invoice.notes}\n\n{note}" if invoice.notes else note)
    invoice.save(update_fields=['notes'])

    if invoice.journal_entry and invoice.journal_entry.status == 'DRAFT':
        je_number = invoice.journal_entry.entry_number
        invoice.journal_entry.delete()
        invoice.journal_entry = None
        invoice.save(update_fields=['journal_entry'])
        logger.info(f"Deleted DRAFT journal entry {je_number} — will be recreated")

    from fees.invoice_generators import UnifiedStudentInvoiceGenerator
    UnifiedStudentInvoiceGenerator._create_journal_entry(invoice)

    logger.info(
        f"✅ Added {items_added} boarding items to {invoice.invoice_number}. "
        f"New total: {invoice.total_amount}"
    )

def _create_supplementary_boarding_invoice(boarding_enrollment):
    """Create a separate supplementary invoice when the main one is finalized."""
    from fees.invoice_generators import UnifiedStudentInvoiceGenerator

    student = boarding_enrollment.student
    session = boarding_enrollment.academic_session

    class_enrollment = student.class_enrollments.filter(
        academic_session=session,
        is_active=True,
        completion_status='ONGOING',
    ).first()

    if not class_enrollment:
        logger.error(
            f"Cannot create boarding invoice: {student.get_full_name()} "
            f"has no active class enrollment for {session.name}"
        )
        return

    try:
        invoice = UnifiedStudentInvoiceGenerator.generate(
            class_enrollment,
            include_boarding=True,
            force=True,
        )
        note = "SUPPLEMENTARY INVOICE — Boarding fees added mid-session"
        invoice.notes = (f"{note}\n\n{invoice.notes}" if invoice.notes else note)
        invoice.save(update_fields=['notes'])

        boarding_enrollment.boarding_invoice = invoice
        boarding_enrollment.save(update_fields=['boarding_invoice'])

        logger.info(
            f"✅ Created supplementary invoice {invoice.invoice_number} "
            f"for {student.get_full_name()}"
        )
    except Exception as e:
        logger.error(
            f"Error creating supplementary boarding invoice: {e}",
            exc_info=True,
        )


# =============================================================================
# HELPERS  —  REMOVE
# =============================================================================

def _remove_boarding_fees_from_invoice(boarding_enrollment):
    """
    Remove boarding fee line items from the linked invoice when an enrollment
    leaves ACTIVE status (suspended, terminated, completed).

    Only modifies DRAFT invoices.  If the invoice is already finalized the
    finance team must issue a credit note — a warning is logged and the
    linked invoice reference is preserved for the audit trail.
    """
    invoice = boarding_enrollment.boarding_invoice
    if not invoice:
        return

    if invoice.status not in ('DRAFT', 'VOID'):
        logger.warning(
            f"[BOARDING SIGNAL] Invoice {invoice.invoice_number} is "
            f"{invoice.status} — cannot remove boarding items automatically. "
            f"Finance team must issue a credit note."
        )
        return

    boarding_items = invoice.items.filter(
        fee_category__category_type__in=['BOARDING', 'LAUNDRY']
    )
    removed = boarding_items.count()

    if removed == 0:
        logger.info(
            f"[BOARDING SIGNAL] No boarding items on "
            f"{invoice.invoice_number} to remove"
        )
        return

    boarding_items.delete()
    logger.info(
        f"[BOARDING SIGNAL] Removed {removed} boarding items from "
        f"{invoice.invoice_number}"
    )

    if invoice.status != 'VOID':
        invoice.recalculate_totals()

    note = f"[Boarding enrollment {boarding_enrollment.get_status_display()} — boarding fees removed]"
    invoice.notes = (f"{invoice.notes}\n\n{note}" if invoice.notes else note)
    invoice.save(update_fields=['notes'])

    # Regenerate journal entry with updated totals
    if invoice.journal_entry and invoice.journal_entry.status == 'DRAFT':
        je_number = invoice.journal_entry.entry_number
        invoice.journal_entry.delete()
        invoice.journal_entry = None
        invoice.save(update_fields=['journal_entry'])
        logger.info(f"[BOARDING SIGNAL] Deleted DRAFT journal entry {je_number}")

    from fees.invoice_generators import UnifiedStudentInvoiceGenerator
    UnifiedStudentInvoiceGenerator._create_journal_entry(invoice)

    logger.info(
        f"[BOARDING SIGNAL] ✅ Removed boarding fees from "
        f"{invoice.invoice_number}. New total: {invoice.total_amount}"
    )


# =============================================================================
# DELETION GUARD
# =============================================================================

@receiver(pre_delete, sender='boarding.BoardingEnrollment')
def boarding_enrollment_pre_delete(sender, instance, **kwargs):
    """
    Block deletion when the linked invoice cannot be safely modified.

    SAFE (allows deletion, removes boarding items):
        Invoice is DRAFT or VOID, no payments, journal entry is DRAFT or absent.

    UNSAFE (raises ValidationError, blocks deletion):
        Invoice is finalized, payments received, or journal entry is posted/reversed.
        In these cases mark the enrollment TERMINATED instead and issue a credit note.
    """
    if not instance.boarding_invoice:
        logger.info(
            f"Deleting enrollment {instance.id} — no invoice linked"
        )
        return

    invoice = instance.boarding_invoice

    # 1. Journal entry status
    if invoice.journal_entry:
        je_status = invoice.journal_entry.status
        if je_status == 'POSTED':
            raise ValidationError({
                'boarding_invoice': (
                    f"Cannot delete: journal entry {invoice.journal_entry.entry_number} "
                    f"is already posted. Mark the enrollment as TERMINATED instead "
                    f"and issue a credit note for unused boarding fees."
                )
            })
        if je_status == 'REVERSED':
            raise ValidationError({
                'boarding_invoice': (
                    f"Cannot delete: journal entry {invoice.journal_entry.entry_number} "
                    f"has been reversed. Mark the enrollment as TERMINATED instead."
                )
            })

    # 2. Invoice status
    if invoice.status not in ('DRAFT', 'VOID'):
        raise ValidationError({
            'boarding_invoice': (
                f"Cannot delete: invoice {invoice.invoice_number} has status "
                f"{invoice.get_status_display()}. Mark the enrollment as TERMINATED "
                f"and issue a credit note for unused boarding fees."
            )
        })

    # 3. Payments
    if invoice.paid_amount > 0:
        raise ValidationError({
            'boarding_invoice': (
                f"Cannot delete: invoice {invoice.invoice_number} has received "
                f"payments of {invoice.paid_amount}. Mark the enrollment as TERMINATED "
                f"and process a refund if applicable."
            )
        })

    # All checks passed — remove boarding items
    boarding_items = invoice.items.filter(
        fee_category__category_type__in=['BOARDING', 'LAUNDRY']
    )
    removed = boarding_items.count()

    if removed > 0:
        boarding_items.delete()
        logger.info(
            f"Removed {removed} boarding items from "
            f"{invoice.status} invoice {invoice.invoice_number}"
        )

        if invoice.journal_entry and invoice.journal_entry.status == 'DRAFT':
            je_number = invoice.journal_entry.entry_number
            invoice.journal_entry.delete()
            invoice.journal_entry = None
            invoice.save(update_fields=['journal_entry'])
            logger.info(f"Deleted DRAFT journal entry {je_number}")

        if invoice.status != 'VOID':
            invoice.recalculate_totals()

        note = "[Boarding enrollment deleted — boarding fees removed]"
        invoice.notes = (f"{invoice.notes}\n\n{note}" if invoice.notes else note)
        invoice.save(update_fields=['notes'])

        logger.info(
            f"✅ Cleaned up invoice {invoice.invoice_number} after enrollment "
            f"deletion. New total: {invoice.total_amount}"
        )
    else:
        logger.warning(
            f"No boarding items found on {invoice.invoice_number} to remove"
        )