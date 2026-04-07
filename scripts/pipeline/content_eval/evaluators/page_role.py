"""Page role evaluator — checks content against subdomain rubric."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator

KNOWLEDGE_ROOT = Path("knowledge")


def _has_table(page: Page) -> bool:
    """Check if page body contains a markdown table."""
    return bool(re.search(r"^\|.+\|$", page.body, re.MULTILINE))


def _count_code_blocks(page: Page, min_lines: int = 0) -> int:
    """Count code blocks, optionally filtering by minimum line count."""
    return sum(1 for b in page.code_blocks
               if len(b.content.splitlines()) >= min_lines)


def _has_shortcode(page: Page, shortcode: str) -> bool:
    """Check if a Hugo shortcode is present."""
    return shortcode in page.body


class PageRoleEvaluator(BaseEvaluator):
    """Validates page structure matches its subdomain role.

    Each subdomain has different structural requirements:
    - reference: API tables, constructors section, layout: reference-single
    - kb (how-to): steps shortcode, Step N headings, prerequisites
    - kb (faq): question headings, type: topic
    - docs: type: docs, code examples, explanatory prose
    - blog: author, categories, narrative intro
    - products: feature highlights, no long code blocks
    """

    name = "page_role"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        if not page.page_role:
            return []

        dispatch = {
            "reference": self._check_reference,
            "howto": self._check_howto,
            "faq": self._check_faq,
            "docs": self._check_docs,
            "blog": self._check_blog,
            "products": self._check_products,
            "kb_index": self._check_kb_index,
        }

        checker = dispatch.get(page.page_role)
        if checker:
            return checker(page)
        return []

    def _class_has_members(self, page: Page) -> bool:
        """Return True if api_surface has any methods or properties for this class."""
        if not page.family or not page.platform:
            return True  # can't tell — assume it does to avoid false suppression
        api_path = KNOWLEDGE_ROOT / page.family / page.platform / "merged" / "api_surface.json"
        if not api_path.exists():
            return True
        try:
            surface = json.loads(api_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return True
        class_name = page.filepath.stem
        for entry in surface:
            if entry.get("name") == class_name:
                return bool(entry.get("methods") or entry.get("properties") or entry.get("enum_members"))
        return True  # not found → assume has members

    def _check_reference(self, page: Page) -> list[Finding]:
        findings: list[Finding] = []
        fm = page.frontmatter

        # layout: reference-single or reference-home (for _index pages)
        layout = fm.get("layout", "")
        if layout not in ("reference-single", "reference-home"):
            findings.append(Finding(
                level="WARN",
                category="RV",
                filepath=str(page.filepath),
                line_no=1,
                message="Reference page missing `layout: reference-single` in frontmatter",
                suggestion="Add `layout: reference-single` to frontmatter",
                evaluator=self.name,
            ))

        if layout == "reference-home":
            # Reference home (_index.md) — validate required fields and shortcode
            for field in ("summary", "categories"):
                if not fm.get(field):
                    findings.append(Finding(
                        level="WARN",
                        category="RV",
                        filepath=str(page.filepath),
                        line_no=1,
                        message=f"Reference home page missing `{field}` in frontmatter",
                        suggestion=f"Add `{field}` — run `/new-reference-index` to regenerate",
                        evaluator=self.name,
                    ))
            body = page.body or ""
            if "{{< children >}}" not in body:
                findings.append(Finding(
                    level="WARN",
                    category="RV",
                    filepath=str(page.filepath),
                    line_no=1,
                    message="Reference home page missing {{< children >}} shortcode — class list will not render",
                    suggestion="Add `{{< children >}}` to the page body — run `/new-reference-index` to regenerate",
                    evaluator=self.name,
                ))
        else:
            # Reference class pages — must have a properties/methods table
            # unless the class has no documented members (e.g. pure exception types)
            if not _has_table(page) and self._class_has_members(page):
                findings.append(Finding(
                    level="WARN",
                    category="RV",
                    filepath=str(page.filepath),
                    line_no=1,
                    message="Reference page has no markdown table (properties/methods table expected)",
                    suggestion="Add a properties or methods table",
                    evaluator=self.name,
                ))

            # Should have code examples
            if _count_code_blocks(page) == 0:
                findings.append(Finding(
                    level="INFO",
                    category="RV",
                    filepath=str(page.filepath),
                    line_no=1,
                    message="Reference page has no code examples",
                    suggestion="Consider adding usage examples",
                    evaluator=self.name,
                ))

        return findings

    def _check_howto(self, page: Page) -> list[Finding]:
        findings: list[Finding] = []
        fm = page.frontmatter

        # type: topic
        if fm.get("type") != "topic":
            findings.append(Finding(
                level="FAIL",
                category="RV",
                filepath=str(page.filepath),
                line_no=1,
                message="KB how-to page missing `type: topic` in frontmatter",
                suggestion="Add `type: topic` to frontmatter",
                evaluator=self.name,
            ))

        # steps shortcode
        if not _has_shortcode(page, "{{% steps %}}"):
            findings.append(Finding(
                level="WARN",
                category="RV",
                filepath=str(page.filepath),
                line_no=1,
                message="KB how-to page missing `{{% steps %}}` shortcode",
                suggestion="Wrap step headings in {{% steps %}} / {{% /steps %}}",
                evaluator=self.name,
            ))

        # Step headings — accept either "Step N:" pattern or ≥3 h2/h3 headings
        step_headings = [h for h in page.headings if re.match(r"Step\s+\d", h.text)]
        section_headings = [h for h in page.headings if h.level in (2, 3)]
        if len(step_headings) < 3 and len(section_headings) < 3:
            findings.append(Finding(
                level="WARN",
                category="RV",
                filepath=str(page.filepath),
                line_no=1,
                message=f"KB how-to has only {len(step_headings)} step headings and {len(section_headings)} section headings (minimum 3 of either)",
                suggestion="Add more step headings: ### Step 1: ..., or use ## section headings",
                evaluator=self.name,
            ))

        # keywords
        keywords = fm.get("keywords", [])
        if not isinstance(keywords, list) or len(keywords) < 5:
            findings.append(Finding(
                level="WARN",
                category="RV",
                filepath=str(page.filepath),
                line_no=1,
                message=f"KB page has {len(keywords) if isinstance(keywords, list) else 0} keywords (minimum 5)",
                suggestion="Add at least 5 keywords to frontmatter",
                evaluator=self.name,
            ))

        return findings

    def _check_faq(self, page: Page) -> list[Finding]:
        findings: list[Finding] = []
        fm = page.frontmatter

        if fm.get("type") != "topic":
            findings.append(Finding(
                level="FAIL",
                category="RV",
                filepath=str(page.filepath),
                line_no=1,
                message="FAQ page missing `type: topic` in frontmatter",
                suggestion="Add `type: topic`",
                evaluator=self.name,
            ))

        # FAQ should have ## question headings
        h2_count = sum(1 for h in page.headings if h.level == 2)
        if h2_count < 3:
            findings.append(Finding(
                level="WARN",
                category="RV",
                filepath=str(page.filepath),
                line_no=1,
                message=f"FAQ has only {h2_count} question headings (## level)",
                suggestion="Add more ## question headings",
                evaluator=self.name,
            ))

        # Rule 3 — faq.list vs body cross-check.
        # If structured FAQ entries exist in frontmatter but no ### question headings
        # exist in the body, every entry is invisible: Hugo renders .Content (body only)
        # and does not iterate over frontmatter YAML arrays.
        faq_list = fm.get("faq", {}).get("list", [])
        if faq_list:
            h3_count = sum(1 for h in page.headings if h.level == 3)
            if h3_count == 0:
                findings.append(Finding(
                    level="FAIL",
                    category="RV",
                    filepath=str(page.filepath),
                    line_no=1,
                    message=(
                        f"FAQ page has {len(faq_list)} entries in frontmatter `faq.list` "
                        "but no `### Question` headings in body — entries are invisible "
                        "to the Hugo renderer (renders .Content only)"
                    ),
                    suggestion=(
                        "Regenerate using /new-kb-faq or materialize faq.list entries "
                        "as ### headings in the markdown body; remove faq.list from frontmatter"
                    ),
                    evaluator=self.name,
                ))

        return findings

    def _check_docs(self, page: Page) -> list[Finding]:
        findings: list[Finding] = []
        fm = page.frontmatter

        if fm.get("type") != "docs":
            findings.append(Finding(
                level="WARN",
                category="RV",
                filepath=str(page.filepath),
                line_no=1,
                message="Docs page missing `type: docs` in frontmatter",
                suggestion="Add `type: docs`",
                evaluator=self.name,
            ))

        if page.filepath.stem == "_index" and page.filepath.parent.name == page.platform:
            # Platform-level section landing page (e.g. .../email/cpp/_index.md)
            # Distinguish from section-level indexes (.../getting-started/_index.md)
            # by checking parent dir name matches the platform key.
            for field in ("linktitle", "subtitle", "icon"):
                if not fm.get(field):
                    findings.append(Finding(
                        level="WARN",
                        category="RV",
                        filepath=str(page.filepath),
                        line_no=1,
                        message=f"Docs platform index page missing `{field}` in frontmatter",
                        suggestion=f"Add `{field}` — run `/new-docs-index` to regenerate",
                        evaluator=self.name,
                    ))
            body = page.body or ""
            if "{{< sections >}}" not in body:
                findings.append(Finding(
                    level="WARN",
                    category="RV",
                    filepath=str(page.filepath),
                    line_no=1,
                    message="Docs platform index page missing {{< sections >}} shortcode — section will render blank",
                    suggestion="Add `{{< sections >}}` to the page body — run `/new-docs-index` to regenerate",
                    evaluator=self.name,
                ))
        else:
            # Docs content pages should have code examples
            if _count_code_blocks(page) == 0:
                findings.append(Finding(
                    level="INFO",
                    category="RV",
                    filepath=str(page.filepath),
                    line_no=1,
                    message="Docs page has no code examples",
                    suggestion="Consider adding code examples",
                    evaluator=self.name,
                ))

        return findings

    def _check_blog(self, page: Page) -> list[Finding]:
        findings: list[Finding] = []
        fm = page.frontmatter

        author = fm.get("author")
        if not author:
            # Missing author — WARN (fixable)
            findings.append(Finding(
                level="WARN",
                category="RV",
                filepath=str(page.filepath),
                line_no=1,
                message="Blog post missing `author` in frontmatter",
                suggestion="Add `author: Aspose`",
                evaluator=self.name,
            ))
        elif str(author).strip() != "Aspose":
            # Author present but wrong value — FAIL (signals off-skill generation, P-02)
            findings.append(Finding(
                level="FAIL",
                category="RV",
                filepath=str(page.filepath),
                line_no=1,
                message=(
                    f"Blog post `author` is '{author}' — must be exactly 'Aspose'. "
                    "Non-Aspose author signals the post was created outside the skill chain."
                ),
                suggestion="Change `author` to `Aspose`",
                evaluator=self.name,
            ))

        if not fm.get("categories"):
            findings.append(Finding(
                level="WARN",
                category="RV",
                filepath=str(page.filepath),
                line_no=1,
                message="Blog post missing `categories` in frontmatter",
                suggestion="Add a `categories` array",
                evaluator=self.name,
            ))

        # Blog should have at least one code example
        if _count_code_blocks(page) == 0:
            findings.append(Finding(
                level="INFO",
                category="RV",
                filepath=str(page.filepath),
                line_no=1,
                message="Blog post has no code examples",
                suggestion="Consider adding a code example",
                evaluator=self.name,
            ))

        return findings

    def _check_kb_index(self, page: Page) -> list[Finding]:
        """Validate KB section listing pages (_index.md) have all required fields."""
        findings: list[Finding] = []
        fm = page.frontmatter

        if not fm.get("title"):
            findings.append(Finding(
                level="WARN",
                category="RV",
                filepath=str(page.filepath),
                line_no=1,
                message="KB index page missing `title` in frontmatter",
                suggestion="Add a `title` field",
                evaluator=self.name,
            ))

        for field in ("linkTitle", "subtitle", "icon"):
            if not fm.get(field):
                findings.append(Finding(
                    level="WARN",
                    category="RV",
                    filepath=str(page.filepath),
                    line_no=1,
                    message=f"KB index page missing `{field}` in frontmatter",
                    suggestion=f"Add a `{field}` field — run `/new-kb-index` to regenerate",
                    evaluator=self.name,
                ))

        body = page.body or ""
        if "{{< children >}}" not in body:
            findings.append(Finding(
                level="WARN",
                category="RV",
                filepath=str(page.filepath),
                line_no=1,
                message="KB index page missing {{< children >}} shortcode — section will render blank",
                suggestion="Add `{{< children >}}` to the page body — run `/new-kb-index` to regenerate",
                evaluator=self.name,
            ))

        return findings

    def _check_products(self, page: Page) -> list[Finding]:
        findings: list[Finding] = []

        # Products pages should not have long code blocks
        long_blocks = [b for b in page.code_blocks
                       if len(b.content.splitlines()) > 10]
        for block in long_blocks:
            findings.append(Finding(
                level="INFO",
                category="RV",
                filepath=str(page.filepath),
                line_no=block.start_line,
                message="Product page has a code block >10 lines",
                suggestion="Keep product pages high-level; move detailed code to docs",
                evaluator=self.name,
            ))

        return findings
