# Adapted from aspose.org scripts/ci/checks/ for standalone use
"""Check that all skill-containing folders have README.md files.

Detects:
- Missing README.md in skills/ (canonical)
- Missing README.md in .claude/commands/
- Missing README.md in .agents/skills/
- Missing README.md in .kilocode/skills/
- Root README.md missing a link to skills/README.md
- Skill count claims in READMEs that don't match actual disk counts

Usage:
    python scripts/ci/checks/check_skill_readme_coverage.py
    python scripts/ci/checks/check_skill_readme_coverage.py --json
    python scripts/ci/checks/check_skill_readme_coverage.py --fix   # auto-update counts

Exit codes:
    0  All checks pass (or --fix corrected all count mismatches)
    1  One or more documentation files are missing or incomplete
"""
from __future__ import annotations

import json
import re
import os
import sys
from pathlib import Path

_DEFAULT_REPO_ROOT = Path(os.environ.get("REPO_ROOT", str(Path(__file__).resolve().parent.parent.parent.parent)))
_REPO_ROOT = _DEFAULT_REPO_ROOT


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global _REPO_ROOT
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT

# Minimum line count to consider a README non-trivial
_MIN_LINES = 20

_CHECKS: list[tuple[str, Path, str | None]] = [
    # (description, path, required_substring_or_None)
    (
        "skills/README.md exists and is non-trivial",
        _REPO_ROOT / "skills" / "README.md",
        None,
    ),
    (
        ".claude/commands/README.md exists and is non-trivial",
        _REPO_ROOT / ".claude" / "commands" / "README.md",
        None,
    ),
    (
        ".agents/skills/README.md exists and is non-trivial",
        _REPO_ROOT / ".agents" / "skills" / "README.md",
        None,
    ),
    (
        ".kilocode/skills/README.md exists and is non-trivial",
        _REPO_ROOT / ".kilocode" / "skills" / "README.md",
        None,
    ),
    (
        "Root README.md links to skills/README.md",
        _REPO_ROOT / "README.md",
        "skills/README.md",
    ),
]


def _check_file(path: Path, required_substring: str | None) -> tuple[bool, str]:
    """Return (passed, reason)."""
    if not path.exists():
        return False, f"file does not exist: {path.relative_to(_REPO_ROOT)}"
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    if required_substring is None:
        if len(lines) < _MIN_LINES:
            return False, (
                f"{path.relative_to(_REPO_ROOT)} has {len(lines)} lines "
                f"(minimum {_MIN_LINES})"
            )
    else:
        content = path.read_text(encoding="utf-8", errors="ignore")
        if required_substring not in content:
            return False, (
                f"{path.relative_to(_REPO_ROOT)} does not contain "
                f"required string: {required_substring!r}"
            )
    return True, "ok"


# ---------------------------------------------------------------------------
# Skill count validation — ensures README prose matches disk reality
# ---------------------------------------------------------------------------

_SKILL_DIRS: dict[str, tuple[Path, str]] = {
    "skills": (_REPO_ROOT / "skills", "flat"),
    ".agents/skills": (_REPO_ROOT / ".agents" / "skills", "nested"),
    ".kilocode/skills": (_REPO_ROOT / ".kilocode" / "skills", "nested"),
    ".claude/commands": (_REPO_ROOT / ".claude" / "commands", "flat"),
}


def _count_skills(path: Path, layout: str) -> int:
    """Count actual skill files on disk, excluding README.md."""
    if layout == "flat":
        return sum(1 for f in path.glob("*.md") if f.stem.lower() != "readme")
    return sum(1 for d in path.iterdir() if d.is_dir() and (d / "SKILL.md").exists())


