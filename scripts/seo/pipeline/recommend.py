"""
SEO-005 recommend.py
====================
Recommendation generation module. Reads opportunities.json and produces
structured recommendation objects for HIGH, MEDIUM, and LOW opportunities.

  HIGH   — title rewrite + description rewrite + tag additions (LLM)
  MEDIUM — seoTitle rewrite if title_aligned=False (LLM if available)
  LOW    — tag additions (deterministic) or add_seo_title placeholder

LLM access is owned by ``LLMRouter`` and the ``seo_recommendation`` operation
profile in ``llm_registry.yaml``. If that route is unavailable, degrade
gracefully and emit ``llm_skipped=True`` recommendations.

No LLM calls for LOW opportunities — deterministic only.

Outputs:
  reports/seo/recommendations.json
"""
from __future__ import annotations

import json
import logging
import sys
import time  # compatibility seam for existing adapter tests; routing owns retries
import uuid
from datetime import date, datetime, timezone
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
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "pipeline"))

_SEO_SCRIPTS = _REPO_ROOT / "scripts" / "seo"
if str(_SEO_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SEO_SCRIPTS))

from core.env_loader import load_env  # noqa: E402
load_env()

from commands.ops.llm_router import EndpointStatus, LLMCallContext, LLMRouter  # noqa: E402
_METRICS_AVAILABLE = True  # compatibility: router always exposes metrics events

try:
    from seo.pipeline import keyword_intent  # noqa: E402
except ImportError:
    from pipeline import keyword_intent  # noqa: E402

try:
    from seo.pipeline import recommendation_memory  # noqa: E402
except ImportError:
    from pipeline import recommendation_memory  # noqa: E402

try:
    from seo.pipeline import execution_invariants  # noqa: E402
except ImportError:
    from pipeline import execution_invariants  # noqa: E402

try:
    from seo.pipeline import description_composer  # noqa: E402
except ImportError:
    from pipeline import description_composer  # noqa: E402

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s: %(message)s",
)
_LOG = logging.getLogger("recommend")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPORTS_DIR = _REPO_ROOT / "reports" / "seo"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

OPPORTUNITIES_PATH = REPORTS_DIR / "opportunities.json"
RECOMMENDATIONS_PATH = REPORTS_DIR / "recommendations.json"

# Batch ID is set once per process invocation (ISO timestamp in UTC).
# This ensures each pipeline run produces uniquely identifiable artifacts.
BATCH_ID = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

# Compatibility label retained for callers of the pre-router helper signature.
# Provider/model/retry selection is exclusively registry-owned.
_LLM_MODEL_MEDIUM = "router-managed"

# SEO length bounds
_TITLE_MIN = 50
_TITLE_MAX = 70
_DESC_MIN = 130
_DESC_MAX = 160

# Tag gap: top N query keywords to propose as tags
_TAG_TOP_N = 2

# Allowed site path prefixes (for later safety checks)
_ALLOWED_SITE_PREFIXES = (
    "content/docs.aspose.org/",
    "content/blog.aspose.org/",
    "content/kb.aspose.org/",
    "content/products.aspose.org/",
    "content/reference.aspose.org/",
)


# ---------------------------------------------------------------------------
# CS-009 Metrics capture — module-level accumulator
# ---------------------------------------------------------------------------

# Accumulates MetricsEvent objects for each professionalize HTTP attempt made via
# _call_llm. Tests read this list. Caller may call metrics_events.clear() between runs.
metrics_events: list = []


# ---------------------------------------------------------------------------
# LLM call — canonical router/client boundary
# ---------------------------------------------------------------------------


def _call_llm(
    prompt: str,
    model: str,
    schema: dict,
    litellm_key: str,
) -> dict | None:
    """
    Call the registry-owned SEO operation through ``LLMRouter``. Returns a
    parsed dict if all required schema keys are present, otherwise ``None``.

    Args:
        prompt:      Full user prompt string.
        model:       Deprecated compatibility label; the registry owns model selection.
        schema:      Dict of {key: type_description} — required keys in response.
        litellm_key: Deprecated compatibility flag; routing owns credentials.

    Returns:
        Parsed dict on success, None on any failure.
    """
    run_id = str(uuid.uuid4())
    result = LLMRouter().call_chat(
        (
            "You are an SEO specialist. Respond only with a valid JSON object. "
            "Never fabricate API names, class names, method names, or capabilities."
        ),
        prompt,
        max_tokens=2048,
        temperature=0.3,
        json_extract=True,
        operation="seo_recommendation",
        context=LLMCallContext(
            consumer_id="seo-recommend",
            run_id=run_id,
            job_type="seo-recommendation",
            work_slice_id="recommendation",
        ),
    )
    metrics_events.extend(result.metrics_events)
    if result.status != EndpointStatus.OK or not isinstance(result.data, dict):
        _LOG.warning("LLM call failed: %s — %s", result.status.value, result.error)
        return None
    missing = [key for key in schema if key not in result.data]
    if missing:
        _LOG.warning("LLM response missing keys %s", missing)
        return None
    return result.data


