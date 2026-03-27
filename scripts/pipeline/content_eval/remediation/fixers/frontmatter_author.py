"""Fixer: add missing ``author:`` field to blog post frontmatter.

Inserts ``author: "Aspose"`` for blog posts missing the author field.
Uses regex insertion to preserve existing YAML formatting.
"""

from __future__ import annotations

import re
from typing import Any

from ...models import Finding
from . import BaseFixer

_FM_RE = re.compile(r"^(---\s*\n)(.*?)(\n---\s*\n)", re.DOTALL)


class FrontmatterAuthorFixer(BaseFixer):
    name = "frontmatter_author"
    categories = {"RV"}

    def can_fix(self, finding: Finding, page_text: str, meta: dict[str, Any]) -> bool:
        if "author" not in finding.message.lower():
            return False
        if meta.get("subdomain") != "blog":
            return False
        m = _FM_RE.match(page_text)
        if not m:
            return False
        fm_body = m.group(2)
        if re.search(r"^author\s*:", fm_body, re.MULTILINE):
            return False  # already has author
        return True

    def apply(self, finding: Finding, page_text: str, meta: dict[str, Any]) -> str:
        m = _FM_RE.match(page_text)
        if not m:
            return page_text

        fm_body = m.group(2)

        # Idempotency
        if re.search(r"^author\s*:", fm_body, re.MULTILINE):
            return page_text

        # Insert after title: line
        title_match = re.search(r"^(title\s*:.*)", fm_body, re.MULTILINE)
        if title_match:
            insert_pos = title_match.end()
            new_fm = fm_body[:insert_pos] + '\nauthor: "Aspose"' + fm_body[insert_pos:]
        else:
            new_fm = fm_body + '\nauthor: "Aspose"'

        return m.group(1) + new_fm + m.group(3) + page_text[m.end():]
