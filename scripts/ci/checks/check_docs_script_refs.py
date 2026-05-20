#!/usr/bin/env python3
# Adapted from aspose.org scripts/ci/checks/ for standalone use
"""check_docs_script_refs.py — Docs-layer drift guard for stale script paths.

Scans tracked documentation files (.md, .yml, .json) for references to old
root-level script paths that should use canonical post-migration locations.

Complements check_stale_path_refs.py (which covers all file types) by focusing
on documentation and providing an allowlist for intentional historical references.

Usage:
    python scripts/ci/checks/check_docs_script_refs.py
    python scripts/ci/checks/check_docs_script_refs.py --verbose

Exit codes:
    0 — no stale references found (or all are allowlisted)
    1 — actionable stale references detected
"""
from __future__ import annotations

import argparse
import re
import subprocess
import os
import sys
from pathlib import Path

REPO_ROOT = Path(os.environ.get("REPO_ROOT", Path(__file__).resolve().parents[3]))

# Old root-level paths that should now use canonical subdirectory paths
STALE_PIPELINE_RE = re.compile(
    r"scripts/pipeline/(?!commands/|lib/|config/|tools/|tests/|core/|content_eval/|"
    r"evidence/|extraction/|scout_enrichers/|verification/|audit/|reports/|knowledge/|"
    r"_bootstrap|__init__|requirements\.txt|PIPELINE|README|INVENTORY|migration_manifest)"
    r"[a-z][a-z0-9_]*\.py"
)

STALE_CI_RE = re.compile(
    r"scripts/ci/(?!checks/|hooks/|tests/|fixtures/|pr-path-proof/|requirements\.txt)"
    r"[a-z][a-z0-9_-]*\.(?:py|sh)"
)

STALE_GAPEVAL_RE = re.compile(
    r"scripts/gap-eval/(?!src/|profiles/|requirements\.txt|known_false_positives)"
    r"[a-z][a-z0-9_]*\.py"
)

# Directories whose files are never scanned
EXCLUDE_DIRS = {"content", "reports", "runs", "node_modules", ".git", "__pycache__", ".venv"}

# Path substrings that exclude individual files
EXCLUDE_SUBSTRINGS = {
    "reports/migration/",
    "scripts/pipeline/tests/",
    "scripts/ci/tests/",
    "scripts/ci/fixtures/",
    "tests/fixtures/",
}

# Exact files that are intentionally allowed to contain old paths
ALLOWLIST_FILES = {
    # Migration plan and evidence — historical references
    "patches/agents-md-s73-manual-edit.md",
    # Translator architecture doc — references translator-internal paths
    "scripts/translator/architecture.md",
    # Migration manifest — archival artifact with old-path inventory (by design)
    "scripts/pipeline/migration_manifest.yaml",
    # Auto-generated inventory — script names appear as labels, not executable refs
    "scripts/pipeline/INVENTORY.md",
    # Registry — script names used as registry keys/labels
    "scripts/pipeline/config/registry.yaml",
    # Monkeypatch baseline — data file keyed by old script names
    "scripts/ci/monkeypatch_baseline.json",
}


def get_tracked_doc_files() -> list[Path]:
    """Get all git-tracked documentation files (excluding content/ pages)."""
    result = subprocess.run(
        ["git", "ls-files", "--", "*.md", "*.yml", "*.yaml", "*.json"],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    paths = []
    for line in result.stdout.strip().splitlines():
        if not line:
            continue
        p = REPO_ROOT / line.replace("/", "\\") if sys.platform == "win32" else REPO_ROOT / line
        rel = line.replace("\\", "/")
        # Skip excluded directories
        top = rel.split("/")[0] if "/" in rel else ""
        if top in EXCLUDE_DIRS:
            continue
        # Skip excluded substrings
        if any(sub in rel for sub in EXCLUDE_SUBSTRINGS):
            continue
        # Skip allowlisted files
        if rel in ALLOWLIST_FILES:
            continue
        if p.is_file():
            paths.append(p)
    return paths


def scan_file(path: Path) -> list[tuple[int, str, str]]:
    """Scan a documentation file for stale path references."""
    hits = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return hits

    lines = text.splitlines()
    in_fence = False
    is_md = path.suffix == ".md"

    for lineno, line in enumerate(lines, 1):
        # Skip markdown code fences (examples, not live references)
        if is_md and line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if is_md and in_fence:
            continue

        # Skip lines with explicit preserve markers
        if "# MIGRATION-PRESERVE" in line or "<!-- migration-preserve -->" in line:
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
    parser.add_argument("--verbose", action="store_true",
                        help="Print scanned file count and allowlist info")
    args = parser.parse_args()

    files = get_tracked_doc_files()
    if args.verbose:
        print(f"Scanning {len(files)} tracked documentation files...")

    all_hits: list[tuple[str, int, str, str]] = []
    for path in sorted(files):
        hits = scan_file(path)
        rel = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
        for lineno, ref, pat in hits:
            all_hits.append((rel, lineno, ref, pat))

    if all_hits:
        print(f"FAIL: {len(all_hits)} stale script path reference(s) in documentation:",
              file=sys.stderr)
        for fpath, lineno, ref, pat in all_hits[:30]:
            print(f"  {fpath}:{lineno}: {ref} [{pat}]", file=sys.stderr)
        if len(all_hits) > 30:
            print(f"  ... and {len(all_hits) - 30} more", file=sys.stderr)
        return 1

    print("OK: no stale root-level script path references in documentation")
    return 0


if __name__ == "__main__":
    sys.exit(main())
