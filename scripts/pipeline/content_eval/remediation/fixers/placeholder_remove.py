"""Fixer: remove or flag placeholder text.

Standalone placeholder lines (e.g. ``{TODO}``, ``TBD``) are removed.
Placeholders embedded within sentences are replaced with ``[NEEDS CONTENT]``
to convert a FAIL into a visible marker for LLM or human follow-up.
"""

from __future__ import annotations

import re
from typing import Any

from ...config import PLACEHOLDER_PATTERNS
from ...models import Finding
from . import BaseFixer

# Build a combined pattern from config
_PLACEHOLDER_RE = re.compile(
    "|".join(f"({pat})" for pat, _ in PLACEHOLDER_PATTERNS),
    re.IGNORECASE,
)

_NEEDS_CONTENT = "[NEEDS CONTENT]"


class PlaceholderRemoveFixer(BaseFixer):
    name = "placeholder_remove"
    categories = {"ST"}

    def can_fix(self, finding: Finding, page_text: str, meta: dict[str, Any]) -> bool:
        msg = finding.message.lower()
        return "placeholder" in msg or "todo" in msg or "tbd" in msg or "fixme" in msg

    def apply(self, finding: Finding, page_text: str, meta: dict[str, Any]) -> str:
        line_no = finding.line_no
        lines = page_text.split("\n")
        if line_no < 1 or line_no > len(lines):
            return page_text

        idx = line_no - 1
        line = lines[idx]
        stripped = line.strip()

        # Idempotency: already replaced
        if _NEEDS_CONTENT in line:
            return page_text

        # Check if the entire line is just placeholder text
        if _PLACEHOLDER_RE.fullmatch(stripped):
            # Remove the line entirely
            lines.pop(idx)
            return "\n".join(lines)

        # Embedded placeholder — replace token with marker
        new_line = _PLACEHOLDER_RE.sub(_NEEDS_CONTENT, line)
        if new_line != line:
            lines[idx] = new_line

        return "\n".join(lines)
