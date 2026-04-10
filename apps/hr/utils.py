# hr/utils.py

"""
HR Utility Functions

Pure utility functions for HR operations:
- Century-safe year handling
- Staff ID format generation (logic only, not creation)
- Salary calculations
- Date calculations
- Staff information queries
- Payroll number generation
- Payroll payment reference generation

NO DATABASE WRITES - Only calculations, formatting, and simple queries.
For complex workflows with DB writes, see hr/services.py
"""

from django.utils import timezone
from django.db.models import F
from datetime import date, timedelta
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# CENTURY-SAFE YEAR UTILITIES
# =============================================================================

def get_century_safe_year_suffix(year):
    """
    Convert year to century-safe format.

    Args:
        year (int): Full year (e.g., 2024, 2125)

    Returns:
        str: Century-safe year suffix

    Examples:
        2024 → "24"
        2099 → "99"
        2100 → "A00"
        2125 → "A25"
        2200 → "B00"
        2350 → "C50"
    """
    if year < 2100:
        return f"{year % 100:02d}"
    else:
        century = year // 100
        century_offset = century - 20
        century_letter = chr(ord('A') + century_offset - 1)
        year_part = year % 100
        return f"{century_letter}{year_part:02d}"


def parse_staff_year_from_id(staff_id):
    """
    Parse the actual year from a century-safe staff ID.

    Args:
        staff_id (str): Staff ID (e.g., "24/SCH/TCH-001", "B25/SCH/ADM-001")

    Returns:
        int: The actual year (e.g., 2024, 2225) or None if parsing fails

    Examples:
        "24/SCH/TCH-001" → 2024
        "A25/SCH/TCH-001" → 2125
        "B00/SCH/ADM-001" → 2200
    """
    try:
        year_part = staff_id.split('/')[0]

        if year_part.isdigit():
            year_suffix = int(year_part)
            if 0 <= year_suffix <= 99:
                return 2000 + year_suffix
        else:
            century_letter = year_part[0]
            year_suffix = int(year_part[1:])
            century_offset = ord(century_letter.upper()) - ord('A') + 1
            century = 20 + century_offset
            return (century * 100) + year_suffix

    except (ValueError, IndexError):
        pass

    return None


# =============================================================================
# STAFF TYPE CODE UTILITIES
# =============================================================================

def get_staff_type_code(employment_status, is_teaching=False):
    """
    Get staff type code based on employment status and teaching status.
    Pure function - no DB access.

    Args:
        employment_status (str): Employment status code
        is_teaching (bool): Whether staff is a teacher

    Returns:
        str: Staff type code

    Examples:
        ('FT', True) → 'TCH'  # Full-time Teacher
        ('FT', False) → 'ADM'  # Full-time Admin
        ('PT', True) → 'PTT'   # Part-time Teacher
        ('CT', False) → 'CNT'  # Contract Staff
    """
    if is_teaching:
        if employment_status == 'PT':
            return 'PTT'
        return 'TCH'
    else:
        status_codes = {
            'FT': 'ADM',
            'PT': 'PTA',
            'CT': 'CNT',
            'PR': 'PRB',
            'IN': 'INT',
            'VO': 'VOL',
        }
        return status_codes.get(employment_status, 'STF')


def build_staff_id_prefix(year, school_abbrev, dept_code=None, staff_type='ADM'):
    """
    Build staff ID prefix WITHOUT touching database.
    Pure function for prefix construction.

    Args:
        year (int): Joining year
        school_abbrev (str): School abbreviation
        dept_code (str, optional): Department code
        staff_type (str): Staff type code

    Returns:
        str: Prefix like "24/ATEPI/TCH-" or "A25/SCH/MATH/ADM-"

    Examples:
        build_staff_id_prefix(2024, 'SCH', None, 'TCH') → "24/SCH/TCH-"
        build_staff_id_prefix(2024, 'SCH', 'MATH', 'TCH') → "24/SCH/MATH/TCH-"
        build_staff_id_prefix(2125, 'SCH', None, 'ADM') → "A25/SCH/ADM-"
    """
    year_suffix = get_century_safe_year_suffix(year)

    if dept_code:
        return f"{year_suffix}/{school_abbrev}/{dept_code}/{staff_type}-"
    else:
        return f"{year_suffix}/{school_abbrev}/{staff_type}-"


