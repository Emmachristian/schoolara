# fees/utils.py

"""
Fee Management Utility Functions

Contains:
- Reference number generation (invoices, payments, receipts, refunds, applications)
- Invoice display organization
- Validation utilities
- Calculation helpers
- Reporting helpers
"""

from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from decimal import Decimal
from itertools import groupby
from operator import attrgetter
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# REFERENCE NUMBER GENERATION
# =============================================================================

def generate_invoice_number():
    """
    Generate unique invoice number using company settings.
    Format depends on settings:
    - With prefix and year: INV-2024-0001
    - With prefix only: INV-0001
    - No prefix: 0001

    Returns:
        str: Unique invoice number
    """
    from fees.models import FeeInvoice
    from core.models import FinancialSettings

    settings = FinancialSettings.get_instance()
    prefix = settings.invoice_prefix.strip() if settings.invoice_prefix else ""
    include_year = settings.include_year_in_invoice_number

    current_year = timezone.now().year

    if prefix and include_year:
        search_prefix = f"{prefix}-{current_year}-"
    elif prefix:
        search_prefix = f"{prefix}-"
    else:
        search_prefix = ""

    with transaction.atomic():
        if search_prefix:
            queryset = FeeInvoice.objects.filter(
                invoice_number__startswith=search_prefix
            ).select_for_update()
        else:
            queryset = FeeInvoice.objects.select_for_update()

        result = queryset.aggregate(max_number=Max('invoice_number'))

        if result['max_number']:
            try:
                if search_prefix:
                    last_number = int(result['max_number'].split('-')[-1])
                else:
                    last_number = int(result['max_number'])
                new_number = last_number + 1
            except (ValueError, IndexError):
                numbers = []
                for invoice_num in queryset.values_list('invoice_number', flat=True):
                    try:
                        if search_prefix:
                            num = int(invoice_num.split('-')[-1])
                        else:
                            num = int(''.join(filter(str.isdigit, invoice_num)))
                        numbers.append(num)
                    except (ValueError, IndexError):
                        continue
                new_number = max(numbers) + 1 if numbers else 1
        else:
            new_number = 1

        if new_number <= 9999:
            min_digits = 4
        elif new_number <= 99999:
            min_digits = 5
        elif new_number <= 999999:
            min_digits = 6
        elif new_number <= 9999999:
            min_digits = 7
        else:
            min_digits = len(str(new_number))

        formatted_number = f"{new_number:0{min_digits}d}"

        if prefix and include_year:
            return f"{prefix}-{current_year}-{formatted_number}"
        elif prefix:
            return f"{prefix}-{formatted_number}"
        else:
            return formatted_number


def generate_payment_number():
    """
    Generate unique payment number using company settings.
    Format: PMT-2024-0001 or PMT-0001 or 0001

    Returns:
        str: Unique payment number
    """
    from fees.models import Payment
    from core.models import FinancialSettings

    settings = FinancialSettings.get_instance()
    prefix = settings.payment_prefix.strip() if settings.payment_prefix else ""
    include_year = settings.include_year_in_payment_number

    current_year = timezone.now().year

    if prefix and include_year:
        search_prefix = f"{prefix}-{current_year}-"
    elif prefix:
        search_prefix = f"{prefix}-"
    else:
        search_prefix = ""

    with transaction.atomic():
        if search_prefix:
            queryset = Payment.objects.filter(
                payment_number__startswith=search_prefix
            ).select_for_update()
        else:
            queryset = Payment.objects.select_for_update()

        result = queryset.aggregate(max_number=Max('payment_number'))

        if result['max_number']:
            try:
                if search_prefix:
                    last_number = int(result['max_number'].split('-')[-1])
                else:
                    last_number = int(result['max_number'])
                new_number = last_number + 1
            except (ValueError, IndexError):
                numbers = []
                for payment_num in queryset.values_list('payment_number', flat=True):
                    try:
                        if search_prefix:
                            num = int(payment_num.split('-')[-1])
                        else:
                            num = int(''.join(filter(str.isdigit, payment_num)))
                        numbers.append(num)
                    except (ValueError, IndexError):
                        continue
                new_number = max(numbers) + 1 if numbers else 1
        else:
            new_number = 1

        if new_number <= 9999:
            formatted_number = f"{new_number:04d}"
        else:
            formatted_number = str(new_number)

        if prefix and include_year:
            return f"{prefix}-{current_year}-{formatted_number}"
        elif prefix:
            return f"{prefix}-{formatted_number}"
        else:
            return formatted_number


