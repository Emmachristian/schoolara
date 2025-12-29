# fees/signals.py

"""
Fee Management Signal Handlers

Auto-processing for:
- Invoice number generation and account assignment
- Payment number/receipt generation and account assignment  
- Refund number generation and account assignment
- Student account balance updates
- Invoice total recalculation
- Audit logging
- Data integrity validation
"""

from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

from academics.models import StudentClassEnrollment
from boarding.models import BoardingEnrollment

from fees.invoice_generators import (
    ClassEnrollmentInvoiceGenerator,
    BoardingEnrollmentInvoiceGenerator
)

# Import number generation from utils.py (centralized)
from fees.utils import (
    generate_invoice_number,
    generate_payment_number,
    generate_receipt_number,
    generate_refund_number,
    generate_scholarship_application_number,
)


# =============================================================================
# INVOICE SIGNALS
# =============================================================================

@receiver(pre_save, sender='fees.FeeInvoice')
def fee_invoice_pre_save(sender, instance, **kwargs):
    """
    Pre-save processing for fee invoices:
    - Auto-generate invoice number
    - Auto-assign accounts from FinancialSettings
    - Set fiscal period if not set
    """
    # Auto-generate invoice number if not set
    if not instance.invoice_number:
        instance.invoice_number = generate_invoice_number()
        logger.info(f"Generated invoice number: {instance.invoice_number}")
    
    # Auto-assign accounts if not set (only for new invoices)
    if not instance.pk:
        from core.models import FinancialSettings
        
        try:
            settings = FinancialSettings.get_instance()
            
            if settings:
                # Assign revenue account
                if not instance.revenue_account:
                    # Use service revenue account as default for fee invoices
                    instance.revenue_account = settings.default_service_revenue_account
                
                # Assign receivable account
                if not instance.receivable_account:
                    instance.receivable_account = settings.default_receivables_account
                
                logger.debug(f"Auto-assigned accounts to invoice {instance.invoice_number}")
            else:
                logger.warning("FinancialSettings not found - invoice accounts not auto-assigned")
        
        except Exception as e:
            logger.error(f"Error auto-assigning invoice accounts: {e}")
    
    # Set fiscal period if not set
    if not instance.fiscal_period:
        from core.models import FiscalPeriod
        instance.fiscal_period = FiscalPeriod.get_current_fiscal_period()
        if not instance.fiscal_period:
            logger.warning(f"No active fiscal period found for invoice {instance.invoice_number}")


@receiver(post_save, sender='fees.FeeInvoice')
def fee_invoice_post_save(sender, instance, created, **kwargs):
    """
    Post-save processing for fee invoices:
    - Update student account balance
    - Log invoice creation
    """
    # Skip if in raw mode (fixtures, migrations)
    if kwargs.get('raw', False):
        return
    
    if created:
        logger.info(
            f"Invoice created: {instance.invoice_number} - "
            f"Student: {instance.student.get_full_name()} - "
            f"Amount: {instance.total_amount}"
        )
        
        # Update student account
        try:
            from fees.models import StudentAccount, AccountTransaction
            
            # Get or create student account
            student_account, _ = StudentAccount.objects.get_or_create(
                student=instance.student
            )
            
            # Calculate new balance (negative balance = amount owed)
            new_balance = student_account.current_balance - instance.total_amount
            
            # Create transaction record
            AccountTransaction.objects.create(
                student_account=student_account,
                transaction_type='INVOICE',
                amount=-instance.total_amount,  # Negative = charge
                description=f"Invoice {instance.invoice_number}",
                balance_after=new_balance,
                invoice=instance,
                academic_session=instance.academic_session,
                fiscal_period=instance.fiscal_period,
                reference_number=instance.invoice_number
            )
            
            # Update account totals (✅ CORRECT FIELD NAME: total_fees_charged)
            student_account.current_balance = new_balance
            student_account.total_fees_charged += instance.total_amount
            student_account.last_transaction_date = timezone.now()
            student_account.save()
            
            logger.debug(f"Updated student account for {instance.student.get_full_name()}")
        
        except Exception as e:
            logger.error(f"Error updating student account: {e}", exc_info=True)


