# hr/services.py

"""
HR Services

Complex HR workflows with database operations:
- Staff ID generation (WITH DB writes)
- Contract number generation (WITH DB writes)
- Payroll processing and accounting
- Staff management workflows
- Contract lifecycle management

For pure calculations without DB writes, see hr/utils.py
"""

from decimal import Decimal
from django.db import transaction
from django.db.models import Sum, Max
from django.utils import timezone
from django.core.exceptions import ValidationError
from datetime import timedelta
import logging

from hr.models import (
    Staff, Contract, StaffDesignation,
    Payroll, PayrollAllowance, PayrollDeduction, PayrollBonus,
    Teacher, Department, Designation
)
from hr.utils import (
    get_century_safe_year_suffix, get_staff_type_code,
    build_staff_id_prefix, build_contract_number_prefix,
    get_contract_type_code, calculate_monthly_salary,
    validate_staff_data, validate_contract_data
)
from finance.models import JournalEntry, JournalTransaction, Journal
from core.models import FinancialSettings, FiscalPeriod
from fees.models import PaymentMethod

logger = logging.getLogger(__name__)


# =============================================================================
# STAFF ID GENERATION SERVICE (WITH DB OPERATIONS)
# =============================================================================

class StaffIDGenerationService:
    """
    Generate unique staff IDs with database locking.
    Uses utils.py for pure logic, adds DB operations here.
    """
    
    @staticmethod
    @transaction.atomic
    def generate_staff_id(
        *,
        school=None,
        user=None,
        joining_year=None,
        department=None,
        employment_status='FT',
        is_teaching=False
    ):
        """
        Generate a unique century-safe staff ID WITH database locking.

        Format:
            YY/SCHOOL/TYPE-NNN
            YY/SCHOOL/DEPT/TYPE-NNN (if department provided)
            AYY/SCHOOL/TYPE-NNN (for years beyond 2099)
        
        Args:
            school: School instance
            user: User instance (alternative to school)
            joining_year: Year of joining (defaults to current year)
            department: Department instance (optional)
            employment_status: Employment status code
            is_teaching: Whether this is a teaching staff
            
        Returns:
            str: Unique staff ID
            
        Examples:
            generate_staff_id(school=sch, is_teaching=True) → "24/ATEPI/TCH-001"
            generate_staff_id(school=sch, department=math) → "24/ATEPI/MATH/TCH-001"
        """
        current_year = joining_year or timezone.now().year

        # -----------------------------
        # Resolve school abbreviation
        # -----------------------------
        school_abbrev = "SCH"

        if school and school.abbreviation:
            school_abbrev = school.abbreviation
        elif user:
            try:
                from accounts.models import UserProfile
                profile = UserProfile.objects.select_related("school").get(user=user)
                if profile.school and profile.school.abbreviation:
                    school_abbrev = profile.school.abbreviation
            except Exception:
                pass

        # -----------------------------
        # Build prefix using pure utility
        # -----------------------------
        staff_type = get_staff_type_code(employment_status, is_teaching)
        dept_code = department.code if department else None
        
        prefix = build_staff_id_prefix(
            current_year,
            school_abbrev,
            dept_code,
            staff_type
        )

        # -----------------------------
        # Generate sequential number WITH DB LOCK
        # -----------------------------
        while True:
            # Use select_for_update to prevent race conditions
            last_staff = (
                Staff.objects
                .select_for_update()
                .filter(staff_id__startswith=prefix)
                .order_by("-staff_id")
                .first()
            )

            if last_staff:
                try:
                    last_seq = int(last_staff.staff_id.split("-")[-1])
                    next_seq = last_seq + 1
                except (ValueError, IndexError):
                    next_seq = (
                        Staff.objects
                        .filter(staff_id__startswith=prefix)
                        .count() + 1
                    )
            else:
                next_seq = 1

            staff_id = f"{prefix}{next_seq:03d}"

            # Double-check uniqueness
            if not Staff.objects.filter(staff_id=staff_id).exists():
                logger.info(f"Generated staff ID: {staff_id}")
                return staff_id


