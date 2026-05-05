"""report_extract.py -- Deterministic extractor for open/unresolved items from markdown reports.

Reads markdown report files (typically in reports/) and outputs structured
JSON of open/unresolved items. Part of the backlog harvest system: report
sections like "Not Completed", "Next Steps Required", "What still blocks"
are parsed and each actionable item is emitted with confidence, category
suggestion, and a stable content hash for deduplication.

Usage (CLI):
  # Human-readable summary of open items
  python scripts/pipeline/report_extract.py reports/forensic-pass1/sprint-summary.md

  # JSON output for downstream tooling
  python scripts/pipeline/report_extract.py "reports/*.md" --json

  # Count-only mode (path: count)
  python scripts/pipeline/report_extract.py "reports/**/*.md" --count-only

  # Filter by minimum confidence
  python scripts/pipeline/report_extract.py reports/ --json --min-confidence 0.9

Usage (Python import):
  from report_extract import parse_report, OpenItem

  items = parse_report("reports/forensic-pass1/sprint-summary.md")
  for item in items:
      print(f"[{item.item_type}] {item.title} (conf={item.confidence})")
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import re
import string
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

# ---------------------------------------------------------------------------
# Repo root resolution (matches session_ledger.py pattern)
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _repo_rel(path: str | Path) -> str:
    """Return repo-relative path string (forward slashes)."""
    try:
        return str(Path(path).resolve().relative_to(_REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class SectionPattern:
    """Describes a report section that may contain open items."""

    regex: str
    item_type: str
    base_confidence: float
    suggested_priority: str
    content_parser: str  # "table_or_list" | "numbered_list" | "bullet_list" | "status_scan"


@dataclass(frozen=True, slots=True)
class OpenItem:
    """A single open/unresolved item extracted from a report."""

    title: str               # First line, truncated to 120 chars
    source_path: str          # Repo-relative path to originating report
    source_section: str       # H2/H3 header name
    source_line: int          # Line number (1-based)
    item_type: str            # not_completed | next_step | deferred | not_started | human_action | blocker | not_proven | escalated
    confidence: float         # 0.0-1.0
    raw_text: str             # Full original text
    context: str              # Surrounding paragraph/table row
    suggested_category: str   # C | S | T | G | K | H
    suggested_priority: str   # P1 | P2 | P3
    item_hash: str            # SHA-256 of normalized(source_path + section_key + title), 16-char hex


# ---------------------------------------------------------------------------
# Section pattern registry (11 groups)
# ---------------------------------------------------------------------------

_SECTION_PATTERNS: list[SectionPattern] = [
    # NOT_COMPLETED
    SectionPattern(
        regex=r"^#{2,3}\s+(?:Not\s+Completed|Incomplete)\s*$",
        item_type="not_completed",
        base_confidence=0.95,
        suggested_priority="P1",
        content_parser="table_or_list",
    ),
    # NEXT_STEPS
    SectionPattern(
        regex=r"^#{2,3}\s+(?:Next\s+Steps(?:\s+Required)?|What.*next)\s*$",
        item_type="next_step",
        base_confidence=0.95,
        suggested_priority="P1",
        content_parser="numbered_list",
    ),
    # HUMAN_ACTION
    SectionPattern(
        regex=r"^#{2,3}\s+Required\s+[Hh]uman\s+[Aa]ctions?\s*$",
        item_type="human_action",
        base_confidence=0.95,
        suggested_priority="P1",
        content_parser="numbered_list",
    ),
    # BLOCKERS
    SectionPattern(
        regex=r"^#{2,3}\s+(?:What\s+still\s+blocks.*|Blockers?|Blocked)\s*$",
        item_type="blocker",
        base_confidence=0.90,
        suggested_priority="P1",
        content_parser="numbered_list",
    ),
    # NOT_PROVEN
    SectionPattern(
        regex=r"^#{2,3}\s+Not\s+proven\s*$",
        item_type="not_proven",
        base_confidence=0.85,
        suggested_priority="P2",
        content_parser="numbered_list",
    ),
    # ESCALATED
    SectionPattern(
        regex=r"^#{2,3}\s+Files\s+Escalated\s*$",
        item_type="escalated",
        base_confidence=0.85,
        suggested_priority="P2",
        content_parser="bullet_list",
    ),
    # REMAINING
    SectionPattern(
        regex=r"^#{2,3}\s+(?:Remaining(?:\s+follow-ups|\s+gaps)?)\s*$",
        item_type="next_step",
        base_confidence=0.90,
        suggested_priority="P2",
        content_parser="numbered_list",
    ),
    # FUTURE_WORK
    SectionPattern(
        regex=r"^#{2,3}\s+(?:Future\s+[Ww]ork|Known\s+limitations)\s*$",
        item_type="deferred",
        base_confidence=0.85,
        suggested_priority="P3",
        content_parser="numbered_list",
    ),
    # OPEN_WORK
    SectionPattern(
        regex=r"^#{2,3}\s+(?:Open\s+work|Open\s+items)\s*$",
        item_type="next_step",
        base_confidence=0.90,
        suggested_priority="P2",
        content_parser="bullet_list",
    ),
]

# Status-scan patterns are not tied to sections; they scan all lines.
_STATUS_SCAN_PATTERNS: list[SectionPattern] = [
    # DEFERRED
    SectionPattern(
        regex=r"(?:DEFERRED|Deferred|⚠️\s*DEFERRED)",
        item_type="deferred",
        base_confidence=0.90,
        suggested_priority="P3",
        content_parser="status_scan",
    ),
    # NOT_STARTED
    SectionPattern(
        regex=r"(?:NOT\s+STARTED|Not\s+[Ss]tarted)",
        item_type="not_started",
        base_confidence=0.90,
        suggested_priority="P2",
        content_parser="status_scan",
    ),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_COMPLETED_CHECKBOX = re.compile(r"\[x\]|✅")

# ALL-CAPS status words are unambiguous completion markers.
_COMPLETED_ALLCAPS = re.compile(
    r"\b(?:FIXED|DONE|RESOLVED|VERIFIED|APPROVED)\b"
)

# Mixed-case variants require explicit status-like context: the status word
# must be the first substantive content in a table cell (after |) or after
# a colon, optionally preceded by ✅.  Avoids "Fixed English files" false positive.
_COMPLETED_STATUS_CONTEXT = re.compile(
    r"(?:(?:^|\|)\s*(?:✅\s*)?)(?:Fixed|Done|Resolved|Verified|Approved|Pass(?:ed)?)\s*(?:\||$)",
    re.MULTILINE,
)


def _is_completed(text: str) -> bool:
    """Return True if text contains a completion marker.

    Uses strict matching to avoid false positives:
    - [x] and ✅ are always completion markers.
    - ALL-CAPS words (FIXED, DONE, etc.) are completion markers unless
      preceded by 'not'.
    - Mixed-case words require status-like context (first word in a table
      cell or after a colon) to match.
    """
    # Checkbox / emoji — unambiguous
    if _COMPLETED_CHECKBOX.search(text):
        return True
    # ALL-CAPS status words (with negation guard)
    for m in _COMPLETED_ALLCAPS.finditer(text):
        start = m.start()
        prefix = text[max(0, start - 5):start].lower().rstrip()
        if prefix.endswith("not"):
            continue
        return True
    # Mixed-case with strict status context
    if _COMPLETED_STATUS_CONTEXT.search(text):
        return True
    return False


_PUNCT_TABLE = str.maketrans("", "", string.punctuation)


def _normalize(text: str) -> str:
    """Lowercase, strip whitespace, remove punctuation (for hashing)."""
    return text.lower().translate(_PUNCT_TABLE).strip()


def _compute_item_hash(source_path: str, section_key: str, title: str) -> str:
    """SHA-256 of '{source_path}::{section_key}::{normalize(title)}', first 16 hex chars."""
    payload = f"{source_path}::{section_key}::{_normalize(title)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


_CATEGORY_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?:script|extraction|pipeline|CLI|tool|runner)", re.IGNORECASE), "S"),
    (re.compile(r"(?:evaluator|grade|grading|heal|threshold)", re.IGNORECASE), "S"),
    (re.compile(r"(?:content|page|format|claim|overclaim)", re.IGNORECASE), "C"),
    (re.compile(r"(?:test|coverage|regression|assert)", re.IGNORECASE), "T"),
    (re.compile(r"(?:knowledge|api_surface|formats\.json)", re.IGNORECASE), "K"),
    (re.compile(r"(?:AGENTS\.md|policy|skill|hook)", re.IGNORECASE), "G"),
]


def _suggest_category(text: str) -> str:
    """Suggest a backlog category from text content."""
    for pattern, category in _CATEGORY_RULES:
        if pattern.search(text):
            return category
    return "H"


def _truncate(text: str, limit: int = 120) -> str:
    """Truncate text to limit characters."""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit - 3] + "..."


# ---------------------------------------------------------------------------
# Sub-parsers
# ---------------------------------------------------------------------------

def _extract_section_lines(lines: list[str], start: int) -> tuple[list[tuple[int, str]], str]:
    """Extract lines belonging to a section starting at `start`.

    Returns (list of (line_number, text), section_header_text).
    A new ## or ### header (or end-of-file) ends the section.
    """
    header = lines[start].strip().lstrip("#").strip()
    section_lines: list[tuple[int, str]] = []
    for i in range(start + 1, len(lines)):
        line = lines[i]
        if re.match(r"^#{2,3}\s+", line):
            break
        section_lines.append((i + 1, line))  # 1-based line numbers
    return section_lines, header


def _parse_table_or_list(
    section_lines: list[tuple[int, str]],
    source_path: str,
    section_header: str,
    pattern: SectionPattern,
) -> list[OpenItem]:
    """Parse a section that may contain a markdown table or a bullet/numbered list."""
    items: list[OpenItem] = []

    # Detect table: look for |---|---| separator
    has_table = any(re.match(r"\s*\|[-:| ]+\|\s*$", line) for _, line in section_lines)

    if has_table:
        for line_num, line in section_lines:
            # Skip separator rows and header rows
            if re.match(r"\s*\|[-:| ]+\|\s*$", line):
                continue
            if "|" not in line:
                continue
            cells = [c.strip() for c in line.split("|")]
            cells = [c for c in cells if c]  # Remove empty from leading/trailing |
            if not cells:
                continue
            raw_text = line.strip()
            if _is_completed(raw_text):
                continue
            # First meaningful column as title
            title = _truncate(cells[0])
            # Skip the header row (heuristic: first row before separator)
            if title.lower() in ("item", "file", "gap", "skill", "status", "test case", "metric", "dimension"):
                continue
            items.append(OpenItem(
                title=title,
                source_path=source_path,
                source_section=section_header,
                source_line=line_num,
                item_type=pattern.item_type,
                confidence=pattern.base_confidence,
                raw_text=raw_text,
                context=raw_text,
                suggested_category=_suggest_category(raw_text),
                suggested_priority=pattern.suggested_priority,
                item_hash=_compute_item_hash(source_path, section_header, title),
            ))
    else:
        # Fall through to bullet/numbered list parsing
        items.extend(_parse_bullet_list(section_lines, source_path, section_header, pattern))
        items.extend(_parse_numbered_list(section_lines, source_path, section_header, pattern))

    return items


def _parse_numbered_list(
    section_lines: list[tuple[int, str]],
    source_path: str,
    section_header: str,
    pattern: SectionPattern,
) -> list[OpenItem]:
    """Parse numbered list items (1., 2., etc.)."""
    items: list[OpenItem] = []
    current_item_lines: list[str] = []
    current_line_num = 0

    def _flush() -> None:
        if not current_item_lines:
            return
        raw = "\n".join(current_item_lines)
        if _is_completed(raw):
            return
        # Strip the leading number+dot
        first = re.sub(r"^\d+\.\s*", "", current_item_lines[0]).strip()
        title = _truncate(first)
        if not title:
            return
        items.append(OpenItem(
            title=title,
            source_path=source_path,
            source_section=section_header,
            source_line=current_line_num,
            item_type=pattern.item_type,
            confidence=pattern.base_confidence,
            raw_text=raw.strip(),
            context=raw.strip(),
            suggested_category=_suggest_category(raw),
            suggested_priority=pattern.suggested_priority,
            item_hash=_compute_item_hash(source_path, section_header, title),
        ))

    for line_num, line in section_lines:
        stripped = line.strip()
        if re.match(r"^\d+\.\s+", stripped):
            _flush()
            current_item_lines = [stripped]
            current_line_num = line_num
        elif current_item_lines and stripped:
            # Continuation line
            current_item_lines.append(stripped)

    _flush()
    return items


def _parse_bullet_list(
    section_lines: list[tuple[int, str]],
    source_path: str,
    section_header: str,
    pattern: SectionPattern,
) -> list[OpenItem]:
    """Parse bullet list items (- or * prefixed)."""
    items: list[OpenItem] = []

    for line_num, line in section_lines:
        stripped = line.strip()
        m = re.match(r"^[-*]\s+(.+)$", stripped)
        if not m:
            continue
        raw = stripped
        if _is_completed(raw):
            continue
        content = m.group(1).strip()
        title = _truncate(content)
        if not title:
            continue
        items.append(OpenItem(
            title=title,
            source_path=source_path,
            source_section=section_header,
            source_line=line_num,
            item_type=pattern.item_type,
            confidence=pattern.base_confidence,
            raw_text=raw,
            context=raw,
            suggested_category=_suggest_category(raw),
            suggested_priority=pattern.suggested_priority,
            item_hash=_compute_item_hash(source_path, section_header, title),
        ))

    return items


def _find_current_section(lines: list[str], line_idx: int) -> str:
    """Walk backwards from line_idx to find the nearest ## or ### header."""
    for i in range(line_idx, -1, -1):
        m = re.match(r"^#{2,3}\s+(.+)", lines[i])
        if m:
            return m.group(1).strip()
    return "(unknown section)"