# =============================================================================
# PAYMENT SIGNALS
# =============================================================================

@receiver(pre_save, sender='fees.Payment')
def payment_pre_save(sender, instance, **kwargs):
    """
    Pre-save processing for payments:
    - Auto-generate payment number
    - Auto-generate receipt number
    - Auto-assign accounts from FinancialSettings
    - Set fiscal period if not set
    """
    # Auto-generate payment number if not set
    if not instance.payment_number:
        instance.payment_number = generate_payment_number()
        logger.info(f"Generated payment number: {instance.payment_number}")
    
    # Auto-generate receipt number if not set and receipt should be issued
    if not instance.receipt_number and instance.receipt_issued:
        instance.receipt_number = generate_receipt_number()
        logger.info(f"Generated receipt number: {instance.receipt_number}")
    
    # Auto-assign accounts if not set (only for new payments)
    if not instance.pk:
        from core.models import FinancialSettings
        
        try:
            settings = FinancialSettings.get_instance()
            
            if settings:
                # Assign deposit account based on payment method
                if not instance.deposit_account:
                    if hasattr(instance.payment_method, 'is_cash') and instance.payment_method.is_cash:
                        instance.deposit_account = settings.default_cash_account
                    elif hasattr(instance.payment_method, 'code'):
                        if instance.payment_method.code == 'MOBILE_MONEY':
                            instance.deposit_account = settings.mobile_money_clearing_account
                        elif instance.payment_method.code == 'BANK':
                            instance.deposit_account = settings.default_bank_account
                        else:
                            instance.deposit_account = settings.default_cash_account
                    else:
                        # Fallback to cash account
                        instance.deposit_account = settings.default_cash_account
                
                # Assign receivable account
                if not instance.receivable_account:
                    instance.receivable_account = settings.default_receivables_account
                
                # Assign processing fee account if there's a processing fee
                if not instance.processing_fee_account and hasattr(instance, 'processing_fee_amount') and instance.processing_fee_amount > 0:
                    instance.processing_fee_account = settings.payment_processing_fee_account
                
                logger.debug(f"Auto-assigned accounts to payment {instance.payment_number}")
            else:
                logger.warning("FinancialSettings not found - payment accounts not auto-assigned")
        
        except Exception as e:
            logger.error(f"Error auto-assigning payment accounts: {e}")
    
    # Set fiscal period if not set
    if not instance.fiscal_period:
        from core.models import FiscalPeriod
        instance.fiscal_period = FiscalPeriod.get_current_fiscal_period()
        if not instance.fiscal_period:
            logger.warning(f"No active fiscal period found for payment {instance.payment_number}")
    
    # Set receipt issue date if receipt is issued but date not set
    if instance.receipt_issued and not instance.receipt_issued_date:
        instance.receipt_issued_date = timezone.now()


