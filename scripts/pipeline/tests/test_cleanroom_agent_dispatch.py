"""
TC-S96-014A: Tests for agent dispatch ledger protocol (Phase B of Mode 3).

Validates the gate logic in Mode 4 (diff) that blocks on incomplete agent tasks,
and the constraints on agent-execution-ledger.json structure.
"""

import json
import pathlib
from unittest.mock import patch

import pytest

from commands.ops.cleanroom_regen import Exit, main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_scope(subdomains=None, family="cells", platform="java"):
    class FakeScope:
        pass
    s = FakeScope()
    s.family = family
    s.platform = platform
    s.subdomains = subdomains or ["reference"]
    s.files = []
    s.content_roots = {}
    s.generation_entry_points = {
        sub: {"type": "script" if sub == "reference" else "agent",
              "skill": "S-62" if sub == "reference" else "S-57"}
        for sub in (subdomains or ["reference"])
    }
    s.knowledge_model_path = None
    s._errors = []
    s._warnings = []
    return s


def _write_baseline(run_dir, sha="abc1234"):
    """Write the minimal baseline-manifest.json required by diff mode."""
    (run_dir / "baseline-manifest.json").write_text(json.dumps({
        "run_id": run_dir.name,
        "baseline_git_sha": sha,
        "captured_at": "2026-01-01T00:00:00Z",
        "scope": {"family": "cells"},
        "files": {},
        "_errors": [],
    }), encoding="utf-8")


# ---------------------------------------------------------------------------
# TC1: reference-only plan — diff allowed immediately (no ledger needed)
# ---------------------------------------------------------------------------

def test_reference_only_plan_diff_allowed_without_ledger(tmp_path):
    """If regeneration-plan.json has only reference entries, diff must not gate on ledger."""
    runs_root = tmp_path / "runs" / "cleanroom"
    run_dir = runs_root / "test-ref-only"
    run_dir.mkdir(parents=True)

    sha = "abc1234"
    _write_baseline(run_dir, sha)
    # Reference-only regeneration plan (no agent subdomain entries)
    (run_dir / "regeneration-plan.json").write_text(json.dumps({
        "run_id": "test-ref-only",
        "baseline_git_sha": sha,
        "phase_a_complete": True,
        "entries": [
            {
                "planned_task_id": "ref-t1",
                "subdomain": "reference",
                "skill_id": "S-62",
                "target_path": "content/reference.aspose.org/en/cells/java/Workbook.md",
                "skill_args": {},
                "status": "COMPLETED",
            }
        ],
    }), encoding="utf-8")
    # No agent-execution-ledger.json — should be OK for reference-only

    scope = _fake_scope(subdomains=["reference"])
    with patch("lib.cleanroom_scope.resolve", return_value=scope):
        rc = main(["diff", "--family", "cells", "--platform", "java",
                   "--run-id", "test-ref-only", "--runs-root", str(runs_root)])

    # diff should not exit MISSING_ARTIFACT (5) for reference-only plan
    assert rc != Exit.MISSING_ARTIFACT


# ---------------------------------------------------------------------------
# TC2: non-reference plan exists — diff must check for ledger
# ---------------------------------------------------------------------------

def test_non_reference_plan_diff_checks_for_ledger(tmp_path):
    """If regeneration-plan.json has blog entries, diff must require agent-execution-ledger.json."""
    runs_root = tmp_path / "runs" / "cleanroom"
    run_dir = runs_root / "test-blog-plan"
    run_dir.mkdir(parents=True)

    sha = "abc1234"
    _write_baseline(run_dir, sha)
    (run_dir / "regeneration-plan.json").write_text(json.dumps({
        "run_id": "test-blog-plan",
        "baseline_git_sha": sha,
        "phase_a_complete": True,
        "entries": [
            {
                "planned_task_id": "blog-t1",
                "subdomain": "blog",
                "skill_id": "S-57",
                "target_path": "content/blog.aspose.org/cells/java/my-post/index.md",
                "skill_args": {},
                "status": "PLANNED",
            }
        ],
    }), encoding="utf-8")
    # No agent-execution-ledger.json

    scope = _fake_scope(subdomains=["blog"])
    scope.generation_entry_points = {"blog": {"type": "agent", "skill": "S-57"}}

    with patch("lib.cleanroom_scope.resolve", return_value=scope):
        rc = main(["diff", "--family", "cells", "--platform", "java",
                   "--run-id", "test-blog-plan", "--runs-root", str(runs_root)])

    assert rc == Exit.MISSING_ARTIFACT


# ---------------------------------------------------------------------------
# TC3: diff fails when ledger missing → exit 5
# ---------------------------------------------------------------------------

