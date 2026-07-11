"""Estate-wide deterministic audit reporting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .registry import EstateRegistry


@dataclass(slots=True)
class AuditResult:
    passed: bool
    errors: list[str]
    warnings: list[str]
    asset_count: int
    generated_at: str

    def markdown(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        lines = [
            "# LOOP ENGINEERING Estate Audit", "",
            f"**Status:** {status}", f"**Generated:** {self.generated_at}",
            f"**Canonical assets:** {self.asset_count}", "", "## Errors",
        ]
        lines.extend([f"- {item}" for item in self.errors] or ["- None"])
        lines.extend(["", "## Warnings"])
        lines.extend([f"- {item}" for item in self.warnings] or ["- None"])
        lines.extend([
            "", "## Proof boundary", "",
            "A passing architecture audit does not constitute live operational validation, battle-tested status, or 1,000/1,000 certification.", "",
        ])
        return "\n".join(lines)


def run_audit(registry: EstateRegistry | None = None) -> AuditResult:
    registry = registry or EstateRegistry.from_catalog()
    errors = registry.validate()
    warnings: list[str] = []
    unassigned = [asset.id for asset in registry.assets if asset.deputy_role.startswith("TBD")]
    if unassigned:
        warnings.append(f"{len(unassigned)} assets require named deputies or successors before pilot deployment.")
    if all(not asset.dependencies for asset in registry.assets):
        warnings.append("Asset dependency graph has not yet been populated with live relationships.")
    return AuditResult(
        passed=not errors, errors=errors, warnings=warnings,
        asset_count=len(registry.assets), generated_at=datetime.now(UTC).isoformat(),
    )


def write_audit(path: Path) -> AuditResult:
    result = run_audit()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(result.markdown(), encoding="utf-8")
    return result