# ---------------------------------------------------------------------------
# Recommendation builders
# ---------------------------------------------------------------------------


def _build_seo_title_rewrite_prompt(
    current_title: str,
    primary_keyword: str,
    family: str | None,
    platform: str | None,
) -> str:
    """Build the prompt for an LLM seoTitle rewrite."""
    family_str = family or "unknown"
    platform_str = platform or "unknown"
    return (
        f"You are rewriting an SEO title for an Aspose FOSS documentation page.\n\n"
        f"Family: {family_str}\n"
        f"Platform: {platform_str}\n"
        f"Primary keyword cluster: {primary_keyword}\n"
        f"Current seoTitle: {current_title}\n\n"
        f"Rules:\n"
        f"- Proposed title MUST be between {_TITLE_MIN} and {_TITLE_MAX} characters\n"
        f"- MUST contain the primary keyword naturally (not keyword-stuffed)\n"
        f"- Must NOT be a comma-separated keyword list\n"
        f"- Must NOT fabricate or invent API class/method names\n"
        f"- Must be a natural English sentence or phrase\n\n"
        f"Respond with a JSON object with exactly these keys:\n"
        f"  proposed_title: string (the new seoTitle)\n"
        f"  rationale: string (1-2 sentences explaining the improvement)\n"
    )


def _pick_primary_keyword(signals: dict) -> str:
    """
    Pick the best primary keyword from opportunity signals.
    Prefers primary_query if present, else first matched_keyword.
    """
    pq = signals.get("primary_query")
    if pq:
        return pq
    kws = signals.get("matched_keywords") or []
    return kws[0] if kws else ""


# ---------------------------------------------------------------------------
# SEO-KEYWORD-INTENT-CONTRACT (Contract A) integration
# ---------------------------------------------------------------------------

_INTENT_SCHEMA = {
    "family": "str|null", "platform": "str|null", "action": "str|null",
    "source_format": "str|null", "target_format": "str|null",
}


def _keyword_intent_llm_call(litellm_key: "str | None"):
    """Adapter routing keyword_intent.py's cached LLM fallback through this
    module's own already-registered LLMRouter call site (_call_llm,
    operation='seo_recommendation') -- Contract A never opens a second,
    unregistered professionalize call site of its own (AGENTS.md Sec.15's
    metrics obligation is satisfied by reuse, not a new registration)."""
    if not litellm_key:
        return None

    def _call(prompt: str) -> "dict | None":
        return _call_llm(prompt, _LLM_MODEL_MEDIUM, _INTENT_SCHEMA, litellm_key)

    return _call


def _compute_placement(
    primary_kw: str,
    family: "str | None",
    platform: "str | None",
    page_path: str,
    signals: dict,
    litellm_key: "str | None",
):
    """Classify the primary keyword's search intent and decide whether it
    should even be attempted, before any composition prompt is built.
    Returns (decision, confidence, reasons); decision is None only when
    there is no primary keyword at all to classify."""
    if not primary_kw:
        return None, None, []
    intent = keyword_intent.parse_search_intent(
        primary_kw, family_hint=family, platform_hint=platform,
        llm_call=_keyword_intent_llm_call(litellm_key),
    )
    return keyword_intent.decide_placement(intent, page=page_path, signals=signals)


_DESCRIPTION_COMPOSER_SCHEMA = {"proposed_description": "str", "rationale": "str"}
_NATURALNESS_JUDGE_SCHEMA = {"status": "str", "reasons": "list"}


def _description_composer_llm_call(litellm_key: "str | None"):
    """Adapter routing description_composer.py's injected composition call
    through this module's own already-registered LLMRouter call site
    (_call_llm, operation='seo_recommendation') -- same reuse pattern as
    _keyword_intent_llm_call above (Contracts A/C never open a second,
    unregistered professionalize call site of their own, AGENTS.md Sec.15)."""
    if not litellm_key:
        return None

    def _call(prompt: str) -> "dict | None":
        return _call_llm(prompt, _LLM_MODEL_MEDIUM, _DESCRIPTION_COMPOSER_SCHEMA, litellm_key)

    return _call


def _naturalness_judge_llm_call(litellm_key: "str | None"):
    """Adapter routing naturalness_evaluator.py's Stage B judge call (Contract
    D) through this module's own already-registered LLMRouter call site --
    same reuse pattern as the two adapters above."""
    if not litellm_key:
        return None

    def _call(prompt: str) -> "dict | None":
        return _call_llm(prompt, _LLM_MODEL_MEDIUM, _NATURALNESS_JUDGE_SCHEMA, litellm_key)

    return _call


