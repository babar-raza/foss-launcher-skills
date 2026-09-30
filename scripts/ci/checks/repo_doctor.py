#!/usr/bin/env python
"""repo_doctor.py — Unified, non-destructive environment readiness check.

Complements venv_doctor.py (which only checks .venv health) with the rest of
what a fresh clone needs before it can run the primary workflow and local
validation: Hugo, git hooks, env vars, repo-state sanity, and generated-data
readiness. Read-only — makes no changes to the repo or environment.

Usage:
    .venv/Scripts/python scripts/ci/checks/repo_doctor.py          # human-readable
    .venv/Scripts/python scripts/ci/checks/repo_doctor.py --json   # machine-readable

Exit codes:
    0  No BLOCKED checks (WARNING/EXTERNAL_UNAVAILABLE do not fail the run)
    1  One or more checks are BLOCKED
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import venv_doctor  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# Kept in sync with content-governance-checks.yml's peaceiris/actions-hugo pin.
# If that pin changes, update this constant to match — see
# docs/development/testing.md's parity table for the source of truth.
EXPECTED_HUGO_VERSION = "0.154.5"

REQUIRED_ENV_VARS = ["GH_TOKEN", "GITHUB_TOKEN"]  # at least one must be set
OPTIONAL_ENV_VARS = ["PROFESSIONALIZE_API_KEY", "LLM_API_KEY", "GOOGLE_API_KEY"]

STATUS_ORDER = {"READY": 0, "WARNING": 1, "EXTERNAL_UNAVAILABLE": 1, "BLOCKED": 2}


def _default_run(cmd: list[str], timeout: int = 10) -> "subprocess.CompletedProcess | None":
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, cwd=REPO_ROOT,
            encoding="utf-8", errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


_run = _default_run


def configure(*, run_fn=None) -> None:
    """Override the subprocess-running seam for testing. No args resets to default."""
    global _run
    _run = _default_run if run_fn is None else run_fn


def check_python_version() -> dict:
    expected_path = REPO_ROOT / ".python-version"
    expected = expected_path.read_text(encoding="utf-8").strip() if expected_path.exists() else None
    actual = f"{sys.version_info.major}.{sys.version_info.minor}"
    if expected is None:
        return {"name": "python_version", "status": "WARNING",
                "detail": ".python-version not found at repo root", "remediation": None}
    if not expected.startswith(actual):
        return {"name": "python_version", "status": "BLOCKED",
                "detail": f"running Python {actual}, repo pins {expected}",
                "remediation": f"Install/activate Python {expected}"}
    return {"name": "python_version", "status": "READY", "detail": f"Python {actual} matches pin", "remediation": None}


def check_venv() -> dict:
    d = venv_doctor.run()
    if d["health"] == "OK":
        return {"name": "venv", "status": "READY", "detail": "healthy", "remediation": None}
    return {"name": "venv", "status": "BLOCKED", "detail": d["health"], "remediation": d["repair_cmd"]}


def check_hugo() -> dict:
    hugo_path = shutil.which("hugo")
    if not hugo_path:
        return {"name": "hugo", "status": "BLOCKED", "detail": "hugo not found on PATH",
                "remediation": f"Install Hugo (extended) {EXPECTED_HUGO_VERSION} — https://gohugo.io/installation/"}
    result = _run(["hugo", "version"])
    if result is None or result.returncode != 0:
        return {"name": "hugo", "status": "WARNING", "detail": "hugo found but `hugo version` failed",
                "remediation": "Re-run `hugo version` manually to diagnose"}
    version_match = re.search(r"v(\d+\.\d+\.\d+)", result.stdout)
    extended = "extended" in result.stdout.lower()
    found_version = version_match.group(1) if version_match else "unknown"
    if found_version != EXPECTED_HUGO_VERSION:
        return {"name": "hugo", "status": "WARNING",
                "detail": f"found {found_version} ({'extended' if extended else 'NOT extended'}), CI pins {EXPECTED_HUGO_VERSION}",
                "remediation": f"Install Hugo extended {EXPECTED_HUGO_VERSION} to match CI exactly"}
    if not extended:
        return {"name": "hugo", "status": "BLOCKED", "detail": f"found {found_version} but not the extended edition",
                "remediation": "Install the *extended* Hugo build (required for SCSS)"}
    return {"name": "hugo", "status": "READY", "detail": f"{found_version} extended", "remediation": None}


def check_git_hooks() -> dict:
    result = _run(["git", "config", "core.hooksPath"])
    configured = (result.stdout.strip() if result and result.returncode == 0 else "")
    if configured.replace("\\", "/") != "scripts/githooks":
        return {"name": "git_hooks", "status": "BLOCKED",
                "detail": f"core.hooksPath is '{configured or '(unset)'}', expected 'scripts/githooks'",
                "remediation": "bash scripts/install-hooks.sh"}
    return {"name": "git_hooks", "status": "READY", "detail": "core.hooksPath = scripts/githooks", "remediation": None}


def check_env_vars() -> dict:
    have_required = [v for v in REQUIRED_ENV_VARS if os.environ.get(v)]
    have_optional = [v for v in OPTIONAL_ENV_VARS if os.environ.get(v)]
    missing_optional = [v for v in OPTIONAL_ENV_VARS if v not in have_optional]
    if not have_required:
        return {"name": "env_vars", "status": "BLOCKED",
                "detail": f"none of {REQUIRED_ENV_VARS} are set",
                "remediation": "Copy .env.example to .env and set GH_TOKEN (classic PAT), or export it directly"}
    detail = f"required OK ({'/'.join(have_required)} set)"
    if missing_optional:
        detail += f"; optional not set: {', '.join(missing_optional)} (features needing them will use fallbacks or be unavailable)"
    return {"name": "env_vars", "status": "READY" if not missing_optional else "WARNING",
            "detail": detail, "remediation": None}


def check_repo_state() -> dict:
    problems = []
    if (REPO_ROOT / ".git" / "rebase-merge").exists() or (REPO_ROOT / ".git" / "rebase-apply").exists():
        problems.append("repo is mid-rebase")
    lock_path = REPO_ROOT / ".git" / "maintenance.lock"
    if lock_path.exists():
        problems.append(f"stale lock file: {lock_path.relative_to(REPO_ROOT)}")
    if problems:
        return {"name": "repo_state", "status": "WARNING", "detail": "; ".join(problems),
                "remediation": "Resolve manually — do not force-clear a lock file without confirming no other process holds it"}
    return {"name": "repo_state", "status": "READY", "detail": "no mid-rebase state, no stale locks found", "remediation": None}


def check_knowledge_dir() -> dict:
    knowledge_dir = REPO_ROOT / "knowledge"
    if not knowledge_dir.is_dir() or not any(knowledge_dir.iterdir()):
        return {"name": "knowledge_data", "status": "BLOCKED", "detail": "knowledge/ missing or empty",
                "remediation": "This directory should be tracked and present after a normal `git clone` — re-clone if missing"}
    return {"name": "knowledge_data", "status": "READY", "detail": "knowledge/ present and non-empty", "remediation": None}


def check_pytest_collection() -> dict:
    venv_python = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
    if not venv_python.exists():
        venv_python = REPO_ROOT / ".venv" / "bin" / "python"
    if not venv_python.exists():
        return {"name": "pytest_collection", "status": "EXTERNAL_UNAVAILABLE",
                "detail": "skipped — .venv not present (see venv check)", "remediation": None}
    env = dict(os.environ)
    env["PYTHONPATH"] = "scripts/pipeline"
    result = _run([str(venv_python), "-m", "pytest", "--collect-only", "-q"])
    if result is None:
        return {"name": "pytest_collection", "status": "WARNING", "detail": "pytest collection timed out or errored", "remediation": None}
    if result.returncode != 0:
        return {"name": "pytest_collection", "status": "BLOCKED",
                "detail": "pytest --collect-only failed (import error somewhere in testpaths)",
                "remediation": "Run `.venv/Scripts/python -m pytest --collect-only -q` directly to see the failing import"}
    return {"name": "pytest_collection", "status": "READY", "detail": "test collection succeeds, no import errors", "remediation": None}


CHECKS = [
    check_python_version,
    check_venv,
    check_hugo,
    check_git_hooks,
    check_env_vars,
    check_repo_state,
    check_knowledge_dir,
    check_pytest_collection,
]

# Maps a short name (matching that check's own result["name"]) to its function, for
# --check <name>. A plain dict literal, not derived by calling each function (that
# would run every check — including a real pytest subprocess — just to read a name).
CHECKS_BY_NAME = {
    "python_version": check_python_version,
    "venv": check_venv,
    "hugo": check_hugo,
    "git_hooks": check_git_hooks,
    "env_vars": check_env_vars,
    "repo_state": check_repo_state,
    "knowledge_data": check_knowledge_dir,
    "pytest_collection": check_pytest_collection,
}


def run(checks: list | None = None) -> dict:
    """Run the given checks (default: all of CHECKS) and summarize the worst status."""
    selected = checks if checks is not None else CHECKS
    results = [check() for check in selected]
    worst = max((r["status"] for r in results), key=lambda s: STATUS_ORDER[s])
    return {"overall": worst, "checks": results}


def print_human(d: dict) -> None:
    print("=== repo_doctor ===")
    for r in d["checks"]:
        print(f"  [{r['status']:<20}] {r['name']}: {r['detail']}")
        if r["remediation"]:
            print(f"      remediation: {r['remediation']}")
    print(f"\nOverall: {d['overall']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    parser.add_argument(
        "--check", metavar="NAME", choices=sorted(CHECKS_BY_NAME),
        help="Run only this one check instead of the full suite (e.g. git_hooks). "
             "Cheap and side-effect-free — use this for a single automated gate "
             "(e.g. session start) instead of a hand-copied re-implementation of the "
             "same logic, which drifts from this script over time.",
    )
    args = parser.parse_args(argv)

    d = run([CHECKS_BY_NAME[args.check]] if args.check else None)
    if args.json:
        print(json.dumps(d, indent=2))
    else:
        print_human(d)

    return 1 if d["overall"] == "BLOCKED" else 0


if __name__ == "__main__":
    sys.exit(main())
