"""Topic-grounding evaluator — detects `type: topic` pages whose title/slug
noun has zero grounding in the reachable/public knowledge surface AND
carries no evidence backing.

CE-02 (plans/healing/2026-09-17-content-eval-hardening-gaps.md:182-311,
gap G-03): this is the check that would have caught the 4 fabricated-
capability KB stub pages retired in commit 820d2c7e8e -- each had a
title/slug noun (e.g. "onestore-format") with no real counterpart in the
product's reachable knowledge surface, and empty evidence.claims/apis.

Design notes (full evidence trail in this taskcard's own "Pre-implementation
design note", plans/healing/2026-09-17-content-eval-hardening-gaps.md):

  - Grounding is checked ONLY against the reachable/public surface, not raw
    claims.json/api_surface.json text. A naive check against raw text
    false-negatives on this evaluator's own motivating fixture:
    knowledge/note/python/merged/claims.json has 46+ claims mentioning
    OneStore, and a real `parse_onestore_file` API entry -- but every one
    traces back to OneStoreFile/OneStoreObject, which api_surface.json
    marks "reachable": false (internal `_internal/onestore/` parser, not
    user-facing). See _reachability.py.

  - Noun-vs-candidate matching requires the FULL noun word-set to be a
    subset of one candidate's word-set (after camelCase/snake_case
    splitting) -- never substring containment and never single-word
    overlap. Substring containment would let "onestore" (from noun
    "onestore-format") match unreachable "OneStoreFile" even after
    splitting; single-word overlap would let noun "onestore-format" match
    REACHABLE "FileFormat"/"SaveFormat" on the word "format" alone (both
    real, reachable classes in the same knowledge model) -- a second,
    independently confirmed false-negative risk. Requiring full coverage
    closes both.

Category: TG (Topic Grounding).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator, _claim_index, _reachability

_DEFAULT_KNOWLEDGE_ROOT = Path(__file__).resolve().parents[4] / "knowledge"
KNOWLEDGE_ROOT = _DEFAULT_KNOWLEDGE_ROOT


def configure(*, knowledge_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing.

    Also re-points _claim_index.KNOWLEDGE_ROOT -- a separate, bare relative
    "knowledge" constant (_claim_index.py, no configure() of its own) -- so
    load_claims() reads from the same fixture root this evaluator was
    configured with. Without this, a test that calls
    configure(knowledge_root=tmp_path) would still read the repo's real
    knowledge/ tree for the claims half of grounding.
    """
    global KNOWLEDGE_ROOT
    KNOWLEDGE_ROOT = Path(knowledge_root) if knowledge_root is not None else _DEFAULT_KNOWLEDGE_ROOT
    _claim_index.KNOWLEDGE_ROOT = KNOWLEDGE_ROOT


# ---------------------------------------------------------------------------
# Slug-noun extraction -- reuses new-kb-howto's own convention (the real,
# tested implementation lives in site_planner.py's _validate_kb_slugs())
# rather than re-deriving a heuristic (taskcard Hard Rule). That function is
# a batch validator (raises/logs) outside this taskcard's allowed paths, so
# ST-198 delegates directly to its single shared implementation
# (split_kb_slug_verb_noun()) instead of maintaining its own copy of the
# verb vocabulary and extraction loop -- the prior verbatim-replica approach
# is exactly what let this copy drift out of sync with site_planner.py's own.
# A third, independently-maintained vocabulary still exists in
# scripts/ci/checks/check_kb_slug_quality.py (pre-existing, out of this
# module's scope, tracked separately -- see backlog F-2 / ST-198).
# ---------------------------------------------------------------------------

try:
    from commands.launch.site_planner import split_kb_slug_verb_noun
except ImportError:
    def split_kb_slug_verb_noun(slug: str, platform: str) -> tuple[str, str]:
        # Degraded fallback matching this module's pre-ST-198 ImportError
        # behavior: no vocabulary available, so no verb is ever recognised.
        if not slug.startswith("how-to-"):
            raise ValueError(f"not a how-to slug: {slug!r}")
        inner = slug[len("how-to-"):]
        if inner.endswith(f"-{platform}"):
            inner = inner[: -(len(platform) + 1)]
        return "", inner

# RC-W1-004 platform->language table. Deliberately a LOCAL, minimal copy --
# member_validity.py defines the identical table with the same rationale
# ("kept local and minimal to avoid coupling content_eval to the extraction
# package"); mirrored here rather than cross-imported from a sibling
# evaluator file for the same reason.
_PLATFORM_TO_LANGUAGE: dict[str, str] = {
    "net": "csharp", "dotnet": "csharp", "java": "java", "cpp": "cpp",
    "python": "python", "typescript": "typescript", "javascript": "javascript",
    "nodejs": "javascript", "go": "go", "rust": "rust",
}