@receiver(post_save, sender='fees.Payment')
def payment_post_save(sender, instance, created, **kwargs):
    """
    Post-save processing for payments:
    - Update invoice balance
    - Update student account
    - Log payment
    """
    # Skip if in raw mode
    if kwargs.get('raw', False):
        return
    
    if created:
        logger.info(
            f"Payment created: {instance.payment_number} - "
            f"Student: {instance.student.get_full_name()} - "
            f"Amount: {instance.amount}"
        )
        
        # Update invoice balance if linked to an invoice
        if instance.invoice:
            try:
                invoice = instance.invoice
                invoice.paid_amount += instance.amount_applied_to_invoice
                invoice.balance = invoice.total_amount - invoice.paid_amount
                
                # Update invoice status
                if invoice.balance <= 0:
                    invoice.status = 'PAID'
                elif invoice.paid_amount > 0:
                    invoice.status = 'PARTIALLY_PAID'
                
                invoice.save()
                
                logger.debug(f"Updated invoice {invoice.invoice_number} balance: {invoice.balance}")
            
            except Exception as e:
                logger.error(f"Error updating invoice balance: {e}", exc_info=True)
        
        # Update student account
        try:
            from fees.models import StudentAccount, AccountTransaction
            
            # Get or create student account
            student_account, _ = StudentAccount.objects.get_or_create(
                student=instance.student
            )
            
            # Calculate new balance (positive = credit to student)
            new_balance = student_account.current_balance + instance.amount
            
            # Create transaction record
            AccountTransaction.objects.create(
                student_account=student_account,
                transaction_type='PAYMENT',
                amount=instance.amount,
                description=f"Payment {instance.payment_number}",
                balance_after=new_balance,
                invoice=instance.invoice,
                payment=instance,
                academic_session=instance.academic_session,
                fiscal_period=instance.fiscal_period,
                reference_number=instance.payment_number
            )
            
            # Update account totals (✅ CORRECT FIELD NAMES)
            student_account.current_balance = new_balance
            student_account.total_payments_received += instance.amount
            student_account.last_payment_date = timezone.now()
            student_account.last_transaction_date = timezone.now()
            student_account.save()
            
            logger.debug(f"Updated student account for {instance.student.get_full_name()}")
        
        except Exception as e:
            logger.error(f"Error updating student account: {e}", exc_info=True)


# =============================================================================
# REFUND SIGNALS
# =============================================================================

@receiver(pre_save, sender='fees.Refund')
def refund_pre_save(sender, instance, **kwargs):
    """
    Pre-save processing for refunds:
    - Auto-generate refund number (using centralized function from utils.py)
    - Auto-assign accounts from FinancialSettings
    - Set fiscal period if not set
    """
    # Auto-generate refund number if not set (imported from utils.py)
    if not instance.refund_number:
        instance.refund_number = generate_refund_number()
        logger.info(f"Generated refund number: {instance.refund_number}")
    
    # Auto-assign accounts if not set (only for new refunds)
    if not instance.pk:
        from core.models import FinancialSettings
        
        try:
            settings = FinancialSettings.get_instance()
            
            if settings:
                # Assign refund account (where money comes from)
                if not instance.refund_account:
                    if hasattr(instance.payment_method, 'is_cash') and instance.payment_method.is_cash:
                        instance.refund_account = settings.default_cash_account
                    else:
                        instance.refund_account = settings.default_bank_account
                
                # Assign receivable account
                if not instance.receivable_account:
                    instance.receivable_account = settings.default_receivables_account
                
                # Assign revenue reversal account
                if not instance.revenue_reversal_account:
                    instance.revenue_reversal_account = settings.default_service_revenue_account
                
                logger.debug(f"Auto-assigned accounts to refund {instance.refund_number}")
            else:
                logger.warning("FinancialSettings not found - refund accounts not auto-assigned")
        
        except Exception as e:
            logger.error(f"Error auto-assigning refund accounts: {e}")
    
    # Set fiscal period if not set
    if not instance.fiscal_period:
        from core.models import FiscalPeriod
        instance.fiscal_period = FiscalPeriod.get_current_fiscal_period()


