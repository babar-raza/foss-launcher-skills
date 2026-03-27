"""Structure evaluator — heading hierarchy, code fences, placeholders, links."""

from __future__ import annotations

import re
from typing import Any

from ..config import PLACEHOLDER_PATTERNS
from ..models import Finding, Page
from . import BaseEvaluator


class StructureEvaluator(BaseEvaluator):
    """Validates structural correctness of content pages.

    Checks:
    - Frontmatter has title and description
    - No placeholder text remains
    - Heading hierarchy is valid (no skipped levels)
    - Code blocks have language identifiers
    - Filename uses kebab-case
    """

    name = "structure"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        findings: list[Finding] = []
        findings.extend(self._check_frontmatter(page))
        findings.extend(self._check_placeholders(page))
        findings.extend(self._check_heading_hierarchy(page))
        findings.extend(self._check_code_fences(page))
        findings.extend(self._check_filename(page))
        findings.extend(self._check_empty_body(page))
        return findings

    def _check_frontmatter(self, page: Page) -> list[Finding]:
        findings: list[Finding] = []
        fm = page.frontmatter

        if not fm.get("title"):
            findings.append(Finding(
                level="FAIL",
                category="ST",
                filepath=str(page.filepath),
                line_no=1,
                message="Missing or empty `title` in frontmatter",
                suggestion="Add a `title` field",
                evaluator=self.name,
            ))

        if not fm.get("description"):
            findings.append(Finding(
                level="WARN",
                category="ST",
                filepath=str(page.filepath),
                line_no=1,
                message="Missing or empty `description` in frontmatter",
                suggestion="Add a `description` field for SEO",
                evaluator=self.name,
            ))

        # Check date format
        for date_field in ("date", "lastmod"):
            val = fm.get(date_field)
            if val and isinstance(val, str):
                if not re.match(r"^\d{4}-\d{2}-\d{2}", val):
                    findings.append(Finding(
                        level="WARN",
                        category="ST",
                        filepath=str(page.filepath),
                        line_no=1,
                        message=f"`{date_field}` not in YYYY-MM-DD format: {val}",
                        suggestion="Use format: 'YYYY-MM-DD'",
                        evaluator=self.name,
                    ))

        return findings

    def _check_placeholders(self, page: Page) -> list[Finding]:
        findings: list[Finding] = []
        for line_no, line_text in page.prose_lines:
            for pattern, desc in PLACEHOLDER_PATTERNS:
                if re.search(pattern, line_text):
                    findings.append(Finding(
                        level="FAIL",
                        category="ST",
                        filepath=str(page.filepath),
                        line_no=line_no,
                        message=f"Placeholder text found: {desc}",
                        suggestion="Replace with actual content",
                        evaluator=self.name,
                    ))
                    break  # One finding per line

        return findings

    def _check_heading_hierarchy(self, page: Page) -> list[Finding]:
        findings: list[Finding] = []
        prev_level = 0

        for heading in page.headings:
            if prev_level > 0 and heading.level > prev_level + 1:
                findings.append(Finding(
                    level="INFO",
                    category="ST",
                    filepath=str(page.filepath),
                    line_no=heading.line_no,
                    message=f"Heading level skipped: h{prev_level} → h{heading.level}",
                    suggestion=f"Use h{prev_level + 1} instead of h{heading.level}",
                    evaluator=self.name,
                ))
            prev_level = heading.level

        return findings

    def _check_code_fences(self, page: Page) -> list[Finding]:
        findings: list[Finding] = []

        _BOX_DRAWING = re.compile(r"[└├│┌┐┘┬┤─┼]")

        for block in page.code_blocks:
            if not block.lang:
                # Downgrade ASCII art / short output blocks to INFO
                lines = block.content.splitlines()
                is_ascii_art = bool(_BOX_DRAWING.search(block.content))
                is_short = len(lines) <= 3
                level = "INFO" if (is_ascii_art or is_short) else "WARN"
                findings.append(Finding(
                    level=level,
                    category="ST",
                    filepath=str(page.filepath),
                    line_no=block.start_line,
                    message="Code block missing language identifier",
                    suggestion="Add a language tag: ```python, ```csharp, etc.",
                    evaluator=self.name,
                ))

        return findings

    def _check_filename(self, page: Page) -> list[Finding]:
        findings: list[Finding] = []
        name = page.filepath.stem

        # Skip _index files
        if name == "_index":
            return findings

        # Check kebab-case (allow leading underscore)
        if not re.match(r"^_?[a-z0-9]+(?:-[a-z0-9]+)*$", name):
            # Don't flag index.md (common for blog posts)
            if name != "index":
                findings.append(Finding(
                    level="INFO",
                    category="ST",
                    filepath=str(page.filepath),
                    line_no=1,
                    message=f"Filename `{name}.md` not in kebab-case",
                    suggestion="Use lowercase with hyphens: my-page-name.md",
                    evaluator=self.name,
                ))

        return findings

    def _check_empty_body(self, page: Page) -> list[Finding]:
        if not page.body.strip():
            # Products pages store content in YAML frontmatter (layout: plugin)
            if page.frontmatter.get("layout") == "plugin":
                return []
            return [Finding(
                level="FAIL",
                category="ST",
                filepath=str(page.filepath),
                line_no=1,
                message="Page body is empty (only frontmatter)",
                suggestion="Add content below the frontmatter",
                evaluator=self.name,
            )]
        return []
