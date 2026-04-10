# core/services/school_initialization.py

"""
School Initialization Service

Handles complete financial system setup for a new school database.
Creates all accounts, mappings, categories, journals, fiscal periods,
departments, designations, and supporting data in the correct order.

USAGE:
    from core.services.school_initialization import initialize_school
    result = initialize_school(school_instance, user=request.user)

COMPLEXITY LEVELS:
    BASIC    — ~14 accounts  (< 200 students, kindergarten/primary)
    STANDARD — ~35 accounts  (200–700 students)
    ADVANCED — ~80 accounts  (700+ students, universities)

CHANGES FROM ORIGINAL
---------------------
initialize_all()
    Added Phase 0 — calls SchoolInitConfig.validate_config() before any DB
    writes. Catches bad display_group names, invalid choice values, and
    duplicate designation codes up front, so the transaction never starts
    with a broken config.

_create_account_mappings()
    Removed stale "Account number corrections" comment. The config dict is now
    produced by get_account_mappings_config(complexity), which is already
    complexity-aware, so no manual overrides are needed here.

_create_specialized_account_mappings()
    BUG FIX — late_fee_revenue_account:
        Both branches of the ternary were acct('4300'), making the condition
        meaningless. In STANDARD, 4300 is Transport Fees — wrong for late fees.
        Fixed: ADVANCED only gets acct('4300') (Late Payment Fees); BASIC and
        STANDARD receive None.

    BUG FIX — social_security_payable_account:
        Original used acct('2030') for all complexities. In STANDARD, 2030 is
        Student Deposits — completely wrong for NSSF/social security payroll.
        Fixed: acct('2030') only for ADVANCED (where it is NSSF Payable);
        BASIC and STANDARD receive None.

    NEW — penalty_revenue_account:
        Maps to acct('4310') (Replacement Fees) in ADVANCED where that account
        exists; None on BASIC and STANDARD.

_create_fiscal_year()
    BUG FIX — period_type:
        Was 'TERM', which is not a valid FiscalPeriod.PERIOD_TYPE_CHOICES value.
        FiscalPeriod.save() calls full_clean(), which raises ValidationError and
        prevents any fiscal period from being created. Fixed to 'ACADEMIC_ALIGNED'.

    BUG FIX — date construction:
        Was timezone.datetime(year, month, day).date(). Django's timezone module
        does not expose datetime as an attribute; this raised AttributeError.
        Fixed to _date(year, month, day) using stdlib datetime.date (imported at
        module level as _date).

    calendar import moved from inside the function to module level as _calendar.

_create_units_of_measure()
    BUG FIX — get_or_create lookup key:
        Was symbol, which is nullable (null=True) and not unique on the model.
        Using a nullable field as the lookup key causes None→None collisions
        across multiple records. Fixed to abbreviation, which is always populated.

get_initialization_preview()
    Now calls validate_config() and surfaces config_issues / config_valid in
    the returned dict so callers can surface problems before committing.

cleanup_school_initialization()
    Added SpecialAccountMappings to the singleton deletion list — it was missing
    from the original, leaving orphaned rows after cleanup.
"""

import calendar as _calendar
from datetime import date as _date
from decimal import Decimal

from django.apps import apps
from django.db import transaction
from django.utils import timezone
import logging

from .school_init_config import SchoolInitConfig

logger = logging.getLogger(__name__)


