"""The single long-running worker: lock, loops, heartbeat, graceful shutdown.

No Celery/Redis. A session-level PostgreSQL advisory lock on a dedicated
connection guarantees at most one active worker.
"""

import logging
import signal
import socket
import time
import uuid

import psycopg
from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone

logger = logging.getLogger(__name__)


def _dsn_from_settings() -> str:
    db = settings.DATABASES["default"]
    host = db.get("HOST") or "localhost"
    port = db.get("PORT") or 5432
    return (
        f"host={host} port={port} dbname={db.get('NAME')} "
        f"user={db.get('USER')} password={db.get('PASSWORD')} connect_timeout=10"
    )


class AdvisoryLock:
    """Session-level advisory lock on its own psycopg connection."""

    def __init__(self, key: int) -> None:
        self.key = key
        self._conn: psycopg.Connection | None = None

    def try_acquire(self) -> bool:
        try:
            if self._conn is None or self._conn.closed:
                self._conn = psycopg.connect(_dsn_from_settings(), autocommit=True)
            with self._conn.cursor() as cur:
                cur.execute("SELECT pg_try_advisory_lock(%s)", (self.key,))
                row = cur.fetchone()
                return bool(row and row[0])
        except Exception:
            logger.warning("advisory_lock_connection_failed", extra={"event": "lock_conn_failed"})
            self._close()
            return False

    def is_alive(self) -> bool:
        if self._conn is None or self._conn.closed:
            return False
        try:
            with self._conn.cursor() as cur:
                cur.execute("SELECT 1")
            return True
        except Exception:
            self._close()
            return False

    def release(self) -> None:
        try:
            if self._conn is not None and not self._conn.closed:
                with self._conn.cursor() as cur:
                    cur.execute("SELECT pg_advisory_unlock(%s)", (self.key,))
        except Exception:  # pragma: no cover - connection loss releases the lock anyway
            pass
        finally:
            self._close()

    def _close(self) -> None:
        try:
            if self._conn is not None:
                self._conn.close()
        except Exception:  # pragma: no cover
            pass
        self._conn = None


class MonitorWorker:
    def __init__(self, *, source=None, max_cycles: int | None = None) -> None:
        self.instance_id = f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
        self.lock = AdvisoryLock(settings.WORKER_ADVISORY_LOCK_KEY)
        self.stop_requested = False
        self.max_cycles = max_cycles
        self._source = source
        self._last_heartbeat = 0.0
        self._last_refresh_check = 0.0
        self._last_outbox = 0.0
        self._last_cleanup_date = None

    # -- source lazy init (Playwright only when really needed) -------------

    def _get_source(self):
        if self._source is None:
            from apps.monitoring.collectors.playwright_source import PlaywrightOlxSource

            self._source = PlaywrightOlxSource()
        return self._source

    def request_stop(self, *_args: object) -> None:
        logger.info("worker_stop_requested", extra={"event": "worker_stop"})
        self.stop_requested = True

    # -- loops --------------------------------------------------------------

    def heartbeat(self) -> None:
        from apps.core.models import AppState

        AppState.objects.filter(pk=1).update(
            worker_heartbeat_at=timezone.now(), worker_instance_id=self.instance_id
        )

    def run_due_scan(self) -> bool:
        from apps.core.services import effective_monitoring
        from apps.monitoring.scheduler import select_due_profile
        from apps.monitoring.services import process_profile_scan

        if not effective_monitoring():
            return False
        profile = select_due_profile()
        if profile is None:
            return False
        logger.info(
            "scan_start",
            extra={"event": "scan_start", "search_profile_id": str(profile.id)},
        )
        run = process_profile_scan(profile, self._get_source())
        logger.info(
            "scan_finished",
            extra={
                "event": "scan_finished",
                "search_profile_id": str(profile.id),
                "scan_run_id": str(run.id),
                "error_code": run.error_code or None,
            },
        )
        return True

    def run_refresh_batch(self) -> int:
        from apps.core.services import effective_monitoring
        from apps.monitoring.services import refresh_listing, select_listings_for_refresh

        if not effective_monitoring():
            return 0
        listings = select_listings_for_refresh(limit=5)
        done = 0
        for listing in listings:
            if self.stop_requested:
                break
            try:
                refresh_listing(listing, self._get_source())
                done += 1
            except Exception:
                logger.warning(
                    "refresh_failed",
                    extra={"event": "refresh_failed", "listing_id": str(listing.id)},
                )
        return done

    def run_outbox(self) -> int:
        from apps.alerts.outbox import process_outbox_batch

        return process_outbox_batch()

    def run_pending_analyses(self) -> int:
        from apps.analysis.services import process_pending_analyses

        try:
            return process_pending_analyses()
        except Exception:
            logger.exception("pending_analyses_failed")
            return 0

    def run_cleanup_if_due(self) -> None:
        today = timezone.localdate()
        if self._last_cleanup_date == today:
            return
        self._last_cleanup_date = today
        from apps.core.cleanup import run_cleanup

        try:
            result = run_cleanup(confirm=True)
            logger.info(
                "retention_cleanup_done",
                extra={"event": "cleanup", "duration_ms": None},
            )
            logger.info("cleanup_result %s", result)
        except Exception:
            logger.exception("cleanup_failed")

    # -- main ---------------------------------------------------------------

    def run(self) -> None:
        signal.signal(signal.SIGTERM, self.request_stop)
        signal.signal(signal.SIGINT, self.request_stop)

        from apps.monitoring.services import recover_stuck_state

        logger.info(
            "worker_starting",
            extra={"event": "worker_starting"},
        )

        cycles = 0
        have_lock = False
        while not self.stop_requested:
            if self.max_cycles is not None and cycles >= self.max_cycles:
                break
            cycles += 1

            if not have_lock or not self.lock.is_alive():
                have_lock = self.lock.try_acquire()
                if not have_lock:
                    logger.info(
                        "worker_waiting_for_lock", extra={"event": "worker_waiting_for_lock"}
                    )
                    time.sleep(settings.WORKER_POLL_SECONDS)
                    continue
                logger.info("worker_lock_acquired", extra={"event": "worker_lock_acquired"})
                recover_stuck_state()
                self.heartbeat()
                self._last_heartbeat = time.monotonic()

            close_old_connections()
            now = time.monotonic()
            try:
                if now - self._last_heartbeat >= settings.WORKER_HEARTBEAT_SECONDS:
                    self.heartbeat()
                    self._last_heartbeat = now

                if now - self._last_outbox >= settings.OUTBOX_POLL_SECONDS:
                    self.run_outbox()
                    self._last_outbox = now

                worked = self.run_due_scan()
                self.run_pending_analyses()

                if now - self._last_refresh_check >= 60:
                    self.run_refresh_batch()
                    self._last_refresh_check = now

                self.run_cleanup_if_due()
            except Exception:
                logger.exception("worker_cycle_error")
                worked = False

            if not worked and not self.stop_requested:
                time.sleep(settings.WORKER_POLL_SECONDS)

        # Graceful shutdown
        try:
            if self._source is not None:
                self._source.close()
        except Exception:  # pragma: no cover
            pass
        self.lock.release()
        logger.info("worker_stopped", extra={"event": "worker_stopped"})
