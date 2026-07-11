from __future__ import annotations

import json
from pathlib import Path

from loop_engineering.cli import main


def test_cli_registry_validate(capsys) -> None:
    assert main(["registry", "validate"]) == 0
    assert "PASS" in capsys.readouterr().out


def test_cli_mission_flow(tmp_path: Path) -> None:
    mission_file = tmp_path / "mission.json"
    assert main([
        "mission", "init",
        "--objective", "Implement a controlled research pilot",
        "--completion", "Produce the pilot plan",
        "--risk", "medium",
        "--output", str(mission_file),
    ]) == 0
    assert main(["mission", "plan", str(mission_file)]) == 0
    payload = json.loads(mission_file.read_text())
    assert payload["state"] == "planned"
    assert "OS-060" in payload["activated_asset_ids"]


def test_cli_audit(tmp_path: Path) -> None:
    report = tmp_path / "audit.md"
    assert main(["audit", "--output", str(report)]) == 0
    assert "Status:** PASS" in report.read_text()
