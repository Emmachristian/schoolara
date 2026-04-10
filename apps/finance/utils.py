# finance/utils.py

"""
Finance Management Utility Functions

Comprehensive utilities for financial operations including:

**REFERENCE NUMBER GENERATION:**
- Journal entry numbering with year and sequence
- Expense numbering with auto-increment
- Budget code generation with fiscal year

**ACCOUNT BALANCE TRACKING:**
- Real-time balance calculations from transactions
- Automatic balance updates on journal entry posting
- Balance validation and discrepancy detection
- Hierarchical account balance roll-ups
- Fiscal period-specific balance calculations

**VALIDATIONS:**
- Journal entry balance validation (debits = credits)
- Fiscal period status checks (open/closed)
- Transaction integrity validation
- Budget limit enforcement

**REPORTING:**
- Trial balance calculations
- Income statement (P&L) generation
- Balance sheet generation
- Account activity reports
- Budget variance analysis

**PAYMENT OPERATIONS:**
- Payment reversal handling
- Refund processing
- Payment allocation

**DATA INTEGRITY:**
- Journal entry posting workflow
- Account balance reconciliation
- Audit trail generation

**TIMEZONE HANDLING:**
All date/time operations use core.utils timezone functions to ensure
consistency with school's operational timezone.
"""

from django.db import transaction, models
from django.db.models import Max, Sum, Q, Count, F
from django.utils import timezone
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import datetime, date, timedelta
import logging

# Import timezone utilities from core
from core.utils import (
    get_school_today,
    get_school_current_time,
    get_school_timezone,
    localize_datetime,
    get_active_fiscal_period,
    get_active_fiscal_year,
    format_money,
    calculate_percentage
)

logger = logging.getLogger(__name__)


# =============================================================================
# REFERENCE NUMBER GENERATION
# =============================================================================

def generate_journal_entry_number(journal=None):
    """
    Generate unique journal entry number.
    Format: JE-YYYY-NNNNN or JE-JOURNAL_CODE-YYYY-NNNNN
    
    Args:
        journal: Journal instance (optional, for journal-specific numbering)
        
    Returns:
        str: Unique journal entry number
        
    Example:
        >>> journal = Journal.objects.get(journal_type='GENERAL')
        >>> number = generate_journal_entry_number(journal)
        >>> print(number)
        JE-2025-00001
    """
    from finance.models import JournalEntry
    
    current_year = get_school_today().year
    
    if journal and hasattr(journal, 'code'):
        prefix = f"JE-{journal.code}-{current_year}-"
    else:
        prefix = f"JE-{current_year}-"
    
    with transaction.atomic():
        queryset = JournalEntry.objects.filter(
            entry_number__startswith=prefix
        ).select_for_update()
        
        result = queryset.aggregate(max_number=Max('entry_number'))
        
        if result['max_number']:
            try:
                last_number = int(result['max_number'].split('-')[-1])
                new_number = last_number + 1
            except (ValueError, IndexError):
                new_number = queryset.count() + 1
        else:
            new_number = 1
        
        formatted_number = f"{new_number:05d}"
        
        return f"{prefix}{formatted_number}"


def generate_expense_number():
    """
    Generate unique expense number.
    Format: EXP-YYYY-NNNNN
    
    Returns:
        str: Unique expense number
        
    Example:
        >>> number = generate_expense_number()
        >>> print(number)
        EXP-2025-00042
    """
    from finance.models import Expense
    
    current_year = get_school_today().year
    prefix = f"EXP-{current_year}-"
    
    with transaction.atomic():
        queryset = Expense.objects.filter(
            expense_number__startswith=prefix
        ).select_for_update()
        
        result = queryset.aggregate(max_number=Max('expense_number'))
        
        if result['max_number']:
            try:
                last_number = int(result['max_number'].split('-')[-1])
                new_number = last_number + 1
            except (ValueError, IndexError):
                new_number = queryset.count() + 1
        else:
            new_number = 1
        
        formatted_number = f"{new_number:05d}"
        
        return f"{prefix}{formatted_number}"
    
def generate_payment_reference_number():
    """
    Generate unique payment reference number.
    Format: PAY-YYYY-NNNNN

    Called by payment_pre_save signal when the user does not supply a
    reference number (e.g. cash payments where the field is hidden).

    Uses select_for_update() + Max() — same pattern as generate_expense_number()
    — to prevent duplicate numbers under concurrent requests.

    Returns:
        str: Unique payment reference number e.g. 'PAY-2026-00001'

    Example:
        >>> ref = generate_payment_reference_number()
        >>> print(ref)
        PAY-2026-00001
    """
    from finance.models import ExpensePayment

    current_year = get_school_today().year
    prefix = f"PAY-{current_year}-"

    with transaction.atomic():
        queryset = ExpensePayment.objects.filter(
            reference_number__startswith=prefix
        ).select_for_update()

        result = queryset.aggregate(max_ref=Max('reference_number'))

        if result['max_ref']:
            try:
                last_number = int(result['max_ref'].split('-')[-1])
                new_number  = last_number + 1
            except (ValueError, IndexError):
                new_number = queryset.count() + 1
        else:
            new_number = 1

        return f"{prefix}{new_number:05d}"


def generate_budget_code(fiscal_year, department=None):
    """
    Generate unique budget code.
    Format: BDG-YYYY or BDG-YYYY-DEPT
    
    Args:
        fiscal_year: FiscalYear instance
        department: Department code (optional)
        
    Returns:
        str: Unique budget code
        
    Example:
        >>> fiscal_year = FiscalYear.objects.get(year=2025)
        >>> code = generate_budget_code(fiscal_year, 'ADMIN')
        >>> print(code)
        BDG-2025-ADMIN
    """
    from finance.models import Budget
    
    year = fiscal_year.start_date.year
    
    if department:
        base_code = f"BDG-{year}-{department}"
    else:
        base_code = f"BDG-{year}"
    
    # Check if code exists, append number if needed
    code = base_code
    counter = 1
    
    while Budget.objects.filter(name__icontains=code).exists():
        code = f"{base_code}-{counter:02d}"
        counter += 1
    
    return code


