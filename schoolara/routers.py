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
    """Control database operations for school-specific apps"""
    
    # Apps that should only be in the default database
    default_apps = {'admin', 'auth', 'contenttypes', 'sessions'}
    
    # Apps that should be in school-specific databases
    school_apps = {
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
    }
    
    # Models that should ALWAYS use default database (even if app is in school_apps)
    # Format: 'app_label.modelname' in lowercase
    always_default_models = {
        'accounts.user',
        'accounts.customuser',
        'auth.user',
        'auth.group',
        'auth.permission',
    }
    
    def __init__(self):
        """Initialize the router"""
        self._error_logged = False
        self._school_dbs = set()
        self._update_school_dbs()
    
    def _update_school_dbs(self):
        """Update the cached list of school databases"""
        try:
            # Get all databases that start with 'school_' from settings
            self._school_dbs = {
                db_name for db_name in settings.DATABASES.keys()
                if db_name.startswith('school_') and db_name != 'default'
            }
            logger.debug(f"Updated school databases: {self._school_dbs}")
        except Exception as e:
            logger.error(f"Error updating school databases: {e}")
            self._school_dbs = set()
    
    def _should_use_default_db(self, model):
        """Check if a model should always use the default database"""
        model_label = f"{model._meta.app_label}.{model._meta.model_name}".lower()
        return model_label in self.always_default_models
    
    def _is_makemigrations_or_system_command(self):
        """Check if we're running makemigrations or other system commands"""
        system_commands = ['makemigrations', 'migrate', 'showmigrations', 'sqlmigrate']
        return any(cmd in sys.argv for cmd in system_commands)
    
    def db_for_read(self, model, **hints):
        """Determine which database to read from"""
        app_label = model._meta.app_label
        
        # FIRST: Check if this specific model should always use default
        if self._should_use_default_db(model):
            logger.debug(f"Model {model._meta.label} always uses default database")
            return 'default'
        
        # Route default apps to default database
        if app_label in self.default_apps:
            return 'default'
        
        # Route school apps to current school database
        if app_label in self.school_apps:
            # During makemigrations and system commands, return None
            if self._is_makemigrations_or_system_command():
                return None  # Let Django decide
            
            current_db = get_current_db()
            
            # Only use current_db if it's valid and not default
            if current_db and current_db in connections and current_db != 'default':
                logger.debug(f"Using database '{current_db}' for {model._meta.label}")
                return current_db
            
            # No valid database set
            if not self._error_logged:
                logger.warning(
                    f"No valid school database set for {app_label}. "
                    f"Current: {current_db}. Consider setting database in middleware."
                )
                self._error_logged = True
            
            # Try to find any school database as emergency fallback
            self._update_school_dbs()
            if self._school_dbs:
                emergency_db = list(self._school_dbs)[0]
                logger.warning(f"Using emergency fallback database: {emergency_db}")
                return emergency_db
            
            # Return None to let Django use model's default
            return None
        
        # Default fallback for unknown apps
        return 'default'

    def db_for_write(self, model, **hints):
        """Determine which database to write to"""
        app_label = model._meta.app_label
        
        # Check if this specific model should always use default
        if self._should_use_default_db(model):
            logger.debug(f"Model {model._meta.label} always writes to default database")
            return 'default'
        
        # Route default apps to default database
        if app_label in self.default_apps:
            return 'default'
        
        # Route school apps to current school database
        if app_label in self.school_apps:
            # During makemigrations and system commands, return None
            if self._is_makemigrations_or_system_command():
                return None
            
            current_db = get_current_db()
            
            if current_db and current_db in connections and current_db != 'default':
                logger.debug(f"Writing to database '{current_db}' for {model._meta.label}")
                return current_db
            
            # For writes, we're stricter - log error
            logger.error(
                f"No valid school database set for writing {model._meta.label}. "
                f"This write operation may fail. Current: {current_db}"
            )
            return None
        
        # Default fallback
        return 'default'
    
    def allow_relation(self, obj1, obj2, **hints):
        """Allow relations between specific models even across different databases"""
        app1 = obj1._meta.app_label
        app2 = obj2._meta.app_label
        
        # ALWAYS allow relations involving models that use default database
        if (self._should_use_default_db(obj1.__class__) or 
            self._should_use_default_db(obj2.__class__)):
            return True
        
        # Allow relations within the same database category
        if app1 in self.school_apps and app2 in self.school_apps:
            return True
            
        # Allow relations if both are in default apps
        if app1 in self.default_apps and app2 in self.default_apps:
            return True
        
        # Allow relations between default apps and school apps
        # (e.g., ForeignKey from school app to User model)
        if ((app1 in self.default_apps and app2 in self.school_apps) or
            (app2 in self.default_apps and app1 in self.school_apps)):
            return True
            
        # If unsure, allow Django to decide
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """Enhanced migration control with better school database routing"""
        
        # During makemigrations, only allow to default for file creation
        if 'makemigrations' in sys.argv:
            return db == 'default'
        
        # Check if this specific model should always be in default
        if model_name:
            model_label = f"{app_label}.{model_name}".lower()
            if model_label in self.always_default_models:
                logger.debug(f"Model {model_label} always migrates to default database")
                return db == 'default'
        
        # Update school databases list
        self._update_school_dbs()
        
        # DEFAULT_APPS: Only migrate to default database
        if app_label in self.default_apps:
            result = db == 'default'
            logger.debug(f"App '{app_label}' migrate to '{db}': {result}")
            return result
            
        # SCHOOL_APPS: Only migrate to school databases (NEVER to default)
        if app_label in self.school_apps:
            # CRITICAL: School apps should NEVER migrate to default
            if db == 'default':
                logger.debug(f"Blocking migration of school app '{app_label}' to default database")
                return False
            
            # Only allow migration to actual school databases
            is_school_db = db in self._school_dbs
            if not is_school_db:
                logger.debug(
                    f"Blocking migration of school app '{app_label}' "
                    f"to non-school database '{db}'"
                )
            else:
                logger.debug(f"Allowing migration of school app '{app_label}' to '{db}'")
            
            return is_school_db
            
        # Unknown apps: migrate to default
        logger.warning(f"Unknown app '{app_label}' migrating to default database")
        return db == 'default'