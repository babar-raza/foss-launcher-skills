"""
body_impact.py — Map semantic changes to specific body sections.

Extends (does NOT re-implement) semantic_body_update_planner.py by adding
section-level granularity via claim_parser output (C-010).

Input:
  - reports/refresh_review/{family}/{platform}/semantic_changes.json  (WAVE 1)
  - reports/refresh_review/{family}/{platform}/claim_maps/            (WAVE 2)
  - reports/refresh_review/{family}/{platform}/planner_output.json    (optional — planner signal)

Output:
  - reports/refresh_review/{family}/{platform}/body_impact.json

CLI:
    PYTHONPATH=scripts/pipeline python -m commands.content.body_impact pdf net

Impact levels:
  DEFINITE              — exact symbol match in section claims
  HIGHLY_LIKELY         — keyword/feature match in section
  POSSIBLE_REVIEW_REQUIRED — planner flagged page; no section-level match
  VERIFIED_UNAFFECTED   — no match of any kind; page confirmed safe
"""

from pathlib import Path
import sys

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

import argparse
import glob
import json
import re
from typing import Any

# ── Impact level constants ─────────────────────────────────────────────────

IL_DEFINITE = "DEFINITE"
IL_HIGHLY_LIKELY = "HIGHLY_LIKELY"
IL_POSSIBLE = "POSSIBLE_REVIEW_REQUIRED"
IL_UNAFFECTED = "VERIFIED_UNAFFECTED"

REQUIRED_ACTIONS = {
    IL_DEFINITE: "BODY_UPDATE",
    IL_HIGHLY_LIKELY: "BODY_UPDATE",
    IL_POSSIBLE: "HUMAN_REVIEW",
    IL_UNAFFECTED: "NO_ACTION",
}

# Update type selection (used by body_refresh.py WAVE 4)
UT_SURGICAL = "SURGICAL_CLAIM_REPLACEMENT"
UT_TABLE = "TABLE_ROW_RECONCILIATION"
UT_EXAMPLE = "EXAMPLE_REGENERATION"
UT_REMOVAL = "SECTION_REMOVAL"
UT_REWRITE = "PARAGRAPH_REWRITE"

# ── Configurable defaults ──────────────────────────────────────────────────

_cfg_reports_root: str = "reports/refresh_review"


def configure(reports_root: str | None = None) -> None:
    """Override path roots for testing."""
    global _cfg_reports_root
    if reports_root is not None:
        _cfg_reports_root = reports_root


# ── Loaders ────────────────────────────────────────────────────────────────

def _load_semantic_changes(family: str, platform: str) -> list[dict]:
    """Load typed semantic changes from WAVE 1 output."""
    path = Path(_cfg_reports_root) / family / platform / "semantic_changes.json"
    if not path.exists():
        raise FileNotFoundError(
            f"semantic_changes.json not found at {path}. Run semantic_diff.py first."
        )
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_claim_maps(family: str, platform: str) -> dict[str, dict]:
    """Load per-page claim maps from WAVE 2 output. Returns {page_path: claim_map}."""
    claim_maps_dir = Path(_cfg_reports_root) / family / platform / "claim_maps"
    result: dict[str, dict] = {}
    if not claim_maps_dir.exists():
        return result
    for cm_file in claim_maps_dir.glob("*.claim_map.json"):
        with open(cm_file, encoding="utf-8") as f:
            cm = json.load(f)
        page_path = cm.get("page_path", "")
        if page_path:
            result[page_path] = cm
    return result


def _load_planner_output(family: str, platform: str) -> dict | None:
    """Optionally load existing planner output as additional signal (C-010)."""
    candidate_paths = [
        Path(_cfg_reports_root) / family / platform / "planner_output.json",
        Path("reports") / "refresh_review" / family / platform / "s73_proposals.json",
        Path("reports") / "refresh_review" / family / platform / "body_update_plan.json",
    ]
    for p in candidate_paths:
        if p.exists():
            with open(p, encoding="utf-8") as f:
                return json.load(f)
    return None


# ── Matching logic ─────────────────────────────────────────────────────────

def _normalise_symbol(s: str) -> str:
    """Lowercase and strip parens/whitespace for fuzzy comparison."""
    return re.sub(r"\([^)]*\)", "", s).lower().strip()


def _symbol_in_section(symbol: str, section: dict) -> bool:
    """Return True if symbol appears in any section claim."""
    norm = _normalise_symbol(symbol)
    for claim in section.get("claims", []):
        for detected in claim.get("detected_symbols", []):
            if norm in _normalise_symbol(detected):
                return True
        # Also check raw sentence for the symbol
        if norm in claim.get("sentence", "").lower():
            return True
    return False