# =============================================================================
# ACCOUNT BALANCE CALCULATIONS - ENHANCED VERSION
# =============================================================================

def calculate_account_balance(account, as_of_date=None, fiscal_period=None, start_date=None, end_date=None):
    """
    Calculate the current balance for an account based on all posted transactions.
    
    This is the DEFINITIVE balance calculation - it sums all journal transactions
    and applies the correct accounting rules based on the account's normal balance.
    
    **IMPORTANT**: Uses school timezone for all date comparisons via get_school_today()
    
    **Accounting Rules Applied:**
    - Assets & Expenses (DEBIT accounts): Balance = Debits - Credits
    - Liabilities, Equity & Revenue (CREDIT accounts): Balance = Credits - Debits
    
    Args:
        account: Account model instance
        as_of_date: Optional date to calculate balance as of (uses school timezone)
        fiscal_period: Optional FiscalPeriod to limit calculation
        start_date: Optional start date for date range calculation
        end_date: Optional end date for date range calculation
    
    Returns:
        Decimal: Current account balance
    
    Example:
        >>> account = Account.objects.get(account_number='1100')
        >>> balance = calculate_account_balance(account)
        >>> print(f"Student Receivables: {format_money(balance)}")
        Student Receivables: UGX 129,210,000.00
        
        >>> # Balance as of specific date
        >>> from core.utils import get_school_today
        >>> from datetime import timedelta
        >>> last_month = get_school_today() - timedelta(days=30)
        >>> balance = calculate_account_balance(account, as_of_date=last_month)
        
        >>> # Balance for specific fiscal period
        >>> period = FiscalPeriod.objects.get(name='Term 1 - 2025')
        >>> balance = calculate_account_balance(account, fiscal_period=period)
    """
    from finance.models import JournalTransaction, JournalEntry
    
    # Build query for transactions
    query = Q(
        account=account,
        journal_entry__status='POSTED'  # Only count posted entries
    )
    
    # Filter by date if provided (using school timezone)
    if as_of_date:
        query &= Q(journal_entry__entry_date__lte=as_of_date)
    
    # Filter by date range if both provided
    if start_date and end_date:
        query &= Q(journal_entry__entry_date__gte=start_date)
        query &= Q(journal_entry__entry_date__lte=end_date)
    elif start_date:
        query &= Q(journal_entry__entry_date__gte=start_date)
    elif end_date:
        query &= Q(journal_entry__entry_date__lte=end_date)
    
    # Filter by fiscal period if provided
    if fiscal_period:
        query &= Q(journal_entry__fiscal_period=fiscal_period)
    
    # Get all transactions for this account
    transactions = JournalTransaction.objects.filter(query)
    
    # Calculate total debits and credits
    totals = transactions.aggregate(
        total_debits=Sum('amount', filter=Q(is_debit=True)),
        total_credits=Sum('amount', filter=Q(is_debit=False))
    )
    
    total_debits = totals['total_debits'] or Decimal('0.00')
    total_credits = totals['total_credits'] or Decimal('0.00')
    
    # Calculate balance based on account's normal balance
    # Get normal balance from account type
    normal_balance = account.account_type.normal_balance
    
    if normal_balance == 'DEBIT':
        # Assets, Expenses: Debit increases, Credit decreases
        balance = total_debits - total_credits
    else:
        # Liabilities, Equity, Revenue: Credit increases, Debit decreases
        balance = total_credits - total_debits
    
    # Add opening balance if exists
    if account.opening_balance:
        balance += account.opening_balance
    
    return balance


def calculate_account_balance_breakdown(account, as_of_date=None):
    """
    Calculate account balance with detailed breakdown.
    
    Provides comprehensive information about an account's balance including
    opening balance, debits, credits, net change, and final balance.
    
    Args:
        account: Account model instance
        as_of_date: Optional date to calculate balance as of (uses school timezone)
    
    Returns:
        dict: Detailed balance breakdown
            {
                'account': account,
                'account_number': str,
                'account_name': str,
                'opening_balance': Decimal,
                'total_debits': Decimal,
                'total_credits': Decimal,
                'net_change': Decimal,
                'current_balance': Decimal,
                'transaction_count': int,
                'normal_balance': str ('DEBIT' or 'CREDIT'),
                'as_of_date': date or None
            }
    
    Example:
        >>> account = Account.objects.get(account_number='1100')
        >>> breakdown = calculate_account_balance_breakdown(account)
        >>> print(f"Account: {breakdown['account_number']} - {breakdown['account_name']}")
        >>> print(f"Opening Balance: {format_money(breakdown['opening_balance'])}")
        >>> print(f"Total Debits: {format_money(breakdown['total_debits'])}")
        >>> print(f"Total Credits: {format_money(breakdown['total_credits'])}")
        >>> print(f"Current Balance: {format_money(breakdown['current_balance'])}")
        >>> print(f"Transactions: {breakdown['transaction_count']}")
    """
    from finance.models import JournalTransaction
    
    # Build query
    query = Q(
        account=account,
        journal_entry__status='POSTED'
    )
    
    if as_of_date:
        query &= Q(journal_entry__entry_date__lte=as_of_date)
    
    # Get transaction totals
    transactions = JournalTransaction.objects.filter(query)
    
    totals = transactions.aggregate(
        total_debits=Sum('amount', filter=Q(is_debit=True)),
        total_credits=Sum('amount', filter=Q(is_debit=False)),
        transaction_count=Count('id')
    )
    
    total_debits = totals['total_debits'] or Decimal('0.00')
    total_credits = totals['total_credits'] or Decimal('0.00')
    transaction_count = totals['transaction_count'] or 0
    
    # Get normal balance
    normal_balance = account.account_type.normal_balance
    
    # Calculate net change and balance
    if normal_balance == 'DEBIT':
        net_change = total_debits - total_credits
    else:
        net_change = total_credits - total_debits
    
    opening_balance = account.opening_balance or Decimal('0.00')
    current_balance = opening_balance + net_change
    
    return {
        'account': account,
        'account_number': account.account_number,
        'account_name': account.name,
        'opening_balance': opening_balance,
        'total_debits': total_debits,
        'total_credits': total_credits,
        'net_change': net_change,
        'current_balance': current_balance,
        'transaction_count': transaction_count,
        'normal_balance': normal_balance,
        'as_of_date': as_of_date
    }


