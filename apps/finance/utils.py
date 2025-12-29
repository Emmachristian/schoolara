# finance/utils.py

"""
Finance Management Utility Functions

Provides helper functions for:
- Reference number generation (journal entries, expenses, budgets)
- Account balance calculations
- Financial period validations
- Journal entry validations
- Reporting calculations
- Account tree traversal
"""

from django.db import transaction
from django.db.models import Max, Sum, Q
from django.utils import timezone
from decimal import Decimal
import logging

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
    """
    from finance.models import JournalEntry
    
    current_year = timezone.now().year
    
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
    """
    from finance.models import Expense
    
    current_year = timezone.now().year
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


def generate_budget_code(fiscal_year, department=None):
    """
    Generate unique budget code.
    Format: BDG-YYYY or BDG-YYYY-DEPT
    
    Args:
        fiscal_year: FiscalYear instance
        department: Department code (optional)
        
    Returns:
        str: Unique budget code
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
    
    while Budget.objects.filter(budget_code=code).exists():
        code = f"{base_code}-{counter:02d}"
        counter += 1
    
    return code


# =============================================================================
# ACCOUNT BALANCE CALCULATIONS
# =============================================================================

def calculate_account_balance(account, start_date=None, end_date=None):
    """
    Calculate account balance for a date range.
    
    Args:
        account: Account instance
        start_date: Start date (optional, from beginning if None)
        end_date: End date (optional, up to now if None)
        
    Returns:
        dict: {
            'debit_total': Decimal,
            'credit_total': Decimal,
            'balance': Decimal,
            'transaction_count': int
        }
    """
    from finance.models import JournalTransaction
    
    # Build query
    query = Q(account=account, journal_entry__status='POSTED')
    
    if start_date:
        query &= Q(journal_entry__entry_date__gte=start_date)
    
    if end_date:
        query &= Q(journal_entry__entry_date__lte=end_date)
    
    # Get transactions
    transactions = JournalTransaction.objects.filter(query)
    
    # Calculate totals
    debit_total = transactions.filter(is_debit=True).aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0.00')
    
    credit_total = transactions.filter(is_debit=False).aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0.00')
    
    # Calculate balance based on account type
    balance = calculate_normal_balance(account, debit_total, credit_total)
    
    return {
        'debit_total': debit_total,
        'credit_total': credit_total,
        'balance': balance,
        'transaction_count': transactions.count()
    }


def calculate_normal_balance(account, debit_total, credit_total):
    """
    Calculate account balance based on normal balance type.
    
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
    account_type = account.account_type.code
    
    if account_type in ['ASSET', 'EXPENSE']:
        # Debit balance accounts
        balance = debit_total - credit_total
    else:  # LIABILITY, EQUITY, REVENUE
        # Credit balance accounts
        balance = credit_total - debit_total
    
    return balance


def get_account_balance_tree(account, start_date=None, end_date=None):
    """
    Get account balance including all child accounts.
    
    Args:
        account: Account instance
        start_date: Start date (optional)
        end_date: End date (optional)
        
    Returns:
        dict: {
            'account': Account instance,
            'balance': Decimal,
            'children': [nested dicts for child accounts]
        }
    """
    from finance.models import Account
    
    # Calculate this account's balance
    balance_data = calculate_account_balance(account, start_date, end_date)
    
    # Get child accounts
    children = []
    for child in Account.objects.filter(parent_account=account, is_active=True):
        child_data = get_account_balance_tree(child, start_date, end_date)
        children.append(child_data)
    
    # Calculate total including children
    total_balance = balance_data['balance']
    for child in children:
        total_balance += child['balance']
    
    return {
        'account': account,
        'own_balance': balance_data['balance'],
        'balance': total_balance,
        'debit_total': balance_data['debit_total'],
        'credit_total': balance_data['credit_total'],
        'transaction_count': balance_data['transaction_count'],
        'children': children
    }


