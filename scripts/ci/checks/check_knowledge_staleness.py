#!/usr/bin/env python3
# Adapted from aspose.org scripts/ci/checks/ for standalone use
"""check_knowledge_staleness.py — Warn when a PR modifies content for a product
whose knowledge model has stale_since set.

Called by content-audit.yml for PRs that touch content files.
Parses each changed file's path to derive {family}/{platform}, then checks
knowledge/{family}/{platform}/model.yaml for stale_since != null.

Usage:
    python scripts/ci/checks/check_knowledge_staleness.py file1.md file2.md ...
    # Files are from: git diff --name-only origin/main...HEAD -- 'content/**/*.md'

Exit codes:
    0  All products are fresh (stale_since is null) or no knowledge model found
    0  Stale products found (advisory warning — does not block PRs)

Note: This check is always advisory. Set continue-on-error: true in the workflow.
"""

from __future__ import annotations

import re
import os
import sys
from pathlib import Path

REPO_ROOT = Path(os.environ.get("REPO_ROOT", Path(__file__).resolve().parents[3]))

# Pattern to extract {family}/{platform} from content paths.
# Handles: content/{site}/en/{family}/{platform}/...
# Also handles: content/{site}/{family}/... (products pages without /en/)
_CONTENT_PATH_RE = re.compile(
    r"^content/[^/]+/(?:en/)?([^/]+)/([^/]+)/",
)


def parse_product(filepath: str) -> tuple[str, str] | None:
    """Extract (family, platform) from a content file path. Returns None if unparseable."""
    m = _CONTENT_PATH_RE.match(filepath.replace("\\", "/"))
    if not m:
        return None
    family, platform = m.group(1), m.group(2)
    # Skip locale directories (ar, bg, ca, etc.) — these are translation variants
    # Real platforms: net, python, java, cpp, typescript
    # Locale codes are typically 2-3 chars; platform names match known values
    known_platforms = {"net", "python", "java", "cpp", "typescript"}
    locale_pattern = re.compile(r"^[a-z]{2,3}$")
    if family in known_platforms or (locale_pattern.match(family) and family not in known_platforms):
        # path is content/{site}/{locale}/{family}/{platform}/... - locale variant
        # We can't reliably extract family from locale paths - skip
        return None
    return family, platform


def check_staleness(family: str, platform: str) -> str | None:
    """Return stale_since string if the product is stale, None if fresh or model missing."""
    model_path = REPO_ROOT / "knowledge" / family / platform / "model.yaml"
    if not model_path.exists():
        return None
    try:
        text = model_path.read_text(encoding="utf-8")
        # Fast regex parse - avoid yaml dependency in CI
        m = re.search(r"^stale_since\s*:\s*(.+)$", text, re.MULTILINE)
        if not m:
            return None
        value = m.group(1).strip().strip('"\'')
        # null, ~, empty string = not stale
        if value in ("null", "~", "", "None"):
            return None
        return value
    except (OSError, UnicodeDecodeError):
        return None


def main(argv: list[str]) -> int:
    if not argv:
        print("No files provided — nothing to check.")
        return 0

    # Collect unique (family, platform) pairs from changed files
    products: dict[tuple[str, str], list[str]] = {}
    for filepath in argv:
        result = parse_product(filepath)
        if result:
            if result not in products:
                products[result] = []
            products[result].append(filepath)

    if not products:
        print("No recognizable product paths in changed files.")
        return 0

    stale: list[tuple[str, str, str]] = []
    for (family, platform), files in sorted(products.items()):
        since = check_staleness(family, platform)
        if since:
            stale.append((family, platform, since))

    if not stale:
        print(f"Knowledge freshness: OK — all {len(products)} product(s) have current knowledge.")
        return 0

    print(f"::warning::Knowledge staleness detected in {len(stale)} product(s):")
    for family, platform, since in stale:
        print(
            f"::warning::{family}/{platform}: stale_since={since} — "
            f"run knowledge-diff then knowledge-update before writing content"
        )
    print(
        f"\nSummary: {len(stale)} stale product(s) in this PR. "
        "Content written against stale knowledge may contain incorrect API claims. "
        "This is an advisory warning — the PR is not blocked."
    )
    # Always exit 0 — staleness is advisory, not a hard gate
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
