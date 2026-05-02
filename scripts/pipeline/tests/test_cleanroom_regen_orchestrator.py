"""
TC-S96-006 + TC-S96-002 + TC-S96-015: Tests for cleanroom_regen.py orchestrator.
"""

import json
import pathlib
import sys
from unittest.mock import patch, MagicMock

import pytest

from commands.ops.cleanroom_regen import Exit, main, _git_current_branch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_scope(family="cells", platform="java", subdomains=None, errors=None):
    class FakeScope:
        pass
    s = FakeScope()
    s.family = family
    s.platform = platform
    s.subdomains = subdomains or ["reference"]
    s.files = []
    s.content_roots = {}
    s.generation_entry_points = {
        "reference": {"type": "script", "skill": "S-62"},
    }
    s.knowledge_model_path = None
    s._errors = errors or []
    s._warnings = []
    return s


def _patch_scope(scope=None):
    if scope is None:
        scope = _fake_scope()
    return patch("commands.ops.cleanroom_regen.main.__code__", None), \
           patch("lib.cleanroom_scope.resolve", return_value=scope)


# ---------------------------------------------------------------------------
# TC1: inspect mode writes inspect-report.json
# ---------------------------------------------------------------------------

def test_inspect_mode_writes_report(tmp_path):
    """Mode 1 (inspect) must write inspect-report.json without touching content/."""
    runs_root = tmp_path / "runs" / "cleanroom"

    scope = _fake_scope()
    with patch("commands.ops.cleanroom_regen._git_current_branch", return_value="test/s96-pilot"), \
         patch("commands.ops.cleanroom_regen._git_head_sha", return_value="abc1234"), \
         patch("commands.ops.cleanroom_regen._git_content_clean", return_value=True), \
         patch("lib.cleanroom_scope.resolve", return_value=scope):
        rc = main(["inspect", "--family", "cells", "--platform", "java",
                   "--run-id", "test-inspect-001", "--runs-root", str(runs_root)])

    report_path = runs_root / "test-inspect-001" / "inspect-report.json"
    assert report_path.exists(), "inspect-report.json must be created"
    data = json.loads(report_path.read_text())
    assert data["run_id"] == "test-inspect-001"
    assert data["family"] == "cells"
    assert isinstance(data["ready"], bool)
    assert rc in (Exit.OK, Exit.BLOCKER)


# ---------------------------------------------------------------------------
# TC2: regenerate-cleanroom without --confirm-overwrite exits 2
# ---------------------------------------------------------------------------

def test_regenerate_without_confirm_overwrite_exits_2(tmp_path):
    """regenerate-cleanroom without --confirm-overwrite must exit 2."""
    runs_root = tmp_path / "runs" / "cleanroom"
    scope = _fake_scope()
    with patch("lib.cleanroom_scope.resolve", return_value=scope), \
         patch("commands.ops.cleanroom_regen._git_current_branch", return_value="test/s96-pilot"):
        rc = main(["regenerate-cleanroom", "--family", "cells", "--platform", "java",
                   "--run-id", "test-regen-no-confirm", "--runs-root", str(runs_root)])
    assert rc == Exit.INVALID_ARGS


# ---------------------------------------------------------------------------
# TC3: regenerate-cleanroom on main branch exits 4
# ---------------------------------------------------------------------------

def test_regenerate_on_main_branch_exits_4(tmp_path):
    """regenerate-cleanroom on main branch must exit 4."""
    runs_root = tmp_path / "runs" / "cleanroom"
    # Create minimal artifacts so gates don't exit 5 before branch check
    run_dir = runs_root / "test-regen-main"
    run_dir.mkdir(parents=True)
    (run_dir / "baseline-manifest.json").write_text(json.dumps({"run_id": "x", "baseline_git_sha": "abc", "captured_at": "2026-01-01T00:00:00Z", "scope": {"family": "cells"}, "files": {}, "_errors": []}), encoding="utf-8")
    (run_dir / "git-baseline.json").write_text(json.dumps({"run_id": "x", "baseline_git_sha": "abc", "branch": "main", "captured_at": "2026-01-01T00:00:00Z", "status_short": ""}), encoding="utf-8")

    scope = _fake_scope()
    with patch("lib.cleanroom_scope.resolve", return_value=scope), \
         patch("commands.ops.cleanroom_regen._git_current_branch", return_value="main"):
        rc = main(["regenerate-cleanroom", "--family", "cells", "--platform", "java",
                   "--confirm-overwrite", "--run-id", "test-regen-main", "--runs-root", str(runs_root)])
    assert rc == Exit.UNSAFE_BRANCH


# ---------------------------------------------------------------------------
# TC4: diff without baseline-manifest exits 5
# ---------------------------------------------------------------------------