def parse_staff_id_components(staff_id):
    """
    Parse staff ID into components.
    Pure function - no DB access.

    Args:
        staff_id (str): Staff ID (e.g., "24/SCH/MATH/TCH-001")

    Returns:
        dict: Components or None if invalid
        {
            'year': int,
            'school': str,
            'department': str or None,
            'type': str,
            'sequence': int
        }
    """
    try:
        parts = staff_id.split('/')

        if len(parts) == 3:
            year_part, school, type_seq = parts
            type_code, sequence = type_seq.split('-')
            return {
                'year': parse_staff_year_from_id(staff_id),
                'school': school,
                'department': None,
                'type': type_code,
                'sequence': int(sequence)
            }
        elif len(parts) == 4:
            year_part, school, dept, type_seq = parts
            type_code, sequence = type_seq.split('-')
            return {
                'year': parse_staff_year_from_id(staff_id),
                'school': school,
                'department': dept,
                'type': type_code,
                'sequence': int(sequence)
            }
    except (ValueError, IndexError):
        pass

    return None


# =============================================================================
# CONTRACT NUMBER UTILITIES
# =============================================================================

def build_contract_number_prefix(year, type_code='GEN'):
    """
    Build contract number prefix WITHOUT touching database.
    Pure function for prefix construction.

    Args:
        year (int): Contract year
        type_code (str): Contract type code

    Returns:
        str: Prefix like "CONT/2024/GEN/" or "CONT/A125/TEMP/"
    """
    if year < 2100:
        year_str = str(year)
    else:
        century = year // 100
        century_offset = century - 20
        century_letter = chr(ord('A') + century_offset - 1)
        year_str = f"{century_letter}{year}"

    return f"CONT/{year_str}/{type_code}/"


def get_contract_type_code(contract_type_name):
    """
    Get contract type code from contract type name.
    Pure function - no DB access.

    Args:
        contract_type_name (str): Contract type name

    Returns:
        str: 4-letter type code
    """
    return contract_type_name[:4].upper().replace(' ', '')


# =============================================================================
# SIMPLE QUERY HELPERS (Read-Only)
# =============================================================================

def get_expiring_contracts(days=30):
    """
    Get contracts expiring within specified days.
    Simple query helper - read-only.
    """
    from hr.models import Contract

    today = date.today()
    end_date = today + timedelta(days=days)

    return Contract.objects.filter(
        status='ACTIVE',
        end_date__gte=today,
        end_date__lte=end_date
    ).select_related('staff')


def get_active_contracts():
    """Get all active contracts. Read-only."""
    from hr.models import Contract
    return Contract.objects.filter(status='ACTIVE')


def get_probation_staff():
    """Get all staff currently on probation. Read-only."""
    from hr.models import Staff
    return Staff.objects.filter(employment_status='PR', is_active=True)


def get_staff_on_probation_ending_soon(days=30):
    """Get staff whose probation period is ending soon."""
    from hr.models import Contract

    today = date.today()
    end_date = today + timedelta(days=days)

    contracts = Contract.objects.filter(
        status='ACTIVE',
        probation_period_months__gt=0
    ).select_related('staff')

    probation_ending = []
    for contract in contracts:
        probation_end = contract.start_date + timedelta(days=contract.probation_period_months * 30)
        if today <= probation_end <= end_date:
            probation_ending.append(contract.staff)

    return probation_ending


def get_available_teachers():
    """Get teachers who have capacity for more classes. Read-only."""
    from hr.models import Teacher

    return Teacher.objects.filter(
        staff__is_active=True
    ).exclude(
        current_teaching_load__gte=F('max_hours_per_week')
    )


def get_staff_current_contract(staff):
    """Get staff member's current active contract. Read-only."""
    from hr.models import Contract

    return Contract.objects.filter(
        staff=staff,
        status='ACTIVE'
    ).first()


# =============================================================================
# DATE & AGE CALCULATIONS
# =============================================================================

def get_days_until_birthday(staff):
    """Calculate days until staff member's next birthday. Pure calculation."""
    if not staff.date_of_birth:
        return None

    today = date.today()
    next_birthday = date(today.year, staff.date_of_birth.month, staff.date_of_birth.day)

    if next_birthday < today:
        next_birthday = date(today.year + 1, staff.date_of_birth.month, staff.date_of_birth.day)

    return (next_birthday - today).days