def generate_receipt_number():
    """
    Generate unique receipt number using company settings.
    Format: RCPT-000001 or 000001

    Returns:
        str: Unique receipt number
    """
    from fees.models import Payment
    from core.models import FinancialSettings

    settings = FinancialSettings.get_instance()
    prefix = settings.receipt_prefix.strip() if settings.receipt_prefix else ""

    if prefix:
        search_prefix = f"{prefix}-"
    else:
        search_prefix = ""

    with transaction.atomic():
        if search_prefix:
            queryset = Payment.objects.filter(
                receipt_number__startswith=search_prefix
            ).select_for_update()
        else:
            queryset = Payment.objects.filter(
                receipt_number__isnull=False
            ).exclude(receipt_number='').select_for_update()

        result = queryset.aggregate(max_number=Max('receipt_number'))

        if result['max_number']:
            try:
                if search_prefix:
                    last_number = int(result['max_number'].split('-')[-1])
                else:
                    last_number = int(result['max_number'])
                new_number = last_number + 1
            except (ValueError, IndexError):
                numbers = []
                for receipt_num in queryset.values_list('receipt_number', flat=True):
                    try:
                        if search_prefix and receipt_num.startswith(search_prefix):
                            num = int(receipt_num.split('-')[-1])
                        else:
                            numeric_part = ''.join(filter(str.isdigit, receipt_num))
                            if numeric_part:
                                num = int(numeric_part)
                            else:
                                continue
                        numbers.append(num)
                    except (ValueError, IndexError):
                        continue
                new_number = max(numbers) + 1 if numbers else 1
        else:
            new_number = 1

        if new_number <= 999999:
            formatted_number = f"{new_number:06d}"
        else:
            formatted_number = str(new_number)

        if prefix:
            return f"{prefix}-{formatted_number}"
        else:
            return formatted_number



def generate_scholarship_application_number(scholarship_program=None, year=None):
    """
    Generate unique scholarship application number.
    Format:
    - With type: APP-2024-MERIT-001, APP-2024-NEED-001
    - Without type: APP-2024-001

    Args:
        scholarship_program: ScholarshipProgram instance (to get scholarship_type)
        year: Optional year (defaults to current year)

    Returns:
        str: Unique application number
    """
    from fees.models import StudentScholarshipApplication

    if year is None:
        year = timezone.now().year

    prefix = "APP"

    TYPE_PREFIX_MAP = {
        'ACADEMIC_MERIT':        'MERIT',
        'SPORTS_EXCELLENCE':     'SPORT',
        'ARTS_TALENT':           'ARTS',
        'NEED_BASED':            'NEED',
        'COMMUNITY_SERVICE':     'COMMUNITY',
        'LEADERSHIP':            'LEADER',
        'SPECIAL_CIRCUMSTANCES': 'SPECIAL',
        'ALUMNI_SPONSORED':      'ALUMNI',
        'CORPORATE_SPONSORED':   'CORP',
        'GOVERNMENT_BURSARY':    'GOV',
        'FULL_SCHOLARSHIP':      'FULL',
        'PARTIAL_SCHOLARSHIP':   'PARTIAL',
        'EMERGENCY_AID':         'EMERG',
    }

    type_prefix = None
    if scholarship_program:
        type_prefix = TYPE_PREFIX_MAP.get(scholarship_program.scholarship_type)

    if type_prefix:
        search_prefix = f"{prefix}-{year}-{type_prefix}-"
    else:
        search_prefix = f"{prefix}-{year}-"

    with transaction.atomic():
        queryset = StudentScholarshipApplication.objects.filter(
            application_number__startswith=search_prefix
        ).select_for_update()

        result = queryset.aggregate(max_number=Max('application_number'))

        if result['max_number']:
            try:
                last_number = int(result['max_number'].split('-')[-1])
                new_number = last_number + 1
            except (ValueError, IndexError):
                numbers = []
                for app_num in queryset.values_list('application_number', flat=True):
                    try:
                        num = int(app_num.split('-')[-1])
                        numbers.append(num)
                    except (ValueError, IndexError):
                        continue
                new_number = max(numbers) + 1 if numbers else 1
        else:
            new_number = 1

        formatted_number = f"{new_number:03d}"

        if type_prefix:
            return f"{prefix}-{year}-{type_prefix}-{formatted_number}"
        else:
            return f"{prefix}-{year}-{formatted_number}"


# =============================================================================
# INVOICE DISPLAY ORGANIZATION
# =============================================================================

