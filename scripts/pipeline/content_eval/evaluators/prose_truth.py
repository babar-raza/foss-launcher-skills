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

        # Check format claims in prose
        for line_no, line_text in page.prose_lines:
            if _is_markdown_table_row(line_text):
                continue

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
