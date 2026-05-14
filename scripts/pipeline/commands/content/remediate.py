"""Batch remediation CLI — reads eval reports and applies auto-fixes at scale.

Usage:
    python scripts/pipeline/remediate.py triage  <eval-report.json>
    python scripts/pipeline/remediate.py fix     <eval-report.json> [--dry-run] [--categories ST,RV]
    python scripts/pipeline/remediate.py report  <eval-report.json>
    python scripts/pipeline/remediate.py status  <remediation-report.json>
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure content_eval package is importable
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

# --- Standalone repo path resolution via config_loader ---
_HERE = Path(__file__).resolve().parent
_PIPELINE = _HERE.parents[1]
_SCRIPTS = _HERE.parents[2]
import sys as _sys
for _path in (_SCRIPTS, _PIPELINE):
    if str(_path) not in _sys.path:
        _sys.path.insert(0, str(_path))
from config_loader import (                       # noqa: E402
    resolve_reports_root as _resolve_reports_root,
    resolve_knowledge_root as _resolve_knowledge_root,
)
# --------------------------------------------------------

from content_eval.models import Finding  # noqa: E402
from content_eval.remediation.triage import (  # noqa: E402
    CATEGORY_TO_EVALUATOR,
    TriageResult,
    triage_findings,
)
from content_eval.remediation.runner import FixResult, run_fixes  # noqa: E402


REPORTS_DIR = _resolve_reports_root() / "remediation"


def _log(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


# ---------------------------------------------------------------------------
# Load eval report JSON into Finding objects
# ---------------------------------------------------------------------------
def _load_eval_report(path: Path) -> list[Finding]:
    """Parse a content_eval JSON report into Finding objects."""
    data = json.loads(path.read_text(encoding="utf-8"))
    findings = []
    for f in data.get("findings", []):
        findings.append(Finding(
            level=f["level"],
            category=f["category"],
            filepath=f["file"],
            line_no=f["line"],
            message=f["message"],
            suggestion=f.get("suggestion", ""),
            evaluator=f.get("evaluator", ""),
        ))
    return findings


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------
def _generate_json_report(
    input_path: str,
    triage: TriageResult,
    fixes: list[FixResult] | None = None,
) -> str:
    """Generate remediation report as JSON."""
    now = datetime.now(timezone.utc).isoformat()

    fix_data = []
    if fixes:
        for fx in fixes:
            fix_data.append({
                "finding_id": fx.finding_id,
                "filepath": fx.filepath,
                "fixer": fx.fixer_name,
                "action": fx.action,
                "description": fx.description,
                "diff_preview": fx.diff_preview,
            })

    llm_data = []
    for tf in triage.llm_needed:
        llm_data.append({
            "finding_id": tf.finding.id,
            "filepath": tf.finding.filepath,
            "category": tf.finding.category,
            "level": tf.finding.level,
            "line": tf.finding.line_no,
            "message": tf.finding.message,
            "reason": tf.reason,
        })

    human_data = []
    for tf in triage.human_needed:
        human_data.append({
            "finding_id": tf.finding.id,
            "filepath": tf.finding.filepath,
            "category": tf.finding.category,
            "level": tf.finding.level,
            "line": tf.finding.line_no,
            "message": tf.finding.message,
            "reason": tf.reason,
        })

    data = {
        "schema_version": 1,
        "generated_at": now,
        "input_report": input_path,
        "triage_summary": triage.summary,
        "auto_fixes": fix_data,
        "llm_queue": llm_data,
        "human_queue": human_data,
    }

    # Add fix summary stats
    if fixes:
        action_counts = Counter(fx.action for fx in fixes)
        fixer_counts = Counter(fx.fixer_name for fx in fixes if fx.action == "fixed")
        data["fix_summary"] = {
            "by_action": dict(action_counts),
            "by_fixer": dict(fixer_counts),
        }

    return json.dumps(data, indent=2, ensure_ascii=False)


def _generate_markdown_report(
    input_path: str,
    triage: TriageResult,
    fixes: list[FixResult] | None = None,
) -> str:
    """Generate remediation report as markdown."""
    lines = [
        "# Remediation Report",
        "",
        f"**Input**: `{input_path}`",
        f"**Date**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "## Triage Summary",
        "",
        f"| Bucket | Count |",
        f"|--------|-------|",
        f"| Auto-fixable | {len(triage.auto_fixable)} |",
        f"| LLM-needed | {len(triage.llm_needed)} |",
        f"| Human-needed | {len(triage.human_needed)} |",
        f"| Skipped | {len(triage.skipped)} |",
        f"| **Total** | **{triage.total}** |",
        "",
    ]

    if fixes:
        fixed = [fx for fx in fixes if fx.action == "fixed"]
        skipped = [fx for fx in fixes if fx.action == "skipped"]
        would_fix = [fx for fx in fixes if fx.action == "would_fix"]

        lines.append("## Auto-Fix Results")
        lines.append("")
        if would_fix:
            lines.append(f"**Dry-run mode** — {len(would_fix)} fixes would be applied:")
            lines.append("")
            for fx in would_fix:
                lines.append(f"- `{fx.filepath}` [{fx.fixer_name}]: {fx.description}")
            lines.append("")
        if fixed:
            lines.append(f"**Applied** {len(fixed)} fixes:")
            lines.append("")
            for fx in fixed:
                lines.append(f"- `{fx.filepath}` [{fx.fixer_name}]: {fx.description}")
                if fx.diff_preview:
                    lines.append(f"  ```diff")
                    lines.append(f"  {fx.diff_preview}")
                    lines.append(f"  ```")
            lines.append("")
        if skipped:
            lines.append(f"**Skipped** {len(skipped)} (already fixed or not applicable)")
            lines.append("")

    if triage.llm_needed:
        lines.append("## LLM Queue")
        lines.append("")
        lines.append(f"{len(triage.llm_needed)} findings need LLM-assisted fixes:")
        lines.append("")
        by_cat = Counter(tf.finding.category for tf in triage.llm_needed)
        for cat, count in sorted(by_cat.items()):
            evaluator = CATEGORY_TO_EVALUATOR.get(cat, cat)
            lines.append(f"- **{cat}** ({evaluator}): {count}")
        lines.append("")

    if triage.human_needed:
        lines.append("## Human Queue")
        lines.append("")
        for tf in triage.human_needed:
            lines.append(
                f"- [{tf.finding.level}] `{tf.finding.filepath}:{tf.finding.line_no}` "
                f"— {tf.finding.message} ({tf.reason})"
            )
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI subcommands
# ---------------------------------------------------------------------------
def _cmd_triage(args):
    """Triage only — classify findings without modifying files."""
    report_path = Path(args.eval_report)
    findings = _load_eval_report(report_path)
    _log(f"Loaded {len(findings)} findings from {report_path}")

    triage = triage_findings(findings)

    _log(f"\nTriage results:")
    for k, v in triage.summary.items():
        _log(f"  {k}: {v}")

    # Output markdown to stdout
    output = _generate_markdown_report(str(report_path), triage)
    sys.stdout.buffer.write(output.encode("utf-8"))
    sys.stdout.buffer.write(b"\n")


def _cmd_fix(args):
    """Triage + apply auto-fixes."""
    report_path = Path(args.eval_report)
    findings = _load_eval_report(report_path)
    _log(f"Loaded {len(findings)} findings from {report_path}")

    triage = triage_findings(findings)
    _log(f"Triage: {triage.summary}")

    # Parse optional category filter
    categories = None
    if args.categories:
        categories = {c.strip().upper() for c in args.categories.split(",")}
        _log(f"Filtering to categories: {categories}")

    # Run fixes
    fixes = run_fixes(
        triage.auto_fixable,
        dry_run=args.dry_run,
        categories=categories,
    )

    # Generate and save report
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    json_output = _generate_json_report(str(report_path), triage, fixes)
    json_path = REPORTS_DIR / f"rem-{timestamp}.json"
    json_path.write_text(json_output, encoding="utf-8")

    md_output = _generate_markdown_report(str(report_path), triage, fixes)
    md_path = REPORTS_DIR / f"rem-{timestamp}.md"
    md_path.write_text(md_output, encoding="utf-8")

    # Print markdown to stdout
    sys.stdout.buffer.write(md_output.encode("utf-8"))
    sys.stdout.buffer.write(b"\n")

    # Summary to stderr
    action_counts = Counter(fx.action for fx in fixes)
    _log(f"\nFix results:")
    for action, count in sorted(action_counts.items()):
        _log(f"  {action}: {count}")
    _log(f"  Reports: {json_path}, {md_path}")


def _cmd_report(args):
    """Triage + fix + full report (same as fix but always applies)."""
    # Delegate to fix with dry_run=False
    args.dry_run = False
    args.categories = None
    _cmd_fix(args)


def _cmd_status(args):
    """Show remaining items from a remediation report."""
    report_path = Path(args.remediation_report)
    data = json.loads(report_path.read_text(encoding="utf-8"))

    print(f"Remediation Report: {data.get('input_report', '?')}")
    print(f"Generated: {data.get('generated_at', '?')}")
    print()

    triage = data.get("triage_summary", {})
    print("Triage Summary:")
    for k, v in triage.items():
        print(f"  {k}: {v}")
    print()

    fixes = data.get("auto_fixes", [])
    if fixes:
        action_counts = Counter(f["action"] for f in fixes)
        print("Auto-Fix Results:")
        for action, count in sorted(action_counts.items()):
            print(f"  {action}: {count}")
        print()

    llm_queue = data.get("llm_queue", [])
    if llm_queue:
        print(f"LLM Queue: {len(llm_queue)} remaining")
        by_cat = Counter(f["category"] for f in llm_queue)
        for cat, count in sorted(by_cat.items()):
            print(f"  {cat}: {count}")
        print()

    human_queue = data.get("human_queue", [])
    if human_queue:
        print(f"Human Queue: {len(human_queue)} remaining")
        for item in human_queue:
            print(f"  [{item['level']}] {item['filepath']}:{item['line']} — {item['message']}")
        print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(
        prog="remediate",
        description="Batch remediation pipeline — triage and auto-fix eval findings",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # triage
    p_triage = sub.add_parser("triage", help="Classify findings (read-only)")
    p_triage.add_argument("eval_report", help="Path to content_eval JSON report")
    p_triage.set_defaults(func=_cmd_triage)

    # fix
    p_fix = sub.add_parser("fix", help="Triage + apply auto-fixes")
    p_fix.add_argument("eval_report", help="Path to content_eval JSON report")
    p_fix.add_argument("--dry-run", action="store_true", help="Show what would change")
    p_fix.add_argument("--categories", help="Comma-separated category codes (e.g. ST,RV)")
    p_fix.set_defaults(func=_cmd_fix)

    # report
    p_report = sub.add_parser("report", help="Full triage + fix + report")
    p_report.add_argument("eval_report", help="Path to content_eval JSON report")
    p_report.set_defaults(func=_cmd_report)

    # status
    p_status = sub.add_parser("status", help="Show remaining items from remediation report")
    p_status.add_argument("remediation_report", help="Path to remediation JSON report")
    p_status.set_defaults(func=_cmd_status)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
