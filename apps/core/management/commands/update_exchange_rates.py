# core/management/commands/update_exchange_rates.py

"""
Management command — fetch and save exchange rates.

Usage
-----
# Update all schools that have auto_update_exchange_rates=True
python manage.py update_exchange_rates

# Update one specific school DB (ignores auto_update flag)
python manage.py update_exchange_rates --database atepi_palabek

# Force-update even if today's rates already exist
python manage.py update_exchange_rates --database atepi_palabek --force

# Print coverage report without fetching anything
python manage.py update_exchange_rates --status
python manage.py update_exchange_rates --status --database atepi_palabek

# Add a new currency to a school's tracked list, then fetch
python manage.py update_exchange_rates --add-currency USD --database atepi_palabek

File layout
-----------
core/
  management/
    __init__.py          (empty)
    commands/
      __init__.py        (empty)
      update_exchange_rates.py   ← this file
"""

import logging
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Fetch and save exchange rates for tracked currencies. "
        "Updates all school databases by default, or one specific DB with --database."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--database',
            metavar='DB_ALIAS',
            help='Target a specific school database (e.g. atepi_palabek). '
                 'Omit to update all non-default databases.',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Fetch even if today\'s rates already exist in the database.',
        )
        parser.add_argument(
            '--status',
            action='store_true',
            help='Print coverage report only — do not fetch anything.',
        )
        parser.add_argument(
            '--add-currency',
            metavar='CODE',
            dest='add_currency',
            help='Add a currency code to a school\'s tracked list before fetching '
                 '(requires --database).',
        )

    # -------------------------------------------------------------------------
    # ENTRY POINT
    # -------------------------------------------------------------------------

    def handle(self, *args, **options):
        db_alias     = options.get('database')
        force        = options.get('force', False)
        status_only  = options.get('status', False)
        add_currency = options.get('add_currency', '').upper().strip() if options.get('add_currency') else None

        # Validate --add-currency requires --database
        if add_currency and not db_alias:
            raise CommandError("--add-currency requires --database to specify which school.")

        databases = self._resolve_databases(db_alias)
        if not databases:
            raise CommandError(
                f"No valid school databases found. "
                f"Check DATABASES in settings.py — expected non-default aliases."
            )

        # --status: just print coverage, exit
        if status_only:
            self._print_status(databases)
            return

        # --add-currency: add to tracked list first
        if add_currency:
            self._add_currency(add_currency, db_alias)

        # Fetch rates
        self._run_updates(databases, force, ignore_auto_flag=bool(db_alias))

    # -------------------------------------------------------------------------
    # DATABASE RESOLUTION
    # -------------------------------------------------------------------------

    def _resolve_databases(self, db_alias):
        """Return list of DB aliases to update."""
        if db_alias:
            if db_alias not in settings.DATABASES:
                raise CommandError(
                    f"Database '{db_alias}' not found in settings.DATABASES. "
                    f"Available: {list(settings.DATABASES.keys())}"
                )
            if db_alias == 'default':
                raise CommandError("Cannot run exchange rate updates on the 'default' database.")
            return [db_alias]

        # All non-default databases
        return [db for db in settings.DATABASES if db != 'default']

    # -------------------------------------------------------------------------
    # STATUS REPORT
    # -------------------------------------------------------------------------

    def _print_status(self, databases):
        from core.middleware import ExchangeRateMiddleware

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\nExchange Rate Coverage — {timezone.now().date()}\n"
                f"{'=' * 55}"
            )
        )

        for db in databases:
            status = ExchangeRateMiddleware.get_coverage_status(db)
            self._print_db_status(db, status)

    def _print_db_status(self, db, status):
        s = status.get('status', 'unknown')

        if s == 'no_settings':
            self.stdout.write(f"\n  {db}: {self.style.WARNING('No FinancialSettings found')}")
            return

        if s == 'no_foreign_currencies':
            self.stdout.write(
                f"\n  {db}: {self.style.SUCCESS('OK')} — "
                f"no foreign currencies tracked "
                f"(base: {status.get('school_currency')}, "
                f"auto-update: {status.get('auto_update')})"
            )
            return

        if s == 'error':
            self.stdout.write(
                f"\n  {db}: {self.style.ERROR('ERROR')} — {status.get('error')}"
            )
            return

        colour = self.style.SUCCESS if s == 'ok' else self.style.WARNING
        pct    = status.get('coverage_pct', 0)

        self.stdout.write(f"\n  {db}:")
        self.stdout.write(f"    Base currency  : {status.get('school_currency')}")
        self.stdout.write(f"    Auto-update    : {status.get('auto_update')}")
        self.stdout.write(f"    Needed         : {status.get('needed')}")
        self.stdout.write(f"    Covered today  : {status.get('covered')}")
        if status.get('missing'):
            self.stdout.write(
                f"    Missing        : {self.style.WARNING(str(status.get('missing')))}"
            )
        self.stdout.write(f"    Coverage       : {colour(f'{pct}%')}")

    # -------------------------------------------------------------------------
    # ADD CURRENCY
    # -------------------------------------------------------------------------

    def _add_currency(self, code, db_alias):
        from django.apps import apps
        from schoolara.managers import DatabaseContext

        with DatabaseContext(db_alias):
            try:
                FinancialSettings = apps.get_model('core', 'FinancialSettings')
                fs = FinancialSettings.objects.using(db_alias).filter(pk=1).first()
                if not fs:
                    raise CommandError(f"No FinancialSettings found in {db_alias}.")

                if code == fs.school_currency:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  {code} is the school currency for {db_alias} — "
                            f"no rate tracking needed."
                        )
                    )
                    return

                added = fs.add_tracked_currency(code)
                if added:
                    self.stdout.write(
                        self.style.SUCCESS(f"  Added {code} to tracked currencies for {db_alias}.")
                    )
                else:
                    self.stdout.write(
                        f"  {code} already tracked for {db_alias} — no change."
                    )
            except CommandError:
                raise
            except Exception as e:
                raise CommandError(f"Error adding currency {code} to {db_alias}: {e}")

    # -------------------------------------------------------------------------
    # RUN UPDATES
    # -------------------------------------------------------------------------

    def _run_updates(self, databases, force, ignore_auto_flag):
        """Fetch and save rates for each database."""
        from django.apps import apps
        from schoolara.managers import DatabaseContext
        from core.exchange_rate_fetcher import fetch_and_save_rates

        total_saved  = 0
        total_failed = 0
        skipped      = 0

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\nUpdating exchange rates — {timezone.now().date()}"
                f"{' (FORCED)' if force else ''}\n"
                f"{'=' * 55}"
            )
        )

        for db in databases:
            self.stdout.write(f"\n  [{db}]")

            with DatabaseContext(db):
                try:
                    FinancialSettings = apps.get_model('core', 'FinancialSettings')
                    fs = FinancialSettings.objects.using(db).filter(pk=1).first()

                    if not fs:
                        self.stdout.write(
                            f"    {self.style.WARNING('No FinancialSettings — skipped.')}"
                        )
                        skipped += 1
                        continue

                    # Respect auto_update flag unless --database was explicitly given
                    if not ignore_auto_flag and not fs.auto_update_exchange_rates:
                        self.stdout.write(
                            f"    auto_update_exchange_rates=False — skipped. "
                            f"(use --database {db} to force)"
                        )
                        skipped += 1
                        continue

                    currencies = fs.get_currencies_needing_rates()
                    if not currencies:
                        self.stdout.write(
                            f"    No foreign currencies tracked — skipped."
                        )
                        skipped += 1
                        continue

                    # Skip if today's rates already exist (unless --force)
                    if not force and self._rates_exist_today(db, fs.school_currency, currencies):
                        self.stdout.write(
                            f"    Today's rates already exist for "
                            f"{currencies} — skipped. (use --force to re-fetch)"
                        )
                        skipped += 1
                        continue

                    self.stdout.write(
                        f"    Fetching {fs.school_currency} → {currencies} ..."
                    )
                    result = fetch_and_save_rates(
                        base_currency=fs.school_currency,
                        target_currencies=currencies,
                        school_db=db,
                    )

                    saved  = result.get('saved', 0)
                    failed = result.get('failed', 0)
                    source = result.get('source', 'unknown')

                    total_saved  += saved
                    total_failed += failed

                    if saved > 0:
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"    ✓ Saved {saved} rates via {source}"
                            )
                        )
                    if failed > 0:
                        self.stdout.write(
                            self.style.WARNING(f"    ⚠ Failed to save {failed} rates")
                        )
                    if saved == 0 and failed == 0:
                        self.stdout.write(
                            self.style.WARNING("    No rates returned from any API.")
                        )

                except Exception as e:
                    self.stderr.write(
                        self.style.ERROR(f"    ERROR: {e}")
                    )
                    logger.exception(f"update_exchange_rates failed for {db}")
                    total_failed += 1

        # Summary
        self.stdout.write(
            f"\n{'=' * 55}\n"
            f"  Done. "
            f"Saved: {self.style.SUCCESS(str(total_saved))}  "
            f"Failed: {self.style.WARNING(str(total_failed)) if total_failed else '0'}  "
            f"Skipped: {skipped}\n"
        )

    # -------------------------------------------------------------------------
    # HELPERS
    # -------------------------------------------------------------------------

    def _rates_exist_today(self, db, base_currency, currencies):
        """True if all tracked currencies already have a rate for today."""
        from django.apps import apps

        today = timezone.now().date()
        try:
            ExchangeRate = apps.get_model('core', 'ExchangeRate')
            covered = (
                ExchangeRate.objects
                .using(db)
                .filter(
                    from_currency=base_currency,
                    to_currency__in=currencies,
                    date=today,
                    is_active=True,
                )
                .values('to_currency')
                .distinct()
                .count()
            )
            return covered >= len(currencies)
        except Exception as e:
            logger.warning(f"Could not check existing rates in {db}: {e}")
            return False