def _placement_signals_block(placement_decision, placement_confidence, placement_reasons, primary_kw):
    return {
        "placement": placement_decision.value if placement_decision else None,
        "confidence": placement_confidence,
        "reasons": placement_reasons,
        "source_query": primary_kw,
    }


def _tag_proposals_from_signals(signals: dict, current_tags: list[str]) -> list[str]:
    """
    Deterministically propose top-N matched keywords as new tags,
    filtering out any that already appear in current tags (case-insensitive).
    Uses impressions-sorted queries when available; falls back to matched_keywords.
    """
    current_lower = {t.lower().strip() for t in current_tags}

    # Prefer impression-ordered matched_keywords (already sorted in analyze.py)
    candidates = signals.get("matched_keywords") or []

    # Deduplicate and filter
    proposed: list[str] = []
    seen: set[str] = set(current_lower)
    for kw in candidates:
        kw_clean = kw.strip()
        if kw_clean.lower() not in seen:
            proposed.append(kw_clean)
            seen.add(kw_clean.lower())
        if len(proposed) >= _TAG_TOP_N:
            break

    return proposed


# ---------------------------------------------------------------------------
# Per-opportunity recommendation generation
# ---------------------------------------------------------------------------


def _gen_high_recommendations(
    opp: dict,
    litellm_key: str | None,
) -> dict:
    """
    Generate recommendations for a HIGH opportunity.
    Attempts LLM rewrite for seoTitle and description; deterministic tag proposals.
    """
    page_path = opp["page_path"]
    signals = opp.get("signals", {})
    seo_fields = opp.get("seo_fields", {})
    family = opp.get("family")
    platform = opp.get("platform")
    primary_kw = _pick_primary_keyword(signals)
    placement_decision, placement_confidence, placement_reasons = _compute_placement(
        primary_kw, family, platform, page_path, signals, litellm_key,
    )
    placement_blocks_llm = placement_decision in keyword_intent.NO_LLM_CALL_DISPOSITIONS
    signals_block = _placement_signals_block(
        placement_decision, placement_confidence, placement_reasons, primary_kw,
    )

    recs: list[dict] = []
    llm_skipped = litellm_key is None
    source_kws = signals.get("matched_keywords") or []

    # 1. seoTitle rewrite
    current_title = seo_fields.get("seo_title")
    title_aligned = signals.get("title_aligned", True)

    if current_title and not title_aligned:
        if litellm_key and not placement_blocks_llm:
            title_consult = recommendation_memory.consult_before_llm_call(
                page_path, "seoTitle", current_value=current_title,
                primary_kw=primary_kw, family=family, platform=platform,
            )
            if not title_consult["should_call_llm"]:
                cached = title_consult["cached_proposal"]
                if cached is not None:
                    proposed_title = cached.get("proposed_title")
                    rationale = cached.get("rationale", "Cached from a prior run (recommendation memory).")
                else:
                    proposed_title = None
                    rationale = (
                        f"Recommendation memory: {title_consult['reason']} for this exact "
                        "signal state — not regenerating a new guess until it changes."
                    )
                    llm_skipped = True
            else:
                prompt = _build_seo_title_rewrite_prompt(
                    current_title, primary_kw, family, platform
                )
                llm_result = _call_llm(
                    prompt,
                    _LLM_MODEL_MEDIUM,
                    {"proposed_title": "str", "rationale": "str"},
                    litellm_key,
                )
                if llm_result:
                    proposed_title = llm_result.get("proposed_title")
                    rationale = llm_result.get("rationale", "LLM-proposed rewrite.")
                    recommendation_memory.record_result(
                        page_path, "seoTitle", title_consult["signal_hash"],
                        {"proposed_title": proposed_title, "rationale": rationale},
                    )
                else:
                    proposed_title = None
                    rationale = "LLM call failed — human review required."
                    llm_skipped = True
        elif placement_blocks_llm:
            proposed_title = None
            rationale = (
                f"Keyword intent analysis returned {placement_decision.value} "
                f"({'; '.join(placement_reasons) or 'no reasons recorded'}) — "
                "LLM rewrite skipped."
            )
            llm_skipped = True
        else:
            proposed_title = None
            rationale = "LLM router operation unavailable — human must draft."
            llm_skipped = True

        recs.append({
            "field": "seoTitle",
            "action": "rewrite",
            "current": current_title,
            "proposed": proposed_title,
            "char_count": len(proposed_title) if proposed_title else None,
            "source_keywords": source_kws[:5],
            "rationale": rationale,
            "signals": signals_block,
        })
    elif not current_title:
        recs.append({
            "field": "seoTitle",
            "action": "add_seo_title",
            "current": None,
            "proposed": None,
            "char_count": None,
            "source_keywords": source_kws[:5],
            "rationale": "seoTitle missing — human must draft (HIGH priority).",
        })
        llm_skipped = True

    # 2. description rewrite
    current_desc = seo_fields.get("description")
    desc_ok = signals.get("description_ok", True)

    if not desc_ok and current_desc and litellm_key and not llm_skipped and not placement_blocks_llm:
        # Loaded before the consult call (not just before generation) so the
        # signal hash itself is sensitive to a claims change -- Contract C's
        # own explicit hash formula (v14 design doc line 674) includes
        # sorted(claim_ids); a page whose cited claims changed since the
        # last run must regenerate, not silently reuse a proposal grounded
        # in claims that no longer apply (Defect A, round-1 independent
        # review, agentId a45b555463d284f22).
        page_claims = description_composer.load_page_claims(
            page_path, family, platform, repo_root=_REPO_ROOT,
        )
        desc_consult = recommendation_memory.consult_before_llm_call(
            page_path, "description", current_value=current_desc,
            primary_kw=primary_kw, family=family, platform=platform,
            claim_ids=page_claims, composer_version=description_composer.COMPOSER_VERSION,
        )
        if not desc_consult["should_call_llm"]:
            cached = desc_consult["cached_proposal"]
            if cached is not None:
                proposed_desc = cached.get("proposed_description")
                desc_rationale = cached.get("rationale", "Cached from a prior run (recommendation memory).")
            else:
                proposed_desc = None
                desc_rationale = (
                    f"Recommendation memory: {desc_consult['reason']} for this exact "
                    "signal state — not regenerating a new guess until it changes."
                )
        else:
            candidate = description_composer.compose_description(
                page_path, current_desc, primary_kw, page_claims, family, platform,
                min_chars=_DESC_MIN, max_chars=_DESC_MAX,
                llm_call=_description_composer_llm_call(litellm_key),
                naturalness_judge_call=_naturalness_judge_llm_call(litellm_key),
            )
            if candidate is not None:
                proposed_desc = candidate.text
                desc_rationale = candidate.rationale
                recommendation_memory.record_result(
                    page_path, "description", desc_consult["signal_hash"],
                    {"proposed_description": proposed_desc, "rationale": desc_rationale},
                )
            else:
                proposed_desc = None
                desc_rationale = (
                    "Description composer (Contract C) found no grounded, "
                    "natural candidate — human review required."
                )
    else:
        proposed_desc = None
        if not desc_ok and placement_blocks_llm:
            desc_rationale = (
                f"Keyword intent analysis returned {placement_decision.value} "
                f"({'; '.join(placement_reasons) or 'no reasons recorded'}) — "
                "LLM rewrite skipped."
            )
        elif not desc_ok:
            desc_len = signals.get("description_len", 0)
            if desc_len < _DESC_MIN:
                desc_rationale = (
                    f"Description too short ({desc_len} chars, min {_DESC_MIN}) — "
                    "human review required."
                )
            else:
                desc_rationale = (
                    f"Description too long ({desc_len} chars, max {_DESC_MAX}) — "
                    "human review required."
                )
        else:
            desc_rationale = "Description length OK."

    if not desc_ok:
        recs.append({
            "field": "description",
            "action": "rewrite",
            "current": current_desc,
            "proposed": proposed_desc,
            "char_count": len(proposed_desc) if proposed_desc else None,
            "source_keywords": source_kws[:5],
            "rationale": desc_rationale,
            "signals": signals_block,
        })

    # 3. tag additions (deterministic)
    current_tags = seo_fields.get("tags") or []
    tag_gap_count = signals.get("tag_gap_count", 0)
    if tag_gap_count >= 1 or not current_tags:
        proposed_tags = _tag_proposals_from_signals(signals, current_tags)
        if proposed_tags:
            recs.append({
                "field": "tags",
                "action": "add",
                "current": current_tags,
                "proposed": proposed_tags,
                "char_count": None,
                "source_keywords": proposed_tags,
                "rationale": (
                    f"Top-{_TAG_TOP_N} impression-ranked queries not represented in "
                    "existing tags."
                ),
            })

    requires_human = (
        llm_skipped
        or any(r.get("action") == "add_seo_title" for r in recs)
        or any(r.get("proposed") is None for r in recs)
    )

    return {
        "batch_id": BATCH_ID,
        "page_path": page_path,
        "site": opp.get("site"),
        "family": family,
        "platform": platform,
        "opportunity_level": "HIGH",
        "llm_skipped": llm_skipped,
        "recommendations": recs,
        "requires_human_review": requires_human,
    }


