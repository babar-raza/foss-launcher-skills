"""
TC-S96-006 + TC-S96-002 + TC-S96-015: Tests for cleanroom_regen.py orchestrator.
(Historical TC-S96 naming retained; skill is governed as S-97.)
"""

import json
import pathlib
import subprocess
import sys
from unittest.mock import patch, MagicMock

import pytest

from commands.ops.cleanroom_regen import Exit, main, _git_current_branch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_scope(family="cells", platform="java", subdomains=None, errors=None,
                content_roots=None):
    class FakeScope:
        pass
    s = FakeScope()
    s.family = family
    s.platform = platform
    s.subdomains = subdomains or ["reference"]
    s.files = []
    s.content_roots = content_roots or {}
    s.generation_entry_points = {
        "reference": {"type": "script", "skill": "S-62"},
    }
    s.knowledge_model_path = None
    s._errors = errors or []
    s._warnings = []
    return s


def _write_artifact(run_dir, name, data):
    (run_dir / name).write_text(json.dumps(data), encoding="utf-8")


def _make_full_run_artifacts(run_dir, sha="abc1234", run_id="test-run",
                             decision_entries=None, review_bad_revert=0,
                             validators=None):
    """Write a complete set of artifacts for commit-ready testing."""
    if decision_entries is None:
        decision_entries = []
    if validators is None:
        validators = {}
    for name, data in [
        ("baseline-manifest.json", {"run_id": run_id, "baseline_git_sha": sha,
                                     "captured_at": "2026-01-01T00:00:00Z",
                                     "scope": {"family": "cells"}, "files": {}, "_errors": []}),
        ("diff-report.json", {"run_id": run_id, "baseline_git_sha": sha,
                               "generated_at": "2026-01-01T00:00:00Z",
                               "counts": {"added": 0, "edited": 1, "deleted": 0, "unchanged": 0,
                                          "generated_identical": 0, "out_of_scope": 0, "churn_only": 0},
                               "entries": [{"path": "foo.md", "category": "EDITED"}]}),
        ("review-report.json", {"run_id": run_id, "baseline_git_sha": sha,
                                 "generated_at": "2026-01-01T00:00:00Z", "llm_review_used": False,
                                 "counts": {"good_keep": 0, "bad_revert": review_bad_revert,
                                            "risky_review": 0, "unclear_needs_evidence": 0},
                                 "entries": []}),
        ("decision-ledger.json", {"run_id": run_id, "baseline_git_sha": sha,
                                   "generated_at": "2026-01-01T00:00:00Z",
                                   "counts": {"kept": 0, "reverted": 0, "deleted": 0,
                                              "pending_risky": 0, "pending_unclear": 0},
                                   "entries": decision_entries}),
        ("validator-report.json", {"run_id": run_id, "generated_at": "2026-01-01T00:00:00Z",
                                    "overall_passed": True, "validators": validators}),
        ("test-report.json", {"run_id": run_id, "generated_at": "2026-01-01T00:00:00Z",
                               "passed": True, "exit_code": 0,
                               "summary": {"total": 10, "passed": 10, "failed": 0,
                                           "errors": 0, "skipped": 0}}),
        ("run_state.json", {"run_id": run_id,
                             "target": {"family": "cells", "platform": "java",
                                        "subdomains": ["reference"]},
                             "baseline_git_sha": sha, "isolated_branch": "test/s96",
                             "started_at": "2026-01-01T00:00:00Z", "completed_modes": [],
                             "resumable": True, "lock_status": "LOCKED"}),
    ]:
        _write_artifact(run_dir, name, data)


