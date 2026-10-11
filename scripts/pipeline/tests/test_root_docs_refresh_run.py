"""Round-trip state-machine test for root_docs_refresh_run.py, against a scratch fixture
repo (real git, never the actual aspose.org repo). Proves the two load-bearing safety
properties from the plan (moonlit-strolling-sunset.md): (1) submit() hard-gates on real
findings instead of silently advancing, and (2) approve() detects git-HEAD drift between
plan() and approve() -- the direct defense against the concurrent-session hazard this repo
has hit before -- rather than approving against a stale factpack.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "commands" / "governance"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

import root_docs_refresh_run as rdr  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_configure():
    yield
    rdr.configure()


def _run_git(args, cwd):
    result = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, f"git {args} failed: {result.stderr}"
    return result.stdout.strip()


_REGISTRY = (
    "| Skill | ID | Purpose |\n"
    "|-------|----|--------|\n"
    "| content-check | S-23 | Deterministic API accuracy audit |\n"
)

_CLEAN_OPERATOR_GUIDE = "# Operator Guide\n\n### content-check (S-23)\n\nSee data/products.json for the current count.\n"
_BROKEN_OPERATOR_GUIDE = (
    "# Operator Guide\n\n### translate\n```bash\n"
    "python scripts/translator/cli.py batch\n```\n"
)

_INIT_TEXT = 'EVALUATOR_FREEZE_VERSION: str | None = "18"\n'
_GRADE_CONFIG_TEXT = "TA:\n  ceiling: C\n"
_CLEAN_GRADE_CONTRACT = "Current frozen baseline: EVALUATOR_FREEZE_VERSION = 18.\n| TA | WARN | C | type_accuracy |\n"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _build_repo(tmp_path: Path, *, operator_guide_text: str) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run_git(["init", "-q"], cwd=repo)
    _run_git(["config", "user.email", "test@example.com"], cwd=repo)
    _run_git(["config", "user.name", "Test"], cwd=repo)

    _write(repo / "data" / "products.json", json.dumps([{"family": "3d", "platform": "net", "active": True}]))
    _write(repo / "docs" / "registries" / "skills.md", _REGISTRY)
    _write(repo / "scripts" / "pipeline" / "content_eval" / "__init__.py", _INIT_TEXT)
    _write(repo / "scripts" / "pipeline" / "content_eval" / "grade_config.yaml", _GRADE_CONFIG_TEXT)

    _write(repo / "OPERATOR_GUIDE.md", operator_guide_text)
    _write(repo / "RUNBOOK.md", "# Runbook\n")
    _write(repo / "CODEX.md", "# Codex\n")
    _write(repo / "GRADE_CONTRACT.md", _CLEAN_GRADE_CONTRACT)
    _write(repo / "LAYMAN_SYSTEM_STATUS_REVIEW.md", "# Snapshot\n")
    _write(repo / "TASK_BACKLOG_20260521.md", "# Backlog snapshot\n")

    _run_git(["add", "-A"], cwd=repo)
    _run_git(["commit", "-q", "-m", "initial"], cwd=repo)
    return repo


def _configure(repo: Path) -> None:
    rdr.configure(repo_root=repo, reports_root=repo / "reports")


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_full_lifecycle_reaches_committed(tmp_path):
    repo = _build_repo(tmp_path, operator_guide_text=_CLEAN_OPERATOR_GUIDE)
    _configure(repo)

    manifest = rdr.plan(session_id="test-session-1")
    assert manifest["state"] == "FACTS_PINNED"
    run_id = manifest["run_id"]

    results = rdr.recheck(run_id)
    assert results["total_hard_gate"] == 0

    manifest = rdr.submit(run_id)
    assert manifest["state"] == "AWAITING_REVIEW"

    manifest = rdr.approve(run_id, note="looks good", session_id="test-session-1")
    assert manifest["state"] == "APPROVED"

    manifest = rdr.commit_prepare(run_id, changed_files=["OPERATOR_GUIDE.md"], reason="test commit prep")
    assert manifest["commit_prepare"]["override_token_ids"]

    manifest = rdr.finalize(run_id, commit_sha="deadbeef")
    assert manifest["state"] == "COMMITTED"
    assert manifest["commit_sha"] == "deadbeef"

    # ACTIVE.json is cleared once terminal -- a new plan() must be able to start.
    assert not rdr._active_path().is_file()


# ---------------------------------------------------------------------------
# Hard-gate safety property
# ---------------------------------------------------------------------------


def test_submit_blocks_on_hard_gate_finding(tmp_path):
    repo = _build_repo(tmp_path, operator_guide_text=_BROKEN_OPERATOR_GUIDE)
    _configure(repo)

    manifest = rdr.plan(session_id="test-session-1")
    run_id = manifest["run_id"]

    with pytest.raises(rdr.RootDocsRefreshRunError, match="HARD_GATE finding"):
        rdr.submit(run_id)

    # Manifest must still be FACTS_PINNED -- a hard-gate failure must never silently advance.
    assert rdr.status(run_id)["state"] == "FACTS_PINNED"


def test_submit_passes_after_remediation_and_recheck(tmp_path):
    repo = _build_repo(tmp_path, operator_guide_text=_BROKEN_OPERATOR_GUIDE)
    _configure(repo)

    manifest = rdr.plan(session_id="test-session-1")
    run_id = manifest["run_id"]
    with pytest.raises(rdr.RootDocsRefreshRunError):
        rdr.submit(run_id)

    # Remediate: fix the dead reference in place, exactly like the real skill's remediation step.
    (repo / "OPERATOR_GUIDE.md").write_text(_CLEAN_OPERATOR_GUIDE, encoding="utf-8")
    results = rdr.recheck(run_id)
    assert results["total_hard_gate"] == 0

    manifest = rdr.submit(run_id)
    assert manifest["state"] == "AWAITING_REVIEW"


# ---------------------------------------------------------------------------
# Drift-detection safety property (concurrent-session hazard)
# ---------------------------------------------------------------------------


def test_approve_forces_replan_on_git_head_drift(tmp_path):
    repo = _build_repo(tmp_path, operator_guide_text=_CLEAN_OPERATOR_GUIDE)
    _configure(repo)

    manifest = rdr.plan(session_id="test-session-1")
    run_id = manifest["run_id"]
    rdr.recheck(run_id)
    rdr.submit(run_id)

    # Simulate a concurrent session committing to main between plan() and approve().
    (repo / "UNRELATED.md").write_text("someone else's change\n", encoding="utf-8")
    _run_git(["add", "-A"], cwd=repo)
    _run_git(["commit", "-q", "-m", "concurrent session commit"], cwd=repo)

    with pytest.raises(rdr.RootDocsRefreshRunError, match="HEAD moved"):
        rdr.approve(run_id, note="approving stale state", session_id="test-session-1")

    # Forced back to FACTS_PINNED, not left in an ambiguous AWAITING_REVIEW state.
    assert rdr.status(run_id)["state"] == "FACTS_PINNED"


# ---------------------------------------------------------------------------
# State machine integrity
# ---------------------------------------------------------------------------


def test_illegal_transition_rejected(tmp_path):
    repo = _build_repo(tmp_path, operator_guide_text=_CLEAN_OPERATOR_GUIDE)
    _configure(repo)
    manifest = rdr.plan(session_id="test-session-1")
    run_id = manifest["run_id"]

    # approve() before submit() -- FACTS_PINNED has no direct APPROVED transition.
    with pytest.raises(rdr.RootDocsRefreshRunError):
        rdr.approve(run_id, note="skip ahead", session_id="test-session-1")


def test_concurrent_plan_blocked_while_run_active(tmp_path):
    repo = _build_repo(tmp_path, operator_guide_text=_CLEAN_OPERATOR_GUIDE)
    _configure(repo)
    rdr.plan(session_id="session-a")

    with pytest.raises(rdr.RootDocsRefreshRunError, match="already has active run"):
        rdr.plan(session_id="session-b")


def test_abandon_from_facts_pinned(tmp_path):
    repo = _build_repo(tmp_path, operator_guide_text=_CLEAN_OPERATOR_GUIDE)
    _configure(repo)
    manifest = rdr.plan(session_id="test-session-1")
    run_id = manifest["run_id"]

    manifest = rdr.abandon(run_id, reason="testing abandon path")
    assert manifest["state"] == "ABANDONED"
    assert not rdr._active_path().is_file()

    # A new plan() must now be able to start -- ACTIVE.json was cleared.
    new_manifest = rdr.plan(session_id="test-session-1")
    assert new_manifest["run_id"] != run_id


def test_approve_requires_nonempty_note(tmp_path):
    repo = _build_repo(tmp_path, operator_guide_text=_CLEAN_OPERATOR_GUIDE)
    _configure(repo)
    manifest = rdr.plan(session_id="test-session-1")
    run_id = manifest["run_id"]
    rdr.recheck(run_id)
    rdr.submit(run_id)

    with pytest.raises(rdr.RootDocsRefreshRunError, match="non-empty --note"):
        rdr.approve(run_id, note="   ", session_id="test-session-1")
