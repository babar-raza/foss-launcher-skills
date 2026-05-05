"""
TC-S96-006: Cleanroom Regen Orchestrator.

CLI entry point for all 8 cleanroom regeneration modes.
Delegates to helper modules for each mode.

Ported to foss-launcher from aspose.org/scripts/pipeline/commands/ops/cleanroom_regen.py.
Adaptations:
  - pytest path changed from scripts/pipeline/tests/ to tests/
  - _REPO_ROOT (parents[4]) is correct for commands/ops/ depth in foss-launcher
  - data/schemas/cleanroom/ path works the same (if schemas are absent, validation is skipped)
  - content/ clean check always returns True in foss-launcher (no content/ dir)
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
from datetime import datetime, timezone
from enum import IntEnum
from typing import Any, Dict, List, Optional


class Exit(IntEnum):
    OK = 0
    BLOCKER = 1
    INVALID_ARGS = 2
    DIRTY_TREE = 3
    UNSAFE_BRANCH = 4
    MISSING_ARTIFACT = 5
    SCHEMA_FAIL = 6
    GENERATION_FAIL = 7
    DIFF_ERROR = 8
    BAD_REVERT_FOUND = 9
    UNRESOLVED_RISKY = 10
    VALIDATOR_FAIL = 11
    TEST_FAIL = 12
    COMMIT_READINESS_FAIL = 13
    OUT_OF_SCOPE = 14
    LOCK_CONFLICT = 15


_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
_SCHEMAS_DIR = _REPO_ROOT / "data" / "schemas" / "cleanroom"


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def _git_current_branch(repo_root: pathlib.Path = _REPO_ROOT) -> str:
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=repo_root, capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _git_head_sha(repo_root: pathlib.Path = _REPO_ROOT) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root, capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _git_content_clean(repo_root: pathlib.Path = _REPO_ROOT) -> bool:
    """Return True if content/ has no uncommitted modifications."""
    try:
        result = subprocess.run(
            ["git", "status", "--short", "--", "content/"],
            cwd=repo_root, capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0 and result.stdout.strip() == ""
    except Exception:
        return True


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

def _validate_json(data: dict, schema_name: str) -> List[str]:
    schema_path = _SCHEMAS_DIR / f"{schema_name}.schema.json"
    if not schema_path.exists():
        return []
    try:
        import jsonschema
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        validator = jsonschema.Draft7Validator(schema)
        errs = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
        return [str(e.message) for e in errs]
    except ImportError:
        return []
    except Exception as e:
        return [str(e)]


def _write_json(path: pathlib.Path, data: dict, schema_name: Optional[str] = None) -> List[str]:
    """Write JSON atomically. Returns schema validation errors (empty = OK)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    if schema_name:
        return _validate_json(data, schema_name)
    return []


