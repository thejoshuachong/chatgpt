"""Canonical registry access and integrity assurance."""

from __future__ import annotations

import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = PACKAGE_ROOT / "registry" / "catalog.py"
DEFAULT_REGISTRY_PATH = PACKAGE_ROOT / "registry" / "assets.json"


@dataclass(frozen=True, slots=True)
class Asset:
    id: str
    family: str
    canonical_name: str
    version: str
    status: str
    proof_maturity: str
    owner_role: str
    deputy_role: str
    purpose: str
    dependencies: tuple[str, ...]
    interfaces: tuple[str, ...]
    review_date: str
    retirement_condition: str
    source_lineage: tuple[str, ...]
    core_stack: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "family": self.family,
            "canonical_name": self.canonical_name,
            "version": self.version,
            "status": self.status,
            "proof_maturity": self.proof_maturity,
            "owner_role": self.owner_role,
            "deputy_role": self.deputy_role,
            "purpose": self.purpose,
            "dependencies": list(self.dependencies),
            "interfaces": list(self.interfaces),
            "review_date": self.review_date,
            "retirement_condition": self.retirement_condition,
            "source_lineage": list(self.source_lineage),
            **({"core_stack": True} if self.core_stack else {}),
        }


class RegistryError(ValueError):
    """Raised when the canonical estate violates a registry invariant."""


class EstateRegistry:
    """In-memory canonical asset registry."""

    def __init__(self, assets: Iterable[Asset], metadata: dict[str, Any]):
        self.assets = tuple(assets)
        self.metadata = metadata
        self._by_id = {asset.id: asset for asset in self.assets}

    @staticmethod
    def _load_catalog():
        spec = importlib.util.spec_from_file_location("loop_engineering_catalog", CATALOG_PATH)
        if spec is None or spec.loader is None:
            raise RegistryError(f"Unable to load catalogue from {CATALOG_PATH}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    @classmethod
    def from_catalog(cls) -> "EstateRegistry":
        catalog = cls._load_catalog()
        assets: list[Asset] = []
        for family, names in catalog.FAMILIES.items():
            prefix = catalog.PREFIXES[family]
            for number, name in enumerate(names, start=1):
                assets.append(
                    Asset(
                        id=f"{prefix}-{number:03d}",
                        family=family,
                        canonical_name=name,
                        version="6.0",
                        status="active-design-baseline",
                        proof_maturity="architected",
                        owner_role=catalog.OWNER_ROLES[family],
                        deputy_role="TBD before pilot",
                        purpose="Canonical Step #1–Step #6 asset; detailed purpose is maintained in architecture documents.",
                        dependencies=(),
                        interfaces=(),
                        review_date="2027-01-12",
                        retirement_condition="Retire or replace only through evidence-based renewal review with preserved lineage.",
                        source_lineage=("Steps #1–#6",),
                        core_stack=(family == "OS" and number in catalog.CORE_OS_NUMBERS),
                    )
                )
        metadata = {
            "canonical_name": "LOOP ENGINEERING ∞ + × PARALLEL AGENTS™",
            "estate_name": "Sovereign Compounding Execution and Intelligence Estate™",
            "version": "6.0",
            "registry_version": "2.0.0",
            "generated_from": "Steps #1–#6 canonical architecture",
            "proof_boundary": "Architected and implementation-ready; not universally empirically validated.",
            "canonical_counts": {family: len(names) for family, names in catalog.FAMILIES.items()},
        }
        registry = cls(assets, metadata)
        registry.assert_valid()
        return registry

    @classmethod
    def from_json(cls, path: Path) -> "EstateRegistry":
        payload = json.loads(path.read_text(encoding="utf-8"))
        assets = [
            Asset(
                **{
                    **item,
                    "dependencies": tuple(item.get("dependencies", [])),
                    "interfaces": tuple(item.get("interfaces", [])),
                    "source_lineage": tuple(item.get("source_lineage", [])),
                    "core_stack": bool(item.get("core_stack", False)),
                }
            )
            for item in payload["assets"]
        ]
        registry = cls(assets, payload["estate"])
        registry.assert_valid()
        return registry

    def to_dict(self) -> dict[str, Any]:
        return {"estate": self.metadata, "assets": [asset.to_dict() for asset in self.assets]}

    def write(self, path: Path = DEFAULT_REGISTRY_PATH) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def get(self, asset_id: str) -> Asset:
        try:
            return self._by_id[asset_id]
        except KeyError as exc:
            raise RegistryError(f"Unknown asset id: {asset_id}") from exc

    def list(self, family: str | None = None) -> tuple[Asset, ...]:
        if family is None:
            return self.assets
        return tuple(asset for asset in self.assets if asset.family.casefold() == family.casefold())

    def core_stack(self) -> tuple[Asset, ...]:
        return tuple(asset for asset in self.assets if asset.family == "OS" and asset.core_stack)

    def validate(self) -> list[str]:
        errors: list[str] = []
        ids = [asset.id for asset in self.assets]
        names = [asset.canonical_name for asset in self.assets]
        if len(ids) != len(set(ids)):
            errors.append("Duplicate asset identifiers detected.")
        if len(names) != len(set(names)):
            errors.append("Duplicate canonical names detected.")
        expected = self.metadata.get("canonical_counts", {})
        actual: dict[str, int] = {}
        for asset in self.assets:
            actual[asset.family] = actual.get(asset.family, 0) + 1
            if not asset.owner_role.strip():
                errors.append(f"{asset.id} has no owner role.")
            if asset.proof_maturity in {"proven", "battle-tested", "1,000/1,000-calibre-certified"}:
                errors.append(f"{asset.id} overclaims proof maturity.")
        if actual != expected:
            errors.append(f"Canonical counts differ. Expected {expected}; actual {actual}.")
        core_ids = {asset.id for asset in self.core_stack()}
        expected_core = {
            "OS-001", "OS-002", "OS-003", "OS-005", "OS-009", "OS-010",
            "OS-011", "OS-012", "OS-014", "OS-022", "OS-056", "OS-057",
        }
        if core_ids != expected_core:
            errors.append(f"Core stack drifted. Expected {sorted(expected_core)}; actual {sorted(core_ids)}.")
        if "not universally empirically validated" not in str(self.metadata.get("proof_boundary", "")).lower():
            errors.append("Estate proof boundary is missing or overclaimed.")
        return errors

    def assert_valid(self) -> None:
        errors = self.validate()
        if errors:
            raise RegistryError("\n".join(errors))
