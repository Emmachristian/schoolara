# academics/signals.py
"""
Signal handlers for the academics app.

RESPONSIBILITY BOUNDARIES
─────────────────────────
Invoice creation
    Handled EXPLICITLY by:
      • enrollment_create view (single enrolment)
      • BulkEnrollmentService._create_invoices() (bulk enrolment)
    The auto_create_invoice field is read directly by those callers.
    NO signal here creates invoices.

Roll-number generation
    auto_generate_roll_number (pre_save) fires only for NEW enrolment records
    (_state.adding == True).  reset_class_roll_numbers() in utils.py updates
    existing records via save(update_fields=['roll_number']) and intentionally
    bypasses this signal — see the IMPORTANT note in that function.

Validation
    Business-rule validation lives in model clean() methods, not here.
    Pre-save stubs in this file do only what a signal uniquely enables
    (e.g. reading the pre-save DB state to detect field changes).

Session deduplication
    AcademicSession.save() already calls
        AcademicSession.objects.filter(is_current=True).exclude(pk=self.pk).update(is_current=False)
    ensure_only_one_current_session() (bottom of file) is a repair utility for
    management commands / data-migration use; it additionally sorts by start_date
    to pick the most recent session when multiple are flagged.  The two approaches
    are intentionally slightly different — if the model's behaviour changes,
    update this utility accordingly.
"""

from django.db.models.signals import (
    post_save, pre_save, post_delete, m2m_changed, pre_delete,
)
from django.db.models import Q
from django.dispatch import receiver
from django.utils import timezone
from django.core.exceptions import ValidationError
from academics.models import Subject
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# ACADEMIC SESSION SIGNALS
# =============================================================================

@receiver(post_save, sender='academics.AcademicSession')
def academic_session_post_save(sender, instance, created, **kwargs):
    """
    Post-save handler for AcademicSession.

    On creation of a regular (non-special) session, attempt to auto-create a
    FiscalPeriod aligned with the session dates.  Failures are logged but do not
    propagate — the session is already saved at this point.
    """
    if created:
        logger.info(
            f"New academic session created: {instance.name} "
            f"({'Special' if instance.is_special_session else 'Regular'})"
        )

        if not instance.is_special_session:
            try:
                from core.models import FiscalPeriod
                fiscal_period = FiscalPeriod.create_for_academic_session(
                    academic_session=instance,
                    grace_days=60,
                )
                logger.info(f"Auto-created fiscal period: {fiscal_period}")
            except ImportError:
                logger.debug("FiscalPeriod model not available")
            except Exception as e:
                logger.error(f"Error auto-creating fiscal period: {e}")
    else:
        logger.info(f"Academic session updated: {instance.name}")


@receiver(post_delete, sender='academics.AcademicSession')
def academic_session_post_delete(sender, instance, **kwargs):
    """Log academic session deletion."""
    logger.warning(f"Academic session deleted: {instance.name}")


# =============================================================================
# CLASS SIGNALS
# =============================================================================

@receiver(post_save, sender='academics.Class')
def class_post_save(sender, instance, created, **kwargs):
    """
    Post-save handler for Class.

    On creation, auto-assign every compulsory subject that is applicable to this
    class's academic level.  Uses get_or_create so re-saving a class never
    produces duplicate assignments.
    """
    if not created:
        return

    logger.info(
        f"New class created: {instance.get_display_name()} "
        f"for session {instance.academic_session.name}"
    )

    try:
        from .models import Subject, ClassSubject

        compulsory_subjects = Subject.objects.filter(
            is_compulsory=True,
            is_active=True,
        ).filter(
            Q(applicable_levels__isnull=True) |
            Q(applicable_levels=instance.academic_level)
        ).distinct()

        for subject in compulsory_subjects:
            ClassSubject.objects.get_or_create(
                class_instance=instance,
                subject=subject,
                defaults={
                    'is_optional':    False,
                    'hours_per_week': 3,
                },
            )

        if compulsory_subjects.exists():
            logger.info(
                f"Auto-assigned {compulsory_subjects.count()} compulsory "
                f"subject(s) to {instance.get_display_name()}"
            )

    except Exception as e:
        logger.error(f"Error auto-assigning class subjects: {e}")


