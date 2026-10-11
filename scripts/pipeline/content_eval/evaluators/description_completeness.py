"""Description completeness evaluator — detects empty description cells in reference tables."""

from __future__ import annotations

from typing import Any

from lib.markdown_tables import parse_markdown_tables as _parse_tables

from ..models import Finding, Page
from . import BaseEvaluator

# Column headers that indicate a description column (case-insensitive)
_DESC_HEADERS = {"description", "summary", "returns", "remarks"}

# Minimum data rows to evaluate a table (skip tiny tables)
_MIN_DATA_ROWS = 3

# Tables below this row count use absolute-count checks only (not percentage).
# This prevents grade instability where one cell change in a 3-4 row table
# swings a 67% → FAIL to 33% → no-finding.
_SMALL_TABLE_ROWS = 6

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

            # For small tables (< _SMALL_TABLE_ROWS), use absolute count
            # checks only — percentage thresholds are too volatile when one
            # cell change swings the result by 25-33%.
            if total < _SMALL_TABLE_ROWS:
                if empty >= _FAIL_EMPTY_MIN:
                    findings.append(Finding(
                        level="FAIL",
                        category="DC",
                        filepath=str(page.filepath),
                        line_no=table["header_line"],
                        message=f"Table has {empty}/{total} empty description cells — reference content incomplete",
                        suggestion="Populate description cells with meaningful text for each API member",
                        evaluator=self.name,
                    ))
                elif empty >= _WARN_EMPTY_MIN:
                    findings.append(Finding(
                        level="WARN",
                        category="DC",
                        filepath=str(page.filepath),
                        line_no=table["header_line"],
                        message=f"Table has {empty}/{total} empty description cells",
                        suggestion="Add descriptions for undocumented API members",
                        evaluator=self.name,
                    ))
            elif pct > _FAIL_EMPTY_PCT and empty >= _FAIL_EMPTY_MIN:
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
