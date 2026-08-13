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


def extract_product_key(title: str) -> str | None:
    """Best-effort extraction of a '{family}/{platform}' product key from a row's
    Title column, following this backlog's own established convention -- every
    Cat=knowledge row's title observed to date starts with 'family/platform ...'
    (e.g. 'pdf/java new upstream drift...', '3d/net refresh...').

    Returns None when the title doesn't start with a recognizable slash-separated
    product key -- callers must treat that as "cannot determine product", not guess.
    """
    if not title:
        return None
    first_token = title.split()[0] if title.split() else ""
    if "/" not in first_token:
        return None
    parts = first_token.split("/")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None
    # Reject tokens that are clearly not a product key (e.g. a URL fragment or a
    # path that happens to start the title) -- product keys are short, lowercase,
    # alphanumeric-with-hyphens identifiers, never containing '.', ':', or digits-only.
    family, platform = parts
    # Must start with a letter or digit (e.g. "3d" is a real family) and contain only
    # lowercase alphanumerics/hyphens after that -- rejects URL fragments, decimals, etc.
    _key_re = re.compile(r"[a-z0-9][a-z0-9-]*")
    if not _key_re.fullmatch(family) or not _key_re.fullmatch(platform):
        return None
    return f"{family}/{platform}"
