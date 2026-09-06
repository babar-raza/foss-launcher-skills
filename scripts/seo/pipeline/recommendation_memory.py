"""SEO-RECOMMENDATION-MEMORY (Finding #69): persist recommend.py's LLM
proposals keyed on grounded-signal state, so an unchanged page stops
regenerating a fresh (and possibly differently-bad) proposal every
scheduled run.

Before recommend.py's `_gen_high_recommendations`/`_gen_medium_recommendations`
would call `_call_llm` for a given (page_path, field): look up the hash of
exactly what that call's prompt is built from (the current field text, the
primary keyword, and family/platform). No entry -> generate fresh. An
existing entry whose hash matches and whose outcome is `pending`/`approved`/
`applied` -> reuse the cached proposal, no LLM call. An existing entry whose
hash matches and whose outcome is `rejected_by_s116`/`requires_human_review`
-> do not regenerate a new guess for the same rejected signal state (this is
a "stuck" page/field, surfaced elsewhere, not spammed weekly). An existing
entry whose hash has CHANGED -> the page genuinely changed since the last
proposal; generate fresh, matching `get_keywords.py`'s own
title-changed-triggers-regeneration precedent (Finding #51) exactly.

Store: `reports/seo/recommendation_memory.json`, one current entry per
(page_path, field) -- a new hash simply replaces the old entry. There is no
value in keeping a stale entry once the signal state it was computed from no
longer exists.

`record_outcome()` is the write-back hook S-116's real approve/reject
verdict (and `apply.py`'s real applied verdict) would call to close the
review-to-memory loop -- it only updates an existing entry's `outcome`
field, never overriding what S-116/apply.py actually decided. It is
exposed here but NOT wired into `apply.py`/`safety.py` by this card: both
are outside this card's own `allowed_paths` (write-back is additive, not a
change to their own governance gates), left for a future card to call,
mirroring the same zero-caller-foundation pattern this mission already
used for `scripts/seo/pipeline/pipeline_state.py` (SEO-STATE-MANIFEST).

Fail-open-loud: every read/write failure here is caught and logged, never
raised. `consult_before_llm_call()` defaults to `should_call_llm=True` on
any internal error -- the always-safe fallback recommend.py already has
for every other failure mode -- and `record_result()`/`record_outcome()`
return `False` on failure instead of raising, mirroring the same
non-fatal discipline already established for `pipeline_state.py`
(SEO-STATE-MANIFEST) and `scripts/seo/llm_metrics_adapter.py`
(SEO-LLM-METRICS-UNIFY).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from seo.pipeline import pipeline_state  # noqa: E402
except ImportError:
    from pipeline import pipeline_state  # noqa: E402

log = logging.getLogger(__name__)

_THIS_FILE = Path(__file__).resolve()
_DEFAULT_REPO_ROOT = _THIS_FILE.parents[3]
REPO_ROOT = _DEFAULT_REPO_ROOT

SCHEMA_VERSION = 1
_STORE_RELPATH = "reports/seo/recommendation_memory.json"

# Outcomes meaning "we already have a good answer for this exact signal
# state -- reuse it, never re-ask the LLM."
_REUSE_OUTCOMES = frozenset({"pending", "approved", "applied"})
# Outcomes meaning "a human/S-116 already said no to this exact signal
# state -- do not spam a new guess; this is a 'stuck' page/field."
_STUCK_OUTCOMES = frozenset({"rejected_by_s116", "requires_human_review"})


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override the module-level repo root for testing."""
    global REPO_ROOT
    REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT


def _store_path() -> Path:
    return REPO_ROOT / _STORE_RELPATH