def _make_regen_artifacts(run_dir, sha="abc1234", run_id="test-regen"):
    """Write baseline + git-baseline artifacts for regeneration tests."""
    _write_artifact(run_dir, "baseline-manifest.json", {
        "run_id": run_id, "baseline_git_sha": sha,
        "captured_at": "2026-01-01T00:00:00Z",
        "scope": {"family": "cells"}, "files": {}, "_errors": []
    })
    _write_artifact(run_dir, "git-baseline.json", {
        "run_id": run_id, "baseline_git_sha": sha,
        "branch": "test/s96", "captured_at": "2026-01-01T00:00:00Z",
        "status_short": ""
    })


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
    run_dir = runs_root / "test-regen-main"
    run_dir.mkdir(parents=True)
    _make_regen_artifacts(run_dir, run_id="test-regen-main")

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
    _write_artifact(run_dir, "baseline-manifest.json", {
        "run_id": "test-apply-001", "baseline_git_sha": baseline_sha,
        "captured_at": "2026-01-01T00:00:00Z", "scope": {"family": "cells"},
        "files": {}, "_errors": [],
    })
    _write_artifact(run_dir, "review-report.json", {
        "run_id": "test-apply-001", "baseline_git_sha": baseline_sha,
        "generated_at": "2026-01-01T00:00:00Z", "llm_review_used": False,
        "counts": {"good_keep": 0, "bad_revert": 0, "risky_review": 0, "unclear_needs_evidence": 0},
        "entries": [],
    })
    _write_artifact(run_dir, "run_state.json", {
        "run_id": "test-apply-001",
        "target": {"family": "cells", "platform": "java", "subdomains": ["reference"]},
        "baseline_git_sha": baseline_sha, "isolated_branch": "test/s96",
        "started_at": "2026-01-01T00:00:00Z", "completed_modes": ["snapshot"],
        "resumable": True, "lock_status": "LOCKED",
    })

    scope = _fake_scope()

    def mock_revert(path, sha, repo_root, dry_run):
        return True, None

    with patch("lib.cleanroom_scope.resolve", return_value=scope), \
         patch("commands.ops.selective_revert._git_checkout_baseline", side_effect=mock_revert):
        rc = main(["apply-decision", "--family", "cells", "--platform", "java",
                   "--run-id", "test-apply-001", "--runs-root", str(runs_root)])

    ledger_path = run_dir / "decision-ledger.json"
    assert ledger_path.exists()
    ledger = json.loads(ledger_path.read_text())
    assert ledger["baseline_git_sha"] == baseline_sha


# ---------------------------------------------------------------------------
# TC6: commit-ready with UNHANDLED BAD_REVERT exits 13 (P-5 fix)
# ---------------------------------------------------------------------------

def test_commit_ready_with_unhandled_bad_revert_exits_13(tmp_path):
    """commit-ready must fail if decision-ledger has BAD_REVERT with LEFT_PENDING."""
    runs_root = tmp_path / "runs" / "cleanroom"
    run_dir = runs_root / "test-cr-001"
    run_dir.mkdir(parents=True)

    _make_full_run_artifacts(
        run_dir, run_id="test-cr-001", review_bad_revert=1,
        decision_entries=[{"path": "foo.md", "verdict": "BAD_REVERT",
                           "action_taken": "LEFT_PENDING", "result": "PENDING"}],
    )

    scope = _fake_scope()
    with patch("lib.cleanroom_scope.resolve", return_value=scope), \
         patch("commands.ops.cleanroom_regen._git_content_clean", return_value=True):
        rc = main(["commit-ready", "--family", "cells", "--platform", "java",
                   "--run-id", "test-cr-001", "--runs-root", str(runs_root)])

    assert rc == Exit.COMMIT_READINESS_FAIL


def test_commit_ready_passes_when_bad_reverts_properly_reverted(tmp_path):
    """commit-ready must PASS when BAD_REVERT files were reverted via apply-decision."""
    runs_root = tmp_path / "runs" / "cleanroom"
    run_dir = runs_root / "test-cr-002"
    run_dir.mkdir(parents=True)

    _make_full_run_artifacts(
        run_dir, run_id="test-cr-002", review_bad_revert=1,
        decision_entries=[{"path": "foo.md", "verdict": "BAD_REVERT",
                           "action_taken": "REVERTED_FROM_BASELINE", "result": "SUCCESS"}],
    )

    scope = _fake_scope()
    with patch("lib.cleanroom_scope.resolve", return_value=scope), \
         patch("commands.ops.cleanroom_regen._git_content_clean", return_value=True):
        rc = main(["commit-ready", "--family", "cells", "--platform", "java",
                   "--run-id", "test-cr-002", "--runs-root", str(runs_root)])

    assert rc == Exit.OK