_STOPWORDS = frozenset({"a", "an", "the", "to", "of", "in", "on", "for",
                         "and", "or", "with", "from", "into", "as"})

# Connector words that split a noun into independently-groundable segments,
# generalizing the extremely common "convert X to Y" KB slug shape (found
# live, portfolio dry run 2026-09-18: cells/python's
# how-to-convert-csv-to-json-python.md and email/cpp's
# how-to-convert-eml-to-msg-cpp.md both false-FAILed under whole-noun
# matching, even though CSV/JSON and EML/MSG are each independently real,
# reachable formats -- confirmed live via CSVLoadOptions/JsonSaveOptions and
# mapi_message.load_from_eml -- because no single class is ever named
# "CsvToJson" or "EmlToMsg"). Each side of a conversion claim must
# independently be real for the combined claim to be non-fabricated, but
# neither side needs to be named jointly with the other in one identifier.
# Deliberately narrow (connector-split only, not a general "any word
# anywhere" relaxation) so it does not reopen the FileFormat/SaveFormat
# single-word-overlap trap this evaluator was built to close in the first
# place -- see _noun_segments()'s docstring.
_CONNECTOR_WORDS = frozenset({"to", "from", "into"})

_NON_ALNUM_RE = re.compile(r"[^A-Za-z0-9]+")
_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")

_CLASS_DEFINED_RE = re.compile(r"^Class\s+([A-Za-z_]\w*)\s+defined\b")
_LEADING_MEMBER_RE = re.compile(r"^([A-Za-z_]\w*)\.")
_CLASSDOC_RE = re.compile(r"^([A-Za-z_]\w*):\s")

# Severity by subdomain -- FAIL for kb/blog per this taskcard's explicit Fix
# text ("blocking for kb/blog"), a deliberate deviation from
# capability_claim_check.py's own kb/blog->WARN mapping (documented in this
# taskcard's pre-implementation design note, not an oversight). docs/
# products get WARN -- `type: topic` is rarer there and less characterized.
_SEVERITY: dict[str, str] = {
    "kb": "FAIL",
    "blog": "FAIL",
    "docs": "WARN",
    "products": "WARN",
}

_API_CLAIM_KINDS = frozenset({"api", "api_method", "api_class", "class_doc"})


def _extract_topic_noun(slug: str, platform: str) -> "str | None":
    """Mirrors site_planner.py's _validate_kb_slugs() extraction loop
    exactly. Returns None for slugs that don't have the
    how-to-{verb}-...-{platform} shape (e.g. a `type: topic` FAQ page) --
    Step 0a's convention is only defined for how-to-* slugs; this evaluator
    does not invent a second heuristic for other shapes (Hard Rule)."""
    if not slug.startswith("how-to-"):
        return None
    _verb, noun = split_kb_slug_verb_noun(slug, platform)
    return noun or None


def _noun_words(noun: str) -> frozenset:
    return frozenset(w for w in noun.split("-") if w and w not in _STOPWORDS)


def _noun_segments(noun: str) -> list[frozenset]:
    """Split the noun into segments around connector words (to/from/into) so
    each side of a "convert X to Y" topic is graded independently -- see
    _CONNECTOR_WORDS' module-level comment for why. Falls back to the prior
    single-whole-noun behavior when there is no connector, or when
    connector-splitting would produce any EMPTY segment (e.g. a noun that
    starts or ends on a connector) -- an empty frozenset is a subset of
    everything, so a degenerate empty segment must never be allowed through
    to _grounded(), it would trivially "ground" any candidate."""
    words = [w for w in noun.split("-") if w]
    segments: list[list[str]] = [[]]
    for w in words:
        if w in _CONNECTOR_WORDS:
            segments.append([])
        else:
            segments[-1].append(w)
    groups = [frozenset(w for w in seg if w not in _STOPWORDS) for seg in segments]
    if len(groups) > 1 and all(groups):
        return groups
    whole = _noun_words(noun)
    return [whole] if whole else []


def _split_identifier(name: str) -> frozenset:
    """CompoundFile -> {compound,file}; parse_onestore_file ->
    {parse,onestore,file}; OneStoreFile -> {one,store,file}."""
    words: set[str] = set()
    for piece in _NON_ALNUM_RE.split(name):
        if not piece:
            continue
        for w in _CAMEL_BOUNDARY_RE.split(piece):
            if w:
                words.add(w.lower())
    return frozenset(words)


