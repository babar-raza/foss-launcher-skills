#!/usr/bin/env python3
"""check_root_docs_truth.py — commit-time gate for the seven root operator/governance docs.

Imports the SAME check functions the /root-docs-refresh skill (S-121) uses
(scripts/pipeline/commands/governance/root_docs_checks.py) -- not a reimplementation. This
is deliberate: the manual refresh tool and this automated gate can never disagree about what
"correct" means, because they call the same code (plan: moonlit-strolling-sunset.md, Design
section D3 "Requirement 2: automated enforcement").

Only HARD_GATE findings block the commit. HEURISTIC findings are printed as non-blocking
WARN output -- a hard-fail on a judgment call trains people to bypass the gate, which is
exactly how a prior, unrelated check (check_agent_governance_surface.py) became permanently
advisory in this repo. See root_docs_checks.py's own module docstring for the tier contract.

Usage:
    python scripts/ci/checks/check_root_docs_truth.py            # check all seven files
    python scripts/ci/checks/check_root_docs_truth.py --staged   # check only staged ones
    python scripts/ci/checks/check_root_docs_truth.py --json     # machine-readable output

Exit codes:
    0  no HARD_GATE findings (HEURISTIC findings may still be present, printed as WARN)
    1  one or more HARD_GATE findings
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
REPO_ROOT = _DEFAULT_REPO_ROOT

_GOVERNANCE_DIR = _DEFAULT_REPO_ROOT / "scripts" / "pipeline" / "commands" / "governance"
if str(_GOVERNANCE_DIR) not in sys.path:
    sys.path.insert(0, str(_GOVERNANCE_DIR))

import root_docs_checks as checks  # noqa: E402

# Same seven-file set root_docs_refresh_run.py operates on. Duplicated here (not imported
# from that module) deliberately -- importing root_docs_refresh_run.py would pull in its
# state-machine dependencies (advisory_lock, session_identity) for a pure read-only check
# that has no business touching run/lock state. TARGET_FILES is small and stable; if it
# drifts, test_check_root_docs_truth.py's own fixture would catch a real omission.
TARGET_FILES: tuple[str, ...] = (
    "OPERATOR_GUIDE.md",
    "RUNBOOK.md",
    "CODEX.md",
    "GRADE_CONTRACT.md",
    "LAYMAN_SYSTEM_STATUS_REVIEW.md",
    "TASK_BACKLOG_20260521.md",
)


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override REPO_ROOT for testing. Call without arguments to reset."""
    global REPO_ROOT
    REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT


def _load_text(rel_path: str) -> "str | None":
    path = REPO_ROOT / rel_path
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def _staged_files() -> set[str]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    return set(result.stdout.splitlines())


def check_file(rel_path: str) -> dict:
    """Run every applicable HARD_GATE/HEURISTIC check against one file's current on-disk
    content. Same logic as root_docs_refresh_run.py's _run_checks_for_file — kept as a
    thin, independent re-implementation of the ORCHESTRATION (which functions to call for
    which file) since that's a few lines of glue, not the actual detection logic (which is
    fully shared via the root_docs_checks import above)."""
    text = _load_text(rel_path)
    if text is None:
        return {"file": rel_path, "exists": False, "hard_gate": [], "heuristic": []}

    findings: list[dict] = []
    findings += checks.check_dead_path_references(text, REPO_ROOT)

    registry_text = _load_text("docs/registries/skills.md")
    if registry_text:
        findings += checks.check_skill_id_references(text, registry_text)

    if rel_path == "GRADE_CONTRACT.md":
        init_text = _load_text("scripts/pipeline/content_eval/__init__.py")
        config_text = _load_text("scripts/pipeline/content_eval/grade_config.yaml")
        if init_text and config_text:
            findings += checks.check_grade_contract_sync(text, init_text, config_text)

    findings += checks.check_volatile_count_hardcoding(text)

    dead_snapshot = checks.check_dead_snapshot_file(REPO_ROOT / rel_path, REPO_ROOT)
    if dead_snapshot:
        findings.append(dead_snapshot)

    return {
        "file": rel_path,
        "exists": True,
        "hard_gate": [f for f in findings if f["tier"] == checks.HARD_GATE],
        "heuristic": [f for f in findings if f["tier"] == checks.HEURISTIC],
    }


def main(argv: "list[str] | None" = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--staged", action="store_true", help="Only check staged files, not all seven")
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    args = parser.parse_args(argv)

    targets = list(TARGET_FILES)
    if args.staged:
        staged = _staged_files()
        targets = [f for f in targets if f in staged]

    results = [check_file(f) for f in targets]
    total_hard_gate = sum(len(r["hard_gate"]) for r in results)
    total_heuristic = sum(len(r["heuristic"]) for r in results)

    if args.json:
        print(json.dumps({"files": results, "total_hard_gate": total_hard_gate, "total_heuristic": total_heuristic}, indent=2))
        return 1 if total_hard_gate else 0

    for r in results:
        if not r["exists"]:
            continue
        for f in r["hard_gate"]:
            print(f"FAIL [{r['file']}] {f['message']}", file=sys.stderr)
        for f in r["heuristic"]:
            print(f"WARN [{r['file']}] {f['message']}")

    if total_hard_gate:
        print(
            f"\ncheck_root_docs_truth: FAILED ({total_hard_gate} HARD_GATE finding(s) "
            f"across {sum(1 for r in results if r['hard_gate'])} file(s))\n"
            "  Fix: /root-docs-refresh (S-121), or edit directly and re-run this check.",
            file=sys.stderr,
        )
        return 1

    print(f"check_root_docs_truth: PASSED ({len(targets)} file(s) checked, {total_heuristic} advisory finding(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