def test_diff_without_prior_artifacts_exits_5(tmp_path):
    """diff mode without baseline-manifest.json must exit 5."""
    runs_root = tmp_path / "runs" / "cleanroom"
    scope = _fake_scope()
    with patch("lib.cleanroom_scope.resolve", return_value=scope):
        with pytest.raises(SystemExit) as exc_info:
            main(["diff", "--family", "cells", "--platform", "java",
                  "--run-id", "no-artifacts-run", "--runs-root", str(runs_root)])
    assert exc_info.value.code == Exit.MISSING_ARTIFACT


# ---------------------------------------------------------------------------
# TC5: apply-decision uses baseline_git_sha not HEAD
# ---------------------------------------------------------------------------

def test_apply_decision_uses_baseline_sha(tmp_path):
    """apply-decision must use baseline_git_sha from run state, not HEAD."""
    runs_root = tmp_path / "runs" / "cleanroom"
    run_dir = runs_root / "test-apply-001"
    run_dir.mkdir(parents=True)

    baseline_sha = "deadbeef1234567"
    # Write required artifacts
    (run_dir / "baseline-manifest.json").write_text(json.dumps({
        "run_id": "test-apply-001",
        "baseline_git_sha": baseline_sha,
        "captured_at": "2026-01-01T00:00:00Z",
        "scope": {"family": "cells"},
        "files": {},
        "_errors": [],
    }), encoding="utf-8")
    (run_dir / "review-report.json").write_text(json.dumps({
        "run_id": "test-apply-001",
        "baseline_git_sha": baseline_sha,
        "generated_at": "2026-01-01T00:00:00Z",
        "llm_review_used": False,
        "counts": {"good_keep": 0, "bad_revert": 0, "risky_review": 0, "unclear_needs_evidence": 0},
        "entries": [],
    }), encoding="utf-8")
    (run_dir / "run_state.json").write_text(json.dumps({
        "run_id": "test-apply-001",
        "target": {"family": "cells", "platform": "java", "subdomains": ["reference"]},
        "baseline_git_sha": baseline_sha,
        "isolated_branch": "test/s96",
        "started_at": "2026-01-01T00:00:00Z",
        "completed_modes": ["snapshot"],
        "resumable": True,
        "lock_status": "LOCKED",
    }), encoding="utf-8")

    scope = _fake_scope()
    reverted_shas = []

    def mock_revert(path, sha, repo_root, dry_run):
        reverted_shas.append(sha)
        return True, None

    with patch("lib.cleanroom_scope.resolve", return_value=scope), \
         patch("commands.ops.selective_revert._git_checkout_baseline", side_effect=mock_revert):
        rc = main(["apply-decision", "--family", "cells", "--platform", "java",
                   "--run-id", "test-apply-001", "--runs-root", str(runs_root)])

    # No reverts happened (empty entries), but the sha must be baseline_sha not HEAD
    # (Verified by checking the decision-ledger baseline_git_sha)
    ledger_path = run_dir / "decision-ledger.json"
    assert ledger_path.exists()
    ledger = json.loads(ledger_path.read_text())
    assert ledger["baseline_git_sha"] == baseline_sha


# ---------------------------------------------------------------------------
# TC6: commit-ready with BAD_REVERT remaining exits 13
# ---------------------------------------------------------------------------

