"""Limitations check evaluator — detects capability pages that lack a limitations section.

Per AGENTS.md evidence rules, documentation pages that cover API capabilities
should either:

* Include a "Limitations" / "Known Issues" section, OR
* Link to a separate limitations page, OR
* Explicitly direct readers to such a page.

Pages that do none of the above are flagged as INFO when the product has a
non-trivial ``merged/limitations.md`` knowledge file.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator

KNOWLEDGE_ROOT = Path("knowledge")

# Headings that qualify as a limitations section
_LIMITATION_HEADING_RE = re.compile(
    r"\b(?:limitation|known\s+issue|not\s+supported|restriction|caveat)\b",
    re.IGNORECASE,
)

# Prose patterns that indicate limitations are addressed inline
_LIMITATION_PROSE_RE = re.compile(
    r"\b(?:not\s+supported|not\s+implemented|throws?\s+NotImplementedError"
    r"|raises?\s+NotImplementedError|does\s+not\s+support|limitation)\b",
    re.IGNORECASE,
)

# Explicit "For limitations, see <link>" style redirects
_LIMITATION_SEE_RE = re.compile(
    r"(?:for|see|refer\s+to)\s+.{0,40}?limitation",
    re.IGNORECASE,
)

# Backtick API reference pattern (for counting)
_BACKTICK_API_RE = re.compile(r"`[A-Z][A-Za-z0-9]+(?:\.[a-zA-Z0-9]+)?`")

# URL pattern indicating a link to a limitations page
_LIMITATION_URL_RE = re.compile(r"limitation", re.IGNORECASE)


def _limitations_md_has_content(family: str, platform: str) -> bool:
    """Return True if merged/limitations.md exists and has substantial content."""
    path = KNOWLEDGE_ROOT / family / platform / "merged" / "limitations.md"
    if not path.exists():
        return False
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        return len(content.strip()) > 100
    except OSError:
        return False


class LimitationsCheckEvaluator(BaseEvaluator):
    """Flags docs/kb pages that cover API usage but lack any limitations section.

    Only fires when the product has a non-trivial ``merged/limitations.md``
    to ensure there is something meaningful to link to.  Level is INFO.
    """

    name = "limitations_check"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        # Gate: docs or kb subdomain, docs/howto role, non-index pages
        if page.subdomain not in ("docs", "kb"):
            return []
        if page.page_role not in ("docs", "howto"):
            return []
        if page.filepath.name == "_index.md":
            return []
        if not page.family or not page.platform:
            return []

        # Check whether the page covers substantial API usage
        code_block_count = len(page.code_blocks)
        backtick_api_count = sum(
            len(_BACKTICK_API_RE.findall(line))
            for _, line in page.prose_lines
        )
        covers_api = code_block_count >= 2 or backtick_api_count >= 5
        if not covers_api:
            return []

        # Check for limitations heading
        for heading in page.headings:
            if _LIMITATION_HEADING_RE.search(heading.text):
                return []

        # Check for inline limitation prose
        for _, line in page.prose_lines:
            if _LIMITATION_PROSE_RE.search(line):
                return []
            if _LIMITATION_SEE_RE.search(line):
                return []

        # Check for links to a limitations page
        for link in page.links:
            if _LIMITATION_URL_RE.search(link.url):
                return []

        # Only fire if the product actually has limitations content
        if not _limitations_md_has_content(page.family, page.platform):
            return []

        lim_path = (
            f"knowledge/{page.family}/{page.platform}/merged/limitations.md"
        )
        return [Finding(
            level="INFO",
            category="LC",
            filepath=str(page.filepath),
            line_no=1,
            message=(
                f"Page covers API usage ({code_block_count} code block(s), "
                f"{backtick_api_count} backtick ref(s)) but has no limitations section"
            ),
            suggestion=(
                f"Add a '## Limitations' section or link to the limitations page. "
                f"Known limitations are documented in {lim_path}"
            ),
            evaluator=self.name,
        )]
