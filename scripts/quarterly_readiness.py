"""quarterly_readiness.py — Simulate quarterly review scoring locally.

Usage:
    python scripts/quarterly_readiness.py [--output-dir <dir>] [--no-tests]

Exit codes:
    0  READY — estimated score >= 60
    1  NOT_READY — estimated score < 60
    2  ERROR — could not run assessment

Output:
    reports/score-readiness-YYYY-MM-DD.md
    stdout: scored summary

Scoring dimensions (mirrors inferred quarterly rubric):
    Testing         0-100  (test pass rate, failure-mode coverage)
    Code Structure  0-100  (duplication signals, package org)
    Delivery Evid   0-100  (CI present, commit provenance, evidence files)
    Governance      0-100  (skill registry valid, hooks installed, AGENTS.md present)
    Confidence      0 or -2 penalty (unverified claims in docs)
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TODAY = date.today().isoformat()

# Discover user site-packages for pytest access (Windows installs pytest there)
_USER_SITE = None
try:
    import site as _site
    _user_sp = _site.getusersitepackages()
    if _user_sp and Path(_user_sp).is_dir():
        _USER_SITE = _user_sp
except Exception:
    pass


# ---------------------------------------------------------------------------
# Dimension scorers
# ---------------------------------------------------------------------------

def score_testing(repo_root: Path, run_tests: bool) -> tuple[float, list[str]]:
    """Score 0-100 based on test pass rate and failure-mode coverage."""
    notes = []
    if not run_tests:
        notes.append("NOTE: tests not run (--no-tests); using file-count heuristic")
        test_files = list((repo_root / "tests").glob("test_*.py"))
        base = min(60.0, 40.0 + len(test_files) * 0.5)
        return base, notes

    # Build env with user site-packages for pytest discovery
    env = dict(os.environ)
    if _USER_SITE:
        env["PYTHONPATH"] = _USER_SITE + os.pathsep + env.get("PYTHONPATH", "")

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "--tb=no", "-q",
             "-m", "not scout", "--ignore=tests/test_e2e_pipeline.py"],
            capture_output=True, text=True, timeout=180,
            cwd=str(repo_root), env=env,
        )
        output = result.stdout + result.stderr
        # Parse "X passed, Y failed, Z skipped"
        m = re.search(r"(\d+) passed", output)
        passed = int(m.group(1)) if m else 0
        m = re.search(r"(\d+) failed", output)
        failed = int(m.group(1)) if m else 0
        total = passed + failed
        if total == 0:
            notes.append("WARN: no tests collected")
            return 40.0, notes

        pass_rate = passed / total
        score = pass_rate * 75.0  # 75 max from pass rate

        # Bonus: failure-mode tests present
        fm_count = 0
        for name in ["fallback", "degraded", "missing", "invalid", "failure", "stale", "error"]:
            fm_result = subprocess.run(
                [sys.executable, "-m", "pytest", "tests/", "--co", "-q",
                 "-k", name, "-m", "not scout"],
                capture_output=True, text=True, timeout=30, cwd=str(repo_root), env=env,
            )
            m = re.search(r"(\d+) test", fm_result.stdout)
            if m:
                fm_count += int(m.group(1))
        bonus = min(25.0, fm_count * 1.5)
        score += bonus

        notes.append(f"Tests: {passed} passed, {failed} failed (pass_rate={pass_rate:.1%})")
        notes.append(f"Failure-mode tests detected: ~{fm_count} (bonus: +{bonus:.1f})")
        if failed > 0:
            notes.append(f"WARN: {failed} test failure(s) detected — fix before review")
        return min(100.0, score), notes
    except Exception as exc:
        notes.append(f"ERROR running tests: {exc}")
        return 40.0, notes


def score_delivery_evidence(repo_root: Path) -> tuple[float, list[str]]:
    """Score 0-100 based on CI, commit provenance, evidence files."""
    notes = []
    score = 0.0

    # CI workflow present
    ci_path = repo_root / ".github" / "workflows" / "skill-governance.yml"
    if ci_path.exists():
        score += 30.0
        notes.append("PASS: CI workflow present (.github/workflows/skill-governance.yml)")
    else:
        notes.append("FAIL: CI workflow absent — add .github/workflows/skill-governance.yml")

    # Git log: commits with "Skills invoked:" in last 90 days
    try:
        cutoff = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
        result = subprocess.run(
            ["git", "log", f"--after={cutoff}", "--format=%s", "--", "content/"],
            capture_output=True, text=True, timeout=15, cwd=str(repo_root),
        )
        content_commits = [l for l in result.stdout.strip().split("\n") if l]
        with_provenance = [l for l in content_commits if "Skills invoked:" in l]
        if content_commits:
            rate = len(with_provenance) / len(content_commits)
            score += rate * 30.0
            notes.append(f"Provenance: {len(with_provenance)}/{len(content_commits)} content commits have 'Skills invoked:' ({rate:.0%})")
        else:
            score += 20.0  # no content commits in window = not penalized
            notes.append("NOTE: no content/ commits in last 90 days (not penalized)")
    except Exception as exc:
        notes.append(f"WARN: could not check git provenance: {exc}")

    # Evidence files present
    evidence_dir = repo_root / "evidence"
    if evidence_dir.exists():
        pef_files = list(evidence_dir.glob("**/pef.json"))
        if pef_files:
            score += 20.0
            notes.append(f"PASS: {len(pef_files)} PEF evidence file(s) found in evidence/")
        else:
            notes.append("WARN: evidence/ exists but contains no pef.json files")
            score += 5.0
    else:
        notes.append("NOTE: evidence/ directory absent (expected for clean repo state)")
        score += 10.0

    # STATUS.md present and recently updated
    status_path = repo_root / "reports" / "STATUS.md"
    if status_path.exists():
        score += 10.0
        notes.append("PASS: reports/STATUS.md present")
    else:
        notes.append("WARN: reports/STATUS.md absent")

    # ops.log present
    ops_log = repo_root / "reports" / "ops.log"
    if ops_log.exists():
        score += 10.0
        notes.append("PASS: reports/ops.log present")
    else:
        notes.append("NOTE: reports/ops.log absent (created when skills run)")

    return min(100.0, score), notes


def score_governance(repo_root: Path) -> tuple[float, list[str]]:
    """Score 0-100 based on AGENTS.md, skill registry, hooks."""
    notes = []
    score = 0.0

    # AGENTS.md present
    if (repo_root / "AGENTS.md").exists():
        score += 25.0
        notes.append("PASS: AGENTS.md present")

    # Skill registry valid
    registry_path = repo_root / "skills" / "registry.yaml"
    if registry_path.exists():
        try:
            result = subprocess.run(
                [sys.executable, "scripts/validate_skills.py"],
                capture_output=True, text=True, timeout=30, cwd=str(repo_root),
            )
            if result.returncode == 0:
                score += 25.0
                notes.append("PASS: skill registry validates")
            else:
                notes.append(f"WARN: skill registry validation failed: {result.stdout[:200]}")
                score += 10.0
        except Exception as exc:
            notes.append(f"WARN: could not validate skill registry: {exc}")
    else:
        notes.append("FAIL: skills/registry.yaml absent")

    # Hooks installed
    hooks_dir = repo_root / ".git" / "hooks"
    commit_msg_hook = hooks_dir / "commit-msg"
    pre_commit_hook = hooks_dir / "pre-commit"
    if commit_msg_hook.exists():
        score += 25.0
        notes.append("PASS: commit-msg hook installed")
    else:
        notes.append("WARN: commit-msg hook not installed — run scripts/install-hooks.sh")
    if pre_commit_hook.exists():
        score += 25.0
        notes.append("PASS: pre-commit hook installed")
    else:
        notes.append("NOTE: pre-commit hook not installed")

    return min(100.0, score), notes


def score_code_structure(repo_root: Path) -> tuple[float, list[str]]:
    """Score 0-100 based on duplication signals and package organisation."""
    notes = []
    score = 60.0  # base (current state)

    # pyproject.toml present (package boundary)
    if (repo_root / "pyproject.toml").exists():
        score += 15.0
        notes.append("PASS: pyproject.toml present (package boundary)")
    else:
        notes.append("WARN: pyproject.toml absent — Phase 2 work needed")

    # Hardcoded paths in scripts
    try:
        result = subprocess.run(
            ["grep", "-rn", 'Path("evidence")', "scripts/"],
            capture_output=True, text=True, cwd=str(repo_root),
        )
        hardcoded = len(result.stdout.strip().split("\n")) if result.stdout.strip() else 0
        if hardcoded > 0:
            score -= 5.0
            notes.append(f"WARN: {hardcoded} hardcoded Path(\"evidence\") in scripts/ — fix in Phase 2")
        else:
            notes.append("PASS: no hardcoded Path(\"evidence\") in scripts/")
    except Exception:
        pass

    # Duplicate launcher code — penalised unless a boundary adapter is present
    adapter_path = repo_root / "scripts" / "launcher_adapter.py"
    scout_path = repo_root / "scripts" / "scout.py"
    if adapter_path.exists():
        score += 10.0
        scout_lines = 0
        if scout_path.exists():
            scout_lines = len(scout_path.read_text(encoding="utf-8", errors="ignore").splitlines())
        notes.append(
            f"PASS: launcher boundary explicitly managed (launcher_adapter.py); "
            f"scout.py is {scout_lines} lines"
        )
    elif scout_path.exists():
        scout_lines = len(scout_path.read_text(encoding="utf-8", errors="ignore").splitlines())
        if scout_lines > 1500:
            notes.append(f"WARN: scripts/scout.py is {scout_lines} lines — launcher duplication risk")
            score -= 5.0
        else:
            notes.append(f"NOTE: scripts/scout.py is {scout_lines} lines")

    return min(100.0, max(0.0, score)), notes


def score_confidence(repo_root: Path) -> tuple[float, list[str]]:
    """Return confidence adjustment (0 = no penalty, -2 = medium penalty)."""
    notes = []
    # Check if verify_claims report exists and shows zero critical unverified claims
    claim_report = repo_root / "reports"
    claim_files = list(claim_report.glob("claim-coverage-*.md"))
    if claim_files:
        latest = max(claim_files, key=lambda p: p.stat().st_mtime)
        content = latest.read_text(encoding="utf-8")
        if "Critical unverified | 0" in content or "0 critical" in content:
            notes.append(f"PASS: claim coverage report shows zero critical unverified claims ({latest.name})")
            return 0.0, notes
        else:
            notes.append(f"WARN: claim coverage report has unverified claims ({latest.name})")
            return -2.0, notes
    else:
        # No claim coverage report → use heuristic
        # Check if core claims have tests
        critical_tests = [
            "test_path_guard.py",
            "test_pre_write.py",
            "test_no_downgrade_guard.py",
        ]
        missing = [t for t in critical_tests if not (repo_root / "tests" / t).exists()]
        if missing:
            notes.append(f"WARN: missing critical tests: {missing} → confidence penalty likely")
            return -2.0, notes
        else:
            notes.append("PASS: core claim tests present — confidence penalty unlikely")
            return 0.0, notes


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_assessment(repo_root: Path, run_tests: bool = True) -> dict:
    """Run all dimension scorers and return assessment dict."""
    testing_score, testing_notes = score_testing(repo_root, run_tests)
    delivery_score, delivery_notes = score_delivery_evidence(repo_root)
    governance_score, governance_notes = score_governance(repo_root)
    structure_score, structure_notes = score_code_structure(repo_root)
    confidence_adj, confidence_notes = score_confidence(repo_root)

    # Weighted overall (approximate rubric weights inferred from review)
    raw = (
        testing_score * 0.30 +
        delivery_score * 0.25 +
        governance_score * 0.20 +
        structure_score * 0.25
    )
    overall = raw + confidence_adj

    return {
        "date": TODAY,
        "dimensions": {
            "Testing": testing_score,
            "Delivery Evidence": delivery_score,
            "Governance": governance_score,
            "Code Structure": structure_score,
        },
        "confidence_adjustment": confidence_adj,
        "overall_estimate": round(overall, 1),
        "raw_before_penalty": round(raw, 1),
        "notes": {
            "Testing": testing_notes,
            "Delivery Evidence": delivery_notes,
            "Governance": governance_notes,
            "Code Structure": structure_notes,
            "Confidence": confidence_notes,
        },
        "ready": overall >= 60.0,
    }


def write_report(assessment: dict, output_dir: Path) -> Path:
    """Write Markdown report and return path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"score-readiness-{assessment['date']}.md"

    lines = [
        f"# Score Readiness Report — {assessment['date']}",
        "",
        "## Overall Estimate",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Overall (estimated) | **{assessment['overall_estimate']}** |",
        f"| Raw before penalty | {assessment['raw_before_penalty']} |",
        f"| Confidence adjustment | {assessment['confidence_adjustment']} |",
        f"| Readiness | {'READY (≥60)' if assessment['ready'] else 'NOT READY (<60)'} |",
        "",
        "## Dimension Scores",
        "",
        "| Dimension | Score |",
        "|-----------|-------|",
    ]
    for dim, score in assessment["dimensions"].items():
        lines.append(f"| {dim} | {score:.1f} |")

    lines += ["", "## Notes by Dimension", ""]
    for dim, notes in assessment["notes"].items():
        lines.append(f"### {dim}")
        for note in notes:
            lines.append(f"- {note}")
        lines.append("")

    lines += [
        "## Next Actions",
        "",
        "See `reports/TASK_BACKLOG.md` for prioritized improvement work.",
        "",
        f"*Generated by scripts/quarterly_readiness.py on {TODAY}*",
    ]

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Quarterly review readiness assessment")
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "reports"),
                        help="Directory for the readiness report (default: reports/)")
    parser.add_argument("--no-tests", action="store_true",
                        help="Skip running the test suite (faster, less accurate)")
    parser.add_argument("--json", action="store_true",
                        help="Output raw assessment JSON to stdout instead of report")
    args = parser.parse_args(argv)

    try:
        assessment = run_assessment(REPO_ROOT, run_tests=not args.no_tests)
    except Exception as exc:
        print(f"ERROR: assessment failed: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(assessment, indent=2))
    else:
        report_path = write_report(assessment, Path(args.output_dir))
        print(f"Score estimate: {assessment['overall_estimate']} "
              f"({'READY' if assessment['ready'] else 'NOT READY'})")
        print(f"Report: {report_path}")

        # Print dimension summary
        for dim, score in assessment["dimensions"].items():
            print(f"  {dim}: {score:.1f}")
        if assessment["confidence_adjustment"] != 0:
            print(f"  Confidence penalty: {assessment['confidence_adjustment']}")

    return 0 if assessment["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
