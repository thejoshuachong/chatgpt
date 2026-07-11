#!/usr/bin/env python3
"""Generate the canonical machine-readable estate registry."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ROOT / "loop-engineering" / "registry" / "catalog.py"
OUTPUT = ROOT / "loop-engineering" / "registry" / "assets.json"


def load_catalog():
    spec = importlib.util.spec_from_file_location("loop_engineering_catalog", CATALOG_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load catalogue from {CATALOG_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_registry() -> dict:
    catalog = load_catalog()
    assets: list[dict] = []
    for family, names in catalog.FAMILIES.items():
        prefix = catalog.PREFIXES[family]
        for number, name in enumerate(names, start=1):
            asset = {
                "id": f"{prefix}-{number:03d}",
                "family": family,
                "canonical_name": name,
                "version": "6.0",
                "status": "active-design-baseline",
                "proof_maturity": "architected",
                "owner_role": catalog.OWNER_ROLES[family],
                "deputy_role": "TBD before pilot",
                "purpose": "Canonical Step #1–Step #6 asset; detailed purpose is maintained in architecture documents.",
                "dependencies": [],
                "interfaces": [],
                "review_date": "2027-01-12",
                "retirement_condition": "Retire or replace only through evidence-based renewal review with preserved lineage.",
                "source_lineage": ["Steps #1–#6"],
            }
            if family == "OS":
                asset["core_stack"] = number in catalog.CORE_OS_NUMBERS
            assets.append(asset)

    return {
        "estate": {
            "canonical_name": "LOOP ENGINEERING ∞ + × PARALLEL AGENTS™",
            "estate_name": "Sovereign Compounding Execution and Intelligence Estate™",
            "version": "6.0",
            "registry_version": "1.0.0",
            "generated_from": "Steps #1–#6 canonical architecture",
            "proof_boundary": "Architected and implementation-ready; not universally empirically validated.",
            "canonical_counts": {
                family: len(names) for family, names in catalog.FAMILIES.items()
            },
        },
        "assets": assets,
    }


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(build_registry(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Generated {OUTPUT}")


if __name__ == "__main__":
    main()