def test_commit_ready_with_bad_revert_remaining_exits_13(tmp_path):
    """commit-ready must fail (exit 13) if BAD_REVERT files exist in review report."""
    runs_root = tmp_path / "runs" / "cleanroom"
    run_dir = runs_root / "test-cr-001"
    run_dir.mkdir(parents=True)

    sha = "abc1234"
    # Write all required artifacts with BAD_REVERT present
    for name, data in [
        ("baseline-manifest.json", {"run_id": "test-cr-001", "baseline_git_sha": sha,
                                     "captured_at": "2026-01-01T00:00:00Z", "scope": {"family": "cells"}, "files": {}, "_errors": []}),
        ("diff-report.json", {"run_id": "test-cr-001", "baseline_git_sha": sha,
                               "generated_at": "2026-01-01T00:00:00Z",
                               "counts": {"added": 0, "edited": 1, "deleted": 0, "unchanged": 0,
                                          "generated_identical": 0, "out_of_scope": 0, "churn_only": 0},
                               "entries": [{"path": "foo.md", "category": "EDITED"}]}),
        ("review-report.json", {"run_id": "test-cr-001", "baseline_git_sha": sha,
                                 "generated_at": "2026-01-01T00:00:00Z", "llm_review_used": False,
                                 "counts": {"good_keep": 0, "bad_revert": 1, "risky_review": 0, "unclear_needs_evidence": 0},
                                 "entries": [{"path": "foo.md", "verdict": "BAD_REVERT",
                                              "reason": "test", "profile_used": "reference_page"}]}),
        ("decision-ledger.json", {"run_id": "test-cr-001", "baseline_git_sha": sha,
                                   "generated_at": "2026-01-01T00:00:00Z",
                                   "counts": {"kept": 0, "reverted": 1, "deleted": 0, "pending_risky": 0, "pending_unclear": 0},
                                   "entries": [{"path": "foo.md", "verdict": "BAD_REVERT",
                                                "action_taken": "REVERTED_FROM_BASELINE", "result": "SUCCESS"}]}),
        ("validator-report.json", {"run_id": "test-cr-001", "generated_at": "2026-01-01T00:00:00Z",
                                    "overall_passed": True, "validators": {}}),
        ("test-report.json", {"run_id": "test-cr-001", "generated_at": "2026-01-01T00:00:00Z",
                               "passed": True, "exit_code": 0,
                               "summary": {"total": 10, "passed": 10, "failed": 0, "errors": 0, "skipped": 0}}),
        ("run_state.json", {"run_id": "test-cr-001", "target": {"family": "cells", "platform": "java", "subdomains": ["reference"]},
                             "baseline_git_sha": sha, "isolated_branch": "test/s96",
                             "started_at": "2026-01-01T00:00:00Z", "completed_modes": [],
                             "resumable": True, "lock_status": "LOCKED"}),
    ]:
        (run_dir / name).write_text(json.dumps(data), encoding="utf-8")

    scope = _fake_scope()
    with patch("lib.cleanroom_scope.resolve", return_value=scope), \
         patch("commands.ops.cleanroom_regen._git_content_clean", return_value=True):
        rc = main(["commit-ready", "--family", "cells", "--platform", "java",
                   "--run-id", "test-cr-001", "--runs-root", str(runs_root)])

    assert rc == Exit.COMMIT_READINESS_FAIL


# ---------------------------------------------------------------------------
# TC7: resume — snapshot skipped if already done
# ---------------------------------------------------------------------------

def test_inspect_is_always_safe(tmp_path):
    """inspect mode must not create a run.lock."""
    runs_root = tmp_path / "runs" / "cleanroom"
    scope = _fake_scope()
    with patch("lib.cleanroom_scope.resolve", return_value=scope), \
         patch("commands.ops.cleanroom_regen._git_current_branch", return_value="test/s96-pilot"), \
         patch("commands.ops.cleanroom_regen._git_head_sha", return_value="abc1234"), \
         patch("commands.ops.cleanroom_regen._git_content_clean", return_value=True):
        main(["inspect", "--family", "cells", "--platform", "java",
              "--run-id", "test-no-lock", "--runs-root", str(runs_root)])

    lock = runs_root / "test-no-lock" / "run.lock"
    assert not lock.exists(), "inspect must not create run.lock"


# ---------------------------------------------------------------------------
# TC8: diff fails if agent-execution-ledger has PLANNED entries
# ---------------------------------------------------------------------------

def test_diff_fails_if_agent_tasks_still_planned(tmp_path):
    """diff must exit 5 if agent plan exists with PLANNED entries and ledger not complete."""
    runs_root = tmp_path / "runs" / "cleanroom"
    run_dir = runs_root / "test-diff-agent"
    run_dir.mkdir(parents=True)

    sha = "abc1234"
    (run_dir / "baseline-manifest.json").write_text(json.dumps({
        "run_id": "test-diff-agent", "baseline_git_sha": sha,
        "captured_at": "2026-01-01T00:00:00Z", "scope": {"family": "cells"}, "files": {}, "_errors": []
    }), encoding="utf-8")
    # Regeneration plan with a blog entry (non-reference)
    (run_dir / "regeneration-plan.json").write_text(json.dumps({
        "run_id": "test-diff-agent", "baseline_git_sha": sha, "phase_a_complete": True,
        "entries": [{"planned_task_id": "t1", "subdomain": "blog", "skill_id": "S-57",
                     "target_path": "content/blog.aspose.org/cells/java/post/index.md",
                     "skill_args": {}, "status": "PLANNED"}]
    }), encoding="utf-8")
    # No agent-execution-ledger.json

    scope = _fake_scope(subdomains=["blog"])
    scope.generation_entry_points = {"blog": {"type": "agent", "skill": "S-57"}}
    with patch("lib.cleanroom_scope.resolve", return_value=scope):
        rc = main(["diff", "--family", "cells", "--platform", "java",
                   "--run-id", "test-diff-agent", "--runs-root", str(runs_root)])

    assert rc == Exit.MISSING_ARTIFACT
