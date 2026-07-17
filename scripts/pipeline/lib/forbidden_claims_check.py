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
        #    and is not explicitly negated.
        if matched is None:
            for line in lines:
                if _NEGATION_RE.search(line):
                    continue
                if not _CAPABILITY_RE.search(line):
                    continue
                for cls in owning_classes:
                    if re.search(r"\b" + re.escape(cls) + r"\b", line):
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