def is_birthday_today(staff):
    """Check if today is staff member's birthday. Pure check."""
    if not staff.date_of_birth:
        return False

    today = date.today()
    return (staff.date_of_birth.month == today.month and
            staff.date_of_birth.day == today.day)


def get_employment_duration(staff):
    """Get how long staff member has been employed (in days). Pure calculation."""
    if not staff.date_of_joining:
        return None

    end_date = staff.date_of_leaving if staff.date_of_leaving else date.today()
    return (end_date - staff.date_of_joining).days


def get_years_of_service(staff):
    """Get years of service. Pure calculation."""
    days = get_employment_duration(staff)
    if days:
        return round(days / 365.25, 1)
    return 0


def get_staff_age(staff):
    """Calculate staff member's current age. Pure calculation."""
    if not staff.date_of_birth:
        return None

    today = date.today()
    age = today.year - staff.date_of_birth.year - (
        (today.month, today.day) < (staff.date_of_birth.month, staff.date_of_birth.day)
    )
    return age


def is_staff_due_for_retirement(staff, retirement_age=60):
    """Check if staff is approaching retirement age. Pure calculation."""
    age = get_staff_age(staff)
    if not age:
        return {'is_due': False, 'years_remaining': None, 'retirement_date': None}

    years_remaining = retirement_age - age
    is_due = years_remaining <= 5

    retirement_date = None
    if staff.date_of_birth:
        retirement_date = date(
            staff.date_of_birth.year + retirement_age,
            staff.date_of_birth.month,
            staff.date_of_birth.day
        )

    return {
        'is_due': is_due,
        'years_remaining': years_remaining,
        'retirement_date': retirement_date,
        'current_age': age
    }


# =============================================================================
# SALARY CALCULATIONS
# =============================================================================

def calculate_monthly_salary(contract):
    """Calculate monthly salary from contract based on salary frequency. Pure calculation."""
    basic_salary = contract.basic_salary
    frequency = contract.salary_frequency

    conversions = {
        'MONTHLY': 1,
        'ANNUAL': 1/12,
        'WEEKLY': 52/12,
        'DAILY': 22,
        'HOURLY': contract.working_hours_per_week * 52 / 12
    }

    multiplier = conversions.get(frequency, 1)
    return basic_salary * Decimal(str(multiplier))


def calculate_annual_salary(contract):
    """Calculate annual salary from contract. Pure calculation."""
    monthly = calculate_monthly_salary(contract)
    return monthly * 12


def calculate_daily_rate(contract):
    """Calculate daily rate from contract. Pure calculation."""
    monthly = calculate_monthly_salary(contract)
    return monthly / 22


def calculate_hourly_rate(contract):
    """Calculate hourly rate from contract. Pure calculation."""
    monthly = calculate_monthly_salary(contract)
    hours_per_month = contract.working_hours_per_week * 52 / 12
    return monthly / Decimal(str(hours_per_month))


# =============================================================================
# TEACHER-SPECIFIC UTILITIES
# =============================================================================

def get_teacher_workload(teacher):
    """Calculate teacher's current workload percentage. Pure calculation."""
    if teacher.max_hours_per_week == 0:
        return 0
    return round((teacher.current_teaching_load / teacher.max_hours_per_week) * 100, 1)


def is_teacher_overloaded(teacher):
    """Check if teacher is overloaded. Pure check."""
    return teacher.current_teaching_load > teacher.max_hours_per_week


def calculate_available_teaching_hours(teacher):
    """Calculate how many hours teacher has available. Pure calculation."""
    return teacher.max_hours_per_week - teacher.current_teaching_load


# =============================================================================
# VALIDATION HELPERS
# =============================================================================