def update_account_balance(account):
    """
    Recalculate account balance from all non-reversed posted transactions.
    
    IMPORTANT: Excludes transactions from REVERSED journal entries.
    """
    from django.db.models import Q, Sum, Case, When, DecimalField
    from finance.models import JournalTransaction
    
    old_balance = account.current_balance
    
    # Get all transactions for this account from POSTED entries only
    # EXCLUDE transactions from REVERSED entries ⭐ KEY CHANGE
    transactions = JournalTransaction.objects.filter(
        account=account,
        journal_entry__status='POSTED'  # Only POSTED, not REVERSED
    )
    
    # Calculate total debits
    total_debits = transactions.filter(
        is_debit=True
    ).aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0.00')
    
    # Calculate total credits
    total_credits = transactions.filter(
        is_debit=False
    ).aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0.00')
    
    # Calculate new balance based on account type
    account_type = account.account_type.account_type
    
    if account_type in ['ASSET', 'EXPENSE']:
        # Assets and Expenses: Debit increases, Credit decreases
        new_balance = account.opening_balance + total_debits - total_credits
    else:
        # Liabilities, Equity, Revenue: Credit increases, Debit decreases
        new_balance = account.opening_balance + total_credits - total_debits
    
    # Update and save
    account.current_balance = new_balance
    account.save(update_fields=['current_balance', 'updated_at'])
    
    logger.debug(
        f"Account {account.account_number} balance updated: "
        f"{old_balance:,.2f} → {new_balance:,.2f}"
    )
    
    return old_balance, new_balance


@transaction.atomic
def update_journal_entry_accounts(journal_entry):
    from finance.models import Account

    # Evaluate to a concrete list immediately — avoids lazy queryset length bugs
    account_ids = list(
        journal_entry.transactions.values_list('account_id', flat=True).distinct()
    )

    if not account_ids:
        raise ValueError(
            f"Journal entry {journal_entry.entry_number} has no transactions"
        )

    accounts = Account.objects.filter(id__in=account_ids)
    found_ids = set(accounts.values_list('id', flat=True))
    missing_ids = set(account_ids) - found_ids

    if missing_ids:  # only raise if accounts are genuinely missing
        raise Account.DoesNotExist(
            f"Accounts not found: {missing_ids}"
        )

    results = {}

    for account in accounts:
        old_balance, new_balance = update_account_balance(account)
        results[account.account_number] = {
            'account':     account,
            'old_balance': old_balance,
            'new_balance': new_balance,
            'change':      new_balance - old_balance,
        }

    logger.info(
        f"Updated {len(results)} accounts for journal entry "
        f"{journal_entry.entry_number}: "
        f"{', '.join(f'{k}={format_money(v[chr(99)+chr(104)+chr(97)+chr(110)+chr(103)+chr(101)])}'for k,v in results.items())}"
    )

    return results


@transaction.atomic
def recalculate_all_account_balances(account_type=None, verbose=True):
    """
    Recalculate balances for all accounts (or specific account type).
    
    This is useful for:
    - Initial data migration
    - Fixing balance discrepancies
    - Periodic reconciliation
    - After bulk journal entry imports
    
    **WARNING**: This can be slow for large datasets. Use with caution in production.
    
    Args:
        account_type: Optional AccountType to limit recalculation
        verbose: Whether to log progress (default: True)
    
    Returns:
        dict: Summary of recalculation
            {
                'total_accounts': int,
                'updated_count': int,
                'error_count': int,
                'total_change': Decimal,
                'changes': list of dicts with account details
            }
    
    Example:
        >>> # Recalculate all accounts
        >>> summary = recalculate_all_account_balances()
        >>> print(f"Updated {summary['updated_count']} of {summary['total_accounts']} accounts")
        >>> 
        >>> # Recalculate only asset accounts
        >>> asset_type = AccountType.objects.get(account_type='ASSET')
        >>> summary = recalculate_all_account_balances(account_type=asset_type)
    """
    from finance.models import Account
    
    # Build query
    query = Q(is_active=True)
    if account_type:
        query &= Q(account_type=account_type)
    
    accounts = Account.objects.filter(query)
    total_accounts = accounts.count()
    
    if verbose:
        logger.info(f"Recalculating balances for {total_accounts} accounts...")
    
    updated_count = 0
    error_count = 0
    total_change = Decimal('0.00')
    
    changes = []
    
    for i, account in enumerate(accounts, 1):
        try:
            old_balance = account.current_balance
            new_balance = calculate_account_balance(account)
            change = new_balance - old_balance
            
            if change != 0:
                account.current_balance = new_balance
                account.save(update_fields=['current_balance', 'updated_at'])
                updated_count += 1
                total_change += abs(change)
                
                changes.append({
                    'account_number': account.account_number,
                    'account_name': account.name,
                    'old_balance': old_balance,
                    'new_balance': new_balance,
                    'change': change
                })
                
                if verbose and change != 0:
                    logger.info(
                        f"  [{i}/{total_accounts}] {account.account_number}: "
                        f"{old_balance:,.2f} → {new_balance:,.2f} "
                        f"(Δ {change:+,.2f})"
                    )
        
        except Exception as e:
            error_count += 1
            logger.error(
                f"Error recalculating balance for {account.account_number}: {e}",
                exc_info=True
            )
    
    summary = {
        'total_accounts': total_accounts,
        'updated_count': updated_count,
        'error_count': error_count,
        'total_change': total_change,
        'changes': changes
    }
    
    if verbose:
        logger.info(
            f"Recalculation complete: {updated_count}/{total_accounts} accounts updated, "
            f"{error_count} errors, total change: {total_change:,.2f}"
        )
    
    return summary


# =============================================================================
# LEGACY ACCOUNT BALANCE FUNCTION (for backwards compatibility)
# =============================================================================

