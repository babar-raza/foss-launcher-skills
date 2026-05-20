#!/usr/bin/env python3
# Adapted from aspose.org scripts/ci/checks/ for standalone use
"""check_plan_quality.py — Static analysis for plan file quality.

Scans plan files for conditions that trigger mandatory S-91 plan-normalize,
reporting each detected trigger as a WARNING. This script is advisory: it
always exits 0 and produces a report, not a hard block.

Rules implemented:
  PQ-01  MIXED_CONTEXT        Sprint/retrospective/postmortem H2 alongside open-action language
  PQ-02  STALE_UNNORMALIZED   Last modified >N days ago with no normalization record
  PQ-03  COMPLETED_MIXED_WITH_OPEN  Archive/done H2 section alongside open-work H2 section
  PQ-04  MATURITY_AMBIGUITY   "spec-only"/"partially validated" alongside "ready" in same section
  PQ-05  LONG_UNNORMALIZED    >4 H2 sections and no normalization record

Usage:
    python scripts/ci/checks/check_plan_quality.py {path...} [--json] [--min-age-days N]
    python scripts/ci/checks/check_plan_quality.py tests/fixtures/plan-normalize/
    python scripts/ci/checks/check_plan_quality.py --help
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path
from typing import List, NamedTuple, Optional


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class Finding(NamedTuple):
    rule: str
    filepath: str
    reason: str


# ---------------------------------------------------------------------------
# Rule helpers
# ---------------------------------------------------------------------------

_ARCHIVE_H2 = re.compile(
    r"^##\s+.*?(retrospective|postmortem|post-mortem|sprint\s+\d)",
    re.IGNORECASE | re.MULTILINE,
)
_OPEN_ACTION_KEYWORDS = re.compile(
    r"\bstatus:\s*ready\b|\- \[[ x]\]|\bopen work\b|\bnext action\b",
    re.IGNORECASE,
)
_COMPLETED_H2 = re.compile(
    r"^##\s+(completed|done|archive|archived|finished)",
    re.IGNORECASE | re.MULTILINE,
)
_OPEN_WORK_H2 = re.compile(
    r"^##\s+(open work|backlog|in progress|todo|tasks)",
    re.IGNORECASE | re.MULTILINE,
)
_MATURITY_WEAK = re.compile(
    r"spec-only|partially[- ]validated|not yet (written|implemented|wired)",
    re.IGNORECASE,
)
_MATURITY_READY = re.compile(r"\bready\b", re.IGNORECASE)
_NORMALIZATION_RECORD = re.compile(
    r"^##\s+plan normalization record",
    re.IGNORECASE | re.MULTILINE,
)
_H2_SECTION = re.compile(r"^##\s+\S", re.MULTILINE)


def _split_h2_sections(text: str) -> List[str]:
    """Return list of H2 section bodies (text between consecutive H2 headers)."""
    headers = [m.start() for m in _H2_SECTION.finditer(text)]
    if not headers:
        return [text]
    sections = []
    for i, start in enumerate(headers):
        end = headers[i + 1] if i + 1 < len(headers) else len(text)
        sections.append(text[start:end])
    return sections


def check_pq01(text: str) -> Optional[str]:
    """MIXED_CONTEXT: archive H2 heading alongside open-action language anywhere in file."""
    if not _ARCHIVE_H2.search(text):
        return None
    if _OPEN_ACTION_KEYWORDS.search(text):
        return (
            "H2 section with sprint/retrospective/postmortem keyword "
            "found alongside open-action language (checkboxes or 'Status: ready')"
        )
    return None


def check_pq02(filepath: str, text: str, min_age_days: int) -> Optional[str]:
    """STALE_UNNORMALIZED: file modified >N days ago with no normalization record."""
    if _NORMALIZATION_RECORD.search(text):
        return None
    try:
        mtime = os.path.getmtime(filepath)
    except OSError:
        return None
    age_days = (datetime.datetime.now().timestamp() - mtime) / 86400
    if age_days > min_age_days:
        return (
            f"File last modified {age_days:.0f} day(s) ago "
            f"(threshold: {min_age_days}) with no '## Plan Normalization Record' section"
        )
    return None


def check_pq03(text: str) -> Optional[str]:
    """COMPLETED_MIXED_WITH_OPEN: archive H2 section alongside open-work H2 section."""
    if _COMPLETED_H2.search(text) and _OPEN_WORK_H2.search(text):
        return (
            "Plan has both a completed/archive H2 section and an open-work/backlog H2 section"
        )
    return None


def check_pq04(text: str) -> Optional[str]:
    """MATURITY_AMBIGUITY: spec-only/partially-validated alongside ready in same section."""
    for section in _split_h2_sections(text):
        if _MATURITY_WEAK.search(section) and _MATURITY_READY.search(section):
            return (
                "Section contains both capability-maturity caveats "
                "('spec-only'/'partially validated') and 'ready' status"
            )
    return None


def check_pq05(text: str) -> Optional[str]:
    """LONG_UNNORMALIZED: >4 H2 sections with no normalization record."""
    if _NORMALIZATION_RECORD.search(text):
        return None
    h2_count = len(_H2_SECTION.findall(text))
    if h2_count > 4:
        return (
            f"Plan has {h2_count} H2 sections but no '## Plan Normalization Record' section"
        )
    return None


# ---------------------------------------------------------------------------
# File scanner
# ---------------------------------------------------------------------------

def scan_file(filepath: str, min_age_days: int) -> List[Finding]:
    """Return all findings for a single file. Never raises."""
    try:
        text = Path(filepath).read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return [Finding("READ_ERROR", filepath, str(exc))]

    findings: List[Finding] = []
    for rule, checker in [
        ("PQ-01", lambda t: check_pq01(t)),
        ("PQ-02", lambda t: check_pq02(filepath, t, min_age_days)),
        ("PQ-03", lambda t: check_pq03(t)),
        ("PQ-04", lambda t: check_pq04(t)),
        ("PQ-05", lambda t: check_pq05(t)),
    ]:
        try:
            reason = checker(text)
        except Exception as exc:  # noqa: BLE001
            reason = f"[rule error: {exc}]"
        if reason:
            findings.append(Finding(rule, filepath, reason))

    return findings


def collect_files(paths: List[str]) -> List[str]:
    """Expand paths to a sorted, deduplicated list of .md files."""
    result: List[str] = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            result.extend(str(f) for f in path.rglob("*.md"))
        elif path.is_file() and path.suffix == ".md":
            result.append(str(path))
        # Non-.md files and missing paths are silently skipped
    return sorted(set(result))


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

def format_human(findings: List[Finding], file_count: int) -> str:
    lines: List[str] = []
    for f in findings:
        lines.append(f"WARN [{f.rule}] {f.filepath}: {f.reason}")
    lines.append(f"\n{file_count} file(s) scanned, {len(findings)} finding(s)")
    return "\n".join(lines)


def format_json_output(findings: List[Finding], file_count: int) -> str:
    return json.dumps(
        {
            "files_scanned": file_count,
            "finding_count": len(findings),
            "findings": [
                {"rule": f.rule, "filepath": f.filepath, "reason": f.reason}
                for f in findings
            ],
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# Public entry point (importable for testing)
# ---------------------------------------------------------------------------

def run(paths: List[str], min_age_days: int = 7, as_json: bool = False) -> str:
    """Scan paths and return formatted output string."""
    files = collect_files(paths)
    all_findings: List[Finding] = []
    for filepath in files:
        all_findings.extend(scan_file(filepath, min_age_days))
    if as_json:
        return format_json_output(all_findings, len(files))
    return format_human(all_findings, len(files))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scan plan files for conditions requiring S-91 plan-normalize.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="One or more .md files or directories to scan",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Emit machine-readable JSON instead of human-readable text",
    )
    parser.add_argument(
        "--min-age-days",
        type=int,
        default=7,
        metavar="N",
        help="Days threshold for STALE_UNNORMALIZED check (default: 7)",
    )
    args = parser.parse_args(argv)
    output = run(args.paths, min_age_days=args.min_age_days, as_json=args.as_json)
    print(output)
    return 0  # always advisory


if __name__ == "__main__":
    sys.exit(main())
