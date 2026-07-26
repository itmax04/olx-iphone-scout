"""Monitoring services: idempotent ingest, snapshots, scan orchestration, refresh.

Worker-only write paths. Views never call Playwright from here.
"""

import hashlib
import logging
import uuid
from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.enums import ErrorCode
from apps.monitoring.collectors.dto import ListingDetailDTO, SearchCardDTO
from apps.monitoring.collectors.exceptions import (
    BlockedError,
    CaptchaError,
    CollectorError,
    OlxRateLimitedError,
)
from apps.monitoring.enums import (
    DecisionStatus,
    ItemType,
    ScanRunStatus,
    SnapshotSource,
)
from apps.monitoring.models import (
    Listing,
    ListingDiscovery,
    ListingSnapshot,
    ScanRun,
    SearchProfile,
)
from apps.pricing.extraction import classify_item_type
from apps.pricing.services import evaluate_listing_for_profile, select_current_evaluation

logger = logging.getLogger(__name__)

PRICE_INTEREST_FACTOR = Decimal("1.25")
LISTING_MAX_AGE_DAYS = 30


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compute_hashes(title: str, description: str | None, photo_urls: list[str]) -> dict[str, str]:
    title_hash = _sha256(title.strip())
    photos_hash = _sha256("\n".join(photo_urls))
    content_hash = _sha256(f"{title.strip()}\n{(description or '').strip()}\n{photos_hash}")
    return {"title_hash": title_hash, "photos_hash": photos_hash, "content_hash": content_hash}


def _change_fingerprint(listing: Listing) -> str:
    return _sha256(
        f"{listing.current_price_uah}|{listing.title_hash}|{listing.content_hash}"
        f"|{listing.photos_hash}|{listing.is_active}"
    )


def record_snapshot(
    listing: Listing, source: str, changed_fields: list[str]
) -> ListingSnapshot | None:
    """Create a snapshot for the listing's current state; dedup by fingerprint."""
    fingerprint = _change_fingerprint(listing)
    safe_summary = {
        "price_uah": str(listing.current_price_uah)
        if listing.current_price_uah is not None
        else None,
        "is_active": listing.is_active,
    }
    try:
        with transaction.atomic():
            return ListingSnapshot.objects.create(
                listing=listing,
                source=source,
                price_uah=listing.current_price_uah,
                title=listing.title,
                title_hash=listing.title_hash,
                content_hash=listing.content_hash,
                photos_hash=listing.photos_hash,
                is_active=listing.is_active,
                changed_fields=changed_fields,
                change_fingerprint=fingerprint,
                safe_summary=safe_summary,
            )
    except IntegrityError:
        return None  # identical state already recorded


def ingest_search_card(
    card: SearchCardDTO, profile: SearchProfile
) -> tuple[Listing, bool, bool, Decimal | None]:
    """Idempotent upsert by olx_id.

    Returns (listing, created, price_changed, old_price).
    """
    now = timezone.now()
    item_type, _codes = classify_item_type(card.title)
    from apps.pricing.extraction import extract_model, extract_storage

    model_key, _ambiguous = extract_model(card.title)
    storage_gb = extract_storage(card.title)
    hashes = compute_hashes(card.title, None, [])

    price_changed = False
    old_price: Decimal | None = None
    with transaction.atomic():
        try:
            listing = Listing.objects.select_for_update().get(olx_id=card.olx_id)
            created = False
        except Listing.DoesNotExist:
            try:
                listing = Listing.objects.create(
                    olx_id=card.olx_id,
                    canonical_url=card.url,
                    title=card.title,
                    current_price_uah=card.price_uah,
                    currency=card.currency if card.currency != "UNK" else "UAH",
                    item_type=item_type,
                    model_key=model_key or "",
                    storage_gb=storage_gb,
                    location=card.location,
                    primary_image_url=card.thumbnail_url,
                    last_seen_at=now,
                    **hashes,
                )
                created = True
            except IntegrityError:
                listing = Listing.objects.select_for_update().get(olx_id=card.olx_id)
                created = False

        if created:
            record_snapshot(listing, SnapshotSource.SEARCH, ["initial"])
        else:
            changed_fields: list[str] = []
            if card.price_uah is not None and card.price_uah != listing.current_price_uah:
                changed_fields.append("price")
                old_price = listing.current_price_uah
                listing.current_price_uah = card.price_uah
                price_changed = True
            if card.title != listing.title:
                changed_fields.append("title")
                listing.title = card.title
                listing.title_hash = _sha256(card.title.strip())
                listing.content_hash = compute_hashes(
                    card.title, listing.description, list(listing.photo_urls or [])
                )["content_hash"]
            if not listing.is_active:
                changed_fields.append("is_active")
                listing.is_active = True
                listing.inactive_reason = ""
            listing.last_seen_at = now
            if card.thumbnail_url and not listing.primary_image_url:
                listing.primary_image_url = card.thumbnail_url
            listing.save()
            if changed_fields:
                record_snapshot(listing, SnapshotSource.SEARCH, changed_fields)

        discovery, disc_created = ListingDiscovery.objects.get_or_create(
            listing=listing, search_profile=profile
        )
        if not disc_created:
            discovery.last_seen_at = now
            discovery.save(update_fields=["last_seen_at"])

    return listing, created, price_changed, old_price