def calculate_normal_balance(account, debit_total, credit_total):
    """
    Calculate account balance based on normal balance type.
    
    **LEGACY FUNCTION** - kept for backwards compatibility.
    New code should use calculate_account_balance() instead.
    
    Normal balances:
    - ASSET: Debit
    - LIABILITY: Credit
    - EQUITY: Credit
    - REVENUE: Credit
    - EXPENSE: Debit
    
    Args:
        account: Account instance
        debit_total: Total debits
        credit_total: Total credits
        
    Returns:
        Decimal: Account balance (positive or negative)
    """
    normal_balance = account.account_type.normal_balance
    
    if normal_balance == 'DEBIT':
        # Assets, Expenses: Debit balance accounts
        balance = debit_total - credit_total
    else:
        # Liabilities, Equity, Revenue: Credit balance accounts
        balance = credit_total - debit_total
    
    return balance


# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================

def validate_journal_entry_balance(journal_entry):
    """
    Validate that debits equal credits for a journal entry.
    
    Args:
        journal_entry: JournalEntry model instance
    
    Returns:
        tuple: (is_balanced: bool, total_debits: Decimal, total_credits: Decimal)
    
    Raises:
        ValueError: If entry is not balanced
    
    Example:
        >>> entry = JournalEntry.objects.get(entry_number='JE-2025-00001')
        >>> try:
        >>>     is_balanced, debits, credits = validate_journal_entry_balance(entry)
        >>>     print(f"Entry is balanced: Debits={format_money(debits)}, Credits={format_money(credits)}")
        >>> except ValueError as e:
        >>>     print(f"Entry not balanced: {e}")
    """
    from finance.models import JournalTransaction
    
    transactions = journal_entry.transactions.all()
    
    totals = transactions.aggregate(
        total_debits=Sum('amount', filter=Q(is_debit=True)),
        total_credits=Sum('amount', filter=Q(is_debit=False))
    )
    
    total_debits = totals['total_debits'] or Decimal('0.00')
    total_credits = totals['total_credits'] or Decimal('0.00')
    
    is_balanced = total_debits == total_credits
    
    if not is_balanced:
        difference = total_debits - total_credits
        raise ValueError(
            f"Journal entry {journal_entry.entry_number} is not balanced. "
            f"Debits: {total_debits:,.2f}, Credits: {total_credits:,.2f}, "
            f"Difference: {difference:,.2f}"
        )
    
    return (is_balanced, total_debits, total_credits)


def validate_all_journal_entries(fiscal_period=None):
    """
    Validate that all posted journal entries are balanced.
    
    Args:
        fiscal_period: Optional FiscalPeriod to limit validation
    
    Returns:
        dict: Validation results
            {
                'total_entries': int,
                'valid_count': int,
                'invalid_count': int,
                'invalid_entries': list of error dicts
            }
    
    Example:
        >>> results = validate_all_journal_entries()
        >>> if results['invalid_count'] > 0:
        >>>     print(f"Found {results['invalid_count']} invalid entries:")
        >>>     for entry in results['invalid_entries']:
        >>>         print(f"  - {entry['entry_number']}: {entry['error']}")
    """
    from finance.models import JournalEntry
    
    query = Q(status='POSTED')
    if fiscal_period:
        query &= Q(fiscal_period=fiscal_period)
    
    entries = JournalEntry.objects.filter(query)
    total_entries = entries.count()
    
    logger.info(f"Validating {total_entries} journal entries...")
    
    valid_count = 0
    invalid_entries = []
    
    for entry in entries:
        try:
            validate_journal_entry_balance(entry)
            valid_count += 1
        except ValueError as e:
            invalid_entries.append({
                'entry_number': entry.entry_number,
                'error': str(e)
            })
            logger.warning(f"Invalid entry: {e}")
    
    result = {
        'total_entries': total_entries,
        'valid_count': valid_count,
        'invalid_count': len(invalid_entries),
        'invalid_entries': invalid_entries
    }
    
    logger.info(
        f"Validation complete: {valid_count}/{total_entries} entries valid, "
        f"{len(invalid_entries)} invalid"
    )
    
    return result


def find_account_discrepancies(threshold=Decimal('0.01')):
    """
    Find accounts where stored balance doesn't match calculated balance.
    
    This helps identify data integrity issues where the stored balance
    has become out of sync with actual transaction totals.
    
    Args:
        threshold: Maximum acceptable difference (default: 0.01)
    
    Returns:
        list: Accounts with discrepancies
            [{
                'account_number': str,
                'account_name': str,
                'stored_balance': Decimal,
                'calculated_balance': Decimal,
                'difference': Decimal
            }, ...]
    
    Example:
        >>> discrepancies = find_account_discrepancies()
        >>> if discrepancies:
        >>>     print(f"Found {len(discrepancies)} accounts with balance issues:")
        >>>     for d in discrepancies:
        >>>         print(f"  {d['account_number']}: Off by {format_money(d['difference'])}")
        >>> else:
        >>>     print("✓ All account balances are correct!")
    """
    from finance.models import Account
    
    discrepancies = []
    
    accounts = Account.objects.filter(is_active=True)
    
    logger.info(f"Checking {accounts.count()} accounts for discrepancies...")
    
    for account in accounts:
        stored_balance = account.current_balance
        calculated_balance = calculate_account_balance(account)
        difference = abs(stored_balance - calculated_balance)
        
        if difference > threshold:
            discrepancies.append({
                'account_number': account.account_number,
                'account_name': account.name,
                'stored_balance': stored_balance,
                'calculated_balance': calculated_balance,
                'difference': difference
            })
            
            logger.warning(
                f"Discrepancy found: {account.account_number} - "
                f"Stored: {stored_balance:,.2f}, "
                f"Calculated: {calculated_balance:,.2f}, "
                f"Difference: {difference:,.2f}"
            )
    
    logger.info(f"Found {len(discrepancies)} discrepancies")
    
    return discrepancies


