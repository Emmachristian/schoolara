# core/management/commands/init_school.py

"""
Custom Django management command to initialize school financial systems.

This command sets up the complete financial infrastructure for a school including:
- Chart of Accounts (based on school size/type)
- Account Mappings (automatic configuration)
- Fee Categories (tuition, boarding, activities, etc.)
- Expense Categories (salaries, utilities, supplies, etc.)
- Financial Settings (currency, invoice numbering, payment terms)
- Fiscal Year and Periods (current year)

The system automatically determines the appropriate accounting complexity:
- BASIC: 10-12 accounts (small schools, < 200 students)
- STANDARD: 20-30 accounts (medium schools, 200-700 students)
- ADVANCED: 50-60 accounts (large schools, 700+ students, with auditors)

PREREQUISITES:
==============
1. School must exist in the database (created via admin or fixture)
2. School's database must be configured in settings.DATABASES
3. Migrations must be run for the school's database:
   python manage.py migrate_schools --only <database_alias>

USAGE EXAMPLES:
===============

1. Initialize a specific school (by database alias):
   python manage.py init_school --database atepi_palabek

2. Initialize all non-initialized schools:
   python manage.py init_school --all

3. Override the auto-detected complexity:
   python manage.py init_school --database atepi_palabek --complexity BASIC
   python manage.py init_school --database atepi_pajok --complexity STANDARD
   python manage.py init_school --database kampala_high --complexity ADVANCED

4. List all schools and their initialization status:
   python manage.py list_schools

5. List only schools that need initialization:
   python manage.py list_schools --not-initialized

TYPICAL WORKFLOW:
=================
# Step 1: Create school in admin or via fixture
# Step 2: Run migrations for school database
python manage.py migrate_schools --only atepi_palabek

# Step 3: List schools to verify
python manage.py list_schools

# Step 4: Initialize the school
python manage.py init_school --database atepi_palabek

# Step 5: Verify initialization
python manage.py list_schools

WHAT GETS CREATED:
==================
BASIC Complexity (Small Schools):
  - 10-12 GL accounts
  - 3 fee categories
  - 4 expense categories
  - Simple account mappings
  - Financial settings with defaults

STANDARD Complexity (Medium Schools):
  - 25-30 GL accounts
  - 4-5 fee categories
  - 6-8 expense categories
  - Detailed account mappings
  - Enhanced financial settings

ADVANCED Complexity (Large Schools):
  - 55-65 GL accounts
  - 8-10 fee categories
  - 15-20 expense categories
  - Comprehensive account mappings
  - Full financial system with all features

COMPLEXITY AUTO-DETECTION:
==========================
The system automatically determines complexity based on:
- School type (University/College → ADVANCED)
- Student capacity (700+ → ADVANCED, 200-700 → STANDARD, <200 → BASIC)
- Educational level (Kindergarten/Primary → BASIC)

You can always override with --complexity flag.

ERROR HANDLING:
===============
- If school is already initialized, command will warn and exit
- If database doesn't exist in settings, command will list available databases
- If school doesn't exist with given database_alias, command will error
- All operations are transactional (rollback on error)

NOTES:
======
- This command is SAFE to run - it checks initialization status first
- Each school can only be initialized ONCE
- For re-initialization (data wipe), use Django admin interface
- Initialization is per-school, not global
- Each school gets its own isolated financial system

AUTHOR: Schoolara Development Team
VERSION: 1.0
LAST UPDATED: 2025-01-09
"""

from django.core.management.base import BaseCommand
from django.conf import settings
from accounts.models import School
from apps.core.services.school_initialization import initialize_school


