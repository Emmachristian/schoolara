# finance/services.py

"""
Core Finance Operations

Handles CRUD, payments, approvals, journal entries, and budget operations.
This is the foundation for all finance-related operations across the system.

Services:
- ExpenseService: Expense CRUD, approval workflows, status management
- ExpensePaymentService: Payment processing, verification, reversal
- JournalEntryService: Journal entry creation, posting, reversal
- BudgetService: Budget management, tracking, variance analysis
"""

from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from datetime import timedelta
from django.db.models import Sum, Q, F
import logging

from finance.models import (
    Expense, ExpenseCategory, ExpenseLine, ExpensePayment,
    Journal, JournalEntry, JournalTransaction,
    Budget, BudgetLine, Account, FiscalPeriod, FiscalYear,
    PaymentMethod, TaxRate
)
from academics.models import AcademicSession
from core.models import FinancialSettings
from core.utils import get_school_today, get_school_current_time

logger = logging.getLogger(__name__)


# =============================================================================
# EXPENSE SERVICE - CORE EXPENSE OPERATIONS
# =============================================================================

class ExpenseService:
    """
    Core expense operations shared across all modules.
    Handles CRUD, approval workflows, and expense lifecycle.
    """
    
    @staticmethod
    @transaction.atomic
    def create_expense(expense_data):
        """
        Create expense with validation and auto-assignment of accounts.
        
        Args:
            expense_data (dict): Expense information
                Required:
                    - description: str
                    - category: ExpenseCategory instance or ID
                    - total_amount: Decimal
                Optional:
                    - expense_date: Date (defaults to today)
                    - fiscal_period: FiscalPeriod instance or ID (auto-assigned if not provided)
                    - academic_session: AcademicSession instance or ID
                    - vendor_name: str
                    - vendor_contact: str
                    - vendor_reference: str
                    - preferred_payment_method: PaymentMethod instance or code
                    - notes: str
                    - lines: List of expense line dicts
                    
        Returns:
            Expense instance
            
        Example:
            expense = ExpenseService.create_expense({
                'description': 'Office Supplies',
                'category': supplies_category,
                'total_amount': 150000,
                'vendor_name': 'ABC Suppliers',
                'lines': [
                    {'description': 'Paper', 'quantity': 10, 'unit_price': 5000, 'amount': 50000},
                    {'description': 'Pens', 'quantity': 100, 'unit_price': 1000, 'amount': 100000}
                ]
            })
        """
        # Extract lines if provided
        lines_data = expense_data.pop('lines', [])
        
        # Set default expense_date if not provided
        if 'expense_date' not in expense_data:
            expense_data['expense_date'] = get_school_today()
        
        # Resolve foreign keys if IDs provided
        if isinstance(expense_data.get('category'), int):
            expense_data['category'] = ExpenseCategory.objects.get(pk=expense_data['category'])
        
        if isinstance(expense_data.get('academic_session'), int):
            expense_data['academic_session'] = AcademicSession.objects.get(
                pk=expense_data['academic_session']
            )
        
        # Auto-assign fiscal period if not provided
        if 'fiscal_period' not in expense_data:
            expense_data['fiscal_period'] = FiscalPeriod.get_period_for_date(
                expense_data['expense_date']
            )
        elif isinstance(expense_data.get('fiscal_period'), int):
            expense_data['fiscal_period'] = FiscalPeriod.objects.get(
                pk=expense_data['fiscal_period']
            )
        
        # Resolve payment method if provided
        if expense_data.get('preferred_payment_method'):
            if isinstance(expense_data['preferred_payment_method'], str):
                expense_data['preferred_payment_method'] = PaymentMethod.objects.get(
                    code=expense_data['preferred_payment_method']
                )
        
        # Get category for account assignment
        category = expense_data['category']
        
        # Auto-assign expense account from category
        if not expense_data.get('expense_account'):
            if category.default_expense_account:
                expense_data['expense_account'] = category.default_expense_account
            else:
                # Fallback to settings
                settings = FinancialSettings.get_instance()
                if settings:
                    mappings = settings.get_account_mappings()
                    expense_data['expense_account'] = mappings.get_expense_account(category)
        
        # Set initial status based on approval requirements
        if 'status' not in expense_data:
            if category.requires_approval:
                expense_data['status'] = 'PENDING_APPROVAL'
            else:
                expense_data['status'] = 'APPROVED'
        
        # Calculate subtotal from lines or use total_amount
        if lines_data:
            subtotal = sum(Decimal(str(line.get('amount', 0))) for line in lines_data)
            expense_data['subtotal_amount'] = subtotal
        elif 'subtotal_amount' not in expense_data:
            expense_data['subtotal_amount'] = expense_data.get('total_amount', Decimal('0.00'))
        
        # Set tax_amount default
        if 'tax_amount' not in expense_data:
            expense_data['tax_amount'] = Decimal('0.00')
        
        # Create expense
        expense = Expense.objects.create(**expense_data)
        
        # Add lines if provided
        for line_data in lines_data:
            ExpenseService.add_expense_line(expense, line_data)
        
        logger.info(
            f"Created expense {expense.expense_number} for {expense.description} "
            f"(amount: {expense.total_amount}, status: {expense.status})"
        )
        
        return expense
    
    @staticmethod
    @transaction.atomic
    def add_expense_line(expense, line_data):
        """
        Add line item to existing expense.
        
        Args:
            expense: Expense instance
            line_data (dict): Line item information
                Required:
                    - description: str
                    - amount: Decimal
                Optional:
                    - quantity: Decimal (default: 1.00)
                    - unit_price: Decimal
                    - expense_account: Account instance or ID
                    - tax_rate: TaxRate instance or ID
                    - notes: str
                    
        Returns:
            ExpenseLine instance
        """
        # Resolve foreign keys
        if isinstance(line_data.get('expense_account'), int):
            line_data['expense_account'] = Account.objects.get(pk=line_data['expense_account'])
        
        if isinstance(line_data.get('tax_rate'), int):
            line_data['tax_rate'] = TaxRate.objects.get(pk=line_data['tax_rate'])
        
        # Set defaults
        if 'quantity' not in line_data:
            line_data['quantity'] = Decimal('1.00')
        
        if 'unit_price' not in line_data and 'amount' in line_data:
            line_data['unit_price'] = Decimal(str(line_data['amount'])) / line_data['quantity']
        
        # Use expense's account if not specified
        if not line_data.get('expense_account'):
            line_data['expense_account'] = expense.expense_account
        
        # Calculate tax if tax_rate provided
        if line_data.get('tax_rate') and 'tax_amount' not in line_data:
            tax_rate = line_data['tax_rate']
            line_amount = Decimal(str(line_data['amount']))
            line_data['tax_amount'] = (line_amount * tax_rate.rate / 100).quantize(Decimal('0.01'))
        elif 'tax_amount' not in line_data:
            line_data['tax_amount'] = Decimal('0.00')
        
        # Create line
        line = ExpenseLine.objects.create(
            expense=expense,
            **line_data
        )
        
        logger.debug(f"Added line to expense {expense.expense_number}: {line.description}")
        
        return line
    
    @staticmethod
    @transaction.atomic
    def update_expense(expense, update_data):
        """
        Update expense fields.
        
        Args:
            expense: Expense instance
            update_data (dict): Fields to update
            
        Returns:
            Updated Expense instance
            
        Raises:
            ValidationError: If expense is paid or in invalid state for update
        """
        # Prevent updates to paid expenses
        if expense.status == 'PAID':
            raise ValidationError("Cannot update paid expense")
        
        # Prevent updates to cancelled expenses
        if expense.status == 'CANCELLED':
            raise ValidationError("Cannot update cancelled expense")
        
        # Update fields
        for field, value in update_data.items():
            if hasattr(expense, field):
                setattr(expense, field, value)
        
        expense.save()
        
        logger.info(f"Updated expense {expense.expense_number}")
        
        return expense
    
    @staticmethod
    @transaction.atomic
    def submit_for_approval(expense, requested_by_id=None):
        """
        Submit expense for approval.
        
        Args:
            expense: Expense instance
            requested_by_id: User ID who submitted
            
        Returns:
            Updated Expense instance
        """
        if expense.status != 'DRAFT':
            raise ValidationError(f"Cannot submit {expense.get_status_display()} expense for approval")
        
        expense.status = 'PENDING_APPROVAL'
        if requested_by_id:
            expense.requested_by_id = str(requested_by_id)
        expense.save()
        
        logger.info(
            f"Submitted expense {expense.expense_number} for approval "
            f"(by user {requested_by_id or 'System'})"
        )
        
        return expense
    
    @staticmethod
    @transaction.atomic
    def approve_expense(expense, approved_by_id, notes='', auto_create_journal=True):
        """
        Approve an expense.
        
        Args:
            expense: Expense instance
            approved_by_id: User ID who approved
            notes (str): Approval notes
            auto_create_journal (bool): Whether to create journal entry
            
        Returns:
            Updated Expense instance
        """
        if expense.status not in ['PENDING_APPROVAL', 'DRAFT']:
            raise ValidationError(f"Cannot approve {expense.get_status_display()} expense")
        
        expense.status = 'APPROVED'
        expense.approved_by_id = str(approved_by_id)
        expense.approval_date = get_school_current_time()
        if notes:
            expense.approval_notes = notes
        expense.save()
        
        # Create journal entry if enabled
        if auto_create_journal and expense.auto_create_journal_entry:
            try:
                journal_entry = JournalEntryService.create_expense_journal_entry(expense)
                expense.journal_entry = journal_entry
                expense.save(update_fields=['journal_entry'])
            except Exception as e:
                logger.error(f"Error creating journal entry for expense {expense.expense_number}: {e}")
        
        logger.info(
            f"Approved expense {expense.expense_number} "
            f"(by user {approved_by_id})"
        )
        
        return expense
    
    @staticmethod
    @transaction.atomic
    def reject_expense(expense, rejected_by_id, reason):
        """
        Reject an expense.
        
        Args:
            expense: Expense instance
            rejected_by_id: User ID who rejected
            reason (str): Rejection reason
            
        Returns:
            Updated Expense instance
        """
        if expense.status != 'PENDING_APPROVAL':
            raise ValidationError(f"Cannot reject {expense.get_status_display()} expense")
        
        expense.status = 'REJECTED'
        expense.rejected_by_id = str(rejected_by_id)
        expense.rejection_date = get_school_current_time()
        expense.rejection_reason = reason
        expense.save()
        
        logger.info(
            f"Rejected expense {expense.expense_number}: {reason} "
            f"(by user {rejected_by_id})"
        )
        
        return expense
    
    @staticmethod
    @transaction.atomic
    def cancel_expense(expense, reason):
        """
        Cancel an expense.
        
        Args:
            expense: Expense instance
            reason (str): Cancellation reason
            
        Returns:
            Updated Expense instance
            
        Raises:
            ValidationError: If expense has payments or is already paid
        """
        if expense.status == 'PAID':
            raise ValidationError("Cannot cancel paid expense. Reverse payments instead.")
        
        # Check for active payments
        active_payments = expense.payments.filter(reversed=False)
        if active_payments.exists():
            raise ValidationError(
                f"Expense has {active_payments.count()} active payment(s). "
                "Reverse payments before cancelling."
            )
        
        expense.status = 'CANCELLED'
        expense.notes = f"{expense.notes}\n\nCANCELLED: {reason}" if expense.notes else f"CANCELLED: {reason}"
        expense.save()
        
        logger.info(f"Cancelled expense {expense.expense_number}: {reason}")
        
        return expense
    
    @staticmethod
    def get_expense_status(expense):
        """
        Get detailed expense status information.
        
        Args:
            expense: Expense instance
            
        Returns:
            dict: Status information
        """
        active_payments = expense.payments.filter(reversed=False)
        total_paid = active_payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        return {
            'status': expense.status,
            'status_display': expense.get_status_display(),
            'total_amount': expense.total_amount,
            'paid_amount': total_paid,
            'balance': expense.total_amount - total_paid,
            'payment_count': active_payments.count(),
            'is_fully_paid': total_paid >= expense.total_amount,
            'can_be_approved': expense.status in ['DRAFT', 'PENDING_APPROVAL'],
            'can_be_paid': expense.status == 'APPROVED',
            'can_be_cancelled': expense.status in ['DRAFT', 'PENDING_APPROVAL', 'REJECTED'] or (
                expense.status == 'APPROVED' and total_paid == 0
            ),
        }


