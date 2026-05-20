# Adapted from aspose.org
"""verify.py — Healing verification with regression detection.

Re-evaluates modified files after healing and compares before/after
finding counts to detect regressions (new FAILs that weren't there before).

Usage (Python import):
    from verify import verify_healing

    report = verify_healing(
        healed_files=["content/docs.aspose.org/en/slides/net/features.md"],
        before_findings=before_findings_list,
    )
    if report.regression_detected:
        print(f"REGRESSION: {len(report.new_fails)} new FAILs introduced")

Usage (CLI):
    python scripts/pipeline/commands/healing/verify.py --before-report reports/eval-before.json \\
        --files content/docs.aspose.org/en/slides/net/features.md
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from content_eval.models import Finding, compute_grade


_GRADE_ORDER = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}


def _regression_severity(
    new_fail_count: int,
    resolved_fail_count: int,
    before_grade: str,
    after_grade: str,
) -> str:
    """Classify regression severity.

    Returns:
        "none"     — no new FAILs
        "minor"    — new FAILs exist but net improvement (more resolved than new)
        "moderate" — new FAILs with no net improvement, grade unchanged
        "critical" — new FAILs AND grade decreased
    """
    if new_fail_count == 0:
        return "none"
    bg = _GRADE_ORDER.get(before_grade, 0)
    ag = _GRADE_ORDER.get(after_grade, 0)
    if ag < bg:
        return "critical"
    if resolved_fail_count > new_fail_count:
        return "minor"
    return "moderate"


@dataclass(slots=True)
class VerifyResult:
    """Result of healing verification for a single page."""

    filepath: str
    before_grade: str
    after_grade: str
    before_fail_count: int
    after_fail_count: int
    before_warn_count: int
    after_warn_count: int
    new_fails: list[dict] = field(default_factory=list)
    new_warns: list[dict] = field(default_factory=list)
    resolved_fails: list[dict] = field(default_factory=list)
    resolved_warns: list[dict] = field(default_factory=list)

    @property
    def regression_detected(self) -> bool:
        return len(self.new_fails) > 0

    @property
    def improved(self) -> bool:
        return self.after_fail_count < self.before_fail_count

    @property
    def regression_severity(self) -> str:
        """Classify severity: none, minor, moderate, critical."""
        return _regression_severity(
            len(self.new_fails), len(self.resolved_fails),
            self.before_grade, self.after_grade,
        )


@dataclass
class HealingReport:
    """Aggregated healing verification report."""

    pages_verified: int = 0
    total_before_fails: int = 0
    total_after_fails: int = 0
    total_before_warns: int = 0
    total_after_warns: int = 0
    total_new_fails: int = 0
    total_resolved_fails: int = 0
    regression_detected: bool = False
    regression_severity: str = "none"
    page_results: list[VerifyResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pages_verified": self.pages_verified,
            "total_before_fails": self.total_before_fails,
            "total_after_fails": self.total_after_fails,
            "total_before_warns": self.total_before_warns,
            "total_after_warns": self.total_after_warns,
            "total_new_fails": self.total_new_fails,
            "total_resolved_fails": self.total_resolved_fails,
            "regression_detected": self.regression_detected,
            "regression_severity": self.regression_severity,
            "pages": [
                {
                    "filepath": r.filepath,
                    "before_grade": r.before_grade,
                    "after_grade": r.after_grade,
                    "before_fails": r.before_fail_count,
                    "after_fails": r.after_fail_count,
                    "new_fails": r.new_fails,
                    "resolved_fails": r.resolved_fails,
                    "regression": r.regression_detected,
                    "regression_severity": r.regression_severity,
                    "improved": r.improved,
                }
                for r in self.page_results
            ],
        }


def _finding_to_dict(f: Finding) -> dict:
    """Convert a Finding to a serializable dict."""
    return {
        "id": f.id,
        "level": f.level,
        "category": f.category,
        "message": f.message,
        "line_no": f.line_no,
        "evaluator": f.evaluator,
    }


def _findings_from_dicts(dicts: list[dict]) -> list[Finding]:
    """Reconstruct Finding objects from dicts (e.g., from JSON report)."""
    findings = []
    for d in dicts:
        findings.append(Finding(
            level=d.get("level", "FAIL"),
            category=d.get("category", ""),
            filepath=d.get("filepath", ""),
            line_no=d.get("line_no", 0) or d.get("line", 0),
            message=d.get("message", ""),
            suggestion=d.get("suggestion", ""),
            evaluator=d.get("evaluator", ""),
            cause_class=d.get("cause_class", ""),
        ))
    return findings


def _compare_findings(
    before: list[Finding],
    after: list[Finding],
) -> tuple[list[Finding], list[Finding], list[Finding], list[Finding]]:
    """Compare before/after findings by ID.

    Returns (new_fails, new_warns, resolved_fails, resolved_warns).
    """
    before_ids = {f.id: f for f in before}
    after_ids = {f.id: f for f in after}

    before_set = set(before_ids.keys())
    after_set = set(after_ids.keys())

    added_ids = after_set - before_set
    removed_ids = before_set - after_set

    new_fails = [after_ids[fid] for fid in added_ids if after_ids[fid].level == "FAIL"]
    new_warns = [after_ids[fid] for fid in added_ids if after_ids[fid].level == "WARN"]
    resolved_fails = [before_ids[fid] for fid in removed_ids if before_ids[fid].level == "FAIL"]
    resolved_warns = [before_ids[fid] for fid in removed_ids if before_ids[fid].level == "WARN"]

    return new_fails, new_warns, resolved_fails, resolved_warns


def verify_healing(
    healed_files: list[str] | set[str],
    *,
    before_findings: list[Finding] | None = None,
    before_report_path: Path | None = None,
    after_findings: list[Finding] | None = None,
    after_report_path: Path | None = None,
) -> HealingReport:
    """Verify that healing improved page quality.

    Compares before and after findings for healed files and detects regressions.

    Args:
        healed_files: Paths of files that were healed.
        before_findings: Pre-healing findings (or load from before_report_path).
        before_report_path: Path to JSON eval report from before healing.
        after_findings: Post-healing findings (or load from after_report_path).
        after_report_path: Path to JSON eval report from after healing.

    Returns:
        HealingReport with per-page results and regression detection.
    """
    healed_set = {str(Path(f)) for f in healed_files}

    # Load before findings
    if before_findings is None and before_report_path is not None:
        raw = json.loads(before_report_path.read_text(encoding="utf-8"))
        before_findings = _findings_from_dicts(raw.get("findings", []))
    if before_findings is None:
        before_findings = []

    # Load after findings
    if after_findings is None and after_report_path is not None:
        raw = json.loads(after_report_path.read_text(encoding="utf-8"))
        after_findings = _findings_from_dicts(raw.get("findings", []))
    if after_findings is None:
        after_findings = []

    # Group findings by file
    before_by_file: dict[str, list[Finding]] = {}
    for f in before_findings:
        fp = str(Path(f.filepath))
        before_by_file.setdefault(fp, []).append(f)

    after_by_file: dict[str, list[Finding]] = {}
    for f in after_findings:
        fp = str(Path(f.filepath))
        after_by_file.setdefault(fp, []).append(f)

    report = HealingReport()

    for filepath in sorted(healed_set):
        bf = before_by_file.get(filepath, [])
        af = after_by_file.get(filepath, [])

        bf_fails = [f for f in bf if f.level == "FAIL"]
        bf_warns = [f for f in bf if f.level == "WARN"]
        af_fails = [f for f in af if f.level == "FAIL"]
        af_warns = [f for f in af if f.level == "WARN"]

        new_fails, new_warns, resolved_fails, resolved_warns = _compare_findings(bf, af)

        before_grade = compute_grade(len(bf_fails), len(bf_warns))
        after_grade = compute_grade(len(af_fails), len(af_warns))

        result = VerifyResult(
            filepath=filepath,
            before_grade=before_grade,
            after_grade=after_grade,
            before_fail_count=len(bf_fails),
            after_fail_count=len(af_fails),
            before_warn_count=len(bf_warns),
            after_warn_count=len(af_warns),
            new_fails=[_finding_to_dict(f) for f in new_fails],
            new_warns=[_finding_to_dict(f) for f in new_warns],
            resolved_fails=[_finding_to_dict(f) for f in resolved_fails],
            resolved_warns=[_finding_to_dict(f) for f in resolved_warns],
        )

        report.page_results.append(result)
        report.pages_verified += 1
        report.total_before_fails += result.before_fail_count
        report.total_after_fails += result.after_fail_count
        report.total_before_warns += result.before_warn_count
        report.total_after_warns += result.after_warn_count
        report.total_new_fails += len(new_fails)
        report.total_resolved_fails += len(resolved_fails)

        if result.regression_detected:
            report.regression_detected = True

    # Compute aggregate severity (worst across all pages)
    if report.regression_detected:
        severity_order = {"none": 0, "minor": 1, "moderate": 2, "critical": 3}
        worst = max(
            (r.regression_severity for r in report.page_results),
            key=lambda s: severity_order.get(s, 0),
        )
        report.regression_severity = worst

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="verify",
        description="Verify healing results — detect regressions in modified files.",
    )
    parser.add_argument("--before-report", required=True, help="Path to pre-healing eval report JSON")
    parser.add_argument("--after-report", required=True, help="Path to post-healing eval report JSON")
    parser.add_argument("--files", nargs="+", required=True, help="Healed file paths")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args(argv)

    report = verify_healing(
        healed_files=args.files,
        before_report_path=Path(args.before_report),
        after_report_path=Path(args.after_report),
    )

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(f"Healing Verification: {report.pages_verified} pages")
        print(f"  FAILs: {report.total_before_fails} → {report.total_after_fails} "
              f"({report.total_resolved_fails} resolved, {report.total_new_fails} new)")
        print(f"  WARNs: {report.total_before_warns} → {report.total_after_warns}")
        if report.regression_detected:
            sev = report.regression_severity.upper()
            print(f"\n  REGRESSION DETECTED [{sev}] — new FAILs introduced:")
            for pr in report.page_results:
                if pr.new_fails:
                    print(f"    [{pr.filepath}] severity={pr.regression_severity}")
                for nf in pr.new_fails:
                    print(f"      {nf['category']}: {nf['message']}")
        else:
            print("\n  No regressions detected.")

        for pr in report.page_results:
            status = "IMPROVED" if pr.improved else ("REGRESSED" if pr.regression_detected else "UNCHANGED")
            print(f"\n  {pr.filepath}: {pr.before_grade}→{pr.after_grade} ({status})")

    return 1 if report.regression_detected else 0


if __name__ == "__main__":
    raise SystemExit(main())
