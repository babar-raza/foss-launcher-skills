"""vector_store.py — staleness detection for gap-index vector profiles (TC-VEC-03, RC2).

Reads the ACTIVE profile's manifest.json (written by embed_api_index(), see
scripts/pipeline/commands/knowledge/embed.py) and compares its recorded
source_hash against a fresh hash of the live api_surface.json, so a reader
can tell whether the currently-active profile still describes the knowledge
that is actually on disk -- distinct from "vectors exist at all". Prior to
this module, source_hash was write-only: computed and stored in every
manifest.json but never read back by anything (confirmed by direct source
read of tier2_verify(), the only consumer of the active profile).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

_DEFAULT_KNOWLEDGE_ROOT = Path(__file__).resolve().parents[3] / "knowledge"
_knowledge_root = _DEFAULT_KNOWLEDGE_ROOT


def configure(*, knowledge_root: "Path | str | None" = None) -> None:
    """Override external boundaries for tests; call without arguments to reset."""
    global _knowledge_root
    _knowledge_root = (
        Path(knowledge_root) if knowledge_root is not None else _DEFAULT_KNOWLEDGE_ROOT
    )


class VectorStatus:
    CURRENT = "current"
    STALE = "stale"
    MISSING = "missing"


def vector_status(family: str, platform: str) -> str:
    """One of VectorStatus.{CURRENT,STALE,MISSING}.

    MISSING and STALE are deliberately distinct so a caller never conflates
    "no vectors were ever generated for this product" with "vectors exist but
    the knowledge has moved on since they were generated."
    """
    api_path = _knowledge_root / family / platform / "merged" / "api_surface.json"
    active_path = _knowledge_root / "_vectors" / family / platform / "active.json"
    if not api_path.exists() or not active_path.exists():
        return VectorStatus.MISSING

    try:
        active = json.loads(active_path.read_text(encoding="utf-8"))
        profile_dir = (
            _knowledge_root / "_vectors" / family / platform / "profiles" / active["profile_id"]
        )
        manifest = json.loads((profile_dir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, KeyError, json.JSONDecodeError):
        return VectorStatus.MISSING

    recorded_hash = manifest.get("source_hash")
    if not recorded_hash:
        return VectorStatus.MISSING

    live_hash = hashlib.sha256(api_path.read_bytes()).hexdigest()
    return VectorStatus.CURRENT if live_hash == recorded_hash else VectorStatus.STALE


def vectors_are_current(family: str, platform: str) -> bool:
    """True only when an active profile exists AND its source_hash matches the
    live api_surface.json. Both "stale" and "missing" return False here --
    callers that need to distinguish those two cases should use
    vector_status() directly instead of this convenience wrapper."""
    return vector_status(family, platform) == VectorStatus.CURRENT
