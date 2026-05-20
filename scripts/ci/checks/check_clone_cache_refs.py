#!/usr/bin/env python3
# Adapted from aspose.org scripts/ci/checks/ for standalone use
"""check_clone_cache_refs.py — Enforce that no active file references foss-launcher as clone cache.

Scans governance, skills, source code, docs, and active plans for forbidden patterns that
imply the obsolete foss-launcher clone-cache location.

Canonical clone cache: runs/.clone_cache/ (inside the aspose.org repo)
Canonical path: {REPO_ROOT}/runs/.clone_cache/
Resolver: scripts/pipeline/core/clone_cache.py -> cache_root()

Usage:
    python scripts/ci/checks/check_clone_cache_refs.py
    python scripts/ci/checks/check_clone_cache_refs.py --dry-run   # report only, exit 0

Exit codes:
    0  clean — no active obsolete references found
    1  violations found — active files reference the obsolete foss-launcher clone-cache location
"""
from __future__ import annotations

import argparse
import re
import os
import sys
from pathlib import Path

REPO_ROOT = Path(os.environ.get("REPO_ROOT", Path(__file__).resolve().parents[3]))

# ---------------------------------------------------------------------------
# Forbidden patterns that indicate the obsolete foss-launcher clone-cache path
# ---------------------------------------------------------------------------

FORBIDDEN_PATTERNS: list[tuple[str, str]] = [
    # Exact path variants
    (r"foss-launcher/runs/\.clone_cache", "obsolete foss-launcher clone-cache path (forward slash)"),
    (r"foss-launcher\\runs\\\.clone_cache", "obsolete foss-launcher clone-cache path (backslash)"),
    (r"\.\./foss-launcher", "relative sibling foss-launcher reference"),
    # Concept variants
    (r"foss.launcher.clone.cache", "foss-launcher clone cache concept reference"),
    (r"sibling.foss-launcher", "sibling foss-launcher reference"),
    # Variable name variants
    (r"FOSS_LAUNCHER_PATH", "obsolete FOSS_LAUNCHER_PATH env variable"),
    (r"\bFOSS_LAUNCHER\b", "obsolete FOSS_LAUNCHER identifier"),
    (r"\bfoss_launcher\b", "obsolete foss_launcher identifier"),
]

# Compiled pattern list: (compiled_re, description)
_COMPILED = [(re.compile(p, re.IGNORECASE), d) for p, d in FORBIDDEN_PATTERNS]

# ---------------------------------------------------------------------------
# Allowlist: files where historical references are expected and marked obsolete
# ---------------------------------------------------------------------------

# Files may contain obsolete references ONLY if:
#   1. The file is explicitly listed here, AND
#   2. The same line (or an adjacent line) contains the marker: HISTORICAL_OBSOLETE_FOSS_LAUNCHER_REFERENCE
ALLOWLISTED_FILES: frozenset[str] = frozenset(
    [
        # Plans archive — historical records of past sprints; not read by agents as instructions
        "plans/archive/",
        # The evidence helper scripts used during this healing sprint
        "plans/evidence/clone-cache-foss-launcher-healing/",
    ]
)

# Inline marker that explicitly flags a reference as obsolete/historical
OBSOLETE_MARKER = "HISTORICAL_OBSOLETE_FOSS_LAUNCHER_REFERENCE"
# Inline marker for test fixtures that intentionally reference the forbidden path for rejection testing
FIXTURE_MARKER = "TEST_FIXTURE_OBSOLETE_FOSS_LAUNCHER_REFERENCE"
# Inline marker for active prohibition/guard rules that mention obsolete terms only to reject them
PROHIBITION_MARKER = "PROHIBITION_OBSOLETE_FOSS_LAUNCHER_REFERENCE"

# ---------------------------------------------------------------------------
# Directories to scan
# ---------------------------------------------------------------------------

SCAN_DIRS: list[str] = [
    "AGENTS.md",
    ".claude/commands/",
    ".agents/skills/",
    ".kilocode/skills/",
    "skills/",
    "scripts/",
    "docs/",
    ".github/",
]

# Active plan files (only current/non-archived plans)
ACTIVE_PLANS_GLOB = "plans/*.md"
ACTIVE_PLANS_SUBDIR = "plans/healing/"

# File extensions to scan
SCAN_EXTENSIONS: frozenset[str] = frozenset(
    [".py", ".md", ".yml", ".yaml", ".toml", ".txt", ".sh", ".json"]
)

