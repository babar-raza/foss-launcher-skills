"""
SEO-009 compare.py
==================
Post-apply verification: compare two opportunities.json snapshots and produce
a delta report showing how opportunity levels changed per page.

Usage:
  python scripts/seo/pipeline/compare.py --before <path> --after <path>
  python scripts/seo/pipeline/compare.py  # auto-discovers latest two snapshots

Reads:
  Two opportunities.json files (before/after a patch apply run).

Writes:
  reports/seo/compare_<timestamp>.json  — machine-readable delta
  reports/seo/compare_<timestamp>.md    — human-readable delta report

The delta report classifies each changed page as:
  IMPROVED   — opportunity level went down  (e.g. MEDIUM → SKIP, LOW → SKIP)
  REGRESSED  — opportunity level went up    (e.g. SKIP → LOW, LOW → HIGH)
  UNCHANGED  — same level in both snapshots
  NEW        — page appears only in "after"
  REMOVED    — page appears only in "before"
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

_THIS_FILE = Path(__file__).resolve()
_REPO_ROOT = _THIS_FILE.parents[3]

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s  %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("compare")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPORTS_DIR = _REPO_ROOT / "reports" / "seo"

# Opportunity level ordering for IMPROVED / REGRESSED classification
_LEVEL_ORDER = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "SKIP": 0}

# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def _load(path: Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)

def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    log.info("wrote %s", path.relative_to(_REPO_ROOT))

def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    log.info("wrote %s", path.relative_to(_REPO_ROOT))

# ---------------------------------------------------------------------------
# Core delta logic
# ---------------------------------------------------------------------------

def _build_level_index(opp_doc: dict) -> dict[str, str]:
    """Return page_path → opportunity_level from an opportunities.json doc."""
    return {
        o["page_path"]: o.get("opportunity_level", "SKIP")
        for o in opp_doc.get("opportunities", [])
    }


def compute_delta(
    before_doc: dict,
    after_doc: dict,
) -> dict:
    """
    Compute per-page opportunity level changes between two snapshots.

    Returns a structured delta dict with:
      - summary: counts by change_type
      - changes: list of per-page delta records
    """
    before_index = _build_level_index(before_doc)
    after_index = _build_level_index(after_doc)

    all_paths = set(before_index) | set(after_index)
    changes: list[dict] = []

    for path in sorted(all_paths):
        before_level = before_index.get(path)
        after_level = after_index.get(path)

        if before_level is None:
            change_type = "NEW"
        elif after_level is None:
            change_type = "REMOVED"
        elif before_level == after_level:
            change_type = "UNCHANGED"
        else:
            before_ord = _LEVEL_ORDER.get(before_level, -1)
            after_ord = _LEVEL_ORDER.get(after_level, -1)
            if after_ord < before_ord:
                change_type = "IMPROVED"
            else:
                change_type = "REGRESSED"

        changes.append({
            "page_path": path,
            "before": before_level,
            "after": after_level,
            "change_type": change_type,
        })

    # Summary counts
    from collections import Counter
    summary = dict(Counter(c["change_type"] for c in changes))

    return {
        "before_run_at": before_doc.get("run_at", "unknown"),
        "after_run_at": after_doc.get("run_at", "unknown"),
        "total_pages": len(all_paths),
        "summary": summary,
        "changes": changes,
    }


def build_delta_md(delta: dict) -> str:
    """Build a human-readable markdown delta report."""
    before_ts = delta["before_run_at"]
    after_ts = delta["after_run_at"]
    summary = delta.get("summary", {})
    changes = delta.get("changes", [])

    improved = [c for c in changes if c["change_type"] == "IMPROVED"]
    regressed = [c for c in changes if c["change_type"] == "REGRESSED"]
    new_pages = [c for c in changes if c["change_type"] == "NEW"]
    removed = [c for c in changes if c["change_type"] == "REMOVED"]

    lines = [
        "# SEO Opportunity Delta Report",
        "",
        f"**Before snapshot:** {before_ts}",
        f"**After snapshot:**  {after_ts}",
        "",
        "## Summary",
        "| Change Type | Count | Meaning |",
        "| ----------- | ----- | ------- |",
        f"| IMPROVED  | {summary.get('IMPROVED', 0)} | Opportunity level decreased (good — patches reduced gaps) |",
        f"| REGRESSED | {summary.get('REGRESSED', 0)} | Opportunity level increased (investigate) |",
        f"| UNCHANGED | {summary.get('UNCHANGED', 0)} | No change in opportunity level |",
        f"| NEW       | {summary.get('NEW', 0)} | Page appeared in after snapshot only |",
        f"| REMOVED   | {summary.get('REMOVED', 0)} | Page present in before only |",
        "",
    ]

    if improved:
        lines += [
            f"## Improved Pages ({len(improved)})",
            "| Page | Before | After |",
            "| ---- | ------ | ----- |",
        ]
        for c in improved[:50]:
            lines.append(f"| {c['page_path']} | {c['before']} | {c['after']} |")
        if len(improved) > 50:
            lines.append(f"| ... and {len(improved) - 50} more | | |")
        lines.append("")

    if regressed:
        lines += [
            f"## ⚠ Regressed Pages ({len(regressed)})",
            "| Page | Before | After |",
            "| ---- | ------ | ----- |",
        ]
        for c in regressed:
            lines.append(f"| {c['page_path']} | {c['before']} | {c['after']} |")
        lines.append("")

    if not improved and not regressed:
        lines += [
            "## No opportunity level changes detected.",
            "",
            "This is expected if patches haven't been applied yet, or if the",
            "GSC data hasn't refreshed since the last apply run.",
            "",
        ]

    lines += [
        "## Notes",
        "- IMPROVED pages moved to a lower opportunity level (closer to SKIP = fully optimized).",
        "- REGRESSED pages should be investigated — new content gaps or GSC signal changes.",
        "- Run this comparison 4+ weeks after applying patches to measure GSC impact.",
        "",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_compare(before_path: Path, after_path: Path) -> dict:
    """Run the comparison and write outputs. Returns the delta dict."""
    log.info("Loading before: %s", before_path)
    before_doc = _load(before_path)
    log.info("Loading after:  %s", after_path)
    after_doc = _load(after_path)

    delta = compute_delta(before_doc, after_doc)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    json_out = REPORTS_DIR / f"compare_{ts}.json"
    md_out = REPORTS_DIR / f"compare_{ts}.md"

    _write_json(json_out, delta)
    _write_text(md_out, build_delta_md(delta))

    return delta


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SEO-009: Compare two opportunities.json snapshots."
    )
    parser.add_argument(
        "--before",
        type=Path,
        help="Path to the 'before' opportunities.json snapshot.",
    )
    parser.add_argument(
        "--after",
        type=Path,
        help="Path to the 'after' opportunities.json snapshot.",
    )
    args = parser.parse_args()

    # Auto-discover if not specified
    before_path = args.before
    after_path = args.after

    if before_path is None or after_path is None:
        # Look for opportunities.json in canonical + artifact locations
        candidates = []
        for d in [_CANONICAL_REPORTS_DIR, _ARTIFACT_REPORTS_DIR]:
            p = d / "opportunities.json"
            if p.exists():
                candidates.append(p)
        if len(candidates) < 2:
            print(
                "ERROR: Could not auto-discover two opportunities.json snapshots. "
                "Provide --before and --after explicitly.",
                file=sys.stderr,
            )
            sys.exit(1)
        before_path, after_path = candidates[0], candidates[1]
        log.info("Auto-discovered: before=%s, after=%s", before_path, after_path)

    delta = run_compare(before_path, after_path)

    print()
    print("=" * 60)
    print("SEO-009 compare.py complete")
    summary = delta.get("summary", {})
    print(f"  Total pages compared : {delta['total_pages']}")
    print(f"  IMPROVED             : {summary.get('IMPROVED', 0)}")
    print(f"  REGRESSED            : {summary.get('REGRESSED', 0)}")
    print(f"  UNCHANGED            : {summary.get('UNCHANGED', 0)}")
    print(f"  NEW / REMOVED        : {summary.get('NEW', 0)} / {summary.get('REMOVED', 0)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
