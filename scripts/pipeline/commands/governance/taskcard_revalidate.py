"""taskcard_revalidate.py -- MT069 HC-15: the "re-validation of completed_verified cards" proposal, built.

A card can declare a read-only `revalidate` field (a shell command run from the repo root) when it
advances to a terminal status. This tool re-runs every declared check for a mission and reports which
ones still pass -- without changing any ledger status itself (that stays a human/agent decision informed
by the report).

Why this exists: a real incident (MT069, 2026-09-18) found `skill-governance.yml`'s TC-SG-20 closure
("both governance workflows green", 2026-08-31, graded completed_verified) had silently gone stale 6
days later when a real bug (commit acd165e07e) re-broke the exact thing it certified -- nobody
re-checked it until a cost investigation stumbled onto the gap. A declared, mechanically re-run check
would have caught that automatically.

This is intentionally NOT wired into any CI workflow: taskcards.jsonl is a per-mission, gitignored,
LOCAL ledger (never checked out by a public-repo workflow, and mission task descriptions should not be
made public). Run it by hand, or from a local/self-hosted mechanism with access to reports/plan_state/.

Declaring a check on an existing card (no taskcard_cli.py change needed -- it already supports
arbitrary --field key=value):
    python scripts/pipeline/commands/governance/taskcard_cli.py --mission <id> advance \\
        --task <task-id> --expected <status> --to <status> \\
        --field revalidate="pytest scripts/ci/tests/test_check_platform_capabilities.py -q"

Usage:
    python scripts/pipeline/commands/governance/taskcard_revalidate.py --mission <id> [--task <id>] [--json]

Exit codes: 0 = every declared check still passes (or none declared); 1 = at least one now fails
(this is the finding -- a card whose declared check no longer passes); 2 = infrastructure error
(mission/ledger not found).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "pipeline"))

from lib.taskcard_store import TaskcardStore  # noqa: E402


def cards_with_revalidation(mission: str, *, repo_root: Path = _REPO_ROOT) -> "list[dict]":
    """Every card in the mission's ledger that declares a non-empty `revalidate` field, latest row only."""
    store = TaskcardStore(mission, repo_root=repo_root)
    latest = store.read_latest()
    return [
        {"task_id": task_id, **row}
        for task_id, row in sorted(latest.items())
        if row.get("revalidate")
    ]


def run_check(command: str, *, repo_root: Path, runner=subprocess.run) -> "tuple[bool, str]":
    """Runs `command` as a shell string from repo_root. Returns (passed, output_tail).

    `shell=True` invokes cmd.exe on Windows, which does not understand the Unix inline
    `VAR=value command` env-var-prefix syntax (found live: every declared command silently failed
    with "'PYTHONPATH' is not recognized..."). PYTHONPATH is injected into the subprocess
    environment directly instead, so a declared check never needs to know which shell will run it --
    this repo's own universal convention is `PYTHONPATH=scripts/pipeline` for every pytest invocation.
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = str(repo_root / "scripts" / "pipeline")
    result = runner(command, shell=True, cwd=str(repo_root), capture_output=True,
                     text=True, encoding="utf-8", errors="replace", timeout=600, env=env)
    output = (result.stdout or "") + (result.stderr or "")
    tail = "\n".join(output.strip().splitlines()[-15:])
    return result.returncode == 0, tail


def main(argv: "list[str] | None" = None, *, runner=subprocess.run) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mission", required=True, help="Mission id (matches taskcard_cli.py --mission)")
    parser.add_argument("--task", default=None, help="Only re-validate this one task id")
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root) if args.repo_root else _REPO_ROOT

    try:
        cards = cards_with_revalidation(args.mission, repo_root=repo_root)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.task:
        cards = [c for c in cards if c["task_id"] == args.task]

    results = []
    for card in cards:
        passed, tail = run_check(card["revalidate"], repo_root=repo_root, runner=runner)
        results.append({
            "task_id": card["task_id"], "status": card.get("status"), "revalidate": card["revalidate"],
            "passed": passed, "output_tail": tail,
        })

    failing = [r for r in results if not r["passed"]]

    if args.json:
        print(json.dumps({"mission": args.mission, "checked": len(results), "failing": failing}, indent=2))
    else:
        if not results:
            print(f"No revalidation checks declared for {args.mission}" + (f" (task {args.task})" if args.task else "") + ".")
        else:
            print(f"Re-ran {len(results)} declared check(s) for {args.mission}:")
            for r in results:
                mark = "PASS" if r["passed"] else "FAIL"
                print(f"  [{mark}] {r['task_id']} (ledger status: {r['status']}): {r['revalidate']}")
                if not r["passed"]:
                    print(f"    {r['output_tail']}")
            if failing:
                print(f"\n{len(failing)} card(s) whose declared check no longer passes -- their ledger "
                      f"status may be stale. This tool does not change the ledger.")

    return 1 if failing else 0


if __name__ == "__main__":
    sys.exit(main())