def get_invoice_items_organized(invoice):
    """
    Organize invoice items based on display group settings.

    Groups or displays items individually based on the
    display_group.show_as_group flag.

    Args:
        invoice: FeeInvoice instance

    Returns:
        list: List of dicts with organized items:
        [
            {
                'type': 'grouped' or 'individual',
                'group': DisplayGroup instance or None,
                'items': [FeeInvoiceItem, ...],
                'show_subtotal': bool,
                'subtotal': Decimal
            },
            ...
        ]
    """
    items = invoice.items.select_related(
        'fee_category__display_group'
    ).order_by(
        'fee_category__display_group__display_order',
        'fee_category__display_order',
    )

    organized = []

    for group, items_in_group in groupby(items, key=lambda x: x.fee_category.display_group):
        items_list = list(items_in_group)

        if group and group.show_as_group:
            subtotal = sum(item.final_amount for item in items_list)
            organized.append({
                'type':          'grouped',
                'group':         group,
                'items':         items_list,
                'show_subtotal': group.show_group_subtotal,
                'subtotal':      subtotal,
            })
        else:
            for item in items_list:
                organized.append({
                    'type':          'individual',
                    'group':         group,
                    'items':         [item],
                    'show_subtotal': False,
                    'subtotal':      item.final_amount,
                })

    return organized


def calculate_invoice_totals_by_group(invoice):
    """
    Calculate invoice totals grouped by display group.

    Args:
        invoice: FeeInvoice instance

    Returns:
        dict: {
            'by_group': [...],
            'grand_total': Decimal,
            'total_tax': Decimal,
            'total_discount': Decimal
        }
    """
    items = invoice.items.select_related('fee_category__display_group')

    groups_data = []
    for group, items_in_group in groupby(
        items.order_by('fee_category__display_group__display_order'),
        key=lambda x: x.fee_category.display_group,
    ):
        items_list = list(items_in_group)

        group_subtotal = sum(item.amount       for item in items_list)
        group_tax      = sum(item.tax_amount   for item in items_list)
        group_total    = sum(item.final_amount for item in items_list)

        groups_data.append({
            'group_name': group.name if group else 'Other',
            'group':      group,
            'subtotal':   group_subtotal,
            'tax':        group_tax,
            'total':      group_total,
            'item_count': len(items_list),
        })

    return {
        'by_group':       groups_data,
        'grand_total':    invoice.total_amount,
        'total_tax':      invoice.tax_amount,
        'total_discount': invoice.discount_amount,
    }


def format_invoice_for_display(invoice, include_payments=True):
    """
    Format invoice data for display in templates or PDFs.

    Args:
        invoice: FeeInvoice instance
        include_payments: Whether to include payment history

    Returns:
        dict: Formatted invoice data ready for rendering
    """
    organized_items = get_invoice_items_organized(invoice)

    data = {
        'invoice':          invoice,
        'student':          invoice.student,
        'organized_items':  organized_items,
        'totals': {
            'subtotal': invoice.subtotal_amount,
            'discount': invoice.discount_amount,
            'tax':      invoice.tax_amount,
            'total':    invoice.total_amount,
            'paid':     invoice.paid_amount,
            'balance':  invoice.balance,
        },
        'dates': {
            'issue': invoice.issue_date,
            'due':   invoice.due_date,
        },
        'status':       invoice.get_status_display(),
        'status_color': get_invoice_status_color(invoice.status),
    }

    if include_payments:
        data['payments'] = invoice.payments.all().order_by('-payment_date')

    return data


def get_invoice_status_color(status):
    """
    Get hex color code for invoice status.

    Args:
        status: Invoice status string

    Returns:
        str: Hex color code
    """
    colors = {
        'DRAFT':          '#6C757D',
        'PENDING':        '#FFC107',
        'PARTIALLY_PAID': '#17A2B8',
        'PAID':           '#28A745',
        'OVERDUE':        '#DC3545',
        'CANCELLED':      '#343A40',
        'REFUNDED':       '#6F42C1',
    }
    return colors.get(status, '#6C757D')


# =============================================================================
# VALIDATION UTILITIES
# =============================================================================