def apply_detail(listing: Listing, detail: ListingDetailDTO) -> list[str]:
    """Merge detail-page data into the listing; snapshot on meaningful change."""
    from apps.core.services import get_app_state

    changed: list[str] = []
    with transaction.atomic():
        listing = Listing.objects.select_for_update().get(pk=listing.pk)
        photo_urls = list(detail.photo_urls)
        hashes = compute_hashes(detail.title, detail.description, photo_urls)

        if detail.title and detail.title != listing.title:
            changed.append("title")
            listing.title = detail.title
        if detail.price_uah is not None and detail.price_uah != listing.current_price_uah:
            changed.append("price")
            listing.current_price_uah = detail.price_uah
        if (detail.description or "") != (listing.description or ""):
            changed.append("description")
            listing.description = detail.description
        if photo_urls != list(listing.photo_urls or []):
            changed.append("photos")
            listing.photo_urls = photo_urls
            if photo_urls and not listing.primary_image_url:
                listing.primary_image_url = photo_urls[0]

        listing.location = detail.location or listing.location
        listing.seller_name = detail.seller_name or listing.seller_name
        listing.seller_profile_url = detail.seller_profile_url or listing.seller_profile_url
        if detail.seller_type != "UNKNOWN":
            listing.seller_type = detail.seller_type
        listing.seller_joined_text = detail.seller_joined_text or listing.seller_joined_text
        if detail.delivery_available is not None:
            listing.delivery_available = detail.delivery_available

        content_changed = hashes["content_hash"] != listing.content_hash
        listing.title_hash = hashes["title_hash"]
        listing.photos_hash = hashes["photos_hash"]
        listing.content_hash = hashes["content_hash"]

        facts_source = f"{listing.title}\n{listing.description or ''}"
        item_type, _ = classify_item_type(facts_source)
        listing.item_type = item_type
        from apps.pricing.extraction import extract_model, extract_storage

        model_key, _ambiguous = extract_model(facts_source)
        storage_gb = extract_storage(facts_source)
        if model_key:
            listing.model_key = model_key
        if storage_gb is not None:
            listing.storage_gb = storage_gb

        now = timezone.now()
        listing.last_detail_fetched_at = now
        listing.last_seen_at = now
        listing.next_refresh_at = now + timedelta(hours=get_app_state().old_listing_refresh_hours)
        listing.save()

        if changed or content_changed:
            record_snapshot(listing, SnapshotSource.DETAIL, changed or ["content"])
    listing.refresh_from_db()
    return changed


def mark_listing_inactive(listing: Listing, reason: str) -> None:
    with transaction.atomic():
        listing = Listing.objects.select_for_update().get(pk=listing.pk)
        if not listing.is_active:
            return
        listing.is_active = False
        listing.inactive_reason = reason[:64]
        listing.next_refresh_at = None
        listing.save(
            update_fields=["is_active", "inactive_reason", "next_refresh_at", "updated_at"]
        )
        record_snapshot(listing, SnapshotSource.REFRESH, ["is_active"])


