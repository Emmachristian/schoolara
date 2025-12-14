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
    Universal, SAFE multi-tenant database middleware.

    ✔ Databases are selected via School.database_alias
    ✔ Email domains are for identity, NOT DB switching
    ✔ No cross-school data leakage
    ✔ Superuser override supported
    ✔ Caching preserved
    """

    SYSTEM_PATHS = ['/admin/', '/static/', '/media/', '/__debug__/']
    CACHE_TIMEOUT = 3600  # 1 hour

    def __init__(self, get_response):
        self.get_response = get_response
        self.load_school_databases()

    # ------------------------------------------------------------------
    # INITIAL LOAD
    # ------------------------------------------------------------------

    def load_school_databases(self):
        try:
            self.school_databases = self.get_available_school_databases()
            logger.info(f"Loaded school databases: {self.school_databases}")
        except Exception:
            logger.exception("Failed to load school databases")
            self.school_databases = []

    # ------------------------------------------------------------------
    # MAIN ENTRY
    # ------------------------------------------------------------------

    def __call__(self, request):
        original_db = get_current_db()
        request.original_db = original_db

        try:
            target_db = self.determine_database(request)

            if target_db and self.ensure_database_available(target_db):
                if target_db != original_db:
                    set_current_db(target_db)
                    logger.debug(f"Switched to database: {target_db}")
                request.current_db = target_db
            else:
                set_current_db('default')
                request.current_db = 'default'

        except Exception:
            logger.exception("SchoolDatabaseMiddleware failure")
            set_current_db('default')
            request.current_db = 'default'

        response = self.get_response(request)

        if original_db:
            set_current_db(original_db)
        else:
            clear_current_db()

        return response

    # ------------------------------------------------------------------
    # DATABASE DECISION
    # ------------------------------------------------------------------

    def determine_database(self, request):
        if self.is_system_path(request.path):
            return self.handle_system_path(request)

        if request.user.is_authenticated:
            return self.handle_authenticated_user(request)

        return 'default'

    def is_system_path(self, path):
        return any(path.startswith(p) for p in self.SYSTEM_PATHS)

    # ------------------------------------------------------------------
    # SYSTEM / ADMIN
    # ------------------------------------------------------------------

    def handle_system_path(self, request):
        if request.user.is_authenticated and request.user.is_superuser:
            override = self.get_database_override(request)
            if override:
                return override
        return 'default'

    # ------------------------------------------------------------------
    # AUTHENTICATED USERS
    # ------------------------------------------------------------------

    def handle_authenticated_user(self, request):
        user_db = self.get_user_school_database(request.user)

        if request.user.is_superuser:
            return self.handle_superuser_access(request, user_db)

        return self.handle_regular_user_access(request, user_db)

    # ------------------------------------------------------------------
    # USER → SCHOOL → DATABASE
    # ------------------------------------------------------------------

    def get_user_school_database(self, user):
        try:
            if not hasattr(user, 'userprofile'):
                return None

            profile = user.userprofile
            school = profile.school

            if not school:
                logger.warning(f"User {user.username} has no school assigned")
                return None

            if not school.is_active_subscription:
                logger.warning(f"Inactive subscription: {school.full_name}")
                return None

            db_alias = school.database_alias

            if db_alias not in settings.DATABASES:
                logger.error(
                    f"Database alias '{db_alias}' not found for {school.full_name}"
                )
                return None

            return db_alias

        except Exception:
            logger.exception("Error resolving user's school database")
            return None

    # ------------------------------------------------------------------
    # SCHOOL LOOKUPS (CACHED)
    # ------------------------------------------------------------------

    def get_database_by_school_id(self, school_id):
        cache_key = f"school_db_{school_id}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        try:
            School = apps.get_model('accounts', 'School')
            school = School.objects.filter(
                id=school_id,
                is_active_subscription=True
            ).first()

            if school:
                db_alias = school.database_alias
                if db_alias in settings.DATABASES:
                    cache.set(cache_key, db_alias, self.CACHE_TIMEOUT)
                    return db_alias

        except Exception:
            logger.exception(f"Error resolving DB for school ID {school_id}")

        return None

    def get_database_by_email_domain(self, email):
        if not email or '@' not in email:
            return None

        domain = email.split('@')[1].lower()
        cache_key = f"domain_db_{domain}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        try:
            School = apps.get_model('accounts', 'School')
            school = School.objects.filter(
                domain__iexact=domain,
                is_active_subscription=True
            ).first()

            if school:
                db_alias = school.database_alias
                if db_alias in settings.DATABASES:
                    cache.set(cache_key, db_alias, self.CACHE_TIMEOUT)
                    return db_alias

        except Exception:
            logger.exception(f"Error resolving DB for email domain {domain}")

        return None

    # ------------------------------------------------------------------
    # ACCESS CONTROL
    # ------------------------------------------------------------------

    def handle_superuser_access(self, request, user_school_db):
        override = self.get_database_override(request)
        if override:
            return override

        return user_school_db or 'default'

    def handle_regular_user_access(self, request, user_school_db):
        if 'db' in request.GET:
            messages.error(request, "You are not allowed to switch databases.")
            logger.warning(
                f"User {request.user.username} attempted DB override"
            )
        return user_school_db or 'default'

    # ------------------------------------------------------------------
    # OVERRIDE LOGIC
    # ------------------------------------------------------------------

    def get_database_override(self, request):
        db_param = request.GET.get('db')

        if db_param and self.is_valid_database(db_param):
            request.session['db_override'] = db_param
            logger.info(f"Database override set to: {db_param}")
            return db_param

        session_db = request.session.get('db_override')
        if session_db and self.is_valid_database(session_db):
            return session_db

        request.session.pop('db_override', None)
        return None

    # ------------------------------------------------------------------
    # VALIDATION / UTILITIES
    # ------------------------------------------------------------------

    def is_valid_database(self, db_name):
        return db_name in settings.DATABASES

    def ensure_database_available(self, db_name):
        try:
            connection = connections[db_name]
            connection.ensure_connection()
            return True
        except Exception:
            logger.error(f"Database '{db_name}' is unavailable", exc_info=True)
            return False

    def get_available_school_databases(self):
        try:
            return [
                db for db in settings.DATABASES.keys()
                if db != 'default' and not db.startswith('test_')
            ]
        except Exception:
            logger.exception("Failed to list school databases")
            return []
