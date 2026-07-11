"""Command-line interface for the sovereign estate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .assurance import assess_calibre
from .audit import write_audit
from .mission import Mission, MissionEngine
from .models import RiskLevel
from .registry import DEFAULT_REGISTRY_PATH, EstateRegistry, RegistryError


def _json_print(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="loop-estate", description="LOOP ENGINEERING estate CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    registry = sub.add_parser("registry", help="Build, validate, or inspect the canonical registry")
    registry_sub = registry.add_subparsers(dest="registry_command", required=True)
    build = registry_sub.add_parser("build")
    build.add_argument("--output", type=Path, default=DEFAULT_REGISTRY_PATH)
    registry_sub.add_parser("validate")
    listing = registry_sub.add_parser("list")
    listing.add_argument("--family")
    show = registry_sub.add_parser("show")
    show.add_argument("asset_id")

    mission = sub.add_parser("mission", help="Create, plan, and validate missions")
    mission_sub = mission.add_subparsers(dest="mission_command", required=True)
    init = mission_sub.add_parser("init")
    init.add_argument("--objective", required=True)
    init.add_argument("--completion", action="append", required=True)
    init.add_argument("--risk", choices=[item.value for item in RiskLevel], default=RiskLevel.MEDIUM.value)
    init.add_argument("--output", type=Path, required=True)
    plan = mission_sub.add_parser("plan")
    plan.add_argument("mission_file", type=Path)
    plan.add_argument("--output", type=Path)
    validate = mission_sub.add_parser("validate")
    validate.add_argument("mission_file", type=Path)
    readiness = mission_sub.add_parser("readiness")
    readiness.add_argument("mission_file", type=Path)

    audit = sub.add_parser("audit", help="Run the deterministic estate audit")
    audit.add_argument("--output", type=Path, default=Path("audit-report.md"))

    score = sub.add_parser("score", help="Calculate an evidence-bearing calibre score")
    for dimension in ("architecture", "operation", "evidence", "outcome"):
        score.add_argument(f"--{dimension}-checks", type=int, required=True)
        score.add_argument(f"--{dimension}-total", type=int, required=True)
    score.add_argument("--fatal-flaw", action="append", default=[])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "registry":
            registry = EstateRegistry.from_catalog()
            if args.registry_command == "build":
                output = registry.write(args.output)
                print(output)
            elif args.registry_command == "validate":
                registry.assert_valid()
                print(f"PASS: {len(registry.assets)} canonical assets validated.")
            elif args.registry_command == "list":
                _json_print([asset.to_dict() for asset in registry.list(args.family)])
            elif args.registry_command == "show":
                _json_print(registry.get(args.asset_id).to_dict())
            return 0

        if args.command == "mission":
            engine = MissionEngine()
            if args.mission_command == "init":
                mission = Mission.create(args.objective, args.completion, RiskLevel(args.risk))
                mission.write(args.output)
                print(args.output)
            else:
                mission = Mission.read(args.mission_file)
                if args.mission_command == "plan":
                    engine.plan(mission)
                    output = args.output or args.mission_file
                    mission.write(output)
                    _json_print(engine.readiness_report(mission))
                elif args.mission_command == "validate":
                    errors = mission.validate(engine.registry)
                    if errors:
                        _json_print({"valid": False, "errors": errors})
                        return 1
                    _json_print({"valid": True, "errors": []})
                elif args.mission_command == "readiness":
                    report = engine.readiness_report(mission)
                    _json_print(report)
                    return 0 if not report["errors"] else 1
            return 0

        if args.command == "audit":
            result = write_audit(args.output)
            print(args.output)
            return 0 if result.passed else 1

        if args.command == "score":
            assessment = assess_calibre(
                architecture_checks=args.architecture_checks,
                architecture_total=args.architecture_total,
                operation_checks=args.operation_checks,
                operation_total=args.operation_total,
                evidence_checks=args.evidence_checks,
                evidence_total=args.evidence_total,
                outcome_checks=args.outcome_checks,
                outcome_total=args.outcome_total,
                fatal_flaws=args.fatal_flaw,
            )
            _json_print(assessment.to_dict())
            return 0 if not assessment.fatal_flaws else 2
    except (RegistryError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
