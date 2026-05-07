"""
SEO-005 recommend.py
====================
Recommendation generation module. Reads opportunities.json and produces
structured recommendation objects for HIGH, MEDIUM, and LOW opportunities.

  HIGH   — title rewrite + description rewrite + tag additions (LLM)
  MEDIUM — seoTitle rewrite if title_aligned=False (LLM if available)
  LOW    — tag additions (deterministic) or add_seo_title placeholder

LLM access: LITELLM_KEY env var → https://llm.professionalize.com/v1/
If absent: degrade gracefully, emit llm_skipped=True recommendations.

No LLM calls for LOW opportunities — deterministic only.

Outputs:
  reports/seo/recommendations.json
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
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

from core.env_loader import load_env  # noqa: E402
load_env()

try:
    sys.path.insert(0, str(_REPO_ROOT / "scripts" / "pipeline"))
    from commands.ops.metrics_schema import (
        MetricsEvent,
        generate_event_id,
        now_iso8601,
        redact_secret_like_values,
    )
    _METRICS_AVAILABLE = True
except ImportError:
    _METRICS_AVAILABLE = False

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

# LLM settings
_LLM_BASE_URL = "https://llm.professionalize.com/v1/"
_LLM_MODEL_MEDIUM = "recommended"          # seoTitle rewrites for MEDIUM/HIGH
_LLM_MAX_RETRIES = 3
_LLM_RETRY_DELAY = 3                       # seconds between retries

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


def _emit_cs009_event(
    *,
    status: str,
    http_status: int | None,
    total_tokens: int,
    latency_ms: int,
    error_summary: str | None = None,
) -> None:
    """Append a MetricsEvent for one professionalize HTTP attempt (CS-009)."""
    if not _METRICS_AVAILABLE:
        return
    safe_error = (
        redact_secret_like_values(error_summary) if error_summary else None
    )
    event = MetricsEvent(
        event_id=generate_event_id(),
        call_site_id="CS-009",
        endpoint=_LLM_BASE_URL.rstrip("/") + "/chat/completions",
        request_type="seo",
        status=status,
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=total_tokens,
        api_calls_count_delta=1,
        timestamp=now_iso8601(),
        http_status=http_status,
        latency_ms=latency_ms,
        redacted_error_summary=safe_error,
    )
    metrics_events.append(event)


# ---------------------------------------------------------------------------
# LLM call — openai SDK pointed at custom base URL
# ---------------------------------------------------------------------------


def _call_llm(
    prompt: str,
    model: str,
    schema: dict,
    litellm_key: str,
) -> dict | None:
    """
    Call https://llm.professionalize.com/v1/chat/completions with structured
    JSON output.  Returns a parsed dict if all required schema keys are present,
    None on failure (after _LLM_MAX_RETRIES attempts).

    Args:
        prompt:      Full user prompt string.
        model:       Model ID to request.
        schema:      Dict of {key: type_description} — required keys in response.
        litellm_key: Bearer token.

    Returns:
        Parsed dict on success, None on any failure.
    """
    try:
        import openai  # local import so module is usable without openai installed
    except ImportError:
        _LOG.warning("openai package not installed — LLM calls disabled")
        return None

    client = openai.OpenAI(
        api_key=litellm_key,
        base_url=_LLM_BASE_URL,
    )

    last_exc: Exception | None = None
    for attempt in range(1, _LLM_MAX_RETRIES + 1):
        t0 = time.monotonic()
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an SEO specialist. "
                            "Respond ONLY with a valid JSON object — no markdown, no prose, "
                            "no code fences. Output raw JSON only. "
                            "Never fabricate API names, class names, or method names. "
                            "Base all suggestions strictly on the provided context."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=2048,
                temperature=0.3,
            )
            latency_ms = int((time.monotonic() - t0) * 1000)
            total_tokens = 0
            if response.usage:
                total_tokens = getattr(response.usage, "total_tokens", 0) or 0

            raw = response.choices[0].message.content
            if not raw:
                _LOG.warning("LLM returned empty content (attempt %d)", attempt)
                _emit_cs009_event(
                    status="failure", http_status=200, total_tokens=total_tokens,
                    latency_ms=latency_ms, error_summary="empty LLM response",
                )
                last_exc = ValueError("empty LLM response")
                time.sleep(_LLM_RETRY_DELAY)
                continue

            # Strip markdown code fences if present (```json ... ``` or ``` ... ```)
            stripped = raw.strip()
            if stripped.startswith("```"):
                stripped = stripped.split("```", 2)[-1] if stripped.count("```") >= 2 else stripped
                stripped = stripped.lstrip("json").strip().rstrip("`").strip()
            parsed: dict = json.loads(stripped)

            # Validate required schema keys are present
            missing = [k for k in schema if k not in parsed]
            if missing:
                _LOG.warning(
                    "LLM response missing keys %s (attempt %d)", missing, attempt
                )
                _emit_cs009_event(
                    status="failure", http_status=200, total_tokens=total_tokens,
                    latency_ms=latency_ms, error_summary=f"missing schema keys: {missing}",
                )
                last_exc = ValueError(f"missing schema keys: {missing}")
                time.sleep(_LLM_RETRY_DELAY)
                continue

            _emit_cs009_event(
                status="success", http_status=200,
                total_tokens=total_tokens, latency_ms=latency_ms,
            )
            return parsed

        except json.JSONDecodeError as exc:
            latency_ms = int((time.monotonic() - t0) * 1000)
            _LOG.warning("LLM response not valid JSON (attempt %d): %s", attempt, exc)
            _emit_cs009_event(
                status="failure", http_status=None, total_tokens=0,
                latency_ms=latency_ms, error_summary="JSON decode error",
            )
            last_exc = exc
            time.sleep(_LLM_RETRY_DELAY)
        except Exception as exc:  # noqa: BLE001
            latency_ms = int((time.monotonic() - t0) * 1000)
            _LOG.warning("LLM call error (attempt %d): %s", attempt, exc)
            # Detect timeout via openai SDK exception type when available
            _status = "timeout" if type(exc).__name__ == "APITimeoutError" else "failure"
            _emit_cs009_event(
                status=_status, http_status=None, total_tokens=0,
                latency_ms=latency_ms, error_summary=str(exc)[:200],
            )
            last_exc = exc
            time.sleep(_LLM_RETRY_DELAY)

    _LOG.warning("LLM call failed after %d attempts: %s", _LLM_MAX_RETRIES, last_exc)
    return None


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


def _build_description_rewrite_prompt(
    current_desc: str,
    primary_keyword: str,
    family: str | None,
    platform: str | None,
) -> str:
    """Build the prompt for an LLM description rewrite."""
    family_str = family or "unknown"
    platform_str = platform or "unknown"
    return (
        f"You are rewriting a meta description for an Aspose FOSS documentation page.\n\n"
        f"Family: {family_str}\n"
        f"Platform: {platform_str}\n"
        f"Primary keyword cluster: {primary_keyword}\n"
        f"Current description: {current_desc}\n\n"
        f"Rules:\n"
        f"- Proposed description MUST be between {_DESC_MIN} and {_DESC_MAX} characters\n"
        f"- MUST contain the primary keyword naturally\n"
        f"- Must be a compelling, readable summary sentence\n"
        f"- Must NOT fabricate API names or capabilities\n\n"
        f"Respond with a JSON object with exactly these keys:\n"
        f"  proposed_description: string (the new meta description)\n"
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

    recs: list[dict] = []
    llm_skipped = litellm_key is None
    source_kws = signals.get("matched_keywords") or []

    # 1. seoTitle rewrite
    current_title = seo_fields.get("seo_title")
    title_aligned = signals.get("title_aligned", True)

    if current_title and not title_aligned:
        if litellm_key:
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
            else:
                proposed_title = None
                rationale = "LLM call failed — human review required."
                llm_skipped = True
        else:
            proposed_title = None
            rationale = "LLM unavailable (no LITELLM_KEY) — human must draft."
            llm_skipped = True

        recs.append({
            "field": "seoTitle",
            "action": "rewrite",
            "current": current_title,
            "proposed": proposed_title,
            "char_count": len(proposed_title) if proposed_title else None,
            "source_keywords": source_kws[:5],
            "rationale": rationale,
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

    if not desc_ok and current_desc and litellm_key and not llm_skipped:
        prompt = _build_description_rewrite_prompt(
            current_desc, primary_kw, family, platform
        )
        llm_result = _call_llm(
            prompt,
            _LLM_MODEL_MEDIUM,
            {"proposed_description": "str", "rationale": "str"},
            litellm_key,
        )
        if llm_result:
            proposed_desc = llm_result.get("proposed_description")
            desc_rationale = llm_result.get("rationale", "LLM-proposed rewrite.")
        else:
            proposed_desc = None
            desc_rationale = "LLM call failed — human review required."
    else:
        proposed_desc = None
        if not desc_ok:
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

    recs: list[dict] = []
    llm_skipped = litellm_key is None

    current_title = seo_fields.get("seo_title")
    title_aligned = signals.get("title_aligned", True)

    # seoTitle rewrite: only if title present but misaligned
    if current_title and not title_aligned:
        if litellm_key:
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
            else:
                proposed_title = None
                rationale = "LLM call failed after retries — human review required."
                llm_skipped = True
        else:
            proposed_title = None
            rationale = "LLM unavailable (no LITELLM_KEY) — human must draft."
            llm_skipped = True

        recs.append({
            "field": "seoTitle",
            "action": "rewrite",
            "current": current_title,
            "proposed": proposed_title,
            "char_count": len(proposed_title) if proposed_title else None,
            "source_keywords": source_kws[:5],
            "rationale": rationale,
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

    print(f"Loaded {len(all_opps)} total opportunities from {opportunities_path}")

    # ------------------------------------------------------------------
    # 2. Check LLM availability
    # ------------------------------------------------------------------
    litellm_key: str | None = os.environ.get("LITELLM_KEY") or None
    litellm_available = litellm_key is not None
    if litellm_available:
        _LOG.info("LITELLM_KEY present — LLM calls enabled (model: %s)", _LLM_MODEL_MEDIUM)
    else:
        _LOG.warning("LITELLM_KEY not set — LLM calls disabled, all recs will be llm_skipped=True")

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