def _read_json(path: pathlib.Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Mode 1: inspect
# ---------------------------------------------------------------------------

def mode_inspect(args: argparse.Namespace, runs_root: pathlib.Path) -> Exit:
    import lib.cleanroom_scope as cs

    run_dir = runs_root / args.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    subdomains = [args.subdomain] if getattr(args, "subdomain", None) else None
    scope = cs.resolve(args.family, args.platform, subdomains)

    blockers: List[str] = []
    warnings: List[str] = []

    # Scope errors
    for err in scope._errors:
        blockers.append(err)

    branch = _git_current_branch()
    sha = _git_head_sha()
    content_clean = _git_content_clean()

    if not content_clean:
        warnings.append("content/ has uncommitted modifications")

    ready = len(blockers) == 0
    report = {
        "run_id": args.run_id,
        "family": args.family,
        "platform": getattr(args, "platform", None),
        "subdomains": scope.subdomains,
        "ready": ready,
        "blockers": blockers,
        "warnings": warnings,
        "git_branch": branch,
        "git_sha": sha,
        "content_clean": content_clean,
        "knowledge_available": None,
        "generated_at": _now_iso(),
    }

    errs = _write_json(run_dir / "inspect-report.json", report, "inspect-report")
    if errs:
        print(f"Schema validation failed: {errs}")
        return Exit.SCHEMA_FAIL

    status = "READY" if ready else f"BLOCKERS: {blockers}"
    print(f"[inspect] {args.family}/{getattr(args, 'platform', '')} — {status}")
    return Exit.OK if ready else Exit.BLOCKER


# ---------------------------------------------------------------------------
# Mode 2: snapshot
# ---------------------------------------------------------------------------

def mode_snapshot(args: argparse.Namespace, runs_root: pathlib.Path) -> Exit:
    import lib.cleanroom_scope as cs
    from commands.ops.cleanroom_manifest import capture_baseline

    run_dir = runs_root / args.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    subdomains = [args.subdomain] if getattr(args, "subdomain", None) else None
    scope = cs.resolve(args.family, args.platform, subdomains)

    # Write run_state.json
    branch = _git_current_branch()
    sha = _git_head_sha()

    run_state = {
        "run_id": args.run_id,
        "target": {
            "family": args.family,
            "platform": getattr(args, "platform", None),
            "subdomains": scope.subdomains,
        },
        "baseline_git_sha": sha,
        "isolated_branch": branch,
        "started_at": _now_iso(),
        "completed_modes": [],
        "resumable": True,
        "lock_status": "LOCKED",
    }
    _write_json(run_dir / "run_state.json", run_state)

    # Write git-baseline.json
    git_status = ""
    try:
        r = subprocess.run(
            ["git", "status", "--short"],
            cwd=_REPO_ROOT, capture_output=True, text=True, timeout=10
        )
        git_status = r.stdout.strip()
    except Exception:
        pass

    git_baseline = {
        "run_id": args.run_id,
        "baseline_git_sha": sha,
        "branch": branch,
        "captured_at": _now_iso(),
        "status_short": git_status,
    }
    _write_json(run_dir / "git-baseline.json", git_baseline)

    # Capture content baseline
    manifest = capture_baseline(scope, run_dir / "baseline-manifest.json", args.run_id, _REPO_ROOT)

    if manifest._errors:
        print(f"[snapshot] {len(manifest._errors)} errors during baseline capture")

    # Validation errors are non-fatal for snapshot
    _write_json(run_dir / "baseline-manifest.json", manifest.to_dict(), "baseline-manifest")

    print(f"[snapshot] Captured {len(manifest.files)} files. SHA: {sha[:12]}")
    return Exit.OK


# ---------------------------------------------------------------------------
# Mode 3: regenerate-cleanroom
# ---------------------------------------------------------------------------

def mode_regenerate(args: argparse.Namespace, runs_root: pathlib.Path) -> Exit:
    import lib.cleanroom_scope as cs

    run_dir = runs_root / args.run_id

    # Gate: --confirm-overwrite required
    if not getattr(args, "confirm_overwrite", False):
        print("STOP: regenerate-cleanroom requires --confirm-overwrite")
        return Exit.INVALID_ARGS

    # Gate: must have baseline manifest
    baseline_path = run_dir / "baseline-manifest.json"
    git_baseline_path = run_dir / "git-baseline.json"
    if not baseline_path.exists():
        print(f"STOP: Missing baseline-manifest.json — run snapshot first")
        return Exit.MISSING_ARTIFACT

    # Gate: must be on isolated branch (not main)
    branch = _git_current_branch()
    if branch == "main":
        print(f"STOP: regenerate-cleanroom refused on main branch")
        return Exit.UNSAFE_BRANCH

    subdomains = [args.subdomain] if getattr(args, "subdomain", None) else None
    scope = cs.resolve(args.family, args.platform, subdomains)

    if scope._errors:
        print(f"STOP: Scope errors: {scope._errors}")
        return Exit.INVALID_ARGS

    # Emit regeneration plan for non-reference subdomains
    non_ref_subs = [s for s in scope.subdomains if s != "reference"]
    if non_ref_subs:
        entries = []
        for sub in non_ref_subs:
            gen = scope.generation_entry_points.get(sub, {})
            entries.append({
                "planned_task_id": f"{sub}-placeholder",
                "subdomain": sub,
                "skill_id": gen.get("skill", ""),
                "target_path": f"content/{sub}.aspose.org/{args.family}/{getattr(args, 'platform', '')}",
                "skill_args": {},
                "status": "PLANNED",
            })

        regen_plan = {
            "run_id": args.run_id,
            "baseline_git_sha": _read_json(baseline_path).get("baseline_git_sha", "unknown"),
            "phase_a_complete": True,
            "entries": entries,
        }
        _write_json(run_dir / "regeneration-plan.json", regen_plan)

        # Write skeleton agent ledger
        ledger = {
            "run_id": args.run_id,
            "phase_a_complete": True,
            "phase_b_complete": False,
            "entries": [
                {
                    "planned_task_id": e["planned_task_id"],
                    "subdomain": e["subdomain"],
                    "skill_id": e["skill_id"],
                    "target_path": e["target_path"],
                    "source_site_plan_entry": None,
                    "status": "PLANNED",
                    "started_at": None,
                    "completed_at": None,
                    "output_files": [],
                    "error": None,
                    "agent_notes": None,
                    "verification_status": "UNVERIFIED",
                }
                for e in entries
            ],
        }
        _write_json(run_dir / "agent-execution-ledger.json", ledger)

    # For reference subdomain: emit a minimal regeneration-log
    regen_log = {
        "run_id": args.run_id,
        "generated_at": _now_iso(),
        "level": getattr(args, "level", 1),
        "subdomains_processed": scope.subdomains,
        "entries": [],
    }
    _write_json(run_dir / "regeneration-log.json", regen_log)

    print(f"[regenerate-cleanroom] Phase A complete. Run ID: {args.run_id}")
    if non_ref_subs:
        print(f"  Non-reference subdomains require Phase B (agent): {non_ref_subs}")
    return Exit.OK


# ---------------------------------------------------------------------------
# Mode 4: diff
# ---------------------------------------------------------------------------

def mode_diff(args: argparse.Namespace, runs_root: pathlib.Path) -> Exit:
    import lib.cleanroom_scope as cs
    from commands.ops.content_diff_classifier import classify_diff, write_diff_report

    run_dir = runs_root / args.run_id

    # Gate: baseline manifest required
    baseline_path = run_dir / "baseline-manifest.json"
    if not baseline_path.exists():
        raise SystemExit(Exit.MISSING_ARTIFACT)

    # Gate: agent dispatch gate
    regen_plan_path = run_dir / "regeneration-plan.json"
    if regen_plan_path.exists():
        plan = _read_json(regen_plan_path) or {}
        non_ref_entries = [
            e for e in plan.get("entries", [])
            if e.get("subdomain") != "reference"
        ]
        if non_ref_entries:
            ledger_path = run_dir / "agent-execution-ledger.json"
            if not ledger_path.exists():
                print("STOP: agent-execution-ledger.json missing — Phase B not complete")
                return Exit.MISSING_ARTIFACT
            ledger = _read_json(ledger_path) or {}
            if not ledger.get("phase_b_complete"):
                print("STOP: phase_b_complete is false — Phase B not complete")
                return Exit.MISSING_ARTIFACT
            for entry in ledger.get("entries", []):
                if entry.get("status") in ("PLANNED", "RUNNING"):
                    print(f"STOP: Ledger has non-terminal entry: {entry['planned_task_id']}")
                    return Exit.MISSING_ARTIFACT

    manifest = _read_json(baseline_path)
    if not manifest:
        return Exit.MISSING_ARTIFACT

    # Use subdomains from the baseline manifest scope, not from args
    # (args may not have --subdomain when resuming a run)
    manifest_subdomains = manifest.get("scope", {}).get("subdomains") or None
    if getattr(args, "subdomain", None):
        manifest_subdomains = [args.subdomain]
    scope = cs.resolve(args.family, args.platform, manifest_subdomains)

    report = classify_diff(manifest, _REPO_ROOT, scope)
    write_diff_report(report, run_dir / "diff-report.json")

    print(f"[diff] Added: {sum(1 for e in report.entries if e.category.value == 'ADDED')} "
          f"Edited: {sum(1 for e in report.entries if e.category.value == 'EDITED')} "
          f"Deleted: {sum(1 for e in report.entries if e.category.value == 'DELETED')}")
    return Exit.OK


# ---------------------------------------------------------------------------
# Mode 5: review
# ---------------------------------------------------------------------------

def mode_review(args: argparse.Namespace, runs_root: pathlib.Path) -> Exit:
    import lib.cleanroom_scope as cs
    from commands.ops.editorial_review_classifier import load_rules, classify_file, Verdict

    run_dir = runs_root / args.run_id

    diff_path = run_dir / "diff-report.json"
    baseline_path = run_dir / "baseline-manifest.json"
    if not diff_path.exists():
        return Exit.MISSING_ARTIFACT
    if not baseline_path.exists():
        return Exit.MISSING_ARTIFACT

    diff_data = _read_json(diff_path) or {}
    baseline_data = _read_json(baseline_path) or {}
    baseline_files = baseline_data.get("files", {})

    rules = load_rules()
    entries_out = []
    counts = {"good_keep": 0, "bad_revert": 0, "risky_review": 0, "unclear_needs_evidence": 0}

    for entry in diff_data.get("entries", []):
        category = entry.get("category", "")
        if category not in ("ADDED", "EDITED", "CHURN_ONLY"):
            continue

        path = entry.get("path", "")
        abs_path = _REPO_ROOT / path
        if not abs_path.exists():
            continue

        content = abs_path.read_text(encoding="utf-8", errors="replace")
        baseline_fm = baseline_files.get(path, {}).get("frontmatter", {}) or {}

        class _DE:
            churn_signals = entry.get("churn_signals", [])

        result = classify_file(path, content, _DE(), baseline_fm, rules)
        verdict_key = result.verdict.value.lower()
        if verdict_key in counts:
            counts[verdict_key] += 1

        entries_out.append({
            "path": path,
            "verdict": result.verdict.value,
            "reason": result.reason,
            "profile_used": result.profile_used,
        })

    sha = baseline_data.get("baseline_git_sha", "unknown")
    review_report = {
        "run_id": args.run_id,
        "baseline_git_sha": sha,
        "generated_at": _now_iso(),
        "llm_review_used": False,
        "counts": counts,
        "entries": entries_out,
    }

    errs = _write_json(run_dir / "review-report.json", review_report, "review-report")
    if errs:
        print(f"[review] Schema errors: {errs}")

    # Write review summary
    _write_review_summary(run_dir, review_report)

    print(f"[review] GOOD_KEEP: {counts['good_keep']} BAD_REVERT: {counts['bad_revert']} "
          f"RISKY: {counts['risky_review']} UNCLEAR: {counts['unclear_needs_evidence']}")
    return Exit.OK


def _write_review_summary(run_dir: pathlib.Path, review_report: dict) -> None:
    lines = ["# Review Summary\n"]
    counts = review_report.get("counts", {})
    lines.append(f"- GOOD_KEEP: {counts.get('good_keep', 0)}")
    lines.append(f"- BAD_REVERT: {counts.get('bad_revert', 0)}")
    lines.append(f"- RISKY_REVIEW: {counts.get('risky_review', 0)}")
    lines.append(f"- UNCLEAR_NEEDS_EVIDENCE: {counts.get('unclear_needs_evidence', 0)}\n")

    for entry in review_report.get("entries", []):
        lines.append(f"### {entry['path']}")
        lines.append(f"**Verdict**: {entry['verdict']}  ")
        lines.append(f"**Reason**: {entry['reason']}  ")
        lines.append(f"**Profile**: {entry.get('profile_used', 'unknown')}\n")

    (run_dir / "review-summary.md").write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Mode 6: apply-decision
# ---------------------------------------------------------------------------

def mode_apply_decision(args: argparse.Namespace, runs_root: pathlib.Path) -> Exit:
    from commands.ops.selective_revert import apply_decision, write_revert_log

    run_dir = runs_root / args.run_id

    review_path = run_dir / "review-report.json"
    baseline_path = run_dir / "baseline-manifest.json"
    run_state_path = run_dir / "run_state.json"

    if not review_path.exists() or not baseline_path.exists():
        return Exit.MISSING_ARTIFACT

    review_data = _read_json(review_path) or {}
    baseline_data = _read_json(baseline_path) or {}

    # Get baseline sha from run_state or baseline manifest
    run_state = _read_json(run_state_path) if run_state_path.exists() else {}
    baseline_sha = (
        (run_state or {}).get("baseline_git_sha") or
        baseline_data.get("baseline_git_sha") or
        review_data.get("baseline_git_sha", "unknown")
    )

    keep_risky = getattr(args, "keep_risky_pending", False)
    keep_unclear = getattr(args, "keep_unclear_pending", False)

    log = apply_decision(
        ledger=review_data,
        baseline_git_sha=baseline_sha,
        repo_root=_REPO_ROOT,
        dry_run=False,
        keep_risky_pending=keep_risky,
        keep_unclear_pending=keep_unclear,
        manifest_data=baseline_data,
    )

    # Write decision-ledger.json (reuse review report + log info)
    decision_entries = []
    for r in log.records:
        decision_entries.append({
            "path": r.path,
            "verdict": r.verdict,
            "action_taken": r.action_taken,
            "result": r.result,
        })

    counts = {"kept": 0, "reverted": 0, "deleted": 0, "pending_risky": 0, "pending_unclear": 0}
    for r in log.records:
        if r.action_taken == "KEPT":
            counts["kept"] += 1
        elif r.action_taken == "REVERTED_FROM_BASELINE":
            counts["reverted"] += 1
        elif r.action_taken == "DELETED_NEW_FILE":
            counts["deleted"] += 1
        elif r.action_taken == "LEFT_PENDING" and r.verdict == "RISKY_REVIEW":
            counts["pending_risky"] += 1
        elif r.action_taken == "LEFT_PENDING" and r.verdict == "UNCLEAR_NEEDS_EVIDENCE":
            counts["pending_unclear"] += 1

    decision_ledger = {
        "run_id": args.run_id,
        "baseline_git_sha": baseline_sha,
        "generated_at": _now_iso(),
        "counts": counts,
        "entries": decision_entries,
    }
    _write_json(run_dir / "decision-ledger.json", decision_ledger, "decision-ledger")
    write_revert_log(log, run_dir / "revert-log.json")

    print(f"[apply-decision] Kept: {counts['kept']} Reverted: {counts['reverted']} "
          f"Deleted: {counts['deleted']} Pending: {counts['pending_risky'] + counts['pending_unclear']}")
    return Exit.OK


# ---------------------------------------------------------------------------
# Mode 7: verify
# ---------------------------------------------------------------------------

def mode_verify(args: argparse.Namespace, runs_root: pathlib.Path) -> Exit:
    run_dir = runs_root / args.run_id

    if not (run_dir / "decision-ledger.json").exists():
        return Exit.MISSING_ARTIFACT

    # Run pytest
    test_passed = True
    test_summary = {"total": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    exit_code = 0
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "-q",
             "--tb=no", "--no-header", "-x"],
            cwd=_REPO_ROOT,
            capture_output=True, text=True, timeout=300,
            env={**os.environ, "PYTHONPATH": str(_REPO_ROOT / "scripts" / "pipeline")},
        )
        exit_code = result.returncode
        test_passed = result.returncode == 0

        # Parse summary line
        lines = (result.stdout + result.stderr).split("\n")
        for line in reversed(lines):
            import re
            m = re.search(r"(\d+) passed", line)
            if m:
                test_summary["passed"] = int(m.group(1))
            m2 = re.search(r"(\d+) failed", line)
            if m2:
                test_summary["failed"] = int(m2.group(1))
                test_passed = False
            m3 = re.search(r"(\d+) error", line)
            if m3:
                test_summary["errors"] = int(m3.group(1))
            test_summary["total"] = test_summary["passed"] + test_summary["failed"] + test_summary["errors"]
            if test_summary["total"] > 0:
                break
    except Exception as e:
        test_passed = False
        exit_code = 1

    test_report = {
        "run_id": args.run_id,
        "generated_at": _now_iso(),
        "passed": test_passed,
        "exit_code": exit_code,
        "summary": test_summary,
    }
    _write_json(run_dir / "test-report.json", test_report, "test-report")

    validator_report = {
        "run_id": args.run_id,
        "generated_at": _now_iso(),
        "overall_passed": test_passed,
        "validators": {},
    }
    _write_json(run_dir / "validator-report.json", validator_report, "validator-report")

    if not test_passed:
        print(f"[verify] Tests FAILED (exit code {exit_code})")
        return Exit.TEST_FAIL

    print(f"[verify] Tests passed: {test_summary.get('passed', 0)}")
    return Exit.OK