def _find_nearest_heading(lines: list[str], line_idx: int, max_levels: int = 4) -> str | None:
    """Walk backwards to find the nearest heading up to max_levels deep (##, ###, ####)."""
    pattern = r"^#{2," + str(max_levels) + r"}\s+(.+)"
    for i in range(line_idx, -1, -1):
        m = re.match(pattern, lines[i])
        if m:
            return m.group(1).strip()
    return None


def _parse_status_scan(
    lines: list[str],
    source_path: str,
    pattern: SectionPattern,
) -> list[OpenItem]:
    """Scan all lines for inline status markers (DEFERRED, NOT STARTED).

    Skips summary/metric table rows (e.g. '| Gaps Deferred | 1 |') and
    uses the nearest H3/H4 heading as the title when the marker line itself
    contains only status boilerplate.
    """
    items: list[OpenItem] = []
    seen_hashes: set[str] = set()

    for i, line in enumerate(lines):
        if not re.search(pattern.regex, line):
            continue
        raw = line.strip()
        if _is_completed(raw):
            continue

        # Skip summary table rows: if line is a table row where all non-status
        # cells are short numbers or metric labels, it's a summary — not an item.
        if "|" in raw:
            cells = [c.strip() for c in raw.split("|")]
            cells = [c for c in cells if c]
            # Heuristic: if any cell is purely numeric or the row has exactly
            # 2 cells (label + count), treat as a summary row.
            non_status_cells = [
                c for c in cells
                if not re.search(pattern.regex, c)
            ]
            if all(re.match(r"^\d+$", c) for c in non_status_cells if c):
                continue
            title = _truncate(cells[0]) if cells else _truncate(raw)
        else:
            # Strip the status marker and boilerplate
            cleaned = re.sub(pattern.regex, "", raw).strip()
            cleaned = re.sub(r"^\*\*Status\*\*\s*:?\s*", "", cleaned).strip()
            cleaned = cleaned.strip(":").strip("-").strip()
            title = _truncate(cleaned) if cleaned else None

        # If no meaningful title from the line itself, use the nearest heading
        if not title or len(title) < 5:
            heading = _find_nearest_heading(lines, i, max_levels=4)
            if heading:
                title = _truncate(heading)
            elif not title:
                continue

        section_header = _find_current_section(lines, i)
        item_hash = _compute_item_hash(source_path, section_header, title)

        if item_hash in seen_hashes:
            continue
        seen_hashes.add(item_hash)

        items.append(OpenItem(
            title=title,
            source_path=source_path,
            source_section=section_header,
            source_line=i + 1,
            item_type=pattern.item_type,
            confidence=pattern.base_confidence,
            raw_text=raw,
            context=raw,
            suggested_category=_suggest_category(raw),
            suggested_priority=pattern.suggested_priority,
            item_hash=item_hash,
        ))

    return items


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------