class SchoolInitializer:
    """
    Orchestrates complete school financial system initialization.
    All methods use get_or_create() — safe to run multiple times.
    """

    def __init__(self, school):
        self.school     = school
        self.config     = SchoolInitConfig.get_init_config(school)
        self.complexity = self.config['complexity']

    @transaction.atomic
    def initialize_all(self, user=None):
        """
        Run all initialization steps in dependency order.
        Wrapped in a transaction — rolls back everything on failure.

        Returns:
            dict: {
                'success': bool,
                'errors': list,
                'created': {
                    'account_types', 'accounts', 'fee_categories',
                    'expense_categories', 'journals', 'fiscal_periods',
                    'display_groups', 'payment_methods', 'departments',
                    'designations', 'units_of_measure', 'tax_rates'
                }
            }
        """
        results = {
            'success': True,
            'errors':  [],
            'created': {
                'account_types':      0,
                'accounts':           0,
                'fee_categories':     0,
                'expense_categories': 0,
                'journals':           0,
                'fiscal_periods':     0,
                'display_groups':     0,
                'payment_methods':    0,
                'departments':        0,
                'designations':       0,
                'units_of_measure':   0,
                'tax_rates':          0,
            }
        }

        try:
            # ----------------------------------------------------------------
            # PHASE 0: VALIDATE CONFIG
            # Catch config inconsistencies before any DB writes. Any issue
            # found here means the config file needs fixing — not the DB.
            # ----------------------------------------------------------------
            logger.info(f"[{self.school.full_name}] Phase 0: Validating configuration")
            issues = SchoolInitConfig.validate_config()
            if issues:
                for issue in issues:
                    logger.error(f"  Config issue: {issue}")
                raise ValueError(
                    f"SchoolInitConfig has {len(issues)} issue(s). "
                    "Fix before initializing. See logs for details."
                )
            logger.info("  Config validation passed")

            # ----------------------------------------------------------------
            # PHASE 1: CORE FINANCIAL SETUP
            # ----------------------------------------------------------------
            logger.info(f"[{self.school.full_name}] Phase 1: Core financial setup")

            account_types = self._create_account_types()
            results['created']['account_types'] = len(account_types)

            accounts = self._create_chart_of_accounts()
            results['created']['accounts'] = len(accounts)

            self._create_financial_settings()
            self._create_account_mappings()
            self._create_specialized_account_mappings()

            # ----------------------------------------------------------------
            # PHASE 2: FEES AND EXPENSES
            # ----------------------------------------------------------------
            logger.info(f"[{self.school.full_name}] Phase 2: Fees and expenses")

            display_groups = self._create_display_groups()
            results['created']['display_groups'] = len(display_groups)

            fee_categories = self._create_fee_categories()
            results['created']['fee_categories'] = len(fee_categories)

            expense_categories = self._create_expense_categories()
            results['created']['expense_categories'] = len(expense_categories)

            # ----------------------------------------------------------------
            # PHASE 3: JOURNALS AND FISCAL PERIODS
            # ----------------------------------------------------------------
            logger.info(f"[{self.school.full_name}] Phase 3: Journals and fiscal periods")

            journals = self._create_journals()
            results['created']['journals'] = len(journals)

            fiscal_periods = self._create_fiscal_year()
            results['created']['fiscal_periods'] = len(fiscal_periods)

            # ----------------------------------------------------------------
            # PHASE 4: PAYMENT AND TAX
            # ----------------------------------------------------------------
            logger.info(f"[{self.school.full_name}] Phase 4: Payment methods and tax rates")

            payment_methods = self._create_payment_methods()
            results['created']['payment_methods'] = len(payment_methods)

            tax_rates = self._create_tax_rates()
            results['created']['tax_rates'] = len(tax_rates)

            # ----------------------------------------------------------------
            # PHASE 5: HR STRUCTURE
            # ----------------------------------------------------------------
            logger.info(f"[{self.school.full_name}] Phase 5: Departments and designations")

            departments = self._create_departments()
            results['created']['departments'] = len(departments)

            designations = self._create_designations()
            results['created']['designations'] = len(designations)

            # ----------------------------------------------------------------
            # PHASE 6: INVENTORY
            # ----------------------------------------------------------------
            logger.info(f"[{self.school.full_name}] Phase 6: Units of measure")

            units = self._create_units_of_measure()
            results['created']['units_of_measure'] = len(units)

            # ----------------------------------------------------------------
            # FINALIZATION
            # ----------------------------------------------------------------
            self.school.is_financial_setup_complete = True
            self.school.is_initial_setup_complete   = True
            self.school.setup_completed_at          = timezone.now()
            self.school.setup_completed_by          = user
            self.school.save(using='default')

            logger.info(
                f"[{self.school.full_name}] Initialization complete — "
                f"complexity={self.complexity} "
                f"accounts={results['created']['accounts']} "
                f"fee_cats={results['created']['fee_categories']} "
                f"periods={results['created']['fiscal_periods']}"
            )

        except Exception as e:
            logger.error(
                f"[{self.school.full_name}] Initialization failed: {e}",
                exc_info=True,
            )
            results['success'] = False
            results['errors'].append(str(e))
            raise  # triggers transaction rollback

        return results

    # =========================================================================
    # STEP 1: ACCOUNT TYPES
    # =========================================================================

    def _create_account_types(self):
        """Create the 5 standard GL account types (ASSET/LIABILITY/EQUITY/REVENUE/EXPENSE)."""
        AccountType   = apps.get_model('finance', 'AccountType')
        account_types = []

        for config in SchoolInitConfig.get_account_types():
            obj, created = AccountType.objects.get_or_create(
                code=config['code'],
                defaults=config,
            )
            account_types.append(obj)
            if created:
                logger.debug(f"  Created AccountType: {obj.name}")

        logger.info(f"  Account types: {len(account_types)} created/verified")
        return account_types

    # =========================================================================
    # STEP 2: CHART OF ACCOUNTS
    # =========================================================================

    def _create_chart_of_accounts(self):
        """Create GL accounts based on school complexity level."""
        Account     = apps.get_model('finance', 'Account')
        AccountType = apps.get_model('finance', 'AccountType')

        optional_fields = [
            'description', 'is_bank_account', 'is_cash_account',
            'is_receivable_account', 'is_payable_account', 'is_revenue_account',
            'is_expense_account', 'is_inventory_account', 'is_fixed_asset',
            'is_contra_account', 'is_loan_account', 'is_tax_account',
            'receivable_type', 'revenue_type', 'expense_type',
            'inventory_type', 'mobile_money_provider',
        ]

        accounts = []
        for account_data in self.config['chart_of_accounts']:
            account_type = AccountType.objects.get(account_type=account_data['type'])

            create_data = {
                'account_number': account_data['number'],
                'name':           account_data['name'],
                'account_type':   account_type,
                'is_active':      True,
            }
            for field in optional_fields:
                if field in account_data:
                    create_data[field] = account_data[field]

            obj, created = Account.objects.get_or_create(
                account_number=account_data['number'],
                defaults=create_data,
            )
            accounts.append(obj)
            if created:
                logger.debug(f"  Created account: {obj.account_number} {obj.name}")

        logger.info(f"  Accounts: {len(accounts)} created/verified ({self.complexity})")
        return accounts

    # =========================================================================
    # STEP 3: FINANCIAL SETTINGS
    # =========================================================================

    def _create_financial_settings(self):
        """Create FinancialSettings singleton if it doesn't exist."""
        FinancialSettings = apps.get_model('core', 'FinancialSettings')

        if FinancialSettings.objects.exists():
            logger.debug("  FinancialSettings already exists — skipping")
            return FinancialSettings.objects.first()

        settings = FinancialSettings.objects.create(**self.config['financial_settings'])
        logger.info(f"  Created FinancialSettings (currency={settings.school_currency})")
        return settings

    # =========================================================================
    # STEP 4a: CORE ACCOUNT MAPPINGS
    # =========================================================================

    def _create_account_mappings(self):
        """
        Create CoreAccountMappings — the Big 7 required accounts plus
        optional specialised accounts (petty cash, mobile money, etc.).

        The account numbers come from get_account_mappings_config(complexity),
        which is already complexity-aware — BASIC/STANDARD/ADVANCED each
        produce the correct bank and cash account numbers. No manual overrides
        are needed here.
        """
        CoreAccountMappings = apps.get_model('core', 'CoreAccountMappings')
        FinancialSettings   = apps.get_model('core', 'FinancialSettings')
        Account             = apps.get_model('finance', 'Account')

        fs = FinancialSettings.objects.first()
        if not fs:
            raise Exception("FinancialSettings must exist before CoreAccountMappings")

        try:
            existing = CoreAccountMappings.objects.get(financial_settings=fs)
            logger.debug("  CoreAccountMappings already exists — skipping")
            return existing
        except CoreAccountMappings.DoesNotExist:
            pass

        mapping_data    = {'financial_settings': fs}
        mappings_config = self.config['account_mappings']  # complexity-aware

        for field_name, config in mappings_config.items():
            account = Account.objects.filter(**config['search']).first()

            if not account and 'fallback' in config:
                account = Account.objects.filter(**config['fallback']).first()

            if not account and config.get('optional', False):
                logger.debug(f"  Optional mapping not found: {field_name} — skipping")
                continue

            if not account:
                raise Exception(
                    f"Required account for '{field_name}' not found. "
                    f"Search criteria: {config['search']}"
                )

            mapping_data[field_name] = account

        mappings = CoreAccountMappings.objects.create(**mapping_data)
        logger.info(
            f"  Created CoreAccountMappings ({len(mapping_data) - 1} accounts mapped)"
        )
        return mappings

    # =========================================================================
    # STEP 4b: SPECIALIZED ACCOUNT MAPPINGS
    # =========================================================================

    def _create_specialized_account_mappings(self):
        """
        Create PayrollAccountMappings, ExpenseAccountMappings,
        RevenueAccountMappings, and SpecialAccountMappings.

        All fields on these models are null=True — accounts that don't exist
        in a simpler chart silently become None rather than raising an error.

        ACCOUNT NUMBER CROSS-REFERENCE BY COMPLEXITY
        ─────────────────────────────────────────────
        Number  BASIC                STANDARD                   ADVANCED
        ──────  ──────────────────── ─────────────────────────  ────────────────────────────
        1140    —                    —                          Allowance for Doubtful Accts
        1200    —                    Inventory - Supplies       Inventory - General Supplies
        2010    —                    Salaries Payable           Salaries Payable
        2020    —                    Tax Payable                PAYE Tax Payable
        2030    —                    Student Deposits (!)       NSSF Payable        ← key diff
        2050    —                    Student Deposits           Student Deposits
        2060    —                    —                          Advance Fee Payments
        4100    (boarding only)      (boarding only)            Boarding Fees
        4110    (boarding only)      (boarding only)            Meals Revenue
        4200    —                    Uniform & Book Sales       Uniform Sales
        4220    —                    —                          Transport Fees
        4300    —                    Transport Fees (!)         Late Payment Fees   ← key diff
        4310    —                    —                          Replacement Fees
        5000    Salaries & Wages     Teaching Staff Salaries    Teaching Staff Basic Salary
        5010    —                    Admin Salaries             Housing Allowance
        5020    —                    Support Staff Salaries     Transport Allowance
        5060    —                    —                          Staff Medical Insurance
        5100    Utilities            Electricity                Electricity
        5300    Maintenance          Building Maintenance       Building Maintenance
        5820    —                    —                          Bad Debt Write-off
        5850    —                    —                          Depreciation - Buildings

        BUGS FIXED vs ORIGINAL
        ──────────────────────
        late_fee_revenue_account
            Original: acct('4300') if complexity != 'ADVANCED' else acct('4300')
            Both branches identical — condition was meaningless.
            In STANDARD, 4300 = Transport Fees (wrong for late fee revenue).
            Fixed: ADVANCED only gets 4300 (Late Payment Fees); others get None.

        social_security_payable_account
            Original used acct('2030') for ALL complexities.
            In STANDARD, 2030 = Student Deposits — completely wrong for payroll.
            Fixed: 2030 only for ADVANCED (where it = NSSF Payable); others None.

        NEW: penalty_revenue_account
            Maps to 4310 (Replacement Fees) in ADVANCED; None elsewhere.

        NOTE: student_credit_balance_account and unearned_revenue_account both
        intentionally map to 2060 (Advance Fee Payments) — the closest liability
        account for pre-paid and overpaid amounts in ADVANCED.
        """
        FinancialSettings      = apps.get_model('core', 'FinancialSettings')
        PayrollAccountMappings = apps.get_model('core', 'PayrollAccountMappings')
        ExpenseAccountMappings = apps.get_model('core', 'ExpenseAccountMappings')
        RevenueAccountMappings = apps.get_model('core', 'RevenueAccountMappings')
        SpecialAccountMappings = apps.get_model('core', 'SpecialAccountMappings')
        Account                = apps.get_model('finance', 'Account')

        fs = FinancialSettings.objects.first()
        if not fs:
            raise Exception("FinancialSettings must exist before specialised mappings")

        def acct(number):
            """Return Account by number, or None if absent from this chart."""
            return Account.objects.filter(account_number=number).first()

        is_advanced   = self.complexity == 'ADVANCED'
        is_std_or_adv = self.complexity in ('STANDARD', 'ADVANCED')

        # ── Payroll Account Mappings ──────────────────────────────────────────
        pm, created = PayrollAccountMappings.objects.get_or_create(financial_settings=fs)
        if created:
            pm.salaries_expense_account = acct('5000')  # ALL complexities

            # 2010 = Salaries Payable — STANDARD + ADVANCED; absent in BASIC
            pm.wages_payable_account = acct('2010')

            # 2020 = Tax Payable (STANDARD) / PAYE Tax Payable (ADVANCED)
            pm.payroll_tax_payable_account = acct('2020')

            # FIX: 2030 = NSSF Payable only in ADVANCED.
            # In STANDARD, 2030 = Student Deposits — wrong for social security.
            pm.social_security_payable_account = acct('2030') if is_advanced else None

            # 5010 = Admin Salaries (STANDARD) / Housing Allowance (ADVANCED)
            pm.housing_allowance_expense_account = acct('5010')

            # 5020 = Support Staff (STANDARD) / Transport Allowance (ADVANCED)
            pm.transport_allowance_expense_account = acct('5020')

            # 5060 = Staff Medical Insurance — ADVANCED only; None elsewhere
            pm.staff_benefits_expense_account = acct('5060')

            pm.save()
            logger.info("  Created PayrollAccountMappings")
        else:
            logger.debug("  PayrollAccountMappings already exists — skipping")

        # ── Expense Account Mappings ──────────────────────────────────────────
        em, created = ExpenseAccountMappings.objects.get_or_create(financial_settings=fs)
        if created:
            # 1200 = Inventory - Supplies (STANDARD) / General Supplies (ADVANCED)
            em.default_inventory_account = acct('1200')

            # 5100 = Utilities (BASIC) / Electricity (STANDARD + ADVANCED)
            em.utilities_expense_account = acct('5100')

            # 5300 = Maintenance & Repairs (BASIC) / Building Maintenance (STD + ADV)
            em.maintenance_expense_account = acct('5300')

            # 5850 = Depreciation - Buildings — ADVANCED only; None elsewhere
            em.depreciation_expense_account = acct('5850')

            em.save()
            logger.info("  Created ExpenseAccountMappings")
        else:
            logger.debug("  ExpenseAccountMappings already exists — skipping")

        # ── Revenue Account Mappings ──────────────────────────────────────────
        rm, created = RevenueAccountMappings.objects.get_or_create(financial_settings=fs)
        if created:
            # 4100 = Boarding Fees — all complexities (boarding schools only)
            rm.boarding_revenue_account = acct('4100')

            # 4110 = Meals Revenue — all complexities (boarding schools only)
            rm.meals_revenue_account = acct('4110')

            # 4200 = Uniform & Book Sales (STANDARD) / Uniform Sales (ADVANCED)
            rm.uniform_sales_revenue_account = acct('4200')

            # Transport: 4220 in ADVANCED; 4300 in STANDARD (both = Transport Fees)
            # acct('4220') returns None on STANDARD so falls through to acct('4300')
            rm.transport_revenue_account = acct('4220') or acct('4300')

            # FIX: 4300 = Transport Fees in STANDARD — wrong for late fee revenue.
            #      4300 = Late Payment Fees in ADVANCED — correct.
            # Original had acct('4300') on BOTH sides of the ternary (meaningless).
            rm.late_fee_revenue_account = acct('4300') if is_advanced else None

            # NEW: 4310 = Replacement Fees — ADVANCED only; None elsewhere
            rm.penalty_revenue_account = acct('4310')

            rm.save()
            logger.info("  Created RevenueAccountMappings")
        else:
            logger.debug("  RevenueAccountMappings already exists — skipping")

        # ── Special Account Mappings ──────────────────────────────────────────
        sm, created = SpecialAccountMappings.objects.get_or_create(financial_settings=fs)
        if created:
            # 2050 = Student Deposits — STANDARD + ADVANCED; absent in BASIC
            sm.default_student_deposit_account = acct('2050')

            # 2060 = Advance Fee Payments — ADVANCED only.
            # Both credit balance and unearned revenue map here intentionally;
            # it is the closest liability account for pre-paid / overpaid amounts.
            sm.student_credit_balance_account = acct('2060')
            sm.unearned_revenue_account       = acct('2060')

            # 5820 = Bad Debt Write-off — ADVANCED only; None elsewhere
            sm.bad_debt_expense_account = acct('5820')

            # 1140 = Allowance for Doubtful Accounts — ADVANCED only; None elsewhere
            sm.allowance_for_doubtful_accounts = acct('1140')

            sm.save()
            logger.info("  Created SpecialAccountMappings")
        else:
            logger.debug("  SpecialAccountMappings already exists — skipping")

    # =========================================================================
    # STEP 5: DISPLAY GROUPS
    # =========================================================================

    def _create_display_groups(self):
        """Create fee invoice display groups."""
        DisplayGroup = apps.get_model('fees', 'DisplayGroup')
        groups = []

        for group_data in self.config['display_groups']:
            group_data = group_data.copy()
            name = group_data.pop('name')
            obj, _ = DisplayGroup.objects.get_or_create(name=name, defaults=group_data)
            groups.append(obj)

        logger.info(f"  Display groups: {len(groups)} created/verified")
        return groups

    # =========================================================================
    # STEP 6: FEE CATEGORIES
    # =========================================================================

    def _create_fee_categories(self):
        """
        Create fee categories mapped to display groups.

        display_group is stored as a string name in the config. It is resolved
        to a DisplayGroup instance here after display groups have been seeded
        (Phase 2 creates them before fee categories).

        A warning is logged — not an error — when a group name is not found,
        because validate_config() in Phase 0 would have caught true mismatches.
        """
        FeesCategory = apps.get_model('fees', 'FeesCategory')
        DisplayGroup = apps.get_model('fees', 'DisplayGroup')

        display_groups_map = {dg.name: dg for dg in DisplayGroup.objects.all()}
        categories = []

        for category_data in self.config['fee_categories']:
            category_data      = category_data.copy()
            display_group_name = category_data.pop('display_group', None)
            code               = category_data.pop('code')

            if display_group_name:
                category_data['display_group'] = display_groups_map.get(display_group_name)
                if not category_data['display_group']:
                    logger.warning(
                        f"  Display group '{display_group_name}' not found "
                        f"for fee category '{code}'"
                    )
            else:
                category_data['display_group'] = None

            obj, _ = FeesCategory.objects.get_or_create(code=code, defaults=category_data)
            categories.append(obj)

        logger.info(f"  Fee categories: {len(categories)} created/verified")
        return categories

    # =========================================================================
    # STEP 7: EXPENSE CATEGORIES
    # =========================================================================

    def _create_expense_categories(self):
        """
        Create expense categories and wire each one to a default GL expense
        account — exactly as QuickBooks does at item/category setup time.

        ACCOUNT PRIORITY LISTS
        ──────────────────────
        Each category_type maps to an ordered list of account numbers.
        The first number that exists in the DB wins, so the mapping
        degrades gracefully across complexity levels:

          ADVANCED  → finds specific accounts (5720, 5920, 5910, …)
          STANDARD  → finds intermediate accounts (5300, 5500, 5600, …)
          BASIC     → falls through to catch-all

        CATCH-ALL LOGIC
        ───────────────
        BASIC/STANDARD: 5900 = Other Expenses (correct catch-all)
        ADVANCED:       5990 = Miscellaneous Expenses (correct catch-all)
                        5900 = Entertainment & Events (wrong as catch-all)
        So ADVANCED tries 5990 first; BASIC/STANDARD try 5900 first.

        CROSS-REFERENCE: Account numbers by complexity level
        ─────────────────────────────────────────────────────
        Number  BASIC              STANDARD                    ADVANCED
        ──────  ─────────────────  ──────────────────────────  ─────────────────────────────
        5000    Salaries & Wages   Teaching Staff Salaries     Teaching Staff Basic Salary
        5100    Utilities          Electricity                 Electricity
        5200    Supplies           Office Supplies             Textbooks & Learning Mats
        5210    —                  Learning Materials          Stationery & Office Supplies
        5220    —                  Cleaning Supplies           Laboratory Supplies
        5240    —                  —                           Computer Software & Licenses
        5300    Maintenance        Building Maintenance        Building Maintenance
        5310    —                  Equipment Repairs           Equipment Repairs
        5340    —                  —                           Cleaning Supplies
        5400    —                  Security Services           Security Services
        5500    —                  Transport & Fuel            Fuel & Oil
        5510    —                  —                           Vehicle Maintenance & Repairs
        5600    Boarding Expenses  Professional Fees (!)       Food & Provisions
        5610    —                  Food & Provisions (board.)  Kitchen Supplies & Equipment
        5700    —                  Insurance                   Advertising & Marketing
        5710    —                  —                           Printing & Publications
        5720    —                  —                           Legal & Professional Fees
        5730    —                  —                           Audit Fees
        5740    —                  —                           Bank Charges & Fees
        5760    —                  —                           Insurance - General
        5800    Scholarships       Scholarships & Discounts    Scholarships & Bursaries
        5820    —                  —                           Bad Debt Write-off
        5850    —                  —                           Depreciation - Buildings
        5900    Other Expenses     Other Expenses              Entertainment & Events (!)
        5910    —                  —                           Sports & Recreation
        5920    —                  —                           Medical Supplies
        5930    —                  —                           Interest Expense
        5990    —                  —                           Miscellaneous Expenses

        NOTE: 5600 = Professional Fees in STANDARD but Food & Provisions in
        ADVANCED. The MEALS priority list deliberately tries 5610 before 5600
        so ADVANCED boarding schools hit Food & Provisions correctly, and
        STANDARD non-boarding schools only fall through to 5600 as a last
        resort — acceptable since they won't have meaningful food records.
        """
        ExpenseCategory = apps.get_model('finance', 'ExpenseCategory')
        Account         = apps.get_model('finance', 'Account')

        if self.complexity == 'ADVANCED':
            CATCH_ALL = ['5990', '5900']
        else:
            CATCH_ALL = ['5900', '5990']

        CATEGORY_ACCOUNT_PRIORITY = {
            'ADMINISTRATIVE': ['5210', '5200', '5740', '5900', '5990'],
            'ACADEMIC':       ['5200', '5210', '5070', '5900', '5990'],
            'SCHOLASTIC':     ['5200', '5210', '5220', '5230', '5900', '5990'],
            'EXAMINATION':    ['5200', '5210', '5900', '5990'],
            'FACILITIES':     ['5300', '5310', '5340', '5400', '5900', '5990'],
            'CAPITAL':        CATCH_ALL,
            'UTILITIES':      ['5100', '5110', '5120', '5130', '5900', '5990'],
            'TRANSPORT':      ['5500', '5510', '5900', '5990'],
            'MEALS':          ['5610', '5600', '5900', '5990'],
            'STAFF':          ['5000', '5010', '5030', '5900', '5990'],
            'MEDICAL':        ['5920', '5900', '5990'],
            'SPORTS':         ['5910', '5900', '5990'],
            'STUDENT_SERVICES': CATCH_ALL,
            'PTA':            CATCH_ALL,
            'MARKETING':      ['5700', '5710', '5900', '5990'],
            'TECHNOLOGY':     ['5240', '5200', '5210', '5900', '5990'],
            'LEGAL':          ['5720', '5730', '5600', '5900', '5990'],
            'FINANCIAL':      ['5740', '5930', '5900', '5990'],
            'INSURANCE':      ['5760', '5700', '5520', '5900', '5990'],
            'TAX':            CATCH_ALL,
            'DEPRECIATION':   ['5850', '5851', '5852', '5853', '5854', '5900', '5990'],
            'DRAWINGS':       CATCH_ALL,
            'CHARITY':        ['5800', '5900', '5990'],
            'MISCELLANEOUS':  ['5820', '5900', '5990'],
            'OTHER':          CATCH_ALL,
        }

        # Pre-fetch every potentially needed account in a single query
        all_needed_numbers = set()
        for numbers in CATEGORY_ACCOUNT_PRIORITY.values():
            all_needed_numbers.update(numbers)

        account_cache = {
            a.account_number: a
            for a in Account.objects.filter(
                account_number__in=all_needed_numbers,
                is_active=True,
                is_header=False,
            )
        }

        def resolve_account(category_type):
            for number in CATEGORY_ACCOUNT_PRIORITY.get(category_type, CATCH_ALL):
                account = account_cache.get(number)
                if account:
                    return account
            return None

        categories = []
        wired      = 0
        backfilled = 0

        for category_data in self.config['expense_categories']:
            category_data = category_data.copy()
            name          = category_data.pop('name')
            category_type = category_data.get('category_type')

            account = resolve_account(category_type)
            if account:
                category_data['default_expense_account'] = account

            obj, created = ExpenseCategory.objects.get_or_create(
                name=name,
                defaults=category_data,
            )

            if created and account:
                wired += 1
            elif not created and not obj.default_expense_account and account:
                obj.default_expense_account = account
                obj.save(update_fields=['default_expense_account'])
                backfilled += 1

            categories.append(obj)

        logger.info(
            f"  Expense categories: {len(categories)} created/verified — "
            f"{wired} wired, {backfilled} back-filled ({self.complexity})"
        )
        return categories

    # =========================================================================
    # STEP 8: JOURNALS
    # =========================================================================

    def _create_journals(self):
        """Create accounting journals (General, Fees, Expenses, Cash, Bank, Payroll, Adjustments)."""
        Journal  = apps.get_model('finance', 'Journal')
        journals = []

        for journal_data in self.config['journals']:
            journal_data = journal_data.copy()
            name = journal_data.pop('name')
            obj, _ = Journal.objects.get_or_create(name=name, defaults=journal_data)
            journals.append(obj)

        logger.info(f"  Journals: {len(journals)} created/verified")
        return journals

    # =========================================================================
    # STEP 9: FISCAL YEAR AND PERIODS
    # =========================================================================

    def _create_fiscal_year(self):
        """
        Create a fiscal year and term-based fiscal periods for the current year.

        PERIOD TYPE FIX
        ───────────────
        Was period_type='TERM'. 'TERM' is not in FiscalPeriod.PERIOD_TYPE_CHOICES.
        FiscalPeriod.save() calls full_clean(), which rejects invalid choices and
        raises ValidationError — preventing any period from being saved.
        Fixed to 'ACADEMIC_ALIGNED'.

        DATE CONSTRUCTION FIX
        ─────────────────────
        Was timezone.datetime(year, month, day).date(). Django's timezone module
        does not expose datetime as an attribute; this raised AttributeError.
        Fixed to _date(year, month, day) from stdlib datetime.date (imported at
        module level as _date).

        PERIODS
        ───────
        Creates term-based periods aligned to the school's academic calendar.
        Periods are left OPEN (is_closed=False) so historical data can be entered
        without journal-entry permission errors on a fresh database.
        """
        FiscalYear          = apps.get_model('core', 'FiscalYear')
        FiscalPeriod        = apps.get_model('core', 'FiscalPeriod')
        SchoolConfiguration = apps.get_model('core', 'SchoolConfiguration')

        current_year = timezone.now().year

        fiscal_year, fy_created = FiscalYear.objects.get_or_create(
            code=f'AY{current_year}',
            defaults={
                'name':       f'FY {current_year}',
                'start_date': _date(current_year, 1, 1),    # FIX: was timezone.datetime(...)
                'end_date':   _date(current_year, 12, 31),  # FIX: was timezone.datetime(...)
                'is_active':  True,
                'is_closed':  False,
                'status':     'ACTIVE',
            }
        )
        if fy_created:
            logger.debug(f"  Created FiscalYear: {fiscal_year.name}")

        # Determine number of periods from SchoolConfiguration
        try:
            school_config   = SchoolConfiguration.get_instance()
            periods_count   = school_config.get_period_count()
            get_period_name = lambda i: school_config.get_period_name(
                i, include_year=True, academic_year=current_year
            )
        except Exception:
            periods_count   = 3
            get_period_name = lambda i: f"Term {i} {current_year}"

        months_per_period = 12 // periods_count
        periods           = []

        for period_num in range(1, periods_count + 1):
            start_month = (period_num - 1) * months_per_period + 1
            end_month   = (
                period_num * months_per_period
                if period_num < periods_count
                else 12
            )

            start_date = _date(current_year, start_month, 1)       # FIX: was timezone.datetime(...)
            last_day   = _calendar.monthrange(current_year, end_month)[1]
            end_date   = _date(current_year, end_month, last_day)  # FIX: was timezone.datetime(...)

            period, created = FiscalPeriod.objects.get_or_create(
                code=f'FP_{current_year}_T{period_num}',
                defaults={
                    'fiscal_year':   fiscal_year,
                    'name':          get_period_name(period_num),
                    'period_number': Decimal(str(period_num)),
                    # FIX: was 'TERM' — not in PERIOD_TYPE_CHOICES; full_clean() rejected it.
                    'period_type':   'ACADEMIC_ALIGNED',
                    'start_date':    start_date,
                    'end_date':      end_date,
                    'is_active':     True,
                    'is_closed':     False,  # Always open — avoids JE creation errors
                    'status':        'ACTIVE',
                }
            )
            periods.append(period)
            if created:
                logger.debug(f"  Created FiscalPeriod: {period.name}")

        logger.info(
            f"  Fiscal periods: {len(periods)} created/verified for {current_year}"
        )
        return periods

    # =========================================================================
    # STEP 10: PAYMENT METHODS
    # =========================================================================

    def _create_payment_methods(self):
        """Create payment methods (Cash, Bank Transfer, Mobile Money, Card, Cheque)."""
        PaymentMethod = apps.get_model('core', 'PaymentMethod')
        methods       = []

        for method_data in self.config['payment_methods']:
            method_data = method_data.copy()
            code = method_data.pop('code')
            obj, _ = PaymentMethod.objects.get_or_create(code=code, defaults=method_data)
            methods.append(obj)

        logger.info(f"  Payment methods: {len(methods)} created/verified")
        return methods

    # =========================================================================
    # STEP 11: TAX RATES
    # =========================================================================

    def _create_tax_rates(self):
        """Create country-specific tax rates."""
        TaxRate = apps.get_model('core', 'TaxRate')
        rates   = []

        for rate_data in self.config['tax_rates']:
            rate_data      = rate_data.copy()
            name           = rate_data.pop('name')
            tax_type       = rate_data.get('tax_type')
            effective_from = rate_data.get('effective_from')

            obj, _ = TaxRate.objects.get_or_create(
                tax_type=tax_type,
                effective_from=effective_from,
                defaults={'name': name, **rate_data},
            )
            rates.append(obj)

        logger.info(f"  Tax rates: {len(rates)} created/verified")
        return rates

    # =========================================================================
    # STEP 12: DEPARTMENTS
    # =========================================================================

    def _create_departments(self):
        """Create organisational departments."""
        Department  = apps.get_model('hr', 'Department')
        departments = []

        for dept_data in self.config['departments']:
            dept_data = dept_data.copy()
            code = dept_data.pop('code')
            obj, _ = Department.objects.get_or_create(code=code, defaults=dept_data)
            departments.append(obj)

        logger.info(f"  Departments: {len(departments)} created/verified")
        return departments

    # =========================================================================
    # STEP 13: DESIGNATIONS
    # =========================================================================

    def _create_designations(self):
        """
        Create job designations linked to departments.

        Designations whose department_code is not found are logged and skipped
        rather than raising, so a partially failed department creation does not
        block all remaining designations.
        """
        Designation = apps.get_model('hr', 'Designation')
        Department  = apps.get_model('hr', 'Department')

        dept_map     = {d.code: d for d in Department.objects.all()}
        designations = []
        skipped      = 0

        for desig_data in self.config['designations']:
            desig_data = desig_data.copy()
            dept_code  = desig_data.pop('department_code')
            desig_code = desig_data.pop('code')

            department = dept_map.get(dept_code)
            if not department:
                logger.warning(
                    f"  Department '{dept_code}' not found — "
                    f"skipping designation '{desig_data.get('name')}'"
                )
                skipped += 1
                continue

            desig_data['department'] = department
            obj, _ = Designation.objects.get_or_create(
                code=desig_code, defaults=desig_data
            )
            designations.append(obj)

        if skipped:
            logger.warning(
                f"  Designations: {len(designations)} created/verified, "
                f"{skipped} skipped (missing departments)"
            )
        else:
            logger.info(f"  Designations: {len(designations)} created/verified")

        return designations

    # =========================================================================
    # STEP 14: UNITS OF MEASURE
    # =========================================================================

    def _create_units_of_measure(self):
        """
        Create units of measure for inventory and procurement.

        FIX: Was using symbol as the get_or_create lookup key. symbol is
        nullable (null=True) and not unique on the model. Using a nullable
        non-unique field as the lookup key causes None→None collisions across
        multiple records. Fixed to abbreviation, which is always populated.
        """
        UnitOfMeasure = apps.get_model('core', 'UnitOfMeasure')
        units         = []

        for unit_data in self.config['units_of_measure']:
            unit_data    = unit_data.copy()
            abbreviation = unit_data.get('abbreviation')

            if not abbreviation:
                logger.warning(f"  Unit missing abbreviation — skipping: {unit_data}")
                continue

            obj, _ = UnitOfMeasure.objects.get_or_create(
                abbreviation=abbreviation,  # FIX: was symbol (nullable, non-unique)
                defaults=unit_data,
            )
            units.append(obj)

        logger.info(f"  Units of measure: {len(units)} created/verified")
        return units


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