# Paths to skip entirely
SKIP_PATH_PREFIXES: tuple[str, ...] = (
    ".git/",
    ".venv/",
    "runs/",         # actual clone cache — not a governance file
    "reports/",      # local-only, not read as instructions
    "content/",      # generated content pages
    "knowledge/",    # extracted knowledge artifacts
    # This script defines the forbidden patterns as string literals — skip self-scan
    "scripts/ci/checks/check_clone_cache_refs.py",
    "scripts/ci/checks/check_clone_cache_refs.py",
    # Active healing plans contain historical code samples and resolved gap entries
    "plans/healing/",
    "plans/from_chat/",
    "plans/archive/",
)


def _is_allowlisted(rel_path: str) -> bool:
    for prefix in ALLOWLISTED_FILES:
        if rel_path.startswith(prefix):
            return True
    return False


def _is_context_marked_obsolete(lines: list[str], lineno: int) -> bool:
    """Return True if the line or an adjacent line contains an allowed marker.

    Allowed markers:
      HISTORICAL_OBSOLETE_FOSS_LAUNCHER_REFERENCE — non-test code referencing the
          forbidden path for documentation/rejection purposes (e.g. error messages,
          CI comments explaining the prohibition).
      TEST_FIXTURE_OBSOLETE_FOSS_LAUNCHER_REFERENCE — test code referencing the
          forbidden path as fixture data to verify rejection behaviour.
      PROHIBITION_OBSOLETE_FOSS_LAUNCHER_REFERENCE — active guard/prohibition rule
          that mentions the obsolete term only to instruct rejection of it.
    """
    window = lines[max(0, lineno - 2) : lineno + 2]
    return any(
        OBSOLETE_MARKER in l or FIXTURE_MARKER in l or PROHIBITION_MARKER in l
        for l in window
    )


def collect_files() -> list[Path]:
    """Return all files to scan."""
    files: list[Path] = []

    for entry in SCAN_DIRS:
        target = REPO_ROOT / entry
        if target.is_file():
            files.append(target)
        elif target.is_dir():
            for f in target.rglob("*"):
                if f.is_file() and f.suffix in SCAN_EXTENSIONS:
                    files.append(f)

    # Active plans
    for f in (REPO_ROOT / "plans").glob("*.md"):
        files.append(f)
    healing_dir = REPO_ROOT / ACTIVE_PLANS_SUBDIR
    if healing_dir.exists():
        for f in healing_dir.glob("*.md"):
            files.append(f)

    return sorted(set(files))


def scan_file(filepath: Path) -> list[tuple[int, str, str]]:
    """Scan a single file, return (lineno, matched_text, description) for violations."""
    try:
        rel = filepath.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        rel = filepath.as_posix()  # out-of-repo file (e.g. tmp_path in tests)

    # Skip entirely if in a skip prefix
    for skip in SKIP_PATH_PREFIXES:
        if rel.startswith(skip):
            return []

    try:
        text = filepath.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    lines = text.splitlines()
    violations: list[tuple[int, str, str]] = []

    for lineno, line in enumerate(lines, 1):
        for pattern, desc in _COMPILED:
            if pattern.search(line):
                # Check allowlist
                if _is_allowlisted(rel):
                    if _is_context_marked_obsolete(lines, lineno - 1):
                        break  # marked as obsolete — allowed
                    # Allowlisted path but no marker — still flag
                    violations.append((lineno, line.strip(), f"{desc} [in allowlisted path but missing marker]"))
                    break
                # Not allowlisted — check for inline obsolete marker
                if _is_context_marked_obsolete(lines, lineno - 1):
                    break  # explicitly marked obsolete — skip
                violations.append((lineno, line.strip(), desc))
                break  # one violation per line is enough

    return violations


def run_checks(dry_run: bool = False) -> int:
    files = collect_files()
    all_violations: list[tuple[str, int, str, str]] = []

    for f in files:
        try:
            rel = f.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            rel = f.as_posix()  # file outside repo (e.g. temp files in tests)
        hits = scan_file(f)
        for lineno, matched, desc in hits:
            all_violations.append((rel, lineno, matched, desc))

    if not all_violations:
        print("check_clone_cache_refs: PASS — no active obsolete foss-launcher references found.")
        return 0

    print(f"check_clone_cache_refs: FAIL — {len(all_violations)} active obsolete reference(s) found:\n")
    for rel, lineno, matched, desc in all_violations:
        print(f"  {rel}:{lineno}  [{desc}]")
        print(f"    {matched[:120]}")
        print()

    print("Fix: replace obsolete foss-launcher clone-cache references with runs/.clone_cache/")
    print("     If a reference is genuinely historical and must remain, add this marker to the line:")
    print(f"     {OBSOLETE_MARKER}")
    print()
    print("Canonical clone cache: runs/.clone_cache/")

    if dry_run:
        print("\n[dry-run] Not failing — run without --dry-run to enforce.")
        return 0
    return 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report violations but exit 0")
    args = parser.parse_args()
    sys.exit(run_checks(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
