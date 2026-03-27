"""Markdown report generator."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from ..models import EvalReport
from ..remediation.planner import RemediationBatch


def generate_markdown(report: EvalReport,
                      remediation: list[RemediationBatch] | None = None) -> str:
    """Generate a human-readable markdown report."""
    lines: list[str] = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines.append(f"# Content Evaluation Report")
    lines.append(f"")
    lines.append(f"**Date**: {now}")
    lines.append(f"**Pages evaluated**: {report.pages_evaluated}")
    lines.append(f"**Evaluators run**: {', '.join(report.evaluators_run)}")
    lines.append(f"")

    # Summary table
    lines.append(f"## Summary")
    lines.append(f"")
    lines.append(f"| Severity | Count |")
    lines.append(f"|----------|-------|")
    lines.append(f"| FAIL | {len(report.fails)} |")
    lines.append(f"| WARN | {len(report.warns)} |")
    lines.append(f"| INFO | {len(report.infos)} |")
    lines.append(f"| **Total** | **{len(report.findings)}** |")
    lines.append(f"")

    # By category
    cat_counts = Counter(f.category for f in report.findings)
    if cat_counts:
        lines.append(f"### By Category")
        lines.append(f"")
        lines.append(f"| Category | Count |")
        lines.append(f"|----------|-------|")
        for cat, count in cat_counts.most_common():
            lines.append(f"| {cat} | {count} |")
        lines.append(f"")

    # FAIL findings first
    if report.fails:
        lines.append(f"## FAIL — Must Fix")
        lines.append(f"")
        by_file = {}
        for f in report.fails:
            by_file.setdefault(f.filepath, []).append(f)
        for filepath in sorted(by_file):
            lines.append(f"### {filepath}")
            for f in sorted(by_file[filepath], key=lambda x: x.line_no):
                msg = f"- **Line {f.line_no}** [{f.category}]: {f.message}"
                if f.suggestion:
                    msg += f" → {f.suggestion}"
                lines.append(msg)
            lines.append(f"")

    # WARN findings
    if report.warns:
        lines.append(f"## WARN — Review")
        lines.append(f"")
        by_file = {}
        for f in report.warns:
            by_file.setdefault(f.filepath, []).append(f)
        for filepath in sorted(by_file):
            lines.append(f"### {filepath}")
            for f in sorted(by_file[filepath], key=lambda x: x.line_no):
                msg = f"- **Line {f.line_no}** [{f.category}]: {f.message}"
                if f.suggestion:
                    msg += f" → {f.suggestion}"
                lines.append(msg)
            lines.append(f"")

    # INFO findings (collapsed)
    if report.infos:
        lines.append(f"## INFO — Improvements")
        lines.append(f"")
        by_file = {}
        for f in report.infos:
            by_file.setdefault(f.filepath, []).append(f)
        for filepath in sorted(by_file):
            lines.append(f"### {filepath}")
            for f in sorted(by_file[filepath], key=lambda x: x.line_no):
                lines.append(f"- **Line {f.line_no}** [{f.category}]: {f.message}")
            lines.append(f"")

    # Remediation plan
    if remediation:
        lines.append(f"## Remediation Plan")
        lines.append(f"")
        for batch in remediation:
            lines.append(f"### Priority {batch.priority}: {batch.description}")
            lines.append(f"- **Effort**: {batch.estimated_effort}")
            lines.append(f"- **Files**: {len(batch.files)}")
            if batch.post_actions:
                lines.append(f"- **Post-actions**: {', '.join(batch.post_actions)}")
            lines.append(f"")

    return "\n".join(lines)
