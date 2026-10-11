#!/usr/bin/env python3
"""Generate pending_page_updates.json from page_impact.json.

Reads PIA output and filters HIGH_IMPACT / MEDIUM_IMPACT pages that are NOT
in the reference subdomain.  Writes a dispatch manifest so the operator (or
a future agent workflow) knows which existing content pages need updating
after Phase 5 regenerates reference pages.

Usage:
    semantic_body_update_dispatch.py <family> <platform>
        [--page-impact PATH] [--out PATH] [--repo-root PATH]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
_REPORTS_ROOT = _REPO_ROOT / "reports" / "refresh_review"
_STATE_ROOT = _REPO_ROOT / "runs" / "state"

_REFERENCE_MARKERS = ("reference.aspose.org",)
_TARGET_SCORES = frozenset({"HIGH_IMPACT", "MEDIUM_IMPACT"})


def generate_pending_updates(
    page_impact_path: Path,
    *,
    family: str,
    platform: str,
) -> list[dict]:
    """Return list of existing content pages needing agent-assisted update."""
    data = json.loads(page_impact_path.read_text(encoding="utf-8"))
    pages = data.get("pages", [])

    pending = []
    for page in pages:
        score = page.get("pia_score", "")
        if score not in _TARGET_SCORES:
            continue
        path = page.get("path", "")
        if any(m in path for m in _REFERENCE_MARKERS):
            continue
        pending.append({
            "path": path,
            "pia_score": score,
            "signals": page.get("signals_found", []),
        })

    return pending


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate pending_page_updates.json from PIA output",
    )
    parser.add_argument("family", help="Product family")
    parser.add_argument("platform", help="Platform")
    parser.add_argument(
        "--page-impact",
        help="Path to page_impact.json (default: reports/refresh_review/{family}/{platform}/page_impact.json)",
    )
    parser.add_argument(
        "--out",
        help="Output path (default: runs/state/{family}/{platform}/pending_page_updates.json)",
    )
    parser.add_argument("--repo-root", type=Path, default=_REPO_ROOT)
    args = parser.parse_args(argv)

    repo = args.repo_root
    family, platform = args.family, args.platform

    impact_path = Path(args.page_impact) if args.page_impact else (
        repo / "reports" / "refresh_review" / family / platform / "page_impact.json"
    )
    if not impact_path.is_file():
        print(f"ERROR: page_impact.json not found: {impact_path}", file=sys.stderr)
        return 1

    pending = generate_pending_updates(impact_path, family=family, platform=platform)

    out_path = Path(args.out) if args.out else (
        repo / "runs" / "state" / family / platform / "pending_page_updates.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(pending, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Written {len(pending)} pending page updates to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
