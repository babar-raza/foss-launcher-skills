"""reports.py — Audit report generation and quality trend tracking.

Extracted from audit.py (Phase 5). Contains report_text, report_json,
and the quality trend JSONL management functions.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# sibling-import guard: sub-packages must add the pipeline root so they can
# import sibling top-level modules (knowledge_core, token_ops, core.*).
# This is not the antipattern -- Python adds the sub-package dir to sys.path,
# not the pipeline root. This guard is the correct workaround for the flat layout.
_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

REPORTS_DIR = Path("reports") / "audit"
QUALITY_TREND_MAX_ENTRIES = 180


def _log(*args, **kwargs):
    """Print to stderr so stdout stays clean for --json."""
    import sys as _sys
    print(*args, file=_sys.stderr, **kwargs)


def report_text(all_findings, products_checked) -> str:
    """Generate human-readable report."""
    lines = [
        "# Content API Audit Report",
        f"Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
    ]

    total_fails = sum(1 for f in all_findings if f.level == "FAIL")
    total_warns = sum(1 for f in all_findings if f.level == "WARN")
    total_infos = sum(1 for f in all_findings if f.level == "INFO")

    lines.append("## Summary")
    lines.append(f"Products checked: {len(products_checked)}")
    summary = f"**FAIL: {total_fails}** | WARN: {total_warns}"
    if total_infos:
        summary += f" | INFO: {total_infos}"
    lines.append(summary)
    lines.append("")

    if not all_findings:
        lines.append("No issues found.")
        return "\n".join(lines)

    # Group by file
    by_file = defaultdict(list)
    for f in all_findings:
        by_file[str(f.filepath)].append(f)

    fails = [f for f in all_findings if f.level == "FAIL"]
    warns = [f for f in all_findings if f.level == "WARN"]

    if fails:
        lines.append("## FAIL — Must Fix")
        lines.append("")
        for filepath in sorted(set(str(f.filepath) for f in fails)):
            lines.append(f"### {filepath}")
            for f in sorted(by_file[filepath], key=lambda x: x.line_no):
                if f.level == "FAIL":
                    line = f"- **Line {f.line_no}**: {f.message}"
                    if f.suggestion:
                        line += f" -> {f.suggestion}"
                    lines.append(line)
            lines.append("")

    if warns:
        lines.append("## WARN — Review")
        lines.append("")
        for filepath in sorted(set(str(f.filepath) for f in warns)):
            lines.append(f"### {filepath}")
            for f in sorted(by_file[filepath], key=lambda x: x.line_no):
                if f.level == "WARN":
                    line = f"- **Line {f.line_no}**: {f.message}"
                    if f.suggestion:
                        line += f" -> {f.suggestion}"
                    lines.append(line)
            lines.append("")

    infos = [f for f in all_findings if f.level == "INFO"]
    if infos:
        lines.append("## INFO — Advisory (snippet coverage)")
        lines.append("")
        for filepath in sorted(set(str(f.filepath) for f in infos)):
            lines.append(f"### {filepath}")
            for f in sorted(by_file[filepath], key=lambda x: x.line_no):
                if f.level == "INFO":
                    line = f"- **Line {f.line_no}**: {f.message}"
                    if f.suggestion:
                        line += f" -> {f.suggestion}"
                    lines.append(line)
            lines.append("")

    return "\n".join(lines)


def report_json(all_findings, products_checked) -> str:
    """Generate machine-readable JSON report."""
    return json.dumps({
        "date": datetime.now(timezone.utc).isoformat(),
        "products_checked": products_checked,
        "total_fails": sum(1 for f in all_findings if f.level == "FAIL"),
        "total_warns": sum(1 for f in all_findings if f.level == "WARN"),
        "total_checked": len(all_findings),
        "findings": [
            {
                "level": f.level,
                "file": str(f.filepath),
                "line": f.line_no,
                "message": f.message,
                "suggestion": f.suggestion,
            }
            for f in all_findings
        ],
    }, indent=2)


def _load_trend_entries(trend_path: Path) -> list:
    """Read quality_trend.jsonl, skipping and warning on any malformed lines."""
    if not trend_path.exists():
        return []
    valid, bad = [], 0
    for i, raw in enumerate(trend_path.read_text(encoding="utf-8").splitlines()):
        raw = raw.strip()
        if not raw:
            continue
        try:
            valid.append(json.loads(raw))
        except json.JSONDecodeError:
            bad += 1
            _log(f"  WARNING: quality_trend.jsonl line {i + 1} is malformed — skipping")
    if bad:
        _log(f"  WARNING: dropped {bad} malformed entr{'y' if bad == 1 else 'ies'} from quality trend")
    return valid


def _append_quality_trend(products_summary: list) -> None:
    """Append one entry to quality_trend.jsonl, prune, then write the whole file atomically.

    Replaces the old append-only strategy with a read→validate→append→prune→atomic-write
    cycle so that:
      * malformed lines are dropped before they accumulate
      * the prune and the write happen in one atomic operation (no torn state)
      * the file is never partially written
    """
    from core.fs import atomic_write  # noqa: E402

    trend_path = REPORTS_DIR / "quality_trend.jsonl"
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    entries = _load_trend_entries(trend_path)
    entries.append({
        "run_at": datetime.now(timezone.utc).isoformat(),
        "products": products_summary,
    })
    # Prune in memory — keep only the most recent N entries
    if len(entries) > QUALITY_TREND_MAX_ENTRIES:
        removed = len(entries) - QUALITY_TREND_MAX_ENTRIES
        entries = entries[-QUALITY_TREND_MAX_ENTRIES:]
        _log(f"  quality_trend.jsonl: pruned {removed} oldest entries, keeping {len(entries)}")
    try:
        content = "\n".join(json.dumps(e, ensure_ascii=False) for e in entries) + "\n"
        atomic_write(trend_path, content)
        _log(f"  quality_trend.jsonl updated ({len(entries)} entries)")
    except Exception as exc:
        _log(f"  WARNING: could not write quality_trend.jsonl: {exc}")


def _write_quality_baseline(products_summary: list) -> None:
    """Overwrite quality_baseline.json with latest run results (atomic write)."""
    from core.fs import atomic_write  # noqa: E402

    baseline_path = REPORTS_DIR / "quality_baseline.json"
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        atomic_write(
            baseline_path,
            json.dumps(
                {"updated_at": datetime.now(timezone.utc).isoformat(),
                 "products": products_summary},
                indent=2, ensure_ascii=False,
            ),
        )
    except Exception as exc:
        _log(f"  WARNING: could not write quality_baseline.json: {exc}")


def _prune_quality_trend() -> None:
    """No-op shim — pruning is now integrated into _append_quality_trend."""
    pass
