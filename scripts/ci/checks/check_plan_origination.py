#!/usr/bin/env python3
"""check_plan_origination.py — Parallel mission/taskcard tracker detection.

Targeted mechanical check for newly-authored plans (AGENTS.md §17 / PSE-01):
a plan must not invent its own mission/taskcard tracking shape instead of
binding to this repo's existing mechanisms (`MISSION_AUTHORITY.yaml`,
`reports/plan_state/{mission_id}/taskcards.jsonl` schema 5f, `backlog/BACKLOG.md`).
Reference doc Core Principle #2: "parallel ledgers create predictable failures."

This is intentionally narrow — it does not attempt to mechanically enforce the
full Planning Review Checklist / Taskcard Readiness Checklist in
docs/reference/planning-execution-state-machine.md (see that doc's own
"Non-goals": turning the whole checklist into a rigid regex gate is explicitly
not the goal). It catches one mechanically-detectable anti-pattern.

Rules implemented:
  PO-01  PARALLEL_MISSION_SCHEMA  Fenced code block defines a mission/taskcard-shaped
                                  structure with no canonical-anchor citation anywhere
                                  in the plan.
  PO-02  NEW_TRACKER_PROPOSAL     Plan text proposes creating a new tracking file for
                                  task/mission state with no canonical-anchor citation.

Usage:
    python scripts/ci/checks/check_plan_origination.py {path...} [--json]
    python scripts/ci/checks/check_plan_origination.py C:/Users/me/.claude/plans/foo.md
    python scripts/ci/checks/check_plan_origination.py --help

Exit code: 1 if any finding is produced, 0 otherwise (unlike check_plan_quality.py,
this check is NOT purely advisory — a non-zero exit is meant to be consumed by a
gate, see scripts/ci/hooks/check_plan_origination_gate_hook.sh).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import List, NamedTuple, Optional


class Finding(NamedTuple):
    rule: str
    filepath: str
    reason: str


# ---------------------------------------------------------------------------
# Canonical anchors — citing any of these anywhere in the plan is the escape
# hatch: it means the plan is binding to the real mechanism, not inventing one.
# ---------------------------------------------------------------------------

_CANONICAL_ANCHOR = re.compile(
    r"MISSION_AUTHORITY\.yaml|reports[/\\]plan_state[/\\]|taskcards\.jsonl|backlog[/\\]BACKLOG\.md",
)

_FENCED_BLOCK = re.compile(r"```[a-zA-Z]*\n(.*?)```", re.DOTALL)

_MISSION_SCHEMA_KEY = re.compile(
    r"^\s*(mission_id|taskcards|task_graph|mission_authority)\s*:",
    re.IGNORECASE | re.MULTILINE,
)

_NEW_TRACKER_PROPOSAL = re.compile(
    r"\b(?:create|creat(?:e|ing)|build(?:ing)?|add(?:ing)?|introduc(?:e|ing))\s+"
    r"(?:a|an|the)?\s*new\s+(?:task|status|mission)?\s*"
    r"(?:tracking|status)?\s*(?:file|ledger|tracker|registry)\b",
    re.IGNORECASE,
)


def check_po01(text: str) -> Optional[str]:
    """PARALLEL_MISSION_SCHEMA: fenced block defines a mission/taskcard-shaped
    structure and the plan cites no canonical anchor anywhere."""
    for match in _FENCED_BLOCK.finditer(text):
        block = match.group(1)
        if _MISSION_SCHEMA_KEY.search(block):
            if not _CANONICAL_ANCHOR.search(text):
                return (
                    "Fenced code block defines a mission/taskcard-shaped structure "
                    "(mission_id:/taskcards:/task_graph:/mission_authority: as a "
                    "top-level key) but the plan never cites MISSION_AUTHORITY.yaml, "
                    "reports/plan_state/, taskcards.jsonl, or backlog/BACKLOG.md - "
                    "this looks like a new parallel tracker instead of binding to "
                    "the existing mechanism (AGENTS.md section 17)"
                )
    return None


def check_po02(text: str) -> Optional[str]:
    """NEW_TRACKER_PROPOSAL: plan proposes a new task/status tracking file and
    cites no canonical anchor anywhere."""
    match = _NEW_TRACKER_PROPOSAL.search(text)
    if match and not _CANONICAL_ANCHOR.search(text):
        return (
            f"Plan proposes creating a new tracking artifact ({match.group(0)!r}) "
            "but never cites MISSION_AUTHORITY.yaml, reports/plan_state/, "
            "taskcards.jsonl, or backlog/BACKLOG.md - bind to the existing "
            "mechanism instead of inventing a parallel one (AGENTS.md section 17)"
        )
    return None


# ---------------------------------------------------------------------------
# File scanner (same shape as check_plan_quality.py)
# ---------------------------------------------------------------------------

def scan_file(filepath: str) -> List[Finding]:
    """Return all findings for a single file. Never raises."""
    try:
        text = Path(filepath).read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return [Finding("READ_ERROR", filepath, str(exc))]

    findings: List[Finding] = []
    for rule, checker in [
        ("PO-01", check_po01),
        ("PO-02", check_po02),
    ]:
        try:
            reason = checker(text)
        except Exception as exc:  # noqa: BLE001
            reason = f"[rule error: {exc}]"
        if reason:
            findings.append(Finding(rule, filepath, reason))

    return findings


def collect_files(paths: List[str]) -> List[str]:
    """Expand paths to a sorted, deduplicated list of .md files."""
    result: List[str] = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            result.extend(str(f) for f in path.rglob("*.md"))
        elif path.is_file() and path.suffix == ".md":
            result.append(str(path))
        # Non-.md files and missing paths are silently skipped
    return sorted(set(result))


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

def format_human(findings: List[Finding], file_count: int) -> str:
    lines: List[str] = []
    for f in findings:
        lines.append(f"BLOCK [{f.rule}] {f.filepath}: {f.reason}")
    lines.append(f"\n{file_count} file(s) scanned, {len(findings)} finding(s)")
    return "\n".join(lines)


def format_json_output(findings: List[Finding], file_count: int) -> str:
    return json.dumps(
        {
            "files_scanned": file_count,
            "finding_count": len(findings),
            "findings": [
                {"rule": f.rule, "filepath": f.filepath, "reason": f.reason}
                for f in findings
            ],
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# Public entry point (importable for testing)
# ---------------------------------------------------------------------------

def run(paths: List[str], as_json: bool = False) -> str:
    """Scan paths and return formatted output string."""
    files = collect_files(paths)
    all_findings: List[Finding] = []
    for filepath in files:
        all_findings.extend(scan_file(filepath))
    if as_json:
        return format_json_output(all_findings, len(files))
    return format_human(all_findings, len(files))


def has_findings(paths: List[str]) -> bool:
    """True if any path produces a finding. Used by callers that just need a verdict."""
    files = collect_files(paths)
    return any(scan_file(f) for f in files)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Detect a plan inventing a parallel mission/taskcard tracker.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="One or more .md files or directories to scan",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Emit machine-readable JSON instead of human-readable text",
    )
    args = parser.parse_args(argv)
    output = run(args.paths, as_json=args.as_json)
    print(output)
    files = collect_files(args.paths)
    any_findings = any(scan_file(f) for f in files)
    return 1 if any_findings else 0


if __name__ == "__main__":
    sys.exit(main())
