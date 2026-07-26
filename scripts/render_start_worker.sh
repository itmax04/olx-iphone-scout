#!/usr/bin/env bash
# Worker никогда не применяет миграции: он ждет schema gate и запускается.
set -eu

python manage.py wait_for_schema --timeout 900
exec python manage.py run_monitor
