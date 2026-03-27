"""Prose truth evaluator — matches factual claims against knowledge."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator

KNOWLEDGE_ROOT = Path("knowledge")

# Sentence patterns that indicate factual API claims
_API_CLAIM_RE = re.compile(
    r"`(\w+(?:\.\w+)*)`\s+"
    r"(?:provides?|has|supports?|exposes?|returns?|implements?|contains?|inherits?|extends?)",
    re.IGNORECASE,
)

# Format claim patterns
_FORMAT_CLAIM_RE = re.compile(
    r"(?:supports?|import|export|convert|load|save|read|write)\w*\s+"
    r"(?:the\s+)?(?:to\s+|from\s+)?(\w{2,6})\s+(?:format|file|document)",
    re.IGNORECASE,
)

# Strong wording indicators
_STRONG_WORDS = re.compile(
    r"\b(?:always|never|all|every|none|only|must|guaranteed|ensures?|"
    r"fully|completely|perfectly|exactly|precisely)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# TF-IDF semantic matching — imported from embed.py (single source of truth)
# ---------------------------------------------------------------------------

try:
    from scripts.pipeline.embed import (
        tokenize as _tfidf_tokenize,
        compute_idf as _compute_idf,
        compute_tfidf_vector as _tfidf_vector,
        cosine_similarity as _cosine_similarity,
    )
    _TFIDF_AVAILABLE = True
except ImportError:
    _TFIDF_AVAILABLE = False

    def _tfidf_tokenize(text):  # type: ignore[misc]
        return []

    def _compute_idf(documents):  # type: ignore[misc]
        return {}

    def _tfidf_vector(tokens, idf):  # type: ignore[misc]
        return {}

    def _cosine_similarity(v1, v2):  # type: ignore[misc]
        return 0.0


# Module-level cache: (family, platform) → _ClaimIndex
_CLAIM_INDEX_CACHE: dict[tuple[str, str], "_ClaimIndex"] = {}


def clear_claim_cache() -> None:
    """Clear the claim index cache (for test isolation)."""
    _CLAIM_INDEX_CACHE.clear()


def _get_claim_index(family: str, platform: str) -> "_ClaimIndex":
    """Lazily build and cache a _ClaimIndex per (family, platform)."""
    key = (family, platform)
    if key not in _CLAIM_INDEX_CACHE:
        claims = _load_claims(family, platform)
        _CLAIM_INDEX_CACHE[key] = _ClaimIndex(claims)
    return _CLAIM_INDEX_CACHE[key]


class _ClaimIndex:
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_claims(family: str, platform: str) -> list[dict]:
    """Load claims.json for a product."""
    path = KNOWLEDGE_ROOT / family / platform / "merged" / "claims.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, KeyError):
        return []


def _load_formats(family: str, platform: str) -> list[dict]:
    """Load formats.json for a product."""
    path = KNOWLEDGE_ROOT / family / platform / "merged" / "formats.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, KeyError):
        return []


def _tokenize(text: str) -> set[str]:
    """Extract lowercase word tokens."""
    return set(re.findall(r"[a-z][a-z0-9_]+", text.lower()))


class ProseTruthEvaluator(BaseEvaluator):
    """Evaluates factual prose claims against knowledge artifacts.

    Extracts API claims and format claims from prose, then verifies:
    - API claims match entries in claims.json (token overlap)
    - Format claims match entries in formats.json
    - Strong wording is backed by evidence (token overlap + TF-IDF fallback)
    """

    name = "prose_truth"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        if not page.family or not page.platform:
            return []

        claims = _load_claims(page.family, page.platform)
        formats = _load_formats(page.family, page.platform)

        if not claims and not formats:
            return []

        findings: list[Finding] = []

        # --- API claim verification against knowledge model ---
        has_knowledge = hasattr(knowledge, "classes") and knowledge is not None
        if has_knowledge and knowledge.available:
            for line_no, line_text in page.prose_lines:
                for m in _API_CLAIM_RE.finditer(line_text):
                    api_ref = m.group(1)  # e.g. "Scene.open" or "Scene"
                    parts = api_ref.split(".")
                    cls_name = parts[0]
                    if cls_name not in knowledge.classes:
                        continue  # Not a known class reference; skip
                    if len(parts) >= 2:
                        member = parts[1]
                        if not knowledge.has_method(cls_name, member) and \
                           not knowledge.has_property(cls_name, member):
                            findings.append(Finding(
                                level="WARN",
                                category="PT",
                                filepath=str(page.filepath),
                                line_no=line_no,
                                message=f"Prose claims `{cls_name}` has `{member}` but not found in API surface",
                                suggestion=f"Verify `{cls_name}.{member}` exists or fix the reference",
                                evaluator=self.name,
                            ))

        # Build claim token index for fuzzy matching
        claim_tokens = [(c.get("text", ""), _tokenize(c.get("text", "")))
                        for c in claims if c.get("text")]

        # Build TF-IDF claim index for semantic matching (secondary tier, cached)
        claim_index = _get_claim_index(page.family, page.platform)

        # Build format lookup
        format_support: dict[str, str] = {}
        for fmt in formats:
            ext = (fmt.get("format") or fmt.get("ext") or "").lower()
            direction = (fmt.get("direction") or fmt.get("support") or "").lower()
            if ext:
                format_support[ext] = direction

        # Check format claims in prose
        for line_no, line_text in page.prose_lines:
            for m in _FORMAT_CLAIM_RE.finditer(line_text):
                claimed_format = m.group(1).lower()
                if claimed_format in format_support:
                    # Check direction consistency
                    direction = format_support[claimed_format]
                    text_lower = line_text.lower()
                    if "export" in text_lower and direction == "import":
                        findings.append(Finding(
                            level="FAIL",
                            category="PT",
                            filepath=str(page.filepath),
                            line_no=line_no,
                            message=f"Claims {claimed_format.upper()} export but knowledge shows import-only",
                            suggestion=f"Fix direction: {claimed_format.upper()} supports {direction}",
                            evaluator=self.name,
                        ))
                    elif "import" in text_lower and direction == "export":
                        findings.append(Finding(
                            level="FAIL",
                            category="PT",
                            filepath=str(page.filepath),
                            line_no=line_no,
                            message=f"Claims {claimed_format.upper()} import but knowledge shows export-only",
                            suggestion=f"Fix direction: {claimed_format.upper()} supports {direction}",
                            evaluator=self.name,
                        ))

            # Flag strong wording without evidence backing
            if _STRONG_WORDS.search(line_text):
                line_tokens = _tokenize(line_text)
                best_overlap = 0.0
                for _, ct in claim_tokens:
                    if ct:
                        overlap = len(line_tokens & ct) / max(len(ct), 1)
                        best_overlap = max(best_overlap, overlap)

                if best_overlap < 0.3 and len(line_tokens) > 3:
                    # Secondary tier: TF-IDF semantic matching
                    # If cosine similarity is high enough, the claim is supported
                    if claim_index.available:
                        semantic_score = claim_index.best_similarity(line_text)
                        if semantic_score >= 0.4:
                            continue  # Supported by semantic similarity

                    findings.append(Finding(
                        level="INFO",
                        category="PT",
                        filepath=str(page.filepath),
                        line_no=line_no,
                        message="Strong wording with weak evidence backing",
                        suggestion="Qualify the claim or add supporting evidence",
                        evaluator=self.name,
                    ))

        return findings
