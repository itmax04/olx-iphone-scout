#!/usr/bin/env bash
# Единый локальный CI-контракт (§17.1). GitHub Actions выполняет те же шаги.
set -eu

cd "$(dirname "$0")/.."

echo "==> ruff format --check"
ruff format --check .

echo "==> ruff check"
ruff check .

echo "==> mypy apps"
mypy apps

echo "==> makemigrations --check --dry-run"
python manage.py makemigrations --check --dry-run

echo "==> migrate --noinput"
python manage.py migrate --noinput

echo "==> pytest with coverage (fail under 80%)"
pytest --cov=apps --cov-report=term-missing --cov-fail-under=80 -q

echo "==> django check"
python manage.py check

echo "==> production-like settings check"
./scripts/check_production_settings.sh

echo "CI: OK"
