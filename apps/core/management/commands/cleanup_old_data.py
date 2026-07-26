"""Retention cleanup CLI: dry-run по умолчанию, удаление только с --confirm."""

from django.core.management.base import BaseCommand, CommandError

from apps.core.cleanup import run_cleanup


class Command(BaseCommand):
    help = (
        "Delete expired technical rows (scan runs, audit, axes logs, sessions). "
        "Default is dry-run; pass --confirm to actually delete. "
        "Listings, snapshots, evaluations, AI analyses, outbox and deals are never touched."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("--dry-run", action="store_true", help="Только подсчет (default).")
        parser.add_argument("--confirm", action="store_true", help="Выполнить удаление.")

    def handle(self, *args: object, **options) -> None:
        if options["dry_run"] and options["confirm"]:
            raise CommandError("Выберите либо --dry-run, либо --confirm.")
        confirm = bool(options["confirm"])
        result = run_cleanup(confirm=confirm)
        mode = "DELETED" if confirm else "DRY-RUN"
        for key, value in result.items():
            self.stdout.write(f"{mode} {key}={value}")
        if not confirm:
            self.stdout.write("Ничего не удалено. Для удаления добавьте --confirm.")