# =============================================================================
# CONTRACT NUMBER GENERATION SERVICE (WITH DB OPERATIONS)
# =============================================================================

class ContractNumberGenerationService:
    """
    Generate unique contract numbers with database locking.
    Uses utils.py for pure logic, adds DB operations here.
    """
    
    @staticmethod
    @transaction.atomic
    def generate_contract_number(contract_type=None, year=None):
        """
        Generate a unique century-safe contract number WITH database locking.
        
        Format: CONT/YYYY/TYPE/NNNN or CONT/AYYYY/TYPE/NNNN (for years beyond 2099)
        
        Args:
            contract_type: Contract type name (optional)
            year: Contract year (defaults to current year)
            
        Returns:
            str: Unique contract number
            
        Examples:
            generate_contract_number() → "CONT/2024/GEN/0001"
            generate_contract_number("Permanent") → "CONT/2024/PERM/0001"
            generate_contract_number("Temporary", 2125) → "CONT/A125/TEMP/0001"
        """
        current_year = year or timezone.now().year
        
        # Get type code using pure utility
        type_code = "GEN"
        if contract_type:
            if isinstance(contract_type, str):
                type_code = get_contract_type_code(contract_type)
            else:
                # Assume it's an object with a name attribute
                type_code = get_contract_type_code(contract_type.name)
        
        # Build prefix using pure utility
        prefix = build_contract_number_prefix(current_year, type_code)
        
        # Generate sequential number WITH DB LOCK
        while True:
            last_contract = (
                Contract.objects
                .select_for_update()
                .filter(contract_number__startswith=prefix)
                .order_by("-contract_number")
                .first()
            )
            
            if last_contract:
                try:
                    last_seq = int(last_contract.contract_number.split("/")[-1])
                    next_seq = last_seq + 1
                except (ValueError, IndexError):
                    next_seq = (
                        Contract.objects
                        .filter(contract_number__startswith=prefix)
                        .count() + 1
                    )
            else:
                next_seq = 1
            
            contract_number = f"{prefix}{next_seq:04d}"
            
            # Double-check uniqueness
            if not Contract.objects.filter(contract_number=contract_number).exists():
                logger.info(f"Generated contract number: {contract_number}")
                return contract_number


# =============================================================================
# STAFF MANAGEMENT SERVICE
# =============================================================================

class StaffManagementService:
    """Complete staff management workflows"""
    
    @staticmethod
    @transaction.atomic
    def create_staff(staff_data, user=None):
        """
        Create staff member with complete workflow:
        1. Validate data
        2. Generate staff ID
        3. Create staff record
        4. Create initial designation assignment
        
        Args:
            staff_data (dict): Staff information
            user: User creating the staff
            
        Returns:
            Staff instance
        """
        # Validate data
        validation = validate_staff_data(staff_data)
        if not validation['valid']:
            raise ValidationError(validation['errors'])
        
        # Log warnings
        if validation['warnings']:
            for warning in validation['warnings']:
                logger.warning(f"Staff creation warning: {warning}")
        
        # Generate staff ID
        staff_id = StaffIDGenerationService.generate_staff_id(
            school=staff_data.get('school'),
            user=user,
            joining_year=staff_data.get('date_of_joining').year if staff_data.get('date_of_joining') else None,
            department=staff_data.get('primary_department'),
            employment_status=staff_data.get('employment_status', 'FT'),
            is_teaching=staff_data.get('is_teaching', False)
        )
        
        # Create staff
        staff = Staff.objects.create(
            staff_id=staff_id,
            **staff_data
        )
        
        logger.info(f"Created staff: {staff.full_name()} ({staff.staff_id})")
        
        return staff
    
    @staticmethod
    @transaction.atomic
    def update_staff_designation(staff, designation, is_primary=False, **kwargs):
        """
        Update staff designation assignment.
        
        Args:
            staff: Staff instance
            designation: Designation instance
            is_primary: Whether this is primary designation
            **kwargs: Additional StaffDesignation fields
            
        Returns:
            StaffDesignation instance
        """
        # If setting as primary, unset other primary designations
        if is_primary:
            StaffDesignation.objects.filter(
                staff=staff,
                is_primary=True
            ).update(is_primary=False)
        
        # Create or update designation
        designation_assignment, created = StaffDesignation.objects.update_or_create(
            staff=staff,
            designation=designation,
            defaults={
                'is_primary': is_primary,
                **kwargs
            }
        )
        
        action = "Created" if created else "Updated"
        logger.info(
            f"{action} designation assignment: {staff.full_name()} - "
            f"{designation.name} (Primary: {is_primary})"
        )
        
        return designation_assignment


