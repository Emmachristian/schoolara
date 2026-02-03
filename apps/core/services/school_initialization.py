# core/services/school_initialization.py

"""
School Initialization Service
==============================

This service handles the complete initialization of a school's financial system.
It creates all necessary accounts, categories, settings, and configurations
based on the school's characteristics (size, type, location).

USAGE:
======
from core.services.school_initialization import initialize_school

# Initialize a school
result = initialize_school(school_instance, user=request.user)

if result['success']:
    print(f"Created {result['created']['accounts']} accounts")
else:
    print(f"Errors: {result['errors']}")

WHAT IT CREATES:
================
1. Account Types (ASSET, LIABILITY, EQUITY, REVENUE, EXPENSE)
2. Chart of Accounts (10-130 accounts based on complexity)
3. Financial Settings (currency, numbering, payment terms)
4. Account Mappings (links accounts to system operations)
5. Fee Categories (tuition, boarding, activities, etc.)
6. Expense Categories (salaries, utilities, supplies, etc.)
7. Journals (General, Fees, Expenses, Cash, Bank, Payroll, Adjustments)
8. Fiscal Year and Periods (current year with 12 monthly periods)
9. Display Groups (for organizing fees on invoices)
10. Payment Methods (Cash, Bank Transfer, Mobile Money, Cards, etc.)
11. Departments (Academic, Administrative, Support, Operational)
12. Designations (Job positions mapped to departments)
13. Units of Measure (for inventory and procurement)
14. Tax Rates (country-specific VAT and withholding tax)

COMPLEXITY LEVELS:
==================
BASIC (10-12 accounts):
  - Small schools (< 200 students)
  - Kindergartens, small primary schools
  - Simple accounting needs

STANDARD (25-30 accounts):
  - Medium schools (200-700 students)
  - Secondary schools, combined schools
  - Moderate accounting needs

ADVANCED (130+ accounts):
  - Large schools (700+ students)
  - Universities, large secondary schools
  - Professional accounting with auditors

AUTHOR: Schoolara Development Team
VERSION: 2.1
LAST UPDATED: 2025-01-09
CHANGES: Updated all create() to get_or_create() for idempotency
"""

from django.db import transaction
from django.utils import timezone
from django.apps import apps
from decimal import Decimal
import logging

from .school_init_config import SchoolInitConfig

logger = logging.getLogger(__name__)