def compute_signal_hash(*, current_value: "str | None", primary_kw: "str | None",
                         family: "str | None", platform: "str | None") -> str:
    """Tier-1 deterministic: byte-identical input always produces the
    byte-identical hash. Covers exactly what recommend.py's prompt builders
    take as grounding context for a field rewrite -- the current field
    text, the primary keyword, and family/platform."""
    canonical = json.dumps(
        {
            "current_value": current_value,
            "primary_kw": primary_kw,
            "family": family,
            "platform": platform,
        },
        sort_keys=True,
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_memory() -> dict:
    """The current memory store, or a bootstrap-empty shape if none exists
    yet or the file is unreadable/corrupt."""
    path = _store_path()
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "entries": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or not isinstance(data.get("entries"), dict):
            raise ValueError("unexpected recommendation_memory.json shape")
        return data
    except Exception:
        log.warning("recommendation_memory.py: failed to read %s; treating as empty", path, exc_info=True)
        return {"schema_version": SCHEMA_VERSION, "entries": {}}


def _save_atomic(state: dict) -> None:
    """Write via a temp file + os.replace so a crash mid-write can never
    leave a partially-written, corrupt store -- mirrors the exact pattern
    already established by migrate_platform_labels.py and pipeline_state.py."""
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=".seo_recommendation_memory_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def get_entry(page_path: str, field: str) -> "dict | None":
    try:
        return load_memory().get("entries", {}).get(page_path, {}).get(field)
    except Exception:
        log.warning("recommendation_memory.py: get_entry(%r, %r) failed", page_path, field, exc_info=True)
        return None


def consult_before_llm_call(page_path: str, field: str, *, current_value: "str | None",
                             primary_kw: "str | None", family: "str | None",
                             platform: "str | None") -> dict:
    """Returns {"should_call_llm": bool, "signal_hash": str, "reason": str,
    "cached_proposal": dict|None}. Never raises -- any internal failure
    defaults to should_call_llm=True (generate fresh), the same always-safe
    fallback recommend.py already has for every other failure mode."""
    signal_hash = compute_signal_hash(
        current_value=current_value, primary_kw=primary_kw, family=family, platform=platform,
    )
    try:
        entry = get_entry(page_path, field)
        if entry is None:
            return {"should_call_llm": True, "signal_hash": signal_hash,
                     "reason": "no_prior_entry", "cached_proposal": None}
        if entry.get("hash") != signal_hash:
            return {"should_call_llm": True, "signal_hash": signal_hash,
                     "reason": "signal_changed", "cached_proposal": None}
        outcome = entry.get("outcome")
        if outcome in _REUSE_OUTCOMES:
            return {"should_call_llm": False, "signal_hash": signal_hash,
                     "reason": f"cached_{outcome}", "cached_proposal": entry.get("proposal")}
        if outcome in _STUCK_OUTCOMES:
            return {"should_call_llm": False, "signal_hash": signal_hash,
                     "reason": f"stuck_{outcome}", "cached_proposal": None}
        # An outcome value this module doesn't recognize -- fail open to
        # regeneration rather than silently trusting an unknown state.
        return {"should_call_llm": True, "signal_hash": signal_hash,
                 "reason": "unknown_outcome", "cached_proposal": None}
    except Exception:
        log.warning("recommendation_memory.py: consult_before_llm_call(%r, %r) failed",
                    page_path, field, exc_info=True)
        return {"should_call_llm": True, "signal_hash": signal_hash,
                 "reason": "consult_error", "cached_proposal": None}


def record_result(page_path: str, field: str, signal_hash: str, proposal: dict,
                   *, outcome: str = "pending") -> bool:
    """Record a freshly-generated proposal for (page_path, field). Replaces
    any existing entry for that (page_path, field) outright -- a new hash
    means the old entry's signal state no longer exists. Never raises."""
    try:
        state = load_memory()
        now = datetime.now(timezone.utc).isoformat()
        page_entries = state.setdefault("entries", {}).setdefault(page_path, {})
        page_entries[field] = {
            "hash": signal_hash,
            "outcome": outcome,
            "proposal": proposal,
            "recorded_at": now,
            "updated_at": now,
        }
        _save_atomic(state)
        # Registered in SEO-STATE-MANIFEST's pipeline_state.json index, per
        # this module's own acceptance criteria; record_stage_write() is
        # itself non-fatal, so a registration failure here can never block
        # the real store write above, which has already succeeded. Synced
        # to this module's OWN repo root first -- otherwise a test that
        # only calls this module's configure() would silently leak a
        # registration write into the real, shared pipeline_state.json,
        # the same test-isolation hazard SEO-CHANGE-BUDGET-GUARD already
        # found and fixed for change_budget.py/apply.py.
        pipeline_state.configure(repo_root=REPO_ROOT)
        pipeline_state.record_stage_write("recommendation_memory", path=_STORE_RELPATH)
        return True
    except Exception:
        log.warning("recommendation_memory.py: record_result(%r, %r) failed", page_path, field, exc_info=True)
        return False


def record_outcome(page_path: str, field: str, outcome: str) -> bool:
    """Write-back hook: update an EXISTING entry's outcome (S-116's real
    approve/reject verdict, or apply.py's real applied verdict). Never
    fabricates an entry, and never overrides what was decided -- it only
    records it. Not called from anywhere in this repo yet (see module
    docstring); exposed for a future card to wire into apply.py/safety.py."""
    try:
        state = load_memory()
        page_entries = state.get("entries", {}).get(page_path)
        if not page_entries or field not in page_entries:
            log.warning("recommendation_memory.py: record_outcome(%r, %r) -- no existing entry to update",
                        page_path, field)
            return False
        page_entries[field]["outcome"] = outcome
        page_entries[field]["updated_at"] = datetime.now(timezone.utc).isoformat()
        _save_atomic(state)
        return True
    except Exception:
        log.warning("recommendation_memory.py: record_outcome(%r, %r) failed", page_path, field, exc_info=True)
        return False
