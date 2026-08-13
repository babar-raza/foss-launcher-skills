"""
backlog_parser.py — shared table parser for backlog/BACKLOG.md's Active/Queued tables.

CONTRACT: scripts/pipeline/lib/backlog_parser.py
  purpose: MT030-2026-08-13 found this exact table-parsing logic already existed,
           un-shared, inside scripts/ci/checks/check_backlog_open_items.py
           (_parse_table_rows). backlog_reconcile.py needs the same rows (plus a
           couple of columns that checker never needed: Cat, Updated) to cross-check
           against data/knowledge_state.json. Extracted here so both callers use one
           parser instead of two regexes drifting apart -- the reference doc's own
           Core Principle #2 ("one controller, one task graph... parallel ledgers
           create predictable failures") applies just as much to a table parser as
           to a mission tracker.
  inputs:  BACKLOG.md's raw text (or a Path to it)
  outputs: list[dict] — one dict per Active/Queued table row
  idempotent: yes (pure parse, no side effects)

Column order (backlog/BACKLOG.md's Active/Queued tables):
    ID | Cat | Effect | Title | Status | Priority | Size | Wave | Score | Plan | Blocker | Updated
"""
from __future__ import annotations

import re
from pathlib import Path

_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def parse_table_rows(text: str) -> list[dict]:
    """Extract rows from the Active and Queued markdown tables in BACKLOG.md.

    Returns a list of dicts with keys: id, cat, title, status, blocker, plan,
    updated, raw_line.
    """
    rows = []
    in_table = False
    header_seen = False
    for line in text.splitlines():
        stripped = line.strip()
        # Only process rows inside the ## Active and ## Queued sections
        if stripped.startswith("## Active") or stripped.startswith("## Queued"):
            in_table = True
            header_seen = False
            continue
        if stripped.startswith("## ") and in_table:
            in_table = False
            continue
        if not in_table:
            continue
        if not stripped.startswith("|"):
            continue
        # Split on | and discard empty strings (leading/trailing pipes produce empties)
        parts = [p.strip() for p in stripped.split("|") if p.strip()]
        # Table header row
        if parts and parts[0].upper() == "ID":
            header_seen = True
            continue
        # Separator row (---|---)
        if parts and re.match(r"^[-:]+$", parts[0]):
            continue
        if not header_seen or len(parts) < 5:
            continue
        # Col indices: 0=ID, 1=Cat, 2=Effect, 3=Title, 4=Status, 5=Priority,
        #              6=Size, 7=Wave, 8=Score, 9=Plan, 10=Blocker, 11=Updated
        rows.append({
            "id": parts[0] if len(parts) > 0 else "",
            "cat": parts[1] if len(parts) > 1 else "",
            "title": parts[3] if len(parts) > 3 else "",
            "status": parts[4] if len(parts) > 4 else "",
            "plan": parts[9] if len(parts) > 9 else "",
            "blocker": parts[10] if len(parts) > 10 else "",
            "updated": parts[11] if len(parts) > 11 else "",
            "raw_line": stripped,
        })
    return rows


def parse_backlog_file(path: "Path | str") -> list[dict]:
    """Convenience wrapper: read *path* and return parse_table_rows(text)."""
    p = Path(path)
    if not p.exists():
        return []
    return parse_table_rows(p.read_text(encoding="utf-8", errors="replace"))


# Scan window for extract_product_key(): how many leading whitespace-separated
# tokens to check for a family/platform-shaped token. Wide enough to survive a
# "CLOSED {date} ({mission-id}) -- " closure prefix (confirmed live: MT030's own
# PDF-JAVA-REFRESH-003 closure note put a 4-token prefix before the row's own
# "pdf/java", which a first-token-only check silently failed to resolve --
# ironically excluding that exact row from the reconciliation check it was
# supposed to prove passes), narrow enough to avoid matching deep into
# multi-hundred-word descriptions.
_PRODUCT_KEY_SCAN_WINDOW = 15
_PRODUCT_KEY_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9-]*/[a-z0-9][a-z0-9-]*")


def extract_product_key(title: str) -> str | None:
    """Best-effort extraction of a '{family}/{platform}' product key from a row's
    Title column, following this backlog's own established convention -- every
    Cat=knowledge row's title observed to date starts with 'family/platform ...'
    (e.g. 'pdf/java new upstream drift...', '3d/net refresh...'), possibly after
    a short closure-annotation prefix (e.g. 'CLOSED 2026-08-13 (MT030-...) -- ').

    Scans the first _PRODUCT_KEY_SCAN_WINDOW whitespace-separated tokens for one
    matching the strict family/platform shape (lowercase alphanumeric-hyphen on
    each side of exactly one '/') and returns the first match. Product keys are
    never uppercase, never contain '.', ':', or multiple slashes -- this rejects
    URL fragments, version-like tokens, and other slash-containing prose that
    isn't a product reference.

    Returns None when no recognizable product key appears within the scan
    window -- callers must treat that as "cannot determine product", not guess.
    """
    if not title:
        return None
    tokens = title.split()[:_PRODUCT_KEY_SCAN_WINDOW]
    for token in tokens:
        # Strip common prose punctuation that might cling to the token
        # (trailing colons, parens, commas) without touching the '/' itself.
        stripped = token.strip(".,;:()[]{}\"'")
        match = _PRODUCT_KEY_TOKEN_RE.fullmatch(stripped)
        if match:
            return stripped
    return None