# ---------------------------------------------------------------------------
# TC7: inspect mode must not create run.lock
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
    _write_artifact(run_dir, "baseline-manifest.json", {
        "run_id": "test-diff-agent", "baseline_git_sha": sha,
        "captured_at": "2026-01-01T00:00:00Z", "scope": {"family": "cells"},
        "files": {}, "_errors": []
    })
    _write_artifact(run_dir, "regeneration-plan.json", {
        "run_id": "test-diff-agent", "baseline_git_sha": sha, "phase_a_complete": True,
        "entries": [{"planned_task_id": "t1", "subdomain": "blog", "skill_id": "S-57",
                     "target_path": "content/blog.aspose.org/cells/java/post/index.md",
                     "skill_args": {}, "status": "PLANNED"}]
    })

    scope = _fake_scope(subdomains=["blog"])
    scope.generation_entry_points = {"blog": {"type": "agent", "skill": "S-57"}}
    with patch("lib.cleanroom_scope.resolve", return_value=scope):
        rc = main(["diff", "--family", "cells", "--platform", "java",
                   "--run-id", "test-diff-agent", "--runs-root", str(runs_root)])

    assert rc == Exit.MISSING_ARTIFACT


# ===========================================================================
# P-1: regenerate calls batch_reference.py for reference subdomain
# ===========================================================================

def test_regenerate_reference_calls_batch_reference(tmp_path):
    """regenerate-cleanroom must invoke batch_reference.py for reference subdomain."""
    runs_root = tmp_path / "runs" / "cleanroom"
    run_dir = runs_root / "test-regen-ref"
    run_dir.mkdir(parents=True)
    _make_regen_artifacts(run_dir, run_id="test-regen-ref")

    scope = _fake_scope()
    captured_cmds = []

    def mock_subprocess_run(cmd, **kwargs):
        captured_cmds.append(cmd)
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        return result

    with patch("lib.cleanroom_scope.resolve", return_value=scope), \
         patch("commands.ops.cleanroom_regen._git_current_branch", return_value="test/s96"), \
         patch("commands.ops.cleanroom_regen._git_content_clean", return_value=True), \
         patch("commands.ops.cleanroom_regen.subprocess.run", side_effect=mock_subprocess_run):
        rc = main(["regenerate-cleanroom", "--family", "cells", "--platform", "java",
                   "--confirm-overwrite", "--run-id", "test-regen-ref",
                   "--runs-root", str(runs_root)])

    assert rc == Exit.OK
    batch_calls = [c for c in captured_cmds if any("batch_reference" in str(a) for a in c)]
    assert len(batch_calls) == 1
    assert "--rebuild-all" in batch_calls[0]
    assert "--confirm-rebuild" in batch_calls[0]

    log = json.loads((run_dir / "regeneration-log.json").read_text())
    assert log["reference_exit_code"] == 0
    assert log["dry_run"] is False


def test_regenerate_reference_fails_on_nonzero_exit(tmp_path):
    """regenerate-cleanroom must return GENERATION_FAIL if batch_reference.py exits non-zero."""
    runs_root = tmp_path / "runs" / "cleanroom"
    run_dir = runs_root / "test-regen-fail"
    run_dir.mkdir(parents=True)
    _make_regen_artifacts(run_dir, run_id="test-regen-fail")

    scope = _fake_scope()

    def mock_subprocess_run(cmd, **kwargs):
        result = MagicMock()
        if any("batch_reference" in str(a) for a in cmd):
            result.returncode = 1
            result.stdout = ""
            result.stderr = "ERROR: something failed"
        else:
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
        return result

    with patch("lib.cleanroom_scope.resolve", return_value=scope), \
         patch("commands.ops.cleanroom_regen._git_current_branch", return_value="test/s96"), \
         patch("commands.ops.cleanroom_regen._git_content_clean", return_value=True), \
         patch("commands.ops.cleanroom_regen.subprocess.run", side_effect=mock_subprocess_run):
        rc = main(["regenerate-cleanroom", "--family", "cells", "--platform", "java",
                   "--confirm-overwrite", "--run-id", "test-regen-fail",
                   "--runs-root", str(runs_root)])

    assert rc == Exit.GENERATION_FAIL