def validate_staff_data(staff_data):
    """Validate staff data before creation. Pure validation - no DB writes."""
    errors = []
    warnings = []

    required = ['first_name', 'last_name', 'date_of_joining']
    for field in required:
        if field not in staff_data or not staff_data[field]:
            errors.append(f"{field.replace('_', ' ').title()} is required")

    if 'date_of_birth' in staff_data and staff_data['date_of_birth']:
        if staff_data['date_of_birth'] > date.today():
            errors.append("Birth date cannot be in the future")

        age = (date.today() - staff_data['date_of_birth']).days / 365.25
        if age < 18:
            warnings.append("Staff member is under 18 years old")

    if 'date_of_joining' in staff_data and staff_data['date_of_joining']:
        if staff_data['date_of_joining'] > date.today():
            errors.append("Joining date cannot be in the future")

    if 'personal_email' in staff_data and staff_data['personal_email']:
        if '@' not in staff_data['personal_email']:
            errors.append("Invalid email address")

    return {'valid': len(errors) == 0, 'errors': errors, 'warnings': warnings}


def validate_contract_data(contract_data):
    """Validate contract data before creation. Pure validation - no DB writes."""
    errors = []
    warnings = []

    required = ['staff', 'contract_type', 'start_date', 'basic_salary']
    for field in required:
        if field not in contract_data or not contract_data[field]:
            errors.append(f"{field.replace('_', ' ').title()} is required")

    if 'start_date' in contract_data and 'end_date' in contract_data:
        if contract_data['end_date'] and contract_data['end_date'] < contract_data['start_date']:
            errors.append("End date cannot be before start date")

    if 'basic_salary' in contract_data:
        if contract_data['basic_salary'] <= 0:
            errors.append("Basic salary must be positive")

    return {'valid': len(errors) == 0, 'errors': errors, 'warnings': warnings}


# =============================================================================
# PAYROLL NUMBER UTILITIES
# =============================================================================

def _get_century_safe_year_str(year):
    """
    Internal helper — return a year string suitable for payroll/payment numbers.
    Uses full 4-digit year for readability (e.g. 2024, A2125).
    """
    if year < 2100:
        return str(year)
    else:
        century = year // 100
        century_offset = century - 20
        century_letter = chr(ord('A') + century_offset - 1)
        return f"{century_letter}{year}"


def build_payroll_number_prefix(year, month, pay_frequency='MONTHLY'):
    """
    Build payroll number prefix WITHOUT touching database.
    Pure function for prefix construction.

    Args:
        year (int): Payroll year
        month (int): Payroll month (1-12)
        pay_frequency (str): Pay frequency code

    Returns:
        str: Prefix like "PAY/2024/01/" or "PAY/A125/06/W/"

    Examples:
        build_payroll_number_prefix(2024, 1, 'MONTHLY') → "PAY/2024/01/"
        build_payroll_number_prefix(2125, 6, 'WEEKLY')  → "PAY/A125/06/W/"
    """
    year_str = _get_century_safe_year_str(year)

    freq_suffix = ""
    if pay_frequency == 'WEEKLY':
        freq_suffix = "/W"
    elif pay_frequency == 'BIWEEKLY':
        freq_suffix = "/BW"

    return f"PAY/{year_str}/{month:02d}{freq_suffix}/"


def generate_payroll_number(pay_period_start, pay_frequency='MONTHLY'):
    """
    Generate payroll number based on pay period.
    READS from database to get next sequence number.

    Format: PAY/YYYY/MM/NNNN or PAY/AYYY/MM/NNNN (century-safe)
    Examples:
        PAY/2024/01/0001 (January 2024 monthly payroll)
        PAY/A125/06/W0001 (June 2125 weekly payroll)

    Args:
        pay_period_start (date): Start date of pay period
        pay_frequency (str): Pay frequency code

    Returns:
        str: Generated payroll number
    """
    from hr.models import Payroll

    year  = pay_period_start.year
    month = pay_period_start.month

    prefix = build_payroll_number_prefix(year, month, pay_frequency)

    last_payroll = Payroll.objects.filter(
        pay_period_start__year=year,
        pay_period_start__month=month,
        pay_frequency=pay_frequency
    ).order_by('-created_at').first()

    if last_payroll and last_payroll.payroll_number:
        try:
            last_seq = int(last_payroll.payroll_number.split('/')[-1])
            next_seq = last_seq + 1
        except (ValueError, IndexError):
            next_seq = 1
    else:
        next_seq = 1

    return f"{prefix}{next_seq:04d}"


# =============================================================================
# PAYROLL PAYMENT REFERENCE UTILITIES
# =============================================================================

