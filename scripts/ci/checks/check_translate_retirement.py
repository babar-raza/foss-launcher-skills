"""CI check: verify /translate retirement is complete and intact.

Fails with exit code 2 (FAIL) if any retired translation surface is found.
Passes with exit code 0 (PASS) when retirement is fully enforced.

Usage:
    .venv/Scripts/python scripts/ci/checks/check_translate_retirement.py
    .venv/Scripts/python scripts/ci/checks/check_translate_retirement.py --verbose

Wired into pre-commit hook as Step N (translate-retirement gate).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

EXIT_PASS = 0
EXIT_WARN = 1
EXIT_FAIL = 2

RETIRED_PATHS = [
    ("scripts/translator/", "Internal translator package must be deleted"),
    ("skills/translate-page.md", "S-52 skill must be deleted"),
    ("skills/translate-batch.md", "S-53 skill must be deleted"),
]

TOMBSTONE_MARKER = "PERMANENTLY RETIRED"
TRANSLATE_COMMAND = ".claude/commands/translate.md"


def check_retired_paths() -> list[str]:
    """Return error messages for any retired paths that still exist."""
    errors = []
    for rel_path, reason in RETIRED_PATHS:
        full = REPO_ROOT / rel_path
        if full.exists():
            errors.append(f"FAIL: {rel_path} still exists -- {reason}")
    return errors


def check_tombstone() -> list[str]:
    """Return error if translate.md is executable (not a tombstone)."""
    errors = []
    path = REPO_ROOT / TRANSLATE_COMMAND
    if not path.exists():
        errors.append(f"FAIL: {TRANSLATE_COMMAND} missing entirely (expected tombstone)")
        return errors
    content = path.read_text(encoding="utf-8", errors="replace")
    if TOMBSTONE_MARKER not in content:
        errors.append(
            f"FAIL: {TRANSLATE_COMMAND} does not contain tombstone marker "
            f"'{TOMBSTONE_MARKER}' -- it may still be executable"
        )
    # Routing keywords that would make it executable
    active_keywords = [
        "Invoke the **translate-page** skill",
        "Invoke the **translate-batch** skill",
        "python -m translator",
    ]
    for kw in active_keywords:
        if kw in content:
            errors.append(
                f"FAIL: {TRANSLATE_COMMAND} contains active routing keyword: '{kw}'"
            )
    return errors


def check_no_direct_translator_calls() -> list[str]:
    """Return errors for any python -m translator invocations in skills/ or .claude/commands/."""
    errors = []
    search_dirs = [
        REPO_ROOT / "skills",
        REPO_ROOT / ".claude" / "commands",
    ]
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for md_file in search_dir.glob("*.md"):
            if md_file.name == "translate.md":
                # tombstone is allowed to mention the retired CLI in its history section
                continue
            content = md_file.read_text(encoding="utf-8", errors="replace")
            if "python -m translator" in content:
                errors.append(
                    f"FAIL: {md_file.relative_to(REPO_ROOT)} contains 'python -m translator' call"
                )
    return errors


def check_hugo_translator_skills_present() -> list[str]:
    """Verify the authorized HT skill files exist."""
    warnings = []
    ht_skills = [
        "skills/ht-translate.md",
        "skills/ht-translate-batch.md",
    ]
    for rel_path in ht_skills:
        if not (REPO_ROOT / rel_path).exists():
            warnings.append(f"WARN: {rel_path} not found -- authorized HT skill missing")
    return warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Check translate retirement is complete")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    failures: list[str] = []
    warnings: list[str] = []

    failures.extend(check_retired_paths())
    failures.extend(check_tombstone())
    failures.extend(check_no_direct_translator_calls())
    warnings.extend(check_hugo_translator_skills_present())

    if args.verbose or failures or warnings:
        print("=== check_translate_retirement ===")

    for msg in warnings:
        print(msg)

    for msg in failures:
        print(msg)

    if not failures and not warnings:
        if args.verbose:
            print("PASS: translate retirement enforced -- all checks green")
        return EXIT_PASS

    if failures:
        print(
            f"\nFAIL: {len(failures)} translate retirement violation(s) found.\n"
            "The internal scripts/translator/ package is permanently retired.\n"
            "Use hugo-translator with an explicit --site profile instead.\n"
            "See reports/translation/translation-retirement-gap-ledger.yaml"
        )
        return EXIT_FAIL

    return EXIT_WARN


if __name__ == "__main__":
    sys.exit(main())
