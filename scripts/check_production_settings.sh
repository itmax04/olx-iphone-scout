#!/usr/bin/env bash
# Безопасная production-like проверка (§14.5): временные значения процесса,
# никаких реальных секретов, никаких сетевых запросов и миграций.
set -eu

cd "$(dirname "$0")/.."

if [ "${APP_ENV:-local}" = "production" ]; then
    echo "check_production_settings: отказ — уже production-окружение." >&2
    exit 1
fi

DB_URL="${DATABASE_URL:-postgresql://iphone_scout:change_me_local_only@db:5432/iphone_scout}"
DB_HOST="$(python - "$DB_URL" <<'PY'
import sys
from urllib.parse import urlsplit

print(urlsplit(sys.argv[1]).hostname or "")
PY
)"
case "$DB_HOST" in
    db|localhost|127.0.0.1) ;;
    *)
        echo "check_production_settings: отказ — host БД '$DB_HOST' не похож на локальный/CI." >&2
        exit 1
        ;;
esac

APP_ENV=production \
DJANGO_SETTINGS_MODULE=config.settings.production \
DJANGO_SECRET_KEY=test-only-not-a-real-secret-0123456789-abcdefghijklmnopqrstuvwxyz \
DJANGO_DEBUG=false \
DJANGO_ALLOWED_HOSTS=example.test \
DJANGO_CSRF_TRUSTED_ORIGINS=https://example.test \
APP_BASE_URL=https://example.test \
MONITOR_ENABLED=false \
AI_ENABLED=false \
SECURE_SSL_REDIRECT=true \
DATABASE_URL="$DB_URL" \
python manage.py check --deploy --fail-level WARNING --settings=config.settings.production

echo "check_production_settings: OK"
