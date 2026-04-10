# core/services/school_init_config.py
"""
School Initialization Configuration
=====================================
Centralises all default seed data for school initialisation.
One record per section — the init command reads this and creates DB records.

USAGE
-----
    from core.services.school_init_config import SchoolInitConfig

    config = SchoolInitConfig.get_init_config(school)

    # Validate before using (raises AssertionError on first failure)
    issues = SchoolInitConfig.validate_config()
    if issues:
        for issue in issues:
            print(issue)

CHANGES FROM ORIGINAL
---------------------
get_account_mappings_config()
    Now accepts a `complexity` parameter. Account numbers are complexity-aware
    so the correct accounts are found for BASIC, STANDARD, and ADVANCED charts.

    BASIC:    bank=1000, cash=1010 (was bank=1020/cash=1000 — wrong for basic)
    STANDARD: bank=1000, cash=1010, mobile_money=1020
    ADVANCED: bank=1020, cash=1000, petty_cash=1010, mobile_money=1030

    boarding_expense account numbers also corrected per complexity:
    BASIC: 5600, STANDARD: 5610, ADVANCED: 5600

get_init_config()
    Passes complexity to get_account_mappings_config().

get_designations()
    Three designation codes clashed with department codes. Fixed:
    'School Administrator'  ADMIN    → SCH_ADMIN
    'School Counselor'      COUNSEL  → SCHL_COUNSEL
    'Security Guard'        SECURITY → SEC_GUARD

get_display_groups()
    Added 'PTA & Community' (display_order=12) for PTA-related fee categories.

get_fee_categories()
    Applicability values corrected to match FeesCategory.APPLICABILITY_CHOICES:
        APPLICANTS → NEW_STUDENTS    (Application Fee)

    category_type values improved:
        Academic Enhancement Fee  OTHER → TUITION
        Application Fee           OTHER → REGISTRATION
        Accommodation Deposit     OTHER → DEPOSIT   ← routes to LIABILITY account
        Stationery Pack           OTHER → BOOKS
        Remedial Classes          OTHER → TUITION

    is_refundable added explicitly where it differs from model default (True):
        Registration, Admission, Application, Graduation, PTA Levy,
        Late Payment Penalty, School Leaving Certificate → False

    New categories added (with correct types from updated FeesCategory):
        PTA Levy                  (PTA,         TERMLY,       ALL)
        Caution Money Deposit     (DEPOSIT,      ONE_TIME,     ALL)
        Sports Kit / PE Uniform   (UNIFORM,      YEARLY,       ALL)
        Re-examination Fee        (EXAM,         PER_INCIDENT, ALL)
        Mental Health Counseling  (MEDICAL,      TERMLY,       OPTIONAL)
        School Photos             (PHOTO,        YEARLY,       ALL)
        School Magazine/Yearbook  (PUBLICATION,  YEARLY,       ALL)
        School Leaving Cert       (OTHER,        ONE_TIME,     CONTINUING_STUDENTS)

get_payment_methods()
    Added missing fields:
        requires_reference=True for BANK_TRANSFER and CHECK
        minimum_amount / maximum_amount for mobile money methods
        processing_time for all methods

get_units_of_measure()
    Added school-practical units missing from original:
        Jerrycan (20 L volume), Gross (144 qty), Tray (qty),
        Portion / Serving (qty), Dose / Tablet / Capsule (qty),
        Lesson / Period (service/time unit)

validate_config()
    New classmethod. Checks display_group name consistency, applicability
    validity, category_type validity, frequency validity, designation code
    uniqueness, and designation department_code existence.
"""

from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


