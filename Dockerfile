# OLX iPhone Scout: one image for web and worker.
# Debian slim (not Alpine) because Playwright Chromium needs glibc.
FROM python:3.14-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl postgresql-client \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "uv>=0.5,<1"

# Install locked dependencies (including dev tools used by scripts/ci.sh).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# Install Chromium plus its system dependencies as root.
RUN python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

COPY . .

# Collect static files with build-only settings; manifest ships in the image.
RUN chmod +x scripts/*.sh && ./scripts/build.sh

# Non-root runtime user.
RUN groupadd --gid 10001 scout \
    && useradd --uid 10001 --gid scout --create-home scout \
    && chown -R scout:scout /app /opt/playwright-browsers

USER scout

ENTRYPOINT ["./scripts/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-"]
