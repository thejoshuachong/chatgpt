from __future__ import annotations

import json
from pathlib import Path

from loop_engineering.assurance import assess_calibre, maximum_maturity
from loop_engineering.audit import run_audit
from loop_engineering.mission import Mission, MissionEngine
from loop_engineering.models import ProofMaturity, RiskLevel
from loop_engineering.registry import EstateRegistry


def test_registry_is_valid_and_core_stack_is_fixed() -> None:
    registry = EstateRegistry.from_catalog()
    assert not registry.validate()
    assert len(registry.assets) == 297
    assert {asset.id for asset in registry.core_stack()} == {
        "OS-001", "OS-002", "OS-003", "OS-005", "OS-009", "OS-010",
        "OS-011", "OS-012", "OS-014", "OS-022", "OS-056", "OS-057",
    }


def test_mission_planner_uses_proportionate_complexity() -> None:
    mission = Mission.create(
        "Implement and test a privacy-sensitive AI product pilot",
        ["Produce a validated implementation plan", "Define rollback and evidence controls"],
        RiskLevel.HIGH,
    )
    mission.rollback_plan = "Restore the last approved configuration and quarantine affected data."
    engine = MissionEngine()
    engine.plan(mission)
    selected = set(mission.activated_asset_ids)
    assert {"OS-025", "OS-040", "OS-046", "OS-060", "OS-061", "OS-066"} <= selected
    assert len(selected) < 66


def test_high_risk_mission_requires_rollback() -> None:
    mission = Mission.create("High-risk mission", ["Complete safely"], RiskLevel.HIGH)
    assert any("rollback" in error.lower() for error in mission.validate())


def test_calibre_score_is_evidence_bearing() -> None:
    assessment = assess_calibre(
        architecture_checks=10, architecture_total=10,
        operation_checks=8, operation_total=10,
        evidence_checks=5, evidence_total=10,
        outcome_checks=2, outcome_total=10,
    )
    assert assessment.total == 625
    assert not assessment.certified


def test_maturity_never_skips_required_evidence() -> None:
    assert maximum_maturity(
        simulations=1, pilots=1, operational_runs=5, stress_tests=1,
        contexts=2, independent_reviews=0, proof_envelope_complete=False,
    ) == ProofMaturity.CROSS_CONTEXT_VALIDATED


def test_audit_passes_with_honest_warnings() -> None:
    audit = run_audit()
    assert audit.passed
    assert audit.warnings
    assert "not constitute" in audit.markdown()


def test_mission_round_trip(tmp_path: Path) -> None:
    mission = Mission.create("Build a market research database", ["Deliver a traceable register"])
    path = tmp_path / "mission.json"
    mission.write(path)
    loaded = Mission.read(path)
    assert loaded.id == mission.id
    assert json.loads(path.read_text())["state"] == "draft"
