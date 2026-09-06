"""
SEO-006 safety.py
==================
Deterministic safety gate for all SEO recommendations.

Reads recommendations.json, runs each recommendation through ordered safety
checks, and emits three output files:

  reports/seo/safe_recommendations.json  — passed all checks
  reports/seo/rejected.json              — failed at least one check
  reports/seo/safety_summary.json        — aggregate counts

All checks are deterministic — no LLM, no network calls.
stdlib + pyyaml only.

Check order (first failure = reject):
  1. stale_since         — model.yaml stale check
  2. path_guard          — content/ prefix + allowed site
  3. evidence_block      — no writes to evidence/model_sha/claims/apis/formats fields
  4. length_gate         — seoTitle 50-70, description 130-160
  4.5. page_metadata_consistency — SEO-PAGE-METADATA-CONSISTENCY (Contract E): WARN-only
                           title/description/subtitle consistency (never rejects; sets
                           requires_human_review). Mechanically applied once per page
                           entry, not per-field (needs both title AND description
                           sub-recs side by side) — same non-rejecting position as
                           checks 8-9 below, listed here at its conceptual position
                           in the design doc's own ordering.
  5. keyword_density     — no phrase > 2x in proposed text
  6. api_name_leak       — no new API names introduced
  7. placement_decision  — SEO-KEYWORD-INTENT-CONTRACT backstop: reject a proposal that
                           injects its own source query despite that query's own upstream
                           placement disposition being do_not_use/human_review
  8. over_opt_cap        — trim to top 4 field-level recs (not a rejection)
  9. requires_human      — set flag (not a rejection; folds in check 4.5's findings)
"""
from __future__ import annotations

import json
import logging
import re
import sys
import warnings
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

_THIS_FILE = Path(__file__).resolve()
_PIPELINE_DIR = _THIS_FILE.parent        # scripts/seo/pipeline/
_REPO_ROOT = _THIS_FILE.parents[3]       # .../aspose.org

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_SEO_SCRIPTS = _REPO_ROOT / "scripts" / "seo"
if str(_SEO_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SEO_SCRIPTS))
try:
    from seo.pipeline import metadata_consistency
except ImportError:
    from pipeline import metadata_consistency

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s: %(message)s",
)
_LOG = logging.getLogger("safety")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPORTS_DIR = _REPO_ROOT / "reports" / "seo"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

RECOMMENDATIONS_PATH = REPORTS_DIR / "recommendations.json"
SAFE_RECOMMENDATIONS_PATH = REPORTS_DIR / "safe_recommendations.json"
REJECTED_PATH = REPORTS_DIR / "rejected.json"
SAFETY_SUMMARY_PATH = REPORTS_DIR / "safety_summary.json"

KNOWLEDGE_DIR = _REPO_ROOT / "knowledge"

# Allowed site content path prefixes
_ALLOWED_PREFIXES = (
    "content/docs.aspose.org/",
    "content/blog.aspose.org/",
    "content/kb.aspose.org/",
    "content/products.aspose.org/",
    "content/reference.aspose.org/",
)

# Fields that must never be written by recommend.py
_FORBIDDEN_FIELDS = frozenset({"evidence", "model_sha", "claims", "apis", "formats"})

# SEO length bounds
_TITLE_MIN = 50
_TITLE_MAX = 70
_DESC_MIN = 130
_DESC_MAX = 160

# Keyword density: max occurrences of a phrase token in proposed text
_MAX_KEYWORD_DENSITY = 2

# Over-optimisation: max field-level recommendations per page
_MAX_RECS_PER_PAGE = 4

