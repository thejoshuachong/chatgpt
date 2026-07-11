"""Shared domain models and validation primitives."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class ProofMaturity(StrEnum):
    CONCEPTUAL = "conceptual"
    ARCHITECTED = "architected"
    SIMULATION_TESTED = "simulation-tested"
    PILOT_DEPLOYED = "pilot-deployed"
    OPERATIONALLY_VALIDATED = "operationally-validated"
    STRESS_VALIDATED = "stress-validated"
    CROSS_CONTEXT_VALIDATED = "cross-context-validated"
    BATTLE_TESTED = "battle-tested"
    PROVEN_WITHIN_BOUNDARIES = "proven-within-defined-boundaries"
    CALIBRE_CERTIFIED = "1,000/1,000-calibre-certified"


class MissionState(StrEnum):
    DRAFT = "draft"
    VALIDATED = "validated"
    PLANNED = "planned"
    ACTIVE = "active"
    BLOCKED = "blocked"
    RELEASE_READY = "release-ready"
    RELEASED = "released"
    CLOSED = "closed"
    RETIRED = "retired"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    MISSION_CRITICAL = "mission-critical"


class ClaimType(StrEnum):
    VERIFIED_FACT = "verified-fact"
    SUPPORTED_INFERENCE = "supported-inference"
    ASSUMPTION = "assumption"
    ESTIMATE = "estimate"
    FORECAST = "forecast"
    OPINION = "opinion"
    CONTESTED = "contested"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class Evidence:
    id: str
    description: str
    source: str
    source_date: str | None = None
    evidence_class: str = "unclassified"
    verified: bool = False
    reviewer: str | None = None
    expires_at: str | None = None

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.id.strip():
            errors.append("Evidence id is required.")
        if not self.description.strip():
            errors.append(f"Evidence {self.id!r} requires a description.")
        if not self.source.strip():
            errors.append(f"Evidence {self.id!r} requires a source.")
        return errors


@dataclass(slots=True)
class Claim:
    id: str
    text: str
    claim_type: ClaimType
    confidence: float
    evidence_ids: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.id.strip():
            errors.append("Claim id is required.")
        if not self.text.strip():
            errors.append(f"Claim {self.id!r} requires text.")
        if not 0 <= self.confidence <= 1:
            errors.append(f"Claim {self.id!r} confidence must be between 0 and 1.")
        if self.claim_type == ClaimType.VERIFIED_FACT and not self.evidence_ids:
            errors.append(f"Verified fact {self.id!r} requires evidence.")
        return errors


@dataclass(slots=True)
class Risk:
    id: str
    description: str
    level: RiskLevel
    owner: str
    mitigation: str
    accepted: bool = False

    def validate(self) -> list[str]:
        errors: list[str] = []
        for name, value in {
            "id": self.id,
            "description": self.description,
            "owner": self.owner,
            "mitigation": self.mitigation,
        }.items():
            if not value.strip():
                errors.append(f"Risk {self.id!r} requires {name}.")
        return errors


@dataclass(slots=True)
class MissionEvent:
    event_type: str
    message: str
    actor: str = "system"
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)


class Serializable:
    """Mixin for dataclass JSON conversion."""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)  # type: ignore[arg-type]
