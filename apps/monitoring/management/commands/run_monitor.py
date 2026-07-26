"""Long-running monitor worker (web never runs this)."""

from django.core.management.base import BaseCommand

from apps.monitoring.worker import MonitorWorker


class Command(BaseCommand):
    help = "Run the continuous monitoring worker (scheduler, refresh, outbox, heartbeat)."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--max-cycles",
            type=int,
            default=None,
            help="Stop after N loop cycles (used by tests).",
        )

    def handle(self, *args: object, **options) -> None:
        worker = MonitorWorker(max_cycles=options.get("max_cycles"))
        worker.run()
