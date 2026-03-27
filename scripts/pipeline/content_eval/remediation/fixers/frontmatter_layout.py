"""Fixer: add missing ``layout: reference-single`` to reference pages.

Reference pages (non-index) on reference.aspose.org require this layout
field for proper rendering.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ...models import Finding
from . import BaseFixer

_FM_RE = re.compile(r"^(---\s*\n)(.*?)(\n---\s*\n)", re.DOTALL)


class FrontmatterLayoutFixer(BaseFixer):
    name = "frontmatter_layout"
    categories = {"RV"}

    def can_fix(self, finding: Finding, page_text: str, meta: dict[str, Any]) -> bool:
        if "layout" not in finding.message.lower():
            return False
        if meta.get("subdomain") != "reference":
            return False
        # Don't fix _index pages
        filepath = Path(meta.get("filepath", ""))
        if filepath.stem == "_index":
            return False
        m = _FM_RE.match(page_text)
        if not m:
            return False
        fm_body = m.group(2)
        if re.search(r"^layout\s*:", fm_body, re.MULTILINE):
            return False  # already has layout
        return True

    def apply(self, finding: Finding, page_text: str, meta: dict[str, Any]) -> str:
        m = _FM_RE.match(page_text)
        if not m:
            return page_text

        fm_body = m.group(2)

        # Idempotency
        if re.search(r"^layout\s*:", fm_body, re.MULTILINE):
            return page_text

        # Insert after title: line
        title_match = re.search(r"^(title\s*:.*)", fm_body, re.MULTILINE)
        if title_match:
            insert_pos = title_match.end()
            new_fm = fm_body[:insert_pos] + "\nlayout: reference-single" + fm_body[insert_pos:]
        else:
            new_fm = fm_body + "\nlayout: reference-single"

        return m.group(1) + new_fm + m.group(3) + page_text[m.end():]
