# core/middleware.py

"""
Exchange Rate Middleware

Lightweight staleness detector — does NOT fetch rates inline.

Flow:
    1. Request comes in on a financial page
    2. Check cache — if rates were checked recently, skip
    3. If stale, check ExchangeRate table for today's coverage
    4. If coverage is insufficient:
       a. If Celery is available → queue async task (non-blocking)
       b. Otherwise → log a warning (management command / cron handles it)
    5. Return response immediately — never block on API call

This middleware never makes an HTTP request to an exchange rate API.
That work belongs in:
    - management command:  python manage.py update_exchange_rates
    - Celery beat task:    core.tasks.update_exchange_rates_task (if Celery configured)
"""

import threading
import logging
from datetime import timedelta

from django.apps import apps
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

# Paths that deal with money — only check rates on these
_FINANCIAL_PATHS = (
    '/fees/',
    '/finance/',
    '/payments/',
    '/billing/',
    '/invoices/',
    '/uniforms/',
    '/core/currency/',
    '/core/exchange-rate/',
    '/admin/core/',
    '/admin/fees/',
    '/admin/finance/',
)

# How long to wait before re-checking the DB for staleness (seconds)
_STALENESS_CHECK_TTL = 3600  # 1 hour


class ExchangeRateMiddleware:
    """
    Detects stale exchange rates and triggers an async update if needed.
    Never blocks the request thread with network I/O.
    """

    def __init__(self, get_response):
        self.get_response  = get_response
        self._update_lock  = threading.Lock()

    def __call__(self, request):
        if self._should_check(request):
            self._check_and_maybe_trigger(request)
        return self.get_response(request)

    # -------------------------------------------------------------------------
    # GATE: is this request worth checking?
    # -------------------------------------------------------------------------

    def _should_check(self, request):
        """Only check on financial pages when school context exists."""
        if not any(request.path.startswith(p) for p in _FINANCIAL_PATHS):
            return False

        # SchoolDatabaseMiddleware must have run first
        school = getattr(request, 'school', None)
        if not school:
            return False

        # Only GET requests — don't slow down form POSTs
        if request.method != 'GET':
            return False

        return True

    # -------------------------------------------------------------------------
    # STALENESS DETECTION
    # -------------------------------------------------------------------------

    def _check_and_maybe_trigger(self, request):
        """Check staleness at most once per hour per school, non-blocking."""
        school    = request.school
        school_db = self._get_school_db()

        if not school_db or school_db == 'default':
            return

        cache_key = f'exrate_staleness_check_{school_db}'
        if cache.get(cache_key):
            return  # Checked recently — nothing to do

        # Acquire lock without blocking — skip if another thread is already checking
        if not self._update_lock.acquire(blocking=False):
            return

        try:
            cache.set(cache_key, True, timeout=_STALENESS_CHECK_TTL)
            self._evaluate_staleness(school, school_db)
        except Exception as e:
            logger.error(f"ExchangeRateMiddleware error for {school_db}: {e}")
        finally:
            self._update_lock.release()

    def _evaluate_staleness(self, school, school_db):
        """
        Check whether today's rates exist in the DB.
        If not, trigger an async update (or log a warning).
        """
        try:
            FinancialSettings = apps.get_model('core', 'FinancialSettings')
            settings = FinancialSettings.objects.using(school_db).filter(pk=1).first()

            if not settings:
                return

            if not settings.auto_update_exchange_rates:
                return  # Manual-only school — nothing to do

            currencies_needed = settings.get_currencies_needing_rates()
            if not currencies_needed:
                return  # No foreign currencies tracked

            # Check coverage for today
            today    = timezone.now().date()
            coverage = self._get_today_coverage(
                school_db, settings.school_currency, currencies_needed, today
            )

            expected    = len(currencies_needed)
            is_adequate = coverage >= max(1, int(expected * 0.8))  # 80% threshold

            if is_adequate:
                logger.debug(
                    f"[{school_db}] Exchange rates OK: "
                    f"{coverage}/{expected} currencies covered for {today}"
                )
                return

            logger.info(
                f"[{school_db}] Exchange rates stale: "
                f"{coverage}/{expected} currencies covered for {today}. "
                f"Triggering update."
            )
            self._trigger_update(school, school_db, settings)

        except Exception as e:
            logger.error(f"Error evaluating rate staleness for {school_db}: {e}")

    def _get_today_coverage(self, school_db, base_currency, currencies_needed, today):
        """Count how many of the needed currencies have a rate for today."""
        try:
            ExchangeRate = apps.get_model('core', 'ExchangeRate')
            return ExchangeRate.objects.using(school_db).filter(
                from_currency=base_currency,
                to_currency__in=currencies_needed,
                date=today,
                is_active=True,
            ).values('to_currency').distinct().count()
        except Exception as e:
            logger.warning(f"Could not check rate coverage in {school_db}: {e}")
            return 0

    # -------------------------------------------------------------------------
    # UPDATE TRIGGER — async if Celery available, otherwise warn
    # -------------------------------------------------------------------------

    def _trigger_update(self, school, school_db, settings):
        """
        Non-blocking: queue a Celery task if available, otherwise log a warning.
        The actual HTTP fetch to exchange rate APIs happens in the task/command,
        never here in the middleware.
        """
        # Try Celery first (non-blocking — fire and forget)
        if self._try_celery_task(school_db):
            return

        # Try threading as fallback (only if Celery is not configured)
        if self._try_threaded_update(school, school_db, settings):
            return

        # Last resort — just warn so the admin knows to run the command
        logger.warning(
            f"[{school_db}] Exchange rates are stale and no async mechanism "
            f"is configured. Run: python manage.py update_exchange_rates "
            f"--database {school_db}"
        )

    def _try_celery_task(self, school_db):
        """Attempt to queue a Celery task. Returns True if queued successfully."""
        try:
            from core.tasks import update_exchange_rates_task
            update_exchange_rates_task.delay(school_db)
            logger.info(f"[{school_db}] Queued Celery task to update exchange rates.")
            return True
        except ImportError:
            # core.tasks doesn't exist or Celery not installed — that's fine
            return False
        except Exception as e:
            logger.warning(f"[{school_db}] Could not queue Celery task: {e}")
            return False

    def _try_threaded_update(self, school, school_db, settings):
        """
        Fallback: run the fetch in a background thread.
        Only used when Celery is not available.
        Not suitable for production — use Celery or cron instead.
        """
        try:
            from core.exchange_rate_fetcher import fetch_and_save_rates
            thread = threading.Thread(
                target=self._run_threaded_fetch,
                args=(school, school_db, settings),
                daemon=True,
            )
            thread.start()
            logger.info(f"[{school_db}] Started background thread for exchange rate update.")
            return True
        except ImportError:
            return False
        except Exception as e:
            logger.warning(f"[{school_db}] Could not start background thread: {e}")
            return False

    def _run_threaded_fetch(self, school, school_db, settings):
        """Executed in background thread — isolated from the request."""
        try:
            from core.exchange_rate_fetcher import fetch_and_save_rates
            currencies = settings.get_currencies_needing_rates()
            fetch_and_save_rates(
                base_currency=settings.school_currency,
                target_currencies=currencies,
                school_db=school_db,
            )
            logger.info(f"[{school_db}] Background thread: exchange rates updated.")
        except Exception as e:
            logger.error(f"[{school_db}] Background thread fetch failed: {e}")

    # -------------------------------------------------------------------------
    # HELPERS
    # -------------------------------------------------------------------------

    @staticmethod
    def _get_school_db():
        """Get current school DB from thread-local routing context."""
        try:
            from schoolara.routers import get_current_db
            return get_current_db()
        except ImportError:
            try:
                from database_registry.routers import get_current_db
                return get_current_db()
            except ImportError:
                logger.debug("Could not import get_current_db — exchange rate check skipped.")
                return None

    # -------------------------------------------------------------------------
    # CLASS METHODS for management command / manual use
    # -------------------------------------------------------------------------

    @classmethod
    def force_check_school(cls, school, school_db):
        """
        Force a staleness check for a specific school.
        Called by the management command when --force is passed.
        """
        instance = cls(get_response=lambda r: r)
        try:
            FinancialSettings = apps.get_model('core', 'FinancialSettings')
            settings = FinancialSettings.objects.using(school_db).filter(pk=1).first()
            if settings:
                instance._evaluate_staleness(school, school_db)
        except Exception as e:
            logger.error(f"force_check_school failed for {school_db}: {e}")

    @classmethod
    def get_coverage_status(cls, school_db):
        """
        Return a dict describing today's rate coverage for a school DB.
        Used by the management command's --status flag and admin views.
        """
        try:
            today = timezone.now().date()
            FinancialSettings = apps.get_model('core', 'FinancialSettings')
            settings = FinancialSettings.objects.using(school_db).filter(pk=1).first()

            if not settings:
                return {'school_db': school_db, 'status': 'no_settings'}

            currencies_needed = settings.get_currencies_needing_rates()
            if not currencies_needed:
                return {
                    'school_db':          school_db,
                    'status':             'no_foreign_currencies',
                    'auto_update':        settings.auto_update_exchange_rates,
                    'school_currency':    settings.school_currency,
                }

            ExchangeRate = apps.get_model('core', 'ExchangeRate')
            covered = list(
                ExchangeRate.objects.using(school_db).filter(
                    from_currency=settings.school_currency,
                    to_currency__in=currencies_needed,
                    date=today,
                    is_active=True,
                ).values_list('to_currency', flat=True).distinct()
            )
            missing = [c for c in currencies_needed if c not in covered]

            return {
                'school_db':       school_db,
                'date':            today,
                'auto_update':     settings.auto_update_exchange_rates,
                'school_currency': settings.school_currency,
                'needed':          currencies_needed,
                'covered':         covered,
                'missing':         missing,
                'coverage_pct':    round(len(covered) / len(currencies_needed) * 100, 1),
                'status':          'ok' if not missing else 'stale',
            }
        except Exception as e:
            logger.error(f"get_coverage_status failed for {school_db}: {e}")
            return {'school_db': school_db, 'status': 'error', 'error': str(e)}