#!/usr/bin/env bash
# Локальный backup: pg_dump custom format + SHA-256 + безопасный manifest.
# Пишет только в backups/, никогда не включает .env.
set -eu

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"
if [ ! -f compose.yaml ]; then
    echo "backup_local: compose.yaml не найден — не тот каталог." >&2
    exit 1
fi

DB_NAME="${POSTGRES_DB:-iphone_scout}"
DB_USER="${POSTGRES_USER:-iphone_scout}"

mkdir -p backups
STAMP="$(date -u +%Y-%m-%dT%H%M%SZ)"
DUMP="backups/iphone_scout_${STAMP}.dump"

echo "==> pg_dump ${DB_NAME} -> ${DUMP}"
docker compose exec -T db pg_dump \
    --username "$DB_USER" \
    --format=custom --no-owner --no-acl \
    "$DB_NAME" > "$DUMP"

echo "==> SHA-256"
shasum -a 256 "$DUMP" > "${DUMP}.sha256"

echo "==> manifest"
{
    echo "created_utc=${STAMP}"
    echo "database=${DB_NAME}"
    echo "schema_migration=$(docker compose exec -T db psql -U "$DB_USER" -d "$DB_NAME" -Atc \
        "SELECT app || '.' || name FROM django_migrations ORDER BY id DESC LIMIT 1")"
    for table in monitoring_listing monitoring_searchprofile deals_deal \
                 analysis_evaluation alerts_notificationoutbox; do
        count=$(docker compose exec -T db psql -U "$DB_USER" -d "$DB_NAME" -Atc \
            "SELECT COUNT(*) FROM ${table}")
        echo "count_${table}=${count}"
    done
} > "backups/iphone_scout_${STAMP}.manifest.txt"

echo "backup_local: OK"
ls -lh "$DUMP" "${DUMP}.sha256" "backups/iphone_scout_${STAMP}.manifest.txt"
