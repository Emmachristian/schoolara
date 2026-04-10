# core/tasks.py

"""
Celery tasks for core app.

Requires Celery to be installed and configured in schoolara/celery.py.
If Celery is not installed, this module is never imported — the middleware
and management command handle scheduling through other means.
"""

import logging
from django.conf import settings

logger = logging.getLogger(__name__)

try:
    from celery import shared_task
    _CELERY_AVAILABLE = True
except ImportError:
    _CELERY_AVAILABLE = False
    # Define a no-op decorator so the module loads without Celery
    def shared_task(*args, **kwargs):
        def decorator(func):
            func.delay = func
            func.apply_async = lambda *a, **kw: func(*a, **kw)
            return func
        return decorator if args and callable(args[0]) else decorator


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=300,   # retry after 5 minutes
    name='core.update_exchange_rates',
)
def update_exchange_rates_task(self, school_db=None):
    """
    Fetch and save exchange rates for one or all school databases.

    Args:
        school_db: specific DB alias to update, or None for all school DBs

    Called by:
      - core/middleware.py   when rates are stale and Celery is available
      - Celery beat schedule (see CELERY_BEAT_SCHEDULE in settings)
    """
    from schoolara.managers import DatabaseContext

    databases = _get_target_databases(school_db)
    if not databases:
        logger.warning("update_exchange_rates_task: no target databases found.")
        return {'updated': 0, 'failed': 0}

    updated = 0
    failed  = 0

    for db in databases:
        try:
            with DatabaseContext(db):
                result = _update_one_database(db)
            if result:
                updated += 1
            else:
                failed += 1
        except Exception as exc:
            logger.error(f"update_exchange_rates_task failed for {db}: {exc}")
            failed += 1
            # Retry the whole task if something unexpected happened
            try:
                raise self.retry(exc=exc)
            except self.MaxRetriesExceededError:
                logger.error(f"Max retries exceeded for exchange rate update on {db}")

    logger.info(f"update_exchange_rates_task done: {updated} updated, {failed} failed.")
    return {'updated': updated, 'failed': failed}


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _get_target_databases(school_db=None):
    """Return list of DB aliases to update."""
    if school_db:
        if school_db not in settings.DATABASES:
            logger.warning(f"Database '{school_db}' not found in settings.")
            return []
        return [school_db]

    # All non-default databases
    return [db for db in settings.DATABASES if db != 'default']


def _update_one_database(db):
    """
    Fetch and save rates for one school database.
    Returns True on success, False if settings not found or no currencies tracked.
    """
    from django.apps import apps
    from core.exchange_rate_fetcher import fetch_and_save_rates

    try:
        FinancialSettings = apps.get_model('core', 'FinancialSettings')
        fs = FinancialSettings.objects.using(db).filter(pk=1).first()

        if not fs:
            logger.warning(f"[{db}] No FinancialSettings found — skipping.")
            return False

        if not fs.auto_update_exchange_rates:
            logger.debug(f"[{db}] auto_update_exchange_rates=False — skipping.")
            return False

        currencies = fs.get_currencies_needing_rates()
        if not currencies:
            logger.debug(f"[{db}] No foreign currencies tracked — skipping.")
            return False

        result = fetch_and_save_rates(
            base_currency=fs.school_currency,
            target_currencies=currencies,
            school_db=db,
        )
        return result['saved'] > 0

    except Exception as e:
        logger.error(f"[{db}] _update_one_database error: {e}")
        return False