def is_potentially_interesting(listing: Listing, profile: SearchProfile) -> bool:
    """Cheap check before spending a detail-page fetch."""
    if listing.item_type in (ItemType.ACCESSORY, ItemType.PARTS, ItemType.COPY):
        return False
    if listing.current_price_uah is None:
        return False
    ceiling = profile.max_purchase_price_uah * PRICE_INTEREST_FACTOR
    return listing.current_price_uah <= ceiling


def evaluate_listing(listing: Listing, *, ai_analysis=None) -> None:
    """Evaluate against every profile that discovered the listing, then pick current."""
    snapshot = listing.snapshots.order_by("-observed_at", "-id").first()
    profiles = SearchProfile.objects.filter(
        discoveries__listing=listing, is_active=True, archived_at__isnull=True
    ).distinct()
    for profile in profiles:
        evaluate_listing_for_profile(listing, profile, snapshot=snapshot, ai_analysis=ai_analysis)
    select_current_evaluation(listing)


# ---------- Scan orchestration ----------


def process_profile_scan(profile: SearchProfile, source, *, send_alerts: bool = True) -> ScanRun:
    """One full scan of a profile's search page through the given source."""
    from apps.alerts.services import (
        enqueue_candidate_alert,
        enqueue_price_drop_alert,
        enqueue_system_incident,
    )
    from apps.monitoring.scheduler import (
        apply_failure_backoff,
        schedule_next_scan,
    )

    run = ScanRun.objects.create(
        search_profile=profile,
        correlation_id=uuid.uuid4(),
        status=ScanRunStatus.RUNNING,
        started_at=timezone.now(),
    )
    SearchProfile.objects.filter(pk=profile.pk).update(is_running=True)
    started = timezone.now()
    found = new = changed = candidates = 0
    try:
        page = source.fetch_search(profile.canonical_url, max_cards=profile.max_cards)
        found = len(page.cards)
        for card in page.cards:
            listing, created, price_changed, old_price = ingest_search_card(card, profile)
            if created:
                new += 1
            if price_changed:
                changed += 1
            if (created or price_changed) and is_potentially_interesting(listing, profile):
                detail_result = source.fetch_detail(listing.canonical_url)
                if not detail_result.is_active:
                    mark_listing_inactive(listing, "REMOVED_ON_DETAIL")
                    continue
                if detail_result.detail is not None:
                    apply_detail(listing, detail_result.detail)
                    listing.refresh_from_db()
            was_candidate = listing.current_is_candidate
            evaluate_listing(listing)
            listing.refresh_from_db()
            _maybe_run_ai(listing)
            if listing.current_is_candidate:
                candidates += 1
                price_dropped = (
                    price_changed
                    and old_price is not None
                    and listing.current_price_uah is not None
                    and listing.current_price_uah < old_price
                )
                if not was_candidate:
                    enqueue_candidate_alert(listing, send=send_alerts)
                elif price_dropped:
                    enqueue_price_drop_alert(listing, old_price=old_price, send=send_alerts)

        now = timezone.now()
        run.status = ScanRunStatus.SUCCESS
        run.found_count = found
        run.new_count = new
        run.changed_count = changed
        run.candidate_count = candidates
        run.finished_at = now
        run.duration_ms = int((now - started).total_seconds() * 1000)
        run.parser_version = page.parser_version
        run.save()
        schedule_next_scan(profile, success=True)
    except (CaptchaError, BlockedError, OlxRateLimitedError) as exc:
        _finish_failed_run(run, started, exc.error_code, str(exc), blocked=True)
        _handle_safety_incident(exc)
        apply_failure_backoff(profile, error_code=exc.error_code, message=str(exc))
        if send_alerts:
            enqueue_system_incident(exc.error_code, str(exc))
    except CollectorError as exc:
        _finish_failed_run(run, started, exc.error_code, str(exc))
        apply_failure_backoff(profile, error_code=exc.error_code, message=str(exc))
    except Exception as exc:  # unexpected: never leak internals to UI fields
        logger.exception("scan_unexpected_error", extra={"scan_run_id": str(run.id)})
        _finish_failed_run(run, started, ErrorCode.INTERNAL_ERROR, type(exc).__name__)
        apply_failure_backoff(
            profile, error_code=ErrorCode.INTERNAL_ERROR, message="Внутренняя ошибка сканирования."
        )
    finally:
        SearchProfile.objects.filter(pk=profile.pk).update(is_running=False)
    run.refresh_from_db()
    return run


