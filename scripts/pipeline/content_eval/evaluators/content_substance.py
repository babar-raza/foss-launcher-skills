"""Content substance evaluator — detects stub pages and pages lacking code examples."""

from __future__ import annotations

from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator

# Thresholds
_STUB_WORD_LIMIT = 50       # <50 prose words → FAIL (stub page; docs/blog/howto)
_REF_STUB_WORD_LIMIT = 10   # <10 prose words → FAIL (reference pages; content is in tables)
_REF_PROSE_MINIMUM = 200    # reference pages: need code OR ≥200 words
_HOWTO_PROSE_MINIMUM = 150  # howto/docs/blog: need code AND ≥150 words


def _count_prose_words(page: Page) -> int:
    """Count words in prose lines, excluding table rows."""
    total = 0
    for _, text in page.prose_lines:
        # Skip table rows (lines that are part of Markdown tables)
        if text.strip().startswith("|"):
            continue
        total += len(text.split())
    return total


def _has_table_content(page: Page) -> bool:
    """Return True if the page has at least one non-empty markdown table data row."""
    for _, text in page.prose_lines:
        stripped = text.strip()
        if stripped.startswith("|") and not stripped.startswith("|---") and stripped.count("|") >= 2:
            # Filter out header-separator rows (|---|---|) and count real data rows
            parts = [p.strip() for p in stripped.split("|")[1:-1]]
            if any(p and p != "---" and not all(c in "-: " for c in p) for p in parts):
                return True
    return False


class ContentSubstanceEvaluator(BaseEvaluator):
    """Detects pages with insufficient content substance.

    Flags:
    - Stub pages with very little prose (<50 words for docs/blog/howto) → FAIL
    - Reference pages with nearly-empty prose (<10 words) and no table → FAIL
    - Reference pages lacking code examples and thin prose → WARN
    - Howto/docs/blog pages lacking code examples and thin prose → WARN

    Note: reference pages legitimately have their content in Properties/Methods tables,
    which are excluded from prose word counts.  The stub threshold is therefore much
    lower for reference pages — only pages with almost no content at all are flagged.
    """

    name = "content_substance"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        findings: list[Finding] = []

        # Exempt _index.md section pages
        if page.filepath.stem == "_index":
            return findings

        # Exempt products pages (feature highlights, not technical content)
        if page.subdomain == "products":
            return findings

        prose_words = _count_prose_words(page)
        code_count = len(page.code_blocks)

        # Stub page check — threshold depends on page role.
        # Reference pages have content in tables (excluded from prose count), so the
        # threshold is lowered: only fire FAIL if prose is extremely sparse AND no table.
        if page.page_role == "reference":
            stub_limit = _REF_STUB_WORD_LIMIT
            is_stub = prose_words < stub_limit and not _has_table_content(page)
        else:
            stub_limit = _STUB_WORD_LIMIT
            is_stub = prose_words < stub_limit

        if is_stub:
            findings.append(Finding(
                level="FAIL",
                category="CS",
                filepath=str(page.filepath),
                line_no=1,
                message=f"Stub page: only {prose_words} prose words",
                suggestion=(
                    "Add substantive content — a published page needs meaningful prose"
                    if page.page_role != "reference"
                    else "Add a description and API member entries to this reference page"
                ),
                evaluator=self.name,
            ))
            return findings  # Don't add lower-severity findings on top of stub FAIL

        # Reference pages: need code examples OR substantial prose
        if page.page_role == "reference":
            if code_count == 0 and prose_words < _REF_PROSE_MINIMUM:
                findings.append(Finding(
                    level="WARN",
                    category="CS",
                    filepath=str(page.filepath),
                    line_no=1,
                    message=f"Reference page lacks code examples and has thin prose ({prose_words} words)",
                    suggestion="Add usage examples or expand API member descriptions",
                    evaluator=self.name,
                ))

        # Howto, docs, blog pages: need code examples AND sufficient prose
        elif page.page_role in ("howto", "docs", "blog"):
            if code_count == 0 and prose_words < _HOWTO_PROSE_MINIMUM:
                findings.append(Finding(
                    level="WARN",
                    category="CS",
                    filepath=str(page.filepath),
                    line_no=1,
                    message=f"Page lacks code examples and has thin prose ({prose_words} words)",
                    suggestion="Add code examples demonstrating the topic",
                    evaluator=self.name,
                ))

        return findings