def initialize_school(school, user=None):
    """
    Initialize a school's complete financial system.
    Idempotent — safe to run multiple times.

    Args:
        school: School instance
        user:   User performing initialization (optional, for audit trail)

    Returns:
        dict: Results with 'success', 'errors', and 'created' counts.

    Raises:
        Exception: If initialization fails (transaction is rolled back).
    """
    try:
        initializer = SchoolInitializer(school)
        return initializer.initialize_all(user=user)
    except Exception as e:
        logger.error(f"Failed to initialize {school.full_name}: {e}")
        raise


# =============================================================================
# VALIDATION HELPERS
# =============================================================================

def validate_school_can_be_initialized(school):
    """
    Check whether a school is ready for initialization.

    Returns:
        tuple[bool, str]: (can_initialize, reason)
    """
    if school.is_initial_setup_complete:
        return False, "School is already initialized"

    if not school.is_active_subscription:
        return False, "School subscription is not active"

    from django.conf import settings
    if school.database_alias not in settings.DATABASES:
        return False, f"Database '{school.database_alias}' not configured in settings"

    return True, "School can be initialized"


def get_initialization_preview(school):
    """
    Return a summary of what will be created during initialization.
    Also runs validate_config() so callers can surface config problems
    before committing to a run.

    Returns:
        dict: Counts, configuration details, config_issues, config_valid.
    """
    config = SchoolInitConfig.get_init_config(school)
    issues = SchoolInitConfig.validate_config()

    return {
        'complexity':               config['complexity'],
        'accounts_count':           len(config['chart_of_accounts']),
        'fee_categories_count':     len(config['fee_categories']),
        'expense_categories_count': len(config['expense_categories']),
        'journals_count':           len(config['journals']),
        'display_groups_count':     len(config['display_groups']),
        'payment_methods_count':    len(config['payment_methods']),
        'departments_count':        len(config['departments']),
        'designations_count':       len(config['designations']),
        'units_of_measure_count':   len(config['units_of_measure']),
        'tax_rates_count':          len(config['tax_rates']),
        'currency':                 config['financial_settings']['school_currency'],
        'needs_boarding':           config['needs_boarding'],
        'school_type':              school.school_type,
        'student_capacity':         school.student_capacity,
        # NEW: surface config issues so callers can warn the user before running
        'config_issues':            issues,
        'config_valid':             len(issues) == 0,
    }


