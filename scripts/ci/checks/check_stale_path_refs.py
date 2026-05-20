#!/usr/bin/env python3
# Adapted from aspose.org scripts/ci/checks/ for standalone use
"""check_stale_path_refs.py — Detect stale old-path references after migration.

Scans non-content files for references to scripts at old root-level locations
(e.g., scripts/pipeline/commands/content/audit.py instead of scripts/pipeline/commands/content/audit.py).

Usage:
    python scripts/ci/checks/check_stale_path_refs.py
    python scripts/ci/checks/check_stale_path_refs.py --dry-run

Exit codes:
    0 — no stale references found
    1 — stale references detected
"""
from __future__ import annotations

import argparse
import re
import os
import sys
from pathlib import Path

REPO_ROOT = Path(os.environ.get("REPO_ROOT", Path(__file__).resolve().parents[3]))

# Pattern: scripts/pipeline/{name}.py where name is a lowercase module (not __init__, _bootstrap)
# This catches old root-level paths like scripts/pipeline/commands/content/audit.py
STALE_PIPELINE_RE = re.compile(
    r"scripts/pipeline/(?!commands/|lib/|config/|tools/|tests/|core/|content_eval/|"
    r"evidence/|extraction/|scout_enrichers/|verification/|audit/|knowledge/|"
    r"_bootstrap|__init__|requirements\.txt|PIPELINE|README|INVENTORY|migration_manifest)"
    r"[a-z][a-z0-9_]*\.py"
)

# Pattern: scripts/ci/{name}.py or .sh at root (not in checks/ or hooks/)
STALE_CI_RE = re.compile(
    r"scripts/ci/(?!checks/|hooks/|tests/|fixtures/|requirements\.txt)"
    r"[a-z][a-z0-9_-]*\.(?:py|sh)"
)

# Pattern: scripts/gap-eval/{name}.py at root (not in src/ or profiles/)
STALE_GAPEVAL_RE = re.compile(
    r"scripts/gap-eval/(?!src/|profiles/|requirements\.txt|known_false_positives)"
    r"[a-z][a-z0-9_]*\.py"
)

# Files/dirs to scan
SCAN_GLOBS = [
    "*.md", ".github/workflows/*.yml", ".gitlab-ci*.yml", ".claude/**/*.json", ".claude/**/*.md",
    "skills/*.md", ".agents/skills/**/*.md", ".kilocode/skills/**/*.md",
    "scripts/**/*.sh", "scripts/**/*.py",
    "docs/**/*.md",
]

# Directories to exclude from scanning
EXCLUDE_DIRS = {
    "reports", "node_modules", ".git", "__pycache__", "runs",
    "content",  # Hugo content — not script references
}

# Files to exclude (migration artifacts, test fixtures, etc.)
EXCLUDE_PATTERNS = {
    "reports/migration/",
    "scripts/pipeline/tests/",
    "scripts/ci/tests/",
    "scripts/ci/fixtures/",
    "migration_manifest.yaml",
    ".claude/settings.json",  # governance-controlled; updated via separate protocol
}


def should_scan(path: Path) -> bool:
    """Check if a file should be scanned for stale refs."""
    rel = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    for excl in EXCLUDE_PATTERNS:
        if excl in rel:
            return False
    parts = path.relative_to(REPO_ROOT).parts
    if parts and parts[0] in EXCLUDE_DIRS:
        return False
    return True


def scan_file(path: Path) -> list[tuple[int, str, str]]:
    """Scan a file for stale path references. Returns [(line_no, ref, pattern_name)]."""
    hits = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return hits

    lines = text.splitlines()
    in_fence = False
    is_md = path.suffix == ".md"

    for lineno, line in enumerate(lines, 1):
        # Skip lines inside markdown code fences (examples, not live refs)
        if is_md and line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if is_md and in_fence:
            continue

        for m in STALE_PIPELINE_RE.finditer(line):
            hits.append((lineno, m.group(), "pipeline-root"))
        for m in STALE_CI_RE.finditer(line):
            hits.append((lineno, m.group(), "ci-root"))
        for m in STALE_GAPEVAL_RE.finditer(line):
            hits.append((lineno, m.group(), "gap-eval-root"))
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Report issues but always exit 0")
    args = parser.parse_args()

    all_hits: list[tuple[str, int, str, str]] = []

    for glob_pat in SCAN_GLOBS:
        for path in sorted(REPO_ROOT.glob(glob_pat)):
            if not path.is_file():
                continue
            if not should_scan(path):
                continue
            hits = scan_file(path)
            rel = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
            for lineno, ref, pat in hits:
                all_hits.append((rel, lineno, ref, pat))

    if all_hits:
        print(f"FAIL: {len(all_hits)} stale path reference(s) found:", file=sys.stderr)
        for fpath, lineno, ref, pat in all_hits[:50]:
            print(f"  {fpath}:{lineno}: {ref} [{pat}]", file=sys.stderr)
        if len(all_hits) > 50:
            print(f"  ... and {len(all_hits) - 50} more", file=sys.stderr)
        if args.dry_run:
            print("\n(dry-run: exiting 0 despite failures)")
            return 0
        return 1

    print("OK: no stale root-level script path references found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