def test_regenerate_reference_timeout_returns_generation_fail(tmp_path):
    """regenerate-cleanroom must return GENERATION_FAIL on subprocess timeout."""
    runs_root = tmp_path / "runs" / "cleanroom"
    run_dir = runs_root / "test-regen-timeout"
    run_dir.mkdir(parents=True)
    _make_regen_artifacts(run_dir, run_id="test-regen-timeout")

    scope = _fake_scope()

    def mock_subprocess_run(cmd, **kwargs):
        if any("batch_reference" in str(a) for a in cmd):
            raise subprocess.TimeoutExpired(cmd, 1800)
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        return result

    with patch("lib.cleanroom_scope.resolve", return_value=scope), \
         patch("commands.ops.cleanroom_regen._git_current_branch", return_value="test/s96"), \
         patch("commands.ops.cleanroom_regen._git_content_clean", return_value=True), \
         patch("commands.ops.cleanroom_regen.subprocess.run", side_effect=mock_subprocess_run):
        rc = main(["regenerate-cleanroom", "--family", "cells", "--platform", "java",
                   "--confirm-overwrite", "--run-id", "test-regen-timeout",
                   "--runs-root", str(runs_root)])

    assert rc == Exit.GENERATION_FAIL
    log = json.loads((run_dir / "regeneration-log.json").read_text())
    assert log["reference_timed_out"] is True


# ===========================================================================
# P-8: --dry-run forwarded to batch_reference.py
# ===========================================================================

def test_regenerate_dry_run_forwarded(tmp_path):
    """--dry-run must be forwarded to batch_reference.py."""
    runs_root = tmp_path / "runs" / "cleanroom"
    run_dir = runs_root / "test-regen-dry"
    run_dir.mkdir(parents=True)
    _make_regen_artifacts(run_dir, run_id="test-regen-dry")

    scope = _fake_scope()
    captured_cmds = []

    def mock_subprocess_run(cmd, **kwargs):
        captured_cmds.append(cmd)
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        return result

    with patch("lib.cleanroom_scope.resolve", return_value=scope), \
         patch("commands.ops.cleanroom_regen._git_current_branch", return_value="test/s96"), \
         patch("commands.ops.cleanroom_regen._git_content_clean", return_value=True), \
         patch("commands.ops.cleanroom_regen.subprocess.run", side_effect=mock_subprocess_run):
        rc = main(["regenerate-cleanroom", "--family", "cells", "--platform", "java",
                   "--confirm-overwrite", "--dry-run", "--run-id", "test-regen-dry",
                   "--runs-root", str(runs_root)])

    assert rc == Exit.OK
    batch_calls = [c for c in captured_cmds if any("batch_reference" in str(a) for a in c)]
    assert len(batch_calls) == 1
    assert "--dry-run" in batch_calls[0]

    log = json.loads((run_dir / "regeneration-log.json").read_text())
    assert log["dry_run"] is True


# ===========================================================================
# P-4: regenerate fails without git-baseline.json
# ===========================================================================

def test_regenerate_fails_if_git_baseline_missing(tmp_path):
    """regenerate-cleanroom must exit MISSING_ARTIFACT without git-baseline.json."""
    runs_root = tmp_path / "runs" / "cleanroom"
    run_dir = runs_root / "test-regen-nobl"
    run_dir.mkdir(parents=True)
    _write_artifact(run_dir, "baseline-manifest.json", {
        "run_id": "test-regen-nobl", "baseline_git_sha": "abc",
        "captured_at": "2026-01-01T00:00:00Z",
        "scope": {"family": "cells"}, "files": {}, "_errors": []
    })

    scope = _fake_scope()
    with patch("lib.cleanroom_scope.resolve", return_value=scope), \
         patch("commands.ops.cleanroom_regen._git_current_branch", return_value="test/s96"):
        rc = main(["regenerate-cleanroom", "--family", "cells", "--platform", "java",
                   "--confirm-overwrite", "--run-id", "test-regen-nobl",
                   "--runs-root", str(runs_root)])

    assert rc == Exit.MISSING_ARTIFACT


# ===========================================================================
# P-6: regenerate fails if content/ is dirty
# ===========================================================================

def test_regenerate_fails_if_content_dirty(tmp_path):
    """regenerate-cleanroom must exit DIRTY_TREE if content/ is dirty."""
    runs_root = tmp_path / "runs" / "cleanroom"
    run_dir = runs_root / "test-regen-dirty"
    run_dir.mkdir(parents=True)
    _make_regen_artifacts(run_dir, run_id="test-regen-dirty")

    scope = _fake_scope()
    with patch("lib.cleanroom_scope.resolve", return_value=scope), \
         patch("commands.ops.cleanroom_regen._git_current_branch", return_value="test/s96"), \
         patch("commands.ops.cleanroom_regen._git_content_clean", return_value=False):
        rc = main(["regenerate-cleanroom", "--family", "cells", "--platform", "java",
                   "--confirm-overwrite", "--run-id", "test-regen-dirty",
                   "--runs-root", str(runs_root)])

    assert rc == Exit.DIRTY_TREE


