"""Manual listing status state machine (§9.10). Worker never calls this."""

from django.db import transaction

from apps.core.enums import AuditAction
from apps.core.exceptions import ApiError, ConflictError
from apps.core.services import record_audit
from apps.monitoring.enums import DecisionStatus
from apps.monitoring.models import Listing

# Manual transitions available through UI/API (BOUGHT/SOLD go through Deal).
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    DecisionStatus.NEW: {
        DecisionStatus.REVIEWED,
        DecisionStatus.CONTACTED,
        DecisionStatus.REJECTED,
        DecisionStatus.ARCHIVED,
    },
    DecisionStatus.CANDIDATE: {
        DecisionStatus.REVIEWED,
        DecisionStatus.CONTACTED,
        DecisionStatus.REJECTED,
        DecisionStatus.ARCHIVED,
    },
    DecisionStatus.REVIEWED: {
        DecisionStatus.CANDIDATE,
        DecisionStatus.CONTACTED,
        DecisionStatus.REJECTED,
        DecisionStatus.ARCHIVED,
    },
    DecisionStatus.CONTACTED: {
        DecisionStatus.CANDIDATE,
        DecisionStatus.REVIEWED,
        DecisionStatus.REJECTED,
    },
    DecisionStatus.REJECTED: {
        DecisionStatus.CANDIDATE,
        DecisionStatus.REVIEWED,
        DecisionStatus.ARCHIVED,
    },
    DecisionStatus.SKIPPED: {
        DecisionStatus.CANDIDATE,
        DecisionStatus.REVIEWED,
        DecisionStatus.ARCHIVED,
    },
    DecisionStatus.BOUGHT: set(),
    DecisionStatus.SOLD: set(),
    DecisionStatus.ARCHIVED: {DecisionStatus.CANDIDATE},
}


def change_status(
    listing: Listing,
    *,
    new_status: str | None,
    note: str | None = None,
    expected_current_status: str | None = None,
    actor=None,
    request=None,
) -> Listing:
    """Apply a manual status change and/or note update atomically."""
    if new_status is not None and new_status not in DecisionStatus.values:
        raise ApiError("Недопустимый статус.")
    if note is not None and len(note) > 5000:
        raise ApiError("Заметка длиннее 5000 символов.")

    with transaction.atomic():
        current = Listing.objects.select_for_update().get(pk=listing.pk)

        if expected_current_status and current.decision_status != expected_current_status:
            raise ConflictError(
                f"Статус уже изменился: сейчас {current.decision_status}. Обновите страницу."
            )

        changes: dict[str, object] = {}
        if note is not None and note != current.manual_notes:
            changes["note_changed"] = True
            current.manual_notes = note

        if new_status is not None and new_status != current.decision_status:
            allowed = ALLOWED_TRANSITIONS.get(current.decision_status, set())
            if new_status not in allowed:
                raise ConflictError(
                    f"Переход {current.decision_status} → {new_status} не разрешен."
                )
            changes["status"] = {"from": current.decision_status, "to": new_status}
            current.decision_status = new_status

        if changes:
            current.save()
            action = (
                AuditAction.LISTING_STATUS_CHANGED
                if "status" in changes
                else AuditAction.LISTING_NOTE_UPDATED
            )
            record_audit(
                action=action,
                actor=actor,
                target_type="Listing",
                target_id=str(current.id),
                changes=changes,
                request=request,
            )
    listing.refresh_from_db()
    return listing
