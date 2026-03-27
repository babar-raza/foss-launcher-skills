"""Install recipe evaluator — detects API documentation pages that lack installation guidance.

Documentation pages that demonstrate API usage (code blocks or backtick
references) but contain no installation instructions and no link to an
installation page are flagged as INFO.  This is a cross-page concern, so the
severity is kept low.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator

KNOWLEDGE_ROOT = Path("knowledge")

# Package-manager / install command patterns (case-insensitive)
_INSTALL_PROSE_RE = re.compile(
    r"pip\s+install|mvn\b|<dependency\b|dotnet\s+add\s+package|nuget\b"
    r"|npm\s+install|cargo\s+add|gem\s+install|composer\s+require",
    re.IGNORECASE,
)

# Heading text patterns that indicate an install/setup section
_INSTALL_HEADING_RE = re.compile(
    r"\b(?:install|setup|prerequisite|requirement|getting[\s-]started)\b",
    re.IGNORECASE,
)

# URL fragments that suggest a link to an install page
_INSTALL_URL_RE = re.compile(
    r"installation|getting-started|getting_started|quickstart",
    re.IGNORECASE,
)

# Slug patterns: if the page itself is an install/setup page, skip it
_INSTALL_SLUG_RE = re.compile(
    r"installation|getting-started|getting_started|install\b|setup",
    re.IGNORECASE,
)

# Backtick API reference pattern in prose
_BACKTICK_API_RE = re.compile(r"`[A-Z][A-Za-z0-9]+(?:\.[a-zA-Z0-9]+)?`")


class InstallRecipeEvaluator(BaseEvaluator):
    """Flags documentation pages that demonstrate API usage but lack install guidance.

    Only applies to ``docs`` subdomain pages with role ``docs`` or ``howto``
    that are not index pages.  Level is INFO because installation instructions
    may legitimately live on a linked page.
    """

    name = "install_recipe"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        # Gate: only docs subdomain, docs/howto role, non-index pages
        if page.subdomain != "docs":
            return []
        if page.page_role not in ("docs", "howto"):
            return []
        if page.filepath.name == "_index.md":
            return []

        # Skip if this page IS an installation/setup page
        page_path_str = str(page.filepath).replace("\\", "/")
        if _INSTALL_SLUG_RE.search(page_path_str):
            return []

        # Check whether the page has meaningful API usage
        code_block_count = len(page.code_blocks)
        backtick_api_count = sum(
            len(_BACKTICK_API_RE.findall(line))
            for _, line in page.prose_lines
        )
        has_api_usage = code_block_count >= 1 or backtick_api_count >= 3
        if not has_api_usage:
            return []

        # Check for installation content in prose
        for _, line in page.prose_lines:
            if _INSTALL_PROSE_RE.search(line):
                return []  # Install instructions present

        # Check for install instructions inside code blocks
        for block in page.code_blocks:
            if _INSTALL_PROSE_RE.search(block.content):
                return []

        # Check for install-related headings
        for heading in page.headings:
            if _INSTALL_HEADING_RE.search(heading.text):
                return []

        # Check for links pointing to an installation page
        for link in page.links:
            if _INSTALL_URL_RE.search(link.url):
                return []

        # No install content found — build a helpful suggestion
        suggestion = (
            "Add installation instructions or link to an installation page. "
        )
        if page.family and page.platform:
            install_md = KNOWLEDGE_ROOT / page.family / page.platform / "merged" / "install.md"
            if install_md.exists():
                content = install_md.read_text(encoding="utf-8", errors="replace")
                if len(content) > 50:
                    suggestion += (
                        f"Installation content is available at "
                        f"knowledge/{page.family}/{page.platform}/merged/install.md"
                    )

        return [Finding(
            level="INFO",
            category="IR",
            filepath=str(page.filepath),
            line_no=1,
            message=(
                f"Page demonstrates API usage ({code_block_count} code block(s), "
                f"{backtick_api_count} backtick ref(s)) but has no installation instructions"
            ),
            suggestion=suggestion.strip(),
            evaluator=self.name,
        )]
