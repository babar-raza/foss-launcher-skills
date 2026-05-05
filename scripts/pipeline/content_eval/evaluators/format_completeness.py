"""Format completeness evaluator — checks format support tables against formats.json.

This evaluator fires only on pages that contain an explicit format support table
(detected by markdown table headers with columns like Format/Extension/Import/Export).

What it checks:
- **Phantom formats** (FAIL/FM): A format name appears in the page table but has
  no matching entry in formats.json after normalization.  Indicates a stale or
  fabricated format reference.
- **Table incompleteness** (WARN/FM): More than 20% of formats.json entries are
  absent from the page table on feature/overview pages in blog or docs subdomains.
  Indicates that the table is out-of-date relative to the product's known format set.

What it does NOT check (deferred to format_truth.py):
- Direction mismatches (claiming export when knowledge says import-only)
- Unknown format extensions mentioned in prose or code blocks
- Detect-only mismatches
- Products pages format unsupported claims

Category code: FM (distinct from FT used by format_truth.py)
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator

try:
    import sys as _sys
    from pathlib import Path as _Path
    _scripts = _Path(__file__).resolve().parent.parent.parent.parent
    if str(_scripts) not in _sys.path:
        _sys.path.insert(0, str(_scripts))
    from config_loader import resolve_knowledge_root as _rkr
    KNOWLEDGE_ROOT = _rkr()
except Exception:
    KNOWLEDGE_ROOT = Path("knowledge")

# Table header patterns that indicate a format support table is present.
# Match lines like:
#   | Format | Extension |
#   | Format | Import | Export |
#   | Format | Read | Write |
#   | Extension | Import | Export |
# Case-insensitive; leading/trailing whitespace/pipes tolerated.
_TABLE_HEADER_RE = re.compile(
    r"^\s*\|\s*(?!`)[^`|]*\b(?:format|extension)\b[^`|]*\|.*\b(?:extension|import|export|read|write)\b.*\|",
    re.IGNORECASE,
)

# Separator row pattern (e.g.  | --- | --- | --- |)
_TABLE_SEP_RE = re.compile(r"^\s*\|[\s\-|:]+\|?\s*$")

# Words that are header/separator tokens — skip rows whose sole non-empty cell
# is one of these words.
_SKIP_WORDS: frozenset[str] = frozenset({
    "format", "extension", "ext", "import", "export", "read", "write",
    "yes", "no", "true", "false", "---", "support", "supported",
})


def _normalize(name: str) -> str:
    """Normalise a format name for comparison.

    Lowercases, strips leading dots, trailing underscores, trailing asterisks,
    and all internal underscores so that e.g. 'PDF_', '.PDF', 'pdf*' all
    compare equal to 'pdf'.
    """
    n = name.strip().lower()
    n = n.replace(" ", "")
    n = n.lstrip(".")
    n = n.rstrip("_*")
    n = n.replace("_", "")
    return n


# Maps enum-style canonical keys (after normalization) to their common
# file-extension / display-name equivalents so that content using the
# human-readable name (e.g. "3MF") still matches the knowledge key
# (e.g. "ThreeMf" → normalized "threemf").
_FORMAT_ALIASES: dict[str, str] = {
    "threemf": "3mf",
    "microsoft3mf": "3mf",
    "excelopenxml": "xlsx",   # "Excel Open XML" display name → formats.json key
    "xlsx": "excelopenxml",   # reverse alias for safety
}


def _load_formats(family: str, platform: str) -> dict[str, str]:
    """Load formats.json and return a dict of normalized_name -> direction.

    Returns an empty dict if the file is absent, unreadable, or has fewer
    than 2 entries (too little data to be reliable).

    Handles both ``name`` and ``format``/``ext`` key variants.
    Direction is inferred from explicit ``direction`` field or from boolean
    ``import``/``export`` fields.
    """
    path = KNOWLEDGE_ROOT / family / platform / "merged" / "formats.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, TypeError, OSError):
        return {}

    if not isinstance(data, list) or len(data) < 2:
        return {}

    result: dict[str, str] = {}
    for entry in data:
        raw_key = (
            entry.get("name")
            or entry.get("format")
            or entry.get("ext")
            or ""
        ).lstrip(".")
        if not raw_key:
            continue
        norm = _normalize(raw_key)
        if not norm:
            continue

        direction = (entry.get("direction") or entry.get("support") or "").lower()
        if not direction:
            can_import = bool(entry.get("import", False))
            can_export = bool(entry.get("export", False))
            if can_import and can_export:
                direction = "both"
            elif can_import:
                direction = "import"
            elif can_export:
                direction = "export"
            else:
                direction = "none"

        # If the same normalised key appears with conflicting directions, promote to "both"
        existing = result.get(norm)
        if existing and existing != direction:
            result[norm] = "both"
        else:
            result[norm] = direction

    # Register aliases so human-readable display names match enum canonical keys.
    for canon, alias in _FORMAT_ALIASES.items():
        if canon in result and alias not in result:
            result[alias] = result[canon]

    return result


def _find_format_table(prose_lines: list[tuple[int, str]]) -> list[tuple[int, str]] | None:
    """Return the rows of the FIRST format support table found in prose_lines.

    Returns None if no such table is detected.
    Each element is (line_no, raw_line).
    """
    in_table = False
    header_line_no: int = -1
    rows: list[tuple[int, str]] = []

    for line_no, line_text in prose_lines:
        if not in_table:
            if _TABLE_HEADER_RE.match(line_text):
                in_table = True
                header_line_no = line_no
                rows = [(line_no, line_text)]
        else:
            # Continue collecting as long as the line looks like a table row
            stripped = line_text.strip()
            if stripped.startswith("|") or _TABLE_SEP_RE.match(line_text):
                rows.append((line_no, line_text))
            else:
                # Table ended — we have what we need
                break

    if not in_table or len(rows) < 1:
        return None
    return rows


def _parse_table_format_names(rows: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Extract (line_no, normalised_format_name) from table rows.

    Only the first data column (column 0 after splitting on '|') is used, as
    that conventionally holds the format name or extension.

    Skips header and separator rows.
    """
    result: list[tuple[int, str]] = []
    for line_no, line_text in rows:
        # Skip separator rows
        if _TABLE_SEP_RE.match(line_text):
            continue

        cells = [c.strip() for c in line_text.strip().strip("|").split("|")]
        if not cells:
            continue

        raw = cells[0].strip()
        if not raw:
            continue

        norm = _normalize(raw)

        # Skip if it maps to a known header/skip word or is too short
        if norm in _SKIP_WORDS:
            continue
        if len(norm) <= 2:
            continue

        result.append((line_no, norm))

    return result


