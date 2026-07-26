"""F-21: state machine ручных статусов."""

import pytest

from apps.core.exceptions import ApiError, ConflictError
from apps.core.models import AuditEvent
from apps.monitoring.status_machine import change_status
from tests import factories

pytestmark = pytest.mark.django_db


class TestTransitions:
    @pytest.mark.parametrize(
        "start,target,allowed",
        [
            ("NEW", "REVIEWED", True),
            ("NEW", "CONTACTED", True),
            ("NEW", "REJECTED", True),
            ("NEW", "ARCHIVED", True),
            ("NEW", "SOLD", False),
            ("NEW", "BOUGHT", False),
            ("CANDIDATE", "CONTACTED", True),
            ("CONTACTED", "REVIEWED", True),
            ("CONTACTED", "ARCHIVED", False),
            ("REJECTED", "CANDIDATE", True),
            ("SKIPPED", "REVIEWED", True),
            ("SOLD", "NEW", False),
            ("BOUGHT", "REVIEWED", False),
            ("ARCHIVED", "CANDIDATE", True),
        ],
    )
    def test_matrix(self, start, target, allowed):
        listing = factories.create_listing(decision_status=start)
        if allowed:
            change_status(listing, new_status=target)
            listing.refresh_from_db()
            assert listing.decision_status == target
        else:
            with pytest.raises(ConflictError):
                change_status(listing, new_status=target)

    def test_same_status_idempotent(self):
        listing = factories.create_listing(decision_status="REVIEWED")
        change_status(listing, new_status="REVIEWED")  # не бросает
        assert AuditEvent.objects.count() == 0  # без изменений — без аудита

    def test_note_only_update(self):
        listing = factories.create_listing()
        change_status(listing, new_status=None, note="Уточнить АКБ")
        listing.refresh_from_db()
        assert listing.manual_notes == "Уточнить АКБ"
        assert AuditEvent.objects.filter(action="LISTING_NOTE_UPDATED").count() == 1

    def test_stale_expected_status_conflict(self):
        listing = factories.create_listing(decision_status="REVIEWED")
        with pytest.raises(ConflictError):
            change_status(listing, new_status="CONTACTED", expected_current_status="NEW")

    def test_note_too_long(self):
        listing = factories.create_listing()
        with pytest.raises(ApiError):
            change_status(listing, new_status=None, note="x" * 5001)

    def test_status_change_audited(self):
        listing = factories.create_listing()
        change_status(listing, new_status="REVIEWED")
        event = AuditEvent.objects.get(action="LISTING_STATUS_CHANGED")
        assert event.changes["status"] == {"from": "NEW", "to": "REVIEWED"}
