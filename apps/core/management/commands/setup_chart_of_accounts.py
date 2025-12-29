# core/management/commands/setup_chart_of_accounts.py

from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import FinancialSettings
from finance.models import Account, AccountType
from decimal import Decimal


class Command(BaseCommand):
    help = 'Setup complete chart of accounts and link to FinancialSettings'
    
    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING('Setting up Chart of Accounts...'))
        
        with transaction.atomic():
            # Step 1: Create Account Types
            self.stdout.write('Creating Account Types...')
            asset_type = self.create_account_type('ASSET', 'Asset', 'ASSET', '1')
            liability_type = self.create_account_type('LIABILITY', 'Liability', 'LIABILITY', '2')
            equity_type = self.create_account_type('EQUITY', 'Equity', 'EQUITY', '3')
            revenue_type = self.create_account_type('REVENUE', 'Revenue', 'REVENUE', '4')
            expense_type = self.create_account_type('EXPENSE', 'Expense', 'EXPENSE', '6')
            
            # Step 2: Create Accounts
            self.stdout.write('Creating Accounts...')
            
            # ASSETS (1000-1999)
            cash_account = self.create_account('1000', 'Cash on Hand', asset_type, is_cash_account=True)
            undeposited_funds = self.create_account('1005', 'Undeposited Funds', asset_type)
            bank_account = self.create_account('1010', 'Main Bank Account', asset_type, 
                                               is_bank_account=True, bank_account_type='CURRENT')
            mobile_money = self.create_account('1020', 'Mobile Money Account', asset_type, 
                                               is_mobile_money_account=True)
            receivable_account = self.create_account('1200', 'Accounts Receivable - Students', asset_type,
                                                     is_receivable_account=True, receivable_type='STUDENT')
            
            # LIABILITIES (2000-2999)
            student_deposits = self.create_account('2100', 'Student Deposits', liability_type,
                                                   is_liability_account=True, liability_type='STUDENT_DEPOSITS')
            refunds_payable = self.create_account('2110', 'Refunds Payable', liability_type,
                                                  is_liability_account=True)
            unearned_revenue = self.create_account('2120', 'Unearned Revenue', liability_type,
                                                   is_liability_account=True)
            
            # EQUITY (3000-3999)
            retained_earnings = self.create_account('3900', 'Retained Earnings', equity_type,
                                                    is_equity_account=True, equity_type='RETAINED_EARNINGS')
            
            # REVENUE (4000-4999)
            revenue_account = self.create_account('4100', 'Student Fees Revenue', revenue_type,
                                                  is_revenue_account=True, revenue_type='TUITION')
            tuition_revenue = self.create_account('4110', 'Tuition Revenue', revenue_type,
                                                  is_revenue_account=True, revenue_type='TUITION')
            boarding_revenue = self.create_account('4120', 'Boarding Revenue', revenue_type,
                                                   is_revenue_account=True, revenue_type='BOARDING')
            transport_revenue = self.create_account('4130', 'Transport Revenue', revenue_type,
                                                    is_revenue_account=True, revenue_type='TRANSPORT')
            other_fees_revenue = self.create_account('4190', 'Other Fees Revenue', revenue_type,
                                                     is_revenue_account=True, revenue_type='OTHER_FEES')
            revenue_contra = self.create_account('4900', 'Revenue Reversals (Contra)', revenue_type,
                                                 is_revenue_account=True)
            
            # EXPENSES (6000-6999)
            processing_fee = self.create_account('6300', 'Payment Processing Fees', expense_type,
                                                 is_expense_account=True, expense_type='BANK_CHARGES')
            bank_charges = self.create_account('6310', 'Bank Charges', expense_type,
                                               is_expense_account=True, expense_type='BANK_CHARGES')
            bad_debt = self.create_account('6400', 'Bad Debt Expense', expense_type,
                                           is_expense_account=True, expense_type='BAD_DEBT')
            scholarship_expense = self.create_account('6500', 'Scholarship Expense', expense_type,
                                                      is_expense_account=True, expense_type='SCHOLARSHIP')
            discount_expense = self.create_account('6510', 'Fee Discount Expense', expense_type,
                                                   is_expense_account=True, expense_type='FEE_DISCOUNT')
            
            # Step 3: Link to FinancialSettings
            self.stdout.write('Linking accounts to FinancialSettings...')
            settings, created = FinancialSettings.objects.get_or_create(pk=1)
            
            settings.default_revenue_account = revenue_account
            settings.tuition_revenue_account = tuition_revenue
            settings.boarding_revenue_account = boarding_revenue
            settings.transport_revenue_account = transport_revenue
            settings.other_fees_revenue_account = other_fees_revenue
            
            settings.default_receivable_account = receivable_account
            settings.default_cash_account = cash_account
            settings.default_bank_account = bank_account
            settings.mobile_money_clearing_account = mobile_money
            settings.undeposited_funds_account = undeposited_funds
            
            settings.payment_processing_fee_account = processing_fee
            settings.bank_charges_account = bank_charges
            settings.bad_debt_expense_account = bad_debt
            settings.scholarship_expense_account = scholarship_expense
            settings.discount_expense_account = discount_expense
            
            settings.student_deposits_account = student_deposits
            settings.refunds_payable_account = refunds_payable
            settings.unearned_revenue_account = unearned_revenue
            
            settings.revenue_contra_account = revenue_contra
            
            settings.save()
            
            self.stdout.write(self.style.SUCCESS('✅ Chart of Accounts setup complete!'))
            self.stdout.write(self.style.SUCCESS(f'   - Created 5 Account Types'))
            self.stdout.write(self.style.SUCCESS(f'   - Created {Account.objects.count()} Accounts'))
            self.stdout.write(self.style.SUCCESS(f'   - Linked all default accounts to FinancialSettings'))
    
    def create_account_type(self, code, name, account_type, prefix):
        """Create or get account type"""
        obj, created = AccountType.objects.get_or_create(
            code=code,
            defaults={
                'name': name,
                'account_type': account_type,
                'number_prefix': prefix,
                'is_active': True
            }
        )
        if created:
            self.stdout.write(f'  ✓ Created Account Type: {name}')
        return obj
    
    def create_account(self, account_number, name, account_type, **kwargs):
        """Create or get account"""
        obj, created = Account.objects.get_or_create(
            account_number=account_number,
            defaults={
                'name': name,
                'account_type': account_type,
                'current_balance': Decimal('0.00'),
                'opening_balance': Decimal('0.00'),
                'is_active': True,
                **kwargs
            }
        )
        if created:
            self.stdout.write(f'  ✓ Created Account: {account_number} - {name}')
        return obj