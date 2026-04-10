# management/commands/migrate_schools.py

"""
Custom Django management command to migrate school databases.

USAGE EXAMPLES:
===============

# 1. Migrate all apps to all school databases
python manage.py migrate_schools

# 2. Migrate only school apps to all schools
python manage.py migrate_schools --school-apps-only

# 3. Migrate a specific app (finance) to all schools
python manage.py migrate_schools finance --school-apps-only

# 4. Migrate all apps to a specific school
python manage.py migrate_schools --only atepi_palabek

# 5. Migrate a specific app to specific schools (comma-separated)
python manage.py migrate_schools finance --only atepi_palabek,atepi_pajok --school-apps-only

# 6. Show migration plan for an app on a specific school (dry run)
python manage.py migrate_schools finance --only atepi_palabek --plan

# 7. Fake migrations (mark as applied without running)
python manage.py migrate_schools finance --only atepi_palabek --fake

# 8. Fake initial migrations (when tables already exist)
python manage.py migrate_schools finance --only atepi_palabek --fake-initial
"""

from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


# Apps whose data lives in school databases.
# 'accounts' is intentionally excluded — User rows live in `default`.
SCHOOL_APPS = [
    'students',
    'academics',
    'exams',
    'hr',
    'fees',
    'finance',
    'inventory',
    'uniforms',
    'core',
    'boarding',
    'discipline',
    'documents',
    'utils',
]

# Apps that need their table *structure* in every database (default + school DBs)
# so that FK joins from school models to auth.User do not fail at query time.
# The actual rows for these apps always live in `default` — school DBs only
# need the empty table definitions.
SHARED_STRUCTURE_APPS = [
    'auth',
    'contenttypes',
    'sessions',
]


class Command(BaseCommand):
    help = 'Run migrations for all school databases'

    def add_arguments(self, parser):
        parser.add_argument(
            'app_label', nargs='?', default=None,
            help='Optional app label to migrate'
        )
        parser.add_argument(
            'migration_name', nargs='?', default=None,
            help='Optional migration name to migrate to'
        )
        parser.add_argument(
            '--fake', action='store_true',
            help='Mark migrations as run without actually executing them'
        )
        parser.add_argument(
            '--plan', action='store_true',
            help='Show migration plan without executing it'
        )
        parser.add_argument(
            '--fake-initial', action='store_true',
            help='Mark initial migrations as applied if tables already exist'
        )
        parser.add_argument(
            '--school-apps-only', action='store_true',
            help=(
                'Only migrate school apps. '
                'Shared structure apps (auth, contenttypes, sessions) are '
                'always included so FK joins work correctly.'
            )
        )
        parser.add_argument(
            '--only', type=str, default=None,
            help='Comma-separated list of school database names to migrate'
        )
        parser.add_argument(
            '--skip-shared', action='store_true',
            help=(
                'Skip shared structure apps (auth, contenttypes, sessions). '
                'Only use this if you are certain those tables already exist '
                'in the target school databases.'
            )
        )

    def handle(self, *args, **options):
        # ── Determine target databases ─────────────────────────────────────────

        if options['only']:
            school_databases = [db.strip() for db in options['only'].split(',')]
        else:
            school_databases = [
                db for db in settings.DATABASES.keys()
                if db != 'default'
            ]

        if not school_databases:
            self.stdout.write(self.style.WARNING('No school databases found.'))
            return

        # ── Determine apps to migrate ──────────────────────────────────────────

        app_label = options['app_label']
        migration_name = options['migration_name']

        if app_label:
            # Explicit app requested — migrate only that one
            apps_to_migrate = [app_label]
            shared_apps_to_migrate = []
        elif options['school_apps_only']:
            # School apps + shared structure (unless explicitly skipped)
            apps_to_migrate = list(SCHOOL_APPS)
            shared_apps_to_migrate = [] if options['skip_shared'] else list(SHARED_STRUCTURE_APPS)
        else:
            # Migrate everything — let the router decide per-app
            apps_to_migrate = None
            shared_apps_to_migrate = []

        # ── Build base options for call_command ───────────────────────────────

        cmd_options = {
            'verbosity':    options.get('verbosity', 1),
            'fake':         options['fake'],
            'plan':         options['plan'],
            'fake_initial': options['fake_initial'],
        }

        # ── Run migrations ─────────────────────────────────────────────────────

        for db in school_databases:
            if db not in settings.DATABASES:
                self.stderr.write(
                    self.style.ERROR(f"Database '{db}' not found in settings — skipping.")
                )
                continue

            self.stdout.write(
                self.style.MIGRATE_HEADING(f"\n{'='*60}\nMigrating database: {db}\n{'='*60}")
            )

            db_options = {**cmd_options, 'database': db}

            try:
                if apps_to_migrate is None:
                    # Migrate all apps at once — router controls what lands where
                    self.stdout.write(self.style.MIGRATE_LABEL('  Migrating all apps…'))
                    call_command('migrate', **db_options)

                else:
                    # 1. Shared structure first (auth, contenttypes, sessions)
                    #    These must exist before school app tables that FK to them.
                    for app in shared_apps_to_migrate:
                        self.stdout.write(
                            self.style.MIGRATE_LABEL(f'  [{app}] shared structure…')
                        )
                        try:
                            call_command('migrate', app, **db_options)
                        except Exception as e:
                            self.stderr.write(
                                self.style.ERROR(f'  Error migrating {app} on {db}: {e}')
                            )

                    # 2. Then school apps
                    for app in apps_to_migrate:
                        self.stdout.write(
                            self.style.MIGRATE_LABEL(f'  [{app}]…')
                        )
                        args_list = [app]
                        if migration_name:
                            args_list.append(migration_name)
                        try:
                            call_command('migrate', *args_list, **db_options)
                        except Exception as e:
                            self.stderr.write(
                                self.style.ERROR(f'  Error migrating {app} on {db}: {e}')
                            )

            except Exception as e:
                self.stderr.write(
                    self.style.ERROR(f"Fatal error migrating {db}: {e}")
                )

        self.stdout.write(self.style.SUCCESS('\nDone.'))