def validate_fiscal_period(fiscal_period):
    """
    Validate if fiscal period is open and can accept transactions.
    
    Args:
        fiscal_period: FiscalPeriod instance
        
    Returns:
        dict: {
            'valid': bool,
            'errors': list of str,
            'warnings': list of str
        }
    
    Example:
        >>> from core.models import FiscalPeriod
        >>> period = FiscalPeriod.objects.get(name='Term 1 - 2025')
        >>> validation = validate_fiscal_period(period)
        >>> if not validation['valid']:
        >>>     print(f"Cannot post to this period: {', '.join(validation['errors'])}")
    """
    errors = []
    warnings = []
    
    # Check if period is closed
    if fiscal_period.is_closed:
        errors.append(f"Fiscal period {fiscal_period.name} is closed")
    
    # Check if period is in the future (using school timezone)
    today = get_school_today()
    
    if fiscal_period.start_date > today:
        warnings.append(f"Fiscal period {fiscal_period.name} has not started yet")
    
    # Check if period has ended
    if fiscal_period.end_date < today:
        warnings.append(f"Fiscal period {fiscal_period.name} has ended")
    
    valid = len(errors) == 0
    
    return {
        'valid': valid,
        'errors': errors,
        'warnings': warnings
    }


def get_current_fiscal_period(raise_error=False):
    """
    Get the current active fiscal period.
    
    **USES SCHOOL TIMEZONE** via get_school_today() for determining "current"
    
    Args:
        raise_error: Whether to raise exception if no period found
        
    Returns:
        FiscalPeriod instance or None
        
    Raises:
        ValueError: If raise_error=True and no period found
    
    Example:
        >>> period = get_current_fiscal_period()
        >>> if period:
        >>>     print(f"Current period: {period.name}")
        >>> else:
        >>>     print("No active fiscal period!")
    """
    # Use core.utils function which handles school timezone
    period = get_active_fiscal_period()
    
    if not period and raise_error:
        raise ValueError("No active fiscal period found")
    
    return period


def is_date_in_open_period(date_to_check):
    """
    Check if a date falls within an open fiscal period.
    
    Args:
        date_to_check: Date to check
        
    Returns:
        bool: True if date is in an open period
    
    Example:
        >>> from core.utils import get_school_today
        >>> today = get_school_today()
        >>> if is_date_in_open_period(today):
        >>>     # OK to post transactions
        >>>     pass
    """
    from core.models import FiscalPeriod
    
    try:
        period = FiscalPeriod.objects.get(
            start_date__lte=date_to_check,
            end_date__gte=date_to_check,
            is_closed=False
        )
        return True
    except FiscalPeriod.DoesNotExist:
        return False


def validate_journal_entry(journal_entry):
    """
    Validate journal entry for accounting rules.
    
    Performs comprehensive validation including:
    - Entry has transactions
    - Debits equal credits
    - No negative or zero amounts
    - Fiscal period is open
    - Entry date is in valid period
    
    Args:
        journal_entry: JournalEntry instance
        
    Returns:
        dict: {
            'valid': bool,
            'errors': list of str,
            'warnings': list of str,
            'balanced': bool,
            'debit_total': Decimal,
            'credit_total': Decimal
        }
    
    Example:
        >>> entry = JournalEntry.objects.get(pk=1)
        >>> validation = validate_journal_entry(entry)
        >>> if not validation['valid']:
        >>>     print("Entry has errors:")
        >>>     for error in validation['errors']:
        >>>         print(f"  - {error}")
    """
    errors = []
    warnings = []
    
    # Get transactions
    transactions = journal_entry.transactions.all()
    
    # Check if entry has transactions
    if not transactions.exists():
        errors.append("Journal entry has no transactions")
        return {
            'valid': False,
            'errors': errors,
            'warnings': warnings,
            'balanced': False,
            'debit_total': Decimal('0.00'),
            'credit_total': Decimal('0.00')
        }
    
    # Calculate debits and credits
    debit_total = transactions.filter(is_debit=True).aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0.00')
    
    credit_total = transactions.filter(is_debit=False).aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0.00')
    
    # Check if balanced
    balanced = abs(debit_total - credit_total) < Decimal('0.01')  # Allow 1 cent tolerance
    
    if not balanced:
        errors.append(
            f"Journal entry is not balanced. "
            f"Debits: {debit_total}, Credits: {credit_total}, "
            f"Difference: {abs(debit_total - credit_total)}"
        )
    
    # Check for negative amounts
    if transactions.filter(amount__lt=0).exists():
        errors.append("Journal entry contains negative amounts")
    
    # Check for zero amounts
    if transactions.filter(amount=0).exists():
        warnings.append("Journal entry contains zero-amount transactions")
    
    # Check fiscal period
    if journal_entry.fiscal_period:
        period_validation = validate_fiscal_period(journal_entry.fiscal_period)
        errors.extend(period_validation['errors'])
        warnings.extend(period_validation['warnings'])
    else:
        warnings.append("Journal entry has no fiscal period assigned")
    
    # Check if entry date is in open period
    if not is_date_in_open_period(journal_entry.entry_date):
        errors.append(
            f"Entry date {journal_entry.entry_date} is not in an open fiscal period"
        )
    
    valid = len(errors) == 0 and balanced
    
    return {
        'valid': valid,
        'errors': errors,
        'warnings': warnings,
        'balanced': balanced,
        'debit_total': debit_total,
        'credit_total': credit_total
    }


def validate_journal_transaction(transaction):
    """
    Validate individual journal transaction.
    
    Args:
        transaction: JournalTransaction instance
        
    Returns:
        dict: {
            'valid': bool,
            'errors': list of str,
            'warnings': list of str
        }
    
    Example:
        >>> txn = JournalTransaction.objects.get(pk=1)
        >>> validation = validate_journal_transaction(txn)
        >>> if not validation['valid']:
        >>>     print(f"Transaction error: {', '.join(validation['errors'])}")
    """
    errors = []
    warnings = []
    
    # Check amount is positive
    if transaction.amount <= 0:
        errors.append("Transaction amount must be positive")
    
    # Check account is active
    if not transaction.account.is_active:
        errors.append(f"Account {transaction.account.account_number} is inactive")
    
    # Check account allows transactions
    if transaction.account.is_header:
        errors.append(
            f"Account {transaction.account.account_number} is a header account "
            f"and cannot have transactions"
        )
    
    valid = len(errors) == 0
    
    return {
        'valid': valid,
        'errors': errors,
        'warnings': warnings
    }