# =============================================================================
# EXPENSE PAYMENT SERVICE - PAYMENT PROCESSING AND REVERSAL
# =============================================================================

class ExpensePaymentService:
    """
    Expense payment operations including processing, verification, and reversal.
    """
    
    @staticmethod
    @transaction.atomic
    def create_payment(expense, payment_data):
        """
        Create expense payment with validation.
        
        Args:
            expense: Expense instance
            payment_data (dict): Payment information
                Required:
                    - amount: Decimal
                    - payment_method: PaymentMethod instance or code
                    - account: Account instance or ID (payment source)
                Optional:
                    - payment_date: Date (defaults to today)
                    - fiscal_period: FiscalPeriod instance or ID (auto-assigned)
                    - reference_number: str
                    - transaction_id: str
                    - check_number: str
                    - processing_fee: Decimal
                    - bank_charges: Decimal
                    - notes: str
                    - performed_by: str
                    - performed_by_user_id: str
                    
        Returns:
            ExpensePayment instance
        """
        # Validate expense can receive payment
        if expense.status == 'CANCELLED':
            raise ValidationError("Cannot create payment for cancelled expense")
        
        if expense.status != 'APPROVED':
            raise ValidationError(
                f"Expense must be approved before payment. Current status: {expense.get_status_display()}"
            )
        
        # Validate amount
        amount = Decimal(str(payment_data['amount']))
        if amount <= 0:
            raise ValidationError("Payment amount must be positive")
        
        # Set defaults
        if 'payment_date' not in payment_data:
            payment_data['payment_date'] = get_school_today()
        
        # Auto-assign fiscal period
        if 'fiscal_period' not in payment_data:
            payment_data['fiscal_period'] = FiscalPeriod.get_period_for_date(
                payment_data['payment_date']
            )
        elif isinstance(payment_data.get('fiscal_period'), int):
            payment_data['fiscal_period'] = FiscalPeriod.objects.get(
                pk=payment_data['fiscal_period']
            )
        
        # Resolve foreign keys
        if isinstance(payment_data.get('payment_method'), str):
            payment_data['payment_method'] = PaymentMethod.objects.get(
                code=payment_data['payment_method']
            )
        
        if isinstance(payment_data.get('account'), int):
            payment_data['account'] = Account.objects.get(pk=payment_data['account'])
        
        # Set processing fee account if fee provided
        if payment_data.get('processing_fee') and payment_data['processing_fee'] > 0:
            if not payment_data.get('processing_fee_account'):
                settings = FinancialSettings.get_instance()
                if settings:
                    special_mappings = getattr(settings, 'special_account_mappings', None)
                    if special_mappings and hasattr(special_mappings, 'payment_processing_fee_account'):
                        payment_data['processing_fee_account'] = special_mappings.payment_processing_fee_account
        
        # Set defaults for optional fields
        payment_data.setdefault('processing_fee', Decimal('0.00'))
        payment_data.setdefault('bank_charges', Decimal('0.00'))
        payment_data.setdefault('status', 'PENDING')
        
        # Create payment
        payment = ExpensePayment.objects.create(
            expense=expense,
            **payment_data
        )
        
        logger.info(
            f"Created payment for expense {expense.expense_number}: "
            f"{amount} via {payment.payment_method.name} (ref: {payment.reference_number})"
        )
        
        return payment
    
    @staticmethod
    @transaction.atomic
    def verify_payment(payment, verified_by_id, notes='', auto_create_journal=True):
        """
        Verify expense payment and optionally create journal entry.
        
        Args:
            payment: ExpensePayment instance
            verified_by_id: User ID who verified
            notes (str): Verification notes
            auto_create_journal (bool): Whether to create journal entry
            
        Returns:
            Updated ExpensePayment instance
        """
        if payment.status == 'VERIFIED':
            raise ValidationError("Payment is already verified")
        
        if payment.reversed:
            raise ValidationError("Cannot verify reversed payment")
        
        payment.is_verified = True
        payment.verified_by_id = str(verified_by_id)
        payment.verification_date = get_school_current_time()
        if notes:
            payment.verification_notes = notes
        payment.status = 'VERIFIED'
        payment.save()
        
        # Create journal entry if enabled
        if auto_create_journal and payment.auto_create_journal_entry:
            try:
                journal_entry = JournalEntryService.create_expense_payment_journal_entry(payment)
                payment.journal_entry = journal_entry
                payment.save(update_fields=['journal_entry'])
            except Exception as e:
                logger.error(
                    f"Error creating journal entry for payment {payment.reference_number}: {e}"
                )
        
        # Update expense status
        payment.update_expense_status()
        
        logger.info(
            f"Verified payment {payment.reference_number} "
            f"(by user {verified_by_id})"
        )
        
        return payment
    
    @staticmethod
    @transaction.atomic
    def reverse_payment(payment, reversed_by_id, reason, requires_approval=True):
        """
        Reverse an expense payment (internal correction).
        
        Args:
            payment: ExpensePayment instance
            reversed_by_id: User ID who initiated reversal
            reason (str): Reversal reason
            requires_approval (bool): Whether reversal requires approval
            
        Returns:
            Updated ExpensePayment instance
        """
        # Check if can be reversed
        can_reverse, message = payment.can_be_reversed()
        if not can_reverse:
            raise ValidationError(message)
        
        # If requires approval and not yet approved
        if requires_approval and not payment.reversal_approved_by_id:
            payment.reversal_approval_required = True
            payment.reversal_reason = reason
            payment.save(update_fields=['reversal_approval_required', 'reversal_reason'])
            
            logger.info(
                f"Reversal requested for payment {payment.reference_number}: {reason} "
                f"(awaiting approval)"
            )
            return payment
        
        # Perform reversal
        payment.reversed = True
        payment.reversed_by_id = str(reversed_by_id)
        payment.reversed_on = get_school_current_time()
        payment.reversal_reason = reason
        payment.status = 'REVERSED'
        payment.save()
        
        # Create reversal journal entry if original has journal entry
        if payment.journal_entry:
            try:
                reversal_entry = JournalEntryService.reverse_journal_entry(
                    payment.journal_entry,
                    reason=f"Payment reversal: {reason}",
                    reversed_by_id=reversed_by_id
                )
                payment.reversal_journal_entry = reversal_entry
                payment.save(update_fields=['reversal_journal_entry'])
            except Exception as e:
                logger.error(
                    f"Error creating reversal journal entry for payment {payment.reference_number}: {e}"
                )
        
        # Update expense status
        payment.update_expense_status()
        
        logger.info(
            f"Reversed payment {payment.reference_number}: {reason} "
            f"(by user {reversed_by_id})"
        )
        
        return payment
    
    @staticmethod
    @transaction.atomic
    def approve_reversal(payment, approved_by_id):
        """
        Approve payment reversal.
        
        Args:
            payment: ExpensePayment instance
            approved_by_id: User ID who approved
            
        Returns:
            Updated ExpensePayment instance
        """
        if not payment.reversal_approval_required:
            raise ValidationError("This payment reversal does not require approval")
        
        if payment.reversal_approved_by_id:
            raise ValidationError("Reversal already approved")
        
        payment.reversal_approved_by_id = str(approved_by_id)
        payment.reversal_approved_on = get_school_current_time()
        payment.save()
        
        # Now perform the actual reversal
        return ExpensePaymentService.reverse_payment(
            payment,
            reversed_by_id=payment.reversed_by_id or approved_by_id,
            reason=payment.reversal_reason,
            requires_approval=False  # Already approved
        )
    
    @staticmethod
    def get_payment_summary(expense):
        """
        Get payment summary for expense.
        
        Args:
            expense: Expense instance
            
        Returns:
            dict: Payment summary
        """
        all_payments = expense.payments.all()
        active_payments = all_payments.filter(reversed=False)
        reversed_payments = all_payments.filter(reversed=True)
        
        total_paid = active_payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        total_reversed = reversed_payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        total_fees = active_payments.aggregate(
            total=Sum(F('processing_fee') + F('bank_charges'))
        )['total'] or Decimal('0.00')
        
        return {
            'total_amount': expense.total_amount,
            'total_paid': total_paid,
            'total_reversed': total_reversed,
            'total_fees': total_fees,
            'net_disbursed': total_paid + total_fees,
            'balance': expense.total_amount - total_paid,
            'payment_count': active_payments.count(),
            'reversed_count': reversed_payments.count(),
            'last_payment_date': active_payments.order_by('-payment_date').first().payment_date 
                if active_payments.exists() else None,
        }


