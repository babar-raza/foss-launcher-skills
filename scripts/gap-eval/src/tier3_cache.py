"""Tier 3 LLM result cache for S-43 gap-eval.

Makes Tier 3 (LLM) findings idempotent for unchanged files across reruns.
A cache hit returns the same finding set from the prior run without calling the LLM.

Storage: inside the existing state file under a top-level "tier3_cache" key.
Backwards-compatible — load_state() returns {} for missing keys.

Cache key: SHA-256 of raw .md file bytes (first 16 hex chars).
Content-hash is used (not mtime) because mtime is unreliable on Windows
when git operations or antivirus touch files without changing content.

Two-axis validity check (both must match for a cache hit):
  1. profile_sha: SHA-256 of profile YAML bytes (first 8 hex chars).
     If profile changes between runs, cached Tier 3 results may be invalid
     because Stage 1 override logic changes which claims are escalated.
  2. clone_sha: clone cache git HEAD SHA.
     If the upstream repo was updated, all Tier 3 results are stale
     because the source context used in LLM prompts has changed.

Path normalization: all paths stored as POSIX-normalized strings
(str(Path(p).as_posix())) to prevent Windows/Unix path separator mismatch
when state files are shared across platforms.

Read mode: SHA-256 is computed from content read with encoding="utf-8",
errors="replace" — the same mode used by run_gap_eval() — to guarantee
the same hash regardless of encoding errors in the file.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)


def clear_cache(family: str, platform: str, state_dir: Path | None = None) -> bool:
    """Clear all Tier 3 cache entries for family/platform from the state file.

    The Tier 3 cache is embedded in the state file at the "tier3_cache" key.
    This function zeroes that key without deleting the rest of the state.
    Call this BEFORE reset_state() if you want to log whether entries existed.

    Returns True if the state file existed and had cache entries (cleared).
    Returns False if no state file existed or the cache was already empty.
    Safe to call when no state file exists.
    """
    from state import _state_path  # type: ignore  # noqa: PLC0415
    path = _state_path(family, platform, state_dir)
    if not path.exists():
        log.debug("clear_cache: no state file at %s — nothing to clear", path)
        return False
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("clear_cache: cannot read state file %s: %s — skipping cache clear", path, exc)
        return False
    existing = state.get("tier3_cache") or {}
    if not existing:
        log.debug("clear_cache: tier3_cache already empty for %s/%s", family, platform)
        return False
    state["tier3_cache"] = {}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(path)
    log.debug("clear_cache: cleared %d tier3 cache entries for %s/%s", len(existing), family, platform)
    return True


class Tier3Cache:
    """Per-run cache for Tier 3 LLM findings, keyed by file content hash.

    Usage in run_gap_eval():
        _cache = Tier3Cache(prior_state, _profile_path(family, platform), clone_sha)

        # Before processing claims for a file:
        hit, cached_findings = _cache.get(fpath, content)
        if hit:
            raw_findings.extend(cached_findings)
            # skip Tier 3 for all claims in this file

        # After processing claims for a file (cache miss path):
        _cache.put(fpath, content, file_t3_findings)

        # Before save_state():
        new_state["tier3_cache"] = _cache.export()
    """

    def __init__(self, state: dict, profile_path: Path, clone_sha: str) -> None:
        """Initialise cache from prior state.

        Args:
            state: Dict returned by load_state() — may or may not contain "tier3_cache".
            profile_path: Path to the profile YAML for this family/platform.
            clone_sha: Current HEAD SHA of the clone cache git repo.
        """
        self._store: dict[str, dict] = dict(state.get("tier3_cache") or {})
        self._profile_path = profile_path
        self._clone_sha = clone_sha
        self._profile_sha: str | None = None  # computed lazily, cached after first call
        self._dirty: bool = False  # True if any put() has been called

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def get(self, file_path: Path, content: str) -> tuple[bool, list[dict]]:
        """Look up Tier 3 findings for a file by content hash.

        Returns:
            (True, findings)  — cache hit; findings is the stored list (may be []).
            (False, [])       — cache miss; caller must run Tier 3 and call put().

        Cache-sourced findings are annotated with "tier3_cache_hit": True.
        """
        key = self.compute_file_hash(content)
        entry = self._store.get(key)
        if not entry:
            return False, []

        # Validate profile axis
        current_profile_sha = self._get_profile_sha()
        if entry.get("profile_sha") != current_profile_sha:
            log.debug(
                "Tier3Cache: profile SHA changed (%s → %s) — invalidating cache for %s",
                entry.get("profile_sha"), current_profile_sha, file_path.name,
            )
            return False, []

        # Validate clone axis
        if entry.get("clone_sha") != self._clone_sha:
            log.debug(
                "Tier3Cache: clone SHA changed — invalidating cache for %s", file_path.name
            )
            return False, []

        findings = entry.get("findings", [])
        # Annotate each cached finding so callers can distinguish cache vs. fresh LLM
        annotated = [dict(f, tier3_cache_hit=True) for f in findings]
        log.debug(
            "Tier3Cache: HIT for %s — returning %d cached findings", file_path.name, len(annotated)
        )
        return True, annotated

    def put(self, file_path: Path, content: str, findings: list[dict]) -> None:
        """Store Tier 3 findings for a file after a fresh LLM evaluation.

        Args:
            file_path: Path to the evaluated .md file.
            content:   Full text of the file (same string that was read for evaluation).
            findings:  List of Tier 3 finding dicts for this file (may be empty list
                       if LLM confirmed all claims accurate).
        """
        key = self.compute_file_hash(content)
        self._store[key] = {
            "file_path": str(Path(file_path).as_posix()),
            "cached_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "profile_sha": self._get_profile_sha(),
            "clone_sha": self._clone_sha,
            "findings": findings,
        }
        self._dirty = True
        log.debug(
            "Tier3Cache: stored %d finding(s) for %s (key=%s)",
            len(findings), file_path.name, key,
        )

    def export(self) -> dict:
        """Return the current tier3_cache dict for storage in the state file.

        Always returns the full store (including entries that were hits and
        therefore not modified). Callers should write this into new_state before
        calling save_state().
        """
        return dict(self._store)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def compute_file_hash(self, content: str) -> str:
        """SHA-256 of file content bytes (UTF-8), first 16 hex chars.

        Uses the same encoding as run_gap_eval: encode to bytes with
        errors="replace" to handle files with invalid UTF-8 sequences
        identically to how they are read for evaluation.
        """
        raw = content.encode("utf-8", errors="replace")
        return hashlib.sha256(raw).hexdigest()[:16]

    def _get_profile_sha(self) -> str:
        """SHA-256 of profile YAML bytes, first 8 hex chars. Computed once and cached."""
        if self._profile_sha is not None:
            return self._profile_sha
        try:
            raw = self._profile_path.read_bytes()
            self._profile_sha = hashlib.sha256(raw).hexdigest()[:8]
        except OSError:
            # Profile missing — use a fixed sentinel so cache entries from
            # prior runs (when profile existed) will be invalidated.
            self._profile_sha = "no-profile"
        return self._profile_sha