# =============================================================================
# CONTRACT MANAGEMENT SERVICE
# =============================================================================

class ContractManagementService:
    """Complete contract lifecycle management"""
    
    @staticmethod
    @transaction.atomic
    def create_contract(contract_data, user=None):
        """
        Create contract with complete workflow:
        1. Validate data
        2. Generate contract number
        3. Create contract record
        4. Update staff employment status
        
        Args:
            contract_data (dict): Contract information
            user: User creating the contract
            
        Returns:
            Contract instance
        """
        # Validate data
        validation = validate_contract_data(contract_data)
        if not validation['valid']:
            raise ValidationError(validation['errors'])
        
        # Generate contract number
        contract_number = ContractNumberGenerationService.generate_contract_number(
            contract_type=contract_data.get('contract_type'),
            year=contract_data.get('start_date').year if contract_data.get('start_date') else None
        )
        
        # Create contract
        contract = Contract.objects.create(
            contract_number=contract_number,
            **contract_data
        )
        
        logger.info(f"Created contract: {contract.contract_number} for {contract.staff.full_name()}")
        
        return contract
    
    @staticmethod
    @transaction.atomic
    def activate_contract(contract, user=None):
        """
        Activate a contract and update staff status.
        
        Args:
            contract: Contract instance
            user: User activating the contract
        """
        if contract.status == 'ACTIVE':
            logger.warning(f"Contract {contract.contract_number} is already active")
            return
        
        # Deactivate other active contracts for this staff
        Contract.objects.filter(
            staff=contract.staff,
            status='ACTIVE'
        ).exclude(pk=contract.pk).update(status='EXPIRED')
        
        # Activate contract
        contract.status = 'ACTIVE'
        if user:
            contract.approved_by_id = str(user.id) if hasattr(user, 'id') else str(user.pk)
            contract.approved_at = timezone.now()
        contract.save()
        
        # Update staff employment status
        staff = contract.staff
        staff.employment_status = contract.contract_type
        staff.is_active = True
        staff.save()
        
        logger.info(f"Activated contract: {contract.contract_number}")
    
    @staticmethod
    @transaction.atomic
    def terminate_contract(contract, reason, user=None, termination_date=None, notes=''):
        """
        Terminate a contract.
        
        Args:
            contract: Contract instance
            reason: Termination reason
            user: User terminating the contract
            termination_date: Date of termination
            notes: Termination notes
        """
        contract.terminate(reason, user, termination_date, notes)
        
        # Update staff status if no other active contracts
        staff = contract.staff
        active_contracts = Contract.objects.filter(
            staff=staff,
            status='ACTIVE'
        ).exclude(pk=contract.pk).count()
        
        if active_contracts == 0:
            staff.is_active = False
            staff.employment_status = 'TR'  # Terminated
            staff.date_of_leaving = termination_date or timezone.now().date()
            staff.save()
        
        logger.info(f"Terminated contract: {contract.contract_number}")


# =============================================================================
# PAYROLL CALCULATION SERVICE
# =============================================================================