def parse_report(path: str | Path) -> list[OpenItem]:
    """Parse a markdown report file and return a list of open items.

    Items where _is_completed(raw_text) returns True are excluded.
    Deduplication is by item_hash within the same file.
    """
    path = Path(path)
    if not path.is_file():
        return []

    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    source_path = _repo_rel(path)

    items: list[OpenItem] = []
    seen_hashes: set[str] = set()

    # Phase 1: Section-based extraction
    for i, line in enumerate(lines):
        for pattern in _SECTION_PATTERNS:
            if not re.match(pattern.regex, line.strip(), re.IGNORECASE):
                continue
            section_lines, section_header = _extract_section_lines(lines, i)

            if pattern.content_parser == "table_or_list":
                found = _parse_table_or_list(section_lines, source_path, section_header, pattern)
            elif pattern.content_parser == "numbered_list":
                found = _parse_numbered_list(section_lines, source_path, section_header, pattern)
            elif pattern.content_parser == "bullet_list":
                found = _parse_bullet_list(section_lines, source_path, section_header, pattern)
            else:
                found = []

            for item in found:
                if item.item_hash not in seen_hashes:
                    seen_hashes.add(item.item_hash)
                    items.append(item)

    # Phase 2: Status-scan extraction (DEFERRED, NOT STARTED markers anywhere)
    for pattern in _STATUS_SCAN_PATTERNS:
        for item in _parse_status_scan(lines, source_path, pattern):
            if item.item_hash not in seen_hashes:
                seen_hashes.add(item.item_hash)
                items.append(item)

    return items


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _resolve_paths(path_args: Sequence[str]) -> list[Path]:
    """Resolve path arguments, expanding globs."""
    paths: list[Path] = []
    for arg in path_args:
        expanded = glob.glob(arg, recursive=True)
        if expanded:
            for p in sorted(expanded):
                fp = Path(p)
                if fp.is_file() and fp.suffix == ".md":
                    paths.append(fp)
                elif fp.is_dir():
                    paths.extend(sorted(fp.rglob("*.md")))
        else:
            fp = Path(arg)
            if fp.is_file():
                paths.append(fp)
            elif fp.is_dir():
                paths.extend(sorted(fp.rglob("*.md")))
    return paths