def _gen_medium_recommendations(
    opp: dict,
    litellm_key: str | None,
) -> dict:
    """
    Generate recommendations for a MEDIUM opportunity.
    LLM rewrite only for seoTitle when title_aligned=False and seo_title is not None.
    Deterministic tag proposals if tag gap exists.
    """
    page_path = opp["page_path"]
    signals = opp.get("signals", {})
    seo_fields = opp.get("seo_fields", {})
    family = opp.get("family")
    platform = opp.get("platform")
    primary_kw = _pick_primary_keyword(signals)
    source_kws = signals.get("matched_keywords") or []
    placement_decision, placement_confidence, placement_reasons = _compute_placement(
        primary_kw, family, platform, page_path, signals, litellm_key,
    )
    placement_blocks_llm = placement_decision in keyword_intent.NO_LLM_CALL_DISPOSITIONS
    signals_block = _placement_signals_block(
        placement_decision, placement_confidence, placement_reasons, primary_kw,
    )

    recs: list[dict] = []
    llm_skipped = litellm_key is None

    current_title = seo_fields.get("seo_title")
    title_aligned = signals.get("title_aligned", True)

    # seoTitle rewrite: only if title present but misaligned
    if current_title and not title_aligned:
        if litellm_key and not placement_blocks_llm:
            title_consult = recommendation_memory.consult_before_llm_call(
                page_path, "seoTitle", current_value=current_title,
                primary_kw=primary_kw, family=family, platform=platform,
            )
            if not title_consult["should_call_llm"]:
                cached = title_consult["cached_proposal"]
                if cached is not None:
                    proposed_title = cached.get("proposed_title")
                    rationale = cached.get("rationale", "Cached from a prior run (recommendation memory).")
                else:
                    proposed_title = None
                    rationale = (
                        f"Recommendation memory: {title_consult['reason']} for this exact "
                        "signal state — not regenerating a new guess until it changes."
                    )
                    llm_skipped = True
            else:
                prompt = _build_seo_title_rewrite_prompt(
                    current_title, primary_kw, family, platform
                )
                llm_result = _call_llm(
                    prompt,
                    _LLM_MODEL_MEDIUM,
                    {"proposed_title": "str", "rationale": "str"},
                    litellm_key,
                )
                if llm_result:
                    proposed_title = llm_result.get("proposed_title")
                    rationale = llm_result.get("rationale", "LLM-proposed rewrite.")
                    _LOG.info(
                        "LLM seoTitle rewrite for %s: %r → %r",
                        page_path,
                        current_title[:50],
                        (proposed_title or "")[:50],
                    )
                    recommendation_memory.record_result(
                        page_path, "seoTitle", title_consult["signal_hash"],
                        {"proposed_title": proposed_title, "rationale": rationale},
                    )
                else:
                    proposed_title = None
                    rationale = "LLM call failed after retries — human review required."
                    llm_skipped = True
        elif placement_blocks_llm:
            proposed_title = None
            rationale = (
                f"Keyword intent analysis returned {placement_decision.value} "
                f"({'; '.join(placement_reasons) or 'no reasons recorded'}) — "
                "LLM rewrite skipped."
            )
            llm_skipped = True
        else:
            proposed_title = None
            rationale = "LLM router operation unavailable — human must draft."
            llm_skipped = True

        recs.append({
            "field": "seoTitle",
            "action": "rewrite",
            "current": current_title,
            "proposed": proposed_title,
            "char_count": len(proposed_title) if proposed_title else None,
            "source_keywords": source_kws[:5],
            "rationale": rationale,
            "signals": signals_block,
        })
    elif not current_title:
        # MEDIUM with no title — treat as add_seo_title
        recs.append({
            "field": "seoTitle",
            "action": "add_seo_title",
            "current": None,
            "proposed": None,
            "char_count": None,
            "source_keywords": source_kws[:5],
            "rationale": "seoTitle missing (MEDIUM) — human must draft.",
        })
        llm_skipped = True

    # Tag additions (deterministic) — for MEDIUM with tag gaps
    tag_gap_count = signals.get("tag_gap_count", 0)
    current_tags = seo_fields.get("tags") or []
    if tag_gap_count >= 2:
        proposed_tags = _tag_proposals_from_signals(signals, current_tags)
        if proposed_tags:
            recs.append({
                "field": "tags",
                "action": "add",
                "current": current_tags,
                "proposed": proposed_tags,
                "char_count": None,
                "source_keywords": proposed_tags,
                "rationale": (
                    f"Tag gap detected: {tag_gap_count} high-impression queries "
                    "not represented in tags."
                ),
            })

    requires_human = (
        llm_skipped
        or any(r.get("action") == "add_seo_title" for r in recs)
        or any(r.get("proposed") is None for r in recs)
    )

    return {
        "batch_id": BATCH_ID,
        "page_path": page_path,
        "site": opp.get("site"),
        "family": family,
        "platform": platform,
        "opportunity_level": "MEDIUM",
        "llm_skipped": llm_skipped,
        "recommendations": recs,
        "requires_human_review": requires_human,
    }