@receiver(post_save, sender='fees.Refund')
def refund_post_save(sender, instance, created, **kwargs):
    """
    Post-save processing for refunds:
    - Update invoice balance
    - Update student account
    - Log refund
    """
    # Skip if in raw mode
    if kwargs.get('raw', False):
        return
    
    if created:
        logger.info(
            f"Refund created: {instance.refund_number} - "
            f"Student: {instance.student.get_full_name()} - "
            f"Amount: {instance.refund_amount}"  # ✅ CORRECT FIELD NAME
        )
        
        # Update invoice balance if linked to an invoice
        if instance.invoice:
            try:
                invoice = instance.invoice
                invoice.paid_amount -= instance.refund_amount  # ✅ CORRECT
                invoice.balance = invoice.total_amount - invoice.paid_amount
                
                # Update invoice status
                if invoice.balance <= 0:
                    invoice.status = 'PAID'
                elif invoice.paid_amount > 0:
                    invoice.status = 'PARTIALLY_PAID'
                else:
                    invoice.status = 'PENDING'
                
                invoice.save()
                
                logger.debug(f"Updated invoice {invoice.invoice_number} after refund")
            
            except Exception as e:
                logger.error(f"Error updating invoice after refund: {e}", exc_info=True)
        
        # Update student account
        try:
            from fees.models import StudentAccount, AccountTransaction
            
            # Get or create student account
            student_account, _ = StudentAccount.objects.get_or_create(
                student=instance.student
            )
            
            # Calculate new balance (negative = amount owed by student)
            new_balance = student_account.current_balance - instance.refund_amount  # ✅ CORRECT
            
            # Create transaction record
            AccountTransaction.objects.create(
                student_account=student_account,
                transaction_type='REFUND',
                amount=-instance.refund_amount,  # ✅ CORRECT - Negative = refund
                description=f"Refund {instance.refund_number}",
                balance_after=new_balance,
                invoice=instance.invoice,
                academic_session=instance.academic_session,
                fiscal_period=instance.fiscal_period,
                reference_number=instance.refund_number
            )
            
            # Update account totals (✅ CORRECT FIELD NAME: total_refunds_issued)
            student_account.current_balance = new_balance
            student_account.total_refunds_issued += instance.refund_amount
            student_account.last_transaction_date = timezone.now()
            student_account.save()
            
            logger.debug(f"Updated student account for refund {instance.refund_number}")
        
        except Exception as e:
            logger.error(f"Error updating student account after refund: {e}", exc_info=True)


# =============================================================================
# FEE INVOICE ITEM SIGNALS
# =============================================================================

@receiver(post_save, sender='fees.FeeInvoiceItem')
def fee_invoice_item_post_save(sender, instance, created, **kwargs):
    """
    Post-save processing for invoice items:
    - Recalculate invoice totals
    """
    # Skip if in raw mode
    if kwargs.get('raw', False):
        return
    
    try:
        # Recalculate invoice totals
        invoice = instance.invoice
        
        # Sum all items
        items = invoice.items.all()
        invoice.subtotal_amount = sum(item.amount for item in items)
        invoice.tax_amount = sum(item.tax_amount for item in items)
        invoice.total_amount = sum(item.final_amount for item in items)
        invoice.balance = invoice.total_amount - invoice.paid_amount
        
        # Save without triggering signals again
        invoice.save(update_fields=[
            'subtotal_amount', 'tax_amount', 'total_amount', 'balance'
        ])
        
        logger.debug(f"Recalculated totals for invoice {invoice.invoice_number}")
    
    except Exception as e:
        logger.error(f"Error recalculating invoice totals: {e}", exc_info=True)


# =============================================================================
# SCHOLARSHIP APPLICATION SIGNALS
# =============================================================================

@receiver(pre_save, sender='fees.StudentScholarshipApplication')
def scholarship_application_pre_save(sender, instance, **kwargs):
    """
    Pre-save processing for scholarship applications:
    - Auto-generate application number (using centralized function from utils.py)
    """
    if not instance.application_number:
        instance.application_number = generate_scholarship_application_number()
        logger.info(f"Generated scholarship application number: {instance.application_number}")


# =============================================================================
# AUDIT LOGGING
# =============================================================================

@receiver(post_save, sender='fees.FeeInvoice')
def log_invoice_status_change(sender, instance, created, **kwargs):
    """Log important invoice status changes"""
    # Skip if in raw mode
    if kwargs.get('raw', False):
        return
    
    if not created and hasattr(instance, '_previous_status'):
        if instance._previous_status != instance.status:
            logger.info(
                f"AUDIT: Invoice status changed - {instance.invoice_number} - "
                f"From: {instance._previous_status} To: {instance.status}"
            )


@receiver(pre_save, sender='fees.FeeInvoice')
def store_previous_invoice_status(sender, instance, **kwargs):
    """Store previous status for comparison"""
    if instance.pk:
        try:
            from fees.models import FeeInvoice
            previous = FeeInvoice.objects.get(pk=instance.pk)
            instance._previous_status = previous.status
        except:
            instance._previous_status = None