def _format_human(items: list[OpenItem], path: Path) -> str:
    """Format items for human-readable console output."""
    if not items:
        return f"  {_repo_rel(path)}: 0 open items"
    lines = [f"  {_repo_rel(path)}: {len(items)} open items"]
    for item in items:
        lines.append(
            f"    [{item.item_type:14s}] {item.title}"
            f"  (conf={item.confidence:.2f}, cat={item.suggested_category}, "
            f"pri={item.suggested_priority}, L{item.source_line})"
        )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Extract open/unresolved items from markdown reports.",
        prog="report_extract",
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="Report file paths or glob patterns (e.g. 'reports/*.md')",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output JSON array of OpenItem dicts",
    )
    parser.add_argument(
        "--count-only",
        action="store_true",
        help="Output {path: count} format only",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.0,
        help="Minimum confidence threshold (default: 0.0)",
    )

    args = parser.parse_args(argv)
    paths = _resolve_paths(args.paths)

    if not paths:
        print("No matching report files found.", file=sys.stderr)
        sys.exit(0)

    all_items: list[OpenItem] = []
    counts: dict[str, int] = {}

    for p in paths:
        items = parse_report(p)
        items = [it for it in items if it.confidence >= args.min_confidence]
        rel = _repo_rel(p)
        counts[rel] = len(items)

        if args.count_only:
            continue

        if args.json_output:
            all_items.extend(items)
        else:
            print(_format_human(items, p))

    if args.count_only:
        print(json.dumps(counts, indent=2))
    elif args.json_output:
        print(json.dumps([asdict(it) for it in all_items], indent=2))

    sys.exit(0)


if __name__ == "__main__":
    main()