class SchoolInitConfig:
    """Configuration class for school initialisation data."""

    # =========================================================================
    # VALID CHOICE SETS — mirrors the model choices for validation
    # =========================================================================

    _VALID_APPLICABILITY = {
        'ALL', 'DAY_SCHOLARS', 'BOARDERS', 'WEEKLY_BOARDERS', 'FULL_BOARDERS',
        'FLEXI_BOARDERS', 'NEW_STUDENTS', 'CONTINUING_STUDENTS',
        'SCHOLARSHIP_STUDENTS', 'TRANSPORT_USERS', 'SCIENCE_STUDENTS',
        'ICT_STUDENTS', 'PARTICIPANTS', 'DEFAULTERS', 'OPTIONAL',
    }

    _VALID_CATEGORY_TYPES = {
        'TUITION', 'EXAM', 'LABORATORY', 'LIBRARY', 'BOOKS', 'TECHNOLOGY',
        'BOARDING', 'MEALS', 'LAUNDRY', 'TRANSPORT', 'MEDICAL', 'INSURANCE',
        'SPORT', 'CLUB', 'FIELD_TRIP', 'UNIFORM', 'REGISTRATION', 'ADMISSION',
        'DEVELOPMENT', 'GRADUATION', 'PTA', 'DEPOSIT', 'LATE_PAYMENT', 'PENALTY',
        'PHOTO', 'PUBLICATION', 'MISCELLANEOUS', 'OTHER',
    }

    _VALID_FREQUENCIES = {
        'MONTHLY', 'TERMLY', 'YEARLY', 'ONE_TIME',
        'DAILY', 'WEEKLY', 'PER_INCIDENT',
    }

    # =========================================================================
    # COMPLEXITY DETERMINATION
    # =========================================================================

    @classmethod
    def determine_complexity(cls, school):
        """
        Auto-determine accounting complexity based on school characteristics.

        Returns 'BASIC', 'STANDARD', or 'ADVANCED'.
        """
        if school.accounting_complexity:
            return school.accounting_complexity
        if school.school_type in ['UNIVERSITY', 'COLLEGE']:
            return 'ADVANCED'
        if school.student_capacity >= 700:
            return 'ADVANCED'
        if school.student_capacity <= 200:
            return 'BASIC'
        if school.school_type in ['KINDERGARTEN', 'PRIMARY', 'KINDERGARTEN_PRIMARY']:
            return 'BASIC'
        return 'STANDARD'

    # =========================================================================
    # ACCOUNT TYPES
    # =========================================================================

    @classmethod
    def get_account_types(cls):
        """
        The 5 fundamental account types for double-entry bookkeeping.
        Must be created BEFORE chart of accounts during initialisation.
        """
        return [
            {
                'name': 'Assets', 'code': 'ASSET', 'account_type': 'ASSET',
                'description': (
                    'Resources owned or controlled by the school that provide future '
                    'economic benefits. Includes cash, bank accounts, receivables, '
                    'inventory, equipment, and property.'
                ),
                'normal_balance': 'DEBIT', 'affects_balance_sheet': True,
                'affects_income_statement': False, 'number_prefix': '1',
                'next_number': 1, 'display_order': 1,
                'icon': 'fa-coins', 'color': '#28a745',
                'is_active': True, 'requires_approval': False, 'allows_manual_entries': True,
            },
            {
                'name': 'Liabilities', 'code': 'LIABILITY', 'account_type': 'LIABILITY',
                'description': (
                    'Obligations and debts owed by the school to external parties. '
                    'Includes accounts payable, loans, accrued expenses, and student deposits.'
                ),
                'normal_balance': 'CREDIT', 'affects_balance_sheet': True,
                'affects_income_statement': False, 'number_prefix': '2',
                'next_number': 1, 'display_order': 2,
                'icon': 'fa-file-invoice', 'color': '#dc3545',
                'is_active': True, 'requires_approval': False, 'allows_manual_entries': True,
            },
            {
                'name': 'Equity', 'code': 'EQUITY', 'account_type': 'EQUITY',
                'description': (
                    'Net assets representing ownership interest in the school. '
                    'Includes capital contributions, retained earnings, and reserves.'
                ),
                'normal_balance': 'CREDIT', 'affects_balance_sheet': True,
                'affects_income_statement': False, 'number_prefix': '3',
                'next_number': 1, 'display_order': 3,
                'icon': 'fa-landmark', 'color': '#6f42c1',
                'is_active': True, 'requires_approval': False, 'allows_manual_entries': True,
            },
            {
                'name': 'Revenue', 'code': 'REVENUE', 'account_type': 'REVENUE',
                'description': (
                    'Income and earnings from school operations and activities. '
                    'Includes tuition fees, boarding fees, donations, and other income.'
                ),
                'normal_balance': 'CREDIT', 'affects_balance_sheet': False,
                'affects_income_statement': True, 'number_prefix': '4',
                'next_number': 1, 'display_order': 4,
                'icon': 'fa-dollar-sign', 'color': '#17a2b8',
                'is_active': True, 'requires_approval': False, 'allows_manual_entries': True,
            },
            {
                'name': 'Expenses', 'code': 'EXPENSE', 'account_type': 'EXPENSE',
                'description': (
                    'Operating costs and expenditures incurred in running the school. '
                    'Includes salaries, utilities, supplies, maintenance, and all other costs.'
                ),
                'normal_balance': 'DEBIT', 'affects_balance_sheet': False,
                'affects_income_statement': True, 'number_prefix': '5',
                'next_number': 1, 'display_order': 5,
                'icon': 'fa-file-invoice-dollar', 'color': '#fd7e14',
                'is_active': True, 'requires_approval': False, 'allows_manual_entries': True,
            },
        ]

    @classmethod
    def get_recommended_accounts_count(cls, complexity):
        return {'BASIC': 10, 'STANDARD': 25, 'ADVANCED': 60}.get(complexity, 25)

    # =========================================================================
    # CHART OF ACCOUNTS
    # =========================================================================

    @classmethod
    def get_chart_of_accounts(cls, school):
        complexity = cls.determine_complexity(school)
        if complexity == 'BASIC':
            return cls._get_basic_accounts(school)
        elif complexity == 'STANDARD':
            return cls._get_standard_accounts(school)
        return cls._get_advanced_accounts(school)

    @classmethod
    def _get_basic_accounts(cls, school):
        """
        Basic chart — ~13 accounts covering all 5 account types.

        ACCOUNT NUMBER LAYOUT (matches get_account_mappings_config BASIC):
          1000 = Main Bank Account   (default_bank_account)
          1010 = Cash on Hand        (default_cash_account)
        """
        accounts = [
            # ASSETS
            {'number': '1000', 'name': 'Main Bank Account',    'type': 'ASSET',     'is_bank_account': True,     'description': 'Primary bank account',            'is_active': True},
            {'number': '1010', 'name': 'Cash on Hand',         'type': 'ASSET',     'is_cash_account': True,     'description': 'Physical cash at school',          'is_active': True},
            {'number': '1100', 'name': 'Student Receivables',  'type': 'ASSET',     'is_receivable_account': True, 'receivable_type': 'STUDENT', 'description': 'Amounts owed by students', 'is_active': True},
            {'number': '1200', 'name': 'Supplies & Equipment', 'type': 'ASSET',     'description': 'School supplies and equipment',    'is_active': True},
            # LIABILITIES
            {'number': '2000', 'name': 'Accounts Payable',     'type': 'LIABILITY', 'is_payable_account': True,  'description': 'Amounts owed to vendors',          'is_active': True},
            {'number': '2050', 'name': 'Student Deposits',     'type': 'LIABILITY', 'description': 'Refundable student deposits/caution money', 'is_active': True},
            # EQUITY
            {'number': '3000', 'name': 'Capital',              'type': 'EQUITY',    'description': 'Owner capital and retained earnings',  'is_active': True},
            # REVENUE
            {'number': '4000', 'name': 'School Fees',          'type': 'REVENUE',   'is_revenue_account': True,  'revenue_type': 'TUITION',    'description': 'All school fees revenue',         'is_active': True},
            # EXPENSES
            {'number': '5000', 'name': 'Salaries & Wages',     'type': 'EXPENSE',   'is_expense_account': True,  'expense_type': 'TEACHING_SALARIES', 'description': 'All staff salaries and wages', 'is_active': True},
            {'number': '5100', 'name': 'Utilities',            'type': 'EXPENSE',   'is_expense_account': True,  'expense_type': 'UTILITIES',  'description': 'Electricity, water, internet',    'is_active': True},
            {'number': '5200', 'name': 'Supplies',             'type': 'EXPENSE',   'is_expense_account': True,  'description': 'School supplies and materials',   'is_active': True},
            {'number': '5300', 'name': 'Maintenance & Repairs','type': 'EXPENSE',   'is_expense_account': True,  'description': 'Building and equipment maintenance', 'is_active': True},
            {'number': '5800', 'name': 'Scholarships & Discounts', 'type': 'EXPENSE', 'is_expense_account': True, 'expense_type': 'SCHOLARSHIP', 'description': 'Student scholarships and fee discounts', 'is_active': True},
            {'number': '5900', 'name': 'Other Expenses',       'type': 'EXPENSE',   'is_expense_account': True,  'description': 'Miscellaneous operating expenses', 'is_active': True},
        ]
        if school.boarding_type in ('BOARDING', 'MIXED'):
            accounts += [
                {'number': '4100', 'name': 'Boarding Fees',     'type': 'REVENUE', 'is_revenue_account': True, 'revenue_type': 'BOARDING_REVENUE', 'description': 'Boarding and meals revenue',           'is_active': True},
                {'number': '5600', 'name': 'Boarding Expenses', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Food and boarding operational costs', 'is_active': True},
            ]
        return accounts

    @classmethod
    def _get_standard_accounts(cls, school):
        """
        Standard chart — ~35-40 accounts.

        ACCOUNT NUMBER LAYOUT (matches get_account_mappings_config STANDARD):
          1000 = Main Bank Account   (default_bank_account)
          1010 = Petty Cash          (default_cash_account / petty_cash_account)
          1020 = Mobile Money        (mobile_money_account)
        """
        accounts = [
            # ASSETS — Cash & Bank
            {'number': '1000', 'name': 'Main Bank Account',         'type': 'ASSET', 'is_bank_account': True,     'description': 'Primary bank account',             'is_active': True},
            {'number': '1010', 'name': 'Petty Cash',                'type': 'ASSET', 'is_cash_account': True,     'description': 'Petty cash fund',                  'is_active': True},
            {'number': '1020', 'name': 'Mobile Money',              'type': 'ASSET', 'description': 'Mobile money clearing account',     'is_active': True},
            {'number': '1030', 'name': 'Bank Account - Savings',    'type': 'ASSET', 'is_bank_account': True,     'description': 'Savings and reserve account',      'is_active': True},
            # ASSETS — Receivables
            {'number': '1100', 'name': 'Student Receivables',       'type': 'ASSET', 'is_receivable_account': True, 'receivable_type': 'STUDENT', 'description': 'Amounts owed by students', 'is_active': True},
            {'number': '1110', 'name': 'Staff Receivables',         'type': 'ASSET', 'is_receivable_account': True, 'receivable_type': 'STAFF', 'description': 'Staff loans and advances', 'is_active': True},
            # ASSETS — Other
            {'number': '1200', 'name': 'Inventory - Supplies',      'type': 'ASSET', 'description': 'School supplies inventory',         'is_active': True},
            {'number': '1210', 'name': 'Inventory - Uniforms & Books', 'type': 'ASSET', 'description': 'Uniforms and textbooks inventory', 'is_active': True},
            {'number': '1300', 'name': 'Equipment & Furniture',     'type': 'ASSET', 'description': 'School equipment and furniture',    'is_active': True},
            # LIABILITIES
            {'number': '2000', 'name': 'Accounts Payable',          'type': 'LIABILITY', 'is_payable_account': True, 'description': 'Amounts owed to vendors',       'is_active': True},
            {'number': '2010', 'name': 'Salaries Payable',          'type': 'LIABILITY', 'description': 'Accrued salaries not yet paid',  'is_active': True},
            {'number': '2020', 'name': 'Tax Payable',               'type': 'LIABILITY', 'description': 'PAYE and other taxes withheld',  'is_active': True},
            {'number': '2030', 'name': 'Student Deposits',          'type': 'LIABILITY', 'description': 'Refundable student deposits',    'is_active': True},
            # EQUITY
            {'number': '3000', 'name': 'Capital',                   'type': 'EQUITY', 'description': 'Owner capital contribution',       'is_active': True},
            {'number': '3100', 'name': 'Retained Earnings',         'type': 'EQUITY', 'description': 'Accumulated profits',              'is_active': True},
            # REVENUE
            {'number': '4000', 'name': 'Tuition Fees',              'type': 'REVENUE', 'is_revenue_account': True, 'revenue_type': 'TUITION',           'description': 'School tuition fees',      'is_active': True},
            {'number': '4010', 'name': 'Examination Fees',          'type': 'REVENUE', 'is_revenue_account': True, 'revenue_type': 'EXAM_FEES',         'description': 'Exam registration fees',   'is_active': True},
            {'number': '4200', 'name': 'Uniform & Book Sales',      'type': 'REVENUE', 'is_revenue_account': True, 'revenue_type': 'UNIFORM_SALES',     'description': 'Uniform and textbook sales', 'is_active': True},
            {'number': '4300', 'name': 'Transport Fees',            'type': 'REVENUE', 'is_revenue_account': True, 'revenue_type': 'TRANSPORT_REVENUE', 'description': 'School transport fees',    'is_active': True},
            {'number': '4400', 'name': 'Activity Fees',             'type': 'REVENUE', 'is_revenue_account': True, 'description': 'Sports and extracurricular fees',  'is_active': True},
            {'number': '4900', 'name': 'Other Income',              'type': 'REVENUE', 'is_revenue_account': True, 'description': 'Donations and miscellaneous income','is_active': True},
            # EXPENSES — Salaries
            {'number': '5000', 'name': 'Teaching Staff Salaries',   'type': 'EXPENSE', 'is_expense_account': True, 'expense_type': 'TEACHING_SALARIES', 'description': 'Teaching staff salaries',  'is_active': True},
            {'number': '5010', 'name': 'Administrative Salaries',   'type': 'EXPENSE', 'is_expense_account': True, 'expense_type': 'ADMIN_SALARIES',    'description': 'Administrative staff salaries', 'is_active': True},
            {'number': '5020', 'name': 'Support Staff Salaries',    'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Support and maintenance staff',   'is_active': True},
            {'number': '5030', 'name': 'Staff Allowances',          'type': 'EXPENSE', 'is_expense_account': True, 'expense_type': 'STAFF_BENEFITS',    'description': 'Housing, transport allowances',  'is_active': True},
            # EXPENSES — Utilities
            {'number': '5100', 'name': 'Electricity',               'type': 'EXPENSE', 'is_expense_account': True, 'expense_type': 'UTILITIES',         'description': 'Electricity bills',        'is_active': True},
            {'number': '5110', 'name': 'Water & Sewerage',          'type': 'EXPENSE', 'is_expense_account': True, 'expense_type': 'UTILITIES',         'description': 'Water and sewerage charges','is_active': True},
            {'number': '5120', 'name': 'Internet & Communication',  'type': 'EXPENSE', 'is_expense_account': True, 'expense_type': 'UTILITIES',         'description': 'Internet and phone services','is_active': True},
            # EXPENSES — Supplies
            {'number': '5200', 'name': 'Office Supplies',           'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Stationery and office materials',  'is_active': True},
            {'number': '5210', 'name': 'Learning Materials',        'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Teaching aids and materials',       'is_active': True},
            {'number': '5220', 'name': 'Cleaning Supplies',         'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Cleaning materials and chemicals',  'is_active': True},
            # EXPENSES — Maintenance
            {'number': '5300', 'name': 'Building Maintenance',      'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Building repairs and maintenance',  'is_active': True},
            {'number': '5310', 'name': 'Equipment Repairs',         'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Equipment maintenance and repairs', 'is_active': True},
            # EXPENSES — Other
            {'number': '5400', 'name': 'Security Services',         'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Security personnel and services',   'is_active': True},
            {'number': '5500', 'name': 'Transport & Fuel',          'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Fuel and vehicle maintenance',       'is_active': True},
            {'number': '5600', 'name': 'Professional Fees',         'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Legal and consultancy fees',         'is_active': True},
            {'number': '5700', 'name': 'Insurance',                 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Insurance premiums',                 'is_active': True},
            {'number': '5800', 'name': 'Scholarships & Discounts',  'type': 'EXPENSE', 'is_expense_account': True, 'expense_type': 'SCHOLARSHIP', 'description': 'Scholarships and fee discounts', 'is_active': True},
            {'number': '5900', 'name': 'Other Expenses',            'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Miscellaneous operating expenses',   'is_active': True},
        ]
        if school.boarding_type in ('BOARDING', 'MIXED'):
            accounts += [
                {'number': '4100', 'name': 'Boarding Fees',      'type': 'REVENUE', 'is_revenue_account': True, 'revenue_type': 'BOARDING_REVENUE', 'description': 'Boarding accommodation fees', 'is_active': True},
                {'number': '4110', 'name': 'Meals Revenue',      'type': 'REVENUE', 'is_revenue_account': True, 'revenue_type': 'MEALS_REVENUE',    'description': 'Meal service fees',           'is_active': True},
                {'number': '5610', 'name': 'Food & Provisions',  'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Food purchases for boarding',          'is_active': True},
                {'number': '5620', 'name': 'Boarding Supplies',  'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Bedding, toiletries, boarding supplies','is_active': True},
            ]
        return accounts

    @classmethod
    def _get_advanced_accounts(cls, school):
        """
        Advanced comprehensive chart — ~80 accounts.

        ACCOUNT NUMBER LAYOUT (matches get_account_mappings_config ADVANCED):
          1000 = Cash on Hand        (default_cash_account)
          1010 = Petty Cash          (petty_cash_account)
          1020 = Bank Account - Main (default_bank_account)
          1030 = Mobile Money - MTN  (mobile_money_account)
        """
        accounts = [
            # ASSETS (1000-1999) — Cash & Bank
            {'number': '1000', 'name': 'Cash on Hand',                           'type': 'ASSET', 'is_cash_account': True,     'description': 'Physical cash at school',                  'is_active': True},
            {'number': '1010', 'name': 'Petty Cash',                             'type': 'ASSET', 'is_cash_account': True,     'description': 'Petty cash fund for minor expenses',       'is_active': True},
            {'number': '1020', 'name': 'Bank Account - Main',                    'type': 'ASSET', 'is_bank_account': True,     'description': 'Primary bank account',                    'is_active': True},
            {'number': '1021', 'name': 'Bank Account - Payroll',                 'type': 'ASSET', 'is_bank_account': True,     'description': 'Dedicated payroll account',               'is_active': True},
            {'number': '1022', 'name': 'Bank Account - Savings',                 'type': 'ASSET', 'is_bank_account': True,     'description': 'Savings and reserve account',             'is_active': True},
            {'number': '1030', 'name': 'Mobile Money - MTN',                     'type': 'ASSET', 'description': 'MTN Mobile Money clearing',                     'is_active': True},
            {'number': '1031', 'name': 'Mobile Money - Airtel',                  'type': 'ASSET', 'description': 'Airtel Money clearing',                         'is_active': True},
            # Receivables
            {'number': '1100', 'name': 'Student Receivables - Current',          'type': 'ASSET', 'is_receivable_account': True, 'receivable_type': 'STUDENT', 'description': 'Current term student fees',   'is_active': True},
            {'number': '1110', 'name': 'Student Receivables - Arrears',          'type': 'ASSET', 'is_receivable_account': True, 'receivable_type': 'STUDENT', 'description': 'Overdue student fees',        'is_active': True},
            {'number': '1120', 'name': 'Staff Receivables',                      'type': 'ASSET', 'is_receivable_account': True, 'receivable_type': 'STAFF',   'description': 'Staff loans and advances',   'is_active': True},
            {'number': '1130', 'name': 'Other Receivables',                      'type': 'ASSET', 'is_receivable_account': True, 'description': 'Miscellaneous receivables',              'is_active': True},
            {'number': '1140', 'name': 'Allowance for Doubtful Accounts',        'type': 'ASSET', 'description': 'Bad debt provision',                          'is_active': True},
            # Inventory
            {'number': '1200', 'name': 'Inventory - General Supplies',           'type': 'ASSET', 'description': 'General school supplies',                     'is_active': True},
            {'number': '1210', 'name': 'Inventory - Uniforms',                   'type': 'ASSET', 'description': 'School uniforms inventory',                   'is_active': True},
            {'number': '1220', 'name': 'Inventory - Textbooks',                  'type': 'ASSET', 'description': 'Textbooks and learning materials',            'is_active': True},
            {'number': '1230', 'name': 'Inventory - Food & Provisions',          'type': 'ASSET', 'description': 'Food items and catering supplies',            'is_active': True},
            {'number': '1240', 'name': 'Inventory - Stationery',                 'type': 'ASSET', 'description': 'Office and student stationery',               'is_active': True},
            # Prepaid Expenses
            {'number': '1300', 'name': 'Prepaid Rent',                           'type': 'ASSET', 'description': 'Rent paid in advance',                        'is_active': True},
            {'number': '1310', 'name': 'Prepaid Insurance',                      'type': 'ASSET', 'description': 'Insurance premiums paid in advance',          'is_active': True},
            {'number': '1320', 'name': 'Prepaid Subscriptions',                  'type': 'ASSET', 'description': 'Software and service subscriptions',          'is_active': True},
            # Fixed Assets
            {'number': '1500', 'name': 'Land',                                   'type': 'ASSET', 'description': 'School land',                                 'is_active': True},
            {'number': '1510', 'name': 'Buildings',                              'type': 'ASSET', 'description': 'School buildings and structures',             'is_active': True},
            {'number': '1511', 'name': 'Accumulated Depreciation - Buildings',   'type': 'ASSET', 'description': 'Building depreciation',                       'is_active': True},
            {'number': '1520', 'name': 'Furniture & Fixtures',                   'type': 'ASSET', 'description': 'Desks, chairs, cabinets',                     'is_active': True},
            {'number': '1521', 'name': 'Accumulated Depreciation - Furniture',   'type': 'ASSET', 'description': 'Furniture depreciation',                      'is_active': True},
            {'number': '1530', 'name': 'Computer Equipment',                     'type': 'ASSET', 'description': 'Computers and IT hardware',                   'is_active': True},
            {'number': '1531', 'name': 'Accumulated Depreciation - Computers',   'type': 'ASSET', 'description': 'Computer depreciation',                       'is_active': True},
            {'number': '1540', 'name': 'Vehicles',                               'type': 'ASSET', 'description': 'School buses and vehicles',                   'is_active': True},
            {'number': '1541', 'name': 'Accumulated Depreciation - Vehicles',    'type': 'ASSET', 'description': 'Vehicle depreciation',                        'is_active': True},
            {'number': '1550', 'name': 'Laboratory Equipment',                   'type': 'ASSET', 'description': 'Science lab equipment',                       'is_active': True},
            {'number': '1551', 'name': 'Accumulated Depreciation - Lab Equipment','type': 'ASSET', 'description': 'Lab equipment depreciation',                 'is_active': True},
            {'number': '1560', 'name': 'Sports Equipment',                       'type': 'ASSET', 'description': 'Sports and PE equipment',                     'is_active': True},
            {'number': '1570', 'name': 'Library Books',                          'type': 'ASSET', 'description': 'Library collection',                          'is_active': True},

            # LIABILITIES (2000-2999) — Current
            {'number': '2000', 'name': 'Accounts Payable',                       'type': 'LIABILITY', 'is_payable_account': True, 'description': 'Vendor payables',                      'is_active': True},
            {'number': '2010', 'name': 'Salaries Payable',                       'type': 'LIABILITY', 'description': 'Accrued salaries',                                                 'is_active': True},
            {'number': '2020', 'name': 'PAYE Tax Payable',                       'type': 'LIABILITY', 'description': 'Employee income tax withheld',                                     'is_active': True},
            {'number': '2030', 'name': 'NSSF Payable',                           'type': 'LIABILITY', 'description': 'Social security contributions',                                    'is_active': True},
            {'number': '2040', 'name': 'Local Service Tax Payable',              'type': 'LIABILITY', 'description': 'Local service tax',                                                'is_active': True},
            {'number': '2050', 'name': 'Student Deposits',                       'type': 'LIABILITY', 'description': 'Refundable student deposits and caution money',                   'is_active': True},
            {'number': '2060', 'name': 'Advance Fee Payments',                   'type': 'LIABILITY', 'description': 'Fees paid in advance',                                             'is_active': True},
            {'number': '2070', 'name': 'Utilities Payable',                      'type': 'LIABILITY', 'description': 'Accrued utility bills',                                           'is_active': True},
            {'number': '2080', 'name': 'Interest Payable',                       'type': 'LIABILITY', 'description': 'Accrued interest on loans',                                       'is_active': True},
            # Long-term Liabilities
            {'number': '2100', 'name': 'Bank Loans - Long Term',                 'type': 'LIABILITY', 'description': 'Long-term bank loans',                                            'is_active': True},
            {'number': '2110', 'name': 'Equipment Financing',                    'type': 'LIABILITY', 'description': 'Equipment lease obligations',                                     'is_active': True},
            {'number': '2120', 'name': 'Mortgage Payable',                       'type': 'LIABILITY', 'description': 'Property mortgage',                                               'is_active': True},

            # EQUITY (3000-3999)
            {'number': '3000', 'name': 'Capital',                                'type': 'EQUITY', 'description': 'Owners capital contribution',                                        'is_active': True},
            {'number': '3100', 'name': 'Retained Earnings',                      'type': 'EQUITY', 'description': 'Accumulated profits',                                                'is_active': True},
            {'number': '3200', 'name': 'Current Year Earnings',                  'type': 'EQUITY', 'description': 'Current year profit/loss',                                           'is_active': True},
            {'number': '3300', 'name': 'Reserves',                               'type': 'EQUITY', 'description': 'Statutory and voluntary reserves',                                  'is_active': True},

            # REVENUE (4000-4999) — Tuition
            {'number': '4000', 'name': 'Tuition Fees - Primary',                 'type': 'REVENUE', 'is_revenue_account': True, 'revenue_type': 'TUITION',           'description': 'Primary school tuition',       'is_active': True},
            {'number': '4010', 'name': 'Tuition Fees - Secondary',               'type': 'REVENUE', 'is_revenue_account': True, 'revenue_type': 'TUITION',           'description': 'Secondary school tuition',     'is_active': True},
            {'number': '4020', 'name': 'Examination Fees',                       'type': 'REVENUE', 'is_revenue_account': True, 'revenue_type': 'EXAM_FEES',         'description': 'Exam registration and materials','is_active': True},
            {'number': '4030', 'name': 'Development Fees',                       'type': 'REVENUE', 'is_revenue_account': True, 'description': 'Infrastructure development fees',      'is_active': True},
            # Boarding & Meals
            {'number': '4100', 'name': 'Boarding Fees',                          'type': 'REVENUE', 'is_revenue_account': True, 'revenue_type': 'BOARDING_REVENUE',  'description': 'Boarding accommodation fees',  'is_active': True},
            {'number': '4110', 'name': 'Meals Revenue',                          'type': 'REVENUE', 'is_revenue_account': True, 'revenue_type': 'MEALS_REVENUE',     'description': 'Meal service fees',            'is_active': True},
            # Other Revenue
            {'number': '4200', 'name': 'Uniform Sales',                          'type': 'REVENUE', 'is_revenue_account': True, 'revenue_type': 'UNIFORM_SALES',     'description': 'School uniform sales',         'is_active': True},
            {'number': '4210', 'name': 'Textbook Sales',                         'type': 'REVENUE', 'is_revenue_account': True, 'revenue_type': 'BOOK_SALES',        'description': 'Textbook and stationery sales', 'is_active': True},
            {'number': '4220', 'name': 'Transport Fees',                         'type': 'REVENUE', 'is_revenue_account': True, 'revenue_type': 'TRANSPORT_REVENUE', 'description': 'School transport fees',        'is_active': True},
            {'number': '4230', 'name': 'Activity Fees',                          'type': 'REVENUE', 'is_revenue_account': True, 'description': 'Sports and extracurricular fees',      'is_active': True},
            {'number': '4240', 'name': 'Computer Lab Fees',                      'type': 'REVENUE', 'is_revenue_account': True, 'description': 'ICT and computer fees',                'is_active': True},
            {'number': '4250', 'name': 'Library Fees',                           'type': 'REVENUE', 'is_revenue_account': True, 'description': 'Library service fees',                 'is_active': True},
            # Penalties & Other Income
            {'number': '4300', 'name': 'Late Payment Fees',                      'type': 'REVENUE', 'is_revenue_account': True, 'description': 'Late payment penalties',               'is_active': True},
            {'number': '4310', 'name': 'Replacement Fees',                       'type': 'REVENUE', 'is_revenue_account': True, 'description': 'Lost item replacement charges',        'is_active': True},
            {'number': '4900', 'name': 'Donations & Grants',                     'type': 'REVENUE', 'is_revenue_account': True, 'description': 'Donations and grant income',           'is_active': True},
            {'number': '4910', 'name': 'Interest Income',                        'type': 'REVENUE', 'is_revenue_account': True, 'description': 'Bank interest earned',                 'is_active': True},
            {'number': '4920', 'name': 'Miscellaneous Income',                   'type': 'REVENUE', 'is_revenue_account': True, 'description': 'Other income',                         'is_active': True},

            # EXPENSES (5000-5999) — Salaries & Benefits
            {'number': '5000', 'name': 'Teaching Staff - Basic Salary',          'type': 'EXPENSE', 'is_expense_account': True, 'expense_type': 'TEACHING_SALARIES', 'description': 'Teacher base salaries',        'is_active': True},
            {'number': '5010', 'name': 'Teaching Staff - Housing Allowance',     'type': 'EXPENSE', 'is_expense_account': True, 'expense_type': 'TEACHING_SALARIES', 'description': 'Teacher housing allowance',    'is_active': True},
            {'number': '5020', 'name': 'Teaching Staff - Transport Allowance',   'type': 'EXPENSE', 'is_expense_account': True, 'expense_type': 'TEACHING_SALARIES', 'description': 'Teacher transport allowance',  'is_active': True},
            {'number': '5030', 'name': 'Administrative Staff Salaries',          'type': 'EXPENSE', 'is_expense_account': True, 'expense_type': 'ADMIN_SALARIES',    'description': 'Admin staff salaries',         'is_active': True},
            {'number': '5040', 'name': 'Support Staff Salaries',                 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Support and maintenance staff',        'is_active': True},
            {'number': '5050', 'name': 'NSSF Contributions',                     'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Employer NSSF contributions',          'is_active': True},
            {'number': '5060', 'name': 'Staff Medical Insurance',                'type': 'EXPENSE', 'is_expense_account': True, 'expense_type': 'STAFF_BENEFITS',    'description': 'Staff health insurance',       'is_active': True},
            {'number': '5070', 'name': 'Staff Training & Development',           'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Professional development',             'is_active': True},
            {'number': '5080', 'name': 'Staff Welfare',                          'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Staff welfare expenses',               'is_active': True},
            # Utilities
            {'number': '5100', 'name': 'Electricity',                            'type': 'EXPENSE', 'is_expense_account': True, 'expense_type': 'UTILITIES',         'description': 'Electricity bills',            'is_active': True},
            {'number': '5110', 'name': 'Water & Sewerage',                       'type': 'EXPENSE', 'is_expense_account': True, 'expense_type': 'UTILITIES',         'description': 'Water and sewerage charges',   'is_active': True},
            {'number': '5120', 'name': 'Internet & WiFi',                        'type': 'EXPENSE', 'is_expense_account': True, 'expense_type': 'UTILITIES',         'description': 'Internet connectivity',        'is_active': True},
            {'number': '5130', 'name': 'Telephone & Mobile',                     'type': 'EXPENSE', 'is_expense_account': True, 'expense_type': 'UTILITIES',         'description': 'Phone services',               'is_active': True},
            {'number': '5140', 'name': 'Waste Management',                       'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Garbage collection services',          'is_active': True},
            # Academic Supplies
            {'number': '5200', 'name': 'Textbooks & Learning Materials',         'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Teaching materials purchases',         'is_active': True},
            {'number': '5210', 'name': 'Stationery & Office Supplies',           'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Office stationery',                    'is_active': True},
            {'number': '5220', 'name': 'Laboratory Supplies',                    'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Science lab consumables',              'is_active': True},
            {'number': '5230', 'name': 'Library Books & Materials',              'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Library acquisitions',                 'is_active': True},
            {'number': '5240', 'name': 'Computer Software & Licenses',           'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Software subscriptions',               'is_active': True},
            # Maintenance & Repairs
            {'number': '5300', 'name': 'Building Maintenance',                   'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Building repairs',                     'is_active': True},
            {'number': '5310', 'name': 'Equipment Repairs',                      'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Equipment maintenance',                'is_active': True},
            {'number': '5320', 'name': 'Plumbing & Electrical Repairs',          'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Plumbing and electrical work',         'is_active': True},
            {'number': '5330', 'name': 'Painting & Renovation',                  'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Painting and refurbishment',           'is_active': True},
            {'number': '5340', 'name': 'Cleaning Supplies',                      'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Cleaning materials',                   'is_active': True},
            # Security & Safety
            {'number': '5400', 'name': 'Security Services',                      'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Security guard services',              'is_active': True},
            {'number': '5410', 'name': 'Security Equipment',                     'type': 'EXPENSE', 'is_expense_account': True, 'description': 'CCTV and security systems',            'is_active': True},
            {'number': '5420', 'name': 'Fire Safety Equipment',                  'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Fire extinguishers and safety',        'is_active': True},
            # Transport
            {'number': '5500', 'name': 'Fuel & Oil',                             'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Vehicle fuel costs',                   'is_active': True},
            {'number': '5510', 'name': 'Vehicle Maintenance & Repairs',          'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Vehicle servicing',                    'is_active': True},
            {'number': '5520', 'name': 'Vehicle Insurance',                      'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Vehicle insurance premiums',           'is_active': True},
            {'number': '5530', 'name': 'Vehicle Licensing & Permits',            'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Road licenses and permits',            'is_active': True},
            # Boarding & Catering
            {'number': '5600', 'name': 'Food & Provisions',                      'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Food purchases',                       'is_active': True},
            {'number': '5610', 'name': 'Kitchen Supplies & Equipment',           'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Kitchen utensils and equipment',       'is_active': True},
            {'number': '5620', 'name': 'Cooking Gas',                            'type': 'EXPENSE', 'is_expense_account': True, 'description': 'LPG and cooking fuel',                 'is_active': True},
            {'number': '5630', 'name': 'Laundry Services',                       'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Boarding laundry costs',               'is_active': True},
            {'number': '5640', 'name': 'Bedding & Linen',                        'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Bedding for boarding',                 'is_active': True},
            # Administrative
            {'number': '5700', 'name': 'Advertising & Marketing',                'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Marketing and promotion',              'is_active': True},
            {'number': '5710', 'name': 'Printing & Publications',                'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Printing services',                    'is_active': True},
            {'number': '5720', 'name': 'Legal & Professional Fees',              'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Legal and consultancy fees',           'is_active': True},
            {'number': '5730', 'name': 'Audit Fees',                             'type': 'EXPENSE', 'is_expense_account': True, 'description': 'External audit costs',                 'is_active': True},
            {'number': '5740', 'name': 'Bank Charges & Fees',                    'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Banking transaction fees',             'is_active': True},
            {'number': '5750', 'name': 'Licenses & Permits',                     'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Business licenses',                    'is_active': True},
            {'number': '5760', 'name': 'Insurance - General',                    'type': 'EXPENSE', 'is_expense_account': True, 'description': 'General insurance premiums',           'is_active': True},
            {'number': '5770', 'name': 'Subscriptions & Memberships',            'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Professional memberships',             'is_active': True},
            # Scholarships & Financial Aid
            {'number': '5800', 'name': 'Scholarships & Bursaries',               'type': 'EXPENSE', 'is_expense_account': True, 'expense_type': 'SCHOLARSHIP', 'description': 'Student scholarships', 'is_active': True},
            {'number': '5810', 'name': 'Fee Discounts',                          'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Fee reduction allowances',             'is_active': True},
            {'number': '5820', 'name': 'Bad Debt Write-off',                     'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Uncollectible fees',                   'is_active': True},
            # Depreciation
            {'number': '5850', 'name': 'Depreciation - Buildings',               'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Building depreciation expense',        'is_active': True},
            {'number': '5851', 'name': 'Depreciation - Furniture',               'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Furniture depreciation expense',       'is_active': True},
            {'number': '5852', 'name': 'Depreciation - Computers',               'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Computer depreciation expense',        'is_active': True},
            {'number': '5853', 'name': 'Depreciation - Vehicles',                'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Vehicle depreciation expense',         'is_active': True},
            {'number': '5854', 'name': 'Depreciation - Equipment',               'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Equipment depreciation expense',       'is_active': True},
            # Other Expenses
            {'number': '5900', 'name': 'Entertainment & Events',                 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'School events and functions',          'is_active': True},
            {'number': '5910', 'name': 'Sports & Recreation',                    'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Sports equipment and activities',      'is_active': True},
            {'number': '5920', 'name': 'Medical Supplies',                       'type': 'EXPENSE', 'is_expense_account': True, 'description': 'First aid and medical supplies',       'is_active': True},
            {'number': '5930', 'name': 'Interest Expense',                       'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Loan interest payments',               'is_active': True},
            {'number': '5990', 'name': 'Miscellaneous Expenses',                 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Other operating expenses',             'is_active': True},
        ]
        return accounts

    # =========================================================================
    # EXPENSE CATEGORIES
    # =========================================================================

    @classmethod
    def get_expense_categories(cls):
        """Comprehensive expense categories for the finance/expense module."""
        return [
            # ADMINISTRATIVE
            {'name': 'Office Supplies',           'category_type': 'ADMINISTRATIVE', 'description': 'Office supplies, stationery, and general administrative expenses',      'requires_approval': True,  'approval_limit': Decimal('50000.00'),     'is_active': True},
            {'name': 'Legal & Professional Fees', 'category_type': 'ADMINISTRATIVE', 'description': 'Legal consultations, audit fees, and professional services',           'requires_approval': True,  'approval_limit': Decimal('100000.00'),    'is_active': True},
            {'name': 'Licenses & Permits',        'category_type': 'ADMINISTRATIVE', 'description': 'Government licenses, permits, and regulatory fees',                    'requires_approval': True,  'approval_limit': Decimal('200000.00'),    'is_active': True},
            {'name': 'Bank Charges',              'category_type': 'ADMINISTRATIVE', 'description': 'Banking fees, transaction charges, and account maintenance',           'requires_approval': False, 'approval_limit': None,                   'is_active': True},
            {'name': 'Postage & Courier',         'category_type': 'ADMINISTRATIVE', 'description': 'Mail, postage, and courier delivery services',                         'requires_approval': False, 'approval_limit': Decimal('20000.00'),     'is_active': True},
            # ACADEMIC
            {'name': 'Curriculum Development',   'category_type': 'ACADEMIC',       'description': 'Curriculum design, development, and review activities',                 'requires_approval': True,  'approval_limit': Decimal('300000.00'),    'is_active': True},
            {'name': 'Teacher Training',          'category_type': 'ACADEMIC',       'description': 'Professional development and training programs for teaching staff',     'requires_approval': True,  'approval_limit': Decimal('500000.00'),    'is_active': True},
            {'name': 'Educational Consultancy',   'category_type': 'ACADEMIC',       'description': 'External educational consultants and advisory services',               'requires_approval': True,  'approval_limit': Decimal('200000.00'),    'is_active': True},
            # SCHOLASTIC
            {'name': 'Learning Materials',        'category_type': 'SCHOLASTIC',     'description': 'Textbooks, workbooks, stationery, and teaching aids',                  'requires_approval': True,  'approval_limit': Decimal('100000.00'),    'is_active': True},
            {'name': 'Library Resources',         'category_type': 'SCHOLASTIC',     'description': 'Books, journals, magazines, and digital library resources',            'requires_approval': True,  'approval_limit': Decimal('150000.00'),    'is_active': True},
            {'name': 'Laboratory Supplies',       'category_type': 'SCHOLASTIC',     'description': 'Science lab chemicals, equipment, and consumables',                    'requires_approval': True,  'approval_limit': Decimal('200000.00'),    'is_active': True},
            {'name': 'Art & Craft Supplies',      'category_type': 'SCHOLASTIC',     'description': 'Art materials, craft supplies, and creative resources',               'requires_approval': True,  'approval_limit': Decimal('80000.00'),     'is_active': True},
            # EXAMINATION
            {'name': 'Examination Materials',     'category_type': 'EXAMINATION',    'description': 'Question papers, answer sheets, printing, and exam supplies',          'requires_approval': True,  'approval_limit': Decimal('100000.00'),    'is_active': True},
            {'name': 'External Examination Fees', 'category_type': 'EXAMINATION',    'description': 'UNEB, Cambridge, and other external examination body fees',            'requires_approval': True,  'approval_limit': Decimal('500000.00'),    'is_active': True},
            {'name': 'Invigilation Costs',        'category_type': 'EXAMINATION',    'description': 'External invigilators and examination supervision costs',              'requires_approval': True,  'approval_limit': Decimal('150000.00'),    'is_active': True},
            # FACILITIES
            {'name': 'Maintenance & Repairs',     'category_type': 'FACILITIES',     'description': 'Building maintenance, equipment repairs, and general upkeep',          'requires_approval': True,  'approval_limit': Decimal('300000.00'),    'is_active': True},
            {'name': 'Cleaning Supplies',         'category_type': 'FACILITIES',     'description': 'Cleaning materials, detergents, and sanitation supplies',              'requires_approval': True,  'approval_limit': Decimal('50000.00'),     'is_active': True},
            {'name': 'Security Services',         'category_type': 'FACILITIES',     'description': 'Security guard services, surveillance, and security equipment',       'requires_approval': True,  'approval_limit': Decimal('200000.00'),    'is_active': True},
            {'name': 'Groundskeeping',            'category_type': 'FACILITIES',     'description': 'Landscaping, gardening, and ground maintenance',                       'requires_approval': True,  'approval_limit': Decimal('100000.00'),    'is_active': True},
            # CAPITAL
            {'name': 'Land & Buildings',          'category_type': 'CAPITAL',        'description': 'Purchase of land and building construction projects',                  'requires_approval': True,  'approval_limit': Decimal('10000000.00'),  'is_active': True},
            {'name': 'Building Improvements',     'category_type': 'CAPITAL',        'description': 'Major renovations and structural improvements',                        'requires_approval': True,  'approval_limit': Decimal('5000000.00'),   'is_active': True},
            {'name': 'Furniture & Fixtures',      'category_type': 'CAPITAL',        'description': 'Desks, chairs, classroom furniture, and fixtures',                    'requires_approval': True,  'approval_limit': Decimal('1000000.00'),   'is_active': True},
            {'name': 'Vehicles',                  'category_type': 'CAPITAL',        'description': 'Purchase of school buses, cars, and other vehicles',                  'requires_approval': True,  'approval_limit': Decimal('5000000.00'),   'is_active': True},
            {'name': 'Laboratory Equipment',      'category_type': 'CAPITAL',        'description': 'Major laboratory equipment and machinery',                             'requires_approval': True,  'approval_limit': Decimal('2000000.00'),   'is_active': True},
            # UTILITIES
            {'name': 'Electricity',               'category_type': 'UTILITIES',      'description': 'Monthly electricity bills and power consumption',                     'requires_approval': True,  'approval_limit': Decimal('500000.00'),    'is_active': True},
            {'name': 'Water & Sewerage',          'category_type': 'UTILITIES',      'description': 'Water supply and sewerage services',                                   'requires_approval': True,  'approval_limit': Decimal('200000.00'),    'is_active': True},
            {'name': 'Internet & Phone',          'category_type': 'UTILITIES',      'description': 'Internet connectivity, telephone, and communication services',        'requires_approval': True,  'approval_limit': Decimal('300000.00'),    'is_active': True},
            {'name': 'Gas & Fuel',                'category_type': 'UTILITIES',      'description': 'Cooking gas and generator fuel',                                       'requires_approval': True,  'approval_limit': Decimal('400000.00'),    'is_active': True},
            # TRANSPORT
            {'name': 'School Vehicles',           'category_type': 'TRANSPORT',      'description': 'School bus operations, maintenance, and repairs',                     'requires_approval': True,  'approval_limit': Decimal('300000.00'),    'is_active': True},
            {'name': 'Fuel Costs',                'category_type': 'TRANSPORT',      'description': 'Fuel for all school vehicles',                                         'requires_approval': True,  'approval_limit': Decimal('500000.00'),    'is_active': True},
            {'name': 'Official Travel',           'category_type': 'TRANSPORT',      'description': 'Staff official travel and transportation expenses',                   'requires_approval': True,  'approval_limit': Decimal('200000.00'),    'is_active': True},
            # MEALS
            {'name': 'Food & Beverages',          'category_type': 'MEALS',          'description': 'Raw food materials, ingredients, and beverages',                      'requires_approval': True,  'approval_limit': Decimal('1000000.00'),   'is_active': True},
            {'name': 'Kitchen Supplies',          'category_type': 'MEALS',          'description': 'Cooking equipment, utensils, and kitchen supplies',                   'requires_approval': True,  'approval_limit': Decimal('200000.00'),    'is_active': True},
            {'name': 'Catering Services',         'category_type': 'MEALS',          'description': 'External catering for special events and functions',                  'requires_approval': True,  'approval_limit': Decimal('300000.00'),    'is_active': True},
            # STAFF
            {'name': 'Staff Salaries',            'category_type': 'STAFF',          'description': 'Monthly salaries and wages for all staff',                             'requires_approval': True,  'approval_limit': Decimal('20000000.00'),  'is_active': True},
            {'name': 'Staff Benefits',            'category_type': 'STAFF',          'description': 'Medical insurance, pension, allowances, and other benefits',          'requires_approval': True,  'approval_limit': Decimal('2000000.00'),   'is_active': True},
            {'name': 'Temporary Staff',           'category_type': 'STAFF',          'description': 'Substitute teachers, casual workers, and temporary staff',            'requires_approval': True,  'approval_limit': Decimal('500000.00'),    'is_active': True},
            {'name': 'Staff Training',            'category_type': 'STAFF',          'description': 'Professional development and staff training programs',                'requires_approval': True,  'approval_limit': Decimal('1000000.00'),   'is_active': True},
            # MEDICAL
            {'name': 'Health Services',           'category_type': 'MEDICAL',        'description': 'School clinic operations and medical staff',                           'requires_approval': True,  'approval_limit': Decimal('300000.00'),    'is_active': True},
            {'name': 'Medical Supplies',          'category_type': 'MEDICAL',        'description': 'Medicines, medical equipment, and health supplies',                   'requires_approval': True,  'approval_limit': Decimal('200000.00'),    'is_active': True},
            {'name': 'First Aid Supplies',        'category_type': 'MEDICAL',        'description': 'Basic medical and first aid supplies',                                 'requires_approval': False, 'approval_limit': Decimal('50000.00'),     'is_active': True},
            {'name': 'Health Insurance',          'category_type': 'MEDICAL',        'description': 'Student and staff health insurance premiums',                         'requires_approval': True,  'approval_limit': Decimal('1000000.00'),   'is_active': True},
            # SPORTS
            {'name': 'Sports Equipment',          'category_type': 'SPORTS',         'description': 'Sports equipment, gear, and athletic supplies',                       'requires_approval': True,  'approval_limit': Decimal('300000.00'),    'is_active': True},
            {'name': 'Sports Competitions',       'category_type': 'SPORTS',         'description': 'Inter-school competitions, tournaments, and sports events',           'requires_approval': True,  'approval_limit': Decimal('500000.00'),    'is_active': True},
            {'name': 'Music & Drama',             'category_type': 'SPORTS',         'description': 'Musical instruments, drama supplies, and performance arts',           'requires_approval': True,  'approval_limit': Decimal('400000.00'),    'is_active': True},
            {'name': 'School Events',             'category_type': 'SPORTS',         'description': 'School functions, celebrations, and special events',                  'requires_approval': True,  'approval_limit': Decimal('600000.00'),    'is_active': True},
            # STUDENT SERVICES
            {'name': 'Student Welfare',           'category_type': 'STUDENT_SERVICES','description': 'Student counseling, welfare programs, and support services',         'requires_approval': True,  'approval_limit': Decimal('200000.00'),    'is_active': True},
            {'name': 'Student Activities',        'category_type': 'STUDENT_SERVICES','description': 'Student clubs, societies, and co-curricular activities',             'requires_approval': True,  'approval_limit': Decimal('300000.00'),    'is_active': True},
            {'name': 'Guidance & Counseling',     'category_type': 'STUDENT_SERVICES','description': 'Professional counseling services and guidance programs',             'requires_approval': True,  'approval_limit': Decimal('400000.00'),    'is_active': True},
            # PTA
            {'name': 'PTA Activities',            'category_type': 'PTA',            'description': 'Parent-Teacher Association programs and activities',                   'requires_approval': True,  'approval_limit': Decimal('200000.00'),    'is_active': True},
            {'name': 'Parent Engagement',         'category_type': 'PTA',            'description': 'Parent meetings, workshops, and engagement programs',                 'requires_approval': True,  'approval_limit': Decimal('150000.00'),    'is_active': True},
            # MARKETING
            {'name': 'Advertising',               'category_type': 'MARKETING',      'description': 'Print, radio, TV, and online advertising campaigns',                  'requires_approval': True,  'approval_limit': Decimal('500000.00'),    'is_active': True},
            {'name': 'Website & Digital Marketing','category_type': 'MARKETING',     'description': 'Website maintenance, SEO, and digital marketing',                    'requires_approval': True,  'approval_limit': Decimal('200000.00'),    'is_active': True},
            {'name': 'Public Relations',          'category_type': 'MARKETING',      'description': 'PR activities, community engagement, and media relations',            'requires_approval': True,  'approval_limit': Decimal('300000.00'),    'is_active': True},
            {'name': 'Promotional Materials',     'category_type': 'MARKETING',      'description': 'Brochures, banners, flyers, and promotional items',                  'requires_approval': True,  'approval_limit': Decimal('150000.00'),    'is_active': True},
            # TECHNOLOGY
            {'name': 'Hardware',                  'category_type': 'TECHNOLOGY',     'description': 'Computer equipment, servers, and hardware purchases',                 'requires_approval': True,  'approval_limit': Decimal('1000000.00'),   'is_active': True},
            {'name': 'Software & Licenses',       'category_type': 'TECHNOLOGY',     'description': 'Software licenses, subscriptions, and digital tools',                'requires_approval': True,  'approval_limit': Decimal('500000.00'),    'is_active': True},
            {'name': 'IT Maintenance',            'category_type': 'TECHNOLOGY',     'description': 'IT support, equipment maintenance, and technical services',          'requires_approval': True,  'approval_limit': Decimal('300000.00'),    'is_active': True},
            {'name': 'Internet & Connectivity',   'category_type': 'TECHNOLOGY',     'description': 'Internet services, bandwidth, and network connectivity',             'requires_approval': True,  'approval_limit': Decimal('400000.00'),    'is_active': True},
            # LEGAL
            {'name': 'Legal Fees',                'category_type': 'LEGAL',          'description': 'Legal consultation, representation, and advisory services',           'requires_approval': True,  'approval_limit': Decimal('1000000.00'),   'is_active': True},
            {'name': 'Audit Fees',                'category_type': 'LEGAL',          'description': 'External audit, accounting services, and financial reviews',         'requires_approval': True,  'approval_limit': Decimal('2000000.00'),   'is_active': True},
            {'name': 'Compliance Costs',          'category_type': 'LEGAL',          'description': 'Regulatory compliance, certifications, and inspections',             'requires_approval': True,  'approval_limit': Decimal('500000.00'),    'is_active': True},
            # FINANCIAL
            {'name': 'Interest on Loans',         'category_type': 'FINANCIAL',      'description': 'Interest payments on borrowed funds and financing',                   'requires_approval': False, 'approval_limit': None,                   'is_active': True},
            {'name': 'Loan Principal Repayment',  'category_type': 'FINANCIAL',      'description': 'Principal repayment on loans and borrowings',                        'requires_approval': False, 'approval_limit': None,                   'is_active': True},
            {'name': 'Foreign Exchange Loss',     'category_type': 'FINANCIAL',      'description': 'Losses from currency exchange rate fluctuations',                    'requires_approval': False, 'approval_limit': None,                   'is_active': True},
            {'name': 'Investment Losses',         'category_type': 'FINANCIAL',      'description': 'Losses on financial investments and securities',                     'requires_approval': False, 'approval_limit': None,                   'is_active': True},
            # INSURANCE
            {'name': 'Building Insurance',        'category_type': 'INSURANCE',      'description': 'Property, building, and asset insurance premiums',                   'requires_approval': True,  'approval_limit': Decimal('2000000.00'),   'is_active': True},
            {'name': 'Vehicle Insurance',         'category_type': 'INSURANCE',      'description': 'Motor vehicle insurance for school fleet',                           'requires_approval': True,  'approval_limit': Decimal('1000000.00'),   'is_active': True},
            {'name': 'General Liability',         'category_type': 'INSURANCE',      'description': 'Public liability and third-party insurance coverage',                'requires_approval': True,  'approval_limit': Decimal('1500000.00'),   'is_active': True},
            {'name': 'Student Insurance',         'category_type': 'INSURANCE',      'description': 'Student accident and injury insurance coverage',                     'requires_approval': True,  'approval_limit': Decimal('500000.00'),    'is_active': True},
            # TAX
            {'name': 'Corporate Income Tax',      'category_type': 'TAX',            'description': 'Corporate income tax payments to government',                         'requires_approval': False, 'approval_limit': None,                   'is_active': True},
            {'name': 'VAT Payments',              'category_type': 'TAX',            'description': 'Value Added Tax remittances to tax authority',                       'requires_approval': False, 'approval_limit': None,                   'is_active': True},
            {'name': 'Withholding Tax',           'category_type': 'TAX',            'description': 'Withholding tax on payments to suppliers and contractors',           'requires_approval': False, 'approval_limit': None,                   'is_active': True},
            {'name': 'Property Tax',              'category_type': 'TAX',            'description': 'Local government property taxes and rates',                          'requires_approval': False, 'approval_limit': None,                   'is_active': True},
            {'name': 'Penalties & Fines',         'category_type': 'TAX',            'description': 'Government penalties, fines, and compliance charges',               'requires_approval': False, 'approval_limit': None,                   'is_active': True},
            # DRAWINGS
            {'name': 'Owner Drawings',            'category_type': 'DRAWINGS',       'description': 'Proprietor personal withdrawals from school funds',                   'requires_approval': True,  'approval_limit': Decimal('5000000.00'),   'is_active': True},
            {'name': 'Partner Distributions',     'category_type': 'DRAWINGS',       'description': 'Profit distributions to business partners',                          'requires_approval': True,  'approval_limit': Decimal('10000000.00'),  'is_active': True},
            {'name': 'Shareholder Dividends',     'category_type': 'DRAWINGS',       'description': 'Dividend payments to shareholders',                                  'requires_approval': True,  'approval_limit': Decimal('10000000.00'),  'is_active': True},
            # DEPRECIATION
            {'name': 'Depreciation - Buildings',  'category_type': 'DEPRECIATION',   'description': 'Annual depreciation charge on buildings and structures',              'requires_approval': False, 'approval_limit': None,                   'is_active': True},
            {'name': 'Depreciation - Equipment',  'category_type': 'DEPRECIATION',   'description': 'Annual depreciation on furniture, fixtures, and equipment',          'requires_approval': False, 'approval_limit': None,                   'is_active': True},
            {'name': 'Depreciation - Vehicles',   'category_type': 'DEPRECIATION',   'description': 'Annual depreciation on school vehicles and fleet',                  'requires_approval': False, 'approval_limit': None,                   'is_active': True},
            {'name': 'Amortization',              'category_type': 'DEPRECIATION',   'description': 'Amortization of intangible assets and goodwill',                    'requires_approval': False, 'approval_limit': None,                   'is_active': True},
            # CHARITY
            {'name': 'Charitable Donations',      'category_type': 'CHARITY',        'description': 'Donations to charitable organisations and causes',                   'requires_approval': True,  'approval_limit': Decimal('1000000.00'),   'is_active': True},
            {'name': 'Community Support',         'category_type': 'CHARITY',        'description': 'Community development and social support programs',                  'requires_approval': True,  'approval_limit': Decimal('500000.00'),    'is_active': True},
            {'name': 'Scholarship Fund',          'category_type': 'CHARITY',        'description': 'Scholarships and financial aid for needy students',                  'requires_approval': True,  'approval_limit': Decimal('2000000.00'),   'is_active': True},
            # MISCELLANEOUS
            {'name': 'Bad Debts',                 'category_type': 'MISCELLANEOUS',  'description': 'Write-off of uncollectible student fees and debts',                  'requires_approval': True,  'approval_limit': Decimal('1000000.00'),   'is_active': True},
            {'name': 'Emergency Expenses',        'category_type': 'MISCELLANEOUS',  'description': 'Unexpected emergency costs and urgent requirements',                 'requires_approval': True,  'approval_limit': Decimal('500000.00'),    'is_active': True},
            {'name': 'Loss on Asset Disposal',    'category_type': 'MISCELLANEOUS',  'description': 'Losses incurred from selling or disposing of assets',               'requires_approval': False, 'approval_limit': None,                   'is_active': True},
            # OTHER
            {'name': 'Miscellaneous Expenses',    'category_type': 'OTHER',          'description': 'Other uncategorised expenses not fitting elsewhere',                  'requires_approval': True,  'approval_limit': Decimal('100000.00'),    'is_active': True},
        ]

    # =========================================================================
    # JOURNALS
    # =========================================================================

    @classmethod
    def get_journals(cls):
        """Standard accounting journals. Journal type drives which transactions can post."""
        return [
            {
                'name': 'General Journal', 'journal_type': 'GENERAL',
                'description': (
                    'General accounting entries including adjustments, corrections, '
                    'opening balances, and non-routine transactions.'
                ),
                'is_active': True,
            },
            {
                'name': 'Fee Collection Journal', 'journal_type': 'FEES',
                'description': (
                    'All student fee-related transactions including tuition payments, '
                    'boarding fees, activity fees, and other student charges.'
                ),
                'is_active': True,
            },
            {
                'name': 'Expense Journal', 'journal_type': 'EXPENSES',
                'description': (
                    'School operational expenses including salaries, utilities, supplies, '
                    'and maintenance. Records all non-payroll expenditure.'
                ),
                'is_active': True,
            },
            {
                'name': 'Cash Journal', 'journal_type': 'CASH',
                'description': (
                    'All cash transactions including receipts, payments, petty cash '
                    'disbursements, and cash transfers.'
                ),
                'is_active': True,
            },
            {
                'name': 'Bank Journal', 'journal_type': 'BANK',
                'description': (
                    'Bank-related transactions including deposits, withdrawals, transfers, '
                    'cheques, mobile money, and bank charges. Facilitates reconciliation.'
                ),
                'is_active': True,
            },
            {
                'name': 'Payroll Journal', 'journal_type': 'PAYROLL',
                'description': (
                    'Staff salary entries including gross salaries, deductions, net pay, '
                    'and employer contributions. Auto-generated from payroll processing.'
                ),
                'is_active': True,
            },
            {
                'name': 'Adjustments Journal', 'journal_type': 'ADJUSTMENTS',
                'description': (
                    'Period-end adjustments including accruals, prepayments, depreciation, '
                    'provisions, and error corrections for financial statement preparation.'
                ),
                'is_active': True,
            },
        ]

    # =========================================================================
    # FINANCIAL SETTINGS DEFAULTS
    # =========================================================================

    @classmethod
    def get_financial_settings_defaults(cls, school):
        """Get FinancialSettings field values based on school country."""
        country = str(school.country) if school.country else 'UG'

        currency_map = {
            'UG': 'UGX', 'KE': 'KES', 'TZ': 'TZS',
            'RW': 'RWF', 'SS': 'SSP', 'US': 'USD',
        }
        currency = currency_map.get(country, 'UGX')

        # UGX, KES, TZS, RWF don't use decimal places in practice
        decimal_places = 2 if currency in ('USD', 'GBP', 'EUR') else 0

        if currency in ('USD', 'GBP', 'EUR'):
            min_payment = Decimal('10.00')
        elif currency == 'SSP':
            min_payment = Decimal('100.00')
        else:
            min_payment = Decimal('1000.00')

        return {
            'school_currency':             currency,
            'currency_position':           'BEFORE',
            'decimal_places':              decimal_places,
            'use_thousand_separator':      True,
            'invoice_prefix':              'INV',
            'include_year_in_invoice_number': True,
            'payment_prefix':              'PMT',
            'include_year_in_payment_number': True,
            'receipt_prefix':              'RCPT',
            'expense_prefix':              'EXP',
            'include_year_in_expense_number': True,
            'default_payment_terms_days':  30,
            'late_fee_enabled':            False,
            'late_fee_percentage':         Decimal('5.00'),
            'grace_period_days':           7,
            'minimum_payment_amount':      min_payment,
            'allow_partial_payments':      True,
            'auto_apply_scholarships':     True,
            'scholarship_approval_required': True,
            'auto_apply_discounts':        False,
            'discount_approval_required':  True,
            'expense_approval_required':   True,
            'require_expense_receipts':    True,
            'send_invoice_emails':         True,
            'send_payment_confirmations':  True,
            'send_overdue_reminders':      True,
            'overdue_reminder_days':       7,
            'invoice_aging_periods':       [30, 60, 90, 120],
            'auto_generate_recurring_invoices': True,
        }

    # =========================================================================
    # ACCOUNT MAPPINGS — COMPLEXITY-AWARE
    # =========================================================================

    @classmethod
    def get_account_mappings_config(cls, complexity='ADVANCED'):
        """
        Return CoreAccountMappings field → account search criteria.

        FIX: complexity-aware account numbers eliminate the collision where
        default_cash_account search '1000' would find the bank account on
        BASIC and STANDARD charts (where 1000 IS the bank account).

        The init command uses this dict to look up Account instances and
        populate CoreAccountMappings. Optional fields are silently skipped
        if the account is not found.

        BASIC layout:
            1000 = Main Bank Account  (default_bank_account)
            1010 = Cash on Hand       (default_cash_account)

        STANDARD layout:
            1000 = Main Bank Account  (default_bank_account)
            1010 = Petty Cash         (default_cash_account / petty_cash_account)
            1020 = Mobile Money       (mobile_money_account)

        ADVANCED layout:
            1000 = Cash on Hand       (default_cash_account)
            1010 = Petty Cash         (petty_cash_account)
            1020 = Bank Account-Main  (default_bank_account)
            1030 = Mobile Money-MTN   (mobile_money_account)
        """
        if complexity == 'BASIC':
            bank_number         = '1000'
            cash_number         = '1010'
            petty_cash_number   = None          # 1010 IS the cash account in BASIC
            mobile_money_number = None          # No mobile money in basic chart
            boarding_exp_number = '5600'        # Boarding Expenses in BASIC
        elif complexity == 'STANDARD':
            bank_number         = '1000'        # Main Bank Account
            cash_number         = '1010'        # Petty Cash (closest to cash on hand)
            petty_cash_number   = '1010'        # Same as cash in standard
            mobile_money_number = '1020'        # Mobile Money
            boarding_exp_number = '5610'        # Food & Provisions (conditional on boarding)
        else:  # ADVANCED
            bank_number         = '1020'        # Bank Account - Main
            cash_number         = '1000'        # Cash on Hand
            petty_cash_number   = '1010'        # Petty Cash
            mobile_money_number = '1030'        # Mobile Money - MTN
            boarding_exp_number = '5600'        # Food & Provisions

        config = {
            # ─── REQUIRED: The Big 7 + scholarship ───────────────────────────
            'default_bank_account': {
                'search': {'account_number': bank_number},
                'fallback': {'is_bank_account': True},
            },
            'default_cash_account': {
                'search': {'account_number': cash_number},
                'fallback': {'is_cash_account': True},
            },
            'student_receivables_account': {
                'search': {'account_number': '1100'},
                'fallback': {'is_receivable_account': True},
            },
            'default_payable_account': {
                'search': {'account_number': '2000'},
                'fallback': {'is_payable_account': True},
            },
            'default_equity_account': {
                'search': {'account_number': '3000'},
                'fallback': {'account_type__account_type': 'EQUITY'},
            },
            'default_revenue_account': {
                'search': {'account_number': '4000'},
                'fallback': {'is_revenue_account': True},
            },
            # 5990 = Miscellaneous Expenses (catch-all, NOT 5900 Entertainment)
            'default_expense_account': {
                'search': {'account_number': '5990'},
                'fallback': {'name__icontains': 'miscellaneous'},
            },
            'scholarship_discount_account': {
                'search': {'account_number': '5800'},
                'fallback': {'name__icontains': 'scholarship'},
            },

            # ─── OPTIONAL specialised accounts ───────────────────────────────
            'boarding_revenue_account': {
                'search': {'account_number': '4100'},
                'optional': True,
            },
            'uniform_and_book_sales_account': {
                'search': {'account_number': '4200'},
                'optional': True,
            },
            'salaries_account': {
                'search': {'account_number': '5000'},
                'optional': True,
            },
            'utilities_account': {
                'search': {'account_number': '5100'},
                'optional': True,
            },
            'boarding_expense_account': {
                'search': {'account_number': boarding_exp_number},
                'optional': True,
            },
        }

        # Only add petty cash and mobile money entries when the accounts exist
        if petty_cash_number:
            config['petty_cash_account'] = {
                'search': {'account_number': petty_cash_number},
                'optional': True,
            }
        if mobile_money_number:
            config['mobile_money_account'] = {
                'search': {'account_number': mobile_money_number},
                'optional': True,
            }

        return config

    # =========================================================================
    # DEPARTMENTS
    # =========================================================================

    @classmethod
    def get_departments(cls, school=None):
        """All school departments. Must be created before designations."""
        return [
            # CORE ADMINISTRATIVE
            {'name': 'Administration',          'code': 'ADMIN',       'department_type': 'ADMINISTRATIVE', 'description': 'School administration and management',               'is_academic': False, 'is_active': True},
            {'name': 'Finance & Accounts',      'code': 'FINANCE',     'department_type': 'ADMINISTRATIVE', 'description': 'Finance, accounting, and budgeting',                 'is_academic': False, 'is_active': True},
            {'name': 'Human Resources',         'code': 'HR',          'department_type': 'ADMINISTRATIVE', 'description': 'Human resources management',                         'is_academic': False, 'is_active': True},
            {'name': 'Student Affairs',         'code': 'STUDENT',     'department_type': 'SUPPORT',        'description': 'Student welfare and discipline',                     'is_academic': False, 'is_active': True},
            {'name': 'Admissions & Registry',   'code': 'REGISTRY',    'department_type': 'ADMINISTRATIVE', 'description': 'Student admissions and records',                     'is_academic': False, 'is_active': True},
            # ACADEMIC
            {'name': 'Academic Affairs',        'code': 'ACADEMIC',    'department_type': 'ACADEMIC',       'description': 'Academic programs and curriculum oversight',         'is_academic': True,  'is_active': True},
            {'name': 'Early Childhood Dev.',    'code': 'ECD',         'department_type': 'ACADEMIC',       'description': 'Kindergarten and nursery education',                 'is_academic': True,  'is_active': True},
            {'name': 'Primary Education',       'code': 'PRIMARY',     'department_type': 'ACADEMIC',       'description': 'Primary school education',                           'is_academic': True,  'is_active': True},
            {'name': 'Mathematics Department',  'code': 'MATH',        'department_type': 'ACADEMIC',       'academic_subtype': 'MATHEMATICS',    'description': 'Mathematics instruction',                    'is_academic': True,  'is_active': True},
            {'name': 'Science Department',      'code': 'SCIENCE',     'department_type': 'ACADEMIC',       'description': 'Science instruction (Biology, Chemistry, Physics)', 'is_academic': True,  'is_active': True},
            {'name': 'English Department',      'code': 'ENGLISH',     'department_type': 'ACADEMIC',       'academic_subtype': 'ENGLISH',        'description': 'English language and literature',            'is_academic': True,  'is_active': True},
            {'name': 'Social Studies Dept.',    'code': 'SST',         'department_type': 'ACADEMIC',       'description': 'History, Geography, and Social Studies',             'is_academic': True,  'is_active': True},
            {'name': 'Languages Department',    'code': 'LANG',        'department_type': 'ACADEMIC',       'description': 'Foreign and local languages',                        'is_academic': True,  'is_active': True},
            {'name': 'Business Studies Dept.',  'code': 'BUSINESS',    'department_type': 'ACADEMIC',       'academic_subtype': 'BUSINESS_STUDIES','description': 'Business, Economics, and Accounting',       'is_academic': True,  'is_active': True},
            {'name': 'Arts & Creative Studies', 'code': 'ARTS',        'department_type': 'ACADEMIC',       'academic_subtype': 'ARTS',           'description': 'Fine Arts, Music, Drama',                    'is_academic': True,  'is_active': True},
            {'name': 'Physical Education',      'code': 'PE',          'department_type': 'ACADEMIC',       'academic_subtype': 'PHYSICAL_EDUCATION', 'description': 'Physical education and sports',          'is_academic': True,  'is_active': True},
            {'name': 'Religious Education',     'code': 'RE',          'department_type': 'ACADEMIC',       'description': 'Religious and moral education',                      'is_academic': True,  'is_active': True},
            # SPECIALIZED SUPPORT
            {'name': 'Library Services',        'code': 'LIBRARY',     'department_type': 'ACADEMIC',       'description': 'Library and information services',                   'is_academic': False, 'is_active': True},
            {'name': 'ICT Services',            'code': 'ICT',         'department_type': 'TECHNICAL',      'description': 'Information and communication technology',           'is_academic': False, 'is_active': True},
            {'name': 'Examinations Office',     'code': 'EXAMS',       'department_type': 'ACADEMIC',       'description': 'Examinations coordination and management',           'is_academic': False, 'is_active': True},
            {'name': 'Guidance & Counseling',   'code': 'COUNSEL',     'department_type': 'SUPPORT',        'description': 'Student guidance and counseling services',           'is_academic': False, 'is_active': True},
            # OPERATIONAL SUPPORT
            {'name': 'Facilities & Maintenance','code': 'MAINT',       'department_type': 'MAINTENANCE',    'description': 'Building and equipment maintenance',                 'is_academic': False, 'is_active': True},
            {'name': 'Security Services',       'code': 'SECURITY',    'department_type': 'SECURITY',       'description': 'School security and safety',                         'is_academic': False, 'is_active': True},
            {'name': 'Transport Services',      'code': 'TRANSPORT',   'department_type': 'TRANSPORT',      'description': 'School transport and logistics',                     'is_academic': False, 'is_active': True},
            {'name': 'Health Services',         'code': 'HEALTH',      'department_type': 'HEALTH',         'description': 'School clinic and health services',                  'is_academic': False, 'is_active': True},
            {'name': 'Boarding & Hostel',       'code': 'BOARDING',    'department_type': 'SUPPORT',        'description': 'Boarding and residential services',                  'is_academic': False, 'is_active': True},
            {'name': 'Catering & Food',         'code': 'CATERING',    'department_type': 'CATERING',       'description': 'Food preparation and catering services',             'is_academic': False, 'is_active': True},
            {'name': 'Procurement & Stores',    'code': 'PROCUREMENT', 'department_type': 'PROCUREMENT',    'description': 'Purchasing and inventory management',                'is_academic': False, 'is_active': True},
            # SPECIAL PROGRAMS
            {'name': 'Special Needs Support',   'code': 'SPECIAL',     'department_type': 'SUPPORT',        'description': 'Special needs education support',                   'is_academic': True,  'is_active': True},
            {'name': 'International Programs',  'code': 'INTL',        'department_type': 'ACADEMIC',       'description': 'International curriculum and programs',              'is_academic': True,  'is_active': True},
            {'name': 'Parent Relations',        'code': 'PARENT',      'department_type': 'SUPPORT',        'description': 'Parent-Teacher Association and relations',           'is_academic': False, 'is_active': True},
            {'name': 'Quality Assurance',       'code': 'QA',          'department_type': 'ACADEMIC',       'description': 'Academic quality assurance and standards',           'is_academic': True,  'is_active': True},
            {'name': 'Marketing & Comms',       'code': 'MARKETING',   'department_type': 'ADMINISTRATIVE', 'description': 'Marketing, PR, and communications',                 'is_academic': False, 'is_active': True},
            {'name': 'Research & Development',  'code': 'RD',          'department_type': 'ACADEMIC',       'description': 'Educational research and innovation',                'is_academic': True,  'is_active': True},
        ]

    # =========================================================================
    # DESIGNATIONS
    # =========================================================================

    def get_designations(cls, school=None):
        """
        Default job designations — 36 total (28 original + 8 new).

        FIX: Three designation codes clashed with department codes.
        Designation.code is unique=True on the model.
            School Administrator  ADMIN    → SCH_ADMIN
            School Counselor      COUNSEL  → SCHL_COUNSEL
            Security Guard        SECURITY → SEC_GUARD

        NEW additions (8):
            ASST_TEACH, HOD, REGISTRAR, RECEPT,
            INT_AUDIT, LAB_TECH, CLIN_OFF, DORM_WARD

        department_code must match a code in get_departments().
        Departments must be seeded before designations.
        """
        return [
            # ── SENIOR MANAGEMENT (3) ──────────────────────────────────────────────
            # 1
            {'name': 'Head Teacher',        'code': 'HEAD',        'department_code': 'ADMIN',       'is_teaching': True,  'is_management': True,  'rank_order': 1,  'min_salary': Decimal('2000000.00'), 'max_salary': Decimal('5000000.00'), 'description': 'Overall school leadership and management',           'is_active': True},
            # 2
            {'name': 'Deputy Head Teacher', 'code': 'DEPUTY',      'department_code': 'ADMIN',       'is_teaching': True,  'is_management': True,  'rank_order': 2,  'min_salary': Decimal('1500000.00'), 'max_salary': Decimal('3000000.00'), 'description': 'Assists head teacher in school management',          'is_active': True},
            # 3
            {'name': 'Academic Director',   'code': 'ACADIR',      'department_code': 'ACADEMIC',    'is_teaching': True,  'is_management': True,  'rank_order': 3,  'min_salary': Decimal('1200000.00'), 'max_salary': Decimal('2500000.00'), 'description': 'Oversees academic programs and curriculum',          'is_active': True},

            # ── TEACHING (5) ───────────────────────────────────────────────────────
            # 4
            {'name': 'Head of Department',  'code': 'HOD',         'department_code': 'ACADEMIC',    'is_teaching': True,  'is_management': True,  'rank_order': 4,  'min_salary': Decimal('900000.00'),  'max_salary': Decimal('1600000.00'), 'description': 'Departmental lead with management responsibilities',  'is_active': True},
            # 5
            {'name': 'Senior Teacher',      'code': 'SRTEACH',     'department_code': 'ACADEMIC',    'is_teaching': True,  'is_management': False, 'rank_order': 5,  'min_salary': Decimal('800000.00'),  'max_salary': Decimal('1500000.00'), 'description': 'Experienced teacher with mentorship responsibilities', 'is_active': True},
            # 6
            {'name': 'Teacher',             'code': 'TEACHER',     'department_code': 'ACADEMIC',    'is_teaching': True,  'is_management': False, 'rank_order': 6,  'min_salary': Decimal('600000.00'),  'max_salary': Decimal('1200000.00'), 'description': 'Classroom teacher',                                   'is_active': True},
            # 7  NEW
            {'name': 'Assistant Teacher',   'code': 'ASST_TEACH',  'department_code': 'ACADEMIC',    'is_teaching': True,  'is_management': False, 'rank_order': 7,  'min_salary': Decimal('400000.00'),  'max_salary': Decimal('800000.00'),  'description': 'Assistant / junior classroom teacher',               'is_active': True},

            # ── ADMINISTRATIVE (4) ─────────────────────────────────────────────────
            # FIX: SCH_ADMIN was 'ADMIN' — clashed with ADMIN department code
            # 8
            {'name': 'School Administrator','code': 'SCH_ADMIN',   'department_code': 'ADMIN',       'is_teaching': False, 'is_management': True,  'rank_order': 8,  'min_salary': Decimal('700000.00'),  'max_salary': Decimal('1400000.00'), 'description': 'General school administration',                       'is_active': True},
            # 9
            {'name': 'School Secretary',    'code': 'SECRETARY',   'department_code': 'ADMIN',       'is_teaching': False, 'is_management': False, 'rank_order': 9,  'min_salary': Decimal('400000.00'),  'max_salary': Decimal('800000.00'),  'description': 'Administrative support and office management',        'is_active': True},
            # 10  NEW
            {'name': 'Registrar',           'code': 'REGISTRAR',   'department_code': 'REGISTRY',    'is_teaching': False, 'is_management': True,  'rank_order': 9,  'min_salary': Decimal('600000.00'),  'max_salary': Decimal('1200000.00'), 'description': 'Student records and admissions management',           'is_active': True},
            # 11  NEW
            {'name': 'Receptionist',        'code': 'RECEPT',      'department_code': 'ADMIN',       'is_teaching': False, 'is_management': False, 'rank_order': 10, 'min_salary': Decimal('350000.00'),  'max_salary': Decimal('700000.00'),  'description': 'Front desk and visitor management',                   'is_active': True},

            # ── FINANCE (3) ────────────────────────────────────────────────────────
            # 12
            {'name': 'Bursar',              'code': 'BURSAR',      'department_code': 'FINANCE',     'is_teaching': False, 'is_management': True,  'rank_order': 11, 'min_salary': Decimal('900000.00'),  'max_salary': Decimal('1800000.00'), 'description': 'Financial management and accounting',                 'is_active': True},
            # 13
            {'name': 'Accounts Clerk',      'code': 'ACCOUNTS',    'department_code': 'FINANCE',     'is_teaching': False, 'is_management': False, 'rank_order': 12, 'min_salary': Decimal('500000.00'),  'max_salary': Decimal('900000.00'),  'description': 'Financial record keeping and transactions',           'is_active': True},
            # 14  NEW
            {'name': 'Internal Auditor',    'code': 'INT_AUDIT',   'department_code': 'FINANCE',     'is_teaching': False, 'is_management': False, 'rank_order': 12, 'min_salary': Decimal('700000.00'),  'max_salary': Decimal('1300000.00'), 'description': 'Internal audit and financial controls',               'is_active': True},

            # ── PROCUREMENT (2) ────────────────────────────────────────────────────
            # 15
            {'name': 'Procurement Officer', 'code': 'PROCURE',     'department_code': 'PROCUREMENT', 'is_teaching': False, 'is_management': False, 'rank_order': 13, 'min_salary': Decimal('700000.00'),  'max_salary': Decimal('1300000.00'), 'description': 'Purchasing and vendor management',                    'is_active': True},
            # 16
            {'name': 'Storekeeper',         'code': 'STOREKEEPER', 'department_code': 'PROCUREMENT', 'is_teaching': False, 'is_management': False, 'rank_order': 14, 'min_salary': Decimal('400000.00'),  'max_salary': Decimal('750000.00'),  'description': 'Inventory and stores management',                     'is_active': True},

            # ── STUDENT SUPPORT (2) ────────────────────────────────────────────────
            # FIX: SCHL_COUNSEL was 'COUNSEL' — clashed with COUNSEL department code
            # 17
            {'name': 'Dean of Students',    'code': 'DEAN',        'department_code': 'STUDENT',     'is_teaching': False, 'is_management': True,  'rank_order': 15, 'min_salary': Decimal('800000.00'),  'max_salary': Decimal('1500000.00'), 'description': 'Student affairs and welfare management',              'is_active': True},
            # 18
            {'name': 'School Counselor',    'code': 'SCHL_COUNSEL','department_code': 'COUNSEL',     'is_teaching': False, 'is_management': False, 'rank_order': 16, 'min_salary': Decimal('600000.00'),  'max_salary': Decimal('1200000.00'), 'description': 'Student counseling and guidance',                     'is_active': True},

            # ── SPECIALIST SUPPORT (6) ─────────────────────────────────────────────
            # 19
            {'name': 'Librarian',           'code': 'LIBRAR',      'department_code': 'LIBRARY',     'is_teaching': False, 'is_management': False, 'rank_order': 17, 'min_salary': Decimal('500000.00'),  'max_salary': Decimal('1000000.00'), 'description': 'Library management and information services',         'is_active': True},
            # 20
            {'name': 'ICT Coordinator',     'code': 'ICTCOORD',    'department_code': 'ICT',         'is_teaching': False, 'is_management': False, 'rank_order': 18, 'min_salary': Decimal('600000.00'),  'max_salary': Decimal('1200000.00'), 'description': 'Technology coordination and support',                 'is_active': True},
            # 21  NEW
            {'name': 'Lab Technician',      'code': 'LAB_TECH',    'department_code': 'SCIENCE',     'is_teaching': False, 'is_management': False, 'rank_order': 18, 'min_salary': Decimal('500000.00'),  'max_salary': Decimal('900000.00'),  'description': 'Laboratory management and technical support',         'is_active': True},
            # 22
            {'name': 'School Nurse',        'code': 'NURSE',       'department_code': 'HEALTH',      'is_teaching': False, 'is_management': False, 'rank_order': 19, 'min_salary': Decimal('500000.00'),  'max_salary': Decimal('1000000.00'), 'description': 'Health services and medical care',                    'is_active': True},
            # 23  NEW
            {'name': 'Clinical Officer',    'code': 'CLIN_OFF',    'department_code': 'HEALTH',      'is_teaching': False, 'is_management': True,  'rank_order': 18, 'min_salary': Decimal('700000.00'),  'max_salary': Decimal('1400000.00'), 'description': 'Senior health officer for larger boarding schools',   'is_active': True},

            # ── OPERATIONAL STAFF (5) ──────────────────────────────────────────────
            # FIX: SEC_GUARD was 'SECURITY' — clashed with SECURITY department code
            # 24
            {'name': 'Security Guard',      'code': 'SEC_GUARD',   'department_code': 'SECURITY',    'is_teaching': False, 'is_management': False, 'rank_order': 20, 'min_salary': Decimal('300000.00'),  'max_salary': Decimal('600000.00'),  'description': 'School security and safety',                          'is_active': True},
            # 25
            {'name': 'Driver',              'code': 'DRIVER',      'department_code': 'TRANSPORT',   'is_teaching': False, 'is_management': False, 'rank_order': 21, 'min_salary': Decimal('350000.00'),  'max_salary': Decimal('700000.00'),  'description': 'School transport services',                           'is_active': True},
            # 26
            {'name': 'Groundskeeper',       'code': 'GROUNDS',     'department_code': 'MAINT',       'is_teaching': False, 'is_management': False, 'rank_order': 22, 'min_salary': Decimal('300000.00'),  'max_salary': Decimal('600000.00'),  'description': 'Grounds and facility maintenance',                    'is_active': True},
            # 27
            {'name': 'Cleaner',             'code': 'CLEANER',     'department_code': 'MAINT',       'is_teaching': False, 'is_management': False, 'rank_order': 23, 'min_salary': Decimal('250000.00'),  'max_salary': Decimal('500000.00'),  'description': 'School cleaning services',                            'is_active': True},
            # 28
            {'name': 'School Messenger',    'code': 'MESSENGER',   'department_code': 'ADMIN',       'is_teaching': False, 'is_management': False, 'rank_order': 24, 'min_salary': Decimal('250000.00'),  'max_salary': Decimal('500000.00'),  'description': 'Message delivery and errands',                        'is_active': True},

            # ── CATERING (4) ───────────────────────────────────────────────────────
            # 29
            {'name': 'Head Cook',           'code': 'HEAD_COOK',   'department_code': 'CATERING',    'is_teaching': False, 'is_management': True,  'rank_order': 25, 'min_salary': Decimal('500000.00'),  'max_salary': Decimal('900000.00'),  'description': 'Kitchen and catering management',                     'is_active': True},
            # 30
            {'name': 'School Cook',         'code': 'COOK',        'department_code': 'CATERING',    'is_teaching': False, 'is_management': False, 'rank_order': 26, 'min_salary': Decimal('350000.00'),  'max_salary': Decimal('700000.00'),  'description': 'Food preparation and cooking',                        'is_active': True},
            # 31
            {'name': 'Assistant Cook',      'code': 'AST_COOK',    'department_code': 'CATERING',    'is_teaching': False, 'is_management': False, 'rank_order': 27, 'min_salary': Decimal('300000.00'),  'max_salary': Decimal('550000.00'),  'description': 'Kitchen assistance and food prep',                    'is_active': True},
            # 32
            {'name': 'Kitchen Assistant',   'code': 'KITCHEN_AST', 'department_code': 'CATERING',    'is_teaching': False, 'is_management': False, 'rank_order': 28, 'min_salary': Decimal('250000.00'),  'max_salary': Decimal('500000.00'),  'description': 'Kitchen cleaning and support',                        'is_active': True},

            # ── BOARDING (4) ───────────────────────────────────────────────────────
            # 33
            {'name': 'Matron',              'code': 'MATRON',      'department_code': 'BOARDING',    'is_teaching': False, 'is_management': True,  'rank_order': 29, 'min_salary': Decimal('600000.00'),  'max_salary': Decimal('1200000.00'), 'description': 'Boarding hostel supervision and welfare',             'is_active': True},
            # 34
            {'name': 'Boarding Supervisor', 'code': 'BOARD_SUP',   'department_code': 'BOARDING',    'is_teaching': False, 'is_management': False, 'rank_order': 30, 'min_salary': Decimal('400000.00'),  'max_salary': Decimal('800000.00'),  'description': 'Boarding facility oversight',                         'is_active': True},
            # 35  NEW
            {'name': 'Dormitory Warden',    'code': 'DORM_WARD',   'department_code': 'BOARDING',    'is_teaching': False, 'is_management': False, 'rank_order': 31, 'min_salary': Decimal('350000.00'),  'max_salary': Decimal('650000.00'),  'description': 'Nightly dormitory supervision',                       'is_active': True},
            # 36
            {'name': 'Laundry Attendant',   'code': 'LAUNDRY',     'department_code': 'BOARDING',    'is_teaching': False, 'is_management': False, 'rank_order': 32, 'min_salary': Decimal('300000.00'),  'max_salary': Decimal('550000.00'),  'description': 'Laundry services for boarding',                       'is_active': True},
        ]


    # =========================================================================
    # DISPLAY GROUPS
    # =========================================================================

    @classmethod
    def get_display_groups(cls):
        """
        Fee display groups for invoice layout.

        IMPORTANT: Every 'display_group' string used in get_fee_categories()
        must exactly match one 'name' here. validate_config() checks this.
        Display groups must be seeded before fee categories during init.
        """
        return [
            {'name': 'Tuition & Academic Fees',   'description': 'Core academic fees and tuition',                          'display_order': 1,  'color_code': '#2E86AB', 'show_as_group': True,  'show_group_subtotal': True,  'is_active': True},
            {'name': 'Registration & Admission',   'description': 'One-time enrollment and admission fees',                 'display_order': 2,  'color_code': '#A23B72', 'show_as_group': True,  'show_group_subtotal': True,  'is_active': True},
            {'name': 'Boarding & Accommodation',   'description': 'Boarding fees and accommodation costs',                  'display_order': 3,  'color_code': '#F18F01', 'show_as_group': True,  'show_group_subtotal': True,  'is_active': True},
            {'name': 'Meals & Catering',           'description': 'Food and catering services',                             'display_order': 4,  'color_code': '#C73E1D', 'show_as_group': True,  'show_group_subtotal': True,  'is_active': True},
            {'name': 'Activities & Services',      'description': 'Extracurricular and support services',                   'display_order': 5,  'color_code': '#7209B7', 'show_as_group': True,  'show_group_subtotal': True,  'is_active': True},
            {'name': 'Transport & Travel',         'description': 'Transportation and travel costs',                        'display_order': 6,  'color_code': '#560BAD', 'show_as_group': True,  'show_group_subtotal': True,  'is_active': True},
            {'name': 'Technology & Equipment',     'description': 'IT services and equipment fees',                         'display_order': 7,  'color_code': '#264653', 'show_as_group': True,  'show_group_subtotal': True,  'is_active': True},
            {'name': 'Medical & Health',           'description': 'Health services and medical fees',                       'display_order': 8,  'color_code': '#2A9D8F', 'show_as_group': True,  'show_group_subtotal': True,  'is_active': True},
            {'name': 'Uniform & Supplies',         'description': 'School uniforms and supplies',                           'display_order': 9,  'color_code': '#E76F51', 'show_as_group': True,  'show_group_subtotal': True,  'is_active': True},
            {'name': 'Special Programs',           'description': 'Specialised courses and programs',                       'display_order': 10, 'color_code': '#F4A261', 'show_as_group': True,  'show_group_subtotal': True,  'is_active': True},
            {'name': 'Penalties & Adjustments',    'description': 'Late fees, penalties, and adjustments',                  'display_order': 11, 'color_code': '#E63946', 'show_as_group': False, 'show_group_subtotal': False, 'is_active': True},
            # NEW: PTA levies are a distinct income stream remitted separately
            {'name': 'PTA & Community',            'description': 'Parent-Teacher Association levies and community fees',   'display_order': 12, 'color_code': '#3D405B', 'show_as_group': True,  'show_group_subtotal': True,  'is_active': True},
        ]

    # =========================================================================
    # FEE CATEGORIES
    # =========================================================================

    @classmethod
    def get_fee_categories(cls, school):
        """
        Seed fee categories for a school.

        NOTES FOR THE INIT COMMAND
        --------------------------
        display_group is a string name. The init command must resolve it to a
        DisplayGroup FK via DisplayGroup.objects.get(name=...) AFTER display
        groups have been seeded. Validate that every name here exists in
        get_display_groups() by calling validate_config() before seeding.

        is_refundable is omitted when it equals the model default (True).
        The model's clean() enforces DEPOSIT=True and PENALTY/PTA=False
        automatically, so these are explicit here for clarity.

        is_recurring is omitted — the model's save() auto-sets it to False for
        ONE_TIME and PER_INCIDENT frequencies.
        """
        cats = [
            # ── TUITION & ACADEMIC FEES ────────────────────────────────────────
            {
                'name': 'Tuition Fee',              'code': 'TUITION',
                'category_type': 'TUITION',         'frequency': 'TERMLY',
                'applicability': 'ALL',             'is_mandatory': True,
                'allows_partial_payment': True,
                'display_group': 'Tuition & Academic Fees',
                'description': 'Core academic fees and instruction',
            },
            {
                # FIX: was OTHER — TUITION aggregates correctly in revenue reports
                'name': 'Academic Enhancement Fee', 'code': 'ACADEMIC_ENH',
                'category_type': 'TUITION',         'frequency': 'TERMLY',
                'applicability': 'ALL',             'is_mandatory': False,
                'allows_partial_payment': True,
                'display_group': 'Tuition & Academic Fees',
                'description': 'Additional academic support and enrichment',
            },
            {
                'name': 'Examination Fee',          'code': 'EXAM',
                'category_type': 'EXAM',            'frequency': 'TERMLY',
                'applicability': 'ALL',             'is_mandatory': True,
                'allows_partial_payment': True,
                'display_group': 'Tuition & Academic Fees',
                'description': 'Internal and external examination fees',
            },
            {
                'name': 'Development Fee',          'code': 'DEV',
                'category_type': 'DEVELOPMENT',     'frequency': 'YEARLY',
                'applicability': 'ALL',             'is_mandatory': True,
                'allows_partial_payment': True,
                'display_group': 'Tuition & Academic Fees',
                'description': 'School infrastructure development projects',
            },
            {
                'name': 'Laboratory Fee',           'code': 'LAB',
                'category_type': 'LABORATORY',      'frequency': 'TERMLY',
                'applicability': 'SCIENCE_STUDENTS','is_mandatory': True,
                'allows_partial_payment': True,
                'display_group': 'Tuition & Academic Fees',
                'description': 'Science lab usage and consumables',
            },
            {
                # FIX: was OTHER — routes to EXAM revenue, PER_INCIDENT now valid
                'name': 'Re-examination Fee',       'code': 'RETAKE_EXAM',
                'category_type': 'EXAM',            'frequency': 'PER_INCIDENT',
                'applicability': 'ALL',             'is_mandatory': False,
                'is_refundable': False,
                'allows_partial_payment': False,
                'display_group': 'Tuition & Academic Fees',
                'description': 'Fee charged each time a student retakes an internal examination',
            },

            # ── REGISTRATION & ADMISSION ───────────────────────────────────────
            {
                'name': 'Registration Fee',         'code': 'REG',
                'category_type': 'REGISTRATION',    'frequency': 'ONE_TIME',
                'applicability': 'NEW_STUDENTS',    'is_mandatory': True,
                'is_refundable': False,
                'allows_partial_payment': False,
                'display_group': 'Registration & Admission',
                'description': 'One-time student registration fee',
            },
            {
                'name': 'Admission Fee',            'code': 'ADMISSION',
                'category_type': 'ADMISSION',       'frequency': 'ONE_TIME',
                'applicability': 'NEW_STUDENTS',    'is_mandatory': True,
                'is_refundable': False,
                'allows_partial_payment': False,
                'display_group': 'Registration & Admission',
                'description': 'Admission processing and assessment',
            },
            {
                # FIX: was OTHER — REGISTRATION is semantically correct here
                # FIX: applicability was 'APPLICANTS' (not in model choices) → NEW_STUDENTS
                'name': 'Application Fee',          'code': 'APPLICATION',
                'category_type': 'REGISTRATION',    'frequency': 'ONE_TIME',
                'applicability': 'NEW_STUDENTS',    'is_mandatory': True,
                'is_refundable': False,
                'allows_partial_payment': False,
                'display_group': 'Registration & Admission',
                'description': 'Application processing fee',
            },
            {
                'name': 'Graduation Fee',           'code': 'GRADUATION',
                'category_type': 'GRADUATION',      'frequency': 'ONE_TIME',
                'applicability': 'CONTINUING_STUDENTS', 'is_mandatory': True,
                'is_refundable': False,
                'allows_partial_payment': False,
                'display_group': 'Registration & Admission',
                'description': 'Graduation ceremony and certificate fee',
            },
            {
                'name': 'School Leaving Certificate','code': 'LEAVING_CERT',
                'category_type': 'OTHER',           'frequency': 'ONE_TIME',
                'applicability': 'CONTINUING_STUDENTS', 'is_mandatory': False,
                'is_refundable': False,
                'allows_partial_payment': False,
                'display_group': 'Registration & Admission',
                'description': 'School leaving certificate and clearance fee',
            },

            # ── BOARDING & ACCOMMODATION ───────────────────────────────────────
            {
                'name': 'Boarding Fee',             'code': 'BOARD',
                'category_type': 'BOARDING',        'frequency': 'TERMLY',
                'applicability': 'BOARDERS',        'is_mandatory': True,
                'allows_partial_payment': True,
                'display_group': 'Boarding & Accommodation',
                'description': 'Boarding accommodation fee',
            },
            {
                # FIX: was OTHER — DEPOSIT routes to liability account, not revenue.
                # The model's clean() enforces is_refundable=True and
                # allows_partial_payment=False for DEPOSIT type automatically.
                'name': 'Accommodation Deposit',    'code': 'ACCOM_DEPOSIT',
                'category_type': 'DEPOSIT',         'frequency': 'ONE_TIME',
                'applicability': 'BOARDERS',        'is_mandatory': True,
                'is_refundable': True,
                'allows_partial_payment': False,
                'display_group': 'Boarding & Accommodation',
                'description': 'Refundable security deposit held against boarding damage',
            },
            {
                # NEW: separate from Accommodation Deposit — covers breakages/damage
                'name': 'Caution Money',            'code': 'CAUTION',
                'category_type': 'DEPOSIT',         'frequency': 'ONE_TIME',
                'applicability': 'ALL',             'is_mandatory': True,
                'is_refundable': True,
                'allows_partial_payment': False,
                'display_group': 'Boarding & Accommodation',
                'description': 'Refundable caution deposit held against school property damage',
            },
            {
                'name': 'Laundry Fee',              'code': 'LAUNDRY',
                'category_type': 'LAUNDRY',         'frequency': 'TERMLY',
                'applicability': 'BOARDERS',        'is_mandatory': False,
                'allows_partial_payment': True,
                'display_group': 'Boarding & Accommodation',
                'description': 'Boarding laundry services',
            },

            # ── MEALS & CATERING ───────────────────────────────────────────────
            {
                'name': 'Meals Fee',                'code': 'MEALS',
                'category_type': 'MEALS',           'frequency': 'TERMLY',
                'applicability': 'BOARDERS',        'is_mandatory': True,
                'allows_partial_payment': True,
                'display_group': 'Meals & Catering',
                'description': 'Full board meal service',
            },
            {
                'name': 'Day Scholar Meals',        'code': 'DAY_MEALS',
                'category_type': 'MEALS',           'frequency': 'TERMLY',
                'applicability': 'DAY_SCHOLARS',    'is_mandatory': False,
                'allows_partial_payment': True,
                'display_group': 'Meals & Catering',
                'description': 'Optional lunch service for day scholars',
            },
            {
                'name': 'Breakfast Only',           'code': 'BREAKFAST',
                'category_type': 'MEALS',           'frequency': 'TERMLY',
                'applicability': 'OPTIONAL',        'is_mandatory': False,
                'allows_partial_payment': True,
                'display_group': 'Meals & Catering',
                'description': 'Breakfast-only meal plan',
            },

            # ── ACTIVITIES & SERVICES ──────────────────────────────────────────
            {
                'name': 'Library Fee',              'code': 'LIB',
                'category_type': 'LIBRARY',         'frequency': 'YEARLY',
                'applicability': 'ALL',             'is_mandatory': True,
                'allows_partial_payment': True,
                'display_group': 'Activities & Services',
                'description': 'Library access and services',
            },
            {
                'name': 'Sports Fee',               'code': 'SPORTS',
                'category_type': 'SPORT',           'frequency': 'YEARLY',
                'applicability': 'ALL',             'is_mandatory': False,
                'allows_partial_payment': True,
                'display_group': 'Activities & Services',
                'description': 'Sports and physical education activities',
            },
            {
                'name': 'Student ID Card',          'code': 'ID_CARD',
                'category_type': 'OTHER',           'frequency': 'YEARLY',
                'applicability': 'ALL',             'is_mandatory': True,
                'allows_partial_payment': False,
                'display_group': 'Activities & Services',
                'description': 'Student identification card',
            },
            {
                'name': 'Music & Drama',            'code': 'MUSIC_DRAMA',
                'category_type': 'CLUB',            'frequency': 'TERMLY',
                'applicability': 'OPTIONAL',        'is_mandatory': False,
                'allows_partial_payment': True,
                'display_group': 'Activities & Services',
                'description': 'Music, drama, and performing arts activities',
            },
            {
                'name': 'Clubs & Societies',        'code': 'CLUBS',
                'category_type': 'CLUB',            'frequency': 'TERMLY',
                'applicability': 'OPTIONAL',        'is_mandatory': False,
                'allows_partial_payment': True,
                'display_group': 'Activities & Services',
                'description': 'Student clubs and co-curricular activities',
            },
            {
                # NEW
                'name': 'School Photos',            'code': 'PHOTOS',
                'category_type': 'PHOTO',           'frequency': 'YEARLY',
                'applicability': 'ALL',             'is_mandatory': False,
                'allows_partial_payment': False,
                'display_group': 'Activities & Services',
                'description': 'Annual school photography fee',
            },
            {
                # NEW
                'name': 'School Magazine / Yearbook','code': 'MAGAZINE',
                'category_type': 'PUBLICATION',     'frequency': 'YEARLY',
                'applicability': 'ALL',             'is_mandatory': False,
                'allows_partial_payment': False,
                'display_group': 'Activities & Services',
                'description': 'School magazine, yearbook, or diary publication fee',
            },

            # ── TRANSPORT & TRAVEL ─────────────────────────────────────────────
            {
                'name': 'Transport Fee',            'code': 'TRANS',
                'category_type': 'TRANSPORT',       'frequency': 'TERMLY',
                'applicability': 'TRANSPORT_USERS', 'is_mandatory': False,
                'allows_partial_payment': True,
                'display_group': 'Transport & Travel',
                'description': 'School bus service',
            },
            {
                'name': 'Field Trip Fee',           'code': 'FIELD_TRIP',
                'category_type': 'FIELD_TRIP',      'frequency': 'TERMLY',
                'applicability': 'PARTICIPANTS',    'is_mandatory': False,
                'allows_partial_payment': True,
                'display_group': 'Transport & Travel',
                'description': 'Educational field trip fee',
            },

            # ── TECHNOLOGY & EQUIPMENT ─────────────────────────────────────────
            {
                'name': 'Computer Fee',             'code': 'COMPUTER',
                'category_type': 'TECHNOLOGY',      'frequency': 'TERMLY',
                'applicability': 'ICT_STUDENTS',    'is_mandatory': True,
                'allows_partial_payment': True,
                'display_group': 'Technology & Equipment',
                'description': 'Computer lab usage and ICT resources',
            },
            {
                'name': 'Internet & WiFi Fee',      'code': 'INTERNET',
                'category_type': 'TECHNOLOGY',      'frequency': 'TERMLY',
                'applicability': 'ALL',             'is_mandatory': False,
                'allows_partial_payment': True,
                'display_group': 'Technology & Equipment',
                'description': 'Campus internet and WiFi access',
            },

            # ── MEDICAL & HEALTH ───────────────────────────────────────────────
            {
                'name': 'Medical Fee',              'code': 'MED',
                'category_type': 'MEDICAL',         'frequency': 'YEARLY',
                'applicability': 'ALL',             'is_mandatory': False,
                'allows_partial_payment': True,
                'display_group': 'Medical & Health',
                'description': 'Basic school clinic and medical services',
            },
            {
                'name': 'Health Insurance',         'code': 'HEALTH_INS',
                'category_type': 'INSURANCE',       'frequency': 'YEARLY',
                'applicability': 'ALL',             'is_mandatory': False,
                'allows_partial_payment': True,
                'display_group': 'Medical & Health',
                'description': 'Student health insurance cover',
            },
            {
                # NEW
                'name': 'Mental Health / Counseling','code': 'MENTAL_HEALTH',
                'category_type': 'MEDICAL',          'frequency': 'TERMLY',
                'applicability': 'OPTIONAL',         'is_mandatory': False,
                'allows_partial_payment': True,
                'display_group': 'Medical & Health',
                'description': 'Professional counseling and mental health support services',
            },

            # ── UNIFORM & SUPPLIES ─────────────────────────────────────────────
            {
                'name': 'School Uniform',           'code': 'UNIFORM',
                'category_type': 'UNIFORM',         'frequency': 'YEARLY',
                'applicability': 'ALL',             'is_mandatory': True,
                'allows_partial_payment': True,
                'display_group': 'Uniform & Supplies',
                'description': 'Official school uniform set',
            },
            {
                # NEW — separate revenue line from school uniform
                'name': 'Sports Kit / PE Uniform',  'code': 'SPORTS_KIT',
                'category_type': 'UNIFORM',         'frequency': 'YEARLY',
                'applicability': 'ALL',             'is_mandatory': False,
                'allows_partial_payment': True,
                'display_group': 'Uniform & Supplies',
                'description': 'Sports kit and physical education uniform',
            },
            {
                'name': 'Textbooks',                'code': 'TEXTBOOKS',
                'category_type': 'BOOKS',           'frequency': 'YEARLY',
                'applicability': 'ALL',             'is_mandatory': False,
                'allows_partial_payment': True,
                'display_group': 'Uniform & Supplies',
                'description': 'Required course textbooks',
            },
            {
                # FIX: was OTHER — BOOKS is more specific and routes correctly
                'name': 'Stationery Pack',          'code': 'STATIONERY',
                'category_type': 'BOOKS',           'frequency': 'TERMLY',
                'applicability': 'ALL',             'is_mandatory': False,
                'allows_partial_payment': True,
                'display_group': 'Uniform & Supplies',
                'description': 'Termly stationery supply pack',
            },

            # ── SPECIAL PROGRAMS ───────────────────────────────────────────────
            {
                # FIX: was OTHER — TUITION is correct since this is instruction
                'name': 'Remedial Classes',         'code': 'REMEDIAL',
                'category_type': 'TUITION',         'frequency': 'TERMLY',
                'applicability': 'OPTIONAL',        'is_mandatory': False,
                'allows_partial_payment': True,
                'display_group': 'Special Programs',
                'description': 'Additional remedial or extra tuition classes',
            },

            # ── PENALTIES & ADJUSTMENTS ────────────────────────────────────────
            {
                'name': 'Late Payment Penalty',     'code': 'LATE_PENALTY',
                'category_type': 'LATE_PAYMENT',    'frequency': 'MONTHLY',
                'applicability': 'DEFAULTERS',      'is_mandatory': True,
                'is_refundable': False,
                'allows_partial_payment': False,
                'display_group': 'Penalties & Adjustments',
                'description': 'Penalty charge for late fee payment',
            },
            {
                # FIX: frequency was 'PER_INCIDENT' (now valid from model rewrite)
                'name': 'Replacement Fee',          'code': 'REPLACEMENT',
                'category_type': 'OTHER',           'frequency': 'PER_INCIDENT',
                'applicability': 'ALL',             'is_mandatory': True,
                'is_refundable': False,
                'allows_partial_payment': False,
                'display_group': 'Penalties & Adjustments',
                'description': 'Charged each time a student needs to replace a lost or damaged item',
            },

            # ── PTA & COMMUNITY ────────────────────────────────────────────────
            {
                # NEW — PTA levies route to a separate income line and are
                # remitted to the PTA; is_refundable=False is required by the
                # model's clean() for PTA type
                'name': 'PTA Levy',                 'code': 'PTA_LEVY',
                'category_type': 'PTA',             'frequency': 'TERMLY',
                'applicability': 'ALL',             'is_mandatory': True,
                'is_refundable': False,
                'allows_partial_payment': True,
                'display_group': 'PTA & Community',
                'description': 'Parent-Teacher Association levy remitted to the PTA',
            },
        ]

        return cats

    # =========================================================================
    # PAYMENT METHODS
    # =========================================================================

    @classmethod
    def get_payment_methods(cls):
        """
        Default payment methods.

        FIX: Added missing fields across all methods:
          requires_reference — True for BANK_TRANSFER and CHECK (bank-based
            methods without a reference number cannot be reconciled).
            The PaymentMethod.save() also auto-sets this for new records,
            but being explicit here makes the intent clear.
          minimum_amount / maximum_amount — real-world limits for mobile money.
            Uganda MTN/Airtel: min ~500 UGX, max ~5,000,000 UGX per transaction.
          processing_time — displayed to cashiers when recording payments.
        """
        return [
            {
                'name': 'Cash Payment',
                'code': 'CASH',
                'method_type': 'CASH',
                'instructions': 'Physical cash payments at the school bursar office. Collect and issue receipt immediately.',
                'processing_time': 'Instant',
                'is_active': True,
                'is_default': True,
                'requires_approval': False,
                'requires_reference': False,
                'display_order': 1,
                'icon': 'fa-money-bill-wave',
                'color_code': '#28a745',
            },
            {
                'name': 'Bank Transfer',
                'code': 'BANK_TRANSFER',
                'method_type': 'BANK_TRANSFER',
                'instructions': 'Electronic bank transfer directly to the school bank account. Use student name and admission number as reference.',
                'processing_time': '1–3 business days',
                # FIX: requires_reference must be True — bank transfers without a
                # reference cannot be matched to a student during reconciliation.
                'requires_reference': True,
                'is_active': True,
                'is_default': False,
                'requires_approval': True,
                'display_order': 2,
                'icon': 'fa-university',
                'color_code': '#007bff',
            },
            {
                'name': 'MTN Mobile Money',
                'code': 'MTN_MOBILE',
                'method_type': 'MOBILE_MONEY',
                'mobile_money_provider': 'MTN',
                'instructions': 'MTN Mobile Money via *165#. Use student admission number as payment reference.',
                'processing_time': 'Instant',
                'is_active': True,
                'is_default': False,
                'requires_approval': False,
                'requires_reference': False,
                'has_transaction_fee': True,
                'transaction_fee_type': 'PERCENTAGE',
                'transaction_fee_amount': Decimal('1.5'),
                'fee_bearer': 'PARENT',
                # Uganda MTN limits (approximate — verify with current MTN schedule)
                'minimum_amount': Decimal('500.00'),
                'maximum_amount': Decimal('5000000.00'),
                'display_order': 3,
                'icon': 'fa-mobile-alt',
                'color_code': '#ffcc00',
            },
            {
                'name': 'Airtel Money',
                'code': 'AIRTEL_MOBILE',
                'method_type': 'MOBILE_MONEY',
                'mobile_money_provider': 'AIRTEL',
                'instructions': 'Airtel Money via *185#. Use student admission number as payment reference.',
                'processing_time': 'Instant',
                'is_active': True,
                'is_default': False,
                'requires_approval': False,
                'requires_reference': False,
                'has_transaction_fee': True,
                'transaction_fee_type': 'PERCENTAGE',
                'transaction_fee_amount': Decimal('1.5'),
                'fee_bearer': 'PARENT',
                'minimum_amount': Decimal('500.00'),
                'maximum_amount': Decimal('5000000.00'),
                'display_order': 4,
                'icon': 'fa-mobile-alt',
                'color_code': '#ff6b35',
            },
            {
                'name': 'Bank Cheque',
                'code': 'CHECK',
                'method_type': 'CHEQUE',
                'instructions': 'Bank cheques made payable to the school. Attach the cheque stub as reference.',
                'processing_time': '3–5 business days',
                # FIX: requires_reference must be True — cheque number is essential
                # for reconciliation when a cheque bounces or is delayed.
                'requires_reference': True,
                'is_active': True,
                'is_default': False,
                'requires_approval': True,
                'display_order': 5,
                'icon': 'fa-money-check',
                'color_code': '#6c757d',
            },
            {
                'name': 'Credit / Debit Card',
                'code': 'CARD',
                'method_type': 'CARD',
                'instructions': 'Visa, MasterCard, and local debit cards accepted at the bursar office POS terminal.',
                'processing_time': 'Instant',
                'is_active': True,
                'is_default': False,
                'requires_approval': False,
                'requires_reference': False,
                'has_transaction_fee': True,
                'transaction_fee_type': 'PERCENTAGE',
                'transaction_fee_amount': Decimal('2.5'),
                'fee_bearer': 'PARENT',
                'display_order': 6,
                'icon': 'fa-credit-card',
                'color_code': '#17a2b8',
            },
        ]

    # =========================================================================
    # TAX RATES
    # =========================================================================

    @classmethod
    def get_tax_rates(cls, school=None):
        """
        Default tax rates by country.

        NOTE: applies_to_fees=False on all entries is INTENTIONAL.
        School fees in Uganda (and most East African countries) are VAT-exempt.
        These rates exist for non-fee revenue (e.g. canteen sales, commercial
        printing). Flipping applies_to_fees=True will incorrectly add VAT to
        student invoices.
        """
        from datetime import date

        country = str(school.country) if school and school.country else 'UG'

        if country == 'UG':
            return [
                {
                    'name': 'VAT - Uganda',
                    'tax_type': 'VAT',
                    'rate': Decimal('18.00'),
                    'effective_from': date(2024, 1, 1),
                    'effective_to': None,
                    'is_active': True,
                    # Intentionally False — school fees are VAT-exempt in Uganda
                    'applies_to_fees': False,
                    'applies_to_services': True,
                    'description': 'Value Added Tax in Uganda (school fees are VAT-exempt)',
                    'legal_reference': 'VAT Act (Cap 349)',
                },
                {
                    'name': 'Withholding Tax - Interest',
                    'tax_type': 'WHT_INTEREST',
                    'rate': Decimal('15.00'),
                    'effective_from': date(2024, 1, 1),
                    'effective_to': None,
                    'is_active': True,
                    'applies_to_fees': False,
                    'applies_to_services': False,
                    'description': 'Withholding tax on interest income',
                    'legal_reference': 'Income Tax Act',
                },
            ]

        if country == 'KE':
            return [
                {
                    'name': 'VAT - Kenya',
                    'tax_type': 'VAT',
                    'rate': Decimal('16.00'),
                    'effective_from': date(2024, 1, 1),
                    'effective_to': None,
                    'is_active': True,
                    'applies_to_fees': False,
                    'applies_to_services': True,
                    'description': 'Value Added Tax in Kenya (school fees are VAT-exempt)',
                },
            ]

        # Generic fallback
        return [
            {
                'name': 'Standard VAT',
                'tax_type': 'VAT',
                'rate': Decimal('18.00'),
                'effective_from': date(2024, 1, 1),
                'effective_to': None,
                'is_active': True,
                'applies_to_fees': False,
                'applies_to_services': True,
                'description': 'Standard Value Added Tax (school fees may be exempt — verify locally)',
            },
        ]

    # =========================================================================
    # UNITS OF MEASURE
    # =========================================================================

    @classmethod
    def get_units_of_measure(cls):
        """
        Comprehensive units of measurement for inventory, procurement, and catering.

        NEW units added:
          Jerrycan (20 L) — ubiquitous in Uganda for fuel and water storage
          Gross            — 144 units, bulk stationery procurement
          Tray             — eggs, seedlings, lab specimens
          Portion/Serving  — catering quantities per student
          Dose/Tablet/Capsule — clinic/medical supplies
          Lesson/Period    — service unit for contracted tutors, remedial classes
        """
        return [
            # ── BASE UNITS ─────────────────────────────────────────────────────
            {'name': 'Each',           'abbreviation': 'ea',     'symbol': 'ea',  'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'),        'description': 'Individual item',          'is_active': True},
            {'name': 'Kilogram',       'abbreviation': 'kg',     'symbol': 'kg',  'uom_type': 'WEIGHT',   'conversion_factor': Decimal('1.0'),        'description': 'Base unit of mass',        'is_active': True},
            {'name': 'Meter',          'abbreviation': 'm',      'symbol': 'm',   'uom_type': 'LENGTH',   'conversion_factor': Decimal('1.0'),        'description': 'Base unit of length',      'is_active': True},
            {'name': 'Liter',          'abbreviation': 'L',      'symbol': 'L',   'uom_type': 'VOLUME',   'conversion_factor': Decimal('1.0'),        'description': 'Base unit of volume',      'is_active': True},
            {'name': 'Day',            'abbreviation': 'day',    'symbol': 'd',   'uom_type': 'TIME',     'conversion_factor': Decimal('1.0'),        'description': 'Base unit of time',        'is_active': True},
            {'name': 'Square Meter',   'abbreviation': 'm²',     'symbol': 'm²',  'uom_type': 'AREA',     'conversion_factor': Decimal('1.0'),        'description': 'Base unit of area',        'is_active': True},
            # ── LENGTH ─────────────────────────────────────────────────────────
            {'name': 'Kilometer',      'abbreviation': 'km',     'symbol': 'km',  'uom_type': 'LENGTH',   'conversion_factor': Decimal('1000.0'),     'description': '1000 meters',              'is_active': True},
            {'name': 'Centimeter',     'abbreviation': 'cm',     'symbol': 'cm',  'uom_type': 'LENGTH',   'conversion_factor': Decimal('0.01'),       'description': '0.01 meters',              'is_active': True},
            {'name': 'Millimeter',     'abbreviation': 'mm',     'symbol': 'mm',  'uom_type': 'LENGTH',   'conversion_factor': Decimal('0.001'),      'description': '0.001 meters',             'is_active': True},
            {'name': 'Inch',           'abbreviation': 'in',     'symbol': 'in',  'uom_type': 'LENGTH',   'conversion_factor': Decimal('0.0254'),     'description': '0.0254 meters',            'is_active': True},
            {'name': 'Foot',           'abbreviation': 'ft',     'symbol': 'ft',  'uom_type': 'LENGTH',   'conversion_factor': Decimal('0.3048'),     'description': '0.3048 meters',            'is_active': True},
            {'name': 'Yard',           'abbreviation': 'yd',     'symbol': 'yd',  'uom_type': 'LENGTH',   'conversion_factor': Decimal('0.9144'),     'description': '0.9144 meters',            'is_active': True},
            # ── WEIGHT ─────────────────────────────────────────────────────────
            {'name': 'Gram',           'abbreviation': 'g',      'symbol': 'g',   'uom_type': 'WEIGHT',   'conversion_factor': Decimal('0.001'),      'description': '0.001 kilograms',          'is_active': True},
            {'name': 'Milligram',      'abbreviation': 'mg',     'symbol': 'mg',  'uom_type': 'WEIGHT',   'conversion_factor': Decimal('0.000001'),   'description': '0.000001 kilograms',       'is_active': True},
            {'name': 'Ton',            'abbreviation': 't',      'symbol': 't',   'uom_type': 'WEIGHT',   'conversion_factor': Decimal('1000.0'),     'description': '1000 kilograms',           'is_active': True},
            {'name': 'Pound',          'abbreviation': 'lb',     'symbol': 'lb',  'uom_type': 'WEIGHT',   'conversion_factor': Decimal('0.453592'),   'description': '0.453592 kilograms',       'is_active': True},
            {'name': 'Ounce',          'abbreviation': 'oz',     'symbol': 'oz',  'uom_type': 'WEIGHT',   'conversion_factor': Decimal('0.028350'),   'description': '0.028350 kilograms',       'is_active': True},
            # ── VOLUME ─────────────────────────────────────────────────────────
            {'name': 'Milliliter',     'abbreviation': 'mL',     'symbol': 'mL',  'uom_type': 'VOLUME',   'conversion_factor': Decimal('0.001'),      'description': '0.001 liters',             'is_active': True},
            {'name': 'US Gallon',      'abbreviation': 'gal',    'symbol': 'gal', 'uom_type': 'VOLUME',   'conversion_factor': Decimal('3.78541'),    'description': '3.78541 liters',           'is_active': True},
            {'name': 'Cup',            'abbreviation': 'cup',    'symbol': 'c',   'uom_type': 'VOLUME',   'conversion_factor': Decimal('0.236588'),   'description': '0.236588 liters',          'is_active': True},
            {'name': 'Tablespoon',     'abbreviation': 'tbsp',   'symbol': 'tbsp','uom_type': 'VOLUME',   'conversion_factor': Decimal('0.014787'),   'description': '0.014787 liters',          'is_active': True},
            {'name': 'Teaspoon',       'abbreviation': 'tsp',    'symbol': 'tsp', 'uom_type': 'VOLUME',   'conversion_factor': Decimal('0.004929'),   'description': '0.004929 liters',          'is_active': True},
            # NEW — Jerrycan: ubiquitous in Uganda for fuel and water storage
            {'name': 'Jerrycan (20 L)','abbreviation': 'jrcan',  'symbol': 'jrcan','uom_type': 'VOLUME',  'conversion_factor': Decimal('20.0'),       'description': '20-liter jerrycan — common unit for fuel and water procurement in Uganda', 'is_active': True},
            # ── TIME ───────────────────────────────────────────────────────────
            {'name': 'Second',         'abbreviation': 's',      'symbol': 's',   'uom_type': 'TIME',     'conversion_factor': Decimal('0.000012'),   'description': 'Fraction of day (1/86400)','is_active': True},
            {'name': 'Minute',         'abbreviation': 'min',    'symbol': 'min', 'uom_type': 'TIME',     'conversion_factor': Decimal('0.000694'),   'description': 'Fraction of day (1/1440)', 'is_active': True},
            {'name': 'Hour',           'abbreviation': 'hr',     'symbol': 'h',   'uom_type': 'TIME',     'conversion_factor': Decimal('0.041667'),   'description': 'Fraction of day (1/24)',   'is_active': True},
            {'name': 'Week',           'abbreviation': 'wk',     'symbol': 'wk',  'uom_type': 'TIME',     'conversion_factor': Decimal('7.0'),        'description': '7 days',                   'is_active': True},
            {'name': 'Month',          'abbreviation': 'mo',     'symbol': 'mo',  'uom_type': 'TIME',     'conversion_factor': Decimal('30.44'),      'description': '30.44 days average',       'is_active': True},
            {'name': 'Year',           'abbreviation': 'yr',     'symbol': 'yr',  'uom_type': 'TIME',     'conversion_factor': Decimal('365.24'),     'description': '365.24 days',              'is_active': True},
            # NEW — service unit for contracted tutors, remedial classes
            {'name': 'Lesson / Period','abbreviation': 'lesson', 'symbol': 'lsn', 'uom_type': 'TIME',     'conversion_factor': Decimal('0.028'),      'description': 'Single teaching period (~40 min). Use for contracted tutors and remedial class billing.', 'is_active': True},
            # ── AREA ───────────────────────────────────────────────────────────
            {'name': 'Square Centimeter','abbreviation': 'cm²',  'symbol': 'cm²', 'uom_type': 'AREA',     'conversion_factor': Decimal('0.0001'),     'description': '0.0001 square meters',     'is_active': True},
            {'name': 'Square Foot',    'abbreviation': 'sq ft',  'symbol': 'ft²', 'uom_type': 'AREA',     'conversion_factor': Decimal('0.092903'),   'description': '0.092903 square meters',   'is_active': True},
            {'name': 'Acre',           'abbreviation': 'ac',     'symbol': 'ac',  'uom_type': 'AREA',     'conversion_factor': Decimal('4046.86'),    'description': '4046.86 square meters',    'is_active': True},
            {'name': 'Hectare',        'abbreviation': 'ha',     'symbol': 'ha',  'uom_type': 'AREA',     'conversion_factor': Decimal('10000.0'),    'description': '10000 square meters',      'is_active': True},
            # ── QUANTITY — general ─────────────────────────────────────────────
            {'name': 'Piece',          'abbreviation': 'pc',     'symbol': 'pc',  'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'),        'description': 'Single item',              'is_active': True},
            {'name': 'Dozen',          'abbreviation': 'doz',    'symbol': 'dz',  'uom_type': 'QUANTITY', 'conversion_factor': Decimal('12.0'),       'description': '12 units',                 'is_active': True},
            # NEW — Gross: 144 units, standard bulk for pens, pencils, exercise books
            {'name': 'Gross',          'abbreviation': 'gr',     'symbol': 'gr',  'uom_type': 'QUANTITY', 'conversion_factor': Decimal('144.0'),      'description': '144 units (12 dozen). Common bulk unit for stationery procurement.', 'is_active': True},
            {'name': 'Pair',           'abbreviation': 'pr',     'symbol': 'pr',  'uom_type': 'QUANTITY', 'conversion_factor': Decimal('2.0'),        'description': '2 units',                  'is_active': True},
            {'name': 'Set',            'abbreviation': 'set',    'symbol': 'set', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'),        'description': 'Complete set',             'is_active': True},
            {'name': 'Pack',           'abbreviation': 'pack',   'symbol': 'pk',  'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'),        'description': 'Package of items',         'is_active': True},
            {'name': 'Packet',         'abbreviation': 'pkt',    'symbol': 'pkt', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'),        'description': 'Packet of items',          'is_active': True},
            {'name': 'Box',            'abbreviation': 'box',    'symbol': 'box', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'),        'description': 'Box of items',             'is_active': True},
            {'name': 'Carton',         'abbreviation': 'ctn',    'symbol': 'ctn', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'),        'description': 'Carton container',         'is_active': True},
            {'name': 'Crate',          'abbreviation': 'crt',    'symbol': 'crt', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'),        'description': 'Crate container',          'is_active': True},
            {'name': 'Bundle',         'abbreviation': 'bundle', 'symbol': 'bndl','uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'),        'description': 'Bundle of items',          'is_active': True},
            {'name': 'Roll',           'abbreviation': 'roll',   'symbol': 'roll','uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'),        'description': 'Roll of material',         'is_active': True},
            {'name': 'Sheet',          'abbreviation': 'sheet',  'symbol': 'sht', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'),        'description': 'Single sheet',             'is_active': True},
            {'name': 'Ream',           'abbreviation': 'ream',   'symbol': 'rm',  'uom_type': 'QUANTITY', 'conversion_factor': Decimal('500.0'),      'description': '500 sheets of paper',      'is_active': True},
            {'name': 'Book',           'abbreviation': 'book',   'symbol': 'bk',  'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'),        'description': 'Single book',              'is_active': True},
            {'name': 'Bottle',         'abbreviation': 'bottle', 'symbol': 'btl', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'),        'description': 'Bottle container',         'is_active': True},
            {'name': 'Can',            'abbreviation': 'can',    'symbol': 'can', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'),        'description': 'Can or tin',               'is_active': True},
            {'name': 'Bag',            'abbreviation': 'bag',    'symbol': 'bag', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'),        'description': 'Bag or small sack',        'is_active': True},
            {'name': 'Sack',           'abbreviation': 'sack',   'symbol': 'sack','uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'),        'description': 'Large sack (50 kg rice, posho)',  'is_active': True},
            {'name': 'Tube',           'abbreviation': 'tube',   'symbol': 'tube','uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'),        'description': 'Tube container',           'is_active': True},
            {'name': 'Jar',            'abbreviation': 'jar',    'symbol': 'jar', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'),        'description': 'Jar container',            'is_active': True},
            {'name': 'Drum',           'abbreviation': 'drum',   'symbol': 'drum','uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'),        'description': 'Large drum (200 L)',       'is_active': True},
            {'name': 'Barrel',         'abbreviation': 'bbl',    'symbol': 'bbl', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'),        'description': 'Barrel container',         'is_active': True},
            # NEW — catering quantities
            {'name': 'Tray',           'abbreviation': 'tray',   'symbol': 'tray','uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'),        'description': 'Tray (eggs=30, seedlings, lab specimens)',  'is_active': True},
            {'name': 'Portion',        'abbreviation': 'portion','symbol': 'ptn', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'),        'description': 'Single serving / portion — use for catering stock planning per student', 'is_active': True},
            {'name': 'Serving',        'abbreviation': 'serving','symbol': 'svg', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'),        'description': 'Prepared serving unit for meals tracking',   'is_active': True},
            # NEW — clinic/medical supplies
            {'name': 'Dose',           'abbreviation': 'dose',   'symbol': 'dos', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'),        'description': 'Single medication dose',                     'is_active': True},
            {'name': 'Tablet',         'abbreviation': 'tab',    'symbol': 'tab', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'),        'description': 'Single tablet or pill',                      'is_active': True},
            {'name': 'Capsule',        'abbreviation': 'cap',    'symbol': 'cap', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'),        'description': 'Single capsule',                             'is_active': True},
            # ── QUANTITY — school-specific ─────────────────────────────────────
            {'name': 'Classroom Set',  'abbreviation': 'cls-set','symbol': 'cls', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('30.0'),       'description': 'Classroom quantity (30 students)',            'is_active': True},
            {'name': 'Student Pack',   'abbreviation': 'std-pk', 'symbol': 'sp',  'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'),        'description': 'Per-student package',                        'is_active': True},
            {'name': 'Teacher Pack',   'abbreviation': 'tcr-pk', 'symbol': 'tp',  'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'),        'description': 'Teacher reference package',                  'is_active': True},
            {'name': 'Class Bundle',   'abbreviation': 'cls-bndl','symbol': 'cb', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('40.0'),       'description': 'Large class bundle (40 students)',            'is_active': True},
            # ── OTHER ──────────────────────────────────────────────────────────
            {'name': 'Percent',        'abbreviation': '%',      'symbol': '%',   'uom_type': 'OTHER',    'conversion_factor': Decimal('0.01'),       'description': 'One hundredth',            'is_active': True},
            {'name': 'Degree Celsius', 'abbreviation': '°C',     'symbol': '°C',  'uom_type': 'OTHER',    'conversion_factor': Decimal('1.0'),        'description': 'Temperature (Celsius)',    'is_active': True},
            {'name': 'Degree Fahrenheit','abbreviation': '°F',   'symbol': '°F',  'uom_type': 'OTHER',    'conversion_factor': Decimal('1.0'),        'description': 'Temperature (Fahrenheit)', 'is_active': True},
        ]

    # =========================================================================
    # COMPLETE INIT CONFIG
    # =========================================================================

    @classmethod
    def get_init_config(cls, school):
        """
        Return complete initialisation configuration for a school.

        The init command should call validate_config() on this class first,
        then process each section in dependency order:
          1. account_types          (prerequisite for chart_of_accounts)
          2. chart_of_accounts
          3. financial_settings
          4. account_mappings       (prerequisite: chart_of_accounts must exist)
          5. journals
          6. expense_categories
          7. departments            (prerequisite for designations)
          8. designations
          9. display_groups         (prerequisite for fee_categories)
         10. fee_categories
         11. payment_methods
         12. tax_rates
         13. units_of_measure
        """
        complexity = cls.determine_complexity(school)

        return {
            'school':             school,
            'complexity':         complexity,
            'needs_boarding':     school.boarding_type in ('BOARDING', 'MIXED'),

            # Seeding sections (process in dependency order above)
            'account_types':      cls.get_account_types(),
            'chart_of_accounts':  cls.get_chart_of_accounts(school),
            'financial_settings': cls.get_financial_settings_defaults(school),
            # FIX: pass complexity so account numbers match the correct chart
            'account_mappings':   cls.get_account_mappings_config(complexity),
            'journals':           cls.get_journals(),
            'expense_categories': cls.get_expense_categories(),
            'departments':        cls.get_departments(school),
            'designations':       cls.get_designations(school),
            'display_groups':     cls.get_display_groups(),
            'fee_categories':     cls.get_fee_categories(school),
            'payment_methods':    cls.get_payment_methods(),
            'tax_rates':          cls.get_tax_rates(school),
            'units_of_measure':   cls.get_units_of_measure(),
        }

    # =========================================================================
    # VALIDATION
    # =========================================================================

    @classmethod
    def validate_config(cls):
        """
        Sanity-check the configuration for internal consistency.

        Returns a list of issue strings. An empty list means the config is
        clean. Call this before seeding to surface problems early.

        Checks:
          1. All display_group names in fee_categories exist in display_groups
          2. All fee category applicability values are in APPLICABILITY_CHOICES
          3. All fee category category_type values are in CATEGORY_TYPE_CHOICES
          4. All fee category frequency values are in FREQUENCY_CHOICES
          5. No duplicate designation codes
          6. All designation department_codes exist in departments

        Usage:
            issues = SchoolInitConfig.validate_config()
            for issue in issues:
                logger.error(issue)
            assert not issues, f"{len(issues)} config issue(s) found"
        """
        issues = []

        # ── 1. Display group name cross-reference ──────────────────────────────
        # Use a mock school — validate_config() doesn't depend on real data
        class _MockSchool:
            boarding_type = 'MIXED'
            accounting_complexity = None
            student_capacity = 500
            school_type = 'SECONDARY'
            country = 'UG'

        mock_school     = _MockSchool()
        group_names     = {g['name'] for g in cls.get_display_groups()}
        fee_categories  = cls.get_fee_categories(mock_school)

        for cat in fee_categories:
            dg = cat.get('display_group')
            if dg and dg not in group_names:
                issues.append(
                    f"fee_category '{cat['code']}': display_group '{dg}' "
                    f"not found in get_display_groups(). "
                    f"Available: {sorted(group_names)}"
                )

        # ── 2-4. Choice field validation ───────────────────────────────────────
        for cat in fee_categories:
            code = cat.get('code', '?')

            applicability = cat.get('applicability')
            if applicability and applicability not in cls._VALID_APPLICABILITY:
                issues.append(
                    f"fee_category '{code}': applicability='{applicability}' "
                    f"is not in FeesCategory.APPLICABILITY_CHOICES."
                )

            category_type = cat.get('category_type')
            if category_type and category_type not in cls._VALID_CATEGORY_TYPES:
                issues.append(
                    f"fee_category '{code}': category_type='{category_type}' "
                    f"is not in FeesCategory.CATEGORY_TYPE_CHOICES."
                )

            frequency = cat.get('frequency')
            if frequency and frequency not in cls._VALID_FREQUENCIES:
                issues.append(
                    f"fee_category '{code}': frequency='{frequency}' "
                    f"is not in FeesCategory.FREQUENCY_CHOICES."
                )

        # ── 5. Designation code uniqueness ─────────────────────────────────────
        designations = cls.get_designations(mock_school)
        seen_codes   = {}
        for desig in designations:
            code = desig.get('code', '?')
            if code in seen_codes:
                issues.append(
                    f"Designation code '{code}' is duplicated. "
                    f"First seen: '{seen_codes[code]}', "
                    f"duplicate: '{desig.get('name')}'"
                )
            else:
                seen_codes[code] = desig.get('name', '?')

        # ── 6. Designation department_code existence ────────────────────────────
        dept_codes = {d['code'] for d in cls.get_departments(mock_school)}
        for desig in designations:
            dept_code = desig.get('department_code')
            if dept_code and dept_code not in dept_codes:
                issues.append(
                    f"Designation '{desig.get('code')}': department_code "
                    f"'{dept_code}' not found in get_departments(). "
                    f"Available codes: {sorted(dept_codes)}"
                )

        if issues:
            logger.error(
                f"SchoolInitConfig.validate_config() found {len(issues)} issue(s)."
            )
        else:
            logger.info("SchoolInitConfig.validate_config() passed — no issues found.")

        return issues