# core/services/school_init_config.py
"""
School Initialization Configuration
===================================

This file contains all the configuration data for school initialization.
It centralizes all default data to eliminate redundancy across commands.

USAGE:
======
from core.services.school_init_config import SchoolInitConfig

# Get configuration for a school
config = SchoolInitConfig.get_init_config(school_instance)

# Access specific configurations
accounts = SchoolInitConfig.get_chart_of_accounts(school_instance)
categories = SchoolInitConfig.get_fee_categories(school_instance)
settings = SchoolInitConfig.get_financial_settings(school_instance)
"""

from decimal import Decimal
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


class SchoolInitConfig:
    """Configuration class for school initialization data"""
    
    # =========================================================================
    # COMPLEXITY DETERMINATION
    # =========================================================================
    
    @classmethod
    def determine_complexity(cls, school):
        """
        Auto-determine accounting complexity based on school characteristics.
        
        Args:
            school: School instance
            
        Returns:
            str: 'BASIC', 'STANDARD', or 'ADVANCED'
        """
        # If explicitly set, use that
        if school.accounting_complexity:
            return school.accounting_complexity
        
        # Universities and Colleges → ADVANCED
        if school.school_type in ['UNIVERSITY', 'COLLEGE']:
            return 'ADVANCED'
        
        # Large schools (700+ students) → ADVANCED
        if school.student_capacity >= 700:
            return 'ADVANCED'
        
        # Small schools (200 or fewer students) → BASIC
        if school.student_capacity <= 200:
            return 'BASIC'
        
        # Kindergarten and Primary only → BASIC
        if school.school_type in ['KINDERGARTEN', 'PRIMARY', 'KINDERGARTEN_PRIMARY']:
            return 'BASIC'
        
        # Default → STANDARD
        return 'STANDARD'
    
    @classmethod
    def get_account_types(cls):
        """
        Get standard account type configurations for all schools.
        
        These are the 5 fundamental account types in double-entry accounting:
        - ASSET: Resources owned (normal debit balance, appears on balance sheet)
        - LIABILITY: Obligations owed (normal credit balance, appears on balance sheet)
        - EQUITY: Net assets (normal credit balance, appears on balance sheet)
        - REVENUE: Income earned (normal credit balance, appears on income statement)
        - EXPENSE: Costs incurred (normal debit balance, appears on income statement)
        
        Returns:
            list: List of account type dictionaries with all required fields
            
        Usage:
            >>> types = SchoolInitConfig.get_account_types()
            >>> for type_config in types:
            >>>     AccountType.objects.create(**type_config)
        """
        return [
            {
                'name': 'Assets',
                'code': 'ASSET',
                'account_type': 'ASSET',
                'description': (
                    'Resources owned or controlled by the school that provide future economic benefits. '
                    'Includes cash, bank accounts, receivables, inventory, equipment, and property.'
                ),
                'normal_balance': 'DEBIT',
                'affects_balance_sheet': True,
                'affects_income_statement': False,
                'number_prefix': '1',
                'next_number': 1,
                'display_order': 1,
                'icon': 'fa-coins',
                'color': '#28a745',
                'is_active': True,
                'requires_approval': False,
                'allows_manual_entries': True,
            },
            {
                'name': 'Liabilities',
                'code': 'LIABILITY',
                'account_type': 'LIABILITY',
                'description': (
                    'Obligations and debts owed by the school to external parties. '
                    'Includes accounts payable, loans, accrued expenses, and student deposits.'
                ),
                'normal_balance': 'CREDIT',
                'affects_balance_sheet': True,
                'affects_income_statement': False,
                'number_prefix': '2',
                'next_number': 1,
                'display_order': 2,
                'icon': 'fa-file-invoice',
                'color': '#dc3545',
                'is_active': True,
                'requires_approval': False,
                'allows_manual_entries': True,
            },
            {
                'name': 'Equity',
                'code': 'EQUITY',
                'account_type': 'EQUITY',
                'description': (
                    'Net assets representing ownership interest in the school. '
                    'Includes capital contributions, retained earnings, and reserves.'
                ),
                'normal_balance': 'CREDIT',
                'affects_balance_sheet': True,
                'affects_income_statement': False,
                'number_prefix': '3',
                'next_number': 1,
                'display_order': 3,
                'icon': 'fa-landmark',
                'color': '#6f42c1',
                'is_active': True,
                'requires_approval': False,
                'allows_manual_entries': True,
            },
            {
                'name': 'Revenue',
                'code': 'REVENUE',
                'account_type': 'REVENUE',
                'description': (
                    'Income and earnings from school operations and activities. '
                    'Includes tuition fees, boarding fees, donations, and other income sources.'
                ),
                'normal_balance': 'CREDIT',
                'affects_balance_sheet': False,
                'affects_income_statement': True,
                'number_prefix': '4',
                'next_number': 1,
                'display_order': 4,
                'icon': 'fa-dollar-sign',
                'color': '#17a2b8',
                'is_active': True,
                'requires_approval': False,
                'allows_manual_entries': True,
            },
            {
                'name': 'Expenses',
                'code': 'EXPENSE',
                'account_type': 'EXPENSE',
                'description': (
                    'Operating costs and expenditures incurred in running the school. '
                    'Includes salaries, utilities, supplies, maintenance, and all other operational costs.'
                ),
                'normal_balance': 'DEBIT',
                'affects_balance_sheet': False,
                'affects_income_statement': True,
                'number_prefix': '5',
                'next_number': 1,
                'display_order': 5,
                'icon': 'fa-file-invoice-dollar',
                'color': '#fd7e14',
                'is_active': True,
                'requires_approval': False,
                'allows_manual_entries': True,
            },
        ]
    
    @classmethod
    def get_recommended_accounts_count(cls, complexity):
        """Get recommended number of accounts for complexity level"""
        return {
            'BASIC': 10,
            'STANDARD': 25,
            'ADVANCED': 60,
        }.get(complexity, 25)
    
    # =========================================================================
    # CHART OF ACCOUNTS BY COMPLEXITY
    # =========================================================================
    
    @classmethod
    def get_chart_of_accounts(cls, school):
        """Get complete chart of accounts based on school complexity"""
        complexity = cls.determine_complexity(school)
        
        if complexity == 'BASIC':
            return cls._get_basic_accounts(school)
        elif complexity == 'STANDARD':
            return cls._get_standard_accounts(school)
        else:  # ADVANCED
            return cls._get_advanced_accounts(school)
    
    @classmethod
    def _get_basic_accounts(cls, school):
        """
        Basic chart of accounts - HORIZONTAL FORMAT
        
        Simplified chart for small schools with ~10-12 accounts covering
        the fundamental operations. Includes all 5 account types required
        for complete double-entry bookkeeping.
        """
        accounts = [
            # ===== ASSETS =====
            {'number': '1000', 'name': 'Main Bank Account', 'type': 'ASSET', 'is_bank_account': True, 'description': 'Primary bank account', 'is_active': True},
            {'number': '1010', 'name': 'Cash on Hand', 'type': 'ASSET', 'is_cash_account': True, 'description': 'Physical cash at school', 'is_active': True},
            {'number': '1100', 'name': 'Student Receivables', 'type': 'ASSET', 'is_receivable_account': True, 'receivable_type': 'STUDENT', 'description': 'Amounts owed by students', 'is_active': True},
            {'number': '1200', 'name': 'Supplies & Equipment', 'type': 'ASSET', 'description': 'School supplies and equipment', 'is_active': True},
            
            # ===== LIABILITIES =====
            {'number': '2000', 'name': 'Accounts Payable', 'type': 'LIABILITY', 'is_payable_account': True, 'description': 'Amounts owed to vendors', 'is_active': True},
            
            # ===== EQUITY =====
            {'number': '3000', 'name': 'Capital', 'type': 'EQUITY', 'description': 'Owner capital and retained earnings', 'is_active': True},
            
            # ===== REVENUE =====
            {'number': '4000', 'name': 'School Fees', 'type': 'REVENUE', 'is_revenue_account': True, 'revenue_type': 'TUITION', 'description': 'All school fees revenue', 'is_active': True},
            
            # ===== EXPENSES =====
            {'number': '5000', 'name': 'Salaries & Wages', 'type': 'EXPENSE', 'is_expense_account': True, 'expense_type': 'TEACHING_SALARIES', 'description': 'All staff salaries and wages', 'is_active': True},
            {'number': '5100', 'name': 'Utilities', 'type': 'EXPENSE', 'is_expense_account': True, 'expense_type': 'UTILITIES', 'description': 'Electricity, water, internet', 'is_active': True},
            {'number': '5200', 'name': 'Supplies', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'School supplies and materials', 'is_active': True},
            {'number': '5300', 'name': 'Maintenance & Repairs', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Building and equipment maintenance', 'is_active': True},
            {'number': '5800', 'name': 'Scholarships & Discounts', 'type': 'EXPENSE', 'is_expense_account': True, 'expense_type': 'SCHOLARSHIP', 'description': 'Student scholarships and fee discounts', 'is_active': True},
            {'number': '5900', 'name': 'Other Expenses', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Miscellaneous operating expenses', 'is_active': True},
        ]
        
        # Add boarding revenue if school has boarding
        if school.boarding_type in ['BOARDING', 'MIXED']:
            boarding_accounts = [
                {'number': '4100', 'name': 'Boarding Fees', 'type': 'REVENUE', 'is_revenue_account': True, 'revenue_type': 'BOARDING_REVENUE', 'description': 'Boarding and meals revenue', 'is_active': True},
                {'number': '5600', 'name': 'Boarding Expenses', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Food and boarding operational costs', 'is_active': True},
            ]
            accounts.extend(boarding_accounts)
        
        return accounts
    
    @classmethod
    def _get_standard_accounts(cls, school):
        """
        Standard chart of accounts - HORIZONTAL FORMAT
        
        This method builds a complete chart for standard complexity schools.
        Instead of extending basic accounts and creating duplicates, it creates
        a fresh set of appropriately detailed accounts.
        """
        accounts = [
            # ===== ASSETS =====
            # Cash & Bank Accounts
            {'number': '1000', 'name': 'Main Bank Account', 'type': 'ASSET', 'is_bank_account': True, 'description': 'Primary bank account', 'is_active': True},
            {'number': '1010', 'name': 'Petty Cash', 'type': 'ASSET', 'is_cash_account': True, 'description': 'Petty cash fund', 'is_active': True},
            {'number': '1020', 'name': 'Mobile Money', 'type': 'ASSET', 'description': 'Mobile money clearing account', 'is_active': True},
            {'number': '1030', 'name': 'Bank Account - Savings', 'type': 'ASSET', 'is_bank_account': True, 'description': 'Savings and reserve account', 'is_active': True},
            
            # Receivables
            {'number': '1100', 'name': 'Student Receivables', 'type': 'ASSET', 'is_receivable_account': True, 'receivable_type': 'STUDENT', 'description': 'Amounts owed by students', 'is_active': True},
            {'number': '1110', 'name': 'Staff Receivables', 'type': 'ASSET', 'is_receivable_account': True, 'receivable_type': 'STAFF', 'description': 'Staff loans and advances', 'is_active': True},
            
            # Other Assets
            {'number': '1200', 'name': 'Inventory - Supplies', 'type': 'ASSET', 'description': 'School supplies inventory', 'is_active': True},
            {'number': '1210', 'name': 'Inventory - Uniforms & Books', 'type': 'ASSET', 'description': 'Uniforms and textbooks inventory', 'is_active': True},
            {'number': '1300', 'name': 'Equipment & Furniture', 'type': 'ASSET', 'description': 'School equipment and furniture', 'is_active': True},
            
            # ===== LIABILITIES =====
            {'number': '2000', 'name': 'Accounts Payable', 'type': 'LIABILITY', 'is_payable_account': True, 'description': 'Amounts owed to vendors', 'is_active': True},
            {'number': '2010', 'name': 'Salaries Payable', 'type': 'LIABILITY', 'description': 'Accrued salaries not yet paid', 'is_active': True},
            {'number': '2020', 'name': 'Tax Payable', 'type': 'LIABILITY', 'description': 'PAYE and other taxes withheld', 'is_active': True},
            {'number': '2030', 'name': 'Student Deposits', 'type': 'LIABILITY', 'description': 'Refundable student deposits', 'is_active': True},
            
            # ===== EQUITY =====
            {'number': '3000', 'name': 'Capital', 'type': 'EQUITY', 'description': 'Owner capital contribution', 'is_active': True},
            {'number': '3100', 'name': 'Retained Earnings', 'type': 'EQUITY', 'description': 'Accumulated profits', 'is_active': True},
            
            # ===== REVENUE =====
            # Tuition & Fees
            {'number': '4000', 'name': 'Tuition Fees', 'type': 'REVENUE', 'is_revenue_account': True, 'revenue_type': 'TUITION', 'description': 'School tuition fees', 'is_active': True},
            {'number': '4010', 'name': 'Examination Fees', 'type': 'REVENUE', 'is_revenue_account': True, 'revenue_type': 'EXAM_FEES', 'description': 'Exam registration fees', 'is_active': True},
            
            # Other Revenue
            {'number': '4200', 'name': 'Uniform & Book Sales', 'type': 'REVENUE', 'is_revenue_account': True, 'revenue_type': 'UNIFORM_SALES', 'description': 'Uniform and textbook sales', 'is_active': True},
            {'number': '4300', 'name': 'Transport Fees', 'type': 'REVENUE', 'is_revenue_account': True, 'revenue_type': 'TRANSPORT_REVENUE', 'description': 'School transport fees', 'is_active': True},
            {'number': '4400', 'name': 'Activity Fees', 'type': 'REVENUE', 'is_revenue_account': True, 'description': 'Sports and extracurricular fees', 'is_active': True},
            {'number': '4900', 'name': 'Other Income', 'type': 'REVENUE', 'is_revenue_account': True, 'description': 'Donations and miscellaneous income', 'is_active': True},
            
            # ===== EXPENSES =====
            # Salaries & Benefits (DETAILED - no generic "Salaries & Wages")
            {'number': '5000', 'name': 'Teaching Staff Salaries', 'type': 'EXPENSE', 'is_expense_account': True, 'expense_type': 'TEACHING_SALARIES', 'description': 'Teaching staff salaries', 'is_active': True},
            {'number': '5010', 'name': 'Administrative Salaries', 'type': 'EXPENSE', 'is_expense_account': True, 'expense_type': 'ADMIN_SALARIES', 'description': 'Administrative staff salaries', 'is_active': True},
            {'number': '5020', 'name': 'Support Staff Salaries', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Support and maintenance staff', 'is_active': True},
            {'number': '5030', 'name': 'Staff Allowances', 'type': 'EXPENSE', 'is_expense_account': True, 'expense_type': 'STAFF_BENEFITS', 'description': 'Housing, transport allowances', 'is_active': True},
            
            # Utilities (DETAILED - no generic "Utilities")
            {'number': '5100', 'name': 'Electricity', 'type': 'EXPENSE', 'is_expense_account': True, 'expense_type': 'UTILITIES', 'description': 'Electricity bills', 'is_active': True},
            {'number': '5110', 'name': 'Water & Sewerage', 'type': 'EXPENSE', 'is_expense_account': True, 'expense_type': 'UTILITIES', 'description': 'Water and sewerage charges', 'is_active': True},
            {'number': '5120', 'name': 'Internet & Communication', 'type': 'EXPENSE', 'is_expense_account': True, 'expense_type': 'UTILITIES', 'description': 'Internet and phone services', 'is_active': True},
            
            # Supplies (DETAILED - no generic "Supplies")
            {'number': '5200', 'name': 'Office Supplies', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Stationery and office materials', 'is_active': True},
            {'number': '5210', 'name': 'Learning Materials', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Teaching aids and materials', 'is_active': True},
            {'number': '5220', 'name': 'Cleaning Supplies', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Cleaning materials and chemicals', 'is_active': True},
            
            # Maintenance (DETAILED - no generic "Maintenance")
            {'number': '5300', 'name': 'Building Maintenance', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Building repairs and maintenance', 'is_active': True},
            {'number': '5310', 'name': 'Equipment Repairs', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Equipment maintenance and repairs', 'is_active': True},
            
            # Other Operating Expenses
            {'number': '5400', 'name': 'Security Services', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Security personnel and services', 'is_active': True},
            {'number': '5500', 'name': 'Transport & Fuel', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Fuel and vehicle maintenance', 'is_active': True},
            {'number': '5600', 'name': 'Professional Fees', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Legal and consultancy fees', 'is_active': True},
            {'number': '5700', 'name': 'Insurance', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Insurance premiums', 'is_active': True},
            
            # Scholarships & Discounts
            {'number': '5800', 'name': 'Scholarships & Discounts', 'type': 'EXPENSE', 'is_expense_account': True, 'expense_type': 'SCHOLARSHIP', 'description': 'Scholarships and fee discounts', 'is_active': True},
            
            # Miscellaneous
            {'number': '5900', 'name': 'Other Expenses', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Miscellaneous operating expenses', 'is_active': True},
        ]
        
        # Add boarding-related accounts if school has boarding
        if school.boarding_type in ['BOARDING', 'MIXED']:
            boarding_accounts = [
                {'number': '4100', 'name': 'Boarding Fees', 'type': 'REVENUE', 'is_revenue_account': True, 'revenue_type': 'BOARDING_REVENUE', 'description': 'Boarding accommodation fees', 'is_active': True},
                {'number': '4110', 'name': 'Meals Revenue', 'type': 'REVENUE', 'is_revenue_account': True, 'revenue_type': 'MEALS_REVENUE', 'description': 'Meal service fees', 'is_active': True},
                {'number': '5610', 'name': 'Food & Provisions', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Food purchases for boarding', 'is_active': True},
                {'number': '5620', 'name': 'Boarding Supplies', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Bedding, toiletries, and boarding supplies', 'is_active': True},
            ]
            accounts.extend(boarding_accounts)
        
        return accounts
    
    @classmethod
    def _get_advanced_accounts(cls, school):
        """Advanced comprehensive chart of accounts - HORIZONTAL FORMAT"""
        accounts = [
            # ===== ASSETS (1000-1999) =====
            # Current Assets - Cash & Bank
            {'number': '1000', 'name': 'Cash on Hand', 'type': 'ASSET', 'is_cash_account': True, 'description': 'Physical cash at school', 'is_active': True},
            {'number': '1010', 'name': 'Petty Cash', 'type': 'ASSET', 'is_cash_account': True, 'description': 'Petty cash fund for minor expenses', 'is_active': True},
            {'number': '1020', 'name': 'Bank Account - Main', 'type': 'ASSET', 'is_bank_account': True, 'description': 'Primary bank account', 'is_active': True},
            {'number': '1021', 'name': 'Bank Account - Payroll', 'type': 'ASSET', 'is_bank_account': True, 'description': 'Dedicated payroll account', 'is_active': True},
            {'number': '1022', 'name': 'Bank Account - Savings', 'type': 'ASSET', 'is_bank_account': True, 'description': 'Savings and reserve account', 'is_active': True},
            {'number': '1030', 'name': 'Mobile Money - MTN', 'type': 'ASSET', 'description': 'MTN Mobile Money clearing', 'is_active': True},
            {'number': '1031', 'name': 'Mobile Money - Airtel', 'type': 'ASSET', 'description': 'Airtel Money clearing', 'is_active': True},
            # Receivables
            {'number': '1100', 'name': 'Student Receivables - Current', 'type': 'ASSET', 'is_receivable_account': True, 'receivable_type': 'STUDENT', 'description': 'Current term student fees', 'is_active': True},
            {'number': '1110', 'name': 'Student Receivables - Arrears', 'type': 'ASSET', 'is_receivable_account': True, 'receivable_type': 'STUDENT', 'description': 'Overdue student fees', 'is_active': True},
            {'number': '1120', 'name': 'Staff Receivables', 'type': 'ASSET', 'is_receivable_account': True, 'receivable_type': 'STAFF', 'description': 'Staff loans and advances', 'is_active': True},
            {'number': '1130', 'name': 'Other Receivables', 'type': 'ASSET', 'is_receivable_account': True, 'description': 'Miscellaneous receivables', 'is_active': True},
            {'number': '1140', 'name': 'Allowance for Doubtful Accounts', 'type': 'ASSET', 'description': 'Bad debt provision', 'is_active': True},
            # Inventory
            {'number': '1200', 'name': 'Inventory - General Supplies', 'type': 'ASSET', 'description': 'General school supplies', 'is_active': True},
            {'number': '1210', 'name': 'Inventory - Uniforms', 'type': 'ASSET', 'description': 'School uniforms inventory', 'is_active': True},
            {'number': '1220', 'name': 'Inventory - Textbooks', 'type': 'ASSET', 'description': 'Textbooks and learning materials', 'is_active': True},
            {'number': '1230', 'name': 'Inventory - Food & Provisions', 'type': 'ASSET', 'description': 'Food items and catering supplies', 'is_active': True},
            {'number': '1240', 'name': 'Inventory - Stationery', 'type': 'ASSET', 'description': 'Office and student stationery', 'is_active': True},
            # Prepaid Expenses
            {'number': '1300', 'name': 'Prepaid Rent', 'type': 'ASSET', 'description': 'Rent paid in advance', 'is_active': True},
            {'number': '1310', 'name': 'Prepaid Insurance', 'type': 'ASSET', 'description': 'Insurance premiums paid in advance', 'is_active': True},
            {'number': '1320', 'name': 'Prepaid Subscriptions', 'type': 'ASSET', 'description': 'Software and service subscriptions', 'is_active': True},
            # Fixed Assets
            {'number': '1500', 'name': 'Land', 'type': 'ASSET', 'description': 'School land', 'is_active': True},
            {'number': '1510', 'name': 'Buildings', 'type': 'ASSET', 'description': 'School buildings and structures', 'is_active': True},
            {'number': '1511', 'name': 'Accumulated Depreciation - Buildings', 'type': 'ASSET', 'description': 'Building depreciation', 'is_active': True},
            {'number': '1520', 'name': 'Furniture & Fixtures', 'type': 'ASSET', 'description': 'Desks, chairs, cabinets', 'is_active': True},
            {'number': '1521', 'name': 'Accumulated Depreciation - Furniture', 'type': 'ASSET', 'description': 'Furniture depreciation', 'is_active': True},
            {'number': '1530', 'name': 'Computer Equipment', 'type': 'ASSET', 'description': 'Computers and IT hardware', 'is_active': True},
            {'number': '1531', 'name': 'Accumulated Depreciation - Computers', 'type': 'ASSET', 'description': 'Computer depreciation', 'is_active': True},
            {'number': '1540', 'name': 'Vehicles', 'type': 'ASSET', 'description': 'School buses and vehicles', 'is_active': True},
            {'number': '1541', 'name': 'Accumulated Depreciation - Vehicles', 'type': 'ASSET', 'description': 'Vehicle depreciation', 'is_active': True},
            {'number': '1550', 'name': 'Laboratory Equipment', 'type': 'ASSET', 'description': 'Science lab equipment', 'is_active': True},
            {'number': '1551', 'name': 'Accumulated Depreciation - Lab Equipment', 'type': 'ASSET', 'description': 'Lab equipment depreciation', 'is_active': True},
            {'number': '1560', 'name': 'Sports Equipment', 'type': 'ASSET', 'description': 'Sports and PE equipment', 'is_active': True},
            {'number': '1570', 'name': 'Library Books', 'type': 'ASSET', 'description': 'Library collection', 'is_active': True},
            
            # ===== LIABILITIES (2000-2999) =====
            # Current Liabilities
            {'number': '2000', 'name': 'Accounts Payable', 'type': 'LIABILITY', 'is_payable_account': True, 'description': 'Vendor payables', 'is_active': True},
            {'number': '2010', 'name': 'Salaries Payable', 'type': 'LIABILITY', 'description': 'Accrued salaries', 'is_active': True},
            {'number': '2020', 'name': 'PAYE Tax Payable', 'type': 'LIABILITY', 'description': 'Employee income tax withheld', 'is_active': True},
            {'number': '2030', 'name': 'NSSF Payable', 'type': 'LIABILITY', 'description': 'Social security contributions', 'is_active': True},
            {'number': '2040', 'name': 'Local Service Tax Payable', 'type': 'LIABILITY', 'description': 'Local service tax', 'is_active': True},
            {'number': '2050', 'name': 'Student Deposits', 'type': 'LIABILITY', 'description': 'Refundable student deposits', 'is_active': True},
            {'number': '2060', 'name': 'Advance Fee Payments', 'type': 'LIABILITY', 'description': 'Fees paid in advance', 'is_active': True},
            {'number': '2070', 'name': 'Utilities Payable', 'type': 'LIABILITY', 'description': 'Accrued utility bills', 'is_active': True},
            {'number': '2080', 'name': 'Interest Payable', 'type': 'LIABILITY', 'description': 'Accrued interest on loans', 'is_active': True},
            # Long-term Liabilities
            {'number': '2100', 'name': 'Bank Loans - Long Term', 'type': 'LIABILITY', 'description': 'Long-term bank loans', 'is_active': True},
            {'number': '2110', 'name': 'Equipment Financing', 'type': 'LIABILITY', 'description': 'Equipment lease obligations', 'is_active': True},
            {'number': '2120', 'name': 'Mortgage Payable', 'type': 'LIABILITY', 'description': 'Property mortgage', 'is_active': True},
            
            # ===== EQUITY (3000-3999) =====
            {'number': '3000', 'name': 'Capital', 'type': 'EQUITY', 'description': 'Owners capital contribution', 'is_active': True},
            {'number': '3100', 'name': 'Retained Earnings', 'type': 'EQUITY', 'description': 'Accumulated profits', 'is_active': True},
            {'number': '3200', 'name': 'Current Year Earnings', 'type': 'EQUITY', 'description': 'Current year profit/loss', 'is_active': True},
            {'number': '3300', 'name': 'Reserves', 'type': 'EQUITY', 'description': 'Statutory and voluntary reserves', 'is_active': True},
            
            # ===== REVENUE (4000-4999) =====
            # Tuition Revenue
            {'number': '4000', 'name': 'Tuition Fees - Primary', 'type': 'REVENUE', 'is_revenue_account': True, 'revenue_type': 'TUITION', 'description': 'Primary school tuition', 'is_active': True},
            {'number': '4010', 'name': 'Tuition Fees - Secondary', 'type': 'REVENUE', 'is_revenue_account': True, 'revenue_type': 'TUITION', 'description': 'Secondary school tuition', 'is_active': True},
            {'number': '4020', 'name': 'Examination Fees', 'type': 'REVENUE', 'is_revenue_account': True, 'revenue_type': 'EXAM_FEES', 'description': 'Exam registration and materials', 'is_active': True},
            {'number': '4030', 'name': 'Development Fees', 'type': 'REVENUE', 'is_revenue_account': True, 'description': 'Infrastructure development fees', 'is_active': True},
            # Boarding & Meals
            {'number': '4100', 'name': 'Boarding Fees', 'type': 'REVENUE', 'is_revenue_account': True, 'revenue_type': 'BOARDING_REVENUE', 'description': 'Boarding accommodation fees', 'is_active': True},
            {'number': '4110', 'name': 'Meals Revenue', 'type': 'REVENUE', 'is_revenue_account': True, 'revenue_type': 'MEALS_REVENUE', 'description': 'Meal service fees', 'is_active': True},
            # Other Fees
            {'number': '4200', 'name': 'Uniform Sales', 'type': 'REVENUE', 'is_revenue_account': True, 'revenue_type': 'UNIFORM_SALES', 'description': 'School uniform sales', 'is_active': True},
            {'number': '4210', 'name': 'Textbook Sales', 'type': 'REVENUE', 'is_revenue_account': True, 'revenue_type': 'BOOK_SALES', 'description': 'Textbook and stationery sales', 'is_active': True},
            {'number': '4220', 'name': 'Transport Fees', 'type': 'REVENUE', 'is_revenue_account': True, 'revenue_type': 'TRANSPORT_REVENUE', 'description': 'School transport fees', 'is_active': True},
            {'number': '4230', 'name': 'Activity Fees', 'type': 'REVENUE', 'is_revenue_account': True, 'description': 'Sports and extracurricular fees', 'is_active': True},
            {'number': '4240', 'name': 'Computer Lab Fees', 'type': 'REVENUE', 'is_revenue_account': True, 'description': 'ICT and computer fees', 'is_active': True},
            {'number': '4250', 'name': 'Library Fees', 'type': 'REVENUE', 'is_revenue_account': True, 'description': 'Library service fees', 'is_active': True},
            # Penalties & Other Income
            {'number': '4300', 'name': 'Late Payment Fees', 'type': 'REVENUE', 'is_revenue_account': True, 'description': 'Late payment penalties', 'is_active': True},
            {'number': '4310', 'name': 'Replacement Fees', 'type': 'REVENUE', 'is_revenue_account': True, 'description': 'Lost item replacement charges', 'is_active': True},
            {'number': '4900', 'name': 'Donations & Grants', 'type': 'REVENUE', 'is_revenue_account': True, 'description': 'Donations and grant income', 'is_active': True},
            {'number': '4910', 'name': 'Interest Income', 'type': 'REVENUE', 'is_revenue_account': True, 'description': 'Bank interest earned', 'is_active': True},
            {'number': '4920', 'name': 'Miscellaneous Income', 'type': 'REVENUE', 'is_revenue_account': True, 'description': 'Other income', 'is_active': True},
            
            # ===== EXPENSES (5000-5999) =====
            # Salaries & Wages
            {'number': '5000', 'name': 'Teaching Staff - Basic Salary', 'type': 'EXPENSE', 'is_expense_account': True, 'expense_type': 'TEACHING_SALARIES', 'description': 'Teacher base salaries', 'is_active': True},
            {'number': '5010', 'name': 'Teaching Staff - Housing Allowance', 'type': 'EXPENSE', 'is_expense_account': True, 'expense_type': 'TEACHING_SALARIES', 'description': 'Teacher housing allowance', 'is_active': True},
            {'number': '5020', 'name': 'Teaching Staff - Transport Allowance', 'type': 'EXPENSE', 'is_expense_account': True, 'expense_type': 'TEACHING_SALARIES', 'description': 'Teacher transport allowance', 'is_active': True},
            {'number': '5030', 'name': 'Administrative Staff Salaries', 'type': 'EXPENSE', 'is_expense_account': True, 'expense_type': 'ADMIN_SALARIES', 'description': 'Admin staff salaries', 'is_active': True},
            {'number': '5040', 'name': 'Support Staff Salaries', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Support and maintenance staff', 'is_active': True},
            {'number': '5050', 'name': 'NSSF Contributions', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Employer NSSF contributions', 'is_active': True},
            {'number': '5060', 'name': 'Staff Medical Insurance', 'type': 'EXPENSE', 'is_expense_account': True, 'expense_type': 'STAFF_BENEFITS', 'description': 'Staff health insurance', 'is_active': True},
            {'number': '5070', 'name': 'Staff Training & Development', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Professional development', 'is_active': True},
            {'number': '5080', 'name': 'Staff Welfare', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Staff welfare expenses', 'is_active': True},
            # Utilities
            {'number': '5100', 'name': 'Electricity', 'type': 'EXPENSE', 'is_expense_account': True, 'expense_type': 'UTILITIES', 'description': 'Electricity bills', 'is_active': True},
            {'number': '5110', 'name': 'Water & Sewerage', 'type': 'EXPENSE', 'is_expense_account': True, 'expense_type': 'UTILITIES', 'description': 'Water and sewerage charges', 'is_active': True},
            {'number': '5120', 'name': 'Internet & WiFi', 'type': 'EXPENSE', 'is_expense_account': True, 'expense_type': 'UTILITIES', 'description': 'Internet connectivity', 'is_active': True},
            {'number': '5130', 'name': 'Telephone & Mobile', 'type': 'EXPENSE', 'is_expense_account': True, 'expense_type': 'UTILITIES', 'description': 'Phone services', 'is_active': True},
            {'number': '5140', 'name': 'Waste Management', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Garbage collection services', 'is_active': True},
            # Academic Supplies
            {'number': '5200', 'name': 'Textbooks & Learning Materials', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Teaching materials purchases', 'is_active': True},
            {'number': '5210', 'name': 'Stationery & Office Supplies', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Office stationery', 'is_active': True},
            {'number': '5220', 'name': 'Laboratory Supplies', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Science lab consumables', 'is_active': True},
            {'number': '5230', 'name': 'Library Books & Materials', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Library acquisitions', 'is_active': True},
            {'number': '5240', 'name': 'Computer Software & Licenses', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Software subscriptions', 'is_active': True},
            # Maintenance & Repairs
            {'number': '5300', 'name': 'Building Maintenance', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Building repairs', 'is_active': True},
            {'number': '5310', 'name': 'Equipment Repairs', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Equipment maintenance', 'is_active': True},
            {'number': '5320', 'name': 'Plumbing & Electrical Repairs', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Plumbing and electrical work', 'is_active': True},
            {'number': '5330', 'name': 'Painting & Renovation', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Painting and refurbishment', 'is_active': True},
            {'number': '5340', 'name': 'Cleaning Supplies', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Cleaning materials', 'is_active': True},
            # Security & Safety
            {'number': '5400', 'name': 'Security Services', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Security guard services', 'is_active': True},
            {'number': '5410', 'name': 'Security Equipment', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'CCTV and security systems', 'is_active': True},
            {'number': '5420', 'name': 'Fire Safety Equipment', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Fire extinguishers and safety', 'is_active': True},
            # Transport
            {'number': '5500', 'name': 'Fuel & Oil', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Vehicle fuel costs', 'is_active': True},
            {'number': '5510', 'name': 'Vehicle Maintenance & Repairs', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Vehicle servicing', 'is_active': True},
            {'number': '5520', 'name': 'Vehicle Insurance', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Vehicle insurance premiums', 'is_active': True},
            {'number': '5530', 'name': 'Vehicle Licensing & Permits', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Road licenses and permits', 'is_active': True},
            # Boarding & Catering
            {'number': '5600', 'name': 'Food & Provisions', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Food purchases', 'is_active': True},
            {'number': '5610', 'name': 'Kitchen Supplies & Equipment', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Kitchen utensils and equipment', 'is_active': True},
            {'number': '5620', 'name': 'Cooking Gas', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'LPG and cooking fuel', 'is_active': True},
            {'number': '5630', 'name': 'Laundry Services', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Boarding laundry costs', 'is_active': True},
            {'number': '5640', 'name': 'Bedding & Linen', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Bedding for boarding', 'is_active': True},
            # Administrative
            {'number': '5700', 'name': 'Advertising & Marketing', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Marketing and promotion', 'is_active': True},
            {'number': '5710', 'name': 'Printing & Publications', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Printing services', 'is_active': True},
            {'number': '5720', 'name': 'Legal & Professional Fees', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Legal and consultancy fees', 'is_active': True},
            {'number': '5730', 'name': 'Audit Fees', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'External audit costs', 'is_active': True},
            {'number': '5740', 'name': 'Bank Charges & Fees', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Banking transaction fees', 'is_active': True},
            {'number': '5750', 'name': 'Licenses & Permits', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Business licenses', 'is_active': True},
            {'number': '5760', 'name': 'Insurance - General', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'General insurance premiums', 'is_active': True},
            {'number': '5770', 'name': 'Subscriptions & Memberships', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Professional memberships', 'is_active': True},
            # Scholarships & Financial Aid
            {'number': '5800', 'name': 'Scholarships & Bursaries', 'type': 'EXPENSE', 'is_expense_account': True, 'expense_type': 'SCHOLARSHIP', 'description': 'Student scholarships', 'is_active': True},
            {'number': '5810', 'name': 'Fee Discounts', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Fee reduction allowances', 'is_active': True},
            {'number': '5820', 'name': 'Bad Debt Write-off', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Uncollectible fees', 'is_active': True},
            # Depreciation & Amortization
            {'number': '5850', 'name': 'Depreciation - Buildings', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Building depreciation expense', 'is_active': True},
            {'number': '5851', 'name': 'Depreciation - Furniture', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Furniture depreciation expense', 'is_active': True},
            {'number': '5852', 'name': 'Depreciation - Computers', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Computer depreciation expense', 'is_active': True},
            {'number': '5853', 'name': 'Depreciation - Vehicles', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Vehicle depreciation expense', 'is_active': True},
            {'number': '5854', 'name': 'Depreciation - Equipment', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Equipment depreciation expense', 'is_active': True},
            # Other Expenses
            {'number': '5900', 'name': 'Entertainment & Events', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'School events and functions', 'is_active': True},
            {'number': '5910', 'name': 'Sports & Recreation', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Sports equipment and activities', 'is_active': True},
            {'number': '5920', 'name': 'Medical Supplies', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'First aid and medical supplies', 'is_active': True},
            {'number': '5930', 'name': 'Interest Expense', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Loan interest payments', 'is_active': True},
            {'number': '5990', 'name': 'Miscellaneous Expenses', 'type': 'EXPENSE', 'is_expense_account': True, 'description': 'Other operating expenses', 'is_active': True},
        ]
        
        return accounts
    
    # =========================================================================
    # EXPENSE CATEGORIES
    # =========================================================================
    
    @classmethod
    def get_expense_categories(cls):
        """
        Comprehensive expense categories mapped to the ExpenseCategory model structure.
        
        Returns:
            list: List of expense category dictionaries with all required fields
            
        Usage:
            >>> categories = SchoolInitConfig.get_expense_categories()
            >>> for category in categories:
            >>>     ExpenseCategory.objects.create(**category)
        """
        return [
            # =====================================================================
            # ADMINISTRATIVE EXPENSES
            # =====================================================================
            {
                'name': 'Office Supplies',
                'category_type': 'ADMINISTRATIVE',
                'description': 'Office supplies, stationery, and general administrative expenses',
                'requires_approval': True,
                'approval_limit': Decimal('50000.00'),
                'is_active': True,
            },
            {
                'name': 'Legal & Professional Fees',
                'category_type': 'ADMINISTRATIVE',
                'description': 'Legal consultations, audit fees, and professional services',
                'requires_approval': True,
                'approval_limit': Decimal('100000.00'),
                'is_active': True,
            },
            {
                'name': 'Licenses & Permits',
                'category_type': 'ADMINISTRATIVE',
                'description': 'Government licenses, permits, and regulatory fees',
                'requires_approval': True,
                'approval_limit': Decimal('200000.00'),
                'is_active': True,
            },
            {
                'name': 'Bank Charges',
                'category_type': 'ADMINISTRATIVE',
                'description': 'Banking fees, transaction charges, and account maintenance',
                'requires_approval': False,
                'approval_limit': None,
                'is_active': True,
            },
            {
                'name': 'Postage & Courier',
                'category_type': 'ADMINISTRATIVE',
                'description': 'Mail, postage, and courier delivery services',
                'requires_approval': False,
                'approval_limit': Decimal('20000.00'),
                'is_active': True,
            },

            # =====================================================================
            # ACADEMIC RESOURCES
            # =====================================================================
            {
                'name': 'Curriculum Development',
                'category_type': 'ACADEMIC',
                'description': 'Curriculum design, development, and review activities',
                'requires_approval': True,
                'approval_limit': Decimal('300000.00'),
                'is_active': True,
            },
            {
                'name': 'Teacher Training',
                'category_type': 'ACADEMIC',
                'description': 'Professional development and training programs for teaching staff',
                'requires_approval': True,
                'approval_limit': Decimal('500000.00'),
                'is_active': True,
            },
            {
                'name': 'Educational Consultancy',
                'category_type': 'ACADEMIC',
                'description': 'External educational consultants and advisory services',
                'requires_approval': True,
                'approval_limit': Decimal('200000.00'),
                'is_active': True,
            },

            # =====================================================================
            # SCHOLASTIC MATERIALS
            # =====================================================================
            {
                'name': 'Learning Materials',
                'category_type': 'SCHOLASTIC',
                'description': 'Textbooks, workbooks, stationery, and teaching aids',
                'requires_approval': True,
                'approval_limit': Decimal('100000.00'),
                'is_active': True,
            },
            {
                'name': 'Library Resources',
                'category_type': 'SCHOLASTIC',
                'description': 'Books, journals, magazines, and digital library resources',
                'requires_approval': True,
                'approval_limit': Decimal('150000.00'),
                'is_active': True,
            },
            {
                'name': 'Laboratory Supplies',
                'category_type': 'SCHOLASTIC',
                'description': 'Science lab chemicals, equipment, and consumables',
                'requires_approval': True,
                'approval_limit': Decimal('200000.00'),
                'is_active': True,
            },
            {
                'name': 'Art & Craft Supplies',
                'category_type': 'SCHOLASTIC',
                'description': 'Art materials, craft supplies, and creative resources',
                'requires_approval': True,
                'approval_limit': Decimal('80000.00'),
                'is_active': True,
            },

            # =====================================================================
            # EXAMINATION MATERIALS
            # =====================================================================
            {
                'name': 'Examination Materials',
                'category_type': 'EXAMINATION',
                'description': 'Question papers, answer sheets, printing, and exam supplies',
                'requires_approval': True,
                'approval_limit': Decimal('100000.00'),
                'is_active': True,
            },
            {
                'name': 'External Examination Fees',
                'category_type': 'EXAMINATION',
                'description': 'UNEB, Cambridge, and other external examination body fees',
                'requires_approval': True,
                'approval_limit': Decimal('500000.00'),
                'is_active': True,
            },
            {
                'name': 'Invigilation Costs',
                'category_type': 'EXAMINATION',
                'description': 'External invigilators and examination supervision costs',
                'requires_approval': True,
                'approval_limit': Decimal('150000.00'),
                'is_active': True,
            },

            # =====================================================================
            # FACILITIES & MAINTENANCE
            # =====================================================================
            {
                'name': 'Maintenance & Repairs',
                'category_type': 'FACILITIES',
                'description': 'Building maintenance, equipment repairs, and general upkeep',
                'requires_approval': True,
                'approval_limit': Decimal('300000.00'),
                'is_active': True,
            },
            {
                'name': 'Cleaning Supplies',
                'category_type': 'FACILITIES',
                'description': 'Cleaning materials, detergents, and sanitation supplies',
                'requires_approval': True,
                'approval_limit': Decimal('50000.00'),
                'is_active': True,
            },
            {
                'name': 'Security Services',
                'category_type': 'FACILITIES',
                'description': 'Security guard services, surveillance, and security equipment',
                'requires_approval': True,
                'approval_limit': Decimal('200000.00'),
                'is_active': True,
            },
            {
                'name': 'Groundskeeping',
                'category_type': 'FACILITIES',
                'description': 'Landscaping, gardening, and ground maintenance',
                'requires_approval': True,
                'approval_limit': Decimal('100000.00'),
                'is_active': True,
            },

            # =====================================================================
            # CAPITAL EXPENDITURE
            # =====================================================================
            {
                'name': 'Land & Buildings',
                'category_type': 'CAPITAL',
                'description': 'Purchase of land and building construction projects',
                'requires_approval': True,
                'approval_limit': Decimal('10000000.00'),
                'is_active': True,
            },
            {
                'name': 'Building Improvements',
                'category_type': 'CAPITAL',
                'description': 'Major renovations and structural improvements',
                'requires_approval': True,
                'approval_limit': Decimal('5000000.00'),
                'is_active': True,
            },
            {
                'name': 'Furniture & Fixtures',
                'category_type': 'CAPITAL',
                'description': 'Desks, chairs, classroom furniture, and fixtures',
                'requires_approval': True,
                'approval_limit': Decimal('1000000.00'),
                'is_active': True,
            },
            {
                'name': 'Vehicles',
                'category_type': 'CAPITAL',
                'description': 'Purchase of school buses, cars, and other vehicles',
                'requires_approval': True,
                'approval_limit': Decimal('5000000.00'),
                'is_active': True,
            },
            {
                'name': 'Laboratory Equipment',
                'category_type': 'CAPITAL',
                'description': 'Major laboratory equipment and machinery',
                'requires_approval': True,
                'approval_limit': Decimal('2000000.00'),
                'is_active': True,
            },

            # =====================================================================
            # UTILITIES
            # =====================================================================
            {
                'name': 'Electricity',
                'category_type': 'UTILITIES',
                'description': 'Monthly electricity bills and power consumption',
                'requires_approval': True,
                'approval_limit': Decimal('500000.00'),
                'is_active': True,
            },
            {
                'name': 'Water & Sewerage',
                'category_type': 'UTILITIES',
                'description': 'Water supply and sewerage services',
                'requires_approval': True,
                'approval_limit': Decimal('200000.00'),
                'is_active': True,
            },
            {
                'name': 'Internet & Phone',
                'category_type': 'UTILITIES',
                'description': 'Internet connectivity, telephone, and communication services',
                'requires_approval': True,
                'approval_limit': Decimal('300000.00'),
                'is_active': True,
            },
            {
                'name': 'Gas & Fuel',
                'category_type': 'UTILITIES',
                'description': 'Cooking gas and generator fuel',
                'requires_approval': True,
                'approval_limit': Decimal('400000.00'),
                'is_active': True,
            },

            # =====================================================================
            # TRANSPORT
            # =====================================================================
            {
                'name': 'School Vehicles',
                'category_type': 'TRANSPORT',
                'description': 'School bus operations, maintenance, and repairs',
                'requires_approval': True,
                'approval_limit': Decimal('300000.00'),
                'is_active': True,
            },
            {
                'name': 'Fuel Costs',
                'category_type': 'TRANSPORT',
                'description': 'Fuel for all school vehicles',
                'requires_approval': True,
                'approval_limit': Decimal('500000.00'),
                'is_active': True,
            },
            {
                'name': 'Official Travel',
                'category_type': 'TRANSPORT',
                'description': 'Staff official travel and transportation expenses',
                'requires_approval': True,
                'approval_limit': Decimal('200000.00'),
                'is_active': True,
            },

            # =====================================================================
            # MEALS & CATERING
            # =====================================================================
            {
                'name': 'Food & Beverages',
                'category_type': 'MEALS',
                'description': 'Raw food materials, ingredients, and beverages',
                'requires_approval': True,
                'approval_limit': Decimal('1000000.00'),
                'is_active': True,
            },
            {
                'name': 'Kitchen Supplies',
                'category_type': 'MEALS',
                'description': 'Cooking equipment, utensils, and kitchen supplies',
                'requires_approval': True,
                'approval_limit': Decimal('200000.00'),
                'is_active': True,
            },
            {
                'name': 'Catering Services',
                'category_type': 'MEALS',
                'description': 'External catering for special events and functions',
                'requires_approval': True,
                'approval_limit': Decimal('300000.00'),
                'is_active': True,
            },

            # =====================================================================
            # STAFF SALARIES & BENEFITS
            # =====================================================================
            {
                'name': 'Staff Salaries',
                'category_type': 'STAFF',
                'description': 'Monthly salaries and wages for all staff',
                'requires_approval': True,
                'approval_limit': Decimal('20000000.00'),
                'is_active': True,
            },
            {
                'name': 'Staff Benefits',
                'category_type': 'STAFF',
                'description': 'Medical insurance, pension, allowances, and other benefits',
                'requires_approval': True,
                'approval_limit': Decimal('2000000.00'),
                'is_active': True,
            },
            {
                'name': 'Temporary Staff',
                'category_type': 'STAFF',
                'description': 'Substitute teachers, casual workers, and temporary staff',
                'requires_approval': True,
                'approval_limit': Decimal('500000.00'),
                'is_active': True,
            },
            {
                'name': 'Staff Training',
                'category_type': 'STAFF',
                'description': 'Professional development and staff training programs',
                'requires_approval': True,
                'approval_limit': Decimal('1000000.00'),
                'is_active': True,
            },

            # =====================================================================
            # MEDICAL & HEALTH SERVICES
            # =====================================================================
            {
                'name': 'Health Services',
                'category_type': 'MEDICAL',
                'description': 'School clinic operations and medical staff',
                'requires_approval': True,
                'approval_limit': Decimal('300000.00'),
                'is_active': True,
            },
            {
                'name': 'Medical Supplies',
                'category_type': 'MEDICAL',
                'description': 'Medicines, medical equipment, and health supplies',
                'requires_approval': True,
                'approval_limit': Decimal('200000.00'),
                'is_active': True,
            },
            {
                'name': 'First Aid Supplies',
                'category_type': 'MEDICAL',
                'description': 'Basic medical and first aid supplies',
                'requires_approval': False,
                'approval_limit': Decimal('50000.00'),
                'is_active': True,
            },
            {
                'name': 'Health Insurance',
                'category_type': 'MEDICAL',
                'description': 'Student and staff health insurance premiums',
                'requires_approval': True,
                'approval_limit': Decimal('1000000.00'),
                'is_active': True,
            },

            # =====================================================================
            # SPORTS & PHYSICAL EDUCATION
            # =====================================================================
            {
                'name': 'Sports Equipment',
                'category_type': 'SPORTS',
                'description': 'Sports equipment, gear, and athletic supplies',
                'requires_approval': True,
                'approval_limit': Decimal('300000.00'),
                'is_active': True,
            },
            {
                'name': 'Sports Competitions',
                'category_type': 'SPORTS',
                'description': 'Inter-school competitions, tournaments, and sports events',
                'requires_approval': True,
                'approval_limit': Decimal('500000.00'),
                'is_active': True,
            },
            {
                'name': 'Music & Drama',
                'category_type': 'SPORTS',
                'description': 'Musical instruments, drama supplies, and performance arts',
                'requires_approval': True,
                'approval_limit': Decimal('400000.00'),
                'is_active': True,
            },
            {
                'name': 'School Events',
                'category_type': 'SPORTS',
                'description': 'School functions, celebrations, and special events',
                'requires_approval': True,
                'approval_limit': Decimal('600000.00'),
                'is_active': True,
            },

            # =====================================================================
            # STUDENT WELFARE & SERVICES
            # =====================================================================
            {
                'name': 'Student Welfare',
                'category_type': 'STUDENT_SERVICES',
                'description': 'Student counseling, welfare programs, and support services',
                'requires_approval': True,
                'approval_limit': Decimal('200000.00'),
                'is_active': True,
            },
            {
                'name': 'Student Activities',
                'category_type': 'STUDENT_SERVICES',
                'description': 'Student clubs, societies, and co-curricular activities',
                'requires_approval': True,
                'approval_limit': Decimal('300000.00'),
                'is_active': True,
            },
            {
                'name': 'Guidance & Counseling',
                'category_type': 'STUDENT_SERVICES',
                'description': 'Professional counseling services and guidance programs',
                'requires_approval': True,
                'approval_limit': Decimal('400000.00'),
                'is_active': True,
            },

            # =====================================================================
            # PARENT-TEACHER ASSOCIATION
            # =====================================================================
            {
                'name': 'PTA Activities',
                'category_type': 'PTA',
                'description': 'Parent-Teacher Association programs and activities',
                'requires_approval': True,
                'approval_limit': Decimal('200000.00'),
                'is_active': True,
            },
            {
                'name': 'Parent Engagement',
                'category_type': 'PTA',
                'description': 'Parent meetings, workshops, and engagement programs',
                'requires_approval': True,
                'approval_limit': Decimal('150000.00'),
                'is_active': True,
            },

            # =====================================================================
            # MARKETING & PROMOTION
            # =====================================================================
            {
                'name': 'Advertising',
                'category_type': 'MARKETING',
                'description': 'Print, radio, TV, and online advertising campaigns',
                'requires_approval': True,
                'approval_limit': Decimal('500000.00'),
                'is_active': True,
            },
            {
                'name': 'Website & Digital Marketing',
                'category_type': 'MARKETING',
                'description': 'Website maintenance, SEO, and digital marketing',
                'requires_approval': True,
                'approval_limit': Decimal('200000.00'),
                'is_active': True,
            },
            {
                'name': 'Public Relations',
                'category_type': 'MARKETING',
                'description': 'PR activities, community engagement, and media relations',
                'requires_approval': True,
                'approval_limit': Decimal('300000.00'),
                'is_active': True,
            },
            {
                'name': 'Promotional Materials',
                'category_type': 'MARKETING',
                'description': 'Brochures, banners, flyers, and promotional items',
                'requires_approval': True,
                'approval_limit': Decimal('150000.00'),
                'is_active': True,
            },

            # =====================================================================
            # TECHNOLOGY & IT
            # =====================================================================
            {
                'name': 'Hardware',
                'category_type': 'TECHNOLOGY',
                'description': 'Computer equipment, servers, and hardware purchases',
                'requires_approval': True,
                'approval_limit': Decimal('1000000.00'),
                'is_active': True,
            },
            {
                'name': 'Software & Licenses',
                'category_type': 'TECHNOLOGY',
                'description': 'Software licenses, subscriptions, and digital tools',
                'requires_approval': True,
                'approval_limit': Decimal('500000.00'),
                'is_active': True,
            },
            {
                'name': 'IT Maintenance',
                'category_type': 'TECHNOLOGY',
                'description': 'IT support, equipment maintenance, and technical services',
                'requires_approval': True,
                'approval_limit': Decimal('300000.00'),
                'is_active': True,
            },
            {
                'name': 'Internet & Connectivity',
                'category_type': 'TECHNOLOGY',
                'description': 'Internet services, bandwidth, and network connectivity',
                'requires_approval': True,
                'approval_limit': Decimal('400000.00'),
                'is_active': True,
            },

            # =====================================================================
            # LEGAL & PROFESSIONAL SERVICES
            # =====================================================================
            {
                'name': 'Legal Fees',
                'category_type': 'LEGAL',
                'description': 'Legal consultation, representation, and advisory services',
                'requires_approval': True,
                'approval_limit': Decimal('1000000.00'),
                'is_active': True,
            },
            {
                'name': 'Audit Fees',
                'category_type': 'LEGAL',
                'description': 'External audit, accounting services, and financial reviews',
                'requires_approval': True,
                'approval_limit': Decimal('2000000.00'),
                'is_active': True,
            },
            {
                'name': 'Compliance Costs',
                'category_type': 'LEGAL',
                'description': 'Regulatory compliance, certifications, and inspections',
                'requires_approval': True,
                'approval_limit': Decimal('500000.00'),
                'is_active': True,
            },

            # =====================================================================
            # FINANCIAL EXPENSES
            # =====================================================================
            {
                'name': 'Interest on Loans',
                'category_type': 'FINANCIAL',
                'description': 'Interest payments on borrowed funds and financing',
                'requires_approval': False,
                'approval_limit': None,
                'is_active': True,
            },
            {
                'name': 'Loan Principal Repayment',
                'category_type': 'FINANCIAL',
                'description': 'Principal repayment on loans and borrowings',
                'requires_approval': False,
                'approval_limit': None,
                'is_active': True,
            },
            {
                'name': 'Foreign Exchange Loss',
                'category_type': 'FINANCIAL',
                'description': 'Losses from currency exchange rate fluctuations',
                'requires_approval': False,
                'approval_limit': None,
                'is_active': True,
            },
            {
                'name': 'Investment Losses',
                'category_type': 'FINANCIAL',
                'description': 'Losses on financial investments and securities',
                'requires_approval': False,
                'approval_limit': None,
                'is_active': True,
            },

            # =====================================================================
            # INSURANCE & RISK MANAGEMENT
            # =====================================================================
            {
                'name': 'Building Insurance',
                'category_type': 'INSURANCE',
                'description': 'Property, building, and asset insurance premiums',
                'requires_approval': True,
                'approval_limit': Decimal('2000000.00'),
                'is_active': True,
            },
            {
                'name': 'Vehicle Insurance',
                'category_type': 'INSURANCE',
                'description': 'Motor vehicle insurance for school fleet',
                'requires_approval': True,
                'approval_limit': Decimal('1000000.00'),
                'is_active': True,
            },
            {
                'name': 'General Liability',
                'category_type': 'INSURANCE',
                'description': 'Public liability and third-party insurance coverage',
                'requires_approval': True,
                'approval_limit': Decimal('1500000.00'),
                'is_active': True,
            },
            {
                'name': 'Student Insurance',
                'category_type': 'INSURANCE',
                'description': 'Student accident and injury insurance coverage',
                'requires_approval': True,
                'approval_limit': Decimal('500000.00'),
                'is_active': True,
            },

            # =====================================================================
            # TAXES & COMPLIANCE
            # =====================================================================
            {
                'name': 'Corporate Income Tax',
                'category_type': 'TAX',
                'description': 'Corporate income tax payments to government',
                'requires_approval': False,
                'approval_limit': None,
                'is_active': True,
            },
            {
                'name': 'VAT Payments',
                'category_type': 'TAX',
                'description': 'Value Added Tax remittances to tax authority',
                'requires_approval': False,
                'approval_limit': None,
                'is_active': True,
            },
            {
                'name': 'Withholding Tax',
                'category_type': 'TAX',
                'description': 'Withholding tax on payments to suppliers and contractors',
                'requires_approval': False,
                'approval_limit': None,
                'is_active': True,
            },
            {
                'name': 'Property Tax',
                'category_type': 'TAX',
                'description': 'Local government property taxes and rates',
                'requires_approval': False,
                'approval_limit': None,
                'is_active': True,
            },
            {
                'name': 'Penalties & Fines',
                'category_type': 'TAX',
                'description': 'Government penalties, fines, and compliance charges',
                'requires_approval': False,
                'approval_limit': None,
                'is_active': True,
            },

            # =====================================================================
            # OWNER DRAWINGS & DISTRIBUTIONS
            # =====================================================================
            {
                'name': 'Owner Drawings',
                'category_type': 'DRAWINGS',
                'description': 'Proprietor personal withdrawals from school funds',
                'requires_approval': True,
                'approval_limit': Decimal('5000000.00'),
                'is_active': True,
            },
            {
                'name': 'Partner Distributions',
                'category_type': 'DRAWINGS',
                'description': 'Profit distributions to business partners',
                'requires_approval': True,
                'approval_limit': Decimal('10000000.00'),
                'is_active': True,
            },
            {
                'name': 'Shareholder Dividends',
                'category_type': 'DRAWINGS',
                'description': 'Dividend payments to shareholders',
                'requires_approval': True,
                'approval_limit': Decimal('10000000.00'),
                'is_active': True,
            },

            # =====================================================================
            # DEPRECIATION & AMORTIZATION
            # =====================================================================
            {
                'name': 'Depreciation - Buildings',
                'category_type': 'DEPRECIATION',
                'description': 'Annual depreciation charge on buildings and structures',
                'requires_approval': False,
                'approval_limit': None,
                'is_active': True,
            },
            {
                'name': 'Depreciation - Equipment',
                'category_type': 'DEPRECIATION',
                'description': 'Annual depreciation on furniture, fixtures, and equipment',
                'requires_approval': False,
                'approval_limit': None,
                'is_active': True,
            },
            {
                'name': 'Depreciation - Vehicles',
                'category_type': 'DEPRECIATION',
                'description': 'Annual depreciation on school vehicles and fleet',
                'requires_approval': False,
                'approval_limit': None,
                'is_active': True,
            },
            {
                'name': 'Amortization',
                'category_type': 'DEPRECIATION',
                'description': 'Amortization of intangible assets and goodwill',
                'requires_approval': False,
                'approval_limit': None,
                'is_active': True,
            },

            # =====================================================================
            # CHARITY & SOCIAL SUPPORT
            # =====================================================================
            {
                'name': 'Charitable Donations',
                'category_type': 'CHARITY',
                'description': 'Donations to charitable organizations and causes',
                'requires_approval': True,
                'approval_limit': Decimal('1000000.00'),
                'is_active': True,
            },
            {
                'name': 'Community Support',
                'category_type': 'CHARITY',
                'description': 'Community development and social support programs',
                'requires_approval': True,
                'approval_limit': Decimal('500000.00'),
                'is_active': True,
            },
            {
                'name': 'Scholarship Fund',
                'category_type': 'CHARITY',
                'description': 'Scholarships and financial aid for needy students',
                'requires_approval': True,
                'approval_limit': Decimal('2000000.00'),
                'is_active': True,
            },

            # =====================================================================
            # MISCELLANEOUS & EMERGENCY
            # =====================================================================
            {
                'name': 'Bad Debts',
                'category_type': 'MISCELLANEOUS',
                'description': 'Write-off of uncollectible student fees and debts',
                'requires_approval': True,
                'approval_limit': Decimal('1000000.00'),
                'is_active': True,
            },
            {
                'name': 'Emergency Expenses',
                'category_type': 'MISCELLANEOUS',
                'description': 'Unexpected emergency costs and urgent requirements',
                'requires_approval': True,
                'approval_limit': Decimal('500000.00'),
                'is_active': True,
            },
            {
                'name': 'Loss on Asset Disposal',
                'category_type': 'MISCELLANEOUS',
                'description': 'Losses incurred from selling or disposing of assets',
                'requires_approval': False,
                'approval_limit': None,
                'is_active': True,
            },

            # =====================================================================
            # OTHER EXPENSES
            # =====================================================================
            {
                'name': 'Miscellaneous Expenses',
                'category_type': 'OTHER',
                'description': 'Other uncategorized expenses not fitting elsewhere',
                'requires_approval': True,
                'approval_limit': Decimal('100000.00'),
                'is_active': True,
            },
        ]
    
    # =============================================================================
    # JOURNALS INITIALIZATION
    # =============================================================================

    @classmethod
    def get_journals(cls):
        """
        Standard accounting journals for school financial operations.
        
        Returns:
            list: List of journal dictionaries with all required fields
            
        Usage:
            >>> journals = SchoolInitConfig.get_journals()
            >>> for journal in journals:
            >>>     Journal.objects.create(**journal)
        
        Notes:
            - Each journal type serves a specific purpose in the accounting system
            - Journals help organize and categorize different types of transactions
            - The journal type determines which transactions can be posted to it
        """
        return [
            # =====================================================================
            # GENERAL JOURNAL
            # =====================================================================
            {
                'name': 'General Journal',
                'journal_type': 'GENERAL',
                'description': (
                    'General accounting entries including adjustments, corrections, '
                    'opening balances, and non-routine transactions. Used for any '
                    'transaction that does not fit into specialized journals.'
                ),
                'is_active': True,
            },

            # =====================================================================
            # FEE COLLECTION JOURNAL
            # =====================================================================
            {
                'name': 'Fee Collection Journal',
                'journal_type': 'FEES',
                'description': (
                    'All student fee-related transactions including tuition payments, '
                    'boarding fees, activity fees, and other student charges. Automatically '
                    'records debits to cash/bank and credits to revenue accounts.'
                ),
                'is_active': True,
            },

            # =====================================================================
            # EXPENSE JOURNAL
            # =====================================================================
            {
                'name': 'Expense Journal',
                'journal_type': 'EXPENSES',
                'description': (
                    'School operational expenses including salaries, utilities, supplies, '
                    'maintenance, and other costs. Records all non-payroll expenditure '
                    'with debits to expense accounts and credits to cash/payables.'
                ),
                'is_active': True,
            },

            # =====================================================================
            # CASH JOURNAL
            # =====================================================================
            {
                'name': 'Cash Journal',
                'journal_type': 'CASH',
                'description': (
                    'All cash transactions including cash receipts, cash payments, '
                    'petty cash disbursements, and cash transfers. Tracks physical '
                    'cash movements in and out of school premises.'
                ),
                'is_active': True,
            },

            # =====================================================================
            # BANK JOURNAL
            # =====================================================================
            {
                'name': 'Bank Journal',
                'journal_type': 'BANK',
                'description': (
                    'Bank-related transactions including deposits, withdrawals, bank transfers, '
                    'checks, mobile money payments, and bank charges. Facilitates bank '
                    'reconciliation and tracks all banking activities.'
                ),
                'is_active': True,
            },

            # =====================================================================
            # PAYROLL JOURNAL
            # =====================================================================
            {
                'name': 'Payroll Journal',
                'journal_type': 'PAYROLL',
                'description': (
                    'Staff salary and payroll entries including gross salaries, deductions, '
                    'net pay, employer contributions (NSSF, PAYE), and staff benefits. '
                    'Automatically generated from payroll processing system.'
                ),
                'is_active': True,
            },

            # =====================================================================
            # ADJUSTMENTS JOURNAL
            # =====================================================================
            {
                'name': 'Adjustments Journal',
                'journal_type': 'ADJUSTMENTS',
                'description': (
                    'Period-end adjustments including accruals, prepayments, depreciation, '
                    'provisions, and error corrections. Used for financial statement '
                    'preparation and closing entries at month-end and year-end.'
                ),
                'is_active': True,
            },
        ]
    
    # =========================================================================
    # FINANCIAL SETTINGS
    # =========================================================================
    
    @classmethod
    def get_financial_settings_defaults(cls, school):
        """Get financial settings defaults based on country"""
        country = str(school.country) if school.country else 'UG'
        
        # Currency mapping
        currency_map = {
            'UG': 'UGX',
            'KE': 'KES',
            'TZ': 'TZS',
            'RW': 'RWF',
            'SS': 'SSP',
            'US': 'USD',
        }
        
        currency = currency_map.get(country, 'UGX')
        
        # Decimal places based on currency
        decimal_places = 2 if currency in ['USD', 'GBP', 'SSP'] else 0
        
        # Minimum payment based on currency
        if currency in ['USD', 'GBP']:
            min_payment = Decimal('10.00')
        elif currency == 'SSP':
            min_payment = Decimal('100.00')
        else:
            min_payment = Decimal('1000.00')
        
        return {
            'school_currency': currency,
            'currency_position': 'BEFORE',
            'decimal_places': decimal_places,
            'use_thousand_separator': True,
            'invoice_prefix': 'INV',
            'payment_prefix': 'PMT',
            'receipt_prefix': 'RCPT',
            'expense_prefix': 'EXP',
            'default_payment_terms_days': 30,
            'late_fee_enabled': False,
            'late_fee_percentage': Decimal('5.00'),
            'grace_period_days': 7,
            'minimum_payment_amount': min_payment,
            'allow_partial_payments': True,
            'auto_apply_scholarships': True,
            'scholarship_approval_required': True,
            'auto_apply_discounts': False,
            'discount_approval_required': True,
            'expense_approval_required': True,
            'send_invoice_emails': True,
            'send_payment_confirmations': True,
        }
    
    # =========================================================================
    # ACCOUNT MAPPINGS
    # =========================================================================
    
    @classmethod
    def get_account_mappings_config(cls):
        """
        Get configuration for creating account mappings.
        Returns mapping of field names to search criteria.
        """
        return {
            # ✅ NEW: Split into bank and cash
            'default_bank_account': {
                'search': {'account_number': '1000'},
                'fallback': {'is_bank_account': True}
            },
            'default_cash_account': {
                'search': {'account_number': '1010'},
                'fallback': {'is_cash_account': True}
            },
            
            # ✅ NEW: Required accounts
            'default_payable_account': {
                'search': {'account_number': '2000'},
                'fallback': {'is_payable_account': True}
            },
            'default_equity_account': {
                'search': {'account_number': '3000'},
                'fallback': {'account_type__account_type': 'EQUITY'}
            },
            
            # Existing accounts
            'student_receivables_account': {
                'search': {'account_number': '1100'},
                'fallback': {'is_receivable_account': True}
            },
            'default_revenue_account': {
                'search': {'account_number': '4000'},
                'fallback': {'is_revenue_account': True}
            },
            'default_expense_account': {
                'search': {'account_number': '5900'},
                'fallback': {'is_expense_account': True}
            },
            'scholarship_discount_account': {
                'search': {'account_number': '5800'},
                'fallback': {'name__icontains': 'scholarship'}
            },
            
            # Optional accounts
            'boarding_revenue_account': {
                'search': {'account_number': '4100'},
                'optional': True
            },
            'uniform_and_book_sales_account': {  # ✅ RENAMED
                'search': {'account_number': '4200'},
                'optional': True
            },
            'salaries_account': {
                'search': {'account_number': '5000'},
                'optional': True
            },
            'utilities_account': {
                'search': {'account_number': '5100'},
                'optional': True
            },
            'boarding_expense_account': {  # ✅ NEW
                'search': {'account_number': '5600'},
                'optional': True
            },
        }
    
    # =============================================================================
    # DEPARTMENTS
    # =============================================================================
    
    @classmethod
    def get_departments(cls, school=None):
        """
        Comprehensive school departments.
        
        Returns:
            list: List of department dictionaries
        """
        return [
            # CORE ADMINISTRATIVE DEPARTMENTS
            {'name': 'Administration', 'code': 'ADMIN', 'department_type': 'ADMINISTRATIVE', 'description': 'School administration and management', 'is_academic': False, 'is_active': True},
            {'name': 'Finance & Accounts', 'code': 'FINANCE', 'department_type': 'ADMINISTRATIVE', 'description': 'Finance, accounting, and budgeting', 'is_academic': False, 'is_active': True},
            {'name': 'Human Resources', 'code': 'HR', 'department_type': 'ADMINISTRATIVE', 'description': 'Human resources management', 'is_academic': False, 'is_active': True},
            {'name': 'Student Affairs', 'code': 'STUDENT', 'department_type': 'SUPPORT', 'description': 'Student welfare and discipline', 'is_academic': False, 'is_active': True},
            {'name': 'Admissions & Registry', 'code': 'REGISTRY', 'department_type': 'ADMINISTRATIVE', 'description': 'Student admissions and records', 'is_academic': False, 'is_active': True},
            
            # ACADEMIC DEPARTMENTS
            {'name': 'Academic Affairs', 'code': 'ACADEMIC', 'department_type': 'ACADEMIC', 'description': 'Academic programs and curriculum oversight', 'is_academic': True, 'is_active': True},
            {'name': 'Early Childhood Development', 'code': 'ECD', 'department_type': 'ACADEMIC', 'description': 'Kindergarten and nursery education', 'is_academic': True, 'is_active': True},
            {'name': 'Primary Education', 'code': 'PRIMARY', 'department_type': 'ACADEMIC', 'description': 'Primary school education', 'is_academic': True, 'is_active': True},
            {'name': 'Mathematics Department', 'code': 'MATH', 'department_type': 'ACADEMIC', 'academic_subtype': 'MATHEMATICS', 'description': 'Mathematics instruction', 'is_academic': True, 'is_active': True},
            {'name': 'Science Department', 'code': 'SCIENCE', 'department_type': 'ACADEMIC', 'description': 'Science instruction (Biology, Chemistry, Physics)', 'is_academic': True, 'is_active': True},
            {'name': 'English Department', 'code': 'ENGLISH', 'department_type': 'ACADEMIC', 'academic_subtype': 'ENGLISH', 'description': 'English language and literature', 'is_academic': True, 'is_active': True},
            {'name': 'Social Studies Department', 'code': 'SST', 'department_type': 'ACADEMIC', 'description': 'History, Geography, and Social Studies', 'is_academic': True, 'is_active': True},
            {'name': 'Languages Department', 'code': 'LANG', 'department_type': 'ACADEMIC', 'description': 'Foreign and local languages', 'is_academic': True, 'is_active': True},
            {'name': 'Business Studies Department', 'code': 'BUSINESS', 'department_type': 'ACADEMIC', 'academic_subtype': 'BUSINESS_STUDIES', 'description': 'Business, Economics, and Accounting', 'is_academic': True, 'is_active': True},
            {'name': 'Arts & Creative Studies', 'code': 'ARTS', 'department_type': 'ACADEMIC', 'academic_subtype': 'ARTS', 'description': 'Fine Arts, Music, Drama', 'is_academic': True, 'is_active': True},
            {'name': 'Physical Education', 'code': 'PE', 'department_type': 'ACADEMIC', 'academic_subtype': 'PHYSICAL_EDUCATION', 'description': 'Physical education and sports', 'is_academic': True, 'is_active': True},
            {'name': 'Religious Education', 'code': 'RE', 'department_type': 'ACADEMIC', 'description': 'Religious and moral education', 'is_academic': True, 'is_active': True},
            
            # SPECIALIZED ACADEMIC SUPPORT
            {'name': 'Library Services', 'code': 'LIBRARY', 'department_type': 'ACADEMIC', 'description': 'Library and information services', 'is_academic': False, 'is_active': True},
            {'name': 'ICT Services', 'code': 'ICT', 'department_type': 'TECHNICAL', 'description': 'Information and communication technology', 'is_academic': False, 'is_active': True},
            {'name': 'Examinations Office', 'code': 'EXAMS', 'department_type': 'ACADEMIC', 'description': 'Examinations coordination and management', 'is_academic': False, 'is_active': True},
            {'name': 'Guidance & Counseling', 'code': 'COUNSEL', 'department_type': 'SUPPORT', 'description': 'Student guidance and counseling services', 'is_academic': False, 'is_active': True},
            
            # OPERATIONAL SUPPORT DEPARTMENTS
            {'name': 'Facilities & Maintenance', 'code': 'MAINT', 'department_type': 'MAINTENANCE', 'description': 'Building and equipment maintenance', 'is_academic': False, 'is_active': True},
            {'name': 'Security Services', 'code': 'SECURITY', 'department_type': 'SECURITY', 'description': 'School security and safety', 'is_academic': False, 'is_active': True},
            {'name': 'Transport Services', 'code': 'TRANSPORT', 'department_type': 'TRANSPORT', 'description': 'School transport and logistics', 'is_academic': False, 'is_active': True},
            {'name': 'Health Services', 'code': 'HEALTH', 'department_type': 'HEALTH', 'description': 'School clinic and health services', 'is_academic': False, 'is_active': True},
            {'name': 'Boarding & Hostel Services', 'code': 'BOARDING', 'department_type': 'SUPPORT', 'description': 'Boarding and residential services', 'is_academic': False, 'is_active': True},
            {'name': 'Catering & Food Services', 'code': 'CATERING', 'department_type': 'CATERING', 'description': 'Food preparation and catering services', 'is_academic': False, 'is_active': True},
            {'name': 'Procurement & Stores', 'code': 'PROCUREMENT', 'department_type': 'PROCUREMENT', 'description': 'Purchasing and inventory management', 'is_academic': False, 'is_active': True},
            
            # SPECIAL PROGRAMS
            {'name': 'Special Needs Support', 'code': 'SPECIAL', 'department_type': 'SUPPORT', 'description': 'Special needs education support', 'is_academic': True, 'is_active': True},
            {'name': 'International Programs', 'code': 'INTL', 'department_type': 'ACADEMIC', 'description': 'International curriculum and programs', 'is_academic': True, 'is_active': True},
            {'name': 'Parent Relations', 'code': 'PARENT', 'department_type': 'SUPPORT', 'description': 'Parent-Teacher Association and relations', 'is_academic': False, 'is_active': True},
            {'name': 'Quality Assurance', 'code': 'QA', 'department_type': 'ACADEMIC', 'description': 'Academic quality assurance and standards', 'is_academic': True, 'is_active': True},
            {'name': 'Marketing & Communications', 'code': 'MARKETING', 'department_type': 'ADMINISTRATIVE', 'description': 'Marketing, PR, and communications', 'is_academic': False, 'is_active': True},
            {'name': 'Research & Development', 'code': 'RD', 'department_type': 'ACADEMIC', 'description': 'Educational research and innovation', 'is_academic': True, 'is_active': True},
        ]
    
    # =============================================================================
    # DESIGNATIONS
    # =============================================================================
    
    @classmethod
    def get_designations(cls, school=None):
        """
        Get default job designations mapped to departments.
        
        Note: These designations reference department codes.
        Departments must be created first.
        
        Returns:
            list: List of designation dictionaries
            
        Usage:
            >>> designations = SchoolInitConfig.get_designations()
            >>> for desig in designations:
            >>>     dept = Department.objects.get(code=desig['department_code'])
            >>>     Designation.objects.create(**desig, department=dept)
        """
        designations = [
            # SENIOR MANAGEMENT
            {
                'name': 'Head Teacher',
                'code': 'HEAD',
                'department_code': 'ADMIN',
                'description': 'Overall school leadership and management',
                'is_teaching': True,
                'is_management': True,
                'rank_order': 1,
                'min_salary': Decimal('2000000.00'),
                'max_salary': Decimal('5000000.00'),
                'is_active': True,
            },
            {
                'name': 'Deputy Head Teacher',
                'code': 'DEPUTY',
                'department_code': 'ADMIN',
                'description': 'Assists head teacher in school management',
                'is_teaching': True,
                'is_management': True,
                'rank_order': 2,
                'min_salary': Decimal('1500000.00'),
                'max_salary': Decimal('3000000.00'),
                'is_active': True,
            },
            {
                'name': 'Academic Director',
                'code': 'ACADIR',
                'department_code': 'ACADEMIC',
                'description': 'Oversees academic programs and curriculum',
                'is_teaching': True,
                'is_management': True,
                'rank_order': 3,
                'min_salary': Decimal('1200000.00'),
                'max_salary': Decimal('2500000.00'),
                'is_active': True,
            },
            
            # TEACHING POSITIONS
            {
                'name': 'Senior Teacher',
                'code': 'SRTEACH',
                'department_code': 'ACADEMIC',
                'description': 'Experienced teacher with mentorship responsibilities',
                'is_teaching': True,
                'is_management': False,
                'rank_order': 4,
                'min_salary': Decimal('800000.00'),
                'max_salary': Decimal('1500000.00'),
                'is_active': True,
            },
            {
                'name': 'Teacher',
                'code': 'TEACHER',
                'department_code': 'ACADEMIC',
                'description': 'Classroom teacher',
                'is_teaching': True,
                'is_management': False,
                'rank_order': 5,
                'min_salary': Decimal('600000.00'),
                'max_salary': Decimal('1200000.00'),
                'is_active': True,
            },
            
            # ADMINISTRATIVE POSITIONS
            {
                'name': 'School Administrator',
                'code': 'ADMIN',
                'department_code': 'ADMIN',
                'description': 'General school administration',
                'is_teaching': False,
                'is_management': True,
                'rank_order': 7,
                'min_salary': Decimal('700000.00'),
                'max_salary': Decimal('1400000.00'),
                'is_active': True,
            },
            {
                'name': 'School Secretary',
                'code': 'SECRETARY',
                'department_code': 'ADMIN',
                'description': 'Administrative support and office management',
                'is_teaching': False,
                'is_management': False,
                'rank_order': 8,
                'min_salary': Decimal('400000.00'),
                'max_salary': Decimal('800000.00'),
                'is_active': True,
            },
            
            # FINANCIAL POSITIONS
            {
                'name': 'Bursar',
                'code': 'BURSAR',
                'department_code': 'FINANCE',
                'description': 'Financial management and accounting',
                'is_teaching': False,
                'is_management': True,
                'rank_order': 9,
                'min_salary': Decimal('900000.00'),
                'max_salary': Decimal('1800000.00'),
                'is_active': True,
            },
            {
                'name': 'Accounts Clerk',
                'code': 'ACCOUNTS',
                'department_code': 'FINANCE',
                'description': 'Financial record keeping and transactions',
                'is_teaching': False,
                'is_management': False,
                'rank_order': 10,
                'min_salary': Decimal('500000.00'),
                'max_salary': Decimal('900000.00'),
                'is_active': True,
            },
            
            # PROCUREMENT
            {
                'name': 'Procurement Officer',
                'code': 'PROCURE',
                'department_code': 'PROCUREMENT',
                'description': 'Purchasing and vendor management',
                'is_teaching': False,
                'is_management': False,
                'rank_order': 11,
                'min_salary': Decimal('700000.00'),
                'max_salary': Decimal('1300000.00'),
                'is_active': True,
            },
            
            # STUDENT SUPPORT
            {
                'name': 'Dean of Students',
                'code': 'DEAN',
                'department_code': 'STUDENT',
                'description': 'Student affairs and welfare management',
                'is_teaching': False,
                'is_management': True,
                'rank_order': 13,
                'min_salary': Decimal('800000.00'),
                'max_salary': Decimal('1500000.00'),
                'is_active': True,
            },
            {
                'name': 'School Counselor',
                'code': 'COUNSEL',
                'department_code': 'COUNSEL',
                'description': 'Student counseling and guidance',
                'is_teaching': False,
                'is_management': False,
                'rank_order': 14,
                'min_salary': Decimal('600000.00'),
                'max_salary': Decimal('1200000.00'),
                'is_active': True,
            },
            
            # SUPPORT STAFF
            {
                'name': 'Librarian',
                'code': 'LIBRAR',
                'department_code': 'LIBRARY',
                'description': 'Library management and information services',
                'is_teaching': False,
                'is_management': False,
                'rank_order': 16,
                'min_salary': Decimal('500000.00'),
                'max_salary': Decimal('1000000.00'),
                'is_active': True,
            },
            {
                'name': 'ICT Coordinator',
                'code': 'ICTCOORD',
                'department_code': 'ICT',
                'description': 'Technology coordination and support',
                'is_teaching': False,
                'is_management': False,
                'rank_order': 17,
                'min_salary': Decimal('600000.00'),
                'max_salary': Decimal('1200000.00'),
                'is_active': True,
            },
            {
                'name': 'School Nurse',
                'code': 'NURSE',
                'department_code': 'HEALTH',
                'description': 'Health services and medical care',
                'is_teaching': False,
                'is_management': False,
                'rank_order': 18,
                'min_salary': Decimal('500000.00'),
                'max_salary': Decimal('1000000.00'),
                'is_active': True,
            },
            
            # OPERATIONAL STAFF
            {
                'name': 'Security Guard',
                'code': 'SECURITY',
                'department_code': 'SECURITY',
                'description': 'School security and safety',
                'is_teaching': False,
                'is_management': False,
                'rank_order': 19,
                'min_salary': Decimal('300000.00'),
                'max_salary': Decimal('600000.00'),
                'is_active': True,
            },
            {
                'name': 'Driver',
                'code': 'DRIVER',
                'department_code': 'TRANSPORT',
                'description': 'School transport services',
                'is_teaching': False,
                'is_management': False,
                'rank_order': 20,
                'min_salary': Decimal('350000.00'),
                'max_salary': Decimal('700000.00'),
                'is_active': True,
            },
            {
                'name': 'Groundskeeper',
                'code': 'GROUNDS',
                'department_code': 'MAINT',
                'description': 'Grounds and facility maintenance',
                'is_teaching': False,
                'is_management': False,
                'rank_order': 21,
                'min_salary': Decimal('300000.00'),
                'max_salary': Decimal('600000.00'),
                'is_active': True,
            },
            
            # CATERING STAFF
            {
                'name': 'Head Cook',
                'code': 'HEAD_COOK',
                'department_code': 'CATERING',
                'description': 'Kitchen and catering management',
                'is_teaching': False,
                'is_management': True,
                'rank_order': 22,
                'min_salary': Decimal('500000.00'),
                'max_salary': Decimal('900000.00'),
                'is_active': True,
            },
            {
                'name': 'School Cook',
                'code': 'COOK',
                'department_code': 'CATERING',
                'description': 'Food preparation and cooking',
                'is_teaching': False,
                'is_management': False,
                'rank_order': 23,
                'min_salary': Decimal('350000.00'),
                'max_salary': Decimal('700000.00'),
                'is_active': True,
            },
            {
                'name': 'Assistant Cook',
                'code': 'AST_COOK',
                'department_code': 'CATERING',
                'description': 'Kitchen assistance and food prep',
                'is_teaching': False,
                'is_management': False,
                'rank_order': 24,
                'min_salary': Decimal('300000.00'),
                'max_salary': Decimal('550000.00'),
                'is_active': True,
            },
            {
                'name': 'Kitchen Assistant',
                'code': 'KITCHEN_AST',
                'department_code': 'CATERING',
                'description': 'Kitchen cleaning and support',
                'is_teaching': False,
                'is_management': False,
                'rank_order': 25,
                'min_salary': Decimal('250000.00'),
                'max_salary': Decimal('500000.00'),
                'is_active': True,
            },
            
            # BOARDING STAFF
            {
                'name': 'Matron',
                'code': 'MATRON',
                'department_code': 'BOARDING',
                'description': 'Boarding hostel supervision and welfare',
                'is_teaching': False,
                'is_management': True,
                'rank_order': 26,
                'min_salary': Decimal('600000.00'),
                'max_salary': Decimal('1200000.00'),
                'is_active': True,
            },
            {
                'name': 'Boarding Supervisor',
                'code': 'BOARD_SUP',
                'department_code': 'BOARDING',
                'description': 'Boarding facility oversight',
                'is_teaching': False,
                'is_management': False,
                'rank_order': 27,
                'min_salary': Decimal('400000.00'),
                'max_salary': Decimal('800000.00'),
                'is_active': True,
            },
            
            # ADDITIONAL SUPPORT STAFF
            {
                'name': 'School Messenger',
                'code': 'MESSENGER',
                'department_code': 'ADMIN',
                'description': 'Message delivery and errands',
                'is_teaching': False,
                'is_management': False,
                'rank_order': 28,
                'min_salary': Decimal('250000.00'),
                'max_salary': Decimal('500000.00'),
                'is_active': True,
            },
            {
                'name': 'Cleaner',
                'code': 'CLEANER',
                'department_code': 'MAINT',
                'description': 'School cleaning services',
                'is_teaching': False,
                'is_management': False,
                'rank_order': 29,
                'min_salary': Decimal('250000.00'),
                'max_salary': Decimal('500000.00'),
                'is_active': True,
            },
            {
                'name': 'Laundry Attendant',
                'code': 'LAUNDRY',
                'department_code': 'BOARDING',
                'description': 'Laundry services for boarding',
                'is_teaching': False,
                'is_management': False,
                'rank_order': 30,
                'min_salary': Decimal('300000.00'),
                'max_salary': Decimal('550000.00'),
                'is_active': True,
            },
            {
                'name': 'Storekeeper',
                'code': 'STOREKEEPER',
                'department_code': 'PROCUREMENT',
                'description': 'Inventory and stores management',
                'is_teaching': False,
                'is_management': False,
                'rank_order': 31,
                'min_salary': Decimal('400000.00'),
                'max_salary': Decimal('750000.00'),
                'is_active': True,
            },
        ]
        
        return designations
    
   # =============================================================================
    # DISPLAY GROUPS
    # =============================================================================
    
    @classmethod
    def get_display_groups(cls):
        """
        Get display groups for fee categorization on invoices.
        
        Returns:
            list: List of display group dictionaries
            
        Usage:
            >>> groups = SchoolInitConfig.get_display_groups()
            >>> for group in groups:
            >>>     DisplayGroup.objects.create(**group)
        """
        return [
            {
                'name': 'Tuition & Academic Fees',
                'description': 'Core academic fees and tuition',
                'display_order': 1,
                'color_code': '#2E86AB',
                'show_as_group': True,
                'show_group_subtotal': True,
                'is_active': True,
            },
            {
                'name': 'Registration & Admission',
                'description': 'One-time enrollment and admission fees',
                'display_order': 2,
                'color_code': '#A23B72',
                'show_as_group': True,
                'show_group_subtotal': True,
                'is_active': True,
            },
            {
                'name': 'Boarding & Accommodation',
                'description': 'Boarding fees and accommodation costs',
                'display_order': 3,
                'color_code': '#F18F01',
                'show_as_group': True,
                'show_group_subtotal': True,
                'is_active': True,
            },
            {
                'name': 'Meals & Catering',
                'description': 'Food and catering services',
                'display_order': 4,
                'color_code': '#C73E1D',
                'show_as_group': True,
                'show_group_subtotal': True,
                'is_active': True,
            },
            {
                'name': 'Activities & Services',
                'description': 'Extracurricular and support services',
                'display_order': 5,
                'color_code': '#7209B7',
                'show_as_group': True,
                'show_group_subtotal': True,
                'is_active': True,
            },
            {
                'name': 'Transport & Travel',
                'description': 'Transportation and travel costs',
                'display_order': 6,
                'color_code': '#560BAD',
                'show_as_group': True,
                'show_group_subtotal': True,
                'is_active': True,
            },
            {
                'name': 'Technology & Equipment',
                'description': 'IT services and equipment fees',
                'display_order': 7,
                'color_code': '#264653',
                'show_as_group': True,
                'show_group_subtotal': True,
                'is_active': True,
            },
            {
                'name': 'Medical & Health',
                'description': 'Health services and medical fees',
                'display_order': 8,
                'color_code': '#2A9D8F',
                'show_as_group': True,
                'show_group_subtotal': True,
                'is_active': True,
            },
            {
                'name': 'Uniform & Supplies',
                'description': 'School uniforms and supplies',
                'display_order': 9,
                'color_code': '#E76F51',
                'show_as_group': True,
                'show_group_subtotal': True,
                'is_active': True,
            },
            {
                'name': 'Special Programs',
                'description': 'Specialized courses and programs',
                'display_order': 10,
                'color_code': '#F4A261',
                'show_as_group': True,
                'show_group_subtotal': True,
                'is_active': True,
            },
            {
                'name': 'Penalties & Adjustments',
                'description': 'Late fees, penalties, and adjustments',
                'display_order': 11,
                'color_code': '#E63946',
                'show_as_group': False,
                'show_group_subtotal': False,
                'is_active': True,
            },
        ]

    # =========================================================================
    # FEE CATEGORIES
    # =========================================================================
    
    @classmethod
    def get_fee_categories(cls, school):
        """
        Comprehensive fee categories based on school type.
        
        Returns:
            list: List of fee category dictionaries
        """
        categories = [
            # TUITION & ACADEMIC FEES
            {'name': 'Tuition Fee', 'code': 'TUITION', 'category_type': 'TUITION', 'frequency': 'TERMLY', 'applicability': 'ALL', 'is_mandatory': True, 'allows_partial_payment': True, 'display_group': 'Tuition & Academic Fees', 'description': 'Core academic fees and instruction'},
            {'name': 'Academic Enhancement Fee', 'code': 'ACADEMIC_ENH', 'category_type': 'OTHER', 'frequency': 'TERMLY', 'applicability': 'ALL', 'is_mandatory': False, 'allows_partial_payment': True, 'display_group': 'Tuition & Academic Fees', 'description': 'Additional academic support'},
            {'name': 'Examination Fee', 'code': 'EXAM', 'category_type': 'EXAM', 'frequency': 'TERMLY', 'applicability': 'ALL', 'is_mandatory': True, 'allows_partial_payment': True, 'display_group': 'Tuition & Academic Fees', 'description': 'Internal and external examination fees'},
            {'name': 'Development Fee', 'code': 'DEV', 'category_type': 'DEVELOPMENT', 'frequency': 'YEARLY', 'applicability': 'ALL', 'is_mandatory': True, 'allows_partial_payment': True, 'display_group': 'Tuition & Academic Fees', 'description': 'School development projects'},
            {'name': 'Laboratory Fee', 'code': 'LAB', 'category_type': 'LABORATORY', 'frequency': 'TERMLY', 'applicability': 'SCIENCE_STUDENTS', 'is_mandatory': True, 'allows_partial_payment': True, 'display_group': 'Tuition & Academic Fees', 'description': 'Science lab usage'},

            # REGISTRATION & ADMISSION
            {'name': 'Registration Fee', 'code': 'REG', 'category_type': 'REGISTRATION', 'frequency': 'ONE_TIME', 'applicability': 'NEW_STUDENTS', 'is_mandatory': True, 'allows_partial_payment': False, 'display_group': 'Registration & Admission', 'description': 'One-time registration'},
            {'name': 'Admission Fee', 'code': 'ADMISSION', 'category_type': 'ADMISSION', 'frequency': 'ONE_TIME', 'applicability': 'NEW_STUDENTS', 'is_mandatory': True, 'allows_partial_payment': False, 'display_group': 'Registration & Admission', 'description': 'Admission processing'},
            {'name': 'Application Fee', 'code': 'APPLICATION', 'category_type': 'OTHER', 'frequency': 'ONE_TIME', 'applicability': 'APPLICANTS', 'is_mandatory': True, 'allows_partial_payment': False, 'display_group': 'Registration & Admission', 'description': 'Application processing'},

            # BOARDING & ACCOMMODATION
            {'name': 'Boarding Fee', 'code': 'BOARD', 'category_type': 'BOARDING', 'frequency': 'TERMLY', 'applicability': 'BOARDERS', 'is_mandatory': True, 'allows_partial_payment': True, 'display_group': 'Boarding & Accommodation', 'description': 'Boarding accommodation'},
            {'name': 'Accommodation Deposit', 'code': 'ACCOM_DEPOSIT', 'category_type': 'OTHER', 'frequency': 'ONE_TIME', 'applicability': 'BOARDERS', 'is_mandatory': True, 'allows_partial_payment': False, 'display_group': 'Boarding & Accommodation', 'description': 'Refundable security deposit'},
            {'name': 'Laundry Fee', 'code': 'LAUNDRY', 'category_type': 'LAUNDRY', 'frequency': 'TERMLY', 'applicability': 'BOARDERS', 'is_mandatory': False, 'allows_partial_payment': True, 'display_group': 'Boarding & Accommodation', 'description': 'Laundry services'},

            # MEALS & CATERING
            {'name': 'Meals Fee', 'code': 'MEALS', 'category_type': 'MEALS', 'frequency': 'TERMLY', 'applicability': 'BOARDERS', 'is_mandatory': True, 'allows_partial_payment': True, 'display_group': 'Meals & Catering', 'description': 'Full board meal service'},
            {'name': 'Day Scholar Meals', 'code': 'DAY_MEALS', 'category_type': 'MEALS', 'frequency': 'TERMLY', 'applicability': 'DAY_SCHOLARS', 'is_mandatory': False, 'allows_partial_payment': True, 'display_group': 'Meals & Catering', 'description': 'Optional lunch service'},
            {'name': 'Breakfast Only', 'code': 'BREAKFAST', 'category_type': 'MEALS', 'frequency': 'TERMLY', 'applicability': 'OPTIONAL', 'is_mandatory': False, 'allows_partial_payment': True, 'display_group': 'Meals & Catering', 'description': 'Breakfast meal plan'},

            # ACTIVITIES & SERVICES
            {'name': 'Library Fee', 'code': 'LIB', 'category_type': 'LIBRARY', 'frequency': 'YEARLY', 'applicability': 'ALL', 'is_mandatory': True, 'allows_partial_payment': True, 'display_group': 'Activities & Services', 'description': 'Library services'},
            {'name': 'Sports Fee', 'code': 'SPORTS', 'category_type': 'SPORT', 'frequency': 'YEARLY', 'applicability': 'ALL', 'is_mandatory': False, 'allows_partial_payment': True, 'display_group': 'Activities & Services', 'description': 'Sports activities'},
            {'name': 'Student ID Card', 'code': 'ID_CARD', 'category_type': 'OTHER', 'frequency': 'YEARLY', 'applicability': 'ALL', 'is_mandatory': True, 'allows_partial_payment': False, 'display_group': 'Activities & Services', 'description': 'Student identification'},
            {'name': 'Music & Drama', 'code': 'MUSIC_DRAMA', 'category_type': 'CLUB', 'frequency': 'TERMLY', 'applicability': 'OPTIONAL', 'is_mandatory': False, 'allows_partial_payment': True, 'display_group': 'Activities & Services', 'description': 'Music and drama activities'},
            {'name': 'Clubs & Societies', 'code': 'CLUBS', 'category_type': 'CLUB', 'frequency': 'TERMLY', 'applicability': 'OPTIONAL', 'is_mandatory': False, 'allows_partial_payment': True, 'display_group': 'Activities & Services', 'description': 'Student clubs'},

            # TRANSPORT & TRAVEL
            {'name': 'Transport Fee', 'code': 'TRANS', 'category_type': 'TRANSPORT', 'frequency': 'TERMLY', 'applicability': 'TRANSPORT_USERS', 'is_mandatory': False, 'allows_partial_payment': True, 'display_group': 'Transport & Travel', 'description': 'School bus service'},
            {'name': 'Field Trip Fee', 'code': 'FIELD_TRIP', 'category_type': 'FIELD_TRIP', 'frequency': 'TERMLY', 'applicability': 'PARTICIPANTS', 'is_mandatory': False, 'allows_partial_payment': True, 'display_group': 'Transport & Travel', 'description': 'Educational trips'},

            # TECHNOLOGY & EQUIPMENT
            {'name': 'Computer Fee', 'code': 'COMPUTER', 'category_type': 'TECHNOLOGY', 'frequency': 'TERMLY', 'applicability': 'ICT_STUDENTS', 'is_mandatory': True, 'allows_partial_payment': True, 'display_group': 'Technology & Equipment', 'description': 'Computer lab usage'},
            {'name': 'Internet & WiFi Fee', 'code': 'INTERNET', 'category_type': 'TECHNOLOGY', 'frequency': 'TERMLY', 'applicability': 'ALL', 'is_mandatory': False, 'allows_partial_payment': True, 'display_group': 'Technology & Equipment', 'description': 'Internet access'},

            # MEDICAL & HEALTH
            {'name': 'Medical Fee', 'code': 'MED', 'category_type': 'MEDICAL', 'frequency': 'YEARLY', 'applicability': 'ALL', 'is_mandatory': False, 'allows_partial_payment': True, 'display_group': 'Medical & Health', 'description': 'Basic medical services'},
            {'name': 'Health Insurance', 'code': 'HEALTH_INS', 'category_type': 'INSURANCE', 'frequency': 'YEARLY', 'applicability': 'ALL', 'is_mandatory': False, 'allows_partial_payment': True, 'display_group': 'Medical & Health', 'description': 'Student health insurance'},

            # UNIFORM & SUPPLIES
            {'name': 'School Uniform', 'code': 'UNIFORM', 'category_type': 'UNIFORM', 'frequency': 'YEARLY', 'applicability': 'ALL', 'is_mandatory': True, 'allows_partial_payment': True, 'display_group': 'Uniform & Supplies', 'description': 'Official school uniform'},
            {'name': 'Textbooks', 'code': 'TEXTBOOKS', 'category_type': 'BOOKS', 'frequency': 'YEARLY', 'applicability': 'ALL', 'is_mandatory': False, 'allows_partial_payment': True, 'display_group': 'Uniform & Supplies', 'description': 'Required textbooks'},
            {'name': 'Stationery Pack', 'code': 'STATIONERY', 'category_type': 'OTHER', 'frequency': 'TERMLY', 'applicability': 'ALL', 'is_mandatory': False, 'allows_partial_payment': True, 'display_group': 'Uniform & Supplies', 'description': 'Stationery supplies'},

            # SPECIAL PROGRAMS
            {'name': 'Remedial Classes', 'code': 'REMEDIAL', 'category_type': 'OTHER', 'frequency': 'TERMLY', 'applicability': 'OPTIONAL', 'is_mandatory': False, 'allows_partial_payment': True, 'display_group': 'Special Programs', 'description': 'Extra tuition classes'},
            {'name': 'Graduation Fee', 'code': 'GRADUATION', 'category_type': 'GRADUATION', 'frequency': 'ONE_TIME', 'applicability': 'CONTINUING_STUDENTS', 'is_mandatory': True, 'allows_partial_payment': False, 'display_group': 'Special Programs', 'description': 'Graduation ceremony'},

            # PENALTIES & ADJUSTMENTS
            {'name': 'Late Payment Penalty', 'code': 'LATE_PENALTY', 'category_type': 'LATE_PAYMENT', 'frequency': 'MONTHLY', 'applicability': 'DEFAULTERS', 'is_mandatory': True, 'allows_partial_payment': False, 'display_group': 'Penalties & Adjustments', 'description': 'Late payment charges'},
            {'name': 'Replacement Fee', 'code': 'REPLACEMENT', 'category_type': 'OTHER', 'frequency': 'PER_INCIDENT', 'applicability': 'ALL', 'is_mandatory': True, 'allows_partial_payment': False, 'display_group': 'Penalties & Adjustments', 'description': 'Lost item replacement'},
        ]
        
        return categories
    
    # =============================================================================
    # PAYMENT METHODS
    # =============================================================================
    
    @classmethod
    def get_payment_methods(cls):
        """
        Get default payment methods with account mapping configuration.
        
        Returns:
            list: List of payment method dictionaries
            
        Usage:
            >>> methods = SchoolInitConfig.get_payment_methods()
            >>> for method in methods:
            >>>     PaymentMethod.objects.create(**method)
        """
        return [
            {
                'name': 'Cash Payment',
                'code': 'CASH',
                'method_type': 'CASH',
                'instructions': 'Physical cash payments at school office',
                'is_active': True,
                'requires_approval': False,
                'display_order': 1,
                'icon': 'fa-money-bill-wave',
                'color_code': '#28a745',
            },
            {
                'name': 'Bank Transfer',
                'code': 'BANK_TRANSFER',
                'method_type': 'BANK_TRANSFER',
                'instructions': 'Electronic bank transfer to school account',
                'is_active': True,
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
                'instructions': 'MTN Mobile Money payments via *165#',
                'is_active': True,
                'requires_approval': False,
                'has_transaction_fee': True,
                'transaction_fee_type': 'PERCENTAGE',
                'transaction_fee_amount': Decimal('1.5'),
                'fee_bearer': 'PARENT',
                'display_order': 3,
                'icon': 'fa-mobile-alt',
                'color_code': '#ffcc00',
            },
            {
                'name': 'Airtel Money',
                'code': 'AIRTEL_MOBILE',
                'method_type': 'MOBILE_MONEY',
                'mobile_money_provider': 'AIRTEL',
                'instructions': 'Airtel Money payments via *185#',
                'is_active': True,
                'requires_approval': False,
                'has_transaction_fee': True,
                'transaction_fee_type': 'PERCENTAGE',
                'transaction_fee_amount': Decimal('1.5'),
                'fee_bearer': 'PARENT',
                'display_order': 4,
                'icon': 'fa-mobile-alt',
                'color_code': '#ff6b35',
            },
            {
                'name': 'Bank Check',
                'code': 'CHECK',
                'method_type': 'CHEQUE',
                'instructions': 'Bank check payments',
                'is_active': True,
                'requires_approval': True,
                'display_order': 5,
                'icon': 'fa-money-check',
                'color_code': '#6c757d',
            },
            {
                'name': 'Credit/Debit Card',
                'code': 'CARD',
                'method_type': 'CARD',
                'instructions': 'Visa, MasterCard, and local debit cards',
                'is_active': True,
                'requires_approval': False,
                'has_transaction_fee': True,
                'transaction_fee_type': 'PERCENTAGE',
                'transaction_fee_amount': Decimal('2.5'),
                'fee_bearer': 'PARENT',
                'display_order': 6,
                'icon': 'fa-credit-card',
                'color_code': '#17a2b8',
            },
        ]
    
    # =============================================================================
    # TAX RATES
    # =============================================================================
    
    @classmethod
    def get_tax_rates(cls, school=None):
        """
        Get default tax rates based on country.
        
        Args:
            school: School instance (optional, for country-specific rates)
            
        Returns:
            list: List of tax rate dictionaries
            
        Usage:
            >>> rates = SchoolInitConfig.get_tax_rates(school)
            >>> for rate in rates:
            >>>     TaxRate.objects.create(**rate)
        """
        from datetime import date
        
        # Default to Uganda tax rates
        country = str(school.country) if school and school.country else 'UG'
        
        # Uganda tax rates (default)
        if country == 'UG':
            return [
                {
                    'name': 'VAT - Uganda',
                    'tax_type': 'VAT',
                    'rate': Decimal('18.00'),
                    'effective_from': date(2024, 1, 1),
                    'effective_to': None,
                    'is_active': True,
                    'applies_to_fees': False,
                    'applies_to_services': True,
                    'description': 'Value Added Tax in Uganda',
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
        
        # Kenya tax rates
        elif country == 'KE':
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
                    'description': 'Value Added Tax in Kenya',
                },
            ]
        
        # Generic/default rates
        else:
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
                    'description': 'Standard Value Added Tax',
                },
            ]
    
    # =============================================================================
    # UNITS OF MEASURE
    # =============================================================================
    
    @classmethod
    def get_units_of_measure(cls):
        """
        Comprehensive units of measurement.
        
        Returns:
            list: List of unit dictionaries
        """
        return [
            # BASE UNITS - Foundation units
            {'name': 'Each', 'abbreviation': 'ea', 'symbol': 'ea', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'), 'description': 'Individual items', 'is_active': True},
            {'name': 'Kilogram', 'abbreviation': 'kg', 'symbol': 'kg', 'uom_type': 'WEIGHT', 'conversion_factor': Decimal('1.0'), 'description': 'Base unit of mass', 'is_active': True},
            {'name': 'Meter', 'abbreviation': 'm', 'symbol': 'm', 'uom_type': 'LENGTH', 'conversion_factor': Decimal('1.0'), 'description': 'Base unit of length', 'is_active': True},
            {'name': 'Liter', 'abbreviation': 'L', 'symbol': 'L', 'uom_type': 'VOLUME', 'conversion_factor': Decimal('1.0'), 'description': 'Base unit of volume', 'is_active': True},
            {'name': 'Day', 'abbreviation': 'day', 'symbol': 'd', 'uom_type': 'TIME', 'conversion_factor': Decimal('1.0'), 'description': 'Base unit of time', 'is_active': True},
            {'name': 'Square Meter', 'abbreviation': 'm²', 'symbol': 'm²', 'uom_type': 'AREA', 'conversion_factor': Decimal('1.0'), 'description': 'Base unit of area', 'is_active': True},

            # LENGTH UNITS
            {'name': 'Kilometer', 'abbreviation': 'km', 'symbol': 'km', 'uom_type': 'LENGTH', 'conversion_factor': Decimal('1000.0'), 'description': '1000 meters', 'is_active': True},
            {'name': 'Centimeter', 'abbreviation': 'cm', 'symbol': 'cm', 'uom_type': 'LENGTH', 'conversion_factor': Decimal('0.01'), 'description': '0.01 meters', 'is_active': True},
            {'name': 'Millimeter', 'abbreviation': 'mm', 'symbol': 'mm', 'uom_type': 'LENGTH', 'conversion_factor': Decimal('0.001'), 'description': '0.001 meters', 'is_active': True},
            {'name': 'Inch', 'abbreviation': 'in', 'symbol': 'in', 'uom_type': 'LENGTH', 'conversion_factor': Decimal('0.0254'), 'description': '0.0254 meters', 'is_active': True},
            {'name': 'Foot', 'abbreviation': 'ft', 'symbol': 'ft', 'uom_type': 'LENGTH', 'conversion_factor': Decimal('0.3048'), 'description': '0.3048 meters', 'is_active': True},
            {'name': 'Yard', 'abbreviation': 'yd', 'symbol': 'yd', 'uom_type': 'LENGTH', 'conversion_factor': Decimal('0.9144'), 'description': '0.9144 meters', 'is_active': True},

            # WEIGHT UNITS
            {'name': 'Gram', 'abbreviation': 'g', 'symbol': 'g', 'uom_type': 'WEIGHT', 'conversion_factor': Decimal('0.001'), 'description': '0.001 kilograms', 'is_active': True},
            {'name': 'Milligram', 'abbreviation': 'mg', 'symbol': 'mg', 'uom_type': 'WEIGHT', 'conversion_factor': Decimal('0.000001'), 'description': '0.000001 kilograms', 'is_active': True},
            {'name': 'Ton', 'abbreviation': 't', 'symbol': 't', 'uom_type': 'WEIGHT', 'conversion_factor': Decimal('1000.0'), 'description': '1000 kilograms', 'is_active': True},
            {'name': 'Pound', 'abbreviation': 'lb', 'symbol': 'lb', 'uom_type': 'WEIGHT', 'conversion_factor': Decimal('0.453592'), 'description': '0.453592 kilograms', 'is_active': True},
            {'name': 'Ounce', 'abbreviation': 'oz', 'symbol': 'oz', 'uom_type': 'WEIGHT', 'conversion_factor': Decimal('0.028350'), 'description': '0.028350 kilograms', 'is_active': True},

            # VOLUME UNITS
            {'name': 'Milliliter', 'abbreviation': 'mL', 'symbol': 'mL', 'uom_type': 'VOLUME', 'conversion_factor': Decimal('0.001'), 'description': '0.001 liters', 'is_active': True},
            {'name': 'US Gallon', 'abbreviation': 'gal', 'symbol': 'gal', 'uom_type': 'VOLUME', 'conversion_factor': Decimal('3.78541'), 'description': '3.78541 liters', 'is_active': True},
            {'name': 'Cup', 'abbreviation': 'cup', 'symbol': 'c', 'uom_type': 'VOLUME', 'conversion_factor': Decimal('0.236588'), 'description': '0.236588 liters', 'is_active': True},
            {'name': 'Tablespoon', 'abbreviation': 'tbsp', 'symbol': 'tbsp', 'uom_type': 'VOLUME', 'conversion_factor': Decimal('0.0147868'), 'description': '0.0147868 liters', 'is_active': True},
            {'name': 'Teaspoon', 'abbreviation': 'tsp', 'symbol': 'tsp', 'uom_type': 'VOLUME', 'conversion_factor': Decimal('0.00492892'), 'description': '0.00492892 liters', 'is_active': True},

            # TIME UNITS
            {'name': 'Second', 'abbreviation': 's', 'symbol': 's', 'uom_type': 'TIME', 'conversion_factor': Decimal('0.000012'), 'description': 'Fraction of day (1/86400)', 'is_active': True},
            {'name': 'Minute', 'abbreviation': 'min', 'symbol': 'min', 'uom_type': 'TIME', 'conversion_factor': Decimal('0.000694'), 'description': 'Fraction of day (1/1440)', 'is_active': True},
            {'name': 'Hour', 'abbreviation': 'hr', 'symbol': 'h', 'uom_type': 'TIME', 'conversion_factor': Decimal('0.041667'), 'description': 'Fraction of day (1/24)', 'is_active': True},
            {'name': 'Week', 'abbreviation': 'wk', 'symbol': 'wk', 'uom_type': 'TIME', 'conversion_factor': Decimal('7.0'), 'description': '7 days', 'is_active': True},
            {'name': 'Month', 'abbreviation': 'mo', 'symbol': 'mo', 'uom_type': 'TIME', 'conversion_factor': Decimal('30.44'), 'description': '30.44 days average', 'is_active': True},
            {'name': 'Year', 'abbreviation': 'yr', 'symbol': 'yr', 'uom_type': 'TIME', 'conversion_factor': Decimal('365.24'), 'description': '365.24 days', 'is_active': True},

            # AREA UNITS
            {'name': 'Square Centimeter', 'abbreviation': 'cm²', 'symbol': 'cm²', 'uom_type': 'AREA', 'conversion_factor': Decimal('0.0001'), 'description': '0.0001 square meters', 'is_active': True},
            {'name': 'Square Foot', 'abbreviation': 'sq ft', 'symbol': 'ft²', 'uom_type': 'AREA', 'conversion_factor': Decimal('0.092903'), 'description': '0.092903 square meters', 'is_active': True},
            {'name': 'Acre', 'abbreviation': 'ac', 'symbol': 'ac', 'uom_type': 'AREA', 'conversion_factor': Decimal('4046.86'), 'description': '4046.86 square meters', 'is_active': True},
            {'name': 'Hectare', 'abbreviation': 'ha', 'symbol': 'ha', 'uom_type': 'AREA', 'conversion_factor': Decimal('10000.0'), 'description': '10000 square meters', 'is_active': True},

            # QUANTITY UNITS - Enhanced for school inventory
            {'name': 'Piece', 'abbreviation': 'pc', 'symbol': 'pc', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'), 'description': 'Single item', 'is_active': True},
            {'name': 'Dozen', 'abbreviation': 'doz', 'symbol': 'dz', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('12.0'), 'description': '12 units', 'is_active': True},
            {'name': 'Pair', 'abbreviation': 'pr', 'symbol': 'pr', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('2.0'), 'description': '2 units', 'is_active': True},
            {'name': 'Set', 'abbreviation': 'set', 'symbol': 'set', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'), 'description': 'Complete set', 'is_active': True},
            {'name': 'Pack', 'abbreviation': 'pack', 'symbol': 'pk', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'), 'description': 'Package of items', 'is_active': True},
            {'name': 'Packet', 'abbreviation': 'pkt', 'symbol': 'pkt', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'), 'description': 'Packet of items', 'is_active': True},
            {'name': 'Box', 'abbreviation': 'box', 'symbol': 'box', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'), 'description': 'Box of items', 'is_active': True},
            {'name': 'Carton', 'abbreviation': 'ctn', 'symbol': 'ctn', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'), 'description': 'Carton container', 'is_active': True},
            {'name': 'Crate', 'abbreviation': 'crt', 'symbol': 'crt', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'), 'description': 'Crate container', 'is_active': True},
            {'name': 'Bundle', 'abbreviation': 'bundle', 'symbol': 'bndl', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'), 'description': 'Bundle of items', 'is_active': True},
            {'name': 'Roll', 'abbreviation': 'roll', 'symbol': 'roll', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'), 'description': 'Roll of material', 'is_active': True},
            {'name': 'Sheet', 'abbreviation': 'sheet', 'symbol': 'sht', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'), 'description': 'Single sheet', 'is_active': True},
            {'name': 'Ream', 'abbreviation': 'ream', 'symbol': 'rm', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('500.0'), 'description': '500 sheets', 'is_active': True},
            {'name': 'Book', 'abbreviation': 'book', 'symbol': 'bk', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'), 'description': 'Single book', 'is_active': True},
            {'name': 'Bottle', 'abbreviation': 'bottle', 'symbol': 'btl', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'), 'description': 'Bottle container', 'is_active': True},
            {'name': 'Can', 'abbreviation': 'can', 'symbol': 'can', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'), 'description': 'Can or tin', 'is_active': True},
            {'name': 'Bag', 'abbreviation': 'bag', 'symbol': 'bag', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'), 'description': 'Bag or sack', 'is_active': True},
            {'name': 'Sack', 'abbreviation': 'sack', 'symbol': 'sack', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'), 'description': 'Large sack', 'is_active': True},
            {'name': 'Tube', 'abbreviation': 'tube', 'symbol': 'tube', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'), 'description': 'Tube container', 'is_active': True},
            {'name': 'Jar', 'abbreviation': 'jar', 'symbol': 'jar', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'), 'description': 'Jar container', 'is_active': True},
            {'name': 'Drum', 'abbreviation': 'drum', 'symbol': 'drum', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'), 'description': 'Large drum', 'is_active': True},
            {'name': 'Barrel', 'abbreviation': 'bbl', 'symbol': 'bbl', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'), 'description': 'Barrel container', 'is_active': True},

            # SCHOOL-SPECIFIC UNITS
            {'name': 'Classroom Set', 'abbreviation': 'cls-set', 'symbol': 'cls', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('30.0'), 'description': 'Classroom quantity (30)', 'is_active': True},
            {'name': 'Student Pack', 'abbreviation': 'std-pk', 'symbol': 'sp', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'), 'description': 'Student package', 'is_active': True},
            {'name': 'Teacher Pack', 'abbreviation': 'tcr-pk', 'symbol': 'tp', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'), 'description': 'Teacher package', 'is_active': True},
            {'name': 'Class Bundle', 'abbreviation': 'cls-bndl', 'symbol': 'cb', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('40.0'), 'description': 'Large class (40)', 'is_active': True},

            # OTHER UNITS
            {'name': 'Percent', 'abbreviation': '%', 'symbol': '%', 'uom_type': 'OTHER', 'conversion_factor': Decimal('0.01'), 'description': 'One hundredth', 'is_active': True},
            {'name': 'Degree Celsius', 'abbreviation': '°C', 'symbol': '°C', 'uom_type': 'OTHER', 'conversion_factor': Decimal('1.0'), 'description': 'Temperature unit', 'is_active': True},
            {'name': 'Degree Fahrenheit', 'abbreviation': '°F', 'symbol': '°F', 'uom_type': 'OTHER', 'conversion_factor': Decimal('1.0'), 'description': 'Temperature unit', 'is_active': True},
        ]
    
    # =========================================================================
    # COMPLETE INITIALIZATION CONFIG
    # =========================================================================
    
    @classmethod
    def get_init_config(cls, school):
        """Get complete initialization configuration"""
        complexity = cls.determine_complexity(school)
        
        return {
            'school': school,
            'complexity': complexity,
            
            # ⭐ ADD THIS LINE - Account Types (must be created BEFORE accounts)
            'account_types': cls.get_account_types(),
            
            # Existing configurations
            'chart_of_accounts': cls.get_chart_of_accounts(school),
            'expense_categories': cls.get_expense_categories(),
            'journals': cls.get_journals(),
            'departments': cls.get_departments(school),
            'designations': cls.get_designations(school),
            'display_groups': cls.get_display_groups(),
            'fee_categories': cls.get_fee_categories(school),
            'payment_methods': cls.get_payment_methods(),
            'tax_rates': cls.get_tax_rates(school),
            'units_of_measure': cls.get_units_of_measure(),
            'financial_settings': cls.get_financial_settings_defaults(school),
            'account_mappings': cls.get_account_mappings_config(),
            'needs_boarding': school.boarding_type in ['BOARDING', 'MIXED'],
        }