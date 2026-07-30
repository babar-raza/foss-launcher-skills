"""Prose truth evaluator — matches factual claims against knowledge."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator

_DEFAULT_KNOWLEDGE_ROOT = Path("knowledge")
KNOWLEDGE_ROOT = _DEFAULT_KNOWLEDGE_ROOT


def configure(*, knowledge_root: "Path | str | None" = None) -> None:
    """Testing seam (AGENTS.md §16) — set/reset KNOWLEDGE_ROOT without monkeypatch."""
    global KNOWLEDGE_ROOT
    KNOWLEDGE_ROOT = Path(knowledge_root) if knowledge_root is not None else _DEFAULT_KNOWLEDGE_ROOT

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

# ST-023 (2026-07-30) directional-claim patterns.
#
# Root cause: _FORMAT_CLAIM_RE grabs whatever short token sits directly
# before "format"/"file"/"document", with no regard for sentence direction.
# For "Aspose.PDF FOSS for Go now exports PDF documents to HTML..." that
# token is "PDF" -- but the sentence names TWO formats: PDF (the kind of
# document being acted on -- this library's own source format, not a claim
# about PDF being an export TARGET) and HTML (the actual destination the
# capability claim is about: "can produce HTML output"). Nearest-token
# matching picks the wrong one, so the evaluator flagged the true, correct
# claim "PDF export but knowledge shows import-only" for a sentence that
# never claimed PDF is an export target at all.
#
# Fix: resolve the sentence's real directional clause -- "<verb> ... to/into
# <FORMAT>" claims export of FORMAT; "<verb> ... from <FORMAT>" claims import
# of FORMAT -- and let that take priority over the nearest-token match. The
# candidate FORMAT is validated against this page's own format_support dict
# (built from formats.json below) rather than a hardcoded allowlist, so a
# generic "to disk"/"to the caller" clause is never mistaken for a format
# claim: only a token this specific product's knowledge actually recognizes
# as a format name is treated as one.
_DIRECTIONAL_CLAIM_RE = re.compile(
    r"\b(?:export|import|convert|save|write|read|load|render)\w*\b"
    r".{0,60}?"
    r"\b(?P<prep>to|into|from)\s+(?:the\s+)?(?P<fmt>\w{2,6})\b",
    re.IGNORECASE,
)

# "<SRC>-to-<DST> conversion"/"supports X-to-Y conversion" -- the hyphenated
# form of the same directional claim, handled separately because there is no
# whitespace between the verb-governed clause and the format tokens for
# _DIRECTIONAL_CLAIM_RE to anchor on. A claimed "X-to-Y" conversion asserts
# BOTH capabilities: import of X (the source) and export of Y (the
# destination).
_HYPHEN_TO_RE = re.compile(r"\b(\w{2,6})-to-(\w{2,6})\b", re.IGNORECASE)

# Strong wording indicators
_STRONG_WORDS = re.compile(
    r"\b(?:always|never|all|every|none|only|must|guaranteed|ensures?|"
    r"fully|completely|perfectly|exactly|precisely)\b",
    re.IGNORECASE,
)

# Site-specific severity for unbacked claims (H-06 / H-09)
_UNBACKED_CLAIM_SEVERITY: dict[str, str] = {
    "reference": "FAIL",
    "blog": "WARN",
    "kb": "WARN",
    "docs": "INFO",
    "products": "WARN",
}

# ---------------------------------------------------------------------------
# TF-IDF semantic matching — shared module (H-10 refactor)
# ---------------------------------------------------------------------------

from ._claim_index import (
    ClaimIndex as _ClaimIndex,
    best_token_overlap as _best_token_overlap,
    clear_claim_cache,
    get_claim_index as _get_claim_index,
    is_markdown_table_row as _is_markdown_table_row,
    load_claims as _load_claims,
    tokenize as _tokenize_shared,
)

# Re-export for backwards compatibility
clear_claim_cache = clear_claim_cache


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# EC-03 fix: patterns where "strong words" are normal technical language,
# not marketing claims.  These appear in API docs (e.g. "the only supported
# format", "must be called before save()", "all properties are read-only").
_TECHNICAL_CONTEXT_RE = re.compile(
    r"(?:"
    r"must\s+be\s+(?:called|set|specified|initialized|non-null|valid)"
    r"|(?:the\s+)?only\s+(?:supported|available|valid|required|property|method|parameter|way)"
    r"|all\s+(?:properties|members|methods|parameters|fields|elements|items)\s+(?:are|have|must)"
    r"|every\s+(?:property|member|method|call|instance)\s+(?:must|should|has|returns)"
    r"|(?:returns?|accepts?|expects?)\s+(?:exactly|precisely)\s+\d+"
    r"|read[\s-]only"
    r"|write[\s-]only"
    r"|none\s+of\s+the\s+(?:properties|methods|members|parameters)"
    r"|ensures?\s+(?:that\s+)?(?:the\s+)?(?:object|instance|value|result)"
    r"|guaranteed\s+to\s+(?:be|return|succeed)"
    r"|all\s+(?:examples?|code\s+(?:examples?|samples?|snippets?)|snippets?)\b"
    r"|\|\s*`?none`?\s*\|"
    r")",
    re.IGNORECASE,
)


def _is_technical_strong_wording(line_text: str) -> bool:
    """Return True if the strong word appears in a technical API context."""
    return bool(_TECHNICAL_CONTEXT_RE.search(line_text))


_BACKTICK_SPAN_RE = re.compile(r"`[^`]*`")


def _has_prose_strong_wording(line_text: str) -> bool:
    """Return True if a strong word appears outside any backtick-quoted span.

    A strong word wrapped in backticks (e.g. a property or method literally
    named `All`, `Any`, `None`, `Only`) is an identifier reference, not a
    prose overclaim -- reference pages routinely list real API member names
    that happen to collide with common English words (PageSet.All is a real
    static property). Excluding backtick spans here prevents those from being
    misread as marketing language while still catching genuine unbacked
    strong wording elsewhere on the same line.
    """
    code_spans = [m.span() for m in _BACKTICK_SPAN_RE.finditer(line_text)]
    for m in _STRONG_WORDS.finditer(line_text):
        start, end = m.span()
        if not any(cs <= start and end <= ce for cs, ce in code_spans):
            return True
    return False


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
    """Extract lowercase word tokens (delegates to shared _claim_index)."""
    return _tokenize_shared(text)


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

        findings: list[Finding] = []

        if knowledge is None or not getattr(knowledge, 'available', False):
            findings.append(Finding(
                level="WARN",
                category="PT",
                filepath=str(page.filepath),
                line_no=0,
                message=(
                    f"UNVERIFIED: knowledge artifacts not available for "
                    f"{page.family}/{page.platform}. Claims cannot be validated."
                ),
                evaluator=self.name,
            ))

        # --- API claim verification against knowledge model ---
        # Runs unconditionally when knowledge is available; does NOT require on-disk claims.
        has_knowledge = knowledge is not None and hasattr(knowledge, "classes") and getattr(knowledge, "available", False)
        if has_knowledge:
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
                            # Site-specific: reference → FAIL, blog/kb → WARN, docs → WARN
                            _api_level = _UNBACKED_CLAIM_SEVERITY.get(
                                page.subdomain, "WARN"
                            )
                            findings.append(Finding(
                                level=_api_level,
                                category="PT",
                                filepath=str(page.filepath),
                                line_no=line_no,
                                message=f"Prose claims `{cls_name}` has `{member}` but not found in API surface",
                                suggestion=f"Verify `{cls_name}.{member}` exists or fix the reference",
                                evaluator=self.name,
                            ))

        # Load on-disk claims and formats for token/format matching
        claims = _load_claims(page.family, page.platform)
        formats = _load_formats(page.family, page.platform)


        # Build claim token index for fuzzy matching
        claim_tokens = [(c.get("text", ""), _tokenize(c.get("text", "")))
                        for c in claims if c.get("text")]

        # Build TF-IDF claim index for semantic matching (secondary tier, cached)
        claim_index = _get_claim_index(page.family, page.platform)

        # Build section → claims map for strong-wording suppression (N2).
        # Maps heading text to its claims list; only sections with ≥1 claim are included.
        # Uses page.headings line_nos (always current) rather than the stored section "line"
        # values (which can be stale after frontmatter rewrites).
        _evidence = page.frontmatter.get("evidence") or {}
        _section_claims: dict[str, list] = {}
        for _sec in (_evidence.get("sections") or []):
            _heading_text = _sec.get("heading", "")
            _sec_claims = _sec.get("claims") or []
            if _heading_text and _sec_claims:
                _section_claims[_heading_text] = _sec_claims

        # Build sorted list of (line_no, heading_text) for evidenced sections.
        # Primary source: page.headings line_nos (always current).
        # Fallback for sections whose heading text doesn't appear as an actual ##
        # heading (e.g., preamble "Introduction" text before the first heading):
        # insert at line 0 so all pre-heading prose is covered.
        _heading_texts_in_page = {h.text for h in page.headings}
        _evidenced_section_lines: list[tuple[int, str]] = []
        for h in page.headings:
            if h.text in _section_claims:
                _evidenced_section_lines.append((h.line_no, h.text))
        for _heading_text in _section_claims:
            if _heading_text not in _heading_texts_in_page:
                # Preamble/intro section with no matching heading — cover from line 0
                _evidenced_section_lines.append((0, _heading_text))
        _evidenced_section_lines.sort(key=lambda x: x[0])

        def _enclosing_section_has_claims(line_no: int) -> bool:
            """Return True if *line_no* falls within an evidence-backed section."""
            enclosing: str | None = None
            for sec_line, sec_heading in _evidenced_section_lines:
                if sec_line <= line_no:
                    enclosing = sec_heading
                else:
                    break
            return bool(enclosing)

        # Build format lookup — merge entries so bidirectional formats get "both"
        format_support: dict[str, str] = {}
        for fmt in formats:
            ext = (fmt.get("format") or fmt.get("ext") or "").lower()
            direction = (fmt.get("direction") or fmt.get("support") or "").lower()
            if ext:
                existing = format_support.get(ext)
                if existing and existing != direction:
                    format_support[ext] = "both"
                else:
                    format_support[ext] = direction

        def _direction_mismatch_finding(
            fmt_token: str, claimed_dir: str, known_dir: str, line_no: int,
        ) -> "Finding | None":
            """Return a FAIL Finding when claimed_dir contradicts known_dir,
            or None when the claim is consistent (or known_dir is 'both')."""
            if claimed_dir == "export" and known_dir == "import":
                return Finding(
                    level="FAIL",
                    category="PT",
                    filepath=str(page.filepath),
                    line_no=line_no,
                    message=f"Claims {fmt_token.upper()} export but knowledge shows import-only",
                    suggestion=f"Fix direction: {fmt_token.upper()} supports {known_dir}",
                    evaluator=self.name,
                )
            if claimed_dir == "import" and known_dir == "export":
                return Finding(
                    level="FAIL",
                    category="PT",
                    filepath=str(page.filepath),
                    line_no=line_no,
                    message=f"Claims {fmt_token.upper()} import but knowledge shows export-only",
                    suggestion=f"Fix direction: {fmt_token.upper()} supports {known_dir}",
                    evaluator=self.name,
                )
            return None

        # Check format claims in prose
        for line_no, line_text in page.prose_lines:
            if _is_markdown_table_row(line_text):
                continue

            # ST-023: resolve directional "<verb> ... to/into/from <FORMAT>"
            # clauses FIRST -- they identify which of potentially several
            # format-like tokens on the line is the one actually being
            # claimed, and in which direction. Spans consumed by a resolved
            # directional clause are shadowed from the nearest-token fallback
            # below so the SOURCE token in "exports SRC documents to DST"
            # (SRC, not an independent claim) isn't re-evaluated in the
            # opposite, wrong direction.
            _shadowed_spans: list[tuple[int, int]] = []

            for dm in _DIRECTIONAL_CLAIM_RE.finditer(line_text):
                fmt_token = dm.group("fmt").lower()
                if fmt_token not in format_support:
                    continue  # not a recognized format for this product
                claimed_dir = (
                    "export" if dm.group("prep").lower() in ("to", "into") else "import"
                )
                finding = _direction_mismatch_finding(
                    fmt_token, claimed_dir, format_support[fmt_token], line_no,
                )
                if finding is not None:
                    findings.append(finding)
                # The clause between the verb and the preposition names the
                # SOURCE/acted-upon document (e.g. "PDF" in "exports PDF
                # documents to HTML") -- shadow it regardless of whether a
                # mismatch fired, so it is never independently re-checked.
                _shadowed_spans.append((dm.start(), dm.start("prep")))

            for hm in _HYPHEN_TO_RE.finditer(line_text):
                # "X-to-Y conversion" claims import(X) + export(Y).
                src_token = hm.group(1).lower()
                dst_token = hm.group(2).lower()
                if src_token in format_support:
                    finding = _direction_mismatch_finding(
                        src_token, "import", format_support[src_token], line_no,
                    )
                    if finding is not None:
                        findings.append(finding)
                    _shadowed_spans.append(hm.span(1))
                if dst_token in format_support:
                    finding = _direction_mismatch_finding(
                        dst_token, "export", format_support[dst_token], line_no,
                    )
                    if finding is not None:
                        findings.append(finding)
                    _shadowed_spans.append(hm.span(2))

            def _in_shadow(pos: int) -> bool:
                return any(start <= pos < end for start, end in _shadowed_spans)

            for m in _FORMAT_CLAIM_RE.finditer(line_text):
                if _in_shadow(m.start(1)):
                    continue
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
            if _has_prose_strong_wording(line_text):
                # EC-03 Pattern fix: suppress strong-wording check in
                # technical API contexts where words like "only", "all",
                # "must", "every" are factual descriptors, not marketing.
                if _is_technical_strong_wording(line_text):
                    continue

                line_tokens = _tokenize(line_text)
                best_overlap = _best_token_overlap(line_tokens, [ct for _, ct in claim_tokens])

                if best_overlap < 0.3 and len(line_tokens) > 3:
                    # Secondary tier: TF-IDF semantic matching
                    # If cosine similarity is high enough, the claim is supported
                    if claim_index.available:
                        semantic_score = claim_index.best_similarity(line_text)
                        if semantic_score >= 0.6:
                            continue  # Supported by semantic similarity

                    # Tertiary tier: section-level evidence suppression.
                    # If the line falls within a section that has ≥1 claim in
                    # evidence.sections, the operator has explicitly backed this
                    # section — suppress the strong-wording WARN.
                    if _enclosing_section_has_claims(line_no):
                        continue

                    # Site-specific severity: reference pages get FAIL,
                    # blog/kb/products get WARN, docs gets INFO.
                    _unbacked_level = _UNBACKED_CLAIM_SEVERITY.get(
                        page.subdomain, "WARN"
                    )
                    findings.append(Finding(
                        level=_unbacked_level,
                        category="PT",
                        filepath=str(page.filepath),
                        line_no=line_no,
                        message="Strong wording with weak evidence backing",
                        suggestion="Qualify the claim or add supporting evidence",
                        evaluator=self.name,
                    ))

        return findings
