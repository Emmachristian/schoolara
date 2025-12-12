from django.db import models, connections
from threading import local
import logging

logger = logging.getLogger(__name__)

_thread_locals = local()

def get_current_db():
    """Get the current database name for this thread"""
    return getattr(_thread_locals, 'current_db', None)

def set_current_db(db):
    """Set the current database name for this thread"""
    # Validate database exists
    if db and db not in connections:
        logger.warning(f"Attempted to set invalid database: {db}")
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
        
        # If no database is set or it's 'default', use the model's default
        if not current_db or current_db == 'default':
            return super().get_queryset()
        
        # Validate database exists
        if current_db not in connections:
            logger.error(f"Invalid database '{current_db}' for {self.model._meta.label}")
            return super().get_queryset()
        
        return super().get_queryset().using(current_db)