def _keyword_in_section(change: dict, section: dict) -> bool:
    """Return True if change-related keyword appears in section claims."""
    symbol = change.get("symbol", "")
    # Split on dots, underscores AND CamelCase word boundaries
    # e.g. DocumentConverter → ["Document", "Converter"]
    camel_parts = re.sub(r"([A-Z])", r" \1", symbol).split()
    dot_parts = re.split(r"[._]", symbol)
    all_parts = camel_parts + dot_parts
    tokens = [t.lower() for t in all_parts if len(t) >= 4]

    for claim in section.get("claims", []):
        sentence = claim.get("sentence", "").lower()
        for token in tokens:
            if token in sentence:
                return True
    return False


def _select_update_type(change: dict, section: dict) -> str:
    """Select update type for a DEFINITE section impact."""
    change_type = change.get("change_type", "")
    # Check if section has code block content (heuristic: ``` in heading context)
    section_text = " ".join(
        c.get("sentence", "") for c in section.get("claims", [])
    )

    if change_type in ("API_REMOVED", "API_RENAMED"):
        if "table" in section.get("heading", "").lower() or "|" in section_text:
            return UT_TABLE
        if "```" in section_text or "example" in section.get("section_id", "").lower():
            return UT_EXAMPLE
        return UT_SURGICAL

    if change_type in ("API_ADDED", "API_RESURRECTED", "API_MODIFIED", "API_SIGNATURE_CHANGED"):
        return UT_REWRITE

    if change_type in ("FEATURE_REMOVED",):
        return UT_REMOVAL

    if change_type in ("FEATURE_ADDED", "BEHAVIOR_CHANGED", "CLAIM_MODIFIED"):
        return UT_REWRITE

    return UT_SURGICAL


def _match_change_to_sections(change: dict, claim_map: dict) -> list[dict]:
    """Return list of ImpactEntry objects for sections matching a change."""
    impacts: list[dict] = []
    symbol = change.get("symbol", "")
    change_type = change.get("change_type", "")
    content_impact = change.get("content_impact", "")

    # Skip internal-only changes — they don't affect user-facing prose
    if change.get("public_impact") == "INTERNAL_ONLY":
        return []

    # Skip changes with NO_ACTION content impact
    if content_impact == "NO_ACTION":
        return []

    for section in claim_map.get("sections", []):
        if _symbol_in_section(symbol, section):
            impacts.append(
                {
                    "section_id": section["section_id"],
                    "change_id": change.get("change_id", ""),
                    "heading": section["heading"],
                    "lines": [section["start_line"], section["end_line"]],
                    "reason": f"{change_type} reference to {symbol}",
                    "impact_level": IL_DEFINITE,
                    "required_action": REQUIRED_ACTIONS[IL_DEFINITE],
                    "update_type": _select_update_type(change, section),
                }
            )
        elif _keyword_in_section(change, section):
            impacts.append(
                {
                    "section_id": section["section_id"],
                    "change_id": change.get("change_id", ""),
                    "heading": section["heading"],
                    "lines": [section["start_line"], section["end_line"]],
                    "reason": f"keyword match for {symbol} ({change_type})",
                    "impact_level": IL_HIGHLY_LIKELY,
                    "required_action": REQUIRED_ACTIONS[IL_HIGHLY_LIKELY],
                    "update_type": _select_update_type(change, section),
                }
            )

    return impacts


_IMPACT_LEVEL_RANK = {IL_DEFINITE: 0, IL_HIGHLY_LIKELY: 1}


def _dedupe_affected_sections(sections: list[dict]) -> list[dict]:
    """Collapse multiple change-matches against the same section_id into one entry.

    _match_change_to_sections runs once per semantic change. A section whose prose
    mentions several changed classes (common in intro/notes boilerplate) would
    otherwise collect one near-duplicate entry per matching change, and
    body_refresh.py's consumer loop revisits actionable_sections in order — so it
    would rewrite that same section once per duplicate entry within a single pass,
    compounding near-duplicate prose and malformed markdown at each rewrite.
    Keep the highest-confidence match per section_id (DEFINITE over
    HIGHLY_LIKELY); break ties by first occurrence for determinism.
    """
    best: dict[str, dict] = {}
    order: list[str] = []
    for section in sections:
        sid = section["section_id"]
        if sid not in best:
            best[sid] = section
            order.append(sid)
            continue
        current_rank = _IMPACT_LEVEL_RANK.get(best[sid]["impact_level"], 99)
        candidate_rank = _IMPACT_LEVEL_RANK.get(section["impact_level"], 99)
        if candidate_rank < current_rank:
            best[sid] = section
    return [best[sid] for sid in order]


