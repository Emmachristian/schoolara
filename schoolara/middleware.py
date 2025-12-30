# schoolara/middleware.py

"""
Multi-tenant database middleware for School Management System.

This middleware:
1. Routes authenticated users to their school's database
2. Sets timezone in request context to prevent recursion
3. Handles superuser database overrides
4. Implements proper caching and error handling
5. Prevents cross-school data leakage

Key Features:
- Database routing based on user's school assignment
- Direct SQL queries for timezone to avoid model layer recursion
- Comprehensive caching to minimize database queries
- Safe fallbacks for all error conditions
- Superuser override capabilities for administration
"""

import logging
from django.core.cache import cache
from django.apps import apps
from django.contrib import messages
from django.conf import settings
from django.db import connections

from .managers import get_current_db, set_current_db, clear_current_db

logger = logging.getLogger(__name__)


class SchoolDatabaseMiddleware:
    """
    Universal, SAFE multi-tenant database middleware with timezone support.
    
    Database Selection Logic:
    1. System paths (/admin/, /static/, /media/) → 'default' database
    2. Authenticated users → School's database (from user.profile.school.database_alias)
    3. Superusers → Can override with ?db=<database_name>
    4. Fallback → 'default' database
    
    Timezone Handling:
    - Queries timezone directly from SchoolConfiguration table
    - Sets timezone in request.school_timezone for use by other components
    - Caches timezone to minimize database queries
    - Prevents recursion in BaseModel.save() by avoiding model layer
    """

    # Paths that always use 'default' database
    SYSTEM_PATHS = ['/admin/', '/static/', '/media/', '/__debug__/']
    
    # Cache timeout (1 hour)
    CACHE_TIMEOUT = 3600

    def __init__(self, get_response):
        self.get_response = get_response
        self.load_school_databases()

    # ==========================================================================
    # INITIALIZATION
    # ==========================================================================

    def load_school_databases(self):
        """
        Load list of available school databases on startup.
        This helps with validation and logging.
        """
        try:
            self.school_databases = self.get_available_school_databases()
            logger.info(f"SchoolDatabaseMiddleware loaded. School databases: {self.school_databases}")
        except Exception as e:
            logger.exception("Failed to load school databases")
            self.school_databases = []

    # ==========================================================================
    # MAIN REQUEST PROCESSING
    # ==========================================================================

    def __call__(self, request):
        """
        Process request and set appropriate database context.
        
        Flow:
        1. Save original database state
        2. Determine target database for this request
        3. Set database context and timezone
        4. Process request
        5. Restore original database state
        """
        # Save original database state
        original_db = get_current_db()
        request.original_db = original_db

        try:
            # Determine which database to use
            target_db = self.determine_database(request)

            if target_db and self.ensure_database_available(target_db):
                # Set database context if different from original
                if target_db != original_db:
                    set_current_db(target_db)
                    logger.debug(f"Switched database context to: {target_db}")
                
                request.current_db = target_db
                
                # ⭐ CRITICAL: Set timezone in request context
                # This prevents recursion in BaseModel.save() by making
                # timezone available without querying SchoolConfiguration model
                request.school_timezone = self.get_school_timezone_for_db(target_db)
                logger.debug(f"Set timezone to: {request.school_timezone}")
            else:
                # Fallback to default database
                set_current_db('default')
                request.current_db = 'default'
                request.school_timezone = 'Africa/Kampala'
                logger.debug("Using default database and timezone")

        except Exception as e:
            # On any error, fallback to default database
            logger.exception("SchoolDatabaseMiddleware failure - falling back to default")
            set_current_db('default')
            request.current_db = 'default'
            request.school_timezone = 'Africa/Kampala'

        # Process the request
        response = self.get_response(request)

        # Restore original database context
        if original_db:
            set_current_db(original_db)
        else:
            clear_current_db()

        return response

    # ==========================================================================
    # DATABASE DETERMINATION LOGIC
    # ==========================================================================

    def determine_database(self, request):
        """
        Determine which database should be used for this request.
        
        Returns:
            str: Database name to use
        """
        # System paths always use default database
        if self.is_system_path(request.path):
            return self.handle_system_path(request)

        # Authenticated users route to their school database
        if request.user.is_authenticated:
            return self.handle_authenticated_user(request)

        # Unauthenticated users use default database
        return 'default'

    def is_system_path(self, path):
        """Check if path is a system path that should use default database."""
        return any(path.startswith(p) for p in self.SYSTEM_PATHS)

    # ==========================================================================
    # SYSTEM PATH HANDLING
    # ==========================================================================

    def handle_system_path(self, request):
        """
        Handle system paths (admin, static, media).
        
        Superusers can override database even on system paths.
        """
        if request.user.is_authenticated and request.user.is_superuser:
            override = self.get_database_override(request)
            if override:
                return override
        
        return 'default'

    # ==========================================================================
    # AUTHENTICATED USER HANDLING
    # ==========================================================================

    def handle_authenticated_user(self, request):
        """
        Route authenticated users to their school's database.
        
        Returns:
            str: Database name for user's school
        """
        # Get user's school database
        user_db = self.get_user_school_database(request.user)

        # Superusers can override their school's database
        if request.user.is_superuser:
            return self.handle_superuser_access(request, user_db)

        # Regular users must use their assigned school database
        return self.handle_regular_user_access(request, user_db)

    # ==========================================================================
    # USER → SCHOOL → DATABASE RESOLUTION
    # ==========================================================================

    def get_user_school_database(self, user):
        """
        Get database name for user's school.
        
        This method:
        1. Checks user has a profile with school assigned
        2. Verifies school has active subscription
        3. Validates database exists in settings
        4. Returns database alias or None
        
        CRITICAL: School model is ALWAYS queried from 'default' database!
        
        Args:
            user: Django User object
            
        Returns:
            str or None: Database alias or None if not found
        """
        try:
            # Check if user has profile
            if not hasattr(user, 'profile'):
                logger.warning(f"User {user.username} has no profile")
                return None

            profile = user.profile
            school = profile.school

            if not school:
                logger.warning(f"User {user.username} has no school assigned")
                return None

            # Check cache first
            cache_key = f"user_school_db_{user.id}"
            cached_db = cache.get(cache_key)
            if cached_db:
                return cached_db

            # Verify school has active subscription
            if not school.is_active_subscription:
                logger.warning(f"Inactive subscription for school: {school.full_name}")
                return None

            # Get database alias from school
            db_alias = school.database_alias

            # Verify database exists in settings
            if db_alias not in settings.DATABASES:
                logger.error(
                    f"Database alias '{db_alias}' not found in settings for school: {school.full_name}"
                )
                return None

            # Cache the result
            cache.set(cache_key, db_alias, self.CACHE_TIMEOUT)
            
            logger.debug(f"Resolved database for user {user.username}: {db_alias}")
            return db_alias

        except Exception as e:
            logger.exception(f"Error resolving database for user {user.username}: {e}")
            return None

    # ==========================================================================
    # TIMEZONE RESOLUTION (PREVENTS RECURSION)
    # ==========================================================================

    def get_school_timezone_for_db(self, db_name):
        """
        Get timezone for a specific school database.
        
        CRITICAL: Uses direct SQL query to avoid model layer recursion!
        
        When BaseModel.save() tries to set timestamps, it calls
        get_school_current_time() which needs timezone. If we query
        SchoolConfiguration model, it triggers another save(), causing
        infinite recursion.
        
        Solution: Query timezone table directly with raw SQL.
        
        Args:
            db_name: Database name (e.g., 'atepi_palabek')
            
        Returns:
            str: Timezone string (e.g., 'Africa/Kampala')
        """
        # Default database always uses default timezone
        if not db_name or db_name == 'default':
            return 'Africa/Kampala'
        
        # Check cache first
        cache_key = f"school_tz_{db_name}"
        cached_tz = cache.get(cache_key)
        if cached_tz:
            return cached_tz
        
        try:
            # Query timezone directly from database using raw SQL
            # This bypasses the model layer and prevents recursion
            with connections[db_name].cursor() as cursor:
                cursor.execute(
                    "SELECT operational_timezone FROM core_schoolconfiguration WHERE id = 1 LIMIT 1"
                )
                row = cursor.fetchone()
                
                if row and row[0]:
                    tz_str = row[0]
                    # Cache for 1 hour
                    cache.set(cache_key, tz_str, self.CACHE_TIMEOUT)
                    logger.debug(f"Retrieved timezone for {db_name}: {tz_str}")
                    return tz_str
                else:
                    logger.warning(f"No SchoolConfiguration found in {db_name}, using default timezone")
                    
        except Exception as e:
            logger.debug(f"Could not get timezone for {db_name}: {e}")
        
        # Fallback to default timezone
        return 'Africa/Kampala'

    # ==========================================================================
    # SCHOOL LOOKUPS (CACHED)
    # ==========================================================================

    def get_database_by_school_id(self, school_id):
        """
        Get database alias by school ID.
        
        ALWAYS queries from 'default' database.
        
        Args:
            school_id: School UUID
            
        Returns:
            str or None: Database alias
        """
        cache_key = f"school_db_{school_id}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        try:
            School = apps.get_model('accounts', 'School')
            
            # CRITICAL: Always query School from 'default' database
            school = School.objects.using('default').filter(
                id=school_id,
                is_active_subscription=True
            ).first()

            if school:
                db_alias = school.database_alias
                if db_alias in settings.DATABASES:
                    cache.set(cache_key, db_alias, self.CACHE_TIMEOUT)
                    return db_alias

        except Exception as e:
            logger.exception(f"Error resolving database for school ID {school_id}: {e}")

        return None

    def get_database_by_email_domain(self, email):
        """
        Get database alias by email domain.
        
        ALWAYS queries from 'default' database.
        
        Args:
            email: Email address
            
        Returns:
            str or None: Database alias
        """
        if not email or '@' not in email:
            return None

        domain = email.split('@')[1].lower()
        cache_key = f"domain_db_{domain}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        try:
            School = apps.get_model('accounts', 'School')
            
            # CRITICAL: Always query School from 'default' database
            school = School.objects.using('default').filter(
                domain__iexact=domain,
                is_active_subscription=True
            ).first()

            if school:
                db_alias = school.database_alias
                if db_alias in settings.DATABASES:
                    cache.set(cache_key, db_alias, self.CACHE_TIMEOUT)
                    return db_alias

        except Exception as e:
            logger.exception(f"Error resolving database for email domain {domain}: {e}")

        return None

    # ==========================================================================
    # ACCESS CONTROL
    # ==========================================================================

    def handle_superuser_access(self, request, user_school_db):
        """
        Handle database routing for superusers.
        
        Superusers can:
        1. Override database with ?db=<database_name>
        2. Use their assigned school database
        3. Fall back to default
        
        Args:
            request: HTTP request
            user_school_db: User's school database (or None)
            
        Returns:
            str: Database to use
        """
        # Check for database override
        override = self.get_database_override(request)
        if override:
            return override

        # Use school database if available
        if user_school_db:
            return user_school_db
        
        # Fall back to default
        return 'default'

    def handle_regular_user_access(self, request, user_school_db):
        """
        Handle database routing for regular users.
        
        Regular users:
        1. CANNOT override database
        2. Must use their assigned school database
        3. Get error message if they try to override
        
        Args:
            request: HTTP request
            user_school_db: User's school database (or None)
            
        Returns:
            str: Database to use
        """
        # Block attempts to override database
        if 'db' in request.GET:
            messages.error(request, "You are not allowed to switch databases.")
            logger.warning(
                f"User {request.user.username} attempted unauthorized database override"
            )
        
        # Use school database or fall back to default
        return user_school_db or 'default'

    # ==========================================================================
    # DATABASE OVERRIDE (SUPERUSER ONLY)
    # ==========================================================================

    def get_database_override(self, request):
        """
        Get database override from query parameter or session.
        
        Superusers can switch databases by:
        1. Adding ?db=<database_name> to URL
        2. Using session-stored override from previous request
        
        Args:
            request: HTTP request
            
        Returns:
            str or None: Database override or None
        """
        # Check for ?db= parameter
        db_param = request.GET.get('db')

        if db_param and self.is_valid_database(db_param):
            # Store override in session for subsequent requests
            request.session['db_override'] = db_param
            logger.info(f"Database override set to: {db_param} by {request.user.username}")
            return db_param

        # Check session for stored override
        session_db = request.session.get('db_override')
        if session_db and self.is_valid_database(session_db):
            return session_db

        # Clear invalid override from session
        request.session.pop('db_override', None)
        return None

    # ==========================================================================
    # VALIDATION & UTILITIES
    # ==========================================================================

    def is_valid_database(self, db_name):
        """
        Check if database name is valid.
        
        Args:
            db_name: Database name to check
            
        Returns:
            bool: True if valid
        """
        return db_name in settings.DATABASES

    def ensure_database_available(self, db_name):
        """
        Ensure database connection is available and working.
        
        Args:
            db_name: Database name
            
        Returns:
            bool: True if available
        """
        try:
            connection = connections[db_name]
            connection.ensure_connection()
            return True
        except Exception as e:
            logger.error(f"Database '{db_name}' is unavailable: {e}", exc_info=True)
            return False

    def get_available_school_databases(self):
        """
        Get list of available school databases from settings.
        
        Returns:
            list: List of database names (excluding 'default' and 'test_*')
        """
        try:
            return [
                db for db in settings.DATABASES.keys()
                if db != 'default' and not db.startswith('test_')
            ]
        except Exception as e:
            logger.exception("Failed to list school databases")
            return []

    # ==========================================================================
    # CACHE MANAGEMENT
    # ==========================================================================

    @staticmethod
    def clear_database_cache():
        """
        Clear all database-related caches.
        
        Call this when:
        - School assignments change
        - Database configuration changes
        - Subscriptions are modified
        
        Usage:
            from schoolara.middleware import SchoolDatabaseMiddleware
            SchoolDatabaseMiddleware.clear_database_cache()
        """
        cache.delete_many([
            key for key in cache.keys() 
            if key.startswith(('user_school_db_', 'school_db_', 'domain_db_', 'school_tz_'))
        ])
        logger.info("Cleared database routing cache")

    @staticmethod
    def clear_user_cache(user_id):
        """
        Clear cache for specific user.
        
        Call this when user's school assignment changes.
        
        Args:
            user_id: User ID
            
        Usage:
            from schoolara.middleware import SchoolDatabaseMiddleware
            SchoolDatabaseMiddleware.clear_user_cache(user.id)
        """
        cache_key = f"user_school_db_{user_id}"
        cache.delete(cache_key)
        logger.debug(f"Cleared database cache for user {user_id}")

    @staticmethod
    def clear_timezone_cache(db_name):
        """
        Clear timezone cache for specific database.
        
        Call this when SchoolConfiguration timezone changes.
        
        Args:
            db_name: Database name
            
        Usage:
            from schoolara.middleware import SchoolDatabaseMiddleware
            SchoolDatabaseMiddleware.clear_timezone_cache('atepi_palabek')
        """
        cache_key = f"school_tz_{db_name}"
        cache.delete(cache_key)
        logger.debug(f"Cleared timezone cache for {db_name}")


