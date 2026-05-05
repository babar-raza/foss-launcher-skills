"""Description completeness evaluator — detects empty description cells in reference tables."""

from __future__ import annotations

import re
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator

# Column headers that indicate a description column (case-insensitive)
_DESC_HEADERS = {"description", "summary", "returns", "remarks"}

# Minimum data rows to evaluate a table (skip tiny tables)
_MIN_DATA_ROWS = 3

# Thresholds — tightened from 70/40 to 50/25 to catch majority-empty tables sooner.
_FAIL_EMPTY_PCT = 50  # >50% empty → FAIL
_WARN_EMPTY_PCT = 25  # >25% empty → WARN

# Minimum chars for a cell to count as "populated"
_MIN_CELL_LEN = 6

# Minimum absolute empty-cell count before the percentage thresholds apply.
# Lowered from 5/2 to 3/2 so that small-but-sparse tables (≥3 empty cells)
# still receive FAIL when the percentage threshold is met.
_FAIL_EMPTY_MIN = 3   # require ≥3 empty cells to fire FAIL
_WARN_EMPTY_MIN = 2   # require ≥2 empty cells to fire WARN


def _parse_tables(body: str, body_offset: int) -> list[dict]:
    """Parse Markdown tables from body text.

    Returns list of dicts with keys:
      header_line: int (1-based absolute line number)
      headers: list[str] (stripped column headers)
      rows: list[list[str]] (stripped cell values, excluding header + separator)
    """
    tables: list[dict] = []
    lines = body.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # Detect table start: line with pipes
        if "|" in line and i + 1 < len(lines):
            sep_line = lines[i + 1].strip()
            # Separator row: |---|---|  or  | --- | --- |
            if re.match(r"^\|[\s:]*-+[\s:]*(\|[\s:]*-+[\s:]*)*\|?$", sep_line):
                # Parse header
                headers = [c.strip() for c in line.split("|")]
                headers = [h for h in headers if h]  # remove empty from leading/trailing |

                # Collect data rows
                rows: list[list[str]] = []
                j = i + 2
                while j < len(lines):
                    row_line = lines[j].strip()
                    if not row_line or "|" not in row_line:
                        break
                    # Replace escaped pipes (\|) with a placeholder before splitting
                    # so that type unions like `str \| None` don't misalign columns.
                    safe_line = row_line.replace("\\|", "\x00")
                    # Rebuild: split on | gives ['', 'a', 'b', ''] for |a|b|
                    raw_cells = safe_line.split("|")
                    if raw_cells and not raw_cells[0].strip():
                        raw_cells = raw_cells[1:]
                    if raw_cells and not raw_cells[-1].strip():
                        raw_cells = raw_cells[:-1]
                    cells = [c.replace("\x00", "|").strip() for c in raw_cells]
                    rows.append(cells)
                    j += 1

                tables.append({
                    "header_line": i + body_offset + 1,  # 1-based
                    "headers": headers,
                    "rows": rows,
                })
                i = j
                continue
        i += 1
    return tables


class DescriptionCompletenessEvaluator(BaseEvaluator):
    """Detects reference pages with empty description/summary cells in tables.

    Only runs on reference pages. Checks tables for columns named
    "Description", "Summary", "Returns", or "Remarks" and flags when
    a high percentage of those cells are empty.
    """

    name = "description_completeness"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        findings: list[Finding] = []

        # Only evaluate reference pages
        if page.subdomain != "reference":
            return findings

        # Skip retired pages — they are snapshots and may intentionally lack descriptions
        if page.frontmatter.get("retired_at"):
            return findings

        # Skip dc_exempt pages explicitly opted out of description completeness checks
        if page.frontmatter.get("dc_exempt"):
            return findings

        # Skip enum-declaration pages — enum member names ARE the documentation.
        # e.g. XYZ, NOT_DEFINED, ISOMETRIC_BOTTOM_DOWN are self-documenting;
        # requiring description cells for enum values produces false positives.
        categories = page.frontmatter.get("categories", [])
        if isinstance(categories, list) and "Enum" in categories:
            return findings

        tables = _parse_tables(page.body, page.body_offset)

        for table in tables:
            headers_lower = [h.lower() for h in table["headers"]]

            # Find description column index — prefer specific description headers
            # over "returns" so that tables with both a Returns and a Description
            # column are evaluated on the Description column.
            _HIGH_PRIO = {"description", "summary", "remarks"}
            _LOW_PRIO = {"returns"}
            desc_idx = None
            low_prio_idx = None
            for idx, h in enumerate(headers_lower):
                if h in _HIGH_PRIO:
                    desc_idx = idx
                    break
                if h in _LOW_PRIO and low_prio_idx is None:
                    low_prio_idx = idx
            if desc_idx is None:
                desc_idx = low_prio_idx

            if desc_idx is None:
                continue

            rows = table["rows"]
            if len(rows) < _MIN_DATA_ROWS:
                continue

            # Count empty vs populated description cells
            total = 0
            empty = 0
            for row in rows:
                if desc_idx < len(row):
                    total += 1
                    if len(row[desc_idx]) < _MIN_CELL_LEN:
                        empty += 1

            if total == 0:
                continue

            pct = int(100 * empty / total)

            if pct > _FAIL_EMPTY_PCT and empty >= _FAIL_EMPTY_MIN:
                findings.append(Finding(
                    level="FAIL",
                    category="DC",
                    filepath=str(page.filepath),
                    line_no=table["header_line"],
                    message=f"Table has {pct}% empty description cells ({empty}/{total}) — reference content incomplete",
                    suggestion="Populate description cells with meaningful text for each API member",
                    evaluator=self.name,
                ))
            elif pct > _WARN_EMPTY_PCT and empty >= _WARN_EMPTY_MIN:
                findings.append(Finding(
                    level="WARN",
                    category="DC",
                    filepath=str(page.filepath),
                    line_no=table["header_line"],
                    message=f"Table has {pct}% empty description cells ({empty}/{total})",
                    suggestion="Add descriptions for undocumented API members",
                    evaluator=self.name,
                ))

        return findings
