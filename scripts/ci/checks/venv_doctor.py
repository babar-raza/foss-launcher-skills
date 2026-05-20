#!/usr/bin/env python
# Adapted from aspose.org scripts/ci/checks/ for standalone use
"""venv_doctor.py — Unified .venv diagnostic command.

Reports 7 data points about the repo's .venv state and recommends a repair
command when the environment is broken.

Usage:
    .venv/Scripts/python scripts/ci/checks/venv_doctor.py          # human-readable
    .venv/Scripts/python scripts/ci/checks/venv_doctor.py --json   # machine-readable

Exit codes:
    0  All checks passed (.venv is healthy)
    1  One or more checks failed (.venv is broken or absent)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPAIR_CMD = "bash scripts/ci/hooks/repair_venv.sh"
REPAIR_CMD_FRESH = "bash scripts/ci/hooks/repair_venv.sh --fresh"

KEY_DEPS = ["yaml", "requests", "pytest"]
OPTIONAL_DEPS = {"dotenv": "python-dotenv"}


def _repo_root() -> Path:
    """Return repo root (parent of this script's scripts/ci/ dir)."""
    return Path(__file__).resolve().parent.parent.parent.parent


def _expected_venv_paths(repo_root: Path) -> list[Path]:
    """Return candidate .venv Python paths in preference order."""
    venv = repo_root / ".venv"
    return [
        venv / "Scripts" / "python",    # Windows (Git Bash path)
        venv / "Scripts" / "python.exe", # Windows (native)
        venv / "bin" / "python",         # Unix/macOS
    ]


def run() -> dict:
    """Collect all 7 diagnostic data points."""
    repo_root = _repo_root()
    candidates = _expected_venv_paths(repo_root)

    # 1. Repo root
    repo_root_str = str(repo_root)

    # 2. Expected .venv Python paths
    expected_paths = [str(p) for p in candidates]

    # 3 & 4. Actual interpreter + whether it is inside .venv
    actual_executable = str(Path(sys.executable).resolve())
    venv_dir = repo_root / ".venv"
    is_inside_venv = str(actual_executable).startswith(str(venv_dir.resolve()))

    # 5. pip availability through actual interpreter
    pip_available = False
    pip_version = ""
    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            pip_available = True
            pip_version = result.stdout.strip().split("\n")[0]
    except Exception:
        pass

    # 6. Key dependency availability
    dep_results: dict[str, bool] = {}
    for pkg in KEY_DEPS:
        try:
            __import__(pkg)
            dep_results[pkg] = True
        except ImportError:
            dep_results[pkg] = False

    for import_name, pkg_name in OPTIONAL_DEPS.items():
        try:
            __import__(import_name)
            dep_results[pkg_name] = True
        except ImportError:
            dep_results[pkg_name] = False

    # 7. Recommended repair command
    venv_exists = venv_dir.exists()
    any_candidate_exists = any(p.exists() for p in candidates)
    deps_ok = all(dep_results.values())

    if not venv_exists or not any_candidate_exists:
        repair_cmd = REPAIR_CMD
        health = "BROKEN"
    elif not is_inside_venv:
        repair_cmd = REPAIR_CMD
        health = "WRONG_INTERPRETER"
    elif not pip_available:
        repair_cmd = REPAIR_CMD_FRESH
        health = "PIP_MISSING"
    elif not deps_ok:
        repair_cmd = REPAIR_CMD
        health = "DEPS_MISSING"
    else:
        repair_cmd = None
        health = "OK"

    return {
        "health": health,
        "repo_root": repo_root_str,
        "expected_venv_paths": expected_paths,
        "actual_executable": actual_executable,
        "is_inside_venv": is_inside_venv,
        "pip_available": pip_available,
        "pip_version": pip_version,
        "dependencies": dep_results,
        "repair_cmd": repair_cmd,
    }


def print_human(d: dict) -> None:
    ok = "\u2713" if sys.stdout.encoding and "utf" in sys.stdout.encoding.lower() else "OK"
    fail = "\u2717" if sys.stdout.encoding and "utf" in sys.stdout.encoding.lower() else "FAIL"

    print("=== venv_doctor ===")
    print(f"  Health         : {d['health']}")
    print(f"  Repo root      : {d['repo_root']}")
    print(f"  Expected paths :")
    for p in d["expected_venv_paths"]:
        exists = Path(p).exists()
        mark = ok if exists else fail
        print(f"    [{mark}] {p}")
    mark = ok if d["is_inside_venv"] else fail
    print(f"  Actual Python  : {d['actual_executable']}")
    print(f"  Inside .venv   : [{mark}] {d['is_inside_venv']}")
    mark = ok if d["pip_available"] else fail
    print(f"  pip available  : [{mark}] {d['pip_version'] or 'NOT FOUND'}")
    print(f"  Dependencies   :")
    for pkg, status in d["dependencies"].items():
        mark = ok if status else fail
        print(f"    [{mark}] {pkg}")
    if d["repair_cmd"]:
        print(f"\n  [!] Repair recommended:")
        print(f"      {d['repair_cmd']}")
    else:
        print(f"\n  .venv is healthy.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    args = parser.parse_args()

    d = run()

    if args.json:
        print(json.dumps(d, indent=2))
    else:
        print_human(d)

    return 0 if d["health"] == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())
