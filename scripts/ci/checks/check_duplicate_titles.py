#!/usr/bin/env python3
"""check_duplicate_titles.py — CI gate for peer-consistent, non-duplicate titles.

SEO-DUPLICATE-TITLE-CI-CHECK (seo-keyword-production-integration mission,
Finding #22/#24): 31 docs devguide pages and 28 KB FAQ pages currently share
a single literal title each ("Developer Guide", "Frequently Asked
Questions") -- this pre-existing debt is being worked down via a governed
pilot backfill (SEO-TITLE-PILOT-BACKFILL-PDF-DEVGUIDE), not fixed in one
shot. This check therefore grandfathers whatever duplicate groups exist in
the checked-in baseline and BLOCKS only NEW duplicate-title groups from
being introduced -- the same "don't re-litigate existing debt, stop new
regressions" pattern this repo already uses for grade churn and no-downgrade
comparisons.

Scope: docs.aspose.org, kb.aspose.org, products.aspose.org, blog.aspose.org.
reference.aspose.org is deliberately excluded -- its title skeleton is a
bare {ClassName} by design (title_templates.yaml: reference_class), so the
same class name legitimately appearing in two different family/platform
API surfaces (e.g. a "Document" class in both pdf and words) is expected
and not a duplicate-title problem.

Modes:
  --mode report    Print every current duplicate group (baseline candidate
                    generation / manual inspection). Always exits 0.
  --mode ci        Compare current duplicates against the checked-in
                    baseline (scripts/ci/config/duplicate_titles_baseline.json).
                    Exits 1 if any NEW duplicate group (not in the baseline)
                    is found. Exits 0 otherwise, including when a
                    baseline-listed group has since been resolved (fewer
                    duplicates is always fine).
  --update-baseline   Write the current duplicate state as the new baseline
                      (only after a deliberate, reviewed title backfill --
                      never run casually, since it would silently grandfather
                      any new regression introduced since the last baseline).

Exit codes:
  0 = pass
  1 = new duplicate-title group(s) found (--mode ci only)
  2 = error (baseline missing/unreadable in --mode ci)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTENT_ROOT = REPO_ROOT / "content"
BASELINE_PATH = REPO_ROOT / "scripts" / "ci" / "config" / "duplicate_titles_baseline.json"

_LOCALE_VARIANT_RE = re.compile(r"\.[a-z]{2}\.md$", re.IGNORECASE)

# reference.aspose.org excluded by design -- see module docstring.
_CHECKED_SITES = [
    "docs.aspose.org",
    "kb.aspose.org",
    "products.aspose.org",
    "blog.aspose.org",
]

try:
    import yaml
except ImportError:
    sys.exit("check_duplicate_titles.py requires PyYAML: pip install pyyaml")


def _extract_title(text: str) -> str | None:
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        fm = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return None
    title = fm.get("title")
    return title if isinstance(title, str) else None


def find_duplicate_titles(content_root: Path | None = None) -> dict[str, list[str]]:
    """Return {title: [repo-relative paths]} for every title appearing on
    2+ pages within the same checked site. A title shared ACROSS different
    checked sites (unlikely, but not inherently wrong) is not flagged --
    only within-site duplication is a peer-consistency problem.
    """
    content_root = content_root or CONTENT_ROOT
    duplicates: dict[str, list[str]] = {}

    for site in _CHECKED_SITES:
        site_root = content_root / site
        if not site_root.exists():
            continue
        by_title: dict[str, list[str]] = {}
        for path in site_root.rglob("*.md"):
            if _LOCALE_VARIANT_RE.search(path.name):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            title = _extract_title(text)
            if not title:
                continue
            rel = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
            by_title.setdefault(title, []).append(rel)

        for title, paths in by_title.items():
            if len(paths) >= 2:
                duplicates[f"{site}::{title}"] = sorted(paths)

    return duplicates


def load_baseline() -> dict[str, list[str]]:
    if not BASELINE_PATH.exists():
        return {}
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def write_baseline(duplicates: dict[str, list[str]]) -> None:
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(
        json.dumps(duplicates, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )


def diff_against_baseline(current: dict[str, list[str]], baseline: dict[str, list[str]]) -> list[str]:
    """Return keys present in `current` but not in `baseline` -- a NEW
    duplicate-title group. A baseline group with fewer (or zero) current
    duplicates is not a regression and is not returned.
    """
    return sorted(set(current) - set(baseline))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=["report", "ci"], default="report")
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args()

    current = find_duplicate_titles()

    if args.update_baseline:
        write_baseline(current)
        print(f"Baseline updated: {len(current)} duplicate-title group(s) recorded at {BASELINE_PATH}")
        return 0

    if args.mode == "report":
        print(f"=== Duplicate Title Report ({len(current)} group(s)) ===")
        for key in sorted(current):
            site, title = key.split("::", 1)
            paths = current[key]
            print(f"  [{site}] \"{title}\" -- {len(paths)} pages")
            for p in paths[:5]:
                print(f"    {p}")
            if len(paths) > 5:
                print(f"    ... and {len(paths) - 5} more")
        return 0

    # --mode ci
    if not BASELINE_PATH.exists():
        print(f"ERROR: baseline missing at {BASELINE_PATH} -- run --update-baseline once to create it", file=sys.stderr)
        return 2
    baseline = load_baseline()
    new_groups = diff_against_baseline(current, baseline)

    if new_groups:
        print(f"BLOCK: {len(new_groups)} NEW duplicate-title group(s) introduced since the baseline:", file=sys.stderr)
        for key in new_groups:
            site, title = key.split("::", 1)
            print(f"  [{site}] \"{title}\" -- {len(current[key])} pages: {current[key]}", file=sys.stderr)
        return 1

    resolved = sorted(set(baseline) - set(current))
    if resolved:
        print(f"Note: {len(resolved)} baseline duplicate-title group(s) appear resolved (fewer/no current duplicates) -- consider --update-baseline")
    print("PASS: no new duplicate-title groups")
    return 0


if __name__ == "__main__":
    sys.exit(main())