# ===========================================================================
# P-9: non-reference target paths use scope.content_roots
# ===========================================================================

def test_regenerate_plan_uses_scope_content_roots(tmp_path):
    """Non-reference regeneration plan must use scope.content_roots for paths."""
    runs_root = tmp_path / "runs" / "cleanroom"
    run_dir = runs_root / "test-regen-roots"
    run_dir.mkdir(parents=True)
    _make_regen_artifacts(run_dir, run_id="test-regen-roots")

    content_roots = {
        "docs": "content/docs.aspose.org/en/cells/java",
        "blog": "content/blog.aspose.org/cells/java",
    }
    scope = _fake_scope(subdomains=["docs", "blog"], content_roots=content_roots)
    scope.generation_entry_points = {
        "docs": {"type": "agent", "skill": "S-56"},
        "blog": {"type": "agent", "skill": "S-57"},
    }

    def mock_subprocess_run(cmd, **kwargs):
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        return result

    with patch("lib.cleanroom_scope.resolve", return_value=scope), \
         patch("commands.ops.cleanroom_regen._git_current_branch", return_value="test/s96"), \
         patch("commands.ops.cleanroom_regen._git_content_clean", return_value=True), \
         patch("commands.ops.cleanroom_regen.subprocess.run", side_effect=mock_subprocess_run):
        rc = main(["regenerate-cleanroom", "--family", "cells", "--platform", "java",
                   "--confirm-overwrite", "--run-id", "test-regen-roots",
                   "--runs-root", str(runs_root)])

    assert rc == Exit.OK
    plan = json.loads((run_dir / "regeneration-plan.json").read_text())
    paths = {e["subdomain"]: e["target_path"] for e in plan["entries"]}
    assert paths["docs"] == "content/docs.aspose.org/en/cells/java"
    assert paths["blog"] == "content/blog.aspose.org/cells/java"


# ===========================================================================
# P-2: completed_modes updated after successful modes
# ===========================================================================

def test_completed_modes_updated_after_snapshot(tmp_path):
    """completed_modes must be persisted to run_state.json after snapshot succeeds."""
    runs_root = tmp_path / "runs" / "cleanroom"

    scope = _fake_scope()
    with patch("lib.cleanroom_scope.resolve", return_value=scope), \
         patch("commands.ops.cleanroom_regen._git_current_branch", return_value="test/s96"), \
         patch("commands.ops.cleanroom_regen._git_head_sha", return_value="abc1234"), \
         patch("commands.ops.cleanroom_regen._git_content_clean", return_value=True), \
         patch("commands.ops.cleanroom_manifest.capture_baseline") as mock_capture:
        mock_manifest = MagicMock()
        mock_manifest._errors = []
        mock_manifest.files = {}
        mock_manifest.to_dict.return_value = {
            "run_id": "test-modes-001", "baseline_git_sha": "abc1234",
            "captured_at": "2026-01-01T00:00:00Z", "scope": {"family": "cells"},
            "files": {}, "_errors": []
        }
        mock_capture.return_value = mock_manifest
        rc = main(["snapshot", "--family", "cells", "--platform", "java",
                   "--run-id", "test-modes-001", "--runs-root", str(runs_root)])

    assert rc == Exit.OK
    state = json.loads((runs_root / "test-modes-001" / "run_state.json").read_text())
    assert "snapshot" in state["completed_modes"]


