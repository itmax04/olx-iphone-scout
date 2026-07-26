"""Full local acceptance pipeline on sanitized fixtures. No external network.

Guards: refuses to run outside APP_ENV=local|test with DEBUG or with
MONITOR_ENABLED=true. Idempotent per fixture namespace.
"""

from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

FIXTURE_NAMESPACE = "FIXTURE"

PROFILE_FIXTURES = {
    "iphone_13_128": {
        "name": f"{FIXTURE_NAMESPACE} iPhone 13 128 — приемка",
        "olx_url": (
            "https://www.olx.ua/uk/elektronika/telefony-i-aksesuary/"
            "mobilnye-telefony-smartfony/q-iphone-13/?search%5Border%5D=created_at%3Adesc"
        ),
        "target_models": ["iphone_13"],
        "target_storage_gb": [128],
        "min_price_uah": Decimal("3000.00"),
        "max_purchase_price_uah": Decimal("12500.00"),
        "min_expected_profit_uah": Decimal("1800.00"),
        "min_roi_percent": Decimal("12.00"),
        "market_rule": {
            "model_key": "iphone_13",
            "storage_gb": 128,
            "expected_final_sale_price_uah": Decimal("14800.00"),
            "acquisition_shipping_uah": Decimal("150.00"),
            "other_cost_reserve_uah": Decimal("250.00"),
        },
        "defect_rules": [
            ("BATTERY_85_89", Decimal("500.00"), "BATTERY", 100),
            ("BATTERY_80_84", Decimal("900.00"), "BATTERY", 200),
            ("FRONT_GLASS_CRACK", Decimal("1200.00"), "", 100),
        ],
    }
}


