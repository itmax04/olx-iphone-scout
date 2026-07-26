"""Wait until the DB is reachable and all migrations are applied (no migrate)."""

import time

from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Wait for the database and a fully applied schema; never runs migrate."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--timeout", type=int, default=900)
        parser.add_argument("--interval", type=int, default=5)

    def handle(self, *args: object, **options) -> None:
        timeout = int(options["timeout"])
        interval = max(int(options["interval"]), 1)
        deadline = time.monotonic() + timeout

        while True:
            if self._schema_ready():
                self.stdout.write(self.style.SUCCESS("wait_for_schema: schema is ready"))
                return
            if time.monotonic() > deadline:
                raise CommandError(
                    f"wait_for_schema: схема не готова за {timeout} секунд; "
                    "проверьте pre-deploy миграции web-сервиса."
                )
            self.stdout.write("wait_for_schema: ожидание...")
            time.sleep(interval)

    def _schema_ready(self) -> bool:
        try:
            connection.close()
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            from django.db.migrations.executor import MigrationExecutor

            executor = MigrationExecutor(connection)
            plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
            if plan:
                return False
            from apps.core.models import AppState

            return AppState.objects.filter(pk=1).exists()
        except Exception:
            return False
