# routers.py
import logging
import sys
from django.conf import settings
from django.db import connections

logger = logging.getLogger(__name__)


def get_current_db():
    """Import and call get_current_db from managers"""
    try:
        from .managers import get_current_db as _get_current_db
        return _get_current_db()
    except ImportError:
        logger.warning("Could not import get_current_db from managers")
        return None


class SchoolRouter:
    """
    Router to handle multi-database setup.

    Database layout
    ───────────────
    default           → auth, admin, contenttypes, sessions, accounts
    <school_db>       → all school apps (students, fees, academics, …)
                        PLUS auth/contenttypes/sessions table structure
                        (required because school models have FKs to auth.User)

    Why auth tables in every school DB?
    ────────────────────────────────────
    Django cannot JOIN across databases. Any school model that has a FK to
    auth.User (e.g. ScholarshipApplication.reviewed_by, Payment.created_by)
    will cause "Table '…db.auth_user' doesn't exist" at query time unless the
    auth table structure exists in the school database.

    The actual User *rows* still live only in `default`. School databases just
    need the table definitions so Django's SQL is valid. After any schema
    change run:
        python manage.py migrate --database=<school_alias>
    """

    # Apps whose data always lives in `default`
    default_apps = {'admin', 'contenttypes', 'sessions', 'accounts'}

    # Apps whose data always lives in the current school DB
    school_apps = {
        'students',
        'boarding',
        'discipline',
        'documents',
        'academics',
        'exams',
        'hr',
        'fees',
        'finance',
        'inventory',
        'uniforms',
        'core',
        'utils',
    }

    # Apps that need their table structure in EVERY database
    # (auth is here so school-DB queries can JOIN on auth_user without errors)
    shared_structure_apps = {'auth', 'contenttypes', 'sessions'}

    # Specific model labels that must always use `default`, regardless of app
    always_default_models = {
        'accounts.user',
        'accounts.customuser',
        'auth.user',
        'auth.group',
        'auth.permission',
    }

    def __init__(self):
        self._error_logged = False
        self._school_dbs = set()
        self._update_school_dbs()

    def _update_school_dbs(self):
        """Cache all school databases from settings (everything except default)."""
        try:
            self._school_dbs = {
                db_name for db_name in settings.DATABASES.keys()
                if db_name != 'default'
            }
            logger.debug(f"School databases: {self._school_dbs}")
        except Exception as e:
            logger.error(f"Error updating school databases: {e}")
            self._school_dbs = set()

    def _should_use_default_db(self, model):
        label = f"{model._meta.app_label}.{model._meta.model_name}".lower()
        return label in self.always_default_models

    def _is_system_command(self):
        cmds = ['makemigrations', 'migrate', 'showmigrations', 'sqlmigrate']
        return any(cmd in sys.argv for cmd in cmds)

    # ──────────────────────────────────────────────────────────────────────────
    # READ / WRITE ROUTING
    # ──────────────────────────────────────────────────────────────────────────

    def db_for_read(self, model, **hints):
        app_label = model._meta.app_label

        # Specific models that must always read from default
        if self._should_use_default_db(model):
            return 'default'

        # Default-only apps
        if app_label in self.default_apps:
            return 'default'

        # Auth / contenttypes / sessions — actual rows live in default
        if app_label in self.shared_structure_apps:
            return 'default'

        # School apps — use the current thread's school DB
        if app_label in self.school_apps:
            db = get_current_db()
            if db and db in connections and db != 'default':
                return db
            # Fallback to first available school DB (dev convenience)
            if self._school_dbs:
                return next(iter(self._school_dbs))
            return None

        return 'default'

    def db_for_write(self, model, **hints):
        return self.db_for_read(model, **hints)

    # ──────────────────────────────────────────────────────────────────────────
    # RELATION CHECKING
    # ──────────────────────────────────────────────────────────────────────────

    def allow_relation(self, obj1, obj2, **hints):
        app1 = obj1._meta.app_label
        app2 = obj2._meta.app_label

        def is_default(app, obj):
            return (
                app in self.default_apps
                or app in self.shared_structure_apps
                or self._should_use_default_db(obj.__class__)
            )

        # Both sides live in default — always OK
        if is_default(app1, obj1) and is_default(app2, obj2):
            return True

        # Both sides are school apps — OK (same school DB)
        if app1 in self.school_apps and app2 in self.school_apps:
            return True

        # Cross-DB relation between a school model and auth/default model
        # — allowed because we replicate auth table structure into school DBs
        if (
            (app1 in self.school_apps and is_default(app2, obj2)) or
            (app2 in self.school_apps and is_default(app1, obj1))
        ):
            return True

        return None

    # ──────────────────────────────────────────────────────────────────────────
    # MIGRATION CONTROL
    # ──────────────────────────────────────────────────────────────────────────

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """
        Migration routing rules
        ───────────────────────
        always_default_models   → default only
        admin                   → default only
        default_apps            → default only
        shared_structure_apps   → ALL databases (default + every school DB)
            ↳ this ensures auth_user, django_content_type, etc. exist in
              school databases so FK joins from school models don't fail
        school_apps             → school DBs only (never default)
        everything else         → default
        """

        # Specific models that must only ever live in default
        if model_name:
            label = f"{app_label}.{model_name}".lower()
            if label in self.always_default_models:
                return db == 'default'

        # Admin stays in default only
        if app_label == 'admin':
            return db == 'default'

        # Default-only apps
        if app_label in self.default_apps:
            return db == 'default'

        # Shared structure apps (auth, contenttypes, sessions) run on
        # default AND every school database so table definitions are present.
        if app_label in self.shared_structure_apps:
            return True

        # School apps migrate to school DBs only — never to default
        if app_label in self.school_apps:
            if db == 'default':
                return False
            return db in self._school_dbs

        # Unknown apps default to the default database
        return db == 'default'