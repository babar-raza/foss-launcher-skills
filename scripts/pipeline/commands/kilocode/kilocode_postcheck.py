# Adapted from aspose.org
"""Post-skill validation: verify outputs against repository rules.

This script provides post-execution validation for Kilo Code to ensure
skill outputs comply with repository rules.

Usage:
    python scripts/pipeline/commands/kilocode/kilocode_postcheck.py <skill-name> <output-path> [output-path2 ...]

Exit codes:
    0  PASS - all outputs are valid
    1  FAIL - one or more outputs have issues
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent.parent.parent


def check_path(path: str) -> Tuple[bool, str]:
    """Check if path is allowed using path_guard.py.

    Args:
        path: Path to check

    Returns:
        Tuple of (allowed: bool, reason: str)
    """
    result = subprocess.run(
        ["python", "scripts/pipeline/commands/governance/path_guard.py", path],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT)
    )
    if result.returncode == 0:
        return True, "ALLOWED"
    return False, result.stdout.strip()


def run_audit(file_path: str) -> dict:
    """Run content audit on file using audit.py.

    Args:
        file_path: Path to the content file

    Returns:
        Dict with audit results
    """
    result = subprocess.run(
        ["python", "scripts/pipeline/commands/content/audit.py", "--files", file_path],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT)
    )
    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "has_failures": result.returncode != 0
    }


def has_evidence_frontmatter(file_path: str) -> bool:
    """Check if file has evidence frontmatter.

    Args:
        file_path: Path to the content file

    Returns:
        True if evidence frontmatter is present
    """
    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
        return "evidence:" in content
    except (OSError, IOError):
        return False


def post_skill_validation(skill_name: str, output_paths: List[str]) -> Tuple[bool, List[str]]:
    """Validate skill output against repository rules.

    Args:
        skill_name: Name of the skill that was executed
        output_paths: List of output file paths

    Returns:
        Tuple of (all_valid: bool, issues: List[str])
    """
    issues = []

    for path in output_paths:
        # Check path guard
        allowed, reason = check_path(path)
        if not allowed:
            issues.append(f"Path violation in {skill_name}: {reason}")

        # Check content audit (if content file)
        if path.startswith("content/"):
            result = run_audit(path)
            if result["has_failures"]:
                issues.append(f"Audit failure in {skill_name} for {path}: {result['stdout'][:200]}")

            # Check evidence frontmatter
            if not has_evidence_frontmatter(path):
                issues.append(f"Missing evidence frontmatter in {skill_name} for {path}")

    return len(issues) == 0, issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="kilocode_postcheck",
        description="Post-skill validation for Kilo Code."
    )
    parser.add_argument("skill_name", help="Name of the skill that was executed")
    parser.add_argument("output_paths", nargs="+", help="Output file paths to validate")
    args = parser.parse_args(argv)

    all_valid, issues = post_skill_validation(args.skill_name, args.output_paths)

    if all_valid:
        print("PASS: All outputs are valid")
        return 0
    else:
        print("FAIL: One or more outputs have issues:")
        for issue in issues:
            print(f"  - {issue}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
