"""U-29: строгая схема AI-ответа отклоняет лишние и отсутствующие поля."""

import pytest
from pydantic import ValidationError

from apps.analysis.schemas import validate_ai_result

VALID = {
    "model": {"value": "iphone_13", "source": "stated", "evidence": "iPhone 13"},
    "storage_gb": {"value": 128, "source": "stated", "evidence": "128 GB"},
    "battery_health": {"value": 87, "source": "stated", "evidence": "АКБ 87%"},
    "face_id": {"status": "unknown", "source": "unknown", "evidence": None},
    "true_tone": {"status": "unknown", "source": "unknown", "evidence": None},
    "display_replacement": {"status": "unknown", "source": "unknown", "evidence": None},
    "battery_replacement": {"status": "unknown", "source": "unknown", "evidence": None},
    "sim_variant": {"value": "unknown", "source": "unknown", "evidence": None},
    "icloud_status": {"status": "unknown", "source": "unknown", "evidence": None},
    "carrier_lock_status": {"status": "unknown", "source": "unknown", "evidence": None},
    "mdm_status": {"status": "unknown", "source": "unknown", "evidence": None},
    "defects": [],
    "repair_claims": [],
    "missing_checks": ["face_id", "true_tone", "icloud", "parts_history"],
    "risk_level": "medium",
    "confidence": 0.82,
    "seller_questions_uk": ["Вітаю! Чи працюють Face ID та True Tone?"],
}


def test_valid_result_passes():
    result = validate_ai_result(VALID)
    assert result.confidence == 0.82
    assert result.risk_level == "medium"


def test_extra_field_rejected():
    payload = dict(VALID, action="buy_now")
    with pytest.raises(ValidationError):
        validate_ai_result(payload)


def test_missing_field_rejected():
    payload = {k: v for k, v in VALID.items() if k != "risk_level"}
    with pytest.raises(ValidationError):
        validate_ai_result(payload)


def test_confidence_out_of_range_rejected():
    with pytest.raises(ValidationError):
        validate_ai_result(dict(VALID, confidence=1.5))


def test_unknown_defect_code_rejected():
    with pytest.raises(ValidationError):
        validate_ai_result(dict(VALID, defects=["EXPLODED"]))


def test_known_defect_code_accepted():
    result = validate_ai_result(dict(VALID, defects=["FRONT_GLASS_CRACK"]))
    assert result.defects == ["FRONT_GLASS_CRACK"]


def test_too_many_questions_rejected():
    with pytest.raises(ValidationError):
        validate_ai_result(dict(VALID, seller_questions_uk=["q"] * 6))


def test_question_truncated_to_300():
    result = validate_ai_result(dict(VALID, seller_questions_uk=["й" * 300]))
    assert len(result.seller_questions_uk[0]) == 300


def test_bad_risk_level_rejected():
    with pytest.raises(ValidationError):
        validate_ai_result(dict(VALID, risk_level="catastrophic"))