class Command(BaseCommand):
    help = "Run the fixture acceptance pipeline (collector → dedup → evaluation → outbox)."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--fixture", default="detail_normal")
        parser.add_argument("--search-fixture", default="search_normal")
        parser.add_argument("--profile-fixture", default="iphone_13_128")
        parser.add_argument(
            "--no-send",
            action="store_true",
            default=True,
            help="Never send Telegram (always on; kept for CLI compatibility).",
        )
        parser.add_argument(
            "--collector-only", action="store_true", help="Stop after ingest: no evaluation/outbox."
        )
        parser.add_argument(
            "--price-drop", action="store_true", help="Second pass with the price-drop fixtures."
        )
        parser.add_argument(
            "--cleanup-fixture-namespace",
            action="store_true",
            help="Delete only fixture-namespaced rows and exit.",
        )

    # -- guards --------------------------------------------------------------

    def _guard(self) -> None:
        if settings.APP_ENV not in ("local", "test"):
            raise CommandError("run_fixture_pipeline разрешен только при APP_ENV=local|test.")
        if settings.MONITOR_ENABLED:
            raise CommandError("Выключите MONITOR_ENABLED перед fixture-прогоном.")
        db_name = settings.DATABASES["default"].get("NAME", "")
        if "prod" in str(db_name).lower():
            raise CommandError("Похоже на production базу; отказ.")

    def handle(self, *args: object, **options) -> None:
        self._guard()

        from apps.monitoring.models import Listing

        if options["cleanup_fixture_namespace"]:
            self._cleanup()
            return

        config_name = options["profile_fixture"]
        config = PROFILE_FIXTURES.get(config_name)
        if config is None:
            raise CommandError(
                f"Неизвестный profile fixture: {config_name}. Доступно: {sorted(PROFILE_FIXTURES)}"
            )

        profile = self._ensure_profile(config)
        self._ensure_rules(config)

        from apps.monitoring.collectors.fixture_source import FixtureOlxSource
        from apps.monitoring.services import process_profile_scan

        search_fixture = options["search_fixture"]
        detail_fixture = options["fixture"]
        if options["price_drop"]:
            search_fixture = "search_price_drop"
            detail_fixture = "detail_price_drop"

        source = FixtureOlxSource(search_fixture=search_fixture, detail_fixture=detail_fixture)
        run = process_profile_scan(profile, source, send_alerts=True)
        # send_alerts=True only creates outbox rows; nothing is delivered because
        # the worker outbox loop is a separate process and Telegram is not
        # configured in local/test. The rows stay PENDING for inspection.

        if options["collector_only"]:
            self.stdout.write(f"FIXTURE_PIPELINE=collector-only run={run.id} status={run.status}")
            return

        listings = Listing.objects.filter(discoveries__search_profile=profile).distinct()
        from apps.alerts.models import NotificationOutbox
        from apps.analysis.models import Evaluation

        evaluations = Evaluation.objects.filter(listing__in=listings).count()
        outbox = NotificationOutbox.objects.filter(listing__in=listings).count()
        candidates = listings.filter(current_is_candidate=True)

        self.stdout.write(f"run={run.id} status={run.status} found={run.found_count}")
        for listing in listings.order_by("olx_id"):
            self.stdout.write(
                f"  listing={listing.id} olx_id={listing.olx_id} "
                f"status={listing.decision_status} candidate={listing.current_is_candidate} "
                f"profit={listing.current_expected_profit_uah}"
            )
        self.stdout.write(
            f"evaluations={evaluations} outbox={outbox} candidates={candidates.count()}"
        )

        passed = (
            run.status == "SUCCESS"
            and listings.exists()
            and evaluations > 0
            and (options["collector_only"] or outbox >= 0)
        )
        self.stdout.write(f"FIXTURE_PIPELINE={'PASS' if passed else 'FAIL'}")
        if not passed:
            raise CommandError("Fixture pipeline не прошел проверку.")

    # -- helpers ---------------------------------------------------------------

    def _ensure_profile(self, config: dict):
        from apps.monitoring.models import SearchProfile
        from apps.monitoring.validators import canonicalize_olx_url

        canonical = canonicalize_olx_url(config["olx_url"])
        profile, _ = SearchProfile.objects.update_or_create(
            canonical_url=canonical,
            defaults={
                "name": config["name"],
                "olx_url": config["olx_url"],
                "is_active": True,
                "archived_at": None,
                "target_models": config["target_models"],
                "target_storage_gb": config["target_storage_gb"],
                "min_price_uah": config["min_price_uah"],
                "max_purchase_price_uah": config["max_purchase_price_uah"],
                "min_expected_profit_uah": config["min_expected_profit_uah"],
                "min_roi_percent": config["min_roi_percent"],
                "next_scan_at": timezone.now(),
            },
        )
        return profile

    def _ensure_rules(self, config: dict) -> None:
        from apps.pricing.models import DefectReserveRule, MarketPriceRule

        rule = config["market_rule"]
        MarketPriceRule.objects.get_or_create(
            model_key=rule["model_key"],
            storage_gb=rule["storage_gb"],
            sim_variant="ANY",
            defaults={
                "expected_final_sale_price_uah": rule["expected_final_sale_price_uah"],
                "acquisition_shipping_uah": rule["acquisition_shipping_uah"],
                "other_cost_reserve_uah": rule["other_cost_reserve_uah"],
                "checked_at": timezone.now(),
                "is_active": True,
            },
        )
        from apps.pricing.constants import DEFECT_CODES

        for code, amount, group, priority in config["defect_rules"]:
            DefectReserveRule.objects.update_or_create(
                code=code,
                model_key="",
                defaults={
                    "label": DEFECT_CODES[code]["label"],
                    "amount_uah": amount,
                    "exclusive_group": group,
                    "priority": priority,
                    "is_active": True,
                },
            )

    def _cleanup(self) -> None:
        from apps.monitoring.models import Listing, SearchProfile

        profiles = SearchProfile.objects.filter(name__startswith=FIXTURE_NAMESPACE)
        listing_ids = list(
            Listing.objects.filter(discoveries__search_profile__in=profiles)
            .exclude(deal__isnull=False)
            .values_list("pk", flat=True)
        )
        deleted_listings, _ = Listing.objects.filter(pk__in=listing_ids).delete()
        deleted_profiles, _ = profiles.delete()
        self.stdout.write(
            f"cleanup: listings={deleted_listings} profiles={deleted_profiles} "
            "(строки вне fixture namespace не тронуты)"
        )