# =============================================================================
# CLASS SUBJECT SIGNALS
# =============================================================================

@receiver(post_save, sender='academics.ClassSubject')
def class_subject_post_save(sender, instance, created, **kwargs):
    """Log subject assignment to a class."""
    if created:
        logger.info(
            f"Subject assigned: {instance.subject.name} to "
            f"{instance.class_instance.get_display_name()}"
        )


# =============================================================================
# HOLIDAY SIGNALS
# =============================================================================

@receiver(post_save, sender='academics.Holiday')
def holiday_post_save(sender, instance, created, **kwargs):
    """
    Post-save handler for Holiday.

    Queues a notification when the holiday is first created and either
    notify_parents or notify_staff is set.  The actual notification dispatch
    is a stub — wire this into your notification system when ready.
    """
    if not created:
        return

    logger.info(f"New holiday created: {instance.name} ({instance.start_date})")

    if instance.notify_parents or instance.notify_staff:
        try:
            # TODO: replace with actual notification dispatch
            logger.info(f"Holiday notification queued for: {instance.name}")
        except Exception as e:
            logger.error(f"Error queuing holiday notification: {e}")


# =============================================================================
# SUBJECT SIGNALS
# =============================================================================

@receiver(m2m_changed, sender=Subject.prerequisites.through)
def subject_prerequisites_changed(sender, instance, action, **kwargs):
    """
    Detect and log circular prerequisite dependencies whenever the
    prerequisites M2M relation changes.

    Only logs a warning — it does not raise.  The academic_level_pre_save
    signal (below) uses the same pattern for level progression.
    """
    if action not in ('post_add', 'post_remove'):
        return

    try:
        visited = set()
        stack   = [instance]

        while stack:
            current = stack.pop()
            if current.id in visited:
                logger.warning(
                    f"Circular prerequisite dependency detected "
                    f"for subject: {instance.name}"
                )
                break
            visited.add(current.id)
            stack.extend(current.prerequisites.all())

    except Exception as e:
        logger.error(f"Error checking subject prerequisites: {e}")


# =============================================================================
# ACADEMIC LEVEL SIGNALS
# =============================================================================

@receiver(pre_save, sender='academics.AcademicLevel')
def academic_level_pre_save(sender, instance, **kwargs):
    """
    Guard against circular chains in the level progression before saving.

    Raises ValidationError if next_level eventually leads back to instance,
    preventing an infinite loop in get_level_progression_path().
    """
    if not instance.next_level:
        return

    current    = instance.next_level
    visited    = {instance.id}
    max_iter   = 20
    iterations = 0

    while current and iterations < max_iter:
        if current.id in visited:
            raise ValidationError(
                "Circular progression detected in level progression chain"
            )
        visited.add(current.id)
        current    = getattr(current, 'next_level', None)
        iterations += 1


# =============================================================================
# CLASSROOM SIGNALS
# =============================================================================

@receiver(post_save, sender='academics.ClassRoom')
def classroom_post_save(sender, instance, created, **kwargs):
    """Log classroom creation."""
    if created:
        logger.info(
            f"New classroom created: {instance.room_number} — {instance.name} "
            f"(Type: {instance.get_room_type_display()})"
        )


# =============================================================================
# STUDENT CLASS ENROLMENT — PRE-SAVE SIGNALS
# (Two separate receivers on the same sender.  Django fires all pre_save
#  receivers before the INSERT/UPDATE, in registration order.)
# =============================================================================