def _is_feature_page(page: Page) -> bool:
    """Return True if this page's role/slug suggests a features/overview page
    in a subdomain where table completeness matters (docs or blog only).
    """
    if page.subdomain not in ("docs", "blog"):
        return False

    # Check page_role attribute if present
    page_role = getattr(page, "page_role", None)
    if page_role in ("features", "overview", "key-features"):
        return True

    # Fallback: inspect the slug/filepath
    path_str = str(page.filepath).lower().replace("\\", "/")
    for keyword in ("feature", "overview", "key-feature", "supported-format", "supported_format"):
        if keyword in path_str:
            return True

    # Check frontmatter slug/title
    if isinstance(page.frontmatter, dict):
        slug = str(page.frontmatter.get("slug", "") or "").lower()
        title = str(page.frontmatter.get("title", "") or "").lower()
        for keyword in ("feature", "overview", "supported format"):
            if keyword in slug or keyword in title:
                return True

    return False


class FormatCompletenessEvaluator(BaseEvaluator):
    """Check format support tables for phantom entries and missing formats.

    Fires only on pages that contain a markdown format support table.
    Does NOT duplicate format_truth.py's direction-mismatch or prose-scanning
    checks — this evaluator is exclusively concerned with table coverage.
    """

    name = "format_completeness"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        if not page.family or not page.platform:
            return []

        # --- Locate the format table in prose ---
        table_rows = _find_format_table(page.prose_lines)
        if table_rows is None:
            return []  # No format table on this page

        # --- Load formats.json ---
        known_formats = _load_formats(page.family, page.platform)
        if not known_formats:
            return []  # No knowledge available — skip silently

        # --- Parse format names from the table ---
        table_entries = _parse_table_format_names(table_rows)
        if not table_entries:
            return []

        table_norm_set: set[str] = {norm for _, norm in table_entries}

        findings: list[Finding] = []

        # ---------------------------------------------------------------
        # Check 1 — Phantom formats (FAIL)
        # A format name in the table that has no match in formats.json
        # ---------------------------------------------------------------
        reported_phantoms: set[str] = set()
        for line_no, norm in table_entries:
            if norm in reported_phantoms:
                continue
            if norm not in known_formats:
                reported_phantoms.add(norm)
                findings.append(Finding(
                    level="FAIL",
                    category="FM",
                    filepath=str(page.filepath),
                    line_no=line_no,
                    message=(
                        f"Format '{norm.upper()}' appears in the page table but "
                        f"has no matching entry in formats.json"
                    ),
                    suggestion=(
                        f"Verify '{norm.upper()}' is a real supported format for "
                        f"{page.family}/{page.platform}, or remove it from the table. "
                        f"If it is supported, add it to formats.json."
                    ),
                    evaluator=self.name,
                ))

        # ---------------------------------------------------------------
        # Check 2 — Table incompleteness (WARN)
        # More than 20% of formats.json entries absent from the table,
        # but only on feature/overview pages in docs or blog subdomains,
        # and only when the table has at least 3 data rows.
        # ---------------------------------------------------------------
        if len(table_entries) >= 3 and _is_feature_page(page):
            known_set = set(known_formats.keys())
            missing = known_set - table_norm_set
            if known_set:
                missing_ratio = len(missing) / len(known_set)
                if missing_ratio > 0.20:
                    missing_display = ", ".join(
                        sorted(m.upper() for m in missing)[:15]
                    )
                    if len(missing) > 15:
                        missing_display += f", … ({len(missing) - 15} more)"
                    findings.append(Finding(
                        level="WARN",
                        category="FM",
                        filepath=str(page.filepath),
                        line_no=table_rows[0][0],
                        message=(
                            f"Format table is missing {len(missing)} of "
                            f"{len(known_set)} known formats "
                            f"({missing_ratio:.0%} absent): {missing_display}"
                        ),
                        suggestion=(
                            "Update the format support table to include all formats "
                            "listed in formats.json, or confirm the omissions are "
                            "intentional and annotate the table accordingly."
                        ),
                        evaluator=self.name,
                    ))

        return findings
