"""Consumer usefulness evaluator -- checks that pages are actionable and purpose-driven."""

from __future__ import annotations

import re
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator

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
        r"\blet['\u2019]s\b",
        r"\bby\s+the\s+end\s+of\b",
        r"\bafter\s+(?:completing|following|reading)\b",
        r"\benables?\s+(?:developers?|users?|you)\s+to\b",
        r"\ballows?\s+(?:developers?|users?|you)\s+to\b",
        r"\bdesigned\s+(?:for|to)\b",
        r"\bsupports?\s+(?:creating|building|generating|working|processing|converting|loading|reading|writing|parsing|extracting|handling)\b",
        r"\ba\s+(?:\S+\s+)*(?:library|tool|package|module|SDK|framework|API)\s+for\b",
        r"\b(?:free|open[- ]source|MIT[- ]licensed)\s+(?:\S+\s+)*(?:library|tool|package|module|SDK)\b",
    ]
]

_NOQA_RE = re.compile(r"#\s*noqa:\s*usefulness", re.IGNORECASE)
_APPLICABLE_SUBDOMAINS = {"docs", "blog", "kb"}
_MIN_PROSE_WORDS_FOR_US1 = 80
_PURPOSE_SCAN_WORDS = 80
_MIN_CONTEXT_WORDS = 10


class ConsumerUsefulnessEvaluator(BaseEvaluator):
    """Checks that docs/kb/blog pages frame their purpose and provide context for code."""

    name = "consumer_usefulness"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        if page.subdomain not in _APPLICABLE_SUBDOMAINS:
            return []

        for _, text in page.prose_lines[:5]:
            if _NOQA_RE.search(text):
                return []

        findings: list[Finding] = []

        if page.prose_lines:
            total_words = sum(len(t.split()) for _, t in page.prose_lines)
            if total_words >= _MIN_PROSE_WORDS_FOR_US1:
                findings.extend(self._check_purpose_framing(page))

        findings.extend(self._check_code_context(page))
        return findings

    def _check_purpose_framing(self, page: Page) -> list[Finding]:
        if page.page_role == "faq":
            return []

        collected: list[str] = []
        first_prose_line = page.prose_lines[0][0]
        for _, text in page.prose_lines:
            collected.extend(text.split())
            if len(collected) >= _PURPOSE_SCAN_WORDS:
                break

        if not collected:
            return []

        window = " ".join(collected[:_PURPOSE_SCAN_WORDS])
        for pattern in _PURPOSE_INDICATORS:
            if pattern.search(window):
                return []

        return [Finding(
            level="WARN",
            category="US",
            filepath=str(page.filepath),
            line_no=first_prose_line,
            message="No purpose framing in opening section -- reader cannot tell what they will accomplish",
            suggestion='Add a sentence such as "This guide shows how to ..." near the top of the page',
            evaluator=self.name,
        )]

    def _check_code_context(self, page: Page) -> list[Finding]:
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
                        f"in its section -- add an explanation before the example"
                    ),
                    suggestion="Add at least one sentence describing what the code does before the code block",
                    evaluator=self.name,
                ))

        return findings

    def _prose_words_before_block(self, block_start: int, page: Page) -> int:
        section_start = 0
        for h in page.headings:
            if h.line_no < block_start:
                section_start = h.line_no

        word_count = 0
        for line_no, text in page.prose_lines:
            if section_start <= line_no < block_start:
                word_count += len(text.split())
        return word_count
