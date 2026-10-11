"""Consumer usefulness evaluator — checks that pages are actionable and purpose-driven.

H-15: Two signals, both WARN-level:

  US-1 (purpose framing): docs/kb/blog pages with ≥ 80 prose words that have no
    purpose-framing phrase in the first 80 words. Indicates the page launches
    directly into content without telling the reader what they will accomplish.
    Example fix: add "This guide shows how to ..." to the opening paragraph.

  US-2 (code without context): a code block on a docs/kb/blog page whose
    immediately-preceding section (from the most recent heading to the block)
    contains fewer than 10 prose words. Raw code without any explanation reduces
    usability for developers unfamiliar with the API.
    Example fix: add a one-sentence description above the code block.

Exempt pages:
  - subdomain == "reference" or "products" — reference stubs are exempt by design
  - pages with < 80 total prose words (too short to judge)
  - pages with page_role == "faq" for US-1 (FAQ structure differs)

Noqa escape: add ``# noqa: usefulness`` to the first prose line to skip entirely.
"""

from __future__ import annotations

import re
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator

# ---------------------------------------------------------------------------
# Purpose-framing phrases (case-insensitive, compiled once)
# ---------------------------------------------------------------------------
_PURPOSE_INDICATORS: list[re.Pattern[str]] = [
    re.compile(pat, re.IGNORECASE)
    for pat in [
        r"\bthis\s+(guide|article|tutorial|document|page|example|section)\b",
        r"\bhow\s+to\b",
        r"\bshows?\s+how\b",
        r"\bdemonstrat(?:es?|ing)\s+how\b",
        r"\byou\s+will\s+(learn|see|find|discover|create|build|generate|use|be able)\b",
        r"\byou(?:'ll|\s+can)\s+(learn|see|find|discover|create|build|generate|use)\b",
        r"\blearn\s+how\b",
        r"\bstep[- ]by[- ]step\b",
        r"\bfollowing\s+(steps?|example|guide|instructions?)\b",
        r"\bin\s+this\s+(guide|article|tutorial|section|example|document|page)\b",
        r"\blet['']s\b",
        r"\bby\s+the\s+end\s+of\b",
        r"\bafter\s+(?:completing|following|reading)\b",
        # EC-03 FP fix: product/library introduction framing — common in
        # blog posts that introduce a library rather than teach a tutorial.
        r"\benables?\s+(?:developers?|users?|you)\s+to\b",
        r"\ballows?\s+(?:developers?|users?|you)\s+to\b",
        r"\bdesigned\s+(?:for|to)\b",
        r"\bsupports?\s+(?:creating|building|generating|working|processing|converting|loading|reading|writing|parsing|extracting|handling)\b",
        r"\ba\s+(?:\S+\s+)*(?:library|tool|package|module|SDK|framework|API)\s+for\b",
        r"\b(?:free|open[- ]source|MIT[- ]licensed)\s+(?:\S+\s+)*(?:library|tool|package|module|SDK)\b",
    ]
]

# Noqa marker
_NOQA_RE = re.compile(r"#\s*noqa:\s*usefulness", re.IGNORECASE)

# Subdomains where usefulness signals apply
_APPLICABLE_SUBDOMAINS = {"docs", "blog", "kb"}

# Minimum prose words for purpose-framing check (US-1)
_MIN_PROSE_WORDS_FOR_US1 = 80

# First-N-words window for purpose framing scan
_PURPOSE_SCAN_WORDS = 80

# Minimum prose words required in the section before a code block (US-2)
_MIN_CONTEXT_WORDS = 10


class ConsumerUsefulnessEvaluator(BaseEvaluator):
    """Checks that docs/kb/blog pages frame their purpose and provide context for code."""

    name = "consumer_usefulness"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        # Only applies to docs, blog, kb
        if page.subdomain not in _APPLICABLE_SUBDOMAINS:
            return []

        # Noqa escape: if any of the first 5 prose lines carries the marker, skip entirely
        for _, text in page.prose_lines[:5]:
            if _NOQA_RE.search(text):
                return []

        findings: list[Finding] = []

        # US-1 requires sufficient prose to be meaningful
        if page.prose_lines:
            total_words = sum(len(t.split()) for _, t in page.prose_lines)
            if total_words >= _MIN_PROSE_WORDS_FOR_US1:
                findings.extend(self._check_purpose_framing(page))

        # US-2 applies even when there is little or no prose (bare code blocks)
        findings.extend(self._check_code_context(page))

        return findings

    # ------------------------------------------------------------------
    # US-1: Purpose framing
    # ------------------------------------------------------------------

    def _check_purpose_framing(self, page: Page) -> list[Finding]:
        """WARN when the first PURPOSE_SCAN_WORDS prose words lack purpose indicators."""
        # Skip FAQ pages — they have a Q&A structure, not a purpose opener
        if page.page_role == "faq":
            return []

        # Collect the first PURPOSE_SCAN_WORDS words from prose
        collected: list[str] = []
        first_prose_line = page.prose_lines[0][0]
        for _, text in page.prose_lines:
            words = text.split()
            collected.extend(words)
            if len(collected) >= _PURPOSE_SCAN_WORDS:
                break

        if not collected:
            return []

        window = " ".join(collected[:_PURPOSE_SCAN_WORDS])
        for pattern in _PURPOSE_INDICATORS:
            if pattern.search(window):
                return []  # purpose framing found — all good

        return [Finding(
            level="WARN",
            category="US",
            filepath=str(page.filepath),
            line_no=first_prose_line,
            message=(
                "No purpose framing in opening section — "
                "reader cannot tell what they will accomplish"
            ),
            suggestion=(
                "Add a sentence such as \"This guide shows how to ...\" "
                "or \"You will learn how to ...\" near the top of the page"
            ),
            evaluator=self.name,
        )]

    # ------------------------------------------------------------------
    # US-2: Code block without prose context
    # ------------------------------------------------------------------

    def _check_code_context(self, page: Page) -> list[Finding]:
        """WARN when a code block has fewer than MIN_CONTEXT_WORDS prose words before it."""
        findings: list[Finding] = []

        for block in page.code_blocks:
            context_words = self._prose_words_before_block(block.start_line, page)
            if context_words < _MIN_CONTEXT_WORDS:
                findings.append(Finding(
                    level="WARN",
                    category="US",
                    filepath=str(page.filepath),
                    line_no=block.start_line,
                    message=(
                        f"Code block has only {context_words} prose word(s) of context "
                        f"in its section — add an explanation before the example"
                    ),
                    suggestion=(
                        "Add at least one sentence describing what the code does "
                        "and why before the code block"
                    ),
                    evaluator=self.name,
                ))

        return findings

    def _prose_words_before_block(self, block_start: int, page: Page) -> int:
        """Count prose words in the section immediately preceding a code block.

        'Section' is defined as the text between the most recent heading
        (or the page start) and the code block's opening line.
        """
        # Find the most-recent heading before the block
        section_start = 0
        for h in page.headings:
            if h.line_no < block_start:
                section_start = h.line_no

        word_count = 0
        for line_no, text in page.prose_lines:
            if section_start <= line_no < block_start:
                word_count += len(text.split())
        return word_count