# =============================================================================
# JOURNAL ENTRY SERVICE - ACCOUNTING INTEGRATION
# =============================================================================

class JournalEntryService:
    """
    Journal entry operations for double-entry bookkeeping.
    """
    
    @staticmethod
    @transaction.atomic
    def create_expense_journal_entry(expense):
        """
        Create journal entry for approved expense (records liability).
        
        Journal Entry:
            DR: Expense Account (expense.expense_account)
            CR: Accounts Payable (from settings)
        
        Args:
            expense: Expense instance
            
        Returns:
            JournalEntry instance
        """
        if expense.status != 'APPROVED':
            raise ValidationError("Can only create journal entry for approved expenses")
        
        if expense.journal_entry:
            raise ValidationError("Journal entry already exists for this expense")
        
        # Get accounts
        expense_account = expense.get_expense_account()
        payable_account = expense.get_payable_account()
        
        if not expense_account:
            raise ValidationError("Expense account not configured")
        if not payable_account:
            raise ValidationError("Accounts payable account not configured")
        
        # Get or create expense journal
        journal, _ = Journal.objects.get_or_create(
            journal_type='EXPENSES',
            defaults={
                'name': 'Expense Journal',
                'description': 'Journal for recording approved expenses'
            }
        )
        
        # Create journal entry
        entry = JournalEntry.objects.create(
            journal=journal,
            entry_date=expense.expense_date,
            fiscal_period=expense.fiscal_period,
            academic_session=expense.academic_session,
            description=f"Expense: {expense.description}",
            reference_number=expense.expense_number,
            status='POSTED',
            posted_at=get_school_current_time()
        )
        
        # Create transactions
        # DR: Expense Account
        JournalTransaction.objects.create(
            journal_entry=entry,
            account=expense_account,
            description=f"Expense: {expense.description}",
            amount=expense.total_amount,
            is_debit=True
        )
        
        # CR: Accounts Payable
        JournalTransaction.objects.create(
            journal_entry=entry,
            account=payable_account,
            description=f"Payable for: {expense.description}",
            amount=expense.total_amount,
            is_debit=False
        )
        
        logger.info(
            f"Created journal entry {entry.entry_number} for expense {expense.expense_number}"
        )
        
        return entry
    
    @staticmethod
    @transaction.atomic
    def create_expense_payment_journal_entry(payment):
        """
        Create journal entry for expense payment (records payment and fees).
        
        Journal Entry:
            DR: Accounts Payable
            DR: Processing Fee Expense (if applicable)
            CR: Cash/Bank Account
        
        Args:
            payment: ExpensePayment instance
            
        Returns:
            JournalEntry instance
        """
        if not payment.is_verified:
            raise ValidationError("Can only create journal entry for verified payments")
        
        if payment.reversed:
            raise ValidationError("Cannot create journal entry for reversed payment")
        
        if payment.journal_entry:
            raise ValidationError("Journal entry already exists for this payment")
        
        # Get accounts
        payable_account = payment.get_payable_account()
        payment_account = payment.get_payment_account()
        
        if not payable_account:
            raise ValidationError("Accounts payable account not configured")
        if not payment_account:
            raise ValidationError("Payment account not configured")
        
        # Get journal
        journal, _ = Journal.objects.get_or_create(
            journal_type='CASH' if payment.payment_method.is_cash else 'BANK',
            defaults={
                'name': 'Cash Journal' if payment.payment_method.is_cash else 'Bank Journal',
                'description': f"Journal for {'cash' if payment.payment_method.is_cash else 'bank'} transactions"
            }
        )
        
        # Create journal entry
        entry = JournalEntry.objects.create(
            journal=journal,
            entry_date=payment.payment_date,
            fiscal_period=payment.fiscal_period,
            description=f"Payment for: {payment.expense.description}",
            reference_number=payment.reference_number or payment.transaction_id,
            status='POSTED',
            posted_at=get_school_current_time()
        )
        
        # DR: Accounts Payable
        JournalTransaction.objects.create(
            journal_entry=entry,
            account=payable_account,
            description=f"Payment: {payment.expense.expense_number}",
            amount=payment.amount,
            is_debit=True
        )
        
        # DR: Processing Fee Expense (if applicable)
        if payment.processing_fee > 0:
            fee_account = payment.get_processing_fee_account()
            if fee_account:
                JournalTransaction.objects.create(
                    journal_entry=entry,
                    account=fee_account,
                    description=f"Processing fee: {payment.payment_method.name}",
                    amount=payment.processing_fee,
                    is_debit=True
                )
        
        # CR: Cash/Bank Account
        total_credit = payment.amount + payment.processing_fee + payment.bank_charges
        JournalTransaction.objects.create(
            journal_entry=entry,
            account=payment_account,
            description=f"Payment via {payment.payment_method.name}",
            amount=total_credit,
            is_debit=False
        )
        
        logger.info(
            f"Created journal entry {entry.entry_number} for payment {payment.reference_number}"
        )
        
        return entry
    
    @staticmethod
    @transaction.atomic
    def reverse_journal_entry(original_entry, reason, reversed_by_id=None):
        """
        Create reversing journal entry.
        
        Args:
            original_entry: JournalEntry instance to reverse
            reason (str): Reversal reason
            reversed_by_id: User ID who reversed
            
        Returns:
            JournalEntry instance (reversal)
        """
        if original_entry.status == 'REVERSED':
            raise ValidationError("Journal entry is already reversed")
        
        if original_entry.status != 'POSTED':
            raise ValidationError("Can only reverse posted journal entries")
        
        # Create reversal entry
        reversal_entry = JournalEntry.objects.create(
            journal=original_entry.journal,
            entry_date=get_school_today(),
            fiscal_period=FiscalPeriod.get_period_for_date(get_school_today()),
            academic_session=original_entry.academic_session,
            description=f"REVERSAL: {original_entry.description}",
            reference_number=f"REV-{original_entry.entry_number}",
            notes=f"Reversal of {original_entry.entry_number}: {reason}",
            status='POSTED',
            posted_at=get_school_current_time(),
            original_entry=original_entry
        )
        
        # Create reverse transactions (flip debits and credits)
        for transaction in original_entry.transactions.all():
            JournalTransaction.objects.create(
                journal_entry=reversal_entry,
                account=transaction.account,
                description=f"Reversal: {transaction.description}",
                amount=transaction.amount,
                is_debit=not transaction.is_debit  # Flip debit/credit
            )
        
        # Mark original as reversed
        original_entry.status = 'REVERSED'
        original_entry.reversed_at = get_school_current_time()
        original_entry.reversed_by_id = str(reversed_by_id) if reversed_by_id else None
        original_entry.reversal_reason = reason
        original_entry.save()
        
        logger.info(
            f"Created reversal entry {reversal_entry.entry_number} "
            f"for {original_entry.entry_number}: {reason}"
        )
        
        return reversal_entry


