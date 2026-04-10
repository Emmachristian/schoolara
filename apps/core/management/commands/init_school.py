# core/management/commands/init_school.py

"""
Custom Django management command to initialize school financial systems.

This command sets up the complete financial infrastructure for a school:
  - Account Types (ASSET / LIABILITY / EQUITY / REVENUE / EXPENSE)
  - Chart of Accounts (based on school size/type)
  - Financial Settings (currency, invoice numbering, payment terms)
  - Account Mappings (CoreAccountMappings + 4 specialised mapping models)
  - Display Groups (fee invoice layout groups)
  - Fee Categories (tuition, boarding, activities, etc.)
  - Expense Categories (salaries, utilities, supplies, etc.)
  - Journals (General, Fees, Expenses, Cash, Bank, Payroll, Adjustments)
  - Fiscal Year and Periods (current year, term-based)
  - Payment Methods (Cash, Bank Transfer, Mobile Money, Card, Cheque)
  - Tax Rates (country-specific VAT / withholding tax)
  - Departments (administrative, academic, operational)
  - Designations (job titles linked to departments)
  - Units of Measure (70 units for inventory and procurement)

The system automatically determines accounting complexity:
  BASIC    — ~14 accounts  (small schools, < 200 students)
  STANDARD — ~35 accounts  (medium schools, 200–700 students)
  ADVANCED — ~80 accounts  (large schools, 700+ students, universities)

PREREQUISITES
=============
1. School must exist in the database (created via admin or fixture).
2. School's database must be configured in settings.DATABASES.
3. Migrations must be run for the school's database:
   python manage.py migrate_schools --only <database_alias>

USAGE EXAMPLES
==============
Initialize a specific school (by database alias):
  python manage.py init_school --database atepi_palabek

Initialize all non-initialized schools:
  python manage.py init_school --all

Override auto-detected complexity:
  python manage.py init_school --database atepi_palabek --complexity BASIC
  python manage.py init_school --database atepi_pajok  --complexity STANDARD
  python manage.py init_school --database kampala_high --complexity ADVANCED

List all schools and their initialization status:
  python manage.py list_schools

TYPICAL WORKFLOW
================
  # Step 1: Create school in admin or via fixture
  # Step 2: Run migrations for the school database
  python manage.py migrate_schools --only atepi_palabek

  # Step 3: Verify the school record
  python manage.py list_schools

  # Step 4: Initialize
  python manage.py init_school --database atepi_palabek

  # Step 5: Confirm
  python manage.py list_schools

WHAT GETS CREATED
=================
BASIC Complexity (~14 accounts):
  - 14 GL accounts covering all 5 account types
  - 6 payment methods
  - 33+ fee categories and 80+ expense categories
  - 3 fiscal periods (terms), 7 journals
  - 34 departments, 36 designations, 70 units of measure

STANDARD Complexity (~35 accounts):
  - 35+ GL accounts (more with boarding)
  - Same fee/expense/journal/HR setup as BASIC
  - More granular account mappings

ADVANCED Complexity (~80 accounts):
  - 80+ GL accounts with full fixed-asset and depreciation sub-ledger
  - Payroll account split across salary types
  - NSSF, PAYE, and LST payable accounts
  - Specialised boarding, transport, and penalty revenue accounts

COMPLEXITY AUTO-DETECTION
=========================
  University / College               → ADVANCED
  Student capacity ≥ 700             → ADVANCED
  Student capacity ≤ 200             → BASIC
  Kindergarten / Primary             → BASIC
  Everything else                    → STANDARD

Override any time with --complexity.

ERROR HANDLING
==============
- Config validation runs BEFORE any DB writes (Phase 0). If
  SchoolInitConfig.validate_config() finds issues (e.g. a fee category
  references a display group that doesn't exist in the config), the
  command aborts with a clear list of issues. Fix the config file and retry.
- If the school is already initialized, the command warns and exits.
- If the database alias is missing from settings, available databases are listed.
- All DB operations are transactional — on any error everything rolls back.

NOTES
=====
- Safe to call on an already-initialized school (exits with warning).
- Each school can only be initialized once; for a full wipe + re-init,
  use the Django admin interface or the reinitialize_school() function.
- Initialization is per-school and fully isolated — no cross-school data.

AUTHOR: Schoolara Development Team
VERSION: 2.0
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
            help=(
                'Database alias of the school to initialize '
                '(e.g. atepi_palabek, kampala_high). '
                'Required unless --all is passed.'
            ),
        )
        parser.add_argument(
            '--complexity',
            type=str,
            choices=['BASIC', 'STANDARD', 'ADVANCED'],
            help=(
                'Override accounting complexity. '
                'Auto-detected from school size/type when omitted.'
            ),
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Initialize every school that has not been initialized yet.',
        )

    def handle(self, *args, **options):
        database       = options.get('database')
        complexity     = options.get('complexity')
        initialize_all = options.get('all')

        if initialize_all:
            self._initialize_all_schools(complexity)
        elif database:
            self._initialize_school_by_database(database, complexity)
        else:
            self.stdout.write(self.style.ERROR(
                '\n❌ Error: specify --database <alias> or --all\n'
            ))
            self.stdout.write('Examples:')
            self.stdout.write('  python manage.py init_school --database atepi_palabek')
            self.stdout.write('  python manage.py init_school --database atepi_pajok --complexity ADVANCED')
            self.stdout.write('  python manage.py init_school --all')
            self.stdout.write('\nTo see available schools:')
            self.stdout.write('  python manage.py list_schools\n')

    # =========================================================================
    # SINGLE SCHOOL
    # =========================================================================

    def _initialize_school_by_database(self, database_alias, complexity):
        """
        Initialize one school by database alias.

        Returns:
            bool: True if initialization ran successfully, False otherwise.
                  Callers (e.g. _initialize_all_schools) use this to count results.
        """

        # ── Validate database alias ───────────────────────────────────────────
        if database_alias not in settings.DATABASES:
            self.stdout.write(self.style.ERROR(
                f'\n❌ Database "{database_alias}" not found in settings.\n'
            ))
            self.stdout.write('Available databases:')
            for db_name in settings.DATABASES:
                if db_name != 'default':
                    self.stdout.write(f'  - {db_name}')
            self.stdout.write('')
            return False

        # ── Find school record ────────────────────────────────────────────────
        try:
            school = School.objects.using('default').get(
                database_alias=database_alias
            )
        except School.DoesNotExist:
            self.stdout.write(self.style.ERROR(
                f'\n❌ No school found with database_alias "{database_alias}"\n'
            ))
            self.stdout.write(
                'Use "python manage.py list_schools" to see available schools.\n'
            )
            return False

        # ── Guard: already initialized ────────────────────────────────────────
        if school.is_initial_setup_complete:
            self.stdout.write(self.style.WARNING(
                f'\n⚠️  {school.full_name} is already initialized.\n'
            ))
            self.stdout.write(
                'To re-initialize (WARNING: wipes all financial data):\n'
                '  1. Open Django admin\n'
                f'  2. Navigate to Schools → {school.full_name}\n'
                '  3. Click "Re-initialize School"\n'
            )
            return False

        # ── Apply complexity override ─────────────────────────────────────────
        if complexity:
            school.accounting_complexity = complexity
            school.save(using='default')

        # ── Print header ──────────────────────────────────────────────────────
        sep = '=' * 70
        self.stdout.write(self.style.MIGRATE_HEADING(f'\n{sep}'))
        self.stdout.write(self.style.MIGRATE_HEADING(f'🚀 INITIALIZING: {school.full_name}'))
        self.stdout.write(self.style.MIGRATE_HEADING(sep))
        self.stdout.write(f'📊 Database:         {database_alias}')
        self.stdout.write(f'🏫 School Type:      {school.get_school_type_display()}')
        self.stdout.write(f'👥 Student Capacity: {school.student_capacity}')
        self.stdout.write(f'📈 Complexity:       {school.get_accounting_complexity_level()}')
        self.stdout.write(f'🔢 ~Accounts:        {school.get_recommended_accounts_count()}')
        self.stdout.write('')

        # ── Run initialization ────────────────────────────────────────────────
        try:
            result = initialize_school(school)
        except ValueError as exc:
            # Config validation failure (Phase 0) — list every issue clearly
            self.stdout.write(self.style.ERROR('\n❌ CONFIG VALIDATION FAILED\n'))
            self.stdout.write(
                'The initialization config has errors that must be fixed '
                'before the database is touched:\n'
            )
            for line in str(exc).splitlines():
                self.stdout.write(self.style.ERROR(f'  ✗ {line}'))
            self.stdout.write(
                '\nFix core/services/school_init_config.py and retry.\n'
            )
            return False
        except Exception as exc:
            self.stdout.write(self.style.ERROR('\n❌ INITIALIZATION FAILED\n'))
            self.stdout.write(self.style.ERROR(f'  ✗ {exc}'))
            self.stdout.write('')
            return False

        # ── Print results ─────────────────────────────────────────────────────
        if result['success']:
            c = result['created']
            self.stdout.write(self.style.SUCCESS('\n✅ INITIALIZATION SUCCESSFUL!\n'))
            self.stdout.write('Created:')
            self.stdout.write(f"  📁 Account Types:      {c.get('account_types', 0)}")
            self.stdout.write(f"  📁 GL Accounts:        {c.get('accounts', 0)}")
            self.stdout.write(f"  🗂  Display Groups:     {c.get('display_groups', 0)}")
            self.stdout.write(f"  💰 Fee Categories:     {c.get('fee_categories', 0)}")
            self.stdout.write(f"  💳 Expense Categories: {c.get('expense_categories', 0)}")
            self.stdout.write(f"  📔 Journals:           {c.get('journals', 0)}")
            self.stdout.write(f"  📅 Fiscal Periods:     {c.get('fiscal_periods', 0)}")
            self.stdout.write(f"  💳 Payment Methods:    {c.get('payment_methods', 0)}")
            self.stdout.write(f"  🧾 Tax Rates:          {c.get('tax_rates', 0)}")
            self.stdout.write(f"  🏢 Departments:        {c.get('departments', 0)}")
            self.stdout.write(f"  👤 Designations:       {c.get('designations', 0)}")
            self.stdout.write(f"  📏 Units of Measure:   {c.get('units_of_measure', 0)}")
            self.stdout.write(f"  ⚙️  Financial Settings: Configured")
            self.stdout.write(f"  🔗 Account Mappings:   Configured")
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS(f'🎉 {school.full_name} is ready to use!\n'))
            return True
        else:
            self.stdout.write(self.style.ERROR('\n❌ INITIALIZATION FAILED\n'))
            for error in result['errors']:
                self.stdout.write(self.style.ERROR(f'  ✗ {error}'))
            self.stdout.write('')
            return False

    # =========================================================================
    # ALL SCHOOLS
    # =========================================================================

    def _initialize_all_schools(self, complexity):
        """Initialize every school that has not yet been initialized."""

        schools = School.objects.using('default').filter(
            is_initial_setup_complete=False
        )

        if not schools.exists():
            self.stdout.write(self.style.WARNING(
                '\n⚠️  No schools found that need initialization.\n'
            ))
            self.stdout.write('All schools are already initialized! ✅\n')
            return

        self.stdout.write(self.style.SUCCESS(
            f'\n📋 Found {schools.count()} school(s) to initialize:\n'
        ))
        for school in schools:
            self.stdout.write(
                f'  • {school.full_name} ({school.database_alias}) '
                f'[{school.get_accounting_complexity_level()}]'
            )
        self.stdout.write('')

        success_count = 0
        error_count   = 0

        for school in schools:
            # FIX: check the return value — _initialize_school_by_database returns
            # False on early-exit (already initialized, database missing, etc.) as
            # well as on actual failure. Don't count early exits as successes.
            try:
                ok = self._initialize_school_by_database(
                    school.database_alias, complexity
                )
                if ok:
                    success_count += 1
                else:
                    error_count += 1
            except Exception as exc:
                self.stdout.write(self.style.ERROR(
                    f'\n❌ Unexpected error for {school.full_name}: {exc}\n'
                ))
                error_count += 1

        # Summary
        sep = '=' * 70
        self.stdout.write(self.style.MIGRATE_HEADING(f'\n{sep}'))
        self.stdout.write(self.style.MIGRATE_HEADING('📊 INITIALIZATION SUMMARY'))
        self.stdout.write(self.style.MIGRATE_HEADING(sep))

        if success_count:
            self.stdout.write(self.style.SUCCESS(
                f'✅ Successfully initialized: {success_count} school(s)'
            ))
        if error_count:
            self.stdout.write(self.style.ERROR(
                f'❌ Failed / skipped: {error_count} school(s)'
            ))

        self.stdout.write('')

        if success_count == schools.count():
            self.stdout.write(self.style.SUCCESS(
                '🎉 All schools are now initialized and ready to use!'
            ))

        self.stdout.write('')