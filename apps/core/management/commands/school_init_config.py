# school_settings/management/commands/school_init_config.py
"""
School Initialization Configuration
===================================

This file contains all the configuration data for school initialization.
It centralizes all default data to eliminate redundancy across commands.

Enhanced to support all school types from the database registry:
- KINDERGARTEN - Pure early childhood education
- KINDERGARTEN_PRIMARY - Combined kindergarten and primary
- PRIMARY - Primary education only
- SECONDARY - Secondary education only
- PRIMARY_SECONDARY - Combined primary and secondary
- KINDERGARTEN_PRIMARY_SECONDARY - Complete K-12 system
- TERTIARY, VOCATIONAL, TECHNICAL, SPECIAL_NEEDS
- INTERNATIONAL, MONTESSORI, WALDORF
- Plus boarding variations
"""

from decimal import Decimal
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

class SchoolInitConfig:
    """Configuration class for school initialization data"""

    @classmethod
    def get_school_type_from_registry(cls, school_instance):
        """
        Determine the appropriate HR configuration based on School model instance
        """
        if not school_instance:
            return 'kindergarten_primary'  # fallback
        
        school_type = school_instance.school_type
        boarding_type = getattr(school_instance, 'boarding_type', 'DAY')
        
        # Map database registry school types to HR configuration types
        type_mapping = {
            # Early Childhood
            'KINDERGARTEN': 'kindergarten',
            'KINDERGARTEN_PRIMARY': 'kindergarten_primary',
            
            # Primary
            'PRIMARY': 'primary',
            
            # Secondary
            'SECONDARY': 'secondary',
            'HIGH_SCHOOL_GENERAL': 'secondary',
            'HIGH_SCHOOL_O_LEVEL': 'secondary',
            'HIGH_SCHOOL_A_LEVEL': 'secondary', 
            'HIGH_SCHOOL_O_A_LEVEL': 'secondary',
            
            # Combined
            'PRIMARY_SECONDARY': 'primary_secondary',
            'KINDERGARTEN_PRIMARY_SECONDARY': 'kindergarten_primary_secondary',
            
            # Tertiary
            'COLLEGE': 'tertiary',
            'UNIVERSITY': 'tertiary',
            
            # Specialized
            'VOCATIONAL': 'vocational',
            'TECHNICAL': 'technical',
            'SPECIAL_NEEDS': 'special_needs',
            
            # International/Alternative
            'INTERNATIONAL': 'international',
            'MONTESSORI': 'montessori',
            'WALDORF': 'waldorf',
        }
        
        base_type = type_mapping.get(school_type, 'primary')
        
        # Add boarding modifier if applicable
        if boarding_type in ['BOARDING', 'MIXED']:
            return f"{base_type}_boarding"
        
        return base_type
    
    @classmethod
    def create_financial_settings(cls, school_instance=None, country='UG'):
        """Create default FinancialSettings instance - UPDATED WITH SSP"""
        try:
            from django.apps import apps
            
            # Get the model dynamically to avoid circular imports
            FinancialSettings = apps.get_model('school_settings', 'FinancialSettings')
            
            # Determine which database to use
            db_name = getattr(school_instance, 'db_name', 'default') if school_instance else 'default'
            
            # CRITICAL: Set the database context for the router
            from database_registry.routers import set_current_db
            set_current_db(db_name)
            
            # CRITICAL: Ensure the database is loaded by the database_loader
            from database_registry.database_loader import ensure_database_loaded
            if not ensure_database_loaded(db_name):
                raise Exception(f"Could not load database {db_name}")
            
            # Check if already exists - USING CORRECT DATABASE
            existing_settings = FinancialSettings.objects.using(db_name).first()
            if existing_settings:
                logger.info(f"FinancialSettings already exists in {db_name}, returning existing instance")
                return existing_settings
            
            # Determine currency based on country - UPDATED WITH SSP
            currency_map = {
                'UG': 'UGX',  # Uganda Shilling
                'KE': 'KES',  # Kenyan Shilling
                'TZ': 'TZS',  # Tanzanian Shilling
                'RW': 'RWF',  # Rwandan Franc
                'SS': 'SSP',  # South Sudanese Pound
                'NG': 'NGN',  # Nigerian Naira
                'GH': 'GHS',  # Ghanaian Cedi
                'ZA': 'ZAR',  # South African Rand
                'US': 'USD',  # US Dollar
                'GB': 'GBP',  # British Pound
            }
            
            school_currency = currency_map.get(country, 'UGX')
            
            # Create with comprehensive defaults - USING CORRECT DATABASE
            settings = FinancialSettings.objects.using(db_name).create(
                school_currency=school_currency,
                currency_position='BEFORE',
                decimal_places=2 if school_currency in ['SSP', 'USD', 'GBP', 'ZAR'] else 0,
                use_thousand_separator=True,
                default_payment_terms_days=30,
                late_fee_enabled=False,
                late_fee_percentage=Decimal('5.00'),
                grace_period_days=7,
                minimum_payment_amount=Decimal('10.00') if school_currency in ['SSP', 'USD', 'GBP'] else Decimal('1000.00'),
                auto_apply_scholarships=True,
                scholarship_approval_required=True,
                auto_apply_discounts=False,
                discount_approval_required=True,
                expense_approval_required=True,
                expense_approval_limit=Decimal('1000.00') if school_currency in ['SSP', 'USD', 'GBP'] else Decimal('100000.00'),
                send_invoice_emails=True,
                send_payment_confirmations=True,
                send_overdue_reminders=True,
            )
            
            logger.info(f"Created FinancialSettings with currency {school_currency} on database {db_name}")
            return settings
            
        except Exception as e:
            logger.error(f"Error creating FinancialSettings for {db_name}: {e}")
            raise

    @classmethod
    def create_school_configuration(cls, school_instance=None):
        """Create default SchoolConfiguration instance"""
        try:
            from school_settings.models import SchoolConfiguration
            
            # Determine which database to use
            db_name = getattr(school_instance, 'db_name', 'default') if school_instance else 'default'
            
            # Check if already exists - USING CORRECT DATABASE
            if SchoolConfiguration.objects.using(db_name).exists():
                logger.info("SchoolConfiguration already exists, skipping creation")
                return SchoolConfiguration.objects.using(db_name).first()
            
            # Determine configuration based on school type
            if school_instance:
                school_type = cls.get_school_type_from_registry(school_instance)
            else:
                school_type = 'kindergarten_primary'  # Default
            
            # Set term system based on school type
            if school_type in ['tertiary', 'university', 'college']:
                term_system = 'semester'
                periods_per_year = 2
            elif school_type in ['vocational', 'technical']:
                term_system = 'module'
                periods_per_year = 6
            else:
                term_system = 'term'
                periods_per_year = 3
            
            # Create using correct database
            config = SchoolConfiguration.objects.using(db_name).create(
                term_system=term_system,
                periods_per_year=periods_per_year,
                period_naming_convention='numeric',
                academic_year_type='northern',  
                regional_season_type='temperate',
                academic_year_start_month=1, 
                academic_year_start_day=1,
                auto_create_breaks=True,
                minimum_break_days=1,
                default_period_duration_weeks=12,
                default_payment_due_days=30,
                allow_partial_payments=True,
                enable_automatic_reminders=True,
                enable_email_notifications=True,
                enable_sms=False,
            )
            
            logger.info(f"Created SchoolConfiguration with {term_system} system ({periods_per_year} periods)")
            return config
            
        except Exception as e:
            logger.error(f"Error creating SchoolConfiguration: {e}")
            raise
    
    @classmethod
    def get_payment_methods(cls):
        """
        Enhanced payment methods with automatic account mapping for school operations.
        Now includes account mapping, display settings, and smart defaults.
        """
        return [
            {
                'name': 'Cash Payment',
                'code': 'CASH',
                'description': 'Physical cash payments made in person at school office',
                'payment_type': 'CASH',
                'is_active': True,
                'requires_approval': False,
                'requires_verification': True,
                'has_processing_fee': False,
                'auto_create_journal_entry': True,
                'processing_time_hours': 0,  # Instant
                'display_order': 1,
                'icon': 'fa-money-bill-wave',
                'color': '#28a745',
                # Account mapping
                'account_mapping': {
                    'type': 'cash_account',
                    'fallback_name': 'Cash in Hand',
                    'search_criteria': {'is_cash_account': True}
                }
            },
            {
                'name': 'Bank Transfer',
                'code': 'BANK_TRANSFER',
                'description': 'Electronic bank transfer to school account',
                'payment_type': 'BANK_TRANSFER',
                'is_active': True,
                'requires_approval': True,
                'requires_verification': True,
                'has_processing_fee': False,
                'auto_create_journal_entry': True,
                'processing_time_hours': 24,  # 1 day for verification
                'display_order': 2,
                'icon': 'fa-university',
                'color': '#007bff',
                # Account mapping
                'account_mapping': {
                    'type': 'bank_account',
                    'fallback_name': 'Bank Account - Main',
                    'search_criteria': {'is_bank_account': True},
                    'advanced_rules': {
                        'rules': [
                            {
                                'conditions': {'bank_name_contains': 'Stanbic'},
                                'account_name': 'Bank Account - Stanbic'
                            },
                            {
                                'conditions': {'bank_name_contains': 'Centenary'},
                                'account_name': 'Bank Account - Centenary'
                            }
                        ]
                    }
                }
            },
            {
                'name': 'MTN Mobile Money',
                'code': 'MTN_MOBILE',
                'description': 'MTN Mobile Money payments via *165# or MoMo app',
                'payment_type': 'MOBILE_PAYMENT',
                'is_active': True,
                'requires_approval': False,
                'requires_verification': True,
                'has_processing_fee': True,
                'fee_percentage': Decimal('1.5'),
                'fee_fixed_amount': Decimal('500.00'),  # UGX 500 minimum fee
                'auto_create_journal_entry': True,
                'processing_time_hours': 1,  # Near instant
                'display_order': 3,
                'icon': 'fa-mobile-alt',
                'color': '#ffcc00',
                # Account mapping
                'account_mapping': {
                    'type': 'mobile_money_account',
                    'fallback_name': 'Mobile Money Account - MTN',
                    'search_criteria': {
                        'is_mobile_money_account': True,
                        'mobile_money_provider': 'MTN'
                    }
                }
            },
            {
                'name': 'Airtel Money',
                'code': 'AIRTEL_MOBILE',
                'description': 'Airtel Money payments via *185# or Airtel app',
                'payment_type': 'MOBILE_PAYMENT',
                'is_active': True,
                'requires_approval': False,
                'requires_verification': True,
                'has_processing_fee': True,
                'fee_percentage': Decimal('1.5'),
                'fee_fixed_amount': Decimal('500.00'),  # UGX 500 minimum fee
                'auto_create_journal_entry': True,
                'processing_time_hours': 1,
                'display_order': 4,
                'icon': 'fa-mobile-alt',
                'color': '#ff6b35',
                # Account mapping
                'account_mapping': {
                    'type': 'mobile_money_account',
                    'fallback_name': 'Mobile Money Account - Airtel',
                    'search_criteria': {
                        'is_mobile_money_account': True,
                        'mobile_money_provider': 'AIRTEL'
                    }
                }
            },
            {
                'name': 'Bank Check',
                'code': 'CHECK',
                'description': 'Bank check payments (requires physical verification)',
                'payment_type': 'CHECK',
                'is_active': True,
                'requires_approval': True,
                'requires_verification': True,
                'has_processing_fee': False,
                'auto_create_journal_entry': False,  # Manual verification required
                'processing_time_hours': 72,  # 3 days for check clearance
                'display_order': 5,
                'icon': 'fa-money-check',
                'color': '#6c757d',
                # Account mapping
                'account_mapping': {
                    'type': 'bank_account',
                    'fallback_name': 'Bank Account - Main',
                    'search_criteria': {'is_bank_account': True}
                }
            },
            {
                'name': 'Credit/Debit Card',
                'code': 'CARD',
                'description': 'Visa, MasterCard, and local debit card payments',
                'payment_type': 'CREDIT_CARD',
                'is_active': True,
                'requires_approval': False,
                'requires_verification': True,
                'has_processing_fee': True,
                'fee_percentage': Decimal('2.5'),
                'fee_fixed_amount': Decimal('1000.00'),  # UGX 1000 minimum fee
                'auto_create_journal_entry': True,
                'processing_time_hours': 48,  # 2 days for card processing
                'display_order': 6,
                'icon': 'fa-credit-card',
                'color': '#17a2b8',
                # Account mapping
                'account_mapping': {
                    'type': 'bank_account',
                    'fallback_name': 'Bank Account - Card Processing',
                    'search_criteria': {'is_bank_account': True},
                    'preferred_account_name': 'Bank Account - Card Processing'
                }
            },
            {
                'name': 'Online Banking',
                'code': 'ONLINE_BANK',
                'description': 'Direct online banking transfers and payments',
                'payment_type': 'ONLINE',
                'is_active': True,
                'requires_approval': False,
                'requires_verification': True,
                'has_processing_fee': False,
                'auto_create_journal_entry': True,
                'processing_time_hours': 4,  # Few hours for online verification
                'display_order': 7,
                'icon': 'fa-laptop',
                'color': '#6f42c1',
                # Account mapping
                'account_mapping': {
                    'type': 'bank_account',
                    'fallback_name': 'Bank Account - Main',
                    'search_criteria': {'is_bank_account': True}
                }
            },
            {
                'name': 'M-Pesa (Safaricom)',
                'code': 'MPESA',
                'description': 'M-Pesa mobile money payments',
                'payment_type': 'MOBILE_PAYMENT',
                'is_active': False,  # Disabled by default (not common in Uganda)
                'requires_approval': False,
                'requires_verification': True,
                'has_processing_fee': True,
                'fee_percentage': Decimal('1.0'),
                'auto_create_journal_entry': True,
                'processing_time_hours': 1,
                'display_order': 8,
                'icon': 'fa-mobile-alt',
                'color': '#00d4aa',
                # Account mapping
                'account_mapping': {
                    'type': 'mobile_money_account',
                    'fallback_name': 'Mobile Money Account - M-Pesa',
                    'search_criteria': {
                        'is_mobile_money_account': True,
                        'mobile_money_provider': 'SAFARICOM'
                    }
                }
            }
        ]
    
    @classmethod
    def get_tax_rates(cls, country='UG'):
        """Tax rates by country - FIXED to use decimal rates (0.18 for 18%)"""
        tax_rates_by_country = {
            'UG': [  # Uganda
                {
                    'name': 'VAT',
                    'code': 'VAT_UG',
                    'description': 'Value Added Tax - Uganda',
                    'rate': Decimal('0.18'),  # FIXED: 18% as decimal (0.18)
                    'tax_type': 'VAT',
                    'country': 'UG',
                    'is_active': True,
                },
                {
                    'name': 'Withholding Tax',
                    'code': 'WHT_UG',
                    'description': 'Withholding Tax - Uganda',
                    'rate': Decimal('0.06'),  # FIXED: 6% as decimal (0.06)
                    'tax_type': 'WITHHOLDING',
                    'country': 'UG',
                    'is_active': True,
                },
                {
                    'name': 'Service Tax',
                    'code': 'ST_UG',
                    'description': 'Service Tax - Uganda',
                    'rate': Decimal('0.12'),  # FIXED: 12% as decimal (0.12)
                    'tax_type': 'SERVICE',
                    'country': 'UG',
                    'is_active': True,
                },
            ],
            'KE': [  # Kenya
                {
                    'name': 'VAT',
                    'code': 'VAT_KE',
                    'description': 'Value Added Tax - Kenya',
                    'rate': Decimal('0.16'),  # FIXED: 16% as decimal (0.16)
                    'tax_type': 'VAT',
                    'country': 'KE',
                    'is_active': True,
                },
                {
                    'name': 'Withholding Tax',
                    'code': 'WHT_KE',
                    'description': 'Withholding Tax - Kenya',
                    'rate': Decimal('0.05'),  # FIXED: 5% as decimal (0.05)
                    'tax_type': 'WITHHOLDING',
                    'country': 'KE',
                    'is_active': True,
                },
            ],
            'TZ': [  # Tanzania
                {
                    'name': 'VAT',
                    'code': 'VAT_TZ',
                    'description': 'Value Added Tax - Tanzania',
                    'rate': Decimal('0.18'),  # FIXED: 18% as decimal (0.18)
                    'tax_type': 'VAT',
                    'country': 'TZ',
                    'is_active': True,
                },
                {
                    'name': 'Service Tax',
                    'code': 'ST_TZ',
                    'description': 'Service Tax - Tanzania',
                    'rate': Decimal('0.07'),  # FIXED: 7% as decimal (0.07)
                    'tax_type': 'SALES',
                    'country': 'TZ',
                    'is_active': True,
                },
            ],
            'RW': [  # Rwanda
                {
                    'name': 'VAT',
                    'code': 'VAT_RW',
                    'description': 'Value Added Tax - Rwanda',
                    'rate': Decimal('0.18'),  # FIXED: 18% as decimal (0.18)
                    'tax_type': 'VAT',
                    'country': 'RW',
                    'is_active': True,
                },
            ],
        }
        
        return tax_rates_by_country.get(country, [
            {
                'name': 'No Tax',
                'code': 'NO_TAX',
                'description': 'No tax applied',
                'rate': Decimal('0.0'),
                'tax_type': 'OTHER',
                'is_active': True,
            }
        ])
    
    @classmethod
    def get_academic_levels(cls, level_type='primary', school_instance=None):
        """Academic levels by school type"""
        levels = {
            'kindergarten': [
                {'name': 'Baby Class', 'code': 'BABY', 'order': 1, 'min_age': 2, 'max_age': 4, 'has_sections': False, 'description': 'Early childhood development'},
                {'name': 'Middle Class', 'code': 'MID', 'order': 2, 'min_age': 3, 'max_age': 5, 'has_sections': False, 'description': 'Pre-primary development'},
                {'name': 'Top Class', 'code': 'TOP', 'order': 3, 'min_age': 4, 'max_age': 6, 'has_sections': False, 'description': 'Pre-primary advanced'},
            ],
            'kindergarten_primary': [
                # Kindergarten levels
                {'name': 'Baby Class', 'code': 'BABY', 'order': 1, 'min_age': 2, 'max_age': 4, 'has_sections': False, 'description': 'Early childhood development'},
                {'name': 'Middle Class', 'code': 'MID', 'order': 2, 'min_age': 3, 'max_age': 5, 'has_sections': False, 'description': 'Pre-primary development'},
                {'name': 'Top Class', 'code': 'TOP', 'order': 3, 'min_age': 4, 'max_age': 6, 'has_sections': False, 'description': 'Pre-primary advanced'},
                # Primary levels
                {'name': 'Primary 1', 'code': 'P1', 'order': 4, 'min_age': 6, 'max_age': 8, 'has_sections': True, 'description': 'Foundation literacy and numeracy'},
                {'name': 'Primary 2', 'code': 'P2', 'order': 5, 'min_age': 7, 'max_age': 9, 'has_sections': True, 'description': 'Basic skills development'},
                {'name': 'Primary 3', 'code': 'P3', 'order': 6, 'min_age': 8, 'max_age': 10, 'has_sections': True, 'description': 'Intermediate primary'},
                {'name': 'Primary 4', 'code': 'P4', 'order': 7, 'min_age': 9, 'max_age': 11, 'has_sections': True, 'description': 'Upper primary foundation'},
                {'name': 'Primary 5', 'code': 'P5', 'order': 8, 'min_age': 10, 'max_age': 12, 'has_sections': True, 'description': 'Upper primary development'},
                {'name': 'Primary 6', 'code': 'P6', 'order': 9, 'min_age': 11, 'max_age': 13, 'has_sections': True, 'description': 'Upper primary advanced'},
                {'name': 'Primary 7', 'code': 'P7', 'order': 10, 'min_age': 12, 'max_age': 14, 'has_sections': True, 'description': 'Primary completion level'},
            ],
            'primary': [
                {'name': 'Primary 1', 'code': 'P1', 'order': 1, 'min_age': 6, 'max_age': 8, 'has_sections': True, 'description': 'Foundation literacy and numeracy'},
                {'name': 'Primary 2', 'code': 'P2', 'order': 2, 'min_age': 7, 'max_age': 9, 'has_sections': True, 'description': 'Basic skills development'},
                {'name': 'Primary 3', 'code': 'P3', 'order': 3, 'min_age': 8, 'max_age': 10, 'has_sections': True, 'description': 'Intermediate primary'},
                {'name': 'Primary 4', 'code': 'P4', 'order': 4, 'min_age': 9, 'max_age': 11, 'has_sections': True, 'description': 'Upper primary foundation'},
                {'name': 'Primary 5', 'code': 'P5', 'order': 5, 'min_age': 10, 'max_age': 12, 'has_sections': True, 'description': 'Upper primary development'},
                {'name': 'Primary 6', 'code': 'P6', 'order': 6, 'min_age': 11, 'max_age': 13, 'has_sections': True, 'description': 'Upper primary advanced'},
                {'name': 'Primary 7', 'code': 'P7', 'order': 7, 'min_age': 12, 'max_age': 14, 'has_sections': True, 'description': 'Primary completion level'},
            ],
            'secondary': [
                {'name': 'Senior 1', 'code': 'S1', 'order': 1, 'min_age': 13, 'max_age': 15, 'has_sections': True, 'description': 'Lower secondary foundation'},
                {'name': 'Senior 2', 'code': 'S2', 'order': 2, 'min_age': 14, 'max_age': 16, 'has_sections': True, 'description': 'Lower secondary development'},
                {'name': 'Senior 3', 'code': 'S3', 'order': 3, 'min_age': 15, 'max_age': 17, 'has_sections': True, 'description': 'Lower secondary advanced'},
                {'name': 'Senior 4', 'code': 'S4', 'order': 4, 'min_age': 16, 'max_age': 18, 'has_sections': True, 'description': 'O-Level completion'},
                {'name': 'Senior 5', 'code': 'S5', 'order': 5, 'min_age': 17, 'max_age': 19, 'has_sections': True, 'description': 'A-Level foundation'},
                {'name': 'Senior 6', 'code': 'S6', 'order': 6, 'min_age': 18, 'max_age': 20, 'has_sections': True, 'description': 'A-Level completion'},
            ],
            'primary_secondary': [
                # Primary levels
                {'name': 'Primary 1', 'code': 'P1', 'order': 1, 'min_age': 6, 'max_age': 8, 'has_sections': True, 'description': 'Foundation literacy and numeracy'},
                {'name': 'Primary 2', 'code': 'P2', 'order': 2, 'min_age': 7, 'max_age': 9, 'has_sections': True, 'description': 'Basic skills development'},
                {'name': 'Primary 3', 'code': 'P3', 'order': 3, 'min_age': 8, 'max_age': 10, 'has_sections': True, 'description': 'Intermediate primary'},
                {'name': 'Primary 4', 'code': 'P4', 'order': 4, 'min_age': 9, 'max_age': 11, 'has_sections': True, 'description': 'Upper primary foundation'},
                {'name': 'Primary 5', 'code': 'P5', 'order': 5, 'min_age': 10, 'max_age': 12, 'has_sections': True, 'description': 'Upper primary development'},
                {'name': 'Primary 6', 'code': 'P6', 'order': 6, 'min_age': 11, 'max_age': 13, 'has_sections': True, 'description': 'Upper primary advanced'},
                {'name': 'Primary 7', 'code': 'P7', 'order': 7, 'min_age': 12, 'max_age': 14, 'has_sections': True, 'description': 'Primary completion level'},
                # Secondary levels
                {'name': 'Senior 1', 'code': 'S1', 'order': 8, 'min_age': 13, 'max_age': 15, 'has_sections': True, 'description': 'Lower secondary foundation'},
                {'name': 'Senior 2', 'code': 'S2', 'order': 9, 'min_age': 14, 'max_age': 16, 'has_sections': True, 'description': 'Lower secondary development'},
                {'name': 'Senior 3', 'code': 'S3', 'order': 10, 'min_age': 15, 'max_age': 17, 'has_sections': True, 'description': 'Lower secondary advanced'},
                {'name': 'Senior 4', 'code': 'S4', 'order': 11, 'min_age': 16, 'max_age': 18, 'has_sections': True, 'description': 'O-Level completion'},
                {'name': 'Senior 5', 'code': 'S5', 'order': 12, 'min_age': 17, 'max_age': 19, 'has_sections': True, 'description': 'A-Level foundation'},
                {'name': 'Senior 6', 'code': 'S6', 'order': 13, 'min_age': 18, 'max_age': 20, 'has_sections': True, 'description': 'A-Level completion'},
            ],
            'kindergarten_primary_secondary': [
                # Kindergarten levels
                {'name': 'Baby Class', 'code': 'BABY', 'order': 1, 'min_age': 2, 'max_age': 4, 'has_sections': False, 'description': 'Early childhood development'},
                {'name': 'Middle Class', 'code': 'MID', 'order': 2, 'min_age': 3, 'max_age': 5, 'has_sections': False, 'description': 'Pre-primary development'},
                {'name': 'Top Class', 'code': 'TOP', 'order': 3, 'min_age': 4, 'max_age': 6, 'has_sections': False, 'description': 'Pre-primary advanced'},
                # Primary levels
                {'name': 'Primary 1', 'code': 'P1', 'order': 4, 'min_age': 6, 'max_age': 8, 'has_sections': True, 'description': 'Foundation literacy and numeracy'},
                {'name': 'Primary 2', 'code': 'P2', 'order': 5, 'min_age': 7, 'max_age': 9, 'has_sections': True, 'description': 'Basic skills development'},
                {'name': 'Primary 3', 'code': 'P3', 'order': 6, 'min_age': 8, 'max_age': 10, 'has_sections': True, 'description': 'Intermediate primary'},
                {'name': 'Primary 4', 'code': 'P4', 'order': 7, 'min_age': 9, 'max_age': 11, 'has_sections': True, 'description': 'Upper primary foundation'},
                {'name': 'Primary 5', 'code': 'P5', 'order': 8, 'min_age': 10, 'max_age': 12, 'has_sections': True, 'description': 'Upper primary development'},
                {'name': 'Primary 6', 'code': 'P6', 'order': 9, 'min_age': 11, 'max_age': 13, 'has_sections': True, 'description': 'Upper primary advanced'},
                {'name': 'Primary 7', 'code': 'P7', 'order': 10, 'min_age': 12, 'max_age': 14, 'has_sections': True, 'description': 'Primary completion level'},
                # Secondary levels
                {'name': 'Senior 1', 'code': 'S1', 'order': 11, 'min_age': 13, 'max_age': 15, 'has_sections': True, 'description': 'Lower secondary foundation'},
                {'name': 'Senior 2', 'code': 'S2', 'order': 12, 'min_age': 14, 'max_age': 16, 'has_sections': True, 'description': 'Lower secondary development'},
                {'name': 'Senior 3', 'code': 'S3', 'order': 13, 'min_age': 15, 'max_age': 17, 'has_sections': True, 'description': 'Lower secondary advanced'},
                {'name': 'Senior 4', 'code': 'S4', 'order': 14, 'min_age': 16, 'max_age': 18, 'has_sections': True, 'description': 'O-Level completion'},
                {'name': 'Senior 5', 'code': 'S5', 'order': 15, 'min_age': 17, 'max_age': 19, 'has_sections': True, 'description': 'A-Level foundation'},
                {'name': 'Senior 6', 'code': 'S6', 'order': 16, 'min_age': 18, 'max_age': 20, 'has_sections': True, 'description': 'A-Level completion'},
            ],
            'tertiary': [
                {'name': 'Year 1', 'code': 'Y1', 'order': 1, 'min_age': 18, 'max_age': 25, 'has_sections': True, 'description': 'First year undergraduate'},
                {'name': 'Year 2', 'code': 'Y2', 'order': 2, 'min_age': 19, 'max_age': 26, 'has_sections': True, 'description': 'Second year undergraduate'},
                {'name': 'Year 3', 'code': 'Y3', 'order': 3, 'min_age': 20, 'max_age': 27, 'has_sections': True, 'description': 'Third year undergraduate'},
                {'name': 'Year 4', 'code': 'Y4', 'order': 4, 'min_age': 21, 'max_age': 28, 'has_sections': True, 'description': 'Fourth year undergraduate'},
            ],
            'vocational': [
                {'name': 'Certificate Level 1', 'code': 'CERT1', 'order': 1, 'min_age': 16, 'max_age': 30, 'has_sections': True, 'description': 'Basic vocational training'},
                {'name': 'Certificate Level 2', 'code': 'CERT2', 'order': 2, 'min_age': 17, 'max_age': 31, 'has_sections': True, 'description': 'Intermediate vocational training'},
                {'name': 'Diploma Level', 'code': 'DIPL', 'order': 3, 'min_age': 18, 'max_age': 32, 'has_sections': True, 'description': 'Advanced vocational training'},
            ],
        }
        
        return levels.get(level_type, levels['primary'])
    
    @classmethod
    def get_subjects(cls, curriculum_type='primary', school_instance=None):
        """Subjects by curriculum type"""
        subjects = {
            'kindergarten': [
                # Early childhood subjects
                {'name': 'Play-based Learning', 'code': 'PLAY', 'abbreviation': 'PLAY', 'subject_type': 'PLAY_BASED', 'is_compulsory': True, 'pass_mark': 50.0, 'description': 'Learning through play activities'},
                {'name': 'Early Literacy', 'code': 'ELIT', 'abbreviation': 'ELIT', 'subject_type': 'LITERACY', 'is_compulsory': True, 'pass_mark': 50.0, 'description': 'Foundation reading and writing'},
                {'name': 'Early Numeracy', 'code': 'ENUM', 'abbreviation': 'ENUM', 'subject_type': 'NUMERACY', 'is_compulsory': True, 'pass_mark': 50.0, 'description': 'Foundation mathematics concepts'},
                {'name': 'Creative Arts', 'code': 'CART', 'abbreviation': 'CART', 'subject_type': 'CREATIVE', 'is_compulsory': True, 'pass_mark': 50.0, 'description': 'Art, music, and creative expression'},
                {'name': 'Physical Development', 'code': 'PHDEV', 'abbreviation': 'PHDEV', 'subject_type': 'PHYSICAL', 'is_compulsory': True, 'pass_mark': 50.0, 'description': 'Motor skills and physical activity'},
                {'name': 'Social Skills', 'code': 'SOCIAL', 'abbreviation': 'SOC', 'subject_type': 'SOCIAL', 'is_compulsory': True, 'pass_mark': 50.0, 'description': 'Social interaction and emotional development'},
            ],
            'kindergarten_primary': [
                # Kindergarten subjects
                {'name': 'Play-based Learning', 'code': 'PLAY', 'abbreviation': 'PLAY', 'subject_type': 'PLAY_BASED', 'is_compulsory': True, 'pass_mark': 50.0, 'description': 'Learning through play activities'},
                {'name': 'Early Literacy', 'code': 'ELIT', 'abbreviation': 'ELIT', 'subject_type': 'LITERACY', 'is_compulsory': True, 'pass_mark': 50.0, 'description': 'Foundation reading and writing'},
                {'name': 'Early Numeracy', 'code': 'ENUM', 'abbreviation': 'ENUM', 'subject_type': 'NUMERACY', 'is_compulsory': True, 'pass_mark': 50.0, 'description': 'Foundation mathematics concepts'},
                # Primary subjects
                {'name': 'Mathematics', 'code': 'MATH', 'abbreviation': 'MATH', 'subject_type': 'MATH', 'is_compulsory': True, 'pass_mark': 50.0, 'description': 'Core mathematics curriculum'},
                {'name': 'English', 'code': 'ENG', 'abbreviation': 'ENG', 'subject_type': 'LANG_ARTS', 'is_compulsory': True, 'pass_mark': 50.0, 'description': 'English language and literature'},
                {'name': 'Science', 'code': 'SCI', 'abbreviation': 'SCI', 'subject_type': 'SCIENCES', 'is_compulsory': True, 'pass_mark': 50.0, 'description': 'General science concepts'},
                {'name': 'Social Studies', 'code': 'SST', 'abbreviation': 'SST', 'subject_type': 'SOCIAL', 'is_compulsory': True, 'pass_mark': 50.0, 'description': 'Social and cultural studies'},
                {'name': 'Religious Education', 'code': 'RE', 'abbreviation': 'RE', 'subject_type': 'RELIGIOUS', 'is_compulsory': True, 'pass_mark': 50.0, 'description': 'Religious and moral education'},
                {'name': 'Physical Education', 'code': 'PE', 'abbreviation': 'PE', 'subject_type': 'PE', 'is_compulsory': False, 'pass_mark': 50.0, 'description': 'Physical education and sports'},
            ],
            'primary': [
                # Core subjects
                {'name': 'Mathematics', 'code': 'MATH', 'abbreviation': 'MATH', 'subject_type': 'MATH', 'is_compulsory': True, 'pass_mark': 50.0, 'description': 'Core mathematics curriculum'},
                {'name': 'English', 'code': 'ENG', 'abbreviation': 'ENG', 'subject_type': 'LANG_ARTS', 'is_compulsory': True, 'pass_mark': 50.0, 'description': 'English language and literature'},
                {'name': 'Science', 'code': 'SCI', 'abbreviation': 'SCI', 'subject_type': 'SCIENCES', 'is_compulsory': True, 'pass_mark': 50.0, 'description': 'General science concepts'},
                {'name': 'Social Studies', 'code': 'SST', 'abbreviation': 'SST', 'subject_type': 'SOCIAL', 'is_compulsory': True, 'pass_mark': 50.0, 'description': 'Social and cultural studies'},
                {'name': 'Religious Education', 'code': 'RE', 'abbreviation': 'RE', 'subject_type': 'RELIGIOUS', 'is_compulsory': True, 'pass_mark': 50.0, 'description': 'Religious and moral education'},
                
                # Learning areas (lower primary)
                {'name': 'Literacy', 'code': 'LIT', 'abbreviation': 'LIT', 'subject_type': 'LITERACY', 'is_compulsory': True, 'pass_mark': 50.0, 'description': 'Reading and writing skills'},
                {'name': 'Numeracy', 'code': 'NUM', 'abbreviation': 'NUM', 'subject_type': 'NUMERACY', 'is_compulsory': True, 'pass_mark': 50.0, 'description': 'Number concepts and operations'},
                {'name': 'Life Skills', 'code': 'LIFE', 'abbreviation': 'LIFE', 'subject_type': 'LIFE_SKILLS', 'is_compulsory': True, 'pass_mark': 50.0, 'description': 'Practical life skills'},
                
                # Optional subjects
                {'name': 'Physical Education', 'code': 'PE', 'abbreviation': 'PE', 'subject_type': 'PE', 'is_compulsory': False, 'pass_mark': 50.0, 'description': 'Physical education and sports'},
                {'name': 'Arts and Crafts', 'code': 'ART', 'abbreviation': 'ART', 'subject_type': 'ARTS_CRAFTS', 'is_compulsory': False, 'pass_mark': 50.0, 'description': 'Visual arts and handicrafts'},
                {'name': 'Music', 'code': 'MUS', 'abbreviation': 'MUS', 'subject_type': 'MUSIC', 'is_compulsory': False, 'pass_mark': 50.0, 'description': 'Music theory and practice'},
                {'name': 'Computer Studies', 'code': 'ICT', 'abbreviation': 'ICT', 'subject_type': 'COMPUTER', 'is_compulsory': False, 'pass_mark': 50.0, 'description': 'Basic computer literacy'},
                {'name': 'Local Language', 'code': 'LOCAL', 'abbreviation': 'LOCAL', 'subject_type': 'MOTHER_TONGUE', 'is_compulsory': False, 'pass_mark': 50.0, 'description': 'Local/native language'},
            ],
            'secondary': [
                # Core subjects
                {'name': 'Mathematics', 'code': 'MATH', 'abbreviation': 'MATH', 'subject_type': 'MATH', 'is_compulsory': True, 'pass_mark': 50.0, 'description': 'Advanced mathematics'},
                {'name': 'English Language', 'code': 'ENG', 'abbreviation': 'ENG', 'subject_type': 'LANG_ARTS', 'is_compulsory': True, 'pass_mark': 50.0, 'description': 'English language and communication'},
                {'name': 'Biology', 'code': 'BIO', 'abbreviation': 'BIO', 'subject_type': 'SCIENCES', 'is_compulsory': True, 'pass_mark': 50.0, 'description': 'Biological sciences'},
                {'name': 'Chemistry', 'code': 'CHEM', 'abbreviation': 'CHEM', 'subject_type': 'SCIENCES', 'is_compulsory': True, 'pass_mark': 50.0, 'description': 'Chemical sciences'},
                {'name': 'Physics', 'code': 'PHY', 'abbreviation': 'PHY', 'subject_type': 'SCIENCES', 'is_compulsory': True, 'pass_mark': 50.0, 'description': 'Physical sciences'},
                {'name': 'History', 'code': 'HIST', 'abbreviation': 'HIST', 'subject_type': 'SOCIAL', 'is_compulsory': True, 'pass_mark': 50.0, 'description': 'World and local history'},
                {'name': 'Geography', 'code': 'GEOG', 'abbreviation': 'GEOG', 'subject_type': 'SOCIAL', 'is_compulsory': True, 'pass_mark': 50.0, 'description': 'Physical and human geography'},
                
                # Optional subjects
                {'name': 'Literature', 'code': 'LIT', 'abbreviation': 'LIT', 'subject_type': 'LANG_ARTS', 'is_compulsory': False, 'pass_mark': 50.0, 'description': 'English literature'},
                {'name': 'Economics', 'code': 'ECON', 'abbreviation': 'ECON', 'subject_type': 'BUSINESS', 'is_compulsory': False, 'pass_mark': 50.0, 'description': 'Economic principles and theory'},
                {'name': 'Agriculture', 'code': 'AGRIC', 'abbreviation': 'AGRIC', 'subject_type': 'AGRICULTURE', 'is_compulsory': False, 'pass_mark': 50.0, 'description': 'Agricultural science and practice'},
                {'name': 'Computer Studies', 'code': 'ICT', 'abbreviation': 'ICT', 'subject_type': 'COMPUTER', 'is_compulsory': False, 'pass_mark': 50.0, 'description': 'Computing and information technology'},
                {'name': 'French', 'code': 'FRE', 'abbreviation': 'FRE', 'subject_type': 'FOREIGN_LANG', 'is_compulsory': False, 'pass_mark': 50.0, 'description': 'French language'},
                {'name': 'Fine Art', 'code': 'ART', 'abbreviation': 'ART', 'subject_type': 'ARTS_CRAFTS', 'is_compulsory': False, 'pass_mark': 50.0, 'description': 'Visual and fine arts'},
                {'name': 'Music', 'code': 'MUS', 'abbreviation': 'MUS', 'subject_type': 'MUSIC', 'is_compulsory': False, 'pass_mark': 50.0, 'description': 'Music theory and performance'},
                {'name': 'Physical Education', 'code': 'PE', 'abbreviation': 'PE', 'subject_type': 'PE', 'is_compulsory': False, 'pass_mark': 50.0, 'description': 'Physical education and sports'},
                {'name': 'Business Studies', 'code': 'BUS', 'abbreviation': 'BUS', 'subject_type': 'BUSINESS', 'is_compulsory': False, 'pass_mark': 50.0, 'description': 'Business and entrepreneurship'},
                {'name': 'Accounting', 'code': 'ACC', 'abbreviation': 'ACC', 'subject_type': 'BUSINESS', 'is_compulsory': False, 'pass_mark': 50.0, 'description': 'Financial accounting principles'},
            ],
            'combined': [
                # Primary subjects
                {'name': 'Mathematics', 'code': 'MATH', 'abbreviation': 'MATH', 'subject_type': 'MATH', 'is_compulsory': True, 'pass_mark': 50.0, 'description': 'Mathematics (all levels)'},
                {'name': 'English', 'code': 'ENG', 'abbreviation': 'ENG', 'subject_type': 'LANG_ARTS', 'is_compulsory': True, 'pass_mark': 50.0, 'description': 'English language (all levels)'},
                {'name': 'Science', 'code': 'SCI', 'abbreviation': 'SCI', 'subject_type': 'SCIENCES', 'is_compulsory': True, 'pass_mark': 50.0, 'description': 'General science'},
                {'name': 'Social Studies', 'code': 'SST', 'abbreviation': 'SST', 'subject_type': 'SOCIAL', 'is_compulsory': True, 'pass_mark': 50.0, 'description': 'Social studies'},
                {'name': 'Religious Education', 'code': 'RE', 'abbreviation': 'RE', 'subject_type': 'RELIGIOUS', 'is_compulsory': True, 'pass_mark': 50.0, 'description': 'Religious education'},
                # Secondary subjects
                {'name': 'Biology', 'code': 'BIO', 'abbreviation': 'BIO', 'subject_type': 'SCIENCES', 'is_compulsory': False, 'pass_mark': 50.0, 'description': 'Biological sciences (secondary)'},
                {'name': 'Chemistry', 'code': 'CHEM', 'abbreviation': 'CHEM', 'subject_type': 'SCIENCES', 'is_compulsory': False, 'pass_mark': 50.0, 'description': 'Chemical sciences (secondary)'},
                {'name': 'Physics', 'code': 'PHY', 'abbreviation': 'PHY', 'subject_type': 'SCIENCES', 'is_compulsory': False, 'pass_mark': 50.0, 'description': 'Physical sciences (secondary)'},
                {'name': 'History', 'code': 'HIST', 'abbreviation': 'HIST', 'subject_type': 'SOCIAL', 'is_compulsory': False, 'pass_mark': 50.0, 'description': 'History (secondary)'},
                {'name': 'Geography', 'code': 'GEOG', 'abbreviation': 'GEOG', 'subject_type': 'SOCIAL', 'is_compulsory': False, 'pass_mark': 50.0, 'description': 'Geography (secondary)'},
                {'name': 'Literature', 'code': 'LIT', 'abbreviation': 'LIT', 'subject_type': 'LANG_ARTS', 'is_compulsory': False, 'pass_mark': 50.0, 'description': 'Literature (secondary)'},
                {'name': 'Economics', 'code': 'ECON', 'abbreviation': 'ECON', 'subject_type': 'BUSINESS', 'is_compulsory': False, 'pass_mark': 50.0, 'description': 'Economics (secondary)'},
                # Common optional subjects
                {'name': 'Physical Education', 'code': 'PE', 'abbreviation': 'PE', 'subject_type': 'PE', 'is_compulsory': False, 'pass_mark': 50.0, 'description': 'Physical education (all levels)'},
                {'name': 'Computer Studies', 'code': 'ICT', 'abbreviation': 'ICT', 'subject_type': 'COMPUTER', 'is_compulsory': False, 'pass_mark': 50.0, 'description': 'Computer studies (all levels)'},
                {'name': 'Music', 'code': 'MUS', 'abbreviation': 'MUS', 'subject_type': 'MUSIC', 'is_compulsory': False, 'pass_mark': 50.0, 'description': 'Music (all levels)'},
                {'name': 'Art', 'code': 'ART', 'abbreviation': 'ART', 'subject_type': 'ARTS_CRAFTS', 'is_compulsory': False, 'pass_mark': 50.0, 'description': 'Visual arts (all levels)'},
            ],
        }
        
        return subjects.get(curriculum_type, subjects['primary'])
    
    @classmethod
    def get_departments(cls):
        """Comprehensive school departments - FIXED VERSION with proper code lengths"""
        return [
            # CORE ADMINISTRATIVE DEPARTMENTS
            {
                'name': 'Administration',
                'code': 'ADMIN',
                'department_type': 'ADMINISTRATIVE',
                'description': 'School administration and management',
                'is_academic': False
            },
            {
                'name': 'Finance & Accounts',
                'code': 'FINANCE',
                'department_type': 'ADMINISTRATIVE',
                'description': 'Finance, accounting, and budgeting',
                'is_academic': False
            },
            {
                'name': 'Human Resources',
                'code': 'HR',
                'department_type': 'ADMINISTRATIVE',
                'description': 'Human resources management',
                'is_academic': False
            },
            {
                'name': 'Student Affairs',
                'code': 'STUDENT',
                'department_type': 'SUPPORT',
                'description': 'Student welfare and discipline',
                'is_academic': False
            },
            {
                'name': 'Admissions & Registry',
                'code': 'REGISTRY',
                'department_type': 'ADMINISTRATIVE',
                'description': 'Student admissions and records',
                'is_academic': False
            },
            
            # ACADEMIC DEPARTMENTS
            {
                'name': 'Academic Affairs',
                'code': 'ACADEMIC',
                'department_type': 'ACADEMIC',
                'description': 'Academic programs and curriculum oversight',
                'is_academic': True
            },
            {
                'name': 'Early Childhood Development',
                'code': 'ECD',
                'department_type': 'ACADEMIC',
                'description': 'Kindergarten and nursery education',
                'is_academic': True
            },
            {
                'name': 'Primary Education',
                'code': 'PRIMARY',
                'department_type': 'ACADEMIC',
                'description': 'Primary school education',
                'is_academic': True
            },
            {
                'name': 'Mathematics Department',
                'code': 'MATH',
                'department_type': 'ACADEMIC',
                'description': 'Mathematics instruction',
                'is_academic': True
            },
            {
                'name': 'Science Department',
                'code': 'SCIENCE',
                'department_type': 'ACADEMIC',
                'description': 'Science instruction (Biology, Chemistry, Physics)',
                'is_academic': True
            },
            {
                'name': 'English Department',
                'code': 'ENGLISH',
                'department_type': 'ACADEMIC',
                'description': 'English language and literature',
                'is_academic': True
            },
            {
                'name': 'Social Studies Department',
                'code': 'SST',
                'department_type': 'ACADEMIC',
                'description': 'History, Geography, and Social Studies',
                'is_academic': True
            },
            {
                'name': 'Languages Department',
                'code': 'LANG',
                'department_type': 'ACADEMIC',
                'description': 'Foreign and local languages',
                'is_academic': True
            },
            {
                'name': 'Business Studies Department',
                'code': 'BUSINESS',
                'department_type': 'ACADEMIC',
                'description': 'Business, Economics, and Accounting',
                'is_academic': True
            },
            {
                'name': 'Arts & Creative Studies',
                'code': 'ARTS',
                'department_type': 'ACADEMIC',
                'description': 'Fine Arts, Music, Drama',
                'is_academic': True
            },
            {
                'name': 'Physical Education',
                'code': 'PE',
                'department_type': 'ACADEMIC',
                'description': 'Physical education and sports',
                'is_academic': True
            },
            {
                'name': 'Religious Education',
                'code': 'RE',
                'department_type': 'ACADEMIC',
                'description': 'Religious and moral education',
                'is_academic': True
            },
            
            # SPECIALIZED ACADEMIC SUPPORT
            {
                'name': 'Library Services',
                'code': 'LIBRARY',
                'department_type': 'ACADEMIC',
                'description': 'Library and information services',
                'is_academic': False
            },
            {
                'name': 'ICT Services',
                'code': 'ICT',
                'department_type': 'TECHNICAL',
                'description': 'Information and communication technology',
                'is_academic': False
            },
            {
                'name': 'Examinations Office',
                'code': 'EXAMS',
                'department_type': 'ACADEMIC',
                'description': 'Examinations coordination and management',
                'is_academic': False
            },
            {
                'name': 'Guidance & Counseling',
                'code': 'COUNSEL',
                'department_type': 'SUPPORT',
                'description': 'Student guidance and counseling services',
                'is_academic': False
            },
            
            # OPERATIONAL SUPPORT DEPARTMENTS
            {
                'name': 'Facilities & Maintenance',
                'code': 'MAINT',
                'department_type': 'MAINTENANCE',
                'description': 'Building and equipment maintenance',
                'is_academic': False
            },
            {
                'name': 'Security Services',
                'code': 'SECURITY',
                'department_type': 'SECURITY',
                'description': 'School security and safety',
                'is_academic': False
            },
            {
                'name': 'Transport Services',
                'code': 'TRANSPORT',
                'department_type': 'TRANSPORT',
                'description': 'School transport and logistics',
                'is_academic': False
            },
            {
                'name': 'Health Services',
                'code': 'HEALTH',
                'department_type': 'HEALTH',
                'description': 'School clinic and health services',
                'is_academic': False
            },
            {
                'name': 'Boarding & Hostel Services',
                'code': 'BOARDING',
                'department_type': 'SUPPORT',
                'description': 'Boarding and residential services',
                'is_academic': False
            },
            {
                'name': 'Catering & Food Services',
                'code': 'CATERING',
                'department_type': 'CATERING',
                'description': 'Food preparation and catering services',
                'is_academic': False
            },
            {
                'name': 'Procurement & Stores',
                'code': 'PROCURE',
                'department_type': 'PROCUREMENT',
                'description': 'Purchasing and inventory management',
                'is_academic': False
            },
            
            # SPECIAL PROGRAMS
            {
                'name': 'Special Needs Support',
                'code': 'SPECIAL',
                'department_type': 'SUPPORT',
                'description': 'Special needs education support',
                'is_academic': True
            },
            {
                'name': 'International Programs',
                'code': 'INTL',
                'department_type': 'ACADEMIC',
                'description': 'International curriculum and programs',
                'is_academic': True
            },
            {
                'name': 'Parent Relations',
                'code': 'PARENT',
                'department_type': 'SUPPORT',
                'description': 'Parent-Teacher Association and relations',
                'is_academic': False
            },
            {
                'name': 'Quality Assurance',
                'code': 'QA',
                'department_type': 'ACADEMIC',
                'description': 'Academic quality assurance and standards',
                'is_academic': True
            },
        ]
    
    @classmethod
    def get_designations(cls, school_type='PRIMARY', school_obj=None):
        """
        Get job designations - FIXED VERSION with correct department codes
        All department codes now match the codes used in get_departments()
        """
        
        # Common designations for all school types
        common_designations = [
            # =====================================================================
            # SENIOR MANAGEMENT
            # =====================================================================
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
                'required_qualifications': [
                    'Bachelor\'s Degree in Education',
                    'Teaching experience (minimum 10 years)',
                    'Leadership and management training',
                    'Current teaching license'
                ],
                'key_responsibilities': 'Strategic planning, staff management, student welfare, community relations'
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
                'required_qualifications': [
                    'Bachelor\'s Degree in Education',
                    'Teaching experience (minimum 8 years)',
                    'Leadership training',
                    'Current teaching license'
                ],
                'key_responsibilities': 'Academic oversight, staff supervision, curriculum implementation'
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
                'required_qualifications': [
                    'Bachelor\'s Degree in Education',
                    'Curriculum development experience',
                    'Teaching experience (minimum 7 years)'
                ],
                'key_responsibilities': 'Curriculum development, academic standards, teacher training'
            },
            
            # =====================================================================
            # TEACHING POSITIONS
            # =====================================================================
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
                'required_qualifications': [
                    'Bachelor\'s Degree in Education or subject area',
                    'Teaching experience (minimum 5 years)',
                    'Current teaching license'
                ],
                'key_responsibilities': 'Subject instruction, mentoring junior teachers, curriculum support'
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
                'required_qualifications': [
                    'Bachelor\'s Degree in Education or subject area',
                    'Teaching license',
                    'Subject matter expertise'
                ],
                'key_responsibilities': 'Classroom instruction, student assessment, lesson planning'
            },
            {
                'name': 'Assistant Teacher',
                'code': 'ASSTEACH',
                'department_code': 'ACADEMIC',
                'description': 'Assistant to classroom teacher',
                'is_teaching': True,
                'is_management': False,
                'rank_order': 6,
                'min_salary': Decimal('400000.00'),
                'max_salary': Decimal('800000.00'),
                'required_qualifications': [
                    'Diploma in Education',
                    'Classroom support experience'
                ],
                'key_responsibilities': 'Classroom assistance, student support, materials preparation'
            },
            
            # =====================================================================
            # ADMINISTRATIVE POSITIONS
            # =====================================================================
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
                'required_qualifications': [
                    'Bachelor\'s Degree in Administration or related field',
                    'Administrative experience',
                    'Computer literacy'
                ],
                'key_responsibilities': 'Administrative coordination, record keeping, policy implementation'
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
                'required_qualifications': [
                    'Certificate in Secretarial Studies',
                    'Computer literacy',
                    'Communication skills'
                ],
                'key_responsibilities': 'Office administration, correspondence, visitor reception'
            },
            
            # =====================================================================
            # FINANCIAL POSITIONS - FIXED: Changed 'FIN' to 'FINANCE'
            # =====================================================================
            {
                'name': 'Bursar',
                'code': 'BURSAR',
                'department_code': 'FINANCE',  # ✅ FIXED: was 'FIN'
                'description': 'Financial management and accounting',
                'is_teaching': False,
                'is_management': True,
                'rank_order': 9,
                'min_salary': Decimal('900000.00'),
                'max_salary': Decimal('1800000.00'),
                'required_qualifications': [
                    'Bachelor\'s Degree in Accounting or Finance',
                    'Professional accounting qualification preferred',
                    'Financial management experience'
                ],
                'key_responsibilities': 'Financial planning, budget management, fee collection, financial reporting'
            },
            {
                'name': 'Accounts Clerk',
                'code': 'ACCOUNTS',
                'department_code': 'FINANCE',  # ✅ FIXED: was 'FIN'
                'description': 'Financial record keeping and transactions',
                'is_teaching': False,
                'is_management': False,
                'rank_order': 10,
                'min_salary': Decimal('500000.00'),
                'max_salary': Decimal('900000.00'),
                'required_qualifications': [
                    'Diploma in Accounting',
                    'Computer literacy',
                    'Attention to detail'
                ],
                'key_responsibilities': 'Financial transactions, record keeping, invoice processing'
            },
            
            # =====================================================================
            # PROCUREMENT POSITIONS - FIXED: Changed 'PROC' to 'PROCUREMENT'
            # Note: Make sure 'PROCUREMENT' department exists in get_departments()
            # =====================================================================
            {
                'name': 'Procurement Officer',
                'code': 'PROCURE',
                'department_code': 'PROCUREMENT',  # ✅ FIXED: was 'PROC'
                'description': 'Purchasing and vendor management',
                'is_teaching': False,
                'is_management': False,
                'rank_order': 11,
                'min_salary': Decimal('700000.00'),
                'max_salary': Decimal('1300000.00'),
                'required_qualifications': [
                    'Diploma/Degree in Procurement or Business',
                    'Vendor management experience',
                    'Negotiation skills'
                ],
                'key_responsibilities': 'Vendor sourcing, purchase planning, contract negotiation, quality assurance'
            },
            {
                'name': 'Stores Keeper',
                'code': 'STORES',
                'department_code': 'PROCUREMENT',  # ✅ FIXED: was 'PROC'
                'description': 'Inventory management and storage',
                'is_teaching': False,
                'is_management': False,
                'rank_order': 12,
                'min_salary': Decimal('400000.00'),
                'max_salary': Decimal('750000.00'),
                'required_qualifications': [
                    'Certificate in Stores Management',
                    'Inventory management skills',
                    'Computer literacy'
                ],
                'key_responsibilities': 'Inventory control, stock management, issue control, record keeping'
            },
            
            # =====================================================================
            # STUDENT SUPPORT
            # =====================================================================
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
                'required_qualifications': [
                    'Bachelor\'s Degree in Education or Social Sciences',
                    'Student affairs experience',
                    'Counseling skills'
                ],
                'key_responsibilities': 'Student welfare, discipline, counseling coordination, activities'
            },
            {
                'name': 'School Counselor',
                'code': 'COUNSEL',
                'department_code': 'COUNSEL',  # ✅ FIXED: was 'GUIDE'
                'description': 'Student counseling and guidance',
                'is_teaching': False,
                'is_management': False,
                'rank_order': 14,
                'min_salary': Decimal('600000.00'),
                'max_salary': Decimal('1200000.00'),
                'required_qualifications': [
                    'Bachelor\'s Degree in Psychology or Counseling',
                    'Counseling certification',
                    'Experience with children/adolescents'
                ],
                'key_responsibilities': 'Individual counseling, group sessions, crisis intervention, referrals'
            },
            {
                'name': 'Registrar',
                'code': 'REGISTRAR',
                'department_code': 'REGISTRY',
                'description': 'Student records and registration management',
                'is_teaching': False,
                'is_management': False,
                'rank_order': 15,
                'min_salary': Decimal('600000.00'),
                'max_salary': Decimal('1100000.00'),
                'required_qualifications': [
                    'Bachelor\'s Degree',
                    'Records management experience',
                    'Computer literacy'
                ],
                'key_responsibilities': 'Student records, registration, transcripts, data management'
            },
            
            # =====================================================================
            # SUPPORT STAFF - FIXED: Library, ICT, Health codes
            # =====================================================================
            {
                'name': 'Librarian',
                'code': 'LIBRAR',
                'department_code': 'LIBRARY',  # ✅ FIXED: was 'LIB'
                'description': 'Library management and information services',
                'is_teaching': False,
                'is_management': False,
                'rank_order': 16,
                'min_salary': Decimal('500000.00'),
                'max_salary': Decimal('1000000.00'),
                'required_qualifications': [
                    'Bachelor\'s Degree in Library Science or related field',
                    'Library management experience',
                    'Computer literacy'
                ],
                'key_responsibilities': 'Library operations, resource management, student assistance, cataloging'
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
                'required_qualifications': [
                    'Diploma/Degree in Computer Science or IT',
                    'Network administration skills',
                    'Technical support experience'
                ],
                'key_responsibilities': 'IT infrastructure, system maintenance, user support, training'
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
                'required_qualifications': [
                    'Diploma in Nursing',
                    'Valid nursing license',
                    'First aid certification'
                ],
                'key_responsibilities': 'Student health care, medical emergencies, health education, record keeping'
            },
            
            # =====================================================================
            # OPERATIONAL STAFF - FIXED: Security and Transport codes
            # =====================================================================
            {
                'name': 'Security Guard',
                'code': 'SECURITY',
                'department_code': 'SECURITY',  # ✅ FIXED: was 'SEC'
                'description': 'School security and safety',
                'is_teaching': False,
                'is_management': False,
                'rank_order': 19,
                'min_salary': Decimal('300000.00'),
                'max_salary': Decimal('600000.00'),
                'required_qualifications': [
                    'Security training certificate',
                    'Physical fitness',
                    'Reliability'
                ],
                'key_responsibilities': 'Premises security, access control, incident reporting, emergency response'
            },
            {
                'name': 'Driver',
                'code': 'DRIVER',
                'department_code': 'TRANSPORT',  # ✅ FIXED: was 'TRANS'
                'description': 'School transport services',
                'is_teaching': False,
                'is_management': False,
                'rank_order': 20,
                'min_salary': Decimal('350000.00'),
                'max_salary': Decimal('700000.00'),
                'required_qualifications': [
                    'Valid driving license',
                    'Clean driving record',
                    'Vehicle maintenance knowledge'
                ],
                'key_responsibilities': 'Student transport, vehicle maintenance, route management, safety compliance'
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
                'required_qualifications': [
                    'Basic maintenance skills',
                    'Physical fitness',
                    'Tool handling experience'
                ],
                'key_responsibilities': 'Grounds maintenance, cleaning, basic repairs, facility upkeep'
            },
            {
                'name': 'Cleaner',
                'code': 'CLEANER',
                'department_code': 'MAINT',
                'description': 'Cleaning and sanitation services',
                'is_teaching': False,
                'is_management': False,
                'rank_order': 22,
                'min_salary': Decimal('250000.00'),
                'max_salary': Decimal('500000.00'),
                'required_qualifications': [
                    'Basic literacy',
                    'Hygiene awareness',
                    'Reliability'
                ],
                'key_responsibilities': 'Facility cleaning, sanitation, waste management, supply inventory'
            }
        ]
        
        # =========================================================================
        # SCHOOL TYPE SPECIFIC ADDITIONS
        # =========================================================================
        
        # Secondary/High School Specific
        if school_type in ['SECONDARY', 'HIGH_SCHOOL']:
            secondary_specific = [
                {
                    'name': 'Subject Coordinator',
                    'code': 'SUBJCOORD',
                    'department_code': 'ACADEMIC',
                    'description': 'Coordinates specific subject department',
                    'is_teaching': True,
                    'is_management': True,
                    'rank_order': 23,
                    'min_salary': Decimal('900000.00'),
                    'max_salary': Decimal('1600000.00'),
                    'required_qualifications': [
                        'Bachelor\'s Degree in subject area',
                        'Teaching experience (minimum 5 years)',
                        'Leadership skills'
                    ],
                    'key_responsibilities': 'Subject curriculum, teacher coordination, resource planning'
                },
                {
                    'name': 'Careers Counselor',
                    'code': 'CAREERS',
                    'department_code': 'COUNSEL',  # ✅ FIXED: was 'GUIDE'
                    'description': 'Career guidance and university preparation',
                    'is_teaching': False,
                    'is_management': False,
                    'rank_order': 24,
                    'min_salary': Decimal('600000.00'),
                    'max_salary': Decimal('1200000.00'),
                    'required_qualifications': [
                        'Bachelor\'s Degree in Counseling or Education',
                        'Career guidance training',
                        'University admission knowledge'
                    ],
                    'key_responsibilities': 'Career counseling, university applications, aptitude testing, job market guidance'
                }
            ]
            common_designations.extend(secondary_specific)
        
        # Boarding/Residential School Specific
        if school_type in ['BOARDING', 'RESIDENTIAL']:
            boarding_specific = [
                {
                    'name': 'Boarding Master/Mistress',
                    'code': 'BOARDING',
                    'department_code': 'BOARDING',  # ✅ FIXED: was 'BOARD'
                    'description': 'Residential facility management',
                    'is_teaching': False,
                    'is_management': True,
                    'rank_order': 25,
                    'min_salary': Decimal('700000.00'),
                    'max_salary': Decimal('1400000.00'),
                    'required_qualifications': [
                        'Bachelor\'s Degree',
                        'Residential management experience',
                        'Child welfare knowledge'
                    ],
                    'key_responsibilities': 'Dormitory management, student welfare, discipline, residential activities'
                },
                {
                    'name': 'House Parent',
                    'code': 'HOUSEPNT',
                    'department_code': 'BOARDING',  # ✅ FIXED: was 'BOARD'
                    'description': 'Residential house supervision',
                    'is_teaching': False,
                    'is_management': False,
                    'rank_order': 26,
                    'min_salary': Decimal('500000.00'),
                    'max_salary': Decimal('900000.00'),
                    'required_qualifications': [
                        'Certificate in Child Care or related field',
                        'Experience with children',
                        'Communication skills'
                    ],
                    'key_responsibilities': 'Student supervision, welfare monitoring, conflict resolution, activities coordination'
                }
            ]
            common_designations.extend(boarding_specific)
        
        # Technical/Vocational School Specific
        if school_type in ['TECHNICAL', 'VOCATIONAL']:
            technical_specific = [
                {
                    'name': 'Workshop Supervisor',
                    'code': 'WORKSHOP',
                    'department_code': 'ACADEMIC',
                    'description': 'Technical workshop management',
                    'is_teaching': True,
                    'is_management': False,
                    'rank_order': 27,
                    'min_salary': Decimal('700000.00'),
                    'max_salary': Decimal('1300000.00'),
                    'required_qualifications': [
                        'Technical qualification in relevant field',
                        'Workshop safety training',
                        'Teaching experience'
                    ],
                    'key_responsibilities': 'Workshop safety, equipment maintenance, practical instruction, inventory management'
                }
            ]
            common_designations.extend(technical_specific)
        
        return common_designations

    @classmethod
    def get_contract_types(cls):
        """Standard contract types for school staff"""
        return [
            {
                'name': 'Permanent Full-Time',
                'description': 'Permanent employment with full benefits and job security',
                'default_duration_months': 0,  # 0 means indefinite/permanent
                'requires_renewal': False,
                'auto_create_probation': True,
                'default_probation_months': 6,
                'is_active': True,
            },
            {
                'name': 'Permanent Part-Time',
                'description': 'Permanent part-time employment with pro-rated benefits',
                'default_duration_months': 0,  # 0 means indefinite/permanent
                'requires_renewal': False,
                'auto_create_probation': True,
                'default_probation_months': 3,
                'is_active': True,
            },
            {
                'name': 'Fixed-Term Contract',
                'description': 'Employment for a specific period with defined end date',
                'default_duration_months': 12,
                'requires_renewal': True,
                'auto_create_probation': True,
                'default_probation_months': 3,
                'is_active': True,
            },
            {
                'name': 'Academic Year Contract',
                'description': 'Contract aligned with academic year calendar',
                'default_duration_months': 10,  # Typical academic year
                'requires_renewal': True,
                'auto_create_probation': False,  # Usually for returning staff
                'default_probation_months': 0,
                'is_active': True,
            },
            {
                'name': 'Term Contract',
                'description': 'Contract for single academic term',
                'default_duration_months': 3,
                'requires_renewal': True,
                'auto_create_probation': False,
                'default_probation_months': 0,
                'is_active': True,
            },
            {
                'name': 'Temporary Contract',
                'description': 'Short-term employment for specific needs or coverage',
                'default_duration_months': 6,
                'requires_renewal': True,
                'auto_create_probation': False,
                'default_probation_months': 1,
                'is_active': True,
            },
            {
                'name': 'Substitute/Relief Contract',
                'description': 'Temporary coverage for absent staff',
                'default_duration_months': 1,
                'requires_renewal': True,
                'auto_create_probation': False,
                'default_probation_months': 0,
                'is_active': True,
            },
            {
                'name': 'Internship Contract',
                'description': 'Training position for new graduates or students',
                'default_duration_months': 6,
                'requires_renewal': True,
                'auto_create_probation': False,
                'default_probation_months': 1,
                'is_active': True,
            },
            {
                'name': 'Volunteer Agreement',
                'description': 'Non-paid volunteer service agreement',
                'default_duration_months': 12,
                'requires_renewal': True,
                'auto_create_probation': False,
                'default_probation_months': 0,
                'is_active': True,
            },
            {
                'name': 'Consultant Contract',
                'description': 'Professional services contract for specialized expertise',
                'default_duration_months': 6,
                'requires_renewal': True,
                'auto_create_probation': False,
                'default_probation_months': 0,
                'is_active': True,
            },
            {
                'name': 'Casual/Daily Rate',
                'description': 'Day-to-day employment without long-term commitment',
                'default_duration_months': 1,
                'requires_renewal': True,
                'auto_create_probation': False,
                'default_probation_months': 0,
                'is_active': True,
            },
            {
                'name': 'Seasonal Contract',
                'description': 'Employment during specific seasons or periods',
                'default_duration_months': 4,
                'requires_renewal': True,
                'auto_create_probation': False,
                'default_probation_months': 0,
                'is_active': True,
            },
            {
                'name': 'Probationary Contract',
                'description': 'Initial employment period for evaluation',
                'default_duration_months': 6,
                'requires_renewal': True,
                'auto_create_probation': False,  # This IS the probation
                'default_probation_months': 0,
                'is_active': True,
            },
            {
                'name': 'Retirement Contract',
                'description': 'Part-time employment for retired staff',
                'default_duration_months': 12,
                'requires_renewal': True,
                'auto_create_probation': False,
                'default_probation_months': 0,
                'is_active': True,
            },
            {
                'name': 'Research Contract',
                'description': 'Contract for research and development activities',
                'default_duration_months': 24,
                'requires_renewal': True,
                'auto_create_probation': True,
                'default_probation_months': 3,
                'is_active': True,
            }
        ]
    
    @classmethod
    def get_advanced_allowance_types(cls):
        """Comprehensive allowance types for staff compensation"""
        return [
            # BASIC ALLOWANCES
            {
                'name': 'Housing Allowance',
                'code': 'HOUSE',
                'description': 'Monthly housing/accommodation allowance',
                'calculation_type': 'PERCENTAGE',
                'default_amount': Decimal('0.00'),
                'default_percentage': Decimal('30.00'),  # 30% of basic salary
                'is_taxable': True,
                'is_pensionable': True,
                'applicable_employment_types': ['FT', 'PT', 'CT'],
                'requires_approval': False,
                'is_active': True,
            },
            {
                'name': 'Transport Allowance',
                'code': 'TRANS',
                'description': 'Monthly transport/commuting allowance',
                'calculation_type': 'FIXED',
                'default_amount': Decimal('200000.00'),  # UGX 200K
                'default_percentage': Decimal('0.00'),
                'is_taxable': True,
                'is_pensionable': False,
                'applicable_employment_types': ['FT', 'PT', 'CT'],
                'requires_approval': False,
                'is_active': True,
            },
            {
                'name': 'Lunch Allowance',
                'code': 'LUNCH',
                'description': 'Daily lunch allowance for non-boarding staff',
                'calculation_type': 'DAILY',
                'default_amount': Decimal('15000.00'),  # UGX 15K per day
                'default_percentage': Decimal('0.00'),
                'is_taxable': True,
                'is_pensionable': False,
                'applicable_employment_types': ['FT', 'PT', 'CT'],
                'requires_approval': False,
                'is_active': True,
            },
            {
                'name': 'Communication Allowance',
                'code': 'COMM',
                'description': 'Monthly phone/internet allowance',
                'calculation_type': 'FIXED',
                'default_amount': Decimal('100000.00'),  # UGX 100K
                'default_percentage': Decimal('0.00'),
                'is_taxable': True,
                'is_pensionable': False,
                'applicable_employment_types': ['FT', 'CT'],
                'requires_approval': False,
                'is_active': True,
            },
            
            # RESPONSIBILITY ALLOWANCES
            {
                'name': 'Management Allowance',
                'code': 'MGMT',
                'description': 'Additional allowance for management responsibilities',
                'calculation_type': 'PERCENTAGE',
                'default_amount': Decimal('0.00'),
                'default_percentage': Decimal('20.00'),  # 20% of basic salary
                'is_taxable': True,
                'is_pensionable': True,
                'applicable_employment_types': ['FT', 'CT'],
                'requires_approval': True,
                'is_active': True,
            },
            {
                'name': 'Head of Department Allowance',
                'code': 'HOD',
                'description': 'Additional allowance for department heads',
                'calculation_type': 'PERCENTAGE',
                'default_amount': Decimal('0.00'),
                'default_percentage': Decimal('15.00'),  # 15% of basic salary
                'is_taxable': True,
                'is_pensionable': True,
                'applicable_employment_types': ['FT', 'CT'],
                'requires_approval': True,
                'is_active': True,
            },
            {
                'name': 'Class Teacher Allowance',
                'code': 'CLSTEACH',
                'description': 'Additional allowance for class teachers',
                'calculation_type': 'FIXED',
                'default_amount': Decimal('150000.00'),  # UGX 150K
                'default_percentage': Decimal('0.00'),
                'is_taxable': True,
                'is_pensionable': True,
                'applicable_employment_types': ['FT', 'PT', 'CT'],
                'requires_approval': False,
                'is_active': True,
            },
            {
                'name': 'Subject Coordinator Allowance',
                'code': 'SUBJCORD',
                'description': 'Allowance for subject coordination duties',
                'calculation_type': 'FIXED',
                'default_amount': Decimal('100000.00'),  # UGX 100K
                'default_percentage': Decimal('0.00'),
                'is_taxable': True,
                'is_pensionable': True,
                'applicable_employment_types': ['FT', 'PT', 'CT'],
                'requires_approval': False,
                'is_active': True,
            },
            
            # QUALIFICATION ALLOWANCES
            {
                'name': 'Graduate Allowance',
                'code': 'GRAD',
                'description': 'Allowance for degree qualification',
                'calculation_type': 'PERCENTAGE',
                'default_amount': Decimal('0.00'),
                'default_percentage': Decimal('10.00'),  # 10% of basic salary
                'is_taxable': True,
                'is_pensionable': True,
                'applicable_employment_types': ['FT', 'PT', 'CT'],
                'requires_approval': False,
                'is_active': True,
            },
            {
                'name': 'Postgraduate Allowance',
                'code': 'POSTGRAD',
                'description': 'Additional allowance for postgraduate qualifications',
                'calculation_type': 'PERCENTAGE',
                'default_amount': Decimal('0.00'),
                'default_percentage': Decimal('15.00'),  # 15% of basic salary
                'is_taxable': True,
                'is_pensionable': True,
                'applicable_employment_types': ['FT', 'PT', 'CT'],
                'requires_approval': True,
                'is_active': True,
            },
            {
                'name': 'Professional Certification Allowance',
                'code': 'PROFCERT',
                'description': 'Allowance for professional certifications',
                'calculation_type': 'FIXED',
                'default_amount': Decimal('200000.00'),  # UGX 200K
                'default_percentage': Decimal('0.00'),
                'is_taxable': True,
                'is_pensionable': True,
                'applicable_employment_types': ['FT', 'CT'],
                'requires_approval': True,
                'is_active': True,
            },
            
            # SPECIAL ALLOWANCES
            {
                'name': 'Overtime Allowance',
                'code': 'OVERTIME',
                'description': 'Payment for work beyond normal hours',
                'calculation_type': 'HOURLY',
                'default_amount': Decimal('10000.00'),  # UGX 10K per hour
                'default_percentage': Decimal('0.00'),
                'is_taxable': True,
                'is_pensionable': False,
                'applicable_employment_types': ['FT', 'PT', 'CT'],
                'requires_approval': True,
                'is_active': True,
            },
            {
                'name': 'Weekend Duty Allowance',
                'code': 'WEEKEND',
                'description': 'Allowance for weekend work',
                'calculation_type': 'DAILY',
                'default_amount': Decimal('50000.00'),  # UGX 50K per day
                'default_percentage': Decimal('0.00'),
                'is_taxable': True,
                'is_pensionable': False,
                'applicable_employment_types': ['FT', 'PT', 'CT'],
                'requires_approval': True,
                'is_active': True,
            },
            {
                'name': 'Night Duty Allowance',
                'code': 'NIGHT',
                'description': 'Allowance for night shift work',
                'calculation_type': 'DAILY',
                'default_amount': Decimal('30000.00'),  # UGX 30K per night
                'default_percentage': Decimal('0.00'),
                'is_taxable': True,
                'is_pensionable': False,
                'applicable_employment_types': ['FT', 'PT', 'CT'],
                'requires_approval': False,
                'is_active': True,
            },
            {
                'name': 'Examination Allowance',
                'code': 'EXAM',
                'description': 'Allowance for examination duties',
                'calculation_type': 'DAILY',
                'default_amount': Decimal('25000.00'),  # UGX 25K per day
                'default_percentage': Decimal('0.00'),
                'is_taxable': True,
                'is_pensionable': False,
                'applicable_employment_types': ['FT', 'PT', 'CT'],
                'requires_approval': False,
                'is_active': True,
            },
            {
                'name': 'Sports Coaching Allowance',
                'code': 'SPORTS',
                'description': 'Allowance for sports coaching activities',
                'calculation_type': 'FIXED',
                'default_amount': Decimal('150000.00'),  # UGX 150K per month
                'default_percentage': Decimal('0.00'),
                'is_taxable': True,
                'is_pensionable': False,
                'applicable_employment_types': ['FT', 'PT', 'CT'],
                'requires_approval': False,
                'is_active': True,
            },
            
            # HARDSHIP ALLOWANCES
            {
                'name': 'Rural Hardship Allowance',
                'code': 'RURAL',
                'description': 'Allowance for working in rural/remote areas',
                'calculation_type': 'PERCENTAGE',
                'default_amount': Decimal('0.00'),
                'default_percentage': Decimal('25.00'),  # 25% of basic salary
                'is_taxable': True,
                'is_pensionable': True,
                'applicable_employment_types': ['FT', 'CT'],
                'requires_approval': True,
                'is_active': True,
            },
            {
                'name': 'Risk Allowance',
                'code': 'RISK',
                'description': 'Allowance for high-risk or hazardous duties',
                'calculation_type': 'PERCENTAGE',
                'default_amount': Decimal('0.00'),
                'default_percentage': Decimal('20.00'),  # 20% of basic salary
                'is_taxable': True,
                'is_pensionable': True,
                'applicable_employment_types': ['FT', 'CT'],
                'requires_approval': True,
                'is_active': True,
            },
            
            # PERFORMANCE ALLOWANCES
            {
                'name': 'Performance Bonus',
                'code': 'PERFBON',
                'description': 'Performance-based bonus payment',
                'calculation_type': 'PERFORMANCE',
                'default_amount': Decimal('500000.00'),  # UGX 500K
                'default_percentage': Decimal('0.00'),
                'is_taxable': True,
                'is_pensionable': False,
                'applicable_employment_types': ['FT', 'CT'],
                'requires_approval': True,
                'is_active': True,
            },
            {
                'name': 'Long Service Allowance',
                'code': 'LONGSERV',
                'description': 'Allowance for long-term service',
                'calculation_type': 'PERCENTAGE',
                'default_amount': Decimal('0.00'),
                'default_percentage': Decimal('5.00'),  # 5% of basic salary
                'is_taxable': True,
                'is_pensionable': True,
                'applicable_employment_types': ['FT'],
                'requires_approval': False,
                'is_active': True,
            },
            
            # MEDICAL AND WELFARE
            {
                'name': 'Medical Allowance',
                'code': 'MEDICAL',
                'description': 'Monthly medical/health allowance',
                'calculation_type': 'FIXED',
                'default_amount': Decimal('100000.00'),  # UGX 100K
                'default_percentage': Decimal('0.00'),
                'is_taxable': False,  # Usually tax-exempt
                'is_pensionable': False,
                'applicable_employment_types': ['FT', 'CT'],
                'requires_approval': False,
                'is_active': True,
            },
            {
                'name': 'Uniform Allowance',
                'code': 'UNIFORM',
                'description': 'Annual uniform/clothing allowance',
                'calculation_type': 'FIXED',
                'default_amount': Decimal('200000.00'),  # UGX 200K annually
                'default_percentage': Decimal('0.00'),
                'is_taxable': False,
                'is_pensionable': False,
                'applicable_employment_types': ['FT', 'PT', 'CT'],
                'requires_approval': False,
                'is_active': True,
            },
            
            # SPECIAL CIRCUMSTANCES
            {
                'name': 'Acting Allowance',
                'code': 'ACTING',
                'description': 'Allowance when acting in higher position',
                'calculation_type': 'PERCENTAGE',
                'default_amount': Decimal('0.00'),
                'default_percentage': Decimal('25.00'),  # 25% of basic salary
                'is_taxable': True,
                'is_pensionable': False,
                'applicable_employment_types': ['FT', 'CT'],
                'requires_approval': True,
                'is_active': True,
            },
            {
                'name': 'Retention Allowance',
                'code': 'RETAIN',
                'description': 'Special allowance to retain critical staff',
                'calculation_type': 'FIXED',
                'default_amount': Decimal('500000.00'),  # UGX 500K
                'default_percentage': Decimal('0.00'),
                'is_taxable': True,
                'is_pensionable': True,
                'applicable_employment_types': ['FT'],
                'requires_approval': True,
                'is_active': True,
            }
        ]

    @classmethod
    def get_advanced_deduction_types(cls):
        """Comprehensive deduction types for staff payroll"""
        return [
            # STATUTORY DEDUCTIONS
            {
                'name': 'Pay As You Earn (PAYE)',
                'code': 'PAYE',
                'description': 'Government income tax deduction',
                'calculation_type': 'TIERED',
                'default_amount': Decimal('0.00'),
                'default_percentage': Decimal('0.00'),  # Calculated based on tax brackets
                'minimum_amount': Decimal('0.00'),
                'maximum_amount': Decimal('0.00'),  # No limit
                'category': 'STATUTORY',
                'is_mandatory': True,
                'requires_employee_consent': False,
                'is_active': True,
            },
            {
                'name': 'National Social Security Fund (NSSF)',
                'code': 'NSSF',
                'description': 'Mandatory social security contribution',
                'calculation_type': 'PERCENTAGE',
                'default_amount': Decimal('0.00'),
                'default_percentage': Decimal('5.00'),  # 5% of gross salary
                'minimum_amount': Decimal('0.00'),
                'maximum_amount': Decimal('200000.00'),  # UGX 200K max per month
                'category': 'STATUTORY',
                'is_mandatory': True,
                'requires_employee_consent': False,
                'is_active': True,
            },
            {
                'name': 'Local Service Tax',
                'code': 'LST',
                'description': 'Local government service tax',
                'calculation_type': 'FIXED',
                'default_amount': Decimal('30000.00'),  # UGX 30K per year
                'default_percentage': Decimal('0.00'),
                'minimum_amount': Decimal('30000.00'),
                'maximum_amount': Decimal('30000.00'),
                'category': 'STATUTORY',
                'is_mandatory': True,
                'requires_employee_consent': False,
                'is_active': True,
            },
            
            # PENSION AND RETIREMENT
            {
                'name': 'Pension Contribution',
                'code': 'PENSION',
                'description': 'Employee pension fund contribution',
                'calculation_type': 'PERCENTAGE',
                'default_amount': Decimal('0.00'),
                'default_percentage': Decimal('5.00'),  # 5% of basic salary
                'minimum_amount': Decimal('0.00'),
                'maximum_amount': Decimal('0.00'),  # No limit
                'category': 'VOLUNTARY',
                'is_mandatory': False,
                'requires_employee_consent': True,
                'is_active': True,
            },
            {
                'name': 'Provident Fund',
                'code': 'PROVIDENT',
                'description': 'Employee provident fund contribution',
                'calculation_type': 'PERCENTAGE',
                'default_amount': Decimal('0.00'),
                'default_percentage': Decimal('10.00'),  # 10% of basic salary
                'minimum_amount': Decimal('0.00'),
                'maximum_amount': Decimal('0.00'),  # No limit
                'category': 'VOLUNTARY',
                'is_mandatory': False,
                'requires_employee_consent': True,
                'is_active': True,
            },
            
            # INSURANCE
            {
                'name': 'Medical Insurance',
                'code': 'MEDINS',
                'description': 'Employee medical insurance premium',
                'calculation_type': 'FIXED',
                'default_amount': Decimal('50000.00'),  # UGX 50K per month
                'default_percentage': Decimal('0.00'),
                'minimum_amount': Decimal('50000.00'),
                'maximum_amount': Decimal('200000.00'),
                'category': 'VOLUNTARY',
                'is_mandatory': False,
                'requires_employee_consent': True,
                'is_active': True,
            },
            {
                'name': 'Life Insurance',
                'code': 'LIFEINS',
                'description': 'Employee life insurance premium',
                'calculation_type': 'PERCENTAGE',
                'default_amount': Decimal('0.00'),
                'default_percentage': Decimal('1.00'),  # 1% of basic salary
                'minimum_amount': Decimal('10000.00'),
                'maximum_amount': Decimal('100000.00'),
                'category': 'VOLUNTARY',
                'is_mandatory': False,
                'requires_employee_consent': True,
                'is_active': True,
            },
            {
                'name': 'Group Personal Accident Insurance',
                'code': 'ACCINS',
                'description': 'Personal accident insurance coverage',
                'calculation_type': 'FIXED',
                'default_amount': Decimal('15000.00'),  # UGX 15K per month
                'default_percentage': Decimal('0.00'),
                'minimum_amount': Decimal('15000.00'),
                'maximum_amount': Decimal('50000.00'),
                'category': 'VOLUNTARY',
                'is_mandatory': False,
                'requires_employee_consent': True,
                'is_active': True,
            },
            
            # LOANS AND ADVANCES
            {
                'name': 'Salary Advance',
                'code': 'ADVANCE',
                'description': 'Deduction for salary advance repayment',
                'calculation_type': 'LOAN_INSTALLMENT',
                'default_amount': Decimal('0.00'),
                'default_percentage': Decimal('0.00'),
                'minimum_amount': Decimal('0.00'),
                'maximum_amount': Decimal('0.00'),  # Based on salary
                'category': 'ADVANCE',
                'is_mandatory': False,
                'requires_employee_consent': True,
                'is_active': True,
            },
            {
                'name': 'Staff Loan',
                'code': 'LOAN',
                'description': 'Deduction for staff loan repayment',
                'calculation_type': 'LOAN_INSTALLMENT',
                'default_amount': Decimal('0.00'),
                'default_percentage': Decimal('0.00'),
                'minimum_amount': Decimal('0.00'),
                'maximum_amount': Decimal('0.00'),  # Based on loan terms
                'category': 'LOAN',
                'is_mandatory': False,
                'requires_employee_consent': True,
                'is_active': True,
            },
            {
                'name': 'Emergency Loan',
                'code': 'EMERGENCY',
                'description': 'Emergency loan repayment deduction',
                'calculation_type': 'LOAN_INSTALLMENT',
                'default_amount': Decimal('0.00'),
                'default_percentage': Decimal('0.00'),
                'minimum_amount': Decimal('0.00'),
                'maximum_amount': Decimal('1000000.00'),  # UGX 1M max
                'category': 'LOAN',
                'is_mandatory': False,
                'requires_employee_consent': True,
                'is_active': True,
            },
            {
                'name': 'Housing Loan',
                'code': 'HOUSELOAN',
                'description': 'Housing/mortgage loan repayment',
                'calculation_type': 'LOAN_INSTALLMENT',
                'default_amount': Decimal('0.00'),
                'default_percentage': Decimal('0.00'),
                'minimum_amount': Decimal('0.00'),
                'maximum_amount': Decimal('0.00'),  # Based on loan terms
                'category': 'LOAN',
                'is_mandatory': False,
                'requires_employee_consent': True,
                'is_active': True,
            },
            
            # WELFARE AND COOPERATIVE
            {
                'name': 'Staff Welfare Fund',
                'code': 'WELFARE',
                'description': 'Monthly contribution to staff welfare fund',
                'calculation_type': 'FIXED',
                'default_amount': Decimal('20000.00'),  # UGX 20K per month
                'default_percentage': Decimal('0.00'),
                'minimum_amount': Decimal('10000.00'),
                'maximum_amount': Decimal('50000.00'),
                'category': 'VOLUNTARY',
                'is_mandatory': False,
                'requires_employee_consent': True,
                'is_active': True,
            },
            {
                'name': 'Staff Cooperative',
                'code': 'COOP',
                'description': 'Monthly cooperative society contribution',
                'calculation_type': 'PERCENTAGE',
                'default_amount': Decimal('0.00'),
                'default_percentage': Decimal('2.00'),  # 2% of basic salary
                'minimum_amount': Decimal('10000.00'),
                'maximum_amount': Decimal('100000.00'),
                'category': 'VOLUNTARY',
                'is_mandatory': False,
                'requires_employee_consent': True,
                'is_active': True,
            },
            {
                'name': 'Staff SACCO',
                'code': 'SACCO',
                'description': 'Savings and Credit Cooperative contribution',
                'calculation_type': 'PERCENTAGE',
                'default_amount': Decimal('0.00'),
                'default_percentage': Decimal('10.00'),  # 10% of basic salary
                'minimum_amount': Decimal('50000.00'),
                'maximum_amount': Decimal('500000.00'),
                'category': 'VOLUNTARY',
                'is_mandatory': False,
                'requires_employee_consent': True,
                'is_active': True,
            },
            
            # PROFESSIONAL AND UNION
            {
                'name': 'Professional Membership',
                'code': 'PROF',
                'description': 'Professional association membership fees',
                'calculation_type': 'FIXED',
                'default_amount': Decimal('25000.00'),  # UGX 25K per month
                'default_percentage': Decimal('0.00'),
                'minimum_amount': Decimal('10000.00'),
                'maximum_amount': Decimal('100000.00'),
                'category': 'VOLUNTARY',
                'is_mandatory': False,
                'requires_employee_consent': True,
                'is_active': True,
            },
            {
                'name': 'Union Dues',
                'code': 'UNION',
                'description': 'Trade union membership dues',
                'calculation_type': 'PERCENTAGE',
                'default_amount': Decimal('0.00'),
                'default_percentage': Decimal('1.00'),  # 1% of basic salary
                'minimum_amount': Decimal('5000.00'),
                'maximum_amount': Decimal('50000.00'),
                'category': 'VOLUNTARY',
                'is_mandatory': False,
                'requires_employee_consent': True,
                'is_active': True,
            },
            
            # DISCIPLINARY AND PENALTIES
            {
                'name': 'Disciplinary Fine',
                'code': 'FINE',
                'description': 'Deduction for disciplinary infractions',
                'calculation_type': 'FIXED',
                'default_amount': Decimal('0.00'),
                'default_percentage': Decimal('0.00'),
                'minimum_amount': Decimal('0.00'),
                'maximum_amount': Decimal('200000.00'),  # UGX 200K max
                'category': 'PENALTY',
                'is_mandatory': False,
                'requires_employee_consent': False,  # Disciplinary action
                'is_active': True,
            },
            {
                'name': 'Lateness Penalty',
                'code': 'LATE',
                'description': 'Deduction for repeated lateness',
                'calculation_type': 'FIXED',
                'default_amount': Decimal('5000.00'),  # UGX 5K per incident
                'default_percentage': Decimal('0.00'),
                'minimum_amount': Decimal('1000.00'),
                'maximum_amount': Decimal('50000.00'),
                'category': 'PENALTY',
                'is_mandatory': False,
                'requires_employee_consent': False,
                'is_active': True,
            },
            {
                'name': 'Absence Without Leave',
                'code': 'AWOL',
                'description': 'Deduction for unauthorized absence',
                'calculation_type': 'PERCENTAGE_BASIC',
                'default_amount': Decimal('0.00'),
                'default_percentage': Decimal('100.00'),  # 100% of daily salary
                'minimum_amount': Decimal('0.00'),
                'maximum_amount': Decimal('0.00'),  # Based on daily rate
                'category': 'PENALTY',
                'is_mandatory': True,
                'requires_employee_consent': False,
                'is_active': True,
            },
            
            # UTILITIES AND SERVICES
            {
                'name': 'Staff Quarters Rent',
                'code': 'RENT',
                'description': 'Deduction for staff accommodation',
                'calculation_type': 'FIXED',
                'default_amount': Decimal('200000.00'),  # UGX 200K per month
                'default_percentage': Decimal('0.00'),
                'minimum_amount': Decimal('100000.00'),
                'maximum_amount': Decimal('500000.00'),
                'category': 'VOLUNTARY',
                'is_mandatory': False,
                'requires_employee_consent': True,
                'is_active': True,
            },
            {
                'name': 'Utilities (Water & Electricity)',
                'code': 'UTILS',
                'description': 'Staff quarters utility bills',
                'calculation_type': 'FIXED',
                'default_amount': Decimal('50000.00'),  # UGX 50K per month
                'default_percentage': Decimal('0.00'),
                'minimum_amount': Decimal('20000.00'),
                'maximum_amount': Decimal('150000.00'),
                'category': 'VOLUNTARY',
                'is_mandatory': False,
                'requires_employee_consent': True,
                'is_active': True,
            },
            {
                'name': 'Staff Canteen',
                'code': 'CANTEEN',
                'description': 'Staff meals and canteen services',
                'calculation_type': 'FIXED',
                'default_amount': Decimal('80000.00'),  # UGX 80K per month
                'default_percentage': Decimal('0.00'),
                'minimum_amount': Decimal('30000.00'),
                'maximum_amount': Decimal('150000.00'),
                'category': 'VOLUNTARY',
                'is_mandatory': False,
                'requires_employee_consent': True,
                'is_active': True,
            },
            
            # EQUIPMENT AND UNIFORMS
            {
                'name': 'Uniform Deduction',
                'code': 'UNIFDEDUCT',
                'description': 'Cost recovery for staff uniforms',
                'calculation_type': 'FIXED',
                'default_amount': Decimal('0.00'),
                'default_percentage': Decimal('0.00'),
                'minimum_amount': Decimal('0.00'),
                'maximum_amount': Decimal('100000.00'),
                'category': 'VOLUNTARY',
                'is_mandatory': False,
                'requires_employee_consent': True,
                'is_active': True,
            },
            {
                'name': 'Equipment Damage',
                'code': 'DAMAGE',
                'description': 'Cost recovery for damaged equipment',
                'calculation_type': 'FIXED',
                'default_amount': Decimal('0.00'),
                'default_percentage': Decimal('0.00'),
                'minimum_amount': Decimal('0.00'),
                'maximum_amount': Decimal('500000.00'),  # UGX 500K max
                'category': 'PENALTY',
                'is_mandatory': False,
                'requires_employee_consent': False,
                'is_active': True,
            },
            
            # MISCELLANEOUS
            {
                'name': 'Court Order/Garnishment',
                'code': 'COURT',
                'description': 'Court-ordered salary garnishment',
                'calculation_type': 'PERCENTAGE',
                'default_amount': Decimal('0.00'),
                'default_percentage': Decimal('25.00'),  # Max 25% of salary
                'minimum_amount': Decimal('0.00'),
                'maximum_amount': Decimal('0.00'),  # Court determined
                'category': 'STATUTORY',
                'is_mandatory': True,
                'requires_employee_consent': False,
                'is_active': True,
            },
            {
                'name': 'Overpayment Recovery',
                'code': 'OVERPAY',
                'description': 'Recovery of previous overpayments',
                'calculation_type': 'LOAN_INSTALLMENT',
                'default_amount': Decimal('0.00'),
                'default_percentage': Decimal('0.00'),
                'minimum_amount': Decimal('0.00'),
                'maximum_amount': Decimal('0.00'),  # Based on overpayment
                'category': 'OTHER',
                'is_mandatory': True,
                'requires_employee_consent': False,
                'is_active': True,
            },
            {
                'name': 'Charitable Donations',
                'code': 'CHARITY',
                'description': 'Voluntary charitable contributions',
                'calculation_type': 'FIXED',
                'default_amount': Decimal('10000.00'),  # UGX 10K per month
                'default_percentage': Decimal('0.00'),
                'minimum_amount': Decimal('5000.00'),
                'maximum_amount': Decimal('100000.00'),
                'category': 'VOLUNTARY',
                'is_mandatory': False,
                'requires_employee_consent': True,
                'is_active': True,
            }
        ]
    
    @classmethod
    def get_leave_types(cls):
        """Standard leave types for staff"""
        return [
            {'name': 'Annual Leave', 'code': 'ANNUAL', 'max_days_per_year': 21, 'min_days_notice': 7, 'is_paid': True, 'salary_percentage': 100, 'carries_forward': True, 'applicable_to_gender': 'ALL'},
            {'name': 'Sick Leave', 'code': 'SICK', 'max_days_per_year': 14, 'min_days_notice': 0, 'is_paid': True, 'salary_percentage': 100, 'carries_forward': True, 'applicable_to_gender': 'ALL'},
            {'name': 'Maternity Leave', 'code': 'MATERNITY', 'max_days_per_year': 84, 'min_days_notice': 14, 'is_paid': True, 'salary_percentage': 100, 'carries_forward': False, 'applicable_to_gender': 'FEMALE'},
            {'name': 'Paternity Leave', 'code': 'PATERNITY', 'max_days_per_year': 7, 'min_days_notice': 0, 'is_paid': True, 'salary_percentage': 100, 'carries_forward': False, 'applicable_to_gender': 'MALE'},
            {'name': 'Compassionate Leave', 'code': 'COMPASSIONATE', 'max_days_per_year': 5, 'min_days_notice': 0, 'is_paid': True, 'salary_percentage': 100, 'carries_forward': False, 'applicable_to_gender': 'ALL'},
            {'name': 'Study Leave', 'code': 'STUDY', 'max_days_per_year': 0, 'min_days_notice': 30, 'is_paid': False, 'salary_percentage': 0, 'carries_forward': False, 'applicable_to_gender': 'ALL'},
            {'name': 'Emergency Leave', 'code': 'EMERGENCY', 'max_days_per_year': 3, 'min_days_notice': 0, 'is_paid': True, 'salary_percentage': 100, 'carries_forward': False, 'applicable_to_gender': 'ALL'},
        ]
    
    @classmethod
    def get_account_types(cls):
        """Chart of accounts structure"""
        return [
            {'name': 'Assets', 'code': 'ASSETS', 'account_type': 'ASSET', 'number_prefix': '1', 'is_active': True},
            {'name': 'Liabilities', 'code': 'LIABILITIES', 'account_type': 'LIABILITY', 'number_prefix': '2', 'is_active': True},
            {'name': 'Equity', 'code': 'EQUITY', 'account_type': 'EQUITY', 'number_prefix': '3', 'is_active': True},
            {'name': 'Revenue', 'code': 'REVENUE', 'account_type': 'REVENUE', 'number_prefix': '4', 'is_active': True},
            {'name': 'Expenses', 'code': 'EXPENSES', 'account_type': 'EXPENSE', 'number_prefix': '5', 'is_active': True},
        ]
    
    @classmethod
    def get_basic_accounts(cls):
        """Complete essential accounts for comprehensive school financial management"""
        return [
            # ========================================
            # ASSETS (1000-1999)
            # ========================================
            
            # Current Assets - Cash and Equivalents (1000-1099)
            {
                'account_number': '1001', 
                'name': 'Cash in Hand', 
                'account_type_name': 'Assets', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_cash_account': True,
                'cash_location': 'Main Office',
                'is_active': True, 
                'description': 'Physical cash on school premises'
            },
            {
                'account_number': '1002', 
                'name': 'Bank Account - Main', 
                'account_type_name': 'Assets', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_bank_account': True,
                'bank_name': 'To be configured',
                'bank_account_type': 'CURRENT',
                'is_active': True, 
                'description': 'Primary bank account for school operations'
            },
            {
                'account_number': '1003', 
                'name': 'Bank Account - Savings', 
                'account_type_name': 'Assets', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_bank_account': True,
                'bank_name': 'To be configured',
                'bank_account_type': 'SAVINGS',
                'is_active': True, 
                'description': 'Savings account for reserves and long-term funds'
            },
            {
                'account_number': '1004', 
                'name': 'Mobile Money Account - MTN', 
                'account_type_name': 'Assets', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_mobile_money_account': True,
                'mobile_money_provider': 'MTN',
                'is_active': True, 
                'description': 'MTN Mobile Money wallet'
            },
            {
                'account_number': '1005', 
                'name': 'Mobile Money Account - Airtel', 
                'account_type_name': 'Assets', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_mobile_money_account': True,
                'mobile_money_provider': 'Airtel',
                'is_active': True, 
                'description': 'Airtel Money wallet'
            },
            {
                'account_number': '1006', 
                'name': 'Petty Cash Fund', 
                'account_type_name': 'Assets', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_cash_account': True,
                'cash_location': 'Administration Office',
                'is_active': True, 
                'description': 'Small cash fund for minor expenses'
            },

            # Receivables (1100-1199)
            {
                'account_number': '1100', 
                'name': 'Accounts Receivable - Students', 
                'account_type_name': 'Assets', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_receivable_account': True,
                'receivable_type': 'STUDENT',
                'is_active': True, 
                'description': 'Outstanding fees owed by students'
            },
            {
                'account_number': '1101', 
                'name': 'Accounts Receivable - Staff', 
                'account_type_name': 'Assets', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_receivable_account': True,
                'receivable_type': 'STAFF',
                'is_active': True, 
                'description': 'Money owed by staff (loans, advances, etc.)'
            },
            {
                'account_number': '1102', 
                'name': 'Accounts Receivable - Other', 
                'account_type_name': 'Assets', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_receivable_account': True,
                'receivable_type': 'OTHER',
                'is_active': True, 
                'description': 'Other receivables (government grants, donations pending, etc.)'
            },

            # Inventory (1200-1299)
            {
                'account_number': '1200', 
                'name': 'Inventory - Uniforms', 
                'account_type_name': 'Assets', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_inventory_account': True,
                'inventory_type': 'UNIFORMS',
                'is_active': True, 
                'description': 'School uniforms in stock for sale'
            },
            {
                'account_number': '1201', 
                'name': 'Inventory - Books and Stationery', 
                'account_type_name': 'Assets', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_inventory_account': True,
                'inventory_type': 'BOOKS_STATIONERY',
                'is_active': True, 
                'description': 'Books, notebooks, and stationery for sale'
            },
            {
                'account_number': '1202', 
                'name': 'Inventory - Food and Provisions', 
                'account_type_name': 'Assets', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_inventory_account': True,
                'inventory_type': 'FOOD_PROVISIONS',
                'is_active': True, 
                'description': 'Food items and provisions for school meals'
            },
            {
                'account_number': '1203', 
                'name': 'Inventory - Medical Supplies', 
                'account_type_name': 'Assets', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_inventory_account': True,
                'inventory_type': 'MEDICAL',
                'is_active': True, 
                'description': 'Medical supplies and first aid items'
            },

            # Fixed Assets (1500-1699)
            {
                'account_number': '1500', 
                'name': 'Land and Buildings', 
                'account_type_name': 'Assets', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_fixed_asset': True,
                'asset_type': 'REAL_ESTATE',
                'is_active': True, 
                'description': 'School land, buildings, and permanent structures'
            },
            {
                'account_number': '1501', 
                'name': 'Furniture and Equipment', 
                'account_type_name': 'Assets', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_fixed_asset': True,
                'asset_type': 'FURNITURE_EQUIPMENT',
                'is_active': True, 
                'description': 'Desks, chairs, equipment, and furniture'
            },
            {
                'account_number': '1502', 
                'name': 'Vehicles', 
                'account_type_name': 'Assets', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_fixed_asset': True,
                'asset_type': 'VEHICLES',
                'is_active': True, 
                'description': 'School buses, cars, and other vehicles'
            },
            {
                'account_number': '1503', 
                'name': 'Computer Equipment', 
                'account_type_name': 'Assets', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_fixed_asset': True,
                'asset_type': 'COMPUTER_EQUIPMENT',
                'is_active': True, 
                'description': 'Computers, laptops, printers, and IT equipment'
            },

            # ========================================
            # LIABILITIES (2000-2999)
            # ========================================
            
            # Current Liabilities (2000-2199)
            {
                'account_number': '2001', 
                'name': 'Accounts Payable - Suppliers', 
                'account_type_name': 'Liabilities', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_payable_account': True,
                'payable_type': 'SUPPLIERS',
                'is_active': True, 
                'description': 'Money owed to suppliers and vendors'
            },
            {
                'account_number': '2002', 
                'name': 'Salaries and Wages Payable', 
                'account_type_name': 'Liabilities', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_payable_account': True,
                'payable_type': 'STAFF_COMPENSATION',
                'is_active': True, 
                'description': 'Unpaid salaries, wages, and staff benefits'
            },
            {
                'account_number': '2003', 
                'name': 'Taxes Payable', 
                'account_type_name': 'Liabilities', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_payable_account': True,
                'payable_type': 'TAXES',
                'is_active': True, 
                'description': 'VAT, PAYE, and other taxes owed to government'
            },
            {
                'account_number': '2004', 
                'name': 'Student Deposits and Prepayments', 
                'account_type_name': 'Liabilities', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_liability_account': True,
                'liability_type': 'STUDENT_DEPOSITS',
                'is_active': True, 
                'description': 'Security deposits and advance payments from students'
            },
            {
                'account_number': '2005', 
                'name': 'Utilities Payable', 
                'account_type_name': 'Liabilities', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_payable_account': True,
                'payable_type': 'UTILITIES',
                'is_active': True, 
                'description': 'Electricity, water, internet, and other utility bills'
            },

            # Long-term Liabilities (2200-2299)
            {
                'account_number': '2200', 
                'name': 'Bank Loans', 
                'account_type_name': 'Liabilities', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_loan_account': True,
                'loan_type': 'BANK_LOAN',
                'is_active': True, 
                'description': 'Long-term loans from banks and financial institutions'
            },
            {
                'account_number': '2201', 
                'name': 'Equipment Financing', 
                'account_type_name': 'Liabilities', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_loan_account': True,
                'loan_type': 'EQUIPMENT_FINANCING',
                'is_active': True, 
                'description': 'Financing for equipment purchases'
            },

            # ========================================
            # EQUITY (3000-3999)
            # ========================================
            
            {
                'account_number': '3001', 
                'name': 'Retained Earnings', 
                'account_type_name': 'Equity', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_equity_account': True,
                'equity_type': 'RETAINED_EARNINGS',
                'is_active': True, 
                'description': 'Accumulated profits/losses from previous years'
            },
            {
                'account_number': '3002', 
                'name': 'Capital Fund', 
                'account_type_name': 'Equity', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_equity_account': True,
                'equity_type': 'CAPITAL',
                'is_active': True, 
                'description': 'Capital contributions and initial funding'
            },
            {
                'account_number': '3003', 
                'name': 'Development Fund', 
                'account_type_name': 'Equity', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_equity_account': True,
                'equity_type': 'DEVELOPMENT_FUND',
                'is_active': True, 
                'description': 'Funds designated for school development projects'
            },

            # ========================================
            # REVENUE (4000-4999)
            # ========================================
            
            # Educational Revenue (4000-4099)
            {
                'account_number': '4001', 
                'name': 'Tuition and Academic Fees', 
                'account_type_name': 'Revenue', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_revenue_account': True,
                'revenue_type': 'TUITION',
                'is_active': True, 
                'description': 'Revenue from tuition, admission, examination, and academic fees'
            },
            {
                'account_number': '4002', 
                'name': 'Boarding and Accommodation Fees', 
                'account_type_name': 'Revenue', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_revenue_account': True,
                'revenue_type': 'BOARDING',
                'is_active': True, 
                'description': 'Revenue from boarding, accommodation, and meal services'
            },
            {
                'account_number': '4003', 
                'name': 'Transport Fees', 
                'account_type_name': 'Revenue', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_revenue_account': True,
                'revenue_type': 'TRANSPORT',
                'is_active': True, 
                'description': 'Revenue from school bus and transport services'
            },
            {
                'account_number': '4004', 
                'name': 'Activities and Sports Fees', 
                'account_type_name': 'Revenue', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_revenue_account': True,
                'revenue_type': 'ACTIVITIES_SPORTS',
                'is_active': True, 
                'description': 'Revenue from extracurricular activities, sports, and events'
            },

            # Retail and Other Revenue (4100-4199)
            {
                'account_number': '4100', 
                'name': 'Uniform Sales Revenue', 
                'account_type_name': 'Revenue', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_revenue_account': True,
                'revenue_type': 'UNIFORM_SALES',
                'is_active': True, 
                'description': 'Revenue from school uniform sales'
            },
            {
                'account_number': '4101', 
                'name': 'Books and Stationery Sales', 
                'account_type_name': 'Revenue', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_revenue_account': True,
                'revenue_type': 'BOOKS_STATIONERY_SALES',
                'is_active': True, 
                'description': 'Revenue from textbooks, notebooks, and stationery sales'
            },
            {
                'account_number': '4102', 
                'name': 'Other School Fees', 
                'account_type_name': 'Revenue', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_revenue_account': True,
                'revenue_type': 'OTHER_FEES',
                'is_active': True, 
                'description': 'Medical fees, graduation fees, and miscellaneous charges'
            },

            # External Revenue (4200-4299)
            {
                'account_number': '4200', 
                'name': 'Government Grants', 
                'account_type_name': 'Revenue', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_revenue_account': True,
                'revenue_type': 'GOVERNMENT_GRANTS',
                'is_active': True, 
                'description': 'Grants and funding from government agencies'
            },
            {
                'account_number': '4201', 
                'name': 'Donations and Gifts', 
                'account_type_name': 'Revenue', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_revenue_account': True,
                'revenue_type': 'DONATIONS',
                'is_active': True, 
                'description': 'Donations from parents, alumni, and benefactors'
            },
            {
                'account_number': '4202', 
                'name': 'Interest Income', 
                'account_type_name': 'Revenue', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_revenue_account': True,
                'revenue_type': 'INTEREST_INCOME',
                'is_active': True, 
                'description': 'Interest earned on bank deposits and investments'
            },

            # ========================================
            # EXPENSES (5000-6999)
            # ========================================
            
            # Staff Costs (5000-5099)
            {
                'account_number': '5001', 
                'name': 'Teaching Staff Salaries', 
                'account_type_name': 'Expenses', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_expense_account': True,
                'expense_type': 'TEACHING_SALARIES',
                'is_active': True, 
                'description': 'Salaries and wages for teaching staff'
            },
            {
                'account_number': '5002', 
                'name': 'Administrative Staff Salaries', 
                'account_type_name': 'Expenses', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_expense_account': True,
                'expense_type': 'ADMIN_SALARIES',
                'is_active': True, 
                'description': 'Salaries for administrative and support staff'
            },
            {
                'account_number': '5003', 
                'name': 'Staff Benefits and Allowances', 
                'account_type_name': 'Expenses', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_expense_account': True,
                'expense_type': 'STAFF_BENEFITS',
                'is_active': True, 
                'description': 'Medical insurance, transport allowances, and other benefits'
            },

            # Operational Expenses (5100-5199)
            {
                'account_number': '5100', 
                'name': 'Utilities Expense', 
                'account_type_name': 'Expenses', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_expense_account': True,
                'expense_type': 'UTILITIES',
                'is_active': True, 
                'description': 'Electricity, water, internet, and telephone expenses'
            },
            {
                'account_number': '5101', 
                'name': 'Maintenance and Repairs', 
                'account_type_name': 'Expenses', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_expense_account': True,
                'expense_type': 'MAINTENANCE_REPAIRS',
                'is_active': True, 
                'description': 'Building maintenance, equipment repairs, and renovations'
            },
            {
                'account_number': '5102', 
                'name': 'Security Services', 
                'account_type_name': 'Expenses', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_expense_account': True,
                'expense_type': 'SECURITY',
                'is_active': True, 
                'description': 'Security guard services and security equipment'
            },
            {
                'account_number': '5103', 
                'name': 'Cleaning and Sanitation', 
                'account_type_name': 'Expenses', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_expense_account': True,
                'expense_type': 'CLEANING_SANITATION',
                'is_active': True, 
                'description': 'Cleaning supplies, detergents, and sanitation services'
            },

            # Academic Expenses (5200-5299)
            {
                'account_number': '5200', 
                'name': 'Teaching Materials and Supplies', 
                'account_type_name': 'Expenses', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_expense_account': True,
                'expense_type': 'TEACHING_MATERIALS',
                'is_active': True, 
                'description': 'Textbooks, teaching aids, laboratory supplies, and educational materials'
            },
            {
                'account_number': '5201', 
                'name': 'Library and Reference Materials', 
                'account_type_name': 'Expenses', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_expense_account': True,
                'expense_type': 'LIBRARY_MATERIALS',
                'is_active': True, 
                'description': 'Library books, journals, and reference materials'
            },
            {
                'account_number': '5202', 
                'name': 'Computer and IT Expenses', 
                'account_type_name': 'Expenses', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_expense_account': True,
                'expense_type': 'IT_EXPENSES',
                'is_active': True, 
                'description': 'Software licenses, IT support, and computer maintenance'
            },

            # Food and Boarding Expenses (5300-5399)
            {
                'account_number': '5300', 
                'name': 'Food and Catering', 
                'account_type_name': 'Expenses', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_expense_account': True,
                'expense_type': 'FOOD_CATERING',
                'is_active': True, 
                'description': 'Food purchases, meal preparation, and catering services'
            },
            {
                'account_number': '5301', 
                'name': 'Boarding Supplies', 
                'account_type_name': 'Expenses', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_expense_account': True,
                'expense_type': 'BOARDING_SUPPLIES',
                'is_active': True, 
                'description': 'Bedding, toiletries, and other boarding necessities'
            },

            # Transport Expenses (5400-5499)
            {
                'account_number': '5400', 
                'name': 'Vehicle Fuel and Maintenance', 
                'account_type_name': 'Expenses', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_expense_account': True,
                'expense_type': 'VEHICLE_EXPENSES',
                'is_active': True, 
                'description': 'Fuel, maintenance, and repairs for school vehicles'
            },
            {
                'account_number': '5401', 
                'name': 'Transport Services', 
                'account_type_name': 'Expenses', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_expense_account': True,
                'expense_type': 'TRANSPORT_SERVICES',
                'is_active': True, 
                'description': 'Hired transport services and driver allowances'
            },

            # Administrative Expenses (5500-5599)
            {
                'account_number': '5500', 
                'name': 'Office Supplies and Stationery', 
                'account_type_name': 'Expenses', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_expense_account': True,
                'expense_type': 'OFFICE_SUPPLIES',
                'is_active': True, 
                'description': 'Office supplies, printing, and administrative stationery'
            },
            {
                'account_number': '5501', 
                'name': 'Communication Expenses', 
                'account_type_name': 'Expenses', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_expense_account': True,
                'expense_type': 'COMMUNICATION',
                'is_active': True, 
                'description': 'Postage, courier services, and communication costs'
            },
            {
                'account_number': '5502', 
                'name': 'Legal and Professional Fees', 
                'account_type_name': 'Expenses', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_expense_account': True,
                'expense_type': 'PROFESSIONAL_FEES',
                'is_active': True, 
                'description': 'Legal fees, audit fees, and professional consultancy'
            },
            {
                'account_number': '5503', 
                'name': 'Insurance Premiums', 
                'account_type_name': 'Expenses', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_expense_account': True,
                'expense_type': 'INSURANCE',
                'is_active': True, 
                'description': 'Property, vehicle, and liability insurance premiums'
            },

            # Financial Expenses (5600-5699)
            {
                'account_number': '5600', 
                'name': 'Bank Charges and Fees', 
                'account_type_name': 'Expenses', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_expense_account': True,
                'expense_type': 'BANK_CHARGES',
                'is_active': True, 
                'description': 'Bank transaction fees, account maintenance charges'
            },
            {
                'account_number': '5601', 
                'name': 'Interest Expense', 
                'account_type_name': 'Expenses', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_expense_account': True,
                'expense_type': 'INTEREST_EXPENSE',
                'is_active': True, 
                'description': 'Interest paid on loans and financing'
            },

            # Other Expenses (5700-5799)
            {
                'account_number': '5700', 
                'name': 'Bad Debt Expense', 
                'account_type_name': 'Expenses', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_expense_account': True,
                'expense_type': 'BAD_DEBT',
                'is_active': True, 
                'description': 'Uncollectible student fees and accounts'
            },
            {
                'account_number': '5701', 
                'name': 'Depreciation Expense', 
                'account_type_name': 'Expenses', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_expense_account': True,
                'expense_type': 'DEPRECIATION',
                'is_active': True, 
                'description': 'Depreciation of fixed assets and equipment'
            },
            {
                'account_number': '5702', 
                'name': 'Miscellaneous Expenses', 
                'account_type_name': 'Expenses', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_expense_account': True,
                'expense_type': 'MISCELLANEOUS',
                'is_active': True, 
                'description': 'Other general expenses not classified elsewhere'
            },

            # Scholarship and Financial Aid (5800-5899)
            {
                'account_number': '5800', 
                'name': 'Scholarship and Financial Aid', 
                'account_type_name': 'Expenses', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_expense_account': True,
                'expense_type': 'SCHOLARSHIP',
                'is_active': True, 
                'description': 'Scholarships and financial aid given to students'
            },
            {
                'account_number': '5801', 
                'name': 'Bursaries and Grants', 
                'account_type_name': 'Expenses', 
                'opening_balance': Decimal('0.00'),
                'current_balance': Decimal('0.00'),
                'is_expense_account': True,
                'expense_type': 'BURSARY',
                'is_active': True, 
                'description': 'Need-based bursaries and grants to students'
            }
        ]
    
    @classmethod
    def get_display_groups(cls):
        """Comprehensive fee display groups for all school types"""
        return [
            {'name': 'Tuition & Academic Fees', 'description': 'Core academic fees and tuition', 'display_order': 1, 'is_active': True, 'color_code': '#2E86AB'},
            {'name': 'Registration & Admission', 'description': 'One-time enrollment and admission fees', 'display_order': 2, 'is_active': True, 'color_code': '#A23B72'},
            {'name': 'Boarding & Accommodation', 'description': 'Boarding fees and accommodation costs', 'display_order': 3, 'is_active': True, 'color_code': '#F18F01'},
            {'name': 'Meals & Catering', 'description': 'Food and catering services', 'display_order': 4, 'is_active': True, 'color_code': '#C73E1D'},
            {'name': 'Activities & Services', 'description': 'Extracurricular and support services', 'display_order': 5, 'is_active': True, 'color_code': '#7209B7'},
            {'name': 'Transport & Travel', 'description': 'Transportation and travel costs', 'display_order': 6, 'is_active': True, 'color_code': '#560BAD'},
            {'name': 'Technology & Equipment', 'description': 'IT services and equipment fees', 'display_order': 7, 'is_active': True, 'color_code': '#264653'},
            {'name': 'Medical & Health', 'description': 'Health services and medical fees', 'display_order': 8, 'is_active': True, 'color_code': '#2A9D8F'},
            {'name': 'Uniform & Supplies', 'description': 'School uniforms and supplies', 'display_order': 9, 'is_active': True, 'color_code': '#E76F51'},
            {'name': 'Special Programs', 'description': 'Specialized courses and programs', 'display_order': 10, 'is_active': True, 'color_code': '#F4A261'},
            {'name': 'Penalties & Adjustments', 'description': 'Late fees, penalties, and adjustments', 'display_order': 11, 'is_active': True, 'color_code': '#E63946'},
        ]

    @classmethod
    def get_fee_categories(cls):
        """Comprehensive fee categories - FIXED VERSION"""
        return [
            # TUITION & ACADEMIC FEES
            {'name': 'Tuition Fee', 'code': 'TUITION', 'frequency': 'TERMLY', 'applicability': 'ALL', 'is_mandatory': True, 'allows_partial_payment': True, 'display_group': 'Tuition & Academic Fees', 'description': 'Core academic fees and instruction'},
            {'name': 'Academic Enhancement Fee', 'code': 'ACADEMIC_ENH', 'frequency': 'TERMLY', 'applicability': 'ALL', 'is_mandatory': False, 'allows_partial_payment': True, 'display_group': 'Tuition & Academic Fees', 'description': 'Additional academic support and resources'},
            {'name': 'Examination Fee', 'code': 'EXAM', 'frequency': 'TERMLY', 'applicability': 'ALL', 'is_mandatory': True, 'allows_partial_payment': True, 'display_group': 'Tuition & Academic Fees', 'description': 'Internal and external examination fees'},
            {'name': 'Development Fee', 'code': 'DEV', 'frequency': 'YEARLY', 'applicability': 'ALL', 'is_mandatory': True, 'allows_partial_payment': True, 'display_group': 'Tuition & Academic Fees', 'description': 'School development and improvement projects'},
            {'name': 'Laboratory Fee', 'code': 'LAB', 'frequency': 'TERMLY', 'applicability': 'SCIENCE_STUDENTS', 'is_mandatory': True, 'allows_partial_payment': True, 'display_group': 'Tuition & Academic Fees', 'description': 'Science laboratory usage and materials'},

            # REGISTRATION & ADMISSION
            {'name': 'Registration Fee', 'code': 'REG', 'frequency': 'ONE_TIME', 'applicability': 'NEW_STUDENTS', 'is_mandatory': True, 'allows_partial_payment': False, 'display_group': 'Registration & Admission', 'description': 'One-time registration for new students'},
            {'name': 'Admission Fee', 'code': 'ADMISSION', 'frequency': 'ONE_TIME', 'applicability': 'NEW_STUDENTS', 'is_mandatory': True, 'allows_partial_payment': False, 'display_group': 'Registration & Admission', 'description': 'School admission processing fee'},
            {'name': 'Application Fee', 'code': 'APPLICATION', 'frequency': 'ONE_TIME', 'applicability': 'APPLICANTS', 'is_mandatory': True, 'allows_partial_payment': False, 'display_group': 'Registration & Admission', 'description': 'Application processing fee'},

            # BOARDING & ACCOMMODATION
            {'name': 'Boarding Fee', 'code': 'BOARD', 'frequency': 'TERMLY', 'applicability': 'BOARDERS', 'is_mandatory': True, 'allows_partial_payment': True, 'display_group': 'Boarding & Accommodation', 'description': 'Boarding accommodation and supervision'},
            {'name': 'Accommodation Deposit', 'code': 'ACCOM_DEPOSIT', 'frequency': 'ONE_TIME', 'applicability': 'BOARDERS', 'is_mandatory': True, 'allows_partial_payment': False, 'display_group': 'Boarding & Accommodation', 'description': 'Refundable accommodation security deposit'},

            # MEALS & CATERING
            {'name': 'Meals Fee', 'code': 'MEALS', 'frequency': 'TERMLY', 'applicability': 'BOARDERS', 'is_mandatory': True, 'allows_partial_payment': True, 'display_group': 'Meals & Catering', 'description': 'Full board meal service'},
            {'name': 'Day Scholar Meals', 'code': 'DAY_MEALS', 'frequency': 'TERMLY', 'applicability': 'DAY_SCHOLARS', 'is_mandatory': False, 'allows_partial_payment': True, 'display_group': 'Meals & Catering', 'description': 'Optional lunch service for day students'},

            # ACTIVITIES & SERVICES
            {'name': 'Library Fee', 'code': 'LIB', 'frequency': 'YEARLY', 'applicability': 'ALL', 'is_mandatory': True, 'allows_partial_payment': True, 'display_group': 'Activities & Services', 'description': 'Library services and resources'},
            {'name': 'Sports Fee', 'code': 'SPORTS', 'frequency': 'YEARLY', 'applicability': 'ALL', 'is_mandatory': False, 'allows_partial_payment': True, 'display_group': 'Activities & Services', 'description': 'Sports equipment and activities'},
            {'name': 'Student ID Card', 'code': 'ID_CARD', 'frequency': 'YEARLY', 'applicability': 'ALL', 'is_mandatory': True, 'allows_partial_payment': False, 'display_group': 'Activities & Services', 'description': 'Student identification card'},

            # TRANSPORT & TRAVEL
            {'name': 'Transport Fee', 'code': 'TRANS', 'frequency': 'TERMLY', 'applicability': 'TRANSPORT_USERS', 'is_mandatory': False, 'allows_partial_payment': True, 'display_group': 'Transport & Travel', 'description': 'School bus transportation service'},
            {'name': 'Field Trip Fee', 'code': 'FIELD_TRIP', 'frequency': 'TERMLY', 'applicability': 'PARTICIPANTS', 'is_mandatory': False, 'allows_partial_payment': True, 'display_group': 'Transport & Travel', 'description': 'Educational field trips and excursions'},

            # TECHNOLOGY & EQUIPMENT
            {'name': 'Computer Fee', 'code': 'COMPUTER', 'frequency': 'TERMLY', 'applicability': 'ICT_STUDENTS', 'is_mandatory': True, 'allows_partial_payment': True, 'display_group': 'Technology & Equipment', 'description': 'Computer lab usage and maintenance'},
            {'name': 'Internet & WiFi Fee', 'code': 'INTERNET', 'frequency': 'TERMLY', 'applicability': 'ALL', 'is_mandatory': False, 'allows_partial_payment': True, 'display_group': 'Technology & Equipment', 'description': 'Internet access and connectivity'},

            # MEDICAL & HEALTH
            {'name': 'Medical Fee', 'code': 'MED', 'frequency': 'YEARLY', 'applicability': 'ALL', 'is_mandatory': False, 'allows_partial_payment': True, 'display_group': 'Medical & Health', 'description': 'Basic medical services and first aid'},
            {'name': 'Health Insurance', 'code': 'HEALTH_INS', 'frequency': 'YEARLY', 'applicability': 'ALL', 'is_mandatory': False, 'allows_partial_payment': True, 'display_group': 'Medical & Health', 'description': 'Student health insurance coverage'},

            # UNIFORM & SUPPLIES
            {'name': 'School Uniform', 'code': 'UNIFORM', 'frequency': 'YEARLY', 'applicability': 'ALL', 'is_mandatory': True, 'allows_partial_payment': True, 'display_group': 'Uniform & Supplies', 'description': 'Official school uniform'},
            {'name': 'Textbooks', 'code': 'TEXTBOOKS', 'frequency': 'YEARLY', 'applicability': 'ALL', 'is_mandatory': False, 'allows_partial_payment': True, 'display_group': 'Uniform & Supplies', 'description': 'Required textbooks and learning materials'},

            # PENALTIES & ADJUSTMENTS
            {'name': 'Late Payment Penalty', 'code': 'LATE_PENALTY', 'frequency': 'MONTHLY', 'applicability': 'DEFAULTERS', 'is_mandatory': True, 'allows_partial_payment': False, 'display_group': 'Penalties & Adjustments', 'description': 'Late payment penalty charges'},
            {'name': 'Replacement Fee', 'code': 'REPLACEMENT', 'frequency': 'PER_INCIDENT', 'applicability': 'ALL', 'is_mandatory': True, 'allows_partial_payment': False, 'display_group': 'Penalties & Adjustments', 'description': 'Lost or damaged item replacement'},
        ]

    @classmethod
    def get_expense_categories(cls):
        """Comprehensive expense categories mapped to the ExpenseCategory model structure"""
        return [
            # ADMINISTRATIVE
            {'name': 'Office Supplies', 'category_type': 'ADMINISTRATIVE', 'description': 'Office supplies and admin expenses', 'requires_approval': True, 'approval_limit': 50000, 'is_active': True},
            {'name': 'Legal & Professional Fees', 'category_type': 'ADMINISTRATIVE', 'description': 'Lawyers, auditors, consultants', 'requires_approval': True, 'approval_limit': 100000, 'is_active': True},
            {'name': 'Licenses & Permits', 'category_type': 'ADMINISTRATIVE', 'description': 'Government licenses and permits', 'requires_approval': True, 'approval_limit': 200000, 'is_active': True},
            {'name': 'Bank Charges', 'category_type': 'ADMINISTRATIVE', 'description': 'Banking fees and charges', 'requires_approval': False, 'approval_limit': None, 'is_active': True},
            {'name': 'Postage & Courier', 'category_type': 'ADMINISTRATIVE', 'description': 'Mail and delivery services', 'requires_approval': False, 'approval_limit': 20000, 'is_active': True},

            # ACADEMIC
            {'name': 'Curriculum Development', 'category_type': 'ACADEMIC', 'description': 'Curriculum design and development', 'requires_approval': True, 'approval_limit': 300000, 'is_active': True},
            {'name': 'Teacher Training', 'category_type': 'ACADEMIC', 'description': 'Professional development programs', 'requires_approval': True, 'approval_limit': 500000, 'is_active': True},
            {'name': 'Educational Consultancy', 'category_type': 'ACADEMIC', 'description': 'External educational consultants', 'requires_approval': True, 'approval_limit': 200000, 'is_active': True},

            # SCHOLASTIC
            {'name': 'Learning Materials', 'category_type': 'SCHOLASTIC', 'description': 'Books, stationery, teaching aids', 'requires_approval': True, 'approval_limit': 100000, 'is_active': True},
            {'name': 'Library Resources', 'category_type': 'SCHOLASTIC', 'description': 'Books, journals, digital resources', 'requires_approval': True, 'approval_limit': 150000, 'is_active': True},
            {'name': 'Laboratory Supplies', 'category_type': 'SCHOLASTIC', 'description': 'Science lab chemicals and equipment', 'requires_approval': True, 'approval_limit': 200000, 'is_active': True},
            {'name': 'Art & Craft Supplies', 'category_type': 'SCHOLASTIC', 'description': 'Art materials and craft supplies', 'requires_approval': True, 'approval_limit': 80000, 'is_active': True},

            # EXAMINATION
            {'name': 'Examination Materials', 'category_type': 'EXAMINATION', 'description': 'Question papers, answer sheets, printing', 'requires_approval': True, 'approval_limit': 100000, 'is_active': True},
            {'name': 'External Examination Fees', 'category_type': 'EXAMINATION', 'description': 'UNEB, Cambridge, other exam bodies', 'requires_approval': True, 'approval_limit': 500000, 'is_active': True},
            {'name': 'Invigilation Costs', 'category_type': 'EXAMINATION', 'description': 'External invigilators and supervision', 'requires_approval': True, 'approval_limit': 150000, 'is_active': True},

            # FACILITIES
            {'name': 'Maintenance & Repairs', 'category_type': 'FACILITIES', 'description': 'Building and equipment maintenance', 'requires_approval': True, 'approval_limit': 300000, 'is_active': True},
            {'name': 'Cleaning Supplies', 'category_type': 'FACILITIES', 'description': 'Cleaning materials and equipment', 'requires_approval': True, 'approval_limit': 50000, 'is_active': True},
            {'name': 'Security Services', 'category_type': 'FACILITIES', 'description': 'Security guards and surveillance', 'requires_approval': True, 'approval_limit': 200000, 'is_active': True},
            {'name': 'Groundskeeping', 'category_type': 'FACILITIES', 'description': 'Landscaping and ground maintenance', 'requires_approval': True, 'approval_limit': 100000, 'is_active': True},

            # CAPITAL
            {'name': 'Land & Buildings', 'category_type': 'CAPITAL', 'description': 'Purchase of land and building construction', 'requires_approval': True, 'approval_limit': 10000000, 'is_active': True},
            {'name': 'Building Improvements', 'category_type': 'CAPITAL', 'description': 'Major renovations and improvements', 'requires_approval': True, 'approval_limit': 5000000, 'is_active': True},
            {'name': 'Furniture & Fixtures', 'category_type': 'CAPITAL', 'description': 'Desks, chairs, classroom furniture', 'requires_approval': True, 'approval_limit': 1000000, 'is_active': True},
            {'name': 'Vehicles', 'category_type': 'CAPITAL', 'description': 'Purchase of school vehicles', 'requires_approval': True, 'approval_limit': 5000000, 'is_active': True},
            {'name': 'Laboratory Equipment', 'category_type': 'CAPITAL', 'description': 'Major lab equipment and machinery', 'requires_approval': True, 'approval_limit': 2000000, 'is_active': True},

            # UTILITIES
            {'name': 'Electricity', 'category_type': 'UTILITIES', 'description': 'Monthly electricity bills', 'requires_approval': True, 'approval_limit': 500000, 'is_active': True},
            {'name': 'Water & Sewerage', 'category_type': 'UTILITIES', 'description': 'Water and sewerage bills', 'requires_approval': True, 'approval_limit': 200000, 'is_active': True},
            {'name': 'Internet & Phone', 'category_type': 'UTILITIES', 'description': 'Internet, telephone, and communication', 'requires_approval': True, 'approval_limit': 300000, 'is_active': True},
            {'name': 'Gas & Fuel', 'category_type': 'UTILITIES', 'description': 'Cooking gas and generator fuel', 'requires_approval': True, 'approval_limit': 400000, 'is_active': True},

            # TRANSPORT
            {'name': 'School Vehicles', 'category_type': 'TRANSPORT', 'description': 'School bus operations and maintenance', 'requires_approval': True, 'approval_limit': 300000, 'is_active': True},
            {'name': 'Fuel Costs', 'category_type': 'TRANSPORT', 'description': 'Fuel for school vehicles', 'requires_approval': True, 'approval_limit': 500000, 'is_active': True},
            {'name': 'Official Travel', 'category_type': 'TRANSPORT', 'description': 'Staff official travel expenses', 'requires_approval': True, 'approval_limit': 200000, 'is_active': True},

            # MEALS
            {'name': 'Food & Beverages', 'category_type': 'MEALS', 'description': 'Raw food materials and beverages', 'requires_approval': True, 'approval_limit': 1000000, 'is_active': True},
            {'name': 'Kitchen Supplies', 'category_type': 'MEALS', 'description': 'Cooking equipment and utensils', 'requires_approval': True, 'approval_limit': 200000, 'is_active': True},
            {'name': 'Catering Services', 'category_type': 'MEALS', 'description': 'External catering for events', 'requires_approval': True, 'approval_limit': 300000, 'is_active': True},

            # STAFF
            {'name': 'Staff Salaries', 'category_type': 'STAFF', 'description': 'Monthly staff salaries and wages', 'requires_approval': True, 'approval_limit': 20000000, 'is_active': True},
            {'name': 'Staff Benefits', 'category_type': 'STAFF', 'description': 'Medical insurance, pension, allowances', 'requires_approval': True, 'approval_limit': 2000000, 'is_active': True},
            {'name': 'Temporary Staff', 'category_type': 'STAFF', 'description': 'Substitute teachers, casual workers', 'requires_approval': True, 'approval_limit': 500000, 'is_active': True},
            {'name': 'Staff Training', 'category_type': 'STAFF', 'description': 'Professional development and training', 'requires_approval': True, 'approval_limit': 1000000, 'is_active': True},

            # MEDICAL
            {'name': 'Health Services', 'category_type': 'MEDICAL', 'description': 'Clinic operations and medical staff', 'requires_approval': True, 'approval_limit': 300000, 'is_active': True},
            {'name': 'Medical Supplies', 'category_type': 'MEDICAL', 'description': 'Medicines and medical equipment', 'requires_approval': True, 'approval_limit': 200000, 'is_active': True},
            {'name': 'First Aid Supplies', 'category_type': 'MEDICAL', 'description': 'Basic medical and first aid supplies', 'requires_approval': False, 'approval_limit': 50000, 'is_active': True},
            {'name': 'Health Insurance', 'category_type': 'MEDICAL', 'description': 'Student and staff health insurance', 'requires_approval': True, 'approval_limit': 1000000, 'is_active': True},

            # SPORTS
            {'name': 'Sports Equipment', 'category_type': 'SPORTS', 'description': 'Sports equipment and gear', 'requires_approval': True, 'approval_limit': 300000, 'is_active': True},
            {'name': 'Sports Competitions', 'category_type': 'SPORTS', 'description': 'Inter-school competitions and tournaments', 'requires_approval': True, 'approval_limit': 500000, 'is_active': True},
            {'name': 'Music & Drama', 'category_type': 'SPORTS', 'description': 'Musical instruments and drama supplies', 'requires_approval': True, 'approval_limit': 400000, 'is_active': True},
            {'name': 'School Events', 'category_type': 'SPORTS', 'description': 'School functions and celebrations', 'requires_approval': True, 'approval_limit': 600000, 'is_active': True},

            # STUDENT_SERVICES
            {'name': 'Student Welfare', 'category_type': 'STUDENT_SERVICES', 'description': 'Student counseling and welfare services', 'requires_approval': True, 'approval_limit': 200000, 'is_active': True},
            {'name': 'Student Activities', 'category_type': 'STUDENT_SERVICES', 'description': 'Student clubs and activities', 'requires_approval': True, 'approval_limit': 300000, 'is_active': True},
            {'name': 'Guidance & Counseling', 'category_type': 'STUDENT_SERVICES', 'description': 'Professional counseling services', 'requires_approval': True, 'approval_limit': 400000, 'is_active': True},

            # PTA
            {'name': 'PTA Activities', 'category_type': 'PTA', 'description': 'Parent-Teacher Association activities', 'requires_approval': True, 'approval_limit': 200000, 'is_active': True},
            {'name': 'Parent Engagement', 'category_type': 'PTA', 'description': 'Parent meetings and engagement programs', 'requires_approval': True, 'approval_limit': 150000, 'is_active': True},

            # MARKETING
            {'name': 'Advertising', 'category_type': 'MARKETING', 'description': 'Print, radio, TV, and online advertising', 'requires_approval': True, 'approval_limit': 500000, 'is_active': True},
            {'name': 'Website & Digital Marketing', 'category_type': 'MARKETING', 'description': 'Website maintenance and online marketing', 'requires_approval': True, 'approval_limit': 200000, 'is_active': True},
            {'name': 'Public Relations', 'category_type': 'MARKETING', 'description': 'PR activities and community engagement', 'requires_approval': True, 'approval_limit': 300000, 'is_active': True},
            {'name': 'Promotional Materials', 'category_type': 'MARKETING', 'description': 'Brochures, banners, promotional items', 'requires_approval': True, 'approval_limit': 150000, 'is_active': True},

            # TECHNOLOGY
            {'name': 'Hardware', 'category_type': 'TECHNOLOGY', 'description': 'Computer equipment and hardware', 'requires_approval': True, 'approval_limit': 1000000, 'is_active': True},
            {'name': 'Software & Licenses', 'category_type': 'TECHNOLOGY', 'description': 'Software licenses and subscriptions', 'requires_approval': True, 'approval_limit': 500000, 'is_active': True},
            {'name': 'IT Maintenance', 'category_type': 'TECHNOLOGY', 'description': 'IT support and equipment maintenance', 'requires_approval': True, 'approval_limit': 300000, 'is_active': True},
            {'name': 'Internet & Connectivity', 'category_type': 'TECHNOLOGY', 'description': 'Internet services and connectivity', 'requires_approval': True, 'approval_limit': 400000, 'is_active': True},

            # LEGAL
            {'name': 'Legal Fees', 'category_type': 'LEGAL', 'description': 'Legal consultation and services', 'requires_approval': True, 'approval_limit': 1000000, 'is_active': True},
            {'name': 'Audit Fees', 'category_type': 'LEGAL', 'description': 'External audit and accounting services', 'requires_approval': True, 'approval_limit': 2000000, 'is_active': True},
            {'name': 'Compliance Costs', 'category_type': 'LEGAL', 'description': 'Regulatory compliance expenses', 'requires_approval': True, 'approval_limit': 500000, 'is_active': True},

            # FINANCIAL (New category needed)
            {'name': 'Interest on Loans', 'category_type': 'FINANCIAL', 'description': 'Interest payments on borrowed funds', 'requires_approval': False, 'approval_limit': None, 'is_active': True},
            {'name': 'Loan Principal Repayment', 'category_type': 'FINANCIAL', 'description': 'Principal repayment on loans', 'requires_approval': False, 'approval_limit': None, 'is_active': True},
            {'name': 'Foreign Exchange Loss', 'category_type': 'FINANCIAL', 'description': 'Losses from currency exchange', 'requires_approval': False, 'approval_limit': None, 'is_active': True},
            {'name': 'Investment Losses', 'category_type': 'FINANCIAL', 'description': 'Losses on investments', 'requires_approval': False, 'approval_limit': None, 'is_active': True},

            # INSURANCE (New category needed)
            {'name': 'Building Insurance', 'category_type': 'INSURANCE', 'description': 'Property and building insurance', 'requires_approval': True, 'approval_limit': 2000000, 'is_active': True},
            {'name': 'Vehicle Insurance', 'category_type': 'INSURANCE', 'description': 'Motor vehicle insurance', 'requires_approval': True, 'approval_limit': 1000000, 'is_active': True},
            {'name': 'General Liability', 'category_type': 'INSURANCE', 'description': 'Public liability and third-party insurance', 'requires_approval': True, 'approval_limit': 1500000, 'is_active': True},
            {'name': 'Student Insurance', 'category_type': 'INSURANCE', 'description': 'Student accident and injury coverage', 'requires_approval': True, 'approval_limit': 500000, 'is_active': True},

            # TAX (New category needed)
            {'name': 'Corporate Income Tax', 'category_type': 'TAX', 'description': 'Corporate income tax payments', 'requires_approval': False, 'approval_limit': None, 'is_active': True},
            {'name': 'VAT Payments', 'category_type': 'TAX', 'description': 'Value Added Tax payments', 'requires_approval': False, 'approval_limit': None, 'is_active': True},
            {'name': 'Withholding Tax', 'category_type': 'TAX', 'description': 'Withholding tax on suppliers', 'requires_approval': False, 'approval_limit': None, 'is_active': True},
            {'name': 'Property Tax', 'category_type': 'TAX', 'description': 'Local government property taxes', 'requires_approval': False, 'approval_limit': None, 'is_active': True},
            {'name': 'Penalties & Fines', 'category_type': 'TAX', 'description': 'Government penalties and fines', 'requires_approval': False, 'approval_limit': None, 'is_active': True},

            # DRAWINGS (New category needed)
            {'name': 'Owner Drawings', 'category_type': 'DRAWINGS', 'description': 'Proprietor personal withdrawals', 'requires_approval': True, 'approval_limit': 5000000, 'is_active': True},
            {'name': 'Partner Distributions', 'category_type': 'DRAWINGS', 'description': 'Distributions to business partners', 'requires_approval': True, 'approval_limit': 10000000, 'is_active': True},
            {'name': 'Shareholder Dividends', 'category_type': 'DRAWINGS', 'description': 'Dividend payments to shareholders', 'requires_approval': True, 'approval_limit': 10000000, 'is_active': True},

            # DEPRECIATION (New category needed)
            {'name': 'Depreciation - Buildings', 'category_type': 'DEPRECIATION', 'description': 'Annual depreciation of buildings', 'requires_approval': False, 'approval_limit': None, 'is_active': True},
            {'name': 'Depreciation - Equipment', 'category_type': 'DEPRECIATION', 'description': 'Annual depreciation of equipment', 'requires_approval': False, 'approval_limit': None, 'is_active': True},
            {'name': 'Depreciation - Vehicles', 'category_type': 'DEPRECIATION', 'description': 'Annual depreciation of vehicles', 'requires_approval': False, 'approval_limit': None, 'is_active': True},
            {'name': 'Amortization', 'category_type': 'DEPRECIATION', 'description': 'Amortization of intangible assets', 'requires_approval': False, 'approval_limit': None, 'is_active': True},

            # CHARITY
            {'name': 'Charitable Donations', 'category_type': 'CHARITY', 'description': 'Donations to charitable organizations', 'requires_approval': True, 'approval_limit': 1000000, 'is_active': True},
            {'name': 'Community Support', 'category_type': 'CHARITY', 'description': 'Community development and support', 'requires_approval': True, 'approval_limit': 500000, 'is_active': True},
            {'name': 'Scholarship Fund', 'category_type': 'CHARITY', 'description': 'Scholarships for needy students', 'requires_approval': True, 'approval_limit': 2000000, 'is_active': True},

            # MISCELLANEOUS
            {'name': 'Bad Debts', 'category_type': 'MISCELLANEOUS', 'description': 'Uncollectible student fees', 'requires_approval': True, 'approval_limit': 1000000, 'is_active': True},
            {'name': 'Emergency Expenses', 'category_type': 'MISCELLANEOUS', 'description': 'Unexpected emergency costs', 'requires_approval': True, 'approval_limit': 500000, 'is_active': True},
            {'name': 'Loss on Asset Disposal', 'category_type': 'MISCELLANEOUS', 'description': 'Losses from selling assets', 'requires_approval': False, 'approval_limit': None, 'is_active': True},

            # OTHER
            {'name': 'Miscellaneous Expenses', 'category_type': 'OTHER', 'description': 'Other uncategorized expenses', 'requires_approval': True, 'approval_limit': 100000, 'is_active': True},
        ]
    
    @classmethod
    def get_journals(cls):
        """Standard accounting journals"""
        return [
            {'name': 'General Journal', 'journal_type': 'GENERAL', 'description': 'General accounting entries', 'is_active': True},
            {'name': 'Fee Collection Journal', 'journal_type': 'FEES', 'description': 'Student fee collection entries', 'is_active': True},
            {'name': 'Expense Journal', 'journal_type': 'EXPENSES', 'description': 'School expense entries', 'is_active': True},
            {'name': 'Cash Journal', 'journal_type': 'CASH', 'description': 'Cash transaction entries', 'is_active': True},
            {'name': 'Bank Journal', 'journal_type': 'BANK', 'description': 'Bank transaction entries', 'is_active': True},
            {'name': 'Payroll Journal', 'journal_type': 'PAYROLL', 'description': 'Staff salary and payroll entries', 'is_active': True},
        ]
    
    @classmethod
    def get_units_of_measure(cls):
        """Comprehensive units of measurement - FIXED VERSION with proper conversion factors"""
        return [
            # BASE UNITS - Foundation units for each category
            {'name': 'Each', 'abbreviation': 'ea', 'symbol': 'ea', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'), 'description': 'Individual items', 'is_active': True},
            {'name': 'Kilogram', 'abbreviation': 'kg', 'symbol': 'kg', 'uom_type': 'WEIGHT', 'conversion_factor': Decimal('1.0'), 'description': 'Base unit of mass', 'is_active': True},
            {'name': 'Meter', 'abbreviation': 'm', 'symbol': 'm', 'uom_type': 'LENGTH', 'conversion_factor': Decimal('1.0'), 'description': 'Base unit of length', 'is_active': True},
            {'name': 'Liter', 'abbreviation': 'L', 'symbol': 'L', 'uom_type': 'VOLUME', 'conversion_factor': Decimal('1.0'), 'description': 'Base unit of volume', 'is_active': True},
            {'name': 'Day', 'abbreviation': 'day', 'symbol': 'd', 'uom_type': 'TIME', 'conversion_factor': Decimal('1.0'), 'description': 'Base unit of time for school purposes', 'is_active': True},
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
            {'name': 'Pound', 'abbreviation': 'lb', 'symbol': 'lb', 'uom_type': 'WEIGHT', 'conversion_factor': Decimal('0.453592'), 'description': '0.453592 kilograms', 'is_active': True},
            {'name': 'Ounce', 'abbreviation': 'oz', 'symbol': 'oz', 'uom_type': 'WEIGHT', 'conversion_factor': Decimal('0.028350'), 'description': '0.028350 kilograms', 'is_active': True},

            # VOLUME UNITS
            {'name': 'Milliliter', 'abbreviation': 'mL', 'symbol': 'mL', 'uom_type': 'VOLUME', 'conversion_factor': Decimal('0.001'), 'description': '0.001 liters', 'is_active': True},
            {'name': 'US Gallon', 'abbreviation': 'gal', 'symbol': 'gal', 'uom_type': 'VOLUME', 'conversion_factor': Decimal('3.78541'), 'description': '3.78541 liters', 'is_active': True},
            {'name': 'Cup', 'abbreviation': 'cup', 'symbol': 'c', 'uom_type': 'VOLUME', 'conversion_factor': Decimal('0.236588'), 'description': '0.236588 liters', 'is_active': True},
            {'name': 'Tablespoon', 'abbreviation': 'tbsp', 'symbol': 'tbsp', 'uom_type': 'VOLUME', 'conversion_factor': Decimal('0.0147868'), 'description': '0.0147868 liters', 'is_active': True},

            # TIME UNITS - FIXED to avoid overflow
            {'name': 'Second', 'abbreviation': 's', 'symbol': 's', 'uom_type': 'TIME', 'conversion_factor': Decimal('0.000012'), 'description': 'Fraction of a day (1/86400)', 'is_active': True},
            {'name': 'Minute', 'abbreviation': 'min', 'symbol': 'min', 'uom_type': 'TIME', 'conversion_factor': Decimal('0.000694'), 'description': 'Fraction of a day (1/1440)', 'is_active': True},
            {'name': 'Hour', 'abbreviation': 'hr', 'symbol': 'h', 'uom_type': 'TIME', 'conversion_factor': Decimal('0.041667'), 'description': 'Fraction of a day (1/24)', 'is_active': True},
            {'name': 'Week', 'abbreviation': 'wk', 'symbol': 'wk', 'uom_type': 'TIME', 'conversion_factor': Decimal('7.0'), 'description': '7 days', 'is_active': True},
            {'name': 'Month', 'abbreviation': 'mo', 'symbol': 'mo', 'uom_type': 'TIME', 'conversion_factor': Decimal('30.44'), 'description': '30.44 days average', 'is_active': True},
            {'name': 'Year', 'abbreviation': 'yr', 'symbol': 'yr', 'uom_type': 'TIME', 'conversion_factor': Decimal('365.24'), 'description': '365.24 days', 'is_active': True},

            # AREA UNITS
            {'name': 'Square Centimeter', 'abbreviation': 'cm²', 'symbol': 'cm²', 'uom_type': 'AREA', 'conversion_factor': Decimal('0.0001'), 'description': '0.0001 square meters', 'is_active': True},
            {'name': 'Square Foot', 'abbreviation': 'sq ft', 'symbol': 'ft²', 'uom_type': 'AREA', 'conversion_factor': Decimal('0.092903'), 'description': '0.092903 square meters', 'is_active': True},

            # QUANTITY UNITS - Enhanced for school inventory
            {'name': 'Piece', 'abbreviation': 'pc', 'symbol': 'pc', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'), 'description': 'A single item', 'is_active': True},
            {'name': 'Dozen', 'abbreviation': 'doz', 'symbol': 'dz', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('12.0'), 'description': '12 units', 'is_active': True},
            {'name': 'Pair', 'abbreviation': 'pr', 'symbol': 'pr', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('2.0'), 'description': '2 units', 'is_active': True},
            {'name': 'Set', 'abbreviation': 'set', 'symbol': 'set', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'), 'description': 'A complete set or kit', 'is_active': True},
            {'name': 'Pack', 'abbreviation': 'pack', 'symbol': 'pk', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'), 'description': 'A package of items', 'is_active': True},
            {'name': 'Packet', 'abbreviation': 'pkt', 'symbol': 'pkt', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'), 'description': 'A packet of items', 'is_active': True},
            {'name': 'Box', 'abbreviation': 'box', 'symbol': 'box', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'), 'description': 'A box of items', 'is_active': True},
            {'name': 'Bundle', 'abbreviation': 'bundle', 'symbol': 'bndl', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'), 'description': 'A bundle of items', 'is_active': True},
            {'name': 'Roll', 'abbreviation': 'roll', 'symbol': 'roll', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'), 'description': 'A roll of material', 'is_active': True},
            {'name': 'Sheet', 'abbreviation': 'sheet', 'symbol': 'sht', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'), 'description': 'A single sheet', 'is_active': True},
            {'name': 'Ream', 'abbreviation': 'ream', 'symbol': 'rm', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('500.0'), 'description': '500 sheets of paper', 'is_active': True},
            {'name': 'Book', 'abbreviation': 'book', 'symbol': 'bk', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'), 'description': 'A single book', 'is_active': True},
            {'name': 'Bottle', 'abbreviation': 'bottle', 'symbol': 'btl', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'), 'description': 'A bottle container', 'is_active': True},
            {'name': 'Can', 'abbreviation': 'can', 'symbol': 'can', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'), 'description': 'A can or tin', 'is_active': True},
            {'name': 'Bag', 'abbreviation': 'bag', 'symbol': 'bag', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'), 'description': 'A bag or sack', 'is_active': True},
            {'name': 'Tube', 'abbreviation': 'tube', 'symbol': 'tube', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'), 'description': 'A tube container', 'is_active': True},
            {'name': 'Jar', 'abbreviation': 'jar', 'symbol': 'jar', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'), 'description': 'A jar container', 'is_active': True},

            # SCHOOL-SPECIFIC UNITS
            {'name': 'Classroom Set', 'abbreviation': 'cls-set', 'symbol': 'cls', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('30.0'), 'description': 'Typical classroom quantity (30 units)', 'is_active': True},
            {'name': 'Student Pack', 'abbreviation': 'std-pk', 'symbol': 'sp', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'), 'description': 'Individual student package', 'is_active': True},
            {'name': 'Teacher Pack', 'abbreviation': 'tcr-pk', 'symbol': 'tp', 'uom_type': 'QUANTITY', 'conversion_factor': Decimal('1.0'), 'description': 'Teacher resource package', 'is_active': True},

            # OTHER UNITS
            {'name': 'Percent', 'abbreviation': '%', 'symbol': '%', 'uom_type': 'OTHER', 'conversion_factor': Decimal('0.01'), 'description': 'One hundredth', 'is_active': True},
            {'name': 'Degree Celsius', 'abbreviation': '°C', 'symbol': '°C', 'uom_type': 'OTHER', 'conversion_factor': Decimal('1.0'), 'description': 'Temperature unit', 'is_active': True},
        ]
    
    @classmethod
    def get_sample_classrooms(cls):
        """Sample classroom data"""
        return [
            {'name': 'Main Classroom 1', 'room_number': 'MC-001', 'building': 'Main Block', 'capacity': 35, 'room_type': 'REGULAR', 'has_projector': True, 'has_whiteboard': True, 'is_active': True},
            {'name': 'Main Classroom 2', 'room_number': 'MC-002', 'building': 'Main Block', 'capacity': 35, 'room_type': 'REGULAR', 'has_projector': True, 'has_whiteboard': True, 'is_active': True},
            {'name': 'Science Laboratory', 'room_number': 'SL-001', 'building': 'Science Block', 'capacity': 30, 'room_type': 'SCIENCE_LAB', 'has_projector': True, 'has_whiteboard': True, 'is_active': True},
            {'name': 'Computer Lab', 'room_number': 'CL-001', 'building': 'ICT Block', 'capacity': 25, 'room_type': 'COMPUTER_LAB', 'has_projector': True, 'has_computer': True, 'has_internet': True, 'is_active': True},
            {'name': 'Library', 'room_number': 'LIB-001', 'building': 'Main Block', 'capacity': 50, 'room_type': 'LIBRARY', 'has_projector': False, 'has_whiteboard': False, 'is_active': True},
            {'name': 'Music Room', 'room_number': 'MR-001', 'building': 'Arts Block', 'capacity': 20, 'room_type': 'MUSIC_ROOM', 'has_sound_system': True, 'is_active': True},
            {'name': 'Art Room', 'room_number': 'AR-001', 'building': 'Arts Block', 'capacity': 25, 'room_type': 'ART_ROOM', 'is_active': True},
            {'name': 'Auditorium', 'room_number': 'AUD-001', 'building': 'Main Block', 'capacity': 200, 'room_type': 'AUDITORIUM', 'has_projector': True, 'has_sound_system': True, 'is_active': True},
        ]

# Usage examples and validation
class SchoolInitValidator:
    """Validator for school initialization configuration"""
    
    @classmethod
    def validate_config(cls, config_type, country=None, curriculum=None):
        """Validate configuration data"""
        errors = []
        
        try:
            if config_type == 'payment_methods':
                data = SchoolInitConfig.get_payment_methods()
                cls._validate_payment_methods(data, errors)
            elif config_type == 'tax_rates':
                data = SchoolInitConfig.get_tax_rates(country or 'UG')
                cls._validate_tax_rates(data, errors)
            elif config_type == 'academic_levels':
                data = SchoolInitConfig.get_academic_levels(curriculum or 'primary')
                cls._validate_academic_levels(data, errors)
            elif config_type == 'subjects':
                data = SchoolInitConfig.get_subjects(curriculum or 'primary')
                cls._validate_subjects(data, errors)
            # Add more validations as needed
                
        except Exception as e:
            errors.append(f"Configuration error: {e}")
        
        return errors
    
    @classmethod
    def _validate_payment_methods(cls, data, errors):
        """Validate payment methods data"""
        codes = set()
        for item in data:
            if item['code'] in codes:
                errors.append(f"Duplicate payment method code: {item['code']}")
            codes.add(item['code'])
            
            if item['has_processing_fee'] and not (item.get('fee_percentage') or item.get('fee_fixed_amount')):
                errors.append(f"Payment method {item['code']} has processing fee but no fee amount specified")
    
    @classmethod
    def _validate_tax_rates(cls, data, errors):
        """Validate tax rates data"""
        for item in data:
            if not (0 <= item['rate'] <= 1):
                errors.append(f"Tax rate {item['code']} has invalid rate: {item['rate']}")
    
    @classmethod
    def _validate_academic_levels(cls, data, errors):
        """Validate academic levels data"""
        orders = set()
        codes = set()
        
        for item in data:
            if item['order'] in orders:
                errors.append(f"Duplicate academic level order: {item['order']}")
            orders.add(item['order'])
            
            if item['code'] in codes:
                errors.append(f"Duplicate academic level code: {item['code']}")
            codes.add(item['code'])
            
            if item['min_age'] >= item['max_age']:
                errors.append(f"Academic level {item['code']} has invalid age range")
    
    @classmethod
    def _validate_subjects(cls, data, errors):
        """Validate subjects data"""
        codes = set()
        abbreviations = set()
        
        for item in data:
            if item['code'] in codes:
                errors.append(f"Duplicate subject code: {item['code']}")
            codes.add(item['code'])
            
            if item['abbreviation'] in abbreviations:
                errors.append(f"Duplicate subject abbreviation: {item['abbreviation']}")
            abbreviations.add(item['abbreviation'])
            
            if not (0 <= item['pass_mark'] <= 100):
                errors.append(f"Subject {item['code']} has invalid pass mark: {item['pass_mark']}")


# Configuration presets for different school types
class SchoolPresets:
    """Predefined configurations for different school types"""
    
    PRESETS = {
        'nursery': {
            'academic_levels': 'primary',  # Use first 3 levels only
            'subjects': 'primary',  # Use basic subjects only
            'level_filter': lambda x: x['order'] <= 3,
            'subject_filter': lambda x: x['subject_type'] in ['LITERACY', 'NUMERACY', 'LIFE_SKILLS', 'CREATIVE'],
        },
        'primary': {
            'academic_levels': 'primary',
            'subjects': 'primary',
            'level_filter': None,
            'subject_filter': None,
        },
        'secondary': {
            'academic_levels': 'secondary',
            'subjects': 'secondary',
            'level_filter': None,
            'subject_filter': None,
        },
        'combined': {
            'academic_levels': 'combined',
            'subjects': ['primary', 'secondary'],  # Merge both
            'level_filter': None,
            'subject_filter': None,
        },
    }
    
    @classmethod
    def get_preset_config(cls, preset_name):
        """Get configuration for a specific preset"""
        if preset_name not in cls.PRESETS:
            raise ValueError(f"Unknown preset: {preset_name}")
        
        preset = cls.PRESETS[preset_name]
        config = {}
        
        # Academic levels
        levels = SchoolInitConfig.get_academic_levels(preset['academic_levels'])
        if preset['level_filter']:
            levels = [l for l in levels if preset['level_filter'](l)]
        config['academic_levels'] = levels
        
        # Subjects
        if isinstance(preset['subjects'], list):
            # Merge multiple subject sets
            subjects = []
            for subj_type in preset['subjects']:
                subjects.extend(SchoolInitConfig.get_subjects(subj_type))
        else:
            subjects = SchoolInitConfig.get_subjects(preset['subjects'])
        
        if preset['subject_filter']:
            subjects = [s for s in subjects if preset['subject_filter'](s)]
        config['subjects'] = subjects
        
        # Use standard configurations for other components
        config['payment_methods'] = SchoolInitConfig.get_payment_methods()
        config['departments'] = SchoolInitConfig.get_departments()
        config['leave_types'] = SchoolInitConfig.get_leave_types()
        config['fee_categories'] = SchoolInitConfig.get_fee_categories()
        config['expense_categories'] = SchoolInitConfig.get_expense_categories()
        
        return config