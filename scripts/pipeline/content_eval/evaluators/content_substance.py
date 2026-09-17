"""Content substance evaluator — detects stub pages and pages lacking code examples."""

from __future__ import annotations

import re
from typing import Any

from ..models import CodeBlock, Finding, Page
from . import BaseEvaluator

# Thresholds
_STUB_WORD_LIMIT = 50       # <50 prose words → FAIL (stub page; docs/blog/howto)
_REF_STUB_WORD_LIMIT = 10   # <10 prose words → FAIL (reference pages; content is in tables)
_REF_PROSE_MINIMUM = 200    # reference pages: need code OR ≥200 words
_HOWTO_PROSE_MINIMUM = 150  # howto/docs/blog: need code AND ≥150 words

# CE-03 (plans/healing/2026-09-17-content-eval-hardening-gaps.md, gap G-04):
# section headings whose bodies are known template boilerplate — generic
# advice ("dispose of resources", "check the API reference") that a
# skill-generated stub can pad prose-word-count with even when the page has
# zero real content. A line inside one of these sections is excluded from
# the word count UNLESS it cites a real, specific identifier (backtick-
# wrapped) — a genuine page's "Tips and Best Practices" section naming real
# methods/classes still counts; the retired-page template's generic prose
# ("Handle file I/O exceptions when reading or writing files") does not.
# Measured against the 4 pages retired in commit 820d2c7e8e (fixtures under
# scripts/pipeline/tests/content_eval/fixtures/): each carried exactly this
# 3-section boilerplate block and none contained a single backtick.
_BOILERPLATE_SECTION_HEADINGS = frozenset({
    "tips and best practices",
    "related resources",
    "see also",
})


def _boilerplate_line_numbers(page: Page) -> set[int]:
    """Line numbers inside a known-boilerplate section with no backticked identifier."""
    if not page.headings:
        return set()

    ordered = sorted(page.headings, key=lambda h: h.line_no)
    boilerplate_ranges: list[tuple[int, int, int]] = []  # (start, end, level)
    for i, h in enumerate(ordered):
        if h.text.strip().lower() not in _BOILERPLATE_SECTION_HEADINGS:
            continue
        end = ordered[i + 1].line_no if i + 1 < len(ordered) else float("inf")
        boilerplate_ranges.append((h.line_no, end, h.level))

    if not boilerplate_ranges:
        return set()

    excluded: set[int] = set()
    for line_no, text in page.prose_lines:
        if "`" in text:
            continue  # cites a real identifier — never exclude
        for start, end, _level in boilerplate_ranges:
            if start < line_no < end:
                excluded.add(line_no)
                break
    return excluded


def _count_prose_words(page: Page) -> int:
    """Count words in prose lines, excluding table rows and boilerplate-section filler."""
    excluded = _boilerplate_line_numbers(page)
    total = 0
    for line_no, text in page.prose_lines:
        # Skip table rows (lines that are part of Markdown tables)
        if text.strip().startswith("|"):
            continue
        if line_no in excluded:
            continue
        total += len(text.split())
    return total


# CE-03 (gap G-04): a fenced code block whose only content is a single
# comment-style line (e.g. `// See API reference for usage details`) is a
# placeholder, not a working example — presence alone must not satisfy the
# "has code" checks below. Matches the exact defect measured in CE-01's
# fixtures (all 4 retired pages' only API-language block was one such line).
_COMMENT_ONLY_LINE_RE = re.compile(r"^\s*(?:#|//|/\*.*\*/|--|;|%)\s*\S")


def _is_placeholder_code(content: str) -> bool:
    """True if a code block has no content, or exactly one comment-only line."""
    lines = [ln for ln in content.strip().splitlines() if ln.strip()]
    if not lines:
        return True
    return len(lines) == 1 and bool(_COMMENT_ONLY_LINE_RE.match(lines[0]))


def _has_real_code(code_blocks: list[CodeBlock]) -> bool:
    """True if at least one code block is more than a placeholder comment."""
    return any(not _is_placeholder_code(cb.content) for cb in code_blocks)


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
        has_real_code = _has_real_code(page.code_blocks)

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
            if not has_real_code and prose_words < _REF_PROSE_MINIMUM:
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
            if not has_real_code and prose_words < _HOWTO_PROSE_MINIMUM:
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
