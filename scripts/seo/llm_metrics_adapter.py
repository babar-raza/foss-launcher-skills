"""Finding #59 / SEO-LLM-METRICS-UNIFY: unified LLM budget visibility,
without unifying the call path (v14 design doc, "Platform Architecture
Hardening" Section A).

Decision carried over from that design: do not route Gemini calls through
`LLMRouter` (`llm_registry.yaml` models an OpenAI-compatible `/chat/
completions` contract; Gemini uses a different SDK, auth model, and error
surface -- rebuilding that inside LLMRouter would mean re-deriving the
already-live-proven pacing/retry/circuit-breaker logic in `get_keywords.py`
for no functional upside). Instead, both surfaces report into the SAME
existing `MetricsEventLedger` JSONL sink `recommend.py` already uses, tagged
`provider="gemini-direct"` so a reader can always tell the two providers'
numbers apart.

AGENTS.md §15 excludes Gemini/Ollama/M2M/local-model calls from
*professionalize* `token_usage`/`api_calls_count` accounting ("do not mix
them") -- this module never claims that accounting. It adds a second,
clearly-labeled provider into the same shared ledger for cross-surface
visibility (Finding #59's actual gap: "nobody can see total SEO-system LLM
spend in one place"), which is a different thing from professionalize cost
metrics and needs no `metrics_callsite_registry.yaml` entry --
`check_professionalize_call_sites.py` already excludes both real call sites
(`scripts/seo/get_keywords.py` "CS-010", `scripts/seo/review_keywords.py`
"CS-011") as boundary systems, and this module never calls
`llm.professionalize.com` or any OpenAI-compatible transport, so nothing it
does would ever match that scanner's patterns even if it weren't excluded.

Every call is wrapped in try/except and never raises -- a metrics failure
must never block keyword generation, mirroring `recommend.py`'s own
never-raises `metrics_events.extend(...)` pattern.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MAIN_PIPELINE = _REPO_ROOT / "scripts" / "pipeline"
if str(_MAIN_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_MAIN_PIPELINE))

from commands.ops.metrics_event_ledger import MetricsEventLedger  # noqa: E402
from commands.ops.metrics_schema import (  # noqa: E402
    MetricsEvent, generate_event_id, generate_run_id, now_iso8601, redact_secret_like_values,
)

log = logging.getLogger("llm_metrics_adapter")

# One run_id per process (lazily created, cached): every Gemini metrics event
# emitted by this process's lifetime lands in the same reports/metrics/events/
# {run_id}.jsonl file, the same "one file per invocation" granularity
# recommend.py's own metrics-dry-run block already establishes (a fresh
# generate_run_id() there too) -- real production runs and any test process
# that happens to exercise this code path each get their own fresh UUID,
# never colliding with each other or with a real production ledger file.
_PROCESS_RUN_ID: str | None = None


def _default_run_id() -> str:
    global _PROCESS_RUN_ID
    if _PROCESS_RUN_ID is None:
        _PROCESS_RUN_ID = generate_run_id()
    return _PROCESS_RUN_ID


def extract_gemini_token_usage(response) -> "tuple[int, int]":
    """Real `usage_metadata.prompt_token_count`/`.candidates_token_count`
    when the SDK response exposes them -- confirmed present on the real
    installed `google-generativeai` response type (`generativelanguage_v1beta`
    proto), verified live rather than assumed (v14's own open question).
    Returns (0, 0) on any missing/unexpected shape rather than raising --
    a token-count read must never crash keyword generation.
    """
    try:
        usage = response.usage_metadata
        if usage is None:
            return 0, 0
        return int(usage.prompt_token_count or 0), int(usage.candidates_token_count or 0)
    except Exception:
        return 0, 0


def record_gemini_call(
    call_site_id: str,
    consumer_id: str,
    status: str,
    *,
    model: "str | None" = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    latency_ms: "int | None" = None,
    run_id: "str | None" = None,
    redacted_error_summary: "str | None" = None,
    ledger: "MetricsEventLedger | None" = None,
) -> bool:
    """Emit one MetricsEvent for a real Gemini API call attempt.

    `status` is one of the real MetricsEvent statuses ("success", "retry",
    "failure", "timeout") -- one event per real underlying
    `model.generate_content()` attempt, so a call that hits 429 twice before
    succeeding produces 2 "retry" events plus 1 "success" event, not one
    event per logical `get_keywords_from_gemini()` invocation.

    Never raises. Returns True if the event was actually written, False if
    the attempt was swallowed (this function's own contract: a metrics
    failure must never block keyword generation).
    """
    try:
        safe_error_summary = (
            redact_secret_like_values(redacted_error_summary)[:200]
            if redacted_error_summary else None
        )
        event = MetricsEvent(
            event_id=generate_event_id(),
            call_site_id=call_site_id,
            endpoint="generativelanguage.googleapis.com",
            request_type="seo",
            status=status,
            prompt_tokens=max(int(prompt_tokens), 0),
            completion_tokens=max(int(completion_tokens), 0),
            total_tokens=max(int(prompt_tokens), 0) + max(int(completion_tokens), 0),
            api_calls_count_delta=1,
            timestamp=now_iso8601(),
            model=model,
            latency_ms=latency_ms,
            consumer_id=consumer_id,
            provider="gemini-direct",
            redacted_error_summary=safe_error_summary,
        )
        active_ledger = ledger or MetricsEventLedger(run_id or _default_run_id(), root_dir=_REPO_ROOT / "reports" / "metrics" / "events")
        active_ledger.record_event(event)
        if ledger is None:
            active_ledger.close()
        return True
    except Exception:
        log.debug("llm_metrics_adapter: failed to record a Gemini call metrics event", exc_info=True)
        return False
