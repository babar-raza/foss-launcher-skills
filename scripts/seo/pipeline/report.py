"""
SEO-007 report.py
==================
Consume all pipeline outputs and produce human-readable markdown reports
plus a final patch manifest.

Reads:
  reports/seo/validation_report.json
  reports/seo/opportunities.json
  reports/seo/seo_gap_summary.json
  reports/seo/recommendations.json
  reports/seo/safe_recommendations.json
  reports/seo/rejected.json
  reports/seo/safety_summary.json

Writes:
  reports/seo/summary.md               — orchestrator-level markdown report
  reports/seo/per_page/{...}/{slug}.md — per-page reports (MEDIUM + HIGH only)
  reports/seo/low_priority_summary.md  — aggregate LOW opportunity summary
  patches/seo/patch_manifest.json      — machine-readable patch manifest

CLI:
  python scripts/seo/pipeline/report.py
"""
from __future__ import annotations

import json
import logging
import sys
from collections import Counter, defaultdict
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Path setup — importable as module or runnable as __main__
# ---------------------------------------------------------------------------

_THIS_FILE = Path(__file__).resolve()
_PIPELINE_DIR = _THIS_FILE.parent        # scripts/seo/pipeline/
_REPO_ROOT = _THIS_FILE.parents[3]       # .../aspose.org

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
log = logging.getLogger("report")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Prefer the canonical output directory; fall back to the workflow-artifact
# location (reports/reports/seo/) if the canonical path has no inputs yet.
_CANONICAL_REPORTS_DIR = _REPO_ROOT / "reports" / "seo"
_ARTIFACT_REPORTS_DIR = _REPO_ROOT / "reports" / "reports" / "seo"

def _resolve_reports_dir() -> Path:
    """Return the reports dir that actually contains pipeline outputs."""
    # If canonical dir has opportunities.json already, use it (fresh local run).
    if (_CANONICAL_REPORTS_DIR / "opportunities.json").exists():
        return _CANONICAL_REPORTS_DIR
    # Fall back to the workflow-artifact location committed to the repo.
    if (_ARTIFACT_REPORTS_DIR / "opportunities.json").exists():
        return _ARTIFACT_REPORTS_DIR
    # Default to canonical (will be created on first run).
    return _CANONICAL_REPORTS_DIR

REPORTS_DIR = _resolve_reports_dir()
PATCHES_DIR = _REPO_ROOT / "patches" / "seo"
PER_PAGE_DIR = REPORTS_DIR / "per_page"


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def _load(path: Path) -> Any:
    """Load JSON file with UTF-8 encoding."""
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _write_text(path: Path, text: str) -> None:
    """Write UTF-8 text file, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    log.info("wrote %s", path.relative_to(_REPO_ROOT))


def _write_json(path: Path, data: Any) -> None:
    """Write JSON file with UTF-8 encoding."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    log.info("wrote %s", path.relative_to(_REPO_ROOT))


# ---------------------------------------------------------------------------
# Load pipeline outputs
# ---------------------------------------------------------------------------

def load_pipeline_outputs() -> dict[str, Any]:
    """Load all pipeline JSON outputs into a single dict."""
    files = {
        "validation": REPORTS_DIR / "validation_report.json",
        "opportunities": REPORTS_DIR / "opportunities.json",
        "gap_summary": REPORTS_DIR / "seo_gap_summary.json",
        "recommendations": REPORTS_DIR / "recommendations.json",
        "safe_recommendations": REPORTS_DIR / "safe_recommendations.json",
        "rejected": REPORTS_DIR / "rejected.json",
        "safety_summary": REPORTS_DIR / "safety_summary.json",
    }
    outputs: dict[str, Any] = {}
    for key, path in files.items():
        if not path.exists():
            log.warning("missing pipeline output: %s", path)
            outputs[key] = None
        else:
            outputs[key] = _load(path)
            log.info("loaded %s", path.name)
    return outputs


# ---------------------------------------------------------------------------
# Build index helpers
# ---------------------------------------------------------------------------

def _build_opp_index(opportunities_data: dict | None) -> dict[str, dict]:
    """Return page_path → opportunity dict."""
    if not opportunities_data:
        return {}
    return {o["page_path"]: o for o in opportunities_data.get("opportunities", [])}


