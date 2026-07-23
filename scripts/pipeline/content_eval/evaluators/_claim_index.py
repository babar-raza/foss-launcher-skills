"""Shared claim index for semantic matching against knowledge claims.

Factored out of prose_truth.py (H-10) so that both prose_truth and
prose_claim_binding evaluators can reuse the same TF-IDF claim index.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

KNOWLEDGE_ROOT = Path("knowledge")

# A markdown table row (Properties/Methods tables on reference pages, always
# generated verbatim from api_surface.json's own per-member `doc` field --
# see batch_reference.py). Its cell content is already verified by dedicated
# table-focused evaluators (member_validity.py, api_accuracy.py,
# code_block_api.py) against api_surface.json directly; scanning it again as
# free-standing declarative prose against claims.json is the wrong tool for
# the job and produces false positives (confirmed live: real property docs
# like "Deletes all tab stop positions." or "Returns true if the LineStyle is
# not None." trip the strong-wording/claim-binding checks on words that are
# accurate technical description, not marketing prose).
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")


def is_markdown_table_row(line_text: str) -> bool:
    """Return True if line_text is a markdown table row (starts and ends with |)."""
    return bool(_TABLE_ROW_RE.match(line_text))


_BACKTICK_SPAN_RE = re.compile(r"`[^`]*`")
_WORD_RE = re.compile(r"[A-Za-z]+")

# Below this many backtick-quoted spans, a line isn't a "listing" -- it's an
# ordinary sentence that happens to reference one or two identifiers.
_MIN_ENUMERATION_IDENTIFIERS = 3
# Above this many residual (non-backtick) words, there's enough surrounding
# prose that the line is making an assertion, not just introducing a list.
_MAX_ENUMERATION_RESIDUAL_WORDS = 6

# A claim verb appearing AFTER the last identifier means the list is the
# SUBJECT of an assertion ("`A`, `B`, `C` fully support advanced editing"),
# not a list introduced by connective glue ("Available methods include:
# `A`, `B`, `C`."). Only checked in the trailing text -- "include" itself is
# one of these verbs and legitimately appears BEFORE the list in the real
# generated sentences, so checking the whole line would defeat the recognizer.
# Found via independent review, 2026-07-23: a constructed line matching this
# shape was not present anywhere in the words/net corpus, but the recognizer
# should not rely on that remaining true forever.
_TRAILING_CLAIM_VERB_RE = re.compile(
    r"\b(?:support|supports|provide|provides|enable|enables|deliver|delivers|"
    r"offer|offers|allow|allows|implement|implements|expose|exposes|"
    r"ship|ships|come|comes)\b",
    re.IGNORECASE,
)


def is_identifier_enumeration(line_text: str) -> bool:
    """Return True if line_text is a structural listing of backtick-quoted
    identifiers (e.g. "Available methods include: `Add`, `Clear`, ... .") with
    only a few words of fixed connective glue outside the backticks, and no
    claim verb describing what the listed identifiers do AFTER the list.

    batch_reference.py generates these directly from api_surface.json's own
    method/property name lists (see its "LC-10 FIX" block, whose comment
    states plainly: "Only method/property/member names from api_surface.json
    are used -- no hallucinated claims"). The listed names are the same data
    already verified via the page's Methods/Properties tables; matching this
    sentence against claims.json prose is the wrong tool -- claims.json has
    no reason to contain a claim that just restates a name list, so a
    correctly-generated page can never win here even though nothing is wrong.
    """
    spans = list(_BACKTICK_SPAN_RE.finditer(line_text))
    if len(spans) < _MIN_ENUMERATION_IDENTIFIERS:
        return False
    residual = _BACKTICK_SPAN_RE.sub(" ", line_text)
    residual_words = _WORD_RE.findall(residual)
    if len(residual_words) > _MAX_ENUMERATION_RESIDUAL_WORDS:
        return False
    trailing_text = line_text[spans[-1].end():]
    return not _TRAILING_CLAIM_VERB_RE.search(trailing_text)


# ---------------------------------------------------------------------------
# TF-IDF semantic matching — imported from embed.py (single source of truth)
# ---------------------------------------------------------------------------

try:
    from commands.knowledge.embed import (
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


# Module-level cache: (family, platform) → ClaimIndex
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


# Claims shorter than this contribute too little context for the overlap
# ratio (len(intersection) / len(claim_tokens)) to be a meaningful grounding
# signal: a short claim can cross a 0.3 threshold from a couple of shared
# generic words (e.g. "for", "with", "provides", "method") purely by chance,
# regardless of whether the claim has anything to do with the line being
# checked. Confirmed live: a words/net claim "ResourceLoadingArgs: Provides
# data for the ResourceLoading method." (7 tokens) scored 0.43 overlap
# against an unrelated "This interface provides 1 method for working with X
# objects in .NET programs." sentence on nothing but shared filler words.
# 8 is chosen to exclude that case and the common 5-token "X.Y property of
# type Z" claim shape while still admitting genuinely descriptive claims
# ("Class X defined in Y.cs" claims run ~9 tokens). This is a coarse,
# length-based filter, not a semantic one -- it reduces but does not
# eliminate ratio-tier noise (a sufficiently long claim full of generic
# connector words could still collide). TF-IDF (IDF-weighted, so common
# words are naturally down-weighted) is the tier that should be trusted for
# precision; the ratio tier remains a cheap first pass.
MIN_OVERLAP_CLAIM_TOKENS = 8


def best_token_overlap(line_tokens: set[str], claim_token_sets: list[set[str]]) -> float:
    """Highest token-overlap ratio between line_tokens and any claim long
    enough for the ratio to be a meaningful signal (see MIN_OVERLAP_CLAIM_TOKENS)."""
    best = 0.0
    for ct in claim_token_sets:
        if len(ct) < MIN_OVERLAP_CLAIM_TOKENS:
            continue
        overlap = len(line_tokens & ct) / len(ct)
        if overlap > best:
            best = overlap
    return best


def _load_class_doc_claims(family: str, platform: str) -> list[dict]:
    """Synthesize claims from class/interface-level docstrings in api_surface.json.

    api_surface.json's per-class `doc` field is a verified, source-derived fact
    (the real docstring), but claims.json never captures it -- claims.json only
    records mechanical signature facts ("Class X defined in Y.cs", "X.Y property
    of type Z"), not descriptive prose. Reference pages' Overview sections quote
    or paraphrase these docstrings directly (see batch_reference.py page
    generation), so without this, prose-grounding evaluators have no claim to
    trace that text to -- match success then depends on incidental token overlap
    with unrelated signature claims, which is unreliable (interfaces with few
    methods, or classes whose docstring shares little vocabulary with their own
    method/property names, fail to match purely by chance).
    """
    path = KNOWLEDGE_ROOT / family / platform / "merged" / "api_surface.json"
    if not path.exists():
        return []
    try:
        classes = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, KeyError):
        return []
    if not isinstance(classes, list):
        return []
    claims: list[dict] = []
    for c in classes:
        doc = c.get("doc")
        name = c.get("name")
        if not doc or not name:
            continue
        claims.append({
            "claim_id": f"SYN-classdoc-{name}",
            "kind": "class_doc",
            "text": f"{name}: {doc}",
            "claim_source": "api_surface",
            "provenance": "api_surface",
        })
    return claims


def load_claims(family: str, platform: str) -> list[dict]:
    """Load claims.json for a product, augmented with class/interface docstring claims."""
    path = KNOWLEDGE_ROOT / family / platform / "merged" / "claims.json"
    claims: list[dict] = []
    if path.exists():
        try:
            claims = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, KeyError):
            claims = []
    return list(claims) + _load_class_doc_claims(family, platform)


def tokenize(text: str) -> set[str]:
    """Extract lowercase word tokens."""
    return set(re.findall(r"[a-z][a-z0-9_]+", text.lower()))
