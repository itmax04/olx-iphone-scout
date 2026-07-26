"""Refresh a single known listing's detail page."""

from django.core.management.base import BaseCommand, CommandError

from apps.monitoring.models import Listing


class Command(BaseCommand):
    help = "Re-fetch one listing detail page and re-evaluate it."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--listing", required=True, help="Listing UUID")
        parser.add_argument(
            "--fixture",
            default="",
            help="Use a named detail fixture instead of the live collector (local only).",
        )

    def handle(self, *args: object, **options) -> None:
        try:
            listing = Listing.objects.get(pk=options["listing"])
        except (Listing.DoesNotExist, ValueError, Exception) as exc:
            raise CommandError(f"Listing not found: {exc}")

        source: object
        fixture = options.get("fixture") or ""
        if fixture:
            from apps.monitoring.collectors.fixture_source import FixtureOlxSource

            source = FixtureOlxSource(detail_fixture=fixture)
        else:
            from apps.monitoring.collectors.playwright_source import PlaywrightOlxSource

            source = PlaywrightOlxSource()

        from apps.monitoring.services import refresh_listing

        try:
            outcome = refresh_listing(listing, source)
        finally:
            source.close()
        self.stdout.write(f"listing={listing.id} outcome={outcome}")
