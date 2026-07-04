"""run_sync.py — Master capability synchronization pipeline.

Runs the complete sync pipeline:
  LOAD CANONICAL REGISTRY
  → VALIDATE CONTRACTS (validate_skills.py)
  → INVENTORY CAPABILITIES (inventory_capabilities.py)
  → GENERATE CLAUDE COMMANDS (sync_commands.py --sync)
  → GENERATE AGENT SKILLS (sync_agents.py --sync)
  → UPDATE GENERATED INDEXES (generate_capability_index.py)
  → DETECT ORPHANS (detect_orphans.py)
  → DETECT DRIFT (detect_adapter_drift.py --sync)
  → VALIDATE PARITY (validate_semantic_parity.py --sync)
  → EMIT REPORTS (.governance/generated/)

Exit codes:
  0  all checks pass — system is synchronized
  1  one or more checks failed — run with --verbose for details

Usage:
    python tools/capability_sync/run_sync.py           # full sync
    python tools/capability_sync/run_sync.py --check   # check only (no writes)
    python tools/capability_sync/run_sync.py --verbose # verbose output
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_TOOLS = Path(__file__).resolve().parent


def run_step(name: str, cmd: list[str], check: bool, verbose: bool) -> tuple[bool, str]:
    """Run a pipeline step. Returns (success, output)."""
    result = subprocess.run(cmd, cwd=_REPO_ROOT, capture_output=True, text=True)
    output = (result.stdout + result.stderr).strip()
    success = result.returncode == 0
    status = "PASS" if success else "FAIL"
    if verbose or not success:
        print(f"  [{status}] {name}")
        if output:
            for line in output.splitlines():
                print(f"    {line}")
    else:
        print(f"  [{status}] {name}")
    return success, output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Master capability sync pipeline — inventory, generate, validate, report."
    )
    parser.add_argument("--check", action="store_true", help="Check only; no writes to adapter files")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show full output from each step")
    args = parser.parse_args(argv)

    mode = "--check" if args.check else "--sync"
    py = sys.executable
    started = datetime.now(tz=timezone.utc)

    print(f"\n{'='*60}")
    print(f"Capability Sync Pipeline — {started.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"Mode: {'CHECK (no writes)' if args.check else 'SYNC (writes enabled)'}")
    print(f"{'='*60}\n")

    steps = [
        ("Registry integrity (validate_skills.py)",
         [py, "scripts/validate_skills.py"]),
        ("Inventory capabilities",
         [py, str(_TOOLS / "inventory_capabilities.py"), "--output",
          ".governance/generated/baseline.yaml"] if not args.check else
         [py, str(_TOOLS / "inventory_capabilities.py")]),
        ("Generate Claude commands",
         [py, str(_TOOLS / "generate_claude_commands.py"), mode]),
        ("Generate agent skill indexes",
         [py, str(_TOOLS / "generate_agent_skill_index.py"), mode]),
        ("Generate capability discovery indexes",
         [py, str(_TOOLS / "generate_capability_index.py")] if not args.check else
         [py, "-c", "print('SKIP: index generation skipped in check mode')"]),
        ("Detect orphan adapters",
         [py, str(_TOOLS / "detect_orphans.py"), "--check"]),
        ("Detect adapter drift",
         [py, str(_TOOLS / "detect_adapter_drift.py"), mode]),
        ("Validate semantic parity",
         [py, str(_TOOLS / "validate_semantic_parity.py"), mode]),
        ("Validate agent discoverability",
         [py, str(_TOOLS / "validate_discoverability.py"), "--check"]),
    ]

    results = []
    for step_name, step_cmd in steps:
        ok, out = run_step(step_name, step_cmd, args.check, args.verbose)
        results.append((step_name, ok))

    elapsed = (datetime.now(tz=timezone.utc) - started).total_seconds()
    passed = sum(1 for _, ok in results if ok)
    failed = sum(1 for _, ok in results if not ok)

    print(f"\n{'='*60}")
    print(f"Pipeline complete in {elapsed:.1f}s: {passed} passed, {failed} failed")

    if failed > 0:
        print("\nFailed steps:")
        for step_name, ok in results:
            if not ok:
                print(f"  FAIL: {step_name}")
        print("\nFix failures and re-run: python tools/capability_sync/run_sync.py")
        print(f"{'='*60}\n")
        return 1

    verdict = "CROSS_AGENT_SKILL_COMMAND_PARITY_AUTOMATICALLY_ENFORCED"
    print(f"\nVerdict: {verdict}")
    print(f"{'='*60}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
