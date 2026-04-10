# fees/services.py

"""
Core Invoice Operations

Handles CRUD, payments, status updates for invoices.
Refunds are handled directly on the Payment model via Payment.refunded,
Payment.refund_method, Payment.refund_reference, etc.

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
    FeeInvoice, FeeInvoiceItem, Payment,
    FeesCategory, AccountTransaction,
)
from core.models import PaymentMethod, FinancialSettings   
from students.models import Student
from academics.models import AcademicSession
from finance.models import JournalEntry, JournalTransaction, Journal
from core.utils import get_school_today, get_school_current_time

logger = logging.getLogger(__name__)


# =============================================================================
# INVOICE SERVICE
# =============================================================================

class InvoiceService:
    """
    Core invoice operations: create, update, cancel, void, payment, status.
    """

    @staticmethod
    @transaction.atomic
    def create_invoice(invoice_data):
        """
        Generic invoice creation with validation.

        Args:
            invoice_data (dict):
                Required: student, academic_session
                Optional: issue_date, due_date, notes, discount_amount,
                          tax_amount, items (list of item dicts)

        Returns:
            FeeInvoice
        """
        items_data = invoice_data.pop('items', [])

        if 'issue_date' not in invoice_data:
            invoice_data['issue_date'] = get_school_today()

        if 'due_date' not in invoice_data:
            settings = FinancialSettings.get_instance()
            days = settings.default_payment_terms_days if settings else 30
            invoice_data['due_date'] = invoice_data['issue_date'] + timedelta(days=days)

        if isinstance(invoice_data.get('student'), int):
            invoice_data['student'] = Student.objects.get(pk=invoice_data['student'])

        if isinstance(invoice_data.get('academic_session'), int):
            invoice_data['academic_session'] = AcademicSession.objects.get(
                pk=invoice_data['academic_session']
            )

        invoice = FeeInvoice.objects.create(**invoice_data)

        for item_data in items_data:
            InvoiceService.add_invoice_item(invoice, item_data)

        return invoice

    @staticmethod
    @transaction.atomic
    def add_invoice_item(invoice, item_data):
        """
        Add a line item to an existing invoice.

        Args:
            invoice:    FeeInvoice
            item_data:  dict with fee_category, amount, and optional fields

        Returns:
            FeeInvoiceItem
        """
        if isinstance(item_data.get('fee_category'), int):
            item_data['fee_category'] = FeesCategory.objects.get(pk=item_data['fee_category'])

        fee_category = item_data.get('fee_category')

        item_data.setdefault('description', fee_category.name)
        item_data.setdefault(
            'tax_percentage',
            fee_category.default_tax_rate if fee_category.is_taxable else Decimal('0.00'),
        )
        item_data.setdefault('quantity', 1)
        item_data.setdefault('discount_percentage', Decimal('0.00'))
        item_data.setdefault('is_optional', not fee_category.is_mandatory)

        return FeeInvoiceItem.objects.create(invoice=invoice, **item_data)

    @staticmethod
    @transaction.atomic
    def update_invoice(invoice, update_data):
        """
        Update invoice fields.

        Raises:
            ValidationError: if invoice is PAID or CANCELLED
        """
        if invoice.status in ['PAID', 'CANCELLED']:
            raise ValidationError(
                f"Cannot update a {invoice.get_status_display()} invoice."
            )

        for field, value in update_data.items():
            if hasattr(invoice, field):
                setattr(invoice, field, value)

        invoice.save()
        return invoice

    @staticmethod
    @transaction.atomic
    def cancel_invoice(invoice, reason, cancelled_by=None):
        """
        Cancel an invoice that has no payments.

        Raises:
            ValidationError: if already cancelled, paid, or has payments
        """
        if invoice.status == 'CANCELLED':
            raise ValidationError("Invoice is already cancelled.")

        if invoice.status == 'PAID':
            raise ValidationError(
                "Cannot cancel a paid invoice. Process a refund on the Payment instead."
            )

        if invoice.paid_amount > 0:
            raise ValidationError(
                f"Invoice has payments totalling {invoice.paid_amount}. "
                "Mark the Payment as refunded before cancelling."
            )

        invoice.status = 'CANCELLED'
        invoice.notes  = (
            f"{invoice.notes}\n\nCANCELLED: {reason}" if invoice.notes
            else f"CANCELLED: {reason}"
        )
        invoice.save()

        # AccountTransaction has no direct 'student' field — traverse via student_account
        AccountTransaction.objects.filter(
            student_account__student=invoice.student,
            invoice=invoice,
            transaction_type='DEBIT',
        ).update(
            transaction_type='CREDIT',
            description=f"Cancelled: {invoice.invoice_number}",
        )

        return invoice

    @staticmethod
    @transaction.atomic
    def void_invoice(invoice, reason, voided_by=None):
        """
        Void an invoice (used for data-entry errors, stronger than cancel).

        Raises:
            ValidationError: if invoice has payments
        """
        if invoice.paid_amount > 0:
            raise ValidationError(
                "Cannot void an invoice that has payments. Cancel it instead."
            )

        invoice.status = 'VOID'
        invoice.notes  = (
            f"{invoice.notes}\n\nVOIDED: {reason}" if invoice.notes
            else f"VOIDED: {reason}"
        )
        invoice.save()
        return invoice

    @staticmethod
    @transaction.atomic
    def process_payment(invoice, payment_data):
        """
        Record a payment against an invoice.

        Args:
            invoice:       FeeInvoice
            payment_data:  dict
                Required:  amount, payment_method (instance or code), payment_date
                Optional:  reference_number, remarks, paid_by_name, receipt_number

        Returns:
            Payment

        Raises:
            ValidationError: invalid state or amount
        """
        if invoice.status in ['CANCELLED', 'VOID']:
            raise ValidationError(
                f"Cannot process payment for a {invoice.get_status_display()} invoice."
            )

        amount = Decimal(str(payment_data['amount']))
        if amount <= 0:
            raise ValidationError("Payment amount must be positive.")

        remaining = invoice.total_amount - invoice.paid_amount
        if amount > remaining:
            raise ValidationError(
                f"Payment ({amount}) exceeds remaining balance ({remaining})."
            )

        payment_method = payment_data.get('payment_method')
        if isinstance(payment_method, str):
            payment_method = PaymentMethod.objects.get(code=payment_method)

        return Payment.objects.create(
            invoice=invoice,
            student=invoice.student,
            amount=amount,
            payment_method=payment_method,
            payment_date=payment_data['payment_date'],
            reference_number=payment_data.get('reference_number', ''),
            remarks=payment_data.get('remarks', ''),          # correct field name
            paid_by_name=payment_data.get(                    # correct field name
                'paid_by_name',
                invoice.student.get_full_name(),
            ),
            status='COMPLETED',
        )

    @staticmethod
    def get_invoice_status(invoice):
        """Return a dict of key status metrics for an invoice."""
        today        = get_school_today()
        is_overdue   = (
            invoice.due_date < today and
            invoice.status in ['PENDING', 'PARTIALLY_PAID', 'OVERDUE']
        )
        days_overdue = (today - invoice.due_date).days if is_overdue else 0
        days_until_due = (invoice.due_date - today).days if not is_overdue else 0

        payment_progress = (
            round(float(invoice.paid_amount / invoice.total_amount * 100), 1)
            if invoice.total_amount > 0 else 0
        )

        return {
            'status':                    invoice.status,
            'status_display':            invoice.get_status_display(),
            'is_overdue':                is_overdue,
            'days_overdue':              days_overdue,
            'days_until_due':            days_until_due,
            'total_amount':              invoice.total_amount,
            'paid_amount':               invoice.paid_amount,
            'balance':                   invoice.balance,
            'payment_progress_percent':  payment_progress,
            'can_be_paid':               invoice.status not in ['PAID', 'CANCELLED', 'VOID'],
            'can_be_cancelled':          (
                invoice.status in ['PENDING', 'PARTIALLY_PAID']
                and invoice.paid_amount == 0
            ),
        }

    @staticmethod
    def mark_invoice_as_overdue(invoice):
        """Mark invoice OVERDUE if past due date. Returns True if status changed."""
        today      = get_school_today()
        is_overdue = (
            invoice.due_date < today and
            invoice.status in ['PENDING', 'PARTIALLY_PAID']
        )
        if is_overdue:
            invoice.status = 'OVERDUE'
            invoice.save(update_fields=['status'])
            return True
        return False


# =============================================================================
# INVOICE CALCULATOR
# =============================================================================

class InvoiceCalculator:
    """Pure calculation utilities for invoices."""

    @staticmethod
    def calculate_totals(items):
        """
        Aggregate totals from a collection of FeeInvoiceItem instances.

        Returns:
            dict: subtotal, total_tax, total_discount, total_amount
        """
        subtotal       = Decimal('0.00')
        total_tax      = Decimal('0.00')
        total_discount = Decimal('0.00')

        for item in items:
            line = InvoiceCalculator.calculate_line_item_totals(item)
            subtotal       += line['subtotal']
            total_tax      += line['tax_amount']
            total_discount += line['discount_amount']

        return {
            'subtotal':       subtotal,
            'total_tax':      total_tax,
            'total_discount': total_discount,
            'total_amount':   subtotal + total_tax - total_discount,
        }

    @staticmethod
    def calculate_line_item_totals(item):
        """
        Calculate totals for a single line item (model instance or dict).

        Returns:
            dict: subtotal, discount_amount, tax_amount, total_amount
        """
        if isinstance(item, dict):
            amount              = Decimal(str(item.get('amount', 0)))
            quantity            = item.get('quantity', 1)
            tax_percentage      = Decimal(str(item.get('tax_percentage', 0)))
            discount_percentage = Decimal(str(item.get('discount_percentage', 0)))
        else:
            amount              = item.amount
            quantity            = item.quantity
            tax_percentage      = item.tax_percentage
            discount_percentage = item.discount_percentage

        subtotal        = amount * quantity
        discount_amount = (subtotal * discount_percentage / 100).quantize(Decimal('0.01'))
        taxable         = subtotal - discount_amount
        tax_amount      = (taxable * tax_percentage / 100).quantize(Decimal('0.01'))

        return {
            'subtotal':        subtotal,
            'discount_amount': discount_amount,
            'tax_amount':      tax_amount,
            'total_amount':    subtotal - discount_amount + tax_amount,
        }

    @staticmethod
    def apply_discount(invoice, discount_data):
        """
        Apply a discount to an invoice.

        Args:
            invoice:       FeeInvoice
            discount_data: dict
                discount_type:  'PERCENTAGE' or 'FIXED'
                discount_value: Decimal
                reason:         str (optional, appended to notes)

        Returns:
            dict: discount_amount, new_total, new_balance
        """
        discount_type  = discount_data.get('discount_type', 'FIXED')
        discount_value = Decimal(str(discount_data['discount_value']))

        if discount_type == 'PERCENTAGE':
            if not (0 <= discount_value <= 100):
                raise ValidationError("Discount percentage must be between 0 and 100.")
            discount_amount = (
                invoice.subtotal_amount * discount_value / 100
            ).quantize(Decimal('0.01'))
        else:
            if discount_value > invoice.subtotal_amount:
                raise ValidationError("Discount amount cannot exceed the invoice subtotal.")
            discount_amount = discount_value

        invoice.discount_amount = discount_amount
        # FeeInvoice has no discount_percentage field — do not set it

        if discount_data.get('reason'):
            invoice.notes = (
                f"{invoice.notes}\nDiscount: {discount_data['reason']}"
                if invoice.notes else f"Discount: {discount_data['reason']}"
            )

        invoice.save()

        return {
            'discount_amount': discount_amount,
            'new_total':       invoice.total_amount,
            'new_balance':     invoice.balance,
        }

    @staticmethod
    def project_payment_schedule(invoice, num_installments):
        """
        Project an installment schedule for the remaining balance.

        Returns:
            list of dicts: installment, amount, due_date
        """
        if num_installments <= 0:
            raise ValidationError("Number of installments must be positive.")

        balance            = invoice.balance
        installment_amount = (balance / num_installments).quantize(Decimal('0.01'))
        last_installment   = balance - installment_amount * (num_installments - 1)
        schedule           = []
        current_date       = invoice.due_date

        for i in range(1, num_installments + 1):
            amount = last_installment if i == num_installments else installment_amount
            schedule.append({'installment': i, 'amount': amount, 'due_date': current_date})
            current_date = current_date + timedelta(days=30)

        return schedule

    @staticmethod
    def calculate_payment_breakdown(invoice):
        """
        Return a breakdown of payments and refunds for an invoice.

        Refunds are read directly from Payment.refunded — no separate Refund model.
        """
        payments = invoice.payments.filter(
            status='COMPLETED', reversed=False, refunded=False
        )
        refunded = invoice.payments.filter(refunded=True)

        return {
            'total_amount':      invoice.total_amount,
            'total_paid':        payments.aggregate(t=Sum('amount'))['t'] or Decimal('0.00'),
            'total_refunded':    refunded.aggregate(t=Sum('amount'))['t'] or Decimal('0.00'),
            'net_paid':          invoice.paid_amount,
            'balance':           invoice.balance,
            'payment_count':     payments.count(),
            'refund_count':      refunded.count(),
            'last_payment_date': (
                payments.order_by('-payment_date')
                        .values_list('payment_date', flat=True)
                        .first()
            ),
        }


# =============================================================================
# BULK OPERATIONS
# =============================================================================

class InvoiceBulkOperations:
    """Bulk operations across multiple invoices."""

    @staticmethod
    @transaction.atomic
    def bulk_cancel_invoices(invoices, reason, cancelled_by=None):
        """
        Cancel multiple invoices.

        Returns:
            dict: cancelled (list), failed (list), total (int)
        """
        results = {'cancelled': [], 'failed': [], 'total': len(invoices)}

        for invoice in invoices:
            try:
                InvoiceService.cancel_invoice(invoice, reason, cancelled_by)
                results['cancelled'].append(invoice)
            except Exception as e:
                results['failed'].append({'invoice': invoice, 'error': str(e)})
                logger.exception(f"Failed to cancel invoice {invoice.invoice_number}")

        return results

    @staticmethod
    @transaction.atomic
    def bulk_apply_discount(invoices, discount_data):
        """
        Apply the same discount to multiple invoices.

        Returns:
            dict: updated (list), failed (list), total (int), total_discount (Decimal)
        """
        results = {
            'updated':        [],
            'failed':         [],
            'total':          len(invoices),
            'total_discount': Decimal('0.00'),
        }

        for invoice in invoices:
            try:
                result = InvoiceCalculator.apply_discount(invoice, discount_data)
                results['updated'].append(invoice)
                results['total_discount'] += result['discount_amount']
            except Exception as e:
                results['failed'].append({'invoice': invoice, 'error': str(e)})
                logger.exception(f"Failed to apply discount to invoice {invoice.invoice_number}")

        return results

    @staticmethod
    def mark_overdue_invoices():
        """
        Mark all past-due invoices as OVERDUE.
        Intended for use in a scheduled task.

        Returns:
            int: number of invoices updated
        """
        today = get_school_today()

        overdue = FeeInvoice.objects.filter(
            status__in=['PENDING', 'PARTIALLY_PAID'],
            due_date__lt=today,
        )

        count = sum(
            1 for invoice in overdue
            if InvoiceService.mark_invoice_as_overdue(invoice)
        )

        return count