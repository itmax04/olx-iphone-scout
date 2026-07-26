#!/usr/bin/env bash
# Shared container entrypoint: wait for the database, then exec the command.
# It intentionally does NOT run migrate/bootstrap; the one-shot `migrate`
# compose service (or Render pre-deploy) owns schema changes.
set -eu

python - <<'PY'
import os
import sys
import time

import psycopg

url = os.environ.get("DATABASE_URL", "")
if not url:
    print("entrypoint: DATABASE_URL is not set", file=sys.stderr)
    sys.exit(1)

deadline = time.monotonic() + 120
attempt = 0
while True:
    attempt += 1
    try:
        with psycopg.connect(url, connect_timeout=5) as conn:
            conn.execute("SELECT 1")
        print(f"entrypoint: database is reachable (attempt {attempt})")
        break
    except Exception:
        if time.monotonic() > deadline:
            print("entrypoint: database is not reachable after 120s", file=sys.stderr)
            sys.exit(1)
        time.sleep(2)
PY

exec "$@"