class PayrollCalculationService:
    """Calculate payroll amounts"""
    
    @staticmethod
    def calculate_payroll(payroll):
        """
        Calculate all payroll amounts.
        
        Args:
            payroll: Payroll instance
            
        Returns:
            dict: Calculated amounts
        """
        from django.db.models import Sum
        
        # Calculate gross pay
        gross_pay = PayrollCalculationService.calculate_gross_pay(payroll)
        
        # Calculate total deductions
        total_deductions = PayrollCalculationService.calculate_total_deductions(payroll)
        
        # Calculate net pay
        net_pay = gross_pay - total_deductions
        
        # Update payroll
        payroll.gross_pay = gross_pay
        payroll.total_deductions = total_deductions
        payroll.net_pay = net_pay
        payroll.save(update_fields=['gross_pay', 'total_deductions', 'net_pay'])
        
        return {
            'basic_salary': payroll.basic_salary,
            'gross_pay': gross_pay,
            'total_deductions': total_deductions,
            'net_pay': net_pay
        }
    
    @staticmethod
    def calculate_gross_pay(payroll):
        """Calculate gross pay = basic salary + allowances + bonuses"""
        from django.db.models import Sum
        
        total = payroll.basic_salary
        
        # Add allowances
        total += payroll.allowances.aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')
        
        # Add bonuses
        total += payroll.bonuses.aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')
        
        return total
    
    @staticmethod
    def calculate_total_deductions(payroll):
        """Calculate total deductions"""
        from django.db.models import Sum
        
        total = payroll.deductions.aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')
        
        return total


# =============================================================================
# PAYROLL ACCOUNTING SERVICE
# =============================================================================