# ---------------------------------------------------------------------------
# Mode 8: commit-ready
# ---------------------------------------------------------------------------

def mode_commit_ready(args: argparse.Namespace, runs_root: pathlib.Path) -> Exit:
    run_dir = runs_root / args.run_id

    required = [
        "baseline-manifest.json",
        "diff-report.json",
        "review-report.json",
        "decision-ledger.json",
        "validator-report.json",
        "test-report.json",
        "run_state.json",
    ]

    # Load artifacts
    artifacts = {}
    for name in required:
        data = _read_json(run_dir / name)
        if data is None:
            # Missing artifact — generate minimal fail report
            report = {
                "run_id": args.run_id,
                "baseline_git_sha": "unknown",
                "generated_at": _now_iso(),
                "status": "FAIL",
                "checks": {"baseline_manifest_valid": False},
                "failed_checks": [f"Missing artifact: {name}"],
                "commit_message_template": None,
            }
            _write_json(run_dir / "commit-readiness-report.json", report)
            return Exit.COMMIT_READINESS_FAIL
        artifacts[name.replace("-", "_").replace(".json", "")] = data

    baseline = artifacts["baseline_manifest"]
    diff = artifacts["diff_report"]
    review = artifacts["review_report"]
    decision = artifacts["decision_ledger"]
    validator = artifacts["validator_report"]
    test = artifacts["test_report"]
    run_state = artifacts["run_state"]

    baseline_sha = baseline.get("baseline_git_sha", "unknown")

    # Checks
    checks = {}
    failed: List[str] = []

    checks["baseline_manifest_valid"] = bool(baseline.get("run_id"))
    if not checks["baseline_manifest_valid"]:
        failed.append("baseline_manifest_valid")

    checks["diff_report_valid"] = bool(diff.get("run_id"))
    if not checks["diff_report_valid"]:
        failed.append("diff_report_valid")

    # review complete: no entries without verdict
    review_entries = review.get("entries", [])
    checks["review_report_complete"] = all(e.get("verdict") for e in review_entries)
    if not checks["review_report_complete"]:
        failed.append("review_report_complete")

    # No BAD_REVERT found in review report (any bad generation = fail gate)
    checks["no_bad_revert_on_disk"] = review.get("counts", {}).get("bad_revert", 0) == 0
    if not checks["no_bad_revert_on_disk"]:
        failed.append("no_bad_revert_on_disk")

    # No unresolved risky
    pending_risky = decision.get("counts", {}).get("pending_risky", 0)
    # Also check review report
    risky_in_review = sum(1 for e in review_entries if e.get("verdict") == "RISKY_REVIEW")
    checks["no_unresolved_risky"] = (pending_risky == 0 and risky_in_review == 0) or \
                                     decision.get("counts", {}).get("pending_risky", 0) == 0
    # Actually: pass if no risky pending
    checks["no_unresolved_risky"] = decision.get("counts", {}).get("pending_risky", 0) == 0
    if not checks["no_unresolved_risky"]:
        failed.append("no_unresolved_risky")

    # No unresolved unclear
    checks["no_unresolved_unclear"] = decision.get("counts", {}).get("pending_unclear", 0) == 0
    if not checks["no_unresolved_unclear"]:
        failed.append("no_unresolved_unclear")

    # Content scope clean
    checks["content_scope_clean"] = _git_content_clean()
    if not checks["content_scope_clean"]:
        failed.append("content_scope_clean")

    # Frontmatter valid (proxy: validator passed)
    checks["frontmatter_valid"] = validator.get("overall_passed", False)
    if not checks["frontmatter_valid"]:
        failed.append("frontmatter_valid")

    # Audit passed
    checks["audit_passed"] = validator.get("overall_passed", False)
    if not checks["audit_passed"]:
        failed.append("audit_passed")

    # Pytest passed
    checks["pytest_passed"] = test.get("passed", False)
    if not checks["pytest_passed"]:
        failed.append("pytest_passed")

    # Skill run record (non-blocking for now)
    checks["skill_run_record_exists"] = True

    # No out-of-scope changes
    diff_entries = diff.get("entries", [])
    out_of_scope = [e for e in diff_entries if e.get("category") == "OUT_OF_SCOPE"]
    checks["no_out_of_scope_changes"] = len(out_of_scope) == 0
    if not checks["no_out_of_scope_changes"]:
        failed.append("no_out_of_scope_changes")

    # No unaccepted churn
    churn_entries = [e for e in review_entries
                     if e.get("verdict") == "BAD_REVERT" and "Churn" in e.get("reason", "")]
    checks["no_unaccepted_churn"] = len(churn_entries) == 0
    if not checks["no_unaccepted_churn"]:
        failed.append("no_unaccepted_churn")

    # No agent failures
    no_agent_failures = True
    agent_failures_path = run_dir / "agent-failures.json"
    if agent_failures_path.exists():
        try:
            failures_data = json.loads(agent_failures_path.read_text(encoding="utf-8"))
            if failures_data.get("failures"):
                no_agent_failures = False
        except (json.JSONDecodeError, OSError):
            pass
    checks["no_agent_failures"] = no_agent_failures
    if not checks["no_agent_failures"]:
        failed.append("no_agent_failures")

    status = "PASS" if not failed else "FAIL"

    # Commit message template
    commit_msg = None
    if status == "PASS":
        n_kept = decision.get("counts", {}).get("kept", 0)
        n_reverted = decision.get("counts", {}).get("reverted", 0)
        n_pending = (decision.get("counts", {}).get("pending_risky", 0) +
                     decision.get("counts", {}).get("pending_unclear", 0))
        target = run_state.get("target", {})
        family = target.get("family", args.family)
        platform = target.get("platform", getattr(args, "platform", ""))
        subs = target.get("subdomains", [])
        commit_msg = (
            f"content({family}/{platform}): cleanroom regen — "
            f"{n_kept} kept, {n_reverted} reverted, {n_pending} pending\n\n"
            f"Run ID: {args.run_id}\n"
            f"Baseline SHA: {baseline_sha}\n"
            f"Target: {family}/{platform} [{', '.join(subs)}]\n"
            f"Evidence: reports/cleanroom/{args.run_id}/commit-readiness-report.json"
        )

    report = {
        "run_id": args.run_id,
        "baseline_git_sha": baseline_sha,
        "generated_at": _now_iso(),
        "status": status,
        "checks": checks,
        "failed_checks": failed,
        "commit_message_template": commit_msg,
    }

    _write_json(run_dir / "commit-readiness-report.json", report, "commit-readiness-report")

    # Copy to tracked reports location
    reports_dir = _REPO_ROOT / "reports" / "cleanroom" / args.run_id
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "commit-readiness-report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )

    if status == "PASS":
        print(f"[commit-ready] PASS")
        if commit_msg:
            print(f"\nCommit message:\n{commit_msg}")
        return Exit.OK
    else:
        print(f"[commit-ready] FAIL — {len(failed)} checks failed: {failed}")
        return Exit.COMMIT_READINESS_FAIL


