# core/exchange_rate_fetcher.py

"""
Exchange rate fetch logic — shared by:
  - core/management/commands/update_exchange_rates.py  (cron / manual)
  - core/tasks.py                                       (Celery beat)
  - core/middleware.py                                  (background thread fallback)

Never import this from views or middleware directly in the request cycle.
"""

import json
import logging
from decimal import Decimal, InvalidOperation
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

from django.apps import apps
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PUBLIC ENTRY POINT
# ---------------------------------------------------------------------------

def fetch_and_save_rates(base_currency, target_currencies, school_db, date=None):
    """
    Fetch exchange rates for target_currencies relative to base_currency
    and save them to the ExchangeRate table in school_db.

    Tries APIs in order until one succeeds:
      1. ExchangeRate-API (free, no key required)
      2. Fixer.io         (requires FIXER_API_KEY in settings)
      3. OpenExchangeRates(requires OPENEXCHANGE_API_KEY in settings)

    Args:
        base_currency:     ISO 4217 code  (e.g. 'SSD', 'UGX')
        target_currencies: list of codes  (e.g. ['USD', 'UGX'])
        school_db:         database alias (e.g. 'atepi_palabek')
        date:              date to store against (default: today in UTC)

    Returns:
        dict: {'saved': int, 'failed': int, 'source': str or None}
    """
    if not target_currencies:
        logger.info(f"[{school_db}] No target currencies — nothing to fetch.")
        return {'saved': 0, 'failed': 0, 'source': None}

    date = date or timezone.now().date()

    fetchers = [
        _fetch_exchangerate_api,
        _fetch_fixer,
        _fetch_openexchange,
    ]

    for fetcher in fetchers:
        rates_data, source = fetcher(base_currency, target_currencies)
        if rates_data:
            result = _save_rates(base_currency, target_currencies, rates_data, date, source, school_db)
            return result

    logger.error(
        f"[{school_db}] All exchange rate APIs failed for {base_currency} "
        f"→ {target_currencies}"
    )
    return {'saved': 0, 'failed': len(target_currencies), 'source': None}


# ---------------------------------------------------------------------------
# FETCHERS — each returns (rates_dict, source_name) or (None, None)
# ---------------------------------------------------------------------------

def _fetch_exchangerate_api(base_currency, target_currencies):
    """ExchangeRate-API free tier — no key required."""
    url = f'https://open.exchangerate-api.com/v6/latest/{base_currency}'
    try:
        data = _get_json(url)
        if data and data.get('result') == 'success':
            rates = {
                k: v for k, v in data.get('rates', {}).items()
                if k in target_currencies
            }
            if rates:
                return rates, 'ExchangeRate-API'
            logger.warning(
                f"ExchangeRate-API: none of {target_currencies} found in response."
            )
    except Exception as e:
        logger.warning(f"ExchangeRate-API failed: {e}")
    return None, None


def _fetch_fixer(base_currency, target_currencies):
    """Fixer.io — requires FIXER_API_KEY in settings."""
    api_key = getattr(settings, 'FIXER_API_KEY', '')
    if not api_key:
        return None, None
    symbols = ','.join(target_currencies[:20])
    url = (
        f'http://data.fixer.io/api/latest'
        f'?access_key={api_key}&base={base_currency}&symbols={symbols}'
    )
    try:
        data = _get_json(url)
        if data and data.get('success'):
            rates = data.get('rates', {})
            if rates:
                return rates, 'Fixer.io'
    except Exception as e:
        logger.warning(f"Fixer.io failed: {e}")
    return None, None


def _fetch_openexchange(base_currency, target_currencies):
    """OpenExchangeRates — requires OPENEXCHANGE_API_KEY in settings."""
    api_key = getattr(settings, 'OPENEXCHANGE_API_KEY', '')
    if not api_key:
        return None, None
    symbols = ','.join(target_currencies[:20])
    url = (
        f'https://openexchangerates.org/api/latest.json'
        f'?app_id={api_key}&base={base_currency}&symbols={symbols}'
    )
    try:
        data = _get_json(url)
        if data and 'rates' in data:
            rates = data.get('rates', {})
            if rates:
                return rates, 'OpenExchangeRates'
    except Exception as e:
        logger.warning(f"OpenExchangeRates failed: {e}")
    return None, None


# ---------------------------------------------------------------------------
# SAVE
# ---------------------------------------------------------------------------

def _save_rates(base_currency, target_currencies, rates_data, date, source, school_db):
    """
    Upsert forward and inverse rates into the school DB.
    Returns {'saved': int, 'failed': int, 'source': str}
    """
    ExchangeRate = apps.get_model('core', 'ExchangeRate')
    saved = 0
    failed = 0

    for code in target_currencies:
        raw = rates_data.get(code)
        if raw is None:
            logger.debug(f"[{school_db}] No rate data for {code} from {source}")
            failed += 1
            continue

        try:
            rate = Decimal(str(raw))
            if rate <= 0:
                raise ValueError(f"Non-positive rate: {rate}")
        except (InvalidOperation, ValueError) as e:
            logger.warning(f"[{school_db}] Invalid rate for {code}: {raw} — {e}")
            failed += 1
            continue

        try:
            # Forward rate: base → code
            ExchangeRate.objects.using(school_db).update_or_create(
                from_currency=base_currency,
                to_currency=code,
                date=date,
                source=source,
                defaults={'rate': rate, 'is_active': True},
            )
            saved += 1

            # Inverse rate: code → base
            inverse = (Decimal('1') / rate).quantize(Decimal('0.000001'))
            ExchangeRate.objects.using(school_db).update_or_create(
                from_currency=code,
                to_currency=base_currency,
                date=date,
                source=f'{source} (inverse)',
                defaults={'rate': inverse, 'is_active': True},
            )
            saved += 1

        except Exception as e:
            logger.error(f"[{school_db}] DB error saving rate {base_currency}→{code}: {e}")
            failed += 1

    logger.info(
        f"[{school_db}] {source}: saved {saved} rates, failed {failed} "
        f"for {base_currency} → {target_currencies} on {date}"
    )
    return {'saved': saved, 'failed': failed, 'source': source}


# ---------------------------------------------------------------------------
# HTTP HELPER
# ---------------------------------------------------------------------------

def _get_json(url, timeout=15):
    req = Request(url)
    req.add_header('User-Agent', 'Schoolara/1.0')
    req.add_header('Accept', 'application/json')
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8'))