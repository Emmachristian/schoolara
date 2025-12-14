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
from django.db import connections
import logging

logger = logging.getLogger(__name__)

# List of apps that belong to "school" databases
SCHOOL_APPS = [
    'accounts',
    'students',
    'academics',
    'exams',
    'hr',
    'fees',
    'finance',
    'inventory',
    'uniforms',
    'core',
    'utils'
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
            help='Only migrate apps that belong to school databases'
        )
        parser.add_argument(
            '--only', type=str, default=None,
            help='Comma-separated list of school database names to migrate'
        )

    def handle(self, *args, **options):
        # Determine databases to migrate
        if options['only']:
            school_databases = [db.strip() for db in options['only'].split(',')]
        else:
            # Default: all databases starting with 'school_' in settings
            school_databases = [
                db for db in settings.DATABASES.keys()
                if db != 'default'  # everything else is a school DB
            ]

        if not school_databases:
            self.stdout.write(self.style.WARNING('No school databases found.'))
            return

        # Determine apps to migrate
        app_label = options['app_label']
        if options['school_apps_only'] and app_label is None:
            # Migrate all school apps
            apps_to_migrate = SCHOOL_APPS
        elif app_label:
            apps_to_migrate = [app_label]
        else:
            apps_to_migrate = None  # All apps

        # Prepare migration command options
        cmd_options = {
            'verbosity': options.get('verbosity', 1),
            'fake': options['fake'],
            'plan': options['plan'],
            'fake_initial': options['fake_initial'],
        }

        # Loop through each school database
        for db in school_databases:
            if db not in settings.DATABASES:
                self.stderr.write(self.style.ERROR(f"Database '{db}' not found in settings"))
                continue

            self.stdout.write(self.style.MIGRATE_HEADING(f"\nMigrating database: {db}"))

            cmd_options['database'] = db

            try:
                if apps_to_migrate:
                    for app in apps_to_migrate:
                        call_command(
                            'migrate', 
                            app, 
                            *([options['migration_name']] if options['migration_name'] else []), 
                            **cmd_options
                        )
                else:
                    # Migrate all apps
                    call_command('migrate', **cmd_options)

            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Error migrating {db}: {str(e)}"))
