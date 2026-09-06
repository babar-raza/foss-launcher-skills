"""
lib/example_verification/cache.py

CONTRACT: scripts/pipeline/lib/example_verification/cache.py
  purpose: ResultCache -- a per-(family, platform) on-disk cache of
           deterministic block-verification outcomes, keyed so a rerun over
           unchanged inputs is byte-identical by construction (same key ->
           same stored result), and so a runner improvement, a toolchain
           version change, or an upstream clone-head move each show up as an
           explicit `stale_reason`, never a silent hit against a
           now-invalid result.
  inputs:  sha256_norm (code_fences.py), canonical_lang, clone_head,
           toolchain_fp, runners_module_version
  outputs: CacheEntry / ResultCache.get() / ResultCache.put() / stale_reason()
  owner_domain: content-quality

Only deterministic outcomes are ever cached (see
result.DETERMINISTIC_STATUSES_FOR_CACHE / DETERMINISTIC_REASONS_FOR_CACHE):
never TIMEOUT/SLOW, ACQUIRE-*, TOOLCHAIN-/GRAMMAR-UNAVAILABLE,
NO-CLONE-CACHE, BUDGET-EXHAUSTED -- caching any of those would let a
transient, machine- or moment-dependent condition silently outlive the
condition that produced it.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[4]
_RUNS_BASE = _REPO_ROOT / "runs" / ".example_verification"


def cache_key(
    sha256_norm: str, canonical_lang: str, clone_head: str, toolchain_fp: str,
    runners_module_version: str,
) -> str:
    """`max_tier` is deliberately NOT part of the key -- see ResultCache.get()
    for how a stored entry answers a request for a different tier than the
    one it was originally computed at."""
    raw = f"1|{sha256_norm}|{canonical_lang}|{clone_head}|{toolchain_fp}|{runners_module_version}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class CacheEntry:
    status: str
    proof_tier: int
    reason: str | None = None
    detail: str = ""
    clone_head: str = ""
    toolchain_version: str = ""
    runners_module_version: str = ""
    code_sha256: str = ""

    def is_deterministic_failure(self) -> bool:
        from . import result as result_mod
        return self.status == "BLOCKED-WITH-REASON" and self.reason in result_mod.DETERMINISTIC_REASONS_FOR_CACHE

    def is_pass(self) -> bool:
        return self.status == "PASS"


def stale_reason(
    entry: CacheEntry, *, clone_head: str | None = None, toolchain_version: str | None = None,
    runners_module_version: str | None = None, current_code_sha256: str | None = None,
) -> str | None:
    """Name the first component whose current value differs from what's
    recorded on `entry`, in this fixed priority order: clone_head ->
    toolchain_version -> runners_version -> snippet_edited. Returns None if
    every supplied component matches (the entry is fresh). Any component
    the caller omits (passes None) is not checked -- lets both cache.py's
    own hit/miss check (which only ever knows the first three) and a future
    snippet-index consumer (which also has current_code_sha256) share one
    function without cache.py needing to know about snippets."""
    if clone_head is not None and entry.clone_head and clone_head != entry.clone_head:
        return "clone_head"
    if toolchain_version is not None and entry.toolchain_version and toolchain_version != entry.toolchain_version:
        return "toolchain_version"
    if runners_module_version is not None and entry.runners_module_version and runners_module_version != entry.runners_module_version:
        return "runners_version"
    if current_code_sha256 is not None and entry.code_sha256 and current_code_sha256 != entry.code_sha256:
        return "snippet_edited"
    return None


class ResultCache:
    """One JSON file per (family, platform): `runs/.example_verification/
    {family}_{platform}/cache.json`, mapping cache_key() -> CacheEntry
    (as a dict). Never in `content/` or `knowledge/` -- `runs/` is this
    repo's established disposable-scratch location for run artifacts."""

    def __init__(self, family: str, platform: str, root: Path | None = None) -> None:
        base = root if root is not None else _RUNS_BASE
        self._path = base / f"{family}_{platform}" / "cache.json"
        self._data: dict[str, dict[str, Any]] | None = None

    @property
    def path(self) -> Path:
        return self._path

    def _load(self) -> dict[str, dict[str, Any]]:
        if self._data is None:
            if self._path.is_file():
                try:
                    self._data = json.loads(self._path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    self._data = {}
            else:
                self._data = {}
        return self._data

    def get(self, key: str, want_tier: int) -> CacheEntry | None:
        """A stored entry is a hit if it proves at least `want_tier`
        (`entry.proof_tier >= want_tier`), OR if it's a deterministic
        failure found at any tier -- a real SYNTAX-ERROR found at tier 1
        still answers a tier-2 request, since compiling can't un-fail a
        block whose syntax is already known to be broken."""
        raw = self._load().get(key)
        if raw is None:
            return None
        entry = CacheEntry(**raw)
        if entry.proof_tier >= want_tier:
            return entry
        if entry.is_deterministic_failure():
            return entry
        return None

    def put(self, key: str, entry: CacheEntry) -> bool:
        """Store `entry` under `key` iff it's a cacheable (deterministic)
        outcome. Returns True if stored, False if silently skipped (not
        an error -- a non-deterministic outcome is simply never persisted,
        per this module's own contract)."""
        if not (entry.is_pass() or entry.is_deterministic_failure()):
            return False
        data = self._load()
        data[key] = asdict(entry)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(data, indent=2, sort_keys=True), encoding="utf-8",
        )
        return True