def _maybe_run_ai(listing: Listing) -> None:
    """Run AI for interesting listings; failures never break the scan."""
    from apps.analysis.services import AiAlreadyRunning, analyze_listing
    from apps.core.services import effective_ai

    if not effective_ai():
        return
    if not (listing.current_is_candidate or listing.current_evaluation_id):
        return
    try:
        analyze_listing(listing)
        listing.refresh_from_db()
    except AiAlreadyRunning:
        pass
    except Exception:
        logger.exception("ai_analysis_failed", extra={"listing_id": str(listing.id)})


def _finish_failed_run(
    run: ScanRun, started, error_code: str, message: str, *, blocked: bool = False
) -> None:
    now = timezone.now()
    run.status = ScanRunStatus.BLOCKED if blocked else ScanRunStatus.FAILED
    run.error_code = error_code
    run.error_message = message[:500]
    run.finished_at = now
    run.duration_ms = int((now - started).total_seconds() * 1000)
    run.save()


def _handle_safety_incident(exc: CollectorError) -> None:
    from apps.core.services import apply_safety_block

    apply_safety_block(exc.safe_message, error_code=exc.error_code)


# ---------- Old listing refresh (§6.3) ----------


def select_listings_for_refresh(limit: int = 20) -> list[Listing]:
    now = timezone.now()
    cutoff = now - timedelta(days=LISTING_MAX_AGE_DAYS)
    queryset = (
        Listing.objects.filter(
            is_active=True,
            next_refresh_at__isnull=False,
            next_refresh_at__lte=now,
            first_seen_at__gte=cutoff,
        )
        .exclude(
            decision_status__in=[
                DecisionStatus.REJECTED,
                DecisionStatus.BOUGHT,
                DecisionStatus.SOLD,
                DecisionStatus.ARCHIVED,
            ]
        )
        .exclude(item_type__in=[ItemType.ACCESSORY, ItemType.PARTS, ItemType.COPY])
        .order_by("next_refresh_at")
    )
    result: list[Listing] = []
    for listing in queryset[: limit * 3]:
        ceilings = [
            profile.max_purchase_price_uah * PRICE_INTEREST_FACTOR
            for profile in SearchProfile.objects.filter(
                discoveries__listing=listing, is_active=True, archived_at__isnull=True
            )
        ]
        if not ceilings:
            continue
        if listing.current_price_uah is not None and all(
            listing.current_price_uah > c for c in ceilings
        ):
            continue
        result.append(listing)
        if len(result) >= limit:
            break
    return result


def refresh_listing(listing: Listing, source, *, send_alerts: bool = True) -> str:
    """Re-open a known listing's detail page. Returns a short outcome code."""
    from apps.alerts.services import enqueue_price_drop_alert
    from apps.core.services import get_app_state

    old_price = listing.current_price_uah
    old_hash = listing.content_hash
    try:
        result = source.fetch_detail(listing.canonical_url)
    except (CaptchaError, BlockedError, OlxRateLimitedError) as exc:
        _handle_safety_incident(exc)
        raise
    except CollectorError:
        # Temporary failure: do NOT mark inactive; retry later.
        Listing.objects.filter(pk=listing.pk).update(
            next_refresh_at=timezone.now() + timedelta(hours=1)
        )
        raise

    if not result.is_active:
        mark_listing_inactive(listing, "REMOVED")
        return "inactive"

    assert result.detail is not None
    apply_detail(listing, result.detail)
    listing.refresh_from_db()

    if listing.current_price_uah == old_price and listing.content_hash == old_hash:
        Listing.objects.filter(pk=listing.pk).update(
            last_seen_at=timezone.now(),
            next_refresh_at=timezone.now()
            + timedelta(hours=get_app_state().old_listing_refresh_hours),
        )
        return "unchanged"

    was_candidate = listing.current_is_candidate
    evaluate_listing(listing)
    listing.refresh_from_db()

    price_dropped = (
        old_price is not None
        and listing.current_price_uah is not None
        and listing.current_price_uah < old_price
    )
    if price_dropped and listing.current_is_candidate and not was_candidate:
        enqueue_price_drop_alert(listing, old_price=old_price, send=send_alerts)
        return "price_drop_candidate"
    if price_dropped:
        return "price_drop"
    return "changed"


