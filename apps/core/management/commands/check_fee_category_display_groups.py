# fees/management/commands/check_fee_category_display_groups.py
#
# Usage:
#   python manage.py check_fee_category_display_groups
#   python manage.py check_fee_category_display_groups --fix
#   python manage.py check_fee_category_display_groups --fix --fix-group=3
#   python manage.py check_fee_category_display_groups --database=atepi_palabek

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = "Report (and optionally fix) fee categories that have no display group assigned."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fix",
            action="store_true",
            default=False,
            help=(
                "Auto-assign a DisplayGroup to every category that lacks one. "
                "Uses --fix-group if supplied, otherwise the first active group "
                "ordered by display_order."
            ),
        )
        parser.add_argument(
            "--fix-group",
            type=int,
            metavar="PK",
            dest="fix_group",
            help="pk of the DisplayGroup to assign when using --fix.",
        )
        parser.add_argument(
            "--database",
            default=None,
            metavar="ALIAS",
            help=(
                "School database alias to query (e.g. atepi_palabek). "
                "Omit to use the thread-local school DB set by the router."
            ),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _qs(self, model, db):
        """Return a queryset for *model* optionally pinned to *db*."""
        qs = model.objects
        if db:
            qs = qs.using(db)
        return qs.all()

    def _section(self, title):
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(f"{'─' * 60}"))
        self.stdout.write(self.style.MIGRATE_HEADING(f"  {title}"))
        self.stdout.write(self.style.MIGRATE_HEADING(f"{'─' * 60}"))

    # ------------------------------------------------------------------
    # Main
    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        from fees.models import FeesCategory, DisplayGroup

        db        = options["database"]
        do_fix    = options["fix"]
        fix_group = options["fix_group"]

        db_label = db or "default router"
        self._section(f"Fee Category Display-Group Check  [{db_label}]")

        # ── Totals ──────────────────────────────────────────────────────
        all_cats      = self._qs(FeesCategory, db)
        total         = all_cats.count()
        active        = all_cats.filter(is_active=True).count()
        inactive      = total - active
        missing_qs    = all_cats.filter(display_group__isnull=True)
        missing_total = missing_qs.count()
        ok_count      = total - missing_total

        self.stdout.write("")
        self.stdout.write(f"  Total categories   : {total}")
        self.stdout.write(f"  Active             : {active}")
        self.stdout.write(f"  Inactive           : {inactive}")
        self.stdout.write(f"  Have display group : {ok_count}")
        self.stdout.write(
            "  Missing group      : "
            + (self.style.ERROR(str(missing_total)) if missing_total else self.style.SUCCESS("0"))
        )

        # ── Available display groups ────────────────────────────────────
        self._section("Available Display Groups")
        groups = (
            self._qs(DisplayGroup, db)
            .filter(is_active=True)
            .order_by("display_order", "name")
        )
        if not groups.exists():
            self.stdout.write(self.style.WARNING("  No active display groups found!"))
        else:
            self.stdout.write(f"  {'uuid (short)':<38} {'order':<6} name")
            self.stdout.write(f"  {'────────────':<38} {'─────':<6} ────")
            for g in groups:
                self.stdout.write(f"  {str(g.pk):<38} {g.display_order:<6} {g.name}")

        # ── Early exit if nothing is missing ────────────────────────────
        if not missing_total:
            self._section("Result")
            self.stdout.write(self.style.SUCCESS("  ✓ All fee categories have a display group."))
            self.stdout.write("")
            return

        # ── List the offenders ──────────────────────────────────────────
        self._section(f"Categories Missing a Display Group  ({missing_total})")
        self.stdout.write(
            f"  {'uuid (short)':<38} {'code':<12} {'active':<8} {'type':<16} name"
        )
        self.stdout.write(
            f"  {'────────────':<38} {'────':<12} {'──────':<8} {'────':<16} ────"
        )
        for cat in missing_qs.order_by("category_type", "name"):
            active_flag = "yes" if cat.is_active else "no"
            self.stdout.write(
                f"  {str(cat.pk):<38} {cat.code:<12} {active_flag:<8} "
                f"{cat.category_type:<16} {cat.name}"
            )

        # ── Fix ─────────────────────────────────────────────────────────
        if not do_fix:
            self._section("Next Steps")
            self.stdout.write(
                "  Run with  --fix                    to auto-assign the first group."
            )
            self.stdout.write(
                "  Run with  --fix --fix-group=<pk>   to assign a specific group."
            )
            self.stdout.write("")
            # Non-zero exit so CI/CD pipelines can detect the issue.
            raise SystemExit(1)

        # Resolve which group to assign
        if fix_group:
            try:
                target_group = self._qs(DisplayGroup, db).get(pk=fix_group)
            except DisplayGroup.DoesNotExist:
                raise CommandError(
                    f"DisplayGroup pk={fix_group} does not exist "
                    f"in database '{db_label}'."
                )
        else:
            target_group = groups.first()
            if not target_group:
                raise CommandError(
                    "No active DisplayGroup found to assign. "
                    "Create one first or pass --fix-group=<pk>."
                )

        self._section(
            f"Fixing: assigning '{target_group.name}' (pk={target_group.pk}) "
            f"to {missing_total} categor{'y' if missing_total == 1 else 'ies'}"
        )

        using = db or "default"
        with transaction.atomic(using=using):
            updated = missing_qs.update(display_group=target_group)

        self.stdout.write(
            self.style.SUCCESS(
                f"  ✓ {updated} categor{'y' if updated == 1 else 'ies'} updated."
            )
        )

        # ── Verification pass ───────────────────────────────────────────
        still_missing = (
            self._qs(FeesCategory, db).filter(display_group__isnull=True).count()
        )
        self._section("Post-Fix Verification")
        if still_missing:
            self.stdout.write(
                self.style.ERROR(
                    f"  ✗ {still_missing} categor(ies) still have no display group."
                )
            )
            raise SystemExit(1)
        else:
            self.stdout.write(
                self.style.SUCCESS("  ✓ All fee categories now have a display group.")
            )

        self.stdout.write("")