def _build_rec_index(safe_data: dict | None) -> dict[str, dict]:
    """Return page_path → recommendation dict."""
    if not safe_data:
        return {}
    return {r["page_path"]: r for r in safe_data.get("recommendations", [])}


# ---------------------------------------------------------------------------
# SEO-007A — summary.md
# ---------------------------------------------------------------------------

def _pct(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "0.0%"
    return f"{numerator / denominator * 100:.1f}%"


def build_summary_md(outputs: dict[str, Any], today: str) -> str:
    """Produce the orchestrator-level summary.md content."""
    val = outputs["validation"] or {}
    opp = outputs["opportunities"] or {}
    gap = outputs["gap_summary"] or {}
    safe = outputs["safe_recommendations"] or {}
    rej = outputs["rejected"] or []
    safety_sum = outputs["safety_summary"] or {}

    pages_analyzed = opp.get("total_pages_analyzed", 0)
    schema_b = opp.get("schema_b_matches", 0)
    schema_a = opp.get("schema_a_matches", 0)
    match_pct = _pct(schema_b, pages_analyzed)

    opp_summary = opp.get("summary", {})
    high_count = opp_summary.get("HIGH", 0)
    med_count = opp_summary.get("MEDIUM", 0)
    low_count = opp_summary.get("LOW", 0)
    skip_count = opp_summary.get("SKIP", 0)

    total_pages = gap.get("total_pages", 0)
    miss_title = gap.get("pages_missing_seo_title", 0)
    miss_desc = gap.get("pages_missing_description", 0)
    miss_tags = gap.get("pages_missing_tags", 0)
    pct_title = gap.get("pct_missing_seo_title", 0.0)
    pct_desc = gap.get("pct_missing_description", 0.0)
    pct_tags = gap.get("pct_missing_tags", 0.0)

    recs_generated = safe.get("total_recommendations_generated", 0)
    passed = safe.get("safety_passed_count", 0)
    rejected_count = safe.get("safety_rejected_count", 0)
    human_review = safety_sum.get("requires_human_review_count", 0)

    rej_reasons = ", ".join(
        f"{r.get('reason_code', 'unknown')}"
        for r in (rej if isinstance(rej, list) else [])
    ) or "none"

    # Validation schema B counts from validation_report
    val_files = val.get("files", []) if val else []
    schema_b_count = sum(1 for f in val_files if f.get("schema") == "B")

    lines = [
        f"# SEO Analysis Report — {today}",
        "",
        "## Coverage",
        f"- Pages analyzed: {pages_analyzed}",
        f"- Matched to GSC data: {schema_b} ({match_pct}) — NOTE: match rate low because Phase 0a pending",
        f"- Schema A structural matches: {schema_a}",
        "",
        f"## SEO Field Gaps ({total_pages:,} pages total)",
        "| Field | Missing | % |",
        "| ----- | ------- | - |",
        f"| seoTitle | {miss_title:,} | {pct_title}% |",
        f"| description | {miss_desc:,} | {pct_desc}% |",
        f"| tags | {miss_tags:,} | {pct_tags}% |",
        "",
        "## Opportunities Found",
        "| Level | Count | Action |",
        "| ----- | ----- | ------ |",
        f"| HIGH | {high_count} | Ready for LLM rewrite |",
        f"| MEDIUM | {med_count} | Needs title alignment |",
        f"| LOW | {low_count} | Tag additions + missing field flags |",
        f"| SKIP | {skip_count} | No action needed |",
        "",
        "## Recommendations",
        f"- Generated: {recs_generated}",
        f"- Passed safety: {passed}",
        f"- Rejected: {rejected_count} ({rej_reasons})",
        f"- Requires human review: {human_review}",
        "",
        "## Blocked by Phase 0a",
        "Match rate will rise significantly once GSC service account is granted access to:",
        "blog.aspose.org, docs.aspose.org, kb.aspose.org, reference.aspose.org",
        "",
        "## Known Data Gaps",
        f"- All {schema_b_count} Schema B files have metrics_missing=true (pre-Phase-0 format)",
        "- Schema A data: .NET-only, 14 months old — used for structural analysis only",
    ]

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# SEO-007B — per-page markdown reports (MEDIUM + HIGH only)
# ---------------------------------------------------------------------------

def _page_path_to_report_path(page_path: str) -> Path:
    """
    Convert a page_path like:
      content/blog.aspose.org/cells/python/introducing-cells-foss-python.md
    to a per-page report path like:
      reports/seo/per_page/blog.aspose.org/cells/python/introducing-cells-foss-python.md
    """
    # Strip leading "content/"
    rel = page_path
    if rel.startswith("content/"):
        rel = rel[len("content/"):]
    return PER_PAGE_DIR / rel


def build_per_page_md(rec: dict, opp: dict | None) -> str:
    """Produce per-page markdown for a MEDIUM or HIGH recommendation."""
    page_path = rec["page_path"]
    level = rec["opportunity_level"]
    analysis_path = opp.get("analysis_path", "structural") if opp else "structural"
    signals = opp.get("signals", {}) if opp else {}
    seo_fields = opp.get("seo_fields", {}) if opp else {}

    seo_title_val = seo_fields.get("seo_title")
    desc_val = seo_fields.get("description")
    tags_val = seo_fields.get("tags", [])

    seo_title_str = f'"{seo_title_val}"  ({len(seo_title_val)} chars)' if seo_title_val else "null"
    desc_str = f'"{desc_val}"  ({len(desc_val)} chars)' if desc_val else "null"
    tags_str = str(tags_val)

    position_zone = signals.get("position_zone", "unknown")
    primary_query = signals.get("primary_query") or "null"
    ctr_gap = signals.get("ctr_gap", False)

    lines = [
        f"# SEO Report: {page_path}",
        "",
        f"**Opportunity Level:** {level}",
        f"**Analysis Path:** {analysis_path}",
        "",
        "## Current SEO Fields",
        f"- seoTitle: {seo_title_str}",
        f"- description: {desc_str}",
        f"- tags: {tags_str}",
        "",
        "## GSC Signals",
        f"- position_zone: {position_zone}",
        f"- primary_query: {primary_query}",
        f"- ctr_gap: {ctr_gap}",
        "",
        "## Recommendations",
    ]

    for field_rec in rec.get("recommendations", []):
        field = field_rec.get("field", "unknown")
        current = field_rec.get("current")
        proposed = field_rec.get("proposed")
        rationale = field_rec.get("rationale", "")
        llm_skipped = rec.get("llm_skipped", False)

        lines.append(f"### {field}")
        lines.append(f'- **Current:** {json.dumps(current)}')
        if proposed is None and llm_skipped:
            lines.append(f'- **Proposed:** null (llm_skipped=true)')
        elif proposed is None:
            lines.append(f'- **Proposed:** null')
        else:
            lines.append(f'- **Proposed:** {json.dumps(proposed)}')
        lines.append(f'- **Rationale:** "{rationale}"')
        if rec.get("requires_human_review"):
            lines.append("- ⚠️ Requires human review")
        lines.append("")

    # Source keywords from first recommendation
    recs_list = rec.get("recommendations") or [{}]
    first_rec = recs_list[0] if recs_list else {}
    source_kws = first_rec.get("source_keywords", [])
    if source_kws:
        lines.append("## Source Keywords")
        for kw in source_kws:
            lines.append(f"- {kw}")
        lines.append("")

    return "\n".join(lines)


def write_per_page_reports(
    safe_data: dict | None,
    opp_index: dict[str, dict],
) -> int:
    """Write per-page markdown for MEDIUM and HIGH only. Returns count."""
    if not safe_data:
        return 0
    count = 0
    for rec in safe_data.get("recommendations", []):
        level = rec.get("opportunity_level", "")
        if level not in ("MEDIUM", "HIGH"):
            continue
        page_path = rec["page_path"]
        opp = opp_index.get(page_path)
        md = build_per_page_md(rec, opp)
        out_path = _page_path_to_report_path(page_path)
        _write_text(out_path, md)
        count += 1
    return count


# ---------------------------------------------------------------------------
# SEO-007C — low_priority_summary.md
# ---------------------------------------------------------------------------

def build_low_priority_summary_md(safe_data: dict | None, today: str) -> str:
    """Produce aggregate LOW opportunity summary."""
    if not safe_data:
        return "# Low Priority Summary\n\nNo data available.\n"

    recs = safe_data.get("recommendations", [])
    low_recs = [r for r in recs if r.get("opportunity_level") == "LOW"]

    # Count by missing field type
    field_counts: Counter[str] = Counter()
    rationale_patterns: Counter[str] = Counter()
    site_counts: Counter[str] = Counter()

    for r in low_recs:
        site = r.get("site", "unknown")
        site_counts[site] += 1
        for rec in r.get("recommendations", []):
            field = rec.get("field", "unknown")
            field_counts[field] += 1
            rationale = rec.get("rationale", "")
            # Categorize rationale
            if "too short" in rationale:
                rationale_patterns["description_too_short"] += 1
            elif "too long" in rationale:
                rationale_patterns["description_too_long"] += 1
            elif "missing" in rationale.lower() and "seoTitle" in rationale:
                rationale_patterns["seoTitle_missing"] += 1
            elif "missing" in rationale.lower():
                rationale_patterns["field_missing"] += 1
            else:
                rationale_patterns["other"] += 1

    lines = [
        f"# Low Priority SEO Opportunities — {today}",
        "",
        f"Total LOW opportunities: {len(low_recs)}",
        "",
        "## Pages by Missing Field Type",
        "| Field | Count |",
        "| ----- | ----- |",
    ]
    for field, count in field_counts.most_common():
        lines.append(f"| {field} | {count} |")

    lines += [
        "",
        "## Pages by Site",
        "| Site | Count |",
        "| ---- | ----- |",
    ]
    for site, count in site_counts.most_common():
        lines.append(f"| {site} | {count} |")

    lines += [
        "",
        "## Issue Pattern Breakdown",
        "| Pattern | Count |",
        "| ------- | ----- |",
    ]
    for pattern, count in rationale_patterns.most_common():
        lines.append(f"| {pattern} | {count} |")

    lines += [
        "",
        "## Top 10 Most Common Rationale Patterns",
    ]
    for i, (pattern, count) in enumerate(rationale_patterns.most_common(10), 1):
        lines.append(f"{i}. **{pattern}**: {count} pages")

    lines += [
        "",
        "## Notes",
        "- Per-page files are NOT generated for LOW opportunities (596 pages would be excessive).",
        "- All LOW opportunities require human review — no proposed values are auto-generated.",
        "- To action LOWs: filter safe_recommendations.json by opportunity_level=LOW.",
        "- Recommended workflow: batch-process by site + field pattern.",
        "",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# SEO-007D — patch_manifest.json
# ---------------------------------------------------------------------------

def build_patch_manifest(safe_data: dict | None, today: str) -> dict:
    """
    Build machine-readable patch manifest.

    Include only patches where:
      safety_checks_passed=True
      AND at least one field has a non-null actionable value to apply.

    Note: requires_human_review=True does NOT block a patch from inclusion;
    the flag is preserved on the patch entry so apply.py can gate on it.
    Fields that still require human input (null proposed) are simply omitted
    from fields_to_update — only actionable fields are included.
    """
    if not safe_data:
        return {
            "batch_id": "unknown",
            "generated_at": today,
            "total_patches": 0,
            "patches": [],
        }

    batch_id = safe_data.get("batch_id", "unknown")
    patches = []

    for rec in safe_data.get("recommendations", []):
        if not rec.get("safety_checks_passed", False):
            continue

        requires_review = rec.get("requires_human_review", True)
        field_recs = rec.get("recommendations", [])

        # Build fields_to_update — collect only fields with actionable values
        seo_title_proposed = None
        description_proposed = None
        tags_to_add: list[str] = []

        for r in field_recs:
            field = r.get("field")
            proposed = r.get("proposed")
            if field == "seoTitle" and proposed is not None:
                seo_title_proposed = proposed
            elif field == "description" and proposed is not None:
                description_proposed = proposed
            elif field == "tags":
                ta = r.get("proposed") or r.get("tags_to_add") or []
                if ta:
                    tags_to_add.extend(ta)

        # Skip patches that have nothing to apply — no actionable fields at all
        has_actionable = (
            seo_title_proposed is not None
            or description_proposed is not None
            or bool(tags_to_add)
        )
        if not has_actionable:
            continue

        patches.append({
            "page_path": rec["page_path"],
            "fields_to_update": {
                "seoTitle": seo_title_proposed,
                "description": description_proposed,
                "tags_to_add": list(dict.fromkeys(tags_to_add)),  # deduplicate, preserve order
            },
            "requires_human_review": requires_review,
            "safety_checks_passed": True,
        })

    return {
        "batch_id": batch_id,
        "generated_at": today,
        "total_patches": len(patches),
        "patches": patches,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    today = str(date.today())
    log.info("SEO-007 report.py — %s", today)

    # Ensure output directories exist
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    PATCHES_DIR.mkdir(parents=True, exist_ok=True)
    PER_PAGE_DIR.mkdir(parents=True, exist_ok=True)

    # Load all pipeline outputs
    outputs = load_pipeline_outputs()

    # Build indexes
    opp_index = _build_opp_index(outputs.get("opportunities"))
    # rec_index unused at top-level but available for extension

    # --- A: summary.md ---
    summary_md = build_summary_md(outputs, today)
    _write_text(REPORTS_DIR / "summary.md", summary_md)

    # --- B: per-page reports (MEDIUM + HIGH only) ---
    per_page_count = write_per_page_reports(
        outputs.get("safe_recommendations"),
        opp_index,
    )
    log.info("wrote %d per-page reports", per_page_count)

    # --- C: low_priority_summary.md ---
    low_md = build_low_priority_summary_md(outputs.get("safe_recommendations"), today)
    _write_text(REPORTS_DIR / "low_priority_summary.md", low_md)

    # --- D: patch_manifest.json ---
    manifest = build_patch_manifest(outputs.get("safe_recommendations"), today)
    _write_json(PATCHES_DIR / "patch_manifest.json", manifest)

    # --- E: pipeline_run.json ---
    run_ts = datetime.now(timezone.utc).isoformat()
    safe = outputs.get("safe_recommendations") or {}
    opp_data = outputs.get("opportunities") or {}
    gap_data = outputs.get("gap_summary") or {}
    recs_list = safe.get("recommendations", [])
    pipeline_run = {
        "run_at": run_ts,
        "batch_id": safe.get("batch_id", "unknown"),
        "reports_dir": str(REPORTS_DIR.relative_to(_REPO_ROOT)),
        "stages_loaded": {k: v is not None for k, v in outputs.items()},
        "artifact_sizes": {
            k: (REPORTS_DIR / f"{k}.json").stat().st_size
            if (REPORTS_DIR / f"{k}.json").exists() else 0
            for k in ["opportunities", "safe_recommendations", "recommendations",
                      "validation_report", "seo_gap_summary"]
        },
        "opportunities": opp_data.get("summary", {}),
        "total_pages_analyzed": opp_data.get("total_pages_analyzed", 0),
        "gsc_match_rate_pct": round(
            opp_data.get("schema_b_matches", 0) /
            max(opp_data.get("total_pages_analyzed", 1), 1) * 100, 1
        ),
        "total_pages_inventory": gap_data.get("total_pages", 0),
        "recommendations_generated": safe.get("total_recommendations_generated", 0),
        "safety_passed": safe.get("safety_passed_count", 0),
        "requires_human_review": sum(1 for r in recs_list if r.get("requires_human_review")),
        "patches_generated": manifest["total_patches"],
        "per_page_reports": per_page_count,
    }
    _write_json(REPORTS_DIR / "pipeline_run.json", pipeline_run)

    # Summary
    print()
    print("=" * 60)
    print("SEO-007 report.py complete")
    print(f"  reports_dir          : {REPORTS_DIR.relative_to(_REPO_ROOT)}")
    print(f"  summary.md           : {REPORTS_DIR.relative_to(_REPO_ROOT)}/summary.md")
    print(f"  per-page reports     : {per_page_count} files")
    print(f"  low_priority_summary : written")
    print(f"  patch_manifest.json  : patches/seo/patch_manifest.json")
    print(f"    total_patches      : {manifest['total_patches']}")
    print(f"  pipeline_run.json    : written")
    print("=" * 60)


if __name__ == "__main__":
    main()
