"""Scan a single profile once (diagnostics; uses the real collector)."""

from django.core.management.base import BaseCommand, CommandError

from apps.monitoring.models import SearchProfile


class Command(BaseCommand):
    help = "Scan one search profile immediately (one live request unless --fixture)."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--profile", required=True, help="SearchProfile UUID")
        parser.add_argument(
            "--fixture",
            default="",
            help="Use a named fixture instead of the live collector (local only).",
        )

    def handle(self, *args: object, **options) -> None:
        try:
            profile = SearchProfile.objects.get(pk=options["profile"])
        except (SearchProfile.DoesNotExist, ValueError, Exception) as exc:
            raise CommandError(f"Profile not found: {exc}")

        source: object
        fixture = options.get("fixture") or ""
        if fixture:
            from apps.monitoring.collectors.fixture_source import FixtureOlxSource

            source = FixtureOlxSource(search_fixture=fixture)
        else:
            from apps.monitoring.collectors.playwright_source import PlaywrightOlxSource

            source = PlaywrightOlxSource()

        from apps.monitoring.services import process_profile_scan

        try:
            run = process_profile_scan(profile, source)
        finally:
            source.close()
        self.stdout.write(
            f"run={run.id} status={run.status} found={run.found_count} "
            f"new={run.new_count} candidates={run.candidate_count} error={run.error_code or '-'}"
        )
        if run.status not in ("SUCCESS", "PARTIAL"):
            raise CommandError(f"Scan failed: {run.error_code}")