# =============================================================================
# BUDGET SERVICE - BUDGET MANAGEMENT AND TRACKING
# =============================================================================

class BudgetService:
    """
    Budget operations including creation, tracking, and variance analysis.
    """
    
    @staticmethod
    @transaction.atomic
    def create_budget(budget_data):
        """
        Create budget with validation.
        
        Args:
            budget_data (dict): Budget information
                Required:
                    - name: str
                    - budget_type: str
                    - academic_session: AcademicSession instance or ID
                    - fiscal_year: FiscalYear instance or ID
                    - start_date: Date
                    - end_date: Date
                Optional:
                    - description: str
                    - parent_budget: Budget instance or ID
                    - lines: List of budget line dicts
                    
        Returns:
            Budget instance
        """
        # Extract lines if provided
        lines_data = budget_data.pop('lines', [])
        
        # Resolve foreign keys
        if isinstance(budget_data.get('academic_session'), int):
            budget_data['academic_session'] = AcademicSession.objects.get(
                pk=budget_data['academic_session']
            )
        
        if isinstance(budget_data.get('fiscal_year'), int):
            budget_data['fiscal_year'] = FiscalYear.objects.get(
                pk=budget_data['fiscal_year']
            )
        
        if isinstance(budget_data.get('parent_budget'), int):
            budget_data['parent_budget'] = Budget.objects.get(
                pk=budget_data['parent_budget']
            )
        
        # Set defaults
        budget_data.setdefault('status', 'DRAFT')
        budget_data.setdefault('total_revenue_budget', Decimal('0.00'))
        budget_data.setdefault('total_expense_budget', Decimal('0.00'))
        budget_data.setdefault('net_budget', Decimal('0.00'))
        
        # Create budget
        budget = Budget.objects.create(**budget_data)
        
        # Add lines if provided
        for line_data in lines_data:
            BudgetService.add_budget_line(budget, line_data)
        
        logger.info(f"Created budget {budget.name} for {budget.academic_session}")
        
        return budget
    
    @staticmethod
    @transaction.atomic
    def add_budget_line(budget, line_data):
        """
        Add line item to budget.
        
        Args:
            budget: Budget instance
            line_data (dict): Line information
                Required:
                    - line_type: 'REVENUE' or 'EXPENSE'
                    - account: Account instance or ID
                    - budgeted_amount: Decimal
                Optional:
                    - description: str
                    - notes: str
                    
        Returns:
            BudgetLine instance
        """
        # Resolve foreign keys
        if isinstance(line_data.get('account'), int):
            line_data['account'] = Account.objects.get(pk=line_data['account'])
        
        # Set defaults
        line_data.setdefault('actual_amount', Decimal('0.00'))
        
        # Create line
        line = BudgetLine.objects.create(
            budget=budget,
            **line_data
        )
        
        # Update budget totals
        BudgetService._update_budget_totals(budget)
        
        logger.debug(f"Added budget line to {budget.name}: {line.account.name}")
        
        return line
    
    @staticmethod
    @transaction.atomic
    def approve_budget(budget, approved_by_id):
        """
        Approve budget.
        
        Args:
            budget: Budget instance
            approved_by_id: User ID who approved
            
        Returns:
            Updated Budget instance
        """
        if budget.status not in ['DRAFT', 'SUBMITTED']:
            raise ValidationError(f"Cannot approve {budget.get_status_display()} budget")
        
        budget.status = 'APPROVED'
        budget.approved_by_id = str(approved_by_id)
        budget.approval_date = get_school_current_time()
        budget.save()
        
        logger.info(f"Approved budget {budget.name} (by user {approved_by_id})")
        
        return budget
    
    @staticmethod
    @transaction.atomic
    def activate_budget(budget):
        """
        Activate approved budget.
        
        Args:
            budget: Budget instance
            
        Returns:
            Updated Budget instance
        """
        if budget.status != 'APPROVED':
            raise ValidationError("Budget must be approved before activation")
        
        budget.status = 'ACTIVE'
        budget.save()
        
        logger.info(f"Activated budget {budget.name}")
        
        return budget
    
    @staticmethod
    def sync_budget_actuals(budget):
        """
        Synchronize budget actual amounts from transactions.
        
        Args:
            budget: Budget instance
            
        Returns:
            dict: Sync results
        """
        updated_lines = 0
        
        for line in budget.lines.all():
            # Get actual amount from transactions
            actual = JournalTransaction.objects.filter(
                account=line.account,
                journal_entry__entry_date__gte=budget.start_date,
                journal_entry__entry_date__lte=budget.end_date,
                journal_entry__status='POSTED'
            ).aggregate(
                total=Sum('amount', filter=Q(is_debit=True)) - 
                      Sum('amount', filter=Q(is_debit=False))
            )['total'] or Decimal('0.00')
            
            # Update line
            if line.actual_amount != actual:
                line.actual_amount = actual
                line.save(update_fields=['actual_amount'])
                updated_lines += 1
        
        # Update budget totals
        revenue_actual = budget.lines.filter(line_type='REVENUE').aggregate(
            total=Sum('actual_amount')
        )['total'] or Decimal('0.00')
        
        expense_actual = budget.lines.filter(line_type='EXPENSE').aggregate(
            total=Sum('actual_amount')
        )['total'] or Decimal('0.00')
        
        budget.actual_revenue_total = revenue_actual
        budget.actual_expense_total = expense_actual
        budget.last_actuals_sync = get_school_current_time()
        budget.save(update_fields=['actual_revenue_total', 'actual_expense_total', 'last_actuals_sync'])
        
        logger.info(
            f"Synced actuals for budget {budget.name}: "
            f"{updated_lines} lines updated"
        )
        
        return {
            'updated_lines': updated_lines,
            'revenue_actual': revenue_actual,
            'expense_actual': expense_actual,
            'sync_time': budget.last_actuals_sync
        }
    
    @staticmethod
    def get_budget_variance_analysis(budget):
        """
        Get variance analysis for budget.
        
        Args:
            budget: Budget instance
            
        Returns:
            dict: Variance analysis
        """
        # Sync actuals first if auto-sync enabled
        if budget.auto_sync_actuals:
            BudgetService.sync_budget_actuals(budget)
        
        # Calculate variances
        revenue_variance = budget.actual_revenue_total - budget.total_revenue_budget
        expense_variance = budget.actual_expense_total - budget.total_expense_budget
        net_variance = revenue_variance - expense_variance
        
        # Calculate percentages
        revenue_pct = (revenue_variance / budget.total_revenue_budget * 100) if budget.total_revenue_budget > 0 else Decimal('0.00')
        expense_pct = (expense_variance / budget.total_expense_budget * 100) if budget.total_expense_budget > 0 else Decimal('0.00')
        
        # Line-level variances
        line_variances = []
        for line in budget.lines.all():
            variance = line.actual_amount - line.budgeted_amount
            variance_pct = (variance / line.budgeted_amount * 100) if line.budgeted_amount > 0 else Decimal('0.00')
            
            line_variances.append({
                'account': line.account.name,
                'line_type': line.get_line_type_display(),
                'budgeted': line.budgeted_amount,
                'actual': line.actual_amount,
                'variance': variance,
                'variance_percentage': variance_pct,
                'status': 'OVER' if variance > 0 else 'UNDER' if variance < 0 else 'ON_TARGET'
            })
        
        return {
            'budget_name': budget.name,
            'period': f"{budget.start_date} to {budget.end_date}",
            'revenue': {
                'budgeted': budget.total_revenue_budget,
                'actual': budget.actual_revenue_total,
                'variance': revenue_variance,
                'variance_percentage': revenue_pct
            },
            'expenses': {
                'budgeted': budget.total_expense_budget,
                'actual': budget.actual_expense_total,
                'variance': expense_variance,
                'variance_percentage': expense_pct
            },
            'net': {
                'budgeted': budget.net_budget,
                'actual': budget.actual_revenue_total - budget.actual_expense_total,
                'variance': net_variance
            },
            'line_variances': line_variances,
            'last_sync': budget.last_actuals_sync
        }
    
    @staticmethod
    def _update_budget_totals(budget):
        """
        Update budget total amounts from lines.
        
        Args:
            budget: Budget instance
        """
        revenue_total = budget.lines.filter(line_type='REVENUE').aggregate(
            total=Sum('budgeted_amount')
        )['total'] or Decimal('0.00')
        
        expense_total = budget.lines.filter(line_type='EXPENSE').aggregate(
            total=Sum('budgeted_amount')
        )['total'] or Decimal('0.00')
        
        budget.total_revenue_budget = revenue_total
        budget.total_expense_budget = expense_total
        budget.net_budget = revenue_total - expense_total
        budget.save(update_fields=['total_revenue_budget', 'total_expense_budget', 'net_budget'])


