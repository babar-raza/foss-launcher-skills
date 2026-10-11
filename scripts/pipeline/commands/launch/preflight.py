"""Universal pre-write preflight check — agent-agnostic enforcement.

Consolidates the three checks that Claude Code enforces via PreToolUse hooks
into a single script that any agent platform can run before writing a file.

Checks performed:
  1. Path guard (path_guard.py) — is the path in the allowed write list?
  2. Python placement (check_python_placement.py) — is the .py file in a
     sanctioned location?
  3. Content workflow gate — does the content/ file have a content-check
     pass marker?

Usage:
    python scripts/pipeline/commands/launch/preflight.py <path>
    python scripts/pipeline/commands/launch/preflight.py --json <path>

Exit codes:
    0  ALLOW — all checks pass
    1  DENY  — one or more checks failed (details printed)
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent.parent.parent


def _normalize(path_str: str) -> str:
    """Normalize path to repo-relative forward-slash form."""
    p = path_str.replace("\\", "/")
    # Strip absolute prefix if it points to repo root (case-insensitive on Windows)
    repo_prefix = str(_REPO_ROOT).replace("\\", "/") + "/"
    if p.lower().startswith(repo_prefix.lower()):
        p = p[len(repo_prefix):]
    return p.lstrip("./")


def check_path_guard(rel_path: str) -> tuple[bool, str]:
    """Check path_guard allowlist. Returns (passed, message)."""
    # Import path_guard from the same directory (scripts/pipeline/).
    # Use importlib to avoid mutating sys.path.
    import importlib.util

    _PIPELINE_ROOT = _SCRIPT_DIR.parent.parent  # commands/launch/ -> commands/ -> pipeline/
    spec = importlib.util.spec_from_file_location(
        "path_guard", _PIPELINE_ROOT / "commands" / "governance" / "path_guard.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    decision, reason = mod.check_path(rel_path)
    if decision == "ALLOW":
        return True, reason
    return False, f"Path guard DENY: {reason}"


def check_python_placement(rel_path: str) -> tuple[bool, str]:
    """Check Python file placement rules. Returns (passed, message)."""
    if not rel_path.endswith(".py"):
        return True, "not a .py file"

    check_script = _REPO_ROOT / "scripts" / "ci" / "check_python_placement.py"
    if not check_script.exists():
        return True, "check_python_placement.py not found (skipped)"

    result = subprocess.run(
        [sys.executable, str(check_script), "--propose", rel_path],
        capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )
    if result.returncode == 0:
        return True, "Python placement OK"
    return False, f"Python placement blocked: {result.stderr.strip()}"


def check_content_gate(rel_path: str) -> tuple[bool, str]:
    """Check content-check pass marker exists. Returns (passed, message)."""
    if not rel_path.startswith("content/"):
        return True, "not a content path"

    encoded = rel_path.replace("/", "_")
    marker = _REPO_ROOT / "reports" / "content-check" / f"{encoded}.pass"
    if marker.exists():
        return True, "content-check pass marker found"
    return False, (
        f"Content-check (S-23) not passed. "
        f"Run: python scripts/pipeline/commands/content/audit.py --files {rel_path}"
    )


def preflight(path_str: str) -> list[dict]:
    """Run all preflight checks. Returns list of failures (empty = all pass)."""
    rel = _normalize(path_str)
    failures = []

    for name, check_fn in [
        ("path_guard", check_path_guard),
        ("python_placement", check_python_placement),
        ("content_gate", check_content_gate),
    ]:
        passed, message = check_fn(rel)
        if not passed:
            failures.append({"check": name, "path": rel, "message": message})

    return failures


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="preflight",
        description="Universal pre-write preflight check for any agent platform.",
    )
    parser.add_argument("path", help="File path to check before writing")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args(argv)

    rel = _normalize(args.path)
    failures = preflight(args.path)

    if args.json:
        result = {
            "path": rel,
            "decision": "DENY" if failures else "ALLOW",
            "failures": failures,
        }
        print(json.dumps(result, indent=2))
    else:
        if failures:
            print(f"DENY  {rel}")
            for f in failures:
                print(f"  [{f['check']}] {f['message']}")
        else:
            print(f"ALLOW  {rel}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
