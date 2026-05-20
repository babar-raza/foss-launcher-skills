# Adapted from aspose.org
"""validate_chain.py — Single-file validation chain runner.

Runs frontmatter validation, API audit, evidence check, and content evaluation
in sequence on one content file. Returns 0 if all pass, 1 if any fail.

Usage:
    python scripts/pipeline/commands/content/validate_chain.py {filepath}
    python scripts/pipeline/commands/content/validate_chain.py {filepath} --skip-eval
    python scripts/pipeline/commands/content/validate_chain.py {filepath} --json
"""

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PIPELINE = _HERE.parents[1]
_SCRIPTS = _HERE.parents[2]
_COMMANDS = _HERE.parent
for _path in (_SCRIPTS, _PIPELINE):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from config_loader import resolve_content_repo  # noqa: E402


def _resolve_repo_root() -> Path:
    """Return the repo root via $CONTENT_REPO_PATH or config_loader."""
    env = os.environ.get("CONTENT_REPO_PATH")
    if env:
        return Path(env).resolve()
    try:
        return resolve_content_repo()
    except Exception:
        return _HERE.parents[3]


import argparse
import json
import platform
import subprocess

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REPO_ROOT = _resolve_repo_root()

_VENV_PYTHON = (
    str(_REPO_ROOT / ".venv" / "Scripts" / "python")
    if platform.system() == "Windows"
    else str(_REPO_ROOT / ".venv" / "bin" / "python")
)

_CMD_DIR = Path(__file__).resolve().parent          # commands/content/
_HEAL_DIR = _CMD_DIR.parent / "healing"             # commands/healing/


def _infer_family_platform(filepath: Path):
    """Return (family, platform) inferred from a content path, or (None, None)."""
    parts = filepath.resolve().parts
    try:
        idx = list(parts).index("content")
    except ValueError:
        return None, None

    remaining = parts[idx + 1:]  # site, [en,] family, [platform,] ...
    if len(remaining) < 2:
        return None, None

    site = remaining[0]  # e.g. blog.aspose.org
    offset = 1
    # Some sites have an /en/ segment between site and family
    if offset < len(remaining) and remaining[offset] == "en":
        offset += 1

    family = remaining[offset] if offset < len(remaining) else None
    # products.aspose.org has no platform level
    if "products" in site:
        return family, None
    plat = remaining[offset + 1] if (offset + 1) < len(remaining) else None
    return family, plat


def _run_tool(label, cmd):
    """Run *cmd* via subprocess, return (passed, stdout, stderr)."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return result.returncode == 0, result.stdout, result.stderr
    except FileNotFoundError:
        return False, "", f"{label}: command not found -- {cmd[0]}"
    except subprocess.TimeoutExpired:
        return False, "", f"{label}: timed out after 120 s"


# ---------------------------------------------------------------------------
# Step definitions
# ---------------------------------------------------------------------------

def _build_steps(filepath, family, plat, args):
    """Return list of (label, cmd) tuples for the steps to run."""
    fp = str(filepath)
    steps = []

    # 1. Frontmatter validation (always runs)
    steps.append((
        "frontmatter",
        [_VENV_PYTHON, str(_CMD_DIR / "validate_frontmatter.py"), fp],
    ))

    # 2. Audit
    if not args.skip_audit:
        steps.append((
            "audit",
            [_VENV_PYTHON, str(_CMD_DIR / "audit.py"), "--files", fp],
        ))

    # 3. Evidence (dry-run)
    if not args.skip_evidence:
        steps.append((
            "evidence",
            [_VENV_PYTHON, str(_HEAL_DIR / "attach_evidence.py"),
             "--files", fp, "--dry-run"],
        ))

    # 4. Content eval (requires family; platform optional)
    if not args.skip_eval and family:
        cmd = [
            _VENV_PYTHON,
            str(_CMD_DIR / "run_content_eval.py"),
            "evaluate", family,
        ]
        if plat:
            cmd.append(plat)
        cmd += ["--files", fp, "--strict"]
        steps.append(("content_eval", cmd))

    return steps


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _print_table(results):
    """Print a human-readable summary table."""
    hdr = f"{'Step':<16} {'Result':<8}"
    print("\n" + hdr)
    print("-" * len(hdr))
    for label, passed, _out, _err in results:
        status = "PASS" if passed else "FAIL"
        print(f"{label:<16} {status:<8}")
    print()


def _print_json(results):
    """Print JSON summary."""
    payload = {
        "steps": [
            {"step": label, "passed": passed}
            for label, passed, _out, _err in results
        ],
        "all_passed": all(p for _, p, _, _ in results),
    }
    print(json.dumps(payload, indent=2))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Run validation chain on a single content file.",
    )
    parser.add_argument("filepath", type=Path, help="Path to content file")
    parser.add_argument("--skip-audit", action="store_true",
                        help="Skip the audit step")
    parser.add_argument("--skip-eval", action="store_true",
                        help="Skip the content evaluation step")
    parser.add_argument("--skip-evidence", action="store_true",
                        help="Skip the evidence check step")
    parser.add_argument("--stop-on-fail", action="store_true",
                        help="Abort chain on first failure")
    parser.add_argument("--json", action="store_true",
                        help="Output results as JSON")
    args = parser.parse_args()

    filepath = args.filepath.resolve()
    if not filepath.is_file():
        print(f"ERROR: file not found -- {filepath}", file=sys.stderr)
        sys.exit(1)

    family, plat = _infer_family_platform(filepath)
    steps = _build_steps(filepath, family, plat, args)

    results = []  # [(label, passed, stdout, stderr)]
    for label, cmd in steps:
        passed, out, err = _run_tool(label, cmd)
        results.append((label, passed, out, err))
        if not passed and args.stop_on_fail:
            break

    # Output
    if args.json:
        _print_json(results)
    else:
        _print_table(results)

    all_passed = all(p for _, p, _, _ in results)
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
