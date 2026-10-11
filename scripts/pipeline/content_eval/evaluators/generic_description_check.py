"""Generic description check for reference index tables.

Catches placeholder descriptions such as "Class in the Pdf API." that are
produced by the last-resort fallback in batch_reference.py._build_grouped_index_body()
when:
  1. The api_surface.json entry has no doc string, and
  2. No ERC claim covers the class.

These placeholder descriptions are not useful to readers and indicate either
missing source-code doc comments or a pipeline coverage gap.

This evaluator is experimental: it runs in evaluation and reports appear in
manifests, but it does not affect canonical frontmatter grade until graduation.
"""

from __future__ import annotations

import re
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator

# These strings indicate that the generic fallback was triggered.
# Matches: "Class in the Pdf API." / "Interface in the 3d API." etc.
# The pattern requires exactly one word between "the" and "API." to avoid
# matching the synthesized fallback "Class in the Pdf NET API.".
_GENERIC_PATTERN = re.compile(
    r"\b(Class|Interface|Enum|Struct|Delegate) in the \w+ API\.$"
)

_FAIL_MIN = 3
_FAIL_PCT = 5.0
_WARN_MIN = 1
_MIN_TABLE_ROWS = 3

_SEP_RE = re.compile(r"^\|[\s:]*-+[\s:]*(\|[\s:]*-+[\s:]*)*\|?$")


def _parse_index_table_rows(body: str, body_offset: int) -> list[tuple[int, list[str]]]:
    """Extract ``(line_no, cells)`` rows from Markdown tables with descriptions."""
    lines = body.splitlines()
    result: list[tuple[int, list[str]]] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if "|" in line and i + 1 < len(lines):
            sep = lines[i + 1].strip()
            if _SEP_RE.match(sep):
                hdrs = [c.strip() for c in line.split("|") if c.strip()]
                desc_idx = next(
                    (
                        idx
                        for idx, header in enumerate(hdrs)
                        if header.lower() in {"description", "summary"}
                    ),
                    None,
                )
                if desc_idx is None:
                    i += 1
                    continue

                j = i + 2
                while j < len(lines):
                    row_line = lines[j].strip()
                    if not row_line or "|" not in row_line:
                        break
                    safe = row_line.replace("\\|", "\x00")
                    raw = safe.split("|")
                    if raw and not raw[0].strip():
                        raw = raw[1:]
                    if raw and not raw[-1].strip():
                        raw = raw[:-1]
                    cells = [c.replace("\x00", "|").strip() for c in raw]
                    result.append((j + body_offset + 1, cells))
                    j += 1
                i = j
                continue
        i += 1
    return result


class GenericDescriptionCheckEvaluator(BaseEvaluator):
    """Detect generic placeholder descriptions in reference index page tables."""

    name = "generic_description_check"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        if page.subdomain != "reference":
            return []

        fp_str = str(page.filepath).replace("\\", "/")
        if not fp_str.endswith("_index.md"):
            return []

        if page.frontmatter.get("retired_at"):
            return []

        rows = _parse_index_table_rows(page.body, page.body_offset)
        if len(rows) < _MIN_TABLE_ROWS:
            return []

        matching: list[tuple[int, str]] = []
        for abs_line, cells in rows:
            desc = cells[1] if len(cells) >= 2 else ""
            if _GENERIC_PATTERN.search(desc):
                matching.append((abs_line, desc))

        if not matching:
            return []

        count = len(matching)
        total = len(rows)
        pct = (count / total) * 100
        level = "FAIL" if count >= _FAIL_MIN or pct > _FAIL_PCT else "WARN"
        sample = matching[0][1]

        return [Finding(
            level=level,
            category="GD",
            filepath=str(page.filepath),
            line_no=matching[0][0],
            message=(
                f"{count}/{total} index table rows ({pct:.1f}%) contain generic "
                f"placeholder descriptions (e.g. '{sample}'). These are produced "
                "by the batch_reference.py last-resort fallback and indicate "
                "missing source-code doc comments or ERC claim coverage."
            ),
            suggestion=(
                "Regenerate the index with --generate-index after ensuring "
                "api_surface.json doc fields are populated or ERC claims cover "
                "the affected classes."
            ),
            evaluator=self.name,
        )]