class PayrollAccountingService:
    """Handle payroll accounting and journal entries"""
    
    @staticmethod
    @transaction.atomic
    def create_payroll_journal_entry(payroll):
        """
        Create comprehensive journal entry for payroll.
        
        Journal Entry Structure:
        
        DEBIT ENTRIES (Expenses):
        - Salaries Expense (basic salary)
        - Housing Allowance Expense
        - Transport Allowance Expense
        - Medical Allowance Expense
        - Overtime Expense
        - Bonus Expense
        - Commission Expense
        
        CREDIT ENTRIES (Liabilities):
        - Wages Payable (net pay to be paid)
        - Payroll Tax Payable (PAYE withheld)
        - Social Security Payable (NSSF withheld)
        - Pension Payable (pension withheld)
        - Staff Loan Receivable (loan deductions)
        - Staff Advance (advance deductions)
        
        Args:
            payroll: Payroll instance
            
        Returns:
            JournalEntry instance
        """
        if payroll.status != 'APPROVED':
            raise ValueError("Can only create journal entry for approved payroll")
        
        # Check if already has journal entry
        from finance.models import JournalEntry as FinanceJournalEntry
        existing_entry = FinanceJournalEntry.objects.filter(
            reference_number=f"PAYROLL-{payroll.staff.staff_id}-{payroll.period.code if hasattr(payroll.period, 'code') else payroll.period.pk}"
        ).first()
        
        if existing_entry:
            logger.warning(f"Payroll {payroll.pk} already has journal entry")
            return existing_entry
        
        # Get accounts from settings
        settings = FinancialSettings.get_instance()
        if not settings:
            raise ValueError("FinancialSettings not found")
        
        accounts = settings.get_payroll_accounts()
        
        # Get or create payroll journal
        journal, _ = Journal.objects.get_or_create(
            journal_type='PAYROLL',
            defaults={
                'name': 'Payroll Journal',
                'description': 'Journal for payroll transactions',
                'is_active': True
            }
        )
        
        # Create journal entry
        entry = JournalEntry.objects.create(
            journal=journal,
            entry_date=payroll.payment_date,
            fiscal_period=payroll.fiscal_year.periods.first() if hasattr(payroll, 'fiscal_year') and payroll.fiscal_year else FiscalPeriod.get_current_fiscal_period(),
            reference_number=f"PAYROLL-{payroll.staff.staff_id}-{payroll.period.code if hasattr(payroll.period, 'code') else payroll.period.pk}",
            description=f"Payroll for {payroll.staff.full_name()} - {payroll.period.name if hasattr(payroll.period, 'name') else 'Period'}",
            status='POSTED'
        )
        
        # =================================================================
        # DEBIT ENTRIES - EXPENSES
        # =================================================================
        
        # 1. Basic Salary Expense
        if payroll.basic_salary > 0 and accounts['salaries_expense']:
            JournalTransaction.objects.create(
                journal_entry=entry,
                account=accounts['salaries_expense'],
                description=f"Basic Salary - {payroll.staff.full_name()}",
                amount=payroll.basic_salary,
                is_debit=True
            )
        
        # 2. Allowance Expenses
        for allowance in payroll.allowances.all():
            expense_account = settings.get_allowance_expense_account(allowance.allowance_type)
            if expense_account and allowance.amount > 0:
                JournalTransaction.objects.create(
                    journal_entry=entry,
                    account=expense_account,
                    description=f"{allowance.get_allowance_type_display()} - {payroll.staff.full_name()}",
                    amount=allowance.amount,
                    is_debit=True
                )
        
        # 3. Bonus/Overtime Expenses
        for bonus in payroll.bonuses.all():
            expense_account = settings.get_bonus_expense_account(bonus.bonus_type)
            if expense_account and bonus.amount > 0:
                JournalTransaction.objects.create(
                    journal_entry=entry,
                    account=expense_account,
                    description=f"{bonus.get_bonus_type_display()} - {payroll.staff.full_name()}",
                    amount=bonus.amount,
                    is_debit=True
                )
        
        # =================================================================
        # CREDIT ENTRIES - LIABILITIES & REDUCTIONS
        # =================================================================
        
        # 4. Wages Payable (Net Pay - what employee receives)
        if payroll.net_pay > 0 and accounts['wages_payable']:
            JournalTransaction.objects.create(
                journal_entry=entry,
                account=accounts['wages_payable'],
                description=f"Net Pay - {payroll.staff.full_name()}",
                amount=payroll.net_pay,
                is_debit=False  # Credit
            )
        
        # 5. Deduction Liabilities (amounts withheld)
        for deduction in payroll.deductions.all():
            liability_account = settings.get_deduction_payable_account(deduction.deduction_type)
            if liability_account and deduction.amount > 0:
                JournalTransaction.objects.create(
                    journal_entry=entry,
                    account=liability_account,
                    description=f"{deduction.get_deduction_type_display()} - {payroll.staff.full_name()}",
                    amount=deduction.amount,
                    is_debit=False  # Credit
                )
        
        logger.info(
            f"Created payroll journal entry {entry.entry_number} for "
            f"{payroll.staff.full_name()} - Period: {payroll.period.name if hasattr(payroll.period, 'name') else 'N/A'}"
        )
        
        return entry
    
    @staticmethod
    @transaction.atomic
    def create_payment_disbursement_entry(payroll):
        """
        Create journal entry when payroll is actually paid.
        
        Journal Entry:
        Debit:  Wages Payable         [Net Pay]
        Credit: Bank Account                     [Net Pay]
        
        Args:
            payroll: Payroll instance with status='PAID'
            
        Returns:
            JournalEntry instance
        """
        if payroll.status != 'PAID':
            raise ValueError("Can only create disbursement entry for paid payroll")
        
        # Get accounts
        settings = FinancialSettings.get_instance()
        accounts = settings.get_payroll_accounts()
        
        # Determine bank/cash account based on payment method
        if payroll.payment_method.code == 'BANK':
            deposit_account = settings.default_bank_account
        elif payroll.payment_method.code == 'MOBILE_MONEY':
            deposit_account = settings.mobile_money_clearing_account
        else:
            deposit_account = settings.default_cash_account
        
        if not deposit_account:
            raise ValueError("No deposit account configured for payroll payment")
        
        # Get or create payroll journal
        journal, _ = Journal.objects.get_or_create(
            journal_type='PAYROLL',
            defaults={'name': 'Payroll Journal', 'description': 'Payroll transactions'}
        )
        
        # Create journal entry
        entry = JournalEntry.objects.create(
            journal=journal,
            entry_date=payroll.payment_date,
            fiscal_period=payroll.fiscal_year.periods.first() if hasattr(payroll, 'fiscal_year') and payroll.fiscal_year else FiscalPeriod.get_current_fiscal_period(),
            reference_number=f"PAY-{payroll.staff.staff_id}-{payroll.period.code if hasattr(payroll.period, 'code') else payroll.period.pk}",
            description=f"Payment disbursement - {payroll.staff.full_name()} - {payroll.period.name if hasattr(payroll.period, 'name') else 'Period'}",
            status='POSTED'
        )
        
        # Debit: Wages Payable (reduce liability)
        JournalTransaction.objects.create(
            journal_entry=entry,
            account=accounts['wages_payable'],
            description=f"Payment to {payroll.staff.full_name()}",
            amount=payroll.net_pay,
            is_debit=True
        )
        
        # Credit: Bank/Cash Account (reduce asset)
        JournalTransaction.objects.create(
            journal_entry=entry,
            account=deposit_account,
            description=f"Payroll payment - {payroll.staff.full_name()}",
            amount=payroll.net_pay,
            is_debit=False  # Credit
        )
        
        logger.info(
            f"Created payment disbursement entry {entry.entry_number} for "
            f"{payroll.staff.full_name()}"
        )
        
        return entry
    
    @staticmethod
    @transaction.atomic
    def create_statutory_payment_entry(deduction_type, total_amount, payment_date, reference_number):
        """
        Create journal entry when paying statutory deductions to authorities.
        (e.g., paying PAYE to tax authority, NSSF to social security)
        
        Journal Entry:
        Debit:  Payroll Tax Payable / NSSF Payable   [Amount]
        Credit: Bank Account                                   [Amount]
        
        Args:
            deduction_type: Type of statutory payment ('TAX', 'SOCIAL_SECURITY', 'PENSION')
            total_amount: Total amount being paid
            payment_date: Date of payment
            reference_number: Payment reference
            
        Returns:
            JournalEntry instance
        """
        settings = FinancialSettings.get_instance()
        accounts = settings.get_payroll_accounts()
        
        # Determine liability account
        liability_mapping = {
            'TAX': accounts['payroll_tax_payable'],
            'SOCIAL_SECURITY': accounts['social_security_payable'],
            'PENSION': accounts['pension_payable'],
        }
        
        liability_account = liability_mapping.get(deduction_type)
        if not liability_account:
            raise ValueError(f"No liability account configured for {deduction_type}")
        
        # Get or create payroll journal
        journal, _ = Journal.objects.get_or_create(
            journal_type='PAYROLL',
            defaults={'name': 'Payroll Journal', 'description': 'Payroll transactions'}
        )
        
        # Create journal entry
        entry = JournalEntry.objects.create(
            journal=journal,
            entry_date=payment_date,
            fiscal_period=FiscalPeriod.get_current_fiscal_period(),
            reference_number=reference_number,
            description=f"Statutory payment - {deduction_type} - {reference_number}",
            status='POSTED'
        )
        
        # Debit: Liability Account (reduce liability)
        JournalTransaction.objects.create(
            journal_entry=entry,
            account=liability_account,
            description=f"Payment of {deduction_type}",
            amount=total_amount,
            is_debit=True
        )
        
        # Credit: Bank Account
        JournalTransaction.objects.create(
            journal_entry=entry,
            account=settings.default_bank_account,
            description=f"Statutory payment - {deduction_type}",
            amount=total_amount,
            is_debit=False  # Credit
        )
        
        logger.info(f"Created statutory payment entry {entry.entry_number} for {deduction_type}")
        
        return entry


