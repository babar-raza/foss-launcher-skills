"""
regrounding_check.py — RPR-E-03: per-page re-grounding to stop template propagation.

CONTRACT: scripts/pipeline/lib/regrounding_check.py
  purpose: Detect the same distinctive technical span (a code block or a claim
           carrying a dotted API symbol) being reused VERBATIM across multiple
           pages within one refresh run without the reusing page being grounded
           in the same evidence — the exact shape of the 3d/net
           `node.Transform.Scale = new FVector3(...)` fabrication that recurred
           identically across 6 unrelated pages (plan §2.4). A shared bad snippet
           copied without regard to what each page is actually about.
  inputs:  per-page body text + that page's cited evidence IDs.
  outputs: violation dicts (empty = clean). Stateful across a run via RegroundingCache.
  idempotent: re-checking the SAME page with the same content re-registers cleanly
           (same_page_repeat), so a rerun of a whole product does not self-flag.

Deliberately EXEMPT (returns no span, so never flagged):
  - Generic prose with no dotted API symbol (e.g. the canned deterministic-fallback
    note "This section has been reviewed against the current source model ...").
    Reusing boilerplate across pages is not propagation of a fabricated CLAIM, and
    flagging it would create WARN-fatigue and fight the legitimate fallback path.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

# A dotted API reference: ClassName.Member — the marker of a specific technical claim.
_DOTTED_SYMBOL_RE = re.compile(r"\b[A-Z][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*\b")
_FENCED_CODE_RE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)


def _normalize(span: str) -> str:
    return re.sub(r"\s+", " ", span.strip().lower())


def fingerprint(span: str) -> str:
    """Whitespace-insensitive content hash of a distinctive span."""
    return hashlib.sha256(_normalize(span).encode("utf-8")).hexdigest()[:16]


def extract_distinctive_spans(text: str) -> list[str]:
    """Return the distinctive technical spans of a body: fenced code blocks that
    contain a dotted API symbol, plus individual non-code lines carrying a dotted
    symbol. Spans without a dotted symbol are omitted (generic/boilerplate)."""
    spans: list[str] = []
    seen: set[str] = set()

    # Fenced code blocks with a dotted symbol.
    for code in _FENCED_CODE_RE.findall(text):
        if _DOTTED_SYMBOL_RE.search(code):
            key = _normalize(code)
            if key and key not in seen:
                seen.add(key)
                spans.append(code)

    # Non-code lines carrying a dotted symbol (strip fenced blocks first so their
    # interior lines are not double-counted).
    text_no_code = _FENCED_CODE_RE.sub("", text)
    for line in text_no_code.splitlines():
        if _DOTTED_SYMBOL_RE.search(line):
            key = _normalize(line)
            if key and key not in seen:
                seen.add(key)
                spans.append(line)

    return spans


@dataclass
class RegroundingViolation:
    fingerprint: str
    span_excerpt: str
    reusing_page: str
    first_page: str
    reason: str = "template_propagation_without_shared_grounding"

    def to_dict(self) -> dict:
        return {
            "fingerprint": self.fingerprint,
            "span_excerpt": self.span_excerpt[:120],
            "reusing_page": self.reusing_page,
            "first_page": self.first_page,
            "reason": self.reason,
        }


@dataclass
class RegroundingCache:
    """Per-run store of distinctive-span fingerprints → (first page, its grounded IDs)."""

    _seen: dict = field(default_factory=dict)  # fingerprint -> (page_id, frozenset[str])

    def check_page(
        self,
        page_id: str,
        body_text: str,
        cited_evidence: list[str] | None = None,
    ) -> list[RegroundingViolation]:
        """Register this page's distinctive spans and return any that reuse a span
        first seen on a DIFFERENT page whose grounding this page does not share.

        A first occurrence, or a same-page re-check, or a reuse where the two pages
        share at least one cited evidence ID, is allowed (no violation).
        """
        cited = frozenset(cited_evidence or [])
        violations: list[RegroundingViolation] = []

        for span in extract_distinctive_spans(body_text):
            fp = fingerprint(span)
            if fp not in self._seen:
                self._seen[fp] = (page_id, cited)
                continue
            first_page, first_grounded = self._seen[fp]
            if first_page == page_id:
                continue  # same page re-checked (idempotent rerun) — fine
            if cited & first_grounded:
                continue  # both pages grounded in the same evidence — legitimate reuse
            violations.append(RegroundingViolation(
                fingerprint=fp,
                span_excerpt=span,
                reusing_page=page_id,
                first_page=first_page,
            ))
        return violations
