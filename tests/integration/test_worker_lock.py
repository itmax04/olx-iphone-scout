"""I-13/I-14: PostgreSQL advisory lock — второй worker не работает."""

import pytest

from apps.monitoring.worker import AdvisoryLock

pytestmark = pytest.mark.django_db

TEST_KEY = 987_654_321_000_111


def test_second_lock_holder_waits():
    first = AdvisoryLock(TEST_KEY)
    second = AdvisoryLock(TEST_KEY)
    try:
        assert first.try_acquire() is True
        assert second.try_acquire() is False  # I-13
    finally:
        first.release()
        second.release()


def test_lock_released_after_connection_close():
    first = AdvisoryLock(TEST_KEY)
    assert first.try_acquire() is True
    first.release()  # закрытие соединения освобождает lock (I-14)

    second = AdvisoryLock(TEST_KEY)
    try:
        assert second.try_acquire() is True
    finally:
        second.release()


def test_is_alive_detects_closed_connection():
    lock = AdvisoryLock(TEST_KEY)
    assert lock.try_acquire() is True
    assert lock.is_alive() is True
    lock.release()
    assert lock.is_alive() is False
