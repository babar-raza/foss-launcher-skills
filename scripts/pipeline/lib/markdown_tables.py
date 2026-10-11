"""Shared GFM pipe-table parser.

Extracted from ``content_eval/evaluators/description_completeness.py`` (H7,
MT068-2026-09-11-IMAGING-NET-LAUNCH) so a second, independent consumer
(``extraction/capability_tables.py``) does not reimplement markdown-table
parsing a third time in this codebase. Behavior is unchanged from the
original ``_parse_tables`` — this is a pure extraction, not a rewrite.
"""

from __future__ import annotations

import re

_SEPARATOR_ROW_RE = re.compile(r"^\|[\s:]*-+[\s:]*(\|[\s:]*-+[\s:]*)*\|?$")


def parse_markdown_tables(body: str, body_offset: int = 0) -> list[dict]:
    """Parse GFM pipe-tables out of ``body`` text.

    A table is recognized as a line containing ``|`` immediately followed by
    a separator line matching ``|---|---|`` (with optional alignment colons).
    Escaped pipes (``\\|``) inside a cell do not split that cell.

    Returns a list of dicts, one per table found, each with:
      header_line: int — 1-based absolute line number of the header row
      headers: list[str] — stripped column headers
      rows: list[list[str]] — stripped cell values (excludes header + separator rows)
    """
    tables: list[dict] = []
    lines = body.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if "|" in line and i + 1 < len(lines):
            sep_line = lines[i + 1].strip()
            if _SEPARATOR_ROW_RE.match(sep_line):
                headers = [c.strip() for c in line.split("|")]
                headers = [h for h in headers if h]

                rows: list[list[str]] = []
                j = i + 2
                while j < len(lines):
                    row_line = lines[j].strip()
                    if not row_line or "|" not in row_line:
                        break
                    safe_line = row_line.replace("\\|", "\x00")
                    raw_cells = safe_line.split("|")
                    if raw_cells and not raw_cells[0].strip():
                        raw_cells = raw_cells[1:]
                    if raw_cells and not raw_cells[-1].strip():
                        raw_cells = raw_cells[:-1]
                    cells = [c.replace("\x00", "|").strip() for c in raw_cells]
                    rows.append(cells)
                    j += 1

                tables.append({
                    "header_line": i + body_offset + 1,
                    "headers": headers,
                    "rows": rows,
                })
                i = j
                continue
        i += 1
    return tables