# =============================================================================
# ACCOUNT HIERARCHY UTILITIES
# =============================================================================

def calculate_account_with_children_balance(account, as_of_date=None):
    """
    Calculate balance including all child accounts (for header accounts).
    
    Args:
        account: Account model instance
        as_of_date: Optional date to calculate balance as of
    
    Returns:
        dict: Balance breakdown including children
    
    Example:
        >>> # Get balance for "Current Assets" including all child accounts
        >>> account = Account.objects.get(account_number='1000')
        >>> breakdown = calculate_account_with_children_balance(account)
        >>> print(f"Own balance: {format_money(breakdown['own_balance'])}")
        >>> print(f"Total with children: {format_money(breakdown['total_with_children'])}")
    """
    from finance.models import Account
    
    # Get this account's balance
    own_balance = calculate_account_balance(account, as_of_date)
    
    # Get all descendant accounts recursively
    def get_all_descendants(acc):
        descendants = []
        children = Account.objects.filter(parent_account=acc, is_active=True)
        for child in children:
            descendants.append(child)
            descendants.extend(get_all_descendants(child))
        return descendants
    
    descendants = get_all_descendants(account)
    
    # Calculate total including descendants
    total_with_children = own_balance
    child_balances = []
    
    for child in descendants:
        child_balance = calculate_account_balance(child, as_of_date)
        total_with_children += child_balance
        child_balances.append({
            'account_number': child.account_number,
            'account_name': child.name,
            'balance': child_balance
        })
    
    return {
        'account': account,
        'own_balance': own_balance,
        'child_count': len(descendants),
        'child_balances': child_balances,
        'total_with_children': total_with_children,
        'as_of_date': as_of_date
    }


def get_account_balance_tree(account, start_date=None, end_date=None):
    """
    Get account balance including all child accounts in hierarchical structure.
    
    Args:
        account: Account instance
        start_date: Start date (optional)
        end_date: End date (optional)
        
    Returns:
        dict: Hierarchical account balance data
    """
    from finance.models import Account, JournalTransaction
    
    # Build query for this account's transactions
    query = Q(account=account, journal_entry__status='POSTED')
    
    if start_date:
        query &= Q(journal_entry__entry_date__gte=start_date)
    
    if end_date:
        query &= Q(journal_entry__entry_date__lte=end_date)
    
    # Get transaction totals
    transactions = JournalTransaction.objects.filter(query)
    
    totals = transactions.aggregate(
        debit_total=Sum('amount', filter=Q(is_debit=True)),
        credit_total=Sum('amount', filter=Q(is_debit=False)),
        transaction_count=Count('id')
    )
    
    debit_total = totals['debit_total'] or Decimal('0.00')
    credit_total = totals['credit_total'] or Decimal('0.00')
    transaction_count = totals['transaction_count'] or 0
    
    # Calculate this account's balance
    own_balance = calculate_account_balance(account, start_date=start_date, end_date=end_date)
    
    # Get child accounts
    children = []
    total_balance = own_balance
    
    for child in Account.objects.filter(parent_account=account, is_active=True):
        child_data = get_account_balance_tree(child, start_date, end_date)
        children.append(child_data)
        total_balance += child_data['balance']
    
    return {
        'account': account,
        'own_balance': own_balance,
        'balance': total_balance,
        'debit_total': debit_total,
        'credit_total': credit_total,
        'transaction_count': transaction_count,
        'children': children
    }


def get_account_hierarchy(root_account=None):
    """
    Get complete account hierarchy as nested structure.
    
    Args:
        root_account: Root account (None for all top-level accounts)
        
    Returns:
        list: Nested account structure
    """
    from finance.models import Account
    
    if root_account:
        accounts = Account.objects.filter(parent_account=root_account, is_active=True)
    else:
        accounts = Account.objects.filter(parent_account__isnull=True, is_active=True)
    
    hierarchy = []
    
    for account in accounts.order_by('account_number'):
        account_data = {
            'account': account,
            'children': get_account_hierarchy(account)
        }
        hierarchy.append(account_data)
    
    return hierarchy


def get_all_child_accounts(account, include_self=False):
    """
    Get all descendant accounts recursively.
    
    Args:
        account: Parent account
        include_self: Whether to include the parent account
        
    Returns:
        list: All child accounts
    """
    from finance.models import Account
    
    children = []
    
    if include_self:
        children.append(account)
    
    direct_children = Account.objects.filter(parent_account=account, is_active=True)
    
    for child in direct_children:
        children.append(child)
        children.extend(get_all_child_accounts(child, include_self=False))
    
    return children


def get_account_path(account):
    """
    Get full path from root to account.
    
    Args:
        account: Account instance
        
    Returns:
        list: Path of accounts from root to this account
    """
    path = [account]
    current = account
    
    while current.parent_account:
        current = current.parent_account
        path.insert(0, current)
    
    return path


def format_account_path(account, separator=' > '):
    """
    Format account path as string.
    
    Args:
        account: Account instance
        separator: Path separator
        
    Returns:
        str: Formatted path
    """
    path = get_account_path(account)
    return separator.join([acc.name for acc in path])


# =============================================================================
# REPORTING CALCULATIONS
# =============================================================================

