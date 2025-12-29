# fees/services.py

"""
Core Invoice Operations

Handles basic CRUD, payments, refunds, status updates for invoices.
This is the foundation for all invoice-related operations across the system.

For invoice generation (enrollment-specific), see fees/invoice_generators.py
"""

from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from datetime import timedelta
from django.db.models import Sum
import logging

from fees.models import (
    FeeInvoice, FeeInvoiceItem, Payment, Refund, 
    PaymentMethod, FeesCategory, AccountTransaction
)
from students.models import Student
from academics.models import AcademicSession
from core.models import FinancialSettings
from finance.models import JournalEntry, JournalTransaction, Journal

logger = logging.getLogger(__name__)


# =============================================================================
# INVOICE SERVICE - CORE INVOICE OPERATIONS
# =============================================================================

class InvoiceService:
    """
    Core invoice operations shared across all modules.
    Handles CRUD, status management, and invoice lifecycle.
    """
    
    @staticmethod
    @transaction.atomic
    def create_invoice(invoice_data):
        """
        Generic invoice creation with validation.
        
        Args:
            invoice_data (dict): Invoice information
                Required:
                    - student: Student instance or ID
                    - academic_session: AcademicSession instance or ID
                    - issue_date: Date
                    - due_date: Date
                Optional:
                    - invoice_type: 'ACADEMIC', 'BOARDING', 'UNIFORM', etc.
                    - notes: str
                    - discount_amount: Decimal
                    - tax_amount: Decimal
                    - items: List of item dicts (see add_invoice_item)
                    
        Returns:
            FeeInvoice instance
            
        Example:
            invoice = InvoiceService.create_invoice({
                'student': student,
                'academic_session': session,
                'issue_date': date.today(),
                'due_date': date.today() + timedelta(days=30),
                'invoice_type': 'ACADEMIC',
                'notes': 'Term 1 fees',
                'items': [
                    {
                        'fee_category': tuition_category,
                        'amount': 500000,
                        'quantity': 1,
                        'description': 'Tuition Fee'
                    }
                ]
            })
        """
        # Extract items if provided
        items_data = invoice_data.pop('items', [])
        
        # Resolve foreign keys if IDs provided
        if isinstance(invoice_data.get('student'), int):
            invoice_data['student'] = Student.objects.get(pk=invoice_data['student'])
        
        if isinstance(invoice_data.get('academic_session'), int):
            invoice_data['academic_session'] = AcademicSession.objects.get(
                pk=invoice_data['academic_session']
            )
        
        # Get settings for defaults
        settings = FinancialSettings.get_instance()
        
        # Set default accounts if not provided
        if not invoice_data.get('revenue_account'):
            invoice_type = invoice_data.get('invoice_type', 'ACADEMIC')
            invoice_data['revenue_account'] = settings.get_revenue_account(invoice_type)
        
        if not invoice_data.get('receivable_account'):
            invoice_data['receivable_account'] = settings.default_receivables_account
        
        # Create invoice
        invoice = FeeInvoice.objects.create(**invoice_data)
        
        # Add items if provided
        for item_data in items_data:
            InvoiceService.add_invoice_item(invoice, item_data)
        
        logger.info(f"Created invoice {invoice.invoice_number} for {invoice.student.get_full_name()}")
        
        return invoice
    
    @staticmethod
    @transaction.atomic
    def add_invoice_item(invoice, item_data):
        """
        Add item to existing invoice.
        
        Args:
            invoice: FeeInvoice instance
            item_data (dict): Item information
                Required:
                    - fee_category: FeesCategory instance or ID
                    - amount: Decimal
                Optional:
                    - description: str
                    - quantity: int (default: 1)
                    - tax_percentage: Decimal (default: from category)
                    - discount_percentage: Decimal (default: 0)
                    - is_optional: bool (default: False)
                    - display_group: DisplayGroup instance
                    
        Returns:
            FeeInvoiceItem instance
            
        Example:
            item = InvoiceService.add_invoice_item(invoice, {
                'fee_category': tuition_category,
                'amount': 500000,
                'quantity': 1,
                'description': 'Tuition Fee - Term 1',
                'tax_percentage': 0
            })
        """
        # Resolve foreign keys if IDs provided
        if isinstance(item_data.get('fee_category'), int):
            item_data['fee_category'] = FeesCategory.objects.get(pk=item_data['fee_category'])
        
        # Set defaults
        fee_category = item_data.get('fee_category')
        
        if not item_data.get('description'):
            item_data['description'] = fee_category.name
        
        if 'tax_percentage' not in item_data:
            item_data['tax_percentage'] = (
                fee_category.default_tax_rate 
                if fee_category.is_taxable 
                else Decimal('0.00')
            )
        
        if 'quantity' not in item_data:
            item_data['quantity'] = 1
        
        if 'discount_percentage' not in item_data:
            item_data['discount_percentage'] = Decimal('0.00')
        
        if 'is_optional' not in item_data:
            item_data['is_optional'] = not fee_category.is_mandatory
        
        # Create item
        item = FeeInvoiceItem.objects.create(
            invoice=invoice,
            **item_data
        )
        
        logger.debug(f"Added item to invoice {invoice.invoice_number}: {item.description}")
        
        return item
    
    @staticmethod
    @transaction.atomic
    def update_invoice(invoice, update_data):
        """
        Update invoice fields.
        
        Args:
            invoice: FeeInvoice instance
            update_data (dict): Fields to update
            
        Returns:
            Updated FeeInvoice instance
            
        Raises:
            ValidationError: If invoice is paid/cancelled
        """
        # Prevent updates to paid/cancelled invoices
        if invoice.status in ['PAID', 'CANCELLED']:
            raise ValidationError(
                f"Cannot update {invoice.get_status_display()} invoice"
            )
        
        # Update fields
        for field, value in update_data.items():
            if hasattr(invoice, field):
                setattr(invoice, field, value)
        
        invoice.save()
        
        logger.info(f"Updated invoice {invoice.invoice_number}")
        
        return invoice
    
    @staticmethod
    @transaction.atomic
    def cancel_invoice(invoice, reason, cancelled_by=None):
        """
        Cancel an invoice.
        
        Args:
            invoice: FeeInvoice instance
            reason (str): Cancellation reason
            cancelled_by: User who cancelled (optional)
            
        Returns:
            Updated FeeInvoice instance
            
        Raises:
            ValidationError: If invoice has payments or is already cancelled
        """
        # Validate can cancel
        if invoice.status == 'CANCELLED':
            raise ValidationError("Invoice is already cancelled")
        
        if invoice.status == 'PAID':
            raise ValidationError("Cannot cancel paid invoice. Process refund instead.")
        
        if invoice.paid_amount > 0:
            raise ValidationError(
                f"Invoice has payments totaling {invoice.paid_amount}. "
                "Process refunds before cancelling."
            )
        
        # Cancel invoice
        invoice.status = 'CANCELLED'
        invoice.notes = f"{invoice.notes}\n\nCANCELLED: {reason}" if invoice.notes else f"CANCELLED: {reason}"
        invoice.save()
        
        # Reverse student account transaction if exists
        AccountTransaction.objects.filter(
            student=invoice.student,
            invoice=invoice,
            transaction_type='DEBIT'
        ).update(
            transaction_type='CREDIT',
            description=f"Cancelled: {invoice.invoice_number}"
        )
        
        logger.info(
            f"Cancelled invoice {invoice.invoice_number}: {reason} "
            f"(by {cancelled_by or 'System'})"
        )
        
        return invoice
    
    @staticmethod
    @transaction.atomic
    def void_invoice(invoice, reason, voided_by=None):
        """
        Void an invoice (stronger than cancel - used for errors).
        
        Args:
            invoice: FeeInvoice instance
            reason (str): Void reason
            voided_by: User who voided
            
        Returns:
            Updated FeeInvoice instance
        """
        if invoice.paid_amount > 0:
            raise ValidationError(
                "Cannot void invoice with payments. Cancel instead."
            )
        
        invoice.status = 'VOID'
        invoice.notes = f"{invoice.notes}\n\nVOIDED: {reason}" if invoice.notes else f"VOIDED: {reason}"
        invoice.save()
        
        logger.warning(
            f"Voided invoice {invoice.invoice_number}: {reason} "
            f"(by {voided_by or 'System'})"
        )
        
        return invoice
    
    @staticmethod
    @transaction.atomic
    def process_payment(invoice, payment_data):
        """
        Process payment for invoice.
        
        Args:
            invoice: FeeInvoice instance
            payment_data (dict): Payment information
                Required:
                    - amount: Decimal
                    - payment_method: PaymentMethod instance or code
                    - payment_date: Date
                Optional:
                    - reference_number: str
                    - notes: str
                    - payer_name: str
                    - receipt_number: str (auto-generated if not provided)
                    
        Returns:
            Payment instance
            
        Example:
            payment = InvoiceService.process_payment(invoice, {
                'amount': 500000,
                'payment_method': 'BANK',
                'payment_date': date.today(),
                'reference_number': 'TXN123456',
                'notes': 'Bank transfer'
            })
        """
        # Validate invoice can receive payment
        if invoice.status == 'CANCELLED':
            raise ValidationError("Cannot process payment for cancelled invoice")
        
        if invoice.status == 'VOID':
            raise ValidationError("Cannot process payment for voided invoice")
        
        # Validate amount
        amount = Decimal(str(payment_data['amount']))
        if amount <= 0:
            raise ValidationError("Payment amount must be positive")
        
        remaining = invoice.total_amount - invoice.paid_amount
        if amount > remaining:
            raise ValidationError(
                f"Payment amount ({amount}) exceeds remaining balance ({remaining})"
            )
        
        # Resolve payment method
        payment_method = payment_data.get('payment_method')
        if isinstance(payment_method, str):
            payment_method = PaymentMethod.objects.get(code=payment_method)
        
        # Create payment
        payment = Payment.objects.create(
            invoice=invoice,
            student=invoice.student,
            amount=amount,
            payment_method=payment_method,
            payment_date=payment_data['payment_date'],
            reference_number=payment_data.get('reference_number', ''),
            notes=payment_data.get('notes', ''),
            payer_name=payment_data.get('payer_name', invoice.student.get_full_name()),
            status='CONFIRMED'
        )
        
        logger.info(
            f"Processed payment {payment.payment_number} for invoice "
            f"{invoice.invoice_number}: {amount}"
        )
        
        return payment
    
    @staticmethod
    @transaction.atomic
    def process_refund(invoice, refund_data):
        """
        Process refund for invoice.
        
        Args:
            invoice: FeeInvoice instance
            refund_data (dict): Refund information
                Required:
                    - amount: Decimal
                    - reason: str
                    - refund_date: Date
                Optional:
                    - refund_method: PaymentMethod instance or code
                    - reference_number: str
                    - notes: str
                    - approved_by: User instance
                    
        Returns:
            Refund instance
            
        Example:
            refund = InvoiceService.process_refund(invoice, {
                'amount': 100000,
                'reason': 'Student withdrew',
                'refund_date': date.today(),
                'refund_method': 'BANK',
                'notes': 'Partial refund for Term 1'
            })
        """
        # Validate can refund
        if invoice.status == 'CANCELLED':
            raise ValidationError("Cannot process refund for cancelled invoice")
        
        # Validate amount
        amount = Decimal(str(refund_data['amount']))
        if amount <= 0:
            raise ValidationError("Refund amount must be positive")
        
        if amount > invoice.paid_amount:
            raise ValidationError(
                f"Refund amount ({amount}) exceeds paid amount ({invoice.paid_amount})"
            )
        
        # Resolve refund method
        refund_method = refund_data.get('refund_method')
        if isinstance(refund_method, str):
            refund_method = PaymentMethod.objects.get(code=refund_method)
        elif not refund_method:
            # Default to original payment method
            last_payment = invoice.payments.filter(status='CONFIRMED').last()
            refund_method = last_payment.payment_method if last_payment else None
        
        # Create refund
        refund = Refund.objects.create(
            invoice=invoice,
            student=invoice.student,
            amount=amount,
            reason=refund_data['reason'],
            refund_date=refund_data['refund_date'],
            refund_method=refund_method,
            reference_number=refund_data.get('reference_number', ''),
            notes=refund_data.get('notes', ''),
            status='APPROVED'
        )
        
        # Set approved_by if provided
        if refund_data.get('approved_by'):
            refund.approved_by = refund_data['approved_by']
            refund.approved_at = timezone.now()
            refund.save()
        
        logger.info(
            f"Processed refund {refund.refund_number} for invoice "
            f"{invoice.invoice_number}: {amount}"
        )
        
        return refund
    
    @staticmethod
    def get_invoice_status(invoice):
        """
        Get detailed invoice status information.
        
        Args:
            invoice: FeeInvoice instance
            
        Returns:
            dict: Status information
        """
        return {
            'status': invoice.status,
            'status_display': invoice.get_status_display(),
            'is_overdue': invoice.is_overdue,
            'days_overdue': invoice.days_overdue,
            'total_amount': invoice.total_amount,
            'paid_amount': invoice.paid_amount,
            'balance': invoice.balance,
            'payment_progress_percentage': invoice.payment_progress_percentage,
            'can_be_paid': invoice.status not in ['PAID', 'CANCELLED', 'VOID'],
            'can_be_cancelled': invoice.status in ['PENDING', 'PARTIALLY_PAID'] and invoice.paid_amount == 0,
        }
    
    @staticmethod
    def mark_invoice_as_overdue(invoice):
        """
        Mark invoice as overdue if past due date.
        
        Args:
            invoice: FeeInvoice instance
            
        Returns:
            bool: True if marked as overdue
        """
        if invoice.is_overdue and invoice.status in ['PENDING', 'PARTIALLY_PAID']:
            invoice.status = 'OVERDUE'
            invoice.save(update_fields=['status'])
            logger.info(f"Marked invoice {invoice.invoice_number} as overdue")
            return True
        return False