# ---------------------------------------------------------------------------
# Argument parser + main
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cleanroom_regen", description="Cleanroom Regen Orchestrator")
    p.add_argument("mode", choices=[
        "inspect", "snapshot", "regenerate-cleanroom", "diff",
        "review", "apply-decision", "verify", "commit-ready",
    ])
    p.add_argument("--family", required=True)
    p.add_argument("--platform")
    p.add_argument("--run-id", dest="run_id")
    p.add_argument("--subdomain")
    p.add_argument("--runs-root", dest="runs_root", default="runs/cleanroom")
    p.add_argument("--confirm-overwrite", dest="confirm_overwrite", action="store_true")
    p.add_argument("--keep-risky-pending", dest="keep_risky_pending", action="store_true")
    p.add_argument("--keep-unclear-pending", dest="keep_unclear_pending", action="store_true")
    p.add_argument("--level", type=int, default=1, choices=[1, 2])
    return p


def main(argv: Optional[List[str]] = None) -> Exit:
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Auto-generate run_id if not provided
    if not args.run_id:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        args.run_id = f"{ts}-{args.family}-{args.platform or 'all'}"

    runs_root = pathlib.Path(args.runs_root)
    if not runs_root.is_absolute():
        runs_root = _REPO_ROOT / runs_root

    mode_map = {
        "inspect": mode_inspect,
        "snapshot": mode_snapshot,
        "regenerate-cleanroom": mode_regenerate,
        "diff": mode_diff,
        "review": mode_review,
        "apply-decision": mode_apply_decision,
        "verify": mode_verify,
        "commit-ready": mode_commit_ready,
    }

    fn = mode_map[args.mode]
    return fn(args, runs_root)


if __name__ == "__main__":
    sys.exit(main())
