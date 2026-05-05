"""Shared claim index for semantic matching against knowledge claims.

Provides a TF-IDF claim index that prose_claim_binding and prose_grounding
evaluators use to match prose sentences against claims.json entries.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Knowledge root resolution — use destination convention
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent          # evaluators/
_SCRIPTS = _HERE.parent.parent.parent            # scripts/

# Ensure scripts/ is importable for embed and config_loader
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

try:
    from config_loader import resolve_knowledge_root as _resolve_knowledge_root
    KNOWLEDGE_ROOT = _resolve_knowledge_root()
except Exception:
    KNOWLEDGE_ROOT = Path("knowledge")

# ---------------------------------------------------------------------------
# TF-IDF semantic matching — imported from embed.py
# ---------------------------------------------------------------------------
try:
    from embed import (
        tokenize as _tfidf_tokenize,
        compute_idf as _compute_idf,
        compute_tfidf_vector as _tfidf_vector,
        cosine_similarity as _cosine_similarity,
    )
    TFIDF_AVAILABLE = True
except ImportError:
    TFIDF_AVAILABLE = False

    def _tfidf_tokenize(text):  # type: ignore[misc]
        return []

    def _compute_idf(documents):  # type: ignore[misc]
        return {}

    def _tfidf_vector(tokens, idf):  # type: ignore[misc]
        return {}

    def _cosine_similarity(v1, v2):  # type: ignore[misc]
        return 0.0


# Module-level cache: (family, platform) -> ClaimIndex
_CLAIM_INDEX_CACHE: dict[tuple[str, str], "ClaimIndex"] = {}


def clear_claim_cache() -> None:
    """Clear the claim index cache (for test isolation)."""
    _CLAIM_INDEX_CACHE.clear()


def get_claim_index(family: str, platform: str) -> "ClaimIndex":
    """Lazily build and cache a ClaimIndex per (family, platform)."""
    key = (family, platform)
    if key not in _CLAIM_INDEX_CACHE:
        claims = load_claims(family, platform)
        _CLAIM_INDEX_CACHE[key] = ClaimIndex(claims)
    return _CLAIM_INDEX_CACHE[key]


class ClaimIndex:
    """Pre-computed TF-IDF index over knowledge claims for semantic matching."""

    def __init__(self, claims: list[dict]):
        self._texts: list[str] = []
        self._token_lists: list[list[str]] = []

        for c in claims:
            text = c.get("text", "")
            if text:
                self._texts.append(text)
                self._token_lists.append(_tfidf_tokenize(text))

        self._idf = _compute_idf(self._token_lists) if self._token_lists else {}
        self._vectors = [
            _tfidf_vector(toks, self._idf) for toks in self._token_lists
        ]

    @property
    def available(self) -> bool:
        return len(self._vectors) >= 1

    def best_similarity(self, text: str) -> float:
        """Return highest cosine similarity between text and any claim."""
        if not self._vectors:
            return 0.0
        tokens = _tfidf_tokenize(text)
        if not tokens:
            return 0.0
        vec = _tfidf_vector(tokens, self._idf)
        return max(_cosine_similarity(vec, cv) for cv in self._vectors)


def load_claims(family: str, platform: str) -> list[dict]:
    """Load claims.json for a product."""
    path = KNOWLEDGE_ROOT / family / platform / "merged" / "claims.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, KeyError):
        return []


def tokenize(text: str) -> set[str]:
    """Extract lowercase word tokens (for overlap matching)."""
    return set(re.findall(r"[a-z][a-z0-9_]+", text.lower()))
