"""
forbidden_claims_check.py — RPR-E-02 (shared with RPR-F-04).

CONTRACT: scripts/pipeline/lib/forbidden_claims_check.py
  purpose: Detect content that affirmatively claims support for an API/capability
           the knowledge model marks FORBIDDEN (i.e. its methods throw
           NotImplementedException). Used at generation time by body_refresh.py
           (S-105) to reject a candidate before it is written, instead of only
           catching the violation in a post-hoc audit — the exact gap behind the
           3d/net "3MF" fabrication that landed across 13 files and was never
           re-scanned (plan §2.4).
  inputs:  candidate text; a forbidden_claims list (strings from
           knowledge/{family}/{platform}/merged/index.json's "forbidden_claims").
  outputs: a list of violation dicts (empty = clean). Pure function, no I/O in scan().
  idempotent: yes — deterministic, read-only scan.

Matching precision (deliberately NOT fuzzy, to avoid WARN-fatigue):
  - A fully-qualified symbol from a forbidden claim (e.g. ``Microsoft3MFFormat.IsBuildable``)
    matched as a word in the text is a STRONG violation — a page mentioning that exact
    member is almost certainly claiming it works.
  - A bare owning-class name (e.g. ``Microsoft3MFFormat``) is flagged only when the SAME
    line also carries affirmative capability language (support/can/enable/convert/…),
    so an incidental or explicitly-negative mention ("X is NOT supported") is not flagged.

Library usage::

    from forbidden_claims_check import scan, load_forbidden_claims
    violations = scan(candidate_text, load_forbidden_claims("3d", "net"))
    if violations:
        ...  # reject candidate / route to review — never write silently
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]  # lib/ -> pipeline/ -> scripts/ -> repo root

# A dotted API reference: ClassName or ClassName.Member(.Member)*. Requires an
# uppercase-initial head so lowercase prose words ("supports", "the") never match.
_SYMBOL_RE = re.compile(r"\b[A-Z][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+\b")
_BARE_CLASS_RE = re.compile(r"\b[A-Z][A-Za-z0-9_]{2,}\b")

# Affirmative capability language that turns a bare-class mention into a claim.
_CAPABILITY_RE = re.compile(
    r"\b(support|supports|supported|can|enables?|enabled|convert|converts|"
    r"provides?|allow|allows|use|uses|write|writes|read|reads|export|exports|import|imports)\b",
    re.IGNORECASE,
)
_NEGATION_RE = re.compile(r"\b(not|no|never|cannot|can't|unsupported|without)\b", re.IGNORECASE)

# A class name reached only through a relational/possessive phrase ("associated
# with X", "properties of X", "part of X") is being named as CONTEXT for what
# the sentence is actually about, not as the subject performing the capability.
# Matches immediately before the class name so a per-occurrence check (see
# _class_mentions_outside_relation below) can tell "the Foo instance" (direct,
# a real subject) apart from "properties of Foo" (relational, not a subject).
_RELATION_PRECEDING_RE = re.compile(
    r"\b(associated with|related to|belonging to|part of|properties of|"
    r"members? of|attributes? of|fields? of)\s+$",
    re.IGNORECASE,
)

# Inline-code spans: `like this`. A single backtick pair, non-greedy, no newline.
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")

# A markdown table row: starts and ends with `|` (ignoring surrounding whitespace),
# with at least one more `|` inside — i.e. 2+ cells.
_TABLE_ROW_RE = re.compile(r"^\s*\|(.*)\|\s*$")


def _strip_inline_code(text: str) -> str:
    """Remove backtick-delimited inline-code spans from text."""
    return _INLINE_CODE_RE.sub(" ", text)


def _capability_scan_text(line: str) -> str:
    """Return the portion of a line tier 2 should search for capability
    language and bare-class mentions.

    HARDEN-FC-01 (2026-07-29): tier 2 ("class_with_capability_language") used
    to search the WHOLE line for both a bare owning-class mention and generic
    capability language, with no distinction between prose that actually
    claims a capability and the structural, non-prose columns of an
    auto-generated Methods (`| Signature | Description |`) or Properties
    (`| Name | Type | Access | Description |`) table. Two concrete failure
    shapes, both found live blocking 29 3d/java reference pages from a
    legitimate ST-013 regeneration:

      1. A class name appearing only as a backtick-quoted return/parameter
         TYPE (e.g. `` `getFileSystem()` `->` `FileSystem` ``) is a type
         annotation, not a capability subject — handled by stripping inline
         code before the class-name search (see below).
      2. A Properties table's Access column is literally the word "Read" or
         "Read/Write" — and "read"/"write" are themselves in the generic
         capability-verb list, so EVERY properties row satisfies the
         capability check regardless of what the description says (found:
         `` | `fileSystemFactory` | `FileSystemFactory` | Read | Gets the
         factory class for FileSystem. | `` flagged purely because of its
         own Access="Read" column, not because the description claims
         anything about reading files).

    For a table row (2+ `|`-delimited cells — every Methods/Properties row
    this pipeline generates), both checks are scoped to the LAST cell only:
    by construction, the description/prose column is always last in these
    templates, and every other column (signature, type, access) is
    structural markup that should never itself satisfy either check. Inline
    code is additionally stripped from that cell before the class-name
    search, per case 1. Non-table lines (ordinary prose paragraphs, where
    the original 3d/net "3MF" incident this module exists to catch actually
    occurred) are returned unchanged — this narrowing applies only to the
    generated-table shape, never to free-form prose.
    """
    m = _TABLE_ROW_RE.match(line)
    if not m:
        return line
    cells = m.group(1).split("|")
    return cells[-1] if cells else line


def _class_mentioned_outside_relation(prose: str, cls: str) -> bool:
    """True if ``cls`` appears in ``prose`` at least once NOT immediately
    preceded by a relational/possessive phrase ("associated with X",
    "properties of X", "part of X", ...).

    HARDEN-FC-02 (2026-07-29): a bare owning-class match plus capability
    language on the same description text still over-triggers when the class
    is named only as CONTEXT for what the sentence is actually about, not as
    the subject performing the capability. Found live: "Export meta data
    associated with Scene/Node to client." -- "Export" (capability language)
    and "Scene" (owning class of the forbidden "supports Scene.render" claim)
    both appear, but the sentence is about an `exportMetaData` boolean flag,
    not about Scene rendering. Every mention of "Scene" in that file follows
    "associated with" or "properties of" -- never appears as a direct object
    ("supports Scene", "can render Scene") the way a real over-claiming
    incident (the 3d/net "3MF" case this module exists to catch) would.

    This checks each occurrence independently: a class mentioned BOTH
    relationally and directly in the same text still counts as a genuine
    mention (the direct occurrence carries the signal), preserving recall for
    real capability prose that happens to also contain an incidental
    possessive reference elsewhere.
    """
    for m in re.finditer(r"\b" + re.escape(cls) + r"\b", prose):
        preceding = prose[:m.start()]
        if not _RELATION_PRECEDING_RE.search(preceding):
            return True
    return False


def extract_symbols(forbidden_claim: str) -> tuple[set[str], set[str]]:
    """Return (fully_qualified_symbols, owning_classes) from one forbidden-claim string.

    'supports Microsoft3MFFormat.IsBuildable'
        -> ({'Microsoft3MFFormat.IsBuildable'}, {'Microsoft3MFFormat'})
    'supports DocumentCollection'
        -> (set(), {'DocumentCollection'})
    """
    fq: set[str] = set()
    classes: set[str] = set()
    for m in _SYMBOL_RE.findall(forbidden_claim):
        fq.add(m)
        classes.add(m.split(".", 1)[0])
    if not fq:
        # No dotted symbol; take a bare class-like token (skip the leading verb).
        for m in _BARE_CLASS_RE.findall(forbidden_claim):
            classes.add(m)
    return fq, classes


def scan(text: str, forbidden_claims: list[str]) -> list[dict]:
    """Return violation dicts for forbidden claims affirmatively made by ``text``.

    Each violation: {forbidden_claim, matched_symbol, match_type}
    where match_type is 'fully_qualified' or 'class_with_capability_language'.
    At most one violation per forbidden_claim (first/strongest match wins).
    """
    if not text or not forbidden_claims:
        return []

    lines = text.splitlines()
    violations: list[dict] = []

    for claim in forbidden_claims:
        fq_symbols, owning_classes = extract_symbols(claim)
        matched = None

        # 1) Fully-qualified member match anywhere in the text — strong signal.
        for sym in fq_symbols:
            if re.search(r"\b" + re.escape(sym) + r"\b", text):
                matched = {"forbidden_claim": claim, "matched_symbol": sym,
                           "match_type": "fully_qualified"}
                break

        # 2) Bare owning-class match on a line that also carries capability language
        #    and is not explicitly negated. Both checks run against the line's
        #    description-only scan text (HARDEN-FC-01) — for a generated
        #    Methods/Properties table row that means just the last (Description)
        #    cell, with inline code additionally stripped before the class-name
        #    search; for ordinary prose it's the line unchanged. Negation is
        #    still checked against the full original line (conservative: a
        #    negation word anywhere in the row still suppresses the match).
        #    A class reached only through a relational/possessive phrase
        #    ("associated with X", "properties of X") is named as context,
        #    not as the subject of the capability (HARDEN-FC-02) — every
        #    other occurrence still counts normally.
        if matched is None:
            for line in lines:
                if _NEGATION_RE.search(line):
                    continue
                scan_text = _capability_scan_text(line)
                if not _CAPABILITY_RE.search(scan_text):
                    continue
                prose = _strip_inline_code(scan_text)
                for cls in owning_classes:
                    if _class_mentioned_outside_relation(prose, cls):
                        matched = {"forbidden_claim": claim, "matched_symbol": cls,
                                   "match_type": "class_with_capability_language"}
                        break
                if matched:
                    break

        if matched:
            violations.append(matched)

    return violations


def load_forbidden_claims(family: str, platform: str, *, repo_root: Path | None = None) -> list[str]:
    """Load the forbidden_claims list from a product's merged/index.json.

    Returns [] when the product has no index.json or no forbidden_claims key —
    an absent list means "nothing forbidden known", NOT an error.
    """
    root = repo_root or _REPO_ROOT
    index_path = root / "knowledge" / family / platform / "merged" / "index.json"
    if not index_path.exists():
        return []
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    fc = data.get("forbidden_claims") or data.get("forbidden") or []
    return [str(x) for x in fc if x]


def newly_introduced(old_text: str, new_text: str, forbidden_claims: list[str]) -> list[dict]:
    """Violations present in new_text but NOT already in old_text.

    body_refresh.py uses this so a refresh is blocked only for a forbidden claim
    *it introduces*, never punished for a pre-existing violation it did not touch
    (that is a separate remediation concern, not a reason to abort this edit).
    """
    old_v = {(v["forbidden_claim"], v["matched_symbol"]) for v in scan(old_text, forbidden_claims)}
    return [v for v in scan(new_text, forbidden_claims)
            if (v["forbidden_claim"], v["matched_symbol"]) not in old_v]
