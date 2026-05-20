#!/usr/bin/env python3
"""check_new_script_placement.py — Enforce domain placement for new scripts.

Any new .py file in scripts/pipeline/commands/ must be in a recognized domain
subdirectory (knowledge, content, governance, ops, healing, launch, diagnostics,
migration, kilocode). Files placed directly in commands/ root are rejected.

Also verifies every .py in commands/{domain}/ has a module docstring.

Usage:
    python scripts/ci/checks/check_new_script_placement.py
    python scripts/ci/checks/check_new_script_placement.py --dry-run

Exit codes:
    0 — all scripts correctly placed
    1 — placement violations detected
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
COMMANDS_DIR = REPO_ROOT / "scripts" / "pipeline" / "commands"

# Recognized domain subdirectories
RECOGNIZED_DOMAINS = {
    "knowledge", "content", "governance", "ops", "healing",
    "launch", "diagnostics", "migration", "kilocode",
}


def check_placement() -> list[str]:
    """Return list of placement violation messages."""
    errors = []

    if not COMMANDS_DIR.exists():
        return errors

    # Check for .py files directly in commands/ root (should be in a domain subdir)
    for p in sorted(COMMANDS_DIR.glob("*.py")):
        if p.name == "__init__.py":
            continue
        errors.append(
            f"MISPLACED: {p.name} is at commands/ root — "
            f"move to commands/{{domain}}/"
        )

    # Check for unrecognized domain directories
    for d in sorted(COMMANDS_DIR.iterdir()):
        if not d.is_dir():
            continue
        if d.name.startswith("__"):
            continue
        if d.name not in RECOGNIZED_DOMAINS:
            errors.append(
                f"UNKNOWN DOMAIN: commands/{d.name}/ is not a recognized domain. "
                f"Recognized: {sorted(RECOGNIZED_DOMAINS)}"
            )

    return errors


def check_docstrings() -> list[str]:
    """Return list of missing-docstring warnings."""
    warnings = []

    if not COMMANDS_DIR.exists():
        return warnings

    for domain_dir in sorted(COMMANDS_DIR.iterdir()):
        if not domain_dir.is_dir() or domain_dir.name.startswith("__"):
            continue
        for p in sorted(domain_dir.glob("*.py")):
            if p.name == "__init__.py":
                continue
            try:
                tree = ast.parse(p.read_text(encoding="utf-8"))
                docstring = ast.get_docstring(tree)
                if not docstring:
                    rel = p.relative_to(REPO_ROOT)
                    warnings.append(f"NO DOCSTRING: {rel}")
            except SyntaxError:
                rel = p.relative_to(REPO_ROOT)
                warnings.append(f"SYNTAX ERROR: {rel}")

    return warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Report issues but always exit 0")
    args = parser.parse_args()

    errors = check_placement()
    warnings = check_docstrings()

    if warnings:
        print(f"WARN: {len(warnings)} docstring issue(s):", file=sys.stderr)
        for w in warnings:
            print(f"  {w}", file=sys.stderr)

    if errors:
        print(f"\nFAIL: {len(errors)} placement violation(s):", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        if args.dry_run:
            print("\n(dry-run: exiting 0 despite failures)")
            return 0
        return 1

    domain_count = sum(
        1 for d in COMMANDS_DIR.iterdir()
        if d.is_dir() and not d.name.startswith("__")
    ) if COMMANDS_DIR.exists() else 0
    print(f"OK: script placement valid ({domain_count} domains, 0 violations)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
