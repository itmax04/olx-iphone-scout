#!/usr/bin/env bash
# Secret scan (§13.13): Gitleaks по рабочему дереву и истории Git.
# Использует локальный gitleaks либо pinned Docker image; без обеих опций
# завершается с ошибкой, а не «пропускает» проверку.
set -eu

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [ ! -d "$PROJECT_ROOT/.git" ]; then
    echo "secret_scan: $PROJECT_ROOT не является git-репозиторием." >&2
    exit 1
fi

GITLEAKS_IMAGE="zricethezav/gitleaks:v8.30.1"

run_with_binary() {
    gitleaks git --redact --no-banner "$PROJECT_ROOT"
    gitleaks dir --redact --no-banner "$PROJECT_ROOT"
}

run_with_docker() {
    docker run --rm -v "$PROJECT_ROOT:/repo:ro" "$GITLEAKS_IMAGE" \
        git --redact --no-banner /repo
    docker run --rm -v "$PROJECT_ROOT:/repo:ro" "$GITLEAKS_IMAGE" \
        dir --redact --no-banner /repo
}

if command -v gitleaks >/dev/null 2>&1; then
    run_with_binary
elif command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    run_with_docker
else
    echo "secret_scan: нет ни gitleaks, ни работающего Docker — проверка НЕ выполнена." >&2
    exit 1
fi

echo "secret_scan: утечек не найдено."
