#!/usr/bin/env bash
# Render pre-deploy: production check, migrations, idempotent bootstrap admin.
# Никакого collectstatic (static уже в image) и никаких значений env в выводе.
set -eu

python manage.py check --deploy --settings=config.settings.production
python manage.py migrate --noinput
python manage.py bootstrap_admin