def _gen_low_recommendations(opp: dict) -> dict | None:
    """
    Generate recommendations for a LOW opportunity — deterministic only.
    No LLM calls.

    Returns None if there's nothing actionable to recommend.
    """
    page_path = opp["page_path"]
    signals = opp.get("signals", {})
    seo_fields = opp.get("seo_fields", {})
    family = opp.get("family")
    platform = opp.get("platform")
    source_kws = signals.get("matched_keywords") or []

    recs: list[dict] = []
    current_title = seo_fields.get("seo_title")

    # Case 1: missing seo_title entirely
    if not current_title:
        recs.append({
            "field": "seoTitle",
            "action": "add_seo_title",
            "current": None,
            "proposed": None,
            "char_count": None,
            "source_keywords": source_kws[:5],
            "rationale": (
                "seoTitle field is missing. No GSC data to confirm traffic impact — "
                "human should draft a 50-70 char title."
            ),
        })

    # Case 2: description out-of-range — flag for human review (no LLM for LOW)
    desc_ok = signals.get("description_ok", True)
    if not desc_ok:
        desc_len = signals.get("description_len", 0)
        current_desc = seo_fields.get("description")
        if desc_len < 130:
            action_rationale = (
                f"Description too short ({desc_len} chars, min 130) — "
                "human should expand."
            )
        else:
            action_rationale = (
                f"Description too long ({desc_len} chars, max 160) — "
                "human should trim."
            )
        recs.append({
            "field": "description",
            "action": "rewrite",
            "current": current_desc,
            "proposed": None,          # LOW: no LLM rewrite, human drafts
            "char_count": None,
            "source_keywords": source_kws[:3],
            "rationale": action_rationale,
        })

    # Case 3: tag gap — deterministic proposals
    tag_gap_count = signals.get("tag_gap_count", 0)
    current_tags = seo_fields.get("tags") or []
    if tag_gap_count >= 1:
        proposed_tags = _tag_proposals_from_signals(signals, current_tags)
        if proposed_tags:
            recs.append({
                "field": "tags",
                "action": "add",
                "current": current_tags,
                "proposed": proposed_tags,
                "char_count": None,
                "source_keywords": proposed_tags,
                "rationale": (
                    f"Top-{_TAG_TOP_N} impression-ranked queries not in existing tags."
                ),
            })

    if not recs:
        return None

    # For LOW: LLM always skipped; requires_human if any proposed is None
    requires_human = any(r.get("proposed") is None for r in recs)

    return {
        "batch_id": BATCH_ID,
        "page_path": page_path,
        "site": opp.get("site"),
        "family": family,
        "platform": platform,
        "opportunity_level": "LOW",
        "llm_skipped": True,
        "recommendations": recs,
        "requires_human_review": requires_human,
    }


