"""
validate.py — Assess evidence quality from reports/content_eval and reports/audit.

Eval JSON schema (reports/content_eval/eval-*.json):
  {schema_version, generated_at, scope,
   summary: {total_findings, pages_evaluated, pages_clean, pages_with_findings,
             by_severity: {FAIL, WARN, INFO}, by_category: {...}},
   findings: [{id, level, category, file, line, message, suggestion, evaluator}]}

Grade signal is derived from severity counts (FAIL/WARN/INFO) and per-page findings.
Pages with FAIL-level findings -> pages_needing_heal.

Handles missing report directories gracefully with warnings (not fatal errors).
Exit 0 always (missing reports = warnings). Exit 1 on fatal schema errors only.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
from _common import REPO_ROOT, base_args, safe_emit


def validate(repo_root=None):
    root = Path(repo_root or REPO_ROOT)
    reports_dir = root / "reports"

    result = {
        "grade_summary": {},
        "pages_needing_heal": [],
        "api_audit_status": {},
        "eval_reports_found": [],
        "audit_reports_found": [],
        "warnings": [],
    }

    # ---- Quality signal from reports/content_eval/ ----
    eval_dir = reports_dir / "content_eval"
    if not eval_dir.exists():
        result["warnings"].append(
            f"reports/content_eval/ not found at {eval_dir} — skipping grade assessment"
        )
    else:
        severity_totals: dict = defaultdict(int)
        pages_clean_total = 0
        pages_with_findings_total = 0
        pages_evaluated_total = 0
        # Track per-page FAIL counts across all reports
        page_fail_counts: dict = defaultdict(int)
        page_warn_counts: dict = defaultdict(int)

        for eval_file in sorted(eval_dir.glob("eval-*.json")):
            result["eval_reports_found"].append(eval_file.name)
            try:
                data = json.loads(eval_file.read_text(encoding="utf-8"))
                summary = data.get("summary", {})
                # Accumulate severity totals from summary.by_severity (FAIL/WARN/INFO)
                by_sev = summary.get("by_severity", {})
                for sev, count in by_sev.items():
                    severity_totals[sev] += count
                pages_clean_total += summary.get("pages_clean", 0)
                pages_with_findings_total += summary.get("pages_with_findings", 0)
                pages_evaluated_total += summary.get("pages_evaluated", 0)
                # Build per-page heal list from findings array
                for finding in data.get("findings", []):
                    page_path = finding.get("file", "unknown")
                    level = finding.get("level", "").upper()
                    if level == "FAIL":
                        page_fail_counts[page_path] += 1
                    elif level == "WARN":
                        page_warn_counts[page_path] += 1
            except Exception as exc:
                result["warnings"].append(f"Could not parse {eval_file.name}: {exc}")

        result["grade_summary"] = {
            "pages_evaluated": pages_evaluated_total,
            "pages_clean": pages_clean_total,
            "pages_with_findings": pages_with_findings_total,
            "severity_totals": dict(severity_totals),
        }

        # Pages needing heal: at least one FAIL-level finding
        for page_path, fail_count in sorted(page_fail_counts.items()):
            result["pages_needing_heal"].append({
                "path": page_path,
                "grade": "F" if fail_count >= 3 else "D",
                "fail_count": fail_count,
                "warn_count": page_warn_counts.get(page_path, 0),
            })

    # ---- API audit from reports/audit/ ----
    audit_dir = reports_dir / "audit"
    if not audit_dir.exists():
        result["warnings"].append(
            f"reports/audit/ not found at {audit_dir} — skipping API audit assessment"
        )
    else:
        audit_counts: dict = defaultdict(int)
        for audit_file in sorted(audit_dir.glob("batch-audit-*.md")):
            result["audit_reports_found"].append(audit_file.name)
            try:
                text = audit_file.read_text(encoding="utf-8")
                audit_counts["FAIL"] += len(re.findall(r"\bFAIL\b", text))
                audit_counts["WARN"] += len(re.findall(r"\bWARN\b", text))
                audit_counts["PASS"] += len(re.findall(r"\bPASS\b", text))
            except Exception as exc:
                result["warnings"].append(f"Could not parse {audit_file.name}: {exc}")
        result["api_audit_status"] = dict(audit_counts)

    return result


def main():
    parser = base_args("Assess evidence quality from reports/ directories")
    args = parser.parse_args()

    data = validate()

    summary = {
        "status": "VALIDATION_COMPLETE",
        "eval_files_found": len(data["eval_reports_found"]),
        "audit_files_found": len(data["audit_reports_found"]),
        "pages_needing_heal_count": len(data["pages_needing_heal"]),
        "warning_count": len(data["warnings"]),
        **data,
    }

    if args.output:
        safe_emit(summary, args.output)
        print(f"Validation complete: {summary['eval_files_found']} eval files, "
              f"{summary['pages_needing_heal_count']} pages need healing")
        print(f"Written to {args.output}")
    else:
        print(json.dumps(summary, indent=2, default=str))

    return 0


if __name__ == "__main__":
    sys.exit(main())
