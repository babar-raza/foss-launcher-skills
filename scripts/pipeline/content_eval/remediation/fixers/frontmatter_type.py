"""Fixer: add missing ``type:`` field to frontmatter.

Docs pages get ``type: docs``, KB non-index pages get ``type: topic``.
Uses regex insertion to preserve existing YAML formatting.
"""

from __future__ import annotations

import re
from typing import Any

from ...models import Finding
from . import BaseFixer

# Match the opening frontmatter block
_FM_RE = re.compile(r"^(---\s*\n)(.*?)(\n---\s*\n)", re.DOTALL)


class FrontmatterTypeFixer(BaseFixer):
    name = "frontmatter_type"
    categories = {"RV"}

    def can_fix(self, finding: Finding, page_text: str, meta: dict[str, Any]) -> bool:
        if "type:" not in finding.message.lower() and "type" not in finding.message.lower():
            return False
        subdomain = meta.get("subdomain", "")
        if subdomain not in ("docs", "kb"):
            return False
        # Don't fix if type: already present
        m = _FM_RE.match(page_text)
        if not m:
            return False
        fm_body = m.group(2)
        if re.search(r"^type\s*:", fm_body, re.MULTILINE):
            return False  # already has type
        return True

    def apply(self, finding: Finding, page_text: str, meta: dict[str, Any]) -> str:
        subdomain = meta.get("subdomain", "")
        page_role = meta.get("page_role", "")

        # Determine what type value to insert
        if subdomain == "docs":
            type_val = "docs"
        elif subdomain == "kb" and page_role != "kb_index":
            type_val = "topic"
        else:
            return page_text  # no change for kb _index pages

        m = _FM_RE.match(page_text)
        if not m:
            return page_text

        fm_body = m.group(2)

        # Idempotency: already has type
        if re.search(r"^type\s*:", fm_body, re.MULTILINE):
            return page_text

        # Insert after title: line (or at end of frontmatter if no title)
        title_match = re.search(r"^(title\s*:.*)", fm_body, re.MULTILINE)
        if title_match:
            insert_pos = title_match.end()
            new_fm = fm_body[:insert_pos] + f"\ntype: {type_val}" + fm_body[insert_pos:]
        else:
            new_fm = fm_body + f"\ntype: {type_val}"

        return m.group(1) + new_fm + m.group(3) + page_text[m.end():]