# =============================================================================
# FINANCIAL PERIOD VALIDATIONS
# =============================================================================

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
    """
    errors = []
    warnings = []
    
    # Check if period is closed
    if fiscal_period.is_closed:
        errors.append(f"Fiscal period {fiscal_period.period_name} is closed")
    
    # Check if period is in the future
    if fiscal_period.start_date > timezone.now().date():
        warnings.append(f"Fiscal period {fiscal_period.period_name} has not started yet")
    
    # Check if period has ended
    if fiscal_period.end_date < timezone.now().date():
        warnings.append(f"Fiscal period {fiscal_period.period_name} has ended")
    
    valid = len(errors) == 0
    
    return {
        'valid': valid,
        'errors': errors,
        'warnings': warnings
    }


def get_current_fiscal_period(raise_error=False):
    """
    Get the current active fiscal period.
    
    Args:
        raise_error: Whether to raise exception if no period found
        
    Returns:
        FiscalPeriod instance or None
        
    Raises:
        ValueError: If raise_error=True and no period found
    """
    from core.models import FiscalPeriod
    
    period = FiscalPeriod.get_current_fiscal_period()
    
    if not period and raise_error:
        raise ValueError("No active fiscal period found")
    
    return period


def is_date_in_open_period(date):
    """
    Check if a date falls within an open fiscal period.
    
    Args:
        date: Date to check
        
    Returns:
        bool: True if date is in an open period
    """
    from core.models import FiscalPeriod
    
    try:
        period = FiscalPeriod.objects.get(
            start_date__lte=date,
            end_date__gte=date,
            is_closed=False
        )
        return True
    except FiscalPeriod.DoesNotExist:
        return False


# =============================================================================
# JOURNAL ENTRY VALIDATIONS
# =============================================================================

def validate_journal_entry(journal_entry):
    """
    Validate journal entry for accounting rules.
    
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
    """
    errors = []
    warnings = []
    
    # Check amount is positive
    if transaction.amount <= 0:
        errors.append("Transaction amount must be positive")
    
    # Check account is active
    if not transaction.account.is_active:
        errors.append(f"Account {transaction.account.code} is inactive")
    
    # Check account allows transactions
    if transaction.account.is_header:
        errors.append(f"Account {transaction.account.code} is a header account and cannot have transactions")
    
    valid = len(errors) == 0
    
    return {
        'valid': valid,
        'errors': errors,
        'warnings': warnings
    }


# =============================================================================
# REPORTING CALCULATIONS
# =============================================================================

def calculate_trial_balance(start_date=None, end_date=None):
    """
    Calculate trial balance for all accounts.
    
    Args:
        start_date: Start date (optional)
        end_date: End date (optional)
        
    Returns:
        dict: {
            'accounts': list of account data,
            'total_debits': Decimal,
            'total_credits': Decimal,
            'balanced': bool
        }
    """
    from finance.models import Account
    
    accounts_data = []
    total_debits = Decimal('0.00')
    total_credits = Decimal('0.00')
    
    # Get all leaf accounts (non-header)
    accounts = Account.objects.filter(is_active=True, is_header=False)
    
    for account in accounts:
        balance_data = calculate_account_balance(account, start_date, end_date)
        
        # Determine debit or credit balance
        if balance_data['balance'] >= 0:
            if account.account_type.code in ['ASSET', 'EXPENSE']:
                debit_balance = balance_data['balance']
                credit_balance = Decimal('0.00')
            else:
                debit_balance = Decimal('0.00')
                credit_balance = balance_data['balance']
        else:
            if account.account_type.code in ['ASSET', 'EXPENSE']:
                debit_balance = Decimal('0.00')
                credit_balance = abs(balance_data['balance'])
            else:
                debit_balance = abs(balance_data['balance'])
                credit_balance = Decimal('0.00')
        
        if debit_balance != 0 or credit_balance != 0:
            accounts_data.append({
                'account': account,
                'debit_balance': debit_balance,
                'credit_balance': credit_balance,
                'debit_total': balance_data['debit_total'],
                'credit_total': balance_data['credit_total']
            })
            
            total_debits += debit_balance
            total_credits += credit_balance
    
    balanced = abs(total_debits - total_credits) < Decimal('0.01')
    
    return {
        'accounts': accounts_data,
        'total_debits': total_debits,
        'total_credits': total_credits,
        'balanced': balanced
    }


def calculate_income_statement(start_date, end_date):
    """
    Calculate income statement (profit & loss).
    
    Args:
        start_date: Period start date
        end_date: Period end date
        
    Returns:
        dict: {
            'revenue': Decimal,
            'expenses': Decimal,
            'net_income': Decimal,
            'revenue_accounts': list,
            'expense_accounts': list
        }
    """
    from finance.models import Account
    
    # Get revenue accounts
    revenue_accounts = Account.objects.filter(
        account_type__code='REVENUE',
        is_active=True,
        is_header=False
    )
    
    revenue_data = []
    total_revenue = Decimal('0.00')
    
    for account in revenue_accounts:
        balance_data = calculate_account_balance(account, start_date, end_date)
        if balance_data['balance'] != 0:
            revenue_data.append({
                'account': account,
                'amount': balance_data['balance']
            })
            total_revenue += balance_data['balance']
    
    # Get expense accounts
    expense_accounts = Account.objects.filter(
        account_type__code='EXPENSE',
        is_active=True,
        is_header=False
    )
    
    expense_data = []
    total_expenses = Decimal('0.00')
    
    for account in expense_accounts:
        balance_data = calculate_account_balance(account, start_date, end_date)
        if balance_data['balance'] != 0:
            expense_data.append({
                'account': account,
                'amount': balance_data['balance']
            })
            total_expenses += balance_data['balance']
    
    # Calculate net income
    net_income = total_revenue - total_expenses
    
    return {
        'revenue': total_revenue,
        'expenses': total_expenses,
        'net_income': net_income,
        'revenue_accounts': revenue_data,
        'expense_accounts': expense_data
    }


def calculate_balance_sheet(as_of_date=None):
    """
    Calculate balance sheet.
    
    Args:
        as_of_date: Date to calculate balance sheet (default: today)
        
    Returns:
        dict: {
            'assets': Decimal,
            'liabilities': Decimal,
            'equity': Decimal,
            'balanced': bool,
            'asset_accounts': list,
            'liability_accounts': list,
            'equity_accounts': list
        }
    """
    from finance.models import Account
    
    if not as_of_date:
        as_of_date = timezone.now().date()
    
    # Assets
    asset_accounts = Account.objects.filter(
        account_type__code='ASSET',
        is_active=True,
        is_header=False
    )
    
    asset_data = []
    total_assets = Decimal('0.00')
    
    for account in asset_accounts:
        balance_data = calculate_account_balance(account, end_date=as_of_date)
        if balance_data['balance'] != 0:
            asset_data.append({
                'account': account,
                'amount': balance_data['balance']
            })
            total_assets += balance_data['balance']
    
    # Liabilities
    liability_accounts = Account.objects.filter(
        account_type__code='LIABILITY',
        is_active=True,
        is_header=False
    )
    
    liability_data = []
    total_liabilities = Decimal('0.00')
    
    for account in liability_accounts:
        balance_data = calculate_account_balance(account, end_date=as_of_date)
        if balance_data['balance'] != 0:
            liability_data.append({
                'account': account,
                'amount': balance_data['balance']
            })
            total_liabilities += balance_data['balance']
    
    # Equity
    equity_accounts = Account.objects.filter(
        account_type__code='EQUITY',
        is_active=True,
        is_header=False
    )
    
    equity_data = []
    total_equity = Decimal('0.00')
    
    for account in equity_accounts:
        balance_data = calculate_account_balance(account, end_date=as_of_date)
        if balance_data['balance'] != 0:
            equity_data.append({
                'account': account,
                'amount': balance_data['balance']
            })
            total_equity += balance_data['balance']
    
    # Check if balanced (Assets = Liabilities + Equity)
    balanced = abs(total_assets - (total_liabilities + total_equity)) < Decimal('0.01')
    
    return {
        'assets': total_assets,
        'liabilities': total_liabilities,
        'equity': total_equity,
        'balanced': balanced,
        'asset_accounts': asset_data,
        'liability_accounts': liability_data,
        'equity_accounts': equity_data
    }


# =============================================================================
# ACCOUNT TREE TRAVERSAL
# =============================================================================

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
    
    for account in accounts.order_by('code'):
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
# BUDGET CALCULATIONS
# =============================================================================

def calculate_budget_variance(budget, actual_amount):
    """
    Calculate budget variance.
    
    Args:
        budget: Budget instance
        actual_amount: Actual amount spent/earned
        
    Returns:
        dict: {
            'budget_amount': Decimal,
            'actual_amount': Decimal,
            'variance': Decimal,
            'variance_percentage': Decimal,
            'status': str ('UNDER_BUDGET', 'ON_BUDGET', 'OVER_BUDGET')
        }
    """
    budget_amount = budget.allocated_amount
    variance = budget_amount - actual_amount
    
    if budget_amount > 0:
        variance_percentage = (variance / budget_amount) * 100
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
# EXPORT UTILITIES
# =============================================================================

def export_trial_balance_to_csv(start_date=None, end_date=None):
    """
    Export trial balance to CSV format.
    
    Returns:
        str: CSV data as string
    """
    import csv
    from io import StringIO
    
    output = StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow([
        'Account Code',
        'Account Name',
        'Account Type',
        'Debit Balance',
        'Credit Balance'
    ])
    
    # Get trial balance
    trial_balance = calculate_trial_balance(start_date, end_date)
    
    # Data
    for account_data in trial_balance['accounts']:
        account = account_data['account']
        writer.writerow([
            account.code,
            account.name,
            account.account_type.name,
            account_data['debit_balance'],
            account_data['credit_balance']
        ])
    
    # Totals
    writer.writerow([])
    writer.writerow([
        'TOTAL',
        '',
        '',
        trial_balance['total_debits'],
        trial_balance['total_credits']
    ])
    
    return output.getvalue()