# =============================================================================
# INVOICE CALCULATOR - CALCULATION UTILITIES
# =============================================================================

class InvoiceCalculator:
    """
    Invoice calculation utilities.
    Pure calculation logic for invoices.
    """
    
    @staticmethod
    def calculate_totals(items):
        """
        Calculate invoice totals from items.
        
        Args:
            items: QuerySet or list of FeeInvoiceItem instances
            
        Returns:
            dict: Calculated totals
            {
                'subtotal': Decimal,
                'total_tax': Decimal,
                'total_discount': Decimal,
                'total_amount': Decimal
            }
            
        Example:
            totals = InvoiceCalculator.calculate_totals(invoice.items.all())
            # {'subtotal': 500000, 'total_tax': 0, 'total_discount': 0, 'total_amount': 500000}
        """
        subtotal = Decimal('0.00')
        total_tax = Decimal('0.00')
        total_discount = Decimal('0.00')
        
        for item in items:
            # Calculate line item totals
            line_totals = InvoiceCalculator.calculate_line_item_totals(item)
            
            subtotal += line_totals['subtotal']
            total_tax += line_totals['tax_amount']
            total_discount += line_totals['discount_amount']
        
        total_amount = subtotal + total_tax - total_discount
        
        return {
            'subtotal': subtotal,
            'total_tax': total_tax,
            'total_discount': total_discount,
            'total_amount': total_amount
        }
    
    @staticmethod
    def calculate_line_item_totals(item):
        """
        Calculate totals for a single line item.
        
        Args:
            item: FeeInvoiceItem instance or dict
            
        Returns:
            dict: Line item totals
        """
        # Handle both model instances and dicts
        if isinstance(item, dict):
            amount = Decimal(str(item.get('amount', 0)))
            quantity = item.get('quantity', 1)
            tax_percentage = Decimal(str(item.get('tax_percentage', 0)))
            discount_percentage = Decimal(str(item.get('discount_percentage', 0)))
        else:
            amount = item.amount
            quantity = item.quantity
            tax_percentage = item.tax_percentage
            discount_percentage = item.discount_percentage
        
        # Calculate subtotal
        subtotal = amount * quantity
        
        # Calculate discount
        discount_amount = (subtotal * discount_percentage / 100).quantize(Decimal('0.01'))
        
        # Calculate tax (after discount)
        taxable_amount = subtotal - discount_amount
        tax_amount = (taxable_amount * tax_percentage / 100).quantize(Decimal('0.01'))
        
        # Calculate total
        total = subtotal - discount_amount + tax_amount
        
        return {
            'subtotal': subtotal,
            'discount_amount': discount_amount,
            'tax_amount': tax_amount,
            'total_amount': total
        }
    
    @staticmethod
    def apply_discount(invoice, discount_data):
        """
        Apply discount to invoice.
        
        Args:
            invoice: FeeInvoice instance
            discount_data (dict): Discount information
                - discount_type: 'PERCENTAGE' or 'FIXED'
                - discount_value: Decimal (percentage or amount)
                - reason: str (optional)
                
        Returns:
            dict: Updated totals after discount
            
        Example:
            # Apply 10% discount
            result = InvoiceCalculator.apply_discount(invoice, {
                'discount_type': 'PERCENTAGE',
                'discount_value': 10,
                'reason': 'Sibling discount'
            })
            
            # Apply fixed 50000 discount
            result = InvoiceCalculator.apply_discount(invoice, {
                'discount_type': 'FIXED',
                'discount_value': 50000,
                'reason': 'Scholarship'
            })
        """
        discount_type = discount_data.get('discount_type', 'FIXED')
        discount_value = Decimal(str(discount_data['discount_value']))
        
        # Calculate discount amount
        if discount_type == 'PERCENTAGE':
            if not (0 <= discount_value <= 100):
                raise ValidationError("Discount percentage must be between 0 and 100")
            
            discount_amount = (invoice.subtotal * discount_value / 100).quantize(Decimal('0.01'))
        else:  # FIXED
            if discount_value > invoice.subtotal:
                raise ValidationError("Discount amount cannot exceed subtotal")
            
            discount_amount = discount_value
        
        # Update invoice
        invoice.discount_amount = discount_amount
        invoice.discount_percentage = discount_value if discount_type == 'PERCENTAGE' else Decimal('0.00')
        
        # Add reason to notes if provided
        if discount_data.get('reason'):
            discount_note = f"\nDiscount applied: {discount_data['reason']}"
            invoice.notes = f"{invoice.notes}{discount_note}" if invoice.notes else discount_note
        
        invoice.save()
        
        logger.info(
            f"Applied discount to invoice {invoice.invoice_number}: "
            f"{discount_value}{'%' if discount_type == 'PERCENTAGE' else ''} = {discount_amount}"
        )
        
        return {
            'discount_amount': discount_amount,
            'new_total': invoice.total_amount,
            'new_balance': invoice.balance
        }
    
    @staticmethod
    def apply_late_fee(invoice):
        """
        Calculate and apply late fee to overdue invoice.
        
        Args:
            invoice: FeeInvoice instance
            
        Returns:
            Decimal: Late fee amount applied
        """
        settings = FinancialSettings.get_instance()
        
        if not settings.late_fee_enabled:
            return Decimal('0.00')
        
        if not invoice.is_overdue:
            return Decimal('0.00')
        
        # Check grace period
        days_overdue = invoice.days_overdue
        if days_overdue <= settings.grace_period_days:
            return Decimal('0.00')
        
        # Calculate late fee
        late_fee = (invoice.balance * settings.late_fee_percentage / 100).quantize(Decimal('0.01'))
        
        # Add as invoice item or to separate field
        # (Implementation depends on your preference)
        
        logger.info(
            f"Calculated late fee for invoice {invoice.invoice_number}: "
            f"{late_fee} ({days_overdue} days overdue)"
        )
        
        return late_fee
    
    @staticmethod
    def calculate_payment_breakdown(invoice):
        """
        Get detailed breakdown of invoice payments.
        
        Args:
            invoice: FeeInvoice instance
            
        Returns:
            dict: Payment breakdown
        """
        payments = invoice.payments.filter(status='CONFIRMED')
        refunds = invoice.refunds.filter(status='APPROVED')
        
        return {
            'total_amount': invoice.total_amount,
            'total_paid': payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00'),
            'total_refunded': refunds.aggregate(total=Sum('amount'))['total'] or Decimal('0.00'),
            'net_paid': invoice.paid_amount,
            'balance': invoice.balance,
            'payment_count': payments.count(),
            'refund_count': refunds.count(),
            'last_payment_date': payments.order_by('-payment_date').first().payment_date if payments.exists() else None,
        }
    
    @staticmethod
    def project_payment_schedule(invoice, num_installments):
        """
        Project payment schedule for invoice.
        
        Args:
            invoice: FeeInvoice instance
            num_installments (int): Number of installments
            
        Returns:
            list: Payment schedule
            [
                {'installment': 1, 'amount': Decimal, 'due_date': date},
                ...
            ]
        """
        if num_installments <= 0:
            raise ValidationError("Number of installments must be positive")
        
        balance = invoice.balance
        installment_amount = (balance / num_installments).quantize(Decimal('0.01'))
        
        # Adjust last installment for rounding
        last_installment = balance - (installment_amount * (num_installments - 1))
        
        schedule = []
        current_date = invoice.due_date
        
        for i in range(1, num_installments + 1):
            amount = last_installment if i == num_installments else installment_amount
            
            schedule.append({
                'installment': i,
                'amount': amount,
                'due_date': current_date
            })
            
            # Next installment 30 days later
            current_date = current_date + timedelta(days=30)
        
        return schedule