def calculate_trial_balance(start_date=None, end_date=None):
    """
    Calculate trial balance for all accounts.
    
    **USES SCHOOL TIMEZONE** for date comparisons
    
    Args:
        start_date: Start date (optional)
        end_date: End date (optional, defaults to get_school_today())
        
    Returns:
        dict: Trial balance data
    """
    from finance.models import Account
    
    # Default end_date to today in school timezone
    if not end_date:
        end_date = get_school_today()
    
    accounts_data = []
    total_debits = Decimal('0.00')
    total_credits = Decimal('0.00')
    
    # Get all leaf accounts (non-header)
    accounts = Account.objects.filter(is_active=True, is_header=False)
    
    for account in accounts:
        balance = calculate_account_balance(
            account,
            start_date=start_date,
            end_date=end_date
        )
        
        # Get transaction totals for display
        breakdown = calculate_account_balance_breakdown(account, as_of_date=end_date)
        
        # Determine debit or credit balance based on account type
        normal_balance = account.account_type.normal_balance
        
        if balance >= 0:
            if normal_balance == 'DEBIT':
                debit_balance = balance
                credit_balance = Decimal('0.00')
            else:
                debit_balance = Decimal('0.00')
                credit_balance = balance
        else:
            # Negative balance (contra account)
            if normal_balance == 'DEBIT':
                debit_balance = Decimal('0.00')
                credit_balance = abs(balance)
            else:
                debit_balance = abs(balance)
                credit_balance = Decimal('0.00')
        
        if debit_balance != 0 or credit_balance != 0:
            accounts_data.append({
                'account': account,
                'debit_balance': debit_balance,
                'credit_balance': credit_balance,
                'debit_total': breakdown['total_debits'],
                'credit_total': breakdown['total_credits']
            })
            
            total_debits += debit_balance
            total_credits += credit_balance
    
    balanced = abs(total_debits - total_credits) < Decimal('0.01')
    
    return {
        'accounts': accounts_data,
        'total_debits': total_debits,
        'total_credits': total_credits,
        'balanced': balanced,
        'start_date': start_date,
        'end_date': end_date
    }


def calculate_income_statement(start_date, end_date):
    """
    Calculate income statement (profit & loss).
    
    **USES SCHOOL TIMEZONE** for date comparisons
    
    Args:
        start_date: Period start date
        end_date: Period end date
        
    Returns:
        dict: Income statement data
    """
    from finance.models import Account
    
    # Get revenue accounts
    revenue_accounts = Account.objects.filter(
        account_type__account_type='REVENUE',
        is_active=True,
        is_header=False
    )
    
    revenue_data = []
    total_revenue = Decimal('0.00')
    
    for account in revenue_accounts:
        balance = calculate_account_balance(
            account,
            start_date=start_date,
            end_date=end_date
        )
        if balance != 0:
            revenue_data.append({
                'account': account,
                'amount': balance
            })
            total_revenue += balance
    
    # Get expense accounts
    expense_accounts = Account.objects.filter(
        account_type__account_type='EXPENSE',
        is_active=True,
        is_header=False
    )
    
    expense_data = []
    total_expenses = Decimal('0.00')
    
    for account in expense_accounts:
        balance = calculate_account_balance(
            account,
            start_date=start_date,
            end_date=end_date
        )
        if balance != 0:
            expense_data.append({
                'account': account,
                'amount': balance
            })
            total_expenses += balance
    
    # Calculate net income
    net_income = total_revenue - total_expenses
    
    return {
        'revenue': total_revenue,
        'expenses': total_expenses,
        'net_income': net_income,
        'revenue_accounts': revenue_data,
        'expense_accounts': expense_data,
        'start_date': start_date,
        'end_date': end_date
    }


def calculate_balance_sheet(as_of_date=None):
    """
    Calculate balance sheet.
    
    **USES SCHOOL TIMEZONE** - defaults to get_school_today()
    
    Args:
        as_of_date: Date to calculate balance sheet (default: today in school timezone)
        
    Returns:
        dict: Balance sheet data
    """
    from finance.models import Account
    
    if not as_of_date:
        as_of_date = get_school_today()
    
    # Assets
    asset_accounts = Account.objects.filter(
        account_type__account_type='ASSET',
        is_active=True,
        is_header=False
    )
    
    asset_data = []
    total_assets = Decimal('0.00')
    
    for account in asset_accounts:
        balance = calculate_account_balance(account, as_of_date=as_of_date)
        if balance != 0:
            asset_data.append({
                'account': account,
                'amount': balance
            })
            total_assets += balance
    
    # Liabilities
    liability_accounts = Account.objects.filter(
        account_type__account_type='LIABILITY',
        is_active=True,
        is_header=False
    )
    
    liability_data = []
    total_liabilities = Decimal('0.00')
    
    for account in liability_accounts:
        balance = calculate_account_balance(account, as_of_date=as_of_date)
        if balance != 0:
            liability_data.append({
                'account': account,
                'amount': balance
            })
            total_liabilities += balance
    
    # Equity
    equity_accounts = Account.objects.filter(
        account_type__account_type='EQUITY',
        is_active=True,
        is_header=False
    )
    
    equity_data = []
    total_equity = Decimal('0.00')
    
    for account in equity_accounts:
        balance = calculate_account_balance(account, as_of_date=as_of_date)
        if balance != 0:
            equity_data.append({
                'account': account,
                'amount': balance
            })
            total_equity += balance
    
    # Check if balanced (Assets = Liabilities + Equity)
    balanced = abs(total_assets - (total_liabilities + total_equity)) < Decimal('0.01')
    
    return {
        'assets': total_assets,
        'liabilities': total_liabilities,
        'equity': total_equity,
        'balanced': balanced,
        'asset_accounts': asset_data,
        'liability_accounts': liability_data,
        'equity_accounts': equity_data,
        'as_of_date': as_of_date
    }


def get_account_balance_report(account_type=None, as_of_date=None):
    """
    Generate a balance report for accounts.
    
    Args:
        account_type: Optional AccountType to filter by
        as_of_date: Optional date to calculate balances as of (uses school timezone)
        
    Returns:
        dict: Balance report data
    """
    from finance.models import Account
    
    if not as_of_date:
        as_of_date = get_school_today()
    
    query = Q(is_active=True, is_header=False)  # Exclude header accounts
    if account_type:
        query &= Q(account_type=account_type)
    
    accounts = Account.objects.filter(query).select_related('account_type')
    
    report_data = []
    total_balance = Decimal('0.00')
    
    for account in accounts:
        breakdown = calculate_account_balance_breakdown(account, as_of_date)
        report_data.append(breakdown)
        total_balance += breakdown['current_balance']
    
    return {
        'as_of_date': as_of_date,
        'account_type': account_type.name if account_type else 'All',
        'total_accounts': len(report_data),
        'total_balance': total_balance,
        'accounts': report_data
    }


# =============================================================================
# BUDGET CALCULATIONS
# =============================================================================

