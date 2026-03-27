"""Fixer: wrap step headings in ``{{% steps %}}`` shortcode.

KB how-to pages use ``### Step N:`` headings. This fixer wraps the
step section in Hugo's ``{{% steps %}} ... {{% /steps %}}`` shortcode
for proper rendering.
"""

from __future__ import annotations

import re
from typing import Any

from ...models import Finding
from . import BaseFixer

# Match step headings: ### Step 1, ## Step 2, ### Step 1:, etc.
_STEP_HEADING_RE = re.compile(r"^(#{2,3})\s+(?:Step\s+\d+|الخطوة\s+\d+)", re.IGNORECASE)

# Match any ## heading (non-step) — used to find the boundary after steps
_H2_HEADING_RE = re.compile(r"^##\s+(?!Step\s+\d)", re.IGNORECASE)

_STEPS_OPEN = "{{% steps %}}"
_STEPS_CLOSE = "{{% /steps %}}"


class StepsShortcodeFixer(BaseFixer):
    name = "steps_shortcode"
    categories = {"RV"}

    def can_fix(self, finding: Finding, page_text: str, meta: dict[str, Any]) -> bool:
        msg = finding.message.lower()
        if "steps" not in msg or "shortcode" not in msg:
            return False
        if meta.get("subdomain") != "kb":
            return False
        # Must have step headings to wrap
        if not _STEP_HEADING_RE.search(page_text):
            return False
        # Already has shortcode
        if _STEPS_OPEN in page_text:
            return False
        return True

    def apply(self, finding: Finding, page_text: str, meta: dict[str, Any]) -> str:
        # Idempotency
        if _STEPS_OPEN in page_text:
            return page_text

        lines = page_text.split("\n")

        # Find first step heading
        first_step_idx = None
        last_step_end_idx = None

        for i, line in enumerate(lines):
            if _STEP_HEADING_RE.match(line):
                if first_step_idx is None:
                    first_step_idx = i
                last_step_end_idx = i

        if first_step_idx is None:
            return page_text

        # Find where the last step section ends:
        # Either at the next non-step ## heading, or at EOF
        end_idx = len(lines)
        for i in range(last_step_end_idx + 1, len(lines)):
            line = lines[i]
            # A ## heading that is NOT a step heading ends the step section
            if line.startswith("## ") and not _STEP_HEADING_RE.match(line):
                end_idx = i
                break

        # Walk backwards from end_idx to skip trailing blank lines
        insert_close_idx = end_idx
        while insert_close_idx > last_step_end_idx and not lines[insert_close_idx - 1].strip():
            insert_close_idx -= 1

        # Insert shortcodes
        # Insert close tag first (higher index) to preserve line numbers
        lines.insert(insert_close_idx, "")
        lines.insert(insert_close_idx + 1, _STEPS_CLOSE)

        # Insert open tag before first step heading
        lines.insert(first_step_idx, _STEPS_OPEN)
        lines.insert(first_step_idx + 1, "")

        return "\n".join(lines)