# =============================================================================
# BULK OPERATIONS
# =============================================================================

class InvoiceBulkOperations:
    """Bulk operations for invoices"""
    
    @staticmethod
    @transaction.atomic
    def bulk_cancel_invoices(invoices, reason, cancelled_by=None):
        """
        Cancel multiple invoices at once.
        
        Args:
            invoices: QuerySet or list of FeeInvoice instances
            reason (str): Cancellation reason
            cancelled_by: User who cancelled
            
        Returns:
            dict: Results
        """
        results = {
            'cancelled': [],
            'failed': [],
            'total': len(invoices)
        }
        
        for invoice in invoices:
            try:
                InvoiceService.cancel_invoice(invoice, reason, cancelled_by)
                results['cancelled'].append(invoice)
            except Exception as e:
                logger.error(f"Error cancelling invoice {invoice.invoice_number}: {e}")
                results['failed'].append({
                    'invoice': invoice,
                    'error': str(e)
                })
        
        return results
    
    @staticmethod
    @transaction.atomic
    def bulk_apply_discount(invoices, discount_data):
        """
        Apply discount to multiple invoices.
        
        Args:
            invoices: QuerySet or list of FeeInvoice instances
            discount_data (dict): Discount information
            
        Returns:
            dict: Results
        """
        results = {
            'updated': [],
            'failed': [],
            'total': len(invoices),
            'total_discount': Decimal('0.00')
        }
        
        for invoice in invoices:
            try:
                result = InvoiceCalculator.apply_discount(invoice, discount_data)
                results['updated'].append(invoice)
                results['total_discount'] += result['discount_amount']
            except Exception as e:
                logger.error(f"Error applying discount to invoice {invoice.invoice_number}: {e}")
                results['failed'].append({
                    'invoice': invoice,
                    'error': str(e)
                })
        
        return results
    
    @staticmethod
    def mark_overdue_invoices():
        """
        Mark all overdue invoices.
        Called by scheduled task.
        
        Returns:
            int: Number of invoices marked as overdue
        """
        from django.db.models import Q
        
        today = timezone.now().date()
        
        overdue_invoices = FeeInvoice.objects.filter(
            Q(status='PENDING') | Q(status='PARTIALLY_PAID'),
            due_date__lt=today
        )
        
        count = 0
        for invoice in overdue_invoices:
            if InvoiceService.mark_invoice_as_overdue(invoice):
                count += 1
        
        logger.info(f"Marked {count} invoices as overdue")
        
        return count