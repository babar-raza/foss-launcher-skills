"""check_backlog_open_items.py — Advisory validator for backlog carry-forward hygiene.

Prevents three classes of drift discovered in carry-forward rectification sprint
(2026-06-08):
  CF-01  OPEN/CONDITIONALLY_ACCEPTED row has empty Blocker column
  CF-02  INV-* row with CONDITIONALLY_ACCEPTED status has no "Next review:" date
  CF-03  Non-CLOSED external item (INV-*) has Status=CLOSED without evidence keyword

Advisory only — exits 0 with findings printed. Does not block PRs.
No files are modified.

Usage:
    .venv/Scripts/python scripts/ci/checks/check_backlog_open_items.py
    .venv/Scripts/python scripts/ci/checks/check_backlog_open_items.py --json
    .venv/Scripts/python scripts/ci/checks/check_backlog_open_items.py --strict   (exit 1 on CF findings)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKLOG_PATH = REPO_ROOT / "backlog" / "BACKLOG.md"

# Statuses that are considered "done" — no blocker/review-date required.
_DONE_STATUSES = {
    "CLOSED", "CLOSED/INVALID", "ACCEPTED", "ACCEPTED_CEILING",
    "BLOCKED", "OPEN_EXTERNAL_REVIEW_SCHEDULED",
}

# Statuses that must have a non-empty Blocker column.
_NEEDS_BLOCKER = {"OPEN", "CONDITIONALLY_ACCEPTED", "DOWNGRADED"}

# Review-date pattern: YYYY-MM-DD
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _parse_table_rows(text: str) -> list[dict]:
    """Extract rows from the Active and Queued markdown tables in BACKLOG.md.

    Returns list of dicts with keys: id, title, status, blocker, raw_line.
    Column order: ID | Cat | Effect | Title | Status | Priority | Size | Wave | Score | Plan | Blocker | Updated
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
        row_id = parts[0] if len(parts) > 0 else ""
        title = parts[3] if len(parts) > 3 else ""
        status = parts[4] if len(parts) > 4 else ""
        blocker = parts[10] if len(parts) > 10 else ""
        rows.append({
            "id": row_id,
            "title": title,
            "status": status,
            "blocker": blocker,
            "raw_line": stripped,
        })
    return rows


def check_backlog(path: Path) -> list[dict]:
    """Run all CF-* checks. Returns list of findings."""
    if not path.exists():
        return [{"rule": "CF-00", "id": "N/A", "message": f"BACKLOG.md not found at {path}"}]

    text = path.read_text(encoding="utf-8", errors="replace")
    rows = _parse_table_rows(text)
    findings = []

    for row in rows:
        row_id = row["id"]
        status = row["status"].upper().strip()
        blocker = row["blocker"].strip()
        title = row["title"]

        # CF-01: non-done rows must have a Blocker
        if status in _NEEDS_BLOCKER:
            blocker_empty = not blocker or blocker in ("-", "\u2014", "\u2013", "N/A", "n/a")
            if blocker_empty:
                findings.append({
                    "rule": "CF-01",
                    "id": row_id,
                    "status": status,
                    "message": (
                        f"{row_id} ({status}): Blocker column is empty "
                        "— add a reason why this item remains open"
                    ),
                })

        # CF-02: INV-* with CONDITIONALLY_ACCEPTED must have a review date
        if row_id.startswith("INV-") and "CONDITIONALLY_ACCEPTED" in status:
            if not _DATE_RE.search(title):
                findings.append({
                    "rule": "CF-02",
                    "id": row_id,
                    "status": status,
                    "message": (
                        f"{row_id} (CONDITIONALLY_ACCEPTED): "
                        "Title/description has no YYYY-MM-DD review date "
                        "— add 'Next review: YYYY-MM-DD' to prevent silent expiry"
                    ),
                })

        # CF-03: INV-* must not be CLOSED without an evidence keyword
        if row_id.startswith("INV-") and "CLOSED" in status:
            evidence_keywords = ("verified", "confirmed", "merged", "fixed", "closed", "resolved")
            has_evidence = any(kw in title.lower() for kw in evidence_keywords)
            if not has_evidence:
                findings.append({
                    "rule": "CF-03",
                    "id": row_id,
                    "status": status,
                    "message": (
                        f"{row_id} (CLOSED): "
                        "External item closed without evidence keyword "
                        "(verified/confirmed/merged/fixed/resolved) "
                        "— risk of false closure"
                    ),
                })

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument(
        "--strict", action="store_true",
        help="Exit 1 if any CF findings found (default: advisory, always exit 0)",
    )
    parser.add_argument(
        "--backlog", default=str(BACKLOG_PATH),
        help="Path to BACKLOG.md (default: repo backlog/BACKLOG.md)",
    )
    args = parser.parse_args()

    findings = check_backlog(Path(args.backlog))

    if args.json:
        print(json.dumps({"findings": findings, "count": len(findings)}, indent=2))
    else:
        if not findings:
            print("check_backlog_open_items: OK — 0 carry-forward hygiene findings")
        else:
            print(f"check_backlog_open_items: {len(findings)} finding(s):")
            for f in findings:
                print(f"  [{f['rule']}] {f['message']}")

    if args.strict and findings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
