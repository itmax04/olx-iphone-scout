#!/usr/bin/env bash
# Restore ТОЛЬКО в отдельную пустую тестовую БД iphone_scout_restore_test.
# Скрипт не удаляет и не пересоздает базы; --clean не используется; --force нет.
set -eu

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"
if [ ! -f compose.yaml ]; then
    echo "restore_local: compose.yaml не найден — не тот каталог." >&2
    exit 1
fi

if [ $# -ne 2 ]; then
    echo "Использование: $0 backups/<файл>.dump iphone_scout_restore_test" >&2
    exit 1
fi

DUMP="$1"
TARGET_DB="$2"
DB_USER="${POSTGRES_USER:-iphone_scout}"
MAIN_DB="${POSTGRES_DB:-iphone_scout}"

if [ "${APP_ENV:-local}" = "production" ]; then
    echo "restore_local: отказ — production-окружение." >&2
    exit 1
fi
if [ "$TARGET_DB" != "iphone_scout_restore_test" ]; then
    echo "restore_local: отказ — разрешена только БД iphone_scout_restore_test." >&2
    exit 1
fi
if [ "$TARGET_DB" = "$MAIN_DB" ]; then
    echo "restore_local: отказ — target совпадает с рабочей БД." >&2
    exit 1
fi
case "$DUMP" in
    backups/*.dump) ;;
    *)
        echo "restore_local: отказ — dump должен лежать в backups/." >&2
        exit 1
        ;;
esac
if [ ! -f "$DUMP" ]; then
    echo "restore_local: файл $DUMP не найден." >&2
    exit 1
fi

echo "==> Проверка контрольной суммы"
shasum -a 256 -c "${DUMP}.sha256"

echo "==> Проверка, что target существует и пуст"
EXISTS=$(docker compose exec -T db psql -U "$DB_USER" -d postgres -Atc \
    "SELECT 1 FROM pg_database WHERE datname = '$TARGET_DB'" || true)
if [ "$EXISTS" != "1" ]; then
    echo "restore_local: БД $TARGET_DB не существует. Создайте ее командой:" >&2
    echo "  docker compose exec db createdb -U $DB_USER $TARGET_DB" >&2
    exit 1
fi
TABLES=$(docker compose exec -T db psql -U "$DB_USER" -d "$TARGET_DB" -Atc \
    "SELECT COUNT(*) FROM pg_tables WHERE schemaname = 'public'")
if [ "$TABLES" != "0" ]; then
    echo "restore_local: отказ — target БД не пуста ($TABLES таблиц)." >&2
    exit 1
fi

echo "==> Проверка структуры архива (pg_restore --list)"
docker compose cp "$DUMP" db:/tmp/restore_check.dump
docker compose exec -T db pg_restore --list /tmp/restore_check.dump > /dev/null

echo "==> Восстановление в $TARGET_DB"
docker compose exec -T db pg_restore \
    --username "$DB_USER" \
    --dbname "$TARGET_DB" \
    --exit-on-error --no-owner --no-acl \
    /tmp/restore_check.dump
docker compose exec -T db rm -f /tmp/restore_check.dump

echo "==> Контрольные подсчеты"
for table in monitoring_listing deals_deal; do
    count=$(docker compose exec -T db psql -U "$DB_USER" -d "$TARGET_DB" -Atc \
        "SELECT COUNT(*) FROM ${table}")
    echo "count_${table}=${count}"
done

echo "RESTORE_VERIFY=PASS"