# =============================================================================
# CLEANUP AND RE-INITIALIZATION
# =============================================================================

@transaction.atomic
def cleanup_school_initialization(school):
    """
    Delete all initialization data for a school.

    WARNING: Destructive. Use only for testing or fixing broken setups.

    Returns:
        dict: Counts of deleted records per model.
    """
    logger.warning(f"CLEANUP starting for {school.full_name}")

    deleted = {k: 0 for k in [
        'designations', 'departments', 'units_of_measure', 'tax_rates',
        'payment_methods', 'fiscal_periods', 'journals', 'expense_categories',
        'fee_categories', 'display_groups', 'accounts',
    ]}

    model_steps = [
        ('hr',      'Designation',     'designations'),
        ('hr',      'Department',      'departments'),
        ('core',    'UnitOfMeasure',   'units_of_measure'),
        ('core',    'TaxRate',         'tax_rates'),
        ('core',    'PaymentMethod',   'payment_methods'),
        ('core',    'FiscalPeriod',    'fiscal_periods'),
        ('finance', 'Journal',         'journals'),
        ('finance', 'ExpenseCategory', 'expense_categories'),
        ('fees',    'FeesCategory',    'fee_categories'),
        ('fees',    'DisplayGroup',    'display_groups'),
        ('finance', 'Account',         'accounts'),
    ]

    for app, model_name, key in model_steps:
        try:
            Model        = apps.get_model(app, model_name)
            count, _     = Model.objects.all().delete()
            deleted[key] = count
            if count:
                logger.info(f"  Deleted {count} {model_name}")
        except Exception as e:
            logger.error(f"  Error deleting {model_name}: {e}")

    # Singleton / mapping models — order matters (FKs point inward)
    for app, model_name in [
        ('core',    'PayrollAccountMappings'),
        ('core',    'ExpenseAccountMappings'),
        ('core',    'RevenueAccountMappings'),
        ('core',    'SpecialAccountMappings'),  # NEW: was missing from original
        ('core',    'CoreAccountMappings'),
        ('core',    'FinancialSettings'),
        ('core',    'FiscalYear'),
        ('finance', 'AccountType'),
    ]:
        try:
            apps.get_model(app, model_name).objects.all().delete()
        except Exception as e:
            logger.error(f"  Error deleting {model_name}: {e}")

    school.is_financial_setup_complete = False
    school.is_initial_setup_complete   = False
    school.setup_completed_at          = None
    school.setup_completed_by          = None
    school.save(using='default')

    logger.warning(f"CLEANUP complete for {school.full_name}: {deleted}")
    return deleted


@transaction.atomic
def reinitialize_school(school, user=None):
    """
    Clean up then re-initialize a school. DESTRUCTIVE.

    Returns:
        dict: Initialization results.
    """
    logger.warning(f"RE-INITIALIZATION starting for {school.full_name}")
    cleanup_school_initialization(school)
    result = initialize_school(school, user=user)
    logger.warning(f"RE-INITIALIZATION complete for {school.full_name}")
    return result