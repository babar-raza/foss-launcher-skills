"""
format_table_handler.py — TC-06: Populate and update format support tables in content pages.

Handles FORMAT_ADDED, FORMAT_REMOVED, FORMAT_DIRECTION_CHANGED events from
format_delta.json. Also handles initial population from formats.json for
STUB pages (table header exists, 0 data rows) and MISSING pages.

Gold standard reference: content/docs.aspose.org/en/3d/python/developer-guide/format-support.md

Three page states:
  POPULATED  — table header + data rows present; use format_delta events only
  STUB       — table header present, 0 data rows; populate from formats.json
  MISSING    — no format-support.md at all; create page scaffold + populate

CLI:
    PYTHONPATH=scripts/pipeline python -m commands.content.format_table_handler 3d net
    PYTHONPATH=scripts/pipeline python -m commands.content.format_table_handler 3d net --dry-run
    PYTHONPATH=scripts/pipeline python -m commands.content.format_table_handler 3d net --execute
"""

from pathlib import Path
import sys

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

# ── Path constants ──────────────────────────────────────────────────────────

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
_REPO_ROOT = _DEFAULT_REPO_ROOT
_KNOWLEDGE_ROOT = _REPO_ROOT / "knowledge"
_CONTENT_ROOT = _REPO_ROOT / "content"


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Reconfigure module paths (used by tests)."""
    global _REPO_ROOT, _KNOWLEDGE_ROOT, _CONTENT_ROOT
    if repo_root is not None:
        _REPO_ROOT = Path(repo_root)
        _KNOWLEDGE_ROOT = _REPO_ROOT / "knowledge"
        _CONTENT_ROOT = _REPO_ROOT / "content"
    else:
        _REPO_ROOT = _DEFAULT_REPO_ROOT
        _KNOWLEDGE_ROOT = _DEFAULT_REPO_ROOT / "knowledge"
        _CONTENT_ROOT = _DEFAULT_REPO_ROOT / "content"


# ── Result constants ────────────────────────────────────────────────────────

R_POPULATED = "FORMAT_TABLE_POPULATED"
R_UPDATED = "FORMAT_TABLE_UPDATED"
R_CREATED = "FORMAT_PAGE_CREATED"
R_NOOP = "NOOP_ALREADY_CURRENT"
R_DRY_RUN = "DRY_RUN"
R_SKIPPED_LOCALE = "SKIPPED_LOCALE"
R_SKIPPED_PROTECTED = "SKIPPED_PROTECTED"
R_NO_FORMATS_JSON = "NO_FORMATS_JSON"
R_NO_FORMAT_DELTA = "NO_FORMAT_DELTA"

# Table header pattern — detect existing format table
_TABLE_HEADER_RE = re.compile(
    r"\|\s*Format\s*\|", re.IGNORECASE
)
_TABLE_SEPARATOR_RE = re.compile(r"^\|[-: |]+\|$")


# ── Format data helpers ─────────────────────────────────────────────────────

def _parse_formats_json(formats_path: Path) -> list[dict[str, str]]:
    """Parse formats.json (list of format records) into collapsed format rows.

    Each row: {name, ext, support, read, write}
    'support' is one of: 'both', 'import-only', 'export-only'
    """
    if not formats_path.is_file():
        return []

    records: list[dict] = json.loads(formats_path.read_text(encoding="utf-8"))

    # Collapse by format name; combine directions
    by_name: dict[str, set] = defaultdict(set)
    ext_hint: dict[str, str] = {}

    for rec in records:
        name = rec.get("format", "")
        if not name:
            continue
        direction = rec.get("direction", "")
        by_name[name].add(direction)

        # Extract extension hint from source file name
        f = rec.get("file", "")
        if f and name not in ext_hint:
            import re as _re
            m = _re.search(r"/([A-Za-z0-9]+)(Reader|Writer|Loader|Exporter|Importer|Saver)", f)
            if m:
                ext_hint[name] = m.group(1).lower()

    # Build canonical rows
    # Deduplicate: skip sub-variants that are just aliases (Ascii, BinaryLittleEndian for PLY etc.)
    # Keep only the canonical format name if it's a prefix variant
    canonical_names = set(by_name.keys())
    skip_names: set[str] = set()
    for name in canonical_names:
        ext = ext_hint.get(name, name.lower())
        # If another format maps to the same ext and has a shorter, simpler name, skip this one
        if ext in ext_hint.values():
            simpler = [n for n in canonical_names if ext_hint.get(n) == ext and n != name]
            if simpler:
                # Skip longer/more complex name variants (e.g. BinaryLittleEndian -> PLY)
                if len(name) > min(len(s) for s in simpler):
                    skip_names.add(name)

    rows = []
    for name in sorted(by_name.keys()):
        if name in skip_names:
            continue
        dirs = by_name[name]
        if "import" in dirs and "export" in dirs:
            support = "both"
            read, write = "Yes", "Yes"
        elif "import" in dirs:
            support = "import-only"
            read, write = "Yes", "No"
        elif "export" in dirs:
            support = "export-only"
            read, write = "No", "Yes"
        else:
            continue

        ext = ext_hint.get(name, name.lower())
        rows.append({"name": name, "ext": ext, "support": support, "read": read, "write": write})

    return rows


def _format_row(row: dict[str, str]) -> str:
    """Render a single markdown table row from a format record."""
    name = row["name"]
    ext = row["ext"]
    read = row["read"]
    write = row["write"]
    # Extension display
    if "." not in ext:
        ext_display = f"`.{ext}`"
    else:
        ext_display = f"`{ext}`"
    return f"| {name} | {ext_display} | {read} | {write} | — | — |"


# ── Page state detection ────────────────────────────────────────────────────

def _detect_page_state(page_path: Path) -> str:
    """Return 'POPULATED', 'STUB', or 'MISSING'."""
    if not page_path.is_file():
        return "MISSING"

    content = page_path.read_text(encoding="utf-8", errors="replace")

    # Find format table
    lines = content.splitlines()
    header_idx = None
    for i, line in enumerate(lines):
        if _TABLE_HEADER_RE.search(line) and "Read" in line and "Write" in line:
            header_idx = i
            break

    if header_idx is None:
        return "STUB"  # No table header at all — treat as STUB (will add table)

    # Check if there are data rows after the separator
    # Look for separator line (|---|---| pattern)
    sep_idx = None
    for i in range(header_idx + 1, min(header_idx + 3, len(lines))):
        if _TABLE_SEPARATOR_RE.match(lines[i].strip()):
            sep_idx = i
            break

    if sep_idx is None:
        return "STUB"

    # Count data rows
    data_rows = 0
    for i in range(sep_idx + 1, len(lines)):
        line = lines[i].strip()
        if not line.startswith("|"):
            break
        if "|" in line[1:]:
            data_rows += 1

    if data_rows == 0:
        return "STUB"
    return "POPULATED"


# ── Table operations ────────────────────────────────────────────────────────

_TABLE_HEADER = "| Format | Extension | Read | Write | Options class | Notes |"
_TABLE_SEP = "|--------|-----------|:----:|:-----:|---------------|-------|"


def _build_full_table(rows: list[dict[str, str]]) -> str:
    """Build a complete markdown format table from format rows."""
    lines = [_TABLE_HEADER, _TABLE_SEP]
    for row in rows:
        lines.append(_format_row(row))
    return "\n".join(lines)


def _insert_table_into_stub(content: str, rows: list[dict[str, str]]) -> str:
    """Insert format table rows into a STUB page (table header exists, 0 data rows)."""
    lines = content.splitlines(keepends=True)

    # Find the table header line
    header_idx = None
    for i, line in enumerate(lines):
        if _TABLE_HEADER_RE.search(line) and "Read" in line and "Write" in line:
            header_idx = i
            break

    if header_idx is None:
        # No table header — find a suitable location and insert full table
        return _insert_table_at_section(content, rows)

    # Replace the header and any existing separator with the complete table
    # Find end of the existing incomplete table
    end_idx = header_idx + 1
    for i in range(header_idx + 1, len(lines)):
        stripped = lines[i].strip()
        if stripped.startswith("|"):
            end_idx = i + 1
        elif stripped == "":
            end_idx = i
            break
        else:
            break

    new_table = _TABLE_HEADER + "\n" + _TABLE_SEP + "\n"
    for row in rows:
        new_table += _format_row(row) + "\n"

    result = "".join(lines[:header_idx]) + new_table + "".join(lines[end_idx:])
    return result


def _insert_table_at_section(content: str, rows: list[dict[str, str]]) -> str:
    """Insert a full format table after a '## Supported Formats' or '## Overview' heading."""
    table_text = _TABLE_HEADER + "\n" + _TABLE_SEP + "\n"
    for row in rows:
        table_text += _format_row(row) + "\n"

    # Look for a supported-formats or overview section
    for heading_pattern in [
        r"^##\s+Supported Formats",
        r"^##\s+Overview",
        r"^##\s+Format Support",
        r"^##",  # fallback: first H2
    ]:
        m = re.search(heading_pattern, content, re.MULTILINE)
        if m:
            insert_after = m.end()
            # Skip to end of the heading line
            newline = content.find("\n", insert_after)
            if newline == -1:
                newline = len(content)
            return content[: newline + 1] + "\n" + table_text + "\n" + content[newline + 1 :]

    # Fallback: append at end
    return content + "\n\n" + table_text


def _add_rows_to_table(content: str, rows_to_add: list[dict[str, str]]) -> str:
    """Add new format rows to an existing POPULATED table."""
    lines = content.splitlines(keepends=True)

    # Find table end
    header_idx = None
    for i, line in enumerate(lines):
        if _TABLE_HEADER_RE.search(line) and "Read" in line and "Write" in line:
            header_idx = i
            break

    if header_idx is None:
        return content

    # Find last data row of table
    last_row_idx = header_idx
    for i in range(header_idx + 1, len(lines)):
        stripped = lines[i].strip()
        if stripped.startswith("|"):
            last_row_idx = i
        else:
            break

    new_rows_text = ""
    for row in rows_to_add:
        new_rows_text += _format_row(row) + "\n"

    return "".join(lines[: last_row_idx + 1]) + new_rows_text + "".join(lines[last_row_idx + 1 :])


def _remove_rows_from_table(content: str, format_names: list[str]) -> tuple[str, list[str]]:
    """Remove rows for given format names from the table. Returns (new_content, removed_names)."""
    lines = content.splitlines(keepends=True)
    removed = []

    new_lines = []
    for line in lines:
        # Check if this is a table row for one of the removed formats
        if line.strip().startswith("|"):
            remove = False
            for name in format_names:
                # Match format name at start of table cell
                if re.match(r"\|\s*" + re.escape(name) + r"\s*\|", line.strip(), re.IGNORECASE):
                    removed.append(name)
                    remove = True
                    break
            if remove:
                continue
        new_lines.append(line)

    return "".join(new_lines), removed


def _update_row_direction(content: str, format_name: str, new_support: str) -> str:
    """Update the Read/Write columns for a specific format row."""
    if new_support == "both":
        read, write = "Yes", "Yes"
    elif new_support == "import-only":
        read, write = "Yes", "No"
    elif new_support == "export-only":
        read, write = "No", "Yes"
    else:
        return content

    lines = content.splitlines(keepends=True)
    new_lines = []
    for line in lines:
        if line.strip().startswith("|") and re.match(
            r"\|\s*" + re.escape(format_name) + r"\s*\|", line.strip(), re.IGNORECASE
        ):
            # Split table row and update Read/Write columns (0=Format, 1=Ext, 2=Read, 3=Write, ...)
            parts = line.strip().split("|")
            # parts[0] is empty (before first |), parts[1..] are cells, parts[-1] is empty
            if len(parts) >= 5:
                parts[3] = f" {read} "
                parts[4] = f" {write} "
                line = "|".join(parts) + "\n" if not line.endswith("\n") else "|".join(parts) + "\n"
        new_lines.append(line)
    return "".join(new_lines)


# ── MISSING page scaffold ──────────────────────────────────────────────────

def _scaffold_format_page(family: str, platform: str, rows: list[dict[str, str]]) -> str:
    """Generate a complete format-support.md page for a MISSING product."""
    family_display = family.upper() if len(family) <= 4 else family.title()
    platform_display = platform.upper() if len(platform) <= 4 else platform.title()

    table_text = _TABLE_HEADER + "\n" + _TABLE_SEP + "\n"
    for row in rows:
        table_text += _format_row(row) + "\n"

    return f"""\
