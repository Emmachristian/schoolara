import logging
from django.core.cache import cache
from django.apps import apps
from django.contrib import messages
from django.conf import settings
from django.db import connections

from .managers import get_current_db, set_current_db

logger = logging.getLogger(__name__)


class SchoolDatabaseMiddleware:
    """
    Universal middleware that works with ANY school database configuration.
    No hardcoded database names - completely dynamic and scalable.
    """
    
    # System paths that should always use default database
    SYSTEM_PATHS = ['/admin/', '/static/', '/media/', '/__debug__/']
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.cache_timeout = 3600  # 1 hour cache
        self.load_school_databases()
    
    def load_school_databases(self):
        """Load and cache available school databases"""
        try:
            self.school_databases = self.get_available_school_databases()
            logger.info(f"Loaded school databases: {self.school_databases}")
        except Exception as e:
            logger.error(f"Error loading school databases: {e}")
            self.school_databases = []
    
    def __call__(self, request):
        """Main middleware processing"""
        original_db = get_current_db()
        request.original_db = original_db
        
        try:
            # Determine target database
            target_db = self.determine_database(request)
            
            # Set the database if it's valid and different
            if target_db and self.ensure_database_available(target_db):
                if target_db != original_db:
                    set_current_db(target_db)
                    logger.debug(f"Switched to database: {target_db}")
                request.current_db = target_db
            else:
                # Fallback to default
                set_current_db('default')
                request.current_db = 'default'
                
        except Exception as e:
            logger.error(f"Middleware error: {e}", exc_info=True)
            set_current_db('default')
            request.current_db = 'default'
            
        # Process request
        response = self.get_response(request)
        
        # Restore original database (or clear if there wasn't one)
        if original_db:
            set_current_db(original_db)
        else:
            from .managers import clear_current_db
            clear_current_db()
        
        return response
    
    def determine_database(self, request):
        """Determine which database to use for this request"""
        
        # 1. Check if this is an admin/system path
        if self.is_system_path(request.path):
            return self.handle_system_path(request)
        
        # 2. Handle authenticated users
        if hasattr(request, 'user') and request.user.is_authenticated:
            return self.handle_authenticated_user(request)
        
        # 3. Unauthenticated users use default
        return 'default'
    
    def is_system_path(self, path):
        """Check if path is a system path"""
        return any(path.startswith(system_path) for system_path in self.SYSTEM_PATHS)
    
    def handle_system_path(self, request):
        """Handle system paths - use default unless superuser overrides"""
        if (hasattr(request, 'user') and 
            request.user.is_authenticated and 
            request.user.is_superuser):
            
            # Allow superuser to override for admin operations
            override_db = self.get_database_override(request)
            if override_db:
                return override_db
        
        return 'default'
    
    def handle_authenticated_user(self, request):
        """Handle database selection for authenticated users"""
        user = request.user
        
        # Get user's assigned school database
        user_school_db = self.get_user_school_database(user)
        
        if user.is_superuser:
            return self.handle_superuser_access(request, user_school_db)
        else:
            return self.handle_regular_user_access(request, user_school_db)
    
    def get_user_school_database(self, user):
        """Get the database name for user's school - UNIVERSAL approach"""
        try:
            # Method 1: Direct school relationship (most common)
            if hasattr(user, 'school') and user.school:
                if hasattr(user.school, 'is_active') and user.school.is_active:
                    db_name = user.school.db_name
                    logger.debug(f"Got database from user.school: {db_name}")
                    return db_name
                else:
                    logger.warning(f"User {user.email} has inactive school")
                    return None
            
            # Method 2: School ID lookup (if using FK instead of direct relation)
            if hasattr(user, 'school_id') and user.school_id:
                return self.get_database_by_school_id(user.school_id)
            
            # Method 3: Email domain mapping (fallback)
            if hasattr(user, 'email') and user.email:
                return self.get_database_by_email_domain(user.email)
            
            logger.debug(f"No school database found for user {getattr(user, 'email', user.username)}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting user school database: {e}", exc_info=True)
            return None
    
    def get_database_by_school_id(self, school_id):
        """Get database by school ID - works with any school model"""
        try:
            # Try to get from cache first
            cache_key = f"school_db_{school_id}"
            cached_db = cache.get(cache_key)
            if cached_db:
                return cached_db
            
            # Query the school model
            try:
                School = apps.get_model('database_registry', 'School')
            except LookupError:
                logger.warning("School model not found in database_registry app")
                return None
            
            school = School.objects.filter(id=school_id, is_active=True).first()
            
            if school and hasattr(school, 'db_name') and school.db_name:
                cache.set(cache_key, school.db_name, self.cache_timeout)
                return school.db_name
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting database by school ID {school_id}: {e}")
            return None
    
    def get_database_by_email_domain(self, email):
        """Get database by email domain - universal fallback"""
        try:
            if not email or '@' not in email:
                return None
            
            domain = email.split('@')[1].lower()
            
            # Try to get from cache
            cache_key = f"domain_db_{domain}"
            cached_db = cache.get(cache_key)
            if cached_db:
                return cached_db
            
            # Query schools with this email domain
            try:
                School = apps.get_model('database_registry', 'School')
            except LookupError:
                logger.warning("School model not found in database_registry app")
                return None
            
            school = School.objects.filter(
                email_domain__icontains=domain,
                is_active=True
            ).first()
            
            if school and hasattr(school, 'db_name') and school.db_name:
                cache.set(cache_key, school.db_name, self.cache_timeout)
                return school.db_name
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting database by email domain: {e}")
            return None
    
    def handle_superuser_access(self, request, user_school_db):
        """Handle database access for superusers"""
        # Check for explicit database override
        override_db = self.get_database_override(request)
        if override_db:
            return override_db
        
        # Use user's school database if available
        if user_school_db:
            return user_school_db
        
        # Default to default database for superusers
        return 'default'
    
    def handle_regular_user_access(self, request, user_school_db):
        """Handle database access for regular users"""
        # Block any override attempts
        if 'db' in request.GET:
            logger.warning(f"Regular user {getattr(request.user, 'email', request.user.username)} attempted database override")
            if hasattr(messages, 'error'):
                messages.error(request, "You cannot switch databases.")
        
        # Regular users can only use their assigned school database
        return user_school_db or 'default'
    
    def get_database_override(self, request):
        """Get database override for superusers"""
        # Check URL parameter
        db_param = request.GET.get('db')
        if db_param and self.is_valid_database(db_param):
            # Store in session for persistence
            request.session['db_override'] = db_param
            logger.info(f"Database override set to: {db_param}")
            return db_param
        
        # Check session override
        session_db = request.session.get('db_override')
        if session_db and self.is_valid_database(session_db):
            return session_db
        
        # Clear invalid override
        if 'db_override' in request.session:
            del request.session['db_override']
        
        return None
    
    def is_valid_database(self, db_name):
        """Check if database name is valid"""
        try:
            return db_name in settings.DATABASES
        except:
            return False
    
    def ensure_database_available(self, db_name):
        """Ensure database connection is available"""
        if not db_name:
            return False
        
        try:
            # Check if database is configured
            if db_name not in settings.DATABASES:
                logger.error(f"Database '{db_name}' not found in settings")
                return False
            
            # Try to ensure connection exists
            connection = connections[db_name]
            connection.ensure_connection()
            return True
            
        except Exception as e:
            logger.error(f"Database '{db_name}' is not available: {e}")
            return False
    
    def get_available_school_databases(self):
        """Get list of all available school databases"""
        try:
            return [
                db for db in settings.DATABASES.keys() 
                if db != 'default' and not db.startswith('test_')
            ]
        except Exception as e:
            logger.error(f"Error getting available databases: {e}")
            return []