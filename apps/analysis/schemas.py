"""Strict Pydantic schema for AI output. Extra/missing fields are rejected."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from apps.pricing.constants import DEFECT_CODES

SourceType = Literal["stated", "inferred", "unknown"]
YesNoUnknown = Literal["yes", "no", "unknown"]
LockStatus = Literal["clean", "locked", "unknown"]
DefectCode = Literal[tuple(DEFECT_CODES.keys())]  # type: ignore[valid-type]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TextFact(_Strict):
    value: str | None
    source: SourceType
    evidence: str | None = Field(default=None, max_length=300)


class IntFact(_Strict):
    value: int | None = Field(default=None, ge=0, le=2000)
    source: SourceType
    evidence: str | None = Field(default=None, max_length=300)


class StatusFact(_Strict):
    status: YesNoUnknown
    source: SourceType
    evidence: str | None = Field(default=None, max_length=300)


class LockFact(_Strict):
    status: LockStatus
    source: SourceType
    evidence: str | None = Field(default=None, max_length=300)


class SimFact(_Strict):
    value: Literal["physical", "esim_only", "dual", "unknown"]
    source: SourceType
    evidence: str | None = Field(default=None, max_length=300)


class AiResultV1(_Strict):
    """Schema version 1 (`AI_SCHEMA_VERSION=1`)."""

    model: TextFact
    storage_gb: IntFact
    battery_health: IntFact
    face_id: StatusFact
    true_tone: StatusFact
    display_replacement: StatusFact
    battery_replacement: StatusFact
    sim_variant: SimFact
    icloud_status: LockFact
    carrier_lock_status: LockFact
    mdm_status: LockFact
    defects: list[DefectCode] = Field(max_length=16)
    repair_claims: list[str] = Field(max_length=10)
    missing_checks: list[str] = Field(max_length=10)
    risk_level: Literal["low", "medium", "high"]
    confidence: float = Field(ge=0, le=1)
    seller_questions_uk: list[str] = Field(max_length=5)


def validate_ai_result(raw: object) -> AiResultV1:
    result = AiResultV1.model_validate(raw)
    # Bound the free-text list items explicitly.
    result.repair_claims = [item[:200] for item in result.repair_claims]
    result.missing_checks = [item[:100] for item in result.missing_checks]
    result.seller_questions_uk = [item[:300] for item in result.seller_questions_uk]
    return result


def json_schema_for_provider() -> dict:
    """Strict JSON schema passed to the Responses API structured output."""
    return AiResultV1.model_json_schema()