def validate_invoice_data(invoice_data):
    """
    Validate invoice data before creation.

    Args:
        invoice_data: Dict with invoice information

    Returns:
        dict: {'valid': bool, 'errors': list, 'warnings': list}
    """
    errors   = []
    warnings = []

    required_fields = ['student', 'academic_session', 'items']
    for field in required_fields:
        if field not in invoice_data or not invoice_data[field]:
            errors.append(f"{field.replace('_', ' ').title()} is required")

    if 'items' in invoice_data and invoice_data['items']:
        for idx, item in enumerate(invoice_data['items']):
            if 'fee_category' not in item:
                errors.append(f"Item {idx + 1}: fee_category is required")
            if 'amount' not in item or item['amount'] <= 0:
                errors.append(f"Item {idx + 1}: amount must be positive")
    else:
        errors.append("At least one invoice item is required")

    if 'issue_date' in invoice_data and 'due_date' in invoice_data:
        if invoice_data['due_date'] < invoice_data['issue_date']:
            errors.append("Due date cannot be before issue date")

    if 'discount_amount' in invoice_data and invoice_data['discount_amount'] < 0:
        errors.append("Discount amount cannot be negative")

    if 'tax_amount' in invoice_data and invoice_data['tax_amount'] < 0:
        errors.append("Tax amount cannot be negative")

    return {
        'valid':    len(errors) == 0,
        'errors':   errors,
        'warnings': warnings,
    }


def validate_payment_data(payment_data):
    """
    Validate payment data before creation.

    Args:
        payment_data: Dict with payment information

    Returns:
        dict: {'valid': bool, 'errors': list, 'warnings': list}
    """
    from core.utils import get_school_today

    errors   = []
    warnings = []

    if 'amount' not in payment_data or payment_data['amount'] <= 0:
        errors.append("Payment amount must be positive")

    if 'payment_method' not in payment_data:
        errors.append("Payment method is required")

    if 'student' not in payment_data:
        errors.append("Student is required")

    if 'invoice' in payment_data:
        invoice = payment_data['invoice']
        amount  = payment_data.get('amount', 0)

        if amount > invoice.balance:
            warnings.append(
                f"Payment amount ({amount}) exceeds invoice balance ({invoice.balance}). "
                f"Excess will be recorded as overpayment."
            )

    if 'payment_date' in payment_data:
        today        = get_school_today()
        payment_date = payment_data['payment_date']
        if payment_date > today:
            errors.append("Payment date cannot be in the future")

    return {
        'valid':    len(errors) == 0,
        'errors':   errors,
        'warnings': warnings,
    }


# =============================================================================
# CALCULATION HELPERS
# =============================================================================

def calculate_line_item_totals(amount, quantity=1, tax_percentage=0, discount_percentage=0):
    """
    Calculate line item totals with tax and discount.

    Args:
        amount: Base amount per unit
        quantity: Quantity
        tax_percentage: Tax percentage (0-100)
        discount_percentage: Discount percentage (0-100)

    Returns:
        dict: {
            'subtotal': Decimal,
            'discount_amount': Decimal,
            'taxable_amount': Decimal,
            'tax_amount': Decimal,
            'final_amount': Decimal
        }
    """
    amount              = Decimal(str(amount))
    quantity            = Decimal(str(quantity))
    tax_percentage      = Decimal(str(tax_percentage))
    discount_percentage = Decimal(str(discount_percentage))

    subtotal         = amount * quantity
    discount_amount  = (subtotal * discount_percentage) / 100
    taxable_amount   = subtotal - discount_amount
    tax_amount       = (taxable_amount * tax_percentage) / 100
    final_amount     = taxable_amount + tax_amount

    return {
        'subtotal':        subtotal,
        'discount_amount': discount_amount,
        'taxable_amount':  taxable_amount,
        'tax_amount':      tax_amount,
        'final_amount':    final_amount,
    }


def apply_discount_to_invoice(invoice, discount_amount=None, discount_percentage=None):
    """
    Apply discount to invoice and recalculate totals.

    Args:
        invoice: FeeInvoice instance
        discount_amount: Fixed discount amount (optional)
        discount_percentage: Percentage discount (optional)

    Returns:
        dict: Updated totals
    """
    subtotal = invoice.subtotal_amount

    if discount_percentage:
        discount = (subtotal * Decimal(str(discount_percentage))) / 100
    elif discount_amount:
        discount = Decimal(str(discount_amount))
    else:
        discount = Decimal('0.00')

    discount = min(discount, subtotal)

    invoice.discount_amount = discount
    invoice.total_amount    = subtotal + invoice.tax_amount - discount
    invoice.balance         = invoice.total_amount - invoice.paid_amount

    return {
        'subtotal': invoice.subtotal_amount,
        'discount': invoice.discount_amount,
        'tax':      invoice.tax_amount,
        'total':    invoice.total_amount,
        'balance':  invoice.balance,
    }


