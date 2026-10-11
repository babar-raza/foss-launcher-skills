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
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
from _common import REPO_ROOT, base_args, safe_emit


def _parse_eval_timestamp(filename: str) -> str:
    """Extract sortable timestamp from eval-YYYYMMDD-HHMMSS.json filename."""
    m = re.match(r"eval-(\d{8}-\d{6})\.json$", filename)
    return m.group(1) if m else ""


def _filter_eval_files(
    eval_files: list[Path],
    max_age_days: int | None = None,
) -> list[Path]:
    """Filter eval files by age if max_age_days is set."""
    if max_age_days is None:
        return eval_files
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    cutoff_str = cutoff.strftime("%Y%m%d-%H%M%S")
    return [f for f in eval_files if _parse_eval_timestamp(f.name) >= cutoff_str]


def _load_manifest_grades(root: Path) -> dict[str, str]:
    """Load {normalized_path -> grade} from reports/grade_manifest.json.

    Returns empty dict if manifest is absent or unreadable.
    Paths are normalised to forward-slash absolute strings.
    """
    manifest_path = root / "reports" / "grade_manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        # Each value is a dict with a "grade" key (A|B|C|D|F)
        return {k.replace("\\", "/"): v.get("grade", "") for k, v in data.items()
                if isinstance(v, dict)}
    except Exception:
        return {}


_GRADE_RE = re.compile(r"^grade:\s*([A-F])", re.MULTILINE)


def _frontmatter_grade(page_path: str) -> str:
    """Return the grade from a page's YAML frontmatter, or '' if unreadable/absent."""
    try:
        text = Path(page_path).read_text(encoding="utf-8", errors="replace")
        m = _GRADE_RE.search(text)
        return m.group(1) if m else ""
    except Exception:
        return ""


def validate(repo_root=None, *, dedup: bool = True, max_age_days: int | None = None):
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

        eval_files = sorted(eval_dir.glob("eval-*.json"))
        eval_files = _filter_eval_files(eval_files, max_age_days)

        # --- Phase 1: collect per-page findings with report timestamps ---
        # page_path -> {timestamp: str, fails: int, warns: int}
        page_latest: dict[str, dict] = {}

        for eval_file in eval_files:
            result["eval_reports_found"].append(eval_file.name)
            file_ts = _parse_eval_timestamp(eval_file.name)
            try:
                data = json.loads(eval_file.read_text(encoding="utf-8"))
                summary = data.get("summary", {})
                by_sev = summary.get("by_severity", {})
                for sev, count in by_sev.items():
                    severity_totals[sev] += count
                pages_clean_total += summary.get("pages_clean", 0)
                pages_with_findings_total += summary.get("pages_with_findings", 0)
                pages_evaluated_total += summary.get("pages_evaluated", 0)

                # Collect per-page findings from this report
                report_page_fails: dict[str, int] = defaultdict(int)
                report_page_warns: dict[str, int] = defaultdict(int)
                for finding in data.get("findings", []):
                    page_path = finding.get("file", "unknown")
                    level = finding.get("level", "").upper()
                    if level == "FAIL":
                        report_page_fails[page_path] += 1
                    elif level == "WARN":
                        report_page_warns[page_path] += 1

                # For dedup mode: only keep findings from the latest report per page
                all_pages = set(report_page_fails) | set(report_page_warns)
                for page_path in all_pages:
                    existing = page_latest.get(page_path)
                    if dedup:
                        if existing is None or file_ts > existing["timestamp"]:
                            page_latest[page_path] = {
                                "timestamp": file_ts,
                                "fails": report_page_fails.get(page_path, 0),
                                "warns": report_page_warns.get(page_path, 0),
                            }
                    else:
                        # Legacy accumulation mode
                        if existing is None:
                            page_latest[page_path] = {
                                "timestamp": file_ts,
                                "fails": 0,
                                "warns": 0,
                            }
                        page_latest[page_path]["fails"] += report_page_fails.get(page_path, 0)
                        page_latest[page_path]["warns"] += report_page_warns.get(page_path, 0)
            except Exception as exc:
                result["warnings"].append(f"Could not parse {eval_file.name}: {exc}")

        result["grade_summary"] = {
            "pages_evaluated": pages_evaluated_total,
            "pages_clean": pages_clean_total,
            "pages_with_findings": pages_with_findings_total,
            "severity_totals": dict(severity_totals),
        }

        # Load grade manifest to cross-reference accepted grades.
        # Pages with grade A, B, or C in grade_manifest.json are NOT actionable
        # (C = accepted evaluator ceiling; A/B = healed). Only D/F pages need healing.
        manifest_grades = _load_manifest_grades(root)

        # Pages needing heal: at least one FAIL-level finding AND explicitly grade D/F.
        # Pages graded A/B/C (accepted states) are excluded. Pages not in the grade
        # manifest are checked via frontmatter grade as a fallback. Pages whose files no
        # longer exist (ghost entries in old eval reports) are skipped unconditionally.
        for page_path, info in sorted(page_latest.items()):
            fail_count = info["fails"]
            if fail_count > 0:
                # Skip ghost entries — file was deleted since the eval report was written.
                if not Path(page_path).exists():
                    continue
                # Normalise path for manifest lookup (backslash → forward slash)
                norm_path = page_path.replace("\\", "/")
                manifest_grade = manifest_grades.get(norm_path, "")
                if manifest_grade:
                    # Manifest is authoritative: skip A/B/C, include D/F only.
                    if manifest_grade in ("A", "B", "C"):
                        continue
                else:
                    # Page not in manifest — fall back to frontmatter grade.
                    # Only flag if frontmatter explicitly says D or F; all other states
                    # (A/B/C, no grade, structural index pages) are not actionable here.
                    fm_grade = _frontmatter_grade(page_path)
                    if fm_grade not in ("D", "F"):
                        continue
                result["pages_needing_heal"].append({
                    "path": page_path,
                    "grade": "F" if fail_count >= 3 else "D",
                    "fail_count": fail_count,
                    "warn_count": info["warns"],
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
    parser.add_argument(
        "--max-age-days", type=int, default=None,
        help="Only include eval reports from the last N days (default: all)",
    )
    parser.add_argument(
        "--no-dedup", action="store_true",
        help="Disable per-page deduplication (legacy accumulation mode)",
    )
    args = parser.parse_args()

    data = validate(dedup=not args.no_dedup, max_age_days=args.max_age_days)

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