@receiver(pre_save, sender='academics.StudentClassEnrollment')
def auto_generate_roll_number(sender, instance, **kwargs):
    """
    Automatically generate a roll number for NEW enrolments that do not
    already have one.

    NEW RECORDS ONLY — _state.adding == True.
    Existing records updated via reset_class_roll_numbers() in utils.py bypass
    this signal intentionally (those calls use save(update_fields=['roll_number'])
    on already-persisted instances).  If this signal ever needs to cover updates
    as well, revise reset_class_roll_numbers() accordingly.
    """
    is_new           = instance._state.adding
    needs_roll_number = (
        is_new and
        (not instance.roll_number or instance.roll_number.strip() == '')
    )

    if not needs_roll_number:
        return

    from academics.utils import generate_class_roll_number

    try:
        instance.roll_number = generate_class_roll_number(
            class_instance=instance.class_instance,
            academic_session=instance.academic_session,
        )
        logger.info(
            f"Auto-generated roll number {instance.roll_number} for "
            f"{instance.student.get_full_name()} in "
            f"{instance.class_instance.get_display_name()}"
        )
    except Exception as e:
        logger.error(
            f"Error auto-generating roll number for "
            f"{instance.student.get_full_name()}: {e}",
            exc_info=True,
        )


@receiver(pre_save, sender='academics.StudentClassEnrollment')
def enrollment_status_change_handler(sender, instance, **kwargs):
    """
    React to completion_status changes on existing enrolment records.

    • Auto-sets completion_date when status moves to a terminal state
      (COMPLETED, DROPPED, TRANSFERRED, WITHDRAWN) and none is set yet.
    • Marks the enrolment inactive whenever it is no longer ONGOING.

    Skipped entirely for new records (no prior state to compare against).
    """
    if not instance.pk:
        return

    try:
        old = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return
    except Exception as e:
        logger.error(f"Error in enrollment_status_change_handler: {e}")
        return

    if old.completion_status == instance.completion_status:
        return

    logger.info(
        f"Enrolment status changed for {instance.student}: "
        f"{old.completion_status} → {instance.completion_status}"
    )

    if instance.completion_status in ('COMPLETED', 'DROPPED', 'TRANSFERRED', 'WITHDRAWN'):
        if not instance.completion_date:
            instance.completion_date = timezone.now().date()
            logger.debug(f"Auto-set completion_date to {instance.completion_date}")

    if instance.completion_status != 'ONGOING':
        instance.is_active = False


# =============================================================================
# STUDENT CLASS ENROLMENT — POST-SAVE SIGNAL
# =============================================================================

@receiver(post_save, sender='academics.StudentClassEnrollment')
def enrollment_post_save(sender, instance, created, **kwargs):
    """
    Post-save handler for StudentClassEnrollment.

    INVOICE CREATION IS NOT DONE HERE.  It is handled explicitly by:
      • enrollment_create view (single enrolment)
      • BulkEnrollmentService._create_invoices() (bulk enrolment)
    The auto_create_invoice field is read directly by those callers.

    This signal handles:
      1. Auto-creating the AcademicProgress record for the student / session pair.
      2. Updating the student's current_academic_level to reflect the new enrolment.
    """
    if not created:
        return

    logger.info(
        f"New enrolment: {instance.student.get_full_name()} enrolled in "
        f"{instance.class_instance} for {instance.academic_session}"
    )

    # ── 1. AcademicProgress ────────────────────────────────────────────────
    try:
        from academics.models import AcademicProgress

        progress, progress_created = AcademicProgress.objects.get_or_create(
            student=instance.student,
            academic_session=instance.academic_session,
            defaults={
                'class_enrollment': instance,
                'total_subjects':   instance.class_instance.subjects.filter(
                    is_active=True
                ).count(),
            },
        )

        if progress_created:
            logger.info(
                f"Auto-created AcademicProgress for {instance.student} — "
                f"{instance.academic_session}"
            )
        else:
            # Progress record already existed (e.g. from a previous enrolment
            # attempt that was rolled back).  Update the enrolment link only.
            progress.class_enrollment = instance
            progress.save(update_fields=['class_enrollment'])
            logger.debug(
                f"Updated class_enrollment on existing AcademicProgress "
                f"for {instance.student}"
            )

    except Exception as e:
        logger.error(f"Error creating/updating AcademicProgress: {e}")

    # ── 2. Student current academic level ──────────────────────────────────
    if instance.is_active and instance.completion_status == 'ONGOING':
        try:
            instance.student.current_academic_level = (
                instance.class_instance.academic_level
            )
            instance.student.save(update_fields=['current_academic_level'])
            logger.debug(
                f"Updated {instance.student}'s current level to "
                f"{instance.class_instance.academic_level}"
            )
        except Exception as e:
            logger.error(f"Error updating student current level: {e}")


