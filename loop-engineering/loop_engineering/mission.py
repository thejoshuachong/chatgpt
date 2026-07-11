"""Mission planning and controlled lifecycle execution."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .models import Claim, Evidence, MissionEvent, MissionState, Risk, RiskLevel
from .registry import EstateRegistry

CONDITIONAL_OS: dict[str, tuple[str, ...]] = {
    "OS-025": ("security", "privacy", "credential", "sensitive"),
    "OS-039": ("data", "dataset", "database", "record"),
    "OS-040": ("model", "ai", "algorithm", "prompt"),
    "OS-043": ("vendor", "supplier", "third-party", "outsourc"),
    "OS-044": ("budget", "finance", "capital", "revenue", "cost"),
    "OS-045": ("legal", "tax", "accounting", "insurance", "jurisdiction"),
    "OS-046": ("product", "service", "customer"),
    "OS-047": ("programme", "program", "project", "milestone", "dependency"),
    "OS-048": ("reliability", "capacity", "latency", "availability"),
    "OS-049": ("incident", "crisis", "outage", "recovery"),
    "OS-050": ("change", "configuration", "architecture", "release"),
    "OS-051": ("documentation", "records", "legal hold", "archive"),
    "OS-052": ("fraud", "misconduct", "whistleblow", "integrity"),
    "OS-053": ("accessibility", "localization", "language", "cultural"),
    "OS-054": ("sustainability", "externality", "environment", "social impact"),
    "OS-055": ("decommission", "retire", "dispose", "sunset"),
    "OS-059": ("canonical", "reconcile", "deduplicate", "registry"),
    "OS-060": ("implement", "activate", "deployment", "operationalize"),
    "OS-061": ("simulate", "test", "regression", "verify"),
    "OS-062": ("training", "competency", "certify operator"),
    "OS-063": ("trademark", "copyright", "intellectual property", "brand clearance"),
    "OS-064": ("economics", "funding", "capacity", "unit economics"),
    "OS-065": ("calendar", "cadence", "operating rhythm", "governance schedule"),
    "OS-066": ("pilot", "evidence accumulation", "validation portfolio"),
}

HIGH_RISK_OS = {"OS-023", "OS-024", "OS-025", "OS-033", "OS-041", "OS-042", "OS-057", "OS-061"}


@dataclass(slots=True)
class Mission:
    id: str
    objective: str
    completion_contract: list[str]
    risk_level: RiskLevel
    state: MissionState = MissionState.DRAFT
    assumptions: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    activated_asset_ids: list[str] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    risks: list[Risk] = field(default_factory=list)
    events: list[MissionEvent] = field(default_factory=list)
    human_approval_required: bool = False
    rollback_plan: str = ""

    @classmethod
    def create(cls, objective: str, completion_contract: list[str],
               risk_level: RiskLevel = RiskLevel.MEDIUM) -> "Mission":
        mission = cls(
            id=f"MIS-{uuid.uuid4().hex[:10].upper()}",
            objective=objective.strip(),
            completion_contract=[item.strip() for item in completion_contract if item.strip()],
            risk_level=risk_level,
            human_approval_required=risk_level in {RiskLevel.HIGH, RiskLevel.MISSION_CRITICAL},
        )
        mission.events.append(MissionEvent("created", "Mission created."))
        return mission

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Mission":
        claims = []
        for item in payload.get("claims", []):
            claims.append(Claim(**item))
        evidence = [Evidence(**item) for item in payload.get("evidence", [])]
        risks = [Risk(**item) for item in payload.get("risks", [])]
        return cls(
            id=payload["id"], objective=payload["objective"],
            completion_contract=list(payload.get("completion_contract", [])),
            risk_level=RiskLevel(payload.get("risk_level", RiskLevel.MEDIUM)),
            state=MissionState(payload.get("state", MissionState.DRAFT)),
            assumptions=list(payload.get("assumptions", [])),
            constraints=list(payload.get("constraints", [])),
            activated_asset_ids=list(payload.get("activated_asset_ids", [])),
            claims=claims, evidence=evidence, risks=risks,
            events=[MissionEvent(**item) for item in payload.get("events", [])],
            human_approval_required=bool(payload.get("human_approval_required", False)),
            rollback_plan=payload.get("rollback_plan", ""),
        )

    @classmethod
    def read(cls, path: Path) -> "Mission":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["risk_level"] = self.risk_level.value
        payload["state"] = self.state.value
        for claim in payload["claims"]:
            claim["claim_type"] = str(claim["claim_type"])
        for risk in payload["risks"]:
            risk["level"] = str(risk["level"])
        return payload

    def write(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def validate(self, registry: EstateRegistry | None = None) -> list[str]:
        errors: list[str] = []
        if not self.id.strip():
            errors.append("Mission id is required.")
        if not self.objective.strip():
            errors.append("Mission objective is required.")
        if not self.completion_contract:
            errors.append("At least one completion criterion is required.")
        evidence_ids = {item.id for item in self.evidence}
        if len(evidence_ids) != len(self.evidence):
            errors.append("Evidence identifiers must be unique.")
        claim_ids = {item.id for item in self.claims}
        if len(claim_ids) != len(self.claims):
            errors.append("Claim identifiers must be unique.")
        for item in self.evidence:
            errors.extend(item.validate())
        for item in self.claims:
            errors.extend(item.validate())
            missing = sorted(set(item.evidence_ids) - evidence_ids)
            if missing:
                errors.append(f"Claim {item.id!r} references missing evidence: {missing}")
        for item in self.risks:
            errors.extend(item.validate())
        if self.risk_level in {RiskLevel.HIGH, RiskLevel.MISSION_CRITICAL}:
            if not self.human_approval_required:
                errors.append("High-risk mission must require human approval.")
            if not self.rollback_plan.strip():
                errors.append("High-risk mission requires a rollback or containment plan.")
        if registry is not None:
            for asset_id in self.activated_asset_ids:
                try:
                    registry.get(asset_id)
                except ValueError:
                    errors.append(f"Mission references unknown asset {asset_id}.")
        return errors


class MissionEngine:
    """Deterministic planner that activates the smallest responsible estate stack."""

    def __init__(self, registry: EstateRegistry | None = None):
        self.registry = registry or EstateRegistry.from_catalog()

    def select_assets(self, mission: Mission) -> list[str]:
        selected = {asset.id for asset in self.registry.core_stack()}
        text = " ".join([mission.objective, *mission.completion_contract, *mission.constraints]).casefold()
        for os_id, terms in CONDITIONAL_OS.items():
            if any(term in text for term in terms):
                selected.add(os_id)
        if mission.risk_level in {RiskLevel.HIGH, RiskLevel.MISSION_CRITICAL}:
            selected.update(HIGH_RISK_OS)
        return sorted(selected)

    def plan(self, mission: Mission) -> Mission:
        errors = mission.validate()
        if errors:
            raise ValueError("Mission cannot be planned:\n" + "\n".join(errors))
        mission.activated_asset_ids = self.select_assets(mission)
        mission.state = MissionState.PLANNED
        mission.events.append(MissionEvent(
            "planned",
            f"Activated {len(mission.activated_asset_ids)} assets using proportionate complexity.",
            metadata={"assets": mission.activated_asset_ids},
        ))
        return mission

    def readiness_report(self, mission: Mission) -> dict[str, Any]:
        errors = mission.validate(self.registry)
        warnings: list[str] = []
        if mission.state == MissionState.DRAFT:
            warnings.append("Mission has not been planned.")
        if not mission.evidence:
            warnings.append("No evidence has been registered; proof claims remain unavailable.")
        if not mission.risks:
            warnings.append("No explicit risks have been recorded.")
        if any(not item.verified for item in mission.evidence):
            warnings.append("One or more evidence items remain unverified.")
        release_ready = not errors and not warnings and mission.state in {MissionState.ACTIVE, MissionState.RELEASE_READY}
        return {
            "mission_id": mission.id, "state": mission.state.value,
            "risk_level": mission.risk_level.value,
            "activated_assets": mission.activated_asset_ids,
            "errors": errors, "warnings": warnings,
            "release_ready": release_ready,
            "proof_boundary": "Planning and deterministic validation only; live operational proof must be supplied separately.",
        }
