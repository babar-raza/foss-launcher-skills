"""lane_evidence_schema.py — Evidence requirements for lane commits.

Defines and validates the minimum evidence required at each pilot stage.

Usage (CLI):
  python scripts/pipeline/commands/ops/lane_evidence_schema.py check --pilot 1 --lane-dir path/to/lane/
  python scripts/pipeline/commands/ops/lane_evidence_schema.py schema --pilot 1

Exit codes:
  0  All requirements met (PASS)
  1  Requirements not met (FAIL)
  2  I/O error
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Evidence requirements per pilot stage
PILOT_EVIDENCE: dict[int, list[dict]] = {
    1: [
        {"id": "lane-manifest", "description": "Lane manifest JSON exists and is valid", "required": True},
        {"id": "overlap-check", "description": "Overlap checker output (PASS)", "required": True},
        {"id": "dirty-classifier", "description": "Dirty-tree classification output", "required": True},
        {"id": "state-transition-log", "description": "State machine transition log", "required": True},
        {"id": "evidence-bundle", "description": "Evidence bundle ZIP or directory", "required": False},
    ],
    2: [
        {"id": "lane-manifest", "description": "Lane manifest JSON exists and is valid", "required": True},
        {"id": "overlap-check", "description": "Overlap checker output (PASS)", "required": True},
        {"id": "dirty-classifier", "description": "Dirty-tree classification output", "required": True},
        {"id": "s23-audit", "description": "S-23 content audit PASS on lane files", "required": True},
        {"id": "path-guard", "description": "Path guard PASS on all candidates", "required": True},
        {"id": "diff-checker", "description": "Lane-owned diff checker PASS", "required": True},
        {"id": "staging-checker", "description": "Exact-path staging checker PASS", "required": True},
        {"id": "skill-run-record", "description": "Skill run record created", "required": True},
        {"id": "commit-sha", "description": "Commit SHA recorded in lane manifest", "required": True},
        {"id": "git-status-proof", "description": "git status captured after commit", "required": True},
        {"id": "rollback-drill", "description": "Rollback drill evidence", "required": True},
    ],
    3: [
        {"id": "lane-manifest", "description": "Lane manifest JSON exists and is valid", "required": True},
        {"id": "overlap-check", "description": "Overlap checker output (PASS)", "required": True},
        {"id": "dirty-classifier", "description": "Dirty-tree classification output", "required": True},
        {"id": "s23-audit", "description": "S-23 content audit PASS on lane files", "required": True},
        {"id": "path-guard", "description": "Path guard PASS on all candidates", "required": True},
        {"id": "diff-checker", "description": "Lane-owned diff checker PASS", "required": True},
        {"id": "staging-checker", "description": "Exact-path staging checker PASS", "required": True},
        {"id": "skill-run-record", "description": "Skill run record created", "required": True},
        {"id": "commit-sha", "description": "Commit SHA recorded in lane manifest", "required": True},
        {"id": "git-status-proof", "description": "git status captured after commit", "required": True},
        {"id": "generation-manifest", "description": "Generation manifest with denominator_gap == 0", "required": True},
        {"id": "repeatability-proof", "description": "Second generator run produces zero diff", "required": True},
        {"id": "file-level-manifest", "description": "File-level manifest checker PASS", "required": True},
    ],
}


def get_schema(pilot: int) -> list[dict]:
    """Get evidence requirements for a given pilot stage."""
    if pilot not in PILOT_EVIDENCE:
        raise ValueError(f"Unknown pilot stage: {pilot}. Must be 1, 2, or 3.")
    return PILOT_EVIDENCE[pilot]


def check_evidence(pilot: int, evidence_dir: Path) -> list[dict]:
    """Check whether evidence artifacts exist in a directory.

    Returns list of check results: {id, description, required, found, status}.
    """
    schema = get_schema(pilot)
    results = []

    for req in schema:
        found = False
        matching_files = []

        if evidence_dir.is_dir():
            for f in evidence_dir.rglob("*"):
                if req["id"].replace("-", "_") in f.stem or req["id"].replace("-", "-") in f.stem:
                    found = True
                    matching_files.append(str(f.relative_to(evidence_dir)))

        status = "PASS" if found else ("FAIL" if req["required"] else "WARN")
        results.append({
            "id": req["id"],
            "description": req["description"],
            "required": req["required"],
            "found": found,
            "status": status,
            "files": matching_files,
        })

    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Lane evidence schema and checker."
    )
    sub = parser.add_subparsers(dest="command")

    schema_parser = sub.add_parser("schema", help="Print evidence schema")
    schema_parser.add_argument("--pilot", type=int, required=True, choices=[1, 2, 3])

    check_parser = sub.add_parser("check", help="Check evidence completeness")
    check_parser.add_argument("--pilot", type=int, required=True, choices=[1, 2, 3])
    check_parser.add_argument("--lane-dir", type=Path, required=True)
    check_parser.add_argument("--format", choices=["json", "table"], default="table")

    args = parser.parse_args(argv)

    if args.command == "schema":
        schema = get_schema(args.pilot)
        print(f"Evidence requirements for Pilot {args.pilot}:")
        for req in schema:
            marker = "*" if req["required"] else " "
            print(f"  [{marker}] {req['id']}: {req['description']}")
        print(f"\n  * = required")
        return 0

    elif args.command == "check":
        if not args.lane_dir.is_dir():
            print(f"ERROR: Directory not found: {args.lane_dir}", file=sys.stderr)
            return 2

        results = check_evidence(args.pilot, args.lane_dir)

        if args.format == "json":
            print(json.dumps(results, indent=2))
        else:
            fails = 0
            for r in results:
                marker = "PASS" if r["status"] == "PASS" else r["status"]
                print(f"  [{marker}] {r['id']}: {r['description']}")
                if r["status"] == "FAIL":
                    fails += 1

            print(f"\n{len(results)} checks, {fails} failures")

        return 1 if any(r["status"] == "FAIL" for r in results) else 0

    else:
        parser.print_help()
        return 2


if __name__ == "__main__":
    sys.exit(main())