def test_completed_modes_not_updated_on_failure(tmp_path):
    """completed_modes must NOT be updated when a mode fails."""
    runs_root = tmp_path / "runs" / "cleanroom"
    run_dir = runs_root / "test-modes-fail"
    run_dir.mkdir(parents=True)
    _write_artifact(run_dir, "run_state.json", {
        "run_id": "test-modes-fail", "completed_modes": [],
        "target": {"family": "cells"}, "baseline_git_sha": "abc",
        "isolated_branch": "test", "started_at": "2026-01-01T00:00:00Z",
        "resumable": True, "lock_status": "LOCKED",
    })

    scope = _fake_scope()
    with patch("lib.cleanroom_scope.resolve", return_value=scope), \
         patch("commands.ops.cleanroom_regen._git_current_branch", return_value="test/s96"):
        rc = main(["regenerate-cleanroom", "--family", "cells", "--platform", "java",
                   "--run-id", "test-modes-fail", "--runs-root", str(runs_root)])

    assert rc == Exit.INVALID_ARGS
    state = json.loads((run_dir / "run_state.json").read_text())
    assert state["completed_modes"] == []


def test_completed_modes_no_duplicates(tmp_path):
    """completed_modes must not have duplicate entries."""
    runs_root = tmp_path / "runs" / "cleanroom"
    scope = _fake_scope()

    run_dir = runs_root / "test-modes-dup"
    run_dir.mkdir(parents=True)
    _write_artifact(run_dir, "run_state.json", {
        "run_id": "test-modes-dup", "completed_modes": ["apply-decision"],
        "target": {"family": "cells"}, "baseline_git_sha": "abc",
        "isolated_branch": "test", "started_at": "2026-01-01T00:00:00Z",
        "resumable": True, "lock_status": "LOCKED",
    })
    _write_artifact(run_dir, "review-report.json", {
        "run_id": "test-modes-dup", "baseline_git_sha": "abc",
        "generated_at": "2026-01-01T00:00:00Z", "llm_review_used": False,
        "counts": {"good_keep": 0, "bad_revert": 0, "risky_review": 0, "unclear_needs_evidence": 0},
        "entries": [],
    })
    _write_artifact(run_dir, "baseline-manifest.json", {
        "run_id": "test-modes-dup", "baseline_git_sha": "abc",
        "captured_at": "2026-01-01T00:00:00Z", "scope": {"family": "cells"},
        "files": {}, "_errors": [],
    })

    with patch("lib.cleanroom_scope.resolve", return_value=scope), \
         patch("commands.ops.selective_revert.apply_decision") as mock_apply, \
         patch("commands.ops.selective_revert.write_revert_log"):
        mock_log = MagicMock()
        mock_log.records = []
        mock_apply.return_value = mock_log
        rc = main(["apply-decision", "--family", "cells", "--platform", "java",
                   "--run-id", "test-modes-dup", "--runs-root", str(runs_root)])

    assert rc == Exit.OK
    state = json.loads((run_dir / "run_state.json").read_text())
    assert state["completed_modes"].count("apply-decision") == 1


# ===========================================================================
# P-3/P-14: verify runs validate_frontmatter
# ===========================================================================

def test_verify_runs_validate_frontmatter(tmp_path):
    """mode_verify must invoke validate_frontmatter and populate validators{}."""
    runs_root = tmp_path / "runs" / "cleanroom"
    run_dir = runs_root / "test-verify-vf"
    run_dir.mkdir(parents=True)
    _write_artifact(run_dir, "decision-ledger.json", {"run_id": "test-verify-vf"})
    _write_artifact(run_dir, "baseline-manifest.json", {
        "run_id": "test-verify-vf",
        "scope": {"content_roots": {"reference": "content/reference.aspose.org/en/cells/java"}},
    })

    call_log = []

    def mock_subprocess_run(cmd, **kwargs):
        call_log.append(cmd)
        result = MagicMock()
        result.returncode = 0
        result.stdout = "all good\n"
        result.stderr = ""
        return result

    with patch("commands.ops.cleanroom_regen.subprocess.run", side_effect=mock_subprocess_run):
        rc = main(["verify", "--family", "cells", "--platform", "java",
                   "--run-id", "test-verify-vf", "--runs-root", str(runs_root)])

    assert rc == Exit.OK
    validator_report = json.loads((run_dir / "validator-report.json").read_text())
    assert "validate_frontmatter" in validator_report["validators"]
    vf = validator_report["validators"]["validate_frontmatter"]
    assert vf["passed"] is True

    vf_calls = [c for c in call_log if any("validate_frontmatter" in str(a) for a in c)]
    assert len(vf_calls) >= 1


# ===========================================================================
# P-3/P-15: verify skips audit when knowledge missing
# ===========================================================================

