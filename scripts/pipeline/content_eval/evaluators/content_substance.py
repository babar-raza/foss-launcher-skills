"""Content substance evaluator -- detects stub pages and pages lacking code examples."""

from __future__ import annotations

from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator

_STUB_WORD_LIMIT = 50
_REF_PROSE_MINIMUM = 200
_HOWTO_PROSE_MINIMUM = 150


def _count_prose_words(page: Page) -> int:
    total = 0
    for _, text in page.prose_lines:
        if text.strip().startswith("|"):
            continue
        total += len(text.split())
    return total


class ContentSubstanceEvaluator(BaseEvaluator):
    """Detects pages with insufficient content substance."""

    name = "content_substance"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        findings: list[Finding] = []

        if page.filepath.stem == "_index":
            return findings
        if page.subdomain == "products":
            return findings

        prose_words = _count_prose_words(page)
        code_count = len(page.code_blocks)

        if prose_words < _STUB_WORD_LIMIT:
            findings.append(Finding(
                level="FAIL",
                category="SB",
                filepath=str(page.filepath),
                line_no=1,
                message=f"Stub page: only {prose_words} prose words",
                suggestion="Add substantive content -- a published page needs meaningful prose",
                evaluator=self.name,
            ))
            return findings

        if page.page_role == "reference":
            if code_count == 0 and prose_words < _REF_PROSE_MINIMUM:
                findings.append(Finding(
                    level="WARN",
                    category="SB",
                    filepath=str(page.filepath),
                    line_no=1,
                    message=f"Reference page lacks code examples and has thin prose ({prose_words} words)",
                    suggestion="Add usage examples or expand API member descriptions",
                    evaluator=self.name,
                ))

        elif page.page_role in ("howto", "docs", "blog"):
            if code_count == 0 and prose_words < _HOWTO_PROSE_MINIMUM:
                findings.append(Finding(
                    level="WARN",
                    category="SB",
                    filepath=str(page.filepath),
                    line_no=1,
                    message=f"Page lacks code examples and has thin prose ({prose_words} words)",
                    suggestion="Add code examples demonstrating the topic",
                    evaluator=self.name,
                ))

        return findings