# ==============================================================================
# UTILITY FUNCTIONS FOR MANUAL DATABASE CONTEXT MANAGEMENT
# ==============================================================================

def with_school_database(db_name):
    """
    Decorator to execute a function with specific database context.
    
    Usage:
        from schoolara.middleware import with_school_database
        
        @with_school_database('atepi_palabek')
        def get_student_count():
            return Student.objects.count()
        
        count = get_student_count()
    
    Args:
        db_name: Database name to use
        
    Returns:
        Decorated function
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            from .managers import DatabaseContext
            with DatabaseContext(db_name):
                return func(*args, **kwargs)
        return wrapper
    return decorator


def get_request_database(request):
    """
    Get the database being used for current request.
    
    Usage:
        from schoolara.middleware import get_request_database
        
        def my_view(request):
            db = get_request_database(request)
            logger.info(f"Using database: {db}")
    
    Args:
        request: HTTP request
        
    Returns:
        str: Database name or 'default'
    """
    return getattr(request, 'current_db', 'default')


def get_request_timezone(request):
    """
    Get the timezone being used for current request.
    
    Usage:
        from schoolara.middleware import get_request_timezone
        
        def my_view(request):
            tz = get_request_timezone(request)
            logger.info(f"Using timezone: {tz}")
    
    Args:
        request: HTTP request
        
    Returns:
        str: Timezone string or 'Africa/Kampala'
    """
    return getattr(request, 'school_timezone', 'Africa/Kampala')