def test_verify_skips_audit_when_knowledge_missing(tmp_path):
    """mode_verify must skip audit.py when knowledge dir is missing."""
    runs_root = tmp_path / "runs" / "cleanroom"
    run_dir = runs_root / "test-verify-noaudit"
    run_dir.mkdir(parents=True)
    _write_artifact(run_dir, "decision-ledger.json", {"run_id": "test-verify-noaudit"})
    _write_artifact(run_dir, "baseline-manifest.json", {
        "run_id": "test-verify-noaudit", "scope": {},
    })

    def mock_subprocess_run(cmd, **kwargs):
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        return result

    # Use a nonexistent family so knowledge/nonexistent/nope/merged/ doesn't exist
    with patch("commands.ops.cleanroom_regen.subprocess.run", side_effect=mock_subprocess_run):
        rc = main(["verify", "--family", "nonexistent", "--platform", "nope",
                   "--run-id", "test-verify-noaudit", "--runs-root", str(runs_root)])

    assert rc == Exit.OK
    validator_report = json.loads((run_dir / "validator-report.json").read_text())
    audit = validator_report["validators"].get("audit", {})
    assert audit.get("skipped") is True


# ===========================================================================
# P-3: verify returns VALIDATOR_FAIL not TEST_FAIL
# ===========================================================================

def test_verify_returns_validator_fail_not_test_fail(tmp_path):
    """mode_verify must return VALIDATOR_FAIL when pytest passes but validator fails."""
    runs_root = tmp_path / "runs" / "cleanroom"
    run_dir = runs_root / "test-verify-valfail"
    run_dir.mkdir(parents=True)
    _write_artifact(run_dir, "decision-ledger.json", {"run_id": "test-verify-valfail"})
    _write_artifact(run_dir, "baseline-manifest.json", {
        "run_id": "test-verify-valfail",
        "scope": {"content_roots": {"reference": "content/reference.aspose.org/en/cells/java"}},
    })

    def mock_subprocess_run(cmd, **kwargs):
        result = MagicMock()
        if any("validate_frontmatter" in str(a) for a in cmd):
            result.returncode = 1
        else:
            result.returncode = 0
        result.stdout = "10 passed\n"
        result.stderr = ""
        return result

    with patch("commands.ops.cleanroom_regen.subprocess.run", side_effect=mock_subprocess_run):
        rc = main(["verify", "--family", "cells", "--platform", "java",
                   "--run-id", "test-verify-valfail", "--runs-root", str(runs_root)])

    assert rc == Exit.VALIDATOR_FAIL


# ===========================================================================
# P-7: commit message includes replay level
# ===========================================================================

def test_commit_ready_includes_replay_level(tmp_path):
    """commit-ready commit message must include Replay level."""
    runs_root = tmp_path / "runs" / "cleanroom"
    run_dir = runs_root / "test-cr-replay"
    run_dir.mkdir(parents=True)
    _make_full_run_artifacts(run_dir, run_id="test-cr-replay")

    scope = _fake_scope()
    with patch("lib.cleanroom_scope.resolve", return_value=scope), \
         patch("commands.ops.cleanroom_regen._git_content_clean", return_value=True):
        rc = main(["commit-ready", "--family", "cells", "--platform", "java",
                   "--run-id", "test-cr-replay", "--runs-root", str(runs_root)])

    assert rc == Exit.OK
    report = json.loads((run_dir / "commit-readiness-report.json").read_text())
    assert "Replay level:" in report["commit_message_template"]


# ===========================================================================
# P-11: snapshot refuses duplicate run_id
# ===========================================================================

def test_snapshot_refuses_duplicate_run_id(tmp_path):
    """snapshot must refuse existing run_id without --resume."""
    runs_root = tmp_path / "runs" / "cleanroom"
    run_dir = runs_root / "test-snap-dup"
    run_dir.mkdir(parents=True)
    _write_artifact(run_dir, "run_state.json", {"run_id": "test-snap-dup", "completed_modes": []})

    scope = _fake_scope()
    with patch("lib.cleanroom_scope.resolve", return_value=scope), \
         patch("commands.ops.cleanroom_regen._git_current_branch", return_value="test/s96"), \
         patch("commands.ops.cleanroom_regen._git_head_sha", return_value="abc1234"), \
         patch("commands.ops.cleanroom_regen._git_content_clean", return_value=True):
        rc = main(["snapshot", "--family", "cells", "--platform", "java",
                   "--run-id", "test-snap-dup", "--runs-root", str(runs_root)])

    assert rc == Exit.LOCK_CONFLICT