def calculate_budget_variance(budget_amount, actual_amount):
    """
    Calculate budget variance.
    
    Args:
        budget_amount: Budgeted amount
        actual_amount: Actual amount spent/earned
        
    Returns:
        dict: Budget variance analysis
    """
    budget_amount = Decimal(str(budget_amount or 0))
    actual_amount = Decimal(str(actual_amount or 0))
    
    variance = budget_amount - actual_amount
    
    if budget_amount > 0:
        variance_percentage = calculate_percentage(variance, budget_amount)
    else:
        variance_percentage = Decimal('0.00')
    
    # Determine status
    if abs(variance) < Decimal('0.01'):
        status = 'ON_BUDGET'
    elif variance > 0:
        status = 'UNDER_BUDGET'
    else:
        status = 'OVER_BUDGET'
    
    return {
        'budget_amount': budget_amount,
        'actual_amount': actual_amount,
        'variance': variance,
        'variance_percentage': variance_percentage,
        'status': status
    }


# =============================================================================
# PAYMENT REVERSAL UTILITIES
# =============================================================================

@transaction.atomic
def reverse_expense_payment(expense_payment, user, reason):
    """
    Reverse an expense payment (internal correction).
    
    **USES SCHOOL TIMEZONE** for reversal timestamps via get_school_current_time()
    
    Args:
        expense_payment: ExpensePayment instance
        user: User performing reversal
        reason: Reason for reversal
    
    Returns:
        tuple: (success: bool, message: str, journal_entry: JournalEntry or None)
    """
    if expense_payment.reversed:
        return False, "Payment already reversed", None
    
    try:
        from finance.models import JournalEntry, JournalTransaction, Journal
        from core.models import FiscalPeriod
        
        # 1. Mark as reversed (using school timezone)
        expense_payment.reversed = True
        expense_payment.reversed_on = get_school_current_time()
        expense_payment.reversed_by_id = str(user.id)
        expense_payment.reversal_reason = reason
        
        # 2. Update expense status
        expense = expense_payment.expense
        # Recalculate total paid (excluding reversed payments)
        total_paid = sum(
            p.amount for p in expense.payments.all()
            if not p.reversed
        )
        
        if total_paid == 0:
            expense.status = 'APPROVED'  # Back to approved, not paid
        elif total_paid < expense.total_amount:
            expense.status = 'APPROVED'  # Partially unpaid
        
        expense.save()
        
        # 3. Create reversal journal entry (using school timezone for dates)
        fiscal_period = get_active_fiscal_period()
        
        general_journal = Journal.objects.filter(
            journal_type='GENERAL',
            is_active=True
        ).first()
        
        if not general_journal:
            return False, "No active journal found", None
        
        reversal_entry = JournalEntry.objects.create(
            journal=general_journal,
            entry_date=get_school_today(),
            fiscal_period=fiscal_period,
            reference_number=expense_payment.reference_number,
            description=f"REVERSAL: Expense Payment {expense_payment.reference_number} - {reason}",
            status='POSTED'
        )
        
        # Get accounts
        payable_account = expense.get_payable_account()
        payment_account = expense_payment.account
        
        # REVERSAL entries (opposite of payment):
        # DR: Accounts Payable (restore liability)
        JournalTransaction.objects.create(
            journal_entry=reversal_entry,
            account=payable_account,
            amount=expense_payment.amount,
            is_debit=True,
            description="Reversal: Payable restored"
        )
        
        # CR: Cash/Bank (reverse outflow)
        JournalTransaction.objects.create(
            journal_entry=reversal_entry,
            account=payment_account,
            amount=expense_payment.amount,
            is_debit=False,
            description=f"Reversal: Payment reversed"
        )
        
        # Update balances (this will be handled by signals, but do it explicitly for safety)
        update_journal_entry_accounts(reversal_entry)
        
        expense_payment.reversal_journal_entry = reversal_entry
        expense_payment.save()
        
        logger.info(f"Expense payment reversed: {expense_payment.reference_number}")
        
        return True, f"Payment reversed. Journal: {reversal_entry.entry_number}", reversal_entry
    
    except Exception as e:
        logger.error(f"Error reversing expense payment: {e}", exc_info=True)
        return False, f"Error: {str(e)}", None


# =============================================================================
# QUICK FIX FUNCTION (For Immediate Issues)
# =============================================================================

def fix_student_receivables_balance():
    """
    Quick fix to recalculate and update Student Receivables balance.
    
    This is a one-time fix for the issue where the balance shows 0.00
    despite having transactions.
    
    Returns:
        dict: Fix results
    """
    from finance.models import Account
    
    try:
        # Find Student Receivables account
        receivables_account = Account.objects.get(account_number='1100')
        
        logger.info("=" * 60)
        logger.info("FIXING STUDENT RECEIVABLES BALANCE")
        logger.info("=" * 60)
        
        # Get detailed breakdown
        breakdown = calculate_account_balance_breakdown(receivables_account)
        
        logger.info(f"Account: {breakdown['account_number']} - {breakdown['account_name']}")
        logger.info(f"Current stored balance: {receivables_account.current_balance:,.2f}")
        logger.info(f"Transaction count: {breakdown['transaction_count']}")
        logger.info(f"Total debits: {breakdown['total_debits']:,.2f}")
        logger.info(f"Total credits: {breakdown['total_credits']:,.2f}")
        logger.info(f"Calculated balance: {breakdown['current_balance']:,.2f}")
        
        # Update the balance
        old_balance, new_balance = update_account_balance(receivables_account)
        
        logger.info(f"✓ Updated: {old_balance:,.2f} → {new_balance:,.2f}")
        logger.info("=" * 60)
        
        return {
            'success': True,
            'account': receivables_account,
            'old_balance': old_balance,
            'new_balance': new_balance,
            'breakdown': breakdown
        }
    
    except Account.DoesNotExist:
        logger.error("Student Receivables account (1100) not found!")
        return {
            'success': False,
            'error': 'Account 1100 not found'
        }
    except Exception as e:
        logger.error(f"Error fixing balance: {e}", exc_info=True)
        return {
            'success': False,
            'error': str(e)
        }