class SchoolInitializer:
    """
    Main class for school initialization.
    
    This class orchestrates the complete setup of a school's financial system
    by creating all necessary database records in the correct order with
    proper relationships and validations.
    
    All methods use get_or_create() making initialization idempotent - 
    it can be safely run multiple times without errors.
    
    Example:
        >>> from accounts.models import School
        >>> school = School.objects.get(database_alias='atepi_palabek')
        >>> initializer = SchoolInitializer(school)
        >>> result = initializer.initialize_all(user=request.user)
        >>> print(result['created']['accounts'])
        25
    """
    
    def __init__(self, school):
        """
        Initialize the SchoolInitializer.
        
        Args:
            school: School instance to initialize
        """
        self.school = school
        self.config = SchoolInitConfig.get_init_config(school)
        self.complexity = self.config['complexity']
        
        logger.info(
            f"Initializing {school.full_name} with {self.complexity} complexity"
        )
    
    @transaction.atomic
    def initialize_all(self, user=None):
        """
        Perform complete school initialization.
        
        This is the main entry point that orchestrates all initialization steps.
        All operations are wrapped in a transaction - if any step fails, 
        everything is rolled back.
        
        Args:
            user: User performing the initialization (for audit trail)
            
        Returns:
            dict: Results dictionary with structure:
                {
                    'success': bool,
                    'errors': list,
                    'created': {
                        'account_types': int,
                        'accounts': int,
                        'fee_categories': int,
                        'expense_categories': int,
                        'journals': int,
                        'fiscal_periods': int,
                        'display_groups': int,
                        'payment_methods': int,
                        'departments': int,
                        'designations': int,
                        'units_of_measure': int,
                        'tax_rates': int,
                    }
                }
        """
        results = {
            'success': True,
            'errors': [],
            'created': {
                'account_types': 0,
                'accounts': 0,
                'fee_categories': 0,
                'expense_categories': 0,    
                'journals': 0,  
                'fiscal_periods': 0,
                'display_groups': 0,
                'payment_methods': 0,
                'departments': 0,
                'designations': 0,
                'units_of_measure': 0,
                'tax_rates': 0,
            }
        }
        
        try:
            # PHASE 1: CORE FINANCIAL SETUP
            logger.info("="*70)
            logger.info("PHASE 1: CORE FINANCIAL SETUP")
            logger.info("="*70)
            
            logger.info(f"Step 1: Creating account types...")
            account_types = self._create_account_types()
            results['created']['account_types'] = len(account_types)
            
            logger.info(f"Step 2: Creating chart of accounts ({self.complexity})...")
            accounts = self._create_chart_of_accounts()
            results['created']['accounts'] = len(accounts)
            
            logger.info(f"Step 3: Creating financial settings...")
            self._create_financial_settings()
            
            logger.info(f"Step 4: Creating account mappings...")
            self._create_account_mappings()
            
            # PHASE 2: FEES AND EXPENSES
            logger.info("="*70)
            logger.info("PHASE 2: FEES AND EXPENSES")
            logger.info("="*70)
            
            logger.info(f"Step 5: Creating display groups...")
            display_groups = self._create_display_groups()
            results['created']['display_groups'] = len(display_groups)
            
            logger.info(f"Step 6: Creating fee categories...")
            fee_categories = self._create_fee_categories()
            results['created']['fee_categories'] = len(fee_categories)
            
            logger.info(f"Step 7: Creating expense categories...")
            expense_categories = self._create_expense_categories()
            results['created']['expense_categories'] = len(expense_categories)
            
            # PHASE 3: JOURNALS AND FISCAL PERIODS
            logger.info("="*70)
            logger.info("PHASE 3: JOURNALS AND FISCAL PERIODS")
            logger.info("="*70)
            
            logger.info(f"Step 8: Creating journals...")
            journals = self._create_journals()
            results['created']['journals'] = len(journals)
            
            logger.info(f"Step 9: Creating fiscal year and periods...")
            fiscal_periods = self._create_fiscal_year()
            results['created']['fiscal_periods'] = len(fiscal_periods)
            
            # PHASE 4: PAYMENT AND TAX SETUP
            logger.info("="*70)
            logger.info("PHASE 4: PAYMENT AND TAX SETUP")
            logger.info("="*70)
            
            logger.info(f"Step 10: Creating payment methods...")
            payment_methods = self._create_payment_methods()
            results['created']['payment_methods'] = len(payment_methods)
            
            logger.info(f"Step 11: Creating tax rates...")
            tax_rates = self._create_tax_rates()
            results['created']['tax_rates'] = len(tax_rates)
            
            # PHASE 5: HR AND ORGANIZATIONAL STRUCTURE
            logger.info("="*70)
            logger.info("PHASE 5: HR AND ORGANIZATIONAL STRUCTURE")
            logger.info("="*70)
            
            logger.info(f"Step 12: Creating departments...")
            departments = self._create_departments()
            results['created']['departments'] = len(departments)
            
            logger.info(f"Step 13: Creating designations...")
            designations = self._create_designations()
            results['created']['designations'] = len(designations)
            
            # PHASE 6: INVENTORY AND PROCUREMENT
            logger.info("="*70)
            logger.info("PHASE 6: INVENTORY AND PROCUREMENT")
            logger.info("="*70)
            
            logger.info(f"Step 14: Creating units of measure...")
            units = self._create_units_of_measure()
            results['created']['units_of_measure'] = len(units)
            
            # FINALIZATION
            logger.info("="*70)
            logger.info("FINALIZATION")
            logger.info("="*70)
            
            # Mark school as initialized
            self.school.is_financial_setup_complete = True
            self.school.is_initial_setup_complete = True
            self.school.setup_completed_at = timezone.now()
            self.school.setup_completed_by = user
            self.school.save(using='default')
            
            logger.info("="*70)
            logger.info(f"✓ INITIALIZATION COMPLETE FOR {self.school.full_name.upper()}")
            logger.info("="*70)
            logger.info(f"Complexity Level: {self.complexity}")
            logger.info(f"Account Types: {results['created']['account_types']}")
            logger.info(f"Accounts Created: {results['created']['accounts']}")
            logger.info(f"Fee Categories: {results['created']['fee_categories']}")
            logger.info(f"Expense Categories: {results['created']['expense_categories']}")
            logger.info(f"Journals: {results['created']['journals']}")
            logger.info(f"Fiscal Periods: {results['created']['fiscal_periods']}")
            logger.info(f"Display Groups: {results['created']['display_groups']}")
            logger.info(f"Payment Methods: {results['created']['payment_methods']}")
            logger.info(f"Tax Rates: {results['created']['tax_rates']}")
            logger.info(f"Departments: {results['created']['departments']}")
            logger.info(f"Designations: {results['created']['designations']}")
            logger.info(f"Units of Measure: {results['created']['units_of_measure']}")  
            logger.info("="*70)
            
        except Exception as e:
            logger.error("="*70)
            logger.error(f"✗ INITIALIZATION FAILED: {e}")
            logger.error("="*70)
            logger.error(f"Error details:", exc_info=True)
            results['success'] = False
            results['errors'].append(str(e))
            raise  # Re-raise to trigger transaction rollback
        
        return results
    
    # =========================================================================
    # STEP 1: CREATE ACCOUNT TYPES
    # =========================================================================
    
    def _create_account_types(self):
        """Create standard account types using get_or_create()"""
        from core.services.school_init_config import SchoolInitConfig
        
        logger.info(f"Creating account types for {self.school.full_name}...")
        
        account_types = []
        account_type_configs = SchoolInitConfig.get_account_types()
        
        for config in account_type_configs:
            try:
                AccountType = apps.get_model('finance', 'AccountType')
                # Use code as the unique lookup key
                account_type, created = AccountType.objects.get_or_create(
                    code=config['code'],  # Code is unique within this database
                    defaults=config
                )
                
                if created:
                    logger.info(f"  ✓ Created: {account_type.name} ({account_type.code})")
                else:
                    logger.info(f"  → Exists: {account_type.name} ({account_type.code})")
                
                account_types.append(account_type)
                
            except Exception as e:
                logger.error(f"  ✗ Failed to create {config.get('name')}: {e}")
                raise
        
        logger.info(f"Account types complete: {len(account_types)} types created/verified")
        return account_types
    
    # =========================================================================
    # STEP 2: CREATE CHART OF ACCOUNTS
    # =========================================================================
    
    def _create_chart_of_accounts(self):
        """
        Create the complete chart of accounts from config using get_or_create().
        
        The chart of accounts is customized based on school complexity:
        - BASIC: 10-15 accounts (simple structure)
        - STANDARD: 25-30 accounts (moderate detail)
        - ADVANCED: 130+ accounts (comprehensive)
        
        Returns:
            list: List of created/found Account instances
        """
        Account = apps.get_model('finance', 'Account')
        AccountType = apps.get_model('finance', 'AccountType')
        
        accounts = []
        account_configs = self.config['chart_of_accounts']
        
        for account_data in account_configs:
            # Get the account type
            account_type = AccountType.objects.get(
                account_type=account_data['type']
            )
            
            # Separate account data from metadata
            create_data = {
                'account_number': account_data['number'],
                'name': account_data['name'],
                'account_type': account_type,
                'is_active': True,
            }
            
            # Add optional fields if present
            optional_fields = [
                'description',
                'is_bank_account',
                'is_cash_account',
                'is_receivable_account',
                'is_payable_account',
                'is_revenue_account',
                'is_expense_account',
                'is_inventory_account',
                'is_fixed_asset',
                'is_contra_account',
                'is_loan_account',
                'is_tax_account',
                'receivable_type',
                'revenue_type',
                'expense_type',
                'inventory_type',
                'mobile_money_provider',
            ]
            
            for field in optional_fields:
                if field in account_data:
                    create_data[field] = account_data[field]
            
            # ✅ Use get_or_create instead of create
            account, created = Account.objects.get_or_create(
                account_number=account_data['number'],
                defaults=create_data
            )
            
            accounts.append(account)
            
            if created:
                logger.debug(f"  ✓ Created: {account.account_number} - {account.name}")
            else:
                logger.debug(f"  → Exists: {account.account_number} - {account.name}")
        
        logger.info(
            f"  Created/verified {len(accounts)} accounts for {self.complexity} complexity"
        )
        
        return accounts
    
    # =========================================================================
    # STEP 3: CREATE FINANCIAL SETTINGS
    # =========================================================================
    
    def _create_financial_settings(self):
        """
        Create financial settings with defaults from config.
        
        Financial settings control:
        - Currency and formatting
        - Invoice/payment numbering
        - Payment terms and policies
        - Late fees and discounts
        - Email notifications
        
        Returns:
            FinancialSettings: Created settings instance
        """
        FinancialSettings = apps.get_model('core', 'FinancialSettings')
        
        # Check if already exists (singleton pattern)
        if FinancialSettings.objects.exists():
            logger.warning("  ⊙ FinancialSettings already exists, skipping creation")
            return FinancialSettings.objects.first()
        
        # Create with defaults from config
        settings_data = self.config['financial_settings']
        settings = FinancialSettings.objects.create(**settings_data)
        
        logger.info(
            f"  ✓ Created FinancialSettings (Currency: {settings.school_currency})"
        )
        
        return settings
    
    # =========================================================================
    # STEP 4: CREATE ACCOUNT MAPPINGS
    # =========================================================================
    
    def _create_account_mappings(self):
        """
        Create account mappings that link accounts to system operations.
        
        Account mappings tell the system which GL account to use for:
        - Bank receipts
        - Cash receipts
        - Student receivables
        - Revenue recognition
        - Expense posting
        - Scholarships/discounts
        - Accounts payable
        - Equity/capital
        
        This enables automatic journal entry creation.
        
        Returns:
            CoreAccountMappings: Created mappings instance
        """
        CoreAccountMappings = apps.get_model('core', 'CoreAccountMappings')
        FinancialSettings = apps.get_model('core', 'FinancialSettings')
        Account = apps.get_model('finance', 'Account')
        
        # Get financial settings
        financial_settings = FinancialSettings.objects.first()
        
        if not financial_settings:
            raise Exception("FinancialSettings must be created before account mappings")
        
        # Check if already exists
        if hasattr(financial_settings, 'account_mappings'):
            logger.warning("  ⊙ CoreAccountMappings already exists, skipping creation")
            return financial_settings.account_mappings
        
        # Get account mapping configuration
        mappings_config = self.config['account_mappings']
        
        # Build mapping data
        mapping_data = {'financial_settings': financial_settings}
        
        for field_name, config in mappings_config.items():
            # Try primary search criteria
            account = Account.objects.filter(**config['search']).first()
            
            # Try fallback if primary fails
            if not account and 'fallback' in config:
                account = Account.objects.filter(**config['fallback']).first()
            
            # Skip if optional and not found
            if not account and config.get('optional', False):
                logger.debug(f"  ⊙ Optional account {field_name} not found, skipping")
                continue
            
            # Error if required and not found
            if not account:
                raise Exception(
                    f"Required account for {field_name} not found. "
                    f"Search: {config['search']}"
                )
            
            mapping_data[field_name] = account
            logger.debug(f"  ✓ Mapped {field_name} → {account.account_number}")
        
        # Create the mappings
        mappings = CoreAccountMappings.objects.create(**mapping_data)
        
        logger.info("  ✓ Created CoreAccountMappings with required accounts")
        
        return mappings
    
    # =========================================================================
    # STEP 5: CREATE DISPLAY GROUPS
    # =========================================================================
    
    def _create_display_groups(self):
        """Create display groups using name as unique identifier."""
        DisplayGroup = apps.get_model('fees', 'DisplayGroup')
        
        groups = []
        groups_config = self.config['display_groups']
        
        for group_data in groups_config:
            # ✅ Use 'name' as unique identifier (it's already unique in the model)
            group_name = group_data.pop('name')
            
            group, created = DisplayGroup.objects.get_or_create(
                name=group_name,  # ✅ Use name instead of code
                defaults=group_data
            )
            groups.append(group)
            
            if created:
                logger.debug(f"  ✓ Created: {group.name}")
            else:
                logger.debug(f"  → Exists: {group.name}")
        
        logger.info(f"  Created/verified {len(groups)} display groups")
        
        return groups
    
    # =========================================================================
    # STEP 6: CREATE FEE CATEGORIES
    # =========================================================================
    
    def _create_fee_categories(self):
        """
        Create fee categories with display group references using get_or_create().
        
        DisplayGroups must be created first (in Step 5) before this step.
        This method converts display_group names from config into
        DisplayGroup instances before creating FeesCategory records.
        
        Returns:
            list: List of created/found FeesCategory instances
        """
        FeesCategory = apps.get_model('fees', 'FeesCategory')
        DisplayGroup = apps.get_model('fees', 'DisplayGroup')
        
        categories = []
        categories_config = self.config['fee_categories']
        
        # ✅ Build display group lookup map by NAME (not code)
        display_groups_map = {
            dg.name: dg for dg in DisplayGroup.objects.all()
        }
        
        for category_data in categories_config.copy():
            # Extract display_group NAME (string) from config
            display_group_name = category_data.pop('display_group', None)
            category_code = category_data.pop('code')
            
            # ✅ Convert NAME to DisplayGroup instance
            if display_group_name and display_group_name in display_groups_map:
                category_data['display_group'] = display_groups_map[display_group_name]
            else:
                category_data['display_group'] = None
                if display_group_name:
                    logger.warning(f"  ⚠ Display group not found: {display_group_name}")
            
            # Use get_or_create with code as unique identifier
            category, created = FeesCategory.objects.get_or_create(
                code=category_code,
                defaults=category_data
            )
            categories.append(category)
            
            if created:
                logger.debug(f"  ✓ Created: {category.name} ({category.code})")
            else:
                logger.debug(f"  → Exists: {category.name} ({category.code})")
        
        logger.info(f"  Created/verified {len(categories)} fee categories")
        
        return categories
    
    # =========================================================================
    # STEP 7: CREATE EXPENSE CATEGORIES
    # =========================================================================
    
    def _create_expense_categories(self):
        """Create default expense categories from config using get_or_create()"""
        ExpenseCategory = apps.get_model('finance', 'ExpenseCategory')
        
        categories = []
        categories_config = self.config['expense_categories']
        
        for category_data in categories_config.copy():
            # ✅ Use 'name' as the unique identifier (no 'code' field exists)
            category_name = category_data.pop('name')
            
            # ✅ Use get_or_create with name as unique identifier
            category, created = ExpenseCategory.objects.get_or_create(
                name=category_name,
                defaults=category_data
            )
            categories.append(category)
            
            if created:
                logger.debug(f"  ✓ Created: {category.name}")
            else:
                logger.debug(f"  → Exists: {category.name}")
        
        logger.info(f"  Created/verified {len(categories)} expense categories")
        
        return categories
    
    # =========================================================================
    # STEP 8: CREATE JOURNALS
    # =========================================================================

    def _create_journals(self):
        """Create default journals from config using get_or_create()"""
        Journal = apps.get_model('finance', 'Journal')
        
        journals = []
        journals_config = self.config['journals']
        
        for journal_data in journals_config.copy():
            # ✅ Use 'name' as the unique identifier (no 'code' field exists)
            journal_name = journal_data.pop('name')
            
            # ✅ Use get_or_create with name as unique identifier
            journal, created = Journal.objects.get_or_create(
                name=journal_name,
                defaults=journal_data
            )
            journals.append(journal)
            
            if created:
                logger.debug(f"  ✓ Created: {journal.name}")
            else:
                logger.debug(f"  → Exists: {journal.name}")
        
        logger.info(f"  Created/verified {len(journals)} journals")
        
        return journals
    
    # =========================================================================
    # STEP 9: CREATE FISCAL YEAR AND PERIODS
    # =========================================================================
    
    def _create_fiscal_year(self):
        """
        Create fiscal year and periods for current year using get_or_create().
        
        Creates:
        - Fiscal year (e.g., 2025)
        - 12 fiscal periods (Jan-Dec)
        - Sets current period as active
        
        Returns:
            list: List of created/found FiscalPeriod instances
        """
        FiscalYear = apps.get_model('core', 'FiscalYear')
        FiscalPeriod = apps.get_model('core', 'FiscalPeriod')
        
        # Get current year
        current_year = timezone.now().year
        current_month = timezone.now().month
        
        # Create fiscal year using 'name' and 'code' instead of 'year'
        fiscal_year_name = f'FY {current_year}'
        fiscal_year_code = f'AY{current_year}'
        
        # ✅ Already using get_or_create
        fiscal_year, created = FiscalYear.objects.get_or_create(
            code=fiscal_year_code,  # Use code as unique identifier
            defaults={
                'name': fiscal_year_name,
                'start_date': timezone.datetime(current_year, 1, 1).date(),
                'end_date': timezone.datetime(current_year, 12, 31).date(),
                'is_active': True,
                'is_closed': False,
                'status': 'ACTIVE',
            }
        )
        
        if created:
            logger.info(f"  ✓ Created fiscal year: {fiscal_year.name}")
        else:
            logger.info(f"  → Fiscal year already exists: {fiscal_year.name}")
        
        # Create fiscal periods (months)
        periods = []
        month_names = [
            'January', 'February', 'March', 'April', 'May', 'June',
            'July', 'August', 'September', 'October', 'November', 'December'
        ]
        
        for month_num in range(1, 13):
            # Calculate period dates
            import calendar
            last_day = calendar.monthrange(current_year, month_num)[1]
            
            start_date = timezone.datetime(current_year, month_num, 1).date()
            end_date = timezone.datetime(current_year, month_num, last_day).date()
            
            # Generate unique code for this period
            period_code = f'FP_{current_year}_{month_num:02d}'
            
            # ✅ Already using get_or_create
            period, created = FiscalPeriod.objects.get_or_create(
                code=period_code,  # Use code as unique identifier
                defaults={
                    'fiscal_year': fiscal_year,
                    'name': f'{month_names[month_num - 1]} {current_year}',
                    'period_number': Decimal(str(month_num)),
                    'period_type': 'MONTHLY',
                    'start_date': start_date,
                    'end_date': end_date,
                    'is_active': (month_num == current_month),
                    'is_closed': (month_num < current_month),
                    'status': 'ACTIVE' if month_num == current_month else 'CLOSED' if month_num < current_month else 'DRAFT',
                }
            )
            
            periods.append(period)
            
            if created:
                status = "ACTIVE" if month_num == current_month else "CLOSED" if month_num < current_month else "FUTURE"
                logger.debug(f"  ✓ Created: {period.name} [{status}]")
            else:
                logger.debug(f"  → Exists: {period.name}")
        
        logger.info(f"  Created/verified {len(periods)} fiscal periods for {current_year}")
        
        return periods
    
    # =========================================================================
    # STEP 10: CREATE PAYMENT METHODS
    # =========================================================================
    
    def _create_payment_methods(self):
        """
        Create default payment methods from config using get_or_create().
        
        Payment methods define how parents can pay fees:
        - Cash
        - Bank Transfer
        - Mobile Money (MTN, Airtel)
        - Credit/Debit Cards
        - Checks
        
        Returns:
            list: List of created/found PaymentMethod instances
        """
        PaymentMethod = apps.get_model('core', 'PaymentMethod')
        
        methods = []
        methods_config = self.config['payment_methods']
        
        for method_data in methods_config.copy():
            # Extract code for lookup
            method_code = method_data.pop('code')
            
            # ✅ Use get_or_create with code as unique identifier
            method, created = PaymentMethod.objects.get_or_create(
                code=method_code,
                defaults=method_data
            )
            methods.append(method)
            
            if created:
                logger.debug(f"  ✓ Created: {method.name} ({method.code})")
            else:
                logger.debug(f"  → Exists: {method.name} ({method.code})")
        
        logger.info(f"  Created/verified {len(methods)} payment methods")
        
        return methods
    
    # =========================================================================
    # STEP 11: CREATE TAX RATES
    # =========================================================================
    
    def _create_tax_rates(self):
        """Create default tax rates from config (country-specific) using get_or_create()."""
        TaxRate = apps.get_model('core', 'TaxRate')
        
        rates = []
        rates_config = self.config['tax_rates']
        
        for rate_data in rates_config.copy():
            # Extract lookup fields
            rate_name = rate_data.pop('name')
            tax_type = rate_data.get('tax_type')
            effective_from = rate_data.get('effective_from')
            
            # ✅ Use get_or_create with tax_type + effective_from for uniqueness
            rate, created = TaxRate.objects.get_or_create(
                tax_type=tax_type,
                effective_from=effective_from,
                defaults={'name': rate_name, **rate_data}
            )
            rates.append(rate)
            
            if created:
                logger.debug(f"  ✓ Created: {rate.name} ({rate.rate}%)")
            else:
                logger.debug(f"  → Exists: {rate.name} ({rate.rate}%)")
        
        logger.info(f"  Created/verified {len(rates)} tax rates")
        
        return rates
    
    # =========================================================================
    # STEP 12: CREATE DEPARTMENTS
    # =========================================================================
    
    def _create_departments(self):
        """
        Create organizational departments from config using get_or_create().
        
        Departments organize staff into functional units:
        - Academic (teaching departments)
        - Administrative (office and management)
        - Support (library, ICT, health, etc.)
        - Operational (maintenance, security, transport)
        
        Returns:
            list: List of created/found Department instances
        """
        Department = apps.get_model('hr', 'Department')
        
        departments = []
        departments_config = self.config['departments']
        
        for dept_data in departments_config.copy():
            # Extract code for lookup
            dept_code = dept_data.pop('code')
            
            # ✅ Use get_or_create with code as unique identifier
            dept, created = Department.objects.get_or_create(
                code=dept_code,
                defaults=dept_data
            )
            departments.append(dept)
            
            if created:
                logger.debug(f"  ✓ Created: {dept.name} ({dept.code})")
            else:
                logger.debug(f"  → Exists: {dept.name} ({dept.code})")
        
        logger.info(f"  Created/verified {len(departments)} departments")
        
        return departments
    
    # =========================================================================
    # STEP 13: CREATE DESIGNATIONS
    # =========================================================================
    
    def _create_designations(self):
        """Create job designations mapped to departments using get_or_create()."""
        Designation = apps.get_model('hr', 'Designation')
        Department = apps.get_model('hr', 'Department')
        
        # First, log all available departments for debugging
        all_depts = list(Department.objects.all().values_list('code', 'name'))
        logger.info(f"  Available departments: {len(all_depts)}")
        for code, name in all_depts:
            logger.debug(f"    - {code}: {name}")
        
        designations = []
        designations_config = self.config['designations']
        
        for desig_data in designations_config.copy():
            try:
                # Get the department by code
                dept_code = desig_data.pop('department_code')
                desig_code = desig_data.pop('code')
                
                # Try to get department with detailed error
                try:
                    department = Department.objects.get(code=dept_code)
                except Department.DoesNotExist:
                    logger.error(f"  ✗ MISSING: Department '{dept_code}' not found for designation '{desig_data.get('name')}'")
                    logger.error(f"     Tried to find: code='{dept_code}' (length={len(dept_code)})")
                    logger.error(f"     Available codes: {[d[0] for d in all_depts]}")
                    continue
                
                # ✅ Use get_or_create with code as unique identifier
                desig_data['department'] = department
                desig, created = Designation.objects.get_or_create(
                    code=desig_code,
                    defaults=desig_data
                )
                designations.append(desig)
                
                if created:
                    logger.debug(f"  ✓ Created: {desig.name} → {department.code}")
                else:
                    logger.debug(f"  → Exists: {desig.name} → {department.code}")
                
            except Exception as e:
                logger.error(f"  ✗ Failed designation '{desig_data.get('name', 'UNKNOWN')}': {e}")
                continue
        
        logger.info(f"  Created/verified {len(designations)} designations (skipped {len(designations_config) - len(designations)})")
        return designations
    
    # =========================================================================
    # STEP 14: CREATE UNITS OF MEASURE
    # =========================================================================
    
    def _create_units_of_measure(self):
        """
        Create units of measure for inventory and procurement using get_or_create().
        
        Units of measure are used for:
        - Ordering supplies (pieces, boxes, reams)
        - Inventory tracking (kilograms, liters, meters)
        - Food service (servings, portions)
        - Classroom sets (30 pieces, 40 pieces)
        
        Returns:
            list: List of created/found UnitOfMeasure instances
        """
        UnitOfMeasure = apps.get_model('core', 'UnitOfMeasure')
        
        units = []
        units_config = self.config['units_of_measure']
        
        for unit_data in units_config.copy():
            # ✅ Extract symbol for lookup (primary unique identifier)
            unit_symbol = unit_data.pop('symbol', None)
            
            if not unit_symbol:
                logger.warning(f"  ⚠ Unit missing symbol: {unit_data.get('name')}")
                continue
            
            # ✅ Use get_or_create with symbol as unique identifier
            unit, created = UnitOfMeasure.objects.get_or_create(
                symbol=unit_symbol,
                defaults=unit_data
            )
            units.append(unit)
            
            if created:
                logger.debug(f"  ✓ Created: {unit.name} ({unit.symbol})")
            else:
                logger.debug(f"  → Exists: {unit.name} ({unit.symbol})")
        
        logger.info(f"  Created/verified {len(units)} units of measure")
        
        return units

# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

def initialize_school(school, user=None):
    """
    Convenience function to initialize a school.
    
    This is the main entry point for school initialization.
    Use this function instead of directly instantiating SchoolInitializer.
    
    This initialization is IDEMPOTENT - it can be safely run multiple times.
    Existing records will be found and reused instead of creating duplicates.
    
    Args:
        school: School instance to initialize
        user: User performing the initialization (optional, for audit)
        
    Returns:
        dict: Results dictionary with structure:
            {
                'success': bool,
                'errors': list,
                'created': {
                    'account_types': int,
                    'accounts': int,
                    'fee_categories': int,
                    'expense_categories': int,
                    'journals': int,
                    'fiscal_periods': int,
                    'display_groups': int,
                    'payment_methods': int,
                    'departments': int,
                    'designations': int,
                    'units_of_measure': int,
                    'tax_rates': int,
                }
            }
    
    Example:
        >>> from accounts.models import School
        >>> from core.services.school_initialization import initialize_school
        >>> 
        >>> school = School.objects.get(database_alias='atepi_palabek')
        >>> result = initialize_school(school, user=request.user)
        >>> 
        >>> if result['success']:
        >>>     print(f"Success! Created {result['created']['accounts']} accounts")
        >>>     print(f"Fee categories: {result['created']['fee_categories']}")
        >>>     print(f"Departments: {result['created']['departments']}")
        >>> else:
        >>>     print(f"Failed: {result['errors']}")
    
    Raises:
        Exception: If initialization fails (wrapped in transaction)
    """
    try:
        initializer = SchoolInitializer(school)
        return initializer.initialize_all(user=user)
    except Exception as e:
        logger.error(f"Failed to initialize {school.full_name}: {e}")
        raise


# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================

def validate_school_can_be_initialized(school):
    """
    Validate that a school can be initialized.
    
    Args:
        school: School instance to validate
        
    Returns:
        tuple: (can_initialize: bool, reason: str)
    
    Example:
        >>> can_init, reason = validate_school_can_be_initialized(school)
        >>> if not can_init:
        >>>     print(f"Cannot initialize: {reason}")
    """
    if school.is_initial_setup_complete:
        return False, "School is already initialized"
    
    if not school.is_active_subscription:
        return False, "School subscription is not active"
    
    # Check if database exists in settings
    from django.conf import settings
    if school.database_alias not in settings.DATABASES:
        return False, f"Database '{school.database_alias}' not found in settings"
    
    return True, "School can be initialized"


def get_initialization_preview(school):
    """
    Get a preview of what will be created during initialization.
    
    Args:
        school: School instance
        
    Returns:
        dict: Preview information
    
    Example:
        >>> preview = get_initialization_preview(school)
        >>> print(f"Will create {preview['accounts_count']} accounts")
        >>> print(f"Complexity: {preview['complexity']}")
        >>> print(f"Currency: {preview['currency']}")
    """
    config = SchoolInitConfig.get_init_config(school)
    
    return {
        'complexity': config['complexity'],
        'accounts_count': len(config['chart_of_accounts']),
        'fee_categories_count': len(config['fee_categories']),
        'expense_categories_count': len(config['expense_categories']),
        'journals_count': len(config['journals']),
        'display_groups_count': len(config['display_groups']),
        'payment_methods_count': len(config['payment_methods']),
        'departments_count': len(config['departments']),
        'designations_count': len(config['designations']),
        'units_of_measure_count': len(config['units_of_measure']),
        'tax_rates_count': len(config['tax_rates']),
        'currency': config['financial_settings']['school_currency'],
        'needs_boarding': config['needs_boarding'],
        'school_type': school.school_type,
        'student_capacity': school.student_capacity,
    }