def test_snapshot_with_resume_flag_overwrites(tmp_path):
    """snapshot with --resume must allow overwriting an existing run_id."""
    runs_root = tmp_path / "runs" / "cleanroom"
    run_dir = runs_root / "test-snap-resume"
    run_dir.mkdir(parents=True)
    _write_artifact(run_dir, "run_state.json", {"run_id": "test-snap-resume", "completed_modes": []})

    scope = _fake_scope()
    with patch("lib.cleanroom_scope.resolve", return_value=scope), \
         patch("commands.ops.cleanroom_regen._git_current_branch", return_value="test/s96"), \
         patch("commands.ops.cleanroom_regen._git_head_sha", return_value="abc1234"), \
         patch("commands.ops.cleanroom_regen._git_content_clean", return_value=True), \
         patch("commands.ops.cleanroom_manifest.capture_baseline") as mock_capture:
        mock_manifest = MagicMock()
        mock_manifest._errors = []
        mock_manifest.files = {}
        mock_manifest.to_dict.return_value = {
            "run_id": "test-snap-resume", "baseline_git_sha": "abc1234",
            "captured_at": "2026-01-01T00:00:00Z", "scope": {"family": "cells"},
            "files": {}, "_errors": []
        }
        mock_capture.return_value = mock_manifest
        rc = main(["snapshot", "--family", "cells", "--platform", "java",
                   "--run-id", "test-snap-resume", "--resume",
                   "--runs-root", str(runs_root)])

    assert rc == Exit.OK


# ===========================================================================
# P-10: review returns SCHEMA_FAIL on invalid artifact
# ===========================================================================

def test_review_returns_schema_fail_on_invalid_artifact(tmp_path):
    """mode_review must return SCHEMA_FAIL when schema validation fails."""
    runs_root = tmp_path / "runs" / "cleanroom"
    run_dir = runs_root / "test-review-schema"
    run_dir.mkdir(parents=True)
    _write_artifact(run_dir, "diff-report.json", {"run_id": "test-review-schema", "entries": []})
    _write_artifact(run_dir, "baseline-manifest.json", {"run_id": "test-review-schema", "files": {}})

    scope = _fake_scope()
    with patch("lib.cleanroom_scope.resolve", return_value=scope), \
         patch("commands.ops.editorial_review_classifier.load_rules", return_value={}), \
         patch("commands.ops.cleanroom_regen._validate_json", return_value=["Schema error: missing required field"]):
        rc = main(["review", "--family", "cells", "--platform", "java",
                   "--run-id", "test-review-schema", "--runs-root", str(runs_root)])

    assert rc == Exit.SCHEMA_FAIL


# ===========================================================================
# P-12: snapshot records dirty-content warning
# ===========================================================================

def test_snapshot_warns_when_content_dirty(tmp_path, capsys):
    """snapshot must print a warning when content/ is dirty."""
    runs_root = tmp_path / "runs" / "cleanroom"

    scope = _fake_scope()
    with patch("lib.cleanroom_scope.resolve", return_value=scope), \
         patch("commands.ops.cleanroom_regen._git_current_branch", return_value="test/s96"), \
         patch("commands.ops.cleanroom_regen._git_head_sha", return_value="abc1234"), \
         patch("commands.ops.cleanroom_regen._git_content_clean", return_value=False), \
         patch("commands.ops.cleanroom_manifest.capture_baseline") as mock_capture:
        mock_manifest = MagicMock()
        mock_manifest._errors = []
        mock_manifest.files = {}
        mock_manifest.to_dict.return_value = {
            "run_id": "test-snap-dirty", "baseline_git_sha": "abc1234",
            "captured_at": "2026-01-01T00:00:00Z", "scope": {"family": "cells"},
            "files": {}, "_errors": []
        }
        mock_capture.return_value = mock_manifest
        rc = main(["snapshot", "--family", "cells", "--platform", "java",
                   "--run-id", "test-snap-dirty", "--runs-root", str(runs_root)])

    assert rc == Exit.OK
    captured = capsys.readouterr()
    assert "WARNING" in captured.out
    assert "content/" in captured.out