# ---------- Web-triggered actions ----------


def queue_manual_run(profile: SearchProfile, *, actor=None, request=None) -> dict:
    """Mark the profile due now; the worker picks it up. Web never scans."""
    from apps.core.enums import AuditAction
    from apps.core.exceptions import ConflictError
    from apps.core.services import (
        effective_monitoring,
        enforce_rate_limit,
        get_app_state,
        record_audit,
        worker_status,
    )

    state = get_app_state()
    if profile.archived_at is not None:
        raise ConflictError("Профиль архивирован.")
    if not profile.is_active:
        raise ConflictError("Профиль выключен. Включите его перед запуском.")
    if profile.is_running:
        raise ConflictError("Профиль уже сканируется. Подождите завершения.")
    if not effective_monitoring(state):
        raise ConflictError("Мониторинг сейчас выключен или на паузе; запуск невозможен.")
    enforce_rate_limit(AuditAction.MANUAL_RUN_QUEUED, "MANUAL_RUN", actor)

    now = timezone.now()
    SearchProfile.objects.filter(pk=profile.pk).update(next_scan_at=now, blocked_until=None)
    record_audit(
        action=AuditAction.MANUAL_RUN_QUEUED,
        actor=actor,
        target_type="SearchProfile",
        target_id=str(profile.id),
        request=request,
    )
    return {
        "queued": True,
        "next_scan_at": now.isoformat(),
        "worker_status": worker_status(state),
    }


def test_search_url(url: str, *, max_cards: int = 5, actor=None, request=None) -> dict:
    """One safe fetch of a search URL. No DB rows are created."""
    from apps.core.enums import AuditAction
    from apps.core.services import enforce_rate_limit, record_audit
    from apps.monitoring.validators import validate_olx_url

    max_cards = min(max(int(max_cards), 1), 5)
    validate_olx_url(url)
    enforce_rate_limit(AuditAction.SEARCH_URL_TESTED, "SEARCH_URL_TEST", actor)

    from apps.monitoring.collectors.playwright_source import PlaywrightOlxSource

    source = PlaywrightOlxSource()
    try:
        page = source.fetch_search(url, max_cards=max_cards)
    finally:
        source.close()
    record_audit(
        action=AuditAction.SEARCH_URL_TESTED,
        actor=actor,
        target_type="SearchProfile",
        changes={"found_count": len(page.cards)},
        request=request,
    )
    return {
        "found_count": len(page.cards),
        "sample": [
            {"title": card.title, "price_uah": str(card.price_uah) if card.price_uah else None}
            for card in page.cards[:5]
        ],
        "parser_version": page.parser_version,
    }


def archive_profile(profile: SearchProfile, *, actor=None, request=None) -> SearchProfile:
    from apps.core.enums import AuditAction
    from apps.core.exceptions import ConflictError
    from apps.core.services import record_audit

    if profile.is_running:
        raise ConflictError("Профиль сейчас сканируется; повторите после завершения.")
    profile.is_active = False
    profile.archived_at = timezone.now()
    profile.save(update_fields=["is_active", "archived_at", "updated_at"])
    record_audit(
        action=AuditAction.SEARCH_PROFILE_ARCHIVED,
        actor=actor,
        target_type="SearchProfile",
        target_id=str(profile.id),
        request=request,
    )
    for listing in Listing.objects.filter(discoveries__search_profile=profile).distinct():
        select_current_evaluation(listing)
    return profile


# ---------- Startup recovery ----------


def recover_stuck_state() -> int:
    """Called at worker start: finish orphaned RUNNING runs, clear running flags."""
    stale = ScanRun.objects.filter(status=ScanRunStatus.RUNNING)
    count = 0
    for run in stale:
        _finish_failed_run(
            run, run.started_at, ErrorCode.INTERNAL_ERROR, "Прерван перезапуском worker."
        )
        count += 1
    SearchProfile.objects.filter(is_running=True).update(is_running=False)
    return count