def build_payment_reference_prefix(year, month):
    """
    Build payroll payment reference prefix WITHOUT touching database.
    Pure function for prefix construction.

    Format: PP/YYYY/MM/ or PP/AYYY/MM/ (century-safe)

    The PP prefix distinguishes payment instalments from payroll records
    (PAY prefix) and makes it easy to identify in bank statements and
    journal entries.

    Args:
        year (int): Payment year
        month (int): Payment month (1-12)

    Returns:
        str: Prefix like "PP/2024/01/" or "PP/A125/06/"

    Examples:
        build_payment_reference_prefix(2024, 1)  → "PP/2024/01/"
        build_payment_reference_prefix(2025, 11) → "PP/2025/11/"
        build_payment_reference_prefix(2125, 6)  → "PP/A125/06/"
    """
    year_str = _get_century_safe_year_str(year)
    return f"PP/{year_str}/{month:02d}/"


def generate_payment_reference(payment_date):
    """
    Generate a unique payment reference number for a PayrollPayment instalment.
    READS from database to get next sequence number.

    Format: PP/YYYY/MM/NNNN
    Examples:
        PP/2025/02/0001  — first payment instalment recorded in Feb 2025
        PP/2025/02/0002  — second payment instalment recorded in Feb 2025

    The sequence is a global monthly counter — not per-staff. Two payments
    for different staff members in the same month get consecutive numbers,
    just like payroll numbers. The sequence resets each calendar month.

    Auto-assignment: called from PayrollPayment.save() when payment_reference
    is blank, so users never need to type a reference manually. They can still
    override it with an external bank reference if preferred.

    Args:
        payment_date (date): Date of the payment instalment

    Returns:
        str: Generated payment reference e.g. "PP/2025/02/0001"
    """
    from hr.models import PayrollPayment

    year  = payment_date.year
    month = payment_date.month

    prefix = build_payment_reference_prefix(year, month)

    # Find the last auto-generated reference for this month
    # Only look at references that match the PP/YYYY/MM/ pattern to avoid
    # collisions with manually entered bank references
    last_payment = PayrollPayment.objects.filter(
        payment_date__year=year,
        payment_date__month=month,
        payment_reference__startswith=prefix,
    ).order_by('-created_at').first()

    if last_payment and last_payment.payment_reference:
        try:
            last_seq = int(last_payment.payment_reference.split('/')[-1])
            next_seq = last_seq + 1
        except (ValueError, IndexError):
            next_seq = 1
    else:
        next_seq = 1

    return f"{prefix}{next_seq:04d}"


# =============================================================================
# PAYMENT REVERSAL UTILITIES
# =============================================================================

from django.db import transaction as db_transaction