def test_diff_fails_when_ledger_missing(tmp_path):
    """diff must exit MISSING_ARTIFACT when agent plan exists but ledger is absent."""
    runs_root = tmp_path / "runs" / "cleanroom"
    run_dir = runs_root / "test-no-ledger"
    run_dir.mkdir(parents=True)

    sha = "abc1234"
    _write_baseline(run_dir, sha)
    (run_dir / "regeneration-plan.json").write_text(json.dumps({
        "run_id": "test-no-ledger",
        "baseline_git_sha": sha,
        "phase_a_complete": True,
        "entries": [
            {
                "planned_task_id": "docs-t1",
                "subdomain": "docs",
                "skill_id": "S-56",
                "target_path": "content/docs.aspose.org/en/cells/java/features.md",
                "skill_args": {},
                "status": "PLANNED",
            }
        ],
    }), encoding="utf-8")
    # No ledger file

    scope = _fake_scope(subdomains=["docs"])
    scope.generation_entry_points = {"docs": {"type": "agent", "skill": "S-56"}}

    with patch("lib.cleanroom_scope.resolve", return_value=scope):
        rc = main(["diff", "--family", "cells", "--platform", "java",
                   "--run-id", "test-no-ledger", "--runs-root", str(runs_root)])

    assert rc == Exit.MISSING_ARTIFACT


# ---------------------------------------------------------------------------
# TC4: diff fails when ledger has PLANNED entry → exit 5
# ---------------------------------------------------------------------------

def test_diff_fails_when_ledger_has_planned_entry(tmp_path):
    """diff must exit MISSING_ARTIFACT when ledger exists but has PLANNED entries."""
    runs_root = tmp_path / "runs" / "cleanroom"
    run_dir = runs_root / "test-planned-entry"
    run_dir.mkdir(parents=True)

    sha = "abc1234"
    _write_baseline(run_dir, sha)
    (run_dir / "regeneration-plan.json").write_text(json.dumps({
        "run_id": "test-planned-entry",
        "baseline_git_sha": sha,
        "phase_a_complete": True,
        "entries": [
            {
                "planned_task_id": "blog-t2",
                "subdomain": "blog",
                "skill_id": "S-57",
                "target_path": "content/blog.aspose.org/cells/java/post2/index.md",
                "skill_args": {},
                "status": "PLANNED",
            }
        ],
    }), encoding="utf-8")
    (run_dir / "agent-execution-ledger.json").write_text(json.dumps({
        "run_id": "test-planned-entry",
        "phase_a_complete": True,
        "phase_b_complete": False,
        "entries": [
            {
                "planned_task_id": "blog-t2",
                "subdomain": "blog",
                "skill_id": "S-57",
                "target_path": "content/blog.aspose.org/cells/java/post2/index.md",
                "source_site_plan_entry": None,
                "status": "PLANNED",
                "started_at": None,
                "completed_at": None,
                "output_files": [],
                "error": None,
                "agent_notes": None,
                "verification_status": "UNVERIFIED",
            }
        ],
    }), encoding="utf-8")

    scope = _fake_scope(subdomains=["blog"])
    scope.generation_entry_points = {"blog": {"type": "agent", "skill": "S-57"}}

    with patch("lib.cleanroom_scope.resolve", return_value=scope):
        rc = main(["diff", "--family", "cells", "--platform", "java",
                   "--run-id", "test-planned-entry", "--runs-root", str(runs_root)])

    assert rc == Exit.MISSING_ARTIFACT


# ---------------------------------------------------------------------------
# TC5: diff passes when all agent tasks COMPLETED or SKIPPED_WITH_REASON
# ---------------------------------------------------------------------------

def test_diff_passes_when_all_agent_tasks_terminal(tmp_path):
    """diff must proceed when all agent tasks are in terminal state."""
    runs_root = tmp_path / "runs" / "cleanroom"
    run_dir = runs_root / "test-all-terminal"
    run_dir.mkdir(parents=True)

    sha = "abc1234"
    _write_baseline(run_dir, sha)
    (run_dir / "regeneration-plan.json").write_text(json.dumps({
        "run_id": "test-all-terminal",
        "baseline_git_sha": sha,
        "phase_a_complete": True,
        "entries": [
            {
                "planned_task_id": "blog-t3",
                "subdomain": "blog",
                "skill_id": "S-57",
                "target_path": "content/blog.aspose.org/cells/java/post3/index.md",
                "skill_args": {},
                "status": "COMPLETED",
            }
        ],
    }), encoding="utf-8")
    (run_dir / "agent-execution-ledger.json").write_text(json.dumps({
        "run_id": "test-all-terminal",
        "phase_a_complete": True,
        "phase_b_complete": True,
        "entries": [
            {
                "planned_task_id": "blog-t3",
                "subdomain": "blog",
                "skill_id": "S-57",
                "target_path": "content/blog.aspose.org/cells/java/post3/index.md",
                "source_site_plan_entry": None,
                "status": "COMPLETED",
                "started_at": "2026-01-01T00:00:00Z",
                "completed_at": "2026-01-01T00:01:00Z",
                "output_files": ["content/blog.aspose.org/cells/java/post3/index.md"],
                "error": None,
                "agent_notes": None,
                "verification_status": "VERIFIED",
            }
        ],
    }), encoding="utf-8")

    scope = _fake_scope(subdomains=["blog"])
    scope.generation_entry_points = {"blog": {"type": "agent", "skill": "S-57"}}

    with patch("lib.cleanroom_scope.resolve", return_value=scope):
        rc = main(["diff", "--family", "cells", "--platform", "java",
                   "--run-id", "test-all-terminal", "--runs-root", str(runs_root)])

    # Should not fail with MISSING_ARTIFACT — diff proceeds
    assert rc != Exit.MISSING_ARTIFACT