# =============================================================================
# BULK OPERATIONS
# =============================================================================

class ExpenseBulkOperations:
    """Bulk operations for expenses"""
    
    @staticmethod
    @transaction.atomic
    def bulk_approve_expenses(expenses, approved_by_id, notes=''):
        """
        Approve multiple expenses at once.
        
        Args:
            expenses: QuerySet or list of Expense instances
            approved_by_id: User ID who approved
            notes (str): Approval notes
            
        Returns:
            dict: Results
        """
        results = {
            'approved': [],
            'failed': [],
            'total': len(expenses)
        }
        
        for expense in expenses:
            try:
                ExpenseService.approve_expense(expense, approved_by_id, notes)
                results['approved'].append(expense)
            except Exception as e:
                logger.error(f"Error approving expense {expense.expense_number}: {e}")
                results['failed'].append({
                    'expense': expense,
                    'error': str(e)
                })
        
        return results
    
    @staticmethod
    @transaction.atomic
    def bulk_cancel_expenses(expenses, reason):
        """
        Cancel multiple expenses at once.
        
        Args:
            expenses: QuerySet or list of Expense instances
            reason (str): Cancellation reason
            
        Returns:
            dict: Results
        """
        results = {
            'cancelled': [],
            'failed': [],
            'total': len(expenses)
        }
        
        for expense in expenses:
            try:
                ExpenseService.cancel_expense(expense, reason)
                results['cancelled'].append(expense)
            except Exception as e:
                logger.error(f"Error cancelling expense {expense.expense_number}: {e}")
                results['failed'].append({
                    'expense': expense,
                    'error': str(e)
                })
        
        return results