"""Runtime diagnostics: DB, schema, AppState, effective switches. Exit != 0 on failure."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Verify DB connectivity, applied schema, AppState and runtime switches."

    def handle(self, *args: object, **options: object) -> None:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except Exception as exc:
            raise CommandError(f"database: unavailable ({type(exc).__name__})")
        self.stdout.write("database: ok")

        from django.db.migrations.executor import MigrationExecutor

        executor = MigrationExecutor(connection)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        if plan:
            raise CommandError(f"schema: {len(plan)} непримененных миграций")
        self.stdout.write("schema: current")

        from apps.core.models import AppState

        if not AppState.objects.filter(pk=1).exists():
            raise CommandError("app_state: missing (запустите migrate)")
        self.stdout.write("app_state: ok")

        from apps.core.services import effective_ai, effective_monitoring, worker_status

        self.stdout.write(f"monitor_env_enabled: {settings.MONITOR_ENABLED}")
        self.stdout.write(f"effective_monitoring: {effective_monitoring()}")
        self.stdout.write(f"ai_env_enabled: {settings.AI_ENABLED}")
        self.stdout.write(f"effective_ai: {effective_ai()}")
        self.stdout.write(f"worker_status: {worker_status()}")
        self.stdout.write(f"openai_configured: {bool(settings.OPENAI_API_KEY)}")
        telegram_ready = bool(settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID)
        self.stdout.write(f"telegram_configured: {telegram_ready}")
        self.stdout.write(self.style.SUCCESS("check_runtime: OK"))