# ---------------------------------------------------------------------------
# Main run function
# ---------------------------------------------------------------------------


def run_recommendations(
    opportunities_path: Path | None = None,
    output_path: Path | None = None,
) -> dict:
    """
    Run the full recommendation generation pass.

    Reads opportunities.json, generates recommendation objects for HIGH/MEDIUM/LOW
    opportunities (skipping SKIP), writes recommendations.json.

    Returns the full output document dict.
    """
    if opportunities_path is None:
        opportunities_path = OPPORTUNITIES_PATH
    if output_path is None:
        output_path = RECOMMENDATIONS_PATH

    # Sync recommendation_memory.py's and autonomy_state.py's own module-
    # level repo roots to this module's own _REPO_ROOT -- _REPO_ROOT is a
    # test seam (see test_metrics_recommend_adapter.py's own monkeypatch
    # conventions), and without this an isolated test run would silently
    # read/consult the REAL, shared reports/seo/recommendation_memory.json
    # and data/seo_autonomy_state.json instead of its own tmp_path. Routed
    # through execution_invariants.configure() (which syncs its OWN
    # internally-bound recommendation_memory/autonomy_state references),
    # not a direct call on this module's own imports -- this repo has two
    # live import conventions for the same sibling modules
    # (`scripts.seo.pipeline.X` in apply.py, `seo.pipeline.X` here and in
    # execution_invariants.py's own import), and Python caches a module by
    # the exact dotted name used to import it, so configuring the "wrong"
    # reference directly is a real, live-reproduced hazard this mission's
    # second independent review of SEO-EXECUTION-INVARIANTS found in
    # apply.py's own equivalent gate.
    execution_invariants.configure(repo_root=_REPO_ROOT)

    # description_composer.py is stateless (writes nothing -- see its own
    # module docstring) but its reads (page frontmatter, claims.json,
    # sibling descriptions) must still respect an isolated test's tmp_path
    # rather than silently falling through to the real, shared content/
    # knowledge trees. Not routed through execution_invariants.configure()
    # (that function's own forwarding list is Contract J's own two targets,
    # recommendation_memory/autonomy_state -- execution_invariants.py is
    # outside this card's own allowed_paths) -- a direct call here is the
    # single canonical sync point, since this file only ever imports
    # description_composer via the one `seo.pipeline` dotted path, so there
    # is no module-identity split to guard against for this particular call.
    description_composer.configure(repo_root=_REPO_ROOT)

    # --- Governance gate: execution invariants (Contract J), invariant 13
    # "recommendation_memory_readable_and_schema_matched" --- read-only,
    # fails open on a merely-missing store (load_memory() bootstraps empty),
    # only refuses on a genuine schema-version mismatch. See
    # execution_invariants.py's own module docstring for why the other 13
    # named invariants are not duplicated at this call site.
    if not execution_invariants.recommendation_memory_is_ok():
        print(
            "ERROR: recommendation-memory store failed Contract J invariant 13 "
            "(readable + schema-version-matched) — refusing to generate recommendations",
            file=sys.stderr,
        )
        sys.exit(1)

    # ------------------------------------------------------------------
    # 1. Load opportunities.json
    # ------------------------------------------------------------------
    if not opportunities_path.exists():
        print(
            f"ERROR: opportunities.json not found at {opportunities_path}",
            file=sys.stderr,
        )
        print("Run analyze.py first.", file=sys.stderr)
        sys.exit(1)

    doc = json.loads(opportunities_path.read_text(encoding="utf-8"))
    all_opps: list[dict] = doc.get("opportunities", [])
    run_at = doc.get("run_at", date.today().isoformat())

    # --- Governance gate: execution invariants (Contract J), invariant 14
    # "no_unresolved_suspension_for_family_mechanism" --- per-family, never
    # a blanket refusal of the whole run: an opportunity whose family is
    # currently SUSPENDED for title_description_writes is skipped, not
    # generated. apply.py would refuse to WRITE these anyway (its own
    # pre-existing autonomy-eligibility gate), but before this fix
    # recommend.py had zero autonomy-state awareness of any kind and kept
    # burning LLM calls / populating recommendation-memory with fresh
    # proposals for an already-stopped family -- directly against Contract
    # J's stop-the-line intent (found by this card's first independent
    # review).
    _families_present = sorted({o.get("family") for o in all_opps if o.get("family")})
    _suspended_families = {
        family for family in _families_present
        if not execution_invariants.no_unresolved_suspension([family], "title_description_writes")
    }
    if _suspended_families:
        _skipped_count = sum(1 for o in all_opps if o.get("family") in _suspended_families)
        _LOG.warning(
            "Contract J invariant 14: skipping %d opportunit(y/ies) for SUSPENDED famil(y/ies) %s",
            _skipped_count, sorted(_suspended_families),
        )
        print(
            f"Skipping {_skipped_count} opportunit(y/ies) for SUSPENDED famil(y/ies) "
            f"{sorted(_suspended_families)} (Contract J invariant 14)"
        )
        all_opps = [o for o in all_opps if o.get("family") not in _suspended_families]

    print(f"Loaded {len(all_opps)} total opportunities from {opportunities_path}")

    # ------------------------------------------------------------------
    # 2. Check LLM availability
    # ------------------------------------------------------------------
    litellm_available = LLMRouter().is_operation_available("seo_recommendation")
    litellm_key: str | None = "router-managed" if litellm_available else None
    if litellm_available:
        _LOG.info("SEO LLM router operation available")
    else:
        _LOG.warning(
            "SEO LLM router operation unavailable — all recommendations will be llm_skipped=True"
        )

    # ------------------------------------------------------------------
    # 3. Separate by level (skip SKIP)
    # ------------------------------------------------------------------
    high_opps = [o for o in all_opps if o.get("opportunity_level") == "HIGH"]
    medium_opps = [o for o in all_opps if o.get("opportunity_level") == "MEDIUM"]
    low_opps = [o for o in all_opps if o.get("opportunity_level") == "LOW"]

    print(f"  HIGH  : {len(high_opps)}")
    print(f"  MEDIUM: {len(medium_opps)}")
    print(f"  LOW   : {len(low_opps)}")

    # ------------------------------------------------------------------
    # 4. Generate recommendations
    # ------------------------------------------------------------------
    recommendations: list[dict] = []

    for opp in high_opps:
        rec = _gen_high_recommendations(opp, litellm_key)
        recommendations.append(rec)

    for opp in medium_opps:
        rec = _gen_medium_recommendations(opp, litellm_key)
        recommendations.append(rec)

    low_tag_only_count = 0
    for opp in low_opps:
        rec = _gen_low_recommendations(opp)
        if rec is not None:
            recommendations.append(rec)
            low_tag_only_count += 1

    # ------------------------------------------------------------------
    # 5. Build output document
    # ------------------------------------------------------------------
    total_input = len(high_opps) + len(medium_opps) + len(low_opps)

    output_doc = {
        "batch_id": BATCH_ID,
        "run_at": run_at,
        "litellm_available": litellm_available,
        "total_input_opportunities": total_input,
        "total_recommendations_generated": len(recommendations),
        "summary": {
            "HIGH": len(high_opps),
            "MEDIUM": len(medium_opps),
            "LOW_tag_only": low_tag_only_count,
        },
        "recommendations": recommendations,
    }

    # ------------------------------------------------------------------
    # 6. Write output
    # ------------------------------------------------------------------
    output_path.write_text(
        json.dumps(output_doc, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"recommendations.json written to: {output_path}")
    # Slice 8: Write metrics dry-run for this recommendations run
    try:
        import json as _mjson
        import uuid as _muuid
        from commands.ops.run_metrics import RunMetrics
        from commands.ops.metrics_schema import row_to_dict, generate_run_id
        _mrun_id = generate_run_id()
        _mdry_dir = _REPO_ROOT / "reports" / "metrics" / "dry"
        _mdry_dir.mkdir(parents=True, exist_ok=True)
        _mevents = list(metrics_events)  # snapshot current events
        _mdisc = output_doc.get("total_input_opportunities", 0)
        _msucc = output_doc.get("total_recommendations_generated", 0)
        _mfail = max(0, _mdisc - _msucc)
        with RunMetrics(
            run_id=_mrun_id,
            agent_name="aspose-org-seo",
            job_type="seo",
            product="seo",
            platform="all",
            website="aspose.org",
            website_section="Products",
            ledger_root=_REPO_ROOT / "reports" / "metrics" / "events",
        ) as _rm:
            if _mevents:
                _rm.record_events(_mevents)
            _mrow = _rm.to_row(
                items_discovered=_mdisc,
                items_failed=_mfail,
                items_succeeded=_msucc,
                run_duration_ms=0,
            )
        (_mdry_dir / f"{_mrun_id}.dry.json").write_text(
            _mjson.dumps(row_to_dict(_mrow), indent=2), encoding="utf-8"
        )
        # Slice 16: production submit if AGENT_METRICS_PRODUCTION=1
        from commands.ops.metrics_submitter import try_production_submit
        try_production_submit(_mrow)
    except Exception:
        pass  # metrics capture must never break SEO recommendations

    return output_doc


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print_summary(doc: dict) -> None:
    print()
    print("=" * 60)
    print("  SEO-005 recommend.py — RECOMMENDATION SUMMARY")
    print("=" * 60)
    print(f"  Batch ID             : {doc['batch_id']}")
    print(f"  Run at               : {doc['run_at']}")
    print(f"  LLM available        : {doc['litellm_available']}")
    print(f"  Total input opps     : {doc['total_input_opportunities']}")
    print(f"  Recs generated       : {doc['total_recommendations_generated']}")
    print()
    s = doc.get("summary", {})
    print(f"  HIGH recs            : {s.get('HIGH', 0)}")
    print(f"  MEDIUM recs          : {s.get('MEDIUM', 0)}")
    print(f"  LOW (tag/desc only)  : {s.get('LOW_tag_only', 0)}")
    print()

    recs = doc.get("recommendations", [])
    human_review = sum(1 for r in recs if r.get("requires_human_review"))
    llm_skipped = sum(1 for r in recs if r.get("llm_skipped"))
    print(f"  Requires human review: {human_review}")
    print(f"  LLM skipped          : {llm_skipped}")
    print()

    # Show first 2 recommendations as examples
    if recs:
        print("  Example recommendations (up to 2):")
        for rec in recs[:2]:
            print(f"    Path  : {rec['page_path']}")
            print(f"    Level : {rec['opportunity_level']}")
            for r in rec.get("recommendations", [])[:2]:
                print(f"    Field : {r['field']} / {r['action']}")
                print(f"    Prop  : {str(r.get('proposed'))[:80]}")
            print()

    print(f"  Output: {RECOMMENDATIONS_PATH}")
    print("=" * 60)
    print()


def main() -> None:
    print("=== SEO-005 recommend.py — Recommendation Generator ===")
    doc = run_recommendations()
    _print_summary(doc)


if __name__ == "__main__":
    main()