class Command(BaseCommand):
    help = 'Initialize a school with default configuration'

    def add_arguments(self, parser):
        parser.add_argument(
            '--database',
            type=str,
            default=None,
            help='Database alias (e.g., atepi_palabek, atepi_pajok). If not provided, use --all to initialize all schools.'
        )
        
        parser.add_argument(
            '--complexity',
            type=str,
            choices=['BASIC', 'STANDARD', 'ADVANCED'],
            help='Override accounting complexity (auto-detected by default based on school size/type)'
        )
        
        parser.add_argument(
            '--all',
            action='store_true',
            help='Initialize all non-initialized schools in the system'
        )

    def handle(self, *args, **options):
        database = options.get('database')
        complexity = options.get('complexity')
        initialize_all = options.get('all')
        
        if initialize_all:
            self._initialize_all_schools(complexity)
        elif database:
            self._initialize_school_by_database(database, complexity)
        else:
            self.stdout.write(
                self.style.ERROR(
                    '\n❌ Error: You must specify either --database or --all\n'
                )
            )
            self.stdout.write('Usage examples:')
            self.stdout.write('  python manage.py init_school --database atepi_palabek')
            self.stdout.write('  python manage.py init_school --database atepi_pajok --complexity ADVANCED')
            self.stdout.write('  python manage.py init_school --all')
            self.stdout.write('\nTo see available schools:')
            self.stdout.write('  python manage.py list_schools')
            self.stdout.write('')
    
    def _initialize_school_by_database(self, database_alias, complexity):
        """Initialize school by its database alias"""
        
        # Validate database exists
        if database_alias not in settings.DATABASES:
            self.stdout.write(
                self.style.ERROR(
                    f'\n❌ Database "{database_alias}" not found in settings.\n'
                )
            )
            self.stdout.write('Available databases:')
            for db_name in settings.DATABASES.keys():
                if db_name != 'default':
                    self.stdout.write(f'  - {db_name}')
            self.stdout.write('')
            return
        
        # Find school with this database alias
        try:
            school = School.objects.using('default').get(
                database_alias=database_alias
            )
        except School.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(
                    f'\n❌ No school found with database_alias "{database_alias}"\n'
                )
            )
            self.stdout.write('Use "python manage.py list_schools" to see available schools.')
            self.stdout.write('')
            return
        
        # Check if already initialized
        if school.is_initial_setup_complete:
            self.stdout.write(
                self.style.WARNING(
                    f'\n⚠️  {school.full_name} is already initialized.\n'
                )
            )
            self.stdout.write('If you need to re-initialize (WARNING: deletes all data):')
            self.stdout.write('  1. Go to Django admin')
            self.stdout.write(f'  2. Navigate to Schools → {school.full_name}')
            self.stdout.write('  3. Click "Re-initialize School" button')
            self.stdout.write('')
            return
        
        # Override complexity if specified
        if complexity:
            school.accounting_complexity = complexity
            school.save(using='default')
        
        # Display initialization details
        self.stdout.write(self.style.MIGRATE_HEADING(f'\n{"="*70}'))
        self.stdout.write(self.style.MIGRATE_HEADING(f'🚀 INITIALIZING: {school.full_name}'))
        self.stdout.write(self.style.MIGRATE_HEADING(f'{"="*70}'))
        self.stdout.write(f'📊 Database: {database_alias}')
        self.stdout.write(f'🏫 School Type: {school.get_school_type_display()}')
        self.stdout.write(f'👥 Student Capacity: {school.student_capacity}')
        self.stdout.write(f'📈 Complexity: {school.get_accounting_complexity_level()}')
        self.stdout.write(f'🔢 Accounts to Create: ~{school.get_recommended_accounts_count()}')
        self.stdout.write('')
        
        # Perform initialization
        result = initialize_school(school)
        
        # Display results
        if result['success']:
            self.stdout.write(self.style.SUCCESS('\n✅ INITIALIZATION SUCCESSFUL!\n'))
            self.stdout.write('Created:')
            self.stdout.write(f"  📁 GL Accounts: {result['created'].get('accounts', 0)}")
            self.stdout.write(f"  💰 Fee Categories: {result['created'].get('fee_categories', 0)}")
            self.stdout.write(f"  💳 Expense Categories: {result['created'].get('expense_categories', 0)}")
            self.stdout.write(f"  📅 Fiscal Periods: {result['created'].get('fiscal_periods', 0)}")
            self.stdout.write(f"  ⚙️  Financial Settings: Configured")
            self.stdout.write(f"  🔗 Account Mappings: Configured")
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS(f'🎉 {school.full_name} is ready to use!'))
            self.stdout.write('')
        else:
            self.stdout.write(self.style.ERROR('\n❌ INITIALIZATION FAILED\n'))
            self.stdout.write('Errors:')
            for error in result['errors']:
                self.stdout.write(self.style.ERROR(f'  ✗ {error}'))
            self.stdout.write('')
    
    def _initialize_all_schools(self, complexity):
        """Initialize all non-initialized schools"""
        
        # Get all non-initialized schools
        schools = School.objects.using('default').filter(
            is_initial_setup_complete=False
        )
        
        if not schools.exists():
            self.stdout.write(
                self.style.WARNING(
                    '\n⚠️  No schools found that need initialization.\n'
                )
            )
            self.stdout.write('All schools are already initialized! ✅')
            self.stdout.write('')
            return
        
        # Display schools to be initialized
        self.stdout.write(
            self.style.SUCCESS(
                f'\n📋 Found {schools.count()} school(s) to initialize:\n'
            )
        )
        
        for school in schools:
            complexity_level = school.get_accounting_complexity_level()
            self.stdout.write(
                f'  • {school.full_name} ({school.database_alias}) '
                f'[{complexity_level}]'
            )
        
        self.stdout.write('')
        
        # Initialize each school
        success_count = 0
        error_count = 0
        
        for school in schools:
            try:
                self._initialize_school_by_database(school.database_alias, complexity)
                success_count += 1
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f'\n❌ Error initializing {school.full_name}: {str(e)}\n'
                    )
                )
                error_count += 1
        
        # Display summary
        self.stdout.write(self.style.MIGRATE_HEADING(f'\n{"="*70}'))
        self.stdout.write(self.style.MIGRATE_HEADING('📊 INITIALIZATION SUMMARY'))
        self.stdout.write(self.style.MIGRATE_HEADING(f'{"="*70}'))
        
        if success_count > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f'✅ Successfully initialized: {success_count} school(s)'
                )
            )
        
        if error_count > 0:
            self.stdout.write(
                self.style.ERROR(
                    f'❌ Failed: {error_count} school(s)'
                )
            )
        
        self.stdout.write('')
        
        if success_count == schools.count():
            self.stdout.write(
                self.style.SUCCESS(
                    '🎉 All schools are now initialized and ready to use!'
                )
            )
        
        self.stdout.write('')