# =============================================================================
# PAYROLL PROCESSING SERVICE (ORCHESTRATOR)
# =============================================================================

class PayrollProcessingService:
    """Complete payroll processing workflow"""
    
    @staticmethod
    @transaction.atomic
    def process_payroll(payroll, user=None):
        """
        Complete payroll processing workflow:
        1. Calculate amounts
        2. Create journal entry
        3. Update status to APPROVED
        
        Args:
            payroll: Payroll instance
            user: User processing payroll
            
        Returns:
            dict: Processing results
        """
        if payroll.status != 'DRAFT':
            raise ValueError("Can only process draft payroll")
        
        # Step 1: Calculate amounts
        calculation_results = PayrollCalculationService.calculate_payroll(payroll)
        
        # Step 2: Approve payroll
        payroll.status = 'APPROVED'
        if user:
            payroll.approved_by_id = str(user.id) if hasattr(user, 'id') else str(user.pk)
            payroll.approved_at = timezone.now()
        payroll.save()
        
        # Step 3: Create journal entry
        journal_entry = PayrollAccountingService.create_payroll_journal_entry(payroll)
        
        logger.info(f"Processed payroll for {payroll.staff.full_name()}")
        
        return {
            'payroll': payroll,
            'calculation': calculation_results,
            'journal_entry': journal_entry,
            'success': True
        }
    
    @staticmethod
    @transaction.atomic
    def pay_payroll(payroll, user=None):
        """
        Mark payroll as paid and create disbursement entry.
        
        Args:
            payroll: Approved Payroll instance
            user: User making payment
            
        Returns:
            dict: Payment results
        """
        if payroll.status != 'APPROVED':
            raise ValueError("Can only pay approved payroll")
        
        # Update status
        payroll.status = 'PAID'
        payroll.save()
        
        # Create payment disbursement entry
        disbursement_entry = PayrollAccountingService.create_payment_disbursement_entry(payroll)
        
        logger.info(f"Paid payroll for {payroll.staff.full_name()}")
        
        return {
            'payroll': payroll,
            'disbursement_entry': disbursement_entry,
            'success': True
        }
    
    @staticmethod
    def bulk_process_payroll(payrolls, user=None):
        """
        Process multiple payrolls at once.
        
        Args:
            payrolls: QuerySet or list of Payroll instances
            user: User processing payroll
            
        Returns:
            dict: Bulk processing results
        """
        results = {
            'processed': [],
            'failed': [],
            'total': len(payrolls)
        }
        
        for payroll in payrolls:
            try:
                result = PayrollProcessingService.process_payroll(payroll, user)
                results['processed'].append(result)
            except Exception as e:
                logger.error(f"Error processing payroll {payroll.pk}: {e}", exc_info=True)
                results['failed'].append({
                    'payroll': payroll,
                    'error': str(e)
                })
        
        return results


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def create_payroll_for_staff(staff, period, **kwargs):
    """
    Create payroll record for a staff member.
    
    Args:
        staff: Staff instance
        period: Period instance
        **kwargs: Additional payroll data
        
    Returns:
        Payroll instance
    """
    # Get active contract
    active_contract = Contract.objects.filter(
        staff=staff,
        status='ACTIVE'
    ).first()
    
    if not active_contract:
        raise ValueError(f"No active contract found for {staff.full_name()}")
    
    # Get payment method
    payment_method = kwargs.get('payment_method')
    if not payment_method:
        # Default to bank transfer
        payment_method, _ = PaymentMethod.objects.get_or_create(
            code='BANK',
            defaults={'name': 'Bank Transfer', 'is_active': True}
        )
    
    # Calculate monthly salary
    monthly_salary = calculate_monthly_salary(active_contract)
    
    # Create payroll
    payroll = Payroll.objects.create(
        staff=staff,
        period=period,
        payment_date=kwargs.get('payment_date', period.end_date if hasattr(period, 'end_date') else timezone.now().date()),
        basic_salary=monthly_salary,
        payment_method=payment_method,
        bank_account=staff.bank_account_number,
        status='DRAFT'
    )
    
    logger.info(f"Created payroll for {staff.full_name()} - {period.name if hasattr(period, 'name') else 'Period'}")
    
    return payroll


def process_and_pay_payroll(payroll, user=None):
    """
    One-step function to process and pay payroll.
    
    Args:
        payroll: Payroll instance
        user: User processing
        
    Returns:
        dict: Combined results
    """
    # Process
    process_results = PayrollProcessingService.process_payroll(payroll, user)
    
    # Pay
    payment_results = PayrollProcessingService.pay_payroll(payroll, user)
    
    return {
        'process_results': process_results,
        'payment_results': payment_results,
        'success': True
    }