def _build_impact_entries(
    changes: list[dict],
    claim_maps: dict[str, dict],
    planner_output: dict | None,
) -> list[dict]:
    """Build full body_impact.json entries."""
    # Build a set of pages the planner flagged (C-010 signal)
    planner_flagged: set[str] = set()
    if planner_output:
        for entry in planner_output if isinstance(planner_output, list) else []:
            pp = entry.get("page_path", "")
            if pp:
                planner_flagged.add(pp)

    # Impact entries keyed by page_path
    page_impacts: dict[str, dict] = {}

    for change in changes:
        for page_path, claim_map in claim_maps.items():
            section_impacts = _match_change_to_sections(change, claim_map)
            if not section_impacts:
                continue

            if page_path not in page_impacts:
                impact_id = f"IMP-{len(page_impacts) + 1:04d}"
                locale = "en"  # default; extract from path
                for part in page_path.replace("\\", "/").split("/"):
                    if len(part) == 2 and part.islower():
                        locale = part
                        break

                page_impacts[page_path] = {
                    "impact_id": impact_id,
                    "page_path": page_path,
                    "locale": locale,
                    "semantic_change_ids": [],
                    "affected_sections": [],
                    "planner_signal": page_path in planner_flagged,
                }

            entry = page_impacts[page_path]
            if change["change_id"] not in entry["semantic_change_ids"]:
                entry["semantic_change_ids"].append(change["change_id"])
            entry["affected_sections"].extend(section_impacts)

    # Add planner-flagged pages with no section matches as POSSIBLE
    for pp in planner_flagged:
        if pp not in page_impacts:
            page_impacts[pp] = {
                "impact_id": f"IMP-{len(page_impacts) + 1:04d}",
                "page_path": pp,
                "locale": "en",
                "semantic_change_ids": [],
                "affected_sections": [
                    {
                        "section_id": "unknown",
                        "heading": "",
                        "lines": [0, 0],
                        "reason": "planner flagged page; no section-level match found",
                        "impact_level": IL_POSSIBLE,
                        "required_action": REQUIRED_ACTIONS[IL_POSSIBLE],
                        "update_type": UT_REWRITE,
                    }
                ],
                "planner_signal": True,
            }

    for entry in page_impacts.values():
        entry["affected_sections"] = _dedupe_affected_sections(entry["affected_sections"])

    return list(page_impacts.values())


def run(family: str, platform: str) -> list[dict]:
    """Main logic entry point (importable by tests and CLI)."""
    changes = _load_semantic_changes(family, platform)
    claim_maps = _load_claim_maps(family, platform)
    planner_output = _load_planner_output(family, platform)

    impacts = _build_impact_entries(changes, claim_maps, planner_output)

    out_path = Path(_cfg_reports_root) / family / platform / "body_impact.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(impacts, f, indent=2)

    return impacts


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "body_impact — Map semantic changes to specific body sections. "
            "Extends semantic_body_update_planner.py with section-level granularity."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  PYTHONPATH=scripts/pipeline python -m commands.content.body_impact pdf net
  PYTHONPATH=scripts/pipeline python -m commands.content.body_impact 3d java

Reads:
  reports/refresh_review/{family}/{platform}/semantic_changes.json
  reports/refresh_review/{family}/{platform}/claim_maps/*.claim_map.json

Writes:
  reports/refresh_review/{family}/{platform}/body_impact.json
        """,
    )
    parser.add_argument("family", help="Product family (e.g. pdf, 3d)")
    parser.add_argument("platform", help="Platform (e.g. net, java)")
    parser.add_argument(
        "--reports-root",
        default=None,
        help="Run-scoped reports root containing {family}/{platform}/ inputs",
    )
    args = parser.parse_args()

    try:
        if args.reports_root:
            configure(args.reports_root)
        impacts = run(args.family, args.platform)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    body_update_count = sum(
        1 for imp in impacts
        if any(s["required_action"] == "BODY_UPDATE" for s in imp["affected_sections"])
    )
    print(f"body_impact: {args.family}/{args.platform}")
    print(f"  pages impacted    : {len(impacts)}")
    print(f"  requiring update  : {body_update_count}")
    out_path = f"reports/refresh_review/{args.family}/{args.platform}/body_impact.json"
    print(f"  output            : {out_path}")


if __name__ == "__main__":
    main()