def _claim_backing_class(claim: dict) -> "str | None":
    """Resolve the class a claim is about, purely from its own text -- no
    evidence[].file cross-referencing needed. Only API-ish claim kinds are
    resolved; other kinds (feature/format_support/install/license/
    troubleshoot) are never excluded by reachability."""
    if claim.get("kind") not in _API_CLAIM_KINDS:
        return None
    text = claim.get("text") or ""
    for rx in (_CLASS_DEFINED_RE, _LEADING_MEMBER_RE, _CLASSDOC_RE):
        m = rx.match(text)
        if m:
            return m.group(1)
    return None


def _reachable_default_true(entry: dict, name: str, family: str, platform: str, language: str) -> bool:
    """True unless POSITIVELY confirmed unreachable. Mirrors
    member_validity.py's _check_class_reachability two-tier logic (primary
    field trusted; live-fallback only on unknown); defaults to "reachable"
    on unknown ambiguity so this evaluator never manufactures a FAIL from a
    partial read (matches _reachability.py's own explicit contract)."""
    primary = _reachability.class_reachability(entry)
    if primary is False:
        return False
    if primary is True:
        return True
    is_unreachable, _reason = _reachability.live_unreachable(name, family, platform, language)
    return not is_unreachable


def _load_api_surface_classes(family: str, platform: str) -> list[dict]:
    path = KNOWLEDGE_ROOT / family / platform / "merged" / "api_surface.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


def _grounded(noun_words: frozenset, classes: list[dict], claims: list[dict],
              family: str, platform: str, language: str) -> bool:
    for entry in classes:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name", "")
        if not name or not _reachable_default_true(entry, name, family, platform, language):
            continue
        candidates = [name]
        candidates += [m.get("name", "") for m in (entry.get("methods") or []) if isinstance(m, dict)]
        candidates += [p.get("name", "") for p in (entry.get("properties") or []) if isinstance(p, dict)]
        for e in (entry.get("enum_members") or []):
            ename = e.get("name") if isinstance(e, dict) else (e if isinstance(e, str) else None)
            if ename:
                candidates.append(ename)
        for cand in candidates:
            if cand and noun_words <= _split_identifier(cand):
                return True

    class_by_name = {c.get("name"): c for c in classes if isinstance(c, dict) and c.get("name")}
    for claim in claims:
        text = claim.get("text") or ""
        if not text:
            continue
        cls = _claim_backing_class(claim)
        if cls is not None:
            entry = class_by_name.get(cls)
            if entry is not None and not _reachable_default_true(entry, cls, family, platform, language):
                continue  # confirmed-unreachable-backed claim -- excluded
        if noun_words <= _claim_index.tokenize(text):
            return True
    return False


class TopicGroundingEvaluator(BaseEvaluator):
    """FAIL when a `type: topic` page's title/slug noun has zero grounding
    in the reachable knowledge surface AND evidence.claims/evidence.apis
    are both empty (see module docstring)."""

    name = "topic_grounding"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        if page.frontmatter.get("type") != "topic":
            return []
        if not page.family or not page.platform:
            return []

        evidence = page.frontmatter.get("evidence") or {}
        ev_claims = evidence.get("claims") or []
        ev_apis = evidence.get("apis") or []
        if ev_claims or ev_apis:
            return []  # FAIL requires BOTH empty -- short-circuit before any I/O

        slug = page.filepath.stem
        noun = _extract_topic_noun(slug, page.platform)
        if noun is None:
            return []
        segments = _noun_segments(noun)
        if not segments:
            return []

        classes = _load_api_surface_classes(page.family, page.platform)
        claims = _claim_index.load_claims(page.family, page.platform)
        if not classes and not claims:
            return []  # no knowledge artifacts at all -- skip cleanly (taskcard robustness rule)

        language = _PLATFORM_TO_LANGUAGE.get(page.platform, page.platform)
        # Every segment must independently ground (AND, not OR): for a
        # "convert X to Y" topic, both X and Y must be real -- if either
        # side is fabricated, the combined claim is still an overclaim.
        if all(_grounded(seg, classes, claims, page.family, page.platform, language) for seg in segments):
            return []

        level = _SEVERITY.get(page.subdomain, "WARN")
        return [Finding(
            level=level,
            category="TG",
            filepath=str(page.filepath),
            line_no=1,
            message=(
                f"Topic noun '{noun}' (from slug/title) has no grounding in the "
                f"reachable knowledge surface for {page.family}/{page.platform} "
                f"(claims.json + api_surface.json), and evidence.claims/evidence.apis "
                f"are both empty"
            ),
            suggestion=(
                "Cite real evidence.claims/evidence.apis backing this topic "
                "(run attach_evidence.py), or retire the page via /page-retire "
                "if the topic does not correspond to any real capability"
            ),
            evaluator=self.name,
        )]