# ---------------------------------------------------------------------------
# TC6: commit-ready fails when agent-failures.json has entries
# ---------------------------------------------------------------------------

def test_commit_ready_fails_with_agent_failures(tmp_path):
    """commit-ready must fail (exit COMMIT_READINESS_FAIL) when agent-failures.json has entries."""
    runs_root = tmp_path / "runs" / "cleanroom"
    run_dir = runs_root / "test-cr-failures"
    run_dir.mkdir(parents=True)

    sha = "abc1234"
    for name, data in [
        ("baseline-manifest.json", {
            "run_id": "test-cr-failures", "baseline_git_sha": sha,
            "captured_at": "2026-01-01T00:00:00Z", "scope": {"family": "cells"}, "files": {}, "_errors": [],
        }),
        ("diff-report.json", {
            "run_id": "test-cr-failures", "baseline_git_sha": sha,
            "generated_at": "2026-01-01T00:00:00Z",
            "counts": {"added": 0, "edited": 0, "deleted": 0, "unchanged": 0,
                       "generated_identical": 0, "out_of_scope": 0, "churn_only": 0},
            "entries": [],
        }),
        ("review-report.json", {
            "run_id": "test-cr-failures", "baseline_git_sha": sha,
            "generated_at": "2026-01-01T00:00:00Z", "llm_review_used": False,
            "counts": {"good_keep": 0, "bad_revert": 0, "risky_review": 0, "unclear_needs_evidence": 0},
            "entries": [],
        }),
        ("decision-ledger.json", {
            "run_id": "test-cr-failures", "baseline_git_sha": sha,
            "generated_at": "2026-01-01T00:00:00Z",
            "counts": {"kept": 0, "reverted": 0, "deleted": 0, "pending_risky": 0, "pending_unclear": 0},
            "entries": [],
        }),
        ("validator-report.json", {
            "run_id": "test-cr-failures", "generated_at": "2026-01-01T00:00:00Z",
            "overall_passed": True, "validators": {},
        }),
        ("test-report.json", {
            "run_id": "test-cr-failures", "generated_at": "2026-01-01T00:00:00Z",
            "passed": True, "exit_code": 0,
            "summary": {"total": 10, "passed": 10, "failed": 0, "errors": 0, "skipped": 0},
        }),
        ("run_state.json", {
            "run_id": "test-cr-failures",
            "target": {"family": "cells", "platform": "java", "subdomains": ["blog"]},
            "baseline_git_sha": sha, "isolated_branch": "test/s96",
            "started_at": "2026-01-01T00:00:00Z", "completed_modes": [],
            "resumable": True, "lock_status": "LOCKED",
        }),
        # agent-failures.json with a FAILED entry
        ("agent-failures.json", {
            "run_id": "test-cr-failures",
            "failures": [
                {
                    "planned_task_id": "blog-fail-1",
                    "subdomain": "blog",
                    "target_path": "content/blog.aspose.org/cells/java/failed-post/index.md",
                    "status": "FAILED",
                    "error": "Skill S-57 timed out",
                    "retry_hint": "Re-invoke S-57 for this slug",
                }
            ],
        }),
    ]:
        (run_dir / name).write_text(json.dumps(data), encoding="utf-8")

    scope = _fake_scope(subdomains=["blog"])
    scope.generation_entry_points = {"blog": {"type": "agent", "skill": "S-57"}}

    with patch("lib.cleanroom_scope.resolve", return_value=scope), \
         patch("commands.ops.cleanroom_regen._git_content_clean", return_value=True):
        rc = main(["commit-ready", "--family", "cells", "--platform", "java",
                   "--run-id", "test-cr-failures", "--runs-root", str(runs_root)])

    assert rc == Exit.COMMIT_READINESS_FAIL