---
title: "Format Support"
linktitle: "Format Support"
description: >-
  Supported file formats in Aspose.{family_display} FOSS for {platform_display}.
weight: 40
type: docs
provenance:
  content_origin: skill-generated
  last_mechanism: format-table-handler
  auto_updatable: true
  content_hash: ""
evidence:
  model_sha: ""
  model_version: ""
  claims: []
  apis: []
grade: ""
---

## Supported Formats

{table_text}

## See Also

- [Developer Guide](./)
"""


# ── English-only guard ─────────────────────────────────────────────────────

def _is_english_path(page_path: Path) -> bool:
    """Return True if page_path is an English content page."""
    path_str = str(page_path).replace("\\", "/")

    # Reject locale-suffixed filenames (blog style)
    if re.search(r"\.[a-z]{2}(?:-[a-z0-9]{2,4})?\.md$", page_path.name):
        return False

    # Require /en/ for directory-localized sites
    for site in ("docs.aspose.org", "kb.aspose.org", "reference.aspose.org", "products.aspose.org"):
        if site in path_str and f"/{site}/en/" not in path_str:
            return False

    return True


# ── Core handler ────────────────────────────────────────────────────────────

def handle_format_table(
    family: str,
    platform: str,
    *,
    dry_run: bool = True,
    format_delta_path: "Path | None" = None,
    formats_json_path: "Path | None" = None,
) -> dict[str, Any]:
    """Populate or update the format-support page for a product.

    Returns a summary dict.
    """
    summary: dict[str, Any] = {
        "family": family,
        "platform": platform,
        "dry_run": dry_run,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "page_state": "",
        "result": R_NOOP,
        "rows_added": 0,
        "rows_removed": 0,
        "rows_updated": 0,
        "prose_mentions": [],
        "error": "",
    }

    # 1. Load formats.json
    if formats_json_path is None:
        formats_json_path = _KNOWLEDGE_ROOT / family / platform / "merged" / "formats.json"
    if not formats_json_path.is_file():
        summary["result"] = R_NO_FORMATS_JSON
        return summary

    all_rows = _parse_formats_json(formats_json_path)

    # 2. Locate the format-support page
    page_path = _CONTENT_ROOT / "docs.aspose.org" / "en" / family / platform / "developer-guide" / "format-support.md"

    # 3. Detect page state
    state = _detect_page_state(page_path)
    summary["page_state"] = state

    if state == "MISSING":
        return _handle_missing(page_path, family, platform, all_rows, summary, dry_run=dry_run)

    # STUB or POPULATED
    if not _is_english_path(page_path):
        summary["result"] = R_SKIPPED_LOCALE
        return summary

    content = page_path.read_text(encoding="utf-8", errors="replace")

    if "auto_updatable: false" in content:
        summary["result"] = R_SKIPPED_PROTECTED
        return summary

    if state == "STUB":
        return _handle_stub(page_path, content, all_rows, summary, dry_run=dry_run)

    # POPULATED — use format_delta
    if format_delta_path is None:
        format_delta_path = _KNOWLEDGE_ROOT / family / platform / "merged" / "format_delta.json"
    if not format_delta_path.is_file():
        summary["result"] = R_NO_FORMAT_DELTA
        return summary

    return _handle_populated(page_path, content, all_rows, format_delta_path, summary, dry_run=dry_run)


def _handle_missing(
    page_path: Path,
    family: str,
    platform: str,
    rows: list[dict[str, str]],
    summary: dict[str, Any],
    *,
    dry_run: bool,
) -> dict[str, Any]:
    """Create a new format-support.md page from scratch."""
    if not rows:
        summary["error"] = "no format rows to populate"
        return summary

    new_content = _scaffold_format_page(family, platform, rows)
    summary["rows_added"] = len(rows)

    if dry_run:
        summary["result"] = R_DRY_RUN
        return summary

    page_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from lib.provenance import safe_content_write
        safe_content_write(page_path, new_content, mechanism="format-table-handler")
    except ImportError:
        page_path.write_text(new_content, encoding="utf-8")

    summary["result"] = R_CREATED
    return summary


def _handle_stub(
    page_path: Path,
    content: str,
    rows: list[dict[str, str]],
    summary: dict[str, Any],
    *,
    dry_run: bool,
) -> dict[str, Any]:
    """Populate a STUB page (has table header, no data rows)."""
    if not rows:
        summary["error"] = "no format rows to populate"
        return summary

    new_content = _insert_table_into_stub(content, rows)
    summary["rows_added"] = len(rows)

    if new_content == content:
        summary["result"] = R_NOOP
        return summary

    if dry_run:
        summary["result"] = R_DRY_RUN
        return summary

    try:
        from lib.provenance import safe_content_write
        safe_content_write(page_path, new_content, mechanism="format-table-handler")
    except ImportError:
        page_path.write_text(new_content, encoding="utf-8")

    summary["result"] = R_POPULATED
    return summary


def _handle_populated(
    page_path: Path,
    content: str,
    all_rows: list[dict[str, str]],
    format_delta_path: Path,
    summary: dict[str, Any],
    *,
    dry_run: bool,
) -> dict[str, Any]:
    """Update a POPULATED page using format_delta events only."""
    delta = json.loads(format_delta_path.read_text(encoding="utf-8"))

    formats_added = delta.get("formats_added", [])
    formats_removed = delta.get("formats_removed", [])
    formats_direction_changed = delta.get("formats_direction_changed", [])

    if not formats_added and not formats_removed and not formats_direction_changed:
        summary["result"] = R_NOOP
        return summary

    new_content = content

    # Add new rows
    if formats_added:
        row_lookup = {r["name"].lower(): r for r in all_rows}
        rows_to_add = []
        for fmt in formats_added:
            name = fmt.get("name", "")
            row = row_lookup.get(name.lower())
            if row:
                rows_to_add.append(row)
            else:
                # Build from delta data
                support = fmt.get("support", "both")
                read = "Yes" if support in ("both", "import-only") else "No"
                write = "Yes" if support in ("both", "export-only") else "No"
                rows_to_add.append({
                    "name": name,
                    "ext": fmt.get("ext", name.lower()),
                    "support": support,
                    "read": read,
                    "write": write,
                })
        if rows_to_add:
            new_content = _add_rows_to_table(new_content, rows_to_add)
            summary["rows_added"] = len(rows_to_add)

    # Remove rows
    if formats_removed:
        removed_names = [fmt.get("name", "") for fmt in formats_removed]
        new_content, actually_removed = _remove_rows_from_table(new_content, removed_names)
        summary["rows_removed"] = len(actually_removed)
        # Check prose for removed format mentions
        for name in actually_removed:
            if name.lower() in new_content.lower():
                summary["prose_mentions"].append(name)

    # Update direction
    if formats_direction_changed:
        for fmt in formats_direction_changed:
            name = fmt.get("name", "")
            new_support = fmt.get("new_support", "")
            if name and new_support:
                new_content = _update_row_direction(new_content, name, new_support)
                summary["rows_updated"] += 1

    if new_content == content:
        summary["result"] = R_NOOP
        return summary

    if dry_run:
        summary["result"] = R_DRY_RUN
        return summary

    try:
        from lib.provenance import safe_content_write
        safe_content_write(page_path, new_content, mechanism="format-table-handler")
    except ImportError:
        page_path.write_text(new_content, encoding="utf-8")

    summary["result"] = R_UPDATED
    return summary


# ── CLI ─────────────────────────────────────────────────────────────────────

def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        prog="format_table_handler",
        description="Populate or update format support tables in content pages.",
    )
    parser.add_argument("family", nargs="?", help="Product family (e.g. 3d)")
    parser.add_argument("platform", nargs="?", help="Platform (e.g. net)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Preview changes without writing (default)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Write changes to disk",
    )
    parser.add_argument(
        "--format-delta",
        metavar="PATH",
        help="Override path to format_delta.json",
    )
    args = parser.parse_args(argv)

    if not args.family or not args.platform:
        parser.print_help()
        return 1

    dry_run = not args.execute
    format_delta_path = Path(args.format_delta) if args.format_delta else None

    summary = handle_format_table(
        args.family,
        args.platform,
        dry_run=dry_run,
        format_delta_path=format_delta_path,
    )

    mode = "DRY-RUN" if dry_run else "EXECUTE"
    print(f"\nformat_table_handler [{mode}] {args.family}/{args.platform}")
    print(f"  page_state:    {summary['page_state']}")
    print(f"  result:        {summary['result']}")
    print(f"  rows_added:    {summary['rows_added']}")
    print(f"  rows_removed:  {summary['rows_removed']}")
    print(f"  rows_updated:  {summary['rows_updated']}")
    if summary.get("error"):
        print(f"  error:         {summary['error']}")
    if summary.get("prose_mentions"):
        print(f"  prose_mentions (HUMAN_REVIEW): {summary['prose_mentions']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
