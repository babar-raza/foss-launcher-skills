# Adapted from aspose.org scripts/ci/checks/ for standalone use
"""extract_session_skills.py — Read session invocation logs and suggest Skills invoked text.

Reads reports/session-invocations/*.jsonl from the current session (by date or PID)
and outputs a "Skills invoked (verified): [S-xx, ...]" declaration string.

"Verified" means the skill was logged by a pipeline script automatically.
"Attested" would be a manual declaration by the agent.

Usage:
  python scripts/ci/checks/extract_session_skills.py
  python scripts/ci/checks/extract_session_skills.py --date 2026-03-31
  python scripts/ci/checks/extract_session_skills.py --format text     # default: print declaration
  python scripts/ci/checks/extract_session_skills.py --format ids      # print only IDs
  python scripts/ci/checks/extract_session_skills.py --format json     # print JSON list

Exit codes:
  0  Skills found and output
  1  No session logs found or no skills in logs
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(os.environ.get("REPO_ROOT", Path(__file__).resolve().parent.parent.parent.parent))
SESSION_DIR = REPO_ROOT / "reports" / "session-invocations"


def load_session_invocations(date_str: str | None = None) -> list[dict]:
    """Load all invocation records from session logs for the given date (or today)."""
    if not SESSION_DIR.exists():
        return []

    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    records = []
    for log_file in sorted(SESSION_DIR.glob(f"{date_str}-*.jsonl")):
        try:
            with log_file.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
        except (json.JSONDecodeError, OSError):
            pass

    return records


def extract_skill_ids(records: list[dict]) -> list[str]:
    """Extract unique skill IDs from invocation records, preserving order."""
    seen: set[str] = set()
    ids: list[str] = []
    for record in records:
        sid = record.get("skill_id", "")
        if sid and sid not in seen:
            seen.add(sid)
            ids.append(sid)
    return ids


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="extract_session_skills",
        description="Extract skill IDs from session logs for commit message generation.",
    )
    parser.add_argument("--date", default=None, help="Date to read logs for (YYYY-MM-DD, default: today)")
    parser.add_argument("--format", choices=["text", "ids", "json"], default="text",
                        help="Output format")
    args = parser.parse_args(argv)

    records = load_session_invocations(args.date)
    if not records:
        print(
            "No session invocation logs found for today.\n"
            "Pipeline scripts log invocations to reports/session-invocations/.\n"
            "If skills were invoked as LLM-session steps (not via pipeline scripts),\n"
            "declare them manually with: Skills invoked (attested): [S-xx, ...]",
            file=sys.stderr,
        )
        return 1

    skill_ids = extract_skill_ids(records)
    if not skill_ids:
        print("Session logs found but no skill IDs recorded.", file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps(skill_ids))
    elif args.format == "ids":
        print(" ".join(skill_ids))
    else:
        print(f"Skills invoked (verified): [{', '.join(skill_ids)}]")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
