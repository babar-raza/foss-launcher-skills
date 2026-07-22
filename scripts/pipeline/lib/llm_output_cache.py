"""llm_output_cache.py — content-hash-keyed LLM output cache (HARDEN-A4).

CONTRACT: scripts/pipeline/lib/llm_output_cache.py
  purpose: Make LLM-backed generation rerun-consistent where the pipeline's two
           highest-impact call sites had none: S-37 knowledge-enrich
           (enrich.py::_llm_call) and refresh-time prose rewrite
           (body_refresh.py::_paragraph_rewrite). Generalizes the two proven
           in-repo patterns: generate_product_backlink_copy.py's input-hash
           cache keys and tier3_cache.py's invalidate-on-source-change model.
           A cache hit returns the stored output byte-identically with zero
           LLM calls; a miss calls the LLM and stores the first success.
  key design: the cache key hashes the FULLY RENDERED prompts (system + user)
           plus caller-supplied identity parts (family/platform/source sha/
           schema version). Because the rendered prompt embeds the actual
           source-derived content (API facts, section text, claims), hashing it
           invalidates the entry automatically when — and only when — the
           underlying input actually changed. No separate batch bookkeeping.
  drift detection: each namespace records the last model identity that produced
           a fresh entry (_model_marker.json). A fresh call served by a
           different provider/model logs MODEL_DRIFT_DETECTED — a served-model
           upgrade cannot silently mix outputs without a trace.
  escape hatch: enabled=False (CLI --no-llm-cache / force_llm_regen) bypasses
           reads but still records fresh outputs; bypass is logged loudly by
           callers, never a silent default. ASPOSE_NO_LLM_CACHE=1 env disables
           reads globally (operator diagnostics).
  storage: reports/{family}/{platform}/llm_cache/{namespace}/{key[:2]}/{key}.json
           (gitignored, local — same durability class as tier3_cache).
  concurrency: writes are atomic (tmp+replace). Two processes racing on the
           same key both compute valid outputs; last write wins harmlessly.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

log = logging.getLogger("llm_output_cache")

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ENV_DISABLE = "ASPOSE_NO_LLM_CACHE"


def sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def build_cache_key(parts: list[str]) -> str:
    """Deterministic key from ordered string parts (hash long parts first)."""
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class LLMOutputCache:
    """Per-(family, platform, namespace) LLM output cache."""

    def __init__(
        self,
        family: str,
        platform: str,
        namespace: str,
        *,
        reports_root: Path | str | None = None,
        enabled: bool = True,
    ):
        root = Path(reports_root) if reports_root else _REPO_ROOT / "reports"
        self.dir = root / family / platform / "llm_cache" / namespace
        self.read_enabled = enabled and os.environ.get(_ENV_DISABLE, "") != "1"
        self.hits = 0
        self.misses = 0

    # ── entries ──────────────────────────────────────────────────────────

    def _entry_path(self, key: str) -> Path:
        return self.dir / key[:2] / f"{key}.json"

    def load(self, key: str) -> dict | None:
        """Return the cached entry for key, or None (miss/disabled/corrupt)."""
        if not self.read_enabled:
            return None
        try:
            entry = json.loads(self._entry_path(key).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.misses += 1
            return None
        if not isinstance(entry, dict) or "output" not in entry:
            self.misses += 1
            return None
        self.hits += 1
        return entry

    def save(self, key: str, output, model_used: str, extra: dict | None = None) -> None:
        """Store a fresh successful output (always — even when reads are bypassed,
        so a forced-fresh run refreshes the cache for future runs).

        R3: a failed cache WRITE must never outrank a successful generation —
        any I/O or serialization error here is logged and swallowed. (Windows
        os.replace can raise PermissionError if a concurrent reader holds the
        entry open; disk-full raises OSError; unserializable output TypeError.)
        """
        entry = {
            "output": output,
            "model_used": model_used,
            "created_at": _now_iso(),
        }
        if extra:
            entry.update(extra)
        try:
            path = self._entry_path(key)
            path.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile("w", encoding="utf-8", delete=False,
                                    dir=path.parent, suffix=".tmp") as handle:
                json.dump(entry, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
                temp_path = Path(handle.name)
            temp_path.replace(path)
        except (OSError, TypeError, ValueError) as exc:
            log.warning("LLM cache write failed (non-fatal, output still used): %s", exc)
            return
        self.note_model(model_used)

    # ── model-drift marker ───────────────────────────────────────────────

    def note_model(self, model_used: str) -> None:
        """Record the model identity behind fresh entries; log drift loudly.
        Marker I/O failures are non-fatal (R3) — drift detection is advisory."""
        if not model_used:
            return
        marker = self.dir / "_model_marker.json"
        previous = None
        try:
            previous = json.loads(marker.read_text(encoding="utf-8")).get("model_used")
        except (OSError, json.JSONDecodeError):
            pass
        if previous and previous != model_used:
            log.warning(
                "MODEL_DRIFT_DETECTED: fresh LLM outputs in %s now come from %r "
                "(previously %r) — cached and new entries mix model generations. "
                "Consider --no-llm-cache to regenerate coherently.",
                self.dir, model_used, previous,
            )
        if previous != model_used:
            try:
                marker.parent.mkdir(parents=True, exist_ok=True)
                with NamedTemporaryFile("w", encoding="utf-8", delete=False,
                                        dir=marker.parent, suffix=".tmp") as handle:
                    json.dump({"model_used": model_used, "updated_at": _now_iso()}, handle)
                    handle.write("\n")
                    temp_path = Path(handle.name)
                temp_path.replace(marker)
            except (OSError, TypeError, ValueError) as exc:
                log.warning("LLM cache model-marker write failed (non-fatal): %s", exc)