# Field priority for over-opt trimming (higher index = higher priority)
_FIELD_PRIORITY = {"seoTitle": 3, "description": 2, "tags": 1}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric tokens."""
    if not text:
        return []
    return re.findall(r"[a-z0-9]+", text.lower())


def _load_model_yaml(family: str | None, platform: str | None) -> dict | None:
    """
    Load knowledge/{family}/{platform}/merged/model.yaml.
    Returns None if the file does not exist (caller should warn and skip).
    """
    if not family or not platform:
        return None
    model_path = KNOWLEDGE_DIR / family / platform / "merged" / "model.yaml"
    if not model_path.exists():
        return None
    try:
        import yaml  # pyyaml
        return yaml.safe_load(model_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("Could not load model.yaml at %s: %s", model_path, exc)
        return None


def _load_api_surface(family: str | None, platform: str | None) -> set[str] | None:
    """
    Load knowledge/{family}/{platform}/merged/api_surface.json.
    Returns None if the file does not exist (caller should warn and skip).

    Expected format: list of strings OR dict with 'classes'/'methods' lists.
    Returns a set of lowercase token strings extracted from all API names.
    """
    if not family or not platform:
        return None
    api_path = KNOWLEDGE_DIR / family / platform / "merged" / "api_surface.json"
    if not api_path.exists():
        return None
    try:
        data = json.loads(api_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("Could not load api_surface.json at %s: %s", api_path, exc)
        return None

    names: set[str] = set()

    def _extract_names(obj: Any) -> None:
        if isinstance(obj, str):
            # Keep full name and also split CamelCase/dot-separated tokens
            names.add(obj.lower())
            for tok in _tokenize(obj):
                names.add(tok)
        elif isinstance(obj, list):
            for item in obj:
                _extract_names(item)
        elif isinstance(obj, dict):
            for v in obj.values():
                _extract_names(v)

    _extract_names(data)
    return names


# ---------------------------------------------------------------------------
# Safety checks
# ---------------------------------------------------------------------------


def _check_stale_since(
    rec: dict,
    model_cache: dict[tuple, dict | None],
) -> tuple[bool, str, str]:
    """
    Check 1: stale_since.
    Returns (passed, reason_code, detail).
    """
    family = rec.get("family")
    platform = rec.get("platform")
    key = (family, platform)

    if key not in model_cache:
        model = _load_model_yaml(family, platform)
        if model is None and (family and platform):
            _LOG.warning(
                "model.yaml not found for %s/%s — skipping stale_since check",
                family,
                platform,
            )
        model_cache[key] = model

    model = model_cache[key]
    if model is None:
        # File absent → skip check, don't block
        return True, "", ""

    stale = model.get("stale_since")
    if stale is not None:
        return (
            False,
            "stale_knowledge_model",
            f"model.yaml stale_since={stale!r} for {family}/{platform}",
        )
    return True, "", ""


def _check_path_guard(rec: dict) -> tuple[bool, str, str]:
    """
    Check 2: page_path must start with content/ and be within an allowed site.
    """
    page_path: str = rec.get("page_path", "")
    if not page_path.startswith("content/"):
        return (
            False,
            "path_guard_fail",
            f"page_path does not start with 'content/': {page_path!r}",
        )
    if not any(page_path.startswith(prefix) for prefix in _ALLOWED_PREFIXES):
        return (
            False,
            "path_guard_fail",
            f"page_path not within an allowed site prefix: {page_path!r}",
        )
    return True, "", ""


def _check_evidence_block(rec: dict) -> tuple[bool, str, str]:
    """
    Check 3: no recommendation may touch evidence/model_sha/claims/apis/formats.
    """
    for r in rec.get("recommendations", []):
        field = r.get("field", "")
        if field in _FORBIDDEN_FIELDS:
            return (
                False,
                "evidence_block_write_attempt",
                f"recommendation attempts to write forbidden field: {field!r}",
            )
    return True, "", ""


def _check_length_gate(r: dict) -> tuple[bool, str, str]:
    """
    Check 4 (per-rec): proposed text must meet length bounds.
    Skip if proposed is None (llm_skipped case).
    """
    field = r.get("field")
    proposed = r.get("proposed")

    if proposed is None or isinstance(proposed, list):
        # None = llm_skipped (not a violation); list = tags (no length check)
        return True, "", ""

    if not isinstance(proposed, str):
        return True, "", ""

    char_count = len(proposed)

    if field == "seoTitle":
        if not (_TITLE_MIN <= char_count <= _TITLE_MAX):
            return (
                False,
                "seo_title_length_violation",
                (
                    f"seoTitle proposed length {char_count} chars — "
                    f"must be {_TITLE_MIN}-{_TITLE_MAX}"
                ),
            )
    elif field == "description":
        if not (_DESC_MIN <= char_count <= _DESC_MAX):
            return (
                False,
                "description_length_violation",
                (
                    f"description proposed length {char_count} chars — "
                    f"must be {_DESC_MIN}-{_DESC_MAX}"
                ),
            )
    return True, "", ""


def _check_keyword_density(r: dict) -> tuple[bool, str, str]:
    """
    Check 5 (per-rec): no phrase from source_keywords appears > _MAX_KEYWORD_DENSITY
    times in the proposed text.
    """
    proposed = r.get("proposed")
    if not isinstance(proposed, str) or not proposed:
        return True, "", ""

    source_kws: list[str] = r.get("source_keywords") or []
    proposed_tokens = _tokenize(proposed)
    proposed_text_lower = proposed.lower()

    for phrase in source_kws:
        if not phrase:
            continue
        # Count non-overlapping occurrences of the full phrase (case-insensitive)
        phrase_lower = phrase.lower().strip()
        if not phrase_lower:
            continue
        count = proposed_text_lower.count(phrase_lower)
        if count > _MAX_KEYWORD_DENSITY:
            return (
                False,
                "keyword_density_violation",
                (
                    f"keyword phrase {phrase_lower!r} appears {count}x "
                    f"in proposed text (max {_MAX_KEYWORD_DENSITY})"
                ),
            )
    return True, "", ""


def _check_api_name_leak(
    r: dict,
    rec: dict,
    api_surface_cache: dict[tuple, set[str] | None],
) -> tuple[bool, str, str]:
    """
    Check 6 (per-rec): no token in proposed seoTitle/description matches an
    API surface name that was NOT already in the current seoTitle.
    """
    field = r.get("field")
    if field not in ("seoTitle", "description"):
        return True, "", ""

    proposed = r.get("proposed")
    if not isinstance(proposed, str) or not proposed:
        return True, "", ""

    family = rec.get("family")
    platform = rec.get("platform")
    key = (family, platform)

    if key not in api_surface_cache:
        api_names = _load_api_surface(family, platform)
        if api_names is None and (family and platform):
            _LOG.warning(
                "api_surface.json not found for %s/%s — skipping api_name_leak check",
                family,
                platform,
            )
        api_surface_cache[key] = api_names

    api_names = api_surface_cache[key]
    if api_names is None:
        # File absent → skip check, don't block
        return True, "", ""

    # Tokens already present in current seoTitle are allowed
    current_title: str = r.get("current") or ""
    current_tokens = set(_tokenize(current_title))

    proposed_tokens = set(_tokenize(proposed))
    new_tokens = proposed_tokens - current_tokens

    leaked = new_tokens & api_names
    if leaked:
        # Only block on proper-noun-like tokens (length > 3, not common English)
        # to avoid false positives on words like 'from', 'this', etc.
        significant_leak = {t for t in leaked if len(t) > 3}
        if significant_leak:
            return (
                False,
                "api_name_leak",
                (
                    f"proposed text introduces API name token(s) "
                    f"not in current title: {sorted(significant_leak)}"
                ),
            )
    return True, "", ""


# SEO-KEYWORD-INTENT-CONTRACT (Contract A): dispositions that must never
# reach a proposal injecting the literal source query. Kept as a plain
# string set here, not an import of keyword_intent.py's PlacementDecision
# enum -- this module's own docstring promises "no LLM, no network calls,
# stdlib + pyyaml only" and every existing check already reads recommend.py's
# output structurally rather than importing its producer; the upstream
# disposition value is already a plain string once it reaches this file.
_PLACEMENT_BLOCKING_VALUES = {"do_not_use", "human_review"}


def _check_placement_decision(r: dict) -> tuple[bool, str, str]:
    """
    Check 7 (per-rec): never trust an upstream stage's placement decision
    without a downstream re-check (this file's existing philosophy, applied
    to the new contract). Hard-fails any recommendation whose own
    signals['placement'] says do_not_use/human_review but which nonetheless
    proposes injecting that literal source query into the proposed text.
    Absent signals/placement (every existing recommendation shape, and any
    field this contract doesn't classify, e.g. tags) is not itself a
    violation -- there is nothing to re-check.
    """
    signals = r.get("signals")
    if not isinstance(signals, dict):
        return True, "", ""

    placement = signals.get("placement")
    if placement not in _PLACEMENT_BLOCKING_VALUES:
        return True, "", ""

    proposed = r.get("proposed")
    if not isinstance(proposed, str) or not proposed:
        return True, "", ""

    source_query = signals.get("source_query")
    if not isinstance(source_query, str) or not source_query.strip():
        return True, "", ""

    if source_query.strip().lower() in proposed.lower():
        return (
            False,
            "placement_decision_bypass",
            (
                f"proposed text injects source query {source_query!r} despite "
                f"its own upstream placement disposition {placement!r}"
            ),
        )
    return True, "", ""


def _effective_field_value(recs: list[dict], field: str) -> str | None:
    """The value this page's title/description would actually carry once
    this recommendation entry is applied -- the proposed value if a
    sub-rec for `field` exists and proposes a string, else that sub-rec's
    own current value. None if no sub-rec for this field exists at all in
    this entry (e.g. a LOW-tier, tags-only entry)."""
    for r in recs:
        if r.get("field") == field:
            proposed = r.get("proposed")
            if isinstance(proposed, str) and proposed:
                return proposed
            current = r.get("current")
            return current if isinstance(current, str) else None
    return None


def _proposed_field_value(recs: list[dict], field: str) -> str | None:
    """The genuinely NEW proposed value for `field` in this entry, or None
    if this entry proposes no change to it (distinct from
    _effective_field_value, which falls back to the current value)."""
    for r in recs:
        if r.get("field") == field:
            proposed = r.get("proposed")
            return proposed if isinstance(proposed, str) and proposed else None
    return None


def _check_page_metadata_consistency(rec: dict) -> list[metadata_consistency.ConsistencyFinding]:
    """Check 4.5 (page-level, WARN-only, never a rejection): SEO-PAGE-
    METADATA-CONSISTENCY (Contract E). Compares the page's EFFECTIVE
    post-application title/description (proposed-or-current, per field),
    plus -- for a family-root page -- its real current `subtitle` against
    a genuinely newly-proposed title. Returns [] when there is nothing to
    flag (including when the entry carries neither a title nor a
    description sub-rec at all)."""
    recs = rec.get("recommendations", [])
    title = _effective_field_value(recs, "seoTitle")
    description = _effective_field_value(recs, "description")
    if title is None and description is None:
        return []

    proposed_title = _proposed_field_value(recs, "seoTitle")
    subtitle = metadata_consistency.load_current_subtitle(rec.get("page_path", ""))

    source_keywords: list[str] = []
    for r in recs:
        if r.get("field") in ("seoTitle", "description"):
            source_keywords.extend(r.get("source_keywords") or [])

    report = metadata_consistency.check_page_metadata_consistency(
        rec.get("page_path", ""), title, description, subtitle,
        source_keywords=source_keywords, proposed_title=proposed_title,
    )
    return report.findings


def _apply_over_opt_cap(rec: dict) -> dict:
    """
    Check 8: trim to _MAX_RECS_PER_PAGE field-level recommendations.
    Not a rejection — modifies rec in-place (returns same dict).
    Keeps highest-priority fields first: seoTitle > description > tags.
    """
    recs = rec.get("recommendations", [])
    if len(recs) <= _MAX_RECS_PER_PAGE:
        return rec

    # Sort by field priority descending, keep top N
    sorted_recs = sorted(
        recs,
        key=lambda r: _FIELD_PRIORITY.get(r.get("field", ""), 0),
        reverse=True,
    )
    rec["recommendations"] = sorted_recs[:_MAX_RECS_PER_PAGE]
    _LOG.info(
        "over_opt_cap applied to %s: trimmed %d → %d recs",
        rec.get("page_path"),
        len(recs),
        _MAX_RECS_PER_PAGE,
    )
    return rec


def _apply_requires_human(rec: dict) -> dict:
    """
    Check 9: set requires_human_review=True if any condition is met.
    Not a rejection — modifies rec in-place. Folds in check 4.5's
    page-metadata-consistency findings (SEO-PAGE-METADATA-CONSISTENCY,
    Contract E) -- a WARN there is exactly the kind of judgment call this
    flag exists to route to a human, matching this check's own established
    precedent for llm_skipped/add_seo_title/missing-proposal.
    """
    recs = rec.get("recommendations", [])
    requires = (
        rec.get("llm_skipped", False)
        or any(r.get("action") == "add_seo_title" for r in recs)
        or any(r.get("proposed") is None for r in recs)
        or bool(rec.get("metadata_consistency_findings"))
    )
    rec["requires_human_review"] = requires
    return rec


# ---------------------------------------------------------------------------
# Per-recommendation entry safety gate
# ---------------------------------------------------------------------------


def _gate_recommendation(
    rec: dict,
    model_cache: dict[tuple, dict | None],
    api_surface_cache: dict[tuple, set[str] | None],
) -> tuple[bool, list[dict]]:
    """
    Run all safety checks for a single recommendation entry.

    Returns:
        (all_passed: bool, rejections: list[dict])

    'rejections' is a list of rejection records (one per failing per-rec check).
    Page-level rejections (stale, path_guard, evidence_block) produce a single
    rejection entry for the whole page.
    """
    rejections: list[dict] = []
    page_path = rec.get("page_path", "")

    # --- Page-level checks (any failure rejects the entire entry) ---

    # Check 1: stale_since
    passed, code, detail = _check_stale_since(rec, model_cache)
    if not passed:
        rejections.append({
            "page_path": page_path,
            "field": "*",
            "reason_code": code,
            "detail": detail,
        })
        return False, rejections

    # Check 2: path guard
    passed, code, detail = _check_path_guard(rec)
    if not passed:
        rejections.append({
            "page_path": page_path,
            "field": "*",
            "reason_code": code,
            "detail": detail,
        })
        return False, rejections

    # Check 3: evidence block
    passed, code, detail = _check_evidence_block(rec)
    if not passed:
        rejections.append({
            "page_path": page_path,
            "field": "*",
            "reason_code": code,
            "detail": detail,
        })
        return False, rejections

    # --- Per-field-recommendation checks ---
    field_rejected = False
    for r in rec.get("recommendations", []):
        field = r.get("field", "unknown")

        # Check 4: length gate
        passed, code, detail = _check_length_gate(r)
        if not passed:
            rejections.append({
                "page_path": page_path,
                "field": field,
                "reason_code": code,
                "detail": detail,
            })
            field_rejected = True
            break  # first failure = reject this entry

        # Check 5: keyword density
        passed, code, detail = _check_keyword_density(r)
        if not passed:
            rejections.append({
                "page_path": page_path,
                "field": field,
                "reason_code": code,
                "detail": detail,
            })
            field_rejected = True
            break

        # Check 6: API name leak
        passed, code, detail = _check_api_name_leak(r, rec, api_surface_cache)
        if not passed:
            rejections.append({
                "page_path": page_path,
                "field": field,
                "reason_code": code,
                "detail": detail,
            })
            field_rejected = True
            break

        # Check 7: SEO-KEYWORD-INTENT-CONTRACT placement-decision backstop
        passed, code, detail = _check_placement_decision(r)
        if not passed:
            rejections.append({
                "page_path": page_path,
                "field": field,
                "reason_code": code,
                "detail": detail,
            })
            field_rejected = True
            break

    if field_rejected:
        return False, rejections

    # --- Non-rejection adjustments ---

    # Check 4.5: page metadata consistency (SEO-PAGE-METADATA-CONSISTENCY,
    # Contract E) -- WARN-only, never rejects; stores findings for check 9
    # to fold into requires_human_review.
    findings = _check_page_metadata_consistency(rec)
    rec["metadata_consistency_findings"] = [
        {"code": f.code, "detail": f.detail} for f in findings
    ]

    # Check 8: over-optimisation cap (trim, not reject)
    _apply_over_opt_cap(rec)

    # Check 9: requires_human flag (set, not reject)
    _apply_requires_human(rec)

    return True, []


# ---------------------------------------------------------------------------
# Main run function
# ---------------------------------------------------------------------------


def run_safety(
    recommendations_path: Path | None = None,
    safe_output_path: Path | None = None,
    rejected_output_path: Path | None = None,
    summary_output_path: Path | None = None,
) -> dict:
    """
    Run the full safety gate pass.

    Reads recommendations.json, applies all checks, and writes:
      safe_recommendations.json
      rejected.json
      safety_summary.json

    Returns the safety_summary dict.
    """
    if recommendations_path is None:
        recommendations_path = RECOMMENDATIONS_PATH
    if safe_output_path is None:
        safe_output_path = SAFE_RECOMMENDATIONS_PATH
    if rejected_output_path is None:
        rejected_output_path = REJECTED_PATH
    if summary_output_path is None:
        summary_output_path = SAFETY_SUMMARY_PATH

    # ------------------------------------------------------------------
    # 1. Load recommendations.json
    # ------------------------------------------------------------------
    if not recommendations_path.exists():
        print(
            f"ERROR: recommendations.json not found at {recommendations_path}",
            file=sys.stderr,
        )
        print("Run recommend.py first.", file=sys.stderr)
        sys.exit(1)

    doc = json.loads(recommendations_path.read_text(encoding="utf-8"))
    all_recs: list[dict] = doc.get("recommendations", [])
    print(f"Loaded {len(all_recs)} recommendation entries from {recommendations_path}")

    # ------------------------------------------------------------------
    # 2. Run safety gate on each entry
    # ------------------------------------------------------------------
    model_cache: dict[tuple, dict | None] = {}
    api_surface_cache: dict[tuple, set[str] | None] = {}

    safe_recs: list[dict] = []
    all_rejections: list[dict] = []

    for rec in all_recs:
        passed, rejections = _gate_recommendation(rec, model_cache, api_surface_cache)
        if passed:
            rec["safety_checks_passed"] = True
            safe_recs.append(rec)
        else:
            all_rejections.extend(rejections)

    # ------------------------------------------------------------------
    # 3. Compute summary
    # ------------------------------------------------------------------
    by_reason: dict[str, int] = {}
    for rej in all_rejections:
        code = rej.get("reason_code", "unknown")
        by_reason[code] = by_reason.get(code, 0) + 1

    requires_human_count = sum(
        1 for r in safe_recs if r.get("requires_human_review", False)
    )

    summary = {
        "total_input": len(all_recs),
        "passed": len(safe_recs),
        "rejected": len(all_rejections),
        "by_reason_code": by_reason,
        "requires_human_review_count": requires_human_count,
    }

    # ------------------------------------------------------------------
    # 4. Build safe_recommendations output document
    # ------------------------------------------------------------------
    safe_doc = {
        "batch_id": doc.get("batch_id"),
        "run_at": doc.get("run_at"),
        "litellm_available": doc.get("litellm_available"),
        "total_input_opportunities": doc.get("total_input_opportunities"),
        "total_recommendations_generated": doc.get("total_recommendations_generated"),
        "safety_passed_count": len(safe_recs),
        "safety_rejected_count": len(all_rejections),
        "summary": doc.get("summary", {}),
        "recommendations": safe_recs,
    }

    # ------------------------------------------------------------------
    # 5. Write outputs
    # ------------------------------------------------------------------
    safe_output_path.write_text(
        json.dumps(safe_doc, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"safe_recommendations.json written to: {safe_output_path}")

    rejected_output_path.write_text(
        json.dumps(all_rejections, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"rejected.json written to: {rejected_output_path}")

    summary_output_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"safety_summary.json written to: {summary_output_path}")

    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print_summary(summary: dict) -> None:
    print()
    print("=" * 60)
    print("  SEO-006 safety.py — SAFETY GATE SUMMARY")
    print("=" * 60)
    print(f"  Total input          : {summary['total_input']}")
    print(f"  Passed               : {summary['passed']}")
    print(f"  Rejected             : {summary['rejected']}")
    print(f"  Requires human review: {summary['requires_human_review_count']}")
    print()
    by_code = summary.get("by_reason_code", {})
    if by_code:
        print("  Rejections by reason code:")
        for code, count in sorted(by_code.items()):
            print(f"    {code:<35} {count}")
    else:
        print("  No rejections.")
    print()
    print(f"  safe_recommendations.json : {SAFE_RECOMMENDATIONS_PATH}")
    print(f"  rejected.json             : {REJECTED_PATH}")
    print(f"  safety_summary.json       : {SAFETY_SUMMARY_PATH}")
    print("=" * 60)
    print()


def main() -> None:
    print("=== SEO-006 safety.py — Safety Gate ===")
    summary = run_safety()
    _print_summary(summary)


if __name__ == "__main__":
    main()