# =============================================================================
# STUDENT CLASS ENROLMENT — DELETION SIGNALS
# =============================================================================

@receiver(pre_delete, sender='academics.StudentClassEnrollment')
def class_enrollment_pre_delete(sender, instance, **kwargs):
    """
    Guard enrolment deletion against invoices that cannot be safely removed.

    Decision matrix:
      No invoice linked                              → allow deletion
      Invoice is VOID or CANCELLED                   → delete invoice, then allow
      Invoice is DRAFT with no payments              → delete invoice, then allow
      Invoice is finalised / has payments            → raise ValidationError (block)
    """
    logger.info(
        f"pre_delete fired for enrolment {instance.id} — "
        f"{instance.student.get_full_name()} / "
        f"{instance.class_instance} / {instance.academic_session}"
    )

    if not instance.academic_invoice:
        logger.info("No invoice linked — allowing deletion")
        return

    invoice        = instance.academic_invoice
    invoice_number = invoice.invoice_number
    invoice_status = invoice.status

    logger.info(
        f"Invoice found: {invoice_number} "
        f"(status={invoice_status}, paid={invoice.paid_amount})"
    )

    # VOID or CANCELLED — safe to delete alongside the enrolment
    if invoice_status in ('VOID', 'CANCELLED'):
        try:
            invoice.delete()
            logger.info(
                f"Deleted {invoice_status} invoice {invoice_number} "
                f"alongside enrolment"
            )
        except Exception as e:
            logger.error(
                f"Error deleting {invoice_status} invoice: {e}", exc_info=True
            )
            raise
        return

    # DRAFT with no payments — safe to delete
    can_modify, reason = invoice.can_be_safely_modified()
    if can_modify:
        try:
            invoice.delete()
            logger.info(
                f"Deleted DRAFT invoice {invoice_number} alongside enrolment"
            )
        except Exception as e:
            logger.error(f"Error deleting DRAFT invoice: {e}", exc_info=True)
            raise
        return

    # Finalised invoice with payments — block deletion
    logger.error(
        f"Blocking deletion of enrolment {instance.id}: {reason}"
    )
    raise ValidationError(
        f"Cannot delete this enrolment because it has a finalised invoice "
        f"({invoice_number}). {reason}\n\n"
        f"Please cancel or void the invoice and process any necessary refunds "
        f"before removing the enrolment."
    )


@receiver(post_delete, sender='academics.StudentClassEnrollment')
def enrollment_post_delete(sender, instance, **kwargs):
    """Log enrolment deletion."""
    logger.warning(
        f"Enrolment deleted: {instance.student.get_full_name()} from "
        f"{instance.class_instance} ({instance.academic_session})"
    )


# =============================================================================
# HELPER UTILITIES
# =============================================================================

def ensure_only_one_current_session():
    """
    Repair utility — ensure exactly one session is flagged is_current=True.

    Intended for use in management commands or data-migration scripts when
    a data-integrity issue has left multiple sessions marked as current.

    NOTE ON ORDERING:
        This function retains the session with the most recent start_date.
        AcademicSession.save() uses a different strategy — it un-flags all
        *other* sessions without sorting, preserving whichever was already
        current before the save.  If you change the model's behaviour,
        update this function to match.
    """
    from .models import AcademicSession

    current_sessions = AcademicSession.objects.filter(is_current=True)

    if current_sessions.count() > 1:
        latest = current_sessions.order_by('-start_date').first()
        current_sessions.exclude(pk=latest.pk).update(is_current=False)
        logger.warning(
            f"Multiple current sessions found. Retained only: {latest.name}"
        )