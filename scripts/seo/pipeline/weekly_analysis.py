"""
SEO-INREPO-ANALYSIS-WORKFLOW weekly_analysis.py
==================================================
Orchestrates the read-only SEO analysis stages already built this mission
into a single weekly check, consumed by .github/workflows/seo-analysis.yml
(issue-only pattern -- matches this repo's existing upstream-monitor.yml
style: never commits or opens a PR directly, only opens/updates a tracking
GitHub issue when something is genuinely noteworthy).

Runs, in order:
  1. check_duplicate_titles.py --mode ci   -- blocks only on NEW duplicate
     groups since the last reviewed baseline (grandfathers existing debt)
  2. keyword_gap_report.py                 -- real GSC demand with no
     backing content ("investigate" classification only; "structural"
     entries are expected Hugo list pages, never noteworthy)
  3. frontmatter_grounding_audit.py         -- keyword-source distribution
     across real KB pages (informational; does not itself trigger noteworthy)
  4. title_consistency_evaluator.py        -- WARN count against
     title_templates.yaml (informational; the backlog is already known and
     tracked via the frozen pilot, so this alone does not trigger noteworthy)

"Noteworthy" (exit 1) is deliberately narrow: only a genuinely NEW
regression (a new duplicate-title group, or a new investigate-worthy
keyword gap) opens an issue. The known, already-tracked backlogs (title
WARN count, KB keyword-count gaps) are informational context in the issue
body, not triggers on their own -- otherwise this workflow would open a
noisy issue every single week for debt this mission already knows about and
is working down through its own governed, frozen-pilot process.

Exit codes:
  0 -- nothing new to report
  1 -- new duplicate-title group(s) and/or new investigate-worthy keyword
       gap(s) found
  2 -- a stage failed to run at all (distinct from "found something")
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
REPORTS_DIR = _REPO_ROOT / "reports" / "seo"

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "ci" / "checks"))

try:
    import check_duplicate_titles
    import keyword_gap_report
    import frontmatter_grounding_audit
    import title_consistency_evaluator
except Exception as exc:  # pragma: no cover -- defensive import guard
    print(f"ERROR: weekly_analysis.py could not import a required stage: {exc}", file=sys.stderr)
    sys.exit(2)


def run() -> dict:
    summary: dict = {"stages": {}, "noteworthy": False, "errors": []}

    try:
        current = check_duplicate_titles.find_duplicate_titles()
        baseline = check_duplicate_titles.load_baseline()
        new_groups = check_duplicate_titles.diff_against_baseline(current, baseline)
        summary["stages"]["duplicate_titles"] = {
            "new_group_count": len(new_groups),
            "new_groups": new_groups[:20],
            "total_current_groups": len(current),
        }
        if new_groups:
            summary["noteworthy"] = True
    except Exception as exc:
        summary["errors"].append(f"duplicate_titles: {exc}")

    try:
        gap_report = keyword_gap_report.build_gap_report()
        investigate_count = gap_report["meta"]["investigate_count"]
        summary["stages"]["keyword_gaps"] = {
            "investigate_count": investigate_count,
            "structural_count": gap_report["meta"]["structural_count"],
            "top_investigate": gap_report["investigate"][:10],
        }
        if investigate_count > 0:
            summary["noteworthy"] = True
    except Exception as exc:
        summary["errors"].append(f"keyword_gaps: {exc}")

    try:
        grounding_report = frontmatter_grounding_audit.build_report()
        summary["stages"]["frontmatter_grounding"] = grounding_report["meta"]
    except Exception as exc:
        summary["errors"].append(f"frontmatter_grounding: {exc}")

    try:
        title_report = title_consistency_evaluator.build_report()
        summary["stages"]["title_consistency"] = title_report["meta"]
    except Exception as exc:
        summary["errors"].append(f"title_consistency: {exc}")

    if summary["errors"]:
        summary["noteworthy"] = True

    return summary


def _render_markdown(summary: dict) -> str:
    lines = ["## Weekly SEO Analysis", ""]

    dt = summary["stages"].get("duplicate_titles")
    if dt:
        lines.append(f"**Duplicate titles**: {dt['new_group_count']} new group(s) "
                      f"since baseline ({dt['total_current_groups']} total tracked)")
        for g in dt["new_groups"]:
            lines.append(f"  - `{g}`")

    kg = summary["stages"].get("keyword_gaps")
    if kg:
        lines.append(f"**Keyword gaps**: {kg['investigate_count']} investigate-worthy "
                      f"({kg['structural_count']} structural, not actionable)")
        for c in kg["top_investigate"][:5]:
            lines.append(f"  - `{c['gsc_url']}` ({c['total_impressions']} impressions)")

    fg = summary["stages"].get("frontmatter_grounding")
    if fg:
        lines.append(f"**Frontmatter grounding** (informational): {fg['total_kb_pages']} KB pages, "
                      f"{fg['pages_meeting_min_5_count']} meet the >=5-keyword count, "
                      f"sources={fg['by_grounded_source']}")

    tc = summary["stages"].get("title_consistency")
    if tc:
        lines.append(f"**Title consistency** (informational, tracked via the frozen pilot): "
                      f"{tc['warn_count']}/{tc['total_evaluated']} WARN")

    if summary["errors"]:
        lines.append("")
        lines.append("**Errors**:")
        for e in summary["errors"]:
            lines.append(f"  - {e}")

    return "\n".join(lines)


def main() -> int:
    summary = run()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "weekly_analysis_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    markdown = _render_markdown(summary)
    (REPORTS_DIR / "weekly_analysis_summary.md").write_text(markdown, encoding="utf-8")
    print(markdown)

    if summary["errors"]:
        return 2
    return 1 if summary["noteworthy"] else 0


if __name__ == "__main__":
    sys.exit(main())
