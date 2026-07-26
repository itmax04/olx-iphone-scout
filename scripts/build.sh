#!/usr/bin/env bash
# Collect static files during the Docker image build using build-only settings.
set -eu

APP_ENV=build \
DJANGO_SETTINGS_MODULE=config.settings.build \
DJANGO_SECRET_KEY=build-only-not-a-runtime-secret \
python manage.py collectstatic --noinput
