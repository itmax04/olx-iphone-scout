#!/usr/bin/env bash
# Быстрая проверка live/ready локального приложения.
set -eu

BASE_URL="${1:-http://localhost:8000}"

echo "==> GET $BASE_URL/api/v1/health/live/"
curl -fsS "$BASE_URL/api/v1/health/live/"
echo

echo "==> GET $BASE_URL/api/v1/health/ready/"
curl -fsS "$BASE_URL/api/v1/health/ready/"
echo

echo "healthcheck: OK"
