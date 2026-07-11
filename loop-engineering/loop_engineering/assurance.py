"""Calibre scoring, proof envelopes, and fatal-flaw governance."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .models import ProofMaturity

FATAL_FLAWS = {
    "material-fabrication", "unsupported-proof-claim", "critical-inaccuracy",
    "illegal-action", "severe-security-exposure", "privacy-breach",
    "missing-authority", "uncontrolled-material-risk", "destructive-lineage-loss",
    "false-independence-claim", "concealed-contradictory-evidence",
    "untested-critical-recovery", "untraceable-critical-data",
    "unmeasured-claimed-benefit",
}


@dataclass(slots=True)
class ProofEnvelope:
    asset_name: str
    version: str
    intended_purpose: str
    test_environment: str
    operators_and_users: list[str]
    number_of_uses: int
    duration: str
    baseline: str
    benchmark: str
    success_metrics: dict[str, Any]
    guardrails: dict[str, Any]
    failures: list[str]
    recoveries: list[str]
    replication_status: str
    independent_review_status: str
    contexts_tested: list[str]
    contexts_untested: list[str]
    limitations: list[str]
    review_or_expiry_date: str
    permitted_claim_language: str
    responsible_authority: str

    def validate(self) -> list[str]:
        errors: list[str] = []
        required_text = {
            "asset_name": self.asset_name, "version": self.version,
            "intended_purpose": self.intended_purpose,
            "test_environment": self.test_environment, "duration": self.duration,
            "baseline": self.baseline, "benchmark": self.benchmark,
            "replication_status": self.replication_status,
            "independent_review_status": self.independent_review_status,
            "review_or_expiry_date": self.review_or_expiry_date,
            "permitted_claim_language": self.permitted_claim_language,
            "responsible_authority": self.responsible_authority,
        }
        for name, value in required_text.items():
            if not value.strip():
                errors.append(f"Proof envelope requires {name}.")
        if self.number_of_uses < 0:
            errors.append("number_of_uses cannot be negative.")
        if not self.limitations:
            errors.append("Proof envelope must disclose at least one limitation.")
        if not self.contexts_untested:
            errors.append("Proof envelope must identify untested contexts.")
        return errors

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CalibreAssessment:
    architectural: int
    operational: int
    evidentiary: int
    outcome: int
    fatal_flaws: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.architectural + self.operational + self.evidentiary + self.outcome

    @property
    def certified(self) -> bool:
        return self.total == 1000 and not self.fatal_flaws

    def validate(self) -> list[str]:
        errors: list[str] = []
        for name in ("architectural", "operational", "evidentiary", "outcome"):
            value = getattr(self, name)
            if not 0 <= value <= 250:
                errors.append(f"{name} score must be between 0 and 250.")
        unknown = sorted(set(self.fatal_flaws) - FATAL_FLAWS)
        if unknown:
            errors.append(f"Unknown fatal flaw codes: {unknown}")
        return errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "architectural": self.architectural,
            "operational": self.operational,
            "evidentiary": self.evidentiary,
            "outcome": self.outcome,
            "total": self.total,
            "certified": self.certified,
            "fatal_flaws": self.fatal_flaws,
            "notes": self.notes,
        }


def assess_calibre(*, architecture_checks: int, architecture_total: int,
                   operation_checks: int, operation_total: int,
                   evidence_checks: int, evidence_total: int,
                   outcome_checks: int, outcome_total: int,
                   fatal_flaws: list[str] | None = None) -> CalibreAssessment:
    """Create an evidence-bearing four-dimensional score without inflation."""
    def scaled(passed: int, total: int) -> int:
        if total <= 0:
            return 0
        if passed < 0 or passed > total:
            raise ValueError("Passed checks must be between zero and total checks.")
        return round(250 * passed / total)

    assessment = CalibreAssessment(
        architectural=scaled(architecture_checks, architecture_total),
        operational=scaled(operation_checks, operation_total),
        evidentiary=scaled(evidence_checks, evidence_total),
        outcome=scaled(outcome_checks, outcome_total),
        fatal_flaws=list(fatal_flaws or []),
    )
    errors = assessment.validate()
    if errors:
        raise ValueError("\n".join(errors))
    if assessment.total == 1000 and not assessment.fatal_flaws:
        assessment.notes.append(
            "A numerical 1,000 score is not a valid certification without independent review, a complete Proof Envelope, and time-bounded authorization."
        )
    return assessment


def maximum_maturity(*, simulations: int, pilots: int, operational_runs: int,
                     stress_tests: int, contexts: int, independent_reviews: int,
                     proof_envelope_complete: bool) -> ProofMaturity:
    """Return the highest defensible maturity from observed evidence."""
    if simulations <= 0:
        return ProofMaturity.ARCHITECTED
    if pilots <= 0:
        return ProofMaturity.SIMULATION_TESTED
    if operational_runs <= 1:
        return ProofMaturity.PILOT_DEPLOYED
    if stress_tests <= 0:
        return ProofMaturity.OPERATIONALLY_VALIDATED
    if contexts <= 1:
        return ProofMaturity.STRESS_VALIDATED
    if independent_reviews <= 0:
        return ProofMaturity.CROSS_CONTEXT_VALIDATED
    if not proof_envelope_complete:
        return ProofMaturity.BATTLE_TESTED
    return ProofMaturity.PROVEN_WITHIN_BOUNDARIES