# =============================================================================
# DATA INTEGRITY SIGNALS
# =============================================================================

@receiver(pre_save, sender='fees.Payment')
def validate_payment_amount(sender, instance, **kwargs):
    """Validate payment amount is not negative"""
    if instance.amount < 0:
        from django.core.exceptions import ValidationError
        raise ValidationError("Payment amount cannot be negative")


@receiver(pre_save, sender='fees.Refund')
def validate_refund_amount(sender, instance, **kwargs):
    """Validate refund amount"""
    if instance.refund_amount < 0:
        from django.core.exceptions import ValidationError
        raise ValidationError("Refund amount cannot be negative")
    
    # Validate refund doesn't exceed paid amount
    if instance.invoice:
        if instance.refund_amount > instance.invoice.paid_amount:
            from django.core.exceptions import ValidationError
            raise ValidationError(
                f"Refund amount ({instance.refund_amount}) cannot exceed "
                f"paid amount ({instance.invoice.paid_amount})"
            )


# =============================================================================
# AUTO-INVOICE GENERATION SIGNALS
# =============================================================================
        
@receiver(post_save, sender=StudentClassEnrollment)
def auto_generate_class_enrollment_invoice(sender, instance, created, **kwargs):
    """
    Auto-generate invoice for class enrollment.
    
    Note: ClassEnrollmentInvoiceGenerator already calls generate_invoice_number()
    internally, so we don't need to generate it here. The signal just triggers
    the generation based on enrollment state.
    
    Uses the exact field name 'academic_invoice' from StudentClassEnrollment model.
    """
    if kwargs.get('raw', False):
        return
    
    # Only generate if auto_create_invoice is enabled
    if not instance.auto_create_invoice:
        logger.debug(f"Skipping auto-invoice generation for enrollment {instance.id} - auto_create_invoice is False")
        return
    
    # Only for active ongoing enrollments without existing invoice
    if (instance.is_active and 
        instance.completion_status == 'ONGOING' and 
        not instance.academic_invoice):  # ✅ CORRECT FIELD NAME
        
        try:
            # Generator handles all invoice creation logic including number generation
            invoice = ClassEnrollmentInvoiceGenerator.generate(instance)
            instance.academic_invoice = invoice
            instance.save(update_fields=['academic_invoice'])
            logger.info(
                f"Auto-generated class invoice {invoice.invoice_number} "
                f"for {instance.student.get_full_name()} in {instance.class_instance}"
            )
        except Exception as e:
            logger.error(
                f"Error auto-generating class invoice for enrollment {instance.id}: {e}",
                exc_info=True
            )


@receiver(post_save, sender=BoardingEnrollment)
def auto_generate_boarding_invoice(sender, instance, created, **kwargs):
    """
    Auto-generate invoice for boarding enrollment.
    
    Note: BoardingEnrollmentInvoiceGenerator already calls generate_invoice_number()
    internally, so we don't need to generate it here. The signal just triggers
    the generation based on enrollment state.
    """
    if kwargs.get('raw', False):
        return
    
    # Only for active/approved enrollments with consent and no existing invoice
    if (instance.status in ['ACTIVE', 'APPROVED'] and 
        instance.guardian_consent and 
        not instance.boarding_invoice):
        
        try:
            # Generator handles all invoice creation logic including number generation
            invoice = BoardingEnrollmentInvoiceGenerator.generate(
                instance,
                include_meals=True,  # Could be from settings
                include_laundry=False
            )
            instance.boarding_invoice = invoice
            instance.save(update_fields=['boarding_invoice'])
            logger.info(
                f"Auto-generated boarding invoice {invoice.invoice_number} "
                f"for {instance.student.get_full_name()}"
            )
        except Exception as e:
            logger.error(
                f"Error auto-generating boarding invoice for enrollment {instance.id}: {e}",
                exc_info=True
            )