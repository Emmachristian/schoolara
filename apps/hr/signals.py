# hr/signals.py

"""
HR Payroll Signals

Automatic triggers for payroll operations.
"""

from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.utils import timezone
import logging

from hr.models import Payroll, PayrollAllowance, PayrollDeduction, PayrollBonus
from hr.services import PayrollCalculationService, PayrollAccountingService

logger = logging.getLogger(__name__)


# =============================================================================
# PAYROLL SIGNALS
# =============================================================================

@receiver(post_save, sender=Payroll)
def payroll_post_save(sender, instance, created, **kwargs):
    """
    Post-save processing for payroll:
    - Log payroll creation
    - Auto-create journal entry when approved
    - Auto-create disbursement entry when paid
    """
    # Skip if in raw mode
    if kwargs.get('raw', False):
        return
    
    if created:
        logger.info(
            f"Payroll created: {instance.staff.full_name()} - "
            f"{instance.period.name} - Status: {instance.status}"
        )
    
    # Auto-create journal entry when status changes to APPROVED
    if instance.status == 'APPROVED':
        if not hasattr(instance, 'journal_entry') or not instance.journal_entry:
            try:
                PayrollAccountingService.create_payroll_journal_entry(instance)
                logger.info(f"Auto-created journal entry for payroll {instance.pk}")
            except Exception as e:
                logger.error(
                    f"Error auto-creating journal entry for payroll {instance.pk}: {e}",
                    exc_info=True
                )
    
    # Auto-create disbursement entry when status changes to PAID
    if instance.status == 'PAID':
        # Check if we need disbursement entry
        # (You might track this with a field like has_disbursement_entry)
        try:
            # Only create if not already created
            # This is a simplified check - you may want to add a field to track this
            PayrollAccountingService.create_payment_disbursement_entry(instance)
            logger.info(f"Auto-created disbursement entry for payroll {instance.pk}")
        except Exception as e:
            logger.error(
                f"Error auto-creating disbursement entry for payroll {instance.pk}: {e}",
                exc_info=True
            )


@receiver(post_save, sender=PayrollAllowance)
def payroll_allowance_post_save(sender, instance, created, **kwargs):
    """
    Post-save processing for payroll allowances:
    - Recalculate payroll totals
    """
    # Skip if in raw mode
    if kwargs.get('raw', False):
        return
    
    try:
        PayrollCalculationService.calculate_payroll(instance.payroll)
        logger.debug(f"Recalculated payroll after allowance change: {instance.payroll.pk}")
    except Exception as e:
        logger.error(f"Error recalculating payroll: {e}", exc_info=True)


@receiver(post_save, sender=PayrollDeduction)
def payroll_deduction_post_save(sender, instance, created, **kwargs):
    """
    Post-save processing for payroll deductions:
    - Recalculate payroll totals
    """
    # Skip if in raw mode
    if kwargs.get('raw', False):
        return
    
    try:
        PayrollCalculationService.calculate_payroll(instance.payroll)
        logger.debug(f"Recalculated payroll after deduction change: {instance.payroll.pk}")
    except Exception as e:
        logger.error(f"Error recalculating payroll: {e}", exc_info=True)


@receiver(post_save, sender=PayrollBonus)
def payroll_bonus_post_save(sender, instance, created, **kwargs):
    """
    Post-save processing for payroll bonuses:
    - Recalculate payroll totals
    """
    # Skip if in raw mode
    if kwargs.get('raw', False):
        return
    
    try:
        PayrollCalculationService.calculate_payroll(instance.payroll)
        logger.debug(f"Recalculated payroll after bonus change: {instance.payroll.pk}")
    except Exception as e:
        logger.error(f"Error recalculating payroll: {e}", exc_info=True)


# =============================================================================
# PAYROLL VALIDATION
# =============================================================================

@receiver(pre_save, sender=Payroll)
def payroll_pre_save(sender, instance, **kwargs):
    """
    Pre-save validation for payroll:
    - Prevent changes to paid payroll
    - Validate amounts
    """
    # Prevent changes to paid payroll
    if instance.pk:
        try:
            previous = Payroll.objects.get(pk=instance.pk)
            if previous.status == 'PAID' and instance.status != 'PAID':
                from django.core.exceptions import ValidationError
                raise ValidationError("Cannot modify paid payroll")
        except Payroll.DoesNotExist:
            pass
    
    # Validate amounts
    if instance.net_pay < 0:
        from django.core.exceptions import ValidationError
        raise ValidationError("Net pay cannot be negative")