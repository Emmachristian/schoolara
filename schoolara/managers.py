# managers.py

from django.db import models, connections, router
from django.conf import settings
from threading import local
import logging

logger = logging.getLogger(__name__)

_thread_locals = local()


def get_current_db():
    """Get the current database name for this thread"""
    return getattr(_thread_locals, 'current_db', None)


def set_current_db(db):
    """Set the current database name for this thread"""
    if not db:
        return False
    
    if db not in settings.DATABASES:
        logger.warning(f"Database '{db}' not found in settings")
        return False
    
    _thread_locals.current_db = db
    logger.debug(f"Set current_db to: {db}")
    return True


def clear_current_db():
    """Clear the current database setting"""
    if hasattr(_thread_locals, 'current_db'):
        delattr(_thread_locals, 'current_db')


class DatabaseContext:
    """Context manager for temporarily switching databases"""
    
    def __init__(self, db_name):
        self.db_name = db_name
        self.previous_db = None
    
    def __enter__(self):
        self.previous_db = get_current_db()
        set_current_db(self.db_name)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.previous_db:
            set_current_db(self.previous_db)
        else:
            clear_current_db()


class SchoolManager(models.Manager):
    """Manager that automatically uses the current school database"""
    
    def get_queryset(self):
        current_db = get_current_db()
        
        if not current_db or current_db == 'default':
            return super().get_queryset()
        
        if current_db not in connections:
            logger.error(f"Invalid database '{current_db}'")
            return super().get_queryset()
        
        return super().get_queryset().using(current_db)
    
    # Override all creation methods to use current database
    def create(self, **kwargs):
        return self.get_queryset().create(**kwargs)
    
    def bulk_create(self, objs, **kwargs):
        return self.get_queryset().bulk_create(objs, **kwargs)
    
    def get_or_create(self, **kwargs):
        return self.get_queryset().get_or_create(**kwargs)
    
    def update_or_create(self, **kwargs):
        return self.get_queryset().update_or_create(**kwargs)

# ==============================================================================
# STANDALONE MANAGERS (if you don't want to change base class)
# ==============================================================================

class DefaultDatabaseManager(models.Manager):
    """Manager that ALWAYS uses default database"""
    
    def get_queryset(self):
        return super().get_queryset().using('default')
    
    def create(self, **kwargs):
        return self.get_queryset().create(**kwargs)
    
    def bulk_create(self, objs, **kwargs):
        return self.get_queryset().bulk_create(objs, **kwargs)
    
    def get_or_create(self, **kwargs):
        return self.get_queryset().get_or_create(**kwargs)
    
    def update_or_create(self, **kwargs):
        return self.get_queryset().update_or_create(**kwargs)


# ==============================================================================
# UTILITY FUNCTIONS
# ==============================================================================

def with_database(db_name):
    """
    Decorator to execute a function with a specific database context.
    
    Example:
        @with_database('school_abc')
        def get_students():
            return list(Student.objects.all())
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            with DatabaseContext(db_name):
                return func(*args, **kwargs)
        return wrapper
    return decorator


def execute_on_all_school_databases(func, *args, **kwargs):
    """
    Execute a function on all school databases.
    
    Example:
        def count_students():
            return Student.objects.count()
        
        results = execute_on_all_school_databases(count_students)
        # Returns: {'school_abc': 150, 'school_xyz': 200}
    """
    results = {}
    school_dbs = [
        db for db in settings.DATABASES.keys()
        if db.startswith('school_')
    ]
    
    for db in school_dbs:
        try:
            with DatabaseContext(db):
                results[db] = func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error on database '{db}': {e}")
            results[db] = None
    
    return results

