from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ROOT / "loop-engineering" / "registry" / "catalog.py"
REGISTRY_PATH = ROOT / "loop-engineering" / "registry" / "assets.json"
GENERATOR = ROOT / "loop-engineering" / "scripts" / "generate_registry.py"

EXPECTED_COUNTS = {
    "DNA": 45,
    "OS": 66,
    "Engine": 40,
    "Framework": 34,
    "SOP": 16,
    "Protocol": 14,
    "Council": 5,
    "Layer": 16,
    "Blueprint": 10,
    "Playbook": 14,
    "Strategy": 14,
    "Assurance System": 20,
    "Brand Candidate": 3,
}

EXPECTED_CORE_OS = {
    "OS-001", "OS-002", "OS-003", "OS-005", "OS-009", "OS-010",
    "OS-011", "OS-012", "OS-014", "OS-022", "OS-056", "OS-057",
}


def load_catalog():
    spec = importlib.util.spec_from_file_location("loop_engineering_catalog", CATALOG_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_registry() -> dict:
    subprocess.run([sys.executable, str(GENERATOR)], cwd=ROOT, check=True)
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def test_catalogue_counts_are_frozen() -> None:
    catalog = load_catalog()
    assert catalog.EXPECTED_COUNTS == EXPECTED_COUNTS


def test_registry_counts_and_unique_identifiers() -> None:
    registry = load_registry()
    assets = registry["assets"]
    assert registry["estate"]["canonical_counts"] == EXPECTED_COUNTS
    assert len({asset["id"] for asset in assets}) == len(assets)
    assert len({asset["canonical_name"] for asset in assets}) == len(assets)


def test_required_asset_fields_are_present() -> None:
    registry = load_registry()
    required = {
        "id", "family", "canonical_name", "version", "status",
        "proof_maturity", "owner_role", "deputy_role", "purpose",
        "dependencies", "interfaces", "review_date", "retirement_condition",
        "source_lineage",
    }
    for asset in registry["assets"]:
        assert required <= asset.keys(), asset["id"]
        assert asset["proof_maturity"] != "proven"


def test_minimum_viable_sovereign_stack_is_exact() -> None:
    registry = load_registry()
    core = {
        asset["id"]
        for asset in registry["assets"]
        if asset["family"] == "OS" and asset.get("core_stack")
    }
    assert core == EXPECTED_CORE_OS


def test_proof_boundary_is_not_overclaimed() -> None:
    registry = load_registry()
    boundary = registry["estate"]["proof_boundary"].lower()
    assert "not universally empirically validated" in boundary