# =============================================================================
# CLEANUP AND RE-INITIALIZATION
# =============================================================================

@transaction.atomic
def cleanup_school_initialization(school):
    """
    Clean up (delete) all initialization data for a school.
    
    WARNING: This is a DESTRUCTIVE operation. Use with extreme caution.
    This should only be used for testing or fixing broken initializations.
    
    Args:
        school: School instance to clean up
        
    Returns:
        dict: Summary of deleted records
    
    Example:
        >>> from core.services.school_initialization import cleanup_school_initialization
        >>> summary = cleanup_school_initialization(school)
        >>> print(f"Deleted {summary['accounts']} accounts")
    """
    logger.warning(f"⚠️  CLEANUP: Starting cleanup for {school.full_name}")
    
    deleted = {
        'accounts': 0,
        'fee_categories': 0,
        'expense_categories': 0,
        'journals': 0,
        'fiscal_periods': 0,
        'display_groups': 0,
        'payment_methods': 0,
        'departments': 0,
        'designations': 0,
        'units_of_measure': 0,
        'tax_rates': 0,
    }
    
    try:
        # Delete in reverse order of creation
        
        # Delete designations (depends on departments)
        Designation = apps.get_model('hr', 'Designation')
        count = Designation.objects.all().delete()[0]
        deleted['designations'] = count
        logger.info(f"  Deleted {count} designations")
        
        # Delete departments
        Department = apps.get_model('hr', 'Department')
        count = Department.objects.all().delete()[0]
        deleted['departments'] = count
        logger.info(f"  Deleted {count} departments")
        
        # Delete units of measure
        UnitOfMeasure = apps.get_model('core', 'UnitOfMeasure')
        count = UnitOfMeasure.objects.all().delete()[0]
        deleted['units_of_measure'] = count
        logger.info(f"  Deleted {count} units of measure")
        
        # Delete tax rates
        TaxRate = apps.get_model('core', 'TaxRate')
        count = TaxRate.objects.all().delete()[0]
        deleted['tax_rates'] = count
        logger.info(f"  Deleted {count} tax rates")
        
        # Delete payment methods
        PaymentMethod = apps.get_model('core', 'PaymentMethod')
        count = PaymentMethod.objects.all().delete()[0]
        deleted['payment_methods'] = count
        logger.info(f"  Deleted {count} payment methods")
        
        # Delete fiscal periods and year
        FiscalPeriod = apps.get_model('core', 'FiscalPeriod')
        count = FiscalPeriod.objects.all().delete()[0]
        deleted['fiscal_periods'] = count
        logger.info(f"  Deleted {count} fiscal periods")
        
        FiscalYear = apps.get_model('core', 'FiscalYear')
        FiscalYear.objects.all().delete()
        
        # Delete journals
        Journal = apps.get_model('finance', 'Journal')
        count = Journal.objects.all().delete()[0]
        deleted['journals'] = count
        logger.info(f"  Deleted {count} journals")
        
        # Delete expense categories
        ExpenseCategory = apps.get_model('finance', 'ExpenseCategory')
        count = ExpenseCategory.objects.all().delete()[0]
        deleted['expense_categories'] = count
        logger.info(f"  Deleted {count} expense categories")
        
        # Delete fee categories
        FeesCategory = apps.get_model('fees', 'FeesCategory')
        count = FeesCategory.objects.all().delete()[0]
        deleted['fee_categories'] = count
        logger.info(f"  Deleted {count} fee categories")
        
        # Delete display groups
        DisplayGroup = apps.get_model('fees', 'DisplayGroup')
        count = DisplayGroup.objects.all().delete()[0]
        deleted['display_groups'] = count
        logger.info(f"  Deleted {count} display groups")
        
        # Delete account mappings and financial settings
        CoreAccountMappings = apps.get_model('core', 'CoreAccountMappings')
        CoreAccountMappings.objects.all().delete()
        
        FinancialSettings = apps.get_model('core', 'FinancialSettings')
        FinancialSettings.objects.all().delete()
        
        # Delete accounts
        Account = apps.get_model('finance', 'Account')
        count = Account.objects.all().delete()[0]
        deleted['accounts'] = count
        logger.info(f"  Deleted {count} accounts")
        
        # Delete account types
        AccountType = apps.get_model('finance', 'AccountType')
        AccountType.objects.all().delete()
        
        # Reset school initialization flags
        school.is_financial_setup_complete = False
        school.is_initial_setup_complete = False
        school.setup_completed_at = None
        school.setup_completed_by = None
        school.save(using='default')
        
        logger.warning(f"✓ CLEANUP COMPLETE for {school.full_name}")
        
    except Exception as e:
        logger.error(f"✗ CLEANUP FAILED: {e}", exc_info=True)
        raise
    
    return deleted


@transaction.atomic
def reinitialize_school(school, user=None):
    """
    Clean up and re-initialize a school.
    
    WARNING: This is DESTRUCTIVE. All existing data will be deleted.
    
    Args:
        school: School instance to re-initialize
        user: User performing the operation
        
    Returns:
        dict: Initialization results
    
    Example:
        >>> result = reinitialize_school(school, user=request.user)
        >>> if result['success']:
        >>>     print("Re-initialization successful!")
    """
    logger.warning(f"⚠️  RE-INITIALIZATION: Starting for {school.full_name}")
    
    # Clean up existing data
    cleanup_summary = cleanup_school_initialization(school)
    logger.info(f"Cleanup complete: {cleanup_summary}")
    
    # Re-initialize
    result = initialize_school(school, user=user)
    
    logger.warning(f"✓ RE-INITIALIZATION COMPLETE for {school.full_name}")
    
    return result