# Each tuple: (readme_path, regex_pattern, tree_key_in_SKILL_DIRS, description)
_COUNT_PATTERNS: list[tuple[Path, str, str, str]] = [
    (
        _REPO_ROOT / "skills" / "README.md",
        r"(\d+)\s+registered\s+skills",
        "skills",
        "skills/README.md registered count",
    ),
    (
        _REPO_ROOT / ".agents" / "skills" / "README.md",
        r"all\s+(\d+)\s+registered",
        ".agents/skills",
        ".agents/skills/README.md mirror count",
    ),
    (
        _REPO_ROOT / ".kilocode" / "skills" / "README.md",
        r"all\s+(\d+)\s+registered",
        ".kilocode/skills",
        ".kilocode/skills/README.md mirror count",
    ),
    (
        _REPO_ROOT / ".claude" / "commands" / "README.md",
        r"Skill\s+List\s*\((\d+)\s+registered",
        ".claude/commands",
        ".claude/commands/README.md skill list count",
    ),
    (
        _REPO_ROOT / ".claude" / "commands" / "README.md",
        r"This\s+tree\s*\((\d+)\s+files?\)",
        ".claude/commands",
        ".claude/commands/README.md tree file count",
    ),
    (
        _REPO_ROOT / ".claude" / "commands" / "README.md",
        r"canonical\s+`skills/`\s*\((\d+)\s+files?\)",
        "skills",
        ".claude/commands/README.md canonical reference count",
    ),
]


def check(as_json: bool = False) -> int:
    """Run all checks. Returns exit code."""
    results: list[dict] = []
    all_passed = True

    for description, path, required_substring in _CHECKS:
        passed, reason = _check_file(path, required_substring)
        results.append(
            {
                "check": description,
                "path": str(path.relative_to(_REPO_ROOT)),
                "passed": passed,
                "reason": reason,
            }
        )
        if not passed:
            all_passed = False

    # Count validation: compare stated counts in READMEs to actual disk counts
    for readme_path, pattern, tree_key, desc in _COUNT_PATTERNS:
        if not readme_path.exists():
            continue  # already caught by existence check above
        text = readme_path.read_text(encoding="utf-8", errors="ignore")
        m = re.search(pattern, text)
        if not m:
            continue  # pattern not found — no count claim to validate
        claimed = int(m.group(1))
        tree_path, layout = _SKILL_DIRS[tree_key]
        actual = _count_skills(tree_path, layout)
        passed = claimed == actual
        results.append({
            "check": desc,
            "path": str(readme_path.relative_to(_REPO_ROOT)),
            "passed": passed,
            "reason": "ok" if passed else f"claims {claimed} but actual count is {actual}",
        })
        if not passed:
            all_passed = False

    if as_json:
        print(json.dumps({"passed": all_passed, "checks": results}, indent=2))
    else:
        for r in results:
            status = "PASS" if r["passed"] else "FAIL"
            print(f"  [{status}] {r['check']}")
            if not r["passed"]:
                print(f"         > {r['reason']}")
        print()
        if all_passed:
            print("PASS: All skill tree README.md files are present and non-trivial")
        else:
            fails = sum(1 for r in results if not r["passed"])
            print(f"FAIL: {fails} check(s) failed — skills documentation is incomplete")

    return 0 if all_passed else 1


def fix_counts() -> int:
    """Rewrite count claims in all README files to match disk reality.

    Uses the same ``_COUNT_PATTERNS`` and ``_count_skills`` as the check —
    single source of truth.  Only the captured digit group is replaced,
    preserving surrounding prose.  Idempotent: returns 0 when already correct.
    """
    fixed = 0
    for readme_path, pattern, tree_key, desc in _COUNT_PATTERNS:
        if not readme_path.exists():
            continue
        text = readme_path.read_text(encoding="utf-8", errors="ignore")
        m = re.search(pattern, text)
        if not m:
            continue
        claimed = int(m.group(1))
        tree_path, layout = _SKILL_DIRS[tree_key]
        actual = _count_skills(tree_path, layout)
        if claimed != actual:
            new_text = text[: m.start(1)] + str(actual) + text[m.end(1) :]
            readme_path.write_text(new_text, encoding="utf-8")
            print(f"  [FIXED] {desc}: {claimed} -> {actual}")
            fixed += 1
        else:
            print(f"  [OK]    {desc}: {actual}")
    if fixed:
        print(f"\nFixed {fixed} count(s). Re-run without --fix to verify.")
    else:
        print("\nAll counts already correct — nothing to fix.")
    return fixed


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Check README.md coverage for all skill-containing folders"
    )
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Auto-update README count claims to match disk reality",
    )
    args = parser.parse_args()
    if args.fix:
        fix_counts()
        return check(as_json=args.json)
    return check(as_json=args.json)


if __name__ == "__main__":
    raise SystemExit(main())
