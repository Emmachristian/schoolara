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
    """Router to handle multi-database setup"""

    default_apps = {'admin', 'auth', 'contenttypes', 'sessions', 'accounts'}
    school_apps = {
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
    }
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
        """Cache all school databases from settings"""
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

    def db_for_read(self, model, **hints):
        app_label = model._meta.app_label
        if self._should_use_default_db(model) or app_label in self.default_apps:
            return 'default'
        if app_label in self.school_apps:
            db = get_current_db()
            if db in connections and db != 'default':
                return db
            # fallback to first school DB
            if self._school_dbs:
                return list(self._school_dbs)[0]
            # No valid DB set, block read
            return None
        return 'default'

    def db_for_write(self, model, **hints):
        return self.db_for_read(model, **hints)

    def allow_relation(self, obj1, obj2, **hints):
        app1 = obj1._meta.app_label
        app2 = obj2._meta.app_label
        if (app1 in self.default_apps or self._should_use_default_db(obj1.__class__)) and \
           (app2 in self.default_apps or self._should_use_default_db(obj2.__class__)):
            return True
        if app1 in self.school_apps and app2 in self.school_apps:
            return True
        if (app1 in self.default_apps and app2 in self.school_apps) or \
           (app2 in self.default_apps and app1 in self.school_apps):
            return True
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """Control migrations"""

        # always-default models
        if model_name:
            label = f"{app_label}.{model_name}".lower()
            if label in self.always_default_models:
                return db == 'default'

        # default apps
        if app_label in self.default_apps:
            return db == 'default'

        # school apps
        if app_label in self.school_apps:
            # NEVER migrate school apps to default
            if db == 'default':
                return False
            # only allow migration to valid school DBs
            return db in self._school_dbs

        # unknown apps migrate to default
        return db == 'default'
    