@db_transaction.atomic
def reverse_payroll(payroll, user, reason, approved_by=None, statutory_notes=''):
    """
    Reverse a staff payroll (complex operation affecting multiple models).

    CRITICAL DIFFERENCES FROM PAYMENT REVERSAL:
    1. Must reverse related records: allowances, deductions, bonuses
    2. May require statutory adjustments (tax/NSSF filings)
    3. Requires higher-level approval if already paid
    4. Cannot reverse if period is closed

    Args:
        payroll: Payroll instance
        user: User initiating reversal
        reason: Detailed reason for reversal
        approved_by: User who approved reversal (required for PAID payrolls)
        statutory_notes: Notes on tax/NSSF adjustments needed

    Returns:
        tuple: (success: bool, message: str, journal_entry: JournalEntry or None)
    """
    if payroll.reversed:
        return False, "Payroll already reversed", None

    can_reverse, msg = payroll.can_be_reversed()
    if not can_reverse:
        return False, msg, None

    if payroll.status == 'PAID' and not approved_by:
        return False, "Finance/HR Director approval required for paid payroll reversal", None

    try:
        from finance.models import JournalEntry, JournalTransaction, Journal
        from core.models import FiscalPeriod

        # ====================================================================
        # STEP 1: Mark payroll as reversed
        # ====================================================================
        payroll.reversed = True
        payroll.reversed_on = timezone.now()
        payroll.reversed_by_id = str(user.id)
        payroll.reversal_reason = reason
        payroll.status = 'REVERSED'

        if approved_by:
            payroll.reversal_approved_by_id = str(approved_by.id)
            payroll.reversal_approved_on = timezone.now()

        if payroll.requires_statutory_adjustments():
            payroll.statutory_reversals_required = True
            payroll.statutory_adjustments_notes = statutory_notes

        # ====================================================================
        # STEP 2: Create reversal journal entry
        # ====================================================================
        fiscal_period = FiscalPeriod.get_current_fiscal_period()

        general_journal = Journal.objects.filter(
            journal_type='PAYROLL',
            is_active=True
        ).first()

        if not general_journal:
            general_journal = Journal.objects.filter(
                journal_type='GENERAL',
                is_active=True
            ).first()

        if not general_journal:
            return False, "No active journal found for reversal", None

        reversal_entry = JournalEntry.objects.create(
            journal=general_journal,
            entry_date=timezone.now().date(),
            fiscal_period=fiscal_period,
            reference_number=f"PAY-{payroll.period.name}-{payroll.staff.employee_id}",
            description=(
                f"REVERSAL: Payroll {payroll.staff.full_name()} - "
                f"{payroll.period.name} - {reason}"
            ),
            status='POSTED'
        )

        # ====================================================================
        # STEP 3: Create reversal journal transactions
        # ====================================================================
        salary_expense = payroll.get_salary_expense_account()
        salary_payable = payroll.get_salary_payable_account()
        cash_account   = payroll.get_cash_account()

        if not all([salary_expense, salary_payable]):
            return False, "Required payroll accounts not configured", None

        if payroll.status in ['APPROVED', 'PROCESSING']:
            JournalTransaction.objects.create(
                journal_entry=reversal_entry,
                account=salary_payable,
                amount=payroll.gross_pay,
                is_debit=True,
                description="Reversal: Salary payable"
            )
            JournalTransaction.objects.create(
                journal_entry=reversal_entry,
                account=salary_expense,
                amount=payroll.gross_pay,
                is_debit=False,
                description="Reversal: Salary expense"
            )
            salary_payable.current_balance -= payroll.gross_pay
            salary_payable.save()
            salary_expense.current_balance -= payroll.gross_pay
            salary_expense.save()

        elif payroll.status == 'PAID':
            if not cash_account:
                return False, "Cash account not configured for paid payroll reversal", None

            JournalTransaction.objects.create(
                journal_entry=reversal_entry,
                account=cash_account,
                amount=payroll.net_pay,
                is_debit=True,
                description="Reversal: Cash recovered from employee"
            )
            JournalTransaction.objects.create(
                journal_entry=reversal_entry,
                account=salary_payable,
                amount=payroll.net_pay,
                is_debit=False,
                description="Reversal: Salary payable restored"
            )

            for deduction in payroll.deductions.filter(
                deduction_type__in=['PAYE', 'SOCIAL_SECURITY', 'LOCAL_TAX']
            ):
                deduction_account = payroll.get_deduction_account(deduction.deduction_type)
                if deduction_account:
                    JournalTransaction.objects.create(
                        journal_entry=reversal_entry,
                        account=deduction_account,
                        amount=deduction.amount,
                        is_debit=True,
                        description=f"Reversal: {deduction.get_deduction_type_display()}"
                    )
                    deduction_account.current_balance -= deduction.amount
                    deduction_account.save()

            cash_account.current_balance += payroll.net_pay
            cash_account.save()
            salary_payable.current_balance += payroll.net_pay
            salary_payable.save()

        payroll.reversal_journal_entry = reversal_entry
        payroll.save()

        logger.info(
            f"Payroll reversed: {payroll.staff.full_name()} - {payroll.period.name} - "
            f"Journal: {reversal_entry.entry_number}"
        )

        # ====================================================================
        # STEP 4: Log statutory warning if needed
        # ====================================================================
        if payroll.statutory_reversals_required:
            logger.warning(
                f"STATUTORY ADJUSTMENT REQUIRED: Payroll {payroll.id} reversal "
                f"affects tax/NSSF filings. Notes: {statutory_notes}"
            )

        return True, f"Payroll reversed. Journal: {reversal_entry.entry_number}", reversal_entry

    except Exception as e:
        logger.error(f"Error reversing payroll: {e}", exc_info=True)
        return False, f"Error: {str(e)}", None